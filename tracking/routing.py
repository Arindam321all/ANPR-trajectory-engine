import os
from pathlib import Path
import osmnx as ox
import networkx as nx

GRAPH_PATH = Path(__file__).parent.parent / "map" / "data" / "road_network.graphml"

_G = None

def get_graph():
    global _G
    if _G is None and GRAPH_PATH.exists():
        _G = ox.load_graphml(GRAPH_PATH)
    return _G

def get_optimistic_route(lat1, lon1, lat2, lon2):
    """
    Finds the shortest path between two points on the road network graph.
    Returns: (list_of_coordinates_for_geojson, distance_in_km)
    """
    G = get_graph()
    if not G:
        return None, 0.0

    try:
        # nearest_nodes takes X(lon) and Y(lat)
        orig_node = ox.distance.nearest_nodes(G, X=lon1, Y=lat1)
        dest_node = ox.distance.nearest_nodes(G, X=lon2, Y=lat2)

        if orig_node == dest_node:
            return [[lon1, lat1], [lon2, lat2]], 0.0

        # Shortest path by physical length
        route = nx.shortest_path(G, orig_node, dest_node, weight='length')
        
        # Calculate distance
        distance_km = 0.0
        for i in range(len(route) - 1):
            u = route[i]
            v = route[i + 1]
            # networkx MultiDiGraph edge access
            distance_km += G[u][v][0]['length']
        distance_km /= 1000.0
        
        # Convert route nodes to GeoJSON coordinates (lon, lat)
        coords = [[G.nodes[n]['x'], G.nodes[n]['y']] for n in route]
        return coords, distance_km
    except Exception as e:
        print(f"Routing error: {e}")
        return None, 0.0
