"""盲执行校验：独立执行者的产出是否落在任务书的边界与契约内。

这是"切分可局部化执行"的可检验形态：拿一份盲化任务书（见 ``briefing``）和
一个不知道全局计划的执行者产出，检查三件事：

- ``boundary``：写出的节点是否都在写入边界（含通配）内；
- ``dependencies``：边的端点是否只引用边界内节点或任务书列出的外部输入；
- ``contract``：产出节点 kind 是否在工单的产出契约内、边 kind 是否已知。

``produces`` 只对**新建**节点生效（id 不在已展开边界里的）；更新已有节点不改
判它的产出 kind。``locality`` 是这三项的加权得分，供人看趋势，不参与判定。

本模块是纯函数：不连数据库、不 import 契约模块，已知 kind 由调用方传入。
"""

from __future__ import annotations

__all__ = ["check_output"]


def _matches(pattern: str, node_id: str) -> bool:
    """与 ``briefing`` 保持同一约定：``前缀*`` 是通配，其余精确匹配。"""
    if pattern.endswith("*"):
        return node_id.startswith(pattern[:-1])
    return node_id == pattern


def _in_patterns(node_id: str, patterns: list[str]) -> bool:
    return any(_matches(pattern, node_id) for pattern in patterns)


def check_output(
    *,
    brief: dict,
    output: dict,
    known_node_kinds: list[str] | None = None,
    known_edge_kinds: list[str] | None = None,
) -> dict:
    """校验一次盲执行的产出，返回可机读的判定与分解明细。"""
    known_nodes = set(known_node_kinds or ())
    known_edges = set(known_edge_kinds or ())
    patterns = list(brief.get("write_patterns") or [])
    boundary = set(brief.get("write_boundary") or [])
    inputs = {item["id"] for item in brief.get("inputs") or [] if "id" in item}
    produces = set(brief.get("produces") or ())
    declared = boundary | inputs

    nodes = output.get("nodes") or []
    edges = output.get("edges") or []

    out_of_bounds: list[str] = []
    unexpected_kinds: list[dict] = []
    unknown_kinds: list[dict] = []
    malformed: list[dict] = []
    for node in nodes:
        node_id = node.get("id")
        kind = node.get("kind")
        if not node_id or not kind:
            malformed.append({"node": node, "reason": "缺少 id 或 kind"})
            continue
        if node_id not in boundary and not _in_patterns(node_id, patterns):
            out_of_bounds.append(node_id)
        if produces and node_id not in boundary and kind not in produces:
            unexpected_kinds.append({"id": node_id, "kind": kind})
        if known_nodes and kind not in known_nodes:
            unknown_kinds.append({"id": node_id, "kind": kind})

    undeclared: list[dict] = []
    unknown_edge_kinds: list[dict] = []
    for edge in edges:
        src, dst, kind = edge.get("src"), edge.get("dst"), edge.get("kind")
        if not src or not dst or not kind:
            malformed.append({"edge": edge, "reason": "缺少 src/dst/kind"})
            continue
        for endpoint in (src, dst):
            if endpoint not in declared and not _in_patterns(endpoint, patterns):
                undeclared.append({"edge": {"src": src, "dst": dst, "kind": kind}, "endpoint": endpoint})
        if known_edges and kind not in known_edges:
            unknown_edge_kinds.append({"src": src, "dst": dst, "kind": kind})

    boundary_ok = not out_of_bounds
    contract_ok = not (unexpected_kinds or unknown_kinds or unknown_edge_kinds or malformed)
    dependencies_ok = not undeclared

    locality = 1.0
    if out_of_bounds:
        locality -= 0.4 + 0.1 * (len(out_of_bounds) - 1)
    if undeclared:
        locality -= 0.3 + 0.1 * (len(undeclared) - 1)
    if not contract_ok:
        locality -= 0.3
    locality = max(0.0, round(locality, 2))

    verdict = "PASS" if boundary_ok and contract_ok and dependencies_ok else "FAIL"
    return {
        "work_item": brief.get("work_item"),
        "verdict": verdict,
        "locality": locality,
        "boundary": {"ok": boundary_ok, "out_of_bounds": out_of_bounds},
        "contract": {
            "ok": contract_ok,
            "unexpected_kinds": unexpected_kinds,
            "unknown_kinds": unknown_kinds,
            "unknown_edge_kinds": unknown_edge_kinds,
            "malformed": malformed,
        },
        "dependencies": {"ok": dependencies_ok, "undeclared": undeclared},
    }
