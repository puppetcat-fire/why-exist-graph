# why-exist-graph 3.12.0

发布日期：2026-11-06
契约版本：`3.12.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.12.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.12.0/why-exist-graph-3.12.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.12.0.zip`（65 个文件） | 373869 | `b9dc53c49bfb1657d32a10c48c6b713043285abc7ee39a5614a4cedef1814b0e` |

代码提交：`b1a8b36`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**测试规格不再冒充交付证据：验收覆盖要求代码锚点。** 3.6 起追溯门只问"有没有 testcase 指向
验收条目"，可一个没写路径、只有一句描述的 `testcase` 节点也能满足它——又退化成"有个节点说
有测试"，和当初 gate 空输入判 PASS 是同一种病，只是下沉了一层。

- **锚点口径**：`testcase` 的 `path`（节点自身或 `attrs.path`）非空才算覆盖。只有规格、没有
  路径的测试不计入验收覆盖，`trace` 单列 `acceptance_spec_only`（每一行也有 `spec_only`），
  `gate` 的 FAIL 理由里会写"其中 N 条只有测试规格、没有代码锚点"。
- **故意没做的**：不校验文件是否真的存在——技能是语言/仓库无关的，文件级锚点留给项目侧分层做
  （四仓项目在 `tools/requirement_trace.py` 里做这层）。
- **`trace --md` 多一列「仅规格」**。
- **契约**：`trace_rules` 12 → 13 条。
- **测试**：437 → 438（node.path 认作锚点、attrs.path 认作锚点、只有规格仍算缺口）。

## 验证

`python tools/preflight.py --release` 十二步全过（432 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

实测（四仓项目 gen33）：20 条验收已测、**0 条纯规格**——289 个 testcase 全部带锚点，
这版不改他们的数字；但它堵住了"以后补测试时偷懒只写规格"这条路。

## 升级注意（会改变判定）

- 库里如果有**没有路径**的 `testcase`，它不再计入验收覆盖：`trace` 会把它算进
  `acceptance_spec_only`，`gate` 可能从 PASS 变 FAIL。补法：给节点写 `path`（或 `attrs.path`），
  或换成真正落地了测试的节点。
- 无 schema 变更。

## 已知限制

- 锚点只校验"写了路径"，不校验路径是否有效——那是项目侧的活。
- 追溯门仍不判"测试是否真测了那条验收"，只能要求测试名/位置可复核。
- CHANGELOG 记录 0.1.0 ~ 3.12.0 共 140 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
