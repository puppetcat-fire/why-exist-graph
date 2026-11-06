# why-exist-graph 3.13.0

发布日期：2026-11-06
契约版本：`3.13.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.13.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.13.0/why-exist-graph-3.13.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.13.0.zip`（65 个文件） | 375112 | `e908b22f8e50341e0382346f0d1790e5d61dec4abe74a44df170f842013ecfd0` |

代码提交：`e4b7299`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**缺口是条目级的，钻取要看到条目。** 在四仓项目里补 AUTH 验收测试时发现：`trace --requirement`
只给"6 条验收、5 条已测、缺 1 条"，可哪一条缺、哪条被谁测，还得自己查库。真正开工时看的是条目。

- **`trace --requirement <id>` 新增 `items` 明细**：每条验收的 `id` / `ordinal` / `text` /
  `tested` / `tests`（覆盖它的带锚点测试 id）。
- **`trace --requirement … --md`** 渲染「验收条目明细」表：`| # | 验收 | 覆盖测试 |`，没测的显示 `—`。
- **契约**：`trace_rules` 13 → 14 条。
- **测试**：438 → 439（钻取带条目明细、md 有小节、未覆盖条目的 tests 为空）。

## 验证

`python tools/preflight.py --release` 十二步全过（432 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

## 同轮的四仓项目进展（不是技能改动，但本轮一起做完了）

- 新写 `apps/sysj/.../AuthAcceptanceTest.java` 10 条测试，覆盖 FR-AUTH-02 的 5 条验收与
  FR-AUTH-03 的 5 条验收；sysj 全量 117 个测试通过。
- 在 gen34 里登记 10 个 testcase 节点 + 10 条 `verifies` 边（都带代码锚点）。
- 四仓项目：验收已测 20 → **30**，缺口 742 → **732**；`fr-auth-02` / `fr-auth-03` 退出
  `top_gaps`（现缺 1 / 1 条），首屏换成 `fr-base-01`、`fr-auth-04` 等仍为 0 的需求。
- **两条没实现的验收故意不写测试**：AUTH-02 验收 5（签名密钥最小长度）、AUTH-03 验收 6
  （未识别身份不得写默认用户）——缺口要留着显形，不能拿相近行为冒充。

## 升级注意

- 无 schema 变更；`items` 只在 `--requirement` 钻取时非空，其余情况为空数组。

## 已知限制

- `items` 只给覆盖测试的 id，不给测试文件行号（行号由项目侧的锚点校验负责）。
- 追溯门仍不判"测试是否真测了那条验收"，只能要求测试名/位置可复核。
- CHANGELOG 记录 0.1.0 ~ 3.13.0 共 141 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
