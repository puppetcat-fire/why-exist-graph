# why-exist-graph 行为契约审计汇总

- 契约卡：16 份
- 覆盖模块：97 个；公开入口：300 个
- 契约条目：592 条 —— covered 206，gap 197，partial 189
- 分区判定：152 项 —— refactor_in_place 65，keep 49，rewrite 22，freeze 16

## 每片概览

| # | 切片 | 模块 | 入口 | 契约 | covered | partial | gap | verdict |
|---|---|---|---|---|---|---|---|---|
| 01 | 01-cli-skeleton | 6 | 15 | 38 | 20 | 9 | 9 | freeze:1 keep:2 refactor_in_place:2 rewrite:1 |
| 02 | 02-contract-commands | 9 | 55 | 24 | 8 | 6 | 10 | keep:4 refactor_in_place:3 rewrite:3 |
| 03 | 03-contract-rules | 2 | 12 | 32 | 9 | 9 | 14 | freeze:1 keep:2 refactor_in_place:4 |
| 04 | 04-db-schema | 6 | 11 | 25 | 4 | 7 | 14 | freeze:1 refactor_in_place:5 rewrite:2 |
| 05 | 05-db-backends | 9 | 17 | 24 | 9 | 5 | 10 | keep:2 refactor_in_place:6 rewrite:3 |
| 06 | 06-graph-core | 3 | 13 | 35 | 15 | 12 | 8 | keep:1 refactor_in_place:1 rewrite:1 |
| 07 | 07-query-import | 3 | 14 | 38 | 4 | 19 | 15 | freeze:3 keep:1 refactor_in_place:3 |
| 08 | 08-cmd-repo | 2 | 18 | 39 | 10 | 13 | 16 | freeze:1 keep:2 refactor_in_place:5 rewrite:2 |
| 09 | 09-cmd-feature | 3 | 22 | 38 | 10 | 17 | 11 | freeze:3 keep:6 refactor_in_place:7 rewrite:3 |
| 10 | 10-cmd-gates | 3 | 19 | 38 | 21 | 7 | 10 | keep:1 refactor_in_place:2 rewrite:1 |
| 11 | 11-cmd-graph | 2 | 21 | 28 | 5 | 11 | 12 | freeze:1 refactor_in_place:4 rewrite:1 |
| 12 | 12-cmd-misc | 2 | 10 | 49 | 2 | 22 | 25 | freeze:1 keep:3 refactor_in_place:4 rewrite:1 |
| 13 | 13-cmd-compiler | 5 | 25 | 75 | 33 | 23 | 19 | freeze:1 keep:3 refactor_in_place:5 rewrite:1 |
| 14 | 14-work-flow | 5 | 21 | 35 | 18 | 11 | 6 | keep:2 refactor_in_place:3 |
| 15 | 15-tests-baseline | 16 | 11 | 56 | 36 | 12 | 8 | keep:13 refactor_in_place:2 rewrite:2 |
| 16 | 16-docs-release | 21 | 16 | 18 | 2 | 6 | 10 | freeze:3 keep:7 refactor_in_place:9 rewrite:1 |

## 分区判定（按模块）

| # | 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|---|
| 01 | scripts/whyexist/errors.py | keep | 13 行、一个异常类、语义清楚；跨层捕获的“只有一份类”约束由 wxg.py 的 __main__ 注册兜住，本身没有可改的空间。 | 几乎没有。唯一危险是未来有人给它加字段/factory，破坏 100+ 处 except Reject 的假设。 |
| 01 | scripts/whyexist/jsonio.py | keep | 6 个函数、12 个直接单测、输出格式被断言钉死（dumps 定形态、token 定长度，utc_now 只钉了结尾 Z）。实现足够短，重写不会更好；需要的是补 utc_now 格式与 load_json_arg 空串两条断言，不是换实现。 | dumps 的 sort_keys 是错误 JSON 与 serve 摘要的既定格式；换实现（例如改 indent 或 ensure_ascii）会让快照类断言和人工 diff 全变。 |
| 02 | scripts/whyexist/commands_misc.py::cmd_verify（L269-352） | keep | 它是本切片契约的执行器，有 drift 与 zero-side-effect 两个测试，逻辑直白。 | 盲点：只查注册→handler，不查孤儿 handler；改契约字段时必须同步这里，否则 verify 会给出虚假安全感。 |
| 02 | scripts/whyexist/commands_compiler.py::cmd_apply（L259-295） | keep | 实现简单、三个测试覆盖成功/冲突/dry-run；无 token 是文档化的单一执行者例外，不是实现缺陷。 | 例外只写在 SKILL.md:450，契约与 help 未表达；任何人顺手补 token 都会改变并行合并模型的语义。 |
| 02 | scripts/whyexist/commands_feature.py（work-claim/finish/judge 的 token 链路） | keep | 状态机与原子领取清楚，claim/actor/独立性/supersede/evidence 都有测试。 | work-judge 的 audit-id 分支无测试；改 claimed_at/token 清理会牵动 doctor 与 reconcile。 |
| 02 | scripts/whyexist/work.py（require_token/require_role/require_targets） | keep | 小、纯、有单测；是 token 语义的唯一权威实现。 | require_role 依赖调用方传对命令名（import-repo 传了 import-file）；修调用点即可，不必改这里。 |
| 03 | scripts/wxg_contract.py（L269-637：COMMANDS 命令表） | keep | 50 条命令、123 个选项、19 个标志的单一定义，CLI 由它生成，verify 强制每个命令有处理器与 WRITE_MODES 条目，端到端测试实际走这些参数。合同清楚、无重复实现。 | 没有任何检查确认处理器真的读了声明的选项（feature-declare 的 5 个参数走 getattr，verify 看不见）；可选参数不进生成文档的"关键参数"列，新增可选参数容易只在 argparse help 里可见。 |
| 03 | scripts/wxg_contract.py（L640-691：WRITE_MODES） | keep | 键集由 verify 与 test 双重锁定，值是给人看的短句，改动的可观察后果只是文档措辞。 | 13 种自由文本取值无枚举，值写错（例如把只读命令写成"状态库"）不会有任何检查失败；与行为脱钩的声明只能靠审阅。 |
| 05 | scripts/wxg_mysql.py | keep | 全切片唯一“契约清楚 + 测试真实”的部分：12 个客户端用例在真实 MariaDB 12.3 上全过，协议子集与已知边界写在文件头 wxg_mysql.py:19-27，不引入第三方依赖是有意设计。 | 它是自制数据库驱动：无 TLS、无 caching_sha2、无多结果集、无重连、超时固定 5s；MySQL 8 默认认证插件下直接不可用。要保持 keep 就必须把“仅 MariaDB/native 认证”写进对外文档，并停止在这份客户端上扩功能。 |
| 05 | tests/test_wxg_mysql.py | keep | 覆盖到位且能真跑：类型转换、? 转义、rowcount、事务、并发写、大文本、百分号凭据、AuthSwitch（伪造包）、close 幂等。是这次审计里唯一能立刻复现的证据来源。 | 只在有 MariaDB 时运行（连不上整类 skip），CI 仍会静默跳过；多包（>16MB）读写与 LOAD DATA 中止路径没有用例。 |
| 06 | scripts/whyexist/graph_algo.py | keep | 纯函数、零内部依赖、零 DB；30 个测试覆盖归一化/SCC/分层/反链/可达/analyze 的主要分支与边界（空图、自环、双环分量、重复边、确定性）；契约以输入输出类型表达，容易继续加测。 | 它的函数同时出现在 whyexist.__init__ 的 __all__ 里，删改签名会连带影响 planner/cycles/impact 与包级 API；reachable 是死代码，删除前要确认没有任何外部使用者（当前仓库内无生产调用）。 |
| 07 | scripts/whyexist/derive.py | keep | 本切片最干净的模块：纯函数、140 行、15 个直接测试覆盖分组/排除/边来源/证据/空仓，输出结构与文档一致；没有 I/O 与全局状态，契约可以用输入输出类型完整表达。 | 它的输入依赖外部约定的 (src,dst) 元组与文件相对路径；depth<=0 的语义没写进文档（现在等价于全部目录，不是报错）。任何改动必须保持 components/depends/excluded_nodes 的键名与排序，否则 conformance 的 x_evidence 与 verify_reports 的断言会连带失败。 |
| 08 | scripts/whyexist/derive.py | keep | 纯函数、无 I/O、15 个单测覆盖分组/depends/exclude/证据；职责单一，契约清楚。 | 低；import 解析不在这个模块，跨文件依赖仍受 commands_repo 的 _import_file_pairs 限制。 |
| 08 | scripts/whyexist/commands_repo.py:sample | keep | 25 行只读抽样，feature/repo 二选一与 seed 语义清楚，有端到端测试。 | 低；只需改未登记 repo 的错误文案，不必动抽样逻辑。 |
| 09 | scripts/whyexist/commands_feature.py::work-open（496-504） | keep | 只做合并委托，行为窄；除死校验外没有结构问题 | merge 的拒绝条件在 work.py:46-47；放宽会让 submitted/passed 单被改写 |
| 09 | scripts/whyexist/commands_feature.py::work-claim（507-561） | keep | 原子 UPDATE+rowcount 与 token 字段清楚，claim/actor/独立性有测试；slice 形状属 07 切片冻结项 | 跨 feature 选择、--brief 全量 target_ids、并发只在 MySQL 测试（默认 skip）三个契约还没定；改动会波及 agent 提示词 |
| 09 | scripts/whyexist/commands_feature.py::work-finish（564-582） | keep | token 生命周期、submitted、audit 单 id 拼法都有测试；没有 role 校验但当前与 ROLES 等价 | audit id 被 doctor/role-prompt 引用；改拼接会留下孤儿工单 |
| 09 | scripts/whyexist/commands_feature.py::record_judge_history（601-617） | keep | 唯一写入口、列与契约一致、有历史测试 | id 格式 jh:<uuid> 无断言；迁移回填用 jh:<work_item_id>，两种格式并存 |
| 09 | scripts/whyexist/work.py | keep | 薄原语、单一权威；require_* 与 target_match 语义清楚 | require_role 依赖调用方传对命令名（import-repo 传 import-file 是 02 切片的问题） |
| 09 | scripts/whyexist/workflow.py | keep | 条件链/Ready/作用域的唯一实现，被本切片与 gate/reconcile 共用 | condition_flags 对条件行不齐直接 Reject，决定 feature-list/status 的 all-or-nothing 行为；scope_ids 的通配展开决定 coverage/drift 分母 |
| 10 | scripts/whyexist/evidence.py | keep | 35 行、单一职责、契约清楚（同代+exit0+产物有效）；sha256 有单测，evidence_qualifies 由 gate/judge 三条测试间接锁定。没有可回收的重复实现（doctor 的重复在别的切片，应改为调用它）。 | 直接重写最容易丢掉两个隐式边界：artifact_path 为空也算有效、artifact_sha256 为空时跳过 hash 校验。改前应把 probe P10 的矩阵固化成单测。 |
| 12 | scripts/whyexist/commands_misc.py:cmd_role_prompt（207-247） | keep | 纯字符串拼装、无 I/O、已有 audit/scan 两条端到端断言；契约（角色→允许命令）由 ROLES 单点驱动。 | 唯一的真风险是 token 明文与后端不感知，这两个是产品决策，不是实现烂；动它要同时改测试与文档。 |
| 12 | scripts/gen_sample.py | keep | 确定性 fixture，直接复用 cmd_export 而不是另写一套渲染；verify 与 README 的刷新流程都依赖它。 | 它调用 wxg.cmd_export（依赖 sys.modules['wxg'] 注册），改 wxg.py 的注册方式会同时影响 verify 的样例自检。 |
| 12 | references/export-sample/feat-demo/*.md | keep | 生成产物，由 gen_sample --write 刷新、verify 比对；不应手改。 | 导出排序/格式一变就必须整组重生成，否则 verify 立刻红。 |
| 13 | scripts/whyexist/impact.py | keep | 纯函数、确定性、15 条测试覆盖闭包/跳数/断边/覆盖；模块只是被命令层用得不够严谨，问题不在模块本身。 | requirement_ids 由调用方传全图 requirement，模块语义是“任意 requirement”；若未来要在模块内做 feature 内闭环，需要同时改 commands_compiler 与 Engine.impact。 |
| 13 | scripts/whyexist/cycles.py:1-31,176-285（find_cycles / cycle_shape / cycle_guidance） | keep | SCC 展开、自环单列、形态与 guidance 都是纯函数，10 条测试覆盖，输出被 SKILL.md:376 引用且没有未验证分支。 | find_cycles 对 SCC 内部边“全列出”是保守但可解释的选择；若改成只列构成具体环的边，测试 test_cycles.py:26-32 的断言（4 条边）会失效。 |
| 13 | scripts/whyexist/conflicts.py | keep | 80 行纯函数，12 条测试，重叠语义（仅尾部 *）与 work/scope 的匹配规则一致；没有未验证分支。 | 匹配规则是第 6 份拷贝；若抽公共匹配函数，必须保证 conflicts 的“精确模式视作非通配”语义不被改掉（tests/test_conflicts.py:29-33）。 |
| 14 | scripts/whyexist/briefing.py | keep | 契约最清楚的一块：纯函数、零 IO、15 个键被测试锁死、边界/输入/产出三条语义各有正反用例，另有 CLI 与 Engine 两条端到端覆盖。确定性承诺与固定文案是唯二没锁的部分，加一条顺序敏感测试即可，不需要动实现。 | 低。真正的风险在外部：commands_compiler._brief_payload 传的是 loads 过的 target_ids 子集（只给 id/role/kind/target_ids），若重写时把接受字段换成 work 整行，会悄悄改变对 _brief_payload 的隐式契约。 |
| 14 | scripts/whyexist/blind.py | keep | 12 条单元测试覆盖三类判定与 locality 趋势，纯函数、边界清楚，是切片里测试密度最高的一块。省略 known kinds 时的退化、inputs 不可作产出、locality 精确值三条属于文档缺口而不是实现缺陷，补测试与注释即可。 | 低到中。若判定规则收紧（例如把 inputs 当合法产出、或强制 known kinds），会改变 PASS/FAIL 语义，而 apply/patch 流程还没有把 blind-check 作为硬门，外部消费者只在 Engine 与 CLI 两处。 |
| 15 | tests/test_wxg.py | keep | 85 条、335 断言，覆盖 37 条命令与全部门禁语义；20 条只读性断言（库哈希/整库快照）是项目最硬的安全网，变异 M4 被它杀掉 | 单文件 1895 行、夹具与断言混写；verify 用例依赖 copytree 整树，仓库变大会慢或挂 |
| 15 | tests/test_plan_cli.py | keep | 39 条覆盖 plan/brief/blind/apply/impact/cycles/conflicts/up；plan 的 12 表快照是不可替代的只读证明 | 48 s 的 subprocess 开销；up 在 gate FAIL 时仍退 0 只被隐式断言 |
| 15 | tests/test_package_units.py | keep | 87 条、134 断言直接打内存库；方言翻译、工单状态机、coverage 数学、conformance 报告在重写时是秒级反馈 | 方言翻译只有字符串断言；与私有符号（_required_coverage、SCHEMA_SQL）强耦合 |
| 15 | tests/test_graph_algo.py | keep | 30 条纯函数，空图/自环/双环/顺序无关/确定性边界齐全，运行 0.002 s | 无大图或性能用例，O(n^2) 退化不会被发现 |
| 15 | tests/test_planner.py | keep | 13 条锁层级选择、并行度与 bottleneck 文案，重写 planner 时可直接对照 | bottleneck 只断言中文子串（第 85-101 行），改措辞会误报回归 |
| 15 | tests/test_cycles.py | keep | 25 条覆盖环、断边集、建议排序、形状与 guidance，含 truncated 边界 | 2^n 枚举的上限只测了一条；改断边策略会连带改多条断言 |
| 15 | tests/test_impact.py | keep | 15 条覆盖闭包/跳数/断边/跨 feature，纯函数且确定 | CLI 侧只断言 affected/closed，cross_feature 与 depends_on 无 CLI 用例 |
| 15 | tests/test_derive.py | keep | 15 条覆盖分组键、跨组 depends、排除目录、文件依赖，重写 derive 可先跑它 | depth<=0 语义与 Windows 分隔符只有各一条 |
| 15 | tests/test_briefing.py | keep | 12 条锁死盲化键集（15 键）与输入判定，是 blind 契约的一半 | 字段顺序、文案、--out 未测 |
| 15 | tests/test_blind.py | keep | 12 条覆盖 PASS/FAIL 三类判定、locality 单调性、空产出 | locality 精确值与 known kinds 省略未测 |
| 15 | tests/test_reducer.py | keep | 10 条覆盖去重、指纹冲突、跨补丁端点、交换律 | 指纹范围（repo/path/unmapped）与边 kind 合法性未测 |
| 15 | tests/test_conflicts.py | keep | 12 条锁通配重叠语义，纯函数、0.002 s | 只有尾部 * 一种通配，语义收紧会改多项目标 |
| 15 | tests/test_engine.py | keep | 7 条锁 README 承诺的 Python API 入口（from whyexist import Engine） | 只测 gate FAIL、close 后重连；Engine 与 CLI 的等价性只覆盖 5 个方法 |
| 16 | references/contract.md | keep | 纯生成物，verify 逐字节比对；内容完整且与代码一致（本次 verify PASS） | 手工改会被下次 contract --write 覆盖；这是特性不是缺陷 |
| 16 | references/patterns.md | keep | 内容是 gate 对 pattern 的强制口径（applicability/not_applicable/applies）的说明，与代码一致；只在标题里带了一个过时的 0.5.0 标签 | 无测试约束措辞；与 gate 实现漂移时只能靠人读发现 |
| 16 | references/export-sample/feat-demo/ | keep | 确定性夹具，本次重生成 6/6 字节一致，verify 每次都会重跑；它同时也是导出格式（含 frontmatter 头）的唯一事实标准 | 格式细节（表头文案、frontmatter 字段）只存在于样例里，没有契约条目；改导出器必须同时刷新样例，否则 verify 红 |
| 16 | tools/verify_release.py | keep | 本次对 dist/v2.92.0 实跑 PASS；断言的是“包能独立跑”这个真正重要的性质，而不是文件清单 | 收尾会删 <系统临时>/demo-repo（root 之外）；按 mtime 选最新包在多版本并存时不稳 |
| 16 | tools/doc_flow.py | keep | 它是“文档承诺 vs 实现”的唯一自动化 oracle，本次 PASS；按 SKILL 原样跑而不是按测试的正确顺序跑，这个设计值得保留 | 它硬编码了最短路径步骤，SKILL 改流程就得同步改它；不能进发布包（依赖 whyexist.temp 与源码仓结构） |
| 16 | tools/verify_reports.py | keep | 6 条交叉断言抓的是命令之间自相矛盾，本次 preflight 里 PASS；它是唯一验证“多个只读命令说法一致”的地方 | 依赖具体输出字段名（plan.level/bottleneck、conformance 的 orphan 计数），字段改名会静默变成 skip 而不是报错 |
| 16 | VERSION + CHANGELOG.md | keep | CHANGELOG 是 113 次迭代唯一的完整记录，格式被 check_docs 与 publish_github 双向依赖；VERSION 是三个工具的唯一锚点 | 两者与 CONTRACT_VERSION/测试硬编码构成 5 处副本，任何一处漏改都靠 check_docs 兜底，而 check_docs 不在 CI 里 |
| 01 | scripts/whyexist/cli.py | refactor_in_place | 对外契约最密（退出码 6 条映射、stdout/stderr 分流、needs_db 零副作用）且大部分有精确测试；烂在实现：connect 在兜底外、needs_db 硬编码、两套 JSON 风格、死 --json。形状保留、边界重画，不需要推倒。 | 退出码被 CI（ci.yml:28 的 verify）、测试夹具（test_wxg.py:61-83 先解析 stdout 再退到 stderr）和 agent 提示词共同依赖；改动若只跑全量测试不看契约表，容易把 1/2 的语义悄悄对调。 |
| 01 | scripts/whyexist/__init__.py | refactor_in_place | Engine 的库 API 有独立测试（tests/test_engine.py 走真实库），公开面本身合理；但 __version__ 是漂移的假信息，且 __init__ 顶层 import 会把 db/commands/contract 全部拉进来。删版本常量、明确“包导入不做 IO”，是原地改而不是重写。 | __version__ 虽无人读，但“读包版本”是外部用户最自然的动作；删除前要确认没有发布脚本依赖（tools/ 里无引用）。顶层 import 改懒加载会让 `from whyexist import Engine` 的行为在 import 期副作用上变化，需要确认 engine 的测试不依赖 import 即建连（它不建连）。 |
| 02 | scripts/wxg_contract.py（P/O/F/C + COMMANDS，L269-637） | refactor_in_place | 唯一契约源，50/50 handler 对齐、verify 与测试覆盖结构完整性；但 help 有真实漂移、写模式无枚举、P/token 是死字段。 | 任何字段改名都会同时改 contract --json、SKILL.md/contract.md 的生成字节与导出样例；必须先加新字段、后删旧字段。 |
| 02 | scripts/wxg_contract.py（渲染器/contract_json，L786-1031） | refactor_in_place | 输出是字节级契约，逻辑清楚；缺陷集中在 _cmd_params 只列必填项，导致生成文档漏关键参数。 | 高：verify 逐字节比较，任何排版变化都会让 CI 红；必须与文档再生成同一次提交。 |
| 02 | scripts/whyexist/cli.py（parser 生成 + 分派 + 退出码） | refactor_in_place | 结构简单、主路径有测试；问题是无契约的 needs_db 硬编码、退出码 if 链、--db-url 直接改进程 env。 | 退出码是 CI 语义（gate/verify/doctor/apply/reconcile），改动会静默改变调用方判断；env 副作用可能影响同进程的 Engine。 |
| 03 | scripts/wxg_contract.py（L17-265：版本号、条件、kind、判决、规则表、ROLES） | refactor_in_place | 枚举型常量（CONDITIONS/CONDITION_TO_KIND/WORK_KINDS/NODE_KINDS/EDGE_KINDS/BIND_EDGE_KIND/BITE_VERDICTS/GATE_FAIL_VERDICTS/DRIFT_VERDICTS/EVIDENCE_REQUIRED_CONDITIONS/COVERAGE_DEFAULTS/RECONCILE_DEFAULTS/ROLES/PRODUCT_CODE_ROLES）都有真实消费点且被测试间接固定，可直接原地改。但同一文件里混着三类东西：被消费的枚举、零消费的 TOKEN_COMMANDS、纯文字的规则表；需要拆开，删掉死常量。 | 删 TOKEN_COMMANDS 是对外可 import 名字的移除（包级 API），要先确认外部没有 import；规则表文本是已发布文档内容，改动会改变 SKILL.md/contract.md 的字节，必须 --write 后重跑 verify。 |
| 03 | scripts/wxg_contract.py（L695-750：ATTR_SCHEMA / COMMON_ATTRS / EXPORT_FILES / EXPORT_RULE） | refactor_in_place | ATTR_SCHEMA 是唯一被强执行的属性契约（graph.check_attrs），但它把类型语义藏在 'str'/'int'/'bool'/'任意' 四个魔法字符串里，靠另一个模块解释；COMMON_ATTRS 与 EXPORT_RULE 没有消费者；EXPORT_FILES 被按下标取用。行为清楚，实现该收口。 | 改 ATTR_SCHEMA 会直接影响所有写图命令（upsert-node、import-file、feature-declare 的 requirement 写入）与导入器；收紧类型可能拒绝既有扫描数据。EXPORT_FILES 重排会让 export 内容错位而 verify 仍通过（样例与实现同源）。 |
| 03 | scripts/wxg_contract.py（L780-1058：渲染、contract_json、块替换、version line） | refactor_in_place | 渲染逻辑本身简单（纯字符串拼接），但块替换是 verify 漂移检测的地基，现有实现有四个未声明的行为：write_text 会做平台换行转换（Windows 下整文件变 CRLF，与 .gitattributes 的 eol=lf 冲突）、只处理第一对标记、比较时 strip 首尾换行、未知 section 抛 KeyError 而非统一错误。 | 这是本切片风险最高的一段：verify 是唯一防文档漂移的机制。收紧比较（真逐字节）会让现有文件立刻失败；修 write_text 换行会改变已提交文档的字节；只处理第一对标记的行为一旦有人依赖，改动会改变 --write 的语义。 |
| 03 | scripts/whyexist/contract.py（DESIGN_ANCHOR_KINDS 桥接） | refactor_in_place | 文件自述是过渡桥接（"等契约本身搬进包内，这个桥接就消失"），而 DESIGN_ANCHOR_KINDS 是被 graph.py 校验 maps_to 方向的真正契约常量，却没进契约文件、没进生成文档。这是契约单一来源的直接破口。 | 搬动会影响 graph.upsert_edge 的 maps_to 校验与 conformance 的锚点判定；如果只搬常量不通读计划，容易在契约文件里再定义一份、形成第三次重复。 |
| 04 | scripts/whyexist/db.py（SCHEMA_SQL，L19-150） | refactor_in_place | 表/列形状是既成公共契约（外部 why-exist-uml 直接按列名读 nodes/edges/features/feature_nodes/work_items；references/contract.md 记录了 evidence/judge_history 的列语义），且 40 多个契约版本里 schema 只升到 9、一直只做加列/加表。可以原地补索引、补文档、补 CHECK 的新表；不能改名/删列 | SQLite 加外键/CHECK 需要重建表并搬数据，等于一次 schema 手术；任何列改名会同时打断外部只读消费者与所有旧库迁移 |
| 04 | scripts/whyexist/db.py（MYSQL_SCHEMA_SQL / PG_SCHEMA_SQL，L154-289） | refactor_in_place | 表与列同样是硬契约，只能原地演进；坏的是三份手抄 DDL 只能人肉同步（PG 版还是 SQLite 版的字符串 replace）。方言适配层（L292-422 的 wrapper 与 SQL 翻译）不在本片，归 05 片（其判定：翻译层 rewrite、wrapper refactor_in_place）。本地 MariaDB 12.3.3 与 PG 16.15 实跑建表成功 | 改列名会同时打断 SQLite 迁移与两个后端的新建库；CREATE INDEX IF NOT EXISTS 与 LONGTEXT 默认值在 MySQL 8 上会拒建（未验证），动手前要先定支持面 |
| 04 | scripts/whyexist/db.py（connect / ensure_db / init_db，L441-465、468-483、605-616） | refactor_in_place | 契约简单且大部分有测试（缺库不建、WAL、init 幂等）。坏的是边界：ensure_db 只看 meta 表、连接异常在 CLI 兜底之外、init_db 自带 commit。局部改签名/加校验即可，不需要换实现 | ensure_db 一旦变严（校验版本/列），所有旧库会从「静默 OperationalError」变成「直接拒绝」，需要同时给出手动迁移路径；init_db 的内嵌 commit 是「报错但已落库」的根源，改动会改变退出码语义 |
| 04 | scripts/whyexist/commands_repo.py（cmd_init，L44-59） | refactor_in_place | 输出形状简单、有测试（schema_version），坏点只有两处未导入的全局名（db_url、re）。原地修 import 与脱敏正则即可 | 修好后 mysql/pg init 才开始真正返回 backend/db 字段；这两个后端从「没跑通过」变成「可用」，会暴露迁移里未验证的 SQL（尤其 F7） |
| 04 | scripts/whyexist/cli.py（连接时机与 commit 边界，L62-93） | refactor_in_place | 与 01 片对 cli.py 的判定一致：契约密、大部分有断言。本片关心的两点是 connect 在 try 之外、以及 commit 只有一次，两者都只需移动/补充分支，不涉及重写 | 把 connect 挪进 try 会改变现存的 traceback+1 行为（01 片 C11 记录的就是它），下游若靠退出码区分「环境错」与「业务拒绝」需要一起改 |
| 05 | scripts/whyexist/db.py:154-289（MYSQL_SCHEMA_SQL、PG_SCHEMA_SQL） | refactor_in_place | 表与列是对外契约（迁移、doctor、导出都依赖），不能整块重写；但三份手抄 schema 只能靠人肉同步，PG 版还是字符串 .replace 派生。改成单一 schema 模型生成三种 DDL，或至少加一条断言三后端表/列集合一致的测试。 | MYSQL_SCHEMA_SQL 用了 MariaDB 扩展（CREATE INDEX IF NOT EXISTS、TEXT/LONGTEXT 字面量 DEFAULT），MySQL 8 上大概率建表失败；改结构前必须先定“支持 MariaDB 还是也支持 MySQL 8”。 |
| 05 | scripts/whyexist/db.py:323-397（_MySQLConnection、_PgConnection） | refactor_in_place | 薄适配层思路正确，契约也简单（sqlite3 子集），但缺 executemany 直接打断产品写入路径，且没有测试断言这个子集。补方法 + 加一条「对包装层跑一遍 sqlite 子集」的测试即可，不需要推翻。 | 补齐时容易顺手加 cursor()/row_factory 等产品不用的 API，扩大维护面；子集边界要写进注释并配测试，否则下次还会漏。 |
| 05 | scripts/whyexist/db.py:441-616（connect、ensure_db、_table_columns、migrate_schema、init_db） | refactor_in_place | 迁移语义（非破坏、只迁一次、legacy 回填）是这块最值钱的契约，且 sqlite 上有完整测试；问题在方言分支散落三处、迁移 SQL 里混了 MySQL 不兼容的 \|\| 拼接。收成一个后端接口 + 方言常量即可，行为保持。 | migrate_schema 的 rowcount 计数在 MySQL 是 modified rows，会改变 migrated 的数值；任何“顺手统一”都可能改掉测试断言的返回形状。 |
| 05 | scripts/whyexist/cli.py:55-70（后端选择与连接时序） | refactor_in_place | 逻辑很短，但 connect() 落在 try 之外，导致四种后端连接失败全部变成 traceback；--db-url 直接写 os.environ 也是在这里定的。把连接移进 try、把 URL 作为参数传递即可，不需要重写整个 CLI。 | 把连接移进 try 会改变 gate/doctor 之外的失败输出形态（现在是 traceback + 1），下游若有脚本依赖退出码 1 会受影响。 |
| 05 | tests/test_mysql_backend.py 与 tests/test_pg_backend.py | refactor_in_place | 它们写的正是该有的端到端契约（init→repo→feature→prepare→claim→write→judge→gate→doctor、并发 claim、serve --once），但 skipUnless + CI 无数据库 ⇒ 永远绿。不需要重写，需要让它们真的跑起来。 | 两个 setUpClass 都是破坏性的（清空目标库所有表 / DROP SCHEMA public），接进 CI 必须用一次性容器，否则会清掉开发者本机库。 |
| 05 | scripts/wxg.py:31-49（db 内部符号 re-export） | refactor_in_place | 这层是给旧测试的兼容垫片，但现在 16 个符号里只有 connect/init_db 有消费者（gen_sample.py），其余 grep 零命中。删到只剩实际使用面，注释写明删除条件。 | 可能有仓外脚本按 wxg._mysql_translate 这类私有名访问；删之前先在 dist 与文档里搜一遍引用。 |
| 06 | scripts/whyexist/graph.py | refactor_in_place | 写入契约大体清楚（kind/id/attrs/applies/maps_to 都有测试），但校验只覆盖 20 种边里的 2 种、edge id 无校验、attrs 覆盖/合并双语义与 stale/unmapped 复位都是隐式行为；调用方有 9 个包内模块，整模块重写最容易丢掉这些没人写下来的细节。 | 收紧校验会改变 gate/doctor/conformance 看到的图内容（例如给 depends 加端点 kind 校验会拒掉现存测试和外部图库）；改动 attrs 合并策略会直接丢设计角色手写的 duty/x_note。 |
| 07 | scripts/whyexist/query.py | refactor_in_place | 三个只读命令的边界很小、输出键被 work-claim 直接复用，原地改比重写安全；但实现里有 5 个独立缺陷值得一次修掉：LIKE 未转义、slice/get/find 节点形状不一致、depth 常量、两套截断逻辑、通配未命中静默。 | 统一节点形状（attrs_json -> attrs）会改变 work-claim 返回的 slice 字段，agent 侧提示词与外部脚本可能按 attrs_json 解析；转义 LIKE 会让现在把 % 当通配用的调用方行为变化。修之前先补 C2/C5/C6/C9/C11/C12 的行为测试。 |
| 07 | scripts/whyexist/importer.py | refactor_in_place | 不是屎山：单函数、纯内存、无全局状态、节点 payload 字段稳定、unmapped 聚合规则有注释与测试，属于"可扩展但有洞"的资产。要补的是护栏而不是重写：重复类名 KeyError、非 UTF-8 崩溃、缺 reads/imports/inherits/嵌套函数、不校验扩展名。 | 任何解析增强都会改变节点集合，进而改变 stale/missing 漂移与 plan 的计数（导入器的 unmapped 占比在真实仓上是 50~58%，见 CHANGELOG 实测）；同时要保证 id 规则不变，否则旧库整批失效。 |
| 07 | scripts/whyexist/commands_repo.py::_import_file_pairs（derive 的 import 解析） | refactor_in_place | 44 行纯函数、4 个相对/绝对导入测试，行为边界清楚；问题是它长在命令层、与 importer 分成两套 AST 解析与两套错误策略。正确动作是挪进 importer 并复用同一次文件读取，而不是重写解析规则。 | 相对导入规则（from . / from .. / from . import x）是 derive depends 的主要来源，规则一动 depends 全变；跳过点目录与 errors="replace" 的宽容策略若改成严格，会让一部分仓在 derive 时直接失败。 |
| 08 | scripts/whyexist/commands_repo.py:init | refactor_in_place | SQLite 行为清楚且有迁移/幂等测试；只需补回 re/db_url 导入并加一条非 SQLite 测试。 | 中；init 是所有后端的入口，改错会直接让状态库不可用。 |
| 08 | scripts/whyexist/commands_repo.py:repo-add/repo-list | refactor_in_place | repo-add 的 upsert 语义清楚；修 _is_integrity_error 导入、补 id 校验与冲突测试即可。repo-list 只有 2 行，原样保留。 | 中；path 唯一约束与已有仓重新指向会改变后续 find_repo 的归属。 |
| 08 | scripts/whyexist/commands_repo.py:import-file/import-repo | refactor_in_place | 写入语义清楚且核心路径有测试，但 prepare/write 两套循环重复、点目录规则与 sync 分叉、解析错误策略不一致、输出不对称、写库忽略 --feature。适合合并成一个导入引擎，而不是推倒重来。 | 高；import 是所有工作流的入口，涉及大仓性能、stale 语义与 token 边界，改错会污染全图。 |
| 08 | scripts/whyexist/commands_repo.py:promote | refactor_in_place | derived→declared 与审计痕迹语义清楚，2 个测试覆盖主路径；需补 token.feature_id == --feature 校验、拒绝 stale 节点、补越界/缺 actor 测试。 | 中；跨 feature 提升会把节点塞进另一个 feature 的作用域，gate/coverage 都会跟着变。 |
| 08 | scripts/whyexist/commands_repo.py:sync | refactor_in_place | 只读、核心报告有测试；但文件集与 import-repo 不一致、无语言检查、parse_errors 未测试。抽一个共享的“枚举仓内 Python 文件”函数即可。 | 低；只读命令，改错只影响报告，不影响状态库。 |
| 09 | scripts/whyexist/commands_feature.py::feature-declare（43-137） | refactor_in_place | 契约基本清楚且 coverage/conformance 策略有测试，但策略解析与两套 SQL 缠在一起，参数校验分支无测试 | 策略字段被 gate/judge/status 读取，改持久化分支会影响旧库与 export 样例；先补 C1/C2 校验测试 |
| 09 | scripts/whyexist/commands_feature.py::feature-register（140-232） | refactor_in_place | 三个分支返回键不一致、与 declare 重复写 features/conditions；coverage 关闭是隐式行为，需要显式策略矩阵 | 代际推进与 token 清理牵动 doctor 的 conditions 校验与旧代工单；改错会让新代领到旧单 |
| 09 | scripts/whyexist/commands_feature.py::feature-status（248-338） | refactor_in_place | 输出字段集是最大公开面，但实现里有 N+1、重复循环、evidence 不分代、token 泄漏四个独立问题 | 字段集必须 freeze（tools/verify_reports.py:224-227 消费 scope_size，agent 提示消费 phase/conditions）；改 bite 过滤会改 gate 语义 |
| 09 | scripts/whyexist/commands_feature.py::change-open（341-396） | refactor_in_place | 核心流程有 6 个测试，但死字段 affected_json、全局 id 命名空间、重复条件插入需要一并修 | doctor 依赖 changes 行与继承条件（commands_misc.py:468-494）；改 id 规则会破坏已有库的变更集 |
| 09 | scripts/whyexist/commands_feature.py::work_seed（456-489） | refactor_in_place | 依赖链是状态机核心，逻辑小但边界多（继承条件无单、prev 只在 passed 时设、双写状态），适合原地收拢并补链形状测试 | declare/change-open/reconcile/serve 四处复用；改链规则会改变工单 id 与代际语义 |
| 09 | scripts/whyexist/commands_feature.py::work-judge（620-705） | refactor_in_place | 本切片最复杂的状态机，双 id、legacy 放行、COALESCE、两段 UPDATE 复制；主路径测试够，支路（audit-id、legacy）没有 | 状态转移表是 gate/doctor/serve 的输入，改动会静默改交付判定；先把转移表冻结再重构内部 |
| 09 | scripts/whyexist/commands_feature.py::_require_write（717-720） | refactor_in_place | 归属错位：定义在 feature 切片，被 graph/repo 命令导入；应移到 work.py 与其原语同处 | 低；但要同步改 commands_graph.py:11、commands_repo.py:664 与 wxg.py:120 的 re-export |
| 10 | scripts/whyexist/gates.py | refactor_in_place | 四套 bite 选择、构造/返扫双扫描、分母不一致、悬空漂移都必须原地收敛；但每个报告字段都有测试或 probe 钉住（x_evidence 免检、derived orphan 拆分、唯一名启发式、stage 顺序），重写会静默丢边界。先把四套选择抽成一个函数并明确「跨 feature / 全局 / 悬空」三种语义，再动实现。 | 收敛选择逻辑会改变 gate/coverage/drift 三处输出，可能让原本 FAIL 的库变 PASS 或反之；没有回归基线的用户升级后无法解释结果变化。改前需要给 C4/C5/C17 各补反例测试。 |
| 10 | scripts/whyexist/commands_gates.py | refactor_in_place | gate 的九级判定链是产品核心，失败优先级与输出键已被 20+ 条测试固定，不能重写；但文件里混着 dead re-export、重复构造/返扫、双重 enforced 赋值、无用的 import time、未读的 args.json。应原地删兼容层、把判定链抽成有序的检查表（name + 函数 + reason 模板），保持输出逐字节兼容。 | 抽检查表时如果顺手「修正」优先级或 reason 文案，会破 test_gate_checks_report_each_item 与所有断言 reason 关键字的测试；删除 re-export 前要确认外部 shell 不 import 这些名字（仓内已确认，仓外不可知）。 |
| 11 | scripts/whyexist/commands_graph.py:20-55（upsert-node/upsert-edge/bind 处理器） | refactor_in_place | 编排很薄（校验字段 → require_targets → 调 graph 原语 → 追加 evidence_ids），输出形状与错误可观察；问题在它选择的调用参数（merge_attrs=False、payload 直通）和鉴权来源，不在流程本身。 | 改覆盖/合并参数会立刻改变导入节点与设计角色手写 attrs 的存亡（对应 06-graph-core 的 C7/C8）；改校验（例如校验 bind_to 的 kind）会拒掉现存图库与测试；必须先补 C6/C9/C11/C12 的行为测试再动。 |
| 11 | scripts/whyexist/commands_graph.py:109-141（cmd_bite） | refactor_in_place | 核心契约清楚且有测试（判决集、actor、历史追加、phase/generation），gate/coverage 都在读它的产出；缺的是 target 边界、--feature 扩作用域、unmapped 粘滞这三处补丁级问题。 | 给它加 claim_token/target 边界会改掉现有的「任何人都能咬」工作流（SKILL.md:53、357 都按无 token 写）；清 unmapped 或改 --feature 的 feature_nodes 写入，会改变 plan/conformance/coverage 的输入集合——这是本切片里最容易被当成「顺手修」而改坏门禁的地方。 |
| 11 | scripts/whyexist/commands_graph.py:144-206（evidence-record/evidence-list） | refactor_in_place | 写一条记录 + 列一张表，行为边界清楚；需要补的是 exit_code/artifact 的组合校验、work 归属之外的工单状态校验，以及把 SELECT * 换成显式列。 | evidence 列已被 doctor/gate/export 读取，list 输出又被外部脚本当 JSON API 用；改列名或去掉列会静默破坏消费方。generation 从 --work 继承的语义（旧代补证）必须保留。 |
| 11 | scripts/whyexist/commands_graph.py:11 + scripts/whyexist/commands_feature.py:717-720（鉴权依赖） | refactor_in_place | 图写入不应该依赖 feature 模块的私有函数；鉴权应下沉到 work.py 并与 commands_repo 的内联实现合并成单一入口。 | _require_write、require_token、require_role 都在 wxg.py 的 re-export 面上（wxg.py:83-93, 120）；移动/改名会破坏测试与可能的包级 API 使用；需同步 facade 并接受一次 import 顺序调整。 |
| 12 | scripts/whyexist/commands_misc.py:cmd_verify（269-352） | refactor_in_place | 契约清楚、行为安全（只读、临时目录自清理），九类检查各自独立；但只有 main 块漂移与零副作用有测试，checks 名单是手写常量，full 块的修复提示指错路径。适合保留骨架、补测试、把“逐字节”改成真实字节或改文档。 | 收紧成真字节比较会让当前 CRLF 工作树与两份文档立刻失败；改 checks 名单会改 stdout 契约；拆检查函数会动到 CLI 端到端。 |
| 12 | scripts/whyexist/commands_misc.py:doctor_report（355-555） | refactor_in_place | 只读、意图清楚（32 类一致性检查），但 24 类无测试、check 名无枚举、没有 kind/verdict/attrs 校验。适合按检查项拆函数并逐项加 fixture，而不是重写语义。 | 新增枚举/属性检查会让历史上用 SQL 直改的库突然变红；拆函数时容易改变 issue 字段形状，下游测试和 by_check 统计都依赖它们。 |
| 12 | scripts/whyexist/commands_misc.py:cmd_export（22-194） | refactor_in_place | 行为边界清楚（六份视图、作用域可枚举），但实现把六段遍历写在一个函数里、按下标取 EXPORT_FILES、无 ORDER BY、不清理旧文件、非原子。适合抽成“作用域查询 + 六个 projection”并补作用域/顺序测试。 | 改排序会改导出字节与 references/export-sample；改作用域会影响 verify 样例与用户已有导出；目录清理若默认删除会误删手工产物。 |
| 12 | scripts/whyexist/commands_misc.py:cmd_contract（250-262） | refactor_in_place | 20 行、职责单一；但 --write 零测试，CRLF、相对路径、缺标记、--json 静默忽略都是未声明行为，且错误提示不可读。补测试与明确路径解析即可，不值得重写。 | 固定 LF 会改已提交文档字节；把 --write 限制在白名单文件会破坏 HANDOFF 里“任意 --write”的用法。 |
| 13 | scripts/whyexist/planner.py | refactor_in_place | 契约清楚（层级选择、bottleneck 文案、dangling 三键），纯函数、有 13 条函数级测试，不值得重写；但必须先修空节点集崩溃（planner.py:114-118），并把 design kind 过滤与 code 层计数语义写进契约。 | bottleneck 是中文人读文案，测试按子串断言（tests/test_planner.py:85-97）；改文案会连带改测试与 SKILL.md:366。plan JSON 被 Engine 与导出样例消费，键改名会漂移。 |
| 13 | scripts/whyexist/commands_compiler.py：plan/brief/blind-check 部分 | refactor_in_place | CLI 只是取数+组装，命令边界清楚；主要问题是与 Engine 重复、--out 分支无测试、错误分类（OSError→2）没写进契约。 | plan 的 hint 与 excluded_* 是文档明确承诺的字段（SKILL.md:366、README.md:44）；修 hint 逻辑要同步删掉 commands_compiler.py:64 的字面量。 |
| 13 | scripts/whyexist/commands_compiler.py：cycles 部分 | refactor_in_place | 取数与 evidence 组装无问题；必须修 --without 与 --break-set/--advise 的组合语义（commands_compiler.py:189-230），并把 truncated/10 组上限做成显式契约。 | break_sets 的嵌套形状（edges[] 里再带 evidence，cost 只留两个键）已被 SKILL.md:376 与 README:55 引用，改结构会破坏文档与 test_plan_cli.py:803-819。 |
| 13 | scripts/whyexist/commands_compiler.py：patch 部分 | refactor_in_place | 只有 20 行，行为简单：读文件→normalize→写文件。问题只是没校验 --work、错误分支无测试。 | 补丁文件被 SKILL.md:450 定义为“操作日志”；如果加校验（要求 work 存在且 claimed），会让离线出补丁的用法失效。 |
| 13 | scripts/whyexist/commands_compiler.py：impact/conflicts 部分 | refactor_in_place | 两段都是薄壳，域逻辑在纯函数里且测试较足；需要修的是壳层语义：--changed/--remove-edges 互斥、--remove-edges 端点校验、conflicts 的 status/世代过滤写清楚。 | impact 的 closed 是“连到任意 requirement”（跨 feature），改成 feature 内闭环会改变调用方对交付门的预期；conflicts 加 status 过滤会让历史工单边界不再报警。 |
| 14 | scripts/whyexist/reducer.py | refactor_in_place | 归约的对外形状（ok/conflicts/unknown_endpoints/nodes/edges、顺序无关）已有 10 条测试锁住，但冲突指纹只看 kind/name/attrs，丢掉了 upsert_node 实际会写的 repo/path/symbol/line_*/origin/unmapped，于是同一节点被两个补丁写到不同代码锚点时静默取第一份；merge 也不校验 kind 合法性，把失败推迟到写库阶段。这两处要在原地改，不能整块重写：冲突检测的语义被 apply 的 ok 直接消费。 | 中。扩大指纹会改变哪些输入算冲突（现有测试里 test_identical_node_content_is_not_a_conflict 依赖 attrs 等值判定）；若同时引入 kind 校验，apply 的失败点会从写库前移到归约期，退出码仍是 1/2，但 reports 字段会变。 |
| 14 | scripts/whyexist/work.py | refactor_in_place | 公开函数的承诺大多被 17 条单元测试覆盖（work_id/target_match/require_targets/require_role/require_token/insert_work/append_evidence），但实现里有三类硬伤：同一匹配规则四种写法、insert_work 非 merge 分支静默重置 depends_on（无生产调用点）、require_targets 对非字符串 id 抛 AttributeError。它也不该继续叫「工单状态机」——领取/提交/裁决都在命令层。建议保留函数名（wxg.py 与 4 个命令模块依赖它们），把匹配逻辑抽成单一 helper，把 insert_work 的两个分支收敛成一个显式参数。 | 中。require_token 的错误文案被 test_wxg.py:1371 以子串依赖；insert_work 的 merge 白名单决定 work-open/reconcile/import 三条路径能否扩边界，改宽改窄都会改 lead 的行为。 |
| 14 | scripts/whyexist/workflow.py | refactor_in_place | 条件链语义清楚且有 9 条直接测试 + judge/declare 端到端，但它是「状态读取层」而不是驱动者：set_condition 无行时静默、recompute_ready 返回 0 或 True（JSON 里 ready 变成 0 或 true）、多一行未知条件就永远出不了 Ready、scope_ids 顺序随哈希种子变。这些都是在原地能修的行为细节；真正该做的是把「一次裁决如何迁移条件」收敛成一个显式转移函数，供 work-judge 与 change-open 共用。 | 中到高。recompute_ready 的返回值类型动一下就会改 work-judge 的 JSON 形状；scope_ids 被 7 个模块的约 20 个调用点消费，任何排序或去重规则的改动都会在 plan/gate/export/status 里体现。没有测试锁住顺序，属于「改了没人拦」的区域。 |
| 15 | tests/test_wxg_mysql.py | refactor_in_place | 13 条覆盖协议细节（类型、转义、rowcount、事务、并发写、大文本、百分号凭据、AuthSwitch），质量高且本机可跑 | 依赖本机 MariaDB；无库时静默降级为 1 条 skip，CI 里等于不存在。应改显式开关 + CI service |
| 15 | .github/workflows/ci.yml | refactor_in_place | 流程本身正确（verify + unittest，2 OS × 3 Python），只是拿不到当前测试集 | 仓库只跟踪 25 个文件，15/16 个测试文件与 scripts/whyexist/ 全部未提交；不先修版本控制，CI 绿与当前代码无关 |
| 16 | README.md | refactor_in_place | 结构、特性清单与已知边界本身仍然准确（逐条对照 50 命令与测试后没发现虚构能力），错的只有数字与版本：2.67.0、79 个用例、181 行 | 这些数字没有机器校验，改完还会再烂；必须同时把 README 纳入 check_docs，否则只修一次等于没修 |
| 16 | SKILL.md | refactor_in_place | 正文（快速开始、26 条工作流、24 条边界）与实际行为一致，且被 doc_flow 端到端验证；问题在 frontmatter 描述只覆盖 38/50 个能力，plan/brief/blind-check/impact/cycles 等迭代出来的核心能力在模型侧不可发现 | 契约块是生成物不能手改；描述文案若改成“生成”需要新的渲染器与 verify 分支，改动会触及 I1 |
| 16 | docs/HANDOFF.md | refactor_in_place | 结构对路（当前状态/能力地图/验证/顺序/边界/下一步），但验证章节的第一条命令指向不存在的 refactor-lab/run_all.py，版本写 2.91.0，design.md 写 109 节（实际 110） | “下一步方向”四条是唯一成文的未完成需求，重写时容易丢；应保留原意只换失效引用 |
| 16 | docs/PRODUCT-PLAN.md | refactor_in_place | 它是唯一写“产品定位与不做清单”的文档，四条命题仍成立；但进度表停在 2.67.0/dist/v2.67.0，P6 声称的 refactor-lab 三个脚本不存在，且 §8“不做非 Python 导入器”与 HANDOFF 的“最大缺口”互相矛盾 | “明确不做”的条目一旦被改，会反向影响是否该做多语言导入器这个最大的路线判断，需要产品决策而不是编辑 |
| 16 | tools/build_release.py | refactor_in_place | 确定性打包已实测可复现（重建 SHA 相同）、版本校验到位；缺的是 manifest 里没有 commit、也不检查工作树是否干净，导致产物不可追溯 | 加 commit 字段会让所有历史 manifest 的字段集不一致；加 clean-tree 检查会让当前这套未提交工作流无法打包 |
| 16 | tools/preflight.py | refactor_in_place | 六步串联有效（本次实跑 PASS，381 用例 183s），但 docstring 与步骤不符、清理 <tmp>/demo-repo 越界、且不检查 README/HANDOFF 这类最常漂移的文档 | 它是唯一会把所有检查串起来的地方；改它等于改发布门，必须先把工具本身纳入测试 |
| 16 | tools/check_docs.py | refactor_in_place | 三处版本一致 + CHANGELOG 连续 + design 节号连续都实现得干净，但覆盖面只到 4 个文件，恰好漏掉实际漂移最严重的 README/HANDOFF/PRODUCT-PLAN/quality | 扩到 README 会让当前仓库立刻变红（版本 2.67.0），所以要么先修文档，要么让它成为软检查 |
| 16 | .github/workflows/ci.yml | refactor_in_place | 矩阵与两条命令都对，但只跑 verify + unittest；文档一致性（check_docs）、文档可执行性（doc_flow）、发布包可用性（verify_release）都不在 CI 里 | 加 preflight 会把 183s 测试再跑一遍；应改成复用同一份测试结果或分 job |
| 16 | .github/workflows/release.yml | refactor_in_place | tag → verify → build → release 的主干正确，但缺 check_docs 与 verify_release，也没有与 publish_github 的分工说明 | 在 CI 里重建 zip 而不校验本地 dist 的 SHA，会让“可复现”这个承诺在发布路径上失去检验 |
| 01 | scripts/wxg.py | rewrite | 行为简单（插 path、注册 __main__、转发 main），但物理上混了三件事：入口、50 个 handler 的动态注册表、74 个无人用的兼容导出。重写成“入口 + 显式 handler 注册表 + 只保留 gen_sample/tests 实际用的 8 个 helper”，兼容面才有边界。 | verify 用 getattr(wxg, 'cmd_*') 校验 handler 存在（commands_misc.py:303），分派也用同一路径；重写时若换注册表却漏改这两处，会同时坏掉 verify 和所有命令。仓库外是否有人 import wxg 拿 helper，无法从代码证明。 |
| 02 | scripts/wxg_contract.py（WRITE_MODES，L639-691） | rewrite | 行为简单（50 个映射）、边界清楚（只被渲染器/verify/JSON 读），值得改成 read/write/both 枚举 + 生成展示文本，才能让 verify 机械校验。 | 展示文本变化会改文档字节；改完必须同时重生成 SKILL.md、references/contract.md 与导出样例。 |
| 02 | scripts/wxg_contract.py（TOKEN_COMMANDS，L262） | rewrite | 无读者、与事实不符的 6 条清单，直接删除或由 token=True 派生。 | 低；外部若有人 import 该常量会断（仓内 grep 无引用）。 |
| 02 | scripts/whyexist/commands_repo.py（re-export 层 L662-735 + 重复 import L14/L725） | rewrite | 拆包后的兼容残留；wxg.py 已从原模块导入，仓内只有 _import_file_pairs 从该模块被用。 | 低-中：旧测试/外部脚本若按 wxg.commands_repo.cmd_* 访问会断；仓内 grep 未发现。 |
| 04 | scripts/whyexist/db.py（migrate_schema 的结构迁移部分：补列/建表/顺序，L516-562、L613-614） | rewrite | 只加列的语义清楚，但执行顺序错：init_db 先跑完整 DDL（含引用新列的索引）再补列，0.4.x 旧库升级会永久卡死；也没有版本门控（靠列存在性推断）。改成有序步骤 + 明确的兼容检查，成本低 | 改的是所有旧库唯一的升级入口；必须保留 create-if-not-exists 的收敛性（重复 init 零写入）与已迁移库零改写 |
| 04 | scripts/whyexist/db.py（_is_integrity_error，L500-505） | rewrite | 6 行判定，概念清楚（跨后端识别唯一键/非空/外键冲突），但和 wxg_mysql 的第二个实现集合不一致、唯一调用点还缺 import。合并成一份 + 三个后端各两条单测即可 | 合并后若采用更宽的 errno 集合（1048/1451/1452/3819），repo-add 可能把非唯一键错误也翻译成「仓登记冲突」，错误文案会变 |
| 05 | scripts/whyexist/db.py:292-422（_NoopCursor、_mysql_translate、_pg_translate、_named_params） | rewrite | 契约清楚（16 条单测把行为钉死），但实现是引号无关的字符串替换：字面量里的 ? 会被改成 %s、% 会被当占位符、:name 在字符串里也会被替换。新增后端等于再抄一遍正则，且没有任何机制保证改译后 SQL 可执行。 | 重写必须把这 16 条断言当规格逐条过；产品 SQL 目前只有 6 种形态（meta upsert/select、INSERT OR IGNORE、features/repos/nodes/edges upsert），先枚举再迁移，避免顺手改掉 rowcount/占位符语义。 |
| 05 | scripts/whyexist/commands_repo.py:44-59（cmd_init） | rewrite | 16 行、行为清楚，现在却是坏的：db_url 与 re 都没导入，mysql/pg 下 100% NameError。顺带把掩码 URL 的规则写成函数并加测试，比在原地打补丁干净。 | mysql/pg 的 db 字段（掩码 URL）从没被执行过，没有任何断言；重写前要先定这个字段的格式，否则会“修好”成另一个未记录的形状。 |
| 05 | scripts/whyexist/engine.py:36-51（db_url 注入环境变量） | rewrite | 行为简单、边界清楚：Engine 只是想把 URL 传给 connect。现在靠改 os.environ，构造两个 Engine 会互相污染，也会污染同进程的 CLI 逻辑。改成显式参数一路传到 connect。 | connect(root) 的签名变化会波及 cli 与 cmd_up；这是有意为之的接口收紧，需同时更新调用点。 |
| 06 | scripts/whyexist/engine.py | rewrite | 151 行门面，行为边界简单（把连接接到 5 个纯函数入口），但当前实现与 CLI 组装重复、依赖命令层（_brief_payload/cmd_gate）、有 env 与文件副作用；更适合改成薄包装 + 显式只读连接，顺手消除双份组装。 | 输出形状没有完全锁死：gate 返回完整 cmd_gate 字典、impact 的 cross_feature/depends_on 与 db_url 语义都只有 happy path 测试；重写前应先补 C18/C21/C22/C23/C24 的行为测试，否则会静默改掉库 API 的返回结构。 |
| 08 | scripts/whyexist/commands_repo.py:up | rewrite | 60 行编排把 connect/init/repo-add/feature-declare/gate 串在一个 handler 里，分阶段提交、失败留半成品；next 不带 --root；minimal+--path 与帮助文案矛盾；gate 结果重复。行为简单、边界清楚，值得重写为显式步骤与幂等状态机。 | 中高；只有 3 个测试，首屏体验最容易被改坏；需要先立“bootstrap 失败是否回滚/是否非零退出”的契约。 |
| 08 | scripts/whyexist/commands_repo.py:re-exports/imports | rewrite | 662-735 的兼容 re-export 与十余个未使用导入应整体删除；wxg.py 已直接导入各 commands_* 模块，保留这层只会继续掩盖未定义名。 | 低；先全局搜 whyexist.commands_repo 的引用，仓内只有 wxg.py 与 tests 的 _import_file_pairs。 |
| 09 | scripts/whyexist/commands_feature.py::feature-list（235-245） | rewrite | 10 行、0 测试、all-or-nothing 失败模式；行为简单边界清楚，重写并补测试成本最低 | 输出 conditions 字典被可能的脚本消费；没有测试锚，形状变化不可见 |
| 09 | scripts/whyexist/commands_feature.py::change-diff（399-453） | rewrite | 只有 1 个测试，基线选择（未来代不报错）与 inherited/pending 语义未定义；函数小，重写并立契约更安全 | 输出键被 SKILL.md:67 与 agent 流程引用；重写前先补基线/空集/跨代测试 |
| 09 | scripts/whyexist/commands_feature.py::work-list（708-714） | rewrite | 5 行、2 个断言只查 status、原样泄漏 claim_token，行为简单边界清楚 | 返回的 target_ids/depends_on 是 JSON 字符串（外部脚本可能按此解析）；改形状会破坏消费方 |
| 10 | scripts/whyexist/commands_gates.py:118-156（cmd_serve） | rewrite | 行为边界小且独立：循环、间隔、feature 过滤、--once/--apply、每趟打印一行。现有实现混杂了退出码 0、单 feature 异常中止整轮、未知 feature 静默、commit 时机四个未文档化决定，正好可以在重写时显式定义并补测。 | 外部 CI 可能依赖「serve 恒 0」与紧凑单行 JSON；重写若改成 reconcile 式 1 退出码会破坏调用方。先按现契约重写，再单独讨论是否改退出码。 |
| 11 | scripts/whyexist/commands_graph.py:58-106（prune_work_refs + cmd_retract） | rewrite | 行为简单（硬删 + 引用重建），但当前实现有三个可观察错误：删节点连带删 target 外的边、跨 feature 工单引用静默裁剪、不存在的节点也计 1。适合按「校验 → 收集级联集 → 删除 → 重建引用 → 返回真实计数」重写，而不是打补丁。 | 四字段返回形状已被文档（SKILL.md:168）与代理流程依赖；doctor --fix 复制了引用裁剪逻辑，重写后两处必须收敛，否则新删法会被 doctor 改回去；role 矩阵（只有 scan/observe 能 retract）是现行绕过方式，收紧前要决定是否允许建边角色删边。 |
| 12 | scripts/whyexist/commands_misc.py:10-20 导入/常量、197-204 re-export | rewrite | 未使用的 make_temp_dir、无人消费的 query re-export、第三份 DEFAULT_ROOT 都是拆包残留；删除后行为不变，且能减少循环导入风险。 | 低；先全局搜 `whyexist.commands_misc` 的引用（当前只有 wxg.py 与 commands_repo.py 的 re-export）。 |
| 13 | scripts/whyexist/cycles.py:34-173（minimal_break_sets / break_set_costs / advise_break_edges） | rewrite | 行为边界清楚（求最小反馈边集合并给代价），但实现是 2^n 组合枚举 + 每档静默截断 10 组 + truncated 只表达“边太多”；advise 内部又重跑 find_cycles/minimal_break_sets，且与 --without 的交互在 CLI 层就错了。这三点叠起来，重写成一个“按 SCC 求有界最小反馈边、显式报告不完整”的小函数，比在原地打补丁更省事，也更容易单测。 | 返回条数、排序与 edge 顺序会变：test_cycles.py:62-88、tests/test_plan_cli.py:803-819 需要重写断言；SKILL.md:376/README.md:55 对“枚举最小断边集合”的措辞要改成“给定策略下的建议集合”。break_sets 的嵌套形状（edges[] 内含 evidence，cost 只留两键）是对外契约，重写时必须原样保留。 |
| 15 | tests/test_mysql_backend.py | rewrite | 与 pg 版 90% 重复、破坏性 setUpClass、默认 skip，实际从未在 CI 执行；行为边界清楚，值得合并成参数化后端套件 | 它正是「init 在非 SQLite 上 NameError」没被发现的直接原因；重写前必须先决定后端是否进 CI |
| 15 | tests/test_pg_backend.py | rewrite | 同上，另需 psycopg，环境更难；三处 DROP SCHEMA public 不可用于共享库 | 同 MySQL；若后端不冻结，必须先有可复现的 PG 环境 |
| 16 | references/quality.md | rewrite | 清单本身有价值，但它复制了版本号与用例数（2.42.0 / 357，都过期），又自称“已知边界只在 SKILL 维护一处”——按它自己的原则，这些副本就该删掉，只留可执行检查项与指针 | 删掉数字后，提交者失去“当前期望值”这个参照；应改为指向 check_docs/verify 的输出而不是写死 |
| 01 | scripts/whyexist/temp.py | freeze | 42 行，唯一实质逻辑是“Windows 用默认 mode、POSIX 用 0o700”。这条逻辑无法在 CI 里验证（受限 token 环境、空 DACL 都是外部条件），行为靠注释与历史事故记录支撑。没有测试覆盖重试/耗尽/分支差异，动它等于拿不可复现的沙箱故障做实验。 | 冻结的代价是这段“为什么不用 tempfile”的知识只存在于注释（temp.py:1-7）与 CHANGELOG；重写者很容易改回 tempfile 或统一 0o700，然后在 DSH Windows 沙箱里以 PermissionError WinError 5 的形式炸掉所有临时目录用例。 |
| 03 | scripts/wxg_contract.py（L754-776：INVARIANTS） | freeze | 21 条不变量是纯文档字符串：无代码读取、无测试引用、无 I 编号到测试的映射。它们却是跨模块一致性主张的唯一汇总（SKILL.md 开头就拿它当卖点），删改等于悄悄改变对外说法；没有任何检查会因此失败。 | 冻结意味着已知的过时表述会留着（例如 I9 的清单与 DOCTOR_FIXABLE_CHECKS 双份）；谁要动它，必须先建立"不变量 ↔ 测试用例"的机械映射，否则改动不可验证。 |
| 04 | scripts/whyexist/db.py（migrate_schema 的数据回填部分：L528-538、L551-583、L585-592） | freeze | 回填语义是猜测且不可复现：legacy 身份、generation 取 feature 当前代、claimed_at 取 created_at、judge_history 由最终 status 推导。没有测试能验证这些值对不对，表里也没有来源标记；在决定「旧数据可不可追溯」之前不许改 | 动它会静默改变历史解释（例如把更早代的咬合算到当前代、把 failed 历史推导成 passed）；冻结的代价是这些不确定性只活在 CHANGELOG 与注释里 |
| 07 | scripts/whyexist/query.py#slice_payload 输出形状 | freeze | slice_payload 的键（nodes/edges/missing_ids/patterns/depth）被 work-claim 原样嵌入返回值，属于 agent 运行时契约；有没有测试都不该在审计里顺手改形状。 | 冻结意味着 C12 的形状不一致（attrs_json vs attrs）只能靠新增字段解决，不能直接替换；迁移前要给消费方一个版本窗口。 |
| 07 | scripts/whyexist/importer.py#_node_id 与 unmapped 聚合 id 规则 | freeze | 节点 id 是外部主键：work_items.target_ids、feature_nodes、bites.node_id、evidence_ids、导出全部存字面量，没有 id 映射表；改生成规则等于要求全库重建。 | 连"行号不进 id"这条也不能回退（旧 id `@21:len` 的教训在 CHANGELOG.md:1137）；若必须改，需要迁移脚本 + 一次性 stale/retract 策略，且要在 id 里保留旧值映射。 |
| 07 | scripts/whyexist/commands_repo.py::cmd_derive（仅 --apply 写路径） | freeze | 分组/依赖算法在 derive.py（判 keep），问题全集中在写路径，而且都是静默改写：0 组件 apply 成功并 stale 掉旧组件（C34）、重跑只 stale 节点不清旧边（C33）、同 id 的人工组件被覆盖成 derived 且 attrs 丢 duty（C36）、成员 contains 边与 stale 清理绕过 target_ids 边界（C37）、stale 代码节点仍参与分组（C38）。这五条要么没测试、要么与文档承诺冲突，先定契约再动。dry-run 与 derive.py 不受影响。 | 冻结意味着"重跑 derive 会改写人工组织"继续存在；任何修复都要先定三件事：derived 能否覆盖同名 declared、stale 清理是否受 target_ids 约束、成员边是否算越界写入。改错方向的代价是永久丢设计标注或让 verify_reports 的自动化流程失败。 |
| 08 | scripts/whyexist/commands_repo.py:derive --apply | freeze | 写库路径没有测试覆盖同名 declared 组件、越界 stale 清理、stale 代码节点分组；这三条都会静默改写人工组织。先冻结写路径，把“derived 是否允许覆盖同名节点、stale 是否受 target_ids 约束”定成契约，再动。dry-run 与 derive.py 不受影响。 | 高；当前行为会把 declared 组件降级为 derived 并清掉 attrs，重写若保留旧语义等于把 bug 固化。 |
| 09 | scripts/whyexist/commands_feature.py::work-judge 的状态转移表（585-705） | freeze | 每次裁决写入的 status/condition/judged_by/judge_history 组合是 gate、doctor、serve、reconcile 的输入，已由契约（GATE_RULES/AUDIT_RULES）固定；audit-id 与 legacy 两条支路没有测试，任何“顺手统一”都会改变交付判定 | 改转移会静默改变 PASS/FAIL、历史追溯与 Ready 派生；要动先在 tests 里把转移矩阵写死 |
| 09 | scripts/whyexist/commands_feature.py::feature-status 输出字段集（318-338） | freeze | tools/verify_reports.py:224-227 消费 scope_size，agent 提示消费 phase/conditions/coverage；字段名与嵌套形状没有完整断言，重写会静默改外部读取方 | 改名/合并字段会破坏外部脚本与提示词；新增字段安全，删除或改类型不安全 |
| 09 | work_items 状态词表（ready/claimed/submitted/passed/failed/blocked/superseded） | freeze | 这些字符串由本切片写、由 reconcile/doctor/serve/role-prompt 读，且出现在库内已有数据与测试断言中；没有集中常量（散在字面量里） | 任何改名都要迁移旧库并同步 commands_gates.py、commands_misc.py、tools/；先把词表提成常量再谈重构 |
| 11 | scripts/whyexist/commands_repo.py:683-693（本切片 7 个命令的兼容 re-export） | freeze | 它不是本切片的实现，但把 commands_graph 的全部公开名复制了第二份；当前无仓内消费者，删除属于包级 API 变更，先冻结、等外部 import 盘点后再删。 | 冻结期间两套 import 路径并存，新代码可能继续从 commands_repo 取，导致下一次审计仍要追两份；删除时若外部脚本依赖会直接 ImportError。 |
| 12 | scripts/whyexist/commands_misc.py:cmd_doctor --fix（558-617） | freeze | 这是切片里唯一会删数据的路径：硬删 bites/edges/feature_nodes、改写 work_items 的 target_ids/evidence_ids、清 token、刷 meta 版本。6 组修复里 orphan-edge/feature-node-missing/work-refs 三组零测试，meta 计数是假的，stamp 版本还能掩盖未迁移的旧库。先把“能删什么、要不要备份、meta 算不算修复”定成契约，再动。 | 直接改 SQL 条件可能误删活数据；改 meta 行为会让既有 --fix 脚本失效；回退只能靠库备份，而 SQLite 默认没有。 |
| 13 | scripts/whyexist/commands_compiler.py：apply 部分 | freeze | 行为不明且无测试：免 token/role、绕过 target_ids、透传 origin/stale/unmapped/feature_id、不经 work_items 记证据、只查补丁间冲突不查库内已有节点。这些语义只被 SKILL.md:450 提了一句，没有任何测试固定，改它等于在盲改生产写库路径。 | 改严（要求 token/target/证据）会让现有“补丁文件即日志”的工作流报错；改松会继续让 apply 成为绕过 upsert-node 写入契约的后门。先补测试和契约条目，再决定方向。 |
| 16 | references/design.md | freeze | 110 节演进叙事，记录的是“当时为什么这么选”，无法从代码重建；check_docs 只校验节号连续，语义无人守 | 其中 20+ 处引用已不存在的 refactor-lab 脚本与目录；重写会丢掉唯一的设计决策史，所以只冻结不重写 |
| 16 | tools/publish_github.py | freeze | 300 行、零测试、需要 token 与网络、与 release.yml 职责重叠，且因为当前工作树是脏的而从未在 2.x 上成功执行；在弄清“发布到底走哪条路”之前不能动 | 冻结等于保留一条会与 CI 抢 Release 的路径；若直接删，首次建仓/发布的唯一脚本就没了，需要先确认 GitHub 仓库与 Release 由谁维护 |
| 16 | dist/v2.82.0…v2.92.0/ | freeze | 已发布的历史产物，重建只会得到相同的 zip（v2.92.0 已验证），但 manifest 不可追溯、2.90-2.92 内容重复；它们是不可变证据，不该原地重写 | dist/ 被 .gitignore 忽略，这些产物只存在于这台机器；换环境即丢失 |

## 契约空洞（partial / gap）

| # | id | 承诺 | 状态 | 证据 |
|---|---|---|---|---|
| 01 | C2 | --root 省略时状态库根是“进程 cwd 下的 .why-exist”，不是技能目录；init 会在那里建库 | partial | scripts/whyexist/cli.py:16,53-54, scripts/whyexist/commands_repo.py:51, tests/test_wxg.py:873-882 |
| 01 | C4 | --db-url 覆盖 WXG_DB_URL；mysql/mariadb/postgresql/postgres 四个协议被接受，未知协议输出 JSON error 并返回 2 | partial | scripts/whyexist/cli.py:23-27,55-61, scripts/whyexist/db.py:429-438, scripts/whyexist/commands_repo.py:47-49 |
| 01 | C6 | verify / contract / role-prompt 永不 connect，在任何目录运行都不创建 .why-exist/ 或 graph.sqlite | partial | scripts/whyexist/cli.py:62-65,70, tests/test_wxg.py:873-882 |
| 01 | C10 | 非预期异常同样转成 {"error": "<TypeName>: <msg>"} + 退出 2 | gap | scripts/whyexist/cli.py:88-90 |
| 01 | C11 | 连接期失败（psycopg 连不上、root 不可写、mysql 握手失败）给可读错误而不是 traceback | gap | scripts/whyexist/cli.py:58-61,70, scripts/whyexist/db.py:441-465, SKILL.md:277, scripts/wxg_contract.py:221 |
| 01 | C12 | verify：ok=true → 0；ok=false（issues 非空）→ 1 | partial | scripts/whyexist/cli.py:94-96, scripts/whyexist/commands_misc.py:350-352, tests/test_wxg.py:481-487, tests/test_wxg.py:495-501, tests/test_wxg.py:873-881 |
| 01 | C19 | argparse 层错误（缺必填、未知子命令、非法 choices、无子命令）输出 usage 文本到 stderr 并退出 2，不是 JSON | partial | scripts/whyexist/cli.py:28-44, tests/test_wxg.py:904-907 |
| 01 | C20 | --json 标志影响输出格式 | gap | scripts/whyexist/cli.py:95-99,112, scripts/whyexist/commands_misc.py:251 |
| 01 | C21 | stdout 被强制成 UTF-8（sys.stdout.reconfigure），保证中文 JSON 在 Windows 控制台不乱码 | gap | scripts/whyexist/cli.py:49-50, tests/test_wxg.py:21 |
| 01 | C22 | main(argv) 可被进程内调用并返回退出码（不依赖 subprocess） | gap | scripts/whyexist/cli.py:48-113 |
| 01 | C24 | utc_now 返回秒级 UTC ISO 串，固定以 'Z' 结尾、无微秒、无时区偏移 | partial | scripts/whyexist/jsonio.py:15-16, tests/test_package_units.py:80-81 |
| 01 | C26 | loads：None/'' 返回 default；已是容器则原样返回；坏 JSON 抛 Reject | partial | scripts/whyexist/jsonio.py:23-31, tests/test_package_units.py:30-39 |
| 01 | C29 | make_temp_dir：在系统 temp 下按前缀建唯一目录；Windows 用默认 ACL（不做 0o700）、POSIX 保持 0o700；撞名重试，100 次后 RuntimeError | partial | scripts/whyexist/temp.py:21-33, tests/test_wxg.py:47, tests/test_plan_cli.py:50, tools/preflight.py:84 |
| 01 | C30 | temp_dir 在上下文退出时删除目录且忽略删除失败 | gap | scripts/whyexist/temp.py:36-42 |
| 01 | C33 | wxg 模块同时是给旧脚本/测试用的兼容面：wxg.upsert_node / upsert_edge / bind_node / connect / init_db / make_temp_dir / temp_dir / Reject / cmd_init / cmd_export / cmd_feature_declare 可用 | partial | scripts/wxg.py:30-178, scripts/gen_sample.py:43-104, tests/test_wxg.py:612-624, tests/test_plan_cli.py:24,50 |
| 01 | C34 | 以库方式调用 cli.main（scripts/ 不在 sys.path、或没有 wxg.py 兄弟文件）应给出可读错误而不是 traceback | gap | scripts/whyexist/cli.py:71-72, scripts/wxg.py:18-24 |
| 01 | C37 | contract --write 把相对路径解析到技能根、以替换契约块的方式改写文档 | gap | scripts/whyexist/commands_misc.py:255-261 |
| 01 | C38 | graph.sqlite 存在但没有 meta 表时，ensure_db 拒绝并提示 init（退出 2） | gap | scripts/whyexist/db.py:468-483, scripts/whyexist/cli.py:79-80 |
| 02 | C3 | WRITE_MODES 的值真实反映读写：标只读的命令不写状态库。 | gap | scripts/wxg_contract.py:640-691, scripts/whyexist/commands_misc.py:306-307 |
| 02 | C5 | help 文案与真实行为一致。 | gap | scripts/wxg_contract.py:331, scripts/wxg_contract.py:626, scripts/wxg_contract.py:631, scripts/wxg_contract.py:635, scripts/whyexist/commands_repo.py:177-192, scripts/whyexist/query.py:95-97, scripts/whyexist/commands_misc.py:255-260, scripts/whyexist/commands_misc.py:561-600 |
| 02 | C6 | 50 条命令全部是 flag-only（0 个 positionals）；位置参数会被拒绝。 | gap | scripts/wxg_contract.py:269-270, scripts/wxg_contract.py:787, scripts/whyexist/cli.py:31-32 |
| 02 | C9 | TOKEN_COMMANDS 是 token 命令的权威清单。 | gap | scripts/wxg_contract.py:262, scripts/wxg_contract.py:320-469 |
| 02 | C10 | COMMANDS[*].token 字段决定该命令是否需要 token。 | gap | scripts/wxg_contract.py:289-296, scripts/wxg_contract.py:797-798 |
| 02 | C11 | 退出码：成功 0；gate FAIL 1；verify/doctor 有问题 1；apply 冲突 1；reconcile 未收敛 1；Reject/未捕获异常 2。 | partial | scripts/whyexist/cli.py:57-113, tests/test_wxg.py:868, tests/test_wxg.py:1331, tests/test_wxg.py:947-955, tests/test_wxg.py:481-501 |
| 02 | C12 | stdout 是 JSON（indent=2）；contract/role-prompt 输出纯文本；错误 JSON 写 stderr。 | partial | scripts/whyexist/cli.py:109-113, scripts/whyexist/commands_misc.py:262, scripts/whyexist/commands_misc.py:247 |
| 02 | C13 | gate/coverage 的 --json 开关改变输出形态。 | gap | scripts/wxg_contract.py:501, scripts/wxg_contract.py:622, scripts/whyexist/commands_gates.py:28-30, scripts/whyexist/commands_gates.py:159, scripts/whyexist/commands_misc.py:251 |
| 02 | C16 | contract --json 暴露 version/schema/commands/command_write_modes 等，作为机器可读契约。 | partial | scripts/wxg_contract.py:997-1031, tests/test_wxg.py:518-525 |
| 02 | C18 | up 幂等：首次建 root/库/demo 仓/demo feature 并返回 gate 结果；重复执行不重置已有 feature；minimal 模板不建仓。 | partial | scripts/whyexist/commands_repo.py:62-127, tests/test_plan_cli.py:337-359, tests/test_plan_cli.py:518-522 |
| 02 | C19 | feature-list 与 repo-list 的成功输出。 | gap | scripts/whyexist/commands_feature.py:235-245, scripts/whyexist/commands_repo.py:149-150 |
| 02 | C20 | work-judge 可按被审工单 id 或 audit 工单 id 裁决；--role 只能是 audit；failed 必须 --fail-reason；BehaviorPassed 需同代 evidence；开启 coverage 时该阶段需达标。 | partial | scripts/whyexist/commands_feature.py:585-598, scripts/whyexist/commands_feature.py:620-705, tests/test_wxg.py:527-567, tests/test_wxg.py:861-871, tests/test_wxg.py:1133-1157 |
| 02 | C21 | 命令表的关键参数列由 _cmd_params 生成，只列必填 option 与 boolean flag。 | gap | scripts/wxg_contract.py:786-794, SKILL.md:192 |
| 02 | C22 | 契约文件描述完整 CLI 面（含全局 --root/--db-url 与每条命令的退出码）。 | gap | scripts/whyexist/cli.py:22-27, scripts/wxg_contract.py:997-1031, scripts/wxg_contract.py:299-637 |
| 02 | C23 | 角色限制按被调用的命令名执行（ROLES[role] 必须包含该命令）。 | partial | scripts/whyexist/work.py:74-77, scripts/whyexist/commands_repo.py:299, tests/test_package_units.py:108-115 |
| 02 | C24 | 只读命令不输出可写凭证。 | gap | scripts/whyexist/commands_feature.py:250-252, scripts/whyexist/commands_feature.py:310-317, scripts/whyexist/commands_feature.py:708-714 |
| 03 | C3 | `contract --json` 输出可 JSON 序列化，且至少包含 version=2.92.0、schema_version=9、commands、evidence_required_conditions=BehaviorPassed、command_write_modes 与 commands 键集相同。 | partial | scripts/wxg_contract.py:997-1031, tests/test_wxg.py:518-525 |
| 03 | C5 | references/contract.md 的 full 契约块同样被 verify 比较，漂移即报错。 | partial | scripts/whyexist/commands_misc.py:274-285, scripts/wxg_contract.py:924-983 |
| 03 | C7 | verify 做交叉引用检查：每个 COMMANDS 有 cmd_<name> 处理器且出现在 WRITE_MODES；ROLES 引用的命令必须存在；ATTR_SCHEMA / BIND_EDGE_KIND 的 kind 必须属于 NODE_KINDS；EXPORT_FILES 每份必须有列；技能资源文件必须存在；SKILL.md frontmatter 必须 name=why-exist-graph 且有 description。 | partial | scripts/whyexist/commands_misc.py:287-329, tests/test_wxg.py:503-515 |
| 03 | C8 | verify 用真实导出器重新生成 references/export-sample/feat-demo 的 6 份文件并逐份文本比较，样例过期即列出具体文件名。 | partial | scripts/whyexist/commands_misc.py:330-348, scripts/gen_sample.py:118, tests/test_wxg.py:486 |
| 03 | C9 | verify 成功时返回固定的 checks 名单 ['contract-blocks','commands','roles','kinds','write-modes','export-sample'] 和版本行。 | gap | scripts/whyexist/commands_misc.py:352 |
| 03 | C10 | `contract --write <file> --section main\|full` 用渲染结果替换标记之间内容，重复执行结果不变（幂等），相对路径以技能根为基准。 | gap | scripts/whyexist/commands_misc.py:255-261, scripts/wxg_contract.py:1040-1047, README.md:121-122 |
| 03 | C11 | 契约块标记缺失时 verify 报告问题而不是崩溃；extract_block / replace_block 对缺标记抛 ValueError。 | gap | scripts/wxg_contract.py:1040-1054, scripts/whyexist/commands_misc.py:278-282 |
| 03 | C13 | ATTR_SCHEMA 的类型标记语义：'str'/'int'/'bool' 由 graph.check_attrs 解释，'任意' 表示不校验（parameter.example）。 | gap | scripts/wxg_contract.py:695-721, scripts/whyexist/graph.py:30-38 |
| 03 | C14 | 边属性不受任何 schema 约束：upsert_edge 直接把 payload.attrs JSON 化落库。 | gap | scripts/whyexist/graph.py:140-187, scripts/wxg_contract.py:723-726 |
| 03 | C15 | BIND_EDGE_KIND 把 parameter/argument/assertion 映射到 has_input/has_argument/asserts，bind 只接受这三类节点。 | partial | scripts/wxg_contract.py:113-117, scripts/whyexist/graph.py:190-213, tests/test_wxg.py:229-231, tests/test_wxg.py:510 |
| 03 | C17 | work-open 只接受 WORK_KINDS 内的 kind（audit 必须由 work-finish 生成）；work_items.role 直接等于 kind。 | partial | scripts/wxg_contract.py:57-66, scripts/whyexist/commands_feature.py:496-503, scripts/whyexist/work.py:25-43 |
| 03 | C19 | TOKEN_COMMANDS 列出需要 claim_token 的命令集合。 | gap | scripts/wxg_contract.py:262 |
| 03 | C20 | WRITE_MODES 为每个命令声明"写入"列，是生成文档命令表写入列的唯一来源；缺声明会被 verify 报错。 | partial | scripts/wxg_contract.py:640-691, scripts/wxg_contract.py:797-798, scripts/whyexist/commands_misc.py:306-307, tests/test_wxg.py:525 |
| 03 | C21 | EXPORT_FILES 决定导出文件名、标题、列与顺序，export 按列表下标 0..5 逐份生成。 | partial | scripts/wxg_contract.py:730-742, scripts/whyexist/commands_misc.py:66-194, tests/test_wxg.py:1004-1026, tests/test_wxg.py:608-631 |
| 03 | C22 | EXPORT_RULE 描述导出作用域（01 取 requirement、02 取 satisfies、04 取 depends/associates/realizes、05 取 contains、07 取 writes→sink 等），是导出行为的文字契约。 | gap | scripts/wxg_contract.py:744-750, scripts/wxg_contract.py:977-979, scripts/whyexist/commands_misc.py:22-194 |
| 03 | C23 | JUDGE_HISTORY_COLUMNS 声明 judge_history 的 9 列，应等于 SCHEMA_SQL 里的实际表结构。 | gap | scripts/wxg_contract.py:174-184, scripts/whyexist/db.py:127-137 |
| 03 | C24 | 21 条 INVARIANTS（I1-I21）是系统一致性承诺，渲染进 SKILL.md main 块与 contract.md full 块。 | gap | scripts/wxg_contract.py:754-776, tests/test_wxg.py:189, tests/test_wxg.py:391, tests/test_wxg.py:1102, tests/test_wxg.py:1613 |
| 03 | C26 | VERSION 文件内容与 CONTRACT_VERSION 一致，且与 CHANGELOG 最新条目一致。 | gap | tools/check_docs.py:28-45, tools/preflight.py:70-73, tools/build_release.py:81-86 |
| 03 | C28 | SCHEMA_VERSION 是迁移的判据：版本落后时执行对应迁移。 | gap | scripts/wxg_contract.py:17, scripts/whyexist/db.py:509-601 |
| 03 | C29 | DOCTOR_FIXABLE_CHECKS 决定 doctor 输出里哪些 issue 带 fixable=true，且 I9 的"--fix 只自动修这些"必须与之一致。 | partial | scripts/wxg_contract.py:22-30, scripts/whyexist/commands_misc.py:603, scripts/wxg_contract.py:763 |
| 03 | C30 | 块替换/比较对首尾空行不敏感：verify 用 strip("\n") 后比较，块边界多一个空行不会报漂移。 | gap | scripts/wxg_contract.py:1047, scripts/wxg_contract.py:1054, scripts/whyexist/commands_misc.py:279-284 |
| 03 | C31 | 同一文件出现多对契约块标记时，只有第一对被比较/替换，其余被忽略。 | gap | scripts/wxg_contract.py:1045-1047, scripts/wxg_contract.py:1054 |
| 03 | C32 | GATE_RULES / AUDIT_RULES / EVIDENCE_RULES / COVERAGE_RULES / RECONCILE_RULES / CHANGE_RULES / RESCAN_RULES / BACKEND_RULES / SERVE_RULES / CONFORMANCE_RULES 是规则的文字契约，应与实现同构。 | gap | scripts/wxg_contract.py:129-242, scripts/whyexist/gates.py:81-121, scripts/whyexist/commands_gates.py:159-322, scripts/whyexist/commands_feature.py:620-696 |
| 04 | C2 | init 的 stdout 是 JSON，键为 root/db/backend/schema_version/contract_version/migrated | partial | scripts/whyexist/commands_repo.py:52-59, scripts/whyexist/cli.py:75-77,109-113, tests/test_wxg.py:652, tests/test_mysql_backend.py:88, tests/test_pg_backend.py:90 |
| 04 | C3 | 全新库第一次 init 返回 migrated={"meta": 2}，第二次返回 {} | gap | scripts/whyexist/db.py:593-601, tests/test_wxg.py:693 |
| 04 | C5 | init 能把任意旧 schema 非破坏地收敛到 9（只加列/加表，不删行） | gap | scripts/whyexist/db.py:613-614, scripts/whyexist/db.py:126, scripts/whyexist/db.py:551-553, SKILL.md:144 |
| 04 | C6 | 旧 work_items 补 claimed_by/judged_by/judged_at/claimed_at 四列；未知身份按状态标 legacy（audit 工单豁免、不伪造具体成员） | partial | scripts/whyexist/db.py:516-527, scripts/whyexist/db.py:563-583, tests/test_wxg.py:632-679 |
| 04 | C7 | claimed_at 只对 status='claimed' 的旧行按 created_at 回填（下界，不还原真实领取时刻） | gap | scripts/whyexist/db.py:581-583, SKILL.md:237 |
| 04 | C9 | 旧 bites 补 generation/phase 两列，generation 按 feature 当前代回填 | partial | scripts/whyexist/db.py:551-562, tests/test_wxg.py:671 |
| 04 | C10 | judge_history 回填用确定性 id `jh:<work_item_id>`，只对 judged_by 非空、kind<>audit、且尚无历史行的工单执行；verdict 由最终 status 推导（passed 否则 failed） | partial | scripts/whyexist/db.py:585-592, references/contract.md:329, tests/test_wxg.py:673 |
| 04 | C12 | 没有降级保护：库里版本号高于代码时，init 直接把它改写成当前版本，随后 doctor 报 ok | gap | scripts/whyexist/db.py:593-601, scripts/whyexist/commands_misc.py:537-540 |
| 04 | C13 | ensure_db 的唯一判据是 meta 表存在；不存在则 Reject「状态库未初始化」并退出 2 | gap | scripts/whyexist/db.py:468-483, scripts/whyexist/cli.py:79-80, tests/test_wxg.py:947-955 |
| 04 | C13b | meta 表存在即视为可用；缺表/缺列不会被 ensure_db 或 init 前置发现，命令以 OperationalError 退出 2 | gap | scripts/whyexist/db.py:468-483, scripts/whyexist/cli.py:85-90 |
| 04 | C14 | sqlite connect：创建 root 目录、timeout=5s、WAL、busy_timeout=5000、foreign_keys=ON | partial | scripts/whyexist/db.py:458-465, tests/test_wxg.py:1391-1402, SKILL.md:276 |
| 04 | C15 | 连接期失败（graph.sqlite 不是数据库、--root 指向文件）不是可读 JSON，而是 traceback + 退出码 1 | gap | scripts/whyexist/cli.py:70, scripts/whyexist/db.py:458-464 |
| 04 | C16 | 一条 CLI 命令一个事务：handler 返回后统一 commit；抛异常不 commit，关闭连接即回滚，不留半截写入 | gap | scripts/whyexist/cli.py:74-93, scripts/whyexist/db.py:353-360, scripts/whyexist/commands_repo.py:73,87,107, scripts/whyexist/commands_gates.py:142 |
| 04 | C17 | --db-url 覆盖 WXG_DB_URL；未知协议输出 JSON 错误并退出 2 | gap | scripts/whyexist/cli.py:55-61, scripts/whyexist/db.py:429-438 |
| 04 | C18 | _is_integrity_error 识别 sqlite3.IntegrityError、MySQL errno {1022,1062,1169,1557}、PG sqlstate 23*，其它异常原样抛出 | gap | scripts/whyexist/db.py:500-505, scripts/whyexist/graph.py:9, scripts/wxg_mysql.py:116-157 |
| 04 | C19 | repo-add 用不同 id 登记同一路径时，返回 Reject「仓登记冲突：path ... 已被其它 repo id 占用」并退出 2 | gap | scripts/whyexist/commands_repo.py:136-146, scripts/whyexist/db.py:26, CHANGELOG.md:1499 |
| 04 | C20 | SQLite/MySQL/PG 三份 DDL 的表集合与列名逐表一致（12 表） | gap | scripts/whyexist/db.py:19-150, scripts/whyexist/db.py:154-285, scripts/whyexist/db.py:288-289 |
| 04 | C21 | 表间不声明任何外键/CHECK；引用完整性由 doctor 事后检查（dangling-bite/orphan-edge/feature-node-missing/work-*-missing/token-on-inactive），--fix 只手删悬空引用与清 token | partial | scripts/whyexist/db.py:19-150, scripts/whyexist/commands_misc.py:360-400,562-589, references/design.md:72, tests/test_wxg.py:391-429 |
| 04 | C22 | mysql/postgres 后端 init 输出 backend 名与脱敏后的 db 标签，退出 0 | gap | scripts/whyexist/commands_repo.py:46-51, tests/test_mysql_backend.py:86-89, tests/test_pg_backend.py:88-91 |
| 04 | C23 | init_db 在返回前自行 commit；因此 init 报错时库可能已经建好/迁移完 | gap | scripts/whyexist/db.py:613-615, scripts/whyexist/cli.py:75-77 |
| 04 | C24 | 迁移的 generation/身份回填是猜测值，升级后不标记来源（无法区分真实值与回填值） | partial | scripts/whyexist/db.py:531-538,554-559, CHANGELOG.md:1504-1506, references/design.md:151,169-170 |
| 05 | C1 | --db-url 是全局参数，优先于 WXG_DB_URL；必须写在子命令之前。 | partial | scripts/whyexist/cli.py:23-27, scripts/whyexist/cli.py:55-56, SKILL.md:60-63 |
| 05 | C2 | URL scheme 只接受 mysql/mariadb/postgresql/postgres，其余抛 Reject，CLI 输出 JSON error 并退出 2。 | gap | scripts/whyexist/db.py:433-438, scripts/whyexist/cli.py:57-61 |
| 05 | C4 | sqlite 下状态库文件不存在时，非 init 命令直接报「状态库未初始化」退出 2，且不留下 0 字节库。 | gap | scripts/whyexist/cli.py:66-69 |
| 05 | C5 | mysql/postgres 后端连接成功但库未建表时，报「状态库未初始化：先运行 wxg init」并退出 2。 | gap | scripts/whyexist/db.py:468-483, tests/test_mysql_backend.py:87 |
| 05 | C6 | wxg init 在 mysql 后端返回 backend='mysql'、schema_version=9，并建好全部表。 | gap | tests/test_mysql_backend.py:86-89, scripts/whyexist/commands_repo.py:44-59 |
| 05 | C7 | wxg init 在 postgres 后端返回 backend='postgres'、schema_version=9，并建好全部表。 | gap | tests/test_pg_backend.py:88-91, scripts/whyexist/commands_repo.py:44-59 |
| 05 | C10 | mysql/pg 上 migrate_schema 与 sqlite 行为一致。 | gap | scripts/whyexist/db.py:586-592, scripts/whyexist/db.py:500-505 |
| 05 | C11 | mysql/pg 上 import-file / import-repo 的写入路径与 sqlite 一致（nodes/edges/feature_nodes 落库、stale 标记）。 | gap | tests/test_mysql_backend.py:93-102, tests/test_pg_backend.py:96-106, scripts/whyexist/commands_repo.py:204-207, scripts/whyexist/commands_repo.py:308-311 |
| 05 | C12 | mysql/pg 上并发 work-claim 只有一个成功（退出码 0 与 2）。 | partial | tests/test_mysql_backend.py:109-126, tests/test_pg_backend.py:112-129, scripts/whyexist/commands_feature.py:527-532 |
| 05 | C13 | 后端连接失败（错密码、端口不通、PG 无服务、未装 psycopg）报可读错误而不是 traceback。 | gap | scripts/wxg_contract.py:221, references/contract.md:170, CHANGELOG.md:1297-1298, scripts/whyexist/cli.py:70 |
| 05 | C20 | mysql/pg 连接对象提供 sqlite3.Connection 的所需子集：execute / executemany / executescript / commit / rollback / close，游标有 fetchone/fetchall/rowcount/close。 | gap | scripts/whyexist/db.py:323-397, scripts/whyexist/commands_repo.py:204, scripts/whyexist/commands_repo.py:308 |
| 05 | C21 | 后端只决定状态库位置，不影响 --root 决定的导出目录；同一个库不要混用后端。 | partial | scripts/wxg_contract.py:223, references/contract.md:171 |
| 05 | C22 | mysql/pg 后端下 --root 目录不会被创建（不会留下 .why-exist）。 | gap | scripts/whyexist/db.py:458-459 |
| 05 | C23 | init 不创建数据库本身，要求目标 MySQL/PG 库已存在。 | partial | references/design.md:276, CHANGELOG.md:1307, scripts/wxg_mysql.py:223-248 |
| 05 | C24 | wxg contract 的 JSON 含 backend_rules，且与 SKILL.md / references/contract.md 的生成块一致。 | partial | scripts/wxg_contract.py:884, scripts/wxg_contract.py:1021, tests/test_wxg.py:490-525 |
| 06 | C2 | 写边的 kind 必须在 EDGE_KINDS 内，且 src/dst/kind 三者必须是非空字符串，否则 Reject | gap | scripts/whyexist/graph.py:140-147 |
| 06 | C4 | attrs 必须是 JSON 对象；只允许 ATTR_SCHEMA 声明的键或 x_ 前缀键；声明为 str/int/bool 的键做类型校验；否则 Reject | partial | scripts/whyexist/graph.py:18-41, tests/test_package_units.py:168-175, tests/test_wxg.py:1430-1441 |
| 06 | C6 | upsert-node 返回 {"action":"insert"\|"update","id":<id>}，insert/update 由写入前该 id 是否存在决定 | gap | scripts/whyexist/graph.py:95-96, scripts/whyexist/graph.py:133 |
| 06 | C7 | 已存在节点被 upsert 时，attrs 整体替换（默认 merge_attrs=False）；name/repo/path/symbol/line_*/origin 缺省时沿用旧值；stale 一律清 0；unmapped 由 payload 的真假值重写 | partial | scripts/whyexist/graph.py:97-118, tests/test_wxg.py:1404-1428, docs/audit/_probe_06.py:45-64 |
| 06 | C9 | upsert_node 的 payload 若带 feature_id，就写 feature_nodes(feature_id,node_id)；不校验该 feature 是否存在 | partial | scripts/whyexist/graph.py:130-132, tests/test_wxg.py:1869-1889 |
| 06 | C10 | upsert_edge 要求 src/dst 节点已存在，否则 Reject（写时引用完整性） | gap | scripts/whyexist/graph.py:148-151, references/design.md:1637 |
| 06 | C13 | 边 id 默认 edge:{kind}:{src}:{dst}；payload 带 id 时原样使用，不做格式校验 | partial | scripts/whyexist/graph.py:136-137, scripts/whyexist/graph.py:168, tests/test_package_units.py:177-178, docs/audit/_probe_06.py:82-87 |
| 06 | C14 | bind 只接受 parameter/argument/assertion；目标节点必须存在；默认边 kind 取 BIND_EDGE_KIND；parameter/argument 的方向是 bind_to -> node，assertion 是 node -> bind_to | partial | scripts/whyexist/graph.py:190-213, tests/test_wxg.py:142-143, tests/test_wxg.py:229-231 |
| 06 | C15 | --edge-kind 可取 has_input/has_argument/asserts 中任意值，且不与 node kind 交叉校验 | gap | scripts/wxg_contract.py:462, scripts/whyexist/graph.py:198-206, docs/audit/_probe_06.py:67-80 |
| 06 | C16 | find_repo 取路径前缀最长（最具体）的已登记仓；文件不在任何仓内时 Reject 并提示 repo-add | gap | scripts/whyexist/graph.py:60-72 |
| 06 | C17 | Engine 只读：各方法不写节点/边/条件/工单；重复调用结果一致 | partial | scripts/whyexist/engine.py:11-15, README.md:48, tests/test_engine.py:109-115 |
| 06 | C18 | Engine.plan 返回 planner 的结果，默认排除作用域内 unmapped 与 stale 节点，并回填 excluded_unmapped/excluded_stale | partial | scripts/whyexist/engine.py:77-113, tests/test_engine.py:82-88, tests/test_plan_cli.py:525-535 |
| 06 | C21 | Engine.gate 返回 cmd_gate 的完整字典，result 为 PASS/FAIL；FAIL 不抛异常 | partial | scripts/whyexist/engine.py:129-131, tests/test_engine.py:109-115 |
| 06 | C22 | Engine.impact 返回 build_impact 的闭包字段（affected 含 changed、direct/indirect、cross_feature、depends_on、requirements/uncovered、closed） | partial | scripts/whyexist/engine.py:133-151, tests/test_engine.py:123-129 |
| 06 | C23 | Engine.connect 在状态库未初始化时抛 Reject（状态库未初始化：先运行 wxg init）；构造时传 db_url 会写入进程级 WXG_DB_URL | gap | scripts/whyexist/engine.py:43-51, docs/audit/_probe_06.py:28-43 |
| 06 | C24 | close() 只关闭连接并把 _conn 置 None；之后调用方法会静默重连（连接不是终止状态） | gap | scripts/whyexist/engine.py:43-64, tests/test_engine.py:131-136 |
| 06 | C25 | graph_algo 是纯函数层：只 import dataclasses，不 import 项目内模块、不读写数据库 | partial | scripts/whyexist/graph_algo.py:19-21, tests/test_graph_algo.py:11-14 |
| 06 | C30 | reachable 返回从 start 出发的可达集、不含 start 自身；reverse=True 走上游；未知 start 返回空集 | partial | scripts/whyexist/graph_algo.py:240-263, tests/test_graph_algo.py:139-160, docs/audit/_probe_06.py:112 |
| 06 | C31 | transitive_reachable 返回每个节点严格可达集（不含自身）；DAG 上走位集传递闭包，环图退化为逐点 DFS，结果同样排除自身 | partial | scripts/whyexist/graph_algo.py:201-237, tests/test_graph_algo.py:157-160, references/design.md:575 |
| 06 | C33 | analyze 对空图返回 acyclic=True、layers=[]、max_antichain=0；对多个独立环 parallelism 取最大环 SCC 大小 | gap | scripts/whyexist/graph_algo.py:366-380, docs/audit/_probe_06.py:99-111 |
| 07 | C1 | resolve_targets 把 target_ids 拆成三类：库中存在的精确 id 原样保留；后缀 `*` 的模式按前缀展开为排序后的现存 id（去重、保持 target_ids 顺序）；其余精确 id 进 missing；模式本身原样进 patterns | partial | scripts/whyexist/query.py:13-34, tests/test_wxg.py:431-442, tests/test_wxg.py:1286-1289 |
| 07 | C2 | 通配模式若一个节点都没匹配到，命令静默成功：nodes=[]、missing_ids=[]、patterns 里仍有该模式，退出码 0 | gap | scripts/whyexist/query.py:21-27, docs/audit/_probe_07.py（输出：通配未命中的 slice） |
| 07 | C3 | slice 返回的是'命中节点的关联边'：凡 src 或 dst 等于某个命中节点的边（按边 id 去重），不要求边的另一端也在返回的 nodes 里；depth 字段恒为 1，不做遍历 | partial | scripts/whyexist/query.py:37-52, docs/audit/_probe_07.py（输出：slice 边的另一端不在 nodes 里） |
| 07 | C4 | slice payload 恒定包含 depth:1；这是常量而非遍历深度，库内没有任何消费方读取它 | gap | scripts/whyexist/query.py:51, scripts/whyexist/commands_feature.py:552-560 |
| 07 | C5 | slice --limit N 把 nodes 与 edges 各自截到 N 条（不是总数），并额外输出 nodes_total/edges_total（截断前）与 truncated（任一列表被截断） | partial | scripts/whyexist/query.py:66-74, tests/test_wxg.py:1277-1289 |
| 07 | C6 | slice 必须给 --work 或 --ids 之一，两个都给时 --work 生效、--ids 被忽略；--limit 为负 -> Reject（exit 2） | gap | scripts/whyexist/query.py:56-74 |
| 07 | C7 | get 返回节点整行并把 attrs_json 解析成 attrs 对象（输出里不再有 attrs_json）；节点不存在 -> Reject "节点不存在：<id>"（exit 2） | partial | scripts/whyexist/query.py:78-83, tests/test_wxg.py:367-369 |
| 07 | C8 | find 按 kind / path_prefix / from_id 组合过滤（AND），结果按 id 升序，attrs_json 解析成 attrs | partial | scripts/whyexist/query.py:86-102, tests/test_wxg.py:346-347, tests/test_wxg.py:941-943 |
| 07 | C9 | find 返回 total（截断前）与 truncated（截断后条数 < total）；--limit 0 返回空列表且 truncated=True；--limit<0 -> Reject | partial | scripts/whyexist/query.py:103-109, tests/test_wxg.py:1281-1284, docs/audit/_probe_07.py（输出：find --limit 0） |
| 07 | C10 | find --path-prefix 被直接拼成 SQL `path LIKE ?`（参数为 prefix+"%"），不做 LIKE 转义：用户传 % 或 _ 会按通配符生效 | gap | scripts/whyexist/query.py:92-94, docs/audit/_probe_07.py（输出：find --path-prefix %（LIKE 通配泄漏）） |
| 07 | C11 | slice/get/find 不过滤 stale 节点与边：stale=1 的行照常出现在查询结果里 | gap | scripts/whyexist/query.py:39-42, scripts/whyexist/query.py:87-99, docs/audit/_probe_07.py（输出：find 含 stale 节点） |
| 07 | C12 | 三个只读命令的节点形状不一致：slice 的节点/边带原始 attrs_json 字符串，get/find 的节点带解析后的 attrs 对象 | gap | scripts/whyexist/query.py:39, scripts/whyexist/query.py:82, scripts/whyexist/query.py:101, docs/audit/_probe_07.py（输出：slice 节点字段带 attrs_json / get 节点字段带 attrs） |
| 07 | C13 | slice/get/find 只读：不改任何表，不在状态库里留下写入 | gap | scripts/whyexist/query.py:1-4, CONTRIBUTING.md:43, README.md:152, references/quality.md:60 |
| 07 | C14 | plan_python 为顶层 class 建 classifier，为顶层函数/async 函数与类方法建 operation（类方法 symbol 为 Class.method），为类体 plain Assign 与 self.attr 赋值建 property；classifier->成员 contains，operation->property writes | partial | scripts/whyexist/importer.py:53-113, scripts/whyexist/importer.py:180-208, tests/test_wxg.py:334-351, tests/test_wxg.py:925-945 |
| 07 | C15 | calls 解析三档：self.<method> 命中本类已定义方法时建已解析 calls 边；裸名命中同文件顶层函数时建已解析 calls 边；其余（外部接收者、内置函数、未知裸名、链式/下标调用）建一个按名字聚合的 unmapped operation 节点 + unmapped=1 的 calls 边 | partial | scripts/whyexist/importer.py:143-172, scripts/whyexist/importer.py:174-178, tests/test_plan_cli.py:537-564, tests/test_wxg.py:925-945 |
| 07 | C16 | unmapped 节点 id 按名字聚合、不含行号：简单名 `operation:<repo>:<rel>:<display>`，复杂表达式 `operation:<repo>:<rel>:<清洗串>:<sha1(display)[:8]>`；行号只写 line_start/line_end（首次出现处，后续不更新） | partial | scripts/whyexist/importer.py:116-136, scripts/whyexist/importer.py:169-172, tests/test_plan_cli.py:537-564, CHANGELOG.md:1137 |
| 07 | C17 | 导入器不产出 reads / imports / inherits / generalizes 边，也不处理 import 语句、继承基类、嵌套 def/class、模块级赋值、参数：这些结构在图里完全不可见 | gap | scripts/whyexist/importer.py:53-211, scripts/wxg_contract.py:90-111, docs/audit/_probe_07.py（输出：边 kind 集合 / 是否出现 reads / imports / generalizes） |
| 07 | C18 | 节点 id 形如 kind:repo:<仓内相对 POSIX 路径>:symbol，行号不进 id；改文件名/移动目录/改名都会得到新 id，旧 id 只能靠 stale 标记保留 | partial | scripts/whyexist/importer.py:18-19, scripts/whyexist/importer.py:24, tests/test_plan_cli.py:564, SKILL.md:443 |
| 07 | C19 | 语法错误 -> Reject("Python 语法无法解析：...")（CLI exit 2）；非 UTF-8 文件 -> UnicodeDecodeError（CLI exit 2，错误文本是 UnicodeDecodeError）；文件不在 repo.path 下 -> ValueError（只有 CLI 层 find_repo 会先挡住） | gap | scripts/whyexist/importer.py:24-29, docs/audit/_probe_07.py（输出：重复类名 / 非 UTF-8 / 语法错误 / 仓外文件） |
| 07 | C20 | 同一文件里重复定义同名类（条件定义等）会让第二遍的 class_ops 查表失败，抛 KeyError；CLI 以 {"error":"KeyError: '<method>'"} exit 2 | gap | scripts/whyexist/importer.py:67, scripts/whyexist/importer.py:83, scripts/whyexist/importer.py:185, docs/audit/_probe_07.py（输出：重复类名） |
| 07 | C23 | import-file --prepare 必须带 --feature（否则 Reject），只创建/并入 scan 工单（targets = 本次节点 ∪ stale 节点）并写 feature_nodes，不写 nodes/edges | partial | scripts/whyexist/commands_repo.py:177-192, tests/test_wxg.py:337-338, tests/test_plan_cli.py:544-548 |
| 07 | C24 | import-repo 递归扫描仓内全部 *.py（跳过以 . 开头的路径段），遇第一个语法错误整批 Reject（错误带相对文件名）；返回 files/nodes/edges 计数（prepare）或写入计数（write） | partial | scripts/whyexist/commands_repo.py:249-272, scripts/whyexist/commands_repo.py:276-338, tests/test_plan_cli.py:567-584 |
| 07 | C25 | import-file 不校验扩展名：仓内任意 UTF-8、语法合法的文件（如 notes.txt 里写 Python）都会被当成模块导入并产生节点 | gap | scripts/whyexist/commands_repo.py:153-163, docs/audit/_probe_07.py（输出：import-file 非 .py（语法合法）） |
| 07 | C26 | plan_python 是纯函数：只读传入的文件，返回 (nodes, edges) 字典，不碰状态库、不建文件；sync 的只读承诺依赖这一点 | partial | scripts/whyexist/importer.py:22-31, scripts/whyexist/importer.py:213, tests/test_wxg.py:1600 |
| 07 | C27 | group_key 只取目录部分：depth>0 取前 depth 层用 "." 连接，根目录文件返回 "."，反斜杠归一成 "/"；depth<=0 时取全部目录层 | partial | scripts/whyexist/derive.py:26-41, tests/test_derive.py:15-26, docs/audit/_probe_07.py（输出：depth=0 / depth=-1 组件） |
| 07 | C28 | component_id 为 `component:<repo>:<key>`；components 按 id 排序、members 排序、depends 按 (src,dst) 排序且 evidence 去重排序 | partial | scripts/whyexist/derive.py:44-46, scripts/whyexist/derive.py:121-140, tests/test_derive.py:38-41, tests/test_derive.py:90-101 |
| 07 | C31 | derive 默认 dry-run 且不写库，返回 mode="dry-run" 与 strategy/depth/exclude_dirs/excluded_nodes/components/depends；只推导出 <=1 个组件时附 hint（目录层级不足） | partial | scripts/whyexist/commands_repo.py:445-468, scripts/wxg_contract.py:647, tests/test_plan_cli.py:587-600 |
| 07 | C32 | derive --apply 需要 --token，工单角色必须在 derive 的允许集内，且工单 target_ids 必须覆盖本轮全部 component id；写入 origin=derived 的 component 节点（attrs x_strategy/x_depth/x_path）、component->member 的 contains 边、component->component 的 depends 边（attrs.x_evidence 为前 20 条来源对），返回各类计数 | partial | scripts/whyexist/commands_repo.py:470-533, scripts/whyexist/work.py:88-100, tests/test_plan_cli.py:602-626, tests/test_package_units.py:619-634 |
| 07 | C33 | 重跑 derive 时，本轮未出现的 origin=derived 组件被标 stale=1（promote 后的 declared 不动），返回 stale_derived 计数；只标节点，不清理旧节点的 contains/depends 边 | partial | scripts/whyexist/commands_repo.py:474-485, CHANGELOG.md:1105-1111, docs/audit/_probe_07.py（输出：重跑后留下的 depends 边 / 旧边指向 stale 组件） |
| 07 | C34 | derive --apply 在推导出 0 个组件时仍然成功（exit 0），不写任何节点/边，但把该仓全部旧 derived 组件标 stale=1（stale_derived>0）；dry-run 同样 0 组件只给 hint | gap | scripts/whyexist/commands_repo.py:472-485, scripts/whyexist/work.py:88-100, docs/audit/_probe_07.py（输出：0 组件 apply） |
| 07 | C35 | derive 每次运行都从磁盘重新解析全仓 import（绝对 + 相对、跳过点目录、语法错误静默跳过、解码 errors="replace"），与 importer 的严格 UTF-8 读取是两套策略 | partial | scripts/whyexist/commands_repo.py:380-423, scripts/whyexist/commands_repo.py:448, tests/test_package_units.py:690-739 |
| 07 | C36 | derive --apply 对同 id 的人工组件不做区分：origin 被改写成 derived、name 被改成组件键名、attrs 被 x_strategy/x_depth/x_path 整体替换（人工写的 duty 等丢失），既不跳过也不警告 | gap | scripts/whyexist/commands_repo.py:488-505, scripts/whyexist/graph.py:97-105, docs/audit/_probe_07.py（输出：同名人工组件被 apply 后的 origin/name/attrs） |
| 07 | C37 | derive --apply 的写入边界只校验 component id：组件的 contains 边写向成员节点（成员 id 通常不在 target_ids 内），depends 边写向另一组件，重跑的 stale 清理按 id 前缀扫全仓——三者都不受当前工单 target_ids 约束 | gap | scripts/whyexist/commands_repo.py:472-473, scripts/whyexist/commands_repo.py:476-485, scripts/whyexist/commands_repo.py:506-523, SKILL.md:463, docs/audit/_probe_07.py（输出：成员 id 是否在 target_ids 内） |
| 07 | C38 | derive 的节点取数只过滤 unmapped=0、不过滤 stale：已标 stale 的代码节点仍被分进组件，apply 时还会为它写 contains 边 | gap | scripts/whyexist/commands_repo.py:438-441, docs/audit/_probe_07.py（输出：dry-run 是否把 stale 代码节点分进组件） |
| 08 | C1 | SQLite 上 wxg init 创建全部 schema 表、写 meta.schema_version/contract_version，并返回 root/db/backend/schema_version/contract_version/migrated，退出码 0。 | partial | scripts/whyexist/commands_repo.py:44-59, scripts/whyexist/db.py:605-616, tests/test_wxg.py:651-652 |
| 08 | C4 | MySQL/PostgreSQL 后端上 wxg init 返回 backend=mysql/postgres，db 字段为掩码后的 URL。 | gap | scripts/whyexist/commands_repo.py:46-51, tests/test_mysql_backend.py:86-89, tests/test_pg_backend.py:89 |
| 08 | C6 | wxg up 即使 gate 结果为 FAIL 也以退出码 0 结束（bootstrap 成功不等于交付通过）。 | partial | tests/test_plan_cli.py:337-351, scripts/whyexist/commands_repo.py:109-125, scripts/whyexist/cli.py:109-113 |
| 08 | C7 | wxg up --template standard（或未给 --path）在 <root>/../demo-repo 创建 demo.py（不存在时）并登记仓。 | gap | scripts/whyexist/commands_repo.py:75-87 |
| 08 | C9 | wxg up 返回的 next 命令带同一 --root，用户照抄不会落到默认 ./.why-exist。 | gap | scripts/whyexist/commands_repo.py:117-124 |
| 08 | C10 | wxg repo-add 按 id upsert 仓、把 path 规范化为绝对路径、language 只接受 python；重复同 id/path 幂等。 | partial | scripts/whyexist/commands_repo.py:130-146, tests/test_wxg.py:85-87, tests/test_wxg.py:904-907 |
| 08 | C11 | wxg repo-add 对路径不存在、非 python、path 被其它 id 占用给可读 JSON Reject（退出码 2）。 | partial | scripts/whyexist/commands_repo.py:131-145, tests/test_wxg.py:904-907 |
| 08 | C12 | wxg repo-list 按 id 升序返回全部 repos（含 created_at），只读；未初始化时退出 2 且不创建目录。 | partial | scripts/whyexist/commands_repo.py:149-150, scripts/whyexist/graph.py:56-57, tests/test_wxg.py:947-955 |
| 08 | C13 | wxg import-file --prepare 免 token、要求 --feature，把新节点与 stale 候选并入当前代 scan 工单，并写 feature_nodes。 | partial | scripts/whyexist/commands_repo.py:177-192, tests/test_wxg.py:337-340, tests/test_wxg.py:1566-1569 |
| 08 | C14 | wxg import-file 写库要求 claimed token、角色 import-file、全部 node/stale id 落在 target_ids 内，否则 Reject 2。 | gap | scripts/whyexist/commands_repo.py:193-195, scripts/whyexist/work.py:88-100 |
| 08 | C18 | wxg import-file 写库时使用 claim 所属 feature，忽略 --feature 参数。 | gap | scripts/whyexist/commands_repo.py:193-215 |
| 08 | C19 | wxg import-file 在 prepare 阶段就校验导入器生成的 kind/id，非法 id 不落 target_ids/feature_nodes。 | gap | scripts/whyexist/commands_repo.py:164-168 |
| 08 | C20 | wxg import-repo 批量导入仓内非点路径的 Python 文件，准备/写入语义与 import-file 一致。 | partial | tests/test_plan_cli.py:567-584, scripts/whyexist/commands_repo.py:249-338 |
| 08 | C21 | import-repo 与 sync 使用同一文件集（点目录/点文件处理一致）。 | gap | scripts/whyexist/commands_repo.py:252-254, scripts/whyexist/commands_repo.py:580-583 |
| 08 | C22 | import-repo 遇任一语法错误整批失败（不写半截），错误带相对路径；sync 则逐文件记 parse_errors 后继续。 | gap | scripts/whyexist/commands_repo.py:256-259, scripts/whyexist/commands_repo.py:584-588 |
| 08 | C23 | import-repo 的输出与 import-file 对称，包含 stale 节点明细。 | gap | scripts/whyexist/commands_repo.py:218-227, scripts/whyexist/commands_repo.py:329-338 |
| 08 | C25 | wxg derive --apply 需 token/角色/全部新 component id 在 targets，写 origin=derived 的 component、contains 与 depends（x_evidence），并把旧 derived 标 stale。 | partial | scripts/whyexist/commands_repo.py:470-523, tests/test_plan_cli.py:602-626 |
| 08 | C26 | wxg derive --apply 不覆盖人工声明的同名 component（origin 与 attrs 保留）。 | gap | scripts/whyexist/commands_repo.py:488-504 |
| 08 | C27 | wxg derive 的 stale 清理也只写 token 边界内的节点。 | gap | scripts/whyexist/commands_repo.py:474-485 |
| 08 | C28 | wxg derive 只对未 stale、未 unmapped 的代码节点分组。 | gap | scripts/whyexist/commands_repo.py:438-442 |
| 08 | C29 | wxg promote 只接受 origin=derived 且 id 在 targets 的节点，需 token 与 actor。 | partial | scripts/whyexist/commands_repo.py:542-552, tests/test_plan_cli.py:629-647 |
| 08 | C31 | wxg promote 只能把节点提升进 token 所属 feature，不能跨 feature 改作用域。 | gap | scripts/whyexist/commands_repo.py:542-561 |
| 08 | C32 | wxg sync 只读，返回 files/db_nodes/planned_nodes/missing/new/changed/stale 计数与截断列表；--limit 控制列表长度；不改库。 | partial | scripts/whyexist/commands_repo.py:568-630, tests/test_wxg.py:1585-1603 |
| 08 | C33 | wxg sync 对语法错误逐文件记 parse_errors 并继续。 | gap | scripts/whyexist/commands_repo.py:584-588 |
| 08 | C34 | wxg sample 按 --repo 或 --feature 二选一，均匀随机取一个节点；--seed 可复现；返回 source/candidates/sample。 | partial | scripts/whyexist/commands_repo.py:633-659, tests/test_wxg.py:1079-1091 |
| 08 | C35 | wxg sample 对未登记 repo、不存在 feature、空作用域给出与原因相符的 Reject。 | gap | scripts/whyexist/commands_repo.py:636-656 |
| 08 | C36 | 除 verify/doctor/gate/apply/reconcile/serve 等特殊命令外，成功输出 JSON 到 stdout 且退出 0；Reject/异常输出 JSON 到 stderr 且退出 2。 | partial | scripts/whyexist/cli.py:85-113, tests/test_plan_cli.py:62-86 |
| 08 | C38 | WXG_DB_URL / --db-url 选择 SQLite、MySQL/MariaDB 或 PostgreSQL 后端；SQLite 是默认。 | gap | scripts/whyexist/db.py:425-465, tests/test_mysql_backend.py:86-99, tests/test_pg_backend.py:89-102 |
| 08 | C39 | repo 域的图写入命令（import-file/import-repo/derive --apply/promote）都要 claim_token，并限定 target_ids（I5 写入边界）。 | partial | scripts/whyexist/commands_repo.py:193-195, scripts/whyexist/commands_repo.py:470-485, scripts/whyexist/commands_repo.py:542-545 |
| 09 | C1 | feature-declare / feature-register 的 --id 只接受 [A-Za-z0-9._-]+，其他形式 Reject（退出码 2，JSON error 到 stderr） | gap | scripts/whyexist/commands_feature.py:45-46, scripts/whyexist/commands_feature.py:149-150 |
| 09 | C2 | feature-declare 要求 --acceptance/--constraints 为 JSON 数组、--statement 非空，且两者支持 @文件；不满足 Reject | gap | scripts/whyexist/commands_feature.py:47-52, scripts/whyexist/jsonio.py:34-59 |
| 09 | C5 | --drift-limit 必须 ≥0；以 COALESCE 持久化——重声明不带该参数保留旧值；没有任何命令能清除已设置的 drift_limit | partial | scripts/whyexist/commands_feature.py:59-61, scripts/whyexist/commands_feature.py:107, tests/test_wxg.py:1238-1244 |
| 09 | C6 | --conformance/--no-conformance 互斥；新建 declare 默认关闭；显式开启/关闭后重声明保留 | partial | scripts/whyexist/commands_feature.py:62-65, scripts/whyexist/commands_feature.py:77-84, tests/test_wxg.py:1758-1813 |
| 09 | C9 | feature-declare 自动 work_seed：六张工单按 model-architecture→model-structure→interact→specify-test→implement-test→observe 建依赖链，只有首张 ready，其余 blocked；target_ids 为 seed 时的 scope（通常只有 requirement） | partial | scripts/whyexist/commands_feature.py:136, scripts/whyexist/commands_feature.py:456-489, tests/test_wxg.py:270-297, tests/test_wxg.py:1455-1475 |
| 09 | C10 | feature-register 新建：只写 features（不带 coverage_epsilon/drift_limit/conformance 列）、conditions（只 Accepted=1）、requirement 节点；不派工，输出没有 work_seed；该 feature 的 coverage/drift 门禁从此为关闭状态 | partial | scripts/whyexist/commands_feature.py:172-191, tests/test_wxg.py:757-769 |
| 09 | C12 | feature-register --generation：必须大于当前代，否则 Reject；旧代所有工单（含 claimed）superseded 并清 token；新代条件只 Accepted=1；不自动 seed；输出带 superseded_previous_generation | partial | scripts/whyexist/commands_feature.py:207-232, tests/test_wxg.py:710-742 |
| 09 | C13 | feature-list 输出 {features:[{id,name,generation,conditions}]} 按 id 排序；只要有一个 feature 的条件行不齐，整条命令 Reject（不是跳过该行） | gap | scripts/whyexist/commands_feature.py:235-245, scripts/whyexist/workflow.py:45-49 |
| 09 | C14 | feature-status 固定字段集；work_items 用 target_count+target_sample(≤5) 代替完整 target_ids；phase=第一个为假的条件；evidence 列全部代、changes 列全部代、conformance 仅在开启时计算；claim_token 原样返回 | partial | scripts/whyexist/commands_feature.py:248-338, scripts/whyexist/commands_feature.py:310-317, tests/test_plan_cli.py:723-733, tests/test_plan_cli.py:776-780 |
| 09 | C15 | feature-status 与 gate 对 bite 的归属过滤不一致：gate 把「节点在作用域内但 bite 标记属于其他 feature」计入，status 只看「节点在作用域内且 bite 的 feature 为空或本 feature」，因此同一状态可能出现 status.bites=[] 而 gate FAIL | gap | scripts/whyexist/commands_feature.py:257-272, scripts/whyexist/commands_gates.py:166-187, scripts/whyexist/gates.py:14-33 |
| 09 | C17 | change id 是全局命名空间：同一 id 在任意 feature 下已存在即 Reject；未收口前再次 change-open 由 Ready=0 拒绝 | partial | scripts/whyexist/commands_feature.py:342-351, tests/test_wxg.py:1477-1489 |
| 09 | C18 | change-diff 基线：--from-generation > 当前代变更集的 from_generation > 当前代-1；基线<1 Reject；added/removed/kept 来自两代工单 evidence_ids，inherited/pending 只在匹配到当前代变更集时计算，code_anchors 只列带 repo+path 的节点 | partial | scripts/whyexist/commands_feature.py:399-453, tests/test_wxg.py:1491-1518 |
| 09 | C19 | change-diff 看不到 import-file 写过的节点：scan 路径刻意不追加 evidence_ids，只有 upsert-node/upsert-edge/bind 会追加 | gap | scripts/whyexist/commands_repo.py:216-217, scripts/whyexist/work.py:103-111, scripts/whyexist/commands_feature.py:416-423, tests/test_wxg.py:1310-1321 |
| 09 | C20 | work-seed 幂等：缺的条件各建一张 work:<f>:g<gen>:<kind>；依赖链只在「上一条件已置真且对应工单 passed」时建立；已存在工单不改状态；返回 created/existed/ready | partial | scripts/whyexist/commands_feature.py:456-489, tests/test_wxg.py:739-742 |
| 09 | C21 | work-open 对 audit Reject；已存在 ready/claimed/blocked 工单时合并 target_ids（去重）并保持状态；submitted/passed/failed 工单不能并入；不存在的 kind 新建 ready 行（depends_on=[]） | partial | scripts/whyexist/commands_feature.py:496-504, scripts/whyexist/work.py:25-60, tests/test_wxg.py:431-443, tests/test_wxg.py:884-892 |
| 09 | C22 | work-claim 前置：role 必须是 ROLES 且不能是 audit；implement-test 需 --allow-product-code；--actor 或 WXG_ACTOR 必填、1-80 个非空白字符；无 ready 时 Reject '没有可领的 ready 工单' | partial | scripts/whyexist/commands_feature.py:507-537, scripts/whyexist/workflow.py:12-20, tests/test_wxg.py:465-479, tests/test_wxg.py:527-567 |
| 09 | C23 | work-claim 原子领取（UPDATE ... WHERE status='ready' + rowcount）并写 assignee=role、claimed_by=actor、claim_token=uuid4hex、claimed_at；只发当前 generation 的工单；返回完整 target_ids 与深度 1 切片 | partial | scripts/whyexist/commands_feature.py:515-560, scripts/whyexist/db.py:93, tests/test_wxg.py:1391-1402, tests/test_wxg.py:444-463 |
| 09 | C24 | --brief 只把 slice 换成计数摘要，target_ids 仍全量返回（400 个 id ≈ 4.7KB；大仓 scan 可达 MB 级） | gap | scripts/whyexist/commands_feature.py:539-552, tests/test_wxg.py:1291-1297 |
| 09 | C25 | work-finish：需要有效 claimed token；本单 evidence_ids 必须落在 target_ids（否则 Reject）；置 submitted 并清 token；创建/重置 audit 单（id=work:<f>:g<gen>:audit:<本单 id>，target_ids/depends_on=[本单 id]，status=ready） | partial | scripts/whyexist/commands_feature.py:564-582, tests/test_wxg.py:444-463, tests/test_wxg.py:710-736 |
| 09 | C26 | work-judge 前置：role 必须 audit；actor 必填且不得等于被审单 claimed_by（claimed_by 为 NULL/空/legacy 时放行并返回 legacy_claim=true）；被审单必须 submitted；--id 可以是本单或 audit 单（用 depends_on 反查被审对象） | partial | scripts/whyexist/commands_feature.py:585-630, tests/test_wxg.py:527-567 |
| 09 | C30 | judge_history 行格式：id=jh:<uuid>，列集合与 JUDGE_HISTORY_COLUMNS 一致，每次裁决一条、只增不删；kind 为被审工单 kind（含 scan） | partial | scripts/whyexist/commands_feature.py:601-617, scripts/wxg_contract.py:174-184, tests/test_wxg.py:1102-1131 |
| 09 | C31 | work-list 只列当前 generation 的工单原始行：target_ids/depends_on 是 JSON 字符串，claim_token 原样输出，无状态过滤、无排序保证（ORDER BY id 有，但文档未承诺） | partial | scripts/whyexist/commands_feature.py:708-714, tests/test_wxg.py:350-351, tests/test_wxg.py:1470-1473 |
| 09 | C32 | 只读命令 feature-list / feature-status / change-diff / work-list 不写任何表 | gap | scripts/whyexist/commands_feature.py:235-245, scripts/whyexist/commands_feature.py:248-338, scripts/whyexist/commands_feature.py:399-453, scripts/whyexist/commands_feature.py:708-714 |
| 09 | C33 | 12 条命令都要求状态库已初始化：sqlite 下 graph.sqlite 不存在时直接退出 2 并输出 {'error':'状态库未初始化：先运行 `wxg init`'}，不创建目录 | partial | scripts/whyexist/cli.py:65-69, tests/test_wxg.py:947-955 |
| 09 | C34 | 只读入口泄漏写凭证：work-list 的 SELECT 含 claim_token，feature-status 的 work_items 也保留 claim_token，任何调用方都能拿到别人未完成的 claim 令牌 | gap | scripts/whyexist/commands_feature.py:250-254, scripts/whyexist/commands_feature.py:310-317, scripts/whyexist/commands_feature.py:711 |
| 09 | C35 | work-claim 把 role 写进 assignee，finish/judge 都不清空；只有 supersede 与 reconcile 的 release-stale-claim 会清 assignee；claimed_by 才是 actor 记录 | gap | scripts/whyexist/commands_feature.py:528-532, scripts/whyexist/commands_feature.py:571, scripts/whyexist/commands_feature.py:653-655, scripts/whyexist/commands_gates.py:68-74 |
| 09 | C36 | change-open 写入 changes.affected_json='[]'，代码里没有任何路径填充它，change-diff 也不读它 | gap | scripts/whyexist/commands_feature.py:375-379, scripts/whyexist/commands_feature.py:401-406 |
| 09 | C37 | judge(failed) 后重试单保留上一轮的 evidence_ids 与 claimed_by：重领不重置证据，失败证据会带进下一轮 | gap | scripts/whyexist/commands_feature.py:685-689 |
| 10 | C4 | 悬空 bite（node 已不存在）不计入 bites 检查，并在输出里显式给出 ignored_dangling_bites，由 doctor 清理。 | partial | scripts/whyexist/commands_gates.py:174-178, scripts/whyexist/commands_gates.py:248-249, scripts/wxg_contract.py:141, tests/test_wxg.py:391-429 |
| 10 | C5 | gate 的咬合集合 = 节点在作用于内 OR bite.feature_id 等于本 feature；即其它 feature 对共享节点的判决也会进入本 feature 的门禁。 | gap | scripts/whyexist/commands_gates.py:169-172, scripts/whyexist/gates.py:26-31, docs/audit/_probe_10.py:105-114 |
| 10 | C7 | 结构性漂移：feature 设置 drift_limit N 时，作用域内最新判决为 UNMAPPED/DOC-ONLY 的节点数 > N → FAIL；未设置只报告不拦门。 | partial | scripts/whyexist/commands_gates.py:266-272, scripts/whyexist/gates.py:58-78, tests/test_wxg.py:1220-1236 |
| 10 | C13 | 证据采信是「存在一条满足即可」：无 artifact_path 的 exit_code=0 记录、或 artifact_path 有值但 artifact_sha256 为空，都算有效；后续失败记录不会撤销。 | partial | scripts/whyexist/evidence.py:26-34, docs/audit/_probe_10.py:164-196 |
| 10 | C15 | coverage 策略开启时，gate 要求六个阶段（ArchitectureReconciled…BehaviorPassed）全部 met；不是只要求当前阶段。 | gap | scripts/whyexist/commands_gates.py:220, scripts/whyexist/commands_gates.py:313-319, scripts/whyexist/gates.py:91-109, docs/audit/_probe_10.py:80-86 |
| 10 | C17 | 覆盖公式：p=(1+d)/(10+n)；n_required=满足 p_m·(S-m)≤ε 的最小 m，p_m=(1+d)/(10+m)，m≤S。 | partial | scripts/whyexist/gates.py:36-55, scripts/whyexist/gates.py:95-97, scripts/wxg_contract.py:168-170, SKILL.md:388, tests/test_package_units.py:442-459 |
| 10 | C18 | 覆盖「命中」d = 该阶段内任一判决非 KEEP 且非 UNKNOWN 的去重节点数；历史判决不因后续 KEEP 回退。 | partial | scripts/whyexist/gates.py:92-95, scripts/wxg_contract.py:168, docs/audit/_probe_10b.py:78-84 |
| 10 | C19 | coverage 命令可用 --epsilon/--prior-p 覆盖策略，但 enforced 只看 feature 策略；ε≤0 或 prior_p∉[0,1] 不做校验。 | gap | scripts/whyexist/commands_gates.py:28-30, scripts/whyexist/gates.py:83-87, docs/audit/_probe_10b.py:60-70 |
| 10 | C22 | conformance 命令只读，不生成节点、不补写设计；gate 内嵌报告与命令输出字段不完全一致（命令有 enforced，gate 内嵌没有）。 | gap | scripts/whyexist/commands_gates.py:53-56, scripts/whyexist/commands_gates.py:250-251, docs/audit/_probe_10.py:117-121 |
| 10 | C23 | conformance 的测试覆盖只检查「存在 kind=verifies 的边指向 use_case」，不校验边源必须是 testcase。 | gap | scripts/whyexist/gates.py:265-271, scripts/wxg_contract.py:239, docs/audit/_probe_10.py:144-154 |
| 10 | C27 | claim 回收边界：claimed_at 缺失或无法解析时视为已过期；claim_ttl=0 时刚领取的工单也会被回收（now-claimed_at 以秒计 >0）。 | partial | scripts/whyexist/gates.py:349-367, scripts/whyexist/commands_gates.py:68-76, tests/test_wxg.py:1357-1374, docs/audit/_probe_10b.py:38-55 |
| 10 | C28 | reconcile 的只读待办动作包含 retry（ready+fail_reason）、coverage-gap、drift-over-limit、construction-open、stale-node，auto=false，且会阻止 converged。 | gap | scripts/whyexist/gates.py:369-398, docs/audit/_probe_10d.py:44-53, docs/audit/_probe_10c.py:51-56 |
| 10 | C32 | serve --feature <不存在的 id> 静默成功：features=[]、converged=true、退出 0。 | gap | scripts/whyexist/commands_gates.py:130-140, docs/audit/_probe_10.py:125-127 |
| 10 | C33 | serve 循环中任一 feature 抛 Reject（例如条件行缺失）会中止整趟：退出 2、stdout 无摘要；同趟已执行的 apply 写入未 commit 即关闭连接。 | gap | scripts/whyexist/commands_gates.py:127-156, docs/audit/_probe_10c.py:38-46 |
| 10 | C36 | gate/coverage 的 --json 旗标不改变任何行为；输出始终是 JSON。 | gap | scripts/wxg_contract.py:501, scripts/wxg_contract.py:622, scripts/whyexist/commands_gates.py:28, scripts/whyexist/commands_gates.py:159, docs/audit/_probe_10.py:129-134 |
| 10 | C37 | Engine.gate 与 CLI gate 同源（都调 cmd_gate），返回同一 dict 结构。 | partial | scripts/whyexist/engine.py:129-131, tests/test_engine.py:109-115 |
| 10 | C38 | coverage/conformance 在 feature 条件行不完整时仍能正常输出，gate/reconcile/serve 则拒绝（退出 2）。 | gap | scripts/whyexist/commands_gates.py:47-56, scripts/whyexist/commands_gates.py:160-161, docs/audit/_probe_10c.py:38-46, docs/audit/_probe_10c.py:58-61 |
| 11 | C1 | upsert-node/upsert-edge/bind/retract 必须先通过 _require_write：token 有效、工单处于 claimed、角色在 ROLES 里包含该命令，否则 Reject（退出码 2）。 | partial | scripts/whyexist/commands_graph.py:21, scripts/whyexist/commands_graph.py:37, scripts/whyexist/commands_graph.py:51, scripts/whyexist/commands_graph.py:80, scripts/whyexist/commands_feature.py:717-720, scripts/whyexist/work.py:63-77, tests/test_wxg.py:465-479 |
| 11 | C2 | target_ids 边界：upsert-node 校验节点 id、upsert-edge 校验 src+dst、bind 校验两端、retract 校验 node_ids 与显式 edge 的端点；id 必须精确命中或命中 * 前缀通配。 | partial | scripts/whyexist/commands_graph.py:29, scripts/whyexist/commands_graph.py:44, scripts/whyexist/commands_graph.py:52, scripts/whyexist/commands_graph.py:83, scripts/whyexist/commands_graph.py:97, scripts/whyexist/work.py:88-100, tests/test_wxg.py:473-479 |
| 11 | C5 | upsert-node 的 kind/id/attrs 校验：kind 必须在 NODE_KINDS、id 必须含冒号且前缀等于 kind、attrs 必须是对象、键必须在 ATTR_SCHEMA 或 x_ 前缀、声明类型必须匹配。 | partial | scripts/whyexist/graph.py:13-51, tests/test_wxg.py:1430-1441, tests/test_package_units.py:153-175 |
| 11 | C6 | 同 id 再 upsert-node 是整条覆盖：attrs 整体替换（未提交的键丢失）、name/repo/path/origin 缺省沿用旧值、unmapped 按 payload 重写（缺省清 0）、stale 强制清 0；返回 action=insert/update。 | gap | scripts/whyexist/graph.py:97-119, scripts/whyexist/commands_graph.py:30, docs/audit/06-graph-core.md:49 |
| 11 | C7 | upsert-node 把节点挂进 token 所属 feature 的 feature_nodes；payload.feature_id 存在时再挂到该 feature（不校验 feature 是否存在）。 | gap | scripts/whyexist/commands_graph.py:31, scripts/whyexist/graph.py:130-132, docs/audit/06-graph-core.md:51 |
| 11 | C8 | upsert-edge 校验 src/dst/kind 必填、kind ∈ EDGE_KINDS、两端节点已存在；applies 的 src 限 component/classifier/operation 且 dst 必须是 pattern；maps_to 的 src 限 use_case/component/port 且 dst 必须带 repo+path。 | partial | scripts/whyexist/graph.py:140-167, tests/test_wxg.py:1246-1275, tests/test_wxg.py:1847-1864 |
| 11 | C9 | 边 id 缺省是 edge:{kind}:{src}:{dst}；显式 id 原样使用并整行覆盖（改 src/dst/kind 都覆盖同一行）；改 kind 会生成新 id，旧边留下。 | gap | scripts/whyexist/graph.py:136-137, scripts/whyexist/graph.py:168, docs/audit/06-graph-core.md:55 |
| 11 | C10 | bind 只收 parameter/argument/assertion 节点，bind_to 必须存在；默认边 kind 来自 BIND_EDGE_KIND；parameter/argument 方向是 bind_to→node，assertion 是 node→bind_to。 | partial | scripts/whyexist/graph.py:190-213, tests/test_wxg.py:229-231, tests/test_wxg.py:608-630, docs/audit/06-graph-core.md:56 |
| 11 | C11 | bind --edge-kind 覆盖默认映射，且与节点 kind 不做交叉校验，bind_to 的 kind 也不校验（可造出 use_case -asserts-> parameter）。 | gap | scripts/whyexist/graph.py:198-206, scripts/wxg_contract.py:462, docs/audit/06-graph-core.md:57 |
| 11 | C12 | upsert-node/upsert-edge/bind 会把涉及的节点 id 去重追加进当前工单 evidence_ids；work-finish 会校验 evidence_ids 全部落在 target_ids 内。 | gap | scripts/whyexist/commands_graph.py:32, scripts/whyexist/commands_graph.py:46, scripts/whyexist/commands_graph.py:54, scripts/whyexist/work.py:103-110, scripts/whyexist/commands_feature.py:566-570 |
| 11 | C13 | retract 是硬删除：删 node、删触及它的 edge、删它的 bites、删它的 feature_nodes，并从所有非 audit 工单的 target_ids/evidence_ids 中剔除该 id（保留 * 结尾通配）；返回四个计数。 | partial | scripts/whyexist/commands_graph.py:86-106, tests/test_wxg.py:371-389, SKILL.md:214, scripts/wxg_contract.py:141 |
| 11 | C14 | retract 的边界只落到被删节点：删节点会连带删除端点不在 token target_ids 内的边；被删节点会把其他 feature/代的工单引用一并裁剪。 | gap | scripts/whyexist/commands_graph.py:86-89, scripts/whyexist/commands_graph.py:100, scripts/whyexist/commands_graph.py:63-75 |
| 11 | C15 | retract 对不存在的节点也返回 nodes_deleted 计数 +1（DELETE 不核对存在性），不存在的 edge id 静默跳过；两个参数都省略时成功返回全 0。 | gap | scripts/whyexist/commands_graph.py:85-93, scripts/whyexist/commands_graph.py:94-99 |
| 11 | C16 | 一次 CLI 调用 = 一个事务：cli 在 handler 返回后统一 commit，Reject/异常路径不 commit，SQLite 在 close 时回滚，所以 retract 中途失败不会留下半截删除。 | gap | scripts/whyexist/cli.py:71-84, scripts/whyexist/cli.py:85-93, scripts/whyexist/db.py:459-465 |
| 11 | C18 | bite 必须记录执行者：--actor 或 WXG_ACTOR，1-80 个非空白字符，否则 Reject；actor 不做身份校验、不与 ROLES/工单对账。 | partial | scripts/whyexist/commands_graph.py:112, scripts/whyexist/workflow.py:12-20, tests/test_wxg.py:527-549 |
| 11 | C20 | bite 把最新判决投影到 nodes.attrs_json.bite（有 reason 时写 x_bite_reason），保留节点已有 attrs；该投影仅供展示。 | gap | scripts/whyexist/commands_graph.py:128-133, scripts/wxg_contract.py:131 |
| 11 | C21 | bite --feature 不经过 target_ids 边界，直接把节点 INSERT OR IGNORE 进该 feature 的 feature_nodes，从而扩大作用域；不带 --feature 时 feature_id/generation/phase 全为 NULL。 | gap | scripts/whyexist/commands_graph.py:118-122, scripts/whyexist/commands_graph.py:134-141 |
| 11 | C22 | bite verdict=UNMAPPED 把 nodes.unmapped 置 1；后续 KEEP/HOLLOW 等判决不会把它清 0（只有 upsert-node 能清）。 | gap | scripts/whyexist/commands_graph.py:132-133, scripts/whyexist/commands_compiler.py:28-37, scripts/whyexist/gates.py:166, scripts/whyexist/gates.py:222 |
| 11 | C23 | evidence-record 要求 feature 存在、name/command 去空白后非空、actor 可取值；--work 存在时校验工单存在且属于该 feature；否则 Reject（退出码 2）。 | partial | scripts/whyexist/commands_graph.py:145-158, scripts/whyexist/workflow.py:30-34, tests/test_wxg.py:569-583, tests/test_wxg.py:792-801 |
| 11 | C25 | evidence-record --artifact 必须指向存在的文件；落库绝对路径与 SHA-256；产物被删除或 hash 变化后 gate FAIL、doctor 报 evidence-artifact-missing/changed。 | partial | scripts/whyexist/commands_graph.py:159-166, scripts/whyexist/evidence.py:19-35, tests/test_wxg.py:569-587, tests/test_wxg.py:589-606 |
| 11 | C26 | evidence-record 接受任意 --exit-code（含非 0）并原样落库；采信侧只认 exit_code=0，doctor 对非 0 只报提示。 | gap | scripts/whyexist/commands_graph.py:178, scripts/whyexist/evidence.py:19-24, scripts/whyexist/commands_misc.py:440-441 |
| 11 | C27 | evidence-list 返回该 feature 全部代的 evidence 行（SELECT *），按 created_at,id 排序；不提供按代/工单过滤。 | partial | scripts/whyexist/commands_graph.py:198-206, tests/test_wxg.py:581-582 |
| 11 | C28 | 写命令的成功输出是 stdout 的缩进 JSON 且退出码 0；Reject/异常是 stderr 的 {"error":...} 且退出码 2；argparse 的缺参/非法 choices 也退出 2 但输出 usage 文本。 | partial | scripts/whyexist/cli.py:85-90, scripts/whyexist/cli.py:109-113, tests/test_wxg.py:61-83 |
| 12 | C1 | export 在 <root>/export/<feature_id>/ 写六份文件，名字/标题/列来自 C.EXPORT_FILES，每份带 generation/feature_id 头；返回 {dir,generation,steps,files}，退出 0。 | partial | scripts/whyexist/commands_misc.py:22-49, scripts/whyexist/commands_misc.py:66-194, tests/test_wxg.py:264-268, tests/test_wxg.py:608-630 |
| 12 | C2 | export 的作用域是 scope_ids：feature_nodes + requirement:<feature>: 前缀 + 当前代 work_items.target_ids（含 `前缀*` 展开），不是仅 feature_nodes。 | gap | scripts/whyexist/commands_misc.py:51, scripts/whyexist/workflow.py:94-124, docs/audit/_probe_12.py:214 |
| 12 | C3 | 01 需求表每行 = 作用域内一个 requirement；能力取 attrs.statement 或 name；验收/约束取 feature 级 acceptance_json/constraints_json，用“；”连接后对每个 requirement 重复。 | gap | scripts/whyexist/commands_misc.py:54-65, docs/audit/_probe_12.py:187 |
| 12 | C4 | 02 用例 = satisfies 指向作用域内 requirement 的 use_case，按 id 去重；行的顺序来自 edges 扫描顺序（无 ORDER BY）。 | gap | scripts/whyexist/commands_misc.py:74-86, scripts/whyexist/commands_misc.py:76 |
| 12 | C5 | 04 架构 = 从 use_case 经 depends/associates/realizes 到达的 component/port，加作用域内 pattern；按 (kind,id,name) 去重并排序。 | partial | scripts/whyexist/commands_misc.py:88-107, tests/test_wxg.py:1198-1200 |
| 12 | C6 | 05 类图 = use_case contains 的 operation、contains 指向这些 operation 的 classifier、operation 的 has_input parameter；按 classifier/operation/parameter 顺序再按名称排序；property 永不出现在导出里。 | gap | scripts/whyexist/commands_misc.py:109-140, docs/audit/_probe_12.py:271, scripts/wxg_contract.py:744-750 |
| 12 | C7 | 07 数据流每条 (operation, writes→sink) 一行，步号按发现顺序递增；该 operation 的所有 asserts 断言文本用“；”拼进断言列，并在每个 sink 行重复。 | partial | scripts/whyexist/commands_misc.py:142-154, tests/test_wxg.py:264-268, docs/audit/_probe_12.py:237 |
| 12 | C8 | 07 追加“请求参数”小节；参数按 id 去重、按首次出现排序；属性列是 attrs_json 原样 JSON。 | partial | scripts/whyexist/commands_misc.py:155-162, scripts/wxg_contract.py:735-740, tests/test_wxg.py:608-630 |
| 12 | C9 | 测试规格 = verifies 指向这些 operation/use_case 的 testcase + asserts 指向 operation 的 assertion，按节点 id 去重；属性列是 attrs_json 原文。 | gap | scripts/whyexist/commands_misc.py:164-193 |
| 12 | C10 | 单元格里的 `\|` 转义成 `\\|`；空表渲染成一行全空单元格，而不是空表体。 | partial | scripts/whyexist/commands_misc.py:41-49, tests/test_wxg.py:1004-1026 |
| 12 | C11 | export 对不存在的 feature 抛 Reject（exit 2），在 ensure_feature 之前不创建导出目录。 | gap | scripts/whyexist/commands_misc.py:23, scripts/whyexist/workflow.py:30-34, docs/audit/_probe_12.py:198 |
| 12 | C12 | export 只覆盖六份已知文件，不删除目录里的旧文件；写文件发生在所有读取之后逐个进行，中途异常会留下半套产物。 | gap | scripts/whyexist/commands_misc.py:25-26, scripts/whyexist/commands_misc.py:38-39, docs/audit/_probe_12.py:194 |
| 12 | C13 | 导出目录由 feature id 拼路径；feature id 允许 `.`/`..`（正则只限字符集），`--feature ..` 会把六份 md 直接写进 <root>。 | gap | scripts/whyexist/commands_misc.py:25, scripts/whyexist/commands_feature.py:45, docs/audit/_probe_12.py:426 |
| 12 | C14 | role-prompt 输出纯文本提示词：角色名、<root>/graph.sqlite、CLI 绝对路径、ROLES 里的允许命令、五条边界；audit 走“不领工单、直接 work-judge”分支，其他角色追加 work-finish；model-architecture/model-structure 追加 pattern 提示，implement-test 追加 construction 提示。 | partial | scripts/whyexist/commands_misc.py:207-247, tests/test_wxg.py:894-902, scripts/wxg_contract.py:246-255 |
| 12 | C15 | role-prompt 在给 --token 时把 claim_token 明文写进“## 你的令牌”段，在给 --feature 时写“## feature”段，两者都不校验存在性。 | gap | scripts/whyexist/commands_misc.py:243-246, docs/audit/_probe_12.py:317 |
| 12 | C16 | 未知角色由 argparse choices 拦截（usage 文本、exit 2），cmd_role_prompt 里的 `未知角色` Reject 分支经 CLI 不可达。 | gap | scripts/whyexist/commands_misc.py:209-210, scripts/wxg_contract.py:627-630, docs/audit/_probe_12.py:319 |
| 12 | C17 | role-prompt 不需要状态库：不 connect、不创建 .why-exist，root 取 --root 或 cwd/.why-exist 的 resolve 结果。 | partial | scripts/whyexist/cli.py:62-70, scripts/whyexist/commands_misc.py:211, tests/test_wxg.py:894-898, docs/audit/_probe_12.py:311 |
| 12 | C18 | role-prompt 无条件告诉 teammate“状态库：<root>/graph.sqlite”并只给 `--root` 的 CLI 用法，不感知 WXG_DB_URL/MySQL/PostgreSQL 后端。 | gap | scripts/whyexist/commands_misc.py:211-218, scripts/whyexist/db.py:425-438 |
| 12 | C19 | contract 无 --json/--write 时把 main 契约 Markdown 打到 stdout；--section full 输出完整契约（含节点/边/属性/证据/history/导出规则/版本行）；不连库。 | gap | scripts/whyexist/commands_misc.py:250-262, scripts/wxg_contract.py:801,924, docs/audit/_probe_12.py:278-281 |
| 12 | C20 | contract --json 返回 contract_json()（32 键、argparse type 降级为字符串名），并静默忽略同时给出的 --write/--section。 | partial | scripts/whyexist/commands_misc.py:251-252, scripts/wxg_contract.py:997-1031, tests/test_wxg.py:518-525, docs/audit/_probe_12.py:297 |
| 12 | C21 | contract --write 替换第一对 begin/end 之间的全部内容，保留块外文本，返回 {written,section}；相对路径相对 SKILL_DIR（技能根）解析而不是 cwd。 | gap | scripts/whyexist/commands_misc.py:255-261, scripts/wxg_contract.py:1040-1047, docs/audit/_probe_12.py:289,301 |
| 12 | C22 | contract --write 的目标不存在或文件里没有对应 begin/end 标记时退出 2（stderr JSON）；标记顺序颠倒时 replace_block 解包抛 ValueError，同样是 exit 2。 | gap | scripts/whyexist/commands_misc.py:259-260, scripts/wxg_contract.py:1043-1047, scripts/whyexist/cli.py:85-90, docs/audit/_probe_12.py:307 |
| 12 | C23 | contract --write 用 Path.write_text 默认换行，Windows 上整文件写成 CRLF；verify 用文本模式读并 strip，因此换行差异不会报漂移。 | gap | scripts/whyexist/commands_misc.py:260, docs/audit/_probe_12.py:291, .gitattributes:3 |
| 12 | C24 | verify 对 full 块漂移给出的修复提示是 `wxg contract --write contract.md --section full`，但该相对路径解析到技能根，文件不存在，照做直接 exit 2。 | gap | scripts/whyexist/commands_misc.py:285, scripts/whyexist/commands_misc.py:257-258, docs/audit/_probe_12.py:371,417 |
| 12 | C25 | verify 把 SKILL.md 的 main 块与 references/contract.md 的 full 块分别与渲染器输出比较，不同则记 issue 并 exit 1；两处都读不到标记也算 issue。 | partial | scripts/whyexist/commands_misc.py:274-285, tests/test_wxg.py:481-501, docs/audit/_probe_12.py:371,378 |
| 12 | C26 | verify 校验 SKILL.md 以 --- 开头、frontmatter 含 `name: why-exist-graph` 与 `description:`；不符则 issue。 | gap | scripts/whyexist/commands_misc.py:287-298, docs/audit/_probe_12.py:390 |
| 12 | C27 | verify 交叉引用：50 条 COMMANDS 都有 wxg.cmd_* 处理器且都在 WRITE_MODES 里；ROLES 只引用已注册命令；ATTR_SCHEMA/BIND_EDGE_KIND 的 kind 必须存在；EXPORT_FILES 每份有列、附加小节有列；五类资源文件存在。 | partial | scripts/whyexist/commands_misc.py:299-329, tests/test_wxg.py:503-516 |
| 12 | C28 | verify 用 gen_sample 在临时目录真实建库并导出六份视图，与 references/export-sample/feat-demo 逐份文本比较；缺失/过期各记 issue；整个样例自检的异常被收成一条 `导出样例自检失败`。 | gap | scripts/whyexist/commands_misc.py:330-348, scripts/gen_sample.py:38-61, docs/audit/_probe_12.py:359,364 |
| 12 | C29 | verify 成功时返回固定六项 checks 名单与版本行；失败时返回 {ok:false, issues[]}，两者都是 stdout JSON。 | partial | scripts/whyexist/commands_misc.py:350-352, scripts/whyexist/cli.py:94-96, docs/audit/_probe_12.py:353 |
| 12 | C30 | verify 是零 DB 命令：不 connect、不在 cwd 建 .why-exist；但它会创建临时目录、建库、导出后删除。WXG_SKILL_DIR 可把“被检查的技能根”指向任意目录。 | partial | scripts/whyexist/cli.py:62-70, scripts/whyexist/commands_misc.py:271,336-338, tests/test_wxg.py:873-882, docs/audit/_probe_12.py:328 |
| 12 | C31 | verify/contract 的“字节比较”实际是文本比较：换行、块外首尾空行不影响，只有块内文本变化才报漂移；只处理第一对标记，伪造的第二对标记不被检查。 | gap | scripts/wxg_contract.py:1040-1054, scripts/whyexist/commands_misc.py:279-284, docs/audit/_probe_12.py:402,414 |
| 12 | C32 | doctor 输出固定 32 类 check（dangling-bite/orphan-edge/applies-invalid/…/audit-passed-subject-not），每条形如 {check, ...上下文}；汇总含 ok/issue_count/fixable_count/unfixable_count/unfixable_checks/by_check/truncated/issues≤200。 | partial | scripts/whyexist/commands_misc.py:355-555, scripts/whyexist/commands_misc.py:601-617, tests/test_wxg.py:408-414 |
| 12 | C34 | 不带 --fix 的 doctor 对状态库只读：两次运行主库文件 hash 不变。 | gap | scripts/whyexist/commands_misc.py:355,558-601, docs/audit/_probe_12.py:101, references/quality.md:12 |
| 12 | C35 | doctor --fix 执行六组修复：删悬空 bites、删悬空 edges、删悬空 feature_nodes、裁非 audit 工单的 target_ids/evidence_ids、清非 claimed 的 claim_token、把 meta.contract_version/schema_version 刷成当前常量；返回六组计数。 | partial | scripts/whyexist/commands_misc.py:561-600, tests/test_wxg.py:415-425, docs/audit/_probe_12.py:130,146 |
| 12 | C36 | doctor --fix 只修 DOCTOR_FIXABLE_CHECKS 的 7 类；其余 25 类（legacy 身份、applies-invalid、证据非零退出、审计配对、条件/变更一致性等）只报不修，且不会因此把 ok 变成 true。 | partial | scripts/wxg_contract.py:22-30, scripts/whyexist/commands_misc.py:602-612, tests/test_wxg.py:675-679, docs/audit/_probe_12.py:172 |
| 12 | C37 | doctor 把任何 exit_code≠0 的 evidence 记为 `evidence-exit-nonzero`（不可修）；而系统没有删除 evidence 的 CLI 命令，所以如实登记一次失败测试会让 doctor 永久红。 | gap | scripts/whyexist/commands_misc.py:440-441, docs/audit/_probe_12.py:158, scripts/wxg_contract.py:153-158 |
| 12 | C38 | doctor 校验 evidence 的 generation 非空、关联工单存在、产物文件仍存在且 hash 未变；并复算 BehaviorPassed 是否有同代有效证据。 | partial | scripts/whyexist/commands_misc.py:437-451, scripts/whyexist/commands_misc.py:528-534, scripts/whyexist/evidence.py:19-35, tests/test_wxg.py:569-606 |
| 12 | C39 | doctor 校验工单/审计配对：claimed/submitted 必须有 claimed_by，claimed 必须有 claimed_at，audit 裁决必须有 judged_by 且不等于被审工单 claimed_by，passed 工单必须有 passed 的 audit，audit passed 的被审工单必须 passed，claimed_by/judged_by=legacy 单独报。 | partial | scripts/whyexist/commands_misc.py:397-435, scripts/whyexist/commands_misc.py:542-554, tests/test_wxg.py:675-679 |
| 12 | C40 | doctor 校验每个 feature 当前代条件存在、每代 8 行且名称齐全、Ready=前七项与、BehaviorPassed 有证据。 | gap | scripts/whyexist/commands_misc.py:502-534 |
| 12 | C41 | doctor 校验 changes：from_generation<to_generation、from_condition 合法、目标代有条件行、from_condition 之前的条件必须为真（Accepted/Ready 除外）。 | partial | scripts/whyexist/commands_misc.py:468-494, tests/test_wxg.py:1535-1551 |
| 12 | C42 | doctor 校验作用域外所有 pattern 节点都有非空 applicability 与 not_applicable（不要求 applies 边）。 | gap | scripts/whyexist/commands_misc.py:496-500, scripts/wxg_contract.py:701-709 |
| 12 | C43 | doctor 比对 meta.contract_version/schema_version 与契约常量；--fix 直接 upsert 成当前值，不做结构迁移。 | partial | scripts/whyexist/commands_misc.py:537-540, scripts/whyexist/commands_misc.py:590-599, tests/test_wxg.py:402-425, docs/audit/_probe_12.py:150 |
| 12 | C44 | doctor 不校验枚举与属性类型：非法 node.kind、非法 edge.kind、非法 bite.verdict、attrs_json 不合 schema 都不会被 doctor 报出。 | gap | scripts/whyexist/commands_misc.py:355-555, scripts/whyexist/graph.py:13-41 |
| 12 | C45 | doctor 每次运行都会算两遍 doctor_report（before 未使用）；--fix 的 fixed.meta 固定为 1，即使没有版本变化。 | gap | scripts/whyexist/commands_misc.py:559, scripts/whyexist/commands_misc.py:600, docs/audit/_probe_12.py:150 |
| 12 | C46 | doctor 的 issues 最多输出 200 条，truncated 标记是否截断；by_check 统计全部问题；无法翻页取剩余部分。 | partial | scripts/whyexist/commands_misc.py:604-615, tests/test_wxg.py:414 |
| 12 | C47 | verify/contract/role-prompt 不走 connect、不创建 .why-exist；doctor/export 需要已初始化状态库，缺库时 exit 2 且不创建目录。 | partial | scripts/whyexist/cli.py:62-70, tests/test_wxg.py:873-882, tests/test_wxg.py:947-955, docs/audit/_probe_12.py:328 |
| 12 | C48 | 五条命令的 Reject/异常统一输出 stderr JSON 并 exit 2；argparse 层错误（未知 --role、非法 --section）输出 usage 文本而不是 JSON。 | partial | scripts/whyexist/cli.py:85-90, scripts/whyexist/cli.py:29-44, docs/audit/_probe_12.py:319 |
| 13 | C5 | wxg plan --level design 在过滤后节点集为空时抛 ValueError，退出码 2，无结果 JSON。 | gap | scripts/whyexist/planner.py:114-118, scripts/whyexist/cli.py:88-90 |
| 13 | C6 | code 层不做节点 kind 过滤：requirement/use_case 等设计节点也计入 node_count、layers 与反链。 | gap | scripts/whyexist/planner.py:99-109, docs/audit/_probe_13c.py |
| 13 | C9 | plan 排除 stale 节点并返回 excluded_stale 计数。 | gap | scripts/whyexist/commands_compiler.py:38-45 |
| 13 | C10 | 排除 unmapped/stale 后，它们关联的边仍留在待分析边集里，被报成 dangling.unknown_endpoint。 | gap | scripts/whyexist/commands_compiler.py:28-47, scripts/whyexist/planner.py:48-67, docs/audit/_probe_13b.py |
| 13 | C13 | 只有自环时 acyclic=false、layers=null、bottleneck 说“单点自环”，parallelism 退回 max_antichain。 | partial | tests/test_planner.py:99-101, scripts/whyexist/graph_algo.py:374-379 |
| 13 | C14 | 悬空边按三类报告：unknown_endpoint / self_loop / duplicate，不静默丢事实。 | partial | tests/test_planner.py:103-107, scripts/whyexist/planner.py:138-142, scripts/whyexist/graph_algo.py:57-85 |
| 13 | C15 | plan 输出键集合固定：feature/level/node_count/edge_count/acyclic/cyclic_components/layers/layer_count/max_antichain/parallelism/bottleneck/dangling，命令层再加 excluded_unmapped/excluded_stale（可选 hint）。 | partial | scripts/whyexist/planner.py:126-143, scripts/whyexist/commands_compiler.py:59-69, tests/test_plan_cli.py:166-182 |
| 13 | C17 | Engine.plan 与 wxg plan 输出同一份契约。 | partial | tests/test_engine.py:82-88, scripts/whyexist/engine.py:77-113 |
| 13 | C22 | wxg brief --out 把任务书写成 JSON 文件（ensure_ascii=False、indent=2、末尾换行），stdout 只返回 {written, work_item}。 | gap | scripts/whyexist/commands_compiler.py:110-116 |
| 13 | C24 | brief --out 指向不可写路径时抛 OSError，经通用异常分支变成退出码 2，error 文案前缀是 OSError: 而不是 Reject 文案。 | gap | scripts/whyexist/cli.py:88-90, scripts/whyexist/commands_compiler.py:110-114 |
| 13 | C28 | 未知节点 kind、未知边 kind、畸形条目都使 contract.ok=false 并计入 FAIL。 | partial | tests/test_blind.py:99-114, scripts/whyexist/blind.py:65-79 |
| 13 | C29 | 产出文件缺失/不可解析/顶层非 JSON 对象时给 Reject，退出码 2。 | partial | tests/test_plan_cli.py:323-334, scripts/whyexist/commands_compiler.py:123-131 |
| 13 | C30 | blind-check verdict=FAIL 时进程退出码仍为 0，不参与 CI 门禁。 | partial | tests/test_plan_cli.py:317-321, scripts/whyexist/cli.py:94-113 |
| 13 | C31 | blind-check 在检查时从库里重新生成任务书，而不是使用执行者当初拿到的那份。 | gap | scripts/whyexist/commands_compiler.py:122 |
| 13 | C33 | cycles 只分析作用域内、非 stale、kind=component/port/pattern 节点之间的 depends 边。 | partial | scripts/whyexist/commands_compiler.py:143-168 |
| 13 | C34 | cycles 输出 feature/node_count/edge_count/without/cycle_count/cycles[]，每个环带 members/shape/guidance/edges(evidence)/self_loops。 | partial | scripts/whyexist/commands_compiler.py:181-188, scripts/whyexist/cycles.py:256-284, tests/test_plan_cli.py:684-701 |
| 13 | C36 | --without 在分析前剔除指定依赖边，返回排序后的 without 列表，cycle_count 随之变化；格式错或端点不在设计层时 Reject 退出 2。 | partial | tests/test_plan_cli.py:703-721, scripts/whyexist/commands_compiler.py:170-179 |
| 13 | C37 | --break-set 按边数从小到大枚举最小断边集合，每项带 evidence 与 cost{lost_pairs,affected_count}。 | partial | tests/test_plan_cli.py:803-819, tests/test_cycles.py:57-132, scripts/whyexist/commands_compiler.py:189-210 |
| 13 | C38 | --break-set 与 --advise 不受 --without 影响：组合使用时 break_sets/advice 仍基于未移除的图。 | gap | scripts/whyexist/commands_compiler.py:189-230 |
| 13 | C40 | 最小断边集合枚举的边界：非自环边 >20 条时 truncated=true 且 break_sets=[]；每个 size 档最多返回 10 组，超出静默截断。 | partial | scripts/whyexist/cycles.py:24, scripts/whyexist/cycles.py:50-55, scripts/whyexist/cycles.py:73-79, tests/test_cycles.py:90-94 |
| 13 | C42 | cycles 输出中的 truncated 键只在带 --break-set 或 --advise 时出现。 | gap | scripts/whyexist/commands_compiler.py:210, scripts/whyexist/commands_compiler.py:229-230 |
| 13 | C43 | patch 把一次执行产出规范成 {work_item,nodes[],edges[]}：节点按 id 去重保留首个、边按三元组去重排序，写到 --out。 | partial | tests/test_reducer.py:28-56, scripts/whyexist/commands_compiler.py:246-256 |
| 13 | C44 | patch 不校验 --work 是否存在于 work_items，任意标签都接受并写进补丁。 | partial | tests/test_plan_cli.py:480-481, scripts/whyexist/commands_compiler.py:246 |
| 13 | C45 | patch 的 --result 缺失/不可解析/非对象时 Reject 退出 2；--out 不可写时走通用异常退出 2。 | gap | scripts/whyexist/commands_compiler.py:237-250 |
| 13 | C49 | apply 中途写库校验失败时不留下半截状态（同一事务回滚）。 | gap | scripts/whyexist/commands_compiler.py:284-287, scripts/whyexist/cli.py:83-84 |
| 13 | C50 | apply 不要求 claim_token/角色，也不校验 target_ids 写边界。 | partial | scripts/whyexist/commands_compiler.py:259-295, SKILL.md:450 |
| 13 | C51 | apply 不写 feature_nodes（除非补丁节点自带 feature_id）、不追加 work_items.evidence_ids、不记录 actor。 | gap | scripts/whyexist/commands_compiler.py:284-294, scripts/whyexist/graph.py:130-132 |
| 13 | C52 | apply 把补丁节点的其余字段透传给 upsert_node：origin/unmapped/feature_id 生效，stale 被 upsert_node 强制写成 0。 | gap | scripts/whyexist/commands_compiler.py:284-287, scripts/whyexist/graph.py:106-119 |
| 13 | C53 | apply 只在补丁之间比较节点内容；与库中已有节点的覆盖不产生冲突、不留审计。 | gap | scripts/whyexist/reducer.py:55-102 |
| 13 | C54 | apply 的 --patches 为空、补丁文件缺失/不可解析/非对象时 Reject 退出 2。 | partial | scripts/whyexist/commands_compiler.py:262-276 |
| 13 | C55 | apply 的退出码：合并失败 1、参数/解析/写库校验失败 2、成功或 dry-run 成功 0。 | partial | scripts/whyexist/cli.py:100-102, tests/test_plan_cli.py:448-451, tests/test_plan_cli.py:483-486 |
| 13 | C56 | impact --changed 输出反向可达 affected、正向 depends_on、以及按最短跳数拆的 direct/indirect。 | partial | tests/test_impact.py:42-116, tests/test_plan_cli.py:360-379, scripts/whyexist/impact.py:181-191 |
| 13 | C59 | cross_feature 列出作用域外的受影响节点及其所属 feature。 | partial | tests/test_impact.py:104-116, scripts/whyexist/impact.py:196-203 |
| 13 | C62 | --remove-edges 不校验端点是否存在：未知边的 lost_reachable=[]、lost_count=0、closed=true。 | gap | scripts/whyexist/commands_compiler.py:315-324, scripts/whyexist/impact.py:96-103 |
| 13 | C63 | 同时给 --changed 与 --remove-edges 时 remove-edges 静默优先，--changed 被忽略且不报参数冲突。 | gap | scripts/whyexist/commands_compiler.py:314-348, scripts/wxg_contract.py:599 |
| 13 | C65 | 两个 flag 都不给 → Reject 退出 2；--changed 空串 → Reject 2；--changed 非数组 JSON → Reject 2。 | partial | scripts/whyexist/commands_compiler.py:347-351, tests/test_plan_cli.py:741-744, tests/test_plan_cli.py:381-385 |
| 13 | C66 | --changed 支持逗号分隔、JSON 数组与 @文件三种写法。 | partial | scripts/whyexist/jsonio.py:load_id_list, tests/test_plan_cli.py:735-739, tests/test_plan_cli.py:381-385 |
| 13 | C67 | impact 只读。 | gap | scripts/whyexist/commands_compiler.py:298-359 |
| 13 | C71 | --features 只检查给定 feature；其中有不存在的 feature 时 Reject 退出 2。 | gap | scripts/whyexist/commands_compiler.py:369-375 |
| 13 | C72 | conflicts 只看当前代的 work_items，且不过滤 status：已完成/已判定的工单边界仍参与比较。 | gap | scripts/whyexist/commands_compiler.py:376-379 |
| 13 | C73 | 检出冲突时退出码仍为 0（只报告，不拦门）。 | partial | tests/test_plan_cli.py:394-399, scripts/whyexist/cli.py:94-113, SKILL.md:370 |
| 13 | C74 | 切片的参数错误统一走 Reject：stdout 空、stderr 输出 {error}、退出码 2；未捕获异常同样退出 2 但 error 是 TypeName: msg。 | partial | scripts/whyexist/cli.py:85-90 |
| 14 | C3 | insert_work(merge=True) 对已存在工单只做 target_ids 并集（保序去重），status 为 ready/claimed/blocked 时允许，其它状态抛 Reject；返回 {"action":"merge"}。 | partial | scripts/whyexist/work.py:45-55, tests/test_package_units.py:265-280 |
| 14 | C4 | insert_work(merge=False) 对已存在工单整体替换 target_ids 与 depends_on（传 None 落库为 []），不改 status；返回 {"action":"update"}。 | partial | scripts/whyexist/work.py:56-60, tests/test_package_units.py:282-287 |
| 14 | C8 | require_targets 用精确集合 + 通配前缀判定越界，越界时抛 Reject 且只列前 5 个 id；target_ids 为空时任何写入都被拒。 | partial | scripts/whyexist/work.py:88-100, tests/test_package_units.py:99-106 |
| 14 | C10 | actor_value 依次取 --actor、WXG_ACTOR，strip 后要求长度 1-80、无空白字符，否则 Reject；required=False 时缺省返回空串。 | partial | scripts/whyexist/workflow.py:12-20, tests/test_wxg.py:531-533 |
| 14 | C13 | set_condition 只做 UPDATE；目标行不存在时静默无操作，不报错、不插入。 | gap | scripts/whyexist/workflow.py:63-67 |
| 14 | C14 | recompute_ready 在条件行齐全且除 Ready 外全为 1 时把 Ready 置 1（reason="条件齐"），否则置 0；返回 ready 值。 | partial | scripts/whyexist/workflow.py:70-78, tests/test_package_units.py:387-398 |
| 14 | C16 | scope_ids 返回三个来源的并集：feature_nodes、requirement:<feature>: 前缀节点、当前代工单 target_ids（通配展开），并过滤掉库里不存在的 id。 | partial | scripts/whyexist/workflow.py:94-124, tests/test_package_units.py:418-439 |
| 14 | C19 | brief 只接收单张工单的数据（不接受工单列表），未知工单抛 Reject 退出码 2；输出里不含其它 feature 的 id。 | partial | scripts/whyexist/commands_compiler.py:76-104, tests/test_plan_cli.py:255-258, tests/test_briefing.py:122-139 |
| 14 | C20 | brief --out 把任务书写成 UTF-8 JSON（indent=2、结尾换行），无条件覆盖同名文件，并只回 {"written","work_item"}。 | gap | scripts/whyexist/commands_compiler.py:110-115 |
| 14 | C23 | produces 只约束「不在 write_boundary 里」的新节点；produces 为空（implement-test/observe/audit）时不做产出 kind 校验。 | partial | scripts/whyexist/blind.py:45,63-64, tests/test_blind.py:88-97 |
| 14 | C24 | check_output 的 known_node_kinds/known_edge_kinds 省略时，kind 合法性检查整体跳过（未知 kind 也能 PASS）。 | gap | scripts/whyexist/blind.py:40-41,65-66,78-79 |
| 14 | C25 | brief.inputs 里的节点只能作为边端点使用；若产出把它们当节点写出，判为越界。 | gap | scripts/whyexist/blind.py:43-46,61-62 |
| 14 | C26 | locality 从 1.0 起扣：越界 0.4（每多一项再 0.1）、未声明的边端点 0.3（每多一项再 0.1）、契约不符 0.3，clamp 到 [0,1] 并保留两位小数；不参与 verdict。 | partial | scripts/whyexist/blind.py:85-92, tests/test_blind.py:116-131, references/design.md:364 |
| 14 | C27 | patch 把 --result 规范化后写进 --out（覆盖），返回 {written,work_item,nodes,edges} 计数。 | partial | scripts/whyexist/commands_compiler.py:246-256, tests/test_plan_cli.py:414-446 |
| 14 | C32 | apply 不校验 claim_token、角色与 target_ids 写入边界，也不把 id 记进工单 evidence_ids；它是有意绕过写入边界的旁路。 | gap | scripts/whyexist/commands_compiler.py:259-295, scripts/wxg_contract.py:585-591, docs/PRODUCT-PLAN.md:126 |
| 14 | C33 | work-finish 要求 token 属于 claimed 工单、evidence_ids 全部落在 target_ids 内；成功后置 submitted、清 claim_token，并创建/重置 audit 单。 | partial | scripts/whyexist/commands_feature.py:564-582, scripts/whyexist/work.py:63-71,80-85, tests/test_wxg.py:444-460 |
| 14 | C35 | work-list 原样返回 work_items 行：target_ids/depends_on 是 JSON 字符串，claim_token 明文出现；与 feature-status 的裁剪形状（target_count/target_sample/depends_on 数组）不同。 | gap | scripts/whyexist/commands_feature.py:708-714, scripts/whyexist/commands_feature.py:310-317, tests/test_plan_cli.py:723-733 |
| 15 | C3 | 每条 e2e 用例使用独立临时状态库，不写工作区 ./.why-exist | partial | tests/test_wxg.py:47-58, tests/test_plan_cli.py:50-58, CONTRIBUTING.md:47 |
| 15 | C4 | 失败时输出可读 JSON 到 stderr、stdout 为空、退出码 2 | partial | scripts/whyexist/cli.py:85-90, tests/test_wxg.py:61-83,479 |
| 15 | C7 | verify 无漂移时 ok=true 退出 0；文档块被手改时非 0 且 stdout 含「过期」 | partial | tests/test_wxg.py:481-501, scripts/whyexist/commands_misc.py:269-352 |
| 15 | C11 | 状态库缺失时命令退 2 且不创建 .why-exist 目录 | partial | tests/test_wxg.py:947-955, scripts/whyexist/cli.py:66-69 |
| 15 | C19 | 状态库含 meta/repos/nodes/edges/features/conditions/work_items/feature_nodes/evidence/bites/judge_history/changes 共 12 张表 | partial | tests/test_wxg.py:157-166, tests/test_plan_cli.py:44-46, tests/test_package_units.py:244 |
| 15 | C20 | export 在 <root>/export/<feature>/ 写 6 份 Markdown | partial | tests/test_wxg.py:264-268,628-630,753-755,1004-1026,1198-1200, scripts/whyexist/commands_misc.py:22-194 |
| 15 | C22 | up 幂等；next 首步是 import-file --prepare；已存在的 feature 不重建 | partial | tests/test_plan_cli.py:337-351 |
| 15 | C27 | import-repo 递归扫描仓内全部 .py（跳过点目录） | partial | tests/test_plan_cli.py:567-584 |
| 15 | C32 | 图写入必须 token 有效、角色匹配、全部 id 落在 target_ids 内 | partial | tests/test_wxg.py:465-479, tests/test_package_units.py:289-309 |
| 15 | C40 | 并发 work-claim 只有一个成功（退出码集合 {0,2}） | gap | tests/test_mysql_backend.py:109-126, tests/test_pg_backend.py:112-129 |
| 15 | C41 | MySQL/PostgreSQL 后端 init 返回 backend=mysql/postgres、schema_version=9 | gap | tests/test_mysql_backend.py:86-89, tests/test_pg_backend.py:88-91 |
| 15 | C42 | feature-list 返回 {features:[{id,name,generation,conditions}]}，按 id 升序 | gap | scripts/whyexist/commands_feature.py:235-245, 探针 docs/audit/_probe_15e.py |
| 15 | C43 | repo-list 返回 {repos:[{id,path,language,created_at}]}，按 id 升序，只读 | gap | tests/test_wxg.py:947-955, 探针 docs/audit/_probe_15e.py |
| 15 | C44 | bind 只收 parameter/argument/assertion，方向随 kind，默认边 kind 来自 BIND_EDGE_KIND | partial | tests/test_wxg.py:229-231, scripts/whyexist/graph.py:190-213 |
| 15 | C45 | gate --json / coverage --json 改变输出形态 | gap | scripts/whyexist/commands_gates.py:159（cmd_gate 不读 args.json）, scripts/whyexist/commands_gates.py:28（cmd_coverage 同）, 探针 docs/audit/_probe_15e.py（两种调用 stdout 相同） |
| 15 | C46 | --db-url 覆盖 WXG_DB_URL；非法协议退 2 且错误进 stderr | gap | scripts/whyexist/cli.py:55-61, 探针 docs/audit/_probe_15e.py |
| 15 | C47 | WXG_ACTOR 环境变量可作为 actor 兜底 | gap | scripts/whyexist/workflow.py:12-20 |
| 15 | C48 | 相对 --root 可用（会被 resolve 成绝对路径） | gap | scripts/whyexist/cli.py:53 |
| 15 | C50 | 中文输出可被 UTF-8 解析 | partial | tests/test_wxg.py:21,66-68 |
| 15 | C54 | SQL 方言翻译：INSERT IGNORE / ON DUPLICATE KEY / VALUES(x) / ON CONFLICT DO NOTHING / ? 换 %s | partial | tests/test_package_units.py:181-222 |
| 16 | C2 | references/contract.md 的 full 契约块同样与契约渲染逐字节一致 | partial | scripts/whyexist/commands_misc.py:274-287, scripts/wxg_contract.py:1-6 |
| 16 | C3 | references/export-sample/feat-demo 的 6 份文件等于 gen_sample.py 实时导出的结果（verify 每次重新生成并逐字节比对） | partial | scripts/whyexist/commands_misc.py:330-346, scripts/gen_sample.py:38-116 |
| 16 | C4 | VERSION、CONTRACT_VERSION、CHANGELOG 最新条目三者一致，否则发布前检查失败 | gap | tools/check_docs.py:28-45, tools/preflight.py:70-73 |
| 16 | C5 | CHANGELOG 版本条目连续、无重复、最新在前；references/design.md 的编号节连续无缺号（附节不带数字） | gap | tools/check_docs.py:48-82 |
| 16 | C6 | build_release 拒绝 VERSION 与 CONTRACT_VERSION 不一致的发布（发布版本必须等于契约版本） | gap | tools/build_release.py:80-86 |
| 16 | C7 | 同一份源码重复构建得到相同 zip SHA-256（固定条目时间戳 2026-10-29、权限 0644、条目排序） | gap | tools/build_release.py:37, tools/build_release.py:89-101 |
| 16 | C8 | 发布 zip 能脱离源码仓独立运行：解压后只调包内 scripts/wxg.py，up → 最短路径 → gate PASS（退出码 0） | gap | tools/verify_release.py:66-111, tools/preflight.py:120-124 |
| 16 | C9 | 发布包恰好 63 个文件，含 SKILL.md/VERSION/CHANGELOG.md/references/scripts/tests，不含 tools/、README.md、docs/ 与 __pycache__ | partial | tools/build_release.py:33-38, tools/verify_release.py:73-75, dist/v2.92.0/manifest.json:20-339 |
| 16 | C11 | SKILL.md 写的最短路径（up → import-file --prepare → scan 链 → 六阶段 → evidence → observe → gate → export）能原样从零走到 gate PASS | partial | SKILL.md:83-102, tools/doc_flow.py:47-116 |
| 16 | C12 | README / CONTRIBUTING / HANDOFF / quality 里写的版本号、用例数、行数、脚本数与实际一致 | gap | README.md:58, README.md:117, README.md:139, README.md:179, CONTRIBUTING.md:16, docs/HANDOFF.md:14, references/quality.md:8 |
| 16 | C13 | CI 在 ubuntu + windows × Python 3.10/3.12/3.13 上跑 wxg verify 与全量 unittest，任一失败即红 | gap | .github/workflows/ci.yml:11-30 |
| 16 | C14 | 推送 v* tag 会触发 Release 工作流：先 verify + 全量测试，再确定性打包并把 zip 附到 GitHub Release | gap | .github/workflows/release.yml:3-30 |
| 16 | C15 | publish_github.py 能建仓、设 remote、打 tag、推分支与 tag、创建 Release 并上传 zip；缺 token 或工作树脏时拒绝执行 | gap | tools/publish_github.py:53-58, tools/publish_github.py:117-121, tools/publish_github.py:220-296 |
| 16 | C16 | gate PASS 退出码 0、FAIL 退出码 1；verify/doctor 按 ok 映射 0/1；apply 按 ok、reconcile 按 converged 映射 0/1；可预期拒绝与未捕获异常一律 stderr JSON + 2 | partial | scripts/whyexist/cli.py:87-105, tests/test_wxg.py:500 |
| 16 | C17 | wxg export --feature F 在 <root>/export/F/ 写 6 份只读视图，每份带 generation/feature_id/来源/说明 的 frontmatter | partial | scripts/whyexist/commands_misc.py:22-78, tests/test_wxg.py:264-268, tools/doc_flow.py:110-113 |
| 16 | C18 | 发布产物可回指到生成它的源码版本（清单里应能定位到提交） | gap | tools/build_release.py:104-116, dist/v2.92.0/manifest.json:1-12 |

## 冗余信号

| # | 条目 | 信号 | 把握 |
|---|---|---|---|
| 01 | 三个 --json 标志（gate / coverage / contract），只有 contract 真的读 args.json | commands_misc.py:251 是唯一 args.json 用法；gate 分支 cli.py:97-99 与通用分支 cli.py:112 无论如何都打印 JSON，gate --json 与 gate 输出逐字节相同 | high |
| 01 | needs_db 硬编码元组 vs 契约里的 command_write_modes | cli.py:65 手写 ('verify','contract','role-prompt','up')；契约 wxg_contract.py:640 另有一份“只读/写库”声明；verify 只检查 WRITE_MODES 键存在（commands_misc.py:306-307），从不校验两者一致 | high |
| 01 | wxg.py 的 re-export 面：132 个 whyexist 名字，74 个没有任何外部消费者 | AST 统计：132 个 whyexist 导入 = 50 个 cmd_* + 82 个 helper；helper 里只有 8 个被外部以 wxg.X 使用（connect/init_db/Reject/bind_node/upsert_edge/upsert_node/make_temp_dir/temp_dir），74 个零引用；cmd_* 只有 3 处显式 wxg.cmd_* 使用，其余靠 getattr 动态取 | high |
| 01 | DEFAULT_ROOT 定义三处，wxg.py 的副本从未使用 | cli.py:16、commands_misc.py:20、wxg.py:26；wxg.py:26 无任何引用，另外两处语义相同（import 时求值） | high |
| 01 | wxg.py 导入 `wxg_contract as C` 但全文件不用，也没有外部通过 wxg.C 访问 | wxg.py:28；随后 30-178 行没有任何 C. 引用，外部也无 wxg.C 用法 | high |
| 01 | 两套 JSON 序列化风格并用 | 错误与 serve 摘要走 jsonio.dumps（sort_keys、紧凑，cli.py:60,68,86,89；commands_gates.py:149）；成功结果走 json.dumps(indent=2, 不排序，cli.py:95,98,101,104,112) | high |
| 01 | 两个 JSON 解析入口，语义与报错文案不同 | jsonio.loads（jsonio.py:23-31，空值返回 default，用于库内 JSON 列）与 load_json_arg（jsonio.py:34-59，@文件、带行列号，用于 CLI 参数）；两者都各自 try json.loads + Reject | medium |
| 01 | `import wxg` 的双通道：__main__ 注册 + sys.path 注入 + 两处运行期 import | wxg.py:18-24 注册；cli.py:72 与 commands_misc.py:300 又各自 import wxg；contract.py:12-14 再插一次 scripts 到 sys.path | medium |
| 01 | build_parser 的 positionals 分支是死路径 | cli.py:31-32；契约 50 条命令的 positionals 全为空数组（wxg_contract.py:299 起），循环体从不执行 | high |
| 01 | whyexist.__version__ = 2.23.0，落后仓库版本 69 个发布且无人读取 | __init__.py:49；VERSION=2.92.0、wxg_contract.py:18=2.92.0；全仓 grep 只命中定义本身与 CHANGELOG.md:818 的一次同步记录 | high |
| 01 | 文档里的 wxg.py 行数已过时 | 实际 181 行（python 统计）；SKILL.md:448,472 与 docs/HANDOFF.md:16 写 176；CHANGELOG.md:88 记录“修正 181 → 176”但文件又涨回 181 | medium |
| 01 | jsonio.__all__ 漏了 load_id_list | jsonio.py:12 只有 5 个名字；load_id_list 定义在 62 行且被 4 个模块显式 import，CHANGELOG.md:638 称其为“公共解析函数” | medium |
| 02 | TOKEN_COMMANDS（scripts/wxg_contract.py:262） | 0 个读者；列 6 条，与 token=True 的 9 条不一致（漏 import-repo/derive/promote） | high |
| 02 | COMMANDS[*].token（scripts/wxg_contract.py:289-296,320-469） | 仅被 _cmd_write 的不可达 fallback 读取（:797-798）；50 条全有 WRITE_MODES | high |
| 02 | P() / positionals（scripts/wxg_contract.py:269-270,787、cli.py:31-32） | P() 无调用点；50 条命令 positionals 全空，渲染与解析分支永不执行 | high |
| 02 | _cmd_write fallback（scripts/wxg_contract.py:797-798） | WRITE_MODES 覆盖全部 50 条（tests/test_wxg.py:525），fallback 分支不可达 | high |
| 02 | DEFAULT_ROOT 三份（cli.py:16、commands_misc.py:20、wxg.py:26） | 同一表达式三处定义；wxg.py:26 那份无人读取 | high |
| 02 | SKILL_DIR 三份（wxg.py:19、commands_misc.py:19、gen_sample.py:16） | 同一路径三种推导方式，且 commands_misc 是 parent.parent.parent | medium |
| 02 | commands_repo.py 的 re-export 层（:662-735） | 35 个符号从其它命令模块再导出，但 wxg.py 直接从原模块导入；测试只用 _import_file_pairs | medium |
| 02 | commands_repo.py 重复导入 cmd_gate（:14 与 :725） | 同一名字两次 from … import | high |
| 02 | gate/coverage 的 --json（contract:501,622） | 两个 handler 都不读 args.json；只有 cmd_contract 读（commands_misc.py:251） | high |
| 02 | cmd_conformance 的 enforced 双写（commands_gates.py:53-55） | 先 bool(...) 再 if 赋 True，第二行恒为冗余 | high |
| 02 | cmd_serve 函数内 import time（commands_gates.py:152） | 模块顶部 :6 已 import time，局部重复 | high |
| 02 | import-file 与 import-repo 的写入主体（commands_repo.py:196-227 vs 301-338） | upsert 循环、feature_nodes 批量插、stale 标记三段近似复制 | high |
| 02 | Engine.plan 与 cmd_plan 的取数逻辑（engine.py:77-113 vs commands_compiler.py:23-70） | scope/unmapped/stale/edge_rows/planner.build_plan 逐行同构，无 parity 测试 | medium |
| 02 | ROLES 的模块级原地追加（wxg_contract.py:258-259） | 常量字典在 import 时被改；重载会重复追加 evidence-record | medium |
| 02 | work-list / evidence-list 与 feature-status 的重叠投影 | status 已含 work_items/evidence/bites；三条命令各自一套字段（且 token 暴露面不同） | low |
| 02 | cmd_work_judge 的 isinstance(subject, dict) 分支（commands_feature.py:627） | _resolve_subject 恒返回 dict，else 分支不可达 | medium |
| 03 | 版本号三套来源：CONTRACT_VERSION、VERSION 文件、whyexist.__version__ | __version__ 是 2.23.0（scripts/whyexist/__init__.py:49）且全仓无读取方；VERSION=2.92.0 只有 tools/ 读；文档侧 docs/HANDOFF.md:14 仍写 2.91.0、docs/PRODUCT-PLAN.md:178 写 2.67.0 | high |
| 03 | TOKEN_COMMANDS 与 COMMANDS[*].token 并行维护 | TOKEN_COMMANDS 零消费且漏掉 import-repo/derive/promote（token=True 共 9 条，它只列 6 条） | high |
| 03 | COMMON_ATTRS 与 full 契约块的硬编码公共键说明 | COMMON_ATTRS 只进 contract_json（scripts/wxg_contract.py:1009），markdown 在 scripts/wxg_contract.py:942 又手写一遍"bite / x_*"；graph.check_attrs 里是第三处字面量（bite、x_ 前缀） | high |
| 03 | DOCTOR_FIXABLE_CHECKS 与 I9 不变量正文里的同一清单 | tuple 在 scripts/wxg_contract.py:22-30，I9 文字在 :763 把 7 个检查名重抄一遍；改一处不影响另一处 | medium |
| 03 | DESIGN_ANCHOR_KINDS 放在桥接模块而不是契约文件 | 定义在 scripts/whyexist/contract.py:19，被 graph.py 的 maps_to 校验与 gates.py 的一致性检查使用，但不进 markdown/JSON——契约概念分裂在两处 | high |
| 03 | 代码层边集合定义两份 | EDGE_KINDS（scripts/wxg_contract.py:90-111）与 CODE_EDGE_KINDS=('calls','reads','writes')（scripts/whyexist/gates.py:124）各自维护 | medium |
| 03 | gate 输出 checks 名单与规则表脱钩 | commands_gates.py:237-246 硬编码 9 个检查名（bites/pattern/drift/construction/stale/conformance/conditions/evidence/coverage），GATE_RULES 有 12 条，二者无映射 | medium |
| 03 | _cmd_write 的兜底分支不可达 | scripts/wxg_contract.py:798 的 "状态库 if token else 只读" 兜底，在 verify 强制 WRITE_MODES 全覆盖后永远走不到 | low |
| 03 | P() 与 positionals 机制是死代码 | scripts/wxg_contract.py:269 定义 P()，全仓 0 次调用；50 条命令的 positionals 全为空，_cmd_params 的首个循环空转（:787） | high |
| 03 | 默认状态库目录 DEFAULT_ROOT 三份 | scripts/wxg.py:24、scripts/whyexist/cli.py:16、scripts/whyexist/commands_misc.py:20 各定义一次 Path.cwd()/'.why-exist' | medium |
| 03 | serve 的默认间隔 5 秒两处 | COMMANDS 里 --interval default=5（scripts/wxg_contract.py:514），cmd_serve 又兜底 `else 5`（scripts/whyexist/commands_gates.py:120-121） | low |
| 03 | 契约 JSON 形状无版本化 | contract_json 的 32 个键没有 schema 版本/快照测试；_jsonable 会把任何 type= 类对象降级成名字，形状变化只能被 test_wxg.py:518-525 的 6 条断言偶然拦住 | medium |
| 04 | 三份手工维护的 DDL（SCHEMA_SQL / MYSQL_SCHEMA_SQL / PG_SCHEMA_SQL） | 同一 12 表在 db.py:19-150、154-285、288-289 各写一遍；PG 版是 SQLite 版的字符串 replace；无任何测试比对列集 | high |
| 04 | 运行时 SQL 字符串翻译层（_mysql_translate / _pg_translate / _named_params） | db.py:305-320,400-422；把 SQLite 方言硬翻译成 MySQL/PG，新增 SQL 只要用错方言就静默坏；只有 8 个纯字符串单测，没有真库验证 | high |
| 04 | _MySQLConnection 与 _PgConnection 几乎逐行复制 | db.py:323-360 与 363-397：execute/executescript/commit/rollback/close 五个方法完全同构 | high |
| 04 | 两份完整性错误判定，且集合不一致 | db.py:500-505（4 个 MySQL errno + sqlstate 23*）vs wxg_mysql.py:120-157（10 个 errno）。wxg_mysql.is_integrity_error 无人调用，db._is_integrity_error 的唯一调用点又缺 import | high |
| 04 | _NoopCursor 与两个后端 wrapper 里的 PRAGMA 分支不可达 | db.py:292-302,334-342,371-379；全仓只有 connect（仅 sqlite）和 _table_columns（先按方言分流）会发 PRAGMA，mysql/pg 的 wrapper 根本走不到这两个分支 | high |
| 04 | PRAGMA foreign_keys = ON 是空操作 | db.py:461；schema 0 外键（PRAGMA foreign_key_list 全空），这条 PRAGMA 只对将来可能加的外键有意义，容易被读成「已有外键保护」 | high |
| 04 | work_items.assignee 列只写不读 | 写入 commands_feature.py:529（存 role）、在 5 处被置 NULL；12 张表逐列扫描后，只有它没有任何读取点，actor 语义由 claimed_by 承担 | high |
| 04 | meta 版本写入逻辑两份 | db.py:596-600 与 commands_misc.py:590-599 是同一段 UPSERT 的拷贝；doctor --fix 另外把 fixed["meta"]=1 写死（commands_misc.py:600），无论是否真的改了 | high |
| 04 | 迁移增列与建索引的顺序耦合 | db.py:613 executescript 一次跑完整份 DDL（含 7 个 CREATE INDEX），db.py:614 才补列；任何「索引引用新列」都会在补列前失败。当前 idx_bites_feature(db.py:126) 正好引用迁移列 generation | high |
| 04 | 级联删除有两套手写实现 | retract（commands_graph.py:86-92）与 doctor --fix（commands_misc.py:562-570）各自 DELETE bites/edges/feature_nodes；schema 没有 ON DELETE CASCADE | medium |
| 04 | 旧库迁移守卫 `_table_columns(conn, "evidence") != set()` | db.py:528；init_db 在 migrate 前已 executescript 建好 evidence 表，这个条件在唯一调用路径上恒真，是无效守卫 | high |
| 04 | db_url 的两套读取路径 | cli.py:55-56 与 engine.py:47-48 都写 os.environ；db.py:426 是唯一读取点，没有参数化入口 | medium |
| 05 | 三份 schema：SCHEMA_SQL / MYSQL_SCHEMA_SQL 手抄 / PG_SCHEMA_SQL 由字符串 .replace 派生 | db.py:19-150、154-285、289；加列要改 2-3 处，且没有任何测试断言三者表/列集合一致 | high |
| 05 | 两套 integrity-error 分类器 | db.py:500-505（errno 4 个 + sqlstate 23）与 wxg_mysql.py:120-157（errno 10 个）判定集合不同；产品只用前者，后者只有测试消费者 | high |
| 05 | 两套 SQL 脚本切分器 | db.py:347-351 / 384-388 用裸 split(';')；wxg_mysql.py:532-556 有引号/注释感知的 _split_script，产品路径不用它，只被 test_wxg_mysql.py:171 覆盖 | high |
| 05 | _named_params 没有生产调用点 | 全仓 grep 无 dict 参数形式的 conn.execute 调用；只有 test_package_units.py:140-149/225-235 在测它 | high |
| 05 | PRAGMA 翻译分支与 _NoopCursor 不可达 | db.py:334-342 / 371-379 只在调用方直接发 PRAGMA 时命中，而产品对 mysql/pg 走 _table_columns（db.py:486-497）；全仓只有 test_wxg.py:654 在 sqlite 连接上发 PRAGMA | high |
| 05 | wxg.py 的 db 内部符号 re-export 基本无消费者 | wxg.py:31-49 导出 16 个符号；全仓只有 scripts/gen_sample.py:43-45 用到 wxg.connect/init_db，其余 grep 零命中 | high |
| 05 | 会话初始化分散两层 | wxg_mysql.py:642-643 做 SET NAMES/autocommit=0；db.py:330 再做 SET SESSION ISOLATION | medium |
| 05 | dialect 分支重复三处 | db.py:468-483（ensure_db）、486-497（_table_columns）、605-616（init_db）各自 if/elif 三后端，没有统一的 Backend 抽象 | high |
| 05 | commands_repo.py 里未使用的导入 | commands_repo.py:16 导入 ensure_db、migrate_schema，模块内无引用（只有 init_db 被用） | high |
| 05 | PRAGMA foreign_keys = ON 但 schema 无任何外键 | db.py:461；SCHEMA_SQL 全文无 FOREIGN KEY/REFERENCES | high |
| 05 | db_backend() 每次连接重复解析 | cli.py:58 调一次做早失败，db.py:442 在 connect 里再调一次 | medium |
| 05 | 同一批失败模式在文档里写成已达成 | references/quality.md:49-50 的验收项与现状相反；CHANGELOG.md:1324-1325 把默认跳过的集成测试计入测试总数 | high |
| 06 | engine.plan 与 cmd_plan 各写一份取数组装 | scripts/whyexist/engine.py:77-113 vs scripts/whyexist/commands_compiler.py:23-70；Engine 版缺 level=code 的 hint，CLI 版缺 Engine 的 no-op 差异，两份已开始漂移 | high |
| 06 | engine.impact 与 cmd_impact 各写一份取数组装 | scripts/whyexist/engine.py:133-151 vs scripts/whyexist/commands_compiler.py:298-313；CLI 的 remove-edges 模式 Engine 不暴露 | high |
| 06 | 可达性实现三份 | graph_algo.reachable（graph_algo.py:240-263）无生产调用方，只在 __init__.py:27 导出与测试里用；impact.py:28-61 又自己写 _forward/_backward DFS；transitive_reachable 是第三份 | high |
| 06 | '环是否阻塞并行' 的判定规则两份 | graph_algo.py:366-380（GraphAnalysis.parallelism）与 planner.py:113-124 各自过滤 len(component)>1 并取 max | medium |
| 06 | 环检测/环分量计算入口三处 | graph_algo.topological_layers（Kahn 抛错）、_cyclic_components（SCC 过滤，graph_algo.py:157-166）、cycles._has_cycle（cycles.py:27-31 再跑一遍 SCC） | medium |
| 06 | analyze 内重复归一化与重复 SCC | analyze 先 normalize+SCC+_cyclic_components 再 max_antichain；max_antichain 内部又 normalize+SCC，transitive_reachable 再 normalize+topological_layers（graph_algo.py:331-351,383-406） | medium |
| 06 | 同一节点被写两次 feature_nodes | graph.upsert_node（graph.py:130-132）与 cmd_upsert_node（commands_graph.py:31）各写一次 INSERT OR IGNORE；feature-declare/import 路径也各自批量写 | medium |
| 06 | 节点 id 规则散在三处 | importer._node_id（importer.py:18-19）定 kind:repo:path:symbol；graph.check_node_id（graph.py:44-51）定前缀/字符集；requirement 作用域又依赖 requirement:<feature>: 前缀（commands_feature.py:127,163、workflow.py:106） | medium |
| 06 | 兼容层 re-export 残留 | wxg.py:61-72 把 graph 函数整体 re-export 供旧测试；commands_gates.py:33-44 又 re-export 编译器命令；design.md:382 提到的 whyexist/legacy.py 源码已不存在，只剩 __pycache__/legacy.cpython-312.pyc | medium |
| 06 | applies 端点 kind 列表硬编码 | graph.py:155 写死 ('component','classifier','operation')，而同文件 maps_to 用契约常量 DESIGN_ANCHOR_KINDS（contract.py:19） | low |
| 07 | "构成依赖的边 kind" 有 4 份定义，且互不相同 | derive.py:23（calls/reads/writes）、briefing.py:28（depends+calls+reads+writes）、gates.py:124（calls/reads/writes）、planner.py:35（calls/reads/writes）；四份常量各自维护，新增 kind 会漏改 | high |
| 07 | 导入写库循环写了两遍 | commands_repo.py:196-227（import-file）与 301-338（import-repo）几乎逐行相同：nodes upsert/计数、feature_nodes 批量插、edges upsert/计数、stale 标记；import-repo 的 docstring 也承认"写入语义与 import-file 一致" | high |
| 07 | 同一个仓被两套 AST 解析器扫两遍、两套错误策略 | importer.plan_python（utf-8-sig，语法错误 Reject，整批失败）vs commands_repo._import_file_pairs（errors="replace"，语法错误 continue，静默跳过）；derive 每次运行都重新 parse 全仓 | high |
| 07 | 查询命令的 re-export 兼容层已无人用 | commands_misc.py:197-204 把 cmd_find/cmd_get/cmd_slice/resolve_targets/slice_payload 从 whyexist.query 再导出，注释写"保持 CLI 分派不变"；但 cli.py:81 从 wxg 取 handler、wxg.py:75-81 直接从 query 导入，模块内部也不引用这些名字 | high |
| 07 | _node_id 的 re-export 是死兼容层 | wxg.py:73 `from whyexist.importer import _node_id, plan_python`；全仓无 wxg._node_id / wxg.plan_python 的引用（tests 也不引用），导出的理由是 wxg.py docstring 里的"旧测试仍按 wxg.xxx 访问" | high |
| 07 | "代码节点 kind" 的集合散在四处 | derive.py:20（classifier/operation/property）、commands_compiler.py:64（operation/classifier/property/sink/testcase/parameter/assertion）、gates.py:160-168（operation/classifier）、planner.py:38（设计层 DESIGN_NODE_KINDS）；同一概念不同口径 | medium |
| 07 | --limit 截断逻辑两份 | query.py:66-74（slice：nodes/edges 各自截断 + 两个 total）与 query.py:103-109（find：单列表 + total）；两处都手写 truncated 判定，语义不完全一致（slice 是 or，find 是单列表比较） | medium |
| 07 | slice payload 里的 depth:1 是废弃字段 | query.py:51 恒写 1，但没有任何消费方读取（commands_feature.py:552-560 只透传）；SKILL.md:187/design.md:733 却称"深度 1 切片" | high |
| 07 | 节点 id 生成与 id 校验分居两地，规则靠约定同步 | importer.py:18-19 生成 kind:repo:path:symbol；graph.py:44-51 校验前缀与字符集；derive.py:44-46 又定义 component:repo:key。三处字符串拼装，靠 check_node_id 兜底而不是共用构造函数 | medium |
| 07 | derive 的 import 解析与 importer 的路径计算各写一遍相对路径逻辑 | importer.py:24 用 relative_to(repo.path) 得 rel；commands_repo._module_to_rel/_resolve_relative_import（341-377）另写模块名->文件路径；derive.py:35-41 再写一次分隔符归一 | low |
| 08 | commands_repo.py 尾部 662-735 的 6 组 re-export | wxg.py 已直接从 commands_feature/commands_graph/commands_gates/commands_compiler/commands_misc 导入；仓内除 _import_file_pairs 外无人从 commands_repo 取这些符号，74 行是纯兼容层残留。 | high |
| 08 | import-file 与 import-repo 的 prepare/write 循环 | 177-215 与 276-328 逐段同构（insert_work、feature_nodes 批量插入、节点 upsert、边 upsert、stale 标记）；两处已经开始漂移（stale_nodes 输出、解析错误处理）。 | high |
| 08 | import-repo 与 sync 的整仓遍历 | 249-259 与 580-589 都是 sorted(rglob('*.py')) + plan_python；文件过滤与错误处理不同，导致 C21/C22 的行为分叉。 | high |
| 08 | cmd_gate 重复导入 | scripts/whyexist/commands_repo.py:14 与 724-725 两次 import cmd_gate。 | high |
| 08 | 未使用导入 | os/sys/ensure_db/migrate_schema/check_attrs/edge_id/dumps/load_json_arg/loads/append_evidence/get_work/get_work_by_token/target_match/work_id 在文件内无引用；它们掩盖了真正缺的 re/db_url/_is_integrity_error。 | high |
| 08 | wxg.py 与 commands_repo.py 双层 facade | wxg.py 165-178 从 commands_repo 再导出，commands_repo 又从四个模块再导出；调用链 cli → wxg → commands_repo → commands_*，多一层只增加循环导入与漏导入风险。 | high |
| 08 | up 的 gate 输出重复 | 返回体同时有 gate_result 与完整 gate；gate 里已有 result，等于同一判定两份。 | medium |
| 08 | sample 命令与 scripts/gen_sample.py 同名不同物 | wxg sample 是随机抽节点；gen_sample.py 生成 references/export-sample 导出夹具。文档与索引里两个 sample 极易混。 | medium |
| 09 | commands_feature.py 顶部三个未使用 import：append_evidence、get_work_by_token、require_targets | 本文件内除 import 行（:21,:23,:26）外 0 次引用 | high |
| 09 | _require_write 定义在 commands_feature.py:717-720，却被 commands_graph.py:11 与 commands_repo.py:664 导入，wxg.py:120 再导出 | 职责属于 work.py，本模块自己从不调用它 | high |
| 09 | 两处不可达校验：work-open 的 kind ∈ WORK_KINDS（:500-501）、change-open 的 from_condition ∈ CONDITION_TO_KIND（:346-348） | argparse choices 已经先拒绝（scripts/wxg_contract.py:412,426；探针 E6.1/E6.2） | high |
| 09 | feature-declare 与 feature-register 各写一套 features INSERT/upsert + 8 条件 INSERT | commands_feature.py:102-126 与 174-183、210-223 三处近似复制，列集合还不一致 | high |
| 09 | feature-status 与 cmd_gate 的 constructions/stale 两段循环逐字重复 | commands_feature.py:289-298 vs commands_gates.py:205-215 | high |
| 09 | bite 的 feature 归属过滤有三套实现且行为不一致 | commands_feature.py:257-272、commands_gates.py:166-187、gates.py:14-33 | high |
| 09 | work-claim 对每个依赖两次 get_work | commands_feature.py:525 同一表达式里的重复查询 | medium |
| 09 | insert_work 一律先插 ready，再单独 UPDATE status | scripts/whyexist/work.py:30-43 + commands_feature.py:480 | medium |
| 09 | changes.affected_json 恒为 '[]' 的死列 | commands_feature.py:378 写死 '[]'，全仓无其它写入/读取 | high |
| 09 | work_seed 返回 created/existed/ready 三份重叠视图 | commands_feature.py:481-489 同一批行被列三次 | low |
| 09 | assignee 与 role 同值，且 finish/judge 不清 | commands_feature.py:529-531 写 role，:571/:653 只清 token；探针 E5 | medium |
| 09 | feature-status 对 scope 内每个节点两次 get_node | commands_feature.py:289-298 两个完整循环，可合并为一次 | medium |
| 09 | JUDGE_HISTORY_COLUMNS 与 db.py 的 judge_history DDL/迁移回填两处维护列定义 | scripts/wxg_contract.py:174-184 vs scripts/whyexist/db.py:127-138,586-591 | medium |
| 09 | 测试用 force_ready 直接 UPDATE conditions 绕过状态机 | tests/test_wxg.py:110-117；change-open 的 6 个测试都靠它造 Ready | medium |
| 10 | commands_gates.py:33-44 从 commands_compiler re-export 8 个命令处理器 | 本模块自身不用它们；commands_repo.py:709-719 与 wxg.py 都直接从 commands_compiler 导入；仓内无任何 from whyexist.commands_gates import cmd_apply 之类调用 | high |
| 10 | commands_repo.py:696-705,724-725 从 commands_gates re-export 门禁命令 | wxg.py:137-146 直接从 commands_gates 导入；除测试外无模块从 commands_repo 取这些名字；形成 commands_repo→commands_gates→commands_compiler 的无用依赖链 | high |
| 10 | gates.py:402-413 从 whyexist.work re-export 9 个工单函数 | grep 只有 3 处 from .gates import，均只取 _feature_bites/_required_coverage/_truncate 与三个 report；无人从 gates 取 append_evidence/get_work 等 | high |
| 10 | 四套「哪些 bite 算本 feature」的选择实现 | commands_gates.py:166-172（gate：node in scope OR feature_id==id）、gates.py:20-31（_feature_bites：必须 in scope 且 feature_id∈{None,id}）、gates.py:61-71（drift：同 gate 但不过滤悬空）、commands_graph.py 写侧另加 feature_nodes；四者结果不同（C4/C5） | high |
| 10 | construction / stale 扫描各写两遍 | commands_gates.py:205-215 与 gates.py:384-398 用同样的 sorted(scope)+get_node+attrs 检查 | high |
| 10 | cmd_conformance 对 enforced 重复赋值 | commands_gates.py:53-55：先 bool(...) 再 if 同一条件赋 True | high |
| 10 | commands_gates.py 顶部与循环内各 import 一次 time | scripts/whyexist/commands_gates.py:5 与 152 | high |
| 10 | gate/coverage 的 --json 旗标是空操作 | commands_gates.py:28/159 从不读 args.json；cli.py:97-113 对所有结果统一打印 JSON；probe P7 输出逐字节相同 | high |
| 10 | cmd_conformance 的 limit 默认值写两遍 | argparse 默认 50（wxg_contract.py:619）+ commands_gates.py:49 的 args.limit is not None else 50 | high |
| 10 | _required_coverage 的 return scope_size 分支在合法输入下不可达 | residual(S)=0，ε>0 时必然 ≤ε；只有 NaN 等异常值会走到 gates.py:55 | medium |
| 10 | CODE_EDGE_KINDS 两处定义 | gates.py:124 与 planner.py:35 各写一份 ('calls','reads','writes')，无共享来源 | high |
| 10 | 证据产物校验两套实现 | evidence.py:26-34 与 doctor 的 commands_misc.py:446-452 各写一遍「存在 + hash 一致」，doctor 不调用 evidence_qualifies | high |
| 10 | gate 返回的 fails 列表字段名叫 hollow | commands_gates.py:252-258 对 UNNECESSARY 与 HOLLOW 共用 "hollow" 键 | medium |
| 10 | checks 9 个硬编码名字与 GATE_RULES 12 条规则无映射 | commands_gates.py:237-247 vs wxg_contract.py:129-142；docs/audit/03-contract-rules.json 已记录 | high |
| 10 | reconcile --apply 时 actions 计算两遍 | commands_gates.py:91 一次、96 一次；每次都在 gates.py:378-383 重新跑 coverage_report/drift_report | medium |
| 10 | reconcile_feature 生成 gate 结果后又把它压成 {result,reason} | commands_gates.py:97,105：完整 gate dict 被丢弃，与 gate 命令两套输出形状 | medium |
| 11 | TOKEN_COMMANDS 与真实 token 拦截 | TOKEN_COMMANDS 是零消费常量（全仓只有定义，wxg_contract.py:262）；它列 6 条，而 COMMANDS 里 token=True 有 9 条（漏 import-repo/derive/promote）。本切片的 4 条命令真正拦 token 的是 _require_write，不是它。 | high |
| 11 | token+role 校验的两套实现 | _require_write（commands_feature.py:717-720）只被本切片 4 条命令调用；commands_repo.py:193-194、298-299、470-471、543-544 四处内联 require_token+require_role，等价逻辑没有单一入口。 | high |
| 11 | feature_nodes 双向写入 | cmd_upsert_node 写一次（commands_graph.py:31），graph.upsert_node 在 payload.feature_id 存在时再写一次（graph.py:130-132）；同一次命令可能写两个 feature。 | high |
| 11 | 工单引用裁剪两份实现 | prune_work_refs（commands_graph.py:58-76）与 doctor --fix 的内联循环（commands_misc.py:571-586）做同一件事：跳过 audit、保留 * 通配、改写 target_ids/evidence_ids。判据不同（已删 id vs 不存在 id），已开始分叉。 | high |
| 11 | 命令 facade 两套 | wxg.py:147-156 从 commands_graph 导入 7 个 cmd_*，commands_repo.py:683-693 又原样 re-export 一遍同样的名字与 prune_work_refs；仓内无人从 commands_repo 取这些符号。 | high |
| 11 | "需要 token" 声明三处 | COMMANDS[name]['token']（wxg_contract.py:454-470）、WRITE_MODES（wxg_contract.py:662-668）、handler 内实际鉴权（commands_graph.py:21/37/51/80）三处独立维护；verify 只检查 WRITE_MODES 存在，不检查 token 标记与实现一致。 | high |
| 11 | 通配匹配实现多处 | target_ids 的 * 语义分散在 require_targets（work.py:88-100）、target_match（work.py:80-85）、scope_ids（workflow.py:116-121）、prune_work_refs（commands_graph.py:68）、doctor（commands_misc.py:390）、query.py:21、blind.py:23、briefing.py:57、conflicts.py:16。 | medium |
| 11 | bite 判决双重校验 | argparse choices（wxg_contract.py:475）与 cmd_bite 内的 membership 检查（commands_graph.py:110-111）重复；错误文本打印 Python list repr。 | low |
| 11 | upsert_node 的两种语义共用一个函数 | merge_attrs 参数开关（graph.py:85, 97-105）：CLI/declare/derive/promote 用覆盖，import-file/import-repo 用合并；同一 API 名承载两种写入契约。 | medium |
| 11 | evidence 列定义三份 | SQLite schema（db.py:100-113）、MySQL schema（db.py:235-247）、PG 复用 SCHEMA_SQL（db.py:289）；而 evidence-list 直接 SELECT * 输出，列名即对外契约。 | medium |
| 12 | commands_misc.py:197-204 从 whyexist.query re-export cmd_find/cmd_get/cmd_slice/resolve_targets/slice_payload | wxg.py:75-81 直接从 whyexist.query 导入；全仓没有 `from ...commands_misc import cmd_get/cmd_find/cmd_slice` 的调用点，这 8 行是拆包残留。 | high |
| 12 | commands_misc.py:15 import make_temp_dir 但全文只用 temp_dir | grep make_temp_dir 在本文件只出现在 import 行；verify 的临时目录走 temp_dir。 | high |
| 12 | commands_misc.py:559 的 before = doctor_report(conn) 计算后未使用 | 后续只用 after；每次 doctor 都多跑一遍全库检查（探针 A1 的耗时无法直接看，但代码路径确定）。 | high |
| 12 | commands_misc.py:600 fixed['meta'] = 1 是硬编码 | 无论 meta 是否变化都报 1；探针 A6 在干净库上 --fix 仍返回 meta:1，其它计数为 0。 | high |
| 12 | verify 成功输出的 checks 名单（commands_misc.py:352）与实际执行的检查块不同步 | 名单 6 项，代码实际还检查 frontmatter、资源存在、attr/bind kind、导出列；名单是手写常量，不是从检查过程收集的。 | high |
| 12 | DOCTOR_FIXABLE_CHECKS（wxg_contract.py:22-30）与 I9 正文（wxg_contract.py:763）各一份 7 项清单 | 改一处不影响另一处；verify 不比较两份文本。 | medium |
| 12 | doctor 的 32 类 check 名字散落在 20 处 issues.append，没有枚举/常量表 | check 名是字符串字面量；测试只能靠字符串匹配，新增/改名没有机械校验。 | medium |
| 12 | role-prompt 的未知角色校验与 argparse choices 双重实现 | commands_misc.py:209-210 的分支经 CLI 不可达；choices 已经拦截（探针 D4）。 | high |
| 12 | DEFAULT_ROOT 三份：cli.py:16、wxg.py:26、commands_misc.py:20 | commands_misc 的那份只作为 getattr(args,'root_path',...) 的死回退；wxg.py 的那份无人读。 | medium |
| 12 | EXPORT_RULE 文本（wxg_contract.py:744-750）与 cmd_export 的硬编码遍历逻辑两份描述 | 输出代码不读 EXPORT_RULE；verify 只比较由同一实现生成的样例，两者可以一起漂移而无人发现。 | medium |
| 12 | commands_repo.py:728-735 再导出 commands_misc 的 6 个符号，而 wxg.py:157-164 直接从 commands_misc 导入 | 双层 facade；commands_repo 的 re-export 层本身也被 08 切片标为兼容残留。 | medium |
| 12 | quality.md:43 声称 applies-invalid“有反例测试”，但 tests 里该字符串 0 次 | 文档与测试断言不一致；同理 quality.md:12 的 doctor hash 稳定性也无测试。 | high |
| 13 | Engine.plan 与 cmd_plan 两份取数+过滤逻辑 | scripts/whyexist/commands_compiler.py:23-70 与 scripts/whyexist/engine.py:77-113 几乎逐行相同；已漂移：Engine 版没有 hint。 | high |
| 13 | target_ids 通配匹配规则 6 份实现 | blind.py:21-25、briefing.py:56-59、conflicts.py:14-39、query.py:19-25、work.py:80-85、workflow.py:117-122 各写一遍“尾部 * = 前缀匹配”。 | high |
| 13 | 依赖边 kind 集合多处定义 | planner.DESIGN_EDGE_KINDS/CODE_EDGE_KINDS（planner.py:32-35）、briefing.DEPENDENCY_EDGE_KINDS（briefing.py:28，被 impact.py:19 反向依赖）、gates.CODE_EDGE_KINDS（gates.py:124）、derive.DEPENDENCY_EDGE_KINDS（derive.py:23）。 | high |
| 13 | 设计层节点 kind 三元组重复 | planner.DESIGN_NODE_KINDS（planner.py:38）与 commands_compiler.py:156 的字面量 (component, port, pattern) 各一份；hint 又用第三份 code kind 字面量（commands_compiler.py:64）。 | high |
| 13 | 编译器命令 re-export 兼容层 | commands_gates.py:33-44 与 commands_repo.py:708-719 重复导出 _brief_payload/cmd_apply/.../cmd_plan，但 wxg.py:108-118 直接从 commands_compiler 导入，没有任何调用方使用这两份转口。 | high |
| 13 | --advise 重复计算环与断边集合 | cmd_cycles 已算 find_cycles（commands_compiler.py:180），--advise 分支又在 cycles.advise_break_edges 内部再算 find_cycles 与 minimal_break_sets（cycles.py:135、143）；同时带 --break-set 时 minimal_break_sets 被执行两次。 | high |
| 13 | 纯函数返回值没人消费 | break_set_costs 返回 affected_nodes（cycles.py:113）但 CLI 只取 lost_pairs/affected_count（commands_compiler.py:203-207）；minimal_break_sets 返回 edge_count（cycles.py:49/55/78）CLI 从不读。 | high |
| 13 | cmd_impact 在 remove-edges 分支白算全部 feature 作用域 | commands_compiler.py:311-312 无条件构造 all_scopes，remove-edges 分支（314-345）完全不用它。 | high |
| 13 | cmd_conflicts 每个 feature 查两次 ensure_feature | commands_compiler.py:371-372 先校验一遍，374-375 再 ensure_feature 一遍取 generation。 | high |
| 13 | cmd_plan 重复扫描 nodes 表 | commands_compiler.py:28-32、38-43、48-51 三次全表读；每次 scope_ids 还要再读一遍 nodes（workflow.py:97）。 | medium |
| 13 | test_plan_cli.py 越界收纳非 plan 测试 | 865 行/39 个用例里只有约 24 个属于本片；up/derive/promote/gate/import/feature-status 的夹具与 test_wxg.py 重复（文件头注释自认是复制夹具）。 | high |
| 13 | plan 的 dangling 自环/重复键无任何断言 | planner.py:138-142 输出三个键，测试只用到 unknown_endpoint（tests/test_planner.py:103-107）；self_loop/duplicate 形同未验证的装饰字段。 | medium |
| 13 | cycles 自己实现 _has_cycle | cycles.py:27-31 用 SCC 重写环检测，graph_algo 里已有 _cyclic_components（graph_algo.py:157-166）与 CyclicGraph 语义。 | medium |
| 13 | layer_count 与 len(layers) 同源重复 | planner.py:134 输出 layer_count = len(layers)，layers 本身也在输出里。 | low |
| 14 | 「前缀* 通配」匹配规则至少有 9 份实现，语义还不完全一致 | work.target_match（work.py:80-85，带非字符串保护）；work.require_targets（work.py:88-100，为性能重写成精确集合+前缀元组，没有类型保护）；briefing._matches（briefing.py:56-59）；blind._matches（blind.py:21-25，docstring 自己承认「与 briefing 保持同一约定」）；workflow.scope_ids（workflow.py:117-121）；query.py:21-23；conflicts.py:16-17；commands_misc.py:390；commands_graph.py:68 | high |
| 14 | gates.py 末尾的工单状态机 re-export 块是死兼容层 | scripts/whyexist/gates.py:402-413 导入 9 个符号，只有 work_id 在模块体内使用且已由第 11 行导入；append_evidence/get_work_by_token/insert_work/require_role/require_targets/require_token/target_match 在本文件内零使用，grep 全仓也没有从 gates 反向取这些名字的调用点 | high |
| 14 | conditions 表有两个写入入口，状态机没有单一权威 | INSERT 与 Accepted 置真在 commands_feature.py:122-126 和 179-182 直接写 SQL；后续 UPDATE 走 workflow.set_condition（workflow.py:63-67）；派生 Ready 在 workflow.recompute_ready（workflow.py:70-78）；failed 的后缀重置又写在 commands_feature.py:692-695 | high |
| 14 | 工单生命周期被切成三层，work.py 的模块说明与实际内容不符 | work.py:1 自称「工单状态机：领取、令牌校验、写入边界与证据追加」，但领取在 commands_feature.py:507-561、提交在 564-582、裁决在 620-705；work.py 只有校验谓词与两条 UPDATE | high |
| 14 | 「依赖边」常量定义三份、两份同名不同值 | briefing.DEPENDENCY_EDGE_KINDS=('depends','calls','reads','writes')（briefing.py:28）；derive.DEPENDENCY_EDGE_KINDS=('calls','reads','writes')（derive.py:23）；planner 拆成 DESIGN_EDGE_KINDS/CODE_EDGE_KINDS（planner.py:32-35）；impact.py:19 直接复用 briefing 的那个 | high |
| 14 | 「任务书」概念两套实现：role-prompt 手写文案 vs brief 结构化输出 | commands_misc.py:207-247 手写角色任务书；briefing.build_brief 生成工单任务书；references/design.md:830 声称 role-prompt「调 briefing」，但 commands_misc.py 全文件没有 import briefing | medium |
| 14 | engine.py 与命令层重复取数组装（跨切片，但在 brief 这条链上共享 _brief_payload） | engine.plan（engine.py:77-113）≈ cmd_plan（commands_compiler.py:23-70）；engine.impact（engine.py:133-151）≈ cmd_impact（commands_compiler.py:305-313）；只有 brief/blind_check 走了共享的 _brief_payload（commands_compiler.py:73-104） | medium |
| 14 | 包级 __version__ 与契约版本漂移且无人读 | scripts/whyexist/__init__.py:49 "2.23.0" vs scripts/wxg_contract.py:18 CONTRACT_VERSION "2.92.0"；全仓 grep 只有这一处定义，没有读者；tools/check_docs.py 只比文档与 CONTRACT_VERSION | medium |
| 14 | condition_rows 只为 condition_flags 存在，却被当成公开导出 | scripts/whyexist/workflow.py:37-42 仅被 45-46 调用；scripts/wxg.py:97 把它和其余 10 个函数一起 re-export | low |
| 14 | brief 的禁止事项/完成定义是散落的字面量清单，与 SKILL.md 的边界叙述重复 | briefing.py:42-53 的 _FORBIDDEN/_DONE 与 SKILL.md:446-448、references/contract.md 的边界段各自表述同一组约束，没有引用关系 | low |
| 15 | CLI 夹具在四个文件里重复实现 | test_wxg.py:61-166、test_plan_cli.py:62-146、test_mysql_backend.py:59-84、test_pg_backend.py:61-86 的 cli/init_repo/declare/db_snapshot 近乎逐行相同；8 行块跨文件重复共 51 组 | high |
| 15 | SHOP_PY 夹具四份副本 | test_wxg.py:26-42、test_plan_cli.py:26-42、test_mysql_backend.py:50-53、test_pg_backend.py:52-55 | high |
| 15 | TABLES 元组重复声明 | test_wxg.py:162-163 与 test_plan_cli.py:44-45 同一份 12 表清单 | high |
| 15 | mysql 与 pg 后端 IT 互为副本 | 两个文件 140/143 行，除 URL、backend 断言与 skip 文案外结构一致；setUpClass 都是破坏性的 | high |
| 15 | gate --json / coverage --json 是死开关 | commands_gates.py 全文无 args.json 读取；实测两种调用 stdout 逐字节相同；测试仍传 20+ 次 | high |
| 15 | 三种互不相同的 DB 不可用判定 | skipUnless(WXG_TEST_MYSQL_URL)（test_mysql_backend.py:31）、skipUnless(WXG_TEST_PG_URL)（test_pg_backend.py:30）、setUpClass 抛 SkipTest（test_wxg_mysql.py:57-58） | high |
| 15 | 测试文件几乎全部未纳入版本控制 | git ls-files tests 只有 tests/test_wxg.py；HEAD 版本 42 条用例，工作区 85 条；scripts/whyexist/ 整包未跟踪 | high |
| 15 | 文档里的用例数与版本号漂移 | README.md:139 写 79 条（实际 85）、README.md:116 写 contract v1.1.0/schema v8（实际 2.92.0/9）、references/design.md:280 写 76→95 | high |
| 15 | CHANGELOG 把「381 不变」当发布门 | CHANGELOG.md 连续几十条记录只写「测试 381 不变」，把用例数当成覆盖度指标 | medium |
| 15 | verify 用例复制整棵技能树 | test_wxg.py:489-490 copytree(SKILL)，会连 dist/（13 个 zip，3.5 MB）与 docs/audit/_probe_*_tmp 里的 sqlite 一起复制 | medium |
| 15 | 根目录残留日志 | plan-test.log（1233 B，13 行手工跑测输出，*.log 已被 .gitignore 忽略） | low |
| 16 | 版本号有 5 份代码副本 + 4 份文档副本：VERSION、CONTRACT_VERSION（scripts/wxg_contract.py）、whyexist.__version__（scripts/whyexist/__init__.py:49，停在 2.23.0 且无人读）、tests/test_wxg.py:520 的硬编码断言、README:179、HANDOFF:14、quality.md:72、PRODUCT-PLAN:178 | 同一个数字要人肉同步 9 处；本次实测只有 4 处一致（VERSION / 契约 / tests/test_wxg.py:520 / CHANGELOG），其余 5 处全落后 | high |
| 16 | 每次版本 bump 都必然改动 wxg_contract.py 与 tests/test_wxg.py 这两个“非版本文件” | 对比 11 份 manifest：每一对相邻版本都同时改了 scripts/wxg_contract.py 与 tests/test_wxg.py，即使实际行为没变（v2.90→2.91→2.92 没有动 scripts/whyexist/*） | high |
| 16 | refactor-lab/ 被 40+ 行文档引用，但目录在仓库里不存在 | HANDOFF:52 把 `python refactor-lab/run_all.py` 列为“怎么验证”的第一条命令；PRODUCT-PLAN:187-190 整张验证表指向 refactor-lab/verify_*.py；CHANGELOG 与 design.md 里还有 30+ 处；`Test-Path refactor-lab` 为假 | high |
| 16 | 两条并存的发布路径：tools/publish_github.py（本地 API + git push）与 .github/workflows/release.yml（tag 触发 CI 打包发布） | 两者都会对同一个 tag 创建 Release 并上传 asset；publish_github 先推 tag 再建 Release，会与 CI 的 action-gh-release 竞争；CONTRIBUTING:52-66 同时介绍两条，没说哪条是权威 | high |
| 16 | v2.90.0 / v2.91.0 / v2.92.0 三个“发布”的运行时行为完全相同 | 相邻 manifest 差异只有 CHANGELOG.md / VERSION / references/*.md / wxg_contract.py / tests/test_wxg.py；两者都不含 docs/，而这三个版本的内容正是 docs 与 refactor-lab | high |
| 16 | 测试数量有四个互相矛盾的副本：README:139（79）、CONTRIBUTING:16（104）、quality.md:8,73（357）、README:58/117 与 HANDOFF:15,99（381） | 实测 unittest discover = 381，tests/test_wxg.py = 85；四个数字都不是笔误，是四个时代留下的快照 | high |
| 16 | 契约内容被渲染两份：SKILL.md 的 main 块与 references/contract.md 的 full 块 | 由同一契约生成、由 verify 双向比对，属于 I1 的有意设计；但每条规则文本都有两个可读副本，改措辞时要刷新两处 | low |
| 16 | tools/preflight.py 的模块 docstring 描述 4 步，实现跑 6 步 | tools/preflight.py:4 写“测试 + 文档一致性 + verify + doctor”，实际是测试/文档一致性/文档完整性/契约校验/状态库体检/报告自洽 | medium |
| 16 | 导出文件名编号 01/02/04/05/07 缺 03/06 | contract 的 EXPORT_FILES 与 6 份样例都用缺号命名，没有任何文档解释 03/06 去哪了；读文档的人会以为导出不全 | medium |
| 16 | README 与 SKILL.md 各自维护一份“已知边界” | README:161-175 有 13 条，SKILL:433-458 有 24 条，内容部分重叠（coverage、drift、conformance、变更集、回扫各出现两次），只有 SKILL 那份被文档流程引用 | medium |
| 16 | docs/HANDOFF.md 与 docs/PRODUCT-PLAN.md 各自维护状态表（版本/测试数/里程碑） | HANDOFF:12-17 与 PRODUCT-PLAN:169-180 记录同一批事实，数值互相不一致（2.91 vs 2.67；381 vs 381；refactor-lab 三个脚本 vs 不存在） | high |
| 16 | <tmp>/demo-repo 的清理逻辑在三个脚本里各写一遍，且删的是各自 root 之外的共享临时目录 | tools/preflight.py:96、tools/preflight.py:111、tools/verify_release.py:114 都是 `shutil.rmtree(tmp.parent / 'demo-repo')` | medium |

## 隐含需求（重写会静默丢掉的行为）

| # | 行为 |
|---|---|
| 01 | stdout 必须是可 json.loads 的单一 JSON 文档（除 role-prompt / 裸 contract）；测试夹具先解析 stdout、失败后仅在退出码非 0 时才去读 stderr（test_wxg.py:69-83），这个顺序本身就是契约。 |
| 01 | 错误与成功必须走不同流：stdout 成功、stderr 失败。否则夹具会把错误 JSON 当成功结果解析。 |
| 01 | “Reject 之后不写库”靠的是不 commit 就 close（sqlite3 默认隔离级别），cli 从不显式 rollback；换连接实现/换隔离级别会静默破坏这条。 |
| 01 | --root 必须解析成 realpath：Windows 上 tempfile 根可能是 8.3 短路径，测试断言拿 resolve() 后的路径和输出比对（test_wxg.py:48-51）。 |
| 01 | verify 的零副作用是给 CI/仓库根目录用的：它在仓库根跑，不能在那里生成 .why-exist/。这条需求只写在 cli.py:62-64 的注释与 SKILL.md:79。 |
| 01 | stdout 强制 UTF-8 是为了 Windows 默认 cp936 控制台下中文 JSON 不乱码；测试用 PYTHONIOENCODING 掩盖了它的必要性，删掉这行在 CI 里不会红。 |
| 01 | make_temp_dir 的 Windows 分支是给 DSH windows-acl 受限 token 沙箱用的（0o700 显式 DACL 在受限 token 下解析为空，目录创建者自己都写不进）。这条知识只存在于注释、CHANGELOG 与 DSH discussion 引用里。 |
| 01 | 临时目录前缀 'wxg-' 是人类识别与清理约定（CHANGELOG 记载早期手敲命令在仓库里堆噪音的历史），不是功能需求。 |
| 01 | wxg 模块的 __main__ 注册是为了让 Reject 类只有一份；删掉它不会立刻报错，但 except Reject 会开始失效，错误全部退化成 traceback+1。 |
| 01 | sys.path 注入 scripts/ 是为了让 `import wxg_contract` / `import gen_sample` 这两个非包模块可达；verify 依赖它（commands_misc.py:334）。 |
| 01 | DEFAULT_ROOT 在 import 时求值：进程模型下等价于 cwd，进程内复用 main() 时会过期。 |
| 01 | --db-url 直接改 os.environ 且不恢复，Engine(db_url=...) 同样如此（engine.py:47-48）——同进程内两个不同后端的状态库不可能并存。 |
| 01 | doctor 无 --fix 时也走 commit（cli.py:83-84），只是没有写入；这层“空提交”是幂等，不是契约。 |
| 02 | import-file/import-repo 的 --prepare 需要同名 feature 已存在（ensure_feature），并会写 work_items.scan 与 feature_nodes；help 的不写库指不写 nodes/edges。 |
| 02 | apply 是唯一无 claim_token、无 target_ids、无 actor 的图写入路径，且写出的节点不进 feature_nodes，因此不进入任何 feature 作用域；这是 SKILL.md:450 记录的有意例外。 |
| 02 | up 给 demo feature 显式 no_coverage=True（commands_repo.py:101），与新 feature 默认开启覆盖相反；standard 模板还会在 <root>/../demo-repo/demo.py 造样例代码。 |
| 02 | work-judge 同时接受被审工单 id 与 audit 工单 id（commands_feature.py:585-598），并由 depends_on 反查被审对象。 |
| 02 | work-claim 对 implement-test 额外要求 --allow-product-code，否则 Reject。 |
| 02 | feature-declare 的 --drift-limit 用 COALESCE 持久化：重声明不带该参数时保留旧策略；--coverage/--conformance 则各有保留已有策略的分支。 |
| 02 | import-file 带 --token 时 --feature 可以省略，feature 取自 token 所属工单；target 边界包含本次将标 stale 的旧节点。 |
| 02 | verify/contract/role-prompt/up 是仅有的四条不要求本地 sqlite 文件存在的命令；其中 up 自己连库并提交。 |
| 02 | gate/coverage 的 --json 是空开关；所有非文本结果的命令本来就输出 JSON。 |
| 02 | serve 的 stdout 格式与其它命令不同：每趟打印一行紧凑 JSON，且无论 converged 与否都退出 0。 |
| 02 | argparse 层错误（缺必填、非法 choice、未知命令）退出 2，但 stderr 是 usage 文本，不进入统一 JSON 错误通道。 |
| 02 | role-prompt --token 会把 claim_token 原样写进角色提示；contract --write 的相对路径以 SKILL_DIR 为基准，不是 cwd。 |
| 02 | 只读命令 work-list / feature-status 会返回 claimed 工单的 claim_token（bearer 凭证）。 |
| 03 | verify 用 WXG_SKILL_DIR 重定向技能根（commands_misc.py:271），这个环境变量没有出现在 SKILL.md/references/任何文档里，只有 tests/test_wxg.py:498 用。重写时不实现它，测试会挂。 |
| 03 | contract --write 的相对路径以技能根（脚本上两级）为基准，不是当前工作目录（commands_misc.py:257-258）。README 里写 `contract --write SKILL.md` 能成，正是靠这个隐含规则。 |
| 03 | contract --json 时 --write 与 --section 被静默忽略（commands_misc.py:251-252 提前 return），不报错也不提示。 |
| 03 | contract --write 在 Windows 上会把整个文件重写成 CRLF（Path.write_text 的 newline=None 转换）：实测 SKILL.md 491 行全是 CRLF、references/contract.md 344 行全是 CRLF，而 .gitattributes 要求 eol=lf，git 已经在警告"CRLF will be replaced by LF"。verify 用 read_text（通用换行）比较，看不见这个差异。 |
| 03 | 契约块只在第一对 begin/end 标记之间生效：同一文件里第二对标记的内容既不比较也不替换（实测 extract_block 返回 A，replace_block 只改第一段）。 |
| 03 | verify 的块比较先 strip("\n") 再比，块首尾多空行不会报漂移——与文档宣称的"逐字节"不完全一致。 |
| 03 | ATTR_SCHEMA 里值写 "任意" 表示跳过类型校验（graph.py:30-38 的 else 分支），这是契约文件里没有解释的魔法值。 |
| 03 | 节点属性强校验，边属性完全不校验（graph.py:184 直接 dumps payload.attrs）：同一份 attrs 语义在节点与边上不对称，契约里只有 COMMON_ATTRS 一句泛泛说明。 |
| 03 | bite 命令绕过 check_attrs 直接合并 attrs：写 bite 与 x_bite_reason 两个键（commands_graph.py:128-133）；x_bite_reason 不在 ATTR_SCHEMA、不在文档。 |
| 03 | work_items.role 就是工单 kind 字符串（work.py:36 用 kind 同时填 kind 与 role），契约把 WORK_KINDS 与 ROLES 分成两张表却没写这个身份关系。 |
| 03 | COMMANDS[*].token 只是数据标记：真正拦 token 的是各处理器的 require_token 调用，token=True 的有 9 条而 TOKEN_COMMANDS 只有 6 条——两组数据已经不一致，且没有检查。 |
| 03 | doctor 会无条件查 judge_history 与 changes 两张表（commands_misc.py:453、468），而 meta-version 检查在它们之后（:537）。旧 schema 库不会得到"版本落后"的提示，只会得到 exit 2 的 OperationalError。 |
| 03 | doctor --fix 无条件把 meta 的 contract_version / schema_version 覆写成常量值（commands_misc.py:590-599），可以在没做任何迁移的情况下把版本对齐。 |
| 03 | 生成的命令表"关键参数"列只列 required 选项与 store_true 标志，可选参数一律不出现：--fail-reason、--edge-kind、--section 在生成块里完全不可见（实测 main/full 都不含这三个字符串）。 |
| 03 | verify 会真实执行导出器（gen_sample → cmd_export）并建临时 SQLite 库；导出代码的任何运行时失败都会以"导出样例自检失败"的形式变成 verify 的一条 issue，而不是崩溃。 |
| 03 | tests/test_wxg.py:520 硬编码契约版本 2.92.0：升版本必须同时改契约、VERSION、CHANGELOG、references/contract.md（verify 会拦）与测试断言（否则测试挂）。 |
| 04 | init_db 在返回前自己 commit（db.py:615）：所以命令报错时库可能已经初始化完成——C22 的 mysql/pg init 就是这样「失败但已落库」 |
| 04 | migrate_schema 自己不 commit（db.py:602）：直接把它当公共 API 调用会留下未提交事务；它只被 init_db 调用 |
| 04 | judge_history 回填不是一次性：每次 init 都执行（db.py:585-592），靠 NOT EXISTS 去重；手工删掉的历史行会被 init 复活成 jh:<work_item_id> |
| 04 | migrated 的键名与计数是 init 输出的一部分：work_items.<col>、evidence.generation、features.<col>、nodes.stale、bites.<col>、claimed_by.legacy（值=行数）、judged_by.legacy、meta（首次 init 为 2） |
| 04 | claimed_by='legacy' 只标 claimed/submitted/passed/failed 四种状态，audit 工单永不参与（db.py:564-570） |
| 04 | judged_at 在补列时用 created_at 兜底（db.py:576-578），因此旧库的裁决时间不是真实裁决时间 |
| 04 | bites.generation 按 feature 的当前代回填，更早代的咬合会被算到当前代（db.py:554-558 + CHANGELOG.md:1450-1452） |
| 04 | evidence.generation 的两级回退：先关联工单、再 feature 当前代、都无则留 NULL（db.py:532-537），doctor 把 NULL 报成 evidence-missing-generation |
| 04 | 迁移期间不改 conditions：旧 feature 不会自动补 8 条条件行，doctor 报 missing-generation-conditions/condition-rows（commands_misc.py:502-516） |
| 04 | sqlite 连接开 WAL + busy_timeout=5000 + timeout=5s；同一时刻仍只有单写者（db.py:459-464） |
| 04 | MySQL 连接在构造时把会话隔离级别改成 READ COMMITTED（db.py:328-330），SQLite/PG 没有对应设置 |
| 04 | meta 版本号没有上界检查：更高版本的库会被 init 改写成当前版本；doctor 只看「值是否等于当前」 |
| 04 | `PRAGMA foreign_keys = ON` 在 0 外键的 schema 上是空操作，但代码/注释暗示有外键保护 |
| 04 | bites.verdict / work_items.status 等枚举列没有 CHECK，doctor 只校验 judge_history.verdict（commands_misc.py:456），不校验 bites.verdict |
| 04 | --db-url 与 Engine(db_url=) 都通过改 os.environ 生效且不恢复，同进程内无法并存两个后端的状态库（cli.py:55-56、engine.py:47-48） |
| 04 | doctor --fix 的 fixed.meta 恒为 1（commands_misc.py:600），不是真实改动计数；fixed 其余键是 rowcount |
| 04 | meta 表是「已初始化」的唯一凭据；但没有任何地方核对它是不是这个工具的表（别的 SQLite 库恰好有 meta 也会被放行） |
| 05 | 实际只验证过 MariaDB：MYSQL_SCHEMA_SQL 用了 MariaDB 扩展（CREATE INDEX IF NOT EXISTS、TEXT/LONGTEXT 字面量 DEFAULT），MySQL 8 上建表大概率报错，而文档写的是「MariaDB/MySQL」。 |
| 05 | MySQL 账号必须是 mysql_native_password；MySQL 8 默认 caching_sha2_password 下内置客户端直接连不上（wxg_mysql.py:19-27 承认，但对外的 BACKEND_RULES 没写）。 |
| 05 | 目标数据库必须事先存在：init 不建库（design.md:276）。 |
| 05 | MySQL 会话必须是 autocommit=0 + READ COMMITTED + utf8mb4，否则 work-claim 的并发语义和回滚都不对（db.py:328-330、wxg_mysql.py:641-643 只是注释，不是文档契约）。 |
| 05 | 每条 CLI 命令一个事务、末尾统一 commit（cli.py:77-84）；异常路径靠连接 close 回滚，不允许中间提交。 |
| 05 | 所有业务 SQL 必须只用 SQLite 方言的少数形态（INSERT OR IGNORE / ON CONFLICT(col) DO UPDATE SET / excluded.x / ? 占位符）；这条约定没有任何文档，翻译函数只认这几种。 |
| 05 | SQL 字面量里不能出现 ?、% 或 :name——翻译层不识别引号（db.py:400-408 实测会报 ProgrammingError）。 |
| 05 | SQL 里不能用 \|\| 做字符串拼接：迁移里用了（db.py:587），在 MySQL 上退化成逻辑或。 |
| 05 | 结果行必须是 dict 或 sqlite3.Row（按列名取值）；任何 row[0] 形式的访问在 mysql/pg 上会 KeyError。 |
| 05 | MySQL/PG 列有长度上限（id 512、path/symbol 700、claim_token 191、actor 191），SQLite 没有；超长值在 MySQL 严格模式会报错，在 INSERT IGNORE 下会被静默截断。 |
| 05 | INSERT IGNORE 的语义比 SQLite OR IGNORE 宽：MySQL 会连截断、类型转换错误一起忽略，只有警告没有异常。 |
| 05 | rowcount 语义按后端不同（MySQL = modified rows，SQLite = matched rows），migrate_schema 的计数与 doctor 的判据都间接依赖它。 |
| 05 | 非 sqlite 后端不创建 --root 目录（也不写 .why-exist），但 --root 仍决定导出目录。 |
| 05 | 后端是进程级环境变量状态，不是每调用一份配置；Engine(db_url=...) 会改写全局。 |
| 05 | WXG_DB_URL 一旦设置就无法在单条命令里显式选回 SQLite（没有 sqlite:// 支持）。 |
| 06 | 任何节点 upsert 都把 stale 清 0（graph.py:118）：重扫后人工改过的 stale 节点会被一次普通写入重新激活，这条只写在 design.md:237，没有测试。 |
| 06 | upsert 时 payload 里显式 null 会覆盖 name/repo/path/symbol/line_* 为 NULL（payload.get 的缺省值不覆盖显式 None）；探针实测 name 变 NULL。 |
| 06 | attrs 在 CLI 路径是整体替换，只有导入/declare/promote 路径用 merge_attrs=True 合并；SKILL.md:400 只讲了用一次不带 construction 的 upsert 清除标记，没讲其余 attrs 会一起消失。 |
| 06 | unmapped 标志由每次 upsert 的 payload 重写（graph.py:117）：一个被标记 unmapped 的节点若被设计角色再 upsert 一次且不带 unmapped，会静默变回已映射。 |
| 06 | upsert_edge 接受随意的自定义 id（graph.py:168），可以绕开 edge:{kind}:{src}:{dst} 约定，且没有任何格式或冲突校验。 |
| 06 | bind 的 --edge-kind 不检查与节点 kind 的匹配（probe 造出 operation -has_argument-> parameter），未知参数只被 choices 限制在三个值。 |
| 06 | has_output 边无法通过 bind 建立（choices 只有 has_input/has_argument/asserts），只能走 upsert-edge；'入参/出参' 两个方向因此不对称。 |
| 06 | find_repo 用最长路径前缀选最具体的仓（graph.py:69-72），嵌套仓/多仓登记的行为没有文档也没有测试。 |
| 06 | edges 表没有外键（db.py:44-53），写时校验只是应用层约定；dangling edge 靠 doctor 的 orphan-edge 兜底（commands_misc.py:369）。 |
| 06 | upsert_node 写 feature_nodes 时不校验 feature 是否存在（graph.py:130-132），会留下悬空作用域关联，doctor 的 feature-node-missing 检查只看另一个方向。 |
| 06 | 只有 applies 与 maps_to 校验端点语义，其余 18 种边 kind 只检查端点存在；契约文档里写的 contains/calls/reads 方向并不被强制。 |
| 06 | Engine 在未初始化目录上 connect 会先创建 .why-exist 目录与 graph.sqlite/-shm/-wal，然后才抛 Reject；cli.py:62-69 明确要求命令不要留下 0 字节库，Engine 没有遵守这条策略。 |
| 06 | Engine(db_url=...) 改的是进程级 WXG_DB_URL，close 不恢复；同进程里后续任何 db_backend()/connect() 都会继续用这个 URL。 |
| 06 | Engine.close 之后调用方法会静默重连，close 不是终止状态，也没有 closed 标志。 |
| 06 | graph_algo.reachable 在环图里会把起点算进可达集（probe：reachable(['a','b'],[('a','b'),('b','a')],'a') == {'a','b'}），与 docstring 的'不含 start 自身'冲突；同模块 transitive_reachable 则显式 seen - {start}。 |
| 07 | 节点 id 是跨表主键：work_items.target_ids / feature_nodes.node_id / bites.node_id / evidence_ids 都存字面量，没有 id 映射表；改 _node_id 的拼法或 unmapped 聚合粒度，等于要求全库重建 + 所有工单 target 重写。 |
| 07 | unmapped 聚合粒度是计数口径的一部分：plan 默认排除 unmapped、conformance 靠 unmapped 节点名做"唯一名字启发式"、sync 输出 changed_unmapped_count。把聚合改成逐调用点，会让 plan 的 excluded_unmapped、conformance 的 resolved_heuristically、sync 的 changed 全部变化。 |
| 07 | importer 在节点上写 attrs.x_lang="python" 与 origin="scan"：export/类图列 x_lang，promote 用 origin=derived 判断可否提升，conformance 用 origin 区分"derived 组件 contains 覆盖"与"真孤立"。重写导入器时漏掉这两个字段会静默改变导出与一致性报告。 |
| 07 | import-file 的 merge_attrs=True 是设计标注的唯一保护：扫描重导入不能覆盖设计角色写的 duty/x_note（test_wxg.py:353-369）。如果新实现改成整行 upsert，设计正文会被静默清空。 |
| 07 | stale 的置位/清位协议：扫描与 derive 置 stale=1，任何 upsert 都清 0；查询不过滤 stale，plan 过滤，gate 对作用域内 stale 直接 FAIL。重写时若在查询层加 stale 过滤，会改变 agent 看到的工作队列与 doctor 的可见性。 |
| 07 | derive --apply 的"工单 target 必须预先覆盖 component id"把 derive 和 work-open 流程绑在一起：tools/verify_reports.py:69-76 与 SKILL.md:374 都按 work-open component:* → derive --apply 的顺序走。 |
| 07 | derive 的 depends 依赖 commands_repo 的 import 解析器与 x_evidence 形状；conformance 把带 x_evidence 的 depends 直接视为"有代码支撑"（test_package_units.py:619-634）。改 evidence 结构会让所有 derive 出来的依赖突然变成"缺支撑"。 |
| 07 | derive --apply 不区分同 id 的人工节点：origin 改成 derived、name 改成组件键名、attrs 整体替换（探针：duty 丢失）。promote 建立的"derived→declared 唯一转换入口"在反方向上不成立，重跑 derive 会把 declared 组件降级。 |
| 07 | derive --apply 的写入边界只覆盖 component id：成员 contains 边写向 target_ids 外的节点，stale 清理按 id 前缀扫全仓。SKILL.md:463 的"target_ids 就是写入边界"对 derive 不适用，且没有文档承认这个例外。 |
| 07 | derive 的节点取数不过滤 stale（只过滤 unmapped）：stale 代码节点仍进组件，apply 时为它写 contains 边；与 plan 的"排除 stale"口径（commands_compiler.py:40-45）不一致。 |
| 07 | 组件 id 由目录深度决定（component:repo:<depth 层目录>）：改 --depth/--exclude 等于换一套 id，旧组件的精确 target 失效，只能靠 `component:repo:*` 通配兜住。这个"id 随参数漂移"的规则没有文档承认为契约。 |
| 07 | slice 的节点/边是原始 DB 行（attrs_json 字符串）而不是解析后的对象，work-claim 的 slice 字段原样继承这一点；任何"顺手统一成 attrs"都会破坏 agent 侧的消费。 |
| 07 | --limit 的语义是"节点与边各自截断到 N"，truncated 表示"任一被截断"，不是"总数不超过 N"；同时 slice 的 total 字段只在给 --limit 时出现，find 的 total 总是出现。 |
| 07 | find --path-prefix 是未转义的 SQL LIKE 前缀（% 与 _ 生效）；调用方把它当字符串前缀用时会静默扩大命中面。 |
| 07 | id 通配只支持后缀 `*`：`*:foo`、`a*b` 这类写法会被当成精确 id 进入 missing_ids，不展开也不报错；拼错的通配符产生的空切片与"作用域本来为空"无法区分。 |
| 07 | 两套源码读取策略：importer 严格 utf-8-sig（非 UTF-8 直接崩），derive 的 import 扫描 errors="replace" 并跳过语法错误。同一仓在 import-file 与 derive 下的可用性因此不同，且都没写进文档。 |
| 07 | import-file 不校验扩展名，只校验"在已登记仓内 + 仓 language=python"；命令 help 与 design.md 的"Python 源码文件"描述比实现严格。 |
| 07 | derive 的 import 解析读的是工作树当前内容，不是状态库：库里的节点集合与 depends 可能来自不同时刻的代码；重跑 derive 会用新代码覆盖旧的 depends 证据，没有版本号或快照校验。 |
| 07 | repo-add --language 是"只有一个取值的开关"：值落库并作为导入前置校验，当前没有任何语言分发逻辑；design.md:64-66 说扩展方式是在 wxg.py 增加导入器，但 wxg.py 已无此逻辑，文档过时。 |
| 08 | up 的“成功”是 bootstrap 成功，不是 gate 通过；gate FAIL 仍退出 0。 |
| 08 | up 在 <root> 的父目录创建 demo-repo/demo.py，不是 <root>/demo-repo；demo.py 已存在时不覆盖。 |
| 08 | up --template minimal 一旦带 --path 仍会登记仓，与“minimal 只建 feature”的帮助文案冲突。 |
| 08 | up 对已存在的 feature 不重置、不更新声明，只重跑 gate；对已存在的 demo 仓会 upsert path。 |
| 08 | up 的 next 命令不带 --root，照抄会落到默认 ./.why-exist。 |
| 08 | import-file 写库时只认 claim 的 feature，--feature 是 prepare 专用参数；传错不报错。 |
| 08 | import-file 的 prepare 可以把新 id 合并进一张已被领取的 scan 工单，持 token 的扫描者无需重新领取就能看到扩大的边界。 |
| 08 | import-file/import-repo 重导入只 merge attrs；节点 origin 会被 importer 的 scan 覆盖，人工声明的 origin 不保留。 |
| 08 | import-repo 跳过所有点目录/点文件；sync 不跳过，会把 .venv 里的文件报成 new。 |
| 08 | import-repo 遇到第一个语法错误就整批失败；sync 逐文件记 parse_errors 并继续。 |
| 08 | import-repo 的返回没有 stale_nodes，只有数量。 |
| 08 | derive 的 stale 清理不受 claim target_ids 约束，会改写 token 边界外的 derived 节点。 |
| 08 | derive --apply 会把同 id 的人工/declared component 覆盖成 derived，并清空其 attrs。 |
| 08 | derive 对 stale 代码节点仍参与分组与 contains 边；只有 unmapped 被排除。 |
| 08 | promote 不校验 --feature 与 token.feature_id 一致，可把节点提升进另一个 feature 的作用域。 |
| 08 | promote 经 upsert_node 会把节点的 stale 清 0，已消失代码的候选可以被“提升”回活跃。 |
| 08 | repo-add 不在登记时校验 repo id 字符；非法 id 直到 import 生成节点 id 才报错。 |
| 08 | repo-add 的 path 冲突当前抛 NameError，而不是文档承诺的可读 Reject。 |
| 08 | init 在 MySQL/PostgreSQL 上因 re/db_url 未导入而抛 NameError；对应集成测试默认 skip。 |
| 08 | sample --repo 不检查仓是否登记；不存在的仓返回“仓里还没有节点”。 |
| 08 | sync 不检查 repo.language，也不检查仓路径是否还存在；路径消失时只会报 missing。 |
| 08 | init 在全新库上也会把 meta 的两条版本写入计入 migrated。 |
| 08 | import 的“增量”不是 mtime/hash：每次都全量重解析 .py，按节点 id 集合与 name/line_start/line_end/symbol 比对；stale 由同 repo+path 下本次未出现的 id 差集决定。 |
| 08 | wxg sample 不生成任何文件；references/export-sample 由 scripts/gen_sample.py 用 feature-declare + export 生成，两者只有名字相同，没有产物交集。 |
| 09 | feature-register 新建的 feature 永远没有 coverage 策略（coverage_epsilon NULL），之后再用 feature-declare 重声明也不会打开——「新 feature 默认开启覆盖」只在 declare 入口成立（探针 E4.2/E4.3）。 |
| 09 | work-claim --brief 只裁剪 slice，target_ids 仍全量返回；scan 工单的上万 id 依旧会进 stdout（探针 E3.2：400 个 id = 4690 字符）。 |
| 09 | work-claim 没有 --feature：按 role 在所有 feature 的当前代里挑 id 最小的一张 ready 工单（探针 S5.10），多 feature 并行只能靠工单 id 顺序。 |
| 09 | work_items.assignee 被写成 role，且 finish/judge 都不清空；只有 supersede 与 reconcile 会清（探针 E5）。 |
| 09 | claim 本身没有租约/过期：claimed_at 只被 reconcile 读，TTL 默认 3600 秒，且只在显式跑 reconcile/serve 时才回收（探针 S5.8/S5.9）。 |
| 09 | --allow-product-code 对非 implement-test 角色静默无效，不报错（探针 S9.4）。 |
| 09 | feature-list 是全体成功/全体失败：任一 feature 条件行不齐，整条命令 Reject（探针 E1.1），其它 feature 也看不到。 |
| 09 | 重声明会保留 requirement 节点上手写的 attrs（包括 attrs.bite），只覆盖 name 与 attrs.statement（探针 E8.1）。 |
| 09 | change 的 id 是全局命名空间，不按 feature 隔离；跨 feature 同 id 直接 Reject（探针 S7.10）。 |
| 09 | change-open 的 --statement 只校验“给了”，空白字符串也能通过（commands_feature.py:341-396 无内容校验）。 |
| 09 | changes.affected_json 永远是 '[]'，没有任何代码或测试依赖它的内容（探针 S7.4）。 |
| 09 | judge(failed) 之后重试单保留 evidence_ids 与 claimed_by：上一轮失败证据会带进下一轮（探针 S6.12/S6.14）。 |
| 09 | feature-status 的 evidence 列表不按 generation 过滤，而 judge/gate 只认同代 evidence（commands_feature.py:281-288 vs evidence.py:19-35）。 |
| 09 | change-diff 看不到 import-file 写出的节点：scan 路径刻意不追加 evidence_ids（commands_repo.py:216-217）。 |
| 09 | audit 单从不被领取、没有 token；它只在 judge 时被同时置 passed/failed（commands_feature.py:572-581,650-656）。 |
| 09 | work-open 允许在 claimed 工单上继续合并写入边界，合并后 finish 的 evidence 校验按新边界算（探针 S4.7）。 |
| 09 | drift_limit 一旦设置无法清除：没有 --no-drift 或传 0 之外的关闭方式（探针 S2.5）。 |
| 09 | 旧代的 conditions/work_items/judge_history 永不删除，只 supersede；status 只展示当前代工单但展示全部代的 changes/evidence（探针 S2.3/S2.4）。 |
| 09 | feature-declare 每调用一次就推进 generation，即使 statement/acceptance 完全没变（探针 S2.1）。 |
| 09 | work-seed 的依赖链只在上一条件已真且对应工单 passed 时建立；change-open 继承来的条件没有工单，链从第一个缺失条件重新开始（探针 S7.6）。 |
| 10 | bite.feature_id 为 NULL 的「全局咬合」会对每一个作用域包含该节点的 feature 生效；契约文字没有描述这一点。 |
| 10 | 其它 feature 对共享节点写的咬合也会进入本 feature 的 gate（node 在 scope 即可），但不会进入本 feature 的 coverage（_feature_bites 排除）。 |
| 10 | bite.feature_id 等于本 feature 但节点已不在作用域时，gate 仍会统计该 bite（只要节点还存在）。 |
| 10 | drift_report 不检查节点是否仍存在：悬空 bite 只要判决是 UNMAPPED/DOC-ONLY，就会在 --drift-limit 下拦门，同时它又被列进 ignored_dangling_bites。 |
| 10 | drift 不按 phase 过滤：任何阶段记录的 UNMAPPED/DOC-ONLY 都计入漂移。 |
| 10 | coverage 的 hits 是历史累积：同一节点先 UNNECESSARY 后 KEEP，命中数不回落，p 永远偏高。 |
| 10 | gate 的覆盖检查要求六个阶段全部 met，而 work-judge 只检查当前将被置真的那一个阶段。 |
| 10 | coverage 命令不校验 ε>0 与 prior_p∈[0,1]；ε≤0 会让所有阶段 trivially met。 |
| 10 | coverage 的 enforced 只由 feature 策略决定，--epsilon 覆盖不会把 enforced 变成 true。 |
| 10 | coverage 报告里的 index=α^i·p 只用于展示；没有任何命令消费它来做调度（文档说「预算有限时按索引分配」）。 |
| 10 | conformance 的 verifies 边不校验源节点 kind；任何节点指向 use_case 都算测试覆盖。 |
| 10 | conformance 锚点只在作用域内找 maps_to 目标：设计节点锚到作用域外的代码节点时仍算「缺锚点」。 |
| 10 | evidence_qualifies 接受无产物的 exit_code=0 记录（只证明有人登记过），也接受有产物但 hash 为空的记录。 |
| 10 | evidence_qualifies 只要有一条合格证据就返回 true；后续失败证据不影响。 |
| 10 | reconcile 的 retry/coverage-gap/drift-over-limit/construction-open/stale-node 五类动作没有文档、没有测试，但会阻止 converged 并出现在 serve 的 JSON 里。 |
| 10 | reconcile --apply 的 applied 列表可能包含实际 rowcount=0 的 release-stale-claim（并发下误报）。 |
| 10 | claim_ttl=0 时任何已被领取的工单立即过期；claimed_at 缺失/解析失败也当过期处理。 |
| 10 | serve 恒以 0 退出，即使 converged=false；reconcile 用 1 表达同一状态。 |
| 10 | serve --feature 未知时静默成功（features=[], converged=true）。 |
| 10 | serve 循环里任一 feature 的 Reject 会中止整趟（退出 2、无摘要）；同趟 apply 已执行但未 commit 的写入随连接关闭丢失。 |
| 10 | serve --apply 每趟 commit；reconcile --apply 在命令结束时由 cli 统一 commit。 |
| 10 | gate/coverage 的 --json 是空旗标，所有命令默认输出 JSON。 |
| 10 | gate 的错误路径走 stderr + 退出 2，stdout 为空；脚本若只读 stdout 会拿到空串。 |
| 10 | gate 的 conformance 子报告缺少 enforced 字段；conformance 命令输出有。 |
| 10 | reconcile 的 gate 子对象只有 result/reason，CI 无法从 reconcile 结果里读到 checks 明细。 |
| 11 | upsert-node 的 attrs 是整体替换：设计角色 upsert 一次、不带原来手写的键，`duty`/`x_note` 等标注会消失；SKILL.md:400 只说了用「不含 construction 的 upsert」清标记，没说其余 attrs 会一起没。 |
| 11 | upsert-node 会把 nodes.unmapped 按 payload 重写（缺省清 0）、把 stale 强制清 0：一次手工 upsert 就能让节点重新进入 plan/conformance 的默认集合。 |
| 11 | upsert-node 会同时写 token 所属 feature 与 payload.feature_id 的 feature_nodes，且不校验后者存在；这是唯一能在一条命令里跨两个 feature 扩作用域的图写入口。 |
| 11 | upsert-edge 的 id 由 kind 派生：改 kind 不是「改一条边」，而是新边 + 旧边残留；同一对端点可以并存多条不同 kind 的边。 |
| 11 | bind 的 --edge-kind 与节点 kind、bind_to 的 kind 都不交叉校验；asserts 可以挂到 use_case→parameter 上，图里会出现语义错边而没有任何报警。 |
| 11 | 图写入追加的 work_items.evidence_ids 是 change-diff 与 work-finish 边界的真实数据源，而不是证据表；删节点时它也会被裁剪，等于抹掉「这张单写过哪些节点」的痕迹。 |
| 11 | retract 是硬删除且没有任何撤销/软删标记；被删节点 id 从工单 target_ids 移除后，同一工单再次提交不会报错。 |
| 11 | retract 的计数不可信：不存在的节点也计 1，不存在的边静默 0；调用方无法区分「删了」和「本来就没有」。 |
| 11 | retract 只删节点关联的边和 bite；外部遗留的悬空边/悬空 bite 只能靠 doctor --fix 清理（契约把这条写进了 GATE_RULES）。 |
| 11 | bite 无 token、无 target 边界：它是唯一没有 claim 门槛的图写入口，写 bites + nodes.attrs_json，还能借 --feature 把节点塞进 feature 作用域，从而改变 coverage.scope_size 与 gate 的作用域。 |
| 11 | bite 不传 --feature 时 bites.feature_id/generation/phase 全为 NULL；这些行不进 coverage 的分阶段统计，但 attrs.bite 仍被改写，看起来像「咬过了」。 |
| 11 | bite verdict=UNMAPPED 把 nodes.unmapped 置 1 且不可逆（后续 KEEP 不清），于是「结构性漂移」的判决会反过来改变 plan 的节点集合与 conformance 的启发式解析。 |
| 11 | bite 的 actor 是自由文本：不校验身份、不与 roles/工单关联；gate 的「审计独立性」只比较字符串。 |
| 11 | evidence-record 允许 exit_code 非 0 落库；只有采信侧（evidence_qualifies）过滤 0，doctor 只报提示，所以「失败证据」是合法记录且不影响行为。 |
| 11 | evidence-record 的 --artifact 只校验「存在且是文件」，不校验路径是否在仓/项目内，也不在登记时阻止后续 hash 变化（靠 doctor/gate 兜底）。 |
| 11 | evidence-record 的 --work 可以把证据写进旧 generation，这是补历史证据的唯一路径，也是唯一能绕过「当前代」写入的地方。 |
| 11 | evidence-list 返回 SELECT * 的原始行：列名与集合就是 CLI 契约，且不按代过滤，旧代证据会与新代混在一起。 |
| 11 | CLI 的默认 root 在模块导入时用 Path.cwd() 计算（cli.py:16），`--db-url` 会写进 os.environ（cli.py:55-56）：同进程后续调用会被静默改后端。 |
| 12 | export 的作用域会吸收当前代 work_items.target_ids 里的通配模式；只改 feature_nodes 不一定改变导出内容。 |
| 12 | 01 的“验收/约束”是 feature 级字段，对每个 requirement 行重复；不是每个 requirement 自己的字段。 |
| 12 | 07 的断言列在每个 writes→sink 行都重复一遍；同一 operation 多 sink 时会出现相同的断言文本多行。 |
| 12 | 02/05/07/测试规格 的行顺序依赖 SQL 返回顺序（多处无 ORDER BY）；SQLite 下稳定，MySQL/PG 下不保证跨后端字节一致。 |
| 12 | 05 永远不导出 property 节点，即使 classifier contains property；导出规则文本与节点 kind 表存在这一层缺口。 |
| 12 | 空表渲染为一行全空单元格，消费者必须把“全空行”当作无数据，而不是空表。 |
| 12 | export 不清理导出目录里的旧文件；EXPORT_FILES 改名/减项后旧文件会一直留着。 |
| 12 | export 不是原子操作：六份文件逐个写，第 N 份失败会留下前 N-1 份新内容 + 旧内容混合。 |
| 12 | feature id 允许 `.` 与 `..`；`--feature ..` 会把六份视图写到 <root> 根目录，`export/` 目录根本不存在。 |
| 12 | role-prompt 把 --token 明文写进提示词，提示词天然会被复制/转发；没有脱敏或一次性令牌概念。 |
| 12 | role-prompt 不读 WXG_DB_URL，MySQL/PostgreSQL 后端下仍宣称状态库是 <root>/graph.sqlite。 |
| 12 | role-prompt 的 root 是调用时 --root 或 cwd 的绝对路径；提示词换机器/换目录后路径失效。 |
| 12 | contract --write 的相对路径以技能根解析，不是 cwd；HANDOFF 里的 `--write SKILL.md` 依赖这一点。 |
| 12 | contract --json 与 --write 同时给时，--json 静默胜出，文件不被修改。 |
| 12 | contract --write 在 Windows 上把整个文件改写成 CRLF，即使原文件是 LF；verify 看不见这个差异。 |
| 12 | verify 只检查第一对 begin/end；文件里可以有第二对伪造标记而不被发现。 |
| 12 | verify 的比较是“文本相等 + strip 块外换行”，不是逐字节；块内行尾空格会报漂移，换行符不会。 |
| 12 | verify 的 full 块修复提示丢了 references/ 前缀，照提示执行会 exit 2。 |
| 12 | verify 会真实执行 gen_sample → cmd_export → 建临时 SQLite 库；它的“零副作用”只保证不碰 cwd 与权威库。 |
| 12 | WXG_SKILL_DIR 能重定向 verify 的被检查根，但代码仍从真实安装导入；测试靠这一点做漂移探针。 |
| 12 | doctor 默认只读但仍会走 connect 的 PRAGMA journal_mode=WAL 与 CLI 末尾 commit；对旧的非 WAL 库会产生文件级副作用。 |
| 12 | doctor 把 exit_code≠0 的 evidence 当问题，且没有删除 evidence 的命令；如实记录失败运行会让 doctor 永久红。 |
| 12 | doctor --fix 会改写 superseded 旧代工单的 target_ids/evidence_ids（只跳过 audit），旧代写入边界的历史记录会被抹掉。 |
| 12 | doctor --fix 的 meta 版本刷新不做结构迁移，能把“版本对不上”变成“版本对但结构旧”。 |
| 12 | doctor 的 fixed.meta 恒为 1，其它计数才反映真实变化。 |
| 12 | doctor 的 issues 上限 200；超限时只给 truncated=true，没有分页参数。 |
| 12 | doctor 不校验 kind/verdict/attrs 的枚举与类型，绕过命令直写库的非法值不会被体检发现。 |
| 12 | evidence 的 artifact_path 在 evidence-record 时被 resolve 成绝对路径；移动仓库/日志目录后 doctor 会报产物缺失。 |
| 12 | CLI 对除 verify/contract/role-prompt/up 外的所有命令都要求 graph.sqlite 已存在，并在连接前做文件检查；doctor/export 因此不会“先建空库再报错”。 |
| 12 | 所有 DB 命令在 handler 返回后无条件 conn.commit()，包括纯读命令；SQLite 下通常无内容变化，但不是严格的无事务副作用。 |
| 13 | plan 排除 unmapped 节点后，其边仍参与分析并变成 dangling.unknown_endpoint；噪声从 node_count 转移到 dangling，默认扫描图会显示 edge_count=0。（commands_compiler.py:28-47、_probe_13b） |
| 13 | plan 的 code 层不按 kind 过滤节点，requirement/use_case 会计入 node_count、layers 与反链；只有 design 层有 kind 白名单。（planner.py:99-107） |
| 13 | plan --level design 在过滤后无节点时直接 ValueError 退出 2，没有友好提示；同一状态用 auto 却正常。（planner.py:114-118） |
| 13 | excluded_unmapped 在排除 stale 之前统计，同时属于 unmapped 与 stale 的节点只计入 unmapped。（commands_compiler.py:33-45） |
| 13 | blind-check 在检查时重新从库里取任务书；执行者手里的那份 brief 不是裁决依据。（commands_compiler.py:122） |
| 13 | 空产出（没有 nodes/edges）算 PASS、locality=1.0；漏交作业与干净交付不可区分。（blind.py:48-94、tests/test_blind.py:128-131） |
| 13 | brief 的 produces 表是 briefing.PRODUCES 的字面量，新增工单 kind 不会自动获得产出契约；未列出的 kind 静默得到空 produces。（briefing.py:31-40） |
| 13 | brief/patch 的 --out 是覆盖写、非原子、不建父目录；失败时按通用异常退出 2。（commands_compiler.py:110-114、246-250） |
| 13 | apply 免 claim_token/角色、不查 target_ids，也不往 work_items.evidence_ids 追加证据；唯一痕迹是补丁文件本身。（commands_compiler.py:259-295） |
| 13 | apply 透传补丁节点的 origin/stale/unmapped/feature_id：可以伪造 origin=declared、把节点塞进任意 feature，stale 会被 upsert_node 清 0。（graph.py:106-132、_probe_13b） |
| 13 | apply 只在补丁之间比较节点内容，覆盖库中已有节点是静默的（后写覆盖先写）。（reducer.py:55-102） |
| 13 | impact --remove-edges 不校验端点：写错 id 得到 lost_reachable=[]、closed=true，看起来像“断这条边没影响”。（commands_compiler.py:315-324） |
| 13 | impact 同时收到 --changed 与 --remove-edges 时 remove-edges 优先，另一个参数被静默丢弃。（commands_compiler.py:314-348） |
| 13 | impact 的 closed/uncovered 用全图 requirement 判断，不限于本 feature；跨 feature 的 requirement 也能让节点算“有归属”。（impact.py:193-194） |
| 13 | conflicts 参与比较的是当前代全部 work_items 的 target_ids，不区分 ready/claimed/passed；历史边界会继续算冲突。（commands_compiler.py:376-379） |
| 13 | cycles 的 --without 只影响 cycles[] 与 cycle_count；--break-set/--advise 用未移除的图重算，组合结果是自相矛盾的。（commands_compiler.py:189-230） |
| 13 | minimal_break_sets 每个 size 档最多返回 10 组，超出静默丢弃，truncated 不反映这件事；>20 条非自环边则直接放弃枚举。（cycles.py:50-79） |
| 13 | cycles 的 truncated 键只在带 --break-set/--advise 时存在，默认输出没有该键。（commands_compiler.py:210、229-230） |
| 13 | patch 不校验 --work 是否存在，w1/w2 这类标签会原样写进补丁并成为 apply 冲突报告里的 a/b。（commands_compiler.py:246、tests/test_plan_cli.py:480-481） |
| 13 | Engine.plan 与 wxg plan 不是同一份实现：Engine 版没有 hint，也没有 excluded 之外的命令层错误包装。（engine.py:77-113） |
| 14 | insert_work(merge=False) 会把 depends_on 一起重置为 []（work.py:56-59，探针：blocked 工单被覆盖后 depends_on 变 "[]"，status 仍是 blocked，于是永远解不开）。这条行为只在单元测试里被触发过，生产调用点全部走 merge=True 或只在工单不存在时插入。 |
| 14 | target_ids 为空等于「禁止任何写入」（work.py:94-98，探针：空边界拒绝一切 id）。这是安全语义，但 SKILL.md 与 references/contract.md 都只讲「落在 target_ids 内」，没讲空集是硬拒绝，也没讲单独的 "*" 是全通配。 |
| 14 | scope_ids 的通配展开遍历 set(existing)，输出顺序随 PYTHONHASHSEED 变（探针：0/1/2/3 四个种子四种顺序）。result 会被 work_seed 原样写进 work_items.target_ids（commands_feature.py:460,479），也会被 feature-status 取前 5 条做 target_sample，所以「同一状态库同一条命令两次输出一致」在这条路径上不成立。 |
| 14 | brief 的 write_boundary 只展开「当前已存在」的节点，新建节点靠 write_patterns 放行（design.md:362 有记录）；而 blind-check 允许 write_patterns 匹配任意 id（blind.py:61,76），于是 target_ids 里的宽通配会让边界检查实质失效——这条推论没有任何文档与测试。 |
| 14 | check_output 的 known_node_kinds/known_edge_kinds 默认 None 时静默跳过 kind 校验（blind.py:40-41,65-66,78-79），库里消费方只有 CLI 与 Engine 两处显式传入；外部调用方省略参数会拿到一个恒 PASS 的校验器。 |
| 14 | brief.inputs 里的节点只能当边端点，不能作为产出节点写出，否则算越界（blind.py:43-46,61-62；探针）。任务书里 inputs 的语义只有一句「输入契约」，这条限制没写。 |
| 14 | locality 的精确扣分（0.4/0.3/0.3，额外项 0.1，clamp 两位）只出现在 design.md:364 的叙述里，没有断言；它「不参与判定」这一点也没有测试能证明。 |
| 14 | reducer 的冲突指纹刻意不含 repo/path/symbol/line_start/line_end/origin/unmapped（reducer.py:20-24；探针：repo= r1/x.py 与 r2/y.py 的两个补丁 ok=True，第一份胜出）。apply 会把第一份写进图库，代码锚点因此在无提示的情况下被选中。 |
| 14 | merge_patches 不校验边 kind 与节点 kind（探针：bogus 边 kind 也 ok=True），非法输入要等到 apply 调用 graph.upsert_node 才抛 Reject；能回滚只是因为 CLI 在最后才 commit（cli.py:84），这层兜底没有任何测试。 |
| 14 | apply 完全绕过 claim_token、角色与 target_ids 写入边界，也不把写过的 id 记进 evidence_ids（commands_compiler.py:259-295）。意图只写在 docs/PRODUCT-PLAN.md:126，SKILL.md 的契约规则块没有；任何进程都能直写图库。 |
| 14 | recompute_ready 的返回值是 0 或 True（workflow.py:76-78），所以 work-judge 的 ready 字段在 JSON 里是 0 或 true（探针）。测试用 assertEqual(1, ...) 掩掉了类型差异。 |
| 14 | conditions 行数多一行（例如手工插了一个未知条件名）会让 recompute_ready 永远返回假，Ready 永远为 0，且没有任何报错（探针：9 行全真 → 0）。doctor 只查缺行，不查多行。 |
| 14 | refresh_blocked 只认 status='passed' 的依赖（workflow.py:85,90）；依赖工单被 superseded 或 failed 时，blocked 工单会永久卡住，没有超时或升级路径。 |
| 14 | actor_value 的身份规则（strip 后 1-80、无空白、环境变量回退）只在 CLI 缺 actor 的那一条测试里被间接碰过；SKILL.md:294 只说「必须带 --actor」或者设 WXG_ACTOR。 |
| 14 | work-list 把 target_ids/depends_on 以 JSON 字符串返回，并把 claim_token 明文列出来（commands_feature.py:711-714）；而 feature-status 对同一张表做了裁剪与解码（commands_feature.py:310-317）。两个视图的字段语义不一致，没有任何文档说明。 |
| 14 | brief 的 forbidden/definition_of_done 是给执行者看的硬约束文本（briefing.py:42-53），但没有测试断言其内容；改文案不会触发任何失败。 |
| 14 | brief 文档承诺「字段顺序固定、同样输入两次生成字节一致」（briefing.py:15），测试却用 sort_keys=True 比对（test_briefing.py:157-159），实际只证明了内容相同，没证明顺序稳定。 |
| 15 | 错误必须走 stderr（M5 变异把错误 JSON 改到 stdout 后 381 条测试全绿） |
| 15 | 成功 JSON 用 indent=2、ensure_ascii=False 输出（只被解析，未被断言） |
| 15 | gate/coverage 的 --json 是空开关，加不加输出相同 |
| 15 | doctor --fix 会把 meta.contract_version 刷成当前版本（test_wxg.py:425） |
| 15 | SQLite journal_mode 必须是 wal（test_wxg.py:1399），这是实现细节被测试锁死 |
| 15 | up 的 next 第一条必须是 import-file ... --prepare，不能是 work-claim（test_plan_cli.py:344-346） |
| 15 | feature-declare 默认 coverage.enforced=true、epsilon=1.0；重声明沿用旧策略（test_wxg.py:1613-1654） |
| 15 | import-file 写库只认 claim 所属 feature，--feature 只在 prepare 阶段生效（test_wxg.py:337-343） |
| 15 | serve --once 由 handler 自己 print 一份 JSON，CLI 层不再打印（cli.py:106-108） |
| 15 | 测试直接 import 私有符号：wxg.make_temp_dir、wxg.upsert_node/upsert_edge/bind_node、wxg.Reject、whyexist.gates._required_coverage，改内部 API 会先红测试 |
| 15 | --root 被 resolve 成长路径，测试也 resolve 后比较（Windows 8.3 短名曾导致 CI 失败） |
| 15 | evidence-record 默认 exit_code=0；--artifact 存绝对路径 + SHA-256 |
| 15 | 快照断言依赖 SELECT * ... ORDER BY 1 的物理行序，加列会改快照 |
| 15 | WXG_SKILL_DIR 只为测试存在，文档从未写 |
| 16 | 导出文件头是固定文本：`---` + generation + feature_id + `来源: wxg-export` + `说明: 缺的 id 留空，不从任何旧文档补句。`。契约的导出表只定义列，没定义这个头；改它会让 verify 直接红。 |
| 16 | `up` 返回的 next[0] 必须包含 `import-file … --prepare` 字样——doc_flow.py:54-58 按这个字符串断言，改文案会破坏文档一致性检查。 |
| 16 | 发布包里必须没有 tools/ 目录（verify_release.py:74 断言）；这一条把“工具不随包分发”变成了硬约束，而不是打包脚本里的实现细节。 |
| 16 | zip 的条目时间戳固定为 2026-10-29、权限 0644、create_system=3（build_release.py:37,96-99）。这是“可复现构建”的全部实现基础，没有任何文档说明。 |
| 16 | `up` 会在 <root> 的父目录创建 demo-repo（commands_repo.py:75-78）；preflight/verify_release 会删掉 <临时根>/demo-repo。两个动作都发生在各自 root 之外，共享系统临时目录。 |
| 16 | CLI 的可预期拒绝一律走 stderr 紧凑 JSON + 退出码 2，argparse 用法错误除外；成功路径是 stdout JSON（indent=2）或纯文本（role-prompt/contract）。 |
| 16 | verify 会检查技能目录里存在 references/design.md、references/contract.md、references/quality.md、tests/test_wxg.py、CHANGELOG.md（commands_misc.py:327-329）；少一个文件包就自检失败。 |
| 16 | `contract --write` 的相对路径基准是技能根，不是 cwd（commands_misc.py:250-256）；从任意目录调用都能改到仓库文件。 |
| 16 | CHANGELOG 的标题格式 `## x.y.z（YYYY-MM-DD）` 与 design.md 的 `## N. ` 编号格式都是被解析的接口（check_docs.py:20-21），不是纯排版。 |
| 16 | publish_github 的 Release 正文是从 CHANGELOG 里截取对应版本段（publish_github.py:123-133）；章节层级写错不会报错，只会发一个空正文。 |
| 16 | dist/ 与 *.zip 被 .gitignore 忽略（.gitignore:15-17），发布产物不进版本库是既定策略，不是遗漏。 |
| 16 | 安装目标路径字符串 `<workspace>/.dsh/skills/why-exist-graph` 同时出现在 manifest 的 install.target 与 README/SKILL 的说明里；改目录名要三处同改。 |

## 待人工判断的问题

| # | 问题 |
|---|---|
| 01 | “只读命令零副作用”到底是公共契约，还是只为 verify 一个命令服务？答案决定 needs_db 继续手写，还是从契约的 WRITE_MODES 派生（并让 verify 交叉校验）。 |
| 01 | 仓库外有没有消费者 import wxg 拿 helper？没有的话，74 个无用导出可以全部删掉，只留 handler 注册表 + 8 个实际使用的函数；有的话需要先发兼容说明。 |
| 01 | “错误一律 JSON”是硬契约吗？argparse 的用法错误永远不是 JSON；要不要把 stderr 统一包一层（或者接受两族格式并写进文档）。 |
| 01 | 退出码 1 现在同时表示“业务判定失败”（gate FAIL）和“未捕获异常”（连接失败），2 表示“可预期拒绝”。这个分界是有意的吗？如果是，连接失败应该算 2 还是 1？ |
| 01 | 成功输出的 indent=2 是否有人依赖（快照、文档粘贴、agent 解析）？若只是人读，统一到 jsonio.dumps 能消掉一套格式。 |
| 01 | serve 恒返回 0 是否可接受？常驻控制器的失败只能从 JSON 里读；作为 CI 步骤它永远是绿。 |
| 01 | 是否允许 `from whyexist.cli import main` 这种库式调用？允许的话，cli.py:72 的 import wxg 必须挪进兜底，且 DEFAULT_ROOT 要改成调用时求值。 |
| 01 | `--db-url` 改写进程环境变量不恢复：这是刻意的（让 handler 与 Engine 复用同一套读取逻辑），还是应该改成显式传参？ |
| 02 | apply 的无 token/无边界写入要保留还是收回？收回会改变单一执行者合并补丁的并行模型，保留则需要契约字段显式表达这个例外。 |
| 02 | serve --once 是否该像 reconcile 一样用退出码表达 converged？现在 CI 只能解析 JSON。 |
| 02 | contract --json 里的 commands[*].token 算不算公开 API？删 TOKEN_COMMANDS 不影响 JSON，但删 token 字段会。 |
| 02 | work-list/feature-status 返回 claim_token 是调试便利还是凭据泄漏？要不要只给 claimed_by 与 token 前缀。 |
| 02 | --prepare 的不写库该怎么修：改 help 说明它写工单与作用域，还是改名/加 --plan 只读模式？ |
| 02 | work-list/evidence-list 与 feature-status 的输出重叠，是否合并成一套投影，减少两套字段的漂移面？ |
| 02 | import-repo 的角色判定用 import-file 是否有意（当前 scan/observe 两名单相同）？ |
| 02 | 契约拆包后是否保持 wxg_contract 顶层模块名？build_release 按文件路径加载、verify 按模块导入，改名会同时影响两处。 |
| 03 | 规则表与 INVARIANTS 要保留为"人读镜像"，还是拆到 references/ 下改由 verify 只比较生成块？现在它们在契约文件里，改一个字就改变已发布文档，却没有测试能判断改得对不对。 |
| 03 | 版本号是否该收敛成单源（CONTRACT_VERSION 读 VERSION，或 verify 直接校验 VERSION/CHANGELOG），并把 tools/check_docs.py 接进 CI？现在靠"记得跑 preflight"。 |
| 03 | SCHEMA_VERSION 要不要真正参与迁移判定（旧库拒绝服务 / 按版本选迁移路径）？当前 doctor --fix 可以把版本号刷成当前值而不做任何结构修复。 |
| 03 | TOKEN_COMMANDS 与 DESIGN_ANCHOR_KINDS 属于包级可 import 的公开名，外部可能有 import；删/搬之前需要确认兼容策略，还是按"不留副本"原则直接删？ |
| 03 | 块替换是否要改成真逐字节 + 拒绝多块 + 统一换行？这会让现有 CRLF 工作树与两份文档立刻失败，需要一并决定重生成流程。 |
| 03 | 工作树大量未提交修改与 git 历史只到 v0.4.1：冻结/重写的基线应取工作树当前状态，还是先整理成可追溯提交？没有这个答案，freeze 判定没有可回退点。 |
| 04 | 要不要给 schema 补外键/CHECK？SQLite 只能重建表，而 12 表里 9 张带跨表引用列、还有外部只读消费者（why-exist-uml）。是继续「无约束 + doctor」，还是做一次带版本号的数据迁移手术？ |
| 04 | 旧库（0.4.x 及更早）还要不要救？要救就得修 F1 并补一个真实旧 schema 的迁移夹具；不救则 init 应检测到缺列后给可读错误和重建指引，而不是 OperationalError |
| 04 | schema_version 的权威方向：只允许升级吗？遇到“库版本 > 代码版本”应该拒绝、警告，还是像现在这样静默改写？这直接决定回滚策略 |
| 04 | MySQL/PostgreSQL 是产品承诺还是实验？本地容器可跑（MariaDB 12.3.3 / PG 16.15）、CI 永不跑；DDL 是 MariaDB 方言、回填 SQL 有 \|\| 拼接（MariaDB 上实测丢历史）。要么上 service container 解冻，要么从 SKILL.md/契约里撤掉这两个后端 |
| 04 | migrated 字典的键名与计数算不算公开契约？如果算，需要一条测试把每个键钉住；如果不算，现在 init 的输出形状就是偶然实现 |
| 04 | 迁移的猜测值（evidence.generation / bites.generation / claimed_at）要不要在表里留来源标记（如 generation_source / claimed_at_source）？现在只能靠 CHANGELOG 记住哪些行不可信 |
| 04 | doctor 与 schema 的职责边界：既然没有 DB 约束，doctor 是否应该补齐枚举校验（bites.verdict、work_items.status）？现在它只校 judge_history.verdict |
| 04 | work_items.assignee 还有存在价值吗？它存的是 role，与 work_items.role 完全重复且无人读；删除需要 SQLite 3.35+ 或重建表，但外部消费者不读它，风险低 |
| 05 | MySQL/PG 后端到底算不算对外承诺？SKILL.md:427、references/contract.md:169-171、quality.md:49-50 都说能用，代码说不能。要么补齐并进 CI，要么把这条产品线从文档里删掉——现在是两者都不成立。 |
| 05 | 要不要为 MySQL 8（caching_sha2/TLS）引入一个可选第三方驱动？如果坚持零依赖，就得接受「只支持 MariaDB + native 认证」，并把这句话写进 BACKEND_RULES。 |
| 05 | schema 的权威定义放哪？三份手抄是 bug 温床。是否可以只维护 SQLite 一份 + 一张列元数据表，由代码生成 MySQL/PG DDL？ |
| 05 | VARCHAR 长度上限是不是隐性契约？超长 node id/path 在 MySQL 上是报错还是被 INSERT IGNORE 截断？要不要在写入前显式 Reject？ |
| 05 | init 半成功（已建表但退出 2）要保留吗？还是应该先做所有可失败检查、再建表？ |
| 05 | 方言翻译要不要改成「按语句模板 + 参数化绑定」，而不是正则改字符串？改动量不小，但这是唯一能保证新 SQL 不被静默改坏的办法。 |
| 05 | migrate_schema 里出现 'jh:' \|\| 说明 MySQL 后端从来没有过需要迁移的旧库；那这条迁移路径在 MySQL 上到底要不要保留？ |
| 05 | 是否支持显式 sqlite 选择（sqlite:///path）？现在设了 WXG_DB_URL 就没有单命令退回 SQLite 的办法。 |
| 06 | attrs 整包替换是有意契约还是历史选择？SKILL.md:400 依赖它清除 construction，但同一条路径也会抹掉 duty/x_note；如果改成合并，现有清除手法就要重写。 |
| 06 | 自定义 edge id（graph.py:168）要不要保留？保留就该给格式/长度/冲突规则；不保留就直接拒绝 payload.id，但可能有外部导入方依赖它。 |
| 06 | bind 的 --edge-kind 应该与 node kind 交叉校验吗？has_output 为什么不在 choices 里？这是遗漏还是有意只让 upsert-edge 建输出边？ |
| 06 | Engine 是否应该接受注入的只读连接，而不是自己 connect/建文件/改 env？还是保持现状但把'首次连接会建文件'写进文档并补测试？ |
| 06 | reachable 是公开库 API 还是遗留？__init__.__all__ 导出了它但没有生产调用方，删除会影响包级 API 的兼容承诺。 |
| 06 | edges 只校验 2/20 种端点语义，这是有意的宽松设计（把结构判断留给 gate/conformance）还是没做完？这决定 graph.py 重写的范围。 |
| 07 | `reads` 边到底是"没实现"还是"已放弃"？三条文档都说导入器产 reads，而 conformance 的 code_edges 把它算进依赖支撑。要补实现（self.attr 读、Name 读）还是删文档并删掉 gates.py:124 里的 reads？两种都改变现有报告的语义。 |
| 07 | importer 的"同名裸名调用"解析要不要保留？它把跨文件同名函数误连到本文件函数（探针里 run 调用 helper() 被连到本文件的 helper），这是启发式而非真解析；保留会制造假 calls 边，删掉会让更多调用变 unmapped。 |
| 07 | derive 的组件 id 绑定目录深度（换 --depth 就换一套 id），现有工单 target 用精确 id 时会失效。是否值得引入"稳定组件 id + 路径别名"？代价是要维护一张别名表，收益是重跑 derive 不再需要重新 work-open。 |
| 07 | 要不要一个 depends-only 命令，或 `derive --components-from graph`：给手工聚合/手工声明的 component 推导跨组件依赖？derive.py 的计算部分已经具备（nodes 带 path 即可），缺的是"组件归属"输入与组件的 target 校验。 |
| 07 | 重跑 derive 时旧的 depends/contains 边该删、该标 stale、还是该保留？现在什么都不做（只有节点标 stale）。删会丢审计轨迹，保留会让 edges 表缓慢膨胀并让直接查边的消费者看到失效依赖。 |
| 07 | derived 能不能覆盖同名 declared 组件？现在能，而且是静默覆盖（origin 降级、attrs 清空）。禁止覆盖会让 derive 在"目录键撞上人工命名"时直接报冲突；允许覆盖就得给人工组件换 id 规则。 |
| 07 | derive 的成员 contains 边该不该受 target_ids 约束？现在不受（成员 id 从不进 target 校验）。收紧会让 derive 必须先 work-open 成员 id（大仓上等于把整仓节点写进工单），放松则"写入边界"这个安全承诺对 derive 失效。 |
| 07 | stale 代码节点该不该参与 derive 分组？现在参与（只过滤 unmapped）。排除它会改变现有 depends 图（stale 节点常常是刚被删的代码），不排除则 derived 组件里会含已不存在的成员。 |
| 07 | find --path-prefix 要不要改成转义 LIKE（LIKE ? ESCAPE '\\'）并新增通配参数？直接转义会让当前把 % 当通配的调用方行为变化；不转义则"前缀"这个名字是错的。 |
| 07 | 三个只读命令的节点形状要不要统一成 attrs？统一是明显的一致性收益，但 slice 的输出被 work-claim 原样嵌入、agent 提示词按它消费；这属于要人判断的兼容性取舍，而不是技术债清单。 |
| 07 | importer 要不要接受非 UTF-8（比如按 PEP 263 的 coding cookie 解码）？现在一个 GBK 文件会让整仓 import-repo 中止，而 derive 的扫描却能跳过它——同一仓在两处可用性不同。 |
| 07 | repo-add --language 现在只有一个合法值，是留在契约里当"未来扩展点"，还是降级成隐含 python 并删掉这个参数？design.md:64-66 说扩展要在 wxg.py 加分发，但 wxg.py 已是薄入口，文档与代码位置对不上。 |
| 08 | import-file 写库时 --feature 应该被禁止、被校验相等，还是作为“把节点也登记进另一个 feature”的显式操作？现在的静默忽略最危险。 |
| 08 | derive --apply 遇到同名 declared/manual component 应该拒绝、跳过、还是派生到独立命名空间？当前覆盖 origin 与 attrs 的行为是否有人依赖？ |
| 08 | stale=1 是否算 I5 说的“图内容写入”？如果是，derive 的清理必须走 target_ids；如果不是，需要把这个例外写进契约。 |
| 08 | promote 是否允许跨 feature 提升？如果不允许，应比较 token.feature_id 与 --feature；如果允许，需要定义节点同时属于多个 feature 的语义。 |
| 08 | import-repo 与 sync 是否应共享同一个文件枚举器（点目录、点文件、语言、路径存在性）？现在两套规则会让回扫报告永远包含 import 不会写的文件。 |
| 08 | import-repo 遇到语法错误应该整批失败还是跳过并继续？如果整批失败，是否需要 --keep-going 或 parse_errors 输出？ |
| 08 | up 的退出码语义：bootstrap 成功但 gate FAIL 时返回 0 是否是刻意设计？如果 CI 直接跑 up，会不会把 FAIL 当成功？ |
| 08 | repo-add 是否应在登记时校验 id 字符集（与 check_node_id 一致），避免非法 id 把错误推迟到 import？ |
| 08 | sample 的抽样域是否应排除 stale/unmapped/requirement 节点？现在 feature 作用域里这些节点都可能被抽中。 |
| 08 | repo-list 的输出是否算稳定契约（含 created_at、绝对路径、无分页）？有没有外部脚本依赖？ |
| 09 | register 路径没有 coverage 默认是设计还是遗漏？如果是有意，两种入口的策略矩阵应该写进契约；如果不是，修它会改变已登记 feature 的门禁结果。 |
| 09 | work-claim 要不要 --feature？现在的跨 feature 选择会让多 feature 并行时的领取结果由 id 字典序决定。 |
| 09 | --brief 要不要连 target_ids 一起裁剪（例如只给 count + hash）？不裁剪的话文档里“省上下文”的理由不成立。 |
| 09 | claim_token 出现在只读命令里是调试便利还是安全缺陷？如果保留，是否至少只给前缀/哈希；如果收回，role-prompt 与测试工具要同步改。 |
| 09 | status 与 gate 的咬合过滤要不要抽成唯一实现？统一意味着改 gate 的判定结果（当前 gate 更宽），这是行为变更不是重构。 |
| 09 | change-diff 的基线允许未来代（--from-generation 9 不报错，探针 S7.9），要不要收紧；scan 写出的节点算不算“变更”也需要先定义。 |
| 09 | assignee 列还有存在价值吗？role 列已经是同值，agent 身份在 claimed_by；删列会影响 MySQL/PG 迁移脚本（db.py:516-583）。 |
| 09 | judge 的 legacy 放行（claimed_by 为空即允许自审）要不要保留？如果保留，audit-id 入口是否应该成为唯一入口，以减少两条路径的测试面。 |
| 09 | changes.affected_json 是保留给未来字段级 diff，还是直接删列？当前它是纯死字段，但删列要改 schema 版本与迁移。 |
| 10 | 覆盖检查在 gate 阶段到底应该要求「当前阶段」还是「全部六个阶段」？work-judge 与 gate 现在不是同一检查，SKILL.md:388 与 GATE_RULES 第 11 条的措辞也不一致。 |
| 10 | 其它 feature 写在共享节点上的咬合，是否应该影响本 feature 的门禁？gate 说影响，coverage 说不影响；哪一个才是预期语义？ |
| 10 | 悬空 bite 应该只被 doctor 清理，还是在 drift 计数里也排除？现在的实现让同一条记录既「被忽略」又「导致 FAIL」。 |
| 10 | coverage 的 n_required 是应该按文档的 (1+d)/(10+m) 修代码，还是按实现的 9+m 改文档？两者只差 1，但 P1 已经造成 p 与 met 自相矛盾。 |
| 10 | prior_p 的语义是「Beta 先验均值」还是固定 Beta(1,9)？现在 a0=prior*10、b0=(1-prior)*10 是把先验强度写死为 10，文档没有说明。 |
| 10 | serve 是否应该像 reconcile 一样用退出码表达未收敛？现在恒 0 会让 CI 把「控制器跑过」误当成「系统已收敛」。 |
| 10 | serve 遇到单个坏 feature 时应该跳过并继续（并报告 skipped），还是中止整轮？现在的行为是中止，长驻进程会被一个坏库杀死。 |
| 10 | conformance 的 verifies 是否必须来自 testcase？实现只看边，文档说 testcase；若收紧会不会让现有库突然 violations>0？ |
| 10 | reconcile 的五类非自动动作（retry/coverage-gap/drift-over-limit/construction-open/stale-node）是否是对外稳定契约？serve 的消费者可能已经在解析它们。 |
| 10 | gate 的「不可无声失败」边界是否需要定义空作用域与裸证据的下限？现在两者都能 PASS，评审者需要知道 PASS 不代表什么。 |
| 11 | retract 的写边界到底承诺什么：节点级 target 就够，还是边/工单引用也要受边界约束？当前「删节点连带删 target 外的边、跨 feature 裁引用」是设计还是 bug——这决定它该重写还是只补测试。 |
| 11 | upsert-node 的 attrs 整体替换是契约还是历史选择？import-file 用 merge_attrs=True，CLI 用 False；要不要显式化成 --merge/--replace，还是统一成合并（SKILL.md:400 的「清 construction」依赖覆盖语义）？ |
| 11 | bite 该不该也要求 claim_token + target 边界？I5（SKILL.md:327）说图内容写入必须有边界，而 bite 是唯一例外且能扩 feature 作用域；收紧会改掉「任何人可咬」的现有工作流。 |
| 11 | nodes.unmapped 的权威来源是谁：导入器（I7）、bite(UNMAPPED)、upsert payload 三个写点都能改它；目前没有单一规则，重写时按哪个保留？ |
| 11 | retract 的计数要不要修成「真实删除数」并让不存在的 id 报错？调用方（CI/代理/doctor）现在会把 nodes_deleted=1 当成成功依据。 |
| 11 | 跨后端事务：MySQL/PG 在 Reject 后只 close 不 rollback，是否要显式 rollback 并补测试？SQLite 的回滚行为目前只被探针验证过。 |
| 11 | evidence 的 exit_code 语义：记录允许任意值、采信只认 0，这是有意的「留失败证据」还是漏洞？是否要求 --artifact 与 --exit-code 组合出现（非 0 时不要求产物）？ |
| 11 | TOKEN_COMMANDS 要不要删（零消费、与 COMMANDS.token 不一致）？删它属于包级 API 变更，需先确认无外部 import；同样的问题也适用于 commands_repo.py:683-693 的兼容 re-export。 |
| 12 | verify 应该做真字节比较（拒绝 CRLF/多标记/块外改动），还是维持“文本归一化”并把文档里的“逐字节”改掉？前者会让当前工作树立刻失败，需要先定重生成流程。 |
| 12 | verify 的检查范围要不要扩展到 VERSION/CHANGELOG/README/quality 的版本一致性？现在这些正文漂移完全无人管，tools/check_docs.py 又不在 CI。 |
| 12 | doctor 是“交付门”还是“诊断工具”？如果是门，exit_code≠0 的 evidence 就不该是问题（失败运行也要留痕）；如果是诊断，就不该用退出码 1 表达。 |
| 12 | doctor --fix 允许硬删 bites/edges/feature_nodes 吗？要不要先备份/导出被删行，或改成“报告 + 显式 --apply --yes”？ |
| 12 | doctor --fix 的 meta 刷新算修复还是掩盖？是否应该在 schema_version 不匹配时拒绝 stamp，要求先跑 init 迁移？ |
| 12 | doctor 要不要补 kind/verdict/attrs 的枚举与类型校验？补了会让用 SQL 直改的旧库变红，不补则“体检通过”有盲区。 |
| 12 | export 是否应对旧文件做清理、是否要原子写（临时目录 + rename）、是否要固定排序以保证跨后端字节一致？ |
| 12 | feature id 的校验要不要禁止 `.`/`..`（或统一禁止以点开头）？这会影响已有 feature 命名。 |
| 12 | role-prompt 的 token 要不要脱敏、要不要支持“二维码/一次性令牌”，以及是否应感知 WXG_DB_URL 输出 --db-url？ |
| 12 | contract --write 是否应限制为 SKILL.md / references/contract.md 两个已知路径？现在它可以改写任意带标记的文件。 |
| 12 | verify 失败提示里的修复命令要不要直接给出可复制的绝对/正确相对路径（`--write references/contract.md`）？ |
| 12 | WXG_SKILL_DIR 是测试后门还是公开能力？如果公开，需要写进契约并校验目录结构；如果是测试后门，应改成参数或 pytest fixture。 |
| 13 | apply 的定位到底是什么：单一执行者的批量落库入口（文档口径），还是并行执行者的合并入口（命令名与 SKILL.md:372 的口径）？前者可以继续免 token，后者必须补 target/claim/证据，否则 merge 模型等于没有写边界。 |
| 13 | plan --level design 在空设计层时应该返回空计划还是报错？如果返回空计划，parallelism/bottleneck 的语义要重新定义（当前崩溃点正是这两项）。 |
| 13 | break_sets 想要“完整枚举”还是“一组可执行建议”？完整枚举在 20 条边上不可行；若只给建议，应改成每 SCC 一组最小反馈边，并在输出里写清策略。 |
| 13 | blind-check 应该用执行者拿到的 brief 快照裁决，还是用当前库状态？现在是后者，意味着工单边界变化会追溯影响旧产出。是否需要给 brief 加 hash/brief_version 并在 check 时比对？ |
| 13 | impact 的 closed 是“连到任意 requirement”还是“连到本 feature 的 requirement”？现在是前者，且被 README/SKILL 描述成“意料之外的影响面”，两者口径不一致。 |
| 13 | conflicts 要不要把 passed/withdrawn 工单的 target_ids 排除？不排除会把已交付区域算成永久冲突；排除会让“重新打开同一区域”的并发风险不再被提前发现。 |
| 13 | Engine 是仓库的公开库 API（README.md:48），还是 CLI 的薄包装？现在它复制了 plan 逻辑、缺 cycles/conflicts/apply，且 import 了 commands_compiler 的私有函数 _brief_payload——需要决定它是不是一等公民。 |
| 13 | plan 的 dangling.self_loop/duplicate 两个字段有没有消费者？如果只是 graph_algo 的透传，可以删掉以减少契约面；如果要保留，应补断言。 |
| 14 | 「工单状态机」应该有一个归属模块吗？现在 claim（commands_feature.py:507）、finish（564）、judge（620）、条件迁移（workflow.py:63-91）、依赖解锁（workflow.py:81）分散在三处，重写时先合并成 lifecycle.py 还是保持现状、只在测试里补契约？ |
| 14 | recompute_ready 的返回类型是 0/True 混合，是历史遗留还是下游真的按布尔消费？改 成统一 bool 会让 work-judge 的 JSON 从 0 变成 false，需要先确认没有脚本按整数判断。 |
| 14 | apply 绕过 claim_token 与写入边界是产品决定（PRODUCT-PLAN.md:126）还是尚未收口的安全口子？如果是有意的，SKILL.md 的 I5 规则需要为 apply 写例外；如果不是，apply 缺一个 token 参数就是一个洞。 |
| 14 | scope_ids 的顺序不确定是否值得修？它的直接消费者大多会排序或转 set，但 work_seed 落库的 target_ids 顺序与 feature-status 的 target_sample 会不同步；修法是在 scope_ids 末尾排序，还是让调用方各自负责？ |
| 14 | reducer 的冲突指纹要不要包含 repo/path/symbol/line_*/origin/unmapped？扩大指纹会让更多并行补丁判冲突（更安全但更吵），不扩则是静默丢锚点。 |
| 14 | brief 的 forbidden/definition_of_done 文本算不算对外契约？如果算，应该进 wxg_contract 由 verify 校验；如果不算，为什么它出现在机读 JSON 里而 role-prompt 另写一套？ |
| 14 | work-list 为什么要明文返回 claim_token 并把 target_ids 留在字符串形态？是给脚本用的兼容形状，还是没人看的调试输出？这决定它能不能和 feature-status 合并成一个视图。 |
| 14 | gates.py:402-413 的 re-export 块什么时候删？它已经在文件末尾静置了两个版本（注释说「保持模块内调用点不变」，但模块内没有调用点）。 |
| 15 | 要不要先把 tests/ 与 scripts/whyexist/ 提交进版本控制再谈重写？现在 381 条只活在工作区，git reset/clean 会把安全网和实现一起抹掉 |
| 15 | mysql/pg 后端要不要进 CI？不进，后端改动只能冻结；进，就要决定容器化与两个破坏性 setUpClass 的重写 |
| 15 | 错误流（stderr）与退出码算不算正式契约？补一条 assert stdout == 空 成本极低，但会立刻暴露现有夹具的掩盖行为 |
| 15 | gate --json / coverage --json 保留还是删？保留要有行为，删要同步契约块与 20+ 处测试调用 |
| 15 | 05-类图.md 与 测试规格.md 的导出内容要不要锁？verify 的样例逐字节校验只间接覆盖了一部分 |
| 15 | SQLite 并发 claim 的语义（WAL + busy_timeout）要不要测？默认后端反而没有并发用例 |
| 15 | test_wxg_mysql 在无 MariaDB 的机器上降级为 1 条 skip，这算通过还是算没跑？基线数字会因此差 11 条 |
| 15 | CHANGELOG 把「381 不变」当发布门，是否说明在用数量代替覆盖判断？本次已找到 1 条零测试命令、1 条仅错误路径命令、1 类仅间接命令 |
| 15 | check_docs 是否应该接管 README 里的用例数与契约版本？现在只校验三处版本号与章节编号 |
| 15 | verify 用例要不要改成最小 fixture 目录，还是继续复制整棵树？ |
| 16 | docs/ 到底算不算发布物？CHANGELOG 2.92.0 说这版“加一份 docs/HANDOFF.md”，但 build_release 的 INCLUDE_DIRS 不含 docs/，11 个 zip 里都没有它。若 docs 该进包，打包规则要改；若不该，2.92.0 的发布说明就是错的。 |
| 16 | ~/.dsh/skills/why-exist-graph 的 1.4.0 是谁、按什么流程装的？仓库里没有同步脚本，README 只说“git clone 或解压 zip”，而 GitHub 上只有 0.4.1。 |
| 16 | publish_github.py 还要不要留？它与 release.yml 重复且会抢同一个 tag 的 Release；若答案是“发布只走 tag + CI”，这个脚本应删；若要保留“首次建仓”能力，应缩到只做建仓，不碰 Release。 |
| 16 | refactor-lab/ 是本次审计环境缺失，还是已经被删掉？如果是删掉，40+ 处引用要一起清，且 HANDOFF 的“两层验证”只剩一层（preflight），真实仓验证（flask 1186 节点那类证据）就没有可复现入口了。 |
| 16 | 每版 +0.1.0、每 10 个进一个大版本（0.9→1.0、1.9→2.0），这是刻意的发布节奏还是自动迭代留下的副作用？如果对外发布只发生在真正的里程碑，版本号应该在发布时收敛，否则用户无法从版本号判断兼容性。 |
| 16 | README/quality/CONTRIBUTING 里的数字（用例数、行数、脚本数）应该手改，还是由 CHANGELOG/测试输出自动生成？手改已被证明会过期四处；自动生成需要一个新的渲染步骤与 verify 分支。 |

## 解析失败

（无）
