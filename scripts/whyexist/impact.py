"""影响域闭包与需求闭环。

改动一个设计节点后回答三件事：

- 谁依赖它：反向可达集，这些节点可能被这次改动影响；
- 它依赖谁：正向可达集，改它会动到哪些下游契约；
- 受影响范围是否都落在需求上：连不到任何 ``requirement`` 的节点就是
  "意料之外的影响面"，应当报告（强策略下可拦门）。

方向约定与 ``briefing`` 一致：边 ``a -> b`` 表示 a 依赖 b。

本模块是纯函数：不碰数据库。节点 kind、作用域、各 feature 成员由调用方传入，
这样它既能被 CLI 用，也能被 ``Engine`` 用，还能单独测。
"""

from __future__ import annotations

from . import graph_algo
from .briefing import DEPENDENCY_EDGE_KINDS

__all__ = ["build_impact", "edge_removal_impact"]


def _dependency_edges(edge_rows: list[tuple[str, str, str]]) -> list[tuple[str, str]]:
    return [(src, dst) for src, dst, kind in edge_rows if kind in DEPENDENCY_EDGE_KINDS]


def _forward(
    edges: list[tuple[str, str]], starts: list[str]
) -> set[str]:
    """从 starts 沿依赖方向走：starts 依赖谁。"""
    adjacency: dict[str, list[str]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        node = stack.pop()
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _backward(
    edges: list[tuple[str, str]], starts: list[str]
) -> set[str]:
    """从 starts 沿依赖反向走：谁依赖 starts。"""
    reverse: dict[str, list[str]] = {}
    for src, dst in edges:
        reverse.setdefault(dst, []).append(src)
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        node = stack.pop()
        for nxt in reverse.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _undirected_component(
    edges: list[tuple[str, str]], start: str
) -> set[str]:
    """忽略方向的连通分量；用于判断一个节点是否还挂在任何需求上。"""
    adjacency: dict[str, list[str]] = {}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)
        adjacency.setdefault(dst, []).append(src)
    seen = {start}
    stack = [start]
    while stack:
        node = stack.pop()
        for nxt in adjacency.get(node, ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def edge_removal_impact(
    nodes: list[str],
    edge_rows: list[tuple[str, str, str]],
    removed_edges: set[tuple[str, str]],
) -> list[dict]:
    """断掉指定依赖边后，每条边的源点失去了对哪些节点的可达。

    ``lost_reachable`` 是精确的「断前可达、断后不可达」集合——也就是真正依赖
    这条边传递的节点。它比「边两端」更接近"断掉这条边会牵动什么"。

    只分析依赖边（``depends`` / ``calls`` / ``reads`` / ``writes``）；其它边
    不参与可达性。
    """
    edges = _dependency_edges(edge_rows)
    full = graph_algo.transitive_reachable(nodes, edges)
    rows = []
    for src, dst in sorted(removed_edges):
        # 逐条移除：评估"只断这一条"的代价，而不是"断掉全部"的代价。
        reduced_edges = [edge for edge in edges if edge != (src, dst)]
        reduced = graph_algo.transitive_reachable(nodes, reduced_edges)
        lost = sorted(full.get(src, set()) - reduced.get(src, set()))
        rows.append(
            {
                "src": src,
                "dst": dst,
                "lost_reachable": lost,
                "lost_count": len(lost),
            }
        )
    return rows


def requirement_coverage(
    affected: set[str] | list[str],
    all_edges: list[tuple[str, str]],
    requirement_ids: set[str],
) -> tuple[set[str], set[str]]:
    """把受影响节点归到 requirement：返回 ``(requirements, uncovered)``。

    requirement 节点本身直接计入；其余节点按无向连通判断是否仍挂在某个需求上。
    """
    requirements: set[str] = set()
    uncovered: set[str] = set()
    for node in sorted(affected):
        if node in requirement_ids:
            requirements.add(node)
            continue
        hit = _undirected_component(all_edges, node) & requirement_ids
        if hit:
            requirements.update(hit)
        else:
            uncovered.add(node)
    return requirements, uncovered


def _backward_depth(
    edges: list[tuple[str, str]], starts: list[str]
) -> dict[str, int]:
    """从 starts 反向走，返回 ``节点 -> 最短跳数``（starts 自身为 0）。"""
    reverse: dict[str, list[str]] = {}
    for src, dst in edges:
        reverse.setdefault(dst, []).append(src)
    depth: dict[str, int] = {node: 0 for node in starts}
    frontier = list(starts)
    level = 0
    while frontier:
        level += 1
        nxt: list[str] = []
        for node in frontier:
            for prev in reverse.get(node, ()):
                if prev not in depth:
                    depth[prev] = level
                    nxt.append(prev)
        frontier = nxt
    return depth


def build_impact(
    *,
    feature_id: str,
    scope: list[str],
    changed: list[str],
    edge_rows: list[tuple[str, str, str]],
    node_kinds: dict[str, str],
    all_scopes: dict[str, list[str]] | None = None,
) -> dict:
    """计算一次改动的闭包与需求覆盖。

    ``changed`` 可以包含作用域外节点：影响域会如实扩出去，并在 ``cross_feature``
    里标出它落到了哪些其它 feature。
    """
    edges = _dependency_edges(edge_rows)
    # 需求覆盖要用全部结构边：satisfies / associates / contains 不是依赖边，
    # 但正是它们把设计节点挂到 requirement 上。
    all_edges = [(src, dst) for src, dst, _ in edge_rows]
    scope_set = set(scope)
    changed_set = set(changed)

    affected = (_backward(edges, changed) | changed_set)
    depends_on = _forward(edges, changed) - changed_set
    affected_in_scope = affected & scope_set
    cross = affected - scope_set

    # affected 原样保留（一次改动的完整波及面），另外按跳数拆成直接下游与间接波及：
    # 改 httpie.cli 时 11 个组件里哪些是"直接依赖它"、哪些是"隔了几层才被波及"，
    # 对判断改动代价是两回事。
    depth = _backward_depth(edges, changed)
    direct = sorted(node for node, hops in depth.items() if hops == 1)
    indirect = sorted(node for node, hops in depth.items() if hops >= 2)

    requirement_ids = {node for node, kind in node_kinds.items() if kind == "requirement"}
    requirements, uncovered = requirement_coverage(affected_in_scope, all_edges, requirement_ids)

    cross_detail = []
    for node in sorted(cross):
        owners = sorted(
            feature
            for feature, members in (all_scopes or {}).items()
            if node in set(members)
        )
        cross_detail.append({"node": node, "features": owners})

    return {
        "feature": feature_id,
        "changed": sorted(changed_set),
        "affected": sorted(affected),
        "direct": direct,
        "indirect": indirect,
        "affected_in_scope": sorted(affected_in_scope),
        "cross_feature": cross_detail,
        "depends_on": sorted(depends_on),
        "requirements": sorted(requirements),
        "uncovered": sorted(uncovered),
        "closed": not uncovered,
    }
