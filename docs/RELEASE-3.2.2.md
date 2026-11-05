# why-exist-graph 3.2.2

发布日：2026-11-06
契约版本：`3.2.2`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.2.2.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.2.2/why-exist-graph-3.2.2.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.2.2.zip`（63 个文件） | 342807 | `53e86695c45f865c5ae306e113f61035417d326d07604cf033503b79f3c8892b` |

来源提交：`02c82f2`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

只有测试，无行为变化。审计指出 `doctor` 的 32 类检查里 24 类无测试：
3.2.1 覆盖了可修的 7 类，本版补 5 类核心的**不可修**检查。

- **`applies-invalid`**：`applies` 边的语义是「谁应用了哪个设计模式」，dst 不是
  pattern 时必须报。
- **`pattern-unjustified`**：pattern 节点缺 `applicability` 或 `not_applicable`
  时必须报——否则等于没做选型。
- **`evidence-artifact-changed`**：证据登记的产物被改过，登记就失效，必须报。
- **`evidence-work-missing`**：evidence 关联的工单不存在时必须报。
- **`legacy-identity`**：迁移留下的 legacy 身份只能报给人看，且必须出现在
  `unfixable_checks` 里——自动改成某个 actor 等于伪造审计身份。

变异验证：前三条各回退检查逻辑一次，用例全部变红。测试：411 → 416。

## 验证

`python tools/preflight.py --release` 十一步全过：

```
回归测试 416 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
未定义全局名（运行期 NameError 的前置检查） PASS
契约校验 contract v3.2.2 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.2.2 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- `doctor` 仍有约 20 类检查没有逐个用例（`condition-rows` / `ready-inconsistent` /
  `change-inheritance` / `judge-history-*` 等）。它们多数是「结构一致性」检查，
  触发条件更复杂。
- `apply` 仍然绕过 `target_ids` 写边界；`bite` 仍然无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.2.2 共 125 个版本，v0.4.1 之后有 12 个 tag。
