"""切片 13 追加探针：plan 的 unmapped 噪声、stale 计数、design 层与 break-set 阈值。"""

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
BASE = Path(__file__).resolve().parent / "_probe_13_tmp2"
ROOT = BASE / "state"
REPO = BASE / "repo"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

sys.path.insert(0, str(SKILL / "scripts"))


def run(*args):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
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
        raise SystemExit(f"失败 {args} rc={rc} {err}")
    return payload


def main():
    shutil.rmtree(BASE, ignore_errors=True)
    REPO.mkdir(parents=True)
    (REPO / "shop.py").write_text(
        "def a(x):\n    return len(x)\n\n\ndef b(x):\n    return max(x)\n", encoding="utf-8"
    )
    must("init")
    must("repo-add", "--id", "demo", "--path", str(REPO))
    must("feature-declare", "--id", "feat-k", "--name", "K", "--statement", "x",
         "--acceptance", "[]", "--constraints", "[]", "--no-coverage")
    must("import-file", "--file", str(REPO / "shop.py"), "--feature", "feat-k", "--prepare")
    scan = must("work-claim", "--role", "scan", "--actor", "p")
    must("import-file", "--file", str(REPO / "shop.py"), "--token", scan["claim_token"])

    rc, plan, _ = run("plan", "--feature", "feat-k")
    print("plan keys:", sorted(plan))
    print("level:", plan["level"], "nodes:", plan["node_count"], "edges:", plan["edge_count"],
          "excluded_unmapped:", plan["excluded_unmapped"])
    print("dangling count:", len(plan["dangling"]["unknown_endpoint"]),
          "sample:", plan["dangling"]["unknown_endpoint"][:5])
    rc, full, _ = run("plan", "--feature", "feat-k", "--include-unmapped")
    print("include-unmapped nodes/edges/dangling:", full["node_count"], full["edge_count"],
          len(full["dangling"]["unknown_endpoint"]))
    rc, design, err = run("plan", "--feature", "feat-k", "--level", "design")
    print("level=design:", [rc, design, err[:90]])

    # stale：改文件后重扫，旧节点标 stale；plan 计数
    (REPO / "shop.py").write_text("def a(x):\n    return len(x)\n", encoding="utf-8")
    prep = must("import-file", "--file", str(REPO / "shop.py"), "--feature", "feat-k", "--prepare")
    scan2 = must("work-claim", "--role", "scan", "--actor", "p")
    must("import-file", "--file", str(REPO / "shop.py"), "--token", scan2["claim_token"])
    conn = sqlite3.connect(ROOT / "graph.sqlite")
    try:
        stale = conn.execute("SELECT id FROM nodes WHERE stale=1").fetchall()
    finally:
        conn.close()
    print("stale rows:", stale)
    rc, plan2, _ = run("plan", "--feature", "feat-k")
    print("after rescan excluded_stale:", plan2["excluded_stale"], "nodes:", plan2["node_count"])

    # break-set 阈值：21 条依赖边 + 一个 2 环
    import whyexist.cycles as C

    nodes = [f"n{i}" for i in range(20)]
    edges = [(nodes[i], nodes[i + 1]) for i in range(19)] + [
        (nodes[0], nodes[1]), (nodes[1], nodes[0])
    ]
    print("21 边 + 2 环:", C.minimal_break_sets(nodes, edges)["truncated"],
          len(C.minimal_break_sets(nodes, edges)["break_sets"]))


if __name__ == "__main__":
    main()
