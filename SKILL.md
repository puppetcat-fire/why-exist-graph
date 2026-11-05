---
name: why-exist-graph
description: >-
  DSH 原生的“设计图谱 + 交付门”技能：登记源码仓、按 Python 源文件导入图库、声明功能、
  按角色领取工单、必要性撕咬（KEEP/UNNECESSARY 等）、设计模式有限应用、咬合覆盖约束、
  按 feature 导出只读设计视图；状态库默认 SQLite，也可切 MariaDB/MySQL/PostgreSQL 并行后端，支持常驻控制器。
  条件、工单、角色、命令、属性键、导出形状由 scripts/wxg_contract.py 定义；`wxg verify`
  校验生成文档块与导出样例是否漂移，`doctor` 校验状态库。用于 why-exist、设计一致性检查、
  质疑一块代码有没有必要、声明功能、拆分角色并行、交付前门禁（gate，PASS/FAIL 退出码 0/1）。
whenToUse: 需要把“设计/代码是否成立、功能是否交付”变成可判定状态时；或用户点名 why-exist、撕咬、交付门、声明调和、设计图谱时。
---

# why-exist-graph（DSH 原生）

一个 DSH 技能、一个 CLI（`wxg`）、一个 SQLite 状态库、一份契约。
设计目标是让“设计是否成立”和“功能是否交付”都可被机械判定，并且**文档不会和实现漂移**。

## 为什么它设计上一致

下面 21 条不变量由契约生成（见“契约”块末尾“一致性不变量”表）；`wxg verify` 校验生成文档块、命令/角色/kind/写入列交叉引用与导出样例的字节一致性（不替代 doctor 与行为测试）；`tests/test_wxg.py` 覆盖主要不变量与端到端流程（I6 的“导入器仅 Python”边界见 `references/design.md`）。

## 快速开始（在 DSH 里调用）

设 `<skill>` 为本技能目录（`.dsh/skills/why-exist-graph`），`<root>` 为状态库目录（建议工作区下 `.why-exist`）：

```powershell
$env:PYTHONUTF8=1
python <skill>/scripts/wxg.py --root <root> init
python <skill>/scripts/wxg.py --root <root> repo-add --id demo --path <源码仓>
python <skill>/scripts/wxg.py --root <root> feature-declare --id feat-x --name "小功能" `
  --statement "一句话" --acceptance @acceptance.json --constraints @constraints.json
# 咬合覆盖门禁：新 feature 默认开启 ε=1.0；--no-coverage 关闭，--coverage-epsilon 改阈值
python <skill>/scripts/wxg.py --root <root> feature-declare --id feat-y --name "严格功能" `
  --statement "一句话" --acceptance @acceptance.json --constraints @constraints.json `
  --coverage-epsilon 2.0
python <skill>/scripts/wxg.py --root <root> feature-declare --id feat-y2 --name "轻量功能" `
  --statement "一句话" --acceptance @acceptance.json --constraints @constraints.json `
  --no-coverage
# 可选：开启结构性漂移门禁；N 是允许的 UNMAPPED/DOC-ONLY 节点数上限
python <skill>/scripts/wxg.py --root <root> feature-declare --id feat-z --name "对账功能" `
  --statement "一句话" --acceptance @acceptance.json --constraints @constraints.json `
  --drift-limit 0
# work-seed 已由 feature-declare 自动完成；下面这条可重跑（幂等），不必重复
python <skill>/scripts/wxg.py --root <root> work-seed --feature feat-x
# 当前角色要写哪些 id，就先用 work-open 并进工单 target_ids（支持前缀* 通配）
python <skill>/scripts/wxg.py --root <root> work-open --feature feat-x --kind model-architecture `
  --target-ids @targets.json
python <skill>/scripts/wxg.py --root <root> work-claim --role model-architecture --actor agent-arch
python <skill>/scripts/wxg.py --root <root> ...   # 用返回的 claim_token 写图
python <skill>/scripts/wxg.py --root <root> work-finish --token <token>
python <skill>/scripts/wxg.py --root <root> work-judge --id <工单id> --verdict passed --role audit --actor auditor-1
python <skill>/scripts/wxg.py --root <root> sample --feature feat-x --seed 1   # 按 feature 作用域抽样
python <skill>/scripts/wxg.py --root <root> bite --node <id> --verdict KEEP `
  --feature feat-x --actor agent-lead
python <skill>/scripts/wxg.py --root <root> coverage --feature feat-x   # 各阶段 covered/n_required 与调度建议
# 控制器单步：默认只读列待办；--apply 只做补单/解阻塞/回收陈旧 claim
python <skill>/scripts/wxg.py --root <root> reconcile --feature feat-x
# 常驻控制器：每 5 秒跑一遍 reconcile（--once 单趟，Ctrl+C 退出）
python <skill>/scripts/wxg.py --root <root> serve --interval 5 --apply
# 切 MariaDB/MySQL 状态库（默认 SQLite；全局 --db-url 放在子命令前）
python <skill>/scripts/wxg.py --root <root> --db-url mysql://user:pass@127.0.0.1:3306/wxg init
# 切 PostgreSQL（需要 pip install 'psycopg[binary]'）
python <skill>/scripts/wxg.py --root <root> --db-url postgresql://user:pass@127.0.0.1:5432/wxg init
# 交付后改设计：继承 from-condition 之前的条件，从它起重置并 seed 下游工单
python <skill>/scripts/wxg.py --root <root> change-open --feature feat-x `
  --statement "改持久化边界" --from-condition StructureReconciled
python <skill>/scripts/wxg.py --root <root> change-diff --feature feat-x   # 两代写过的节点集合与代码锚点
# 回扫断言：只读对比 DB 图与当前代码，报 missing/new/changed/stale
python <skill>/scripts/wxg.py --root <root> sync --repo demo
# 设计-代码一致性：默认只报差异；feature-declare 加 --conformance 后 gate 强制
python <skill>/scripts/wxg.py --root <root> conformance --feature feat-x
# 裁决 BehaviorPassed（observe 单）之前，必须先有一条同 generation、exit_code=0 的 evidence：
python <skill>/scripts/wxg.py --root <root> evidence-record --feature feat-x --name unittest `
  --command "python -m unittest" --artifact <日志> --actor auditor-1
python <skill>/scripts/wxg.py --root <root> gate --feature feat-x --json   # PASS=退出码 0，FAIL=1
python <skill>/scripts/wxg.py --root <root> export --feature feat-x
```

自检：`python <skill>/scripts/wxg.py verify`（不需要已初始化状态库，且不创建 `.why-exist/`）。
状态库体检：`python <skill>/scripts/wxg.py --root <root> doctor`；加 `--fix` 清理悬空引用与陈旧 token（不改条件与裁决）。
提交质量门：见 `references/quality.md`；`evidence-record` 是证据入口，`doctor` 校验证据产物 hash 与 legacy 身份。

### 从零到 `gate PASS` 的最短路径

一条命令起步：

```powershell
python <skill>/scripts/wxg.py --root <root> up --template standard
```

`up` 建库、登记示例仓、声明 `demo` feature，并跑一次 gate（通常 FAIL，列出缺项）。
之后只剩一个循环：

1. **扫描导入**：`import-file --prepare`（这一步才创建 scan 工单）→ `work-claim --role scan`
   → `import-file --token` → `work-finish` → `work-judge`；
2. **每个条件 = 一次工单生命周期**：`work-open`（并写入边界）→ `work-claim`（拿 token）→
   写图（`upsert-node` / `upsert-edge` / `bind`）→ `work-finish` → `work-judge`。
   `implement-test` 要改产品代码，claim 时加 `--allow-product-code`。

八个条件按顺序推进；`gate` 的 `checks` 直接告诉你下一个卡在哪项，卡哪补哪，不必一次把
八条都想全。完整可跑示例见 `references/design.md` 的 checks 表与
`tests/test_wxg.py::test_full_flow_reaches_pass_gate`。

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
<!-- wxg:contract:main:end -->

## 工作流

> 首次使用先跑 `wxg up`（可选 `--feature` / `--repo` / `--path`）：一条命令完成 init、
> demo 仓、demo feature 与第一次 gate 结果；幂等、不自动裁决。之后从第 1 步开始。

1. **登记仓**：`repo-add` 把源码仓写进状态库；技能本身不含任何具体仓名（导入器当前仅 Python）。
2. **导入**：`import-file --prepare` 先预列节点 id 到 `scan` 工单，`work-claim --role scan` 领取令牌后写入；同一代内、scan 单 passed 之前，重复导入是更新不是新增；scan 单 passed 后要重扫只能 `feature-declare` 开新代（会重置条件）。
3. **声明/登记**：`feature-declare` 写 spec、`generation+1`、重置条件并自动 seed；`feature-register` 用于已有图：同代登记完全不动条件，新建/新代只置 Accepted（新代会重置条件并 supersede 旧工单），不自动派工（新代需手动 `work-seed`）。
4. **派工/领取**：`work-seed` 按缺的条件各生成一单；`work-claim` 按角色领**当前代**的 `ready` 工单，返回 `claim_token` + 深度 1 切片；大仓整仓扫描用 `--brief` 只取计数，正文用 `slice --work <id> --limit N` 按需取。
5. **扩边界/写图**：`work-seed` 的 target_ids 只是当前图作用域（通常只有 requirement 节点）；写新 id 前先用 `work-open --kind <kind> --target-ids <pattern>` 把它并进工单。写命令带令牌，id 必须落在 target_ids 内；越界直接拒绝。
6. **提交/裁决**：`work-finish` 生成 audit 单；独立 audit 角色用 `work-judge --actor <id>` 判 passed/failed，actor 不能等于被审工单的 `claimed_by`。failed 会把该条件及其后的条件置假（scan 等无对应条件的工单不改条件）。裁决 `BehaviorPassed` 前必须已登记**同 generation**、exit_code=0 的 evidence。
7. **撕咬**：`sample --feature <id>` 在作用域内随机取一个节点（`--repo` 仍可按仓抽），`bite --actor <id> --verdict KEEP|UNNECESSARY|HOLLOW|DOC-ONLY|UNMAPPED|UNKNOWN` 记录判定，同时记下当前代与阶段。`gate` 按**每个节点当前代最新一条**判决计：最新是 UNNECESSARY/HOLLOW 判 FAIL；KEEP 只反证同一节点，跨节点或旧代 KEEP 不再抵消。feature 开启 `--drift-limit N` 时，最新判决为 UNMAPPED/DOC-ONLY 的节点数超过 N 也判 FAIL。`attrs.bite` 只能由 `bite` 写，图写入命令不允许伪造。
8. **证据**：测试、HTTP 冒烟、gate、export、独立重跑用 `evidence-record` 登记命令、退出码、generation、actor 与产物 SHA-256；`doctor` 会报产物缺失、hash 变化、非零退出码与 legacy 身份。
9. **导出/交付门**：`export` 生成六份只读视图；`gate` 通过（PASS，退出码 0）前不得宣称交付；FAIL 退出码为 1，可直接接 CI。`gate` 的 `checks` 按判定顺序列出 9 项（bites / pattern / drift / construction / stale / conformance / conditions / evidence / coverage），第一个 `ok=false` 就是 FAIL 原因。`feature-status` 的 `phase` 直接给出当前阶段（第一个为假的条件）。
10. **体检**：`doctor` 检查悬空 bite/边/引用、陈旧 token、条件完整性、audit 配对、actor 缺失、legacy 身份与证据/BehaviorPassed 一致性；每个 issue 带 `fixable`，汇总有 `fixable_count` / `unfixable_checks`——`--fix` 只自动修 7 类可判定问题（悬空引用、陈旧 token、meta 版本等），`legacy-identity` 这类只能报给人看（修了等于伪造审计身份）。
11. **调谐**：`reconcile --feature <id>` 是控制器单步，默认只读、幂等；`converged` = gate PASS 且无待办，退出码 0/1。`--apply` 只做三件安全迁移：补缺失工单、解 blocked、回收超过 `--claim-ttl` 的陈旧 claim；裁决、咬合、图写入永不自动。
12. **变更集**：feature Ready 后要改设计，用 `change-open --from-condition <条件>` 开新一代：之前的条件按上一代继承为真，从该条件起重置；`work-seed` 自动补齐下游工单（含 implement-test/observe），`change-diff` 只读对比两代写过的节点与代码锚点。BehaviorPassed 必须用新代 evidence 重新证明。
13. **回扫**：`sync --repo <id>` 只读对比 DB 图与当前 AST（missing/new/changed/stale）；`import-file` 重扫时把本次未再出现的旧节点标 `stale=1`，gate 对作用域内 stale 节点 FAIL，重扫出现即清 0。
14. **常驻控制器**：`serve --interval 5 --apply` 周期性对全部 feature 跑 reconcile，只做三类安全迁移；`--once` 单趟适合 CI。它不裁决、不咬合、不写图，交付判定仍看 gate。
15. **一致性**：`conformance --feature <id>` 只读输出设计锚点、depends 的代码支撑、未声明耦合、use_case 的测试覆盖差异；孤立节点拆成 `unanchored_count`（落在 derived 组件 `contains` 内、尚未 `maps_to` 锚定）与 `truly_orphan_count`（完全无设计覆盖），derived 组件存在时带 `hint` 说明前者属正常中间态；depends 边带 `x_evidence`（derive 写入）时视为有代码依据。feature 开启 `--conformance` 时 gate 对这些差异 FAIL。它只报差异，不补节点、不生成描述。
16. **并行规划**：`plan --feature <id>` 只读输出强连通分量（必须先拆的环）、拓扑波次、最大反链与理论并行上限；`parallelism` 附 `bottleneck` 说明它受限于什么（无环时是最大反链，有环时是最大环大小）；`--level design|code|auto`，`auto` 在没有 `depends` 边时退到代码层并在输出标明实际层级，`--level code` 且作用域内没有代码节点时结果带 `hint`。一端在作用域外的依赖边作为 `dangling` 报告，不静默丢弃。
17. **盲化任务书**：`brief --work <工单id>` 生成只含写入边界、界外上游输入、产出契约、禁止事项与完成定义的说明，可 `--out` 落文件交给独立执行者；它只接收该工单的数据，结构上无法泄露其它在途工单。
18. **盲执行校验**：`blind-check --work <工单id> --result <产出.json>` 检查独立执行者的产出是否越界、是否引用未声明依赖、产出 kind 是否在契约内，输出 PASS/FAIL 与 `locality` 得分。它只做结构校验，不替代审计。
19. **影响域**：`impact --feature <id> --changed <ids>` 输出改动节点的反向可达受影响集、正向依赖集、命中的 requirement、连不到任何 requirement 的 `uncovered`（意料之外的影响面），以及落到其它 feature 的 `cross_feature`；`affected` 按反向 BFS 最短跳数拆成 `direct`（一跳内直接依赖）与 `indirect`（两跳及以上）；`--changed` 支持逗号分隔；`--remove-edges src->dst,...` 分析断掉依赖后源点失去哪些可达节点（`lost_reachable`）。
20. **声明期冲突检测**：`conflicts [--features a,b]` 两两比较 feature 的 `target_ids`，列出会重叠的写入边界与当前图上真正重叠的节点；它只报告，不拦门，但声明阶段就该看。
21. **出补丁**：`patch --work <工单id> --result <产出.json> --out <补丁.json>` 把一次盲执行产出规范成补丁（节点去重、边排序），供合并使用；它只读、只写补丁文件。
22. **合并**：`apply --patches <a.json,b.json> [--dry-run]` 由单一 reducer 合并补丁；同一节点内容冲突显式报告且不写半截，边端点未知也拒绝；冲突退出码 1。这条替换了"抢写 + 锁"的并行模型。
23. **批量导入**：`import-repo --repo <id> --feature <id> [--prepare]` 一次导入整个仓的 Python 文件（写入语义同 `import-file`）；中型仓逐文件敲 CLI 不现实。
24. **反推候选设计**：`derive --repo <id> --feature <id> [--depth N] [--exclude dirs]` 按目录把代码聚成 component 候选，用跨组调用与 import 解析（绝对与相对导入）推导 depends 候选；默认 dry-run，`--apply` 写入 `origin=derived`，可被 `bite` 质疑。只推算出 1 个组件时结果带 `hint`（目录层级不足以分组，`--depth` 不会有区别）。
25. **提升候选**：`promote --feature <id> --node <id> --token <token> --actor <id>` 把 `derived` 节点提升为 `declared` 并记录裁决者；非 derived 节点拒绝。它只记录确认，不阻塞后续修改。
26. **环成因与断边建议**：`cycles --feature <id>` 把设计层的强连通分量展开成具体依赖边，每条边带 `x_evidence`，每个环带 `shape` 与 `guidance`（`parent-child` = 父子包互依赖，建议让子包单向依赖父包而**不要**断边——断边只改可达性、不改变分层方向；`sibling` = 平级互调；`self-loop`）；`--without src->dst,...` 模拟移除依赖后还剩哪些环；`--break-set` 枚举最小断边集合（边数 ≤ 20），每项带整体代价 `cost.lost_pairs`；`--advise` 按「是否参与断边集合 + 断了丢多少可达」排序给出 `preferred`/`acceptable`/`avoid`。它只读，最终怎么改仍是设计决策。

### 设计模式与有限应用

设计模式在 0.5.0 起是一等设计决策，不是装饰：

- 用 `pattern` 节点记录模式实例，`applies` 边从具体设计元素（component/classifier/operation）指向它；04 架构导出会带上作用域内的 pattern 行。
- `attrs` 必须写 `applicability`（适用条件）与 `not_applicable`（不适用边界），gate 对缺失字段或没有 `applies` 入边的 pattern 直接 FAIL；误用/过度应用由 `UNNECESSARY` 咬合兜底，声称存在但代码里找不到实例标 `DOC-ONLY`。
- 模式目录与“有限应用原则”见 `references/patterns.md`：变化点真实出现才用、先删后抽象、一个变化轴最多一个主模式、组合模式必须写理由。

### 咬合覆盖（默认开启）

新 feature 默认开启覆盖门禁（ε=1.0）；`--no-coverage` 关闭，显式 `--coverage-epsilon ε` 覆盖默认值，重声明保留已有策略。`work-judge(passed)` 与 `gate` 都会检查该阶段覆盖：设作用域 S、阶段内已覆盖节点 n（去重）、命中节点 d（判决非 KEEP 且非 UNKNOWN），后验缺陷率 p=(1+d)/(10+n)；要求存在 m（不超过 S）使 p_m·(S-m) ≤ ε 且 n ≥ m。`coverage` 命令给出各阶段 covered / n_required / met 与调度索引（α^(i-1)·p），`next` 取**条件顺序里第一个未达标阶段**（阶段不能跳着推进）；预算有限时按索引分配额外咬合。先验 p=0.1、α=2；关闭时只报告不拦截。

注意成本：ε=1 时 `n_required` 随 S 增长（大作用域可能要求覆盖很大比例的节点）。作用域大就用 feature 拆小、调高 ε，或 `--no-coverage` 后靠 gate 其他检查兜底。

### 结构漂移（可选门禁）

`feature-declare --drift-limit N` 开启后，`gate` 统计作用域内当前代最新判决为 `UNMAPPED` 或 `DOC-ONLY` 的节点数，超过 N 直接 FAIL；未开启时仍在 gate/status 输出 `drift` 计数供人工判断。它补的是“结构与代码对不上”这一侧的强制：这一侧默认只记录，不自动判死。

### 调谐与施工中标记

`reconcile` 的输出是动作清单：`seed-ticket`（缺单）、`unblock`（依赖已 passed）、`release-stale-claim`（超过 TTL）、`retry`（失败后已回 ready）、`coverage-gap`、`drift-over-limit`、`construction-open`。前 3 类可 `--apply` 自动做，其余只报告。

施工中的代码段用 `attrs.construction=true` 标记（component/classifier/operation），gate 遇到未清除的标记直接 FAIL；完成时用一次不含该键的 upsert-node 覆盖清掉。标记不参与咬合与覆盖统计。

### 变更集

需求文本变更是 `feature-declare` 开新代（整链重置）；**设计实现变更**用 `change-open`：只在 feature Ready 后使用，从 `--from-condition` 起把条件重置为假，之前的条件按上一代继承为真（`changes` 表记录继承边界）。之后 `work-seed` 派发下游工单，`change-diff` 只读输出两代写过的节点集合（added/removed/kept）、继承/待办条件与代码锚点。被继承的条件在当前代没有审计单；`doctor` 会核对 `changes` 记录与继承条件是否一致。一个 feature 同时只允许一个未收口的变更集。

### 回扫断言

`sync --repo <id>` 重新解析登记仓的 Python 文件，与 DB 图对比：`missing`（DB 有、代码无）、`new`（代码有、DB 无）、`changed`（行号/名称变化）、`stale`（已标 stale 的节点）。只读，不写库。

`import-file` 可用同一 scan 工单重扫同一文件（`--prepare` 会把该文件已有旧节点一并并入 target_ids）：本次没再出现的旧节点标 `stale=1`，说明代码里已删除/改名；再次出现则清 0。gate 对作用域内 stale 节点直接 FAIL，必须重扫或按设计修正后再交付。

### 设计-代码一致性（conformance）

设计节点用一条 `maps_to` 边指到代码锚点（带 repo/path 的节点），不复制代码结构。`maps_to` 写入时校验方向（src 必须是 use_case/component/port，dst 必须带 repo/path）。`conformance` 只读输出：

- `anchors.missing`：use_case/component/port 没有指向代码锚点的 `maps_to`。
- `anchors.code_orphans`：作用域内没有被任何 `maps_to` 指向的 operation/classifier（只报告，不算 violation）。
- `structural.missing_backing`：component/port 的 `depends` 在两边锚定的代码节点之间找不到 calls/reads/writes 支撑。
- `structural.undeclared`：代码节点跨组件有调用，但组件之间没有 `depends`/`associates`。
- `structural.resolved_heuristically`：跨文件裸名调用被导入器标成 unmapped 时，按“作用域内唯一名字”启发式解析出的依赖数；只用于支撑判断，不写回图。
- `tests.missing`：use_case 没有 testcase 的 `verifies`。

feature 开启 `--conformance`（默认关闭）时，gate 对 `missing`/`missing_backing`/`undeclared`/`tests.missing` FAIL；code_orphans 只报告。conformance 不生成节点、不补写设计、不做字段级 diff——它是“差异清单”，不是“设计描述”。

### 状态库后端

默认 SQLite（WAL + busy_timeout=5000，单写者）。设 `WXG_DB_URL=mysql://...` / `postgresql://...` 或全局 `--db-url` 切到 MariaDB/MySQL/PostgreSQL：行级锁支持多代理并行写，同一工单领取靠原子 `UPDATE ... WHERE status='ready'` 的 rowcount，只有一个代理能拿到。MySQL 客户端是内置的纯标准库实现（`scripts/wxg_mysql.py`），不需要 pip 包；PostgreSQL 后端需要 `pip install 'psycopg[binary]'`。导出目录仍由 `--root` 决定，与后端无关。

### 常驻控制器（serve）

`serve --interval 5 --apply` 是控制器循环：每趟对所有 feature 跑 reconcile，执行补缺失工单/解 blocked/回收超过 TTL 的 claim；`--once` 只跑一趟并打印一行 JSON 摘要。裁决、咬合、图写入永不自动。Ctrl+C 退出并保留已提交状态。SQLite 下它是唯一写者，MySQL/PostgreSQL 下可多实例并行。

## 已知边界

- 导入器只有 Python AST；`repo-add --language` 仅接受 `python`，其他语言请用 `upsert-node`/`upsert-edge`（详见 `references/design.md` §5）。
- 测试执行不在 wxg 内：BehaviorPassed 只强制“必须有同 generation、exit_code=0 且产物有效的 evidence”，不校验证据真伪；需要调用方如实执行并登记（重新声明后旧代证据不再满足新代）。
- `wxg` 信任状态库文件本身：直接手改 sqlite（绕过命令）不在防护范围，`doctor` 只能发现部分不一致。
- `gate` 校验条件/咬合/证据、pattern、施工标记、作用域内 stale 节点、coverage/drift 与 conformance（开启时）；不评价图规模与设计语义质量，最小 requirement 图也可能 PASS。
- coverage 是概率性约束：新 feature 默认开启，先验、ε 与作用域大小共同决定成本；它不证明代码正确，只把“还剩多少未被抽样覆盖的风险”变成可计算量。**ε 是残余缺陷率上界，不是容差**——调小反而要求更多咬合：`(a/(b0+m))·(S−m) ≤ ε`，S=1186 时 ε=1.0 已要求覆盖 589 个节点，ε=0.01 要 1174 个。千节点级真实仓上基本不可行，应拆 feature 或调大 ε（或 `--no-coverage`）。
- drift 是计数约束：它只能保证“图与代码对不上的节点不超过 N”，不区分是漏标还是真缺实现。
- `reconcile` 只做安全迁移，不是自动交付；`converged` 以 gate PASS 为准，裁决与咬合永远要独立 actor。
- 变更集只比较“工单写过的节点集合”（evidence_ids），不存节点内容快照；要字段级 diff 需要在图写入时另记快照。
- 回扫只解析 AST：删除/改名表现为 stale 或 missing+new，跨文件移动需要人工判断；没被 `import-file` 重扫过的文件不会自动标 stale。
- conformance 依赖 `maps_to` 与现有 calls/reads/writes 边：唯一名字的启发式解析只兜住一部分跨文件裸名调用，其余 unmapped 会让结构检查偏保守；只覆盖 Python，不证明语义正确；code_orphans 只报告，不要求每个操作都进设计图。
- `plan` 只能分析图里已有的依赖边：设计图没有 `depends` 时退到代码层，粒度细且受导入器解析率影响；它给出的是结构上限，不评价任务划分是否合理。`--level code` 只分析作用域内**已包含**的代码节点；作用域只有设计元素时会返回 0 边（结果带 `hint`），需先用 `work-open --target-ids '["operation:*"]'` 把代码节点并进来。
- `brief` 的盲化是信息裁剪，只保证“不含其它工单的计划”，不保证切分本身正确。
- `blind-check` 只校验结构（边界 / 产出 kind / 依赖引用），不评价产出语义；PASS 只说明这次执行没有越界，不说明切分策略合理。
- `up` 只搭骨架，不替你跑完 8 个条件；`Engine` 只提供只读方法，写库仍走 CLI 与 claim_token；`wxg.py` 是薄入口（176 行），实现都在 `whyexist` 包里。
- `impact` 的 `closed` 用无向连通判断，偏宽松（会少报 uncovered）；`conflicts` 只看 `target_ids` 模式重叠，不看依赖时序——A 依赖 B 的产出时，边界不重叠也不该并行。
- `apply` 有意绕过 `target_ids` 写边界（它假定自己是单一执行者）；冲突只按节点内容判定，不检测语义冲突；补丁文件就是操作日志，没有单独的日志表。
- `derive` 只按目录结构给候选，不猜组件语义；import 解析支持绝对导入与相对导入（`from .` / `from ..`），但解析不到的跨包别名仍会漏；`derived` 到 `declared` 的唯一入口是 `promote`，它记录裁决者但不重新审计。
- 变更集继承的条件不在当前代重新审计，只由 `doctor` 核对 changes 记录与继承状态。
- 施工标记靠写入方自觉清除；忘了清 gate 会一直 FAIL（有意如此）。
- SQLite 已开 WAL + `busy_timeout=5000`，多代理短写排队；跨主机共享同一个 SQLite 文件仍不支持——要跨主机就换 MySQL/MariaDB 或 PostgreSQL 后端。
- MySQL 后端不支持 TLS 与 caching_sha2_password（内置客户端只实现 mysql_native_password）；PostgreSQL 后端依赖外置 psycopg 包，未安装时报可读错误。
- `serve` 是单进程循环，不是分布式控制器；多实例同时跑时只有安全迁移是幂等的，审计与写入仍由代理显式完成。
- `feature-register` 不能代替 work-judge 置真条件（0.4.0 起不再提供 `--true`）；已有图要恢复条件，仍需走 work-open → claim → finish → judge 的审计链。
- `tools/verify_reports.py` 只验证"同一份图在不同命令里的说法一致"，不验证结论对不对——后者需要外部真值。它抓得到命令间自相矛盾，抓不到"几个命令一起错"。

## 与 DSH Agent Teams 对齐

- 每个角色都可用 `role-prompt --role <role> [--token <token>] [--feature <id>]` 生成自包含的 teammate 提示（含真实状态库路径、CLI 路径、允许命令与边界；audit 的提示是“直接裁决、不 work-finish”）。
- `target_ids` 就是写入边界，适合把 scan / model-architecture / model-structure / interact / specify-test / implement-test / observe 分给不同 teammate 并行；audit 必须由独立成员执行。
- 大仓扫描：`work-claim --brief` 只给计数，正文用 `slice --work <id> --limit N` / `find --limit N` 按需取；`import-file` 的 target 校验改成精确集合 + 前缀匹配，且不再把扫描节点写进 `evidence_ids`（省掉 O(N²) 序列化）；SQLite 用 WAL + busy_timeout 让多代理短写排队。
- 本技能不依赖 Cursor；状态库、导出、文档生成全部是本地 Python 标准库；SQLite/MySQL 后端零外部依赖，PostgreSQL 后端只额外需要 psycopg。

## 文件

| 路径 | 作用 |
|------|------|
| `scripts/wxg_contract.py` | 唯一契约（条件/工单/角色/命令/属性/导出/不变量） |
| `scripts/wxg.py` | 薄入口（176 行）：准备 `sys.path`、注册 `__main__` 为 `wxg`、re-export 包内符号 |
| `scripts/whyexist/` | 实现包：db / graph / work / workflow / gates / importer / 各 `commands_*` / cli，纯函数层与 Engine |
| `scripts/wxg_mysql.py` | MySQL/MariaDB 状态库后端（纯标准库客户端，无第三方依赖） |
| `scripts/gen_sample.py` | 生成 `references/export-sample` 的确定性 fixture |
| `tools/preflight.py` | 发布前检查：测试 + 文档一致性 + 文档完整性 + `verify` + `doctor` + 报告自洽（`--release` 再加打包与包能跑）（仅源码仓） |
| `tools/doc_flow.py` | 文档一致性检查：照 `SKILL.md` 最短路径跑一遍到 `gate PASS`（仅源码仓，不随发布包分发） |
| `tools/check_docs.py` | 文档完整性：VERSION / CONTRACT_VERSION / CHANGELOG 最新条目三者一致、CHANGELOG 版本连续、design.md 节号连续 |
| `tools/verify_reports.py` | 报告自洽性：`--repo <源码仓>` 一键扫描 + derive + 6 条交叉断言，或 `--root` 检查已有库（仅源码仓） |
| `tools/verify_release.py` | 发布包独立运行验证：解压 → `up` → 最短路径 → gate PASS（仅源码仓） |
| `tools/build_release.py` | 打包发布，版本必须与契约版本一致（仅源码仓） |
| `references/contract.md` | 完整契约视图（生成块） |
| `references/patterns.md` | 设计模式目录与有限应用原则（gate 强制字段的建模示例） |
| `references/export-sample/` | 导出样例（`verify` 逐字节比较） |
| `tests/test_wxg.py` | 端到端与一致性测试 |
| `tests/test_wxg_mysql.py` | MySQL 客户端集成测试（需要本地 MariaDB，127.0.0.1:3307） |
| `tests/test_mysql_backend.py` | MySQL 状态库后端集成测试（WXG_TEST_MYSQL_URL） |
| `tests/test_pg_backend.py` | PostgreSQL 后端集成测试（WXG_TEST_PG_URL，需要 psycopg） |
| `references/design.md` | 设计说明：它如何修掉 Cursor 版的设计不一致 |
| `references/quality.md` | 提交质量门：可复现 / 可追溯 / 契约一致 / 通用安全 |
| `CHANGELOG.md` | 契约版本与行为变更记录 |
