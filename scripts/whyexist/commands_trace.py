"""需求追溯命令：acceptance-add / acceptance-import / trace（3.6.0）。

写入命令走 claim_token + 角色边界（`_require_write`）。边界口径：**requirement 在工单
target_ids 内时，它的 acceptance 子节点自动在边界内**——验收条目是需求的确定性派生
（`acceptance:{feature}:{suffix}:{序号}`），不要求工单事先预列每个序号。
"""

from __future__ import annotations

from .commands_feature import _require_write
from .errors import Reject
from .graph import get_node, upsert_node
from .jsonio import loads
from .work import append_evidence, require_targets, target_match
from .workflow import ensure_feature
from . import trace as trace_mod


def _in_scope(item: dict, node_id: str) -> bool:
    patterns = loads(item.get("target_ids") or "[]", [])
    return any(target_match(pattern, node_id) for pattern in patterns)


def cmd_acceptance_add(conn, args):
    item = _require_write(conn, args, "acceptance-add")
    requirement = args.requirement
    trace_mod.split_requirement(requirement)
    require_targets(item, [requirement])
    result = trace_mod.add_acceptance(conn, requirement, args.text)
    append_evidence(conn, item, [requirement, result["id"]])
    return result


def cmd_acceptance_import(conn, args):
    feature = ensure_feature(conn, args.feature)
    dry_run = bool(getattr(args, "dry_run", False))
    if dry_run:
        result = trace_mod.import_acceptance(conn, feature["id"], dry_run=True)
        result["work"] = None
        result["skipped_out_of_scope"] = []
        return result

    item = _require_write(conn, args, "acceptance-import")
    planned = trace_mod.import_acceptance(conn, feature["id"], dry_run=True)
    out_of_scope = sorted({
        entry["requirement"] for entry in planned["created"] if not _in_scope(item, entry["requirement"])
    })
    result = trace_mod.import_acceptance(
        conn,
        feature["id"],
        dry_run=False,
        skip_requirements=set(out_of_scope),
    )
    touched = [entry["id"] for entry in result["created"]] + [entry["requirement"] for entry in result["created"]]
    if touched:
        append_evidence(conn, item, list(dict.fromkeys(touched)))
    result["work"] = item["id"]
    result["skipped_out_of_scope"] = out_of_scope
    return result


def _render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        f"# 追溯矩阵：{report['feature']}（generation {report['generation']}）",
        "",
        (
            f"需求 {summary['requirements']} 条；验收条目 {summary['acceptance_items']}，"
            f"已测（带锚点）{summary['acceptance_tested']}，仅规格 {summary['acceptance_spec_only']}，"
            f"缺口 {summary['acceptance_missing']}（其中标注未实现/阻塞 {summary.get('acceptance_blocked', 0)}）；"
            f"未登记验收 {summary['requirements_without_acceptance']}，"
            f"聚合需求 {summary['aggregate_requirements']}。"
        ),
        "",
        "| 需求 | 优先级 | 验收 | 已测 | 仅规格 | 缺口 | 未实现 |",
        "|---|---|---|---|---|---|---|",
    ]
    rows = sorted(
        report["requirements_detail"],
        key=lambda row: (row.get("priority_rank", 99), -row["missing_count"], row["id"]),
    )
    for row in rows:
        priority = row.get("priority") or "—"
        lines.append(
            f"| `{row['id']}` | {priority} | {row['acceptance']} | {row['tested']} "
            f"| {row.get('spec_only', 0)} | {row['missing_count']} | {row.get('blocked', 0)} |"
        )
    if not rows:
        lines.append("| （无需求） | | | | | | |")
    if report.get("items"):
        lines.extend(["", "### 验收条目明细", "", "| # | 验收 | 覆盖测试 | 状态 |", "|---|---|---|---|"])
        for item in report["items"]:
            tests = "、".join(f"`{test.split(':')[-1]}`" for test in item["tests"]) or "—"
            status = item.get("status") or "—"
            lines.append(f"| {item['ordinal']} | {item['text']} | {tests} | {status} |")
    if report["truncated"]:
        lines.append("")
        lines.append("明细按 `--limit` 截断；完整清单用 `--json`。")
    return "\n".join(lines) + "\n"


def cmd_acceptance_status(conn, args):
    """给验收条目写/清 `x_status`（未实现、不适用、阻塞原因）。

    为什么不走 upsert-node：那要先把 attrs 原样读回来再整体写回，漏一个键就丢 text/ordinal。
    这个命令只碰 `x_status` 一个键，别的键原样保留。
    """
    item = _require_write(conn, args, "acceptance-status")
    node = get_node(conn, args.acceptance)
    if node is None:
        raise Reject(f"节点不存在：{args.acceptance}")
    if node["kind"] != "acceptance":
        raise Reject(f"{args.acceptance} 不是 acceptance 节点（实际 kind={node['kind']}）")
    require_targets(item, [args.acceptance])
    attrs = loads(node["attrs_json"], {})
    status = (args.status or "").strip()
    if status:
        attrs["x_status"] = status
    else:
        attrs.pop("x_status", None)
    upsert_node(conn, {
        "id": args.acceptance,
        "kind": "acceptance",
        "name": node["name"],
        "attrs": attrs,
    })
    append_evidence(conn, item, [args.acceptance])
    return {"id": args.acceptance, "status": status or None, "cleared": not status}


def cmd_trace(conn, args):
    feature = ensure_feature(conn, args.feature)
    limit = args.limit if args.limit is not None else 20
    report = trace_mod.trace_report(
        conn,
        feature,
        limit=limit,
        requirement=getattr(args, "requirement", None),
    )
    if getattr(args, "md", False):
        return {"ok": report["ok"], "markdown": _render_markdown(report), "summary": report["summary"]}
    return report
