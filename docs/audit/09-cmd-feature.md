# 09 命令族：feature / change / work 域

审计对象：`scripts/whyexist/commands_feature.py`（722 行；任务书写 678 行，实际 722）、其状态原语 `scripts/whyexist/work.py`（111 行）与 `scripts/whyexist/workflow.py`（126 行）。契约层（`scripts/wxg_contract.py`）已在 02 切片审计，本切片只引用其行号，不重复判定。

## 一句话结论

这 12 条命令把「feature 代际 + 8 条件 + 工单状态机」写进同一组表，主链路（declare → claim → finish → judge）测试密集、可以原地改；但只读入口泄漏 claim_token、status 与 gate 的咬合过滤口径不一致、`--brief` 仍返回全量 target_ids——这三条是当前实现里最该先定契约的行为。

---

## 1. 切片范围

| 文件 | 行数 | 作用 | 本切片判定 |
|---|---|---|---|
| `scripts/whyexist/commands_feature.py` | 722 | 12 条命令 handler + `work_seed` + `_require_write` | 按子功能分区，见 §7 |
| `scripts/whyexist/work.py` | 111 | 工单行、token、角色白名单、target 边界 | keep |
| `scripts/whyexist/workflow.py` | 126 | 条件链、Ready 派生、解锁、作用域 | keep |

进入本切片的 12 条命令：`feature-declare`、`feature-register`、`feature-list`、`feature-status`、`change-open`、`change-diff`、`work-seed`、`work-open`、`work-claim`、`work-finish`、`work-judge`、`work-list`。

不在本切片但被直接依赖：`gates.py`（coverage/drift/reconcile 的 claim TTL 在 `gates.py:316-417`）、`commands_gates.py::cmd_gate`（另一套 bite 过滤，`commands_gates.py:166-187`）、`evidence.py:19-35`、`db.py` 的 schema 与迁移。它们的行为只在解释本切片时引用。

本切片不产生任何文件产物：没有 export、没有临时文件；唯一的持久化是 `<root>/graph.sqlite`（由 `cli.py:66-69` 检查存在性，`db.py:441-465` 连接）。

实测：`python -m unittest tests.test_wxg` 的 27 个相关用例全过（45.1s）；探针见 `docs/audit/_probe_09.py`、`_probe_09b.py`，输出在 `_probe_09.out.txt`、`_probe_09b.out.txt`。

---

## 2. 公开面

### 2.1 CLI

退出码统一：成功 0；`Reject` 与 argparse 错误 2（`cli.py:85-90`）；`work-judge` 判 failed 也是 0（探针 S6.11）。输出统一是 indent=2 JSON 写 stdout，错误是 `{"error": ...}` 写 stderr（`cli.py:109-113`）。

| 命令 | handler | 输入 | 输出（stdout JSON） | 副作用（DB 写入） |
|---|---|---|---|---|
| `feature-declare` | `commands_feature.py:43-137` | `--id/--name/--statement/--acceptance/--constraints`，`--coverage-epsilon`、`--drift-limit`，flags `--no-coverage/--conformance/--no-conformance` | `{feature_id,generation,accepted_only,work_seed}` | features（upsert，gen+1）、conditions（8 行，仅 Accepted=1）、nodes（requirement，merge_attrs）、work_items（旧代 superseded；新代 6 张） |
| `feature-register` | `commands_feature.py:140-232` | `--id/--name/--spec`、`--generation` | 三分支键不一致（见 C10-C12） | features、conditions（新 feature/新代仅 Accepted）、nodes（requirement）；旧代 supersede；从不 seed |
| `feature-list` | `commands_feature.py:235-245` | — | `{features:[{id,name,generation,conditions}]}` | 只读 |
| `feature-status` | `commands_feature.py:248-338` | `--id` | `feature/phase/conditions/work_items/bites/evidence/judge_history/changes/coverage/drift/constructions/stale/conformance/scope_size` | 只读 |
| `change-open` | `commands_feature.py:341-396` | `--feature/--statement/--from-condition`、`--id` | `{change,feature,from_generation,to_generation,from_condition,inherited,reset,work_seed}` | work_items（supersede）、features（gen+1）、conditions（新代 8 行）、changes、work_items（seed） |
| `change-diff` | `commands_feature.py:399-453` | `--feature`、`--from-generation` | `{feature,change,from_generation,to_generation,inherited_conditions,pending_conditions,added,removed,kept,code_anchors}` | 只读 |
| `work-seed` | `commands_feature.py:456-493` | `--feature` | `{created,existed,ready}` | work_items |
| `work-open` | `commands_feature.py:496-504` | `--feature/--kind/--target-ids` | `{work:{action,id}}` | work_items.target_ids |
| `work-claim` | `commands_feature.py:507-561` | `--role`、`--actor`，flags `--allow-product-code/--brief` | `{work_item_id,kind,role,actor,claim_token,target_ids,slice}` | work_items（claimed + assignee/claimed_by/claimed_at/token） |
| `work-finish` | `commands_feature.py:564-582` | `--token` | `{work_item_id,status,audit_id,audit_status}` | work_items（submitted、清 token、建/重置 audit 单） |
| `work-judge` | `commands_feature.py:620-705` | `--id/--verdict/--fail-reason/--role/--actor` | passed / failed 两套（见 C26-C30） | work_items、conditions、judge_history |
| `work-list` | `commands_feature.py:708-714` | `--feature` | `{feature,generation,work_items:[...]}` | 只读 |

### 2.2 公开函数与跨模块入口

| 入口 | 位置 | 说明 |
|---|---|---|
| `work_seed(conn, feature_id)` | `commands_feature.py:456-489` | 被 declare(:136)、change-open(:380)、reconcile 的 apply（`commands_gates.py:63`）复用；本模块唯一被外部当函数用的状态迁移 |
| `_require_write(conn,args,cmd)` | `commands_feature.py:717-720` | 被 `commands_graph.py:11`、`commands_repo.py:664` 导入；`wxg.py:120` 再导出。归属应在 `work.py` |
| `record_judge_history(...)` | `commands_feature.py:601-617` | judge_history 的唯一写入点 |
| `_resolve_subject(conn,id)` | `commands_feature.py:585-598` | 支持「本单 id」与「audit 单 id」两种裁决入口 |

### 2.3 数据表

本切片读写 9 张表：`db.py:54-65` 的 `features`、`db.py:66-73` 的 `conditions`、`db.py:74-94` 的 `work_items`（token 唯一索引 `db.py:93`）、`db.py:127-138` 的 `judge_history`、`db.py:139-149` 的 `changes`，以及 `nodes`（requirement 子集）、`feature_nodes`（经 scope 只读）、`bites`（只读）、`evidence`（只读）。MySQL 版本在 `db.py:154-284`（`work_items.id VARCHAR(512)`、token 唯一键 `db.py:227`）。

---

## 3. 契约表

状态：covered = 有测试直接断言；partial = 有测试只覆盖部分分支；gap = 行为存在但无测试/文档断言。

| ID | 承诺 | 状态 | 关键证据 |
|---|---|---|---|
| C1 | `--id` 只接受 `[A-Za-z0-9._-]+`，否则 Reject | gap | `commands_feature.py:45-46,149-150`；探针 S1.6 |
| C2 | declare 的 acceptance/constraints 必须是 JSON 数组，支持 `@文件`；statement 非空 | gap | `commands_feature.py:47-52`；`jsonio.py:34-59` |
| C3 | coverage 策略：显式 ε>0 优先、`--no-coverage` 置空、互斥、新 declare 默认 1.0、重声明保留 | covered | `commands_feature.py:53-58,68-75,92-96`；`test_wxg.py:1613-1654` |
| C4 | coverage 开启时 judge(passed) 与 gate 同规则拦截 | covered | `commands_feature.py:642-649`；`gates.py:81-121`；`test_wxg.py:1133-1156` |
| C5 | `--drift-limit` ≥0；COALESCE 持久化；无清除入口 | partial | `commands_feature.py:59-61,107`；`test_wxg.py:1238-1244`；探针 S2.2/S2.5 |
| C6 | conformance 默认关、显式开关、互斥、重声明保留 | partial | `commands_feature.py:62-65,77-84`；`test_wxg.py:1758-1813` |
| C7 | declare 每次 gen+1；旧代 supersede 并清 token；新代只 Accepted=1；旧代行保留 | covered | `commands_feature.py:85-126`；`test_wxg.py:270-297`；探针 S2.3/S2.4 |
| C8 | requirement 节点写入，merge_attrs 保留外部 attrs（含 declare 重声明） | covered | `commands_feature.py:127-135,161-169`；`test_wxg.py:744-755,1028-1050` |
| C9 | declare 自动 seed 六张工单，依赖链只有首张 ready | partial | `commands_feature.py:136,456-489`；`test_wxg.py:1455-1475` |
| C10 | register 新建：只写元数据+Accepted+requirement，不 seed；coverage 关闭 | partial | `commands_feature.py:172-191`；`test_wxg.py:757-769`；探针 S3.2-S3.4/E4 |
| C11 | register 同代：只改 name/spec/requirement，条件不动 | covered | `commands_feature.py:193-205`；`test_wxg.py:698-708` |
| C12 | register `--generation` 必须更大；旧代（含 claimed）supersede 并清 token；不自动 seed | partial | `commands_feature.py:207-232`；`test_wxg.py:710-742`；探针 S3.6 |
| C13 | feature-list 输出形状；任一 feature 条件行不齐则整条 Reject | gap | `commands_feature.py:235-245`；`workflow.py:45-49`；探针 E1.1 |
| C14 | feature-status 字段集；target_ids 换 target_count/sample；phase=首个假条件；evidence 不分代 | partial | `commands_feature.py:248-338,310-317`；`test_plan_cli.py:723-733,776-780` |
| C15 | status 与 gate 的 bite 归属过滤不一致（可同时出现 status 空 / gate FAIL） | gap | `commands_feature.py:257-272` vs `commands_gates.py:166-187`、`gates.py:14-33`；探针 S8 |
| C16 | change-open 只允许 Ready；from-condition 限六个设计条件；继承/重置/新代/seed 生效 | covered | `commands_feature.py:341-396`；`test_wxg.py:1446-1533` |
| C17 | change id 全局唯一；未收口前再次 change-open 被 Ready=0 拒绝 | partial | `commands_feature.py:342-351`；`test_wxg.py:1477-1489`；探针 S7.10 |
| C18 | change-diff 基线优先级；基线<1 Reject；added/removed/kept/anchors 定义 | partial | `commands_feature.py:399-453`；`test_wxg.py:1491-1518`；探针 S7.9 |
| C19 | change-diff 看不到 import-file 写的节点（scan 不追加 evidence_ids） | gap | `commands_repo.py:216-217`；`work.py:103-111`；`test_wxg.py:1310-1321` |
| C20 | work-seed 幂等、依赖链规则、exists 不改状态 | partial | `commands_feature.py:456-489`；`test_wxg.py:739-742`；探针 S6.22 |
| C21 | work-open 合并去重、audit 拒绝、submitted/passed/failed 不可并入 | partial | `commands_feature.py:496-504`；`work.py:25-60`；`test_wxg.py:431-443`；探针 S4.7 |
| C22 | claim 前置：role/audit/implement-test/actor 校验 | partial | `commands_feature.py:507-537`；`workflow.py:12-20`；`test_wxg.py:465-479,527-567`；探针 E2 |
| C23 | claim 原子 + 写 assignee/claimed_by/claimed_at/token；只发当前代 | partial | `commands_feature.py:515-560`；`db.py:93`；`test_wxg.py:1391-1402` |
| C24 | `--brief` 只裁 slice，target_ids 仍全量 | gap | `commands_feature.py:539-552`；`test_wxg.py:1291-1297`；探针 E3.2 |
| C25 | finish：token 校验、evidence ⊆ targets、submitted、建/重置 audit 单 | partial | `commands_feature.py:564-582`；`test_wxg.py:444-463,710-736` |
| C26 | judge 前置：audit 角色、actor 独立（legacy 放行）、submitted、双 id 入口 | partial | `commands_feature.py:585-630`；`test_wxg.py:527-567`；探针 S6.7/S6.15 |
| C27 | judge(passed) 的状态与条件效果、Ready 重算、解锁 | covered | `commands_feature.py:650-676`；`test_wxg.py:527-567,1102-1131` |
| C28 | judge(passed) 的 evidence / coverage 门槛 | covered | `commands_feature.py:635-649`；`evidence.py:19-35`；`test_wxg.py:822-835,1133-1156` |
| C29 | judge(failed) 的效果：audit failed、subject ready、链重置、scan 不改条件 | covered | `commands_feature.py:677-696`；`test_wxg.py:324-333,836-847,1102-1131` |
| C30 | judge_history 9 列、id 格式、只增不删 | partial | `commands_feature.py:601-617`；`wxg_contract.py:174-184`；`test_wxg.py:1102-1131` |
| C31 | work-list 只列当前代原始行，target_ids 是 JSON 字符串，含 token | partial | `commands_feature.py:708-714`；`test_wxg.py:350-351,1470-1473` |
| C32 | 四条只读命令不写库 | gap | `commands_feature.py:235-338,399-453,708-714`；gate 有只读测试（`test_wxg.py:299-306`），这四条没有 |
| C33 | 缺库时 12 条命令退出 2、不建目录 | partial | `cli.py:65-69`；`test_wxg.py:947-955` 只测 gate/work-seed/repo-list |
| C34 | 只读入口原样返回 claim_token | gap | `commands_feature.py:250-254,711`；探针 S5.6/S5.7 |
| C35 | assignee=role，finish/judge 不清 | gap | `commands_feature.py:528-532,571,653-655`；探针 E5 |
| C36 | changes.affected_json 恒 `[]` | gap | `commands_feature.py:375-379`；探针 S7.4 |
| C37 | failed 后重试保留 evidence_ids 与 claimed_by | gap | `commands_feature.py:685-689`；探针 S6.12/S6.14 |
| C38 | audit 单不参与 claim、无 token；judge 同时写 audit 的 judged_by | covered | `commands_feature.py:508-511,572-581,650-656`；`test_wxg.py:527-567` |

---

## 4. 状态读写

| 目标 | 读写 | 位置 |
|---|---|---|
| `features` | both | 写 `commands_feature.py:87-121,171-232,359`；读 `commands_feature.py:66,237-243,402,427` |
| `conditions` | both | 写 `commands_feature.py:122-126,179-183,219-223,360-374,693-696`；读 `commands_feature.py:243,322-323,343,427,459` |
| `work_items` | both | 写 `commands_feature.py:87-91,211-214,354-358,463-489,503,515-535,571-581,650-696`；读 `commands_feature.py:250-254,419,710-714` |
| `judge_history` | both | 写 `commands_feature.py:601-617`；读 `commands_feature.py:273-280` |
| `changes` | both | 写 `commands_feature.py:375-379`；读 `commands_feature.py:299-306,401-406` |
| `nodes` | both | 写 requirement `commands_feature.py:127-135,161-169`；读 construction/stale/锚点 `commands_feature.py:289-298,437-441` |
| `feature_nodes` | read | `workflow.py:104-105`（经 `commands_feature.py:256,290,295`） |
| `bites` | read | `commands_feature.py:257-272` |
| `evidence` | read | `commands_feature.py:281-288,637` |
| `WXG_ACTOR` | read | `workflow.py:12-20` |
| `WXG_DB_URL` / `--db-url` | read | `cli.py:55-61`、`db.py:425-438`（全局共享，进程内不还原本地 env） |
| `<root>/graph.sqlite` | read（存在性） | `cli.py:66-69` |

隐式共享状态（跨命令）：`scope_ids` 把 `work_items.target_ids` 也算进作用域（`workflow.py:110-124`），所以 `work-open` 会改变 coverage 分母、drift 统计与 gate 范围；`changes` 由 change-open 写、doctor 与 change-diff 读；`judge_history` 由 work-judge 写、doctor 读（`commands_misc.py:453-466`）；`conditions` 一旦缺行，feature-list/status/work-seed 全部 Reject（`workflow.py:45-49`）。

---

## 5. 冗余信号

| 项 | 信号 | 置信度 |
|---|---|---|
| 3 个未用 import | `append_evidence`/`get_work_by_token`/`require_targets` 只在 `:21,:23,:26` 出现 | high |
| `_require_write` 归属错位 | 定义 `:717-720`，被 `commands_graph.py:11`、`commands_repo.py:664` 导入，本模块从不调用 | high |
| 两处不可达校验 | `:500-501`、`:346-348`；argparse choices 先拒绝（`wxg_contract.py:412,426`） | high |
| features/conditions 写入重复 | `:102-126` vs `:174-183`、`:210-223`，列集合不一致 | high |
| construction/stale 循环重复 | `:289-298` vs `commands_gates.py:205-215` | high |
| bite 过滤三套 | `:257-272`、`commands_gates.py:166-187`、`gates.py:14-33`，行为还不一致 | high |
| claim 每依赖两次 `get_work` | `:525` | medium |
| insert 后单写 status | `work.py:30-43` + `:480` | medium |
| `affected_json` 死列 | `:378` 写死 `[]`，无读者 | high |
| 三份重叠视图 | `:481-489` 的 created/existed/ready | low |
| assignee 与 role 同值且不清 | `:529-531`、`:571`、`:653` | medium |
| feature-status 每节点两次 get_node | `:289-298` | medium |
| JUDGE_HISTORY_COLUMNS 与 DDL 双维护 | `wxg_contract.py:174-184` vs `db.py:127-138,586-591` | medium |
| 测试用 force_ready 绕过状态机 | `test_wxg.py:110-117`；change-open 的 6 个用例都靠它 | medium |

---

## 6. 测试断言密度

数字来自 `docs/audit/_count_09.py`：把 helper 调用（`declare/status/open_targets/claim/finish/judge/import_scan/complete_through_implement`）折算成命令调用后，每个命令被多少个测试触达 / 总调用次数。

| 命令 | test_wxg（85 用例） | test_plan_cli（39 用例） |
|---|---|---|
| feature-declare | 72 / 81 | 34 / 36 |
| feature-register | 6 / 8 | 0 |
| feature-list | 0 | 0 |
| feature-status | 19 / 26 | 2 / 2 |
| change-open | 6 / 7 | 0 |
| change-diff | 1 / 1 | 0 |
| work-seed | 2 / 2 | 0 |
| work-open | 16 / 21 | 20 / 22 |
| work-claim | 40 / 56 | 24 / 27 |
| work-finish | 22 / 29 | 14 / 14 |
| work-judge | 21 / 35 | 0 |
| work-list | 2 / 2 | 0 |

注意：触达数不代表断言密度。`change-diff` 只有 1 个用例，且只断言 added/removed/anchors；`work-list` 的 2 个用例只取 status；`feature-status` 的 19 次触达里只有 2 个用例断言了具体字段（target 裁剪、phase）。

---

## 7. 分区判定

| 模块/函数 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `commands_feature.py::feature-declare`（43-137） | refactor_in_place | 契约清楚、策略有测试；策略解析与两套 SQL 缠在一起，参数校验分支无测试 | 策略字段决定 gate/judge 行为；改持久化会影响旧库 |
| `::feature-register`（140-232） | refactor_in_place | 三分支返回键不一致、与 declare 重复写表；coverage 关闭是隐式行为 | 代际与 token 清理牵动 doctor/旧代工单 |
| `::feature-list`（235-245） | rewrite | 10 行、0 测试、all-or-nothing | 输出形状无测试锚 |
| `::feature-status`（248-338） | refactor_in_place（字段集 freeze） | 最大公开面；N+1、重复循环、evidence 不分代、token 泄漏 | `tools/verify_reports.py:224-227` 与 agent 提示消费字段 |
| `::change-open`（341-396） | refactor_in_place | 流程有测试；死字段、全局 id、重复条件插入 | doctor 依赖 changes 行与继承条件（`commands_misc.py:468-494`） |
| `::change-diff`（399-453） | rewrite | 1 个测试、基线语义未定、未来代不报错 | 输出键被 SKILL.md:67 引用；需先补测试 |
| `::work_seed`（456-489） | refactor_in_place | 依赖链核心，边界多（继承条件无单、prev 只在 passed 时设） | declare/change-open/reconcile/serve 四处复用 |
| `::work-open`（496-504） | keep | 只做合并委托，行为窄 | merge 拒绝条件在 `work.py:46-47` |
| `::work-claim`（507-561） | keep | 原子领取、token 字段清楚；slice 形状属 07 切片冻结项 | 跨 feature 选择、`--brief` 全量 targets、并发无 SQLite 测试 |
| `::work-finish`（564-582） | keep | token 生命周期与 audit 单有测试 | audit id 拼法被 doctor/role-prompt 引用 |
| `::work-judge`（620-705） | refactor_in_place（转移表 freeze） | 最复杂状态机；双 id、legacy、COALESCE、两段 UPDATE 复制；支路无测试 | 直接决定条件/Ready/gate/doctor/serve 观感 |
| `::work-list`（708-714） | rewrite | 5 行、2 个断言只查 status、泄 token | target_ids/depends_on 是 JSON 字符串 |
| `::record_judge_history`（601-617） | keep | 唯一写入口、列与契约一致 | id 格式无断言；迁移回填用另一格式 |
| `::_require_write`（717-720） | refactor_in_place | 归属错位，应移入 `work.py` | 低；同步 3 处 import/re-export |
| `::work-judge` 的状态转移表（585-705） | freeze | `status/condition/judged_by/judge_history` 的组合是 gate/doctor/serve/reconcile 的输入，契约已固定；audit-id 与 legacy 支路无测试 | 改转移会静默改 PASS/FAIL 与 Ready 派生；先补转移矩阵测试 |
| `::feature-status` 输出字段集（318-338） | freeze | `tools/verify_reports.py:224-227` 消费 `scope_size`，agent 提示消费 `phase/conditions/coverage`；字段无完整断言 | 改名字段/嵌套形状会破坏外部读取方；只加不删 |
| `work_items` 状态词表 | freeze | `ready/claimed/submitted/passed/failed/blocked/superseded` 是散在字面量里的隐式枚举，被 reconcile/doctor/serve/role-prompt 共享 | 改名要迁移旧库并同步 `commands_gates.py`、`commands_misc.py`、`tools/`；先提常量 |
| `work.py` | keep | 薄原语、单一权威 | `require_role` 依赖调用方传对命令名 |
| `workflow.py` | keep | 条件链/作用域唯一实现 | `condition_flags` 的不齐即 Reject 决定列表命令的失败粒度 |

---

## 8. 隐含需求（重写会静默丢掉的行为）

1. `feature-register` 新建的 feature 没有 coverage 策略，之后 `feature-declare` 也不会打开（探针 E4.2/E4.3）；「新 feature 默认开启覆盖」只对 declare 成立。
2. `work-claim --brief` 仍返回完整 `target_ids`（400 个 id = 4690 字符），只裁剪 slice（探针 E3.2）。
3. `work-claim` 没有 `--feature`：按 role 在所有 feature 的当前代里挑 id 最小的一张（探针 S5.10）。
4. `assignee` 被写成 role，finish/judge 不清；清它的是 supersede 与 reconcile（探针 E5）。
5. claim 本身没有租约：`claimed_at` 只被 reconcile 读，TTL 默认 3600 秒（`gates.py:349-367`，探针 S5.8/S5.9）。
6. `--allow-product-code` 对非 implement-test 角色静默无效（探针 S9.4）。
7. `feature-list` 一条 feature 的条件行缺失会让整条命令 Reject（探针 E1.1）。
8. 重声明保留 requirement 上手写 attrs（含 `attrs.bite`），只覆盖 name/statement（探针 E8.1）。
9. change id 全局唯一，不按 feature 隔离（探针 S7.10）。
10. change-open 的 `--statement` 只校验存在，空白也算（`commands_feature.py:341-396` 无内容校验）。
11. `changes.affected_json` 永远是 `[]`（探针 S7.4）。
12. judge(failed) 后重试单保留 `evidence_ids` 与 `claimed_by`（探针 S6.12/S6.14）。
13. feature-status 的 `evidence` 不按代过滤，而 judge/gate 只认同代（`commands_feature.py:281-288` vs `evidence.py:19-35`）。
14. change-diff 看不到 import-file 写的节点（`commands_repo.py:216-217`）。
15. audit 单从不被 claim、没有 token，只在 judge 时被同时置 passed/failed（`commands_feature.py:572-581,650-656`）。
16. `work-open` 允许在 claimed 单上继续合并边界，finish 的 evidence 校验按新边界算（探针 S4.7）。
17. `drift_limit` 一旦设置无法清除（探针 S2.5）。
18. 旧代 conditions/work_items/judge_history 永不删除；status 只展示当前代工单，但展示全部代的 changes/evidence（探针 S2.3/S2.4）。
19. `feature-declare` 每次调用都推进 generation，即使文本没变（探针 S2.1）。
20. `work-seed` 的依赖链只在上一条件已真且工单 passed 时建立；继承条件没有工单，链从第一个缺失条件重新开始（探针 S7.6）。

---

## 9. 值得人判断的问题

1. register 路径没有 coverage 默认，是设计还是遗漏？若有意，两种入口的策略矩阵要写进契约；若修，已登记 feature 的门禁结果会变。
2. `work-claim` 要不要 `--feature`？现在多 feature 并行的领取结果由 id 字典序决定。
3. `--brief` 要不要连 `target_ids` 一起裁剪（count + hash）？不裁剪的话「省上下文」不成立。
4. claim_token 出现在只读命令里是调试便利还是安全缺陷？保留则至少给前缀；收回则 role-prompt 与测试工具要同步。
5. status 与 gate 的咬合过滤要不要抽成唯一实现？统一就是改 gate 判定（当前 gate 更宽），属于行为变更。
6. change-diff 允许未来代（`--from-generation 9` 不报错，探针 S7.9）要不要收紧；scan 写的节点算不算「变更」。
7. `assignee` 列还有存在价值吗？role 已是同值，agent 身份在 `claimed_by`；删列要动 MySQL/PG 迁移（`db.py:516-583`）。
8. judge 的 legacy 放行（claimed_by 为空即允许自审）要不要保留？保留则 audit-id 入口是否应成为唯一入口。
9. `changes.affected_json` 是留给未来字段级 diff，还是直接删列？当前是纯死字段，删列要升 schema。
