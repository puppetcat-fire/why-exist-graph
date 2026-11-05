# why-exist-graph 2.93.0

发布日：2026-11-06
契约版本：`2.93.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

包内目录是 `why-exist-graph/`，解压到 DSH 的技能根即可：

```bash
# 手动
unzip why-exist-graph-2.93.0.zip -d ~/.dsh/skills/

# 或在源码仓里一条命令（会先备份旧目录，装完自检 verify）
python tools/install_skill.py --zip dist/v2.93.0/why-exist-graph-2.93.0.zip
```

安装后自检：

```bash
python ~/.dsh/skills/why-exist-graph/scripts/wxg.py verify
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-2.93.0.zip` | 326853 | `4c8d6a17a0ee7ac161d7da9eee0f695f0bcc897f4c9e05fc51c8a448acb054b8` |

包内 63 个文件，含 `SKILL.md` / `VERSION` / `CHANGELOG.md` / `references/` / `scripts/` / `tests/`，
不含 `tools/`（发布工具不随包分发）与 `docs/`。

## 本版变更

- **审计落盘**：16 路并行契约审计产物入库（`docs/audit/`）——592 条行为契约、
  152 个模块 keep / 原地改 / 重写 / 冻结判定。
- **版本真源收口**：删掉 `whyexist.__version__`（停在 2.23.0、零读取）；
  README / HANDOFF / PRODUCT-PLAN / quality / CONTRIBUTING / SKILL 里的版本号、
  用例数、代码行数全部去掉，统一指向 `VERSION` 与运行结果。
- **`check_docs` 扩到四类检查**并接进 CI：文档里再出现「当前版本 X.Y.Z」
  「Ran N tests」「N 个用例」直接失败。
- **契约块固定 LF**：`contract --write` 与 `export` 不再被 Windows 的
  `write_text` 转成 CRLF。
- **错误流兜底**：`cli.py` 的 `connect()` 移进 `try`——MySQL/PostgreSQL 的错密码、
  端口不通、没装 psycopg 从「裸 traceback + 退出 1」变成「JSON error + 退出 2」，
  并补了两条回归测试。
- **技能描述补全**：frontmatter 补上 `plan` / `brief` / `blind-check` / `impact` /
  `cycles` / `conformance` / `derive` / `conflicts` / `patch` / `apply`——此前模型侧
  只能看到 50 条命令里的 38 条。
- **新增 `tools/install_skill.py`**：把「构建 → 安装到技能目录 → verify 自检」
  做成一条可重复命令。

完整记录见 `CHANGELOG.md` 的 2.93.0 条目。

## 验证

发布前 `python tools/preflight.py --release` 八步全过：

```
回归测试 383 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
契约校验 contract v2.93.0 / schema v9
状态库体检 ok
报告自洽性 PASS
打包发布 v2.93.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- CHANGELOG 记录了 0.1.0 ~ 2.93.0 共 114 个版本，但 v0.4.1 之后的历史版本没有
  对应 tag（那些改动长期停留在一个未提交的工作树里）。`v2.93.0` 是 2.x 的首个正式 tag。
- GitHub Releases 页面需要手动上传本目录的 zip 与 sha256；仓库里没有 token，
  `tools/publish_github.py` 未执行。
- MySQL/PostgreSQL 后端仍不可用：`cmd_init` 缺 `db_url` / `re` 导入，
  两个连接包装缺 `executemany`。这属于审计 P1 的待修项，不在本版范围。
