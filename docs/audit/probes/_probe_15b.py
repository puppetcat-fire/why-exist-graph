"""Slice 15 探针 2：契约常量与命令形状。只读。"""
from __future__ import annotations

import sys
import json

sys.path.insert(0, "scripts")
from whyexist.contract import C  # noqa: E402


def main() -> None:
    print("CONTRACT VERSION", getattr(C, "CONTRACT_VERSION", "?"),
          "SCHEMA", getattr(C, "SCHEMA_VERSION", "?"),
          "COMMANDS", len(C.COMMANDS))
    print("\nEXPORT_FILES:")
    for f in C.EXPORT_FILES:
        print("  ", f["name"], "|", f["title"], "| cols", len(f["columns"]))
    print("\nexport options:", [(o["flag"], o["required"]) for o in C.COMMANDS["export"]["options"]])
    print("export flags:", [f["flag"] for f in C.COMMANDS["export"]["flags"]])
    print("feature-list options:", C.COMMANDS["feature-list"]["options"])
    print("feature-list flags:", C.COMMANDS["feature-list"]["flags"])
    print("\nCOMMAND_WRITE_MODES:", len(C.COMMAND_WRITE_MODES))
    print(json.dumps(C.COMMAND_WRITE_MODES, ensure_ascii=False, indent=1))
    print("\nROLES keys:", list(C.ROLES))
    print("CONDITIONS:", C.CONDITIONS)


if __name__ == "__main__":
    main()
