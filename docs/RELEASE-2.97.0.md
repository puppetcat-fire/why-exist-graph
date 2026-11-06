# why-exist-graph 2.97.0

发布日：2026-11-06
契约版本：`2.97.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-2.97.0.zip -d ~/.dsh/skills/

# 或在源码仓里一条命令（先备份旧目录，装完跑 verify 自检）
python tools/install_skill.py --zip dist/v2.97.0/why-exist-graph-2.97.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-2.97.0.zip`（63 个文件） | 335129 | `a1ccec26397a80857a912336363934ae9ad5ebc7d1cd3681c9e767050938a1af` |

> 这个包在 2.98.0 修完行尾后重建过。本版刚发布时，本地工作树被 `core.autocrlf`
> 弄成 CRLF，打出来的包是 `c1fe9d69…`（335482 字节）；CI 的 Release 附件与修正后的
> 本地重建都是 `a1ccec26…`。差异原因与修法见 `RELEASE-2.98.0.md`。

来源提交：`97f95f8`（manifest 里 `source.commit` / `source.dirty=false`）。
包内含 `SKILL.md` / `VERSION` / `CHANGELOG.md` / `references/` / `scripts/` / `tests/`，
不含 `tools/` 与 `docs/`。

## 本版变更

这版不加功能，只把「后端到底能不能用」从手工验证变成常规回归。

- **CI 新增 `backend` job**（ubuntu-latest）：MariaDB 11 与 PostgreSQL 16 各起一个
  service 容器，分别跑 `tests.test_mysql_backend` 与 `tests.test_pg_backend`。
  GitHub Actions 的 `services` 只在 Linux 上可用，所以独立成 job，不动三系统矩阵。
  在此之前这两个测试文件在 CI 里永远 skip——2.94.0 修的三条后端断链就是因为这个
  漏过去的。
- **新增 `tools/test_backend.py`**：本地一条命令跑两个后端，按 `WXG_TEST_MYSQL_URL` /
  `WXG_TEST_PG_URL` 决定跑哪个；URL 里的密码自动掩码；`--strict` 要求至少跑一个。
  测试会清空目标库所有表，脚本里明确提示只能指向可丢弃的库。
- **`preflight` 新增一步**「后端集成（可选）」：配了环境变量就跑，没配就跳过，
  不阻断发布。

## 验证

`python tools/preflight.py --release` 九步全过（本机 MariaDB 12.3.3 / PG 16.15 在线）：

```
回归测试 404 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
契约校验 contract v2.97.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v2.97.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

两个后端各自 3 条用例全过：完整 `init → repo → feature → claim → write → judge →
gate → doctor` 流程、并发 claim 只有一方胜出、`serve --once`。

## 已知限制

- CI 的 `backend` job 用的是容器里的库，和本机 12.3.3 / 16.15 版本不完全一致
  （CI 是 MariaDB 11、PostgreSQL 16），方言边界仍可能有差异。
- 没有 MariaDB 就永远跑不到 `mysql_native_password` 之外的认证路径——自制客户端
  不支持 caching_sha2，MySQL 8 默认认证下不可用，这是已知边界不是本版能修的。
- `migrate_schema` 的数据回填仍是猜测（legacy 身份、generation 取当前代、
  `judge_history` 由最终 status 推导），没有来源标记；审计判定这部分应当冻结。
- GitHub Releases 附件仍需手动上传（仓库里没有 token）。
- CHANGELOG 记录 0.1.0 ~ 2.97.0 共 118 个版本，v0.4.1 之后有 5 个 tag。
