# 0001: deck.gl-raster RasterLayer draws in EPSG:3031, lon/lat over the pole needs a fix

- Date: 2026-09-30
- Status: proposed
- Issue: allboa/spikes#3
- Decided by: agent

## Question

Can deck.gl-raster's lower-level `RasterLayer`, given a custom EPSG:3031
reprojection, draw one untiled COG that covers the pole and crosses the
antimeridian in an `OrthographicView`?

## Answer

Yes for a COG already in EPSG:3031, with stock deck.gl-raster 0.8.1. Not yet
for a lon/lat (EPSG:4326) COG over the pole. The layer's mesh builder measures
error through the inverse projection, and at the pole and on the 180 meridian
that inverse has more than one answer, so the mesh never converges and
nothing draws. Measuring the error in the forward direction instead fixes
it. That is a small change, about 30 lines in one function, and worth
proposing upstream.

## Evidence

The code, screenshots and numbers are in
[allboa/spikes `rasterlayer-3031/`](https://github.com/allboa/spikes/tree/main/rasterlayer-3031)
(PR [allboa/spikes#6](https://github.com/allboa/spikes/pull/6)). Versions:
`@developmentseed/deck.gl-raster` 0.8.1, `@developmentseed/geotiff` 0.8.1,
deck.gl 9.4, and proj4 2.22. Everything was bundled locally with esbuild and
rendered in headless Chromium with SwiftShader. The test COGs come from
`make_cogs.py` (GDAL 3.10 via rasterio). They hold a synthetic field with
30 degree sector stripes, a ring at -60 and a blob on the antimeridian, so
seams show.

- **EPSG:3031 COG, stock layer.** 2560 x 2560, 5 km cells, a +-6.4e6 m square
  over the pole. The reprojection is the identity, and the mesh is 4 vertices
  and 2 triangles. It draws, and so do the pole and the antimeridian
  ([full](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/stock_3031.png),
  [pole](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/stock_3031_pole.png),
  [antimeridian](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/stock_3031_antimeridian.png)).
- **Lon/lat COG, stock layer.** The image covers lon -180..180 and lat
  -40..-90 at 0.1 degrees (3600 x 500). `RasterReprojector` hits its
  10000-iteration cap with error 3600 px, the full image width, and every
  triangle has zero area, so nothing draws
  ([screenshot](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/stock_4326.png),
  [mesh](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/stock_4326_mesh.png)).
  The error check interpolates an output position and sends it back
  through `inverseReproject` and `inverseTransform`. At the pole every
  longitude maps to one point. On the 180 meridian proj4 returns -180 or +180,
  depending on the sign of a rounding error. So samples on those edges
  always report the whole image width as error, and refinement keeps adding
  vertices there.
- **The antimeridian inside the image, no pole.** For lon 90..270 and lat
  -40..-80, the stock layer converges if the caller wraps the inverse longitude
  into the image's range. That is a caller-side fix. Taking the same image to
  -89.9 already exhausts the iteration cap (0.313 px), and at -90 it fails
  (`mesh-check.txt`).
- **Forward error metric.** `src/forward-metric.js` is patched onto the
  prototype at runtime (it replaces a private method). It projects the exact UV sample forward, compares it
  with the interpolated output position, and divides by the local output size
  of one source pixel. It uses only the forward functions. With it, the same
  `RasterLayer` draws the lon -180..180 COG
  ([full](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/forward_4326.png),
  [pole](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/forward_4326_pole.png),
  [antimeridian](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/forward_4326_antimeridian.png),
  [mesh](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/forward_4326_mesh.png))
  and the lon 90..270 COG
  ([screenshot](https://github.com/allboa/spikes/blob/main/rasterlayer-3031/screenshots/forward_4326-90-270.png)).
  The 90..270 image converges to 0.125 px in 5372 vertices. On the pole-free
  image the forward metric needs 5323 vertices where the stock metric with
  wrapping needs 8221. The full-resolution 3600 x
  500 image stops at 0.216 px when it hits the cap, which is invisible here.
  Its level-3 overview converges in 2150 vertices.
- **The view.** `RasterLayer` works in an `OrthographicView` with
  `coordinateSystem: CARTESIAN` and metre positions up to 6.4e6, with no
  visible jitter at the zooms tried.

## Consequences

- For an untiled raster in the view CRS, deck.gl-raster's `RasterLayer` is
  usable today when the source is already in the view CRS. That is the
  common Antarctic case (EPSG:3031 COGs). The core does not need its own mesh
  code for that case.
- A source in another CRS that covers the pole or has the antimeridian as an
  image edge (global lon/lat grids such as OISST, ERA5 and GEBCO) needs
  either the upstream fix or R-side meshes like the probe's. Until the fix
  lands, the core should ship a pre-projected mesh for those sources rather
  than depend on a runtime prototype patch.
- The upstream proposal for developmentseed/deck.gl-raster has three parts:
  1. a forward error metric in `RasterReprojector._findReprojectionCandidate`,
     or a forward fallback when the inverse round trip jumps;
  2. `maxIterations` exposed through `RasterLayer`, or scaled with image
     size;
  3. polar tests: EPSG:3031 output, and a lon/lat input over the pole with
     the seam both at the image edge and inside the image.

  This touches upstream issues #625, #366, #172 and #171 (and the polar examples #646 and #330), which were found by
  title and not read from this session. It fits the charter's upstream
  contribution goal and helps lonboard too.
- Scene spec 0.1 covers this only with materialized values or a
  pre-projected mesh. Referencing a COG by URL needs a spec addition (see
  0003).
- Tiling and level of detail are out of scope here. The tiled question
  (gate A) is allboa/spikes#1, decision 0003.
