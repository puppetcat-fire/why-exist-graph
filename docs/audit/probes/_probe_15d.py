"""Slice 15 探针 4：命令 -> 测试方法映射（按方法体扫描）。只读。"""
from __future__ import annotations

import collections
import pathlib
import re
import sys

CMDS = """init up repo-add repo-list import-file import-repo derive promote sample
feature-declare feature-register feature-list feature-status change-open change-diff
work-open work-seed work-claim work-finish work-judge work-list upsert-node upsert-edge
bind retract bite evidence-record evidence-list coverage reconcile serve sync plan cycles
brief blind-check patch apply impact conflicts conformance gate export slice get find
role-prompt contract verify doctor""".split()

TOKEN_RE = re.compile(r'"(' + "|".join(sorted(CMDS, key=len, reverse=True)) + r')"')
METHOD_RE = re.compile(r"^    def (test_\w+)\(", re.M)


def main(root: str = "tests") -> None:
    base = pathlib.Path(root)
    cmd_methods: dict[str, list[str]] = collections.defaultdict(list)
    for f in sorted(base.glob("test_*.py")):
        text = f.read_text(encoding="utf-8")
        starts = [(m.start(), m.group(1)) for m in METHOD_RE.finditer(text)]
        # 行号索引
        line_starts = [0]
        for i, ch in enumerate(text):
            if ch == "\n":
                line_starts.append(i + 1)
        def line_of(pos: int) -> int:
            lo, hi = 0, len(line_starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if line_starts[mid] <= pos:
                    lo = mid
                else:
                    hi = mid - 1
            return lo + 1
        for idx, (pos, name) in enumerate(starts):
            end = starts[idx + 1][0] if idx + 1 < len(starts) else len(text)
            body = text[pos:end]
            seen = {m.group(1) for m in TOKEN_RE.finditer(body)}
            for cmd in sorted(seen):
                cmd_methods[cmd].append(f"{f.name}:{line_of(pos)}:{name}")
    print("== command -> tests ==")
    for c in CMDS:
        entries = cmd_methods.get(c, [])
        print(f"\n### {c}  ({len(entries)})")
        for e in entries:
            print("   ", e)
    print("\n== zero ==")
    print([c for c in CMDS if not cmd_methods.get(c)])


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
