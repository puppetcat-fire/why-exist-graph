# why-exist-graph 2.94.0

发布日：2026-11-06
契约版本：`2.94.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

包内目录是 `why-exist-graph/`，解压到 DSH 的技能根即可：

```bash
unzip why-exist-graph-2.94.0.zip -d ~/.dsh/skills/

# 或在源码仓里一条命令（先备份旧目录，装完跑 verify 自检）
python tools/install_skill.py --zip dist/v2.94.0/why-exist-graph-2.94.0.zip
```

## 产物

| 文件 | SHA-256 |
|---|---|
| `why-exist-graph-2.94.0.zip`（63 个文件） | `c667cc8d75d672f2ac7bdaa0154465ac9f29dd8191e1998aff61ba3b4e3613ca` |

来源提交：`2f08eb6`（manifest 里 `source.commit` / `source.dirty=false`）。
包内含 `SKILL.md` / `VERSION` / `CHANGELOG.md` / `references/` / `scripts/` / `tests/`，
不含 `tools/`（发布工具不随包分发）与 `docs/`。

## 本版变更

把 MySQL / PostgreSQL 后端从「纸面上有」修到「真能用」——审计 04、05 两片在真实
MariaDB 12.3 与 PG 16.15 上实测出的三条断链，本版补掉：

- **`wxg init` 在 MySQL/PG 上必崩**：`commands_repo.py` 里用了 `db_url()` 与 `re.sub`，
  但两个名字都没导入。非 SQLite 后端走「掩码连接串」那条分支 100% NameError——
  而 `init_db` 已经提交过，结果是 12 张表全建好、退出码却是 2。补 import。
- **写路径 100% `AttributeError`**：`_MySQLConnection` / `_PgConnection` 只实现了
  `execute` / `executescript` / `commit` / `rollback` / `close`，而 `import-file`、
  `import-repo` 批量写 `feature_nodes` 时调 `conn.executemany`。两个包装各补一份逐条
  `execute` 的实现，翻译/PRAGMA/命名参数全部复用 execute 的统一路径。
- **PG 占位符误换**：原来是 `sql.replace("?", "%s")`——字符串字面量里的 `?` 也被换掉
  （`'status?'` → `'status%s'`），`'100%'` 被 psycopg 当成占位符。改成引号感知扫描：
  `?` 只在引号外替换；`%` 在有参数时统一转义成 `%%`（含引号内，因为 psycopg 的占位符
  解析不看 SQL 引号）；无参数时传 `None` 不做插值。
- **`repo-add` 冲突路径**：`_is_integrity_error` 只被 `graph.py` 导入，`commands_repo.py`
  用它时是 NameError——path 冲突会变成未定义名异常，而不是「仓登记冲突」的可读错误。

测试：`tests/test_package_units.py` 87 → 96 条，全量 381 → 392 条。

## 验证

`python tools/preflight.py --release` 八步全过：

```
回归测试 392 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
契约校验 contract v2.94.0 / schema v9
状态库体检 ok
报告自洽性 PASS
打包发布 v2.94.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- **MySQL/PG 仍没有 CI 数据库服务**，两个后端集成测试默认 skip。本版修复的证据是
  审计在真实 MariaDB 12.3 / PG 16.15 上的实测 + 新增单测，尚未在 CI 里回归。
- `ensure_db` 仍只检查 `meta` 表是否存在，缺表/缺列的库会报 `OperationalError` 退出 2，
  而不是给出可读的「库不完整」提示。
- 旧库迁移仍按列存在性推断顺序，`0.4.x` 的库升级路径没有回归夹具。
- GitHub Releases 附件需手动上传（仓库里没有 token）。
- CHANGELOG 记录 0.1.0 ~ 2.94.0 共 115 个版本，但 v0.4.1 之后只有 `v2.93.0` / `v2.94.0`
  两个 tag——中间的历史改动长期停留在一个未提交的工作树里。
