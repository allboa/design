# 0012: Renderer reprojection of vector data, as an optional capability (scene spec 0.8)

- Date: 2026-11-03
- Status: proposed (draft now, build after deck.gl v10 betas are on npm)
- Issue: allboa/scenespec#17
- Decided by: Michael (plan level: it relaxes a rule of the explicit-data
  contract, decision 0011). He chose "draft now, build later" in the project
  thread on 2026-11-03.

## Question

deck.gl's v10 line now accepts PROJJSON as a layer's `coordinateSystem` and
gives a viewport its own CRS, with reprojection done by math.gl. Should the
scene spec let a vector table arrive in a CRS other than the view's and have
the renderer reproject it, and if so, on what terms?

## Answer

Yes, as an opt-in per vector data reference in scene spec 0.8: a data
reference may say `"reproject": "renderer"`, and its geometry may then be in
any CRS the scene names, for a `projected` view. The producer default does not change: R transforms with PROJ, as
decision 0004 says, and a scene that does not opt in is drawn exactly as
today. A renderer that cannot reproject reports an error for that layer and
draws the rest; so does one whose engine cannot run the data's CRS (math.gl
implements a set of projection families, not every EPSG code). Nothing is built until deck.gl v10 betas with this work are
published on npm.

## Evidence

The landscape review of 2026-11-03 (a project document, "scenespec and the
new deck.gl CRS work") and these upstream records:

- [visgl/deck.gl#10894](https://github.com/visgl/deck.gl/pull/10894), merged
  2026-10-23: `coordinateSystem` accepts PROJJSON and other math.gl CRS
  definitions; CRS equality is centralised, so an equivalent definition does
  not re-project geometry.
- [visgl/deck.gl#10872](https://github.com/visgl/deck.gl/pull/10872), open:
  the base `Viewport` gets a `crs` and no longer assumes Web Mercator.
  Review found that drawing in the plain CRS mode still throws.
These states were read from the pull request pages on 2026-11-03.

- [visgl/math.gl#251](https://github.com/visgl/math.gl/pull/251), merged
  2026-10-15: `CRSDescriptor`, with rendering bounds from the CRS area of use.
- [visgl/deck.gl#10835](https://github.com/visgl/deck.gl/pull/10835) and its
  two follow-ups, open: source units from the declared CRS, and subdivision
  of path and polygon rings so long edges follow the projection.
- wxylib's watch note on the same work
  ([wxylib/design `docs/watch/visgl.md`](https://github.com/wxylib/design/blob/main/docs/watch/visgl.md))
  records math.gl#368 (open, an example so far) driving raster mesh
  refinement with proj-wasm, so a browser engine with PROJ's own answers is
  in reach, not only proj4js. The same note has deck.gl#10874 (CRS strings
  in `coordinateSystem`) open as of 2026-11-01; #10894 is the PROJJSON form
  that landed.
- The scene spec already writes CRSs in the two forms deck.gl now accepts
  (`authority:code` and PROJJSON), so no new CRS syntax is needed.

## The 0.8 terms

0.8 is 0.7 plus one data reference property. Every 0.7 construct is
unchanged.

- **`reproject`** on a vector data reference (one with a `geometry`):
  `producer` (the default, and the only behaviour before 0.8) or `renderer`.
  It sits on the data reference, beside `geometry.crs` and
  `origin_subtracted`, so every layer that draws the table agrees. Mesh
  layers (0.7) and raster values are not vector references and cannot set
  it: their tables carry no CRS.
- **With `renderer`**, the view must be `projected` with a `crs`. A
  `cartesian` view and a `globe` view do not take it: 0004 already leaves a
  globe view's reprojection to the renderer, and this record does not change
  that. The data reference must give `geometry.crs`, in either CRS form, and
  the Arrow column's `crs` must match it by the existing rule (equal JSON,
  or one authority code names both). It need not match `view.crs`. With
  `producer`, the rule from 0.1 stands: the data are in the view CRS.
- **Clipping stays with the producer.** As decision 0004 says, the producer
  clips in the source CRS to the area where the view CRS is valid (its area
  of use) before writing. This is 0004's clip, not 0005's view domain, which
  limits the camera and not the data. A producer without PROJ clips to the
  view CRS's area of use as a lon/lat box, which the scene's CRS carries
  (PROJJSON `bbox`). The validator cannot check a clip; a renderer drops
  any vertex that projects to a non-finite position, reports how many, and
  is not required to cut at a seam or a pole.
- **Edges.** Edges remain planar in the source CRS. A renderer subdivides
  long edges so that a drawn line or ring stays within the conformance
  tolerance below, with upstream subdivision (deck.gl#10835 series) when it
  lands, or its own until then.
- **Precision.** `local_origin` applies to view coordinates, after
  reprojection. `origin_subtracted: true` is not allowed on a layer with
  `reproject: renderer`, since its coordinates are not in view units.
- **Popups, legends and colour columns** are unchanged: they read columns,
  not coordinates.
- **Rasters are out of scope.** Tiled rasters keep their producer plan
  (0.2, 0.6), and a raster source without a plan belongs with decision 0010
  item 3 and allboa/scenespec#9, not here.
- **No engine is named.** The spec states the tolerance, not the library, so
  a renderer may use proj4js, proj-wasm or anything else that meets it.

## Conformance

- A conformance scene per geometry kind in lon/lat (EPSG:4326), drawn in
  EPSG:3031 with `reproject: renderer`, with lines that cross the
  antimeridian inside the clipped domain and approach the pole.
- **Reference**: the same data transformed and densified by R (PROJ, as
  aobcore does), written as a `producer` scene with the same view.
- **Tolerance**: both scenes are rendered at 900 x 900 CSS pixels, device
  pixel ratio 1, camera fitted to the view's `extent`, layers drawn as 1 px
  lines and point outlines with no antialiasing of the mask (pixels
  thresholded against the background). Every drawn pixel of each mask lies
  within 1 pixel of a drawn pixel of the other (symmetric distance at most
  1 px). Polygons are checked by their rings.
- The check runs as a probe in allboa/spikes `probes/`, like the 0001 probe:
  a version matrix against deck.gl releases, weekly in CI. Its first job is
  the gate below.

## Gate

Build starts when all of these hold, checked by the probe:

1. A deck.gl v10 prerelease on npm includes #10894 (PROJJSON
   `coordinateSystem`).
2. A flat view whose CRS is EPSG:3031 draws a vector layer in that release
   (the plain CRS mode that #10872's review found throwing). Draws means the
   0001 probe's criterion: 90 percent or more of sample points on the data
   are not background.
3. The tolerance check passes for points, lines and polygons, with upstream
   subdivision or the renderer's own.

Until then aobcore's renderer stays on deck.gl 9.4 with an `OrthographicView`
and `CARTESIAN` coordinates (decision 0001).

## Consequences

- **scenespec**: a 0.8 schema, fixtures with `reproject: renderer`, a
  validator rule for `geometry.crs` and `origin_subtracted`, and the
  explicit-data contract's CRS paragraph updated to say "in the view CRS,
  unless the data reference says `renderer`". Schema descriptions name no
  renderer or its props (`check-terms.js` holds).
- **aobcore**: R keeps transforming by default. A scene may opt in when the
  data are already lon/lat and very large, or come from a producer that has
  no PROJ (DuckDB, a browser-resolved source), which is the route decision
  0010 opens.
- **Rules out**: a renderer-side reprojection that is silent. A layer
  either declares it or its data are in the view CRS.
- Two definitions of "correct" now exist (PROJ in R, the renderer's engine
  in the browser). The tolerance test is what keeps them one.
