# 0006: A local server transport for large local data

- Date: 2026-10-01
- Status: proposed
- Issue: none; next milestone after the embed transport, raised by Michael in the project thread
- Decided by: agent

## Question

The design post lists four transports: "embedded in a standalone page,
served from a local httpuv server for large or streaming data, updated over a
websocket (with selections coming back to R as row ids), or handed over
in-process under webR". Only the first exists. How should aobcore serve a
scene from a local HTTP server, so that large local data (a local COG above
all) is read by the browser on demand instead of being copied into the page,
without growing the core's Imports or the scene spec?

## Answer

Proposed: a function `serve_scene(scene)` in aobcore starts an httpuv server
(httpuv in Suggests) on 127.0.0.1, on a random port, under a random token
path, and returns a handle with a `url` and a `stop()`. The server answers a
fixed set of routes: the page, the renderer bundle, the scene's Arrow blobs
and the local files the scene registered, the files with HTTP Range support.
The scene document is the same one the embed transport writes. Blob keys stay
blob keys, and a local COG's `url` is a relative URL under the server root,
so **no scene spec change is needed**. `view()` keeps embedding by default
and serves only when the local raster bytes it would embed pass a size
threshold, or when asked. The websocket path (selections and live updates)
is a separate, later decision.

## What exists today

- `write_scene_html()` (aobcore `R/html.R`) writes one page: the scene JSON
  in a `<script type="application/json">`, every blob as base64 in a
  `<script data-aob-blob>`, and the renderer inlined. It needs no server.
- `scene_add_tiled_raster()` (aobcore `R/cog.R`) embeds a local COG by
  default (`embed = TRUE` when the COG is not a URL). It reads the bytes of
  every planned tile at add time with `gdalraster::VSIFile` (`tile_blobs()`)
  and carries each as a blob keyed `"<source>@<byte_offset>+<byte_length>"`.
  The cog reference's `url` is then the file's base name, a page-relative URL,
  so a shared page does not reveal the local directory. Its documentation
  already says the base name "works when the COG is served beside it", and
  suggests serving over HTTP for a large local COG.
- The renderer (`js/src/tiles.js`) uses a tile's blob when the page has one
  and otherwise calls `rangeReader()`, which sends
  `Range: bytes=<offset>-<offset+length-1>`. A server that answers 200
  instead of 206 has its whole body fetched once and sliced, which is fine
  for a small file and very bad for a large one. A page opened from `file://`
  cannot range-request, which is why local COGs are embedded.
- Arrow data references (`js/src/index.js`, `loadBytes()`) use the delivered
  blob for `blob` and `fetch(ref.url)` for `url`.
- aobview's terra method writes a temporary COG for anything that is not
  already a usable COG, and deletes it once the page is written.

Scene spec 0.5 already covers a served scene:

- `arrowRef.blob` is "Key of a blob delivered alongside the scene by the
  transport (embedded, served or handed over in-process)". How a blob arrives
  is the transport's business.
- `arrowRef.url` and `cogRef.url` are `uri-reference`s, "absolute or
  scene-relative". `cogRef` says "The server must answer HTTP range
  requests".

## Decisions

### 1. Server

Options:

- **a. httpuv in Suggests, used by aobcore** (`serve_scene()`), checked with
  `requireNamespace("httpuv")` and an error naming the package when it is
  missing.
- b. httpuv in Imports. Rejected: it breaks the lean-Imports rule for a
  transport many users never need.
- c. A separate package (`aobserve`) for transports. Rejected for now: one
  function and about 300 lines do not justify a repo, and the page builder,
  blob checks and renderer bundle it needs are aobcore internals. Revisit if
  the websocket and Shiny transports make it large.
- d. R's internal help server (`tools::startDynamicHelp`). Rejected: not a
  public API.

Recommended: **a**. One function, with names open to change:

```r
srv <- serve_scene(scene, port = NULL, open = interactive(), title = NULL,
                   theme = c("auto", "light", "dark"))
srv$url    # "http://127.0.0.1:43817/3f9c...e1/"
srv$stop()
```

Routes, all under `/<token>/`:

| Route | Body | Type |
| --- | --- | --- |
| `` (the token root) and `index.html` | the page: same builder as `write_scene_html()`, scene JSON inline, renderer by `src`, no blob scripts | `text/html` |
| `aob-renderer.min.js` | the bundled renderer, read once | `text/javascript` |
| `blob/<key>` | one Arrow IPC blob from the scene | `application/vnd.apache.arrow.stream` |
| `files/<data id>/<base name>` | one registered local file, with Range | `image/tiff` for a COG, else `application/octet-stream` |

Anything else is 404. Only `GET` and `HEAD` are answered; other methods get
405. Responses carry `Cache-Control: no-cache` and no CORS headers.

The page builder is shared with `write_scene_html()` (one internal function
with an "inline" and a "linked" mode), so the two transports cannot drift.

**Renderer change, not a spec change.** The page loader (`fromPage()`)
learns one attribute, for example `data-aob-blob-base="blob/"` on the page
`<div>`. When a blob key has no `<script>` in the page and a base is set,
`render()` fetches `<base><encoded key>`. Embedded pages are unchanged. Tile
blobs are simply absent in a served page, so `tiles.js` takes its existing
range path.

Why keep `blob` keys rather than rewrite them to `url` references at serve
time: both are valid 0.5 scenes, but keeping them means the scene document
is byte-identical whatever the transport, and the websocket transport (item
5) can later push blobs under the same keys.

### 2. Local file serving

Options for how a scene refers to a served file:

- **a. A relative URL `files/<data id>/<base name>`**, set at serve time from
  a local path the scene records outside its JSON.
- b. An absolute `http://127.0.0.1:<port>/<token>/...` URL. Rejected: it ties
  the scene to one server run and leaks the token into anything that copies
  the scene.
- c. The base name alone, as today. Rejected: two COGs with the same base
  name in different directories would collide.
- d. A new spec field (say `cogRef.local`) for "a file the transport
  provides". Rejected: `url` already says what the renderer needs, and a
  local path in the scene would reveal the user's directories.

Recommended: **a**. Concretely:

- `scene_add_tiled_raster()` records each local COG's path in an attribute
  of the scene (`attr(scene, "files")`, data id to path), as blobs are
  carried today. The JSON never sees the path.
- Reading tile bytes for embedding moves from add time to write time:
  `write_scene_html()` reads the planned ranges from the recorded file, and
  `serve_scene()` does not read them at all. So one scene can go to either
  transport, and choosing to serve costs no copy. `embed` on
  `scene_add_tiled_raster()` keeps its meaning for a page written to disk;
  `serve_scene()` ignores it (with a message when it was `TRUE` explicitly).
- `serve_scene()` sets each registered file's `url` to
  `files/<data id>/<URL-encoded base name>` in the copy it serves, unless the
  caller gave an explicit `url` (which is then left alone, so a remote COG
  stays remote). Relative URLs resolve against the page, which sits at the
  token root, so they inherit the token without the scene knowing it.
- The file route answers a single range (`bytes=a-b`, `bytes=a-`,
  `bytes=-n`) with 206, `Content-Range` and `Accept-Ranges: bytes`; a range
  past the end with 416; no `Range` header with 200 and the whole file; and
  `HEAD` with the length and no body. A multi-range request gets 416 rather
  than the whole file, since the renderer never sends one and a silent 200
  of a large file is the costly case. Each read is capped (64 MiB by default)
  so one request cannot make R allocate the whole file.
- Bytes are read with base R (`file()`, `seek()`, `readBin()`) in the R
  request handler. gdalraster is not needed to serve, so a plain local file
  works without it.

Not chosen for v1: httpuv's `staticPaths`, which serve from httpuv's
background thread and so keep working while R is busy. They serve
directories, not single files, so they would need a per-scene directory of
links to the registered files (fragile on Windows), and whether they honour
Range has not been checked. This is the first thing to revisit if a busy R
session stalls the page (see Consequences).

**Spec change: none.** `cogRef.url` and `arrowRef.url` are already
scene-relative `uri-reference`s, `cogRef` already requires a server that
answers range requests, and `arrowRef.blob` already allows a served blob.
Served scenes keep the version `scene_spec_version()` picks. If a later need
does arise (for example a transport hint in the scene), it is a scenespec
minor version at the lowest version needed.

### 3. Security

A local server is reachable by every process on the machine and, through the
browser, by any web page the user has open. Recommended, all together:

- **Loopback only.** Bind `127.0.0.1`, never `0.0.0.0`. No argument to change
  the host in this milestone (remote use is out of scope).
- **Random port** from `httpuv::randomPort()` unless `port` is given.
- **Random token in the path**, 128 bits as 32 hex characters: every route is
  under `/<token>/`. A path token rather than a query token, because
  relative URLs (the COG and blob routes) keep the path directory and drop
  the query. A wrong or missing token answers 404, the same as an unknown
  route. The token comes from `/dev/urandom` where it exists, with a
  fallback that does not use R's RNG either, so the server never changes
  `.Random.seed` and a `set.seed()` cannot make the token predictable.
- **Host check.** A request whose `Host` is not `127.0.0.1:<port>` or
  `localhost:<port>` gets 403. This blocks DNS rebinding, where a remote page
  points its own name at 127.0.0.1.
- **No CORS headers**, so other origins cannot read responses.
- **Registered files only.** The file route looks up `<data id>` in the
  scene's registered files and requires `<base name>` to equal that file's
  base name exactly; the path on disk comes from the registry, never from
  the URL. So `..`, encoded `%2e%2e`, `%2f`, absolute paths, symlink tricks
  and other files in the same directory have nothing to resolve. There is no
  directory listing anywhere.
- Paths are normalized with `normalizePath(mustWork = TRUE)` when the scene
  is served, and a file that has gone missing answers 404 with a warning in
  R.

The token is a guard against other local users and other web pages, not
authentication: anyone who sees the URL (shell history, a screen share) can
read the scene while it is served.

### 4. Lifecycle

Options for several scenes at once:

- **a. One server per served scene**, each with its own port and token.
- b. One server per R session, with each scene mounted under its own token.

Recommended: **a** for this milestone. `stop()` is then just
`httpuv::stopServer()` plus clean-up, nothing is shared between scenes, and
starting a server is cheap. b saves ports and is worth it once there is a
websocket per session; that decision can revisit it.

The handle, of class `"aob_server"`:

- `url`, `port`, `token`, and `stop()`; `print()` shows the URL, the number
  of blobs and files, and whether it is running.
- `stop()` is idempotent. It also deletes any temporary files the server was
  asked to own (aobview's temporary COGs, below).
- aobcore keeps a registry of running servers. `scene_servers()` lists them
  and `stop_scene_servers()` stops them all.
- All servers stop when the session ends (a finalizer on the registry with
  `onexit = TRUE`) and when aobcore is unloaded. Losing the handle does not
  stop the server; the registry keeps it, so a page in a browser does not go
  blank at a garbage collection.
- httpuv serves through the `later` event loop, so requests are answered
  when R is idle at the prompt. In `Rscript` the script ends and the server
  with it; `serve_scene()` warns when the session is not interactive.

How aobview's `view()` chooses (options):

- a. Always embed (today). Large local rasters make very large pages.
- b. Always serve. Loses the page that opens from disk, offline, a week
  later, which is the reproducible default the project started with.
- **c. Embed by default; serve when the local bytes to embed pass a
  threshold, or when asked.**

Recommended: **c**:

- A `transport` argument to `view()`, `"auto"` (default), `"embed"` or
  `"serve"`, with its default from `getOption("aobview.transport", "auto")`.
- `"auto"` sums the planned tiles' `byte_length` for every local COG (known
  from the plan before any byte is read). At or under
  `getOption("aobview.embed_max", 64 * 2^20)` bytes it embeds. Over it, in an
  interactive session with httpuv installed, it serves and says so in a
  message. Over it without httpuv, it embeds and warns, naming httpuv and the
  size. Over it in a non-interactive session it embeds and warns. Vectors
  alone never trigger serving in this milestone (their blobs are already in
  memory; the size question for them is a later one).
- A served view returns the same `"aob_view"` object with a `server` element
  and no `file`; printing it opens `server$url` in the viewer or browser.
  IDE viewers accept `http://127.0.0.1` URLs (RStudio's viewer also proxies
  them on RStudio Server), so the `in_tmp` rule in `open_page()` does not
  apply.
- A temporary COG that aobview wrote is handed to the server to own and is
  deleted on `stop()` or session end, not after the page is written.
- `max_tiles` and the plan stay as they are for a served view. Serving
  removes the cost of tile bytes, not of the plan (tile records and meshes
  still travel in the page), so the "levels left out" warning still fires
  where it does today. Whether a served view may plan more levels is left to
  the follow-up, and the warnings stay as noisy as they are (Michael,
  2026-10-01).

### 5. Websocket path, later

Not part of this milestone. A separate decision record (0007) and milestone
should cover it. At a high level, so this one leaves room for it:

- The same httpuv server takes a websocket at `/<token>/ws`, with the same
  Host check plus an `Origin` check (the page's own origin only).
- Messages are JSON text frames with a `type`, and binary frames for blobs
  (a short header naming the blob key, then the Arrow IPC bytes, so blob
  keys mean the same thing on every transport).
- R to page: `scene` (replace), `layers` (add, remove or restyle by id),
  `view` (move the camera), and blobs.
- Page to R: `select` with a layer id and the selected rows as 0-based Arrow
  row indices in that layer's data (R adds 1), and `view` with the settled
  extent and zoom, which lets R re-plan tiles for the view (decision 0003's
  "one round trip per settled view change").
- A `hello` exchange carries the scene spec version both sides speak.

What 0007 must settle: row ids versus a feature id column, how a selection
reaches the user in R (a callback, a reactive value, or polling a handle), and
whether the server moves to one per session (item 4, option b).

### 6. Out of scope

- webR and in-process hand-over.
- Shiny and Quarto. Their own server or document model owns the transport;
  that is a separate milestone, which may reuse the page builder and the
  blob-base attribute from this one.
- Remote servers: binding other interfaces, TLS, real authentication, and
  serving to another machine. Users on a remote R host reach the page through
  their IDE's proxy, or they embed.
- Changing the scene spec.

## Evidence

This is a design record; nothing was built for it. It is based on reading
aobcore at `3502f60` (`R/html.R`, `R/cog.R`, `js/src/tiles.js`,
`js/src/index.js`), aobview at `886d33e` (`R/view.R`, `R/view-terra.R`), and
`schema/scene-0.5.schema.json` in scenespec at `9f8df26`. Not checked: whether
httpuv's `staticPaths` honour Range, and how each IDE viewer treats a
`127.0.0.1` URL. Both belong in the first implementation issue.

## Consequences

- **Charter and design post.** The second transport the post names, with no
  change to goals or non-goals.
- **Dependencies.** aobcore Imports stay nanoarrow, geoarrow, wk and
  htmltools. httpuv joins Suggests (it brings `later` and Rcpp with it when
  installed). aobview's Imports do not change; httpuv is reached through
  aobcore.
- **Scene spec.** No change. Served scenes validate as they do embedded.
- **Renderer.** One page-loader attribute for fetching blobs by URL. The tile
  path is unchanged. Rendering changes need the headless screenshots of the
  conformance scenes, light and dark, so the served page is screenshot too,
  with the EPSG:3031 COG fixture first (polar first).
- **Behaviour change in aobcore.** Tile bytes for embedding are read at write
  time instead of add time. A scene object no longer carries tile blobs, so
  `scene_blobs()` returns fewer blobs for a COG scene; anything that relied
  on that must read them from the page or call the internal reader.
- **Busy R stalls the page.** Requests are answered only when R is idle. If
  that bites (for example a long computation while a view is open), the next
  step is to serve registered files from httpuv's background thread
  (`staticPaths` with Range, if it has it).
- **Rules out** serving arbitrary paths, a directory listing, binding beyond
  loopback, and absolute server URLs inside the scene document.

### Proposed issues (not filed)

1. **aobcore: page builder with linked and inline modes.** Split
   `write_scene_html()`'s page into one internal builder that inlines the
   renderer and blobs (embed) or links them (serve).
   Done when: `write_scene_html()` output is byte-identical to today for the
   conformance scenes; the linked mode emits `<script src="aob-renderer.min.js">`,
   no blob scripts and a `data-aob-blob-base` attribute; tests cover both.
2. **aobcore: renderer fetches blobs by URL when the page names a blob
   base.** Done when: `fromPage()` and `render()` fetch a missing blob from
   `<base><encoded key>`; a missing blob with no base still errors as
   today; embedded pages are unchanged; JS tests cover both paths.
3. **aobcore: record local files on the scene and read tile bytes at write
   time.** Done when: `scene_add_tiled_raster()` stores the COG path in
   `attr(scene, "files")` and no tile blobs; `write_scene_html()` reads and
   embeds the planned ranges; the page for the polar 3031 COG fixture is the
   same as before; the JSON contains no local path.
4. **aobcore: `serve_scene()` with httpuv in Suggests.** Routes as in
   decision 0006 item 1, loopback only, random port, 128-bit path token,
   Host check, 404 for anything unregistered, `GET`/`HEAD` only.
   Done when: R CMD check passes with and without httpuv installed
   (`skip_if_not_installed`); tests fetch every route over 127.0.0.1 with
   base R or curl; wrong token, unknown route, `..`, `%2e%2e`, `%2f`, an
   absolute path and a sibling file in the COG's directory all answer 404;
   a foreign `Host` answers 403; `.Random.seed` is unchanged after a call.
5. **aobcore: HTTP Range on registered files.** Done when: single ranges in
   all three forms answer 206 with correct `Content-Range` and bytes; a range
   past the end answers 416; multi-range answers 416; no `Range` answers 200;
   `HEAD` gives the length; the per-request cap holds; the renderer's
   `rangeReader()` draws the polar 3031 COG fixture from the served page with
   no whole-file fetch (checked by counting response sizes), screenshot light
   and dark.
6. **aobcore: server lifecycle.** Done when: the handle prints its URL and
   state; `stop()` is idempotent and frees the port; `scene_servers()` and
   `stop_scene_servers()` work with three scenes served at once; servers stop
   on session exit and on unloading aobcore (tested in a child R process);
   a non-interactive call warns; owned temporary files are deleted on stop.
7. **aobview: choose serve or embed in `view()`.** Done when: `transport`
   and the `aobview.transport` and `aobview.embed_max` options work as in
   decision 0006 item 4; a local COG over the threshold is served with a
   message in an interactive session and embedded with a warning without
   httpuv or when not interactive; a small scene still writes the same page
   as today; a temporary COG lives until the server stops; printing a
   served view opens its URL.
8. **design: decision 0007, websocket messages.** Done when: a record
   settles the message types, row ids versus feature ids, how selections
   reach the R user, and one server per scene or per session, sketched in
   decision 0006 item 5.
