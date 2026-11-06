# why-exist-graph 3.17.0

发布日期：2026-11-06
契约版本：`3.17.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.17.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.17.0/why-exist-graph-3.17.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.17.0.zip`（65 个文件） | 385354 | `80176ce8ca64cc98d1e91db8fd4977905fcf72fe108def217ea126a06d364d88` |

代码提交：`50745e0`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**范围外需求有正式表达了：`requirement-scope`。** 审计四仓后摆出一个绕不开的问题：47 条需求
是 0.1.0 的旧口径，0.2.0 重建根本不打算做。此前它们和"没做完"躺在同一个缺口列表里，
门禁分不出"决定不做"和"还没做"。

- **`wxg requirement-scope --requirement <id> --scope out --reason "…"`**（`--scope in` 恢复；
  范围外必须写理由，否则拒绝）。
- **`trace`**：范围外需求的验收条目从缺口里移出，但仍在 `descoped` 里逐条列出（id/名称/理由/验收数），
  摘要里单列 `descoped_requirements` / `descoped_acceptance`；`--md` 有「范围外需求」小节。
- **`gate`**：范围外需求不计缺口；PASS 时附 `descoped` 与 `note`，FAIL 时理由里也带
  "另有 N 条需求声明为范围外"。
- **契约**：命令 55 → 56、`TOKEN_COMMANDS` / `I5` 加入 `requirement-scope`、`trace_rules` 16 → 17 条。
- **测试**：445 → 447（范围外需求不算缺口但可见 + gate PASS 写明；命令 set/clear 与缺理由拒绝）。

## 为什么这不是放水

3.15.0 明确拒绝做"标注即豁免"（`x_status` 不能当免死金牌）。这里的区别是：
**范围外是产品决定，有责任人、有理由、有清单，而且仍然可见**。被标范围外的需求不会从报告里
消失，只是不再计入"欠账"；命令强制写理由，`gate` 每次都报数目——想藏就得改 gate 本身，
那就不是偷偷摸摸了。

## 验证

`python tools/preflight.py --release` 十二步全过（441 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 升级注意

- 无 schema 变更。`x_scope` / `x_scope_reason` 是 attrs 扩展键。
- 旧库若已有手工写 `x_scope` 的需求，会被 `trace` 直接认作范围外——请确认那些标记是决定，不是草稿。
- `requirement-scope` 只接受已存在的 requirement 节点，不能新建。

## 已知限制

- 范围外需求仍有验收条目，但 `trace` 不再为它们统计 `acceptance_missing`；要查"范围外需求有没有
  意外做了一部分"，看 `--requirement <id>` 钻取（`items` 里 `tested` 仍会显示）。
- 不做范围外的历史审计（谁在什么时候标的），只留 `x_scope_reason` 与证据链。
- CHANGELOG 记录 0.1.0 ~ 3.17.0 共 145 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
