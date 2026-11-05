"""slice 06 行为探针：只读源码，不写状态库（临时目录 + 内存库）。"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from whyexist import db, graph  # noqa: E402


def mem():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_SQL)
    return conn


def show(label, value):
    print(f"{label} => {value!r}")


def main():
    # 1. Engine 在未初始化目录上的副作用
    from whyexist import Engine
    from whyexist.errors import Reject

    tmp = Path(tempfile.mkdtemp(prefix="wxg06-"))
    root = tmp / "state"
    try:
        Engine(root).connect()
    except Exception as exc:  # noqa: BLE001
        show("Engine 空目录异常类型", type(exc).__name__)
        show("Engine 空目录异常信息", str(exc))
    show("Engine 空目录后存在 state 目录", root.is_dir())
    show(
        "Engine 空目录后文件",
        sorted(p.name for p in root.iterdir()) if root.is_dir() else [],
    )

    # 2. upsert_node 属性覆盖 / 保留 / stale / name=None / merge
    conn = mem()
    graph.upsert_node(conn, {"id": "component:r:a", "kind": "component", "name": "A",
                             "attrs": {"duty": "d", "x_note": "n"}})
    show("首次 attrs", json.loads(graph.get_node(conn, "component:r:a")["attrs_json"]))
    graph.upsert_node(conn, {"id": "component:r:a", "kind": "component", "attrs": {"x_other": "o"}})
    row = graph.get_node(conn, "component:r:a")
    show("不带 attrs 再 upsert 后 attrs", json.loads(row["attrs_json"]))
    show("不带 name 再 upsert 后 name", row["name"])
    graph.upsert_node(conn, {"id": "component:r:a", "kind": "component", "name": None})
    show("显式 name=None 后 name", graph.get_node(conn, "component:r:a")["name"])

    conn.execute("UPDATE nodes SET stale=1, unmapped=1 WHERE id='component:r:a'")
    graph.upsert_node(conn, {"id": "component:r:a", "kind": "component"})
    row = graph.get_node(conn, "component:r:a")
    show("再 upsert 后 stale/unmapped", (row["stale"], row["unmapped"]))

    graph.upsert_node(conn, {"id": "component:r:a", "kind": "component",
                             "attrs": {"duty": "merged"}}, merge_attrs=True)
    show("merge_attrs=True 后 attrs",
         json.loads(graph.get_node(conn, "component:r:a")["attrs_json"]))

    # 3. bind 方向与 kind 覆盖
    graph.upsert_node(conn, {"id": "operation:r:o", "kind": "operation"})
    graph.upsert_node(conn, {"id": "parameter:r:p", "kind": "parameter"})
    graph.upsert_node(conn, {"id": "message:r:m", "kind": "message"})
    graph.upsert_node(conn, {"id": "argument:r:g", "kind": "argument"})
    graph.upsert_node(conn, {"id": "assertion:r:s", "kind": "assertion"})
    graph.bind_node(conn, "parameter:r:p", "operation:r:o")
    graph.bind_node(conn, "argument:r:g", "message:r:m")
    graph.bind_node(conn, "assertion:r:s", "operation:r:o")
    rows = conn.execute("SELECT id, src, dst, kind FROM edges ORDER BY id").fetchall()
    show("bind 生成的边", [(r["kind"], r["src"], r["dst"]) for r in rows])
    graph.bind_node(conn, "parameter:r:p", "operation:r:o", "has_argument")
    rows = conn.execute("SELECT kind, src, dst FROM edges WHERE src='operation:r:o'").fetchall()
    show("parameter 用 --edge-kind has_argument 后", [(r["kind"], r["src"], r["dst"]) for r in rows])

    # 4. upsert_edge 自定义 id / 无 id
    graph.upsert_edge(conn, {"src": "operation:r:o", "dst": "component:r:a", "kind": "associates"})
    graph.upsert_edge(conn, {"id": "随便", "src": "operation:r:o", "dst": "component:r:a",
                             "kind": "associates"})
    rows = conn.execute("SELECT id FROM edges WHERE kind='associates' ORDER BY id").fetchall()
    show("associates 边 id", [r["id"] for r in rows])

    # 5. edge id 与端点绑定的证据
    eid = graph.edge_id("depends", "component:r:a", "component:r:b")
    show("edge_id", eid)
    show("edges 表有外键约束",
         [r["sql"] for r in conn.execute(
             "SELECT sql FROM sqlite_master WHERE type='table' AND name='edges'")][0])

    conn.close()

    # 6. graph_algo 的空图 / 多环 / 自环 / 环图可达
    import whyexist.graph_algo as G
    show("analyze 空图", G.analyze([], []))
    show("analyze 自环", G.analyze(["a", "b"], [("a", "a")]))
    show("max_antichain 自环", G.max_antichain(["a", "b"], [("a", "a")]))
    show("analyze 两个独立环", G.analyze(
        ["a", "b", "c", "d"],
        [("a", "b"), ("b", "a"), ("c", "d"), ("d", "c")],
    ))
    show("两个环 + 一条入边时 parallelism", G.analyze(
        ["a", "b", "c", "d", "e"],
        [("a", "b"), ("b", "a"), ("c", "d"), ("d", "c"), ("e", "a")],
    ).parallelism)
    show("重复边归一化", G.analyze(["a", "b"], [("a", "b"), ("a", "b")]))
    show("reachable 环图含起点", G.reachable(["a", "b"], [("a", "b"), ("b", "a")], "a"))


if __name__ == "__main__":
    main()
