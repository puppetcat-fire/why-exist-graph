# why-exist-graph 3.5.1

发布日：2026-11-06
契约版本：`3.5.1`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.5.1.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.5.1/why-exist-graph-3.5.1.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.5.1.zip`（63 个文件） | 344464 | `834bc69b9258da301ad829bd0bebafeb9af529c2fffea24661c85ed987bf1059` |

来源提交：`90d91f5`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

**安装器不再无限堆备份**。查 `%TEMP%` 时发现：连装十九次技能留下 19 个备份目录
（1806 个文件 / 25.9 MB），外加 90 个测试与审计的临时目录（`wxg-test-*` /
`wxg-audit-*` / `wxg-probe*` 等），合计 **304 MB**。

- **`install_skill.py` 加保留策略**：每次备份后只留最近 3 个，更早的自动删掉并打印
  清理条数。实测再装一次后目录数保持 3、总占 4.1 MB。
- **一次性清理现存残留**：`%TEMP%\wxg-*` 从 304.3 MB / 95 个目录降到 4.1 MB / 1 个目录。

本版只改源码仓工具（`tools/` 不随包分发），发布包内容与 3.5.0 相比只差版本号与
CHANGELOG。

## 验证

`python tools/preflight.py --release` 十二步全过（416 tests），包含本会话新增的
「发布说明校验」——它核对本文件里的 SHA 与 `dist/v3.5.1/archive.sha256` 一致。

## 已知限制

- **测试临时目录仍可能泄漏**：主因是全量测试跑到一半被外部超时 kill，`tearDown` 没
  执行。给 `make_temp_dir` 加清理逻辑只能治标；真正的解法是让全量测试不被外部超时
  打断，或在 CI 里用一次性容器。这次是手工清的，下次还会再积。
- `apply` 仍绕过 `target_ids` 写边界；`bite` 仍无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.5.1 共 131 个版本，v0.4.1 之后有 18 个 tag。
- 环境备注：本机 `git push` 走 SSH 报服务端 `fatal error in commit_refs`，HTTPS 正常。
