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

**设计图**：节点（requirement / use_case / component / port / pattern / operation /
classifier）与边（depends / uses / applies / calls / reads / writes / maps_to /
contains / verifies / satisfies / associates）。两层：`design` 与 `code`。

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
why-exist-graph/          技能本体（随发布包分发）
  SKILL.md                使用说明（工作流 + 边界 + 文件表）
  README.md               介绍与快速开始
  CHANGELOG.md            全版本变更记录
  docs/PRODUCT-PLAN.md    产品定位、三层模型、路线图与进度
  references/
    contract.md           契约全文（生成）
    design.md             设计决策演进记录
    patterns.md           设计模式目录
    quality.md            质量清单
  scripts/                薄入口 + whyexist 包
  tests/                  回归用例
  tools/                  发布工具（不随包分发）
  dist/                   发布包

refactor-lab/             验证与实验（不随包分发）
  14 个真实仓样本、6 个验证脚本、4 份报告
```

## 下一步方向

按价值排序，都还没做：

1. **更多语言的导入器**：现在只有 Python AST。这是最大缺口——设计期编译器的价值不该
   绑定一种语言。
2. **增量扫描**：`import-repo` 是全量重扫。2.78 量出写入约 5k 节点/秒，大仓上增量会明显。
3. **`coverage` 的可用性**：千节点仓上默认约束不可行。要么按阶段估算成本并提示，要么给
   "小作用域"模式。
4. **真实重构**：`httpie` 只诊断到设计图，没做重构。那是检验"设计期编译器能否指导真实
   重构"的唯一办法。
