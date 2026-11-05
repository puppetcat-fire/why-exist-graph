"""盲化任务书：交给执行者的自包含任务说明。

设计要点是**结构性盲化**：本模块只接收这一张工单需要的 feature 投影、边界
节点和依赖边，不接收工单列表、执行者名单或其他目标的 ID。因此即使调用方
想泄露全局计划，也没有字段可以放。

任务书包含：

- 目标与验收（来自 feature 的 statement / acceptance / constraints）
- 写入边界（``target_ids`` 展开后的节点 ID，执行者只能在这里写）
- 输入契约（边界外、但边界内节点依赖的已存在节点）
- 产出契约（该工单 kind 负责产出的节点 kind）
- 禁止事项与完成定义

输出是纯 JSON 字典，字段顺序固定，同样输入两次生成字节一致。
"""

from __future__ import annotations

__all__ = [
    "DEPENDENCY_EDGE_KINDS",
    "PRODUCES",
    "build_brief",
    "resolve_boundary",
]

#: 表示"需求方依赖供给方"的边；其它边（contains/satisfies/...）不构成输入契约。
DEPENDENCY_EDGE_KINDS: tuple[str, ...] = ("depends", "calls", "reads", "writes")

#: 工单 kind -> 该工单负责产出的节点 kind。与契约 NODE_KINDS 的 creator 对齐。
PRODUCES: dict[str, tuple[str, ...]] = {
    "scan": ("classifier", "property", "operation", "sink"),
    "model-architecture": ("use_case", "actor", "component", "port", "pattern"),
    "model-structure": ("classifier", "property", "operation", "pattern"),
    "interact": ("interaction", "lifeline", "message", "argument", "parameter", "sink"),
    "specify-test": ("testcase", "assertion", "parameter"),
    "implement-test": (),
    "observe": (),
    "audit": (),
}

_FORBIDDEN = [
    "不得写入写入边界之外的任何节点或边",
    "不得修改其它工单的产物；发现边界划分错误时先报告，不要自行扩大范围",
    "不得引入未出现在输入契约里的外部依赖",
    "不得把本任务书的内容当作全局设计说明；本任务书是按边界裁剪过的",
]

_DONE = [
    "按产出契约写完节点/边后调用 work-finish 提交",
    "提交后由独立 audit 角色裁决，不能自审",
    "BehaviorPassed 需要同 generation、exit_code=0 的 evidence",
]


def _matches(pattern: str, node_id: str) -> bool:
    if pattern.endswith("*"):
        return node_id.startswith(pattern[:-1])
    return node_id == pattern


def resolve_boundary(target_ids: list[str], node_ids: list[str]) -> list[str]:
    """把 ``target_ids``（支持 ``前缀*``）展开成实际节点 ID，保持排序与去重。"""
    matched: set[str] = set()
    for pattern in target_ids:
        for node_id in node_ids:
            if _matches(pattern, node_id):
                matched.add(node_id)
    return sorted(matched)


def _node_ref(nodes: dict[str, dict], node_id: str) -> dict:
    node = nodes[node_id]
    return {
        "id": node_id,
        "kind": node.get("kind"),
        "name": node.get("name"),
    }


def build_brief(
    *,
    feature: dict,
    work: dict,
    nodes: dict[str, dict],
    edges: list[tuple[str, str, str]],
) -> dict:
    """生成一张工单的盲化任务书。

    ``nodes`` 是 ``id -> {kind, name}``；``edges`` 是 ``(src, dst, kind)``。
    不会读数据库，也不接受其它工单的信息。
    """
    boundary = resolve_boundary(list(work.get("target_ids") or []), sorted(nodes))
    boundary_set = set(boundary)
    upstream = {
        dst
        for src, dst, kind in edges
        if kind in DEPENDENCY_EDGE_KINDS and src in boundary_set and dst not in boundary_set
    }
    inputs = [_node_ref(nodes, node_id) for node_id in sorted(upstream) if node_id in nodes]
    kind = work.get("kind", "")
    return {
        "brief_version": 1,
        "blind": True,
        "work_item": work.get("id"),
        "feature": feature.get("id"),
        "role": work.get("role"),
        "kind": kind,
        "goal": feature.get("statement"),
        "acceptance": list(feature.get("acceptance") or []),
        "constraints": list(feature.get("constraints") or []),
        "write_boundary": boundary,
        "write_patterns": list(work.get("target_ids") or []),
        "inputs": inputs,
        "produces": list(PRODUCES.get(kind, ())),
        "forbidden": list(_FORBIDDEN),
        "definition_of_done": list(_DONE),
    }
