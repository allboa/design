# Stand-in for the R side of the design: produce GeoArrow tables, a
# pre-projected raster mesh, and a scene spec for a polar (EPSG:3031) view.
# Everything is projected here, so the browser only binds buffers.
import base64, io, json, math, urllib.request
import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc
from pyproj import CRS, Transformer
from shapely.geometry import shape, box, LineString, MultiLineString
from shapely import segmentize

NE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
LAT_LIMIT = -40.0          # northern edge of the view, degrees
tr = Transformer.from_crs("EPSG:4326", "EPSG:3031", always_xy=True)
crs_json = json.loads(CRS("EPSG:3031").to_json())
clip = box(-180, -90, 180, LAT_LIMIT)

def fetch(name):
    with urllib.request.urlopen(NE + name) as r:
        return json.load(r)

def proj(coords):
    a = np.asarray(coords, dtype=float)
    x, y = tr.transform(a[:, 0], a[:, 1])
    return np.column_stack([x, y])

def geoarrow_type(kind):
    # interleaved native encoding: FixedSizeList<double, 2> at the leaf
    pt = pa.list_(pa.field("xy", pa.float64()), 2)
    if kind == "linestring":
        storage = pa.list_(pa.field("vertices", pt))
    else:
        storage = pa.list_(pa.field("rings", pa.list_(pa.field("vertices", pt))))
    return storage

def geo_field(kind):
    meta = {b"ARROW:extension:name": ("geoarrow." + kind).encode(),
            b"ARROW:extension:metadata": json.dumps({"crs": crs_json}).encode()}
    return pa.field("geometry", geoarrow_type(kind), metadata=meta)

def to_ipc(table):
    sink = io.BytesIO()
    with ipc.new_stream(sink, table.schema) as w:
        w.write_table(table, max_chunksize=table.num_rows or 1)
    return sink.getvalue()

# ---- land: polygons, exterior rings only (holes dropped for the fill) ----
land_rings = []
for f in fetch("ne_50m_land.geojson")["features"]:
    g = shape(f["geometry"]).intersection(clip)
    if g.is_empty:
        continue
    g = segmentize(g, 0.25)            # densify before projecting
    polys = getattr(g, "geoms", [g])
    for p in polys:
        if p.geom_type != "Polygon" or p.area == 0:
            continue
        land_rings.append([proj(p.exterior.coords).tolist()])

land = pa.table({"geometry": pa.array(land_rings, type=geoarrow_type("polygon"))})
land = land.cast(pa.schema([geo_field("polygon")]))

# ---- coastline: lines (the land polygons close through the pole, so the
# outline must come from a line dataset, not from polygon rings) ----
coast_lines = []
for f in fetch("ne_50m_coastline.geojson")["features"]:
    g = shape(f["geometry"]).intersection(clip)
    if g.is_empty:
        continue
    g = segmentize(g, 0.25)
    for ln in getattr(g, "geoms", [g]):
        if ln.geom_type == "LineString" and len(ln.coords) > 1:
            coast_lines.append(proj(ln.coords).tolist())

coast = pa.table({"geometry": pa.array(coast_lines, type=geoarrow_type("linestring"))})
coast = coast.cast(pa.schema([geo_field("linestring")]))

# ---- graticule with a style column: RGBA computed "in R" ----
grat, colors = [], []
for lon in range(-180, 180, 30):
    lats = np.linspace(-90, LAT_LIMIT, 101)
    grat.append(proj(np.column_stack([np.full_like(lats, lon), lats])).tolist())
    colors.append([120, 140, 160, 150])
for lat in (-40, -50, -60, -70, -80):
    lons = np.linspace(-180, 180, 721)           # densified: 0.5 degree steps
    grat.append(proj(np.column_stack([lons, np.full_like(lons, lat)])).tolist())
    colors.append([120, 140, 160, 220] if lat == -60 else [120, 140, 160, 150])
graticule = pa.table({
    "geometry": pa.array(grat, type=geoarrow_type("linestring")),
    "color": pa.array(colors, type=pa.list_(pa.uint8(), 4)),
})
graticule = graticule.cast(pa.schema([geo_field("linestring"),
                                      pa.field("color", pa.list_(pa.uint8(), 4))]))

# ---- raster: a synthetic lon/lat field (stand-in for OISST) ----
# grid descriptor: extent, dim, crs; values row 0 = northernmost row
NX, NY = 360, 50
lon_c = -180 + 0.5 + np.arange(NX)
lat_c = LAT_LIMIT - 0.5 - np.arange(NY)
LON, LAT = np.meshgrid(lon_c, lat_c)
t = (LAT + 90) / (LAT_LIMIT + 90)
field = -1.8 + 14 * t ** 1.6 + 1.6 * np.sin(np.radians(LON) * 3 + t * 4) * np.sin(math.pi * t)
field = field.astype(np.float32)

# mesh in SOURCE space: every vertex projected on this side, uv carries curvature
MX, MY = 181, 51                                   # 2 deg lon x 1 deg lat
mlon = np.linspace(-180, 180, MX)
mlat = np.linspace(LAT_LIMIT, -90, MY)
MLON, MLAT = np.meshgrid(mlon, mlat)
mx, my = tr.transform(MLON.ravel(), MLAT.ravel())
pos = np.column_stack([mx, my, np.zeros_like(mx)]).astype(np.float32)
uv = np.column_stack([(MLON.ravel() + 180) / 360,
                      (LAT_LIMIT - MLAT.ravel()) / (LAT_LIMIT + 90)]).astype(np.float32)
idx = []
for j in range(MY - 1):
    for i in range(MX - 1):
        a = j * MX + i; b = a + 1; c = a + MX; d = c + 1
        idx += [a, c, b, b, c, d]
idx = np.asarray(idx, dtype=np.uint32)

mesh = pa.table({
    "position": pa.FixedSizeListArray.from_arrays(pa.array(pos.ravel()), 3),
    "uv": pa.FixedSizeListArray.from_arrays(pa.array(uv.ravel()), 2),
})
indices = pa.table({"index": pa.array(idx)})
values = pa.table({"value": pa.array(field.ravel())})

blobs = {"land": to_ipc(land), "coast": to_ipc(coast), "graticule": to_ipc(graticule),
         "sst_mesh": to_ipc(mesh), "sst_index": to_ipc(indices), "sst_values": to_ipc(values)}

scene = {
    "version": "0.0.1",
    "crs": "EPSG:3031",
    "view": {"type": "orthographic", "center": [0, 0], "extent_m": 2 * float(max(np.abs(mx).max(), np.abs(my).max()))},
    "layers": [
        {"id": "sst", "type": "raster-mesh", "label": "Synthetic SST-like field",
         "mesh": "sst_mesh", "indices": "sst_index", "values": "sst_values",
         "grid": {"crs": "EPSG:4326", "extent": [-180, 180, -90, LAT_LIMIT], "dim": [NX, NY]},
         "palette": {"name": "ocean", "range": [-2, 13]}},
        {"id": "land", "type": "polygon", "label": "Land (50m)", "data": "land",
         "fill": [218, 213, 202, 255]},
        {"id": "graticule", "type": "path", "label": "Graticule", "data": "graticule",
         "color": {"column": "color"}, "width_px": 1},
        {"id": "coast", "type": "path", "label": "Coastline (50m)", "data": "coast",
         "color": [60, 66, 72, 255], "width_px": 1},
    ],
}

out = {k: base64.b64encode(v).decode("ascii") for k, v in blobs.items()}
json.dump({"scene": scene, "blobs": out}, open("bundle.json", "w"))
for k, v in blobs.items():
    print(f"{k:12s} {len(v)/1024:8.1f} KiB")
print("land polys", len(land_rings), "coast lines", len(coast_lines), "mesh verts", len(pos), "tris", len(idx)//3)
