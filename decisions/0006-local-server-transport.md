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
so **no scene spec change is needed**. Embedding keeps reading tile bytes
when the layer is added, as today; a layer meant for serving registers its
file instead. `view()` keeps embedding by default and decides to serve
before it adds a raster layer, when the planned local bytes pass a size
threshold or when asked. The websocket path (selections and live updates)
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
  suggests serving over HTTP for a large local COG. A `/vsimem/` COG counts
  as local (`cog_info()`), so it can be embedded.
- The renderer (`js/src/tiles.js`) uses a tile's blob when the page has one
  and otherwise calls `rangeReader()`, which sends
  `Range: bytes=<offset>-<offset+length-1>`. A server that answers 200
  instead of 206 has its whole body fetched once and sliced, which is fine
  for a small file and very bad for a large one. A tile whose bytes are not
  exactly `byte_length` long is an error (`tiles.js`, after the fetch). A
  page opened from `file://` cannot range-request, which is why local COGs
  are embedded.
- Arrow data references (`js/src/index.js`, `loadBytes()`) use the delivered
  blob for `blob` and `fetch(ref.url)` for `url`.
- aobview's terra method writes a temporary COG for anything that is not
  already a usable COG, and deletes it as soon as the layer is added
  (`R/view-terra.R`, `on.exit(unlink(temp$dsn))`), because the tile bytes
  are already in the scene. `finish_view()` writes the page after that, and
  `view_add()` rewrites the page later still, so both rely on the bytes
  having been read at add time.

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
  function and a few hundred lines do not justify a repo, and the page
  builder, blob checks and renderer bundle it needs are aobcore internals.
  Revisit if the websocket and Shiny transports make it large.
- d. R's internal help server (`tools::startDynamicHelp`). Rejected: not a
  public API.

Recommended: **a**. One function, with names open to change:

```r
srv <- serve_scene(scene, blobs = attr(scene, "blobs"),
                   files = attr(scene, "files"), port = NULL,
                   open = interactive(), title = NULL,
                   theme = c("auto", "light", "dark"))
srv$url    # "http://127.0.0.1:43817/3f9c...e1/"
srv$stop()
```

Routes, all under `/<token>/`:

| Route | Body | Type |
| --- | --- | --- |
| `` (the token root) and `index.html` | the page: same builder as `write_scene_html()`, scene JSON inline, renderer by `src`, no blob scripts | `text/html` |
| `aob-renderer.min.js` | the bundled renderer, read once | `text/javascript` |
| `blob/<encoded key>` | one Arrow IPC blob from the scene | by the format of the data reference that names it: `application/vnd.apache.arrow.stream` for `arrow-ipc-stream`, `application/vnd.apache.arrow.file` for `arrow-ipc-file` |
| `files/<data id>/<base name>` | one registered local file, with Range | `image/tiff` for a COG, else `application/octet-stream` |

`/<token>` without the trailing slash answers 301 to `/<token>/`, so the
relative routes resolve under the token. Anything else is 404. Only `GET`
and `HEAD` are answered; other methods get 405. Responses carry
`Cache-Control: no-cache` and no CORS headers.

**Blob keys in URLs.** Keys may contain `/`, `@`, `+` and other reserved
characters. The page builds each blob URL as `<base>` plus
`encodeURIComponent(key)`, so the key is one path segment. The server takes
the segment after `blob/` from the raw request path, decodes it once with
`utils::URLdecode()` (which leaves `+` as `+`), and looks the result up by
exact match in the scene's blob names. No file system is involved, and a
key that does not match is 404.

The page builder is shared with `write_scene_html()` (one internal function
with an "inline" and a "linked" mode), so the two transports cannot drift.

**Renderer change, not a spec change.** The page loader (`fromPage()`)
learns one attribute, for example `data-aob-blob-base="blob/"` on the page
`<div>`. When a blob key has no `<script>` in the page and a base is set,
`render()` fetches `<base><encoded key>`. Embedded pages are unchanged. A
served layer has no tile blobs, so `tiles.js` takes its existing range
path. A linked page also lists the keys the server delivers in one
`<script type="application/json" data-aob-blob-keys>` (a key list, not a
blob script), because a tile's blob key is implied by its byte range and
the renderer cannot otherwise tell an embedded layer's tiles (served as
blobs) from a served layer's (read by range). A tiled raster fetches a
tile from the blob base only when its key is listed, and reads the COG
by range otherwise; Arrow data references use the base for any blob the
page does not carry. (Amended 2026-10-01, from aobcore#36.)

Why keep `blob` keys rather than rewrite them to `url` references at serve
time: both are valid 0.5 scenes, but keeping them means the scene document
is byte-identical whatever the transport, and the websocket transport (item
5) can later push blobs under the same keys.

**Plain-list scenes.** A scene given as a plain list carries no attributes,
so `serve_scene()` takes `blobs` and `files` arguments, as
`write_scene_html()` takes `blobs`. A `cog` reference with a relative `url`
and no registered file and no tile blobs is an error that names the data id,
since the page could never fetch it.

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

Recommended: **a**.

Options for when an embedded layer's tile bytes are read:

- **a. At add time, as today.** The caller (aobview) decides embed or serve
  before adding the layer. A temporary COG can still be deleted right after
  an embedded layer is added.
- b. At write time, from a registered file. Rejected: aobview deletes its
  temporary COG once the layer is added, and `finish_view()` and
  `view_add()` write the page after that, so `view(in_memory_raster)` would
  break unless every temporary COG lived as long as the view.

Recommended: **a**. Concretely:

- `scene_add_tiled_raster(embed = TRUE)` is unchanged: it reads the planned
  ranges and carries tile blobs. Embedded pages, and the blob order in
  them, do not change.
- `scene_add_tiled_raster(embed = FALSE)` on a local COG records the file in
  an attribute of the scene (`attr(scene, "files")`, data id to a record of
  path, size and modification time, and whether `url` was given
  explicitly), as blobs are carried today. That registry is never written
  to the scene JSON. The layer's `url` is another matter: unless the
  caller gave one, it stays the file's `file://` URL, which holds the full
  local path, until `serve_scene()` replaces it in the copy it serves.
  `write_scene_html()` on such a scene writes the
  `file://` URL as today, with a warning that the page cannot read it from
  disk and needs `serve_scene()` or `embed = TRUE`.
- `serve_scene()` sets each registered file's `url` to
  `files/<data id>/<URL-encoded base name>` in the copy it serves, unless the
  caller gave an explicit `url` (which is then left alone, so a remote COG
  stays remote). Relative URLs resolve against the page, which sits at the
  token root, so they inherit the token without the scene knowing it.
  Embedded tile blobs in the same scene are served as blobs, so one scene
  may mix embedded and served layers.
- **Unchanged files only.** Size and modification time are recorded by
  `cog_info()` when it reads the file, and `scene_add_tiled_raster()`
  refuses a file that has changed or gone since, whether or not it embeds
  (the registered record keeps `cog_info()`'s values). `serve_scene()` errors if a registered file has changed or
  gone since, and the file route checks again on each request: a changed
  file answers 409 and a missing one 404, each with a warning in R. A tile
  plan holds byte offsets, so a rewritten file would draw garbage otherwise.
- **`/vsimem/` COGs are embed-only.** Base R cannot read them, and a served
  file must be a real path. `scene_add_tiled_raster(embed = FALSE)` on a
  `/vsimem/` COG with no `url` is an error that says to embed it or write
  it to disk. With an explicit `url` it stays allowed, as before: the plan
  is read from memory, the renderer goes to the caller's URL, and nothing
  is registered. (Amended 2026-10-01, from aobcore#36.)

The file route:

- No `Range` header: 200 with `body = list(file = path)`, which httpuv
  sends from the file itself (`bodyFile`), so R never reads the file into
  memory.
- A single range (`bytes=a-b`, `bytes=a-`, `bytes=-n`): 206 with
  `Content-Range`, `Accept-Ranges: bytes` and exactly those bytes, read with
  base R (`file()`, `seek()`, `readBin()`) in the request handler.
  gdalraster is not needed to serve.
- A range past the end: 416.
- A range longer than the cap (64 MiB by default, far above any tile): 416.
  A shorter 206 is not an option, since the renderer rejects a tile whose
  length does not match.
- A multi-range request: 416 rather than the whole file, since the renderer
  never sends one and a silent 200 of a large file is the costly case.
- `HEAD`: the headers of the matching `GET` with no body.

**httpuv `staticPaths` are not used.** They serve from httpuv's background
thread, so they would keep working while R is busy, but they do not handle
Range requests (httpuv's static file handler in `webapplication.cpp`
answers the whole file), and they serve directories rather than single
files. Every file request therefore goes through the R handler.

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
  the bind address in this milestone (remote use is out of scope).
- **Random token in the path**, 128 bits as 32 hex characters: every route is
  under `/<token>/`. A path token rather than a query token, because
  relative URLs (the COG and blob routes) keep the path directory and drop
  the query. A wrong or missing token answers 404, the same as an unknown
  route.
- **Token source.** 16 bytes from `/dev/urandom` (Linux, macOS). Where it
  does not exist (Windows), a fallback: the MD5 (`tools::md5sum()` of a
  temporary file) of the time to the microsecond, the process id,
  `proc.time()`, a `tempfile()` name and the address of a fresh environment.
  This is weaker: someone on the same machine who knows roughly when the
  server started and its process id can narrow the guesses a lot, so it
  guards against other web pages far better than against other local
  users. The fallback says so in a message each time it is used. A
  stronger Windows source (for example the openssl package) would be a
  new Suggests and is left to a later decision. Neither source uses R's
  RNG, so a server never changes `.Random.seed` and `set.seed()` cannot make
  the token predictable.
- **Random port without R's RNG.** `httpuv::randomPort()` calls `sample()`,
  which changes `.Random.seed` and repeats after `set.seed()`. Instead,
  candidate ports are drawn from the same random bytes as the token, in
  the range 20000 to 60000, and tried with `httpuv::startServer()` until one
  binds (up to 20 tries). `port` overrides this.
- **Host check.** A request whose `Host` is not `127.0.0.1:<port>` or
  `localhost:<port>` gets 403. This blocks DNS rebinding, where a remote page
  points its own name at 127.0.0.1. An IDE proxy (RStudio Server, Posit
  Workbench, code-server, jupyter-server-proxy) may forward requests with
  its own `Host`, which would fail every request, and Michael's sessions
  look like they run on a remote server. So the check is defence in depth,
  and `getOption("aobcore.serve_hosts")` lists further `Host` values to
  allow (for example the proxy's host name). A 403 warns in R with the
  `Host` it saw and names the option.
- **No CORS headers**, so other origins cannot read responses.
- **Registered files only.** The file route looks up `<data id>` in the
  scene's registered files and requires `<base name>` to equal that file's
  base name exactly; the path on disk comes from the registry, never from
  the URL. So `..`, encoded `%2e%2e`, `%2f`, absolute paths and other files
  in the same directory have nothing to resolve. There is no directory
  listing anywhere.
- Paths are normalized with `normalizePath(mustWork = TRUE)` at
  registration.

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
- The scene it serves lives in an environment, so it can be replaced on the
  running server with the same URL and token (`serve_scene(scene, server =
  srv)`). This is what `view_add()` uses on a served view.
- `stop()` is idempotent. It also deletes any temporary files the server was
  asked to own (aobview's temporary COGs, below).
- aobcore keeps a registry of running servers. `scene_servers()` lists them
  and `stop_scene_servers()` stops them all.
- All servers stop when the session ends (a finalizer on the registry with
  `onexit = TRUE`) and when aobcore is unloaded. Losing the handle does not
  stop the server; the registry keeps it, so a page in a browser does not go
  blank at a garbage collection.
- httpuv serves through the `later` event loop, so requests are answered
  only when R is idle at the prompt; a long computation stalls the page
  until it finishes. In `Rscript` the script ends and the server with it;
  `serve_scene()` warns when the session is not interactive.

How aobview's `view()` chooses (options):

- a. Always embed (today). Large local rasters make very large pages.
- b. Always serve. Loses the page that opens from disk, offline, a week
  later, which is the reproducible default the project started with.
- **c. Embed by default; serve when the local bytes to embed pass a
  threshold, or when asked, decided before each raster layer is added.**

Recommended: **c**:

- A `transport` argument to `view()` and `view_add()`, `"auto"` (default),
  `"embed"` or `"serve"`, with its default from
  `getOption("aobview.transport", "auto")`.
- The decision is made per local COG layer, after `cog_plan()` and before
  `scene_add_tiled_raster()`, from the plan's `byte_length` totals (known
  before any byte is read). `"auto"` keeps a running total of local tile
  bytes for the view. If adding this layer keeps the total at or under
  `getOption("aobview.embed_max", 32 * 2^20)` bytes, the layer is embedded
  (`embed = TRUE`) and its temporary COG, if any, is deleted as today.
  Otherwise, in an interactive session with httpuv installed, the layer is
  added with `embed = FALSE` and the view becomes served, with a message
  that names the size and says a server is now running. Over the threshold
  without httpuv, or in a non-interactive session, the layer is embedded
  with a warning naming the size (and httpuv when it is missing).
- **Why 32 MiB.** Base64 makes embedded bytes a third larger, so 32 MiB of
  tiles is about 43 MiB of page; 64 MiB would be about 85 MiB, which
  browsers and IDE viewers load slowly. The threshold is an option, so the
  default is easy to revisit.
- Vectors alone never trigger serving in this milestone (their blobs are
  already in memory; the size question for them is a later one). Remote
  COGs are never embedded, so they never count.
- **A served layer's temporary COG** is written to a session directory
  (`file.path(tempdir(), "aobview-cogs")`), is not deleted when the layer is
  added, and is handed to the server to own: it is deleted on `stop()`, and
  in any case when R removes its temporary directory at exit. An embedded
  layer's temporary COG is deleted at add time, as today.
- **The view object.** An embedded view is as today: `v$file` is the page and
  `v$server` is `NULL`. A served view has `v$server` (the handle) and
  `v$file = NULL`; printing it opens `v$server$url` in the viewer or the
  browser. IDE viewers accept `http://127.0.0.1` URLs, so the `in_tmp`
  rule in `open_page()` does not apply to them.
- **`view_add()` works on both.** On an embedded view it adds layers and
  rewrites the page as today, unless a new layer crosses the threshold:
  then the view becomes served as above (the page already on disk stays,
  and the server serves the earlier layers' embedded blobs as blobs). On a
  served view it adds layers (new local COGs with `embed = FALSE`), replaces
  the scene on the same server, keeps the URL, and opens the page again.
- An auto-served view leaves a server running until `v$server$stop()`,
  `aobcore::stop_scene_servers()` or the end of the session. The message
  that announces serving says this.
- `max_tiles` and the plan stay as they are for a served view. Serving
  removes the cost of tile bytes, not of the plan (tile records and meshes
  still travel in the page), so the "levels left out" warning still fires
  where it does today. Michael's GEBCO example is a remote COG, which is
  never embedded, so serving changes nothing for its "levels left out"
  warning. Whether a served view may plan more levels is left to a
  follow-up, and warnings stay as noisy as they are (Michael, 2026-10-01).

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
  their IDE's proxy (with `aobcore.serve_hosts` if needed), or they embed.
- Changing the scene spec.

## Evidence

This is a design record; nothing was built for it. It is based on reading
aobcore at `3502f60` (`R/html.R`, `R/cog.R`, `js/src/tiles.js`,
`js/src/index.js`), aobview at `886d33e` (`R/view.R`, `R/view-terra.R`,
`R/view-list.R`, and the tests named in the issues), and
`schema/scene-0.5.schema.json` in scenespec at `9f8df26`. The finding that
httpuv's `staticPaths` do not handle Range comes from the review of this
record (httpuv `src/webapplication.cpp`). Not checked: how each IDE viewer
and proxy treats a `127.0.0.1` URL and its `Host` header. That belongs in
the first implementation issues.

## Consequences

- **Charter and design post.** The second transport the post names, with no
  change to goals or non-goals.
- **Dependencies.** aobcore Imports stay nanoarrow, geoarrow, wk and
  htmltools. httpuv joins Suggests; when installed it brings Rcpp, later,
  promises and R6. aobview's Imports do not change; httpuv is reached
  through aobcore.
- **Scene spec.** No change. Served scenes validate as they do embedded.
- **Renderer.** One page-loader attribute for fetching blobs by URL, plus
  the key-list script (`data-aob-blob-keys`) that tells a tiled raster which
  tiles the server has as blobs. The tile range path is unchanged. Rendering changes need the headless screenshots of the
  conformance scenes, light and dark, so the served page is screenshot too,
  with the EPSG:3031 COG fixture first (polar first).
- **Embedding is unchanged.** Tile bytes are still read at add time when
  embedding, so existing pages, `scene_blobs()` and the aobview tests that
  count tile blobs keep working for embedded views.
- **Busy R stalls the page.** Requests are answered only when R is idle, and
  `staticPaths` cannot help because they do not handle Range. If that bites,
  the options are a Range-capable static handler contributed to httpuv, or
  serving from a separate process; either needs its own record.
- **Rules out** serving arbitrary paths, a directory listing, binding beyond
  loopback, absolute server URLs inside the scene document, and serving
  `/vsimem/` files.

### Proposed issues (not filed)

1. **aobcore: page builder with linked and inline modes.** Split
   `write_scene_html()`'s page into one internal builder that inlines the
   renderer and blobs (embed) or links them (serve).
   Done when: `write_scene_html()` output is byte-identical to today for the
   conformance scenes, blob order included; the linked mode emits
   `<script src="aob-renderer.min.js">`, no blob scripts and a
   `data-aob-blob-base` attribute; tests cover both.
2. **aobcore: renderer fetches blobs by URL when the page names a blob
   base.** Done when: `fromPage()` and `render()` fetch a missing blob from
   `<base>` plus `encodeURIComponent(key)`; a key with `/`, `@` and `+`
   round-trips; a missing blob with no base still errors as today; embedded
   pages are unchanged; JS tests cover both paths.
3. **aobcore: register local files for serving.** `scene_add_tiled_raster(embed
   = FALSE)` on a local COG records path, size and modification time in
   `attr(scene, "files")`; `embed = TRUE` is unchanged.
   Done when: with `embed = TRUE` the page for the polar 3031 COG fixture
   is byte-identical to today, blob order included; with `embed = FALSE`
   the scene has no tile blobs, one registered file and no registry in its
   JSON; `write_scene_html()` on it warns and writes the `file://` URL as
   today; a `/vsimem/` COG with `embed = FALSE` and no `url` errors. aobview tests: the
   tile-blob checks (`tile_blobs()` in `tests/testthat/helper-terra.R`,
   line 32, and its use in `tests/testthat/test-view-terra.R`, line 89)
   keep passing unchanged, since embedded views still carry tile blobs.
4. **aobcore: `serve_scene()` with httpuv in Suggests.** Routes as in
   decision 0006 item 1, loopback only, port and token without R's RNG, Host
   check with `aobcore.serve_hosts`, the `/<token>` redirect, blob content
   types by format, 404 for anything unregistered, `GET`/`HEAD` only,
   `blobs` and `files` arguments for plain-list scenes.
   Done when: R CMD check passes with and without httpuv installed
   (`skip_if_not_installed`); tests fetch every route over 127.0.0.1; wrong
   token, unknown route, `..`, `%2e%2e`, `%2f`, an absolute path and a
   sibling file in the COG's directory all answer 404; a foreign `Host`
   answers 403 and warns, and passes once listed in `aobcore.serve_hosts`;
   `.Random.seed` is identical before and after a call, and absent after
   if it was absent before; two calls after the same `set.seed()` give
   different tokens and ports; a test forces the fallback token source
   (through an internal option) and checks 32 hex characters, distinct
   values across calls, the message, and an unchanged `.Random.seed`; a
   relative cog `url` with no file and no blobs errors.
5. **aobcore: HTTP Range on registered files.** Done when: a request with
   no `Range` answers 200 from `body = list(file = path)`; single ranges in
   all three forms answer 206 with correct `Content-Range` and bytes; a range
   past the end, a range longer than the cap and a multi-range request each
   answer 416; `HEAD` gives the length; a file changed after registration
   answers 409 and `serve_scene()` on it errors; the renderer's
   `rangeReader()` draws the polar 3031 COG fixture from the served page
   with no whole-file fetch (checked by counting response sizes),
   screenshot light and dark.
6. **aobcore: server lifecycle.** Done when: the handle prints its URL and
   state; `stop()` is idempotent and frees the port; replacing the scene on
   a running server keeps its URL; `scene_servers()` and
   `stop_scene_servers()` work with three scenes served at once; servers
   stop on session exit and on unloading aobcore (tested in a child R
   process); a non-interactive call warns; owned temporary files are deleted
   on stop.
7. **aobview: choose serve or embed in `view()` and `view_add()`.** Done
   when: `transport` and the `aobview.transport` and `aobview.embed_max`
   (32 MiB) options work as in decision 0006 item 4, decided per local COG
   from the plan's `byte_length` totals before the layer is added; a local
   COG over the threshold is served with a message (which says a server is
   left running) in an interactive session, and embedded with a warning
   without httpuv or when not interactive; a small scene still writes the
   same page as today; a served view has `v$server` and `v$file = NULL`,
   and printing it opens the URL; `view(in_memory_raster)` works both
   embedded (temporary COG deleted at add time) and served (temporary COG
   kept in the session directory until stop); `view_add()` works on an
   embedded view, on a served view (same URL), and on an embedded view that
   crosses the threshold; a served view draws in the RStudio Server viewer
   (checked by hand and recorded in the PR, with the `aobcore.serve_hosts`
   value it needed, if any). aobview tests: the existing tile-blob checks
   (`helper-terra.R` line 32, `test-view-terra.R` line 89) stay for embedded
   views, and new tests for served views assert no tile blobs, one
   registered file and a running server, which they stop.
8. **design: decision 0007, websocket messages.** Done when: a record
   settles the message types, row ids versus feature ids, how selections
   reach the R user, and one server per scene or per session, sketched in
   decision 0006 item 5.

## Amendments

- 2026-10-01, from the review of aobcore#36 (issues 1 to 3):
  - Linked pages carry the served blob keys in a
    `<script type="application/json" data-aob-blob-keys>`, and tiled
    rasters fetch a tile from the blob base only for a listed key (item 1,
    "Renderer change, not a spec change").
  - `scene_add_tiled_raster(embed = FALSE)` on a `/vsimem/` COG with an
    explicit `url` stays allowed and registers nothing; only the case with
    no `url` errors (item 2).
  - Wording: the file registry is never written to the scene JSON, but a
    defaulted `url` is the `file://` URL, full path included, until
    `serve_scene()` replaces it in the copy it serves (item 2). The earlier
    text said "The JSON never sees the path", which was wrong for that
    case. Issue 3's done-when and the Consequences now say the same.
  - Size and modification time are recorded by `cog_info()`, and
    `scene_add_tiled_raster()` refuses a file changed since, embedded or
    not (item 2, "Unchanged files only").
  - The `write_scene_html()` warning names `serve_scene()` once part B
    (issues 4 to 6) ships; until then it says to serve the page over HTTP.
