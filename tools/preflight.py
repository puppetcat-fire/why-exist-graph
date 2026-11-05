"""发布前检查：一条命令跑完全部质量门。

跑法：
    python tools/preflight.py              # 测试 + 文档一致性 + verify + doctor
    python tools/preflight.py --release    # 再加打包

每一步失败立即退出并打印失败原因；全部通过时给一行汇总。
"""

from __future__ import annotations

import argparse
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

STEPS: list[tuple[str, list[str]]] = []


def sh(cmd: list[str], *, cwd: Path = SKILL, expect_codes=(0,)) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", env=ENV)
    if proc.returncode not in expect_codes:
        print(f"\n!! 步骤失败：{' '.join(cmd)}")
        print(f"   exit={proc.returncode}")
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
        for line in tail:
            print(f"   {line}")
        raise SystemExit(1)
    return proc


def step(name: str) -> None:
    print(f"- {name} ...", end="", flush=True)


def ok(detail: str = "") -> None:
    print(f" ok{'  ' + detail if detail else ''}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="why-exist-graph 发布前检查")
    parser.add_argument("--release", action="store_true", help="最后跑 build_release")
    args = parser.parse_args(argv)

    summary: list[str] = []

    step("回归测试")
    proc = sh([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"])
    tail = proc.stderr.strip().splitlines()
    ran = next((line for line in reversed(tail) if line.startswith("Ran ")), "")
    ok(ran)
    summary.append(ran)

    step("文档一致性（照 SKILL.md 走到 gate PASS）")
    proc = sh([sys.executable, str(HERE / "doc_flow.py")])
    ok("PASS")
    summary.append("doc_flow PASS")

    step("文档完整性（版本 / CHANGELOG / design.md）")
    sh([sys.executable, str(HERE / "check_docs.py")])
    ok("PASS")
    summary.append("docs PASS")

    step("工作树行尾（应为 LF）")
    eol = subprocess.run(
        ["git", "ls-files", "--eol"], cwd=str(SKILL),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if eol.returncode == 0:
        crlf = [line for line in eol.stdout.splitlines() if "w/crlf" in line]
        if crlf:
            print(f"\n!! {len(crlf)} 个已跟踪文件的工作树是 CRLF（.gitattributes 要求 LF）")
            print("   Windows 上通常是 core.autocrlf=true 造成的：")
            print("     git config core.autocrlf false")
            print("     git rm --cached -r . ; git reset --hard")
            print(f"   第一个：{crlf[0].split(chr(9))[-1]}")
            raise SystemExit(1)
        ok("LF")
    else:
        ok("跳过（不是 git 工作树）")

    step("未定义全局名（运行期 NameError 的前置检查）")
    sh([sys.executable, str(HERE / "check_undefined.py")])
    ok("PASS")

    step("契约校验")
    proc = sh([sys.executable, str(WXG), "verify"])
    result = json.loads(proc.stdout)
    if not result.get("ok"):
        print(f"\n!! verify 失败：{result.get('issues')}")
        raise SystemExit(1)
    ok(result.get("version", ""))

    step("状态库体检（新库）")
    tmp = make_temp_dir("preflight-")
    try:
        root = tmp / "state"
        sh([sys.executable, str(WXG), "--root", str(root), "up", "--template", "standard"])
        proc = sh([sys.executable, str(WXG), "--root", str(root), "doctor"])
        doctor = json.loads(proc.stdout)
        if not doctor.get("ok"):
            print(f"\n!! doctor 报问题：{doctor.get('issues')}")
            raise SystemExit(1)
        ok("ok")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        shutil.rmtree(tmp.parent / "demo-repo", ignore_errors=True)

    step("报告自洽性（临时库）")
    tmp2 = make_temp_dir("preflight-reports-")
    try:
        root2 = tmp2 / "state"
        sh([sys.executable, str(WXG), "--root", str(root2), "up", "--template", "standard"])
        sh(
            [sys.executable, str(HERE / "verify_reports.py"),
             "--root", str(root2), "--feature", "demo"]
        )
        ok("PASS")
        summary.append("reports PASS")
    finally:
        shutil.rmtree(tmp2, ignore_errors=True)
        shutil.rmtree(tmp2.parent / "demo-repo", ignore_errors=True)

    step("后端集成（可选，需 WXG_TEST_MYSQL_URL / WXG_TEST_PG_URL）")
    proc = sh([sys.executable, str(HERE / "test_backend.py")])
    backend_lines = [line for line in proc.stdout.splitlines() if line.startswith("后端集成测试")]
    ok(backend_lines[-1] if backend_lines else "跳过")
    summary.append(backend_lines[-1] if backend_lines else "backend skipped")

    if args.release:
        step("打包发布")
        proc = sh([sys.executable, str(HERE / "build_release.py")])
        manifest = json.loads(proc.stdout)
        ok(f"v{manifest['version']}  {manifest['files']} 个文件  {manifest['archive']['sha256'][:12]}")
        summary.append(f"release v{manifest['version']}")

        # 打完包立刻验证"这个包能不能独立跑"——否则发布前检查只证明了源码仓是好的
        step("发布包独立运行")
        sh([sys.executable, str(HERE / "verify_release.py")])
        ok("PASS")
        summary.append("release-package PASS")

    print("\npreflight PASS：" + " / ".join(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
