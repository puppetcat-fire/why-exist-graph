# why-exist-graph 3.2.1

发布日：2026-11-06
契约版本：`3.2.1`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.2.1.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.2.1/why-exist-graph-3.2.1.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.2.1.zip`（63 个文件） | 341862 | `d6a82927a785477dced01f291e7ffea19459c751d3153bf60631b5b570da5f2d` |

来源提交：`61f2286`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

只有测试，无行为变化。

`doctor --fix` 是全仓唯一会删数据的路径，7 类可修问题里原先只有 `dangling-bite`
有测试，其余 6 类没有——等于在删数据路径上盲飞。

- 一条端到端用例覆盖全部 7 类：`dangling-bite` / `orphan-edge` /
  `feature-node-missing` / `work-target-missing` / `work-evidence-missing` /
  `token-on-inactive` / `meta-version`。构造坏库 → `doctor --fix` → 断言每类修复
  计数为 1、正常节点一个不少、被删的行确实没了、工单引用被裁空、token 被清。
- 变异验证：审计点名的三组（`orphan-edge` / `feature-node-missing` / `work-refs`）
  各回退一次，用例全部变红。

测试：410 → 411。

## 验证

`python tools/preflight.py --release` 十一步全过：

```
回归测试 411 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
未定义全局名（运行期 NameError 的前置检查） PASS
契约校验 contract v3.2.1 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.2.1 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- `doctor` 的 32 类检查里，本版只覆盖了可修的 7 类；其余 25 类（如
  `audit-not-independent`、`evidence-artifact-changed`、`applies-invalid`）
  仍然没有逐个用例。
- `apply` 仍然绕过 `target_ids` 写边界；`bite` 仍然无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.2.1 共 124 个版本，v0.4.1 之后有 11 个 tag。
