# Changelog — why-exist-graph

## 3.2.2（2026-11-06）

**`doctor` 不可修检查补测**。审计 12 片：32 类检查里 24 类无测试。3.2.1 覆盖了
可修的 7 类，本版补 5 类核心的不可修检查。

- **`applies-invalid`**：`applies` 边的语义是「谁应用了哪个设计模式」，dst 不是
  pattern 时必须报。
- **`pattern-unjustified`**：pattern 节点缺 `applicability` 或 `not_applicable`
  时必须报——否则等于没做选型。
- **`evidence-artifact-changed`**：证据登记的产物被改过，登记就失效，必须报。
- **`evidence-work-missing`**：evidence 关联的工单不存在时必须报。
- **`legacy-identity`**：迁移留下的 legacy 身份只能报给人看，且必须出现在
  `unfixable_checks` 里——自动改成某个 actor 等于伪造审计身份。
- **变异验证**：前三条各回退检查逻辑一次，用例都变红。
- **测试数**：411 → 416（无行为变化）。
- **版本**：契约 `3.2.1` → `3.2.2`；schema 仍为 `9`。

## 3.2.1（2026-11-06）

**`doctor --fix` 的删数据路径补齐测试**。审计 12 片：`--fix` 是全仓唯一会删数据
的地方，7 类可修问题里只有 dangling-bite 有测试，其余 6 类没有。

- **一条端到端用例覆盖全部 7 类**：dangling-bite / orphan-edge /
  feature-node-missing / work-target-missing / work-evidence-missing /
  token-on-inactive / meta-version。构造坏库 → `doctor --fix` → 断言每类修复计数
  为 1、正常节点一个不少、被删的行确实没了、工单引用被裁空、token 被清。
- **变异验证**：审计点名的三组（orphan-edge / feature-node-missing / work-refs）
  各回退一次，用例都变红。
- **测试数**：410 → 411（无行为变化）。
- **版本**：契约 `3.2.0` → `3.2.1`；schema 仍为 `9`。

## 3.2.0（2026-11-06）

**`scope_ids` 的顺序确定性**。审计 14 片：全项目都承诺「同样输入两次运行字节一致」，
唯一例外是这条路径。

- **通配展开改成排序输出**：`scope_ids` 的第三段——从工单 `target_ids` 的 `*` 模式
  展开节点——遍历的是 `set`，顺序随 `PYTHONHASHSEED` 变。审计探针用 4 个种子拿到
  4 种顺序；而这个列表会被 `work-seed` 原样写进 `target_ids`、被 `feature-status`
  取前几条展示，等于把不确定性写进了状态库。
- **修法**：返回前 `sorted(ids)`。前两段（`feature_nodes`、requirement 前缀）本来就是
  DB 顺序，排序后整体变成字典序——这是可见的顺序变化，所以按 minor 发而不是 patch。
- **测试**：新增跨进程用例——建两个 feature，节点由 a 导入、b 的通配 target 把它们
  「新」拉进作用域（只有一个 feature 时新节点会被 `feature_nodes` 的 DB 顺序盖住，
  测不出问题）。用 `PYTHONHASHSEED` 0/1/2/3 四个子进程比对输出。
  变异验证：改回未排序后该用例报「4 种顺序」。
- **测试数**：409 → 410。
- **版本**：契约 `3.1.0` → `3.2.0`；schema 仍为 `9`。

## 3.1.0（2026-11-06）

**拆包兼容残留清理 + 未定义名前置检查**。审计 01/08 两片共同的结论：拆包时留下
大量没人用的 re-export，而「漏 import」这类 bug 只在特定分支才炸。

- **`scripts/wxg.py` 181 → 86 行**：原来 re-export 134 个名字。AST 统计（排除本文件）
  显示 `cmd_*` 之外 84 个里只有 8 个真被用——`wxg.C`（gen_sample）、`make_temp_dir` /
  `temp_dir` / `connect` / `init_db` / `Reject` / `bind_node` / `upsert_node` /
  `upsert_edge`（fixture 与测试）。其余 76 个整片删除。保留 `cmd_*` 是因为 CLI 分派
  与 `verify` 都用 `getattr(wxg, "cmd_" + name)` 动态取，它们必须在这里可见。
- **`commands_repo.py` 738 → 660 行**：末尾 78 行是五个整片 re-export 块
  （feature / graph / gates / compiler / misc），仓内零消费者；`wxg.py` 早已直接
  从各 `commands_*` 导入。删完立刻发现 `cmd_up` 里还在用 `cmd_feature_declare`——
  import 期不报错、跑到 `up` 才 NameError，正好是新工具的检测范围。
- **新增 `tools/check_undefined.py`**：用标准库 `symtable` 找出「按全局解析、但模块里
  没有定义」的名字，接进 `preflight` 成为独立一步。这类 bug `py_compile` 查不出来
  （名字查找发生在运行期），2.94 修的 `cmd_init` 缺 `db_url`/`re`、`repo-add` 缺
  `_is_integrity_error` 都是这个形态。实测：删掉 `db_url` 导入后工具报
  `cmd_init.db_url` 并以 1 退出；对当前 34 个源文件跑是干净的。
- **测试**：409 不变（清理无行为变化，`up` 的回归由既有端到端用例覆盖）。
- **版本**：契约 `3.0.0` → `3.1.0`；schema 仍为 `9`。

## 3.0.0（2026-11-06）

**覆盖公式与契约对齐（行为变更 / breaking）**。审计 10 片查出的「分母不一致」：契约
COVERAGE_RULES 写 `p_m=(1+d)/(10+m)`，代码算的是 `(1+d)/(9+m)`。

- **`_required_coverage` 分母补上 a₀**：旧实现只用 `b₀+m` 作分母，漏掉 Beta 先验的
  a₀（prior=0.1 时为 1）。后果是 `n_required` 比契约大或小一档，最刺眼的是：
  S=1、ε=0.1、d=0 时同一份 `coverage` 报告同时输出 `p=0.1` 与 `met=false`——
  p 已经贴着 ε 了却说没达标。现在分母是 `a₀+b₀+m`，与后验 `p` 的算法、与契约的
  `p_m=(1+d)/(10+m)` 三处一致。
- **这是 breaking change**：修正后 `n_required` 会变（大多变小一档），
  原本因覆盖不足而 `met=false` 的阶段可能变 true，`gate` 结果可能从 FAIL 变 PASS。
  已有的 evidence / bite / 工单数据不受影响，只是覆盖约束的判定口径变了。
  旧文档里 S=1186 的两个数字（ε=1.0 需 589、ε=0.01 需 1174）按修正后公式是
  588 与 1175；`references/design.md` 保留当时的实测记录不动，以 CHANGELOG 为准。
- **测试**：`CoverageMathTest` 的参数改为传先验总强度 `a₀+b₀`；新增一条
  `coverage_report` 级别测试（测接线，不只是纯函数）。变异验证：把调用处改回 `b₀`
  后该测试变红（`assertEqual(0, 1)`），修复前抓不到。
- **测试数**：407 → 409。
- **版本**：契约 `2.99.0` → `3.0.0`；schema 仍为 `9`。

## 2.99.0（2026-11-06）

**`retract` 的计数与越界删除可见化**。审计 11 片列的三条：本版修前两条，第三条
不动工作流、只把副作用报出来。

- **`nodes_deleted` 不再说谎**：旧实现对每个传入 id 无条件 +1，即使节点根本不存在。
  典型场景：重扫后代码里的节点已消失，工单仍按前缀拿到写入权，这时 retract 一个
  不存在的 id 会让报告显示「删了 1 个节点」。
- **越界删边单独计数**：删节点必须连带删它作为端点的边（否则留悬空边），但另一端
  不在本次 `target_ids` 内的边属于越界删除。旧实现把两类混成一个 `edges_deleted`。
  新增 `edges_deleted_out_of_scope` 字段。
- **跨 feature 工单裁剪可见**：`prune_work_refs` 会清掉所有工单里指向已删节点的
  `target_ids` / `evidence_ids`，包括其他 feature 的工单——这是必然的，但旧实现
  只在总数里体现。新增 `work_refs_pruned_other_features` 字段。
- **`bite` 的作用域副作用可见**：`bite --feature` 会把这个节点塞进 `feature_nodes`，
  而那是 plan / coverage / conformance 的输入集合。旧实现静默做这件事。新增
  `added_to_feature_scope`（本次才加进去为 true，已存在为 false）。
  **没有**给它加 token / target 边界——那会改掉「任何人都能咬」的现行工作流，
  属于产品决策而不是实现修复。
- **测试**：新增 3 条，全量 404 → 407；三条都做了变异验证（回退修复后各自变红）。
- **版本**：契约 `2.98.0` → `2.99.0`；schema 仍为 `9`。

## 2.98.0（2026-11-06）

**打包可复现性：行尾**。审计说「重复构建得到相同 SHA」，但那只在同一台机器的同一份
工作树上成立；换台机器就不成立。

- **根因**：`.gitattributes` 声明 `* text=auto eol=lf`，但 Windows 侧的
  `core.autocrlf=true` 会让 checkout 出来的工作树变成 CRLF、索引仍是 LF。
  `build_release` 直接读工作树字节，于是本地包比 CI 包大 353 字节、SHA 不同。
  实测对照：本地 v2.96.0 `c96607e3…`（334992 字节），CI 的 Release 附件
  `889e2af3…`（334639 字节）；用干净 tag checkout 重新构建得到 `889e2af3…`，
  与 CI 附件**逐字节一致**——确定性机制本身没问题，是工作树被弄脏了。
- **`build_release` 自行规范化**：写入 zip 前把文本文件的 CRLF 统一成 LF，
  打包结果不再依赖打包机器的 git 配置。实测：故意把 `db.py` 改成 CRLF 再
  `--allow-dirty` 构建，SHA 与 LF 基线完全相同。
- **`preflight` 新增「工作树行尾」一步**：`git ls-files --eol` 里出现 `w/crlf`
  就失败，并给出 `core.autocrlf false` + 重建索引的修复命令。
- **CONTRIBUTING 补一条环境要求**：Windows 上必须 `git config core.autocrlf false`。
- **测试**：404 不变（本版只修打包通路）。
- **版本**：契约 `2.97.0` → `2.98.0`；schema 仍为 `9`。

## 2.97.0（2026-11-06）

**后端集成测试接进 CI 与本地流程**。2.94–2.96 修的 MySQL/PG 问题，此前只能靠审计时
手工连库验证——CI 里两个后端集成测试永远 skip，后端坏了 CI 照样绿。

- **CI 新增 `backend` job**（ubuntu-latest）：MariaDB 11 + PostgreSQL 16 各起一个
  service 容器，跑 `tests.test_mysql_backend` 与 `tests.test_pg_backend`。
  GitHub Actions 的 `services` 只在 Linux 可用，所以独立成 job，不污染三系统矩阵。
- **新增 `tools/test_backend.py`**：本地一条命令跑两个后端集成测试，按环境变量决定跑哪个；
  URL 里的密码自动掩码；`--strict` 要求至少跑一个（给 CI / preflight 用）。
- **`preflight` 新增一步**「后端集成（可选）」：配了 `WXG_TEST_*_URL` 就跑，没配就跳过，
  不阻断发布。
- **实测**：本机 MariaDB 12.3.3 与 PG 16.15 上各 3 条全过——2.94 的 `cmd_init`
  NameError、`executemany` 缺失、2.96 的 `CONCAT` 拼接都在真库上验证过。
- **测试**：404 不变（本版只接通路，不加用例）。
- **版本**：契约 `2.96.0` → `2.97.0`；schema 仍为 `9`。

## 2.96.0（2026-11-06）

**MariaDB 静默丢历史 + 错误流契约上锁**。一条数据正确性修复，加一组从零到有的断言。

- **`judge_history` 回填在 MariaDB 上丢历史**：迁移用 `'jh:' || w.id` 生成 id，而
  MariaDB 的 `||` 是逻辑或（除非开 `PIPES_AS_CONCAT`），求值为 `0`——所有回填行撞
  同一个 id `'0'`，`INSERT OR IGNORE` 下静默只剩第一条。改按方言选拼接：
  MySQL/MariaDB 用 `CONCAT('jh:', w.id)`，PG/SQLite 保持 `||`；抽成 `_concat_prefix`
  便于单测。
- **错误流契约测试（新增 `ErrorStreamContractTest`）**：6 条场景——未初始化库、
  未知 feature、未知 work、import 文件缺失、不支持的 db 协议、以及 gate FAIL
  （属于「判定」不属于「错误」）。每条都断言：退出码 2、stdout 必须为空、
  stderr 是 JSON 且不含 Traceback。此前这类断言为零：测试夹具先解析 stdout、
  失败才退回 stderr，所以把错误 JSON 从 stderr 挪到 stdout 不会有任何用例变红。
  变异验证：把 `file=sys.stderr` 改成 `file=sys.stdout` 之后，6 条里 5 条变红
  （第 6 条走 gate 判定路径，本来就从 stdout 出），修复前是 0 条。
- **迁移 id 格式**：`jh:<work_item_id>` 的回填格式被端到端测试钉住（契约里已写明
  运行期是 `jh:<uuid>`，两种格式并存是有意的）。
- **测试**：新增 7 条（1 条拼接单元 + 6 条错误流），全量 397 → 404 条。
- **版本**：契约 `2.95.0` → `2.96.0`；schema 仍为 `9`。

## 2.95.0（2026-11-06）

**旧库升级与状态库体检**。审计 04 片的两条：0.4.x 的库永远升不上来、`ensure_db` 名不副实。

- **旧库升级顺序修正**：`init_db` 原来是「完整 DDL（表 + 索引）→ 补列」，而
  `idx_bites_feature` 建在 `bites.generation` 上、`idx_work_feature` 建在
  `work_items.generation` 上——这两列都是迁移才补的。所以 0.4.x 的库一 `init` 就报
  `no such column: generation`，重试同样失败，永久卡死。改成「建表 → 补列 → 建索引」，
  三份 schema 各自拆成 TABLES / INDEXES 两段。
  反例实测：同一个旧库，旧顺序 `OperationalError: no such column: generation`，
  新顺序升级成功、列补上、索引建好、原有行一条不少。
- **`ensure_db` 收紧**：以前只查 `meta` 表在不在，缺表或缺列的库会等到后面某条 SQL
  才炸成 `OperationalError`——用户看到的是 `no such column: claimed_by`，看不出该跑
  init 还是该修库。现在检查 12 张必需表与 5 张表的迁移列，并把两种错误分开：
  缺表 → 「未初始化，跑 `wxg init`」；缺列 → 「schema 落后，跑 `wxg init` 就地迁移，
  不要重建库」。
- **测试**：新增 5 条——旧 bites 表升级（端到端，含索引与数据保留）、`ensure_db` 四类
  场景（空库 / 完整库 / 缺列 / 缺表）。全量 392 → 397 条。
- **版本**：契约 `2.94.0` → `2.95.0`；schema 仍为 `9`。

## 2.94.0（2026-11-06）

**MySQL / PostgreSQL 后端修到能用**。审计 04、05 两片实测出来的三条断链——「init 必崩、
写路径必崩、连接失败裸 traceback」——本版补齐前两条，第三条 2.93.0 已修。

- **`cmd_init` 不再 NameError**：`commands_repo.py` 缺 `db_url` 与 `re` 两个名字，
  非 SQLite 后端走「掩码连接串」那条分支 100% 抛 NameError；而 `init_db` 已经提交过，
  结果是 12 张表全建好、退出码却是 2。补 import，并加两条单测（掩码不泄漏凭据、
  sqlite 分支报库文件路径）。
- **补齐 `executemany`**：`_MySQLConnection` / `_PgConnection` 只实现了
  `execute` / `executescript` / `commit` / `rollback` / `close`，而 `import-file` /
  `import-repo` 批量写 `feature_nodes` 时调 `conn.executemany`——MySQL 与 PG 上
  100% `AttributeError`。两个包装各补一份逐条 `execute` 的实现（要的是能用，不是吞吐；
  翻译、PRAGMA 处理、命名参数都复用 execute 的统一路径，避免第二份实现分叉）。
- **PG 占位符转换改成引号感知**：原来是 `sql.replace("?", "%s")`，两个后果都实测过——
  字符串字面量里的 `?` 也被换掉（`'status?'` → `'status%s'`），`'100%'` 被 psycopg
  当成占位符报数量不符。新实现扫描引号状态：`?` 只在引号外替换；`%` 在有参数时统一
  转义成 `%%`（含引号内——psycopg 的占位符解析不看 SQL 引号）；无参数时传 `None`，
  不做插值。
- **`repo-add` 的冲突路径**：`_is_integrity_error` 只被 `graph.py` 导入，
  `commands_repo.py` 用它时是 NameError——path 冲突会变成未定义名异常而不是
  「仓登记冲突」的可读错误。补 import。
- **测试**：新增 9 条——引号内 `?` 保留、引号内 `%` 转义、无参数不转义、
  双引号标识符不误伤、两个 `executemany`、空序列、`cmd_init` 两个分支。
  `tests/test_package_units.py` 87 → 96 条。
- **版本**：契约 `2.93.0` → `2.94.0`；schema 仍为 `9`。

## 2.93.0（2026-11-06）

**契约审计与真源收口**。16 路并行审计（`docs/audit/`：592 条行为契约、152 个模块分区判定）
之后做的第一批修正：把「一个事实多份副本」的地方收成单一真源。

- **审计产物**：新增 `docs/audit/`——16 份契约卡（JSON + 人读版）、592 条契约
  （covered 206 / partial 189 / gap 197）、152 个 keep / 原地改 / 重写 / 冻结判定、
  26 个实测探针。总报告 `docs/audit/REPORT.md`，模块明细 `docs/audit/DECISIONS.md`。
- **版本真源收口**：删掉 `whyexist.__version__`（停在 `2.23.0`、落后 69 个发布、
  全仓零读取）；README / HANDOFF / PRODUCT-PLAN / quality / CONTRIBUTING / SKILL 里的
  版本号、用例数、代码行数全部去掉，改为指向 `VERSION` 与运行结果。
- **`tools/check_docs.py`**：新增第四项检查——5 份文档里出现「当前版本 `X.Y.Z`」、
  「`Ran N tests`」、「`N 个用例`」、「`| 版本 | X.Y.Z |`」即报错，防止写死副本长回来。
- **CI**：`.github/workflows/ci.yml` 增加 `python tools/check_docs.py` 一步。此前
  `check_docs` 只在手动 `preflight` 里跑，所以版本漂移没人拦。
- **仓库落盘**：2.x 的实现、测试、工具、文档此前全部未提交（git 只跟踪到 v0.4.1 的
  25 个文件，CI 实际跑的是 42 条旧用例），本次整体提交为基线快照。
- **技能描述**：`SKILL.md` frontmatter 补上 `plan` / `brief` / `blind-check` / `impact` /
  `cycles` / `conformance` / `derive` / `conflicts` / `patch` / `apply`——此前模型侧
  只能看到 38 条命令，12 条核心能力不可发现。
- **测试**：381 不变。
- **版本**：契约 `2.92.0` → `2.93.0`；schema 仍为 `9`。

## 2.92.0（2026-11-02）

**交接说明**。96 轮迭代后加一份 `docs/HANDOFF.md`：当前状态、能力地图、两层验证怎么跑、
改东西的顺序、最容易踩的边界、目录结构、下一步方向。

- **测试**：381 不变。
- **版本**：契约 `2.91.0` → `2.92.0`；schema 仍为 `9`。

## 2.91.0（2026-11-02）

**真实仓生命周期验证进 `run_all`**。2.90.0 的脚本之前只能单独跑。

- **`run_all`** 从 5 条扩到 6 条，`verify_real_feature` 归入扫描组（依赖真实仓）。
- **实测**：全量 6 条 PASS；`--quick` 仍是 3 条（不依赖真实仓）。
- **测试**：381 不变。
- **版本**：契约 `2.90.0` → `2.91.0`；schema 仍为 `9`。

## 2.90.0（2026-11-02）

**真实仓完整生命周期验证**。之前所有流程验证都在 demo 仓上跑；这版在 flask（1186 节点）
上从扫描走到 gate PASS。

- **`refactor-lab/verify_real_feature.py`**：登记真实仓 → 扫描（24 文件 / 1186 节点）→
  derive（3 组件 / 6 依赖）→ 声明 feature → 六阶段 → **gate PASS，阶段 `Ready`**。
- **发现一个使用边界**：`coverage` 默认 ε=1.0，在 1186 节点的仓上要求咬合 **589 个节点**
  （公式 `(a/(b0+m))·(S−m) ≤ ε`）；**ε 是残余缺陷率上界，调小反而要求更高**（ε=0.01 时
  要 1174 个）。千节点级真实仓上基本不可行——SKILL 的覆盖边界已写具体数字。
- **测试**：381 不变。
- **版本**：契约 `2.89.0` → `2.90.0`；schema 仍为 `9`。

## 2.89.0（2026-11-02）

**import-repo 写入路径的小优化**。2.78 量出写入是瓶颈（rich 1.08s），试了两处改动。

- **去掉重复查询**：`import-file` / `import-repo` 已经查过节点判断 inserted/updated，
  `upsert_node` 内部又查一次——加 `existing` 参数复用。
- **批量插 feature_nodes**：逐节点插改为一次 `executemany`。
- **效果有限**：rich 合计 2.00s → **1.89s**（写入 1.08 → 1.14，噪声范围内），说明瓶颈不
  在 SQL 次数，而在每节点的属性校验与 JSON 序列化。2 秒扫完 213 文件，不值得继续抠。
- **测试**：381 不变。
- **版本**：契约 `2.88.0` → `2.89.0`；schema 仍为 `9`。

## 2.88.0（2026-11-02）

**文档完整性检查接进 preflight**。`check_changelog` / `check_design` 之前是两个实验脚本，
手工跑。文档漂移应该由发布前检查拦住，而不是靠每隔几十轮想起来核一次。

- **`tools/check_docs.py`**：合并两个检查，并加一项版本一致性——`VERSION`、
  `CONTRACT_VERSION`、`CHANGELOG` 最新条目三者必须一致。
- **`preflight`** 新增"文档完整性"步骤，现在六步（`--release` 时八步）。
- **结果**：CHANGELOG 108 条 / 0.1.0 ~ 2.87.0，design.md 105 节 / 1 ~ 105，三者版本一致。
- **测试**：381 不变。
- **版本**：契约 `2.87.0` → `2.88.0`；schema 仍为 `9`。

## 2.87.0（2026-11-02）

**`design.md` 节号核对**。104 节，需要确认编号连续、无重复。

- **`refactor-lab/check_design.py`**：提取所有 `## N.` 标题，检查数量、连续性、重复与
  版本信息位置。
- **发现并修复**：缺号 85、87——`2.61.0`（`verify_reports --repo`）和 `2.63.0`（仓画像）
  那两轮只写了 CHANGELOG 没写 `design.md`。补上两节后编号 1~104 连续。
- **版本信息分布**：标题 97 节 / 正文 74 节 / 两者皆无 7 节（§1-§6 说明性章节 + §82 收尾
  回顾），符合预期。
- **测试**：381 不变。
- **版本**：契约 `2.86.0` → `2.87.0`；schema 仍为 `9`。

## 2.86.0（2026-11-02）

**`CHANGELOG.md` 完整性核对**。从 0.1.0 到 2.85.0 有 106 个条目，中途多次批量改动，需要
确认没有版本跳跃或漏记。

- **`refactor-lab/check_changelog.py`**：提取所有 `## x.y.z` 标题，检查数量、连续性（允许
  同 minor +1、跨 minor +100、major 升级）、重复、文件顺序。
- **结果**：106 条，0.1.0 ~ 2.85.0，递增连续无跳跃，最新在前。
- **顺手修**：`refactor-lab/README.md` 里 "CRI 层" 的 typo。
- **测试**：381 不变。
- **版本**：契约 `2.85.0` → `2.86.0`；schema 仍为 `9`。

## 2.85.0（2026-11-02）

**过一遍「已知边界」23 条**。逐条判断是否还成立。

- **结论**：23 条全部仍然成立（其中"导入器支持相对导入"、"conformance 认 `x_evidence`"、
  "plan 的 `hint`"、"doctor 的 `fixable`" 已在之前版本更新过）。
- **修正**：`wxg.py` 行数 181 → 176（两处）。
- **新增一条**：`tools/verify_reports.py` 只验证同一份图在不同命令里的说法一致，不验证结论
  对不对——抓得到自相矛盾，抓不到"几个命令一起错"。
- **测试**：381 不变。
- **版本**：契约 `2.84.0` → `2.85.0`；schema 仍为 `9`。

## 2.84.0（2026-11-02）

**monorepo 形态验证**。poetry（`src/poetry/` 下十几层）和 pydantic。

- **poetry**：193 文件 / 5395 节点 → **19 组件 / 80 依赖 / 1 环**，6 条断言 PASS——是目前
  切出组件最多的仓，`--depth 2` 在多层目录上给出了细粒度分组。
- **pydantic**：34 文件 / 3011 节点 → 4 组件 / 6 依赖 / 1 环，4.5 秒跑完。
- **累计 14 个仓**，无新问题。
- **测试**：381 不变。
- **版本**：契约 `2.83.0` → `2.84.0`；schema 仍为 `9`。

## 2.83.0（2026-11-02）

**清理 dist + 第三批仓扫描**。

- **`dist/`**：清掉 87 个旧版本目录（v0.5.0 ~ v2.81.0，约 25MB），只留当前版本。
- **三个怪仓**：attrs（双包 `attr` + `attrs`，2 组件 / 1 依赖 / 无环）、httpx（多子包，
  2 组件 / 2 依赖 / 1 环）、black（40 文件 / 2203 节点，4 组件 / 5 依赖 / 1 环）——6 条
  自洽断言全 PASS。
- **累计扫过 12 个仓**，只有 rich 出过一次问题（2.62.0 已修）。
- **测试**：381 不变。
- **版本**：契约 `2.82.0` → `2.83.0`；schema 仍为 `9`。

## 2.82.0（2026-11-02）

**`refactor-lab/README.md` 补齐脚本表**。`find_dead.py` 和 `coverage_report.py` 是 2.80 /
2.81 加的，没登记进索引。

- 脚本表从 6 个补到 8 个（含各自依赖）。
- **测试**：381 不变。
- **版本**：契约 `2.81.0` → `2.82.0`；schema 仍为 `9`。

## 2.81.0（2026-11-02）

**测试覆盖的按模块统计**。拆包后没核对过哪些模块只被端到端间接覆盖。

- **`refactor-lab/coverage_report.py`**：AST 统计每个模块的顶层定义数与 `tests/` 里直接
  提及的名字数。
- **结论**：低占比的全是 CLI 层（`commands_*` / `query.py` / `importer.py`）——它们经
  子进程调用，静态分析看不见，不是盲区。纯函数层覆盖良好：`work.py` / `planner.py` /
  `jsonio.py` / `cycles.py` 都在 75% 以上。
- **方法局限**：静态统计无法区分"没测"和"经 CLI 测"，所以它只适合找可疑点，不能当覆盖率。
- **测试**：381 不变。
- **版本**：契约 `2.80.0` → `2.81.0`；schema 仍为 `9`。

## 2.80.0（2026-11-02）

**死代码检查**。拆包后有二十多个模块，需要确认没有残留的未引用定义。

- **`refactor-lab/find_dead.py`**：AST 收集 `whyexist` 包的顶层函数/类，与全仓引用比对。
- **结论**：213 个顶层名字里 47 个静态不可见，但**没有一个是死代码**——45 个是 `cmd_*`
  命令处理器（由 `getattr(wxg, "cmd_" + name)` 动态派发），2 个是 `__enter__`/`__exit__`
  上下文管理器协议方法。
- **测试**：381 不变。
- **版本**：契约 `2.79.0` → `2.80.0`；schema 仍为 `9`。

## 2.79.0（2026-11-02）

**`refactor-lab` 整理**。实验目录里堆了 38 个手工验证留下的临时 JSON（约 1.2MB），也没有
任何索引说明每个目录和脚本干什么。

- **清理**：删除 38 个临时 JSON（`h*.json` / `claim.json` 等，共 1.19MB）。
- **`refactor-lab/README.md`**：目录表（9 个仓、两份状态库实验）、脚本表（6 个）、报告表
  （4 份）、怎么跑、各仓的尺度与 import 耗时。
- **验证**：清理后 `run_all.py` 全量仍 5 个 PASS。
- **测试**：381 不变。
- **版本**：契约 `2.78.0` → `2.79.0`；schema 仍为 `9`。

## 2.78.0（2026-11-02）

**`import-repo` 性能基线**。之前只量过分析命令（都 <300ms），没量过扫描本身。

- **`refactor-lab/bench_import.py`**：分离解析与写入两段计时。
- **实测**：tabulate（13 文件 / 811 节点）0.72s、flask（24 / 1186）0.73s、httpie
  （133 / 3285）1.38s、rich（213 / 5273）**1.95s**——线性增长，没有性能问题。
- **写入比解析慢**：rich 上解析 0.87s / 写入 1.08s——写入是 SQLite 逐节点 upsert
  （单事务内），约 5k 节点/秒。
- **测试**：381 不变。
- **版本**：契约 `2.77.0` → `2.78.0`；schema 仍为 `9`。

## 2.77.0（2026-11-02）

**流程验证总入口**。`refactor-lab` 里五个验证脚本之前只能手工一个个跑，没有统一入口。

- **`refactor-lab/run_all.py`**：串跑五个脚本并汇总；`--quick` 只跑不依赖真实仓的三个
  （doc_flow / verify_change / verify_controller）。
- **分工**：`tools/preflight.py` 管发布前检查（测试/文档/契约/状态库/报告/打包/包能跑），
  `run_all.py` 管端到端流程（照文档跑/真实仓扫描/变更集/控制器/回扫）。
- **实测**：quick 3 个 PASS、全量 5 个 PASS。
- **测试**：381 不变。
- **版本**：契约 `2.76.0` → `2.77.0`；schema 仍为 `9`。

## 2.76.0（2026-11-02）

**发布前检查闭环：打包后验包**。`preflight --release` 之前打完包就结束——只证明了源码仓是
好的，没证明这个包能跑。

- **`tools/verify_release.py`**：从 `refactor-lab/` 移进来（它属于发布工具，不是实验脚本），
  解压最新 zip → 断言包内结构 → `up` → 最短路径 → `gate PASS`。
- **`preflight --release`** 在打包步骤后直接调用它，七步闭环：测试 → 文档 → 契约 → 状态库
  → 报告自洽 → 打包 → **包能独立跑**。
- **测试**：381 不变。
- **版本**：契约 `2.75.0` → `2.76.0`；schema 仍为 `9`。

## 2.75.0（2026-11-02）

**发布包独立运行验证**。之前所有验证都在源码仓里跑，没验证过解压出来的发布包能否独立工作。

- **`refactor-lab/verify_release.py`**：解压 `dist/` 最新 zip 到临时目录 → 断言包内结构
  （有 `wxg.py`、有 `SKILL.md`、不含仅源码仓分发的 `tools/`）→ `up --template standard` →
  最短路径六阶段 → `gate PASS`。
- **实测**：v2.74.0 的包在干净目录独立跑到 PASS，`checks` 全过、退出码 0。
- **顺带踩到两个坑**：脚本里用了 `tempfile.mkdtemp`（Windows 受限 token 下 PermissionError，
  该用 `whyexist.temp.make_temp_dir`）；`dist/` 里有旧版 v2.9.0，字符串排序会把它当最新。
- **版本**：契约 `2.74.0` → `2.75.0`；schema 仍为 `9`。测试 `381` 不变。

## 2.74.0（2026-11-02）

**实测"两分钟 PASS"承诺**。`PRODUCT-PLAN` 说新用户两分钟看到 PASS，实测自动化路径（`up` +
6 阶段 + `gate`，即 `tools/doc_flow.py` 全程）只要 **5.6 秒**。

- **文档修正**：把"两分钟内看到 PASS"改为"自动化 5.6 秒，人工跟着敲加阅读约两分钟"——
  两个数字含义不同，别混。
- **测试**：381 不变。
- **版本**：契约 `2.73.0` → `2.74.0`；schema 仍为 `9`。

## 2.73.0（2026-11-02）

**五个验证脚本首次组合跑通**。之前每个都单独跑过，没串起来确认互不干扰（都要建临时库、
都跑 `up`）。

- **组合结果**：`doc_flow` PASS / `verify_reports` 6 条 PASS / `verify_change` PASS /
  `verify_controller` PASS / `verify_sync` 报告一致。全部各自建临时库、跑完即删。
- **测试**：381 不变。
- **版本**：契约 `2.72.0` → `2.73.0`；schema 仍为 `9`。

## 2.72.0（2026-11-02）

**`SKILL.md` 工作流 26 条补上最近新增的字段**。最近几轮给输出加了 `bottleneck` / `direct` /
`hint` / `fixable` / `checks` / `phase`，但工作流条目还停在旧描述。

- **第 9 条**：`gate` 的 `checks`（9 项按顺序）与 `feature-status.phase`。
- **第 10 条**：`doctor` 的 `fixable` / `fixable_count` / `unfixable_checks`，说明 `legacy-identity`
  只能报不能修。
- **第 15 条**：`conformance` 的孤立拆分（`unanchored_count` / `truly_orphan_count`）、`hint`、
  以及 depends 边带 `x_evidence` 视为有依据。
- **第 16 条**：`plan.parallelism` 附 `bottleneck`；`--level code` 无代码节点时带 `hint`。
- **第 19 条**：`impact` 的 `direct` / `indirect` 拆分；`--changed` 支持逗号分隔。
- **第 24 条**：`derive` 的单组件 `hint`；import 解析支持相对导入。
- **版本**：契约 `2.71.0` → `2.72.0`；schema 仍为 `9`。测试 `381` 不变。

## 2.71.0（2026-11-02）

**`PRODUCT-PLAN` §3 / §4 / §6 对齐**。前几节还停在"缺口待补"和"2.0 版本"的说法。

- **§3 现状评估**：缺口表从"伤害排序"改为"当时的判断 → 现在的状态"，七项全部解决；
  资产表的用例数 101 → 381。
- **§4 产品模型**：从"实现主要在第一、三层"改为"三层都已落地"，列出 pass 层的八个纯函数模块。
- **§6 路线图**：P1 的验收改为 `from whyexist import Engine` + 381 用例；P4 的"2.0 版本"
  改为"已到 2.70.0"。
- **测试**：381 不变。
- **版本**：契约 `2.70.0` → `2.71.0`；schema 仍为 `9`。

## 2.70.0（2026-11-02）

**`PRODUCT-PLAN` §5 能力描述与实现对齐**。计划里写的是设计阶段的设想，几处字段名和语义
与实现不符。

- **§5.1 `plan`**：`scc` → `cyclic_components`；`parallelism` 的语义（无环=最大反链、
  有环=最大环大小）；`bottleneck` 从"入度/出度最高的节点"改为"受限于什么的说明文字"。
- **§5.2 `brief`**：实际返回 `feature` / `work_item` / `slice` 三段结构化字段，不是设想里的
  六段文字；补充"输出契约由角色决定，brief 不写死"。
- **§5.4 `impact`**：`downstream`/`upstream` → `affected`/`depends_on`，并补 `direct` /
  `indirect` / `closed` 与 `--remove-edges` 模式；说明 `--require-impact-closure` 未实现。
- **§5.5 `patch`/`apply`**：不是"让并行度由补丁语义决定"这么理想——`apply` 有意绕过
  `target_ids` 写边界，并发安全靠 reducer 冲突检测。
- **测试**：381 不变。
- **版本**：契约 `2.69.0` → `2.70.0`；schema 仍为 `9`。

## 2.69.0（2026-11-02）

**`PRODUCT-PLAN` 的模板描述与实现对齐**。计划里写 `wxg init --template minimal|service|
multi-agent`，实际是 `wxg up --template minimal|standard`——`init` 只建库，模板属于"立起
工作区"的 `up`。

- **修正**：`PRODUCT-PLAN.md` §5.6 的模板描述改为实际命令与选项。
- **测试**：381 不变。
- **版本**：契约 `2.68.0` → `2.69.0`；schema 仍为 `9`。

## 2.68.0（2026-11-02）

**文档与现状对齐**。`PRODUCT-PLAN.md` 和 `README.md` 停在前面的版本（契约 1.4.0 / 104 用例）。

- **`PRODUCT-PLAN.md`**：进度表补到 P6（拆包、分析深化、工具链全部完成），并列出六条核心
  流程的验证脚本；"主实现拆包"从"未开始"改为完成（4500 → 181 行）；质量门的"101 个用例"
  改为 381。
- **`README.md`**：用例数 104 → 381，版本描述从 1.4.0 更新到当前。
- **测试**：381 不变。
- **版本**：契约 `2.67.0` → `2.68.0`；schema 仍为 `9`。

## 2.67.0（2026-11-02）

**验证控制器安全迁移**。`reconcile --apply` / `serve` 之前只有单点测试，没在真实状态上验证。

- **`refactor-lab/verify_controller.py`**：手工制造三种待迁移状态（缺单 / 依赖已 passed 的
  blocked / 陈旧 claim），验证控制器只做安全迁移、不越界。
- **实测**：只读 reconcile 报出三种动作且不动库；`serve --once` 同样只读；
  `serve --once --apply` 后补回工单、解阻塞、回收 token；再跑 reconcile `actions=[]`。
- **顺带确认**：`reconcile` 未收敛时退出码是 1（由 `converged` 决定），不是错误。
- **测试**：381 不变。
- **版本**：契约 `2.66.0` → `2.67.0`；schema 仍为 `9`。

## 2.66.0（2026-11-02）

**验证 change-open 流程**。之前只测过"初次声明到 PASS"，没测过"已交付后改设计"这条路径。

- **`refactor-lab/verify_change.py`**：up → 走到 PASS → `change-open` → 断言继承/重置边界
  → `change-diff` → 新代重新走到 PASS → `reconcile` 收敛。
- **实测**：`1→2` 代，继承 `ArchitectureReconciled`、重置 5 个条件，阶段回到
  `StructureReconciled`；新代 6 阶段走完 gate PASS、`converged`。
- **`change-diff` 返回**：`inherited_conditions` / `pending_conditions` / `added` /
  `removed` / `kept` / `code_anchors`。
- **测试**：381 不变。
- **版本**：契约 `2.65.0` → `2.66.0`；schema 仍为 `9`。

## 2.65.0（2026-11-02）

**真孤立的来源提示**。rich 上 `truly_orphan=844` 看着像"844 个代码节点没被设计覆盖"，
查下来全在被 `--exclude` 排除的目录（`benchmarks/`、`examples/`）里——derive 不给它们分组，
所以没有 `contains`，属预期。

- **`verify_reports` 画像**：真孤立非零且传了 `--exclude` 时，附一句说明来源。
- **验证**：rich 的 844 个真孤立抽查样本全是 `benchmarks/benchmarks.py`、
  `examples/attrs.py` 这类被排除目录的文件。
- **测试**：381 不变。
- **版本**：契约 `2.64.0` → `2.65.0`；schema 仍为 `9`。

## 2.64.0（2026-11-02）

**孤立节点拆成两类**。`code_orphans` 在大仓上动辄几百个，但大部分是 derive 之后还没
promote 的正常中间态，不是"代码没被设计覆盖"。

- **`unanchored_count`**：落在 derived 组件 `contains` 范围内、但还没 `maps_to` 的节点。
- **`truly_orphan_count`**：完全没有任何设计覆盖的节点。
- **`hint`** 改用这两个数：flask 实测 379 个孤立里 **379 个 unanchored、0 个 truly_orphan**。
- **测试**：380 → 381（一个在 derived contains 里、一个完全无覆盖）。
- **版本**：契约 `2.63.0` → `2.64.0`；schema 仍为 `9`。

## 2.63.0（2026-11-02）

**`verify_reports` 输出仓画像**。批量扫仓时只看断言 PASS/FAIL，看不到规模与噪声比例。

- **画像**：扫描后打印 `节点数 / 边数 / unmapped 占比 / 组件数`，以及 `孤立 / 代码节点（占比）`。
- **实测 6 仓**：unmapped 占比稳定在 **50~58%**（内置与外部调用）；孤立率 **100%**——后者
  是因为 derived 组件还没有 `maps_to`（`contains` 是成员关系，不是锚定），属已知表现。
- **结论**：没有异常仓，导入器的 unmapped 处理是稳定的。
- **测试**：380 不变。
- **版本**：契约 `2.62.0` → `2.63.0`；schema 仍为 `9`。

## 2.62.0（2026-11-02）

**批量扫仓抓到的 derive bug**。用 `verify_reports --repo` 一条命令扫 click / tabulate / rich，
rich 上 `derive --apply` 直接失败：`边的 src 不存在：component:repo:tools`。

- **原因**：`derive_components` 的 `file_dependencies` 分支生成 depends 时没有检查端点组件
  是否真的分到了组——import 解析可能指向没有代码节点入图的目录（rich 的 `tools/`），那种
  端点没有 component 可写，`upsert-edge` 校验时直接拒绝。另一条分支（节点边）用的是
  `node_to_component`，天然只含已分组节点，所以只有 import 这条路会漏。
- **修法**：两端都在 `membership` 里才生成 depends。
- **实测**：rich 从"apply 失败"变成 2 组件 / 2 依赖 / 1 环、6 条断言全 PASS；
  click（17 文件）、tabulate（13 文件）也都 PASS。
- **测试**：378 → 380（端点未分组时丢弃、两端都分组时保留）。
- **版本**：契约 `2.61.0` → `2.62.0`；schema 仍为 `9`。

## 2.61.0（2026-11-02）

**`verify_reports --repo`：一条命令从源码仓走到检查**。之前要手工 init / repo-add /
declare / import-repo / claim / derive / 检查，换一个仓重来一遍。

- **`--repo <路径>`**：自动建临时库、登记仓、扫描导入、`derive --apply`（`--depth` /
  `--exclude` 透传），跑完 6 条自洽性断言即删。
- **实测三条**：flask（24 文件 → 1186 节点 → 3 组件 / 6 依赖，6 条 PASS）、
  itsdangerous（8 文件 → 161 节点 → 1 组件，4 条 PASS，跳过口径不同的环断言）、
  httpie `--depth 2`（133 文件 → 3285 节点 → 7 组件 / 21 依赖 / 1 个环，6 条 PASS）。
- **与手工结果一致**：httpie 的 7 组件 / 3-环正是之前 `httpie-lab` 手工跑出来的数字。
- **测试**：378 不变。
- **版本**：契约 `2.60.0` → `2.61.0`；schema 仍为 `9`。

## 2.60.0（2026-11-02）

**preflight 补上报告自洽性**。之前 `preflight` 只跑测试 + doc_flow + verify + doctor，
`verify_reports` 是独立工具，发布前容易忘。

- **新增步骤**：用临时 `up --template standard` 建小库，跑 `verify_reports`，断言 PASS。
- **实测**：`Ran 378 tests` / `doc_flow PASS` / `verify ok` / `doctor ok` / `reports PASS`。
- **测试**：378 不变。
- **版本**：契约 `2.59.0` → `2.60.0`；schema 仍为 `9`。

## 2.59.0（2026-11-02）

**报告自洽性检查工具**。三条验证路径（照文档跑、真实重构、真实仓库）之前都是临时脚本，
换个仓就得重写。这版把其中可自动化的部分固化：`tools/verify_reports.py`。

- **检查项**：plan 与 cycles 的环集合是否一致、cycles 节点数不超过 plan、conformance 的
  depends 数等于图内边数、impact 的 affected = changed ∪ direct ∪ indirect、
  feature-status.scope_size 等于 scope_ids。
- **口径处理**：`plan` 的 level 是 auto（可能退到代码层），`cycles` 永远用设计层——两者
  口径不同时跳过环断言并说明，不硬比。
- **实测**：flask-lab / httpie-lab / itsdangerous 三个库全 PASS。
- **测试**：378 不变。
- **版本**：契约 `2.58.0` → `2.59.0`；schema 仍为 `9`。

## 2.58.0（2026-11-02）

**收尾回顾：五十个版本的经验**。`design.md` 新增一节，把 2.7.0 → 2.57.0 的坑整理成八条
可复用的教训。

- **拆包**：隐式依赖不可见、替换范围吞产物、`globals()` 在包内失效、循环导入不总是显式的。
- **测试**：跳过的测试等于没测（`db.py` 缺 `import re` 就是这么漏的）。
- **验证**：报告真实性只能拿真实数据验——照文档跑、真实重构、真实仓库三次各抓到一个问题。
- **输出**：一个数字有两种来源时必须写明；能自动修和不能自动修要分开说。
- **版本**：契约 `2.57.0` → `2.58.0`；schema 仍为 `9`。测试 `378` 不变。

## 2.57.0（2026-11-02）

**`doctor` 明确哪些能修**。`--fix` 只清理悬空引用与陈旧 token，但输出里没标哪些 issue 是
可修的，读者容易以为 `--fix` 能解决所有问题。

- **`DOCTOR_FIXABLE_CHECKS`**（契约新增）：7 类可自动修的问题——dangling-bite /
  orphan-edge / feature-node-missing / work-target-missing / work-evidence-missing /
  token-on-inactive / meta-version。
- **`doctor` 输出**：每个 issue 带 `fixable`；汇总加 `fixable_count` / `unfixable_count` /
  `unfixable_checks`（如 `legacy-identity` 永远不可修——修了等于伪造审计身份）。
- **I9 不变量**同步更新，列出可修项。
- **测试**：378 不变（在 legacy 场景补断言）。
- **版本**：契约 `2.56.0` → `2.57.0`；schema 仍为 `9`。

## 2.56.0（2026-11-02）

**`conformance` 的孤立节点提示**。flask 上 `code_orphans=379`，看着像"代码没被设计覆盖"，
实际是 derived 组件还没 `maps_to` 锚定。

- **`hint`**：存在 derived 组件且有孤立节点时，说明"有 N 个 derived 组件还没锚定，M 个
  代码节点因此全算孤立；先 promote 并补 maps_to，这个数才有可比性"。
- **实测**：flask（3 个 derived 组件）出提示；httpie（全是 declared 组件、0 孤立）无提示。
- **测试**：376 → 378（derived 场景出提示、全锚定场景不出）。
- **版本**：契约 `2.55.0` → `2.56.0`；schema 仍为 `9`。

## 2.55.0（2026-11-02）

**`conformance` 认 derive 的依赖证据**。flask 上跑 conformance 时 `missing_backing=6`——
但 derive 的 depends 就是从 import 推导的，本身有代码依据。

- **原因**：`missing_backing` 只通过 `maps_to` 建立的 `code_map` 判断支撑；derived 组件没有
  `maps_to`，于是它的依赖全被判"无支撑"。
- **修法**：depends 边若带 `attrs.x_evidence`（derive 写入的来源文件对），直接视为有代码依据。
- **实测（flask）**：`violations` 9 → 3，`missing_backing` 6 → 0；剩下 3 个 missing_anchors
  是 derived 组件确实没有 `maps_to`，属合理报告。
- **测试**：375 → 376（带 x_evidence 的 depends 不计入 missing_backing）。
- **版本**：契约 `2.54.0` → `2.55.0`；schema 仍为 `9`。

## 2.54.0（2026-11-02）

**`sync` 的 unmapped 噪声标注**。用 bad-boids 的真实重构验证 `sync` 报告，发现一个噪声点。

- **验证**：HEAD（重构前）建图 → 工作区（重构后）覆盖 → `sync` 报 missing=3 / new=28 /
  changed=3，与真实改动一致（render.py 的 12 个节点在 new，boids.py 的旧节点在 missing）。
- **改进**：`changed` 里混着 `len` / `range` 这类内置调用的 unmapped 节点——行号变了也算
  "changed"，但不是设计改动。现在每项带 `unmapped` 标记，另加 `changed_unmapped_count`
  单独计数；设计层关心的改动数是 `changed_count - changed_unmapped_count`。
- **测试**：375 不变（在现有 sync 用例里补断言）。
- **版本**：契约 `2.53.0` → `2.54.0`；schema 仍为 `9`。

## 2.53.0（2026-11-02）

**输出体积与耗时的横向检查**。2.52.0 修了 `feature-status` 的 74KB 输出，这版把其他命令
也量了一遍（flask-lab，1186 节点）。

- **体积**：`conformance` 4.5KB（有 limit 截断）、`gate` 3KB、`coverage` 1.5KB、
  `drift` 1.2KB、`doctor` 0.3KB——没有第二个失控的。
- **耗时**：`plan` 252ms、`cycles` 244ms、`conformance` 289ms、`feature-status` 240ms
  （含 Python 启动），没有需要优化的热点。
- **`export`**：6 个视图各 0.2–0.3KB——flask 还没建设计节点，视图是空的，属正常。
- **测试**：375 不变。
- **版本**：契约 `2.52.0` → `2.53.0`；schema 仍为 `9`。

## 2.52.0（2026-11-02）

**`feature-status` 瘦身：概览视图不再塞完整 `target_ids`**。

- **`work_items[*]`**：`target_ids` 换成 `target_count` + `target_sample`（前 5 条），
  `depends_on` 从 JSON 字符串解析成列表。要看全量用 `slice --work <id>`。
- **实测（flask-lab）**：scan 工单有 1186 条 target，`feature-status` 输出从 **74KB 降到 6KB**。
- **测试**：374 → 375（CLI 用例，断言裁剪且 `depends_on` 是列表）。
- **版本**：契约 `2.51.0` → `2.52.0`；schema 仍为 `9`。

## 2.51.0（2026-11-02）

**`impact` 区分直接下游与间接波及**。

- **`direct` / `indirect`**：按反向 BFS 的最短跳数拆——`direct` 是一跳内直接依赖
  `--changed` 的节点，`indirect` 是隔了两跳及以上的。`affected` 保持原样（完整波及面）。
- **实测（httpie）**：改 `httpie.cli` → `affected=11`，其中 `direct=5`
  （extras.scripts / httpie / httpie.manager / httpie.output / tests）、`indirect=5`
  （extras.packaging / httpie.internal / httpie.legacy / tests.fixtures / tests.utils）。
- **测试**：371 → 374（一跳 / 多跳 / 菱形按最短跳）。
- **版本**：契约 `2.50.0` → `2.51.0`；schema 仍为 `9`。

## 2.50.0（2026-11-02）

**`plan` 的 `parallelism` 说清楚受限于什么**。这个数字有两种来源，读者分不清。

- **`bottleneck` 字段**：无环时"最大反链 N 个节点可同时做（M 层，最宽 K 个）"；有环时
  "受限于最大环：N 个节点必须串行（成员）"；只有单点自环时"不阻断并行，但拓扑分层不可用"。
- **实测**：flask 的 `plan` 给出 `parallelism=3` + "受限于最大环：3 个节点必须串行
  （flask / flask.json / flask.sansio）"。
- **测试**：368 → 371（DAG / 环 / 自环三种形态）。
- **版本**：契约 `2.49.0` → `2.50.0`；schema 仍为 `9`。

## 2.49.0（2026-11-02）

**环的形态接成建议**。2.48.0 只标了 `shape`，读者还得自己翻译成"该怎么办"。

- **`cycles` 每个环加 `guidance`**：`parent-child` 明确说"不要用断边掩盖——断边只改可达性、
  不改变分层方向"；`sibling` 建议断代价最小的一条或抽公共下层；`self-loop` 让查递归写入。
- **理由**：两种形态的正确处理不一样。父子包互依赖用断边只会把反向依赖藏起来，环没了但
  问题还在。
- **测试**：366 → 368（guidance 与 shape 对应、父子包场景明确说"不要断边"）。
- **版本**：契约 `2.48.0` → `2.49.0`；schema 仍为 `9`。

## 2.48.0（2026-11-02）

**环的形态分类**。flask 和 httpie 两个仓都出现"包与子包互相依赖"的环，但输出只有成员和
边，看不出这个结构特征。

- **`cycles` 每个环加 `shape`**：`parent-child`（父子包互依赖，分层没切开）、`sibling`
  （平级互调）、`self-loop`。判断基于 component 名的前缀关系；非 component 节点混入时归
  `sibling`，不做语义猜测。
- **实测**：flask 的 `flask` / `flask.json` / `flask.sansio` 与 httpie 的
  `httpie` / `httpie.cli` / `httpie.output` 都判为 `parent-child`——同一种结构问题。
- **测试**：361 → 366（父子 / 平级 / 非 component / 自环 / 多节点带 shape）。
- **版本**：契约 `2.47.0` → `2.48.0`；schema 仍为 `9`。

## 2.47.0（2026-11-02）

**相对导入解析：`derive` 的 `depends` 不再为空**。

- **`_import_file_pairs` 支持相对导入**：`from . import x`（level=1, module=None）、
  `from .json import dumps`（level=1, module 有值）、`from ..base import thing`（level=2+）
  都能解析成仓内文件对；绝对导入行为不变。
- **实测（flask）**：24 文件 → 1186 节点 / 1377 边；`derive --depth 2` 从 3 组件 /
  **0 依赖** 变成 3 组件 / **6 依赖**，每条带文件级证据。顺带暴露 flask 顶层与
  `flask.json` / `flask.sansio` 三方互相依赖。
- **测试**：357 → 361（四种相对导入形态 + 绝对导入回归）。
- **版本**：契约 `2.46.0` → `2.47.0`；schema 仍为 `9`。

## 2.46.0（2026-11-02）

**陌生仓实验：itsdangerous，以及 `derive` 的单组件提示**。拿一个没接触过的仓走一遍扫描分析。

- **扫描**：8 个文件 → 161 节点 / 188 边；`plan` 162 节点 / 142 边 / 7 层 / 无环；
  `conformance` 报 72 个 code_orphans；`cycles` 0 环。
- **发现**：`derive` 在单层包仓上只能得到 1 个组件（`--depth` 无论取多少都一样）——
  这是正确分组，但输出看起来像结论。现在 `components <= 1` 时带 `hint`，说明目录层级
  不足以分组、可先 `--exclude` 再去掉测试/文档。
- **测试**：357 不变（在已有 derive 用例里补 hint 断言）。
- **版本**：契约 `2.45.0` → `2.46.0`；schema 仍为 `9`。

## 2.45.0（2026-11-02）

**发布前检查收成一条命令**。

- **`tools/preflight.py`**：回归测试 + 文档一致性（`doc_flow`）+ `verify` + `doctor`
  （临时新库自建），`--release` 再加打包。任一步失败立即退出并打印尾部日志。
- **`quality.md` §1** 的检查项改为只跑 `preflight`；`SKILL.md` 文件表补一行。
- **实测**：`Ran 357 tests` / `doc_flow PASS` / `verify ok` / `doctor ok` 一路绿。
- **测试**：357 不变。
- **版本**：契约 `2.44.0` → `2.45.0`；schema 仍为 `9`。

## 2.44.0（2026-11-02）

**文档扫描：`design.md` 加阅读指引**。扫了剩下的 `references/*.md`。

- **`design.md` 开头加「怎么读」**：这份文件是按版本追加的演进记录，早期小节的实现细节
  可能已被覆盖（如 §14 提到的 `whyexist/legacy.py` 在 2.24.0 已删）。当前行为以
  `SKILL.md` / `references/contract.md` / `CHANGELOG.md` 顶部为准。
- **`patterns.md` 核对**：没有具体命令引用，`applicability` / `not_applicable` / `applies`
  的描述与 gate 实现一致，无需改动。
- **`design.md` 里的旧版本号是历史记录**，保留不动。
- **测试**：357 不变。
- **版本**：契约 `2.43.0` → `2.44.0`；schema 仍为 `9`。

## 2.43.0（2026-11-02）

**`quality.md` 对齐现行版本**。这份提交检查表停在 1.4.0 / 104 测试，且重复维护了一份
「已知边界」副本。

- **版本状态**：改为 `2.42.0` / schema 9 / 357 用例，版本历史指向 `CHANGELOG.md`。
- **边界单一来源**：删掉重复的边界清单，指向 `SKILL.md`「已知边界」——两处清单必然漂移，
  2.36.0 的 gate 描述过时就是这么漏的。
- **新增检查项**：`python tools/doc_flow.py`（照文档走到 gate PASS）；§3 补"改 CLI 表面后
  必须跑 doc_flow"。
- **测试**：357 不变。
- **版本**：契约 `2.42.0` → `2.43.0`；schema 仍为 `9`。

## 2.42.0（2026-11-02）

**把文档一致性检查收进技能**。2.41.0 靠"照文档手动跑"发现的脱节，这版变成可重复的脚本。

- **`tools/doc_flow.py`**：只按 `SKILL.md` 最短路径执行命令序列，每步断言——`up` →
  `import-file --prepare` → scan 链 → 六阶段 → evidence/observe → `gate PASS` →
  `export`。任何一步失败都说明文档与实现脱节。
- **`SKILL.md` 文件表更新**：补 `scripts/whyexist/`、`tools/doc_flow.py`、
  `tools/build_release.py`；`scripts/wxg.py` 的描述从"CLI 主实现"改为"181 行薄入口"。
- **版本**：契约 `2.41.0` → `2.42.0`；schema 仍为 `9`。测试 `357` 不变。

## 2.41.0（2026-11-02）

**照文档跑一遍，修掉两处误导**。用干净目录、只按 `SKILL.md` 走，从 `up` 到 `gate PASS`
跑通，过程中发现两个问题。

- **修 `up` 的 `next`**：第一条建议是 `work-claim --role scan`，但 scan 工单要到
  `import-file --prepare` 才创建——照做会领不到单。现在第一条是 `import-file --prepare`，
  并注明"scan 工单在这一步才创建"。
- **补文档**：`SKILL.md` 的最短路径写明"扫描导入"是独立第一步，且 `implement-test`
  的 claim 要加 `--allow-product-code`。
- **测试**：357 不变（`up` 的 `next` 断言改成钉住第一条必须是 prepare）。
- **版本**：契约 `2.40.0` → `2.41.0`；schema 仍为 `9`。

## 2.40.0（2026-11-02）

**文档：从零到 `gate PASS` 的最短路径**。

- **`SKILL.md` 快速开始**新增一节：一条 `up --template standard` 起步，之后只剩
  "每个条件 = 一次工单生命周期"的循环（open → claim → 写 → finish → judge）。
- **指向**：`gate` 的 `checks` 表（design.md §61）与完整流程测试
  （`test_full_flow_reaches_pass_gate`）。
- **版本**：契约 `2.39.0` → `2.40.0`；schema 仍为 `9`。测试 `357` 不变。

## 2.39.0（2026-11-02）

**id 列表参数统一支持逗号分隔**。上一版只改了 `impact --changed`，这版把
`--ids` / `--node-ids` / `--edge-ids` / `--target-ids` 也统一了。

- **`jsonio.load_id_list`**：公共解析函数——首字符 `[` / `"` / `{` / `@` 走 JSON，
  其余按逗号分隔；非数组的 JSON 仍报错。
- **同步更新**：`slice --ids`、`retract --node-ids/--edge-ids`、`work-open --target-ids`，
  以及契约里的四处 help。
- **测试**：355 → 357（逗号分隔、JSON 字符串拒绝）。
- **版本**：契约 `2.38.0` → `2.39.0`；schema 仍为 `9`。

## 2.38.0（2026-11-02）

**`impact --changed` 支持逗号分隔**。之前只能传 JSON 数组或 `@文件`，手写别扭。

- **`--changed a,b,c`**：逗号分隔的裸 id 直接用；以 `[` / `"` / `{` / `@` 开头时仍按
  JSON 解析（数组或文件），非数组继续报错。
- **实测**：httpie 上 `--changed cli,output` 正确解析为两个组件，影响 11 个。
- **测试**：353 → 355（逗号分隔、空值拒绝）。
- **版本**：契约 `2.37.0` → `2.38.0`；schema 仍为 `9`。

## 2.37.0（2026-11-02）

**`gate` 返回 `checks` 列表**。原来只有 `result` 和一堆细节字段，FAIL 时得自己对是哪一项。

- **`checks`**：9 项按判定顺序列出 `{name, ok}`——bites / pattern / drift / construction /
  stale / conformance / conditions / evidence / coverage。第一个 `ok=false` 的就是 FAIL 原因。
- **实测**：httpie 的 gate 直接显示 `stale=false`、`conditions=false`，其余为真。
- **测试**：352 → 353（CLI 用例，钉住顺序与字段）。
- **版本**：契约 `2.36.0` → `2.37.0`；schema 仍为 `9`。

## 2.36.0（2026-11-02）

**文档审计：`gate` 的边界描述补全**。系统核对了「已知边界」23 条。

- **修正**：原写"`gate` 只校验条件/咬合/证据、pattern、coverage/drift 与 conformance"，
  漏了施工标记与作用域内 stale 节点——这两项都会让 gate FAIL。
- **其余 22 条**核对后仍准确（导入器、测试执行、状态库信任、coverage/drift 概率性、
  reconcile、变更集、回扫、conformance、plan、brief、blind-check、up/Engine、impact、
  apply、derive、SQLite/MySQL/PG、serve、feature-register）。
- **版本**：契约 `2.35.0` → `2.36.0`；schema 仍为 `9`。测试 `352` 不变。

## 2.35.0（2026-11-02）

**文档：作用域与 `plan` 层级的关系**。

- **`SKILL.md` 已知边界**：补 `plan --level code` 只分析作用域内**已包含**的代码节点；
  作用域只有设计元素时返回 0 边（结果带 `hint`），需先
  `work-open --target-ids '["operation:*"]'`。
- **修正**：`SKILL.md` 里"`wxg.py` 仍是主实现、`whyexist/legacy.py` 是隔离层"已过时——
  `legacy.py` 在 2.24.0 删除，`wxg.py` 现在是 181 行薄入口。
- **版本**：契约 `2.34.0` → `2.35.0`；schema 仍为 `9`。测试 `352` 不变。

## 2.34.0（2026-11-02）

**`plan --level code` 空结果时的提示**。作用域只含设计元素时，代码层边必然为 0，
但输出看起来像"没有并行空间"。

- **`hint` 字段**：`--level code` 且作用域内没有代码层节点时给出提示，说明是作用域问题、
  以及怎么把代码节点纳入（`work-open --target-ids '["operation:*"]'`）。
- **实测**：httpie 的 `--level code` 返回 8 节点 0 边，现在带提示。
- **测试**：351 → 352（CLI 用例）。
- **版本**：契约 `2.33.0` → `2.34.0`；schema 仍为 `9`。

## 2.33.0（2026-11-02）

**JSON 参数报错带期望格式**。`--data` / `--changed` 一类参数同时接受 JSON 与 `@文件`，
原来只报 `JSON 解析失败：Expecting value`，看不出是格式问题。

- **`load_json_arg`**：报错改为"参数不是合法 JSON：期望数组/对象字面量（如 `'["id"]'`）
  或 @文件（第 N 行第 M 列：…）"；文件内容坏时带上文件名。
- **行为变化**：空字符串不再返回 `None`，而是报错（与"该参数必填"一致）。
- **测试**：349 → 351（期望格式提示、坏文件带文件名）。
- **版本**：契约 `2.32.0` → `2.33.0`；schema 仍为 `9`。

## 2.32.0（2026-11-02）

**文档补漏：导出视图与 Windows 临时目录陷阱**。

- **修正**：端到端演练报告里"导出缺数据不生成 03/06"是错的——`EXPORT_FILES` 本来就只有
  6 项（01 需求、02 用例、04 架构、05 类图、07 数据流、测试规格），编号 03 / 06 是空的。
- **新增** `references/design.md` 附录：Windows 受限 token 下 `tempfile.mkdtemp` /
  `TemporaryDirectory` 会因空 DACL 失败，一律改用 `whyexist.temp.make_temp_dir` /
  `temp_dir`。这个坑在注释、单测、端到端脚本里各踩过一次，光写在代码注释里不够。
- **版本**：契约 `2.31.0` → `2.32.0`；schema 仍为 `9`。测试 `349` 不变。

## 2.31.0（2026-11-02）

**`feature-status` 增加 `phase` 字段**。端到端演练时发现当前阶段要从 `conditions` 里
自己推，补一个直接字段。

- **`phase`**：第一个为假的条件名；全齐时是 `Ready`，与门禁判定走同一套条件链。
- **测试**：348 → 349（CLI 用例）。
- **版本**：契约 `2.30.0` → `2.31.0`；schema 仍为 `9`。

## 2.30.0（2026-11-02）

**设计-代码一致性报告的单测**。新增 `ConformanceTest`（10 个用例），直接打内存库。

- **锚点**：设计元素没有 `maps_to` 到带 `repo` / `path` 的代码节点时报告；锚到代码节点后消失。
- **代码孤立**：有 `repo` / `path` 的 operation 未被任何设计映射时报告，但只报告不算 violation。
- **结构支撑**：`depends` 边没有对应代码调用时算 `missing_backing`。
- **未声明耦合**：跨设计单元的代码调用若没声明 `depends`，报 `undeclared`；声明后消失。
- **测试覆盖**：`use_case` 没有 `verifies` 边算缺测试。
- **截断**：`limit` 只截列表，`missing_count` 保持全量，`truncated` 为真。
- **测试**：338 → 348。
- **版本**：契约 `2.29.0` → `2.30.0`；schema 仍为 `9`。

## 2.29.0（2026-11-02）

**覆盖公式与报告的单测**。新增 `CoverageMathTest`（6 个）与 `CoverageReportTest`（3 个）。

- **`_required_coverage`**：零作用域、非正 epsilon、已满足、需二分找最小 m、上限为
  作用域大小这五种情形。
- **`coverage_report`**：空咬合时所有阶段 `covered=0`；默认 `epsilon=1.0` 较宽松，
  `n_required` 可以是 0；`epsilon=0.001` 时每个阶段至少要求 1 个覆盖且 `met=False`。
- **`drift_report`**：空图 count=0、未设上限时 `enforced=False`。
- **测试**：329 → 338。
- **版本**：契约 `2.28.0` → `2.29.0`；schema 仍为 `9`。

## 2.28.0（2026-11-02）

**条件链与就绪派生的 DB 层单测**。新增 `WorkflowStateTest`（9 个用例），直接打 SQLite
内存库。

- **覆盖**：`ensure_feature` 缺失、`condition_flags` 条件不齐拒绝、`current_phase`
  （第一个假条件 / 全齐 → Ready）、`recompute_ready`（全真置 1 / 缺一置 0）、
  `refresh_blocked`（依赖 passed 解阻 / 依赖未 passed 保持阻塞）、`scope_ids`
  （feature_nodes + requirement 前缀 + 工单通配展开）。
- **测试**：320 → 329。
- **版本**：契约 `2.27.0` → `2.28.0`；schema 仍为 `9`。

## 2.27.0（2026-11-02）

**工单状态机的 DB 层单测**。新增 `WorkStateTest`（10 个用例），直接打 SQLite 内存库，
不经过 CLI。

- **覆盖**：`insert_work` 的新建 / merge 去重 / passed 态拒绝 merge / 非 merge 覆盖；
  `require_token` 的缺失 / 无效 / 非 claimed / 正常；`append_evidence` 去重；
  `get_work_by_token`。
- **测试**：310 → 320。
- **版本**：契约 `2.26.0` → `2.27.0`；schema 仍为 `9`。

## 2.26.0（2026-11-02）

**方言转换边界用例**。给 `_mysql_translate` / `_pg_translate` / `_named_params`
补 8 个用例，覆盖实际 schema 里出现的两种 SQL 形态（meta upsert、judge_history
忽略重复）与几个边界。

- **MySQL**：meta upsert 全链路（引号化 `key`/`value`、`ON DUPLICATE KEY UPDATE`、
  `VALUES(value)`）、meta 查询、`INSERT OR IGNORE` 无冲突、多行缩进的 ON CONFLICT。
- **PostgreSQL**：`INSERT OR IGNORE` 追加 `ON CONFLICT DO NOTHING`、尾随分号处理、
  `?` → `%s`。
- **`_named_params`**：同一占位符重复出现时按出现次数收集参数；记录一条已知限制
  ——字符串字面量里的 `:name` 也会被当作占位符（当前 schema 不依赖）。
- **结论**：转换逻辑对真实 SQL 形态是正确的，没有新 bug。
- **测试**：302 → 310。
- **版本**：契约 `2.25.0` → `2.26.0`；schema 仍为 `9`。

## 2.25.0（2026-11-02）

**补包内单测，抓到一个潜伏 bug**。新增 `tests/test_package_units.py`（29 个用例），
直接测包内纯函数层，不经过 CLI subprocess。

- **覆盖**：`jsonio`（序列化、`@文件`、令牌）、`work`（`work_id` / `target_match` /
  `require_targets` / `require_role`）、`db` 方言转换（`_mysql_translate` /
  `_pg_translate` / `_named_params`）、`graph` 校验（kind / node_id / attrs / edge_id）、
  `evidence.sha256_file`。
- **修 `db.py` 缺 `import re`**：`_named_params` 用了 `re.sub` 但模块没导入；因为
  MySQL/PG 后端测试一直跳过，这段从没被执行过。单测第一次跑就报 `NameError`。
- **测试改用 `whyexist.temp.temp_dir`**：`tempfile.TemporaryDirectory` 在 Windows 受限
  token 下会留下空 DACL、清理时 `PermissionError`（与 `temp.py` 注释里的 CVE 同源）。
- **测试**：273 → 302。
- **版本**：契约 `2.24.0` → `2.25.0`；schema 仍为 `9`。

## 2.24.0（2026-11-02）

**清理收尾：删掉 `legacy.py`，收敛延迟导入**。

- **删 `whyexist/legacy.py`**：这层原本是"新代码只经由一个显式文件访问旧入口"的过渡
  边界。所有函数都已在包内，`engine.py` 改为直接 import 具体模块，`test_engine.py`
  改用 `whyexist.errors.Reject` 与 `whyexist.temp.make_temp_dir`，不再依赖 `wxg` 模块。
- **收敛包内导入**：`commands_compiler.py` / `commands_repo.py` 里 10 处函数级
  `from whyexist import xxx` 改成顶层相对导入（`from . import ...`）。
- **`whyexist.__version__`**：`2.0.0-dev` → 与契约同版本。
- **测试**：273 不变。
- **版本**：契约 `2.23.0` → `2.24.0`；schema 仍为 `9`。

## 2.23.0（2026-11-02）

**拆包第十四步：CLI 入口完成，`wxg.py` 变薄壳**。仓库/导入命令搬进
`whyexist/commands_repo.py`，`build_parser` / `main` 搬进 `whyexist/cli.py`。
`wxg.py` 从 4500 行降到 181 行，只负责准备 `sys.path`、注册 `__main__` 为 `wxg`、
re-export 包内符号。

- **`whyexist/cli.py`**：`build_parser` / `main`；命令分派改为从入口模块 `wxg` 取
  `cmd_*`（`globals()` 在包内失效）。
- **`whyexist/commands_repo.py`**：init / up / repo-* / import-* / derive / promote /
  sync / sample。
- **迁移暴露的隐式依赖**：`argparse`、`ast`、`random`、`scope_ids`、`actor_value`、
  `check_kind` / `check_attrs` / `check_node_id`、`insert_work`、`require_role` 等。
- **测试**：273 不变。
- **版本**：契约 `2.22.0` → `2.23.0`；schema 仍为 `9`。
- 边界：`whyexist/legacy.py` 仍是旧入口适配层，后续可删。

## 2.22.0（2026-11-02）

**拆包第十三步：export / verify / doctor**。export、role-prompt、contract、verify、
doctor 搬进 `whyexist/commands_misc.py`。

- **`whyexist/commands_misc.py`**：导出视图、角色提示、契约生成、`verify`、`doctor`。
- **`cmd_verify` 的处理器检查改为从入口模块取**：原来用 `globals()` 找 `cmd_*`，搬进包内
  后 `globals()` 只剩包内命名空间，会误报"命令没有处理器"。
- **迁移暴露的隐式依赖**：`SKILL_DIR`、`Counter`、`ensure_feature`、`scope_ids`、
  `get_work`、`make_temp_dir` / `temp_dir`；一次替换范围还吞掉了 query 的 re-export。
- **测试**：273 不变。
- **版本**：契约 `2.21.0` → `2.22.0`；schema 仍为 `9`。
- 边界：CLI 入口（`build_parser` / `main`）仍在 `wxg.py`。

## 2.21.0（2026-11-02）

**拆包第十二步：覆盖 / 一致性 / 调谐 / gate**。coverage / conformance / reconcile /
serve 搬进 `whyexist/commands_gates.py`，随后把 `cmd_gate` 也搬过去。

- **`whyexist/commands_gates.py`**：coverage / conformance / reconcile / serve / gate，
  以及 `apply_safe_actions` / `_pending_counts` / `reconcile_feature`。
- **为什么 `cmd_gate` 也得搬**：`commands_gates` 的 `reconcile_feature` 要读 gate 结果，
  留在 `wxg.py` 会形成循环导入。
- **迁移暴露的隐式依赖**：`argparse`、`scope_ids`、`evidence_qualifies`、`work_seed`、
  `refresh_blocked`、`get_feature`、`utc_now`、`dumps`，逐个由回归逼出。
- **测试**：273 不变。
- **版本**：契约 `2.20.0` → `2.21.0`；schema 仍为 `9`。
- 边界：export / verify / doctor / CLI 仍在 `wxg.py`。

## 2.20.0（2026-11-02）

**拆包第十一步：编译器命令组**。plan / brief / blind-check / cycles / patch / apply /
impact / conflicts 搬进 `whyexist/commands_compiler.py`。

- **`whyexist/commands_compiler.py`**：8 个编译器命令 + `_brief_payload`；判定逻辑仍在
  planner / briefing / blind / cycles / reducer / impact / conflicts 七个纯函数模块。
- **迁移暴露的隐式依赖**：`Path`、`get_work`、`json`、`upsert_node` / `upsert_edge`，
  照例由回归报 `NameError` 逼出。
- **测试**：273 不变。
- **版本**：契约 `2.19.0` → `2.20.0`；schema 仍为 `9`。
- 边界：覆盖/一致性/调谐、gate/export、verify/doctor、CLI 仍在 `wxg.py`。

## 2.19.0（2026-11-02）

**拆包第十步：图写入与证据命令组**。upsert-node / upsert-edge / bind / retract /
bite / evidence-record / evidence-list 搬进 `whyexist/commands_graph.py`。

- **`whyexist/commands_graph.py`**：8 个命令 + `prune_work_refs`；写入前统一过
  `_require_write`（token + target_ids 边界）。
- **迁移暴露的隐式依赖**：`get_node`、`ensure_feature`、`current_phase`、`dumps`、
  `uuid`、`Path`、`get_work`——又是逐个由回归报 `NameError` 逼出来。
- **测试**：273 不变。
- **版本**：契约 `2.18.0` → `2.19.0`；schema 仍为 `9`。
- 边界：导出/校验/doctor/CLI 仍在 `wxg.py`。

## 2.18.0（2026-11-02）

**拆包第九步：feature 与工单命令组**。15 个 `cmd_*` 函数（约 700 行）搬进
`whyexist/commands_feature.py`；证据校验抽成 `whyexist/evidence.py`；`actor_value`
移入 `workflow.py`。

- **`whyexist/commands_feature.py`**：feature-declare / register / list / status、
  change-open / diff、work-seed / open / claim / finish / judge / list，以及
  `_require_write` / `_resolve_subject` / `record_judge_history`。
- **`whyexist/evidence.py`**：`sha256_file` 与 `evidence_qualifies`（产物 hash 与
  同代 evidence 采信条件），被命令层与 gates 共用。
- **迁移暴露的隐式依赖**：`re`、`uuid`、`get_node`、`upsert_node`、`new_token`、
  `slice_payload`、`resolve_targets`、`require_*` 系列、`coverage_report` /
  `conformance_report` / `drift_report`——逐个由回归报 `NameError` 逼出来。
- **测试**：273 不变。
- **版本**：契约 `2.17.0` → `2.18.0`；schema 仍为 `9`。
- 边界：其余命令（图写入、咬合、证据、导出、校验、CLI）仍在 `wxg.py`。

## 2.17.0（2026-11-02）

**拆包第八步：只读查询命令**。`slice` / `get` / `find` 及其目标解析、切片组装搬到
`whyexist/query.py`。

- **`whyexist/query.py`**：`resolve_targets`（通配展开）、`slice_payload`（深度 1 切片）、
  `cmd_slice` / `cmd_get` / `cmd_find`。
- **迁移暴露的隐式依赖**：`get_node`、`load_json_arg`、`get_work` 三个 import 先后漏掉，
  靠回归逐个抓出。
- **测试**：273 不变。
- **版本**：契约 `2.16.0` → `2.17.0`；schema 仍为 `9`。
- 边界：其余命令实现与 CLI 仍在 `wxg.py`。

## 2.16.0（2026-11-02）

**拆包第七步：Python AST 导入器**。`plan_python` 与 `_node_id` 搬进
`whyexist/importer.py`。

- **`whyexist/importer.py`**：解析单个 Python 文件，产出节点/边；认不出的调用按 I7
  建 unmapped 节点，不静默丢弃。
- **迁移暴露的隐式依赖**：`edge_id` 来自 `graph.py`，漏了 import，靠回归抓出。
- **测试**：273 不变。
- **版本**：契约 `2.15.0` → `2.16.0`；schema 仍为 `9`。
- 边界：命令实现与 CLI（约 2700 行）仍在 `wxg.py`。

## 2.15.0（2026-11-02）

**拆包第六步：门禁分析层**。把咬合覆盖、结构漂移、设计-代码一致性、调谐动作从
`wxg.py` 搬进 `whyexist/gates.py`。

- **`whyexist/gates.py`**：`_feature_bites` / `_required_coverage` / `drift_report` /
  `coverage_report` / `conformance_report` / `reconcile_actions` / `_truncate`。
- **迁移暴露的隐式依赖**：`work_id`（工单段）、`datetime`、`DESIGN_ANCHOR_KINDS`
  都没跟着搬过去，靠全量回归逐个暴露并补上；其中一次替换范围还吞掉了上一轮的
  work re-export，也是回归抓出来的。
- **测试**：273 不变。
- **版本**：契约 `2.14.0` → `2.15.0`；schema 仍为 `9`。
- 边界：导入器、命令处理器、导出/校验/CLI 仍在 `wxg.py`。

## 2.14.0（2026-11-02）

**拆包第五步：feature/条件状态机**。把条件链、代、就绪派生、作用域从 `wxg.py`
搬进 `whyexist/workflow.py`。

- **`whyexist/workflow.py`**：`get_feature` / `ensure_feature` / `condition_rows` /
  `condition_flags` / `current_phase` / `set_condition` / `recompute_ready` /
  `refresh_blocked` / `scope_ids`。
- **测试**：273 不变。
- **版本**：契约 `2.13.0` → `2.14.0`；schema 仍为 `9`。
- 边界：覆盖/漂移/一致性/调谐（`gates.py` 候选）、导入器、命令处理器、导出/校验仍在 `wxg.py`。

## 2.13.0（2026-11-02）

**拆包第四步：工单状态机**。把工单领取、令牌校验、写入边界与证据追加从 `wxg.py`
搬进 `whyexist/work.py`。

- **`whyexist/work.py`**：`work_id` / `get_work` / `get_work_by_token` /
  `insert_work`（含 merge 语义）/ `require_token` / `require_role` /
  `target_match` / `require_targets`（精确集 + 通配前缀）/ `append_evidence`。
- **测试**：273 不变。
- **版本**：契约 `2.12.0` → `2.13.0`；schema 仍为 `9`。
- 边界：feature/条件、导入器、命令处理器、导出/校验仍在 `wxg.py`。

## 2.12.0（2026-11-02）

**拆包第三步：图读写层**。把节点/边/绑定的读写与写入校验从 `wxg.py` 搬进
`whyexist/graph.py`。

- **`whyexist/graph.py`**：`check_kind` / `check_attrs` / `check_node_id`、
  `get_node` / `upsert_node` / `upsert_edge` / `edge_id` / `bind_node`、
  `repo_rows` / `find_repo`。
- **`DESIGN_ANCHOR_KINDS` 移入 `whyexist/contract.py`**：它是契约概念，图读写与导出都用。
- **测试**：273 不变。
- **版本**：契约 `2.11.0` → `2.12.0`；schema 仍为 `9`。
- 边界：状态机、命令处理器、导出/校验仍在 `wxg.py`。

## 2.11.0（2026-11-02）

**拆包第二步：数据库层**。把 schema、连接、后端适配与迁移从 `wxg.py` 搬进
`whyexist/db.py`，`wxg.py` 改为 re-export。

- **`whyexist/db.py`**：`SCHEMA_SQL` / `MYSQL_SCHEMA_SQL` / `PG_SCHEMA_SQL`、连接与
  后端方言（SQLite / MariaDB / PostgreSQL）、`migrate_schema`、`init_db`。
- **`whyexist/contract.py`**：契约桥接——`wxg_contract` 仍在 `scripts/` 根（被 `verify`、
  测试与发布脚本直接引用），包内通过这个桥接拿到它；契约搬进包后桥接消失。
- **迁移方式**：脚本按行范围提取 + 替换为 re-export，`wxg.py` 内调用点不变。
- **测试**：273 不变（拆包不改行为）。
- **版本**：契约 `2.10.0` → `2.11.0`；schema 仍为 `9`。
- 边界：图读写、状态机、命令处理器仍在 `wxg.py`。

## 2.10.0（2026-11-02）

**拆包第一步**。`wxg.py` 已经 4500 行，每个新命令都在加成本。2.10.0 把最独立的三块
搬进 `whyexist` 包，行为不变。

- **`whyexist/errors.py`**：`Reject` 成为全包唯一的异常类；`wxg.py` re-export，
  模块内与旧测试的 `wxg.Reject` 仍可用。
- **`whyexist/jsonio.py`**：`utc_now` / `dumps` / `loads` / `load_json_arg` / `new_token`。
- **`whyexist/temp.py`**：`make_temp_dir` / `temp_dir`（含 Windows 沙箱 DACL 的规避说明）。
- **测试**：273 不变——拆包不改行为，全量回归只用来证明这一点。
- **版本**：契约 `2.9.0` → `2.10.0`；schema 仍为 `9`。
- 边界：`wxg.py` 仍是主实现，拆包只完成基础工具层；命令处理器与状态机尚未迁移。

## 2.9.0（2026-11-02）

**断边集合的总代价**。2.8.0 的 `--advise` 逐条算代价，但真正要断的是一个集合。2.9.0
给 `--break-set` 的每个候选补上整体移除后的代价。

- **`break_set_costs`**：把整个断边集合一起移除，算 `lost_pairs`（失去的可达对数量）
  与 `affected_count`（受影响节点数）。
- **`cycles --break-set` 输出带 `cost`**：每个最小断边集合现在能比出"哪组代价最小"。
- **实测**：httpie 的 6 个 size=3 候选，`lost_pairs` 从 3 到 11；最便宜的是断掉三条
  回流到 `httpie` 根包的边（`cli->httpie`、`cli->output`、`output->httpie`）。
- **测试**：271 → 273（集合代价 2）。
- **版本**：契约 `2.8.0` → `2.9.0`；schema 仍为 `9`。
- 边界：`lost_pairs` 只算可达性，不算功能语义；它给的是"哪组断得更少"，不是"该断哪组"。

## 2.8.0（2026-11-02）

**断边建议**。2.7.0 分别给了"能否破环"和"断了丢多少可达"，2.8.0 把两个维度合起来：
`cycles --advise` 对环内每条边给出 `preferred` / `acceptable` / `avoid` 的建议并排序。

- **`cycles --advise`（新增）**：环内每条边标 `in_break_set`（是否属于某个最小断边集合）
  与 `lost_count`（断它丢多少可达），按建议档位与代价排序。
- **修 `transitive_reachable` 在环图上的 bug**：退化 DFS 分支没有排除起点，导致可达集
  包含自身，进而让断边影响虚高。
- **修 `edge_removal_impact` 的语义**：原先移除全部待断边再比较，现在逐条评估
  "只断这一条"的代价。
- **测试**：267 → 271（advise 3、CLI 1）。
- **版本**：契约 `2.7.0` → `2.8.0`；schema 仍为 `9`。
- 边界：`advise` 逐条评估代价，不评估组合断边的总代价；`in_break_set` 只说明它参与
  某个最小断边集合，不代表断它一条就够。

## 2.7.0（2026-11-02）

**断边的影响分析**。2.6.0 能找出最小断边集合，但回答不了"断掉这条边会不会破坏功能"。
2.7.0 给 `impact` 加 `--remove-edges`：计算断掉依赖后源点失去哪些可达节点。

- **`impact --remove-edges src->dst,...`（新增）**：对比断边前后的传递可达，输出每条边的
  `lost_reachable`（断前可达、断后不可达的节点）；`lost_count` 越大，断它的代价越高。
- **实测**：httpie 断 `cli -> output`，`lost_count` 为 0——因为 cli 仍能经 httpie 到 output，
  说明这条边不是唯一路径；但环也不会因为断它消失（2.5.0 的结论），所以它既非必要也非充分。
- **`requirement_coverage` 抽成公共函数**：节点影响与断边影响共用同一套需求归属判断。
- **测试**：263 → 267（断边失去下游、替代路径不丢可达、叶子边只丢目标、CLI 1）。
- **版本**：契约 `2.6.0` → `2.7.0`；schema 仍为 `9`。
- 边界：`lost_reachable` 只回答"可达性是否丢失"，不回答"功能是否受损"——后者要看语义。

## 2.6.0（2026-11-02）

**最小断边集合**。2.5.0 的 `--without` 要人手动试断；2.6.0 让工具自己枚举：
`cycles --break-set` 按边数从小到大找出能破环的最小依赖边集合。

- **`cycles --break-set`（新增）**：枚举最小反馈弧集，每条候选边带 `x_evidence`；
  边数超过 20 时返回 `truncated`（2^n 枚举不可行）。
- **实测**：httpie 的 3-环断一条不够；最小断边集合大小是 3，共 6 个候选
  （三个双向对各断一个方向，但有些组合断完仍成环）。
- **测试**：256 → 263（break-set 6 个纯函数用例 + 1 个 CLI 用例）。
- **版本**：契约 `2.5.0` → `2.6.0`；schema 仍为 `9`。
- 边界：只保证「边数最少」，不保证「断掉不会破坏功能」；可行性仍要人判断。

## 2.5.0（2026-11-02）

**环的 what-if 分析**。2.4.0 能列出环的成因边，但不能回答"断哪条能破环"。2.5.0 给
`cycles` 加 `--without`：模拟移除指定依赖后的环状态。

- **`cycles --without src->dst,...`（新增）**：剔除指定边后重新算 SCC；输出 `without`
  与剩余环。用来验证"断这条依赖是否足够"，而不是真的改图。
- **实测**：httpie 的 3-环断一条 `cli -> output` 仍在（三个 2-环叠加），断三条
  （`httpie->cli`、`httpie->output`、`cli->output`）才消失。
- **测试**：255 → 256（模拟移除后环消失）。
- **版本**：契约 `2.4.0` → `2.5.0`；schema 仍为 `9`。
- 边界：`--without` 只模拟分析，不写图；它验证"去掉这些边后是否还有环"，不判断去掉是否可行。

## 2.4.0（2026-11-02）

**依赖环的成因追踪**。2.3.0 的 `plan` 能报出强连通分量，但只说"这几个组件成环"。
2.4.0 把环展开成具体依赖边，并追到造成它的文件。

- **`derive --apply` 持久化依赖证据**：depends 边的 `x_evidence` 记录造成它的文件对
  （最多 20 条），环分析据此定位到具体 import。
- **`cycles`（新增）**：把 design 层的 SCC 展开成 `members` + `edges`（带 `evidence`）
  + `self_loops`；只读，不拦截。
- **测试**：246 → 255（cycles 7、CLI 2）。
- **版本**：契约 `2.3.0` → `2.4.0`；schema 仍为 `9`。
- 边界：环内列出的是 SCC 内部全部依赖边，不区分哪几条构成最短环；自环单独列。

## 2.3.0（2026-11-02）

**候选设计的边界清理**。2.2.0 有 `promote`，但重跑 `derive`（换 depth 或 exclude）会把上一轮
的候选留在图里，规划结果被污染。2.3.0 把这件事收干净，并支持排除非设计目录。

- **`derive --exclude`（新增）**：逗号分隔的目录前缀（如 `tests,docs,extras`）不参与分组；
  这些目录不是产品设计单元，混进来只会稀释并行规划。输出 `excluded_nodes`。
- **重跑 `derive` 清理旧候选**：本次推导没再出现的 `origin=derived` 节点标 `stale=1`，
  输出 `stale_derived`；`promote` 后的 `declared` 节点不受影响。
- **`plan` 排除 stale**：旧锚点与过期候选不参与规划，输出 `excluded_stale`。
- **`derive --apply` 写 `repo` 字段**：此前候选节点没有 repo，导致按仓清理失效。
- **测试**：244 → 246（exclude 跳过路径、exclude 过滤 import 依赖）。
- **版本**：契约 `2.2.0` → `2.3.0`；schema 仍为 `9`。
- 边界：stale 只标不删；`derive` 仍只做 package 策略。

## 2.2.0（2026-11-01）

**derived → declared 的显式提升**。2.1.0 用 `origin=derived` 区分"从代码推出来的假设"，
但没有动作把它变成"人裁决过的设计"。2.2.0 补 `promote`：记录谁在什么时候确认过，
不阻塞后续修改。

- **`promote`（新增）**：把 `origin=derived` 的节点提升为 `declared`，写
  `x_promoted_by` / `x_promoted_at`；非 derived 节点直接拒绝。需要 claim_token 与设计角色。
- **边界收紧**：`derived` 与 `declared` 现在有了唯一转换入口；`derive --apply`
  产出的节点必须经 `promote` 才算设计确认。
- **测试**：242 → 244（拒绝非 derived、提升并记录 actor）。
- **版本**：契约 `2.1.0` → `2.2.0`；schema 仍为 `9`。
- 边界：`promote` 只改 origin 与 attrs，不触发重新审计；提升后的节点仍可被 `bite` 判定。

## 2.1.0（2026-11-01）

**从代码反推候选设计**。2.0.0 的编译器全部依赖设计图，但已有仓（尤其是需要重构的仓）
没有设计图。2.1.0 补上 `derive`：按目录把代码聚成 component 候选，用 import 关系推导
depends 候选，写入 `origin=derived`，可被咬合质疑、可在确认后提升为 `declared`。

- **`import-repo`（新增）**：按仓批量导入全部 Python 文件；单文件命令对中型仓不可行
  （httpie 133 个文件）。写入语义与 `import-file` 一致。
- **`derive`（新增）**：`--strategy package` 按目录深度分组；依赖来源有两条——跨组调用边
  与 import 解析（模块间依赖的主要形态）。默认 dry-run，`--apply` 写入 `origin=derived`。
- **unmapped 节点 id 去行号**：旧 id 形如 `@21:len`，代码一移动就整批伪 missing/new；
  现在按名字聚合，行号留在 `line_start/line_end`。
- **`plan` 默认排除 unmapped**：`--include-unmapped` 可看全图并输出 `excluded_unmapped`。
- **`plan` 设计层只保留设计节点**：代码节点混进来会把反链顶到节点数；`design` 层现在只取
  component / port / pattern。
- **`parallelism` 不再被单点自环压成 1**：只有大小 > 1 的 SCC 才阻断并行；自环只让分层不可用。
- **`analyze` 的「有环」与「能分层」对齐**：自环存在时 `layers=null`。
- **测试**：225 → 242（derive 11、import-repo 1、plan 过滤 1、自环 1、CLI 3）。
- **版本**：契约 `2.0.0` → `2.1.0`；schema 仍为 `9`。
- 边界：`derive` 只做 package 策略、不猜组件语义；import 解析只处理绝对 import；
  `derived` 到 `declared` 的硬边界（promote 动作）尚未实现。

## 2.0.0（2026-11-01）

**设计期编译器 2.0**：从"交付门"变成事前可计算、可验证的分解工具。这是 1.x → 2.0 的
总览，逐版细节见下面各条。

- **并行规划**：`plan` 给出 SCC、调度波次、最大反链与理论并行上限；`conflicts` 在声明期
  列出会重叠的写边界。
- **盲执行验证**：`brief` 生成结构性盲化任务书；`blind-check` 校验边界、产出契约与依赖引用，
  给出 PASS/FAIL 与 locality。
- **影响域闭包**：`impact` 输出受影响集、命中的 requirement、`uncovered` 与跨 feature 影响。
- **补丁合并**：`patch` + `apply` 用单一 reducer 替代 `claim_token` 锁；冲突显式、不写半截、
  与顺序无关。
- **产品入口**：`up` 一条命令起步（minimal / standard 模板）；`Engine` 提供只读库 API；
  `legacy` 隔离层把与旧实现的耦合收成一个文件。
- **测试**：224 → 225（`up --template minimal`）。
- **版本**：契约 `1.9.0` → `2.0.0`；schema 仍为 `9`。
- 边界：`wxg.py` 仍是主实现（拆包未完成）；所有新判定都是结构性的，不判断设计语义质量。

## 1.9.0（2026-11-01）

**操作日志 + 单一 reducer**。前几版并行靠 `claim_token` + `target_ids` 互斥：两个代理
不能改同一块，于是那两块只能串行。1.9.0 换成补丁合并——子任务产出补丁，由单一 reducer
合并，冲突在合并阶段显式暴露。

- **`patch`（只读）**：把一次盲执行产出规范成补丁文件（节点按 id 去重、边按三元组排序去重），
  供 `apply` 消费。
- **`apply`（写库）**：合并多个补丁；同一节点被不同补丁以不同内容修改时报告 `conflicts`
  且不写任何东西（事务回滚兜底）；边端点必须存在或由本次补丁新建；`--dry-run` 只报告。
  冲突时退出码 1。
- **`whyexist/reducer.py`**：合并逻辑是纯函数，可单独测；同一节点内容相同只去重、不算冲突；
  结果与补丁顺序无关。
- **测试**：211 → 224（reducer 10、CLI 3：合并、冲突不写、dry-run）。
- **版本**：契约 `1.8.0` → `1.9.0`；schema 仍为 `9`。
- 边界：`apply` 有意绕过 `target_ids` 写边界——它假定自己是单一执行者；冲突只按节点内容
  判定，不检测语义冲突；补丁文件就是操作日志，没有单独的日志表。

## 1.8.0（2026-11-01）

**影响域闭包与声明期冲突检测**。1.7.0 之前，工具能验证"这次执行有没有越界"，但回答不了
"改了这块，还有哪里是意料之外的"。1.8.0 补上影响域与跨 feature 冲突。

- **`impact`（只读）**：输入 feature 与被改动节点，输出反向可达的受影响集、正向可达的依赖集、
  命中的 requirement、连不到任何 requirement 的 `uncovered`（意料之外的影响面），以及落到
  其它 feature 作用域的 `cross_feature`。方向约定：边 `a -> b` 表示 a 依赖 b，改 b 影响 a。
  需求覆盖用全部结构边（satisfies / associates / contains），影响传播只走依赖边。
- **`conflicts`（只读）**：两两检查 feature 的 `target_ids` 写入边界是否可能匹配同一节点，
  输出重叠的模式对与当前图上真正重叠的节点。声明期就能看到"这两个 feature 不能并行改同一块"。
- **`Engine.impact`**：库 API 同步暴露影响域。
- **测试**：185 → 211（impact 9、conflicts 12、CLI 4、Engine 1）。
- **版本**：契约 `1.7.0` → `1.8.0`；schema 仍为 `9`。
- 边界：`impact` 的 `closed` 用无向连通判断，偏宽松（会少报 uncovered）；`conflicts` 只看
  `target_ids` 模式重叠，不看依赖时序（A 依赖 B 的产出时，边界不重叠也不该并行）。

## 1.7.0（2026-11-01）

**可用性：一条命令起步 + 库 API**。前几版的编译器能力都在，但上手要敲十几条命令，
也没法被程序调用。1.7.0 补两个入口。

- **`up`（幂等）**：一条命令完成 init + demo 仓 + demo feature + 第一次 gate 结果，
  可在未初始化的目录直接运行。不自动裁决——gate 只给真实结果（通常 FAIL 并列缺项），
  工单仍要显式领取、提交、审计；重复执行不会重置已有 feature。
- **`Engine` 库 API**：`from whyexist import Engine`，`with Engine(root) as e:` 后可直接
  `plan` / `brief` / `blind_check` / `gate`；只做取数与组装，判定仍在纯函数模块。
- **`legacy` 隔离边界**：新代码不再直接 `import wxg`，全部经由 `whyexist/legacy.py`；
  `wxg.py` 作为脚本运行时把 `__main__` 注册为 `wxg`，避免异常类出现两份。
- **测试**：177 → 185（Engine 6、up CLI 2）。
- **版本**：契约 `1.6.0` → `1.7.0`；schema 仍为 `9`。
- 边界：`up` 只搭骨架，不替你跑完 8 个条件；`Engine` 的底层仍复用既有实现，
  `wxg.py` 仍是主实现，拆包迁移未完成。

## 1.6.0（2026-11-01）

**盲执行验证（`blind-check`）**：1.5.0 能生成盲化任务书，但回答不了"执行者拿到它会不会做对"。
1.6.0 补上结构校验：拿任务书和一次独立执行产出，检查边界、产出契约与依赖引用，给出
PASS/FAIL 与局部化得分。

- **`blind-check`（只读）**：输入工单 id 与产出 JSON（`nodes` / `edges`），输出
  `boundary`（越界节点）、`dependencies`（引用了既不在边界也不在输入契约里的节点）、
  `contract`（产出 kind 不在工单产出契约内、未知 kind、缺 id/kind）三类判定，
  以及 `locality`（从 1.0 起按违规项扣分）与 `verdict`。
- **`brief` 补 `write_patterns`**：任务书同时保留原始通配边界。只展开已存在节点会把
  "允许新建的 id"误判成越界；判定用原始 pattern。
- **产出契约只约束新建节点**：更新边界内已有节点不触发 produces 检查，避免合法更新被误杀。
- **测试**：162 → 177（blind 纯函数 12、CLI 端到端 3）。
- **版本**：契约 `1.5.0` → `1.6.0`；schema 仍为 `9`。
- 边界：`blind-check` 只看结构（边界/契约/依赖），不评价产出语义是否正确；它不替代审计，
  也不能证明切分本身合理——它证明的是"这一次执行没有越界"。

## 1.5.0（2026-11-01）

**设计期编译器（第一块）：并行规划与盲化任务书**。1.4.0 之前，why-exist 只回答"交付有没有证据"；
1.5.0 补上事前那一半——把依赖图变成可计算的并行划分，并生成可独立执行的任务书。

- **`whyexist` 引擎包**：新增 `scripts/whyexist/`（纯标准库）。`graph_algo` 提供 SCC（Kosaraju）、
  拓扑波次（Kahn）、最大反链（Dilworth：最小链覆盖 = n − 二分图最大匹配）与可达闭包；
  `planner`、`briefing` 是纯函数层，不 import 入口脚本，可单独测试。
- **`plan`（只读）**：从 feature 依赖图算强连通分量、调度波次、最大反链与理论并行上限。
  `--level` 支持 `design`（depends）/ `code`（calls,reads,writes）/ `auto`；`auto` 在没有设计边时
  自动退到代码层，并在输出里标明实际层级，避免把"没有依赖信息"误读成"全部可并行"。
  一端在作用域外的依赖边保留下来作为 `dangling` 报告，不再静默丢弃。
- **`brief`（只读）**：生成一张工单的盲化任务书——写入边界、边界外上游输入、该 kind 的产出契约、
  禁止事项与完成定义。结构性盲化：只接收单张工单所需数据，不接收工单列表，因此无法泄露全局计划。
- **测试**：104 → 162（graph_algo 29、planner 10、briefing 12、plan/brief CLI 端到端 7；
  端到端覆盖层级回退、只读、确定性、环检测与未知工单）。
- **版本**：契约 `1.4.0` → `1.5.0`；schema 仍为 `9`。
- 边界：`plan` 的价值取决于图里有没有依赖边，只有扫描图时用 code 层、粒度细且受导入器解析率影响；
  `brief` 只保证结构上不泄露全局计划，不保证切分本身正确——后者要靠盲执行验证（下一版）。

## 1.4.0（2026-11-01）

**让一致性差异少漏一点**：不新增设计描述，只把 1.3.0 的三处盲区补上。

- **唯一名字启发式**：跨文件裸名调用被导入器标成 unmapped 时，若名字在作用域内唯一匹配到
  某个 operation，conformance 临时把它计入“依赖有代码支撑”（`structural.resolved_heuristically`）；
  不写回图，也不用于未声明耦合。
- **代码孤儿**：`anchors.code_orphans` 列出没有被任何 `maps_to` 指向的 operation/classifier；
  只报告，不算 violation。
- **`maps_to` 写入校验**：src 必须是 use_case/component/port，dst 必须带 repo/path；
  错方向、空锚点直接拒绝。
- **测试**：101 → 104（启发式解析、maps_to 校验、code_orphans）。
- **版本**：契约 `1.3.0` → `1.4.0`；schema 仍为 `9`。
- 边界：启发式只在名字唯一时生效，方法调用/重名仍不解析；code_orphans 是清单，不是全覆盖要求。

## 1.3.0（2026-11-01）

**设计-代码一致性（只报差异）**：把“设计节点和代码对不上”从人工看图变成可重复的差异清单，
不新增一套设计描述。

- **`maps_to` 边**：设计节点（use_case/component/port）指向带 repo/path 的代码节点；一条引用边，
  不复制代码结构。
- **`conformance`（只读）**：输出四类差异——`anchors.missing`（设计节点无代码锚点）、
  `structural.missing_backing`（component/port 的 depends 无 calls/reads/writes 支撑）、
  `structural.undeclared`（代码跨组件调用但组件间没有 depends/associates）、
  `tests.missing`（use_case 没有 testcase 的 verifies）。
- **gate 开关**：`feature-declare --conformance` 开启后 gate 对 violations FAIL；`--no-conformance`
  关闭；默认关闭，重声明保留策略，旧 feature 迁移后保持关闭。
- **schema 9**：`features.conformance`（迁移只加列，默认 0）。
- **测试**：98 → 101（conformance 差异报告、gate opt-in、开关保留）。
- **版本**：契约 `1.2.0` → `1.3.0`；schema `8` → `9`。
- 边界：结构检查依赖导入器的 calls/reads/writes，解析不到时偏保守；只覆盖 Python；
  conformance 回答“差异清单是否为空”，不证明语义正确，也不生成描述。

## 1.2.0（2026-10-31）

**PostgreSQL 后端**：网络恢复后补上 PG 支持，三套状态库后端都可用（SQLite 默认 / MariaDB/MySQL / PostgreSQL）。

- **PG 后端**：`WXG_DB_URL=postgresql://...` 或全局 `--db-url` 切到 PostgreSQL；默认仍 SQLite，
  MySQL 路径不变。
- **驱动延迟加载**：PostgreSQL 需要 `pip install 'psycopg[binary]'`；未安装时连接报可读错误，
  不影响 SQLite/MySQL。
- **方言适配**：`PG_SCHEMA_SQL` 用 `BIGSERIAL` 替换 `AUTOINCREMENT`（TEXT 主键、部分唯一索引、
  `ON CONFLICT` 与 SQLite 一致）；`INSERT OR IGNORE` → `ON CONFLICT DO NOTHING`，`?` → `%s`，
  结果用 `psycopg.rows.dict_row`；损坏/完整性错误用 sqlstate `23xxx` 识别。
- **并发领取**：同样的条件 UPDATE + rowcount；PostgreSQL 默认 READ COMMITTED，两进程抢同一张单
  只有一个成功（集成测试覆盖）。
- **测试**：95 → 98（3 个 PG 集成用例：init/scan 全流程、并发 claim、serve --once；需要
  `WXG_TEST_PG_URL`，默认跳过）。
- **版本**：契约 `1.1.0` → `1.2.0`；schema 仍为 `8`（无表结构变更）。
- 边界：PG 后端要求可用的 PostgreSQL 实例，`init` 不建库；不做连接池；psycopg 是唯一新增可选依赖。

## 1.1.0（2026-10-31）

**并行状态库 + 常驻控制器**：状态库从“只有单机 SQLite”扩展为可插拔后端，并补上控制器循环。

- **MySQL/MariaDB 后端**：`WXG_DB_URL=mysql://user:pass@host:3306/db` 或全局 `--db-url`
  切到 MariaDB/MySQL（行级锁、多写者）。默认仍是 SQLite（WAL），现有行为不变。
- **内置纯标准库客户端** `scripts/wxg_mysql.py`：握手 v10、mysql_native_password、AuthSwitch、
  `?` 安全转义、结果类型转换、事务；不需要 pymysql/psycopg 等第三方包。
- **MySQL 方言适配**：独立 `MYSQL_SCHEMA_SQL`（VARCHAR 键列、`AUTO_INCREMENT`、去部分索引、
  `key`/`value` 反引号）；执行层翻译 `INSERT OR IGNORE`、`ON CONFLICT ... DO UPDATE`、
  `excluded.x` 与 `:name` 命名参数。
- **并行领取安全**：`work-claim` 用条件 UPDATE + rowcount 原子领取；MySQL 连接设
  `READ COMMITTED`，避免并发改写触发 1020。两个代理抢同一张单只有一个成功（有集成测试）。
- **常驻控制器**：`serve --interval N [--apply] [--once]` 周期对全部 feature 跑 reconcile；
  `--apply` 仍只做补单/解阻塞/回收陈旧 claim，裁决/咬合/图写入永不自动；`--once` 单趟并输出一行 JSON。
- **测试**：76 → 95（serve 3 个、MySQL 客户端 13 个、MySQL 后端 3 个；后者需要
  `WXG_TEST_MYSQL_URL`，默认跳过；客户端测试在连不上 MariaDB 时整类跳过）。
- **版本**：契约 `1.0.0` → `1.1.0`；schema 仍为 `8`（无表结构变更）。
- 边界：内置客户端只支持 `mysql_native_password`（无 TLS/caching_sha2）；当前版本不内置
  PostgreSQL 后端（需要 psycopg）；`serve` 是单进程循环，不是分布式调度器。

## 1.0.0（2026-10-31）

**收敛约束成为默认**：新 feature 默认开启咬合覆盖门禁（ε=1.0），交付门从“可选检查”变成默认口径。

- **默认覆盖**：`feature-declare` 不给覆盖参数时，新 feature 的 `coverage_epsilon` 默认为 1.0；
  `work-judge(passed)` 与 `gate` 在该阶段推进前执行覆盖检查（公式与参数见契约 coverage 规则）。
- **逃生阀**：`--no-coverage` 显式关闭；显式 `--coverage-epsilon ε` 覆盖默认值；两者互斥。
- **重声明语义**：不给覆盖参数时保留已有策略；迁移后的旧 feature 保持 NULL（不强制），
  只有新声明才默认开启。
- `feature-status` / `coverage` 始终输出 enforced、epsilon、n_required，gate 输出 coverage 明细。
- **测试**：73 → 76（新 feature 默认 coverage、--no-coverage 与互斥、重声明保留策略）。
- **版本**：契约 `0.9.0` → `1.0.0`；schema 仍为 `8`。
- **破坏性（语义）**：新 feature 默认被 coverage 门禁约束；不想被拦的调用方需显式 `--no-coverage`。
  大作用域下 ε=1 的 n_required 随 S 增长，建议拆 feature 或调 ε。

## 0.9.0（2026-10-31）

**回扫断言**：代码删除/改名不再静默留在图里。重扫产生存活事实，交付门能看到并拦截。

- **`sync`（只读）**：重新解析登记仓的 Python 文件，对比 DB 图输出
  `missing`（DB 有、代码无）/`new`（代码有、DB 无）/`changed`（行号或名称变化）/
  `stale`（已标 stale）与 `parse_errors`，`--limit` 截断；不写库。
- **stale 标记**：schema 8 新增 `nodes.stale`。`import-file` 写同一文件时，同 repo+path 下
  本次未再出现的旧节点标 `stale=1`，再次出现清 0；`--prepare` 把该文件已有旧节点并入
  scan 工单 target_ids，保证标记不越出写入边界。
- **gate**：作用域内 `stale=1` 的节点直接 FAIL（“回扫发现已不存在的代码节点”）。
- `feature-status` / `reconcile` 输出 stale 列表与 `stale-node` 动作。
- **测试**：70 → 73（重扫标 stale 与恢复、sync missing/new 只读、sync 未登记仓报错）。
- **schema 7 → 8**：`nodes.stale`（迁移只加列，默认 0）。契约 `0.8.0` → `0.9.0`。
- 非破坏性：新列有默认值；`sync` 是新增只读命令。

## 0.8.0（2026-10-31）

**变更集**：交付后改设计不再整链重跑——新代只重置受影响的设计条件，上游条件按上一代继承，
并自动派发下游工单（含 implement-test/observe）。

- **`change-open`**：只在 feature **Ready** 后可用；`--from-condition` 之前的条件继承为真
  （reason 标“继承自第 N 代”），从它起及其下游重置为假，开启 generation+1；`changes` 表记录
  from/to generation 与继承边界；自动 `work-seed` 下游工单。一个 feature 同时只允许一个未收口变更集。
- **`change-diff`**：只读对比两代工单 `evidence_ids` 写过的节点集合，输出 added/removed/kept、
  继承与待办条件、带 repo/path 的代码锚点；不存节点内容快照，不是字段级 diff。
- **证据语义**：变更新代需要重新登记 BehaviorPassed 的 evidence，旧代证据不满足。
- **doctor**：新增 `change-generation` / `change-from-condition` / `change-conditions-missing` /
  `change-inheritance` 检查，核对 changes 记录与继承条件是否一致。
- **feature-status**：输出 `changes` 列表。
- **测试**：64 → 70（change-open 需 Ready、继承与下游派单、未收口拒绝、diff 节点集合与锚点、
  从行为条件继承、doctor 继承漂移）。
- **schema 6 → 7**：新增 `changes` 表（迁移只建表）。契约 `0.7.0` → `0.8.0`。
- 非破坏性：`change-open`/`change-diff` 是新增命令；既有 feature 不受影响。

## 0.7.0（2026-10-31）

**从命令驱动到控制器单步**：新增 `reconcile`，把“期望 vs 观测”的调谐变成幂等、可干跑的单步动作清单；
补上陈旧 claim 的回收依据与施工中标记。

- **控制器单步**：`wxg reconcile --feature F [--apply] [--claim-ttl 秒]`
  - 默认只读、幂等；输出动作清单：`seed-ticket`、`unblock`、`release-stale-claim`、
    `retry`、`coverage-gap`、`drift-over-limit`、`construction-open`。
  - `converged` = gate PASS 且无待办；退出码 0（已收敛）/ 1（有待办）/ 2（错误）。
  - `--apply` 只做三类安全迁移：补缺失工单、解 blocked、回收超过 TTL 的 claimed 工单
    （清 token/assignee/claimed_by 并回 ready）。裁决、咬合、图写入、导出永不自动。
- **claim 时间戳**：schema 6 新增 `work_items.claimed_at`，`work-claim` 写入；旧库迁移时
  claimed 行按 created_at 回填（只是下界，无法还原真实领取时间）。
- **WAL**：`connect()` 显式 `journal_mode=WAL` + `busy_timeout=5000`，多进程短写排队；
  单写者语义不变，跨主机共享状态库仍不支持。
- **施工中标记**：新增 `construction` 布尔 attr（component/classifier/operation）；
  gate 遇到未清除标记直接 FAIL；清标记 = 一次不含该键的 `upsert-node` 覆盖；标记不参与咬合/覆盖。
  `feature-status` 与 `gate` 输出 `constructions`；`doctor` 新增 `claim-missing-timestamp`。
- **测试**：57 → 64（reconcile 只读/幂等/补单/回收/解阻塞、claim 时间戳与 WAL、
  施工标记拦门与清除、construction 类型校验）。
- **schema 5 → 6**：`work_items.claimed_at`（迁移只加列）。契约 `0.6.0` → `0.7.0`。
- 非破坏性：`reconcile` 是新增命令；`construction` 是新增可选 attr；WAL 对现有命令透明。

## 0.6.0（2026-10-31）

**中大型仓的性能与门禁补齐**：把大仓扫描从超线性拉回可控，并让“结构对不上代码”这一侧的咬合可以真正拦门。

- **结构漂移门禁（可选）**：`feature-declare --drift-limit N` 开启后，`gate` 统计作用域内当前代
  最新判决为 `UNMAPPED`/`DOC-ONLY` 的节点数，超过 N 判 FAIL；未开启时 gate/status 仍输出
  `drift` 计数。对应新增不变量 I16。
- **大仓扫描性能**：
  - `require_targets` 预分成“精确集合 + 通配前缀”，从 O(nodes × patterns) 降到
    O(nodes × 前缀数)；120 文件 / 7.7k 节点的写入实测 20.06s → 16.74s。
  - `import-file` 不再把扫描节点 id 追加进 `evidence_ids`（原先每文件重序列化整个 list，
    是 O(N²) 的主要来源）。
  - `work-claim --brief` 只返回切片计数；`slice --limit` / `find --limit` 截断并带
    `total`/`truncated`，避免整仓切片的 MB 级 JSON 塞爆代理上下文。
- **applies 边方向校验**：`upsert-edge` 强制 `applies` 的 src 只能是
  component/classifier/operation、dst 只能是 pattern；`doctor` 对旧边新增 `applies-invalid`。
- **coverage 调度修正**：`coverage.next` 改为条件顺序里第一个未达标阶段（阶段不能跳着推进），
  调度索引只用于预算分配。
- **schema 4 → 5**：`features.drift_limit`（迁移只加列，默认 NULL = 不强制）。
- **测试**：50 → 57（drift 门禁与阈值、drift 参数校验、applies 方向、find/slice 限量、
  work-claim --brief、coverage.next 顺序、扫描不写 evidence_ids）。
- 版本：契约 `0.5.0` → `0.6.0`，schema `4` → `5`。非破坏性：新增字段/开关默认关闭；
  `applies` 校验只拒绝本就非法的边。

## 0.5.0（2026-10-31）

**产品级设计约束版本**：把“咬合能否收敛”从流程约定变成可计算状态，并把设计模式纳入设计图谱与交付门。
契约与 schema 均有行为变更。

- **咬合计费化（breaking）**：gate 按**每个节点当前代最新一条** bite 计判决；最新为
  UNNECESSARY/HOLLOW 即 FAIL；KEEP 只反证**同一节点**，跨节点或旧代 KEEP 不再抵消。
  （此前一个 KEEP 可抵消作用域内全部 UNNECESSARY/HOLLOW。）
- **失败历史一等化**：新增 `judge_history` 表（schema 4），每次 `work-judge`（passed/failed）
  写入裁决、理由、actor、时间，只增不删；`judge(passed)` 清空该工单陈旧 `fail_reason`；
  `doctor` 新增 `judge-history-*` 检查。
- **设计模式有限应用**：新增 `pattern` 节点 kind 与 `applies` 边（设计元素 → 模式）。gate 要求
  作用域内每个 pattern 有非空 `applicability`/`not_applicable`，且至少被一条 `applies` 挂到
  component/classifier/operation；04 架构导出包含作用域内 pattern 行。新增
  `references/patterns.md`（16 个模式的适用/不适用/代价/替代与建模示例）。
- **抽样与阶段**：`sample` 新增 `--feature`（按 feature 作用域抽样，与 `--repo` 二选一）；
  `bite` 记录 `generation` 与 `phase`（当前第一个未满足的条件），供覆盖统计使用。
- **覆盖与调度（可选门禁）**：新增 `coverage` 只读命令，按“未覆盖节点 × 后验缺陷率”
  计算各阶段 `covered`/`n_required`/`met` 与调度索引 `α^(i-1)·p`；`feature-declare
  --coverage-epsilon <ε>` 开启后，`work-judge(passed)` 与 `gate` 强制该阶段覆盖达标。
  默认参数 ε=1.0、先验 p=0.1（Beta(1,9)）、α=2；未开启只报告不拦截。
- **doctor**：新增 pattern 必填字段检查（`pattern-unjustified`）；`feature-status` 增加
  `judge_history` 与 `coverage` 汇总。
- **schema 3 → 4**：新增 `features.coverage_epsilon`、`bites.generation`/`phase`、
  `judge_history` 表。迁移只加列/表：旧 bites 按升级时 feature 当前代回填 generation（更早代
  无法还原）；旧裁决按 `judged_by` 回填 `judge_history`（幂等，`jh:<work_item_id>`）。
- **测试**：42 → 50（新增最新判决/KEEP 绑定、失败历史与 stale reason、feature 作用域抽样、
  bite 阶段、coverage 强制与默认值、pattern 必填与挂载、pattern 04 导出）。
- **文档**：`references/patterns.md` 新增；`SKILL.md`/`README`/`design.md`/`quality.md`
  同步工作流、边界与质量门。
- 版本：契约 `0.4.1` → `0.5.0`，schema `3` → `4`。
- **破坏性变更**：跨节点 KEEP 不再抵消 UNNECESSARY/HOLLOW；pattern 缺必填字段或未挂载会
  使 gate FAIL；coverage 需显式开启（默认不强制）。

## 0.4.1（2026-10-30）

**仅测试修复，无功能与 schema 行为变更。** Windows 上 `tempfile` 的根可能返回 8.3 短路径
（如 `C:\Users\RUNNER~1\AppData\Local\Temp`），`test_role_prompt_uses_real_root` 用短路径字符串
与 `role-prompt` 解析出的长路径比较，在 GitHub Actions 的 windows runner 上必失败（ubuntu 不复现）。
测试夹具改为 `Path(...).resolve()` 后再断言，其余用例不变。

- 契约版本 `0.4.0` → `0.4.1`（版本号随发布推进；schema 仍为 `3`，命令与行为无变化）。
- CI 六格（ubuntu-latest / windows-latest × Python 3.10/3.12/3.13）全绿；`verify` 与 42 个用例标准不变。
- 发布资产与 0.4.0 的内容差异仅限测试文件与版本号。

## 0.4.0（2026-10-29）

**首个对外发布版本（initial release）**。来自对 0.3.0 的"文档描述 vs 实现"一致性审计
（本技能自我审计 + E2E 复现）。本版修掉削弱交付门可信度的路径，并把文档里绝对化但未被
强制的规则变成代码约束：

- **门禁条件不可被旁路**：移除 `feature-register --true`。同代登记不写条件；新建 feature 或
  显式 `--generation` 开新代时只写 Accepted（新代会重置条件并 supersede 旧代工单、清 token），
  并回写 requirement 节点正文。`work-claim` 只发**当前 generation** 的 ready 工单。
  `feature-declare` 仍只置 Accepted 并在新建时自动 seed。
- **BehaviorPassed 需要同代证据**：`evidence` 新增 `generation` 列（schema 3）；`work-judge(passed)`
  要求 feature **同 generation** 且 `exit_code=0` 的 evidence；`gate` 执行同一检查；`doctor`
  新增 `behavior-passed-without-evidence`。重新声明后旧代证据不再满足新代 BehaviorPassed。
- **封死 attrs.bite 伪造**：`upsert-node` / 图写入拒绝 `attrs.bite`；该键只由 `bite` 命令写；
  `gate` 只采信 `bites` 表（含 actor），不再用节点 attr 兜底。
- **scan 等无对应条件的工单** judge(failed) 不再清空全部条件（尤其不再清 Accepted）。
- **init 幂等**：旧库迁移只在补列时执行一次，且跳过 audit 工单；已迁移库重复 `init`
  零写入（修复 0.3.0 把 fresh audit 工单 `claimed_by` 改成 `legacy` 的问题）。
- **doctor 可追溯**：新增 `legacy-identity` 检查，落实契约里"doctor 提示 legacy 不可追溯"。
- **DSH Windows 沙箱可用**：新增 `make_temp_dir()`，Windows 用默认 mode 建临时目录，
  规避 `tempfile` 的 0o700 目录 DACL 为空的问题（DSH discussion #4290）；
  `verify`/`gen_sample`/测试在 DSH 沙箱内可直接运行。
- **契约形状收口**：命令表"写入"列改为 `WRITE_MODES` 显式声明（`verify` 检查覆盖）；
  `07-数据流.md` 的"请求参数"表进入 `EXPORT_FILES.extra_sections`；导出文件名从契约读取。
- **可用性**：quick start 补 `work-open` 扩 target_ids 步骤与证据前置说明；`role-prompt`
  输出真实状态库/CLI 路径，audit 提示改为直接 work-judge；`repo-add --language` 只接受
  `python` 并说明导入器边界；`@文件` 支持扩展到 `--target-ids`/`--node-ids`/`--ids`；
  `@文件`缺失与 repo 登记冲突返回可读 error 而非 traceback；`gate` FAIL 退出码改为 1。
- **文档纠偏**：I3/I5/I7、GATE_RULES、AUDIT_RULES、quality.md 的绝对化措辞改为准确表述；
  `verify` 的覆盖范围写清楚（生成视图/样例，不替代 doctor 与行为测试）；`sample` 覆盖
  仓内所有节点；Python 导入器对未知裸名调用按 I7 建 unmapped 节点/边。
- **测试**：19 → 42（新增 0.4.0 回归 23 个，含迁移回填、缺库保护、链式调用 unmapped、导出 `|` 转义、declare 保真、证据产物校验）。
- **schema**：`2` → `3`（`evidence.generation` 列；迁移优先按证据关联工单的 generation 回填，
  关联工单不存在（悬空引用）时同样回退到 feature 当前代回填，不删行）。注意：0.3 的旧 evidence
  没有 generation 信息，无法还原真实代；若升级前存在跨代证据，升级后请在新代重新登记 evidence。
- 版本：契约 `0.3.0` → `0.4.0`。
- **破坏性变更**：`feature-register --true` 移除；`gate` FAIL 退出码 1；BehaviorPassed
  裁决需先登记**同代** evidence；旧脚本里用 `--true` 置条件的做法不再可用。

## 0.3.0（2026-10-29）

来自 student-course-system 实战审计：gate/证据可以复现，但审计身份与证据溯源不可验证，
finalize 重跑会追加咬合并改写权威证据。本版把这些变成契约约束：

- **actor 可追溯**：`work-claim` / `work-judge` / `bite` 必须带 `--actor`（或 `WXG_ACTOR`）；
  写 `work_items.claimed_by`、`work_items.judged_by`、`work_items.judged_at`、`bites.actor`。
- **审计独立**：`work-judge` 的 actor 不能等于被审工单的 `claimed_by`；旧库迁移把未知身份
  标成 `legacy` 而不是伪造成员，并在返回里带 `legacy_claim`。
- **证据一等化**：新增 `evidence-record` / `evidence-list`，登记 feature、work、命令、退出码、
  actor、产物路径与 SHA-256；`doctor` 检查证据产物缺失/被篡改、非零退出码、关联工单缺失。
- **导出参数去重**：05/07 的参数、测试、断言按 id 去重，07 同一参数只列一次。
- **schema 迁移**：schema 1 → 2，`init` 非破坏地补 `claimed_by`/`judged_by`/`judged_at`
  与 `evidence` 表；旧 `passed/failed` 行标 `legacy`，不删除业务行。
- **兼容性**：调用 `work-claim` / `work-judge` / `bite` 的旧脚本必须补 `--actor`，或设置
  `WXG_ACTOR` 环境变量；否则退出码 2。旧库先跑一次 `init` 再使用 0.3.0。
- 契约版本 0.2.0 → 0.3.0；测试 14 → 19，新增 actor 独立性、证据登记/篡改检测、
  导出参数去重、0.2→0.3 迁移、contract --json 可序列化用例。
- 新增 `references/quality.md` 提交质量门；`verify` 检查该文件存在。

## 0.2.0（2026-10-29）

针对 calculator-demo 实测暴露的问题：

- **重导入不再覆盖设计标注**：`import-file` 写节点时使用 attrs 合并（`merge_attrs=True`），
  observe/scan 重扫只刷新扫描自有属性，保留 `duty`、`x_note`、`x_*` 等设计角色写入的标注。
- **悬空引用清理**：`retract` 级联删除对应 `bites`，并从工单 `target_ids` / `evidence_ids`
  里剔除已删节点；`scope_ids` 只收现存节点，`slice` 会展开 `前缀*` 通配并只报告真正缺失的 id。
- **gate 不再把已删节点的咬合当证据**：忽略这类 bite，并在输出里给 `ignored_dangling_bites`。
- **token 生命周期**：`work-finish` 与 `work-judge(passed)` 清空 `claim_token`。
- **新增 `doctor`**：检查悬空 bite/边/引用、陈旧 token、条件完整性与审计配对；
  `doctor --fix` 只清理悬空引用和陈旧 token，不替人裁决；输出 `by_check`/`truncated`
  避免长列表被截断，并同步 `meta.contract_version`。退出码：干净 0，有问题 1。
- 契约版本 0.2.0；schema 版本仍为 1（无表结构变更）。
- 测试从 9 个增加到 14 个，新增覆盖 attrs 合并、retract 清理、gate 悬空咬合、slice 通配、token 清理。

## 0.1.0（2026-10-28）

首个 DSH 原生版本：单技能 + SQLite 图库 + 8 条件工单状态机 + 导出视图 + `verify` 契约自检。
