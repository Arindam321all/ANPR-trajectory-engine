"""
Generate a GeoJSON file of the road network for a ~1km x 1km area
around Connaught Place, New Delhi, India using OSMnx.

The exported GeoJSON is consumed by the Leaflet-based map in index.html.

Usage:
    python generate_map.py
"""

import json
import os

import osmnx as ox

# ─── Configuration ──────────────────────────────────────────────────
# Centre: Connaught Place, New Delhi
CENTER_LAT = 28.6315
CENTER_LNG = 77.2167
DIST_METERS = 2500  # ~2500 m radius → roughly 5 km × 5 km bounding box

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
GEOJSON_FILE = os.path.join(OUTPUT_DIR, "data", "road_network.geojson")
GRAPHML_FILE = os.path.join(OUTPUT_DIR, "data", "road_network.graphml")


def main():
    print(f"Downloading road network around ({CENTER_LAT}, {CENTER_LNG}), "
          f"radius={DIST_METERS} m ...")

    # Download drivable road network from OpenStreetMap
    G = ox.graph_from_point(
        (CENTER_LAT, CENTER_LNG),
        dist=DIST_METERS,
        network_type="drive",
    )

    print(f"  Nodes: {G.number_of_nodes()}, Edges: {G.number_of_edges()}")

    # Convert edges to GeoDataFrame → GeoJSON
    _, edges_gdf = ox.graph_to_gdfs(G)

    # Keep only useful columns to keep the file small
    keep_cols = ["geometry", "name", "highway", "length"]
    available = [c for c in keep_cols if c in edges_gdf.columns]
    edges_gdf = edges_gdf[available].copy()

    # Ensure output directory exists
    os.makedirs(os.path.dirname(GEOJSON_FILE), exist_ok=True)

    # Write GeoJSON
    edges_gdf.to_file(GEOJSON_FILE, driver="GeoJSON")
    size_kb = os.path.getsize(GEOJSON_FILE) / 1024
    print(f"[OK] Saved road network to {GEOJSON_FILE}  ({size_kb:.1f} KB)")

    # Save GraphML for routing engine
    ox.save_graphml(G, filepath=GRAPHML_FILE)
    print(f"[OK] Saved graphml to {GRAPHML_FILE}")

    # Also write a small metadata JSON so the HTML page knows the centre/zoom
    meta = {
        "center": [CENTER_LAT, CENTER_LNG],
        "radius_m": DIST_METERS,
        "locality": "Connaught Place, New Delhi, India",
        "default_zoom": 16,
    }
    meta_file = os.path.join(OUTPUT_DIR, "data", "map_meta.json")
    with open(meta_file, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"[OK] Saved metadata to {meta_file}")


if __name__ == "__main__":
    main()
