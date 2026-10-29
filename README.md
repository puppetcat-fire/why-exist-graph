# why-exist-graph

> DSH 原生的「设计图谱 + 交付门」技能：把“一块代码/一个功能到底有没有必要、设计是否成立、是否真的交付了”变成可机械判定的状态。
>
> *A DSH-native "design graph + delivery gate" skill that turns design-vs-code and delivery claims into mechanically checkable state.*

> CI：[`.github/workflows/ci.yml`](.github/workflows/ci.yml)（ubuntu + windows × Python 3.10/3.12/3.13）。

## 为什么

代码评审里最常见、也最难回答的三个问题是：

1. **这块代码/这个功能有没有必要存在？**（还是历史遗留、拍脑袋需求）
2. **设计是否和实现对得上？**（文档说一套、代码做一套）
3. **交付是否真的完成？**（测试跑过吗？谁审计的？证据在哪？）

`why-exist-graph` 把这三件事落成一套本地、可审计、可机械检查的状态机：

- 一份**唯一契约**（条件、工单、角色、命令、属性键、导出形状），CLI 与文档都由它生成；
- 一个**SQLite 设计图谱**（需求、用例、构件、类/操作、参数、交互、数据流、测试、断言）；
- 一套**8 条件交付门**（Accepted → 架构/结构/交互调和 → 测试规格/实现 → 行为通过 → Ready）；
- 一个**独立审计链**（claim_token 写入边界、独立 audit 角色、同代证据、KEEP 反咬）；
- 六份**只读导出视图**（需求/用例/架构/类图/数据流/测试规格），缺就留空，不补旧文档。

## 特性

- **单一契约**：`scripts/wxg_contract.py` 是唯一真源；`scripts/wxg.py` 的 CLI、`SKILL.md` 与 `references/contract.md` 的契约块、导出样例都由它生成，`wxg verify` 逐字节校验漂移。
- **门禁不可旁路**：条件只能由 `work-judge(passed)` 置真（Accepted 由声明/登记新建置真）；`feature-register --true` 已移除；`work-claim` 只发当前 generation 工单；`gate` FAIL 退出码 1。
- **证据同代**：BehaviorPassed 需要同一 generation、`exit_code=0`、产物存在且 SHA-256 一致的 evidence；重新声明后旧代证据失效。
- **咬合可追溯**：`attrs.bite` 只能由 `bite` 写，gate 只采信 `bites` 表（含 actor）。
- **状态库自检**：`doctor` 检查悬空 bite/边/引用、陈旧 token、条件完整性与审计配对、legacy 身份、证据产物；`--fix` 只清理悬空引用与陈旧 token，不替人裁决。
- **DSH Agent Teams 友好**：`role-prompt` 生成可交给 teammate 的角色提示（真实状态库/CLI 路径、允许命令与边界）；`target_ids` 就是并行写入边界，audit 必须由独立成员执行。
- **纯标准库**：Python ≥ 3.10 + SQLite，无第三方依赖；提供确定性导出样例与 42 个回归用例。

## 安装

要求：Python ≥ 3.10；[DSH（DeepSeek Harness）](https://github.com/deepseek-ai/deepseek-harness) 工作区。

方式一：放成 DSH 技能（推荐）

```bash
git clone <this-repo-url> <workspace>/.dsh/skills/why-exist-graph
```

或从 GitHub Releases 下载 `why-exist-graph-<version>.zip`，解包到 `<workspace>/.dsh/skills/why-exist-graph`。

方式二：只作为普通 Python CLI 使用（无需 DSH）

```bash
python scripts/wxg.py --root .why-exist init
```

## 快速开始

```powershell
$env:PYTHONUTF8 = "1"
$wxg = "scripts/wxg.py"

python $wxg --root .why-exist init
python $wxg --root .why-exist repo-add --id demo --path path/to/your/repo
python $wxg --root .why-exist feature-declare --id feat-x --name "小功能" `
  --statement "一句话" --acceptance "@acceptance.json" --constraints "@constraints.json"

# 用 work-open 扩展本角色的写入边界，再领工单
python $wxg --root .why-exist work-open --feature feat-x --kind model-architecture `
  --target-ids "@targets.json"
python $wxg --root .why-exist work-claim --role model-architecture --actor agent-arch

# 用返回的 claim_token 写节点/边，然后提交、由独立 audit 角色裁决
python $wxg --root .why-exist upsert-node --token <token> --data "@node.json"
python $wxg --root .why-exist work-finish --token <token>
python $wxg --root .why-exist work-judge --id <工单id> --verdict passed `
  --role audit --actor auditor-1

# 裁决 BehaviorPassed 前先登记同代证据
python $wxg --root .why-exist evidence-record --feature feat-x --name unittest `
  --command "python -m unittest" --artifact test.log --actor auditor-1

python $wxg --root .why-exist gate --feature feat-x --json   # PASS=0 / FAIL=1
python $wxg --root .why-exist export --feature feat-x
```

> PowerShell 5.1 下内联 JSON 的引号会被改写：`--acceptance/--constraints/--data/--spec/--target-ids/--node-ids/--ids`
> 都支持 `@文件路径`。完整说明见 `SKILL.md`。

## 自检与开发

```bash
PYTHONUTF8=1 python scripts/wxg.py verify          # ok:true, contract v0.4.0 / schema v3
PYTHONUTF8=1 python -m unittest discover -s tests -v   # Ran 42 tests ... OK
python scripts/gen_sample.py                        # 重建导出样例（--write 刷新 references/export-sample）
```

修改契约的流程：改 `scripts/wxg_contract.py` → `python scripts/wxg.py contract --write SKILL.md --section main` →
`python scripts/wxg.py contract --write references/contract.md --section full` → `python scripts/wxg.py verify`。
不要手改生成块。

## 仓库结构

| 路径 | 作用 |
|------|------|
| `SKILL.md` | 技能说明（frontmatter + 契约生成块 + 工作流） |
| `references/contract.md` | 完整契约视图（生成块） |
| `references/design.md` | 设计说明与已知边界 |
| `references/quality.md` | 提交质量门 |
| `references/export-sample/` | 六份导出样例（`verify` 逐字节校验） |
| `scripts/wxg_contract.py` | 唯一契约（条件/工单/角色/命令/属性/导出/不变量） |
| `scripts/wxg.py` | CLI：图库、工单状态机、导入、bite、gate、export、doctor、verify |
| `scripts/gen_sample.py` | 生成确定性导出样例 |
| `tests/test_wxg.py` | 42 个端到端与一致性测试 |
| `tools/build_release.py` | 构建确定性发布 zip + manifest |
| `.github/workflows/` | CI（多平台/多 Python 版本）与 tag 发版 |

运行时状态库默认在 `--root`（建议工作区下 `.why-exist/`），不要提交进 git。

## 设计原则（摘要）

- **图库是唯一权威，文档只是视图**；导出缺数据就留空，禁止从旧文档补句。
- **判定与状态变更分离**：`gate`/`verify`/`slice`/`get`/`find` 只读；条件只由 `work-judge` 改。
- **写入有边界**：图内容写入需要 claim_token 且落在工单 `target_ids` 内；角色只能调用自己 ROLES 里的命令。
- **审计独立**：judge actor ≠ 被审工单 claimed_by；`judged_by` 只写一次；legacy 身份由 doctor 提示不可追溯。
- **同代证据**：BehaviorPassed 的证据按 generation 记账，重声明后必须在新代重新跑测试并登记。

更完整的设计取舍与已知边界见 [`references/design.md`](references/design.md)。

## 已知边界

- 导入器仅 Python AST；其他语言用 `upsert-node`/`upsert-edge` 手工建图。
- 测试执行不在本工具内：BehaviorPassed 只强制“有同代有效 evidence”，不校验证据真伪。
- 本工具信任状态库文件本身；绕过命令直接改 sqlite 不在防护范围（doctor 只能发现部分不一致）。
- `gate` 只校验条件/咬合/证据，不评价图规模与设计质量。

## 版本

当前 `0.4.0`（首个发布版本，契约 0.4.0 / schema 3）。变更记录见 [`CHANGELOG.md`](CHANGELOG.md)，
版本号见 [`VERSION`](VERSION)。GitHub Releases 会附带可安装 zip 与 SHA-256。

## License

[MIT](LICENSE)
