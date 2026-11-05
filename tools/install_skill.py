"""把发布包安装到本机 DSH 技能目录。

跑法：
    python tools/install_skill.py                 # 用 dist/ 下最新版本的包
    python tools/install_skill.py --zip <path>    # 指定 zip
    python tools/install_skill.py --dry-run       # 只报计划，不动文件
    python tools/install_skill.py --target <dir>  # 换安装目标

做四件事：
1. 从 dist/ 里挑最新发布包（按 mtime，不按字符串——v2.9.0 与 v2.74.0 并存时
   字符串排序会把前者当最新）。
2. 把现有技能目录备份到系统临时目录（不放在 skills/ 旁边：那会被当成技能扫描到）。
3. 删旧目录再解压，保证装出来的是包内文件集，不残留上一版的孤儿文件。
   这是本项目反复踩过的一类问题：旧的 re-export / 旧文档片段留在目录里没人删。
4. 跑包内 `scripts/wxg.py verify` 自检，确认装进去的这份能独立通过契约校验。

退出码 0 = 安装并自检通过；1 = 失败。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
DIST = SKILL / "dist"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

DEFAULT_TARGET = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~")) / ".dsh" / "skills" / "why-exist-graph"
ZIP_ROOT = "why-exist-graph"


def latest_zip() -> Path:
    candidates = [p for p in DIST.glob("v*/why-exist-graph-*.zip") if p.is_file()]
    if not candidates:
        raise SystemExit(f"dist/ 下没有发布包：{DIST}（先跑 python tools/build_release.py）")
    return max(candidates, key=lambda p: p.stat().st_mtime)


def backup_dir() -> Path:
    base = Path(os.environ.get("TEMP") or os.environ.get("TMP") or os.getcwd())
    return base / "wxg-skill-backup" / time.strftime("%Y%m%d-%H%M%S")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="把发布包安装到本机 DSH 技能目录")
    parser.add_argument("--zip", default=None, help="发布包路径（默认 dist/ 下最新）")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="安装目标目录")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划，不改文件")
    args = parser.parse_args(argv)

    zip_path = Path(args.zip).resolve() if args.zip else latest_zip()
    target = Path(args.target).resolve()

    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        top = {name.split("/")[0] for name in names}
        if top != {ZIP_ROOT}:
            raise SystemExit(f"包结构不符合预期：顶层应为 {ZIP_ROOT}/，实际 {sorted(top)[:5]}")
        version = next(
            (line for line in archive.read(f"{ZIP_ROOT}/VERSION").decode("utf-8").splitlines() if line.strip()),
            "",
        ).strip()
        member_count = len([n for n in names if not n.endswith("/")])

    print(f"[1] 包：{zip_path.name}  version={version}  {member_count} 个文件")
    print(f"[2] 目标：{target}")
    if args.dry_run:
        print("    --dry-run：不修改任何文件")
        return 0

    if target.exists():
        bak = backup_dir()
        bak.mkdir(parents=True, exist_ok=True)
        shutil.copytree(target, bak, dirs_exist_ok=True)
        print(f"[3] 备份旧目录 -> {bak}（{len(list(bak.rglob('*')))} 项）")
        shutil.rmtree(target)
    else:
        print("[3] 目标不存在，全新安装")

    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(target.parent)

    installed = target / "VERSION"
    if not installed.is_file():
        raise SystemExit(f"解压后没有找到 {installed}")
    got = installed.read_text(encoding="utf-8").strip()
    if got != version:
        raise SystemExit(f"解压后 VERSION={got}，与包内 {version} 不一致")
    count = len([p for p in target.rglob("*") if p.is_file()])
    print(f"[4] 已安装：{count} 个文件，VERSION={got}")

    wxg = target / "scripts" / "wxg.py"
    if not wxg.is_file():
        raise SystemExit(f"安装后没有 {wxg}")
    proc = subprocess.run(
        [sys.executable, str(wxg), "verify"],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    if proc.returncode != 0 or '"ok": true' not in proc.stdout:
        print(proc.stdout[-800:])
        print(proc.stderr[-800:])
        raise SystemExit("安装后的技能没通过 verify 自检")
    print("[5] 自检：verify ok")

    print(f"\n安装完成：{target}  ({version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
