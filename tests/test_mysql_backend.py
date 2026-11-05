"""MariaDB/MySQL 后端集成测试。

默认跳过；设置 WXG_TEST_MYSQL_URL 指向一个**可丢弃**的数据库后运行：

    WXG_TEST_MYSQL_URL=mysql://root:pass@127.0.0.1:3307/wxg_test \
      python -m unittest tests.test_mysql_backend -v

测试会在 setUpClass 清空该库的所有表（SHOW TABLES + DROP），不要指向真实数据。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
WXG = SKILL / "scripts" / "wxg.py"
sys.path.insert(0, str(SKILL / "scripts"))

import wxg  # noqa: E402
import wxg_mysql  # noqa: E402

MYSQL_URL = os.environ.get("WXG_TEST_MYSQL_URL", "").strip()


@unittest.skipUnless(MYSQL_URL, "设置 WXG_TEST_MYSQL_URL 后才跑 MySQL 后端集成测试")
class MySQLBackendTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        conn = wxg_mysql.connect(MYSQL_URL)
        try:
            rows = conn.execute("SHOW TABLES").fetchall()
            for row in rows:
                table = list(row.values())[0]
                conn.execute(f"DROP TABLE `{table}`")
            conn.commit()
        finally:
            conn.close()

    def setUp(self):
        self._tmp = wxg.make_temp_dir("wxg-mysql-it-")
        self.root = Path(self._tmp) / "state"
        self.repo = Path(self._tmp) / "repo"
        self.repo.mkdir(parents=True)
        (self.repo / "shop.py").write_text(
            "class OrderRepo:\n    def save(self, x):\n        self.conn = x\n\n\ndef create(x):\n    return x\n",
            encoding="utf-8",
        )
        self.env = dict(os.environ, PYTHONUTF8="1", WXG_DB_URL=MYSQL_URL)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def cli(self, *args, expect=0):
        proc = subprocess.run(
            [sys.executable, str(WXG), "--root", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=self.env,
        )
        output = proc.stdout.strip()
        if expect is not None and proc.returncode != expect:
            self.fail(f"{args} 退出码 {proc.returncode}，期望 {expect}\nstdout={proc.stdout}\nstderr={proc.stderr}")
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

    def declare(self, feature, repo_id="demo"):
        self.cli("feature-declare", "--id", feature, "--name", feature, "--statement", "s",
                 "--acceptance", "[]", "--constraints", "[]", "--no-coverage")

    def test_init_and_scan_flow_on_mysql(self):
        init = self.cli("init")
        self.assertEqual(init["backend"], "mysql")
        self.assertEqual(init["schema_version"], 9)
        feature = f"feat-{uuid.uuid4().hex[:8]}"
        self.cli("repo-add", "--id", f"repo-{feature}", "--path", str(self.repo))
        self.declare(feature, repo_id=f"repo-{feature}")
        prepared = self.cli("import-file", "--file", str(self.repo / "shop.py"),
                            "--feature", feature, "--prepare")
        self.assertGreater(prepared["nodes"], 0)
        scan = self.cli("work-claim", "--role", "scan", "--actor", "scanner")
        written = self.cli("import-file", "--file", str(self.repo / "shop.py"),
                           "--token", scan["claim_token"])
        self.assertGreater(written["nodes_inserted"], 0)
        self.cli("work-finish", "--token", scan["claim_token"])
        self.cli("work-judge", "--id", scan["work_item_id"], "--verdict", "passed",
                 "--role", "audit", "--actor", "auditor")
        gate = self.cli("gate", "--feature", feature, "--json", expect=1)
        self.assertEqual(gate["result"], "FAIL")
        self.assertIn("条件未齐", gate["reason"])
        doctor = self.cli("doctor")
        self.assertTrue(doctor["ok"], doctor)

    def test_parallel_claims_only_one_wins(self):
        self.cli("init")
        feature = f"feat-{uuid.uuid4().hex[:8]}"
        repo_id = f"repo-{feature}"
        self.cli("repo-add", "--id", repo_id, "--path", str(self.repo))
        self.declare(feature, repo_id=repo_id)
        self.cli("import-file", "--file", str(self.repo / "shop.py"),
                 "--feature", feature, "--prepare")
        command = [sys.executable, str(WXG), "--root", str(self.root),
                   "work-claim", "--role", "scan", "--actor", "racer"]
        first = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, encoding="utf-8", env=self.env)
        second = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, encoding="utf-8", env=self.env)
        first_out = first.communicate(timeout=60)
        second_out = second.communicate(timeout=60)
        codes = [first.returncode, second.returncode]
        self.assertEqual(sorted(codes), [0, 2], (first_out, second_out))

    def test_serve_once_on_mysql(self):
        self.cli("init")
        feature = f"feat-{uuid.uuid4().hex[:8]}"
        repo_id = f"repo-{feature}"
        self.cli("repo-add", "--id", repo_id, "--path", str(self.repo))
        self.declare(feature, repo_id=repo_id)
        summary = self.cli("serve", "--once", "--feature", feature)
        self.assertEqual(summary["pass"], 1)
        self.assertEqual(summary["features"][0]["feature"], feature)


if __name__ == "__main__":
    unittest.main()
