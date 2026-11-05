"""Slice 09 edge-case probes (state left in docs/audit/_probe_09_tmp)."""
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJ = HERE.parent.parent
WXG = PROJ / "scripts" / "wxg.py"
BASE = HERE / "_probe_09b_tmp"
ENV = dict(os.environ, PYTHONUTF8="1")
STATE = BASE / "default"
if BASE.exists():
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)


def run(*args, expect=0):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(STATE), *map(str, args)],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    out = proc.stdout.strip()
    try:
        data = json.loads(out) if out else {}
    except json.JSONDecodeError:
        data = out
    if proc.returncode != expect:
        print("!! UNEXPECTED RC", args, "->", proc.returncode, "expected", expect)
        print("   stderr:", proc.stderr.strip()[:300].replace("\n", " "))
    if proc.returncode != 0:
        try:
            data = {"_rc": proc.returncode, "error": json.loads(proc.stderr.strip())["error"]}
        except (json.JSONDecodeError, KeyError):
            data = {"_rc": proc.returncode, "error": proc.stderr.strip()[:200]}
    return data


def sql(statement, params=()):
    conn = sqlite3.connect(STATE / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute(statement, params).fetchall()]
        conn.commit()
        return rows
    finally:
        conn.close()


def show(title, value):
    print("\n##", title)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def declare(fid, *extra):
    return run("feature-declare", "--id", fid, "--name", fid, "--statement", "s",
               "--acceptance", '["a"]', "--constraints", '["c"]', *extra)


STATE.mkdir(parents=True, exist_ok=True)
run("init")

# E1 broken conditions row breaks whole feature listing
declare("feat-a")
declare("feat-b")
sql("DELETE FROM conditions WHERE feature_id='feat-a' AND generation=1 AND name='Ready'")
show("E1.1 feature-list with one corrupt feature", run("feature-list", expect=2))
show("E1.2 feature-status on corrupt feature", run("feature-status", "--id", "feat-a", expect=2))
show("E1.3 feature-status on healthy feature", {
    "rc_ok": bool(run("feature-status", "--id", "feat-b").get("feature")),
})
show("E1.4 work-seed on corrupt feature", run("work-seed", "--feature", "feat-a", expect=2))

# E2 actor validation
run("work-open", "--feature", "feat-b", "--kind", "model-architecture", "--target-ids", '["x:*"]')
show("E2.1 actor with space", run("work-claim", "--role", "model-architecture",
                                  "--actor", "a b", expect=2))
show("E2.2 actor 81 chars", run("work-claim", "--role", "model-architecture",
                                "--actor", "x" * 81, expect=2))
show("E2.3 actor 80 chars", run("work-claim", "--role", "model-architecture",
                                "--actor", "x" * 80))

# E3 brief still returns full target_ids
big = [f"node:{i}" for i in range(400)]
run("work-open", "--feature", "feat-b", "--kind", "scan", "--target-ids", json.dumps(big))
claimed = run("work-claim", "--role", "scan", "--actor", "a", "--brief")
show("E3.1 brief slice keys", sorted(claimed["slice"]))
show("E3.2 brief target_ids size", {"n": len(claimed["target_ids"]),
                                    "chars": len(json.dumps(claimed["target_ids"]))})

# E4 register-created feature then declare keeps coverage off
run("feature-register", "--id", "feat-r", "--name", "R",
    "--spec", '{"statement":"s","acceptance":["a"],"constraints":["c"]}')
show("E4.1 register row", sql("SELECT coverage_epsilon,drift_limit,conformance FROM features WHERE id='feat-r'"))
declare("feat-r")
show("E4.2 declare after register", sql(
    "SELECT generation,coverage_epsilon,drift_limit,conformance FROM features WHERE id='feat-r'"))
show("E4.3 status coverage", run("feature-status", "--id", "feat-r")["coverage"]["enforced"])

# E5 assignee/claimed_by after finish/judge
STATE = BASE / "e5"
STATE.mkdir(parents=True, exist_ok=True)
run("init")
declare("feat-j")
run("work-open", "--feature", "feat-j", "--kind", "model-architecture",
    "--target-ids", '["use_case:feat-j:*"]')
c = run("work-claim", "--role", "model-architecture", "--actor", "agent-j")
run("upsert-node", "--token", c["claim_token"],
    "--data", '{"id":"use_case:feat-j:uc","kind":"use_case","name":"uc"}')
run("work-finish", "--token", c["claim_token"])
show("E5.1 after finish", sql(
    "SELECT id,status,assignee,claimed_by,claim_token,judged_by,judged_at FROM work_items "
    "WHERE feature_id='feat-j' ORDER BY id"))
run("work-judge", "--id", c["work_item_id"], "--verdict", "passed", "--actor", "auditor-1")
show("E5.2 after judge", sql(
    "SELECT id,status,assignee,claimed_by,claim_token,judged_by,judged_at FROM work_items "
    "WHERE feature_id='feat-j' ORDER BY id"))

# E6 change-open --from-condition rejected at argparse (BITE condition outside map)
raw = sql("SELECT generation FROM features WHERE id='feat-j'")
sql("UPDATE conditions SET status=1 WHERE feature_id='feat-j'")
show("E6.1 from-condition Accepted rejected", run(
    "change-open", "--feature", "feat-j", "--statement", "s",
    "--from-condition", "Accepted", expect=2))
show("E6.2 from-condition Ready rejected", run(
    "change-open", "--feature", "feat-j", "--statement", "s",
    "--from-condition", "Ready", expect=2))
show("E6.3 invalid change-diff baseline", run(
    "change-diff", "--feature", "feat-j", "--from-generation", "-1", expect=2))

# E7 scan ticket judged passed leaves conditions untouched
run("work-open", "--feature", "feat-j", "--kind", "scan", "--target-ids", '["classifier:demo:*"]')
scan = run("work-claim", "--role", "scan", "--actor", "scanner")
run("work-finish", "--token", scan["claim_token"])
before = sql("SELECT name,status FROM conditions WHERE feature_id='feat-j' ORDER BY rowid")
show("E7.1 scan judge passed", run(
    "work-judge", "--id", scan["work_item_id"], "--verdict", "passed", "--actor", "auditor-2"))
show("E7.2 conditions unchanged", before == sql(
    "SELECT name,status FROM conditions WHERE feature_id='feat-j' ORDER BY rowid"))
show("E7.3 judge_history for scan", sql(
    "SELECT work_item_id,kind,verdict,actor FROM judge_history WHERE work_item_id=?",
    (scan["work_item_id"],)))

# E8 redeclare keeps requirement attrs written by others
sql("UPDATE nodes SET attrs_json='{\"statement\":\"s\",\"note\":\"hand\"}' "
    "WHERE id='requirement:feat-j:main'")
declare("feat-j")
show("E8.1 requirement attrs after redeclare", sql(
    "SELECT attrs_json FROM nodes WHERE id='requirement:feat-j:main'"))
show("E8.2 old generation conditions kept", sql(
    "SELECT generation,count(*) n FROM conditions WHERE feature_id='feat-j' GROUP BY generation"))

print("\n## done")
