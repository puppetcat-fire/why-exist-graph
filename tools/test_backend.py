"""跑 MySQL / PostgreSQL 后端集成测试。

测试会 **清空目标库的所有表**（`SHOW TABLES` + `DROP`），只能指向可丢弃的库。
这些用例平时默认 skip，所以本地这条命令就是它们唯一的常规入口。

    PowerShell:
      $env:WXG_TEST_MYSQL_URL = "mysql://root:pass@127.0.0.1:3307/wxg"
      $env:WXG_TEST_PG_URL    = "postgresql://postgres:pass@127.0.0.1:5433/wxg"
    bash:
      export WXG_TEST_MYSQL_URL=mysql://root:pass@127.0.0.1:3307/wxg

跑法：
    python tools/test_backend.py            # 配了哪个跑哪个，都没配就给提示
    python tools/test_backend.py --strict   # 一个都没配就退出 1（给 CI / preflight 用）
    python tools/test_backend.py --only mysql

退出码：0 = 已跑的用例全过；1 = 有失败，或 --strict 下一个都没跑。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

#: (显示名, 环境变量, 测试模块, --only 取值)
TARGETS = (
    ("MySQL/MariaDB", "WXG_TEST_MYSQL_URL", "tests.test_mysql_backend", "mysql"),
    ("PostgreSQL", "WXG_TEST_PG_URL", "tests.test_pg_backend", "pg"),
)


def mask(url: str) -> str:
    return re.sub(r"//([^:/@]+):[^@]*@", r"//\1:***@", url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="跑 MySQL / PostgreSQL 后端集成测试")
    parser.add_argument("--strict", action="store_true", help="一个后端都没配时退出 1")
    parser.add_argument("--only", choices=["mysql", "pg"], default=None, help="只跑一个后端")
    args = parser.parse_args(argv)

    results: list[tuple[str, int]] = []
    for label, var, module, key in TARGETS:
        if args.only and args.only != key:
            continue
        url = os.environ.get(var, "").strip()
        if not url:
            print(f"- {label}：跳过（未设置 {var}）")
            continue
        print(f"- {label}：{module}  ({mask(url)})")
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", module, "-v"],
            cwd=str(SKILL), env=ENV, capture_output=True, text=True, encoding="utf-8",
        )
        for line in proc.stderr.splitlines():
            if line.startswith(("Ran ", "OK", "FAILED")):
                print(f"  {line}")
        if proc.returncode != 0:
            print(proc.stderr[-1500:])
        results.append((label, proc.returncode))

    if not results:
        print("\n没有可跑的后端：设置 WXG_TEST_MYSQL_URL / WXG_TEST_PG_URL。")
        print("注意这些用例会清空目标库的所有表，只能指向可丢弃的库。")
        return 1 if args.strict else 0

    failed = [label for label, code in results if code != 0]
    if failed:
        print(f"\n后端集成测试失败：{', '.join(failed)}")
        return 1
    print(f"\n后端集成测试通过：{', '.join(label for label, _ in results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
