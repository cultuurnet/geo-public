"""Build FeatureCollections from a bq json dump at several coordinate precisions.

Rounding can make consecutive points identical or shrink a ring below 4
points; duplicates are dropped and degenerate rings/polygons removed.
usage: python3 -I round_geojson.py <rows.json> <out_prefix> <decimals>...
"""
import json
import sys

PROPS = ("statisticalsector_nis9", "statisticalsector_name_nl",
         "statisticalsector_name_fr", "statisticalsector_name_de",
         "municipalsection_nis6")


def clean_ring(ring, d):
    out = []
    for lon, lat in ring:
        p = [round(lon, d), round(lat, d)]
        if not out or p != out[-1]:
            out.append(p)
    if out[0] != out[-1]:
        out.append(out[0])
    return out if len(out) >= 4 else None


def clean_geometry(geom, d):
    polygons = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
    kept = []
    for poly in polygons:
        exterior = clean_ring(poly[0], d)
        if exterior:
            kept.append([exterior] + [h for h in (clean_ring(r, d) for r in poly[1:]) if h])
    if not kept:
        return None
    return {"type": "Polygon", "coordinates": kept[0]} if len(kept) == 1 else \
           {"type": "MultiPolygon", "coordinates": kept}


rows = json.load(open(sys.argv[1]))
prefix = sys.argv[2]
print(f"bq-side collapsed (fell back to raw): {sum(r['collapsed'] == 'true' for r in rows)}")
for d in map(int, sys.argv[3:]):
    features, lost = [], []
    for r in rows:
        geom = json.loads(r["geometry"])
        cleaned = clean_geometry(geom, d)
        if cleaned is None:  # rounding destroyed it: keep unrounded shape
            lost.append(r["statisticalsector_nis9"])
            cleaned = geom
        features.append({"type": "Feature",
                         "properties": {k: r.get(k) for k in PROPS},
                         "geometry": cleaned})
    path = f"{prefix}_{d}dec.geojson"
    with open(path, "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    pts = sum(len(ring) for ft in features for poly in
              (ft["geometry"]["coordinates"] if ft["geometry"]["type"] == "MultiPolygon"
               else [ft["geometry"]["coordinates"]]) for ring in poly)
    import os
    print(f"{d} dec: {os.path.getsize(path)/1e6:7.2f} MB  points {pts:,}  destroyed by rounding {len(lost)}")
