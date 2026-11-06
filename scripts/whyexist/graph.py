"""图读写：节点、边、绑定，以及写入前的 kind / attrs / id 校验。"""

from __future__ import annotations

import re
from pathlib import Path

from .contract import C, DESIGN_ANCHOR_KINDS
from .db import _is_integrity_error
from .errors import Reject
from .jsonio import dumps, loads

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


_UNSET = object()


def upsert_node(conn, payload: dict, merge_attrs: bool = False, existing=_UNSET) -> dict:
    node_id = payload.get("id")
    kind = payload.get("kind")
    if not node_id or not kind:
        raise Reject("节点缺少 id 或 kind")
    check_kind(kind)
    check_node_id(kind, node_id)
    incoming = check_attrs(kind, payload.get("attrs") or {})
    # 批量导入时调用方已经查过该节点（用来统计 inserted/updated），把结果传进来
    # 可以省掉一次 SELECT；不传则自己查。
    if existing is _UNSET:
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
        "stale": 0,
    }
    conn.execute(
        """INSERT INTO nodes (id, kind, name, repo, path, symbol, line_start, line_end, attrs_json, origin, unmapped, stale)
           VALUES (:id, :kind, :name, :repo, :path, :symbol, :line_start, :line_end, :attrs_json, :origin, :unmapped, :stale)
           ON CONFLICT(id) DO UPDATE SET
             kind=excluded.kind, name=excluded.name, repo=excluded.repo, path=excluded.path,
             symbol=excluded.symbol, line_start=excluded.line_start, line_end=excluded.line_end,
             attrs_json=excluded.attrs_json, origin=excluded.origin, unmapped=excluded.unmapped,
             stale=excluded.stale""",
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
    if kind == "has_acceptance":
        # 写入期就锁住结构：验收条目唯一归属一条需求、两端 kind 固定。doctor 只兜旧库。
        src_node = get_node(conn, src)
        dst_node = get_node(conn, dst)
        if src_node["kind"] != "requirement":
            raise Reject(f"has_acceptance 的 src 必须是 requirement，实际 {src_node['kind']}")
        if dst_node["kind"] != "acceptance":
            raise Reject(f"has_acceptance 的 dst 必须是 acceptance，实际 {dst_node['kind']}")
        holder = conn.execute(
            "SELECT src FROM edges WHERE kind='has_acceptance' AND dst=?", (dst,)
        ).fetchone()
        if holder is not None and holder["src"] != src:
            raise Reject(f"验收条目已挂在 {holder['src']} 下：{dst}（一个条目只能属于一条需求）")
    if kind == "verifies":
        dst_node = get_node(conn, dst)
        if dst_node["kind"] == "acceptance":
            src_node = get_node(conn, src)
            if src_node["kind"] != "testcase":
                raise Reject(f"verifies 指向 acceptance 时 src 必须是 testcase，实际 {src_node['kind']}")
    if kind == "applies":
        src_kind = get_node(conn, src)["kind"]
        dst_kind = get_node(conn, dst)["kind"]
        if src_kind not in ("component", "classifier", "operation"):
            raise Reject(f"applies 的 src 必须是 component/classifier/operation，实际 {src_kind}")
        if dst_kind != "pattern":
            raise Reject(f"applies 的 dst 必须是 pattern，实际 {dst_kind}")
    if kind == "maps_to":
        src_node = get_node(conn, src)
        dst_node = get_node(conn, dst)
        if src_node["kind"] not in DESIGN_ANCHOR_KINDS:
            raise Reject(
                f"maps_to 的 src 必须是 {'/'.join(DESIGN_ANCHOR_KINDS)}，实际 {src_node['kind']}"
            )
        if not (dst_node["repo"] and dst_node["path"]):
            raise Reject(f"maps_to 的 dst 必须是带 repo/path 的代码节点：{dst}")
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


