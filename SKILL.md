---
name: why-exist-graph
description: >-
  DSH 原生的“设计图谱 + 交付门”技能：登记源码仓、按 Python 源文件导入图库、声明功能、
  按角色领取工单、必要性撕咬（KEEP/UNNECESSARY 等）、按 feature 导出只读设计视图。
  条件、工单、角色、命令、属性键、导出形状由 scripts/wxg_contract.py 定义；`wxg verify`
  校验生成文档块与导出样例是否漂移，`doctor` 校验状态库。用于 why-exist、设计一致性检查、
  质疑一块代码有没有必要、声明功能、拆分角色并行、交付前门禁（gate，PASS/FAIL 退出码 0/1）。
whenToUse: 需要把“设计/代码是否成立、功能是否交付”变成可判定状态时；或用户点名 why-exist、撕咬、交付门、声明调和、设计图谱时。
---

# why-exist-graph（DSH 原生）

一个 DSH 技能、一个 CLI（`wxg`）、一个 SQLite 状态库、一份契约。
设计目标是让“设计是否成立”和“功能是否交付”都可被机械判定，并且**文档不会和实现漂移**。

## 为什么它设计上一致

下面 11 条不变量由契约生成（见“契约”块末尾“一致性不变量”表）；`wxg verify` 校验生成文档块、命令/角色/kind/写入列交叉引用与导出样例的字节一致性（不替代 doctor 与行为测试）；`tests/test_wxg.py` 覆盖主要不变量与端到端流程（I6 的“导入器仅 Python”边界见 `references/design.md`）。

## 快速开始（在 DSH 里调用）

设 `<skill>` 为本技能目录（`.dsh/skills/why-exist-graph`），`<root>` 为状态库目录（建议工作区下 `.why-exist`）：

```powershell
$env:PYTHONUTF8=1
python <skill>/scripts/wxg.py --root <root> init
python <skill>/scripts/wxg.py --root <root> repo-add --id demo --path <源码仓>
python <skill>/scripts/wxg.py --root <root> feature-declare --id feat-x --name "小功能" `
  --statement "一句话" --acceptance @acceptance.json --constraints @constraints.json
# work-seed 已由 feature-declare 自动完成；下面这条可重跑（幂等），不必重复
python <skill>/scripts/wxg.py --root <root> work-seed --feature feat-x
# 当前角色要写哪些 id，就先用 work-open 并进工单 target_ids（支持前缀* 通配）
python <skill>/scripts/wxg.py --root <root> work-open --feature feat-x --kind model-architecture `
  --target-ids @targets.json
python <skill>/scripts/wxg.py --root <root> work-claim --role model-architecture --actor agent-arch
python <skill>/scripts/wxg.py --root <root> ...   # 用返回的 claim_token 写图
python <skill>/scripts/wxg.py --root <root> work-finish --token <token>
python <skill>/scripts/wxg.py --root <root> work-judge --id <工单id> --verdict passed --role audit --actor auditor-1
python <skill>/scripts/wxg.py --root <root> bite --node <id> --verdict KEEP --actor agent-lead
# 裁决 BehaviorPassed（observe 单）之前，必须先有一条同 generation、exit_code=0 的 evidence：
python <skill>/scripts/wxg.py --root <root> evidence-record --feature feat-x --name unittest `
  --command "python -m unittest" --artifact <日志> --actor auditor-1
python <skill>/scripts/wxg.py --root <root> gate --feature feat-x --json   # PASS=退出码 0，FAIL=1
python <skill>/scripts/wxg.py --root <root> export --feature feat-x
```

自检：`python <skill>/scripts/wxg.py verify`（不需要已初始化状态库，且不创建 `.why-exist/`）。
状态库体检：`python <skill>/scripts/wxg.py --root <root> doctor`；加 `--fix` 清理悬空引用与陈旧 token（不改条件与裁决）。
提交质量门：见 `references/quality.md`；`evidence-record` 是证据入口，`doctor` 校验证据产物 hash 与 legacy 身份。

> **JSON 参数**：`--acceptance` / `--constraints` / `--data` / `--spec` / `--target-ids` /
> `--node-ids` / `--ids` 都支持 `@文件路径`（PowerShell 5.1 下内联 JSON 的双引号会被改写；
> `--target-ids` 另支持 `前缀*` 通配）。
>
> **Windows 沙箱**：本技能在 Windows 上用默认 mode 建临时目录，规避 DSH `windows-acl` 沙箱下
> `tempfile` 的 0o700 目录 DACL 为空的问题（DSH discussion #4290），所以 `verify` 在 DSH 里应能直接跑通。

## 契约（生成块，勿手改）

<!-- wxg:contract:main:begin -->
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
<!-- wxg:contract:main:end -->

## 工作流

1. **登记仓**：`repo-add` 把源码仓写进状态库；技能本身不含任何具体仓名（导入器当前仅 Python）。
2. **导入**：`import-file --prepare` 先预列节点 id 到 `scan` 工单，`work-claim --role scan` 领取令牌后写入；同一代内、scan 单 passed 之前，重复导入是更新不是新增；scan 单 passed 后要重扫只能 `feature-declare` 开新代（会重置条件）。
3. **声明/登记**：`feature-declare` 写 spec、`generation+1`、重置条件并自动 seed；`feature-register` 用于已有图：同代登记完全不动条件，新建/新代只置 Accepted（新代会重置条件并 supersede 旧工单），不自动派工（新代需手动 `work-seed`）。
4. **派工/领取**：`work-seed` 按缺的条件各生成一单；`work-claim` 按角色领**当前代**的 `ready` 工单，返回 `claim_token` + 深度 1 切片。
5. **扩边界/写图**：`work-seed` 的 target_ids 只是当前图作用域（通常只有 requirement 节点）；写新 id 前先用 `work-open --kind <kind> --target-ids <pattern>` 把它并进工单。写命令带令牌，id 必须落在 target_ids 内；越界直接拒绝。
6. **提交/裁决**：`work-finish` 生成 audit 单；独立 audit 角色用 `work-judge --actor <id>` 判 passed/failed，actor 不能等于被审工单的 `claimed_by`。failed 会把该条件及其后的条件置假（scan 等无对应条件的工单不改条件）。裁决 `BehaviorPassed` 前必须已登记**同 generation**、exit_code=0 的 evidence。
7. **撕咬**：`sample` 从仓内节点均匀随机取一个，`bite --actor <id> --verdict KEEP|UNNECESSARY|HOLLOW|DOC-ONLY|UNMAPPED|UNKNOWN` 记录判定；`gate` 在无 KEEP 反证时对 UNNECESSARY/HOLLOW 判 FAIL。`attrs.bite` 只能由 `bite` 写，图写入命令不允许伪造。
8. **证据**：测试、HTTP 冒烟、gate、export、独立重跑用 `evidence-record` 登记命令、退出码、generation、actor 与产物 SHA-256；`doctor` 会报产物缺失、hash 变化、非零退出码与 legacy 身份。
9. **导出/交付门**：`export` 生成六份只读视图；`gate` 通过（PASS，退出码 0）前不得宣称交付；FAIL 退出码为 1，可直接接 CI。
10. **体检**：`doctor` 检查悬空 bite/边/引用、陈旧 token、条件完整性、audit 配对、actor 缺失、legacy 身份与证据/BehaviorPassed 一致性；`doctor --fix` 只清理悬空引用与陈旧 token，不替人裁决。

## 已知边界

- 导入器只有 Python AST；`repo-add --language` 仅接受 `python`，其他语言请用 `upsert-node`/`upsert-edge`（详见 `references/design.md` §5）。
- 测试执行不在 wxg 内：BehaviorPassed 只强制“必须有同 generation、exit_code=0 且产物有效的 evidence”，不校验证据真伪；需要调用方如实执行并登记（重新声明后旧代证据不再满足新代）。
- `wxg` 信任状态库文件本身：直接手改 sqlite（绕过命令）不在防护范围，`doctor` 只能发现部分不一致。
- `gate` 只校验条件/咬合/证据，不评价图规模与设计质量；最小 requirement 图也可能 PASS，语义由使用方判断。
- `feature-register` 不能代替 work-judge 置真条件（0.4.0 起不再提供 `--true`）；已有图要恢复条件，仍需走 work-open → claim → finish → judge 的审计链。

## 与 DSH Agent Teams 对齐

- 每个角色都可用 `role-prompt --role <role> [--token <token>] [--feature <id>]` 生成自包含的 teammate 提示（含真实状态库路径、CLI 路径、允许命令与边界；audit 的提示是“直接裁决、不 work-finish”）。
- `target_ids` 就是写入边界，适合把 scan / model-architecture / model-structure / interact / specify-test / implement-test / observe 分给不同 teammate 并行；audit 必须由独立成员执行。
- 本技能不依赖 Cursor；状态库、导出、文档生成全部是本地 Python 标准库 + SQLite。

## 文件

| 路径 | 作用 |
|------|------|
| `scripts/wxg_contract.py` | 唯一契约（条件/工单/角色/命令/属性/导出/不变量） |
| `scripts/wxg.py` | CLI：图库、feature、工单状态机、导入、bite、gate、export、doctor、verify |
| `scripts/gen_sample.py` | 生成 `references/export-sample` 的确定性 fixture |
| `references/contract.md` | 完整契约视图（生成块） |
| `references/export-sample/` | 导出样例（`verify` 逐字节比较） |
| `tests/test_wxg.py` | 端到端与一致性测试 |
| `references/design.md` | 设计说明：它如何修掉 Cursor 版的设计不一致 |
| `references/quality.md` | 提交质量门：可复现 / 可追溯 / 契约一致 / 通用安全 |
| `CHANGELOG.md` | 契约版本与行为变更记录 |
