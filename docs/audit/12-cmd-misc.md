# 12 命令族：misc 域（export / role-prompt / contract / verify / doctor）

## 切片范围

| 文件 | 行数 | 职责 |
|---|---|---|
| `scripts/whyexist/commands_misc.py` | 619 | 五条命令：只读设计视图导出、角色提示词、契约渲染与块替换、文档/样例漂移自检、状态库体检与 `--fix` |
| `scripts/gen_sample.py` | 120 | `verify` 的确定性 fixture：用 `feature-declare` + 真实 `export` 生成 `references/export-sample/feat-demo` |

任务书说 571 行，磁盘实际 619 行。`commands_misc.py` 里还夹着 8 行 query re-export（197-204），19 行是导入与常量。

这五条命令的注册在 `scripts/wxg_contract.py:623-636`，CLI 分派在 `scripts/whyexist/cli.py:29-44,62-70,94-113`。`verify` 与 `doctor` 是发布安全网：CI 第一步跑 `verify`（`.github/workflows/ci.yml:27-30`），`tools/preflight.py:75-96` 在新建的干净库上跑 `doctor`。

### 测试量（tests/test_wxg.py，85 个 test 方法；全仓 381 个）

| 命令 | 直接调用它的用例数 | 反向/故障注入 | 覆盖到的东西 |
|---|---|---|---|
| verify | 2（`test_contract_verify_detects_drift`、`test_verify_is_side_effect_free`） | 1 个（手改 main 块 → exit 1 + “过期”） | main 块漂移、不建 `.why-exist` |
| doctor | 8（391、569、589、632、925、957、1102、1535 起） | 脏库是零散造的，没有“32 类逐项注入” | 32 类 check 里 8 类被正向触发；6 组 `--fix` 里 3 组被断言 |
| export | 5（189、608、744、1004、1168 起） | 无 | 07 有行/参数去重/竖线转义/04 pattern/01 statement |
| contract | 1（518，只测 `--json`） | 无 | 32 键里 6 键 |
| role-prompt | 1（894） | 无 | audit/scan 的 root 与两段文案 |

去重后共 17 个 test 方法直接调用这五条命令；本次审计实跑了其中 12 个，外加 1 个契约注册表用例（503-516），共 13 个方法。`verify` 的导出样例、full 块、frontmatter、资源缺失、缺标记五类失败分支没有测试；`doctor` 的 24 类 check 与 3 组修复没有测试。`test_contract_commands_cover_roles_and_attrs`（503-516）用与 verify 相同的 `getattr(wxg, ...)` 机制直接断言 handler，不经 verify 本身——它测的是契约表，不是 verify。

## 公开面

| 入口 | kind | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg export` | cli | `commands_misc.py:22` | `--feature`（必填）、全局 `--root` | JSON `{dir,generation,steps,files[6]}` | 建 `<root>/export/<feature>/` 并覆盖写六份 md；读 nodes/edges/features/feature_nodes/work_items；不清理旧文件；不原子 | 0；2（未知 feature/异常） |
| `wxg role-prompt` | cli | `commands_misc.py:207` | `--role`（choices=`ROLES`）、`--token`、`--feature`、`--root` | 纯文本 Markdown 提示词 | 无 DB、无文件；`--token` 明文打印 | 0；2（argparse usage 或 stderr JSON） |
| `wxg contract` | cli | `commands_misc.py:250` | `--json`、`--section main\|full`、`--write <path>` | main/full Markdown；JSON 契约；`{written,section}` | `--write` 原地改写目标文件的第一对标记；Windows 写 CRLF；`--json` 忽略 `--write` | 0；2（文件不存在/缺标记/参数错） |
| `wxg verify` | cli | `commands_misc.py:269` | 无参数；`WXG_SKILL_DIR` | JSON：`{ok:false,issues[]}` 或 `{ok:true,checks[6],version}` | 不连权威库、不建 `.why-exist`；临时目录真实建库跑一次 export 后删除 | 0；1（issues）；2（异常） |
| `wxg doctor` | cli | `commands_misc.py:558` | `--fix`、`--root` | JSON `{ok,issue_count,fixable_count,unfixable_count,unfixable_checks,by_check,truncated,issues[≤200],fixed}` | 默认只读；`--fix` 硬删 bites/edges/feature_nodes、裁 work_items 引用、清 token、刷 meta 版本 | 0；1（问题）；2（缺库/异常） |
| `doctor_report(conn)` | function | `commands_misc.py:355` | conn | `list[dict]`，每条形如 `{check,...}` | 只读 SELECT | 不直接面向 CLI |
| `<root>/export/<feature>/*.md` | file | `commands_misc.py:25-26,38-39,66-193` | feature 作用域 | 六份 Markdown（伪 YAML 头 + 表格；空表一行全空单元格） | 覆盖写 | 写失败 → 2 |
| `SKILL.md` / `references/contract.md` 契约块 | file | `commands_misc.py:274-285`；`wxg_contract.py:1040-1047` | 渲染器输出 | `<!-- wxg:contract:{main,full}:begin/end -->` 之间 | `contract --write` 写，`verify` 读 | 缺标记：verify 1 / write 2 |
| `references/export-sample/feat-demo/*.md` | file | `commands_misc.py:330-348` | `gen_sample.build()` | 六份样例，逐份文本比较 | 只读 | 缺失/过期 → verify 1 |
| env `WXG_SKILL_DIR` | function | `commands_misc.py:271` | 目录路径 | 改变 verify 读文档/样例的技能根（代码仍来自真实安装） | 只读目标目录 | 路径无效 → 多条 issue → 1 |

### 为什么 verify/contract/role-prompt 必须零 DB 连接

`scripts/whyexist/cli.py:62-70` 把 `verify`、`contract`、`role-prompt`、`up` 排除在 `needs_db` 之外：不 `connect`、不 `ensure_db`、不 commit。理由是这三条命令的生命周期早于/独立于项目状态库：

- `verify` 是 CI 在干净 checkout 上的第一步（`.github/workflows/ci.yml:27-30`），那时没有 `.why-exist`；如果它先建空库，干净仓库会永远多出一个不该提交的目录。
- `contract` 是“改契约 → 刷新文档块 → verify”流程里的刷新步骤（`docs/HANDOFF.md:63-70`），与项目状态库无关。
- `role-prompt` 是把任务书交给 teammate 的时刻，通常在状态库还没建或 teammate 还没拿到 root 之前。

三个 handler 都接收 `conn` 但完全不用。`verify` 的“零副作用”只指不碰 cwd 与权威库：它仍会在临时目录里建 SQLite 并跑真实导出（`commands_misc.py:336-338`）。

## 契约表

状态口径：covered = 有测试直接断言；partial = 有测试但只覆盖部分分支；gap = 行为存在但没有测试断言（文档提到但无测试仍记 gap，备注里说明）。

### export

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C1 | 写六份文件，名字/列来自 `EXPORT_FILES`，带 generation/feature_id 头；返回 `{dir,generation,steps,files}` | partial | `commands_misc.py:22-49,66-194`；`test_wxg.py:264-268,608-630` | 只断言 07 存在与参数去重；文件名集合/头/返回结构无断言 |
| C2 | 作用域 = feature_nodes + requirement 前缀 + **当前代 work_items.target_ids 的通配展开** | gap | `commands_misc.py:51`；`workflow.py:94-124`；`_probe_12.py:214` | 探针看到 claim 的 target_ids 进入作用域；无测试无文档 |
| C3 | 01 每行一个 requirement；验收/约束取 feature 级字段并对每行重复 | gap | `commands_misc.py:54-65`；`_probe_12.py:187` | 样例只有一个 requirement |
| C4 | 02 = satisfies 作用域 requirement 的 use_case，去重；顺序来自 edges 扫描（无 ORDER BY） | gap | `commands_misc.py:74-86` | 跨后端顺序不保证 |
| C5 | 04 = use_case 经 depends/associates/realizes 到的 component/port + 作用域 pattern，去重排序 | partial | `commands_misc.py:88-107`；`test_wxg.py:1198-1200` | 只断言 pattern 行 |
| C6 | 05 = contains 的 operation、contains 指向它们的 classifier、has_input 参数；property 永不出现 | gap | `commands_misc.py:109-140`；`_probe_12.py:271`；`wxg_contract.py:744-750` | 无测试 |
| C7 | 07 每条 writes→sink 一行；该 op 的所有断言文本拼进每个 sink 行；步号按发现顺序 | partial | `commands_misc.py:142-154`；`test_wxg.py:264-268`；`_probe_12.py:237` | 探针确认两 sink 时断言文本重复 |
| C8 | 07 追加“请求参数”，按 id 去重、首次出现排序，属性是 attrs_json 原文 | partial | `commands_misc.py:155-162`；`test_wxg.py:608-630` | 只测“只出现一次” |
| C9 | 测试规格 = verifies→operation/use_case 的 testcase + asserts→operation 的 assertion，按 id 去重 | gap | `commands_misc.py:164-193` | 无测试 |
| C10 | 单元格里的竖线转义成 `\|`；空表渲染一行全空单元格 | partial | `commands_misc.py:41-49`；`test_wxg.py:1004-1026` | 竖线有测试；空行/换行无测试 |
| C11 | 未知 feature → Reject（2），且在 ensure_feature 前不建导出目录 | gap | `commands_misc.py:23`；`workflow.py:30-34`；`_probe_12.py:198` | 探针确认不建目录 |
| C12 | 只覆盖六份已知文件，不清理旧文件；逐份写，失败留半套 | gap | `commands_misc.py:25-26,38-39`；`_probe_12.py:194` | 探针留了 99-旧版本.md |
| C13 | 导出目录由 feature id 拼路径；id 允许 `.`/`..`；`--feature ..` 把六份视图写进 `<root>` | gap | `commands_misc.py:25`；`commands_feature.py:45`；`_probe_12.py:426` | 实测 `<root>/export` 根本没创建 |

### role-prompt

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C14 | 输出文本提示：角色/`<root>/graph.sqlite`/CLI 路径/ROLES 允许命令/边界；audit 走直接裁决分支，其他角色追加 work-finish；model-* 追加 pattern，implement-test 追加 construction | partial | `commands_misc.py:207-247`；`test_wxg.py:894-902` | 只测 audit/scan |
| C15 | `--token` 明文写进“你的令牌”段；`--feature` 写 feature 段；都不校验存在性 | gap | `commands_misc.py:243-246`；`_probe_12.py:317` | 凭据可转发 |
| C16 | 未知角色由 argparse choices 拦截；handler 的 Reject 分支经 CLI 不可达 | gap | `commands_misc.py:209-210`；`wxg_contract.py:627-630`；`_probe_12.py:319` | 死分支 |
| C17 | 零 DB、不建 `.why-exist`；root 取 `--root` 或 cwd 默认 | partial | `cli.py:62-70`；`commands_misc.py:211`；`test_wxg.py:894-898`；`_probe_12.py:311` | 测试只断言 root 出现在提示里 |
| C18 | 无条件宣称 `<root>/graph.sqlite` 且只给 `--root`，不感知 `WXG_DB_URL`/后端 | gap | `commands_misc.py:211-218`；`db.py:425-438` | MySQL/PG 下提示词指错库 |

### contract

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C19 | 默认输出 main 契约 Markdown；`--section full` 输出完整契约；不连库 | gap | `commands_misc.py:250-262`；`wxg_contract.py:801,924`；`_probe_12.py:278-281` | 测试只覆盖 `--json` |
| C20 | `--json` 返回 `contract_json()`（32 键），静默忽略 `--write`/`--section` | partial | `commands_misc.py:251-252`；`wxg_contract.py:997-1031`；`test_wxg.py:518-525`；`_probe_12.py:297` | 只断言 6 键 |
| C21 | `--write` 替换第一对标记之间内容、保留块外文本、返回 `{written,section}`；相对路径按 SKILL_DIR 解析 | gap | `commands_misc.py:255-261`；`wxg_contract.py:1040-1047`；`_probe_12.py:289,301` | 无测试；探针确认 |
| C22 | 目标缺失/无标记 → exit 2；标记顺序颠倒 → `replace_block` 解包 ValueError → exit 2 | gap | `commands_misc.py:259-260`；`wxg_contract.py:1043-1047`；`cli.py:85-90`；`_probe_12.py:307` | 错误信息是异常原文 |
| C23 | `--write` 用平台默认换行，Windows 整文件 CRLF；verify 看不见 | gap | `commands_misc.py:260`；`_probe_12.py:291`；`.gitattributes:3` | 探针 234/234 行 CRLF |
| C24 | full 块漂移的修复提示 `--write contract.md` 解析到技能根，照做 exit 2 | gap | `commands_misc.py:285,257-258`；`_probe_12.py:371,417` | 提示丢了 `references/` |

### verify

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C25 | 比较 SKILL.md main 块与 references/contract.md full 块，漂移记 issue 并 exit 1；缺标记也算 issue | partial | `commands_misc.py:274-285`；`test_wxg.py:481-501`；`_probe_12.py:371,378` | 反向测试只有 main |
| C26 | frontmatter 必须以 `---` 开头、含 `name: why-exist-graph` 与 `description:` | gap | `commands_misc.py:287-298`；`_probe_12.py:390` | 无测试 |
| C27 | 交叉引用：每条命令有 handler 且进 WRITE_MODES；ROLES 只引用已注册命令；ATTR_SCHEMA/BIND_EDGE_KIND kind 存在；导出列非空；五类资源存在 | partial | `commands_misc.py:299-329`；`test_wxg.py:503-516` | 测试用同机制直接断言，不经 verify；失败分支多无测试 |
| C28 | 临时建库真实导出，与 export-sample 六份逐份比较；缺失/过期各记 issue；异常收成一条自检失败 | gap | `commands_misc.py:330-348`；`gen_sample.py:38-61`；`_probe_12.py:359,364` | 无反向测试 |
| C29 | 成功返回固定六项 checks + version；失败返回 `{ok:false,issues[]}` | partial | `commands_misc.py:350-352`；`cli.py:94-96`；`_probe_12.py:353` | checks/version 无断言（版本升级无人提醒） |
| C30 | 零 DB/不建 .why-exist；会建临时库并删除；`WXG_SKILL_DIR` 可重定向被检查根 | partial | `cli.py:62-70`；`commands_misc.py:271,336-338`；`test_wxg.py:873-882`；`_probe_12.py:328` | 只测不建 `.why-exist` |
| C31 | 名为“逐字节”实为文本比较：换行/块外空行不影响；只处理第一对标记；伪造第二对不被检查 | gap | `wxg_contract.py:1040-1054`；`commands_misc.py:279-284`；`_probe_12.py:402,414` | 探针：CRLF 全改仍 PASS；第二对标记仍 PASS |

### doctor

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C32 | 32 类 check，每条 `{check,...}`；汇总字段含 ok/计数/by_check/truncated/issues≤200 | partial | `commands_misc.py:355-555,601-617`；`test_wxg.py:408-414` | 32 类只有 8 类有测试 |
| C33 | 干净 exit 0，有问题 exit 1；`--fix` 后按修复后状态重算 ok | covered | `commands_misc.py:558-617`；`cli.py:94-96`；`test_wxg.py:391-428` | |
| C34 | 不带 `--fix` 的 doctor 只读，两次运行主库 hash 不变 | gap | `commands_misc.py:355,558-601`；`_probe_12.py:101`；`quality.md:12` | 文档要求，无测试 |
| C35 | `--fix` 六组修复：删悬空 bite/edge/feature_node、裁非 audit 工单引用、清非 claimed token、刷 meta 版本 | partial | `commands_misc.py:561-600`；`test_wxg.py:415-425`；`_probe_12.py:130,146` | 只有 3/6 组有测试 |
| C36 | `--fix` 只修 `DOCTOR_FIXABLE_CHECKS` 7 类；其余只报不修 | partial | `wxg_contract.py:22-30`；`commands_misc.py:602-612`；`test_wxg.py:675-679`；`_probe_12.py:172` | 只断言 legacy 不可修；清单与 I9 双份 |
| C37 | 任何 `exit_code≠0` 的 evidence 都是问题且不可修；没有删除 evidence 的 CLI | gap | `commands_misc.py:440-441`；`_probe_12.py:158`；`wxg_contract.py:153-158` | 与“每次测试都登记”冲突 |
| C38 | 校验 evidence generation/工单/产物存在/hash；复算 BehaviorPassed 证据 | partial | `commands_misc.py:437-451,528-534`；`evidence.py:19-35`；`test_wxg.py:569-606` | evidence-work-missing、behavior-passed-without-evidence 无测试 |
| C39 | 校验 claimed_by/claimed_at、audit actor/独立性、passed-without-audit、audit-passed-subject-not、legacy | partial | `commands_misc.py:397-435,542-554`；`test_wxg.py:675-679` | 只有 legacy 有测试 |
| C40 | 校验 feature 当前代条件存在、每代 8 行齐全、Ready 一致、BehaviorPassed 有证据 | gap | `commands_misc.py:502-534` | 四类全无测试 |
| C41 | 校验 changes 的 generation/from-condition/条件行/继承边界 | partial | `commands_misc.py:468-494`；`test_wxg.py:1535-1551` | 只有 change-inheritance 有反例 |
| C42 | 作用域外所有 pattern 必须有 applicability/not_applicable（不要求 applies 边） | gap | `commands_misc.py:496-500`；`wxg_contract.py:701-709` | 无测试 |
| C43 | 比对 meta 两个版本；`--fix` 直接 upsert 当前值，不做结构迁移 | partial | `commands_misc.py:537-540,590-599`；`test_wxg.py:402-425`；`_probe_12.py:150` | 可把版本刷对而结构仍旧 |
| C44 | 不校验 kind/verdict/attrs 枚举与类型：直写库的非法值不会报 | gap | `commands_misc.py:355-555`；`graph.py:13-41` | “体检通过”有盲区 |
| C45 | 每次运行算两遍 doctor_report（before 未用）；`fixed.meta` 恒 1 | gap | `commands_misc.py:559,600`；`_probe_12.py:150` | 修复计数会误导 |
| C46 | issues 最多 200 条，`truncated` 标记；by_check 统计全部；无分页 | partial | `commands_misc.py:604-615`；`test_wxg.py:414` | 只测 truncated=false |

### 跨命令

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C47 | verify/contract/role-prompt 不 connect 不建 `.why-exist`；doctor/export 缺库 exit 2 且不建目录 | partial | `cli.py:62-70`；`test_wxg.py:873-882,947-955`；`_probe_12.py:328` | 缺库不创建只测了 gate/work-seed/repo-list |
| C48 | Reject/异常 → stderr JSON + exit 2；argparse 层错误 → usage 文本 | partial | `cli.py:85-90,29-44`；`_probe_12.py:319` | argparse 绕过 JSON 通道未声明 |
| C49 | verify/doctor 无论成败都 stdout JSON 按 ok 决定 0/1；role-prompt 打纯文本；export/contract 打 JSON 或文本 | covered | `cli.py:94-113`；`test_wxg.py:487,896` | |

## 状态读写

| 目标 | 读写 | 位置 |
|---|---|---|
| `nodes` | read | `commands_misc.py:54-99,358,382,496,502` |
| `edges` | read | `commands_misc.py:76,90,111,117,124,144,149,174,178,183,365,371` |
| `features` | read | `commands_misc.py:23`（经 `workflow.ensure_feature`）、`:502` |
| `feature_nodes` | both | 读 `workflow.py:104`；删 `commands_misc.py:568` |
| `work_items` | both | 读 `commands_misc.py:386-429,464,542`；写 `:581-584`、`:587-589` |
| `conditions` | read | `commands_misc.py:474-527` |
| `evidence` | read | `commands_misc.py:437-451,529` |
| `judge_history` | read | `commands_misc.py:453-466` |
| `changes` | read | `commands_misc.py:468-494` |
| `bites` | both | 读 `:360`；删 `:562-564` |
| `meta` | both | 读 `:537-540`；写 `:590-599` |
| `<root>/export/<feature>/*.md` | write | `commands_misc.py:25-26,38-39,66-193` |
| `SKILL.md` / `references/contract.md` | both | 读 `:279`；写 `:255-261` |
| `references/{design,quality,contract}.md`、`tests/test_wxg.py`、`CHANGELOG.md` | read | `:327-329`（仅存在性） |
| `references/export-sample/feat-demo/*.md` | read | `:332-346` |
| 临时 state 库与导出目录 | write | `:336-338` |
| env `WXG_SKILL_DIR` | read | `:271` |
| 模块级 `DEFAULT_ROOT` | read | `:20,211`（`args.root_path` 始终存在，实际是死回退） |
| `sys.modules['wxg']` / `sys.path` | read | `:300`；`wxg.py:20-24`；`gen_sample.py:17-19` |

跨命令共享状态：`--root`（默认 `./.why-exist`）、`WXG_DB_URL`（本切片不读）、`WXG_SKILL_DIR`（只被 verify 与测试用）、`C.EXPORT_FILES`/`C.ROLES`/`C.DOCTOR_FIXABLE_CHECKS`/`C.CONTRACT_VERSION`、两个契约块标记、`references/export-sample` 的字节内容。`verify` 还有一层隐式全局：它 `import wxg` 并要求入口模块已注册（`commands_misc.py:300`），所以它依赖调用方式，而不是纯函数。

## 冗余

| 条目 | 信号 | 把握 |
|---|---|---|
| `commands_misc.py:197-204` 的 query re-export | `wxg.py:75-81` 直接从 `whyexist.query` 导入；全仓无 `from ...commands_misc import cmd_get/cmd_find` 调用点 | high |
| `:15` 导入 `make_temp_dir` 但只用 `temp_dir` | 本文件 grep 只有 import 行 | high |
| `:559 before = doctor_report(conn)` 未使用 | 每次 doctor 多跑一遍全库检查 | high |
| `:600 fixed["meta"]=1` 硬编码 | 干净库 `--fix` 仍报 meta:1（探针 A6） | high |
| verify 的 `checks` 名单（`:352`） | 6 项手写，实际检查还包括 frontmatter/资源/kind/导出列 | high |
| `DOCTOR_FIXABLE_CHECKS` 与 I9 正文各一份 7 项清单 | `wxg_contract.py:22-30` vs `:763` | medium |
| 32 个 check 名是散落的字符串字面量 | 无枚举表；测试只能字符串匹配 | medium |
| role-prompt 的未知角色双校验 | `:209-210` 经 CLI 不可达 | high |
| `DEFAULT_ROOT` 三份 | `cli.py:16`、`wxg.py:26`、`commands_misc.py:20` | medium |
| `EXPORT_RULE` 文本与 `cmd_export` 硬编码逻辑两份 | 输出不读规则文本，可一起漂移 | medium |
| `commands_repo.py:728-735` 再导出本模块 | 与 `wxg.py:157-164` 双层 facade | medium |
| `quality.md:43` 声称 applies-invalid 有反例测试 | 测试里该字符串 0 次；`quality.md:12` 的 doctor hash 稳定性也无测试 | high |

## 分区判定

| 模块/单元 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `commands_misc.py:cmd_verify`（269-352） | refactor_in_place | 只读、临时目录自清理、检查项互相独立；缺反向测试、checks 名单是手写常量、修复提示指错路径。保留骨架补测试，比推倒重来稳 | 收紧成真字节比较会让当前 CRLF 工作树与两份文档立刻红；改 checks 名单会改 stdout 契约 |
| `commands_misc.py:doctor_report`（355-555） | refactor_in_place | 只读、意图清楚；24 类无测试、check 名无枚举、缺 kind/verdict/attrs 校验。按检查项拆函数并补 fixture 即可 | 新增枚举校验会让历史直改库突然变红；拆函数容易改 issue 字段形状 |
| `commands_misc.py:cmd_doctor --fix`（558-617） | freeze | 切片里唯一删数据的路径：硬删三类行、改写 work_items、清 token、刷 meta。6 组修复有 3 组零测试，meta 计数是假的，stamp 版本还能掩盖未迁移旧库。先把“删什么/能否备份/元数据算不算修复”定成契约，不许动 | 改 SQL 条件可能误删活数据；改 meta 行为会让既有 `--fix` 脚本失效；SQLite 默认没有回退点 |
| `commands_misc.py:cmd_export`（22-194） | refactor_in_place | 边界清楚（六份视图、作用域可枚举），但六段遍历挤在一个函数、按下标取 `EXPORT_FILES`、无 ORDER BY、不清理旧文件、非原子。抽成“作用域查询 + 六个 projection”并补测试 | 改排序会改导出字节与 export-sample；改作用域会影响 verify 与用户已有产物；默认删除旧文件会误删手工产物 |
| `commands_misc.py:cmd_contract`（250-262） | refactor_in_place | 20 行、职责单一；但 `--write` 零测试，CRLF/相对路径/缺标记/`--json` 静默忽略都是未声明行为，错误不可读。补测试与明确解析即可 | 固定 LF 会改已提交文档字节；限制写入白名单会破坏 HANDOFF 的用法 |
| `commands_misc.py:cmd_role_prompt`（207-247） | keep | 纯字符串拼装、无 I/O、audit/scan 有端到端断言；契约由 ROLES 单点驱动 | token 明文与后端不感知是产品决策，不是实现问题 |
| `commands_misc.py:10-20,197-204`（导入/常量/re-export） | rewrite | 未用导入、无人消费的 query re-export、第三份 DEFAULT_ROOT 都是拆包残留；删掉行为不变 | 低；先全局搜 `whyexist.commands_misc` 引用（当前只有 wxg.py 与 commands_repo.py） |
| `scripts/gen_sample.py` | keep | 确定性 fixture，直接复用 `cmd_export` 而非另写渲染；verify 与 README 都依赖 | 它依赖 `sys.modules['wxg']` 注册，改 wxg.py 会影响 verify 的样例自检 |
| `references/export-sample/feat-demo/*.md` | keep | 生成产物，由 `gen_sample --write` 刷新、verify 比对 | 导出排序/格式一变必须整组重生成，否则 verify 立刻红 |

没有给 `verify` 判 rewrite，是因为它的行为简单、边界清楚，但“逐字节”与“检查覆盖面”两个语义没定；在那之前重写等于把未定行为固化。`--fix` 判 freeze，不是因为它代码烂，而是因为它会删数据且删哪些没被测试锁定。

## 隐含需求（重写会静默丢掉的行为）

1. export 的作用域吸收当前代 `work_items.target_ids` 的通配模式，不只是 `feature_nodes`。
2. 01 的验收/约束是 feature 级字段，对每个 requirement 行重复。
3. 07 的断言文本在每个 writes→sink 行重复。
4. 02/05/07/测试规格 的行顺序依赖 SQL 返回顺序；SQLite 稳定，MySQL/PG 不保证。
5. 05 永不导出 property，即使 classifier contains property。
6. 空表渲染一行全空单元格，不是空表体。
7. export 不清理旧文件、不是原子写。
8. feature id 允许 `.`/`..`；`--feature ..` 把六份视图写进 `<root>`。
9. role-prompt 明文打印 claim_token。
10. role-prompt 不读 `WXG_DB_URL`，MySQL/PG 下仍宣称 `<root>/graph.sqlite`。
11. role-prompt 的路径是生成时的绝对路径，换机器失效。
12. `contract --write` 相对路径按技能根解析，不是 cwd。
13. `contract --json` 静默压过 `--write`/`--section`。
14. `--write` 在 Windows 把整文件转 CRLF，verify 看不见。
15. verify 只检查第一对标记；第二对伪造标记不报。
16. verify 的比较是文本相等 + strip 块外换行，不是逐字节。
17. verify 的 full 块修复提示丢 `references/`，照做 exit 2。
18. verify 会真实执行 gen_sample → cmd_export → 建临时 SQLite。
19. `WXG_SKILL_DIR` 能重定向被检查根，但代码仍从真实安装导入。
20. doctor 默认只读但仍走 `PRAGMA journal_mode=WAL` 与 CLI 末尾 commit。
21. doctor 把 `exit_code≠0` 的 evidence 当问题，且没有删除 evidence 的命令。
22. doctor `--fix` 会改写 superseded 旧代工单的 target_ids/evidence_ids（只跳过 audit）。
23. doctor `--fix` 的 meta 刷新不做结构迁移。
24. `fixed.meta` 恒 1。
25. issues 上限 200，无分页。
26. doctor 不校验 kind/verdict/attrs 的枚举与类型。
27. evidence 的 artifact_path 在登记时 resolve 成绝对路径，移动目录后 doctor 报缺失。
28. SQLite 后端下，除 verify/contract/role-prompt/up/init 外所有命令都要求 graph.sqlite 已存在，并在连接前做文件检查。
29. 所有 DB 命令 handler 返回后无条件 `conn.commit()`，包括纯读。
30. `doctor_report` 是模块级公开名（被 wxg.py 再导出），行为改变会影响外部 import。

## 值得人判断的问题

1. verify 要做真字节比较（拒绝 CRLF/多标记/块外改动），还是维持文本归一化并把文档里的“逐字节”改掉？前者会让当前工作树立刻失败。
2. verify 的检查范围要不要扩展到 VERSION/CHANGELOG/README/quality 的版本一致性？现在 README 写 1.1.0/2.67.0、quality 写 2.42.0/357 用例、HANDOFF 写 2.91.0，全部无人管；`tools/check_docs.py` 又不在 CI。
3. doctor 是“交付门”还是“诊断工具”？是门，`exit_code≠0` 的 evidence 就不该是问题；是诊断，就不该用退出码 1 表达。
4. `doctor --fix` 允许硬删 bites/edges/feature_nodes 吗？要不要先备份/导出被删行，或改成 `--apply --yes` 两步？
5. `doctor --fix` 的 meta 刷新算修复还是掩盖？schema_version 不匹配时要不要拒绝 stamp、要求先跑 `init` 迁移？
6. doctor 要不要补 kind/verdict/attrs 的枚举与类型校验？补了旧库会变红，不补“体检通过”有盲区。
7. export 要不要清理旧文件、原子写、固定排序（跨后端字节一致）？
8. feature id 要不要禁止 `.`/`..`（或以点开头）？会改已有命名。
9. role-prompt 的 token 要不要脱敏/一次性令牌，是否应感知 `WXG_DB_URL` 输出 `--db-url`？
10. `contract --write` 是否限制为 SKILL.md / references/contract.md 两个已知路径？现在能改写任意带标记文件。
11. verify 失败提示要不要直接给可复制的正确路径（`--write references/contract.md`）？
12. `WXG_SKILL_DIR` 是测试后门还是公开能力？公开就写进契约并校验目录结构；是后门就改成参数或 fixture。

## 验证记录

- `python scripts/wxg.py verify` → `ok:true`，checks 六项，version `wxg contract v2.92.0 / schema v9`，exit 0。
- `python -m unittest` 选取 12 个直接调用本切片命令的用例 + 1 个契约注册表用例 → `Ran 13 tests ... OK`。未跑 5 个长流程/迁移用例（`test_full_flow_reaches_pass_gate`、`test_init_migrates_legacy_work_items`、`test_init_backfills_evidence_generation_from_work_item`、`test_chain_calls_get_unmapped_nodes`、`test_judge_history_keeps_failures_and_clears_stale_reason`）。
- `python docs/audit/_probe_12.py` 全跑通，关键结果：
  - doctor 干净库 `ok:true, issues=0`；连跑两次主库 hash 不变。
  - 注入 7 类可修问题 → 7 个 issue；`--fix` 六组计数 `{dangling_bites:1, orphan_edges:1, feature_nodes:1, work_refs:1, tokens:1, meta:1}`，修后 `ok:true`；再 `--fix` 仍报 `meta:1`。
  - 登记 `exit_code=1` 的 evidence → doctor exit 1，只有 `evidence-exit-nonzero`。
  - `applies-invalid`/`legacy-identity` 经 `--fix` 仍在，进 `unfixable_checks`。
  - export：01 两行 requirement 重复 feature 级验收；07 两 sink 两断言 → 断言文本重复两行；参数只列一次；重导出不删 `99-旧版本.md`；未知 feature exit 2 不建目录。
  - contract：无库输出 main 文本；`--write` 保留块外、重复写字节幂等；CRLF 234/234；`--json` 不改文件；相对路径落到技能根；缺标记 exit 2。
  - role-prompt：无库运行不建 `.why-exist`、默认根写进提示；token/feature 段出现；未知角色走 argparse usage；implement-test 有 construction 提示。
  - 白名单：verify/contract/role-prompt 在干净 cwd exit 0 且不建 `.why-exist`；doctor/export exit 2。
  - verify 反向：导出样例漂移/缺样例/full 块漂移/缺 main 标记/缺 quality.md/frontmatter name 不符全部 exit 1 且带对应 issue。
  - 比较语义：整文件 CRLF 仍 PASS；伪造第二对标记仍 PASS；按提示 `--write contract.md` exit 2。
  - feature id `..`：六份视图写进 `<root>`，`<root>/export` 不存在。
- 探针临时目录 `docs/audit/_probe_12_tmp/` 在脚本末尾删除；可重复运行。
