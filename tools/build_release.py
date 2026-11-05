#!/usr/bin/env python3
"""Build a reproducible release zip for why-exist-graph.

Usage (from the repository root):
  python tools/build_release.py
  python tools/build_release.py --out dist
  python tools/build_release.py --version 1.4.0
  python tools/build_release.py --allow-dirty     # 明知工作树脏还打包

产物（默认 dist/v<version>/）：
  why-exist-graph-<version>.zip   确定性的技能包（顶层目录 why-exist-graph/）
  manifest.json                   版本、契约/schema、来源 commit、文件清单与 SHA-256
  archive.sha256                  压缩包校验和

压缩包只包含可安装的技能文件（SKILL.md/VERSION/CHANGELOG.md/references/scripts/tests），
排除 __pycache__、*.pyc、状态库、仓库元数据（README/LICENSE/.github/tools/dist 等）。
zip 内时间戳固定、条目排序，重复构建应得到相同 SHA-256。

默认拒绝在脏工作树上打包：产物必须能追到一个 commit，否则 manifest 里的 commit
就没有意义（历史上 2.x 长期在未提交的工作树上打包，导致 11 个 dist 包都无法溯源）。
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
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


def git_state(repo: Path) -> tuple[str, bool]:
    """返回 (HEAD commit, 工作树是否脏)。不在 git 仓里时返回 ("", False)。"""
    try:
        head = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        if head.returncode != 0:
            return "", False
        status = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        return head.stdout.strip(), bool(status.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return "", False


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


def build(skill: Path, out: Path, version: str, *, allow_dirty: bool = False) -> dict:
    contract_version, schema_version = read_contract_versions(skill)
    if contract_version != version:
        raise SystemExit(f"VERSION={version} 与契约版本 {contract_version} 不一致；发布版本必须与契约版本一致")
    skill_version = (skill / "VERSION").read_text(encoding="utf-8").strip()
    if skill_version != version:
        raise SystemExit(f"VERSION 文件为 {skill_version}，与请求的 {version} 不一致")

    commit, dirty = git_state(skill)
    if dirty and not allow_dirty:
        raise SystemExit(
            "工作树有未提交改动，拒绝打包：产物必须能追到一个 commit。\n"
            "先提交，或确认这次打包不要溯源时加 --allow-dirty。"
        )

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
        "source": {"repo": ".", "commit": commit, "dirty": dirty},
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
    parser.add_argument("--allow-dirty", action="store_true", help="允许在未提交的工作树上打包（manifest 会标 dirty）")
    args = parser.parse_args(argv)
    skill = Path(args.skill).resolve()
    version = args.version or (skill / "VERSION").read_text(encoding="utf-8").strip()
    out = Path(args.out).resolve() if args.out else skill / "dist" / f"v{version}"
    manifest = build(skill, out, version, allow_dirty=args.allow_dirty)
    print(json.dumps({
        "version": manifest["version"],
        "contract_version": manifest["contract_version"],
        "schema_version": manifest["schema_version"],
        "commit": manifest["source"]["commit"],
        "dirty": manifest["source"]["dirty"],
        "archive": manifest["archive"],
        "files": len(manifest["files"]),
        "out": str(out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
