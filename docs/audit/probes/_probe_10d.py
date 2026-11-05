"""slice 10 探针 D：reconcile 的只读待办动作（coverage-gap / drift-over-limit / construction-open）。"""
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
    return proc.returncode, payload, proc.stderr.strip()


tmp = Path(wxg.make_temp_dir("wxg-probe10d-")).resolve()
root = tmp / "state"
run(root, "init")
run(root, "feature-declare", "--id", "feat-acts", "--name", "a", "--statement", "s",
    "--acceptance", "[]", "--constraints", "[]", "--coverage-epsilon", "0.05",
    "--drift-limit", "0", "--conformance")
c = sqlite3.connect(root / "graph.sqlite")
c.execute("INSERT INTO nodes(id, kind, name) VALUES('operation:x:done','operation','op')")
c.execute("INSERT INTO feature_nodes(feature_id, node_id) VALUES('feat-acts','operation:x:done')")
c.execute("UPDATE nodes SET attrs_json='{\"construction\": true}' WHERE id='operation:x:done'")
c.execute("INSERT INTO bites(node_id, feature_id, generation, phase, verdict, reason, actor, created_at) "
          "VALUES('operation:x:done','feat-acts',1,'ArchitectureReconciled','UNMAPPED','x','a','2026-01-01T00:00:00Z')")
c.commit()
c.close()

rc, rec, err = run(root, "reconcile", "--feature", "feat-acts")
OUT.append({"probe": "D1-actions", "rc": rc,
            "actions": rec.get("actions"), "converged": rec.get("converged")})
rc, rec2, err = run(root, "reconcile", "--feature", "feat-acts", "--apply")
OUT.append({"probe": "D2-apply-does-not-fix", "rc": rc, "applied": rec2.get("applied"),
            "actions": [a.get("action") for a in rec2.get("actions", [])],
            "converged": rec2.get("converged")})

print(json.dumps(OUT, ensure_ascii=False, indent=2))
