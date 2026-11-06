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

from .errors import Reject
from .graph import get_node, upsert_edge, upsert_node
from .jsonio import loads
from .workflow import scope_ids

ACCEPTANCE_EDGE_KIND = "has_acceptance"
VERIFIES_EDGE_KIND = "verifies"


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


def _verifies_index(conn) -> dict[str, set[str]]:
    """目标节点 id → 指向它的 testcase id 集合（只看 kind=testcase 的 src）。"""
    index: dict[str, set[str]] = {}
    for row in conn.execute(
        "SELECT e.src AS src, e.dst AS dst FROM edges e JOIN nodes s ON s.id = e.src "
        "WHERE e.kind = ? AND s.kind = 'testcase'",
        (VERIFIES_EDGE_KIND,),
    ).fetchall():
        index.setdefault(row["dst"], set()).add(row["src"])
    return index


def trace_report(conn, feature: dict, limit: int = 20) -> dict:
    """需求→验收→测试矩阵。只读，不改任何状态。"""
    if limit < 0:
        raise Reject("--limit 必须是非负整数")
    scope = sorted(scope_ids(conn, feature["id"]))
    verified = _verifies_index(conn)
    rows: list[dict] = []
    missing: list[dict] = []
    without_acceptance: list[str] = []
    acceptance_total = 0
    acceptance_tested = 0
    for node_id in scope:
        node = get_node(conn, node_id)
        if node is None or node["kind"] != "requirement":
            continue
        items = acceptance_children(conn, node_id)
        tested = [item for item in items if verified.get(item["id"])]
        acceptance_total += len(items)
        acceptance_tested += len(tested)
        gaps = [item for item in items if not verified.get(item["id"])]
        if not items:
            without_acceptance.append(node_id)
        for item in gaps:
            missing.append({"requirement": node_id, "acceptance": item["id"], "text": item["text"]})
        rows.append({
            "id": node_id,
            "name": node["name"],
            "acceptance": len(items),
            "tested": len(tested),
            "direct_tests": len(verified.get(node_id, ())),
            "missing": [item["id"] for item in gaps][:limit],
            "without_acceptance": not items,
        })
    requirements = len(rows)
    applicable = requirements > 0
    unknown = applicable and acceptance_total == 0
    complete = applicable and not missing and not without_acceptance
    return {
        "feature": feature["id"],
        "generation": feature["generation"],
        "requirements": requirements,
        "applicable": applicable,
        "ok": (not applicable) or complete,
        "summary": {
            "requirements": requirements,
            "requirements_with_acceptance": requirements - len(without_acceptance),
            "requirements_without_acceptance": len(without_acceptance),
            "acceptance_items": acceptance_total,
            "acceptance_tested": acceptance_tested,
            "acceptance_missing": len(missing),
            "complete": complete,
            "unknown": unknown,
        },
        "requirements_detail": rows[:limit] if limit else [],
        "without_acceptance": without_acceptance[:limit],
        "missing": missing[:limit],
        "truncated": len(missing) > limit or len(without_acceptance) > limit,
    }
