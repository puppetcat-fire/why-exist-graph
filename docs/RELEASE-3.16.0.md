# why-exist-graph 3.16.0

发布日期：2026-11-06
契约版本：`3.16.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.16.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.16.0/why-exist-graph-3.16.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.16.0.zip`（65 个文件） | 382003 | `62fd57f78f673131d78886d8075e98c488935f845ec4411f83c5d7654178da6c` |

代码提交：`117c5f0`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**标注有专用命令了：`acceptance-status`。** 3.15.0 给验收条目加了 `x_status`，但唯一写法是
`upsert-node` 整体回写 attrs——得先把原 attrs 读回来再拼，漏一个键就丢 `text` / `ordinal`。
在四仓标 6 条时就是这么手搓的，等于给自己造重复实现。

- **`wxg acceptance-status --acceptance <id> [--status <说明>] --token …`**：只改 `x_status`
  一个键，其它 attrs 原样保留；省略 `--status` 即清除标注。非 acceptance 节点、缺 token 都拒绝。
- **契约**：命令 54 → 55、`TOKEN_COMMANDS` 与 `I5` 清单加 `acceptance-status`、
  `trace_rules` 15 → 16 条（写明唯一写入口：新增用 `acceptance-add`，标注用 `acceptance-status`）。
- **测试**：443 → 445（写/清除且其它键不丢；非 acceptance 与缺 token 拒绝）。

## 验证

`python tools/preflight.py --release` 十二步全过（439 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 同轮的四仓项目进展

- 新写 `CatalogAcceptanceTest`，覆盖 FR-CAT-09 验收 3（未知编码→未识别，不返回替代条目）；
  该组另外 4 条早已标 `x_status` 说明未实现/部分实现。
- gen37 登记 testcase 节点 + `verifies` 边，走完工单生命周期；tested **37 → 38**，缺口 **725 → 724**。

## 升级注意

- 无 schema 变更。
- 以前用 `upsert-node` 整体回写 attrs 来改 `x_status` 的脚本，建议换成 `acceptance-status`，
  否则漏键会静默丢字段。

## 已知限制

- `x_status` 仍是自由文本，不做枚举校验。
- `acceptance-status` 只认已存在的 acceptance 节点，不能顺带新建。
- CHANGELOG 记录 0.1.0 ~ 3.16.0 共 144 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
