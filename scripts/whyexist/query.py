"""只读查询命令：slice / get / find 及其切片与目标解析。

这些命令只读状态库，不改任何表。
"""

from __future__ import annotations

from .errors import Reject
from .graph import get_node
from .jsonio import load_id_list, loads
from .work import get_work

def resolve_targets(conn, target_ids: list[str]) -> tuple[list[str], list[str], list[str]]:
    """展开工单 target_ids 里的 `前缀*` 模式，返回 (实体 id, 缺失 id, 模式)。"""
    existing = {row["id"] for row in conn.execute("SELECT id FROM nodes").fetchall()}
    resolved: list[str] = []
    seen = set()
    missing: list[str] = []
    patterns: list[str] = []
    for pattern in target_ids:
        if pattern.endswith("*"):
            patterns.append(pattern)
            prefix = pattern[:-1]
            for node_id in sorted(existing):
                if node_id.startswith(prefix) and node_id not in seen:
                    seen.add(node_id)
                    resolved.append(node_id)
        elif pattern in existing:
            if pattern not in seen:
                seen.add(pattern)
                resolved.append(pattern)
        else:
            missing.append(pattern)
    return resolved, missing, patterns


def slice_payload(conn, target_ids: list[str]) -> dict:
    resolved, missing, patterns = resolve_targets(conn, target_ids)
    nodes = [node for node in (get_node(conn, node_id) for node_id in resolved) if node]
    edges = []
    for node_id in resolved:
        edges.extend(dict(row) for row in conn.execute("SELECT * FROM edges WHERE src=? OR dst=?", (node_id, node_id)).fetchall())
    unique = {}
    for edge in edges:
        unique[edge["id"]] = edge
    return {
        "nodes": nodes,
        "edges": list(unique.values()),
        "missing_ids": missing,
        "patterns": patterns,
        "depth": 1,
    }


def cmd_slice(conn, args):
    if args.work:
        item = get_work(conn, args.work)
        if item is None:
            raise Reject(f"工单不存在：{args.work}")
        payload = slice_payload(conn, loads(item["target_ids"], []))
    else:
        target_ids = load_id_list(args.ids) if args.ids else None
        if not target_ids:
            raise Reject("--work 或 --ids 二选一")
        payload = slice_payload(conn, target_ids)
    limit = getattr(args, "limit", None)
    if limit is not None:
        if limit < 0:
            raise Reject("--limit 必须是非负整数")
        payload["nodes_total"] = len(payload["nodes"])
        payload["edges_total"] = len(payload["edges"])
        payload["nodes"] = payload["nodes"][:limit]
        payload["edges"] = payload["edges"][:limit]
        payload["truncated"] = limit < payload["nodes_total"] or limit < payload["edges_total"]
    return payload


def cmd_get(conn, args):
    node = get_node(conn, args.id)
    if node is None:
        raise Reject(f"节点不存在：{args.id}")
    node["attrs"] = loads(node.pop("attrs_json"), {})
    return {"node": node}


def cmd_find(conn, args):
    sql = "SELECT * FROM nodes WHERE 1=1"
    params = []
    if args.kind:
        sql += " AND kind=?"
        params.append(args.kind)
    if args.path_prefix:
        sql += " AND path LIKE ?"
        params.append(args.path_prefix + "%")
    if args.from_id:
        sql += " AND id IN (SELECT dst FROM edges WHERE src=?)"
        params.append(args.from_id)
    rows = []
    for row in conn.execute(sql + " ORDER BY id", params).fetchall():
        row = dict(row)
        row["attrs"] = loads(row.pop("attrs_json"), {})
        rows.append(row)
    total = len(rows)
    limit = getattr(args, "limit", None)
    if limit is not None:
        if limit < 0:
            raise Reject("--limit 必须是非负整数")
        rows = rows[:limit]
    return {"nodes": rows, "total": total, "truncated": len(rows) < total}


