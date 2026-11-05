"""切片 13 第三探针：stale 排除计数（只在临时状态库上改数据）。"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent
WXG = SKILL / "scripts" / "wxg.py"
ROOT = Path(__file__).resolve().parent / "_probe_13_tmp2" / "state"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(*args):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(ROOT), *args],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    out = proc.stdout.strip()
    return proc.returncode, json.loads(out) if out else None, proc.stderr.strip()


def main():
    conn = sqlite3.connect(ROOT / "graph.sqlite")
    try:
        rows = conn.execute("SELECT id, kind, stale FROM nodes ORDER BY id").fetchall()
        print("nodes:", rows)
        conn.execute("UPDATE nodes SET stale=1 WHERE id='operation:demo:shop.py:b'")
        conn.commit()
    finally:
        conn.close()
    rc, plan, err = run("plan", "--feature", "feat-k")
    print("plan after stale:", rc, {k: plan[k] for k in
          ("level", "node_count", "edge_count", "excluded_unmapped", "excluded_stale")})
    conn = sqlite3.connect(ROOT / "graph.sqlite")
    try:
        conn.execute("UPDATE nodes SET stale=0")
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
