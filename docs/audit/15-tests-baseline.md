# 15 测试盘点与基线

## 0. 切片范围

`tests/` 下实际有 **16** 个 `test_*.py`，5763 行（任务描述写「15 个 / 约 4720 行」，与磁盘不符：少算了 `test_planner.py` 94 行，且各文件行数普遍比描述多 10%——描述的行数应是旧版本）。

| 文件 | 行数 | 用例 | `self.assert*` | 角色 |
|---|---:|---:|---:|---|
| test_wxg.py | 1895 | 85 | 335 | CLI 端到端主回归：37 条命令、迁移、门禁、导出、并发以外的全流程 |
| test_plan_cli.py | 865 | 39 | 119 | plan/brief/blind-check/apply/impact/cycles/conflicts/up 的 e2e |
| test_package_units.py | 753 | 87 | 134 | 包内纯函数 + 内存 SQLite：jsonio/work/db 方言/graph 校验/gates/导入解析 |
| test_wxg_mysql.py | 485 | 13 | 70 | 纯标准库 MySQL 客户端，连真实 MariaDB（默认 127.0.0.1:3307） |
| test_graph_algo.py | 216 | 30 | 51 | SCC/分层/反链/可达/analyze 纯算法 |
| test_cycles.py | 173 | 25 | 42 | 环检测/最小断边集/断边建议/环形状 |
| test_briefing.py | 172 | 12 | 16 | 盲化 brief 的边界展开与输入判定 |
| test_impact.py | 153 | 15 | 24 | 影响闭包/跳数/断边 |
| test_reducer.py | 146 | 10 | 21 | 补丁归一化与合并不交叠 |
| test_derive.py | 143 | 15 | 22 | 按目录分组与 depends 推导 |
| test_pg_backend.py | 143 | 3 | 10 | PostgreSQL 后端 IT，默认 skip |
| test_mysql_backend.py | 140 | 3 | 10 | MySQL 后端 IT，默认 skip |
| test_engine.py | 140 | 7 | 14 | `Engine` 库 API（不经 subprocess） |
| test_blind.py | 135 | 12 | 28 | 盲测输出合法性判定 |
| test_planner.py | 118 | 13 | 24 | 分层选择/并行度/bottleneck 文案 |
| test_conflicts.py | 86 | 12 | 20 | 目标模式重叠判定 |

合计 **381 条用例、940 条断言**。只用标准库；没有 pytest 依赖、没有 `conftest.py`、没有 `tests/__init__.py`。

## 1. 基线（唯一事实）

在本机工作区根目录执行：

```
python -m unittest discover -s tests -v
```

| 指标 | 值 |
|---|---|
| 用例 | **381** |
| 通过 / 失败 / 错误 | 381 / 0 / 0 |
| 跳过 | **6**（`test_mysql_backend` 3 条、`test_pg_backend` 3 条，均因未设 `WXG_TEST_*_URL`） |
| 耗时 | **185.0 s**（`Ran 381 tests in 185.005s`，总墙钟 185.4 s） |
| 退出码 | 0 |

移除 MariaDB（把 `WXG_MYSQL_TEST_URL` 指向死端口，等价 CI 环境）再跑：

| 指标 | 值 |
|---|---|
| 用例 | **370** |
| 跳过 | **7** |
| 耗时 | **170.7 s** |
| 退出码 | 0 |

差异来源：`test_wxg_mysql.MySQLClientTestCase` 有 11 个方法，`setUpClass` 抛 `SkipTest` 时 unittest 只计 1 条 skip（实测该模块单独跑报 `Ran 2 tests ... skipped=1`），所以 381 − 11 = 370。**「381」是两个口径里较大的那个，CI 口径是 370。**

耗时分布（分模块实测）：

| 模块 | 耗时 | 说明 |
|---|---:|---|
| test_wxg.py | 110.5 s | 每条用例 2–10 次 `subprocess` 调 CLI，每次 ~0.2 s |
| test_plan_cli.py | 48.4 s | 同上 |
| test_engine.py | 10.6 s | 也是 subprocess 夹具，7 条用例 |
| test_wxg_mysql.py | 2.6 s | 需本机 MariaDB |
| 其余 12 个模块 | < 0.2 s | 纯函数/内存库 |

失败与错误：**0 条**（`FAIL:`/`ERROR:` 行数均为 0）。这是本次审计唯一可复现的事实地基。

本机 `127.0.0.1:3307` 确实有可连的 MariaDB，`test_wxg_mysql` 的 13 条实跑通过；换个没装 MariaDB 的机器，这 13 条会静默变成 1 条 skip。

## 2. 公开面

这个切片的「对外入口」不是业务命令，而是测试本身的可调用方式、环境开关，以及它落盘的东西。

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `python -m unittest discover -s tests -v` | cli | `tests/` | 无 | stderr 逐条 `... ok/skipped`，尾部 `Ran N tests` / `OK`；stdout 为空 | 写 `__pycache__`；每个 e2e 用例在系统临时目录建 `<tmp>/state/graph.sqlite`（WAL）与 `<tmp>/state/export/`；跑完 `rmtree(ignore_errors=True)` | 0 全绿 / 1 有失败 |
| `python -m unittest tests.test_xxx -v` | cli | 各模块 | 模块名 | 同上 | 同上 | 同上 |
| `tests.test_x.Class.test_y` | cli | 各用例 | 点分名 | 同上 | 同上 | 同上 |
| `WXG_TEST_MYSQL_URL` | env | `tests/test_mysql_backend.py:28,31` | MySQL URL | 未设→整类 skip；设了→`setUpClass` 先 `SHOW TABLES` + `DROP TABLE` **清空目标库** | 破坏性：删目标库所有表 | 0（带 skip） |
| `WXG_TEST_PG_URL` | env | `tests/test_pg_backend.py:27,30` | PG URL | 未设→skip；设了→`DROP SCHEMA public CASCADE` | 破坏性：重置 public schema | 0（带 skip） |
| `WXG_MYSQL_TEST_URL` | env | `tests/test_wxg_mysql.py:29-30,47-58` | MariaDB URL | 默认 `mysql://root:wxgpass@127.0.0.1:3307`；连不上→类级 skip | 建/删库 `wxg_client_test_<pid>`；建/删临时用户 | 0（带 skip） |
| `WXG_SKILL_DIR` | env | `tests/test_wxg.py:498` | 技能根目录 | 让 `verify` 指向拷出来的树 | `shutil.copytree(SKILL, copy)`：把整棵树（当前 9.6 MB / 335 文件，含 `dist/` 13 个 zip、`docs/audit/` 里的临时 sqlite）复制到临时目录 | 0 |
| `<tmp>/state/graph.sqlite` | file | `test_wxg.py:47,155`；`test_plan_cli.py:50,128` | CLI 写入 | SQLite 状态库 + `-wal`/`-shm` | 写；用例内直接 SQL 断言 | — |
| `<tmp>/state/export/<feature>/*.md` | file | `test_wxg.py:264-268,628,753,1020,1198` | `wxg export` | 6 份 Markdown | 写 | — |
| `<tmp>/artifact.txt`、`result.json`、`patch*.json` | file | `test_wxg.py:572`；`test_plan_cli.py:275,423,462` | 用例自造 | 证据产物/盲测产出/补丁 | 写 | — |
| `wxg.make_temp_dir` / `whyexist.*` 私有符号 | function | `test_wxg.py:24,617,1411`；`test_plan_cli.py:24`；`test_engine.py:18-20`；`test_package_units.py:18-23`；`test_mysql_backend.py:25,46`；`test_pg_backend.py:25,48` | 测试直接 import | 复用内部实现 | 无 | — |

> 注意：e2e 夹具把 stdout/stderr 混读（`test_wxg.py:61-83`），所以上表「错误走 stderr」这一层并不是测试锁住的承诺，见 C4。

## 3. 50 条命令 × 测试覆盖矩阵

状态口径：**专测** = 有测试直接断言该命令的输出/退出码；**专测(弱)** = 只有 1 条断言或只覆盖部分字段；**间接** = 只在别的用例里当夹具，无自己的断言；**仅错误** = 只测了失败路径；**零** = 全项目无引用。

| # | 命令 | 状态 | 代表性证据 |
|---:|---|---|---|
| 1 | init | 专测 | `test_wxg.py:632,683,957` |
| 2 | up | 专测 | `test_plan_cli.py:337,353,518` |
| 3 | repo-add | 专测(弱) | `test_wxg.py:904`（只测非 python）；正向只在夹具 `test_wxg.py:87` |
| 4 | repo-list | **仅错误** | `test_wxg.py:947-955`（只验缺库退 2，成功输出了无断言） |
| 5 | import-file | 专测 | `test_wxg.py:334,353,909,1559`；`test_plan_cli.py:537` |
| 6 | import-repo | 专测(弱) | `test_plan_cli.py:567-584`（2 个文件） |
| 7 | derive | 专测 | `test_plan_cli.py:587,602,649` |
| 8 | promote | 专测 | `test_plan_cli.py:629,649` |
| 9 | sample | 专测(弱) | `test_wxg.py:1079-1091`（1 条） |
| 10 | feature-declare | 专测 | `test_wxg.py:1238,1613,1628,1642,1758` |
| 11 | feature-register | 专测 | `test_wxg.py:698,710,744,757,771` |
| 12 | **feature-list** | **零** | 全仓无 `"feature-list"` 字面量；见 C43 |
| 13 | feature-status | 专测 | `test_plan_cli.py:723,776` |
| 14 | change-open | 专测 | `test_wxg.py:1446,1455,1477,1520` |
| 15 | change-diff | 专测 | `test_wxg.py:1491` |
| 16 | work-open | 间接 | `test_wxg.py:431,884`（自身输出只被切片用例间接用） |
| 17 | work-seed | 间接 | `test_wxg.py:710`（靠 g2 领取间接证明） |
| 18 | work-claim | 专测 | `test_wxg.py:527,1291` |
| 19 | work-finish | 专测 | `test_wxg.py:444,1357` |
| 20 | work-judge | 专测 | `test_wxg.py:527,822,1133` |
| 21 | work-list | 专测(弱) | `test_wxg.py:334,1455`（只断言 status 字段） |
| 22 | upsert-node | 专测 | `test_wxg.py:465,812,848,1430` |
| 23 | upsert-edge | 专测(弱) | `test_wxg.py:1246`（只测 applies 方向） |
| 24 | **bind** | **间接** | 仅 `test_wxg.py:229-231` 在 full flow 里调用；无拒绝/方向/默认 kind 断言 |
| 25 | retract | 专测 | `test_wxg.py:371` |
| 26 | bite | 专测 | `test_wxg.py:308,1055,1093` |
| 27 | evidence-record | 专测 | `test_wxg.py:569,589,792,822` |
| 28 | evidence-list | 专测(弱) | `test_wxg.py:581`（只断言 1 条） |
| 29 | coverage | 专测 | `test_wxg.py:1133,1158,1299`；`test_plan_cli.py:746` |
| 30 | reconcile | 专测 | `test_wxg.py:1326,1339,1357,1376` |
| 31 | serve | 专测 | `test_wxg.py:1659,1678,1695` |
| 32 | sync | 专测 | `test_wxg.py:1585,1605` |
| 33 | plan | 专测 | `test_plan_cli.py:150,184,201,212,525` |
| 34 | cycles | 专测 | `test_plan_cli.py:684,703,782,803,821` |
| 35 | brief | 专测 | `test_plan_cli.py:230,255`；`test_briefing.py` |
| 36 | blind-check | 专测 | `test_plan_cli.py:266,294,323`；`test_blind.py` |
| 37 | patch | 专测(弱) | `test_plan_cli.py:435,446,480`（只断言退出码，不查补丁文件内容） |
| 38 | apply | 专测 | `test_plan_cli.py:448,483,507` |
| 39 | impact | 专测 | `test_plan_cli.py:360,735,741,838`；`test_impact.py` |
| 40 | conflicts | 专测 | `test_plan_cli.py:387,401`；`test_conflicts.py` |
| 41 | conformance | 专测 | `test_wxg.py:1704,1758,1795,1814` |
| 42 | gate | 专测 | `test_wxg.py` 20 处 + `test_plan_cli.py:746` |
| 43 | export | 专测 | `test_wxg.py:189,608,744,1004` |
| 44 | slice | 专测 | `test_wxg.py:431,1277` |
| 45 | get | 专测(弱) | `test_wxg.py:353,744,1028` |
| 46 | find | 专测(弱) | `test_wxg.py:346,925,1277` |
| 47 | role-prompt | 专测(弱) | `test_wxg.py:894-902`（字符串子串断言） |
| 48 | contract | 专测(弱) | `test_wxg.py:518-525`（只钉 6 个字段） |
| 49 | verify | 专测(弱) | `test_wxg.py:481,873` |
| 50 | doctor | 专测 | `test_wxg.py:391,569,957,1535` |

**零测试命令：`feature-list` 1 条。** 只有错误路径的命令：`repo-list`。只有间接覆盖的命令：`bind`。

## 4. 契约表

状态：covered = 有测试直接断言；partial = 只覆盖部分分支/路径；gap = 行为存在但无测试。

| id | 承诺 | 状态 | 证据 |
|---|---|---|---|
| C1 | 全量套件在当前工作区发现 381 条、全通过、退出 0，耗时约 185 s | covered | 实测；`README.md:117` |
| C2 | 没有 MariaDB 时仍全绿：370 条、7 skip、退出 0 | covered | 实测（`WXG_MYSQL_TEST_URL` 指向死端口） |
| C3 | 每条 e2e 用例使用独立临时状态库，不碰工作区 `./.why-exist` | partial | `test_wxg.py:47-58`、`test_plan_cli.py:50-58`（构造保证，无断言）；`CONTRIBUTING.md:47` 是唯一书面承诺 |
| C4 | 失败给可读 JSON 到 **stderr**、stdout 为空、退出 2 | partial | 实现 `cli.py:85-90`；测试只断言退出码与 `error` 键（`test_wxg.py:61-83,479`），M5 变异（错误改打 stdout）**存活** |
| C5 | 成功输出 JSON 到 stdout、退出 0 | covered | `test_wxg.py:61-83`（全量解析）；缩进/中文转义未断言 → 格式层 partial |
| C6 | `gate` PASS=0 / FAIL=1 | covered | `test_wxg.py:304,868`；M4 变异被杀 |
| C7 | `verify` ok=0；文档块漂移时非 0 且 stdout 含「过期」 | partial | `test_wxg.py:481-501`：只改 SKILL.md 的 main 块；`references/contract.md` 的 full 块、frontmatter、资源缺失、导出样例过期均无用例 |
| C8 | `doctor` 无问题=0、有问题=1、`--fix` 后=0 | covered | `test_wxg.py:408,415,586` |
| C9 | `apply` 冲突=1、dry-run=0、成功=0 | covered | `test_plan_cli.py:448,483,507` |
| C10 | `reconcile` 不收敛=1、收敛=0 | covered | `test_wxg.py:1331,1348` |
| C11 | 状态库缺失时命令退 2 且不创建目录 | partial | `test_wxg.py:947-955`，只覆盖 gate/work-seed/repo-list 3 条；其余 41 条靠 `cli.py:66-69` 统一分支 |
| C12 | `verify` 零副作用（不建 `.why-exist`） | covered | `test_wxg.py:873-882` |
| C13 | `plan` 只读：执行前后 12 张表快照完全一致 | covered | `test_plan_cli.py:184-199` |
| C14 | `gate` 只读：库文件 sha256 不变 | covered | `test_wxg.py:299-306` |
| C15 | `sync` 只读：库文件 sha256 不变 | covered | `test_wxg.py:1585-1600` |
| C16 | `reconcile` dry-run 只读且两次输出相同 | covered | `test_wxg.py:1326-1337` |
| C17 | `serve --once` 默认只读，`--apply` 才写 | covered | `test_wxg.py:1659-1678` |
| C18 | SQLite 用 WAL；claim 写 `claimed_at` | covered | `test_wxg.py:1391-1402`（实现细节，非用户承诺） |
| C19 | `schema_version=9`、契约版本 `2.92.0`（测试硬编码） | covered | `test_wxg.py:520-521,652,425` |
| C20 | 状态库含 meta/repos/nodes/edges/features/conditions/work_items/feature_nodes/evidence/bites/judge_history/changes 12 张表 | partial | 快照查询隐含要求（`test_wxg.py:157-166`、`test_plan_cli.py:44-46`）；无 DDL 断言 |
| C21 | `export` 在 `<root>/export/<feature>/` 写 6 份 md | partial | 只断言 4 份：`test_wxg.py:266,753,1198,1020`；`05-类图.md` 与 `测试规格.md` 零断言 |
| C22 | 导出表格转义 `\|`；共享 parameter 去重 | covered | `test_wxg.py:1004-1026,608-630` |
| C23 | `up` 幂等、`next` 首步是 `import-file --prepare`、gate FAIL 仍退 0 | partial | `test_plan_cli.py:337-351`；FAIL 时退 0 未显式断言 |
| C24 | `up --template minimal` 只建 feature 不建仓 | covered | `test_plan_cli.py:518-522` |
| C25 | `import-file` 重导入幂等（inserted=0/updated>0），并保留手写 attrs | covered | `test_wxg.py:334-351,353-369` |
| C26 | 符号消失→stale=1、复现→清 0，stale 会让 gate FAIL | covered | `test_wxg.py:1559-1583` |
| C27 | 非 python 仓给可读 Reject（不提 `wxg_import`） | covered | `test_wxg.py:909-923` |
| C28 | `import-repo` 递归扫全仓 `.py` | partial | `test_plan_cli.py:567-584`（2 个文件） |
| C29 | `derive` 默认 dry-run、组件≤1 带 hint；`--apply` 写 `origin=derived` | covered | `test_plan_cli.py:587-626` |
| C30 | `promote` 只收 derived，改成 declared 并记 `x_promoted_by` | covered | `test_plan_cli.py:629-681` |
| C31 | `work-claim` 必须 `--actor`；裁决 actor ≠ claimed_by | covered | `test_wxg.py:527-567` |
| C32 | `work-finish` 清 claim_token；`work-judge(passed)` 后 status=passed | covered | `test_wxg.py:444-463` |
| C33 | 写图必须 token + 角色 + id 落在 target_ids 内 | partial | 只有 `upsert-node` 越界（`test_wxg.py:465-479`）；上一切片已确认 import-file/edge/bind/retract 的边界无测试 |
| C34 | coverage 未达标阻断 judge；`next` 指向首个未达阶段 | covered | `test_wxg.py:1133-1156,1299-1308` |
| C35 | 同一节点只认最新咬合，跨节点 KEEP 不抵消；失败历史只增不删 | covered | `test_wxg.py:1055-1077,1102-1131` |
| C36 | evidence 按 generation 记账；artifact 被删/被改→gate FAIL + doctor 报错 | covered | `test_wxg.py:792-810,569-606` |
| C37 | `doctor --fix` 只修可修项，legacy 身份不自动修 | covered | `test_wxg.py:391-429,675-678` |
| C38 | `init` 迁移旧库（补列、回填 legacy、judge_history），重复执行不改已有行 | covered | `test_wxg.py:632-679,683-696,957-1002`（仅 SQLite） |
| C39 | `change-open` 从第 N 条件继承/重置，generation+1，二次 open 拒绝 | covered | `test_wxg.py:1446-1533` |
| C40 | `conformance` 报 6 类差异；`--conformance` 开启后 gate FAIL | covered | `test_wxg.py:1704-1890`；`test_package_units.py:555-687` |
| C41 | 并发 `work-claim` 只有一个成功（退出码 {0,2}） | gap | 只有 `test_mysql_backend.py:109-126`、`test_pg_backend.py:112-129`，默认 skip；SQLite 无并发用例 |
| C42 | MySQL/PG 后端 `init` 返回 `backend=mysql/postgres`、`schema_version=9` | gap | `test_mysql_backend.py:86-89`、`test_pg_backend.py:88-91` 默认 skip；且 `08-cmd-repo` 已证非 SQLite 上 `init` 走 NameError |
| C43 | `feature-list` 输出 `{features:[{id,name,generation,conditions}]}` | gap | 0 测试；探针实跑确认形状（`docs/audit/_probe_15e.py`） |
| C44 | `repo-list` 输出 `{repos:[{id,path,language,created_at}]}` | gap | 只测缺库错误（`test_wxg.py:947-955`）；探针确认成功形状 |
| C45 | `bind` 只收 parameter/argument/assertion、方向随 kind、默认边 kind 来自 `BIND_EDGE_KIND` | partial | 只在 `test_wxg.py:229-231` happy path 被调用 |
| C46 | `gate --json` / `coverage --json` 改变输出形态 | gap | 两个 handler 都不读 `args.json`；实测两种调用 stdout 逐字节相同；测试仍照传（20+ 处） |
| C47 | `--db-url` 全局参数覆盖 `WXG_DB_URL`，非法协议退 2 | gap | 全项目无 `--db-url` 用例；探针确认行为 |
| C48 | `WXG_ACTOR` 环境变量作为 actor 兜底 | gap | 测试一律显式 `--actor`；无一处设 `WXG_ACTOR` |
| C49 | 相对 `--root` 可用 | gap | 所有测试传绝对路径 |
| C50 | `--data/--target-ids/--ids` 支持 `@文件` 与 BOM | covered | `test_wxg.py:884-892`；`test_package_units.py:41-45` |
| C51 | 中文/UTF-8 输出可解析 | partial | 测试统一 `encoding="utf-8"` + `PYTHONUTF8=1`（`test_wxg.py:21,66`），但没断言字节 |
| C52 | `Engine` 只读 API（plan/brief/blind_check/gate/impact/close） | covered | `test_engine.py:82-136` |
| C53 | 纯函数确定性：graph_algo/planner/impact/reducer/briefing | covered | `test_graph_algo.py:194-212`；`test_planner.py:109-114`；`test_impact.py:128-131`；`test_reducer.py:124-142`；`test_briefing.py:150-159` |
| C54 | 算法边界：空图/自环/双环/悬空边/截断 | covered | `test_graph_algo.py:29,93,182`；`test_cycles.py:40,90-94`；`test_planner.py:99-107` |
| C55 | SQL 方言翻译 5 种形态 + `?`→`%s` | partial | `test_package_units.py:181-222` 只是字符串级断言，无一条在真实后端执行 |
| C56 | `_named_params` 遇字符串字面量里的 `:x` 会误判（已知限制） | covered | `test_package_units.py:231-235` |

## 5. 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `graph.sqlite:meta/repos/nodes/edges/features/conditions/work_items/feature_nodes/evidence/bites/judge_history/changes` | both | 快照 `test_wxg.py:157-166`、`test_plan_cli.py:44-46,130-138`；直接 SQL 断言 `test_wxg.py:380-386,420-426,553-567` 等 |
| `<tmp>/state/`（新建/删除） | write | `test_wxg.py:47-58`；`test_plan_cli.py:50-58` |
| `<tmp>/state/export/<feature>/*.md` | write（由 `wxg export`） | `test_wxg.py:264-268` 等 |
| `<tmp>/artifact.txt` | write | `test_wxg.py:572-576` |
| `<tmp>/{out,patch,result}.json` | write | `test_plan_cli.py:275,303,423,437,462,470,496` |
| 整棵技能树副本 `<tmp>/skill-copy` | write | `test_wxg.py:489-490`（含 `dist/`、`.git`、`docs/audit/` 临时库） |
| `env:PYTHONUTF8` / `PYTHONIOENCODING` | write（子进程 env） | `test_wxg.py:21`；`test_plan_cli.py:21`；`test_mysql_backend.py:54`；`test_pg_backend.py:56` |
| `env:WXG_SKILL_DIR` | write | `test_wxg.py:498` |
| `env:WXG_DB_URL` | write | `test_mysql_backend.py:54`；`test_pg_backend.py:56` |
| `env:WXG_TEST_MYSQL_URL` / `WXG_TEST_PG_URL` / `WXG_MYSQL_TEST_URL` | read | `test_mysql_backend.py:28`；`test_pg_backend.py:27`；`test_wxg_mysql.py:29` |
| MariaDB：库 `wxg_client_test_<pid>`、用户 `wxg_cli_<pid>` | both（建/删） | `test_wxg_mysql.py:44,51-65,398-430` |
| 仓库内文件 | **不写**（除 `__pycache__`） | 全量扫描；`plan-test.log` 是历史残留，非测试产出 |

跨命令共享状态（测试依赖、但不是显式夹具）：`--root` 目录、SQLite WAL 文件、`WXG_DB_URL` 进程级环境变量（`cli.py:55-56` 会写 `os.environ`，同进程后续调用继承；测试从没走过这条）。

## 6. 冗余信号

| 项 | 信号 | 置信 |
|---|---|---|
| CLI 夹具重复 4 份 | `test_wxg.py:61-166`、`test_plan_cli.py:62-146`、`test_mysql_backend.py:59-84`、`test_pg_backend.py:61-86` 的 `cli()`/`init_repo()`/`db_snapshot()` 近乎逐行相同；8 行块跨文件重复共 51 组 | high |
| `SHOP_PY` 夹具重复 4 份 | `test_wxg.py:26-42`、`test_plan_cli.py:26-42`、`test_mysql_backend.py:50-53`、`test_pg_backend.py:52-55` | high |
| TABLES 元组重复 | `test_wxg.py:162-163`、`test_plan_cli.py:44-45` | high |
| mysql/pg 后端 IT 互为副本 | 两个文件 140/143 行，除 URL 与 backend 断言外几乎一致 | high |
| `gate --json` / `coverage --json` 是死开关 | `commands_gates.py` 全文无 `args.json`；实测输出相同；测试 20+ 处照传 | high |
| 「381」在 CHANGELOG 里被当发布门数字 | `CHANGELOG.md:8,17,30,...` 连续几十条「测试 381 不变」，但测试数不等于覆盖 | medium |
| 文档计数漂移 | `README.md:139` 写 test_wxg 79 条（实际 85）；`README.md:116` 写 contract v1.1.0 / schema v8（实际 2.92.0 / 9）；`references/design.md:280` 写 76→95 | high |
| 三种 DB 跳过机制 | `skipUnless(env)`（mysql/pg）、`setUpClass` 抛 `SkipTest`（wxg_mysql）——同一件事三种写法，行为不同（一个按类、一个按环境变量） | high |
| 测试文件几乎全部不在版本控制 | `git ls-files tests` 只有 `tests/test_wxg.py`；HEAD 版本仅 42 条用例；`scripts/whyexist/` 整个包未跟踪 | high |
| 验收产物污染 verify 夹具 | `copytree(SKILL)` 会复制 `docs/audit/_probe_*_tmp/*.sqlite` 与 `dist/`（13 个 zip，3.5 MB） | medium |
| 根目录残留日志 | `plan-test.log`（1233 B，`*.log` 已 gitignore）是旧的一次手工跑测输出 | low |

## 7. 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `tests/test_wxg.py` | **keep** | 85 条、335 断言，覆盖 37 条命令与全部门禁语义；20 条「只读性」断言是整个项目最硬的安全网。变异测试证明它对行为回归敏感（M4 被杀） | 单文件 1895 行、夹具与断言混在一起；`test_contract_verify_detects_drift` 靠 copytree 整树，仓库变大会慢/挂 |
| `tests/test_plan_cli.py` | **keep** | 39 条覆盖 plan/brief/blind/apply/impact/cycles/conflicts/up，都是纯读或明确写入语义；`plan` 的 12 表快照是不可替代的只读证明 | 依赖 `subprocess`，48 s；up 的 gate FAIL 退 0 未显式断言 |
| `tests/test_package_units.py` | **keep** | 87 条、134 断言，直接打内存库；覆盖方言翻译、state machine、coverage 数学、conformance 报告——重写这些模块时是唯一快速反馈 | 方言翻译只有字符串断言，不能证明 SQL 能跑；私有符号耦合 |
| `tests/test_graph_algo.py` | **keep** | 30 条纯函数，边界完整（空图/自环/双环/顺序无关/确定性） | 无大图/性能用例 |
| `tests/test_planner.py` | **keep** | 13 条锁层级选择、并行度、bottleneck 中文文案 | 文案子串断言（`:85-101`）会把措辞改动判成回归 |
| `tests/test_cycles.py` | **keep** | 25 条锁环、断边集、建议排序、形状与 guidance | `truncated` 只有一条；2^n 枚举的成本没测 |
| `tests/test_impact.py` | **keep** | 15 条覆盖闭包/跳数/断边/跨 feature | CLI 侧只测了 affected/closed，`cross_feature` 无 CLI 用例 |
| `tests/test_derive.py` | **keep** | 15 条覆盖分组键、跨组 depends、排除目录、文件依赖 | `depth<=0` 语义未在用例里出现 |
| `tests/test_briefing.py` | **keep** | 12 条锁盲化键集（15 键）、边界展开、输入判定、确定性 | 字段顺序、文案没锁 |
| `tests/test_blind.py` | **keep** | 12 条覆盖 PASS/FAIL 三类判定与 locality 趋势 | locality 精确值没锁 |
| `tests/test_reducer.py` | **keep** | 10 条覆盖去重、指纹冲突、端点跨补丁、交换律 | 指纹范围（repo/path/unmapped）没测 |
| `tests/test_conflicts.py` | **keep** | 12 条锁通配重叠与边界情况 | 纯函数，CLI 侧另有 2 条 |
| `tests/test_engine.py` | **keep** | 7 条锁公开 Python API；`Engine` 是文档承诺的入口（`README.md:48`） | 只测了 fail 路径的 gate；close 后重连未测 |
| `tests/test_wxg_mysql.py` | **refactor_in_place** | 13 条覆盖协议细节（转义、rowcount、事务、并发写、大文本、百分号凭据、AuthSwitch），质量高且能真跑 | 依赖本机 MariaDB，默认静默降级为 1 条 skip；CI 里等于不存在。应改成显式开关 + CI service |
| `tests/test_mysql_backend.py` | **rewrite** | 与 pg 版 90% 重复、破坏性 `setUpClass`、默认 skip，实际从未在 CI 跑过；行为边界清楚，值得合并成参数化后端套件 | 它正是 `init` 在非 SQLite 上 NameError 没被发现的原因；重写前先决定后端是否进 CI |
| `tests/test_pg_backend.py` | **rewrite** | 同上；另需 psycopg，环境更难得 | 同上 |
| `.github/workflows/ci.yml` | **refactor_in_place** | CI 跑 `verify` + `unittest discover`，矩阵 2 OS × 3 Python，设计正确 | 只 checkout 到 HEAD，而 15/16 个测试文件未跟踪 → CI 实际跑的是 42 条旧用例；不先修这个，任何「CI 全绿」都不是重写依据 |

## 8. 隐含需求（测试/实现里有、文档没写的）

1. **错误必须走 stderr**。M5 变异（`print(error)` 到 stdout）全套绿——这条承诺只存在于 `cli.py:86`，测试从未分辨流。
2. **成功 JSON 的格式**：`json.dumps(indent=2, ensure_ascii=False)`（`cli.py:95-112`）。测试只解析，不锁缩进与中文不转义。
3. `gate`/`coverage` 的 `--json` 是**空开关**；契约表却把它列为参数。
4. `doctor --fix` 会把 `meta.contract_version` 刷成当前版本（`test_wxg.py:425`）。
5. SQLite `journal_mode=wal`（`test_wxg.py:1399`）——实现细节被测试锁死。
6. `up` 的 `next` 第一条必须是 `import-file ... --prepare`（`test_plan_cli.py:344-346`）。
7. `feature-declare` 默认 `coverage.enforced=true, epsilon=1.0`；重声明沿用旧策略（`test_wxg.py:1613-1654`）。
8. `import-file` 写库只认 claim 所属 feature，`--feature` 只在 prepare 生效（`test_wxg.py:337-343`）。
9. `serve --once` 由 handler 自己 `print` 一份 JSON，CLI 层不再打印（`cli.py:106-108`）。
10. 测试直接依赖内部符号：`wxg.make_temp_dir`、`wxg.upsert_node/upsert_edge/bind_node`、`wxg.Reject`、`whyexist.gates._required_coverage`。改内部 API 会先红测试，改对外行为不一定红。
11. 平台假设：`--root` 会被 `resolve()` 成长路径，测试也 `resolve()` 后比较（`test_wxg.py:48-50`，Windows 8.3 短名修复）。
12. `evidence-record` 默认 `exit_code=0`；`--artifact` 存绝对路径 + SHA-256。
13. 快照断言依赖 `SELECT * ... ORDER BY 1` 的行序——加列会改变快照但不一定改变契约。
14. `WXG_SKILL_DIR` 只为测试而存在，文档从未写（`docs/audit/03-contract-rules.md:142`）。

## 9. 值得人判断的问题

1. **要不要先把 `tests/` 纳入版本控制，再谈重写？** 现在 381 条只活在工作区；HEAD 只有 42 条。任何 `git reset --hard` / `git clean -fdx` 会连 `scripts/whyexist/` 一起抹掉。这不是测试质量问题，是安全网是否存在的事实问题。
2. mysql/pg 后端要不要进 CI？不进，后端就只能冻结；进，就得决定容器化成本与两个破坏性 `setUpClass` 的重写。
3. 错误流（stderr）与退出码是不是正式契约？M5 已证明它会静默回归。补一条 `assert proc.stdout == ""` 成本极低。
4. `gate --json` / `coverage --json` 保留还是删？保留就该有行为（例如紧凑输出），删就要同步契约块与 20+ 处测试调用。
5. `05-类图.md`、`测试规格.md` 的导出内容要不要锁？`verify` 的样例逐字节校验间接锁了一部分（样例文件本身），但 `export` 行为没有直接断言。
6. SQLite 并发 claim 的语义（WAL + `busy_timeout`）要不要测？现在并发只有 mysql/pg 用例，而默认后端是 SQLite。
7. `test_wxg_mysql` 在无 MariaDB 的机器上降级为 1 条 skip——这算通过还是算「测试没跑」？现在的基线数字会因此变化 11 条。
8. CHANGELOG 把「381 不变」当发布门，是不是说明团队在用数量代替覆盖判断？本次审计已发现 1 条零测试命令、1 条仅错误路径命令、1 类「间接」命令。
9. `check_docs` 只校验 VERSION/CHANGELOG/design 编号，不校验 README 里的用例数与契约版本——要不要把它扩到文档自述的数字？
10. `verify` 用例复制整棵技能树（含 `dist/` 与 `docs/audit/` 临时库），是改成最小 fixture 目录，还是就这样？仓库越长，这条用例越脆。
