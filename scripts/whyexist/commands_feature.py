"""feature 声明与工单流转命令。

覆盖：feature-declare / register / list / status、change-open / diff、
work-seed / open / claim / finish / judge / list。全部通过 conn 读写状态库，
不依赖 CLI 解析层。
"""

from __future__ import annotations

import re
import uuid

from .contract import C
from .evidence import evidence_qualifies
from .gates import conformance_report, coverage_report, drift_report
from .graph import get_node, upsert_node
from .errors import Reject
from .jsonio import dumps, load_id_list, load_json_arg, loads, new_token, utc_now
from .query import resolve_targets, slice_payload
from .trace import sync_acceptance, trace_report
from .work import (
    append_evidence,
    get_work,
    get_work_by_token,
    insert_work,
    require_role,
    require_targets,
    require_token,
    target_match,
    work_id,
)
from .workflow import (
    actor_value,
    condition_flags,
    current_phase,
    ensure_feature,
    get_feature,
    recompute_ready,
    refresh_blocked,
    scope_ids,
    set_condition,
)

def cmd_feature_declare(conn, args):
    feature_id = args.id
    if not re.fullmatch(r"[A-Za-z0-9._-]+", feature_id):
        raise Reject("feature id 只能含字母、数字、点、下划线、连字符")
    acceptance = load_json_arg(args.acceptance)
    constraints = load_json_arg(args.constraints)
    if not isinstance(acceptance, list) or not isinstance(constraints, list):
        raise Reject("acceptance / constraints 必须是 JSON 数组")
    if not args.statement:
        raise Reject("statement 不能为空")
    coverage_epsilon = getattr(args, "coverage_epsilon", None)
    if coverage_epsilon is not None and coverage_epsilon <= 0:
        raise Reject("--coverage-epsilon 必须是正数（允许的期望残留缺陷数）")
    no_coverage = bool(getattr(args, "no_coverage", False))
    if no_coverage and coverage_epsilon is not None:
        raise Reject("--coverage-epsilon 与 --no-coverage 互斥")
    drift_limit = getattr(args, "drift_limit", None)
    if drift_limit is not None and drift_limit < 0:
        raise Reject("--drift-limit 必须是非负整数（允许的 UNMAPPED/DOC-ONLY 节点数）")
    conformance_flag = bool(getattr(args, "conformance", False))
    no_conformance = bool(getattr(args, "no_conformance", False))
    if conformance_flag and no_conformance:
        raise Reject("--conformance 与 --no-conformance 互斥")
    old = get_feature(conn, feature_id)
    # 1.0.0：新 feature 默认开启 coverage；重声明保留已有策略，除非显式改。
    if coverage_epsilon is not None:
        set_coverage, coverage_value = True, coverage_epsilon
    elif no_coverage:
        set_coverage, coverage_value = True, None
    elif old is None:
        set_coverage, coverage_value = True, float(C.COVERAGE_DEFAULTS["epsilon"])
    else:
        set_coverage, coverage_value = False, None
    # 一致性门禁默认关闭；显式 flag 才改，重声明默认保留。
    if conformance_flag:
        set_conformance, conformance_value = True, 1
    elif no_conformance:
        set_conformance, conformance_value = True, 0
    elif old is None:
        set_conformance, conformance_value = True, 0
    else:
        set_conformance, conformance_value = False, None
    generation = (old["generation"] + 1) if old else 1
    if old:
        conn.execute(
            "UPDATE work_items SET status='superseded', claim_token=NULL, assignee=NULL "
            "WHERE feature_id=? AND generation=? AND status<>'superseded'",
            (feature_id, old["generation"]),
        )
        coverage_set = (
            "coverage_epsilon=excluded.coverage_epsilon"
            if set_coverage
            else "coverage_epsilon=features.coverage_epsilon"
        )
        conformance_set = (
            "conformance=excluded.conformance"
            if set_conformance
            else "conformance=features.conformance"
        )
        conn.execute(
            f"INSERT INTO features(id, name, generation, statement, acceptance_json, constraints_json, "
            f"coverage_epsilon, drift_limit, conformance, created_at) "
            f"VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, generation=excluded.generation, "
            f"statement=excluded.statement, acceptance_json=excluded.acceptance_json, constraints_json=excluded.constraints_json, "
            f"{coverage_set}, drift_limit=COALESCE(excluded.drift_limit, features.drift_limit), {conformance_set}",
            (
                feature_id, args.name, generation, args.statement, dumps(acceptance), dumps(constraints),
                coverage_value, drift_limit, conformance_value if set_conformance else 0, utc_now(),
            ),
        )
    else:
        conn.execute(
            "INSERT INTO features(id, name, generation, statement, acceptance_json, constraints_json, "
            "coverage_epsilon, drift_limit, conformance, created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                feature_id, args.name, generation, args.statement, dumps(acceptance), dumps(constraints),
                coverage_value, drift_limit, conformance_value, utc_now(),
            ),
        )
    for name in C.CONDITIONS:
        conn.execute(
            "INSERT INTO conditions(feature_id, generation, name, status, reason) VALUES(?,?,?,?,?)",
            (feature_id, generation, name, 1 if name == "Accepted" else 0, "声明受理" if name == "Accepted" else None),
        )
    requirement_id = f"requirement:{feature_id}:main"
    upsert_node(conn, {
        "id": requirement_id,
        "kind": "requirement",
        "name": args.statement,
        "attrs": {"statement": args.statement},
        "origin": "declared",
        "feature_id": feature_id,
    }, merge_attrs=True)
    write_acceptance_children(conn, feature_id, requirement_id, acceptance)
    seeded = work_seed(conn, feature_id)
    return {"feature_id": feature_id, "generation": generation, "accepted_only": True, "work_seed": seeded}


def cmd_feature_register(conn, args):
    """登记已有图。

    - 新 feature：只建元数据 + conditions（只置 Accepted）+ requirement 节点，不触发派工。
    - 已存在且未给 --generation：只更新 name/spec 与 requirement 节点正文，条件完全不动。
    - 显式 --generation 开新代：新代条件只置 Accepted，并 supersede 旧代工单（清 token），
      避免旧代 ready 工单被新代角色领走；不自动派工，需要时自行 work-seed。
    """
    feature_id = args.id
    if not re.fullmatch(r"[A-Za-z0-9._-]+", feature_id):
        raise Reject("feature id 只能含字母、数字、点、下划线、连字符")
    spec = load_json_arg(args.spec)
    if not isinstance(spec, dict) or not all(key in spec for key in ("statement", "acceptance", "constraints")):
        raise Reject("--spec 必须是含 statement/acceptance/constraints 的 JSON 对象")
    if not isinstance(spec["acceptance"], list) or not isinstance(spec["constraints"], list):
        raise Reject("--spec 的 acceptance / constraints 必须是 JSON 数组")
    if not isinstance(spec["statement"], str) or not spec["statement"]:
        raise Reject("--spec 的 statement 必须是非空字符串")
    if args.generation is not None and args.generation < 1:
        raise Reject("--generation 必须是正整数")

    def write_requirement() -> None:
        requirement_id = f"requirement:{feature_id}:main"
        upsert_node(conn, {
            "id": requirement_id,
            "kind": "requirement",
            "name": spec["statement"],
            "attrs": {"statement": spec["statement"]},
            "origin": "declared",
            "feature_id": feature_id,
        }, merge_attrs=True)
        write_acceptance_children(conn, feature_id, requirement_id, spec["acceptance"])

    old = get_feature(conn, feature_id)
    if old is None:
        generation = args.generation or 1
        conn.execute(
            "INSERT INTO features(id, name, generation, statement, acceptance_json, constraints_json, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (feature_id, args.name, generation, spec["statement"], dumps(spec["acceptance"]), dumps(spec["constraints"]), utc_now()),
        )
        for name in C.CONDITIONS:
            conn.execute(
                "INSERT INTO conditions(feature_id, generation, name, status, reason) VALUES(?,?,?,?,?)",
                (feature_id, generation, name, 1 if name == "Accepted" else 0, "登记" if name == "Accepted" else None),
            )
        write_requirement()
        return {
            "feature_id": feature_id,
            "generation": generation,
            "accepted_only": True,
            "conditions_untouched": False,
            "requirement_written": True,
        }

    if args.generation is None:
        conn.execute(
            "UPDATE features SET name=?, statement=?, acceptance_json=?, constraints_json=? WHERE id=?",
            (args.name, spec["statement"], dumps(spec["acceptance"]), dumps(spec["constraints"]), feature_id),
        )
        write_requirement()
        return {
            "feature_id": feature_id,
            "generation": old["generation"],
            "accepted_only": False,
            "conditions_untouched": True,
            "requirement_written": True,
        }

    if args.generation <= old["generation"]:
        raise Reject(f"--generation 必须大于当前 generation {old['generation']}")
    generation = args.generation
    conn.execute(
        "UPDATE work_items SET status='superseded', claim_token=NULL, assignee=NULL "
        "WHERE feature_id=? AND generation=? AND status<>'superseded'",
        (feature_id, old["generation"]),
    )
    conn.execute(
        "UPDATE features SET name=?, generation=?, statement=?, acceptance_json=?, constraints_json=? WHERE id=?",
        (args.name, generation, spec["statement"], dumps(spec["acceptance"]), dumps(spec["constraints"]), feature_id),
    )
    for name in C.CONDITIONS:
        conn.execute(
            "INSERT INTO conditions(feature_id, generation, name, status, reason) VALUES(?,?,?,?,?)",
            (feature_id, generation, name, 1 if name == "Accepted" else 0, "登记" if name == "Accepted" else None),
        )
    write_requirement()
    return {
        "feature_id": feature_id,
        "generation": generation,
        "accepted_only": True,
        "conditions_untouched": False,
        "requirement_written": True,
        "superseded_previous_generation": old["generation"],
    }


def cmd_feature_list(conn, args):
    rows = []
    for feature in conn.execute("SELECT * FROM features ORDER BY id").fetchall():
        feature = dict(feature)
        rows.append({
            "id": feature["id"],
            "name": feature["name"],
            "generation": feature["generation"],
            "conditions": condition_flags(conn, feature),
        })
    return {"features": rows}


def cmd_feature_status(conn, args):
    feature = ensure_feature(conn, args.id)
    items = conn.execute(
        "SELECT id, kind, status, target_ids, depends_on, claim_token, claimed_by, judged_by, judged_at "
        "FROM work_items WHERE feature_id=? AND generation=? ORDER BY id",
        (feature["id"], feature["generation"]),
    ).fetchall()
    bites = []
    scope = set(scope_ids(conn, feature["id"]))
    for row in conn.execute(
        "SELECT node_id, feature_id, generation, phase, verdict, reason, actor FROM bites ORDER BY id"
    ).fetchall():
        if row["node_id"] not in scope:
            continue
        if row["feature_id"] not in (None, feature["id"]):
            continue
        if row["feature_id"] == feature["id"] and row["generation"] not in (None, feature["generation"]):
            continue
        bites.append({
            "node_id": row["node_id"],
            "phase": row["phase"],
            "verdict": row["verdict"],
            "reason": row["reason"],
            "actor": row["actor"],
        })
    history = [
        dict(row)
        for row in conn.execute(
            "SELECT id, work_item_id, kind, verdict, reason, actor, judged_at FROM judge_history "
            "WHERE feature_id=? AND generation=? ORDER BY judged_at, id",
            (feature["id"], feature["generation"]),
        ).fetchall()
    ]
    evidence = [
        dict(row)
        for row in conn.execute(
            "SELECT id, generation, name, command, exit_code, artifact_sha256, actor, created_at "
            "FROM evidence WHERE feature_id=? ORDER BY created_at, id",
            (feature["id"],),
        ).fetchall()
    ]
    constructions = []
    for node_id in sorted(scope):
        node = get_node(conn, node_id)
        if node and loads(node["attrs_json"], {}).get("construction") is True:
            constructions.append(node_id)
    stale_nodes = []
    for node_id in sorted(scope):
        node = get_node(conn, node_id)
        if node and node["stale"]:
            stale_nodes.append(node_id)
    changes = [
        dict(row)
        for row in conn.execute(
            "SELECT id, from_generation, to_generation, from_condition, statement, created_at "
            "FROM changes WHERE feature_id=? ORDER BY to_generation, id",
            (feature["id"],),
        ).fetchall()
    ]
    conformance = conformance_report(conn, feature) if feature.get("conformance") else None
    # 概览视图不塞完整 target_ids：大仓的 scan 工单可能有上千条（flask 实测 6.8 万字符），
    # 整个 status 从 5KB 涨到 74KB。给计数与前几条，要看全量用 `slice --work <id>`。
    work_items = []
    for row in items:
        item = dict(row)
        targets = loads(item.pop("target_ids", "[]") or "[]", [])
        item["target_count"] = len(targets)
        item["target_sample"] = targets[:5]
        item["depends_on"] = loads(item.get("depends_on") or "[]", [])
        work_items.append(item)
    return {
        "feature": {"id": feature["id"], "name": feature["name"], "generation": feature["generation"]},
        # 当前阶段 = 第一个为假的条件；全齐时是 "Ready"。比让调用方自己从
        # conditions 里推更直观，且与门禁判定用的是同一套条件链。
        "phase": current_phase(conn, feature),
        "conditions": condition_flags(conn, feature),
        "work_items": work_items,
        "bites": bites,
        "evidence": evidence,
        "judge_history": history,
        "changes": changes,
        "coverage": coverage_report(conn, feature),
        "traceability": trace_report(conn, feature, limit=0)["summary"],
        "drift": drift_report(conn, feature),
        "constructions": constructions,
        "stale": stale_nodes,
        "conformance": {
            "enforced": conformance is not None,
            **({"violations": conformance["violations"]} if conformance else {}),
        },
        "scope_size": len(scope),
    }


def cmd_change_open(conn, args):
    feature = ensure_feature(conn, args.feature)
    flags = condition_flags(conn, feature)
    if flags.get("Ready") != 1:
        raise Reject("change-open 只在 feature Ready 后使用；未交付时直接在当前代修改")
    from_condition = args.from_condition
    if from_condition not in C.CONDITION_TO_KIND:
        raise Reject("--from-condition 必须是设计条件之一：" + ", ".join(sorted(C.CONDITION_TO_KIND)))
    change_id = args.id or f"ch-{feature['generation'] + 1}"
    if conn.execute("SELECT 1 FROM changes WHERE id=?", (change_id,)).fetchone() is not None:
        raise Reject(f"变更集 id 已存在：{change_id}")
    old_generation = feature["generation"]
    new_generation = old_generation + 1
    conn.execute(
        "UPDATE work_items SET status='superseded', claim_token=NULL, assignee=NULL "
        "WHERE feature_id=? AND generation=? AND status<>'superseded'",
        (feature["id"], old_generation),
    )
    conn.execute("UPDATE features SET generation=? WHERE id=?", (new_generation, feature["id"]))
    order = C.CONDITIONS
    boundary = order.index(from_condition)
    for name in order:
        if name == "Accepted":
            status, reason = 1, "变更集受理"
        elif name == "Ready":
            status, reason = 0, None
        elif order.index(name) < boundary:
            status, reason = 1, f"继承自第 {old_generation} 代"
        else:
            status, reason = 0, "变更集待重审"
        conn.execute(
            "INSERT INTO conditions(feature_id, generation, name, status, reason) VALUES(?,?,?,?,?)",
            (feature["id"], new_generation, name, status, reason),
        )
    conn.execute(
        "INSERT INTO changes(id, feature_id, from_generation, to_generation, from_condition, statement, affected_json, created_at) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (change_id, feature["id"], old_generation, new_generation, from_condition, args.statement, "[]", utc_now()),
    )
    seeded = work_seed(conn, feature["id"])
    return {
        "change": change_id,
        "feature": feature["id"],
        "from_generation": old_generation,
        "to_generation": new_generation,
        "from_condition": from_condition,
        "inherited": [
            name for name in C.CONDITION_TO_KIND
            if C.CONDITIONS.index(name) < boundary
        ],
        "reset": [
            name for name in C.CONDITION_TO_KIND
            if C.CONDITIONS.index(name) >= boundary
        ],
        "work_seed": seeded,
    }


def cmd_change_diff(conn, args):
    feature = ensure_feature(conn, args.feature)
    current_generation = feature["generation"]
    change = conn.execute(
        "SELECT * FROM changes WHERE feature_id=? AND to_generation=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (feature["id"], current_generation),
    ).fetchone()
    change = dict(change) if change else None
    if args.from_generation is not None:
        from_generation = args.from_generation
    elif change is not None:
        from_generation = change["from_generation"]
    else:
        from_generation = current_generation - 1
    if from_generation < 1:
        raise Reject("没有更早的 generation 可对比")

    def touched(generation: int) -> set[str]:
        ids: set[str] = set()
        for row in conn.execute(
            "SELECT evidence_ids FROM work_items WHERE feature_id=? AND generation=?",
            (feature["id"], generation),
        ).fetchall():
            ids.update(loads(row["evidence_ids"], []))
        return ids

    previous = touched(from_generation)
    current = touched(current_generation)
    flags = condition_flags(conn, feature)
    inherited: list[str] = []
    pending: list[str] = []
    if change is not None and change["to_generation"] == current_generation and change["from_condition"] in C.CONDITIONS:
        boundary = C.CONDITIONS.index(change["from_condition"])
        for name in C.CONDITION_TO_KIND:
            if C.CONDITIONS.index(name) < boundary:
                inherited.append(name)
            elif flags.get(name) != 1:
                pending.append(name)
    anchors = []
    for node_id in sorted(current | previous):
        node = get_node(conn, node_id)
        if node and node["repo"] and node["path"]:
            anchors.append({"node": node_id, "path": node["path"], "symbol": node["symbol"]})
    return {
        "feature": feature["id"],
        "change": change,
        "from_generation": from_generation,
        "to_generation": current_generation,
        "inherited_conditions": inherited,
        "pending_conditions": pending,
        "added": sorted(current - previous),
        "removed": sorted(previous - current),
        "kept": sorted(previous & current),
        "code_anchors": anchors,
    }


def work_seed(conn, feature_id: str) -> dict:
    feature = ensure_feature(conn, feature_id)
    generation = feature["generation"]
    flags = condition_flags(conn, feature)
    targets = scope_ids(conn, feature_id)
    created, existed = [], []
    prev = None
    for cond in C.CONDITIONS:
        if cond not in C.CONDITION_TO_KIND:
            continue
        kind = C.CONDITION_TO_KIND[cond]
        wid = work_id(feature_id, generation, kind)
        existing = get_work(conn, wid)
        if flags[cond] == 1:
            if existing is not None and existing["status"] == "passed":
                prev = wid
            continue
        depends = [prev] if prev else []
        status = "ready"
        if depends:
            dep = get_work(conn, depends[0])
            status = "ready" if dep is not None and dep["status"] == "passed" else "blocked"
        if existing is None:
            insert_work(conn, feature_id, generation, kind, targets, depends)
            conn.execute("UPDATE work_items SET status=? WHERE id=?", (status, wid))
            created.append({"id": wid, "kind": kind, "status": status, "depends_on": depends})
        else:
            existed.append({"id": wid, "kind": kind, "status": existing["status"]})
        prev = wid
    ready = conn.execute(
        "SELECT id, kind, status FROM work_items WHERE feature_id=? AND generation=? AND status='ready' ORDER BY id",
        (feature_id, generation),
    ).fetchall()
    return {"created": created, "existed": existed, "ready": [dict(row) for row in ready]}


def cmd_work_seed(conn, args):
    return work_seed(conn, args.feature)


def cmd_work_open(conn, args):
    feature = ensure_feature(conn, args.feature)
    if args.kind == "audit":
        raise Reject("audit 由 work-finish 自动生成")
    if args.kind not in C.WORK_KINDS:
        raise Reject(f"未知工单 kind：{args.kind}")
    targets = load_id_list(args.target_ids)
    opened = insert_work(conn, feature["id"], feature["generation"], args.kind, targets, [], merge=True)
    return {"work": opened}


def cmd_work_claim(conn, args):
    if args.role not in C.ROLES:
        raise Reject(f"未知角色：{args.role}")
    if args.role == "audit":
        raise Reject("审计不领取工单；直接 work-judge")
    if args.role in C.PRODUCT_CODE_ROLES and not args.allow_product_code:
        raise Reject("当轮未明确允许改产品代码，不能领取 implement-test")
    actor = actor_value(args)
    candidates = conn.execute(
        "SELECT w.* FROM work_items w "
        "JOIN features f ON f.id=w.feature_id AND f.generation=w.generation "
        "WHERE w.role=? AND w.status='ready' ORDER BY w.id",
        (args.role,),
    ).fetchall()
    picked = None
    token = new_token()
    for row in candidates:
        deps = loads(row["depends_on"], [])
        if not all(get_work(conn, dep) and get_work(conn, dep)["status"] == "passed" for dep in deps):
            continue
        # 原子领取：多个代理并行时只有 rowcount=1 的那个拿到单；失败就试下一张。
        changed = conn.execute(
            "UPDATE work_items SET status='claimed', assignee=?, claimed_by=?, claim_token=?, claimed_at=? "
            "WHERE id=? AND status='ready'",
            (args.role, actor, token, utc_now(), row["id"]),
        ).rowcount
        if changed:
            picked = dict(row)
            break
    if picked is None:
        raise Reject(f"角色 {args.role} 没有可领的 ready 工单")
    targets = loads(picked["target_ids"], [])
    if getattr(args, "brief", False):
        # 大仓整仓扫描的 target_ids 可达上万条，完整切片会有多 MB；--brief 只给计数，
        # 需要正文时再用 slice --work <id> --limit N 按需取。
        resolved, missing, patterns = resolve_targets(conn, targets)
        slice_payload_value = {
            "summary": {
                "targets": len(targets),
                "nodes": len(resolved),
                "missing": len(missing),
                "patterns": len(patterns),
            }
        }
    else:
        slice_payload_value = slice_payload(conn, targets)
    return {
        "work_item_id": picked["id"],
        "kind": picked["kind"],
        "role": args.role,
        "actor": actor,
        "claim_token": token,
        "target_ids": targets,
        "slice": slice_payload_value,
    }


def cmd_work_finish(conn, args):
    item = require_token(conn, args.token)
    evidence = loads(item["evidence_ids"], [])
    patterns = loads(item["target_ids"], [])
    missed = [node_id for node_id in evidence if not any(target_match(pattern, node_id) for pattern in patterns)]
    if missed:
        raise Reject(f"evidence 里有 id 不在 target_ids：{missed[:5]}")
    conn.execute("UPDATE work_items SET status='submitted', claim_token=NULL WHERE id=?", (item["id"],))
    audit_id = f"work:{item['feature_id']}:g{item['generation']}:audit:{item['id']}"
    existing = conn.execute("SELECT status FROM work_items WHERE id=?", (audit_id,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO work_items(id, feature_id, generation, kind, role, target_ids, status, depends_on, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (audit_id, item["feature_id"], item["generation"], "audit", "audit", dumps([item["id"]]), "ready", dumps([item["id"]]), utc_now()),
        )
    else:
        conn.execute("UPDATE work_items SET status='ready', depends_on=? WHERE id=?", (dumps([item["id"]]), audit_id))
    return {"work_item_id": item["id"], "status": "submitted", "audit_id": audit_id, "audit_status": "ready"}


def _resolve_subject(conn, item_id: str):
    item = get_work(conn, item_id)
    if item is None:
        raise Reject(f"工单不存在：{item_id}")
    if item["kind"] == "audit":
        deps = loads(item["depends_on"], [])
        if not deps:
            raise Reject("audit 工单缺少被审对象")
        subject = get_work(conn, deps[0])
        if subject is None:
            raise Reject("被审工单不存在")
        return subject, item
    audit_id = f"work:{item['feature_id']}:g{item['generation']}:audit:{item['id']}"
    return item, get_work(conn, audit_id)


def record_judge_history(conn, subject: dict, verdict: str, reason, actor: str, judged_at: str) -> None:
    """裁决历史只增不删：每次 work-judge（passed/failed）都留档。"""
    conn.execute(
        "INSERT INTO judge_history(id, work_item_id, feature_id, generation, kind, verdict, reason, actor, judged_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            "jh:" + uuid.uuid4().hex,
            subject["id"],
            subject["feature_id"],
            subject["generation"],
            subject["kind"],
            verdict,
            reason,
            actor,
            judged_at,
        ),
    )


def cmd_work_judge(conn, args):
    if args.role != "audit":
        raise Reject("只有 audit 角色可以裁决")
    actor = actor_value(args)
    subject, audit = _resolve_subject(conn, args.id)
    if subject["status"] != "submitted":
        raise Reject(f"被审工单必须是 submitted：{subject['status']}")
    claimed_by = subject.get("claimed_by") if isinstance(subject, dict) else subject["claimed_by"]
    legacy_claim = claimed_by in (None, "", "legacy")
    if not legacy_claim and actor == claimed_by:
        raise Reject("审计独立性：work-judge 的 actor 不能等于被审工单的 claimed_by")
    condition = C.KIND_TO_CONDITION.get(subject["kind"])
    feature = ensure_feature(conn, subject["feature_id"])
    flags = condition_flags(conn, feature)
    judged_at = utc_now()
    if args.verdict == "passed":
        if condition in C.EVIDENCE_REQUIRED_CONDITIONS:
            if not evidence_qualifies(conn, subject["feature_id"], subject["generation"]):
                raise Reject(
                    f"{condition} 需要先登记同 generation、exit_code=0 且产物有效的 evidence；"
                    "用 `wxg evidence-record --feature ... --name ... --command ... --actor ...` 登记后再裁决"
                )
        if condition is not None and feature.get("coverage_epsilon") is not None:
            report = coverage_report(conn, feature)
            phase = next((item for item in report["phases"] if item["phase"] == condition), None)
            if phase is not None and not phase["met"]:
                raise Reject(
                    f"{condition} 咬合覆盖未达标：该阶段需要覆盖 {phase['n_required']} 个节点，当前 {phase['covered']} 个；"
                    "先用 `sample --feature` 抽样并 `bite`，或调整 --coverage-epsilon（见 coverage 命令）"
                )
        ids = [subject["id"]] + ([audit["id"]] if audit else [])
        marks = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE work_items SET status='passed', claim_token=NULL, fail_reason=NULL, "
            f"judged_by=COALESCE(judged_by, ?), judged_at=COALESCE(judged_at, ?) WHERE id IN ({marks})",
            (actor, judged_at, *ids),
        )
        record_judge_history(conn, subject, "passed", None, actor, judged_at)
        if condition:
            set_condition(conn, subject["feature_id"], subject["generation"], condition, 1, "audit passed")
        ready = recompute_ready(conn, subject["feature_id"], subject["generation"])
        refresh_blocked(conn, subject["feature_id"], subject["generation"])
        return {
            "verdict": "passed",
            "condition": condition,
            "work_item_id": subject["id"],
            "actor": actor,
            "legacy_claim": legacy_claim,
            "ready": ready,
            "conditions": {
                name: conn.execute(
                    "SELECT status FROM conditions WHERE feature_id=? AND generation=? AND name=?",
                    (subject["feature_id"], subject["generation"], name),
                ).fetchone()["status"]
                for name in C.CONDITIONS
            },
        }
    if not args.fail_reason:
        raise Reject("failed 必须提供 --fail-reason")
    if audit:
        conn.execute(
            "UPDATE work_items SET status='failed', judged_by=COALESCE(judged_by, ?), "
            "judged_at=COALESCE(judged_at, ?) WHERE id=?",
            (actor, judged_at, audit["id"]),
        )
    conn.execute(
        "UPDATE work_items SET status='ready', claim_token=NULL, assignee=NULL, "
        "judged_by=COALESCE(judged_by, ?), judged_at=COALESCE(judged_at, ?), fail_reason=? WHERE id=?",
        (actor, judged_at, args.fail_reason, subject["id"]),
    )
    record_judge_history(conn, subject, "failed", args.fail_reason, actor, judged_at)
    # scan 等没有对应条件的工单，failed 不应清空七项条件（尤其不能清掉 Accepted）。
    if condition is not None:
        start = C.CONDITIONS.index(condition)
        for name in C.CONDITIONS[start:]:
            set_condition(conn, subject["feature_id"], subject["generation"], name, 0, args.fail_reason)
    refresh_blocked(conn, subject["feature_id"], subject["generation"])
    return {
        "verdict": "failed",
        "condition": condition,
        "work_item_id": subject["id"],
        "actor": actor,
        "legacy_claim": legacy_claim,
        "fail_reason": args.fail_reason,
        "conditions_changed": condition is not None,
    }


def cmd_work_list(conn, args):
    feature = ensure_feature(conn, args.feature)
    rows = conn.execute(
        "SELECT id, kind, role, status, target_ids, depends_on, claim_token FROM work_items WHERE feature_id=? AND generation=? ORDER BY id",
        (feature["id"], feature["generation"]),
    ).fetchall()
    return {"feature": feature["id"], "generation": feature["generation"], "work_items": [dict(row) for row in rows]}


def write_acceptance_children(conn, feature_id: str, requirement_id: str, acceptance) -> list[dict]:
    """声明入口把 `--acceptance` 的每条落成 acceptance 节点（只补不删，幂等）。

    验收条目**不进 feature_nodes**：作用域口径是"咬合/导出的对象集合"，验收条目挂在需求
    下面由 `has_acceptance` 表达，进作用域只会把覆盖统计的 S 撑大而无意义。
    新 feature 声明即带验收条目，gate 因此不会落在“有需求无验收”的 UNKNOWN 上；
    UNKNOWN 只留给旧库/手工 `upsert-node` 进来的需求。删验收要显式 `retract`。
    """
    return sync_acceptance(conn, requirement_id, acceptance or [])


def _require_write(conn, args, command: str):
    item = require_token(conn, getattr(args, "token", None))
    require_role(item, command)
    return item


