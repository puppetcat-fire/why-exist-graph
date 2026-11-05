# 07 查询与导入/推导：对外行为契约

读的是这三块：`query.py`（111 行，任务书写 97）、`importer.py`（215 行，任务书写 196）、`derive.py`（140 行，任务书写 106）。
行为证据以 `文件:行号` 标注；标 `docs/audit/_probe_07.py` 的条目可用 `python docs/audit/_probe_07.py` 复跑（脚本在系统临时目录建库，自动清理，不碰项目状态库）。

任务书里的行数比实际少 14~24 行，说明审计简报本身也在漂移——先记一笔，后面所有判定以实际代码为准。

---

## 0. 先核验任务书里的两条「已知缺口」

### 缺口 A「imports/inherits 边不进图」——属实，而且比表述更彻底

不只是「不进图」，是图里**没有这种边 kind**：

- `EDGE_KINDS` 20 种里没有 `imports`、`inherits`，也没有 `generalizes` 之外任何继承语义（`scripts/wxg_contract.py:90-111`），所以就算手工 `upsert-edge` 也会被 `graph.py:146-147` 拒掉。
- `plan_python` 完全不看 `ast.Import` / `ast.ImportFrom` / `ClassDef.bases`（`scripts/whyexist/importer.py:53-211` 全函数没有任何相关分支）。
- 探针实测一个同时含 `import os`、`from .helpers import thing`、`class Keeper(Base)` 的文件：节点 kind 只有 `classifier/operation/property`，边 kind 只有 `calls/contains/writes`，import 与继承零产物。
- import 信息唯一的出口是 derive：`_import_file_pairs` 在命令层把仓里所有 import 解析成「文件对」（`scripts/whyexist/commands_repo.py:380-423`），derive 再把它折成 `depends` 的 `attrs.x_evidence`（`commands_repo.py:511-522`）。inherits 连这个出口都没有。

### 缺口 B「derive 只有分组，没有从代码推导组件间依赖」——前半句不成立，后半句成立

- `derive_components` 同时返回 `components` 与 `depends`（`derive.py:70-140`）；depends 有两类来源：跨组 `calls/reads/writes` 边与文件级 import 对（`derive.py:100-119`）。测试直接断言了这两类（`tests/test_derive.py:48-106`）。
- 真正的限制是：depends 只为 **derive 自己按目录产出的** 组件计算。手工 `upsert-node` 出来的 component 拿不到任何代码推导的依赖；也没有 `--only-depends` 这类独立命令。
- 附带一条硬约束：`--apply` 要求工单 `target_ids` 覆盖**本轮所有** component id（`commands_repo.py:472-473` → `work.py:88-100`），所以流程必须先 `work-open --target-ids '["component:<repo>:*"]'` 再领单（`tools/verify_reports.py:69-76` 就是这么写的）。

结论：写「imports/inherits 不进图」可以；写「derive 只做分组」不可以。另外，derive 的**写路径**（`--apply`）有问题清单比「只做分组」严重得多，见下方 C34/C36/C37/C38。

---

## 1. 切片范围

| 文件 | 职责 | 对外形态 |
|---|---|---|
| `scripts/whyexist/query.py` | target_ids 通配展开、切片组装、slice/get/find 三个只读命令 | 3 个 CLI + 2 个被 work-claim 复用的函数 |
| `scripts/whyexist/importer.py` | Python AST → 节点/边；认不出的调用建 unmapped 节点 | 1 个 CLI 消费链（import-file/import-repo/sync）+ 2 个导出函数 |
| `scripts/whyexist/derive.py` | 按目录聚 component + 推导组间 depends | 1 个 CLI（derive）+ 3 个导出函数 |

宿主代码（行为发生在切片外的命令层，判定时单独列出）：`commands_repo.py::cmd_import_file`（153-227）、`::cmd_import_repo`（230-338）、`::cmd_derive`（426-533）、`::_import_file_pairs`（380-423）。

---

## 2. 公开面

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `wxg slice` | CLI | `query.py:55-75` | `--work` 或 `--ids`（逗号/JSON/@文件，支持后缀 `前缀*`）、`--limit` | `{nodes,edges,missing_ids,patterns,depth:1}`，给 limit 时加 `nodes_total/edges_total/truncated` | 只读 nodes/edges（work 模式读 work_items） | 0；2（两参数都缺、工单不存在、limit<0） |
| `wxg get` | CLI | `query.py:78-83` | `--id` | `{"node":{...attrs}}`（`attrs_json` 被解析并移除） | 只读 nodes | 0；2（节点不存在） |
| `wxg find` | CLI | `query.py:86-109` | `--kind`、`--path-prefix`、`--from-id`、`--limit` | `{nodes,total,truncated}`，按 id 升序，attrs 已解析 | 只读 nodes/edges | 0；2（limit<0、kind 非法） |
| `wxg derive` | CLI | `commands_repo.py:426-533` | `--repo`、`--feature`、`--depth`、`--exclude`、`--apply`+`--token` | dry-run：`{mode:"dry-run",strategy,depth,exclude_dirs,excluded_nodes,components,depends[,hint]}`；apply：`{mode:"apply",...计数}` | apply 写 nodes（`origin=derived`）、edges（contains/depends+x_evidence）、feature_nodes，并把旧 derived 组件标 stale；同 id 的人工节点会被覆盖成 derived 且 attrs 整体替换；成员 contains 边与 stale 清理不受 target_ids 约束 | 0（含 0 组件的 apply）；2（仓/feature/token/角色/target 不满足） |
| `wxg import-file` | CLI | `commands_repo.py:153-227` | `--file`、`--feature`（prepare 必填）、`--prepare` 或 `--token` | prepare：`{mode:"prepare",work,nodes,edges,stale_candidates}`；write：`{nodes_inserted,nodes_updated,edges_inserted,stale_marked,stale_nodes}` | prepare 建/并入 scan 工单 + feature_nodes；write 写 nodes/edges/feature_nodes 并标 stale | 0；2 |
| `wxg import-repo` | CLI | `commands_repo.py:230-338` | `--repo`、`--feature`、`--prepare`/`--token` | 同上多一个 `files` | 递归扫 `*.py`（跳过点目录），写库同 import-file | 0；2（任一文件语法错误即整批失败） |
| `wxg repo-add --language` | CLI | `commands_repo.py:130-146` | `--id`、`--path`、`--language`（choices 只有 python） | `{action:"upsert",repo,path,language}` | 写 repos；language 落库并作为导入前置校验 | 0；2 |
| `wxg sync` | CLI | `commands_repo.py:568-630` | `--repo`、`--limit` | missing/new/changed/stale/parse_errors 报告，`changed` 项带 `unmapped` 标记 | 只读（`test_wxg.py:1600` 有 db hash 断言） | 0；2 |
| `plan_python` | 函数 | `importer.py:22-213` | `repo` dict + 文件绝对路径 | `(nodes, edges)` 两个 id→payload 字典 | 只读源码文件 | 无（SyntaxError→Reject；非 UTF-8→UnicodeDecodeError；仓外→ValueError） |
| `_node_id` | 函数 | `importer.py:18-19` | kind/repo/rel/symbol | `kind:repo:rel:symbol` | 无 | — |
| `resolve_targets` / `slice_payload` | 函数 | `query.py:13-52` | conn + target_ids | `(resolved, missing, patterns)` / 切片字典 | 只读 | — |
| `derive_components` / `group_key` / `component_id` | 函数 | `derive.py:26-140` | 节点、边、repo、depth、file_dependencies、exclude_dirs | `{repo,strategy,depth,exclude_dirs,excluded_nodes,components,depends}` | 无（纯函数） | — |
| 表 `nodes` / `edges` / `repos` / `work_items` / `feature_nodes` | 表 | `db.py:24-53,74-117` | — | 行结构见 `db.py:30-53` | 本切片写 nodes/edges/repos/feature_nodes，读 work_items | — |
| 源码仓 `.py` | 文件 | `importer.py:24-25`、`commands_repo.py:249,387-394` | UTF-8/utf-8-sig 源文件 | 内存节点/边/文件对 | 只读 | — |

---

## 3. 契约表

状态口径：`covered`＝承诺的每个分支都有测试直接断言；`partial`＝有测试但只覆盖部分分支；`gap`＝代码里存在但无测试断言（有文档的会在 note 里注明）。共 38 条：covered 4 / partial 19 / gap 15。这把口径偏严：只有 C21、C22、C29、C30 的承诺被完整断言，其余「有测试」的都至少缺一个分支。

| ID | 可观察行为承诺 | 证据 | 状态 |
|---|---|---|---|
| C1 | `前缀*` 展开为排序后的现存 id；未知精确 id 进 missing；模式原样回显 | `query.py:13-34`、`tests/test_wxg.py:431-442` | partial |
| C2 | 通配未命中任何节点时静默成功（nodes=[], missing=[], patterns 保留） | `query.py:21-27`、`_probe_07.py（通配未命中的 slice）` | gap |
| C3 | slice 的边＝命中节点的关联边（去重），另一端可不在 nodes 里；depth 恒 1 | `query.py:37-52`、`_probe_07.py（slice 边的另一端…）` | partial |
| C4 | `depth:1` 是常量，全仓无消费方 | `query.py:51`、`commands_feature.py:552-560` | gap |
| C5 | `--limit N` 对 nodes/edges 各自截断，输出两个 total 与 truncated | `query.py:66-74`、`tests/test_wxg.py:1277-1289` | partial |
| C6 | `--work`/`--ids` 二选一；同时给时 `--work` 生效；limit<0 → Reject | `query.py:56-74` | gap |
| C7 | get 解析 attrs 并移除 attrs_json；不存在 → Reject | `query.py:78-83`、`tests/test_wxg.py:367-369` | partial |
| C8 | find 三条件 AND、按 id 排序、attrs 已解析 | `query.py:86-102`、`tests/test_wxg.py:346-347` | partial |
| C9 | find 返回截断前 total；limit=0 返回空且 truncated=True；负值 Reject | `query.py:103-109`、`tests/test_wxg.py:1281-1284`、`_probe_07.py（find --limit 0）` | partial |
| C10 | `--path-prefix` 是未转义 LIKE：`%`/`_` 按通配生效 | `query.py:92-94`、`_probe_07.py（% 命中 6/7）` | gap |
| C11 | 三个只读命令不过滤 stale | `query.py:39-42,87-99`、`_probe_07.py（find 含 stale）` | gap |
| C12 | 节点形状不一致：slice 给 attrs_json，get/find 给 attrs | `query.py:39,82,101`、`_probe_07.py（两种字段）` | gap |
| C13 | slice/get/find 只读、不留写入 | `query.py:1-4`、`CONTRIBUTING.md:43`、`README.md:152` | gap |
| C14 | 顶层 class→classifier，函数/方法→operation，类体赋值与 `self.x=`→property；contains/writes 边 | `importer.py:53-113,180-208`、`tests/test_wxg.py:334-351` | partial |
| C15 | calls 三档：self.method 解析、裸名解析同文件函数、其余 unmapped 节点+边 | `importer.py:143-172`、`tests/test_plan_cli.py:537-564` | partial |
| C16 | unmapped 节点按名字聚合、id 不含行号；复杂表达式用 清洗串+sha1[:8] | `importer.py:116-136,169-172`、`tests/test_plan_cli.py:537-564` | partial |
| C17 | 不产 reads/imports/inherits；不处理 import、基类、嵌套 def、模块级赋值、参数 | `importer.py:53-211`、`wxg_contract.py:90-111`、`_probe_07.py（边 kind 集合）` | gap |
| C18 | id 含仓内相对路径；移动/改名＝新 id，行号不进 id | `importer.py:18-19,24`、`SKILL.md:443` | partial |
| C19 | 语法错→Reject；非 UTF-8→UnicodeDecodeError；仓外→ValueError | `importer.py:24-29`、`_probe_07.py（异常路径）` | gap |
| C20 | 同文件重复类名 → KeyError（`{"error":"KeyError: 'one'"}`，exit 2） | `importer.py:67,83,185`、`_probe_07.py（重复类名）` | gap |
| C21 | `--language` 只能是 python；落库并在导入前再校验 | `wxg_contract.py:320`、`commands_repo.py:134-135,157-162,240-243`、`tests/test_wxg.py:904-923` | covered |
| C22 | 重导入幂等、merge_attrs 保留设计 attrs、消失即 stale、复现即清 stale | `commands_repo.py:176-227`、`tests/test_wxg.py:334-369,1559-1583` | covered |
| C23 | `--prepare` 必须带 `--feature`；只建工单+feature_nodes，不写节点 | `commands_repo.py:177-192`、`tests/test_plan_cli.py:544-548` | partial |
| C24 | import-repo 递归扫 `*.py`（跳点目录），首个语法错整批失败 | `commands_repo.py:249-272,276-338`、`tests/test_plan_cli.py:567-584` | partial |
| C25 | 不校验扩展名：仓内任意合法 UTF-8 Python 文件都会被导入 | `commands_repo.py:153-163`、`_probe_07.py（非 .py 导入成功）` | gap |
| C26 | plan_python 纯函数，不碰库、不建文件 | `importer.py:22-31,213`、`tests/test_wxg.py:1600` | partial |
| C27 | group_key 只取目录；depth>0 取前 N 层；根文件 `.`；depth<=0 取全部层 | `derive.py:26-41`、`tests/test_derive.py:15-26`、`_probe_07.py（depth=0/-1）` | partial |
| C28 | `component:<repo>:<key>`；components/members/depends/evidence 排序去重 | `derive.py:44-46,121-140`、`tests/test_derive.py:38-41,90-101` | partial |
| C29 | 只有 classifier/operation/property 分组；exclude 前缀排除并计数、过滤文件依赖 | `derive.py:20,49-58,83-98`、`tests/test_derive.py:43-46,108-134` | covered |
| C30 | depends 来自跨组 calls/reads/writes + import 对；同组不算；未分组端点丢弃 | `derive.py:23,100-119`、`tests/test_derive.py:48-106` | covered |
| C31 | derive 默认 dry-run 只读；≤1 组件给 hint | `commands_repo.py:445-468`、`wxg_contract.py:647`、`tests/test_plan_cli.py:587-600` | partial |
| C32 | apply 需 token+角色+target 覆盖全部组件 id；写 derived 组件+contains+depends(x_evidence) | `commands_repo.py:470-533`、`tests/test_plan_cli.py:602-626`、`tests/test_package_units.py:619-634` | partial |
| C33 | 重跑把未出现的 derived 组件标 stale（declared 不动）；只标节点、不清旧边 | `commands_repo.py:474-485`、`CHANGELOG.md:1105-1111`、`_probe_07.py（旧边指向 stale）` | partial |
| C34 | 0 组件的 `--apply` 仍 exit 0，却把旧 derived 组件全标 stale | `commands_repo.py:472-485`、`work.py:88-100`、`_probe_07.py（0 组件 apply）` | gap |
| C35 | derive 每次重解析全仓 import（绝对+相对，跳点目录，语法错静默跳过，errors=replace） | `commands_repo.py:380-423,448`、`tests/test_package_units.py:690-739` | partial |
| C36 | `--apply` 覆盖同 id 人工节点：origin→derived、name→组件键名、attrs 整体替换（duty 丢失），不跳过不警告 | `commands_repo.py:488-505`、`graph.py:97-105`、`_probe_07.py（同名人工组件被 apply 后）` | gap |
| C37 | `--apply` 的 target 校验只覆盖 component id；成员 contains 边、depends 边、stale 清理都不受 target_ids 约束 | `commands_repo.py:472-485,506-523`、`SKILL.md:463`、`_probe_07.py（成员 id 不在 target）` | gap |
| C38 | derive 取数只过滤 unmapped、不过滤 stale：stale 代码节点仍进组件并拿到 contains 边 | `commands_repo.py:438-441`、`_probe_07.py（stale 节点仍进组件）` | gap |

### 契约空洞里最该先补的 5 条

1. **C36** `--apply` 静默覆盖同名人工组件：origin 降级、attrs 丢 duty，等于把 promote 建立的「derived→declared 唯一入口」反向打穿。
2. **C37** 写入边界名存实亡：target 只覆盖 component id，成员边与 stale 清理都在界外写；`SKILL.md:463` 的「target_ids 就是写入边界」对 derive 不成立。
3. **C34** 0 组件 apply：命令成功但让旧候选全部失效，工单校验也拦不住（`require_targets` 对空列表恒通过）。
4. **C33/C38** 重跑只 stale 节点不清边、stale 节点仍参与分组：旧 `depends`/`contains` 留在库里指向失效组件。
5. **C13 + B 组（C10/C11/C12）** 查询的只读承诺无测试，且三个隐式语义（LIKE 通配、stale 不过滤、形状不一致）调用方会踩、测试看不见。

---

## 4. 状态读写

| 目标 | 模式 | 位置 |
|---|---|---|
| `graph.sqlite:nodes` | 读写 | 读 `query.py:15,39,79,87-99`；写 `commands_repo.py:197-215,301-311,488-505` |
| `graph.sqlite:edges` | 读写 | 读 `query.py:42,96`；写 `commands_repo.py:208-211,313-319,506-523` |
| `graph.sqlite:repos` | 读写 | 读 `commands_repo.py:236,432`、`graph.py:60-72`；写 `commands_repo.py:137-141` |
| `graph.sqlite:work_items` | 读 | `query.py:57`（slice --work）、`commands_repo.py:193-195` |
| `graph.sqlite:feature_nodes` | 写 | `commands_repo.py:184,204-207,215,283-287,308-311,325-328`；derive 经 `upsert_node` 的 feature_id（`graph.py:130-132`） |
| 源码 `*.py` | 读 | `importer.py:24-25`（严格 UTF-8）、`commands_repo.py:249,387-394`（errors=replace） |
| `<root>/graph.sqlite`（+wal/shm） | 写 | `cli.py:53,66-70`（connect）、`cli.py:83-84`（每个 needs_db 命令都 commit） |
| `WXG_DB_URL` | 读写 | 写 `cli.py:55-56`；读 `db.py:425-426` |
| 默认工作区 `./.why-exist` | 读 | `cli.py:16,53`（`DEFAULT_ROOT` 在 import 时按 cwd 求值） |
| stdout/stderr | 写 | 结果 `cli.py:109-113`；错误 `cli.py:60-61,68-69,85-90` |

跨命令共享状态只有两样：状态库文件本身，和进程级 `WXG_DB_URL`。切片内没有模块级可变缓存；`importer`/`derive`/`query` 之间不共享内存状态。

---

## 5. 冗余

| 冗余项 | 信号 | 把握 |
|---|---|---|
| 「依赖边 kind」四份定义且不一致 | `derive.py:23`（calls/reads/writes）、`briefing.py:28`（+depends）、`gates.py:124`、`planner.py:35` | 高 |
| 导入写库循环写两遍 | `commands_repo.py:196-227` 与 `301-338` 几乎逐行相同 | 高 |
| 同一个仓两套 AST 解析、两套错误策略 | `importer.plan_python`（严格 UTF-8 / Reject）vs `_import_file_pairs`（replace / 静默跳过） | 高 |
| query re-export 兼容层无人用 | `commands_misc.py:197-204`；CLI 从 `wxg` 取 handler，`wxg.py:75-81` 直接导 query | 高 |
| `_node_id`/`plan_python` re-export 死代码 | `wxg.py:73`；全仓无 `wxg.plan_python` / `wxg._node_id` 引用 | 高 |
| 「代码节点 kind」集合四处口径 | `derive.py:20`、`commands_compiler.py:64`、`gates.py:160-168`、`planner.py:38` | 中 |
| `--limit` 截断逻辑两份、语义略异 | `query.py:66-74`（or 语义）vs `103-109`（单列表） | 中 |
| `depth:1` 废弃字段 | `query.py:51`；无消费方，文档却称「深度 1 切片」（`SKILL.md:187`、`design.md:733`） | 高 |
| 节点 id 生成/校验/组件 id 三处拼字符串 | `importer.py:18-19`、`graph.py:44-51`、`derive.py:44-46` | 中 |
| 相对路径计算重复 | `importer.py:24`、`commands_repo.py:341-377`、`derive.py:35-41` | 低 |

---

## 6. 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `derive.py` | **keep** | 纯函数、140 行、15 个直接测试覆盖分组/排除/边来源/证据/空仓；输出结构与文档一致，无 I/O、无全局态 | 输入依赖外部 `(src,dst)` 元组与路径约定；`depth<=0` 语义未文档化（现为「全部目录」）。改键名或排序会连带 conformance 的 x_evidence 与 verify_reports 断言 |
| `query.py` | **refactor_in_place** | 三命令边界小，但 5 个独立缺陷：LIKE 未转义、节点形状不一致、depth 常量、两套截断、通配未命中静默 | 统一形状会改 `work-claim` 的 slice 字段；转义 LIKE 会改 `%` 现有行为。先补 C2/C5/C6/C9/C11/C12 测试 |
| `query.py#slice_payload` 输出形状 | **freeze** | 被 `work-claim` 原样嵌入返回值（`commands_feature.py:552-560`），是 agent 运行时契约 | 冻结后 C12 只能靠新增字段解决，不能直接替换；要给消费方迁移窗口 |
| `importer.py` | **refactor_in_place** | 不是屎山：单函数、纯内存、无全局态、payload 字段稳定、unmapped 规则有注释与测试、id 去行号有历史教训（`CHANGELOG.md:1137`）。缺的是护栏：重复类名 KeyError、非 UTF-8 崩溃、无 reads/imports/inherits/嵌套函数、不校验扩展名 | 任何解析增强都会改节点集合 → 改 stale/missing 漂移与 plan 计数；id 规则不能动 |
| `importer.py#_node_id` 与 unmapped 聚合 id | **freeze** | 节点 id 是跨表主键（target_ids/feature_nodes/bites/evidence_ids），没有映射表 | 连「行号不进 id」也不能回退；真改要迁移脚本+一次性 retract 策略 |
| `commands_repo.py::cmd_derive`（仅 `--apply` 写路径） | **freeze** | 算法在 derive.py（keep），问题全在写路径且都是静默改写：0 组件 apply 成功并 stale 旧组件（C34）、重跑只 stale 节点不清边（C33）、同 id 人工组件被覆盖且 duty 丢失（C36）、成员边与 stale 清理绕过 target_ids（C37）、stale 代码节点仍参与分组（C38）。五条要么无测试、要么与文档冲突，先定契约再动 | 冻结期间「重跑 derive 会改写人工组织」继续存在。修复前必须定三件事：derived 能否覆盖同名 declared、stale 清理是否受 target 约束、成员边算不算越界写入。方向错会永久丢设计标注，或让 `tools/verify_reports.py` 的自动化流程失败 |
| `commands_repo.py::_import_file_pairs` | **refactor_in_place** | 44 行纯函数、4 个导入解析测试；问题是长在命令层、与 importer 分裂 | 相对导入规则是 derive depends 的主来源，一动全变；宽容策略改严格会让部分仓 derive 直接失败 |

没有 `rewrite` 判定，有 3 个 `freeze`（slice 输出形状、节点 id 规则、derive 写路径）。理由：这三块的行为都足够简单，但**契约细节密度高**（id 规则、通配语义、形状差异、覆盖语义都是隐式的），重写等于重新发明这些细节；比重写更划算的是先把 gap 补成测试，再原地改。唯一接近 rewrite 的是「把 import 解析并进 importer」，但那是移动 + 复用，不是重写解析规则。

---

## 7. 隐含需求（重写会静默丢掉的行为）

1. **节点 id 是跨表主键**：`work_items.target_ids`、`feature_nodes`、`bites.node_id`、`evidence_ids` 全存字面量。改 `_node_id` 拼法或 unmapped 聚合粒度＝全库重建。
2. **unmapped 聚合粒度是计数口径**：plan 的 `excluded_unmapped`、conformance 的 `resolved_heuristically`、sync 的 `changed_unmapped_count` 都吃这个粒度。
3. **`attrs.x_lang="python"` 与 `origin="scan"` 是隐式判别字段**：导出用 x_lang，promote 用 `origin=derived`，conformance 用 origin 区分「derived 组件覆盖」与「真孤立」。
4. **`merge_attrs=True` 是设计标注唯一保护**：重导入不能覆盖 `duty`/`x_note`（`test_wxg.py:353-369`）。改整行 upsert 会静默清空设计正文。
5. **stale 的置位/清位协议**：扫描与 derive 置 1，任何 upsert 清 0；查询不过滤、plan 过滤、gate 直接 FAIL。
6. **derive 的 depends 依赖 `x_evidence` 形状**：conformance 把带 `x_evidence` 的 depends 视为「有代码支撑」（`test_package_units.py:619-634`）。改 evidence 结构会让所有派生依赖突然「缺支撑」。
7. **`--apply` 的 target 预覆盖把 derive 和 work-open 绑死**：`tools/verify_reports.py:69-76`、`SKILL.md:374` 都按这个顺序走。
8. **组件 id 随 `--depth/--exclude` 漂移**：精确 target 会失效，只能靠 `component:<repo>:*` 兜。这条「id 随参数变」的规则没被文档承认为契约。
9. **`--apply` 不区分同 id 的人工节点**：origin 降级成 derived、name 改成组件键名、attrs 整体替换（探针里 duty 丢失）。promote 的「唯一转换入口」只在正方向成立。
10. **`--apply` 的写入边界只覆盖 component id**：成员 contains 边写向 target 外的节点、stale 清理按 id 前缀扫全仓；`SKILL.md:463` 的「target_ids 就是写入边界」对 derive 不成立。
11. **derive 取数不过滤 stale**（只过滤 unmapped）：stale 代码节点仍进组件并拿到 contains 边，与 plan 的排除口径不一致。
12. **slice 的节点/边是原始 DB 行**（attrs_json 字符串），work-claim 原样继承。
13. **`--limit` 是「两个列表各自截断」**，truncated 是「任一被截断」；slice 的 total 字段只在给 limit 时出现，find 的 total 总在。
14. **`--path-prefix` 是未转义 LIKE**：`%`/`_` 生效。
15. **id 通配只支持后缀 `*`**：`*:foo`、`a*b` 会被当精确 id 报 missing；拼错的通配产生的空切片与「作用域为空」不可区分。
16. **两套源码读取策略**：importer 严格 utf-8-sig，derive 的 import 扫描 `errors="replace"` 并跳过语法错——同一仓在两处可用性不同。
17. **import-file 不校验扩展名**，只校验「在登记仓内 + language=python」。
18. **derive 读工作树当前代码，不是库快照**：库里的节点与 depends 可能来自不同时刻，重跑会用新代码覆盖旧证据，无版本号校验。
19. **`repo-add --language` 是只有一个取值的开关**；`design.md:64-66` 说扩展要在 `wxg.py` 加导入器，但 `wxg.py` 已是薄入口，文档位置过时。

---

## 8. 值得人判断的问题

1. `reads` 边是「没实现」还是「已放弃」？`design.md:717`、`SKILL.md:444`、`README.md:172` 三处都说导入器产 reads，`gates.py:124` 也把它算进依赖支撑，但代码从来不产。补实现还是删文档/删检查？两条都改变现有报告语义。
2. importer 的「同名裸名调用」解析要不要保留？它把跨文件同名函数误连到本文件函数（探针：`helper()` 连到本文件 `helper`）。保留会造假 calls 边，删掉会让更多调用变 unmapped。
3. 组件 id 绑定目录深度，换 `--depth` 就换一套 id。要不要引入「稳定组件 id + 路径别名」？收益是重跑 derive 不用重新 work-open，代价是一张别名表。
4. 要不要一个 depends-only 命令（或 `derive --components-from graph`）给手工组件推依赖？`derive_components` 的计算部分已具备，缺的是「组件归属」输入与 target 校验。
5. derived 能不能覆盖同名 declared 组件？现在能，而且静默覆盖（origin 降级、attrs 清空）。禁止覆盖会让 derive 在「目录键撞上人工命名」时报冲突；允许覆盖就得给人工组件换 id 规则。
6. derive 的成员 contains 边该不该受 target_ids 约束？现在不受。收紧要先把整仓节点写进工单（大仓代价高），放松则「写入边界」对 derive 失效。
7. stale 代码节点该不该参与 derive 分组？现在参与（只过滤 unmapped）。排除会改变现有 depends 图，不排除则 derived 组件里含已不存在的成员。
8. 重跑 derive 时旧 `depends`/`contains` 边该删、该标 stale、还是保留？删丢审计轨迹，保留让 edges 表膨胀且直接查边的消费者看到失效依赖。
9. `find --path-prefix` 要不要转义 LIKE 并新增通配参数？转义改变现有 `%` 行为，不转义则「前缀」这个名字是错的。
10. 三个查询命令的节点形状要不要统一成 attrs？一致性收益明显，但 slice 输出被 agent 侧按 attrs_json 消费——兼容性取舍，不是纯技术债。
11. importer 要不要按 PEP 263 支持非 UTF-8？现在一个 GBK 文件让整仓 import-repo 中止，而 derive 的扫描能跳过它。
12. `repo-add --language` 留作未来扩展点，还是降级成隐含 python 并删参数？文档说扩展在 `wxg.py`，代码已不在那里。

---

## 9. 复跑方式

```powershell
$env:PYTHONIOENCODING='utf-8'
python docs/audit/_probe_07.py                                   # 38 条契约里 16 条的 gap/partial 证据
python -m unittest tests.test_derive -v                          # 15 passed
python -m unittest tests.test_package_units.RelativeImportTest -v # 4 passed
python -m unittest tests.test_wxg.WxgTestCase.test_python_import_and_idempotent_reimport `
  tests.test_wxg.WxgTestCase.test_reimport_preserves_design_attrs `
  tests.test_wxg.WxgTestCase.test_slice_expands_wildcard_targets `
  tests.test_wxg.WxgTestCase.test_find_and_slice_support_limit `
  tests.test_wxg.WxgTestCase.test_chain_calls_get_unmapped_nodes `
  tests.test_wxg.WxgTestCase.test_repo_add_language_only_python `
  tests.test_wxg.WxgTestCase.test_import_non_python_repo_message -v   # 7 passed
python -m unittest tests.test_plan_cli.PlanCase.test_derive_dry_run_reports_components `
  tests.test_plan_cli.PlanCase.test_derive_apply_writes_derived_components `
  tests.test_plan_cli.PlanCase.test_unmapped_calls_are_aggregated_by_name `
  tests.test_plan_cli.PlanCase.test_import_repo_scans_all_python_files `
  tests.test_plan_cli.PlanCase.test_promote_rejects_non_derived_node `
  tests.test_plan_cli.PlanCase.test_promote_marks_derived_component_declared -v  # 6 passed
```
