# why-exist-graph 2.95.0

发布日：2026-11-06
契约版本：`2.95.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-2.95.0.zip -d ~/.dsh/skills/

# 或在源码仓里一条命令（先备份旧目录，装完跑 verify 自检）
python tools/install_skill.py --zip dist/v2.95.0/why-exist-graph-2.95.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-2.95.0.zip`（63 个文件） | 332644 | `7f66aaf78a98171c1dd8bd3002a6df654bfbfee3e18765e830bc22fbf01a9973` |

来源提交：`3a06989`（manifest 里 `source.commit` / `source.dirty=false`）。
包内含 `SKILL.md` / `VERSION` / `CHANGELOG.md` / `references/` / `scripts/` / `tests/`，
不含 `tools/` 与 `docs/`。

## 本版变更

修的是审计 04 片那两条「老库升不上来、体检名不副实」。

- **旧库升级顺序**：`init_db` 原来是「完整 DDL（表 + 索引）→ 补列」。但
  `idx_bites_feature` 建在 `bites.generation` 上、`idx_work_feature` 建在
  `work_items.generation` 上，而这两列正是迁移才补的。结果是 0.4.x 的库一 `init`
  就 `no such column: generation`，重试仍失败、永久卡死。改成「建表 → 补列 → 建索引」，
  三份 schema 各自拆成 TABLES / INDEXES 两段。
  反例实测：同一个旧库，旧顺序 `OperationalError`，新顺序列补上、索引建好、原有行一条不少。
- **`ensure_db` 收紧**：以前只查 `meta` 表在不在，缺表缺列的库会等到后面某条 SQL 才炸成
  `OperationalError`——用户看到 `no such column: claimed_by`，看不出该跑 init 还是该修库。
  现在校验 12 张必需表与 5 张表的迁移列，并区分两种错误：缺表 →「未初始化，跑 `wxg init`」；
  缺列 →「schema 落后，跑 `wxg init` 就地迁移，不要重建库」。

测试：新增 5 条（旧 bites 表升级端到端、`ensure_db` 空库/完整库/缺列/缺表），
全量 392 → 397 条。

## 验证

`python tools/preflight.py --release` 八步全过：

```
回归测试 397 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
契约校验 contract v2.95.0 / schema v9
状态库体检 ok
报告自洽性 PASS
打包发布 v2.95.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- MySQL/PG 仍没有 CI 数据库服务，两个后端集成测试默认 skip；2.94.0 的后端修复
  尚未在 CI 里回归。
- `migrate_schema` 的数据回填仍是猜测（legacy 身份、generation 取当前代、
  `judge_history` 由最终 status 推导），没有来源标记，也验证不了对不对——审计判定这部分
  应当冻结，先定「旧数据可不可追溯」再动。
- `judge_history` 回填用 `'jh:' || w.id`，在 MariaDB 上 `||` 是逻辑或，会把 id 算成 `0`，
  多条历史互相覆盖。这条在 2.94.0 的审计里记录过，本版未修（需要方言化拼接）。
- GitHub Releases 附件仍需手动上传（仓库里没有 token）。
- CHANGELOG 记录 0.1.0 ~ 2.95.0 共 116 个版本，但 v0.4.1 之后只有 v2.93.0 / 2.94.0 /
  2.95.0 三个 tag。
