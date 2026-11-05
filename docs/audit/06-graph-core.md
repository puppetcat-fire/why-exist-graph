# 06 图模型与图算法（graph core）审计

审计对象：`scripts/whyexist/engine.py`（151 行）、`scripts/whyexist/graph.py`（215 行）、`scripts/whyexist/graph_algo.py`（406 行），合计 772 行。

本次只读源码、不修改实现；行为探针在 `docs/audit/_probe_06.py`（临时目录 + 内存 SQLite），可复现下面标注「探针」的结论。测试子集 `python -m unittest tests.test_graph_algo tests.test_engine -v` 实跑 37 项全通过（30 项图算法 + 7 项 Engine）。

## 1. 切片范围

| 模块 | 行数 | 职责 | 与其他切片的关系 |
|---|---|---|---|
| `scripts/whyexist/engine.py` | 151 | `Engine` 库门面：把状态库连接接到 `plan/brief/blind_check/gate/impact`，自身不做判定 | 依赖 `planner/briefing/blind/impact`（纯函数）与 `commands_compiler/_brief_payload`、`commands_gates/cmd_gate`（命令层） |
| `scripts/whyexist/graph.py` | 215 | 节点/边/绑定的写入校验与 upsert，edge id 生成 | 被 9 个包内模块调用（`commands_feature/gates/graph/compiler/misc/repo`、`gates.py`、`importer.py`、`query.py`）以及 `wxg.py` 的 re-export |
| `scripts/whyexist/graph_algo.py` | 406 | 纯图算法：归一化、SCC、拓扑分层、最大反链、传递可达、`analyze` | 被 `planner.py`、`cycles.py`、`impact.py` 与包级 `__init__.py` 引用 |

**先修正一个前提**：`engine.py` 不是状态机。8 条件之间的迁移只发生在 `cmd_work_judge`（`scripts/whyexist/commands_feature.py:636-660` → `workflow.set_condition/recompute_ready`，`scripts/whyexist/workflow.py:63-78`）和 `feature-declare` 的 Accepted（`scripts/whyexist/commands_feature.py:122-126`）。`Engine.gate` 只读条件表（`scripts/whyexist/commands_gates.py:159-247`）。本切片没有"必须冻结的状态机"，只有"读取状态的门面 + 写入状态的图操作 + 纯算法"。

## 2. 公开面

CLI 结果统一 `json.dumps(..., ensure_ascii=False, indent=2)` 写 stdout；`Reject` 与后端异常写 `{"error": ...}` 到 stderr 并返回 2（`scripts/whyexist/cli.py:85-113`）。

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg upsert-node` | CLI | `scripts/whyexist/commands_graph.py:20` | `--token` + `--data`（含字符串 `id`、`kind`，可带 `name/repo/path/symbol/line_*/attrs/origin/unmapped/feature_id`） | `{"action":"insert\|update","id":...}` | 写 `nodes`；`payload.feature_id` 存在时写 `feature_nodes`（命令层 `commands_graph.py:31` 再写一次）；节点 id 追加进当前工单 `evidence_ids`；`stale` 清 0 | 0 / 2 |
| `wxg upsert-edge` | CLI | `scripts/whyexist/commands_graph.py:36` | `--token` + `--data`（`src/dst/kind`，可带 `id/evidence_*/unmapped/attrs`） | `{"action":"upsert","id":...}` | 写 `edges`；两端 id 追加进工单 `evidence_ids` | 0 / 2 |
| `wxg bind` | CLI | `scripts/whyexist/commands_graph.py:50` | `--node-id`（parameter/argument/assertion）、`--bind-to`、可选 `--edge-kind` | `{"action":"bind","id":...}` | 写 `edges`；两端 id 追加进工单 `evidence_ids` | 0 / 2 |
| `wxg plan` | CLI | `scripts/whyexist/commands_compiler.py:23` | `--feature`、`--level auto\|design\|code`、`--include-unmapped` | `level/node_count/edge_count/acyclic/cyclic_components/layers/layer_count/max_antichain/parallelism/bottleneck/dangling/excluded_unmapped/excluded_stale`，code 层无代码节点时多 `hint` | 只读 | 0 / 2 |
| `wxg cycles` | CLI | `scripts/whyexist/commands_compiler.py:140` | `--feature`、`--without`、`--break-set`、`--advise` | `cycles[{members,shape,guidance,edges,self_loops}]`，可选 `break_sets`/`advice`/`truncated` | 只读 | 0 / 2 |
| `wxg impact` | CLI | `scripts/whyexist/commands_compiler.py:298` | `--changed` 或 `--remove-edges` | 闭包字段 `affected/direct/indirect/cross_feature/depends_on/requirements/uncovered/closed`；remove-edges 模式换一组字段 | 只读 | 0 / 2 |
| `whyexist.Engine` | 库 API | `scripts/whyexist/engine.py:33` | `Engine(root, db_url=None)`；方法 `plan/brief/blind_check/gate/impact` | 同 CLI 命令的字典（gate 为完整 `cmd_gate` 输出） | 首次 `connect` 建 SQLite 文件；`db_url` 写进程级 `WXG_DB_URL`；import 时改 `sys.path` | 无；失败抛 `Reject` |
| `whyexist.graph` 公开函数 | 库 API | `scripts/whyexist/graph.py:85` | conn + payload；`bind_node/get_node/find_repo/edge_id/check_*` | `{action,id}` / dict / None / str；校验失败抛 `Reject` | 写 `nodes/edges/feature_nodes`，读 `nodes/repos` | — |
| `whyexist.graph_algo.*` | 库 API | `scripts/whyexist/graph_algo.py:57` | `nodes: list[str]`、`edges: list[tuple[str,str]]`；`reachable` 另有 `start/reverse` | 见函数契约；有环抛 `CyclicGraph` | 无 | 无 |
| `whyexist` 包级导出 | 库 API | `scripts/whyexist/__init__.py:22` | `analyze/strongly_connected_components/topological_layers/max_antichain/reachable/transitive_reachable/CyclicGraph/GraphAnalysis/Engine` | 同上 | 加载 blind/briefing/engine/planner，`contract.py` 改 `sys.path` | 无 |
| 表 `nodes` / `edges` / `feature_nodes` | 数据表 | `scripts/whyexist/db.py:30` | upsert 语句；`edges` 无外键 | `nodes` 12 列、`edges` 8 列、`feature_nodes` 复合主键 | 读写见第 3 节 | — |
| 表 `repos` | 数据表 | `scripts/whyexist/graph.py:56` | `repo-add` 写；`find_repo` 读 | `id/path/language/created_at` | 本切片只读 | — |
| `<root>/graph.sqlite`（+ `-wal/-shm`） | 文件 | `scripts/whyexist/db.py:458` | `connect(root)` | SQLite 库文件 | 目录不存在则 `mkdir(parents=True)`；连接即建文件，WAL 产生 `-wal/-shm` | — |

## 3. 契约与证据

状态口径：covered = 有测试直接断言；partial = 测试只覆盖部分分支或只间接覆盖；gap = 代码里有行为、无测试。

| ID | 可观察承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C1 | 节点 `kind` 必须在 `NODE_KINDS` 内，否则 `Reject`（退出码 2） | `scripts/whyexist/graph.py:13-15`；`tests/test_package_units.py:153-158` | covered | 边 `kind` 校验另见 C2 |
| C2 | 边 `kind` 必须在 `EDGE_KINDS` 内，`src/dst/kind` 必填 | `scripts/whyexist/graph.py:140-147` | gap | 拒绝分支无测试 |
| C3 | 节点 id 必须含 `:`、前缀等于 kind、字符集 `[A-Za-z0-9._:\-@/]` | `scripts/whyexist/graph.py:44-51`；`tests/test_package_units.py:160-166` | covered | 缺冒号/`@`、`/` 未单独断言 |
| C4 | `attrs` 必须 dict；未知键拒绝；`x_` 放行；`str/int/bool` 类型校验 | `scripts/whyexist/graph.py:18-41`；`tests/test_package_units.py:168-175`；`tests/test_wxg.py:1430-1441` | partial | 非 dict、`str/int` 不符分支未测 |
| C5 | `attrs.bite` 只读，图写入一律拒绝（审计轨迹） | `scripts/whyexist/graph.py:26-29`；`tests/test_wxg.py:848-859`；`SKILL.md:298` | covered | 安全契约，测试 + 文档双份 |
| C6 | `upsert-node` 返回 `{"action":"insert\|update","id":...}` | `scripts/whyexist/graph.py:95-96,133` | gap | 无任何断言；import-file 自己统计 inserted/updated |
| C7 | 已存在节点：attrs 整体替换；缺省字段沿用旧值；`stale` 清 0；`unmapped` 按 payload 重写 | `scripts/whyexist/graph.py:97-118`；`tests/test_wxg.py:1404-1428`；探针 | partial | 只有 construction 翻转的间接用例 |
| C8 | `merge_attrs=True` 在旧 attrs 上合并，保留手写标注 | `scripts/whyexist/graph.py:97-103`；`tests/test_wxg.py:353-369` | covered | 导入/derive/promote/declare 走这条路 |
| C9 | payload 带 `feature_id` 就写 `feature_nodes`，不校验 feature 存在 | `scripts/whyexist/graph.py:130-132`；`tests/test_wxg.py:1869-1889` | partial | 仅被 conformance 测试间接触及 |
| C10 | `upsert-edge` 要求两端节点已存在 | `scripts/whyexist/graph.py:148-151`；`references/design.md:1637` | gap | 历史回归只留文档记录 |
| C11 | `applies`：src ∈ component/classifier/operation，dst = pattern | `scripts/whyexist/graph.py:152-158`；`tests/test_wxg.py:1246-1275` | covered | 两个拒绝分支 + 正向用例 |
| C12 | `maps_to`：src ∈ use_case/component/port，dst 带 repo+path | `scripts/whyexist/graph.py:159-167`；`tests/test_wxg.py:1847-1867` | covered | |
| C13 | 边 id 默认 `edge:{kind}:{src}:{dst}`；payload 自定义 id 原样使用、不校验 | `scripts/whyexist/graph.py:136-137,168`；`tests/test_package_units.py:177-178`；探针 | partial | 探针确认 `"随便"` 会落库 |
| C14 | `bind` 只收 parameter/argument/assertion；目标须存在；方向随 kind；默认边 kind 来自 `BIND_EDGE_KIND` | `scripts/whyexist/graph.py:190-213`；`tests/test_wxg.py:142-143,229-231` | partial | 方向无断言，拒绝分支无测试 |
| C15 | `--edge-kind` 取三值且不与节点 kind 交叉校验 | `scripts/wxg_contract.py:462`；`scripts/whyexist/graph.py:198-206`；探针 | gap | 探针可造 `operation -has_argument-> parameter` |
| C16 | `find_repo` 取最长前缀；未登记仓 `Reject` | `scripts/whyexist/graph.py:60-72` | gap | 只间接走过单仓路径 |
| C17 | Engine 只读，重复调用结果一致 | `scripts/whyexist/engine.py:11-15`；`README.md:48`；`tests/test_engine.py:109-115` | partial | 只比较两次 gate 返回值，未断言库/文件不变 |
| C18 | `Engine.plan` 默认排除 unmapped 与 stale 并回填计数 | `scripts/whyexist/engine.py:77-113`；`tests/test_engine.py:82-88`；`tests/test_plan_cli.py:525-535` | partial | Engine 侧未测排除；stale 排除全项目无测试 |
| C19 | `Engine.brief` 返回 `blind=true` + `write_patterns` | `scripts/whyexist/engine.py:115-117`；`tests/test_engine.py:90-99` | covered | 缺库 Reject 只在 CLI 侧测 |
| C20 | `Engine.blind_check` 返回 PASS/FAIL | `scripts/whyexist/engine.py:119-127`；`tests/test_engine.py:90-107` | covered | |
| C21 | `Engine.gate` 返回完整 gate 字典，FAIL 不抛异常 | `scripts/whyexist/engine.py:129-131`；`tests/test_engine.py:109-115` | partial | PASS 路径未测 |
| C22 | `Engine.impact` 返回闭包字段 | `scripts/whyexist/engine.py:133-151`；`tests/test_engine.py:123-129` | partial | `cross_feature/depends_on/uncovered` 未测；无 remove-edges 模式 |
| C23 | 未初始化库连接抛 `Reject`；`db_url` 写进程级 env | `scripts/whyexist/engine.py:43-51` | gap | 探针：抛错前已建 3 个文件 + 目录 |
| C24 | `close()` 后可静默重连，close 不是终止态 | `scripts/whyexist/engine.py:43-64`；`tests/test_engine.py:131-136` | gap | 测试只断言 `_conn is None` |
| C25 | `graph_algo` 纯函数：只 import dataclasses，不碰 DB | `scripts/whyexist/graph_algo.py:19-21`；`tests/test_graph_algo.py:11-14` | partial | 结构事实，无断言 |
| C26 | `normalize` 去重保序，未知端点/自环/重复边分类上报 | `scripts/whyexist/graph_algo.py:57-85`；`tests/test_graph_algo.py:17-33` | covered | 含空图 |
| C27 | SCC 按拓扑序返回，分量内按输入顺序 | `scripts/whyexist/graph_algo.py:104-154`；`tests/test_graph_algo.py:36-69` | covered | 无大图/深链测试 |
| C28 | `topological_layers` Kahn 分层；有环抛 `CyclicGraph`，自环 `components=[[x]]` | `scripts/whyexist/graph_algo.py:169-198`；`tests/test_graph_algo.py:72-96` | covered | |
| C29 | `max_antichain` = SCC 收缩后 n − 最大匹配；空图 0 | `scripts/whyexist/graph_algo.py:322-351`；`tests/test_graph_algo.py:99-136` | covered | |
| C30 | `reachable` 不含 start；`reverse` 走上游；未知 start 空集 | `scripts/whyexist/graph_algo.py:240-263`；`tests/test_graph_algo.py:139-160`；探针 | partial | 环图会含 start，与 docstring 冲突 |
| C31 | `transitive_reachable` 每点严格可达；环图退化 DFS 同样排除自身 | `scripts/whyexist/graph_algo.py:201-237`；`tests/test_graph_algo.py:157-160`；`references/design.md:575` | partial | 环图分支无直接测试 |
| C32 | `analyze` 汇总 SCC/环/layers/反链/悬空边；自环不折叠 parallelism | `scripts/whyexist/graph_algo.py:383-406`；`tests/test_graph_algo.py:163-212` | covered | |
| C33 | 空图 `layers=[]`、多环 parallelism 取最大环 | `scripts/whyexist/graph_algo.py:366-380`；探针 | gap | 三个分支都无测试 |
| C34 | `plan` 用 `analyze` 对接 CLI：auto 设计层优先、无设计边退代码层 | `scripts/whyexist/planner.py:70-143`；`scripts/whyexist/commands_compiler.py:23-70`；`tests/test_planner.py:20-109`；`tests/test_plan_cli.py:150-228` | covered | |
| C35 | `cycles`/`impact` 复用 SCC/传递可达，不另写算法 | `scripts/whyexist/cycles.py:27-31`；`scripts/whyexist/impact.py:83-112`；`tests/test_cycles.py:17-167`；`tests/test_plan_cli.py:684-838` | covered | 重复实现另见第 5 节 |

统计：35 条契约，covered 15、partial 12、gap 8。

## 4. 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `nodes` | 读写 | `scripts/whyexist/graph.py:78,120-133` |
| `edges` | 读写 | `scripts/whyexist/graph.py:148-151,169-186,208-212` |
| `feature_nodes` | 写 | `scripts/whyexist/graph.py:132`；命令层重复 `commands_graph.py:31` |
| `repos` | 读 | `scripts/whyexist/graph.py:56-72` |
| `features/conditions/work_items/feature_nodes` | 读 | `scripts/whyexist/engine.py:83-99,115-131,136-143`（经 `ensure_feature/scope_ids/_brief_payload/cmd_gate`） |
| `bites/evidence/coverage` 相关 | 读 | `scripts/whyexist/engine.py:131` → `commands_gates.py:161-247` |
| `<root>/graph.sqlite`（+`-wal/-shm`） | 写（创建） | `scripts/whyexist/db.py:458-464`，由 `engine.py:49` 或 CLI 触发 |
| 环境变量 `WXG_DB_URL` | 读/写 | 写 `scripts/whyexist/engine.py:47-48`；读 `scripts/whyexist/db.py:425-426` |
| `sys.path`（进程级） | 写 | `scripts/whyexist/contract.py:12-14`（`engine.py:26` import 时触发） |
| stdout/stderr | 写 | `scripts/whyexist/cli.py:85-113` |

跨命令共享状态：状态库本身（SQLite 文件或 `WXG_DB_URL` 指向的 MySQL/PG 库）；`WXG_DB_URL` 是进程级全局，`Engine` 写后不恢复，`close()` 也不清理，同进程后续调用会被静默改后端。`Engine` 的 `db_url` 参数没有连接注入或上下文隔离。

## 5. 冗余

1. **`engine.plan` 与 `cmd_plan` 双份取数组装**（`engine.py:77-113` vs `commands_compiler.py:23-70`）。Engine 版缺 `level=code` 的 hint，两份已开始漂移。high。
2. **`engine.impact` 与 `cmd_impact` 双份取数组装**（`engine.py:133-151` vs `commands_compiler.py:298-313`）。CLI 的 remove-edges 模式 Engine 不暴露。high。
3. **可达性实现三份**：`graph_algo.reachable`（无生产调用方，仅 `__init__.py:27` 导出与测试）→ `impact.py:28-61` 自写 `_forward/_backward` → `transitive_reachable`。high。
4. **"环是否阻塞并行"两份规则**：`graph_algo.py:366-380` 与 `planner.py:113-124` 各自过滤 `len(component)>1` 取 max。medium。
5. **环检测三入口**：Kahn（`topological_layers`）、SCC 过滤（`_cyclic_components`）、`cycles._has_cycle`（`cycles.py:27-31` 再跑 SCC）。medium。
6. **`analyze` 内重复归一化与重复 SCC**：`analyze` → `max_antichain` → 再 `normalize+SCC`；`transitive_reachable` 又 `normalize+topological_layers`（`graph_algo.py:331-351,383-406`）。medium，属性能开销而非错误。
7. **同一节点写两次 `feature_nodes`**：`graph.py:130-132` 与 `commands_graph.py:31` 各写一次 `INSERT OR IGNORE`。medium。
8. **节点 id 规则散在三处**：`importer._node_id`（`importer.py:18-19`）、`check_node_id`（`graph.py:44-51`）、`requirement:<feature>:` 前缀（`commands_feature.py:127,163`、`workflow.py:106`）。medium。
9. **兼容层 re-export 残留**：`wxg.py:61-72` re-export graph 函数；`commands_gates.py:33-44` re-export 编译器命令；`references/design.md:382` 提到的 `whyexist/legacy.py` 源码已不存在，只剩 `__pycache__/legacy.cpython-312.pyc`。medium。
10. **`applies` 端点 kind 硬编码**（`graph.py:155`），而 `maps_to` 用契约常量 `DESIGN_ANCHOR_KINDS`（`contract.py:19`）。low。

## 6. 重写分区

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `scripts/whyexist/graph_algo.py` | keep | 纯函数、零内部依赖、零 DB；30 个测试覆盖归一化/SCC/分层/反链/可达/analyze 的主要分支与边界（空图、自环、双环分量、重复边、确定性、输入顺序无关）。契约由类型表达，继续加测成本低 | 函数同时在 `whyexist.__init__.__all__` 里，改签名会连带 `planner/cycles/impact`；`reachable` 是死代码，删除前需确认无外部使用者 |
| `scripts/whyexist/graph.py` | refactor_in_place | 写入契约大体清楚（kind/id/attrs/applies/maps_to 有测试），但 20 种边只校验 2 种、edge id 无校验、attrs 覆盖/合并双语义与 stale/unmapped 复位都是隐式行为。有 9 个调用模块，整模块重写最容易丢这些没写下来的细节 | 收紧校验会改变 gate/doctor/conformance 看到的图（例如给 `depends` 加端点 kind 校验会拒掉现存测试和外部图库）；改 attrs 合并策略会丢设计角色手写的 `duty/x_note` |
| `scripts/whyexist/engine.py` | rewrite | 151 行门面，行为边界简单（把连接接到 5 个纯函数入口），但当前实现与 CLI 组装重复、依赖命令层（`_brief_payload/cmd_gate`）、带 env 与文件副作用；适合改成薄包装 + 显式只读连接 | 输出形状没被完全锁死：gate 返回完整 `cmd_gate` 字典、impact 的 `cross_feature/depends_on`、`db_url` 语义都只有 happy path 测试；重写前先补 C18/C21/C22/C23/C24 的行为测试，否则会静默改掉库 API 结构 |

没有判定为 freeze 的模块。若必须列一个冻结对象，是 `whyexist/__init__.py` 的导出名单（跨切片公共 API）——但它不在本切片内。

## 7. 隐含需求（重写会静默丢掉的行为）

- 任何节点 upsert 都把 `stale` 清 0（`graph.py:118`）；只写在 `references/design.md:237`，无测试。
- payload 里显式 `null` 会覆盖 `name/repo/path/symbol/line_*` 为 NULL（`payload.get` 的缺省值不覆盖显式 None）；探针确认 `name` 变 NULL。
- CLI 路径 attrs 整体替换，只有导入/declare/promote 用 `merge_attrs=True` 合并；`SKILL.md:400` 只讲"用不带 construction 的 upsert 清除标记"，没讲其余 attrs 会一起消失。
- `unmapped` 由每次 upsert 的 payload 重写（`graph.py:117`）：被标 unmapped 的节点再 upsert 一次会静默变回已映射。
- 自定义 edge id 可绕开 `edge:{kind}:{src}:{dst}` 约定，无格式或冲突校验（`graph.py:168`）。
- `bind --edge-kind` 不校验与节点 kind 匹配（探针造出 `operation -has_argument-> parameter`）；`has_output` 不在 choices 里，bind 永远建不出输出参数边。
- `find_repo` 用最长前缀选最具体的仓（嵌套仓行为无文档无测试）。
- `edges` 无外键，写时校验只是应用层约定；dangling edge 靠 doctor 的 orphan-edge 兜底（`commands_misc.py:369`）。
- `upsert_node` 写 `feature_nodes` 不校验 feature 存在（`graph.py:130-132`），会留悬空作用域关联。
- 只有 `applies`/`maps_to` 校验端点语义，其余 18 种边只检查端点存在；契约文档里 `contains/calls/reads` 的方向并不被强制（`test_package_units.py:644-649` 甚至用了反向的 `verifies` 边）。
- Engine 在未初始化目录上 `connect` 先建目录 + `graph.sqlite`/`-shm`/`-wal` 再抛 `Reject`，与 `cli.py:62-69` 的零副作用策略不一致。
- `Engine(db_url=...)` 改进程级 `WXG_DB_URL` 且不恢复；`close()` 后调用方法会静默重连。
- `reachable` 在环图里把起点算进可达集（探针：`{'a','b'}`），与 docstring"不含 start 自身"冲突，而同模块 `transitive_reachable` 显式 `seen - {start}`。

## 8. 值得人判断的问题

1. **attrs 整包替换**是有意契约还是历史选择？`SKILL.md:400` 依赖它清除 `construction`，但同一路径也抹掉 `duty/x_note`。改成合并就要重写现有清除手法。
2. **自定义 edge id** 要不要保留？保留就该给格式/长度/冲突规则；不保留直接拒绝 `payload.id`，但可能有外部导入方依赖。
3. **`bind --edge-kind`** 该不该与 node kind 交叉校验？`has_output` 为什么不在 choices 里——遗漏还是有意只让 `upsert-edge` 建输出边？
4. **Engine 的连接模型**：接受注入的只读连接，还是保持自建连接但把"首次连接会建文件"写进文档并补测试？
5. **`reachable` 是公开 API 还是遗留**？`__init__.__all__` 导出但无生产调用方，删除会动包级 API 的兼容承诺。
6. **边语义只校验 2/20** 是有意宽松（结构判断留给 gate/conformance）还是没做完？这决定 `graph.py` 重写的范围。
