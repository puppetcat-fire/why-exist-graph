# why-exist-graph 实现梳理报告

> 方法：不逐行读实现，先提取「对外可观察的行为承诺」，再拿证据对账，最后按模块给"改还是重写"的判定。
> 原始证据：`docs/audit/01..16-*.json|md`（16 份契约卡）；机器汇总：`SUMMARY.md`、`DECISIONS.md`；探针脚本：`probes/`。
> 日期：2026-11-06。基线版本 2.92.0 / schema 9。

## 1. 规模与结果

| 项 | 数量 |
|---|---|
| 切片（审计单元） | 16 |
| 覆盖模块 | 77 |
| 公开入口（CLI 命令 / 函数 / 表 / 产物） | 300 |
| 提取到的行为契约 | 592 |
| 其中 covered（有测试直接断言） | 206（34%） |
| partial（只覆盖部分分支） | 189（31%） |
| gap（代码里有、零断言） | 197（33%） |
| 模块分区判定 | 152 |

分区结论：

| 判定 | 数量 | 含义 |
|---|---|---|
| keep | 49 | 契约清楚、测试够，原样保留 |
| refactor_in_place | 65 | 契约清楚但实现烂，原地改 |
| rewrite | 22 | 行为简单、边界清楚，值得重写（多数是 10–60 行的函数/文件） |
| freeze | 16 | 行为不明、无测试，先定契约再动 |

## 2. 结论：不该重写系统，该修三个断层

三条独立证据都指向同一结论。

**（1）项目最值钱的部分已经被判定为"别动"。**
49 个 keep 覆盖了全部纯函数层：`graph_algo`（30 测试）、`derive`（15）、`briefing`（15）、`blind`（12）、`impact`（15）、`cycles` 的环检测、`conflicts`（12）、`evidence`、`planner`（13），以及 `tests/` 下 12 个模块级测试文件。变异测试 5 个变异体杀掉 4 个——安全网是真的。重写会把这些全部推倒重建，换不来任何可验证的收益。

**（2）"重写"的真实成本是 197 条 gap 契约，不是代码量。**
592 条契约里 33% 没有任何断言。这些行为只活在代码里：`attrs` 覆盖 vs 合并的双语义、`stale`/`unmapped` 复位、`recompute_ready` 返回 `0` 或 `True`、`scope_ids` 顺序随 `PYTHONHASHSEED` 变、`retract` 的级联裁剪。重写等于把这些全部丢弃，而且丢的时候没有任何测试会红。

**（3）最烂的地方恰恰是边界最清楚的地方。**
`cmd_init` 16 行、`cmd_serve` 39 行、`cmd_retract` 49 行、`feature-list` 10 行、`work-list` 5 行——这些被判定 rewrite，但"重写"指的是重写一个函数，不是重写系统。真正需要结构性重做的只有一个文件：`scripts/wxg.py`（入口 + 50 个 handler 动态注册表 + 74 个零消费导出混在一起）。

## 3. 真正的病灶

### 3.1 同一实体多份副本，且已经漂移

这是本仓库最系统性的一类问题，共 40+ 处，按危害排序：

| 实体 | 副本数 | 漂移后果 |
|---|---|---|
| 版本号 | 9 处（VERSION / CONTRACT_VERSION / `__version__` / README / HANDOFF / quality / PRODUCT-PLAN / dist manifest / 测试断言），仅 4 处一致 | 模型侧技能停在 1.4.0（38 命令），代码是 2.92.0（50 命令），frontmatter 描述字节相同，无法从描述察觉 |
| 测试用例数 | 4 个值（79 / 104 / 357 / 381） | README、HANDOFF、quality.md 各说各的 |
| 「前缀 `*` 通配」匹配规则 | 9 份实现（`work.target_match`、`work.require_targets`、`blind._matches`、`conflicts`、`scope_ids`…） | `target_match` 有 `isinstance` 保护，`require_targets` 没有；非字符串 id 抛 `AttributeError` |
| 后端 DDL | 3 份手抄（SQLite / MySQL / PG），PG 版由 SQLite 版字符串 `replace` 派生 | 只能人肉同步，MySQL 8 的 `CREATE INDEX IF NOT EXISTS`、`LONGTEXT` 默认值大概率建表失败 |
| 可达性算法 | 2 份（`graph_algo.reachable` 死代码 + `impact.py` 自己写 DFS） | 无 |
| AST 解析 | 2 份（`importer.plan_python` + `commands_repo._import_file_pairs`） | 两套错误策略：严格 UTF-8 vs `errors="replace"` |
| `_is_integrity_error` | 2 份，errno 集合不一致 | 唯一调用点还缺 import |
| `DEFAULT_ROOT` | 3 份 | 无 |
| 规则表 / 不变量 / 导出规则 | 10 张表 58 条 + 21 条 INVARIANTS + EXPORT_RULE，**零代码读取、零测试引用** | 删一行不会有任何检查失败；这是"声明了但没人执行"的契约 |
| 死常量 | `TOKEN_COMMANDS`（列 6 条，实际 9 条）、`COMMON_ATTRS`、`P()`/`positionals`（0 调用） | 与事实不符且无消费者 |

`verify` 只能检查"文档生成块 == 重新生成的内容"，查不出上面任何一种副本漂移。

### 3.2 验证只覆盖成功路径

- 592 条契约里 covered 34%；`doctor` 的 32 类检查有 24 类无测试，`--fix` 6 组有 3 组无测试（其中一组会删数据）。
- 变异测试唯一漏检的变异体是"错误 JSON 从 stderr 改到 stdout"——**错误流契约零断言**。
- `cli.py:70` 的 `connect()` 在 `try` 之外：MySQL/PG 错密码、端口不通、未装 psycopg 四种情况全部裸 traceback + 退出 1，直接违反契约里"错误给可读 JSON、退出 2"。
- 后端集成测试默认 skip 且 CI 无数据库服务，`test_mysql_backend.py` / `test_pg_backend.py` 从未真正跑过。直接后果：`cmd_init` 里 `db_url`/`re` 未导入，MySQL/PG 上 `wxg init` 100% `NameError`，但 12 张表已经建好并 commit——**库是真的建了，退出码说谎**。

### 3.3 版本与发布链断裂

- `git ls-remote` 只有 v0.4.0 / v0.4.1；本地 HEAD 是 b8c6d7b；2.92.0、113 条 CHANGELOG、11 个 `dist/` 目录全部未提交。
- 16 个测试文件里 15 个未进 git，`scripts/whyexist/` 整包未跟踪。**CI 拿到的 381 条测试实际只有 42 条 v0.4.1 旧用例**——"CI 全绿"不能作为任何决策依据。
- `dist/` 被 `.gitignore` 忽略，那 11 个发布包只存在于这台机器。
- `README.md:72/180` 让用户去 GitHub Releases 下载，那里只有 0.4.1。

## 4. 按"能不能动"重排的行动清单

**进度（2026-11-06）**

| 项 | 状态 | 证据 |
|---|---|---|
| P0.1 工作树入 git | 完成 | `29e8680`（130 文件，此前只跟踪 25 个） |
| P0.2 版本号收单一真源 | 完成 | 删 `whyexist.__version__`；文档去写死；`check_docs` 加第四项检查 |
| P0.3 文档数字清理 | 完成 | README / HANDOFF / PRODUCT-PLAN / quality / CONTRIBUTING / SKILL |
| P0.4 技能目录同步 + 描述补全 | 完成 | `~/.dsh/skills/why-exist-graph` 1.4.0 → 2.93.0，50 命令可见 |
| P0.5 tag / push | 完成 | `v2.93.0`（annotated，指向 `9c9be79`）与 `main` 已推 origin |
| P1.6 `connect()` 进错误兜底 | 完成 | 改前 traceback+1，改后 JSON+2；新增 2 条错误流测试 |
| P0.额外 契约块 CRLF 污染 | 完成 | `contract --write` / `export` 固定 LF，文档恢复 LF |
| 发布闭环 | 完成 | `preflight --release` 八步全过；`dist/v2.93.0`（63 文件，SHA `4c8d6a17…`，manifest 带 commit 与 dirty 标记）；`tools/install_skill.py` 装到 `~/.dsh/skills/why-exist-graph` 并通过 verify |
| P1.7 MySQL/PG 三条断链 | 完成 | 2.94.0：`cmd_init` 补 `db_url`/`re`、两个连接包装补 `executemany`、PG 占位符改引号感知、`repo-add` 补 `_is_integrity_error`；单测 87→96，全量 392 |
| 2.94.0 发布闭环 | 完成 | `dist/v2.94.0`（63 文件，SHA `c667cc8d…`，commit `2f08eb6`）+ 技能已装 2.94.0 + tag |
| P1.8 旧库升级 + ensure_db | 完成 | 2.95.0：建表→补列→建索引（旧顺序实测 `no such column: generation`）；ensure_db 校验 12 表 + 5 张表的迁移列，区分「未初始化」与「schema 落后」 |
| 2.95.0 发布闭环 | 完成 | `dist/v2.95.0`（63 文件，SHA `7f66aaf7…`，commit `3a06989`）+ 技能已装 2.95.0 + tag |
| P1.9 MariaDB 拼接 + 错误流测试 | 完成 | 2.96.0：`_concat_prefix` 按方言选 `CONCAT`/`\|\|`（旧写法在 MariaDB 上历史全撞 id `0`）；新增 `ErrorStreamContractTest` 6 条，变异验证 5/6 抓到（修复前 0 条） |
| 2.96.0 发布闭环 | 完成 | `dist/v2.96.0`（63 文件，SHA `c96607e3…`，commit `119700d`）+ 技能已装 2.96.0 + tag |
| P2.1 后端测试接进 CI | 完成 | 2.97.0：CI `backend` job（MariaDB 11 + PG 16 service 容器）、`tools/test_backend.py`、preflight 加「后端集成（可选）」；本机真库 3+3 全过 |
| 2.97.0 发布闭环 | 完成（有修正） | 本地产物 `c1fe9d69…` 是 CRLF 脏版本，**Release 附件 `a1ccec26…` 才是正确产物**；commit `97f95f8` + tag |
| P2.2 打包可复现性（行尾） | 完成 | 2.98.0：`core.autocrlf=false` + 26 文件恢复 LF；`build_release` 打包前统一 LF；`preflight` 加「工作树行尾」检查；本地与 CI 产物 SHA 一致 |
| 2.98.0 发布闭环 | 完成 | `dist/v2.98.0`（63 文件，SHA `1fb79a27…`，commit `0603a9f`）+ 技能已装 2.98.0 + tag；Release 附件与本地逐字节一致 |
| P2.3 retract 计数与越界可见化 | 完成 | 2.99.0：`nodes_deleted` 只计真删；新增 `edges_deleted_out_of_scope`、`work_refs_pruned_other_features`、`bite.added_to_feature_scope`；测试 +3，变异验证 3/3 |
| 2.99.0 发布闭环 | 完成 | `dist/v2.99.0`（63 文件，SHA `b0b14d82…`，commit `73c5be7`）+ 技能已装 2.99.0 + tag |
| P2.4 覆盖公式与契约对齐 | 完成（breaking） | 3.0.0：`_required_coverage` 分母补 `a₀`，与契约 `p_m=(1+d)/(10+m)` 一致；S=1/ε=0.1 从「p=0.1 却 met=false」变为 met=true；变异验证通过（`0 != 1`） |
| 3.0.0 发布闭环 | 完成 | `dist/v3.0.0`（63 文件，SHA `8cf65126…`，commit `3d769d5`）+ 技能已装 3.0.0 + tag |
| Release asset 上传 | 自动（此前判断有误） | `release.yml` 在 tag push 时构建并上传 zip；实测 v2.96.0 附件 SHA `889e2af3…` 与干净 checkout 构建逐字节一致 |

发布版本：`2.92.0` → `2.93.0`（schema 仍为 9），提交 `9c9be79`。

### P0：先让事实存在（全部可并行，纯机械）

1. `git add -A && git commit`：把 `scripts/whyexist/`、`tests/`、`docs/`、`references/` 全部纳入版本控制。没有这一步，后面任何改动都不可回滚。
2. 版本号收成单一来源：`VERSION` 为准，其余全部改成运行时读取或生成物；把 `tools/check_docs.py` 接进 CI。
3. 测试数、代码行数、能力清单从 README/HANDOFF/quality.md 里删掉，改成指向 `verify` / `preflight` 输出。
4. 模型侧技能目录 `~/.dsh/skills/why-exist-graph/` 重新同步到 2.92.0（现在缺 12 条命令）。
5. `git tag v2.92.0` + 推送 + 建 Release。发布链要么修好，要么删掉 `publish_github.py` 只留 CI 一条路。

### P1：把"声明"变成"可执行"（收益最高）

6. 修 `cli.py:70`：`connect()` 移进 `try`，四种后端连接失败统一成 JSON + 退出 2。
7. 修 `cmd_init`（`db_url`/`re` 未导入）与两个连接包装的 `executemany`——MySQL/PG 现在写入路径 100% `AttributeError`。
8. 方言翻译层 `db.py:292-422` 重写：现在是引号无关的正则替换，字面量里的 `?` 会被改成 `%s`，`%` 会被当占位符。
9. `WRITE_MODES` 改成 `read/write/both` 枚举，让 `verify` 能机械校验"只读命令真的只读"。
10. 删掉零消费的契约数据：`TOKEN_COMMANDS`、`COMMON_ATTRS`、`EXPORT_RULE`、`P()`、`commands_repo` / `commands_misc` 的 re-export 层。
11. 把「前缀 `*` 通配」的 9 份实现收敛成 1 个 helper，并补非字符串 id 的行为测试。

### P2：补测试（在动实现之前）

12. 错误流契约矩阵：每条命令的退出码 + stdout/stderr 分流 + 错误 JSON 形状。
13. `retract` 级联边界、`bite` 的 `--feature` 扩作用域、`apply` 的写库语义——这三处一旦"顺手修"就会静默改门禁结果。
14. `scope_ids` 的顺序确定性（现在随 `PYTHONHASHSEED` 变，而全项目承诺确定性）。
15. `doctor --fix` 的三组零测试修复——这是全仓唯一删数据的路径。

### P3：结构问题（慢，且必须在前三档之后）

16. `scripts/wxg.py` 重写：拆成「入口 + 显式 handler 注册表 + 8 个真实被用的 helper」。注意 `verify` 和分派共用 `getattr(wxg, 'cmd_*')`，这里是单点故障。
17. `migrate_schema` 结构部分重写：`init_db` 先跑完整 DDL（含引用新列的索引）再补列，0.4.x 旧库升级永久卡死（`no such column: generation`）。
18. 三份 DDL 收敛成一个 schema 模型生成三种方言，或至少加一条"三后端表/列集合一致"的测试。

### 冻结（先定契约，不许动）

`migrate_schema` 的数据回填（全是猜测，不可复现）、`temp.py`（Windows 受限 token 规避，CI 验证不了）、`_node_id` 生成规则（外部主键，改则全库重建）、`work-judge` 状态转移表、`feature-status` 字段集、`work_items` 状态词表、`slice_payload` 输出形状、`derive --apply` 写路径、`doctor --fix`、`INVARIANTS` 文本、`references/design.md`、`publish_github.py`、`dist/`。

## 5. 和产品定位的关系

这份审计有一个绕不开的讽刺：why-exist 的核心承诺是"防止实现偷偷偏离声明"，而它自己的 592 条契约里 2/3 没有断言，10 张规则表零消费，`verify` 查不出任何一种副本漂移。

所以对它来说，"重新整理需求再重新设计"这条路的产物不是新系统，而是：**把 592 条契约里 197 条 gap 变成可执行断言，把 40+ 处副本收敛成单一定义，把该冻的冻住**。做完这些，它才第一次有能力审计自己。

换句话说，它现在是这个产品的第一个用户，而且还没真正用起来。这比再多加 20 个命令重要。
