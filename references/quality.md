# 提交质量门（why-exist-graph）

本文件是技能自身的提交检查表。`wxg verify` 在运行时会检查本文件存在；其余项目在提交前
必须逐项给出证据（命令、退出码、产物 hash），不能只写“已检查”。

## 1. 可复现

- [ ] `python -m unittest discover -s tests -v` 全绿，记录用例数（当前 357 个；MySQL/PostgreSQL 后端集成用例需要对应 URL 环境变量，默认跳过）。
- [ ] `python tools/preflight.py` 全绿：回归测试 + 文档一致性 + `verify` + `doctor` 一条命令跑完
      （发布时加 `--release` 一并打包）。
- [ ] `python scripts/wxg.py verify` 返回 `ok: true`，记录 `version`；verify 不创建状态库。
- [ ] 同一份状态库连续跑两次 `gate` / `doctor` / `export`：只读命令不改变 DB hash；
      写命令在文档里标了 `--apply` 或 `--fix`。`gate` PASS=退出码 0、FAIL=1。
- [ ] 一键重跑脚本默认不追加 bite、不重写权威证据；必须显式 `--apply` 才写状态。
- [ ] 每条交付证据都由 `evidence-record` 登记（命令、退出码、actor、产物 SHA-256）；
      BehaviorPassed 裁决前必须已有**同 generation**、exit_code=0 的 evidence。
- [ ] feature 开启 `--coverage-epsilon` 时，`work-judge(passed)` 与 `gate` 的覆盖检查跑过，
      记录 `coverage` 输出（各阶段 covered/n_required/met）。
- [ ] 新 feature 默认开启 coverage（ε=1.0），`--no-coverage` 与显式 `--coverage-epsilon` 互斥；
      重声明保留已有策略。迁移后的旧 feature 不应被默认收紧。

## 2. 可追溯

- [ ] 每次 `work-claim` 带 `--actor`；每次 `work-judge` 带 `--actor`，且不等于被审工单的
      `claimed_by`。
- [ ] `work-judge` 写 `judged_by` / `judged_at`；同一工单不被后续裁决覆盖。
- [ ] 审计日志包含执行者、复跑命令、输入摘要或产物 hash；只复述结论的日志只能算过程证据。
- [ ] 旧库迁移把未知身份标 `legacy`，不伪造具体成员；`doctor` 必须报 `legacy-identity`。
- [ ] 咬合只通过 `bite` 落库；`attrs.bite` 不接受图写入伪造；gate 按节点最新判决计，
      KEEP 只反证同一节点。
- [ ] 每次 `work-judge` 都在 `judge_history` 留档；`judge(passed)` 清空 stale `fail_reason`。

## 3. 契约一致

- [ ] 条件、工单、角色、命令、属性键、导出形状（含 07 附加表与命令“写入”列）只在 `scripts/wxg_contract.py` 定义。
- [ ] `SKILL.md` 与 `references/contract.md` 的契约块由 `contract --write` 生成，`verify` 无漂移。
- [ ] `references/export-sample` 与 `gen_sample.py` 输出逐字节相同。
- [ ] 新增命令有 handler、有契约条目、有 `WRITE_MODES` 写入列、有测试；新增 actor/证据规则有 `doctor` 检查。
- [ ] pattern 必填字段（`applicability`/`not_applicable`/`applies` 挂载）有 gate 与 doctor 双重检查；
      04 架构导出包含作用域内 pattern 行。
- [ ] coverage 的默认参数、公式与强制点（judge/gate）写在契约里，且只读命令 `coverage` 不写库。
- [ ] drift 策略（`--drift-limit`）只统计当前代最新判决为 UNMAPPED/DOC-ONLY 的节点；未开启只报告。
- [ ] `applies` 边写入校验（src 设计元素 / dst pattern）与 `doctor` 的 `applies-invalid` 检查都有反例测试。
- [ ] `reconcile` 默认只读且幂等；`--apply` 只做补单/解阻塞/回收陈旧 claim，不裁决、不咬合、不写图；退出码 0/1 有测试。
- [ ] 施工标记（`construction`）gate 会拦；清标记路径（upsert-node 覆盖）与类型校验有测试。
- [ ] `change-open` 只在 Ready 后可用；继承边界与 `changes` 记录一致，`doctor` 有 `change-*` 反例；`change-diff` 只读且不写库。
- [ ] `import-file` 重扫会把消失的旧节点标 stale、再出现清 0；`--prepare` 把旧节点并入 target_ids；gate 会拦 stale 节点。
- [ ] `sync --repo` 只读、不写库，能报 missing/new/changed/stale；解析失败进 parse_errors 而不是崩溃。
- [ ] 设 `WXG_DB_URL`/`--db-url` 时能走 MySQL 后端：`init` 建表、import/claim/judge/gate/doctor 全流程、并发 claim 只有一个成功。
- [ ] 设 `postgresql://` URL 且装了 psycopg 时能走 PG 后端：同样的全流程与并发 claim；没装 psycopg 时报可读错误而不是 traceback。
- [ ] `conformance` 只读、只报差异（锚点/结构支撑/未声明耦合/测试覆盖），不写库、不生成节点；`--conformance` 开启后 gate 对 violations FAIL，关闭时只报告。
- [ ] `serve --once` 只读不写库；`--apply` 只做补单/解阻塞/回收陈旧 claim，输出一行 JSON 摘要。
- [ ] 改过 CLI 表面（新增/改名命令、改必填参数、改 `up` 的 `next` 建议）之后跑
      `python tools/doc_flow.py`：它只按 `SKILL.md` 最短路径执行命令序列，任何一步失败都
      说明文档与实现脱节——单元测试不读文档，端到端测试直接用正确顺序，两边都抓不到。

## 4. 通用与安全

- [ ] 技能内没有写死的仓名、绝对路径；导入器仅 Python AST，`repo-add --language` 只接受 `python`。
- [ ] 图内容写入必须经过 `claim_token` + `target_ids`；`gate`/`slice`/`get`/`find` 只读。
- [ ] JSON 参数（acceptance/constraints/data/spec/target-ids/node-ids/ids）支持 `@文件`；Windows PowerShell 5.1 下用 `@file` 可避开内联引号改写。
- [ ] 常见失败路径返回非零退出码与可读 `error`（`@` 文件缺失、仓登记冲突等已覆盖）；未捕获异常仍以非零退出，不把失败当成功。

## 5. 变更记录

- [ ] `CHANGELOG.md` 写明契约版本、schema 版本、迁移方式、破坏性变更与未覆盖边界。
- [ ] schema 变更提供 `init` 迁移；迁移不删除旧行，未知字段标 `legacy`。
- [ ] 测试数量与覆盖范围写进 `CHANGELOG`，不把“测试全绿”当成“质量足够”。

## 当前版本状态

- 契约 `2.42.0` / schema `9`；版本历史与每次变更的行为差异见 `CHANGELOG.md`。
- 覆盖：357 个回归用例（6 个后端集成用例按环境变量跳过），包括纯函数层单测
  （`tests/test_package_units.py`）、CLI 端到端、以及 `verify` 对文档块与导出样例的逐字节校验。
- 已知边界：**只在 `SKILL.md`「已知边界」维护一处**，本节不再复述——两处清单必然漂移，
  2.36.0 就是因为这里的重复副本过时才发现。
