# why-exist-graph 3.2.0

发布日：2026-11-06
契约版本：`3.2.0`　schema：`9`　Python：`>=3.10`（仅标准库）

## 安装

```bash
unzip why-exist-graph-3.2.0.zip -d ~/.dsh/skills/

python tools/install_skill.py --zip dist/v3.2.0/why-exist-graph-3.2.0.zip
```

## 产物

| 文件 | 大小 | SHA-256 |
|---|---|---|
| `why-exist-graph-3.2.0.zip`（63 个文件） | 340991 | `8ad772141d52e93bdff2d8c9a530ca113102b6dc8a7fcee31a4b9c93db19e0ea` |

来源提交：`d5879b3`（manifest 里 `source.commit` / `source.dirty=false`）。

## 本版变更

**`scope_ids` 的顺序确定性**。全项目都承诺「同样输入两次运行字节一致」，
审计 14 片发现的唯一例外就是这条路径。

- **通配展开改成排序输出**：`scope_ids` 的第三段——从工单 `target_ids` 的 `*` 模式
  展开节点——遍历的是 `set`，顺序随 `PYTHONHASHSEED` 变化。审计探针用 4 个种子
  拿到 4 种顺序；而这个列表会被 `work-seed` 原样写进 `target_ids`、被
  `feature-status` 取前几条展示，等于把不确定性写进了状态库。
- **修法**：返回前 `sorted(ids)`。前两段（`feature_nodes`、requirement 前缀）本来就是
  DB 顺序，排序后整体变成字典序——这是可见的顺序变化，所以按 minor 发而非 patch。
- **测试**：跨进程用例，建两个 feature——节点由 a 导入、b 的通配 target 把它们
  「新」拉进作用域（只有一个 feature 时新节点会被 `feature_nodes` 的 DB 顺序盖住，
  测不出问题）。用 `PYTHONHASHSEED` 0/1/2/3 四个子进程比对输出。
  变异验证：改回未排序后该用例直接报「4 种顺序」。

测试：409 → 410。

## 验证

`python tools/preflight.py --release` 十一步全过：

```
回归测试 410 tests OK (skipped=6)
文档一致性 doc_flow PASS
文档完整性 docs PASS
工作树行尾（应为 LF） LF
未定义全局名（运行期 NameError 的前置检查） PASS
契约校验 contract v3.2.0 / schema v9
状态库体检 ok
报告自洽性 PASS
后端集成（可选） 后端集成测试通过：MySQL/MariaDB, PostgreSQL
打包发布 v3.2.0 63 个文件
发布包独立运行 PASS（解压 → up → 五阶段 → gate PASS）
```

## 已知限制

- 排序让 `feature-status` 的「前几条」从 DB 顺序变成字典序；如果某个下游按位置读
  这几条，需要改用 id 匹配而不是下标。
- `apply` 仍然绕过 `target_ids` 写边界；`bite` 仍然无 token、无 target 边界。
- 自制 MySQL 客户端只支持 MariaDB + `mysql_native_password`。
- CHANGELOG 记录 0.1.0 ~ 3.2.0 共 123 个版本，v0.4.1 之后有 10 个 tag。
