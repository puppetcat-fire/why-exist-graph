# why-exist-graph 3.10.0

发布日期：2026-11-06
契约版本：`3.10.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.10.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.10.0/why-exist-graph-3.10.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.10.0.zip`（65 个文件） | 370215 | `a76cd9580b31632ba275f6939671814b27f6f78b7f4941ca02f202b09f223a40` |

代码提交：`3f6b6ff`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**红区要能直接指着下一步。** 3.9.1 之后四仓项目的 gate 终于说了真话——「742 条验收条目没有
测试指向」——然后就没下文了：哪 742 条、从谁开始补，得自己在一百多条需求的 JSON 里翻。
门禁只说"不通过"是不够的，它得能指出"先补这里"。

- **`trace --md`**：人读的追溯矩阵，按缺口降序排（谁最红在最上面），`--limit` 控制明细条数。
- **`trace --requirement <id>`**：钻取单条需求，看它的验收条目与缺口；需求不在作用域内报错。
- **`gate` 的追溯 FAIL 带 `top_gaps`**（缺口最多的 5 条需求：id / 缺口数 / 验收总数）与
  `next` 提示（"按 top_gaps 从缺口最多的需求开始补测试；`wxg trace --feature … --md` 看全表"）。
- **契约**：`trace_rules` 10 → 11 条。
- **测试**：434 → 436（`--md` + 钻取 + 非法需求、gate 的 `top_gaps`/`next`）。

## 验证

`python tools/preflight.py --release` 十二步全过（430 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

实测（四仓项目 gen33）：`trace --md` 首屏就是 AUTH 组（6/6/6/5… 条验收全无测试），
与它"未做"的组级结论对得上；`gate` 的 FAIL 现在带 `top_gaps` 前 5 条。

## 升级注意

- 无 schema 变更，旧状态库直接可用。
- `trace` 默认仍输出 JSON；`--md` 才输出表格。注意 `--md` 时 stdout 不是 JSON，
  下游脚本要么用 `--json`，要么按文本处理。

## 已知限制

- `top_gaps` 只看缺口**数量**，不看需求优先级（`x_priority` 还没接进来）。
- 追溯门只判"验收条目有没有测试指向"，不判"测试是否真测了那条验收"。
- CHANGELOG 记录 0.1.0 ~ 3.10.0 共 138 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
