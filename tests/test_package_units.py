"""包内纯函数层的直接单测：不经过 CLI subprocess。

覆盖 jsonio / work / db 方言转换 / graph 校验 / evidence。
这些函数是命令层的地基，之前只被 CLI 测试间接覆盖。
"""

from __future__ import annotations

import hashlib
import sqlite3
import sys
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL / "scripts"))

from whyexist import db, evidence, gates, graph, jsonio, work  # noqa: E402
from whyexist import commands_repo  # noqa: E402
from whyexist import workflow as wf  # noqa: E402
from whyexist.contract import C  # noqa: E402
from whyexist.errors import Reject  # noqa: E402
from whyexist.temp import temp_dir  # noqa: E402


class JsonIoTest(unittest.TestCase):
    def test_dumps_is_sorted(self):
        self.assertEqual('{"a": 1, "b": 2}', jsonio.dumps({"b": 2, "a": 1}))

    def test_loads_empty_returns_default(self):
        self.assertEqual([], jsonio.loads("", []))
        self.assertEqual({}, jsonio.loads(None, {}))

    def test_loads_passes_through_containers(self):
        self.assertEqual({"a": 1}, jsonio.loads({"a": 1}, None))

    def test_loads_bad_json_raises_reject(self):
        with self.assertRaises(Reject):
            jsonio.loads("{bad", None)

    def test_load_json_arg_from_file_with_bom(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "a.json"
            path.write_text('{"x": 1}', encoding="utf-8-sig")
            self.assertEqual({"x": 1}, jsonio.load_json_arg("@" + str(path)))

    def test_load_json_arg_missing_file_raises(self):
        with self.assertRaises(Reject):
            jsonio.load_json_arg("@/nonexistent/nope.json")

    def test_load_json_arg_error_mentions_expected_shape(self):
        with self.assertRaises(Reject) as ctx:
            jsonio.load_json_arg("component:x:y")
        self.assertIn("期望数组/对象字面量", str(ctx.exception))

    def test_load_json_arg_bad_file_names_the_file(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "bad.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(Reject) as ctx:
                jsonio.load_json_arg("@" + str(path))
            self.assertIn("bad.json", str(ctx.exception))

    def test_load_id_list_accepts_comma_separated(self):
        self.assertEqual(["a", "b"], jsonio.load_id_list("a, b"))
        self.assertEqual(["a"], jsonio.load_id_list('["a"]'))
        self.assertEqual([], jsonio.load_id_list("   "))
        with self.assertRaises(Reject):
            jsonio.load_id_list('{"a": 1}')

    def test_load_id_list_rejects_json_string(self):
        with self.assertRaises(Reject):
            jsonio.load_id_list('"nope"')

    def test_new_token_is_32_hex(self):
        token = jsonio.new_token()
        self.assertEqual(32, len(token))
        self.assertTrue(all(c in "0123456789abcdef" for c in token))

    def test_utc_now_ends_with_z(self):
        self.assertTrue(jsonio.utc_now().endswith("Z"))


class WorkTargetTest(unittest.TestCase):
    def test_work_id_format(self):
        self.assertEqual(
            "work:f:g1:model-architecture",
            work.work_id("f", 1, "model-architecture"),
        )

    def test_target_match_exact_and_wildcard(self):
        self.assertTrue(work.target_match("a:b", "a:b"))
        self.assertTrue(work.target_match("a:*", "a:b"))
        self.assertFalse(work.target_match("a:*", "b:c"))

    def test_target_match_rejects_non_string(self):
        self.assertFalse(work.target_match("a:*", None))

    def test_require_targets_accepts_exact_and_prefix(self):
        item = {"target_ids": jsonio.dumps(["a:b", "c:*"])}
        work.require_targets(item, ["a:b", "c:d"])

    def test_require_targets_rejects_outside(self):
        item = {"target_ids": jsonio.dumps(["a:b"])}
        with self.assertRaises(Reject):
            work.require_targets(item, ["a:z"])

    def test_require_role_rejects_unlisted_command(self):
        item = {"role": "scan"}
        with self.assertRaises(Reject):
            work.require_role(item, "work-judge")

    def test_require_role_allows_its_own_command(self):
        item = {"role": "scan"}
        work.require_role(item, C.ROLES["scan"][0])


class DbTranslateTest(unittest.TestCase):
    def test_mysql_translate_insert_or_ignore(self):
        out = db._mysql_translate("INSERT OR IGNORE INTO t (a) VALUES (?)")
        self.assertIn("INSERT IGNORE INTO", out)
        self.assertNotIn("OR IGNORE", out)

    def test_mysql_translate_conflict_do_nothing(self):
        out = db._mysql_translate("INSERT OR IGNORE INTO t (a) VALUES (?)")
        self.assertNotIn("ON CONFLICT", out)

    def test_mysql_translate_excluded_to_values(self):
        out = db._mysql_translate(
            "ON CONFLICT(id) DO UPDATE SET value=excluded.value"
        )
        self.assertIn("ON DUPLICATE KEY UPDATE", out)
        self.assertIn("VALUES(value)", out)

    def test_pg_translate_on_conflict_do_nothing(self):
        out = db._pg_translate("INSERT OR IGNORE INTO t (a) VALUES (?)")
        self.assertIn("ON CONFLICT DO NOTHING", out)
        self.assertIn("%s", out)

    def test_named_params_replaces_in_order(self):
        sql, params = db._named_params(
            "SELECT * FROM t WHERE a=:a AND b=:b", {"a": 1, "b": 2}
        )
        self.assertEqual("SELECT * FROM t WHERE a=? AND b=?", sql)
        self.assertEqual((1, 2), params)

    def test_named_params_missing_raises(self):
        with self.assertRaises(Reject):
            db._named_params("SELECT :x", {})


class GraphCheckTest(unittest.TestCase):
    def test_check_kind_rejects_unknown(self):
        with self.assertRaises(Reject):
            graph.check_kind("nope")

    def test_check_kind_accepts_contract_kind(self):
        graph.check_kind(C.NODE_KINDS[0]["kind"])

    def test_check_node_id_requires_matching_prefix(self):
        with self.assertRaises(Reject):
            graph.check_node_id("component", "operation:x")

    def test_check_node_id_rejects_illegal_chars(self):
        with self.assertRaises(Reject):
            graph.check_node_id("component", "component:a b")

    def test_check_attrs_allows_x_prefix(self):
        self.assertEqual(
            {"x_custom": "v"}, graph.check_attrs("component", {"x_custom": "v"})
        )

    def test_check_attrs_rejects_unknown_key(self):
        with self.assertRaises(Reject):
            graph.check_attrs("component", {"nope": 1})

    def test_edge_id_format(self):
        self.assertEqual("edge:depends:a:b", graph.edge_id("depends", "a", "b"))


class SqlDialectTest(unittest.TestCase):
    META_UPSERT = (
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
    )

    def test_mysql_meta_upsert_is_valid(self):
        out = db._mysql_translate(self.META_UPSERT)
        self.assertIn("meta(`key`, `value`)", out)
        self.assertIn("ON DUPLICATE KEY UPDATE", out)
        self.assertIn("`value`=VALUES(value)", out)
        self.assertNotIn("ON CONFLICT", out)
        self.assertNotIn("excluded.", out)

    def test_mysql_meta_select_quotes_identifiers(self):
        out = db._mysql_translate("SELECT value FROM meta WHERE key=?")
        self.assertEqual("SELECT `value` FROM meta WHERE `key`=?", out)

    def test_mysql_insert_or_ignore_without_conflict(self):
        out = db._mysql_translate("INSERT OR IGNORE INTO judge_history(id) VALUES(?)")
        self.assertIn("INSERT IGNORE INTO", out)
        self.assertNotIn("ON CONFLICT", out)

    def test_mysql_multiline_conflict_still_translates(self):
        sql = (
            "INSERT INTO meta(key, value) VALUES(?, ?)\n"
            "  ON CONFLICT(key)\n  DO UPDATE SET value=excluded.value"
        )
        out = db._mysql_translate(sql)
        self.assertIn("ON DUPLICATE KEY UPDATE", out)
        self.assertNotIn("ON CONFLICT", out)

    def test_pg_insert_or_ignore_appends_on_conflict(self):
        out = db._pg_translate("INSERT OR IGNORE INTO judge_history(id) VALUES(?)")
        self.assertTrue(out.endswith("ON CONFLICT DO NOTHING"))
        self.assertIn("%s", out)
        self.assertNotIn("?", out)

    def test_pg_strips_trailing_semicolon_before_appending(self):
        out = db._pg_translate("INSERT OR IGNORE INTO t (a) VALUES(?);")
        self.assertIn("VALUES(%s) ON CONFLICT DO NOTHING", out)
        self.assertNotIn("; ON CONFLICT", out)

    def test_pg_question_mark_inside_string_literal_is_kept(self):
        # 旧实现是朴素 replace("?","%s")，字面量里的 ? 也会被换掉
        out = db._pg_translate("SELECT 'status?' FROM t WHERE a=?", has_params=True)
        self.assertIn("'status?'", out)
        self.assertIn("a=%s", out)

    def test_pg_percent_in_literal_is_escaped_when_params_present(self):
        # '100%' 会被 psycopg 当成占位符，报 placeholder 数量不符
        out = db._pg_translate("SELECT '100%' FROM t WHERE a=?", has_params=True)
        self.assertIn("'100%%'", out)
        self.assertIn("a=%s", out)

    def test_pg_percent_is_untouched_without_params(self):
        out = db._pg_translate("SELECT '100%' FROM t", has_params=False)
        self.assertIn("'100%'", out)
        self.assertNotIn("%%", out)

    def test_pg_double_quoted_identifier_is_not_touched(self):
        out = db._pg_translate('SELECT "a?b" FROM t WHERE a=?', has_params=True)
        self.assertIn('"a?b"', out)
        self.assertIn("a=%s", out)

    def test_concat_prefix_uses_concat_on_mysql(self):
        # MariaDB 的 || 是逻辑或：'jh:' || w.id 求值为 0，回填历史会全部撞到 id='0'
        self.assertEqual("CONCAT('jh:', w.id)", db._concat_prefix("mysql", "jh:", "w.id"))
        self.assertEqual("'jh:' || w.id", db._concat_prefix("sqlite", "jh:", "w.id"))
        self.assertEqual("'jh:' || w.id", db._concat_prefix("postgres", "jh:", "w.id"))


class ConnectionWrapperTest(unittest.TestCase):
    """MySQL / PG 连接包装要对齐 sqlite3 的子集。

    在补上 executemany 之前，import-file / import-repo 在非 SQLite 后端
    100% AttributeError（这两个命令都会批量写 feature_nodes）。
    """

    class _Fake:
        def __init__(self):
            self.calls: list[tuple[str, tuple]] = []

        def execute(self, sql: str, params=()):
            self.calls.append((sql, params))
            return db._NoopCursor()

        def commit(self) -> None:
            return None

        def rollback(self) -> None:
            return None

        def close(self) -> None:
            return None

    def test_mysql_executemany_runs_once_per_row(self):
        fake = self._Fake()
        wrapper = db._MySQLConnection(fake)
        fake.calls.clear()  # 构造时发过 SET SESSION TRANSACTION ISOLATION LEVEL
        wrapper.executemany("INSERT OR IGNORE INTO t(a,b) VALUES(?,?)", [("x", 1), ("y", 2)])
        self.assertEqual(2, len(fake.calls))
        self.assertIn("INSERT IGNORE INTO", fake.calls[0][0])
        self.assertEqual(("x", 1), fake.calls[0][1])
        self.assertEqual(("y", 2), fake.calls[1][1])

    def test_pg_executemany_runs_once_per_row(self):
        fake = self._Fake()
        wrapper = db._PgConnection(fake)
        wrapper.executemany("INSERT OR IGNORE INTO t(a,b) VALUES(?,?)", [("x", 1), ("y", 2)])
        self.assertEqual(2, len(fake.calls))
        self.assertIn("%s", fake.calls[0][0])
        self.assertTrue(fake.calls[0][0].endswith("ON CONFLICT DO NOTHING"))
        self.assertEqual(("x", 1), fake.calls[0][1])

    def test_executemany_with_empty_sequence_is_a_noop(self):
        fake = self._Fake()
        wrapper = db._PgConnection(fake)
        fake.calls.clear()
        wrapper.executemany("INSERT INTO t(a) VALUES(?)", [])
        self.assertEqual(0, len(fake.calls))


class InitCommandTest(unittest.TestCase):
    """cmd_init 在非 SQLite 后端要能返回掩码后的连接串。

    此前 commands_repo 没有 import db_url / re，MySQL 与 PostgreSQL 上这条分支
    100% NameError——而 init_db 已经提交过，表建好了、退出码却是 2。
    """

    def test_non_sqlite_backend_masks_credentials(self):
        from types import SimpleNamespace
        from unittest import mock

        class FakeConn:
            dialect = "mysql"

        args = SimpleNamespace(root_path=Path("state"))
        with mock.patch.object(commands_repo, "init_db", lambda conn: {"from": 0, "to": 9}), \
                mock.patch.object(commands_repo, "db_url", lambda: "mysql://user:s3cret@db.local:3306/x"):
            out = commands_repo.cmd_init(FakeConn(), args)
        self.assertEqual("mysql", out["backend"])
        self.assertNotIn("s3cret", out["db"])
        self.assertIn("***", out["db"])
        self.assertEqual(9, out["schema_version"])

    def test_sqlite_backend_reports_database_file(self):
        from types import SimpleNamespace
        from unittest import mock

        class FakeConn:
            dialect = "sqlite"

        args = SimpleNamespace(root_path=Path("state"))
        with mock.patch.object(commands_repo, "init_db", lambda conn: {"from": 0, "to": 9}):
            out = commands_repo.cmd_init(FakeConn(), args)
        self.assertEqual("sqlite", out["backend"])
        self.assertIn("graph.sqlite", out["db"])


class EnsureDbTest(unittest.TestCase):
    """ensure_db 要能区分「没初始化」和「schema 落后」——两者的修复动作不同。"""

    def _conn(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        return conn

    def test_empty_database_reports_uninitialized(self):
        conn = self._conn()
        with self.assertRaises(Reject) as ctx:
            db.ensure_db(conn)
        self.assertIn("未初始化", str(ctx.exception))
        self.assertIn("meta", str(ctx.exception))
        conn.close()

    def test_complete_schema_passes(self):
        conn = self._conn()
        db.init_db(conn)
        db.ensure_db(conn)  # 不抛即通过
        conn.close()

    def test_lagging_column_reports_schema_behind(self):
        conn = self._conn()
        db.init_db(conn)
        # 模拟迁移前的旧库：少一列。sqlite 3.35+ 支持 DROP COLUMN
        conn.execute("ALTER TABLE bites DROP COLUMN phase")
        conn.commit()
        with self.assertRaises(Reject) as ctx:
            db.ensure_db(conn)
        message = str(ctx.exception)
        self.assertIn("schema 落后", message)
        self.assertIn("bites.phase", message)
        self.assertIn("不要重建库", message)
        conn.close()

    def test_missing_single_table_is_named(self):
        conn = self._conn()
        db.init_db(conn)
        conn.execute("DROP TABLE changes")
        conn.commit()
        with self.assertRaises(Reject) as ctx:
            db.ensure_db(conn)
        self.assertIn("changes", str(ctx.exception))
        conn.close()


class NamedParamsEdgeTest(unittest.TestCase):
    def test_repeated_placeholder_collects_each_occurrence(self):
        sql, params = db._named_params("SELECT * FROM t WHERE a=:x OR b=:x", {"x": 7})
        self.assertEqual("SELECT * FROM t WHERE a=? OR b=?", sql)
        self.assertEqual((7, 7), params)

    def test_placeholder_in_string_literal_is_a_known_limitation(self):
        # :name 出现在字符串字面量里也会被当成占位符；当前 schema 不依赖这种写法，
        # 这里把它记成已知限制，避免以后误以为支持。
        with self.assertRaises(Reject):
            db._named_params("SELECT ':x'", {})


class WorkStateTest(unittest.TestCase):
    """工单状态机直接打 SQLite 内存库。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA_SQL)
        self.conn.execute(
            "INSERT INTO features (id, name, generation, statement, created_at) "
            "VALUES ('f', 'F', 1, 's', '2026-01-01T00:00:00Z')"
        )

    def tearDown(self):
        self.conn.close()

    def _insert(self, kind="scan", targets=None, depends_on=None):
        return work.insert_work(
            self.conn, "f", 1, kind, targets or ["a:*"], depends_on or []
        )

    def test_insert_new_work_item(self):
        result = self._insert(kind="model-architecture", targets=["component:x:*"])
        self.assertEqual("insert", result["action"])
        item = work.get_work(self.conn, result["id"])
        self.assertEqual("ready", item["status"])
        self.assertEqual(["component:x:*"], jsonio.loads(item["target_ids"], []))

    def test_insert_merge_appends_new_targets_without_duplicates(self):
        self._insert(kind="scan", targets=["a:x"])
        result = work.insert_work(
            self.conn, "f", 1, "scan", ["a:x", "a:y"], None, merge=True
        )
        self.assertEqual("merge", result["action"])
        item = work.get_work(self.conn, result["id"])
        self.assertEqual(["a:x", "a:y"], jsonio.loads(item["target_ids"], []))

    def test_insert_merge_rejects_passed_item(self):
        result = self._insert(kind="scan")
        self.conn.execute(
            "UPDATE work_items SET status='passed' WHERE id=?", (result["id"],)
        )
        with self.assertRaises(Reject):
            work.insert_work(self.conn, "f", 1, "scan", ["a:y"], None, merge=True)

    def test_insert_without_merge_replaces_targets(self):
        self._insert(kind="scan", targets=["a:x"])
        result = self._insert(kind="scan", targets=["a:y"])
        self.assertEqual("update", result["action"])
        item = work.get_work(self.conn, result["id"])
        self.assertEqual(["a:y"], jsonio.loads(item["target_ids"], []))

    def test_require_token_missing_raises(self):
        with self.assertRaises(Reject):
            work.require_token(self.conn, "")

    def test_require_token_unknown_raises(self):
        with self.assertRaises(Reject):
            work.require_token(self.conn, "nope")

    def test_require_token_rejects_non_claimed(self):
        wid = self._insert(kind="scan")["id"]
        self.conn.execute("UPDATE work_items SET claim_token='t1' WHERE id=?", (wid,))
        with self.assertRaises(Reject):
            work.require_token(self.conn, "t1")

    def test_require_token_returns_claimed_item(self):
        wid = self._insert(kind="scan")["id"]
        self.conn.execute(
            "UPDATE work_items SET status='claimed', claim_token='t1' WHERE id=?",
            (wid,),
        )
        item = work.require_token(self.conn, "t1")
        self.assertEqual(wid, item["id"])

    def test_append_evidence_deduplicates(self):
        wid = self._insert(kind="scan")["id"]
        item = work.get_work(self.conn, wid)
        work.append_evidence(self.conn, item, ["n1", "n2"])
        work.append_evidence(self.conn, item, ["n2", "n3"])
        stored = jsonio.loads(work.get_work(self.conn, wid)["evidence_ids"], [])
        self.assertEqual(["n1", "n2", "n3"], stored)

    def test_get_work_by_token(self):
        wid = self._insert(kind="scan")["id"]
        self.conn.execute("UPDATE work_items SET claim_token='t9' WHERE id=?", (wid,))
        self.assertEqual(wid, work.get_work_by_token(self.conn, "t9")["id"])


class WorkflowStateTest(unittest.TestCase):
    """条件链与就绪派生直接打 SQLite 内存库。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA_SQL)
        self.conn.execute(
            "INSERT INTO features (id, name, generation, statement, created_at) "
            "VALUES ('f', 'F', 1, 's', '2026-01-01T00:00:00Z')"
        )
        for name in C.CONDITIONS:
            self.conn.execute(
                "INSERT INTO conditions (feature_id, generation, name, status) "
                "VALUES (?,?,?,?)",
                ("f", 1, name, 0),
            )

    def tearDown(self):
        self.conn.close()

    def _feature(self):
        return wf.ensure_feature(self.conn, "f")

    def _insert_work(self, wid, status, depends_on):
        self.conn.execute(
            "INSERT INTO work_items "
            "(id, feature_id, generation, kind, role, target_ids, status, depends_on, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                wid,
                "f",
                1,
                "scan",
                "scan",
                "[]",
                status,
                jsonio.dumps(depends_on),
                "2026-01-01T00:00:00Z",
            ),
        )

    def test_ensure_feature_missing_raises(self):
        with self.assertRaises(Reject):
            wf.ensure_feature(self.conn, "nope")

    def test_condition_flags_requires_complete_chain(self):
        self.conn.execute("DELETE FROM conditions WHERE name='Ready'")
        with self.assertRaises(Reject):
            wf.condition_flags(self.conn, self._feature())

    def test_current_phase_returns_first_false_condition(self):
        self.conn.execute("UPDATE conditions SET status=1 WHERE name='Accepted'")
        self.assertEqual(
            "ArchitectureReconciled", wf.current_phase(self.conn, self._feature())
        )

    def test_current_phase_ready_when_all_true(self):
        self.conn.execute("UPDATE conditions SET status=1")
        self.assertEqual("Ready", wf.current_phase(self.conn, self._feature()))

    def test_recompute_ready_sets_one_when_all_true(self):
        self.conn.execute("UPDATE conditions SET status=1 WHERE name != 'Ready'")
        self.assertEqual(1, wf.recompute_ready(self.conn, "f", 1))
        row = self.conn.execute(
            "SELECT status FROM conditions WHERE name='Ready'"
        ).fetchone()
        self.assertEqual(1, row["status"])

    def test_recompute_ready_sets_zero_when_one_missing(self):
        self.conn.execute("UPDATE conditions SET status=1 WHERE name != 'Ready'")
        self.conn.execute("UPDATE conditions SET status=0 WHERE name='BehaviorPassed'")
        self.assertEqual(0, wf.recompute_ready(self.conn, "f", 1))

    def test_refresh_blocked_unblocks_when_dependency_passed(self):
        self._insert_work("w1", "passed", [])
        self._insert_work("w2", "blocked", ["w1"])
        wf.refresh_blocked(self.conn, "f", 1)
        row = self.conn.execute(
            "SELECT status FROM work_items WHERE id='w2'"
        ).fetchone()
        self.assertEqual("ready", row["status"])

    def test_refresh_blocked_keeps_blocked_when_dependency_open(self):
        self._insert_work("w1", "claimed", [])
        self._insert_work("w2", "blocked", ["w1"])
        wf.refresh_blocked(self.conn, "f", 1)
        row = self.conn.execute(
            "SELECT status FROM work_items WHERE id='w2'"
        ).fetchone()
        self.assertEqual("blocked", row["status"])

    def test_scope_ids_merges_feature_nodes_requirements_and_wildcards(self):
        self.conn.execute(
            "INSERT INTO nodes (id, kind, name) VALUES ('component:x:a','component','A')"
        )
        self.conn.execute(
            "INSERT INTO nodes (id, kind, name) VALUES ('operation:x:b','operation','B')"
        )
        self.conn.execute(
            "INSERT INTO nodes (id, kind, name) VALUES ('requirement:f:r1','requirement','R')"
        )
        self.conn.execute(
            "INSERT INTO feature_nodes (feature_id, node_id) VALUES ('f','component:x:a')"
        )
        self._insert_work("w9", "ready", [])
        self.conn.execute(
            "UPDATE work_items SET target_ids=? WHERE id='w9'",
            (jsonio.dumps(["operation:*"]),),
        )
        ids = wf.scope_ids(self.conn, "f")
        self.assertIn("component:x:a", ids)
        self.assertIn("operation:x:b", ids)
        self.assertIn("requirement:f:r1", ids)


class CoverageMathTest(unittest.TestCase):
    """第三个参数是 Beta 先验总强度 a₀+b₀；prior=0.1 时 a₀=1、b₀=9、denom=10。"""

    def test_zero_scope_returns_covered(self):
        self.assertEqual(0, gates._required_coverage(0, 1.0, 10.0, 0, 0.1))

    def test_nonpositive_epsilon_returns_covered(self):
        self.assertEqual(3, gates._required_coverage(10, 1.0, 10.0, 3, 0.0))

    def test_already_met_returns_covered(self):
        self.assertEqual(9, gates._required_coverage(10, 1.0, 10.0, 9, 0.1))

    def test_finds_minimal_satisfying_m(self):
        self.assertEqual(9, gates._required_coverage(10, 1.0, 10.0, 0, 0.1))

    def test_caps_at_scope_size(self):
        self.assertEqual(10, gates._required_coverage(10, 10.0, 10.0, 0, 0.01))

    def test_denominator_matches_contract_pm_formula(self):
        """契约 p_m=(1+d)/(10+m)。旧实现用 (1+d)/(9+m)，分母少算了 a₀。

        S=1、ε=0.1、d=0 时 residual(0)=1/10=0.1 ≤ ε，不需要任何咬合；
        旧数学会算出需要 1 个，于是 coverage 同时报 p=0.1 与 met=false。
        """
        self.assertEqual(0, gates._required_coverage(1, 1.0, 10.0, 0, 0.1))

    def test_truncate_limits(self):
        self.assertEqual([1, 2], gates._truncate([1, 2, 3], 2))


class CoverageReportTest(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA_SQL)
        self.conn.execute(
            "INSERT INTO features (id, name, generation, statement, created_at) "
            "VALUES ('f', 'F', 1, 's', '2026-01-01T00:00:00Z')"
        )
        for name in C.CONDITIONS:
            self.conn.execute(
                "INSERT INTO conditions (feature_id, generation, name, status) "
                "VALUES (?,?,?,?)",
                ("f", 1, name, 0),
            )
        self.conn.execute(
            "INSERT INTO nodes (id, kind, name) VALUES ('component:x:a','component','A')"
        )
        self.conn.execute(
            "INSERT INTO feature_nodes (feature_id, node_id) VALUES ('f','component:x:a')"
        )

    def tearDown(self):
        self.conn.close()

    def test_empty_bites_report_all_phases(self):
        feature = wf.ensure_feature(self.conn, "f")
        report = gates.coverage_report(self.conn, feature)
        self.assertEqual(1, report["scope_size"])
        self.assertTrue(report["phases"])
        for phase in report["phases"]:
            self.assertEqual(0, phase["covered"])
            self.assertGreaterEqual(phase["n_required"], 0)
        if report["unmet"]:
            self.assertEqual(report["unmet"][0], report["next"])
        else:
            self.assertIsNone(report["next"])

    def test_strict_epsilon_requires_coverage(self):
        feature = wf.ensure_feature(self.conn, "f")
        report = gates.coverage_report(self.conn, feature, epsilon=0.001)
        for phase in report["phases"]:
            self.assertGreaterEqual(phase["n_required"], 1)
            self.assertFalse(phase["met"])
        self.assertEqual(report["unmet"][0], report["next"])

    def test_single_node_scope_needs_no_bite_at_exact_epsilon(self):
        """S=1、ε=0.1、d=0：p=1/(10+0)=0.1，residual(0)=1/10=0.1 ≤ ε，n_required=0。

        旧实现分母用 ``b₀+m``（9+m），residual(0)=1/9>0.1，会算出需要 1 个咬合——
        于是同一份报告里 p=0.1 却 met=false，自相矛盾。这条测的是
        ``coverage_report`` 的接线，不只是 ``_required_coverage`` 本身。
        """
        feature = wf.ensure_feature(self.conn, "f")
        report = gates.coverage_report(self.conn, feature, epsilon=0.1)
        phase = report["phases"][0]
        self.assertAlmostEqual(0.1, phase["p"], places=6)
        self.assertEqual(0, phase["n_required"])
        self.assertTrue(phase["met"])

    def test_drift_report_empty(self):
        feature = wf.ensure_feature(self.conn, "f")
        report = gates.drift_report(self.conn, feature)
        self.assertEqual(0, report["count"])
        self.assertFalse(report["enforced"])


class ConformanceTest(unittest.TestCase):
    """设计-代码一致性报告的四类差异。"""

    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(db.SCHEMA_SQL)
        self.conn.execute(
            "INSERT INTO features (id, name, generation, statement, created_at) "
            "VALUES ('f','F',1,'s','2026-01-01T00:00:00Z')"
        )
        for name in C.CONDITIONS:
            self.conn.execute(
                "INSERT INTO conditions (feature_id, generation, name, status) "
                "VALUES (?,?,?,?)",
                ("f", 1, name, 0),
            )

    def tearDown(self):
        self.conn.close()

    def _node(self, nid, kind, name, repo=None, path=None):
        self.conn.execute(
            "INSERT INTO nodes (id, kind, name, repo, path) VALUES (?,?,?,?,?)",
            (nid, kind, name, repo, path),
        )
        self.conn.execute(
            "INSERT INTO feature_nodes (feature_id, node_id) VALUES ('f', ?)", (nid,)
        )

    def _edge(self, src, dst, kind):
        self.conn.execute(
            "INSERT INTO edges (id, src, dst, kind) VALUES (?,?,?,?)",
            (f"{kind}:{src}:{dst}", src, dst, kind),
        )

    def _report(self, limit: int = 50):
        feature = wf.ensure_feature(self.conn, "f")
        return gates.conformance_report(self.conn, feature, limit=limit)

    def test_empty_scope_has_no_violations(self):
        report = self._report()
        self.assertEqual(0, report["violations"])
        self.assertEqual(0, report["anchors"]["design_nodes"])

    def test_design_element_without_anchor_is_reported(self):
        self._node("component:demo:a", "component", "A")
        report = self._report()
        self.assertEqual(["component:demo:a"], report["anchors"]["missing"])
        self.assertEqual(1, report["violations"])

    def test_anchor_to_code_node_with_repo_path_clears_missing(self):
        self._node("component:demo:a", "component", "A")
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        self._edge("component:demo:a", "operation:demo:r:x", "maps_to")
        report = self._report()
        self.assertNotIn("component:demo:a", report["anchors"]["missing"])

    def test_code_operation_without_design_coverage_is_orphan(self):
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        report = self._report()
        self.assertEqual(1, report["anchors"]["code_orphan_count"])
        # 孤立代码只报告，不算 violation
        self.assertEqual(0, report["violations"])

    def test_depends_without_code_backing(self):
        self._node("component:demo:a", "component", "A")
        self._node("component:demo:b", "component", "B")
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        self._node("operation:demo:r:y", "operation", "y", repo="r", path="p.py")
        self._edge("component:demo:a", "operation:demo:r:x", "maps_to")
        self._edge("component:demo:b", "operation:demo:r:y", "maps_to")
        self._edge("component:demo:a", "component:demo:b", "depends")
        report = self._report()
        self.assertEqual(1, report["structural"]["missing_backing_count"])
        self.assertEqual(1, report["violations"])

    def test_undeclared_call_between_design_units(self):
        self._node("component:demo:a", "component", "A")
        self._node("component:demo:b", "component", "B")
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        self._node("operation:demo:r:y", "operation", "y", repo="r", path="p.py")
        self._edge("component:demo:a", "operation:demo:r:x", "maps_to")
        self._edge("component:demo:b", "operation:demo:r:y", "maps_to")
        self._edge("operation:demo:r:x", "operation:demo:r:y", "calls")
        report = self._report()
        self.assertEqual(1, report["structural"]["undeclared_count"])
        self.assertEqual(
            "component:demo:a", report["structural"]["undeclared"][0]["from"]
        )

    def test_declared_depends_suppresses_undeclared(self):
        self._node("component:demo:a", "component", "A")
        self._node("component:demo:b", "component", "B")
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        self._node("operation:demo:r:y", "operation", "y", repo="r", path="p.py")
        self._edge("component:demo:a", "operation:demo:r:x", "maps_to")
        self._edge("component:demo:b", "operation:demo:r:y", "maps_to")
        self._edge("operation:demo:r:x", "operation:demo:r:y", "calls")
        self._edge("component:demo:a", "component:demo:b", "depends")
        report = self._report()
        self.assertEqual(0, report["structural"]["undeclared_count"])
        self.assertEqual(0, report["violations"])

    def test_depends_with_evidence_is_backed(self):
        # derive 写入的 depends 带 x_evidence（来源文件对），这本身就是代码依据
        self._node("component:demo:a", "component", "A")
        self._node("component:demo:b", "component", "B")
        self.conn.execute(
            "INSERT INTO edges (id, src, dst, kind, attrs_json) VALUES (?,?,?,?,?)",
            (
                "depends:a:b",
                "component:demo:a",
                "component:demo:b",
                "depends",
                jsonio.dumps({"x_evidence": [["flask/app.py", "flask/sansio/app.py"]]}),
            ),
        )
        report = self._report()
        self.assertEqual(0, report["structural"]["missing_backing_count"])

    def test_use_case_without_verifies_is_missing_test(self):
        self._node("use_case:demo:u", "use_case", "U")
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        self._edge("use_case:demo:u", "operation:demo:r:x", "maps_to")
        report = self._report()
        self.assertEqual(1, report["tests"]["missing_count"])
        self.assertEqual(1, report["violations"])

    def test_verified_use_case_is_not_missing(self):
        self._node("use_case:demo:u", "use_case", "U")
        self._node("component:demo:a", "component", "A")
        self._edge("component:demo:a", "use_case:demo:u", "verifies")
        report = self._report()
        self.assertEqual(0, report["tests"]["missing_count"])

    def test_orphan_split_by_derived_contains(self):
        self._node("component:demo:a", "component", "A")
        self.conn.execute(
            "UPDATE nodes SET origin='derived' WHERE id='component:demo:a'"
        )
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        self._node("operation:demo:r:y", "operation", "y", repo="r", path="p.py")
        self._edge("component:demo:a", "operation:demo:r:x", "contains")
        report = self._report()
        self.assertEqual(2, report["anchors"]["code_orphan_count"])
        self.assertEqual(1, report["anchors"]["unanchored_count"])
        self.assertEqual(1, report["anchors"]["truly_orphan_count"])

    def test_hint_when_derived_components_lack_anchors(self):
        self._node("component:demo:a", "component", "A")
        self.conn.execute(
            "UPDATE nodes SET origin='derived' WHERE id='component:demo:a'"
        )
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        report = self._report()
        self.assertIn("hint", report)
        self.assertIn("derived", report["hint"])

    def test_no_hint_when_components_are_anchored(self):
        self._node("component:demo:a", "component", "A")
        self._node("operation:demo:r:x", "operation", "x", repo="r", path="p.py")
        self._edge("component:demo:a", "operation:demo:r:x", "maps_to")
        report = self._report()
        self.assertNotIn("hint", report)

    def test_truncate_limits_list_but_keeps_count(self):
        for i in range(3):
            self._node(f"component:demo:c{i}", "component", f"C{i}")
        report = self._report(limit=1)
        self.assertEqual(1, len(report["anchors"]["missing"]))
        self.assertEqual(3, report["anchors"]["missing_count"])
        self.assertTrue(report["truncated"])


class RelativeImportTest(unittest.TestCase):
    """相对导入解析：derive 的 depends 全靠它。"""

    def _repo(self, tmp: Path, files: dict[str, str]) -> Path:
        for rel, body in files.items():
            path = tmp / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        return tmp

    def test_from_dot_import_name(self):
        with temp_dir() as tmp:
            self._repo(tmp, {
                "pkg/__init__.py": "",
                "pkg/mod.py": "from . import helper",
                "pkg/helper.py": "",
            })
            pairs = commands_repo._import_file_pairs(Path(tmp))
            self.assertIn(("pkg/mod.py", "pkg/helper.py"), pairs)

    def test_from_dot_module_import_name(self):
        with temp_dir() as tmp:
            self._repo(tmp, {
                "pkg/__init__.py": "",
                "pkg/json/__init__.py": "",
                "pkg/mod.py": "from .json import dumps",
            })
            pairs = commands_repo._import_file_pairs(Path(tmp))
            self.assertIn(("pkg/mod.py", "pkg/json/__init__.py"), pairs)

    def test_from_dotdot_import(self):
        with temp_dir() as tmp:
            self._repo(tmp, {
                "pkg/__init__.py": "",
                "pkg/base.py": "",
                "pkg/sub/__init__.py": "",
                "pkg/sub/impl.py": "from ..base import thing",
            })
            pairs = commands_repo._import_file_pairs(Path(tmp))
            self.assertIn(("pkg/sub/impl.py", "pkg/base.py"), pairs)

    def test_absolute_import_still_works(self):
        with temp_dir() as tmp:
            self._repo(tmp, {
                "pkg/__init__.py": "",
                "pkg/target.py": "",
                "pkg/mod.py": "import pkg.target",
            })
            pairs = commands_repo._import_file_pairs(Path(tmp))
            self.assertIn(("pkg/mod.py", "pkg/target.py"), pairs)


class EvidenceTest(unittest.TestCase):
    def test_sha256_file_matches_hashlib(self):
        with temp_dir() as tmp:
            path = Path(tmp) / "x.bin"
            path.write_bytes(b"hello")
            self.assertEqual(
                hashlib.sha256(b"hello").hexdigest(), evidence.sha256_file(path)
            )


if __name__ == "__main__":
    unittest.main()
