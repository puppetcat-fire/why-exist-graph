"""Slice 15 探针 6：反例密度 / 重复代码块 / 断言分布。只读。"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys

NEG_PATTERNS = {
    "expect=2": r"expect=2",
    "expect=1": r"expect=1",
    "assertRaises": r"self\.assertRaises\w*\(",
    "error-key": r"\[\"error\"\]",
    "FAIL断言": r"\"FAIL\"",
    "skip": r"SkipTest|skipUnless|skipIf",
}


def blocks(text: str, size: int = 8):
    lines = [line.strip() for line in text.splitlines()]
    for i in range(len(lines) - size + 1):
        chunk = lines[i:i + size]
        if sum(1 for line in chunk if line) < size - 1:
            continue
        yield "\n".join(chunk)


def main(root: str = "tests") -> None:
    base = pathlib.Path(root)
    seen: dict[str, list[str]] = {}
    files = sorted(base.glob("test_*.py"))
    print(f"{'file':26} {'loc':>5} " + " ".join(f"{k:>12}" for k in NEG_PATTERNS))
    for f in files:
        text = f.read_text(encoding="utf-8")
        counts = [len(re.findall(p, text)) for p in NEG_PATTERNS.values()]
        print(f"{f.name:26} {len(text.splitlines()):5} " + " ".join(f"{v:12}" for v in counts))
    print("\n== 跨文件重复的 8 行块（出现 >=2 个文件） ==")
    for f in files:
        text = f.read_text(encoding="utf-8")
        for b in blocks(text):
            key = hashlib.sha1(b.encode("utf-8")).hexdigest()
            seen.setdefault(key, [])
            if f.name not in seen[key]:
                seen[key].append(f.name)
    shown = 0
    for key, names in seen.items():
        if len(names) >= 2:
            print(f"  files={sorted(names)}")
            shown += 1
            if shown >= 12:
                break
    print("duplicated-block groups (>=2 files):", sum(1 for n in seen.values() if len(n) >= 2))


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
