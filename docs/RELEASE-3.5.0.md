# why-exist-graph 3.5.0

发布日：2026-11-06
契约版本：`3.5.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.5.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.5.0/why-exist-graph-3.5.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.5.0.zip`（63 个文件） | 344031 | `e32d37cf550f5cc89b4d608d3f3ebedb9faa953fb3ebfdcc9251f99604822418` |

来源提交：`e07a9b2`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

只改技能文档：**修正定位——非 Python 重构也是目标场景**。

依据是 dreaming 第 18 次调用（`ep_mw46bgd0_f9771e`，07:25–07:32）：用户要「整理全部
需求和用例，从头做代码重构，还要加功能」，仓库是 Java（`XwsServiceImpl.java` / `sysj`）。
实际用法是建 feature `four-repo-rebuild` + 9 个切片并行抽取，`turnEnd: completed`——
但 probe 预测的 `fit` 只有 0.18，`likelyPitfalls` 第一条就写着「技能不做需求挖掘」
「Java 仓库无法直接进图库」。

- **`whenToUse` 把「重构的需求与用例落点规划」加回适用场景**：3.3.0 为了压 wasteRate
  把「多文件行为契约盘点」整个排除了，过头了——`feature` / `plan` / `brief` / `impact`
  这一层恰恰是为重构切分设计的，而且不依赖导入器。现在只排除「纯代码综述
  （没有交付判定或切分规划目标）」。
- **已知边界第一条重写**：以前只有一句「导入器只有 Python AST」。现在分层——
  - 依赖导入器：`import-file` / `import-repo` / `derive` / `sync` / `conformance`
  - 与语言无关（只吃图里节点与边）：`feature-declare` / `work-*` / `plan` / `brief` /
    `blind-check` / `impact` / `conflicts` / `gate`
  - 非 Python 仓库做法：设计层用 `upsert-node` + `upsert-edge` 手工建模，代码层只记
    「要改哪些文件/符号」的锚点节点，然后照常走 work → gate；代价是 `sync` /
    `conformance` 用不了。

## 验证

`python tools/preflight.py --release` 十一步全过（416 tests）。

## 已知限制

- 上面的「非 Python 做法」没有端到端验证——仓库里没有 Java fixture 跑过一遍
  `upsert-node → work → gate` 的完整链路。这是文档承诺，不是已测行为。
- `apply` 仍绕过 `target_ids` 写边界；`bite` 仍无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.5.0 共 130 个版本，v0.4.1 之后有 17 个 tag。
- 环境备注：本机 `git push` 走 SSH 报服务端 `fatal error in commit_refs`，HTTPS 正常。
