# why-exist-graph 3.6.1

发布日期：2026-11-06
契约版本：`3.6.1`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.6.1.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.6.1/why-exist-graph-3.6.1.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.6.1.zip`（65 个文件） | 359950 | `b284f5cfe9d6ee58f96a18473156d673a85f64a9c500ec4a68da322d30ddf323` |

代码提交：`8af899b`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**验收条目收成单一来源。** 3.6.0 引入 `acceptance` 节点后，同一个"验收"在图里其实有三份：
`features.acceptance_json`（声明快照）、`requirement.attrs.x_acceptance`（旧迁移来源）、
`acceptance` 节点（可寻址）。导出读第一份、门禁读第三份——两套读法迟早起分歧，而这恰好
是本技能存在理由的反面。

- **`export` 的 01-需求.md 验收列改读 `acceptance` 节点**（按序号升序、`；`连接）；
  `features.acceptance_json` 降级为 `brief` 任务书里的功能级目标，不进交付视图。
- **`feature-declare` / `feature-register` 不再写 `requirement.attrs.x_acceptance`**：
  声明直接落成节点；`x_acceptance` 只在旧库 `acceptance-import` 迁移时被读，读完即完成使命。
- **doctor 新增四类验收结构检查**（只报告不自动修，修法涉及语义）：
  `acceptance-orphan`（没有 `has_acceptance` 父）、`acceptance-multi-parent`（挂多个需求）、
  `acceptance-ordinal`（序号重复/缺号/非整数）、`acceptance-source-drift`（旧库两边都在但文本对不上）。
- **契约**：`trace_rules` 5 → 7 条（权威来源、doctor 口径）。
- **测试**：423 → 426（导出只认节点、doctor 三类、声明不写 `x_acceptance`）；
  版本断言改成读 `VERSION`，不再每版改一次常量。

## 验证

`python tools/preflight.py --release` 十二步全过（420 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 升级注意

- 无 schema 变更，旧状态库直接可用。
- 若你的库里有旧 `requirement.attrs.x_acceptance` 且已跑过 `acceptance-import`，
  `doctor` 会核对两边文本；对得上就不会报，对不上报 `acceptance-source-drift`（不自动改）。

## 已知限制

- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真测了那条验收"——后者要靠审计角色读断言。
- `apply` 仍绕过 `target_ids` 写边界；`bite` 仍无 token、无 target 边界（下一版处理）。
- CHANGELOG 记录 0.1.0 ~ 3.6.1 共 133 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
