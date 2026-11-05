"""状态库：schema、连接、后端适配、迁移。

默认 SQLite（WAL + busy_timeout），可选 MariaDB/MySQL 与 PostgreSQL。
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path

from .contract import C
from .errors import Reject

# ------------------------------------------------------------------ 数据库

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE TABLE IF NOT EXISTS repos (
  id TEXT PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  language TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  name TEXT,
  repo TEXT,
  path TEXT,
  symbol TEXT,
  line_start INTEGER,
  line_end INTEGER,
  attrs_json TEXT NOT NULL DEFAULT '{}',
  origin TEXT NOT NULL DEFAULT 'manual',
  unmapped INTEGER NOT NULL DEFAULT 0,
  stale INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS edges (
  id TEXT PRIMARY KEY,
  src TEXT NOT NULL,
  dst TEXT NOT NULL,
  kind TEXT NOT NULL,
  evidence_path TEXT,
  evidence_line INTEGER,
  unmapped INTEGER NOT NULL DEFAULT 0,
  attrs_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS features (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  generation INTEGER NOT NULL,
  statement TEXT NOT NULL,
  acceptance_json TEXT NOT NULL DEFAULT '[]',
  constraints_json TEXT NOT NULL DEFAULT '[]',
  coverage_epsilon REAL,
  drift_limit INTEGER,
  conformance INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS conditions (
  feature_id TEXT NOT NULL,
  generation INTEGER NOT NULL,
  name TEXT NOT NULL,
  status INTEGER NOT NULL DEFAULT 0,
  reason TEXT,
  PRIMARY KEY (feature_id, generation, name)
);
CREATE TABLE IF NOT EXISTS work_items (
  id TEXT PRIMARY KEY,
  feature_id TEXT NOT NULL,
  generation INTEGER NOT NULL,
  kind TEXT NOT NULL,
  role TEXT NOT NULL,
  target_ids TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'ready',
  depends_on TEXT NOT NULL DEFAULT '[]',
  assignee TEXT,
  claimed_by TEXT,
  claim_token TEXT,
  claimed_at TEXT,
  evidence_ids TEXT NOT NULL DEFAULT '[]',
  fail_reason TEXT,
  judged_by TEXT,
  judged_at TEXT,
  created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_work_token ON work_items(claim_token) WHERE claim_token IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_work_feature ON work_items(feature_id, generation);
CREATE TABLE IF NOT EXISTS feature_nodes (
  feature_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  PRIMARY KEY (feature_id, node_id)
);
CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  feature_id TEXT NOT NULL,
  generation INTEGER,
  work_item_id TEXT,
  name TEXT NOT NULL,
  command TEXT NOT NULL,
  exit_code INTEGER NOT NULL,
  artifact_path TEXT,
  artifact_sha256 TEXT,
  actor TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_feature ON evidence(feature_id, name);
CREATE TABLE IF NOT EXISTS bites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  node_id TEXT NOT NULL,
  feature_id TEXT,
  generation INTEGER,
  phase TEXT,
  verdict TEXT NOT NULL,
  reason TEXT,
  actor TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bites_node ON bites(node_id);
CREATE INDEX IF NOT EXISTS idx_bites_feature ON bites(feature_id, generation);
CREATE TABLE IF NOT EXISTS judge_history (
  id TEXT PRIMARY KEY,
  work_item_id TEXT NOT NULL,
  feature_id TEXT NOT NULL,
  generation INTEGER NOT NULL,
  kind TEXT NOT NULL,
  verdict TEXT NOT NULL,
  reason TEXT,
  actor TEXT NOT NULL,
  judged_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_judge_history_item ON judge_history(work_item_id);
CREATE TABLE IF NOT EXISTS changes (
  id TEXT PRIMARY KEY,
  feature_id TEXT NOT NULL,
  from_generation INTEGER NOT NULL,
  to_generation INTEGER NOT NULL,
  from_condition TEXT NOT NULL,
  statement TEXT NOT NULL,
  affected_json TEXT NOT NULL DEFAULT '[]',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_feature ON changes(feature_id, to_generation);
"""

# MariaDB/MySQL 版本：TEXT 键列改成有长度的 VARCHAR，去掉 SQLite 的部分索引，
# meta.key/value 用反引号（key 是 MySQL 保留字），bites.id 用 AUTO_INCREMENT。
MYSQL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS meta (
  `key` VARCHAR(128) PRIMARY KEY,
  `value` VARCHAR(512)
);
CREATE TABLE IF NOT EXISTS repos (
  id VARCHAR(128) PRIMARY KEY,
  path VARCHAR(700) NOT NULL UNIQUE,
  language VARCHAR(32) NOT NULL,
  created_at VARCHAR(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS nodes (
  id VARCHAR(512) PRIMARY KEY,
  kind VARCHAR(64) NOT NULL,
  name VARCHAR(255),
  repo VARCHAR(128),
  path VARCHAR(700),
  symbol VARCHAR(700),
  line_start INTEGER,
  line_end INTEGER,
  attrs_json LONGTEXT NOT NULL DEFAULT '{}',
  origin VARCHAR(32) NOT NULL DEFAULT 'manual',
  unmapped INTEGER NOT NULL DEFAULT 0,
  stale INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS edges (
  id VARCHAR(512) PRIMARY KEY,
  src VARCHAR(512) NOT NULL,
  dst VARCHAR(512) NOT NULL,
  kind VARCHAR(64) NOT NULL,
  evidence_path VARCHAR(700),
  evidence_line INTEGER,
  unmapped INTEGER NOT NULL DEFAULT 0,
  attrs_json LONGTEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS features (
  id VARCHAR(128) PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  generation INTEGER NOT NULL,
  statement TEXT NOT NULL,
  acceptance_json LONGTEXT NOT NULL DEFAULT '[]',
  constraints_json LONGTEXT NOT NULL DEFAULT '[]',
  coverage_epsilon REAL,
  drift_limit INTEGER,
  conformance INTEGER NOT NULL DEFAULT 0,
  created_at VARCHAR(64) NOT NULL
);
CREATE TABLE IF NOT EXISTS conditions (
  feature_id VARCHAR(128) NOT NULL,
  generation INTEGER NOT NULL,
  name VARCHAR(64) NOT NULL,
  status INTEGER NOT NULL DEFAULT 0,
  reason TEXT,
  PRIMARY KEY (feature_id, generation, name)
);
CREATE TABLE IF NOT EXISTS work_items (
  id VARCHAR(512) PRIMARY KEY,
  feature_id VARCHAR(128) NOT NULL,
  generation INTEGER NOT NULL,
  kind VARCHAR(64) NOT NULL,
  role VARCHAR(64) NOT NULL,
  target_ids LONGTEXT NOT NULL DEFAULT '[]',
  status VARCHAR(32) NOT NULL DEFAULT 'ready',
  depends_on LONGTEXT NOT NULL DEFAULT '[]',
  assignee VARCHAR(191),
  claimed_by VARCHAR(191),
  claim_token VARCHAR(191),
  claimed_at VARCHAR(64),
  evidence_ids LONGTEXT NOT NULL DEFAULT '[]',
  fail_reason TEXT,
  judged_by VARCHAR(191),
  judged_at VARCHAR(64),
  created_at VARCHAR(64) NOT NULL,
  UNIQUE KEY idx_work_token (claim_token)
);
CREATE INDEX IF NOT EXISTS idx_work_feature ON work_items(feature_id, generation);
CREATE TABLE IF NOT EXISTS feature_nodes (
  feature_id VARCHAR(128) NOT NULL,
  node_id VARCHAR(512) NOT NULL,
  PRIMARY KEY (feature_id, node_id)
);
CREATE TABLE IF NOT EXISTS evidence (
  id VARCHAR(128) PRIMARY KEY,
  feature_id VARCHAR(128) NOT NULL,
  generation INTEGER,
  work_item_id VARCHAR(512),
  name VARCHAR(255) NOT NULL,
  command TEXT NOT NULL,
  exit_code INTEGER NOT NULL,
  artifact_path TEXT,
  artifact_sha256 VARCHAR(64),
  actor VARCHAR(191) NOT NULL,
  created_at VARCHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_feature ON evidence(feature_id, name);
CREATE TABLE IF NOT EXISTS bites (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  node_id VARCHAR(512) NOT NULL,
  feature_id VARCHAR(128),
  generation INTEGER,
  phase VARCHAR(64),
  verdict VARCHAR(32) NOT NULL,
  reason TEXT,
  actor VARCHAR(191),
  created_at VARCHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bites_node ON bites(node_id);
CREATE INDEX IF NOT EXISTS idx_bites_feature ON bites(feature_id, generation);
CREATE TABLE IF NOT EXISTS judge_history (
  id VARCHAR(128) PRIMARY KEY,
  work_item_id VARCHAR(512) NOT NULL,
  feature_id VARCHAR(128) NOT NULL,
  generation INTEGER NOT NULL,
  kind VARCHAR(64) NOT NULL,
  verdict VARCHAR(32) NOT NULL,
  reason TEXT,
  actor VARCHAR(191) NOT NULL,
  judged_at VARCHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_judge_history_item ON judge_history(work_item_id);
CREATE TABLE IF NOT EXISTS changes (
  id VARCHAR(128) PRIMARY KEY,
  feature_id VARCHAR(128) NOT NULL,
  from_generation INTEGER NOT NULL,
  to_generation INTEGER NOT NULL,
  from_condition VARCHAR(64) NOT NULL,
  statement TEXT NOT NULL,
  affected_json LONGTEXT NOT NULL DEFAULT '[]',
  created_at VARCHAR(64) NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_changes_feature ON changes(feature_id, to_generation);
"""


# PostgreSQL：AUTOINCREMENT 换 BIGSERIAL；TEXT 主键、部分唯一索引、ON CONFLICT 都与 SQLite 兼容。
PG_SCHEMA_SQL = SCHEMA_SQL.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")

#: 索引和建表必须分两步跑。旧库的表可能缺「迁移才补的列」（bites.generation、
#: work_items.generation 等），而 idx_bites_feature 就建在 generation 上——
#: 先跑完整 DDL 会在建索引这一步直接 `no such column: generation`，
#: migrate_schema 还没轮到执行，0.4.x 的库永久卡死。顺序改成：
#: 建表（IF NOT EXISTS 对已有表是 no-op）→ 补列 → 建索引。
_INDEX_STATEMENT = re.compile(r"^[ \t]*CREATE INDEX IF NOT EXISTS [^;]*;[ \t]*$", re.MULTILINE)


def _split_schema(sql: str) -> tuple[str, str]:
    indexes = "\n".join(match.group(0).strip() for match in _INDEX_STATEMENT.finditer(sql))
    tables = _INDEX_STATEMENT.sub("", sql)
    return tables, indexes


SCHEMA_TABLES_SQL, SCHEMA_INDEXES_SQL = _split_schema(SCHEMA_SQL)
MYSQL_TABLES_SQL, MYSQL_INDEXES_SQL = _split_schema(MYSQL_SCHEMA_SQL)
PG_TABLES_SQL, PG_INDEXES_SQL = _split_schema(PG_SCHEMA_SQL)


class _NoopCursor:
    rowcount = 0

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def close(self):
        return None


def _mysql_translate(sql: str) -> str:
    text = sql
    # meta.key / value 在 MySQL 里是保留/易冲突标识符
    text = text.replace("meta(key, value)", "meta(`key`, `value`)")
    text = text.replace("SELECT value FROM meta WHERE key=?", "SELECT `value` FROM meta WHERE `key`=?")
    text = text.replace("SET value=excluded.value", "SET `value`=excluded.value")
    text = text.replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
    text = re.sub(
        r"ON CONFLICT\([^)]*\)\s+DO\s+UPDATE\s+SET",
        "ON DUPLICATE KEY UPDATE",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"excluded\.([A-Za-z_][A-Za-z0-9_]*)", r"VALUES(\1)", text)
    text = text.replace("ON CONFLICT DO NOTHING", "")
    return text


class _MySQLConnection:
    dialect = "mysql"

    def __init__(self, conn):
        self._conn = conn
        # 工单领取是“先读候选、再条件 UPDATE”：READ COMMITTED 避免 REPEATABLE READ
        # 下并发改写触发 1020（record has changed since last read）。
        conn.execute("SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED").close()

    def execute(self, sql: str, params=()):
        text = sql.strip()
        match = re.match(r"PRAGMA\s+table_info\((\w+)\)", text, re.IGNORECASE)
        if match:
            return self._conn.execute(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema=DATABASE() AND table_name=?",
                (match.group(1),),
            )
        if text.upper().startswith("PRAGMA"):
            return _NoopCursor()
        if isinstance(params, dict):
            sql, params = _named_params(sql, params)
        return self._conn.execute(_mysql_translate(sql), params)

    def executemany(self, sql: str, seq_of_params):
        """批量写：底层客户端没有 executemany，逐条走 execute。

        这里要的是「能用」不是吞吐；翻译、PRAGMA 处理、命名参数都复用 execute
        的统一路径，避免第二份实现分叉。此前这个方法根本不存在，import-file /
        import-repo 在 MySQL 上 100% AttributeError。
        """
        cursor: object = _NoopCursor()
        for params in seq_of_params:
            cursor = self.execute(sql, params)
        return cursor

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self._conn.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


class _PgConnection:
    dialect = "postgres"

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql: str, params=()):
        text = sql.strip()
        match = re.match(r"PRAGMA\s+table_info\((\w+)\)", text, re.IGNORECASE)
        if match:
            return self._conn.execute(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema=current_schema() AND table_name=%s",
                (match.group(1),),
            )
        if text.upper().startswith("PRAGMA"):
            return _NoopCursor()
        if isinstance(params, dict):
            sql, params = _named_params(sql, params)
        has_params = bool(params)
        # 无参数时传 None：psycopg 就不做 % 插值，字面量里的 % 才不用转义
        return self._conn.execute(_pg_translate(sql, has_params), params if has_params else None)

    def executemany(self, sql: str, seq_of_params):
        """批量写：逐条走 execute，理由同 _MySQLConnection.executemany。"""
        cursor: object = _NoopCursor()
        for params in seq_of_params:
            cursor = self.execute(sql, params)
        return cursor

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            statement = statement.strip()
            if statement:
                self._conn.execute(statement)

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def _pg_placeholders(sql: str, has_params: bool) -> str:
    """引号外的 `?` 换成 `%s`；有参数时把字面量 `%` 转义成 `%%`。

    旧实现是一行 ``sql.replace("?", "%s")``，两个后果都实测过：
    字符串字面量里的 ``?`` 也被换掉（``'status?'`` 变成 ``'status%s'``），
    而 ``'100%'`` 会被 psycopg 当成占位符，报 placeholder 数量不符。
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    length = len(sql)
    while i < length:
        ch = sql[i]
        if quote is not None:
            # psycopg 的 %s 替换不看 SQL 引号，所以引号内的 % 同样要转义；
            # 但引号内的 ? 是普通字符，不能换。
            if ch == quote:
                out.append(ch)
                if i + 1 < length and sql[i + 1] == quote:  # '' / "" 转义
                    out.append(sql[i + 1])
                    i += 2
                    continue
                quote = None
            elif ch == "%" and has_params:
                out.append("%%")
            else:
                out.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
        elif ch == "?":
            out.append("%s")
        elif ch == "%":
            out.append("%%" if has_params else "%")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _pg_translate(sql: str, has_params: bool = True) -> str:
    text = sql
    if "INSERT OR IGNORE INTO" in text:
        text = text.replace("INSERT OR IGNORE INTO", "INSERT INTO")
        text = text.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    # psycopg 用 %s 占位符
    return _pg_placeholders(text, has_params)


def _named_params(sql: str, params: dict) -> tuple[str, tuple]:
    """把 sqlite 风格的 :name 命名占位符改成 ? 位置参数（各后端再自行换成自己的占位符）。"""
    ordered: list = []

    def repl(match):
        key = match.group(1)
        if key not in params:
            raise Reject(f"缺少 SQL 参数：{key}")
        ordered.append(params[key])
        return "?"

    return re.sub(r":([A-Za-z_][A-Za-z0-9_]*)", repl, sql), tuple(ordered)


def db_url() -> str:
    return os.environ.get("WXG_DB_URL", "").strip()


def db_backend() -> str:
    url = db_url()
    if not url:
        return "sqlite"
    scheme = url.split(":", 1)[0].lower()
    if scheme in ("mysql", "mariadb"):
        return "mysql"
    if scheme in ("postgresql", "postgres"):
        return "postgres"
    raise Reject(f"不支持的 WXG_DB_URL 协议：{scheme}；内置 sqlite / mysql（MariaDB）/ postgres 后端")


def connect(root: Path):
    backend = db_backend()
    if backend == "mysql":
        import wxg_mysql  # 同目录的纯标准库客户端；仅在 mysql 后端时加载

        return _MySQLConnection(wxg_mysql.connect(db_url()))
    if backend == "postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise Reject("PostgreSQL 后端需要 psycopg：pip install 'psycopg[binary]'") from exc
        try:
            conn = psycopg.connect(db_url(), row_factory=dict_row, connect_timeout=5)
        except Exception as exc:  # 连接参数/服务不可用都转成可读错误
            raise Reject(f"PostgreSQL 连接失败：{exc}") from exc
        return _PgConnection(conn)
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / "graph.sqlite", timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    # WAL：读不阻塞写、写不阻塞读；同一时刻仍只有一个写者，多代理的短写排队即可。
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


#: 状态库必须齐全的表；缺任何一张都说明没 init 过，或建库中途失败。
REQUIRED_TABLES = (
    "meta", "repos", "nodes", "edges", "features", "conditions",
    "work_items", "feature_nodes", "evidence", "bites", "judge_history", "changes",
)

#: 迁移才补的列。旧库缺这些列是「schema 落后」而不是「没初始化」——
#: 两者要给出不同的修复动作：init 会就地补列，重建库会丢数据。
REQUIRED_COLUMNS = {
    "work_items": ("claimed_by", "judged_by", "judged_at", "claimed_at"),
    "evidence": ("generation",),
    "features": ("coverage_epsilon", "drift_limit", "conformance"),
    "nodes": ("stale",),
    "bites": ("generation", "phase"),
}


def _existing_tables(conn) -> set[str]:
    dialect = getattr(conn, "dialect", "sqlite")
    if dialect == "mysql":
        rows = conn.execute(
            "SELECT table_name AS name FROM information_schema.tables WHERE table_schema=DATABASE()"
        ).fetchall()
    elif dialect == "postgres":
        rows = conn.execute(
            "SELECT table_name AS name FROM information_schema.tables WHERE table_schema=current_schema()"
        ).fetchall()
    else:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row["name"] for row in rows}


def ensure_db(conn) -> None:
    """确认状态库存在，且 schema 不是明显落后的旧版。

    以前只查 meta 表：缺表或缺列的库会等到后面某条 SQL 才炸成 OperationalError，
    用户看到的是「no such column: claimed_by」而不是「该跑 init 还是该修库」。
    """
    present = _existing_tables(conn)
    missing = [name for name in REQUIRED_TABLES if name not in present]
    if missing:
        raise Reject(f"状态库未初始化：缺表 {', '.join(missing)}；先运行 `wxg init`")
    lagging: list[str] = []
    for table, columns in REQUIRED_COLUMNS.items():
        actual = _table_columns(conn, table)
        lagging.extend(f"{table}.{column}" for column in columns if column not in actual)
    if lagging:
        raise Reject(
            f"状态库 schema 落后（缺列 {', '.join(lagging)}）；运行 `wxg init` 就地迁移，"
            "不要重建库，否则会丢已有节点与工单"
        )


def _table_columns(conn, table: str) -> set[str]:
    dialect = getattr(conn, "dialect", "sqlite")
    if dialect in ("mysql", "postgres"):
        schema_expr = "DATABASE()" if dialect == "mysql" else "current_schema()"
        rows = conn.execute(
            "SELECT column_name AS name FROM information_schema.columns "
            f"WHERE table_schema={schema_expr} AND table_name=?",
            (table,),
        ).fetchall()
        return {row["name"] for row in rows}
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _is_integrity_error(exc: BaseException) -> bool:
    if isinstance(exc, sqlite3.IntegrityError):
        return True
    if getattr(exc, "errno", None) in (1022, 1062, 1169, 1557):
        return True
    return str(getattr(exc, "sqlstate", "")).startswith("23")



def _concat_prefix(dialect: str, prefix: str, column: str) -> str:
    """跨后端的「前缀 + 列」拼接 SQL 片段。

    MariaDB 的 ``||`` 是逻辑或（除非开了 PIPES_AS_CONCAT），``'jh:' || w.id``
    会求值成 0；回填出来的历史全部撞到同一个 id，``OR IGNORE`` 下静默只剩第一条。
    PostgreSQL 与 SQLite 里 ``||`` 才是字符串拼接。
    """
    if dialect == "mysql":
        return f"CONCAT('{prefix}', {column})"
    return f"'{prefix}' || {column}"


def migrate_schema(conn: sqlite3.Connection) -> dict:
    """把旧状态库非破坏地补到当前 schema；只迁移一次，重复 init 不再改已有行。

    旧库没有 actor 列时，对当时已存在且非 audit 的工单标 `legacy`（不伪造成员）；
    全新库创建时列已存在，因此不会被“迁移”误标。
    """
    migrated: dict[str, int] = {}
    columns = _table_columns(conn, "work_items")
    added: list[str] = []
    for name, ddl in (
        ("claimed_by", "ALTER TABLE work_items ADD COLUMN claimed_by TEXT"),
        ("judged_by", "ALTER TABLE work_items ADD COLUMN judged_by TEXT"),
        ("judged_at", "ALTER TABLE work_items ADD COLUMN judged_at TEXT"),
        ("claimed_at", "ALTER TABLE work_items ADD COLUMN claimed_at TEXT"),
    ):
        if name not in columns:
            conn.execute(ddl)
            added.append(name)
            migrated[f"work_items.{name}"] = 1
    if _table_columns(conn, "evidence") != set() and "generation" not in _table_columns(conn, "evidence"):
        # 0.4.0 之前 evidence 是 feature 级；升级后补 generation：
        # 优先用已关联工单的真实 generation，其次才按 feature 当前代回填（旧库无更多信息）。
        conn.execute("ALTER TABLE evidence ADD COLUMN generation INTEGER")
        conn.execute(
            "UPDATE evidence SET generation=COALESCE("
            "  (SELECT w.generation FROM work_items w WHERE w.id=evidence.work_item_id),"
            "  (SELECT f.generation FROM features f WHERE f.id=evidence.feature_id)"
            ") WHERE generation IS NULL"
        )
        migrated["evidence.generation"] = 1
    if "coverage_epsilon" not in _table_columns(conn, "features"):
        conn.execute("ALTER TABLE features ADD COLUMN coverage_epsilon REAL")
        migrated["features.coverage_epsilon"] = 1
    if "drift_limit" not in _table_columns(conn, "features"):
        conn.execute("ALTER TABLE features ADD COLUMN drift_limit INTEGER")
        migrated["features.drift_limit"] = 1
    if "conformance" not in _table_columns(conn, "features"):
        conn.execute("ALTER TABLE features ADD COLUMN conformance INTEGER NOT NULL DEFAULT 0")
        migrated["features.conformance"] = 1
    if "stale" not in _table_columns(conn, "nodes"):
        conn.execute("ALTER TABLE nodes ADD COLUMN stale INTEGER NOT NULL DEFAULT 0")
        migrated["nodes.stale"] = 1
    bite_columns = _table_columns(conn, "bites")
    if "generation" not in bite_columns:
        conn.execute("ALTER TABLE bites ADD COLUMN generation INTEGER")
        # 旧咬合没有代信息；按 feature 当前代回填，并在 CHANGELOG 里说明这层不确定性。
        conn.execute(
            "UPDATE bites SET generation=(SELECT f.generation FROM features f WHERE f.id=bites.feature_id) "
            "WHERE generation IS NULL"
        )
        migrated["bites.generation"] = 1
    if "phase" not in bite_columns:
        conn.execute("ALTER TABLE bites ADD COLUMN phase TEXT")
        migrated["bites.phase"] = 1
    if "claimed_by" in added:
        # 旧库的 claimed_by 只能标 legacy；audit 工单从不经过 work-claim，不参与。
        statuses = ("claimed", "submitted", "passed", "failed")
        marks = ",".join("?" for _ in statuses)
        changed = conn.execute(
            f"UPDATE work_items SET claimed_by='legacy' "
            f"WHERE claimed_by IS NULL AND kind<>'audit' AND status IN ({marks})",
            statuses,
        ).rowcount
        if changed:
            migrated["claimed_by.legacy"] = changed
    if "judged_by" in added:
        changed = conn.execute(
            "UPDATE work_items SET judged_by='legacy', judged_at=COALESCE(judged_at, created_at) "
            "WHERE judged_by IS NULL AND kind<>'audit' AND status IN ('passed','failed')"
        ).rowcount
        if changed:
            migrated["judged_by.legacy"] = changed
    if "claimed_at" in added:
        # 旧库没有领取时间；claimed 行按 created_at 回填（只是下界，无法还原真实领取时刻）。
        conn.execute("UPDATE work_items SET claimed_at=created_at WHERE status='claimed' AND claimed_at IS NULL")
    # 0.5.0：裁决历史独立成表。旧库按现状回填一次（幂等：确定性 id + OR IGNORE）。
    # id 前缀必须按方言拼：MariaDB 里 || 是逻辑或，'jh:' || w.id 求值为 0，
    # 回填的历史会全部撞到 id='0'，OR IGNORE 下静默只剩一条。
    dialect = getattr(conn, "dialect", "sqlite")
    conn.execute(
        "INSERT OR IGNORE INTO judge_history(id, work_item_id, feature_id, generation, kind, verdict, reason, actor, judged_at) "
        f"SELECT {_concat_prefix(dialect, 'jh:', 'w.id')}, w.id, w.feature_id, w.generation, w.kind, "
        "       CASE w.status WHEN 'passed' THEN 'passed' ELSE 'failed' END, "
        "       w.fail_reason, COALESCE(w.judged_by, 'legacy'), COALESCE(w.judged_at, w.created_at) "
        "FROM work_items w WHERE w.judged_by IS NOT NULL AND w.kind<>'audit' "
        "AND NOT EXISTS (SELECT 1 FROM judge_history h WHERE h.work_item_id=w.id)"
    )
    for key, value in (("schema_version", str(C.SCHEMA_VERSION)), ("contract_version", C.CONTRACT_VERSION)):
        row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        if row is None or row["value"] != value:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )
            migrated["meta"] = migrated.get("meta", 0) + 1
    return migrated


def init_db(conn) -> dict:
    dialect = getattr(conn, "dialect", "sqlite")
    if dialect == "mysql":
        tables, indexes = MYSQL_TABLES_SQL, MYSQL_INDEXES_SQL
    elif dialect == "postgres":
        tables, indexes = PG_TABLES_SQL, PG_INDEXES_SQL
    else:
        tables, indexes = SCHEMA_TABLES_SQL, SCHEMA_INDEXES_SQL
    conn.executescript(tables)
    migrated = migrate_schema(conn)
    # 索引最后建：它可能引用迁移才补的列（idx_bites_feature 建在 bites.generation 上）
    conn.executescript(indexes)
    conn.commit()
    return migrated


