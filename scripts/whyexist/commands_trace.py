"""需求追溯命令：acceptance-add / acceptance-import / trace（3.6.0）。

写入命令走 claim_token + 角色边界（`_require_write`）。边界口径：**requirement 在工单
target_ids 内时，它的 acceptance 子节点自动在边界内**——验收条目是需求的确定性派生
（`acceptance:{feature}:{suffix}:{序号}`），不要求工单事先预列每个序号。
"""

from __future__ import annotations

from .commands_feature import _require_write
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


def cmd_trace(conn, args):
    feature = ensure_feature(conn, args.feature)
    return trace_mod.trace_report(conn, feature, limit=args.limit)
