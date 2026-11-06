"""编译器命令：plan / brief / blind-check / cycles / patch / apply / impact / conflicts。

都是只读或"只写补丁文件"的命令；判定逻辑在 planner / briefing / blind / cycles /
reducer / impact / conflicts 六个纯函数模块里。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import blind, briefing, planner, reducer
from . import conflicts as conflicts_mod
from . import cycles as cycles_mod
from . import impact as impact_mod
from .contract import C
from .errors import Reject
from .graph import upsert_edge, upsert_node
from .jsonio import load_id_list, load_json_arg, loads
from .trace import acceptance_children
from .work import get_work, require_role, require_targets, require_token
from .workflow import ensure_feature, scope_ids

def cmd_plan(conn, args):
    """并行规划：只读。默认排除 unmapped 节点，避免内置调用噪声顶高并行度。"""

    feature = ensure_feature(conn, args.feature)
    scope = scope_ids(conn, feature["id"])
    unmapped = {
        row["id"]
        for row in conn.execute("SELECT id, unmapped FROM nodes").fetchall()
        if row["unmapped"]
    }
    excluded = (
        0 if args.include_unmapped else sum(1 for node in scope if node in unmapped)
    )
    if not args.include_unmapped:
        scope = [node for node in scope if node not in unmapped]
    # stale 节点是「代码里已不存在」的旧锚点（或重跑 derive 后不再出现的旧候选），
    # 不参与规划。
    stale = {
        row["id"]
        for row in conn.execute("SELECT id FROM nodes WHERE stale=1").fetchall()
    }
    stale_excluded = sum(1 for node in scope if node in stale)
    scope = [node for node in scope if node not in stale]
    rows = conn.execute("SELECT src, dst, kind FROM edges").fetchall()
    edge_rows = [(row["src"], row["dst"], row["kind"]) for row in rows]
    node_kinds = {
        row["id"]: row["kind"]
        for row in conn.execute("SELECT id, kind FROM nodes").fetchall()
    }
    result = planner.build_plan(
        scope,
        edge_rows,
        level=args.level,
        feature_id=feature["id"],
        node_kinds=node_kinds,
    )
    result["excluded_unmapped"] = excluded
    result["excluded_stale"] = stale_excluded
    # level=code 但作用域里没有代码层节点时，代码边必然是 0——这是作用域只含设计元素，
    # 不是"没有并行空间"。给一条提示，免得把空结果读成结论。
    if args.level == "code":
        code_kinds = {"operation", "classifier", "property", "sink", "testcase", "parameter", "assertion"}
        if not any(node_kinds.get(node) in code_kinds for node in scope):
            result["hint"] = (
                "作用域内没有代码层节点，代码层边为 0。"
                "先把代码节点纳入 feature 作用域（如 work-open --target-ids '[\"operation:*\"]'）。"
            )
    return result


def _brief_payload(conn, work_id: str) -> dict:
    """组装一张工单的盲化任务书；cmd_brief 与 cmd_blind_check 共用。"""

    work = get_work(conn, work_id)
    if work is None:
        raise Reject(f"工单不存在：{work_id}")
    work = dict(work)
    feature = ensure_feature(conn, work["feature_id"])
    scope = scope_ids(conn, feature["id"])
    nodes: dict[str, dict] = {}
    for node_id in scope:
        row = conn.execute("SELECT id, kind, name FROM nodes WHERE id=?", (node_id,)).fetchone()
        if row:
            nodes[row["id"]] = {"kind": row["kind"], "name": row["name"]}
    rows = conn.execute("SELECT src, dst, kind FROM edges").fetchall()
    edge_rows = [(row["src"], row["dst"], row["kind"]) for row in rows]
    targets = loads(work["target_ids"], [])
    boundary = briefing.resolve_boundary(targets, sorted(nodes))
    acceptance_items = []
    for node_id in boundary:
        node = nodes.get(node_id)
        if not node or node["kind"] != "requirement":
            continue
        for item in acceptance_children(conn, node_id):
            acceptance_items.append({
                "id": item["id"],
                "requirement": node_id,
                "ordinal": item["ordinal"],
                "text": item["text"],
            })
    return briefing.build_brief(
        feature={
            "id": feature["id"],
            "statement": feature["statement"],
            "acceptance": loads(feature["acceptance_json"], []),
            "constraints": loads(feature["constraints_json"], []),
        },
        work={
            "id": work["id"],
            "role": work["role"],
            "kind": work["kind"],
            "target_ids": targets,
        },
        nodes=nodes,
        edges=edge_rows,
        acceptance_items=acceptance_items,
    )


def cmd_brief(conn, args):
    """盲化任务书：只读。"""
    result = _brief_payload(conn, args.work)
    if args.out:
        target = Path(args.out)
        target.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return {"written": str(target), "work_item": result["work_item"]}
    return result


def cmd_blind_check(conn, args):
    """盲执行校验：只读。产出文件由调用方提供，不写库。"""

    brief = _brief_payload(conn, args.work)
    path = Path(args.result)
    if not path.is_file():
        raise Reject(f"产出文件不存在：{args.result}")
    try:
        output = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Reject(f"产出文件无法解析为 JSON：{exc}") from exc
    if not isinstance(output, dict):
        raise Reject("产出文件必须是 JSON 对象（含 nodes / edges 数组）")
    return blind.check_output(
        brief=brief,
        output=output,
        known_node_kinds=[kind["kind"] for kind in C.NODE_KINDS],
        known_edge_kinds=[kind["kind"] for kind in C.EDGE_KINDS],
    )


def cmd_cycles(conn, args):
    """依赖环分析：只读。把 design 层的 SCC 展开成具体边与证据。"""

    feature = ensure_feature(conn, args.feature)
    scope = scope_ids(conn, feature["id"])
    stale = {
        row["id"]
        for row in conn.execute("SELECT id FROM nodes WHERE stale=1").fetchall()
    }
    node_kinds = {
        row["id"]: row["kind"]
        for row in conn.execute("SELECT id, kind FROM nodes").fetchall()
    }
    design = {
        node
        for node in scope
        if node not in stale and node_kinds.get(node) in ("component", "port", "pattern")
    }
    edges: list[tuple[str, str]] = []
    evidence: dict[tuple[str, str], list] = {}
    for row in conn.execute("SELECT src, dst, kind, attrs_json FROM edges").fetchall():
        if row["kind"] != "depends":
            continue
        src, dst = row["src"], row["dst"]
        if src in design and dst in design:
            edges.append((src, dst))
            attrs = loads(row["attrs_json"], {})
            if isinstance(attrs, dict):
                evidence[(src, dst)] = attrs.get("x_evidence") or []
    removals: set[tuple[str, str]] = set()
    for item in (args.without or "").split(","):
        item = item.strip()
        if not item:
            continue
        if "->" not in item:
            raise Reject(f"--without 的格式是 src->dst：{item}")
        src, dst = (part.strip() for part in item.split("->", 1))
        if src not in design or dst not in design:
            raise Reject(f"--without 的端点不在设计层：{item}")
        removals.add((src, dst))
    found = cycles_mod.find_cycles(sorted(design), edges, evidence, removals)
    result = {
        "feature": feature["id"],
        "node_count": len(design),
        "edge_count": len(edges),
        "without": [list(edge) for edge in sorted(removals)],
        "cycle_count": len(found),
        "cycles": found,
    }
    if args.break_set:
        info = cycles_mod.minimal_break_sets(sorted(design), edges)
        costs = cycles_mod.break_set_costs(sorted(design), edges, info["break_sets"])
        result["break_sets"] = [
            {
                "size": item["size"],
                "edges": [
                    {
                        "src": edge[0],
                        "dst": edge[1],
                        "evidence": evidence.get((edge[0], edge[1]), []),
                    }
                    for edge in item["edges"]
                ],
                "cost": {
                    "lost_pairs": cost["lost_pairs"],
                    "affected_count": cost["affected_count"],
                },
            }
            for item, cost in zip(info["break_sets"], costs)
        ]
        result["truncated"] = info["truncated"]
    if args.advise:

        cycle_edges: set[tuple[str, str]] = set()
        for cycle in found:
            for edge in cycle["edges"]:
                cycle_edges.add((edge["src"], edge["dst"]))
            for loop in cycle["self_loops"]:
                cycle_edges.add((loop["src"], loop["dst"]))
        lost_counts: dict[tuple[str, str], int] = {}
        if cycle_edges:
            design_edge_rows = [(src, dst, "depends") for src, dst in edges]
            rows = impact_mod.edge_removal_impact(
                sorted(design), design_edge_rows, cycle_edges
            )
            lost_counts = {
                (row["src"], row["dst"]): row["lost_count"] for row in rows
            }
        info = cycles_mod.advise_break_edges(sorted(design), edges, lost_counts)
        result["advice"] = info["advice"]
        result["truncated"] = info["truncated"]
    return result


def cmd_patch(conn, args):
    """把一次盲执行产出规范成补丁文件（只读，写 --out 文件）。"""

    result_path = Path(args.result)
    if not result_path.is_file():
        raise Reject(f"产出文件不存在：{args.result}")
    try:
        output = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Reject(f"产出文件无法解析为 JSON：{exc}") from exc
    if not isinstance(output, dict):
        raise Reject("产出文件必须是 JSON 对象（含 nodes / edges 数组）")
    patch = reducer.normalize_patch(output, work_item=args.work)
    target = Path(args.out)
    target.write_text(
        json.dumps(patch, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {
        "written": str(target),
        "work_item": patch["work_item"],
        "nodes": len(patch["nodes"]),
        "edges": len(patch["edges"]),
    }


def cmd_apply(conn, args):
    """合并补丁并写入图库；冲突时不写任何东西（事务回滚兜底）。"""

    paths = [item.strip() for item in args.patches.split(",") if item.strip()]
    if not paths:
        raise Reject("--patches 至少要有一个补丁文件")
    patches = []
    for item in paths:
        path = Path(item)
        if not path.is_file():
            raise Reject(f"补丁文件不存在：{item}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise Reject(f"补丁文件无法解析：{item}（{exc}）") from exc
        if not isinstance(payload, dict):
            raise Reject(f"补丁文件必须是 JSON 对象：{item}")
        patches.append(payload)

    existing = {row["id"] for row in conn.execute("SELECT id FROM nodes").fetchall()}
    merged = reducer.merge_patches(patches, existing)
    merged.update({"applied": False, "written_nodes": 0, "written_edges": 0})
    if not merged["ok"] or args.dry_run:
        return merged

    # apply 是并行产出的合并写入口，I5 同样适用：没有 token 只能验合并，不能落库。
    token = getattr(args, "token", None)
    if not token:
        raise Reject("写库需要 --token（先用 work-claim 领取工单）；只验证合并请加 --dry-run")
    item = require_token(conn, token)
    require_role(item, "apply")
    written = [node["id"] for node in merged["nodes"]]
    for edge in merged["edges"]:
        written.extend([edge["src"], edge["dst"]])
    require_targets(item, list(dict.fromkeys(written)))

    for node in merged["nodes"]:
        upsert_node(conn, node)
    for edge in merged["edges"]:
        upsert_edge(conn, edge)
    merged.update(
        {
            "applied": True,
            "written_nodes": len(merged["nodes"]),
            "written_edges": len(merged["edges"]),
        }
    )
    return merged


def cmd_impact(conn, args):
    """影响域闭包：只读。取数在 CLI 层，算法在 whyexist.impact。

    两种模式：``--changed`` 看节点改动的影响域；``--remove-edges`` 看断掉依赖边
    后源点失去哪些可达节点——后者用来判断"断这条边会不会破坏功能"。
    """

    feature = ensure_feature(conn, args.feature)
    scope = scope_ids(conn, feature["id"])
    rows = conn.execute("SELECT src, dst, kind FROM edges").fetchall()
    edge_rows = [(row["src"], row["dst"], row["kind"]) for row in rows]
    node_rows = conn.execute("SELECT id, kind FROM nodes").fetchall()
    node_kinds = {row["id"]: row["kind"] for row in node_rows}
    all_features = conn.execute("SELECT id FROM features ORDER BY id").fetchall()
    all_scopes = {row["id"]: scope_ids(conn, row["id"]) for row in all_features}

    if args.remove_edges:
        removed: set[tuple[str, str]] = set()
        for item in args.remove_edges.split(","):
            item = item.strip()
            if not item:
                continue
            if "->" not in item:
                raise Reject(f"--remove-edges 的格式是 src->dst：{item}")
            src, dst = (part.strip() for part in item.split("->", 1))
            removed.add((src, dst))
        removed_rows = impact_mod.edge_removal_impact(scope, edge_rows, removed)
        affected: set[str] = set()
        for row in removed_rows:
            affected.add(row["src"])
            affected.update(row["lost_reachable"])
        affected_in_scope = affected & set(scope)
        requirement_ids = {
            node for node, kind in node_kinds.items() if kind == "requirement"
        }
        all_edges = [(src, dst) for src, dst, _ in edge_rows]
        requirements, uncovered = impact_mod.requirement_coverage(
            affected_in_scope, all_edges, requirement_ids
        )
        return {
            "feature": feature["id"],
            "mode": "remove-edges",
            "removed": removed_rows,
            "affected": sorted(affected),
            "requirements": sorted(requirements),
            "uncovered": sorted(uncovered),
            "closed": not uncovered,
        }

    if not args.changed:
        raise Reject("impact 需要 --changed 或 --remove-edges")
    changed = load_id_list(args.changed)
    if not changed:
        raise Reject("--changed 不能为空")
    return impact_mod.build_impact(
        feature_id=feature["id"],
        scope=scope,
        changed=changed,
        edge_rows=edge_rows,
        node_kinds=node_kinds,
        all_scopes=all_scopes,
    )


def cmd_conflicts(conn, args):
    """声明期冲突检测：只读，跨 feature 对比写入边界。"""

    registered = [
        row["id"] for row in conn.execute("SELECT id FROM features ORDER BY id").fetchall()
    ]
    selected = registered
    if args.features:
        selected = [item.strip() for item in args.features.split(",") if item.strip()]
        for feature_id in selected:
            ensure_feature(conn, feature_id)
    specs: dict[str, list[str]] = {}
    for feature_id in selected:
        feature = ensure_feature(conn, feature_id)
        rows = conn.execute(
            "SELECT target_ids FROM work_items WHERE feature_id=? AND generation=?",
            (feature_id, feature["generation"]),
        ).fetchall()
        patterns: set[str] = set()
        for row in rows:
            patterns.update(loads(row["target_ids"], []))
        specs[feature_id] = sorted(patterns)
    nodes = [row["id"] for row in conn.execute("SELECT id FROM nodes ORDER BY id").fetchall()]
    return conflicts_mod.detect_conflicts(specs, nodes)


