# 05 多后端适配（MySQL / PostgreSQL）审计

## 切片范围

| 文件 | 行数 | 本切片关注的区间 |
|---|---|---|
| `scripts/whyexist/db.py` | 618 | L154-289 两套非 SQLite schema；L292-422 方言翻译与连接包装；L425-438 `db_url`/`db_backend`；L441-616 连接、迁移、建库（后端选择脱离这段无法判定，故纳入） |
| `scripts/wxg_mysql.py` | 904 | 整个文件（纯标准库 MySQL/MariaDB 线路协议客户端） |
| `scripts/whyexist/commands_repo.py` | 737 | L44-59 `cmd_init`（后端标签与掩码 URL）；L204-207、L308-311 `executemany` 调用点 |
| `scripts/whyexist/cli.py` | 115 | L20-27 `--db-url` 定义；L55-70 后端早失败与连接时序；L74-113 退出码 |
| `scripts/whyexist/engine.py` | 151 | L36-51 把 `db_url` 写进进程环境 |
| `tests/test_mysql_backend.py` | 140 | 全部（默认 skip） |
| `tests/test_pg_backend.py` | 143 | 全部（默认 skip） |
| `tests/test_wxg_mysql.py` | 485 | 全部（默认连 127.0.0.1:3307，连不上整类 skip） |
| `tests/test_package_units.py` | 753 | L118-235 方言翻译纯函数用例 |

未纳入：`whyexist/commands_*` 里除 `cmd_init` 外的 SQL 写法（属各自切片），以及 `serve` 循环本身。

本次审计在真实实例上做了验证（不是只读代码）：

- MariaDB 12.3.3（127.0.0.1:3307，项目自带容器 `wxg-mysql`）
- PostgreSQL 16.15（127.0.0.1:5433，容器 `wxg-pg`）
- 本机 `mysql:8.0` 容器（`sysj-mysql`, 3306）无凭据，未使用；因此「MySQL 8 是否可用」只能静态判断。

## 一句话结论

MySQL/PostgreSQL 后端**今天不可用**：`init` 必崩、写入路径必崩，且两者都在「已改了一部分状态」之后才报错。底层的 `wxg_mysql.py` 客户端质量不错、测试能真跑；坏的是它上面的方言适配层与后端接线。这不是一个能用的兼容层，是一个**接线没接完、测试全部跳过、文档却写成已支持**的半成品。

## 公开面

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg --db-url <url> <cmd>` | CLI | `cli.py:23-27,55-56` | mysql/mariadb/postgresql/postgres URL，**必须在子命令之前** | 无直接输出 | 写 `os.environ['WXG_DB_URL']`（进程级全局，子进程继承） | 0；2 = 非法协议（JSON）或参数位置错（argparse 英文） |
| `wxg init` | CLI | `commands_repo.py:44-59` | `--root`、`--db-url`/`WXG_DB_URL` | `{root, db, backend, schema_version, contract_version, migrated}` | 建 12 表 + 写 meta；sqlite 建 `graph.sqlite`；**非 sqlite 时表已建好再崩** | 0（sqlite）；2（mysql/pg，NameError） |
| `WXG_DB_URL` | 环境变量 | `db.py:425-426` | 任意字符串，strip 后生效 | 决定后端 | 只读；但被 `cli.py:56`、`engine.py:48` 写入 | — |
| `db_backend()` | 函数 | `db.py:429-438` | 读环境变量 | `sqlite`/`mysql`/`postgres` | 无 | 非法 scheme 抛 `Reject` → 2 |
| `connect(root)` | 函数 | `db.py:441-465` | `root: Path`（仅 sqlite 用） | `sqlite3.Connection` / `_MySQLConnection` / `_PgConnection` | sqlite：mkdir、建库文件、`PRAGMA foreign_keys/busy_timeout/journal_mode=WAL`；mysql：TCP + `SET NAMES utf8mb4` + `autocommit=0` + `READ COMMITTED`；pg：`psycopg.connect(connect_timeout=5, dict_row)`；**非 sqlite 不建 `--root` 目录** | 连接错误在 try 之外 → traceback + 1 |
| `ensure_db(conn)` | 函数 | `db.py:468-483` | 任意连接 | `None` | 只读 information_schema / sqlite_master | 缺 meta → `Reject` → 2 |
| `_table_columns(conn, table)` | 函数 | `db.py:486-497` | 表名 | 列名 `set[str]` | 只读 | — |
| `_is_integrity_error(exc)` | 函数 | `db.py:500-505` | 异常 | `bool` | 无；`graph.py:9` 导入，`commands_repo.py:143` 用来把仓冲突转可读错误 | — |
| `migrate_schema(conn)` | 函数 | `db.py:509-602` | 已建表连接 | `migrated` 计数字典 | `ALTER TABLE` 补列、legacy 回填、`judge_history` 回填、写 meta | — |
| `init_db(conn)` | 函数 | `db.py:605-616` | 任意连接 | 同 `migrate_schema` | 按 dialect 选 schema 建表 + 迁移 + commit | — |
| `_mysql_translate` / `_pg_translate` / `_named_params` / `_NoopCursor` | 函数 | `db.py:292-422` | SQLite 方言 SQL | 目标方言 SQL | 无（纯函数） | `_named_params` 缺参抛 `Reject` |
| `_MySQLConnection` / `_PgConnection` | 类 | `db.py:323-397` | 底层连接 | sqlite3 子集：`execute/executescript/commit/rollback/close` + `dialect` | mysql 构造时设隔离级别；`execute` 透明改 SQL 与占位符 | — |
| `wxg_mysql.connect` 等 5 个导出 | 函数/类 | `wxg_mysql.py:37-43,136-157,160-202,575-611,614-904` | `mysql://user:pass@host:port/db`（凭据可百分号编码） | 连接；`execute` 返回已读完成的游标（`list[dict]`） | TCP（连接/读写超时 5s）、`SET NAMES`、`autocommit=0`；`close` 发 COM_QUIT 并 shutdown | — |
| 12 张表 | 表 | `db.py:19-150,154-285,289` | — | — | `init_db` 创建；mysql 版 VARCHAR 有长度上限且去部分索引；pg 版由 `.replace` 派生 | — |
| `Engine(root, db_url=...)` | 函数 | `engine.py:36-51` | root + 可选 URL | 编程入口 | `db_url` 非空时写 `os.environ` | — |
| `wxg.py` 的 db re-export | 函数 | `wxg.py:31-49` | — | 16 个符号 | 无 | — |
| `wxg contract`.backend_rules | 函数/JSON | `wxg_contract.py:219-224,1021` | — | 4 条后端契约文本 | 被 `contract --write` 生成进 SKILL.md / contract.md，`verify` 校验漂移 | — |

## 契约表

状态口径：`covered` = 有测试直接断言；`partial` = 有测试但只覆盖部分路径/分支，或只有文档断言；`gap` = 代码里有行为，但没有任何测试或文档断言（实测结果另注）。

| ID | 可观察行为承诺 | 证据 | 状态 | 说明 |
|---|---|---|---|---|
| C1 | `--db-url` 是全局参数，优先于 `WXG_DB_URL`，必须写在子命令之前 | `cli.py:23-27,55-56`；`SKILL.md:60-63` | partial | 只有文档示例，无测试。实测写在子命令后 → argparse `unrecognized arguments`、退出 2 |
| C2 | scheme 只接受 mysql/mariadb/postgresql/postgres，其余 `Reject` + JSON + 退出 2 | `db.py:433-438`；`cli.py:57-61` | gap | 实测 `sqlite:///x`、`oracle://x` 均退出 2 且可读；无测试、BACKEND_RULES 未写 |
| C3 | 不设 URL 时后端 sqlite，状态在 `--root/graph.sqlite`，WAL + busy_timeout=5000 | `db.py:429-432,458-465`；`tests/test_wxg.py:1399` | covered | journal_mode 有直接断言，其余由全量 sqlite 测试间接覆盖 |
| C4 | sqlite 状态库文件缺失时，非 init 命令报「状态库未初始化」退出 2，不留 0 字节库 | `cli.py:66-69` | gap | 有守卫无测试 |
| C5 | mysql/pg 库存在但未建表时报「状态库未初始化」退出 2 | `db.py:468-483` | gap | MariaDB 空库实测符合；无测试 |
| C6 | `wxg init` on mysql 返回 `backend="mysql"`、`schema_version=9` 并建表 | `tests/test_mysql_backend.py:86-89`；`commands_repo.py:44-59` | gap | 测试默认 skip；启用即失败（NameError）。表与 meta 已提交＝半成功 |
| C7 | `wxg init` on postgres 同上，`backend="postgres"` | `tests/test_pg_backend.py:88-91` | gap | PG 16.15 实测同样 NameError 退 2，表已建好 |
| C8 | `init` 幂等：已迁移库再跑 `migrated` 为 `{}` | `tests/test_wxg.py:683-696`；`db.py:509-602` | covered | 仅 sqlite；mysql/pg 无等价测试 |
| C9 | 迁移补列并回填 legacy 身份 / `judge_history` | `tests/test_wxg.py:635-679`；`db.py:516-592` | covered | 断言完整（列集合、legacy、doctor `legacy-identity`）；仅 sqlite |
| C10 | mysql/pg 上迁移行为与 sqlite 一致 | `db.py:586-592` | gap | 无测试；且 `'jh:' \|\| w.id` 在 MySQL 上是逻辑或（实测 `'jh:' \|\| 42 = 1`），回填 id 退化成 0/1 并被 `INSERT IGNORE` 合并 |
| C11 | mysql/pg 上 `import-file`/`import-repo` 写入与 sqlite 一致 | `commands_repo.py:204-207,308-311`；`tests/test_mysql_backend.py:93-102` | gap | 两个包装都没 `executemany`；实测 MySQL 与 PG 均 `AttributeError` 退出 2，事务回滚 |
| C12 | 并发 `work-claim` 只有一个成功（0/2） | `tests/test_mysql_backend.py:109-126`；`commands_feature.py:527-532` | partial | 测试默认 skip 且被 init 崩挡住；MariaDB 实测两进程 `[0,2]` 成立 |
| C13 | 后端连接失败报可读错误而不是 traceback | `wxg_contract.py:221`；`references/contract.md:170`；`CHANGELOG.md:1297-1298` | gap | 四类失败（1045、端口不通、PG 无服务、无 psycopg）实测全部裸 traceback + 退出 1。`cli.py:70` 在 try 之外 |
| C14 | 除标准库外无第三方依赖；只支持 `mysql_native_password`（含 AuthSwitch） | `tests/test_wxg_mysql.py:462-481`；`wxg_mysql.py:733-738` | covered | 12 个客户端用例在真实 MariaDB 全过 |
| C15 | `?` 只在字符串/注释外替换；数量不匹配抛错 | `tests/test_wxg_mysql.py:364-396` | covered | 双写引号、引号内 `?`、注释内 `?`、参数多/少 |
| C16 | 列值转 int/float、NULL→None、其余 utf-8；可按列名取值 | `tests/test_wxg_mysql.py:103-123`；`wxg_mysql.py:374-388` | covered | 客户端级；经包装层的端到端无测试 |
| C17 | 事务 commit/rollback 生效；UPDATE rowcount = modified rows | `tests/test_wxg_mysql.py:193-221,258-294` | covered | 与 sqlite matched-rows 不同，会改变 `migrated` 计数（`db.py:571`） |
| C18 | 方言翻译五种形态（INSERT IGNORE / ON DUPLICATE KEY / VALUES(x) / ON CONFLICT DO NOTHING / `?`→`%s`） | `tests/test_package_units.py:181-222`；`db.py:305-320,400-408` | covered | **只有字符串级断言**，没有一条证明译出来的 SQL 能在真实后端跑 |
| C19 | `_named_params` 顺序替换 / 重复收集 / 缺参抛 `Reject` | `tests/test_package_units.py:140-149,225-235` | covered | 生产代码无任何 dict 参数调用点，只有测试消费者 |
| C20 | 连接对象提供 sqlite3 所需子集（含 `executemany`） | `db.py:323-397`；`commands_repo.py:204,308` | gap | 实测子集只有 5 个方法：缺 `executemany`（产品用了 2 处）、`cursor()`、`row_factory`、`in_transaction`；无断言子集的测试 |
| C21 | 后端不影响 `--root` 决定的导出目录；不要混用后端 | `wxg_contract.py:223` | partial | 文档写明且 `verify` 防漂移；无测试 |
| C22 | mysql/pg 下 `--root` 目录不会被创建 | `db.py:458` | gap | 实测 doctor 跑完后 root 仍不存在；无测试无文档 |
| C23 | `init` 不建数据库本身，要求库已存在 | `references/design.md:276`；`CHANGELOG.md:1307` | partial | 文档写明；库不存在时表现为连接 traceback（见 C13），不是可读提示 |
| C24 | `contract` JSON 含 `backend_rules`，且与生成文档块一致 | `wxg_contract.py:884,1021`；`tests/test_wxg.py:490-525` | partial | 文档漂移有测试；contract JSON 只断言 version/schema_version/commands |

覆盖率：24 条里 covered 10、partial 6、gap 8。**所有覆盖三后端差异的端到端契约（C6、C7、C10、C11、C12）全部落在 gap/partial**，这是本切片的核心事实。

## 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `graph.sqlite`（及 `-wal`/`-shm`） | write | `db.py:458-465` |
| `env:WXG_DB_URL` | read | `db.py:425-426` |
| `env:WXG_DB_URL` | write | `cli.py:56`、`engine.py:48` |
| `meta`（schema_version / contract_version） | both | `db.py:593-601` |
| `work_items`（补列 + legacy 回填） | both | `db.py:516-527,563-583` |
| `evidence.generation` | both | `db.py:528-538` |
| `features`（coverage_epsilon / drift_limit / conformance） | both | `db.py:539-547` |
| `nodes.stale` | both | `db.py:548-550` |
| `bites`（generation / phase） | both | `db.py:551-562` |
| `judge_history`（回填） | write | `db.py:585-592` |
| MySQL `information_schema` | read | `db.py:471-474,490-494` |
| PG `information_schema` | read | `db.py:476-479,490-494` |
| 12 张表建表 | write | `db.py:605-616` |
| `--root` 目录 | write（仅 sqlite） | `db.py:458` |

隐式全局状态有三处，全部与后端选择有关：

1. `WXG_DB_URL` 是**唯一的配置通道**（除了同名的全局参数，那个参数也是先写进环境变量）。同一进程里 `engine.Engine(root, db_url="mysql://…")` 会污染后续所有 `connect()`。
2. `cli.py:56` 的写环境变量让「命令参数」变成了「进程状态」，子进程继承。
3. sqlite 才有「库文件 = 状态」的直觉；mysql/pg 下 `--root` 仍是导出目录，但不落任何库文件——同一个 `--root` 在不同后端下语义不同。

## 冗余

1. **三份 schema**：`SCHEMA_SQL`（`db.py:19-150`）、手抄的 `MYSQL_SCHEMA_SQL`（`154-285`）、由字符串 `.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY")` 派生的 `PG_SCHEMA_SQL`（`289`）。加列要改 2-3 处，没有任何测试断言三者表/列集合一致。
2. **两套 integrity 分类器**：`db.py:500-505` 认 4 个 errno + sqlstate `23`；`wxg_mysql.py:120-157` 认 10 个 errno。产品只用前者。
3. **两套脚本切分器**：包装层用裸 `split(";")`（`db.py:347-351,384-388`），`wxg_mysql.py:532-556` 有引号/注释感知的 `_split_script`，产品路径不用它。
4. **`_named_params` 无生产调用点**：全仓没有任何 dict 形式的 `conn.execute(..., {...})`。
5. **PRAGMA 分支与 `_NoopCursor` 不可达**：`db.py:334-342,371-379` 只在调用方直接发 PRAGMA 时命中，产品走 `_table_columns`。
6. **`wxg.py:31-49` 的 16 个 re-export**：只有 `connect`/`init_db` 有消费者（`scripts/gen_sample.py:43-45`）。
7. **会话初始化分两层**：`wxg_mysql.py:642-643` 做 `SET NAMES`/`autocommit`，`db.py:330` 再做隔离级别。
8. **dialect 三分支散落三处**：`ensure_db`、`_table_columns`、`init_db` 各自 if/elif，没有统一后端抽象。新增后端要改 5+ 处，且连接包装要重新实现一遍 sqlite3 子集。
9. **死导入**：`commands_repo.py:16` 导入 `ensure_db`、`migrate_schema`，模块内无引用。
10. **`PRAGMA foreign_keys = ON`**（`db.py:461`）在无任何外键的 schema 上是空操作。
11. **重复解析 URL**：`cli.py:58` 与 `db.py:442` 各调一次 `db_backend()`。
12. **文档把失败写成已完成**：`references/quality.md:49-50` 的验收项与现状相反；`CHANGELOG.md:1324-1325` 把默认跳过的集成测试计入测试总数。

## 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `db.py:292-422` 方言翻译 + `_NoopCursor` + `_named_params` | **rewrite** | 契约清楚（16 条单测钉住行为），但实现是引号无关的字符串替换：字面量里的 `?` 会被改成 `%s`、`%` 会被当占位符、`:name` 在字符串里也会被替换。新增后端等于再抄一遍正则，且没有任何机制保证译出的 SQL 可执行 | 重写必须逐条过那 16 条断言；先把产品实际用到的 6 种 SQL 形态枚举成模板，别顺手改掉 rowcount/占位符语义 |
| `db.py:154-289` 两套非 SQLite schema | **refactor_in_place** | 表与列是硬契约（迁移、doctor、导出都依赖），不能整块重写；但三份手抄只能人肉同步 | `MYSQL_SCHEMA_SQL` 用了 MariaDB 扩展，MySQL 8 上大概率建表失败；改结构前先定「支持 MariaDB 还是也支持 MySQL 8」 |
| `db.py:323-397` 两个连接包装 | **refactor_in_place** | 薄适配层思路正确、契约简单；缺 `executemany` 直接打断产品写入，且没有断言子集的测试 | 补齐时容易顺手加产品不用的 API（`cursor()`/`row_factory`），扩大维护面；子集边界要写进注释并配测试 |
| `db.py:441-616` connect / ensure_db / _table_columns / migrate / init_db | **refactor_in_place** | 迁移语义（非破坏、只迁一次、legacy 回填）是最值钱的契约，sqlite 上有完整测试；问题在方言分支散落、迁移 SQL 混了 MySQL 不兼容的 `\|\|` | rowcount 语义按后端不同，会改变 `migrated` 数值；任何「顺手统一」都可能改掉测试断言的返回形状 |
| `commands_repo.py:44-59` `cmd_init` | **rewrite** | 16 行、行为清楚，现在 100% 崩（`db_url`/`re` 都没导入）。把掩码规则抽成函数并加测试，比原地打补丁干净 | mysql/pg 的 `db` 字段（掩码 URL）从没被执行过、无断言；重写前先定这个字段的格式 |
| `cli.py:55-70` 后端选择与连接时序 | **refactor_in_place** | 逻辑很短，但 `connect` 落在 try 之外，让四类连接失败全变 traceback；`--db-url` 写环境变量也在这里定 | 移进 try 会改变失败输出形态（traceback+1 → JSON+2），下游若有脚本依赖退出码 1 会受影响 |
| `engine.py:36-51` `db_url` 注入环境 | **rewrite** | 行为简单、边界清楚：只是想把 URL 传下去。改成显式参数，消除构造 Engine 污染全局的问题 | `connect(root)` 签名变化波及 `cli` 与 `cmd_up`，需同批更新调用点 |
| `wxg_mysql.py`（904 行） | **keep** | 全切片唯一「契约清楚 + 测试真实」的部分：12 个用例在真实 MariaDB 全过，协议子集与禁区写在文件头（`wxg_mysql.py:19-27`），零第三方依赖是有意取舍 | 它是自制数据库驱动：无 TLS、无 caching_sha2、无多结果集、无重连、超时固定 5s；MySQL 8 默认认证插件下不可用。要 keep 就必须把「仅 MariaDB/native 认证」写进对外文档并停止扩功能 |
| `tests/test_mysql_backend.py` + `tests/test_pg_backend.py` | **refactor_in_place** | 它们写的正是该有的端到端契约（init→repo→feature→prepare→claim→write→judge→gate→doctor、并发 claim、serve --once），但不进 CI ⇒ 永远绿 | 两个 `setUpClass` 都是破坏性的（清空目标库所有表 / `DROP SCHEMA public`），接 CI 必须用一次性容器 |
| `tests/test_wxg_mysql.py` | **keep** | 覆盖到位且能真跑：类型、转义、rowcount、事务、并发写、大文本、百分号凭据、AuthSwitch、close 幂等 | 只在有 MariaDB 时运行；多包（>16MB）与 LOAD DATA 中止路径无用例 |
| `wxg.py:31-49` re-export | **refactor_in_place** | 兼容垫片，16 个符号里只 2 个有消费者，其余 grep 零命中 | 可能有仓外脚本按 `wxg._mysql_translate` 这类私有名访问；删前先搜 dist 与文档 |

整体判定：**适配层 rewrite，客户端 keep，schema 与迁移 refactor_in_place，测试 refactor_in_place**。没有需要「冻结」的模块——行为不是不明，而是明确地坏着。

## 关键实测（可复现）

1. **init 必崩**
   `WXG_DB_URL=mysql://root:wxgpass@127.0.0.1:3307/<db> python scripts/wxg.py --root <dir> init`
   → `{"error": "NameError: name 'db_url' is not defined"}`，退出 2；随后库里 12 张表 + meta 全在（PG 16.15 同样）。
2. **写入路径必崩**
   先 `init_db` 直连建表，再 `repo-add` → `feature-declare` → `import-file --prepare` → `work-claim` → `import-file --token <t>`
   → `{"error": "AttributeError: '_MySQLConnection' object has no attribute 'executemany'"}`，退出 2；PG 报 `_PgConnection` 同款。
3. **并发 claim 反而正常**（说明不是连接语义的问题）
   同一工单两个 `work-claim` 并发 → 退出码 `[0, 2]`。
4. **连接失败是 traceback**
   错密码 → `wxg_mysql.MySQLDatabaseError: MySQL error 1045` 裸栈、退出 1；`127.0.0.1:1` → 裸栈；PG 无服务 → `Reject: PostgreSQL 连接失败` 裸栈；把 `psycopg` 用影子模块模拟缺失 → `Reject: PostgreSQL 后端需要 psycopg` 裸栈。四种都是退出 1、无 JSON。
5. **翻译层在字面量上就露馅**（PG 实测）
   `SELECT '?' AS q` → `the query has 1 placeholders but 0 parameters were passed`；
   `SELECT '100%' AS pct` → `only '%s', '%b', '%t' are allowed as placeholders`。
6. **MySQL 的 `||`**
   MariaDB 上 `SELECT 'jh:' || 42` = `1`（逻辑或），迁移回填（`db.py:587`）据此拼 id。
7. **空 schema 的路径反而是对的**
   已有库无表时 `doctor` → 退出 2 + `{"error": "状态库未初始化：先运行 wxg init"}`，且不创建 `--root`。
8. **方法子集**
   `hasattr` 实测两个包装都只有 `execute/executescript/commit/rollback/close`，对比 `sqlite3.Connection` 缺 `executemany/cursor/row_factory/in_transaction/...`。

## 值得人判断的问题

1. **MySQL/PG 后端到底算不算对外承诺？** `SKILL.md:427`、`references/contract.md:169-171`、`references/quality.md:49-50` 都说能用；代码说不能。要么补齐并接进 CI，要么把这条产品线从文档、技能描述、CHANGELOG 里删掉。现在两者都不成立，这是比任何单个 bug 都更贵的负债。
2. **要不要为 MySQL 8 引入可选第三方驱动？** 如果坚持零依赖，就得接受「仅 MariaDB + native 认证」，并把这句话写进 `BACKEND_RULES`（现在是：文档写 MariaDB/MySQL，实现只对 MariaDB 成立）。
3. **schema 的权威定义放哪？** 三份手抄是 bug 温床。能否只维护 SQLite 一份 + 一张列元数据，由代码生成 MySQL/PG DDL？
4. **`init` 半成功要保留吗？** 现在「报错退出 2，但表已建好」。是先做所有可失败检查再建表，还是把建表做成显式可重试的幂等步骤？
5. **迁移里的 `'jh:' ||` 说明什么？** 说明 MySQL 后端从来没有过需要迁移的旧库。那这条迁移分支在 MySQL 上要不要直接删掉，而不是留着一条错的分支？
6. **VARCHAR 长度上限是否隐性契约？** `id` 512 / `path` 700 / `claim_token` 191 在 MySQL 上是硬限制，超长在 `INSERT IGNORE` 下会被静默截断。要不要在写入前显式 `Reject`？
7. **方言翻译改成模板 + 参数绑定，还是继续在字符串上打补丁？** 改动量不小，但这是唯一能保证新 SQL 不被静默改坏的办法；继续打补丁的话，每加一条 SQL 都是一次未经测试的赌注。
8. **是否支持显式 sqlite 选择（`sqlite:///path`）？** 现在设了 `WXG_DB_URL` 就没有单命令退回 SQLite 的办法。
