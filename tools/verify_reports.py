"""报告自洽性检查：同一份状态库，各命令给出的数字要互相吻合。

两种跑法：

    python tools/verify_reports.py --root <状态库> --feature <id>   # 检查已有库
    python tools/verify_reports.py --repo <源码仓> [--depth 2]      # 一键扫描 + derive + 检查

`--repo` 模式会先打印一份仓画像（节点/边/unmapped 占比/组件数/孤立率），再看断言。
它不验证"结论对不对"（那需要外部真值），只验证同一份图在不同命令里的说法是否一致。
这类矛盾不需要人读就能抓：比如 plan 说有环而 cycles 说没有、impact 的 affected 不等于
direct + indirect + changed。

退出码 0 = 全部一致；1 = 至少一条断言失败。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
WXG = SKILL / "scripts" / "wxg.py"
ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}

sys.path.insert(0, str(SKILL / "scripts"))
from whyexist.db import connect, ensure_db  # noqa: E402
from whyexist.errors import Reject  # noqa: E402
from whyexist.temp import make_temp_dir  # noqa: E402
from whyexist.workflow import scope_ids  # noqa: E402


def run(root: Path, *args: str):
    proc = subprocess.run(
        [sys.executable, str(WXG), "--root", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", env=ENV,
    )
    out = proc.stdout.strip()
    if not out.startswith("{"):
        raise SystemExit(f"wxg {' '.join(args)} 没有返回 JSON（exit={proc.returncode}）：{proc.stderr.strip()[:300]}")
    return json.loads(out)


def scan_repo(repo_path: Path, depth: int, exclude: str) -> tuple[Path, str, Path]:
    """把源码仓扫进一个临时库并 derive 出设计层，返回 (root, feature, 临时目录)。"""
    tmp = make_temp_dir("verify-reports-")
    root = tmp / "state"
    feature = "verify"
    run(root, "init")
    run(root, "repo-add", "--id", "repo", "--path", str(repo_path))
    run(
        root, "feature-declare", "--id", feature, "--name", "verify",
        "--statement", "s", "--acceptance", '["a"]', "--constraints", '["c"]',
        "--no-coverage", "--no-conformance",
    )
    prepared = run(root, "import-repo", "--repo", "repo", "--feature", feature, "--prepare")
    scan = run(root, "work-claim", "--role", "scan", "--actor", "verify")
    run(root, "import-repo", "--repo", "repo", "--token", scan["claim_token"])
    run(root, "work-finish", "--token", scan["claim_token"])
    run(root, "work-judge", "--id", scan["work_item_id"], "--verdict", "passed",
        "--role", "audit", "--actor", "auditor")
    print(f"  扫描：{prepared['files']} 文件 / {prepared['nodes']} 节点 / {prepared['edges']} 边")

    run(root, "work-open", "--feature", feature, "--kind", "model-architecture",
        "--target-ids", "component:*")
    arch = run(root, "work-claim", "--role", "model-architecture", "--actor", "verify")
    derive_args = ["derive", "--repo", "repo", "--feature", feature, "--depth", str(depth)]
    if exclude:
        derive_args += ["--exclude", exclude]
    derive_args += ["--apply", "--token", arch["claim_token"]]
    derived = run(root, *derive_args)
    print(
        f"  derive：{derived['components']} 组件 / {derived['depends']} 条依赖"
        f" / 写入 {derived['edges_written']} 条边"
    )
    return root, feature, tmp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="why-exist 报告自洽性检查")
    parser.add_argument("--root", default=None, help="已有状态库目录（与 --repo 二选一）")
    parser.add_argument("--feature", default=None, help="配合 --root 使用的 feature id")
    parser.add_argument("--repo", default=None, help="源码仓路径：自动扫描 + derive + 检查")
    parser.add_argument("--depth", type=int, default=2, help="derive 的目录深度（默认 2）")
    parser.add_argument("--exclude", default="", help="derive 排除的目录前缀，逗号分隔")
    args = parser.parse_args(argv)

    tmp: Path | None = None
    if args.repo:
        root = None
        feature_id = None
        root, feature_id, tmp = scan_repo(Path(args.repo).resolve(), args.depth, args.exclude)
    elif args.root and args.feature:
        root = Path(args.root)
        feature_id = args.feature
    else:
        parser.error("需要 --root + --feature，或 --repo")

    try:
        return _check(Path(root).resolve(), feature_id, args.exclude if args.repo else "")
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
            shutil.rmtree(tmp.parent / "demo-repo", ignore_errors=True)


def _check(root: Path, feature_id: str, exclude: str = "") -> int:
    conn = connect(root)
    try:
        ensure_db(conn)
        feature = conn.execute(
            "SELECT * FROM features WHERE id=?", (feature_id,)
        ).fetchone()
        if feature is None:
            raise SystemExit(f"feature 不存在：{feature_id}")
        scope = set(scope_ids(conn, feature_id))
        depends_edges = [
            row
            for row in conn.execute(
                "SELECT src, dst FROM edges WHERE kind='depends'"
            ).fetchall()
            if row["src"] in scope and row["dst"] in scope
        ]
        profile = {
            "nodes": conn.execute("SELECT COUNT(*) c FROM nodes").fetchone()["c"],
            "edges": conn.execute("SELECT COUNT(*) c FROM edges").fetchone()["c"],
            "unmapped": conn.execute(
                "SELECT COUNT(*) c FROM nodes WHERE unmapped=1"
            ).fetchone()["c"],
            "components": conn.execute(
                "SELECT COUNT(*) c FROM nodes WHERE kind='component'"
            ).fetchone()["c"],
            "code_nodes": conn.execute(
                "SELECT COUNT(*) c FROM nodes WHERE kind IN ('operation','classifier') "
                "AND repo IS NOT NULL AND path IS NOT NULL AND unmapped=0"
            ).fetchone()["c"],
        }
    finally:
        conn.close()

    unmapped_pct = 100.0 * profile["unmapped"] / profile["nodes"] if profile["nodes"] else 0.0
    print(
        f"  画像：{profile['nodes']} 节点 / {profile['edges']} 边"
        f" / unmapped {profile['unmapped']} ({unmapped_pct:.0f}%)"
        f" / {profile['components']} 组件"
    )

    checks: list[tuple[str, bool, str]] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))
        print(("  ok    " if ok else "  FAIL  ") + name + (f"  ({detail})" if detail else ""))

    plan = run(root, "plan", "--feature", feature_id, "--include-unmapped")
    cycles = run(root, "cycles", "--feature", feature_id)
    conformance = run(root, "conformance", "--feature", feature_id)
    orphan = conformance["anchors"]["code_orphan_count"]
    truly = conformance["anchors"]["truly_orphan_count"]
    if profile["code_nodes"]:
        orphan_pct = 100.0 * orphan / profile["code_nodes"]
        print(
            f"        孤立 {orphan} / 代码节点 {profile['code_nodes']}"
            f"（{orphan_pct:.0f}%，其中真孤立 {truly}）"
        )
        if truly and exclude:
            print(
                f"        注：真孤立多为被 --exclude 排除的目录（{exclude}），"
                "derive 不给它们分组，属预期"
            )

    # plan 的 level 是 auto：有设计层 depends 时用设计层，否则退到代码层。cycles 永远只
    # 看设计层（component/port/pattern），所以只有 plan 也用设计层时两者才可比。
    design_level = plan.get("level") == "design"
    if design_level:
        # 1. plan 与 cycles 对"有没有环"的看法必须一致
        check(
            "plan.acyclic 与 cycles.cycle_count 一致",
            (plan["acyclic"] == (cycles["cycle_count"] == 0)),
            f"acyclic={plan['acyclic']} cycle_count={cycles['cycle_count']}",
        )
        # 2. plan 的环成员与 cycles 的成员（忽略自环）必须一致
        plan_cycles = {frozenset(component) for component in plan["cyclic_components"]}
        cycles_members = {
            frozenset(cycle["members"]) for cycle in cycles["cycles"] if len(cycle["members"]) > 1
        }
        check(
            "plan.cyclic_components 与 cycles.members 一致",
            plan_cycles == cycles_members,
            f"plan={len(plan_cycles)} cycles={len(cycles_members)}",
        )
    else:
        print(f"  skip  plan 用代码层（level={plan.get('level')}），与 cycles 的设计层口径不同")

    # 3. cycles 只分析设计层，节点数不会超过 plan 的全量
    check(
        "cycles.node_count 不超过 plan.node_count",
        cycles["node_count"] <= plan["node_count"],
        f"cycles={cycles['node_count']} plan={plan['node_count']}",
    )

    # 4. conformance 的 depends 数等于图里 scope 内的 depends 边数
    check(
        "conformance.structural.depends 等于图内 depends 边数",
        conformance["structural"]["depends"] == len(depends_edges),
        f"conformance={conformance['structural']['depends']} db={len(depends_edges)}",
    )

    # 5. impact 的 affected = changed ∪ direct ∪ indirect
    changed = sorted(scope)[0] if scope else None
    if changed:
        impact = run(root, "impact", "--feature", feature_id, "--changed", changed)
        union = set(impact["changed"]) | set(impact["direct"]) | set(impact["indirect"])
        check(
            "impact.affected = changed ∪ direct ∪ indirect",
            set(impact["affected"]) == union,
            f"affected={len(impact['affected'])} union={len(union)}",
        )

    # 6. feature-status 的 scope_size 等于 scope_ids 大小
    status = run(root, "feature-status", "--id", feature_id)
    check(
        "feature-status.scope_size 等于 scope_ids",
        status["scope_size"] == len(scope),
        f"{status['scope_size']} vs {len(scope)}",
    )

    failed = [name for name, ok, _ in checks if not ok]
    if failed:
        print(f"\n自洽性检查：{len(failed)} 条不一致")
        return 1
    print(f"\n自洽性检查：PASS（{len(checks)} 条）")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Reject as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
