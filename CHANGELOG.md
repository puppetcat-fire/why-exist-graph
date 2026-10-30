# Changelog — why-exist-graph

## 0.4.1（2026-10-30）

**仅测试修复，无功能与 schema 行为变更。** Windows 上 `tempfile` 的根可能返回 8.3 短路径
（如 `C:\Users\RUNNER~1\AppData\Local\Temp`），`test_role_prompt_uses_real_root` 用短路径字符串
与 `role-prompt` 解析出的长路径比较，在 GitHub Actions 的 windows runner 上必失败（ubuntu 不复现）。
测试夹具改为 `Path(...).resolve()` 后再断言，其余用例不变。

- 契约版本 `0.4.0` → `0.4.1`（版本号随发布推进；schema 仍为 `3`，命令与行为无变化）。
- CI 六格（ubuntu-latest / windows-latest × Python 3.10/3.12/3.13）全绿；`verify` 与 42 个用例标准不变。
- 发布资产与 0.4.0 的内容差异仅限测试文件与版本号。

## 0.4.0（2026-10-29）

**首个对外发布版本（initial release）**。来自对 0.3.0 的"文档描述 vs 实现"一致性审计
（本技能自我审计 + E2E 复现）。本版修掉削弱交付门可信度的路径，并把文档里绝对化但未被
强制的规则变成代码约束：

- **门禁条件不可被旁路**：移除 `feature-register --true`。同代登记不写条件；新建 feature 或
  显式 `--generation` 开新代时只写 Accepted（新代会重置条件并 supersede 旧代工单、清 token），
  并回写 requirement 节点正文。`work-claim` 只发**当前 generation** 的 ready 工单。
  `feature-declare` 仍只置 Accepted 并在新建时自动 seed。
- **BehaviorPassed 需要同代证据**：`evidence` 新增 `generation` 列（schema 3）；`work-judge(passed)`
  要求 feature **同 generation** 且 `exit_code=0` 的 evidence；`gate` 执行同一检查；`doctor`
  新增 `behavior-passed-without-evidence`。重新声明后旧代证据不再满足新代 BehaviorPassed。
- **封死 attrs.bite 伪造**：`upsert-node` / 图写入拒绝 `attrs.bite`；该键只由 `bite` 命令写；
  `gate` 只采信 `bites` 表（含 actor），不再用节点 attr 兜底。
- **scan 等无对应条件的工单** judge(failed) 不再清空全部条件（尤其不再清 Accepted）。
- **init 幂等**：旧库迁移只在补列时执行一次，且跳过 audit 工单；已迁移库重复 `init`
  零写入（修复 0.3.0 把 fresh audit 工单 `claimed_by` 改成 `legacy` 的问题）。
- **doctor 可追溯**：新增 `legacy-identity` 检查，落实契约里"doctor 提示 legacy 不可追溯"。
- **DSH Windows 沙箱可用**：新增 `make_temp_dir()`，Windows 用默认 mode 建临时目录，
  规避 `tempfile` 的 0o700 目录 DACL 为空的问题（DSH discussion #4290）；
  `verify`/`gen_sample`/测试在 DSH 沙箱内可直接运行。
- **契约形状收口**：命令表"写入"列改为 `WRITE_MODES` 显式声明（`verify` 检查覆盖）；
  `07-数据流.md` 的"请求参数"表进入 `EXPORT_FILES.extra_sections`；导出文件名从契约读取。
- **可用性**：quick start 补 `work-open` 扩 target_ids 步骤与证据前置说明；`role-prompt`
  输出真实状态库/CLI 路径，audit 提示改为直接 work-judge；`repo-add --language` 只接受
  `python` 并说明导入器边界；`@文件` 支持扩展到 `--target-ids`/`--node-ids`/`--ids`；
  `@文件`缺失与 repo 登记冲突返回可读 error 而非 traceback；`gate` FAIL 退出码改为 1。
- **文档纠偏**：I3/I5/I7、GATE_RULES、AUDIT_RULES、quality.md 的绝对化措辞改为准确表述；
  `verify` 的覆盖范围写清楚（生成视图/样例，不替代 doctor 与行为测试）；`sample` 覆盖
  仓内所有节点；Python 导入器对未知裸名调用按 I7 建 unmapped 节点/边。
- **测试**：19 → 42（新增 0.4.0 回归 23 个，含迁移回填、缺库保护、链式调用 unmapped、导出 `|` 转义、declare 保真、证据产物校验）。
- **schema**：`2` → `3`（`evidence.generation` 列；迁移优先按证据关联工单的 generation 回填，
  关联工单不存在（悬空引用）时同样回退到 feature 当前代回填，不删行）。注意：0.3 的旧 evidence
  没有 generation 信息，无法还原真实代；若升级前存在跨代证据，升级后请在新代重新登记 evidence。
- 版本：契约 `0.3.0` → `0.4.0`。
- **破坏性变更**：`feature-register --true` 移除；`gate` FAIL 退出码 1；BehaviorPassed
  裁决需先登记**同代** evidence；旧脚本里用 `--true` 置条件的做法不再可用。

## 0.3.0（2026-10-29）

来自 student-course-system 实战审计：gate/证据可以复现，但审计身份与证据溯源不可验证，
finalize 重跑会追加咬合并改写权威证据。本版把这些变成契约约束：

- **actor 可追溯**：`work-claim` / `work-judge` / `bite` 必须带 `--actor`（或 `WXG_ACTOR`）；
  写 `work_items.claimed_by`、`work_items.judged_by`、`work_items.judged_at`、`bites.actor`。
- **审计独立**：`work-judge` 的 actor 不能等于被审工单的 `claimed_by`；旧库迁移把未知身份
  标成 `legacy` 而不是伪造成员，并在返回里带 `legacy_claim`。
- **证据一等化**：新增 `evidence-record` / `evidence-list`，登记 feature、work、命令、退出码、
  actor、产物路径与 SHA-256；`doctor` 检查证据产物缺失/被篡改、非零退出码、关联工单缺失。
- **导出参数去重**：05/07 的参数、测试、断言按 id 去重，07 同一参数只列一次。
- **schema 迁移**：schema 1 → 2，`init` 非破坏地补 `claimed_by`/`judged_by`/`judged_at`
  与 `evidence` 表；旧 `passed/failed` 行标 `legacy`，不删除业务行。
- **兼容性**：调用 `work-claim` / `work-judge` / `bite` 的旧脚本必须补 `--actor`，或设置
  `WXG_ACTOR` 环境变量；否则退出码 2。旧库先跑一次 `init` 再使用 0.3.0。
- 契约版本 0.2.0 → 0.3.0；测试 14 → 19，新增 actor 独立性、证据登记/篡改检测、
  导出参数去重、0.2→0.3 迁移、contract --json 可序列化用例。
- 新增 `references/quality.md` 提交质量门；`verify` 检查该文件存在。

## 0.2.0（2026-10-29）

针对 calculator-demo 实测暴露的问题：

- **重导入不再覆盖设计标注**：`import-file` 写节点时使用 attrs 合并（`merge_attrs=True`），
  observe/scan 重扫只刷新扫描自有属性，保留 `duty`、`x_note`、`x_*` 等设计角色写入的标注。
- **悬空引用清理**：`retract` 级联删除对应 `bites`，并从工单 `target_ids` / `evidence_ids`
  里剔除已删节点；`scope_ids` 只收现存节点，`slice` 会展开 `前缀*` 通配并只报告真正缺失的 id。
- **gate 不再把已删节点的咬合当证据**：忽略这类 bite，并在输出里给 `ignored_dangling_bites`。
- **token 生命周期**：`work-finish` 与 `work-judge(passed)` 清空 `claim_token`。
- **新增 `doctor`**：检查悬空 bite/边/引用、陈旧 token、条件完整性与审计配对；
  `doctor --fix` 只清理悬空引用和陈旧 token，不替人裁决；输出 `by_check`/`truncated`
  避免长列表被截断，并同步 `meta.contract_version`。退出码：干净 0，有问题 1。
- 契约版本 0.2.0；schema 版本仍为 1（无表结构变更）。
- 测试从 9 个增加到 14 个，新增覆盖 attrs 合并、retract 清理、gate 悬空咬合、slice 通配、token 清理。

## 0.1.0（2026-10-28）

首个 DSH 原生版本：单技能 + SQLite 图库 + 8 条件工单状态机 + 导出视图 + `verify` 契约自检。
