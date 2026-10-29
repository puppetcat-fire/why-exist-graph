#!/usr/bin/env python3
"""wxg — why-exist-graph 的 DSH 原生实现。

一个技能、一个 CLI、一个状态库、一份契约（wxg_contract.py）。
详细设计见技能目录下的 references/design.md；契约视图由 `wxg contract` 生成。

只依赖 Python 3.10+ 标准库：sqlite3、argparse、ast、json、random、uuid。
"""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import sys
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(HERE))

import wxg_contract as C  # noqa: E402

DEFAULT_ROOT = Path.cwd() / ".why-exist"


# ------------------------------------------------------------------ 基础工具

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def loads(text, default):
    if text is None or text == "":
        return default
    if isinstance(text, (list, dict, int, float, bool)):
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise Reject(f"JSON 解析失败：{exc}") from exc


def load_json_arg(text: str):
    if text.startswith("@"):
        path = Path(text[1:])
        try:
            raw = path.read_text(encoding="utf-8-sig")
        except OSError as exc:
            raise Reject(f"JSON 文件无法读取：{path}（{exc.strerror or exc}）") from exc
        return loads(raw, None)
    return loads(text, None)


def new_token() -> str:
    return uuid.uuid4().hex


class Reject(Exception):
    """可预期的拒绝：CLI 以非零退出并输出原因。"""


# ------------------------------------------------------------------ 临时目录
#
# Windows 上 Python >= 3.12.4 为了 CVE-2024-4030，把 os.mkdir(path, 0o700) 的目录
# 建造成只有创建者的显式 DACL；在 DSH 的 windows-acl 沙箱（受限 token）里该 DACL
# 解析为空，目录创建者自己都写不进、删不掉（见 DSH discussion #4290）。
# 这里在 Windows 上改用默认 mode（继承父目录 ACL）建临时目录，POSIX 仍用 0o700。

def make_temp_dir(prefix: str = "wxg-") -> Path:
    base = Path(tempfile.gettempdir())
    for _ in range(100):
        path = base / (prefix + uuid.uuid4().hex)
        try:
            if os.name == "nt":
                path.mkdir()  # 默认 mode：继承可写 ACL，规避受限 token 下的空 DACL
            else:
                path.mkdir(mode=0o700)
        except FileExistsError:
            continue
        return path
    raise RuntimeError("无法创建临时目录")


@contextlib.contextmanager
def temp_dir(prefix: str = "wxg-"):
    path = make_temp_dir(prefix)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


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
  unmapped INTEGER NOT NULL DEFAULT 0
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
  verdict TEXT NOT NULL,
  reason TEXT,
  actor TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_bites_node ON bites(node_id);
"""


def connect(root: Path) -> sqlite3.Connection:
    root.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(root / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_db(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'").fetchone()
    if row is None:
        raise Reject("状态库未初始化：先运行 `wxg init`")


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


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


def init_db(conn: sqlite3.Connection) -> dict:
    conn.executescript(SCHEMA_SQL)
    migrated = migrate_schema(conn)
    conn.commit()
    return migrated


def actor_value(args, *, required: bool = True) -> str:
    raw = getattr(args, "actor", None) or os.environ.get("WXG_ACTOR") or ""
    actor = str(raw).strip()
    if not actor and required:
        raise Reject("缺少 --actor（或 WXG_ACTOR）；审计与领取必须记录执行者")
    if actor and not re.fullmatch(r"[^\s]{1,80}", actor):
        raise Reject("actor 必须是 1-80 个非空白字符")
    return actor


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def evidence_qualifies(conn, feature_id: str, generation: int) -> bool:
    """BehaviorPassed 采信的 evidence：同代、exit_code=0，且产物仍存在/ hash 未变。"""
    rows = conn.execute(
        "SELECT artifact_path, artifact_sha256 FROM evidence "
        "WHERE feature_id=? AND generation=? AND exit_code=0",
        (feature_id, generation),
    ).fetchall()
    for row in rows:
        path = row["artifact_path"]
        if path:
            artifact = Path(path)
            if not artifact.is_file():
                continue
            if row["artifact_sha256"] and sha256_file(artifact) != row["artifact_sha256"]:
                continue
        return True
    return False


# ------------------------------------------------------------------ 校验

def check_kind(kind: str) -> None:
    if kind not in [entry["kind"] for entry in C.NODE_KINDS]:
        raise Reject(f"未知节点 kind：{kind}")


def check_attrs(kind: str, attrs) -> dict:
    if attrs is None:
        return {}
    if not isinstance(attrs, dict):
        raise Reject("attrs 必须是 JSON 对象")
    allowed = C.ATTR_SCHEMA.get(kind, {})
    out = {}
    for key, value in attrs.items():
        if key == "bite":
            # attrs.bite 是只读投影：只能由 bite 命令写，否则任何拿到 token 的角色
            # 都能用 upsert-node 伪造 KEEP 反证（审计轨迹绕过）。
            raise Reject("attrs.bite 只能由 `bite` 命令写入；图写入命令不允许写该键")
        if key in allowed or key.startswith("x_"):
            expected = allowed.get(key)
            if expected == "str" and not isinstance(value, str):
                raise Reject(f"attrs.{key} 必须是字符串")
            if expected == "int" and not isinstance(value, int):
                raise Reject(f"attrs.{key} 必须是整数")
            if expected == "bool" and not isinstance(value, bool):
                raise Reject(f"attrs.{key} 必须是布尔")
            out[key] = value
        else:
            raise Reject(f"kind={kind} 不允许属性键 {key}；自定义键请用 x_ 前缀")
    return out


def check_node_id(kind: str, node_id: str) -> None:
    if ":" not in node_id:
        raise Reject(f"节点 id 必须形如 kind:...：{node_id}")
    prefix = node_id.split(":", 1)[0]
    if prefix != kind:
        raise Reject(f"节点 id 前缀 {prefix} 与 kind {kind} 不一致")
    if not re.fullmatch(r"[A-Za-z0-9._:\-@/]+", node_id):
        raise Reject(f"节点 id 含非法字符：{node_id}")


# ------------------------------------------------------------------ 仓

def repo_rows(conn):
    return [dict(row) for row in conn.execute("SELECT * FROM repos ORDER BY id").fetchall()]


def find_repo(conn, file_path: Path):
    absolute = file_path.resolve()
    matches = []
    for row in repo_rows(conn):
        base = Path(row["path"]).resolve()
        try:
            absolute.relative_to(base)
        except ValueError:
            continue
        matches.append((len(str(base)), row))
    if not matches:
        raise Reject(f"文件不在任何已登记仓内：{absolute}；先用 repo-add 登记仓")
    return max(matches, key=lambda item: item[0])[1]


# ------------------------------------------------------------------ 节点/边写入

def get_node(conn, node_id: str):
    row = conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
    return dict(row) if row else None


def upsert_node(conn, payload: dict, merge_attrs: bool = False) -> dict:
    node_id = payload.get("id")
    kind = payload.get("kind")
    if not node_id or not kind:
        raise Reject("节点缺少 id 或 kind")
    check_kind(kind)
    check_node_id(kind, node_id)
    incoming = check_attrs(kind, payload.get("attrs") or {})
    existing = get_node(conn, node_id)
    if merge_attrs and existing is not None:
        # 扫描/观察重导入只刷新扫描自身产生的属性，保留设计角色手工写入的
        # duty / x_note / x_* 等标注，避免 observe 重扫静默覆盖设计正文。
        attrs = loads(existing["attrs_json"], {})
        if not isinstance(attrs, dict):
            attrs = {}
        attrs.update(incoming)
    else:
        attrs = incoming
    row = {
        "id": node_id,
        "kind": kind,
        "name": payload.get("name", existing["name"] if existing else ""),
        "repo": payload.get("repo", existing["repo"] if existing else None),
        "path": payload.get("path", existing["path"] if existing else None),
        "symbol": payload.get("symbol", existing["symbol"] if existing else None),
        "line_start": payload.get("line_start", existing["line_start"] if existing else None),
        "line_end": payload.get("line_end", existing["line_end"] if existing else None),
        "attrs_json": dumps(attrs),
        "origin": payload.get("origin", existing["origin"] if existing else "manual"),
        "unmapped": 1 if payload.get("unmapped") else 0,
    }
    conn.execute(
        """INSERT INTO nodes (id, kind, name, repo, path, symbol, line_start, line_end, attrs_json, origin, unmapped)
           VALUES (:id, :kind, :name, :repo, :path, :symbol, :line_start, :line_end, :attrs_json, :origin, :unmapped)
           ON CONFLICT(id) DO UPDATE SET
             kind=excluded.kind, name=excluded.name, repo=excluded.repo, path=excluded.path,
             symbol=excluded.symbol, line_start=excluded.line_start, line_end=excluded.line_end,
             attrs_json=excluded.attrs_json, origin=excluded.origin, unmapped=excluded.unmapped""",
        row,
    )
    feature_id = payload.get("feature_id")
    if feature_id:
        conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (feature_id, node_id))
    return {"action": "update" if existing else "insert", "id": node_id}


def edge_id(kind: str, src: str, dst: str) -> str:
    return f"edge:{kind}:{src}:{dst}"


def upsert_edge(conn, payload: dict) -> dict:
    src = payload.get("src")
    dst = payload.get("dst")
    kind = payload.get("kind")
    if not src or not dst or not kind:
        raise Reject("边缺少 src/dst/kind")
    if kind not in [entry["kind"] for entry in C.EDGE_KINDS]:
        raise Reject(f"未知边 kind：{kind}")
    if get_node(conn, src) is None:
        raise Reject(f"边的 src 不存在：{src}")
    if get_node(conn, dst) is None:
        raise Reject(f"边的 dst 不存在：{dst}")
    eid = payload.get("id") or edge_id(kind, src, dst)
    conn.execute(
        """INSERT INTO edges (id, src, dst, kind, evidence_path, evidence_line, unmapped, attrs_json)
           VALUES (?,?,?,?,?,?,?,?)
           ON CONFLICT(id) DO UPDATE SET
             src=excluded.src, dst=excluded.dst, kind=excluded.kind,
             evidence_path=excluded.evidence_path, evidence_line=excluded.evidence_line,
             unmapped=excluded.unmapped, attrs_json=excluded.attrs_json""",
        (
            eid,
            src,
            dst,
            kind,
            payload.get("evidence_path"),
            payload.get("evidence_line"),
            1 if payload.get("unmapped") else 0,
            dumps(payload.get("attrs") or {}),
        ),
    )
    return {"action": "upsert", "id": eid}


def bind_node(conn, node_id: str, bind_to: str, edge_kind: str | None = None) -> dict:
    node = get_node(conn, node_id)
    if node is None:
        raise Reject(f"节点不存在：{node_id}")
    if node["kind"] not in C.BIND_EDGE_KIND:
        raise Reject(f"只有 parameter/argument/assertion 可以 bind：{node['kind']}")
    if get_node(conn, bind_to) is None:
        raise Reject(f"bind 目标不存在：{bind_to}")
    kind = edge_kind or C.BIND_EDGE_KIND[node["kind"]]
    if kind not in [entry["kind"] for entry in C.EDGE_KINDS]:
        raise Reject(f"未知边 kind：{kind}")
    # has_input / has_output 的主语是 operation，has_argument 的主语是 message，
    # asserts 的主语是 assertion 自己。方向与 SCHEMA 的语义保持一致。
    if node["kind"] in ("parameter", "argument"):
        src, dst = bind_to, node_id
    else:
        src, dst = node_id, bind_to
    eid = edge_id(kind, src, dst)
    conn.execute(
        "INSERT INTO edges (id, src, dst, kind, unmapped, attrs_json) VALUES (?,?,?,?,0,'{}') "
        "ON CONFLICT(id) DO UPDATE SET kind=excluded.kind",
        (eid, src, dst, kind),
    )
    return {"action": "bind", "id": eid}


# ------------------------------------------------------------------ feature / 条件

def get_feature(conn, feature_id: str):
    row = conn.execute("SELECT * FROM features WHERE id=?", (feature_id,)).fetchone()
    return dict(row) if row else None


def ensure_feature(conn, feature_id: str) -> dict:
    feature = get_feature(conn, feature_id)
    if feature is None:
        raise Reject(f"feature 不存在：{feature_id}")
    return feature


def condition_rows(conn, feature: dict):
    rows = conn.execute(
        "SELECT name, status, reason FROM conditions WHERE feature_id=? AND generation=?",
        (feature["id"], feature["generation"]),
    ).fetchall()
    return {row["name"]: {"status": row["status"], "reason": row["reason"]} for row in rows}


def condition_flags(conn, feature: dict) -> dict:
    rows = condition_rows(conn, feature)
    if len(rows) != len(C.CONDITIONS):
        raise Reject(f"feature {feature['id']} 第 {feature['generation']} 代条件不齐；重新声明或登记")
    return {name: rows[name]["status"] for name in C.CONDITIONS}


def set_condition(conn, feature_id: str, generation: int, name: str, status: int, reason: str | None = None) -> None:
    conn.execute(
        "UPDATE conditions SET status=?, reason=? WHERE feature_id=? AND generation=? AND name=?",
        (status, reason, feature_id, generation, name),
    )


def recompute_ready(conn, feature_id: str, generation: int) -> int:
    rows = conn.execute(
        "SELECT name, status FROM conditions WHERE feature_id=? AND generation=?",
        (feature_id, generation),
    ).fetchall()
    flags = {row["name"]: row["status"] for row in rows}
    ready = int(all(flags.get(name) == 1 for name in C.CONDITIONS if name != "Ready")) and len(flags) == len(C.CONDITIONS)
    set_condition(conn, feature_id, generation, "Ready", 1 if ready else 0, "条件齐" if ready else None)
    return ready


def refresh_blocked(conn, feature_id: str, generation: int) -> None:
    items = conn.execute(
        "SELECT * FROM work_items WHERE feature_id=? AND generation=?", (feature_id, generation)
    ).fetchall()
    passed = {row["id"] for row in items if row["status"] == "passed"}
    for item in items:
        if item["status"] not in ("blocked",):
            continue
        deps = loads(item["depends_on"], [])
        if all(dep in passed for dep in deps):
            conn.execute("UPDATE work_items SET status='ready' WHERE id=?", (item["id"],))


def scope_ids(conn, feature_id: str) -> list[str]:
    ids = []
    seen = set()
    existing = {row["id"] for row in conn.execute("SELECT id FROM nodes").fetchall()}

    def add(node_id):
        if node_id in existing and node_id not in seen:
            seen.add(node_id)
            ids.append(node_id)

    for row in conn.execute("SELECT node_id FROM feature_nodes WHERE feature_id=?", (feature_id,)).fetchall():
        add(row["node_id"])
    prefix = f"requirement:{feature_id}:"
    for row in conn.execute("SELECT id FROM nodes").fetchall():
        if row["id"].startswith(prefix):
            add(row["id"])
    feature = get_feature(conn, feature_id)
    if feature is not None:
        for row in conn.execute(
            "SELECT target_ids FROM work_items WHERE feature_id=? AND generation=?",
            (feature_id, feature["generation"]),
        ).fetchall():
            for pattern in loads(row["target_ids"], []):
                if pattern.endswith("*"):
                    prefix = pattern[:-1]
                    for node in existing:
                        if node.startswith(prefix):
                            add(node)
                else:
                    add(pattern)
    return ids


# ------------------------------------------------------------------ 工单

def work_id(feature_id: str, generation: int, kind: str) -> str:
    return f"work:{feature_id}:g{generation}:{kind}"


def get_work(conn, item_id: str):
    row = conn.execute("SELECT * FROM work_items WHERE id=?", (item_id,)).fetchone()
    return dict(row) if row else None


def get_work_by_token(conn, token: str):
    row = conn.execute("SELECT * FROM work_items WHERE claim_token=?", (token,)).fetchone()
    return dict(row) if row else None


def insert_work(conn, feature_id: str, generation: int, kind: str, targets: list[str], depends_on: list[str] | None, merge: bool = False) -> dict:
    wid = work_id(feature_id, generation, kind)
    existing = get_work(conn, wid)
    if existing is None:
        conn.execute(
            """INSERT INTO work_items (id, feature_id, generation, kind, role, target_ids, status, depends_on, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                wid,
                feature_id,
                generation,
                kind,
                kind,
                dumps(targets),
                "ready",
                dumps(depends_on or []),
                utc_now(),
            ),
        )
        return {"action": "insert", "id": wid}
    if merge:
        if existing["status"] not in ("ready", "claimed", "blocked"):
            raise Reject(f"工单状态是 {existing['status']}，不能并入 target_ids")
        current = loads(existing["target_ids"], [])
        seen = set(current)
        for node_id in targets:
            if node_id not in seen:
                seen.add(node_id)
                current.append(node_id)
        conn.execute("UPDATE work_items SET target_ids=? WHERE id=?", (dumps(current), wid))
        return {"action": "merge", "id": wid}
    conn.execute(
        "UPDATE work_items SET target_ids=?, depends_on=? WHERE id=?",
        (dumps(targets), dumps(depends_on or []), wid),
    )
    return {"action": "update", "id": wid}


def require_token(conn, token: str) -> dict:
    if not token:
        raise Reject("该命令需要 --token；先用 work-claim 领取工单")
    item = get_work_by_token(conn, token)
    if item is None:
        raise Reject("claim_token 无效")
    if item["status"] != "claimed":
        raise Reject(f"工单不是 claimed 状态：{item['status']}")
    return item


def require_role(item: dict, command: str) -> None:
    allowed = C.ROLES.get(item["role"], [])
    if command not in allowed:
        raise Reject(f"角色 {item['role']} 不能执行 {command}；允许：{allowed}")


def target_match(pattern: str, node_id: str) -> bool:
    if not isinstance(node_id, str):
        return False
    if pattern == node_id:
        return True
    return pattern.endswith("*") and node_id.startswith(pattern[:-1])


def require_targets(item: dict, node_ids: list[str]) -> None:
    patterns = loads(item["target_ids"], [])
    outside = [
        node_id
        for node_id in node_ids
        if not any(target_match(pattern, node_id) for pattern in patterns)
    ]
    if outside:
        raise Reject(f"以下 id 不在工单 target_ids 内：{outside[:5]}（共 {len(outside)} 个）")


def append_evidence(conn, item: dict, node_ids: list[str]) -> None:
    evidence = loads(item["evidence_ids"], [])
    seen = set(evidence)
    for node_id in node_ids:
        if node_id not in seen:
            seen.add(node_id)
            evidence.append(node_id)
    conn.execute("UPDATE work_items SET evidence_ids=? WHERE id=?", (dumps(evidence), item["id"]))
    item["evidence_ids"] = dumps(evidence)


# ------------------------------------------------------------------ 导入器（Python AST）

def _node_id(kind: str, repo: str, rel: str, symbol: str) -> str:
    return f"{kind}:{repo}:{rel}:{symbol}"


def plan_python(repo: dict, absolute: Path) -> tuple[dict, dict]:
    """返回 (nodes, edges)，都是 id -> payload 的字典。"""
    rel = absolute.resolve().relative_to(Path(repo["path"]).resolve()).as_posix()
    source = absolute.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Reject(f"Python 语法无法解析：{exc}") from exc
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(payload):
        nodes[payload["id"]] = payload
        return payload["id"]

    def add_edge(kind, src, dst, line=None, unmapped=False):
        if src not in nodes or dst not in nodes:
            return
        eid = edge_id(kind, src, dst)
        edges[eid] = {
            "id": eid,
            "kind": kind,
            "src": src,
            "dst": dst,
            "evidence_path": rel,
            "evidence_line": line,
            "unmapped": unmapped,
        }

    class_ops: dict[str, dict[str, str]] = {}

    for top in tree.body:
        if isinstance(top, ast.ClassDef):
            cid = add_node({
                "id": _node_id("classifier", repo["id"], rel, top.name),
                "kind": "classifier",
                "name": top.name,
                "repo": repo["id"],
                "path": rel,
                "symbol": top.name,
                "line_start": top.lineno,
                "line_end": getattr(top, "end_lineno", top.lineno),
                "attrs": {"x_lang": "python"},
                "origin": "scan",
            })
            class_ops[top.name] = {}
            for member in top.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbol = f"{top.name}.{member.name}"
                    oid = add_node({
                        "id": _node_id("operation", repo["id"], rel, symbol),
                        "kind": "operation",
                        "name": member.name,
                        "repo": repo["id"],
                        "path": rel,
                        "symbol": symbol,
                        "line_start": member.lineno,
                        "line_end": getattr(member, "end_lineno", member.lineno),
                        "attrs": {"x_lang": "python"},
                        "origin": "scan",
                    })
                    class_ops[top.name][member.name] = oid
                    add_edge("contains", cid, oid, member.lineno)
                elif isinstance(member, ast.Assign):
                    for target in member.targets:
                        if isinstance(target, ast.Name):
                            pid = add_node({
                                "id": _node_id("property", repo["id"], rel, f"{top.name}.{target.id}"),
                                "kind": "property",
                                "name": target.id,
                                "repo": repo["id"],
                                "path": rel,
                                "symbol": f"{top.name}.{target.id}",
                                "line_start": member.lineno,
                                "line_end": member.lineno,
                                "attrs": {"x_lang": "python"},
                                "origin": "scan",
                            })
                            add_edge("contains", cid, pid, member.lineno)
        elif isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            oid = add_node({
                "id": _node_id("operation", repo["id"], rel, top.name),
                "kind": "operation",
                "name": top.name,
                "repo": repo["id"],
                "path": rel,
                "symbol": top.name,
                "line_start": top.lineno,
                "line_end": getattr(top, "end_lineno", top.lineno),
                "attrs": {"x_lang": "python"},
                "origin": "scan",
            })

    def walk_calls(class_name: str | None, op_id: str, func: ast.AST):
        def unmapped_call(display: str, note: str, line, key: str | None = None):
            key = key or display
            target = _node_id("operation", repo["id"], rel, f"@{line}:{key}")
            if target not in nodes:
                add_node({
                    "id": target,
                    "kind": "operation",
                    "name": display,
                    "repo": repo["id"],
                    "path": rel,
                    "symbol": f"@{line}:{display}",
                    "line_start": line,
                    "line_end": line,
                    "attrs": {"x_note": note},
                    "origin": "scan",
                    "unmapped": 1,
                })
            add_edge("calls", op_id, target, line, unmapped=True)

        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            func_expr = node.func
            line = getattr(node, "lineno", None)
            if isinstance(func_expr, ast.Attribute) and isinstance(func_expr.value, ast.Name):
                receiver = func_expr.value.id
                name = func_expr.attr
                if receiver == "self" and class_name and name in class_ops.get(class_name, {}):
                    add_edge("calls", op_id, class_ops[class_name][name], line)
                else:
                    unmapped_call(f"{receiver}.{name}", "未解析的接收者调用", line)
            elif isinstance(func_expr, ast.Name):
                name = func_expr.id
                target = class_ops.get("__module__", {}).get(name)
                if target:
                    add_edge("calls", op_id, target, line)
                else:
                    candidate = _node_id("operation", repo["id"], rel, name)
                    if candidate in nodes:
                        add_edge("calls", op_id, candidate, line)
                    else:
                        # 裸名调用认不出（如内置函数/外部导入）：按 I7 建 unmapped 节点+边。
                        unmapped_call(name, "未解析的裸名调用", line)
            else:
                # 链式属性/下标/复杂表达式调用（如 self.conn.execute(...)、data['k'].append(...)）：
                # 同样认不出，按 I7 建 unmapped 节点+边，不静默丢弃。
                try:
                    display = ast.unparse(func_expr)
                except Exception:  # pragma: no cover - 防御性
                    display = type(func_expr).__name__
                # 节点 id 只允许安全字符：unparse 文本可能含 ()[]' 等，用清洗串+短 hash 防碰撞。
                safe = re.sub(r"[^A-Za-z0-9._@/\-]+", "_", display).strip("_")[:60] or "call"
                key = f"{safe}:{hashlib.sha1(display.encode('utf-8')).hexdigest()[:8]}"
                unmapped_call(display, "未解析的链式/复杂调用", line, key=key)

    module_ops: dict[str, str] = {}
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_ops[top.name] = _node_id("operation", repo["id"], rel, top.name)
    class_ops["__module__"] = module_ops

    # 第二遍：self.attr 赋值 -> property + writes；调用 -> calls
    for top in tree.body:
        if isinstance(top, ast.ClassDef):
            for member in top.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    op_id = class_ops[top.name][member.name]
                    for node in ast.walk(member):
                        if isinstance(node, ast.Assign):
                            for target in node.targets:
                                if (
                                    isinstance(target, ast.Attribute)
                                    and isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    pid = _node_id("property", repo["id"], rel, f"{top.name}.{target.attr}")
                                    if pid not in nodes:
                                        add_node({
                                            "id": pid,
                                            "kind": "property",
                                            "name": target.attr,
                                            "repo": repo["id"],
                                            "path": rel,
                                            "symbol": f"{top.name}.{target.attr}",
                                            "line_start": node.lineno,
                                            "line_end": node.lineno,
                                            "attrs": {"x_lang": "python"},
                                            "origin": "scan",
                                        })
                                    add_edge("writes", op_id, pid, node.lineno)
                    walk_calls(top.name, op_id, member)
        elif isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            walk_calls(None, module_ops[top.name], top)

    return nodes, edges


# ------------------------------------------------------------------ 命令实现

def cmd_init(conn, args):
    migrated = init_db(conn)
    return {
        "root": str(args.root_path),
        "db": str(args.root_path / "graph.sqlite"),
        "schema_version": C.SCHEMA_VERSION,
        "contract_version": C.CONTRACT_VERSION,
        "migrated": migrated,
    }


def cmd_repo_add(conn, args):
    path = Path(args.path).resolve()
    if not path.is_dir():
        raise Reject(f"仓路径不存在或不是目录：{path}")
    if args.language != "python":
        raise Reject("当前版本只内置 Python 导入器；repo-add --language 仅支持 python")
    try:
        conn.execute(
            "INSERT INTO repos(id, path, language, created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET path=excluded.path, language=excluded.language",
            (args.id, str(path), args.language, utc_now()),
        )
    except sqlite3.IntegrityError as exc:
        raise Reject(f"仓登记冲突：path {path} 已被其它 repo id 占用（{exc}）") from exc
    return {"action": "upsert", "repo": args.id, "path": str(path), "language": args.language}


def cmd_repo_list(conn, args):
    return {"repos": repo_rows(conn)}


def cmd_import_file(conn, args):
    absolute = Path(args.file).resolve()
    if not absolute.is_file():
        raise Reject(f"文件不存在：{absolute}")
    repo = find_repo(conn, absolute)
    if repo["language"] != "python":
        raise Reject(
            f"当前版本只内置 Python 导入器；仓 {repo['id']} 登记为 {repo['language']}，"
            "无法按文件导入。请改用 upsert-node/upsert-edge，或按 design.md 的边界扩展导入器"
        )
    nodes, edges = plan_python(repo, absolute)
    # 防御性校验：导入器生成的 id 必须合法；否则 prepare/写库都不应把非法 id 落进
    # target_ids / feature_nodes（否则 doctor 会报一堆 feature-node-missing）。
    for payload in nodes.values():
        check_kind(payload["kind"])
        check_node_id(payload["kind"], payload["id"])
    node_ids = sorted(nodes)
    if args.prepare:
        if not args.feature:
            raise Reject("--prepare 需要 --feature")
        feature = ensure_feature(conn, args.feature)
        opened = insert_work(conn, feature["id"], feature["generation"], "scan", node_ids, [], merge=True)
        for node_id in node_ids:
            conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (feature["id"], node_id))
        return {"mode": "prepare", "repo": repo["id"], "work": opened, "nodes": len(nodes), "edges": len(edges)}
    item = require_token(conn, args.token)
    require_role(item, "import-file")
    require_targets(item, node_ids)
    inserted = updated = edges_written = 0
    for node_id in node_ids:
        existed = get_node(conn, node_id) is not None
        upsert_node(conn, nodes[node_id], merge_attrs=True)
        inserted += 0 if existed else 1
        updated += 1 if existed else 0
        conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (item["feature_id"], node_id))
    for payload in edges.values():
        existed = conn.execute("SELECT 1 FROM edges WHERE id=?", (payload["id"],)).fetchone() is not None
        upsert_edge(conn, payload)
        edges_written += 0 if existed else 1
    append_evidence(conn, item, node_ids)
    return {
        "mode": "write",
        "repo": repo["id"],
        "nodes_inserted": inserted,
        "nodes_updated": updated,
        "edges_inserted": edges_written,
        "work": item["id"],
    }


def cmd_sample(conn, args):
    rows = conn.execute(
        "SELECT id, kind, name, repo, path, symbol, line_start FROM nodes WHERE repo=? ORDER BY id",
        (args.repo,),
    ).fetchall()
    if not rows:
        raise Reject(f"仓 {args.repo} 里还没有可抽取的节点，先 import-file")
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    row = rng.choice([dict(item) for item in rows])
    return {"sample": row, "seed": args.seed}


def cmd_feature_declare(conn, args):
    feature_id = args.id
    if not re.fullmatch(r"[A-Za-z0-9._-]+", feature_id):
        raise Reject("feature id 只能含字母、数字、点、下划线、连字符")
    acceptance = load_json_arg(args.acceptance)
    constraints = load_json_arg(args.constraints)
    if not isinstance(acceptance, list) or not isinstance(constraints, list):
        raise Reject("acceptance / constraints 必须是 JSON 数组")
    if not args.statement:
        raise Reject("statement 不能为空")
    old = get_feature(conn, feature_id)
    generation = (old["generation"] + 1) if old else 1
    if old:
        conn.execute(
            "UPDATE work_items SET status='superseded', claim_token=NULL, assignee=NULL "
            "WHERE feature_id=? AND generation=? AND status<>'superseded'",
            (feature_id, old["generation"]),
        )
        conn.execute(
            "INSERT INTO features(id, name, generation, statement, acceptance_json, constraints_json, created_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name, generation=excluded.generation, "
            "statement=excluded.statement, acceptance_json=excluded.acceptance_json, constraints_json=excluded.constraints_json",
            (feature_id, args.name, generation, args.statement, dumps(acceptance), dumps(constraints), utc_now()),
        )
    else:
        conn.execute(
            "INSERT INTO features(id, name, generation, statement, acceptance_json, constraints_json, created_at) VALUES(?,?,?,?,?,?,?)",
            (feature_id, args.name, generation, args.statement, dumps(acceptance), dumps(constraints), utc_now()),
        )
    for name in C.CONDITIONS:
        conn.execute(
            "INSERT INTO conditions(feature_id, generation, name, status, reason) VALUES(?,?,?,?,?)",
            (feature_id, generation, name, 1 if name == "Accepted" else 0, "声明受理" if name == "Accepted" else None),
        )
    requirement_id = f"requirement:{feature_id}:main"
    upsert_node(conn, {
        "id": requirement_id,
        "kind": "requirement",
        "name": args.statement,
        "attrs": {"statement": args.statement},
        "origin": "declared",
        "feature_id": feature_id,
    }, merge_attrs=True)
    seeded = work_seed(conn, feature_id)
    return {"feature_id": feature_id, "generation": generation, "accepted_only": True, "work_seed": seeded}


def cmd_feature_register(conn, args):
    """登记已有图。

    - 新 feature：只建元数据 + conditions（只置 Accepted）+ requirement 节点，不触发派工。
    - 已存在且未给 --generation：只更新 name/spec 与 requirement 节点正文，条件完全不动。
    - 显式 --generation 开新代：新代条件只置 Accepted，并 supersede 旧代工单（清 token），
      避免旧代 ready 工单被新代角色领走；不自动派工，需要时自行 work-seed。
    """
    feature_id = args.id
    if not re.fullmatch(r"[A-Za-z0-9._-]+", feature_id):
        raise Reject("feature id 只能含字母、数字、点、下划线、连字符")
    spec = load_json_arg(args.spec)
    if not isinstance(spec, dict) or not all(key in spec for key in ("statement", "acceptance", "constraints")):
        raise Reject("--spec 必须是含 statement/acceptance/constraints 的 JSON 对象")
    if not isinstance(spec["acceptance"], list) or not isinstance(spec["constraints"], list):
        raise Reject("--spec 的 acceptance / constraints 必须是 JSON 数组")
    if not isinstance(spec["statement"], str) or not spec["statement"]:
        raise Reject("--spec 的 statement 必须是非空字符串")
    if args.generation is not None and args.generation < 1:
        raise Reject("--generation 必须是正整数")

    def write_requirement() -> None:
        upsert_node(conn, {
            "id": f"requirement:{feature_id}:main",
            "kind": "requirement",
            "name": spec["statement"],
            "attrs": {"statement": spec["statement"]},
            "origin": "declared",
            "feature_id": feature_id,
        }, merge_attrs=True)

    old = get_feature(conn, feature_id)
    if old is None:
        generation = args.generation or 1
        conn.execute(
            "INSERT INTO features(id, name, generation, statement, acceptance_json, constraints_json, created_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (feature_id, args.name, generation, spec["statement"], dumps(spec["acceptance"]), dumps(spec["constraints"]), utc_now()),
        )
        for name in C.CONDITIONS:
            conn.execute(
                "INSERT INTO conditions(feature_id, generation, name, status, reason) VALUES(?,?,?,?,?)",
                (feature_id, generation, name, 1 if name == "Accepted" else 0, "登记" if name == "Accepted" else None),
            )
        write_requirement()
        return {
            "feature_id": feature_id,
            "generation": generation,
            "accepted_only": True,
            "conditions_untouched": False,
            "requirement_written": True,
        }

    if args.generation is None:
        conn.execute(
            "UPDATE features SET name=?, statement=?, acceptance_json=?, constraints_json=? WHERE id=?",
            (args.name, spec["statement"], dumps(spec["acceptance"]), dumps(spec["constraints"]), feature_id),
        )
        write_requirement()
        return {
            "feature_id": feature_id,
            "generation": old["generation"],
            "accepted_only": False,
            "conditions_untouched": True,
            "requirement_written": True,
        }

    if args.generation <= old["generation"]:
        raise Reject(f"--generation 必须大于当前 generation {old['generation']}")
    generation = args.generation
    conn.execute(
        "UPDATE work_items SET status='superseded', claim_token=NULL, assignee=NULL "
        "WHERE feature_id=? AND generation=? AND status<>'superseded'",
        (feature_id, old["generation"]),
    )
    conn.execute(
        "UPDATE features SET name=?, generation=?, statement=?, acceptance_json=?, constraints_json=? WHERE id=?",
        (args.name, generation, spec["statement"], dumps(spec["acceptance"]), dumps(spec["constraints"]), feature_id),
    )
    for name in C.CONDITIONS:
        conn.execute(
            "INSERT INTO conditions(feature_id, generation, name, status, reason) VALUES(?,?,?,?,?)",
            (feature_id, generation, name, 1 if name == "Accepted" else 0, "登记" if name == "Accepted" else None),
        )
    write_requirement()
    return {
        "feature_id": feature_id,
        "generation": generation,
        "accepted_only": True,
        "conditions_untouched": False,
        "requirement_written": True,
        "superseded_previous_generation": old["generation"],
    }


def cmd_feature_list(conn, args):
    rows = []
    for feature in conn.execute("SELECT * FROM features ORDER BY id").fetchall():
        feature = dict(feature)
        rows.append({
            "id": feature["id"],
            "name": feature["name"],
            "generation": feature["generation"],
            "conditions": condition_flags(conn, feature),
        })
    return {"features": rows}


def cmd_feature_status(conn, args):
    feature = ensure_feature(conn, args.id)
    items = conn.execute(
        "SELECT id, kind, status, target_ids, depends_on, claim_token, claimed_by, judged_by, judged_at "
        "FROM work_items WHERE feature_id=? AND generation=? ORDER BY id",
        (feature["id"], feature["generation"]),
    ).fetchall()
    bites = []
    scope = set(scope_ids(conn, feature["id"]))
    for row in conn.execute("SELECT node_id, verdict, reason, actor FROM bites ORDER BY id").fetchall():
        if row["node_id"] in scope:
            bites.append({"node_id": row["node_id"], "verdict": row["verdict"], "reason": row["reason"], "actor": row["actor"]})
    evidence = [
        dict(row)
        for row in conn.execute(
            "SELECT id, generation, name, command, exit_code, artifact_sha256, actor, created_at "
            "FROM evidence WHERE feature_id=? ORDER BY created_at, id",
            (feature["id"],),
        ).fetchall()
    ]
    return {
        "feature": {"id": feature["id"], "name": feature["name"], "generation": feature["generation"]},
        "conditions": condition_flags(conn, feature),
        "work_items": [dict(item) for item in items],
        "bites": bites,
        "evidence": evidence,
        "scope_size": len(scope),
    }


def work_seed(conn, feature_id: str) -> dict:
    feature = ensure_feature(conn, feature_id)
    generation = feature["generation"]
    flags = condition_flags(conn, feature)
    targets = scope_ids(conn, feature_id)
    created, existed = [], []
    prev = None
    for cond in C.CONDITIONS:
        if cond not in C.CONDITION_TO_KIND:
            continue
        kind = C.CONDITION_TO_KIND[cond]
        wid = work_id(feature_id, generation, kind)
        existing = get_work(conn, wid)
        if flags[cond] == 1:
            if existing is not None and existing["status"] == "passed":
                prev = wid
            continue
        depends = [prev] if prev else []
        status = "ready"
        if depends:
            dep = get_work(conn, depends[0])
            status = "ready" if dep is not None and dep["status"] == "passed" else "blocked"
        if existing is None:
            insert_work(conn, feature_id, generation, kind, targets, depends)
            conn.execute("UPDATE work_items SET status=? WHERE id=?", (status, wid))
            created.append({"id": wid, "kind": kind, "status": status, "depends_on": depends})
        else:
            existed.append({"id": wid, "kind": kind, "status": existing["status"]})
        prev = wid
    ready = conn.execute(
        "SELECT id, kind, status FROM work_items WHERE feature_id=? AND generation=? AND status='ready' ORDER BY id",
        (feature_id, generation),
    ).fetchall()
    return {"created": created, "existed": existed, "ready": [dict(row) for row in ready]}


def cmd_work_seed(conn, args):
    return work_seed(conn, args.feature)


def cmd_work_open(conn, args):
    feature = ensure_feature(conn, args.feature)
    if args.kind == "audit":
        raise Reject("audit 由 work-finish 自动生成")
    if args.kind not in C.WORK_KINDS:
        raise Reject(f"未知工单 kind：{args.kind}")
    targets = load_json_arg(args.target_ids)
    if not isinstance(targets, list):
        raise Reject("--target-ids 必须是 JSON 数组或 @文件")
    opened = insert_work(conn, feature["id"], feature["generation"], args.kind, targets, [], merge=True)
    return {"work": opened}


def cmd_work_claim(conn, args):
    if args.role not in C.ROLES:
        raise Reject(f"未知角色：{args.role}")
    if args.role == "audit":
        raise Reject("审计不领取工单；直接 work-judge")
    if args.role in C.PRODUCT_CODE_ROLES and not args.allow_product_code:
        raise Reject("当轮未明确允许改产品代码，不能领取 implement-test")
    actor = actor_value(args)
    candidates = conn.execute(
        "SELECT w.* FROM work_items w "
        "JOIN features f ON f.id=w.feature_id AND f.generation=w.generation "
        "WHERE w.role=? AND w.status='ready' ORDER BY w.id",
        (args.role,),
    ).fetchall()
    picked = None
    for row in candidates:
        deps = loads(row["depends_on"], [])
        if all(get_work(conn, dep) and get_work(conn, dep)["status"] == "passed" for dep in deps):
            picked = dict(row)
            break
    if picked is None:
        raise Reject(f"角色 {args.role} 没有可领的 ready 工单")
    token = new_token()
    conn.execute(
        "UPDATE work_items SET status='claimed', assignee=?, claimed_by=?, claim_token=? WHERE id=?",
        (args.role, actor, token, picked["id"]),
    )
    return {
        "work_item_id": picked["id"],
        "kind": picked["kind"],
        "role": args.role,
        "actor": actor,
        "claim_token": token,
        "target_ids": loads(picked["target_ids"], []),
        "slice": slice_payload(conn, loads(picked["target_ids"], [])),
    }


def cmd_work_finish(conn, args):
    item = require_token(conn, args.token)
    evidence = loads(item["evidence_ids"], [])
    patterns = loads(item["target_ids"], [])
    missed = [node_id for node_id in evidence if not any(target_match(pattern, node_id) for pattern in patterns)]
    if missed:
        raise Reject(f"evidence 里有 id 不在 target_ids：{missed[:5]}")
    conn.execute("UPDATE work_items SET status='submitted', claim_token=NULL WHERE id=?", (item["id"],))
    audit_id = f"work:{item['feature_id']}:g{item['generation']}:audit:{item['id']}"
    existing = conn.execute("SELECT status FROM work_items WHERE id=?", (audit_id,)).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO work_items(id, feature_id, generation, kind, role, target_ids, status, depends_on, created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (audit_id, item["feature_id"], item["generation"], "audit", "audit", dumps([item["id"]]), "ready", dumps([item["id"]]), utc_now()),
        )
    else:
        conn.execute("UPDATE work_items SET status='ready', depends_on=? WHERE id=?", (dumps([item["id"]]), audit_id))
    return {"work_item_id": item["id"], "status": "submitted", "audit_id": audit_id, "audit_status": "ready"}


def _resolve_subject(conn, item_id: str):
    item = get_work(conn, item_id)
    if item is None:
        raise Reject(f"工单不存在：{item_id}")
    if item["kind"] == "audit":
        deps = loads(item["depends_on"], [])
        if not deps:
            raise Reject("audit 工单缺少被审对象")
        subject = get_work(conn, deps[0])
        if subject is None:
            raise Reject("被审工单不存在")
        return subject, item
    audit_id = f"work:{item['feature_id']}:g{item['generation']}:audit:{item['id']}"
    return item, get_work(conn, audit_id)


def cmd_work_judge(conn, args):
    if args.role != "audit":
        raise Reject("只有 audit 角色可以裁决")
    actor = actor_value(args)
    subject, audit = _resolve_subject(conn, args.id)
    if subject["status"] != "submitted":
        raise Reject(f"被审工单必须是 submitted：{subject['status']}")
    claimed_by = subject.get("claimed_by") if isinstance(subject, dict) else subject["claimed_by"]
    legacy_claim = claimed_by in (None, "", "legacy")
    if not legacy_claim and actor == claimed_by:
        raise Reject("审计独立性：work-judge 的 actor 不能等于被审工单的 claimed_by")
    condition = C.KIND_TO_CONDITION.get(subject["kind"])
    flags = condition_flags(conn, ensure_feature(conn, subject["feature_id"]))
    judged_at = utc_now()
    if args.verdict == "passed":
        if condition in C.EVIDENCE_REQUIRED_CONDITIONS:
            if not evidence_qualifies(conn, subject["feature_id"], subject["generation"]):
                raise Reject(
                    f"{condition} 需要先登记同 generation、exit_code=0 且产物有效的 evidence；"
                    "用 `wxg evidence-record --feature ... --name ... --command ... --actor ...` 登记后再裁决"
                )
        ids = [subject["id"]] + ([audit["id"]] if audit else [])
        marks = ",".join("?" for _ in ids)
        conn.execute(
            f"UPDATE work_items SET status='passed', claim_token=NULL, "
            f"judged_by=COALESCE(judged_by, ?), judged_at=COALESCE(judged_at, ?) WHERE id IN ({marks})",
            (actor, judged_at, *ids),
        )
        if condition:
            set_condition(conn, subject["feature_id"], subject["generation"], condition, 1, "audit passed")
        ready = recompute_ready(conn, subject["feature_id"], subject["generation"])
        refresh_blocked(conn, subject["feature_id"], subject["generation"])
        return {
            "verdict": "passed",
            "condition": condition,
            "work_item_id": subject["id"],
            "actor": actor,
            "legacy_claim": legacy_claim,
            "ready": ready,
            "conditions": {
                name: conn.execute(
                    "SELECT status FROM conditions WHERE feature_id=? AND generation=? AND name=?",
                    (subject["feature_id"], subject["generation"], name),
                ).fetchone()["status"]
                for name in C.CONDITIONS
            },
        }
    if not args.fail_reason:
        raise Reject("failed 必须提供 --fail-reason")
    if audit:
        conn.execute(
            "UPDATE work_items SET status='failed', judged_by=COALESCE(judged_by, ?), "
            "judged_at=COALESCE(judged_at, ?) WHERE id=?",
            (actor, judged_at, audit["id"]),
        )
    conn.execute(
        "UPDATE work_items SET status='ready', claim_token=NULL, assignee=NULL, "
        "judged_by=COALESCE(judged_by, ?), judged_at=COALESCE(judged_at, ?), fail_reason=? WHERE id=?",
        (actor, judged_at, args.fail_reason, subject["id"]),
    )
    # scan 等没有对应条件的工单，failed 不应清空七项条件（尤其不能清掉 Accepted）。
    if condition is not None:
        start = C.CONDITIONS.index(condition)
        for name in C.CONDITIONS[start:]:
            set_condition(conn, subject["feature_id"], subject["generation"], name, 0, args.fail_reason)
    refresh_blocked(conn, subject["feature_id"], subject["generation"])
    return {
        "verdict": "failed",
        "condition": condition,
        "work_item_id": subject["id"],
        "actor": actor,
        "legacy_claim": legacy_claim,
        "fail_reason": args.fail_reason,
        "conditions_changed": condition is not None,
    }


def cmd_work_list(conn, args):
    feature = ensure_feature(conn, args.feature)
    rows = conn.execute(
        "SELECT id, kind, role, status, target_ids, depends_on, claim_token FROM work_items WHERE feature_id=? AND generation=? ORDER BY id",
        (feature["id"], feature["generation"]),
    ).fetchall()
    return {"feature": feature["id"], "generation": feature["generation"], "work_items": [dict(row) for row in rows]}


def _require_write(conn, args, command: str):
    item = require_token(conn, getattr(args, "token", None))
    require_role(item, command)
    return item


def cmd_upsert_node(conn, args):
    item = _require_write(conn, args, "upsert-node")
    payload = load_json_arg(args.data)
    if not isinstance(payload, dict):
        raise Reject("--data 必须是 JSON 对象")
    if not isinstance(payload.get("id"), str) or not payload["id"]:
        raise Reject("--data 缺少字符串 id")
    if not isinstance(payload.get("kind"), str) or not payload["kind"]:
        raise Reject("--data 缺少字符串 kind")
    require_targets(item, [payload["id"]])
    result = upsert_node(conn, payload)
    conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (item["feature_id"], payload["id"]))
    append_evidence(conn, item, [payload["id"]])
    return result


def cmd_upsert_edge(conn, args):
    item = _require_write(conn, args, "upsert-edge")
    payload = load_json_arg(args.data)
    if not isinstance(payload, dict):
        raise Reject("--data 必须是 JSON 对象")
    for key in ("src", "dst", "kind"):
        if not isinstance(payload.get(key), str) or not payload[key]:
            raise Reject(f"--data 缺少字符串 {key}")
    require_targets(item, [payload["src"], payload["dst"]])
    result = upsert_edge(conn, payload)
    append_evidence(conn, item, [payload["src"], payload["dst"]])
    return result


def cmd_bind(conn, args):
    item = _require_write(conn, args, "bind")
    require_targets(item, [args.node_id, args.bind_to])
    result = bind_node(conn, args.node_id, args.bind_to, args.edge_kind)
    append_evidence(conn, item, [args.node_id, args.bind_to])
    return result


def prune_work_refs(conn, removed_ids: set[str]) -> int:
    """从工单 target/evidence 里移除已删除的节点 id；保留通配模式与 audit 单。"""
    if not removed_ids:
        return 0
    changed = 0
    for item in conn.execute("SELECT id, kind, target_ids, evidence_ids FROM work_items").fetchall():
        if item["kind"] == "audit":
            continue
        targets = loads(item["target_ids"], [])
        evidence = loads(item["evidence_ids"], [])
        new_targets = [p for p in targets if p.endswith("*") or p not in removed_ids]
        new_evidence = [node_id for node_id in evidence if node_id not in removed_ids]
        if new_targets != targets or new_evidence != evidence:
            conn.execute(
                "UPDATE work_items SET target_ids=?, evidence_ids=? WHERE id=?",
                (dumps(new_targets), dumps(new_evidence), item["id"]),
            )
            changed += 1
    return changed


def cmd_retract(conn, args):
    item = _require_write(conn, args, "retract")
    node_ids = load_json_arg(args.node_ids) if args.node_ids else []
    edge_ids = load_json_arg(args.edge_ids) if args.edge_ids else []
    if not isinstance(node_ids, list) or not isinstance(edge_ids, list):
        raise Reject("--node-ids / --edge-ids 必须是 JSON 数组或 @文件")
    require_targets(item, node_ids)
    removed_edges = removed_nodes = removed_bites = 0
    for node_id in node_ids:
        rows = conn.execute("SELECT id FROM edges WHERE src=? OR dst=?", (node_id, node_id)).fetchall()
        for row in rows:
            conn.execute("DELETE FROM edges WHERE id=?", (row["id"],))
            removed_edges += 1
        removed_bites += conn.execute("DELETE FROM bites WHERE node_id=?", (node_id,)).rowcount
        conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        conn.execute("DELETE FROM feature_nodes WHERE node_id=?", (node_id,))
        removed_nodes += 1
    for eid in edge_ids:
        row = conn.execute("SELECT src, dst FROM edges WHERE id=?", (eid,)).fetchone()
        if row is not None:
            require_targets(item, [row["src"], row["dst"]])
            conn.execute("DELETE FROM edges WHERE id=?", (eid,))
            removed_edges += 1
    pruned = prune_work_refs(conn, set(node_ids))
    return {
        "nodes_deleted": removed_nodes,
        "edges_deleted": removed_edges,
        "bites_deleted": removed_bites,
        "work_refs_pruned": pruned,
    }


def cmd_bite(conn, args):
    if args.verdict not in C.BITE_VERDICTS:
        raise Reject(f"判决必须是 {C.BITE_VERDICTS} 之一")
    actor = actor_value(args)
    node = get_node(conn, args.node)
    if node is None:
        raise Reject(f"节点不存在：{args.node}")
    if args.feature:
        ensure_feature(conn, args.feature)
        conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (args.feature, args.node))
    conn.execute(
        "INSERT INTO bites(node_id, feature_id, verdict, reason, actor, created_at) VALUES(?,?,?,?,?,?)",
        (args.node, args.feature, args.verdict, args.reason, actor, utc_now()),
    )
    attrs = loads(node["attrs_json"], {})
    attrs["bite"] = args.verdict
    if args.reason:
        attrs["x_bite_reason"] = args.reason
    unmapped = 1 if args.verdict == "UNMAPPED" else node["unmapped"]
    conn.execute("UPDATE nodes SET attrs_json=?, unmapped=? WHERE id=?", (dumps(attrs), unmapped, args.node))
    return {"node": args.node, "verdict": args.verdict, "feature": args.feature, "actor": actor}


def cmd_evidence_record(conn, args):
    feature = ensure_feature(conn, args.feature)
    actor = actor_value(args)
    if not args.name.strip() or not args.command.strip():
        raise Reject("evidence 的 name 与 command 不能为空")
    work_item_id = None
    generation = feature["generation"]
    if args.work:
        work = get_work(conn, args.work)
        if work is None:
            raise Reject(f"工单不存在：{args.work}")
        if work["feature_id"] != feature["id"]:
            raise Reject("evidence 关联的工单不属于该 feature")
        work_item_id = work["id"]
        generation = work["generation"]
    artifact_path = None
    artifact_sha = None
    if args.artifact:
        artifact = Path(args.artifact).resolve()
        if not artifact.is_file():
            raise Reject(f"证据产物不存在：{artifact}")
        artifact_path = str(artifact)
        artifact_sha = sha256_file(artifact)
    evidence_id = "ev:" + uuid.uuid4().hex
    conn.execute(
        "INSERT INTO evidence(id, feature_id, generation, work_item_id, name, command, exit_code, "
        "artifact_path, artifact_sha256, actor, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            evidence_id,
            feature["id"],
            generation,
            work_item_id,
            args.name.strip(),
            args.command.strip(),
            int(args.exit_code),
            artifact_path,
            artifact_sha,
            actor,
            utc_now(),
        ),
    )
    return {
        "id": evidence_id,
        "feature_id": feature["id"],
        "generation": generation,
        "work_item_id": work_item_id,
        "name": args.name.strip(),
        "exit_code": int(args.exit_code),
        "artifact": artifact_path,
        "sha256": artifact_sha,
        "actor": actor,
    }


def cmd_evidence_list(conn, args):
    feature = ensure_feature(conn, args.feature)
    rows = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM evidence WHERE feature_id=? ORDER BY created_at, id", (feature["id"],)
        ).fetchall()
    ]
    return {"feature_id": feature["id"], "evidence": rows}


def cmd_gate(conn, args):
    feature = ensure_feature(conn, args.feature)
    flags = condition_flags(conn, feature)
    scope = set(scope_ids(conn, feature["id"]))
    verdicts = []
    dangling = []
    for row in conn.execute("SELECT node_id, feature_id, verdict FROM bites").fetchall():
        in_feature = row["node_id"] in scope or row["feature_id"] == feature["id"]
        if not in_feature:
            continue
        if get_node(conn, row["node_id"]) is None:
            # 已 retract 的节点：不再计入门禁，但把悬空判决显式带出来，
            # 由 doctor 负责清理，避免 gate 把无效咬合当成交付证据。
            dangling.append({"node": row["node_id"], "verdict": row["verdict"]})
            continue
        verdicts.append((row["node_id"], row["verdict"]))
    # 咬合只采信 bites 表；attrs.bite 只是 bite 命令的展示投影，图写入已禁止写它。
    keep = any(verdict == "KEEP" for _node_id, verdict in verdicts)
    hollow = [(node_id, verdict) for node_id, verdict in verdicts if verdict in C.GATE_FAIL_VERDICTS]
    evidence_ok = evidence_qualifies(conn, feature["id"], feature["generation"])
    base = {
        "conditions": flags,
        "bites": [{"node": node_id, "verdict": verdict} for node_id, verdict in verdicts],
        "evidence_ok": evidence_ok,
    }
    if dangling:
        base["ignored_dangling_bites"] = dangling
    if hollow and not keep:
        return {
            "result": "FAIL",
            "reason": "作用域内存在 UNNECESSARY/HOLLOW 且没有 KEEP 反证",
            "hollow": [{"node": node_id, "verdict": verdict} for node_id, verdict in hollow],
            **base,
        }
    missing = [name for name in C.CONDITIONS if flags[name] != 1]
    if missing:
        return {
            "result": "FAIL",
            "reason": "条件未齐：" + ", ".join(missing),
            "missing": missing,
            **base,
        }
    evidence_missing = [name for name in C.EVIDENCE_REQUIRED_CONDITIONS if flags.get(name) == 1]
    if evidence_missing and not evidence_ok:
        return {
            "result": "FAIL",
            "reason": "缺少有效的同 generation evidence（exit_code=0 且产物存在/hash 一致）：" + ", ".join(evidence_missing),
            "missing_evidence_for": evidence_missing,
            **base,
        }
    return {"result": "PASS", **base}


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


def resolve_targets(conn, target_ids: list[str]) -> tuple[list[str], list[str], list[str]]:
    """展开工单 target_ids 里的 `前缀*` 模式，返回 (实体 id, 缺失 id, 模式)。"""
    existing = {row["id"] for row in conn.execute("SELECT id FROM nodes").fetchall()}
    resolved: list[str] = []
    seen = set()
    missing: list[str] = []
    patterns: list[str] = []
    for pattern in target_ids:
        if pattern.endswith("*"):
            patterns.append(pattern)
            prefix = pattern[:-1]
            for node_id in sorted(existing):
                if node_id.startswith(prefix) and node_id not in seen:
                    seen.add(node_id)
                    resolved.append(node_id)
        elif pattern in existing:
            if pattern not in seen:
                seen.add(pattern)
                resolved.append(pattern)
        else:
            missing.append(pattern)
    return resolved, missing, patterns


def slice_payload(conn, target_ids: list[str]) -> dict:
    resolved, missing, patterns = resolve_targets(conn, target_ids)
    nodes = [node for node in (get_node(conn, node_id) for node_id in resolved) if node]
    edges = []
    for node_id in resolved:
        edges.extend(dict(row) for row in conn.execute("SELECT * FROM edges WHERE src=? OR dst=?", (node_id, node_id)).fetchall())
    unique = {}
    for edge in edges:
        unique[edge["id"]] = edge
    return {
        "nodes": nodes,
        "edges": list(unique.values()),
        "missing_ids": missing,
        "patterns": patterns,
        "depth": 1,
    }


def cmd_slice(conn, args):
    if args.work:
        item = get_work(conn, args.work)
        if item is None:
            raise Reject(f"工单不存在：{args.work}")
        return slice_payload(conn, loads(item["target_ids"], []))
    target_ids = load_json_arg(args.ids) if args.ids else None
    if not isinstance(target_ids, list):
        raise Reject("--work 或 --ids 二选一")
    return slice_payload(conn, target_ids)


def cmd_get(conn, args):
    node = get_node(conn, args.id)
    if node is None:
        raise Reject(f"节点不存在：{args.id}")
    node["attrs"] = loads(node.pop("attrs_json"), {})
    return {"node": node}


def cmd_find(conn, args):
    sql = "SELECT * FROM nodes WHERE 1=1"
    params = []
    if args.kind:
        sql += " AND kind=?"
        params.append(args.kind)
    if args.path_prefix:
        sql += " AND path LIKE ?"
        params.append(args.path_prefix + "%")
    if args.from_id:
        sql += " AND id IN (SELECT dst FROM edges WHERE src=?)"
        params.append(args.from_id)
    rows = []
    for row in conn.execute(sql + " ORDER BY id", params).fetchall():
        row = dict(row)
        row["attrs"] = loads(row.pop("attrs_json"), {})
        rows.append(row)
    return {"nodes": rows}


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
    else:
        lines.append("- 做完后执行 `wxg work-finish --token <token>`，把裁决交给独立 audit 角色。")
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

    # 命令 -> 处理器 / 写入列
    for name in C.COMMANDS:
        handler = globals().get("cmd_" + name.replace("-", "_"))
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
        "SELECT id, status, claim_token, kind, claimed_by, judged_by FROM work_items"
    ).fetchall():
        if item["status"] in ("claimed", "submitted") and not item["claimed_by"]:
            issues.append({"check": "claim-missing-actor", "work_item": item["id"], "status": item["status"]})
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
    by_check = dict(Counter(issue["check"] for issue in after))
    return {
        "ok": not after,
        "issue_count": len(after),
        "by_check": by_check,
        "truncated": len(after) > 200,
        "issues": after[:200],
        "fixed": fixed,
    }


# ------------------------------------------------------------------ CLI

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wxg", description="why-exist-graph：图库 / 工单 / 咬合 / 交付门")
    parser.add_argument("--root", default=None, help="状态库目录（默认 ./.why-exist）")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, spec in C.COMMANDS.items():
        p = sub.add_parser(name, help=spec["help"], description=spec["help"])
        for pos in spec["positionals"]:
            p.add_argument(pos["name"], help=pos["help"], nargs=pos["nargs"] if pos["nargs"] else None)
        for opt in spec["options"]:
            p.add_argument(
                opt["flag"],
                dest=opt["dest"],
                required=opt["required"],
                default=opt["default"],
                choices=opt["choices"],
                type=opt["type"],
                help=opt["help"],
            )
        for flag in spec["flags"]:
            p.add_argument(flag["flag"], dest=flag["dest"], action="store_true", help=flag["help"])
    return parser


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else DEFAULT_ROOT.resolve()
    args.root_path = root
    # 不需要状态库的命令不 connect：避免 verify/contract/role-prompt 在干净目录里
    # 创建 .why-exist/ 与空 graph.sqlite（这些命令必须是真只读、零副作用）。
    needs_db = args.cmd not in ("verify", "contract", "role-prompt")
    if needs_db and args.cmd != "init" and not (root / "graph.sqlite").is_file():
        # 状态库不存在时不再“先建空库再报错”，避免 gate/doctor 等命令留下 0 字节库。
        print(dumps({"error": "状态库未初始化：先运行 `wxg init`"}), file=sys.stderr)
        return 2
    conn = connect(root) if needs_db else None
    try:
        if args.cmd == "init":
            result = cmd_init(conn, args)
            conn.commit()
        else:
            if needs_db:
                ensure_db(conn)
            handler = globals()["cmd_" + args.cmd.replace("-", "_")]
            result = handler(conn, args)
            if needs_db:
                conn.commit()
    except Reject as exc:
        print(dumps({"error": str(exc)}), file=sys.stderr)
        return 2
    finally:
        if conn is not None:
            conn.close()
    if args.cmd in ("verify", "doctor"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 1
    if args.cmd == "gate":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("result") == "PASS" else 1
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
