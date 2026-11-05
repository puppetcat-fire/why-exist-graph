"""Slice 15 探针 7：变异测试（只在临时副本上改，不碰仓库源码）。

目的：验证这套测试对实现回归的敏感度，而不是只看「有没有 assert」。
每个变异体在副本里改一处，跑对应测试方法，记录是否 FAIL。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
ENV = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")

MUTANTS = [
    (
        "M1 graph_algo.max_antichain 恒返回节点数",
        "scripts/whyexist/graph_algo.py",
        "def max_antichain(nodes: list[str], edges: list[tuple[str, str]]) -> int:",
        "def max_antichain(nodes: list[str], edges: list[tuple[str, str]]) -> int:\n    return len(list(nodes))",
        "tests.test_graph_algo.MaxAntichainTest.test_chain_antichain_is_one",
    ),
    (
        "M2 derive.group_key 忽略 depth",
        "scripts/whyexist/derive.py",
        'parts = [part for part in path.replace("\\\\", "/").split("/") if part]',
        'parts = [part for part in path.replace("\\\\", "/").split("/") if part][:1]',
        "tests.test_derive.GroupKeyTest.test_two_levels",
    ),
    (
        "M3 work.target_match 只认精确匹配",
        "scripts/whyexist/work.py",
        'return pattern.endswith("*") and node_id.startswith(pattern[:-1])',
        'return pattern == node_id',
        "tests.test_package_units.WorkTargetTest.test_target_match_exact_and_wildcard",
    ),
    (
        "M4 CLI 把 gate 的 FAIL 退出码改成 0",
        "scripts/whyexist/cli.py",
        'return 0 if result.get("result") == "PASS" else 1',
        'return 0 if result.get("result") == "PASS" else 0',
        "tests.test_plan_cli.PlanCase.test_gate_checks_report_each_item",
    ),
    (
        "M5 错误 JSON 改打到 stdout",
        "scripts/whyexist/cli.py",
        'print(dumps({"error": str(exc)}), file=sys.stderr)\n        return 2\n    except Exception as exc:',
        'print(dumps({"error": str(exc)}))\n        return 2\n    except Exception as exc:',
        "tests.test_plan_cli.PlanCase.test_plan_rejects_unknown_feature",
    ),
]


def mutate_copy(src: Path, dst: Path, rel: str, old: str, new: str) -> bool:
    shutil.copytree(src, dst)
    path = dst / rel
    text = path.read_text(encoding="utf-8")
    if old not in text:
        return False
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return True


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="wxg-mut-") as tmp:
        base = Path(tmp)
        for idx, (label, rel, old, new, test) in enumerate(MUTANTS, 1):
            copy = base / f"m{idx}"
            applied = mutate_copy(HERE, copy, rel, old, new)
            if not applied:
                print(f"{label}: 变异点未找到，跳过")
                continue
            proc = subprocess.run(
                [sys.executable, "-m", "unittest", test, "-v"],
                cwd=str(copy), capture_output=True, text=True, encoding="utf-8", env=ENV,
            )
            killed = proc.returncode != 0
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
            print(f"{label}: 测试{'杀掉变异体（FAIL）' if killed else '全绿（漏检）'} :: {test} :: {tail[0][:90]}")
            shutil.rmtree(copy, ignore_errors=True)


if __name__ == "__main__":
    main()
