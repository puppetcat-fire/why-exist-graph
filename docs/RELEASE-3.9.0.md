# why-exist-graph 3.9.0

发布日期：2026-11-06
契约版本：`3.9.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.9.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.9.0/why-exist-graph-3.9.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.9.0.zip`（65 个文件） | 366333 | `55721b8e4875122adefd65a9274c3cb3ef254dbc12a3ccc6bb2c223cc3877dcf` |

代码提交：`a300919`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**验收边的结构约束挪到写入期。** 3.6.0 加 `acceptance` 时，结构正确性全靠 `doctor` 事后报告
（孤儿验收、多父挂载、非 testcase 指向验收），而 `upsert-edge` 当时什么都放行——等于允许
"先写坏、再体检"，正好是这个技能存在理由的反面。

- **`upsert-edge` 写入期强制**：`has_acceptance` 的 src 必须是 `requirement`、dst 必须是
  `acceptance`，且一条验收只能属于一条需求（同一父重复写仍幂等）；`verifies` 指向 `acceptance`
  时 src 必须是 `testcase`。
- **`doctor` 的角色不变**：`acceptance-orphan` / `acceptance-multi-parent` 保留，只兜旧库遗留的
  坏数据，不替代写入期校验。
- **契约**：`trace_rules` 8 → 9 条。
- **测试**：431 → 432（新增写入期守卫的正反例；doctor 的多父用例改成直接造坏行，模拟旧库）。

## 验证

`python tools/preflight.py --release` 十二步全过（426 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 升级注意

- 无 schema 变更，旧状态库直接可用；旧库里的坏结构不迁移，doctor 照旧报告。
- 如果你的脚本用 `upsert-edge` 手工写过 `has_acceptance` / `verifies→acceptance`，现在会被
  两端 kind 与"一条验收一个父"的规则拒绝；正常路径（`acceptance-add` / `acceptance-import` /
  `feature-declare`）不受影响。

## 已知限制

- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真测了那条验收"。
- 验收条目的 `ordinal` 唯一性仍只有 doctor 检查（`acceptance-add` 自己会递增，`upsert-node`
  直写绕不过 doctor 但不拦）。
- CHANGELOG 记录 0.1.0 ~ 3.9.0 共 136 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
