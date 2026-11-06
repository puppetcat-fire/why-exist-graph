"""门禁分析：咬合覆盖、结构漂移、设计-代码一致性、调谐动作。"""

from __future__ import annotations

from datetime import datetime, timezone

from .contract import C, DESIGN_ANCHOR_KINDS
from .errors import Reject
from .graph import get_node
from .jsonio import loads
from .work import work_id
from .workflow import condition_flags, scope_ids

def _feature_bites(conn, feature: dict) -> list[dict]:
    """当前代、feature 作用域内的咬合记录，按 id 升序。

    无 feature_id 的旧咬合按“全局证据”计入；带 feature_id 的旧咬合在迁移时
    已按当时 feature 代回填 generation，无法还原更早代的归属。
    """
    scope = set(scope_ids(conn, feature["id"]))
    rows = []
    for row in conn.execute(
        "SELECT id, node_id, feature_id, generation, phase, verdict, reason, actor, created_at FROM bites ORDER BY id"
    ).fetchall():
        row = dict(row)
        if row["node_id"] not in scope:
            continue
        if row["feature_id"] not in (None, feature["id"]):
            continue
        if row["feature_id"] == feature["id"] and row["generation"] not in (None, feature["generation"]):
            continue
        rows.append(row)
    return rows


def _required_coverage(scope_size: int, a: float, denom: float, covered: int, epsilon: float) -> int:
    """解 p_m·(S-m) ≤ ε，返回需要的去重覆盖节点数下限（m 不超过作用域大小）。

    ``p_m = a / (denom + m)``，其中 ``denom = a₀ + b₀`` 是 Beta 先验的总强度，
    ``a = a₀ + d``。分母必须与 ``coverage_report`` 里后验 ``p`` 的算法一致
    （契约 COVERAGE_RULES：``p_m=(1+d)/(10+m)``）。

    旧实现只用 ``b₀ + m`` 作分母，漏掉了 ``a₀``，于是 ``n_required`` 比契约小一档：
    S=1、ε=0.1、d=0 时会同时输出 ``p=0.1`` 与 ``met=false``。
    """
    if scope_size <= 0 or epsilon <= 0:
        return covered

    def residual(m: int) -> float:
        return (a / (denom + m)) * max(scope_size - m, 0)

    if residual(covered) <= epsilon:
        return covered
    lo, hi = covered, scope_size
    if residual(hi) <= epsilon:
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if residual(mid) <= epsilon:
                hi = mid
            else:
                lo = mid
        return hi
    return scope_size


def drift_report(conn, feature: dict) -> dict:
    """当前代作用域内的结构漂移：最新判决为 UNMAPPED/DOC-ONLY 的节点。"""
    limit = feature.get("drift_limit")
    scope = set(scope_ids(conn, feature["id"]))
    latest: dict[str, str] = {}
    for row in conn.execute(
        "SELECT node_id, feature_id, generation, verdict FROM bites ORDER BY id"
    ).fetchall():
        in_feature = row["node_id"] in scope or row["feature_id"] == feature["id"]
        if not in_feature:
            continue
        if row["feature_id"] == feature["id"] and row["generation"] not in (None, feature["generation"]):
            continue
        latest[row["node_id"]] = row["verdict"]
    drifted = {node: verdict for node, verdict in latest.items() if verdict in C.DRIFT_VERDICTS}
    return {
        "count": len(drifted),
        "limit": limit,
        "enforced": limit is not None,
        "nodes": [{"node": node, "verdict": verdict} for node, verdict in drifted.items()],
    }


def coverage_report(conn, feature: dict, epsilon=None, prior_p=None) -> dict:
    defaults = C.COVERAGE_DEFAULTS
    policy = feature.get("coverage_epsilon") if isinstance(feature, dict) else None
    eps = float(epsilon) if epsilon is not None else float(policy if policy is not None else defaults["epsilon"])
    prior = float(prior_p) if prior_p is not None else float(defaults["prior_p"])
    a0 = max(prior * 10.0, 1e-9)
    b0 = max((1.0 - prior) * 10.0, 1e-9)
    scope = scope_ids(conn, feature["id"])
    bites = _feature_bites(conn, feature)
    phases = []
    for name in [cond for cond in C.CONDITIONS if cond in C.CONDITION_TO_KIND]:
        rows = [bite for bite in bites if bite["phase"] == name]
        covered = {bite["node_id"] for bite in rows}
        n = len(covered)
        hits = len({bite["node_id"] for bite in rows if bite["verdict"] not in ("KEEP", "UNKNOWN")})
        p = (a0 + hits) / (a0 + b0 + n)
        required = _required_coverage(len(scope), a0 + hits, a0 + b0, n, eps)
        alpha = defaults["alpha"]
        phases.append({
            "phase": name,
            "bites": len(rows),
            "covered": n,
            "hits": hits,
            "p": round(p, 6),
            "n_required": required,
            "met": n >= required,
            "index": round((alpha ** C.CONDITIONS.index(name)) * p, 6),
        })
    unmet = [item["phase"] for item in phases if not item["met"]]
    return {
        "feature": feature["id"],
        "generation": feature["generation"],
        "scope_size": len(scope),
        "epsilon": eps,
        "prior_p": prior,
        "enforced": policy is not None,
        "phases": phases,
        "unmet": unmet,
        # 阶段按条件顺序推进，不能跳着走：建议先补第一个未达标阶段。
        "next": unmet[0] if unmet else None,
    }


CODE_EDGE_KINDS = ("calls", "reads", "writes")


def _truncate(items: list, limit: int) -> list:
    return items[:limit]


def conformance_report(conn, feature: dict, limit: int = 50) -> dict:
    """只读设计-代码一致性差异：锚点、结构支撑、未声明耦合、测试覆盖。不做补写。"""
    scope = set(scope_ids(conn, feature["id"]))
    nodes = {}
    for node_id in scope:
        node = get_node(conn, node_id)
        if node:
            nodes[node_id] = node
    edges = conn.execute("SELECT kind, src, dst, attrs_json FROM edges").fetchall()

    maps = [
        (row["src"], row["dst"])
        for row in edges
        if row["kind"] == "maps_to" and row["src"] in nodes and row["dst"] in nodes
    ]
    anchored: dict[str, set[str]] = {}
    for src, dst in maps:
        anchored.setdefault(src, set()).add(dst)

    missing_anchors = []
    for node_id, node in nodes.items():
        if node["kind"] not in DESIGN_ANCHOR_KINDS:
            continue
        targets = [nodes[target] for target in anchored.get(node_id, ())]
        if not any(target["repo"] and target["path"] for target in targets):
            missing_anchors.append(node_id)

    # 设计反向：代码里没有 design 覆盖的 operation/classifier（只报告，不算 violation）。
    mapped_targets = {dst for _src, dst in maps}
    code_orphans = [
        node_id
        for node_id, node in nodes.items()
        if node["kind"] in ("operation", "classifier")
        and node["repo"]
        and node["path"]
        and not node["unmapped"]
        and node_id not in mapped_targets
    ]
    # 孤立节点拆两类：derived 组件 contains 覆盖到的（derive 后还没 promote，属正常中间态）
    # 与完全没有任何设计覆盖的（真孤立）。只看总数会把前者也算成问题。
    derived_components = [
        node_id
        for node_id, node in nodes.items()
        if node["kind"] == "component" and node.get("origin") == "derived"
    ]
    derived_members: set[str] = set()
    for row in edges:
        if row["kind"] == "contains" and row["src"] in derived_components:
            derived_members.add(row["dst"])
    unanchored = [node for node in code_orphans if node in derived_members]
    truly_orphan = [node for node in code_orphans if node not in derived_members]

    code_map: dict[str, set[str]] = {}
    for node_id, node in nodes.items():
        if node["kind"] in ("component", "port"):
            code_map[node_id] = {
                target
                for target in anchored.get(node_id, ())
                if nodes[target]["repo"] and nodes[target]["path"]
            }
    code_to_design: dict[str, set[str]] = {}
    for design_id, code_ids in code_map.items():
        for code_id in code_ids:
            code_to_design.setdefault(code_id, set()).add(design_id)

    code_edges = [
        (row["src"], row["dst"], row["kind"])
        for row in edges
        if row["kind"] in CODE_EDGE_KINDS
        and row["src"] in nodes
        and row["dst"] in nodes
        and nodes[row["src"]]["repo"]
        and nodes[row["dst"]]["repo"]
    ]
    depends_rows = [
        (row["src"], row["dst"], row["attrs_json"])
        for row in edges
        if row["kind"] == "depends" and row["src"] in nodes and row["dst"] in nodes
    ]
    depends = [(src, dst) for src, dst, _attrs in depends_rows]
    depends_set = set(depends)
    declared_pairs = set(depends_set)
    for row in edges:
        if row["kind"] in ("depends", "associates") and row["src"] in code_map and row["dst"] in code_map:
            declared_pairs.add((row["src"], row["dst"]))
            declared_pairs.add((row["dst"], row["src"]))

    # 跨文件裸名调用通常被导入器标成 unmapped；名字在作用域内唯一时做一次启发式解析，
    # 只用于“依赖是否有代码支撑”，不写回图，也不用于未声明耦合（避免误报）。
    ops_by_name: dict[str, list[str]] = {}
    for node_id, node in nodes.items():
        if node["kind"] == "operation" and not node["unmapped"] and node["name"]:
            ops_by_name.setdefault(node["name"], []).append(node_id)
    resolved_pairs = set()
    for row in edges:
        if row["kind"] not in CODE_EDGE_KINDS:
            continue
        src_node = nodes.get(row["src"])
        dst_node = nodes.get(row["dst"])
        if not src_node or not dst_node or not dst_node["unmapped"]:
            continue
        candidates = ops_by_name.get(dst_node["name"], [])
        if len(candidates) == 1 and candidates[0] != row["src"]:
            resolved_pairs.add((row["src"], candidates[0]))
    dependency_pairs = {(src, dst) for src, dst, _kind in code_edges} | resolved_pairs

    missing_backing = []
    for src, dst, attrs in depends_rows:
        # derive 写入的 depends 自带文件级 x_evidence（来源文件对），这本身就是代码依据；
        # 不认它会把 derived 组件的依赖全部误报成"无支撑"。
        if loads(attrs or "{}", {}).get("x_evidence"):
            continue
        backed = any(
            code_src in code_map.get(src, ()) and code_dst in code_map.get(dst, ())
            for code_src, code_dst in dependency_pairs
        )
        if not backed:
            missing_backing.append({"from": src, "to": dst})

    undeclared = []
    seen_pairs = set()
    for code_src, code_dst, kind in code_edges:
        for design_a in code_to_design.get(code_src, ()):
            for design_b in code_to_design.get(code_dst, ()):
                if design_a == design_b:
                    continue
                if (design_a, design_b) in declared_pairs:
                    continue
                key = (design_a, design_b)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                undeclared.append({"from": design_a, "to": design_b, "kind": kind, "code": [code_src, code_dst]})

    use_cases = [node_id for node_id, node in nodes.items() if node["kind"] == "use_case"]
    verified = {
        row["dst"]
        for row in edges
        if row["kind"] == "verifies" and row["dst"] in nodes and nodes[row["dst"]]["kind"] == "use_case"
    }
    missing_tests = [use_case for use_case in use_cases if use_case not in verified]

    violations = len(missing_anchors) + len(missing_backing) + len(undeclared) + len(missing_tests)
    hint = None
    if derived_components and code_orphans:
        hint = (
            f"孤立节点里 {len(unanchored)} 个落在 {len(derived_components)} 个 derived 组件的"
            f" contains 范围内（还没 promote + maps_to，属正常中间态），"
            f"{len(truly_orphan)} 个完全没有任何设计覆盖。先 promote 再看后者。"
        )
    payload = {
        "feature": feature["id"],
        "generation": feature["generation"],
        "limit": limit,
        "anchors": {
            "design_nodes": sum(1 for node in nodes.values() if node["kind"] in DESIGN_ANCHOR_KINDS),
            "missing": _truncate(missing_anchors, limit),
            "missing_count": len(missing_anchors),
            "code_orphans": _truncate(code_orphans, limit),
            "code_orphan_count": len(code_orphans),
            # 拆分：derived 组件 contains 覆盖到但未锚定的 vs 完全无设计覆盖的
            "unanchored_count": len(unanchored),
            "truly_orphan_count": len(truly_orphan),
        },
        "structural": {
            "depends": len(depends),
            "missing_backing": _truncate(missing_backing, limit),
            "missing_backing_count": len(missing_backing),
            "undeclared": _truncate(undeclared, limit),
            "undeclared_count": len(undeclared),
            "resolved_heuristically": len(resolved_pairs),
        },
        "tests": {
            "use_cases": len(use_cases),
            "missing": _truncate(missing_tests, limit),
            "missing_count": len(missing_tests),
        },
        "violations": violations,
        "truncated": violations > limit,
    }
    if hint:
        payload["hint"] = hint
    return payload


def reconcile_actions(conn, feature: dict, claim_ttl: int) -> list[dict]:
    """对比期望（条件）与观测（工单/咬合/标记），返回 controller 的待办动作。只读。"""
    generation = feature["generation"]
    flags = condition_flags(conn, feature)
    items = {
        row["id"]: dict(row)
        for row in conn.execute(
            "SELECT * FROM work_items WHERE feature_id=? AND generation=?", (feature["id"], generation)
        ).fetchall()
    }
    passed = {wid for wid, item in items.items() if item["status"] == "passed"}
    actions: list[dict] = []

    for condition, kind in C.CONDITION_TO_KIND.items():
        if flags.get(condition) == 1:
            continue
        wid = work_id(feature["id"], generation, kind)
        if wid not in items:
            actions.append({
                "action": "seed-ticket",
                "work_item": wid,
                "kind": kind,
                "condition": condition,
                "auto": True,
            })

    for item in items.values():
        if item["status"] != "blocked":
            continue
        deps = loads(item["depends_on"], [])
        if all(dep in passed for dep in deps):
            actions.append({"action": "unblock", "work_item": item["id"], "auto": True})

    now = datetime.now(timezone.utc)
    for item in items.values():
        if item["status"] != "claimed" or not item["claim_token"]:
            continue
        claimed_at = item.get("claimed_at")
        expired = True
        if claimed_at:
            try:
                claimed = datetime.fromisoformat(str(claimed_at).replace("Z", "+00:00"))
                expired = (now - claimed).total_seconds() > claim_ttl
            except ValueError:
                expired = True
        if expired:
            actions.append({
                "action": "release-stale-claim",
                "work_item": item["id"],
                "claimed_at": claimed_at,
                "auto": True,
            })

    for item in items.values():
        if item["status"] == "ready" and item.get("fail_reason"):
            actions.append({
                "action": "retry",
                "work_item": item["id"],
                "fail_reason": item["fail_reason"],
                "auto": False,
            })

    coverage = coverage_report(conn, feature)
    if coverage["enforced"] and coverage["unmet"]:
        actions.append({"action": "coverage-gap", "phases": coverage["unmet"], "auto": False})
    from .trace import trace_report

    trace = trace_report(conn, feature, limit=0)
    if trace["applicable"] and not trace["ok"]:
        actions.append({
            "action": "traceability-gap",
            "unknown": trace["summary"]["unknown"],
            "acceptance_missing": trace["summary"]["acceptance_missing"],
            "requirements_without_acceptance": trace["summary"]["requirements_without_acceptance"],
            "auto": False,
        })
    drift = drift_report(conn, feature)
    if drift["enforced"] and drift["count"] > drift["limit"]:
        actions.append({"action": "drift-over-limit", "count": drift["count"], "limit": drift["limit"], "auto": False})
    scope = set(scope_ids(conn, feature["id"]))
    constructions = []
    for node_id in sorted(scope):
        node = get_node(conn, node_id)
        if node and loads(node["attrs_json"], {}).get("construction") is True:
            constructions.append(node_id)
    if constructions:
        actions.append({"action": "construction-open", "nodes": constructions, "auto": False})
    stale_nodes = []
    for node_id in sorted(scope):
        node = get_node(conn, node_id)
        if node and node["stale"]:
            stale_nodes.append(node_id)
    if stale_nodes:
        actions.append({"action": "stale-node", "nodes": stale_nodes, "auto": False})
    return actions


# 工单状态机已搬进 whyexist.work；这里 re-export，保持模块内调用点不变。
from whyexist.work import (  # noqa: E402
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




