# 04 状态库 schema 与迁移 — 行为契约审计

## 切片范围

| 文件 | 行数 | 本片要回答的问题 |
|---|---|---|
| `scripts/whyexist/db.py` | 618 | 12 张表定义、7 个索引、0 外键；version 1→9 的迁移分支；连接参数与方言适配 |
| `scripts/whyexist/cli.py`（只取 L62-93） | — | 什么时候连库、commit 在哪、失败会不会连库都没连上就 traceback |
| `scripts/whyexist/commands_repo.py`（只取 `cmd_init`/`cmd_up`） | — | 建库入口的输入/输出/副作用 |
| `scripts/whyexist/commands_misc.py`（只取 `doctor_report`/`cmd_doctor`） | — | schema 健康度是谁在观察、能修什么 |
| `scripts/wxg.py`（只取 L31-49） | — | `SCHEMA_SQL`/`_table_columns`/`_is_integrity_error` 的 re-export 面 |
| `scripts/wxg_mysql.py`（只取完整性错误判定） | — | 第二份 `is_integrity_error` |

不在本片：各 `commands_*` 的业务语义（条件状态机、工单裁决、gate 规则）、`wxg_contract.py` 的契约常量、MySQL 协议客户端本身。

方法：`read` 通读 `db.py` 全文与相关调用点；用 `sqlite3` 在内存里 `executescript(SCHEMA_SQL)` 导出表/列/索引/外键；正则静态提取除迁移外的全部 `INSERT`/`UPDATE` 列名与 schema 比对（0 处漂移）；`symtable` 扫未定义全局名；在临时目录实跑 `init`/`doctor`/`repo-add`/坏库/旧库；在本机 MariaDB 12.3.3（127.0.0.1:3307）与 PostgreSQL 16.15（5433）上真库复现 init 与历史回填（临时库，跑完即删）；跑 `test_wxg` 迁移与 doctor 用例、`test_package_units.SqlDialectTest`/`NamedParamsEdgeTest`（13 例全绿）。未改任何源码。

## 公开面

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg init` | cli | `commands_repo.py:44-59` | `--root`、`WXG_DB_URL`/`--db-url` | `{root, db, backend, schema_version:9, contract_version, migrated}` | 建 root 目录与 graph.sqlite、12 表 + 7 索引、写 meta 两键；`init_db` 内部 commit | 0 / 2 |
| `wxg up` | cli | `commands_repo.py:62-127` | `--feature/--repo/--path/--template` | `{root, template, repo, feature, gate_result, gate, next[]}` | 自建连接与三次 commit；init_db + demo 仓 + feature-declare + 一次 gate | 0 / 2 |
| `wxg doctor` / `--fix` | cli | `commands_misc.py:558-617` | `--fix` | `{ok, issue_count, fixable_count, unfixable_count, unfixable_checks, by_check, truncated, issues[], fixed}` | `--fix` 删悬空 bites/edges/feature_nodes、清 token、写回 meta 版本 | 0 干净 / 1 有问题 |
| `connect(root)` | function | `db.py:441-465` | `Path` + `WXG_DB_URL` | 连接（sqlite Row 工厂 / 两个包装类） | sqlite：`mkdir -p`、开库、`foreign_keys=ON`、`busy_timeout=5000`、`journal_mode=WAL`；mysql：设 READ COMMITTED | 异常上抛（CLI 兜底外） |
| `ensure_db(conn)` | function | `db.py:468-483` | 连接 | None 或 `Reject` | 纯只读：查 meta 表是否存在 | 经 CLI → 2 |
| `init_db(conn)` | function | `db.py:605-616` | 连接 | `migrated` 字典 | 方言 DDL → `migrate_schema` → **commit** | 异常上抛 |
| `migrate_schema(conn)` | function | `db.py:509-602` | 连接 | `{变更键: 计数}` | ALTER 补列、UPDATE 回填、INSERT OR IGNORE 回填历史、UPSERT meta；**不 commit** | 异常上抛 |
| `db_url()` / `db_backend()` | function | `db.py:425-438` | `WXG_DB_URL` | URL / `sqlite\|mysql\|postgres` | 只读环境变量 | 未知协议 → 2 |
| `SCHEMA_SQL` / `MYSQL_SCHEMA_SQL` / `PG_SCHEMA_SQL` | function | `db.py:19-289`；`wxg.py:32-34` | — | 三份 DDL 字符串 | 无；被测试当夹具 `executescript` | — |
| `<root>/graph.sqlite` 的 12 张表 | table | `db.py:19-150` | — | 表/列/索引/唯一约束 | 文件形态的状态库是**外部读契约**：why-exist-uml 直接读 `nodes(id,kind,name,repo,path,symbol,attrs_json,unmapped)`、`edges(id,src,dst,kind,unmapped)`，带 `--feature` 还要 `features`/`feature_nodes`/`work_items` | — |
| `<root>/` 目录与 SQLite 文件（含瞬态 `-wal`/`-shm`） | file | `db.py:458-464` | `--root` | 目录 + 库文件 | `mkdir -p`；WAL 产生 `-wal`/`-shm` | 路径不可建 → traceback + 1 |

## 表登记

12 张表、7 个索引、**0 外键、0 CHECK**。核心表：`nodes`、`edges`、`features`、`work_items`、`bites`、`evidence`，外加 `conditions`——任务给的分法里它算辅助表，但 8 条件状态机只存在这张表里，按核心对待；辅助表：`meta`、`repos`、`feature_nodes`、`judge_history`、`changes`。

外部读契约：`.dsh/skills/why-exist-uml/SKILL.md:78` 明确声明它依赖 `nodes(id,kind,name,repo,path,symbol,attrs_json,unmapped)`、`edges(id,src,dst,kind,unmapped)`，带 `--feature` 时还依赖 `features`/`feature_nodes`/`work_items`。删列或改名不会让本仓测试变红，只会让那个技能在运行时拿不到列。

| 表 | 主键 | 索引 | 列要点 | 谁写 / 谁读 |
|---|---|---|---|---|
| `meta` | `key` | PK | `key,value`；只放 `schema_version`/`contract_version` | `db.py:596-600`、`commands_misc.py:590-599` / `db.py:594`、`commands_misc.py:538` |
| `repos` | `id` | PK + `path` UNIQUE | `path` 是唯一约束（repo-add 冲突唯一来源） | `commands_repo.py:137-141` / `graph.py:57` |
| `nodes` | `id` | PK | 12 列；`attrs_json`、`origin`、`unmapped`、`stale` | `graph.py:120-129`、`commands_repo.py:214,323,485` / 41 处 SELECT |
| `edges` | `id` | PK | 8 列；`evidence_path/line`、`unmapped`、`attrs_json` | `graph.py:169-186,208-212` / `gates.py:139` |
| `features` | `id` | PK | 10 列；`generation` 不是键；`coverage_epsilon/drift_limit/conformance` 三个开关列 | `commands_feature.py:102-121,175-218,359` / `workflow.py:26` |
| `conditions` | `(feature_id, generation, name)` | PK | 8 条件 × 每代 8 行；`status` 0/1、`reason` | `workflow.py:65`、`commands_feature.py:123-126,181,221` / `workflow.py:39,72` |
| `work_items` | `id` | PK、`claim_token` **部分唯一索引**、`(feature_id,generation)` | 17 列；`status/role/claimed_by/judged_by/claimed_at/assignee` | `work.py:29-43,54,57`、`commands_feature.py:528-532,652-690` / `commands_feature.py:515-520` |
| `feature_nodes` | `(feature_id,node_id)` | PK | 2 列，作用域绑定 | `graph.py:132`、`commands_graph.py:31,122` / `workflow.py:104` |
| `evidence` | `id` | PK、`(feature_id,name)` | 11 列；`generation` 可空、`artifact_sha256` | `commands_graph.py:169-176` / `evidence.py:22` |
| `bites` | `id`（自增） | `node_id`、`(feature_id,generation)` | 9 列；`verdict` 无 CHECK；`generation/phase` 可空 | `commands_graph.py:124-127` / `gates.py:23,64` |
| `judge_history` | `id` | PK、`work_item_id` | 9 列；只增不删 | `commands_feature.py:603-617`、`db.py:585-592` / `commands_feature.py:276` |
| `changes` | `id` | PK、`(feature_id,to_generation)` | 8 列；`from/to_generation` 与 `from_condition` | `commands_feature.py:376-379` / `commands_feature.py:303` |

代码 SQL 与表结构对齐情况：静态提取除 `db.py` 迁移语句外的全部 `INSERT`（28 条）与 `UPDATE`（26 条）的列名，**没有一处在表里不存在**；12 张表全部被代码碰过；逐列扫描后只有 `work_items.assignee` 是只写不读。

## schema 演进史（v1 → v9）

| 版本 | 引入变更 | 迁移分支 | 数据改写 |
|---|---|---|---|
| 1 | 初始 8 表（nodes/edges/features/conditions/work_items/feature_nodes/meta/repos） | 无（基线） | — |
| 2 | `work_items.claimed_by/judged_by/judged_at` + `evidence` 表 | `db.py:518-527` 补三列；`db.py:563-580` 标 legacy | 旧 claimed/submitted/passed/failed 行 `claimed_by='legacy'`；`judged_by='legacy'` + `judged_at` 用 created_at 兜底 |
| 3 | `evidence.generation` | `db.py:528-538` | 先按关联工单代、再按 feature 当前代回填；都不命中留 NULL |
| 4 | `features.coverage_epsilon`、`bites.generation/phase`、`judge_history` 表 | `db.py:539-541,551-562`；`judge_history` 靠 `CREATE TABLE IF NOT EXISTS` + `db.py:585-592` 回填 | bites 按 feature 当前代回填；历史按 `jh:<work_item_id>` 回填（每次 init 重跑，靠 NOT EXISTS 去重） |
| 5 | `features.drift_limit` | `db.py:542-544` | — |
| 6 | `work_items.claimed_at` | 同 `db.py:518-527`；`db.py:581-583` 回填 | 仅 `status='claimed'` 的行按 created_at 回填 |
| 7 | `changes` 表 | 无分支（DDL 的 `CREATE TABLE IF NOT EXISTS` 自动建） | — |
| 8 | `nodes.stale` | `db.py:548-550` | — |
| 9 | `features.conformance` | `db.py:545-547` | — |

结论：**没有 DROP/DELETE 型迁移，业务行一条不删**。唯一有损的写是 meta（无条件覆盖版本号）；其余回填都只填 NULL，但回填值是猜测、不留来源标记。所谓“v9”不是迁移状态机——`SCHEMA_VERSION` 不参与任何分支，每一步靠“列是否存在”判断。

## 关键发现

- **F1 旧库升级断链**：缺 `generation` 的旧 bites（schema 3/0.4.x）会让 `init` 在建索引阶段就失败——`db.py:613` 先跑完整 DDL，`idx_bites_feature`（`db.py:126`）引用迁移才补的列，`db.py:614` 的 ALTER 永远轮不到。实测 `OperationalError: no such column: generation`，重试同样失败。
- **F2 非 sqlite 后端 init 必失败且退出码说谎**：`commands_repo.py:48,49` 用了未导入的 `db_url`/`re` → NameError；而 `init_db` 已在 `db.py:615` commit，库其实建好了，命令却返回 2。MariaDB 12.3.3 与 PostgreSQL 16.15 实测均是 exit 2、12 张表与 meta 已提交。
- **F3 repo-add 冲突契约已坏**：`commands_repo.py:143` 的 `_is_integrity_error` 未导入，实测得到 NameError 而非「仓登记冲突」；`wxg.py:38` 的 re-export 救不了模块内全局名。
- **F4 ensure_db 名不副实**：只查 meta 表存在（`db.py:468-483`），不查版本也不查列；只有 meta+work_items 的库跑 doctor 直接 `no such table: nodes`。
- **F5 版本号单向默写**：`schema_version=99` 的库 `init` 后被无声改成 9，doctor 随后 ok（`db.py:593-601`）。
- **F6 约束为零**：12 表 0 外键 0 CHECK，唯一约束只有 `repos.path` 与 `work_items.claim_token` 部分唯一索引；引用完整性全靠 doctor 事后修。
- **F7 MySQL 回填用 `||` 拼字符串，实测丢历史**：`db.py:587` 的 `'jh:' || w.id` 在 MariaDB 12.3.3 上实测求值为数字 0（逻辑或）；两条已判工单的回填只留下 1 行 judge_history（id='0'），其余被 INSERT IGNORE 吞掉。同一 SQL 在 PG 16.15 上正常（两条 `jh:<work_item_id>`）。`wxg_mysql` 未设 `PIPES_AS_CONCAT`。
- **F8 MySQL DDL 实际是 MariaDB 方言**：`CREATE INDEX IF NOT EXISTS`（MySQL 8 不支持）与 `LONGTEXT ... DEFAULT`（MariaDB 10.2+ 语义）；MariaDB 12.3.3 与 PG 16.15 上三份 DDL 均实跑成功（各建出 12 张表），MySQL 8 无凭据、未验证。
- **F9 后端测试在 CI 永远不跑**：两个后端测试类各 3 例，`skipUnless(env)` 在 setUpClass 前生效；`ci.yml:30` 无 service container。本地其实有 MariaDB 12.3.3 与 PG 16.15，F2/F7 都是本地真库复现的，但 CI 永远看不到。
- **F10 迁移夹具不代表旧库**：`test_wxg.py:636-643` 只建 work_items，`test_wxg.py:962-984` 只建 4 张表，两次都缺 bites/nodes/changes，F1 测不到。
- **F11 死代码与空操作**：`_NoopCursor`（`db.py:292-302`）、两处 PRAGMA 分支（334-342、371-379）、`PRAGMA foreign_keys=ON`（461）、`wxg_mysql.is_integrity_error`（153）、只写不读的 `work_items.assignee`。
- **F12 唯一有损的写是 meta**：其余回填只填 NULL；但 meta 被无条件覆盖，`judge_history` 回填还会在历史行被删后“复活”出推导值。
- **F13 版本号只写不读**：`SCHEMA_VERSION` 不参与任何迁移分支，v9 只是标签，不是迁移状态机。

## 契约表

状态：covered = 有测试直接断言；partial = 有测试但漏分支/路径；gap = 代码里有、无人断言。

### 建库与幂等

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C1 | 空目录 `init` 建出 `graph.sqlite`（12 表齐全），`schema_version=9`，退出 0 | `db.py:605-616`、`commands_repo.py:44-59`、`test_wxg.py:86,652`、`test_plan_cli.py:341` | covered |
| C2 | `init` 输出键为 `root/db/backend/schema_version/contract_version/migrated` | `commands_repo.py:52-59`、`cli.py:75-77`、`test_mysql_backend.py:88`、`test_pg_backend.py:90` | partial（只有 `schema_version` 直断言；`backend` 只在永远跳过的后端测试里） |
| C3 | 新库首次 `init` 返回 `migrated={"meta":2}`，第二次 `{}` | `db.py:593-601`、`test_wxg.py:693` | gap（只断言了空 dict） |
| C4 | 已迁移库重复 `init` 零写入：`migrated=={}` 且全表快照不变 | `test_wxg.py:683-696` | covered |
| C23 | `init_db` 返回前自行 commit：`init` 报错时库可能已经建好 | `db.py:613-615`、`cli.py:75-77` | gap（无断言；C22 的成因） |

### 迁移

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C5 | 任一旧 schema 都能被 `init` 非破坏地收敛到 9 | `db.py:613-614`、`db.py:126`、`db.py:551-553`、`SKILL.md:144` | **gap — 实测违背**：缺 `generation` 的旧 bites 会让建索引先失败（F1） |
| C6 | 旧 `work_items` 补 4 列；未知身份标 legacy，audit 豁免 | `db.py:516-527,563-583`、`test_wxg.py:632-679` | partial（只测了 passed 一条；其余三种状态与 audit 豁免无断言） |
| C7 | `claimed_at` 只对 `claimed` 行按 created_at 回填 | `db.py:581-583`、`SKILL.md:237` | gap |
| C8 | `evidence.generation` 先取关联工单代、再取 feature 当前代 | `db.py:528-538`、`test_wxg.py:957-1002` | covered |
| C9 | 旧 `bites` 补 `generation/phase`，generation 按 feature 当前代回填 | `db.py:551-562`、`test_wxg.py:671` | partial（只断言列存在） |
| C10 | `judge_history` 用 `jh:<work_item_id>` 幂等回填，只对非 audit、有 judged_by、无历史行的工单 | `db.py:585-592`、`contract.md:329`、`test_wxg.py:673` | partial（只测 passed；failed 推导与 NOT EXISTS 分支无断言） |
| C24 | 回填是猜测值、不标记来源 | `db.py:531-538,554-559`、`CHANGELOG.md:1504-1506` | partial（文档承认，表里没有标记列） |

### 版本与体检

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C11 | 每次 `init` 刷新 meta 两键；`doctor` 报 `meta-version`；`--fix` 写回 | `db.py:593-601`、`commands_misc.py:536-540,590-600`、`test_wxg.py:402-425` | covered（schema_version 的修复未单独断言） |
| C12 | 没有降级保护：更高版本号被静默改写 | `db.py:593-601` | gap（实测 99 → 9 后 doctor ok） |
| C13 | `ensure_db` 只以 meta 表存在为判据；不存在 → Reject + 2 | `db.py:468-483`、`cli.py:79-80`、`test_wxg.py:947-955` | gap（947 测的是文件不存在；无 meta 缺表的夹具） |
| C13b | meta 存在但表/列缺失时放行，命令以 OperationalError 退出 2 | `db.py:468-483`、`cli.py:85-90` | gap（实测 `no such table: nodes`） |
| C21 | 表间无外键/CHECK，完整性靠 doctor 事后检查与 `--fix` | `db.py:19-150`、`commands_misc.py:360-400,562-589`、`design.md:72`、`test_wxg.py:391-429` | partial（doctor 有测试；“schema 不声明约束”本身无人断言） |

### 连接与事务

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C14 | sqlite `connect`：建 root、timeout=5s、WAL、busy_timeout=5000、foreign_keys=ON | `db.py:458-465`、`test_wxg.py:1391-1402` | partial（只断言 WAL；其余无断言，且 `foreign_keys=ON` 是空操作） |
| C15 | 连接期失败是 traceback + 1，不是可读 JSON | `cli.py:70`、`db.py:458-464` | gap（实测坏库文件、root 是文件两种） |
| C16 | 一条命令一个事务，失败不留半截 | `cli.py:74-93`、`db.py:353-360`、`commands_repo.py:73,87,107`、`commands_gates.py:142` | gap（没有“失败后 DB 不变”的断言；up/serve/init 各自 commit） |
| C17 | `--db-url` 覆盖 `WXG_DB_URL`；未知协议 JSON + 2 | `cli.py:55-61`、`db.py:429-438` | gap（全仓测试对 `db_backend`/`db_url` 零引用） |

### 后端与完整性错误

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C18 | `_is_integrity_error` 识别 SQLite / MySQL 4 个 errno / PG sqlstate 23* | `db.py:500-505`、`wxg_mysql.py:116-157` | gap（零测试；与 wxg_mysql 的 10 个 errno 不一致） |
| C19 | `repo-add` 同 path 不同 id → Reject「仓登记冲突」 | `commands_repo.py:136-146`、`CHANGELOG.md:1499` | gap（实测 NameError，见 F3） |
| C20 | 三份 DDL 的表与列逐表一致 | `db.py:19-150,154-285,288-289` | gap（静态比对当前一致；MariaDB 12.3.3 与 PG 16.15 实跑建表成功，MySQL 8 未验证；无测试守护） |
| C22 | mysql/postgres 的 `init` 输出 backend 与脱敏 db 标签 | `commands_repo.py:46-51`、`test_mysql_backend.py:86-89` | **gap — 实测违背**：`db_url`/`re` 未导入 → NameError，且库已 commit（F2；MariaDB 与 PG 真库均复现） |

## 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `<root>/graph.sqlite` | both | `db.py:459`、`db.py:613` |
| `<root>/` 目录 | write | `db.py:458` |
| `graph.sqlite-wal` / `-shm` | write（瞬态） | `db.py:464` |
| `meta` | both | `db.py:596-600`、`commands_misc.py:590-599` / `db.py:594`、`commands_misc.py:538` |
| `repos` | both | `commands_repo.py:137-141` / `graph.py:57` |
| `nodes` | both | `graph.py:120-129`、`commands_repo.py:214,323,485` / `query.py:87` |
| `edges` | both | `graph.py:169-186,208-212` / `gates.py:139` |
| `features` | both | `commands_feature.py:102-121,175-218,359` / `workflow.py:26` |
| `conditions` | both | `workflow.py:65`、`commands_feature.py:123-126,181,221` / `workflow.py:39,72` |
| `work_items` | both | `work.py:29-43,54,57`、`commands_feature.py:528-532,652-690` / `commands_feature.py:515-520` |
| `feature_nodes` | both | `graph.py:132`、`commands_graph.py:31,122` / `workflow.py:104` |
| `evidence` | both | `commands_graph.py:169-176` / `evidence.py:22` |
| `bites` | both | `commands_graph.py:124-127` / `gates.py:23,64` |
| `judge_history` | both | `commands_feature.py:603-617`、`db.py:585-592` / `commands_feature.py:276` |
| `changes` | both | `commands_feature.py:376-379` / `commands_feature.py:303` |
| `WXG_DB_URL` | both | 读 `db.py:426`；写 `cli.py:56`、`engine.py:48`（均不恢复） |

跨命令共享的隐式状态：

- `WXG_DB_URL` 是进程级全局；`--db-url` 和 `Engine(db_url=...)` 都往里写且不还原，同一进程不能并存两个后端的状态库。
- `.why-exist/` 不是配置文件，只是 `--root` 的默认值；没有任何文件记录“这个项目用哪个库”。
- 状态库路径完全靠命令行；库自身不记录 backend（切后端不会报错，只会读到空表或报未初始化）。
- sqlite 的 WAL 让读写不互斥，但单写者依旧；`busy_timeout=5000` 是唯一的排队手段。

## 冗余

| 条目 | 信号 | 把握 |
|---|---|---|
| 三份手工维护的 DDL | 同一 12 表在 `db.py:19-150`、`154-285`、`288-289` 各写一遍；PG 版是字符串 replace；无测试比对列集 | high |
| 运行时 SQL 字符串翻译 | `db.py:305-320,400-422`；新增 SQL 用错方言就静默坏；只有 8 个纯字符串单测 | high |
| `_MySQLConnection` 与 `_PgConnection` 逐行复制 | `db.py:323-360` vs `363-397`，五个方法同构 | high |
| 两份完整性错误判定，集合不一致 | `db.py:500-505`（4 个 errno）vs `wxg_mysql.py:120-157`（10 个）；后者无人调用 | high |
| `_NoopCursor` 与 PRAGMA 分支不可达 | `db.py:292-302,334-342,371-379`；只有 sqlite 路径会发 PRAGMA | high |
| `PRAGMA foreign_keys = ON` 空操作 | `db.py:461`；`PRAGMA foreign_key_list` 全空 | high |
| `work_items.assignee` 只写不读 | 写入 `commands_feature.py:529`、5 处置 NULL；全仓无读取点；语义与 `claimed_by` 重叠 | high |
| meta 版本写入两份 + `fixed.meta` 写死 | `db.py:596-600`、`commands_misc.py:590-599`；`commands_misc.py:600` 恒报 1 | high |
| 建索引早于补列 | `db.py:613` 跑完整 DDL（含 `db.py:126` 的索引）→ `db.py:614` 才 ALTER | high |
| 级联删除两套手写 | `commands_graph.py:86-92`（retract）与 `commands_misc.py:562-570`（doctor --fix）；schema 无 CASCADE | medium |
| `evidence` 迁移的无效守卫 | `db.py:528` 的 `_table_columns(...) != set()` 在唯一调用路径上恒真 | high |
| `db_url` 两套读取路径 | `cli.py:55-56`、`engine.py:47-48` 写环境变量，`db.py:426` 是唯一读取点 | medium |

## 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `db.py` SCHEMA_SQL（L19-150） | refactor_in_place | 表/列形状是既成公共契约：外部 why-exist-uml 按列名直读 5 张表（`.dsh/skills/why-exist-uml/SKILL.md:78`），`contract.md:309-337` 记录了 evidence/judge_history 的列语义，40 多个契约版本里 schema 只升到 9、一直只加列。可以原地补索引、补文档；不能改名/删列 | SQLite 加外键/CHECK 需重建表搬数据；任何列改名同时打断外部只读消费者与旧库迁移 |
| `db.py` MYSQL_SCHEMA_SQL / PG_SCHEMA_SQL（L154-289） | refactor_in_place | 表与列同样是硬契约，只能原地演进；坏的是三份手抄 DDL 只能人肉同步（PG 版还是字符串 replace）。方言适配层（L292-422）不在本片，归 05 片（其判定：翻译层 rewrite、wrapper refactor_in_place）。本地 MariaDB 12.3.3 与 PG 16.15 实跑建表成功 | 改列名会同时打断 SQLite 迁移与两个后端的新建库；`CREATE INDEX IF NOT EXISTS` 与 LONGTEXT 默认值在 MySQL 8 上会拒建（未验证），动手前先定支持面 |
| `db.py` migrate_schema 结构部分（补列/建表/顺序，L516-562、L613-614） | rewrite | 只加列的语义清楚，但顺序错：`init_db` 先跑完整 DDL（含引用新列的索引）再补列，0.4.x 旧库会上不去；也没有版本门控，靠列存在性推断。改成有序步骤 + 兼容检查，成本低 | 这是所有旧库唯一的升级入口；必须保留“重复 init 零写入”的收敛性与已迁移库零改写 |
| `db.py` migrate_schema 数据回填部分（L528-538、L551-583、L585-592） | freeze | 回填是猜测且不可复现：legacy 身份、generation 取 feature 当前代、claimed_at 取 created_at、judge_history 由最终 status 推导。没有测试能验证这些值对不对，表里也没有来源标记；在决定“旧数据可不可追溯”之前不许改 | 动它会静默改变历史解释（更早代咬合算到当前代、failed 历史被推成 passed）；冻结的代价是这些不确定性只活在 CHANGELOG 与注释里 |
| `db.py` connect / ensure_db / init_db（L441-465、468-483、605-616） | refactor_in_place | 契约简单且大部分有测试（缺库不建、WAL、init 幂等）；坏的是边界：ensure_db 只看 meta 表、连接异常在兜底外、init_db 自带 commit。局部改即可 | ensure_db 变严后旧库会从“静默 OperationalError”变成“直接拒绝”，需同时给手动迁移路径；挪 connect 会改变退出码语义 |
| `db.py` `_is_integrity_error`（L500-505） | rewrite | 6 行判定，概念清楚；与第二份实现集合不一致、唯一调用点还缺 import。合并成一份 + 每后端两条单测即可 | 采用更宽的 errno 集合后，repo-add 可能把非唯一键错误也翻成“仓登记冲突” |
| `commands_repo.py` cmd_init（L44-59） | refactor_in_place | 输出形状简单、有测试；坏点只有两处未导入的全局名（`db_url`、`re`） | 修好后 mysql/pg init 才算首次可用，会暴露迁移里未验证的 SQL（尤其 F7） |
| `cli.py` 连接时机与 commit 边界（L62-93） | refactor_in_place | 与 01 片对 cli.py 的判定一致；本片只关心 connect 在 try 外、commit 一次，两处都是局部改动 | 把 connect 挪进 try 会改变现存 traceback+1 行为，依赖退出码区分“环境错/业务拒绝”的下游要一起改 |

## 隐含需求（重写会静默丢掉的行为）

1. `init_db` 返回前自己 commit（`db.py:615`）——“命令失败但库已初始化”是现状语义，F2 就是它的直接产物。
2. `migrate_schema` 自己不 commit（`db.py:602`），只被 `init_db` 调用；直接把它当公共 API 用会留未提交事务。
3. `judge_history` 回填不是一次性：每次 `init` 都跑，靠 NOT EXISTS 去重；被删的历史行会复活成 `jh:<work_item_id>`。
4. `migrated` 的键名与计数是 `init` 输出的一部分（`work_items.<col>`、`evidence.generation`、`claimed_by.legacy` 值为行数、首跑 `meta:2`）。
5. `claimed_by='legacy'` 只覆盖 claimed/submitted/passed/failed 四态，audit 永不参与（`db.py:564-570`）。
6. `judged_at` 用 created_at 兜底（`db.py:576-578`），旧库的裁决时间不是真实裁决时间。
7. `bites.generation` 按 feature 当前代回填，更早代咬合会被算到当前代（`db.py:554-558`）。
8. `evidence.generation` 两级回退、都不命中留 NULL；doctor 把 NULL 报成 `evidence-missing-generation`。
9. 迁移不补 conditions：旧 feature 不会自动得到 8 行条件，doctor 报 `missing-generation-conditions`。
10. sqlite 连接开 WAL + busy_timeout=5000 + timeout=5s，仍是单写者。
11. MySQL 会话被改成 READ COMMITTED（`db.py:328-330`），SQLite/PG 没有对应设置。
12. meta 版本无上界检查：比代码新的库会被改写成当前版本。
13. 枚举列（`bites.verdict`、`work_items.status`）没有 CHECK；doctor 只校 `judge_history.verdict`（`commands_misc.py:456`），不校 bites。
14. `--db-url` 与 `Engine` 都通过改 `os.environ` 生效且不恢复。
15. `doctor --fix` 的 `fixed.meta` 恒为 1，不是真实改动计数。
16. meta 表是“已初始化”的唯一凭据，但不校验它是不是这个工具的表。

## 实测记录

| 操作 | 观察 |
|---|---|
| 空目录 `init` | exit 0；`migrated={"meta":2}`；建出 143360 字节的 graph.sqlite，无 `-wal`（关闭时合并） |
| 再跑一次 `init` | exit 0；`migrated={}` |
| 干净库 `doctor` | exit 0；`ok=true`，五个计数全 0 |
| 缺库 `doctor`（目录不存在） | exit 2；stderr JSON 错误「状态库未初始化：先运行 wxg init」，不建目录 |
| 空 SQLite 文件（无表）`doctor` | exit 2；同上错误（ensure_db 拦下） |
| 只有 meta+work_items 的旧库 `doctor` | exit 2；`{"error":"OperationalError: no such table: nodes"}` |
| 非数据库内容的 graph.sqlite `doctor` | exit 1；**traceback**（`connect` 在 cli 的 try 之外） |
| `--root` 指向一个文件 `init` | exit 1；**traceback**（`root.mkdir` 抛 FileExistsError） |
| 含旧 bites（无 generation）的库 `init` | exit 2；`{"error":"OperationalError: no such column: generation"}`，重试同样失败 |
| `schema_version=99` 后 `init` | exit 0；`migrated={"meta":1}`，meta 变 9，随后 `doctor` ok |
| `repo-add` 同 path 不同 id | exit 2；`{"error":"NameError: name '_is_integrity_error' is not defined"}` |
| 用桩连接跑 `cmd_init`（backend=mysql） | `NameError: name 'db_url' is not defined`（在 `init_db` 已 commit 之后） |
| `python -m unittest tests.test_mysql_backend tests.test_pg_backend -v` | 6 例全部 skipped（无 `WXG_TEST_*_URL`） |
| MariaDB 12.3.3（127.0.0.1:3307）`--db-url ... init` | exit 2；`{"error":"NameError: name 'db_url' is not defined"}`；**12 张表与 meta(schema_version=9, contract_version=2.92.0) 已提交** |
| PostgreSQL 16.15（5433）`--db-url ... init` | exit 2；同样的 NameError；12 张表与 meta 已提交 |
| MariaDB 上跑迁移回填 SQL（2 条已判工单） | judge_history 只有 1 行，`id='0'`；SQL 竖线拼接（\|\|）求值返回 0 |
| PG 上跑同一条回填 SQL（2 条已判工单） | 2 行，id 为 `jh:work:f:g1:scan` / `jh:work:f:g1:observe` |
| 13 个迁移/诊断/方言单测 | 全绿 |

## 值得人判断的问题

1. 要不要给 schema 补外键/CHECK？SQLite 只能重建表，12 表里 9 张带跨表引用列，还有外部只读消费者。是继续“无约束 + doctor”，还是做一次带版本号的数据迁移手术？
2. 旧库（0.4.x 及更早）还要不要救？要救就修 F1 并补真实旧 schema 的迁移夹具；不救则 `init` 应给可读错误与重建指引，而不是 OperationalError。
3. `schema_version` 的权威方向：只允许升级吗？遇到“库版本 > 代码版本”是拒绝、警告，还是像现在静默改写？这决定回滚策略。
4. MySQL/PostgreSQL 是产品承诺还是实验？本地容器可跑（MariaDB 12.3.3 / PG 16.15）、CI 永不跑；DDL 是 MariaDB 方言、回填 SQL 有 `||` 拼接（MariaDB 上实测丢历史）。要么上 service container 解冻，要么从 SKILL.md/契约里撤掉这两个后端。
5. `migrated` 字典算不算公开契约？算就补一条测试把每个键钉住；不算的话，现在的输出形状只是偶然实现。
6. 回填的猜测值要不要在表里留来源（如 `generation_source`）？现在只能靠 CHANGELOG 记住哪些行不可信。
7. 既然没有 DB 约束，doctor 是否该补齐枚举校验（`bites.verdict`、`work_items.status`）？现在它只校 `judge_history.verdict`。
8. `work_items.assignee` 要不要删？它存的就是 role、无人读取；SQLite 3.35+ 可直接 DROP COLUMN，外部消费者不读它，风险低。
