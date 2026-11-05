"""声明期冲突检测：多个 feature 的写入边界是否会打架。

两个 feature 的 ``target_ids`` 只要可能匹配同一个节点，它们就不能同时改那一块。
在声明阶段把这些重叠列出来，比等两个代理抢写、再靠 claim_token 互斥便宜得多。

本模块是纯函数：输入是``feature -> target_ids 模式``与现有节点 id，不读数据库。
"""

from __future__ import annotations

__all__ = ["detect_conflicts", "patterns_overlap"]


def _split(pattern: str) -> tuple[str, bool]:
    """把模式拆成 (前缀, 是否通配)。精确模式视作前缀 + 非通配。"""
    if pattern.endswith("*"):
        return pattern[:-1], True
    return pattern, False


def patterns_overlap(a: str, b: str) -> bool:
    """两个 target_ids 模式是否可能匹配到同一个节点。

    模式只有两种：精确 id，或 ``前缀*``。因此重叠判断就是前缀关系判断。
    """
    prefix_a, wildcard_a = _split(a)
    prefix_b, wildcard_b = _split(b)
    if wildcard_a and wildcard_b:
        return prefix_a.startswith(prefix_b) or prefix_b.startswith(prefix_a)
    if wildcard_a:
        return prefix_b.startswith(prefix_a)
    if wildcard_b:
        return prefix_a.startswith(prefix_b)
    return prefix_a == prefix_b


def _matches(pattern: str, node_id: str) -> bool:
    prefix, wildcard = _split(pattern)
    return node_id.startswith(prefix) if wildcard else node_id == prefix


def detect_conflicts(
    features: dict[str, list[str]], existing_nodes: list[str]
) -> dict:
    """两两检查 feature 的写入边界。

    返回 ``coexist_ok`` 与冲突列表；每项含重叠的模式对与当前图上真正重叠的节点。
    当前没有节点落在重叠区时仍算冲突——声明本身已经把它们绑在同一个区域上了。
    """
    ids = sorted(features)
    conflicts: list[dict] = []
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            overlaps = sorted(
                [pattern_a, pattern_b]
                for pattern_a in features[left]
                for pattern_b in features[right]
                if patterns_overlap(pattern_a, pattern_b)
            )
            if not overlaps:
                continue
            nodes = [
                node
                for node in sorted(existing_nodes)
                if any(_matches(pattern, node) for pattern in features[left])
                and any(_matches(pattern, node) for pattern in features[right])
            ]
            conflicts.append(
                {
                    "a": left,
                    "b": right,
                    "overlapping_patterns": overlaps,
                    "overlapping_nodes": nodes,
                }
            )
    return {
        "features": ids,
        "coexist_ok": not conflicts,
        "conflicts": conflicts,
    }
