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


class BackendFailureCase(unittest.TestCase):
    """错误流契约：后端连不上时必须给可读 JSON + 退出 2，不能是裸 traceback。

    这条曾被整类漏掉——``cli.py`` 的 ``connect()`` 写在 try 之外，MySQL/PostgreSQL
    的错密码、端口不通、没装 psycopg 四种失败全部变成 traceback + 退出 1，
    与契约里「错误给可读 JSON、退出 2」正面冲突。
    """

    def run_wxg(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(WXG), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=ENV,
        )

    def test_mysql_connect_failure_is_readable_json(self):
        # 端口 1 上没有 MySQL，连接会被立刻拒绝（不依赖网络、不依赖装了什么驱动）
        proc = self.run_wxg("--db-url", "mysql://u:p@127.0.0.1:1/db", "repo-list")
        self.assertEqual(proc.returncode, 2, msg=f"stderr={proc.stderr}")
        self.assertNotIn("Traceback", proc.stderr)
        payload = json.loads(proc.stderr.strip())
        self.assertIn("error", payload)

    def test_unknown_backend_scheme_is_rejected_before_connect(self):
        proc = self.run_wxg("--db-url", "oracle://u:p@127.0.0.1:1/db", "repo-list")
        self.assertEqual(proc.returncode, 2, msg=f"stderr={proc.stderr}")
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("error", json.loads(proc.stderr.strip()))


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

    def declare(self, feature="feat-x", statement="创建订单。", acceptance=None, constraints=None,
                coverage_epsilon=None, drift_limit=None, no_coverage=True):
        args = [
            "feature-declare",
            "--id", feature,
            "--name", f"演示 {feature}",
            "--statement", statement,
            "--acceptance", json.dumps(acceptance or ["返回成功"], ensure_ascii=False),
            "--constraints", json.dumps(constraints or ["不改产品代码"], ensure_ascii=False),
        ]
        if coverage_epsilon is not None:
            args += ["--coverage-epsilon", str(coverage_epsilon)]
        elif no_coverage:
            args += ["--no-coverage"]
        if drift_limit is not None:
            args += ["--drift-limit", str(drift_limit)]
        return self.cli(*args)

    def status(self, feature):
        return self.cli("feature-status", "--id", feature)

    def force_ready(self, feature):
        conn = self.db()
        conn.execute(
            "UPDATE conditions SET status=1 WHERE feature_id=? AND generation=(SELECT generation FROM features WHERE id=?)",
            (feature, feature),
        )
        conn.commit()
        conn.close()

    def open_targets(self, feature, kind, patterns):
        return self.cli("work-open", "--feature", feature, "--kind", kind, "--target-ids", json.dumps(patterns, ensure_ascii=False))

    def ready_ticket(self, feature, kind):
        """把指定工单直接置 ready 并清依赖：给只测单条命令的用例用，跳过上游条件链。"""
        conn = self.db()
        conn.execute(
            "UPDATE work_items SET status='ready', depends_on='[]' "
            "WHERE id='work:' || ? || ':g' || (SELECT generation FROM features WHERE id=?) || ':' || ?",
            (feature, feature, kind),
        )
        conn.commit()
        conn.close()

    def claim(self, role, expect=0, allow_product_code=False, actor=None):
        args = ["work-claim", "--role", role, "--actor", actor or f"agent-{role}"]
        if allow_product_code:
            args.append("--allow-product-code")
        return self.cli(*args, expect=expect)

    def bite(self, node, verdict, feature=None, reason=None, actor="agent-lead", allow_new_scope=False, expect=0):
        args = ["bite", "--node", node, "--verdict", verdict, "--actor", actor]
        if feature:
            args += ["--feature", feature]
        if reason:
            args += ["--reason", reason]
        if allow_new_scope:
            args.append("--allow-new-scope")
        return self.cli(*args, expect=expect)

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

    def trace_ok(self, feature, requirement=None, text="返回成功"):
        """给 fixture 补一条完整追溯链：需求 → 验收条目 → 测试。

        3.6.0 起 gate 对“有需求、无验收”判 UNKNOWN。这些测试关心的是证据/漂移/调谐，
        不是追溯本身，所以用这个 helper 直接写库补齐链条（与 `force_ready` 同类：fixture 造数）。
        """
        requirement = requirement or f"requirement:{feature}:main"
        suffix = requirement.split(":", 2)[2]
        acceptance = f"acceptance:{feature}:{suffix}:01"
        testcase = f"testcase:{feature}:trace-ok-{suffix}"
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {
                "id": acceptance,
                "kind": "acceptance",
                "name": text,
                "attrs": {"text": text, "ordinal": 1},
            })
            wxg.upsert_edge(conn, {"src": requirement, "dst": acceptance, "kind": "has_acceptance"})
            wxg.upsert_node(conn, {
                "id": testcase,
                "kind": "testcase",
                "name": "trace fixture",
                "attrs": {"path": "tests/trace_fixture.py"},
            })
            wxg.upsert_edge(conn, {"src": testcase, "dst": acceptance, "kind": "verifies"})
            for node_id in (acceptance, testcase):
                conn.execute(
                    "INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)",
                    (feature, node_id),
                )
            conn.commit()
        finally:
            conn.close()
        return acceptance

    def db_snapshot(self):
        conn = self.db()
        try:
            return {
                table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
                for table in ("meta", "repos", "nodes", "edges", "features", "conditions",
                              "work_items", "feature_nodes", "evidence", "bites", "judge_history", "changes")
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

        self.open_targets("feat-full", "specify-test", ["testcase:feat-full:*", "operation:demo:*", "acceptance:feat-full:*"])
        spec = self.claim("specify-test")
        token = spec["claim_token"]
        self.upsert(token, {"id": "testcase:feat-full:test-save", "kind": "testcase", "name": "save 成功", "attrs": {"path": "tests/test_shop.py"}})
        self.edge(token, "testcase:feat-full:test-save", op, "verifies")
        # 3.6.0：需求必须拆出可判定的验收条目，测试指向验收条目而不是整条需求
        acceptance = self.cli("acceptance-add", "--requirement", "requirement:feat-full:main",
                              "--text", "保存后订单可读回", "--token", token)
        # 声明时的 --acceptance 已经生成了 01，这条是 02
        self.assertEqual(acceptance["ordinal"], 2)
        # 声明期的验收条目（01）与新增的（02）都要有测试指向，gate 才算追溯通过
        self.edge(token, "testcase:feat-full:test-save", "acceptance:feat-full:main:01", "verifies")
        self.edge(token, "testcase:feat-full:test-save", acceptance["id"], "verifies")
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
        reconciled = self.cli("reconcile", "--feature", "feat-full")
        self.assertEqual(reconciled["actions"], [])
        self.assertTrue(reconciled["converged"], reconciled)
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

    def test_retract_does_not_count_missing_nodes(self):
        """不存在的节点不该计入 nodes_deleted——旧实现对每个 id 无条件 +1。

        用通配 target 构造场景：重扫后代码里的节点已经消失，但工单仍按前缀
        拿到写入权，这时 retract 一个不存在的 id 不该报删了 1 个节点。
        """
        self.init_repo()
        self.declare("feat-r-missing")
        self.cli("work-open", "--feature", "feat-r-missing", "--kind", "scan",
                 "--target-ids", '["operation:missing:*"]')
        scan = self.claim("scan")
        result = self.cli(
            "retract", "--token", scan["claim_token"],
            "--node-ids", json.dumps(["operation:missing:never-existed"]),
        )
        self.assertEqual(0, result["nodes_deleted"])
        self.assertEqual(0, result["edges_deleted"])

    def test_retract_reports_edges_beyond_scope(self):
        """删节点会连带删掉它作为端点的边。

        即使边的另一端不在 claim 的 target_ids 内也必须删（否则留悬空边），
        但这类「越界删除」要单独计数报出来，不能和范围内的删除混在一起。
        """
        self.init_repo()
        self.declare("feat-r-scope")
        scan, _ = self.import_scan("feat-r-scope")
        conn = self.db()
        rows = conn.execute("SELECT id, src, dst FROM edges ORDER BY id").fetchall()
        conn.close()
        self.assertTrue(rows, "导入后应该建立了边")
        _, src, dst = rows[0]
        result = self.cli(
            "retract", "--token", scan["claim_token"], "--node-ids", json.dumps([src]),
        )
        self.assertEqual(1, result["nodes_deleted"])
        self.assertGreaterEqual(result["edges_deleted"], 1)
        # 新字段：被连带删除、但两端不全在本次 target 内的边数
        self.assertIn("edges_deleted_out_of_scope", result)
        self.assertGreaterEqual(result["edges_deleted_out_of_scope"], 1)

    def test_bite_rejects_out_of_scope_and_only_expands_with_explicit_flag(self):
        """`bite --feature` 不再顺手扩作用域：作用域是 plan / coverage 的分母，
        被审方不该用咬合扩大它。要扩就显式 `--allow-new-scope` 并在返回值里看得见。"""
        self.init_repo()
        self.declare("feat-bite-a")
        self.declare("feat-bite-b")
        self.import_scan("feat-bite-a")
        node = "classifier:demo:shop.py:OrderRepo"
        rejected = self.bite(node, "KEEP", feature="feat-bite-b", expect=2)
        self.assertIn("作用域", rejected["error"])
        first = self.bite(node, "KEEP", feature="feat-bite-b", allow_new_scope=True)
        self.assertTrue(first["added_to_feature_scope"])
        second = self.bite(node, "KEEP", feature="feat-bite-b", allow_new_scope=True)
        self.assertFalse(second["added_to_feature_scope"])

    def test_scope_ids_order_is_hash_seed_independent(self):
        """scope_ids 的输出会被 work-seed 写进 target_ids、被 feature-status 取前几条。

        旧实现遍历 set 展开通配，顺序随 PYTHONHASHSEED 变（审计探针实测 4 个种子
        4 种顺序）。这里用两个 feature：节点由 feat-a 导入，feat-b 的通配 target
        会把它们「新」拉进作用域——只有新加入的节点才会带上 set 的遍历顺序，
        单个 feature 内部会被 feature_nodes 的 DB 顺序盖住。
        """
        self.init_repo()
        self.declare("feat-scope-a")
        self.declare("feat-scope-b")
        self.import_scan("feat-scope-a")
        self.cli("work-open", "--feature", "feat-scope-b", "--kind", "scan",
                 "--target-ids", '["*"]')
        script = (
            "import sys\n"
            f"sys.path.insert(0, {str(SKILL / 'scripts')!r})\n"
            "from pathlib import Path\n"
            "from whyexist import db, workflow as wf\n"
            f"conn = db.connect(Path({str(self.root)!r}))\n"
            "print('|'.join(wf.scope_ids(conn, 'feat-scope-b')))\n"
        )
        outputs = set()
        for seed in ("0", "1", "2", "3"):
            env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONUTF8="1")
            proc = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, encoding="utf-8", env=env,
            )
            self.assertEqual(0, proc.returncode, proc.stderr)
            outputs.add(proc.stdout.strip())
        self.assertEqual(1, len(outputs), f"不同 PYTHONHASHSEED 下顺序不同：{outputs}")

    def test_doctor_fix_repairs_every_fixable_check(self):
        """`doctor --fix` 是全仓唯一会删数据的路径，7 类可修问题必须逐一验证。

        旧测试只覆盖 dangling-bite；orphan-edge / feature-node-missing /
        work-target-missing / work-evidence-missing / token-on-inactive / meta-version
        都没有断言，等于在删数据的路径上盲飞。
        """
        self.init_repo()
        self.declare("feat-fix")
        scan, _ = self.import_scan("feat-fix")
        conn = self.db()
        conn.execute(
            "INSERT INTO bites(node_id, feature_id, verdict, actor, created_at) VALUES(?,?,?,?,?)",
            ("operation:gone:bite", "feat-fix", "KEEP", "t", "2026-01-01T00:00:00Z"),
        )
        conn.execute(
            "INSERT INTO edges(id, src, dst, kind) "
            "VALUES('edge:gone','operation:gone:a','operation:gone:b','calls')"
        )
        conn.execute(
            "INSERT INTO feature_nodes(feature_id, node_id) VALUES('feat-fix','operation:gone:member')"
        )
        conn.execute(
            "UPDATE work_items SET target_ids=?, evidence_ids=? WHERE id=?",
            (json.dumps(["operation:gone:target"]), json.dumps(["operation:gone:evidence"]),
             scan["work_item_id"]),
        )
        conn.execute(
            "UPDATE work_items SET claim_token='stale-token', status='ready' WHERE id=?",
            (scan["work_item_id"],),
        )
        conn.execute("UPDATE meta SET value='0.1.0' WHERE key='contract_version'")
        before_nodes = {row[0] for row in conn.execute("SELECT id FROM nodes")}
        conn.commit()
        conn.close()

        result = self.cli("doctor", "--fix")
        self.assertTrue(result["ok"], result["issues"][:5])
        fixed = result["fixed"]
        self.assertEqual(1, fixed["dangling_bites"])
        self.assertEqual(1, fixed["orphan_edges"])
        self.assertEqual(1, fixed["feature_nodes"])
        self.assertEqual(1, fixed["work_refs"])
        self.assertEqual(1, fixed["tokens"])
        self.assertEqual(1, fixed["meta"])

        conn = self.db()
        after_nodes = {row[0] for row in conn.execute("SELECT id FROM nodes")}
        self.assertEqual(before_nodes, after_nodes, "修复不能动正常节点")
        self.assertIsNone(conn.execute("SELECT 1 FROM bites WHERE node_id='operation:gone:bite'").fetchone())
        self.assertIsNone(conn.execute("SELECT 1 FROM edges WHERE id='edge:gone'").fetchone())
        self.assertIsNone(conn.execute("SELECT 1 FROM feature_nodes WHERE node_id='operation:gone:member'").fetchone())
        row = conn.execute(
            "SELECT target_ids, evidence_ids, claim_token FROM work_items WHERE id=?",
            (scan["work_item_id"],),
        ).fetchone()
        conn.close()
        self.assertEqual([], json.loads(row[0]))
        self.assertEqual([], json.loads(row[1]))
        self.assertIsNone(row[2])

    def test_doctor_flags_applies_edge_to_non_pattern(self):
        """`applies` 边的语义是「谁应用了哪个设计模式」，dst 必须是 pattern。"""
        self.init_repo()
        conn = self.db()
        conn.execute("INSERT INTO nodes(id, kind, name) VALUES('component:t:src','component','S')")
        conn.execute("INSERT INTO nodes(id, kind, name) VALUES('classifier:t:dst','classifier','D')")
        conn.execute(
            "INSERT INTO edges(id, src, dst, kind) "
            "VALUES('e:applies','component:t:src','classifier:t:dst','applies')"
        )
        conn.commit()
        conn.close()
        result = self.cli("doctor", expect=1)
        self.assertIn("applies-invalid", result["by_check"])
        self.assertIn("applies-invalid", result["unfixable_checks"])

    def test_doctor_flags_pattern_without_justification(self):
        """pattern 节点必须写清 applicability 与 not_applicable，否则等于没做选型。"""
        self.init_repo()
        conn = self.db()
        conn.execute(
            "INSERT INTO nodes(id, kind, name, attrs_json) VALUES('pattern:t:p','pattern','P','{}')"
        )
        conn.commit()
        conn.close()
        result = self.cli("doctor", expect=1)
        self.assertIn("pattern-unjustified", result["by_check"])

    def test_doctor_flags_evidence_artifact_changed(self):
        """证据登记的产物被改过，登记就失效了——这条以前没有用例。"""
        self.init_repo()
        self.declare("feat-ev")
        artifact = self.base / "artifact.txt"
        artifact.write_text("v1", encoding="utf-8")
        self.cli("evidence-record", "--feature", "feat-ev", "--name", "e", "--command", "true",
                 "--artifact", str(artifact), "--actor", "t")
        artifact.write_text("v2", encoding="utf-8")
        result = self.cli("doctor", expect=1)
        self.assertIn("evidence-artifact-changed", result["by_check"])

    def test_doctor_flags_evidence_with_missing_work_item(self):
        self.init_repo()
        self.declare("feat-ev2")
        conn = self.db()
        conn.execute(
            "INSERT INTO evidence(id, feature_id, generation, work_item_id, name, command, "
            "exit_code, actor, created_at) "
            "VALUES('ev:gone','feat-ev2',1,'work:gone','e','true',0,'t','2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()
        result = self.cli("doctor", expect=1)
        self.assertIn("evidence-work-missing", result["by_check"])

    def test_doctor_flags_legacy_identity_as_unfixable(self):
        """legacy 身份只能报给人看：自动改成某个 actor 就等于伪造审计身份。"""
        self.init_repo()
        self.declare("feat-legacy")
        scan, _ = self.import_scan("feat-legacy")
        conn = self.db()
        conn.execute("UPDATE work_items SET claimed_by='legacy' WHERE id=?", (scan["work_item_id"],))
        conn.commit()
        conn.close()
        result = self.cli("doctor", expect=1)
        self.assertIn("legacy-identity", result["by_check"])
        self.assertIn("legacy-identity", result["unfixable_checks"])

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
        self.trace_ok("feat-doc")
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
        self.assertEqual(version[0], (SKILL / "VERSION").read_text(encoding="utf-8").strip())
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
        self.assertEqual(contract["version"], (SKILL / "VERSION").read_text(encoding="utf-8").strip())
        self.assertEqual(contract["schema_version"], 9)
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
        self.trace_ok("feat-art")
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
        self.assertEqual(migrated["schema_version"], 9)
        conn = sqlite3.connect(db)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(work_items)")}
        evidence_columns = {row[1] for row in conn.execute("PRAGMA table_info(evidence)")}
        feature_columns = {row[1] for row in conn.execute("PRAGMA table_info(features)")}
        self.assertIn("conformance", feature_columns)
        bite_columns = {row[1] for row in conn.execute("PRAGMA table_info(bites)")}
        node_columns = {row[1] for row in conn.execute("PRAGMA table_info(nodes)")}
        history = conn.execute(
            "SELECT id, work_item_id, verdict, actor FROM judge_history WHERE work_item_id='work:old:g1:scan'"
        ).fetchall()
        row = conn.execute(
            "SELECT claimed_by, judged_by FROM work_items WHERE id='work:old:g1:scan'"
        ).fetchone()
        conn.close()
        self.assertTrue({"claimed_by", "judged_by", "judged_at", "claimed_at"}.issubset(columns))
        self.assertIn("generation", evidence_columns)
        self.assertIn("coverage_epsilon", feature_columns)
        self.assertIn("drift_limit", feature_columns)
        self.assertTrue({"generation", "phase"}.issubset(bite_columns))
        self.assertIn("stale", node_columns)
        # id 必须是 jh:<work_id>；MariaDB 上用 || 拼会全变成 '0'，多条历史互相覆盖
        self.assertEqual(
            history, [("jh:work:old:g1:scan", "work:old:g1:scan", "passed", "legacy")]
        )
        self.assertEqual(row, ("legacy", "legacy"))
        doctor = self.cli("doctor", expect=1)
        self.assertIn("legacy-identity", doctor["by_check"])
        # legacy 身份只能报给人看，不能自动修（修了就等于伪造审计身份）
        self.assertIn("legacy-identity", doctor["unfixable_checks"])
        self.assertEqual(0, doctor["fixable_count"])

    def test_init_upgrades_legacy_bites_table_without_generation(self):
        """0.4.x 的库：bites 表没有 generation 列，而 idx_bites_feature 建在它上面。

        旧实现先跑完整 DDL（含索引）再补列，所以升级必然
        `no such column: generation`，重试也一样——库永久卡死。
        顺序改成 建表 → 补列 → 建索引 之后才能升上来。
        """
        self.root.mkdir(parents=True)
        db = self.root / "graph.sqlite"
        conn = sqlite3.connect(db)
        conn.execute(
            """CREATE TABLE bites (
                 node_id TEXT NOT NULL, feature_id TEXT NOT NULL, verdict TEXT NOT NULL,
                 reason TEXT, actor TEXT, created_at TEXT NOT NULL,
                 PRIMARY KEY (node_id, feature_id))"""
        )
        conn.execute(
            "INSERT INTO bites(node_id, feature_id, verdict, created_at) "
            "VALUES('operation:demo:x','demo','KEEP','2026-01-01T00:00:00Z')"
        )
        conn.commit()
        conn.close()

        migrated = self.cli("init")
        self.assertEqual(migrated["schema_version"], 9)
        conn = sqlite3.connect(db)
        bite_columns = {row[1] for row in conn.execute("PRAGMA table_info(bites)")}
        indexes = {row[1] for row in conn.execute("PRAGMA index_list(bites)")}
        rows = conn.execute("SELECT node_id, generation FROM bites").fetchall()
        conn.close()
        self.assertIn("generation", bite_columns)
        self.assertIn("idx_bites_feature", indexes)
        # features 表是新建的空表，回填只能得到 NULL——这里只要求升级不丢行
        self.assertEqual([("operation:demo:x", None)], rows)

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
        self.trace_ok("feat-gen")
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
        self.trace_ok("feat-evidence")
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


    # ---------------- 0.5.0 回归：咬合计数化 / 失败历史 / 覆盖 / 模式

    def test_gate_counts_latest_bite_per_node_only(self):
        self.init_repo()
        self.declare("feat-latest")
        other = "use_case:feat-latest:tmp"
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {"id": other, "kind": "use_case", "name": "临时"})
            conn.commit()
        finally:
            conn.close()
        # 跨节点 KEEP 不再抵消 UNNECESSARY（先把该节点并进作用域：bite 不再顺手扩域）
        self.open_targets("feat-latest", "scan", ["use_case:feat-latest:*"])
        self.bite("requirement:feat-latest:main", "UNNECESSARY", feature="feat-latest", reason="多余")
        self.bite(other, "KEEP", feature="feat-latest", reason="别处需要")
        gate = self.cli("gate", "--feature", "feat-latest", "--json", expect=1)
        self.assertEqual(gate["result"], "FAIL")
        self.assertIn("UNNECESSARY/HOLLOW", gate["reason"])
        # 同一节点较新的 KEEP 才能反证
        self.bite("requirement:feat-latest:main", "KEEP", feature="feat-latest", reason="修正")
        gate = self.cli("gate", "--feature", "feat-latest", "--json", expect=1)
        self.assertNotIn("UNNECESSARY/HOLLOW", gate["reason"])
        latest = {item["node"]: item["verdict"] for item in gate["latest_verdicts"]}
        self.assertEqual(latest["requirement:feat-latest:main"], "KEEP")

    def test_sample_is_feature_scoped_and_requires_source(self):
        self.init_repo()
        self.declare("feat-sample")
        self.import_scan("feat-sample")
        sampled = self.cli("sample", "--feature", "feat-sample", "--seed", "7")
        self.assertEqual(sampled["source"], "feature")
        self.assertGreaterEqual(sampled["candidates"], 1)
        scope = self.status("feat-sample")["scope_size"]
        self.assertLessEqual(sampled["candidates"], scope)
        repo_sampled = self.cli("sample", "--repo", "demo", "--seed", "7")
        self.assertEqual(repo_sampled["source"], "repo")
        bad = self.cli("sample", "--seed", "7", expect=2)
        self.assertIn("二选一", bad["error"])

    def test_bite_records_phase_and_generation(self):
        self.init_repo()
        self.declare("feat-phase")
        result = self.bite("requirement:feat-phase:main", "KEEP", feature="feat-phase")
        self.assertEqual(result["phase"], "ArchitectureReconciled")
        self.assertEqual(result["generation"], 1)
        status = self.status("feat-phase")
        self.assertEqual(status["bites"][0]["phase"], "ArchitectureReconciled")

    def test_judge_history_keeps_failures_and_clears_stale_reason(self):
        self.init_repo()
        self.declare("feat-hist")
        arch = self.claim("model-architecture")
        self.finish(arch["claim_token"])
        self.judge(arch["work_item_id"], verdict="failed", reason="结构缺失")
        status = self.status("feat-hist")
        self.assertEqual(status["judge_history"][-1]["verdict"], "failed")
        self.assertEqual(status["judge_history"][-1]["reason"], "结构缺失")
        arch2 = self.claim("model-architecture")
        self.finish(arch2["claim_token"])
        self.judge(arch2["work_item_id"])
        conn = self.db()
        try:
            fail_reason = conn.execute(
                "SELECT fail_reason FROM work_items WHERE id=?", (arch2["work_item_id"],)
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT verdict, actor FROM judge_history WHERE work_item_id=? ORDER BY rowid",
                (arch2["work_item_id"],),
            ).fetchall()
        finally:
            conn.close()
        self.assertIsNone(fail_reason, "judge(passed) 必须清空陈旧 fail_reason")
        self.assertEqual([row[0] for row in rows], ["failed", "passed"])
        self.assertEqual([row[1] for row in rows], ["auditor-1", "auditor-1"])
        doctor = self.cli("doctor")
        self.assertTrue(doctor["ok"])
        self.assertNotIn("judge-history-missing", doctor["by_check"])
        self.assertNotIn("judge-history-work-missing", doctor["by_check"])

    def test_coverage_policy_blocks_judge_until_scope_covered(self):
        self.init_repo()
        self.declare("feat-cov", coverage_epsilon=0.05)
        self.import_scan("feat-cov")
        self.open_targets("feat-cov", "model-architecture", ["requirement:feat-cov:main"])
        arch = self.claim("model-architecture")
        self.finish(arch["claim_token"])
        rejected = self.cli(
            "work-judge", "--id", arch["work_item_id"], "--verdict", "passed",
            "--role", "audit", "--actor", "auditor-1", expect=2,
        )
        self.assertIn("咬合覆盖未达标", rejected["error"])
        cov = self.cli("coverage", "--feature", "feat-cov")
        self.assertTrue(cov["enforced"])
        self.assertFalse(cov["phases"][0]["met"])
        self.assertGreater(cov["phases"][0]["n_required"], 0)
        nodes = self.cli("find")["nodes"]
        self.assertGreaterEqual(len(nodes), cov["phases"][0]["n_required"])
        sys.path.insert(0, str(SKILL / "scripts"))
        from whyexist.workflow import scope_ids  # noqa: WPS433

        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            scope = scope_ids(conn, "feat-cov")
        finally:
            conn.close()
        for node_id in scope:
            self.bite(node_id, "KEEP", feature="feat-cov")
        cov = self.cli("coverage", "--feature", "feat-cov")
        self.assertTrue(cov["phases"][0]["met"], cov)
        self.judge(arch["work_item_id"])
        self.assertEqual(self.status("feat-cov")["conditions"]["ArchitectureReconciled"], 1)

    def test_coverage_defaults_when_policy_off(self):
        self.init_repo()
        self.declare("feat-covdef")
        cov = self.cli("coverage", "--feature", "feat-covdef")
        self.assertFalse(cov["enforced"])
        self.assertEqual(cov["epsilon"], 1.0)
        self.assertEqual(cov["scope_size"], 1)
        self.assertEqual(cov["phases"][0]["n_required"], 0)
        self.assertTrue(cov["phases"][0]["met"])

    def test_pattern_requires_justification_and_attachment(self):
        self.init_repo()
        self.declare("feat-pat")
        self.open_targets("feat-pat", "model-architecture", ["pattern:feat-pat:*", "component:feat-pat:*"])
        arch = self.claim("model-architecture")
        token = arch["claim_token"]
        self.upsert(token, {"id": "pattern:feat-pat:repo", "kind": "pattern", "name": "Repository", "attrs": {}})
        self.upsert(token, {"id": "component:feat-pat:app", "kind": "component", "name": "服务"})
        self.finish(token)
        self.judge(arch["work_item_id"])
        gate = self.cli("gate", "--feature", "feat-pat", "--json", expect=1)
        self.assertIn("模式有限应用", gate["reason"])
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {
                "id": "pattern:feat-pat:repo", "kind": "pattern", "name": "Repository",
                "attrs": {
                    "applicability": "多个写路径复用同一持久化逻辑",
                    "not_applicable": "只有一处 CRUD 时不引入",
                    "alternative": "直接调用 ORM",
                },
            })
            wxg.upsert_edge(conn, {"src": "component:feat-pat:app", "dst": "pattern:feat-pat:repo", "kind": "applies"})
            conn.commit()
        finally:
            conn.close()
        gate = self.cli("gate", "--feature", "feat-pat", "--json", expect=1)
        self.assertNotIn("模式有限应用", gate["reason"])
        self.assertIn("条件未齐", gate["reason"])
        exported = self.cli("export", "--feature", "feat-pat")
        arch_md = (Path(exported["dir"]) / "04-架构.md").read_text(encoding="utf-8")
        self.assertIn("pattern:feat-pat:repo", arch_md)

    def test_pattern_without_applies_edge_fails_gate(self):
        self.init_repo()
        self.declare("feat-pat2")
        self.open_targets("feat-pat2", "model-architecture", ["pattern:feat-pat2:*"])
        arch = self.claim("model-architecture")
        token = arch["claim_token"]
        self.upsert(token, {"id": "pattern:feat-pat2:repo", "kind": "pattern", "name": "Repository", "attrs": {
            "applicability": "有多个写路径", "not_applicable": "单一 CRUD 不引入",
        }})
        self.finish(token)
        self.judge(arch["work_item_id"])
        gate = self.cli("gate", "--feature", "feat-pat2", "--json", expect=1)
        self.assertIn("模式有限应用", gate["reason"])
        self.assertFalse(gate["patterns"][0]["attached"])


    # ---------------- 0.6.0 回归：漂移门禁 / applies 校验 / 大图输出 / 调度

    def test_drift_limit_blocks_gate_above_threshold(self):
        self.init_repo()
        self.declare("feat-drift", drift_limit=0)
        self.import_scan("feat-drift")
        node = self.cli("find", "--kind", "classifier")["nodes"][0]["id"]
        self.bite(node, "UNMAPPED", feature="feat-drift")
        gate = self.cli("gate", "--feature", "feat-drift", "--json", expect=1)
        self.assertIn("结构性漂移", gate["reason"])
        self.assertEqual(gate["drift"]["count"], 1)
        self.assertTrue(gate["drift"]["enforced"])
        # 上限 1 时不因漂移拦门（仍会因条件未齐失败）；bite 不再顺手扩域，先开作用域
        self.declare("feat-drift2", drift_limit=1)
        self.open_targets("feat-drift2", "scan", ["classifier:demo:*"])
        node2 = self.cli("find", "--kind", "classifier")["nodes"][0]["id"]
        self.bite(node2, "UNMAPPED", feature="feat-drift2")
        gate = self.cli("gate", "--feature", "feat-drift2", "--json", expect=1)
        self.assertNotIn("结构性漂移", gate["reason"])
        self.assertIn("条件未齐", gate["reason"])

    def test_declare_validates_drift_limit(self):
        self.init_repo()
        bad = self.cli(
            "feature-declare", "--id", "feat-bad", "--name", "x", "--statement", "s",
            "--acceptance", "[]", "--constraints", "[]", "--drift-limit", "-1", expect=2,
        )
        self.assertIn("drift-limit", bad["error"])

    def test_applies_edge_requires_design_element_to_pattern(self):
        self.init_repo()
        self.declare("feat-applies")
        self.open_targets("feat-applies", "model-architecture", [
            "pattern:feat-applies:*", "component:feat-applies:*", "classifier:feat-applies:*",
        ])
        arch = self.claim("model-architecture")
        token = arch["claim_token"]
        self.upsert(token, {"id": "pattern:feat-applies:p1", "kind": "pattern", "name": "Repository", "attrs": {
            "applicability": "多个写路径", "not_applicable": "单一 CRUD 不用",
        }})
        self.upsert(token, {"id": "component:feat-applies:app", "kind": "component", "name": "服务"})
        self.upsert(token, {"id": "classifier:feat-applies:repo", "kind": "classifier", "name": "OrderRepo"})
        wrong = self.cli(
            "upsert-edge", "--token", token,
            "--data", json.dumps({"src": "pattern:feat-applies:p1", "dst": "component:feat-applies:app", "kind": "applies"}),
            expect=2,
        )
        self.assertIn("applies 的 src", wrong["error"])
        wrong_dst = self.cli(
            "upsert-edge", "--token", token,
            "--data", json.dumps({"src": "classifier:feat-applies:repo", "dst": "component:feat-applies:app", "kind": "applies"}),
            expect=2,
        )
        self.assertIn("applies 的 dst", wrong_dst["error"])
        self.edge(token, "classifier:feat-applies:repo", "pattern:feat-applies:p1", "applies")
        self.finish(token)
        self.judge(arch["work_item_id"])
        gate = self.cli("gate", "--feature", "feat-applies", "--json", expect=1)
        self.assertNotIn("模式有限应用", gate["reason"])

    def test_find_and_slice_support_limit(self):
        self.init_repo()
        self.declare("feat-limit")
        self.import_scan("feat-limit")
        found = self.cli("find", "--limit", "1")
        self.assertEqual(len(found["nodes"]), 1)
        self.assertGreater(found["total"], 1)
        self.assertTrue(found["truncated"])
        all_ids = [node["id"] for node in self.cli("find")["nodes"]]
        sliced = self.cli("slice", "--ids", json.dumps(all_ids), "--limit", "1")
        self.assertEqual(len(sliced["nodes"]), 1)
        self.assertGreater(sliced["nodes_total"], 1)
        self.assertTrue(sliced["truncated"])

    def test_work_claim_brief_omits_slice_bodies(self):
        self.init_repo()
        self.declare("feat-brief")
        claimed = self.cli("work-claim", "--role", "model-architecture", "--actor", "agent-arch", "--brief")
        self.assertIn("summary", claimed["slice"])
        self.assertNotIn("nodes", claimed["slice"])
        self.assertGreater(claimed["slice"]["summary"]["nodes"], 0)

    def test_coverage_next_is_first_unmet_phase(self):
        self.init_repo()
        self.declare("feat-next", coverage_epsilon=0.05)
        cov = self.cli("coverage", "--feature", "feat-next")
        self.assertEqual(cov["next"], cov["phases"][0]["phase"])
        self.assertFalse(cov["phases"][0]["met"])
        self.bite("requirement:feat-next:main", "KEEP", feature="feat-next")
        cov = self.cli("coverage", "--feature", "feat-next")
        self.assertTrue(cov["phases"][0]["met"], cov)
        self.assertEqual(cov["next"], cov["phases"][1]["phase"])

    def test_import_does_not_grow_scan_evidence_ids(self):
        self.init_repo()
        self.declare("feat-scan-ev")
        scan, _ = self.import_scan("feat-scan-ev")
        conn = self.db()
        try:
            evidence_ids = json.loads(conn.execute(
                "SELECT evidence_ids FROM work_items WHERE id=?", (scan["work_item_id"],)
            ).fetchone()[0])
        finally:
            conn.close()
        self.assertEqual(evidence_ids, [])


    # ---------------- 0.7.0 回归：reconcile / 施工标记 / WAL

    def test_reconcile_dry_run_is_read_only_and_idempotent(self):
        self.init_repo()
        self.declare("feat-rec")
        self.trace_ok("feat-rec")
        db = self.root / "graph.sqlite"
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        first = self.cli("reconcile", "--feature", "feat-rec", expect=1)
        second = self.cli("reconcile", "--feature", "feat-rec", expect=1)
        after = hashlib.sha256(db.read_bytes()).hexdigest()
        self.assertEqual(first, second, "reconcile 必须幂等")
        self.assertEqual(first["actions"], [])
        self.assertFalse(first["converged"])
        self.assertEqual(before, after, "dry-run reconcile 不得写状态库")

    def test_reconcile_apply_seeds_missing_ticket(self):
        self.init_repo()
        self.declare("feat-seed")
        conn = self.db()
        conn.execute("DELETE FROM work_items WHERE id='work:feat-seed:g1:model-structure'")
        conn.commit()
        conn.close()
        dry = self.cli("reconcile", "--feature", "feat-seed", expect=1)
        self.assertIn("seed-ticket", [action["action"] for action in dry["actions"]])
        applied = self.cli("reconcile", "--feature", "feat-seed", "--apply", expect=1)
        self.assertIn("seed-ticket", applied["applied"])
        conn = self.db()
        row = conn.execute("SELECT status FROM work_items WHERE id='work:feat-seed:g1:model-structure'").fetchone()
        conn.close()
        self.assertEqual(row[0], "blocked")
        again = self.cli("reconcile", "--feature", "feat-seed", "--apply", expect=1)
        self.assertNotIn("seed-ticket", [action["action"] for action in again["actions"]])

    def test_reconcile_releases_stale_claim(self):
        self.init_repo()
        self.declare("feat-claim")
        claimed = self.claim("model-architecture")
        conn = self.db()
        conn.execute(
            "UPDATE work_items SET claimed_at='2020-01-01T00:00:00Z' WHERE id=?", (claimed["work_item_id"],)
        )
        conn.commit()
        conn.close()
        dry = self.cli("reconcile", "--feature", "feat-claim", expect=1)
        self.assertIn("release-stale-claim", [action["action"] for action in dry["actions"]])
        applied = self.cli("reconcile", "--feature", "feat-claim", "--apply", expect=1)
        self.assertIn("release-stale-claim", applied["applied"])
        stale = self.cli("work-finish", "--token", claimed["claim_token"], expect=2)
        self.assertIn("claim_token", stale["error"])
        reclaimed = self.claim("model-architecture")
        self.assertTrue(reclaimed["claim_token"])

    def test_reconcile_unblocks_after_dependency_passed(self):
        self.init_repo()
        self.declare("feat-unblock")
        arch = self.claim("model-architecture")
        self.finish(arch["claim_token"])
        self.judge(arch["work_item_id"])
        conn = self.db()
        conn.execute("UPDATE work_items SET status='blocked' WHERE id='work:feat-unblock:g1:model-structure'")
        conn.commit()
        conn.close()
        dry = self.cli("reconcile", "--feature", "feat-unblock", expect=1)
        self.assertIn("unblock", [action["action"] for action in dry["actions"]])
        applied = self.cli("reconcile", "--feature", "feat-unblock", "--apply", expect=1)
        self.assertIn("unblock", applied["applied"])

    def test_claim_writes_claimed_at_and_wal_enabled(self):
        self.init_repo()
        self.declare("feat-claim-ts")
        claimed = self.claim("model-architecture")
        conn = self.db()
        claimed_at = conn.execute(
            "SELECT claimed_at FROM work_items WHERE id=?", (claimed["work_item_id"],)
        ).fetchone()[0]
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        conn.close()
        self.assertTrue(claimed_at)
        self.assertEqual(journal.lower(), "wal")

    def test_construction_marker_blocks_gate_and_can_be_cleared(self):
        self.init_repo()
        self.declare("feat-cons")
        self.open_targets("feat-cons", "scan", ["operation:feat-cons:*"])
        node_id = "operation:feat-cons:op"
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {"id": node_id, "kind": "operation", "name": "op", "attrs": {"construction": True}})
            conn.commit()
        finally:
            conn.close()
        self.bite(node_id, "KEEP", feature="feat-cons")
        gate = self.cli("gate", "--feature", "feat-cons", "--json", expect=1)
        self.assertIn("施工中", gate["reason"])
        self.assertEqual(gate["constructions"], [node_id])
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {"id": node_id, "kind": "operation", "name": "op", "attrs": {"construction": False}})
            conn.commit()
        finally:
            conn.close()
        gate = self.cli("gate", "--feature", "feat-cons", "--json", expect=1)
        self.assertNotIn("施工中", gate["reason"])
        self.assertEqual(gate["constructions"], [])

    def test_construction_attr_must_be_bool(self):
        self.init_repo()
        self.declare("feat-cons2")
        self.open_targets("feat-cons2", "model-architecture", ["operation:feat-cons2:*"])
        arch = self.claim("model-architecture")
        bad = self.cli(
            "upsert-node", "--token", arch["claim_token"],
            "--data", json.dumps({"id": "operation:feat-cons2:op", "kind": "operation", "name": "op",
                                  "attrs": {"construction": "yes"}}),
            expect=2,
        )
        self.assertIn("construction", bad["error"])


    # ---------------- 0.8.0 回归：变更集

    def test_change_open_requires_ready(self):
        self.init_repo()
        self.declare("feat-ch0")
        bad = self.cli(
            "change-open", "--feature", "feat-ch0", "--statement", "改设计",
            "--from-condition", "StructureReconciled", expect=2,
        )
        self.assertIn("Ready", bad["error"])

    def test_change_open_inherits_and_seeds_downstream(self):
        self.init_repo()
        self.declare("feat-ch1")
        self.force_ready("feat-ch1")
        opened = self.cli(
            "change-open", "--feature", "feat-ch1", "--statement", "改持久化边界",
            "--from-condition", "StructureReconciled",
        )
        self.assertEqual(opened["to_generation"], 2)
        self.assertEqual(opened["inherited"], ["ArchitectureReconciled"])
        status = self.status("feat-ch1")
        self.assertEqual(status["conditions"]["ArchitectureReconciled"], 1)
        self.assertEqual(status["conditions"]["StructureReconciled"], 0)
        self.assertEqual(status["conditions"]["Ready"], 0)
        self.assertEqual(len(status["changes"]), 1)
        listed = self.cli("work-list", "--feature", "feat-ch1")
        by_kind = {item["kind"]: item["status"] for item in listed["work_items"]}
        self.assertEqual(by_kind["model-structure"], "ready")
        self.assertEqual(by_kind["interact"], "blocked")
        reconcile = self.cli("reconcile", "--feature", "feat-ch1", expect=1)
        self.assertNotIn("seed-ticket", [action["action"] for action in reconcile["actions"]])

    def test_change_open_rejects_second_while_open(self):
        self.init_repo()
        self.declare("feat-ch2")
        self.force_ready("feat-ch2")
        self.cli(
            "change-open", "--feature", "feat-ch2", "--statement", "第一次",
            "--from-condition", "ArchitectureReconciled",
        )
        bad = self.cli(
            "change-open", "--feature", "feat-ch2", "--statement", "第二次",
            "--from-condition", "ArchitectureReconciled", expect=2,
        )
        self.assertIn("Ready", bad["error"])

    def test_change_diff_lists_written_nodes_and_anchors(self):
        self.init_repo()
        self.declare("feat-ch3")
        self.open_targets("feat-ch3", "model-architecture", ["classifier:feat-ch3:*"])
        arch = self.claim("model-architecture")
        self.upsert(arch["claim_token"], {
            "id": "classifier:feat-ch3:old", "kind": "classifier", "name": "Old",
            "repo": "demo", "path": "old.py", "symbol": "Old",
        })
        self.finish(arch["claim_token"])
        self.force_ready("feat-ch3")
        self.cli(
            "change-open", "--feature", "feat-ch3", "--statement", "换实现",
            "--from-condition", "ArchitectureReconciled",
        )
        self.open_targets("feat-ch3", "model-architecture", ["classifier:feat-ch3:new"])
        arch2 = self.claim("model-architecture")
        self.upsert(arch2["claim_token"], {
            "id": "classifier:feat-ch3:new", "kind": "classifier", "name": "New",
            "repo": "demo", "path": "new.py", "symbol": "New",
        })
        self.finish(arch2["claim_token"])
        diff = self.cli("change-diff", "--feature", "feat-ch3")
        self.assertEqual(diff["to_generation"], 2)
        self.assertIn("classifier:feat-ch3:new", diff["added"])
        self.assertIn("classifier:feat-ch3:old", diff["removed"])
        anchors = {item["node"]: item["path"] for item in diff["code_anchors"]}
        self.assertEqual(anchors["classifier:feat-ch3:new"], "new.py")

    def test_change_from_late_condition_inherits_all_earlier(self):
        self.init_repo()
        self.declare("feat-ch4")
        self.force_ready("feat-ch4")
        opened = self.cli(
            "change-open", "--feature", "feat-ch4", "--statement", "只改行为",
            "--from-condition", "BehaviorPassed",
        )
        self.assertEqual(
            opened["inherited"],
            ["ArchitectureReconciled", "StructureReconciled", "InteractionsReconciled",
             "TestsSpecified", "TestsImplemented"],
        )
        self.assertEqual(opened["reset"], ["BehaviorPassed"])

    def test_doctor_flags_change_inheritance_drift(self):
        self.init_repo()
        self.declare("feat-ch5")
        self.force_ready("feat-ch5")
        self.cli(
            "change-open", "--feature", "feat-ch5", "--statement", "改结构",
            "--from-condition", "StructureReconciled",
        )
        conn = self.db()
        conn.execute(
            "UPDATE conditions SET status=0 WHERE feature_id='feat-ch5' AND generation=2 "
            "AND name='ArchitectureReconciled'"
        )
        conn.commit()
        conn.close()
        doctor = self.cli("doctor", expect=1)
        self.assertIn("change-inheritance", doctor["by_check"])


    # ---------------- 0.9.0 回归：回扫断言

    def only_orderrepo_shop(self):
        return SHOP_PY.split("\n\ndef create_order")[0] + "\n"

    def test_import_marks_stale_nodes_when_symbol_removed(self):
        self.init_repo()
        self.declare("feat-stale")
        scan, _ = self.import_scan("feat-stale")
        node = "operation:demo:shop.py:create_order"
        self.assertFalse(bool(self.cli("get", "--id", node)["node"]["stale"]))
        (self.repo / "shop.py").write_text(self.only_orderrepo_shop(), encoding="utf-8")
        prepared = self.cli(
            "import-file", "--file", str(self.repo / "shop.py"), "--feature", "feat-stale", "--prepare"
        )
        self.assertGreaterEqual(prepared["stale_candidates"], 1)
        written = self.cli("import-file", "--file", str(self.repo / "shop.py"), "--token", scan["claim_token"])
        self.assertGreaterEqual(written["stale_marked"], 1)
        self.assertIn(node, written["stale_nodes"])
        self.assertTrue(bool(self.cli("get", "--id", node)["node"]["stale"]))
        status = self.status("feat-stale")
        self.assertIn(node, status["stale"])
        gate = self.cli("gate", "--feature", "feat-stale", "--json", expect=1)
        self.assertIn("stale", gate["reason"])
        (self.repo / "shop.py").write_text(SHOP_PY, encoding="utf-8")
        self.cli("import-file", "--file", str(self.repo / "shop.py"), "--feature", "feat-stale", "--prepare")
        self.cli("import-file", "--file", str(self.repo / "shop.py"), "--token", scan["claim_token"])
        self.assertFalse(bool(self.cli("get", "--id", node)["node"]["stale"]))
        gate = self.cli("gate", "--feature", "feat-stale", "--json", expect=1)
        self.assertNotIn("stale", gate["reason"])

    def test_sync_reports_missing_and_new_read_only(self):
        self.init_repo()
        self.declare("feat-sync")
        self.import_scan("feat-sync")
        db = self.root / "graph.sqlite"
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        (self.repo / "shop.py").write_text(self.only_orderrepo_shop(), encoding="utf-8")
        (self.repo / "extra.py").write_text("class Extra:\n    def run(self):\n        return 1\n", encoding="utf-8")
        report = self.cli("sync", "--repo", "demo")
        self.assertIn("operation:demo:shop.py:create_order", report["missing"])
        self.assertTrue(any(node.startswith("classifier:demo:extra.py:Extra") for node in report["new"]))
        # changed 里 unmapped 节点（len/range 等聚合）行号变化也算变化，单独计数
        self.assertIn("changed_unmapped_count", report)
        for item in report["changed"]:
            self.assertIn("unmapped", item)
        self.assertEqual(before, hashlib.sha256(db.read_bytes()).hexdigest(), "sync 不得写状态库")
        zero = self.cli("sync", "--repo", "demo", "--limit", "0")
        self.assertEqual(zero["missing"], [])
        self.assertGreater(zero["missing_count"], 0)

    def test_sync_rejects_unregistered_repo(self):
        self.init_repo()
        bad = self.cli("sync", "--repo", "nope", expect=2)
        self.assertIn("未登记", bad["error"])


    # ---------------- 1.0.0 回归：默认覆盖策略

    def test_new_feature_defaults_coverage_on(self):
        self.init_repo()
        self.cli(
            "feature-declare", "--id", "feat-default", "--name", "默认", "--statement", "s",
            "--acceptance", "[]", "--constraints", "[]",
        )
        status = self.status("feat-default")
        self.assertTrue(status["coverage"]["enforced"])
        self.assertEqual(status["coverage"]["epsilon"], 1.0)
        self.assertEqual(status["coverage"]["phases"][0]["n_required"], 0)
        arch = self.claim("model-architecture")
        self.finish(arch["claim_token"])
        self.judge(arch["work_item_id"])
        self.assertEqual(self.status("feat-default")["conditions"]["ArchitectureReconciled"], 1)

    def test_no_coverage_flag_and_conflict(self):
        self.init_repo()
        conflict = self.cli(
            "feature-declare", "--id", "feat-nc", "--name", "x", "--statement", "s",
            "--acceptance", "[]", "--constraints", "[]",
            "--no-coverage", "--coverage-epsilon", "1.0", expect=2,
        )
        self.assertIn("互斥", conflict["error"])
        self.cli(
            "feature-declare", "--id", "feat-nc", "--name", "x", "--statement", "s",
            "--acceptance", "[]", "--constraints", "[]", "--no-coverage",
        )
        self.assertFalse(self.status("feat-nc")["coverage"]["enforced"])

    def test_redeclare_preserves_explicit_coverage_policy(self):
        self.init_repo()
        self.declare("feat-keep", coverage_epsilon=0.5)
        self.cli(
            "feature-declare", "--id", "feat-keep", "--name", "再次", "--statement", "s2",
            "--acceptance", "[]", "--constraints", "[]",
        )
        self.assertEqual(self.status("feat-keep")["coverage"]["epsilon"], 0.5)
        self.cli(
            "feature-declare", "--id", "feat-keep", "--name", "关闭", "--statement", "s3",
            "--acceptance", "[]", "--constraints", "[]", "--no-coverage",
        )
        self.assertFalse(self.status("feat-keep")["coverage"]["enforced"])


    # ---------------- 1.1.0 回归：常驻控制器

    def test_serve_once_without_apply_is_read_only(self):
        self.init_repo()
        self.declare("feat-serve")
        conn = self.db()
        conn.execute("DELETE FROM work_items WHERE id='work:feat-serve:g1:model-structure'")
        conn.commit()
        conn.close()
        db = self.root / "graph.sqlite"
        before = hashlib.sha256(db.read_bytes()).hexdigest()
        summary = self.cli("serve", "--once")
        after = hashlib.sha256(db.read_bytes()).hexdigest()
        self.assertEqual(before, after, "serve --once 默认不得写状态库")
        self.assertEqual(summary["pass"], 1)
        feature = summary["features"][0]
        self.assertEqual(feature["feature"], "feat-serve")
        self.assertIn("seed-ticket", [action["action"] for action in feature["actions"]])
        self.assertEqual(feature["applied"], [])
        self.assertFalse(feature["converged"])

    def test_serve_once_apply_seeds_missing_ticket(self):
        self.init_repo()
        self.declare("feat-serve2")
        conn = self.db()
        conn.execute("DELETE FROM work_items WHERE id='work:feat-serve2:g1:model-structure'")
        conn.commit()
        conn.close()
        summary = self.cli("serve", "--once", "--apply")
        feature = summary["features"][0]
        self.assertIn("seed-ticket", feature["applied"])
        conn = self.db()
        row = conn.execute(
            "SELECT status FROM work_items WHERE id='work:feat-serve2:g1:model-structure'"
        ).fetchone()
        conn.close()
        self.assertEqual(row[0], "blocked")

    def test_serve_validates_interval(self):
        self.init_repo()
        self.declare("feat-serve3")
        bad = self.cli("serve", "--once", "--interval", "0", expect=2)
        self.assertIn("interval", bad["error"])


    # ---------------- 1.3.0 回归：设计-代码一致性

    def test_conformance_reports_anchor_structure_and_tests(self):
        self.init_repo()
        self.declare("feat-conf")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            f = "feat-conf"

            def node(nid, kind, **kwargs):
                wxg.upsert_node(conn, {"id": nid, "kind": kind, "feature_id": f, **kwargs})

            def edge(src, dst, kind):
                wxg.upsert_edge(conn, {"src": src, "dst": dst, "kind": kind})

            node(f"use_case:{f}:uc", "use_case", name="uc")
            node(f"component:{f}:a", "component", name="A")
            node(f"component:{f}:b", "component", name="B")
            node(f"component:{f}:c", "component", name="C")
            node("operation:demo:a.py:A.run", "operation", name="A.run", repo="demo", path="a.py", symbol="A.run")
            node("operation:demo:b.py:B.run", "operation", name="B.run", repo="demo", path="b.py", symbol="B.run")
            node("operation:demo:c.py:C.run", "operation", name="C.run", repo="demo", path="c.py", symbol="C.run")
            node(f"testcase:{f}:t", "testcase", name="t")
            edge(f"use_case:{f}:uc", "operation:demo:a.py:A.run", "maps_to")
            edge(f"component:{f}:a", "operation:demo:a.py:A.run", "maps_to")
            edge(f"component:{f}:b", "operation:demo:b.py:B.run", "maps_to")
            edge(f"component:{f}:c", "operation:demo:c.py:C.run", "maps_to")
            edge(f"component:{f}:a", f"component:{f}:b", "depends")
            edge("operation:demo:a.py:A.run", "operation:demo:b.py:B.run", "calls")
            edge(f"testcase:{f}:t", f"use_case:{f}:uc", "verifies")
            conn.commit()
            report = self.cli("conformance", "--feature", f)
            self.assertEqual(report["violations"], 0, report)
            self.assertFalse(report["enforced"])
            # 未声明耦合：A 调用 C，但没有 depends/associates
            edge("operation:demo:a.py:A.run", "operation:demo:c.py:C.run", "calls")
            conn.commit()
            report = self.cli("conformance", "--feature", f)
            self.assertEqual(report["structural"]["undeclared_count"], 1)
            # 缺锚点：component D 没有 maps_to
            node(f"component:{f}:d", "component", name="D")
            conn.commit()
            report = self.cli("conformance", "--feature", f)
            self.assertIn(f"component:{f}:d", report["anchors"]["missing"])
            # 缺测试覆盖：删掉 verifies
            conn.execute(
                "DELETE FROM edges WHERE kind='verifies' AND src=? AND dst=?",
                (f"testcase:{f}:t", f"use_case:{f}:uc"),
            )
            conn.commit()
            report = self.cli("conformance", "--feature", f)
            self.assertIn(f"use_case:{f}:uc", report["tests"]["missing"])
        finally:
            conn.close()

    def test_conformance_gate_opt_in(self):
        self.init_repo()
        self.cli(
            "feature-declare", "--id", "feat-cg", "--name", "cg", "--statement", "s",
            "--acceptance", "[]", "--constraints", "[]", "--no-coverage", "--conformance",
        )
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {
                "id": "component:feat-cg:orphan", "kind": "component", "name": "孤儿组件",
                "feature_id": "feat-cg",
            })
            conn.commit()
        finally:
            conn.close()
        gate = self.cli("gate", "--feature", "feat-cg", "--json", expect=1)
        self.assertIn("一致性", gate["reason"])
        self.assertIn("component:feat-cg:orphan", gate["conformance"]["anchors"]["missing"])
        # 补锚点后，一致性不再是最先触发的原因
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {
                "id": "operation:demo:cg.py:run", "kind": "operation", "name": "run",
                "repo": "demo", "path": "cg.py", "symbol": "run", "feature_id": "feat-cg",
            })
            wxg.upsert_edge(conn, {
                "src": "component:feat-cg:orphan", "dst": "operation:demo:cg.py:run", "kind": "maps_to",
            })
            conn.commit()
        finally:
            conn.close()
        gate = self.cli("gate", "--feature", "feat-cg", "--json", expect=1)
        self.assertNotIn("一致性", gate["reason"])
        self.assertIn("条件未齐", gate["reason"])

    def test_conformance_flag_preserved_and_disabled(self):
        self.init_repo()
        self.cli(
            "feature-declare", "--id", "feat-cf", "--name", "cf", "--statement", "s",
            "--acceptance", "[]", "--constraints", "[]", "--no-coverage", "--conformance",
        )
        self.assertTrue(self.status("feat-cf")["conformance"]["enforced"])
        self.cli(
            "feature-declare", "--id", "feat-cf", "--name", "cf2", "--statement", "s2",
            "--acceptance", "[]", "--constraints", "[]",
        )
        self.assertTrue(self.status("feat-cf")["conformance"]["enforced"])
        self.cli(
            "feature-declare", "--id", "feat-cf", "--name", "cf3", "--statement", "s3",
            "--acceptance", "[]", "--constraints", "[]", "--no-conformance",
        )
        self.assertFalse(self.status("feat-cf")["conformance"]["enforced"])


    def test_conformance_resolves_unique_unmapped_calls_heuristically(self):
        self.init_repo()
        self.declare("feat-heur")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            f = "feat-heur"

            def node(nid, kind, **kwargs):
                wxg.upsert_node(conn, {"id": nid, "kind": kind, "feature_id": f, **kwargs})

            def edge(src, dst, kind):
                wxg.upsert_edge(conn, {"src": src, "dst": dst, "kind": kind})

            node(f"component:{f}:a", "component", name="A")
            node(f"component:{f}:b", "component", name="B")
            node("operation:demo:a.py:A.run", "operation", name="A.run", repo="demo", path="a.py", symbol="A.run")
            node("operation:demo:b.py:helper", "operation", name="helper", repo="demo", path="b.py", symbol="helper")
            node(
                "operation:demo:a.py:@9:helper", "operation", name="helper",
                repo="demo", path="a.py", symbol="@9:helper", unmapped=1,
            )
            edge(f"component:{f}:a", "operation:demo:a.py:A.run", "maps_to")
            edge(f"component:{f}:b", "operation:demo:b.py:helper", "maps_to")
            edge(f"component:{f}:a", f"component:{f}:b", "depends")
            edge("operation:demo:a.py:A.run", "operation:demo:a.py:@9:helper", "calls")
            conn.commit()
            report = self.cli("conformance", "--feature", f)
            self.assertEqual(report["structural"]["missing_backing_count"], 0, report)
            self.assertEqual(report["structural"]["resolved_heuristically"], 1)
        finally:
            conn.close()

    def test_maps_to_write_validation(self):
        self.init_repo()
        self.declare("feat-mapv")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            f = "feat-mapv"
            wxg.upsert_node(conn, {"id": f"use_case:{f}:uc", "kind": "use_case", "name": "uc", "feature_id": f})
            wxg.upsert_node(conn, {
                "id": "operation:demo:v.py:run", "kind": "operation", "name": "run",
                "repo": "demo", "path": "v.py", "symbol": "run", "feature_id": f,
            })
            wxg.upsert_node(conn, {"id": f"component:{f}:x", "kind": "component", "name": "X", "feature_id": f})
            with self.assertRaises(wxg.Reject):
                wxg.upsert_edge(conn, {"src": "operation:demo:v.py:run", "dst": f"use_case:{f}:uc", "kind": "maps_to"})
            with self.assertRaises(wxg.Reject):
                wxg.upsert_edge(conn, {"src": f"use_case:{f}:uc", "dst": f"component:{f}:x", "kind": "maps_to"})
            wxg.upsert_edge(conn, {"src": f"use_case:{f}:uc", "dst": "operation:demo:v.py:run", "kind": "maps_to"})
            conn.commit()
        finally:
            conn.close()

    def test_conformance_reports_code_orphans(self):
        self.init_repo()
        self.declare("feat-orph")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            f = "feat-orph"
            wxg.upsert_node(conn, {
                "id": "operation:demo:o.py:run", "kind": "operation", "name": "run",
                "repo": "demo", "path": "o.py", "symbol": "run", "feature_id": f,
            })
            conn.commit()
            report = self.cli("conformance", "--feature", f)
            self.assertIn("operation:demo:o.py:run", report["anchors"]["code_orphans"])
            wxg.upsert_node(conn, {"id": f"component:{f}:c", "kind": "component", "name": "C", "feature_id": f})
            wxg.upsert_edge(conn, {
                "src": f"component:{f}:c", "dst": "operation:demo:o.py:run", "kind": "maps_to",
            })
            conn.commit()
            report = self.cli("conformance", "--feature", f)
            self.assertNotIn("operation:demo:o.py:run", report["anchors"]["code_orphans"])
        finally:
            conn.close()


    # ---------------------------------------------------------- 3.6.0 追溯门

    def test_acceptance_add_creates_node_and_rejects_duplicates(self):
        self.init_repo()
        self.declare("feat-acc", acceptance=["声明期验收"])
        self.open_targets("feat-acc", "specify-test", ["requirement:feat-acc:main", "acceptance:feat-acc:*"])
        self.ready_ticket("feat-acc", "specify-test")
        spec = self.claim("specify-test")
        token = spec["claim_token"]
        first = self.cli("acceptance-add", "--requirement", "requirement:feat-acc:main",
                         "--text", "返回成功", "--token", token)
        self.assertEqual(first["ordinal"], 2)
        self.assertEqual(first["id"], "acceptance:feat-acc:main:02")
        second = self.cli("acceptance-add", "--requirement", "requirement:feat-acc:main",
                          "--text", "订单落库", "--token", token)
        self.assertEqual(second["ordinal"], 3)
        # 同一条文重复登记拒绝；空条文也拒绝
        self.cli("acceptance-add", "--requirement", "requirement:feat-acc:main",
                 "--text", "声明期验收", "--token", token, expect=2)
        self.cli("acceptance-add", "--requirement", "requirement:feat-acc:main",
                 "--text", "  ", "--token", token, expect=2)
        trace = self.cli("trace", "--feature", "feat-acc", "--json", expect=1)
        self.assertEqual(trace["summary"]["acceptance_items"], 3)
        self.assertEqual(trace["summary"]["acceptance_tested"], 0)
        self.assertEqual(trace["summary"]["acceptance_missing"], 3)

    def test_acceptance_add_rejects_non_requirement(self):
        self.init_repo()
        self.declare("feat-acc-kind")
        self.open_targets("feat-acc-kind", "specify-test", ["use_case:feat-acc-kind:*"])
        self.ready_ticket("feat-acc-kind", "specify-test")
        spec = self.claim("specify-test")
        token = spec["claim_token"]
        self.upsert(token, {"id": "use_case:feat-acc-kind:uc", "kind": "use_case", "name": "uc"})
        rejected = self.cli("acceptance-add", "--requirement", "use_case:feat-acc-kind:uc",
                            "--text", "x", "--token", token, expect=2)
        self.assertIn("requirement", rejected["error"])

    def test_acceptance_import_is_idempotent_and_dry_run_reads_only(self):
        self.init_repo()
        self.declare("feat-imp")
        conn = self.db()
        # 模拟旧库：需求只有 x_acceptance 文本，没有 acceptance 节点
        conn.execute("DELETE FROM edges WHERE kind='has_acceptance'")
        conn.execute("DELETE FROM nodes WHERE kind='acceptance'")
        conn.execute(
            "UPDATE nodes SET attrs_json=? WHERE id='requirement:feat-imp:main'",
            (json.dumps({"statement": "创建订单。", "x_acceptance": ["返回成功", "订单落库"]}, ensure_ascii=False),),
        )
        conn.commit()
        conn.close()
        before = hashlib.sha256((self.root / "graph.sqlite").read_bytes()).hexdigest()
        dry = self.cli("acceptance-import", "--feature", "feat-imp", "--dry-run")
        self.assertEqual(dry["created_count"], 2)
        after = hashlib.sha256((self.root / "graph.sqlite").read_bytes()).hexdigest()
        self.assertEqual(before, after, "--dry-run 不得写状态库")
        self.open_targets("feat-imp", "specify-test", ["requirement:feat-imp:main", "acceptance:feat-imp:*"])
        self.ready_ticket("feat-imp", "specify-test")
        spec = self.claim("specify-test")
        token = spec["claim_token"]
        first = self.cli("acceptance-import", "--feature", "feat-imp", "--token", token)
        self.assertEqual(first["created_count"], 2)
        second = self.cli("acceptance-import", "--feature", "feat-imp", "--token", token)
        self.assertEqual(second["created_count"], 0)
        self.assertEqual(second["existed_count"], 2)

    def test_acceptance_import_skips_requirements_outside_targets(self):
        self.init_repo()
        self.declare("feat-imp2")
        self.declare("feat-imp2")
        conn = self.db()
        conn.execute(
            "UPDATE nodes SET attrs_json=? WHERE id='requirement:feat-imp2:main'",
            (json.dumps({"statement": "main", "x_acceptance": ["main 验收"]}, ensure_ascii=False),),
        )
        conn.execute(
            "INSERT OR IGNORE INTO nodes(id, kind, name, attrs_json) VALUES(?,?,?,?)",
            ("requirement:feat-imp2:other", "requirement", "other",
             json.dumps({"statement": "other", "x_acceptance": ["other 验收"]}, ensure_ascii=False)),
        )
        conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)",
                     ("feat-imp2", "requirement:feat-imp2:other"))
        conn.commit()
        conn.close()
        self.open_targets("feat-imp2", "specify-test", ["requirement:feat-imp2:main"])
        self.ready_ticket("feat-imp2", "specify-test")
        spec = self.claim("specify-test")
        result = self.cli("acceptance-import", "--feature", "feat-imp2", "--token", spec["claim_token"])
        self.assertEqual(result["created_count"], 1)
        self.assertEqual(result["skipped_out_of_scope"], ["requirement:feat-imp2:other"])

    def test_gate_unknown_when_requirements_have_no_acceptance(self):
        self.init_repo()
        self.declare("feat-unknown")
        # 模拟旧库：需求存在，但既没有 acceptance 节点也没有 x_acceptance 文本
        conn = self.db()
        conn.execute("DELETE FROM edges WHERE kind='has_acceptance'")
        conn.execute("DELETE FROM nodes WHERE kind='acceptance'")
        conn.execute(
            "UPDATE nodes SET attrs_json=? WHERE id='requirement:feat-unknown:main'",
            (json.dumps({"statement": "创建订单。"}, ensure_ascii=False),),
        )
        conn.commit()
        conn.close()
        self.cli("evidence-record", "--feature", "feat-unknown", "--name", "e", "--command", "true", "--actor", "t")
        self.force_ready("feat-unknown")
        result = self.cli("gate", "--feature", "feat-unknown", "--json", expect=1)
        self.assertEqual(result["result"], "UNKNOWN")
        self.assertIn("验收", result["reason"])
        self.assertEqual(result["traceability"]["summary"]["acceptance_items"], 0)

    def test_gate_fails_when_acceptance_is_untested(self):
        self.init_repo()
        self.declare("feat-untested")
        self.cli("evidence-record", "--feature", "feat-untested", "--name", "e", "--command", "true", "--actor", "t")
        self.trace_ok("feat-untested")
        conn = self.db()
        conn.execute("DELETE FROM edges WHERE kind='verifies' AND dst LIKE 'acceptance:feat-untested:%'")
        conn.commit()
        conn.close()
        self.force_ready("feat-untested")
        result = self.cli("gate", "--feature", "feat-untested", "--json", expect=1)
        self.assertEqual(result["result"], "FAIL")
        self.assertIn("追溯", result["reason"])
        self.assertEqual(len(result["missing_acceptance"]), 1)

    def test_export_reads_acceptance_nodes_not_declaration_json(self):
        """01-需求.md 的验收列只认 acceptance 节点；声明快照不再写进 requirement attrs。"""
        self.init_repo()
        self.declare("feat-exp", acceptance=["返回成功", "订单落库"])
        self.open_targets("feat-exp", "specify-test", ["requirement:feat-exp:main", "acceptance:feat-exp:*"])
        self.ready_ticket("feat-exp", "specify-test")
        spec = self.claim("specify-test")
        self.cli("acceptance-add", "--requirement", "requirement:feat-exp:main",
                 "--text", "日志可查", "--token", spec["claim_token"])
        exported = self.cli("export", "--feature", "feat-exp")
        text = (Path(exported["dir"]) / "01-需求.md").read_text(encoding="utf-8")
        self.assertIn("返回成功", text)
        self.assertIn("订单落库", text)
        self.assertIn("日志可查", text)
        conn = self.db()
        attrs = json.loads(conn.execute(
            "SELECT attrs_json FROM nodes WHERE id='requirement:feat-exp:main'").fetchone()[0])
        conn.close()
        self.assertNotIn("x_acceptance", attrs, "声明快照不应再写进 requirement attrs（与 acceptance 节点重复）")

    def test_doctor_reports_acceptance_structure_issues(self):
        self.init_repo()
        self.declare("feat-doc-acc")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        wxg.upsert_node(conn, {"id": "acceptance:feat-doc-acc:main:09", "kind": "acceptance",
                               "name": "孤儿", "attrs": {"text": "孤儿", "ordinal": 9}})
        wxg.upsert_node(conn, {"id": "requirement:feat-doc-acc:other", "kind": "requirement",
                               "name": "other", "attrs": {"statement": "other"}})
        # 多父是旧库才可能有的坏数据（新写入会被 upsert-edge 拒绝），这里直接造行
        conn.execute(
            "INSERT INTO edges(id, src, dst, kind) VALUES(?,?,?,?)",
            ("edge:has_acceptance:requirement:feat-doc-acc:other:acceptance:feat-doc-acc:main:01",
             "requirement:feat-doc-acc:other", "acceptance:feat-doc-acc:main:01", "has_acceptance"),
        )
        conn.execute(
            "UPDATE nodes SET attrs_json=? WHERE id='acceptance:feat-doc-acc:main:01'",
            (json.dumps({"text": "返回成功", "ordinal": 3}, ensure_ascii=False),),
        )
        conn.commit()
        conn.close()
        doctor = self.cli("doctor", expect=1)
        for name in ("acceptance-orphan", "acceptance-multi-parent", "acceptance-ordinal"):
            self.assertIn(name, doctor["by_check"])

    def test_doctor_reports_acceptance_source_drift(self):
        """旧库两边都在但对不上时，doctor 报漂移（不自动修：哪边对得人定）。"""
        self.init_repo()
        self.declare("feat-drift-acc")
        conn = self.db()
        conn.execute(
            "UPDATE nodes SET attrs_json=? WHERE id='requirement:feat-drift-acc:main'",
            (json.dumps({"statement": "创建订单。", "x_acceptance": ["另一条验收"]}, ensure_ascii=False),),
        )
        conn.commit()
        conn.close()
        doctor = self.cli("doctor", expect=1)
        self.assertIn("acceptance-source-drift", doctor["by_check"])

    def test_acceptance_edges_are_guarded_at_write_time(self):
        """3.9.0：has_acceptance / verifies 的结构不变量在写入期就拒绝，doctor 只兜旧库。"""
        self.init_repo()
        self.declare("feat-edge-guard")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {"id": "acceptance:feat-edge-guard:main:09", "kind": "acceptance",
                                   "name": "孤儿", "attrs": {"text": "孤儿", "ordinal": 9}})
            wxg.upsert_node(conn, {"id": "use_case:feat-edge-guard:uc", "kind": "use_case", "name": "uc"})
            # src 必须是 requirement
            with self.assertRaises(wxg.Reject):
                wxg.upsert_edge(conn, {"src": "use_case:feat-edge-guard:uc",
                                       "dst": "acceptance:feat-edge-guard:main:09", "kind": "has_acceptance"})
            # dst 必须是 acceptance
            with self.assertRaises(wxg.Reject):
                wxg.upsert_edge(conn, {"src": "requirement:feat-edge-guard:main",
                                       "dst": "use_case:feat-edge-guard:uc", "kind": "has_acceptance"})
            # 一个条目只能挂一条需求
            wxg.upsert_node(conn, {"id": "requirement:feat-edge-guard:other", "kind": "requirement",
                                   "name": "other", "attrs": {"statement": "other"}})
            with self.assertRaises(wxg.Reject):
                wxg.upsert_edge(conn, {"src": "requirement:feat-edge-guard:other",
                                       "dst": "acceptance:feat-edge-guard:main:01", "kind": "has_acceptance"})
            # 同一父重复写是幂等的
            wxg.upsert_edge(conn, {"src": "requirement:feat-edge-guard:main",
                                   "dst": "acceptance:feat-edge-guard:main:01", "kind": "has_acceptance"})
            # verifies 指向 acceptance 时 src 必须是 testcase
            with self.assertRaises(wxg.Reject):
                wxg.upsert_edge(conn, {"src": "use_case:feat-edge-guard:uc",
                                       "dst": "acceptance:feat-edge-guard:main:01", "kind": "verifies"})
            conn.commit()
        finally:
            conn.close()

    def test_doctor_reports_bite_out_of_scope(self):
        """旧库可能留着“咬合把节点带进作用域”时期的越界咬合，doctor 只报告。"""
        self.init_repo()
        self.declare("feat-bite-doc")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            wxg.upsert_node(conn, {"id": "operation:outside:op", "kind": "operation", "name": "op"})
            conn.execute(
                "INSERT INTO bites(node_id, feature_id, generation, phase, verdict, reason, actor, created_at) "
                "VALUES(?,?,?,?,?,?,?,?)",
                ("operation:outside:op", "feat-bite-doc", 1, None, "KEEP", "旧库", "agent", "2026-01-01T00:00:00Z"),
            )
            conn.commit()
        finally:
            conn.close()
        doctor = self.cli("doctor", expect=1)
        self.assertIn("bite-out-of-scope", doctor["by_check"])

    def test_trace_treats_main_requirement_as_aggregate(self):
        """main 是伞节点：有其它需求时，它自己没有验收条目不算缺口。"""
        self.init_repo()
        self.declare("feat-agg")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("DELETE FROM edges WHERE kind='has_acceptance'")
            conn.execute("DELETE FROM nodes WHERE kind='acceptance'")
            wxg.upsert_node(conn, {"id": "requirement:feat-agg:sub", "kind": "requirement",
                                   "name": "子需求", "attrs": {"statement": "子需求"}})
            conn.commit()
        finally:
            conn.close()
        self.trace_ok("feat-agg", requirement="requirement:feat-agg:sub")
        trace = self.cli("trace", "--feature", "feat-agg", "--json", expect=0)
        self.assertEqual(["requirement:feat-agg:main"], trace["aggregate_requirements"])
        self.assertEqual([], trace["without_acceptance"])
        self.assertEqual(1, trace["summary"]["aggregate_requirements"])
        self.assertTrue(trace["summary"]["complete"])

    def test_trace_main_requirement_is_gated_when_it_is_the_only_one(self):
        """只有 main 一条需求时它不是伞节点，没验收就是缺口。"""
        self.init_repo()
        self.declare("feat-agg-only")
        conn = self.db()
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("DELETE FROM edges WHERE kind='has_acceptance'")
            conn.execute("DELETE FROM nodes WHERE kind='acceptance'")
            conn.commit()
        finally:
            conn.close()
        trace = self.cli("trace", "--feature", "feat-agg-only", "--json", expect=1)
        self.assertEqual([], trace["aggregate_requirements"])
        self.assertEqual(["requirement:feat-agg-only:main"], trace["without_acceptance"])
        self.assertFalse(trace["summary"]["complete"])

    def test_trace_md_and_requirement_drilldown(self):
        """3.10.0：--md 出人读表格，--requirement 钻取单条需求。"""
        self.init_repo()
        self.declare("feat-md")
        self.open_targets("feat-md", "specify-test", ["requirement:feat-md:main", "acceptance:feat-md:*"])
        self.ready_ticket("feat-md", "specify-test")
        spec = self.claim("specify-test")
        self.cli("acceptance-add", "--requirement", "requirement:feat-md:main",
                 "--text", "第二条", "--token", spec["claim_token"])
        md = self.cli("trace", "--feature", "feat-md", "--md", expect=1)
        self.assertIsInstance(md, str)
        self.assertIn("# 追溯矩阵", md)
        self.assertIn("requirement:feat-md:main", md)
        self.assertIn("| 需求 | 验收 | 已测 | 缺口 |", md)
        drill = self.cli("trace", "--feature", "feat-md", "--requirement", "requirement:feat-md:main", expect=1)
        self.assertEqual(1, drill["requirements"])
        self.assertEqual(2, drill["summary"]["acceptance_items"])
        self.assertEqual(2, drill["summary"]["acceptance_missing"])
        self.cli("trace", "--feature", "feat-md", "--requirement", "requirement:nope:main", expect=2)

    def test_gate_fail_lists_top_gaps(self):
        self.init_repo()
        self.declare("feat-gap-lead")
        self.cli("evidence-record", "--feature", "feat-gap-lead", "--name", "e", "--command", "true", "--actor", "t")
        self.force_ready("feat-gap-lead")
        gate = self.cli("gate", "--feature", "feat-gap-lead", "--json", expect=1)
        self.assertEqual(gate["result"], "FAIL")
        self.assertEqual("requirement:feat-gap-lead:main", gate["top_gaps"][0]["id"])
        self.assertEqual(1, gate["top_gaps"][0]["missing"])
        self.assertIn("trace", gate["next"])

    def test_trace_ignores_requirement_level_verifies(self):
        """旧式“一条测试覆盖整条需求”不算验收覆盖，只能计入 direct_tests。"""
        self.init_repo()
        self.declare("feat-direct")
        self.trace_ok("feat-direct")
        conn = self.db()
        conn.execute(
            "INSERT OR IGNORE INTO nodes(id, kind, name, attrs_json) VALUES(?,?,?,?)",
            ("testcase:feat-direct:blanket", "testcase", "blanket", json.dumps({"path": "t.py"})),
        )
        conn.execute(
            "INSERT OR IGNORE INTO edges(id, src, dst, kind) VALUES(?,?,?,?)",
            ("edge:verifies:testcase:feat-direct:blanket:requirement:feat-direct:main",
             "testcase:feat-direct:blanket", "requirement:feat-direct:main", "verifies"),
        )
        conn.commit()
        conn.close()
        trace = self.cli("trace", "--feature", "feat-direct", "--json", expect=0)
        row = trace["requirements_detail"][0]
        self.assertEqual(row["acceptance"], 1)
        self.assertEqual(row["tested"], 1)
        self.assertEqual(row["direct_tests"], 1)


class ErrorStreamContractTest(unittest.TestCase):
    """错误流契约：可读 JSON 一律走 stderr + 退出 2；错误时 stdout 必须为空。

    这条以前零断言——``WxgTestCase.cli()`` 先解析 stdout、失败才退回 stderr，
    所以把错误 JSON 从 stderr 挪到 stdout 不会有任何用例变红。审计的变异测试里
    唯一漏检的就是这个变异体。
    """

    def setUp(self):
        self._tmpdir = wxg.make_temp_dir("wxg-err-")
        self.root = Path(self._tmpdir).resolve() / "state"

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(WXG), "--root", str(self.root), *args],
            capture_output=True, text=True, encoding="utf-8", env=ENV,
        )

    def assert_error(self, proc: subprocess.CompletedProcess[str], needle: str) -> None:
        self.assertEqual(2, proc.returncode, f"stderr={proc.stderr}")
        self.assertEqual("", proc.stdout.strip(), "错误时 stdout 必须为空")
        self.assertNotIn("Traceback", proc.stderr)
        payload = json.loads(proc.stderr.strip())
        self.assertIn("error", payload)
        self.assertIn(needle, payload["error"])

    def test_uninitialized_state_db(self):
        self.assert_error(self.run_cli("repo-list"), "未初始化")

    def test_unknown_feature(self):
        self.run_cli("init")
        self.assert_error(self.run_cli("feature-status", "--id", "nope"), "nope")

    def test_unknown_work(self):
        self.run_cli("init")
        self.assert_error(self.run_cli("brief", "--work", "nope"), "nope")

    def test_missing_file_for_import(self):
        self.run_cli("init")
        self.assert_error(self.run_cli("import-file", "--file", "no-such-file.py"), "不存在")

    def test_unsupported_backend_scheme(self):
        proc = subprocess.run(
            [sys.executable, str(WXG), "--db-url", "oracle://h/db", "repo-list"],
            capture_output=True, text=True, encoding="utf-8", env=ENV,
        )
        self.assert_error(proc, "不支持的")

    def test_gate_failure_is_judgement_not_error(self):
        """gate FAIL 是判定结果（退出 1 + JSON 走 stdout），不能混进错误流。"""
        self.run_cli("init")
        self.run_cli("feature-declare", "--id", "f1", "--name", "f1",
                     "--statement", "s", "--acceptance", '["可验收"]',
                     "--constraints", '["无约束"]', "--no-coverage")
        proc = self.run_cli("gate", "--feature", "f1")
        self.assertEqual(1, proc.returncode, f"stderr={proc.stderr}")
        self.assertEqual("", proc.stderr.strip(), "gate FAIL 不应写 stderr")
        self.assertEqual("FAIL", json.loads(proc.stdout.strip())["result"])


if __name__ == "__main__":
    unittest.main()
