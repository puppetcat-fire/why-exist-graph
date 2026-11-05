# why-exist-graph 3.4.1

发布日：2026-11-06
契约版本：`3.4.1`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.4.1.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.4.1/why-exist-graph-3.4.1.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.4.1.zip`（63 个文件） | 342795 | `3cea475a5777f748809d47c58f138d2e78c63ef81cd2bd4b1431d205923d02b6` |

来源提交：`f6861ed`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

只改文档：「文件」节对齐现实。

- **表格拆成两张**：随发布包分发的（`scripts/` / `references/` / `tests/` / CHANGELOG）
  与只在源码仓的（`tools/` / `docs/`）。以前混在一张表里，读者分不清装完哪些就有。
- **补齐漏掉的 4 项**：`tools/install_skill.py`、`tools/test_backend.py`、
  `tools/check_undefined.py`、`docs/`（HANDOFF / CAMPAIGN / audit / 各版本 RELEASE）。
- **更新 3 处过期描述**：`wxg.py` 从「re-export 包内符号」改成「暴露 `cmd_*` 与少量
  fixture helper」（3.1.0 已删 76 个零消费导出）；`preflight` 从六项改成十一项；
  `tests/` 从列举 4 个文件改成「16 个测试文件 + 哪些需要环境变量」。

## 验证

`python tools/preflight.py --release` 十一步全过（416 tests），另外单独核对了
表里 22 个路径逐个存在。

## 已知限制

- `apply` 仍绕过 `target_ids` 写边界；`bite` 仍无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.4.1 共 129 个版本，v0.4.1 之后有 16 个 tag。
- 环境备注：本机 `git push` 走 SSH 报服务端 `fatal error in commit_refs`，HTTPS 正常。
