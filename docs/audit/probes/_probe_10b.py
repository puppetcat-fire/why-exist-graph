"""slice 10 探针 B：reconcile/serve/coverage 参数边界与覆盖计数语义。"""
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


tmp = Path(wxg.make_temp_dir("wxg-probe10b-")).resolve()
root = tmp / "state"
rep = tmp / "repo"
rep.mkdir()
(rep / "shop.py").write_text("def f():\n    return 1\n", encoding="utf-8")
run(root, "init")
run(root, "repo-add", "--id", "demo", "--path", str(rep))
run(root, "feature-declare", "--id", "feat-t", "--name", "t", "--statement", "s",
    "--acceptance", "[]", "--constraints", "[]", "--no-coverage")

# Q1 ttl=0 回收“刚刚领取”的 claim
rc, claim, err = run(root, "work-claim", "--role", "model-architecture", "--actor", "a")
c = sqlite3.connect(root / "graph.sqlite")
claimed_at = c.execute("SELECT claimed_at FROM work_items WHERE id=?", (claim["work_item_id"],)).fetchone()[0]
c.close()
rc_d, dry, err_d = run(root, "reconcile", "--feature", "feat-t", "--claim-ttl", "0")
rc_a, applied, err_a = run(root, "reconcile", "--feature", "feat-t", "--claim-ttl", "0", "--apply")
c = sqlite3.connect(root / "graph.sqlite")
status = c.execute("SELECT status, claim_token FROM work_items WHERE id=?", (claim["work_item_id"],)).fetchone()
c.close()
OUT.append({"probe": "Q1-ttl-zero", "claim_rc": rc, "claimed_at": claimed_at,
            "dry_rc": rc_d, "dry_actions": dry.get("actions"), "dry_converged": dry.get("converged"),
            "apply_rc": rc_a, "applied": applied.get("applied"),
            "row_after": status})

# Q2 serve 即使未收敛也退出 0
rc, serve, err = run(root, "serve", "--once")
OUT.append({"probe": "Q2-serve-unconverged-exit", "rc": rc,
            "converged": serve.get("converged") if isinstance(serve, dict) else serve})

# Q3 coverage 参数不校验
rc, cov, err = run(root, "coverage", "--feature", "feat-t", "--epsilon", "-1")
OUT.append({"probe": "Q3a-coverage-negative-epsilon", "rc": rc, "epsilon": cov.get("epsilon"),
            "enforced": cov.get("enforced"), "next": cov.get("next"),
            "phase0": (cov.get("phases") or [{}])[0]})
rc, cov, err = run(root, "coverage", "--feature", "feat-t", "--prior-p", "2")
OUT.append({"probe": "Q3b-coverage-prior-out-of-range", "rc": rc, "prior_p": cov.get("prior_p"),
            "phase0": (cov.get("phases") or [{}])[0]})

# Q4 reconcile 参数/目标校验
rc, payload, err = run(root, "reconcile", "--feature", "feat-t", "--claim-ttl", "-1")
OUT.append({"probe": "Q4a-reconcile-negative-ttl", "rc": rc, "stderr": err})
rc, payload, err = run(root, "reconcile", "--feature", "nope")
OUT.append({"probe": "Q4b-reconcile-unknown-feature", "rc": rc, "stderr": err})

# Q5 覆盖 hits 是否只认“任一历史判决”(先 UNNECESSARY 再 KEEP 仍计命中)
run(root, "bite", "--node", "requirement:feat-t:main", "--verdict", "UNNECESSARY",
    "--feature", "feat-t", "--actor", "a")
run(root, "bite", "--node", "requirement:feat-t:main", "--verdict", "KEEP",
    "--feature", "feat-t", "--actor", "a")
rc, cov, err = run(root, "coverage", "--feature", "feat-t")
OUT.append({"probe": "Q5-hits-historical", "rc": rc, "phase0": (cov.get("phases") or [{}])[0]})

# Q6 conformance --limit 0：列表空、计数全、truncated
run(root, "feature-declare", "--id", "feat-c0", "--name", "c", "--statement", "s",
    "--acceptance", "[]", "--constraints", "[]", "--no-coverage", "--conformance")
c = sqlite3.connect(root / "graph.sqlite")
c.execute("INSERT INTO nodes(id, kind, name) VALUES('component:feat-c0:x','component','x')")
c.execute("INSERT INTO feature_nodes(feature_id, node_id) VALUES('feat-c0','component:feat-c0:x')")
c.commit()
c.close()
rc, conf, err = run(root, "conformance", "--feature", "feat-c0", "--limit", "0")
OUT.append({"probe": "Q6-conformance-limit-zero", "rc": rc, "anchors": conf.get("anchors"),
            "truncated": conf.get("truncated"), "violations": conf.get("violations")})
rc, payload, err = run(root, "conformance", "--feature", "feat-c0", "--limit", "-1")
OUT.append({"probe": "Q7-conformance-negative-limit", "rc": rc, "stderr": err})

# Q8 reconcile 的 gate 子对象与 actions 的关系
rc, rec, err = run(root, "reconcile", "--feature", "feat-t")
OUT.append({"probe": "Q8-reconcile-shape", "rc": rc, "keys": sorted(rec.keys()) if isinstance(rec, dict) else rec,
            "gate": rec.get("gate") if isinstance(rec, dict) else None,
            "pending": rec.get("pending") if isinstance(rec, dict) else None,
            "actions": [a.get("action") for a in rec.get("actions", [])] if isinstance(rec, dict) else None})

print(json.dumps(OUT, ensure_ascii=False, indent=2))
