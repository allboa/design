# 0005: A default view domain from the projection's centre

- Date: 2026-09-30
- Status: accepted
- Issue: none; raised by Michael in the project thread on CRS input, implemented in allboa/scenespec#7 (0.4 `view.bounds`) and aobcore
- Decided by: Michael

## Question

A view CRS says nothing about how much of it is worth showing. Polar
stereographic runs to infinity at the far pole; Lambert azimuthal equal area
maps the whole Earth into a disc of radius 2R; orthographic stops at the
horizon. How should a scene get a sensible default view and a limit on
panning and zooming out (a "distance across the canvas" in CRS units), while
still letting data stream in from outside that view?

## Answer

Compute a **domain** for the view CRS from its centre: walk outward from the
projection centre along many bearings and stop, on each bearing, at the
first point where the projection fails or where it stretches distance along
the bearing by more than `k` times (default `k = 2`, an open choice). The
domain is the star-shaped region those end points enclose; its bounding box
in CRS units is the "distance across the canvas". A bounded projection
never meets the stretch limit and gets its natural edge (the LAEA disc, the
orthographic hemisphere); a divergent one is cut where it becomes
unreasonable (polar stereographic near the equator).

The domain sets two things and only two:

1. **The default view** when a scene gives no `view.extent`.
2. **The camera clamp**: how far the view may pan and zoom out.

It does **not** limit data. Tile plans and vector producers keep their own
rules (`cog_plan()`'s `max_stretch`, clip boxes), so data outside the
default view still loads when the camera goes there. Clipping data to the
domain is available only when asked for.

## How it looks

In R (aobcore), with names open to change:

```r
d <- crs_domain("EPSG:3031")          # k = 2
d$centre      # projection centre, lon/lat and CRS units
d$extent      # c(xmin, xmax, ymin, ymax) in CRS units
d$bounded     # TRUE when no bearing hit the stretch limit or a failure

s <- scene("EPSG:3031")                         # domain = TRUE: default view and clamp
s <- scene("EPSG:3031", domain = FALSE)         # neither, as today
s <- scene("EPSG:3031", domain = c(-4e6, 4e6, -4e6, 4e6))  # an explicit domain
s <- scene("EPSG:3031", domain = crs_domain("EPSG:3031", k = 4))
```

In the scene spec (0.4, additive): `view.bounds`, an extent in view CRS units
that the renderer keeps the camera within. Absent means no clamp, so every
existing scene is unchanged. `view.extent` stays the initial view. The name
is generic on purpose: it is a renderer-neutral "keep the camera here", not
a deck.gl setting.

The centre is the CRS's natural origin: the point `(false_easting,
false_northing)` inverse-projected to lon/lat, which is the pole for polar
CRSs and `(lon_0, lat_0)` for an azimuthal one. Bearings are geodesic
directions from that centre; at a pole they are meridians.

A geographic CRS (`OGC:CRS84`, `EPSG:4326`) is measured in degrees, so the
stretch rule does not apply; its domain is `[-180, 180] x [-90, 90]`.

## Evidence

Measured with gdalraster (GDAL 3.13.3, PROJ 9.9.0) on 72 bearings (5
degrees apart), walking each in 0.5 degree steps, WGS84. Radial stretch is
the projected length of each 0.5 degree step divided by its length on a
sphere of radius R. aobcore's `crs_domain()` divides by the first step on
each bearing instead (the centre's own scale), which needs no units: for
EPSG:3031, whose scale at the pole is 0.97, it stops at 91 degrees and
12.58e6 m rather than 92 and 12.8e6. Half widths
are in thousands of km (1e6 m); "reach" is the angular distance from the
centre where the walk stopped (min and max over bearings).

| CRS | k = 2 half width x, y | reach | k = 4 half width x, y | reach |
| --- | --- | --- | --- | --- |
| EPSG:3031 polar stereographic S | 12.8, 12.8 | 92 | 21.8, 21.8 | 121 |
| EPSG:3413 polar stereographic N | 12.8, 12.8 | 92 | 21.9, 21.9 | 121.5 |
| LAEA south pole | 12.7, 12.7 | 179.5 (bounded) | same | same |
| LAEA 147E 42S | 12.8, 12.7 | 179.5 (bounded) | same | same |
| Azimuthal equidistant S | 20.0, 20.0 | 180 (bounded) | same | same |
| Orthographic S | 6.4, 6.4 | 90 (fails past horizon) | same | same |
| Gnomonic S | 6.4, 6.4 | 45 | 11.0, 11.0 | 60 |
| EPSG:3857 Web Mercator | 20.0, 8.4 | 60 to 180 | 20.0, 13.2 | 75.5 to 180 |
| Mollweide | 18.0, 9.0 | 89.5 to 180 (bounded) | same | same |
| EPSG:32755 UTM 55S | 8.4, 20.0 | 59.5 to 180 | 13.2, 20.0 | 75 to 180 |

So `k = 2` puts the edge of a 3031 view just past the equator (about 2N),
Web Mercator at 60N/60S, and leaves every bounded projection whole. `k = 4`
gives 3031 about 31N and Web Mercator 75.5N. For comparison, the familiar
Web Mercator cut at 85.05N is `k` of about 11.6.

Radial stretch alone is what makes LAEA "bounded": its stretch across the
bearing does grow toward the antipode, but it only squeezes the outer ring
of the disc, it does not push the edge outward.

## Choices (decided by Michael, 2026-09-30)

1. **`k`**: 2 (3031 to the equator, Mercator to 60 degrees) or 4 (3031 to
   about 30N, Mercator to 75 degrees). Proposed: 2.
2. **Default view with data**: when a scene has data but no `extent`, is the
   default view the domain, or the data's footprint clipped to the domain?
   Proposed: the data's footprint clipped to the domain (what `view_cog()`
   does today, now with a ceiling), and the domain when there is no data.
3. **Clamp on by default?** Proposed: yes, clamped to the domain (with the
   camera allowed to show a margin of a quarter of the domain's width
   beyond it, so the edge can be seen). `domain = FALSE` turns it off; an
   explicit extent replaces it.
4. **Data outside the domain**: loaded as the camera reaches it (only
   possible when the clamp is off or larger than the domain), or never
   planned. Proposed: loaded; `cog_plan()` and `gdal_vector_stream()` keep
   their own limits and do not cull to the domain unless given it as
   `extent` or `clip`.
5. **Spec shape**: `view.bounds` as a plain extent (proposed), or a
   polygon so the clamp can follow the star-shaped domain (a disc for LAEA)
   rather than its bounding box.

Michael took the proposed option on all five: `k = 2`; the default view is
the data footprint clipped to the domain (the domain when there is no
data); the clamp is on by default with a quarter-width margin; data outside
the domain still loads; and `view.bounds` is a plain extent (scene spec
0.4, allboa/scenespec).

## Consequences

- aobcore gains `crs_domain()` and a `domain` argument to `scene()`; the
  renderer honours `view.bounds` and replaces today's fixed `minZoom = z - 4`
  with the zoom at which the bounds fill the canvas.
- scenespec 0.4 adds optional `view.bounds`; no existing scene changes.
- `cog_plan()`'s `max_stretch` stays as the data-side rule. A later record
  may let the domain replace it for tile culling, since both measure the
  same stretch, but that is not part of this decision.
- Rules out clipping data to the default view by default.
