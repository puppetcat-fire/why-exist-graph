"""plan 命令的端到端测试：走真实 CLI、真实状态库。

夹具独立定义，**不继承** test_wxg.py 的 WxgTestCase——unittest 会把基类的
全部 ``test_*`` 方法也当成子类的方法再跑一遍，一个文件就会变成整套回归。
这里只复制 plan 需要的少量夹具。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
WXG = SKILL / "scripts" / "wxg.py"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

sys.path.insert(0, str(SKILL / "scripts"))
import wxg  # noqa: E402  (复用 make_temp_dir：Windows 受限 token 下 tempfile 的 0o700 目录不可写)

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

TABLES = ("meta", "repos", "nodes", "edges", "features", "conditions",
          "work_items", "feature_nodes", "evidence", "bites", "judge_history", "changes")


class PlanCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = wxg.make_temp_dir("wxg-plan-")
        self.base = Path(self._tmpdir).resolve()
        self.root = self.base / "state"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        (self.repo / "shop.py").write_text(SHOP_PY, encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ---------------- 夹具

    def cli(self, *args, expect=0):
        proc = subprocess.run(
            [sys.executable, str(WXG), "--root", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=ENV,
        )
        output = proc.stdout.strip()
        if expect is not None and proc.returncode != expect:
            self.fail(
                f"命令 {args} 退出码 {proc.returncode}，期望 {expect}\n"
                f"stdout={proc.stdout}\nstderr={proc.stderr}"
            )
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

    def declare(self, feature):
        return self.cli(
            "feature-declare",
            "--id", feature,
            "--name", f"演示 {feature}",
            "--statement", "创建订单。",
            "--acceptance", json.dumps(["返回成功"], ensure_ascii=False),
            "--constraints", json.dumps(["不改产品代码"], ensure_ascii=False),
            "--no-coverage",
        )

    def open_targets(self, feature, kind, patterns):
        return self.cli(
            "work-open", "--feature", feature, "--kind", kind,
            "--target-ids", json.dumps(patterns, ensure_ascii=False),
        )

    def claim(self, role):
        return self.cli("work-claim", "--role", role, "--actor", f"agent-{role}")

    def finish(self, token):
        return self.cli("work-finish", "--token", token)

    def upsert(self, token, payload):
        return self.cli(
            "upsert-node", "--token", token,
            "--data", json.dumps(payload, ensure_ascii=False),
        )

    def edge(self, token, src, dst, kind):
        return self.cli(
            "upsert-edge", "--token", token,
            "--data", json.dumps({"src": src, "dst": dst, "kind": kind}, ensure_ascii=False),
        )

    def db(self):
        return sqlite3.connect(self.root / "graph.sqlite")

    def db_snapshot(self):
        conn = self.db()
        try:
            return {
                table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()]
                for table in TABLES
            }
        finally:
            conn.close()

    def import_scan(self, feature):
        prepared = self.cli("import-file", "--file", str(self.repo / "shop.py"), "--feature", feature, "--prepare")
        self.assertGreater(prepared["nodes"], 0)
        scan = self.claim("scan")
        written = self.cli("import-file", "--file", str(self.repo / "shop.py"), "--token", scan["claim_token"])
        self.assertGreater(written["nodes_inserted"], 0)
        return scan, written

    # ---------------- 用例

    def test_plan_uses_design_layer_and_reports_layers(self):
        self.init_repo()
        self.declare("feat-plan")
        self.open_targets("feat-plan", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        for node_id, name in (
            ("component:demo:a", "A"),
            ("component:demo:b", "B"),
            ("component:demo:c", "C"),
        ):
            self.upsert(token, {"id": node_id, "kind": "component", "name": name, "attrs": {"duty": name}})
        self.edge(token, "component:demo:a", "component:demo:c", "depends")
        self.edge(token, "component:demo:b", "component:demo:c", "depends")
        self.finish(token)

        plan = self.cli("plan", "--feature", "feat-plan")

        self.assertEqual("design", plan["level"])
        self.assertTrue(plan["acyclic"])
        # 设计层只保留 component/port/pattern；requirement 不参与并行规划
        self.assertEqual(3, plan["node_count"])
        self.assertEqual(2, plan["edge_count"])
        self.assertEqual(
            [
                ["component:demo:a", "component:demo:b"],
                ["component:demo:c"],
            ],
            plan["layers"],
        )
        # a、b 两两不可比 -> 理论并行上限 2
        self.assertEqual(2, plan["max_antichain"])
        self.assertEqual(2, plan["parallelism"])

    def test_plan_is_read_only_and_deterministic(self):
        self.init_repo()
        self.declare("feat-plan-ro")
        self.open_targets("feat-plan-ro", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:x", "kind": "component", "name": "X", "attrs": {"duty": "x"}})
        self.upsert(token, {"id": "component:demo:y", "kind": "component", "name": "Y", "attrs": {"duty": "y"}})
        self.edge(token, "component:demo:x", "component:demo:y", "depends")
        self.finish(token)

        before = self.db_snapshot()
        first = self.cli("plan", "--feature", "feat-plan-ro")
        second = self.cli("plan", "--feature", "feat-plan-ro")
        self.assertEqual(first, second)
        self.assertEqual(before, self.db_snapshot())

    def test_plan_falls_back_to_code_layer_without_depends(self):
        self.init_repo()
        self.declare("feat-plan-code")
        self.import_scan("feat-plan-code")

        plan = self.cli("plan", "--feature", "feat-plan-code")

        self.assertEqual("code", plan["level"])
        self.assertGreaterEqual(plan["node_count"], 1)
        self.assertTrue(plan["acyclic"])

    def test_plan_reports_cycle(self):
        self.init_repo()
        self.declare("feat-plan-cycle")
        self.open_targets("feat-plan-cycle", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:m", "kind": "component", "name": "M", "attrs": {"duty": "m"}})
        self.upsert(token, {"id": "component:demo:n", "kind": "component", "name": "N", "attrs": {"duty": "n"}})
        self.edge(token, "component:demo:m", "component:demo:n", "depends")
        self.edge(token, "component:demo:n", "component:demo:m", "depends")
        self.finish(token)

        plan = self.cli("plan", "--feature", "feat-plan-cycle")

        self.assertFalse(plan["acyclic"])
        self.assertIsNone(plan["layers"])
        self.assertEqual([["component:demo:m", "component:demo:n"]], plan["cyclic_components"])

    def test_brief_returns_blind_task_spec(self):
        self.init_repo()
        self.declare("feat-brief")
        self.open_targets("feat-brief", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.upsert(token, {"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.finish(token)

        brief = self.cli("brief", "--work", claim["work_item_id"])

        self.assertTrue(brief["blind"])
        self.assertEqual("feat-brief", brief["feature"])
        # work-seed 默认把 requirement 节点放进 target_ids，work-open 再并进 component:*
        self.assertEqual(
            ["component:demo:a", "component:demo:b", "requirement:feat-brief:main"],
            brief["write_boundary"],
        )
        # b 在边界内，不构成外部输入
        self.assertEqual([], brief["inputs"])
        self.assertIn("component", brief["produces"])
        self.assertNotIn("feat-other", json.dumps(brief, ensure_ascii=False))

    def test_brief_rejects_unknown_work(self):
        self.init_repo()
        result = self.cli("brief", "--work", "work:missing", expect=2)
        self.assertIn("error", result)

    def test_plan_rejects_unknown_feature(self):
        self.init_repo()
        result = self.cli("plan", "--feature", "feat-missing", expect=2)
        self.assertIn("error", result)


    def test_blind_check_accepts_clean_output(self):
        self.init_repo()
        self.declare("feat-blind")
        self.open_targets("feat-blind", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.finish(token)

        output = self.base / "output.json"
        output.write_text(
            json.dumps(
                {
                    "nodes": [{"id": "component:demo:new", "kind": "component"}],
                    "edges": [
                        {"src": "component:demo:new", "dst": "component:demo:a", "kind": "depends"}
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        check = self.cli("blind-check", "--work", claim["work_item_id"], "--result", str(output))
        self.assertEqual("PASS", check["verdict"])
        self.assertEqual(1.0, check["locality"])
        self.assertTrue(check["boundary"]["ok"])

    def test_blind_check_flags_out_of_bounds_and_undeclared(self):
        self.init_repo()
        self.declare("feat-blind-bad")
        self.open_targets("feat-blind-bad", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.finish(token)

        output = self.base / "bad-output.json"
        output.write_text(
            json.dumps(
                {
                    "nodes": [{"id": "component:other:x", "kind": "component"}],
                    "edges": [
                        {"src": "component:other:x", "dst": "component:other:q", "kind": "depends"}
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        check = self.cli("blind-check", "--work", claim["work_item_id"], "--result", str(output))
        self.assertEqual("FAIL", check["verdict"])
        self.assertFalse(check["boundary"]["ok"])
        self.assertFalse(check["dependencies"]["ok"])
        self.assertLess(check["locality"], 1.0)

    def test_blind_check_rejects_missing_result_file(self):
        self.init_repo()
        self.declare("feat-blind-missing")
        self.open_targets("feat-blind-missing", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        result = self.cli(
            "blind-check",
            "--work", claim["work_item_id"],
            "--result", str(self.base / "nope.json"),
            expect=2,
        )
        self.assertIn("error", result)


    def test_up_bootstraps_workspace_and_is_idempotent(self):
        first = self.cli("up", "--feature", "demo-up")
        self.assertTrue(first["feature"]["created"])
        self.assertIn(first["gate_result"], ("PASS", "FAIL"))
        self.assertTrue((self.root / "graph.sqlite").is_file())
        # scan 工单由 import-file --prepare 创建，所以 next 的第一步必须是 prepare；
        # 直接建议 work-claim 会让人领不到单。
        self.assertIn("import-file", first["next"][0])
        self.assertIn("--prepare", first["next"][0])
        self.assertFalse(any("work-claim" in step for step in first["next"][:1]))

        second = self.cli("up", "--feature", "demo-up")
        self.assertFalse(second["feature"]["created"])
        self.assertEqual(first["gate_result"], second["gate_result"])
        self.assertEqual(first["repo"], second["repo"])

    def test_up_accepts_existing_repo_path(self):
        result = self.cli(
            "up", "--feature", "demo-up-path", "--repo", "demo2", "--path", str(self.repo)
        )
        self.assertEqual(str(self.repo.resolve()), result["repo"]["path"])


    def test_impact_reports_closure_and_uncovered(self):
        self.init_repo()
        self.declare("feat-imp")
        self.open_targets("feat-imp", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.upsert(token, {"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.finish(token)

        result = self.cli(
            "impact", "--feature", "feat-imp",
            "--changed", json.dumps(["component:demo:b"]),
        )
        self.assertIn("component:demo:a", result["affected"])
        self.assertIn("component:demo:b", result["affected"])
        # a / b 与 requirement 之间没有结构边 -> 影响域不闭环
        self.assertFalse(result["closed"])
        self.assertTrue(result["uncovered"])

    def test_impact_rejects_non_array_changed(self):
        self.init_repo()
        self.declare("feat-imp-bad")
        result = self.cli("impact", "--feature", "feat-imp-bad", "--changed", "\"nope\"", expect=2)
        self.assertIn("error", result)

    def test_conflicts_detects_overlapping_boundaries(self):
        self.init_repo()
        self.declare("feat-c1")
        self.declare("feat-c2")
        self.open_targets("feat-c1", "model-architecture", ["component:demo:*"])
        self.open_targets("feat-c2", "model-architecture", ["component:demo:a"])

        result = self.cli("conflicts")

        self.assertFalse(result["coexist_ok"])
        self.assertEqual(1, len(result["conflicts"]))
        self.assertEqual("feat-c1", result["conflicts"][0]["a"])
        self.assertEqual("feat-c2", result["conflicts"][0]["b"])

    def test_conflicts_clean_when_boundaries_disjoint(self):
        self.init_repo()
        self.declare("feat-d1")
        self.declare("feat-d2")
        self.open_targets("feat-d1", "model-architecture", ["component:one:*"])
        self.open_targets("feat-d2", "model-architecture", ["component:two:*"])

        result = self.cli("conflicts")

        self.assertTrue(result["coexist_ok"])
        self.assertEqual([], result["conflicts"])


    def test_patch_and_apply_merge_disjoint_outputs(self):
        self.init_repo()
        self.declare("feat-reduce")
        self.open_targets("feat-reduce", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})

        out1 = self.base / "out1.json"
        out1.write_text(
            json.dumps(
                {
                    "nodes": [{"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}}],
                    "edges": [{"src": "component:demo:b", "dst": "component:demo:a", "kind": "depends"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        patch1 = self.base / "p1.json"
        self.cli("patch", "--work", claim["work_item_id"], "--result", str(out1), "--out", str(patch1))

        out2 = self.base / "out2.json"
        out2.write_text(
            json.dumps(
                {"nodes": [{"id": "component:demo:c", "kind": "component", "name": "C", "attrs": {"duty": "c"}}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        patch2 = self.base / "p2.json"
        self.cli("patch", "--work", claim["work_item_id"], "--result", str(out2), "--out", str(patch2))

        # 3.7.0：apply 写库要 token（落在 target_ids 内）；无 token 只能 --dry-run
        rejected = self.cli("apply", "--patches", f"{patch1},{patch2}", expect=2)
        self.assertIn("--token", rejected["error"])
        merged = self.cli("apply", "--patches", f"{patch1},{patch2}", "--token", token)
        self.finish(token)

        self.assertTrue(merged["ok"])
        self.assertTrue(merged["applied"])
        self.assertEqual(2, merged["written_nodes"])
        conn = self.db()
        try:
            self.assertIsNotNone(conn.execute("SELECT id FROM nodes WHERE id='component:demo:b'").fetchone())
        finally:
            conn.close()

    def test_apply_rejects_nodes_outside_target_boundary(self):
        """3.7.0：apply 落库也要落在工单 target_ids 内，和 upsert-node 同一条边界。"""
        self.init_repo()
        self.declare("feat-apply-bound")
        self.open_targets("feat-apply-bound", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        out = self.base / "outside.json"
        out.write_text(
            json.dumps({"nodes": [{"id": "classifier:demo:outside.X", "kind": "classifier", "name": "X"}]},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        patch_file = self.base / "p-out.json"
        self.cli("patch", "--work", claim["work_item_id"], "--result", str(out), "--out", str(patch_file))
        rejected = self.cli("apply", "--patches", str(patch_file), "--token", claim["claim_token"], expect=2)
        self.assertIn("target_ids", rejected["error"])

    def test_apply_role_must_be_allowed(self):
        self.init_repo()
        self.declare("feat-apply-role")
        conn = self.db()
        try:
            conn.execute(
                "INSERT INTO work_items(id, feature_id, generation, kind, role, target_ids, status, "
                "depends_on, claimed_by, claim_token, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                ("work:feat-apply-role:g1:scan", "feat-apply-role", 1, "scan", "scan",
                 '["*"]', "claimed", "[]", "tester", "tok-scan", "2026-01-01T00:00:00Z"),
            )
            conn.commit()
        finally:
            conn.close()
        out = self.base / "role.json"
        out.write_text(json.dumps({"nodes": []}, ensure_ascii=False), encoding="utf-8")
        patch_file = self.base / "p-role.json"
        self.cli("patch", "--work", "work:feat-apply-role:g1:scan", "--result", str(out), "--out", str(patch_file))
        rejected = self.cli("apply", "--patches", str(patch_file), "--token", "tok-scan", expect=2)
        self.assertIn("不能执行 apply", rejected["error"])

    def test_apply_conflict_reports_and_writes_nothing(self):
        self.init_repo()
        self.declare("feat-conflict")
        out1 = self.base / "c1.json"
        out1.write_text(
            json.dumps(
                {"nodes": [{"id": "component:demo:x", "kind": "component", "name": "X", "attrs": {"duty": "one"}}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        out2 = self.base / "c2.json"
        out2.write_text(
            json.dumps(
                {"nodes": [{"id": "component:demo:x", "kind": "component", "name": "X", "attrs": {"duty": "two"}}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        patch1 = self.base / "cp1.json"
        patch2 = self.base / "cp2.json"
        self.cli("patch", "--work", "w1", "--result", str(out1), "--out", str(patch1))
        self.cli("patch", "--work", "w2", "--result", str(out2), "--out", str(patch2))

        merged = self.cli("apply", "--patches", f"{patch1},{patch2}", expect=1)

        self.assertFalse(merged["ok"])
        self.assertFalse(merged["applied"])
        conn = self.db()
        try:
            self.assertIsNone(conn.execute("SELECT id FROM nodes WHERE id='component:demo:x'").fetchone())
        finally:
            conn.close()

    def test_apply_dry_run_writes_nothing(self):
        self.init_repo()
        self.declare("feat-dry")
        output = self.base / "dry.json"
        output.write_text(
            json.dumps(
                {"nodes": [{"id": "component:demo:dry", "kind": "component", "name": "D", "attrs": {"duty": "d"}}]},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        patch_file = self.base / "dry-p.json"
        self.cli("patch", "--work", "w1", "--result", str(output), "--out", str(patch_file))

        merged = self.cli("apply", "--patches", str(patch_file), "--dry-run")

        self.assertTrue(merged["ok"])
        self.assertFalse(merged["applied"])
        conn = self.db()
        try:
            self.assertIsNone(conn.execute("SELECT id FROM nodes WHERE id='component:demo:dry'").fetchone())
        finally:
            conn.close()


    def test_up_minimal_template_skips_demo_repo(self):
        result = self.cli("up", "--feature", "demo-min", "--template", "minimal")
        self.assertEqual("minimal", result["template"])
        self.assertIsNone(result["repo"])
        self.assertTrue(result["feature"]["created"])


    def test_plan_excludes_unmapped_by_default(self):
        self.init_repo()
        self.declare("feat-noise")
        self.import_scan("feat-noise")

        plan = self.cli("plan", "--feature", "feat-noise")
        full = self.cli("plan", "--feature", "feat-noise", "--include-unmapped")

        self.assertGreater(plan["excluded_unmapped"], 0)
        self.assertEqual(0, full["excluded_unmapped"])
        self.assertGreater(full["node_count"], plan["node_count"])

    def test_unmapped_calls_are_aggregated_by_name(self):
        self.init_repo()
        self.declare("feat-agg")
        (self.repo / "agg.py").write_text(
            "def first(xs):\n    return len(xs)\n\n\ndef second(xs):\n    return len(xs)\n",
            encoding="utf-8",
        )
        prepared = self.cli(
            "import-file", "--file", str(self.repo / "agg.py"),
            "--feature", "feat-agg", "--prepare",
        )
        self.assertGreater(prepared["nodes"], 0)
        scan = self.claim("scan")
        self.cli(
            "import-file", "--file", str(self.repo / "agg.py"),
            "--token", scan["claim_token"],
        )

        conn = self.db()
        try:
            rows = conn.execute(
                "SELECT id FROM nodes WHERE repo='demo' AND path='agg.py' AND unmapped=1"
            ).fetchall()
        finally:
            conn.close()
        # 两个 len() 调用点聚合为一个 unmapped 节点
        self.assertEqual(1, len(rows))
        self.assertNotIn("@", rows[0][0])


    def test_import_repo_scans_all_python_files(self):
        self.init_repo()
        self.declare("feat-repo")
        (self.repo / "second.py").write_text(
            "def helper():\n    return 1\n", encoding="utf-8"
        )

        prepared = self.cli(
            "import-repo", "--repo", "demo", "--feature", "feat-repo", "--prepare"
        )
        self.assertEqual(2, prepared["files"])

        scan = self.claim("scan")
        written = self.cli(
            "import-repo", "--repo", "demo", "--token", scan["claim_token"]
        )
        self.assertEqual(2, written["files"])
        self.assertGreater(written["nodes_inserted"], 0)


    def test_derive_dry_run_reports_components(self):
        self.init_repo()
        self.declare("feat-derive")
        self.import_scan("feat-derive")

        result = self.cli("derive", "--repo", "demo", "--feature", "feat-derive")

        self.assertEqual("dry-run", result["mode"])
        self.assertGreater(len(result["components"]), 0)
        self.assertEqual("package", result["strategy"])
        # demo 仓是扁平结构（单个文件在根），分组只能得到 1 个组件 → 应带提示
        if len(result["components"]) == 1:
            self.assertIn("hint", result)
            self.assertIn("目录层级不足", result["hint"])

    def test_derive_apply_writes_derived_components(self):
        self.init_repo()
        self.declare("feat-derive-apply")
        self.import_scan("feat-derive-apply")
        self.open_targets(
            "feat-derive-apply", "model-architecture", ["component:demo:*"]
        )
        claim = self.claim("model-architecture")

        result = self.cli(
            "derive", "--repo", "demo", "--feature", "feat-derive-apply",
            "--apply", "--token", claim["claim_token"],
        )

        self.assertEqual("apply", result["mode"])
        self.assertGreater(result["components"], 0)
        conn = self.db()
        try:
            row = conn.execute(
                "SELECT origin FROM nodes WHERE id LIKE 'component:demo:%'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual("derived", row[0])


    def test_promote_rejects_non_derived_node(self):
        self.init_repo()
        self.declare("feat-promote")
        self.import_scan("feat-promote")
        self.open_targets("feat-promote", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(
            token,
            {"id": "component:demo:manual", "kind": "component", "name": "M", "attrs": {"duty": "m"}},
        )

        result = self.cli(
            "promote", "--feature", "feat-promote",
            "--node", "component:demo:manual", "--token", token,
            expect=2,
        )

        self.assertIn("error", result)

    def test_promote_marks_derived_component_declared(self):
        self.init_repo()
        self.declare("feat-promote2")
        self.import_scan("feat-promote2")
        self.open_targets("feat-promote2", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.cli(
            "derive", "--repo", "demo", "--feature", "feat-promote2",
            "--apply", "--token", token,
        )
        conn = self.db()
        try:
            row = conn.execute("SELECT id FROM nodes WHERE origin='derived' LIMIT 1").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        node_id = row[0]

        result = self.cli(
            "promote", "--feature", "feat-promote2", "--node", node_id,
            "--token", token, "--actor", "architect-1",
        )

        self.assertEqual(node_id, result["promoted"])
        conn = self.db()
        try:
            origin = conn.execute("SELECT origin FROM nodes WHERE id=?", (node_id,)).fetchone()[0]
            attrs = conn.execute("SELECT attrs_json FROM nodes WHERE id=?", (node_id,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual("declared", origin)
        self.assertIn("architect-1", attrs)


    def test_cycles_reports_ring_edges(self):
        self.init_repo()
        self.declare("feat-cyc")
        self.open_targets("feat-cyc", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.upsert(token, {"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.edge(token, "component:demo:b", "component:demo:a", "depends")
        self.finish(token)

        result = self.cli("cycles", "--feature", "feat-cyc")

        self.assertEqual(1, result["cycle_count"])
        cycle = result["cycles"][0]
        self.assertEqual(["component:demo:a", "component:demo:b"], cycle["members"])
        self.assertEqual(2, len(cycle["edges"]))

    def test_cycles_without_simulates_removal(self):
        self.init_repo()
        self.declare("feat-cyc2")
        self.open_targets("feat-cyc2", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.upsert(token, {"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.edge(token, "component:demo:b", "component:demo:a", "depends")
        self.finish(token)

        result = self.cli(
            "cycles", "--feature", "feat-cyc2",
            "--without", "component:demo:a->component:demo:b",
        )

        self.assertEqual(0, result["cycle_count"])
        self.assertEqual([["component:demo:a", "component:demo:b"]], result["without"])

    def test_feature_status_trims_work_item_targets(self):
        self.init_repo()
        self.declare("feat-trim")
        status = self.cli("feature-status", "--id", "feat-trim")
        self.assertTrue(status["work_items"])
        for item in status["work_items"]:
            # 概览视图不返回完整 target_ids（大仓 scan 工单可达上千条），只给计数与前几条
            self.assertNotIn("target_ids", item)
            self.assertIn("target_count", item)
            self.assertLessEqual(len(item["target_sample"]), 5)
            self.assertIsInstance(item["depends_on"], list)

    def test_impact_accepts_comma_separated_changed(self):
        self.init_repo()
        self.declare("feat-imp")
        result = self.cli("impact", "--feature", "feat-imp", "--changed", "a:b,c:d")
        self.assertEqual(["a:b", "c:d"], result["changed"])

    def test_impact_rejects_empty_changed(self):
        self.init_repo()
        self.declare("feat-imp2")
        self.cli("impact", "--feature", "feat-imp2", "--changed", "", expect=2)

    def test_gate_checks_report_each_item(self):
        self.init_repo()
        self.declare("feat-checks")
        result = self.cli("gate", "--feature", "feat-checks", "--json", expect=1)
        self.assertEqual("FAIL", result["result"])
        by_name = {item["name"]: item["ok"] for item in result["checks"]}
        self.assertEqual(
            [
                "bites",
                "pattern",
                "drift",
                "construction",
                "stale",
                "conformance",
                "conditions",
                "evidence",
                "traceability",
                "coverage",
            ],
            [item["name"] for item in result["checks"]],
        )
        self.assertFalse(by_name["conditions"])
        self.assertTrue(by_name["bites"])

    def test_plan_code_level_hints_when_scope_has_no_code_nodes(self):
        self.init_repo()
        self.declare("feat-hint")
        result = self.cli("plan", "--feature", "feat-hint", "--level", "code")
        self.assertIn("hint", result)
        self.assertIn("代码层节点", result["hint"])

    def test_feature_status_reports_current_phase(self):
        self.init_repo()
        self.declare("feat-phase")
        status = self.cli("feature-status", "--id", "feat-phase")
        self.assertEqual("ArchitectureReconciled", status["phase"])

    def test_cycles_advise_ranks_break_edges(self):
        self.init_repo()
        self.declare("feat-adv")
        self.open_targets("feat-adv", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.upsert(token, {"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.edge(token, "component:demo:b", "component:demo:a", "depends")
        self.finish(token)

        result = self.cli("cycles", "--feature", "feat-adv", "--advise")

        self.assertEqual(2, len(result["advice"]))
        for item in result["advice"]:
            self.assertTrue(item["in_break_set"])
            # 断任意一条都会让源点失去另一节点
            self.assertEqual(1, item["lost_count"])
            self.assertEqual("acceptable", item["verdict"])

    def test_cycles_break_set_finds_minimal_edges(self):
        self.init_repo()
        self.declare("feat-brk")
        self.open_targets("feat-brk", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.upsert(token, {"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.edge(token, "component:demo:b", "component:demo:a", "depends")
        self.finish(token)

        result = self.cli("cycles", "--feature", "feat-brk", "--break-set")

        self.assertEqual(1, result["break_sets"][0]["size"])
        # 两条边各能单独破环
        self.assertEqual(2, len(result["break_sets"]))

    def test_cycles_is_empty_without_ring(self):
        self.init_repo()
        self.declare("feat-acyc")
        self.open_targets("feat-acyc", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        self.upsert(token, {"id": "component:demo:a", "kind": "component", "name": "A", "attrs": {"duty": "a"}})
        self.upsert(token, {"id": "component:demo:b", "kind": "component", "name": "B", "attrs": {"duty": "b"}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.finish(token)

        result = self.cli("cycles", "--feature", "feat-acyc")

        self.assertEqual(0, result["cycle_count"])
        self.assertEqual([], result["cycles"])


    def test_impact_remove_edges_reports_lost_reachability(self):
        self.init_repo()
        self.declare("feat-rm")
        self.open_targets("feat-rm", "model-architecture", ["component:demo:*"])
        claim = self.claim("model-architecture")
        token = claim["claim_token"]
        for nid in ("component:demo:a", "component:demo:b", "component:demo:c"):
            self.upsert(token, {"id": nid, "kind": "component", "name": nid[-1], "attrs": {"duty": nid[-1]}})
        self.edge(token, "component:demo:a", "component:demo:b", "depends")
        self.edge(token, "component:demo:b", "component:demo:c", "depends")
        self.finish(token)

        result = self.cli(
            "impact", "--feature", "feat-rm",
            "--remove-edges", "component:demo:a->component:demo:b",
        )

        self.assertEqual("remove-edges", result["mode"])
        row = result["removed"][0]
        # a 原本能到 b、c；断掉 a->b 后都到不了
        self.assertEqual(
            ["component:demo:b", "component:demo:c"], row["lost_reachable"]
        )
        self.assertEqual(3, len(result["affected"]))


if __name__ == "__main__":
    unittest.main()
