"""切片 12 行为探针：只读观察五条命令的对外契约，不修改源码。

在 docs/audit/_probe_12_tmp 下建临时状态库与临时文档副本，逐条验证 export /
role-prompt / contract / verify / doctor 的退出码、产物、副作用与边界。
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent.parent
WXG = SKILL / "scripts" / "wxg.py"
BASE = Path(__file__).resolve().parent / "_probe_12_tmp"
ROOT = BASE / "state"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

sys.path.insert(0, str(SKILL / "scripts"))


def show(label, value):
    print(f"== {label}: {json.dumps(value, ensure_ascii=False, default=str)}")


def run(*args, root=ROOT, cwd=None, env=None):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env or ENV,
        cwd=str(cwd) if cwd else None,
    )
    out = proc.stdout.strip()
    try:
        payload = json.loads(out) if out else None
    except json.JSONDecodeError:
        payload = out
    return proc.returncode, payload, proc.stderr.strip()


def run_plain(*args, cwd=None):
    """不带 --root 的运行（观察默认根 ./.why-exist）。"""
    proc = subprocess.run(
        [sys.executable, str(WXG), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=ENV,
        cwd=str(cwd) if cwd else None,
    )
    out = proc.stdout.strip()
    try:
        payload = json.loads(out) if out else None
    except json.JSONDecodeError:
        payload = out
    return proc.returncode, payload, proc.stderr.strip()


def must(*args, root=ROOT):
    rc, payload, err = run(*args, root=root)
    if rc != 0:
        raise SystemExit(f"失败 {args} rc={rc} err={err}")
    return payload


def db(root=ROOT):
    conn = sqlite3.connect(root / "graph.sqlite")
    conn.row_factory = sqlite3.Row
    return conn


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    shutil.rmtree(BASE, ignore_errors=True)
    ROOT.mkdir(parents=True)
    must("up", "--template", "minimal", "--feature", "feat-p")
    # up 会建 demo feature（默认 demo）；用 feat-p 再做设计节点
    must(
        "feature-declare", "--id", "feat-x", "--name", "X", "--statement", "创建订单。",
        "--acceptance", json.dumps(["返回 code===1", "orders 有记录"], ensure_ascii=False),
        "--constraints", json.dumps(["不改产品代码"], ensure_ascii=False), "--no-coverage",
    )

    print("\n#### A. doctor 干净库 / 只读 / --fix 分支")
    rc, clean, err = run("doctor")
    show("A1 doctor 干净库", [rc, clean["ok"], clean["issue_count"], clean["truncated"], clean["fixed"]])
    db_file = ROOT / "graph.sqlite"
    h1 = sha(db_file)
    rc, clean2, _ = run("doctor")
    h2 = sha(db_file)
    show("A2 连跑两次 doctor 主库 hash 是否变化", [h1 == h2, sorted(p.name for p in ROOT.iterdir())])

    # 注入 7 类可修问题（不经过 CLI，模拟 out-of-band 破坏）
    conn = db()
    conn.execute(
        "INSERT INTO bites(node_id, feature_id, generation, verdict, actor, created_at) "
        "VALUES('operation:missing:gone','feat-x',1,'KEEP','probe','2026-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO edges(id, src, dst, kind) VALUES('edge:depends:x:y','component:missing:a','component:missing:b','depends')"
    )
    conn.execute("INSERT INTO feature_nodes(feature_id, node_id) VALUES('feat-x','component:missing:c')")
    scan = conn.execute(
        "SELECT id, target_ids, evidence_ids FROM work_items WHERE feature_id='feat-x' AND kind='model-architecture'"
    ).fetchone()
    conn.execute(
        "UPDATE work_items SET target_ids=?, evidence_ids=? WHERE id=?",
        (json.dumps(["component:missing:d", "use_case:feat-x:*"]), json.dumps(["ev:missing"]), scan["id"]),
    )
    conn.execute("UPDATE work_items SET claim_token='stale-token' WHERE id=?", (scan["id"],))
    conn.execute("UPDATE meta SET value='0.0.1' WHERE key='contract_version'")
    conn.commit()
    conn.close()

    rc, dirty, _ = run("doctor")
    show("A3 注入 7 类问题后", [rc, dirty["issue_count"], dirty["by_check"],
                              dirty["fixable_count"], dirty["unfixable_count"], dirty["unfixable_checks"]])

    rc, fixed, _ = run("doctor", "--fix")
    show("A4 --fix 结果", [rc, fixed["ok"], fixed["fixed"], fixed["by_check"]])
    conn = db()
    remaining = {
        "bites": conn.execute("SELECT COUNT(*) c FROM bites WHERE node_id='operation:missing:gone'").fetchone()["c"],
        "edges": conn.execute("SELECT COUNT(*) c FROM edges WHERE id='edge:depends:x:y'").fetchone()["c"],
        "feature_nodes": conn.execute(
            "SELECT COUNT(*) c FROM feature_nodes WHERE node_id='component:missing:c'"
        ).fetchone()["c"],
        "target_ids": conn.execute("SELECT target_ids FROM work_items WHERE id=?", (scan["id"],)).fetchone()["target_ids"],
        "evidence_ids": conn.execute("SELECT evidence_ids FROM work_items WHERE id=?", (scan["id"],)).fetchone()["evidence_ids"],
        "stale_token": conn.execute(
            "SELECT claim_token FROM work_items WHERE id=?", (scan["id"],)
        ).fetchone()["claim_token"],
        "contract_version": conn.execute("SELECT value FROM meta WHERE key='contract_version'").fetchone()["value"],
    }
    conn.close()
    show("A5 --fix 后实际行状态", remaining)

    # --fix 再跑一次：meta 计数是否仍然 =1（无条件重写）
    rc, fixed2, _ = run("doctor", "--fix")
    show("A6 干净库上再 --fix", [rc, fixed2["ok"], fixed2["fixed"]])

    # evidence-exit-nonzero：登记一次失败测试是否让 doctor 红
    must(
        "evidence-record", "--feature", "feat-x", "--name", "red-run",
        "--command", "python -m unittest", "--exit-code", "1", "--actor", "probe",
    )
    rc, ev, _ = run("doctor")
    show("A7 登记 exit_code=1 的证据后", [rc, ev["ok"], ev["by_check"]])

    # 不可修检查：applies-invalid / legacy-identity
    conn = db()
    conn.execute(
        "INSERT INTO nodes(id, kind, name, attrs_json) VALUES('component:missing:z','component','Z','{}')"
    )
    conn.execute(
        "INSERT INTO edges(id, src, dst, kind) VALUES('edge:applies:bad','component:missing:z','component:missing:z','applies')"
    )
    conn.execute("UPDATE work_items SET judged_by='legacy' WHERE feature_id='feat-x' AND kind='model-architecture'")
    conn.commit()
    conn.close()
    rc, unfix, _ = run("doctor", "--fix")
    show("A8 不可修检查在 --fix 前后", [rc, unfix["ok"], unfix["by_check"],
                                  unfix["unfixable_checks"], unfix["fixed"]])

    print("\n#### B. export 出口与作用域")
    # 第二个 requirement（前缀进作用域）
    conn = db()
    conn.execute(
        "INSERT INTO nodes(id, kind, name, attrs_json) VALUES('requirement:feat-x:alt','requirement','第二条','{\"statement\":\"另一条\"}')"
    )
    conn.commit()
    conn.close()
    exported = must("export", "--feature", "feat-x")
    dump = Path(exported["dir"])
    show("B1 export 返回", [exported["generation"], exported["steps"], exported["files"]])
    req = (dump / "01-需求.md").read_text(encoding="utf-8")
    show("B2 01 需求行（feature 级验收每行重复）", [line for line in req.splitlines() if line.startswith("| requirement")])
    show("B3 目录清单", sorted(p.name for p in dump.iterdir()))

    # 陈旧产物是否被清理
    stale_file = dump / "99-旧版本.md"
    stale_file.write_text("stale", encoding="utf-8")
    must("export", "--feature", "feat-x")
    show("B4 重导出后陈旧的 99-旧版本.md 是否仍在", stale_file.exists())

    # 未知 feature
    rc, missing, err = run("export", "--feature", "feat-nope")
    show("B5 未知 feature", [rc, missing, bool((ROOT / "export" / "feat-nope").exists())])

    # 07：一个 op 两个 sink + 两条断言，是否重复断言文本
    # 单独 root：work-claim --role 是全库取第一张 ready 工单，不按 feature 过滤
    root_s = BASE / "state-s"
    root_s.mkdir()
    must("init", root=root_s)
    must(
        "feature-declare", "--id", "feat-s", "--name", "S", "--statement", "写库。",
        "--acceptance", "[]", "--constraints", "[]", "--no-coverage", root=root_s,
    )
    must("work-open", "--feature", "feat-s", "--kind", "model-architecture",
         "--target-ids", json.dumps(["use_case:feat-s:*", "operation:demo:*", "sink:demo:*",
                                     "assertion:feat-s:*"], ensure_ascii=False), root=root_s)
    claim = must("work-claim", "--role", "model-architecture", "--actor", "probe", root=root_s)
    token = claim["claim_token"]
    show("B6a claim 的 target_ids", claim["target_ids"])
    must("upsert-node", "--token", token, "--data", json.dumps(
        {"id": "use_case:feat-s:uc", "kind": "use_case", "name": "用例"}), root=root_s)
    must("upsert-edge", "--token", token, "--data", json.dumps(
        {"src": "use_case:feat-s:uc", "dst": "requirement:feat-s:main", "kind": "satisfies"}), root=root_s)
    must("upsert-node", "--token", token, "--data", json.dumps(
        {"id": "operation:demo:shop.py:save", "kind": "operation", "name": "save", "symbol": "OrderRepo.save"}), root=root_s)
    must("upsert-edge", "--token", token, "--data", json.dumps(
        {"src": "use_case:feat-s:uc", "dst": "operation:demo:shop.py:save", "kind": "contains"}), root=root_s)
    for sink in ("sink:demo:orders", "sink:demo:audit"):
        must("upsert-node", "--token", token, "--data", json.dumps(
            {"id": sink, "kind": "sink", "name": sink.split(":")[-1]}), root=root_s)
        must("upsert-edge", "--token", token, "--data", json.dumps(
            {"src": "operation:demo:shop.py:save", "dst": sink, "kind": "writes"}), root=root_s)
    for i in (1, 2):
        aid = f"assertion:feat-s:a{i}"
        must("upsert-node", "--token", token, "--data", json.dumps(
            {"id": aid, "kind": "assertion", "name": f"断言{i}", "attrs": {"text": f"code==={i}"}}), root=root_s)
        must("bind", "--token", token, "--node-id", aid, "--bind-to", "operation:demo:shop.py:save", root=root_s)
    must("work-finish", "--token", token, root=root_s)

    exported = must("export", "--feature", "feat-s", root=root_s)
    flow = (Path(exported["dir"]) / "07-数据流.md").read_text(encoding="utf-8")
    show("B6 07 steps（两 sink + 两断言）", [line for line in flow.splitlines() if line.startswith("| ") and "save" in line])

    # 参数去重 + 顺序
    root_par = BASE / "state-par"
    root_par.mkdir()
    must("init", root=root_par)
    must(
        "feature-declare", "--id", "feat-par", "--name", "P", "--statement", "参数。",
        "--acceptance", "[]", "--constraints", "[]", "--no-coverage", root=root_par,
    )
    must("work-open", "--feature", "feat-par", "--kind", "model-architecture",
         "--target-ids", json.dumps(["use_case:feat-par:*", "operation:demo:*", "parameter:feat-par:*"],
                                    ensure_ascii=False), root=root_par)
    claim = must("work-claim", "--role", "model-architecture", "--actor", "probe", root=root_par)
    token = claim["claim_token"]
    must("upsert-node", "--token", token, "--data", json.dumps(
        {"id": "use_case:feat-par:uc", "kind": "use_case", "name": "用例"}), root=root_par)
    must("upsert-edge", "--token", token, "--data", json.dumps(
        {"src": "use_case:feat-par:uc", "dst": "requirement:feat-par:main", "kind": "satisfies"}), root=root_par)
    for name in ("second", "first"):
        op = f"operation:demo:par.py:{name}"
        must("upsert-node", "--token", token, "--data", json.dumps(
            {"id": op, "kind": "operation", "name": name}), root=root_par)
        must("upsert-edge", "--token", token, "--data", json.dumps(
            {"src": "use_case:feat-par:uc", "dst": op, "kind": "contains"}), root=root_par)
    pid = "parameter:feat-par:q"
    must("upsert-node", "--token", token, "--data", json.dumps(
        {"id": pid, "kind": "parameter", "name": "q", "attrs": {"column": "q"}}), root=root_par)
    must("bind", "--token", token, "--node-id", pid, "--bind-to", "operation:demo:par.py:first", root=root_par)
    must("bind", "--token", token, "--node-id", pid, "--bind-to", "operation:demo:par.py:second", root=root_par)
    must("work-finish", "--token", token, root=root_par)
    exported = must("export", "--feature", "feat-par", root=root_par)
    flow = (Path(exported["dir"]) / "07-数据流.md").read_text(encoding="utf-8")
    show("B7 07 参数表（同一参数只列一次）", [line for line in flow.splitlines() if "| q |" in line])
    show("B8 05 类图 kind 顺序", [line for line in (Path(exported["dir"]) / "05-类图.md").read_text(
        encoding="utf-8").splitlines() if line.startswith("| operation") or line.startswith("| parameter")])

    print("\n#### C. contract")
    cwd = BASE / "clean-cwd"
    cwd.mkdir()
    rc, main_md, err = run_plain("contract", cwd=cwd)
    show("C1 contract 无库默认输出", [rc, isinstance(main_md, str), (main_md or "")[:40],
                                (cwd / ".why-exist").exists()])
    rc, full_md, _ = run_plain("contract", "--section", "full", cwd=cwd)
    show("C2 full 比 main 多出", len((full_md or "").splitlines()) - len((main_md or "").splitlines()))

    target = BASE / "doc-copy.md"
    text = "头部\n<!-- wxg:contract:main:begin -->\n旧内容\n<!-- wxg:contract:main:end -->\n尾部\n"
    target.write_text(text, encoding="utf-8", newline="\n")
    rc, written, _ = run_plain("contract", "--write", str(target), cwd=cwd)
    after = target.read_text(encoding="utf-8")
    raw = target.read_bytes()
    show("C3 --write 返回与块外内容", [rc, written, "头部" in after and "尾部" in after,
                                "旧内容" not in after])
    show("C4 --write 后字节换行", [raw.count(b"\r\n"), raw.count(b"\n")])
    first = raw
    run_plain("contract", "--write", str(target), cwd=cwd)
    show("C5 重复 --write 是否逐字节幂等", first == target.read_bytes())

    rc, json_out, _ = run_plain("contract", "--json", "--write", str(target), cwd=cwd)
    show("C6 --json 忽略 --write 且不改文件", [rc, isinstance(json_out, dict), first == target.read_bytes(),
                                        json_out.get("version") if isinstance(json_out, dict) else None])

    rc, err_payload, err = run_plain("contract", "--write", "no-such-file.md", cwd=cwd)
    show("C7 相对路径解析到哪 + 缺失文件", [rc, err_payload or err[:160],
                                  str(SKILL / "no-such-file.md") in (err_payload or err)])

    bad = BASE / "bad-block.md"
    bad.write_text("没有标记\n", encoding="utf-8")
    rc, err_payload, err = run_plain("contract", "--write", str(bad), cwd=cwd)
    show("C8 缺标记", [rc, err_payload])

    print("\n#### D. role-prompt")
    prompt = run_plain("role-prompt", "--role", "scan", cwd=cwd)[1]
    show("D1 scan 无库运行 + 默认根", [isinstance(prompt, str), str(cwd / ".why-exist") in prompt,
                               (cwd / ".why-exist").exists(), prompt.count("wxg ")])
    rc, audit_prompt, _ = run_plain("role-prompt", "--role", "audit", cwd=cwd)
    show("D2 audit 分支", [rc, "直接裁决" in audit_prompt, "work-finish" in audit_prompt])
    rc, tok, _ = run_plain("role-prompt", "--role", "scan", "--token", "tok-123",
                           "--feature", "feat-x", cwd=cwd)
    show("D3 --token/--feature 段落", [rc, "tok-123" in tok, "## feature" in tok, "feat-x" in tok])
    rc, bad_role, err = run_plain("role-prompt", "--role", "nope", cwd=cwd)
    show("D4 未知角色（argparse 还是 handler）", [rc, type(bad_role).__name__, (err or "")[:60]])
    rc, impl, _ = run_plain("role-prompt", "--role", "implement-test", cwd=cwd)
    show("D5 implement-test 专属提示", [rc, "construction" in impl, "work-finish --token" in impl])

    print("\n#### E. 零 DB 白名单")
    for cmd in (["verify"], ["contract"], ["role-prompt", "--role", "scan"], ["doctor"], ["export", "--feature", "x"]):
        target_cwd = BASE / ("cwd-" + cmd[0])
        target_cwd.mkdir()
        rc, payload, err = run_plain(*cmd, cwd=target_cwd)
        show(f"E {cmd[0]}", [rc, (target_cwd / ".why-exist").exists(),
                             (payload.get("error") if isinstance(payload, dict) else (err or "")[:60])])

    print("\n#### F. verify 反向探针（复制技能目录，WXG_SKILL_DIR 重定向）")
    copy = BASE / "skill-copy"

    def fresh():
        nonlocal copy
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(SKILL, copy, ignore=shutil.ignore_patterns(
            "__pycache__", ".git", "docs", "dist", "*.log"))
        return dict(ENV, WXG_SKILL_DIR=str(copy))

    def verify(env):
        proc = subprocess.run(
            [sys.executable, str(WXG), "verify"], capture_output=True, text=True,
            encoding="utf-8", env=env,
        )
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = proc.stdout
        return proc.returncode, payload

    rc, base_out = verify(fresh())
    show("F1 复制目录基线", [rc, base_out.get("ok") if isinstance(base_out, dict) else base_out])

    env = fresh()
    sample = copy / "references" / "export-sample" / "feat-demo" / "02-用例.md"
    sample.write_text(sample.read_text(encoding="utf-8") + "\nX\n", encoding="utf-8")
    rc, drift = verify(env)
    show("F2 导出样例漂移", [rc, drift.get("issues") if isinstance(drift, dict) else drift])

    env = fresh()
    (copy / "references" / "export-sample" / "feat-demo" / "02-用例.md").unlink()
    rc, missing_sample = verify(env)
    show("F3 删除一个导出样例", [rc, missing_sample.get("issues") if isinstance(missing_sample, dict) else missing_sample])

    env = fresh()
    contract_md = copy / "references" / "contract.md"
    contract_md.write_text(contract_md.read_text(encoding="utf-8").replace(
        "<!-- wxg:contract:full:end -->", "手工改的一行\n<!-- wxg:contract:full:end -->"), encoding="utf-8")
    rc, full_drift = verify(env)
    show("F4 full 块漂移（无反向测试）", [rc, full_drift.get("issues") if isinstance(full_drift, dict) else full_drift])

    env = fresh()
    skill_md = copy / "SKILL.md"
    skill_md.write_text(skill_md.read_text(encoding="utf-8").replace(
        "<!-- wxg:contract:main:begin -->", "<!-- gone -->"), encoding="utf-8")
    rc, no_marker = verify(env)
    show("F5 删掉 main begin 标记", [rc, no_marker.get("issues") if isinstance(no_marker, dict) else no_marker])

    env = fresh()
    (copy / "references" / "quality.md").unlink()
    rc, no_quality = verify(env)
    show("F6 删掉 references/quality.md", [rc, no_quality.get("issues") if isinstance(no_quality, dict) else no_quality])

    env = fresh()
    front = copy / "SKILL.md"
    text = front.read_text(encoding="utf-8").replace("name: why-exist-graph", "name: other-skill", 1)
    front.write_text(text, encoding="utf-8")
    rc, bad_name = verify(env)
    show("F7 frontmatter name 不符", [rc, bad_name.get("issues") if isinstance(bad_name, dict) else bad_name])

    print("\n#### G. 比较语义与修复提示")
    crlf = BASE / "g-crlf"
    shutil.rmtree(crlf, ignore_errors=True)
    shutil.copytree(SKILL, crlf, ignore=shutil.ignore_patterns(
        "__pycache__", ".git", "docs", "dist", "*.log"))
    for name in ("SKILL.md", "references/contract.md"):
        path = crlf / name
        path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\r\n")
    env = dict(ENV, WXG_SKILL_DIR=str(crlf))
    raw = (crlf / "SKILL.md").read_bytes()
    show("G1 全 CRLF 改写后 verify", [raw.count(b"\r\n"), raw.count(b"\n"), verify(env)[0]])

    second = BASE / "g-second"
    shutil.rmtree(second, ignore_errors=True)
    shutil.copytree(SKILL, second, ignore=shutil.ignore_patterns(
        "__pycache__", ".git", "docs", "dist", "*.log"))
    path = second / "SKILL.md"
    path.write_text(path.read_text(encoding="utf-8").replace(
        "<!-- wxg:contract:main:end -->",
        "<!-- wxg:contract:main:end -->\n\n<!-- wxg:contract:main:begin -->\n伪造的第二块\n<!-- wxg:contract:main:end -->",
    ), encoding="utf-8")
    rc, second_out = verify(dict(ENV, WXG_SKILL_DIR=str(second)))
    show("G2 伪造第二对标记", [rc, second_out.get("ok") if isinstance(second_out, dict) else second_out])

    rc, payload, err = run_plain("contract", "--write", "contract.md", "--section", "full", cwd=cwd)
    show("G3 按 verify 提示修 contract.md", [rc, (err or "")[:120], (SKILL / "contract.md").exists()])

    print("\n#### H. feature id 决定导出目录")
    root_t = BASE / "state-traversal"
    root_t.mkdir()
    must("init", root=root_t)
    must("feature-declare", "--id", "..", "--name", "x", "--statement", "s",
         "--acceptance", "[]", "--constraints", "[]", "--no-coverage", root=root_t)
    rc, exported, _ = run("export", "--feature", "..", root=root_t)
    show("H1 feature id='..' 的导出目录", [
        rc,
        exported["dir"] if isinstance(exported, dict) else exported,
        sorted(p.name for p in root_t.iterdir()),
        (root_t / "export").exists(),
    ])

    shutil.rmtree(BASE, ignore_errors=True)


if __name__ == "__main__":
    main()
