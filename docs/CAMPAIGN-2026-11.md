# 2026-11 改造战报

从 `v0.4.1` 到 `v3.2.2` 的一次性收敛。这份文档记录做了什么、证据在哪、什么没动。

- 起点提交：`b8c6d7b`（v0.4.1，仓库只跟踪 25 个文件）
- 终点提交：`204c7db`（3.2.2）
- 新增提交：26 个；新增 tag：12 个（v2.93.0 → v3.2.2）
- 测试：381 → 416
- 后端：MySQL/MariaDB 与 PostgreSQL 从「纸面上有」到「CI 里真跑」

## 0. 起点：一份 16 片的契约审计

先做的事不是改代码，是**提取现有行为契约并与声明对账**。产出在 `docs/audit/`：

| 项 | 数 |
|---|---|
| 审计切片 | 16 |
| 覆盖模块 | 77 |
| 公开入口 | 300 |
| 提取到的行为契约 | 592 |
| covered（有测试直接断言） | 206（34%） |
| partial | 189（31%） |
| gap（零断言） | 197（33%） |
| 模块分区判定 | 152 |

分区结果：**keep 49 / 原地改 65 / 重写 22 / 冻结 16**。

这个比例本身就是结论：最值钱的纯函数层（`graph_algo` / `derive` / `briefing` / `blind` /
`impact` / `cycles` / `conflicts` / `evidence` / `planner`）全在 keep 里，重写没有收益；
真正的病灶是「一个事实多份副本」和「验证只覆盖成功路径」。

明细见 `docs/audit/REPORT.md` 与 `docs/audit/DECISIONS.md`；16 份契约卡在
`docs/audit/NN-*.json|md`；26 个实测探针在 `docs/audit/probes/`。

## 1. 十二个版本

| 版本 | 提交 | 主题 | 关键证据 |
|---|---|---|---|
| 2.93.0 | `b3faf03` | 真源收口：版本号 9 处副本 → 1 处；`check_docs` 加「写死副本」检查并进 CI；契约块固定 LF | 删 `whyexist.__version__`（停在 2.23.0、零读取）；6 份文档去写死数字 |
| 2.93.0+ | `5fdc313` | `connect()` 移进错误兜底 | 改前 traceback+1，改后 JSON+2；新增 2 条错误流测试 |
| 2.93.0+ | `9c9be79` | 发布可溯源 + 技能安装一条命令 | `build_release` 写 `source.commit`/`dirty` 并拒绝脏树；`tools/install_skill.py` |
| 2.94.0 | `2f08eb6` | MySQL/PG 三条断链 | `cmd_init` 补 `db_url`/`re`；两个连接包装补 `executemany`；PG 占位符改引号感知 |
| 2.95.0 | `3a06989` | 旧库升级 + `ensure_db` | 建表→补列→建索引（旧顺序实测 `no such column: generation`）；`ensure_db` 区分「未初始化」/「schema 落后」 |
| 2.96.0 | `119700d` | MariaDB 静默丢历史 + 错误流 | `'jh:' \|\| w.id` 在 MariaDB 求值为 0 → 改 `CONCAT`；`ErrorStreamContractTest` 6 条，变异 5/6 被抓 |
| 2.97.0 | `97f95f8` | 后端集成进 CI | CI 新增 `backend` job（MariaDB 11 + PG 16 service）；`tools/test_backend.py`；preflight 加一步 |
| 2.98.0 | `0603a9f` | 打包可复现性 | `core.autocrlf` 弄脏工作树 → 本地包比 CI 大 353 字节；`build_release` 自行规范化 LF；preflight 加行尾检查 |
| 2.99.0 | `73c5be7` | `retract` 计数与越界可见化 | `nodes_deleted` 只计真删；新增 `edges_deleted_out_of_scope`、`work_refs_pruned_other_features`、`bite.added_to_feature_scope` |
| 3.0.0 | `3d769d5` | 覆盖公式对齐契约（breaking） | 分母补 `a₀`，与 `p_m=(1+d)/(10+m)` 一致；S=1/ε=0.1 不再「p=0.1 却 met=false」 |
| 3.1.0 | `a91f659` | 拆包残留清理 | `wxg.py` 181→86（删 76 个零消费 re-export）；`commands_repo.py` 738→660；新增 `tools/check_undefined.py` |
| 3.2.0 | `d5879b3` | `scope_ids` 顺序确定性 | 通配展开遍历 `set` → `sorted()`；跨进程 4 种子比对 |
| 3.2.1 | `61f2286` | `doctor --fix` 七类覆盖 | 唯一删数据的路径，之前 6/7 类无测试；三组变异验证 |
| 3.2.2 | `02c82f2` | `doctor` 五类不可修检查 | `applies-invalid` / `pattern-unjustified` / `evidence-artifact-changed` / `evidence-work-missing` / `legacy-identity` |

（2.93.0 的三个补丁在最终 tag 之前，合并在 v2.93.0 的提交线里。）

## 2. 每个版本都走同一条发布链

`python tools/preflight.py --release` 的十一步：

```
回归测试 → 文档一致性(doc_flow) → 文档完整性(check_docs) → 工作树行尾(LF)
→ 未定义全局名(check_undefined) → 契约校验(verify) → 状态库体检(doctor)
→ 报告自洽性(verify_reports) → 后端集成(可选) → 打包 → 发布包独立运行
```

然后：`tools/install_skill.py` 装进 `~/.dsh/skills/why-exist-graph` 并跑包内 `verify` 自检；
打 annotated tag；推 main + tag；GitHub Actions 的 `Release` workflow 自动构建并上传 zip。

**跨端一致性实测**（本地构建 vs. GitHub Release 附件，SHA-256 逐字节比对）：

| 版本 | 本地产物 SHA | Release 附件 SHA | 一致 |
|---|---|---|---|
| 2.96.0 | `c96607e3…`（修前）/ `889e2af3…`（修后） | `889e2af3…` | 修后一致 |
| 2.97.0 | `c1fe9d69…`（修前）/ `a1ccec26…`（修后） | `a1ccec26…` | 修后一致 |
| 2.98.0 | `1fb79a27…` | `1fb79a27…` | 一致 |
| 2.99.0 | `b0b14d82…` | `b0b14d82…` | 一致 |
| 3.0.0 | `8cf65126…` | `8cf65126…` | 一致 |
| 3.1.0 | `699808a8…` | `699808a8…` | 一致 |
| 3.2.0 | `8ad77214…` | `8ad77214…` | 一致 |
| 3.2.1 | `d6a82927…` | `d6a82927…` | 一致 |
| 3.2.2 | `53e86695…` | `53e86695…` | 一致 |

2.96 与 2.97 的「修前」是本地产物，因为当时工作树被 `core.autocrlf` 弄成 CRLF；
2.98 修完后本地与 CI 完全一致。

**CI 状态**：`5fdc313` 到 `3.2.1` 的每一次 push 都是 success，包括新加的
`backend integration (mariadb + postgres)` job（实测 success 见 commit `d40ca98` 的
run 42074529271）。`3.2.2` 的 CI 在写这份文档时仍在跑。

## 3. 测试增长

| 版本 | 用例数 | 增量来源 |
|---|---|---|
| 起点 | 381 | — |
| 2.93 | 383 | connect 错误流 ×2 |
| 2.94 | 392 | 后端修复 ×9 |
| 2.95 | 397 | 旧库升级 + ensure_db ×5 |
| 2.96 | 404 | 拼接单元 + 错误流 ×7 |
| 2.97–2.98 | 404 | 只接通路，不加用例 |
| 2.99 | 407 | retract/bite 可见化 ×3 |
| 3.0 | 409 | 覆盖公式 ×2 |
| 3.1 | 409 | 纯清理 |
| 3.2 | 410 | scope_ids 确定性 ×1 |
| 3.2.1 | 411 | doctor --fix 七类 ×1 |
| 3.2.2 | 416 | doctor 不可修五类 ×5 |

## 4. 什么没动

按审计的分区判定：

- **keep 49 个模块原样保留**：全部纯函数层、全部 fixture、`VERSION + CHANGELOG`。
- **freeze 16 项没碰**：`migrate_schema` 的数据回填（全是猜测、不可复现）、
  `temp.py`（Windows 受限 token 规避，CI 验证不了）、`_node_id` 生成规则（外部主键）、
  `work-judge` 状态转移表、`feature-status` 字段集、`slice_payload` 形状、
  `derive --apply` 写路径、`doctor --fix` 的语义、`INVARIANTS` 文本、`references/design.md`。

## 5. 还没做的三件事（需要产品决策）

1. **`apply` 绕过 `target_ids` 写边界**：无 token、无 target、无 actor，写出的节点不进
   `feature_nodes`。这个例外只写在 `SKILL.md:450`，契约表里没有。要么把它变成正式契约，
   要么收紧——两者都改变并行合并模型。
2. **`bite` 无 token、无 target 边界**：任何人可以对任何节点下判决，`--feature` 还会
   顺手把节点塞进作用域（3.2.1 起有 `added_to_feature_scope` 报告，但仍不拦）。
   收紧会改掉现行「任何人都能咬」的工作流。
3. **`migrate_schema` 的历史回填**：legacy 身份、generation 取当前代、`judge_history`
   由最终 status 推导——都是猜测，表里没有来源标记。需要定「旧数据可不可追溯」。

## 6. 三个方法论教训

1. **函数级测试测不到接线**。3.0.0 的覆盖公式，我先写了 `_required_coverage` 的单元测试，
   把调用处改回旧参数后测试仍然绿——因为它自己传 `denom`，不经过 `coverage_report`。
   补了一条 report 级用例才抓到（`0 != 1`）。
2. **文档里的数字必须生成，不能手写**。2.93 之前版本号有 9 处副本只有 4 处一致；
   3.2.2 我自己写 RELEASE 时也凭印象填错了 SHA。现在 `check_docs` 会拦「写死的当前版本
   与用例数」，但校验和仍然靠人抄。
3. **测试的场景要能触发 bug**。3.2.0 的 `scope_ids` 顺序，单 feature 的测试变异后仍绿——
   因为导入的节点已经在 `feature_nodes` 里，通配展开被去重，顺序根本没变。换成两个
   feature 才让新节点带上 `set` 的遍历顺序。

## 7. 怎么复现

```bash
cd why-exist-graph
PYTHONUTF8=1 python tools/preflight.py --release   # 十一步（后端集成需 WXG_TEST_*_URL）
python tools/install_skill.py                      # 装进 ~/.dsh/skills 并自检
```

审计产物：`docs/audit/REPORT.md`（总报告）、`docs/audit/DECISIONS.md`（152 条判定明细）、
`docs/audit/NN-*.md`（16 份契约卡）。
