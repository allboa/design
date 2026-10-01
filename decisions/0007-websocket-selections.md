# 0007: Selections and events from the page to R over a websocket

- Date: 2026-10-01
- Status: proposed
- Issue: allboa/design#14 (decision 0006, proposed issue 8)
- Decided by: agent

## Question

The design post's third transport is "updated over a websocket (with
selections coming back to R as row ids)". Decision 0006 built the local
server and sketched the socket in its item 5, leaving four things to this
record: the message types, row ids versus feature ids, how a selection
reaches the user in R, and one server per scene or per session. How should
a served page send selections and its view back to R, what does the R user
call to get them, and what does that cost in security, dependencies and the
scene spec?

## Answer

Proposed: the server from `serve_scene()` also takes a websocket at
`/<token>/ws`, after the same `Host` check as every route plus an `Origin`
check, both made when the upgrade's headers arrive and again when the socket
opens (the spike found httpuv opens the socket even after the first check
has refused it). Messages are JSON text frames of **protocol 1**, versioned
apart from the scene spec. The page sends `hello`, `select` and `view`; R
sends `hello` and `reload`. A selection is the page's whole selection, a
list of layer ids each with 0-based row indices into that layer's Arrow
data, the same index the renderer already uses for popups. R adds 1 and maps
it, through a table aobview keeps outside the scene, to rows of the object
the user passed to `view()`. In R the selection is **pulled**:
`selection(v)` gives indices, `selected(v)` gives the rows of the object,
and `wait_for_selection(v)` blocks until the next one; a callback stays an
aobcore primitive. R pushes only `reload` in this milestone. **No scene spec
change**: which layers can be selected is said by the transport, in R's
`hello`. Embedded pages have no socket, and the R functions say so. Servers
stay one per scene.

## What exists today

- **Picking in the renderer** (aobcore `js/src/index.js`, `layers.js`). A
  vector layer is pickable only when it has a 0.5 popup (`layers.js` line
  82, `pickable: popup`). A pick resolves to a feature row with
  `p.rowOffset + p.feature[info.index]` (`index.js` line 325): the row of
  the layer's Arrow table, counting every record batch in stream order.
  That row is what the popup shows, what the element's
  `data-aob-selected="<layer id>:<row>"` holds, and what
  `handle.selected()` returns. Clicks are the renderer's own press and
  release since aobcore#27, so a slow pick never drops one.
- **The popup spec text** (scenespec 0.5, `popup`) says "Only feature
  attributes are shown; nothing is sent back to the producer". That is
  about popups, and stays true: a selection travels by the transport, not
  because a layer has a popup.
- **Layer rows are not the rows of the user's object.** aobview's
  `add_sfc()` (`R/view.R`) drops empty geometries (line 345) and those that
  cannot be transformed (line 362), splits mixed geometry into up to three
  layers (line 376, `idx <- rows[split$rows[[kind]]]`), and splits a
  geometry collection into parts (line 787 on), so one source row can be
  several rows of one layer. The mapping `idx` is computed and dropped; the
  view does not keep it.
- **The server** (aobcore `R/serve.R`, decision 0006 part B). One httpuv
  server per scene on 127.0.0.1, routes under a 128-bit token, a `Host`
  check with `aobcore.serve_hosts`, `GET` and `HEAD` only, state in an
  environment (`srv$state`) that `serve_scene(scene, server = srv)`
  replaces in place. aobview's served views use it through `serve_view()`
  (`R/transport.R`), and `view_add()` on a served view replaces the scene
  and opens the URL again.
- **JSON.** aobcore writes JSON in base R (`R/json.R`) but cannot read it.
  jsonlite is already in aobcore's Suggests (for tests).
- **httpuv 1.6.17** (checked here): `startServer(host, port, app, quiet)`;
  the app may define `onHeaders(req)` (return a response to refuse the
  request) and `onWSOpen(ws)`; `ws` is an R6 `WebSocket` with `request`,
  `onMessage(function(binary, message))`, `onClose()`, `send()` and
  `close(code, reason)`; `service(timeoutMs)` runs `later::run_now()`. Its
  help says app callbacks run only when R is idle or in `service()`. Its
  NEWS says sockets are pinged every 20 s. It has no setting for a largest
  websocket message.

## Decisions

### 1. The socket, and its security

Options:

- **a. A websocket on the same server, `/<token>/ws`**, as decision 0006
  item 5 says.
- b. A `POST` route for the page's messages. Rejected: it is one-way, so a
  later push from R needs polling, and it opens a method 0006 refuses
  (405); a cross-origin form or `fetch` can send a "simple" `POST` without a
  preflight, so it needs the same `Origin` check anyway.
- c. A second server or port for the socket. Rejected: a second origin, so
  the `Origin` check would have to allow one more, and two ports to keep in
  step for nothing.

Recommended: **a**, with all of these:

- **The upgrade goes through the same gates as any request.** The path
  must be exactly `/<token>/ws` (else 404, as a wrong token is today), the
  `Host` must pass 0006's check, with `aobcore.serve_hosts` and the same
  escaped, once-per-host warning (else 403). Only `GET` with
  `Upgrade: websocket` is an upgrade; `/<token>/ws` without it answers 404.
- **`Origin` check.** The `Origin` must be `http://127.0.0.1:<port>` or
  `http://localhost:<port>`, or, for each value `H` in
  `aobcore.serve_hosts`, `http://H` or `https://H` (an IDE proxy serves
  the page from its own origin, often over TLS). Compared exactly, without
  regard to case in the scheme and host. A missing `Origin` is refused
  (403): browsers always send one on a websocket, and a local non-browser
  client can send it too (tests do). This is the check that matters: a
  page on another origin cannot read the token, but if it ever learns it
  (a URL pasted in a chat), the browser would still let it open the
  socket, and only `Origin` stops it.
- **Both checks run twice.** In `onHeaders()`, which answers 403 or 404
  before the handshake, and again in `onWSOpen()`, which closes the socket
  at once (1008) if they fail. The spike (Evidence) found that httpuv
  sends the refusal from `onHeaders()` and then still calls `onWSOpen()`
  for that connection, so a server that checked only in `onHeaders()`
  would register a socket for a refused client. `call()` is not called
  for an upgrade.
- **Text frames only from the page.** A binary frame closes the socket
  (1003). Binary frames are kept for R to page blobs (0006 item 5).
- **Size cap.** A text message over `getOption("aobcore.ws_max_message",
  2^20)` bytes (1 MiB) closes the socket (1009), with a warning in R. httpuv
  has no cap of its own and hands R the whole message (the spike sent
  2 MiB), so the cap limits what R parses, not what httpuv buffers; the
  peer that can send it has already passed the token, `Host` and `Origin`
  checks. 1 MiB holds about 120000 row indices; the page knows the cap
  (from `hello`) and does not send a larger selection: it keeps it in the
  page and shows a note that it is too large to send.
- **Malformed messages.** Text that is not JSON, or JSON that is not an
  object with a string `type`, closes the socket (1007). A known type with
  bad fields (an unknown layer, a row out of range, a row that is not a
  whole number) is dropped with a warning, once per connection and type,
  and the connection stays. An unknown type is ignored, so a newer page can
  talk to an older R.
- **Several pages.** Each socket is a connection with a number. At most 8
  are open per server; a ninth is closed (1013, try again later) with a
  warning naming the cap. Two tabs on one view are two connections.
- **No change to the HTTP routes**, their headers or their checks.

What the token, `Host` and `Origin` checks together do not stop: another
process of the same user that reads the URL can open the socket with any
headers, as it can already read the scene. A socket message only sets R's
record of the selection and view; it never evaluates anything, names a
file or reaches the scene, so the worst such a client can do is feed R a
wrong selection.

### 2. Messages: protocol 1

Options:

- **a. JSON text frames with a `type`, versioned by a protocol number that
  is not the scene spec version.**
- b. Version the messages with the scene spec. Rejected: the spec
  describes a scene, which is the same on every transport; the messages are
  the socket's, and a transport without a socket (embedding) has none.
- c. Binary (Arrow) frames for selections. Rejected for now: a selection is
  small; JSON is readable in tests and in the browser's devtools. A very
  large selection (a box over a million points) is the case that might
  bring it back.

Recommended: **a**. Each message is one JSON object. Fields not listed are
ignored; a later protocol 1 may add optional fields and new types. A change
that breaks a receiver is protocol 2.

Page to R:

```json
{"type": "hello", "protocol": 1, "renderer": "0.0.5",
 "specs": ["0.1", "0.2", "0.3", "0.4", "0.5"], "scene": 3}

{"type": "select", "scene": 3, "seq": 12, "trigger": "click",
 "items": [{"layer": "nc", "rows": [3, 17]}],
 "at": [1520345.2, -1834001.7]}

{"type": "view", "scene": 3, "seq": 13,
 "extent": [-2.1e6, 2.3e6, -1.9e6, 1.6e6], "zoom": -12.4,
 "units_per_pixel": 3810.2, "size_px": [1152, 720]}
```

- `select` is **the page's whole selection**, not a change to it: after a
  reconnect or a lost message, the next one is right on its own, and R
  never has to replay. An empty `items` is no selection. `rows` are
  distinct, ascending, 0-based row indices into the layer's Arrow data,
  every record batch in stream order (the renderer's existing row, above).
  `trigger` is `click` (one feature, replacing), `toggle` (a feature added
  or removed), `clear`, or later `box`. `at` is the pressed point in view
  CRS units (projected and cartesian views) or `[lon, lat]` (globe), and
  is present on a click even when it hit no feature, so R can look up a
  raster value there later.
- `view` is sent when the camera settles: 250 ms after its last change,
  and at most four times a second. Orthographic views send `extent`
  (`[xmin, xmax, ymin, ymax]`, view CRS units), `zoom` and
  `units_per_pixel` (the renderer's `currentView()`); a globe sends
  `center` (`[lon, lat]`) and `zoom` instead. This is decision 0003's
  "one round trip per settled view change"; using it to plan tiles is a
  later milestone.
- `seq` counts up per connection, so R can tell order and drop a stale
  message.

R to page:

```json
{"type": "hello", "protocol": 1, "connection": 2, "scene": 3,
 "select": ["nc", "coast"], "max_message": 1048576}

{"type": "reload", "scene": 4}
```

- R answers the page's `hello` with its own. A page whose protocol R does
  not speak is closed (4000, with the reason "protocol"), and the page says
  it needs a newer aobcore. A page that sends anything before `hello` is
  closed (1008).
- `scene` is a serial number R gives each scene a server serves, written
  into the page (as `data-aob-scene-serial`). It changes when the scene is
  replaced. A `select` or `view` for another serial is dropped without a
  warning (a tab left open on an old scene), and R sends that page
  `reload`.
- `select` lists the layers the page may let the viewer select (item 6).
- Reserved for later, from 0006 item 5: R to page `scene`, `layers`,
  `view`, `select` (a selection set from R) and binary blob frames, each a
  new type in protocol 1.

Close codes: 1000 normal; 1001 the server is stopping; 1003 a binary
frame; 1007 not JSON; 1008 refused or out of order; 1009 too large; 1013
too many connections; 4000 protocol.

### 3. Row ids versus feature ids

Options:

- **a. Row indices into the layer's Arrow data**, mapped to the user's
  object in R.
- b. A feature id column in the data, named by a new spec field (say
  `arrowRef.feature_id`), sent back as ids. Rejected for now: every layer
  carries a column it does not draw; the producer must make it unique; and
  R must still map ids to rows. It is worth it when ids must stay the same
  across a scene that changes under the page (a streamed or re-planned
  layer), which this milestone does not have. It would be an additive
  0.x spec field then.
- c. Row indices of the user's object, computed in R and carried as a
  column. Rejected: the same cost as b, and it bakes aobview's notion of
  "source object" into the data.

Recommended: **a**, as decision 0006 item 5 already says. The row is the
one the renderer computes for popups, so a selection and a popup can never
disagree. The mapping to the user's rows lives in R:

- aobview keeps, for each vector layer it adds, the integer vector `idx`
  that `add_sfc()` already computes (layer row `i`, 1-based, came from row
  `idx[i]` of the object), and which source the layer came from. These go
  in the view (`v$sources`: per source its name, the object itself, and
  per layer id its `idx`), never in the scene. Several layer rows can map
  to one source row (a geometry collection's parts); R deduplicates.
- A raster layer is never selectable in this milestone; a click on one
  still sends `at`.
- aobcore by itself reports Arrow rows (1-based) per layer id; it knows
  nothing of sources.

### 4. What R gets

Options for how a selection reaches the user:

- **a. Pull: read the latest selection, or block until the next.** The
  socket updates the server's state whenever R services it; the user reads
  it.
- b. A callback per selection (`on_select(v, f)`). Rejected as the user's
  main interface: `f` runs from the `later` loop at whatever moment R is
  next idle, its errors and output land in the console out of turn, and in
  knitr or a script it runs only while something services the loop. Kept
  as an aobcore primitive (below) for packages built on it.
- c. A reactive value. Rejected: it needs a reactive framework, which is
  Shiny's; that is how the Shiny transport will map it (item 9).

Recommended: **a**.

aobcore, on the `"aob_server"` handle (names open to change):

- `srv$selection()`: the latest selection as a data frame with columns
  `layer` (id) and `row` (1-based Arrow row), with attributes `at`,
  `connection`, `seq` and `time`; zero rows when nothing is selected.
- `srv$view_state()`: the latest `view` message as a list, or `NULL`.
- `srv$wait(type = "select", timeout = Inf)`: services the loop
  (`httpuv::service(100)`) until a message of that type newer than the
  call arrives, and returns what `selection()` or `view_state()` then
  returns; `NULL` (with a message) at the timeout. An interrupt (Esc,
  Ctrl-C) ends it as any R call.
- `srv$on(type, f)`: calls `f(message)` for each message of that type and
  returns a function that removes it; an error in `f` becomes a warning.
- `srv$connections()`: how many pages are connected.

aobview, for the user:

```r
v <- view(nc, transport = "serve")
sel <- wait_for_selection(v)  # blocks until a feature is clicked
selection(v)                  # data frame: source, layer, row (of nc)
selected(v)                   # nc[rows, ], every column of nc
view_state(v)                 # the settled view, in the view CRS
```

- `selection(v)` returns `source` (the name a source was viewed under),
  `layer` and `row` (1-based, into that source object), deduplicated.
- `selected(v, source = NULL)` returns the selected rows of one source
  object: `x[rows, ]` for sf, a SpatVector or a data frame, `x[rows]` for
  an sfc. `source` defaults to the only source with selected rows, and is
  an error naming the sources when there are several.
- `wait_for_selection(v, timeout = Inf)` waits for the next `select`
  message (a click, a toggle or a clear) and returns `selected(v)`.
- Each of these first services the loop once (`httpuv::service(0)`), so a
  selection made just before the call is counted.

Why both indices and rows: indices are cheap and exact for a user who
joins back to their own data; rows are what most people want, and they
carry every column of the object, not only the popup's. The view keeping
the object costs no copy (R copies on change), but it keeps the object
alive as long as the view; the help says so.

**R is single-threaded.** httpuv's I/O thread accepts frames at any time,
but the R handlers run only when R is idle at the prompt or inside
`service()`. Messages sent while R is busy wait and arrive in order (the
spike measured this), and the page stays drawable meanwhile (it is the
HTTP routes, not the socket, that stall a page while R is busy, as 0006
says). At the prompt the selection is current; inside a long computation
it is as old as that computation, which `wait_for_selection()` avoids by
servicing the loop itself.

### 5. Pushing from R to the page

Options:

- a. Nothing from R in this milestone.
- **b. Only `reload` now.** Highlighting a selection set from R, adding,
  removing or restyling layers, moving the camera and pushing blobs come
  later as new message types.
- c. 0006 item 5's whole set now. Rejected: each needs renderer work
  (layer diffing, blob arrival by socket) that this decision does not
  need, and it would make this milestone large.

Recommended: **b**. When `serve_scene(scene, server = srv)` replaces the
scene, R gives it a new serial and sends `reload` to every connected page;
the page reloads itself, and keeps the camera (it saves its view state in
`sessionStorage` under the token, and the reloaded page restores it when
the serial is newer and the view CRS is the same). `view_add()` on a served
view then opens the URL only when no page is connected, instead of every
time; that refines 0006 item 4 ("opens the page again") without changing
what the user sees first. The selection is cleared when the scene is
replaced, in R and, by the reload, in the page, since the page cannot show
a selection R keeps until R can push one.

### 6. Selection in the page

- A page connects only when its element has `data-aob-socket` (a URL
  relative to the page, `"ws"`), which only `serve_scene()`'s linked pages
  carry. It opens the socket after the scene is drawn, so a slow socket
  never delays the map.
- The layers in R's `hello` `select` list become pickable, popup or not;
  other layers are as today. `serve_scene(select = )` sets the list: `NULL`
  (the default) is every vector layer, a character vector names layer ids,
  `character(0)` none. aobview passes the default.
- A click on a feature selects it and only it; a click with Shift (or Ctrl
  or Cmd) adds or removes it; a click on nothing, or Escape, clears. A
  0.5 popup still opens as today for the clicked feature. Selected features
  are drawn highlighted, light and dark; how is the renderer's choice.
  Keyboard selection follows the popup's, when that exists.
- Box selection (Shift and drag) is wanted but is a renderer follow-up; its
  messages are `select` with `trigger: "box"`, so the protocol does not
  change. Lasso is later still, and needs no protocol change either: the
  page sends the rows it found.
- Every change sends one `select`. A selection over the size cap stays in
  the page with a note, and is not sent.

### 7. Scene spec

Options:

- **a. No change.** The transport says which layers can be selected.
- b. Scene spec 0.6 with a renderer-neutral `selectable: true` on vector
  layers. Rejected for now: selecting only means something where there is a
  way back to the producer, so an embedded page would carry a flag it
  cannot honour; and the scene document would no longer be the same on
  every transport, which 0006 kept on purpose.
- c. Make every layer with a popup selectable. Rejected: it ties two
  features together, and a layer without attribute columns could not be
  selected.

Recommended: **a**. Served scenes keep the version
`scene_spec_version()` picks, the lowest that expresses them. If a second
renderer or front end needs selectability in the document (say a lonboard
reading allonboard scenes, gate B), it becomes a 0.6 field then, and
producers write 0.6 only for scenes that use it.

### 8. Embedded views and lost connections

- **Embedded (`file://`) pages** carry no `data-aob-socket` and open no
  socket. They behave exactly as today: popups, no selection mode, no
  highlight, nothing sent anywhere.
- **In R**, `selection()`, `selected()`, `wait_for_selection()` and
  `view_state()` on an embedded view are errors that say why and what to
  do: "This view is embedded in a page on disk, which cannot send
  selections back to R. View it with `transport = \"serve\"` (needs the
  'httpuv' and 'jsonlite' packages)." On a served view whose server has
  stopped they are errors that say so, and `wait_for_selection()` with no
  page connected warns once that it is waiting for a page to connect.
- **jsonlite missing.** Serving still works, the page carries no
  `data-aob-socket`, and `serve_scene()` says once per session that
  selections need jsonlite. The aobview functions error naming it.
- **A page that loses its socket** (the server stopped, the R session
  ended) shows a status note, "Not connected to R: selections stay in
  this page", keeps its selection, and retries with backoff (1 s doubling
  to 30 s) while it is open. On reconnecting it sends `hello` and then its
  whole selection. A page refused for a reason that will not change (1003,
  1007, 1008, 4000) does not retry, and its note says why.
- A busy R does not close the socket, so the page shows nothing then.

### 9. Lifecycle, and later transports

Options for servers (0006 item 4):

- **a. Stay one server per scene.** Each view has its own server, socket
  and selection state, so nothing needs routing.
- b. One server per session, each scene under its own token. Rejected for
  now: it saves ports, which nobody has run short of, and costs a router
  and a shared connection cap.

Recommended: **a**. `stop()` closes every socket (1001) before stopping the
server. The selection lives in the server's state, so it is lost with the
server; `selected(v)` after `v$server$stop()` is an error that says so.
Across tabs the selection is the server's, last message wins, and
`selection(v)` gives the connection it came from; two tabs can highlight
differently until R can push a selection (item 5).

**Shiny and Quarto stay out of scope** (they own their transport), but the
messages are meant to carry over unchanged:

- The page side talks to a channel with `send(message)`,
  `onMessage(f)` and a connected state; the websocket is one channel.
- Shiny: the page sends with `Shiny.setInputValue("<output id>_aob",
  message, {priority: "event"})`, so `input$<id>_aob` holds the latest
  `select` or `view`; an R helper splits them into the same data frames.
  R sends with `session$sendCustomMessage("aob", message)`. Shiny's
  session replaces the token, `Host` and `Origin` checks and `hello`.
- Quarto: a rendered document is an embedded page (no selections); with
  `server: shiny` it is the Shiny case.
- webR: messages pass in-process (a function call or `postMessage`), the
  same objects without JSON text.

## Evidence

This is a design record; nothing in aobcore or aobview was built for it. It
is based on reading aobcore at `e69df2a` (`R/serve.R`, `R/json.R`,
`js/src/index.js`, `js/src/layers.js`, `js/src/popup.js`), aobview at
`493d2e5` (`R/view.R`, `R/transport.R`), and scenespec at `9f8df26`
(`schema/scene-0.5.schema.json`, `popup` and `arrowRef`).

**What was checked in this R** (R 4.5.3, httpuv 1.6.17): the signatures of
`startServer()` and `service()`; the methods of httpuv's `AppWrapper`
(`onHeaders`, `call`, `onWSOpen`, `onWSMessage`, `onWSClose`) and
`WebSocket` (`request`, `onMessage`, `onClose`, `send`, `close`);
`?startServer` (callbacks run only when R is idle or in `service()`,
`onHeaders` may return a response); httpuv's NEWS (20-second pings); no
message-size setting in the documentation or the shared library's strings.
jsonlite, later and processx are installed; the `websocket` and `chromote`
packages are not.

**Spike.** A throwaway httpuv server in R (about 110 lines) and a Node
driver (about 90 lines) using playwright-core and headless Chromium
(playwright build 1194), run in the session's scratchpad and not
committed; they can go to allboa/spikes if wanted. The page opened
`new URL("ws", location.href)` with `ws:` for `http:`. Results:

- The page's socket opened; R's `hello` reached the page; a `select` with
  rows `[0, 4, 99]` came back from R as `1, 5, 100`.
- R busy for 2 s (`Sys.sleep()` with no servicing) while the page sent
  three `view` messages: all three were answered 2.03 s after the first
  was sent, in the order sent.
- A second tab on the same URL got its own connection (number 2).
- A 2 MiB text message reached R whole (2097186 bytes; httpuv did not cap
  it); R closed with 1009 and the page saw 1009.
- A page on another origin (the same host, the next port) that knew the
  token: refused with 403 by `onHeaders()`; the page saw only an error and
  close code 1006.
- Raw upgrades from Node: the right path and `Origin` 101; a wrong token
  404; no `Origin` 403; `Host: evil.example:80` 403; `localhost` as both
  `Host` and `Origin` 101.
- **httpuv still calls `onWSOpen()` after `onHeaders()` has refused the
  upgrade**, for every refused case above (the 403s and the 404), with the
  refused request in `ws$request`. The spike's second check closed each at
  once. `call()` was never called for an upgrade. This is why item 1
  checks twice.

Not checked: an IDE proxy (RStudio Server, Posit Workbench, code-server)
forwarding a websocket, and the `Origin` it sends; Firefox and Safari. Those
belong in the implementation issues.

## Testing

- **R, no network.** Most tests drive the app's `onHeaders()` and
  `onWSOpen()` directly with a fake `ws` (an environment with `request`,
  `onMessage()`, `onClose()`, `send()` and `close()` that record calls).
  They cover: each refusal (path, `Host`, `Origin`, missing `Origin`, a
  listed `aobcore.serve_hosts` value over `http` and `https`) in both
  places; close codes for binary, non-JSON, too large and out of order;
  dropped messages with their once-only warnings; the connection cap; the
  scene serial and `reload`; the selection state and `srv$selection()`,
  `srv$view_state()`, `srv$wait()` (with a message queued by `later` and
  with a timeout) and `srv$on()`. No websocket client package is needed;
  all skip without httpuv or jsonlite.
- **R, over a socket.** The status lines of real upgrade requests (101,
  403, 404) from a base R `socketConnection()` against a server in a child
  R process (processx, already installed here; added to Suggests only if
  the issue needs it). The `websocket` package, if a later issue wants a
  full client in R tests, goes in Suggests with `skip_if_not_installed()`.
- **aobview.** The mapping from layer rows to source rows, with empty
  geometries, an untransformable geometry, mixed geometry split into three
  layers and a geometry collection; `selection()` and `selected()` for sf,
  sfc and SpatVector sources and for two sources; the errors on embedded
  and stopped views.
- **Browser** (headless Chromium through playwright-core, as the popup
  checks are run now, in `tools/`): a served EPSG:3031 view of the
  CCAMLR fixture first (polar first), then Web Mercator. A click on a
  feature makes `selected(v)` in R the row the popup shows; Shift-click
  adds and removes; a click on nothing and Escape clear; a pan sends one
  `view` after it settles; `view_add()` reloads the open page with the same
  camera and opens no new tab; a page on another origin cannot connect;
  after `v$server$stop()` the page shows its note; an embedded page opens
  no socket. Screenshots of a selection, light and dark, as for any
  rendering change.

## Consequences

- **Charter and design post.** The post's third transport, "updated over
  a websocket (with selections coming back to R as row ids)", for
  selections and the view. No change to goals or non-goals.
- **Dependencies.** No Imports change. aobcore uses httpuv and jsonlite,
  both already in Suggests, only when serving. aobview's Imports do not
  change.
- **Scene spec.** No change. The popup text ("nothing is sent back to the
  producer") stays true. A 0.6 `selectable` or a feature id field is left
  for when a second consumer needs one.
- **Renderer.** A socket client behind a channel interface, a selection
  mode for the layers R names (pickable without a popup, highlight,
  Shift-click), settled-view messages, the disconnected note and `reload`
  with the camera kept. Embedded pages are unchanged.
- **aobview.** Views keep a row map and a reference to each vector source
  object. New exports `selection()`, `selected()`, `wait_for_selection()`
  and `view_state()`.
- **Decision 0006.** Item 5's sketch holds: the route, the `Origin` check,
  JSON with a `type`, 0-based rows, `hello`. This record settles its open
  points: Arrow row ids, pulled from R, one server per scene. One
  refinement: `view_add()` on a served view reloads connected pages
  rather than opening the URL each time.
- **Rules out** for now: a feature id column, selections as changes rather
  than whole, binary frames from the page, connections from any origin
  but the page's own (or a listed proxy's), and selection in embedded
  pages.

### Proposed issues (not filed)

1. **aobcore: websocket route and its checks.** `/<token>/ws` with path,
   `Host` and `Origin` checks in `onHeaders()` and again in `onWSOpen()`,
   text only, the size cap, the connection cap, close codes, `stop()`
   closing sockets with 1001. Done when: the R tests above for refusals
   and close codes pass with a fake `ws`, and the real upgrade status
   lines (101, 403, 404) are checked against a child-process server.
2. **aobcore: protocol 1 and the server API.** `hello`, `select`, `view`,
   `reload`; the scene serial in the page; `srv$selection()`,
   `srv$view_state()`, `srv$wait()`, `srv$on()`, `srv$connections()`;
   `serve_scene(select = )`; serving without jsonlite. Done when: the
   R tests above pass, `.Random.seed` is still untouched, and existing
   serve tests pass unchanged.
3. **aobcore renderer: socket client and selection mode.** Done when: the
   browser checks above pass in EPSG:3031 and Web Mercator with
   screenshots light and dark; embedded pages are byte-identical to today
   and open no socket.
4. **aobview: row maps and the selection functions.** Done when: the
   aobview tests above pass, and `wait_for_selection()` returns the clicked
   row in the browser check.
5. Later, each its own issue: box selection; a selection pushed from R
   (highlight); `layers` and blobs over the socket; the Shiny channel.

## Open for Michael

None of these changes the project's goals; they are product choices an
agent should not settle alone:

- Whether served views make every vector layer selectable by default
  (proposed), which changes what a click does on a served view (a
  highlight even without a popup), or only when asked
  (`view(x, select = TRUE)`).
- Whether `wait_for_selection()` on an embedded view should serve it
  (start a server and open a new tab, with a message) instead of the
  proposed error.
- Whether `view_add()` should clear the selection (proposed, until R can
  push one) or keep the rows of layers that did not change.
