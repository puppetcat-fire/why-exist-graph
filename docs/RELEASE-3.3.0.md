# why-exist-graph 3.3.0

发布日：2026-11-06
契约版本：`3.3.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.3.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.3.0/why-exist-graph-3.3.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.3.0.zip`（63 个文件） | 344254 | `0d2f7924486e8cd0f98eb816220cffec3cc9da3ac1db9902235ab3b48c262f16` |

来源提交：`f11b9ea`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

只改技能指令，不动实现。依据是 dreaming 的执行日志：该技能 16 次调用里
`boundaryAccuracy` 0.375、`wasteRate` 0.425，`knownFailures` 反复指向同一形态——
被当成开放式仓库审计工具，用临时探针脚本替代它自己的 `verify` / `doctor` / `gate`，
最后超时且没有给出任何 PASS/FAIL 结论。

- **SKILL.md 新增「首次响应」一节**：被问「这样行不行 / 交付了吗 / 该不该存在」时，
  先跑三条命令拿退出码，再决定要不要深挖：

  ```
  wxg verify                 # 字节一致性：ok:true → 退出 0
  wxg doctor                 # 状态库体检
  wxg gate --feature <id>    # PASS/FAIL → 退出 0/1
  ```

  并明确「不要为了更全面另写探针脚本」「预算内先给 PASS/FAIL 再扩展审计」。
- **能力边界写进 description**：`verify` 只比字节一致性（生成文档块、导出样例）、
  **不是契约提取器**；`doctor` 只体检状态库。这两句以前只在正文里，而模型侧读的是
  description——等于模型从来看不到这个边界。
- **`whenToUse` 补了不适用场景**：开放式仓库审计、代码综述、多文件行为契约盘点不属于
  本技能的典型路径，那类任务用普通读码/grep 更快。
- **已知边界加两条**：把 `verify` 当审计工具会得出「全绿所以契约没问题」的错觉；
  加载技能 ≠ 必须建库（只读问题用 `contract --json` / `find` / `get` 即可）。

description 从 762 字符压到 551，保证能力边界那段不会被截断。

## 验证

`python tools/preflight.py --release` 十一步全过：

```
回归测试 416 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
未定义全局名（运行期 NameError 的前置检查） PASS
契约校验 contract v3.3.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.3.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

安装后复核：技能目录 VERSION 3.3.0、`verify` ok、frontmatter 解析出的 description
551 字符且含「能力边界」；DSH 的技能 catalog 已刷新成新描述。

## 已知限制

- 技能指令改的是「怎么用」，不改「能不能判对」。`verify` / `doctor` / `gate` 的实际判定
  能力边界见 SKILL.md「已知边界」。
- `apply` 仍然绕过 `target_ids` 写边界；`bite` 仍然无 token、无 target 边界。
- CHANGELOG 记录 0.1.0 ~ 3.3.0 共 126 个版本，v0.4.1 之后有 13 个 tag。
