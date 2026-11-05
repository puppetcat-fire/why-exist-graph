# Why-Exist 产品方案：设计期编译器

> 状态：草案 v1（2026-11-01）
> 本文件是产品方向与验收标准的唯一真源；命令形状、契约字段最终以 `scripts/wxg_contract.py` 为准。

## 1. 一句话定位

Why-Exist 不是交付门，是**设计期编译器**：把"一个任务该怎么切成互不冲突的并行单元"从架构师的直觉，变成可计算、可验证、可传递的结构。

现有版本（1.3.0）已经能回答"这块代码该不该存在、交付有没有证据"。它缺的是**事前**那一半：切分之前算出可并行度，切分之后验证切分能不能被独立执行者正确执行。

## 2. 核心命题

从与维护者的讨论中固化为四条命题，后续所有功能都必须服务其中之一：

1. **切分质量可度量。** 依赖图的最大反链大小就是理论并行上限；强连通分量就是必须先拆的循环依赖；拓扑分层就是调度波次。这三个量可以机械计算，不需要拍脑袋。
2. **好切分的标志是可局部化执行。** 每个子任务不需要全局视野就能做对。如果某一路必须理解整体设计才知道怎么动手，说明切分没完成，只是转移了难度。这条能用"盲执行测试"检验。
3. **影响范围必须闭环到需求。** 改动的下游可达集若落不到任何 requirement 上，就是我意料之外的影响面，必须报告或拦截。
4. **并行冲突要从运行时挪到声明时。** 现在 `target_ids` 互斥 = 必须串行。正确的做法是子任务只产出补丁，由单一 reducer 合并，冲突在合并时显式暴露，而不是靠锁。

## 3. 现状评估

### 已有资产（不该重写）

| 资产 | 事实 | 价值 |
|---|---|---|
| 单一契约 | `wxg_contract.py` 803 行，命令/角色/条件/导出形状的唯一真源 | 新增能力必须先改契约，自动获得文档与校验 |
| 状态机 | 8 条件、generation、supersede、审计独立、同代证据 | 并行执行的骨架已经存在 |
| 咬合 | `bites` 表 + 覆盖公式 + 抽样 | "必要性"已经是可判定状态 |
| 一致性自检 | `verify`（文档/样例字节一致）、`doctor`（状态库） | 扩展时不会静默漂移 |
| 测试 | 381 个回归用例 + 后端集成用例（默认跳过） | 重构的安全网 |
| 发布 | `build_release.py` 确定性 zip + GitHub Actions | 产品分发路径已通 |

### 缺口（当时的判断，现已全部解决）

| 当时的缺口 | 当时现状 | 现在的状态 |
|---|---|---|
| 没有并行规划 | 只有 `coverage` 的阶段建议 | `plan` 给出 SCC / 层 / 反链 / 并行度 / 瓶颈说明 |
| 没有盲执行验证 | `role-prompt` 给了角色边界 | `brief`（盲化任务书）+ `blind-check`（越界/依赖/局部化评分） |
| 影响域只是节点集合差 | `change-diff` 对比工单写过的节点 | `impact` 闭包 + 需求覆盖 + `direct`/`indirect` 深浅拆分 |
| 共享可变状态 | 子任务直写图库，靠 token 上锁 | `patch` / `apply` + reducer 冲突检测（`apply` 有意绕过写边界） |
| 单文件 3.8k 行 | `wxg.py` 一个文件承载全部命令 | 拆进 `whyexist` 包，`wxg.py` 只剩 181 行薄入口 |
| 无库 API | 只有 CLI 子进程 | `from whyexist import Engine` |
| 上手成本高 | 快速开始 15+ 命令 | `up --template minimal\|standard` + 最短路径文档 + `tools/doc_flow.py` |

## 4. 产品模型：三层

```
Design IR        设计中间表示：图库（节点/边/契约字段）
   │
Compiler passes  规划与验证：plan / impact / brief / blind-check
   │
Runtime          执行：工单状态机 → 操作日志 → reducer
```

现有实现三层都已落地：图库是 Design IR；`whyexist` 包的纯函数模块（`graph_algo` /
`planner` / `briefing` / `blind` / `impact` / `cycles` / `gates` / `derive`）是 pass 层；
工单状态机 + `reducer` 是 Runtime。剩下的增量是三层之间的产品化——工具链、验证脚本、
文档对齐。

## 5. 能力设计

### 5.1 `wxg plan`：并行规划

输入 feature 作用域内的依赖图（设计层 `depends`，或退到代码层 `calls`/`reads`/`writes`），输出：

- `acyclic` / `cyclic_components`：是否有环、环的成员（SCC）；非平凡环必须拆，否则无法给出波次
- `layers`：拓扑分层（Kahn），第 i 层内任务互不依赖；有环时为 `null`
- `max_antichain`：最大反链大小（Dilworth），即**理论并行上限**
- `parallelism`：无环时等于最大反链；有环时等于最大环的大小（环内节点必须串行）
- `bottleneck`：一句话说明这个数字受限于什么——"最大反链 N 个节点可同时做（M 层，最宽 K 个）"
  或"受限于最大环：N 个节点必须串行（成员）"
- `level`：实际用了哪一层（`design` / `code`）；`--level code` 且作用域无代码节点时结果带 `hint`

验收：对构造的 DAG（已知答案）能算出正确的 SCC、层数、反链；有环时 `layers=null` 并给出环成员。

### 5.2 `wxg brief`：盲化任务书

对一张工单生成自包含任务书，**剥掉全局设计意图**。实际返回：

- `feature`：id / statement / acceptance / constraints——只含本 feature 的声明
- `work_item`：id / role / kind / target_ids——写入边界
- `slice`：target_ids 命中的节点与边（深度 1，取决于图里已有什么）

它不含其他在途工单的 id、名称或产出，这是"盲"的含义。输出契约里的 kind 形状由角色决定
（盲执行者从 `blind-check` 的反馈里学），brief 本身不写死。

验收：同一张工单生成的 brief 不含任何其他在途工单的 id 或名称；连续生成两次字节一致（确定性）。

### 5.3 `wxg blind-check`：盲执行验证

输入一张工单的 brief 和执行者产出（节点/补丁 + 说明），输出：

- `boundary`：产出是否全部落在 target_ids 内
- `contract`：是否满足输出契约（kind、必填属性、接口形状）
- `dependencies`：是否引入了未声明的依赖
- `locality`：局部化程度评分（0–1），由"越界写 / 未声明依赖 / 需要补充全局信息"三项扣分
- `verdict`：PASS / FAIL

这是产品的核心差异化：它把"这个切分能不能交给一个不知全局的执行者"从口头保证变成一条可重复运行的测试。

验收：用历史上已交付的 feature 做回归，brief 交给干净 agent 后的产出应 PASS；人为制造越界写与未声明依赖时必 FAIL。

### 5.4 `wxg impact`：影响域闭包

输入 feature 与一组被改动节点，输出：

- `affected`：受影响节点全集（谁依赖被改节点的传递闭包，含被改节点自身）
- `direct` / `indirect`：按反向 BFS 最短跳数拆——一跳内直接依赖 vs 隔两跳及以上
- `depends_on`：被改节点自己依赖谁（上游）
- `requirements` / `uncovered`：受影响节点命中的 requirement，以及没有任何 requirement 覆盖的
- `cross_feature`：影响到了其他 feature 作用域的节点
- `closed`：`uncovered` 为空时为真

`--remove-edges src->dst,...` 是另一种模式：算断掉某条依赖后源点失去哪些可达节点。

`--require-impact-closure` 这类开关没有实现——uncovered 目前只报告，不影响 gate。

验收：构造"改动落到无 requirement 归属节点"的用例，必须被 `uncovered` 捕获。

### 5.5 `wxg patch` / `wxg apply`：操作日志 + reducer

- `patch`：从工单领取后的一次执行产出结构化补丁（节点/边/状态变更的 JSONL），不直接写图库
- `apply`：单一 reducer 顺序应用补丁，冲突（同一节点被两条补丁以不同内容修改、边端点缺失、条件竞争）显式报告，失败不写半截

这一层替换 `claim_token` + `target_ids` 的锁模型：`apply` 有意绕过 `target_ids` 写边界，
并发安全由 reducer 的冲突检测保证，而不是靠互斥区间。

验收：两条并行补丁改同一节点时，`apply` 必须报冲突且不落盘；改不同节点时全部落盘；应用顺序不影响最终状态（交换律测试）。

### 5.6 产品可用性

- `wxg up`：一条命令完成 init + demo feature + 首个工单 + 首个 gate；`tools/doc_flow.py` 把
  最短路径全跑完实测 **5.6 秒**，人工跟着敲加阅读约两分钟
- 库 API：`from whyexist import Engine`，暴露 plan/impact/brief/blind-check/gate 的函数式接口
- 模板：`wxg up --template minimal|standard`（minimal 只建 feature，standard 另建 demo 仓与
  样例文件；`init` 只负责建库与迁移，不带模板）
- 拆分：`scripts/wxg.py` 已拆成 `scripts/whyexist/` 包（db / graph / work / workflow / gates /
  importer / 各 `commands_*` / cli），`wxg.py` 只剩 181 行的薄入口（见 2.24.0）

## 6. 路线图

| 里程碑 | 内容 | 可验证产出 | 预估 |
|---|---|---|---|
| P0 骨架 | `plan` + `brief` + `blind-check` + 一个 demo 仓库 | `python scripts/wxg.py plan --feature demo --json` 给出反链与波次；demo 端到端脚本一键跑通 | 主力 |
| P1 可用性 | `up` 单命令、库 API、拆包、模板 | 最短路径自动化 5.6 秒 PASS；`from whyexist import Engine` 可用；381 测试全绿 | 主力 |
| P2 闭环 | `impact` + 需求覆盖 + 声明期冲突检测 | uncovered 用例被捕获；两个 feature target_ids 重叠时 plan 报冲突 | 主力 |
| P3 并行架构 | `patch` + `apply` + 交换律测试 | 冲突显式报告，无半截写入 | 主力 |
| P4 发布 | 文档、示例、2.x 版本 | `verify` 通过，release zip 可复现（已到 `2.70.0`） | 收尾 |

**执行顺序：P0 → P1 → P2 → P3。** P0 优先，因为它验证"盲执行"这个核心假设；假设不成立，后面全是装饰。

## 7. 质量门（每个里程碑都必须满足）

1. 回归用例全绿（当前 381 个），`wxg verify` 通过（契约块与导出样例不漂移）。
2. 新能力必须有独立用例，且包含一个"故意破坏"的反例（否则不算验收）。
3. 新命令一律先进 `wxg_contract.py` 的 `COMMANDS`，再实现，再 `contract --write` 刷新文档。
4. 任何"只报告不拦截"的检查必须写明为什么不拦（沿用现有边界文档的纪律）。
5. CLI 输出保证确定性：同样输入两次运行字节一致（便于 diff 与回归）。

## 8. 明确不做

- 不做图形界面。
- 不做 UML 图作为输入或中间表示（`why-exist-uml` 保持投影层，不反过来约束内核）。
- 不做非 Python 的自动导入器（仍走 `upsert-node` 手工建模）。
- 不把 coverage/blind-check 包装成"正确性证明"，它们是概率性或局部性证据。
- 不在 P0/P1 阶段碰数据库后端（SQLite/MySQL/PG 保持现状）。

## 9. 进度

| 里程碑 | 状态 | 证据 |
|---|---|---|
| P0 骨架（`plan` / `brief` / `blind-check`） | 已完成（2026-11-01） | `whyexist` 包 + 3 条只读命令 |
| P1 可用性（`up` / 库 API） | 已完成（2026-11-02） | `up` 幂等、`Engine` 只读方法 |
| P1 拆包（主实现迁进包） | 已完成（2026-11-02） | `wxg.py` 4500 → 181 行；`whyexist` 二十多个模块 |
| P2 闭环（影响域 / 需求覆盖 / 冲突检测） | 已完成（2026-11-01） | `impact` / `conflicts` / `Engine.impact` |
| P3 并行架构（operation log + reducer） | 已完成（2026-11-01） | `patch` / `apply` / `whyexist/reducer.py` |
| P4 发布（文档 / 示例 / 2.x） | 进行中（2026-11-02） | 契约 `2.67.0` / schema 9 / 381 用例 / `dist/v2.67.0` |
| P5 分析深化（环形态 / 瓶颈 / 深浅影响 / 孤立拆分） | 已完成（2026-11-02） | `cycles --break-set/--advise`、`plan.bottleneck`、`impact.direct`、`conformance` 孤立拆分 |
| P6 工具链 | 已完成（2026-11-02） | `tools/` 五个脚本 + `refactor-lab/` 三个验证脚本 |

**核心流程全部有端到端验证**：

| 流程 | 脚本 |
|---|---|
| 声明 → 交付 → gate PASS | `tools/doc_flow.py`（照 `SKILL.md` 执行） |
| 已交付后改设计（`change-open`） | `refactor-lab/verify_change.py` |
| 控制器安全迁移（`reconcile --apply` / `serve`） | `refactor-lab/verify_controller.py` |
| 报告自洽（plan/cycles/conformance/impact/status 互相吻合） | `tools/verify_reports.py` |
| 重构前后 `sync` 报告真实性 | `refactor-lab/verify_sync.py` |
| 发布前五项检查 | `tools/preflight.py` |

P0 的实际边界：`plan` 只分析图里已有的依赖边；`brief` 的盲化是信息裁剪；`blind-check`
只做结构校验。三者拼起来能回答"这次切分有没有让执行者越界"，还不能回答"切分本身是否
最优"——后者要靠多个盲执行结果的分布，是 P2 影响域与调度要处理的事。
