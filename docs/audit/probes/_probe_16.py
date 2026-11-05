"""Slice-16 probe: regenerate export sample, diff against references/, inspect release chain."""
from __future__ import annotations

import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_sample  # noqa: E402
import wxg  # noqa: E402

print("== export sample regeneration ==")
with tempfile.TemporaryDirectory() as tmp:
    state = gen_sample.build(Path(tmp) / "state")
    produced = state / "export" / gen_sample.FEATURE
    ref = ROOT / "references" / "export-sample" / "feat-demo"
    prod_files = sorted(p.name for p in produced.iterdir())
    ref_files = sorted(p.name for p in ref.iterdir())
    print("produced:", prod_files)
    print("reference:", ref_files)
    for name in sorted(set(prod_files) | set(ref_files)):
        a = (produced / name).read_bytes() if (produced / name).is_file() else None
        b = (ref / name).read_bytes() if (ref / name).is_file() else None
        print(f"  {name}: {'SAME' if a == b else 'DIFF'}  prod={None if a is None else len(a)} ref={None if b is None else len(b)}")
        if a is not None and b is not None and a != b:
            print("   prod:", a.decode("utf-8")[:400].replace("\n", "\\n"))
            print("   ref :", b.decode("utf-8")[:400].replace("\n", "\\n"))

print("\n== dist manifests ==")
for d in sorted((ROOT / "dist").glob("v*")):
    m = json.loads((d / "manifest.json").read_text(encoding="utf-8"))
    sha_line = (d / "archive.sha256").read_text(encoding="utf-8").split()[0]
    zpath = d / m["archive"]["path"]
    zexists = zpath.is_file()
    zsize = zpath.stat().st_size if zexists else -1
    print(f"{d.name}: version={m['version']} contract={m['contract_version']} schema={m['schema_version']} "
          f"files={len(m['files'])} gen={m['generated_at']} zip={'ok' if zexists and zsize == m['archive']['size'] else 'MISMATCH'} "
          f"sha_line={'ok' if sha_line == m['archive']['sha256'] else 'MISMATCH'}")
    # what does the zip's VERSION say?
    if zexists:
        with zipfile.ZipFile(zpath) as zf:
            names = zf.namelist()
            try:
                v = zf.read("why-exist-graph/VERSION").decode().strip()
            except KeyError:
                v = "<no VERSION>"
            has_docs = any(n.startswith("why-exist-graph/docs/") for n in names)
            has_readme = "why-exist-graph/README.md" in names
            has_tools = any(n.startswith("why-exist-graph/tools/") for n in names)
            skill_bytes = zf.read("why-exist-graph/SKILL.md")
            print(f"   zip VERSION={v} entries={len(names)} docs/={has_docs} README={has_readme} tools/={has_tools} "
                  f"skill_sha_in_zip={__import__('hashlib').sha256(skill_bytes).hexdigest()[:12]}")

print("\n== current tree hashes ==")
import hashlib
for rel in ["SKILL.md", "VERSION", "CHANGELOG.md", "references/contract.md", "references/design.md"]:
    p = ROOT / rel
    print(rel, len(p.read_bytes()), hashlib.sha256(p.read_bytes()).hexdigest()[:12])
