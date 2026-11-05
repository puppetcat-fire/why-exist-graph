# why-exist-graph 3.1.0

发布日：2026-11-06
契约版本：`3.1.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.1.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.1.0/why-exist-graph-3.1.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.1.0.zip`（63 个文件） | 339648 | `699808a830f127a51b135200286b7f24ac70747c1ee0c225fb9e5811b98a83f8` |

来源提交：`a91f659`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

纯清理，无行为变化。审计 01/08 两片共同的结论：拆包时留下大量没人用的 re-export，
且「漏 import」这类 bug 只在特定分支才炸。

- **`scripts/wxg.py` 181 → 86 行**：原来 re-export 134 个名字。AST 统计（排除本文件）
  显示 `cmd_*` 之外 84 个里只有 **8 个**真被用——`wxg.C`（gen_sample）、
  `make_temp_dir` / `temp_dir` / `connect` / `init_db` / `Reject` / `bind_node` /
  `upsert_node` / `upsert_edge`（fixture 与测试）。其余 76 个整片删除。
  保留 `cmd_*` 是因为 CLI 分派与 `verify` 都用 `getattr(wxg, "cmd_" + name)`
  动态取，它们必须在这里可见。
- **`commands_repo.py` 738 → 660 行**：末尾 78 行是五个整片 re-export 块
  （feature / graph / gates / compiler / misc），仓内零消费者；`wxg.py` 早已直接
  从各 `commands_*` 导入。删完立刻发现 `cmd_up` 里还在用 `cmd_feature_declare`——
  import 期不报错、跑到 `up` 才 `NameError`，补了 top-level import。
- **新增 `tools/check_undefined.py`**：基于标准库 `symtable`，找出「按全局解析、
  但模块里没有定义」的名字，接进 `preflight` 成为独立一步。
  `python -m py_compile` 查不出这类问题（名字查找发生在运行期）；
  2.94 修的 `cmd_init` 缺 `db_url`/`re`、`repo-add` 缺 `_is_integrity_error`
  都是这个形态。实测：删掉 `db_url` 导入后工具报 `cmd_init.db_url` 并以 1 退出；
  对当前 34 个源文件跑是干净的。

## 验证

`python tools/preflight.py --release` 十一步全过：

```
回归测试 409 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
未定义全局名（运行期 NameError 的前置检查） PASS
契约校验 contract v3.1.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.1.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- `check_undefined.py` 只判断「模块级有没有这个名字」，不做跨模块解析：可能漏报
  （名字从别处 import 进来但用错）、也可能误报（`globals()` 动态注入）。
  它对「忘了 import」这一类命中率高，但不是完备的。
- `apply` 仍然绕过 `target_ids` 写边界；`bite` 仍然无 token、无 target 边界。
- 自制 MySQL 客户端只支持 MariaDB + `mysql_native_password`。
- CHANGELOG 记录 0.1.0 ~ 3.1.0 共 122 个版本，v0.4.1 之后有 9 个 tag。
