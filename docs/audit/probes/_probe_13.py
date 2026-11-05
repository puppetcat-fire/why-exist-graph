"""切片 13 行为探针：只读观察 CLI 契约，不修改源码。

在 docs/audit/_probe_13_tmp 下建临时状态库，逐条验证命令的退出码、产物与
--without/--break-set/--advise 的组合语义、apply 的原子性与写库旁路。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent
WXG = SKILL / "scripts" / "wxg.py"
BASE = Path(__file__).resolve().parent / "_probe_13_tmp"
ROOT = BASE / "state"
REPO = BASE / "repo"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

sys.path.insert(0, str(SKILL / "scripts"))


def show(label, value):
    print(f"== {label}: {json.dumps(value, ensure_ascii=False, default=str)}")


def run(*args):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(ROOT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ENV,
    )
    out = proc.stdout.strip()
    try:
        payload = json.loads(out) if out else None
    except json.JSONDecodeError:
        payload = out
    return proc.returncode, payload, proc.stderr.strip()


def must(*args):
    rc, payload, err = run(*args)
    if rc != 0:
        raise SystemExit(f"失败 {args} rc={rc} err={err}")
    return payload


def db():
    return sqlite3.connect(ROOT / "graph.sqlite")


def main():
    shutil.rmtree(BASE, ignore_errors=True)
    REPO.mkdir(parents=True)
    (REPO / "shop.py").write_text(
        '"""probe"""\n\n\nclass OrderRepo:\n    def save(self, order):\n        return order\n',
        encoding="utf-8",
    )
    must("init")
    must("repo-add", "--id", "demo", "--path", str(REPO))
    must(
        "feature-declare", "--id", "feat-c", "--name", "C",
        "--statement", "创建订单。",
        "--acceptance", json.dumps(["ok"], ensure_ascii=False),
        "--constraints", json.dumps(["no"], ensure_ascii=False),
        "--no-coverage",
    )
    must(
        "work-open", "--feature", "feat-c", "--kind", "model-architecture",
        "--target-ids", json.dumps(["component:demo:*"]),
    )
    claim = must("work-claim", "--role", "model-architecture", "--actor", "probe")
    token = claim["claim_token"]
    work_id = claim["work_item_id"]
    for nid in ("component:demo:a", "component:demo:b", "component:demo:c"):
        must("upsert-node", "--token", token, "--data",
             json.dumps({"id": nid, "kind": "component", "name": nid[-1], "attrs": {"duty": nid[-1]}}))
    for src, dst in (("component:demo:a", "component:demo:b"), ("component:demo:b", "component:demo:a")):
        must("upsert-edge", "--token", token, "--data",
             json.dumps({"src": src, "dst": dst, "kind": "depends"}))
    must("work-finish", "--token", token)

    # 1. cycles --without 与 --break-set / --advise 的组合
    show("cycles 基准 break_sets", must("cycles", "--feature", "feat-c", "--break-set")["break_sets"])
    forced = must("cycles", "--feature", "feat-c", "--without",
                  "component:demo:a->component:demo:b", "--break-set")
    show("cycles --without + --break-set cycle_count", forced["cycle_count"])
    show("cycles --without + --break-set break_sets", forced["break_sets"])
    advised = must("cycles", "--feature", "feat-c", "--without",
                   "component:demo:a->component:demo:b", "--advise")
    show("cycles --without + --advise cycle_count", advised["cycle_count"])
    show("cycles --without + --advise advice", advised["advice"])

    # 2. 分析类命令的 FAIL/冲突退出码
    bad = BASE / "bad.json"
    bad.write_text(json.dumps({"nodes": [{"id": "component:other:x", "kind": "component"}]},
                              ensure_ascii=False), encoding="utf-8")
    rc, payload, _ = run("blind-check", "--work", work_id, "--result", str(bad))
    show("blind-check FAIL 退出码", [rc, payload["verdict"]])

    arr = BASE / "arr.json"
    arr.write_text("[1,2]", encoding="utf-8")
    rc, payload, err = run("blind-check", "--work", work_id, "--result", str(arr))
    show("blind-check 顶层数组", [rc, payload])

    rc, payload, err = run("impact", "--feature", "feat-c", "--changed", "component:demo:c")
    show("impact uncovered 退出码", [rc, payload["closed"], payload["uncovered"]])

    # 3. conflicts：重叠 + 退出码 + --features 子集
    must("feature-declare", "--id", "feat-d", "--name", "D", "--statement", "x",
         "--acceptance", "[]", "--constraints", "[]", "--no-coverage")
    must("work-open", "--feature", "feat-d", "--kind", "model-architecture",
         "--target-ids", json.dumps(["component:demo:a"]))
    rc, payload, _ = run("conflicts")
    show("conflicts 重叠退出码", [rc, payload["coexist_ok"], len(payload["conflicts"])])
    rc, payload, _ = run("conflicts", "--features", "feat-c,feat-d")
    show("conflicts --features 子集", [rc, [c["a"] for c in payload["conflicts"]]])
    rc, payload, _ = run("conflicts", "--features", "feat-missing")
    show("conflicts 未知 feature", [rc, payload])

    # 4. plan：CLI 与 Engine 的字段差异
    rc, cli_plan, _ = run("plan", "--feature", "feat-c", "--level", "code")
    show("CLI plan --level code keys", [rc, sorted(cli_plan), cli_plan.get("hint")])
    from whyexist import Engine

    with Engine(ROOT) as engine:
        eng_plan = engine.plan("feat-c", level="code")
        eng_plan_design = engine.plan("feat-c")
    show("Engine plan --level code keys", [sorted(eng_plan), eng_plan.get("hint")])
    show("Engine plan 默认 level", [eng_plan_design["level"], eng_plan_design["node_count"]])
    rc, cli_plan_design, _ = run("plan", "--feature", "feat-c")
    show("CLI plan 默认", [rc, cli_plan_design["level"], cli_plan_design["node_count"],
                          cli_plan_design["parallelism"], cli_plan_design["bottleneck"]])

    # 5. brief --out 分支
    out_file = BASE / "brief.json"
    rc, payload, _ = run("brief", "--work", work_id, "--out", str(out_file))
    show("brief --out 返回", [rc, payload])
    show("brief --out 文件键", sorted(json.loads(out_file.read_text(encoding="utf-8"))))
    rc, payload, err = run("brief", "--work", work_id, "--out", str(BASE / "no-such-dir" / "x.json"))
    show("brief --out 不可写路径", [rc, payload])

    # 6. patch：不校验工单存在
    body = BASE / "out1.json"
    body.write_text(json.dumps({"nodes": [{"id": "component:demo:p", "kind": "component",
                                           "name": "P", "attrs": {"duty": "p"}}]},
                               ensure_ascii=False), encoding="utf-8")
    patch_file = BASE / "p1.json"
    rc, payload, _ = run("patch", "--work", "work:does-not-exist", "--result", str(body),
                         "--out", str(patch_file))
    show("patch 未知工单", [rc, payload])
    show("patch 文件内容", json.loads(patch_file.read_text(encoding="utf-8")))

    # 7. apply：原子性（边校验失败时节点是否落库）
    bad_patch = BASE / "bad-apply.json"
    bad_patch.write_text(json.dumps({
        "work_item": "w-atomic",
        "nodes": [{"id": "component:demo:atom", "kind": "component", "name": "A",
                   "attrs": {"duty": "a"}}],
        "edges": [{"src": "component:demo:atom", "dst": "component:demo:a", "kind": "applies"}],
    }, ensure_ascii=False), encoding="utf-8")
    rc, payload, err = run("apply", "--patches", str(bad_patch))
    conn = db()
    try:
        row = conn.execute("SELECT id FROM nodes WHERE id='component:demo:atom'").fetchone()
    finally:
        conn.close()
    show("apply 边校验失败", [rc, payload, err[:80], "atom_in_db", bool(row)])

    # 8. apply 旁路：origin / stale / unmapped / feature_id 透传
    bypass = BASE / "bypass.json"
    bypass.write_text(json.dumps({
        "work_item": "w-bypass",
        "nodes": [{"id": "component:demo:bypass", "kind": "component", "name": "B",
                   "origin": "derived", "stale": 1, "unmapped": 1, "feature_id": "feat-d"}],
    }, ensure_ascii=False), encoding="utf-8")
    rc, payload, err = run("apply", "--patches", str(bypass))
    conn = db()
    try:
        row = conn.execute(
            "SELECT origin, stale, unmapped FROM nodes WHERE id='component:demo:bypass'"
        ).fetchone()
        link = conn.execute(
            "SELECT feature_id FROM feature_nodes WHERE node_id='component:demo:bypass'"
        ).fetchall()
    finally:
        conn.close()
    show("apply 透传字段", [rc, payload, row, link])

    # 9. apply --dry-run 在冲突时的退出码
    c1 = BASE / "c1.json"
    c1.write_text(json.dumps({"work_item": "w1", "nodes": [
        {"id": "component:demo:dup", "kind": "component", "name": "X", "attrs": {"duty": "one"}}]}),
        encoding="utf-8")
    c2 = BASE / "c2.json"
    c2.write_text(json.dumps({"work_item": "w2", "nodes": [
        {"id": "component:demo:dup", "kind": "component", "name": "X", "attrs": {"duty": "two"}}]}),
        encoding="utf-8")
    rc, payload, _ = run("apply", "--patches", f"{c1},{c2}", "--dry-run")
    show("apply --dry-run 冲突", [rc, payload["ok"], payload["applied"]])
    rc, payload, _ = run("apply", "--patches", "")
    show("apply 空 patches", [rc, payload])

    # 10. impact 两种模式同时给
    rc, payload, _ = run("impact", "--feature", "feat-c", "--changed", "component:demo:c",
                         "--remove-edges", "component:demo:a->component:demo:b")
    show("impact 双模式", [rc, payload.get("mode"), sorted(payload)])

    # 11. impact 未知边的 --remove-edges / @文件 --changed
    rc, payload, _ = run("impact", "--feature", "feat-c", "--remove-edges",
                         "component:demo:zzz->component:demo:yyy")
    show("impact 未知边 remove-edges", [rc, payload["removed"], payload["closed"]])
    ids_file = BASE / "ids.json"
    ids_file.write_text(json.dumps(["component:demo:b"]), encoding="utf-8")
    rc, payload, _ = run("impact", "--feature", "feat-c", "--changed", f"@{ids_file}")
    show("impact @文件 changed", [rc, payload["changed"]])

    # 12. cycles --without 非法格式
    rc, payload, _ = run("cycles", "--feature", "feat-c", "--without", "nope")
    show("cycles --without 非法", [rc, payload])
    rc, payload, _ = run("cycles", "--feature", "feat-c", "--without",
                         "component:demo:a->component:other:q")
    show("cycles --without 界外端点", [rc, payload])


if __name__ == "__main__":
    main()
