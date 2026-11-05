# 14 工单 / 流程 / 简报 / 盲区 / 归约（work-flow）审计

审计对象：`scripts/whyexist/work.py`（111 行）、`workflow.py`（126 行）、`briefing.py`（118 行）、`blind.py`（108 行）、`reducer.py`（102 行），合计 565 行。

只读源码，未改实现。行为探针在 `docs/audit/_probe_14.py`（内存 SQLite + 临时目录），`python docs/audit/_probe_14.py scope` 单独复现顺序问题。实跑测试子集：

- `python -m unittest tests.test_blind tests.test_briefing tests.test_reducer tests.test_package_units -v` → 121 项通过（12 + 12 + 10 + 87）
- `python -m unittest tests.test_engine -v` → 7 项通过
- `python -m unittest tests.test_plan_cli` → 39 项通过

**先修两个前提。** 一，行数对不上：任务书给的是 91/99/91/87/77，实际是 111/126/118/108/102（非空行 88/98/97/90/84）。二，`work.py` 里没有 claim/finish：领取在 `commands_feature.py:507-561`，提交在 `564-582`，裁决在 `620-705`。`work.py` 只有 `work_id` 生成、`insert_work`（两条 UPDATE/INSERT）、`require_token / require_role / target_match / require_targets / append_evidence` 五组校验。所以「工单状态机」目前没有单一归属模块。

---

## 1. 切片范围

| 模块 | 行数 | 实际职责 | 与其它切片的关系 |
|---|---|---|---|
| `scripts/whyexist/work.py` | 111 | 工单的库级操作与访问门：id 生成、insert/get、claim_token 校验、角色白名单、target_ids 边界判定、evidence 追加 | 被 `commands_graph.py`（3 个符号）、`commands_feature.py`（7 个）、`commands_repo.py`（9 个）、`gates.py`（死 re-export）、`query.py`、`wxg.py` 消费 |
| `scripts/whyexist/workflow.py` | 126 | 条件链读写层 + 作用域计算：actor 取值、feature 取用、8 条件读取与派生、`scope_ids` | 被 8 个模块消费；`engine.py`、`gates.py`、`commands_*` 全部依赖 `ensure_feature/scope_ids` |
| `scripts/whyexist/briefing.py` | 118 | 单张工单的盲化任务书：边界展开、界外上游输入、按 kind 的产出契约、固定禁止事项/完成定义 | 被 `commands_compiler._brief_payload`、`engine.brief`、包级 `__init__` 导出；`impact.py:19` 复用其 `DEPENDENCY_EDGE_KINDS` |
| `scripts/whyexist/blind.py` | 108 | 盲执行产出校验：越界、未声明依赖、kind 不合契约三类判定 + locality 权重分 | 被 `cmd_blind_check`、`Engine.blind_check`、包级导出消费 |
| `scripts/whyexist/reducer.py` | 102 | 补丁归约：单补丁规范化、多补丁冲突检测、边端点可达性 | 被 `cmd_patch`、`cmd_apply` 消费 |

**「是不是状态机驱动者」的答案：不是。** 本切片负责读条件、算下一个条件、把单个条件置真/置假，但迁移的触发点全在外面：

- `feature-declare` / `feature-register` 直接 INSERT 8 行条件并把 Accepted 置真（`commands_feature.py:122-126`、`179-182`）；
- `work-judge(passed)` 置真一个条件再 `recompute_ready` + `refresh_blocked`（`commands_feature.py:659-661`）；
- `work-judge(failed)` 把该条件及其后全部置假（`commands_feature.py:692-695`）；
- `change-open` 按 `--from-condition` 继承/重置（`commands_feature.py:341-453`）。

`workflow.py` 没有「按事件迁移」的函数，`engine.py` 也不写条件（`engine.py:14` 明说只读）。真正的状态机语义分散在 `C.CONDITIONS` 的顺序（`wxg_contract.py:34-43`）、judge 的后缀重置、declare 的整链重建三处。与 `engine.py` 的职责重叠不在状态迁移，而在取数组装（见第 5 节第 7 条）。

---

## 2. 公开面

退出码统一：成功 0；`Reject` 与后端异常 → stderr 打 `{"error":...}` 并返回 2（`cli.py:85-90`）；例外是 `apply`（ok → 0，否则 1，`cli.py:100-102`）、`gate`、`verify`、`doctor`、`reconcile`。stdout 统一 `json.dumps(..., ensure_ascii=False, indent=2)`（`cli.py:109-113`）。

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg brief` | CLI | `commands_compiler.py:107` | `--work`、可选 `--out` | 15 键任务书 JSON；带 `--out` 时只回 `{written,work_item}` | 只读库；`--out` 无条件覆盖写 UTF-8（indent=2 + 换行，`110-115`），不建父目录 | 0 / 2 |
| `wxg blind-check` | CLI | `commands_compiler.py:119` | `--work`、`--result`（必须 JSON 对象） | `work_item/verdict/locality/boundary/contract/dependencies` | 只读；读 `--result` 文件 | 0（**即使 FAIL**）/ 2 |
| `wxg patch` | CLI | `commands_compiler.py:234` | `--work`（只当标签）、`--result`、`--out`（必填） | `{written,work_item,nodes,edges}` | 不碰库；覆盖写补丁文件；静默丢弃缺 id 节点、缺端点边 | 0 / 2 |
| `wxg apply` | CLI | `commands_compiler.py:259` | `--patches a.json,b.json`、`--dry-run` | `{ok,conflicts,unknown_endpoints,nodes,edges,applied,written_nodes,written_edges}` | 写 `nodes/edges`（`284-287`）；提交在 CLI 末尾（`cli.py:84`）；**不校验 token/角色/target_ids**，不写 evidence_ids | 0 / 1 / 2 |
| `wxg work-open` | CLI | `commands_feature.py:496` | `--feature`、`--kind`、`--target-ids` | `{"work":{action,id}}` | 写 `work_items`（insert / merge / update） | 0 / 2 |
| `wxg work-seed` | CLI | `commands_feature.py:492` | `--feature` | `{created,existed,ready}` | 按缺的条件补工单，depends_on 串链，前置未过则 blocked | 0 / 2 |
| `wxg work-claim` | CLI | `commands_feature.py:507` | `--role`、`--actor`/`WXG_ACTOR`、`--brief`、`--allow-product-code` | `{work_item_id,kind,role,actor,claim_token,target_ids,slice}` | 条件 UPDATE 原子领取（`528-535`），写 claimed/assignee/claimed_by/token/claimed_at；token=uuid4 hex，DB 唯一索引 `db.py:93` | 0 / 2 |
| `wxg work-finish` | CLI | `commands_feature.py:564` | `--token` | `{work_item_id,status:\"submitted\",audit_id,audit_status}` | evidence⊆target 校验；置 submitted + 清 token；建/重置 audit 单 | 0 / 2 |
| `wxg work-judge` | CLI | `commands_feature.py:620` | `--id`、`--verdict`、`--fail-reason`、`--role audit`、`--actor` | passed：`{verdict,condition,work_item_id,actor,legacy_claim,ready,conditions}`；failed：多 `fail_reason/conditions_changed` | 写 work_items / judge_history / conditions / Ready / 解锁 blocked | 0 / 2 |
| `wxg work-list` | CLI | `commands_feature.py:708` | `--feature` | 原始行：`target_ids`/`depends_on` 是 JSON 字符串，含明文 `claim_token` | 只读 | 0 / 2 |
| `briefing.build_brief / resolve_boundary` | function | `briefing.py:62,81` | 关键字参数（feature/work/nodes/edges 普通 dict） | 15 键 dict / 排序去重 id 列表 | 纯函数，零 IO | 无 |
| `blind.check_output` | function | `blind.py:32` | brief、output、known_node_kinds/known_edge_kinds | `{work_item,verdict,locality,boundary,contract,dependencies}` | 纯函数，零 IO | 无 |
| `reducer.normalize_patch / merge_patches` | function | `reducer.py:28,55` | patch dict / patches + existing_ids | 规范化补丁 / `{ok,conflicts,unknown_endpoints,nodes,edges}` | 纯函数，零 IO | 无 |
| `whyexist.work.*`（9 个） | function | `work.py:11-111` | conn + id/token/节点列表/feature+gen+kind | dict / None / `{action,id}`；失败抛 `Reject` | `insert_work`、`append_evidence` 写 `work_items` | 抛 `Reject` |
| `whyexist.workflow.*`（10 个公开） | function | `workflow.py:12-124` | conn + feature dict 或 (feature_id, generation) | str / dict / int|bool / list | 读 features/conditions/nodes/feature_nodes/work_items；写 conditions/work_items；读 `WXG_ACTOR` | 抛 `Reject` |
| `Engine.brief / blind_check` | function | `engine.py:115,119` | work_id（+ output） | 同 CLI | 只读；`Engine(db_url=)` 会改进程级 `WXG_DB_URL`（`47-48`） | 抛 `Reject` |
| 包级 `whyexist.build_brief / check_output` | function | `__init__.py:20,34-47` | 同上 | 同上 | 无 | 无 |
| 表 `work_items` | table | `db.py:74-93` | 16 列 | 工单当前状态 | 本切片写 status/token/evidence/targets/depends | — |
| 表 `conditions` | table | `db.py:66-72` | PK(feature_id,generation,name)，status 0/1 | 每代 8 行 | 本切片只 UPDATE（`workflow.py:64-67,77`）；INSERT 在 `commands_feature.py:122-126` | — |
| 环境变量 `WXG_ACTOR` | env | `workflow.py:14` | `--actor` 缺省回退 | strip 后 1-80 非空白 | 只读 | — |
| `--out` / `--result` 文件 | file | `commands_compiler.py:111,123,247` | 路径 | brief/patch 写 JSON；result 只读 | 覆盖同名文件；失败落到通用异常 → 2 | 0 / 2 |

---

## 3. 契约与证据

状态口径：covered = 有测试直接断言；partial = 有测试但只覆盖部分分支；gap = 代码里有行为、无测试无文档断言。共 35 条：covered 18、partial 11、gap 6。

| ID | 可观察承诺 | 证据 | 状态 |
|---|---|---|---|
| C1 | 工单 id = `work:{feature}:g{gen}:{kind}`，同 (feature, gen, kind) 只可能一张 | `work.py:11-12`；`test_package_units.py:85-89` | covered |
| C2 | `insert_work` 新建：status=ready、role=kind、targets/depends 存 JSON、created_at=UTC | `work.py:28-44`；`test_package_units.py:258-263` | covered |
| C3 | merge 只并集 target_ids，ready/claimed/blocked 放行，其它状态 Reject | `work.py:45-55`；`test_package_units.py:265-280` | partial（只测 passed 被拒） |
| C4 | 非 merge 整体替换 targets **和** depends_on（None→`[]`），status 不动 | `work.py:56-60`；`test_package_units.py:282-287` | partial（depends 重置与 status 不变靠探针） |
| C5 | `require_token` 三档拒绝（空/未知/非 claimed），成功回工单 dict；token 库内唯一 | `work.py:63-71`；`db.py:93`；`test_package_units.py:289-310`；`test_wxg.py:444-460` | covered |
| C6 | `require_role` 以 `C.ROLES` 为唯一白名单，未知角色允许集为空 | `work.py:74-77`；`wxg_contract.py:246-259`；`test_package_units.py:108-115` | covered |
| C7 | `target_match`：精确 或 `前缀*`；非字符串返回 False | `work.py:80-85`；`test_package_units.py:91-97` | covered |
| C8 | `require_targets` 精确集合+前缀判定，越界只报前 5；**空 targets 拒绝一切写入** | `work.py:88-100`；`test_package_units.py:99-106` | partial |
| C9 | `append_evidence` 去重追加并回写 work_items，同时就地改传入 dict | `work.py:103-111`；`test_package_units.py:312-318` | covered |
| C10 | `actor_value`：`--actor`/`WXG_ACTOR`，strip，1-80 非空白 | `workflow.py:12-20`；`test_wxg.py:531-533` | partial（只有缺 actor 一条） |
| C11 | `condition_flags` 要求该代条件行数 == 8，否则 Reject | `workflow.py:37-49`；`test_package_units.py:372-375` | covered |
| C12 | `current_phase` 返回第一个为假的条件名（跳过 Ready），全真返回 `"Ready"` | `workflow.py:52-60`；`test_package_units.py:377-385`；`test_wxg.py:1095-1100` | covered |
| C13 | `set_condition` 只 UPDATE；行不存在静默无效 | `workflow.py:63-67` | gap |
| C14 | `recompute_ready` 齐全且非 Ready 全真才置 Ready=1 | `workflow.py:70-78`；`test_package_units.py:387-398` | partial（返回值 0/True 混用未测） |
| C15 | `refresh_blocked` 只把 blocked→ready，条件是 deps 全 passed | `workflow.py:81-91`；`test_package_units.py:400-416` | covered |
| C16 | `scope_ids` = feature_nodes ∪ requirement 前缀 ∪ 当前代 targets（通配展开），过滤不存在 id | `workflow.py:94-124`；`test_package_units.py:418-439` | partial（顺序不确定） |
| C17 | brief 固定 15 键，blind/version/write_boundary/write_patterns/produces 语义 | `briefing.py:102-118`；`test_briefing.py:72-168`；`test_plan_cli.py:230-253` | covered |
| C18 | inputs = 边界内节点在 depends/calls/reads/writes 边上的边界外终点，不传递 | `briefing.py:28,95-100`；`test_briefing.py:84-120` | covered |
| C19 | 只接收单张工单；未知工单 Reject(2)；输出不含其它 feature | `commands_compiler.py:76-104`；`test_plan_cli.py:255-258`；`test_briefing.py:122-139` | partial（盲化只被弱断言） |
| C20 | `brief --out` 写 UTF-8 JSON（indent=2 + 换行），覆盖同名文件 | `commands_compiler.py:110-115` | gap（无一条测试用 --out） |
| C21 | blind-check 输出结构（三组 boolean + 明细 + locality） | `blind.py:95-108`；`test_blind.py:35-131`；`test_plan_cli.py:266-334` | covered |
| C22 | verdict = 三项逻辑与；**FAIL 不改变退出码** | `blind.py:81-94`；`cli.py:94-113`；`test_plan_cli.py:317-321` | covered（隐式 expect=0） |
| C23 | produces 只约束边界外新节点；produces 为空则放行 | `blind.py:45,63-64`；`test_blind.py:88-97` | partial |
| C24 | 省略 known_node_kinds/known_edge_kinds → kind 校验整体跳过 | `blind.py:40-41,65-66,78-79` | gap（探针：省略→PASS，传入→FAIL） |
| C25 | brief.inputs 里的节点只能作边端点，当产出写会判越界 | `blind.py:43-46,61-62` | gap（探针确认） |
| C26 | locality 扣分公式（0.4/0.3/0.3，额外 -0.1，clamp 两位），不参与 verdict | `blind.py:85-92`；`test_blind.py:116-131`；`design.md:364` | partial（精确值无断言） |
| C27 | `patch` 规范化后覆盖写 `--out`，回计数 | `commands_compiler.py:246-256`；`test_plan_cli.py:414-446` | partial（文件形状未断言） |
| C28 | `normalize_patch`：节点保首次、边去重排序、缺 id/端点丢弃、work_item 覆盖 | `reducer.py:28-52`；`test_reducer.py:28-56` | covered |
| C29 | 冲突指纹 = (kind,name,attrs)；指纹相同不算冲突 | `reducer.py:18-25,68-81`；`test_reducer.py:71-93,124-142` | covered |
| C30 | 边端点未知逐个上报；ok=无冲突且无未知端点；顺序无关 | `reducer.py:83-102`；`test_reducer.py:95-142` | covered |
| C31 | `apply` 只有 ok 且非 dry-run 才写；失败退出码 1 且库不变 | `commands_compiler.py:278-295`；`cli.py:100-102`；`test_plan_cli.py:414-515` | covered |
| C32 | `apply` 不校验 token/角色/target 边界，不记 evidence | `commands_compiler.py:259-295`；`wxg_contract.py:585-591`；`PRODUCT-PLAN.md:126` | gap |
| C33 | `work-finish`：token 必须 claimed；evidence⊆targets；置 submitted 清 token；建 audit 单 | `commands_feature.py:564-582`；`work.py:63-71,80-85`；`test_wxg.py:444-460` | partial（evidence 越界分支无测） |
| C34 | judge(passed) 置真一个条件+重算 Ready；failed 置假后缀；都写 judge_history | `commands_feature.py:635-705`；`workflow.py:63-91`；`test_wxg.py:324-332,1102-1131` | covered |
| C35 | `work-list` 回原始行（targets 是字符串、token 明文），与 feature-status 裁剪形状不同 | `commands_feature.py:708-714,310-317`；`test_plan_cli.py:723-733` | gap |

### 测试文件实际覆盖了什么

| 文件 | 规模 | 覆盖 |
|---|---|---|
| `tests/test_blind.py` | 135 行 / 12 项 | `check_output` 全部分支：干净通过、通配放行、越界、未声明端点、声明输入合法、produces 拒绝新节点 kind、边界内已有节点不复检、未知节点/边 kind、malformed、locality 趋势、空产出。**没有**：known kinds 省略、inputs 不可作产出、locality 精确值 |
| `tests/test_briefing.py` | 172 行 / 12 项 | `resolve_boundary` 4 项（精确/前缀/去重/未匹配）、`build_brief` 8 项（边界展开、输入判定 3 项、盲化键集、produces 映射、确定性、未知 kind）。**没有**：字段顺序、文案内容、`--out` |
| `tests/test_reducer.py` | 146 行 / 10 项 | `normalize_patch` 2 项、`merge_patches` 8 项（不交叠、指纹相同、指纹不同、端点跨补丁/来自 existing、未知端点、交换律 ×2）。**没有**：指纹范围（repo/path/unmapped）、边 kind 合法性、无 label 的冲突命名 |
| `tests/test_package_units.py` | 753 行 / 87 项（切片相关 26 项） | `WorkTargetTest` 7 项、`WorkStateTest` 10 项、`WorkflowStateTest` 9 项。切片里测试密度最高的一块 |
| `tests/test_plan_cli.py` | 865 行 / 39 项 | 切片相关：brief 2 项（e2e + 未知工单）、blind-check 3 项（PASS/FAIL/缺文件）、patch+apply 3 项（合并/冲突/ dry-run）。**没有**：`brief --out`、`patch` 文件形状 |
| `tests/test_planner.py` | 118 行 / 13 项 | **不在本切片**：`planner.select_edges` 的 kind/作用域过滤与去重排序、`build_plan` 的层级选择、波次、反链、悬空边 |
| `tests/test_cycles.py` | 173 行 / 25 项 | **不在本切片**：SCC 展开、自环单列、最小断边集、断边建议、断边代价、环形状分类 |
| `tests/test_engine.py` | 140 行 / 7 项 | `Engine.brief` 的 blind/write_patterns、`Engine.blind_check` 的 PASS/FAIL 两条 |

---

## 4. 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `work_items` | 读写 | 读 `work.py:16,21`、`workflow.py:83,113`；写 `work.py:29-43,54,57,110`、`workflow.py:91` |
| `conditions` | 读写 | 读 `workflow.py:38-42,71-74`；写 `workflow.py:64-67,77` |
| `features` | 读 | `workflow.py:26` |
| `nodes` | 读 | `workflow.py:97,107` |
| `feature_nodes` | 读 | `workflow.py:104` |
| `judge_history` | 写 | `commands_feature.py:601-617`（经 work-judge 消费 workflow 派生的条件状态） |
| `nodes/edges`（apply 旁路） | 写 | `commands_compiler.py:284-287` |
| `--out`（brief/patch） | 写 | `commands_compiler.py:110-115,247-250` |
| `--result`（blind-check/patch/apply） | 读 | `commands_compiler.py:123-129,237-245,266-273` |
| `WXG_ACTOR` | 读 | `workflow.py:14` |
| `WXG_DB_URL` | 读（间接） | `db.py:425-426`；写方 `cli.py:55-56`、`engine.py:47-48` |

跨命令共享状态：状态库本身（SQLite 文件或 `WXG_DB_URL` 指向的 MySQL/PG）、`work_items.claim_token`（唯一索引）、`conditions` 的 8 行形状、`feature_nodes` 的作用域、`WXG_ACTOR` 与 `WXG_DB_URL` 两个进程级环境变量。五个模块内部没有模块级可变全局状态；`append_evidence` 会就地修改调用方传入的 dict（`work.py:111`），是唯一一处隐式别名。

---

## 5. 冗余

1. **「前缀* 通配」至少有 9 份实现，语义已漂移。** `work.target_match`（`work.py:80-85`，有 isinstance 保护）、`work.require_targets`（`88-100`，为性能改成精确集合+前缀元组，**没有**类型保护）、`briefing._matches`（`briefing.py:56-59`）、`blind._matches`（`blind.py:21-25`，docstring 自己写「与 briefing 保持同一约定」）、`workflow.scope_ids`（`workflow.py:117-121`）、`query.py:21-23`、`conflicts.py:16-17`、`commands_misc.py:390`、`commands_graph.py:68`。high。
2. **`gates.py:402-413` 的 re-export 块是死兼容层。** 导入 9 个符号，只有 `work_id` 在模块体内使用且已被 `gates.py:11` 导入；其余 8 个零使用，全仓也没有从 gates 反取的名字。注释说「保持模块内调用点不变」，但模块内没有调用点。high。
3. **conditions 表两个写入入口。** INSERT/Accepted 直写 SQL（`commands_feature.py:122-126`、`179-182`）vs 后续 UPDATE 走 `workflow.set_condition`；failed 的后缀重置又写在 `commands_feature.py:692-695`。状态机没有单一权威。high。
4. **工单生命周期切三层且模块名撒谎。** `work.py:1` 自称状态机，实际领取/提交/裁决都在 `commands_feature.py:507-705`。high。
5. **依赖边常量三份、两份同名不同值。** `briefing.DEPENDENCY_EDGE_KINDS=('depends','calls','reads','writes')`（`briefing.py:28`）vs `derive.DEPENDENCY_EDGE_KINDS=('calls','reads','writes')`（`derive.py:23`）vs `planner.DESIGN_EDGE_KINDS/CODE_EDGE_KINDS`（`planner.py:32-35`）；`impact.py:19` 复用 briefing 那个。high。
6. **「任务书」两套实现。** `role-prompt` 手写文案（`commands_misc.py:207-247`），`brief` 结构化输出（`briefing.py`）。`references/design.md:830` 声称 role-prompt「调 briefing」，实际 `commands_misc.py` 没 import briefing。medium。
7. **engine.py 与命令层重复取数组装。** `engine.plan` ≈ `cmd_plan`（`engine.py:77-113` vs `commands_compiler.py:23-70`）、`engine.impact` ≈ `cmd_impact`（`133-151` vs `305-313`）；只有 brief/blind_check 走共享的 `_brief_payload`（`commands_compiler.py:73-104`）。medium。
8. **`whyexist.__version__ = "2.23.0"`**（`__init__.py:49`）与 `CONTRACT_VERSION "2.92.0"` 漂移，且全仓无读者；`tools/check_docs.py:32` 只比文档与契约版本。medium。
9. **`condition_rows` 被当公开导出**（`wxg.py:97`），实际只被 `condition_flags` 用（`workflow.py:46`）。low。
10. **brief 的 _FORBIDDEN/_DONE 与 SKILL.md 边界段重复表述同一组约束**（`briefing.py:42-53` vs `SKILL.md:446-448`），无引用关系。low。

---

## 6. 重写分区

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `briefing.py` | keep | 契约最清楚：纯函数、零 IO、15 键被测试锁死、边界/输入/产出三条语义各有正反用例，另有 CLI 与 Engine 两条端到端。只有字段顺序与固定文案没锁 | 低。风险在外部：`_brief_payload` 只传 work 的 4 个子字段（`commands_compiler.py:96-101`），若改成收 work 整行，会悄悄扩大对调用方的隐式契约 |
| `blind.py` | keep | 12 条单元测试覆盖三类判定与 locality 趋势，切片里测试密度最高。known kinds 省略退化、inputs 不可作产出、locality 精确值三条是文档缺口，补测试与注释即可 | 低。收紧判定会改 PASS/FAIL 语义，而 blind-check 目前不是硬门 |
| `reducer.py` | refactor_in_place | 对外形状（ok/conflicts/unknown_endpoints/nodes/edges、顺序无关）已被 10 条测试锁住；但冲突指纹只看 kind/name/attrs，丢掉 upsert 会写的 repo/path/symbol/line_*/origin/unmapped，同 id 不同锚点时静默取第一份；且不校验 kind，把失败推迟到写库 | 中。扩大指纹会改变「哪些输入算冲突」（`test_identical_node_content_is_not_a_conflict` 依赖 attrs 等值判定）；加 kind 校验会把失败点从写库前移到归约期 |
| `work.py` | refactor_in_place | 17 条单元测试锁住公开函数，但实现有三类硬伤：匹配规则四写、非 merge 分支静默重置 depends_on、非字符串 id 抛 AttributeError；模块名与内容不符 | 中。require_token 的错误文案被 `test_wxg.py:1371` 以子串依赖；merge 白名单决定 work-open/reconcile/import 三条路径能否扩边界 |
| `workflow.py` | refactor_in_place | 条件链语义清楚且有 9 条直接测试 + judge/declare 端到端，但 set_condition 无行静默、recompute_ready 返回 0/True 混用、多一行条件就永远出不了 Ready、scope_ids 顺序随哈希种子变。应把「一次裁决如何迁移条件」收敛成一个显式转移函数 | 中到高。改返回类型会改 work-judge 的 JSON；scope_ids 被 7 个模块的约 20 个调用点消费，且顺序无测试锁住 |

**没有 freeze。** 五个模块都有直接测试，没有「行为不明、无测试」的整块。若必须冻结一处，是 `briefing._FORBIDDEN/_DONE` 与 `PRODUCES` 三张字面量表（`briefing.py:31-53`）：它们是给执行者看的硬约束，不受任何断言保护，改文案不会触发失败。

**合并建议（按收益排序）：**

1. 抽出唯一的 `pattern_matches(pattern, node_id)` 与 `Patterns` 小对象，替换第 5 节第 1 条里的 9 处；`require_targets` 改用它加预编译前缀，同时补 isinstance 保护。这是纯收益、无行为变化（除修 bug）。
2. `work.py` + `workflow.py` 合成 `ticket.py`：一个负责「工单与条件的持久化 + 一次显式迁移」，把 `commands_feature` 里散落的 judge 条件重置、declare 条件重建搬进来。目前拆成两个文件并没有换来边界，只是把 111+126 行切成两份。
3. 删 `gates.py:402-413`，删 `whyexist.__version__`，把 `derive.DEPENDENCY_EDGE_KINDS` 改名为 `CODE_EDGE_KINDS` 并引用 planner 的定义。
4. `apply` 要么补 token 与边界（与 I5 一致），要么在 `wxg_contract` 写一条显式例外规则并让 `verify` 校验；现在它只在规划文档里存在。
5. `work-list` 与 `feature-status` 合成一个视图（`work-list` 的原始行形状没有测试也没有文档，`claim_token` 明文返回像是调试输出）。

---

## 7. 隐含需求（重写会静默丢掉的行为）

- `insert_work(merge=False)` 会把 depends_on 一起重置为 `[]`（`work.py:56-59`；探针：blocked 工单被覆盖后 depends_on 变 `"[]"`，status 仍是 blocked，于是永远解不开）。生产调用点都走 merge=True 或只在工单不存在时插入。
- `target_ids` 为空等于「禁止任何写入」（`work.py:94-98`）。SKILL.md 与 references/contract.md 只讲「落在 target_ids 内」，没讲空集硬拒绝，也没讲单独的 `*` 是全通配。
- `scope_ids` 的通配展开遍历 `set(existing)`，输出顺序随 PYTHONHASHSEED 变（探针：种子 0/1/2/3 得到四种顺序）。结果会被 `work_seed` 原样写进 `work_items.target_ids`（`commands_feature.py:460,479`），也会被 feature-status 取前 5 条做 `target_sample`。
- brief 的 `write_boundary` 只展开当前已存在节点，新建靠 `write_patterns` 放行（`design.md:362` 有记录）；而 blind-check 允许 pattern 匹配任意 id（`blind.py:61,76`），宽通配会让边界检查实质失效。这条推论没有文档也没有测试。
- `check_output` 的 known kinds 默认 None 时静默跳过 kind 校验（`blind.py:40-41,65-66,78-79`）；外部调用方省略参数会拿到恒 PASS 的校验器，而 CLI/Engine 都显式传。
- `brief.inputs` 里的节点只能当边端点，当产出写会判越界（`blind.py:43-46,61-62`；探针）。任务书里 inputs 只有「输入契约」一句。
- locality 精确扣分（0.4/0.3/0.3，额外 -0.1，clamp 两位）只在 `design.md:364` 有叙述，无断言；「不参与判定」也没有测试能证明。
- reducer 指纹刻意不含 repo/path/symbol/line_start/line_end/origin/unmapped（`reducer.py:20-24`；探针：`repo=r1/x.py` 与 `repo=r2/y.py` 的两个补丁 ok=True，第一份胜出）。apply 会把第一份写进图库，锚点在无提示的情况下被选中。
- `merge_patches` 不校验边 kind 与节点 kind（探针：bogus 边 kind 也 ok=True）；非法输入要等 apply 调 `graph.upsert_node` 才 Reject。能回滚只因为 CLI 最后才 commit（`cli.py:84`），这层兜底无测试。
- `apply` 完全绕过 claim_token、角色与 target_ids 边界，也不把写过的 id 记进 evidence_ids（`commands_compiler.py:259-295`）。意图只在 `docs/PRODUCT-PLAN.md:126`。
- `recompute_ready` 返回 0 或 True（`workflow.py:76-78`），所以 work-judge 的 `ready` 在 JSON 里是 `0` 或 `true`（探针）。测试用 `assertEqual(1, ...)` 掩掉类型差异。
- conditions 行数多一行会让 `recompute_ready` 永远返回假，Ready 永远为 0，且无任何报错（探针：9 行全真 → 0）。doctor 只查缺行不查多行。
- `refresh_blocked` 只认 `status='passed'` 的依赖（`workflow.py:85,90`）；依赖工单被 superseded 或 failed 时，blocked 工单永久卡住。
- `actor_value` 的身份规则（strip、1-80、无空白、env 回退）只在「CLI 缺 actor」一条测试里被间接碰过；`SKILL.md:294` 只说必须带 `--actor` 或设 `WXG_ACTOR`。
- `work-list` 把 `target_ids`/`depends_on` 以 JSON 字符串返回，并明文列出 `claim_token`（`commands_feature.py:711-714`）；feature-status 对同一张表做了裁剪与解码（`310-317`）。两个视图语义不一致，无文档。
- brief 的 forbidden/definition_of_done 是给执行者的硬约束文本（`briefing.py:42-53`），但无任何断言；改文案不会触发失败。
- brief 文档承诺「字段顺序固定、两次生成字节一致」（`briefing.py:15`），测试却用 `sort_keys=True` 比对（`test_briefing.py:157-159`），只证明了内容相同。

---

## 8. 值得人判断的问题

1. **「工单状态机」该有一个归属模块吗？** claim / finish / judge / 条件迁移 / 依赖解锁散在三处。重写时先合并成 `ticket.py`，还是保持现状、只补测试锁契约？
2. **`recompute_ready` 的 0/True 混用**是遗留还是下游真按布尔消费？统一 bool 会把 work-judge 的 `ready` 从 `0` 变成 `false`，需要先确认没有脚本按整数判断。
3. **`apply` 绕过 token 与写入边界**是产品决定（`PRODUCT-PLAN.md:126`）还是没收口的口子？若有意，SKILL.md 的 I5 要为 apply 写例外；若非，apply 缺 token 参数就是个洞。
4. **`scope_ids` 的顺序要不要修？** 消费者大多会排序或转 set，但 `work_seed` 落库顺序与 `target_sample` 会不同步。修在 `scope_ids` 末尾排序，还是让调用方各自负责？
5. **reducer 指纹要不要包含代码锚点？** 扩指纹更安全但更吵（更多并行补丁判冲突）；不扩则静默丢锚点。
6. **brief 的 forbidden/definition_of_done 算不算对外契约？** 算就进 `wxg_contract` 由 `verify` 校验；不算，那它为什么出现在机读 JSON 里，而 role-prompt 另写一套？
7. **`work-list` 为什么要明文返回 claim_token 并把 targets 留在字符串形态？** 是给脚本的兼容形状，还是没人看的调试输出？这决定它能不能并进 feature-status。
8. **`gates.py:402-413` 的 re-export 什么时候删？** 它已静置两个版本，注释说保持模块内调用点不变，但模块内没有调用点。
