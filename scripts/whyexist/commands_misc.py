"""导出、契约、校验与 doctor 命令：export / role-prompt / contract / verify / doctor。"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

from .contract import C
from .errors import Reject
from .evidence import evidence_qualifies, sha256_file
from .graph import get_node
from .jsonio import dumps, loads
from .temp import make_temp_dir, temp_dir
from .work import get_work
from .workflow import ensure_feature, scope_ids

SKILL_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_ROOT = Path.cwd() / ".why-exist"

def cmd_export(conn, args):
    feature = ensure_feature(conn, args.feature)
    gen = feature["generation"]
    export_dir = args.root_path / "export" / feature["id"]
    export_dir.mkdir(parents=True, exist_ok=True)

    def header() -> str:
        return (
            "---\n"
            f"generation: {gen}\n"
            f"feature_id: {feature['id']}\n"
            "来源: wxg-export\n"
            "说明: 缺的 id 留空，不从任何旧文档补句。\n"
            "---\n\n"
        )

    def write(name, body):
        (export_dir / name).write_text(body, encoding="utf-8")

    def table(columns, rows):
        lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
        if not rows:
            lines.append("| " + " | ".join("" for _ in columns) + " |")
        else:
            for row in rows:
                cells = [str(value if value is not None else "").replace("|", "\\|") for value in row]
                lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)

    scope = set(scope_ids(conn, feature["id"]))
    requirement_rows = []
    requirement_ids = []
    for row in conn.execute("SELECT * FROM nodes WHERE kind='requirement' ORDER BY id").fetchall():
        row = dict(row)
        if row["id"] not in scope:
            continue
        requirement_ids.append(row["id"])
        attrs = loads(row["attrs_json"], {})
        requirement_rows.append([
            row["id"],
            attrs.get("statement") or row["name"],
            "；".join(loads(feature["acceptance_json"], [])),
            "；".join(loads(feature["constraints_json"], [])),
        ])
    write(
        C.EXPORT_FILES[0]["name"],
        header()
        + f"# {C.EXPORT_FILES[0]['title']}\n\n"
        + table(C.EXPORT_FILES[0]["columns"], requirement_rows)
        + "\n",
    )

    use_cases = []
    for req_id in requirement_ids:
        for edge in conn.execute("SELECT src FROM edges WHERE dst=? AND kind='satisfies'", (req_id,)).fetchall():
            node = get_node(conn, edge["src"])
            if node and node["kind"] == "use_case" and node["id"] not in [uc["id"] for uc in use_cases]:
                use_cases.append(node)
    write(
        C.EXPORT_FILES[1]["name"],
        header()
        + f"# {C.EXPORT_FILES[1]['title']}\n\n"
        + table(C.EXPORT_FILES[1]["columns"], [[uc["id"], uc["name"]] for uc in use_cases])
        + "\n",
    )

    arch = []
    for uc in use_cases:
        for edge in conn.execute(
            "SELECT dst FROM edges WHERE src=? AND kind IN ('depends','associates','realizes')", (uc["id"],)
        ).fetchall():
            node = get_node(conn, edge["dst"])
            if node and node["kind"] in ("component", "port"):
                arch.append([node["kind"], node["id"], node["name"]])
    for node_id in sorted(scope):
        node = get_node(conn, node_id)
        if node and node["kind"] == "pattern":
            arch.append([node["kind"], node["id"], node["name"]])
    arch = sorted({tuple(row) for row in arch})
    write(
        C.EXPORT_FILES[2]["name"],
        header()
        + f"# {C.EXPORT_FILES[2]['title']}\n\n"
        + table(C.EXPORT_FILES[2]["columns"], [list(row) for row in arch])
        + "\n",
    )

    operations = []
    for uc in use_cases:
        for edge in conn.execute("SELECT dst FROM edges WHERE src=? AND kind='contains'", (uc["id"],)).fetchall():
            node = get_node(conn, edge["dst"])
            if node and node["kind"] == "operation" and node["id"] not in [op["id"] for op in operations]:
                operations.append(node)
    classifiers = []
    for op in operations:
        for edge in conn.execute("SELECT src FROM edges WHERE dst=? AND kind='contains'", (op["id"],)).fetchall():
            node = get_node(conn, edge["src"])
            if node and node["kind"] == "classifier" and node["id"] not in [cl["id"] for cl in classifiers]:
                classifiers.append(node)
    parameters = []
    parameter_ids = set()
    for op in operations:
        for edge in conn.execute("SELECT dst FROM edges WHERE src=? AND kind='has_input'", (op["id"],)).fetchall():
            node = get_node(conn, edge["dst"])
            if node and node["kind"] == "parameter" and node["id"] not in parameter_ids:
                parameter_ids.add(node["id"])
                parameters.append(node)
    order = {"classifier": 0, "operation": 1, "parameter": 2}
    class_rows = sorted(
        [[node["kind"], node["name"], node["path"], node["symbol"], node["unmapped"]] for node in classifiers + operations + parameters],
        key=lambda row: (order.get(row[0], 9), str(row[1])),
    )
    write(
        C.EXPORT_FILES[3]["name"],
        header()
        + f"# {C.EXPORT_FILES[3]['title']}\n\n"
        + table(C.EXPORT_FILES[3]["columns"], class_rows)
        + "\n",
    )

    steps = []
    for op in operations:
        for edge in conn.execute("SELECT dst FROM edges WHERE src=? AND kind='writes'", (op["id"],)).fetchall():
            sink = get_node(conn, edge["dst"])
            if sink is None or sink["kind"] != "sink":
                continue
            texts = []
            for asserts in conn.execute("SELECT src FROM edges WHERE dst=? AND kind='asserts'", (op["id"],)).fetchall():
                assertion = get_node(conn, asserts["src"])
                if assertion:
                    attrs = loads(assertion["attrs_json"], {})
                    texts.append(attrs.get("text") or assertion["name"] or "")
            steps.append([len(steps) + 1, op["name"], op["symbol"], sink["name"], "；".join(text for text in texts if text)])
    param_rows = []
    for param in parameters:
        attrs = loads(param["attrs_json"], {})
        param_rows.append([param["name"] or param["symbol"], param["unmapped"], dumps(attrs)])
    body = header() + f"# {C.EXPORT_FILES[4]['title']}\n\n" + table(C.EXPORT_FILES[4]["columns"], steps)
    for section in C.EXPORT_FILES[4].get("extra_sections", []):
        body += f"\n\n## {section['title']}\n\n" + table(section["columns"], param_rows)
    write(C.EXPORT_FILES[4]["name"], body + "\n")

    test_rows = []
    test_ids = set()

    def add_test_row(node) -> None:
        if node["id"] in test_ids:
            return
        test_ids.add(node["id"])
        test_rows.append([node["kind"], node["id"], node["name"], node["attrs_json"]])

    for op in operations:
        for edge in conn.execute("SELECT src FROM edges WHERE dst=? AND kind='verifies'", (op["id"],)).fetchall():
            node = get_node(conn, edge["src"])
            if node and node["kind"] == "testcase":
                add_test_row(node)
        for edge in conn.execute("SELECT src FROM edges WHERE dst=? AND kind='asserts'", (op["id"],)).fetchall():
            node = get_node(conn, edge["src"])
            if node and node["kind"] == "assertion":
                add_test_row(node)
    for uc in use_cases:
        for edge in conn.execute("SELECT src FROM edges WHERE dst=? AND kind='verifies'", (uc["id"],)).fetchall():
            node = get_node(conn, edge["src"])
            if node and node["kind"] == "testcase":
                add_test_row(node)
    write(
        C.EXPORT_FILES[5]["name"],
        header()
        + f"# {C.EXPORT_FILES[5]['title']}\n\n"
        + table(C.EXPORT_FILES[5]["columns"], test_rows)
        + "\n",
    )
    return {"dir": str(export_dir), "generation": gen, "steps": len(steps), "files": [entry["name"] for entry in C.EXPORT_FILES]}


# 只读查询命令已搬进 whyexist.query；这里 re-export，保持 CLI 分派不变。
from whyexist.query import (  # noqa: E402
    cmd_find,
    cmd_get,
    cmd_slice,
    resolve_targets,
    slice_payload,
)


def cmd_role_prompt(conn, args):
    role = args.role
    if role not in C.ROLES:
        raise Reject(f"未知角色：{role}")
    root = Path(getattr(args, "root_path", DEFAULT_ROOT)).resolve()
    cli = SKILL_DIR / "scripts" / "wxg.py"
    lines = [
        f"# DSH teammate 角色：{role}",
        "",
        f"你是一次 why-exist-graph 流程中的 `{role}` 角色。",
        f"- 状态库：`{root / 'graph.sqlite'}`",
        f"- CLI：`python \"{cli}\" --root \"{root}\" <command>`",
        "",
        "## 允许命令",
        "",
        "、".join(f"`wxg {name}`" for name in C.ROLES[role]),
        "",
        "## 边界",
        "",
        "- 只读/写你当前 claim_token 对应工单的 target_ids；不要碰别人的 id。",
        "- 不要手改状态库，不要手改 export；所有结论通过命令落库。",
        "- 不臆造：认不出的节点/边标 unmapped；证据不足用 UNKNOWN。",
        "- 领取时带 `--actor <你的成员名>`；审计裁决的 actor 不能等于被审工单的 claimed_by。",
        "- 测试/冒烟/重跑结果用 `evidence-record` 登记，不要只写一段散文。",
    ]
    if role == "audit":
        lines.append("- audit 不领取工单、不 work-finish；用 `wxg work-judge --id <工单> --verdict passed|failed --role audit --actor <你的成员名>` 直接裁决。")
        lines.append("- BehaviorPassed 的裁决前必须已有同 generation、exit_code=0 的 evidence，否则会被拒绝。")
        lines.append("- judge(passed) 前检查 coverage（feature 开启 `--coverage-epsilon` 时）与模式有限应用；每次裁决都会写入 `judge_history`。")
    else:
        lines.append("- 做完后执行 `wxg work-finish --token <token>`，把裁决交给独立 audit 角色。")
        if role in ("model-architecture", "model-structure"):
            lines.append("- 设计模式用 `pattern` 节点：attrs 必须写 `applicability` 与 `not_applicable`，并用 `applies` 边挂到 component/classifier/operation；过度应用会被 UNNECESSARY 咬合。")
        if role == "implement-test":
            lines.append("- 正在改的代码节点把 `attrs.construction` 置 true；完成时用一次不含 `construction` 的 upsert-node 覆盖清掉。gate 会拦未清除的施工标记。")
    lines.append("")
    if args.token:
        lines.extend(["## 你的令牌", "", f"`{args.token}`", ""])
    if args.feature:
        lines.extend(["## feature", "", f"`{args.feature}`", ""])
    return "\n".join(lines)


def cmd_contract(conn, args):
    if args.json:
        return C.contract_json()
    section = args.section
    body = C.main_contract_markdown() if section == "main" else C.full_contract_markdown()
    if args.write:
        target = Path(args.write)
        if not target.is_absolute():
            target = SKILL_DIR / target
        text = target.read_text(encoding="utf-8")
        target.write_text(C.replace_block(text, section, body), encoding="utf-8")
        return {"written": str(target), "section": section}
    return body


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def cmd_verify(conn, args):
    issues = []
    skill_dir = Path(os.environ.get("WXG_SKILL_DIR", str(SKILL_DIR))).resolve()
    skill_md = skill_dir / "SKILL.md"
    contract_md = skill_dir / "references" / "contract.md"
    for path, section in ((skill_md, "main"), (contract_md, "full")):
        if not path.exists():
            issues.append(f"缺少文件：{path}")
            continue
        try:
            actual = C.extract_block(_read(path), section)
        except ValueError as exc:
            issues.append(f"{path.name}: {exc}")
            continue
        expected = (C.main_contract_markdown() if section == "main" else C.full_contract_markdown()).strip("\n")
        if actual != expected:
            issues.append(f"{path.name} 的 {section} 契约块已过期；运行 `wxg contract --write {path.name} --section {section}`")

    # frontmatter：name 必须与契约中的技能名一致
    if skill_md.exists():
        text = _read(skill_md)
        if not text.startswith("---"):
            issues.append("SKILL.md 缺少 YAML frontmatter")
        else:
            front = text.split("---", 2)[1]
            if "name: why-exist-graph" not in front:
                issues.append("SKILL.md frontmatter 的 name 必须是 why-exist-graph")
            if "description:" not in front:
                issues.append("SKILL.md frontmatter 缺少 description")

    # 命令 -> 处理器 / 写入列。处理器分散在多个模块，统一从入口模块取。
    import wxg

    for name in C.COMMANDS:
        handler = getattr(wxg, "cmd_" + name.replace("-", "_"), None)
        if handler is None:
            issues.append(f"命令 {name} 没有处理器")
        if name not in C.WRITE_MODES:
            issues.append(f"命令 {name} 缺少 WRITE_MODES 声明（写入列会失去契约来源）")
    # 角色 -> 命令
    for role, commands in C.ROLES.items():
        for command in commands:
            if command not in C.COMMANDS:
                issues.append(f"角色 {role} 引用了不存在的命令 {command}")
    # kind/边/属性/导出交叉引用
    kinds = {entry["kind"] for entry in C.NODE_KINDS}
    for kind in C.ATTR_SCHEMA:
        if kind not in kinds:
            issues.append(f"ATTR_SCHEMA 含未知 kind：{kind}")
    for kind in C.BIND_EDGE_KIND:
        if kind not in kinds:
            issues.append(f"BIND_EDGE_KIND 含未知 kind：{kind}")
    for entry in C.EXPORT_FILES:
        if not entry["columns"]:
            issues.append(f"导出文件 {entry['name']} 没有列定义")
        for section in entry.get("extra_sections", []):
            if not section.get("columns"):
                issues.append(f"导出文件 {entry['name']} 的附加小节 {section.get('title')} 没有列定义")
    for rel in ("references/design.md", "references/contract.md", "references/quality.md", "tests/test_wxg.py", "CHANGELOG.md"):
        if not (skill_dir / rel).exists():
            issues.append(f"缺少技能资源：{rel}")
    # 导出样例（临时目录走 make_temp_dir：Windows 受限 token 下 tempfile.mkdtemp 的
    # 0o700 DACL 会为空，目录不可写/不可删，见 DSH discussion #4290）
    sample_dir = skill_dir / "references" / "export-sample"
    try:
        import gen_sample  # noqa: WPS433

        with temp_dir("wxg-verify-") as tmp:
            state = gen_sample.build(tmp / "state")
            produced = state / "export" / "feat-demo"
            for entry in C.EXPORT_FILES:
                name = entry["name"]
                expected_file = sample_dir / "feat-demo" / name
                if not expected_file.exists():
                    issues.append(f"缺少导出样例：references/export-sample/feat-demo/{name}")
                    continue
                if (produced / name).read_text(encoding="utf-8") != expected_file.read_text(encoding="utf-8"):
                    issues.append(f"导出样例过期：references/export-sample/feat-demo/{name}")
    except Exception as exc:  # pragma: no cover - 防御性
        issues.append(f"导出样例自检失败：{exc}")

    if issues:
        return {"ok": False, "issues": issues}
    return {"ok": True, "checks": ["contract-blocks", "commands", "roles", "kinds", "write-modes", "export-sample"], "version": C.contract_version_line()}


def doctor_report(conn) -> list[dict]:
    """检查状态库内部一致性；只读。"""
    issues: list[dict] = []
    existing = {row["id"] for row in conn.execute("SELECT id FROM nodes").fetchall()}

    for row in conn.execute(
        "SELECT b.id, b.node_id, b.verdict FROM bites b LEFT JOIN nodes n ON n.id=b.node_id WHERE n.id IS NULL"
    ).fetchall():
        issues.append({"check": "dangling-bite", "bite_id": row["id"], "node_id": row["node_id"], "verdict": row["verdict"]})
    for row in conn.execute(
        "SELECT e.id, e.src, e.dst, e.kind FROM edges e "
        "LEFT JOIN nodes s ON s.id=e.src LEFT JOIN nodes d ON d.id=e.dst "
        "WHERE s.id IS NULL OR d.id IS NULL"
    ).fetchall():
        issues.append({"check": "orphan-edge", "edge_id": row["id"], "src": row["src"], "dst": row["dst"], "kind": row["kind"]})
    for row in conn.execute(
        "SELECT e.id, e.src, e.dst, s.kind AS src_kind, d.kind AS dst_kind FROM edges e "
        "JOIN nodes s ON s.id=e.src JOIN nodes d ON d.id=e.dst WHERE e.kind='applies'"
    ).fetchall():
        if row["src_kind"] not in ("component", "classifier", "operation") or row["dst_kind"] != "pattern":
            issues.append({
                "check": "applies-invalid",
                "edge": row["id"],
                "src_kind": row["src_kind"],
                "dst_kind": row["dst_kind"],
            })
    for row in conn.execute(
        "SELECT f.feature_id, f.node_id FROM feature_nodes f LEFT JOIN nodes n ON n.id=f.node_id WHERE n.id IS NULL"
    ).fetchall():
        issues.append({"check": "feature-node-missing", "feature_id": row["feature_id"], "node_id": row["node_id"]})

    for item in conn.execute("SELECT * FROM work_items").fetchall():
        if item["kind"] == "audit":
            continue
        for pattern in loads(item["target_ids"], []):
            if pattern.endswith("*"):
                continue
            if pattern not in existing:
                issues.append({"check": "work-target-missing", "work_item": item["id"], "node_id": pattern})
        for node_id in loads(item["evidence_ids"], []):
            if node_id not in existing:
                issues.append({"check": "work-evidence-missing", "work_item": item["id"], "node_id": node_id})
    for item in conn.execute(
        "SELECT id, status, claim_token FROM work_items WHERE claim_token IS NOT NULL AND status<>'claimed'"
    ).fetchall():
        issues.append({"check": "token-on-inactive", "work_item": item["id"], "status": item["status"]})

    for item in conn.execute(
        "SELECT id, status, claim_token, kind, claimed_by, judged_by, claimed_at FROM work_items"
    ).fetchall():
        if item["status"] in ("claimed", "submitted") and not item["claimed_by"]:
            issues.append({"check": "claim-missing-actor", "work_item": item["id"], "status": item["status"]})
        if item["status"] == "claimed" and not item["claimed_at"]:
            issues.append({"check": "claim-missing-timestamp", "work_item": item["id"]})
        if item["kind"] == "audit" and item["status"] in ("passed", "failed"):
            if not item["judged_by"]:
                issues.append({"check": "audit-missing-actor", "work_item": item["id"]})
            else:
                dep = conn.execute(
                    "SELECT depends_on FROM work_items WHERE id=?", (item["id"],)
                ).fetchone()
                deps = loads(dep["depends_on"], []) if dep else []
                subject = get_work(conn, deps[0]) if deps else None
                if (
                    subject is not None
                    and item["judged_by"] not in ("legacy",)
                    and subject["claimed_by"] not in (None, "", "legacy")
                    and item["judged_by"] == subject["claimed_by"]
                ):
                    issues.append({
                        "check": "audit-not-independent",
                        "audit": item["id"],
                        "subject": subject["id"],
                        "actor": item["judged_by"],
                    })

    for item in conn.execute("SELECT id, claimed_by, judged_by FROM work_items").fetchall():
        if item["claimed_by"] == "legacy":
            issues.append({"check": "legacy-identity", "work_item": item["id"], "field": "claimed_by"})
        if item["judged_by"] == "legacy":
            issues.append({"check": "legacy-identity", "work_item": item["id"], "field": "judged_by"})

    for item in conn.execute("SELECT * FROM evidence").fetchall():
        if item["generation"] is None:
            issues.append({"check": "evidence-missing-generation", "evidence": item["id"]})
        if item["exit_code"] != 0:
            issues.append({"check": "evidence-exit-nonzero", "evidence": item["id"], "exit_code": item["exit_code"]})
        if item["work_item_id"]:
            work = get_work(conn, item["work_item_id"])
            if work is None:
                issues.append({"check": "evidence-work-missing", "evidence": item["id"], "work_item": item["work_item_id"]})
        if item["artifact_path"]:
            artifact = Path(item["artifact_path"])
            if not artifact.is_file():
                issues.append({"check": "evidence-artifact-missing", "evidence": item["id"], "path": item["artifact_path"]})
            elif item["artifact_sha256"] and sha256_file(artifact) != item["artifact_sha256"]:
                issues.append({"check": "evidence-artifact-changed", "evidence": item["id"], "path": item["artifact_path"]})

    for item in conn.execute("SELECT * FROM judge_history").fetchall():
        if not item["actor"]:
            issues.append({"check": "judge-history-actor", "history": item["id"]})
        if item["verdict"] not in ("passed", "failed"):
            issues.append({"check": "judge-history-verdict", "history": item["id"], "verdict": item["verdict"]})
        if get_work(conn, item["work_item_id"]) is None:
            issues.append({
                "check": "judge-history-work-missing",
                "history": item["id"],
                "work_item": item["work_item_id"],
            })
    for item in conn.execute("SELECT id FROM work_items WHERE kind<>'audit' AND status='passed'").fetchall():
        if conn.execute("SELECT 1 FROM judge_history WHERE work_item_id=? LIMIT 1", (item["id"],)).fetchone() is None:
            issues.append({"check": "judge-history-missing", "work_item": item["id"]})

    for change in conn.execute("SELECT * FROM changes").fetchall():
        if change["from_generation"] >= change["to_generation"]:
            issues.append({"check": "change-generation", "change": change["id"]})
        if change["from_condition"] not in C.CONDITIONS:
            issues.append({"check": "change-from-condition", "change": change["id"]})
            continue
        rows = conn.execute(
            "SELECT name, status FROM conditions WHERE feature_id=? AND generation=?",
            (change["feature_id"], change["to_generation"]),
        ).fetchall()
        if not rows:
            issues.append({
                "check": "change-conditions-missing",
                "change": change["id"],
                "generation": change["to_generation"],
            })
            continue
        boundary = C.CONDITIONS.index(change["from_condition"])
        for row in rows:
            if row["name"] in ("Accepted", "Ready"):
                continue
            if C.CONDITIONS.index(row["name"]) < boundary and row["status"] != 1:
                issues.append({
                    "check": "change-inheritance",
                    "change": change["id"],
                    "condition": row["name"],
                })

    for node in conn.execute("SELECT id, attrs_json FROM nodes WHERE kind='pattern'").fetchall():
        attrs = loads(node["attrs_json"], {})
        missing = [key for key in ("applicability", "not_applicable") if not str(attrs.get(key) or "").strip()]
        if missing:
            issues.append({"check": "pattern-unjustified", "node": node["id"], "missing": missing})

    for feature in conn.execute("SELECT * FROM features").fetchall():
        generations = {
            row["generation"]
            for row in conn.execute("SELECT DISTINCT generation FROM conditions WHERE feature_id=?", (feature["id"],)).fetchall()
        }
        if feature["generation"] not in generations:
            issues.append({"check": "missing-generation-conditions", "feature_id": feature["id"], "generation": feature["generation"]})
        for generation in sorted(generations):
            rows = conn.execute(
                "SELECT name, status FROM conditions WHERE feature_id=? AND generation=?",
                (feature["id"], generation),
            ).fetchall()
            names = {row["name"] for row in rows}
            if len(rows) != len(C.CONDITIONS) or names != set(C.CONDITIONS):
                issues.append({"check": "condition-rows", "feature_id": feature["id"], "generation": generation, "count": len(rows)})
                continue
            flags = {row["name"]: row["status"] for row in rows}
            expected_ready = int(all(flags[name] == 1 for name in C.CONDITIONS if name != "Ready"))
            if flags["Ready"] != expected_ready:
                issues.append({
                    "check": "ready-inconsistent",
                    "feature_id": feature["id"],
                    "generation": generation,
                    "ready": flags["Ready"],
                    "expected": expected_ready,
                })
            if flags.get("BehaviorPassed") == 1:
                if not evidence_qualifies(conn, feature["id"], generation):
                    issues.append({
                        "check": "behavior-passed-without-evidence",
                        "feature_id": feature["id"],
                        "generation": generation,
                    })

    # 元数据版本：旧库的 contract_version 不会自动更新，doctor 负责提示与刷新。
    for key, expected in (("contract_version", C.CONTRACT_VERSION), ("schema_version", str(C.SCHEMA_VERSION))):
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None or row["value"] != expected:
            issues.append({"check": "meta-version", "key": key, "found": row["value"] if row else None, "expected": expected})

    items = {row["id"]: dict(row) for row in conn.execute("SELECT * FROM work_items").fetchall()}
    for item in items.values():
        if item["kind"] == "audit":
            continue
        audits = [
            row for row in items.values()
            if row["kind"] == "audit" and loads(row["depends_on"], []) == [item["id"]]
        ]
        if item["status"] == "passed" and (not audits or audits[0]["status"] != "passed"):
            issues.append({"check": "passed-without-audit", "work_item": item["id"]})
        for audit in audits:
            if audit["status"] == "passed" and item["status"] != "passed":
                issues.append({"check": "audit-passed-subject-not", "audit": audit["id"], "subject": item["id"]})
    return issues


def cmd_doctor(conn, args):
    before = doctor_report(conn)
    fixed: dict = {}
    if args.fix:
        fixed["dangling_bites"] = conn.execute(
            "DELETE FROM bites WHERE node_id NOT IN (SELECT id FROM nodes)"
        ).rowcount
        fixed["orphan_edges"] = conn.execute(
            "DELETE FROM edges WHERE src NOT IN (SELECT id FROM nodes) OR dst NOT IN (SELECT id FROM nodes)"
        ).rowcount
        fixed["feature_nodes"] = conn.execute(
            "DELETE FROM feature_nodes WHERE node_id NOT IN (SELECT id FROM nodes)"
        ).rowcount
        existing = {row["id"] for row in conn.execute("SELECT id FROM nodes").fetchall()}
        refs = 0
        for item in conn.execute("SELECT id, kind, target_ids, evidence_ids FROM work_items").fetchall():
            if item["kind"] == "audit":
                continue
            targets = loads(item["target_ids"], [])
            evidence = loads(item["evidence_ids"], [])
            new_targets = [pattern for pattern in targets if pattern.endswith("*") or pattern in existing]
            new_evidence = [node_id for node_id in evidence if node_id in existing]
            if new_targets != targets or new_evidence != evidence:
                conn.execute(
                    "UPDATE work_items SET target_ids=?, evidence_ids=? WHERE id=?",
                    (dumps(new_targets), dumps(new_evidence), item["id"]),
                )
                refs += 1
        fixed["work_refs"] = refs
        fixed["tokens"] = conn.execute(
            "UPDATE work_items SET claim_token=NULL WHERE claim_token IS NOT NULL AND status<>'claimed'"
        ).rowcount
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('contract_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (C.CONTRACT_VERSION,),
        )
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(C.SCHEMA_VERSION),),
        )
        fixed["meta"] = 1
    after = doctor_report(conn)
    for issue in after:
        issue["fixable"] = issue["check"] in C.DOCTOR_FIXABLE_CHECKS
    by_check = dict(Counter(issue["check"] for issue in after))
    unfixable = [issue for issue in after if not issue["fixable"]]
    return {
        "ok": not after,
        "issue_count": len(after),
        "fixable_count": sum(1 for issue in after if issue["fixable"]),
        # 修不了的问题单独列出：它们要么需要裁决、要么需要改设计，自动修等于替人做决定。
        "unfixable_count": len(unfixable),
        "unfixable_checks": sorted({issue["check"] for issue in unfixable}),
        "by_check": by_check,
        "truncated": len(after) > 200,
        "issues": after[:200],
        "fixed": fixed,
    }


