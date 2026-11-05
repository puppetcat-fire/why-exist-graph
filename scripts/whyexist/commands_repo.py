"""仓库与导入命令：init / up / repo-* / import-* / derive / promote / sync / sample。"""

from __future__ import annotations

import argparse
import ast
import json
import os
import random
import sys
from pathlib import Path

from . import derive
from .commands_gates import cmd_gate
from .contract import C
from .db import connect, ensure_db, init_db, migrate_schema
from .errors import Reject
from .graph import (
    check_attrs,
    check_kind,
    check_node_id,
    edge_id,
    find_repo,
    get_node,
    repo_rows,
    upsert_edge,
    upsert_node,
)
from .importer import plan_python
from .jsonio import dumps, load_json_arg, loads, utc_now
from .work import (
    append_evidence,
    get_work,
    get_work_by_token,
    insert_work,
    require_role,
    require_targets,
    require_token,
    target_match,
    work_id,
)
from .workflow import actor_value, ensure_feature, get_feature, scope_ids

def cmd_init(conn, args):
    migrated = init_db(conn)
    backend = getattr(conn, "dialect", "sqlite")
    if backend != "sqlite":
        url = db_url()
        db_label = re.sub(r"//([^:/@]+):[^@]*@", r"//\1:***@", url)
    else:
        db_label = str(args.root_path / "graph.sqlite")
    return {
        "root": str(args.root_path),
        "db": db_label,
        "backend": backend,
        "schema_version": C.SCHEMA_VERSION,
        "contract_version": C.CONTRACT_VERSION,
        "migrated": migrated,
    }


def cmd_up(conn, args):
    """一条命令立起工作区：init + demo 仓 + demo feature + 第一次 gate。

    ``conn`` 传 None：本命令要能在未初始化的目录里工作，自己负责连接与提交。
    不自动裁决——gate 只给当前真实结果（通常 FAIL 并列出缺项），工单仍要显式
    领取、提交、审计。重复执行幂等，不会重置已有 feature。
    """
    root = args.root_path
    conn = connect(root)
    try:
        init_db(conn)
        conn.commit()

        repo_path: Path | None = None
        if args.template == "standard" or args.path:
            repo_path = Path(args.path).resolve() if args.path else root.parent / "demo-repo"
            if not args.path:
                repo_path.mkdir(parents=True, exist_ok=True)
                sample = repo_path / "demo.py"
                if not sample.exists():
                    sample.write_text('def ping():\n    return "pong"\n', encoding="utf-8")
            cmd_repo_add(
                conn,
                argparse.Namespace(id=args.repo, path=str(repo_path), language="python"),
            )
            conn.commit()

        feature_id = args.feature
        created_feature = get_feature(conn, feature_id) is None
        if created_feature:
            cmd_feature_declare(
                conn,
                argparse.Namespace(
                    id=feature_id,
                    name="Demo 功能",
                    statement="一个最小可跑的功能声明。",
                    acceptance=json.dumps(["gate 能给出结果"], ensure_ascii=False),
                    constraints=json.dumps(["不改产品代码"], ensure_ascii=False),
                    coverage_epsilon=None,
                    no_coverage=True,
                    drift_limit=None,
                    conformance=False,
                    no_conformance=False,
                ),
            )
            conn.commit()

        gate = cmd_gate(conn, argparse.Namespace(feature=feature_id, json=True))
        return {
            "root": str(root),
            "template": args.template,
            "repo": {"id": args.repo, "path": str(repo_path)} if repo_path else None,
            "feature": {"id": feature_id, "created": created_feature},
            "gate_result": gate["result"],
            "gate": gate,
            "next": [
                f"wxg import-file --file <源码文件> --feature {feature_id} --prepare"
                "   # scan 工单在这一步才创建",
                "wxg work-claim --role scan --actor agent-scan",
                "wxg brief --work <工单id>",
                "wxg blind-check --work <工单id> --result <产出.json>",
                f"wxg gate --feature {feature_id}",
            ],
        }
    finally:
        conn.close()


def cmd_repo_add(conn, args):
    path = Path(args.path).resolve()
    if not path.is_dir():
        raise Reject(f"仓路径不存在或不是目录：{path}")
    if args.language != "python":
        raise Reject("当前版本只内置 Python 导入器；repo-add --language 仅支持 python")
    try:
        conn.execute(
            "INSERT INTO repos(id, path, language, created_at) VALUES(?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET path=excluded.path, language=excluded.language",
            (args.id, str(path), args.language, utc_now()),
        )
    except Exception as exc:
        if not _is_integrity_error(exc):
            raise
        raise Reject(f"仓登记冲突：path {path} 已被其它 repo id 占用（{exc}）") from exc
    return {"action": "upsert", "repo": args.id, "path": str(path), "language": args.language}


def cmd_repo_list(conn, args):
    return {"repos": repo_rows(conn)}


def cmd_import_file(conn, args):
    absolute = Path(args.file).resolve()
    if not absolute.is_file():
        raise Reject(f"文件不存在：{absolute}")
    repo = find_repo(conn, absolute)
    if repo["language"] != "python":
        raise Reject(
            f"当前版本只内置 Python 导入器；仓 {repo['id']} 登记为 {repo['language']}，"
            "无法按文件导入。请改用 upsert-node/upsert-edge，或按 design.md 的边界扩展导入器"
        )
    nodes, edges = plan_python(repo, absolute)
    # 防御性校验：导入器生成的 id 必须合法；否则 prepare/写库都不应把非法 id 落进
    # target_ids / feature_nodes（否则 doctor 会报一堆 feature-node-missing）。
    for payload in nodes.values():
        check_kind(payload["kind"])
        check_node_id(payload["kind"], payload["id"])
    node_ids = sorted(nodes)
    rel = absolute.resolve().relative_to(Path(repo["path"]).resolve()).as_posix()
    # 同 repo+path 下已有的旧节点：本次重扫如果没再出现，说明代码里已删除/改名。
    existing_ids = sorted(
        row["id"]
        for row in conn.execute("SELECT id FROM nodes WHERE repo=? AND path=?", (repo["id"], rel)).fetchall()
    )
    stale_ids = [node_id for node_id in existing_ids if node_id not in nodes]
    if args.prepare:
        if not args.feature:
            raise Reject("--prepare 需要 --feature")
        feature = ensure_feature(conn, args.feature)
        targets = sorted(set(node_ids) | set(stale_ids))
        opened = insert_work(conn, feature["id"], feature["generation"], "scan", targets, [], merge=True)
        for node_id in targets:
            conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (feature["id"], node_id))
        return {
            "mode": "prepare",
            "repo": repo["id"],
            "work": opened,
            "nodes": len(nodes),
            "edges": len(edges),
            "stale_candidates": len(stale_ids),
        }
    item = require_token(conn, args.token)
    require_role(item, "import-file")
    require_targets(item, sorted(set(node_ids) | set(stale_ids)))
    inserted = updated = edges_written = 0
    for node_id in node_ids:
        existing = get_node(conn, node_id)
        existed = existing is not None
        upsert_node(conn, nodes[node_id], merge_attrs=True, existing=existing)
        inserted += 0 if existed else 1
        updated += 1 if existed else 0
    # 批量插 feature_nodes：逐节点插会多一倍 SQL，大仓上是纯开销
    conn.executemany(
        "INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)",
        [(item["feature_id"], node_id) for node_id in node_ids],
    )
    for payload in edges.values():
        existed = conn.execute("SELECT 1 FROM edges WHERE id=?", (payload["id"],)).fetchone() is not None
        upsert_edge(conn, payload)
        edges_written += 0 if existed else 1
    stale_marked = 0
    for node_id in stale_ids:
        stale_marked += conn.execute("UPDATE nodes SET stale=1 WHERE id=? AND stale<>1", (node_id,)).rowcount
        conn.execute("INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)", (item["feature_id"], node_id))
    # 扫描写入不再把每个节点 id 追加进 evidence_ids：大仓下 list 每文件重序列化是
    # O(N²)，而节点范围已由 target_ids 覆盖；finish 的“evidence ⊆ targets”检查对空列表仍成立。
    return {
        "mode": "write",
        "repo": repo["id"],
        "nodes_inserted": inserted,
        "nodes_updated": updated,
        "edges_inserted": edges_written,
        "stale_marked": stale_marked,
        "stale_nodes": stale_ids,
        "work": item["id"],
    }


def cmd_import_repo(conn, args):
    """批量导入已登记仓的全部 Python 文件；--prepare 只预列到 scan 工单。

    写入语义与 import-file 一致（同一工单内更新而非新增、消失的节点标 stale），
    只是把遍历与校验合并成一次调用，避免对中型仓逐文件敲几百次 CLI。
    """
    repo_row = conn.execute("SELECT * FROM repos WHERE id=?", (args.repo,)).fetchone()
    if repo_row is None:
        raise Reject(f"仓未登记：{args.repo}")
    repo = dict(repo_row)
    if repo["language"] != "python":
        raise Reject(
            f"当前版本只内置 Python 导入器；仓 {repo['id']} 登记为 {repo['language']}"
        )
    base = Path(repo["path"]).resolve()
    all_nodes: dict[str, dict] = {}
    all_edges: dict[str, dict] = {}
    stale_ids: list[str] = []
    files = 0
    for path in sorted(base.rglob("*.py")):
        if not path.is_file():
            continue
        rel = path.relative_to(base)
        if any(part.startswith(".") for part in rel.parts):
            continue
        files += 1
        try:
            nodes, edges = plan_python(repo, path)
        except Reject as exc:
            raise Reject(f"{rel.as_posix()}: {exc}") from exc
        for payload in nodes.values():
            check_kind(payload["kind"])
            check_node_id(payload["kind"], payload["id"])
        all_nodes.update(nodes)
        all_edges.update(edges)
        existing = {
            row["id"]
            for row in conn.execute(
                "SELECT id FROM nodes WHERE repo=? AND path=?",
                (repo["id"], rel.as_posix()),
            ).fetchall()
        }
        stale_ids.extend(sorted(existing - set(nodes)))

    node_ids = sorted(all_nodes)
    targets = sorted(set(node_ids) | set(stale_ids))
    if args.prepare:
        if not args.feature:
            raise Reject("--prepare 需要 --feature")
        feature = ensure_feature(conn, args.feature)
        opened = insert_work(
            conn, feature["id"], feature["generation"], "scan", targets, [], merge=True
        )
        for node_id in targets:
            conn.execute(
                "INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)",
                (feature["id"], node_id),
            )
        return {
            "mode": "prepare",
            "repo": repo["id"],
            "work": opened,
            "files": files,
            "nodes": len(all_nodes),
            "edges": len(all_edges),
            "stale_candidates": len(stale_ids),
        }

    item = require_token(conn, args.token)
    require_role(item, "import-file")
    require_targets(item, targets)
    inserted = updated = 0
    for node_id in node_ids:
        existing = get_node(conn, node_id)
        existed = existing is not None
        upsert_node(conn, all_nodes[node_id], merge_attrs=True, existing=existing)
        inserted += 0 if existed else 1
        updated += 1 if existed else 0
    conn.executemany(
        "INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)",
        [(item["feature_id"], node_id) for node_id in node_ids],
    )
    edges_written = 0
    for payload in all_edges.values():
        existed = (
            conn.execute("SELECT 1 FROM edges WHERE id=?", (payload["id"],)).fetchone()
            is not None
        )
        upsert_edge(conn, payload)
        edges_written += 0 if existed else 1
    stale_marked = 0
    for node_id in stale_ids:
        stale_marked += conn.execute(
            "UPDATE nodes SET stale=1 WHERE id=? AND stale<>1", (node_id,)
        ).rowcount
        conn.execute(
            "INSERT OR IGNORE INTO feature_nodes(feature_id, node_id) VALUES(?,?)",
            (item["feature_id"], node_id),
        )
    return {
        "mode": "write",
        "repo": repo["id"],
        "files": files,
        "nodes_inserted": inserted,
        "nodes_updated": updated,
        "edges_inserted": edges_written,
        "stale_marked": stale_marked,
        "work": item["id"],
    }


def _module_to_rel(module: str, repo_root: Path) -> str | None:
    """把 ``a.b.c`` 形式的模块名映射为仓内相对文件路径；找不到返回 None。"""
    candidate = repo_root / Path(*module.split("."))
    py_file = candidate.with_suffix(".py")
    if py_file.is_file():
        return py_file.relative_to(repo_root).as_posix()
    init = candidate / "__init__.py"
    if init.is_file():
        return init.relative_to(repo_root).as_posix()
    return None


def _resolve_relative_import(
    source_rel: str, module: str | None, level: int, repo_root: Path
) -> str | None:
    """把相对导入解析成仓内相对文件路径。

    - ``from . import x``（level=1, module=None）→ ``<当前包>/x.py``；
    - ``from .json import dumps``（level=1, module="json"）→ ``<当前包>/json/__init__.py``；
    - ``from ..pkg import y``（level=2）先上跳一层包。

    解析不到（目录越界、文件不存在）返回 ``None``，由调用方跳过。
    """
    package = list(Path(source_rel).parts[:-1])
    if level - 1 > len(package):
        return None
    if level > 1:
        package = package[: len(package) - (level - 1)]
    if module:
        package += module.split(".")
    if not package:
        return None
    candidate = repo_root.joinpath(*package)
    for target in (candidate.with_suffix(".py"), candidate / "__init__.py"):
        if target.is_file():
            return target.relative_to(repo_root).as_posix()
    return None


def _import_file_pairs(repo_root: Path) -> list[tuple[str, str]]:
    """解析仓内所有 .py 的 import，返回 ``(源文件, 目标文件)`` 相对路径对。

    绝对导入与相对导入都解析；解析不到的文件静默跳过，由 import-repo 的
    parse_errors 负责报告。
    """
    pairs: list[tuple[str, str]] = []
    for path in sorted(repo_root.rglob("*.py")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        source = rel.as_posix()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _module_to_rel(alias.name, repo_root)
                    if target:
                        pairs.append((source, target))
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    if node.module:
                        target = _module_to_rel(node.module, repo_root)
                        if target:
                            pairs.append((source, target))
                    continue
                if node.module:
                    target = _resolve_relative_import(source, node.module, node.level, repo_root)
                    if target:
                        pairs.append((source, target))
                    continue
                # from . import a, b —— 每个 name 都是一个子模块
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    target = _resolve_relative_import(source, alias.name, node.level, repo_root)
                    if target:
                        pairs.append((source, target))
    return pairs


def cmd_derive(conn, args):
    """从代码图推导 component/depends 候选；默认 dry-run，--apply 才写库。

    写入的节点标 ``origin=derived``：它们是可被咬合质疑的候选，不是已确认设计。
    """

    repo_row = conn.execute("SELECT * FROM repos WHERE id=?", (args.repo,)).fetchone()
    if repo_row is None:
        raise Reject(f"仓未登记：{args.repo}")
    repo = dict(repo_row)
    feature = ensure_feature(conn, args.feature)

    node_rows = conn.execute(
        "SELECT id, kind, name, path FROM nodes WHERE repo=? AND unmapped=0 ORDER BY id",
        (repo["id"],),
    ).fetchall()
    nodes = [dict(row) for row in node_rows]
    edge_rows = conn.execute("SELECT src, dst, kind FROM edges").fetchall()
    edges = [(row["src"], row["dst"], row["kind"]) for row in edge_rows]
    exclude_dirs = tuple(
        item.strip() for item in (args.exclude or "").split(",") if item.strip()
    )
    file_dependencies = _import_file_pairs(Path(repo["path"]).resolve())
    result = derive.derive_components(
        nodes,
        edges,
        repo=repo["id"],
        depth=args.depth,
        file_dependencies=file_dependencies,
        exclude_dirs=exclude_dirs,
    )

    if not args.apply:
        payload = {"mode": "dry-run", "feature": feature["id"], **result}
        if len(result["components"]) <= 1:
            # 单层包仓（如 src/pkg/*.py 没有子目录）无论 depth 都只能得到 1 组；
            # 这是正确的分组，但输出看起来像"这就是全部组件"，给条提示避免误读。
            payload["hint"] = (
                f"只推导出 {len(result['components'])} 个组件：目录层级不足以分组"
                "（--depth 只在目录多于一层时才有区别）。扁平仓的 derive 没有信息量，"
                "可用 --exclude 去掉测试/文档后手动声明组件。"
            )
        return payload

    item = require_token(conn, args.token)
    require_role(item, "derive")
    component_ids = [component["id"] for component in result["components"]]
    require_targets(item, component_ids)
    # 本次推导没再出现的旧候选标 stale：重跑 derive（换了 depth / exclude）时，
    # 上一轮的组件不应继续留在图里参与规划。
    existing_derived = {
        row["id"]
        for row in conn.execute(
            "SELECT id FROM nodes WHERE id LIKE ? AND origin='derived' AND stale=0",
            (f"component:{repo['id']}:%",),
        ).fetchall()
    }
    stale_derived = sorted(existing_derived - set(component_ids))
    for node_id in stale_derived:
        conn.execute("UPDATE nodes SET stale=1 WHERE id=?", (node_id,))
    nodes_written = 0
    edges_written = 0
    for component in result["components"]:
        upsert_node(
            conn,
            {
                "id": component["id"],
                "kind": "component",
                "name": component["name"],
                "repo": repo["id"],
                "origin": "derived",
                "attrs": {
                    "x_strategy": result["strategy"],
                    "x_depth": result["depth"],
                    "x_path": component["path"],
                },
                "feature_id": feature["id"],
            },
        )
        nodes_written += 1
        for member in component["members"]:
            upsert_edge(
                conn, {"src": component["id"], "dst": member, "kind": "contains"}
            )
            edges_written += 1
    for edge in result["depends"]:
        evidence = edge.get("evidence") or []
        upsert_edge(
            conn,
            {
                "src": edge["src"],
                "dst": edge["dst"],
                "kind": "depends",
                # 依赖证据（文件对/节点对）落库：环分析要能追到具体 import。
                "attrs": {"x_evidence": [list(pair) for pair in evidence[:20]]},
            },
        )
        edges_written += 1
    return {
        "mode": "apply",
        "feature": feature["id"],
        "repo": repo["id"],
        "components": len(result["components"]),
        "depends": len(result["depends"]),
        "nodes_written": nodes_written,
        "edges_written": edges_written,
        "stale_derived": len(stale_derived),
    }


def cmd_promote(conn, args):
    """把 origin=derived 的候选节点提升为 declared，并记录裁决者。

    derived 是"从代码推出来的假设"，declared 是"人裁决过的设计"。提升本身不阻塞
    修改——它只留下"谁在什么时候确认过"的痕迹。
    """
    feature = ensure_feature(conn, args.feature)
    item = require_token(conn, args.token)
    require_role(item, "promote")
    require_targets(item, [args.node])
    node = get_node(conn, args.node)
    if node is None:
        raise Reject(f"节点不存在：{args.node}")
    if node["origin"] != "derived":
        raise Reject(
            f"只有 origin=derived 的候选可以提升；节点 {args.node} 当前 origin={node['origin']}"
        )
    actor = actor_value(args)
    upsert_node(
        conn,
        {
            "id": args.node,
            "kind": node["kind"],
            "origin": "declared",
            "attrs": {"x_promoted_by": actor, "x_promoted_at": utc_now()},
            "feature_id": feature["id"],
        },
        merge_attrs=True,
    )
    return {"promoted": args.node, "feature": feature["id"], "actor": actor}


def cmd_sync(conn, args):
    repo_row = conn.execute("SELECT * FROM repos WHERE id=?", (args.repo,)).fetchone()
    if repo_row is None:
        raise Reject(f"仓未登记：{args.repo}")
    repo = dict(repo_row)
    limit = args.limit if args.limit is not None else 50
    if limit < 0:
        raise Reject("--limit 必须是非负整数")
    base = Path(repo["path"])
    planned: dict[str, dict] = {}
    parse_errors = []
    files = 0
    for path in sorted(base.rglob("*.py")):
        if not path.is_file():
            continue
        files += 1
        try:
            nodes, _edges = plan_python(repo, path)
        except Reject as exc:
            parse_errors.append({"file": path.relative_to(base).as_posix(), "error": str(exc)})
            continue
        planned.update(nodes)
    db_nodes = {
        row["id"]: dict(row)
        for row in conn.execute("SELECT * FROM nodes WHERE repo=?", (repo["id"],)).fetchall()
    }
    missing = sorted(set(db_nodes) - set(planned))
    new = sorted(set(planned) - set(db_nodes))
    changed = []
    for node_id in sorted(set(db_nodes) & set(planned)):
        db = db_nodes[node_id]
        plan = planned[node_id]
        if (db["name"], db["line_start"], db["line_end"], db["symbol"]) != (
            plan.get("name"), plan.get("line_start"), plan.get("line_end"), plan.get("symbol")
        ):
            changed.append({
                "node": node_id,
                # unmapped 是内置/外部调用的聚合节点（len/range/...），它们的行号变化
                # 不代表设计改动；标出来，让读者能过滤掉这类噪声。
                "unmapped": bool(db["unmapped"]),
                "db": {"name": db["name"], "line_start": db["line_start"], "line_end": db["line_end"]},
                "plan": {"name": plan.get("name"), "line_start": plan.get("line_start"), "line_end": plan.get("line_end")},
            })
    stale = sorted(node_id for node_id, node in db_nodes.items() if node["stale"])
    return {
        "repo": repo["id"],
        "path": repo["path"],
        "files": files,
        "db_nodes": len(db_nodes),
        "planned_nodes": len(planned),
        "missing_count": len(missing),
        "missing": missing[:limit],
        "new_count": len(new),
        "new": new[:limit],
        "changed_count": len(changed),
        # unmapped 变化单独计数：设计层关心的改动数量是 changed_count - unmapped。
        "changed_unmapped_count": sum(1 for item in changed if item["unmapped"]),
        "changed": changed[:limit],
        "stale_count": len(stale),
        "stale": stale[:limit],
        "parse_errors": parse_errors,
        "truncated": any(len(items) > limit for items in (missing, new, changed, stale)),
    }


def cmd_sample(conn, args):
    if bool(args.repo) == bool(args.feature):
        raise Reject("--repo 与 --feature 二选一：按仓抽或按 feature 作用域抽")
    if args.feature:
        feature = ensure_feature(conn, args.feature)
        scope = set(scope_ids(conn, feature["id"]))
        rows = [
            row
            for row in conn.execute(
                "SELECT id, kind, name, repo, path, symbol, line_start FROM nodes ORDER BY id"
            ).fetchall()
            if row["id"] in scope
        ]
        if not rows:
            raise Reject(f"feature {args.feature} 的作用域里还没有节点，先 import-file 或写图")
        source = "feature"
    else:
        rows = conn.execute(
            "SELECT id, kind, name, repo, path, symbol, line_start FROM nodes WHERE repo=? ORDER BY id",
            (args.repo,),
        ).fetchall()
        if not rows:
            raise Reject(f"仓 {args.repo} 里还没有可抽取的节点，先 import-file")
        source = "repo"
    rng = random.Random(args.seed) if args.seed is not None else random.Random()
    row = rng.choice([dict(item) for item in rows])
    return {"sample": row, "seed": args.seed, "source": source, "candidates": len(rows)}


# feature/工单命令已搬进 whyexist.commands_feature；这里 re-export。
from whyexist.commands_feature import (  # noqa: E402
    _require_write,
    _resolve_subject,
    cmd_change_diff,
    cmd_change_open,
    cmd_feature_declare,
    cmd_feature_list,
    cmd_feature_register,
    cmd_feature_status,
    cmd_work_claim,
    cmd_work_finish,
    cmd_work_judge,
    cmd_work_list,
    cmd_work_open,
    cmd_work_seed,
    record_judge_history,
    work_seed,
)


# 图写入与证据命令已搬进 whyexist.commands_graph；这里 re-export。
from whyexist.commands_graph import (  # noqa: E402
    cmd_bind,
    cmd_bite,
    cmd_evidence_list,
    cmd_evidence_record,
    cmd_retract,
    cmd_upsert_edge,
    cmd_upsert_node,
    prune_work_refs,
)


# 覆盖/一致性/调谐命令已搬进 whyexist.commands_gates；这里 re-export。
from whyexist.commands_gates import (  # noqa: E402
    _pending_counts,
    apply_safe_actions,
    cmd_conformance,
    cmd_coverage,
    cmd_reconcile,
    cmd_serve,
    reconcile_feature,
)


# 编译器命令已搬进 whyexist.commands_compiler；这里 re-export。
from whyexist.commands_compiler import (  # noqa: E402
    _brief_payload,
    cmd_apply,
    cmd_blind_check,
    cmd_brief,
    cmd_conflicts,
    cmd_cycles,
    cmd_impact,
    cmd_patch,
    cmd_plan,
)




# cmd_gate 也已搬进 whyexist.commands_gates。
from whyexist.commands_gates import cmd_gate  # noqa: E402

# 导出/校验/doctor 命令已搬进 whyexist.commands_misc；这里 re-export。
from whyexist.commands_misc import (  # noqa: E402
    cmd_contract,
    cmd_doctor,
    cmd_export,
    cmd_role_prompt,
    cmd_verify,
    doctor_report,
)


