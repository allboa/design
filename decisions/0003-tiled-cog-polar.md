# 0003: Tiled COGs reach a polar view as R-planned tiles (proposed)

- Date: 2026-09-30
- Status: proposed
- Issue: allboa/spikes#1
- Decided by: Michael (gate A)

## Question

Gate A: how should a tiled COG with overviews reach a view in its own CRS
(EPSG:3031 first) with level of detail? Should R plan the tiles and ship
pre-projected meshes plus byte ranges, or should the browser traverse the
tile pyramid itself, as deck.gl-raster's COGLayer does in Web Mercator?

## Answer

Proposed: R-planned tiles for v1. R reads the COG's structure, picks the
overview level and tiles for the view, and ships each tile's byte range with
a mesh already projected to the view CRS. The browser fetches the bytes
itself and only draws. Browser-side traversal in the view CRS becomes an
upstream contribution to deck.gl-raster, not a dependency of v1.

The main reason: R-planned tiles work end to end today, for a 3031 COG and
for a lon/lat COG over the pole and the antimeridian, with no upstream
change, and projection stays with PROJ in R. The browser-side traversal works
only as a prototype on private deck.gl-raster API, and for lon/lat sources
over the pole it needs the unmerged mesh fix from decision 0001.

## Evidence

The code, screenshots and numbers are in
[allboa/spikes `tiled-cog-polar/`](https://github.com/allboa/spikes/tree/spike-tiled-cog-polar/tiled-cog-polar)
(PR [allboa/spikes#7](https://github.com/allboa/spikes/pull/7)). There are two
test COGs, each with five levels, 256 x 256 DEFLATE tiles, and a synthetic
field with seam markers. One is in EPSG:3031 (2560 x 2560, 5 km). The other is
in lon/lat (3600 x 500, 0.1 degree, lon -180..180, lat -40..-90). Everything
was rendered in headless Chromium with SwiftShader, in a deck.gl 9.4
`OrthographicView` of 3031 metres.

- **R-planned tiles, end to end.** `planner.py` stands in for R. It reads
  tile byte ranges from the COG header, chooses the coarsest level whose
  source pixel is no larger than a device pixel, culls tiles by their
  projected footprint, and returns JSON. The browser fetches each range,
  inflates it with `DecompressionStream` and draws one `SimpleMeshLayer` per
  tile.
  - For the 3031 COG, the presets drew levels 3, 1, 0 and 0, with 4, 25, 12
    and 4 tiles
    ([far](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/a_3031_far.png),
    [all](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/a_3031_all.png),
    [pole](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/a_3031_pole.png)).
  - One page session zoomed with the mouse wheel re-planned through levels
    3, 2, 1, 1 and 0
    ([step 4](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/a_3031_wheel_4.png)).
  - The lon/lat COG drew at levels 2 and 0. Its 15 pole-row tiles meet
    cleanly at the pole, and the image edge at 180 shows no seam
    ([pole](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/a_4326_pole.png),
    [antimeridian](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/a_4326_antimeridian.png)).
  - Plans took 2 to 28 ms. A plan is 1 to 8 KiB of JSON for the 3031 COG and
    up to 374 KiB for lon/lat, whose curved meshes use 2-degree cells.
  - All three pieces were written for the spike: the planner is about 130
    lines, the transport about 80 and the browser side about 160.
- **Browser traversal, prototyped.** It keeps deck.gl-raster 0.8.1's
  `RasterTileLayer`, `AffineTileset` and `RasterLayer`. It replaces
  `RasterTileset2D.getTileIndices` with a quadtree walk culled in view metres
  and `getTileMetadata` with per-tile reprojection into the view CRS, and
  overrides `RasterTileLayer._renderTileLayer` to use them. That is about
  130 lines.
  - In every preset run with both approaches, it picks the same level and
    number of tiles as the planner
    ([3031 all](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/b_3031_all.png)).
  - The lon/lat COG draws with gaps along the pole-row tile edges and 16 mesh
    non-convergence warnings
    ([stock](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/b_4326_all_stock.png)).
    It is clean only with decision 0001's forward error metric patched in
    ([forward](https://github.com/allboa/spikes/blob/spike-tiled-cog-polar/tiled-cog-polar/screenshots/b_4326_all_forward.png)).
  - Two Mercator assumptions surfaced along the way. First, deck.gl
    `TileLayer` culls sub-layers against a lon/lat `tile.bbox`, which culls
    every tile in an orthographic view. Second, `TileLayer` hides everything
    below `minZoom` (default 0), while this view sits near zoom -13. Lowering
    `minZoom` hangs the page, because `RasterTileset2D.getParentIndex` returns
    z = 0 for z = 0 and `Tileset2D` walks parents while `z > minZoom`.

## Consequences

What the browser-side option would have cost, as upstream work in
deck.gl-raster (several PRs with tests and maintainer review):

1. A view-projection hook in `RasterTileset2D` and the tile traversal, in
   place of the hard-wired `projectTo3857`, Mercator common space,
   Mercator-latitude LOD and 85.05 degree clamp.
2. `tile.bbox` in view units for non-geographic views.
3. A fix for the zoom gate and the parent walk at z = 0.
4. A supported way to pass a tileset or view projection through
   `RasterTileLayer` and `COGLayer`.
5. The forward mesh error metric (decision 0001).
6. Source-to-view projection in the browser: proj4 for common CRSs, and PROJ
   in wasm or definitions shipped from R for the rest.

These are the upstream changes worth proposing even with R-planned tiles
chosen: they serve lonboard too, and they are the path to globe and spinning
views, where a plan tied to one view CRS does not fit.

If R-planned tiles are accepted:

- **Scene spec.** A tiled raster layer references the COG by URL and carries
  a tile plan: level, tile byte ranges, and per-tile meshes in the view CRS
  with UVs. The plan is data, not renderer props, so the spec stays
  renderer-neutral. The meshes should travel as Arrow buffers (float32
  positions and UVs, uint32 indices), not JSON.
- **Core package (plan issue 10).** The planner is R. GDAL gives tile byte
  ranges through the `BLOCK_OFFSET_x_y` and `BLOCK_SIZE_x_y` metadata items
  in the `TIFF` domain, and PROJ projects the meshes. Mesh building should
  share code with vector densification ("curvature is one sampling
  decision").
- **Transports.** An interactive view needs a live R session (httpuv or a
  websocket) with one round trip per settled view change. For the
  self-contained page, R ships the plan for every level up front: 139 tiles
  and 42 KiB of JSON for the 3031 COG, 45 tiles and about 1 MiB of binary
  meshes (positions, UVs, indices) for the lon/lat one, which could shrink if
  tiles shared a mesh. The browser then only filters tiles by
  footprint and pixel size, which is about 30 lines and renderer-neutral.
- **Browser decoding.** DEFLATE without a predictor works via
  `DecompressionStream`. LZW, ZSTD, LERC and predictors need decoders;
  `@developmentseed/geotiff`'s codecs can be reused for the bytes alone.
- **Rules out for v1:** depending on a deck.gl-raster fork, or on private
  tileset API, for polar tiling. Revisit when upstream has a view-projection
  hook; a later record would then supersede this one.
