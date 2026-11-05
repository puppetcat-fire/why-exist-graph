"""图写入与证据命令：upsert-node / upsert-edge / bind / retract / bite / evidence。

这些命令会改状态库，写入前都要过 token 与 target_ids 边界（`_require_write`）。
"""

from __future__ import annotations

import uuid
from pathlib import Path

from .commands_feature import _require_write
from .contract import C
from .errors import Reject
from .evidence import sha256_file
from .graph import bind_node, get_node, upsert_edge, upsert_node
from .jsonio import dumps, load_id_list, load_json_arg, loads, utc_now
from .work import append_evidence, get_work, require_targets
from .workflow import actor_value, current_phase, ensure_feature

def cmd_upsert_node(conn, args):
    item = _require_write(conn, args, "upsert-node")
    payload = load_json_arg(args.data)
    if not isinstance(payload, dict):
        raise Reject("--data 必须是 JSON 对象")
    if not isinstance(payload.get("id"), str) or not payload["id"]:
        raise Reject("--data 缺少字符串 id")
    if not isinstance(payload.get("kind"), str) or not payload["kind"]:
        raise Reject("--data 缺少字符串 kind")
    require_targets(item, [payload["id"]])
    result = upsert_node(conn, payload)
    conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (item["feature_id"], payload["id"]))
    append_evidence(conn, item, [payload["id"]])
    return result


def cmd_upsert_edge(conn, args):
    item = _require_write(conn, args, "upsert-edge")
    payload = load_json_arg(args.data)
    if not isinstance(payload, dict):
        raise Reject("--data 必须是 JSON 对象")
    for key in ("src", "dst", "kind"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise Reject(f"--data 缺少字符串 {key}")
    require_targets(item, [payload["src"], payload["dst"]])
    result = upsert_edge(conn, payload)
    append_evidence(conn, item, [payload["src"], payload["dst"]])
    return result


def cmd_bind(conn, args):
    item = _require_write(conn, args, "bind")
    require_targets(item, [args.node_id, args.bind_to])
    result = bind_node(conn, args.node_id, args.bind_to, args.edge_kind)
    append_evidence(conn, item, [args.node_id, args.bind_to])
    return result


def prune_work_refs(conn, removed_ids: set[str], own_feature: str | None = None) -> tuple[int, int]:
    """从工单 target/evidence 里移除已删除的节点 id；保留通配模式与 audit 单。

    返回 ``(被裁剪的工单数, 其中不属于 own_feature 的工单数)``。跨 feature 裁剪是
    必然的（节点没了，引用必须清），但要让调用方看得见影响面，而不是静默发生。
    """
    if not removed_ids:
        return 0, 0
    changed = 0
    other_feature = 0
    rows = conn.execute(
        "SELECT id, kind, feature_id, target_ids, evidence_ids FROM work_items"
    ).fetchall()
    for item in rows:
        if item["kind"] == "audit":
            continue
        targets = loads(item["target_ids"], [])
        evidence = loads(item["evidence_ids"], [])
        new_targets = [p for p in targets if p.endswith("*") or p not in removed_ids]
        new_evidence = [node_id for node_id in evidence if node_id not in removed_ids]
        if new_targets != targets or new_evidence != evidence:
            conn.execute(
                "UPDATE work_items SET target_ids=?, evidence_ids=? WHERE id=?",
                (dumps(new_targets), dumps(new_evidence), item["id"]),
            )
            changed += 1
            if own_feature is not None and item["feature_id"] != own_feature:
                other_feature += 1
    return changed, other_feature


def cmd_retract(conn, args):
    item = _require_write(conn, args, "retract")
    node_ids = load_id_list(args.node_ids) if args.node_ids else []
    edge_ids = load_id_list(args.edge_ids) if args.edge_ids else []
    require_targets(item, node_ids)
    target_set = set(node_ids)
    removed_edges = removed_nodes = removed_bites = 0
    edges_out_of_scope = 0
    for node_id in node_ids:
        # 节点可能早就没了；只有真的删掉才计数，否则 nodes_deleted 会说谎
        exists = conn.execute("SELECT 1 FROM nodes WHERE id=?", (node_id,)).fetchone() is not None
        rows = conn.execute(
            "SELECT id, src, dst FROM edges WHERE src=? OR dst=?", (node_id, node_id)
        ).fetchall()
        for row in rows:
            conn.execute("DELETE FROM edges WHERE id=?", (row["id"],))
            removed_edges += 1
            # 删节点必须连带删边（否则留悬空边），但另一端不在本次 target 内的
            # 那些边属于「越界删除」，要单独计数，不能混进范围内的数字。
            if row["src"] not in target_set or row["dst"] not in target_set:
                edges_out_of_scope += 1
        removed_bites += conn.execute("DELETE FROM bites WHERE node_id=?", (node_id,)).rowcount
        conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        conn.execute("DELETE FROM feature_nodes WHERE node_id=?", (node_id,))
        if exists:
            removed_nodes += 1
    for eid in edge_ids:
        row = conn.execute("SELECT src, dst FROM edges WHERE id=?", (eid,)).fetchone()
        if row is not None:
            require_targets(item, [row["src"], row["dst"]])
            conn.execute("DELETE FROM edges WHERE id=?", (eid,))
            removed_edges += 1
    pruned, pruned_other = prune_work_refs(conn, set(node_ids), item.get("feature_id"))
    return {
        "nodes_deleted": removed_nodes,
        "edges_deleted": removed_edges,
        "edges_deleted_out_of_scope": edges_out_of_scope,
        "bites_deleted": removed_bites,
        "work_refs_pruned": pruned,
        "work_refs_pruned_other_features": pruned_other,
    }


def cmd_bite(conn, args):
    if args.verdict not in C.BITE_VERDICTS:
        raise Reject(f"判决必须是 {C.BITE_VERDICTS} 之一")
    actor = actor_value(args)
    node = get_node(conn, args.node)
    if node is None:
        raise Reject(f"节点不存在：{args.node}")
    generation = None
    phase = None
    added_to_scope = False
    if args.feature:
        feature = ensure_feature(conn, args.feature)
        generation = feature["generation"]
        phase = current_phase(conn, feature)
        # bite 会把这个节点塞进 feature_nodes —— 那是 plan / conformance / coverage
        # 的输入集合，不是无副作用的观察。这里要报出来，否则作用域会悄悄变大。
        existing = conn.execute(
            "SELECT 1 FROM feature_nodes WHERE feature_id=? AND node_id=?",
            (args.feature, args.node),
        ).fetchone()
        conn.execute(
            "INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)",
            (args.feature, args.node),
        )
        added_to_scope = existing is None
    conn.execute(
        "INSERT INTO bites(node_id, feature_id, generation, phase, verdict, reason, actor, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (args.node, args.feature, generation, phase, args.verdict, args.reason, actor, utc_now()),
    )
    attrs = loads(node["attrs_json"], {})
    attrs["bite"] = args.verdict
    if args.reason:
        attrs["x_bite_reason"] = args.reason
    unmapped = 1 if args.verdict == "UNMAPPED" else node["unmapped"]
    conn.execute("UPDATE nodes SET attrs_json=?, unmapped=? WHERE id=?", (dumps(attrs), unmapped, args.node))
    return {
        "node": args.node,
        "verdict": args.verdict,
        "feature": args.feature,
        "generation": generation,
        "phase": phase,
        "actor": actor,
        "added_to_feature_scope": added_to_scope,
    }


def cmd_evidence_record(conn, args):
    feature = ensure_feature(conn, args.feature)
    actor = actor_value(args)
    if not args.name.strip() or not args.command.strip():
        raise Reject("evidence 的 name 与 command 不能为空")
    work_item_id = None
    generation = feature["generation"]
    if args.work:
        work = get_work(conn, args.work)
        if work is None:
            raise Reject(f"工单不存在：{args.work}")
        if work["feature_id"] != feature["id"]:
            raise Reject("evidence 关联的工单不属于该 feature")
        work_item_id = work["id"]
        generation = work["generation"]
    artifact_path = None
    artifact_sha = None
    if args.artifact:
        artifact = Path(args.artifact).resolve()
        if not artifact.is_file():
            raise Reject(f"证据产物不存在：{artifact}")
        artifact_path = str(artifact)
        artifact_sha = sha256_file(artifact)
    evidence_id = "ev:" + uuid.uuid4().hex
    conn.execute(
        "INSERT INTO evidence(id, feature_id, generation, work_item_id, name, command, exit_code, "
        "artifact_path, artifact_sha256, actor, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            evidence_id,
            feature["id"],
            generation,
            work_item_id,
            args.name.strip(),
            args.command.strip(),
            int(args.exit_code),
            artifact_path,
            artifact_sha,
            actor,
            utc_now(),
        ),
    )
    return {
        "id": evidence_id,
        "feature_id": feature["id"],
        "generation": generation,
        "work_item_id": work_item_id,
        "name": args.name.strip(),
        "exit_code": int(args.exit_code),
        "artifact": artifact_path,
        "sha256": artifact_sha,
        "actor": actor,
    }


def cmd_evidence_list(conn, args):
    feature = ensure_feature(conn, args.feature)
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM evidence WHERE feature_id=? ORDER BY created_at, id", (feature["id"],)
        ).fetchall()
    ]
    return {"feature_id": feature["id"], "evidence": rows}


