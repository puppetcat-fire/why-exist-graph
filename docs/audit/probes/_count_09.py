"""Count per-command assertion density in the two test files (read-only), including helpers."""
import ast
import json
import re
from pathlib import Path

PROJ = Path(__file__).resolve().parent.parent.parent
COMMANDS = ["feature-declare", "feature-register", "feature-list", "feature-status",
            "change-open", "change-diff", "work-seed", "work-open", "work-claim",
            "work-finish", "work-judge", "work-list"]
# test helper -> commands it drives (helpers are methods on the shared TestCase)
HELPERS = {
    "declare": ["feature-declare"],
    "status": ["feature-status"],
    "open_targets": ["work-open"],
    "claim": ["work-claim"],
    "finish": ["work-finish"],
    "judge": ["work-judge"],
    "force_ready": [],
    "import_scan": ["import-file", "work-claim"],
    "complete_through_implement": ["work-open", "work-claim", "work-finish", "work-judge"],
}

report = {}
for rel in ("tests/test_wxg.py", "tests/test_plan_cli.py"):
    src = (PROJ / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    tests = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            seg = ast.get_source_segment(src, node)
            counts = {cmd: len(re.findall(r'"' + re.escape(cmd) + r'"', seg)) for cmd in COMMANDS}
            for helper, cmds in HELPERS.items():
                n = len(re.findall(r"self\." + helper + r"\(", seg))
                for cmd in cmds:
                    if cmd in counts:
                        counts[cmd] += n
            tests[node.name] = counts
    report[rel] = {
        "tests_total": len(tests),
        "per_command": {
            cmd: {
                "tests_reaching": sum(1 for t in tests.values() if t[cmd] > 0),
                "invocations": sum(t[cmd] for t in tests.values()),
            }
            for cmd in COMMANDS
        },
    }
print(json.dumps(report, ensure_ascii=False, indent=2))
