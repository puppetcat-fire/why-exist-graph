"""Slice-16 probe 3: what actually changed between the 11 dist builds."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
manifests = {}
for d in sorted((ROOT / "dist").glob("v*"), key=lambda p: [int(x) for x in p.name[1:].split(".")]):
    manifests[d.name] = json.loads((d / "manifest.json").read_text(encoding="utf-8"))

names = list(manifests)
for prev, cur in zip(names, names[1:]):
    a = {f["path"]: f["sha256"] for f in manifests[prev]["files"]}
    b = {f["path"]: f["sha256"] for f in manifests[cur]["files"]}
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    print(f"{prev} -> {cur}: changed={changed} added={added} removed={removed}")

print("\nsame-file-count:", {n: len(m["files"]) for n, m in manifests.items()})
