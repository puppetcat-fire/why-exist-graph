# why-exist-graph 3.14.0

发布日期：2026-11-06
契约版本：`3.14.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.14.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.14.0/why-exist-graph-3.14.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.14.0.zip`（65 个文件） | 378338 | `c708652f8e6bfa94da37ae30c1ccc7b76d74f289bd338448a9b5234b6fd9e8cf` |

代码提交：`f22273f`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**批量写入有官方入口了：`bulk`。** 在四仓项目里登记 10 条验收测试要写 10 个节点 + 10 条边，
之前只能逐条 `upsert-node`/`upsert-edge`，于是项目侧自己写了 `batch_write2.py` 去循环调用内部
API——这正是"同一职责两份实现"的味道。

- **`wxg bulk --token … --nodes a.jsonl --edges b.jsonl [--dry-run]`**：JSONL 批量写节点与边。
  先全量校验（kind / id 形态 / attrs / 边 kind / 端点存在 / 批次内重复 id），任一条不合法整批不落库；
  校验通过后在一个事务里写，并记一条 evidence。
- **边界与 `upsert-node` / `upsert-edge` 相同**：token + 工单 `target_ids`；角色只给
  `model-architecture` / `model-structure` / `interact` / `specify-test`（能同时写节点和边的角色）。
- **契约**：命令 53 → 54、`TOKEN_COMMANDS` 加 `bulk`、`I5` 写入边界清单加 `bulk`。
- **测试**：439 → 443（成对写入、整批原子 + 边界拒绝、重复 id/悬空端点、角色与 token）。

## 验证

`python tools/preflight.py --release` 十二步全过（436 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 升级注意

- 无 schema 变更。
- 项目侧那类 `batch_write2.py`（循环调用 `whyexist.*` 内部 API）现在可以用 `wxg bulk` 替掉；
  内部 API 不是稳定接口，替换后少一处随版本漂移的脚本。

## 已知限制

- `bulk` 只做图写入，不触发工单流转（写完仍要 `work-finish` / `work-judge`）。
- 整批写入的 evidence 记在工单上而不是逐条记——要逐条溯源得看 `upsert-node` 的调用日志。
- CHANGELOG 记录 0.1.0 ~ 3.14.0 共 142 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
