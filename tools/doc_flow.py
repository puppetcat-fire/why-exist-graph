"""文档一致性检查：只按 SKILL.md 的最短路径操作，看能不能从 zero 走到 gate PASS。

跑法：python tools/doc_flow.py

它不读技能内部实现，只把文档里写的命令序列原样执行。任何一步报错都说明文档与实现
脱节——单元测试不读文档，端到端测试直接用正确顺序，两边都抓不到这类问题。

建议在改动 CLI 表面（新增/改名命令、改必填参数）之后、发布之前跑一次。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
WXG = SKILL / "scripts" / "wxg.py"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

sys.path.insert(0, str(SKILL / "scripts"))
from whyexist.temp import make_temp_dir  # noqa: E402


def run(root: Path, *args: str, expect: int = 0):
    cmd = [sys.executable, str(WXG), "--root", str(root), *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=ENV)
    if proc.returncode != expect:
        print(f"!! 文档步骤失败：{' '.join(args)}")
        print(f"   exit={proc.returncode} 期望 {expect}")
        print(f"   stderr={proc.stderr.strip()[:500]}")
        raise SystemExit(1)
    out = proc.stdout.strip()
    return json.loads(out) if out.startswith(("{", "[")) else out


def check(label: str, condition: bool, detail: str = "") -> None:
    print(("  ok  " if condition else "  FAIL") + f"  {label}" + (f"  ({detail})" if detail else ""))
    if not condition:
        raise SystemExit(1)


def main() -> int:
    tmp = make_temp_dir("doc-flow-")
    root = tmp / "state"
    try:
        print("[1] 一条命令起步：up --template standard")
        up = run(root, "up", "--template", "standard")
        check("up 返回 gate 结果", up["gate_result"] in ("PASS", "FAIL"), up["gate_result"])
        check(
            "next 第一步是 import-file --prepare",
            "import-file" in up["next"][0] and "--prepare" in up["next"][0],
            up["next"][0],
        )

        demo_repo = Path(up["repo"]["path"])
        source = demo_repo / "demo.py"

        print("[2] 扫描导入：prepare → claim → write → finish → judge")
        prepared = run(root, "import-file", "--file", str(source), "--feature", "demo", "--prepare")
        check("prepare 创建了 scan 工单", prepared["work"]["action"] in ("insert", "merge"))
        scan = run(root, "work-claim", "--role", "scan", "--actor", "agent-scan")
        run(root, "import-file", "--file", str(source), "--token", scan["claim_token"])
        run(root, "work-finish", "--token", scan["claim_token"])
        run(
            root,
            "work-judge", "--id", scan["work_item_id"],
            "--verdict", "passed", "--role", "audit", "--actor", "auditor-1",
        )
        check("扫描链完成", True)

        print("[3] 六个阶段：open → claim → finish → judge")
        stages = [
            ("model-architecture", False),
            ("model-structure", False),
            ("interact", False),
            ("specify-test", False),
            ("implement-test", True),
        ]
        for kind, allow_code in stages:
            targets = ["requirement:demo:main"]
            if kind == "specify-test":
                # 3.6.0：specify-test 要把验收条目的测试接上，否则 gate 判 FAIL
                targets += ["testcase:demo:*", "acceptance:demo:*"]
            run(root, "work-open", "--feature", "demo", "--kind", kind,
                "--target-ids", json.dumps(targets))
            claim_args = ["work-claim", "--role", kind, "--actor", f"agent-{kind}"]
            if allow_code:
                claim_args.append("--allow-product-code")
            claim = run(root, *claim_args)
            if kind == "specify-test":
                run(root, "acceptance-import", "--feature", "demo", "--token", claim["claim_token"])
                run(root, "upsert-node", "--token", claim["claim_token"], "--data", json.dumps({
                    "id": "testcase:demo:trace",
                    "kind": "testcase",
                    "name": "验收条目冒烟",
                    "attrs": {"path": "tests/test_demo.py", "layer": "unit"},
                }, ensure_ascii=False))
                run(root, "upsert-edge", "--token", claim["claim_token"], "--data", json.dumps({
                    "src": "testcase:demo:trace",
                    "dst": "acceptance:demo:main:01",
                    "kind": "verifies",
                }, ensure_ascii=False))
            run(root, "work-finish", "--token", claim["claim_token"])
            run(root, "work-judge", "--id", claim["work_item_id"], "--verdict", "passed",
                "--role", "audit", "--actor", "auditor-1")
            print(f"  ok    {kind}")

        print("[4] 证据 + observe")
        run(root, "evidence-record", "--feature", "demo", "--name", "unittest",
            "--command", "python -m unittest", "--actor", "auditor-1")
        observe = run(root, "work-claim", "--role", "observe", "--actor", "agent-observe")
        run(root, "work-finish", "--token", observe["claim_token"])
        run(root, "work-judge", "--id", observe["work_item_id"], "--verdict", "passed",
            "--role", "audit", "--actor", "auditor-1")

        print("[5] gate")
        gate = run(root, "gate", "--feature", "demo", "--json")
        check("gate PASS", gate["result"] == "PASS", gate["result"])
        failed = [item["name"] for item in gate["checks"] if not item["ok"]]
        check("checks 全过", not failed, ",".join(failed))

        print("[6] export")
        exported = run(root, "export", "--feature", "demo")
        files = sorted(p.name for p in Path(exported["dir"]).iterdir())
        check("导出 6 个视图", len(files) == 6, str(len(files)))

        print("\n文档一致性检查：PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
