# why-exist-graph 3.15.0

发布日期：2026-11-06
契约版本：`3.15.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.15.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.15.0/why-exist-graph-3.15.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.15.0.zip`（65 个文件） | 380124 | `8b54c50cd40e196c51f4ce37f7f60f5dbef8a9782566200a564d0fe80db276b1` |

代码提交：`35c0efd`（manifest 里另有 `source.commit` / `source.dirty=false`）。

## 本版变更

**缺口要能解释自己：验收条目可标注"未实现/阻塞"，但不豁免门禁。**

查四仓 `fr-cat-09` 时发现它的 5 条验收里 4 条根本没实现（没有别名解析、没有"引擎映射"概念、
没有可执行指令投影），只有 1 条是"实现了、缺测试"。门禁此前把两者算成同一个"缺口"，
人看着 5 条红，不知道该写测试还是先做功能。

- **验收条目的 `x_status`**（自由文本）标注未实现/不适用/阻塞原因；`trace` 把它算进
  `acceptance_blocked`（每行也有 `blocked` 数），`--md` 明细表多一列「状态」、全表多一列「未实现」。
- **标注不豁免**：被标注的条目仍是缺口，`gate` 照样 FAIL——只在理由里加一句
  "其中 N 条标注了未实现/阻塞，仍算缺口、不豁免"。做成"标注即豁免"会立刻长出一条逃跑通道。
- **契约**：`trace_rules` 14 → 15 条。
- **测试**：442 → 443（标注进 blocked、明细带状态、gate 理由点出、md 有状态列）。

## 验证

`python tools/preflight.py --release` 十二步全过（437 passed / 6 skipped）；
`python tools/doc_flow.py` 按 SKILL.md 最短路径从零走到 `gate PASS`。

实测（四仓项目 gen36）：标了 6 条——`fr-cat-09` 的 1/2/4/5（未实现/部分实现）、
`fr-auth-02` 验收 5（无签名密钥配置）、`fr-auth-03` 验收 6（不适用：无默认用户概念）。
`trace --requirement fr-cat-09 --md` 的明细表直接写出每条的缺席原因，第 3 条（未知编码→未识别）
留空——那是真正该补测试的一条。

## 升级注意

- 无 schema 变更。`x_status` 只是 attrs 扩展键，旧库无影响。
- 已有库如果曾用别的键记原因（如 `x_note`），需要手动挪到 `x_status` 才会进 `acceptance_blocked`。

## 已知限制

- `x_status` 是自由文本，不做枚举校验——写什么都行，所以只能给人看，不能当机器判据。
- 标注不改变缺口数量与门禁结果；它只解释，不消灾。
- CHANGELOG 记录 0.1.0 ~ 3.15.0 共 143 个版本。
- 本机 `git push` 走 SSH 会报服务端 `fatal error in commit_refs`，HTTPS 正常。
