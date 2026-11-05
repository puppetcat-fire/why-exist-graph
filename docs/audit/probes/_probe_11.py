"""审计切片 11（graph 域写入口）行为探针：只读源码，不改项目；只建临时状态库。

运行：python docs/audit/_probe_11.py
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
WXG = SKILL / "scripts" / "wxg.py"

BASE = Path(tempfile.mkdtemp(prefix="wxg-probe-11-"))
ROOT = BASE / "state"
ENV = {k: v for k, v in os.environ.items() if not k.startswith("WXG_")}
ENV["PYTHONUTF8"] = "1"


def run(*args, expect=0):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    out = proc.stdout.strip()
    try:
        parsed = json.loads(out) if out else None
    except json.JSONDecodeError:
        parsed = out
    if proc.returncode != expect:
        parsed = {"__rc": proc.returncode, "__stderr": proc.stderr.strip()[-300:]}
    return parsed


def db():
    conn = sqlite3.connect(ROOT / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def node(nid):
    conn = db()
    try:
        row = conn.execute("SELECT * FROM nodes WHERE id=?", (nid,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def one(sql, params=()):
    conn = db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def snap():
    conn = db()
    try:
        tables = ["nodes", "edges", "bites", "feature_nodes", "work_items", "evidence"]
        return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}
    finally:
        conn.close()


def section(title):
    print(f"\n===== {title}")


run("init")
run("feature-declare", "--id", "feat-a", "--name", "A", "--statement", "s",
    "--acceptance", "[]", "--constraints", "[]")
run("feature-declare", "--id", "feat-b", "--name", "B", "--statement", "s",
    "--acceptance", "[]", "--constraints", "[]")
run("work-open", "--feature", "feat-a", "--kind", "model-architecture", "--target-ids", '["*"]')
claim = run("work-claim", "--role", "model-architecture", "--actor", "agent-arch")
TOKEN = claim["claim_token"]
print("claim ok, token len", len(TOKEN))

# ---------------------------------------------------------------- upsert-node
section("P1 upsert-node 同 id 再写：attrs 是覆盖还是合并")
a1 = run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "classifier:demo:a.py:K", "kind": "classifier", "name": "K",
     "attrs": {"duty": "第一次", "x_note": "保留？"}}))
a2 = run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "classifier:demo:a.py:K", "kind": "classifier", "name": "K2", "attrs": {"duty": "第二次"}}))
n = node("classifier:demo:a.py:K")
print("action1", a1, "action2", a2)
print("name ->", n["name"], "attrs ->", n["attrs_json"], "origin ->", n["origin"])

section("P2 upsert-node 是否重置 unmapped / stale")
conn = db()
conn.execute("UPDATE nodes SET unmapped=1, stale=1 WHERE id='classifier:demo:a.py:K'")
conn.commit()
conn.close()
run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "classifier:demo:a.py:K", "kind": "classifier", "name": "K3"}))
n = node("classifier:demo:a.py:K")
print("unmapped ->", n["unmapped"], "stale ->", n["stale"], "attrs ->", n["attrs_json"],
      "name ->", n["name"])

section("P3 upsert-node 副作用：feature_nodes(工作单 feature) / payload.feature_id")
print("feature_nodes ->", [tuple(r) for r in one("SELECT * FROM feature_nodes ORDER BY 1,2")])
run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "classifier:demo:a.py:K2", "kind": "classifier", "name": "K2", "feature_id": "feat-b"}))
print("after payload.feature_id=feat-b ->", [tuple(r) for r in one("SELECT * FROM feature_nodes ORDER BY 1,2")])

section("P4 upsert-node 拒绝分支")
print("无 token ->", run("upsert-node", "--data", "{}", expect=2))
print("data 非对象 ->", run("upsert-node", "--token", TOKEN, "--data", "[]", expect=2))
print("坏 kind ->", run("upsert-node", "--token", TOKEN, "--data",
                        json.dumps({"id": "nope:1", "kind": "nope"}), expect=2))
print("id 前缀不符 ->", run("upsert-node", "--token", TOKEN, "--data",
                            json.dumps({"id": "classifier:x", "kind": "use_case"}), expect=2))
print("attrs 未声明键 ->", run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "classifier:demo:a.py:K", "kind": "classifier", "attrs": {"whatever": 1}}), expect=2))

# ---------------------------------------------------------------- upsert-edge
section("P5 upsert-edge：显式 id 覆盖 / 换 kind 生成新 id")
run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "component:demo:svc", "kind": "component", "name": "S"}))
run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "component:demo:other", "kind": "component", "name": "O"}))
e1 = run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"id": "edge:manual:1", "src": "component:demo:svc", "dst": "component:demo:other", "kind": "depends"}))
e2 = run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"id": "edge:manual:1", "src": "component:demo:svc", "dst": "component:demo:other", "kind": "associates"}))
print("edge1", e1, "edge2", e2)
print("rows ->", [tuple(r) for r in one("SELECT id, src, dst, kind FROM edges ORDER BY id")])
e3 = run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"src": "component:demo:svc", "dst": "component:demo:other", "kind": "depends"}))
print("派生 id 追加后 ->", e3, [r["id"] for r in one("SELECT id FROM edges ORDER BY id")])

section("P6 upsert-edge 拒绝分支")
print("src 缺失 ->", run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"src": "component:none", "dst": "component:demo:svc", "kind": "depends"}), expect=2))
print("未知 kind ->", run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"src": "component:demo:svc", "dst": "component:demo:other", "kind": "nope"}), expect=2))
print("maps_to 反向 ->", run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"src": "component:demo:svc", "dst": "component:demo:other", "kind": "maps_to"}), expect=2))

# ---------------------------------------------------------------- bind
section("P7 bind：edge_kind 与 bind_to 的 kind 是否校验")
run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "parameter:feat-a:p1", "kind": "parameter", "name": "p1"}))
run("upsert-node", "--token", TOKEN, "--data", json.dumps(
    {"id": "use_case:feat-a:uc", "kind": "use_case", "name": "uc"}))
print("parameter + --edge-kind asserts ->", run(
    "bind", "--token", TOKEN, "--node-id", "parameter:feat-a:p1",
    "--bind-to", "use_case:feat-a:uc", "--edge-kind", "asserts"))
print("parameter + bind_to=use_case（默认 has_input）->", run(
    "bind", "--token", TOKEN, "--node-id", "parameter:feat-a:p1", "--bind-to", "use_case:feat-a:uc"))
print("非法 node kind bind ->", run(
    "bind", "--token", TOKEN, "--node-id", "use_case:feat-a:uc", "--bind-to", "component:demo:svc", expect=2))
print("bind_to 不存在 ->", run(
    "bind", "--token", TOKEN, "--node-id", "parameter:feat-a:p1", "--bind-to", "component:none", expect=2))
print("edges ->", [tuple(r) for r in one("SELECT id, src, dst, kind FROM edges WHERE kind IN ('asserts','has_input') ORDER BY id")])
print("evidence_ids ->", one("SELECT evidence_ids FROM work_items WHERE id=?", (claim["work_item_id"],))[0][0])

# ---------------------------------------------------------------- bite
section("P8 bite：追加历史 / attrs.bite / unmapped 粘滞")
TARGET = "classifier:demo:a.py:K"
b1 = run("bite", "--node", TARGET, "--verdict", "UNMAPPED", "--reason", "认不出", "--actor", "leady")
b2 = run("bite", "--node", TARGET, "--verdict", "KEEP", "--reason", "需要", "--actor", "leady")
n = node(TARGET)
print("bite1 ->", b1)
print("bite2 ->", b2)
print("attrs ->", n["attrs_json"], "unmapped ->", n["unmapped"])
print("bites ->", [tuple(r) for r in one(
    "SELECT node_id, feature_id, generation, phase, verdict, reason, actor FROM bites ORDER BY id")])

section("P9 bite 无 --feature / 越界节点 / 缺 actor / 节点不存在")
b3 = run("bite", "--node", "classifier:demo:a.py:K2", "--verdict", "UNKNOWN", "--actor", "leady")
print("无 feature ->", b3, [tuple(r) for r in one(
    "SELECT node_id, feature_id, generation, phase, verdict FROM bites WHERE node_id='classifier:demo:a.py:K2'")])
print("feature_nodes 是否被写 ->", [tuple(r) for r in one(
    "SELECT * FROM feature_nodes WHERE node_id='classifier:demo:a.py:K2'")])
run("work-open", "--feature", "feat-b", "--kind", "model-architecture", "--target-ids", '["requirement:feat-b:*"]')
claim_b = run("work-claim", "--role", "model-architecture", "--actor", "agent-arch")
run("upsert-node", "--token", claim_b["claim_token"], "--data", json.dumps(
    {"id": "classifier:demo:a.py:OUT", "kind": "classifier", "name": "越界"}))
b4 = run("bite", "--node", "classifier:demo:a.py:OUT", "--verdict", "HOLLOW",
         "--feature", "feat-b", "--actor", "leady")
print("不在 feat-b target_ids 内也能 bite ->", b4)
print("feature_nodes(feat-b) ->", [tuple(r) for r in one(
    "SELECT * FROM feature_nodes WHERE feature_id='feat-b' ORDER BY 2")])
print("缺 actor ->", run("bite", "--node", TARGET, "--verdict", "KEEP", expect=2))
print("节点不存在 ->", run("bite", "--node", "classifier:none", "--verdict", "KEEP",
                           "--actor", "leady", expect=2))
print("坏 verdict（argparse）->", run("bite", "--node", TARGET, "--verdict", "NOPE",
                                      "--actor", "leady", expect=2))

# ---------------------------------------------------------------- retract
section("P10 retract：不存在 id 的计数 / 显式 edge 静默跳过")
before = snap()
r1 = run("retract", "--token", TOKEN, "--node-ids", "classifier:demo:does-not-exist")
print("删不存在节点 ->", r1, "nodes 数不变:", len(before["nodes"]) == len(one("SELECT id FROM nodes")))

section("P11 retract：级联边 + bite + 跨 feature 工单引用")
# feat-b 的工单 target/evidence 引用 feat-a 的节点
conn = db()
conn.execute("UPDATE work_items SET target_ids=?, evidence_ids=? WHERE id=?",
             (json.dumps(["*"]), json.dumps([TARGET]), claim_b["work_item_id"]))
conn.commit()
conn.close()
edges_before = [r["id"] for r in one("SELECT id FROM edges WHERE src=? OR dst=?", (TARGET, TARGET))]
r2 = run("retract", "--token", TOKEN, "--node-ids", TARGET)
print("retract ->", r2, "被级联的边:", edges_before)
print("node 行 ->", node(TARGET))
print("bites 行 ->", [tuple(r) for r in one("SELECT node_id, verdict FROM bites WHERE node_id=?", (TARGET,))])
print("feat-b 工单引用 ->", [tuple(r) for r in one(
    "SELECT id, target_ids, evidence_ids FROM work_items WHERE id=?", (claim_b["work_item_id"],))])
print("feat-a 工单 evidence_ids ->", one(
    "SELECT evidence_ids FROM work_items WHERE id=?", (claim["work_item_id"],))[0][0])

section("P12 retract：显式 edge-ids 分支")
run("upsert-node", "--token", TOKEN, "--data", json.dumps({"id": "component:demo:x1", "kind": "component", "name": "x1"}))
run("upsert-node", "--token", TOKEN, "--data", json.dumps({"id": "component:demo:x2", "kind": "component", "name": "x2"}))
run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"src": "component:demo:x1", "dst": "component:demo:x2", "kind": "depends"}))
eid = "edge:depends:component:demo:x1:component:demo:x2"
print("按 id 删边 ->", run("retract", "--token", TOKEN, "--edge-ids", eid))
print("再删同一 id（静默 0）->", run("retract", "--token", TOKEN, "--edge-ids", eid))
print("空 node/edge ids ->", run("retract", "--token", TOKEN))

section("P13 retract 中途失败是否回滚（边端点不在 target 内）")
conn = db()
conn.execute("UPDATE work_items SET target_ids=? WHERE id=?",
             (json.dumps(["component:demo:x1", "component:demo:x2"]), claim["work_item_id"]))
conn.commit()
conn.close()
run("upsert-node", "--token", TOKEN, "--data", json.dumps({"id": "component:demo:x3", "kind": "component", "name": "x3"}))
run("upsert-edge", "--token", TOKEN, "--data", json.dumps(
    {"src": "component:demo:x3", "dst": "component:demo:x2", "kind": "associates"}))
# x3 不在 target；x1/x2 在。先删 x1（成功），再对 x3 的边 require_targets 抛错
before = snap()
bad = run("retract", "--token", TOKEN,
          "--node-ids", "component:demo:x1",
          "--edge-ids", "edge:associates:component:demo:x3:component:demo:x2", expect=2)
after = snap()
print("失败输出 ->", bad)
print("回滚（x1 仍在）->", node("component:demo:x1") is not None,
      "全表快照一致:", before == after)

# ---------------------------------------------------------------- evidence
section("P14 evidence-record / evidence-list")
art = BASE / "log.txt"
art.write_text("ok", encoding="utf-8")
print("无 actor ->", run("evidence-record", "--feature", "feat-a", "--name", "n",
                         "--command", "c", expect=2))
print("exit-code 1 ->", run("evidence-record", "--feature", "feat-a", "--name", "fail",
                            "--command", "c", "--exit-code", "1", "--actor", "a1"))
print("artifact 不存在 ->", run("evidence-record", "--feature", "feat-a", "--name", "n",
                                "--command", "c", "--artifact", str(BASE / "nope.txt"),
                                "--actor", "a1", expect=2))
rec = run("evidence-record", "--feature", "feat-a", "--name", "ok", "--command", "c",
          "--artifact", str(art), "--actor", "a1")
print("带产物 ->", rec)
print("空 name ->", run("evidence-record", "--feature", "feat-a", "--name", " ",
                        "--command", "c", "--actor", "a1", expect=2))
print("feat 不存在 ->", run("evidence-record", "--feature", "nope", "--name", "n",
                            "--command", "c", "--actor", "a1", expect=2))
print("work 属于别的 feature ->", run("evidence-record", "--feature", "feat-b", "--name", "n",
                                      "--command", "c", "--work", "work:feat-a:g1:model-architecture",
                                      "--actor", "a1", expect=2))
run("feature-declare", "--id", "feat-a", "--name", "A2", "--statement", "s2",
    "--acceptance", "[]", "--constraints", "[]")
print("旧代 evidence（--work 锁代）->", run(
    "evidence-record", "--feature", "feat-a", "--name", "old", "--command", "c",
    "--work", "work:feat-a:g1:model-architecture", "--actor", "a1"))
listed = run("evidence-list", "--feature", "feat-a")
print("evidence-list 行数 ->", len(listed["evidence"]),
      "generations ->", [row["generation"] for row in listed["evidence"]])
print("evidence-list 的键 ->", sorted(listed["evidence"][0]))
print("evidence-list 缺 feature ->", run("evidence-list", "--feature", "nope", expect=2))

section("P15 输出形态 / 退出码")
print("upsert-node stdout 样例键 ->", sorted(a1))
print("retract stdout 键 ->", sorted(r2))
print("bite stdout 键 ->", sorted(b1))

section("P16 环境变量与全局状态")
env_actor = dict(ENV, WXG_ACTOR="env-actor")
proc = subprocess.run(
    [sys.executable, str(WXG), "--root", str(ROOT), "bite", "--node", "classifier:demo:a.py:OUT",
     "--verdict", "KEEP"],
    capture_output=True, text=True, encoding="utf-8", env=env_actor,
)
print("WXG_ACTOR 生效 ->", proc.returncode, json.loads(proc.stdout or "{}").get("actor"))
print("WXG_DB_URL 不存在时才用 sqlite ->", ENV.get("WXG_DB_URL"))
print("tmp:", BASE)
shutil.rmtree(BASE, ignore_errors=True)
