"""Slice 15 探针 3：列出每个测试方法及其行号。只读。"""
from __future__ import annotations

import pathlib
import re
import sys

TEST_RE = re.compile(r"^    def (test_\w+)\(", re.M)


def main(root: str = "tests") -> None:
    for f in sorted(pathlib.Path(root).glob("test_*.py")):
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        print(f"\n== {f.name} ({len(lines)} lines)")
        for i, line in enumerate(lines, 1):
            m = re.match(r"^    def (test_\w+)\(", line)
            if m:
                print(f"   {i:5}  {m.group(1)}")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
