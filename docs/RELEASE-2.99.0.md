# why-exist-graph 2.99.0

发布日：2026-11-06
契约版本：`2.99.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-2.99.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v2.99.0/why-exist-graph-2.99.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-2.99.0.zip`（63 个文件） | 338037 | `b0b14d82ccbdb981f2dc8b33cae1d2a8096a05eccd5c30f8603ce5c5e16b26a2` |

来源提交：`73c5be7`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

`retract` 的三个「报告说 A、实际做了 B」问题，本版前两个修掉，第三个改为**把副作用
报出来**（不动现行工作流）。

- **`nodes_deleted` 不再说谎**：旧实现对每个传入 id 无条件 +1，即使节点根本不存在。
  典型场景：重扫后代码里的节点已消失，工单仍按前缀拿到写入权，这时 retract 一个
  不存在的 id 会让报告显示「删了 1 个节点」。
- **越界删边单独计数**：删节点必须连带删它作为端点的边（否则留悬空边），但另一端
  不在本次 `target_ids` 内的边属于越界删除，旧实现与范围内的删除混成一个
  `edges_deleted`。新增 `edges_deleted_out_of_scope`。
- **跨 feature 工单裁剪可见**：`prune_work_refs` 会清掉所有工单里指向已删节点的
  `target_ids` / `evidence_ids`，包括其他 feature 的工单。这是必然的，但旧实现只在
  总数里体现。新增 `work_refs_pruned_other_features`。
- **`bite` 的作用域副作用可见**：`bite --feature` 会把这个节点塞进 `feature_nodes`，
  而那是 plan / coverage / conformance 的输入集合，旧实现静默做这件事。新增
  `added_to_feature_scope`（本次才加进去为 `true`，已存在为 `false`）。
  **没有**给它加 token / target 边界——那会改掉「任何人都能咬」的现行工作流，
  属于产品决策，不在实现修复范围。

测试：新增 3 条，全量 404 → 407。三条都做了变异验证：回退修复后各自变红。

## 验证

`python tools/preflight.py --release` 十步全过（本机 MariaDB 12.3.3 / PG 16.15 在线）：

```
回归测试 407 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
契约校验 contract v2.99.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v2.99.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- `retract` 仍然**不校验**被连带删除的边属于谁，只报告数量。要真正拦住越界删除
  得改 `require_targets` 的语义，那会影响所有写命令，属于契约级变更。
- `apply` 仍然绕过 `target_ids` 写边界（`SKILL.md:450` 里有说明，契约表里没有）——
  审计判定需要先补测试再定方向。
- `bite` 仍然无 token、无 target 边界。
- 自制 MySQL 客户端只支持 MariaDB + `mysql_native_password`。
- CHANGELOG 记录 0.1.0 ~ 2.99.0 共 120 个版本，v0.4.1 之后有 7 个 tag。
