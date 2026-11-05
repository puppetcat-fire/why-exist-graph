# why-exist-graph 3.0.0

发布日：2026-11-06
契约版本：`3.0.0`　schema：`9`　Python：`>=3.10`（仅标准库）

> **这是 breaking release**：覆盖约束的判定口径变了，`gate` 结果可能从 FAIL 变 PASS。

## 安装

```bash
unzip why-exist-graph-3.0.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.0.0/why-exist-graph-3.0.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.0.0.zip`（63 个文件） | 339555 | `8cf651263f01d6705d092fb59725b062668dd9b29d47eb3edfb9ebe01d72e086` |

来源提交：`3d769d5`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

审计 10 片查出的「契约与实现算的不是同一个东西」。

- **`_required_coverage` 分母补上 a₀**：契约 `COVERAGE_RULES` 写的是
  `p_m=(1+d)/(10+m)`（Beta(1,9) 先验），代码算的是 `(1+d)/(9+m)`——只用
  `b₀+m` 作分母，漏掉先验的 a₀。最刺眼的表现：`S=1、ε=0.1、d=0` 时同一份
  `coverage` 报告同时输出 `p=0.1` 与 `met=false`，p 已经贴着 ε 了却说没达标。
  现在分母是 `a₀+b₀+m`，与后验 `p` 的算法、与契约公式三处一致。
- **breaking 影响**：`n_required` 会变（大多小一档），原本因覆盖不足而
  `met=false` 的阶段可能变 true，`gate` 可能从 FAIL 变 PASS。
  **已有数据不受影响**（evidence / bite / 工单原样保留），变的只是覆盖约束的判定口径。
- 旧文档里 S=1186 的两个数字按修正后公式是 **588 / 1175**（原文 589 / 1174）。
  `references/design.md` 保留当时的实测记录不动——那是历史，以 CHANGELOG 为准。

测试：407 → 409。新增一条 `coverage_report` 级别测试（测接线，不只纯函数），
变异验证：把调用处改回 `b₀` 后该测试变红（`assertEqual(0, 1)`），修复前抓不到。

## 验证

`python tools/preflight.py --release` 十步全过（本机 MariaDB 12.3.3 / PG 16.15 在线）：

```
回归测试 409 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
契约校验 contract v3.0.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.0.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- 升级到 3.0.0 后，之前因为覆盖不足被拦下的 feature 可能直接变 PASS。这不是放宽，
  是原来的算法比契约严了一档。如果团队依赖旧口径，需要显式调小 `--coverage-epsilon`。
- `apply` 仍然绕过 `target_ids` 写边界；`bite` 仍然无 token、无 target 边界。这两条
  是产品语义问题，审计判定需要先定方向再动代码。
- 自制 MySQL 客户端只支持 MariaDB + `mysql_native_password`。
- CHANGELOG 记录 0.1.0 ~ 3.0.0 共 121 个版本，v0.4.1 之后有 8 个 tag。
