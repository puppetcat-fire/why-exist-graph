# 设计说明：why-exist-graph（DSH 原生）

本文件说明这套实现的设计取舍，以及它如何修掉 Cursor 版 why-exist + program-graph 的
设计不一致。可执行证据在 `tests/test_wxg.py` 与 `wxg verify`。

> **怎么读**：这份文件是按版本追加的**演进记录**——每节解释"那一版为什么这么改"，其中
> 的实现细节可能已被后续版本覆盖（例如 §14 提到 `whyexist/legacy.py`，它在 2.24.0 已删）。
> **当前行为**以 `SKILL.md`、`references/contract.md` 与 `CHANGELOG.md` 顶部为准；
> 这份文件负责"为什么"，不负责"现在是什么"。

## 1. 目标

把“一个功能/一块代码是否成立、是否交付”变成**可判定**的状态，同时保证：

- 设计事实只有一处权威（图库），文档只是视图；
- 状态变更只发生在明确命令里，判定命令不产生副作用；
- 文档、样例、契约由同一实现生成，**结构上不允许漂移**；
- 技能本身与具体工作区解耦，换仓、换项目不需要改技能。

## 2. 与 Cursor 版逐条对照

| Cursor 版的问题 | 本实现的修法 | 证据 |
|---|---|---|
| `gate` / `bite` 在 why-exist 里调用，但 program-graph 的命令表与 `commands/` 没有它们；`bite_apply` 未注册 CLI，判决集校验是死代码 | `bite`、`gate`、`contract`、`verify` 都是一等命令，全部由 `COMMANDS` 注册；判决集在契约里定义，CLI 与文档同时生成 | `scripts/wxg_contract.py`、`wxg verify`、`test_bite_verdicts_are_validated_and_visible_to_gate` |
| 重新声明后 conditions 被置假，但旧 generation 的 passed 工单不重置、工单 id 不带 generation，feature 永久卡死 | 条件与工单 id 都带 generation；重新声明把旧代工单全部标 `superseded`，新代自动 seed 并可领取 | `test_redeclare_starts_new_generation_without_deadlock` |
| `gate` 会写 `Ready=0`；验证命令改状态 | `gate` 只读、不写任何表；正常流程中只有 `work-judge` 能改条件（Accepted 由声明/登记新建时置真） | `test_gate_is_read_only`、`test_scan_failed_judge_keeps_conditions` |
| `gate` 作用域只看 feature tag 的节点，扫描节点上的必要性结论进不了门禁 | 作用域 = `feature_nodes` ∪ requirement 前缀 ∪ **当前代工单 target_ids**（支持 `前缀*`）；`bite` 可显式登记进 feature | `scope_ids()`、`test_bite_verdicts_are_validated_and_visible_to_gate` |
| `docs-format.md` 规定 01 四列，`pg.py` 实际输出两列 + 分节；`attrs` 语义无契约 | 契约定义导出列与属性键；文档与样例由实现生成，`verify` 逐字节比较 | `wxg verify`、`test_contract_verify_detects_drift`、`references/contract.md` |
| 技能里硬编码四个仓（旧版原则是“仓名不进技能”），仓表还存两份 | 技能零仓名、零绝对路径；仓在运行期 `repo-add`，状态库用 `--root` | `test_python_import_and_idempotent_reimport`（临时仓 + 任意 repo id） |
| 触发词保留“随机挑代码”，但删掉了抽样算法，随机撕咬没有入口 | `sample --repo` 在已导入节点里均匀随机；`seed` 可复现 | `commands.sample`（契约） |
| 旧版“给不熟代码的人讲清楚 + 反驳必要性”的叙事能力丢失 | 明确列为非目标：本实现优先可判定与一致性，导出是投影，不假装是叙述型设计文档 | 本文件 §5 |
| 状态字段 `observed_generation` 只写不用 | 不引入该字段；generation 只存在于 feature/conditions/work_items/evidence（evidence.generation 是 0.4.0 新增） | `schema` 在 `wxg.py` |

## 3. 保留的 Cursor 版设计

- 图库为唯一权威；旧文档只读（本实现没有旧文档，天然满足）。
- 8 个条件、每条件一张工单、工单按条件顺序 `depends_on`。
- `claim_token` + `target_ids` 写入边界；审计独立、只读 + 裁决。
- 判决集 `KEEP / UNNECESSARY / HOLLOW / DOC-ONLY / UNMAPPED / UNKNOWN`。
- 认不出就 `unmapped=1`；导出缺 id 留空；没跑过的测试不得置 `BehaviorPassed`（0.4.0 起由 judge 与 gate 双重强制：必须已有**同 generation**、exit_code=0 的 evidence）。
- 不把状态库提交进 git（DSH 的 `--root` 建议放工作区内的 `.why-exist/`，是否 ignore 由项目决定）。

## 4. DSH 原生映射

| 需求 | DSH 机制 |
|------|----------|
| 技能发现与按需加载 | `.dsh/skills/why-exist-graph/SKILL.md`（frontmatter `name/description/whenToUse`；项目根为 cwd 时即 `.dsh/skills`） |
| 技能热更新 | `SKILL.md` 变化由 DSH skill-filesystem 监视并刷新目录，无需重启会话 |
| 状态 | SQLite 文件（`--root`，默认 `./.why-exist`） |
| 角色并行 | `role-prompt` 生成 teammate 提示；`target_ids` 隔离写入；audit 由独立成员执行 |
| 机械自检 | `wxg verify`（契约块、frontmatter、命令/角色/kind/写入列交叉引用、导出样例；不替代 doctor/行为测试） |
| 回归测试 | 标准库 `unittest`，`python -m unittest discover -s .dsh/skills/why-exist-graph/tests` |

DSH 本身没有给“自定义技能挂 CLI”额外包装；本实现就是技能目录下的普通 Python
脚本，因此不依赖 DSH 内部 API。

**Windows 沙箱临时目录**：DSH 的 `windows-acl` 沙箱下，Python ≥3.12.4 用
`os.mkdir(path, 0o700)`（`tempfile.mkdtemp` 的内部实现）创建的目录 DACL 为空，创建者
都无法写入/删除（DSH discussion #4290）。因此 `wxg.py` 的 `make_temp_dir()` 在 Windows
上用**默认 mode** 建临时目录，POSIX 仍用 `0o700`；`verify`、`gen_sample` 与测试都走它。

## 5. 非目标与已知边界

- **导入器只有 Python AST**。`repo-add --language` 只接受 `python`；其他语言通过
  `upsert-node` / `upsert-edge` 手工写；当前没有运行时 adapter 机制，真要扩展需在
  `wxg.py` 增加导入器与分发（不假装支持全语言）。
- **导出不是叙述型设计文档**。它只投影图里连到 feature 的记录；旧版 07 的“读完不用看源码”
  目标没有恢复，因为那需要额外的生成层，且容易与图漂移。
- **测试执行不在 wxg 内**。`implement-test` / `observe` 的裁决依赖外部证据（测试运行结果、
  重扫结果）；wxg 强制“没有同 generation、exit_code=0 且产物有效的 evidence 不得置 BehaviorPassed”，
  但不校验证据真伪。
- **状态库文件是信任边界**。wxg 不防“绕过命令直接改 sqlite”的 out-of-band 篡改；doctor 只能
  发现部分不一致（悬空引用、legacy、条件/审计配对、证据产物等）。
- **gate 不评价图规模/设计质量**。它只校验条件、咬合、证据、pattern 的必填边界与 coverage
  策略；最小 requirement 图也可能 PASS，语义强弱由使用方判断。
- **coverage 是概率约束，不是正确性证明**。先验、ε、α 由使用方选择；它假设咬合能发现该
  阶段同类问题，不覆盖审计误放或运行时缺陷。
- **suite/子系统**：本实现用“一个套件 feature + 多个子 feature”表达跨仓范围，不再生成每个
  子系统的独立设计包；如果要恢复该能力，应作为导出层的扩展，而不是再引入第二套契约。

## 6. 常用命令

```powershell
$env:PYTHONUTF8=1
$skill = ".dsh/skills/why-exist-graph"
# 自检
python "$skill/scripts/wxg.py" verify
# 回归
python -m unittest discover -s "$skill/tests" -v
# 样例重生成（改了导出渲染器后）
python "$skill/scripts/gen_sample.py" --write
# 文档契约块重生成（改了 wxg_contract.py 后）
python "$skill/scripts/wxg.py" contract --write SKILL.md --section main
python "$skill/scripts/wxg.py" contract --write references/contract.md --section full
# 状态库体检
python "$skill/scripts/wxg.py" --root <root> doctor
python "$skill/scripts/wxg.py" --root <root> doctor --fix
```

## 7. 0.2.0 修复（来自 calculator-demo 实测）

| 实测问题 | 0.2.0 行为 |
|---|---|
| observe 重导入覆盖 model-structure 写的 `duty`/`x_note` | `import-file` 写节点改为 attrs 合并；扫描只刷新自己产生的键 |
| retract 后 bites / target_ids / evidence_ids 仍指向已删节点；gate 把悬空 bite 当第 7 条咬合 | `retract` 级联删 bite、剔除工单引用；`scope_ids` 只收现存节点；`gate` 输出 `ignored_dangling_bites` 且不计数 |
| `slice --work` 对通配 target 报 missing | `resolve_targets` 展开 `前缀*`，只报告真正缺失的 id |
| `work-finish` / `work-judge(passed)` 后 claim_token 残留 | finish 与 judge(passed) 清空 token |
| 没有状态完整性自检 | 新增 `doctor [--fix]`：悬空 bite/边/引用、陈旧 token、条件完整性、审计配对；输出 `by_check`/`truncated`，`--fix` 同步 meta 版本；退出码 0/1 |
| 契约版本 | `0.1.0` → `0.2.0`（schema 仍为 1） |

这些行为都有 `tests/test_wxg.py` 中的对应用例；`wxg verify` 仍只检查“文档/契约/样例”是否漂移，
不替代 `doctor` 的状态检查。0.3.0 已补 audit 执行者身份与证据记录；仍已知未覆盖：
implement-test 的文件级写边界、断言 → 测试用例的覆盖检查（见 §5 的非目标/边界）。

## 8. 0.3.0 契约升级（来自 student-course-system 实战审计）

SCS 的 gate/evidence 可以复现，但审计日志没有执行者身份，`finalize` 脚本重跑会追加 bite
并改写权威证据；这暴露的是技能契约的缺口，不是单个产品 bug。0.3.0 把“可追溯”写进契约：

| SCS 暴露的问题 | 0.3.0 行为 |
|---|---|
| audit 日志没有 auditor；`work-judge` 只认 `--role audit`，不记执行者 | `work-claim` / `work-judge` / `bite` 要求 `--actor`（或 `WXG_ACTOR`）；写 `claimed_by` / `judged_by` / `judged_at` / `bites.actor`；审计 actor 不得等于被审工单 `claimed_by` |
| 审计独立性无法从证据链证明 | `work-judge` 拒绝同人自审；旧库迁移身份标 `legacy`，`doctor` 报 `legacy-identity` 提示不可追溯但不伪造具体成员（该检查在 0.4.0 落地） |
| 证据是“脚本 + 日志”，DB 里没有登记；重跑可能改写权威状态 | 新增 `evidence-record` / `evidence-list`：登记 feature、work、命令、退出码、actor、产物路径与 SHA-256；`doctor` 校验产物存在与 hash；`finalize` 契约要求默认 `--dry-run` 或显式 `--apply` |
| 07 导出参数按 operation 展开会重复（course_id×3 等） | 参数、测试、断言按 id 去重；07 同一参数只列一次；契约写明顺序按首次出现 |
| 只有 14 个测试，audit/证据/迁移没覆盖 | 增加到 19 个：actor 独立性、证据登记/篡改检测、导出参数去重、0.2→0.3 schema 迁移、contract --json 可序列化 |

版本：契约 `0.2.0` → `0.3.0`，schema `1` → `2`；迁移只加列/表，旧行不删，未知身份标 `legacy`。

## 9. 0.4.0 契约升级（来自 why-exist-graph 自身一致性审计）

对 0.3.0 做"文档描述 vs 实现"审计后，修掉了会削弱交付门的几条路径（可机械验证的行为都有回归用例；迁移回填、缺库保护、链式调用 unmapped 也补了测试）：

| 审计发现 | 0.4.0 行为 |
|---|---|
| `feature-register --true` 可绕过 work-judge 把全部条件（含 Ready）置真 → gate PASS 且 0 工单/0 证据 | 移除 `--true`；同代登记不写条件；新建 feature / 显式 `--generation` 只写 Accepted（新代会重置条件、supersede 旧工单、回写 requirement 节点）；新代需手动 work-seed |
| I7"没跑过的测试不得置 BehaviorPassed"未强制 | `evidence` 增加 `generation` 列（schema 3）；`work-judge` 与 `gate` 都要求**同 generation**、exit_code=0 的 evidence；`doctor` 也检查 behavior-passed-without-evidence |
| 初版 0.4.0 的证据是 feature 级，旧代 evidence 可让新代零测试通过 | 证据按 generation 记账；重新声明后旧代 evidence 不再满足新代 BehaviorPassed |
| `attrs.bite` 可被 `upsert-node` 写入，gate 采信它当 KEEP 反证，绕过 bite actor 审计 | `upsert-node` 等图写入拒绝 `attrs.bite`；`attrs.bite` 只由 `bite` 命令写；gate 只采信 `bites` 表 |
| `init` 在已使用的新库上把 audit 单 `claimed_by` 从 NULL 改成 `legacy`（不幂等） | 迁移只在补列时执行一次，且跳过 audit 工单；`init` 重复运行零写入 |
| contract/design 说 doctor 会提示 legacy 不可追溯，实际没有 | `doctor` 新增 `legacy-identity` 检查 |
| `work-claim` 可领到旧代 ready 工单（feature-register 默认 gen+1 后） | `work-claim` 只发当前 generation 的工单；register 新代清空旧代 token |
| scan 等无对应条件的工单 failed 会清空全部条件（含 Accepted） | judge(failed) 对无对应条件的工单不改条件 |
| quick start 缺 `work-open`，按文档写新节点必被 target_ids 拒绝 | 文档补 `work-open` 步骤并说明扩展写入边界的用法 |
| `repo-add --language python/java/ts/vue` 实际只有 Python 导入器，错误提示指向不存在的 `wxg_import` | 只接受 `--language python`；错误信息如实说明；design.md §5 写明扩展方式 |
| `wxg verify` 在 DSH Windows 沙箱因 tempfile 0o700 DACL 不可用 | 新增 `make_temp_dir()`（Windows 用默认 mode），verify/gen_sample/tests 全部走它 |
| 命令表"写入"列靠 help 文本启发式，07 有契约外硬编码表 | `WRITE_MODES` 显式声明；07 的"请求参数"表进入 `EXPORT_FILES.extra_sections`；verify 检查每条命令都有写入列声明 |
| 文档绝对化（I3/I5/I7、quality.md）与实现不符 | 重写相关规则/不变量措辞，明确例外（Accepted、feature-declare/register requirement 节点、bite 的 attrs.bite）与 verify 的覆盖边界 |
| 输入校验缺口：register `--generation` 非法/`--spec` 类型错、`upsert-node --data {}` 触发 traceback、链式属性调用不标 unmapped | 补齐校验并给可读 error；链式/复杂调用也按 I7 建 unmapped 节点+边；register 回写 requirement 节点正文 |

版本：契约 `0.3.0` → `0.4.0`；schema `2` → `3`（`evidence.generation`，迁移优先按证据关联工单回填；关联工单不存在时也回退到 feature 当前代，不删行；旧证据无法还原真实代，升级后若需新代 BehaviorPassed 请重新登记）。测试 `19` → `42`。
破坏性变更：`feature-register --true` 移除；`gate` FAIL 退出码改为 1（PASS 为 0）；
`work-judge(passed)` 对 BehaviorPassed 增加**同代** evidence 前置条件。

## 10. 0.5.0 契约升级（产品级设计约束）

0.5.0 处理三件事：判决的确定性（单个 KEEP 不应抵消全作用域）、风险的可度量（覆盖约束与调度）、
设计质量的门禁（模式有限应用）。这三件事都要求契约先行，CLI 与文档随后：

| 暴露的问题 | 0.5.0 行为 |
|---|---|
| 作用域内任意一个 KEEP 会抵消所有 UNNECESSARY/HOLLOW，反证可被滥用 | 按节点当前代最新一条 bite 计判决；KEEP 只反证同一节点；跨节点/旧代 KEEP 不再抵消（I13） |
| 失败历史丢失：判断失败后重做通过，旧 `fail_reason` 一直挂着 | 新增 `judge_history` 表，每次 `work-judge` 写入（只增不删）；`judge(passed)` 清空 `fail_reason`；doctor 校验关联与 actor（I14） |
| `sample` 按仓均匀抽，clean 节点稀释后验缺陷率 | `sample --feature` 按作用域抽；`bite` 记录 generation 与 phase（当前第一个未满足条件） |
| 覆盖没有可计算约束，调度收敛只能靠经验 | `coverage` 命令：按“未覆盖节点 × 后验缺陷率”算 `n_required` 与调度索引；`--coverage-epsilon` 开启后 judge/gate 强制（I15） |
| 模式只是口头约定，过度应用无法机械拦截 | `pattern` 节点 + `applies` 边；gate 强制 `applicability`/`not_applicable` 与具体设计元素挂载（I12）；目录见 `references/patterns.md` |
| 04 架构视图不体现模式决策 | 04 导出包含作用域内 pattern 行 |

版本：契约 `0.4.1` → `0.5.0`；schema `3` → `4`（`features.coverage_epsilon`、`bites.generation`/`phase`、
`judge_history` 表；迁移只加列/表，旧咬合按升级时 feature 当前代回填 generation，更早代无法还原）。测试 `42` → `50`。

破坏性变更：跨节点 KEEP 不再抵消 UNNECESSARY/HOLLOW；pattern 缺必填字段或未挂载会 gate FAIL；
coverage 默认不强制，需 `feature-declare --coverage-epsilon` 显式开启。

## 11. 0.6.0：中大型仓的性能与门禁补齐

0.5.0 之后实测暴露两类问题：大仓扫描的成本随节点数超线性增长；`UNMAPPED/DOC-ONLY`
这一侧“结构对不上代码”的判决仍不拦门。0.6.0 各修一条：

| 问题 | 0.6.0 行为 |
|---|---|
| `require_targets` 对每个节点遍历全部 target_ids，整仓扫描 O(nodes × patterns) | 预分成精确集合与通配前缀，成员检查变成 O(1)+O(前缀数)；实测 120 文件 / 7.7k 节点的写入从 20.06s 降到 16.74s |
| `import-file` 把每个节点 id 追加进工单 `evidence_ids` 并对整个 list 重新序列化，O(N²) | 扫描不再写 `evidence_ids`（节点范围已由 target_ids 覆盖，finish 的子集检查对空列表仍成立） |
| 整仓 scan 的 `work-claim` 会返回多 MB 的深度 1 切片，塞爆代理上下文 | `work-claim --brief` 只返回计数；`slice --work <id> --limit N` / `find --limit N` 截断并带 `truncated`/`total` |
| 结构漂移判决只记录、不拦门 | 新增 `feature-declare --drift-limit N`：gate 统计当前代最新判决为 UNMAPPED/DOC-ONLY 的节点数，超限 FAIL；`drift` 字段在 gate/status 中始终可见 |
| `applies` 边可在任意节点间连，模式挂载可被伪造 | `upsert-edge` 强制 `applies` 的 src 只能是 component/classifier/operation、dst 只能是 pattern；`doctor` 对旧边补 `applies-invalid` 检查 |
| `coverage.next` 取调度索引最大的阶段，和“阶段顺序推进”不一致 | 改为取条件顺序里第一个未达标阶段；索引只用于预算分配 |

版本：契约 `0.5.0` → `0.6.0`；schema `4` → `5`（`features.drift_limit`；迁移只加列，默认 NULL 不强制）。
测试 `50` → `57`。非破坏性：新增字段/开关均默认关闭；`applies` 写入校验只拒绝本就非法的边。

## 12. 0.7.0：从命令驱动到控制器单步

到 0.6.0 为止，每个状态迁移都要人/代理敲一条命令：失败单停在 ready 等人重领，blocked 只在
judge 时刷新，陈旧 claim 不会自动回收。0.7.0 加一个 level-triggered 的控制器单步，
但不把裁决自动化：

| 问题 | 0.7.0 行为 |
|---|---|
| 没有“期望 vs 观测”的统一入口，调谐靠人记 | `reconcile --feature` 默认只读，输出动作清单；`converged` = gate PASS 且无待办，退出码 0/1；同一状态重复运行输出相同 |
| 缺失工单、blocked 卡住、claim 过期无人处理 | `reconcile --apply` 只做三类安全迁移：`work_seed` 补单、`refresh_blocked` 解阻塞、回收超过 `--claim-ttl`（默认 3600s）的 claimed 工单（清 token/assignee/claimed_by 并回 ready） |
| 自动调谐可能越权改图/替人裁决 | 裁决、咬合、图写入、导出永不自动；覆盖缺口、漂移超限、施工标记、失败重试只作为待办报告 |
| 回收陈旧 claim 需要领取时间 | schema 6：`work_items.claimed_at`，`work-claim` 写入；旧库按 created_at 回填（只是下界） |
| 多进程写库时报 `database is locked` | `connect()` 显式 `journal_mode=WAL` + `busy_timeout=5000`；单写者不变，短写排队 |
| 施工中的代码段没有标识，gate 可能带着半成品放行 | `construction` 布尔 attr（component/classifier/operation）；gate 遇未清除标记直接 FAIL；清标记 = 一次不含该键的 upsert-node 覆盖；标记不参与咬合/覆盖 |

版本：契约 `0.6.0` → `0.7.0`；schema `5` → `6`（`work_items.claimed_at`，迁移只加列）。
测试 `57` → `64`。非破坏性：`reconcile` 是新增命令；`construction` 是新增可选 attr；
WAL 对现有 CLI 行为透明。

## 13. 0.8.0：变更集（设计变更不再整代重跑）

0.7.0 之前，交付后要改设计只能 `feature-declare` 开新代，整条条件链（含需求、扫描、证据）
全部重跑。0.8.0 引入变更集：新代只重置受影响的设计条件，上游条件按上一代继承。

| 问题 | 0.8.0 行为 |
|---|---|
| 小改一个结构也要整链重审 | `change-open --from-condition <条件>`：只在 Ready 后可用；from-condition 之前的条件继承为真（reason 标“继承自第 N 代”），从它起及其下游重置为假；`changes` 表记录 from/to generation 与继承边界（I18） |
| 变更后不知道该重做什么 | `work-seed` 自动为被重置的条件补齐工单（含 implement-test/observe），并按依赖链 blocked→ready；reconcile 不会重复补单 |
| 不知道改了哪些设计/代码 | `change-diff` 只读对比两代工单的 `evidence_ids`：added/removed/kept、继承与待办条件、带 repo/path 的代码锚点；不存节点内容快照，因此是“写过的节点集合差”，不是字段级 diff |
| 继承条件绕过了审计 | `doctor` 新增 `change-generation`/`change-from-condition`/`change-conditions-missing`/`change-inheritance` 检查；继承条件必须与 changes 记录的边界一致 |
| 旧代证据混进新代 | 新代是新的 generation，`BehaviorPassed` 必须重新登记同代 evidence；继承只发生在设计条件，不覆盖行为证据 |

版本：契约 `0.7.0` → `0.8.0`；schema `6` → `7`（`changes` 表，迁移只建表）。
测试 `64` → `70`。非破坏性：`change-open`/`change-diff` 是新增命令；既有 feature 不受影响。

## 14. 0.9.0：回扫断言（代码删除/改名不再静默）

`import-file` 只 upsert、从不删除：代码里删掉或改名的符号，图里会留下永久旧节点，gate 看不到。
0.9.0 让重扫产生“生还”事实：

| 问题 | 0.9.0 行为 |
|---|---|
| 删除/改名后旧锚点永远留在图里 | schema 8：`nodes.stale`。`import-file` 写同一文件时，同 repo+path 下本次未再出现的旧节点标 `stale=1`，再出现清 0；`--prepare` 把该文件已有旧节点并入 scan 工单 target_ids，保证标记不越出写入边界（I19） |
| 交付门看不到“图里有、代码没有” | gate 对作用域内 `stale=1` 节点直接 FAIL；`feature-status`/`reconcile` 输出 stale 列表与动作 |
| 想知道整仓和代码差多少 | `sync --repo` 只读重解析全部 Python 文件，对比 DB：missing/new/changed/stale 与解析错误，带 `--limit` 截断 |
| stale 靠自觉清理 | 重扫同一文件（出现即清）、设计角色重写节点（upsert 会清 stale）或人工修正；sync 本身不写库 |

边界：回扫只解析 AST；删除/改名表现为 stale 或 missing+new，跨文件移动需要人工判断；没被重扫的
文件不会自动标 stale。

版本：契约 `0.8.0` → `0.9.0`；schema `7` → `8`（`nodes.stale`，迁移只加列，默认 0）。
测试 `70` → `73`。非破坏性：新列有默认值；`sync` 是新增只读命令。

## 15. 1.0.0：收敛约束成为默认

0.5.0 起 coverage 一直是 opt-in；1.0.0 把它变成新 feature 的默认交付约束，同时保留逃生阀：

| 问题 | 1.0.0 行为 |
|---|---|
| 收敛公式只对显式开启的 feature 生效，默认仍是“无覆盖约束” | 新 feature 默认 `coverage_epsilon=1.0`；`work-judge(passed)` 与 gate 在阶段推进前执行覆盖检查 |
| 团队可能被默认门禁卡住（大作用域 ε=1 的 n_required 接近 S） | `--no-coverage` 显式关闭；显式 `--coverage-epsilon` 改阈值；重声明默认保留已有策略，只有显式 flag 才改 |
| 旧 feature 升级后被突然收紧 | 迁移只加列，旧 feature 的 `coverage_epsilon` 保持 NULL（不强制）；只有新声明的 feature 默认开启 |
| 不知道当前策略 | `feature-status` / `coverage` 始终输出 enforced、epsilon、n_required，gate 输出 coverage 明细 |

代价与边界：ε=1 是“期望残留缺陷数”，不是“缺陷率”；作用域越大，覆盖成本越高。建议把 feature
按能力拆小，或按风险调 ε。覆盖仍是概率模型，不证明语义正确。

版本：契约 `0.9.0` → `1.0.0`；schema 仍为 `8`。测试 `73` → `76`。
破坏性（语义）：新 feature 默认启用 coverage；不想被覆盖门禁拦截的调用方需显式 `--no-coverage`。

## 16. 1.1.0：并行状态库与常驻控制器

1.0.0 的状态库还是单机 SQLite；多代理并行和跨主机是硬边界。1.1.0 把存储层做成可插拔，
并补一个常驻控制器：

| 问题 | 1.1.0 行为 |
|---|---|
| SQLite 只允许一个写者，跨主机无法共享 | `WXG_DB_URL=mysql://user:pass@host:3306/db`（或全局 `--db-url`）切到 MariaDB/MySQL；行级锁 + 多写者，导出目录仍由 `--root` 决定 |
| 依赖第三方 MySQL 驱动会破坏“纯标准库” | 内置 `scripts/wxg_mysql.py`：握手 v10、mysql_native_password、`?` 参数转义、文本协议结果解析、事务；唯一第三方要求仍是 Python 3.10+ |
| MySQL 的 DDL/标识符与 SQLite 不同 | 单独的 `MYSQL_SCHEMA_SQL`（TEXT 键列改 VARCHAR、`AUTO_INCREMENT`、去部分索引、`key`/`value` 反引号）；执行时把 `INSERT OR IGNORE`、`ON CONFLICT ... DO UPDATE`、`excluded.x`、`:name` 参数翻译成 MySQL 方言 |
| 两个代理同时抢同一张工单 | `work-claim` 改成条件 UPDATE 并检查 rowcount，只有拿到 1 的代理成功；MySQL 下连接设 `READ COMMITTED`，避免 1020（record changed since last read） |
| 控制器只能手敲一次 | `serve --interval N [--apply] [--once]`：循环对全部 feature 跑 reconcile，只执行三类安全迁移；`--once` 单趟便于 CI |

边界：内置客户端只支持 `mysql_native_password`（无 TLS、caching_sha2、压缩、LOAD DATA）；MySQL
后端要先有可用的 MariaDB/MySQL 实例，`init` 不会创建数据库本身；`serve` 是单进程循环，不是分布式
调度器。PostgreSQL 后端未内置（需要 psycopg），1.2.0 已补上（见 §17）。

版本：契约 `1.0.0` → `1.1.0`；schema 仍为 `8`（只加后端选择，无表结构变更）。
测试 `76` → `95`（其中 3 个 MySQL 后端集成用例需 `WXG_TEST_MYSQL_URL`，默认跳过）。

## 17. 1.2.0：PostgreSQL 后端

网络恢复后先起 PostgreSQL 16（`postgres:16-alpine`），再补 PG 后端：

| 问题 | 1.2.0 行为 |
|---|---|
| 只有 MySQL 后端，PG 用户用不上 | `WXG_DB_URL=postgresql://...` 或 `--db-url postgresql://...` 切 PG；默认仍是 SQLite |
| PG 驱动是第三方包 | 延迟加载 `psycopg`（`pip install 'psycopg[binary]'`）；没装时连接报可读错误，不影响 SQLite/MySQL 路径 |
| PG 的 DDL/占位符与 SQLite 不同 | `PG_SCHEMA_SQL` 把 `INTEGER PRIMARY KEY AUTOINCREMENT` 换成 `BIGSERIAL`（TEXT 主键、部分唯一索引、ON CONFLICT 语法与 SQLite 相同）；`INSERT OR IGNORE` 翻成 `ON CONFLICT DO NOTHING`，`?` 占位符翻成 `%s`，结果用 `dict_row` |
| 并发抢单 | 与 MySQL 相同的条件 UPDATE + rowcount；PG 默认 READ COMMITTED，两进程抢同一张单只有一个成功（有集成测试） |
| 验证 | 3 个 PG 集成用例（init/scan 全流程、并发 claim、serve --once），需要 `WXG_TEST_PG_URL`，默认跳过 |

边界：PG 后端需要可用的 PostgreSQL 实例，`init` 不会建库；psycopg 未安装时只能走 SQLite/MySQL；
PG 侧不做连接池（每个 CLI 一条短连接）。

版本：契约 `1.1.0` → `1.2.0`；schema 仍为 `8`（无表结构变更）。
测试 `95` → `98`（新增 3 个 PG 后端集成用例，默认跳过）。

## 18. 1.3.0：设计-代码一致性（只报差异）

why-exist 之前只有锚点的一半：代码节点有 path/symbol、重扫能标 stale，但设计节点没有代码锚点，
gate 也不检查设计与代码结构是否对得上。1.3.0 加一层**差异检查**，不建第二套设计模型：

| 问题 | 1.3.0 行为 |
|---|---|
| 设计节点和代码没有可验证的关联 | 新增 `maps_to` 边（设计节点 → 带 repo/path 的代码节点）；use_case/component/port 没有 `maps_to` 就进 `anchors.missing` |
| 架构依赖只是口头的 | 每条 component/port 的 `depends` 要在两边锚定的代码节点之间找到 calls/reads/writes 支撑，否则进 `structural.missing_backing` |
| 代码里存在未声明的耦合 | 代码调用跨了组件、但组件间没有 depends/associates，进 `structural.undeclared` |
| 用例没有测试 | use_case 没有 testcase 的 `verifies`，进 `tests.missing`（只报告，不替代 TestsSpecified） |
| 检查本身制造信息负担 | `conformance` 只输出差异清单，不生成节点、不补写描述、不做字段级 diff；`maps_to` 只是一条引用边，不复制代码结构 |

开关：`feature-declare --conformance` 开启后 gate 对 `violations` FAIL；默认关闭，旧 feature 迁移后保持关闭。
schema 9 只加 `features.conformance` 一列。

边界：结构检查依赖导入器的 calls/reads/writes，解析不到（unmapped）时检查偏保守；只覆盖 Python；
`maps_to` 的语义正确性仍靠审计与咬合，conformance 只回答“差异清单是否为空”。

版本：契约 `1.2.0` → `1.3.0`；schema `8` → `9`（`features.conformance`，迁移只加列）。
测试 `98` → `101`（conformance 差异报告、gate opt-in、开关保留）。

## 19. 1.4.0：让差异检查少漏一点

1.3.0 的结构检查只认已解析的 calls/reads/writes，跨文件裸名调用被导入器标成 unmapped 时，
`depends` 会被误判为“无代码支撑”。1.4.0 做三件小事，都不新增设计描述：

| 问题 | 1.4.0 行为 |
|---|---|
| 跨文件裸名调用解析不到，结构检查偏保守 | `conformance` 读时做一次受限启发式：unmapped 调用的名字在作用域内唯一匹配到某个 operation 时，临时视为该依赖（计入 `structural.resolved_heuristically`）；不写回图 |
| 代码侧看不到“没进设计”的部分 | `anchors.code_orphans` 列出没有被任何 `maps_to` 指向的 operation/classifier；只报告，不算 violation |
| `maps_to` 可以乱连 | 写入校验：src 必须是 use_case/component/port，dst 必须带 repo/path；空锚点、错方向直接拒绝 |

边界：启发式只在名字唯一时生效，重名/方法调用仍不解析；它服务于“依赖支撑”判断，不参与
未声明耦合（避免误报）；code_orphans 是清单，不是“所有代码都必须有设计节点”的要求。

版本：契约 `1.3.0` → `1.4.0`；schema 仍为 `9`。测试 `101` → `104`。

## 20. 1.5.0：设计期编译器（并行规划与盲化任务书）

前 1.x 的检查都在事后：交付有没有证据、设计与代码对不对得上。1.5.0 第一次把"事前"那一半
落成命令，目标是让并行拆分从架构师直觉变成可计算的量。

| 问题 | 1.5.0 行为 |
|---|---|
| 只有覆盖率与阶段建议，没有依赖图的结构指标 | `plan` 输出 SCC（必须先拆的环）、拓扑波次、最大反链（Dilworth：最小链覆盖 = n − 二分图最大匹配）与理论并行上限 |
| 设计图没有 `depends` 时，"全部可并行"是假象 | `--level auto` 检测到空设计图就退到代码层（calls/reads/writes），并在输出标明实际层级 |
| 依赖了作用域外节点的边被悄悄吞掉 | 一端在界内的边保留并由归一化报告为 `dangling`，两端都在界外的才丢弃 |
| 给执行者的说明要么带上全局计划，要么信息不足 | `brief` 生成盲化任务书：写入边界、界外上游输入、产出契约、禁止事项、完成定义；只接收单张工单数据，结构上无法泄露其它工单 |
| 新算法混进 3.8k 行的 `wxg.py` | 新增 `scripts/whyexist/` 纯函数包；`graph_algo` 不碰数据库，`planner`/`briefing` 不 import 入口脚本（避免 `__main__` 与模块双份实例） |

边界：`plan` 只能分析图里已有的边；`brief` 的盲化是信息裁剪，不保证切分正确；盲执行验证
（把任务书交给不知全局的执行者并校验产出）尚未实现，是下一阶段的目标。

版本：契约 `1.4.0` → `1.5.0`；schema 仍为 `9`。测试 `104` → `162`。

## 21. 1.6.0：盲执行验证

1.5.0 有任务书，但没有回答"任务书交给独立执行者会不会做对"。1.6.0 用结构校验回答一半：

| 问题 | 1.6.0 行为 |
|---|---|
| 任务书只展开已存在节点，新建节点被误判越界 | `brief` 同时输出 `write_patterns`（原始 target_ids）；`blind-check` 用 pattern 判定新建 id |
| 执行者越界写、引用未声明外部节点、产出奇怪 kind | `blind-check` 分三类报告：`boundary.out_of_bounds`、`dependencies.undeclared`、`contract.{unexpected_kinds,unknown_kinds,unknown_edge_kinds,malformed}` |
| 只看 PASS/FAIL 看不到差在哪 | `locality` 从 1.0 起按违规项扣分（越界 −0.4、未声明依赖 −0.3、契约不符 −0.3，多项递减），供趋势观察，不参与判定 |
| 更新已有节点被误杀 | `produces` 只检查新建节点（id 不在已展开边界内） |

边界：`blind-check` 只做结构校验，不判断产出语义是否正确，也不替代审计；它证明的是
"这次执行没有越界"，不是"切分合理"。后者要靠多个盲执行结果的分布来看。

版本：契约 `1.5.0` → `1.6.0`；schema 仍为 `9`。测试 `162` → `177`。

## 22. 1.7.0：可用性（一条命令起步 + 库 API）

前几版能力都在，但第一次用要按 SKILL.md 敲十几条命令，而且不能从 Python 调用。
1.7.0 补两个入口，不加新判定：

| 问题 | 1.7.0 行为 |
|---|---|
| 上手成本高，第一次要看完整文档 | `up` 在未初始化目录直接跑：init + demo 仓 + demo feature + 第一次 gate 结果，并列出下一步命令；幂等，不重置已有 feature |
| `up` 可能长成“自动交付”，绕过审计 | `up` 只搭骨架并做只读 gate；裁决、提交、审计仍必须显式执行，gate 结果通常是 FAIL 并列缺项 |
| 编译器能力只能 shell 调用 | `Engine` 暴露 `plan` / `brief` / `blind_check` / `gate`，只读；判定逻辑仍在 `planner` / `briefing` / `blind` |
| 新代码反向依赖入口脚本，异常类出现两份 | 所有对旧实现的调用收进 `whyexist/legacy.py`；`wxg.py` 以 `__main__` 运行时把自身注册为 `wxg`，使 `import wxg` 拿到同一对象 |

边界：`up` 只搭骨架，不跑完 8 个条件；`Engine` 没有写库方法（写仍走 CLI 与 claim_token）；
`wxg.py` 仍是主实现，`legacy` 的迁移目标是把它逐个搬进 `whyexist`。

版本：契约 `1.6.0` → `1.7.0`；schema 仍为 `9`。测试 `177` → `185`。

## 23. 1.8.0：影响域闭包与声明期冲突检测

1.7.0 之前只能验证"这次执行有没有越界"，回答不了"改了这块还有什么会被带动"。
1.8.0 把影响范围变成可计算的闭包，并把跨 feature 的写边界冲突提前到声明期。

| 问题 | 1.8.0 行为 |
|---|---|
| 改动的影响面靠人看 | `impact` 输出反向可达的受影响集、正向依赖集、命中的 requirement，以及连不到任何 requirement 的 `uncovered` |
| 影响落到了别的 feature 却不知道 | `cross_feature` 列出受影响但不在本 feature 作用域内的节点及所属 feature |
| 两个 feature 声明了重叠的写入边界，直到抢写才发现 | `conflicts` 两两比较 `target_ids` 模式（精确 id 与 `前缀*` 的前缀关系），输出重叠模式对与当前图上的重叠节点 |
| 影响传播与需求归属混在一条边集合里 | 影响传播只走 `depends/calls/reads/writes`；需求覆盖用全部结构边（`satisfies/associates/contains`），否则设计节点永远连不到 requirement |

边界：`closed` 用无向连通判断，偏宽松，会少报 uncovered；`conflicts` 只看边界重叠，不看
依赖时序（A 依赖 B 的产出时，边界不重叠也不应该并行）；两者都是只读报告，不拦门。

版本：契约 `1.7.0` → `1.8.0`；schema 仍为 `9`。测试 `185` → `211`。

## 24. 1.9.0：操作日志 + 单一 reducer

前几版的并行靠互斥：`claim_token` + `target_ids` 让两个代理不能改同一块，于是那两块只能
串行。1.9.0 把冲突从"抢写"挪到"合并"，并让合并结果与顺序无关。

| 问题 | 1.9.0 行为 |
|---|---|
| 并行度被 `target_ids` 互斥结构锁死 | 子任务产出补丁（`patch`），由单一 reducer（`apply`）合并；边界外写入不再靠锁排除 |
| 两个补丁改同一节点时互相覆盖 | `merge_patches` 按内容指纹比较：内容相同只去重，不同则报 `conflicts` 并拒绝写入 |
| 冲突时写了一半 | 校验全在写入前；冲突或未知端点直接返回，不写库；写入阶段异常由事务回滚兜底 |
| 合并结果依赖补丁顺序 | 节点/边排序、按 id 去重，交换补丁顺序得到相同结果 |
| 边引用不存在的节点 | `unknown_endpoints` 报告，`ok=false` |

边界：`apply` 有意绕过 `target_ids`（它假定自己是单一执行者）；冲突只按节点内容判定，
不检测语义冲突；补丁文件就是操作日志，没有单独的日志表。

版本：契约 `1.8.0` → `1.9.0`；schema 仍为 `9`。测试 `211` → `224`。

## 25. 2.0.0：设计期编译器总览

1.5.0 到 1.9.0 是一条线：先有并行规划与盲化任务书，再有盲执行校验、影响域、补丁合并。
2.0.0 不再加能力，只把这条线收成产品形态：

| 层次 | 已落地的命令 | 作用 |
|---|---|---|
| 规划 | `plan` / `conflicts` | 依赖图上的 SCC、波次、最大反链、理论并行上限；声明期写边界重叠 |
| 验证 | `brief` / `blind-check` | 结构性盲化任务书；独立执行产出的边界/契约/依赖校验 |
| 影响 | `impact` | 改动闭包、需求覆盖、跨 feature 影响 |
| 并行 | `patch` / `apply` | 补丁合并替代抢写锁；冲突显式、不写半截、与顺序无关 |
| 入口 | `up` / `Engine` | 一条命令起步（minimal/standard）；只读库 API |

边界：`wxg.py` 仍是主实现，`whyexist` 包目前承载新能力与 `legacy` 隔离层，拆包未完成；
所有新判定都是结构性的，不判断设计语义质量。

版本：契约 `1.9.0` → `2.0.0`；schema 仍为 `9`。测试 `224` → `225`。

## 26. 2.1.0：从代码反推候选设计

2.0.0 的编译器全部依赖设计图，但已有仓（尤其需要重构的仓）没有设计图。2.1.0 补上
`derive`：把代码聚成 component 候选、用 import 关系推导 depends 候选，写 `origin=derived`，
可被咬合质疑，确认后提升为 `declared`。

| 问题 | 2.1.0 行为 |
|---|---|
| 单文件导入对中型仓不可行 | `import-repo` 按仓批量导入；httpie 133 个文件一次完成 |
| 已有仓没有设计图 | `derive --strategy package` 按目录深度分组，产出 component 候选 |
| 静态调用图解析不出跨模块依赖 | 依赖有两条来源：跨组调用边 + import 解析（`from a.b import c` 映射到文件） |
| unmapped 节点 id 带行号，重构产生整批伪 diff | id 去行号、按名字聚合；行号留在 `line_start/line_end` |
| `plan` 把内置调用噪声算进并行度 | 默认排除 unmapped，输出 `excluded_unmapped` |
| 代码节点混进设计层，反链 = 节点数 | design 层只保留 component / port / pattern |
| 单点自环把 parallelism 压成 1 | 只有大小 > 1 的 SCC 阻断并行 |
| 「有环」与「能分层」自相矛盾 | 自环存在时 `layers=null` |

边界：`derive` 不猜组件语义，只按目录结构给候选；import 只解析绝对 import；
`derived` 到 `declared` 的硬边界（promote 动作）尚未实现，目前靠 `origin` 字段区分。

版本：契约 `2.0.0` → `2.1.0`；schema 仍为 `9`。测试 `225` → `242`。

## 27. 2.2.0：derived → declared 的显式提升

2.1.0 用 `origin=derived` 标记"从代码推出来的假设"，但没有动作把它变成"人裁决过
的设计"。2.2.0 补 `promote`，把这一步显式化，但不增加修改门槛。

| 问题 | 2.2.0 行为 |
|---|---|
| 候选与确认的设计混在一起，只能靠 origin 字段区分 | `promote` 是唯一转换入口：`derived` → `declared`，写 `x_promoted_by` / `x_promoted_at` |
| 非候选节点也能被"提升"，语义混乱 | 只接受 `origin=derived` 的节点，其余直接拒绝 |
| 提升变成审批，阻碍修改 | 只记录裁决者，不触发重新审计；提升后的节点仍可照常修改、被 `bite` 判定 |

边界：`promote` 不判断组件语义是否合理，只记录"谁确认了它"；`derived` 节点在没有
`promote` 之前不应算作设计确认。

版本：契约 `2.1.0` → `2.2.0`；schema 仍为 `9`。测试 `242` → `244`。

## 28. 2.3.0：候选设计的边界清理

2.2.0 有 `promote`，但重跑 `derive`（换 depth 或 exclude）时，上一轮的候选会留在图里，
下一次 `plan` 把它们也算进去。2.3.0 把重跑语义补成和 `import-file` 一致：不再出现的候选标 stale。

| 问题 | 2.3.0 行为 |
|---|---|
| docs / tests / extras 被当成设计组件 | `derive --exclude tests,docs,extras` 不参与分组，输出 `excluded_nodes` |
| 重跑 derive 后旧候选残留，污染 plan | 本次未出现的 `derived` 节点标 `stale=1`；`declared` 节点不动 |
| 过期锚点仍参与规划 | `plan` 排除 `stale=1` 的节点，输出 `excluded_stale` |
| 候选节点没有 repo，按仓清理失效 | `derive --apply` 写入 `repo` 字段 |

边界：stale 只标不删；`derive` 仍只做 package 策略，不猜组件语义。

版本：契约 `2.2.0` → `2.3.0`；schema 仍为 `9`。测试 `244` → `246`。

## 29. 2.4.0：依赖环的成因追踪

`plan` 报 SCC 只到「这几个节点成环」；要修环，得知道是哪几条依赖、来自哪些文件。
2.4.0 把证据持久化并加一个只读的 `cycles` 命令。

| 问题 | 2.4.0 行为 |
|---|---|
| 只有环成员，没有成因 | `derive --apply` 把依赖证据写进 depends 边的 `x_evidence`（文件对，最多 20 条） |
| 环的定位停留在组件层 | `cycles` 输出 `members` + 环内每条边的 `evidence` + `self_loops` |
| 递归自环被混进环列表 | 自环单独列在 `self_loops`，不与多节点环混排 |

边界：环内列出的是 SCC 内部全部依赖边，不区分哪几条构成最短环；`cycles` 只读，
不判断该断哪条边——那是设计决策。

版本：契约 `2.3.0` → `2.4.0`；schema 仍为 `9`。测试 `246` → `255`。

## 30. 2.5.0：环的 what-if 分析

`cycles` 能列出环的成因边，但回答不了"断哪条能破环"。2.5.0 加 `--without`：在内存里
剔除指定依赖后重算 SCC，不写图。

| 问题 | 2.5.0 行为 |
|---|---|
| 知道环的成员和边，不知道断哪条有效 | `cycles --without src->dst,...` 输出剔除后的剩余环与 `without` 清单 |
| 真的改图再验证代价高 | 只读模拟，不写库 |
| 端点不在设计层时分析无意义 | `--without` 的端点必须属于设计层，否则拒绝 |

实测（httpie）：3-环由三个 2-环叠加而成，断 `cli -> output` 一条环仍在；同时断
`httpie -> cli`、`httpie -> output`、`cli -> output` 三条才归零。

边界：`--without` 只验证"去掉这些边后是否还有环"，不判断去掉是否可行、会不会引入新问题。

版本：契约 `2.4.0` → `2.5.0`；schema 仍为 `9`。测试 `255` → `256`。

## 31. 2.6.0：最小断边集合

`--without` 要人手动试断，2.6.0 让工具自己枚举最小反馈弧集：`cycles --break-set`
按边数从小到大找能破环的依赖边组合。

| 问题 | 2.6.0 行为 |
|---|---|
| 手动试断靠猜 | 枚举 size=1、2、3… 的边组合，返回第一批能破环的集合 |
| 自环会被漏掉 | 自环也是候选断边，和普通边一起参与枚举 |
| 大图枚举爆炸 | 边数超过 20 直接返回 `truncated`，不硬算 |
| 不知道断哪条更安全 | 每条候选边带 `x_evidence`，人能据此判断 |

实测（httpie）：三个双向对的 3-环，最小断边集合大小是 3，共 6 个候选——
理论上 8 种「每对一个方向」里，有 2 种断完仍成环（如剩 `b->a->c->b`）。

边界：只保证边数最少，不保证断掉不破坏功能；可行性是人的设计判断。

版本：契约 `2.5.0` → `2.6.0`；schema 仍为 `9`。测试 `256` → `263`。

## 32. 2.7.0：断边的影响分析

`cycles --break-set` 只保证断边后无环，不保证不破坏功能。2.7.0 给 `impact` 加
`--remove-edges`：对比断边前后的传递可达，回答"断掉它，源点失去哪些可达"。

| 问题 | 2.7.0 行为 |
|---|---|
| 不知道断边会不会丢依赖 | `lost_reachable` 给出断前可达、断后不可达的节点；`lost_count` 是代价指标 |
| 有替代路径时凭空报影响 | 传递可达比较能识别替代路径，`lost_count` 为 0 说明不唯一 |
| 需求归属逻辑重复 | `requirement_coverage` 抽成公共函数，节点影响与断边影响共用 |

实测（httpie）：断 `cli -> output` 的 `lost_count` 是 0（cli 仍可经 httpie 到达 output），
但它也不是断环的有效边（2.5.0）。既非必要也非充分——这正是为什么断边可行性要人判断。

边界：`lost_reachable` 只回答可达性是否丢失，不回答功能是否受损。

版本：契约 `2.6.0` → `2.7.0`；schema 仍为 `9`。测试 `263` → `267`。

## 33. 2.8.0：断边建议

两个维度分开看不够：一条边可能在最小断边集合里，但断它丢很多可达；也可能不丢可达，
但它只是组合的一部分。2.8.0 把两者合起来给建议。

| 问题 | 2.8.0 行为 |
|---|---|
| 知道候选边，不知道优先断哪条 | `cycles --advise` 每条边标 `in_break_set` + `lost_count`，按档位与代价排序 |
| 环图上的可达集把自身算进去，代价虚高 | `transitive_reachable` 退化分支排除起点 |
| 多条待断边一起比较，看不出单条代价 | `edge_removal_impact` 改为逐条评估 |

档位：`preferred`（在断边集合里且不丢可达）、`acceptable`（在集合里但丢可达）、
`avoid`（不在任何最小断边集合里）。

边界：逐条评估「只断这一条」的代价，不评估「组合断掉」的总代价；`in_break_set`
只说明它参与某个最小断边集合，不代表断它一条就够。

版本：契约 `2.7.0` → `2.8.0`；schema 仍为 `9`。测试 `267` → `271`。

## 34. 2.9.0：断边集合的总代价

`--advise` 逐条评估代价，但真正要执行的是一个集合。2.9.0 给 `--break-set` 的每个候选
补上整体移除后的代价，让不同断边方案可比。

| 问题 | 2.9.0 行为 |
|---|---|
| 逐条代价不能代表组合代价 | `break_set_costs` 把整个集合一起移除，算 `lost_pairs` 与 `affected_count` |
| 多个最小断边集合不知道哪个便宜 | `--break-set` 的每项带 `cost`，可直接比 |
| 断了之后哪些节点受影响 | `affected_nodes` 列出端点集合 |

实测（httpie）：6 个 size=3 候选的 `lost_pairs` 从 3 到 11；最便宜的是断掉三条回流到
根包的边（`cli->httpie`、`cli->output`、`output->httpie`）——代价最小，也最符合分层直觉。

边界：`lost_pairs` 只算可达性，不算功能语义；它回答"哪组断得更少"，不回答"该断哪组"。

版本：契约 `2.8.0` → `2.9.0`；schema 仍为 `9`。测试 `271` → `273`。

## 35. 2.10.0：拆包第一步

`wxg.py` 已经 4500 行，命令处理器、状态机、图读写全在一个文件里。2.10.0 开始往外搬，
先搬没有业务依赖的三块。

| 模块 | 内容 |
|---|---|
| `whyexist/errors.py` | `Reject`：全包唯一的异常类；`wxg.py` re-export 保持 `wxg.Reject` 可用 |
| `whyexist/jsonio.py` | `utc_now` / `dumps` / `loads` / `load_json_arg` / `new_token` |
| `whyexist/temp.py` | `make_temp_dir` / `temp_dir`，含 Windows 沙箱 DACL 规避说明 |

迁移方式：先建包内实现，再在 `wxg.py` 顶部 import re-export，删除原定义。这样模块内
调用点与旧测试的 `wxg.xxx` 引用都不必改，全量回归通过即证明行为未变。

边界：只搬了基础工具层；命令处理器、状态机、图读写仍在 `wxg.py`。

版本：契约 `2.9.0` → `2.10.0`；schema 仍为 `9`。测试 `273` 不变。

## 36. 2.11.0：拆包第二步（数据库层）

`wxg.py` 的数据库层约 600 行，是图读写与状态机的前置依赖。2.11.0 把它搬进
`whyexist/db.py`。

| 模块 | 内容 |
|---|---|
| `whyexist/db.py` | 三套 schema、连接与方言适配（SQLite/MariaDB/PostgreSQL）、`migrate_schema`、`init_db` |
| `whyexist/contract.py` | 契约桥接：`wxg_contract` 仍在 `scripts/` 根，包内用它拿契约 |

迁移用一次性脚本按行范围提取整段、再在 `wxg.py` 原位替换为 re-export，避免手抄 600 行。
全量回归仍是 273 通过——拆包不改行为。

边界：图读写、状态机、命令处理器仍在 `wxg.py`。

版本：契约 `2.10.0` → `2.11.0`；schema 仍为 `9`。测试 `273` 不变。

## 37. 2.12.0：拆包第三步（图读写）

节点/边/绑定的读写与写入校验搬进 `whyexist/graph.py`，约 200 行。

| 模块内容 | 说明 |
|---|---|
| `check_kind` / `check_attrs` / `check_node_id` | 写入前的 kind、属性键、id 前缀与字符校验 |
| `get_node` / `upsert_node` | 节点读写；`merge_attrs` 保留设计角色手写标注 |
| `upsert_edge` / `edge_id` / `bind_node` | 边写入与参数绑定；含 `applies` / `maps_to` 方向校验 |
| `repo_rows` / `find_repo` | 仓登记查询 |

`DESIGN_ANCHOR_KINDS` 从 `wxg.py` 挪进 `whyexist/contract.py`——它是契约概念，
图读写的 `maps_to` 校验和导出都用它。

边界：状态机、命令处理器、导出/校验仍在 `wxg.py`。

版本：契约 `2.11.0` → `2.12.0`；schema 仍为 `9`。测试 `273` 不变。

## 38. 2.13.0：拆包第四步（工单状态机）

工单领取、令牌、写入边界、证据追加搬进 `whyexist/work.py`，约 100 行。

| 函数 | 作用 |
|---|---|
| `work_id` / `get_work` / `get_work_by_token` | 工单 id 与查询 |
| `insert_work` | 建单；`merge=True` 时把新节点并入已有 `target_ids` |
| `require_token` / `require_role` | 领取令牌与角色命令校验 |
| `target_match` / `require_targets` | 写入边界校验（精确集 + 通配前缀） |
| `append_evidence` | 工单写过的节点集合 |

边界：feature/条件、导入器、命令处理器、导出/校验仍在 `wxg.py`。

版本：契约 `2.12.0` → `2.13.0`；schema 仍为 `9`。测试 `273` 不变。

## 39. 2.14.0：拆包第五步（feature/条件状态机）

条件链、代、就绪派生与作用域搬进 `whyexist/workflow.py`。

| 函数 | 作用 |
|---|---|
| `get_feature` / `ensure_feature` | feature 读取；不存在时抛 `Reject` |
| `condition_rows` / `condition_flags` | 当前代条件；条件不齐时拒绝 |
| `current_phase` | 第一个为假的条件，即当前阶段 |
| `set_condition` / `recompute_ready` | 条件写入与 `Ready` 派生 |
| `refresh_blocked` | 依赖已 passed 的 blocked 工单回 ready |
| `scope_ids` | feature 作用域 = feature_nodes + requirement 前缀 + 当前代工单 target_ids（含通配展开） |

边界：覆盖/漂移/一致性/调谐（`gates.py` 候选）、导入器、命令处理器、导出/校验仍在 `wxg.py`。

版本：契约 `2.13.0` → `2.14.0`；schema 仍为 `9`。测试 `273` 不变。

## 40. 2.15.0：拆包第六步（门禁分析）

覆盖、漂移、一致性、调谐搬进 `whyexist/gates.py`，约 370 行。

| 函数 | 作用 |
|---|---|
| `_feature_bites` | 当前代作用域内的咬合记录 |
| `_required_coverage` | 解覆盖不等式，给出需要的去重覆盖数 |
| `drift_report` / `coverage_report` | 漂移计数与覆盖报告 |
| `conformance_report` | 设计锚点、结构支撑、未声明耦合、测试覆盖四类差异 |
| `reconcile_actions` | 调谐动作清单（补单、解阻塞、回收陈旧 claim） |

迁移教训：整段提取会丢掉隐式依赖。这轮暴露了 `work_id`、`datetime`、
`DESIGN_ANCHOR_KINDS` 三个缺失 import，以及一次替换范围把上一轮的 work re-export
吞掉——全部由全量回归抓出。

边界：导入器、命令处理器、导出/校验/CLI 仍在 `wxg.py`。

版本：契约 `2.14.0` → `2.15.0`；schema 仍为 `9`。测试 `273` 不变。

## 41. 2.16.0：拆包第七步（Python AST 导入器）

`plan_python` 与 `_node_id` 搬进 `whyexist/importer.py`，约 200 行。

| 内容 | 说明 |
|---|---|
| `_node_id` | `kind:repo:path:symbol` 的节点 id 规则 |
| `plan_python` | 解析单个文件：类/函数/属性、`contains` / `calls` / `reads` / `writes` 边 |
| unmapped 规则 | 内置/外部/链式调用建 unmapped 节点，按名字聚合，不静默丢弃 |

迁移暴露的隐式依赖：`edge_id` 来自 `graph.py`，漏了 import，靠回归抓出。

边界：命令实现与 CLI（约 2700 行）仍在 `wxg.py`。

版本：契约 `2.15.0` → `2.16.0`；schema 仍为 `9`。测试 `273` 不变。

## 42. 2.17.0：拆包第八步（只读查询命令）

`slice` / `get` / `find` 及其辅助搬到 `whyexist/query.py`，约 100 行。

| 函数 | 作用 |
|---|---|
| `resolve_targets` | 展开 `前缀*` 模式，返回实体 id / 缺失 id / 模式 |
| `slice_payload` | 深度 1 切片：节点、入边、出边、属性 |
| `cmd_slice` / `cmd_get` / `cmd_find` | 三个只读命令 |

迁移暴露的隐式依赖：`get_node`、`load_json_arg`、`get_work` 三个 import 先后漏掉，
靠回归逐个抓出。

边界：其余命令实现与 CLI 仍在 `wxg.py`。

版本：契约 `2.16.0` → `2.17.0`；schema 仍为 `9`。测试 `273` 不变。

## 43. 2.18.0：拆包第九步（feature / 工单命令组）

15 个命令函数（约 700 行）搬进 `whyexist/commands_feature.py`，是到目前为止最大的一次搬迁。

| 内容 | 说明 |
|---|---|
| feature 命令 | declare / register / list / status |
| 变更集 | change-open / change-diff |
| 工单命令 | work-seed / open / claim / finish / judge / list |
| 审计辅助 | `_resolve_subject` / `record_judge_history` / `_require_write` |
| 证据校验 | 抽成 `whyexist/evidence.py`：`sha256_file` / `evidence_qualifies` |
| 身份工具 | `actor_value` 移入 `workflow.py` |

这一轮是拆包以来依赖最杂的一次：`re`、`uuid`、`get_node`、`upsert_node`、`new_token`、
`slice_payload`、`resolve_targets`、`require_*`、`coverage_report` / `conformance_report` /
`drift_report` 都是靠回归报 `NameError` 逐个补上的。教训是：命令层没有干净的依赖闭包，
必须先搬、再让测试列出全部缺失，一次性补完。

边界：其余命令（图写入、咬合、证据、导出、校验、CLI）仍在 `wxg.py`。

版本：契约 `2.17.0` → `2.18.0`；schema 仍为 `9`。测试 `273` 不变。

## 44. 2.19.0：拆包第十步（图写入与证据命令）

upsert-node / upsert-edge / bind / retract / bite / evidence-record / evidence-list
搬进 `whyexist/commands_graph.py`，约 190 行。

| 内容 | 说明 |
|---|---|
| 图写入 | `upsert-node` / `upsert-edge` / `bind`，写入前过 `_require_write` 与 `require_targets` |
| 回撤 | `retract` 级联删除并调 `prune_work_refs` 清理工单引用 |
| 咬合 | `bite` 校验判决集，记录当前代与阶段 |
| 证据 | `evidence-record` / `evidence-list`，有产物时算 SHA-256 |

迁移暴露的隐式依赖：`get_node`、`ensure_feature`、`current_phase`、`dumps`、`uuid`、
`Path`、`get_work`。命令层的依赖闭包不干净，仍靠回归逐个逼出。

边界：导出/校验/doctor/CLI 仍在 `wxg.py`。

版本：契约 `2.18.0` → `2.19.0`；schema 仍为 `9`。测试 `273` 不变。

## 45. 2.20.0：拆包第十一步（编译器命令组）

plan / brief / blind-check / cycles / patch / apply / impact / conflicts 搬进
`whyexist/commands_compiler.py`，约 380 行。

| 命令 | 依赖的纯函数模块 |
|---|---|
| `plan` / `cycles` | `planner` / `cycles` |
| `brief` / `blind-check` | `briefing` / `blind` |
| `patch` / `apply` | `reducer` |
| `impact` | `impact` |
| `conflicts` | `conflicts` |

迁移暴露的隐式依赖：`Path`、`get_work`、`json`、`upsert_node` / `upsert_edge`。

边界：覆盖/一致性/调谐、gate/export、verify/doctor、CLI 仍在 `wxg.py`。

版本：契约 `2.19.0` → `2.20.0`；schema 仍为 `9`。测试 `273` 不变。

## 46. 2.21.0：拆包第十二步（覆盖 / 一致性 / 调谐 / gate）

coverage / conformance / reconcile / serve / gate 搬进 `whyexist/commands_gates.py`。

| 命令 | 说明 |
|---|---|
| `coverage` | 覆盖报告（读 gates.coverage_report） |
| `conformance` | 设计-代码一致性差异 |
| `reconcile` / `serve` | 调谐：补单、解阻塞、回收陈旧 claim |
| `gate` | 交付门；只读，PASS/FAIL 由条件、咬合、覆盖、漂移、conformance 共同决定 |

`cmd_gate` 起初留在 `wxg.py`，但 `commands_gates` 的 `reconcile_feature` 要读 gate 结果，
会形成循环导入；于是把它一起搬过来。迁移还逼出了 `argparse`、`scope_ids`、
`evidence_qualifies`、`work_seed`、`refresh_blocked`、`get_feature`、`utc_now`、`dumps`
八个隐式依赖。

边界：export / verify / doctor / CLI 仍在 `wxg.py`。

版本：契约 `2.20.0` → `2.21.0`；schema 仍为 `9`。测试 `273` 不变。

## 47. 2.22.0：拆包第十三步（export / verify / doctor）

export、role-prompt、contract、verify、doctor 搬进 `whyexist/commands_misc.py`，约 590 行。

| 命令 | 说明 |
|---|---|
| `export` | 按 feature 生成只读设计视图到 `.why-exist/export/<id>/` |
| `role-prompt` | 角色任务书（调 `briefing`） |
| `contract` | 从契约生成文档块 |
| `verify` | 校验生成文档块与导出样例是否漂移 |
| `doctor` | 校验状态库完整性 |

这轮暴露的最关键问题不是缺 import，而是 `cmd_verify` 用 `globals()` 找 `cmd_*` 处理器——
搬进包内后 `globals()` 只剩包内命名空间，于是把每条命令都误报成"没有处理器"。改为从入口
模块 `wxg` 取。其余隐式依赖：`SKILL_DIR`、`Counter`、`ensure_feature`、`scope_ids`、
`get_work`、`make_temp_dir` / `temp_dir`。

边界：CLI 入口（`build_parser` / `main`）仍在 `wxg.py`。

版本：契约 `2.21.0` → `2.22.0`；schema 仍为 `9`。测试 `273` 不变。

## 48. 2.23.0：拆包第十四步（CLI 入口完成）

仓库/导入命令搬进 `whyexist/commands_repo.py`，`build_parser` / `main` 搬进
`whyexist/cli.py`。`wxg.py` 从 4500 行降到 181 行。

`wxg.py` 现在只做三件事：

1. 准备 `sys.path`；
2. 把 `__main__` 注册成 `"wxg"`，让包内 `import wxg` 拿到同一模块对象；
3. re-export 包内符号（旧测试与 `whyexist.legacy` 仍按 `wxg.xxx` 访问）。

| 模块 | 内容 |
|---|---|
| `whyexist/cli.py` | `build_parser` / `main`；命令分派从入口模块取 `cmd_*` |
| `whyexist/commands_repo.py` | init / up / repo-* / import-* / derive / promote / sync / sample |

`main` 的分派原用 `globals()["cmd_" + ...]`，搬进包后 `globals()` 只剩包内命名空间，
改为 `getattr(wxg, ...)`。

迁移暴露的隐式依赖：`argparse`、`ast`、`random`、`scope_ids`、`actor_value`、
`check_kind` / `check_attrs` / `check_node_id`、`insert_work`、`require_role` 等。

边界：`whyexist/legacy.py` 仍是旧入口适配层，后续可删。

版本：契约 `2.22.0` → `2.23.0`；schema 仍为 `9`。测试 `273` 不变。

## 49. 2.24.0：清理收尾（删 legacy、收敛导入）

拆包完成后做两件清理。

**删 `whyexist/legacy.py`**：这层原本是"新代码只经由一个显式文件访问旧入口"的过渡
边界（`wxg.py` 既是脚本又是模块，直接 `import wxg` 会拿到第二份模块对象）。所有函数
已在包内，这条理由消失：

| 旧 | 新 |
|---|---|
| `legacy.connect` / `ensure_db` | `.db.connect` / `.db.ensure_db` |
| `legacy.ensure_feature` / `scope_ids` | `.workflow.*` |
| `legacy.brief_payload` | `.commands_compiler._brief_payload` |
| `legacy.cmd_gate` | `.commands_gates.cmd_gate` |
| `legacy.NODE_KINDS` / `EDGE_KINDS` | `.contract.C.*` |

`engine.py` 改为顶层 import，`test_engine.py` 不再依赖 `wxg` 模块。

**收敛包内导入**：`commands_compiler.py` / `commands_repo.py` 里 10 处函数级
`from whyexist import xxx` 改成顶层相对导入。这些延迟导入原本是绕循环的权宜，
包内结构稳定后没必要保留。

版本：契约 `2.23.0` → `2.24.0`；schema 仍为 `9`。测试 `273` 不变。

## 50. 2.25.0：包内单测与潜伏 bug

新增 `tests/test_package_units.py`，29 个用例直接测包内纯函数层，不经过 CLI subprocess。

| 模块 | 覆盖 |
|---|---|
| `jsonio` | 排序序列化、`@文件`（含 BOM）、空值、坏 JSON、令牌、时间戳 |
| `work` | `work_id`、`target_match`（精确 / 通配 / 非字符串）、`require_targets`、`require_role` |
| `db` | `_mysql_translate` / `_pg_translate` / `_named_params` |
| `graph` | `check_kind` / `check_node_id` / `check_attrs` / `edge_id` |
| `evidence` | `sha256_file` 与 hashlib 对照 |

**抓到的 bug**：`db.py` 的 `_named_params` 用了 `re.sub` 却没 `import re`。因为
MySQL/PG 后端集成测试一直跳过（需要环境变量），这段代码从没被执行过；单测第一次跑就
`NameError`。这正说明"只靠 CLI 端到端测试"的盲区——跳过的后端等于没测。

**另一个坑**：`tempfile.TemporaryDirectory` 在 Windows 受限 token 下会留空 DACL，
清理时 `PermissionError`；测试改用 `whyexist.temp.temp_dir`（`temp.py` 注释里记的是同源问题）。

版本：契约 `2.24.0` → `2.25.0`；schema 仍为 `9`。测试 `273` → `302`。

## 51. 2.26.0：方言转换边界

`_mysql_translate` / `_pg_translate` 是"看着简单、边界一堆"的代码，之前只有两条用例。
这轮按实际 schema 里出现的 SQL 形态补了 8 条。

| 场景 | 断言 |
|---|---|
| MySQL meta upsert | 引号化 `key`/`value`、`ON DUPLICATE KEY UPDATE`、`VALUES(value)`、不留 `ON CONFLICT` |
| MySQL meta 查询 | `SELECT \`value\` FROM meta WHERE \`key\`=?` |
| MySQL `INSERT OR IGNORE` | 转成 `INSERT IGNORE`，不追加冲突子句 |
| MySQL 多行缩进 ON CONFLICT | 正则跨行仍匹配 |
| PG `INSERT OR IGNORE` | 末尾追加 `ON CONFLICT DO NOTHING`，`?` → `%s` |
| PG 尾随分号 | 追加前先剥掉，不产生 `; ON CONFLICT` |

`_named_params` 补了两条：同一占位符重复出现时按出现次数收集；字符串字面量里的
`:name` 会被误当占位符——这是已知限制，当前 schema 不依赖，测试把它钉住避免误以为支持。

结论：转换逻辑对真实 SQL 形态正确，没有新 bug。

版本：契约 `2.25.0` → `2.26.0`；schema 仍为 `9`。测试 `302` → `310`。

## 52. 2.27.0：工单状态机的 DB 层单测

`WorkStateTest` 直接打 SQLite 内存库（`executescript(SCHEMA_SQL)`），不经过 CLI。

| 函数 | 覆盖 |
|---|---|
| `insert_work` | 新建返回 `insert`、merge 追加去重、passed 态拒绝 merge、非 merge 覆盖 `update` |
| `require_token` | 缺失 / 无效 token / 非 claimed 状态 / 正常返回 |
| `append_evidence` | 两次追加同一个 id 不重复 |
| `get_work_by_token` | 按 token 反查工单 |

这些边界之前只有 CLI 端到端测试间接覆盖——CLI 测试要跑完整流程，失败时定位慢。直接
打内存库之后，状态机本身的语义（尤其 merge 的去重与批量写入边界）是独立钉住的。

版本：契约 `2.26.0` → `2.27.0`；schema 仍为 `9`。测试 `310` → `320`。

## 53. 2.28.0：条件链与就绪派生的 DB 层单测

`WorkflowStateTest` 直接打 SQLite 内存库，测条件链本身。

| 函数 | 覆盖 |
|---|---|
| `ensure_feature` | feature 不存在时抛 `Reject` |
| `condition_flags` | 当前代条件行不全时拒绝 |
| `current_phase` | 返回第一个为假的条件；全真时 `Ready` |
| `recompute_ready` | 除 `Ready` 外全真置 1，缺一个置 0 |
| `refresh_blocked` | 依赖全 passed 的 blocked 转 ready；依赖未 passed 保持 blocked |
| `scope_ids` | feature_nodes + `requirement:{feature}:` 前缀 + 当前代工单 `target_ids` 通配展开 |

条件链是 why-exist 的核心状态机：阶段推进、门禁判定、工单派发都读它。之前只有 CLI
流程间接覆盖，现在语义本身被独立钉住。

版本：契约 `2.27.0` → `2.28.0`；schema 仍为 `9`。测试 `320` → `329`。

## 54. 2.29.0：覆盖公式与报告的单测

覆盖判定由一条不等式决定：`p_m·(S-m) ≤ ε`，其中 `m` 是去重覆盖数。`_required_coverage`
用二分求最小可行 `m`。这轮把它和两份报告钉住。

| 用例 | 断言 |
|---|---|
| 零作用域 | 直接返回已覆盖数 |
| 非正 epsilon | 返回已覆盖数（不要求加覆盖） |
| 已满足 | 返回 `covered`，不倒退 |
| 需二分 | `(S=10, a=1, b0=1, ε=0.1)` → 9 |
| 上限 | `(S=10, a=10, b0=10, ε=0.01)` → 10，不超过作用域 |

`coverage_report`：空咬合时所有阶段 `covered=0`；默认 `ε=1.0` 较宽松，`n_required`
可以是 0、`met` 为真；`ε=0.001` 时每阶段至少要求 1 个覆盖且 `met=False`，`next`
指向第一个未达标阶段。

`drift_report`：空图 `count=0`、未设上限时 `enforced=False`。

版本：契约 `2.28.0` → `2.29.0`；schema 仍为 `9`。测试 `329` → `338`。

## 55. 2.30.0：设计-代码一致性报告的单测

`conformance_report` 报四类差异，之前完全靠 CLI 测试。这轮用内存库逐类钉住。

| 差异 | 判定 | 测试数据 |
|---|---|---|
| 锚点缺失 | 设计元素没有 `maps_to` 到带 `repo`/`path` 的代码节点 | 只有 component → 报告；补 `maps_to` 后消失 |
| 代码孤立 | 有 `repo`/`path` 的 operation 未被任何 `maps_to` 指向 | 只报告，不计入 violation |
| 结构缺支撑 | `depends` 边找不到对应代码调用 | 两个已锚 component + `depends` → 1 |
| 未声明耦合 | 跨设计单元的代码调用没有 `depends` 声明 | `calls` 跨两个 component → 1；补 `depends` 后 0 |
| 测试覆盖 | `use_case` 没有 `verifies` 边 | 未验证 → 1；补 `verifies` 后 0 |
| 截断 | `limit` 只截列表 | 3 个缺失、`limit=1` → 列表 1、计数 3、`truncated` 真 |

写测试时踩到一次自己的断言错误：`violations` 是四类之和，只造"缺支撑"数据时锚点缺失也在
计，断言 1 实际 3。补锚点后才是干净的单类验证——这也说明报告字段之间是叠加关系，
读结果时要看分类计数而不是只盯总数。

版本：契约 `2.29.0` → `2.30.0`；schema 仍为 `9`。测试 `338` → `348`。

## 56. 2.31.0：`feature-status` 的 `phase` 字段

端到端演练时发现：要知道 feature 当前走到哪个阶段，得从 `conditions` 里自己找第一个为 0
的条件。机器读没问题，人读不直观。

现在 `feature-status` 直接返回 `phase`：

- 第一个为假的条件名（如 `ArchitectureReconciled`）；
- 全齐时是 `Ready`；
- 与 `current_phase` / 门禁判定走同一套条件链，不会出现"两处算法不一致"。

只加字段、不改 `conditions` 结构，旧调用方不受影响。

版本：契约 `2.30.0` → `2.31.0`；schema 仍为 `9`。测试 `348` → `349`。

## 57. 2.33.0：JSON 参数的报错

`--data` / `--changed` 这类参数同时接受 JSON 字面量与 `@文件`。原来解析失败只报
`JSON 解析失败：Expecting value`，看不出是"格式不对"还是"参数写错了"——复用 httpie
复验时第一次就撞上。

现在：

| 场景 | 报错 |
|---|---|
| 裸字符串当 JSON | 参数不是合法 JSON：期望数组/对象字面量（如 `'["id"]'`）或 @文件（第 1 行第 1 列：Expecting value） |
| `@文件` 内容坏 | 文件内容不是合法 JSON：`<路径>`（第 N 行第 M 列：…） |
| `@文件` 不存在 | JSON 文件无法读取：`<路径>`（原因） |

行为变化：空字符串不再返回 `None`，直接报错——这两个参数在契约里都是必填，返回 `None`
只会把错误推到下游。

版本：契约 `2.32.0` → `2.33.0`；schema 仍为 `9`。测试 `349` → `351`。

## 58. 2.34.0：`plan --level code` 的提示

httpie 复验时 `plan --level code` 返回 8 节点 0 边。不是 bug：`scope_ids` 给的是设计
组件，代码层聚合需要作用域里真的有 operation/classifier 节点，否则代码边一条都进不来。
但输出看起来像"没有并行空间"，容易被当成结论。

现在 `--level code` 且作用域内没有代码层节点时，结果带一条 `hint`：

> 作用域内没有代码层节点，代码层边为 0。先把代码节点纳入 feature 作用域
> （如 `work-open --target-ids '["operation:*"]'`）。

只加字段、不改既有字段。`--level auto` 不受影响（它本来就会在没有设计层边时退到代码层）。

版本：契约 `2.33.0` → `2.34.0`；schema 仍为 `9`。测试 `351` → `352`。

## 59. 2.35.0：把作用域语义写进文档

`plan --level code` 的坑（作用域不含代码节点 → 0 边）在 2.34.0 加了 `hint`，但这套
语义不该只靠踩坑学会。这轮补进 `SKILL.md` 的「已知边界」：

> `--level code` 只分析作用域内**已包含**的代码节点；作用域只有设计元素时会返回 0 边
> （结果带 `hint`），需先用 `work-open --target-ids '["operation:*"]'` 把代码节点并进来。

同时修掉一条过时的边界描述：`SKILL.md` 还写着"`wxg.py` 仍是主实现、`whyexist/legacy.py`
是隔离层"，但 `legacy.py` 在 2.24.0 已删、`wxg.py` 现在是 181 行薄入口。

版本：契约 `2.34.0` → `2.35.0`；schema 仍为 `9`。测试 `352` 不变。

## 60. 2.36.0：已知边界审计

上一轮撞见一条过时边界（`legacy.py`），这轮把「已知边界」23 条逐条对照实现。

| 结果 | 条数 | 说明 |
|---|---|---|
| 准确 | 22 | 导入器、测试执行、状态库信任、coverage/drift、reconcile、变更集、回扫、conformance、plan（2.35.0 刚补）、brief、blind-check、up/Engine、impact、apply、derive、SQLite/MySQL/PG、serve、feature-register |
| 修正 | 1 | `gate` 的描述漏了**施工标记**与**作用域内 stale 节点**——这两项都会让 gate FAIL |

`gate` 的实际校验项：条件、咬合（含 pattern）、施工标记、stale、evidence、coverage、
drift、conformance（开启时）。

结论：拆包和功能迭代之后，文档主体跟得上；漂移集中在"某个命令后来又加了检查项"这种
局部补丁上——`gate` 就是典型，2.2.0 加 stale、2.5.0 加施工标记，边界描述都没跟着改。

版本：契约 `2.35.0` → `2.36.0`；schema 仍为 `9`。测试 `352` 不变。

## 61. 2.37.0：`gate` 的 `checks` 列表

`gate` 的判定是九道闸门依次过，任一项不过就 FAIL。原来输出只有结果和细节字段，人得自己
对是哪一项卡的；文档也会漏写检查项（2.36.0 就修过一次）。

现在结果带 `checks`，按判定顺序列出：

| 顺序 | name | 不过的含义 |
|---|---|---|
| 1 | `bites` | 作用域内节点最新咬合为 UNNECESSARY/HOLLOW |
| 2 | `pattern` | 模式缺 applicability/not_applicable 或没挂到具体元素 |
| 3 | `drift` | UNMAPPED/DOC-ONLY 节点数超过上限（未设上限时恒过） |
| 4 | `construction` | 仍有 construction=true 的施工中节点 |
| 5 | `stale` | 作用域内有代码里已不存在的旧锚点 |
| 6 | `conformance` | 设计-代码一致性有差异（未开启时恒过） |
| 7 | `conditions` | 8 个条件未齐 |
| 8 | `evidence` | 需要证据的条件已为真但没有有效 evidence |
| 9 | `coverage` | 咬合覆盖未达标（未启用时恒过） |

第一个 `ok=false` 就是 FAIL 原因。httpie 的实测输出：`stale=false`、`conditions=false`，
其余为真——一眼看出卡在哪。

版本：契约 `2.36.0` → `2.37.0`；schema 仍为 `9`。测试 `352` → `353`。

## 62. 2.38.0：`--changed` 的逗号分隔写法

`impact --changed` 之前只收 JSON 数组或 `@文件`。写一个 id 要拼 `'["a:b"]'`，写三个要
拼 `'["a:b","c:d","e:f"]'`——不自然，也容易漏引号。

现在裸 id 支持逗号分隔：

```
--changed component:httpie:httpie.cli,component:httpie:httpie.output
```

判定规则：首字符是 `[` / `"` / `{` / `@` 时按 JSON 解析（数组或文件），其余按逗号分隔。
JSON 字符串（`"nope"`）和对象（`{"a":1}`）仍然报"必须是字符串数组"——这条是旧测试
抓出来的：最初只判断 `[` 和 `@`，`"nope"` 会被当成裸 id 收下。

版本：契约 `2.37.0` → `2.38.0`；schema 仍为 `9`。测试 `353` → `355`。

## 63. 2.39.0：id 列表参数统一

2.38.0 只让 `impact --changed` 支持逗号分隔，其余 id 列表参数还是只收 JSON。这版统一。

新增 `jsonio.load_id_list`：

```python
def load_id_list(text: str) -> list[str]:
    stripped = text.strip()
    if stripped[:1] in ("[", "@", '"', "{"):
        value = load_json_arg(stripped)
        ...
    return [item.strip() for item in stripped.split(",") if item.strip()]
```

| 命令 | 参数 |
|---|---|
| `slice` | `--ids` |
| `retract` | `--node-ids` / `--edge-ids` |
| `work-open` | `--target-ids` |
| `impact` | `--changed` |

四处调用与契约 help 一起改。`--acceptance` / `--constraints` / `--spec` / `--data` 不动：
前三者是"字符串数组但内容可能含逗号"或对象，`--data` 本来就是对象，逗号分隔无意义。

版本：契约 `2.38.0` → `2.39.0`；schema 仍为 `9`。测试 `355` → `357`。

## 64. 2.40.0：最短路径文档

`SKILL.md` 的快速开始是分段的——每条命令都对，但新人得自己在脑子里拼出完整流程。
补一节"从零到 `gate PASS` 的最短路径"：

1. 一条命令起步：`up --template standard`（建库 + 登记示例仓 + 声明 demo feature + 跑 gate）；
2. 之后只剩一个循环：**每个条件 = 一次工单生命周期**
   `work-open`（并写入边界）→ `work-claim`（拿 token）→ 写图 → `work-finish` → `work-judge`；
3. 八个条件按顺序推进，`gate` 的 `checks` 直接指出下一个卡在哪项。

这样读的人先拿到"心智模型"，再去查具体命令，比从头读 60 行示例快。

版本：契约 `2.39.0` → `2.40.0`；schema 仍为 `9`。测试 `357` 不变。

## 65. 2.41.0：照文档实跑，修掉两处误导

2.40.0 写完最短路径后，在干净目录里只按 `SKILL.md` 操作，从 `up` 走到 `gate PASS`。
流程确实能通，但撞出两个问题——都是文档写对了、`up` 的建议写错了。

| 问题 | 现象 | 修法 |
|---|---|---|
| `up` 的 `next` 第一条 | 建议 `work-claim --role scan`，但 scan 工单要到 `import-file --prepare` 才创建，照做报"没有可领的 ready 工单" | 第一条改为 `import-file --file <源码> --feature <id> --prepare`，并注明工单在这步创建 |
| `implement-test` 的 claim | 不改产品代码的角色默认被拒，文档没提 | `SKILL.md` 最短路径补一句"claim 时加 `--allow-product-code`" |

测试把 `up.next[0]` 钉死为必须含 `--prepare`，防止再回退。

版本：契约 `2.40.0` → `2.41.0`；schema 仍为 `9`。测试 `357` 不变。

## 66. 2.42.0：文档一致性检查脚本

2.41.0 修的两处误导，是"照文档手动跑"发现的。手动一次性的东西容易忘，这版固化成
`tools/doc_flow.py`。

它不读实现、不 import 内部模块，只把 `SKILL.md` 最短路径的命令序列原样执行：

| 步骤 | 断言 |
|---|---|
| `up --template standard` | 返回 gate 结果；`next[0]` 必须是 `import-file --prepare` |
| `import-file --prepare` | 创建了 scan 工单 |
| scan 链 | claim → write → finish → judge 全通 |
| 六阶段 | open → claim → finish → judge；`implement-test` 带 `--allow-product-code` |
| evidence / observe | 记录证据后 observe 单通过 |
| `gate` | PASS，且 `checks` 全过 |
| `export` | 6 个视图 |

价值在于补测试盲区：单元测试不读文档，端到端测试直接用正确顺序，两边都抓不到"文档写的
顺序和实现不一致"。建议改 CLI 表面后、发布前各跑一次。

同时更新了 `SKILL.md` 文件表——`scripts/wxg.py` 的旧描述还是"CLI 主实现"，补上
`scripts/whyexist/` 与两个 `tools/` 脚本。

版本：契约 `2.41.0` → `2.42.0`；schema 仍为 `9`。测试 `357` 不变。

## 67. 2.43.0：`quality.md` 对齐

`references/quality.md` 是提交检查表，但"当前版本状态"停在 1.4.0 / 104 用例，还重复维护了
一份「已知边界」清单。

| 问题 | 修法 |
|---|---|
| 版本状态过时（1.4.0 / 104 用例） | 改为 2.42.0 / schema 9 / 357 用例，历史指向 `CHANGELOG.md` |
| 边界清单与 `SKILL.md` 重复 | 删掉副本，指向 `SKILL.md`「已知边界」——单一来源 |
| 没有 doc_flow 检查项 | §1 加"doc_flow 全绿"，§3 加"改 CLI 表面后必须跑" |

重复维护的清单必然漂移：2.36.0 修 `gate` 描述时，两处里只改了一处。这版把边界收成一处，
以后只改 `SKILL.md`。

版本：契约 `2.42.0` → `2.43.0`；schema 仍为 `9`。测试 `357` 不变。

## 68. 2.44.0：design.md 的阅读指引

扫完剩下的 `references/*.md`：

| 文件 | 结论 |
|---|---|
| `patterns.md` | 没有具体命令引用；`applicability` / `not_applicable` / `applies` 的描述与 gate 实现一致，不动 |
| `contract.md` | 生成块，`verify` 逐字节校验，不用管 |
| `design.md` | 旧版本号是历史记录，保留；但开头缺"怎么读"的说明 |

`design.md` 是**按版本追加的演进记录**：§14 讲 0.9.0 的回扫、§20 讲拆包刚开始时的
`legacy` 隔离层——都写的是"那一版为什么这么改"。但读者翻到 §14 看到 `whyexist/legacy.py`
会以为现在还有这个东西（它在 2.24.0 已删）。

开头补一段「怎么读」：当前行为以 `SKILL.md` / `contract.md` / `CHANGELOG.md` 顶部为准，
这份文件负责"为什么"、不负责"现在是什么"。

版本：契约 `2.43.0` → `2.44.0`；schema 仍为 `9`。测试 `357` 不变。

## 69. 2.45.0：preflight 脚本

发布前要跑五件事：回归测试、文档一致性、`verify`、`doctor`、打包。之前每次零散跑，
容易漏掉其中一项（`doc_flow` 尤其容易忘，它不在测试套件里）。

`tools/preflight.py` 把它们串起来：

| 步骤 | 内容 |
|---|---|
| 回归测试 | `unittest discover`，打印 `Ran N tests` |
| 文档一致性 | `doc_flow`：照 `SKILL.md` 走到 `gate PASS` |
| 契约校验 | `verify`，断言 `ok=true` |
| 状态库体检 | 临时新库 `up` 后跑 `doctor`，断言 `ok=true`（顺带验证 `up` 本身） |
| 打包（`--release`） | `build_release`，打印版本与文件数 |

任一步失败立即退出并打印尾部日志；全部通过时给一行汇总。`doctor` 用临时库，跑完即删，
不污染工作区。

版本：契约 `2.44.0` → `2.45.0`；schema 仍为 `9`。测试 `357` 不变。

## 70. 2.46.0：陌生仓实验（itsdangerous）

拿 `pallets/itsdangerous`（8 个扁平 Python 文件）走一遍：`import-repo` → 161 节点 /
188 边，然后 `derive` / `cycles` / `plan` / `conformance`。

| 命令 | 结果 | 读法 |
|---|---|---|
| `plan --include-unmapped` | 162 节点 / 142 边 / 7 层 / 无环 / 并行度 116 | 准的：内部依赖确实稀疏；并行度是代码层节点上界，不是"116 件事" |
| `cycles` | 0 环 | 代码层无循环依赖 |
| `conformance` | violations 0 / anchors 0 / code_orphans 72 | 把"设计还没做"量化成 72，比空话有用 |
| `derive` | **1 个组件**（depth 1 和 2 都一样） | 单层包没有子目录可分 |

最后一条是这轮改的东西：`derive` 返回 `components <= 1` 时带 `hint`，说明目录层级不足以
分组、`--depth` 只在目录多于一层时才有区别。不改分组结果（1 是对的），只防止把"1"读成结论。

结论：why-exist 在陌生仓上的第一层价值是**可计算的规模事实**（节点/边/层/环/孤立数），
第二层价值（设计粒度）依赖目录结构有多层——扁平仓拿不到。

版本：契约 `2.45.0` → `2.46.0`；schema 仍为 `9`。测试 `357` 不变。

## 71. 2.47.0：相对导入与 derive 的 depends

2.46.0 在 itsdangerous 上实验时 `derive` 只有一个组件，看不出问题；换到 flask
（`src/flask/` 下有 `json/`、`sansio/` 两个子包）才暴露：**3 个组件、0 条依赖**。

原因是 `_import_file_pairs` 只处理 `node.level == 0` 的绝对导入，而 flask 内部全用
`from .app import Flask` 这类相对导入。Python 包里相对导入很常见，这条限制让 `derive`
的 `depends` 在最需要它的场景下永远为空。

补上三种形态：

| 写法 | 解析为 |
|---|---|
| `from . import helper` | `<当前包>/helper.py` |
| `from .json import dumps` | `<当前包>/json/__init__.py` |
| `from ..base import thing` | 上跳一层后的 `base.py` |

flask 实测：`depends` 从 0 变 6，每条带 `(源文件, 目标文件)` 证据；顺带看出
`flask` / `flask.json` / `flask.sansio` 三方**互相依赖**——这种结论靠读代码不容易快速得出。

版本：契约 `2.46.0` → `2.47.0`；schema 仍为 `9`。测试 `357` → `361`。

## 72. 2.48.0：环的形态

flask 那次看出一个共同点：它的环是 `flask` / `flask.json` / `flask.sansio`，httpie 那次是
`httpie` / `httpie.cli` / `httpie.output`——两个仓、不同规模，都是**包与子包互相依赖**。
但 `cycles` 的输出只有成员和边，看不出这个结构特征。

现在每个环带 `shape`：

| shape | 判定 | 含义 |
|---|---|---|
| `parent-child` | 环内存在 `b.startswith(a + ".")` 的 component 名 | 子包被顶层设施反依赖，分层没切开 |
| `sibling` | 其余情况；非 component 节点混入也归此类 | 平级模块互调 |
| `self-loop` | 单节点自环 | 节点依赖自己 |

判定只看 component 名的前缀，不做语义猜测。两个仓实测都判为 `parent-child`，印证了
"同一种结构问题"这个判断。

版本：契约 `2.47.0` → `2.48.0`；schema 仍为 `9`。测试 `361` → `366`。

## 73. 2.49.0：形态接成建议

`shape` 只是标签，读者还得自己翻译。这版给每个环加 `guidance`：

| shape | 建议 |
|---|---|
| `parent-child` | 让子包单向依赖父包（或把共用设施下沉），**不要用断边掩盖**——断边只改可达性，不改变分层方向 |
| `sibling` | 断代价最小的一条，或把双方共同依赖的部分抽成更底层模块 |
| `self-loop` | 查递归写入 / 自引用边 |

关键在 `parent-child` 那条：两种形态的**正确处理不一样**。父子包互依赖如果用断边处理，
环是没了，但反向依赖还在，只是被藏起来了——下一个人重新扫一遍图还会看到。所以
`guidance` 直接说"不要断"，而不是让读者自己从 `shape` 推断。

flask 实测输出：

```
shape= parent-child
guidance= 父子包互依赖：让子包单向依赖父包（或把共用设施下沉到底层），不要用断边掩盖；
          断边只改可达性，不改变分层方向。
```

版本：契约 `2.48.0` → `2.49.0`；schema 仍为 `9`。测试 `366` → `368`。

## 74. 2.50.0：`plan` 的 bottleneck

`parallelism` 一个数字有两种来源：

| 场景 | 值 | 含义 |
|---|---|---|
| 无环 | 最大反链（Dilworth） | 最多能同时做几件事 |
| 有环 | 最大强连通分量大小 | 环里几个节点必须串行 |

读者看 `parallelism=3` 分不清是哪一种，更分不清 3 意味着"只能并行做 3 件"还是
"有个 3 节点的环卡着"。加 `bottleneck` 直接说明：

```
parallelism= 3
bottleneck= 受限于最大环：3 个节点必须串行（flask, flask.json, flask.sansio）
```

无环时写"最大反链 N 个节点可同时做（M 层，最宽 K 个）"；只有单点自环时写
"不阻断并行，但拓扑分层不可用"。

版本：契约 `2.49.0` → `2.50.0`；schema 仍为 `9`。测试 `368` → `371`。

## 75. 2.51.0：`impact` 的深浅之分

改一个节点，`affected` 列出所有受波及的组件，但没区分"直接依赖它"和"隔了几层才被波及"——
判断改动代价时这是两回事。

`impact` 加两个字段，用反向 BFS 的最短跳数拆：

| 字段 | 含义 |
|---|---|
| `affected` | 完整波及面（不变，含 changed 自身） |
| `direct` | 一跳内直接依赖 changed 的节点 |
| `indirect` | 隔两跳及以上才被波及的节点 |

httpie 实测，改 `httpie.cli`：

```
affected=11
direct=5    extras.scripts, httpie, httpie.manager, httpie.output, tests
indirect=5  extras.packaging, httpie.internal, httpie.legacy, tests.fixtures, tests.utils
```

菱形依赖按最短跳归类（`d` 经 `b` 或 `c` 都是 2 跳，算 `indirect`）。

版本：契约 `2.50.0` → `2.51.0`；schema 仍为 `9`。测试 `371` → `374`。

## 76. 2.52.0：feature-status 的体积

最近几轮一直在给输出加解释字段，但没量过输出本身多大。量了一下：flask-lab 的
`feature-status` 有 **74KB**，而它只有 8 个工单——`work_items` 一项占 72.5KB。

原因：scan 工单的 `target_ids` 有 1186 个节点 id、6.8 万字符，被原样塞进概览视图。

概览视图不该塞完整列表。改成：

| 字段 | 内容 |
|---|---|
| `target_count` | 该工单覆盖多少个节点 |
| `target_sample` | 前 5 条，够看出是哪类节点 |
| `depends_on` | 从 JSON 字符串解析成列表（更容易读） |

要看全量用 `slice --work <id>`。改完输出 74KB → **6KB**。

顺手记一个坑：验证时我用 `id.endswith(':scan')` 找 scan 工单，结果匹配到了
`work:...:audit:work:...:scan`（audit 工单也以 `:scan` 结尾），差点以为裁剪逻辑有 bug。

版本：契约 `2.51.0` → `2.52.0`；schema 仍为 `9`。测试 `374` → `375`。

## 77. 2.53.0：输出体积与耗时的横向检查

2.52.0 发现 `feature-status` 有 74KB 输出，顺手把其他命令在 flask-lab（1186 节点）上
也量了一遍：

| 命令 | 输出 | 耗时 |
|---|---|---|
| `feature-status` | 6 KB（修复前 74 KB） | 240 ms |
| `conformance` | 4.5 KB | 289 ms |
| `gate` | 3 KB | — |
| `coverage` | 1.5 KB | — |
| `drift` | 1.2 KB | — |
| `doctor` | 0.3 KB | — |
| `plan` | — | 252 ms |
| `cycles` | — | 244 ms |

结论：体积失控只有 `feature-status` 一个（已修），其余要么有 `limit` 截断（conformance /
find / slice），要么数据量本来就小。耗时全部在 300ms 内（含 Python 启动），没有需要优化的
热点。

`export` 的 6 个视图文件 0.2–0.3 KB——flask 还没建设计节点，视图是空的；这是"设计还没做"
的正常表现，不是导出缺陷。

版本：契约 `2.52.0` → `2.53.0`；schema 仍为 `9`。测试 `375` 不变。

## 78. 2.54.0：sync 报告的真实性验证

之前只"跑过" `sync` 看到有输出，没验证输出对不对。bad-boids 的 git 正好留着重构前的版本
（HEAD 是旧代码，工作区是新代码），可以真对比一次。

脚本：`refactor-lab/verify_sync.py`。

| 步骤 | 结果 |
|---|---|
| HEAD 版本建图 | 6 节点 / 5 边 |
| 覆盖为工作区版本 | boids.py 重写 + render.py 新增 |
| `sync` | missing=3 / new=28 / changed=3 |

逐项核对：`new` 里 12 个节点属于 `render.py`（新增文件）；`missing` 里 3 个是 boids.py 的
旧节点（`len` / `range` / `update_boids`）；`changed` 是这三个节点在新代码里的行号变化。
**报告与实际改动一致**。

顺带发现一个噪声：`changed` 里的 `len` / `range` 是内置调用的 unmapped 聚合节点，它们的
行号变化不算设计改动。现在每项带 `unmapped` 标记，另加 `changed_unmapped_count`，
设计层关心的改动数是两者之差。

版本：契约 `2.53.0` → `2.54.0`；schema 仍为 `9`。测试 `375` 不变。

## 79. 2.55.0：conformance 与 derived 依赖

flask 上跑 `derive --apply` 之后，`conformance` 报 `missing_backing=6`——6 条 derive 出来的
depends 全被判定"没有代码支撑"。

**错在哪**：`missing_backing` 的判定是"这个 depends 边能不能在 `code_map` 里找到对应的代码
调用"，而 `code_map` 只由 `maps_to` 建立。derived 组件没有 `maps_to`（derive 只给组件候选，
不锚定到具体代码节点），所以它的依赖永远找不到支撑。

**但 derive 的 depends 恰恰是最有依据的**：它是从 import 解析出来的，写库时就在
`attrs.x_evidence` 里记了来源文件对。忽略这个证据，等于把最可信的依赖报成最可疑的。

修法：depends 边的 `attrs.x_evidence` 非空时直接视为有代码依据。

flask 实测：`violations` 9 → 3，`missing_backing` 6 → 0。剩下的 3 个 `missing_anchors` 是
derived 组件确实没有 `maps_to`，这个报告是对的。

版本：契约 `2.54.0` → `2.55.0`；schema 仍为 `9`。测试 `375` → `376`。

## 80. 2.56.0：conformance 的孤立提示

flask 上 `conformance` 报 `code_orphans=379`——379 个代码节点"没被任何设计覆盖"。数字吓人，
但根因是 derived 组件还没有 `maps_to`：derive 只按目录推组件候选，不锚定到具体代码节点。
这不是"代码没被设计覆盖"，是"设计还没锚定"。

加 `hint`：存在 derived 组件且有孤立节点时说明这一点，并指出先 `promote` 补 `maps_to`
再看这个数。

| 场景 | 行为 |
|---|---|
| flask（3 个 derived 组件、379 孤立） | 出提示 |
| httpie（全 declared、0 孤立） | 无提示 |

版本：契约 `2.55.0` → `2.56.0`；schema 仍为 `9`。测试 `376` → `378`。

## 81. 2.57.0：doctor 的能修 / 不能修

`doctor --fix` 只清理悬空引用与陈旧 token（I9 里写了"不替人裁决"），但输出里没有标记，
读者容易以为 `--fix` 能解决所有问题——尤其 `legacy-identity` 这种，跑完 `--fix` 还在，
会以为工具坏了。

把边界写进契约：`DOCTOR_FIXABLE_CHECKS` 列出 7 类可自动修的：

| 可修 | 不可修（只报） |
|---|---|
| dangling-bite / orphan-edge / feature-node-missing | legacy-identity（修了等于伪造审计身份） |
| work-target-missing / work-evidence-missing | condition-rows / missing-generation-conditions |
| token-on-inactive / meta-version | audit-* / judge-history-* / evidence-* / pattern-unjustified 等 |

`doctor` 输出：每个 issue 带 `fixable`，汇总加 `fixable_count` / `unfixable_count` /
`unfixable_checks`。

版本：契约 `2.56.0` → `2.57.0`；schema 仍为 `9`。测试 `378` 不变。

## 82. 收尾回顾：五十个版本学到什么

2.7.0 到 2.57.0。按主题分四段，每条都是踩过的坑。

### 拆包（2.7.0 → 2.24.0，14 步）

`wxg.py` 4500 行 → 181 行，`whyexist` 包二十多个模块。

**一、整段搬运的依赖不可见。** 每搬一段，全量测试都会报 1~3 个 `NameError`：`re` /
`uuid` / `Path` / `get_node` / `work_id` / `insert_work`……它们是函数体里的隐式依赖，读代码
看不出来。命令层最严重——2.18.0 一次补了 12 个。

**二、替换范围会吞掉前一次的产物。** 按行号范围替换时，如果范围覆盖了上一轮插入的
re-export，它会无声消失。出现了**两次**（2.15.0、2.18.0），都是全量测试报
`KeyError: 'cmd_xxx'` 才发现。

**三、`globals()` 在包内失效。** `cmd_verify` 和 `main` 都用 `globals()["cmd_" + name]` 找
处理器，搬进包后命名空间变了，全部误报"命令没有处理器"。改成从入口模块取。

**四、循环导入不总是显式的。** `cmd_gate` 原本留在 `wxg.py`，但 `commands_gates` 的
`reconcile_feature` 要读 gate 结果——留着就是环，只能一起搬。

### 测试补盲区（2.25.0 → 2.30.0）

新增 `tests/test_package_units.py`（84 个用例），直接测纯函数层。第一次跑就抓到 `db.py`
缺 `import re`——`_named_params` 从未被执行过，因为 MySQL/PG 后端集成测试一直跳过。

**五、跳过的测试等于没测。** 端到端测试再全，跳过的后端路径就是盲区。

### 验证要真跑（2.41.0 / 2.54.0 / 2.55.0）

- **照文档跑**：发现 `up` 的 `next` 第一条建议 `work-claim --scan`，但 scan 工单要到
  `import-file --prepare` 才创建。文档对了、`up` 的建议错了——单元测试不读文档，端到端
  测试直接用正确顺序，两边都抓不到。固化成 `tools/doc_flow.py`。
- **拿真实重构验证**：bad-boids 的 git 留着重构前后两版，`sync` 报的 missing / new /
  changed 与真实改动一致；顺带发现 unmapped 节点的行号噪声。
- **拿真实仓库验证**：flask 上 `conformance` 报 6 条"无支撑"，但 derive 的 depends 自带
  `x_evidence`——最可信的依赖被报成最可疑的。

**六、报告的真实性只能拿真实数据验。** 测试里的 fixture 永远是对的。

### 输出可读性（2.34.0 → 2.57.0）

给结构化输出加解释字段：`plan.bottleneck`、`cycles.shape` / `guidance`、
`impact.direct` / `indirect`、`derive.hint`、`conformance.hint`、`doctor.fixable`、
`feature-status.phase`。

**七、一个数字有两种来源时，必须写明。** `parallelism` 无环时是最大反链、有环时是最大环
大小；只给数字，读者会按自己以为的那种理解。

**八、能自动修和不能自动修要分开说。** `doctor --fix` 修不了的 `legacy-identity` 如果混在
问题列表里，用户会以为工具坏了。

### 还能做的

导入器跨包别名仍会漏；`derive` 在扁平仓上没信息量；跨主机共享 SQLite 不支持。完整清单见
`SKILL.md`「已知边界」（单一来源）。

## 83. 2.59.0：报告自洽性工具

前面三次"真实数据验证"都是临时脚本：`doc_flow.py`（照文档跑）、`verify_sync.py`
（bad-boids 重构前后对比）、flask 上的手工 conformance 检查。换一个仓就得重写。

其中**可自动化的部分**是自洽性：同一份图，不同命令给出的数字应该互相吻合。
`tools/verify_reports.py --root <库> --feature <id>` 检查 6 条：

| 断言 | 抓什么 |
|---|---|
| `plan.acyclic` ⇔ `cycles.cycle_count == 0` | 两个命令对"有没有环"看法矛盾 |
| `plan.cyclic_components` == `cycles.members` | 环的成员不一致 |
| `cycles.node_count` ≤ `plan.node_count` | 子集关系被破坏 |
| `conformance.structural.depends` == 图内 depends 边数 | 报告与库脱节 |
| `impact.affected` == `changed` ∪ `direct` ∪ `indirect` | 深浅拆分漏节点 |
| `status.scope_size` == `scope_ids` | 作用域口径不一致 |

**口径问题**：`plan` 的 level 是 auto——有设计层 depends 用设计层，否则退代码层；`cycles`
永远只看设计层。所以 plan 用代码层时跳过环断言并打印说明，而不是硬比出假失败。这个坑是
itsdangerous 上试出来的（plan=162 节点 / cycles=0，不是 bug）。

三个库实测全 PASS。

## 84. 2.60.0：preflight 补齐

`preflight` 原本是"测试 + doc_flow + verify + doctor"。`verify_reports` 是 2.59.0 才加的，
独立工具，发布前容易忘。

现在多一步：临时 `up --template standard` 建小库 → `verify_reports` → 断言 PASS。

小库只有 demo 仓（1 节点），断言覆盖面有限，但至少保证工具本身能跑通、不会因为代码变动
静默失效。真实仓的深度检查仍在 `refactor-lab` 里手工做。

当前 preflight 五步：回归测试 / 文档一致性 / 契约校验 / 状态库体检 / 报告自洽性
（`--release` 再加打包）。

## 85. 2.61.0：verify_reports 的 --repo 模式

`verify_reports` 原本只检查"已有状态库"，要检查一个源码仓得手工走一遍 init / repo-add /
declare / import-repo / claim / derive。换一个仓重来一遍。

加 `--repo <路径>`：自动建临时库、扫描、`derive --apply`（`--depth` / `--exclude` 透传）、
跑 6 条断言，跑完即删。

实测三条：flask（24 文件 / 1186 节点 / 3 组件 6 依赖）、itsdangerous（8 / 161 / 1 组件）、
httpie `--depth 2`（133 / 3285 / **7 组件 21 依赖 1 环**）——最后这个数字与之前手工在
`httpie-lab` 里跑出来的完全一致，说明自动链路和手工操作等价。

## 86. 2.62.0：批量扫仓抓到的 derive bug

`verify_reports --repo` 让"扫一个仓"变成一条命令。用它扫了 click / tabulate / rich：

| 仓 | 规模 | 结果 |
|---|---|---|
| click | 91 文件（17 在 src/click） | 1 组件，4 条 PASS |
| tabulate | 13 文件 | 1 组件，4 条 PASS |
| rich | 213 文件 | `derive --apply` **失败** |

rich 的报错是 `边的 src 不存在：component:repo:tools`。

**原因**：`derive_components` 有两条生成 depends 的路径——

- 节点边（`calls` / `reads` / `writes`）：端点经 `node_to_component` 映射，天然只含已分组
  节点，不会出错；
- 文件依赖（import 解析）：直接 `group_key(file, depth)` 算出组件 id，**没有检查这个组件
  是否真的存在**。rich 的 `tools/` 目录下有 .py 被 import 解析引用，但没有代码节点入图，
  于是 depends 指向了一个永远不会被写入的组件，`upsert-edge` 校验端点时拒绝。

修法：两条路径统一——两端都在 `membership` 里才生成 depends。

修完 rich 从"apply 失败"变成 2 组件 / 2 依赖 / 1 环、6 条断言全 PASS。

**教训**：同一个函数里两条数据路径，一条天然安全（有映射表兜着）、另一条没有——这种
不对称最容易漏。批量扫仓比逐个手工验证更容易撞上它。

## 87. 2.63.0：仓画像

批量扫仓时只看断言 PASS/FAIL，看不到规模与噪声比例。`verify_reports --repo` 加一段画像：
`节点数 / 边数 / unmapped 占比 / 组件数`，以及 `孤立 / 代码节点（占比）`。

实测 6 个仓：unmapped 占比稳定在 **50~58%**（内置与外部调用），孤立率 **100%**——后者是
derived 组件还没有 `maps_to`（`contains` 是成员关系，不是锚定），属已知表现。

结论：没有异常仓，导入器的 unmapped 处理是稳定的。

## 88. 2.64.0：孤立节点的两种含义

`code_orphans` 在 flask 上是 379、rich 上是几百——数字看着像"代码大面积没被设计覆盖"，
实际是 derive 之后还没 promote 的正常中间态：derive 写了 `contains`（组件包含成员），但
没有 `maps_to`（设计锚定），conformance 只认后者。

拆成两个数：

| 字段 | 含义 | flask 实测 |
|---|---|---|
| `code_orphan_count` | 未被 `maps_to` 指向的代码节点（总数） | 379 |
| `unanchored_count` | 其中落在 derived 组件 `contains` 范围内的 | **379** |
| `truly_orphan_count` | 完全没有任何设计覆盖的 | **0** |

`hint` 随改：不再说"N 个节点全算孤立"，而是"379 个在 derived 组件里（正常中间态）、
0 个完全没覆盖"。

这才是可比较的口径：`truly_orphan_count` 才是"设计覆盖不足"的度量；
`code_orphan_count` 在 derive 之后必然接近 100%，没有比较意义。

## 89. 2.65.0：真孤立的来源

2.64.0 之后，rich 上 `truly_orphan_count=844`——按新口径这是"844 个代码节点完全没被设计
覆盖"，听起来像大问题。

查下来：844 个全在被 `--exclude` 排除的目录里（`benchmarks/`、`examples/`）。derive 不给
这些目录分组，所以没有 `contains` 边，conformance 自然把它们算成孤立。**这是预期行为**——
benchmarks 和 examples 本来就不该算产品设计覆盖。

问题在于画像没说清。现在 `verify_reports` 在真孤立非零且传了 `--exclude` 时附一句：

> 注：真孤立多为被 --exclude 排除的目录（tests,docs,examples,benchmarks,...），derive 不给
> 它们分组，属预期

这样 `844` 就不会被当成"覆盖不足"。

**教训**：一个指标在新口径下有了值，不代表这个值有含义。得先问"这些是谁"。`truly_orphan`
在 flask 上是 0、在 rich 上是 844，差别不在设计质量，在于有没有排除非产品目录。

## 90. 2.66.0：change-open 流程验证

`change-open` 是唯一没被端到端验证过的核心流程——之前只测"初次声明到 PASS"，没测"已交付
后改设计"。`test_wxg.py` 里有两个 change 相关用例，但都是单点断言（继承边界、只读），
没串成完整链路。

`refactor-lab/verify_change.py` 串了一遍：

| 步骤 | 结果 |
|---|---|
| up → 6 阶段 → gate | PASS |
| `change-open --from-condition StructureReconciled` | `1→2` 代 |
| 继承 | `Accepted` / `ArchitectureReconciled` = 1 |
| 重置 | `StructureReconciled` 起 5 个条件 = 0 |
| 阶段 | 回到 `StructureReconciled` |
| `change-diff` | 返回 `inherited_conditions` / `pending_conditions` / `added` / `removed` / `kept` / `code_anchors` |
| 新代 6 阶段 → gate | PASS，`checks` 全过 |
| `reconcile` | `converged`，无待办 |

这条链路之前只在 2.41.0 的 doc_flow 里被"读文档"覆盖过，但 doc_flow 不测 change-open。
现在补上。

## 91. 2.67.0：控制器安全迁移验证

`reconcile --apply` / `serve` 是"自动动手"的部分——它们会改库，越界代价最大。之前只有单点
测试，没在真实状态上串过。

`refactor-lab/verify_controller.py` 手工制造三种待迁移状态，再让控制器修：

| 制造的状态 | 期望动作 |
|---|---|
| 删掉 `interact` 工单 | `seed-ticket` 补回 |
| `model-structure` 改成 blocked、依赖已 passed | `unblock` 解阻塞 |
| `specify-test` 改成 claimed + 2020 年的 `claimed_at` | `release-stale-claim` 回收 token |

结果：

- 只读 `reconcile` 报出三种动作，**DB hash 不变**；
- `serve --once` 同样只读；
- `serve --once --apply` 后工单补回、状态 ready、token 清空；
- 再跑 `reconcile` 得 `actions=[]`。

顺带确认一个容易误判的行为：`reconcile` 未收敛时退出码是 **1**（由 `converged` 决定），
脚本里第一次就因此被判成失败。

至此核心流程全部有端到端验证：声明→交付（doc_flow）、改设计（verify_change）、控制器
（verify_controller）、报告自洽（verify_reports）。

## 92. 2.68.0：产品文档对齐

`PRODUCT-PLAN.md` 和 `README.md` 停在契约 1.4.0 / 104 用例的年代——那时候拆包还没开始、
分析命令只有一半、工具链还不存在。

更新内容：

| 文档 | 改动 |
|---|---|
| `PRODUCT-PLAN.md` | 进度表补到 P6；"主实现拆包"从未开始改为完成；质量门用例数 101 → 381；列出六条核心流程的验证脚本 |
| `README.md` | 用例数 104 → 381；版本描述 1.4.0 → 当前；拆包状态 |

至此三份面向使用者的文档（`SKILL.md` / `README.md` / `PRODUCT-PLAN.md`）都与 2.68.0 一致，
`design.md` 负责解释演进过程（开头有「怎么读」说明它不代表现状）。

## 93. 2.73.0：五条验证链的组合

`doc_flow` / `verify_reports` / `verify_change` / `verify_controller` / `verify_sync` 五条
都各自跑过，但从没串起来跑——它们都建临时库、都跑 `up`、都调 `wxg`，理论上可能互相干扰
（同一路径、同一缓存、残留文件）。

串行跑一遍：

| 脚本 | 结果 |
|---|---|
| `tools/doc_flow.py` | 文档一致性 PASS |
| `tools/verify_reports.py --repo flask/src` | 6 条自洽 PASS |
| `refactor-lab/verify_change.py` | change-open PASS |
| `refactor-lab/verify_controller.py` | 控制器安全迁移 PASS |
| `refactor-lab/verify_sync.py` | sync 报告与真实改动一致 |

无互相干扰。原因是所有脚本都用 `whyexist.temp.make_temp_dir`（Windows 受限 token 下的
正确做法）且跑完即删；`verify_sync` 只读 bad-boids 的 git，不建库。

五条合起来覆盖：文档、自洽、变更集、控制器、回扫。加上 `preflight` 的六步，发布前的
证据链是完整的。

## 94. 2.74.0：两分钟承诺的实测

`PRODUCT-PLAN` 写"新用户两分钟看到 PASS"。这个数字一直没量过。

`tools/doc_flow.py` 把 `SKILL.md` 的最短路径逐条执行到 `gate PASS`，实测 **5.6 秒**——包含
`up`、导入、六阶段工单、evidence、gate 全部命令。

"两分钟"是人跟着敲加阅读的时间，不是机器时间。两者混在一起会让人以为工具慢。文档改成
两个数分开写。

5.6 秒里大部分是 Python 进程启动（每个命令一个子进程），真正的图操作在百毫秒级——和
2.53.0 量的各命令耗时一致。

## 95. 2.75.0：发布包独立运行

之前所有验证都在源码仓里跑。发布包是另一回事：`build_release.py` 只打
`references` / `scripts` / `tests` 三个目录（`tools/` 故意不打），路径全靠相对引用——解压
到别处能不能跑，一直没验证过。

`refactor-lab/verify_release.py`：

| 步骤 | 断言 |
|---|---|
| 解压 `dist/` 最新 zip | 有 `wxg.py`、有 `SKILL.md`、**不含** `tools/` |
| `up --template standard` | feature 创建、初态 gate FAIL |
| 最短路径六阶段 | 每阶段 claim/finish/judge |
| `gate --json` | PASS、退出码 0、`checks` 全过 |

v2.74.0 实测通过。

**两个坑**：

1. 脚本第一版用了 `tempfile.mkdtemp`，在 Windows 受限 token 下直接 `PermissionError:
   [WinError 5]`——这个坑 design.md 附录里早写了，还是踩了。改用
   `whyexist.temp.make_temp_dir`。
2. `dist/` 下并存 v2.9.0 和 v2.74.0，`sorted(glob)` 按字符串排序会把 `2.9.0` 排在
   `2.74.0` 后面——换成按 mtime 取最新。

## 96. 2.76.0：发布前检查闭环

2.75.0 的 `verify_release.py` 放在 `refactor-lab/` 里，得手工另跑——发布前检查打完包就停，
等于只证明了源码仓是好的。

搬进 `tools/` 并接上 `preflight --release`：

```
测试 → 文档一致性 → 契约校验 → 状态库体检 → 报告自洽性 → 打包 → 发布包独立运行
```

最后一步的产出是"这个 zip 解压到别处能跑到 gate PASS"，而不是"打包没报错"。

`tools/` 不进发布包（`INCLUDE_DIRS` 只有 `references` / `scripts` / `tests`），所以
`verify_release.py` 只在源码仓存在——这是对的，验证包的工具不该在包里。

## 97. 2.77.0：流程验证的总入口

`refactor-lab` 里五个验证脚本（`doc_flow` 除外，它在 `tools/`）之前只能手工一个个跑。
`preflight` 不跑它们——那是发布前检查，不是流程验证。

`refactor-lab/run_all.py` 补上这个入口：

| 脚本 | 验证什么 | quick |
|---|---|---|
| `tools/doc_flow.py` | 照 `SKILL.md` 走到 gate PASS | ✓ |
| `verify_change.py` | change-open 完整链路 | ✓ |
| `verify_controller.py` | reconcile/serve 安全迁移 | ✓ |
| `tools/verify_reports.py --repo flask/src` | 真实仓扫描 + 6 条自洽 | |
| `verify_sync.py` | bad-boids 重构前后对比 | |

实测 quick 3 个 PASS、全量 5 个 PASS。

现在的分工是两层：

```
tools/preflight.py --release   发布前检查：测试/文档/契约/状态库/报告/打包/包能跑
refactor-lab/run_all.py        流程验证：文档/变更集/控制器/扫描/回扫
```

前者每次改代码都该跑，后者每次改流程或改分析逻辑都该跑。

## 98. 2.78.0：import-repo 性能基线

2.53.0 量过分析命令（plan/cycles/conformance 都 <300ms），但没量过扫描本身——`import-repo`
要遍历文件、跑 AST、写几千个节点。

`refactor-lab/bench_import.py` 分离解析与写入：

| 仓 | 文件 | 节点 | 解析 | 写入 | 合计 |
|---|---|---|---|---|---|
| tabulate | 13 | 811 | 0.26s | 0.46s | 0.72s |
| flask | 24 | 1186 | 0.27s | 0.46s | 0.73s |
| httpie | 133 | 3285 | 0.54s | 0.85s | 1.38s |
| rich | 213 | 5273 | 0.87s | 1.08s | **1.95s** |

线性增长，213 文件不到 2 秒，没有需要优化的热点。

有意思的是**写入比解析慢**——原以为 AST 解析是大头。写入是一事务内逐节点 upsert，rich 上
5273 节点花 1.08 秒，约 5k 节点/秒。这个量级对"一次完整扫描"足够，但如果以后要支持增量
扫描，这里才是要动的地方。

## 99. 2.79.0：refactor-lab 的整理

`refactor-lab` 是二十七轮里长出来的：9 个仓（其中 7 个是 `git clone --depth 1` 的），两份
状态库实验，6 个验证脚本，4 份报告，还有 38 个手工验证时 `> xxx.json` 留下的中间产物
（合计 1.19MB，最大的单文件 237KB）。没有任何索引。

- 删掉 38 个临时 JSON；
- 加 `README.md`：目录表、脚本表、报告表、跑法、以及各仓的尺度与 import 耗时。

顺手记一个教训：临时产物应该落在临时目录，不该落在实验仓根——`verify_*` 脚本都用
`make_temp_dir` 并跑完即删，但早期手工敲命令时全是 `> hxxx.json`，攒着就成了噪音。

清理后 `run_all.py` 全量仍 5 个 PASS，说明那些 JSON 确实没被任何脚本读。

## 100. 2.80.0：死代码检查

拆包后有二十多个模块。`wxg.py` 是薄入口 + 四十多个 re-export，`whyexist` 包 213 个顶层
函数/类。需要确认拆除过程中没有留下"定义了但没人用"的东西。

`refactor-lab/find_dead.py` 用 AST 收集包内定义，与全仓（`scripts` / `tests` / `tools`）
的名字引用比对。

第一次跑报 47 个"未被引用"，全是假阳性：

| 类别 | 数量 | 为什么静态看不到 |
|---|---|---|
| `cmd_*` 命令处理器 | 45 | `wxg.py` 的 `getattr(wxg, "cmd_" + name)` 动态派发 |
| `__enter__` / `__exit__` | 2 | 上下文管理器协议 |

加上这两类排除后，结论是**没有死代码**。

`cmd_*` 的动态派发是刻意的——每个命令一个 `cmd_xxx` 函数、名字登记在 `COMMANDS` 契约里，
而不是维护一张大的 `if/elif` 表。代价是静态分析看不见，好处是新增命令不用改派发代码。

## 101. 2.81.0：测试覆盖的模块视角

`test_package_units.py` 是拆包后补的纯函数测试，但没核对过"哪些模块只有端到端间接覆盖"。

`refactor-lab/coverage_report.py` 用 AST 统计每个模块的顶层定义数与 `tests/` 里直接提及的
名字数。结果按占比升序：

| 模块 | 定义 | 测试提及 | 占比 |
|---|---|---|---|
| `commands_compiler.py` / `commands_feature.py` / `commands_gates.py` / `commands_graph.py` | 9~18 | 0 | 0% |
| `importer.py` / `query.py` | 5~6 | 0 | 0% |
| `impact.py` | 8 | 2 | 25% |
| `db.py` / `workflow.py` | 11~23 | 6~12 | 52~55% |
| `graph_algo.py` / `gates.py` / `graph.py` / `cycles.py` | 8~18 | 5~11 | 61~75% |
| `planner.py` / `jsonio.py` / `work.py` / `temp.py` | 2~9 | 2~9 | 100% |

**低占比的全是 CLI 层**——`commands_*` / `query.py` / `importer.py` 都由 `test_wxg.py`
通过子进程调用，AST 看不见。`impact.py` 的 25% 也一样：公共入口 `build_impact` 被直接
测试，其余是内部辅助函数（`_backward` / `_forward` 等），经 `build_impact` 覆盖。

**方法局限**：静态统计无法区分"没测"和"经 CLI 测"。它只适合找可疑点，不能当覆盖率报告。
试过用 `trace` 跑真实执行覆盖，但 `-m unittest` 与 `--ignore-dir` 组合有问题，而且全量
测试 170 秒 × trace 开销不划算，放弃。

结论：没有发现真正的盲区。

## 102. 2.83.0：第三批仓与 dist 清理

两件事一起做：清 `dist/`、再压一轮 `import` / `derive` 的边界。

**`dist/`**：从 0.5.0 起每个版本都打了一个包，87 个目录、约 25MB。只留当前版本，其余删掉
——发布包是产物不是历史，历史在 `CHANGELOG.md` 和 git 里。

**第三批仓**（挑的是之前没覆盖的形态）：

| 仓 | 形态 | 规模 | derive 结果 | 断言 |
|---|---|---|---|---|
| attrs | **双顶层包**（`src/attr` + `src/attrs`） | 19 文件 / 595 节点 | 2 组件 / 1 依赖 / 无环 | 6 条 PASS |
| httpx | 多子包（`_transports` 等） | 60 / 2642 | 2 组件 / 2 依赖 / 1 环 | 6 条 PASS |
| black | 单包 + 大量子模块 | 40 / 2203 | 4 组件 / 5 依赖 / 1 环 | 6 条 PASS |

双包是最值得试的：`attr` 和 `attrs` 是两个并列的顶层包，`attrs/__init__.py` 从 `attr`
重新导出。derive 按目录分组，正好把它们分成两个组件——结果 1 条依赖、无环，符合预期（依赖
方向单向）。

累计扫过 12 个仓（itsdangerous / tabulate / flask / packaging / click / markupsafe /
rich / werkzeug / httpie / attrs / httpx / black），只有 rich 出过一次真问题。**结论**：
`derive` 的边界比预期窄，但每批新形态都值得试——rich 的 bug 就是唯一一次撞出来的。

## 103. 2.84.0：monorepo 形态

前 12 个仓的目录深度都在 2~3 层。poetry 和 pydantic 是另一种形态：`src/poetry/` 下十几个
子目录（`console/commands/`、`packages/`、`repositories/`……），`--depth 2` 会切出很细的组。

| 仓 | 文件 | 节点 | derive 结果 | 耗时 |
|---|---|---|---|---|
| pydantic（`pydantic/`） | 34 | 3011 | 4 组件 / 6 依赖 / 1 环 | 4.5s |
| poetry（`src/poetry/`） | 193 | 5395 | **19 组件 / 80 依赖 / 1 环** | — |

poetry 的 19 组件是目前最多的。80 条依赖里跨组件调用密集，正好能看出 `--depth 2` 的价值：
在多层目录上它给出的粒度接近"按子包切分"，而不是笼统的两个大块。

**注意 pydantic 的规模**：整个仓 3151 个 `.py`，但 `pydantic/` 包本身只有 34 个——其余是
`pydantic-core/`（Rust 的 Python 绑定）、`tests/`、`docs/`。所以扫仓要先明确扫哪个目录，
`--repo` 参数指错会得到误导性的规模。

累计 14 个仓，只有 rich 出过一次问题。

## 104. 2.86.0：CHANGELOG 的完整性

`CHANGELOG.md` 是对外最重要的历史文件，但从没核对过完整性——106 个条目跨越 0.1.0 到
2.85.0，中途有拆包十四步、文档对齐等批量改动，可能有跳跃或漏记。

`refactor-lab/check_changelog.py` 提取所有 `## x.y.z` 标题，做四项检查：

| 检查 | 判定 |
|---|---|
| 条目数、版本范围 | 106 条，0.1.0 ~ 2.85.0 |
| 递增连续性 | 相邻版本序号差应为 +1（同 minor）或 +100（跨 minor）；major 升级单独放行 |
| 重复 | 无 |
| 文件顺序 | 最新在前 |

结果全部通过。

**实现细节**：第一版只查同 minor 内的补丁号连续，把 `0.9.0 -> 1.0.0` 和 `1.9.0 -> 2.0.0`
误报成跳跃——major 升级的序号差是 9100，远超阈值。加了 `c.major == p.major + 1 and
c.minor == 0 and c.patch == 0` 的放行条件后正常。

## 105. 2.87.0：design.md 的节号

顺着 CHANGELOG 的核对，也核了 `design.md` 的节号。

`refactor-lab/check_design.py` 提取所有 `## N.` 标题，检查数量、连续性、重复，以及版本
信息是写在标题里还是正文收尾行里。

**发现缺号 85、87**：`2.61.0`（`verify_reports --repo`）和 `2.63.0`（仓画像）那两轮判断
"小改动只写 CHANGELOG"，没写 design.md——所以节号跳了。补上两节后 1~104 连续。

**版本信息分布**：标题 97 节 / 正文 74 节（有重叠，有些节两处都有）/ 两者皆无 7 节。那 7
节是 §1-§6 的说明性章节和 §82 的收尾回顾，本来就不对应单一版本，合理。

早期节用正文版本行（`版本：契约 X → Y；schema ...`），后期节把版本写进标题（`## 83.
2.59.0：...`）。两种都行，检查工具不做强制。

## 106. 2.88.0：文档完整性进 preflight

2.86 / 2.87 的两个检查（`check_changelog` / `check_design`）是 `refactor-lab` 里的实验脚本，
只在想起来的时候手工跑。文档漂移该由发布前检查拦住——`verify` 只管契约块是否同步，不管
版本号、CHANGELOG 连续性、design.md 节号。

合并成 `tools/check_docs.py`，三项检查：

| 检查 | 规则 |
|---|---|
| 版本一致性 | `VERSION` == `CONTRACT_VERSION` == `CHANGELOG` 最新条目 |
| CHANGELOG | 无重复、递增连续（同 minor +1 / 跨 minor +100 / major 升级放行）、最新在前 |
| design.md | 无重复节号、1..N 无缺号 |

`preflight` 现在六步（`--release` 八步）：

```
测试 → 文档一致性 → 文档完整性 → 契约校验 → 状态库体检 → 报告自洽 → [打包 → 包能跑]
```

版本一致性这项是新加的，抓的是"改了 `CONTRACT_VERSION` 忘了改 `VERSION`"这类漏步——
以前只能靠 `build_release` 的断言在打包时才发现。

## 107. 2.89.0：写入路径的优化尝试

2.78 量出 `import-repo` 的写入比解析慢（rich 上 1.08s vs 0.87s），想优化一下。

**第一处**：`import-file` / `import-repo` 已经查过 `get_node` 判断 inserted/updated，
`upsert_node` 内部又查一次。加 `existing` 参数复用，省掉一次点查。

**第二处**：每节点还额外插一次 `feature_nodes`，改成最后 `executemany` 一次。

**结果：几乎没用**。rich 合计 2.00s → 1.89s，写入段 1.08 → 1.14（在噪声范围内）。

结论：瓶颈不在 SQL 次数。SQLite 的点查和单行 INSERT 都很快，真正的开销在每节点的
`check_attrs` / `check_attrs` 校验、JSON `dumps`、以及 `merge_attrs` 时的 `loads`。

2 秒扫完 213 文件、5273 节点，继续抠没有意义——这已经比读代码快得多。两处改动保留了：
代码更干净（少了冗余查询和循环内单插），且没有引入复杂度。

## 108. 2.90.0：真实仓的完整生命周期

之前所有流程验证都在 `up` 建的 demo 仓上跑。demo 仓只有一个 requirement 节点，六阶段走完
不能说明"设计期编译器在真实代码上可用"。

`refactor-lab/verify_real_feature.py` 在 flask（24 文件 / 1186 节点）上走完整条：

| 步骤 | 结果 |
|---|---|
| 登记仓 + 扫描 | 1186 节点 / 1377 边 |
| derive `--apply` | 3 组件 / 6 依赖 |
| 声明 feature | 默认策略 |
| 六阶段工单 | 全部 passed |
| evidence + observe | passed |
| **gate** | **PASS，阶段 `Ready`** |

**撞到一个使用边界**：第一次尝试开启覆盖约束（ε=0.9），judge 直接失败——要求咬合 623 个
节点。读公式才明白：

```
(a / (b0 + m)) · (S − m) ≤ ε
```

ε 是**残余缺陷率上界**，不是"允许未覆盖多少"。S=1186、默认 ε=1.0 时要覆盖 589 个节点；
ε=0.01 时要 1174 个——调小反而更严。千节点级仓上这个约束实际上不可行。

所以真实仓验证里 `--no-coverage`，并把这条写进 SKILL 的覆盖边界（原来只说"大作用域建议
拆 feature 或调 ε"，现在给出具体数字和方向）。

## 109. 2.91.0：run_all 六条

`verify_real_feature` 之前只能单独跑。加进 `run_all` 的扫描组：

```bash
python refactor-lab/run_all.py --quick   # 3 条：doc_flow / change-open / 控制器
python refactor-lab/run_all.py           # 6 条：加真实仓扫描 / sync 回扫 / 真实仓生命周期
```

现在的验证分两层：

| 层 | 命令 | 覆盖 |
|---|---|---|
| 发布前检查 | `tools/preflight.py --release` | 测试 / 文档一致性 / 文档完整性 / 契约 / 状态库 / 报告自洽 / 打包 / 包能跑 |
| 流程验证 | `refactor-lab/run_all.py` | 文档最短路径 / 变更集 / 控制器 / 真实仓扫描 / 重构回扫 / 真实仓生命周期 |

`preflight` 每次改代码都跑（约 3 分钟），`run_all` 改流程或改分析逻辑时跑（约 1 分钟，
`--quick` 约 10 秒）。

## 110. 2.92.0：交接说明

96 轮之后，信息和结论散在六份文档里（`SKILL.md` 讲怎么用、`README.md` 讲是什么、
`PRODUCT-PLAN.md` 讲为什么、`CHANGELOG.md` 讲改了什么、`design.md` 讲每个版本怎么想、
`contract.md` 是契约全文）。接手的人没有一条路径能把它们串起来。

`docs/HANDOFF.md` 补这个入口：当前状态 → 能力地图 → 两层验证怎么跑 → 改东西的顺序 →
最容易踩的边界 → 目录 → 下一步方向。

其中"改东西的顺序"是七步清单：先改契约、再实现、刷新生成块、`verify`、三处版本号、写
CHANGELOG 与 design.md、最后 `preflight --release`。这七步是九十六轮里反复走的流程，
写下来比留在肌肉记忆里可靠。

## 111. 追溯门：需求拆成验收条目，空输入判 UNKNOWN（3.6.0）

起因是四仓重构项目：`gate` 一路 PASS，同时 `coverage.enforced=false`、`bites=[]`，
而 FR-CV-06/07、FR-XWS-04/05/10 这条画布需求一条测试都没有；图库里登记的 25 个 tree-web
testcase 全部指向同一组 5 个需求，锚点还是 `case-5`、`JSON-2` 这种碎片。统计型覆盖门回答的是
"抽样够不够"，没有人回答"这条需求有没有测试"——门禁不是漏了检查，是**空输入默认通过**。

决定：

1. `acceptance` 升成节点，`requirement --has_acceptance--> acceptance`；
   `verifies` 允许指向 acceptance，验收条目才是可判定、可单条变红的粒度。
2. `testcase --verifies--> requirement` 只作 `direct_tests` 展示，**不算**验收覆盖——
   否则"一条测试覆盖整条需求"又会把缺口糊回去，这正是旧登记的做法。
3. gate 的 `traceability` 是确定性检查：有需求无验收 → `UNKNOWN`，有验收无测试 → `FAIL`；
   作用域内没有 requirement 时按 N/A 跳过，不打扰纯代码图。
4. `UNKNOWN` 是新增的门禁结果，退出码 1：把"无法判定"和"通过"分开，是这次改动的核心；
   `reconcile` 对应报告 `traceability-gap` 待办。
5. 声明期就把 `--acceptance` 的每条拆成 acceptance 节点（只补不删）：新项目因此不会落在
   UNKNOWN 上（它们直接 FAIL 到补测试），UNKNOWN 专留给还没迁移验收条目的旧库。
6. 迁移通道是 `acceptance-import`：按 `ordinal` + `text` 幂等，`--dry-run` 只读不写；
   工单边界口径是"requirement 在 target_ids 内，它的 acceptance 子节点自动在边界内"。

代价：契约面 32 → 33、不变量 21 → 23、命令 50 → 53；6 个既有测试 fixture 要补追溯链，
全流程用例改用真实 `acceptance-add`，`doc_flow` 的 specify-test 阶段也要写一条 testcase
指向验收条目。

## 附：Windows 受限 token 下的临时目录

Windows 上 `tempfile.mkdtemp()` / `TemporaryDirectory()`（Python ≥ 3.12.4，为 CVE-2024-4030）
用 `os.mkdir(path, 0o700)` 建目录，会写一个只允许创建者的显式 DACL。在受限 token 的沙箱里
该 DACL 解析为空——创建者自己都写不进、删不掉。症状是 `PermissionError: [WinError 5]`。

规避：一律用 `whyexist.temp.make_temp_dir()` / `temp_dir()`。它们 Windows 上按默认 mode
建目录（继承父目录 ACL），POSIX 仍用 `0o700`。测试、脚本、临时状态库都走这两个函数，
不要直接用 `tempfile`。

这个坑在 `temp.py` 注释、`test_package_units.py`、端到端演练脚本里各踩过一次——光写在
代码注释里不够，所以在这里再记一笔。












