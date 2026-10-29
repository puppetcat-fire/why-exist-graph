# 设计说明：why-exist-graph（DSH 原生）

本文件说明这套实现的设计取舍，以及它如何修掉 Cursor 版 why-exist + program-graph 的
设计不一致。可执行证据在 `tests/test_wxg.py` 与 `wxg verify`。

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
- **gate 不评价图规模/设计质量**。它只校验条件、咬合与证据；最小 requirement 图也可能 PASS，
  语义强弱由使用方判断。
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


