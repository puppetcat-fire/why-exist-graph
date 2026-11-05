"""功能声明与条件状态机：条件链、代、就绪派生、作用域。"""

from __future__ import annotations

import os
import re

from .contract import C
from .errors import Reject
from .jsonio import loads

def actor_value(args, *, required: bool = True) -> str:
    """从 ``--actor`` 或 ``WXG_ACTOR`` 取执行者身份；审计与领取必须记录。"""
    raw = getattr(args, "actor", None) or os.environ.get("WXG_ACTOR") or ""
    actor = str(raw).strip()
    if not actor and required:
        raise Reject("缺少 --actor（或 WXG_ACTOR）；审计与领取必须记录执行者")
    if actor and not re.fullmatch(r"[^\s]{1,80}", actor):
        raise Reject("actor 必须是 1-80 个非空白字符")
    return actor


# ------------------------------------------------------------------ feature / 条件

def get_feature(conn, feature_id: str):
    row = conn.execute("SELECT * FROM features WHERE id=?", (feature_id,)).fetchone()
    return dict(row) if row else None


def ensure_feature(conn, feature_id: str) -> dict:
    feature = get_feature(conn, feature_id)
    if feature is None:
        raise Reject(f"feature 不存在：{feature_id}")
    return feature


def condition_rows(conn, feature: dict):
    rows = conn.execute(
        "SELECT name, status, reason FROM conditions WHERE feature_id=? AND generation=?",
        (feature["id"], feature["generation"]),
    ).fetchall()
    return {row["name"]: {"status": row["status"], "reason": row["reason"]} for row in rows}


def condition_flags(conn, feature: dict) -> dict:
    rows = condition_rows(conn, feature)
    if len(rows) != len(C.CONDITIONS):
        raise Reject(f"feature {feature['id']} 第 {feature['generation']} 代条件不齐；重新声明或登记")
    return {name: rows[name]["status"] for name in C.CONDITIONS}


def current_phase(conn, feature: dict) -> str:
    """feature 当前所处阶段 = 第一个为假的条件；Ready 表示所有条件已齐。"""
    flags = condition_flags(conn, feature)
    for name in C.CONDITIONS:
        if name == "Ready":
            continue
        if flags.get(name, 0) != 1:
            return name
    return "Ready"


def set_condition(conn, feature_id: str, generation: int, name: str, status: int, reason: str | None = None) -> None:
    conn.execute(
        "UPDATE conditions SET status=?, reason=? WHERE feature_id=? AND generation=? AND name=?",
        (status, reason, feature_id, generation, name),
    )


def recompute_ready(conn, feature_id: str, generation: int) -> int:
    rows = conn.execute(
        "SELECT name, status FROM conditions WHERE feature_id=? AND generation=?",
        (feature_id, generation),
    ).fetchall()
    flags = {row["name"]: row["status"] for row in rows}
    ready = int(all(flags.get(name) == 1 for name in C.CONDITIONS if name != "Ready")) and len(flags) == len(C.CONDITIONS)
    set_condition(conn, feature_id, generation, "Ready", 1 if ready else 0, "条件齐" if ready else None)
    return ready


def refresh_blocked(conn, feature_id: str, generation: int) -> None:
    items = conn.execute(
        "SELECT * FROM work_items WHERE feature_id=? AND generation=?", (feature_id, generation)
    ).fetchall()
    passed = {row["id"] for row in items if row["status"] == "passed"}
    for item in items:
        if item["status"] not in ("blocked",):
            continue
        deps = loads(item["depends_on"], [])
        if all(dep in passed for dep in deps):
            conn.execute("UPDATE work_items SET status='ready' WHERE id=?", (item["id"],))


def scope_ids(conn, feature_id: str) -> list[str]:
    ids = []
    seen = set()
    existing = {row["id"] for row in conn.execute("SELECT id FROM nodes").fetchall()}

    def add(node_id):
        if node_id in existing and node_id not in seen:
            seen.add(node_id)
            ids.append(node_id)

    for row in conn.execute("SELECT node_id FROM feature_nodes WHERE feature_id=?", (feature_id,)).fetchall():
        add(row["node_id"])
    prefix = f"requirement:{feature_id}:"
    for row in conn.execute("SELECT id FROM nodes").fetchall():
        if row["id"].startswith(prefix):
            add(row["id"])
    feature = get_feature(conn, feature_id)
    if feature is not None:
        for row in conn.execute(
            "SELECT target_ids FROM work_items WHERE feature_id=? AND generation=?",
            (feature_id, feature["generation"]),
        ).fetchall():
            for pattern in loads(row["target_ids"], []):
                if pattern.endswith("*"):
                    prefix = pattern[:-1]
                    for node in existing:
                        if node.startswith(prefix):
                            add(node)
                else:
                    add(pattern)
    # 排序是契约，不是美观：这里的输出会被 work-seed 原样写进 target_ids、也会被
    # feature-status 取前几条展示。旧实现直接返回收集顺序，而通配展开遍历的是 set，
    # 顺序随 PYTHONHASHSEED 变——全项目都在承诺确定性，这是唯一的例外。
    return sorted(ids)


