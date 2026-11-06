# why-exist-graph 3.11.0

发布日期：2026-11-06
契约版本：`3.11.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.11.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.11.0/why-exist-graph-3.11.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.11.0.zip`（65 个文件） | 371860 | `517be35863f0701c6f6c2360abd7f7a2dec212ff3b2b271981a150fd230b04b8` |

代码提交：`efbc0c2`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**缺口排序接上优先级。** 3.10.0 的 `top_gaps` 只按缺口数量排，四仓项目首屏被 P1/P2 里条数多的
需求占满——先把 P0 的 5 条补掉比先补 P1 的 6 条更对。

- **`trace` 矩阵与 `gate` 的 `top_gaps` 先按 `x_priority` 排**（`P0`/`P1`/…，大小写不敏感），
  再按缺口数量，最后按 id；没登记或认不出的按最低优先级，不报错（优先级是增强项，不是必填）。
- **`trace --md` 多一列「优先级」**，缺省显示 `—`。
- **契约**：`trace_rules` 11 → 12 条。
- **测试**：436 → 437（P0 的 1 条缺口排在 P2 的 2 条前面；md 行序一致）。

## 验证

`python tools/preflight.py --release` 十二步全过（431 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

实测（四仓项目 gen33）：`trace --md` 首屏从"P1/P2 条数多者"变成 P0 组打头
（auth-02/03/04），P1 的 auth-05 虽然缺口 6 条也排在后面。

## 升级注意

- 无 schema 变更。有 `x_priority` 的库，`trace --md` 行序与 `gate.top_gaps` 顺序会变——这是本意；
  `--json` 里多了 `priority` / `priority_rank` 两个字段。

## 已知限制

- 只认 `P0`…`P99` 这一种写法；`高/中/低`、`P0-1` 之类认不出，按最低优先级排（不报错）。
- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真测了那条验收"。
- CHANGELOG 记录 0.1.0 ~ 3.11.0 共 139 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
