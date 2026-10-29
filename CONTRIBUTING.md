# Contributing

感谢贡献！这个项目的核心目标是“**契约只有一处、文档不会漂移、交付门可机械判定**”，
所以提交前请务必跑自动检查。

## 开发环境

- Python ≥ 3.10（只用标准库，无需安装依赖）
- 推荐 PowerShell / bash 均可；Windows 下含 JSON 的参数请用 `@文件路径`

```bash
PYTHONUTF8=1 python scripts/wxg.py verify
PYTHONUTF8=1 python -m unittest discover -s tests -v
```

两条都必须是绿的（当前期望：`ok:true`，`Ran 42 tests ... OK`）。

## 修改契约（重要）

条件、工单、角色、命令、属性键、导出形状、规则文本都定义在 `scripts/wxg_contract.py`。
**不要手改生成块**（`SKILL.md` 的 `<!-- wxg:contract:main:begin/end -->` 与
`references/contract.md` 的 full 块）。正确流程：

1. 修改 `scripts/wxg_contract.py`（必要时同时升 `CONTRACT_VERSION`，schema 变更时升 `SCHEMA_VERSION`）；
2. 重新生成文档块：
   ```bash
   python scripts/wxg.py contract --write SKILL.md --section main
   python scripts/wxg.py contract --write references/contract.md --section full
   ```
3. 若导出渲染器有变，刷新样例：
   ```bash
   python scripts/gen_sample.py --write
   ```
4. 跑 `python scripts/wxg.py verify` 与全量测试；
5. 在 `CHANGELOG.md` 记录契约/schema 变更、破坏性变更与迁移方式。

## 代码约定

- 仅使用 Python 标准库（`argparse`/`sqlite3`/`ast`/`json`/`hashlib`/`uuid`/`tempfile` 等）。
- 新增命令必须：在契约 `COMMANDS` 注册 → 实现 `cmd_<name>` handler → 补 `WRITE_MODES`
  → 至少一个测试；新增 actor/证据规则必须补 `doctor` 检查。
- 失败路径返回非零退出码与可读 error；不要静默吞异常或把内部 traceback 当成功。
- `gate`/`verify`/`slice`/`get`/`find` 必须保持只读。

## 测试

- `tests/test_wxg.py` 使用独立临时状态库；不要依赖工作区里的真实 `.why-exist/`。
- 新增门禁/证据/审计逻辑时，请同时覆盖“反例路径”（例如无证据 judge、跨 generation 证据、越权写入）。
- 本机 Windows 沙箱若复现 `tempfile` 0o700 DACL 问题，技能内的 `make_temp_dir()` 已做规避；
  CI 在 ubuntu/windows 上跑。

## 发版

1. 更新 `VERSION` 与 `scripts/wxg_contract.py` 的 `CONTRACT_VERSION`（schema 变则 `SCHEMA_VERSION`）；
2. 在 `CHANGELOG.md` 写变更；
3. 构建发布包：`python tools/build_release.py`（产出 `dist/v<version>/`，确定性 zip）；
4. 打 tag 并推送：`git tag v<version> && git push origin v<version>`；
   `.github/workflows/release.yml` 会校验并附上 zip 到 GitHub Release。

首次/手动发布到 GitHub（建仓 + 推送 + 打 tag + 发 Release）可用仓库自带脚本：

```bash
export GITHUB_TOKEN="<你的 token>"     # 不要提交/写进仓库
python tools/publish_github.py --dry-run   # 先看计划
python tools/publish_github.py              # 建仓/推送/Release
```

Windows PowerShell：`$env:GITHUB_TOKEN = "<token>"`。也支持 `--owner <org>` / `--repo <name>` /
`--no-release`，详见脚本头部说明。

## PR

- 说明动机、行为变化与验证命令/结果；
- 不要提交 `.why-exist/`、`export/`、`__pycache__`、`dist/` 等本地产物；
- 保持契约生成块与样例由命令生成，而不是手改。

## License

提交的贡献按 [MIT](LICENSE) 许可。
