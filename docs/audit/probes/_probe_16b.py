"""Slice-16 probe 2: env vars, doc references, installed-vs-repo skill diff, test coverage pointers."""
from __future__ import annotations

import glob
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

print("== env vars read by code ==")
envs: dict[str, set[str]] = defaultdict(set)
for pattern in ("scripts/**/*.py", "tools/*.py", "tests/*.py"):
    for f in glob.glob(str(ROOT / pattern), recursive=True):
        text = Path(f).read_text(encoding="utf-8")
        for m in re.finditer(r"""environ(?:\.get)?[\(\[]\s*["']([A-Z_]+)""", text):
            envs[m.group(1)].add(str(Path(f).relative_to(ROOT)))
for key in sorted(envs):
    print(" ", key, sorted(envs[key])[:6])

print("\n== env vars documented ==")
docs = {}
for pattern in ("*.md", "docs/*.md", "references/*.md"):
    for f in glob.glob(str(ROOT / pattern)):
        docs[str(Path(f).relative_to(ROOT))] = Path(f).read_text(encoding="utf-8")
for key in sorted(envs):
    hits = [name for name, text in docs.items() if key in text]
    print(" ", key, "documented_in=", hits)

print("\n== refactor-lab references in docs ==")
for name, text in docs.items():
    for i, line in enumerate(text.split("\n"), 1):
        if "refactor-lab" in line:
            print(f"  {name}:{i}: {line.strip()[:120]}")

print("\n== tools/ referenced from docs ==")
for script in sorted(p.name for p in (ROOT / "tools").glob("*.py")):
    hits = [name for name, text in docs.items() if script in text]
    print(" ", script, hits)

print("\n== commands mentioned in README vs contract ==")
import sys
sys.path.insert(0, str(ROOT / "scripts"))
import wxg_contract as C

readme = (ROOT / "README.md").read_text(encoding="utf-8")
skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
for name in C.COMMANDS:
    in_readme = bool(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", readme))
    in_skill = bool(re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", skill))
    if not in_readme or not in_skill:
        print(f"  {name:16s} README={in_readme} SKILL={in_skill}")

print("\n== frontmatter lengths ==")
def front(text: str) -> str:
    return text.split("---", 2)[1]
installed = Path("C:/Users/xiaob/.dsh/skills/why-exist-graph/SKILL.md").read_text(encoding="utf-8")
print("repo frontmatter == installed frontmatter:", front(skill) == front(installed))
print("repo len", len(skill), "installed len", len(installed))
inst_cmds = set(re.findall(r"^\| `([a-z][a-z-]+)` \|", installed, re.M))
print("installed command rows:", len(inst_cmds))
print("missing from installed:", sorted(set(C.COMMANDS) - inst_cmds))
print("extra in installed:", sorted(inst_cmds - set(C.COMMANDS)))
