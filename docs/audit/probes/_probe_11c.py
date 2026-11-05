"""审计切片 11 探针（三）：修正角色——scan 能 upsert-node/retract，model-architecture 能 upsert-edge。"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
WXG = SKILL / "scripts" / "wxg.py"
BASE = Path(tempfile.mkdtemp(prefix="wxg-probe-11c-"))
ROOT = BASE / "state"
ENV = {k: v for k, v in os.environ.items() if not k.startswith("WXG_")}
ENV["PYTHONUTF8"] = "1"


def run(*args, expect=0, env=None):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", env=env or ENV,
    )
    out = proc.stdout.strip()
    try:
        parsed = json.loads(out) if out else None
    except json.JSONDecodeError:
        parsed = out
    if proc.returncode != expect:
        parsed = {"__rc": proc.returncode, "__stderr": proc.stderr.strip()[-400:]}
    return parsed


def db():
    conn = sqlite3.connect(ROOT / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def one(sql, params=()):
    conn = db()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def node(nid):
    rows = one("SELECT id, unmapped, stale, attrs_json FROM nodes WHERE id=?", (nid,))
    return dict(rows[0]) if rows else None


def snap():
    conn = db()
    try:
        return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")]
                for t in ("nodes", "edges", "bites", "feature_nodes", "work_items")}
    finally:
        conn.close()


def section(title):
    print(f"\n===== {title}")


run("init")
run("feature-declare", "--id", "feat-a", "--name", "A", "--statement", "s",
    "--acceptance", "[]", "--constraints", "[]")
run("feature-declare", "--id", "feat-b", "--name", "B", "--statement", "s",
    "--acceptance", "[]", "--constraints", "[]")
run("work-open", "--feature", "feat-a", "--kind", "scan", "--target-ids", '["*"]')
tScan = run("work-claim", "--role", "scan", "--actor", "agent-scan")["claim_token"]
run("work-open", "--feature", "feat-a", "--kind", "model-architecture", "--target-ids", '["*"]')
tArch = run("work-claim", "--role", "model-architecture", "--actor", "agent-arch")["claim_token"]
run("work-open", "--feature", "feat-b", "--kind", "scan", "--target-ids", '["requirement:feat-b:*"]')
scan_b = run("work-claim", "--role", "scan", "--actor", "agent-scan")
tScanB = scan_b["claim_token"]

section("S1 角色矩阵实测定论（同一节点、不同角色 token）")
run("upsert-node", "--token", tScan, "--data", json.dumps({"id": "classifier:demo:m1", "kind": "classifier", "name": "m1"}))
print("scan: upsert-node 成功、retract ->", run("retract", "--token", tScan, "--node-ids", "classifier:demo:m1"))
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "classifier:demo:m2", "kind": "classifier", "name": "m2"}))
print("model-architecture: retract ->", run("retract", "--token", tArch, "--node-ids", "classifier:demo:m2", expect=2))
print("scan: upsert-edge ->", run("upsert-edge", "--token", tScan, "--data", json.dumps(
    {"src": "component:demo:keep", "dst": "component:demo:keep2", "kind": "depends"}), expect=2))
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "component:demo:keep", "kind": "component", "name": "k"}))
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "component:demo:keep2", "kind": "component", "name": "k2"}))
print("model-architecture: upsert-edge ->", run("upsert-edge", "--token", tArch, "--data", json.dumps(
    {"src": "component:demo:keep", "dst": "component:demo:keep2", "kind": "depends"})))

section("S2 retract 级联：边（含 target 外端点）与 bite")
run("upsert-node", "--token", tScan, "--data", json.dumps({"id": "classifier:demo:delme", "kind": "classifier", "name": "del"}))
print("建边 keep->delme ->", run("upsert-edge", "--token", tArch, "--data", json.dumps(
    {"src": "component:demo:keep", "dst": "classifier:demo:delme", "kind": "contains"})))
run("bite", "--node", "classifier:demo:delme", "--verdict", "UNMAPPED", "--feature", "feat-b", "--actor", "leady")
conn = db()
conn.execute("UPDATE work_items SET evidence_ids=? WHERE id=?", (json.dumps(["classifier:demo:delme"]), scan_b["work_item_id"]))
conn.commit()
conn.close()
print("删前边 ->", [tuple(x) for x in one("SELECT id, src, dst FROM edges WHERE src='classifier:demo:delme' OR dst='classifier:demo:delme'")])
print("retract ->", run("retract", "--token", tScan, "--node-ids", "classifier:demo:delme"))
print("删后 -> node:", node("classifier:demo:delme"),
      "边:", [tuple(x) for x in one("SELECT id FROM edges WHERE src='classifier:demo:delme' OR dst='classifier:demo:delme'")],
      "bite:", [tuple(x) for x in one("SELECT node_id FROM bites WHERE node_id='classifier:demo:delme'")],
      "feature_nodes:", one("SELECT * FROM feature_nodes WHERE node_id='classifier:demo:delme'"))
print("feat-b 工单 evidence_ids 被清 ->", [tuple(x) for x in one(
    "SELECT target_ids, evidence_ids FROM work_items WHERE id=?", (scan_b["work_item_id"],))])
print("feat-a scan 工单 evidence_ids ->", [tuple(x) for x in one(
    "SELECT evidence_ids FROM work_items WHERE id=?", ((run("work-list", "--feature", "feat-a")["work_items"][0]["id"]),))])

section("S3 retract 边界洞：删节点会连带删掉 target 外的边")
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "component:demo:outA", "kind": "component", "name": "A"}))
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "component:demo:outB", "kind": "component", "name": "B"}))
run("upsert-edge", "--token", tArch, "--data", json.dumps(
    {"src": "component:demo:outA", "dst": "component:demo:outB", "kind": "depends"}))
conn = db()
scan_a = one("SELECT id FROM work_items WHERE feature_id='feat-a' AND kind='scan'")[0][0]
conn.execute("UPDATE work_items SET target_ids=? WHERE id=?", (json.dumps(["component:demo:outA"]), scan_a))
conn.commit()
conn.close()
print("target 只剩 outA，retract outA ->", run("retract", "--token", tScan, "--node-ids", "component:demo:outA"))
print("outA->outB 边被连带删除 ->", one("SELECT id FROM edges WHERE id='edge:depends:component:demo:outA:component:demo:outB'"))

section("S4 回滚：同一次调用里 node 在 target、edge 端点不在")
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "component:demo:r1", "kind": "component", "name": "r1"}))
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "component:demo:r2", "kind": "component", "name": "r2"}))
run("upsert-node", "--token", tArch, "--data", json.dumps({"id": "component:demo:r3", "kind": "component", "name": "r3"}))
run("upsert-edge", "--token", tArch, "--data", json.dumps(
    {"src": "component:demo:r3", "dst": "component:demo:r2", "kind": "associates"}))
conn = db()
conn.execute("UPDATE work_items SET target_ids=? WHERE id=?",
             (json.dumps(["component:demo:r1", "component:demo:r2"]), scan_a))
conn.commit()
conn.close()
before = snap()
print("r1 在 target、r3 的边不在 ->", run(
    "retract", "--token", tScan, "--node-ids", "component:demo:r1",
    "--edge-ids", "edge:associates:component:demo:r3:component:demo:r2", expect=2))
after = snap()
print("回滚后 r1 存在 ->", node("component:demo:r1") is not None, "全表快照未变 ->", before == after)

section("S5 显式 edge-ids（端点都在 target 内）")
conn = db()
conn.execute("UPDATE work_items SET target_ids=? WHERE id=?",
             (json.dumps(["component:demo:r1", "component:demo:r2"]), scan_a))
conn.commit()
conn.close()
run("upsert-edge", "--token", tArch, "--data", json.dumps(
    {"src": "component:demo:r1", "dst": "component:demo:r2", "kind": "depends"}))
eid = "edge:depends:component:demo:r1:component:demo:r2"
print("删一次 ->", run("retract", "--token", tScan, "--edge-ids", eid))
print("再删 ->", run("retract", "--token", tScan, "--edge-ids", eid))
print("删不存在 node ->", run("retract", "--token", tScan, "--node-ids", "component:demo:ghost"))
print("空参数 ->", run("retract", "--token", tScan))

section("S6 bite 作用域：--feature 不校验 target，写 feature_nodes 扩大 scope")
print("upsert outside ->", run("upsert-node", "--token", tArch, "--data", json.dumps(
    {"id": "classifier:demo:outside", "kind": "classifier", "name": "o"})))
cov0 = run("coverage", "--feature", "feat-b")["scope_size"]
print("feat-b target 只有 requirement:*；bite 别的节点 ->",
      run("bite", "--node", "classifier:demo:outside", "--verdict", "HOLLOW",
          "--feature", "feat-b", "--actor", "leady"))
cov1 = run("coverage", "--feature", "feat-b")["scope_size"]
print("scope_size:", cov0, "->", cov1)
print("feature_nodes(feat-b) ->", [tuple(x) for x in one(
    "SELECT * FROM feature_nodes WHERE feature_id='feat-b' ORDER BY 2")])
print("bite 无 feature（feature_id/generation/phase 为 NULL）->",
      run("bite", "--node", "classifier:demo:outside", "--verdict", "KEEP", "--actor", "leady"))
print("bites ->", [tuple(x) for x in one(
    "SELECT node_id, feature_id, generation, phase, verdict FROM bites WHERE node_id='classifier:demo:outside' ORDER BY id")])
print("node.attrs / unmapped ->", node("classifier:demo:outside"))

section("S7 WXG_ACTOR / 缺 actor / argparse")
env_actor = dict(ENV, WXG_ACTOR="env-actor")
print("WXG_ACTOR 生效 ->", run("bite", "--node", "classifier:demo:outside", "--verdict", "KEEP",
                                "--feature", "feat-b", env=env_actor))
print("bite 缺 actor ->", run("bite", "--node", "classifier:demo:outside", "--verdict", "KEEP", expect=2))
print("evidence-record 缺 actor ->", run("evidence-record", "--feature", "feat-b",
                                         "--name", "n", "--command", "c", expect=2))
print("upsert-node 缺 --token（argparse）->", run("upsert-node", "--data", "{}", expect=2))
print("bind 缺 --bind-to（argparse）->", run("bind", "--token", tScan, "--node-id", "x", expect=2))
print("bite 缺 --verdict（argparse）->", run("bite", "--node", "x", "--actor", "a", expect=2))
print("无效 token ->", run("upsert-node", "--token", "deadbeef", "--data",
                            json.dumps({"id": "classifier:demo:z", "kind": "classifier"}), expect=2))

section("S8 feature_nodes 归属（token feature 自动挂；payload.feature_id 也挂）")
print("upsert own ->", run("upsert-node", "--token", tArch, "--data", json.dumps(
    {"id": "classifier:demo:own", "kind": "classifier", "name": "own"})))
print("upsert own2 with feature_id=feat-b ->", run("upsert-node", "--token", tArch, "--data", json.dumps(
    {"id": "classifier:demo:own2", "kind": "classifier", "name": "own2", "feature_id": "feat-b"})))
print("feature_nodes ->", [tuple(x) for x in one(
    "SELECT * FROM feature_nodes WHERE node_id LIKE 'classifier:demo:own%' ORDER BY 2")])

print("\ntmp:", BASE)
