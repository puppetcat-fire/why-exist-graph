# why-exist-graph 3.4.0

发布日：2026-11-06
契约版本：`3.4.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.4.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.4.0/why-exist-graph-3.4.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.4.0.zip`（63 个文件） | 342032 | `84da04cd16414fad00213d209c8d5072f3041a4a403dc9b7ab4f09d4fc522434` |

来源提交：`362e711`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

**契约块分层，SKILL.md 瘦 25%**。依据是 dreaming 的第 17 次调用数据：
n 16→17、`wasteRate` 42.5%→38%、`consciousness` 67→69。3.3.0 / 3.3.1 的指令改动
方向对但不够——技能本体一次就加载 60KB。

- **`main_contract_markdown()` 只放结构**：条件顺序、角色与允许命令、命令表（50 条）、
  咬合判决允许值。
- **10 张规则表与 21 条不变量移到 `_rules_and_invariants()`**：gate / coverage /
  reconcile / 变更集 / 回扫 / conformance / 后端 / serve / 审计与证据 / 导出文件 +
  一致性不变量，只拼进 full 块。
- **效果**：

  | 项 | 前 | 后 |
  |---|---|---|
  | main 块 | 15424 字符 | 6752 字符（-56%） |
  | `SKILL.md` | 60599 字节 / 354 行 | 45369 字节 / 237 行（-25%，省 15KB） |
  | `references/contract.md` | 30727 字节 | 31430 字节（含全部规则，未减） |

- **main 块加了指针**：明确说规则与不变量在 full 块；机器可读用 `contract --json` 的
  `gate_rules` / `coverage_rules` / `invariants` 等独立键。

## 验证

`python tools/preflight.py --release` 十一步全过：

```
回归测试 416 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
未定义全局名（运行期 NameError 的前置检查） PASS
契约校验 contract v3.4.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.4.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

另外单独确认：`verify` 对重新生成的 main/full 块都一致；`doc_flow` 照精简后的
`SKILL.md` 仍能走到 gate PASS；安装后技能目录的 `SKILL.md` 是 45369 字节、
`references/contract.md` 是 31430 字节（规则一条没少）。

## 已知限制

- 模型读 `SKILL.md` 时不再直接看到 10 张规则表的正文。需要细节时要多看一步
  （`contract --section full` 或 `references/contract.md`）；换来的是每次加载省 15KB。
- `apply` 仍绕过 `target_ids` 写边界；`bite` 仍无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.4.0 共 128 个版本，v0.4.1 之后有 15 个 tag。
- 环境备注：本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，
  换 HTTPS 正常。
