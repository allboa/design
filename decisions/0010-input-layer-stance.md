# 0010: Where input data comes from, and what to add next

- Date: 2026-10-06
- Status: accepted (Michael, 2026-10-06, design#21 merged as "net positive")
- Issue: none; Michael's brief in the project thread, 2026-10-06, written up
  as [mdsumner/sidebyside `docs/allonboard-input-layer.md`](https://github.com/mdsumner/sidebyside/blob/main/docs/allonboard-input-layer.md),
  with [hypertidy/rangefinder](https://github.com/hypertidy/rangefinder) and
  [mdsumner/sidebyside](https://github.com/mdsumner/sidebyside) as the
  evidence
- Decided by: Michael (plan level: it widens the input scope beyond the v1
  charter, so it is not an agent decision)

## Question

What input data formats and technologies does allonboard handle today, where
does each one live (R package, scene spec, renderer), which ones should it
add, and by which route? The answer should line up allonboard's "warp"
practice (GDAL and R planning a raster into a view CRS) with the direction of
the Python, Icechunk and JavaScript grid community (zarrita, icechunk-js,
gridlook, rangefinder), so that it can feed back to rangefinder and
sidebyside and from there to that community.

## Answer

allonboard takes three primitives (explicit, warp, cell): vectors stay
GeoArrow, and for grids and cells R sends a recipe, never pixels, by the
R-planned route of decision 0003 wherever GDAL can describe the pieces as
byte ranges and by a new browser-resolved route through rangefinder's
source modules for the rest. The chunk reference (URL, offset, length,
codec) is the currency both routes share, and the order of formats to add
is under Consequences.

## Evidence

### What allonboard reads today, and where

| Input | Route | Lives in | Who reads the bytes |
| --- | --- | --- | --- |
| sf, wk-handleable vectors, terra `SpatVector` | explicit, wk then GeoArrow (0008) | aobview `vector-input.R`, `view-terra.R` | R |
| any GDAL vector source | explicit, GDAL stream then GeoArrow (0002, 0004) | aobcore `gdal_vector_stream()` | R (GDAL) |
| a COG, local or remote | warp, R-planned (0003) | aobcore `cog_info()`, `cog_plan()`, `scene_add_tiled_raster()`; scene spec `tiled_raster` with a `cog` source | browser, by HTTP range (remote) or from embedded or served blobs (local, 0006) |
| a terra `SpatRaster` that is not a COG | warp, via a temporary COG | aobview `view-terra.R` (`terra::writeRaster()`) | R writes, then as a COG |
| a huge GDAL raster (WMS, TMS, VRT) | warp, GDAL reads the planned window into a temporary COG | aobview `view-gdal.R` (`gdalraster::translate()`) | R (GDAL) writes, then as a COG |
| a small grid with a buffer | warp, untiled | scene spec `raster` (0.1) | R |
| Zarr, Kerchunk, Icechunk, STAC, XYZ or WMTS as recipes | none | | |
| DGGS cells, curvilinear model grids | none, except by the user expanding cells to polygons in R | | |

So allonboard is a recipe system for COGs and a payload system for every
other grid: the non-COG paths materialise a COG in R first. That is correct
for local data and wrong for cloud data, where the recipe principle says the
bytes should stay in the bucket.

### What rangefinder and sidebyside show

- rangefinder splits a viewer into space, time, pixels and render, and its
  layers 1 to 3 are interfaces with plain ES module bindings, no build step
  and no UI imports: COG, XYZ and WMTS tiles, VRT mosaics, STAC, starc
  stores, Zarr v2 and v3, Kerchunk JSON and Parquet references, Icechunk
  through icechunk-js, curvilinear grids and HEALPix
  ([`lib/sources/`](https://github.com/hypertidy/rangefinder/tree/main/lib/sources),
  [`docs/design.md`](https://github.com/hypertidy/rangefinder/blob/main/docs/design.md)).
  Icechunk was a fourth store kind behind the existing Zarr seam, not a new
  source ([`docs/icechunk.md`](https://github.com/hypertidy/rangefinder/blob/main/docs/icechunk.md)).
- rangefinder's layer 3 has one shape: given an asset and an output grid
  (CRS, extent, width, height), return typed arrays on that grid
  (`readWarped()` in `lib/cog.js`). That is a **materialised** warp:
  nearest-neighbour onto the output grid, with the fidelity rules written
  down ([`docs/fidelity.md`](https://github.com/hypertidy/rangefinder/blob/main/docs/fidelity.md)).
- allonboard's tiled raster is a **drape**: source values on a texture,
  positions on a mesh, nothing resampled. The sidebyside article's "drape is
  not warp" section names exactly this split. It is the brief's open
  question "texture versus sampled raster", and allonboard has already
  chosen drape for COGs.
- Read as a program for allonboard, sidebyside's pages put each cloud
  format in a stance (the brief, section 5): COG, tiles and big arrays are
  warp, with readers that exist; Zarr, Kerchunk and Icechunk are warp, with
  snapshot pinning to carry; curvilinear grids reach warp by cell
  rasterisation; HEALPix is cell, or warp by inverse sampling; for S2 and H3
  the DGGS abstraction is the open work, and S2 cells have no renderer on
  either side ([page 01](https://github.com/mdsumner/sidebyside#pages));
  projected and polar CRSs are warp only.

### What allonboard can answer back

The brief's first render-side question was whether the warp primitive can be
drawn in a polar view inside deck.gl without its own WebGL context.
allonboard has answered it: yes. Decision 0003 draws COG tiles in a
deck.gl `OrthographicView` of EPSG:3031 metres, one `SimpleMeshLayer` per
tile with a mesh in the view CRS, clean at the pole and the antimeridian;
aobcore's tiled raster is built that way.
What does not work is deck.gl-raster's tiled traversal, which is Mercator
throughout (0003 lists the six upstream changes). The view domain (0005)
handles how far a polar or divergent CRS may be panned. This is worth
sending back to rangefinder and sidebyside as a finding, not a question.

## Consequences

### The stance in detail

allonboard takes three primitives, after the sidebyside article, and gives
each a layer type and a route:

1. **Explicit** (coordinates are stored): vectors arrive as native GeoArrow
   and are drawn as given. This is allonboard's own ground and stays as
   decisions 0002, 0004 and 0008 set it.
2. **Warp** (the image is the primitive): a grid with a CRS and a
   geotransform is draped on a mesh in the view CRS. Values stay values; the
   mesh carries the projection.
3. **Cell** (the grid is the primitive): a column of cell ids plus a scheme
   (HEALPix, S2, H3) whose geometry is computed from the ids.

For warp and cell inputs, **R sends a recipe, never pixels**, and there are
two recipe routes. allonboard keeps both and says which one each format takes:

- **R-planned** (decision 0003, built): R reads the source's structure
  through GDAL, plans the pieces the view needs and ships their byte ranges
  with meshes already projected by PROJ. The browser fetches and decodes the
  bytes and only draws. This stays the default whenever GDAL can describe
  the source's pieces as plain byte ranges with a known codec.
- **Browser-resolved** (new): R ships a small catalogue entry (source kind,
  URL, variable, time, snapshot, CRS) and a JavaScript reader in the page
  resolves it. allonboard does not write those readers. It adopts
  rangefinder's source modules, which were built to be lifted out, as a
  renderer dependency (how they are shipped is item 3's decision below).
  This route is for what R cannot or should not
  plan: Icechunk snapshots, live STAC searches, time scrubbing, and sources
  that must re-plan as the camera moves beyond any plan R made.

The common currency between the routes, and between allonboard and the Zarr
world, is the **chunk reference**: (URL, offset, length, codec, position in
the grid). A COG tile, a Zarr chunk, a Kerchunk reference and an Icechunk
virtual chunk are all one. allonboard's scene spec should name that
currency rather than a file format.

### What to add, in order

Each item is a spike with its own decision record, per the agent brief. The
order puts recipe routes that reuse the built R-planned path first.

1. **Tile services as recipes (XYZ, WMTS).** R plans tiles in the service's
   tile matrix with meshes in the view CRS, exactly as for COG tiles; the
   browser fetches each tile image by URL. This replaces the temporary-COG
   path for remote tile services and is the post's basemap question
   (problem 1) answered by warping, not by vector land alone. It is post-v1
   work and leaves the v1 non-goal "Web Mercator basemap parity" as it is.
   Scene spec: a new data reference `format` (say `tiles`) beside `cog`,
   used by `tiled_raster`. The polar test is the GIBS
   EPSG:3031 WMTS on sidebyside page 04. This is cheap only while the tile
   matrix is regular. WMTS GetCapabilities can describe irregular matrix
   sets (per-level origins, tile sizes and matrix limits), and the LIST
   Tasmania one does, so the R planner reads the capabilities document and
   plans from the matrix set it declares, never from the OGC default
   (GoogleMapsCompatible or a power-of-two pyramid). XYZ templates, which
   carry no capabilities, are the one case where the default is assumed,
   and the spike tests both.
2. **Chunk references as a data format.** Generalise the `cog` data
   reference `format` to a list of chunk references with a codec, so a regular-grid Zarr array, a
   Kerchunk reference set, or the output of `gdal mdim get-refs` or blocklist
   plans and draws like COG tiles. R reads the structure through GDAL's
   multidimensional API. The open cost is codec decoding in the browser
   (blosc, zstd and the Zarr v3 codec chain), which rangefinder already
   loads through zarrita.
3. **A browser-resolved layer.** One layer type whose data is a catalogue
   entry, resolved by rangefinder's source modules, drawn as a texture draped on the view's mesh (the brief's
   suggested first step). Icechunk (with the snapshot id in the recipe),
   STAC searches and starc stores arrive this way first. This needs a
   decision on the JavaScript dependency, and that is the real fork in the
   road. rangefinder loads zarrita and icechunk-js lazily from a CDN, which
   is why it has no build step; an embedded page opened offline (the
   default transport, decision 0006, and every knitted document, 0009)
   cannot do that. The expected answer is to bundle rangefinder's source
   modules into aobcore's renderer, which argues for publishing them to npm
   (as their own package or a rangefinder subpath) sooner rather than
   later, so allonboard pins a version instead of vendoring files. CDN
   loading stays possible for served views but is not the default. Bundle
   size is the cost to measure. It also needs a decision on the
   CRS the browser needs: R knows the view CRS and sends it as WKT plus a
   proj4 string where one exists, with proj-wasm as the fallback, matching
   sidebyside page 07.
4. **Cells.** Today: R expands cell ids to polygons and sends them as
   explicit geometry, which works now with no spec change and is fine for
   tens of thousands of cells. Next: a `cells` layer type, an Arrow column
   of ids plus scheme and level, expanded in the browser and projected to
   the view CRS (deck.gl's `S2Layer` and `H3HexagonLayer` assume lon/lat,
   so they are not usable as they stand in a polar view). HEALPix first,
   because rangefinder's `lib/dggs.js` and gridlook both read it; S2 second,
   with a trend.sst fixture, which is sidebyside page 01's open bridge.
5. **Curvilinear grids.** R builds the cell mesh from the 2D longitude and
   latitude arrays (corners from CF bounds or psi points, as rangefinder
   does) and ships it as an explicit mesh with per-cell values; the
   browser-resolved route takes rangefinder's rasterise-then-warp path. Which
   one is the default waits on item 3.

### What this changes and rules out

- **Charter.** The v1 target is unchanged (a polar COG with vectors). This
  record sets the order of work after v1 and widens "tiled rasters from
  COGs" to chunked grids generally. The non-goals "a new WebGL renderer"
  and "Web Mercator basemap parity" stand: everything here draws through deck.gl layers.
- **Scene spec.** Stays renderer-neutral and reader-neutral. It gains data
  reference formats (`tiles`, `chunks`, a catalogue entry) and later a
  `cells` layer, each in its own scene spec version, none in this record.
  The catalogue entry is defined by the spec, not by rangefinder's internal
  catalogue shape; rangefinder is the first reader of it, not its owner.
- **R packages.** No new Imports. gdalraster stays in Suggests as the
  structure reader. R does not fetch pixels for cloud sources, and the
  temporary-COG paths remain for local and in-memory data only.
- **Renderer.** Adopting rangefinder's source modules is the first JavaScript
  dependency beyond deck.gl and its GeoArrow and raster packages. It is
  taken only with item 3's own decision.
- **Ruled out:** allonboard writing its own Zarr, Icechunk or STAC readers;
  R downloading cloud grids to rewrite them as COGs; a cell layer that only
  works in Web Mercator.
- **Feedback out.** rangefinder and sidebyside get three things back: the
  polar drape works in deck.gl (above), the chunk reference as the shared
  currency of the two routes, and the drape and materialised warp kept
  apart in the input contract, so a reader can offer either.
