"""覆盖 / 一致性 / 调谐命令：coverage / conformance / reconcile / serve。"""

from __future__ import annotations

import argparse
import time

from .commands_feature import work_seed
from .contract import C
from .errors import Reject
from .evidence import evidence_qualifies
from .gates import (
    conformance_report,
    coverage_report,
    drift_report,
    reconcile_actions,
)
from .graph import get_node
from .jsonio import dumps, loads, utc_now
from .trace import trace_report
from .workflow import (
    condition_flags,
    ensure_feature,
    get_feature,
    refresh_blocked,
    scope_ids,
)

def cmd_coverage(conn, args):
    feature = ensure_feature(conn, args.feature)
    return coverage_report(conn, feature, epsilon=args.epsilon, prior_p=args.prior_p)


# 编译器命令已搬进 whyexist.commands_compiler；这里 re-export。
from whyexist.commands_compiler import (  # noqa: E402
    _brief_payload,
    cmd_apply,
    cmd_blind_check,
    cmd_brief,
    cmd_conflicts,
    cmd_cycles,
    cmd_impact,
    cmd_patch,
    cmd_plan,
)


def cmd_conformance(conn, args):
    feature = ensure_feature(conn, args.feature)
    limit = args.limit if args.limit is not None else 50
    if limit < 0:
        raise Reject("--limit 必须是非负整数")
    report = conformance_report(conn, feature, limit=limit)
    report["enforced"] = bool(feature.get("conformance"))
    if feature.get("conformance"):
        report["enforced"] = True
    return report


def apply_safe_actions(conn, feature: dict, actions: list[dict]) -> list[str]:
    """执行 reconcile 允许的三类安全迁移；返回实际执行的类目。"""
    applied: list[str] = []
    if any(action["action"] == "seed-ticket" for action in actions):
        work_seed(conn, feature["id"])
        applied.append("seed-ticket")
    if any(action["action"] == "unblock" for action in actions):
        refresh_blocked(conn, feature["id"], feature["generation"])
        applied.append("unblock")
    stale = [action["work_item"] for action in actions if action["action"] == "release-stale-claim"]
    for wid in stale:
        conn.execute(
            "UPDATE work_items SET status='ready', claim_token=NULL, assignee=NULL, "
            "claimed_by=NULL, claimed_at=NULL WHERE id=? AND status='claimed'",
            (wid,),
        )
    if stale:
        applied.append("release-stale-claim")
    return applied


def _pending_counts(conn, feature: dict) -> dict:
    counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT status FROM work_items WHERE feature_id=? AND generation=?",
        (feature["id"], feature["generation"]),
    ).fetchall():
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def reconcile_feature(conn, feature: dict, ttl: int, do_apply: bool) -> dict:
    actions = reconcile_actions(conn, feature, ttl)
    applied: list[str] = []
    if do_apply:
        applied = apply_safe_actions(conn, feature, actions)
        if applied:
            actions = reconcile_actions(conn, feature, ttl)
    gate = cmd_gate(conn, argparse.Namespace(feature=feature["id"], json=True))
    return {
        "feature": feature["id"],
        "generation": feature["generation"],
        "claim_ttl": ttl,
        "actions": actions,
        "applied": applied,
        "pending": _pending_counts(conn, feature),
        "gate": {"result": gate.get("result"), "reason": gate.get("reason")},
        "converged": (not actions) and gate.get("result") == "PASS",
    }


def cmd_reconcile(conn, args):
    feature = ensure_feature(conn, args.feature)
    ttl = args.claim_ttl if args.claim_ttl is not None else int(C.RECONCILE_DEFAULTS["claim_ttl"])
    if ttl < 0:
        raise Reject("--claim-ttl 必须是非负整数")
    return reconcile_feature(conn, feature, ttl, bool(args.apply))


def cmd_serve(conn, args):
    """常驻控制器：按 interval 反复跑 reconcile；--once 单趟，便于测试与 CI。"""
    interval = args.interval if args.interval is not None else 5
    if interval <= 0:
        raise Reject("--interval 必须是正整数")
    ttl = args.claim_ttl if args.claim_ttl is not None else int(C.RECONCILE_DEFAULTS["claim_ttl"])
    if ttl < 0:
        raise Reject("--claim-ttl 必须是非负整数")
    passes = 0
    try:
        while True:
            passes += 1
            features = (
                [args.feature]
                if getattr(args, "feature", None)
                else [row["id"] for row in conn.execute("SELECT id FROM features ORDER BY id").fetchall()]
            )
            results = []
            for fid in features:
                feature = get_feature(conn, fid)
                if feature is None:
                    continue
                results.append(reconcile_feature(conn, feature, ttl, bool(args.apply)))
            if args.apply:
                conn.commit()
            summary = {
                "pass": passes,
                "at": utc_now(),
                "features": results,
                "converged": all(item["converged"] for item in results) if results else True,
            }
            print(dumps(summary), flush=True)
            if args.once:
                return summary
            import time

            time.sleep(interval)
    except KeyboardInterrupt:
        return {"passes": passes, "stopped": "keyboard-interrupt"}


def cmd_gate(conn, args):
    feature = ensure_feature(conn, args.feature)
    flags = condition_flags(conn, feature)
    scope = set(scope_ids(conn, feature["id"]))
    verdicts = []
    dangling = []
    latest: dict[str, str] = {}
    for row in conn.execute(
        "SELECT node_id, feature_id, generation, phase, verdict FROM bites ORDER BY id"
    ).fetchall():
        in_feature = row["node_id"] in scope or row["feature_id"] == feature["id"]
        if not in_feature:
            continue
        if row["feature_id"] == feature["id"] and row["generation"] not in (None, feature["generation"]):
            continue
        if get_node(conn, row["node_id"]) is None:
            # 已 retract 的节点：不再计入门禁，但把悬空判决显式带出来，
            # 由 doctor 负责清理，避免 gate 把无效咬合当成交付证据。
            dangling.append({"node": row["node_id"], "verdict": row["verdict"]})
            continue
        # 只按最新一条判决：KEEP 只反证同一节点，跨节点不再抵消。
        element = {"node": row["node_id"], "verdict": row["verdict"], "phase": row["phase"]}
        verdicts.append(element)
        latest[row["node_id"]] = row["verdict"]
    fails = [
        {"node": node_id, "verdict": verdict}
        for node_id, verdict in latest.items()
        if verdict in C.GATE_FAIL_VERDICTS
    ]

    pattern_issues = []
    for node_id in sorted(scope):
        node = get_node(conn, node_id)
        if node is None or node["kind"] != "pattern":
            continue
        attrs = loads(node["attrs_json"], {})
        missing_attrs = [
            key for key in ("applicability", "not_applicable") if not str(attrs.get(key) or "").strip()
        ]
        attached = (
            conn.execute("SELECT 1 FROM edges WHERE kind='applies' AND dst=? LIMIT 1", (node_id,)).fetchone()
            is not None
        )
        if missing_attrs or not attached:
            pattern_issues.append({"pattern": node_id, "missing_attrs": missing_attrs, "attached": attached})

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

    conformance = conformance_report(conn, feature) if feature.get("conformance") else None

    evidence_ok = evidence_qualifies(conn, feature["id"], feature["generation"])
    coverage = coverage_report(conn, feature)
    drift = drift_report(conn, feature)
    traceability = trace_report(conn, feature)
    base = {
        "conditions": flags,
        "bites": verdicts,
        "latest_verdicts": [{"node": node_id, "verdict": verdict} for node_id, verdict in latest.items()],
        "evidence_ok": evidence_ok,
        "coverage": coverage,
        "drift": drift,
        "traceability": traceability,
        "constructions": constructions,
        "stale": stale_nodes,
    }

    # 把每项检查的通过情况单独列出来：FAIL 时看 checks 就知道卡在哪，
    # 也让"文档漏写检查项"这类漂移在输出里直接可见。
    missing = [name for name in C.CONDITIONS if flags[name] != 1]
    evidence_missing = [name for name in C.EVIDENCE_REQUIRED_CONDITIONS if flags.get(name) == 1]
    base["checks"] = [
        {"name": "bites", "ok": not fails},
        {"name": "pattern", "ok": not pattern_issues},
        {"name": "drift", "ok": not (drift["enforced"] and drift["count"] > drift["limit"])},
        {"name": "construction", "ok": not constructions},
        {"name": "stale", "ok": not stale_nodes},
        {"name": "conformance", "ok": conformance is None or not conformance["violations"]},
        {"name": "conditions", "ok": not missing},
        {"name": "evidence", "ok": not (evidence_missing and not evidence_ok)},
        {"name": "traceability", "ok": traceability["ok"], "unknown": traceability["summary"]["unknown"]},
        {"name": "coverage", "ok": not (coverage["enforced"] and coverage["unmet"])},
    ]
    if dangling:
        base["ignored_dangling_bites"] = dangling
    if conformance is not None:
        base["conformance"] = conformance
    if fails:
        return {
            "result": "FAIL",
            "reason": "作用域内节点最新咬合为 UNNECESSARY/HOLLOW：" + "、".join(item["node"] for item in fails),
            "hollow": fails,
            **base,
        }
    if pattern_issues:
        return {
            "result": "FAIL",
            "reason": "模式有限应用检查未通过：" + "、".join(item["pattern"] for item in pattern_issues),
            "patterns": pattern_issues,
            **base,
        }
    if drift["enforced"] and drift["count"] > drift["limit"]:
        return {
            "result": "FAIL",
            "reason": f"结构性漂移超标：{drift['count']} 个 UNMAPPED/DOC-ONLY 节点，上限 {drift['limit']}",
            "drifted": drift["nodes"],
            **base,
        }
    if constructions:
        return {
            "result": "FAIL",
            "reason": "仍有施工中节点（construction=true）：" + "、".join(constructions),
            "constructions": constructions,
            **base,
        }
    if stale_nodes:
        return {
            "result": "FAIL",
            "reason": "回扫发现已不存在的代码节点（stale）：" + "、".join(stale_nodes),
            "stale_nodes": stale_nodes,
            **base,
        }
    if conformance is not None and conformance["violations"]:
        return {
            "result": "FAIL",
            "reason": (
                "设计-代码一致性未通过："
                f"锚点缺失 {conformance['anchors']['missing_count']}、"
                f"depends 无代码支撑 {conformance['structural']['missing_backing_count']}、"
                f"未声明耦合 {conformance['structural']['undeclared_count']}、"
                f"use_case 缺测试 {conformance['tests']['missing_count']}"
            ),
            **base,
        }
    if missing:
        return {
            "result": "FAIL",
            "reason": "条件未齐：" + ", ".join(missing),
            "missing": missing,
            **base,
        }
    if evidence_missing and not evidence_ok:
        return {
            "result": "FAIL",
            "reason": "缺少有效的同 generation evidence（exit_code=0 且产物存在/hash 一致）：" + ", ".join(evidence_missing),
            "missing_evidence_for": evidence_missing,
            **base,
        }
    if traceability["summary"]["unknown"]:
        return {
            "result": "UNKNOWN",
            "reason": (
                f"追溯门无法判定：作用域内 {traceability['requirements']} 条需求，但一条验收条目都没登记；"
                "先 `acceptance-import`（从 x_acceptance 迁移）或 `acceptance-add` 登记验收，再谈交付"
            ),
            **base,
        }
    if traceability["applicable"] and not traceability["ok"]:
        summary = traceability["summary"]
        spec_only = summary.get("acceptance_spec_only", 0)
        blocked = summary.get("acceptance_blocked", 0)
        reason = (
            f"需求追溯未通过：{summary['acceptance_missing']} 条验收条目没有带锚点的测试指向、"
            f"{summary['requirements_without_acceptance']} 条需求没有验收条目"
        )
        if spec_only:
            reason += f"（其中 {spec_only} 条只有测试规格、没有代码锚点）"
        if blocked:
            reason += f"（其中 {blocked} 条标注了未实现/阻塞，仍算缺口、不豁免）"
        if summary.get("descoped_requirements"):
            reason += f"；另有 {summary['descoped_requirements']} 条需求声明为范围外（见 traceability.descoped）"
        return {
            "result": "FAIL",
            "reason": reason,
            "missing_acceptance": traceability["missing"],
            "without_acceptance": traceability["without_acceptance"],
            "top_gaps": traceability["top_gaps"],
            "next": "按 top_gaps 从缺口最多的需求开始补带锚点的测试；`wxg trace --feature … --md` 看全表",
            **base,
        }
    if coverage["enforced"] and coverage["unmet"]:
        return {
            "result": "FAIL",
            "reason": "咬合覆盖未达标：" + "、".join(coverage["unmet"]),
            "missing_coverage": coverage["unmet"],
            **base,
        }
    descoped = traceability.get("descoped") or []
    if descoped:
        return {
            "result": "PASS",
            "descoped": descoped,
            "note": f"另有 {len(descoped)} 条需求声明为范围外（见 _wxg_traceability.descoped）",
            **base,
        }
    return {"result": "PASS", **base}


