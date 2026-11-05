# 16 文档对外承诺与发布链 — 行为契约审计

一句话判断：这个切片的生成物部分（SKILL 契约块、contract.md、export-sample、doc_flow 最短路径）是资产，可原地不动；手写文档与发布链是负债——四份手写“当前状态”全部过期，40+ 处引用一个不存在的目录，并且 2.x 从未真正发布出去。

## 切片范围

| 文件 | 行数 | 本片要回答的问题 |
|---|---|---|
| `README.md` | 185 | 对外承诺了哪些能力、数字与安装路径是否成立 |
| `SKILL.md` | 492 | 模型看到的描述够不够、正文承诺是否被执行；生成块与正文的边界在哪 |
| `CHANGELOG.md` | 1550 | 113 条版本记录与 VERSION/契约/dist 是否对得上 |
| `VERSION` | 2 | 版本唯一锚点，谁读它、谁不读 |
| `references/contract.md` | 345 | full 契约块是否与代码同源 |
| `references/design.md` | 2151 | 110 节演进记录里有哪几节对应失效实现 |
| `references/patterns.md` | 764 | gate 对 pattern 的强制口径是否与文档一致 |
| `references/quality.md` | 77 | 提交清单里的版本/用例数是否可信 |
| `references/export-sample/feat-demo/` | 90 | 6 份样例能不能重新生成一致 |
| `docs/HANDOFF.md` | 118 | 交接信息是否可执行（尤其“怎么验证”） |
| `docs/PRODUCT-PLAN.md` | 196 | 路线图里“还没做”的承诺有哪些、与 HANDOFF 是否矛盾 |
| `tools/build_release.py` | 145 | 打包是否确定性、是否可追溯 |
| `tools/verify_release.py` | 119 | 发布包能否独立运行 |
| `tools/preflight.py` | 132 | 发布前串联是否完整、有没有越界副作用 |
| `tools/check_docs.py` | 108 | 文档版本对账覆盖了哪些文件、漏了哪些 |
| `tools/doc_flow.py` | 123 | 文档承诺能否被机器执行一遍 |
| `tools/verify_reports.py` | 246 | 只读命令之间是否自洽 |
| `tools/publish_github.py` | 301 | 发布路径是否还有人走 |
| `.github/workflows/ci.yml` | 31 | CI 到底守住了什么 |
| `.github/workflows/release.yml` | 31 | tag 发布链是否可复现 |
| `dist/v2.82.0…v2.92.0/` | 11×339 | 11 份 manifest 是否一致、是否可回指代码 |

不在本片：各 `commands_*` 的业务语义（另片负责，本片只按“文档承诺的行为”去核对）、`wxg_contract.py` 的契约内容本身（当作真源，不评价）、数据库 schema 与后端（只在“发布包能不能跑”这一层被引用）。

方法：read 读完上述文件；grep 找 `refactor-lab`、`publish_github`、env 变量与“未实现/不做”的表述；用 Python 枚举 `C.COMMANDS`（50 个）与 `C.EXPORT_FILES`（6 个）；重跑 `gen_sample.build()` 与 6 份样例做字节比对；重建 v2.92.0 发布包比 SHA；实跑 `tools/check_docs.py`、`tools/doc_flow.py`、`tools/verify_release.py`、`tools/preflight.py`；用 `git ls-remote` 看远端 tag/branch。

实跑结果（本机，2026-11-06）：

| 命令 | 结果 |
|---|---|
| `python tools/check_docs.py` | PASS：CHANGELOG 113 条（0.1.0~2.92.0），design.md 110 节（1~110） |
| `python tools/doc_flow.py` | PASS：up → 扫描链 → 六阶段 → evidence/observe → gate PASS → export 6 文件 |
| `python tools/verify_release.py --zip dist/v2.92.0/…zip` | PASS：解压 → 包内结构 → up → 最短路径 → gate PASS 退出码 0 |
| `python tools/preflight.py` | PASS：381 用例 183s + doc_flow + check_docs + verify + doctor + verify_reports |
| `python tools/build_release.py --out docs/audit/_build16` | 重建 zip SHA-256 = `8bcdc484…`，与 `dist/v2.92.0/archive.sha256` 相同 |
| `gen_sample.build()` 与 `references/export-sample/feat-demo` 比对 | 6/6 字节相同 |
| `git ls-remote --tags origin` | 只有 `v0.4.0`、`v0.4.1`；`origin/main = b8c6d7b`（= 本地 HEAD） |

未改任何源码；本片新增文件只在 `docs/audit/`（`16-docs-release.json`、`16-docs-release.md`、三个 `_probe_16*.py`；重建用的 `_build16/` 已删，只保留上面的 SHA 结论）。

## 公开面

| 入口 | 类型 | 位置 | 输入 | 输出 | 副作用 | 退出码 |
|---|---|---|---|---|---|---|
| `README.md` | file | `README.md:1-185` | 人读 | 定位/特性/安装/自检/边界/版本 | 无 | — |
| SKILL frontmatter | file | `SKILL.md:1-11` | DSH 加载器 + 模型路由 | 触发描述（决定技能被不被调用） | 无；描述就是模型能看到的全部摘要 | — |
| SKILL main 契约块 | file | `SKILL.md:113-343` | `wxg_contract` 渲染 | 条件/角色/50 命令表/判决/规则/21 不变量 | `contract --write` 覆写块内 | verify 漂移 → 1 |
| contract.md full 块 | file | `references/contract.md:6-344` | 同一契约 | 属性键/边 kind/表列/导出规则全文/版本行 | 同上 | verify 漂移 → 1 |
| export-sample（6 份） | file | `references/export-sample/feat-demo/*.md:1-18` | `gen_sample` 构造的 feat-demo 图 | 6 份带 frontmatter 的 markdown 表 | `gen_sample.py --write` rmtree+copytree 覆写 | verify 过期 → 1 |
| `VERSION` | file | `VERSION:1` | 人工 | `2.92.0` | 无 | — |
| `build_release.py` | cli | `tools/build_release.py:122-140` | `--skill/--out/--version` | stdout JSON（version/archive sha/files） | 写 `dist/v<v>/{zip,manifest,sha256}`；不查 git 干净度 | 0；版本不符 → 1 |
| `verify_release.py` | cli | `tools/verify_release.py:51-114` | `--zip` 或缺省取 mtime 最新 | 人读断言行 + PASS | 解压临时目录；建/删 `<tmp>/../demo-repo` | 0/1 |
| `preflight.py` | cli | `tools/preflight.py:51-127` | `--release` | 每步 ok + 末行汇总 | 全量测试；两个临时库；`--release` 写 dist；删 `<tmp>/../demo-repo` | 0/1 |
| `check_docs.py` | cli | `tools/check_docs.py:85-103` | 无 | CHANGELOG/design 区间 + 问题清单或 PASS | 只读 4 个文件 | 0/1 |
| `doc_flow.py` | cli | `tools/doc_flow.py:47-118` | 无（硬编码 SKILL 路径） | `[1]~[6]` 进度 + PASS | 临时库 + demo 仓 + export | 0/1 |
| `verify_reports.py` | cli | `tools/verify_reports.py:84-110` | `--root+--feature` 或 `--repo` | 仓画像 + ≤6 条断言 | `--repo` 建临时库扫描；直接读 graph.sqlite | 0/1/2 |
| `publish_github.py` | cli | `tools/publish_github.py:147-296` | flags + `GITHUB_TOKEN/GH_TOKEN` | 计划 JSON 或进度 + 结果 JSON | 改 remote、打 tag、push、建仓/Release/上传 | 0/1 |
| `dist/…/manifest.json` | file | `dist/v2.92.0/manifest.json:1-339` | build_release | 版本/契约/schema/63 文件哈希/zip 哈希 | 被写；无 commit 字段 | — |
| `ci.yml` | file | `.github/workflows/ci.yml:1-31` | push main / PR | 6 个矩阵 job：verify + unittest | 无（不跑 check_docs/preflight） | — |
| `release.yml` | file | `.github/workflows/release.yml:1-31` | push tag `v*` | GitHub Release + zip 附件 | CI 内重新打包 | — |

## 契约表

状态：covered = 有测试直接断言；partial = 有测试但漏分支；gap = 代码/流程里存在、无人断言。

### 生成物一致性（这一组是真资产）

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C1 | SKILL main 块与契约渲染逐字节一致，手改会被 verify 报漂移 | `commands_misc.py:269-287`；`test_wxg.py:481-501` | covered |
| C2 | contract.md full 块同样逐字节一致 | `commands_misc.py:274-287` | partial（测试只篡改 SKILL.md） |
| C3 | export-sample 6 份 = gen_sample 实时输出 | `commands_misc.py:330-346`；`gen_sample.py:38-116` | partial（正例每次 verify 都跑；样例被篡改的负例无测试） |
| C11 | SKILL 写的最短路径能原样走到 gate PASS | `SKILL.md:83-102`；`doc_flow.py:47-116` | partial（唯一 oracle 是手工脚本，unittest 不读正文） |
| C10 | verify 不建 `.why-exist`、可无库运行 | `cli.py:62-65`；`test_wxg.py:873-882` | covered |

### 版本与文档完整性

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C4 | VERSION / CONTRACT_VERSION / CHANGELOG 最新条目三者一致 | `check_docs.py:28-45` | gap（实跑 PASS，但 unittest 零引用、CI 不跑） |
| C5 | CHANGELOG 连续无重复倒序；design.md 节号连续 | `check_docs.py:48-82` | gap |
| C12 | README/CONTRIBUTING/HANDOFF/quality 的版本与数字准确 | `README.md:58,117,139,179`；`CONTRIBUTING.md:16`；`HANDOFF.md:14`；`quality.md:8,72,73` | gap（四处全错） |

### 发布链

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C6 | build_release 拒绝 VERSION ≠ CONTRACT_VERSION | `build_release.py:80-86` | gap |
| C7 | 同源码重复构建得到相同 zip SHA | `build_release.py:37,89-101` | gap（重建验证一致，但无自动断言） |
| C8 | 发布包能脱离源码仓独立跑 | `verify_release.py:66-111`；`preflight.py:120-124` | gap（实跑 PASS，不在 CI） |
| C9 | 包恰好 63 文件、含 SKILL、不含 tools/README/docs | `build_release.py:33-38`；`verify_release.py:73-75` | partial（只断言“不含 tools/”） |
| C13 | CI 跑 2 OS × 3 Python 的 verify + 全量测试 | `ci.yml:11-30` | gap（本环境不能执行 Actions） |
| C14 | push v* tag → CI 打包并发布 Release | `release.yml:3-30` | gap（远端只有 v0.4.0/v0.4.1） |
| C15 | publish_github 建仓/推/tag/Release，脏树拒绝 | `publish_github.py:53-58,117-121,220-296` | gap（零测试；当前树脏，必然被拒） |
| C18 | 发布产物可回指源码版本 | `build_release.py:104-116` | gap（manifest 无 commit） |

### 输出与退出码

| id | 承诺 | 证据 | 状态 |
|---|---|---|---|
| C16 | gate PASS=0 / FAIL=1；verify/doctor/apply/reconcile 按结果 0/1；拒绝与异常 JSON+2 | `cli.py:87-105`；`test_wxg.py:500` | partial（FAIL 只断言“非 0”，精确 1 没断言） |
| C17 | export 写 6 文件到 `<root>/export/<feature>/`，带 frontmatter 头 | `commands_misc.py:22-78`；`test_wxg.py:264-268`；`doc_flow.py:110-113` | partial（6 文件数只由 doc_flow 断言；头部格式只被样例钉住） |

## 状态读写

写的：

- `dist/v<v>/why-exist-graph-<v>.zip`、`manifest.json`、`archive.sha256`（`build_release.py:89-118`）——产物不进 git（`.gitignore:15-17`），只存在于本机。
- `references/export-sample/feat-demo/*`（`gen_sample.py:107-112`），仅在 `--write` 时。
- `SKILL.md` / `references/contract.md` 的契约块（`commands_misc.py:250-259`），`--write` 时真实覆写；相对路径基准是技能根不是 cwd。
- `<root>/export/<feature>/*.md`（`commands_misc.py:25-33`）。
- `<root>.parent/demo-repo`（`commands_repo.py:75-84`）——`up` 在状态库的同级建示例仓。
- `<系统临时>/demo-repo`（`preflight.py:96,111`；`verify_release.py:114`）——**删的是共享临时目录**，目标在各自 root 之外。
- `.git/config` 的 remote 与 `refs/tags/v<v>`、GitHub API（`publish_github.py:193-296`）。
- 进程内 `WXG_DB_URL`（`cli.py:58`、`engine.py:47-48`），不恢复；`PYTHONUTF8/PYTHONIOENCODING` 只写子进程环境（`preflight.py:23` 等）。

读的：

- `VERSION`（`build_release.py:129`、`check_docs.py:30`、`publish_github.py:49`）、`CHANGELOG.md`（`check_docs.py:36`、`publish_github.py:123-133`，章节格式错了只会发空正文）。
- `graph.sqlite`（`verify_reports.py:112-144`，只读连接）。
- `GITHUB_TOKEN/GH_TOKEN`（`publish_github.py:53`）、`WXG_SKILL_DIR`（`commands_misc.py:271`，测试专用，文档零提及）。
- 技能目录里必须存在 `references/design.md`、`references/contract.md`、`references/quality.md`、`tests/test_wxg.py`、`CHANGELOG.md`（`commands_misc.py:327-329`）——少一个，打包后的技能自检就红。

隐式全局状态：`WXG_DB_URL` 一旦被 `--db-url` 写进环境，同一进程后续所有连接都受影响；`DEFAULT_ROOT` 在 import 时求值（`cli.py:16`）；`up` 的示例仓位置由 root 的父目录决定，跨命令共享。

## 冗余信号

| 项 | 信号 | 置信度 |
|---|---|---|
| 版本号 9 处副本 | VERSION / CONTRACT_VERSION / `whyexist.__version__`(2.23.0) / `test_wxg.py:520` 硬编码 / README 2.67.0 / HANDOFF 2.91.0 / quality 2.42.0 / PRODUCT-PLAN 2.67.0 / CHANGELOG 2.92.0；只有 4 处一致（VERSION/契约/测试/CHANGELOG） | high |
| 每次发版必改两个非版本文件 | 11 份 manifest 显示每对相邻版本都改了 `wxg_contract.py` 与 `tests/test_wxg.py`；v2.90→2.91→2.92 没动任何 `scripts/whyexist/*` | high |
| refactor-lab/ 幽灵引用 | 40+ 行；`HANDOFF.md:52` 是“怎么验证”的第一条命令；`PRODUCT-PLAN.md:187-190` 整张表；`Test-Path refactor-lab` 为假 | high |
| 两套发布路径 | `publish_github.py` 与 `release.yml` 都会对同一 tag 建 Release；前者先推 tag 再建，会与 CI 的 action-gh-release 竞争；CONTRIBUTING:52-66 同时介绍两条 | high |
| 三个版本行为相同 | v2.90/2.91/2.92 的 manifest 差异只有 VERSION/CHANGELOG/references/契约/测试；内容（docs、refactor-lab）不在包里 | high |
| 四个测试数字 | 79（README:139，实际 85）/104（CONTRIBUTING:16）/357（quality:8,73）/381（README:58,117、HANDOFF:15,99，实测 381） | high |
| 契约渲染两份 | SKILL main + contract.md full，同源且 verify 双向比对；有意设计，但每条规则有两个可读副本 | low |
| preflight docstring 与实现不符 | `preflight.py:4` 写 4 步，实际 6 步（文档一致性之后插入文档完整性、契约校验、报告自洽） | medium |
| 导出文件名缺号 | 01/02/04/05/07，没有 03/06，也没有任何文档解释；读者会以为导出不全 | medium |
| 已知边界两份 | README:161-175（13 条）与 SKILL:433-458（24 条），coverage/drift/conformance/变更集/回扫重复出现 | medium |
| 状态表两份 | HANDOFF:12-17 与 PRODUCT-PLAN:169-180 记同一批事实，数值互不一致 | high |
| 清理逻辑三写 | `preflight.py:96`、`preflight.py:111`、`verify_release.py:114` 都是 `rmtree(tmp.parent/"demo-repo")` | medium |

## 分区判定

| 模块 | 判定 | 理由 | 风险 |
|---|---|---|---|
| `README.md` | refactor_in_place | 能力清单逐条对得上代码，错的只是版本（2.67.0）、用例数（79）、行数（181） | 数字无机器校验，改完会再烂；必须同时把 README 纳入 check_docs |
| `SKILL.md` | refactor_in_place | 正文与实现一致且被 doc_flow 端到端验证；但 frontmatter 描述只覆盖 38/50 能力，plan/brief/blind-check 等在模型侧不可发现 | 描述若改成生成物，要动 I1 的渲染与 verify 分支 |
| `references/contract.md` | keep | 纯生成物，逐字节比对，本次 verify PASS | 手改必被覆盖（这是特性） |
| `references/design.md` | freeze | 110 节叙事记录的是“当时为什么”，无法从代码重建；只有节号格式被校验 | 里面 20+ 处引用已不存在的 refactor-lab 脚本 |
| `references/patterns.md` | keep | pattern 强制口径与 gate 一致；只有标题里的 0.5.0 标签过时 | 措辞无测试约束，与 gate 漂移只能靠人读 |
| `references/quality.md` | rewrite | 复制了版本与用例数（2.42.0/357），又自称“边界只在 SKILL 维护一处”——按它自己的原则这些副本该删，只留检查项与指针 | 删数字后提交者失去“当前期望值”，应改为引用 verify/check_docs 输出 |
| `references/export-sample/` | keep | 确定性夹具，重生成 6/6 字节一致，verify 每次重跑；同时是导出格式（含 frontmatter）的唯一事实标准 | 头部文案只存在于样例，没有契约条目 |
| `docs/HANDOFF.md` | refactor_in_place | 结构对路，但主验证命令指向不存在的 `refactor-lab/run_all.py`，版本 2.91.0，design 109 节 | “下一步方向”四条是唯一成文的未完成需求，重写易丢 |
| `docs/PRODUCT-PLAN.md` | refactor_in_place | 四条命题与“不做清单”仍有价值；进度表停在 2.67.0/dist/v2.67.0，P6 的脚本不存在，§8 与 HANDOFF 矛盾 | 改“不做非 Python 导入器”等于改路线判断，需要产品决策 |
| `tools/build_release.py` | refactor_in_place | 确定性已实测（重建 SHA 相同），版本校验到位；缺 commit 字段、不查工作树 | 加 clean-tree 会让当前这套未提交工作流无法打包 |
| `tools/verify_release.py` | keep | 实跑 PASS；断言的是“包能独立跑”而不是文件清单 | 删 root 之外的 demo-repo；按 mtime 选最新包不稳 |
| `tools/preflight.py` | refactor_in_place | 六步串联有效（实跑 PASS），但 docstring 不符、清理越界、不检查 README/HANDOFF | 它是发布门本身，动它前得先给它加测试 |
| `tools/check_docs.py` | refactor_in_place | 三处版本 + CHANGELOG + design 实现干净，但漏掉实际漂移最严重的 README/HANDOFF/PRODUCT-PLAN/quality | 扩到 README 会让仓库立刻红（2.67.0） |
| `tools/doc_flow.py` | keep | 唯一“文档承诺 vs 实现”的自动化 oracle，实跑 PASS；按 SKILL 原样跑是关键设计 | 硬编码最短路径，SKILL 改流程要同步改它 |
| `tools/verify_reports.py` | keep | 6 条交叉断言抓命令间自相矛盾，preflight 里 PASS | 依赖具体输出字段名，字段改名会静默变 skip |
| `tools/publish_github.py` | freeze | 300 行、零测试、需 token/网络、与 release.yml 重叠、从未在 2.x 成功执行 | 冻结等于留着一条会抢 Release 的路径；删则失去首次建仓入口 |
| `.github/workflows/ci.yml` | refactor_in_place | 矩阵与命令对，但不跑 check_docs/doc_flow/preflight/verify_release | 加 preflight 会重复跑 183s 测试，应分 job 或复用产物 |
| `.github/workflows/release.yml` | refactor_in_place | tag 主干正确，缺 check_docs 与 verify_release，也未与 publish_github 分工 | CI 重建 zip 不校验本地 SHA，“可复现”在发布路径上失去检验 |
| `dist/v2.82.0…v2.92.0/` | freeze | 历史产物，重建只会得到同样的 zip（v2.92.0 已验证），但不可追溯且 2.90-2.92 内容重复 | dist 被 gitignore，换环境即丢失 |
| `VERSION` + `CHANGELOG.md` | keep | CHANGELOG 是 113 次迭代唯一完整记录，格式被两个工具依赖；VERSION 是唯一锚点 | 5 处副本靠 check_docs 兜底，而它不在 CI 里 |

## 值得人判断的问题

1. **docs/ 到底算不算发布物。** CHANGELOG 2.92.0 说这版“加一份 docs/HANDOFF.md”，但 `build_release.py` 的 INCLUDE_DIRS 只有 references/scripts/tests，11 个 zip 里都没有 docs/。要么改打包规则，要么 2.92.0 的发布说明是错的——这两种解释对应完全不同的修法。

2. **`~/.dsh/skills/why-exist-graph` 的 1.4.0 是怎么来的、谁来更新。** 它比仓库落后 98 个发布，少了 12 个命令（含 plan/brief/blind-check），但 frontmatter 描述与 2.92.0 字节相同，所以模型侧看不出自己拿的是旧货。仓库里没有任何同步脚本，README 只说“git clone 或解压 zip”，而 GitHub 上只有 0.4.1。

3. **2.x 从没发布过，这是刻意的还是事故。** 远端只有 v0.4.0/v0.4.1；工作树 38 项未提交；dist 里 11 个包是本地构建。如果“发布”只指本机能跑，那 CHANGELOG 的 113 个版本号就没有对外含义；如果要发，当前 publish_github 会因为树脏直接拒绝。

4. **refactor-lab/ 是缺失还是已删。** 它被 40+ 处引用，HANDOFF 把 `run_all.py` 当作“怎么验证”的第一条，PRODUCT-PLAN 用它证明变更集/控制器/回扫三条流程。如果已删，这些验证证据就只剩 CHANGELOG 里的散文；如果只是这台机器没带，交接文档的路径就应该写清楚。

5. **“不做非 Python 导入器”还成立吗。** PRODUCT-PLAN:165 明确不做，HANDOFF:111 说这是最大缺口。这决定下一个大版本的方向，不是文档编辑问题。

6. **数字该手写还是生成。** README/quality/CONTRIBUTING 各写一份用例数与版本，四处都过期。可以由 CHANGELOG 或测试输出生成，也可以干脆不写数字只给命令——但继续手写已经被证明无效。

7. **publish_github.py 留不留。** 它与 release.yml 职责重叠且会抢同一个 tag 的 Release。留的话要写清“首次建仓用它、之后用 tag”；不留就删掉 CONTRIBUTING 里的两行说明。冻结只是暂时的第三条路。
