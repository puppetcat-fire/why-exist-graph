# 02 契约表：50 条命令声明

审计对象：`scripts/wxg_contract.py` 的 `P/O/F/C` 构造器（L269-296）与 `COMMANDS`（L299-637），加上同一切片的写入列 `WRITE_MODES`（L639-691）、token 相关常量（`TOKEN_COMMANDS` L262、`PRODUCT_CODE_ROLES` L265）、命令分派层 `scripts/whyexist/cli.py`、契约执行器 `cmd_verify`（`scripts/whyexist/commands_misc.py:269-352`）。

不含：条件状态机、bite/gate 判定、数据库 schema 迁移、导出内容生成（分别属其它切片）；本切片只在需要解释命令行为时引用它们。

## 切片范围与事实

| 项 | 值 |
|---|---|
| 契约文件 | `scripts/wxg_contract.py`，1058 行（任务简述写 962 行，已过期） |
| 本切片 | L269-637（构造器 + 50 条命令）共 369 行；L639-691（写入列）53 行 |
| 命令数 | 50；positionals 总数 0；options 条数 123；flags 条数 19；token=True 的命令 9 条 |
| handler | 50 个 `cmd_*`，与 50 条注册一一对应（静态复核 + `tests/test_wxg.py:514-515`） |
| 消费方 | `whyexist/cli.py`（生成 argparse）、`cmd_verify`、`contract --json`、两份文档的生成块、`tools/build_release.py`、测试 |
| 契约版本 | `CONTRACT_VERSION = "2.92.0"`、`SCHEMA_VERSION = 9`（`scripts/wxg_contract.py:17-18`） |

`COMMANDS` 的键序不是字母序，是功能分组序；`WRITE_MODES` 的键序与它一致。`verify` 会逐字节比较由同一份 `COMMANDS` 渲染出的 SKILL.md / references/contract.md 契约块（`scripts/whyexist/commands_misc.py:274-285`），因此这里的任何字符串改动都会波及文档与 `references/export-sample`。

实测跑过的检查：

- `python scripts/wxg.py verify` → `ok: true`，checks = contract-blocks / commands / roles / kinds / write-modes / export-sample。
- `python -m unittest` 子集：`test_contract_json_is_serializable`、`test_contract_commands_cover_roles_and_attrs`、`test_role_and_token_boundaries`、`test_missing_db_commands_do_not_create`、`test_verify_is_side_effect_free`；以及 `test_patch_and_apply_merge_disjoint_outputs`、`test_up_bootstraps_workspace_and_is_idempotent`、`test_import_repo_scans_all_python_files`、`test_promote_marks_derived_component_declared`、`test_apply_dry_run_writes_nothing` — 全部 OK。
- 临时库探针：`import-file --prepare` 后 `work_items` 多出 scan 单、`feature_nodes` 多出节点行（证明 help 的“不写库”不成立）；`find --from-id component:d:a` 在 `a depends b` 时返回 `b`（证明方向描述反了）。

## 公开面

### CLI：50 条命令逐条登记

`注册行` 为 `scripts/wxg_contract.py` 中的行号；`token` 列 = `C(..., token=True)`；`写入` = `WRITE_MODES` 原文。所有命令都没有 positionals，输入全部走 `--flag`；全局 `--root` / `--db-url` 必须放在子命令前（`scripts/whyexist/cli.py:22-27`）。

| # | 命令 | 注册行 | help（原文） | 参数（* 必填） | flags | token | 写入 |
|---|---|---|---|---|---|---|---|
| 1 | init | 300 | 初始化状态库并做一次性旧库迁移；迁移后重复运行不改已有行 | — | — | 否 | 状态库（首次迁移） |
| 2 | up | 301 | 一条命令立起工作区：init + demo 仓 + demo feature + 第一次 gate 结果（不自动裁决，幂等） | --feature、--repo、--path、--template | — | 否 | 状态库 / 文件（demo 仓） |
| 3 | repo-add | 315 | 登记源码仓；技能里不写死任何仓名 | --id*、--path*、--language | — | 否 | 状态库 |
| 4 | repo-list | 323 | 列出已登记仓 | — | — | 否 | 只读 |
| 5 | import-file | 324 | 按单个 Python 源码文件导入节点/边；--prepare 只预列 id 到 scan 工单（此时必须带 --feature） | --file*、--feature、--token | --prepare | 是 | 写图需 claim_token；--prepare 免 token |
| 6 | import-repo | 334 | 按仓批量导入全部 Python 文件；--prepare 只预列到 scan 工单 | --repo*、--feature、--token | --prepare | 是 | 写图需 claim_token；--prepare 免 token |
| 7 | derive | 344 | 从代码图推导 component/depends 候选（默认 dry-run；--apply 写入 origin=derived） | --repo*、--feature*、--depth、--exclude、--token | --apply | 是 | 只读（--apply 时写图，需 claim_token） |
| 8 | promote | 360 | 把 origin=derived 的候选节点提升为 declared，并记录裁决者（需 claim_token） | --feature*、--node*、--actor、--token | — | 是 | 需要 claim_token / 角色命令 |
| 9 | sample | 370 | 从仓或 feature 作用域里随机取一个节点，作为撕咬入口 | --repo、--feature、--seed | — | 否 | 只读 |
| 10 | feature-declare | 378 | 声明功能：generation+1，重置条件，只派 work-seed | --id*、--name*、--statement*、--acceptance*、--constraints*、--coverage-epsilon、--drift-limit | --no-coverage、--conformance、--no-conformance | 否 | 状态库 |
| 11 | feature-register | 395 | 登记已有图：同代登记不写条件；新建/新代只置 Accepted（--generation 会重置条件并 supersede 旧工单） | --id*、--name*、--spec*、--generation | — | 否 | 状态库 |
| 12 | feature-list | 404 | 列出 feature 与当前 generation | — | — | 否 | 只读 |
| 13 | feature-status | 405 | 显示当前 generation 的条件、工单、咬合汇总 | --id* | — | 否 | 只读 |
| 14 | change-open | 406 | 在 feature Ready 后开变更集：继承 from-condition 之前的条件，从它起重置并开启新一代，自动 seed 下游工单 | --feature*、--id、--statement*、--from-condition* | — | 否 | 状态库 |
| 15 | change-diff | 415 | 只读对比：当前代与上一代工单写过的节点集合、继承/待办条件、代码锚点 | --feature*、--from-generation | — | 否 | 只读 |
| 16 | work-open | 422 | 预开/扩展非 audit 工单的 target_ids（scan 与设计角色扩写入边界都用它） | --feature*、--kind*、--target-ids* | — | 否 | 状态库 |
| 17 | work-seed | 430 | 按缺的条件各生成一张工单 | --feature* | — | 否 | 状态库 |
| 18 | work-claim | 431 | 按角色领取当前代一张 ready 工单，返回 claim_token 与切片（--brief 只给计数） | --role*、--actor | --allow-product-code、--brief | 否 | 状态库 |
| 19 | work-finish | 442 | 提交已领取工单；通过后生成 audit 工单 | --token* | — | 是 | 需要 claim_token / 角色命令 |
| 20 | work-judge | 443 | 审计裁决一张 submitted 工单（仅 audit 角色）；BehaviorPassed 需要先登记 evidence | --id*、--verdict*、--fail-reason、--role、--actor | — | 否 | 状态库 |
| 21 | work-list | 453 | 列出某 feature 当前 generation 的工单 | --feature* | — | 否 | 只读 |
| 22 | upsert-node | 454 | 写节点；id 已存在则更新（不接受 attrs.bite） | --token*、--data* | — | 是 | 需要 claim_token / 角色命令 |
| 23 | upsert-edge | 455 | 写边；两端必须已存在 | --token*、--data* | — | 是 | 需要 claim_token / 角色命令 |
| 24 | bind | 456 | 绑定 parameter/argument/assertion 到已存在节点 | --token*、--node-id*、--bind-to*、--edge-kind | — | 是 | 需要 claim_token / 角色命令 |
| 25 | retract | 466 | 撤回 target_ids 内的节点与边；级联删除 bite 并剔除工单引用 | --token*、--node-ids、--edge-ids | — | 是 | 需要 claim_token / 角色命令 |
| 26 | bite | 471 | 记录一次必要性判定；判决集固定，写 bites 与节点 attrs.bite（唯一写入口） | --node*、--verdict*、--reason、--feature、--actor | — | 否 | 状态库 |
| 27 | evidence-record | 481 | 记录一条可追溯证据：命令、退出码、执行者、产物 hash（BehaviorPassed 的门槛） | --feature*、--name*、--command*、--exit-code、--artifact、--work、--actor | — | 否 | 状态库 |
| 28 | evidence-list | 493 | 列出某 feature 的证据记录 | --feature* | — | 否 | 只读 |
| 29 | coverage | 494 | 按咬合覆盖公式计算各阶段 n/d/p/n_required 与调度索引（只读） | --feature*、--epsilon、--prior-p | --json | 否 | 只读 |
| 30 | reconcile | 503 | 控制器单步：对比期望与观测并输出待办动作；--apply 只做安全迁移（补单/解阻塞/回收陈旧 claim），不裁决不咬合不写图 | --feature*、--claim-ttl | --apply | 否 | 只读（--apply 时状态库） |
| 31 | serve | 511 | 常驻控制器：周期性对全部 feature 跑 reconcile 安全迁移；--once 单趟便于测试 | --interval、--feature、--claim-ttl | --once、--apply | 否 | 只读（--apply 时状态库） |
| 32 | sync | 520 | 只读回扫断言：重新解析登记仓，对比 DB 图与当前代码，报 missing/new/changed/stale | --repo*、--limit | — | 否 | 只读 |
| 33 | plan | 527 | 并行规划：从 feature 依赖图算强连通分量、调度波次、最大反链与理论并行上限（只读；默认排除 unmapped 噪声） | --feature*、--level | --include-unmapped | 否 | 只读 |
| 34 | cycles | 545 | 依赖环分析：把 design 层的强连通分量展开成具体依赖边与文件证据（只读） | --feature*、--without | --break-set、--advise | 否 | 只读 |
| 35 | brief | 563 | 生成一张工单的盲化任务书：只含写入边界、输入契约、产出契约与完成定义（只读） | --work*、--out | — | 否 | 只读（--out 时写文件） |
| 36 | blind-check | 570 | 盲执行校验：拿任务书与独立执行者的产出，检查写入边界、产出契约与依赖引用（只读） | --work*、--result* | — | 否 | 只读 |
| 37 | patch | 577 | 把一次盲执行产出规范成补丁文件（只读；--out 写文件），供 apply 合并 | --work*、--result*、--out* | — | 否 | 只读（--out 时写文件） |
| 38 | apply | 585 | 合并补丁并写入图库：冲突显式报告且不写半截；--dry-run 只报告 | --patches* | --dry-run | 否 | 状态库（全量校验通过才写） |
| 39 | impact | 592 | 影响域闭包：改动节点的下游可达集与需求覆盖，或断掉依赖边后的失去可达（只读） | --feature*、--changed、--remove-edges | — | 否 | 只读 |
| 40 | conflicts | 609 | 声明期冲突检测：列出 feature 之间会重叠的 target_ids 写边界（只读） | --features | — | 否 | 只读 |
| 41 | conformance | 615 | 只读一致性检查：设计锚点、depends 的代码支撑、未声明耦合、use_case 的测试覆盖；只报差异 | --feature*、--limit | — | 否 | 只读 |
| 42 | gate | 622 | 交付门：只读计算 PASS/FAIL；PASS 退出码 0、FAIL 退出码 1 | --feature* | --json | 否 | 只读 |
| 43 | export | 623 | 按 feature 导出六份只读视图（写入 <root>/export/） | --feature* | — | 否 | 文件（<root>/export/） |
| 44 | slice | 624 | 取工单或 target_ids 的深度 1 切片（只读；target_ids 支持 `前缀*` 与 @文件；--limit 防大图刷屏） | --work、--ids、--limit | — | 否 | 只读 |
| 45 | get | 625 | 按 id 读取一个节点 | --id* | — | 否 | 只读 |
| 46 | find | 626 | 按 kind / 路径前缀 / 入边起点查找节点（--limit 防大图刷屏） | --kind、--path-prefix、--from-id、--limit | — | 否 | 只读 |
| 47 | role-prompt | 627 | 生成可交给 DSH teammate 的角色提示（含状态库路径、允许命令与边界） | --role*、--token、--feature | — | 否 | 只读 |
| 48 | contract | 631 | 输出契约；--write 刷新文档契约块 | --write、--section | --json | 否 | 只读（--write 时写文档） |
| 49 | verify | 632 | 一致性自检：契约块、角色/命令/kind 交叉引用、导出样例、写入列；不替代 doctor/行为测试 | — | — | 否 | 只读 |
| 50 | doctor | 633 | 状态库自检：悬空 bite/边/引用、陈旧 token、条件与审计配对、legacy 身份、证据产物；--fix 只清理悬空引用与陈旧 token | — | --fix | 否 | 只读（--fix 时状态库） |

### 非 CLI 入口

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 / 退出码 |
|---|---|---|---|---|---|
| `COMMANDS` / `contract_json()` | 模块 API | `scripts/wxg_contract.py:299-637,997-1031` | `import wxg_contract` | 命令字典 / 契约对象 | 无；导入会原地给 `ROLES` 追加 `evidence-record` |
| `graph.sqlite` 12 张表 | 数据表 | `scripts/whyexist/db.py:18-155` | 命令 SQL | meta/repos/nodes/edges/features/conditions/work_items/feature_nodes/evidence/bites/judge_history/changes | WAL + busy_timeout=5000 |
| `<root>/export/<feature>/` | 文件 | `scripts/whyexist/commands_misc.py:22-39` | `--feature` | 6 份 md，覆盖写 | 创建目录与文件 |
| `SKILL.md` / `references/contract.md` 生成块 | 文件 | `scripts/whyexist/commands_misc.py:250-262` | `contract --write <path> [--section]` | 只替换 `wxg:contract:*` 标记之间 | 原地改写；默认路径相对 SKILL_DIR |
| 环境变量 `WXG_DB_URL` / `WXG_ACTOR` / `WXG_SKILL_DIR` | 全局状态 | `cli.py:55-56`、`db.py:425-438`、`workflow.py:14`、`commands_misc.py:271` | 调用方设置 | 选后端 / 执行者 / 校验目录 | `--db-url` 会写进 `os.environ`，进程内后续调用继承 |

### 写入与 token（实现事实，不是 help 声称）

- 实际调用 `require_token` 的有 6 个调用点、覆盖 9 条命令：`import-file`（`commands_repo.py:193`）、`import-repo`（`:298`）、`derive --apply`（`:470`）、`promote`（`:543`）、`work-finish`（`commands_feature.py:565`）、以及 `_require_write`（`commands_feature.py:717-720`，供 `upsert-node/upsert-edge/bind/retract` 共用）。`TOKEN_COMMANDS` 只列 6 条，漏了 `import-repo/derive/promote`，而且没有任何代码读它。
- token 来源：`work-claim` 用 `uuid.uuid4().hex` 生成（`commands_feature.py:522`），写 `work_items.claim_token`（唯一索引 `db.py:93`），只有 `status='claimed'` 时 `require_token` 才放行（`work.py:63-71`）；`work-finish`/`work-judge`/`feature-declare`/`feature-register`/`change-open`/`doctor --fix` 都会清空。
- 角色校验是“按调用方传入的命令名”查 `ROLES`（`work.py:74-77`），不是按注册表里的真实命令名；`import-repo` 传的是 `"import-file"`（`commands_repo.py:299`）。

## help 抽样核对（12 条）

| 命令 | help 声称 | 真实行为 | 结论 |
|---|---|---|---|
| init | 重复运行不改已有行 | `init_db` 只跑 `CREATE IF NOT EXISTS` + 迁移；`test_init_is_idempotent_after_workflow` 断言快照不变（`tests/test_wxg.py:683-696`） | 一致 |
| up | init + demo 仓 + demo feature + gate；不自动裁决、幂等 | `cmd_up` 确实不 judge，重复执行不重置；但 demo feature 用 `no_coverage=True` 创建（`commands_repo.py:101`），help 未说 | 一致但漏关键副作用 |
| import-file | `--prepare` 只预列 id；flag help 写“只预列，不写库” | 实际写 `work_items.scan` 与 `feature_nodes`（`commands_repo.py:177-192`）；探针复现 | 不一致（“不写库”错，应说“不写图”） |
| feature-declare | generation+1、重置条件、只派 work-seed | 还写 `requirement:<id>:main` 节点（`commands_feature.py:127-135`），并持久化 drift/coverage 策略 | 不完整 |
| work-claim | 领一张 ready 工单，返回 token 与切片 | 一致；另有 implement-test 的 `--allow-product-code` 门槛（`:512-513`） | 一致但漏门槛 |
| work-judge | 仅 audit 角色；BehaviorPassed 需 evidence | 一致；另要求 failed 必须 `--fail-reason`（`:677-678`），coverage 开启时还要达标（`:642-649`），且 `--role` 的 choices 含全部角色却只接受 audit | 不完整 |
| gate | PASS 0 / FAIL 1 | 一致（`cli.py:97-99`，`tests/test_wxg.py:868`） | 一致 |
| find | 按“入边起点”查找 | `id IN (SELECT dst FROM edges WHERE src=?)`（`query.py:95-97`）返回的是**出边终点**；探针 `a depends b` 下 `--from-id a` 返回 b | 方向描述反了 |
| doctor | `--fix` 只清理悬空引用与陈旧 token | 还删 feature_nodes 悬空行、裁工单 target/evidence、重写 meta 版本（`commands_misc.py:561-600`） | 少写了修复面 |
| contract | `--write` 刷新契约块 | `--write` 是带值 option（路径），还有 `--section{main,full}`；相对路径相对 SKILL_DIR（`commands_misc.py:255-260`） | 不完整 |
| serve | 周期性跑 reconcile 安全迁移；`--once` 便于测试/CI | `--once` 无论 `converged` 真假都退出 0（`cli.py:106-108`，测试用默认 exit 0 断言），CI 只能解析 JSON | 与“适合 CI”冲突 |
| apply | 冲突报告且不写半截 | 一致；但无 token/无 target_ids/无 actor，help 完全没提，退出码 1 也未写 | 不完整 |

## 契约表

状态定义：covered = 有测试直接断言；partial = 有测试但只覆盖部分分支/错误处理；gap = 行为存在但无测试/文档断言。完整证据列表见 JSON。

| ID | 状态 | 承诺 | 关键证据 |
|---|---|---|---|
| C1 | covered | 50 个注册项 ↔ 50 个 handler，一一对应 | `wxg_contract.py:299-637`；`cli.py:81-82`；`verify` 的 commands 检查 `commands_misc.py:302-305`；`tests/test_wxg.py:503-516` |
| C2 | covered | 每条命令都有 WRITE_MODES，集合相等 | `wxg_contract.py:640-691`；`tests/test_wxg.py:525` |
| C3 | gap | WRITE_MODES 的值真实反映读写 | 只有键存在性检查 `commands_misc.py:306-307`，无只读快照测试 |
| C4 | covered | help 文案进入 argparse（--help 与契约同源） | `cli.py:30` |
| C5 | gap | help 文案与行为一致 | 12 条抽样只有 init、gate 两条完全一致；2 条方向/事实错误，8 条漏关键行为（见上表） |
| C6 | gap | 全部命令 flag-only，位置参数被拒 | `P()` 无调用点（`wxg_contract.py:269-270`）；无测试断言拒绝位置参数 |
| C7 | covered | 写图需 token + 角色 + target_ids | `work.py:63-100`；`tests/test_wxg.py:465-479`；`tests/test_package_units.py:289-309` |
| C8 | covered | token 生成/唯一/生命周期清理 | `commands_feature.py:522-531,571,653`；`db.py:85-93`；`tests/test_wxg.py:444-463,710-736,415-423` |
| C9 | gap | TOKEN_COMMANDS 是权威 token 清单 | `wxg_contract.py:262` 无读者，且与实际 9 条不一致 |
| C10 | gap | command.token 字段决定 token 需求 | 只在不可达 fallback 被读（`wxg_contract.py:797-798`） |
| C11 | partial | 退出码语义 | `cli.py:57-113`；gate/reconcile/缺库有测试；argparse 错误与 serve 恒 0 无契约 |
| C12 | partial | stdout JSON / 文本 / stderr 错误 | `cli.py:109-113`；间接覆盖；argparse 错误格式无断言 |
| C13 | gap | gate/coverage 的 --json 生效 | 两个 handler 都不读 `args.json`（`commands_gates.py:28-30,159`） |
| C14 | covered | 默认 root 与“缺库不创建目录” | `cli.py:16,65-70`；`tests/test_wxg.py:873-882,947-955` |
| C15 | covered | verify 的六类自检 | `commands_misc.py:269-352`；`tests/test_wxg.py:481-501`；实跑 ok |
| C16 | partial | contract --json 是机器可读契约 | 只钉了 6 个断言（`tests/test_wxg.py:518-525`）；`token` 字段对外暴露但无人使用 |
| C17 | covered | apply 冲突不写、dry-run 不写、冲突退出 1 | `commands_compiler.py:259-295`；`tests/test_plan_cli.py:414-515` |
| C18 | partial | up 幂等 / minimal 模板 | `commands_repo.py:62-127`；`tests/test_plan_cli.py:337-359,518-522`；coverage 关闭无断言 |
| C19 | gap | feature-list / repo-list 输出 | `commands_feature.py:235-245`、`commands_repo.py:149-150`；无成功路径测试 |
| C20 | partial | work-judge 的双 id 入口与前置条件 | `commands_feature.py:585-705`；audit-id 分支无测试；help 漏 fail-reason/coverage |
| C21 | gap | 生成文档的“关键参数”列完整 | `_cmd_params` 只列必填（`wxg_contract.py:786-794`）；5 条命令显示 —，contract/serve 只显示 flag |
| C22 | gap | 契约描述完整 CLI（全局参数 + 退出码） | `COMMANDS` 无 exit_codes/read_only；`contract_json` 不含全局参数（`:997-1031`） |
| C23 | partial | 角色限制按真实命令名执行 | `work.py:74-77`；`import-repo` 用 `"import-file"`（`commands_repo.py:299`） |
| C24 | gap | 只读命令不输出可写凭证 | `work-list`/`feature-status` 返回 claim_token（`commands_feature.py:250-252,708-714`） |

## 冗余信号

| 项 | 信号 | 置信度 |
|---|---|---|
| `TOKEN_COMMANDS`（`wxg_contract.py:262`） | 0 个读者；6 条 vs 实际 9 条 | high |
| `COMMANDS[*].token` | 只在不可达 fallback 被读；50 条全有 WRITE_MODES | high |
| `P()` / `positionals` | 无调用点；渲染与解析分支永不执行 | high |
| `_cmd_write` fallback | 不可达（`tests/test_wxg.py:525` 保证覆盖） | high |
| `DEFAULT_ROOT` 三份 | `cli.py:16`、`commands_misc.py:20`、`wxg.py:26`；最后一份无人读 | high |
| `SKILL_DIR` 三份 | `wxg.py:19`、`commands_misc.py:19`、`gen_sample.py:16`，推导方式不同 | medium |
| `commands_repo.py` re-export 层 | 35 个符号再导出，`wxg.py` 却直接从原模块导入 | medium |
| 重复导入 `cmd_gate` | `commands_repo.py:14` 与 `:725` | high |
| gate/coverage 的 `--json` | 空开关；只有 `cmd_contract` 读 `args.json` | high |
| `cmd_conformance` 的 enforced 双写 | `commands_gates.py:53-55` 第二行恒冗余 | high |
| `cmd_serve` 局部 `import time` | `commands_gates.py:152` 与模块顶部 `:6` 重复 | high |
| `import-file` / `import-repo` 写入主体 | `commands_repo.py:196-227` vs `301-338` 三段近似复制 | high |
| `Engine.plan` vs `cmd_plan` | `engine.py:77-113` vs `commands_compiler.py:23-70` 同构，无 parity 测试 | medium |
| `ROLES` 原地追加 | `wxg_contract.py:258-259`，reload 会重复追加 | medium |
| `work-list` / `evidence-list` 与 `feature-status` | 三套重叠投影，token 暴露面还不一致 | low |
| `cmd_work_judge` 的 isinstance 分支 | `commands_feature.py:627` else 永远不可达 | medium |

## 分区判定

本切片没有 `freeze`：最接近“行为不明”的 `apply` 也有三个测试把语义钉住；真正的未知在文档层（例外只写在 SKILL.md），不在实现层。因此冻结应落在“改 apply 语义”这件事上，而不是整个模块。

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `wxg_contract.py`（P/O/F/C + COMMANDS，L269-637） | refactor_in_place | 唯一契约源，结构完整性由 verify + 测试保证；问题在字段缺项与 help 漂移，不是结构错 | 改字段会同时改 `contract --json`、两份文档字节与导出样例；必须增量兼容 |
| `wxg_contract.py`（WRITE_MODES，L639-691） | rewrite | 50 条纯映射、边界清楚；改成枚举才能让 verify 机械校验“只读” | 展示文本变化会改文档字节；需同一次提交重生成文档与样例 |
| `wxg_contract.py`（TOKEN_COMMANDS，L262） | rewrite | 死常量且失真，删或由 `token=True` 派生 | 低；仓内无引用 |
| `wxg_contract.py`（渲染器/contract_json，L786-1031） | refactor_in_place | 输出是字节级契约；缺陷集中在 `_cmd_params` 只列必填项 | 高：`verify` 逐字节比较，排版改动会让 CI 红 |
| `whyexist/cli.py` | refactor_in_place | 分派与退出码简单，主路径有测试；缺契约的是 `needs_db` 硬编码、退出码 if 链、env 副作用 | 改退出码等于改 CI 语义；`--db-url` 污染进程 env 会影响同进程 Engine |
| `commands_misc.py::cmd_verify` | keep | 本切片契约的执行器，有 drift 与零副作用两个测试 | 只查“注册→handler”，不查孤儿 handler；改契约字段必须同步 |
| `commands_repo.py`（re-export L662-735 + 重复 import） | rewrite | 拆包兼容残留；仓内只有 `_import_file_pairs` 从这里被用 | 低-中：外部脚本按 `wxg.commands_repo.cmd_*` 访问会断 |
| `commands_compiler.py::cmd_apply` | keep | 实现简单，三个测试覆盖成功/冲突/dry-run；无 token 是文档化例外 | 例外只在 SKILL.md:450；补 token 会改并行合并模型，属于“冻结改动”而非改代码 |
| `commands_feature.py`（claim/finish/judge token 链路） | keep | 状态机清楚，claim/actor/独立性/supersede/evidence 有测试 | audit-id 分支无测试；改 claimed_at/token 清理会牵动 doctor/reconcile |
| `whyexist/work.py`（require_*） | keep | 小、纯、有单测，token 语义唯一权威 | `require_role` 依赖调用方传对命令名；修调用点即可 |

关于“962 行是否该拆”：文件已 1058 行，其中 COMMANDS 339 行、渲染层 246 行、常量/规则 245 行。拆包（`contract/constants.py` + `contract/commands.py` + `contract/render.py`，`wxg_contract.py` 保留为薄 re-export）是合理的，但必须保留顶层模块名：`verify` 按模块导入、`tools/build_release.py` 按文件路径加载、`whyexist/contract.py` 通过 `sys.path` 插入再 import。拆包本身不改变行为，适合与“写模式枚举化”一起做。

## 隐含需求（重写会静默丢掉的行为）

1. `--prepare` 需要 feature 已存在，并写 `work_items.scan` 与 `feature_nodes`；“不写库”只指不写 nodes/edges。
2. `apply` 是唯一无 token、无 target_ids、无 actor 的图写入；写出的节点不进 `feature_nodes`，因此不进入任何 feature 作用域。
3. `up` 用 `no_coverage=True` 建 demo feature；standard 模板会在 `<root>/../demo-repo/demo.py` 造样例。
4. `work-judge` 同时接受被审工单 id 与 audit 工单 id，用 `depends_on` 反查被审对象。
5. `work-claim` 对 implement-test 额外要求 `--allow-product-code`。
6. `feature-declare --drift-limit` 用 COALESCE 持久化；不带该参数的重新声明会保留旧策略。
7. `import-file` 带 token 时 `--feature` 可省，feature 来自 token；target 边界包含本次将标 stale 的旧节点。
8. `verify` / `contract` / `role-prompt` / `up` 是仅有的四条不要求本地 sqlite 文件存在的命令。
9. gate/coverage 的 `--json` 是空开关。
10. serve 的 stdout 是“每趟一行紧凑 JSON”，与其它命令的整块 indent=2 不同；且始终退出 0。
11. argparse 层错误退出 2，但 stderr 是 usage 文本，不进入统一 JSON 错误通道。
12. `role-prompt --token` 会把 claim_token 写进提示；`contract --write` 的相对路径以 SKILL_DIR 为基准。
13. `work-list` / `feature-status` 会返回 claimed 工单的 claim_token。

## 值得人判断的问题

1. `apply` 的无 token/无边界写入保留还是收回？收回改变“单一执行者合并补丁”的并行模型；保留则契约必须显式表达例外。
2. `serve --once` 要不要像 `reconcile` 一样用退出码表达 `converged`？现在 CI 只能解析 stdout。
3. `contract --json` 里的 `commands[*].token` 算不算公开 API？删常量不影响 JSON，删字段会。
4. `work-list` / `feature-status` 返回 claim_token 是调试便利还是凭据泄漏？要不要只给 `claimed_by` 与前缀。
5. `--prepare` 怎么修：改 help 说明它写工单与作用域，还是拆出只读的 `--plan`？
6. `work-list` / `evidence-list` 与 `feature-status` 输出重叠，要不要合并成一套投影。
7. `import-repo` 的角色判定用 `import-file` 是否有意（当前两个角色名单相同）？
8. 契约拆包后是否保持 `wxg_contract` 顶层模块名？`build_release` 按路径加载、`verify` 按模块导入，改名会同时影响两处。
