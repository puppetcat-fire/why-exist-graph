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
| `scan` | `import-file`、`upsert-node`、`retract`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `model-architecture` | `upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `model-structure` | `upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `interact` | `upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `specify-test` | `upsert-node`、`upsert-edge`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `implement-test` | `upsert-node`、`bind`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `observe` | `import-file`、`upsert-node`、`retract`、`get`、`find`、`slice`、`work-finish`、`role-prompt`、`evidence-record` |
| `audit` | `get`、`find`、`slice`、`work-judge`、`role-prompt`、`evidence-record` |

### 命令

| 命令 | 用途 | 关键参数 | 写入 |
|------|------|----------|------|
| `init` | 初始化状态库并做一次性旧库迁移；迁移后重复运行不改已有行 | — | 状态库（首次迁移） |
| `repo-add` | 登记源码仓；技能里不写死任何仓名 | --id <值> --path <值> | 状态库 |
| `repo-list` | 列出已登记仓 | — | 只读 |
| `import-file` | 按单个 Python 源码文件导入节点/边；--prepare 只预列 id 到 scan 工单（此时必须带 --feature） | --file <值> --prepare | 写图需 claim_token；--prepare 免 token |
| `sample` | 从仓里均匀随机取一个节点，作为撕咬入口 | --repo <值> | 只读 |
| `feature-declare` | 声明功能：generation+1，重置条件，只派 work-seed | --id <值> --name <值> --statement <值> --acceptance <值> --constraints <值> | 状态库 |
| `feature-register` | 登记已有图：同代登记不写条件；新建/新代只置 Accepted（--generation 会重置条件并 supersede 旧工单） | --id <值> --name <值> --spec <值> | 状态库 |
| `feature-list` | 列出 feature 与当前 generation | — | 只读 |
| `feature-status` | 显示当前 generation 的条件、工单、咬合汇总 | --id <值> | 只读 |
| `work-open` | 预开/扩展非 audit 工单的 target_ids（scan 与设计角色扩写入边界都用它） | --feature <值> --kind <值> --target-ids <值> | 状态库 |
| `work-seed` | 按缺的条件各生成一张工单 | --feature <值> | 状态库 |
| `work-claim` | 按角色领取当前代一张 ready 工单，返回 claim_token 与切片 | --role <值> --allow-product-code | 状态库 |
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
| `gate` | 交付门：只读计算 PASS/FAIL；PASS 退出码 0、FAIL 退出码 1 | --feature <值> --json | 只读 |
| `export` | 按 feature 导出六份只读视图（写入 <root>/export/） | --feature <值> | 文件（<root>/export/） |
| `slice` | 取工单或 target_ids 的深度 1 切片（只读；target_ids 支持 `前缀*` 与 @文件） | — | 只读 |
| `get` | 按 id 读取一个节点 | --id <值> | 只读 |
| `find` | 按 kind / 路径前缀 / 入边起点查找节点 | — | 只读 |
| `role-prompt` | 生成可交给 DSH teammate 的角色提示（含状态库路径、允许命令与边界） | --role <值> | 只读 |
| `contract` | 输出契约；--write 刷新文档契约块 | --json | 只读（--write 时写文档） |
| `verify` | 一致性自检：契约块、角色/命令/kind 交叉引用、导出样例、写入列；不替代 doctor/行为测试 | — | 只读 |
| `doctor` | 状态库自检：悬空 bite/边/引用、陈旧 token、条件与审计配对、legacy 身份、证据产物；--fix 只清理悬空引用与陈旧 token | --fix | 只读（--fix 时状态库） |

### 咬合判决

允许值：`KEEP`、`UNNECESSARY`、`HOLLOW`、`DOC-ONLY`、`UNMAPPED`、`UNKNOWN`。

| 规则 |
|------|
| 条件未齐（七项条件与 Ready 任一为假）→ FAIL。 |
| 作用域内存在 UNNECESSARY 或 HOLLOW，且没有任何 KEEP 反证 → FAIL；咬合只采信 `bites` 表（含 actor），`attrs.bite` 仅供展示。 |
| gate 只读：不写条件、不写工单、不改节点，重复执行结果不变；PASS 退出码 0、FAIL 退出码 1。 |
| 除 Accepted 由 `feature-declare` / `feature-register` 新建时置真外，只有 work-judge(passed) 写条件；judge(failed) 把该条件及其后的条件置假，没有对应条件的工单（scan）不改条件。 |
| `BehaviorPassed` 置真前必须有一条**同 generation**、exit_code=0 且产物有效的 evidence（有产物时校验存在与 hash），gate 执行同样的检查。 |
| `retract` 会级联删除 bite；外部遗留的悬空 bite 不计入门禁（输出 ignored_dangling_bites），由 doctor 清理。 |

### 审计与证据

| 规则 |
|------|
| `work-claim`、`work-judge`、`bite` 必须带 `--actor`（或 `WXG_ACTOR` 环境变量），记录到 `work_items.claimed_by` / `judged_by` / `bites.actor`。 |
| 审计独立性：`work-judge --actor` 不得等于被审工单的 `claimed_by`；旧库迁移写入的 `legacy` 允许，但结果会带 `legacy_claim: true`，doctor 报 `legacy-identity`（不可追溯，不伪造成员）。 |
| `work-judge` 同时写 `judged_at`；一个工单的 `judged_by` 不允许被后续裁决覆盖（仅允许从空到有值）。 |
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
| I9 状态可自检 | doctor 检查悬空 bite/边/引用、陈旧 token、条件完整性、审计配对、legacy 身份与证据产物；--fix 只清理悬空引用与陈旧 token，不替人裁决。 |
| I10 审计可追溯 | work-claim / work-judge / bite 记录 actor；审计 actor 不得等于被审工单的 claimed_by；judged_by/judged_at 只写一次；gate 采信的咬合以 bites 表为准。 |
| I11 证据可追溯 | evidence-record 把命令、退出码、generation、执行者、产物 SHA-256 写入 evidence 表；doctor 校验产物存在/hash/退出码/generation 非空与 legacy 身份；judge/gate 对 BehaviorPassed 强制同代、exit_code=0 且产物有效的 evidence；重跑证据不得改写权威状态。 |

### 节点 kind

| kind | 说明 | 创建者 |
|------|------|--------|
| `requirement` | 功能声明；id 前缀 requirement:{feature}: | 声明入口 |
| `actor` | 角色 | model-architecture |
| `use_case` | 用例；satisfies 指向 requirement | model-architecture |
| `component` | 构件；depends 指向 component | model-architecture / scan 锚点 |
| `port` | 端口；associates 指向 component | model-architecture / scan 锚点 |
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
| `component` | `duty`:str |
| `port` | `port`:int、`protocol`:str |
| `classifier` | `duty`:str |
| `property` | `column`:str |
| `operation` | `http`:str、`success_code`:str、`async`:bool |
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

### 导出规则

导出只包含图里连到该 feature 的记录：01 取 requirement；02 取 satisfies 这些 requirement 的 use_case；04 取用例经 depends/associates/realizes 到达的 component 与 port；05 取用例 contains 的 operation 及其 has_input、以及 contains 指向这些 operation 的 classifier；07 每条 writes->sink 算一步，另附请求参数表（同一参数只列一次，顺序按首次出现）；测试规格取 verifies 到这些 operation/use_case 的 testcase 与 asserts 到 operation 的 assertion。缺的格子留空，禁止从任何旧文档补句。参数、测试与断言按 id 去重。

契约版本 `0.4.0`，库 schema 版本 `3`。
<!-- wxg:contract:full:end -->
