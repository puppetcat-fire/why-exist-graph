# why-exist-graph 3.9.1

发布日期：2026-11-06
契约版本：`3.9.1`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.9.1.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.9.1/why-exist-graph-3.9.1.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.9.1.zip`（65 个文件） | 367887 | `f14d4baaa59567567c1ef1c54a99b7750a5b22e6bb027247bde00187e3f64a64` |

代码提交：`eeef57f`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**修一个真实项目撞出来的误报：`main` 是聚合需求，不该因为自己没有验收条目被判缺口。**

四仓重构项目迁验收条目时暴露：191 条子需求 + 1 条 `requirement:four-repo-rebuild:main`，
`trace` 把 main 报成"1 条需求没有验收条目"，`gate` 因此判缺口——但 main 只是 `feature-declare`
自动建的伞节点，从来不是交付单位。

- **`trace` / `gate` 的口径**：作用域里还有其它需求时，`requirement:{feature}:main` 没有验收
  条目不算缺口，单列为 `aggregate_requirements`；如果它是唯一需求、或自己登记了验收条目，
  仍按普通需求算（伞节点不能变成逃避验收的后门）。
- **契约**：`trace_rules` 9 → 10 条。
- **测试**：432 → 434（伞节点豁免 + 唯一需求不豁免）。

实测（四仓项目，同一库）：`requirements_without_acceptance` 1 → 0，`aggregate_requirements` 1，
`gate` 的理由从"1 条需求没有验收条目"变成精确的"742 条验收条目没有测试指向"。

## 验证

`python tools/preflight.py --release` 十二步全过（428 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 升级注意

- 无 schema 变更。此前因为 main 被算缺口而判 FAIL 的 feature，升级后缺口会消失一条；
  其余判定不变。

## 已知限制

- 豁免只认约定 id（`requirement:{feature}:main`）。如果项目把伞节点换了名字，仍会被算成缺口。
- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真测了那条验收"。
- CHANGELOG 记录 0.1.0 ~ 3.9.1 共 137 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
