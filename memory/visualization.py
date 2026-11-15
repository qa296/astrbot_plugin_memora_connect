"""
记忆图谱：prepare_graph_data 构造节点/边数据（形状兼容 v1 前端）；
generate_graph_image 惰性导入 networkx + matplotlib 渲染 PNG，缺失时返回 None。
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from ..domain.models import CATEGORY_NAMES

_EMPTY_ERROR = "记忆图谱为空, 无法生成图谱"

# 类别 → 绘图颜色
_CATEGORY_COLORS = {
    "person": "#e74c3c",
    "place": "#3498db",
    "object": "#2ecc71",
    "action": "#f39c12",
    "trait": "#9b59b6",
}


def _element_stats(repo, elements) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {}
    for elem in elements:
        mems = repo.get_element_memories(elem.id, limit=100)
        count = len(mems)
        strengths = [float(m.strength or 0.0) for m in mems]
        stats[elem.id] = {
            "count": count,
            "avg_strength": (sum(strengths) / count) if count else 0.0,
            "max_strength": max(strengths) if strengths else 0.0,
        }
    return stats


def prepare_graph_data(
    repo,
    scope_id: str,
    max_nodes: int = 200,
    max_edges: int = 800,
) -> dict[str, Any]:
    """构造与 v1 前端兼容的图数据。"""
    elements = repo.list_elements(scope_id)
    if not elements:
        return {"error": _EMPTY_ERROR}
    stats = _element_stats(repo, elements)
    if not any(s["count"] for s in stats.values()):
        return {"error": _EMPTY_ERROR}

    ranked = sorted(elements, key=lambda e: stats.get(e.id, {}).get("count", 0), reverse=True)
    selected = ranked[:max_nodes]
    selected_ids = {e.id for e in selected}

    nodes_data = []
    for elem in selected:
        st = stats.get(elem.id, {"count": 0, "avg_strength": 0.0, "max_strength": 0.0})
        cat_name = CATEGORY_NAMES.get(elem.category, elem.category)
        nodes_data.append(
            {
                "id": elem.id,
                "name": f"{elem.name}({cat_name})",
                "count": st["count"],
                "avg_strength": st["avg_strength"],
                "max_strength": st["max_strength"],
                "category": elem.category,
            }
        )

    edges_data = []
    for conn in repo.list_connections(scope_id):
        if conn["from_element"] not in selected_ids or conn["to_element"] not in selected_ids:
            continue
        edges_data.append(
            {
                "from_element": conn["from_element"],
                "to_element": conn["to_element"],
                "strength": 1.0,
                "relation": conn.get("relation", ""),
            }
        )
        if len(edges_data) >= max_edges:
            break

    return {"nodes": nodes_data, "edges": edges_data, "group_id": scope_id, "error": None}


def _layout_positions(G, layout_style: str) -> dict:
    import networkx as nx

    style = (layout_style or "auto").strip()
    try:
        if style == "circular":
            return nx.circular_layout(G)
        if style == "kamada_kawai":
            return nx.kamada_kawai_layout(G)
        if style == "spectral":
            return nx.spectral_layout(G)
        if style == "hierarchical":
            pos = nx.spring_layout(G, seed=42, k=1.2)
            # 按类别分层：person 顶部、place 底部，其余居中
            level = {"person": 2.0, "action": 1.0, "trait": 0.0, "object": -1.0, "place": -2.0}
            for node in G.nodes:
                y = pos[node][1]
                pos[node][1] = 0.6 * y + 0.4 * level.get(G.nodes[node].get("category", ""), 0.0)
            return pos
        if style == "community":
            communities = list(nx.community.greedy_modularity_communities(G))
            pos = nx.spring_layout(G, seed=42, k=1.2)
            for ci, nodes in enumerate(communities):
                dx = ((ci % 3) - 1) * 1.5
                dy = ((ci // 3) % 3 - 1) * 1.5
                for node in nodes:
                    if node in pos:
                        pos[node][0] += dx
                        pos[node][1] += dy
            return pos
        return nx.spring_layout(G, seed=42, k=1.2)
    except Exception:
        return nx.spring_layout(G, seed=42, k=1.2)


def generate_graph_image_sync(
    repo,
    scope_id: str,
    out_dir: str,
    layout_style: str = "auto",
) -> str | None:
    """同步生成图谱 PNG；依赖缺失或数据为空时返回 None。"""
    data = prepare_graph_data(repo, scope_id)
    if data.get("error"):
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import networkx as nx
    except Exception:
        return None

    G = nx.Graph()
    for node in data["nodes"]:
        G.add_node(
            node["id"],
            name=node["name"],
            count=node["count"],
            category=node["category"],
        )
    for edge in data["edges"]:
        G.add_edge(edge["from_element"], edge["to_element"])
    if G.number_of_nodes() == 0:
        return None

    pos = _layout_positions(G, layout_style)
    counts = [max(1, G.nodes[n]["count"]) for n in G.nodes()]
    max_count = max(counts)
    sizes = [300 + 2200 * (c / max_count) for c in counts]
    colors = [_CATEGORY_COLORS.get(G.nodes[n].get("category", ""), "#95a5a6") for n in G.nodes()]

    fig, ax = plt.subplots(figsize=(14, 10), dpi=120)
    nx.draw_networkx_edges(G, pos, ax=ax, alpha=0.35, edge_color="#7f8c8d", width=1.0)
    nx.draw_networkx_nodes(G, pos, ax=ax, node_size=sizes, node_color=colors, alpha=0.9)
    nx.draw_networkx_labels(G, pos, ax=ax, font_size=8)
    ax.set_axis_off()
    ax.set_title(f"Memora 记忆图谱 ({scope_id or 'default'})", fontsize=13)

    os.makedirs(out_dir, exist_ok=True)
    safe_scope = "".join(c for c in (scope_id or "default") if c.isalnum() or c in "-_") or "default"
    out_path = os.path.join(out_dir, f"graph_{safe_scope}_{int(time.time())}.png")
    try:
        fig.savefig(out_path, bbox_inches="tight")
    finally:
        plt.close(fig)
    return out_path if os.path.exists(out_path) else None


async def generate_graph_image(repo, scope_id: str, out_dir: str,
                               layout_style: str = "auto") -> str | None:
    return await asyncio.to_thread(
        generate_graph_image_sync, repo, scope_id, out_dir, layout_style
    )