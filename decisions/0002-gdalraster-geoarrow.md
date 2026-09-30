# 0002: gdalraster streams native GeoArrow from Arrow layers only

- Date: 2026-09-30
- Status: proposed
- Issue: allboa/spikes#2
- Decided by: agent

## Question

Can an OGR layer reach the browser as a native GeoArrow column
(`geoarrow.linestring` or `geoarrow.polygon`, not WKB) through gdalraster's
Arrow stream, with GDAL asked for GeoArrow encoding and no conversion in
between?

## Answer

Not as asked, for non-Arrow sources: they need one in-memory GDAL write to
the Arrow driver, then the stream is native GeoArrow. Arrow-stored layers
stream native GeoArrow directly. GDAL's generic
Arrow stream, which serves every driver without a native Arrow reader, emits
only WKB, and no stream option changes that. So the producer has two steps.
First, GDAL writes the layer to its Arrow driver in `/vsimem` with
`GEOMETRY_ENCODING=GEOARROW_INTERLEAVED`, in the same `ogr2ogr()` call that
clips and reprojects. Second, `GDALVector$getArrowStream()` streams that
dataset as native GeoArrow, and nanoarrow writes it to IPC bytes. When GDAL
should not re-encode, geoarrow converts the WKB stream in R before it leaves
R.

## Evidence

The code, screenshots and full output are in
[allboa/spikes `gdalraster-geoarrow/`](https://github.com/allboa/spikes/tree/spike-gdalraster-geoarrow/gdalraster-geoarrow)
(PR allboa/spikes#5). The test layer is the Natural Earth 50m coastline,
clipped south of 40S and drawn in EPSG:3031. Versions: R 4.5.3, GDAL 3.13.3,
libarrow 25.0.0, gdalraster 2.7.0, nanoarrow 0.8.0.1, geoarrow 0.4.4 and
wk 0.9.5, all from conda-forge.

- **GeoJSON source (generic stream).** With no options, the geometry column
  is `ogc.wkb`. With `GEOMETRY_METADATA_ENCODING=GEOARROW` it is
  `geoarrow.wkb`, still WKB. `GEOMETRY_ENCODING=GEOARROW` is not a stream
  option; GDAL ignores it silently. The only documented value,
  `GEOMETRY_ENCODING=WKB`, forces WKB on Arrow and Parquet layers.
- **Arrow driver source.** `ogr2ogr()` writes to `/vsimem/coast.arrows`
  with `-f Arrow -lco GEOMETRY_ENCODING=GEOARROW_INTERLEAVED`, together with
  `-clipsrc`, `-segmentize 0.25`, `-explodecollections -nlt LINESTRING` and
  `-t_srs EPSG:3031`. `GDALVector` on that dataset reports
  `FastGetArrowStream = TRUE`, and its stream has a `geoarrow.linestring`
  column with storage `List<FixedSizeList<double,2>>`.
  `nanoarrow::write_nanoarrow()` writes the stream to 162 KiB of IPC.
- **Browser.** apache-arrow 17 and deck.gl 9.1 read the IPC in headless
  Chromium. The check confirms extension `geoarrow.linestring` with
  `FixedSizeList[2]` vertices. deck.gl binds the `Float64Array` to a
  `PathLayer` in an `OrthographicView` and draws 170 lines and 9,887
  vertices
  ([screenshot](https://github.com/allboa/spikes/blob/spike-gdalraster-geoarrow/gdalraster-geoarrow/screenshot.png)).
- **R fallback.**
  `geoarrow::as_geoarrow_vctr(wkb, schema = geoarrow_multilinestring(coord_type = "INTERLEAVED"))`
  on the WKB stream, then `write_nanoarrow()`, gives native interleaved
  `geoarrow.multilinestring` IPC with PROJJSON in the field metadata. So
  nanoarrow and geoarrow in R can write browser IPC without WKB by either
  route.
- **Packaging.** The Arrow and Parquet drivers are not in conda-forge
  `libgdal-core`. They ship in the `libgdal-arrow-parquet` plugin, which
  pulls in libarrow. A GDAL build without them can only stream WKB.
- **CRS placement.** The fast Arrow-driver stream puts the CRS (WKT2) only
  in the schema-level `geo` metadata. The geometry field has no
  `ARROW:extension:metadata`, even with `GEOMETRY_METADATA_ENCODING=GEOARROW`.

## Consequences

- The design post's claim needs one qualifier. A gdalraster-to-browser path
  is conversion-free in R, but GDAL re-encodes any non-Arrow source once,
  in memory. Only Arrow IPC sources, and GeoParquet written with GeoArrow
  encoding, stream native GeoArrow as they are.
- The core's vector producer is `ogr2ogr()` to `/vsimem` with the Arrow
  driver and `GEOMETRY_ENCODING=GEOARROW_INTERLEAVED`, then
  `getArrowStream()`, then `write_nanoarrow()`. Clip, densify and reproject
  happen in the same GDAL call, with `-t_srs` set to the scene's view CRS
  (scene spec 0.1 requires vector coordinates in the view CRS), which fits "curvature is one sampling
  decision". gdalraster stays in Suggests. The geoarrow conversion is the
  fallback, and it keeps the core's Imports at nanoarrow, geoarrow, wk and
  htmltools.
- Use interleaved coordinates (`GEOARROW_INTERLEAVED`, or
  `coord_type = "INTERLEAVED"` in geoarrow). GDAL's default `GEOARROW` is
  the struct (separated) layout, which the probe renderer does not bind.
- The producer must check for the Arrow driver at run time (`"Arrow" %in%
  gdal_formats()$short_name`) and fall back to the geoarrow conversion when
  it is missing. conda-forge users need `libgdal-arrow-parquet`. The
  install docs should say so.
- The renderer and the scene spec must not rely on
  `ARROW:extension:metadata` for the CRS. The scene spec's view CRS is
  authoritative. If a layer CRS is ever needed, read the field metadata
  first, then the schema `geo` metadata.
- Rules out waiting for a GDAL stream option that emits GeoArrow from
  arbitrary drivers. GDAL 3.13 has none. If upstream adds one, this record
  is superseded, and the `/vsimem` step can be dropped.
