# why-exist-graph 2.98.0

发布日：2026-11-06
契约版本：`2.98.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-2.98.0.zip -d ~/.dsh/skills/

# 或在源码仓里一条命令（先备份旧目录，装完跑 verify 自检）
python tools/install_skill.py --zip dist/v2.98.0/why-exist-graph-2.98.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-2.98.0.zip`（63 个文件） | 335746 | `1fb79a27bc65e54ac4452ed291af1967270e69153e2a24c7a9fc41545bff3a2f` |

来源提交：`0603a9f`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

修的是「同一个 commit 在两台机器上打出不同的包」。

- **根因是 `core.autocrlf`**：`.gitattributes` 声明 `* text=auto eol=lf`，但 Windows
  侧 `core.autocrlf=true` 让 checkout 出来的工作树变成 CRLF、索引仍是 LF。
  `build_release` 直接读工作树字节，于是本地包比 CI 包大 353 字节、SHA 不同。
  实测对照：本地 v2.96.0 `c96607e3…`（334992 字节），CI 的 Release 附件
  `889e2af3…`（334639 字节）；用干净 tag checkout 重新构建得到 `889e2af3…`，
  与 CI 附件**逐字节一致**——确定性机制本身没问题，是工作树被弄脏了。
- **`build_release` 自行规范化行尾**：写入 zip 前把文本文件的 CRLF 统一成 LF，
  打包结果不再依赖打包机器的 git 配置。实测：故意把 `db.py` 改成 CRLF 再
  `--allow-dirty` 构建，SHA 与 LF 基线完全相同。
- **`preflight` 新增「工作树行尾」一步**：`git ls-files --eol` 出现 `w/crlf` 就失败，
  并打印修复命令。
- **CONTRIBUTING 补环境要求**：Windows 上必须 `git config core.autocrlf false`。
- 本仓库已 `git config core.autocrlf false` 并重建索引，26 个 CRLF 文件恢复成 LF。

## 验证

`python tools/preflight.py --release` 十步全过（本机 MariaDB 12.3.3 / PG 16.15 在线）：

```
回归测试 404 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
契约校验 contract v2.98.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v2.98.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- **v2.93.0 – v2.97.0 的本地产物与 Release 附件字节不同**：那些版本是在 CRLF 工作树上
  构建的，发布附件由 CI 在 LF 上下文中构建。两者内容等价、功能相同，但 SHA 对不上；
  从 2.98.0 起统一（本版本地 SHA 应与 Release 附件一致，可用 `sha256sum` 核对）。
- CI 的 `backend` job 尚未在远端确认过结果（本版发布时 2.97.0 的那次 main CI 仍
  在跑）；本地真库是通的。
- `migrate_schema` 的数据回填仍是猜测（legacy 身份、generation 取当前代、
  `judge_history` 由最终 status 推导），没有来源标记；审计判定应当冻结。
- 自制 MySQL 客户端不支持 caching_sha2，MySQL 8 默认认证下不可用，仅 MariaDB
  + `mysql_native_password`。
- CHANGELOG 记录 0.1.0 ~ 2.98.0 共 119 个版本，v0.4.1 之后有 6 个 tag。
