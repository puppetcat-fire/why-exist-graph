"""wxg 端到端与一致性测试。

运行：python -m unittest discover -s .dsh/skills/why-exist-graph/tests -v
只依赖标准库；每个用例使用独立临时状态库。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
WXG = SKILL / "scripts" / "wxg.py"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

sys.path.insert(0, str(SKILL / "scripts"))
import wxg  # noqa: E402  (只为复用 make_temp_dir：Windows 受限 token 下 tempfile 的 0o700 目录不可写)

SHOP_PY = '''"""测试夹具：一个很小的订单仓。"""


class OrderRepo:
    def __init__(self, conn):
        self.conn = conn

    def save(self, order):
        self.conn.execute("insert into orders values (?)", (order["id"],))
        return order["id"]


def create_order(repo, data):
    order = {"id": data["id"], "status": "new"}
    repo.save(order)
    return order["id"]
'''


class WxgTestCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = wxg.make_temp_dir("wxg-test-")
        # Windows 上 tempfile 的根可能是 8.3 短路径（如 C:\Users\RUNNER~1\...），
        # 而 wxg 会把 --root 解析成真实长路径；统一成 realpath 后断言与 CLI 输出可比。
        self.base = Path(self._tmpdir).resolve()
        self.root = self.base / "state"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        (self.repo / "shop.py").write_text(SHOP_PY, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ---------------- 辅助

    def cli(self, *args, expect=0):
        proc = subprocess.run(
            [sys.executable, str(WXG), "--root", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=ENV,
        )
        output = proc.stdout.strip()
        if expect is not None:
            if proc.returncode != expect:
                self.fail(f"命令 {args} 退出码 {proc.returncode}，期望 {expect}\nstdout={proc.stdout}\nstderr={proc.stderr}")
        if not output:
            if proc.returncode != 0 and proc.stderr.strip():
                try:
                    return json.loads(proc.stderr.strip())
                except json.JSONDecodeError:
                    return proc.stderr.strip()
            return {}
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return output

    def init_repo(self):
        self.cli("init")
        self.cli("repo-add", "--id", "demo", "--path", str(self.repo))

    def declare(self, feature="feat-x", statement="创建订单。", acceptance=None, constraints=None):
        return self.cli(
            "feature-declare",
            "--id", feature,
            "--name", f"演示 {feature}",
            "--statement", statement,
            "--acceptance", json.dumps(acceptance or ["返回成功"], ensure_ascii=False),
            "--constraints", json.dumps(constraints or ["不改产品代码"], ensure_ascii=False),
        )

    def status(self, feature):
        return self.cli("feature-status", "--id", feature)

    def open_targets(self, feature, kind, patterns):
        return self.cli("work-open", "--feature", feature, "--kind", kind, "--target-ids", json.dumps(patterns, ensure_ascii=False))

    def claim(self, role, expect=0, allow_product_code=False, actor=None):
        args = ["work-claim", "--role", role, "--actor", actor or f"agent-{role}"]
        if allow_product_code:
            args.append("--allow-product-code")
        return self.cli(*args, expect=expect)

    def bite(self, node, verdict, feature=None, reason=None, actor="agent-lead"):
        args = ["bite", "--node", node, "--verdict", verdict, "--actor", actor]
        if feature:
            args += ["--feature", feature]
        if reason:
            args += ["--reason", reason]
        return self.cli(*args)

    def upsert(self, token, payload):
        return self.cli("upsert-node", "--token", token, "--data", json.dumps(payload, ensure_ascii=False))

    def edge(self, token, src, dst, kind):
        return self.cli("upsert-edge", "--token", token, "--data", json.dumps({"src": src, "dst": dst, "kind": kind}, ensure_ascii=False))

    def bind(self, token, node_id, bind_to):
        return self.cli("bind", "--token", token, "--node-id", node_id, "--bind-to", bind_to)

    def finish(self, token):
        return self.cli("work-finish", "--token", token)

    def judge(self, work_item_id, verdict="passed", reason=None, actor="auditor-1", expect=0):
        args = ["work-judge", "--id", work_item_id, "--verdict", verdict, "--role", "audit", "--actor", actor]
        if reason:
            args.extend(["--fail-reason", reason])
        return self.cli(*args, expect=expect)

    def db(self):
        return sqlite3.connect(self.root / "graph.sqlite")

    def db_snapshot(self):
        conn = self.db()
        try:
            return {
                table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
                for table in ("meta", "repos", "nodes", "edges", "features", "conditions",
                              "work_items", "feature_nodes", "evidence", "bites")
            }
        finally:
            conn.close()

    def import_scan(self, feature, repo_file="shop.py"):
        prepared = self.cli("import-file", "--file", str(self.repo / repo_file), "--feature", feature, "--prepare")
        self.assertGreater(prepared["nodes"], 0)
        scan = self.claim("scan")
        written = self.cli("import-file", "--file", str(self.repo / repo_file), "--token", scan["claim_token"])
        self.assertGreater(written["nodes_inserted"], 0)
        return scan, written

    def complete_through_implement(self, feature, audit_actor="auditor-1"):
        """不写图的快速推进：前五个条件全部 passed，observe 单变 ready 并 finish。"""
        for kind in ("model-architecture", "model-structure", "interact", "specify-test", "implement-test"):
            self.open_targets(feature, kind, [f"requirement:{feature}:main"])
            claim = self.claim(kind, allow_product_code=(kind == "implement-test"))
            self.finish(claim["claim_token"])
            self.judge(claim["work_item_id"], actor=audit_actor)
        observe = self.claim("observe")
        self.finish(observe["claim_token"])
        return observe

    # ---------------- 全流程

    def test_full_flow_reaches_pass_gate(self):
        self.init_repo()
        self.declare("feat-full")

        self.open_targets("feat-full", "model-architecture", [
            "use_case:feat-full:*", "actor:feat-full:*", "component:demo:*",
        ])
        arch = self.claim("model-architecture")
        token = arch["claim_token"]
        self.upsert(token, {"id": "use_case:feat-full:uc", "kind": "use_case", "name": "创建订单", "attrs": {"goal": "订单落库"}})
        self.upsert(token, {"id": "actor:feat-full:clerk", "kind": "actor", "name": "店员"})
        self.upsert(token, {"id": "component:demo:app", "kind": "component", "name": "订单服务", "attrs": {"duty": "写库"}})
        self.edge(token, "use_case:feat-full:uc", "requirement:feat-full:main", "satisfies")
        self.edge(token, "actor:feat-full:clerk", "use_case:feat-full:uc", "associates")
        self.edge(token, "use_case:feat-full:uc", "component:demo:app", "associates")
        self.finish(token)
        self.judge(arch["work_item_id"])
        self.assertEqual(self.status("feat-full")["conditions"]["ArchitectureReconciled"], 1)

        self.open_targets("feat-full", "model-structure", ["classifier:demo:*", "property:demo:*"])
        structure = self.claim("model-structure")
        token = structure["claim_token"]
        self.upsert(token, {"id": "classifier:demo:shop.py:OrderRepo", "kind": "classifier", "name": "OrderRepo"})
        self.upsert(token, {"id": "property:demo:shop.py:OrderRepo.conn", "kind": "property", "name": "conn"})
        self.edge(token, "classifier:demo:shop.py:OrderRepo", "property:demo:shop.py:OrderRepo.conn", "contains")
        self.finish(token)
        self.judge(structure["work_item_id"])

        self.open_targets("feat-full", "interact", [
            "operation:demo:*", "sink:demo:*", "parameter:feat-full:*", "assertion:feat-full:*",
            "use_case:feat-full:*",
        ])
        interact = self.claim("interact")
        token = interact["claim_token"]
        op = "operation:demo:shop.py:OrderRepo.save"
        self.upsert(token, {"id": op, "kind": "operation", "name": "save", "attrs": {"success_code": "code===1"}})
        self.edge(token, "use_case:feat-full:uc", op, "contains")
        self.upsert(token, {"id": "sink:demo:orders", "kind": "sink", "name": "orders", "attrs": {"table": "orders"}})
        self.edge(token, op, "sink:demo:orders", "writes")
        self.upsert(token, {"id": "parameter:feat-full:order_id", "kind": "parameter", "name": "order_id", "attrs": {"column": "order_id"}})
        self.bind(token, "parameter:feat-full:order_id", op)
        self.upsert(token, {"id": "assertion:feat-full:code", "kind": "assertion", "name": "成功码", "attrs": {"text": "code===1"}})
        self.bind(token, "assertion:feat-full:code", op)
        self.finish(token)
        self.judge(interact["work_item_id"])

        self.open_targets("feat-full", "specify-test", ["testcase:feat-full:*", "operation:demo:*"])
        spec = self.claim("specify-test")
        token = spec["claim_token"]
        self.upsert(token, {"id": "testcase:feat-full:test-save", "kind": "testcase", "name": "save 成功", "attrs": {"path": "tests/test_shop.py"}})
        self.edge(token, "testcase:feat-full:test-save", op, "verifies")
        self.finish(token)
        self.judge(spec["work_item_id"])

        self.open_targets("feat-full", "implement-test", ["testcase:feat-full:*"])
        impl = self.claim("implement-test", allow_product_code=True)
        self.finish(impl["claim_token"])
        self.judge(impl["work_item_id"])

        # BehaviorPassed 需要 exit_code=0 的 evidence；先登记再裁决。
        self.cli("evidence-record", "--feature", "feat-full", "--name", "unittest",
                 "--command", "python -m unittest", "--actor", "auditor-1")
        observe = self.claim("observe")
        self.finish(observe["claim_token"])
        self.judge(observe["work_item_id"])

        result = self.cli("gate", "--feature", "feat-full", "--json")
        self.assertEqual(result["result"], "PASS", result)
        self.assertTrue(result["evidence_ok"])
        status = self.status("feat-full")
        self.assertEqual(status["conditions"]["Ready"], 1)

        exported = self.cli("export", "--feature", "feat-full")
        dump = Path(exported["dir"])
        self.assertTrue((dump / "07-数据流.md").exists())
        flow = (dump / "07-数据流.md").read_text(encoding="utf-8")
        self.assertIn("| 1 | save |", flow)

    def test_redeclare_starts_new_generation_without_deadlock(self):
        self.init_repo()
        self.declare("feat-re")
        self.open_targets("feat-re", "model-architecture", ["use_case:feat-re:*"])
        arch = self.claim("model-architecture")
        token = arch["claim_token"]
        self.upsert(token, {"id": "use_case:feat-re:uc", "kind": "use_case", "name": "旧用例"})
        self.finish(token)
        self.judge(arch["work_item_id"])
        self.assertEqual(self.status("feat-re")["conditions"]["ArchitectureReconciled"], 1)

        declared = self.declare("feat-re", statement="第二代声明。")
        self.assertEqual(declared["generation"], 2)
        status = self.status("feat-re")
        self.assertEqual(status["conditions"]["Accepted"], 1)
        self.assertEqual(status["conditions"]["ArchitectureReconciled"], 0)
        self.assertEqual(status["conditions"]["Ready"], 0)
        self.assertIn("work:feat-re:g2:model-architecture", [item["id"] for item in status["work_items"]])

        # 旧一代工单被 supersede，当前代仍可领取 —— 不会出现旧 passed 挡住新条件。
        conn = sqlite3.connect(self.root / "graph.sqlite")
        old = conn.execute(
            "SELECT status FROM work_items WHERE id='work:feat-re:g1:model-architecture'"
        ).fetchone()
        conn.close()
        self.assertEqual(old[0], "superseded")
        second = self.claim("model-architecture")
        self.assertTrue(second["claim_token"])

    def test_gate_is_read_only(self):
        self.init_repo()
        self.declare("feat-ro")
        db = self.root / "graph.sqlite"
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        self.cli("gate", "--feature", "feat-ro", "--json", expect=1)
        after = hashlib.sha256(db.read_bytes()).hexdigest()
        self.assertEqual(before, after, "gate 不得写状态库")

    def test_bite_verdicts_are_validated_and_visible_to_gate(self):
        self.init_repo()
        self.declare("feat-bite")
        bad = self.cli("bite", "--node", "requirement:feat-bite:main", "--verdict", "NO_SUCH", "--actor", "agent-lead", expect=2)
        self.assertIn("invalid choice", bad)
        self.bite("requirement:feat-bite:main", "UNNECESSARY", feature="feat-bite", reason="示例")
        gate = self.cli("gate", "--feature", "feat-bite", "--json", expect=1)
        self.assertEqual(gate["result"], "FAIL")
        self.assertIn("UNNECESSARY/HOLLOW", gate["reason"])
        self.bite("requirement:feat-bite:main", "KEEP", feature="feat-bite", reason="反证")
        gate = self.cli("gate", "--feature", "feat-bite", "--json", expect=1)
        self.assertEqual(gate["result"], "FAIL")
        self.assertNotIn("UNNECESSARY/HOLLOW", gate["reason"])
        status = self.status("feat-bite")
        self.assertEqual([item["verdict"] for item in status["bites"]], ["UNNECESSARY", "KEEP"])

    def test_failed_judge_resets_condition_chain(self):
        self.init_repo()
        self.declare("feat-fail")
        arch = self.claim("model-architecture")
        self.finish(arch["claim_token"])
        self.judge(arch["work_item_id"], verdict="failed", reason="证据不足")
        status = self.status("feat-fail")
        self.assertEqual(status["conditions"]["ArchitectureReconciled"], 0)
        self.assertEqual(status["conditions"]["Ready"], 0)

    def test_python_import_and_idempotent_reimport(self):
        self.init_repo()
        self.declare("feat-imp")
        prepared = self.cli("import-file", "--file", str(self.repo / "shop.py"), "--feature", "feat-imp", "--prepare")
        self.assertGreater(prepared["nodes"], 0)
        scan = self.claim("scan")
        token = scan["claim_token"]
        first = self.cli("import-file", "--file", str(self.repo / "shop.py"), "--token", token)
        self.assertGreater(first["nodes_inserted"], 0)
        second = self.cli("import-file", "--file", str(self.repo / "shop.py"), "--token", token)
        self.assertEqual(second["nodes_inserted"], 0)
        self.assertGreater(second["nodes_updated"], 0)
        found = self.cli("find", "--kind", "classifier")
        self.assertTrue(any(node["name"] == "OrderRepo" for node in found["nodes"]))
        self.finish(token)
        self.judge(scan["work_item_id"])
        listed = self.cli("work-list", "--feature", "feat-imp")
        self.assertEqual([item["status"] for item in listed["work_items"] if item["kind"] == "scan"], ["passed"])

    def test_reimport_preserves_design_attrs(self):
        self.init_repo()
        self.declare("feat-attrs")
        scan, _ = self.import_scan("feat-attrs")
        classifier = "classifier:demo:shop.py:OrderRepo"
        conn = self.db()
        row = conn.execute("SELECT attrs_json FROM nodes WHERE id=?", (classifier,)).fetchone()
        attrs = json.loads(row[0])
        attrs["duty"] = "订单持久化（设计角色写入）"
        conn.execute("UPDATE nodes SET attrs_json=? WHERE id=?", (json.dumps(attrs, ensure_ascii=False), classifier))
        conn.commit()
        conn.close()
        refreshed = self.cli("import-file", "--file", str(self.repo / "shop.py"), "--token", scan["claim_token"])
        self.assertEqual(refreshed["nodes_inserted"], 0)
        node = self.cli("get", "--id", classifier)["node"]
        self.assertEqual(node["attrs"].get("duty"), "订单持久化（设计角色写入）")
        self.assertEqual(node["attrs"].get("x_lang"), "python")

    def test_retract_cleans_bites_and_work_refs(self):
        self.init_repo()
        self.declare("feat-retract")
        scan, _ = self.import_scan("feat-retract")
        node_id = "classifier:demo:shop.py:OrderRepo"
        self.bite(node_id, "UNMAPPED", feature="feat-retract", reason="临时")
        result = self.cli("retract", "--token", scan["claim_token"], "--node-ids", json.dumps([node_id]))
        self.assertEqual(result["bites_deleted"], 1)
        self.assertGreaterEqual(result["work_refs_pruned"], 1)
        conn = self.db()
        self.assertIsNone(conn.execute("SELECT id FROM nodes WHERE id=?", (node_id,)).fetchone())
        self.assertIsNone(conn.execute("SELECT id FROM bites WHERE node_id=?", (node_id,)).fetchone())
        self.assertIsNone(conn.execute("SELECT node_id FROM feature_nodes WHERE node_id=?", (node_id,)).fetchone())
        row = conn.execute("SELECT target_ids, evidence_ids FROM work_items WHERE id=?", (scan["work_item_id"],)).fetchone()
        self.assertNotIn(node_id, json.loads(row[0]))
        self.assertNotIn(node_id, json.loads(row[1]))
        conn.close()
        self.finish(scan["claim_token"])
        self.judge(scan["work_item_id"])

    def test_gate_ignores_dangling_bite_and_doctor_fixes(self):
        self.init_repo()
        self.declare("feat-doc")
        self.cli("evidence-record", "--feature", "feat-doc", "--name", "e", "--command", "true", "--actor", "test")
        conn = self.db()
        conn.execute(
            "INSERT INTO bites(node_id, feature_id, verdict, reason, actor, created_at) VALUES(?,?,?,?,?,?)",
            ("operation:missing:gone", "feat-doc", "UNNECESSARY", "stale", "test", "2026-01-01T00:00:00Z"),
        )
        conn.execute("UPDATE work_items SET claim_token='stale-token' WHERE id='work:feat-doc:g1:model-architecture'")
        conn.execute("UPDATE conditions SET status=1 WHERE feature_id='feat-doc' AND generation=1")
        conn.execute("UPDATE meta SET value='0.1.0' WHERE key='contract_version'")
        conn.commit()
        conn.close()
        gate = self.cli("gate", "--feature", "feat-doc", "--json")
        self.assertEqual(gate["result"], "PASS")
        self.assertEqual(gate["ignored_dangling_bites"][0]["node"], "operation:missing:gone")
        doctor = self.cli("doctor", expect=1)
        checks = {issue["check"] for issue in doctor["issues"]}
        self.assertIn("dangling-bite", checks)
        self.assertIn("token-on-inactive", checks)
        self.assertIn("meta-version", checks)
        self.assertIn("dangling-bite", doctor["by_check"])
        self.assertFalse(doctor["truncated"])
        fixed = self.cli("doctor", "--fix")
        self.assertTrue(fixed["ok"])
        self.assertGreaterEqual(fixed["fixed"]["dangling_bites"], 1)
        self.assertGreaterEqual(fixed["fixed"]["tokens"], 1)
        self.assertEqual(fixed["fixed"]["meta"], 1)
        conn = self.db()
        self.assertIsNone(conn.execute("SELECT id FROM bites WHERE node_id='operation:missing:gone'").fetchone())
        token = conn.execute("SELECT claim_token FROM work_items WHERE id='work:feat-doc:g1:model-architecture'").fetchone()
        self.assertIsNone(token[0])
        version = conn.execute("SELECT value FROM meta WHERE key='contract_version'").fetchone()
        self.assertEqual(version[0], "0.4.0")
        conn.close()
        gate_after = self.cli("gate", "--feature", "feat-doc", "--json")
        self.assertEqual(gate_after["result"], "PASS")
        self.assertNotIn("ignored_dangling_bites", gate_after)

    def test_slice_expands_wildcard_targets(self):
        self.init_repo()
        self.declare("feat-slice")
        self.import_scan("feat-slice")
        opened = self.cli(
            "work-open", "--feature", "feat-slice", "--kind", "observe",
            "--target-ids", json.dumps(["classifier:demo:shop.py:*"]),
        )
        sliced = self.cli("slice", "--work", opened["work"]["id"])
        self.assertGreaterEqual(len(sliced["nodes"]), 1)
        self.assertEqual(sliced["missing_ids"], [])
        self.assertIn("classifier:demo:shop.py:*", sliced["patterns"])

    def test_claim_token_cleared_after_finish_and_judge(self):
        self.init_repo()
        self.declare("feat-token")
        scan, _ = self.import_scan("feat-token")
        conn = self.db()
        before = conn.execute("SELECT claim_token FROM work_items WHERE id=?", (scan["work_item_id"],)).fetchone()
        conn.close()
        self.assertIsNotNone(before[0])
        self.finish(scan["claim_token"])
        conn = self.db()
        after_finish = conn.execute("SELECT status, claim_token FROM work_items WHERE id=?", (scan["work_item_id"],)).fetchone()
        conn.close()
        self.assertEqual(after_finish[0], "submitted")
        self.assertIsNone(after_finish[1])
        self.judge(scan["work_item_id"])
        conn = self.db()
        after_judge = conn.execute("SELECT status, claim_token FROM work_items WHERE id=?", (scan["work_item_id"],)).fetchone()
        conn.close()
        self.assertEqual(after_judge[0], "passed")
        self.assertIsNone(after_judge[1])

    def test_role_and_token_boundaries(self):
        self.init_repo()
        self.declare("feat-bound")
        self.claim("audit", expect=2)
        self.claim("implement-test", expect=2)
        self.cli("upsert-node", "--data", "{}", expect=2)
        arch = self.claim("model-architecture")
        token = arch["claim_token"]
        outside = self.cli(
            "upsert-node",
            "--token", token,
            "--data", json.dumps({"id": "classifier:demo:x", "kind": "classifier", "name": "x"}),
            expect=2,
        )
        self.assertIn("target_ids", outside["error"])

    def test_contract_verify_detects_drift(self):
        check = subprocess.run(
            [sys.executable, str(WXG), "--root", str(self.root), "verify"],
            capture_output=True, text=True, encoding="utf-8", env=ENV,
        )
        self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
        self.assertTrue(json.loads(check.stdout)["ok"])

        copy = self.base / "skill-copy"
        shutil.copytree(SKILL, copy)
        skill_md = copy / "SKILL.md"
        text = skill_md.read_text(encoding="utf-8")
        text = text.replace("<!-- wxg:contract:main:end -->", "被手改的一行\n<!-- wxg:contract:main:end -->")
        skill_md.write_text(text, encoding="utf-8")
        drift = subprocess.run(
            [sys.executable, str(WXG), "--root", str(self.root), "verify"],
            capture_output=True, text=True, encoding="utf-8",
            env=dict(ENV, WXG_SKILL_DIR=str(copy)),
        )
        self.assertNotEqual(drift.returncode, 0)
        self.assertIn("过期", drift.stdout)

    def test_contract_commands_cover_roles_and_attrs(self):
        sys.path.insert(0, str(SKILL / "scripts"))
        import wxg_contract as contract  # noqa: WPS433

        kinds = {entry["kind"] for entry in contract.NODE_KINDS}
        edge_kinds = {entry["kind"] for entry in contract.EDGE_KINDS}
        self.assertTrue(set(contract.ATTR_SCHEMA).issubset(kinds))
        self.assertTrue(set(contract.BIND_EDGE_KIND.values()).issubset(edge_kinds))
        for role, commands in contract.ROLES.items():
            for command in commands:
                self.assertIn(command, contract.COMMANDS, f"{role} 引用了未注册命令 {command}")
        for command, spec in contract.COMMANDS.items():
            self.assertTrue(callable(getattr(__import__("wxg"), "cmd_" + command.replace("-", "_"), None)))


    def test_contract_json_is_serializable(self):
        contract = self.cli("contract", "--json")
        self.assertEqual(contract["version"], "0.4.0")
        self.assertEqual(contract["schema_version"], 3)
        self.assertIn("evidence-record", contract["commands"])
        self.assertEqual(contract["commands"]["work-claim"]["options"][1]["type"], "str")
        self.assertEqual(contract["evidence_required_conditions"], ["BehaviorPassed"])
        self.assertEqual(set(contract["commands"]), set(contract["command_write_modes"]))

    def test_audit_actor_required_and_independent(self):
        self.init_repo()
        self.declare("feat-audit")
        self.open_targets("feat-audit", "model-architecture", ["use_case:feat-audit:*"])
        no_actor = self.cli("work-claim", "--role", "model-architecture", expect=2)
        self.assertIn("--actor", no_actor["error"])
        claimed = self.cli(
            "work-claim", "--role", "model-architecture", "--actor", "agent-arch"
        )
        token = claimed["claim_token"]
        self.upsert(token, {"id": "use_case:feat-audit:uc", "kind": "use_case", "name": "用例"})
        self.finish(token)

        missing = self.cli(
            "work-judge", "--id", claimed["work_item_id"], "--verdict", "passed",
            "--role", "audit", expect=2,
        )
        self.assertIn("--actor", missing["error"])
        same = self.cli(
            "work-judge", "--id", claimed["work_item_id"], "--verdict", "passed",
            "--role", "audit", "--actor", "agent-arch", expect=2,
        )
        self.assertIn("独立性", same["error"])

        self.judge(claimed["work_item_id"], actor="auditor-x")
        conn = self.db()
        subject = conn.execute(
            "SELECT status, claimed_by, judged_by, judged_at FROM work_items WHERE id=?",
            (claimed["work_item_id"],),
        ).fetchone()
        audit = conn.execute(
            "SELECT status, judged_by FROM work_items WHERE kind='audit' AND depends_on=?",
            (json.dumps([claimed["work_item_id"]]),),
        ).fetchone()
        conn.close()
        self.assertEqual(subject[0], "passed")
        self.assertEqual(subject[1], "agent-arch")
        self.assertEqual(subject[2], "auditor-x")
        self.assertTrue(subject[3])
        self.assertEqual(audit[0], "passed")
        self.assertEqual(audit[1], "auditor-x")

    def test_evidence_record_and_doctor_artifact(self):
        self.init_repo()
        self.declare("feat-ev")
        artifact = self.base / "artifact.txt"
        artifact.write_text("first", encoding="utf-8")
        recorded = self.cli(
            "evidence-record", "--feature", "feat-ev", "--name", "unittest",
            "--command", "python -m unittest", "--artifact", str(artifact),
            "--actor", "agent-lead",
        )
        self.assertEqual(recorded["exit_code"], 0)
        self.assertTrue(recorded["sha256"])
        listed = self.cli("evidence-list", "--feature", "feat-ev")
        self.assertEqual(len(listed["evidence"]), 1)
        self.assertTrue(self.cli("doctor")["ok"])

        artifact.write_text("tampered", encoding="utf-8")
        broken = self.cli("doctor", expect=1)
        self.assertIn("evidence-artifact-changed", broken["by_check"])

    def test_gate_rejects_evidence_with_deleted_artifact(self):
        self.init_repo()
        self.declare("feat-art")
        observe = self.complete_through_implement("feat-art")
        artifact = self.base / "results.txt"
        artifact.write_text("ok", encoding="utf-8")
        self.cli("evidence-record", "--feature", "feat-art", "--name", "unittest",
                 "--command", "python -m unittest", "--artifact", str(artifact),
                 "--actor", "auditor-1")
        self.judge(observe["work_item_id"])
        gate = self.cli("gate", "--feature", "feat-art", "--json")
        self.assertEqual(gate["result"], "PASS")
        artifact.unlink()
        gate = self.cli("gate", "--feature", "feat-art", "--json", expect=1)
        self.assertEqual(gate["result"], "FAIL")
        self.assertIn("evidence", gate["reason"])
        doctor = self.cli("doctor", expect=1)
        self.assertIn("evidence-artifact-missing", doctor["by_check"])

    def test_export_dedupes_shared_parameter(self):
        self.init_repo()
        self.declare("feat-export-dedup")
        sys.path.insert(0, str(SKILL / "scripts"))
        import wxg  # noqa: WPS433

        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {"id": "use_case:feat-export-dedup:uc", "kind": "use_case", "name": "用用例"})
            wxg.upsert_edge(conn, {"src": "use_case:feat-export-dedup:uc", "dst": "requirement:feat-export-dedup:main", "kind": "satisfies"})
            wxg.upsert_node(conn, {"id": "parameter:feat-export-dedup:order_id", "kind": "parameter", "name": "order_id"})
            for name in ("first", "second"):
                op = f"operation:demo:shop.py:{name}"
                wxg.upsert_node(conn, {"id": op, "kind": "operation", "name": name})
                wxg.upsert_edge(conn, {"src": "use_case:feat-export-dedup:uc", "dst": op, "kind": "contains"})
                wxg.bind_node(conn, "parameter:feat-export-dedup:order_id", op)
            conn.commit()
        finally:
            conn.close()
        exported = self.cli("export", "--feature", "feat-export-dedup")
        flow = (Path(exported["dir"]) / "07-数据流.md").read_text(encoding="utf-8")
        self.assertEqual(flow.count("| order_id |"), 1, flow)

    def test_init_migrates_legacy_work_items(self):
        self.root.mkdir(parents=True)
        db = self.root / "graph.sqlite"
        conn = sqlite3.connect(db)
        conn.execute(
            """CREATE TABLE work_items (
                 id TEXT PRIMARY KEY, feature_id TEXT NOT NULL, generation INTEGER NOT NULL,
                 kind TEXT NOT NULL, role TEXT NOT NULL, target_ids TEXT NOT NULL DEFAULT '[]',
                 status TEXT NOT NULL DEFAULT 'ready', depends_on TEXT NOT NULL DEFAULT '[]',
                 assignee TEXT, claim_token TEXT, evidence_ids TEXT NOT NULL DEFAULT '[]',
                 fail_reason TEXT, created_at TEXT NOT NULL)"""
        )
        conn.execute(
            "INSERT INTO work_items(id, feature_id, generation, kind, role, status, created_at) "
            "VALUES('work:old:g1:scan','old',1,'scan','scan','passed','2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()

        migrated = self.cli("init")
        self.assertEqual(migrated["schema_version"], 3)
        conn = sqlite3.connect(db)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(work_items)")}
        evidence_columns = {row[1] for row in conn.execute("PRAGMA table_info(evidence)")}
        row = conn.execute(
            "SELECT claimed_by, judged_by FROM work_items WHERE id='work:old:g1:scan'"
        ).fetchone()
        conn.close()
        self.assertTrue({"claimed_by", "judged_by", "judged_at"}.issubset(columns))
        self.assertIn("generation", evidence_columns)
        self.assertEqual(row, ("legacy", "legacy"))
        doctor = self.cli("doctor", expect=1)
        self.assertIn("legacy-identity", doctor["by_check"])

    # ---------------- 0.4.0 回归：门禁/注册/幂等/可用性

    def test_init_is_idempotent_after_workflow(self):
        self.init_repo()
        self.declare("feat-idem")
        arch = self.claim("model-architecture")
        self.finish(arch["claim_token"])
        self.judge(arch["work_item_id"])
        before = self.db_snapshot()
        migrated = self.cli("init")
        after = self.db_snapshot()
        self.assertEqual(before, after, "init 不得在已迁移库上改写已有行")
        self.assertEqual(migrated["migrated"], {})
        audit = [row for row in after["work_items"] if row[3] == "audit"]
        self.assertTrue(audit)
        self.assertIsNone(audit[0][9], "fresh audit 工单不得被 init 标成 legacy")

    def test_feature_register_does_not_touch_conditions(self):
        self.init_repo()
        self.declare("feat-reg")
        before = self.status("feat-reg")["conditions"]
        registered = self.cli(
            "feature-register", "--id", "feat-reg", "--name", "登记",
            "--spec", json.dumps({"statement": "s", "acceptance": ["a"], "constraints": ["c"]}),
        )
        self.assertEqual(registered["generation"], 1)
        self.assertTrue(registered["conditions_untouched"])
        self.assertEqual(before, self.status("feat-reg")["conditions"])

    def test_feature_register_new_generation_supersedes(self):
        self.init_repo()
        self.declare("feat-reg2")
        arch = self.claim("model-architecture")
        self.finish(arch["claim_token"])
        self.judge(arch["work_item_id"])
        structure = self.claim("model-structure")  # 已 claimed、未 finish 的旧代工单
        registered = self.cli(
            "feature-register", "--id", "feat-reg2", "--name", "登记",
            "--spec", json.dumps({"statement": "s", "acceptance": ["a"], "constraints": ["c"]}),
            "--generation", "2",
        )
        self.assertEqual(registered["generation"], 2)
        conditions = self.status("feat-reg2")["conditions"]
        self.assertEqual(conditions["Accepted"], 1)
        self.assertEqual(conditions["ArchitectureReconciled"], 0)
        conn = self.db()
        old = conn.execute(
            "SELECT status FROM work_items WHERE id='work:feat-reg2:g1:model-architecture'"
        ).fetchone()
        claimed_old = conn.execute(
            "SELECT status, claim_token FROM work_items WHERE id=?", (structure["work_item_id"],)
        ).fetchone()
        conn.close()
        self.assertEqual(old[0], "superseded")
        self.assertEqual(claimed_old[0], "superseded")
        self.assertIsNone(claimed_old[1], "supersede 时旧代 token 必须清空")
        # 旧代 ready 工单不能被新代角色领走
        self.claim("model-structure", expect=2)
        # 新代需要显式 work-seed，之后领到的必须是 g2 工单（generation join）。
        self.cli("work-seed", "--feature", "feat-reg2")
        fresh = self.claim("model-architecture")
        self.assertIn(":g2:", fresh["work_item_id"])

    def test_feature_register_writes_requirement_node(self):
        self.init_repo()
        self.declare("feat-regreq", statement="旧声明")
        self.cli(
            "feature-register", "--id", "feat-regreq", "--name", "登记",
            "--spec", json.dumps({"statement": "新声明", "acceptance": ["a"], "constraints": ["c"]}),
        )
        node = self.cli("get", "--id", "requirement:feat-regreq:main")["node"]
        self.assertEqual(node["attrs"]["statement"], "新声明")
        exported = self.cli("export", "--feature", "feat-regreq")
        req = (Path(exported["dir"]) / "01-需求.md").read_text(encoding="utf-8")
        self.assertIn("新声明", req)

    def test_feature_register_new_feature(self):
        self.init_repo()
        registered = self.cli(
            "feature-register", "--id", "feat-brandnew", "--name", "新登记",
            "--spec", json.dumps({"statement": "一句话", "acceptance": ["a"], "constraints": ["c"]}),
        )
        self.assertEqual(registered["generation"], 1)
        self.assertTrue(registered["requirement_written"])
        node = self.cli("get", "--id", "requirement:feat-brandnew:main")["node"]
        self.assertEqual(node["attrs"]["statement"], "一句话")
        conditions = self.status("feat-brandnew")["conditions"]
        self.assertEqual(conditions["Accepted"], 1)
        self.assertEqual(conditions["ArchitectureReconciled"], 0)

    def test_feature_register_validates_spec_and_generation(self):
        self.init_repo()
        bad_spec = self.cli(
            "feature-register", "--id", "feat-bad", "--name", "n",
            "--spec", json.dumps({"statement": "s", "acceptance": "a", "constraints": "c"}),
            expect=2,
        )
        self.assertIn("数组", bad_spec["error"])
        zero = self.cli(
            "feature-register", "--id", "feat-zero", "--name", "n",
            "--spec", json.dumps({"statement": "s", "acceptance": ["a"], "constraints": ["c"]}),
            "--generation", "0", expect=2,
        )
        self.assertIn("正整数", zero["error"])
        negative = self.cli(
            "feature-register", "--id", "feat-neg", "--name", "n",
            "--spec", json.dumps({"statement": "s", "acceptance": ["a"], "constraints": ["c"]}),
            "--generation", "-3", expect=2,
        )
        self.assertIn("正整数", negative["error"])

    def test_evidence_is_generation_scoped(self):
        self.init_repo()
        self.declare("feat-gen")
        self.cli("evidence-record", "--feature", "feat-gen", "--name", "unittest",
                 "--command", "python -m unittest", "--actor", "auditor-1")
        self.declare("feat-gen", statement="第二代")
        old_gen = self.cli("evidence-record", "--feature", "feat-gen", "--name", "old-gen",
                           "--command", "python -m unittest", "--work",
                           "work:feat-gen:g1:observe", "--actor", "auditor-1")
        self.assertEqual(old_gen["generation"], 1)
        observe = self.complete_through_implement("feat-gen")
        rejected = self.judge(observe["work_item_id"], expect=2)
        self.assertIn("generation", rejected["error"])
        recorded = self.cli("evidence-record", "--feature", "feat-gen", "--name", "unittest-g2",
                            "--command", "python -m unittest", "--actor", "auditor-1")
        self.assertEqual(recorded["generation"], 2)
        self.judge(observe["work_item_id"])
        gate = self.cli("gate", "--feature", "feat-gen", "--json")
        self.assertEqual(gate["result"], "PASS")

    def test_upsert_missing_id_readable_error(self):
        self.init_repo()
        self.declare("feat-empty")
        self.open_targets("feat-empty", "model-architecture", ["use_case:feat-empty:*"])
        arch = self.claim("model-architecture")
        for bad in ("{}", json.dumps({"kind": "use_case", "name": "x"})):
            rejected = self.cli("upsert-node", "--token", arch["claim_token"], "--data", bad, expect=2)
            self.assertIsInstance(rejected, dict)
            self.assertIn("id", rejected["error"])

    def test_observe_judge_requires_evidence(self):
        self.init_repo()
        self.declare("feat-evidence")
        observe = self.complete_through_implement("feat-evidence")
        rejected = self.judge(observe["work_item_id"], expect=2)
        self.assertIn("evidence", rejected["error"])
        self.cli("evidence-record", "--feature", "feat-evidence", "--name", "unittest",
                 "--command", "python -m unittest", "--actor", "auditor-1")
        self.judge(observe["work_item_id"])
        status = self.status("feat-evidence")
        self.assertEqual(status["conditions"]["BehaviorPassed"], 1)
        gate = self.cli("gate", "--feature", "feat-evidence", "--json")
        self.assertEqual(gate["result"], "PASS")

    def test_scan_failed_judge_keeps_conditions(self):
        self.init_repo()
        self.declare("feat-scan-fail")
        self.open_targets("feat-scan-fail", "scan", ["requirement:feat-scan-fail:main"])
        scan = self.claim("scan")
        self.finish(scan["claim_token"])
        self.judge(scan["work_item_id"], verdict="failed", reason="坏")
        conditions = self.status("feat-scan-fail")["conditions"]
        self.assertEqual(conditions["Accepted"], 1)
        self.assertEqual(conditions["ArchitectureReconciled"], 0)
        self.assertEqual(conditions["Ready"], 0)

    def test_upsert_rejects_attrs_bite(self):
        self.init_repo()
        self.declare("feat-forge")
        arch = self.claim("model-architecture")
        payload = {
            "id": "requirement:feat-forge:main",
            "kind": "requirement",
            "name": "伪造",
            "attrs": {"statement": "s", "bite": "KEEP"},
        }
        rejected = self.cli("upsert-node", "--token", arch["claim_token"], "--data", json.dumps(payload), expect=2)
        self.assertIn("bite", rejected["error"])

    def test_gate_requires_evidence_for_behavior_passed(self):
        self.init_repo()
        self.declare("feat-noevidence")
        conn = self.db()
        conn.execute("UPDATE conditions SET status=1 WHERE feature_id='feat-noevidence' AND generation=1")
        conn.commit()
        conn.close()
        gate = self.cli("gate", "--feature", "feat-noevidence", "--json", expect=1)
        self.assertEqual(gate["result"], "FAIL")
        self.assertIn("evidence", gate["reason"])
        self.assertEqual(gate["missing_evidence_for"], ["BehaviorPassed"])

    def test_verify_is_side_effect_free(self):
        cwd = self.base / "verify-cwd"
        cwd.mkdir()
        proc = subprocess.run(
            [sys.executable, str(WXG), "verify"],
            capture_output=True, text=True, encoding="utf-8", env=ENV, cwd=str(cwd),
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["ok"])
        self.assertFalse((cwd / ".why-exist").exists(), "verify 不得创建状态库目录")

    def test_target_ids_accept_at_file(self):
        self.init_repo()
        self.declare("feat-at")
        target_file = self.base / "targets.json"
        target_file.write_text(json.dumps(["requirement:feat-at:main"]), encoding="utf-8")
        self.cli("work-open", "--feature", "feat-at", "--kind", "model-architecture",
                 "--target-ids", f"@{target_file}")
        claim = self.claim("model-architecture")
        self.assertIn("requirement:feat-at:main", claim["target_ids"])

    def test_role_prompt_uses_real_root(self):
        self.init_repo()
        prompt = self.cli("role-prompt", "--role", "audit")
        self.assertNotIn("{root}", prompt)
        self.assertIn(str(self.root), prompt)
        self.assertIn("work-judge", prompt)
        self.assertIn("直接裁决", prompt)
        scan_prompt = self.cli("role-prompt", "--role", "scan")
        self.assertIn("work-finish --token", scan_prompt)

    def test_repo_add_language_only_python(self):
        self.init_repo()
        bad = self.cli("repo-add", "--id", "jrepo", "--path", str(self.repo), "--language", "java", expect=2)
        self.assertIn("invalid choice", bad)

    def test_import_non_python_repo_message(self):
        self.init_repo()
        src = self.base / "jrepo-src"
        src.mkdir()
        (src / "A.java").write_text("public class A {}\n", encoding="utf-8")
        conn = self.db()
        conn.execute(
            "INSERT INTO repos(id, path, language, created_at) VALUES('jrepo', ?, 'java', '2026-01-01T00:00:00Z')",
            (str(src),),
        )
        conn.commit()
        conn.close()
        rejected = self.cli("import-file", "--file", str(src / "A.java"), "--feature", "feat-java", "--prepare", expect=2)
        self.assertIn("Python 导入器", rejected["error"])
        self.assertNotIn("wxg_import", rejected["error"])

    def test_chain_calls_get_unmapped_nodes(self):
        self.init_repo()
        self.declare("feat-chain")
        weird = self.repo / "weird.py"
        weird.write_text(
            "class Weird:\n"
            "    def run(self, data):\n"
            "        self.get_conn().execute('x')\n"
            "        data['k'].append(1)\n"
            "        return len(data)\n",
            encoding="utf-8",
        )
        prepared = self.cli("import-file", "--file", str(weird), "--feature", "feat-chain", "--prepare")
        self.assertGreater(prepared["nodes"], 0)
        scan = self.claim("scan")
        written = self.cli("import-file", "--file", str(weird), "--token", scan["claim_token"])
        self.assertGreater(written["nodes_inserted"], 0)
        ops = self.cli("find", "--kind", "operation")["nodes"]
        self.assertTrue(any(node["unmapped"] == 1 for node in ops), ops)
        doctor = self.cli("doctor")
        self.assertTrue(doctor["ok"], doctor)

    def test_missing_db_commands_do_not_create(self):
        missing = self.base / "missing-state"
        for cmd in (["gate", "--feature", "x"], ["work-seed", "--feature", "x"], ["repo-list"]):
            proc = subprocess.run(
                [sys.executable, str(WXG), "--root", str(missing), *cmd],
                capture_output=True, text=True, encoding="utf-8", env=ENV,
            )
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertFalse(missing.exists(), f"{cmd} 不应创建状态库目录")

    def test_init_backfills_evidence_generation_from_work_item(self):
        self.root.mkdir(parents=True)
        db = self.root / "graph.sqlite"
        conn = sqlite3.connect(db)
        conn.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
            CREATE TABLE features (id TEXT PRIMARY KEY, name TEXT NOT NULL, generation INTEGER NOT NULL,
              statement TEXT NOT NULL, acceptance_json TEXT NOT NULL DEFAULT '[]',
              constraints_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL);
            CREATE TABLE work_items (
              id TEXT PRIMARY KEY, feature_id TEXT NOT NULL, generation INTEGER NOT NULL,
              kind TEXT NOT NULL, role TEXT NOT NULL, target_ids TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'ready', depends_on TEXT NOT NULL DEFAULT '[]',
              assignee TEXT, claim_token TEXT, evidence_ids TEXT NOT NULL DEFAULT '[]',
              fail_reason TEXT, created_at TEXT NOT NULL,
              claimed_by TEXT, judged_by TEXT, judged_at TEXT);
            CREATE TABLE evidence (id TEXT PRIMARY KEY, feature_id TEXT NOT NULL, work_item_id TEXT,
              name TEXT NOT NULL, command TEXT NOT NULL, exit_code INTEGER NOT NULL,
              artifact_path TEXT, artifact_sha256 TEXT, actor TEXT NOT NULL, created_at TEXT NOT NULL);
            INSERT INTO features VALUES ('f','n',2,'s','[]','[]','2026-01-01T00:00:00Z');
            INSERT INTO work_items(id, feature_id, generation, kind, role, target_ids, status, depends_on,
              evidence_ids, created_at) VALUES
              ('work:f:g1:observe','f',1,'observe','observe','[]','submitted','[]','[]','2026-01-01T00:00:00Z');
            INSERT INTO evidence VALUES ('ev:linked','f','work:f:g1:observe','t','pytest',0,NULL,NULL,'aud','2026-01-01T00:00:00Z');
            INSERT INTO evidence VALUES ('ev:free','f',NULL,'t2','pytest',0,NULL,NULL,'aud','2026-01-01T00:00:00Z');
            INSERT INTO meta VALUES ('schema_version','2'), ('contract_version','0.3.0');
            """
        )
        conn.commit()
        conn.close()
        self.cli("init")
        conn = sqlite3.connect(db)
        generations = dict(conn.execute("SELECT id, generation FROM evidence").fetchall())
        conn.close()
        self.assertEqual(generations["ev:linked"], 1)
        self.assertEqual(generations["ev:free"], 2)
        doctor = self.cli("doctor", expect=1)
        self.assertNotIn("evidence-missing-generation", doctor["by_check"])
        # 手工把一条 evidence 的 generation 置空，doctor 必须能报出来（R3）。
        conn = sqlite3.connect(db)
        conn.execute("UPDATE evidence SET generation=NULL WHERE id='ev:free'")
        conn.commit()
        conn.close()
        broken = self.cli("doctor", expect=1)
        self.assertIn("evidence-missing-generation", broken["by_check"])

    def test_export_escapes_pipes(self):
        self.init_repo()
        self.declare("feat-pipe")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {"id": "use_case:feat-pipe:uc", "kind": "use_case", "name": "用|例"})
            wxg.upsert_edge(conn, {"src": "use_case:feat-pipe:uc", "dst": "requirement:feat-pipe:main", "kind": "satisfies"})
            op = "operation:demo:pipe.py:op"
            wxg.upsert_node(conn, {"id": op, "kind": "operation", "name": "a|b"})
            wxg.upsert_edge(conn, {"src": "use_case:feat-pipe:uc", "dst": op, "kind": "contains"})
            wxg.upsert_node(conn, {"id": "sink:demo:pipe", "kind": "sink", "name": "orders|x"})
            wxg.upsert_edge(conn, {"src": op, "dst": "sink:demo:pipe", "kind": "writes"})
            conn.commit()
        finally:
            conn.close()
        exported = self.cli("export", "--feature", "feat-pipe")
        dump = Path(exported["dir"])
        flow = (dump / "07-数据流.md").read_text(encoding="utf-8")
        self.assertIn("a\\|b", flow)
        self.assertIn("orders\\|x", flow)
        usecase = (dump / "02-用例.md").read_text(encoding="utf-8")
        self.assertIn("用\\|例", usecase)

    def test_register_preserves_requirement_attrs(self):
        self.init_repo()
        self.declare("feat-regattr", statement="旧")
        arch = self.claim("model-architecture")
        payload = {
            "id": "requirement:feat-regattr:main",
            "kind": "requirement",
            "name": "旧",
            "attrs": {"statement": "旧", "x_note": "保留"},
        }
        self.upsert(arch["claim_token"], payload)
        self.cli(
            "feature-register", "--id", "feat-regattr", "--name", "登记",
            "--spec", json.dumps({"statement": "新", "acceptance": ["a"], "constraints": ["c"]}),
        )
        node = self.cli("get", "--id", "requirement:feat-regattr:main")["node"]
        self.assertEqual(node["attrs"]["statement"], "新")
        self.assertEqual(node["attrs"]["x_note"], "保留")
        # 重新声明（declare）也不应丢掉自定义 attrs（与 register 对称）
        self.declare("feat-regattr", statement="第三代")
        node = self.cli("get", "--id", "requirement:feat-regattr:main")["node"]
        self.assertEqual(node["attrs"]["statement"], "第三代")
        self.assertEqual(node["attrs"]["x_note"], "保留")


if __name__ == "__main__":
    unittest.main()
