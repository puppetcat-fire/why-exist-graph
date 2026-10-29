"""生成 references/export-sample 的确定性 fixture。

用法：
  python gen_sample.py            # 打印临时导出目录
  python gen_sample.py --write    # 刷新 references/export-sample/feat-demo
"""
from __future__ import annotations

import argparse
import shutil
import sys
from argparse import Namespace
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
sys.path.insert(0, str(HERE))

import wxg  # noqa: E402

FEATURE = "feat-demo"
REQ = f"requirement:{FEATURE}:main"
UC = f"use_case:{FEATURE}:uc-create-order"
ACTOR = f"actor:{FEATURE}:clerk"
COMPONENT = "component:demo:app"
CLASSIFIER = "classifier:demo:shop.py:OrderRepo"
OPERATION = "operation:demo:shop.py:OrderRepo.save"
SINK = "sink:demo:orders"
ASSERTION = f"assertion:{FEATURE}:code-eq-1"
TESTCASE = f"testcase:{FEATURE}:save-order"
PARAMS = [
    (f"parameter:{FEATURE}:order_id", "order_id", {"column": "order_id"}),
    (f"parameter:{FEATURE}:status", "status", {"column": "status"}),
]


def build(state_root: Path) -> Path:
    """在 state_root 建一个最小但完整的 feature 图并导出，返回 state_root。"""
    import json

    state = Path(state_root)
    conn = wxg.connect(state)
    try:
        wxg.init_db(conn)
        wxg.cmd_feature_declare(
            conn,
            Namespace(
                id=FEATURE,
                name="演示：创建订单",
                statement="创建订单并落库。",
                acceptance=json.dumps(["返回 code===1", "orders 表有记录"], ensure_ascii=False),
                constraints=json.dumps(["不改产品代码"], ensure_ascii=False),
            ),
        )
        _build_graph(conn)
        conn.commit()
        wxg.cmd_export(conn, Namespace(root_path=state, feature=FEATURE))
    finally:
        conn.close()
    return state


def _build_graph(conn) -> None:
    def node(node_id, kind, name, attrs=None, **extra):
        wxg.upsert_node(conn, {"id": node_id, "kind": kind, "name": name, "attrs": attrs or {}, "origin": "declared", **extra})

    node(UC, "use_case", "创建订单", {"actor": "店员", "goal": "订单落库"}, feature_id=FEATURE)
    wxg.upsert_edge(conn, {"src": UC, "dst": REQ, "kind": "satisfies"})
    node(ACTOR, "actor", "店员", feature_id=FEATURE)
    wxg.upsert_edge(conn, {"src": ACTOR, "dst": UC, "kind": "associates"})
    node(COMPONENT, "component", "订单服务", {"duty": "接收订单并写库"})
    wxg.upsert_edge(conn, {"src": UC, "dst": COMPONENT, "kind": "associates"})

    node(CLASSIFIER, "classifier", "OrderRepo", {"duty": "订单持久化"}, repo="demo", path="shop.py", symbol="OrderRepo")
    node(OPERATION, "operation", "save", {"http": "POST /orders", "success_code": "code===1"}, repo="demo", path="shop.py", symbol="OrderRepo.save")
    wxg.upsert_edge(conn, {"src": CLASSIFIER, "dst": OPERATION, "kind": "contains"})
    wxg.upsert_edge(conn, {"src": UC, "dst": OPERATION, "kind": "contains"})
    node(SINK, "sink", "orders", {"table": "orders"})
    wxg.upsert_edge(conn, {"src": OPERATION, "dst": SINK, "kind": "writes"})
    for param_id, name, attrs in PARAMS:
        node(param_id, "parameter", name, attrs, feature_id=FEATURE)
        wxg.bind_node(conn, param_id, OPERATION)

    node(TESTCASE, "testcase", "save 返回成功", {"path": "tests/test_orders.py", "layer": "unit"}, feature_id=FEATURE)
    wxg.upsert_edge(conn, {"src": TESTCASE, "dst": OPERATION, "kind": "verifies"})
    node(ASSERTION, "assertion", "成功码 code===1", {"text": "成功码 code===1", "success_code": "code===1"}, feature_id=FEATURE)
    wxg.bind_node(conn, ASSERTION, OPERATION)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="刷新 references/export-sample/feat-demo")
    args = parser.parse_args(argv)
    with wxg.temp_dir("wxg-sample-") as tmp:
        state = build(Path(tmp) / "state")
        produced = state / "export" / FEATURE
        if args.write:
            target = SKILL_DIR / "references" / "export-sample" / FEATURE
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(produced, target)
            print(str(target))
        else:
            print(str(produced))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
