# 提交质量门（why-exist-graph）

本文件是技能自身的提交检查表。`wxg verify` 在运行时会检查本文件存在；其余项目在提交前
必须逐项给出证据（命令、退出码、产物 hash），不能只写“已检查”。

## 1. 可复现

- [ ] `python -m unittest discover -s tests -v` 全绿，记录用例数（0.4.0：42 个）。
- [ ] `python scripts/wxg.py verify` 返回 `ok: true`，记录 `version`；verify 不创建状态库。
- [ ] 同一份状态库连续跑两次 `gate` / `doctor` / `export`：只读命令不改变 DB hash；
      写命令在文档里标了 `--apply` 或 `--fix`。`gate` PASS=退出码 0、FAIL=1。
- [ ] 一键重跑脚本默认不追加 bite、不重写权威证据；必须显式 `--apply` 才写状态。
- [ ] 每条交付证据都由 `evidence-record` 登记（命令、退出码、actor、产物 SHA-256）；
      BehaviorPassed 裁决前必须已有**同 generation**、exit_code=0 的 evidence。

## 2. 可追溯

- [ ] 每次 `work-claim` 带 `--actor`；每次 `work-judge` 带 `--actor`，且不等于被审工单的
      `claimed_by`。
- [ ] `work-judge` 写 `judged_by` / `judged_at`；同一工单不被后续裁决覆盖。
- [ ] 审计日志包含执行者、复跑命令、输入摘要或产物 hash；只复述结论的日志只能算过程证据。
- [ ] 旧库迁移把未知身份标 `legacy`，不伪造具体成员；`doctor` 必须报 `legacy-identity`。
- [ ] 咬合只通过 `bite` 落库；`attrs.bite` 不接受图写入伪造。

## 3. 契约一致

- [ ] 条件、工单、角色、命令、属性键、导出形状（含 07 附加表与命令“写入”列）只在 `scripts/wxg_contract.py` 定义。
- [ ] `SKILL.md` 与 `references/contract.md` 的契约块由 `contract --write` 生成，`verify` 无漂移。
- [ ] `references/export-sample` 与 `gen_sample.py` 输出逐字节相同。
- [ ] 新增命令有 handler、有契约条目、有 `WRITE_MODES` 写入列、有测试；新增 actor/证据规则有 `doctor` 检查。

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

- 契约 `0.4.0` / schema `3`（evidence.generation）。
- 覆盖：0.3.0 的 19 个用例 + 0.4.0 回归 23 个（门禁条件写入口、BehaviorPassed 同代证据+产物校验、
  attrs.bite 伪造、init 幂等、legacy-identity、当前代领取、scan failed 不清条件、
  register 语义/requirement 回写/入参校验、verify 无副作用、@file、role-prompt、失败路径、
  跨代证据、空 payload 可读错误、迁移回填、缺库保护、链式调用 unmapped、导出转义、declare 保真），共 42 个。
- 已知边界：`implement-test` 没有文件级写边界记录；assertion→testcase 覆盖不检查；
  外部测试执行不在 wxg 内，仍需调用方用 `evidence-record` 落证据；evidence 真伪仍靠执行者自律。
