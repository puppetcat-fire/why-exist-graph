"""验证发布包在干净环境能独立跑通：解压 → up → 最短路径 → gate PASS。

跑法：
    python tools/verify_release.py                    # 用 dist/ 下最新的包
    python tools/verify_release.py --zip <path.zip>

它不复用源码仓的任何文件——解压到临时目录后只调包内的 `scripts/wxg.py`。
`tools/` 不随包分发，所以这里手工重放 `doc_flow` 的步骤。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
DIST = SKILL / "dist"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

sys.path.insert(0, str(SKILL / "scripts"))
# 必须用 whyexist.temp：Windows 受限 token 下 tempfile.mkdtemp 会因空 DACL 报 WinError 5
from whyexist.temp import make_temp_dir  # noqa: E402

STAGES = ["model-architecture", "model-structure", "interact", "specify-test", "implement-test"]


def run(wxg: Path, root: Path, *args: str):
    proc = subprocess.run(
        [sys.executable, str(wxg), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    out = proc.stdout.strip()
    if not out.startswith("{"):
        raise SystemExit(f"wxg {' '.join(args)} 失败 ({proc.returncode})：{proc.stderr.strip()[:400]}")
    return json.loads(out), proc.returncode


def check(label: str, ok: bool, detail: str = "") -> None:
    print(("  ok    " if ok else "  FAIL  ") + label + (f"  ({detail})" if detail else ""))
    if not ok:
        raise SystemExit(1)


def main() -> int:
    parser = argparse.ArgumentParser(description="验证发布包可独立运行")
    parser.add_argument("--zip", default=None)
    args = parser.parse_args()

    zip_path = Path(args.zip) if args.zip else None
    if zip_path is None:
        # 按 mtime 取最新：dist/ 里并存 v2.9.0 和 v2.74.0 时字符串排序会把前者当最新
        versions = sorted(
            DIST.glob("v*/why-exist-graph-*.zip"),
            key=lambda path: path.stat().st_mtime,
        )
        if not versions:
            raise SystemExit(f"dist/ 下没有发布包：{DIST}")
        zip_path = versions[-1]
    print(f"[1] 解压 {zip_path.name}")
    tmp = make_temp_dir("wxg-release-")
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(tmp)
        skill = tmp / "why-exist-graph"
        wxg = skill / "scripts" / "wxg.py"
        check("包内有 wxg.py", wxg.is_file())
        check("包内不含 tools/（仅源码仓）", not (skill / "tools").exists())
        check("包内有 SKILL.md", (skill / "SKILL.md").is_file())

        work = tmp / "work"
        work.mkdir()
        root = work / ".why-exist"
        print("[2] up --template standard")
        up, _ = run(wxg, root, "up", "--template", "standard")
        check("up 建了 feature", up["feature"]["created"], str(up["feature"]))
        check("初态 gate FAIL", up["gate_result"] == "FAIL")

        print("[3] 最短路径走到 PASS")
        for kind in STAGES:
            targets = ["requirement:demo:main"]
            if kind == "specify-test":
                # 3.6.0：specify-test 要把验收条目接上测试，否则 gate 判 FAIL
                targets += ["testcase:demo:*", "acceptance:demo:*"]
            run(wxg, root, "work-open", "--feature", "demo", "--kind", kind,
                "--target-ids", json.dumps(targets))
            claim_args = ["work-claim", "--role", kind, "--actor", "agent"]
            if kind == "implement-test":
                # implement-test 明确允许改产品代码，其余阶段不允许
                claim_args.append("--allow-product-code")
            claim, _ = run(wxg, root, *claim_args)
            if kind == "specify-test":
                run(wxg, root, "acceptance-import", "--feature", "demo", "--token", claim["claim_token"])
                run(wxg, root, "upsert-node", "--token", claim["claim_token"], "--data", json.dumps({
                    "id": "testcase:demo:trace",
                    "kind": "testcase",
                    "name": "验收条目冒烟",
                    "attrs": {"path": "tests/test_demo.py", "layer": "unit"},
                }, ensure_ascii=False))
                run(wxg, root, "upsert-edge", "--token", claim["claim_token"], "--data", json.dumps({
                    "src": "testcase:demo:trace",
                    "dst": "acceptance:demo:main:01",
                    "kind": "verifies",
                }, ensure_ascii=False))
            run(wxg, root, "work-finish", "--token", claim["claim_token"])
            run(wxg, root, "work-judge", "--id", claim["work_item_id"], "--verdict", "passed",
                "--role", "audit", "--actor", "auditor")
        run(wxg, root, "evidence-record", "--feature", "demo", "--name", "unittest",
            "--command", "python -m unittest", "--actor", "auditor")
        observe, _ = run(wxg, root, "work-claim", "--role", "observe", "--actor", "agent")
        run(wxg, root, "work-finish", "--token", observe["claim_token"])
        run(wxg, root, "work-judge", "--id", observe["work_item_id"], "--verdict", "passed",
            "--role", "audit", "--actor", "auditor")

        gate, code = run(wxg, root, "gate", "--feature", "demo", "--json")
        check("gate PASS", gate["result"] == "PASS", gate["result"])
        check("gate 退出码 0", code == 0, str(code))
        failed = [item["name"] for item in gate["checks"] if not item["ok"]]
        check("checks 全过", not failed, ",".join(failed))

        print("\n发布包独立运行：PASS")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp.parent / "demo-repo", ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
