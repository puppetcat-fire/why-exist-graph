"""补丁合并：把并行执行产出合成一次状态迁移。

每个补丁是一次盲执行的产出：``{"work_item": ..., "nodes": [...], "edges": [...]}``。
合并只做两件事：检测同一节点的**内容冲突**、校验边的端点可达。

与"抢写 + claim_token 锁"的区别：补丁不直接改图库，合并阶段才暴露冲突，且冲突
是显式报告而不是互相覆盖。``merge_patches`` 是纯函数；写库由 CLI 的 ``apply`` 完成，
且必须全量校验通过才写（不留半截状态）。
"""

from __future__ import annotations

import json

__all__ = ["merge_patches", "normalize_patch"]


def _canonical(node: dict) -> str:
    """节点内容指纹：只看会冲突的字段，attrs 按键排序。"""
    payload = {
        "kind": node.get("kind"),
        "name": node.get("name"),
        "attrs": node.get("attrs") or {},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def normalize_patch(patch: dict, work_item: str | None = None) -> dict:
    """把一次执行产出规范成补丁：节点按 id 去重、边按三元组去重并排序。

    同一补丁内同 id 重复出现时保留第一次；补丁自身的内容矛盾交给
    ``merge_patches`` 与其它补丁比对时暴露。
    """
    nodes: dict[str, dict] = {}
    for node in patch.get("nodes") or []:
        node_id = node.get("id")
        if not node_id:
            continue
        nodes.setdefault(node_id, node)
    edges = {
        (edge.get("src"), edge.get("dst"), edge.get("kind"))
        for edge in patch.get("edges") or []
        if edge.get("src") and edge.get("dst") and edge.get("kind")
    }
    return {
        "work_item": work_item or patch.get("work_item"),
        "nodes": [nodes[key] for key in sorted(nodes)],
        "edges": [
            {"src": src, "dst": dst, "kind": kind}
            for src, dst, kind in sorted(edges)
        ],
    }


def merge_patches(patches: list[dict], existing_ids: set[str]) -> dict:
    """合并补丁并检测冲突。

    - 同一节点被不同补丁以不同内容修改 → ``conflicts``；
    - 同一节点内容相同（各补丁都写了同样的值）→ 去重，不算冲突；
    - 边的端点既不在补丁节点里、也不在 ``existing_ids`` 里 → ``unknown_endpoints``。

    ``ok`` 为真才允许写入。结果与补丁顺序无关。
    """
    owner: dict[str, tuple[str, str]] = {}
    nodes: dict[str, dict] = {}
    conflicts: list[dict] = []

    for index, patch in enumerate(patches):
        label = patch.get("work_item") or f"patch-{index}"
        for node in patch.get("nodes") or []:
            node_id = node.get("id")
            if not node_id:
                continue
            fingerprint = _canonical(node)
            if node_id in owner:
                previous_fingerprint, previous_label = owner[node_id]
                if previous_fingerprint != fingerprint:
                    conflicts.append({"node": node_id, "a": previous_label, "b": label})
                continue
            owner[node_id] = (fingerprint, label)
            nodes[node_id] = node

    edge_map: dict[tuple[str, str, str], dict] = {}
    for patch in patches:
        for edge in patch.get("edges") or []:
            key = (edge.get("src"), edge.get("dst"), edge.get("kind"))
            edge_map.setdefault(key, {"src": key[0], "dst": key[1], "kind": key[2]})

    known = set(nodes) | set(existing_ids)
    unknown: list[dict] = []
    for key in sorted(edge_map):
        for endpoint in (key[0], key[1]):
            if endpoint not in known:
                unknown.append({"endpoint": endpoint, "edge": edge_map[key]})

    return {
        "ok": not conflicts and not unknown,
        "conflicts": conflicts,
        "unknown_endpoints": unknown,
        "nodes": [nodes[key] for key in sorted(nodes)],
        "edges": [edge_map[key] for key in sorted(edge_map)],
    }
