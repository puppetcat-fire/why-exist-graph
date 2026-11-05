# 11 命令族：graph 域（7 条命令）

## 切片范围

| 文件 | 行数 | 职责 |
|---|---|---|
| scripts/whyexist/commands_graph.py | 208 | 7 条命令的 CLI 处理器：写图鉴权委托、target 边界、retract 级联、bite 落库、evidence 登记与列表；外加 prune_work_refs |

命令：`upsert-node`、`upsert-edge`、`bind`、`retract`、`bite`、`evidence-record`、`evidence-list`。

行数：任务给的是 187 行，磁盘实际 208 行（差 21 行）。文件里没有兼容层残留，全部是有效代码；但它是**唯一**的图写入命令层——`graph.py` 的写原语（upsert_node/upsert_edge/bind_node）由它调用，契约归 `06-graph-core`，本切片只记录命令层的选择带来的可观察差异。与其它切片的交界：

- `scripts/whyexist/graph.py`：写原语的校验与覆盖/合并语义，`06-graph-core.md:43-57` 已逐条审计，本切片不重复，只引用。
- `scripts/whyexist/commands_repo.py:683-693`：把本切片 7 个命令名 + `prune_work_refs` 又 re-export 一遍；该文件归 `08-cmd-repo`。
- `scripts/wxg_contract.py:262` 的 `TOKEN_COMMANDS` 与 `:454-493` 的命令声明：归 `03-contract-rules` / `02-contract-commands`；本切片只把「它是否真的在拦 token」当作契约证据。

## 公开面

CLI 统一在 `cli.py:109-113` 输出 `json.dumps(..., ensure_ascii=False, indent=2)`；Reject/异常在 `cli.py:85-90` 写 stderr `{"error": ...}` 并返回 2。

| 入口 | kind | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg upsert-node` | cli | commands_graph.py:20 | `--token` + `--data`（JSON 或 @文件）：`id`/`kind` 必填，可带 `name/repo/path/symbol/line_*/attrs/origin/unmapped/feature_id` | `{"action":"insert\|update","id":...}` | 写 `nodes`（同 id 整条覆盖）；写 token 所属 feature 的 `feature_nodes`；`payload.feature_id` 再写一条；节点 id 追加进工单 `evidence_ids` | 0 / 2（缺 token、角色、越界、JSON 或字段非法；argparse 缺必填也是 2） |
| `wxg upsert-edge` | cli | commands_graph.py:36 | `--token` + `--data`：`src/dst/kind` 必填，可带 `id/evidence_path/evidence_line/unmapped/attrs` | `{"action":"upsert","id":...}` | 写 `edges`；两端 id 追加进工单 `evidence_ids`；不写 `feature_nodes` | 0 / 2 |
| `wxg bind` | cli | commands_graph.py:50 | `--token` + `--node-id`（parameter\|argument\|assertion）+ `--bind-to` + 可选 `--edge-kind`（asserts\|has_argument\|has_input） | `{"action":"bind","id":...}` | 写 `edges`；两端 id 追加进工单 `evidence_ids` | 0 / 2 |
| `wxg retract` | cli | commands_graph.py:79 | `--token` + `--node-ids` 与/或 `--edge-ids`（逗号/JSON/@文件；都可省略） | `{"nodes_deleted","edges_deleted","bites_deleted","work_refs_pruned"}` | 硬删 `nodes/edges/bites/feature_nodes`；从所有非 audit 工单的 `target_ids/evidence_ids` 剔除被删节点 id（保留 `*` 通配）；不改证据、裁决历史、条件 | 0（含空参数、含不存在的 id）/ 2 |
| `wxg bite` | cli | commands_graph.py:109 | `--node` + `--verdict` + 可选 `--reason/--feature/--actor`（或 `WXG_ACTOR`） | `{"node","verdict","feature","generation","phase","actor"}` | INSERT `bites` 一行；改写 `nodes.attrs_json` 的 `bite`/`x_bite_reason`；`--feature` 时写 `feature_nodes`、取当前代与阶段；`UNMAPPED` 把 `nodes.unmapped` 置 1 | 0 / 2 |
| `wxg evidence-record` | cli | commands_graph.py:144 | `--feature` + `--name` + `--command`；可选 `--exit-code/--artifact/--work/--actor` | `{"id":"ev:<uuid>","feature_id","generation","work_item_id","name","exit_code","artifact","sha256","actor"}` | 写 `evidence` 一行（artifact 存绝对路径 + SHA-256）；不写工单 `evidence_ids`、不写条件 | 0 / 2 |
| `wxg evidence-list` | cli | commands_graph.py:198 | `--feature` | `{"feature_id", "evidence":[SELECT * 行]}` | 无（只读） | 0 / 2 |
| `cmd_upsert_node` 等 7 个处理器 | function | wxg.py:147-156 | `conn` + argparse 命名空间 | Python dict（与 stdout 同构） | 同 CLI；不自行 commit | 不适用 |
| `prune_work_refs` | function | commands_graph.py:58 | `conn` + `removed_ids: set[str]` | `int`（改写的工单数） | 遍历全部 `work_items`（跳 audit）改写 JSON；无 token/边界，任何持连接者可调 | 不适用 |
| `_require_write` | function | commands_feature.py:717 | `conn` + `args` + 命令名 | claimed 工单 dict | 无写入；失败抛 `Reject` | 不适用 |
| 表 `nodes` / `edges` / `bites` / `feature_nodes` / `evidence` / `work_items` | table | db.py:30,44,114,95,100,74 | 见上 | 见上 | 本切片是 `nodes`/`bites` 的唯一 CLI 写入口、`retract` 是唯一 `DELETE FROM nodes` 的入口（`doctor --fix` 另算，commands_misc.py:563-569） | 不适用 |
| 文件 `<root>/graph.sqlite`（+ `-wal/-shm`） | file | db.py:454-465 | `--root` 或默认 `./.why-exist` | SQLite 库 | connect 会 mkdir 并建库；CLI 在连接前拦未初始化库（cli.py:66-70） | 不适用 |
| 文件 证据产物 | file | commands_graph.py:161-166 | `--artifact` 路径 | 绝对路径 + SHA-256 落库 | 只读该文件，不复制 | 不适用 |
| env `WXG_ACTOR` | file | workflow.py:12-20 | 缺 `--actor` 时读取 | actor 字符串（1-80 非空白） | 无 | 不适用 |
| env `WXG_DB_URL` / 全局 `--db-url` | file | cli.py:55-56; db.py:425-438 | mysql/pg/sqlite | 后端选择 | `--db-url` 写进 `os.environ`，同进程后续命令继承 | 不适用 |
| stdout / stderr | file | cli.py:85-90,109-113 | 命令结果 | 成功 stdout 缩进 JSON；失败 stderr `{"error"}` | 无 | 0 / 2；argparse 形态是 usage 文本 |

## 契约表

口径：covered = 有测试直接断言；partial = 只覆盖部分分支/路径；gap = 代码里有、无测试。

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C1 | 4 条写命令先过 `_require_write`：token 有效、工单 claimed、角色包含该命令，否则 Reject 2 | partial | commands_graph.py:21,37,51,80；commands_feature.py:717-720；work.py:63-77；tests/test_wxg.py:465-479 | token/越界对 upsert-node 有断言；bind/upsert-edge/retract 的越界、无效 token、角色拒绝无测试（探针确认） |
| C2 | target 边界：upsert-node 查节点、upsert-edge 查 src+dst、bind 查两端、retract 查 node_ids 与显式 edge 端点 | partial | commands_graph.py:29,44,52,83,97；work.py:88-100；tests/test_wxg.py:473-479 | 只有 upsert-node 越界被断言 |
| C3 | upsert-node 拒绝缺 id 的 `--data`，可读 Reject 2 | covered | commands_graph.py:23-28；tests/test_wxg.py:812-820 | 只测 `{}` 与缺 id |
| C4 | 图写入一律拒绝 `attrs.bite`（bite 唯一写入口） | covered | graph.py:26-29；commands_graph.py:30；tests/test_wxg.py:848-859；SKILL.md:298 | `x_` 前缀放行，`x_bite_reason` 可伪造；gate 不采信 attrs.bite |
| C5 | upsert-node 的 kind/id/attrs 校验（NODE_KINDS、前缀、字符集、键白名单、类型） | partial | graph.py:13-51；tests/test_wxg.py:1430-1441；tests/test_package_units.py:153-175 | CLI 层只测了 construction 的 bool；其余是包级单测 |
| C6 | 同 id 再 upsert 是整条覆盖：attrs 全替换、name/repo/path/origin 缺省沿用、unmapped 按 payload 重写（缺省清 0）、stale 强制清 0 | gap | graph.py:97-119；commands_graph.py:30；06-graph-core.md:49 | CLI 从不传 merge_attrs，与 import-file 的 `merge_attrs=True` 相反；探针 P1/P2 |
| C7 | upsert-node 自动写 token feature 的 `feature_nodes`，`payload.feature_id` 再写一条（不校验 feature 存在） | gap | commands_graph.py:31；graph.py:130-132；06-graph-core.md:51 | 探针 S8：一次 upsert 写两个 feature；无 CLI 断言 |
| C8 | upsert-edge 必填校验、端点存在、applies/maps_to 方向校验 | partial | graph.py:140-167；tests/test_wxg.py:1246-1275,1847-1864 | 两个方向校验有测试；未知 kind、端点不存在、字段缺失无测试 |
| C9 | 边 id 缺省 `edge:{kind}:{src}:{dst}`；显式 id 整行覆盖；改 kind = 新边 + 旧边残留 | gap | graph.py:136-137,168；06-graph-core.md:55 | 探针 P5 |
| C10 | bind 只收 parameter/argument/assertion、目标存在、默认 kind 来自 BIND_EDGE_KIND、方向随 kind | partial | graph.py:190-213；tests/test_wxg.py:229-231,608-630；06-graph-core.md:56 | 只有 happy path |
| C11 | `--edge-kind` 覆盖默认映射且不与节点 kind 交叉校验；bind_to 的 kind 也不校验 | gap | graph.py:198-206；wxg_contract.py:462；06-graph-core.md:57 | 探针 P7：`use_case -asserts-> parameter` |
| C12 | 图写入把节点 id 去重追加进工单 `evidence_ids`；work-finish 校验其在 target_ids 内 | gap | commands_graph.py:32,46,54；work.py:103-110；commands_feature.py:566-570 | change-diff 与 work-finish 边界的真实数据源；无断言 |
| C13 | retract 硬删 node + 触及它的 edge + 它的 bites + feature_nodes，并从非 audit 工单引用中剔除 | partial | commands_graph.py:86-106；tests/test_wxg.py:371-389；SKILL.md:214；wxg_contract.py:141 | 测试节点没有边、只有一个 feature 的工单；edges_deleted 与跨 feature 裁剪无断言 |
| C14 | retract 的边界只到节点：删节点连带删 target 外的边；跨 feature/代工单引用被裁剪 | gap | commands_graph.py:86-89,100,63-75 | 探针 S2/S3 |
| C15 | 不存在的节点也计 `nodes_deleted`；不存在的 edge 静默跳过；空参数成功返回全 0 | gap | commands_graph.py:85-99 | 探针：target=`*` 时 ghost id 返回 1 |
| C16 | 一次 CLI 调用一个事务：handler 返回后统一 commit，异常路径不 commit（SQLite 回滚） | gap | cli.py:71-84,85-93；db.py:459-465 | 探针 S4 实测回滚；无测试；MySQL/PG 只 close 不显式 rollback |
| C17 | bite 的 verdict 必须在 BITE_VERDICTS（argparse 与 handler 双校验） | covered | commands_graph.py:110-111；wxg_contract.py:121,475；tests/test_wxg.py:308-311 | 断言的是 argparse 层 |
| C18 | bite 必须记录 actor（`--actor`/`WXG_ACTOR`，1-80 非空白）；actor 不做身份校验 | partial | commands_graph.py:112；workflow.py:12-20；tests/test_wxg.py:527-549 | 缺 actor 只测了 claim/judge；bite 分支靠探针 |
| C19 | 每次 bite 追加一行 bites（feature/generation/phase/actor/时间），旧行不改 | covered | commands_graph.py:118-127；tests/test_wxg.py:313-322,1093-1100 | 322 断言两次判决按序；1096-1100 断言 phase/generation |
| C20 | bite 把最新判决投影到 `attrs.bite` / `x_bite_reason`，保留其余 attrs | gap | commands_graph.py:128-133；wxg_contract.py:131 | 投影仅供展示；错了门禁也发现不了 |
| C21 | `bite --feature` 不走 target 边界，直接写 feature_nodes 扩作用域；无 feature 时 generation/phase 为 NULL | gap | commands_graph.py:118-122,134-141 | 探针 S6：scope_size 1→2 |
| C22 | `UNMAPPED` 把 nodes.unmapped 置 1，后续 KEEP 不清（只有 upsert-node 能清） | gap | commands_graph.py:132-133；commands_compiler.py:28-37；gates.py:166,222 | 探针 P8；影响 plan 默认排除与 conformance 启发式 |
| C23 | evidence-record 校验 feature 存在、name/command 非空、actor、`--work` 属于该 feature | partial | commands_graph.py:145-158；workflow.py:30-34；tests/test_wxg.py:569-583,792-801 | 空 name / feature 不存在 / 缺 actor 无测试 |
| C24 | evidence 的 generation 默认当前代；`--work` 取工单代（可写旧代）；BehaviorPassed 只采信同代 | covered | commands_graph.py:149-158；tests/test_wxg.py:792-810；evidence.py:19-35；commands_feature.py:637-639 | |
| C25 | `--artifact` 必须是存在文件；存绝对路径 + SHA-256；产物删除/hash 变化 → gate FAIL、doctor 报错 | partial | commands_graph.py:159-166；evidence.py:19-35；tests/test_wxg.py:569-587,589-606 | `--artifact` 不存在的 Reject 分支无测试 |
| C26 | `--exit-code` 任意值都落库；采信只认 0；doctor 对非 0 只报提示 | gap | commands_graph.py:178；evidence.py:19-24；commands_misc.py:440-441 | 无测试记录非 0（探针 P14 记录成功） |
| C27 | evidence-list 返回全部代 evidence 行（SELECT *），按 created_at,id 排序，无代/工单过滤 | partial | commands_graph.py:198-206；tests/test_wxg.py:581-582 | 只断言 1 条；跨代、列集合、排序无断言；同秒记录次序不稳 |
| C28 | 成功 stdout 缩进 JSON + 0；Reject/异常 stderr `{"error"}` + 2；argparse 缺参/非法 choices 也 2 | partial | cli.py:85-90,109-113；tests/test_wxg.py:61-83 | 夹具默认 expect=0 隐含成功路径；argparse 形态只有探针 |

统计：28 条 —— covered 5、partial 11、gap 12。

## 状态与共享状态

| 目标 | 读写 | 位置 |
|---|---|---|
| graph.sqlite:nodes | both | commands_graph.py:30, 91, 113, 128-133 |
| graph.sqlite:edges | both | commands_graph.py:45, 53, 86-88, 95-98 |
| graph.sqlite:bites | both | commands_graph.py:90, 123-127 |
| graph.sqlite:feature_nodes | both | commands_graph.py:31, 92, 122 |
| graph.sqlite:evidence | both | commands_graph.py:168-184, 200-205 |
| graph.sqlite:work_items | both | commands_graph.py:32, 46, 54, 63-75 |
| graph.sqlite:features / conditions | read | commands_graph.py:119,121,145,199（ensure_feature / current_phase） |
| graph.sqlite:meta | read | db.py:468-483（每个命令入口 ensure_db） |
| file `<root>/graph.sqlite` | both | db.py:454-465；cli.py:66-70 |
| file 证据产物 | read | commands_graph.py:161-166；evidence.py:11-16 |
| env `WXG_ACTOR` | read | workflow.py:12-20 |
| env `WXG_DB_URL` | both | cli.py:55-56（写）；db.py:425-438（读） |
| cwd `./.why-exist` | read | cli.py:16,53 |

跨命令共享状态与隐式全局：

1. `DEFAULT_ROOT` 在**模块导入时**用 `Path.cwd()/.why-exist` 算死（cli.py:16）；之后 `chdir` 不会改变默认根。
2. `--db-url` 会写 `os.environ["WXG_DB_URL"]`（cli.py:55-56），进程内后续所有命令（包括同进程的库调用）都被静默切后端。
3. `feature_nodes` 是作用域的唯一存储：`bite --feature` 与 `upsert-node` 都能往里加行，`retract` 能删；gate/coverage/plan 的输入集合因此可被咬合改变。
4. `work_items.evidence_ids` 是「工单写过哪些节点」的隐式台账，图写入追加、retract 裁剪、doctor 校验，但没有任何命令直接展示它。
5. `nodes.unmapped` 有三个写点（导入器、bite UNMAPPED、upsert payload），且 bite 的写法不可逆。
6. 事务边界只在 `cli.main`（一次调用一个事务，cli.py:71-84）；handler 自己从不 commit/rollback。`prune_work_refs` 作为库函数被调用时没有事务保护。

## 冗余

| 条目 | 信号 | 把握 |
|---|---|---|
| `TOKEN_COMMANDS` 与真实拦截 | 零消费常量（wxg_contract.py:262）；只列 6 条，`token=True` 有 9 条（漏 import-repo/derive/promote）；本切片拦 token 的是 `_require_write` | high |
| token+role 两套实现 | `_require_write`（commands_feature.py:717-720）只服务本切片；commands_repo.py:193-194,298-299,470-471,543-544 四处内联 require_token+require_role | high |
| `feature_nodes` 双向写入 | commands_graph.py:31 与 graph.py:130-132 各写一次，一次命令可能写两个 feature | high |
| 工单引用裁剪两份 | `prune_work_refs`（commands_graph.py:58-76）与 doctor --fix 内联循环（commands_misc.py:571-586）同构、判据已分叉 | high |
| 命令 facade 两套 | wxg.py:147-156 与 commands_repo.py:683-693 重复导出同样的 7 个命令 + prune_work_refs | high |
| 「需要 token」声明三处 | COMMANDS.token（wxg_contract.py:454-470）、WRITE_MODES（:662-668）、handler 实际鉴权；verify 只查 WRITE_MODES 存在 | high |
| 通配匹配 8 份 | work.py:80-100、workflow.py:116-121、commands_graph.py:68、commands_misc.py:390、query.py:21、blind.py:23、briefing.py:57、conflicts.py:16 | medium |
| `upsert_node` 两种语义 | `merge_attrs` 开关（graph.py:85,97-105）：CLI/declare/derive/promote 覆盖，import-* 合并 | medium |
| evidence 列定义三份 | db.py:100-113（SQLite）、db.py:235-247（MySQL）、PG 复用 SCHEMA_SQL（db.py:289）；而 evidence-list 直接 `SELECT *` | medium |
| bite 判决双重校验 | argparse choices（wxg_contract.py:475）+ handler 检查（commands_graph.py:110-111） | low |

## 分区判定

| 模块/单元 | 判定 | 理由 | 风险 |
|---|---|---|---|
| commands_graph.py:20-55（upsert-node/upsert-edge/bind 处理器） | refactor_in_place | 编排很薄：校验字段 → require_targets → 调 graph 原语 → 追加 evidence_ids；输出与错误可观察。问题在调用参数（`merge_attrs=False`、payload 直通）和鉴权来源，不在流程 | 改覆盖/合并会立刻改变导入节点与手写 attrs 的存亡（06 C7/C8）；给 bind 补 kind 校验会拒掉现存图库；先补 C6/C9/C11/C12 测试 |
| commands_graph.py:58-106（prune_work_refs + cmd_retract） | rewrite | 行为简单但当前有三个可观察错误：删节点连带删 target 外的边、跨 feature 静默裁剪、不存在的节点也计 1。适合按「校验 → 收集级联集 → 删除 → 重建引用 → 真实计数」重写 | 四字段返回形状被 SKILL.md:168 与代理流程依赖；doctor --fix 复制了裁剪逻辑，重写后必须收敛；role 矩阵（只有 scan/observe 能 retract）是现行绕过方式 |
| commands_graph.py:109-141（cmd_bite） | refactor_in_place | 核心契约清楚且有测试（判决集、actor、历史追加、phase/generation），gate/coverage 都在读产出；缺的是 target 边界、`--feature` 扩作用域、unmapped 粘滞三处补丁级问题 | 加 token/边界会改掉「任何人可咬」的现有工作流（SKILL.md:53,357）；清 unmapped 或停写 feature_nodes 会改变 plan/conformance/coverage 的输入——本切片最容易被「顺手修」改坏门禁的地方 |
| commands_graph.py:144-206（evidence-record/list） | refactor_in_place | 写一条记录 + 列一张表，边界清楚；缺 exit_code/artifact 组合校验与显式列清单 | evidence 列被 doctor/gate/export 读，list 又被外部脚本当 JSON API；改列会静默破坏消费方；`--work` 继承旧代的语义必须保留 |
| commands_graph.py:11 + commands_feature.py:717-720（鉴权依赖） | refactor_in_place | 图写入不该依赖 feature 模块私有函数；鉴权应下沉 work.py，并与 commands_repo 的内联实现合并成单一入口 | `_require_write/require_token/require_role` 都在 wxg.py 的 re-export 面（wxg.py:83-93,120）；移动会动包级 API 与 import 顺序 |
| commands_repo.py:683-693（本切片命令的兼容 re-export） | freeze | 不是本切片实现，但把 7 个命令名复制了第二份；仓内无消费者，删除属包级 API 变更，先冻结、盘点外部 import 后再删 | 冻结期间两套 import 路径并存，新代码可能继续走 compat；删除时外部脚本会 ImportError |

## 隐含需求（重写会静默丢掉）

1. `upsert-node` 的 attrs 是整体替换：设计角色 upsert 一次、不带原来的键，`duty`/`x_note` 就消失。SKILL.md:400 只讲了「用不含 construction 的 upsert 清标记」。
2. `upsert-node` 把 `unmapped` 按 payload 重写（缺省清 0）、`stale` 强制清 0：一次手工 upsert 就让节点回到 plan/conformance 的默认集合。
3. `upsert-node` 同时写 token feature 与 `payload.feature_id` 的 `feature_nodes`，且不校验后者存在——一条命令跨两个 feature 扩作用域的唯一入口。
4. `upsert-edge` 的 id 由 kind 派生：改 kind 不是改边，是新边 + 旧边残留；同一对端点可并存多条不同 kind 的边。
5. `bind --edge-kind` 与节点 kind、`bind_to` 的 kind 都不交叉校验；`asserts` 可以挂到 `use_case→parameter`。
6. 图写入追加的 `work_items.evidence_ids` 是 change-diff 与 work-finish 边界的真实数据源；retract 会把它裁掉，等于抹掉「这张单写过哪些节点」。
7. `retract` 是硬删除，无软删/撤销标记；被删 id 从工单 target 移除后，同一工单再次提交不会报错。
8. `retract` 的计数不可信：不存在的节点计 1，不存在的边静默 0；调用方无法区分「删了」和「本来就没有」。
9. `retract` 只删节点关联的边和 bite；外部悬空边/悬空 bite 靠 `doctor --fix` 兜底（契约写在 wxg_contract.py:141）。
10. `bite` 无 token、无 target 边界：唯一没有 claim 门槛的图写入口；写 `bites` + `nodes.attrs_json`，还能借 `--feature` 改 feature 作用域。
11. `bite` 不传 `--feature` 时 `feature_id/generation/phase` 全 NULL：不进 coverage 分阶段统计，但 `attrs.bite` 仍被改写，看起来像「咬过了」。
12. `bite UNMAPPED` 把 `nodes.unmapped` 置 1 且不可逆，于是「结构性漂移」判决会反过来改变 plan 的节点集合与 conformance 的启发式解析。
13. `bite` 的 actor 是自由文本：不校验身份、不与 roles/工单关联；「审计独立性」只比较字符串。
14. `evidence-record` 允许 exit_code 非 0 落库；只有采信侧过滤 0，doctor 只报提示——「失败证据」是合法记录。
15. `evidence-record --artifact` 只校验存在且是文件，不校验路径是否在仓/项目内，也不阻止事后 hash 变化（靠 doctor/gate）。
16. `evidence-record --work` 可以把证据写进旧 generation（补历史证据的唯一路径）。
17. `evidence-list` 返回 `SELECT *` 原始行：列名与集合就是 CLI 契约，且不按代过滤。
18. 默认 root 在 import 时固定、`--db-url` 改进程环境变量（cli.py:16,55-56）。

## 值得人判断的问题

1. **retract 的边界承诺**：节点级 target 就够，还是边/工单引用也受约束？「删节点连带删 target 外的边、跨 feature 裁引用」是设计还是 bug——这决定它是「补测试」还是「重写」。
2. **upsert-node 的 attrs 覆盖**是契约还是历史选择？`import-file` 用 merge，CLI 用 replace；要不要显式化成 `--merge/--replace`，还是统一合并（SKILL.md:400 的清标记依赖覆盖）。
3. **bite 该不该也要求 claim_token + target 边界**？I5（SKILL.md:327）说图内容写入必须有边界，而 bite 是唯一例外且能扩 feature 作用域。
4. **`nodes.unmapped` 的权威来源**是谁：导入器（I7）、`bite(UNMAPPED)`、upsert payload 三个写点，目前没有单一规则。
5. **retract 的计数**要不要修成真实删除数、不存在的 id 报错？现在调用方会把 `nodes_deleted=1` 当成功依据。
6. **跨后端事务**：MySQL/PG wrapper 在 Reject 后只 close 不 rollback，是否显式 rollback 并补测试？
7. **evidence 的 exit_code 语义**：允许任意值落库、只采信 0，是有意「留失败证据」还是漏洞？要不要约束 `--artifact` 与 `--exit-code` 的组合？
8. **`TOKEN_COMMANDS` 与 commands_repo 的 re-export** 要不要删？两者都是包级可 import 名，删前需盘点外部使用者。

## 探针与测试记录

- `docs/audit/_probe_11.py`：P1-P16。覆盖 upsert 覆盖语义、unmapped/stale 重置、feature_nodes 归属、edge id、bind 越界 kind、bite 历史/粘滞/NULL 代、evidence 的 artifact 与 exit_code、WXG_ACTOR。
- `docs/audit/_probe_11c.py`：S1-S8。覆盖角色矩阵（scan 能 upsert-node/retract、model-architecture 能 upsert-edge 不能 retract、scan 不能 upsert-edge）、retract 级联与跨 feature 裁剪、target 外边被连带删除、中途失败回滚、显式 edge id、bite 扩作用域。两个探针都只用临时状态库，不写项目文件。
- 测试子集实跑（11 项，全部 OK）：`test_role_and_token_boundaries`、`test_retract_cleans_bites_and_work_refs`、`test_evidence_record_and_doctor_artifact`、`test_bite_verdicts_are_validated_and_visible_to_gate`、`test_bite_records_phase_and_generation`、`test_upsert_rejects_attrs_bite`、`test_upsert_missing_id_readable_error`、`test_evidence_is_generation_scoped`、`test_gate_counts_latest_bite_per_node_only`、`test_applies_edge_requires_design_element_to_pattern`、`test_construction_attr_must_be_bool`。（pwsh 把 unittest 的 stderr 进度行当错误，命令整体退出码为 1；unittest 自身输出 `Ran 11 tests ... OK`。）
- 覆盖密度（按 tests/*.py 扫描测试方法，含经 helper 间接调用）：upsert-node 39、upsert-edge 24（多在 plan/engine 测试里当夹具）、bind 3、retract 1、bite 10、evidence-record 7、evidence-list 1。bind/retract/evidence-list 都只有 happy path 或 1 条断言。
