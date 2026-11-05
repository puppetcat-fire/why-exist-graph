"""Engine 库 API 的测试：走真实状态库，但通过 Python 接口而不是 subprocess。"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
WXG = SKILL / "scripts" / "wxg.py"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

sys.path.insert(0, str(SKILL / "scripts"))
from whyexist import Engine  # noqa: E402
from whyexist.errors import Reject  # noqa: E402
from whyexist.temp import make_temp_dir  # noqa: E402


class EngineCase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = make_temp_dir("wxg-engine-")
        self.base = Path(self._tmpdir).resolve()
        self.root = self.base / "state"
        self.repo = self.base / "repo"
        self.repo.mkdir()
        (self.repo / "demo.py").write_text("def ping():\n    return 1\n", encoding="utf-8")

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def cli(self, *args):
        proc = subprocess.run(
            [sys.executable, str(WXG), "--root", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=ENV,
        )
        if proc.returncode != 0:
            self.fail(f"{args} 失败: {proc.stderr}")
        return json.loads(proc.stdout) if proc.stdout.strip() else {}

    def seed(self) -> str:
        """建一个带 depends 边的最小 feature，返回 model-architecture 工单 id。"""
        self.cli("init")
        self.cli("repo-add", "--id", "demo", "--path", str(self.repo))
        self.cli(
            "feature-declare",
            "--id", "feat-e",
            "--name", "E",
            "--statement", "测试。",
            "--acceptance", json.dumps(["ok"]),
            "--constraints", json.dumps(["no"]),
            "--no-coverage",
        )
        self.cli(
            "work-open", "--feature", "feat-e", "--kind", "model-architecture",
            "--target-ids", json.dumps(["component:demo:*"]),
        )
        claim = self.cli("work-claim", "--role", "model-architecture", "--actor", "a1")
        token = claim["claim_token"]
        for node_id, name in (("component:demo:a", "A"), ("component:demo:b", "B")):
            self.cli(
                "upsert-node", "--token", token, "--data",
                json.dumps(
                    {"id": node_id, "kind": "component", "name": name, "attrs": {"duty": name}}
                ),
            )
        self.cli(
            "upsert-edge", "--token", token, "--data",
            json.dumps({"src": "component:demo:a", "dst": "component:demo:b", "kind": "depends"}),
        )
        self.cli("work-finish", "--token", token)
        return claim["work_item_id"]

    # ---------------- 用例

    def test_plan_through_engine(self):
        self.seed()
        with Engine(self.root) as engine:
            plan = engine.plan("feat-e")
        self.assertEqual("design", plan["level"])
        self.assertEqual(1, plan["edge_count"])
        self.assertTrue(plan["acyclic"])

    def test_brief_and_blind_check_through_engine(self):
        work_id = self.seed()
        with Engine(self.root) as engine:
            brief = engine.brief(work_id)
            result = engine.blind_check(
                work_id, {"nodes": [{"id": "component:demo:c", "kind": "component"}]}
            )
        self.assertTrue(brief["blind"])
        self.assertIn("component:demo:*", brief["write_patterns"])
        self.assertEqual("PASS", result["verdict"])

    def test_blind_check_flags_violation_through_engine(self):
        work_id = self.seed()
        with Engine(self.root) as engine:
            result = engine.blind_check(
                work_id, {"nodes": [{"id": "component:other:x", "kind": "component"}]}
            )
        self.assertEqual("FAIL", result["verdict"])

    def test_gate_is_read_only(self):
        self.seed()
        with Engine(self.root) as engine:
            before = engine.gate("feat-e")
            after = engine.gate("feat-e")
        self.assertEqual(before, after)
        self.assertEqual("FAIL", before["result"])  # 条件尚未齐

    def test_unknown_feature_raises_reject(self):
        self.seed()
        with Engine(self.root) as engine:
            with self.assertRaises(Reject):
                engine.plan("nope")

    def test_impact_through_engine(self):
        self.seed()
        with Engine(self.root) as engine:
            result = engine.impact("feat-e", ["component:demo:b"])
        self.assertIn("component:demo:a", result["affected"])
        self.assertIn("component:demo:b", result["affected"])
        self.assertEqual(["component:demo:b"], result["changed"])

    def test_context_manager_closes_connection(self):
        self.seed()
        engine = Engine(self.root)
        with engine:
            engine.plan("feat-e")
        self.assertIsNone(engine._conn)


if __name__ == "__main__":
    unittest.main()
