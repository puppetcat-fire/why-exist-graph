"""slice 10 探针 C：serve 遇到坏 feature 是否整轮中止；reconcile 动作清单。"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent
WXG = SKILL / "scripts" / "wxg.py"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
sys.path.insert(0, str(SKILL / "scripts"))
import wxg  # noqa: E402

OUT = []


def run(root, *args):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    text = proc.stdout.strip()
    try:
        payload = json.loads(text) if text else {}
    except json.JSONDecodeError:
        payload = text
    return proc.returncode, payload, proc.stderr.strip(), proc.stdout


tmp = Path(wxg.make_temp_dir("wxg-probe10c-")).resolve()
root = tmp / "state"
run(root, "init")
for fid in ("feat-ok", "feat-broken"):
    run(root, "feature-declare", "--id", fid, "--name", fid, "--statement", "s",
        "--acceptance", "[]", "--constraints", "[]", "--no-coverage")
c = sqlite3.connect(root / "graph.sqlite")
c.execute("DELETE FROM conditions WHERE feature_id='feat-broken' AND name='Ready'")
c.execute("UPDATE work_items SET status='ready', fail_reason='上次失败' WHERE id='work:feat-ok:g1:model-architecture'")
c.commit()
c.close()

rc, payload, err, stdout = run(root, "serve", "--once")
OUT.append({"probe": "R1-serve-broken-feature", "rc": rc, "stdout": stdout.strip(),
            "stderr": err, "payload": payload})

# 单独看 feat-ok 的 reconcile 动作（retry 是否存在、是否影响 converged）
rc, rec, err, _ = run(root, "reconcile", "--feature", "feat-ok")
OUT.append({"probe": "R2-reconcile-retry-action", "rc": rc,
            "actions": rec.get("actions"), "converged": rec.get("converged")})

# 坏 feature 上 gate / coverage 的退出码
rc, gate, err, _ = run(root, "gate", "--feature", "feat-broken", "--json")
OUT.append({"probe": "R3-gate-broken-feature", "rc": rc, "stdout": gate, "stderr": err})
rc, cov, err, _ = run(root, "coverage", "--feature", "feat-broken")
OUT.append({"probe": "R4-coverage-broken-feature", "rc": rc, "stdout": cov, "stderr": err})
rc, conf, err, _ = run(root, "conformance", "--feature", "feat-broken")
OUT.append({"probe": "R5-conformance-broken-feature", "rc": rc, "stdout": conf, "stderr": err})

# stale-node / construction-open 动作
c = sqlite3.connect(root / "graph.sqlite")
c.execute("INSERT INTO nodes(id, kind, name) VALUES('operation:x:stale','operation','op')")
c.execute("INSERT INTO feature_nodes(feature_id, node_id) VALUES('feat-ok','operation:x:stale')")
c.execute("UPDATE nodes SET stale=1 WHERE id='operation:x:stale'")
c.commit()
c.close()
rc, rec, err, _ = run(root, "reconcile", "--feature", "feat-ok")
OUT.append({"probe": "R6-stale-node-action", "rc": rc,
            "actions": [a.get("action") for a in rec.get("actions", [])],
            "converged": rec.get("converged")})

print(json.dumps(OUT, ensure_ascii=False, indent=2))
