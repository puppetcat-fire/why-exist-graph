# why-exist-graph

> DSH 原生的「设计图谱 + 交付门」技能：把“一块代码/一个功能到底有没有必要、设计是否成立、是否真的交付了”变成可机械判定的状态。
>
> *A DSH-native "design graph + delivery gate" skill that turns design-vs-code and delivery claims into mechanically checkable state.*

> CI：[`.github/workflows/ci.yml`](.github/workflows/ci.yml)（ubuntu + windows × Python 3.10/3.12/3.13）。

## 为什么

代码评审里最常见、也最难回答的三个问题是：

1. **这块代码/这个功能有没有必要存在？**（还是历史遗留、拍脑袋需求）
2. **设计是否和实现对得上？**（文档说一套、代码做一套）
3. **交付是否真的完成？**（测试跑过吗？谁审计的？证据在哪？）

`why-exist-graph` 把这三件事落成一套本地、可审计、可机械检查的状态机：

- 一份**唯一契约**（条件、工单、角色、命令、属性键、导出形状），CLI 与文档都由它生成；
- 一个**SQLite 设计图谱**（需求、用例、构件、类/操作、参数、交互、数据流、测试、断言）；
- 一套**8 条件交付门**（Accepted → 架构/结构/交互调和 → 测试规格/实现 → 行为通过 → Ready）；
- 一个**独立审计链**（claim_token 写入边界、独立 audit 角色、同代证据、KEEP 反咬）；
- 六份**只读导出视图**（需求/用例/架构/类图/数据流/测试规格），缺就留空，不补旧文档。

## 特性

- **单一契约**：`scripts/wxg_contract.py` 是唯一真源；`scripts/wxg.py` 的 CLI、`SKILL.md` 与 `references/contract.md` 的契约块、导出样例都由它生成，`wxg verify` 逐字节校验漂移。
- **门禁不可旁路**：条件只能由 `work-judge(passed)` 置真（Accepted 由声明/登记新建置真）；`feature-register --true` 已移除；`work-claim` 只发当前 generation 工单；`gate` FAIL 退出码 1。
- **证据同代**：BehaviorPassed 需要同一 generation、`exit_code=0`、产物存在且 SHA-256 一致的 evidence；重新声明后旧代证据失效。
- **咬合可追溯**：`attrs.bite` 只能由 `bite` 写，gate 只采信 `bites` 表（含 actor）；判决按**节点当前代最新一条**计，KEEP 只反证同一节点。
- **设计模式有限应用**：`pattern` 节点必须写 `applicability`/`not_applicable` 并被 `applies` 挂到具体设计元素，否则 gate FAIL；模式目录见 `references/patterns.md`。
- **失败历史一等化**：每次 `work-judge` 写 `judge_history`，passed 清空陈旧 `fail_reason`；`doctor` 校验裁决历史与工单关联。
- **覆盖可计算（默认开启）**：新 feature 默认 `--coverage-epsilon 1.0`，judge/gate 按“已覆盖节点 × 后验缺陷率”检查阶段覆盖；`--no-coverage` 显式关闭，`coverage` 命令输出 n_required 与调度建议。
- **结构漂移可门禁（可选）**：`--drift-limit N` 开启后，gate 统计当前代最新判决为 UNMAPPED/DOC-ONLY 的节点数，超限 FAIL；未开启只报告。
- **大图友好**：`work-claim --brief` 只返回切片计数，`slice`/`find` 支持 `--limit`；导入校验改为精确集合 + 前缀匹配，扫描不再把节点 id 写进 `evidence_ids`。
- **控制器单步**：`reconcile` 默认只读、幂等，`--apply` 只做补缺失工单/解阻塞/回收超过 TTL 的陈旧 claim；裁决、咬合、图写入永不自动，`converged` 以 gate PASS 为准。
- **施工中标记**：`construction` 布尔 attr 标出正在改的代码节点，gate 遇到未清除标记直接 FAIL；清标记 = 一次不含该键的 upsert-node 覆盖。
- **WAL**：连接显式 `journal_mode=WAL` + `busy_timeout=5000`，多进程短写排队；单写者语义不变。
- **并行状态库**：设 `WXG_DB_URL=mysql://...` 或 `postgresql://...`（或全局 `--db-url`）切到 MariaDB/MySQL/PostgreSQL，行级锁支持多代理并行写；MySQL 客户端内置（纯标准库），PostgreSQL 需要 `pip install 'psycopg[binary]'`；同一工单仍靠原子 UPDATE 只让一个代理领到。
- **常驻控制器**：`serve --interval N [--apply] [--once]` 周期性对全部 feature 跑 reconcile，只做补单/解阻塞/回收陈旧 claim；裁决、咬合、图写入永不自动。
- **变更集**：交付后改设计用 `change-open --from-condition`，上游条件按上一代继承、下游重置并自动派单；`change-diff` 只读对比两代写过的节点集合与代码锚点，行为证据必须在新代重新登记。
- **回扫断言**：`sync --repo` 只读对比 DB 图与当前 AST（missing/new/changed/stale）；`import-file` 重扫把消失的旧节点标 `stale=1`，gate 会拦未清除的 stale 节点。
- **设计-代码一致性**：`maps_to` 边把设计节点锚到代码；`conformance` 只读输出缺锚点、depends 缺代码支撑、未声明耦合、use_case 缺测试，以及代码侧没进设计的孤儿节点；跨文件裸名调用按“唯一名字”做一次读时启发式解析。feature 开启 `--conformance` 后 gate 对 violations FAIL，默认只报告、不生成描述。
- **并行规划（`plan`）**：从依赖图算强连通分量、拓扑波次、最大反链（Dilworth）与理论并行上限；`--level auto` 在没有设计边时退到代码层，并在输出标明实际层级。
- **盲化任务书（`brief`）**：给一张工单生成只含写入边界、界外上游输入、产出契约与完成定义的说明；结构上只接收该工单数据，无法泄露全局计划。
- **盲执行校验（`blind-check`）**：拿任务书与独立执行者的产出，检查是否越界、是否引用未声明依赖、产出 kind 是否在契约内，输出 PASS/FAIL 与 locality 得分。
- **一条命令起步（`up`）**：在未初始化目录直接跑，完成 init + demo 仓 + demo feature + 第一次 gate 结果；幂等、不自动裁决。
- **库 API（`Engine`）**：`from whyexist import Engine`，在 Python 里直接调 `plan` / `brief` / `blind_check` / `gate` / `impact`，只读。
- **影响域闭包（`impact`）**：改一个节点，输出受影响的节点、命中的 requirement，以及连不到任何 requirement 的 `uncovered`；`--remove-edges src->dst` 分析断掉依赖后源点失去哪些可达节点。
- **声明期冲突检测（`conflicts`）**：两两比较 feature 的 `target_ids`，事先列出会重叠的写入边界，避免并行抢写同一块。
- **补丁合并（`patch` / `apply`）**：子任务产出补丁，由单一 reducer 合并；同一节点内容冲突显式报告且不写半截，结果与补丁顺序无关。
- **批量导入（`import-repo`）**：一次导入整个仓的 Python 文件，写入语义与 `import-file` 一致；中型仓逐文件敲 CLI 不现实。
- **反推候选设计（`derive`）**：按目录把代码聚成 component 候选，用跨组调用与 import 解析推导 depends；写 `origin=derived`，可被咬合质疑。
- **提升候选（`promote`）**：把 `derived` 候选提升为 `declared` 并记录裁决者；只记录确认，不阻塞后续修改。
- **环成因（`cycles`）**：把设计层的强连通分量展开成具体依赖边，每条边带文件证据；自环单独列；`--without src->dst` 可模拟移除依赖，`--break-set` 枚举最小断边集合并给出整体代价（`lost_pairs` / `affected_count`），`--advise` 按「是否参与断边集合 + 断了丢多少可达」排序给建议。
- **状态库自检**：`doctor` 检查悬空 bite/边/引用、陈旧 token、条件完整性与审计配对、legacy 身份、证据产物、裁决历史与 pattern 必填字段；`--fix` 只清理悬空引用与陈旧 token，不替人裁决。
- **DSH Agent Teams 友好**：`role-prompt` 生成可交给 teammate 的角色提示（真实状态库/CLI 路径、允许命令与边界）；`target_ids` 就是并行写入边界，audit 必须由独立成员执行。
- **纯标准库**：Python ≥ 3.10 + SQLite（可选 MariaDB/MySQL 内置客户端、PostgreSQL 需 psycopg），默认路径无第三方依赖；提供确定性导出样例与全量回归用例。

## 安装

要求：Python ≥ 3.10；[DSH（DeepSeek Harness）](https://github.com/deepseek-ai/deepseek-harness) 工作区。
状态库默认 SQLite；MySQL/MariaDB 后端用内置客户端（无需额外依赖）；PostgreSQL 后端需要
`pip install 'psycopg[binary]'`。

方式一：放成 DSH 技能（推荐）

```bash
git clone <this-repo-url> <workspace>/.dsh/skills/why-exist-graph
```

或从 GitHub Releases 下载 `why-exist-graph-<version>.zip`，解包到 `<workspace>/.dsh/skills/why-exist-graph`。

方式二：只作为普通 Python CLI 使用（无需 DSH）

```bash
python scripts/wxg.py --root .why-exist init
```

## 快速开始

```powershell
$env:PYTHONUTF8 = "1"
$wxg = "scripts/wxg.py"

python $wxg --root .why-exist init
python $wxg --root .why-exist repo-add --id demo --path path/to/your/repo
python $wxg --root .why-exist feature-declare --id feat-x --name "小功能" `
  --statement "一句话" --acceptance "@acceptance.json" --constraints "@constraints.json"

# 用 work-open 扩展本角色的写入边界，再领工单
python $wxg --root .why-exist work-open --feature feat-x --kind model-architecture `
  --target-ids "@targets.json"
python $wxg --root .why-exist work-claim --role model-architecture --actor agent-arch

# 用返回的 claim_token 写节点/边，然后提交、由独立 audit 角色裁决
python $wxg --root .why-exist upsert-node --token <token> --data "@node.json"
python $wxg --root .why-exist work-finish --token <token>
python $wxg --root .why-exist work-judge --id <工单id> --verdict passed `
  --role audit --actor auditor-1

# 裁决 BehaviorPassed 前先登记同代证据
python $wxg --root .why-exist evidence-record --feature feat-x --name unittest `
  --command "python -m unittest" --artifact test.log --actor auditor-1

python $wxg --root .why-exist gate --feature feat-x --json   # PASS=0 / FAIL=1
python $wxg --root .why-exist export --feature feat-x
```

> PowerShell 5.1 下内联 JSON 的引号会被改写：`--acceptance/--constraints/--data/--spec/--target-ids/--node-ids/--ids`
> 都支持 `@文件路径`。完整说明见 `SKILL.md`。

## 自检与开发

```bash
PYTHONUTF8=1 python scripts/wxg.py verify          # 输出 ok:true 即通过
PYTHONUTF8=1 python -m unittest discover -s tests -v   # 汇总行 OK 即通过（数量以汇总行为准；MySQL/PG 后端集成用例默认跳过）
python scripts/gen_sample.py                        # 重建导出样例（--write 刷新 references/export-sample）
```

修改契约的流程：改 `scripts/wxg_contract.py` → `python scripts/wxg.py contract --write SKILL.md --section main` →
`python scripts/wxg.py contract --write references/contract.md --section full` → `python scripts/wxg.py verify`。
不要手改生成块。

## 仓库结构

| 路径 | 作用 |
|------|------|
| `SKILL.md` | 技能说明（frontmatter + 契约生成块 + 工作流） |
| `references/contract.md` | 完整契约视图（生成块） |
| `references/design.md` | 设计说明与已知边界 |
| `references/patterns.md` | 设计模式目录与有限应用原则 |
| `references/quality.md` | 提交质量门 |
| `references/export-sample/` | 六份导出样例（`verify` 逐字节校验） |
| `scripts/wxg_contract.py` | 唯一契约（条件/工单/角色/命令/属性/导出/不变量） |
| `scripts/wxg.py` | CLI：图库、工单状态机、导入、bite、coverage、gate、export、doctor、verify、reconcile、serve |
| `scripts/wxg_mysql.py` | MySQL/MariaDB 状态库客户端（纯标准库） |
| `scripts/gen_sample.py` | 生成确定性导出样例 |
| `tests/test_wxg.py` | 端到端与一致性测试 |
| `tests/test_wxg_mysql.py` | MySQL 客户端集成测试（连不上 MariaDB 时整类跳过） |
| `tests/test_mysql_backend.py` | MySQL 后端集成测试（需 `WXG_TEST_MYSQL_URL`） |
| `tests/test_pg_backend.py` | PostgreSQL 后端集成测试（需 `WXG_TEST_PG_URL` 与 psycopg） |
| `tools/build_release.py` | 构建确定性发布 zip + manifest |
| `.github/workflows/` | CI（多平台/多 Python 版本）与 tag 发版 |

运行时状态库默认在 `--root`（建议工作区下 `.why-exist/`），不要提交进 git；也可以用 `WXG_DB_URL`
指向 MariaDB/MySQL，导出目录仍由 `--root` 决定。

## 设计原则（摘要）

- **图库是唯一权威，文档只是视图**；导出缺数据就留空，禁止从旧文档补句。
- **判定与状态变更分离**：`gate`/`verify`/`slice`/`get`/`find` 只读；条件只由 `work-judge` 改。
- **写入有边界**：图内容写入需要 claim_token 且落在工单 `target_ids` 内；角色只能调用自己 ROLES 里的命令。
- **审计独立**：judge actor ≠ 被审工单 claimed_by；`judged_by` 只写一次；legacy 身份由 doctor 提示不可追溯。
- **同代证据**：BehaviorPassed 的证据按 generation 记账，重声明后必须在新代重新跑测试并登记。
- **模式是决策**：pattern 必须写适用条件与不适用边界、必须挂到具体设计元素；过度应用由 UNNECESSARY 咬合反证。
- **判决按最新**：同一节点后一次咬合覆盖前一次，跨节点 KEEP 不抵消；失败历史只增不删。

更完整的设计取舍与已知边界见 [`references/design.md`](references/design.md)。

## 已知边界

- 导入器仅 Python AST；其他语言用 `upsert-node`/`upsert-edge` 手工建图。
- 测试执行不在本工具内：BehaviorPassed 只强制“有同代有效 evidence”，不校验证据真伪。
- 本工具信任状态库文件本身；绕过命令直接改 sqlite 不在防护范围（doctor 只能发现部分不一致）。
- `gate` 只校验条件/咬合/证据、pattern 必填边界、coverage 与 drift 策略，不评价图规模与设计语义质量。
- coverage 是概率约束：新 feature 默认开启，大作用域成本高（n_required 随 S 增长），建议拆 feature 或调 ε。
- drift 是计数约束：只保证“图与代码对不上的节点不超过 N”，不区分漏标与真缺实现。
- `reconcile` 只做安全迁移，不是自动交付；施工标记靠写入方自觉清除，忘了清 gate 会一直 FAIL。
- 变更集只比较工单写过的节点集合（evidence_ids），不存节点内容快照；继承条件不在当前代重新审计。
- 回扫只解析 AST，跨文件移动表现为 missing+new 需人工判断；没被重扫的文件不会自动标 stale。
- conformance 只报差异，依赖导入器的 calls/reads/writes；唯一名字启发式只兜住部分跨文件裸名调用，其余 unmapped 会让结构检查偏保守；code_orphans 只报告，不要求每个操作都进设计图，也不覆盖非 Python 文件。
- MySQL 后端只支持 `mysql_native_password`，没有 TLS/caching_sha2；需要 TLS 的云数据库暂时连不上。
- PostgreSQL 后端需要外置 `psycopg`（`pip install 'psycopg[binary]'`），没装时连接报可读错误。
- `serve` 是单进程循环，不是分布式调度器；多实例并行时只有安全迁移是幂等的。

## 版本

schema 9：主实现已拆进 `whyexist` 包（`wxg.py` 只剩薄入口）、分析命令齐全（plan / cycles / impact / derive / conformance）、工具链完整（preflight / doc_flow / verify_reports）。完整变更记录见 [`CHANGELOG.md`](CHANGELOG.md)。

当前版本号以 [`VERSION`](VERSION) 为唯一真源，本文档不写死——写死就会漂移（历史上出现过 2.23.0 / 2.42.0 / 2.67.0 三处不一致）。GitHub Releases 会附带可安装 zip 与 SHA-256。

## License

[MIT](LICENSE)
