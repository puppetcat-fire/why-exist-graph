"""Slice 15 探针：静态盘点 tests/。只读。"""
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

CLI_CMD_RE = re.compile(r'"(' + "|".join(sorted(CMDS, key=len, reverse=True)) + r')"')
TEST_RE = re.compile(r"^    def (test_\w+)", re.M)


def main(root: str = "tests") -> None:
    base = pathlib.Path(root)
    total_tests = total_asserts = total_lines = 0
    usage = collections.Counter()
    usage_where = collections.defaultdict(list)
    print(f"{'file':28} {'loc':>5} {'tests':>5} {'asserts':>7}  commands(uses)")
    for f in sorted(base.glob("test_*.py")):
        text = f.read_text(encoding="utf-8")
        lines = text.splitlines()
        tests = TEST_RE.findall(text)
        asserts = len(re.findall(r"self\.assert\w+\(", text))
        found = collections.Counter()
        for i, line in enumerate(lines, 1):
            for m in CLI_CMD_RE.finditer(line):
                found[m.group(1)] += 1
                usage_where[m.group(1)].append(f"{f.name}:{i}")
        total_tests += len(tests)
        total_asserts += asserts
        total_lines += len(lines)
        usage.update(found)
        cmds = ", ".join(f"{k}({v})" for k, v in sorted(found.items()))
        print(f"{f.name:28} {len(lines):5} {len(tests):5} {asserts:7}  {cmds}")
    print(f"\nTOTAL loc={total_lines} tests={total_tests} asserts={total_asserts}")
    print("\n== command coverage (quoted tokens in tests) ==")
    for c in CMDS:
        where = usage_where[c]
        mark = "ZERO" if not where else ""
        print(f"{c:20} {usage[c]:3} {mark} {where[:3]}")
    zero = [c for c in CMDS if not usage_where[c]]
    print("\nZERO-TEST COMMANDS:", zero)


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
