# why-exist-graph 3.7.0

发布日期：2026-11-06
契约版本：`3.7.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.7.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.7.0/why-exist-graph-3.7.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.7.0.zip`（65 个文件） | 363088 | `a6291ff45acb0c9baff2d0bde56f0db5a410477395346500f6bec8dec1e39c3b` |

代码提交：`df519c4`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**门禁的两个输入口上锁。** `gate` 的判据来自两处：`bites`（咬合判决）与图内容。这两处此前都
没有写入边界——`bite --feature` 会顺手把节点塞进 `feature_nodes`（也就是 `coverage` 的分母，
被审方可以自己扩大判据），`apply` 可以直接把补丁写进图库（绕过 I5 的旁路）。

- **`bite --feature` 不再扩作用域**：节点必须已经在 feature 作用域内，否则拒绝并提示先
  `work-open` 并入；确需并入时显式 `--allow-new-scope`，返回值里的 `added_to_feature_scope` 照旧报告。
- **`apply` 落库要 `--token`，且写出的每个节点/边端点必须在工单 `target_ids` 内**；
  只想验证合并用 `--dry-run`（无需 token）。角色边界同步：`apply` 只给
  `model-architecture` / `model-structure` / `interact` / `specify-test` / `implement-test`。
- **`doctor` 新增 `bite-out-of-scope`**：旧库可能留着「咬合带节点进作用域」时期的越界咬合，只报告不修。
- **契约**：`AUDIT_RULES` +1（咬合不扩域）、`I5` 扩写（apply/验收命令纳入写边界）、
  `TOKEN_COMMANDS` 加 `apply`；命令表 `apply` 补 `--token`、`bite` 补 `--allow-new-scope`。
- **测试**：426 → 429（apply 无 token / 越界 / 角色限制三条；bite 越界拒绝与显式扩域改写；
  5 个既有 fixture 先把节点并入作用域再咬）。

## 验证

`python tools/preflight.py --release` 十二步全过（423 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 升级注意（会改变既有行为）

- 以前「`bite --feature` 顺手把节点挂进作用域」的用法现在会报错，改法：先
  `work-open --feature <f> --kind <k> --target-ids …`，或在确知后果时加 `--allow-new-scope`。
- 以前不带 token 的 `apply` 现在只做校验不落库（需要落库加 `--token`）。
- `doctor` 可能对旧库报出 `bite-out-of-scope`——那是历史咬合的痕迹，不修也能继续用，
  但下次覆盖统计会把它算在作用域外。

## 已知限制

- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真测了那条验收"——后者要靠审计角色读断言。
- `bite` 仍不需要 token（咬合是观察，不是工单产出）；独立性靠 `--actor` 审计，不做强制分离。
- CHANGELOG 记录 0.1.0 ~ 3.7.0 共 134 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
