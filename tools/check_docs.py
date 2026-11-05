"""文档完整性检查。

四项：
1. 版本号一致：VERSION / CONTRACT_VERSION / CHANGELOG 最新条目三者相同。
2. CHANGELOG 连续：无重复、无跳跃、最新在前。
3. design.md 节号连续：无重复、无缺号。
4. 文档不写死易漂移的事实：版本号与用例数只能有一个真源，文档里出现
   「当前版本 X.Y.Z」「Ran N tests」这类写死副本即报错。

跑法：python tools/check_docs.py
退出码 0 = 全部通过；1 = 有问题。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CHANGELOG = SKILL / "CHANGELOG.md"
DESIGN = SKILL / "references" / "design.md"
VERSION = SKILL / "VERSION"
CONTRACT = SKILL / "scripts" / "wxg_contract.py"

CHANGELOG_PATTERN = re.compile(r"^##\s+(\d+)\.(\d+)\.(\d+)", re.MULTILINE)
DESIGN_PATTERN = re.compile(r"^##\s+(\d+)\.\s", re.MULTILINE)

#: 会写用户可见文案、但历史上反复写死版本/用例数的文档。
PINNED_DOCS = {
    "README.md": SKILL / "README.md",
    "CONTRIBUTING.md": SKILL / "CONTRIBUTING.md",
    "docs/HANDOFF.md": SKILL / "docs" / "HANDOFF.md",
    "docs/PRODUCT-PLAN.md": SKILL / "docs" / "PRODUCT-PLAN.md",
    "references/quality.md": SKILL / "references" / "quality.md",
}

#: 每种写死副本的识别规则。命中即报，因为它们的真源分别在 VERSION 和测试汇总行。
PINNED_PATTERNS = (
    (re.compile(r"当前[^\n]{0,24}\bv?\d+\.\d+\.\d+\b"), "写死了「当前版本」"),
    (re.compile(r"Ran\s+\d+\s+tests"), "写死了测试用例数"),
    (re.compile(r"\|\s*测试\s*\|[^\n]*\d+\s*个"), "写死了测试用例数"),
    (re.compile(r"\|\s*版本\s*\|[^\n]*\d+\.\d+\.\d+"), "写死了版本号"),
    (re.compile(r"\d+\s*个[\u4e00-\u9fa5]{0,4}(回归)?用例"), "写死了测试用例数"),
    (re.compile(r"\d+\s*个端到端"), "写死了测试用例数"),
)


def as_key(parts: tuple[str, str, str] | tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def check_versions() -> list[str]:
    issues = []
    file_version = VERSION.read_text(encoding="utf-8").strip()
    contract_text = CONTRACT.read_text(encoding="utf-8")
    match = re.search(r'CONTRACT_VERSION\s*=\s*"([^"]+)"', contract_text)
    contract_version = match.group(1) if match else ""
    if file_version != contract_version:
        issues.append(f"VERSION（{file_version}）与 CONTRACT_VERSION（{contract_version}）不一致")
    changelog_versions = [".".join(parts) for parts in CHANGELOG_PATTERN.findall(
        CHANGELOG.read_text(encoding="utf-8")
    )]
    if not changelog_versions:
        issues.append("CHANGELOG 里没有版本条目")
        return issues
    newest = max(changelog_versions, key=lambda v: as_key(tuple(v.split("."))))
    if newest != file_version:
        issues.append(f"CHANGELOG 最新条目（{newest}）与 VERSION（{file_version}）不一致")
    return issues


def check_changelog() -> tuple[list[str], str]:
    text = CHANGELOG.read_text(encoding="utf-8")
    versions = [".".join(parts) for parts in CHANGELOG_PATTERN.findall(text)]
    issues = []
    if not versions:
        return ["CHANGELOG 没有版本条目"], ""
    ordered = sorted(versions, key=lambda v: as_key(tuple(v.split("."))))
    duplicates = sorted({v for v in versions if versions.count(v) > 1})
    if duplicates:
        issues.append(f"CHANGELOG 重复版本：{duplicates}")
    for previous, current in zip(ordered, ordered[1:]):
        p, c = as_key(tuple(previous.split("."))), as_key(tuple(current.split(".")))
        if c[0] == p[0] + 1 and c[1] == 0 and c[2] == 0:
            continue  # major 升级
        pn, cn = p[0] * 10000 + p[1] * 100 + p[2], c[0] * 10000 + c[1] * 100 + c[2]
        if cn - pn > 100:
            issues.append(f"CHANGELOG 版本跳跃：{previous} -> {current}")
    if versions != sorted(versions, key=lambda v: as_key(tuple(v.split("."))), reverse=True):
        issues.append("CHANGELOG 顺序不是最新在前")
    return issues, f"{len(versions)} 条，{ordered[0]} ~ {ordered[-1]}"


def check_design() -> tuple[list[str], str]:
    text = DESIGN.read_text(encoding="utf-8")
    numbers = [int(value) for value in DESIGN_PATTERN.findall(text)]
    issues = []
    if not numbers:
        return ["design.md 没有编号节"], ""
    duplicates = sorted({n for n in numbers if numbers.count(n) > 1})
    if duplicates:
        issues.append(f"design.md 重复节号：{duplicates}")
    missing = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
    if missing:
        issues.append(f"design.md 缺号：{missing}")
    return issues, f"{len(numbers)} 节，1 ~ {max(numbers)}"


def check_pinned_facts() -> tuple[list[str], str]:
    """文档里不许写死版本号与用例数——这两样只能有一个真源。"""
    issues: list[str] = []
    scanned = 0
    for label, path in PINNED_DOCS.items():
        if not path.is_file():
            issues.append(f"{label} 不存在")
            continue
        scanned += 1
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for pattern, why in PINNED_PATTERNS:
                if pattern.search(line):
                    issues.append(f"{label}:{lineno} {why}：{line.strip()[:70]}")
    return issues, f"{scanned} 份文档"


def main() -> int:
    all_issues: list[str] = []
    all_issues += check_versions()

    changelog_issues, changelog_summary = check_changelog()
    all_issues += changelog_issues
    print(f"CHANGELOG：{changelog_summary or '—'}")

    design_issues, design_summary = check_design()
    all_issues += design_issues
    print(f"design.md：{design_summary or '—'}")

    pinned_issues, pinned_summary = check_pinned_facts()
    all_issues += pinned_issues
    print(f"写死副本：{pinned_summary}，{len(pinned_issues)} 处")

    if all_issues:
        print(f"\n文档完整性：{len(all_issues)} 个问题")
        for issue in all_issues:
            print(f"  - {issue}")
        return 1
    print("\n文档完整性：PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
