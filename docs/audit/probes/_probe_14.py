"""slice 14 行为探针：只读源码，不写状态库（临时目录 + 内存 SQLite）。

用法：
    python docs/audit/_probe_14.py            # 全部探针
    python docs/audit/_probe_14.py scope      # 只跑 scope_ids 顺序（供外部换 PYTHONHASHSEED 对比）
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from whyexist import blind, briefing, db, jsonio, reducer, work, workflow  # noqa: E402
from whyexist.errors import Reject  # noqa: E402


def mem():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA_SQL)
    conn.execute(
        "INSERT INTO features (id, name, generation, statement, created_at) "
        "VALUES ('f', 'F', 1, 's', '2026-01-01T00:00:00Z')"
    )
    for name in __import__("whyexist.contract", fromlist=["C"]).C.CONDITIONS:
        conn.execute(
            "INSERT INTO conditions (feature_id, generation, name, status) VALUES (?,?,?,0)",
            ("f", 1, name),
        )
    return conn


def show(label, value):
    print(f"{label} => {value!r}")


def try_reject(label, fn):
    try:
        result = fn()
        show(label, f"NOT REJECTED -> {result!r}")
    except Reject as exc:
        show(label, f"Reject: {exc}")


def scope_probe():
    """scope_ids 里通配展开遍历 set()，顺序是否稳定（换 PYTHONHASHSEED 对比）。"""
    conn = mem()
    for i in (1, 2, 3, 4, 5):
        conn.execute(
            "INSERT INTO nodes (id, kind, name) VALUES (?,?,?)",
            (f"component:x:n{i}", "component", f"n{i}"),
        )
    conn.execute("INSERT INTO nodes (id, kind, name) VALUES ('requirement:f:r','requirement','R')")
    conn.execute(
        "INSERT INTO work_items "
        "(id, feature_id, generation, kind, role, target_ids, status, depends_on, created_at) "
        "VALUES ('w1','f',1,'scan','scan',?, 'ready','[]','2026-01-01T00:00:00Z')",
        (jsonio.dumps(["component:x:*"]),),
    )
    print("scope_ids order:", workflow.scope_ids(conn, "f"))


def main():
    # 1. insert_work 非 merge 分支：覆盖 target_ids 的同时也覆盖 depends_on，status 不动
    conn = mem()
    work.insert_work(conn, "f", 1, "scan", ["a:x"], ["dep:1"])
    conn.execute("UPDATE work_items SET status='blocked'")
    result = work.insert_work(conn, "f", 1, "scan", ["a:y"], None)
    item = work.get_work(conn, result["id"])
    show("insert_work 非 merge 动作", result)
    show("非 merge 后 target_ids", item["target_ids"])
    show("非 merge 后 depends_on（None 传入）", item["depends_on"])
    show("非 merge 后 status（blocked 保持不变）", item["status"])

    # 2. merge 允许的 status 白名单
    for status in ("ready", "claimed", "blocked", "submitted", "failed", "superseded"):
        conn2 = mem()
        work.insert_work(conn2, "f", 1, "scan", ["a:x"], None)
        conn2.execute("UPDATE work_items SET status=?", (status,))
        try:
            out = work.insert_work(conn2, "f", 1, "scan", ["a:y"], None, merge=True)
            show(f"merge on {status}", out["action"])
        except Reject as exc:
            show(f"merge on {status}", f"Reject: {exc}")

    # 3. require_targets：空 target_ids 的边界语义
    try_reject(
        "require_targets 空 target_ids",
        lambda: work.require_targets({"target_ids": "[]"}, ["anything:1"]),
    )
    # 通配 "*" 的语义
    show("target_match('*', 'x')", work.target_match("*", "x"))
    show("target_match('a*', 'ab')", work.target_match("a*", "ab"))
    show("target_match('a*', 'ba')", work.target_match("a*", "ba"))

    # 4. require_token 错误文案分档
    conn3 = mem()
    work.insert_work(conn3, "f", 1, "scan", ["a:x"], None)
    try_reject("require_token 空 token", lambda: work.require_token(conn3, ""))
    try_reject("require_token 未知 token", lambda: work.require_token(conn3, "nope"))

    # 5. append_evidence 就地改 item（调用方看到的 dict 也被改）
    conn4 = mem()
    wid = work.insert_work(conn4, "f", 1, "scan", ["a:x"], None)["id"]
    item = work.get_work(conn4, wid)
    work.append_evidence(conn4, item, ["n1"])
    show("append_evidence 后内存 item['evidence_ids']", item["evidence_ids"])

    # 6. actor_value：env 回退、strip、长度/空格规则
    class Args:
        def __init__(self, actor=None):
            self.actor = actor

    import os

    os.environ["WXG_ACTOR"] = "env-agent"
    show("actor_value(None) 读 WXG_ACTOR", workflow.actor_value(Args()))
    os.environ.pop("WXG_ACTOR")
    try_reject("actor_value 缺 actor", lambda: workflow.actor_value(Args()))
    show("actor_value required=False", repr(workflow.actor_value(Args(), required=False)))
    try_reject("actor_value 含空格", lambda: workflow.actor_value(Args("a b")))
    show("actor_value 80 字符", len(workflow.actor_value(Args("x" * 80))))
    try_reject("actor_value 81 字符", lambda: workflow.actor_value(Args("x" * 81)))
    show("actor_value 前后空白被 strip", workflow.actor_value(Args("  a1  ")))

    # 7. blind.check_output：省略 known kinds / produces 为空时的退化
    brief = {
        "write_boundary": ["component:p:a"],
        "write_patterns": ["component:p:*"],
        "inputs": [],
        "produces": [],
    }
    out = {"nodes": [{"id": "component:p:x", "kind": "任意未知kind"}]}
    show(
        "blind 省略 known_node_kinds 的未知 kind",
        blind.check_output(brief=brief, output=out)["verdict"],
    )
    show(
        "blind 传 known_node_kinds 的未知 kind",
        blind.check_output(brief=brief, output=out, known_node_kinds=["component"])["verdict"],
    )
    show(
        "blind produces 为空时任意 kind 不算越契约",
        blind.check_output(
            brief=brief, output=out, known_node_kinds=["任意未知kind"]
        )["contract"]["unexpected_kinds"],
    )
    # 精确的 locality 扣分
    show(
        "locality 一个越界节点（期望 0.6）",
        blind.check_output(
            brief=brief, output={"nodes": [{"id": "component:q:1", "kind": "component"}]}
        )["locality"],
    )
    show(
        "locality 两个越界节点（期望 0.5）",
        blind.check_output(
            brief=brief,
            output={
                "nodes": [
                    {"id": "component:q:1", "kind": "component"},
                    {"id": "component:q:2", "kind": "component"},
                ]
            },
        )["locality"],
    )
    show(
        "locality 一个未声明端点（期望 0.7）",
        blind.check_output(
            brief=brief,
            output={"edges": [{"src": "component:q:1", "dst": "component:q:2", "kind": "depends"}]},
        )["locality"],
    )
    # inputs 里的节点作为产出出现 -> 算越界？
    brief_in = dict(brief, inputs=[{"id": "component:ext:1", "kind": "component"}])
    show(
        "把 inputs 节点当产出写",
        blind.check_output(brief=brief_in, output={"nodes": [{"id": "component:ext:1", "kind": "component"}]})[
            "boundary"
        ],
    )
    # malformed 同时把 contract 弄失败，但不影响 boundary
    show(
        "malformed 节点 verdict",
        blind.check_output(brief=brief, output={"nodes": [{"kind": "component"}]})["verdict"],
    )

    # 8. reducer：normalize 丢弃缺 id/边的行为、重复 id 保留第一次
    show(
        "normalize 重复 id 保留第一次",
        reducer.normalize_patch(
            {
                "nodes": [
                    {"id": "a", "kind": "component", "name": "first"},
                    {"id": "a", "kind": "component", "name": "second"},
                ],
                "edges": [{"src": "a", "dst": "b", "kind": "depends"}, {"src": "a"}],
            },
            work_item="w1",
        ),
    )
    show(
        "normalize 无 work_item 且 patch 无 work_item",
        reducer.normalize_patch({"nodes": []})["work_item"],
    )
    # merge：attrs 缺省与空 dict 视为相同指纹
    m = reducer.merge_patches(
        [
            {"work_item": "w1", "nodes": [{"id": "a", "kind": "component"}]},
            {"work_item": "w2", "nodes": [{"id": "a", "kind": "component", "attrs": {}}]},
        ],
        existing_ids=set(),
    )
    show("merge 缺 attrs vs attrs={} 是否冲突", (m["ok"], m["conflicts"]))
    # merge 忽略 name=None 与缺省
    m2 = reducer.merge_patches(
        [
            {"work_item": "w1", "nodes": [{"id": "a", "kind": "component", "name": "A"}]},
            {"work_item": "w2", "nodes": [{"id": "a", "kind": "component", "name": "A", "attrs": {"x": 1}}]},
        ],
        existing_ids=set(),
    )
    show("merge 第二个补丁多带 attrs", (m2["ok"], m2["conflicts"]))
    # 边只查端点存在，不查 kind 合法性
    m3 = reducer.merge_patches(
        [{"work_item": "w3", "nodes": [], "edges": [{"src": "a", "dst": "b", "kind": "bogus"}]}],
        existing_ids={"a", "b"},
    )
    show("merge 未知边 kind 的 ok", (m3["ok"], m3["edges"]))
    # 顺序：冲突 a=先出现的补丁，b=后出现的补丁
    m4 = reducer.merge_patches(
        [
            {"work_item": None, "nodes": [{"id": "a", "kind": "component", "name": "1"}]},
            {"work_item": None, "nodes": [{"id": "a", "kind": "component", "name": "2"}]},
        ],
        existing_ids=set(),
    )
    show("merge 无 label 的冲突命名", m4["conflicts"])

    # 9. briefing：通配 '*'、未匹配模式、work 缺 kind/target_ids
    show("resolve_boundary('*')", briefing.resolve_boundary(["*"], ["a:1", "b:2"]))
    show("resolve_boundary 未匹配", briefing.resolve_boundary(["z:*"], ["a:1"]))
    brief2 = briefing.build_brief(
        feature={"id": "f"}, work={"id": "w"}, nodes={}, edges=[]
    )
    show("build_brief 最小输入输出键", sorted(brief2))
    show("build_brief 最小输入 produces/kind", (brief2["kind"], brief2["produces"], brief2["goal"]))
    # produces 覆盖了契约 NODE_KINDS 里哪些 kind？
    from whyexist.contract import C

    all_kinds = [item["kind"] for item in C.NODE_KINDS]
    covered = sorted({k for kinds in briefing.PRODUCES.values() for k in kinds})
    show("PRODUCES 未覆盖的 NODE_KINDS", [k for k in all_kinds if k not in covered])
    show("PRODUCES 里不在 NODE_KINDS 的 kind", [k for k in covered if k not in all_kinds])
    from whyexist import impact

    show("DEPENDENCY_EDGE_KINDS", briefing.DEPENDENCY_EDGE_KINDS)
    show("impact 复用的依赖边集一致", impact.__dict__.get("DEPENDENCY_EDGE_KINDS") is briefing.DEPENDENCY_EDGE_KINDS)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scope":
        scope_probe()
    else:
        main()
