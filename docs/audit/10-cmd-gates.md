# 10-cmd-gates：gate 域与门本体

审计对象：`scripts/whyexist/commands_gates.py`、`scripts/whyexist/gates.py`、`scripts/whyexist/evidence.py`，以及它们在 `cli.py` / `wxg_contract.py` / `wxg.py` / `engine.py` 里的对外出口。只读审计，未改任何源码；行为验证用 `docs/audit/_probe_10*.py` 四个探针脚本，跑在临时状态库里。

**结论先行**：gate 的契约总体清楚、有真实测试，但有四处「文档/契约说的 ≠ 代码做的」：覆盖公式分母差 1、悬空 bite 仍能通过 drift 拦门、跨 feature 咬合污染、gate 级覆盖检查要求全部六个阶段。evidence 是整套门禁里唯一无法自证的外部信任点。serve 有四个未文档化的退出/异常行为。分区建议：`gates.py` 与 `commands_gates.py` 原地重构，`evidence.py` 保留，`cmd_serve` 单独重写。

---

## 1. 切片范围

| 文件 | 实际总行 | 纯代码行 | 职责 |
|---|---:|---:|---|
| `scripts/whyexist/gates.py` | 417 | 365 | 咬合选择、覆盖公式与报告、漂移、一致性、调谐动作 |
| `scripts/whyexist/commands_gates.py` | 322 | 287 | 5 个命令处理器 + gate 九项判定级联 + 废弃 re-export |
| `scripts/whyexist/evidence.py` | 35 | 28 | 证据采信与 sha256 |

任务说明里的 293 / 375 / 28 接近纯代码口径（实测去掉空行与注释是 287 / 365 / 28）；总行数之所以是 322 / 417 / 35，差额主要来自空行、注释与两段 dead re-export（`commands_gates.py:33-44`、`gates.py:402-413`）。仓库 HEAD 停在 v0.4.1，`scripts/whyexist/` 整个目录在 git 里是未跟踪状态；本审计以工作区当前内容为准。

切片外的直接消费者：

- `scripts/whyexist/cli.py:97-108`：gate / reconcile / serve 的退出码与打印格式在这里决定，不在命令处理器里。
- `scripts/whyexist/commands_repo.py:109`：`up` 命令内部调用 `cmd_gate`，把 gate 结果当首屏输出。
- `scripts/whyexist/engine.py:129-131`：`Engine.gate()` 直接包 `cmd_gate`，是 Python API 的唯一门禁入口。
- `scripts/whyexist/commands_feature.py:636-649`：work-judge 用同一个 `evidence_qualifies`，evidence 门槛与 gate 一致；coverage 用的是同一函数但检查范围只有当前阶段（见 5.4）。

---

## 2. 公开面

| 入口 | 输入 | 输出 | 退出码 | 副作用 |
|---|---|---|---|---|
| `wxg coverage --feature F [--epsilon E] [--prior-p P] [--json]` | F 必填；E/P 覆盖策略与默认值 | 缩进 JSON：scope_size / epsilon / prior_p / enforced / phases[6] / unmet / next | 0 正常；2 feature 不存在、库未初始化 | 只读，不建文件 |
| `wxg conformance --feature F [--limit N]` | N 默认 50，负数拒绝 | 缩进 JSON：anchors / structural / tests / violations / truncated / enforced（+hint） | 0；2 F 不存在、N<0 | 只读；坏 conditions 的 feature 也能出报告 |
| `wxg reconcile --feature F [--claim-ttl S] [--apply]` | S 默认 3600，负数拒绝 | 缩进 JSON：actions / applied / pending / gate{result,reason} / converged | 0 converged；1 未收敛；2 参数/feature/条件行错误 | 默认只读；`--apply` 写 work_items，命令末尾 commit |
| `wxg serve [--interval N] [--feature F] [--claim-ttl S] [--once] [--apply]` | N 默认 5，<=0 拒绝 | 每趟一行紧凑 JSON：pass / at / features[] / converged | **恒 0**；2 interval 非法或任一 feature 抛错 | 默认只读；`--apply` 每趟 commit；未知 F 静默跳过 |
| `wxg gate --feature F [--json]` | F 必填；`--json` 无效 | 缩进 JSON：result + 9 项 checks + 明细；FAIL 时带 reason 与对应键 | 0 PASS；1 FAIL；2 错误 | 只读（db hash 有测试） |
| `gates.coverage_report(conn, feature, epsilon=None, prior_p=None)` | 连接 + feature | 覆盖报告 dict | — | 只读 |
| `gates._required_coverage(S, a, b0, covered, ε)` | 标量 | 最小 m | — | 无 |
| `gates.drift_report(conn, feature)` | 连接 + feature | {count, limit, enforced, nodes} | — | 只读 |
| `gates.conformance_report(conn, feature, limit=50)` | 连接 + feature | 四类差异报告 | — | 只读 |
| `gates.reconcile_actions(conn, feature, claim_ttl)` | 连接 + feature + TTL | 8 类动作列表 | — | 只读 |
| `commands_gates.reconcile_feature(conn, feature, ttl, do_apply)` | 同上 | reconcile 结果 dict | — | do_apply 时写库 |
| `commands_gates.apply_safe_actions(conn, feature, actions)` | 动作列表 | 执行过的类别名 | — | 写 work_items |
| `evidence.evidence_qualifies(conn, feature_id, generation)` | 连接 + feature + 代 | bool | — | 读 evidence 表与产物文件 |
| `evidence.sha256_file(path)` | Path | hex | — | 读文件 |
| `Engine.gate(feature)` | feature id | 与 CLI 同源 dict | — | 只读 |
| 表 `bites` | node_id/feature_id/generation/phase/verdict/... | 门禁判决输入 | — | 本切片只读 |
| 表 `work_items` | status/depends_on/claim_token/claimed_at/fail_reason | 调谐动作、pending | — | `--apply` 写 |
| 表 `evidence` | feature_id/generation/exit_code/artifact_path/artifact_sha256 | BehaviorPassed 采信 | — | 只读 |
| 表 `features` / `conditions` | coverage_epsilon/drift_limit/conformance、8 条件状态 | 策略与条件判定 | — | 只读 |

文件产物：无。gate/coverage/conformance/reconcile 都只写 stdout/stderr；serve 写 stdout。唯一被读取的外部文件是 `evidence.artifact_path` 指向的产物。

---

## 3. 契约表

状态口径：covered = 有测试直接断言；partial = 测试覆盖部分分支；gap = 行为存在但无测试/文档断言。证据以「文件:行号」给出，探针文件在 `docs/audit/`。

### 3.1 gate 的判定承诺

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C1 | gate 只读，重复执行结果相同 | `tests/test_wxg.py:299-306`（db hash）、`tests/test_engine.py:109-115` | covered | 只验证了 sqlite 主文件 hash |
| C2 | PASS=0 / FAIL=1 / 错误=2 | `cli.py:97-99`、`tests/test_wxg.py:255-256,314-316` | covered | 错误走 stderr，stdout 为空 |
| C3 | 每节点最新判决：UNNECESSARY/HOLLOW → FAIL；KEEP 只反证同节点 | `commands_gates.py:166-187`、`wxg_contract.py:121-124`、`tests/test_wxg.py:308-320,1055-1077` | covered | 跨节点抵消被显式测过 |
| C4 | 悬空 bite 不计入门禁，输出 `ignored_dangling_bites` | `commands_gates.py:174-178,248-249`、`tests/test_wxg.py:391-429` | **partial** | drift 路径仍计入（P3） |
| C6 | pattern 必须有 applicability/not_applicable 且被 applies 挂载 | `commands_gates.py:189-203,259-265`、`tests/test_wxg.py:1168-1215` | covered | — |
| C7 | drift_limit N：UNMAPPED/DOC-ONLY 节点数 > N → FAIL | `commands_gates.py:266-272`、`tests/test_wxg.py:1220-1236` | partial | 含悬空、跨 feature、全 phase |
| C8 | construction=true → FAIL | `commands_gates.py:205-209,273-279`、`tests/test_wxg.py:1404-1428` | covered | — |
| C9 | stale=1 → FAIL | `commands_gates.py:211-215,280-286`、`tests/test_wxg.py:1559-1583` | covered | — |
| C10 | conformance 开启时 violations>0 → FAIL | `commands_gates.py:217,287-298`、`tests/test_wxg.py:1758-1793` | covered | 内嵌报告缺 enforced（C22） |
| C11 | 8 个条件全为 1，否则 FAIL 并列出缺项 | `commands_gates.py:235,299-305`、`tests/test_plan_cli.py:746-767` | covered | 条件是第 7 道 |
| C14 | 覆盖策略关闭时 gate 不拦 | `commands_gates.py:313-319`、`tests/test_wxg.py:189-260` | covered | full-flow 间接覆盖 |
| C15 | 覆盖策略开启时六个阶段必须全 met | `commands_gates.py:220,313-319`、P2 | **gap** | 条件全真也可能 FAIL |
| C34 | `checks` 固定 9 项，顺序固定，第一项 false 即原因 | `commands_gates.py:237-247,252-320`、`tests/test_plan_cli.py:746-767` | covered | 名单/顺序有断言 |
| C35 | 咬合/pattern/drift/施工/stale/conformance 的失败优先于「条件未齐」 | `commands_gates.py:252-320`、六条测试 | covered | 与 GATE_RULES 第一条的叙述顺序不一致 |
| C5 | gate 会把其它 feature 在共享节点上的咬合计入 | `commands_gates.py:169-172`、P4 | **gap** | coverage 不这么算 |
| C37 | `Engine.gate` 与 CLI 同源同形状 | `engine.py:129-131`、`tests/test_engine.py:109-115` | partial | 未比对字段 |

### 3.2 证据

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C12 | 同 generation + exit_code=0 +（有产物时存在且 hash 一致）才采信 | `evidence.py:19-35`、`commands_gates.py:306-312`、`tests/test_wxg.py:589-604,792-820,861-871` | covered | gate 与 judge 共用 |
| C13 | 无产物/无 hash 也算有效；任意一条合格即通过 | `evidence.py:26-34`、`tests/test_wxg.py:249-257`、P10 | partial | 无产物分支被 full-flow 覆盖；hash 为空/失败不撤销未测 |

### 3.3 覆盖

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C16 | phases 固定 6 个；next = 第一个 unmet | `gates.py:99-121`、`tests/test_wxg.py:1299-1308` | covered | — |
| C17 | p=(1+d)/(10+n)；n_required 由 p_m·(S-m)≤ε 求最小 m | `gates.py:36-55,95-97`、`wxg_contract.py:168-170`、`tests/test_package_units.py:442-459` | partial | 实现 residual 分母 9+m（P1） |
| C18 | hits = 该阶段任一非 KEEP/UNKNOWN 判决的去重节点，历史不回落 | `gates.py:92-95`、Q5 | partial | 文档明确；但现有 coverage 测试全用 KEEP，hits>0 路径无断言 |
| C19 | `--epsilon/--prior-p` 可覆盖，但不校验取值 | `commands_gates.py:28-30`、`gates.py:83-87`、Q3 | **gap** | ε=-1 时全阶段 trivially met |

### 3.4 一致性

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C20 | 四类差异 + violations 求和 + limit 只截列表 | `gates.py:150-313`、`tests/test_package_units.py:515-687`、`tests/test_wxg.py:1704-1756` | covered | code_orphans 不计 violation |
| C21 | unmapped 唯一名做一次启发式，不写回图 | `gates.py:218-235,301`、`tests/test_wxg.py:1814-1845` | covered | — |
| C22 | conformance 只读；命令与 gate 内嵌报告字段一致 | `commands_gates.py:53-56,250-251`、P5 | **gap** | gate 内嵌缺 enforced；只读无 hash 断言 |
| C23 | 测试覆盖来自 testcase 的 verifies | `gates.py:265-271`、`wxg_contract.py:239`、P9 | **gap** | 任意节点 src 都算 |

### 3.5 调谐

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C24 | converged = 无动作且 gate PASS，决定退出码 0/1 | `commands_gates.py:90-107`、`cli.py:103-105`、`tests/test_wxg.py:258-260,1326-1337` | covered | gate 明细被压成 result/reason |
| C25 | 默认只读、幂等 | `commands_gates.py:91-96`、`tests/test_wxg.py:1326-1337` | covered | dict + db hash 双重断言 |
| C26 | `--apply` 只做补单/解阻塞/回收 claim | `commands_gates.py:59-77`、`gates.py:329-367`、`tests/test_wxg.py:1339-1389` | covered | applied 可能含 0 行更新 |
| C27 | TTL 过期回收；缺 claimed_at/解析失败也算过期；ttl=0 立即回收 | `gates.py:349-367`、Q1 | partial | 默认 3600 与边界无测试 |
| C28 | retry/coverage-gap/drift-over-limit/construction-open/stale-node 五类待办 | `gates.py:369-398`、D1/R2/R6 | **gap** | 无文档、无测试、阻止 converged |

### 3.6 常驻控制器

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C29 | `--once` 单趟、默认只读、输出 pass/at/features/converged | `commands_gates.py:118-156`、`tests/test_wxg.py:1659-1676` | covered | db hash 断言 |
| C30 | `--apply` 每趟迁移并 commit | `commands_gates.py:141-142`、`tests/test_wxg.py:1678-1693` | covered | 多 feature 部分提交未测 |
| C31 | serve 退出码恒 0（未收敛也 0） | `cli.py:106-108`、Q2 | covered | 测试默认 expect=0 隐含 |
| C32 | `--feature` 指向未知 id 时静默成功 | `commands_gates.py:130-140`、P6 | **gap** | features=[]，converged=true |
| C33 | 任一 feature 抛 Reject → 整轮中止、退出 2、无摘要 | `commands_gates.py:127-156`、R1 | **gap** | 长驻进程的可用性问题 |

### 3.7 CLI 边界

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C36 | `--json` 不改变输出 | `wxg_contract.py:501,622`、P7 | **gap** | 有/无逐字节相同 |
| C38 | coverage/conformance 不要求条件行完整；gate/reconcile/serve 要求 | `commands_gates.py:47-56,160-161`、R1/R4 | **gap** | 同一坏 feature 上 2/0/0 |

合计 38 条：covered 21、partial 7、gap 10。

---

## 4. gate 的 PASS/FAIL 全流程

### 4.1 入口与前置

`wxg gate --feature F` → `cli.py:81-84` 取 `cmd_gate` → `cmd_gate(conn, args)`（`commands_gates.py:159`）。

前置失败（都不是 PASS/FAIL，而是退出 2）：

1. 状态库文件不存在：`cli.py:66-69`。
2. feature 不存在：`ensure_feature`（`workflow.py:30-34`）。
3. 当前代 conditions 行数 ≠ 8：`condition_flags`（`workflow.py:45-49`）。

### 4.2 九道闸门（按实现顺序）

| 序 | checks.name | 判据 | 实现 | FAIL 时的 reason 键 | gate 级测试 |
|---|---|---|---|---|---|
| 1 | `bites` | 作用域内每节点**最新**判决 ∈ {UNNECESSARY, HOLLOW} | `commands_gates.py:166-187,252-258` | `hollow` | `tests/test_wxg.py:308-320,1055-1077` |
| 2 | `pattern` | scope 内 pattern 缺 applicability/not_applicable，或无 applies 入边 | `commands_gates.py:189-203,259-265` | `patterns` | `tests/test_wxg.py:1168-1215` |
| 3 | `drift` | `drift_limit` 非空且 UNMAPPED/DOC-ONLY 节点数 > limit | `commands_gates.py:266-272` | `drifted` | `tests/test_wxg.py:1220-1236` |
| 4 | `construction` | scope 内 `attrs.construction is True` | `commands_gates.py:205-209,273-279` | `constructions` | `tests/test_wxg.py:1404-1428` |
| 5 | `stale` | scope 内 `stale=1` | `commands_gates.py:211-215,280-286` | `stale_nodes` | `tests/test_wxg.py:1559-1583` |
| 6 | `conformance` | feature.conformance=1 且 violations>0 | `commands_gates.py:217,287-298` | 无独立键，用 `conformance` | `tests/test_wxg.py:1758-1793` |
| 7 | `conditions` | 8 条件任一 ≠1 | `commands_gates.py:235,299-305` | `missing` | `tests/test_plan_cli.py:746-767` |
| 8 | `evidence` | BehaviorPassed=1 且 `evidence_qualifies` 为假 | `commands_gates.py:219,306-312` | `missing_evidence_for` | `tests/test_wxg.py:861-871` |
| 9 | `coverage` | enforced 且 `unmet` 非空 | `commands_gates.py:220,313-319` | `missing_coverage` | **无** |

`checks` 数组在 `commands_gates.py:237-247` 一次性生成，顺序与上表一致；`tests/test_plan_cli.py:746-767` 断言了 9 个名字与顺序。

### 4.3 失败优先级

实际优先级就是上表顺序。条件未齐是第 7 位，所以：

- 一个有 UNNECESSARY 咬合、同时条件未齐的 feature，reason 是咬合（`tests/test_wxg.py:308-320`）。
- 有 pattern 问题、条件未齐 → `模式有限应用`（`tests/test_wxg.py:1195-1197`）。
- 漂移超限、条件未齐 → `结构性漂移超标`（`tests/test_wxg.py:1234-1236`）。
- 施工中、条件未齐 → `施工中节点`（`tests/test_wxg.py:1416-1418`）。
- stale、条件未齐 → `stale`（`tests/test_wxg.py:1576-1578`）。
- conformance 违规、条件未齐 → `一致性`（`tests/test_wxg.py:1791-1793`）。

但 `GATE_RULES`（`wxg_contract.py:129-142`）把「条件未齐」列在第一条，`design.md:1089-1106` 的 61 节才按实现顺序写。规则表是 `verify` 逐字节校验的文档真源，不是行为真源。

### 4.4 输出形状

PASS：`{result: "PASS", conditions, bites, latest_verdicts, evidence_ok, coverage, drift, constructions, stale, checks, [conformance], [ignored_dangling_bites]}`。

FAIL：在 PASS 字段基础上加 `reason`，再加一类明细键（`hollow` / `patterns` / `drifted` / `missing` / `missing_evidence_for` / `missing_coverage`）。注意：

- 键名 `hollow` 同时装 UNNECESSARY 与 HOLLOW 两种判决，名字比内容窄。
- `latest_verdicts` 只包含未悬空、当前代/全局的咬合；悬空项只出现在 `ignored_dangling_bites`。
- `conformance` 子对象缺 `enforced`（P5）。
- `checks` 与 `reason` 可能局部不一致：`checks` 是九项全量，`reason` 只取第一个 false。

### 4.5 判定链的边界行为

- **作用域来源**：`feature_nodes` ∪ `requirement:F:` 前缀节点 ∪ 当前代工单 `target_ids`（支持 `*` 通配），且只收仍存在的节点（`workflow.py:94-124`）。`bite --feature F` 会顺手把节点加进 feature_nodes（`commands_graph.py:120-122`），所以「咬一口」会扩作用域。
- **跨 feature 污染**：`in_feature = node_id in scope or bite.feature_id == F`（`commands_gates.py:169-172`）。其它 feature 对共享节点的判决会拦本 feature，probe P4 复现。
- **全局咬合**：`bite.feature_id IS NULL` 的旧记录会被每个作用域包含该节点的 feature 计入（`gates.py:28-31` 的注释承认这点）。
- **悬空漂移**：`drift_report` 不做 `get_node` 校验，P3 复现同一条记录既被忽略又导致 FAIL。
- **不看的**：`attrs.bite` 完全不采信（只写展示；`commands_graph.py:128-133`）；咬合的 `phase` 不参与 gate，只用于 coverage；`actor`、`reason` 不参与判定。

---

## 5. 覆盖公式与报告

### 5.1 代码实际做的

`gates.py:81-121`：

```
a0 = max(prior*10, 1e-9)          # 默认 prior=0.1 → 1.0
b0 = max((1-prior)*10, 1e-9)      # 默认 → 9.0
phase 内 bites 去重 → n = covered，hits = d
p        = (a0 + d) / (a0 + b0 + n)          # 默认 (1+d)/(10+n)
required = _required_coverage(S, a0+d, b0, n, eps)
         residual(m) = (a0+d)/(b0+m) * max(S-m, 0)   # 默认 (1+d)/(9+m)*(S-m)
met      = n >= required
index    = alpha**i * p                      # alpha=2
```

`_required_coverage` 二分求最小 m，m 上限 S；S<=0 或 ε<=0 直接返回 covered。

### 5.2 与 COVERAGE_RULES 的差异

`wxg_contract.py:168-170`、`SKILL.md:388`、`contract.md:117` 写的是：

```
p = (1+d)/(10+n)
p_m = (1+d)/(10+m)
要求存在 m 使 p_m·(S-m) ≤ ε 且 n ≥ m
```

代码的 `p` 对，`n_required` 的 `p_m` 分母是 `9+m` 而不是 `10+m`。默认参数下这是差 1 的分母，不是理论差异；它会让报告自相矛盾：

> probe P1：S=1、ε=0.1、d=0、n=0 → 输出 `p=0.1`、`n_required=1`、`met=false`。按文档公式，m=0 时 p_0·(S-0)=0.1×1=0.1 ≤ ε=0.1，`n=0 ≥ 0`，应判 met。

单测为什么没抓到：`tests/test_package_units.py:442-459` 直接给 `_required_coverage` 传 `b0=1.0`（人工参数），生产路径固定传 `b0=9.0`；`coverage_report` 的测试用 ε=0.001，两种公式同判 required=1，区分不出来。

### 5.3 命中与阶段

- `hits` 取该 phase 所有 `bites` 行里「任一判决非 KEEP/UNKNOWN」的去重节点（`gates.py:93-95`）。同一节点先 UNNECESSARY 后 KEEP，命中仍为 1，p 不回落（Q5：p=0.1818）。文档确实写「任一判决」，所以这是语义选择，不是 bug；但它与 gate 的「最新判决」是两套口径。
- phases 固定为 `CONDITION_TO_KIND` 的 6 个键（`gates.py:91`），Accepted/Ready 不参与覆盖。
- `unmet` 是全部未达标阶段，`next` 是第一个（`gates.py:109-120`）。

### 5.4 强制点

| 调用方 | 检查范围 | 位置 |
|---|---|---|
| `work-judge(passed)` | 只检查该工单对应条件的 phase | `commands_feature.py:642-649` |
| `gate` | 六个 phase 全部 | `commands_gates.py:313-319` |
| `reconcile` | 不拦截，只产出 `coverage-gap` 动作 | `gates.py:378-380` |

所以「judge 过了」不等于「gate 覆盖过了」：判完第一个阶段后，gate 仍会因后五个阶段没咬合而 FAIL（P2）。

---

## 6. evidence 的采信与信任边界

`evidence_qualifies`（`evidence.py:19-35`）对每个候选行：

1. 必须 `feature_id = F` 且 `generation = 当前代` 且 `exit_code = 0`。
2. `artifact_path` 为空 → 直接算合格。
3. 有路径 → 文件必须存在；`artifact_sha256` 非空时必须匹配当前文件内容。
4. 任意一行合格即返回 true；所有行都不合格才 false。

probe P10 的矩阵：

| 场景 | 结果 |
|---|---|
| 只有 exit_code=1 | false |
| 无 artifact、exit 0 | **true** |
| artifact 路径不存在 | false |
| artifact 存在、hash 匹配 | true |
| artifact 存在、hash 不匹配 | false |
| 换一代（generation 不匹配） | false |

含义：gate 能证明「有人在状态库里登记过一条 0 退出码的证据」，不能证明测试真的跑过。这是文档承认的外部执行边界（`design.md:69`），但 EVIDENCE_RULES 的措辞（`wxg_contract.py:154-157`）比实现严格，评审时要按实现理解。

副作用：`sha256_file` 会整文件读取；`evidence_qualifies` 在文件存在性检查与 hash 之间存在竞态，文件消失会抛 OSError，被 `cli.py:88-90` 兜成退出码 2（fail-closed，但表现为错误而非 FAIL）。

---

## 7. conformance 的实现边界

四类差异（`gates.py:131-313`）：

1. **锚点**：scope 内 use_case/component/port 必须有一条 `maps_to` 指向同样在 scope 内、且带 repo+path 的节点（`gates.py:150-156`）。作用域外的代码节点不算锚点。
2. **结构支撑**：每条 `depends`（两端都在 scope）必须在两边锚定的代码节点之间找到 calls/reads/writes；带 `attrs.x_evidence` 的 depends 直接免检（`gates.py:237-248`）。
3. **未声明耦合**：代码边跨两个设计单元，而设计层没有 depends/associates（双向匹配）→ 报告（`gates.py:250-263`）。
4. **测试覆盖**：每个 use_case 必须有一条 `verifies` 入边；**不校验 src 是 testcase**（P9）。

附加输出：`code_orphans`（有 repo/path、未被任何 maps_to 指向的 operation/classifier；只报告不计 violation）、derived 组件 contains 内的 `unanchored_count` 与 `truly_orphan_count`、`hint`、`resolved_heuristically`。

只读性：代码确实不写库，但没有和 gate 一样的 hash 断言（C22）。`cmd_conformance` 还有一处重复赋值：`commands_gates.py:53-55` 先 `bool(...)`，再 `if 同一条件: True`。

---

## 8. reconcile 与 serve

### 8.1 动作清单（`gates.py:316-399`）

| 动作 | 触发 | auto | apply 是否执行 |
|---|---|---|---|
| `seed-ticket` | 条件未真且本代缺对应工单 | true | 是（work_seed 补全） |
| `unblock` | blocked 且 depends 全 passed | true | 是（refresh_blocked） |
| `release-stale-claim` | claimed 且 claimed_at 超过 TTL / 缺失 / 解析失败 | true | 是（清 token/assignee/claimed_by/claimed_at 回 ready） |
| `retry` | ready 且 fail_reason 非空 | false | 否 |
| `coverage-gap` | coverage enforced 且 unmet | false | 否 |
| `drift-over-limit` | drift enforced 且 count>limit | false | 否 |
| `construction-open` | scope 内有 construction=true | false | 否 |
| `stale-node` | scope 内有 stale=1 | false | 否 |

顺序即上表顺序（seed → unblock → release → retry → coverage → drift → construction → stale）。`converged = (actions 为空) and gate.result == PASS`。因此后五类只读动作会让 reconcile 永远返回 1，直到人处理。

`--apply` 的写库由 `cli.py:78-84` 统一 commit；serve 每趟自己 commit。`release-stale-claim` 的 UPDATE 带 `AND status='claimed'`，但 `apply_safe_actions` 不论 rowcount 都把类别加进 `applied`（`commands_gates.py:68-76`）。

### 8.2 serve 的四个未文档化行为

1. **退出码恒 0**（`cli.py:106-108`），即使 `summary.converged=false`（Q2）。reconcile 用 1 表达同一状态。
2. **未知 feature 静默成功**：`get_feature` 返回 None 就跳过，输出 `features: []`、`converged: true`、退出 0（P6）。
3. **单 feature 异常中止整轮**：循环里任一 `reconcile_feature` 抛 Reject（例如条件行缺失），异常冒到 `cli.py:85-87`，本趟已打印的内容之外没有摘要，退出 2（R1）。同趟 `--apply` 已执行但未 commit 的写入随连接关闭回滚。
4. **坏的 feature 不会拖垮 coverage/conformance**：同一状态库上 `coverage`/`conformance` 正常返回 0（R4/R5），说明「只读报告类命令」与「门禁/调谐类命令」的前置条件不同（C38）。

另外：`--once` 打印的那一行就是最终输出；Ctrl+C 时 `cmd_serve` 返回 `{passes, stopped}`，但 cli 对 serve 不再打印，所以用户只看到最后一趟的 JSON。

---

## 9. 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `features` | 读 | `workflow.py:25-34`、`gates.py:83` |
| `conditions` | 读 | `workflow.py:37-49`、`commands_gates.py:161,235` |
| `bites` | 读 | `commands_gates.py:166-168`、`gates.py:22-24,63-65` |
| `nodes` | 读 | `commands_gates.py:174,190-214`、`gates.py:135-156` |
| `edges` | 读 | `commands_gates.py:198-201`、`gates.py:139-270` |
| `feature_nodes` | 读 | `workflow.py:104-105` |
| `work_items` | 读 | `commands_gates.py:82-87`、`gates.py:320-325` |
| `work_items` | 写 | `commands_gates.py:62-74`（apply）、`workflow.py:91`（unblock）、`commands_feature.py:478-481`（seed） |
| `evidence` | 读 | `evidence.py:21-25` |
| evidence 产物文件 | 读 | `evidence.py:29-33` |
| stdout | 写 | `cli.py:97-113`、`commands_gates.py:149` |
| stderr | 写 | `cli.py:85-90` |
| 环境变量 `WXG_DB_URL` | 写（由 `--db-url`） | `cli.py:55-56` |
| 默认目录 `./.why-exist` | 读 | `cli.py:16,53,66-69` |
| 环境变量 `WXG_TEST_MYSQL_URL` / `WXG_TEST_PG_URL` | 读（仅测试） | `tests/test_mysql_backend.py:36`、`tests/test_pg_backend.py:36` |

跨命令共享状态：同一个 `graph.sqlite` 是唯一权威状态；本切片不写文件、不写 `.why-exist` 之外的目录，也不依赖进程内全局变量。实际共享路径是 `bite` 写 `bites` + `feature_nodes` → gate/coverage/drift 读；`work-claim` 写 `claimed_at` → reconcile 读；`evidence-record` 写 `evidence` → gate/judge 读。

---

## 10. 冗余信号

| 项 | 信号 | 置信度 |
|---|---|---|
| `commands_gates.py:33-44` re-export 8 个编译器命令 | 本模块不用；`commands_repo.py:709-719` 与 `wxg.py` 都直接从 `commands_compiler` 导入 | high |
| `commands_repo.py:696-705,724-725` 反向 re-export 门禁命令 | `wxg.py:137-146` 直接从 `commands_gates` 导入，形成无用依赖链 | high |
| `gates.py:402-413` re-export 9 个 work 函数 | 3 个 importer 都只取 report/私有函数 | high |
| 四套 bite 选择逻辑 | gate / `_feature_bites` / drift / 写侧 feature_nodes，语义各不相同 | high |
| construction 与 stale 扫描各写两遍 | `commands_gates.py:205-215` vs `gates.py:384-398` | high |
| `cmd_conformance` enforced 重复赋值 | `commands_gates.py:53-55` | high |
| `import time` 顶部与循环内各一次 | `commands_gates.py:5,152` | high |
| gate/coverage 的 `--json` 空旗标 | 从未读取，P7 输出逐字节相同 | high |
| conformance limit 默认值写两遍 | `wxg_contract.py:619` + `commands_gates.py:49` | high |
| `_required_coverage` 的 `return scope_size` 不可达 | residual(S)=0，合法 ε>0 必走二分 | medium |
| `CODE_EDGE_KINDS` 两处定义 | `gates.py:124` 与 `planner.py:35` | high |
| 证据产物校验两套 | `evidence.py:26-34` 与 `commands_misc.py:446-452` | high |
| `hollow` 键名装两类判决 | `commands_gates.py:252-258` | medium |
| `checks` 9 项与 `GATE_RULES` 12 条无映射 | `commands_gates.py:237-247` vs `wxg_contract.py:129-142` | high |
| `--apply` 时 actions 计算两遍 | `commands_gates.py:91,96`，每次都重跑 coverage/drift | medium |
| reconcile 丢弃 gate 明细 | `commands_gates.py:97,105` | medium |

---

## 11. 重写分区

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `scripts/whyexist/evidence.py` | **keep** | 35 行、契约清楚；sha256 有单测，采信逻辑由 gate/judge 三条测试间接覆盖；没有可回收的重复实现（doctor 那份应改成调用它） | 直接重写会丢两个隐式边界：无产物也算有效、hash 为空跳过校验。建议先把 P10 矩阵固化成单测 |
| `scripts/whyexist/gates.py` | **refactor_in_place** | 逻辑是门禁的算术与选择核心；四套 bite 选择、分母不一致、悬空漂移必须收敛；但每个字段都有测试或探针钉住（x_evidence 免检、derived orphan 拆分、唯一名启发式、phase 顺序），重写会静默丢边界 | 收敛选择逻辑会改变 gate/coverage/drift 三处结果，可能让原本 FAIL 的库变 PASS 或反之；改前给 C4/C5/C17 补反例测试 |
| `scripts/whyexist/commands_gates.py` | **refactor_in_place** | gate 的九级判定链是核心产品承诺，失败优先级与输出键已被 20+ 条断言固定；但文件混着 dead re-export、双重扫描、重复赋值、空旗标。应删兼容层，把判定链抽成有序检查表，保持输出逐字节兼容 | 抽表时「顺手修正」优先级或 reason 文案会破 `test_gate_checks_report_each_item` 与所有 reason 断言；删 re-export 前确认仓外无人 import（仓内已确认） |
| `scripts/whyexist/commands_gates.py:118-156`（`cmd_serve`） | **rewrite** | 行为边界小且独立：循环、间隔、feature 过滤、`--once/--apply`、每趟一行 JSON。现实现混了四个未文档化决定（恒 0、未知 feature 静默、单点异常中止、commit 时机），正好在重写时显式定义并补测 | 外部 CI 可能依赖「serve 恒 0」与紧凑单行 JSON；若重写时改成 reconcile 式退出码会破坏调用方。先按现契约重写，退出码另议 |

---

## 12. 可验证性评估

- **测试密度**：`python -m unittest tests.test_wxg -k gate -k coverage -k conformance -k reconcile -k serve -v` 命中 31 条用例，58s，全绿。另有 `tests/test_package_units.py:442-687`（覆盖数学 + conformance 内存库单测）和 `tests/test_plan_cli.py:746-767`（checks 名单/顺序）。MySQL/PG 后端各有一条 gate FAIL 与 serve --once，但默认 skip（需 `WXG_TEST_MYSQL_URL` / `WXG_TEST_PG_URL`）。
- **九项检查的 gate 级覆盖**：8/9 有「该检查单独失败」的测试；**coverage 没有**（只有 work-judge 级拦截测试）。也就是说，启用 `--coverage-epsilon` 后 gate 因覆盖 FAIL 的路径，只有探针 P2 验证过。
- **没有表驱动矩阵**：没有「八项全过、只让第 N 项失败」的测试，reason 优先级靠 6 条分散断言间接固定；相邻检查对（如 drift vs construction）的先后没有专门测试。
- **gate 的 fail-closed 部分**：DB 缺失、feature 缺失、条件行缺失、后端异常都退出 2，不会误判 PASS；`gate` 的只读性有 db hash 测试。这两点使它适合当 CI 门禁。
- **gate 的「可无声失败/误判」部分**：
  - 空作用域 + 条件全真 + 无覆盖策略 → 可 PASS；PASS 只证明流程完备，不证明设计正确（`design.md:74` 承认）。
  - 裸 evidence（无产物、exit 0）→ 可通过 BehaviorPassed。
  - 悬空 UNMAPPED + `--drift-limit` → 会 FAIL 一个已删除的节点（过度拦截）。
  - 其它 feature 的判决 → 会影响本 feature（过度拦截）。
  - 覆盖公式分母差 1 → `p` 与 `met` 自相矛盾，用户按文档算会以为应该 met。
- **结论**：gate 的「不可无声失败」只在错误路径成立；语义误判的方向目前偏向**过度 FAIL**（悬空/跨 feature/覆盖过严），加上一处**文档性失效**（公式）。作为门禁它是可靠的拦截器，但不是可以单独解释结果的判定器——需要 `checks` + 明细一起读。

---

## 13. 隐含需求（重写会静默丢掉的东西）

1. `bite.feature_id IS NULL` 的全局咬合对每个包含该节点的 feature 生效。
2. 其它 feature 在共享节点上的咬合进入本 feature 的 gate，但不进入 coverage。
3. `bite.feature_id == F` 但节点已移出 scope 时，gate 仍统计（节点存在即可）。
4. `drift_report` 不校验节点存在：悬空 UNMAPPED/DOC-ONLY 会拦门，同时又被列进 `ignored_dangling_bites`。
5. drift 不按 phase 过滤，任何阶段记录的漂移判决都计入。
6. coverage 的 hits 是历史累积，KEEP 不撤销旧命中。
7. gate 要求六个阶段全部覆盖；work-judge 只要求当前阶段。
8. `coverage` 不校验 ε>0 / prior_p∈[0,1]；ε≤0 让所有阶段 trivially met。
9. `coverage.enforced` 只看 feature 策略，`--epsilon` 覆盖不会改变它。
10. `index` 字段只展示，没有任何命令消费它做调度。
11. conformance 的 `verifies` 不校验 src kind。
12. conformance 的锚点只在 scope 内找 maps_to 目标。
13. evidence 无产物也算合格；有产物但 hash 为空也合格；任一合格即通过。
14. reconcile 的 retry/coverage-gap/drift-over-limit/construction-open/stale-node 五类动作没有文档、没有测试，但会阻止 converged 并出现在 serve 输出里。
15. `applied` 可能包含 rowcount=0 的 release-stale-claim。
16. claim_ttl=0 立即回收；claimed_at 缺失/解析失败按过期处理。
17. serve 恒 0 退出；未知 feature 静默成功；单 feature 异常中止整轮；`--apply` 每趟 commit。
18. gate/coverage 的 `--json` 是空旗标；所有命令默认输出 JSON。
19. gate 错误走 stderr + 退出 2，stdout 为空。
20. gate 的 conformance 子报告缺 `enforced`；reconcile 的 gate 子对象只有 result/reason。
21. 同一坏 feature 上 coverage/conformance 成功、gate/reconcile/serve 失败。

---

## 14. 值得人判断的问题

1. 覆盖检查在 gate 阶段到底要求「当前阶段」还是「全部六个阶段」？work-judge 与 gate 现在不是同一个检查。
2. 其它 feature 写在共享节点上的咬合，应该影响本 feature 的门禁吗？gate 说影响，coverage 说不影响。
3. 悬空 bite 应该只由 doctor 清理，还是同时在 drift 里排除？现在它既被「忽略」又导致 FAIL。
4. `n_required` 按文档的 `(1+d)/(10+m)` 修代码，还是按实现的 `9+m` 改文档？P1 已经造成 p 与 met 自相矛盾。
5. `prior_p` 是「Beta 先验均值」还是固定 Beta(1,9)？现在把先验强度写死为 10，文档没说。
6. serve 是否应该像 reconcile 一样用退出码表达未收敛？恒 0 会让 CI 把「跑过」当成「收敛」。
7. serve 遇到单个坏 feature 应该跳过并报告，还是中止整轮？长驻进程会被一个坏库杀死。
8. conformance 的 `verifies` 是否必须来自 testcase？收紧会让现有库突然 violations>0。
9. reconcile 的五类非自动动作是否是对外稳定契约？serve 的消费者可能已经在解析它们。
10. gate 的「不可无声失败」是否需要定义空作用域与裸证据的下限？PASS 现在不代表设计正确，评审者需要知道边界。
