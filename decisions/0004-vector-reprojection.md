# 0004: GDAL reprojects what it reads; wk + PROJ for data already in R

- Date: 2026-09-30
- Status: proposed (its geographic-view refusal amended by 0008)
- Issue: allboa/spikes#8
- Decided by: agent

## Question

When vector data must reach the view CRS, should GDAL reproject it as it
streams from the source (virtual, on the fly), or should R transform it in
memory with a wk handler fed by a PROJ transform
(`PROJ::proj_trans_create()` into `wk::wk_transform()`)?

## Answer

Both, split by input: GDAL clips, densifies and reprojects anything it reads,
lazily, and R encodes each batch as native GeoArrow; data already in R may
take any `wk_trans` in the same encoding pass, into a projected view CRS.
Neither route handles the view's domain or seams, so producers clip in the
source CRS first.

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

- **Coordinates are identical where the routes do the same work.** All
  routes call the same PROJ. On a 2,772,032 vertex 10m coastline, lon/lat
  into EPSG:3031, all five agree to the bit. On the 50m coastline the three
  routes that densify agree to the bit. On the 50m land, `ogr2ogr` and
  `wk_transform()` agree to the bit.
- **Speed and memory barely differ.** At 2.8 million vertices every route
  took 1.5 to 3.2 seconds, with the order changing between runs, and peaked
  at 317 to 457 MB above baseline for 42 MB of IPC. The current producer
  peaks highest because it writes the IPC and reads it back. The embed
  transport needs the whole blob, so streaming the input saves little.
- **GDAL cuts at 180 degrees only into a lon/lat target.** From EPSG:3031
  into lon/lat, `ogr2ogr` and `gdal vector reproject` split a line at the
  antimeridian and close a ring around the south pole, by default.
  `wk_transform()` draws the line across the map and returns a wrong ring.
  Into EPSG:3857 and Equal Earth (EPSG:8857), whose seam is at 180 degrees,
  neither route splits the line. Only a polar source was tested.
- **No method guards the view's domain.** The north pole into EPSG:3031
  comes back as y = 4.0e23, a finite number, from GDAL and PROJ alike.
- **Densifying is GDAL-only.** GDAL segmentizes lazily in the pipeline or in
  `ogr2ogr -segmentize`. wk 0.9.5 has no segmentize filter, and an OGR VRT
  warped layer has no densify step.
- **The pipeline route drops a dependency.** Its stream is GDAL's generic
  Arrow stream, so geometry arrives as WKB (as decision 0002 found), and
  `geoarrow::geoarrow_writer()` encodes each batch in one C pass. With
  GDAL's Arrow and Parquet drivers switched off (`GDAL_SKIP`) it gives the
  same 1.1 MB of IPC.

## Consequences

- **GDAL sources.** aobcore's `gdal_vector_stream()` should gain a pipeline
  route, `read ! clip ! segmentize ! reproject ! write --of stream`, read
  batch by batch into native GeoArrow. The `clip` step was not run here. By
  the documentation it needs gdalraster 2.2 or later with GDAL 3.12 or later
  for `segmentize`; only gdalraster 2.7.0 with GDAL 3.13.3 was tested. This
  amends the producer in decision 0002's consequences; that record's
  encoding findings still stand. If 0002 is accepted first, read this as
  superseding its producer paragraph.
- **Older GDAL is the common case on macOS.** Michael reports (2026-09-30)
  that CRAN's Windows binaries carry GDAL 3.12, but CRAN's macOS binaries
  were still at GDAL 3.8 when he last looked. gdalraster is now on
  conda-forge, but GDAL on macOS remains an open problem. So the fallback
  is a first-class route, not an edge case. On GDAL older than 3.12, GDAL
  streams the source layer in its own CRS through the generic Arrow stream
  (GDAL 3.6 or later), and R densifies, transforms and encodes each batch in
  one wk pass (a densify filter, then `wk_transform_filter()`, then the
  geoarrow writer). wk has no clip filter either, and GDAL's spatial filter
  selects features without cutting them. So until wk has densify and clip
  filters, the current `ogr2ogr` route (a `/vsimem` GeoPackage, `-clipsrc`,
  `-segmentize`, `-t_srs`) is used whenever a clip or densify is needed.
  The wk route inherits the per-coordinate limits below, so a lon/lat view
  still needs GDAL's own reprojection. The generic stream plus
  `wk_transform_filter()` part matches the spike's `wk_proj_stream` route,
  which ran only on GDAL 3.13.3; neither it nor a densify step has been run
  on GDAL 3.8.
- **In-memory inputs.** `vector_stream()` may take an optional `trans`, any
  `wk_trans`, applied with `wk_transform_filter()` in front of the geoarrow
  writer. Core Imports do not change: `wk_transform_filter()` is in wk, and
  the PROJ package goes in Suggests or the caller supplies the transform.
  When the view CRS is geographic, `trans` is refused with a message that
  points to the GDAL route, which cuts at the antimeridian and poles.
- **Densify.** A densify filter in wk is the default home (Michael,
  2026-09-30), to be revisited. Plain linear densifying in the source CRS
  comes first. Geodesic densifying (s2) and adaptive resampling in the view
  CRS (as in D3's projection resampling, bigcurve) are the contenders. Until
  the filter exists, in-memory inputs are densified by the caller or through
  GDAL. A wk clip filter is open work alongside it.
- **Domain clip.** Producers clip to the view CRS's valid area in the source
  CRS before reprojecting, on every route. A default from the view CRS's
  PROJ area of use is a candidate, not tested here.
- **Seams.** A projected view with a seam inside the data (Web Mercator,
  Equal Earth) needs the data cut at the seam before reprojecting, and
  neither route does it. The area-of-use clip does not help: Equal Earth's
  area of use is the whole world. Polar stereographic views, clipped to
  their hemisphere, have no seam, so v1 is not blocked. Seam cutting for
  other views is open work.
- **Scene spec.** No change. 0.1 already requires vector coordinates in the
  view CRS, and reprojection stays in R. Reprojecting in the browser is left
  to globe and spinning views, after v1.
- **Transport.** Encoding per batch keeps open a later transport that sends
  batches as they are ready.
- Rules out a per-coordinate transform into a geographic view, and relying
  on PROJ or GDAL to flag points outside the view's domain or to cut at a
  projected view's seam.
