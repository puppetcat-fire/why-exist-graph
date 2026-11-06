# 交接说明

这份文档给接手的人看：why-exist 现在是什么、能做什么、怎么验证、哪些地方别踩。

## 一句话

把"设计图谱 + 交付门"演进成了**设计期编译器**：设计图（Design IR）→ 编译器 pass
（规划 / 盲执行 / 影响域 / 一致性）→ 运行时（工单状态机 + reducer 合并）。

> 2026-11 的一次性收敛记录在 [`CAMPAIGN-2026-11.md`](CAMPAIGN-2026-11.md)：16 片契约审计、
> 12 个版本、测试 381→416、跨端产物一致性核对，以及「还没做的三件事」（都需要产品决策）。

## 当前状态

| 项 | 值 |
|---|---|
| 版本 | 见仓库根 `VERSION`（schema `9`）；本文档不写死版本号 |
| 代码 | `scripts/wxg.py` 薄入口 + `scripts/whyexist/` 包（模块数与行数会变，不写死） |
| 发布包 | `dist/v<version>/why-exist-graph-<version>.zip`（63 个文件，含 `manifest.json` 与 `archive.sha256`） |
| 安装 | `python tools/install_skill.py`：从 dist/ 挑最新包 → 备份旧目录 → 装到 `~/.dsh/skills/why-exist-graph` → 跑 `verify` 自检 |

## 能力地图

**设计图**：节点（requirement / acceptance / use_case / component / port / pattern /
operation / classifier）与边（depends / uses / applies / calls / reads / writes / maps_to /
contains / verifies / satisfies / has_acceptance / associates）。两层：`design` 与 `code`。

**追溯**：需求拆成验收条目（`acceptance`），测试指向验收条目而不是整条需求；
`trace` 出需求→验收→测试矩阵，gate 的 `traceability` 检查同一口径
（有需求无验收 → UNKNOWN，有验收无测试 → FAIL）。

**编译器 pass**（只读）：

| 命令 | 产出 |
|---|---|
| `plan` | SCC / 拓扑波次 / 最大反链 / `parallelism` + `bottleneck` |
| `cycles` | 环的成因、`shape`、`guidance`、最小断边集合、`--advise` |
| `impact` | 影响闭包 + `direct`/`indirect` 深浅 + 需求覆盖 |
| `conformance` | 锚点 / 代码支撑 / 未声明耦合 / 测试覆盖差异 |
| `brief` + `blind-check` | 盲化任务书与执行产出校验 |
| `derive` | 按目录反推 component + depends 候选 |
| `conflicts` | 多 feature 的写入边界重叠 |

**运行时**：8 条件状态机、generation、变更集（`change-open` / `change-diff`）、工单
（`work-open` / `claim` / `finish` / `judge`）、咬合（`sample` + `bite`）、证据
（`evidence-record`）、控制器（`reconcile` / `serve`）、操作日志（`patch` / `apply`）。

## 怎么验证

两层，都能一键跑：

```bash
cd why-exist-graph

# 发布前检查（八步，约 3 分钟）
PYTHONUTF8=1 python tools/preflight.py --release

# 流程验证（六条，约 1 分钟；--quick 三条约 10 秒）
# refactor-lab/ 与本仓同级，不在仓内，所以先退到上一级
cd .. && PYTHONUTF8=1 python refactor-lab/run_all.py
```

`preflight --release` 的八步：回归测试 → 文档一致性（照 SKILL 走到 gate PASS）→ 文档完整
性（版本 / CHANGELOG / design.md）→ 契约校验 → 状态库体检 → 报告自洽 → 打包 → 发布包独立
运行。

`run_all` 的六条：文档最短路径 / 变更集 / 控制器 / 真实仓扫描 / 重构回扫 / 真实仓生命周期。

## 改东西时的顺序

1. 改 `scripts/wxg_contract.py` 里的契约（命令、条件、角色、属性、导出形状）；
2. 实现；
3. `python scripts/wxg.py contract --write SKILL.md --section main` 和
   `--write references/contract.md --section full`；
4. `python scripts/wxg.py verify`；
5. 版本号三处一起改：`VERSION`、`CONTRACT_VERSION`、`tests/test_wxg.py` 的断言；
6. `CHANGELOG.md` 加条目、`references/design.md` 加一节；
7. `preflight --release`。

`tools/check_docs.py` 会拦住版本号三处不一致。

## 已知边界

完整清单在 `SKILL.md` 的「已知边界」（当前 24 条）。最容易踩的几条：

- **`coverage` 的 ε 是残余缺陷率上界**，不是容差。千节点仓上默认 ε=1.0 已要求咬合约半数
  节点，调小反而更严。
- **`apply` 有意绕过 `target_ids` 写边界**，并发安全靠 reducer 冲突检测。
- **`derive` 只按目录分组**，导入解析不到的跨包别名会漏。
- **导入器只有 Python AST**。
- **`tools/verify_reports.py` 只验证自洽**，不验证结论对不对。

## 目录

```
why-exist-graph/          技能本体
  SKILL.md                使用说明（首次响应 + 契约块 + 工作流 + 已知边界 + 文件表）
  README.md               介绍与快速开始
  CHANGELOG.md            全版本变更记录
  VERSION                 版本号唯一真源
  references/             契约全文 / 设计演进 / 模式目录 / 质量清单 / 导出样例
  scripts/                薄入口 + whyexist 包
  tests/                  回归用例
       ↑ 以上随发布包分发（build_release 的 INCLUDE 清单）

  tools/                  发布与校验工具（不随包分发）
  docs/                   产品文档与审计（不随包分发）
    PRODUCT-PLAN.md       产品定位、三层模型、路线图
    HANDOFF.md            交接说明（本文件）
    CAMPAIGN-2026-11.md   2026-11 改造战报
    audit/                16 片契约审计产物（REPORT / DECISIONS / 契约卡 / 探针）
    RELEASE-*.md          各版本发布说明（SHA 由 check_release_notes 对账）
  dist/                   发布包（每版本 zip + manifest + archive.sha256）

refactor-lab/             验证与实验（与仓同级，不随包分发）
  14 个真实仓样本、6 个验证脚本、4 份报告
```

## 技能维护：按 dreaming 反馈迭代（2026-11-06）

DSH 的 dreaming 会按实际调用给每个技能打分、记录边界缺口。这一节记录 3.3.0～3.5.1
的维护依据与结论，供下次继续。

### 依据的字段

- `skills['why-exist-graph'].counts`：`boundaryGaps`（边界缺口）、`misapplied`、`partial`
- `metrics`：`boundaryAccuracy`（边界判断准确率）、`wasteRate`（加载的技能 token 中被浪费的比例）
- `learned`：`knownFailures` / `actualScope` / `cheaperAlternatives` / `preconditions`
- `episodes.jsonl` 每次调用：`task.userGoal`、`prediction.fit`、`judge.verdict`、
  `cost.skillLoad`、`trace.turnEnd`、`trace.observedMs`

### 已经做过什么

| 版本 | 依据 | 改动 |
|---|---|---|
| 3.3.0 | `knownFailures` 五条都在说「用临时探针替代 verify/doctor/gate，超时无结论」 | SKILL.md 加「首次响应」节：先跑三条命令拿退出码；**能力边界写进 description**——模型读的是 description，不是正文 |
| 3.3.1 | `cheaperAlternatives`：「做契约盘点时 grep 比加载技能更快」 | 补「想要契约清单：`contract --json` 一条命令」+「什么时候不该加载」对照表 |
| 3.4.0 | wasteRate 只从 42.5% 降到 38%——指令改对了，但加载成本本身太大 | 契约块分层：main 只放结构（命令/角色/条件），10 张规则表 + 21 条不变量进 full 块。SKILL.md 60.6KB → 45.4KB |
| 3.4.1 | 「文件」节随十几版改动过期 | 拆两张表（随包分发 / 仅源码仓）、补 4 项、修 3 处过期描述，22 个路径逐个验证存在 |
| 3.5.0 | 第 18 次调用：用户拿 Java 仓库做重构，probe 预测 `fit` 仅 0.18，`likelyPitfalls` 写「Java 无法进图库」 | 3.3.0 把「多文件行为契约盘点」排除过头了——`feature` / `plan` / `brief` / `impact` 这层不依赖导入器。`whenToUse` 加回「重构落点规划」，非 Python 边界改成分层说明 |
| 3.5.1 | 查 `%TEMP%` 发现 304MB 残留 | 安装器只留最近 3 个备份；一次性清理 95 个临时目录 |
| 3.6.0 | 不是 dreaming：四仓重构项目实测「gate 全程 PASS 而 FR-CV-06/07、FR-XWS-04/05/10 一条测试都没有」，`coverage.enforced=false`、`bites=[]` | 加追溯门：`acceptance` 节点 + `has_acceptance` 边、`trace` / `acceptance-add` / `acceptance-import` 三条命令；gate 对「有需求无验收」判 UNKNOWN（退出码 1）、「有验收无测试」判 FAIL |
| 3.6.1 | 3.6.0 后自检发现同一"验收"有三份表示（feature JSON / requirement attrs / acceptance 节点），导出读 A、门禁读 C | 收成单一来源：导出只读节点、声明不再写 `x_acceptance`、doctor 四类验收结构检查（只报告） |
| 3.7.0 | 审计 P2.12 一直挂着的两处：`bite --feature` 会顺手扩作用域、`apply` 无 token 无边界 | 门的两个输入口上锁：`bite` 要求节点已在作用域（`--allow-new-scope` 显式承担）、`apply` 落库要 token + 落 `target_ids`、doctor 报 `bite-out-of-scope` |
| 3.8.0 | 3.6/3.7 之后验收条目只进得了门禁，进不了任务书与状态：执行者得自己跑 trace 才知道验收长什么样 | `brief` 加 `acceptance_items`（边界内需求的验收条目），`feature-status` 加 `traceability` 摘要（与 trace/gate 同口径） |
| 3.9.0 | 验收边只有 doctor 事后报告结构问题，`upsert-edge` 什么都放行 | 结构约束挪到写入期：`has_acceptance` 两端 kind 固定且一条验收只能属于一条需求；`verifies` 指向 acceptance 时 src 必须是 testcase；doctor 退为兜旧库 |
| 3.9.1 | 四仓项目迁验收时暴露：`main` 是伞节点却被算成"没验收的需求" | `trace`/`gate` 对 `requirement:{f}:main` 豁免（有其它需求时），单列 `aggregate_requirements`；唯一需求或自己登记验收时不豁免 |
| 3.10.0 | 3.9.1 后 gate 说"742 条验收没测试"就没了下文，得自己翻 JSON 找从哪补 | `trace --md` 按缺口降序出人读矩阵、`--requirement` 钻取；gate 追溯 FAIL 带 `top_gaps` 与 `next` 提示 |
| 3.11.0 | 3.10 的 `top_gaps` 只按缺口数量排，四仓首屏被 P1/P2 条数多的需求占满 | 接入 `x_priority`：矩阵与 `top_gaps` 按"优先级 → 缺口数 → id"排；没登记按最低优先级不报错；md 多一列优先级 |
| 3.12.0 | 追溯门只问"有没有 testcase 指向"，一个没路径的规格节点也能满足 | 验收覆盖要求代码锚点（节点 path 或 attrs.path）；纯规格单列 `acceptance_spec_only`，gate 理由里点出；文件级校验留给项目侧 |
| 3.13.0 | 四仓补 AUTH 验收测试时，`trace --requirement` 只给"缺 1 条"，不说哪条 | 钻取加 `items` 明细（id/序号/条文/是否被带锚点测试覆盖/测试 id），`--md` 出「验收条目明细」表 |
| 3.14.0 | 登记 10 条测试要写 10 节点 + 10 边，项目侧只好自造 `batch_write2.py` 循环内部 API | 加 `bulk` 命令：JSONL 批量写节点与边，先全量校验再整批落库（token+target 边界不变），替代那类自造脚本 |

### 还没解决的

- **`boundaryGaps` 仍是 10、`wasteRate` 仍是 38.4%**——3.3.0 之后没有新的 judge 数据，
  这些改动还没被验证过。
- **「技能不做需求挖掘」这条能力缺口是真的**：probe 自己指出「无法从 Java 代码自动推导
  出全部需求和用例」。这不是措辞问题，是能力边界；要不要补取决于产品定位。
- **测试临时目录还会漏**：全量测试被外部超时 kill 时 `tearDown` 不执行。

### 下次从哪继续

1. 先看 `~/.dsh/dreaming/state.json` 里 `skills['why-exist-graph']` 的 `lastUsedAt`
   与 `counts`。**如果还停在 2026-11-06 07:32、n=17，说明技能没被调用过——不要再改描述
   造版本，改了也没有数据能验证。**
2. 有新 judge 数据后重点看两件事：
   - `boundaryAccuracy` 是否从 0.412 上升（3.5.0 的定位修正是否见效）
   - `wasteRate` 是否从 0.384 下降（3.4.0 的分层是否见效）
3. 如果两者都没动，问题不在措辞，考虑动能力：例如给非 Python 仓库一个「从现有节点
   反推 use_case 候选」的只读命令。
4. 3.6.0 的追溯门还没在真实项目上跑到全绿：四仓重构项目只把 7 条画布需求补上测试并
   移出基线，其余 97 条仍是缺口。下次可以拿它当验收对象：`wxg trace --feature
   four-repo-rebuild` 看还有多少验收条目没有测试。

## 下一步方向

按价值排序，都还没做：

1. **更多语言的导入器**：现在只有 Python AST。这是最大缺口——设计期编译器的价值不该
   绑定一种语言。
2. **增量扫描**：`import-repo` 是全量重扫。2.78 量出写入约 5k 节点/秒，大仓上增量会明显。
3. **`coverage` 的可用性**：千节点仓上默认约束不可行。要么按阶段估算成本并提示，要么给
   "小作用域"模式。
4. **真实重构**：`httpie` 只诊断到设计图，没做重构。那是检验"设计期编译器能否指导真实
   重构"的唯一办法。
