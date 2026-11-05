"""工单状态机：领取、令牌校验、写入边界与证据追加。"""

from __future__ import annotations

from .contract import C
from .errors import Reject
from .jsonio import dumps, loads, utc_now

# ------------------------------------------------------------------ 工单

def work_id(feature_id: str, generation: int, kind: str) -> str:
    return f"work:{feature_id}:g{generation}:{kind}"


def get_work(conn, item_id: str):
    row = conn.execute("SELECT * FROM work_items WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def get_work_by_token(conn, token: str):
    row = conn.execute("SELECT * FROM work_items WHERE claim_token=?", (token,)).fetchone()
    return dict(row) if row else None


def insert_work(conn, feature_id: str, generation: int, kind: str, targets: list[str], depends_on: list[str] | None, merge: bool = False) -> dict:
    wid = work_id(feature_id, generation, kind)
    existing = get_work(conn, wid)
    if existing is None:
        conn.execute(
            """INSERT INTO work_items (id, feature_id, generation, kind, role, target_ids, status, depends_on, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                wid,
                feature_id,
                generation,
                kind,
                kind,
                dumps(targets),
                "ready",
                dumps(depends_on or []),
                utc_now(),
            ),
        )
        return {"action": "insert", "id": wid}
    if merge:
        if existing["status"] not in ("ready", "claimed", "blocked"):
            raise Reject(f"工单状态是 {existing['status']}，不能并入 target_ids")
        current = loads(existing["target_ids"], [])
        seen = set(current)
        for node_id in targets:
            if node_id not in seen:
                seen.add(node_id)
                current.append(node_id)
        conn.execute("UPDATE work_items SET target_ids=? WHERE id=?", (dumps(current), wid))
        return {"action": "merge", "id": wid}
    conn.execute(
        "UPDATE work_items SET target_ids=?, depends_on=? WHERE id=?",
        (dumps(targets), dumps(depends_on or []), wid),
    )
    return {"action": "update", "id": wid}


def require_token(conn, token: str) -> dict:
    if not token:
        raise Reject("该命令需要 --token；先用 work-claim 领取工单")
    item = get_work_by_token(conn, token)
    if item is None:
        raise Reject("claim_token 无效")
    if item["status"] != "claimed":
        raise Reject(f"工单不是 claimed 状态：{item['status']}")
    return item


def require_role(item: dict, command: str) -> None:
    allowed = C.ROLES.get(item["role"], [])
    if command not in allowed:
        raise Reject(f"角色 {item['role']} 不能执行 {command}；允许：{allowed}")


def target_match(pattern: str, node_id: str) -> bool:
    if not isinstance(node_id, str):
        return False
    if pattern == node_id:
        return True
    return pattern.endswith("*") and node_id.startswith(pattern[:-1])


def require_targets(item: dict, node_ids: list[str]) -> None:
    # 大仓扫描时 target_ids 可达上万条：先分成精确集与通配前缀，避免每个节点
    # 都对全量 patterns 做一次 O(N) 匹配（原实现是 O(nodes × patterns)）。
    patterns = loads(item["target_ids"], [])
    exact = {pattern for pattern in patterns if not pattern.endswith("*")}
    prefixes = tuple(pattern[:-1] for pattern in patterns if pattern.endswith("*"))
    outside = [
        node_id
        for node_id in node_ids
        if node_id not in exact and not (prefixes and node_id.startswith(prefixes))
    ]
    if outside:
        raise Reject(f"以下 id 不在工单 target_ids 内：{outside[:5]}（共 {len(outside)} 个）")


def append_evidence(conn, item: dict, node_ids: list[str]) -> None:
    evidence = loads(item["evidence_ids"], [])
    seen = set(evidence)
    for node_id in node_ids:
        if node_id not in seen:
            seen.add(node_id)
            evidence.append(node_id)
    conn.execute("UPDATE work_items SET evidence_ids=? WHERE id=?", (dumps(evidence), item["id"]))
    item["evidence_ids"] = dumps(evidence)
