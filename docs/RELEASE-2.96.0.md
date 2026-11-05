# why-exist-graph 2.96.0

发布日：2026-11-06
契约版本：`2.96.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-2.96.0.zip -d ~/.dsh/skills/

# 或在源码仓里一条命令（先备份旧目录，装完跑 verify 自检）
python tools/install_skill.py --zip dist/v2.96.0/why-exist-graph-2.96.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-2.96.0.zip`（63 个文件） | 334992 | `c96607e33a26cdd26248ff5f34d02ff980e20ec79985833aed501956ecf5f4ca` |

来源提交：`119700d`（manifest 里 `source.commit` / `source.dirty=false`）。
包内含 `SKILL.md` / `VERSION` / `CHANGELOG.md` / `references/` / `scripts/` / `tests/`，
不含 `tools/` 与 `docs/`。

## 本版变更

一条数据正确性修复，加一组从零到有的断言。

- **MariaDB 上 `judge_history` 回填会静默丢历史**：迁移用 `'jh:' || w.id` 生成 id，
  而 MariaDB 的 `||` 是逻辑或（除非开 `PIPES_AS_CONCAT`），求值为 `0`——所有回填行
  撞同一个 id `'0'`，`INSERT OR IGNORE` 下只剩第一条，其余静默消失。改按方言选拼接：
  MySQL/MariaDB 用 `CONCAT('jh:', w.id)`，PG/SQLite 保持 `||`。
- **错误流契约测试**（新增 `ErrorStreamContractTest`，6 条）：未初始化库、未知 feature、
  未知 work、import 文件缺失、不支持的 db 协议、gate FAIL（属于「判定」不属于「错误」）。
  每条断言：退出码 2（gate 那条是 1）、stdout 必须为空、stderr 是 JSON 且不含 Traceback。
  此前这类断言为零——测试夹具先解析 stdout、失败才退回 stderr，所以把错误 JSON 从
  stderr 挪到 stdout 不会有任何用例变红。
  变异验证：把 `file=sys.stderr` 改成 `file=sys.stdout` 后，6 条里 5 条变红
  （第 6 条走 gate 判定路径，本来就从 stdout 出）；修复前是 0 条。

测试：新增 7 条（1 条拼接单元 + 6 条错误流），全量 397 → 404 条。

## 验证

`python tools/preflight.py --release` 八步全过：

```
回归测试 404 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
契约校验 contract v2.96.0 / schema v9
状态库体检 ok
报告自洽性 PASS
打包发布 v2.96.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- **MySQL/PG 仍没有 CI 数据库服务**，两个后端集成测试默认 skip。2.94.0 的后端修复与
  本版的 `CONCAT` 修复靠单测与审计实测，尚未在 CI 的真实库里回归。
- 错误流测试覆盖 6 个代表性场景，不是 50 条命令的全矩阵。
- `migrate_schema` 的数据回填仍是猜测（legacy 身份、generation 取当前代、
  `judge_history` 由最终 status 推导），没有来源标记——审计判定这部分应当冻结。
- GitHub Releases 附件仍需手动上传（仓库里没有 token）。
- CHANGELOG 记录 0.1.0 ~ 2.96.0 共 117 个版本，v0.4.1 之后有 v2.93.0 / 2.94.0 /
  2.95.0 / 2.96.0 四个 tag。
