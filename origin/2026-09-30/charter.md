# allonboard: project charter

Sep 30, 2026 - @Michael

allonboard builds a map viewer for R that draws data in its own CRS, polar views included, from GeoArrow and grid descriptors. The design post in the first tab and the polar view probe are the origin record. This tab is the charter the project team works from.

## Goals and non-goals

The v1 target is an R user viewing a polar COG with vector overlays in EPSG:3031, from a lean package, in one call.

Goals:

- A renderer-neutral **scene spec**: view CRS, view type, layers, data references, styling as data.
- A lean **core R package** that emits GeoArrow streams, grid descriptors and URLs, and delivers a scene over pluggable transports.
- **Any projected view CRS**, with polar stereographic as the first-class test case.
- **Tiled rasters from COGs**, drawn in the view CRS with level of detail, fetched by the browser where possible.
- A **convenience package** with a mapview-style `view(x)` for sf and terra.
- **Upstream contributions** where the gap is shared, starting with non-Mercator tile loading in deck.gl-raster.

Non-goals for v1:

- A new WebGL renderer. deck.gl comes first; a hand-built renderer happens only if a gate forces it.
- Labels with collision handling, and vector tiles.
- Web Mercator basemap parity. Vector land drawn in the view CRS is the v1 basemap.
- Editing geometry in the browser.
- A Python front end. The scene spec keeps that door open, but lonboard already serves Python.

## Roadmap

Phase 0 turns the proof into a spec and answers the one question that could change the architecture: how tiled COGs reach a polar view.

&#91;embedded content: roadmap - 4 phases, 3 gates\]

Phases are ordered, not dated. Gate A is the one that matters most: until the tiled-raster approach is chosen, phase 1 builds vectors and transport only.

## Org and repos

The project is allonboard. Its public GitHub org is [allboa](https://github.com/allboa) for now, because the `allonboard` name is reserved; the org may be renamed later. It holds five repos, each narrow enough for one agent to own a change end to end. Package names are placeholders until a naming decision.

| Repo | Scope | Language | Phase |
| --- | --- | --- | --- |
| `design` | The origin post, the probe and review (frozen), decision records, org-level agent brief | Markdown | 0 |
| `scenespec` | JSON schema, fixtures, a validator, conformance scenes (the probe is the first) | JSON, JS | 0 |
| `spikes` | Throwaway experiments; each spike ends in a decision record in `design` | Any | 0 |
| `aobcore` (placeholder) | Producers to GeoArrow and grid descriptors, scene building, embed transport, bundled renderer | R, JS | 1 |
| `aobview` (placeholder) | `view(x)` for sf and terra, palettes, legends, popups | R | 3 |

The renderer JavaScript lives in the core package at first. It moves to its own repo only if the go-large option (sharing lonboard's stack) is taken.

## Agent working rules

Every agent reads the org-level brief in `design` before touching a repo, and every change reaches main through a PR that Michael reviews.

The brief states the design principles:

- **Primitives first, recipe not payload.** Prefer sending a URL or a descriptor over materialized data. Prefer thin composable functions over one large interface.
- **Lean dependencies.** Core Imports stay at nanoarrow, geoarrow, wk and htmltools. Anything else needs a decision record.
- **The scene spec is renderer-neutral.** No deck.gl names, props or concepts in the schema. A renderer implements the spec.
- **Native GeoArrow only** in the data plane. WKB is converted before it leaves R.
- **ASCII only** in package sources and shipped files. Any exception needs a stated reason in the PR.
- **Polar first.** Every rendering feature is tested in EPSG:3031 before Web Mercator.

How work flows:

1. Work starts from an issue with acceptance criteria. An agent comments on the issue to claim it.
2. One issue, one branch, one PR. The PR links the issue and says how the criteria were checked.
3. Rendering changes include a headless screenshot of the conformance scenes, light and dark.
4. A spike ends with a short decision record in `design`, even when the answer is no.
5. main is protected: CI must pass and Michael is the required reviewer, at least until the scene spec reaches 0.1.
6. Agents act through the org's GitHub App, installed on this org only. No access to other orgs or personal repos.

## First issues

Ten issues are ready to file. Phase 0 runs issues 1 to 6 in parallel. Issues 7 to 9 can start alongside the spikes; issue 10 waits for gate A.

| # | Repo | Issue | Done when | Phase |
| --- | --- | --- | --- | --- |
| 1 | `design` | Import the origin record | The post, the probe HTML, prep script, bundle and review are committed, with a README that dates them as frozen | 0 |
| 2 | `design` | Write the org agent brief | The working rules above are an AGENTS.md at org level and linked from every repo README | 0 |
| 3 | `scenespec` | Draft scene spec 0.1 schema | JSON Schema covers view, layers, data refs, grid descriptor, styling; the probe's scene validates; no renderer terms | 0 |
| 4 | `spikes` | Tiled COG in a polar view | A polar COG over the pole draws in EPSG:3031 with at least two zoom levels; decision record picks R-planned tiles or browser-side traversal | 0 |
| 5 | `spikes` | gdalraster to native GeoArrow | An OGR layer reaches the browser as native GeoArrow via gdalraster's Arrow stream, or the record says what is missing | 0 |
| 6 | `spikes` | deck.gl-raster RasterLayer in 3031 | One untiled COG draws in an orthographic view with a 3031 reprojection function, or the record says why not | 0 |
| 7 | `aobcore` | Package skeleton | Package installs with only the lean Imports; CI runs R CMD check on Linux, macOS and Windows | 1 |
| 8 | `aobcore` | Vector producers | `wk`-handleable input and GDAL Arrow streams become native GeoArrow; the coastline fixture round-trips | 1 |
| 9 | `aobcore` | Embed transport and renderer | One function writes a self-contained page; conformance scenes screenshot correctly in both themes | 1 |
| 10 | `aobcore` | Raster layer per gate A | The approach chosen in issue 4 draws the polar COG fixture from R in one call | 1 |

## Decisions for Michael

Two of the four pre-phase-0 calls are made; the naming call can wait until before CRAN.

Before phase 0:

- [x] Create the org: `allboa`, public from day one; `allonboard` is reserved and may be reclaimed later.
- [ ] Tell Kyle Barron about the name and the crossover intent. The org is already public, so this is the next thing to do.
- [x] Choose how agents get access: a GitHub App on the org.
- [ ] Replace the placeholder package names `aobcore` and `aobview` before anything goes to CRAN.

At the gates:

- Gate A: which tiled-raster approach to build on, from the issue 4 decision record.
- Gate B: whether to propose the scene spec to the lonboard maintainers as a shared contract.
- Gate C: when to lift the required-reviewer rule and let agents merge within agreed bounds.
