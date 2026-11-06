# why-exist-graph 3.6.0

发布日期：2026-11-06
契约版本：`3.6.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.6.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.6.0/why-exist-graph-3.6.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.6.0.zip`（65 个文件） | 357207 | `88817255f3376d29007975883bab77b754083bcbdbfeaf3331204b9082af7010` |

代码提交：`3d335d2`（manifest 里另有 `source.commit` / `source.dirty=false`；本发布说明是紧随其后的一次 docs 提交，不进包）。

## 本版变更

**门禁不再 fail-open：空输入判 UNKNOWN，需求必须拆成验收条目。**

起因是四仓重构项目的实测结果：`gate` 全程 PASS，同时 `coverage.enforced=false`、`bites=[]`，
而 FR-CV-06/07、FR-XWS-04/05/10 这些画布需求一条测试都没有；图库里登记的 25 个 tree-web
testcase 全部指向同一组 5 个需求，锚点还是 `case-5`、`JSON-2` 这种碎片。统计型覆盖门
（ε/咬合）回答的是"抽样够不够"，没有人回答"这条需求有没有测试"——门禁不是漏了检查，
是空输入默认通过。

- **`acceptance` 节点 + `has_acceptance` 边**：需求拆成可单独判定的验收条目，
  覆盖判定用 `testcase --verifies--> acceptance`；旧式 `testcase --verifies--> requirement`
  只计入 `direct_tests`，不再算验收覆盖。
- **`trace` 命令**：需求→验收→测试矩阵；有缺口退出码 1，无可追溯需求时退出 0。
- **`acceptance-add` / `acceptance-import`**：逐条登记（序号在需求内递增、重复条文拒绝）；
  旧项目用后者从 `requirement.attrs.x_acceptance` 一次性迁移（按序号+条文幂等，`--dry-run` 只读）。
- **gate 的 `traceability` 检查**：有需求无验收 → `UNKNOWN`（退出码 1，不判 PASS）；
  有验收无测试 → `FAIL`；作用域内无 requirement 时按 N/A 跳过。`reconcile` 报 `traceability-gap`。
- **声明即带验收**：`feature-declare` / `feature-register` 的 `--acceptance` 直接拆成
  acceptance 节点（只补不删），新项目不会落在 UNKNOWN 上；UNKNOWN 专留给还没迁移的旧库。
- **契约面**：node kind 17→18、edge kind 20→22、命令 50→53、不变量 21→23；
  SKILL.md 与 `references/contract.md` 的生成块同步。

## 验证

`python tools/preflight.py --release` 十二步全过（417 passed / 6 skipped），另跑
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`（specify-test 阶段
会写一条 testcase 指向验收条目）。

## 升级注意

- 旧状态库**不需要迁移**：新特征只在写入时才产生 acceptance 节点，schema 不变。
- 但旧项目的 gate 结果会变：有 `requirement` 节点、没有验收条目的库将从 `PASS` 变成
  `UNKNOWN`（退出码 1）。迁移办法：在有 `specify-test` 工单时跑
  `wxg acceptance-import --feature <f> --token <t>`，再给每条验收条目补测试。
- `acceptance` 不进 feature 作用域（作用域是咬合/导出的对象集合），因此覆盖统计的 S 不变。

## 已知限制

- `apply` 仍绕过 `target_ids` 写边界；`bite` 仍无 token、无 target 边界。
- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真的测了那条验收"——
  后者要靠审计角色读断言，机制上只能要求测试名/位置可复核。
- CHANGELOG 记录 0.1.0 ~ 3.6.0 共 132 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
