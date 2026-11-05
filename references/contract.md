# wxg 完整契约

> 本文件由 `scripts/wxg_contract.py` 渲染，`wxg contract --write references/contract.md --section full` 刷新。
> `wxg verify` 会逐字节比较下面的契约块；手改会在自检时报漂移。

<!-- wxg:contract:full:begin -->
### 条件顺序（8 项，固定）

| 条件 | 置真方式 |
|------|----------|
| `Accepted` | `feature-declare` 置真；`feature-register` 仅新建/新代时置真 |
| `ArchitectureReconciled` | `model-architecture` 工单 judged passed |
| `StructureReconciled` | `model-structure` 工单 judged passed |
| `InteractionsReconciled` | `interact` 工单 judged passed |
| `TestsSpecified` | `specify-test` 工单 judged passed |
| `TestsImplemented` | `implement-test` 工单 judged passed |
| `BehaviorPassed` | `observe` 工单 judged passed |
| `Ready` | 前七项全真时由 `work-judge(passed)` 派生；没有自己的工单 |

### 角色与允许命令

| 角色 | 允许命令 |
|------|----------|
| `scan` | `import-file`、`import-repo`、`derive`、`upsert-node`、`retract`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `model-architecture` | `derive`、`promote`、`upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `model-structure` | `derive`、`promote`、`upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `interact` | `upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `specify-test` | `upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `implement-test` | `upsert-node`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `observe` | `import-file`、`import-repo`、`derive`、`upsert-node`、`retract`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `audit` | `get`、`find`、`slice`、`work-judge`、`role-prompt`、`evidence-record` |

### 命令

| 命令 | 用途 | 关键参数 | 写入 |
|------|------|----------|------|
| `init` | 初始化状态库并做一次性旧库迁移；迁移后重复运行不改已有行 | — | 状态库（首次迁移） |
| `up` | 一条命令立起工作区：init + demo 仓 + demo feature + 第一次 gate 结果（不自动裁决，幂等） | — | 状态库 / 文件（demo 仓） |
| `repo-add` | 登记源码仓；技能里不写死任何仓名 | --id <值> --path <值> | 状态库 |
| `repo-list` | 列出已登记仓 | — | 只读 |
| `import-file` | 按单个 Python 源码文件导入节点/边；--prepare 只预列 id 到 scan 工单（此时必须带 --feature） | --file <值> --prepare | 写图需 claim_token；--prepare 免 token |
| `import-repo` | 按仓批量导入全部 Python 文件；--prepare 只预列到 scan 工单 | --repo <值> --prepare | 写图需 claim_token；--prepare 免 token |
| `derive` | 从代码图推导 component/depends 候选（默认 dry-run；--apply 写入 origin=derived） | --repo <值> --feature <值> --apply | 只读（--apply 时写图，需 claim_token） |
| `promote` | 把 origin=derived 的候选节点提升为 declared，并记录裁决者（需 claim_token） | --feature <值> --node <值> | 需要 claim_token / 角色命令 |
| `sample` | 从仓或 feature 作用域里随机取一个节点，作为撕咬入口 | — | 只读 |
| `feature-declare` | 声明功能：generation+1，重置条件，只派 work-seed | --id <值> --name <值> --statement <值> --acceptance <值> --constraints <值> --no-coverage --conformance --no-conformance | 状态库 |
| `feature-register` | 登记已有图：同代登记不写条件；新建/新代只置 Accepted（--generation 会重置条件并 supersede 旧工单） | --id <值> --name <值> --spec <值> | 状态库 |
| `feature-list` | 列出 feature 与当前 generation | — | 只读 |
| `feature-status` | 显示当前 generation 的条件、工单、咬合汇总 | --id <值> | 只读 |
| `change-open` | 在 feature Ready 后开变更集：继承 from-condition 之前的条件，从它起重置并开启新一代，自动 seed 下游工单 | --feature <值> --statement <值> --from-condition <值> | 状态库 |
| `change-diff` | 只读对比：当前代与上一代工单写过的节点集合、继承/待办条件、代码锚点 | --feature <值> | 只读 |
| `work-open` | 预开/扩展非 audit 工单的 target_ids（scan 与设计角色扩写入边界都用它） | --feature <值> --kind <值> --target-ids <值> | 状态库 |
| `work-seed` | 按缺的条件各生成一张工单 | --feature <值> | 状态库 |
| `work-claim` | 按角色领取当前代一张 ready 工单，返回 claim_token 与切片（--brief 只给计数） | --role <值> --allow-product-code --brief | 状态库 |
| `work-finish` | 提交已领取工单；通过后生成 audit 工单 | --token <值> | 需要 claim_token / 角色命令 |
| `work-judge` | 审计裁决一张 submitted 工单（仅 audit 角色）；BehaviorPassed 需要先登记 evidence | --id <值> --verdict <值> | 状态库 |
| `work-list` | 列出某 feature 当前 generation 的工单 | --feature <值> | 只读 |
| `upsert-node` | 写节点；id 已存在则更新（不接受 attrs.bite） | --token <值> --data <值> | 需要 claim_token / 角色命令 |
| `upsert-edge` | 写边；两端必须已存在 | --token <值> --data <值> | 需要 claim_token / 角色命令 |
| `bind` | 绑定 parameter/argument/assertion 到已存在节点 | --token <值> --node-id <值> --bind-to <值> | 需要 claim_token / 角色命令 |
| `retract` | 撤回 target_ids 内的节点与边；级联删除 bite 并剔除工单引用 | --token <值> | 需要 claim_token / 角色命令 |
| `bite` | 记录一次必要性判定；判决集固定，写 bites 与节点 attrs.bite（唯一写入口） | --node <值> --verdict <值> | 状态库 |
| `evidence-record` | 记录一条可追溯证据：命令、退出码、执行者、产物 hash（BehaviorPassed 的门槛） | --feature <值> --name <值> --command <值> | 状态库 |
| `evidence-list` | 列出某 feature 的证据记录 | --feature <值> | 只读 |
| `coverage` | 按咬合覆盖公式计算各阶段 n/d/p/n_required 与调度索引（只读） | --feature <值> --json | 只读 |
| `reconcile` | 控制器单步：对比期望与观测并输出待办动作；--apply 只做安全迁移（补单/解阻塞/回收陈旧 claim），不裁决不咬合不写图 | --feature <值> --apply | 只读（--apply 时状态库） |
| `serve` | 常驻控制器：周期性对全部 feature 跑 reconcile 安全迁移；--once 单趟便于测试 | --once --apply | 只读（--apply 时状态库） |
| `sync` | 只读回扫断言：重新解析登记仓，对比 DB 图与当前代码，报 missing/new/changed/stale | --repo <值> | 只读 |
| `plan` | 并行规划：从 feature 依赖图算强连通分量、调度波次、最大反链与理论并行上限（只读；默认排除 unmapped 噪声） | --feature <值> --include-unmapped | 只读 |
| `cycles` | 依赖环分析：把 design 层的强连通分量展开成具体依赖边与文件证据（只读） | --feature <值> --break-set --advise | 只读 |
| `brief` | 生成一张工单的盲化任务书：只含写入边界、输入契约、产出契约与完成定义（只读） | --work <值> | 只读（--out 时写文件） |
| `blind-check` | 盲执行校验：拿任务书与独立执行者的产出，检查写入边界、产出契约与依赖引用（只读） | --work <值> --result <值> | 只读 |
| `patch` | 把一次盲执行产出规范成补丁文件（只读；--out 写文件），供 apply 合并 | --work <值> --result <值> --out <值> | 只读（--out 时写文件） |
| `apply` | 合并补丁并写入图库：冲突显式报告且不写半截；--dry-run 只报告 | --patches <值> --dry-run | 状态库（全量校验通过才写） |
| `impact` | 影响域闭包：改动节点的下游可达集与需求覆盖，或断掉依赖边后的失去可达（只读） | --feature <值> | 只读 |
| `conflicts` | 声明期冲突检测：列出 feature 之间会重叠的 target_ids 写边界（只读） | — | 只读 |
| `conformance` | 只读一致性检查：设计锚点、depends 的代码支撑、未声明耦合、use_case 的测试覆盖；只报差异 | --feature <值> | 只读 |
| `gate` | 交付门：只读计算 PASS/FAIL；PASS 退出码 0、FAIL 退出码 1 | --feature <值> --json | 只读 |
| `export` | 按 feature 导出六份只读视图（写入 <root>/export/） | --feature <值> | 文件（<root>/export/） |
| `slice` | 取工单或 target_ids 的深度 1 切片（只读；target_ids 支持 `前缀*` 与 @文件；--limit 防大图刷屏） | — | 只读 |
| `get` | 按 id 读取一个节点 | --id <值> | 只读 |
| `find` | 按 kind / 路径前缀 / 入边起点查找节点（--limit 防大图刷屏） | — | 只读 |
| `role-prompt` | 生成可交给 DSH teammate 的角色提示（含状态库路径、允许命令与边界） | --role <值> | 只读 |
| `contract` | 输出契约；--write 刷新文档契约块 | --json | 只读（--write 时写文档） |
| `verify` | 一致性自检：契约块、角色/命令/kind 交叉引用、导出样例、写入列；不替代 doctor/行为测试 | — | 只读 |
| `doctor` | 状态库自检：悬空 bite/边/引用、陈旧 token、条件与审计配对、legacy 身份、证据产物；--fix 只清理悬空引用与陈旧 token | --fix | 只读（--fix 时状态库） |

### 咬合判决

允许值：`KEEP`、`UNNECESSARY`、`HOLLOW`、`DOC-ONLY`、`UNMAPPED`、`UNKNOWN`。

结构性漂移判决：`UNMAPPED`、`DOC-ONLY`（由 `--drift-limit` 控制是否拦门）。

| 规则 |
|------|
| 条件未齐（七项条件与 Ready 任一为假）→ FAIL。 |
| 作用域内节点按**当前代最新一条** bite 计判决：最新为 UNNECESSARY/HOLLOW → FAIL；KEEP 只反证**同一节点**，跨节点或旧代 KEEP 不抵消。咬合只采信 `bites` 表（含 actor），`attrs.bite` 仅供展示。 |
| 模式有限应用：作用域内每个 `pattern` 必须有非空 `applicability` 与 `not_applicable`，且至少被一条 `applies` 边挂到具体设计元素（component/classifier/operation），否则 FAIL。 |
| 结构性漂移：feature 开启 `--drift-limit N` 时，作用域内当前代最新判决为 UNMAPPED/DOC-ONLY 的节点数超过 N 则 FAIL；未设置该策略只报告。 |
| 施工中标记：`construction=true` 的节点（施工中代码段）在 gate 前必须清除，否则 FAIL；咬合逻辑不受标记影响。 |
| 回扫生还：作用域内 `stale=1` 的节点（重扫时代码里已不存在的旧锚点）在 gate 前必须清除，否则 FAIL。 |
| 设计-代码一致性：feature 开启 `--conformance` 时，gate 要求 use_case/component/port 有 `maps_to` 代码锚点、component/port 的 `depends` 有代码调用支撑、代码调用不出现未声明耦合、每个 use_case 至少被一个 testcase `verifies`；否则 FAIL。只报告检查结果，不生成新的设计描述。 |
| gate 只读：不写条件、不写工单、不改节点，重复执行结果不变；PASS 退出码 0、FAIL 退出码 1。 |
| 除 Accepted 由 `feature-declare` / `feature-register` 新建时置真外，只有 work-judge(passed) 写条件；judge(failed) 把该条件及其后的条件置假，没有对应条件的工单（scan）不改条件。 |
| `BehaviorPassed` 置真前必须有一条**同 generation**、exit_code=0 且产物有效的 evidence（有产物时校验存在与 hash），gate 执行同样的检查。 |
| feature 开启 coverage 策略（默认对新 feature 开启；`--no-coverage` 关闭）时，gate 与 `work-judge(passed)` 都要求该阶段咬合覆盖达标；关闭则只报告不拦截。 |
| `retract` 会级联删除 bite；外部遗留的悬空 bite 不计入门禁（输出 ignored_dangling_bites），由 doctor 清理。 |

### 咬合覆盖与调度（feature 显式开启后强制）

默认参数：`epsilon=1.0`，`prior_p=0.1`，`alpha=2.0`。

| 规则 |
|------|
| 覆盖对**新 feature 默认开启**（ε=1.0）；`feature-declare --no-coverage` 关闭，显式 `--coverage-epsilon` 覆盖默认值；重声明保留已有策略，旧库迁移后默认关闭。 |
| 设作用域节点数 S、某阶段已覆盖节点数 n（同一节点多次咬合只算一次）、命中节点数 d（该节点任一判决非 KEEP 且非 UNKNOWN），后验缺陷率 p=(1+d)/(10+n)（Beta(1,9) 先验）。 |
| 阶段推进前要求 p_m·(S-m) ≤ ε，其中 p_m=(1+d)/(10+m)（假设后续咬合不再新增命中）；n_required 取满足条件的最小 m，m 不超过 S（m=S 时残留期望为 0）。 |
| 调度索引 I_i = α^(i-1)·p_i，α 默认 2，i 为条件在固定顺序中的位置；预算有限时优先把下一次咬合投给 I 最大的阶段；`coverage.next` 取**条件顺序里第一个未达标阶段**（阶段不能跳着推进）。 |
| `coverage` 只读输出各阶段的 bites、covered、hits、p、n_required、met 与调度建议；策略开启时 `work-judge(passed)` 与 `gate` 执行同一检查。 |

### 调谐（reconcile）

默认参数：`claim_ttl=3600`。

| 规则 |
|------|
| reconcile 默认只读、幂等：同一状态重复运行输出相同；`converged`=gate PASS 且无待办动作，退出码 0，有待办 1，错误 2。 |
| 自动迁移只限三类：补缺失工单、解 blocked、回收超过 `--claim-ttl` 的 claimed 工单（清 token/assignee/claimed_by 并回到 ready）。 |
| 裁决、咬合、图写入、导出永不自动执行；覆盖缺口、漂移超限、施工标记、证据缺失只作为待办动作报告。 |
| `work_items.claimed_at` 由 `work-claim` 写入；旧库迁移时 claimed 行按 created_at 回填，无法还原真实领取时间。 |

### 变更集（change set）

| 规则 |
|------|
| `change-open` 只在 feature **Ready** 后使用：from-condition 之前的条件按上一代继承为真，从 from-condition 起重置为假，并开启新一代（generation+1）。 |
| 被继承的条件在当前代没有审计单；`changes` 表记录 from/to generation 与 from-condition，doctor 核对继承来源。 |
| 变更集会重新派工 from-condition 及其下游（含 implement-test、observe）；BehaviorPassed 必须用新代 evidence 重新证明，旧代证据不满足。 |
| `change-diff` 只读：比较当前代与上一代工单写过的节点集合（evidence_ids），输出 added/removed/kept、继承条件与待办条件、代码锚点。 |
| 一个 feature 同时只允许一个未收口的变更集：变更代 Ready 之前再次 change-open 会被拒绝。 |

### 回扫断言（rescan）

| 规则 |
|------|
| `sync --repo <id>` 只读：重新解析登记仓的 Python 文件，与 DB 图对比，输出 missing（DB 有、代码无）、new（代码有、DB 无）、changed（行号/名称变化）与 stale 计数。 |
| `import-file` 写入时，同 repo+path 下本次未再出现的旧节点标 `nodes.stale=1`（代码里已不存在）；再次导入出现则清 0。 |
| `--prepare` 会把该文件已有的旧节点 id 一并并入 scan 工单 target_ids，使 stale 标记不越出写入边界。 |
| gate 对作用域内 `stale=1` 的节点直接 FAIL；必须重扫/修正设计后清掉，不能带着已删除的代码锚点交付。 |
| sync 不写库；stale 清除只能通过 import-file 重扫或设计角色重写节点。 |

### 设计-代码一致性（conformance）

| 规则 |
|------|
| `maps_to` 是设计节点到代码锚点的一条边，不复制代码结构；conformance 只输出差异（缺锚点、缺代码支撑、未声明耦合、缺测试覆盖、代码孤儿），不生成节点、不补写设计。 |
| 锚点检查：use_case/component/port 至少要有一条 `maps_to` 指向带 repo/path 的代码节点；没有就列入 `anchors.missing`。 |
| 结构检查：每条 component/port 的 `depends` 必须能在两边锚定的代码节点之间找到 calls/reads/writes 支撑；反向，代码调用跨了组件却没有 depends/associates，列入 `structural.undeclared`。 |
| 跨文件裸名调用被导入器标成 unmapped 时，若名字在作用域内唯一，允许一次启发式解析用于“依赖是否有代码支撑”（计入 `structural.resolved_heuristically`）；不写回图，也不用于未声明耦合。 |
| 代码反向：作用域内未被任何 `maps_to` 指向的 operation/classifier 列 `anchors.code_orphans`；只报告，不算 violation，也不要求每个操作都进设计图。 |
| 测试覆盖：每个 use_case 至少要有一条来自 testcase 的 `verifies`；没有就列入 `tests.missing`（只在报告中，不替代 TestsSpecified 条件）。 |
| `maps_to` 写入时校验方向：src 必须是 use_case/component/port，dst 必须带 repo/path 的代码节点。 |
| feature 用 `--conformance` 开启 gate 强制；默认关闭，旧 feature 迁移后保持关闭。报告只读，写入由设计角色显式完成。 |

### 状态库后端

| 规则 |
|------|
| 默认 SQLite（WAL + busy_timeout=5000）；设 `WXG_DB_URL=mysql://...` / `postgresql://...` 或全局 `--db-url` 切换后端。 |
| MySQL 后端使用内置的纯标准库客户端 `scripts/wxg_mysql.py`，不需要第三方包；PostgreSQL 后端需要 `pip install 'psycopg[binary]'`（未安装时连接报可读错误）。 |
| SQLite 仍是单写者；MariaDB/MySQL/PostgreSQL 允许不同行并发写，同一工单领取靠 `UPDATE ... WHERE status='ready'` 的原子 rowcount。 |
| 同一个状态库不要混用后端；导出目录仍由 `--root` 决定，与 DB 后端无关。 |

### 常驻控制器（serve）

| 规则 |
|------|
| `serve` 默认每 `--interval` 秒（默认 5）对全部 feature 跑一遍 reconcile，并打印一行 JSON 摘要。 |
| `--apply` 时只执行 reconcile 允许的三类安全迁移（补单/解阻塞/回收陈旧 claim）；裁决、咬合、图写入永不自动。 |
| `--once` 跑单趟后退出，便于测试与 CI；Ctrl+C 退出并保留已提交状态。 |
| 常驻控制器与后端无关：SQLite 下是唯一写者，MySQL 下可多实例并行，但同一工单仍只有一个代理能领到。 |

### 审计与证据

| 规则 |
|------|
| `work-claim`、`work-judge`、`bite` 必须带 `--actor`（或 `WXG_ACTOR` 环境变量），记录到 `work_items.claimed_by` / `judged_by` / `bites.actor`。 |
| 审计独立性：`work-judge --actor` 不得等于被审工单的 `claimed_by`；旧库迁移写入的 `legacy` 允许，但结果会带 `legacy_claim: true`，doctor 报 `legacy-identity`（不可追溯，不伪造成员）。 |
| `work-judge` 同时写 `judged_at`；一个工单的 `judged_by` 不允许被后续裁决覆盖（仅允许从空到有值）。 |
| `work-judge` 每次裁决（passed/failed）都写入 `judge_history`（裁决、理由、actor、时间，只增不删）；judge(passed) 同时清空该工单的陈旧 `fail_reason`。 |
| `attrs.bite` 只能由 `bite` 命令写入；`upsert-node` 等图写入不得写入 bite，gate 不采信图写入里的 bite 值。 |
| 审计日志/证据不得只复述结论：至少记录执行者、命令、退出码或产物 hash，否则只能标 `UNKNOWN`/过程证据，不计入交付门。 |
| 证据是状态库的一等记录：每次测试、HTTP 冒烟、gate、export、独立重跑用 `evidence-record` 写入 `evidence` 表。 |
| 证据记录至少包含：feature、名称、命令、退出码、执行者、时间；有产物文件时同时写 artifact 路径与 SHA-256。 |
| `BehaviorPassed` 的裁决与 gate 都要求 feature 下**同 generation**、exit_code=0 的 evidence；有产物时还会校验产物存在/hash；没有有效证据时 judge 拒绝置真、gate 判 FAIL。 |
| `doctor` 校验 evidence 指向的产物仍存在且 hash 未变、退出码、generation 非空与 legacy 身份；重跑证据命令不得改写权威状态库与 export。 |
| `finalize`/一键重跑脚本必须幂等：默认 `--dry-run` 或默认不追加 bite；确需写状态时必须显式 `--apply`。 |

### 导出文件

| 文件 | 列 |
|------|----|
| `01-需求.md` | id、能力、验收、约束 |
| `02-用例.md` | id、名称 |
| `04-架构.md` | kind、id、名称 |
| `05-类图.md` | kind、名称、路径、符号、unmapped |
| `07-数据流.md` | 步、操作、符号、写入、断言 |
| `测试规格.md` | kind、id、名称、属性 |

`07-数据流.md` 另含小节 `请求参数`，列：参数、unmapped、属性。

### 一致性不变量

| 编号 | 不变量 |
|------|--------|
| I1 单一契约 | 条件、工单、角色、命令、属性键、导出形状（含 07 的附加表与命令“写入”列）在 wxg_contract.py 定义；CLI 与生成文档块由它生成，`wxg verify` 校验生成视图与导出样例的字节一致性（不校验手写正文语义）。 |
| I2 generation 是身份 | 条件与工单 id 都带 generation；重新声明会开启新一代并 supersede 旧工单，work-claim 只发当前代；不会出现旧 passed 工单挡住或混淆新条件。 |
| I3 交付门只读 | gate 不写库；正常流程中条件只由 work-judge(passed) 改写，Accepted 由声明/登记入口新建时置真。判定与状态变更分离。 |
| I4 判决可校验 | bite 是唯一写入咬合的命令，只接受固定判决集；gate 只采信 bites 表，作用域包含 feature_nodes、requirement 前缀与当前代工单 target_ids。 |
| I5 写入有边界 | 图内容写入（upsert-node/upsert-edge/bind/retract/import-file）必须带 claim_token 且落在工单 target_ids 内；角色只能调用自己在 ROLES 里的命令。feature-declare / feature-register 只写 feature 元数据与 requirement 节点，bite 只写 bites/attrs.bite 且必须带 actor。 |
| I6 技能通用 | 技能不写死仓名、工作区路径；仓在运行期 repo-add 登记，状态库路径用 --root 指定；导入器当前仅 Python AST（扩展边界见 design.md）。 |
| I7 不臆造 | 认不出的节点/边标 unmapped=1；导出缺 id 留空；BehaviorPassed 置真前必须有**同 generation**、exit_code=0 的 evidence，judge 与 gate 双向强制。 |
| I8 文档即生成的视图 | SKILL.md 与 references/contract.md 的契约块、references/export-sample 的样例都由同一实现生成；verify 比较字节。 |
| I9 状态可自检 | doctor 检查悬空 bite/边/引用、陈旧 token、条件完整性、审计配对、legacy 身份与证据产物；--fix 只自动修可判定问题（dangling-bite / orphan-edge / feature-node-missing / work-target-missing / work-evidence-missing / token-on-inactive / meta-version），其余只报不修，不替人裁决。 |
| I10 审计可追溯 | work-claim / work-judge / bite 记录 actor；审计 actor 不得等于被审工单的 claimed_by；judged_by/judged_at 只写一次；gate 采信的咬合以 bites 表为准。 |
| I11 证据可追溯 | evidence-record 把命令、退出码、generation、执行者、产物 SHA-256 写入 evidence 表；doctor 校验产物存在/hash/退出码/generation 非空与 legacy 身份；judge/gate 对 BehaviorPassed 强制同代、exit_code=0 且产物有效的 evidence；重跑证据不得改写权威状态。 |
| I12 模式有限应用 | pattern 是设计决策节点：必须写 applicability 与 not_applicable，必须被 applies 挂到具体设计元素；gate 强制，误用/过度应用由 UNNECESSARY/DOC-ONLY 咬合反证。 |
| I13 判决按最新 | gate 采信当前代每个节点的最新 bite；最新为 UNNECESSARY/HOLLOW 即 FAIL；KEEP 只反证同一节点，跨节点、旧代 KEEP 不抵消。 |
| I14 失败历史 | 每次 work-judge 写 judge_history（只增不删）；judge(passed) 清空陈旧 fail_reason；doctor 校验裁决历史与工单的关联与 actor。 |
| I15 覆盖可计算 | coverage 公式与默认参数（ε=1.0、先验 p=0.1、α=2）由契约定义；新 feature 默认开启 coverage，`--no-coverage` 关闭；work-judge(passed) 与 gate 要求该阶段覆盖达标。 |
| I16 漂移可门禁 | feature 开启 --drift-limit 后，gate 统计当前代最新判决为 UNMAPPED/DOC-ONLY 的节点数，超限即 FAIL；未开启只报告不拦截。 |
| I17 调谐可重复 | reconcile 默认只读且幂等；--apply 只做补单/解阻塞/回收陈旧 claim，不裁决、不咬合、不写图；交付判定仍由 gate 给出。 |
| I18 变更可追溯 | change-open 只在 Ready 后开启新代，并按 from-condition 继承上游条件；changes 表记录 from/to generation 与继承边界，change-diff 只读对比两代写过的节点集合，旧代 evidence 不满足新代 BehaviorPassed。 |
| I19 回扫可断言 | sync 只读对比 DB 图与当前 AST；import-file 把本次未再出现的旧节点标 stale=1，gate 对作用域内 stale 节点 FAIL；stale 只能由重扫或设计重写清除。 |
| I20 控制器可常驻 | serve 周期跑 reconcile；--apply 只做补单/解阻塞/回收陈旧 claim；--once 单趟；控制器可接 SQLite 或 MySQL，裁决/咬合永不自动。 |
| I21 一致性只报差异 | conformance 只做差异检查：设计节点的 maps_to 锚点、depends 的代码支撑、未声明耦合、use_case 的测试覆盖；不生成节点、不补写设计，开关由 feature 的 --conformance 决定。 |

### 节点 kind

| kind | 说明 | 创建者 |
|------|------|--------|
| `requirement` | 功能声明；id 前缀 requirement:{feature}: | 声明入口 |
| `actor` | 角色 | model-architecture |
| `use_case` | 用例；satisfies 指向 requirement | model-architecture |
| `component` | 构件；depends 指向 component | model-architecture / scan 锚点 |
| `port` | 端口；associates 指向 component | model-architecture / scan 锚点 |
| `pattern` | 设计模式实例；attrs 必须写 applicability/not_applicable，applies 挂到具体设计元素 | model-architecture / model-structure |
| `classifier` | 类/接口/枚举等；contains 指向 operation 或 property | scan / model-structure |
| `property` | 字段/属性 | scan / model-structure |
| `operation` | 函数/方法；calls、reads、writes | scan / interact |
| `parameter` | 入参/出参；通过 bind 挂到 operation | interact / specify-test |
| `interaction` | 交互；has_lifeline、has_message | interact |
| `lifeline` | 生命线 | interact |
| `message` | 消息；has_argument | interact |
| `argument` | 消息参数；通过 bind 挂到 message | interact |
| `sink` | 数据落点（表/文件/外部系统）；operation writes 指向它 | interact / scan |
| `testcase` | 测试用例；verifies 指向 use_case 或 operation | specify-test |
| `assertion` | 断言；asserts 指向已存在节点 | specify-test |

### 边 kind

| kind | 说明 |
|------|------|
| `contains` | 容器 -> 被包含节点 |
| `satisfies` | use_case -> requirement |
| `verifies` | testcase -> use_case / operation |
| `include` | use_case -> use_case |
| `extend` | use_case -> use_case |
| `generalizes` | classifier -> classifier |
| `realizes` | classifier -> classifier |
| `associates` | 任意节点 -> 任意节点 |
| `maps_to` | 设计节点（use_case/component/port）-> 代码节点（锚点，必须落在 repo/path 节点上） |
| `applies` | 具体设计元素（component/classifier/operation）-> pattern（该元素采用该模式） |
| `depends` | component -> component |
| `calls` | operation -> operation |
| `reads` | operation -> property |
| `writes` | operation -> sink / property |
| `has_input` | operation -> parameter |
| `has_output` | operation -> parameter |
| `has_lifeline` | interaction -> lifeline |
| `has_message` | interaction -> message |
| `has_argument` | message -> argument |
| `asserts` | assertion -> 已存在节点 |

### 属性键（attrs_json）

公共键：`bite`（只读，仅由 `bite` 命令写入）、`x_*`。其余按节点 kind：

| kind | 允许键 |
|------|--------|
| `requirement` | `statement`:str |
| `actor` | — |
| `use_case` | `goal`:str、`actor`:str |
| `component` | `duty`:str、`construction`:bool |
| `port` | `port`:int、`protocol`:str |
| `pattern` | `intent`:str、`applicability`:str、`not_applicable`:str、`forces`:str、`cost`:str、`alternative`:str、`source`:str |
| `classifier` | `duty`:str、`construction`:bool |
| `property` | `column`:str |
| `operation` | `http`:str、`success_code`:str、`async`:bool、`construction`:bool |
| `parameter` | `column`:str、`on_insert`:str、`note`:str、`example`:任意 |
| `interaction` | — |
| `lifeline` | — |
| `message` | — |
| `argument` | — |
| `sink` | `table`:str、`store`:str |
| `testcase` | `path`:str、`text`:str、`layer`:str |
| `assertion` | `text`:str、`success_code`:str、`column`:str |

### 证据记录（evidence）

| 列 | 含义 |
|----|------|
| `id` | `ev:<uuid>` |
| `feature_id` | 所属 feature |
| `generation` | 证据所属 generation（BehaviorPassed 只认同代证据） |
| `work_item_id` | 可选关联工单 |
| `name` | 证据名称 |
| `command` | 复现命令原文 |
| `exit_code` | 命令退出码 |
| `artifact_path` | 产物文件路径，可空 |
| `artifact_sha256` | 产物 SHA-256，可空 |
| `actor` | 执行者 id |
| `created_at` | UTC 时间 |

### 裁决历史（judge_history）

| 列 | 含义 |
|----|------|
| `id` | `jh:<uuid>`（迁移回填为 `jh:<work_item_id>`） |
| `work_item_id` | 被裁决工单 |
| `feature_id` | 所属 feature |
| `generation` | 所属 generation |
| `kind` | 工单 kind |
| `verdict` | `passed` / `failed` |
| `reason` | 失败理由，可空 |
| `actor` | 审计执行者 id |
| `judged_at` | UTC 时间 |

### 导出规则

导出只包含图里连到该 feature 的记录：01 取 requirement；02 取 satisfies 这些 requirement 的 use_case；04 取用例经 depends/associates/realizes 到达的 component 与 port，以及 feature 作用域内的 pattern；05 取用例 contains 的 operation 及其 has_input、以及 contains 指向这些 operation 的 classifier；07 每条 writes->sink 算一步，另附请求参数表（同一参数只列一次，顺序按首次出现）；测试规格取 verifies 到这些 operation/use_case 的 testcase 与 asserts 到 operation 的 assertion。缺的格子留空，禁止从任何旧文档补句。参数、测试与断言按 id 去重。

契约版本 `3.2.0`，库 schema 版本 `9`。
<!-- wxg:contract:full:end -->
