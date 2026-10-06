# 0011: The input surface, and the two currencies the spec writes down

- Date: 2026-10-06
- Status: accepted
- Issue: allboa/design#22; Michael's response in the project thread,
  2026-10-06, to the input landscape response (a project document,
  "allonboard: input landscape response")
- Decided by: Michael (plan level: it sets the order of work ahead of
  decision 0010's spikes and adds a scene spec contract)

## Question

Given decision 0010's routes (R-planned and browser-resolved, with the chunk
reference as their shared currency), what does allonboard do first to be the
best available viewer in R and to join R data with external sources: which
inputs `view()` takes, where the shared contracts are written, and what is
asked of projects outside the org?

## Answer

allonboard widens `view()`'s front door before it runs 0010's spikes, and it
writes two currencies into scenespec: an Arrow stream with GeoArrow types for
explicit data, and a chunk-reference table for grids. Three points Michael
decided: the chunk-reference schema lives in scenespec first and moves to a
cross-language repo only once a second producer exists; `view("string")`
treats a character scalar as a data source, probed with gdalraster, with WKT
text still taken as geometry; and a time axis enters the spec with 0010 item
3 (the browser-resolved layer), not before.

## Evidence

- aobview dispatches on sf, wk handleables, data frames, terra objects and
  lists only (aobview `NAMESPACE`, `R/view.R`). It reads a
  `nanoarrow_array_stream` internally but offers no front door for one, so
  Arrow, DuckDB and `GDALVector$fetch()` results have no route in.
- A remote COG-backed `SpatRaster` is already referenced by URL rather than
  copied (`R/view-terra.R`); a URL string is not, and a remote VRT or WMS
  source is read into a temporary COG (`R/view-gdal.R`), which 0010 rules
  out for cloud data.
- Zarr and Kerchunk chunk references are arithmetic over plain JSON
  metadata, so R can plan them with jsonlite on any GDAL, including the
  GDAL 3.8 that CRAN's macOS binaries ship.
- The R landscape (mapview, leaflet, mapgl, rdeck, deckglgeoarrow, tmap)
  draws in Web Mercator or statically; none combines interactive GPU
  drawing, any projected CRS and cloud grids read in place. The cheapest
  way to be "best available" is to keep the data contracts identical to
  deckglgeoarrow's and lonboard's and differ only where a projected CRS
  demands it.
- Correction carried from Michael: `gdal mdim get-refs` is his parked
  draft PR to GDAL, not a shipped feature. GDAL extracts HDF5 byte
  references quickly inside the library; nothing exposes that in the CLI or
  application layer yet.

## Consequences

### Order of work, ahead of 0010's spikes

1. Front doors in aobview, no new Imports: URL and DSN strings
   (aobview#39), Arrow streams and tables, DuckDB results and `fetch()`
   output (aobview#40), a matrix or array with an extent and CRS
   (aobview#37).
2. stars and stars_proxy adapters, stars in Suggests (aobview#38).
3. Plan a VRT or GTI mosaic of COGs across its members, retiring the
   temporary-COG read for remote mosaics (aobview#41).
4. The two currencies in scenespec: a chunk-reference data format
   (scenespec#10) and the explicit-data contract (scenespec#11), each with
   fixtures. A time axis waits for 0010 item 3 (scenespec#9).
5. Decision 0010's items 1 to 5 as ordered there.

Items 1 to 3 are agent work under the review policy in the brief. Item 4
changes the spec and is reviewed the same way, but its shape (what a chunk
reference carries) is confirmed with Michael before the schema version is
cut.

### Asked of projects outside the org

These are Michael's to pick up or hand on; allonboard consumes their outputs
and does not block on them:

- an npm release of rangefinder's source modules (0010 item 3);
- a chunk-reference package in R with an Arrow table shape and producers
  for TIFF, Zarr metadata and Kerchunk, so rangefinder, sds and starc share
  it and aobcore depends on its schema only;
- the GDAL byte-reference draft PR, and a gdalraster accessor for it once it
  lands;
- a `wk_trans` provider in gdalraster;
- an R Icechunk binding;
- non-Mercator tile traversal in deck.gl-raster (decision 0003's six
  changes).

### What this changes and rules out

- **Charter.** Goals and non-goals unchanged. "A convenience package with a
  mapview-style `view(x)` for sf and terra" is read as `view(x)` for what
  an R user already holds, which now includes strings, Arrow streams,
  matrices and stars objects.
- **Scene spec.** Gains the two contracts above in their own versions. It
  stays renderer-neutral and reader-neutral; the chunk-reference format
  names codecs, not file formats.
- **R packages.** aobcore Imports unchanged. aobview adds nothing to
  Imports; arrow, duckdb and stars join Suggests only where tests need
  them.
- **Ruled out:** a `view()` that needs sf or terra to be installed; R
  copying a remote mosaic to draw it; a chunk-reference schema that only
  COGs can satisfy.
