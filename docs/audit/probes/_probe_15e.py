"""Slice 15 探针 5：验证「未被测试锁住」的对外行为。只在临时目录写。

关注点：
  P1 Reject 走 stderr + 退出 2（测试夹具把 stdout/stderr 混读，没锁这条）
  P2 feature-list 成功路径输出形状（全项目零测试）
  P3 repo-list 成功路径输出形状（只有缺库错误路径）
  P4 --db-url 全局参数是否改写 WXG_DB_URL / 有无测试
  P5 gate/coverage 的 --json 是否改变输出（契约表里挂着这个 flag）
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
WXG = HERE / "scripts" / "wxg.py"
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(WXG), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )


def show(label: str, proc: subprocess.CompletedProcess) -> None:
    out = proc.stdout.strip()
    err = proc.stderr.strip()
    print(f"\n--- {label}: exit={proc.returncode}")
    print("  stdout:", (out[:400] + ("..." if len(out) > 400 else "")) or "<empty>")
    print("  stderr:", (err[:400] + ("..." if len(err) > 400 else "")) or "<empty>")
    if out:
        try:
            print("  stdout JSON keys:", list(json.loads(out))[:8])
        except json.JSONDecodeError:
            pass


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wxg-probe15-") as tmp:
        base = Path(tmp).resolve()
        root = base / "state"
        repo = base / "repo"
        repo.mkdir()
        (repo / "shop.py").write_text("def ping():\n    return 1\n", encoding="utf-8")

        show("P1a 未 init 直接 gate", run(root, "gate", "--feature", "x"))
        show("P1b 未知 feature-status", run(root, "feature-status", "--id", "nope"))
        print("   -> 缺库目录存在？", (root / "graph.sqlite").exists())

        print("\ninit:", run(root, "init").returncode)
        print("repo-add:", run(root, "repo-add", "--id", "demo", "--path", str(repo)).returncode)
        print("declare:", run(
            root, "feature-declare", "--id", "feat-p", "--name", "P", "--statement", "s",
            "--acceptance", "[]", "--constraints", "[]", "--no-coverage",
        ).returncode)

        show("P2 feature-list", run(root, "feature-list"))
        show("P3 repo-list", run(root, "repo-list"))
        show("P1c 未知 feature-status（有库）", run(root, "feature-status", "--id", "nope"))

        gate_plain = run(root, "gate", "--feature", "feat-p")
        gate_json = run(root, "gate", "--feature", "feat-p", "--json")
        show("P5a gate 无 --json", gate_plain)
        show("P5b gate 有 --json", gate_json)
        print("   -> gate 两种调用 stdout 相同？", gate_plain.stdout == gate_json.stdout)

        cov_plain = run(root, "coverage", "--feature", "feat-p")
        cov_json = run(root, "coverage", "--feature", "feat-p", "--json")
        print("   -> coverage --json 不改变输出？", cov_plain.stdout == cov_json.stdout)

        show("P4a --db-url 非法", run(root, "--db-url", "bogus://x", "doctor"))
        # --db-url 是否持久到后续调用（进程内 env 改写 vs 进程间）
        env2 = dict(ENV, WXG_DB_URL="bogus://env")
        proc = subprocess.run(
            [sys.executable, str(WXG), "--root", str(root), "doctor"],
            capture_output=True, text=True, encoding="utf-8", env=env2,
        )
        show("P4b WXG_DB_URL=bogus://env doctor", proc)


if __name__ == "__main__":
    main()
