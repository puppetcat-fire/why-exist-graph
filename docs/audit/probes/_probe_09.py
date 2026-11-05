"""Slice 09 probes: feature/change/work command family observable behaviour.

Read-only relative to the project: creates throwaway state dirs under docs/audit/_probe_09_tmp.
Each scenario gets its own --root so one feature's ready tickets cannot leak into another's claim.
"""
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
BASE = HERE / "_probe_09_tmp"
ENV = dict(os.environ, PYTHONUTF8="1")
STATE = BASE / "default"

if BASE.exists():
    shutil.rmtree(BASE)
BASE.mkdir(parents=True)


def root(name):
    global STATE
    STATE = BASE / name
    STATE.mkdir(parents=True, exist_ok=True)
    return run("init")


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
        print("   stdout:", out[:300].replace("\n", " "))
        print("   stderr:", proc.stderr.strip()[:300].replace("\n", " "))
    if proc.returncode != 0 and not data:
        try:
            data = {"_rc": proc.returncode, "error": json.loads(proc.stderr.strip())["error"]}
        except (json.JSONDecodeError, KeyError):
            data = {"_rc": proc.returncode, "error": proc.stderr.strip()[:200]}
    return data


def db():
    conn = sqlite3.connect(STATE / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def sql(statement, params=()):
    conn = db()
    try:
        return [dict(row) for row in conn.execute(statement, params).fetchall()]
    finally:
        conn.close()


def raw(statement, params=()):
    conn = db()
    try:
        conn.execute(statement, params)
        conn.commit()
    finally:
        conn.close()


def show(title, value):
    print("\n##", title)
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))


def declare(fid, *extra):
    return run(
        "feature-declare", "--id", fid, "--name", fid, "--statement", "一句话",
        "--acceptance", '["a"]', "--constraints", '["c"]', *extra,
    )


def claim(role, actor="agent", *extra, expect=0):
    return run("work-claim", "--role", role, "--actor", actor, *extra, expect=expect)


def finish(token, expect=0):
    return run("work-finish", "--token", token, expect=expect)


def judge(wid, verdict="passed", *extra, expect=0):
    return run("work-judge", "--id", wid, "--verdict", verdict, "--actor",
               "auditor-1", *extra, expect=expect)


# ============================================================ S1 declare
root("s1")
show("S1.0 declare output", declare("feat-a"))
show("S1.1 features row", sql("SELECT * FROM features"))
show("S1.2 conditions", sql("SELECT name,status,reason FROM conditions ORDER BY rowid"))
show("S1.3 work items", sql(
    "SELECT id,kind,role,status,depends_on,target_ids,claim_token,claimed_at FROM work_items ORDER BY id"))
show("S1.4 requirement node", sql("SELECT id,kind,name,attrs_json,origin,repo,path FROM nodes"))
show("S1.5 feature-list", run("feature-list"))
show("S1.6 validation errors", [
    run("feature-declare", "--id", "bad id", "--name", "n", "--statement", "s",
        "--acceptance", "[]", "--constraints", "[]", expect=2),
    run("feature-declare", "--id", "feat-v", "--name", "n", "--statement", "",
        "--acceptance", "[]", "--constraints", "[]", expect=2),
    run("feature-declare", "--id", "feat-v", "--name", "n", "--statement", "s",
        "--acceptance", "{}", "--constraints", "[]", expect=2),
    run("feature-declare", "--id", "feat-v", "--name", "n", "--statement", "s",
        "--acceptance", "[]", "--constraints", "[]", "--coverage-epsilon", "0", expect=2),
    run("feature-declare", "--id", "feat-v", "--name", "n", "--statement", "s",
        "--acceptance", "[]", "--constraints", "[]", "--coverage-epsilon", "-1", expect=2),
    run("feature-declare", "--id", "feat-v", "--name", "n", "--statement", "s",
        "--acceptance", "[]", "--constraints", "[]", "--conformance", "--no-conformance", expect=2),
    run("feature-declare", "--id", "feat-v", "--name", "n", "--statement", "s",
        "--acceptance", "[]", "--constraints", "[]", "--no-coverage", "--coverage-epsilon", "1", expect=2),
])
show("S1.7 feature-status without coverage flags", {
    k: v for k, v in run("feature-status", "--id", "feat-a").items()
    if k in ("phase", "conditions", "scope_size", "coverage", "drift", "conformance",
             "constructions", "stale", "changes")
})
show("S1.8 feature-status work_items shape", run("feature-status", "--id", "feat-a")["work_items"][:2])

# ============================================================ S2 redeclare policy
root("s2")
declare("feat-b")
steps = [
    ("epsilon=2.0", declare("feat-b", "--coverage-epsilon", "2.0")),
    ("drift-limit=0", declare("feat-b", "--drift-limit", "0")),
    ("conformance", declare("feat-b", "--conformance")),
    ("plain re-declare", declare("feat-b")),
]
show("S2.1 redeclare sequence", [(label, out["generation"]) for label, out in steps])
show("S2.2 features row after sequence",
     sql("SELECT id,generation,coverage_epsilon,drift_limit,conformance FROM features"))
show("S2.3 conditions rows per generation", sql(
    "SELECT generation,count(*) n,sum(status) on_ FROM conditions GROUP BY generation ORDER BY generation"))
show("S2.4 work items per generation", sql(
    "SELECT generation,count(*) n,group_concat(status) statuses FROM work_items GROUP BY generation"))
show("S2.5 no way to unset drift-limit", [
    declare("feat-b", "--drift-limit", "0"),
    sql("SELECT coverage_epsilon,drift_limit,conformance FROM features"),
])

# ============================================================ S3 register
root("s3")
show("S3.1 register new feature", run(
    "feature-register", "--id", "feat-r", "--name", "登记",
    "--spec", '{"statement":"s","acceptance":["a"],"constraints":["c"]}'))
show("S3.2 features row (coverage/conformance/drift)", sql(
    "SELECT id,generation,coverage_epsilon,drift_limit,conformance FROM features"))
show("S3.3 work items after register", sql("SELECT count(*) n FROM work_items"))
show("S3.4 status coverage enforced", {
    "enforced": run("feature-status", "--id", "feat-r")["coverage"]["enforced"],
    "drift_enforced": run("feature-status", "--id", "feat-r")["drift"]["enforced"],
})
show("S3.5 register same generation", run(
    "feature-register", "--id", "feat-r", "--name", "再次",
    "--spec", '{"statement":"s2","acceptance":["a"],"constraints":["c"]}'))
show("S3.6 register generation must exceed current", run(
    "feature-register", "--id", "feat-r", "--name", "再次",
    "--spec", '{"statement":"s3","acceptance":["a"],"constraints":["c"]}',
    "--generation", "1", expect=2))
show("S3.7 register explicit generation", run(
    "feature-register", "--id", "feat-r", "--name", "登记",
    "--spec", '{"statement":"s3","acceptance":["a"],"constraints":["c"]}',
    "--generation", "3"))
show("S3.8 register spec validation", [
    run("feature-register", "--id", "feat-r2", "--name", "n", "--spec", '{"statement":"s"}', expect=2),
    run("feature-register", "--id", "feat-r2", "--name", "n", "--spec",
        '{"statement":"s","acceptance":"a","constraints":["c"]}', expect=2),
    run("feature-register", "--id", "feat-r2", "--name", "n", "--spec",
        '{"statement":"","acceptance":["a"],"constraints":["c"]}', expect=2),
])

# ============================================================ S4 work-open
root("s4")
declare("feat-w")
show("S4.1 work-open merges targets", [
    run("work-open", "--feature", "feat-w", "--kind", "model-architecture",
        "--target-ids", '["use_case:feat-w:*","actor:feat-w:*"]'),
    run("work-open", "--feature", "feat-w", "--kind", "model-architecture",
        "--target-ids", '["use_case:feat-w:*","component:feat-w:*"]'),
    sql("SELECT id,status,target_ids FROM work_items WHERE id='work:feat-w:g1:model-architecture'"),
])
c4 = claim("model-architecture", "a1")
show("S4.2 work-open cannot unblock seeded ticket", c4)
show("S4.3 work-open rejects audit kind", run(
    "work-open", "--feature", "feat-w", "--kind", "audit", "--target-ids", "[]", expect=2))
show("S4.4 work-open accepts scan (no seeded ticket)", [
    run("work-open", "--feature", "feat-w", "--kind", "scan", "--target-ids", '["x:*"]'),
    sql("SELECT id,role,status,depends_on FROM work_items WHERE kind='scan'"),
])
show("S4.5 claim scan while conditions pending", claim("scan", "scanner"))
show("S4.6 work-open after ticket passed", (
    lambda c: (
        run("upsert-node", "--token", c["claim_token"],
            "--data", '{"id":"use_case:feat-w:uc","kind":"use_case","name":"uc"}'),
        finish(c["claim_token"]),
        judge(c["work_item_id"]),
        run("work-open", "--feature", "feat-w", "--kind", "model-architecture",
            "--target-ids", '["use_case:feat-w:uc"]', expect=2),
    )
)(c4))
show("S4.7 work-open merge allowed on claimed ticket", (
    lambda c: (
        run("work-open", "--feature", "feat-w", "--kind", "model-structure",
            "--target-ids", '["classifier:feat-w:*"]'),
        finish(c["claim_token"]),
        sql("SELECT id,status,target_ids FROM work_items WHERE id=?", (c["work_item_id"],)),
    )
)(claim("model-structure", "a2")))

# ============================================================ S5 claim
root("s5")
declare("feat-c")
show("S5.1 claim output", claim("model-architecture", "agent-c"))
show("S5.2 claimed row", sql(
    "SELECT status,assignee,claimed_by,claimed_at,claim_token FROM work_items "
    "WHERE id='work:feat-c:g1:model-architecture'"))
show("S5.3 second claim for same role", claim("model-architecture", "agent-c2", expect=2))
show("S5.4 claim for blocked role", claim("specify-test", "agent-c3", expect=2))
show("S5.5 product-code gate", [
    run("work-open", "--feature", "feat-c", "--kind", "implement-test", "--target-ids", '["x:*"]'),
    claim("implement-test", "impl", expect=2),
    claim("implement-test", "impl", "--allow-product-code", expect=2),
])
show("S5.6 work-list exposes claim_token", run("work-list", "--feature", "feat-c"))
show("S5.7 feature-status exposes claim_token", [
    {k: item.get(k) for k in ("id", "status", "claim_token", "target_count", "target_sample")}
    for item in run("feature-status", "--id", "feat-c")["work_items"]
])
show("S5.8 reconcile TTL releases claim", [
    run("reconcile", "--feature", "feat-c", "--claim-ttl", "0", expect=1),
    run("reconcile", "--feature", "feat-c", "--claim-ttl", "0", "--apply", expect=1),
    sql("SELECT status,claimed_by,claimed_at,claim_token FROM work_items "
        "WHERE id='work:feat-c:g1:model-architecture'"),
])
show("S5.9 stale token after release", run("work-finish", "--token", "any-token", expect=2))

# cross-feature claim ordering
root("s5b")
declare("feat-z1")
declare("feat-z2")
show("S5.10 claim has no feature filter", claim("model-architecture", "agent-z"))

# ============================================================ S6 finish/judge
root("s6")
declare("feat-j")
run("work-open", "--feature", "feat-j", "--kind", "model-architecture",
    "--target-ids", '["use_case:feat-j:*"]')
c = claim("model-architecture", "agent-j")
show("S6.1 finish without token", run("work-finish", expect=2))
show("S6.2 finish bogus token", finish("deadbeef", expect=2))
show("S6.3 finish creates audit ticket", [
    run("upsert-node", "--token", c["claim_token"],
        "--data", '{"id":"use_case:feat-j:uc","kind":"use_case","name":"uc"}'),
    finish(c["claim_token"]),
    sql("SELECT id,kind,role,status,target_ids,depends_on FROM work_items WHERE feature_id='feat-j' ORDER BY id"),
])
show("S6.4 judge without actor", run(
    "work-judge", "--id", c["work_item_id"], "--verdict", "passed", expect=2))
show("S6.5 judge self", run(
    "work-judge", "--id", c["work_item_id"], "--verdict", "passed",
    "--actor", "agent-j", expect=2))
show("S6.6 judge with non-audit role", run(
    "work-judge", "--id", c["work_item_id"], "--verdict", "passed",
    "--role", "observe", "--actor", "auditor-1", expect=2))
show("S6.7 judge by audit ticket id", run(
    "work-judge", "--id", "work:feat-j:g1:audit:work:feat-j:g1:model-architecture",
    "--verdict", "passed", "--actor", "auditor-1"))
show("S6.8 passed rows", sql(
    "SELECT id,status,claimed_by,judged_by,judged_at,evidence_ids FROM work_items "
    "WHERE feature_id='feat-j' ORDER BY id"))
show("S6.9 judge_history", sql("SELECT * FROM judge_history"))

# failed path
root("s6f")
declare("feat-f")
run("work-open", "--feature", "feat-f", "--kind", "model-architecture",
    "--target-ids", '["use_case:feat-f:*"]')
c = claim("model-architecture", "agent-f")
run("upsert-node", "--token", c["claim_token"],
    "--data", '{"id":"use_case:feat-f:uc","kind":"use_case","name":"uc"}')
finish(c["claim_token"])
show("S6.10 failed without reason", run(
    "work-judge", "--id", c["work_item_id"], "--verdict", "failed",
    "--actor", "auditor-1", expect=2))
show("S6.11 failed", run(
    "work-judge", "--id", c["work_item_id"], "--verdict", "failed",
    "--fail-reason", "结构缺失", "--actor", "auditor-1"))
show("S6.12 subject after failed", sql(
    "SELECT id,status,assignee,claimed_by,claim_token,fail_reason,judged_by,evidence_ids "
    "FROM work_items WHERE feature_id='feat-f' ORDER BY id"))
show("S6.13 conditions after failed", sql(
    "SELECT name,status,reason FROM conditions ORDER BY rowid"))
show("S6.14 re-claim retry", claim("model-architecture", "agent-f2"))

# legacy claim: claimed_by NULL permits same actor
root("s6l")
declare("feat-lg")
run("work-open", "--feature", "feat-lg", "--kind", "model-architecture",
    "--target-ids", '["use_case:feat-lg:*"]')
c = claim("model-architecture", "agent-lg")
run("upsert-node", "--token", c["claim_token"],
    "--data", '{"id":"use_case:feat-lg:uc","kind":"use_case","name":"uc"}')
finish(c["claim_token"])
raw("UPDATE work_items SET claimed_by=NULL WHERE id=?", (c["work_item_id"],))
show("S6.15 legacy claim judged by same actor", run(
    "work-judge", "--id", c["work_item_id"], "--verdict", "passed", "--actor", "agent-lg"))
show("S6.16 legacy_claim flag", sql(
    "SELECT id,claimed_by,judged_by FROM work_items WHERE id=?", (c["work_item_id"],)))

# coverage gate inside judge
root("s6c")
declare("feat-cov", "--coverage-epsilon", "0.05")
c = claim("model-architecture", "agent-cov")
finish(c["claim_token"])
show("S6.17 judge blocked by coverage", run(
    "work-judge", "--id", c["work_item_id"], "--verdict", "passed",
    "--actor", "auditor-1", expect=2))
show("S6.18 coverage report", run("coverage", "--feature", "feat-cov"))

# observe requires evidence
root("s6e")
declare("feat-obs")
for kind in ("model-architecture", "model-structure", "interact", "specify-test", "implement-test"):
    extra = ["--allow-product-code"] if kind == "implement-test" else []
    c = claim(kind, "agent-" + kind, *extra)
    finish(c["claim_token"])
    judge(c["work_item_id"])
obs = claim("observe", "agent-obs")
finish(obs["claim_token"])
show("S6.19 observe judge without evidence", run(
    "work-judge", "--id", obs["work_item_id"], "--verdict", "passed",
    "--actor", "auditor-2", expect=2))
run("evidence-record", "--feature", "feat-obs", "--name", "unittest",
    "--command", "python -m unittest", "--actor", "auditor-2")
show("S6.20 observe judge with evidence", run(
    "work-judge", "--id", obs["work_item_id"], "--verdict", "passed", "--actor", "auditor-2"))
show("S6.21 gate after observe", run("gate", "--feature", "feat-obs", "--json"))

# work-seed re-entry
root("s6s")
declare("feat-seed")
show("S6.22 work-seed idempotent", [
    run("work-seed", "--feature", "feat-seed"),
    sql("SELECT id,status FROM work_items ORDER BY id"),
])

# ============================================================ S7 change
root("s7")
declare("feat-ch")
show("S7.1 change-diff on generation 1 without change", run(
    "change-diff", "--feature", "feat-ch", expect=2))
show("S7.2 change-open before Ready", run(
    "change-open", "--feature", "feat-ch", "--statement", "改",
    "--from-condition", "StructureReconciled", expect=2))
raw("UPDATE conditions SET status=1")
show("S7.3 change-open after Ready", run(
    "change-open", "--feature", "feat-ch", "--statement", "改持久化边界",
    "--from-condition", "StructureReconciled"))
show("S7.4 change row", sql("SELECT * FROM changes"))
show("S7.5 conditions gen2", sql(
    "SELECT name,status,reason FROM conditions WHERE generation=2 ORDER BY rowid"))
show("S7.6 work items gen2", sql(
    "SELECT id,kind,status,depends_on FROM work_items WHERE generation=2 ORDER BY id"))
show("S7.7 second change-open before Ready", run(
    "change-open", "--feature", "feat-ch", "--statement", "第二次",
    "--from-condition", "StructureReconciled", expect=2))
show("S7.8 change-diff after change", run("change-diff", "--feature", "feat-ch"))
show("S7.9 change-diff explicit future generation", run(
    "change-diff", "--feature", "feat-ch", "--from-generation", "9"))
show("S7.10 change id collision across features", [
    declare("feat-ch2"),
    raw("UPDATE conditions SET status=1 WHERE feature_id='feat-ch2'"),
    run("change-open", "--feature", "feat-ch2", "--statement", "x",
        "--from-condition", "ArchitectureReconciled", "--id", "dup-id"),
    raw("UPDATE conditions SET status=1"),
    run("change-open", "--feature", "feat-ch", "--statement", "y",
        "--from-condition", "ArchitectureReconciled", "--id", "dup-id", expect=2),
])
show("S7.11 change-open inherits and resets", {
    "gen": sql("SELECT generation FROM features WHERE id='feat-ch'"),
    "changes": sql("SELECT * FROM changes WHERE feature_id='feat-ch'"),
})

# ============================================================ S8 status vs gate bites
root("s8")
declare("feat-s1")
run("work-open", "--feature", "feat-s1", "--kind", "model-architecture",
    "--target-ids", '["classifier:demo:*"]')
c = claim("model-architecture", "a1")
run("upsert-node", "--token", c["claim_token"],
    "--data", '{"id":"classifier:demo:x","kind":"classifier","name":"X"}')
finish(c["claim_token"])
declare("feat-s2")
run("work-open", "--feature", "feat-s2", "--kind", "model-architecture",
    "--target-ids", '["classifier:demo:*"]')
show("S8.1 scopes", {
    "s1": run("feature-status", "--id", "feat-s1")["scope_size"],
    "s2": run("feature-status", "--id", "feat-s2")["scope_size"],
})
show("S8.2 bite node tagged feature-s1", run(
    "bite", "--node", "classifier:demo:x", "--feature", "feat-s1",
    "--verdict", "UNNECESSARY", "--reason", "probe", "--actor", "agent-lead"))
show("S8.3 feature-status feat-s2 bites", run("feature-status", "--id", "feat-s2")["bites"])
show("S8.4 gate feat-s2", {
    k: v for k, v in run("gate", "--feature", "feat-s2", "--json", expect=1).items()
    if k in ("result", "reason", "bites", "latest_verdicts")
})
show("S8.5 feat-s2 coverage hits", {
    "coverage": run("feature-status", "--id", "feat-s2")["coverage"]["phases"][0],
    "drift": run("feature-status", "--id", "feat-s2")["drift"],
})

# ============================================================ S9 error surfaces
root("s9")
declare("feat-e")
show("S9.1 unknown feature", [
    run("feature-status", "--id", "nope", expect=2),
    run("work-list", "--feature", "nope", expect=2),
    run("work-seed", "--feature", "nope", expect=2),
    run("change-diff", "--feature", "nope", expect=2),
    run("change-open", "--feature", "nope", "--statement", "s",
        "--from-condition", "StructureReconciled", expect=2),
])
show("S9.2 unknown work item", run(
    "work-judge", "--id", "nope", "--verdict", "passed", "--actor", "a", expect=2))
show("S9.3 argparse enum errors", [
    run("work-open", "--feature", "feat-e", "--kind", "nope", "--target-ids", "[]", expect=2),
    run("work-claim", "--role", "nope", "--actor", "a", expect=2),
    run("work-judge", "--id", "x", "--verdict", "nope", "--actor", "a", expect=2),
])
show("S9.4 extra flag on non-product role", claim("model-architecture", "a", "--allow-product-code"))
show("S9.5 claim with all conditions passed", [
    raw("UPDATE conditions SET status=1"),
    claim("model-architecture", "a2", expect=2),
])
show("S9.6 feature-list after everything", run("feature-list"))

print("\n## done")
