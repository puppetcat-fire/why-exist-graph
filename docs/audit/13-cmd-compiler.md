# 13 命令族：compiler 域（8 条命令）

plan / brief / blind-check / cycles / patch / apply / impact / conflicts

## 切片范围

| 文件 | 实际行数 | 职责 |
|---|---|---|
| scripts/whyexist/commands_compiler.py | 387 | 8 条命令的取数与组装；判定全部下沉到纯函数模块 |
| scripts/whyexist/planner.py | 143 | 选边、design kind 过滤、调 graph_algo、写 bottleneck/parallelism |
| scripts/whyexist/impact.py | 217 | 可达闭包、direct/indirect、断边损失、requirement 覆盖 |
| scripts/whyexist/cycles.py | 285 | SCC 展开成环、最小断边集合、断边建议、环形态 |
| scripts/whyexist/conflicts.py | 80 | feature 两两 target_ids 模式重叠检测 |

任务给的 350/105/172/229/61 与磁盘实际行数不一致（依次差 37/38/45/56/19 行）；判定按磁盘实际内容做。

相邻但不属于本片的模块：`blind.py`（108 行）、`briefing.py`（118 行）、`reducer.py`（102 行）由切片 14 拥有，本片只记录它们在 brief / blind-check / patch / apply 命令路径上的调用契约；`engine.py`（151 行）只在与 plan/brief/impact 的重复实现有关时引用。

命令注册表与写入模式声明：`scripts/wxg_contract.py:527-614`、`scripts/wxg_contract.py:673-680`。退出码分派：`scripts/whyexist/cli.py:94-113`。

## 公开面

### CLI（stdout 均为 JSON，`apply`/`patch`/`brief --out` 例外说明见下）

| 入口 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|
| `wxg plan` | wxg_contract.py:527 | `--feature`（必填）、`--level auto\|design\|code`、`--include-unmapped` | feature/level/node_count/edge_count/acyclic/cyclic_components/layers/layer_count/max_antichain/parallelism/bottleneck/dangling/excluded_unmapped/excluded_stale（+hint） | 只读 | 0；2（feature 不存在、未初始化、空节点集 ValueError） |
| `wxg brief` | wxg_contract.py:563 | `--work`、`--out` | 15 键任务书；给 `--out` 时只返回 {written, work_item} | 只读；`--out` 覆盖写文件 | 0；2 |
| `wxg blind-check` | wxg_contract.py:570 | `--work`、`--result` | verdict/locality/boundary/contract/dependencies | 只读；每次重算任务书 | 0（FAIL 也 0）；2 |
| `wxg cycles` | wxg_contract.py:545 | `--feature`、`--without`、`--break-set`、`--advise` | cycle_count/cycles[]；可选 break_sets[]/advice[]/truncated | 只读 | 0；2 |
| `wxg patch` | wxg_contract.py:577 | `--work`、`--result`、`--out` | {written, work_item, nodes, edges} | 只写 `--out`，不读库 | 0；2 |
| `wxg apply` | wxg_contract.py:585 | `--patches`、`--dry-run` | ok/conflicts/unknown_endpoints/nodes/edges/applied/written_* | 写 nodes、edges；条件写 feature_nodes | 0；1（合并失败）；2（参数/解析/写库校验） |
| `wxg impact` | wxg_contract.py:592 | `--feature`、`--changed`、`--remove-edges` | 两种模式字段不同，remove-edges 多一个 mode | 只读；为全部 feature 算作用域 | 0（closed=false 也 0）；2 |
| `wxg conflicts` | wxg_contract.py:609 | `--features` | features/coexist_ok/conflicts[] | 只读 | 0（有冲突也 0）；2 |

### 函数 / 表 / 文件

| 入口 | kind | 位置 | 说明 |
|---|---|---|---|
| planner.build_plan / select_edges | function | planner.py:70 / 48 | 纯函数；level 非法抛 ValueError；节点集为空时崩溃 |
| cycles.find_cycles / cycle_shape / cycle_guidance | function | cycles.py:220 / 184 / 216 | 纯函数；SCC 内边全列出，自环单列 |
| cycles.minimal_break_sets / break_set_costs / advise_break_edges | function | cycles.py:34 / 84 / 120 | 纯函数；组合枚举、每档 10 组上限、内部重算 |
| impact.build_impact / edge_removal_impact / requirement_coverage | function | impact.py:160 / 83 / 115 | 纯函数；requirement 集合由调用方传全图 |
| conflicts.detect_conflicts / patterns_overlap | function | conflicts.py:42 / 21 | 纯函数；仅尾部 `*` 通配 |
| _brief_payload | function（私有但跨模块） | commands_compiler.py:73 | cmd_brief / cmd_blind_check / Engine.brief 共用 |
| Engine.plan / brief / blind_check / impact | function（库 API） | engine.py:77-151 | 只覆盖 4 个命令，缺 cycles/patch/apply/conflicts；plan 与 CLI 已漂移 |
| nodes / edges 表 | table | db.py:30 / 44 | 读：plan、cycles、brief、blind-check、impact、conflicts；写：apply |
| features / feature_nodes / work_items 表 | table | db.py:54 / 95 / 74 | 切片内只读；apply 仅在补丁节点带 feature_id 时写 feature_nodes |
| `<root>/graph.sqlite` | file | db.py:458 | 切片内命令要求已存在，不自动建库（cli.py:65-70） |
| `--out` 任务书/补丁文件 | file | commands_compiler.py:110 / 246 | UTF-8 JSON，indent=2，末尾换行；覆盖写、非原子、不建父目录 |
| `--result` 执行产出 | file | commands_compiler.py:123 | 只读输入；顶层必须是 JSON 对象 |

## 契约表

状态口径：covered = 有测试直接断言；partial = 有测试但只覆盖部分分支/路径；gap = 代码行为存在但无测试断言。

### plan

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C1 | plan 只读：执行前后 12 张表内容不变 | covered | tests/test_plan_cli.py:184-199；commands_compiler.py:23-70 |
| C2 | 同一状态连续两次 plan 输出相同；输入顺序反转不影响函数结果 | covered | tests/test_plan_cli.py:196-199；tests/test_planner.py:109-114 |
| C3 | auto 有 depends 边走 design，否则回退 code，输出 level 标明实际层级 | covered | tests/test_planner.py:41-54；tests/test_plan_cli.py:201-210 |
| C4 | design 层只保留 component/port/pattern，requirement 不计入 | covered | tests/test_plan_cli.py:150-182；planner.py:102-107 |
| C5 | `--level design` 在过滤后节点集为空时抛 ValueError、退出 2、无 JSON 结果 | gap | planner.py:114-118；cli.py:88-90；探针 `_probe_13b.py` |
| C6 | code 层不做 kind 过滤，requirement 等也计入 node_count/layers/反链 | gap | planner.py:99-109；探针 `_probe_13c.py` |
| C7 | 显式 `--level code` 且无代码层节点时结果带 hint | covered | tests/test_plan_cli.py:769-774；commands_compiler.py:61-69 |
| C8 | 默认排除 unmapped 并返回 excluded_unmapped；`--include-unmapped` 恢复 | covered | tests/test_plan_cli.py:525-535 |
| C9 | 排除 stale 并返回 excluded_stale | gap | commands_compiler.py:38-45；探针 `_probe_13c.py` |
| C10 | 被排除节点的边仍参与分析，最终报成 dangling.unknown_endpoint | gap | commands_compiler.py:28-47；planner.py:48-67；探针 `_probe_13b.py` |
| C11 | 无环时 layers/layer_count 有值，parallelism=max_antichain，bottleneck 含“最大反链” | covered | tests/test_planner.py:67-90 |
| C12 | 有环时 layers=null、cyclic_components 列出 SCC、parallelism=最大环、bottleneck 含“最大环” | covered | tests/test_planner.py:77-83；tests/test_plan_cli.py:212-228 |
| C13 | 只有自环时 acyclic=false、layers=null、bottleneck 说“单点自环”，parallelism 退回反链 | partial | tests/test_planner.py:99-101；graph_algo.py:374-379 |
| C14 | 悬空边分 unknown_endpoint/self_loop/duplicate 三类报告 | partial | tests/test_planner.py:103-107；planner.py:138-142 |
| C15 | plan 输出键集合固定（含 excluded_* 与可选 hint） | partial | planner.py:126-143；commands_compiler.py:59-69 |
| C16 | 未知 feature 给 Reject（stderr JSON，退出 2） | covered | tests/test_plan_cli.py:260-263 |
| C17 | Engine.plan 与 wxg plan 同一契约 | partial | tests/test_engine.py:82-88；engine.py:77-113（缺 hint） |

### brief（契约属于 commands_compiler；纯函数归切片 14）

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C18 | brief 只读，返回 blind=true 的固定 15 键；Engine.brief 同源 | covered | tests/test_briefing.py:122-139；tests/test_plan_cli.py:230-253；tests/test_engine.py:90-99 |
| C19 | write_boundary = target_ids 对作用域节点展开（排序去重），含 work-seed 的 requirement | covered | tests/test_briefing.py:38-61；tests/test_plan_cli.py:246-249 |
| C20 | inputs 只取边界内节点的一跳依赖目标，且只认 depends/calls/reads/writes | covered | tests/test_briefing.py:84-120；briefing.py:28、95-100 |
| C21 | produces 由工单 kind 查表，未知 kind 为空 | covered | tests/test_briefing.py:141-168 |
| C22 | `--out` 写 JSON 文件（ensure_ascii=False/indent=2/末尾换行），stdout 只回 {written, work_item} | gap | commands_compiler.py:110-116；探针 `_probe_13.py` |
| C23 | 未知工单给 Reject 退出 2 | covered | tests/test_plan_cli.py:255-258 |
| C24 | `--out` 不可写时 OSError 经通用异常分支退出 2（文案前缀非 Reject） | gap | cli.py:88-90；探针 `_probe_13.py` |

### blind-check

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C25 | PASS 需 boundary/contract/dependencies 全 ok；locality 为 0-1 加权分 | covered | tests/test_blind.py:35-53；blind.py:81-107 |
| C26 | 越界节点、未声明依赖端点各自使 FAIL 并逐条列出 | covered | tests/test_blind.py:59-87；tests/test_plan_cli.py:294-321 |
| C27 | produces 只约束新建节点，更新边界内已有节点不重判 | covered | tests/test_blind.py:88-97 |
| C28 | 未知节点/边 kind、畸形条目使 contract.ok=false | partial | tests/test_blind.py:99-114（函数层自造 known 列表） |
| C29 | 产出文件缺失/不可解析/顶层非对象 → Reject 2 | partial | tests/test_plan_cli.py:323-334；探针 `_probe_13.py`（仅缺失有测试） |
| C30 | verdict=FAIL 时退出码仍为 0 | partial | tests/test_plan_cli.py:317-321（expect=0 隐含）；cli.py:94-113 |
| C31 | 检查时从库重算任务书，不用执行者手里的 brief | gap | commands_compiler.py:122 |
| C32 | 空产出判定 PASS、locality=1.0 | covered | tests/test_blind.py:128-131 |

### cycles

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C33 | 只分析作用域内、非 stale、component/port/pattern 之间的 depends 边 | partial | commands_compiler.py:143-168（测试只用 component+depends） |
| C34 | 输出 feature/node_count/edge_count/without/cycle_count/cycles[]；环带 members/shape/guidance/edges(evidence)/self_loops | partial | commands_compiler.py:181-188；cycles.py:256-284；tests/test_plan_cli.py:684-701 |
| C35 | 无环时 cycle_count=0、cycles=[] | covered | tests/test_plan_cli.py:821-835 |
| C36 | `--without` 做 what-if 移除并返回排序列表；格式错/端点不在设计层 Reject 2 | partial | tests/test_plan_cli.py:703-721；commands_compiler.py:170-179 |
| C37 | `--break-set` 按边数升序给最小断边集合，带 evidence 与 cost{lost_pairs,affected_count} | partial | tests/test_plan_cli.py:803-819；tests/test_cycles.py:57-132 |
| C38 | `--break-set`/`--advise` 不受 `--without` 影响（组合结果自相矛盾） | gap | commands_compiler.py:189-230；探针 `_probe_13.py` |
| C39 | `--advise` 分 preferred/acceptable/avoid，按 verdict→lost_count→id 排序 | covered | tests/test_plan_cli.py:782-801；tests/test_cycles.py:97-116 |
| C40 | 非自环边 >20 条时 truncated=true 且 break_sets=[]；每档最多 10 组，超出静默截断 | partial | cycles.py:24、50-55、73-79；tests/test_cycles.py:90-94；探针 |
| C41 | 自环单列成环，断边集合即自环；parent-child/sibling 由 id 前缀判断，guidance 随形态 | covered | tests/test_cycles.py:40-45、85-88、135-169 |
| C42 | truncated 键只在带 `--break-set`/`--advise` 时出现 | gap | commands_compiler.py:210、229-230 |

### patch / apply

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C43 | patch 规范成 {work_item,nodes[],edges[]}：节点按 id 保留首个、边去重排序 | partial | tests/test_reducer.py:28-56；commands_compiler.py:246-256 |
| C44 | patch 不校验 `--work` 是否存在，任意标签接受 | partial | tests/test_plan_cli.py:480-481；commands_compiler.py:246 |
| C45 | patch 的输入缺失/不可解析/非对象 → Reject 2；`--out` 不可写 → 2 | gap | commands_compiler.py:237-250 |
| C46 | apply 合并冲突或未知边端点 → ok=false、退出 1、不写库 | covered | tests/test_plan_cli.py:459-491；tests/test_reducer.py:82-122 |
| C47 | `--dry-run` 只合并校验：applied=false、written_*=0、不写库 | covered | tests/test_plan_cli.py:493-515 |
| C48 | 成功时先写节点再写边，返回 applied=true 与 written_* | covered | tests/test_plan_cli.py:414-457 |
| C49 | 中途写库校验失败不留半截（事务回滚） | gap | commands_compiler.py:284-287；cli.py:83-84；探针 `_probe_13.py` |
| C50 | apply 不要求 token/角色，不校验 target_ids 写边界 | partial | commands_compiler.py:259-295；SKILL.md:450（只承认绕过边界） |
| C51 | apply 不写 feature_nodes（除非补丁带 feature_id）、不追加 work_items.evidence_ids、不记 actor | gap | commands_compiler.py:284-294；graph.py:130-132；探针 |
| C52 | apply 透传补丁节点字段（origin/unmapped/feature_id 生效，stale 被清 0） | gap | commands_compiler.py:284-287；graph.py:106-119；探针 |
| C53 | apply 只比补丁之间的节点内容，覆盖库中已有节点静默 | gap | reducer.py:55-102 |
| C54 | `--patches` 为空/文件缺失/不可解析/非对象 → Reject 2 | partial | commands_compiler.py:262-276 |
| C55 | 退出码：0 成功或 dry-run 成功；1 合并失败；2 参数/写库校验失败 | partial | cli.py:100-102；tests/test_plan_cli.py:448-451、483-486 |

### impact

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C56 | `--changed` 输出反向可达 affected、正向 depends_on、最短跳数 direct/indirect | partial | tests/test_impact.py:42-116（纯函数全）；tests/test_plan_cli.py:360-379（CLI 只断言 affected/closed） |
| C57 | requirement 覆盖按无向连通判断，命中任意 requirement 即算覆盖；requirement 自身直接计入 | covered | tests/test_impact.py:79-102；impact.py:115-135 |
| C58 | closed=false 的节点列在 uncovered | covered | tests/test_impact.py:93-97；tests/test_plan_cli.py:360-379 |
| C59 | cross_feature 列出作用域外节点及其所属 feature | partial | tests/test_impact.py:104-116（CLI 未测） |
| C60 | 非依赖边不传播影响，但参与需求覆盖 | covered | tests/test_impact.py:80-83、118-121 |
| C61 | `--remove-edges` 输出 mode/removed[]/affected/requirements/uncovered/closed；lost_reachable 为断前减断后 | covered | tests/test_plan_cli.py:838-861；tests/test_impact.py:134-149 |
| C62 | `--remove-edges` 不校验端点：未知边 lost=[]、closed=true | gap | commands_compiler.py:315-324；探针 `_probe_13.py` |
| C63 | 同时给 `--changed` 与 `--remove-edges` 时 remove-edges 静默优先 | gap | commands_compiler.py:314-348；wxg_contract.py:599 |
| C64 | 不校验 `--changed` 节点是否存在，任意 id 原样返回 | covered | tests/test_plan_cli.py:735-739 |
| C65 | 两个 flag 都不给/`--changed` 空串/非数组 → Reject 2 | partial | commands_compiler.py:347-351；tests/test_plan_cli.py:381-385、741-744 |
| C66 | `--changed` 支持逗号、JSON 数组、@文件 | partial | jsonio.load_id_list；tests/test_plan_cli.py:735-739（@文件只探针） |
| C67 | impact 只读 | gap | commands_compiler.py:298-359（无快照断言） |

### conflicts

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C68 | 两两比较当前代 work_items 的 target_ids，重叠即冲突，返回固定结构 | covered | tests/test_conflicts.py:36-82；tests/test_plan_cli.py:387-411 |
| C69 | 图上尚无节点时模式重叠也算冲突 | covered | tests/test_conflicts.py:57-62 |
| C70 | 仅尾部 `*` 通配；嵌套前缀算重叠；单 feature 不与自己冲突；空集合 ok | covered | tests/test_conflicts.py:15-33、75-82 |
| C71 | `--features` 只查给定 feature，未知 feature → Reject 2 | gap | commands_compiler.py:369-375；探针 |
| C72 | 只看当前代 work_items，不过滤 status（已 passed 的边界仍参与） | gap | commands_compiler.py:376-379 |
| C73 | 检出冲突时退出码仍为 0 | partial | tests/test_plan_cli.py:394-399（expect=0）；SKILL.md:370 |

### 通用

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C74 | 参数错误统一 Reject：stdout 空、stderr {error}、退出 2；未捕获异常同 2 但文案为 TypeName: msg | partial | cli.py:85-90 |
| C75 | 状态库未初始化时不建库，直接退出 2 | covered | cli.py:65-70（跨切片证据 test_wxg.py） |

统计：75 条，covered 33 / partial 23 / gap 19。

## 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| features | read | workflow.py:25-34 |
| feature_nodes | read | workflow.py:104-109 |
| nodes | read | commands_compiler.py:28-32、48-51；cycles:145-152；impact:309-310 |
| nodes | write | commands_compiler.py:284-287（apply） |
| edges | read | commands_compiler.py:46-47、87-88、160-168、307-308 |
| edges | write | commands_compiler.py:286-287（apply） |
| edges.attrs_json.x_evidence | read | commands_compiler.py:160-168 |
| work_items（含 target_ids） | read | commands_compiler.py:73-104、376-379；workflow.py:112-123 |
| feature_nodes | write（条件） | graph.py:130-132（补丁节点带 feature_id 时） |
| `<root>/graph.sqlite` | read/连接 | db.py:458-465 |
| WXG_DB_URL | both | cli.py:55-56；engine.py:47-48 |
| `--out` brief/patch | write | commands_compiler.py:110-114、246-250 |
| `--result` 产出 | read | commands_compiler.py:123-129 |
| 默认根 `.why-exist` | read | cli.py:16（模块导入时按 cwd 计算） |

共享状态注意点：

- `os.environ["WXG_DB_URL"]` 是进程级改写（cli.py:55-56、engine.py:47-48），同一进程里之后所有连接都会跟着变，CLI 之外没有恢复。
- `DEFAULT_ROOT = Path.cwd() / ".why-exist"` 在导入时求值（cli.py:16）；同进程 cwd 变化不会重算。
- 切片内没有其它跨命令状态：`patch` 文件是事实上的操作日志（SKILL.md:450），没有独立日志表；apply 不往 work_items 写证据，所以“谁合并了什么”只能靠补丁文件本身。
- `--out` 的 brief/patch 都不建父目录、非原子写入；失败时可能留下半截文件（未验证）。

## 冗余

| 条目 | 信号 | 把握 |
|---|---|---|
| Engine.plan 与 cmd_plan 两份取数+过滤 | commands_compiler.py:23-70 vs engine.py:77-113，已漂移（Engine 缺 hint） | high |
| 通配匹配 6 份实现 | blind.py:21-25、briefing.py:56-59、conflicts.py:14-39、query.py:19-25、work.py:80-85、workflow.py:117-122 | high |
| 依赖边 kind 集合多处定义 | planner.py:32-35、briefing.py:28（被 impact.py:19 反向依赖）、gates.py:124、derive.py:23 | high |
| design 节点 kind 三元组重复 | planner.py:38 vs commands_compiler.py:156；hint 又用第三份 code kind 字面量（commands_compiler.py:64） | high |
| 编译器命令 re-export 兼容层无人使用 | commands_gates.py:33-44、commands_repo.py:708-719，而 wxg.py:108-118 直接从 commands_compiler 导入 | high |
| `--advise` 重复计算环与断边集合 | commands_compiler.py:180 已算，cycles.py:135、143 再算；带 `--break-set` 时枚举执行两次 | high |
| 纯函数返回值没人消费 | break_set_costs 的 affected_nodes（cycles.py:113）、minimal_break_sets 的 edge_count（cycles.py:49/55/78） | high |
| remove-edges 分支白算全部 feature 作用域 | commands_compiler.py:311-312 无条件构造，314-345 不用 | high |
| conflicts 每 feature 查两次 ensure_feature | commands_compiler.py:371-372 与 374-375 | high |
| plan 重复扫描 nodes 表 | commands_compiler.py:28-32、38-43、48-51，scope_ids 再读一遍（workflow.py:97） | medium |
| test_plan_cli.py 收纳非 plan 用例 | 865 行/39 用例，约 24 个属本片；up/derive/promote/gate 夹具与 test_wxg.py 重复 | high |
| plan 的 dangling.self_loop/duplicate 无断言 | 只测 unknown_endpoint（tests/test_planner.py:103-107） | medium |
| cycles 自行实现 _has_cycle | cycles.py:27-31 vs graph_algo.py:157-166 | medium |
| layer_count 与 layers 重复 | planner.py:134 | low |

## 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| planner.py | refactor_in_place | 契约清楚、13 条函数测试；先修空节点集崩溃，再把 code 层计数语义写进契约 | bottleneck 中文文案被测试按子串断言（tests/test_planner.py:85-97）与 SKILL.md:366 引用 |
| commands_compiler.py：plan/brief/blind-check | refactor_in_place | 薄壳；问题是与 Engine 重复、`--out` 无测试、OSError 分类没进契约 | plan 字段是文档承诺；hint 逻辑要同步删字面量 |
| commands_compiler.py：cycles | refactor_in_place | 必须修 `--without` 与 `--break-set/--advise` 的组合语义，并让 truncated/10 组上限显式化 | break_sets 嵌套形状被 SKILL.md:376、README.md:55 引用 |
| commands_compiler.py：patch | refactor_in_place | 20 行薄壳；缺 `--work` 校验与错误分支测试 | 补丁文件是“操作日志”，加校验会让离线出补丁失效 |
| commands_compiler.py：apply | freeze | 免 token/角色、绕过 target_ids、透传 origin/stale/unmapped/feature_id、不写证据、只查补丁间冲突——全部无测试，只有 SKILL.md:450 一句提及 | 收紧会打断现有补丁工作流；放松则继续绕开 upsert-node 的写入契约。先补测试与契约再动 |
| commands_compiler.py：impact/conflicts | refactor_in_place | 域逻辑在纯函数里且测试较足；壳层要补互斥、端点校验、status/世代口径 | impact 的 closed 口径改动会影响交付门预期；conflicts 加 status 过滤会让历史边界不再报警 |
| impact.py | keep | 纯函数、确定性、15 条测试覆盖闭包/跳数/断边/覆盖 | requirement_ids 由调用方传全图，“任意 requirement”语义要显式写住 |
| cycles.py:34-173（断边枚举与建议） | rewrite | 2^n 枚举 + 每档静默 10 组上限 + truncated 语义偏窄；重写成“按 SCC 求有界最小反馈边并显式报告不完整”更小更可测 | 返回条数/顺序会变：tests/test_cycles.py:62-88、tests/test_plan_cli.py:803-819 需改；break_sets 形状必须原样保留 |
| cycles.py:1-31,176-285（find_cycles/shape/guidance） | keep | SCC 展开、自环、形态与 guidance 都有测试且无未验证分支 | “SCC 内边全列”是保守选择，改成精确环会破 tests/test_cycles.py:26-32 |
| conflicts.py | keep | 80 行纯函数、12 条测试、无未验证分支 | 匹配规则是第 6 份拷贝；抽公共函数时不能改掉“精确模式非通配”语义 |

判定分布：keep 3、refactor_in_place 5、rewrite 1、freeze 1。

## 隐含需求（重写会静默丢掉的行为）

1. plan 排除 unmapped 后其边仍参与分析并变成 dangling.unknown_endpoint；默认扫描图显示 `edge_count=0`，噪声从节点数转移到悬空边。
2. plan 的 code 层不按 kind 过滤，requirement/use_case 计入 node_count、layers 与反链。
3. `plan --level design` 在空设计层直接 ValueError 退出 2（同一状态用 auto 却正常）。
4. excluded_unmapped 在排除 stale 之前统计；同时 unmapped+stale 的节点只进 unmapped 计数。
5. blind-check 检查时重算任务书，执行者手里的 brief 不是裁决依据。
6. 空产出算 PASS、locality=1.0；漏交与干净交付不可区分。
7. produces 是 briefing.PRODUCES 字面量；新增工单 kind 静默得到空 produces。
8. brief/patch 的 `--out` 覆盖写、非原子、不建父目录，失败按通用异常退出 2。
9. apply 免 token/角色、不查 target_ids、不追加 work_items.evidence_ids；唯一痕迹是补丁文件。
10. apply 透传 origin/stale/unmapped/feature_id：可伪造 origin=declared、把节点塞进任意 feature；stale 被清 0。
11. apply 只在补丁之间比冲突，覆盖库中已有节点是静默的。
12. impact `--remove-edges` 不校验端点，写错 id 得到 lost=[]、closed=true。
13. 同时给 `--changed` 与 `--remove-edges` 时后者优先，另一个被静默丢弃。
14. impact 的 closed/uncovered 用全图 requirement 判断，跨 feature 的 requirement 也算“有归属”。
15. conflicts 比较当前代全部 work_items 的 target_ids，不区分 status；历史边界继续算冲突。
16. `--without` 只影响 cycles[] 与 cycle_count；`--break-set/--advise` 用未移除的图重算。
17. minimal_break_sets 每档最多 10 组、静默丢弃；>20 条非自环边直接放弃枚举。
18. truncated 键只在带 flag 时存在，默认输出没有该键。
19. patch 不校验 `--work`，w1/w2 会成为 apply 冲突报告里的 a/b。
20. Engine.plan 与 wxg plan 不是同一实现：Engine 无 hint。

## 值得人判断的问题

1. **apply 的定位**：单一执行者的批量落库入口（文档口径），还是并行执行者的合并入口（命令名与 SKILL.md:372 的口径）？前者可继续免 token，后者必须补 target/claim/证据，否则 merge 模型等于没有写边界。
2. **plan 空设计层**：返回空计划还是报错？若返回空计划，parallelism/bottleneck 的语义要重定义（当前崩溃点正是这两项）。
3. **break_sets 的目标**：完整枚举（20 条边上不可行）还是“一组可执行建议”？若只给建议，应改成每 SCC 一组最小反馈边并在输出写清策略。
4. **blind-check 的裁决基准**：用执行者拿到的 brief 快照，还是当前库状态？现在是后者；是否给 brief 加 hash/version 并在 check 时比对？
5. **impact 的 closed 口径**：连到任意 requirement，还是连到本 feature 的 requirement？现在是前者，与 README/SKILL 的“意料之外的影响面”叙述不一致。
6. **conflicts 的 status 过滤**：排除 passed/withdrawn 工单会少报“重新打开同一区域”的并发风险；不排除则已交付区域永久冲突。
7. **Engine 的定位**：公开库 API（README.md:48）还是 CLI 薄包装？现在复制 plan 逻辑、缺 cycles/conflicts/apply，还 import 了 commands_compiler 的私有 `_brief_payload`。
8. **plan 的 dangling.self_loop/duplicate**：有消费者吗？没有就删掉以减少契约面；有就补断言。

## 证据与验证

- 测试子集：`python -m unittest tests.test_plan_cli` → 39 tests OK（约 50s）；`tests.test_planner tests.test_cycles tests.test_impact tests.test_conflicts tests.test_blind tests.test_briefing tests.test_reducer tests.test_engine` → 106 tests OK（约 12s）。`test_wxg.py` 不覆盖本片 8 条命令中的任何一条。
- 行为探针：`docs/audit/_probe_13.py`（退出码、--without 组合、apply 原子性/透传、brief --out、patch 不校验工单）、`_probe_13b.py`（plan 噪声、design 崩溃、break-set 阈值）、`_probe_13c.py`（stale 排除）。临时状态库在 `docs/audit/_probe_13_tmp*/`，未改源码。
- 探针关键结果：blind-check FAIL/impact closed=false/conflicts 有冲突均退出 0；apply 边校验失败退出 2 且节点未落库；apply 透传 origin=derived/unmapped=1/feature_id 生效、stale 被清 0；`plan --level design` 空设计层报 `ValueError: max() iterable argument is empty`；`--without` 后 cycle_count=0 但 break_sets/advice 仍按未移除图给出。
