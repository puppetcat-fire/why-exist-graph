"""依赖环分析：把 SCC 展开成具体边与证据。

``plan`` 只报「这几个节点成环」，这个模块回答「哪几条依赖边造成了环、每条边来自
哪些文件」。环内的边按 SCC 收窄：同一强连通分量内部的边都可能参与某个环，把它们
全部列出来是保守但可解释的做法。

本模块是纯函数：不碰数据库；边的证据由调用方从边属性里取出后传入。
"""

from __future__ import annotations

from . import graph_algo

__all__ = [
    "advise_break_edges",
    "break_set_costs",
    "cycle_guidance",
    "cycle_shape",
    "find_cycles",
    "minimal_break_sets",
]

#: 枚举断边组合时允许的边数上限；2^n 枚举超过这个规模就拒绝。
MAX_EDGES_FOR_ENUMERATION = 20


def _has_cycle(nodes: list[str], edges: list[tuple[str, str]]) -> bool:
    if any(src == dst for src, dst in edges):
        return True
    components = graph_algo.strongly_connected_components(nodes, edges)
    return any(len(component) > 1 for component in components)


def minimal_break_sets(
    nodes: list[str],
    edges: list[tuple[str, str]],
    *,
    limit: int = 10,
) -> dict:
    """找出能破环的最小依赖边集合（按边数从小到大枚举）。

    返回 ``{break_sets: [{size, edges}], edge_count, truncated}``。``truncated``
    表示因边数超过 :data:`MAX_EDGES_FOR_ENUMERATION` 没有枚举。没有环时返回空列表。
    """
    normalized_nodes, normalized_edges, _ = graph_algo.normalize(nodes, edges)
    # 自环单独处理：它自己就是一条断边。
    self_loops = [(src, dst) for src, dst in edges if src == dst]
    if not _has_cycle(normalized_nodes, normalized_edges + self_loops):
        return {"break_sets": [], "edge_count": len(normalized_edges), "truncated": False}
    if len(normalized_edges) > MAX_EDGES_FOR_ENUMERATION:
        return {
            "break_sets": [],
            "edge_count": len(normalized_edges),
            "truncated": True,
        }

    from itertools import combinations

    # 自环不在 normalized_edges 里（归一化时被丢掉），但它是合法的断边候选，
    # 必须一起参与枚举，否则「只剩自环」的图永远找不到断边集合。
    candidates = normalized_edges + self_loops
    for size in range(1, len(candidates) + 1):
        found: list[dict] = []
        for combo in combinations(candidates, size):
            removed = set(combo)
            remaining = [edge for edge in normalized_edges if edge not in removed]
            remaining_loops = [loop for loop in self_loops if loop not in removed]
            if remaining_loops:
                continue
            if _has_cycle(normalized_nodes, remaining):
                continue
            found.append({"size": size, "edges": [list(edge) for edge in combo]})
            if len(found) >= limit:
                break
        if found:
            return {
                "break_sets": found,
                "edge_count": len(candidates),
                "truncated": False,
            }
    return {"break_sets": [], "edge_count": len(candidates), "truncated": False}


def break_set_costs(
    nodes: list[str],
    edges: list[tuple[str, str]],
    break_sets: list[dict],
) -> list[dict]:
    """计算每个断边集合**整体移除**后的代价。

    与逐条评估不同：这里把集合里的边一起拿掉，回答"按这个方案破环，总共会失去多少
    可达关系"。``lost_pairs`` 是失去的 (源点, 目标) 可达对数量，``affected_nodes``
    是这些对的端点去重后的集合。
    """
    full = graph_algo.transitive_reachable(nodes, edges)
    results: list[dict] = []
    for item in break_sets:
        removed = {(edge[0], edge[1]) for edge in item["edges"]}
        reduced_edges = [edge for edge in edges if edge not in removed]
        reduced = graph_algo.transitive_reachable(nodes, reduced_edges)
        affected: set[str] = set()
        lost_pairs = 0
        for src in full:
            lost = full[src] - reduced.get(src, set())
            if lost:
                lost_pairs += len(lost)
                affected.add(src)
                affected.update(lost)
        results.append(
            {
                "edges": [list(edge) for edge in item["edges"]],
                "lost_pairs": lost_pairs,
                "affected_nodes": sorted(affected),
                "affected_count": len(affected),
            }
        )
    return results


def advise_break_edges(
    nodes: list[str],
    edges: list[tuple[str, str]],
    lost_counts_by_edge: dict[tuple[str, str], int] | None = None,
) -> dict:
    """对环内每条依赖边给出断边建议。

    两个维度交叉：

    - 这条边是否出现在某个**最小断边集合**里（断了对破环有没有用）；
    - 断它会让源点丢失多少可达节点（``lost_count``，代价）。

    建议分三档：``preferred``（能破环且不丢可达）、``acceptable``（能破环但丢可达）、
    ``avoid``（断了也破不了环）。``lost_counts_by_edge`` 由调用方用 ``impact`` 算好传入。
    """
    cycles = find_cycles(nodes, edges)
    cycle_edges: set[tuple[str, str]] = set()
    for cycle in cycles:
        for edge in cycle["edges"]:
            cycle_edges.add((edge["src"], edge["dst"]))
        for loop in cycle["self_loops"]:
            cycle_edges.add((loop["src"], loop["dst"]))

    info = minimal_break_sets(nodes, edges)
    in_break_set: set[tuple[str, str]] = set()
    for item in info["break_sets"]:
        for edge in item["edges"]:
            in_break_set.add((edge[0], edge[1]))

    lost_counts = lost_counts_by_edge or {}
    rank = {"preferred": 0, "acceptable": 1, "avoid": 2}
    advice: list[dict] = []
    for src, dst in sorted(cycle_edges):
        lost = int(lost_counts.get((src, dst), 0))
        in_set = (src, dst) in in_break_set
        if in_set and lost == 0:
            verdict = "preferred"
        elif in_set:
            verdict = "acceptable"
        else:
            verdict = "avoid"
        advice.append(
            {
                "src": src,
                "dst": dst,
                "in_break_set": in_set,
                "lost_count": lost,
                "verdict": verdict,
            }
        )
    advice.sort(
        key=lambda item: (rank[item["verdict"]], item["lost_count"], item["src"], item["dst"])
    )
    return {"advice": advice, "truncated": info["truncated"]}


def _component_name(node_id: str) -> str | None:
    """``component:repo:pkg.sub`` -> ``pkg.sub``；非 component 返回 None。"""
    parts = node_id.split(":", 2)
    if len(parts) == 3 and parts[0] == "component":
        return parts[2]
    return None


def cycle_shape(members: list[str]) -> str:
    """判断环的形态。

    - ``parent-child``：环里存在父子包互依赖（如 ``flask`` 与 ``flask.json``）——
      这通常意味着子包反过来被顶层设施依赖，是分层没切开；
    - ``sibling``：节点平级，只是互相调用（非 component 节点混在环里时也归此类，
      不做语义猜测）。
    """
    names = [_component_name(node) for node in members]
    if any(name is None for name in names):
        return "sibling"
    for outer in names:
        for inner in names:
            if outer != inner and inner.startswith(outer + "."):
                return "parent-child"
    return "sibling"


#: 每种环形态对应的处理方向。断边只改可达性、不改分层方向，所以父子包互依赖
#: 不能靠断边解决——否则环没了，反向依赖还在，只是被藏起来。
_CYCLE_GUIDANCE = {
    "parent-child": (
        "父子包互依赖：让子包单向依赖父包（或把共用设施下沉到底层），不要用断边掩盖；"
        "断边只改可达性，不改变分层方向。"
    ),
    "sibling": (
        "平级模块互调：可断掉代价最小的一条，或把双方共同依赖的部分抽成更底层的模块。"
    ),
    "self-loop": "节点依赖自己：检查递归写入或自引用边是否应该存在。",
}


def cycle_guidance(shape: str) -> str:
    return _CYCLE_GUIDANCE.get(shape, "")


def find_cycles(
    nodes: list[str],
    edges: list[tuple[str, str]],
    evidence_by_edge: dict[tuple[str, str], list] | None = None,
    removals: set[tuple[str, str]] | None = None,
) -> list[dict]:
    """返回非平凡强连通分量及其内部边。

    - ``members``：环内节点（排序）
    - ``edges``：环内的边，带 ``evidence``（边属性里的文件对/节点对）
    - ``self_loops``：自环边（递归函数的调用环通常以自环出现）

    ``removals`` 是 what-if 用的边集合：这些边在分析前被剔除，用来回答
    「断掉这条依赖后环还在不在」。只有大小 > 1 的 SCC 才需要展开。
    """
    evidence = evidence_by_edge or {}
    removed = removals or set()
    normalized_nodes, normalized_edges, dropped = graph_algo.normalize(nodes, edges)
    normalized_edges = [edge for edge in normalized_edges if edge not in removed]
    remaining_loops = tuple(loop for loop in dropped.self_loop if loop not in removed)
    components = graph_algo.strongly_connected_components(normalized_nodes, normalized_edges)

    cycles: list[dict] = []
    for component in components:
        members = set(component)
        if len(members) > 1:
            cycle_edges = [
                {
                    "src": src,
                    "dst": dst,
                    "evidence": list(evidence.get((src, dst), [])),
                }
                for src, dst in normalized_edges
                if src in members and dst in members and src != dst
            ]
            shape = cycle_shape(sorted(component))
            cycles.append(
                {
                    "members": sorted(component),
                    "shape": shape,
                    "guidance": cycle_guidance(shape),
                    "edges": cycle_edges,
                    "self_loops": [],
                }
            )
            continue
        node = component[0]
        loops = [(src, dst) for src, dst in remaining_loops if src == node]
        if loops:
            cycles.append(
                {
                    "members": [node],
                    "shape": "self-loop",
                    "guidance": cycle_guidance("self-loop"),
                    "edges": [],
                    "self_loops": [
                        {
                            "src": src,
                            "dst": dst,
                            "evidence": list(evidence.get((src, dst), [])),
                        }
                        for src, dst in loops
                    ],
                }
            )
    return cycles
