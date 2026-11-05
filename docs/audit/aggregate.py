"""把 docs/audit 下 16 片契约卡汇总成 SUMMARY.md。

只读 *-*.json，不碰源码。容忍个别卡 JSON 损坏（跳过并记录）。
"""

from __future__ import annotations

import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load_cards() -> tuple[list[dict], list[str]]:
    cards, bad = [], []
    for p in sorted(HERE.glob("[0-9][0-9]-*.json")):
        try:
            card = json.loads(p.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            bad.append(f"{p.name}: {type(exc).__name__}: {exc}")
            continue
        card.setdefault("slice", p.stem)
        card["_file"] = p.name
        cards.append(card)
    return cards, bad


def verdict_stats(cards):
    counter = Counter()
    rows = []
    for c in cards:
        for item in c.get("rewrite_partition") or []:
            v = item.get("verdict", "?")
            counter[v] += 1
            rows.append((c["_file"][:2], item.get("module", ""), v,
                         item.get("reason", ""), item.get("risk", "")))
    return counter, rows


def contract_stats(cards):
    counter = Counter()
    gaps = []
    for c in cards:
        for item in c.get("contracts") or []:
            st = item.get("status", "?")
            counter[st] += 1
            if st != "covered":
                gaps.append((c["_file"][:2], item.get("id", ""),
                             item.get("statement", ""), st,
                             ", ".join(item.get("evidence") or []) or "-"))
    return counter, gaps


def collect(cards, key, fields):
    out = []
    for c in cards:
        for item in c.get(key) or []:
            if isinstance(item, dict):
                out.append([c["_file"][:2]] + [str(item.get(f, "")) for f in fields])
            else:
                out.append([c["_file"][:2], str(item)])
    return out


def md_table(headers, rows):
    if not rows:
        return "（无）\n"
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        cells = [str(x).replace("\n", " ").replace("|", "\\|") for x in r]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    cards, bad = load_cards()
    if not cards:
        print("没有找到任何契约卡", file=sys.stderr)
        return 1

    vc, vrows = verdict_stats(cards)
    cc, gaps = contract_stats(cards)
    mods = sum(len(c.get("modules") or []) for c in cards)
    surface = sum(len(c.get("public_surface") or []) for c in cards)

    out = []
    out.append("# why-exist-graph 行为契约审计汇总\n")
    out.append(f"- 契约卡：{len(cards)} 份" + (f"（损坏 {len(bad)} 份）" if bad else ""))
    out.append(f"- 覆盖模块：{mods} 个；公开入口：{surface} 个")
    out.append(f"- 契约条目：{sum(cc.values())} 条 —— " +
               "，".join(f"{k} {v}" for k, v in cc.most_common()))
    out.append(f"- 分区判定：{sum(vc.values())} 项 —— " +
               "，".join(f"{k} {v}" for k, v in vc.most_common()))
    out.append("")

    out.append("## 每片概览\n")
    head = ["#", "切片", "模块", "入口", "契约", "covered", "partial", "gap", "verdict"]
    rows = []
    for c in cards:
        cts = c.get("contracts") or []
        by = Counter(x.get("status", "?") for x in cts)
        vd = Counter(x.get("verdict", "?") for x in (c.get("rewrite_partition") or []))
        rows.append([
            c["_file"][:2],
            c.get("slice", ""),
            len(c.get("modules") or []),
            len(c.get("public_surface") or []),
            len(cts),
            by.get("covered", 0) or "-",
            by.get("partial", 0) or "-",
            by.get("gap", 0) or "-",
            " ".join(f"{k}:{v}" for k, v in sorted(vd.items())) or "-",
        ])
    out.append(md_table(head, rows))

    out.append("## 分区判定（按模块）\n")
    rows = [[r[0], r[1], r[2], r[3], r[4]] for r in vrows]
    rows.sort(key=lambda r: ("keep", "refactor_in_place", "rewrite", "freeze").index(r[2])
              if r[2] in ("keep", "refactor_in_place", "rewrite", "freeze") else 9)
    out.append(md_table(["#", "模块", "判定", "理由", "风险"], rows))

    out.append("## 契约空洞（partial / gap）\n")
    out.append(md_table(["#", "id", "承诺", "状态", "证据"], gaps))

    out.append("## 冗余信号\n")
    out.append(md_table(["#", "条目", "信号", "把握"],
                        collect(cards, "redundancy", ["item", "signal", "confidence"])))

    out.append("## 隐含需求（重写会静默丢掉的行为）\n")
    rows = []
    for c in cards:
        for item in c.get("implicit_requirements") or []:
            rows.append([c["_file"][:2], str(item)])
    out.append(md_table(["#", "行为"], rows))

    out.append("## 待人工判断的问题\n")
    rows = []
    for c in cards:
        for item in c.get("open_questions") or []:
            rows.append([c["_file"][:2], str(item)])
    out.append(md_table(["#", "问题"], rows))

    out.append("## 解析失败\n")
    out.append("\n".join(f"- {b}" for b in bad) + "\n" if bad else "（无）\n")

    (HERE / "SUMMARY.md").write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {HERE / 'SUMMARY.md'}")
    print(f"cards={len(cards)} bad={len(bad)} contracts={sum(cc.values())} verdicts={sum(vc.values())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
