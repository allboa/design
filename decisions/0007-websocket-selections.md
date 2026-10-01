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
check, both made when the upgrade's headers arrive and again, first of all, when
the socket opens: the spike and its review found that httpuv completes the
upgrade and delivers messages even after the first check has refused it.
Messages are JSON text frames of **protocol 1**, versioned apart from the scene
spec. The page sends `hello`, `select` and `view`; R sends `hello` and `reload`.
A selection is the page's whole selection, a list of layer ids each with 0-based
row indices into that layer's Arrow data, the same index the renderer already
uses for popups. R adds 1 and maps it, through a table aobview keeps outside the
scene, to rows of the object the user passed to `view()`. In R the selection is
**pulled**: `selection(v)` gives indices, `selected(v)` gives the rows of the
object, and `wait_for_selection(v)` blocks until the next one; a callback stays
an aobcore primitive. R pushes only `reload` in this milestone. **No scene spec
change**: which layers can be selected is said by the transport, in R's `hello`.
Embedded pages have no socket, and the R functions say so. Servers stay one per
scene.

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
  geometry collection into parts (lines 778 to 789), so one source row can be
  several rows of one layer. The mapping `idx` is computed and dropped; the
  view does not keep it.
- **The server** (aobcore `R/serve.R`, decision 0006 part B). One httpuv
  server per scene on 127.0.0.1, routes under a 128-bit token, a `Host`
  check with `aobcore.serve_hosts`, `GET` and `HEAD` only, state in an
  environment (`srv$state`) that `serve_scene(scene, server = srv)`
  replaces in place. aobview's served views use it through `serve_view()`
  (`R/transport.R`), which calls `serve_scene(open = FALSE)`;
  `view_add()` on a served view replaces the scene on the same server.
  The page is opened by `print.aob_view()`, each time a served view is
  printed in an interactive session.
- **Upgrades on aobcore main today.** `serve_scene()`'s app has only
  `call`, so httpuv accepts a websocket upgrade on any path, with no token,
  `Host` or `Origin` check (`call()` is not consulted for an upgrade).
  httpuv's `AppWrapper` then prints "Error in try(private$app$onWSOpen(ws))
  : attempt to apply non-function" to the R console and closes the socket
  with 1011. A page on any origin can trigger that. A small aobcore fix,
  being made ahead of this record, refuses every upgrade in `onHeaders()`
  and closes at once in `onWSOpen()`; this record builds on that fix.
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
  The checks run in that order, path, then `Host`, then `Origin`, so a
  wrong path is a silent 404 whatever its headers. (Amended 2026-10-01,
  from aobcore#43.)
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
- **Both checks run twice.** In `onHeaders()`, which answers 403 or 404,
  and again in `onWSOpen()`, which closes the socket at once (1008) if they
  fail. **`onHeaders()` alone does not refuse an upgrade.** When it returns
  403 or 404 for one, httpuv writes that response and then, on the same
  connection, `HTTP/1.1 101 Switching Protocols`: the socket is live, and
  httpuv calls `onWSOpen()` with the refused request. In the review's
  check, a client with a wrong token and a foreign `Origin` got 300
  messages of 1 MiB each into R's `onMessage` handler when the check was
  only in `onHeaders()`, and none when `onWSOpen()` checked again and
  closed (Evidence). So the check is **the first thing `onWSOpen()`
  does**: before it registers `onMessage` or `onClose`, counts the socket
  toward the cap of 8, gives it a connection number or sends `hello`. A
  refused socket leaves no trace in the server's state. A browser shows
  the 403 as a failed connection (1006). `call()` is not called for an
  upgrade. A report of this to httpuv upstream (refusing in `onHeaders()`
  should not upgrade) is a possible follow-up; it is a step outside the
  org, so it waits for Michael's OK.
  The `Host` and `Origin` refusal warnings are given from `onHeaders()`,
  since httpuv may skip `onWSOpen()` for a client that has already hung
  up; `onWSOpen()` closes a refused socket (1008) without a warning. A
  client that hangs up during a refused upgrade can make httpuv print
  "Warning in rm(list = wsconn_address(handle), envir = private$wsconns)
  : object '...' not found". It comes from httpuv's own bookkeeping, is
  known and harmless, and leaves no state in R. (Amended 2026-10-01, from
  aobcore#43.)
- **Text frames only from the page.** A binary frame closes the socket
  (1003). Binary frames are kept for R to page blobs (0006 item 5).
- **Size cap.** A text message over `getOption("aobcore.ws_max_message", 2^20)`
  bytes (1 MiB) closes the socket (1009), with a warning in R. httpuv has no cap
  of its own and hands R the whole message (the spike sent 2 MiB), so the cap
  limits what R parses, not what httpuv buffers: R parses only messages from
  peers that passed the checks, and httpuv buffers what any raw client sends
  until R closes it. 1 MiB holds about 120000 row indices; the page knows the
  cap (from `hello`) and does not send a larger selection: it keeps it in the
  page and shows a note that it is too large to send.
- **Malformed messages.** Text that is not valid UTF-8, text that is not
  JSON, or JSON that is not an object with a string `type`, closes the
  socket (1007). Every handler (`onHeaders()`, `onWSOpen()`, `onMessage`,
  `onClose`) is wrapped in `tryCatch()`, so an error in R closes the
  socket with the right code and a warning, never through httpuv's own
  `try()`, which prints to the console and closes with 1011. A known type with
  bad fields (an unknown layer, a row out of range, a row that is not a
  whole number) is dropped with a warning, once per connection and type,
  and the connection stays. An unknown type is ignored, so a newer page can
  talk to an older R.
- **Several pages.** Each socket is a connection with a number. At most 8
  are open per server; a ninth is closed (1013, try again later) with a
  warning naming the cap. Two tabs on one view are two connections.
  The cap's warning is given once per server, since a page retries.
  (Amended 2026-10-01, from aobcore#43.)
- **Warnings after a socket is accepted are capped.** The warnings for
  closes 1003, 1007, 1008 (a message before `hello`), 4000, 1009 and 1011,
  for a scene spec mismatch in `hello`, and for messages dropped for bad
  fields (still once per connection and type) share one count: the first
  5 per server are given, then one saying further ones are not shown, so
  a page that misbehaves in a loop cannot flood the console.
  (Amended 2026-10-01, from aobcore#43.)
- **Diagnosing refusals.** An `Origin` refusal warns in R as a `Host`
  refusal does: the value escaped (printable ASCII only, other bytes as
  `\xNN`) and cut to 80 bytes, naming `aobcore.serve_hosts` and saying to
  allow it only if it is the IDE proxy's. Warnings are given for the
  first 5 distinct `Origin` values per server, then once "further
  refusals not shown"; a missing `Origin` counts as one of those 5
  values. (Amended 2026-10-01, from aobcore#43.) Wrong-path refusals
  (404) and cross-site refusals that a browser makes on its own are
  silent in R; the page sees only a failed connection. A `serve_hosts`
  value with an explicit default port (`host:443`) will not match an
  `Origin`, since browsers leave a default port out of `Origin`; the help
  says to list the host without it too.
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
- **Triggers, as built.** In selection mode (some layer selectable) every
  click sends a `select`, with `at`: a click on a feature sends `click`
  (or `toggle` with Shift or Cmd); a click on nothing sends `click` with
  no items; a Shift or Cmd click on nothing sends `toggle` with the
  selection unchanged, so a slipped Shift click does not lose a multiple
  selection. Escape sends `clear`, and only when something was selected.
  (`at` is left out when the point cannot be unprojected, as off the
  globe.) (Amended 2026-10-01, from aobcore#44.)
- `view` is sent when the camera settles: 250 ms after its last change,
  and at most four times a second. Orthographic views send `extent`
  (`[xmin, xmax, ymin, ymax]`, view CRS units), `zoom` and
  `units_per_pixel` (the renderer's `currentView()`); a globe sends
  `center` (`[lon, lat]`) and `zoom` instead. This is decision 0003's
  "one round trip per settled view change"; using it to plan tiles is a
  later milestone. The page also sends a `view` after each `hello` from R,
  first or on reconnecting, within the same limit of one per 250 ms, so R
  has the camera without waiting for the viewer to move it. (Amended
  2026-10-01, from aobcore#44.)
- `seq` counts up per connection, so R can tell order and drop a stale
  message.

R to page:

```json
{"type": "hello", "protocol": 1, "connection": 2, "scene": 3,
 "spec": "0.5", "select": ["nc", "coast"], "max_message": 1048576}

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
- `spec` is the scene spec version of the scene being served, as 0006
  item 5 says `hello` carries ("the scene spec version both sides
  speak"). The page's `hello` lists the versions its renderer draws
  (`specs`); if the scene's is not among them, R logs a warning naming
  both, and the page shows its usual "this renderer draws ..." error. It
  matters little today (the page and renderer come from the same server),
  but it will when R pushes a `scene` over the socket.
- `select` lists the layers the page may let the viewer select (item 6).
- Reserved for later, from 0006 item 5: R to page `scene`, `layers`,
  `view`, `select` (a selection set from R) and binary blob frames, each a
  new type in protocol 1.

Close codes: 1000 normal; 1001 the server is stopping; 1003 a binary frame; 1007
not UTF-8 or not JSON; 1008 refused or out of order; 1009 too large; 1013 too
many connections; 4000 protocol.

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
  per layer id its `idx`), never in the scene. The view also keeps the
  scene serial its server gave its scene (item 2).
- **Stale views.** `v2 <- view_add(v, ...)` replaces the scene on `v`'s
  server, so `v` and `v2` share one server but not one row map. Selections
  are recorded with the serial of the scene they were made on, and the
  selection functions compare it with the view's: on `v`, after the scene
  was replaced, they are an error ("This view was replaced by
  `view_add()`; use the view it returned."), never a mapping through the
  wrong rows. Several layer rows can map
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
  As built it also carries `trigger` and `scene` (the serial of the scene
  it was made on). (Amended 2026-10-01, from aobcore#43.)
- `srv$view_state()`: the latest `view` message as a list, or `NULL`.
- `srv$wait(type = "select", timeout = Inf)`: services the loop
  (`httpuv::service(100)`) until a message of that type newer than the
  call arrives, and returns what `selection()` or `view_state()` then
  returns; `NULL` (with a message) at the timeout. An interrupt (Esc,
  Ctrl-C) ends it as any R call. `type` is `"select"` or `"view"`; while
  it waits it calls `httpuv::service()` with a timeout of 1 to 100 ms,
  never 0. (Amended 2026-10-01, from aobcore#43.)
- `srv$wait()`, and the `service(0)` the selection functions run first,
  must not be called from inside an `srv$on()` callback, which is itself
  run by the loop: a flag set while callbacks run makes that an error
  rather than a nested run of the loop.
- **"Service first", as built.** The selection functions do not call
  `httpuv::service()` first: in httpuv 1.6.17 `service(0)` runs the loop
  until something pauses it, which from there never returns, and
  `service(NA)` runs only one callback, so messages queued while R was
  busy would be taken in one per call. They run `later::run_now(0, all =
  TRUE)` (the `later` loop httpuv uses) until it reports nothing ran, at
  most 1000 times, so every message already queued is counted. Inside an
  `srv$on()` callback they skip that and read the state as it is.
  (Amended 2026-10-01, from aobcore#43.)
- `srv$on(type, f)`: calls `f(message)` for each message of that type and
  returns a function that removes it; an error in `f` becomes a warning.
  `type` may also be `"hello"`. (Amended 2026-10-01, from aobcore#43.)
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
  message (a click, a toggle or a clear) and returns `selected(v)`. In a
  non-interactive session with no page connected it is an error unless a
  finite `timeout` is given, so a script cannot hang on a page nobody
  will open.
- Each of these first services the loop once (`httpuv::service(0)`), so a
  selection made just before the call is counted. (Amended 2026-10-01,
  from aobview#23: they drain the loop as `srv$selection()` does, above,
  not with `service(0)`. `wait_for_selection()` is the exception: it does
  not drain before it starts waiting, so a selection made while R was busy
  and still queued counts as the next one and ends the wait.)

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

Recommended: **b**. When `serve_scene(scene, server = srv)` replaces the scene,
R gives it a new serial and sends `reload` to every connected page; the page
reloads itself, and keeps the camera (it saves its view state in
`sessionStorage` under the token, and the reloaded page restores it when the
serial is newer and the view CRS is the same). `print.aob_view()` on a served
view then opens the URL only when no page is connected, instead of each time it
is printed, so `v <- view_add(v, ...); v` updates the open tab rather than
adding one; that refines 0006 item 4 ("printing it opens `v$server$url`")
without changing what the user sees first. The selection is cleared when the
scene is replaced, in R and, by the reload, in the page, since the page cannot
show a selection R keeps until R can push one.

As built (amended 2026-10-01, from aobcore#43 and aobcore#44):

- Only the selection is cleared when the scene is replaced; R keeps the
  last `view_state()`, since the reloaded page keeps its camera.
- The page keeps its camera in `sessionStorage` under a 64-bit hash of
  the page's directory path (which holds the token), not under the token
  itself. The saved camera is read once and removed, and is restored only
  when it was saved under an older scene serial, with the same view type
  and view CRS.
- A page follows `reload` only when its scene serial is greater than the
  page's own, so a `reload` at the page's own serial cannot reload it for
  ever.

### 6. Selection in the page

- A page connects only when its element has `data-aob-socket` (a URL
  relative to the page, `"ws"`), which only `serve_scene()`'s linked pages
  carry. It opens the socket after the scene is drawn, so a slow socket
  never delays the map.
- The layers in R's `hello` `select` list become pickable, popup or not;
  other layers are as today. `serve_scene(select = )` sets the list: `NULL`
  (the default) is every vector layer, a character vector names layer ids,
  `character(0)` none. aobview passes the default.
- A click on a feature selects it and only it; a click with Shift (or Cmd)
  adds or removes it (not Ctrl, which is a context-menu click on
  macOS); a click on nothing, or Escape, clears. A
  0.5 popup still opens as today for the clicked feature. Selected features
  are drawn highlighted, light and dark; how is the renderer's choice.
  Keyboard selection follows the popup's, when that exists.
  (Amended 2026-10-01, from aobcore#44: a Shift or Cmd click edits the
  selection and hides the popup rather than opening one; a Shift or Cmd
  click on nothing keeps the selection instead of clearing it. A click on
  a feature of a layer that is not selectable counts as a click on
  nothing: it sends `click` with no items and clears the selection.)
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
  (Amended 2026-10-01, from aobview#23: it says so in a message, not a
  warning, once per server, since a warning would show only after the
  wait has ended.)
- **jsonlite missing.** Serving still works, the page carries no
  `data-aob-socket`, and `serve_scene()` says once per session that
  selections need jsonlite. The aobview functions error naming it.
- **A page that loses its socket** (the server stopped, the R session
  ended) shows a status note, "Not connected to R: selections stay in
  this page", keeps its selection, and retries with backoff (1 s doubling
  to 30 s) while it is open. On reconnecting it sends `hello` and then its
  whole selection. A page refused for a reason that will not change (1003,
  1007, 1008, 4000) does not retry, and its note says why.
  (Amended 2026-10-01, from aobcore#44.) Opening a socket alone does not
  reset the backoff, since R can accept a socket and close it at once
  (1013, 1011): the delay goes back to 1 s only after R's `hello` and 5 s
  with the socket still open. 1003, 1007, 1008 and 4000 are the final
  codes; every other close is retried. A page closed with 1013 retries,
  and its note says "too many pages are connected to R".
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
  once. `call()` was never called for an upgrade.

**Review check** (in the same scratchpad, `rev17/`). On the wire, a
refusal from `onHeaders()` is the 403 or 404 response followed on the same
connection by `HTTP/1.1 101 Switching Protocols`, and the socket is live.
A raw client with a wrong token and a foreign `Origin` sent 300 messages
of 1 MiB each: with the check only in `onHeaders()`, all 300 (314572800
bytes) reached R's `onMessage` handler; with the check repeated at the top
of `onWSOpen()`, which closed before registering anything, none did. This
is why item 1 checks twice, and first. The same check showed that
aobcore main's `serve_scene()`, which has only `call`, prints "Error in
try(private$app$onWSOpen(ws)) : attempt to apply non-function" for an
upgrade on any path (What exists today), and that `httpuv::service()` can
be called from inside a callback the loop is running, which is why item
4 guards against it.

Not checked: an IDE proxy (RStudio Server, Posit Workbench, code-server)
forwarding a websocket, and the `Origin` it sends; Positron, whose viewer
proxies `localhost` through another port, so the page's `Origin` differs
from the server's; Firefox and Safari. Those
belong in the implementation issues.

## Testing

- **R, no network.** Most tests drive the app's `onHeaders()` and `onWSOpen()`
  directly with a fake `ws` (an environment with `request`, `onMessage()`,
  `onClose()`, `send()` and `close()` that record calls). They cover: each
  refusal (path, `Host`, `Origin`, missing `Origin`, a listed
  `aobcore.serve_hosts` value over `http` and `https`) in both places; close
  codes for binary, non-JSON, too large and out of order; dropped messages with
  their once-only warnings; the connection cap; invalid UTF-8 and a parse
  error closing with 1007 (never 1011); the `Origin` refusal warnings, escaped,
  cut and capped at 5 values; a refused socket leaving no connection, number or
  handler behind; the scene serial and `reload`; the selection state and
  `srv$selection()`, `srv$view_state()`, `srv$wait()` (with a message queued by
  `later` and with a timeout), `srv$on()`, and the error for `srv$wait()` or
  `service()` called inside an `srv$on()` callback. No websocket client package
  is needed; all skip without httpuv or jsonlite.
- **R, over a socket.** The status lines of real upgrade requests (101,
  403, 404) from a base R `socketConnection()` against a server in a child
  R process (processx, already installed here; added to Suggests only if
  the issue needs it). The `websocket` package, if a later issue wants a
  full client in R tests, goes in Suggests with `skip_if_not_installed()`.
  (Amended 2026-10-01, from aobcore#43 and aobcore#46: the child R
  processes are started with base R's `system2()` and `Rscript`, not
  processx, which is not in Suggests.)
- **R, at exit** (aobcore#46). A child R process serves a scene, opens a
  socket to it and ends: ending normally with a page connected exits with
  status 0, a script that stops with an error exits with its error
  (status 1, not a signal's), and unloading aobcore closes the socket with
  1001. A test without a child checks that the exit finalizer forgets the
  sockets without closing them. (Amended 2026-10-01.)
- **aobview.** The mapping from layer rows to source rows, with empty
  geometries, an untransformable geometry, mixed geometry split into three
  layers and a geometry collection; `selection()` and `selected()` for sf,
  sfc and SpatVector sources and for two sources; the errors on embedded
  and stopped views, on a view replaced by `view_add()`, and for
  `wait_for_selection()` with no page, no finite timeout and no
  interactive session.
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
- **Decision 0006.** Item 5's sketch holds: the route, the `Origin` check, JSON
  with a `type`, 0-based rows, `hello`. This record settles its open points:
  Arrow row ids, pulled from R, one server per scene. Two refinements: printing
  a served view opens the URL only when no page is connected, and connected
  pages follow a changed scene through `reload`, rather than a new tab opening
  each time (item 5); and the `Origin` check allows, besides the page's own
  origin, `http://H` and `https://H` for each `aobcore.serve_hosts` value `H`
  (item 1), since an IDE proxy serves the page from its own origin. R's `hello`
  carries the scene's `spec` version, as 0006 asked.
- **Rules out** for now: a feature id column, selections as changes rather
  than whole, binary frames from the page, connections from any origin
  but the page's own (or a listed proxy's), and selection in embedded
  pages.

### Proposed issues (not filed)

1. **aobcore: websocket route and its checks.** Builds on the aobcore fix
   made ahead of this record (every upgrade refused). `/<token>/ws` with
   path, `Host` and `Origin` checks in `onHeaders()` and again, first, in
   `onWSOpen()`, the `Origin` warnings,
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

## Defaults chosen (Michael may revisit)

Each is a default this record sets, with the alternative it passed over:

- **Every vector layer is selectable on a served view**
  (`serve_scene(select = NULL)`, and aobview passes the default). A click
  on a served view then highlights a feature even when the layer has no
  popup. Alternative: selectable only when asked
  (`view(x, select = TRUE)`), which leaves served views behaving as
  today.
- **`wait_for_selection()` on an embedded view is an error** that says to
  use `transport = "serve"`. Alternative: serve the view there and then
  (start a server and open a new tab, with a message).
- **`view_add()` clears the selection**, until R can push a selection to
  the page. Alternative: keep the rows of layers whose data did not
  change, which needs R to page `select` to keep the page in step.

## Amendments

- 2026-10-01, from aobcore#43 (websocket route, protocol 1 and the server
  API), aobcore#44 (renderer) and aobcore#46 (exit), and aobview#23 (row
  maps and the selection functions):
  - Item 1: the checks run path, `Host`, `Origin`, so a wrong path is a
    silent 404; a missing `Origin` counts among the 5 warned values;
    refusal warnings come from `onHeaders()`, and `onWSOpen()` closes a
    refused socket with 1008 silently; the warnings after a socket is
    accepted (closes 1003, 1007, 1008, 4000, 1009, 1011, a spec mismatch,
    dropped messages) share a cap of 5 per server plus one final one; the
    1013 cap warns once per server; httpuv's occasional `rm(...
    wsconns)` warning on an early hang-up is known and harmless.
  - Item 2: in selection mode every click sends a `select` with `at`; a
    click on nothing sends `click` with no items; a Shift or Cmd click on
    nothing sends `toggle` with the selection unchanged; Escape sends
    `clear`, only when something was selected; the page sends a `view`
    after each `hello` from R, at most one per 250 ms.
  - Item 4: "service first" is `later::run_now(0, all = TRUE)` until
    nothing runs (at most 1000 times), since `httpuv::service(0)` never
    returns from there in httpuv 1.6.17 and `service(NA)` runs only one
    callback; `wait()` takes `"select"` or `"view"`; `selection()` also
    carries `trigger` and `scene` attributes; `wait_for_selection()` does
    not drain before waiting, so a selection made while R was busy counts
    as the next one; `srv$on()` also accepts `"hello"`.
  - Item 5: `view_state()` is kept when the scene is replaced (only the
    selection clears); the camera is kept in `sessionStorage` under a
    64-bit hash of the page's path, restored only from an older serial with
    the same view type and CRS; a `reload` is followed only for a serial
    greater than the page's.
  - Item 6: a Shift or Cmd click hides the popup instead of opening it,
    and on nothing keeps the selection; a click on a feature of a layer
    that is not selectable counts as a click on nothing (`click`, no
    items, clears).
  - Item 8: the backoff (1 s doubling to 30 s) resets only after R's
    `hello` and 5 s open; 1003, 1007, 1008 and 4000 are final; a 1013
    close shows "too many pages are connected to R"; `wait_for_selection()`
    with no page connected says it is waiting in a message, once per
    server, not a warning.
  - Testing: child R processes through `system2()`, not processx; the exit
    tests from aobcore#46.
