"""Shortest paths on the walkway graph. Blocked edges are ignored."""
import networkx as nx

NO_ROUTE_MIN = 1e4  # travel time used in matrices for unreachable pairs


def build_graph(nodes, edges):
    """nodes: list of node dicts, edges: list of dicts with id/from/to/length_m/blocked."""
    g = nx.Graph()
    for n in nodes:
        g.add_node(n["id"])
    for e in edges:
        g.add_edge(e["from"], e["to"], id=e["id"], length=e["length_m"], blocked=bool(e["blocked"]))
    return g


def set_blocked(g, u, v, blocked):
    g[u][v]["blocked"] = blocked


def _open_view(g):
    return nx.subgraph_view(g, filter_edge=lambda u, v: not g[u][v]["blocked"])


def shortest_path(g, src, dst):
    """Returns (path_nodes_including_src, length_m) or None if no unblocked route exists."""
    if src == dst:
        return [src], 0.0
    try:
        path = nx.shortest_path(_open_view(g), src, dst, weight="length")
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
    return path, path_length(g, path)


def path_length(g, path):
    return sum(g[a][b]["length"] for a, b in zip(path, path[1:]))


def path_blocked(g, path):
    """True if any hop of the node list is blocked."""
    return any(g[a][b]["blocked"] for a, b in zip(path, path[1:]))


def travel_matrix(g, node_ids, speed_m_per_min):
    """Minutes between every pair of node_ids, in the order given (for optimize.plan_routes)."""
    lengths = dict(nx.all_pairs_dijkstra_path_length(_open_view(g), weight="length"))
    return [[(lengths[a][b] / speed_m_per_min) if b in lengths.get(a, {}) else NO_ROUTE_MIN
             for b in node_ids] for a in node_ids]
