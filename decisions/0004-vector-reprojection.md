# 0004: GDAL reprojects what it reads; wk + PROJ only into projected views

- Date: 2026-09-30
- Status: proposed
- Issue: allboa/spikes#8
- Decided by: agent

## Question

When vector data must reach the view CRS, should GDAL reproject it as it
streams from the source (virtual, on the fly), or should R transform it in
memory with a wk handler fed by a PROJ transform
(`PROJ::proj_trans_create()` into `wk::wk_transform()`)?

## Answer

Both, split by input. Anything GDAL reads is clipped, densified and
reprojected by GDAL, lazily, in one `gdal vector pipeline` with stream
output, and each Arrow batch is encoded as native GeoArrow in R as it
arrives. Inputs already in R (sf, wk vectors, geoarrow) may be transformed
by any `wk_trans`, such as a PROJ transform, in the same pass that encodes
GeoArrow, but only into a projected view CRS. GDAL's transform is
geometry-aware at the antimeridian and the poles; a per-coordinate transform
is not. Every route first clips to the view's valid area in the source CRS.

## Evidence

The code, full output and versions are in
[allboa/spikes `vector-reproject/`](https://github.com/allboa/spikes/tree/main/vector-reproject)
(PR allboa/spikes#9). Versions: R 4.5.3, GDAL 3.13.3, PROJ 9.9.0,
gdalraster 2.7.0, PROJ (R package) 0.7.0, wk 0.9.5, geoarrow 0.4.4 and
nanoarrow 0.8.0.1, all from conda-forge.

Five routes, all ending in native interleaved GeoArrow IPC in EPSG:3031:
`ogr2ogr` to a `/vsimem` Arrow copy (the current aobcore producer, decision
0002), the `gdal vector pipeline` with `--of stream`, an OGR VRT warped layer,
`wk_transform_filter()` with a PROJ transform per GDAL batch, and
`wk_transform()` on the whole layer in memory.

- **Coordinates are identical.** The maximum difference from the current
  producer is 0 m on every route, for the Natural Earth 50m coastline and
  land and for a 2,772,032 vertex 10m coastline. All routes call the same
  PROJ.
- **Speed and memory barely differ.** At 2.8 million vertices every route
  takes 1.7 to 3.7 seconds and peaks at 317 to 489 MB above baseline, for
  42 MB of IPC. The lazy routes are a little faster and lighter than the
  `/vsimem` copy. The embed transport needs the whole blob, so streaming
  the input saves little.
- **GDAL is geometry-aware.** Into a lon/lat target, `ogr2ogr` and
  `gdal vector reproject` split a line at 180 degrees and close a ring
  around the south pole along +-180 and -90, by default, without
  `-wrapdateline`. `wk_transform()` with a PROJ transform draws the line
  across the whole map and returns a wrong 5-vertex ring. Lon/lat into
  EPSG:3031, including Antarctica closing through the pole, the two are
  identical.
- **No route guards the view's domain.** The north pole into EPSG:3031
  comes back as y = 4.0e23, a finite number, from GDAL and from PROJ alike.
- **Densifying is GDAL-only.** GDAL segmentizes lazily in the pipeline
  (`segmentize` step, GDAL 3.12) or in `ogr2ogr -segmentize`. wk 0.9.5 has
  no segmentize filter, and an OGR VRT warped layer has no densify step.
- **The pipeline route drops a dependency.** Its stream is GDAL's generic
  Arrow stream, so geometry arrives as WKB (as decision 0002 found), and
  `geoarrow::geoarrow_writer()` encodes each batch in one C pass. GDAL's
  Arrow driver, and conda-forge's `libgdal-arrow-parquet`, are not needed.

## Consequences

- **GDAL sources.** aobcore's `gdal_vector_stream()` should gain a pipeline
  route, `read ! clip ! segmentize ! reproject ! write --of stream`, read
  batch by batch into native GeoArrow. It needs gdalraster 2.2 or later with
  GDAL 3.12 or later. The current `ogr2ogr` route stays as the fallback for
  older GDAL. This amends the producer in decision 0002's consequences; that
  record's encoding findings still stand.
- **In-memory inputs.** `vector_stream()` may take an optional `trans`, any
  `wk_trans`, applied with `wk_transform_filter()` in front of the geoarrow
  writer. Core Imports do not change: `wk_transform_filter()` is in wk, and
  the PROJ package goes in Suggests or the caller supplies the transform.
  When the view CRS is geographic, `trans` is refused with a message that
  points to the GDAL route.
- **Densify.** Until wk or PROJ has a segmentize filter, in-memory inputs
  are densified by the caller or through GDAL. A wk segmentize filter is an
  upstream candidate.
- **Domain clip.** Producers clip to the view CRS's valid area in the source
  CRS before reprojecting. A default from the view CRS's PROJ area of use is
  a candidate, not tested here.
- **Scene spec.** No change. 0.1 already requires vector coordinates in the
  view CRS, and reprojection stays in R. Reprojecting in the browser is left
  to globe and spinning views, after v1.
- **Transport.** Encoding per batch keeps open a later transport that sends
  batches as they are ready.
- Rules out a per-coordinate transform into a geographic view, and relying
  on PROJ to flag points outside the view's domain.
