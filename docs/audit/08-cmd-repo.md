# 08 命令族：repo 域（10 条命令）

## 切片范围

| 文件 | 行数 | 职责 |
|---|---|---|
| scripts/whyexist/commands_repo.py | 737 | repo 域 10 条命令：初始化/引导、仓登记、单文件与整仓导入、候选推导与提升、回扫、抽样 |
| scripts/whyexist/derive.py | 140 | 纯函数：按目录把代码节点聚成 component 候选，用 calls/reads/writes 与 import 文件对推导 depends |

命令：`init`、`up`、`repo-add`、`repo-list`、`import-file`、`import-repo`、`derive`、`promote`、`sync`、`sample`。
说明：任务给的是 678 行，磁盘实际 737 行（差 59 行）；尾部 662-735 有 74 行兼容 re-export。

## 公开面

| 入口 | kind | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| wxg init | cli | scripts/whyexist/commands_repo.py:44 | --root（全局）；可选 --db-url/WXG_DB_URL | stdout JSON：root/db/backend/schema_version/contract_version/migrated | 建表、写 meta 版本、补旧库列与 legacy 身份；SQLite 会创建 `<root>`/graph.sqlite | 0 成功；2 连接/迁移异常。非 SQLite 分支当前抛 NameError 后仍为 2 |
| wxg up | cli | scripts/whyexist/commands_repo.py:62 | --feature（默认 demo）、--repo（默认 demo）、--path（可选）、--template minimal\|standard | stdout JSON：root/template/repo/feature/gate_result/gate/next | 自建状态库；standard 或无 --path 时在 `<root>`/../demo-repo 建 demo.py 并登记仓；声明 feature；执行只读 gate | 0（即使 gate FAIL）；2 参数/仓登记/声明错误。分阶段提交，失败会留下半成品 |
| wxg repo-add | cli | scripts/whyexist/commands_repo.py:130 | --id、--path、--language（仅 python） | stdout JSON：action/repo/path/language | repos 表按 id upsert；path 做 resolve；path 有 UNIQUE 约束 | 0 成功；2 路径不存在/语言不对。path 冲突路径当前因 _is_integrity_error 未导入而抛 NameError，仍为 2 |
| wxg repo-list | cli | scripts/whyexist/commands_repo.py:149 | 无 | stdout JSON：repos[]（id/path/language/created_at），按 id 升序 | 无；只读 | 0 成功；2 状态库未初始化 |
| wxg import-file | cli | scripts/whyexist/commands_repo.py:153 | --file 必填；--prepare 时 --feature 必填；写库时 --token/--feature（后者实际不参与写库） | prepare：mode/repo/work/nodes/edges/stale_candidates；write：mode/repo/nodes_inserted/nodes_updated/edges_inserted/stale_marked/stale_nodes/work | prepare 写 work_items(scan) 与 feature_nodes；write 写 nodes/edges/feature_nodes，并把消失节点 stale=1；需要已登记仓且语言为 python | 0 成功；2 文件不存在/不在仓内/非 python/缺 feature/缺 token/角色或 target 越界 |
| wxg import-repo | cli | scripts/whyexist/commands_repo.py:230 | --repo 必填；--prepare 时 --feature 必填；写库时 --token | prepare：mode/repo/work/files/nodes/edges/stale_candidates；write：mode/repo/files/nodes_inserted/nodes_updated/edges_inserted/stale_marked/work | 遍历仓内非点路径的 .py；与 import-file 相同的写表；语法错误会中止整批（未提交则回滚） | 0 成功；2 仓未登记/非 python/语法错误/缺 feature/缺 token/越界 |
| wxg derive | cli | scripts/whyexist/commands_repo.py:426 | --repo、--feature 必填；--depth（默认 1）、--exclude；--apply 时 --token | dry-run：mode/feature/repo/strategy/depth/exclude_dirs/excluded_nodes/components/depends，components<=1 时带 hint；apply：mode/feature/repo/components/depends/nodes_written/edges_written/stale_derived | dry-run 只读；apply 写 nodes(origin=derived)/edges(contains,depends)，把旧 derived 标 stale，components 会进 feature_nodes | 0 成功；2 仓未登记/feature 不存在/缺 token/角色不对/新 component 不在 target_ids |
| wxg promote | cli | scripts/whyexist/commands_repo.py:536 | --feature、--node 必填；--token；--actor 或 WXG_ACTOR | stdout JSON：promoted/feature/actor | 把 origin 从 derived 改为 declared，写 attrs.x_promoted_by/x_promoted_at，节点进入 --feature 的 feature_nodes | 0 成功；2 缺 token/角色不对/node 不在 target/节点不存在/非 derived/缺 actor |
| wxg sync | cli | scripts/whyexist/commands_repo.py:568 | --repo 必填；--limit（默认 50，>=0） | stdout JSON：repo/path/files/db_nodes/planned_nodes/missing_count/missing/new_count/new/changed_count/changed_unmapped_count/changed/stale_count/stale/parse_errors/truncated | 无；只读。重解析仓内全部 .py | 0 成功；2 仓未登记/limit 为负 |
| wxg sample | cli | scripts/whyexist/commands_repo.py:633 | --repo 或 --feature 二选一；--seed 可选 | stdout JSON：sample{id,kind,name,repo,path,symbol,line_start}/seed/source/candidates | 无；只读 | 0 成功；2 两个都给或都不给/feature 不存在/候选为空 |
| _module_to_rel / _resolve_relative_import / _import_file_pairs | function | scripts/whyexist/commands_repo.py:341 | 仓根 Path、模块名或源文件相对路径 | 仓内相对文件路径，或 (源文件, 目标文件) 对列表 | 只读源文件；语法错误的文件被静默跳过 | 不直接面向 CLI；异常由 derive 统一转成 2 |
| repos 表 | table | scripts/whyexist/db.py:24 | id/path/language/created_at | 仓记录 | repo-add 写，所有 repo 命令读 | 不适用 |
| nodes / edges 表 | table | scripts/whyexist/db.py:30 | 导入器与 derive 生成的节点/边 | 图 | import-file/import-repo/derive/promote 写；sync/sample/derive 读 | 不适用 |
| features / conditions / feature_nodes 表 | table | scripts/whyexist/db.py:54 | feature 元数据与作用域 | feature/条件/作用域 | up/import-*/derive/promote 写 feature_nodes；其余读 | 不适用 |
| work_items 表 | table | scripts/whyexist/db.py:74 | scan 工单 target_ids/claim_token | 工单状态 | import-file/import-repo --prepare 写/合并 scan 工单；写库路径读 token | 不适用 |
| meta 表 | table | scripts/whyexist/db.py:20 | schema_version/contract_version | 版本 | init 写 | 不适用 |
| `<root>`/graph.sqlite | file | scripts/whyexist/db.py:459 | --root 或默认 ./.why-exist | SQLite 状态库 | init/up 创建；其它命令读写 | 不适用 |
| `<root>`/../demo-repo/demo.py | file | scripts/whyexist/commands_repo.py:77 | up --template standard 或未给 --path | demo 源文件（已存在则不覆盖） | 创建目录与文件 | 不适用 |

## 契约表

| id | 承诺 | 状态 | 证据 | 备注 |
|---|---|---|---|---|
| C1 | SQLite 上 wxg init 创建全部 schema 表、写 meta.schema_version/contract_version，并返回 root/db/backend/schema_version/contract_version/migrated，退出码 0。 | partial | scripts/whyexist/commands_repo.py:44-59<br>scripts/whyexist/db.py:605-616<br>tests/test_wxg.py:651-652 | 只有 schema_version=9 与建表被直接断言；root/db/backend/migrated 的结构没有断言（探针见过 shape，但不算测试）。 |
| C2 | 已迁移库上重复 wxg init 不改写已有行，migrated 返回空对象。 | covered | tests/test_wxg.py:683-696<br>scripts/whyexist/db.py:585-602 |  |
| C3 | wxg init 对旧库补列、回填 evidence.generation 与 legacy 身份，不删除旧行。 | covered | tests/test_wxg.py:632-679<br>tests/test_wxg.py:957-1002<br>scripts/whyexist/db.py:509-602 | 覆盖了 work_items/evidence/features/bites/nodes 的迁移与 judge_history 回填。 |
| C4 | MySQL/PostgreSQL 后端上 wxg init 返回 backend=mysql/postgres，db 字段为掩码后的 URL。 | gap | scripts/whyexist/commands_repo.py:46-51<br>tests/test_mysql_backend.py:86-89<br>tests/test_pg_backend.py:89 | 实现引用未导入的 re 与 db_url，实际抛 NameError；两个集成测试默认 skip，从未在 CI 跑过。 |
| C5 | wxg up 在未初始化目录完成 init + demo 仓 + demo feature + 只读 gate，返回 next；重复执行不重置已有 feature。 | covered | tests/test_plan_cli.py:337-351<br>tests/test_plan_cli.py:353-357<br>scripts/whyexist/commands_repo.py:62-125 | 同时覆盖已有 --path 与幂等；minimal 模板见 test_plan_cli.py:518-522。 |
| C6 | wxg up 即使 gate 结果为 FAIL 也以退出码 0 结束（bootstrap 成功不等于交付通过）。 | partial | tests/test_plan_cli.py:337-351<br>scripts/whyexist/commands_repo.py:109-125<br>scripts/whyexist/cli.py:109-113 | 测试夹具的 expect=0 隐含了这条，但没有显式断言 FAIL 时退出 0；这是与 gate 相反的行为。 |
| C7 | wxg up --template standard（或未给 --path）在 `<root>`/../demo-repo 创建 demo.py（不存在时）并登记仓。 | gap | scripts/whyexist/commands_repo.py:75-87 | 无测试断言文件路径与内容；探针确认 demo.py 会创建，但位置在 --root 之外。 |
| C8 | wxg up 的 next 第一行是 import-file ... --prepare，而不是 work-claim。 | covered | tests/test_plan_cli.py:342-346<br>scripts/whyexist/commands_repo.py:117-124 |  |
| C9 | wxg up 返回的 next 命令带同一 --root，用户照抄不会落到默认 ./.why-exist。 | gap | scripts/whyexist/commands_repo.py:117-124 | next 里只有裸 wxg 命令，没有 --root；up 越是用自定义 root，后续越容易写错库。 |
| C10 | wxg repo-add 按 id upsert 仓、把 path 规范化为绝对路径、language 只接受 python；重复同 id/path 幂等。 | partial | scripts/whyexist/commands_repo.py:130-146<br>tests/test_wxg.py:85-87<br>tests/test_wxg.py:904-907 | happy path 被所有端到端测试使用；没有直接断言 action/path 规范化，也没有同 id 重复登记的幂等用例。 |
| C11 | wxg repo-add 对路径不存在、非 python、path 被其它 id 占用给可读 JSON Reject（退出码 2）。 | partial | scripts/whyexist/commands_repo.py:131-145<br>tests/test_wxg.py:904-907 | 只有非 python 分支有测试；path 冲突分支因 _is_integrity_error 未导入而抛 NameError，可读错误从未生效。 |
| C12 | wxg repo-list 按 id 升序返回全部 repos（含 created_at），只读；未初始化时退出 2 且不创建目录。 | partial | scripts/whyexist/commands_repo.py:149-150<br>scripts/whyexist/graph.py:56-57<br>tests/test_wxg.py:947-955 | 只测了未初始化分支；返回结构没有任何直接断言。 |
| C13 | wxg import-file --prepare 免 token、要求 --feature，把新节点与 stale 候选并入当前代 scan 工单，并写 feature_nodes。 | partial | scripts/whyexist/commands_repo.py:177-192<br>tests/test_wxg.py:337-340<br>tests/test_wxg.py:1566-1569 | happy path 有覆盖；--prepare 缺 --feature 的 Reject 分支无测试。 |
| C14 | wxg import-file 写库要求 claimed token、角色 import-file、全部 node/stale id 落在 target_ids 内，否则 Reject 2。 | gap | scripts/whyexist/commands_repo.py:193-195<br>scripts/whyexist/work.py:88-100 | 角色/边界测试针对 upsert-node，没有针对 import-file 的越界用例。 |
| C15 | 同一 token 重复 wxg import-file 同一文件幂等：nodes_inserted=0、nodes_updated>0，不产生重复节点。 | covered | tests/test_wxg.py:334-351<br>scripts/whyexist/commands_repo.py:196-211 |  |
| C16 | wxg import-file 重导入用 merge_attrs 保留人工写入的 duty/x_* 属性，同时刷新扫描属性。 | covered | tests/test_wxg.py:353-369<br>scripts/whyexist/graph.py:97-105 | 只断言 attrs；origin 是否保留没有断言（重导入会用 scan 覆盖 origin，见 implicit_requirements）。 |
| C17 | wxg import-file 把本次未再出现的同 repo+path 旧节点标 stale=1，重新出现时清 0，并把 stale 节点保留在 feature 作用域。 | covered | tests/test_wxg.py:1559-1583<br>scripts/whyexist/commands_repo.py:172-176<br>scripts/whyexist/commands_repo.py:212-215 |  |
| C18 | wxg import-file 写库时使用 claim 所属 feature，忽略 --feature 参数。 | gap | scripts/whyexist/commands_repo.py:193-215 | 探针：prepare 用 fa，写库传 --feature fb，节点仍只进 fa；无报错、无提示。 |
| C19 | wxg import-file 在 prepare 阶段就校验导入器生成的 kind/id，非法 id 不落 target_ids/feature_nodes。 | gap | scripts/whyexist/commands_repo.py:164-168 | 无直接测试；探针用含空格的 repo id 触发“节点 id 含非法字符”，说明校验生效，但 repo-add 没在登记时拦住非法 id。 |
| C20 | wxg import-repo 批量导入仓内非点路径的 Python 文件，准备/写入语义与 import-file 一致。 | partial | tests/test_plan_cli.py:567-584<br>scripts/whyexist/commands_repo.py:249-338 | 只覆盖 2 个根目录文件的 happy path；与 import-file 的写语义一致性没有逐项对照。 |
| C21 | import-repo 与 sync 使用同一文件集（点目录/点文件处理一致）。 | gap | scripts/whyexist/commands_repo.py:252-254<br>scripts/whyexist/commands_repo.py:580-583 | 探针：import-repo 跳过 .venv，files=1；sync 把 .venv 算进来，files=2 并报 new。 |
| C22 | import-repo 遇任一语法错误整批失败（不写半截），错误带相对路径；sync 则逐文件记 parse_errors 后继续。 | gap | scripts/whyexist/commands_repo.py:256-259<br>scripts/whyexist/commands_repo.py:584-588 | 探针确认：import-repo --prepare 直接 exit 2；sync 同一仓返回 parse_errors 且继续报 new。文档只写了 sync 的行为。 |
| C23 | import-repo 的输出与 import-file 对称，包含 stale 节点明细。 | gap | scripts/whyexist/commands_repo.py:218-227<br>scripts/whyexist/commands_repo.py:329-338 | import-repo 只有 stale_marked，没有 stale_nodes；调用方无法知道哪些节点被标记。 |
| C24 | wxg derive 默认 dry-run、只读，返回 components/depends/strategy/depth/excluded_nodes；components<=1 时带 hint。 | covered | scripts/whyexist/commands_repo.py:458-468<br>tests/test_plan_cli.py:587-600<br>tests/test_derive.py:38-137 |  |
| C25 | wxg derive --apply 需 token/角色/全部新 component id 在 targets，写 origin=derived 的 component、contains 与 depends（x_evidence），并把旧 derived 标 stale。 | partial | scripts/whyexist/commands_repo.py:470-523<br>tests/test_plan_cli.py:602-626 | 测试只断言 components 与 origin；stale_derived、depends.x_evidence、目标边界都没断言。 |
| C26 | wxg derive --apply 不覆盖人工声明的同名 component（origin 与 attrs 保留）。 | gap | scripts/whyexist/commands_repo.py:488-504 | 探针：先 upsert component:d4:pkg（origin=manual，duty=人工职责），derive 后变成 origin=derived，attrs 只剩 x_strategy/x_depth/x_path。 |
| C27 | wxg derive 的 stale 清理也只写 token 边界内的节点。 | gap | scripts/whyexist/commands_repo.py:474-485 | 探针：token targets 只含 component:d5:pkg，derive 仍把 component:d5:other 置 stale=1。 |
| C28 | wxg derive 只对未 stale、未 unmapped 的代码节点分组。 | gap | scripts/whyexist/commands_repo.py:438-442 | SQL 只过滤 unmapped=0，没有 stale=0；已删除代码的 stale 节点仍会进 component.members 与 contains 边。 |
| C29 | wxg promote 只接受 origin=derived 且 id 在 targets 的节点，需 token 与 actor。 | partial | scripts/whyexist/commands_repo.py:542-552<br>tests/test_plan_cli.py:629-647 | 只测了 origin 非 derived；token 缺失、target 越界、actor 缺失都无对应用例。 |
| C30 | wxg promote 写 origin=declared，保留原 attrs，并记录 x_promoted_by/x_promoted_at。 | covered | scripts/whyexist/commands_repo.py:554-564<br>tests/test_plan_cli.py:649-681 |  |
| C31 | wxg promote 只能把节点提升进 token 所属 feature，不能跨 feature 改作用域。 | gap | scripts/whyexist/commands_repo.py:542-561 | 探针：aa-src 的 token + --feature zz-dst 成功，节点进 zz-dst 的 feature_nodes；代码只 ensure_feature(args.feature)，从不比较 item.feature_id。 |
| C32 | wxg sync 只读，返回 files/db_nodes/planned_nodes/missing/new/changed/stale 计数与截断列表；--limit 控制列表长度；不改库。 | partial | scripts/whyexist/commands_repo.py:568-630<br>tests/test_wxg.py:1585-1603 | missing/new/read-only/limit 有覆盖；changed、stale、parse_errors 的结构没有断言。 |
| C33 | wxg sync 对语法错误逐文件记 parse_errors 并继续。 | gap | scripts/whyexist/commands_repo.py:584-588 | 探针确认行为存在；quality.md 提到但无测试。 |
| C34 | wxg sample 按 --repo 或 --feature 二选一，均匀随机取一个节点；--seed 可复现；返回 source/candidates/sample。 | partial | scripts/whyexist/commands_repo.py:633-659<br>tests/test_wxg.py:1079-1091 | source/candidates/二选一有断言；seed 的“同 seed 同结果”没有直接断言。 |
| C35 | wxg sample 对未登记 repo、不存在 feature、空作用域给出与原因相符的 Reject。 | gap | scripts/whyexist/commands_repo.py:636-656 | 探针：sample --repo nope 报“仓 nope 里还没有可抽取的节点”，而不是“仓未登记”。 |
| C36 | 除 verify/doctor/gate/apply/reconcile/serve 等特殊命令外，成功输出 JSON 到 stdout 且退出 0；Reject/异常输出 JSON 到 stderr 且退出 2。 | partial | scripts/whyexist/cli.py:85-113<br>tests/test_plan_cli.py:62-86 | argparse 的 required/choices 错误直接走 argparse，输出 usage 文本而非 JSON（test_wxg.py:904-907 断言的是 invalid choice）。 |
| C37 | 状态库缺失时，除 init/up 外的命令不创建 .why-exist/graph.sqlite，直接退出 2。 | covered | scripts/whyexist/cli.py:62-69<br>tests/test_wxg.py:947-955 |  |
| C38 | WXG_DB_URL / --db-url 选择 SQLite、MySQL/MariaDB 或 PostgreSQL 后端；SQLite 是默认。 | gap | scripts/whyexist/db.py:425-465<br>tests/test_mysql_backend.py:86-99<br>tests/test_pg_backend.py:89-102 | 两个后端测试默认 skip；init 分支又因 C4 的 NameError 必挂，实际可用性没有被任何一个默认测试证明。 |
| C39 | repo 域的图写入命令（import-file/import-repo/derive --apply/promote）都要 claim_token，并限定 target_ids（I5 写入边界）。 | partial | scripts/whyexist/commands_repo.py:193-195<br>scripts/whyexist/commands_repo.py:470-485<br>scripts/whyexist/commands_repo.py:542-545 | import-file 有边界检查；derive 的 stale 清理绕开边界（C27），promote 只查节点不查 feature（C31）。 |

## 状态与共享状态

| 目标 | 读写 | 位置 |
|---|---|---|
| graph.sqlite:meta | write | scripts/whyexist/commands_repo.py:45; scripts/whyexist/db.py:593-601 |
| graph.sqlite:repos | both | scripts/whyexist/commands_repo.py:137-141, 150, 236-239 |
| graph.sqlite:nodes | both | scripts/whyexist/commands_repo.py:172-215, 302-328, 438-442, 488-505, 546-564, 590-611, 640-653 |
| graph.sqlite:edges | both | scripts/whyexist/commands_repo.py:208-211, 313-319, 443-444, 506-523 |
| graph.sqlite:feature_nodes | both | scripts/whyexist/commands_repo.py:184, 204-207, 215, 283-287, 308-311, 325-328, 638-645 |
| graph.sqlite:work_items | both | scripts/whyexist/commands_repo.py:182, 193, 280, 298, 470, 543 |
| graph.sqlite:features | read | scripts/whyexist/commands_repo.py:90, 436, 542 |
| graph.sqlite:conditions | read | scripts/whyexist/commands_repo.py:109（经 cmd_gate） |
| filesystem:登记仓源码 | read | scripts/whyexist/commands_repo.py:163, 249-257, 387-423, 580-589 |
| file:`<root>`/../demo-repo/demo.py | write | scripts/whyexist/commands_repo.py:77-82 |
| env:WXG_DB_URL | both | scripts/whyexist/cli.py:55-56; scripts/whyexist/db.py:425-438 |
| env:WXG_ACTOR | read | scripts/whyexist/commands_repo.py:553; scripts/whyexist/workflow.py:12-20 |
| .why-exist 默认根目录 | both | scripts/whyexist/cli.py:16, 53 |

跨命令共享状态：`--root`（默认 `./.why-exist`）、`WXG_DB_URL`（CLI 会把 `--db-url` 写进环境变量，整个进程生命周期有效）、`WXG_ACTOR`（promote 缺 --actor 时读取）、`repos.path` 的 UNIQUE 约束、`work_items.claim_token`、`feature_nodes` 作用域，以及 `nodes.stale/origin`。`up` 还会在 `<root>` 之外创建 `demo-repo`，这是本切片唯一跨出状态库根目录的写操作。

## 冗余

| 条目 | 信号 | 把握 |
|---|---|---|
| commands_repo.py 尾部 662-735 的 6 组 re-export | wxg.py 已直接从 commands_feature/commands_graph/commands_gates/commands_compiler/commands_misc 导入；仓内除 _import_file_pairs 外无人从 commands_repo 取这些符号，74 行是纯兼容层残留。 | high |
| import-file 与 import-repo 的 prepare/write 循环 | 177-215 与 276-328 逐段同构（insert_work、feature_nodes 批量插入、节点 upsert、边 upsert、stale 标记）；两处已经开始漂移（stale_nodes 输出、解析错误处理）。 | high |
| import-repo 与 sync 的整仓遍历 | 249-259 与 580-589 都是 sorted(rglob('*.py')) + plan_python；文件过滤与错误处理不同，导致 C21/C22 的行为分叉。 | high |
| cmd_gate 重复导入 | scripts/whyexist/commands_repo.py:14 与 724-725 两次 import cmd_gate。 | high |
| 未使用导入 | os/sys/ensure_db/migrate_schema/check_attrs/edge_id/dumps/load_json_arg/loads/append_evidence/get_work/get_work_by_token/target_match/work_id 在文件内无引用；它们掩盖了真正缺的 re/db_url/_is_integrity_error。 | high |
| wxg.py 与 commands_repo.py 双层 facade | wxg.py 165-178 从 commands_repo 再导出，commands_repo 又从四个模块再导出；调用链 cli → wxg → commands_repo → commands_*，多一层只增加循环导入与漏导入风险。 | high |
| up 的 gate 输出重复 | 返回体同时有 gate_result 与完整 gate；gate 里已有 result，等于同一判定两份。 | medium |
| sample 命令与 scripts/gen_sample.py 同名不同物 | wxg sample 是随机抽节点；gen_sample.py 生成 references/export-sample 导出夹具。文档与索引里两个 sample 极易混。 | medium |

## 分区判定

| 模块/单元 | 判定 | 理由 | 风险 |
|---|---|---|---|
| scripts/whyexist/derive.py | keep | 纯函数、无 I/O、15 个单测覆盖分组/depends/exclude/证据；职责单一，契约清楚。 | 低；import 解析不在这个模块，跨文件依赖仍受 commands_repo 的 _import_file_pairs 限制。 |
| scripts/whyexist/commands_repo.py:init | refactor_in_place | SQLite 行为清楚且有迁移/幂等测试；只需补回 re/db_url 导入并加一条非 SQLite 测试。 | 中；init 是所有后端的入口，改错会直接让状态库不可用。 |
| scripts/whyexist/commands_repo.py:up | rewrite | 60 行编排把 connect/init/repo-add/feature-declare/gate 串在一个 handler 里，分阶段提交、失败留半成品；next 不带 --root；minimal+--path 与帮助文案矛盾；gate 结果重复。行为简单、边界清楚，值得重写为显式步骤与幂等状态机。 | 中高；只有 3 个测试，首屏体验最容易被改坏；需要先立“bootstrap 失败是否回滚/是否非零退出”的契约。 |
| scripts/whyexist/commands_repo.py:repo-add/repo-list | refactor_in_place | repo-add 的 upsert 语义清楚；修 _is_integrity_error 导入、补 id 校验与冲突测试即可。repo-list 只有 2 行，原样保留。 | 中；path 唯一约束与已有仓重新指向会改变后续 find_repo 的归属。 |
| scripts/whyexist/commands_repo.py:import-file/import-repo | refactor_in_place | 写入语义清楚且核心路径有测试，但 prepare/write 两套循环重复、点目录规则与 sync 分叉、解析错误策略不一致、输出不对称、写库忽略 --feature。适合合并成一个导入引擎，而不是推倒重来。 | 高；import 是所有工作流的入口，涉及大仓性能、stale 语义与 token 边界，改错会污染全图。 |
| scripts/whyexist/commands_repo.py:derive --apply | freeze | 写库路径没有测试覆盖同名 declared 组件、越界 stale 清理、stale 代码节点分组；这三条都会静默改写人工组织。先冻结写路径，把“derived 是否允许覆盖同名节点、stale 是否受 target_ids 约束”定成契约，再动。dry-run 与 derive.py 不受影响。 | 高；当前行为会把 declared 组件降级为 derived 并清掉 attrs，重写若保留旧语义等于把 bug 固化。 |
| scripts/whyexist/commands_repo.py:promote | refactor_in_place | derived→declared 与审计痕迹语义清楚，2 个测试覆盖主路径；需补 token.feature_id == --feature 校验、拒绝 stale 节点、补越界/缺 actor 测试。 | 中；跨 feature 提升会把节点塞进另一个 feature 的作用域，gate/coverage 都会跟着变。 |
| scripts/whyexist/commands_repo.py:sync | refactor_in_place | 只读、核心报告有测试；但文件集与 import-repo 不一致、无语言检查、parse_errors 未测试。抽一个共享的“枚举仓内 Python 文件”函数即可。 | 低；只读命令，改错只影响报告，不影响状态库。 |
| scripts/whyexist/commands_repo.py:sample | keep | 25 行只读抽样，feature/repo 二选一与 seed 语义清楚，有端到端测试。 | 低；只需改未登记 repo 的错误文案，不必动抽样逻辑。 |
| scripts/whyexist/commands_repo.py:re-exports/imports | rewrite | 662-735 的兼容 re-export 与十余个未使用导入应整体删除；wxg.py 已直接导入各 commands_* 模块，保留这层只会继续掩盖未定义名。 | 低；先全局搜 whyexist.commands_repo 的引用，仓内只有 wxg.py 与 tests 的 _import_file_pairs。 |

## 隐含需求（重写会静默丢掉的行为）

- up 的“成功”是 bootstrap 成功，不是 gate 通过；gate FAIL 仍退出 0。
- up 在 `<root>` 的父目录创建 demo-repo/demo.py，不是 `<root>`/demo-repo；demo.py 已存在时不覆盖。
- up --template minimal 一旦带 --path 仍会登记仓，与“minimal 只建 feature”的帮助文案冲突。
- up 对已存在的 feature 不重置、不更新声明，只重跑 gate；对已存在的 demo 仓会 upsert path。
- up 的 next 命令不带 --root，照抄会落到默认 ./.why-exist。
- import-file 写库时只认 claim 的 feature，--feature 是 prepare 专用参数；传错不报错。
- import-file 的 prepare 可以把新 id 合并进一张已被领取的 scan 工单，持 token 的扫描者无需重新领取就能看到扩大的边界。
- import-file/import-repo 重导入只 merge attrs；节点 origin 会被 importer 的 scan 覆盖，人工声明的 origin 不保留。
- import-repo 跳过所有点目录/点文件；sync 不跳过，会把 .venv 里的文件报成 new。
- import-repo 遇到第一个语法错误就整批失败；sync 逐文件记 parse_errors 并继续。
- import-repo 的返回没有 stale_nodes，只有数量。
- derive 的 stale 清理不受 claim target_ids 约束，会改写 token 边界外的 derived 节点。
- derive --apply 会把同 id 的人工/declared component 覆盖成 derived，并清空其 attrs。
- derive 对 stale 代码节点仍参与分组与 contains 边；只有 unmapped 被排除。
- promote 不校验 --feature 与 token.feature_id 一致，可把节点提升进另一个 feature 的作用域。
- promote 经 upsert_node 会把节点的 stale 清 0，已消失代码的候选可以被“提升”回活跃。
- repo-add 不在登记时校验 repo id 字符；非法 id 直到 import 生成节点 id 才报错。
- repo-add 的 path 冲突当前抛 NameError，而不是文档承诺的可读 Reject。
- init 在 MySQL/PostgreSQL 上因 re/db_url 未导入而抛 NameError；对应集成测试默认 skip。
- sample --repo 不检查仓是否登记；不存在的仓返回“仓里还没有节点”。
- sync 不检查 repo.language，也不检查仓路径是否还存在；路径消失时只会报 missing。
- init 在全新库上也会把 meta 的两条版本写入计入 migrated。
- import 的“增量”不是 mtime/hash：每次都全量重解析 .py，按节点 id 集合与 name/line_start/line_end/symbol 比对；stale 由同 repo+path 下本次未出现的 id 差集决定。
- wxg sample 不生成任何文件；references/export-sample 由 scripts/gen_sample.py 用 feature-declare + export 生成，两者只有名字相同，没有产物交集。

## 值得人判断的问题

- import-file 写库时 --feature 应该被禁止、被校验相等，还是作为“把节点也登记进另一个 feature”的显式操作？现在的静默忽略最危险。
- derive --apply 遇到同名 declared/manual component 应该拒绝、跳过、还是派生到独立命名空间？当前覆盖 origin 与 attrs 的行为是否有人依赖？
- stale=1 是否算 I5 说的“图内容写入”？如果是，derive 的清理必须走 target_ids；如果不是，需要把这个例外写进契约。
- promote 是否允许跨 feature 提升？如果不允许，应比较 token.feature_id 与 --feature；如果允许，需要定义节点同时属于多个 feature 的语义。
- import-repo 与 sync 是否应共享同一个文件枚举器（点目录、点文件、语言、路径存在性）？现在两套规则会让回扫报告永远包含 import 不会写的文件。
- import-repo 遇到语法错误应该整批失败还是跳过并继续？如果整批失败，是否需要 --keep-going 或 parse_errors 输出？
- up 的退出码语义：bootstrap 成功但 gate FAIL 时返回 0 是否是刻意设计？如果 CI 直接跑 up，会不会把 FAIL 当成功？
- repo-add 是否应在登记时校验 id 字符集（与 check_node_id 一致），避免非法 id 把错误推迟到 import？
- sample 的抽样域是否应排除 stale/unmapped/requirement 节点？现在 feature 作用域里这些节点都可能被抽中。
- repo-list 的输出是否算稳定契约（含 created_at、绝对路径、无分页）？有没有外部脚本依赖？

## 验证记录

- `python -m unittest tests.test_derive -v`：15 passed。
- `python -m unittest tests.test_plan_cli -v`：全绿（含 up/import-repo/derive/promote 的 6 个用例）。
- 选取 `tests.test_wxg` 的 10 个 repo 域用例：全绿（init 迁移/幂等、导入幂等/attrs/stale/非 python、repo-add 语言、sample、sync、evidence_ids）。
- `tests.test_package_units.RelativeImportTest`：4 passed。
- `tests.test_mysql_backend`：3 skipped（未设 WXG_TEST_MYSQL_URL）；这正是 C4/C38 没被发现的直接原因。
- 额外行为探针（临时文件已删）确认：repo-add 冲突 NameError、import-file 忽略 --feature、sync 把 .venv 报 new、import-repo 语法错误整批失败、derive 覆盖 manual 组件、derive stale 越界、promote 跨 feature、sample 未知 repo 文案、up FAIL 仍 0、cmd_init(mysql) NameError。
