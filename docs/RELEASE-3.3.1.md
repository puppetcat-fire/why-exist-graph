# why-exist-graph 3.3.1

发布日：2026-11-06
契约版本：`3.3.1`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.3.1.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.3.1/why-exist-graph-3.3.1.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.3.1.zip`（63 个文件） | 345207 | `6b13944f10cc5c36164df67270b6bdbb79468a25ec7a8a2c5ec7cdd1af4f7d86` |

来源提交：`ee568f7`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

只改技能文档。延续 3.3.0 对 dreaming `knownFailures` 的回应——`cheaperAlternatives`
里写着「做契约盘点时 grep 比加载技能更快」，本版把那条更快的路写清楚。

- **新增「想要契约清单：`contract --json` 一条命令」**：说明它零副作用
  （`contract` / `verify` / `role-prompt` 在 `cli.py` 的 `needs_db` 白名单外，
  不会创建 `.why-exist`），一次给出 32 个契约面——50 条命令（含参数与写模式）、
  8 个角色、8 个条件、`node_kinds` / `edge_kinds` / `attr_schema`、全部规则文本
  （gate / coverage / reconcile / audit / change / rescan / backend / serve / conformance）、
  21 条不变量、导出规格。
  以前模型要靠 grep + 读 `commands_*.py` + 读测试来拼契约清单。
- **新增「什么时候不该加载本技能」对照表**：契约清单 / 代码现状综述 / 单次必要性判断 /
  一次性交付判定 / 多文件行为契约盘点，逐项给出该用什么。

## 验证

`python tools/preflight.py --release` 十一步全过：

```
回归测试 416 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
未定义全局名（运行期 NameError 的前置检查） PASS
契约校验 contract v3.3.1 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.3.1 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

安装后复核：技能目录 VERSION 3.3.1、`verify` ok、`contract --json` 与「什么时候不该加载」
两节都已在装好的 `SKILL.md` 里。

## 已知限制

- 本版只改「怎么用」，不改判定能力。`verify` / `doctor` / `gate` 的实际边界见
  SKILL.md「已知边界」。
- `apply` 仍绕过 `target_ids` 写边界；`bite` 仍无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.3.1 共 127 个版本，v0.4.1 之后有 14 个 tag。
- 环境备注：本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，
  换 HTTPS 正常（GitHub 状态页当时显示 All Systems Operational）。
