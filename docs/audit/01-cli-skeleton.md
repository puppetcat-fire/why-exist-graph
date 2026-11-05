# 01 CLI 骨架与分派 — 行为契约审计

## 切片范围

| 文件 | 行数 | 本片要回答的问题 |
|---|---|---|
| `scripts/whyexist/cli.py` | 115 | 哪些命令连库、退出码怎么映射、错误怎么翻译 |
| `scripts/wxg.py` | 181 | 入口是什么、re-export 到底是给谁用的 |
| `scripts/whyexist/errors.py` | 13 | `Reject` 的边界 |
| `scripts/whyexist/jsonio.py` | 78 | 序列化/时间/令牌格式是否稳定契约 |
| `scripts/whyexist/temp.py` | 42 | 临时目录为什么不用 `tempfile`、这条知识有没有测试兜住 |
| `scripts/whyexist/__init__.py` | 49 | 包公开面与版本常量 |

不在本片：各 `commands_*` 的业务语义（只按“它们返回什么形状、抛不抛 Reject”取接口）、`db.py` 的 schema 与方言适配（只在 `connect/ensure_db` 这一层被引用）、`wxg_contract.py` 的契约内容（只当数据源）。

方法：`read` 读全部六个文件 + 相关测试；`grep` 找 `import wxg`、`WXG_DB_URL`、`args.json`、`--db-url`、`DEFAULT_ROOT` 的引用；用 AST 统计 `wxg.py` 的 re-export 面；在临时目录实测 11 条命令路径；跑 `tests.test_package_units.JsonIoTest`（12 例全绿）与 5 个 CLI 骨架用例（全绿）。未改任何源码。

## 公开面

进程级入口只有一条：`python scripts/wxg.py`。没有 `pyproject.toml`/`setup.py`，没有 console_scripts，`cli.py` 也没有 `__main__` guard。

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `scripts/wxg.py <cmd>` | cli | `wxg.py:180-181` | 50 个子命令之一；全局 `--root`/`--db-url` 必须在子命令前 | stdout：dict → `json.dumps(indent=2)`；str → 原样；参数错误 → argparse usage | 插 `scripts/` 进 `sys.path`；脚本模式把 `__main__` 注册为 `sys.modules["wxg"]`；建/开状态库；统一 commit、close | 0 / 1 / 2 |
| `--root` | cli | `cli.py:22,53-54` | 目录；省略 = `cwd/.why-exist`（**import 时**求值） | 无输出；绝对路径进 `args.root_path` | 只解析 | 非法 → 2 |
| `--db-url` | cli | `cli.py:23-27,55-61` | `mysql:// mariadb:// postgresql:// postgres://` | 无直接输出；`db_backend()` 读后端名 | **改写 `os.environ["WXG_DB_URL"]` 且不恢复** | 未知协议 → JSON + 2 |
| `verify` | cli | `cli.py:65,94-96`；`commands_misc.py:269-352` | 无参；技能根由 `WXG_SKILL_DIR` 覆盖 | `{ok, issues[], checks[], version}` | 只读文档与样例；系统临时目录建 `wxg-verify-*` 跑 `gen_sample` 后删 | 0 / 1 / 2 |
| `contract` | cli | `cli.py:65`；`commands_misc.py:250-262` | `--json` / `--write` / `--section` | JSON 契约 / markdown / `{written,section}` | `--write` 覆写 `SKILL.md` 或 `references/contract.md` 的契约块 | 0 / 2 |
| `role-prompt` | cli | `cli.py:65,109-110`；`commands_misc.py:207-247` | `--role`（必填 8 选 1）、`--token`、`--feature` | **纯 markdown，不是 JSON** | 无（实测不建 `.why-exist`） | 0 / 2 |
| `up` | cli | `cli.py:65`；`commands_repo.py:62-127` | `--feature/--repo/--path/--template` | `{root,template,repo,feature,gate_result,gate,next[]}` | 自建连接与提交：`init_db` + 可选 `demo-repo/demo.py` + repo-add + feature-declare + 跑一次 gate | 0 / 2 |
| 其余 46 个子命令 | function | `cli.py:78-84,109-113` | argparse Namespace | dict → JSON；str → 原样 | 由 handler 决定；返回后统一 commit | 0 / 2 |
| 退出码映射 | function | `cli.py:94-113` | handler 返回值 | int | 无 | 见契约表 C12–C18 |
| 异常兜底 | function | `cli.py:85-90` | `Reject` / 任意 `Exception` | stderr 紧凑 JSON，无 traceback | 不 commit | 2 |
| `build_parser` / `main` | function | `cli.py:20-45,48-113` | `C.COMMANDS` + argv | parser / int | 改 stdout 编码、改环境变量 | 同 CLI |
| `jsonio.*` | function | `jsonio.py:15-78` | JSON 值 / 文本 / `@路径` | 字符串、解析值、32 位 hex、`YYYY-MM-DDTHH:MM:SSZ` | 读任意 `@` 文件 | 坏输入 → Reject |
| `temp.*` | function | `temp.py:21-42` | prefix | 临时目录 `Path` | 建目录；退出时 `rmtree(ignore_errors=True)` | 耗尽 → RuntimeError |
| `<root>/graph.sqlite` + `meta` | table | `cli.py:66,70`；`db.py:458-465,468-483` | root + 后端 | 连接 | sqlite：`mkdir -p root`、建库、三条 PRAGMA；mysql/pg 只连不建 | 未初始化 → 2 |
| `SKILL.md` / `references/contract.md` | file | `commands_misc.py:255-261,272-296` | `--write` / verify | 覆写后的块 / 问题列表 | 仓库内文件写入（仅 `--write`） | verify 漂移 → 1 |

## 契约表

状态：covered = 有测试直接断言；partial = 有测试但漏分支；gap = 代码里有、无人断言。

### 入口与参数

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C1 | 唯一入口是 `python scripts/wxg.py`（无 `__main__` guard、无打包入口） | `wxg.py:180-181`；`ci.yml:28`；`test_wxg.py:20,62-68` | covered |
| C2 | `--root` 省略时根是 **cwd** 下的 `.why-exist` | `cli.py:16,53-54`；`test_wxg.py:873-882` | partial（只有 verify 用默认根；init 用默认根无测试） |
| C3 | `--root` 解析成绝对 realpath（Windows 8.3 短路径归一） | `cli.py:53-54`；`test_wxg.py:48-51,894-898` | covered |
| C4 | `--db-url` 覆盖 `WXG_DB_URL`，四协议可识别，未知协议 JSON + 2 | `cli.py:55-61`；`db.py:429-438` | partial（`--db-url` 路径零测试，两个后端测试都走环境变量） |
| C19 | argparse 错误 → usage 文本 + 2，**不是 JSON** | `cli.py:28-44`；`test_wxg.py:904-907` | partial（只测了非法 choices；缺必填/未知命令实测无断言） |

### 零副作用与状态库

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C5 | sqlite 下 `graph.sqlite` 不存在 → 预检失败、JSON + 2、**不建目录** | `cli.py:66-69`；`test_wxg.py:947-955` | covered |
| C6 | `verify`/`contract`/`role-prompt` 永不 connect、不建 `.why-exist` | `cli.py:62-65,70`；`test_wxg.py:873-882` | partial（只断言了 verify） |
| C7 | `up` 例外：自带连接与提交，可在未初始化目录自建库 | `cli.py:64-65`；`commands_repo.py:62-73`；`test_plan_cli.py:337-351` | covered |
| C38 | 库存在但无 `meta` 表 → `ensure_db` 拒绝并提示 init | `db.py:468-483`；`cli.py:79-80` | gap（没有半初始化夹具） |

### 输出与错误边界

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C8 | 成功输出 stdout：dict → `json.dumps(indent=2, ensure_ascii=False)`，str → 原样 | `cli.py:109-113`；`test_wxg.py:61-83,894-902` | covered |
| C9 | `Reject` → stderr `{"error": ...}` + 2 + 无 traceback | `cli.py:85-87`；`test_wxg.py:531-532,858-859,868-871` | covered |
| C10 | 非预期异常 → `{"error": "Type: msg"}` + 2 | `cli.py:88-90` | gap（零测试） |
| C11 | 连接期失败给可读错误（不是 traceback） | `cli.py:58-61,70`；`db.py:441-465`；`SKILL.md:277`；`wxg_contract.py:221` | **gap — 实测违背**：traceback + 1 |
| C20 | `--json` 影响输出格式 | `cli.py:95-99,112`；`commands_misc.py:251` | gap（gate/coverage 的 `--json` 是 no-op） |
| C21 | stdout 强制 UTF-8 | `cli.py:49-50` | gap（测试统一设 `PYTHONIOENCODING`，掩盖了它；stderr 未处理） |
| C22 | `main(argv)` 可进程内调用 | `cli.py:48-113` | gap（全部测试走 subprocess；`DEFAULT_ROOT` import 时固定） |

### 退出码

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C12 | verify：ok → 0，issues → 1 | `cli.py:94-96`；`commands_misc.py:350-352`；`test_wxg.py:481-487,495-501` | partial（失败只断言 `!= 0`） |
| C13 | doctor：ok → 0，否则 1；`--fix` 只修可判定项 | `cli.py:94-96`；`commands_misc.py:558-617`；`test_wxg.py:408,586,605` | covered |
| C14 | gate：PASS → 0，否则 1，且只读 | `cli.py:97-99`；`commands_gates.py:320`；`test_wxg.py:255,299-306,868` | covered |
| C15 | apply：ok → 0，冲突 → 1 且不写 | `cli.py:100-102`；`commands_compiler.py:259-295`；`test_plan_cli.py:448,483` | covered |
| C16 | reconcile：converged → 0，有待办 → 1 | `cli.py:103-105`；`commands_gates.py:106`；`test_wxg.py:258,1331` | covered |
| C17 | serve 恒 0，摘要由 handler 打印、cli 不重复输出 | `cli.py:106-108`；`commands_gates.py:143-151`；`test_wxg.py:1668-1676` | covered |
| C18 | serve 参数非法 → 2 | `commands_gates.py:121-125`；`test_wxg.py:1698` | covered |

### 工具函数格式

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C23 | `dumps` 紧凑、键排序、不转义中文 | `jsonio.py:19-20`；`test_package_units.py:27-28` | covered |
| C24 | `utc_now` 秒级 UTC、以 `Z` 结尾 | `jsonio.py:15-16`；`test_package_units.py:80-81` | partial（只断言结尾 Z） |
| C25 | `new_token` = 32 位小写 hex | `jsonio.py:77-78`；`test_package_units.py:75-78` | covered |
| C26 | `loads`：空 → default、容器透传、坏 JSON → Reject | `jsonio.py:23-31`；`test_package_units.py:30-39` | partial（list/int/bool 分支未测） |
| C27 | `load_json_arg`：`@文件`（utf-8-sig）、报错含形状/文件/行列号 | `jsonio.py:34-59`；`test_package_units.py:41-62` | covered（空串边界未测） |
| C28 | `load_id_list`：逗号 / JSON 数组 / `@文件`；非字符串数组拒绝 | `jsonio.py:62-74`；`test_package_units.py:64-73`；`test_wxg.py:884-892` | covered |
| C29 | `make_temp_dir`：系统 temp、Windows 默认 ACL、POSIX 0o700、撞名重试、100 次耗尽报错 | `temp.py:21-33`；`test_wxg.py:47`；`test_plan_cli.py:50` | partial（只覆盖正常路径） |
| C30 | `temp_dir` 退出删除且忽略失败 | `temp.py:36-42` | gap（无用例断言目录消失） |
| C31 | `Reject` 全包唯一，跨层 `except` 有效 | `errors.py:12-13`；`wxg.py:23-24,50`；`cli.py:13,85` | covered |

### 兼容层

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C32 | 分派用 `getattr(wxg, "cmd_*")`，`wxg` 必须暴露全部 50 个 handler | `cli.py:71-82`；`commands_misc.py:299-303`；`test_wxg.py:514-515` | covered |
| C33 | `wxg` 兼容面：`upsert_node/upsert_edge/bind_node/connect/init_db/make_temp_dir/temp_dir/Reject/cmd_init/cmd_export/cmd_feature_declare` 可用 | `wxg.py:30-178`；`gen_sample.py:43-104`；`test_wxg.py:612-624`；`test_plan_cli.py:24,50` | partial（只有这 11 个真有外部引用） |
| C34 | 库式调用 `cli.main` 时应给可读错误而非 traceback | `cli.py:71-72`；`wxg.py:18-24` | gap（`import wxg` 在 try 外） |
| C35 | role-prompt 内容：真实 root、`work-judge`/`work-finish --token` 等角色边界 | `commands_misc.py:207-247`；`test_wxg.py:894-902` | covered（只测 audit/scan 两角色） |
| C36 | `contract --json` 形状与键集一致 | `test_wxg.py:518-525` | covered |
| C37 | `contract --write` 相对路径基准是技能根，替换契约块 | `commands_misc.py:255-261` | gap（零测试的仓库写操作） |

统计：38 条，covered 20 / partial 9 / gap 9。

## 实测记录（临时目录，未改源码）

| 命令 | 结果 |
|---|---|
| `wxg.py verify`（空 cwd，无 `--root`） | exit 0；stdout JSON `ok:true`；cwd 仍为空 |
| `wxg.py --root <不存在> gate --feature x` | exit 2；stderr `{"error":"状态库未初始化：先运行 \`wxg init\`"}`；目录未创建 |
| `wxg.py role-prompt --role audit`（空 cwd） | exit 0；markdown 到 stdout；cwd 仍为空 |
| `wxg.py contract --json`（空 cwd） | exit 0；契约 JSON；cwd 仍为空 |
| `wxg.py --db-url bogus://x gate ...` | exit 2；stderr JSON「不支持的 WXG_DB_URL 协议：bogus」 |
| `wxg.py --db-url postgresql://u:p@127.0.0.1:1/db gate ...` | **exit 1；Traceback**；`Reject: PostgreSQL 连接失败：connection timeout expired`，抛出点 `db.py:456`，调用点 `cli.py:70`（在 try 之外） |
| `wxg.py gate`（缺 `--feature`） | exit 2；usage 文本到 stderr |
| `wxg.py no-such-cmd` / 无子命令 | exit 2；usage 文本 |
| `wxg.py init`（空 cwd） | exit 0；建 `.why-exist/graph.sqlite`；输出 `{root,db,backend,schema_version,contract_version,migrated}` |
| `wxg.py --root <指向文件> gate` | exit 2；被 sqlite 预检拦下（不会走到 `connect` 的 mkdir） |
| `python -m whyexist.cli verify` | **exit 0、零输出**（没有 `__main__` guard，模块体只定义了函数） |

测试子集：
`python -m unittest tests.test_package_units.JsonIoTest -v` → 12 passed；
`... test_verify_is_side_effect_free test_missing_db_commands_do_not_create test_role_prompt_uses_real_root test_serve_validates_interval test_contract_json_is_serializable` → 5 passed。

## 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `<root>/graph.sqlite` | both | `cli.py:66,70`；`db.py:459` |
| `<root>/`（sqlite 后端 mkdir） | write | `db.py:458`（经 `cli.py:70`） |
| `meta` 表存在性 | read | `db.py:481`（经 `cli.py:80`） |
| `WXG_DB_URL` | both | `cli.py:55-56` 写；`db.py:426` 读 |
| `WXG_SKILL_DIR` | read | `commands_misc.py:271` |
| `SKILL.md` | both | `commands_misc.py:272,289-297` 读；`255-260` 写 |
| `references/contract.md` | both | `commands_misc.py:273,279-285` 读；`255-260` 写 |
| `references/export-sample/feat-demo/*` | read（字节比对） | `commands_misc.py:332-346` |
| 系统临时目录 `wxg-*` | both | `temp.py:21-42`；`commands_misc.py:336-348` |
| `@file` 参数指向的任意文件 | read | `jsonio.py:40-45` |
| `sys.path` / `sys.modules["wxg"]` | write（进程级） | `wxg.py:18-24`；`contract.py:12-14` |
| `sys.stdout` 编码 | write | `cli.py:49-50` |

跨命令共享的隐式状态：
- `WXG_DB_URL` 是进程级全局，`--db-url` 写进去不恢复；`Engine(db_url=...)` 也这么干（`engine.py:47-48`）。同一进程里两个后端的状态库不可能并存。
- `DEFAULT_ROOT` 在 import 时算好（`cli.py:16`），`args.root_path` 才是每条命令的真实根；handler 里用 `getattr(args, "root_path", DEFAULT_ROOT)` 双保险（`commands_misc.py:211`）。
- 状态库路径不写进任何配置文件，完全靠命令行；`.why-exist/` 只是默认约定，不是被读取的配置。

## 冗余

| 条目 | 信号 | 把握 |
|---|---|---|
| 三个 `--json`，两个无效 | 只有 `commands_misc.py:251` 读 `args.json`；gate 分支 `cli.py:97-99` 与通用分支 `cli.py:112` 本来就打印 JSON | high |
| `needs_db` 硬编码 vs 契约 `WRITE_MODES` | `cli.py:65` 手写四命令白名单；`wxg_contract.py:640` 另有一份“只读/写库”声明；verify 只查键存在（`commands_misc.py:306`），不校验一致 | high |
| 132 个 re-export，74 个零消费者 | AST：50 个 `cmd_*`（靠 getattr 动态取）+ 82 个 helper，其中只有 8 个被外部 `wxg.X` 使用，74 个无人引用；`cmd_*` 的显式使用只有 3 处 | high |
| `DEFAULT_ROOT` 三处定义 | `cli.py:16`、`commands_misc.py:20`、`wxg.py:26`；最后一处从未使用 | high |
| `import wxg_contract as C` 在 `wxg.py` 里完全没用 | `wxg.py:28`，后续无 `C.` 引用，外部也无 `wxg.C` | high |
| 成功/错误两套 JSON 风格 | 错误与 serve 摘要用 `jsonio.dumps`（排序、紧凑）；成功用 `json.dumps(indent=2)` | high |
| `positionals` 分支是死路径 | `cli.py:31-32`；50 条命令的 `positionals` 全为空 | high |
| 两个 JSON 解析入口 | `loads`（库内 JSON 列）与 `load_json_arg`（CLI 参数），各自 try + Reject | medium |
| `import wxg` 三处叠加 | `wxg.py:18-24` 注册 + `cli.py:72` + `commands_misc.py:300` + `contract.py:12-14` 再插 path | medium |
| `whyexist.__version__ = 2.23.0` 漂移 69 个版本且无人读 | `__init__.py:49`；VERSION=2.92.0；全仓只命中定义与 `CHANGELOG.md:818` | high |
| 文档行数过时 | 实际 181；`SKILL.md:448,472` 与 `HANDOFF.md:16` 写 176 | medium |
| `jsonio.__all__` 漏了 `load_id_list` | `jsonio.py:12`；定义在 62 行，被 4 个模块显式 import，`CHANGELOG.md:638` 称其为公共函数 | medium |

## 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `whyexist/cli.py` | refactor_in_place | 契约最密且大部分有精确断言；坏的是边界实现（connect 在兜底外、needs_db 手写、两套 JSON、死 `--json`） | 退出码被 CI、测试夹具、agent 提示词同时依赖；只跑全量测试不看契约表，容易把 1/2 语义对调 |
| `wxg.py` | rewrite | 行为简单，但一个文件干了三件事：入口、handler 注册表、74 个无人用的兼容导出。收缩成“入口 + 显式注册表 + 8 个实际使用的 helper”才有边界 | verify 用 `getattr(wxg,"cmd_*")` 校验 handler（`commands_misc.py:303`），分派也走同一条路；漏改会同时坏 verify 与所有命令。仓库外是否有人 import wxg 拿 helper 无法证明 |
| `whyexist/errors.py` | keep | 13 行一个类，跨层捕获由 `__main__` 注册保证，没有可改空间 | 几乎无；未来给它加字段/factory 会破坏 100+ 处 `except Reject` |
| `whyexist/jsonio.py` | keep | 6 个函数、12 个直接单测、格式被钉死；需要的是补两条断言（`utc_now` 格式、`load_json_arg("")`），不是换实现 | `dumps` 的排序/紧凑是错误 JSON 与 serve 摘要的既定格式，换实现会让快照与 diff 全变 |
| `whyexist/temp.py` | freeze | 唯一实质逻辑是“Windows 默认 mode、POSIX 0o700”，无法在 CI 验证（受限 token、空 DACL 都是外部条件）；重试/耗尽/分支差异无测试 | 冻结的代价是这条知识只活在注释与 CHANGELOG；改回 `tempfile` 或统一 0o700，会在 DSH Windows 沙箱里以 PermissionError WinError 5 炸掉所有临时目录用例 |
| `whyexist/__init__.py` | refactor_in_place | Engine 的库 API 有独立测试，公开面合理；但 `__version__` 是假信息，顶层 import 拉进整条 db/commands 链 | 删版本常量前确认发布脚本不依赖（`tools/` 里无引用）；改懒加载会改变 import 期副作用 |

## 值得人判断的问题

1. “只读命令零副作用”是公共契约，还是只为 `verify` 服务？这决定 `needs_db` 继续手写，还是从契约 `WRITE_MODES` 派生并让 verify 交叉校验。现在两份真源没有任何校验，新增只读命令会默认 connect 并在干净目录里建 `.why-exist/`。
2. 退出码 1 同时表示“业务判定失败”（gate FAIL）和“未捕获异常”（连接失败），2 表示“可预期拒绝”。这个分界是有意的吗？连接失败该算 2 还是 1？
3. “错误一律 JSON”是不是硬契约？argparse 的用法错误永远不是 JSON，下游只能靠“能不能 `json.loads`”区分两族格式。
4. 仓库外有没有消费者 `import wxg` 取 helper？没有的话 74 个无用导出可以全删；有的话需要先发兼容说明。
5. 成功输出的 `indent=2` 有人依赖吗（快照、文档粘贴、agent 解析）？若只是人读，统一到 `jsonio.dumps` 能消掉一套格式。
6. `serve` 恒返回 0：作为 CI 步骤永远是绿，常驻控制器的失败只能从 JSON 里读。可接受吗？
7. 是否允许 `from whyexist.cli import main` 这种库式调用？允许的话，`cli.py:72` 的 `import wxg` 必须挪进兜底，`DEFAULT_ROOT` 要改成调用时求值。
8. `--db-url` 改写进程环境变量不恢复，是刻意的（让 handler 与 Engine 复用同一套读取逻辑），还是应该显式传参？现在的写法意味着同进程内不能有两个后端的状态库。
