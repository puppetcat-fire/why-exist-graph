# why-exist-graph 3.8.0

发布日期：2026-11-06
契约版本：`3.8.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.8.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.8.0/why-exist-graph-3.8.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.8.0.zip`（65 个文件） | 364775 | `6610c36cab372dec9d13428f0111c59322420a65a6101ef3c4f70f9ec004d6cb` |

代码提交：`d82b4d6`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**验收条目进工作流：任务书带验收，状态带缺口。** 3.6 / 3.7 把验收条目做成可判定的节点并接上了
门禁（`trace`、`traceability` 检查），但干活的人和看全局的人还得自己跑 `trace` 才知道验收长什么样。

- **`brief` 新增 `acceptance_items`**：边界内需求的验收条目，字段 `id` / `requirement` /
  `ordinal` / `text`。执行者拿到任务书就知道这条切片要做到哪几条验收。
  `brief_version` 不动——字段是追加的，`blind-check` 仍只读 `write_boundary` / `inputs` / `produces`。
- **`feature-status` 新增 `traceability` 摘要**：验收条目数、已测数、缺口数、`complete` / `unknown`，
  与 `trace` 和 `gate` 的 `traceability` 检查同一口径。
- **契约**：`trace_rules` 7 → 8 条（brief / status 的验收口径）。
- **测试**：429 → 431（briefing 两条纯函数、`brief` 端到端一条、`feature-status` 一条）。

## 验证

`python tools/preflight.py --release` 十二步全过（425 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 升级注意

- 无 schema 变更，旧状态库直接可用。
- `brief` 输出多了 `acceptance_items` 字段：如果你的下游脚本对任务书字段做**严格相等**比较，
  需要放行这个字段；做子集检查的不受影响。

## 已知限制

- `brief` 只带**边界内**需求的验收条目；工件跨越多个需求时，其余需求的验收要自己 `trace`。
- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真测了那条验收"。
- CHANGELOG 记录 0.1.0 ~ 3.8.0 共 135 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
