#!/usr/bin/env python3
"""Build a reproducible release zip for why-exist-graph.

Usage (from the repository root):
  python tools/build_release.py
  python tools/build_release.py --out dist
  python tools/build_release.py --version 0.4.0

产物（默认 dist/v<version>/）：
  why-exist-graph-<version>.zip   确定性的技能包（顶层目录 why-exist-graph/）
  manifest.json                   版本、契约/schema、文件清单与 SHA-256
  archive.sha256                  压缩包校验和

压缩包只包含可安装的技能文件（SKILL.md/VERSION/CHANGELOG.md/references/scripts/tests），
排除 __pycache__、*.pyc、状态库、仓库元数据（README/LICENSE/.github/tools/dist 等）。
zip 内时间戳固定、条目排序，重复构建应得到相同 SHA-256。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_SKILL = REPO

INCLUDE_FILES = ["SKILL.md", "VERSION", "CHANGELOG.md"]
INCLUDE_DIRS = ["references", "scripts", "tests"]
EXCLUDE_DIR_PARTS = {"__pycache__", ".git", ".why-exist", ".pytest_cache", ".wxg-tmp", ".verify", "dist"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".log", ".bak"}
FIXED_ZIP_TIME = (2026, 10, 29, 0, 0, 0)
ZIP_ROOT = "why-exist-graph"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_contract_versions(skill: Path) -> tuple[str, int]:
    spec = importlib.util.spec_from_file_location("wxg_contract_release", skill / "scripts" / "wxg_contract.py")
    if spec is None or spec.loader is None:
        raise SystemExit("无法加载 scripts/wxg_contract.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.CONTRACT_VERSION, module.SCHEMA_VERSION


def collect_files(skill: Path) -> list[Path]:
    files: list[Path] = []
    for rel in INCLUDE_FILES:
        path = skill / rel
        if not path.is_file():
            raise SystemExit(f"缺少发布文件：{rel}")
        files.append(path)
    for rel in INCLUDE_DIRS:
        base = skill / rel
        if not base.is_dir():
            raise SystemExit(f"缺少发布目录：{rel}")
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if any(part in EXCLUDE_DIR_PARTS for part in path.parts):
                continue
            if path.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            files.append(path)
    return sorted(set(files), key=lambda p: p.relative_to(skill).as_posix())


def build(skill: Path, out: Path, version: str) -> dict:
    contract_version, schema_version = read_contract_versions(skill)
    if contract_version != version:
        raise SystemExit(f"VERSION={version} 与契约版本 {contract_version} 不一致；发布版本必须与契约版本一致")
    skill_version = (skill / "VERSION").read_text(encoding="utf-8").strip()
    if skill_version != version:
        raise SystemExit(f"VERSION 文件为 {skill_version}，与请求的 {version} 不一致")

    out.mkdir(parents=True, exist_ok=True)
    archive = out / f"why-exist-graph-{version}.zip"
    files = collect_files(skill)
    entries = []
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            rel = path.relative_to(skill).as_posix()
            data = path.read_bytes()
            info = zipfile.ZipInfo(f"{ZIP_ROOT}/{rel}", date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o644 & 0xFFFF) << 16
            info.create_system = 3
            zf.writestr(info, data)
            entries.append({"path": rel, "size": len(data), "sha256": sha256_bytes(data)})

    archive_sha = sha256_file(archive)
    manifest = {
        "name": "why-exist-graph",
        "display_name": "why-exist-graph（DSH 原生设计图谱 + 交付门）",
        "version": version,
        "contract_version": contract_version,
        "schema_version": schema_version,
        "python_requires": ">=3.10",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {"repo": "."},
        "archive": {"path": archive.name, "size": archive.stat().st_size, "sha256": archive_sha},
        "install": {"target": "<workspace>/.dsh/skills/why-exist-graph", "zip_root": ZIP_ROOT + "/"},
        "files": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "archive.sha256").write_text(f"{archive_sha}  {archive.name}\n", encoding="utf-8")
    return manifest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="构建 why-exist-graph 发布包")
    parser.add_argument("--skill", default=str(DEFAULT_SKILL), help="技能目录（默认仓库根）")
    parser.add_argument("--out", default=None, help="输出目录（默认 dist/v<version>）")
    parser.add_argument("--version", default=None, help="发布版本（默认读取 VERSION）")
    args = parser.parse_args(argv)
    skill = Path(args.skill).resolve()
    version = args.version or (skill / "VERSION").read_text(encoding="utf-8").strip()
    out = Path(args.out).resolve() if args.out else skill / "dist" / f"v{version}"
    manifest = build(skill, out, version)
    print(json.dumps({
        "version": manifest["version"],
        "contract_version": manifest["contract_version"],
        "schema_version": manifest["schema_version"],
        "archive": manifest["archive"],
        "files": len(manifest["files"]),
        "out": str(out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
