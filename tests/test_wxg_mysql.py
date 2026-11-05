"""wxg_mysql 的集成测试：直接连 MariaDB，不依赖 wxg.py。

运行（在 why-exist-graph 技能根目录）：
    python -m unittest discover -s tests -p "test_wxg_mysql.py" -v
    python -m unittest discover -s tests -v          # 与 test_wxg.py 一起跑

默认连接 ``mysql://root:wxgpass@127.0.0.1:3307``（可用环境变量
``WXG_MYSQL_TEST_URL`` 覆盖，URL 可带库名，测试会忽略它并另建临时库）。
连不上时整类跳过；测试自建 ``wxg_client_test_<pid>`` 库，结束时删除；
所有断言都走本客户端。
"""

from __future__ import annotations

import os
import sys
import threading
import unittest
import urllib.parse
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import wxg_mysql  # noqa: E402

DEFAULT_TEST_URL = "mysql://root:wxgpass@127.0.0.1:3307"
TEST_URL = os.environ.get("WXG_MYSQL_TEST_URL", DEFAULT_TEST_URL).strip()


def _without_database(url: str) -> tuple[str, str]:
    parts = urllib.parse.urlsplit(url)
    base = urllib.parse.urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    host_port = parts.netloc.rsplit("@", 1)[-1]
    return base, host_port


class MySQLClientTestCase(unittest.TestCase):
    """每个用例一个连接、一个临时库里的独立表。"""

    base_url, host_port = _without_database(TEST_URL)
    db_name = f"wxg_client_test_{os.getpid()}"
    db_url = f"{base_url}/{db_name}"

    @classmethod
    def setUpClass(cls) -> None:
        try:
            with wxg_mysql.connect(cls.base_url) as admin:
                admin.execute(f"DROP DATABASE IF EXISTS `{cls.db_name}`").close()
                admin.execute(
                    f"CREATE DATABASE `{cls.db_name}` "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
                ).close()
                admin.commit()
        except wxg_mysql.MySQLDatabaseError as exc:
            raise unittest.SkipTest(f"MariaDB 不可用（{cls.base_url}）：{exc}")

    @classmethod
    def tearDownClass(cls) -> None:
        try:
            with wxg_mysql.connect(cls.base_url) as admin:
                admin.execute(f"DROP DATABASE IF EXISTS `{cls.db_name}`").close()
                admin.commit()
        except wxg_mysql.MySQLDatabaseError as exc:  # 清理失败不该掩盖测试结果
            print(f"warning: 删除临时库失败: {exc}", file=sys.stderr)

    def setUp(self) -> None:
        self.conn = wxg_mysql.connect(type(self).db_url)

    def tearDown(self) -> None:
        self.conn.close()

    # -------------------------------------------------------------- 辅助

    def rows(self, sql: str, params: tuple = ()) -> list[dict]:
        cur = self.conn.execute(sql, params)
        try:
            return cur.fetchall()
        finally:
            cur.close()

    def row(self, sql: str, params: tuple = ()) -> dict:
        cur = self.conn.execute(sql, params)
        try:
            result = cur.fetchone()
        finally:
            cur.close()
        self.assertIsNotNone(result)
        return result  # type: ignore[return-value]

    def fresh_rows(self, sql: str, params: tuple = ()) -> list[dict]:
        with wxg_mysql.connect(type(self).db_url) as conn:
            cur = conn.execute(sql, params)
            try:
                return cur.fetchall()
            finally:
                cur.close()

    # -------------------------------------------------------------- 用例

    def test_select_scalar_types_and_null(self) -> None:
        cur = self.conn.execute(
            "SELECT 1 AS one, -7 AS neg, 2.5 AS decimal_value, '中文' AS txt, "
            "NULL AS nothing, CAST('42' AS SIGNED) AS casted, (1 = 1) AS truth"
        )
        row = cur.fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["one"], 1)
        self.assertIsInstance(row["one"], int)
        self.assertEqual(row["neg"], -7)
        self.assertEqual(row["decimal_value"], 2.5)
        self.assertIsInstance(row["decimal_value"], float)
        self.assertEqual(row["txt"], "中文")
        self.assertIsNone(row["nothing"])
        self.assertEqual(row["casted"], 42)
        self.assertIsInstance(row["casted"], int)
        self.assertEqual(row["truth"], 1)
        self.assertIsNone(cur.fetchone())
        self.assertEqual(cur.fetchall(), [])
        cur.close()

    def test_create_insert_and_roundtrip(self) -> None:
        self.conn.execute(
            """
            CREATE TABLE roundtrip (
              id INTEGER NOT NULL AUTO_INCREMENT,
              name TEXT NOT NULL,
              score REAL,
              note TEXT,
              created_at TEXT,
              PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        ).close()
        payload = (
            "中文 'single' \"double\" \\ backslash\n换行\r\n\tTAB "
            "\x1a ctrl-z \x00 nul emoji 🧪"
        )
        cur = self.conn.execute(
            "INSERT INTO roundtrip (name, score, note, created_at) "
            "VALUES (?, ?, ?, ?)",
            (payload, 3.25, None, "2026-10-31T12:00:00"),
        )
        self.assertEqual(cur.rowcount, 1)
        cur.close()
        cur = self.conn.execute(
            "INSERT INTO roundtrip (name, score, note, created_at) "
            "VALUES (?, ?, ?, ?)",
            ("第二行", -0.5, "not null", "2026-10-31T12:01:00"),
        )
        self.assertEqual(cur.rowcount, 1)
        cur.close()

        rows = self.rows(
            "SELECT id, name, score, note, created_at FROM roundtrip ORDER BY id"
        )
        self.assertEqual([row["id"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["name"], payload)
        self.assertEqual(rows[0]["score"], 3.25)
        self.assertIsNone(rows[0]["note"])
        self.assertEqual(rows[0]["created_at"], "2026-10-31T12:00:00")
        self.assertEqual(rows[1]["name"], "第二行")
        self.assertEqual(rows[1]["score"], -0.5)
        self.assertEqual(rows[1]["note"], "not null")
        self.assertIsInstance(rows[1]["id"], int)
        self.assertIsInstance(rows[1]["score"], float)

    def test_executescript_multiple_statements(self) -> None:
        script = """
        -- 注释里的分号 ; 不应切分语句
        CREATE TABLE script_a (
          id INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY,
          body TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        CREATE TABLE script_b (id INTEGER PRIMARY KEY, note TEXT);
        # 井号注释里也可以有分号 ;
        INSERT INTO script_b (id, note) VALUES (1, 'a; b');
        INSERT INTO script_a (body) VALUES ('x; y');
        """
        self.conn.executescript(script)
        self.conn.commit()
        self.assertEqual(self.rows("SELECT id, note FROM script_b"), [
            {"id": 1, "note": "a; b"}
        ])
        self.assertEqual(self.rows("SELECT body FROM script_a"), [{"body": "x; y"}])
        # 空脚本 / 只有注释的脚本都是 no-op
        self.conn.executescript("")
        self.conn.executescript("-- 只有注释\n/* 还是注释 */\n")

    def test_update_and_delete_rowcount(self) -> None:
        self.conn.execute(
            "CREATE TABLE changes (id INTEGER PRIMARY KEY, value TEXT, counter INTEGER)"
        ).close()
        self.conn.execute(
            "INSERT INTO changes (id, value, counter) VALUES (?, ?, ?), (?, ?, ?)",
            (1, "one", 0, 2, "two", 0),
        ).close()
        cur = self.conn.execute(
            "UPDATE changes SET value = ? WHERE id = ?", ("one!", 1)
        )
        self.assertEqual(cur.rowcount, 1)
        cur.close()
        # 同值更新：affected_rows 是 modified rows，应为 0
        cur = self.conn.execute(
            "UPDATE changes SET value = ? WHERE id = ?", ("one!", 1)
        )
        self.assertEqual(cur.rowcount, 0)
        cur.close()
        cur = self.conn.execute("UPDATE changes SET counter = counter + 1")
        self.assertEqual(cur.rowcount, 2)
        cur.close()
        cur = self.conn.execute("DELETE FROM changes WHERE id = ?", (2,))
        self.assertEqual(cur.rowcount, 1)
        cur.close()
        self.assertEqual(
            self.rows("SELECT id, value, counter FROM changes ORDER BY id"),
            [{"id": 1, "value": "one!", "counter": 1}],
        )

    def test_duplicate_key_and_error_classification(self) -> None:
        self.conn.execute(
            "CREATE TABLE unique_rows (id INTEGER PRIMARY KEY, value TEXT)"
        ).close()
        self.conn.execute(
            "INSERT INTO unique_rows (id, value) VALUES (?, ?)", (1, "first")
        ).close()
        self.conn.commit()

        with self.assertRaises(wxg_mysql.MySQLDatabaseError) as caught:
            self.conn.execute(
                "INSERT INTO unique_rows (id, value) VALUES (?, ?)", (1, "dup")
            )
        error = caught.exception
        self.assertEqual(error.errno, 1062)
        self.assertIn("Duplicate", str(error))
        self.assertTrue(wxg_mysql.is_integrity_error(error))
        self.assertFalse(wxg_mysql.is_integrity_error(ValueError("nope")))
        self.assertTrue(
            wxg_mysql.is_integrity_error(
                wxg_mysql.MySQLDatabaseError("dup key", errno=1022)
            )
        )

        with self.assertRaises(wxg_mysql.MySQLDatabaseError) as caught:
            self.conn.execute("SELECT * FROM definitely_missing_table")
        missing = caught.exception
        self.assertEqual(missing.errno, 1146)
        self.assertFalse(wxg_mysql.is_integrity_error(missing))

        with self.assertRaises(wxg_mysql.MySQLDatabaseError) as caught:
            wxg_mysql.connect("mysql://root:wxgpass@127.0.0.1:1/wxg")
        self.assertIsNone(caught.exception.errno)
        self.assertFalse(wxg_mysql.is_integrity_error(caught.exception))

    def test_transaction_rollback_and_commit(self) -> None:
        self.conn.execute(
            "CREATE TABLE tx_rows (id INTEGER PRIMARY KEY, value TEXT)"
        ).close()
        self.conn.execute(
            "INSERT INTO tx_rows (id, value) VALUES (?, ?)", (1, "one")
        ).close()
        self.conn.commit()

        # rollback 后不可见
        self.conn.execute(
            "INSERT INTO tx_rows (id, value) VALUES (?, ?)", (2, "two")
        ).close()
        self.conn.rollback()
        self.assertEqual(
            self.fresh_rows("SELECT id FROM tx_rows ORDER BY id"), [{"id": 1}]
        )

        # commit 后可见
        self.conn.execute(
            "INSERT INTO tx_rows (id, value) VALUES (?, ?)", (3, "three")
        ).close()
        self.conn.commit()
        self.assertEqual(
            self.fresh_rows("SELECT id FROM tx_rows ORDER BY id"),
            [{"id": 1}, {"id": 3}],
        )

        # UPDATE 的 rollback
        self.conn.execute(
            "UPDATE tx_rows SET value = ? WHERE id = ?", ("changed", 1)
        ).close()
        self.conn.rollback()
        self.assertEqual(
            self.fresh_rows("SELECT value FROM tx_rows WHERE id = ?", (1,)),
            [{"value": "one"}],
        )

    def test_concurrent_writes_to_distinct_rows(self) -> None:
        self.conn.execute(
            "CREATE TABLE concurrent_rows "
            "(id INTEGER PRIMARY KEY, value TEXT) ENGINE=InnoDB"
        ).close()
        self.conn.execute(
            "INSERT INTO concurrent_rows (id, value) VALUES (1, 'init-1'), (2, 'init-2')"
        ).close()
        self.conn.commit()

        barrier = threading.Barrier(2)
        errors: list[tuple[int, BaseException]] = []
        lock = threading.Lock()

        def worker(row_id: int) -> None:
            connection = None
            try:
                connection = wxg_mysql.connect(type(self).db_url)
                connection.execute(
                    "UPDATE concurrent_rows SET value = ? WHERE id = ?",
                    (f"thread-{row_id}", row_id),
                ).close()
                # 两个事务都持有不同行的写锁时再一起提交；
                # 若退化成表锁，这里会超时并让用例失败。
                barrier.wait(timeout=10)
                connection.commit()
            except BaseException as exc:  # noqa: BLE001 - 测试要收集线程内异常
                with lock:
                    errors.append((row_id, exc))
                try:
                    barrier.abort()
                except BaseException:
                    pass
            finally:
                if connection is not None:
                    connection.close()

        threads = [threading.Thread(target=worker, args=(i,)) for i in (1, 2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        for thread in threads:
            self.assertFalse(thread.is_alive(), "并发写线程未结束")
        self.assertEqual(errors, [], f"并发写失败: {errors!r}")

        self.assertEqual(
            self.fresh_rows("SELECT id, value FROM concurrent_rows ORDER BY id"),
            [{"id": 1, "value": "thread-1"}, {"id": 2, "value": "thread-2"}],
        )

    def test_large_text_roundtrip(self) -> None:
        self.conn.execute(
            "CREATE TABLE big_text (id INTEGER PRIMARY KEY, body LONGTEXT) "
            "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
        ).close()
        body = "中文段落" * 20000 + "x'\"\\\n" * 5000 + "终"
        self.assertGreater(len(body.encode("utf-8")), 64 * 1024)
        cur = self.conn.execute(
            "INSERT INTO big_text (id, body) VALUES (?, ?)", (1, body)
        )
        self.assertEqual(cur.rowcount, 1)
        cur.close()
        row = self.row("SELECT body, LENGTH(body) AS byte_len FROM big_text")
        self.assertEqual(row["body"], body)
        self.assertEqual(row["byte_len"], len(body.encode("utf-8")))
        self.assertIsInstance(row["byte_len"], int)

    def test_placeholders_only_outside_literals_and_comments(self) -> None:
        self.conn.execute(
            "CREATE TABLE placeholders (id INTEGER PRIMARY KEY, value TEXT)"
        ).close()
        value = "what? 'quoted' \"double\" # -- x;"
        self.conn.execute(
            "INSERT INTO placeholders (id, value) VALUES (?, ?)", (1, value)
        ).close()
        self.assertEqual(
            self.rows(
                "SELECT value FROM placeholders WHERE id = ? AND value = ?",
                (1, value),
            ),
            [{"value": value}],
        )

        row = self.row(
            "SELECT ? AS a, '?' AS b, \"?\" AS c, 1 /* ? */ AS d", ("value",)
        )
        self.assertEqual(row["a"], "value")
        self.assertEqual(row["b"], "?")
        self.assertEqual(row["c"], "?")
        self.assertEqual(row["d"], 1)

        # 字符串里用双写单引号转义时，里面的 ? 也不能被当成占位符
        row = self.row("SELECT 'it''s ?' AS lit, ? AS param", ("v",))
        self.assertEqual(row["lit"], "it's ?")
        self.assertEqual(row["param"], "v")

        with self.assertRaises(ValueError):
            self.conn.execute("SELECT 1 AS one", (1,))
        with self.assertRaises(ValueError):
            self.conn.execute("SELECT ? AS a, ? AS b", (1,))

    def test_percent_encoded_credentials(self) -> None:
        user = f"wxg_cli_{os.getpid()}"
        password = "p@ss'w:ord/%?#"
        admin_url = type(self).base_url
        try:
            with wxg_mysql.connect(admin_url) as admin:
                admin.execute("DROP USER IF EXISTS ?@'%'", (user,)).close()
                admin.execute(
                    "CREATE USER ?@'%' IDENTIFIED BY ?", (user, password)
                ).close()
                admin.execute(
                    f"GRANT ALL PRIVILEGES ON `{self.db_name}`.* TO ?@'%'",
                    (user,),
                ).close()
                admin.commit()
            quoted_user = urllib.parse.quote(user, safe="")
            quoted_password = urllib.parse.quote(password, safe="")
            url = (
                f"mysql://{quoted_user}:{quoted_password}@"
                f"{self.host_port}/{self.db_name}"
            )
            with wxg_mysql.connect(url) as connection:
                row = connection.execute(
                    "SELECT 1 AS ok, DATABASE() AS dbname"
                ).fetchone()
                self.assertEqual(row, {"ok": 1, "dbname": self.db_name})
        finally:
            try:
                with wxg_mysql.connect(admin_url) as admin:
                    admin.execute("DROP USER IF EXISTS ?@'%'", (user,)).close()
                    admin.commit()
            except wxg_mysql.MySQLDatabaseError:
                pass

    def test_close_is_idempotent_and_blocks_execute(self) -> None:
        connection = wxg_mysql.connect(type(self).db_url)
        connection.close()
        connection.close()
        with self.assertRaises(wxg_mysql.MySQLDatabaseError):
            connection.execute("SELECT 1")


class AuthSwitchUnitTestCase(unittest.TestCase):
    """AuthSwitchRequest 的状态机单测：本机 MariaDB 只有 native 插件，
    正常登录不会触发切换，只能用伪造包覆盖这条路径。"""

    def _harness(self, packets: list[bytes]) -> "wxg_mysql.MySQLConnection":
        target = wxg_mysql._Target(
            "127.0.0.1", 3306, "user", "secret", "db"
        )
        connection = wxg_mysql.MySQLConnection(None, target)  # type: ignore[arg-type]
        connection._incoming = list(packets)  # type: ignore[attr-defined]
        connection._written = []  # type: ignore[attr-defined]

        def read_packet() -> bytes:
            return connection._incoming.pop(0)  # type: ignore[attr-defined]

        def write_packet(payload: bytes) -> None:
            connection._written.append(payload)  # type: ignore[attr-defined]

        connection._read_packet = read_packet  # type: ignore[method-assign]
        connection._write_packet = write_packet  # type: ignore[method-assign]
        return connection

    def test_native_password_auth_switch(self) -> None:
        seed = bytes(range(20))
        switch = (
            b"\xfe" + b"mysql_native_password\x00" + seed + b"\x00"
        )
        ok = b"\x00\x00\x00\x02\x00\x00\x00"
        connection = self._harness([switch, ok])
        connection._finish_authentication(seed, "mysql_native_password")
        self.assertEqual(len(connection._written), 1)  # type: ignore[attr-defined]
        self.assertEqual(
            connection._written[0],  # type: ignore[attr-defined]
            wxg_mysql._scramble_native_password("secret", seed),
        )

    def test_unsupported_auth_plugin_is_rejected(self) -> None:
        seed = bytes(range(20))
        switch = b"\xfe" + b"caching_sha2_password\x00" + seed + b"\x00"
        connection = self._harness([switch])
        with self.assertRaises(wxg_mysql.MySQLDatabaseError):
            connection._finish_authentication(seed, "mysql_native_password")


if __name__ == "__main__":
    unittest.main()
