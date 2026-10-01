# 0008: wk-first vector input, PROJ as the reprojection engine

- Date: 2026-10-01
- Status: accepted
- Issue: allboa/aobview#26
- Decided by: Michael (project thread, 2026-10-01)

## Question

What vector input does aobview accept, and what reprojects it? Until now
aobview took only `sf` and `sfc`, and `sf` did the CRS reading, transform,
densify and geometry housekeeping; a terra `SpatVector` went through
`sf::st_as_sf()`.

## Answer

aobview's vector input rallies on the 'wk' interop foundation: a bare
wk-handleable vector, or a data frame with a handleable column, with
`sf`, terra `SpatVector` and later GDAL readers as adapters onto those two.
PROJ (the R package) is the reprojection engine and is in aobview's
Imports; `sf` is an input type, not a dependency.

## Evidence

- aobcore was already wk-first: `vector_stream()` takes any handleable
  vector, a data frame with a handleable column, or a nanoarrow stream,
  and never reprojects. Only aobview depended on sf.
- Decision 0004's spike found `wk_transform()` with a PROJ transform
  agrees with `ogr2ogr` to the bit, at similar speed and memory.
- `terra::geom(x, wkb = TRUE)` into `wk::wkb()` is about 30 times faster
  than `sf::st_as_sf()` on terra's `lux.shp` (0.8 ms vs 23 ms per call,
  terra 1.9.50), and needs neither sf nor geos.
- Michael: sf's round trip through lists of matrices is at odds with
  wk's internal efficiency and the Arrow premise; binary availability on
  CRAN macOS is the same for PROJ, gdalraster, terra and sf, so it is not
  a reason to prefer sf.

## Consequences

- **Input contract.** Every vector input becomes one record: the geometry
  as wkb with its CRS (`wk_crs()`), and a plain data frame of the other
  columns (or none). A data frame's geometry column is sf's, else the
  first handleable column, else the one named by `geometry =`. Selections
  return rows of the object as given (`x[rows, ]` or `x[rows]`).
- **Engine.** PROJ in aobview Imports: `wk::wk_transform()` with
  `PROJ::proj_trans_create()`; lon/lat-ness and authority codes are read
  from PROJ's WKT2. gdalraster in Imports is also acceptable, and a
  `wk_trans` from gdalraster is a possible later engine. aobcore's
  Imports do not change (nanoarrow, geoarrow, wk, htmltools).
- **Densify.** A linear wk densify, `aobcore::vector_densify()`, as 0004
  proposed; no GDAL needed for in-memory data.
- **Topology is parked.** The transform is point by point: any CRS works,
  but nothing is cut at the antimeridian or the poles. This amends 0004's
  consequence that refuses a per-coordinate transform into a geographic
  view: aobview keeps its warning and draws, and cutting waits until a
  real case shows the need (Michael: see problems emerge before
  implementing solutions).
- **GDAL.** aobcore's non-Arrow fallback for older GDAL (macOS CRAN, about
  3.8) is untouched; the in-memory path does not use GDAL at all.
- **Todo.** `gdalraster::GDALVector$fetch()` output (a data frame whose
  geometry column is a list of raw WKB, wrapped as `wk::wkb(col, crs =)`)
  and nanoarrow streams (`GDALVector$getArrowStream()`, the ideal source)
  as inputs; a wk `grd` on the raster path rather than as polygon cells.
