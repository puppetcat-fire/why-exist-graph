"""需求 → 验收 → 测试 追溯（3.6.0）。

验收条目是一等节点：`requirement --has_acceptance--> acceptance <--verifies-- testcase`。
本模块只做三件事：

1. 生成 acceptance（`acceptance-add` / `acceptance-import`，含旧项目从
   `requirement.attrs.x_acceptance` 的一次性迁移）；
2. 算追溯矩阵（`trace`，只读）；
3. 给 gate 提供同一口径的判定（有需求无验收 → UNKNOWN，有验收无测试 → FAIL）。

矩阵**只看 acceptance 级 verifies**：`testcase --verifies--> requirement` 这种旧式宽映射
不计入验收条目的覆盖，只作为 `direct_tests` 单独报告——否则“一条测试覆盖整条需求”
又会把缺口糊过去。
"""

from __future__ import annotations

import re

from .errors import Reject
from .graph import get_node, upsert_edge, upsert_node
from .jsonio import loads
from .workflow import scope_ids

ACCEPTANCE_EDGE_KIND = "has_acceptance"
VERIFIES_EDGE_KIND = "verifies"

#: `x_priority` 的形态：P0/P1/…（大小写不敏感）。没有或认不出按最低优先级排。
_PRIORITY = re.compile(r"^[Pp](\d{1,2})$")
NO_PRIORITY_RANK = 99


def priority_rank(value) -> int:
    """`x_priority` → 排序用的整数；认不出（含 None）返回最低优先级。"""
    match = _PRIORITY.match(str(value)) if value is not None else None
    return int(match.group(1)) if match else NO_PRIORITY_RANK


def split_requirement(requirement_id: str) -> tuple[str, str]:
    """`requirement:{feature}:{suffix}` → (feature, suffix)。"""
    parts = (requirement_id or "").split(":", 2)
    if len(parts) != 3 or parts[0] != "requirement" or not parts[1] or not parts[2]:
        raise Reject(f"不是合法的需求 id：{requirement_id}（应为 requirement:{{feature}}:{{suffix}}）")
    return parts[1], parts[2]


def acceptance_id(requirement_id: str, ordinal: int) -> str:
    """验收条目 id：`acceptance:{feature}:{suffix}:{两位序号}`。"""
    if not isinstance(ordinal, int) or not 1 <= ordinal <= 99:
        raise Reject("验收条目序号必须是 1..99 的整数")
    feature, suffix = split_requirement(requirement_id)
    return f"acceptance:{feature}:{suffix}:{ordinal:02d}"


def acceptance_children(conn, requirement_id: str) -> list[dict]:
    """某需求下的验收条目，按序号升序。"""
    rows = conn.execute(
        "SELECT d.id AS id, d.name AS name, d.attrs_json AS attrs_json "
        "FROM edges e JOIN nodes d ON d.id = e.dst "
        "WHERE e.src = ? AND e.kind = ? ORDER BY d.id",
        (requirement_id, ACCEPTANCE_EDGE_KIND),
    ).fetchall()
    items = []
    for row in rows:
        attrs = loads(row["attrs_json"], {})
        ordinal = attrs.get("ordinal")
        try:
            ordinal = int(ordinal)
        except (TypeError, ValueError):
            ordinal = 0
        items.append({
            "id": row["id"],
            "text": str(attrs.get("text") or row["name"] or ""),
            "ordinal": ordinal,
        })
    return sorted(items, key=lambda item: (item["ordinal"], item["id"]))


def _require_requirement(conn, requirement_id: str) -> dict:
    node = get_node(conn, requirement_id)
    if node is None:
        raise Reject(f"需求不存在：{requirement_id}")
    if node["kind"] != "requirement":
        raise Reject(f"{requirement_id} 不是 requirement 节点（实际 kind={node['kind']}）")
    return node


def _write_acceptance(conn, requirement_id: str, ordinal: int, text: str) -> dict:
    node_id = acceptance_id(requirement_id, ordinal)
    upsert_node(conn, {
        "kind": "acceptance",
        "id": node_id,
        "name": text,
        "attrs": {"text": text, "ordinal": ordinal},
    })
    upsert_edge(conn, {
        "kind": ACCEPTANCE_EDGE_KIND,
        "src": requirement_id,
        "dst": node_id,
    })
    return {"id": node_id, "ordinal": ordinal, "text": text}


def add_acceptance(conn, requirement_id: str, text: str) -> dict:
    """给一条需求追加一条验收条目；条文重复或为空都拒绝。"""
    _require_requirement(conn, requirement_id)
    text = (text or "").strip()
    if not text:
        raise Reject("验收条文不能为空")
    existing = acceptance_children(conn, requirement_id)
    for item in existing:
        if item["text"] == text:
            raise Reject(f"该需求已有同一条验收条文：{item['id']}")
    ordinal = max([item["ordinal"] for item in existing], default=0) + 1
    if ordinal > 99:
        raise Reject("单条需求的验收条目最多 99 条；超了说明需求该拆了")
    return _write_acceptance(conn, requirement_id, ordinal, text)


def sync_acceptance(conn, requirement_id: str, texts) -> list[dict]:
    """把声明里的验收条文同步成 acceptance 节点：**只补不删**。

    `feature-declare --acceptance` 与 `acceptance-import` 都走这里。重声明时同一条文
    命中既有条目就跳过（幂等）；声明里去掉的条目不会自动删除——删验收要显式 `retract`，
    否则会连带删掉挂在它上面的测试边，声明就不该有这种杀伤力。
    """
    _require_requirement(conn, requirement_id)
    current = acceptance_children(conn, requirement_id)
    have = {item["text"] for item in current}
    ordinal = max([item["ordinal"] for item in current], default=0)
    created: list[dict] = []
    for value in texts:
        text = str(value).strip()
        if not text or text in have:
            continue
        ordinal += 1
        if ordinal > 99:
            raise Reject(f"{requirement_id} 的验收条目超过 99 条；先拆需求再声明")
        created.append(_write_acceptance(conn, requirement_id, ordinal, text))
        have.add(text)
    return created


def import_acceptance(conn, feature_id: str, dry_run: bool = False, skip_requirements=None) -> dict:
    """从 `requirement.attrs.x_acceptance` 幂等生成验收条目。

    对齐口径是 `ordinal` + `text`：已有条目按文本命中就跳过，缺的按当前最大序号往后补。
    这样重复执行不会造重复条目，也不会把人工调整过顺序的条目打乱。
    """
    scope = scope_ids(conn, feature_id)
    skip = set(skip_requirements or ())
    created: list[dict] = []
    existed: list[dict] = []
    no_source: list[str] = []
    skipped: list[str] = []
    for node_id in sorted(scope):
        node = get_node(conn, node_id)
        if node is None or node["kind"] != "requirement":
            continue
        attrs = loads(node["attrs_json"], {})
        raw = attrs.get("x_acceptance")
        if not isinstance(raw, list):
            no_source.append(node_id)
            continue
        if node_id in skip:
            skipped.append(node_id)
            continue
        current = acceptance_children(conn, node_id)
        have = {item["text"]: item["id"] for item in current}
        ordinal = max([item["ordinal"] for item in current], default=0)
        for value in raw:
            text = str(value).strip()
            if not text:
                continue
            if text in have:
                existed.append({"requirement": node_id, "id": have[text], "text": text})
                continue
            ordinal += 1
            if ordinal > 99:
                raise Reject(f"{node_id} 的验收条目超过 99 条；先拆需求再导入")
            if dry_run:
                created.append({"requirement": node_id, "id": acceptance_id(node_id, ordinal), "ordinal": ordinal, "text": text})
            else:
                created.append({"requirement": node_id, **_write_acceptance(conn, node_id, ordinal, text)})
            have[text] = acceptance_id(node_id, ordinal)
    return {
        "feature": feature_id,
        "dry_run": bool(dry_run),
        "created": created,
        "created_count": len(created),
        "existed_count": len(existed),
        "requirements_without_source": no_source,
        "skipped_requirements": skipped,
    }


def _verifies_index(conn) -> dict[str, dict[str, bool]]:
    """目标节点 id → {testcase id: 是否带代码锚点}（只看 kind=testcase 的 src）。

    锚点 = 节点自身的 `path` 或 `attrs.path`。只有"测试规格"（没写路径）的 testcase 不算
    交付证据——否则"有测试指向"又退化成"有个节点说有测试"。
    """
    index: dict[str, dict[str, bool]] = {}
    for row in conn.execute(
        "SELECT e.src AS src, e.dst AS dst, n.path AS path, n.attrs_json AS attrs_json "
        "FROM edges e JOIN nodes n ON n.id = e.src "
        "WHERE e.kind = ? AND n.kind = 'testcase'",
        (VERIFIES_EDGE_KIND,),
    ).fetchall():
        attrs = loads(row["attrs_json"], {})
        anchored = bool(row["path"]) or bool(attrs.get("path"))
        index.setdefault(row["dst"], {})[row["src"]] = anchored
    return index


def _anchored_verifiers(index: dict[str, dict[str, bool]], node_id: str) -> list[str]:
    return [src for src, anchored in index.get(node_id, {}).items() if anchored]


def trace_report(conn, feature: dict, limit: int = 20, requirement: str | None = None) -> dict:
    """需求→验收→测试矩阵。只读，不改任何状态。

    `requirement:{feature}:main` 是声明入口自动建的**聚合需求**：feature 拆成多条子需求时，
    它只是伞节点，不该因为自己没有验收条目而被判缺口（真实项目里最先撞到这条——
    四仓重构 191 条子需求 + 1 条 main，main 没有 x_acceptance）。它仍是需求的唯一例外：
    如果它是作用域里唯一的需求，或者自己登记了验收条目，就按普通需求算。

    `requirement` 给定 id 时只算这一条需求（钻取用；聚合豁免按该 feature 的全量需求判断）。
    """
    if limit < 0:
        raise Reject("--limit 必须是非负整数")
    scope = sorted(scope_ids(conn, feature["id"]))
    verified = _verifies_index(conn)
    requirement_ids = [
        node_id
        for node_id in scope
        if (node := get_node(conn, node_id)) is not None and node["kind"] == "requirement"
    ]
    main_id = f"requirement:{feature['id']}:main"
    aggregate_main = main_id in requirement_ids and len(requirement_ids) > 1
    item_rows: list[dict] = []
    if requirement is not None:
        if requirement not in requirement_ids:
            raise Reject(f"需求不在该 feature 作用域内：{requirement}")
        requirement_ids = [requirement]
    rows: list[dict] = []
    missing: list[dict] = []
    without_acceptance: list[str] = []
    aggregates: list[str] = []
    tail: list[tuple[int, dict]] = []
    acceptance_total = 0
    acceptance_tested = 0
    acceptance_spec_only = 0
    for node_id in requirement_ids:
        node = get_node(conn, node_id)
        items = acceptance_children(conn, node_id)
        anchored = [item for item in items if _anchored_verifiers(verified, item["id"])]
        spec_only = [
            item for item in items
            if verified.get(item["id"]) and not _anchored_verifiers(verified, item["id"])
        ]
        acceptance_total += len(items)
        acceptance_tested += len(anchored)
        acceptance_spec_only += len(spec_only)
        gaps = [item for item in items if not _anchored_verifiers(verified, item["id"])]
        is_aggregate = aggregate_main and node_id == main_id and not items
        if is_aggregate:
            aggregates.append(node_id)
        elif not items:
            without_acceptance.append(node_id)
        for item in gaps:
            missing.append({"requirement": node_id, "acceptance": item["id"], "text": item["text"]})
        priority = loads(node["attrs_json"], {}).get("x_priority")
        row = {
            "id": node_id,
            "name": node["name"],
            "acceptance": len(items),
            "tested": len(anchored),
            "spec_only": len(spec_only),
            "missing_count": len(gaps),
            "direct_tests": len(_anchored_verifiers(verified, node_id)),
            "missing": [item["id"] for item in gaps][:limit],
            "without_acceptance": not items and not is_aggregate,
            "aggregate": is_aggregate,
            "priority": priority,
            "priority_rank": priority_rank(priority),
        }
        rows.append(row)
        tail.append((len(gaps), row))
        if requirement is not None:
            for item in items:
                item_tests = _anchored_verifiers(verified, item["id"])
                item_rows.append({
                    "id": item["id"],
                    "text": item["text"],
                    "ordinal": item["ordinal"],
                    "tested": bool(item_tests),
                    "tests": sorted(item_tests),
                })
    requirements = len(rows)
    applicable = requirements > 0
    unknown = applicable and acceptance_total == 0
    complete = applicable and not missing and not without_acceptance
    # 缺口最多的需求：让红区直接可行动（gate FAIL 里也用它）
    # 缺口数量排序之外还要看优先级：P0 的 2 条缺口比 P2 的 6 条更该先补
    top_gaps = [
        {
            "id": row["id"],
            "missing": count,
            "acceptance": row["acceptance"],
            "priority": row["priority"],
        }
        for count, row in sorted(
            tail, key=lambda pair: (pair[1]["priority_rank"], -pair[0], pair[1]["id"])
        )[:5]
        if count
    ]
    return {
        "feature": feature["id"],
        "generation": feature["generation"],
        "requirements": requirements,
        "applicable": applicable,
        "ok": (not applicable) or complete,
        "requirement": requirement,
        "items": item_rows,
        "top_gaps": top_gaps,
        "summary": {
            "requirements": requirements,
            "requirements_with_acceptance": requirements - len(without_acceptance) - len(aggregates),
            "requirements_without_acceptance": len(without_acceptance),
            "aggregate_requirements": len(aggregates),
            "acceptance_items": acceptance_total,
            "acceptance_tested": acceptance_tested,
            "acceptance_spec_only": acceptance_spec_only,
            "acceptance_missing": len(missing),
            "complete": complete,
            "unknown": unknown,
        },
        "aggregate_requirements": aggregates[:limit],
        "requirements_detail": rows[:limit] if limit else [],
        "without_acceptance": without_acceptance[:limit],
        "missing": missing[:limit],
        "truncated": len(missing) > limit or len(without_acceptance) > limit,
    }
