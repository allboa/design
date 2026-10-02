# 0009: Views in knitted documents and in Shiny

- Date: 2026-10-02
- Status: proposed
- Issue: none; raised by Michael in the project thread (knitr, R Markdown,
  Quarto and Shiny output for `view()`)
- Decided by: agent

## Question

Decisions 0006 and 0007 left Shiny and Quarto out of scope ("they own their
transport") and sketched how the protocol 1 messages would carry over. How
does an `aob_view` show in a knitted document (knitr, R Markdown, Quarto) and
in a Shiny app, how do several views in one document share the renderer,
which transport each uses, and how do selections reach a Shiny server, with
aobview's Imports kept to exactly aobcore, grDevices, nanoarrow, PROJ, utils
and wk?

## Answer

Proposed: aobcore gains `scene_tag()`, which returns a scene as an htmltools
fragment (a sized `<div>` and its scene and blob scripts, embedded as in
`write_scene_html()`) with the renderer attached once as an
`htmltools::htmlDependency()`. aobview registers `knitr::knit_print()` for
`aob_view` lazily (knitr in Suggests) and prints that fragment, so a document
carries each view's data and one copy of the renderer. A document is always
embedded: while knitr runs, `"auto"` never serves, and a served view cannot be
printed into a document. Shiny gets `aobviewOutput()` and `renderAobview()`
(shiny in Suggests), its own small output binding rather than htmlwidgets, the
scene delivered as the render value, and selections sent as protocol 1
`select` messages through `Shiny.setInputValue()`, read in R with the view's
row map. The IDE viewer cases are unchanged.

## What exists today

- aobcore `scene_page()` (`R/html.R`) builds the one page for both
  transports; `write_scene_html()` writes it inline. The scene's element,
  JSON script and blob scripts are tied by a fixed id `"aob-scene"`.
- The renderer bundle (1.2 MB, an IIFE with the global `aob`) boots every
  `[data-aob-scene]` element without a `data-aob-status` when the document
  is loaded, and exposes `aob.render(container, scene, {blobs})`.
- The renderer's theme is page wide: tokens on `:root`, `data-theme` on the
  root element, and a theme button that sets it.
- aobview `finish_view()` writes the page (or starts a server) when the
  view is made; `print.aob_view()` opens it in the IDE viewer (a file under
  `tempdir()`, or the served URL) or the browser, only when interactive.
- `choose_embed()` serves under `"auto"` only in an interactive session
  with httpuv installed. A knitr run inside an interactive session (the
  console's `rmarkdown::render()`) is interactive, so today it could serve.

## Decisions

### 1. A scene as a fragment (aobcore)

`scene_tag(scene, blobs = attr(scene, "blobs"), width = "100%", height =
"480px", theme = "auto", id = NULL)` returns an htmltools `tagList`: a
`<div class="aob-fragment" data-aob-scene="<id>">` sized by inline style,
the scene JSON script with that id, and one `<script data-aob-blob>` per blob,
built by the same code as `scene_page()`'s inline mode so they cannot drift.
The renderer is not inlined: it is the dependency
`htmlDependency("aob-renderer", <renderer version>, src = <aobcore
inst/renderer>, script = "aob-renderer.min.js")`.

- **One renderer per document.** rmarkdown and Quarto resolve dependencies
  by name and keep the highest version, so a document with any number of
  views carries the 1.2 MB bundle once, in the head (inlined when the
  document is self-contained). `htmltools::save_html()` and Shiny do the
  same. If a host inlines the bundle twice anyway, the second boot skips the
  elements the first claimed (their `data-aob-status`), so nothing draws
  twice; only bytes are wasted.
- **Data are per view**, never shared: each fragment carries its own blobs,
  as base64 in the document. A document shows the same embedded bytes as
  the page `view()` writes.
- **Ids** are unique per call without touching the R random seed (a knitted
  document's random numbers must not change because it shows a view): a
  per-session counter with the process id and the time.
- **Checks** are those of `write_scene_html()`, including the warning for
  a registered local COG a page on disk cannot read.
- **Theme per view.** The renderer sets no theme and no `color-scheme` on
  the host's root element. Its tokens are custom properties only
  (`--aob-*`, including `--aob-scheme`), and `color-scheme` is set on the
  renderer's own element (`.aob-root`) from `--aob-scheme`; a whole page's
  own CSS sets its root's from the same token, so whole pages look as
  before. The tokens also apply under `.aob-fragment[data-theme]` (light
  or dark, fixed), and the theme button acts on the fragment it is in
  rather than the root element; a fragment with theme `"auto"` follows
  `prefers-color-scheme` as a page does.
- **Keys per view.** In a fragment (or over a host's channel, item 3)
  Escape, which clears the selection, is heard only on the view's own
  element, and a press on the map gives that view the keyboard focus, so
  one key press never acts on every view of a page. A whole page is one
  view and keeps listening on the window.
- **Late fragments.** The renderer boots the scene elements in the page
  once the document has loaded. A fragment inserted later (Shiny's
  `renderUI()` or `insertUI()`) ends with a one-line script calling
  `aob.boot()`, which draws every scene element not yet drawn; a renderer
  that loads after the fragment boots it itself. A host that inserts the
  HTML without running its scripts calls `aob.boot()`.

### 2. knitr, R Markdown, Quarto (aobview)

- `knit_print.aob_view(x, options, ...)` is registered by R's delayed S3
  registration, `S3method(knitr::knit_print, aob_view)` in NAMESPACE
  (roxygen `@exportS3Method knitr::knit_print`), which takes effect when
  knitr is loaded, since knitr can only be in Suggests. It returns
  `knitr::knit_print(aobcore::scene_tag(...))`, whose htmltools method
  passes the renderer to the document as `knit_meta`.
- **Size.** Width is the chunk's `out.width` when it is a string, else
  `"100%"` (a numeric `out.width` is knitr's own, set from `fig.width`
  when `fig.retina` is on, as in R Markdown, and would pin every view to
  672 px); height is `out.height` when given, else `fig.height` times 96
  pixels (480 px for R Markdown's default of 5 inches, 672 for plain
  knitr's 7).
- **Theme.** The view's `theme`; `view(theme = "light")` fixes a view in a
  light document whatever the reader's browser prefers.
- **Transport.** A rendered document has no R behind it, so the served
  transport cannot be used. While knitr runs (`knitr.in.progress`),
  `"auto"` embeds whatever the size: over `aobview.embed_max` it embeds with
  the warning `view()` already gives in a non-interactive session, naming
  the document as the reason, and the warning shows in the document.
  `knit_print()` of a served view (`transport = "serve"`, or a view served
  before knitting) is an error that says to use `transport = "embed"`.
- **Not HTML.** For a PDF or Word target knitr's own rule for HTML
  dependencies applies (an error unless `always_allow_html`, or a screenshot
  through webshot); aobview adds nothing.
- `view()` still writes its page to `tempdir()` while knitting; `v$file`
  stays part of the view. No selection in a document (0007 item 8).
- Quarto's knitr engine calls the same method; `server: shiny` documents
  are the Shiny case.

### 3. Shiny (aobview)

Options:

- **a. aobview's own output binding.** `aobviewOutput(outputId, width =
  "100%", height = "480px")` is a `<div class="aobview-output">` with two
  dependencies, the renderer (from aobcore) and a small binding script
  shipped by aobview; `renderAobview(expr)` evaluates `expr` to an
  `aob_view` and sends the scene as the render value.
- b. htmlwidgets. Rejected: it can only be in Suggests, so aobview's
  knitr path could not rely on it and would be written twice; it
  serialises the value with its own JSON (jsonlite) where aobcore already
  writes the scene document; and its sizing policy and `HTMLWidgets.widget`
  wrapper add nothing the renderer lacks.
- c. Embed a whole page in an `<iframe>` (`srcdoc`). Rejected: every
  output carries the renderer again, and the page cannot reach Shiny's
  input values without a second message channel.

Recommended: **a**.

- **Value.** `list(scene = <scene JSON text>, blobs = <named list of
  base64 text>, theme, select = <layer ids>, serial = <render count>)`,
  over Shiny's own websocket. The binding finalizes the previous render of
  its element and calls `aob.render(el, scene, {blobs, channel})`.
- **Transport.** Shiny's server is the only one the browser can reach (an
  app may be remote), so a view rendered in Shiny is embedded: `"auto"`
  never serves while `shiny::isRunning()`, and `renderAobview()` of a served
  view is an error, as in a document. Large local rasters in Shiny (tiles
  over Shiny's own HTTP) are a later decision.
- **Selections.** 0007 item 9, with one change. The renderer takes a
  `channel` option: a factory `channel(onState)` that returns `{send,
  onMessage, close}`, the same interface as the websocket channel.
  `send(message)` is always given a message object (never JSON text) and
  returns whether it was sent; `onMessage(f)` returns a function that
  removes `f`. The channel reports its state through `onState`: `"open"`
  (never synchronously, from inside `channel()`), `"closed"` or
  `"refused"`. `serial` is a render option, 0 when not given. A `reload`
  over a channel is ignored (it would reload the whole app). The binding's
  channel sends each `select` with
  `Shiny.setInputValue("<outputId>_aob_select", message, {priority:
  "event"})` and each `view` as `<outputId>_aob_view`: two inputs, not
  0007's one `<outputId>_aob`, since with one a `view` (sent after every
  settled pan) would replace the latest `select` and R would lose the
  selection. It answers the page's `hello` itself with R's `hello` (`select`,
  `serial`) from the render value: Shiny's session replaces the token,
  `Host` and `Origin` checks and the handshake. Every vector layer is
  selectable, as for a served view.
- **In R.** `renderAobview()` keeps the rendered view (its row map,
  `v$sources`) and the serial of the render in a reactive value per
  output, under the output's full id (`session$ns(outputId)`, so modules
  work), so readers re-run when the output renders again; the serial
  counts every render, `NULL` ones too.
  `aobview_selection(outputId, session)`, `aobview_selected(outputId,
  source = NULL, session)` and `aobview_view_state(outputId, session)` read
  those inputs (so they are reactive) and return what `selection()`,
  `selected()` and `view_state()` return for a served view. A message for
  an older render's serial is ignored. A new render clears the selection,
  as a reload does. The temporary page `view()` writes is deleted on the
  output's next render and when the session ends.
- R pushes nothing in this milestone (no `sendCustomMessage`); a new
  render is how R changes the page.

### 4. IDE viewers

Already covered and unchanged: `print.aob_view()` opens an embedded page
in RStudio's or Positron's viewer (`getOption("viewer")`) when the file is
under `tempdir()`, else the browser, and a served view's
`http://127.0.0.1` URL in the viewer (0006 item 4, 0007 item 5).

## Evidence

Read: aobcore `R/html.R`, `R/serve.R`, `js/src/index.js`, `channel.js`,
`link.js` and `style.js` at `41b4b92`; aobview `R/view.R` and
`R/transport.R` at `406e71e`; htmltools 0.5.9 `knit_print.shiny.tag`
(dependencies returned as `knit_meta`); shiny 1.14.0 exports
(`createRenderFunction`, `isRunning`, `getDefaultReactiveDomain`).

Built and checked (allboa/aobcore#54 and #55, allboa/aobview#32 and
#33): two views in one rendered R Markdown document draw with one copy of
the renderer, each in its own fixed theme; in a Shiny app in headless
Chromium a click, a Shift-click and Escape reach R as
`aobview_selected()` rows, the settled camera as `aobview_view_state()`,
and a re-render clears the selection.

## Consequences

- aobcore: `scene_tag()` and `renderer_dependency()` exported; the
  renderer's theme scoping and a `channel` render option (with the bundle rebuilt). Imports unchanged
  (htmltools is already one).
- aobview: knitr, rmarkdown, shiny in Suggests; lazily registered
  `knit_print.aob_view`; `aobviewOutput()`, `renderAobview()`,
  `aobview_selection()`, `aobview_selected()`, `aobview_view_state()`;
  Imports unchanged.
- No scene spec change and no protocol change: the Shiny channel carries
  protocol 1 messages.
- Ruled out for now: a served view inside a document or a Shiny app; data
  shared between views of one document; htmlwidgets.
