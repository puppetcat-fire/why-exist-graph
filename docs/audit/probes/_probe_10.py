"""slice 10 探针：gate/coverage/conformance/reconcile/serve/evidence 的可观察行为。

只读源码之外的状态：临时目录里的状态库；不改仓库任何文件。
用法：python docs/audit/_probe_10.py
"""
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
from whyexist import db as why_db, evidence as evidence_mod  # noqa: E402

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


def note(name, **kw):
    OUT.append({"probe": name, **kw})


tmp = Path(wxg.make_temp_dir("wxg-probe10-")).resolve()
root = tmp / "state"
repo = tmp / "repo"
repo.mkdir()
(repo / "shop.py").write_text(
    "class OrderRepo:\n    def __init__(self, conn):\n        self.conn = conn\n"
    "    def save(self, order):\n        return order['id']\n", encoding="utf-8")
run(root, "init")
run(root, "repo-add", "--id", "demo", "--path", str(repo))


def declare(fid, *extra):
    return run(root, "feature-declare", "--id", fid, "--name", fid, "--statement", "s",
               "--acceptance", "[]", "--constraints", "[]", *extra)


def conn():
    c = sqlite3.connect(root / "graph.sqlite")
    c.row_factory = sqlite3.Row
    return c


def force_ready(fid):
    c = conn()
    c.execute("UPDATE conditions SET status=1 WHERE feature_id=? AND generation=1", (fid,))
    c.execute(
        "INSERT INTO evidence(id, feature_id, generation, name, command, exit_code, actor, created_at) "
        "VALUES(?,?,1,'e','true',0,'t','2026-01-01T00:00:00Z')", (f"ev:{fid}", fid))
    c.commit()
    c.close()


# P1 覆盖公式：p 与 n_required 用不同分母（文档说 10+m）
declare("feat-cov", "--coverage-epsilon", "0.1")
rc, cov, err, _ = run(root, "coverage", "--feature", "feat-cov")
note("P1-coverage-formula", rc=rc, scope_size=cov.get("scope_size"),
     phase=cov.get("phases", [{}])[0], epsilon=cov.get("epsilon"))

# P2 gate 因“后续阶段”覆盖未达标而 FAIL（条件全真、证据有效、无其它检查项）
declare("feat-covgate", "--coverage-epsilon", "0.05")
force_ready("feat-covgate")
run(root, "bite", "--node", "requirement:feat-covgate:main", "--verdict", "KEEP",
    "--feature", "feat-covgate", "--actor", "a")
rc, gate, err, _ = run(root, "gate", "--feature", "feat-covgate", "--json")
note("P2-gate-coverage-later-phases", rc=rc, result=gate.get("result"),
     reason=gate.get("reason"), unmet=(gate.get("coverage") or {}).get("unmet"),
     checks=gate.get("checks"), phase0=(gate.get("coverage") or {}).get("phases", [{}])[0])

# P3 悬空 bite 被 bites 检查忽略，却仍计入 drift 并拦门
declare("feat-dangle", "--no-coverage", "--drift-limit", "0")
force_ready("feat-dangle")
c = conn()
c.execute(
    "INSERT INTO bites(node_id, feature_id, generation, phase, verdict, reason, actor, created_at) "
    "VALUES('operation:missing:gone','feat-dangle',1,'ArchitectureReconciled','UNMAPPED','x','a','2026-01-01T00:00:00Z')")
c.commit()
c.close()
rc, gate, err, _ = run(root, "gate", "--feature", "feat-dangle", "--json")
note("P3-dangling-drift", rc=rc, result=gate.get("result"), reason=gate.get("reason"),
     drift=gate.get("drift"), ignored=gate.get("ignored_dangling_bites"))

# P4 其它 feature 的咬合因节点在作用域内而影响本 feature 的 gate
declare("feat-a", "--no-coverage")
declare("feat-b", "--no-coverage")
c = conn()
c.execute("INSERT OR IGNORE INTO nodes(id, kind, name) VALUES('operation:demo:x.py:run','operation','run')")
c.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES('feat-a','operation:demo:x.py:run')")
c.commit()
c.close()
rc, bite, err, _ = run(root, "bite", "--node", "operation:demo:x.py:run", "--verdict", "UNNECESSARY",
                       "--feature", "feat-b", "--actor", "a")
rc, gate, err, _ = run(root, "gate", "--feature", "feat-a", "--json")
note("P4-cross-feature-bite", rc=rc, result=gate.get("result"), reason=gate.get("reason"),
     bites=gate.get("bites"))

# P5 conformance 输出形状：命令有 enforced，gate 内嵌没有
declare("feat-conf", "--no-coverage", "--conformance")
rc, conf, err, _ = run(root, "conformance", "--feature", "feat-conf")
rc, gate, err, _ = run(root, "gate", "--feature", "feat-conf", "--json")
note("P5-conformance-shape", conf_keys=sorted(conf.keys()),
     gate_conf_keys=sorted((gate.get("conformance") or {}).keys()),
     conf_enforced=conf.get("enforced"))

# P6 serve 指向不存在的 feature：静默成功
rc, serve, err, raw = run(root, "serve", "--once", "--feature", "nope")
note("P6-serve-unknown-feature", rc=rc, payload=serve, stderr=err)

# P7 --json 旗标是否改变输出
rc1, g1, _, raw1 = run(root, "gate", "--feature", "feat-conf")
rc2, g2, _, raw2 = run(root, "gate", "--feature", "feat-conf", "--json")
rc3, c1, _, craw1 = run(root, "coverage", "--feature", "feat-conf")
rc4, c2, _, craw2 = run(root, "coverage", "--feature", "feat-conf", "--json")
note("P7-json-flag-inert", gate_same=(raw1 == raw2), coverage_same=(craw1 == craw2))

# P8 条件行缺失：gate 直接 2，不落 PASS/FAIL
c = conn()
c.execute("DELETE FROM conditions WHERE feature_id='feat-conf' AND name='Ready'")
c.commit()
c.close()
rc, gate, err, _ = run(root, "gate", "--feature", "feat-conf", "--json")
note("P8-missing-condition-row", rc=rc, payload=gate, stderr=err)

# P9 verifies 边不校验 src 是否 testcase
declare("feat-v", "--no-coverage")
c = conn()
c.execute("INSERT INTO nodes(id, kind, name) VALUES('use_case:feat-v:u','use_case','u')")
c.execute("INSERT INTO nodes(id, kind, name) VALUES('operation:feat-v:o','operation','o')")
c.execute("INSERT INTO feature_nodes(feature_id, node_id) VALUES('feat-v','use_case:feat-v:u')")
c.execute("INSERT INTO edges(id, src, dst, kind) VALUES('e1','operation:feat-v:o','use_case:feat-v:u','verifies')")
c.commit()
c.close()
rc, conf, err, _ = run(root, "conformance", "--feature", "feat-v")
note("P9-verifies-src-not-checked", rc=rc, tests=conf.get("tests"))

# P10 evidence_qualifies 判定矩阵
mem = sqlite3.connect(":memory:")
mem.row_factory = sqlite3.Row
mem.executescript(why_db.SCHEMA_SQL)
art = tmp / "artifact.txt"
art.write_text("ok", encoding="utf-8")
good_hash = evidence_mod.sha256_file(art)
rows = [
    ("e1", 1, 0, None, None),
    ("e2", 1, 1, None, None),
    ("e3", 1, 0, str(tmp / "missing.txt"), None),
    ("e4", 1, 0, str(art), good_hash),
    ("e5", 1, 0, str(art), "deadbeef"),
]
for eid, gen, code, path, sha in rows:
    mem.execute(
        "INSERT INTO evidence(id, feature_id, generation, name, command, exit_code, artifact_path, artifact_sha256, actor, created_at) "
        "VALUES(?, 'f', ?, 'n', 'c', ?, ?, ?, 'a', '2026-01-01T00:00:00Z')",
        (eid, gen, code, path, sha))
mem.commit()


def qualifies_only(row_id):
    mem.execute("DELETE FROM evidence WHERE feature_id='f'")
    if row_id:
        r = [x for x in rows if x[0] == row_id][0]
        mem.execute(
            "INSERT INTO evidence(id, feature_id, generation, name, command, exit_code, artifact_path, artifact_sha256, actor, created_at) "
            "VALUES(?, 'f', ?, 'n', 'c', ?, ?, ?, 'a', '2026-01-01T00:00:00Z')",
            (r[0], r[1], r[2], r[3], r[4]))
    else:
        for r in rows:
            mem.execute(
                "INSERT INTO evidence(id, feature_id, generation, name, command, exit_code, artifact_path, artifact_sha256, actor, created_at) "
                "VALUES(?, 'f', ?, 'n', 'c', ?, ?, ?, 'a', '2026-01-01T00:00:00Z')",
                (r[0], r[1], r[2], r[3], r[4]))
    mem.commit()
    return evidence_mod.evidence_qualifies(mem, "f", 1)


note("P10-evidence-matrix", none=qualifies_only(None), no_artifact=qualifies_only("e1"),
     exit_nonzero=qualifies_only("e2"), missing_artifact=qualifies_only("e3"),
     hash_match=qualifies_only("e4"), hash_mismatch=qualifies_only("e5"))

# P11 claim_ttl=0 时刚领取的工单立即被回收
declare("feat-ttl", "--no-coverage")
rc, claim, err, _ = run(root, "work-claim", "--role", "model-architecture", "--actor", "a")
rc, rec, err, _ = run(root, "reconcile", "--feature", "feat-ttl", "--claim-ttl", "0")
note("P11-ttl-zero", rc=rc, actions=rec.get("actions"),
     applied=rec.get("applied"), converged=rec.get("converged"))

# P12 空库 serve：converged=true，退出 0
empty_root = tmp / "empty-state"
run(empty_root, "init")
rc, serve, err, raw = run(empty_root, "serve", "--once")
note("P12-serve-empty", rc=rc, payload=serve, stdout=raw.strip())

# P13 gate 顶层键
rc, gate, err, _ = run(root, "gate", "--feature", "feat-a", "--json")
note("P13-gate-keys", rc=rc, keys=sorted(gate.keys()) if isinstance(gate, dict) else gate,
     checks=gate.get("checks") if isinstance(gate, dict) else None)

print(json.dumps(OUT, ensure_ascii=False, indent=2))
