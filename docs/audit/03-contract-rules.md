# 03 契约表与常量（`scripts/wxg_contract.py`）

## 判定先说

这个切片不是均质的，必须分三层看：

- **真契约**：8 条件、工单 kind、节点/边 kind、绑定映射、三组判决、`COVERAGE_DEFAULTS`/`RECONCILE_DEFAULTS`、`ROLES`、`PRODUCT_CODE_ROLES`、`COMMANDS`、`WRITE_MODES`、`ATTR_SCHEMA`、`EXPORT_FILES`。它们有真实消费点（grep 得到调用位置），其中大部分被测试或 `verify` 间接锁定，改错会立刻有行为变化或检查失败。
- **装饰性文档**：10 张规则表（58 条）、21 条 `INVARIANTS`、`EXPORT_RULE`。全仓没有任何代码读取它们，`verify` 也不比较文本与实现；抽查内容与实现一致，但一致性靠人工维护，删一行不会让任何检查失败。
- **死数据**：`TOKEN_COMMANDS`（零消费且已过时）、`COMMON_ATTRS`（只进 `contract_json`，markdown 另手写一份）、`P()`/`positionals` 机制（0 次调用）。

一句话：**枚举和形状是真契约，规则文本是文档，块替换是半可靠的漂移地基**。

## 切片范围

| 文件 | 行 | 内容 |
|---|---|---|
| `scripts/wxg_contract.py` | L1-268 | `SCHEMA_VERSION=9`、`CONTRACT_VERSION=2.92.0`、`DOCTOR_FIXABLE_CHECKS`、8 条件及映射、`WORK_KINDS`、`NODE_KINDS`(17)、`EDGE_KINDS`(20)、`BIND_EDGE_KIND`、`BITE_VERDICTS`/`GATE_FAIL_VERDICTS`/`DRIFT_VERDICTS`、`EVIDENCE_REQUIRED_CONDITIONS`、5 张规则表、`COVERAGE_DEFAULTS`/`RECONCILE_DEFAULTS`、`JUDGE_HISTORY_COLUMNS`、3 张规则表（change/rescan/backend/serve/conformance）、`ROLES`、`TOKEN_COMMANDS`、`PRODUCT_CODE_ROLES` |
| `scripts/wxg_contract.py` | L269-691 | `P/O/F/C` 构造器、`COMMANDS`（50 条命令，123 选项、19 标志）、`WRITE_MODES`（13 种取值） |
| `scripts/wxg_contract.py` | L695-776 | `ATTR_SCHEMA`(17 kind)、`COMMON_ATTRS`、`EXPORT_FILES`(6 份)、`EXPORT_RULE`、`INVARIANTS`(21) |
| `scripts/wxg_contract.py` | L780-1058 | 4 个块标记、`_cmd_params`/`_cmd_write`、`main_contract_markdown()`、`full_contract_markdown()`、`contract_json()`、`_BLOCKS`、`replace_block()`、`extract_block()`、`contract_version_line()` |
| `scripts/whyexist/contract.py` | L1-21 | 桥接：`C` re-export + `DESIGN_ANCHOR_KINDS`（契约概念，但不在契约文件里） |

消费方（不在本切片但决定契约真假）：`whyexist/cli.py`（命令表→argparse）、`whyexist/graph.py`（kind/边/属性/bind 校验）、`whyexist/commands_misc.py`（`contract`/`verify`/导出/doctor）、`whyexist/commands_feature.py`、`commands_gates.py`、`commands_graph.py`、`gates.py`、`db.py`、`briefing.py`、`engine.py`、`commands_compiler.py`、`tools/check_docs.py`、`tools/preflight.py`、`tools/build_release.py`。

## 公开面

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg contract` | CLI | `wxg_contract.py:631`、`cli.py:29`、`commands_misc.py:250` | `--json`；`--section main\|full`；`--write <path>`（相对路径按技能根解析） | 230 行 main markdown / 337 行 full markdown / 32 键 JSON / `{written,section}` | 不连库、不建 `.why-exist`（`cli.py:65`）；`--write` 整文件读改写 | 0；参数错或标记缺失 2 |
| `wxg verify` | CLI | `wxg_contract.py:632`、`commands_misc.py:269`、`cli.py:94` | 无参数；`WXG_SKILL_DIR` | `{ok, issues\|checks, version}` | 读 2 份文档 + 4 份资源；临时目录建库跑真实导出 | 0 / 1 / 2 |
| `main_contract_markdown()` | 函数 | `wxg_contract.py:801` | 无 | 230 行 / 15424 字 | 无 | — |
| `full_contract_markdown()` | 函数 | `wxg_contract.py:924` | 无 | 337 行 / 19470 字（末尾带版本行） | 无 | — |
| `contract_json()` | 函数 | `wxg_contract.py:997` | 无 | 32 键 dict | 无；`_jsonable` 把 `type=` 降级成字符串名 | — |
| `replace_block()` | 函数 | `wxg_contract.py:1040` | `(text, section, body?)` | 替换第一对标记之间内容 | 无；缺标记 `ValueError`，未知 section `KeyError` | — |
| `extract_block()` | 函数 | `wxg_contract.py:1050` | `(text, section)` | 第一对标记之间文本（`strip("\n")`） | 无；`end` 在 `begin` 前时返回空串不报错（实测） | — |
| `contract_version_line()` | 函数 | `wxg_contract.py:1057` | 无 | `"wxg contract v2.92.0 / schema v9"` | 无；唯一调用点是 verify 成功输出 `commands_misc.py:352` | — |
| `SKILL.md` main 契约块 | 文件 | `SKILL.md:113-344` | 渲染结果 | 人读契约 | 块内手改 → verify 报过期；块外手改 → 无人检测 | — |
| `references/contract.md` full 块 | 文件 | `references/contract.md:6-344` | 渲染结果 | 全量契约（唯一带版本号的生成块） | 版本变更必须先 `--write` | — |
| `references/export-sample/feat-demo/*.md` | 文件 | 6 份；比较在 `commands_misc.py:332-348` | `gen_sample.build()` | 与库内样例逐份比较 | 每次 verify 真实跑导出代码 | — |
| `meta.contract_version` / `meta.schema_version` | 表 | 写 `db.py:593-601`、`commands_misc.py:590-599`；读 `commands_misc.py:537-540` | 常量值 | doctor `meta-version` 检查项 | `--fix` 无条件覆盖 | — |

## 契约表

状态口径：covered = 有测试直接断言；partial = 有测试但只覆盖部分分支；gap = 行为在代码里但无测试/无消费者。

### 命令表与枚举

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C1 | CLI 子命令与参数完全由 `COMMANDS`(50) 生成 | `cli.py:29-44`、`wxg_contract.py:299,637`、`test_wxg.py:503-515` | covered | 无测试直接断言 parser 产物同构，靠端到端覆盖 |
| C2 | 枚举参数的 choices 绑定契约常量（bite/roles/work kinds/node kinds/bind edge kinds/from-condition） | `wxg_contract.py:412,426,434,462,475,626`、`test_wxg.py:311,906` | covered | 非法 `--from-condition` 无测试 |
| C19 | `TOKEN_COMMANDS` 是需要 token 的命令集合 | `wxg_contract.py:262` | **gap** | 零消费；`token=True` 有 9 条它只列 6 条（漏 import-repo/derive/promote） |
| C18 | `PRODUCT_CODE_ROLES` 拦 implement-test 领取 | `wxg_contract.py:265`、`commands_feature.py:512`、`test_wxg.py:469` | covered | — |
| C20 | `WRITE_MODES` 覆盖每个命令，是文档\"写入\"列唯一来源 | `wxg_contract.py:640-691,797`、`commands_misc.py:306`、`test_wxg.py:525` | partial | 键集有断言；13 种自由文本取值无枚举，值写错不报错 |
| C29 | `DOCTOR_FIXABLE_CHECKS` 决定 doctor `fixable` 标记 | `wxg_contract.py:22-30`、`commands_misc.py:603` | partial | I9 正文（`:763`）抄了同一清单，改一处不影响另一处 |
| C3 | `contract --json` 形状与版本 | `wxg_contract.py:997-1031`、`test_wxg.py:518-525` | partial | 32 键只断言 6 键 |
| C10 | `contract --write` 幂等、按技能根解析相对路径 | `commands_misc.py:255-261`、`wxg_contract.py:1040` | **gap** | 无任何测试执行 `--write`；Windows 上整文件转 CRLF |

### 条件与状态机

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C16 | 8 条件固定顺序；declare 建 8 行只置 Accepted；Ready 派生 | `wxg_contract.py:34-43`、`commands_feature.py:122-126,360-374`、`commands_misc.py:509-527`、`test_wxg.py:189` | covered | `ready-inconsistent` 分支无单独测试 |
| C17 | work-open 只收 `WORK_KINDS`；audit 由 finish 生成；`work_items.role == kind` | `wxg_contract.py:57-66`、`commands_feature.py:496-503`、`work.py:25-43` | partial | role=kind 无契约语句，属隐含约定 |
| — | `KIND_TO_CONDITION`（契约内派生）：kind→条件 | `wxg_contract.py:54`、`commands_feature.py:631` | covered | 由 `CONDITION_TO_KIND` 反向构造 |

### 节点/边/属性

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C12 | 节点属性按 `ATTR_SCHEMA` 强校验：未知键拒、`x_*` 放行、`attrs.bite` 禁写、bool 类型检查 | `graph.py:18-41,92`、`test_package_units.py:168-175`、`test_wxg.py:848,1430` | covered | str/int 不符路径无测试 |
| C13 | 类型语义：`str/int/bool` 由 `graph.check_attrs` 解释，`任意`=不校验 | `wxg_contract.py:695-721`、`graph.py:30-38` | **gap** | `任意` 是无文档魔法值 |
| C14 | 边属性不受 schema 约束 | `graph.py:184`、`wxg_contract.py:723-726` | **gap** | 节点/边属性语义不对称，无文档 |
| C15 | `BIND_EDGE_KIND` 驱动 bind 边种类，只收 3 类节点 | `wxg_contract.py:113-117`、`graph.py:190-213`、`test_wxg.py:229,510` | partial | 拒绝分支与非法 `--edge-kind` 无测试 |

### 判决与覆盖

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C2b | 判决集固定：`BITE_VERDICTS`、`GATE_FAIL_VERDICTS`、`DRIFT_VERDICTS` 被 gate/bite 消费 | `wxg_contract.py:121-124`、`commands_graph.py:110-111`、`commands_gates.py:186`、`gates.py:72`、`test_wxg.py:308-322` | covered | — |
| C4 | SKILL.md main 块=当前渲染，改动报\"过期\" | `commands_misc.py:274-285`、`test_wxg.py:481-501` | covered | 反向测试只有 main |
| C5 | references/contract.md full 块同样被比较 | `commands_misc.py:274-285`、`wxg_contract.py:924-983` | partial | 无反向测试；CI 只覆盖正向 |
| C6 | verify 零副作用（不建 `.why-exist`） | `cli.py:62-70`、`test_wxg.py:873-882` | covered | 临时库副作用未断言 |
| C7 | verify 交叉引用 9 类检查 | `commands_misc.py:287-329` | partial | frontmatter/导出列/资源存在/缺标记 4 类失败分支无测试 |
| C8 | verify 逐份比较 6 个导出样例 | `commands_misc.py:330-348`、`gen_sample.py:118`、`test_wxg.py:486` | partial | 无反向测试；异常被 `except Exception` 收成一条 issue |
| C9 | verify 成功返回固定 `checks` 名单与 version 行 | `commands_misc.py:352` | **gap** | 测试只看 `ok` |
| C11 | 缺标记时 verify 报问题不崩溃 | `wxg_contract.py:1040-1054`、`commands_misc.py:278-282` | **gap** | `--write` 侧不捕获，直接 exit 2 |
| C30 | 块比较 strip 首尾换行，边界空行不算漂移 | `wxg_contract.py:1047,1054`、`commands_misc.py:279-284` | **gap** | 与文档\"逐字节\"不一致，无说明 |
| C31 | 多对标记只处理第一对 | `wxg_contract.py:1045,1054` | **gap** | 实测第二块被忽略 |
| C32 | 10 张规则表与实现同构 | `wxg_contract.py:129-242`、`gates.py:81-121`、`commands_gates.py:159-322` | **gap** | 58 条规则零消费，抽查一致但靠人工 |

### 版本与表结构

| ID | 承诺 | 证据 | 状态 | 备注 |
|---|---|---|---|---|
| C25 | `CONTRACT_VERSION` 出现在 json/init/meta/verify 四处 | `wxg_contract.py:18`、`commands_repo.py:57`、`db.py:593`、`commands_misc.py:537`、`test_wxg.py:425,520` | covered | 测试硬编码版本串，升版必须同步改 |
| C26 | `VERSION` = `CONTRACT_VERSION` = CHANGELOG 最新 | `tools/check_docs.py:28-45`、`preflight.py:70-73`、`build_release.py:81-86` | **gap** | wxg 不读 VERSION；check_docs 不在 CI（`ci.yml:27-30`）；HANDOFF 仍 2.91.0 |
| C27 | `SCHEMA_VERSION` 入 meta、doctor 比对、`--fix` 刷新 | `wxg_contract.py:17`、`db.py:593`、`commands_misc.py:537,590-599`、`test_wxg.py:412-425,652` | covered | — |
| C28 | `SCHEMA_VERSION` 是迁移判据 | `wxg_contract.py:17`、`db.py:509-601` | **gap** | 迁移按列存在性决定；实测旧库直接 doctor → exit 2 `OperationalError: no such column: claimed_by`，到不了 meta-version |
| C23 | `JUDGE_HISTORY_COLUMNS` = judge_history 实际 9 列 | `wxg_contract.py:174-184`、`db.py:127-137` | **gap** | 当前恰好一致，无校验 |
| C24 | 21 条 `INVARIANTS` 与实现/测试对应 | `wxg_contract.py:754-776` | **gap** | 无代码读取、无测试引用、无编号↔测试映射 |
| C21 | `EXPORT_FILES` 决定导出文件/列/顺序 | `wxg_contract.py:730-742`、`commands_misc.py:66-194`、`test_wxg.py:608,1004` | partial | 按下标 `[0]..[5]` 取用，重排会错位而不报错 |
| C22 | `EXPORT_RULE` 描述导出作用域 | `wxg_contract.py:744-750` | **gap** | 零消费；样例比较只证明生成器自洽，不证明符合规则 |

### 21 条不变量逐条落点

| 不变量 | 实现落点 | 测试 | 判定 |
|---|---|---|---|
| I1 单一契约 | `wxg_contract.py` + `commands_misc.py:269-352` | `test_wxg.py:503-525` | covered（仅 main 块方向） |
| I2 generation 是身份 | `commands_feature.py:85-126` | `test_wxg.py:270,710` | covered |
| I3 交付门只读 | `commands_gates.py:159-322` | `test_wxg.py:299` | covered |
| I4 判决可校验 | `commands_graph.py:109-141`、`commands_gates.py:166-187` | `test_wxg.py:308,1055` | covered |
| I5 写入有边界 | `work.py:63-100`、`commands_feature.py:719` | `test_wxg.py:465`、`test_wxg.py:848` | covered |
| I6 技能通用 | `cli.py:53`、`DEFAULT_ROOT` | 无（`test_wxg.py:894` 只测 role-prompt 用真实 root） | **gap**（\"不写死仓名/路径\"无断言） |
| I7 不臆造 | `importer.py`、`commands_misc.py:22-194` | `test_wxg.py:925` | partial（导出\"缺 id 留空\"无断言） |
| I8 文档即生成视图 | `commands_misc.py:274-348` | `test_wxg.py:481` | partial（full 块与样例无反向测试） |
| I9 状态可自检 | `commands_misc.py:355-617` | `test_wxg.py:391,569` | covered（`--fix` 清单与 I9 文字双份） |
| I10 审计可追溯 | `commands_feature.py:620-696`、`db.py:127-137` | `test_wxg.py:527,1102` | covered |
| I11 证据可追溯 | `commands_graph.py:144-195`、`evidence.py` | `test_wxg.py:569,589,792` | covered |
| I12 模式有限应用 | `graph.py:152-158`、`commands_gates.py:189-203` | `test_wxg.py:1168,1202,1246` | covered |
| I13 判决按最新 | `commands_gates.py:166-187` | `test_wxg.py:1055` | covered |
| I14 失败历史 | `commands_feature.py:601-617` | `test_wxg.py:1102` | covered |
| I15 覆盖可计算 | `gates.py:36-121` | `test_wxg.py:1133,1158,1299,1613` | covered |
| I16 漂移可门禁 | `gates.py:58-78`、`commands_gates.py:266-272` | `test_wxg.py:1220,1238` | covered |
| I17 调谐可重复 | `gates.py` reconcile + `commands_gates.py:110-115` | `test_wxg.py:1326-1391` | covered |
| I18 变更可追溯 | `commands_feature.py:341-379` | `test_wxg.py:1446-1559` | covered |
| I19 回扫可断言 | `commands_repo.py` import/sync | `test_wxg.py:1559,1585,1605` | covered |
| I20 控制器可常驻 | `commands_gates.py:118-156` | `test_wxg.py:1659-1704` | covered |
| I21 一致性只报差异 | `gates.py:131-417`、`commands_gates.py:217` | `test_wxg.py:1704-1869` | covered |

结论：21 条里 18 条行为确实有测试，但\"不变量\"这一层本身没有任何机械约束——文本与测试之间是人工映射，删改不变量不会让任何检查变红。

## 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `SKILL.md`（main 块） | both | 写 `commands_misc.py:255-261`；读 `:274-285` |
| `references/contract.md`（full 块） | both | 同上（`--section full`） |
| `references/{design,quality,contract}.md`、`tests/test_wxg.py`、`CHANGELOG.md` | read | `commands_misc.py:327-329`（存在性） |
| `references/export-sample/feat-demo/*.md` | read | `commands_misc.py:339-346` |
| 临时 `state/graph.sqlite`（verify 内真实导出） | write | `commands_misc.py:336-338`、`gen_sample.py:23-52` |
| `WXG_SKILL_DIR` | read | `commands_misc.py:271`（未文档化，只有测试用） |
| `meta.contract_version` / `meta.schema_version` | read | `commands_misc.py:537-540` |
| 同上 | write | `db.py:593-601`（init/迁移）、`commands_misc.py:590-599`（`--fix`） |
| 模块级 `ROLES` | write | `wxg_contract.py:258-259`——**import 即副作用**（追加 `evidence-record`） |

隐式全局状态：`contract`/`verify` 都跳过 `connect()`（`cli.py:65`），所以本切片不碰 `WXG_DB_URL` 与 `.why-exist`；但 `verify` 依赖能被 `import wxg` 的 `sys.path`（`commands_misc.py:300`、`gen_sample.py:22`），以及在临时目录里真实建库。

## 冗余信号

| 项 | 信号 | 把握 |
|---|---|---|
| 版本三套来源 | `__version__=2.23.0`（`whyexist/__init__.py:49`）零读取；`VERSION` 只被 tools 读；HANDOFF `2.91.0`、PRODUCT-PLAN `2.67.0` | high |
| `TOKEN_COMMANDS` vs `COMMANDS[*].token` | 前者零消费且漏 3 条 token 命令 | high |
| `COMMON_ATTRS` vs 手写公共键 | JSON 用常量（`:1009`），markdown 手写（`:942`），`graph.py` 里第三处字面量 | high |
| `DOCTOR_FIXABLE_CHECKS` vs I9 正文 | 清单两处（`:22-30` 与 `:763`） | medium |
| `DESIGN_ANCHOR_KINDS` 在桥接模块 | 供给 `graph.py` 与 `gates.py`，但不进契约文件/文档 | high |
| `CODE_EDGE_KINDS` | `gates.py:124` 与 `EDGE_KINDS` 各一份代码层边集 | medium |
| gate `checks` 名单 vs `GATE_RULES` | `commands_gates.py:237-246` 9 项硬编码，规则 12 条，无映射 | medium |
| `_cmd_write` 兜底分支 | verify 强制全覆盖后不可达（`wxg_contract.py:798`） | low |
| `P()` / positionals | 定义 0 调用，50 条命令 positionals 全空 | high |
| `DEFAULT_ROOT` | `wxg.py:24`、`cli.py:16`、`commands_misc.py:20` 三份 | medium |
| serve 间隔默认值 | 契约 default=5 + `commands_gates.py:120` 兜底 5 | low |
| contract_json 形状 | 无版本/快照，仅 6 条断言；`_jsonable` 可静默改变类型表示 | medium |

## 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `wxg_contract.py` L17-265（版本/条件/kind/判决/规则表/ROLES） | refactor_in_place | 枚举有真实消费且被测试固定；但同文件混着死常量与纯文字，需要拆分并删 `TOKEN_COMMANDS` | 删名字是对包级 API 的移除；规则表文本是已发布内容，改完必须 `--write` + verify |
| `wxg_contract.py` L269-637（COMMANDS） | keep | 50 命令单一定义，CLI 生成，verify 强制处理器/写入列，端到端覆盖 | 无检查确认处理器真的读了声明选项；可选参数不进生成文档 |
| `wxg_contract.py` L640-691（WRITE_MODES） | keep | 键集被 verify + test 双重锁定；值是给人看的短句 | 13 种自由文本无枚举，值写错不报错 |
| `wxg_contract.py` L695-750（ATTR_SCHEMA/COMMON_ATTRS/EXPORT_FILES/EXPORT_RULE） | refactor_in_place | ATTR_SCHEMA 是唯一被强执行的属性契约，但类型语义靠魔法串；其余两个无消费者；EXPORT_FILES 按下标取用 | 收紧类型会拒绝既有扫描数据；重排 EXPORT_FILES 让导出错位而 verify 仍过 |
| `wxg_contract.py` L754-776（INVARIANTS） | freeze | 纯文字、零消费、零测试，却是对外一致性主张的唯一汇总 | 冻结等于留着已知双份表述；要动先建\"不变量↔测试\"映射 |
| `wxg_contract.py` L780-1058（渲染/JSON/块替换） | refactor_in_place | 逻辑简单，但 `--write` 换行转换、只处理第一对标记、strip 容差、KeyError 都是未声明行为；它是 verify 漂移检测的地基 | 本切片风险最高；收紧比较会让现有文件立刻失败，修换行会改已提交字节 |
| `whyexist/contract.py`（`DESIGN_ANCHOR_KINDS` 桥接） | refactor_in_place | 文件自述是过渡；常量是真契约却不进契约文件与文档 | 搬动影响 `maps_to` 校验与 conformance；易在契约文件里再定义一份 |

## 隐含需求（重写会静默丢掉的）

1. `verify` 认 `WXG_SKILL_DIR` 重定向技能根（`commands_misc.py:271`），文档从未提；只有 `test_wxg.py:498` 用。
2. `contract --write` 相对路径以技能根（脚本上两级）解析，不是 cwd（`commands_misc.py:257-258`）。
3. `contract --json` 静默忽略 `--write`/`--section`（`commands_misc.py:251-252` 提前 return）。
4. `--write` 在 Windows 把整文件换行转 CRLF（`Path.write_text` newline=None）：工作树里 SKILL.md 491 行、contract.md 344 行已全 CRLF，`.gitattributes` 却要求 `eol=lf`，git 正在警告；verify 用通用换行读，看不见。
5. 契约块只认第一对 begin/end：第二对既不比较也不替换（实测）。
6. verify 比较前 `strip("\n")`，块边界空行不算漂移——与 README/SKILL 的\"逐字节\"表述有差。
7. `ATTR_SCHEMA` 值 `"任意"` = 跳过类型校验（`graph.py:30-38` else 分支），契约文件不解释。
8. 节点属性强校验、边属性完全自由（`graph.py:184`），`COMMON_ATTRS` 的说明只覆盖前者。
9. `bite` 绕过 `check_attrs` 合并 `attrs.bite` 与 `x_bite_reason`（`commands_graph.py:128-133`），后者不在 `ATTR_SCHEMA`、不在文档。
10. `work_items.role` 就是工单 kind（`work.py:36`）；契约把 `WORK_KINDS` 与 `ROLES` 分两表却没写这层等同。
11. `COMMANDS[*].token` 只是标记，真正拦 token 的是各处理器 `require_token`；`token=True` 9 条 vs `TOKEN_COMMANDS` 6 条，已不一致且无检查。
12. doctor 先查 `judge_history`/`changes`（`:453,468`）再查 meta 版本（`:537`），旧 schema 库只会得到 exit 2 的 `OperationalError`。
13. `doctor --fix` 无条件把 meta 版本刷成当前常量（`:590-599`），能在没迁移的情况下\"对齐\"版本。
14. 生成的命令表\"关键参数\"只列 required 与 store_true：`--fail-reason`、`--edge-kind`、`--section` 在生成块里完全不可见（实测 main/full 都没有）。
15. `verify` 会真实执行导出器并建临时库；导出运行时错误变成一条 issue 而不是崩溃。
16. `tests/test_wxg.py:520` 硬编码 `2.92.0`：升版本要同步改契约、VERSION、CHANGELOG、`contract.md` 与测试断言。

## 值得人判断的问题

1. 规则表与 `INVARIANTS` 继续当\"人读镜像\"，还是拆到 `references/` 由 verify 只比生成块？现在改一个字就改已发布文档，却没有检查能判断改得对不对。
2. 版本号是否收敛成单源（`CONTRACT_VERSION` 读 `VERSION`，或 verify 直接校验 VERSION/CHANGELOG），并把 `tools/check_docs.py` 接进 CI？现在靠\"记得跑 preflight\"。
3. `SCHEMA_VERSION` 要不要真正参与迁移判定（旧库拒服务/按版本选路径）？当前 `--fix` 可以把版本刷成当前值而不修结构。
4. `TOKEN_COMMANDS`、`DESIGN_ANCHOR_KINDS` 是包级可 import 名，外部可能 import；按\"不留副本\"直接删/搬，还是留薄兼容层并写明删除条件？
5. 块替换是否改成真逐字节 + 拒绝多块 + 固定 LF？这会让现有 CRLF 工作树与两份文档立刻失败，需要同时决定重生成流程。
6. 工作树大量未提交修改、git 历史只到 v0.4.1：冻结/重写的基线取当前工作树，还是先整理成可追溯提交？没有这个答案，`freeze` 判定没有回退点。
