"""校验 `docs/RELEASE-*.md` 里写的校验和与 dist 产物是否一致。

为什么需要它：这个数字被手写过两次，两次都错（3.2.2 与 3.5.0）。错法和其它漂移
一样——文档说一个 SHA，dist 里是另一个，而当时没有任何检查会发现。发布说明是给
用户核对下载完整性的，写错比不写更糟。

跑法：
    python tools/check_release_notes.py
    python tools/check_release_notes.py docs/RELEASE-3.5.0.md

退出码 0 = 全部一致（或该版本没有 dist 产物可对照）；1 = 有对不上的。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
DIST = SKILL / "dist"
NOTES = SKILL / "docs"

SHA_RE = re.compile(r"\b([0-9a-f]{64})\b")
NOTE_RE = re.compile(r"RELEASE-(\d+\.\d+\.\d+)\.md$")


def archive_sha(version: str) -> str | None:
    path = DIST / f"v{version}" / "archive.sha256"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8").split()[0].strip()


def check_note(note: Path) -> tuple[bool, str]:
    match = NOTE_RE.search(note.name)
    if not match:
        return True, "（文件名不是 RELEASE-<version>.md，跳过）"
    version = match.group(1)
    expected = archive_sha(version)
    if expected is None:
        return True, f"v{version} 没有 dist 产物，跳过"
    found = set(SHA_RE.findall(note.read_text(encoding="utf-8")))
    if not found:
        return False, f"发布说明里没有 SHA-256，无法核对（dist 的是 {expected[:12]}…）"
    # 只要求「提到 dist 的那个值」，不要求「只提这一个」——历史说明里会同时记录
    # 当时错误的产物和后来修正后的产物（例如 2.97 的 CRLF 脏版本与 CI 附件）。
    if expected not in found:
        return False, f"说明里没有 dist 的 SHA：dist 是 {expected[:12]}…，说明里找到 {sorted(s[:12] for s in found)}"
    return True, "ok"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    notes = [Path(item) for item in args] if args else sorted(NOTES.glob("RELEASE-*.md"))
    if not notes:
        print("没有找到 docs/RELEASE-*.md")
        return 0

    bad = 0
    for note in notes:
        if not note.is_file():
            print(f"{note}: 不存在")
            bad += 1
            continue
        ok, detail = check_note(note)
        name = note.relative_to(SKILL) if note.is_relative_to(SKILL) else note
        print(f"{name}: {detail}")
        if not ok:
            bad += 1

    if bad:
        print(f"\n发布说明校验：{bad} 个文件有问题")
        return 1
    print(f"\n发布说明校验：{len(notes)} 个文件，全部一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
