"""07 切片（query / importer / derive）的行为探针。

用途：为 docs/audit/07-query-import.json 里标 gap / partial 的契约提供可复跑证据。
只读源码；运行时在系统临时目录建库，跑完自动清理，不碰项目状态库。

    python docs/audit/_probe_07.py
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WXG = ROOT / "scripts" / "wxg.py"
ENV = dict(os.environ, PYTHONIOENCODING="utf-8", WXG_DB_URL="")

sys.path.insert(0, str(ROOT / "scripts"))
from whyexist.importer import plan_python  # noqa: E402
from whyexist import derive  # noqa: E402


def p(label, value):
    print(f"{label}: {value}")


# ---------------------------------------------------------------- 导入器
def probe_importer(tmp: Path) -> None:
    print("\n== 导入器：认得出什么 ==")
    repo = tmp / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "probe.py").write_text(
        "\n".join([
            "import os",
            "from .helpers import thing",
            "",
            "class Base:",
            "    pass",
            "",
            "VERSION = '1'",
            "",
            "def helper():",
            "    return 1",
            "",
            "class Keeper(Base):",
            "    LIMIT = 3",
            "",
            "    def __init__(self):",
            "        self.conn = None",
            "",
            "    def run(self, xs):",
            "        self.conn = open('x')",
            "        _ = self.conn",
            "        helper()",
            "        os.path.join('a', 'b')",
            "        len(xs)",
            "        data = {'k': 1}",
            "        data['k'].append(1)",
            "        def inner():",
            "            return helper()",
            "        return inner",
            "",
            "async def go():",
            "    return 1",
        ]) + "\n",
        encoding="utf-8",
    )
    info = {"id": "demo", "path": str(repo)}
    nodes, edges = plan_python(info, repo / "probe.py")
    p("节点 kind 集合", sorted({n["kind"] for n in nodes.values()}))
    p("节点", sorted(nodes))
    p("边 kind 集合", sorted({e["kind"] for e in edges.values()}))
    p("边", sorted((e["kind"], e["dst"].rsplit(":", 1)[-1]) for e in edges.values()))
    p("是否出现 reads", any(e["kind"] == "reads" for e in edges.values()))
    p("是否出现 imports", any(e["kind"] == "imports" for e in edges.values()))
    p("是否出现 generalizes/inherits", any(e["kind"] in ("generalizes", "inherits") for e in edges.values()))
    p("import 语句产生了节点", any("os" == n.get("name") or "thing" == n.get("name") for n in nodes.values()))
    p("模块级常量 VERSION 产生节点", any(n.get("name") == "VERSION" for n in nodes.values()))
    p("嵌套函数 inner 产生节点", any(n.get("symbol") == "inner" for n in nodes.values()))
    p("inner 里的 helper() 归到外层 run", any(
        e["kind"] == "calls" and e["dst"].endswith(":helper") and e["src"].endswith("Keeper.run")
        for e in edges.values()))
    p("self.conn 读没有产生 reads 边", not any(e["kind"] == "reads" for e in edges.values()))
    p("裸名 helper() 被解析成本文件函数", any(
        e["kind"] == "calls" and not e["unmapped"] and e["dst"].endswith(":helper")
        for e in edges.values()))

    print("\n== 导入器：id 与路径 ==")
    (repo / "pkg" / "probe.py").write_text("def helper():\n    return 1\n", encoding="utf-8")
    p("rel=probe.py", sorted(plan_python(info, repo / "probe.py")[0])[0])
    p("rel=pkg/probe.py", sorted(plan_python(info, repo / "pkg" / "probe.py")[0])[0])

    print("\n== 导入器：异常路径 ==")
    dup = repo / "dup.py"
    dup.write_text(
        "class A:\n    def one(self):\n        pass\n"
        "class B:\n    def two(self):\n        pass\n"
        "class A:\n    def three(self):\n        pass\n",
        encoding="utf-8")
    try:
        plan_python(info, dup)
        p("重复类名", "未抛异常")
    except Exception as exc:  # noqa: BLE001
        p("重复类名", f"{type(exc).__name__}: {exc}")
    bad = repo / "gbk.py"
    bad.write_bytes("def f():\n    return '中文'\n".encode("gbk"))
    try:
        plan_python(info, bad)
    except Exception as exc:  # noqa: BLE001
        p("非 UTF-8", type(exc).__name__)
    syntax = repo / "syntax.py"
    syntax.write_text("def (:\n", encoding="utf-8")
    try:
        plan_python(info, syntax)
    except Exception as exc:  # noqa: BLE001
        p("语法错误", f"{type(exc).__name__}: {exc}")
    try:
        plan_python(info, HERE / "_probe_07.py")
    except Exception as exc:  # noqa: BLE001
        p("仓外文件", type(exc).__name__)


# ---------------------------------------------------------------- derive 纯函数
def probe_derive() -> None:
    print("\n== derive：纯函数 ==")
    flat = [
        {"id": "operation:demo:a.py:x", "kind": "operation", "path": "a.py"},
        {"id": "operation:demo:b.py:y", "kind": "operation", "path": "b.py"},
    ]
    result = derive.derive_components(flat, [], repo="demo", depth=1)
    p("扁平仓组件", [c["id"] for c in result["components"]])
    p("扁平仓 depends", result["depends"])
    nested = [
        {"id": "operation:demo:pkg/a.py:x", "kind": "operation", "path": "pkg/a.py"},
        {"id": "operation:demo:pkg/sub/c.py:z", "kind": "operation", "path": "pkg/sub/c.py"},
        {"id": "operation:demo:lib/b.py:y", "kind": "operation", "path": "lib/b.py"},
    ]
    for depth in (0, -1, 1, 2):
        p(f"depth={depth} 组件", [c["id"] for c in
                                  derive.derive_components(nested, [], repo="demo", depth=depth)["components"]])
    with_import = derive.derive_components(
        nested, [], repo="demo", depth=1,
        file_dependencies=[("pkg/a.py", "lib/b.py")])
    p("文件级 import -> depends", [(d["src"], d["dst"]) for d in with_import["depends"]])


# ---------------------------------------------------------------- CLI 流程
def cli(root: Path, *args, expect=0):
    proc = subprocess.run([sys.executable, str(WXG), "--root", str(root), *args],
                          capture_output=True, text=True, encoding="utf-8", env=ENV)
    body = proc.stdout.strip() or proc.stderr.strip()
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {"_raw": body}
    if proc.returncode != expect:
        raise SystemExit(f"wxg {' '.join(args)} 退出码 {proc.returncode}，期望 {expect}：{body[:300]}")
    return payload


def probe_cli(tmp: Path) -> None:
    print("\n== CLI：查询 ==")
    root = tmp / "state"
    repo = tmp / "src"
    (repo / "pkg").mkdir(parents=True)
    (repo / "app.py").write_text(
        "class Svc:\n    def run(self):\n        return helper()\n\ndef helper():\n    return 1\n",
        encoding="utf-8")
    (repo / "pkg" / "core.py").write_text(
        "from app import helper\n\nclass Core:\n    def go(self):\n        return helper()\n",
        encoding="utf-8")

    cli(root, "init")
    cli(root, "repo-add", "--id", "demo", "--path", str(repo))
    cli(root, "feature-declare", "--id", "f", "--name", "F", "--statement", "s",
        "--acceptance", '["a"]', "--constraints", '["c"]', "--no-coverage")
    cli(root, "import-repo", "--repo", "demo", "--feature", "f", "--prepare")
    scan = cli(root, "work-claim", "--role", "scan", "--actor", "a1")
    cli(root, "import-repo", "--repo", "demo", "--token", scan["claim_token"])
    cli(root, "work-finish", "--token", scan["claim_token"])
    cli(root, "work-judge", "--id", scan["work_item_id"], "--verdict", "passed", "--actor", "a2")

    p("slice 两个参数都不给", cli(root, "slice", expect=2)["error"])
    empty = cli(root, "slice", "--ids", '["classifier:nope:*"]')
    p("通配未命中的 slice", {k: empty[k] for k in ("nodes", "missing_ids", "patterns")})
    one = cli(root, "slice", "--ids", '["classifier:demo:app.py:Svc"]')
    returned = {n["id"] for n in one["nodes"]}
    p("slice 返回节点", sorted(returned))
    p("slice 边的另一端不在 nodes 里",
      sorted({x for e in one["edges"] for x in (e["src"], e["dst"])} - returned))
    p("slice 节点字段带 attrs_json", "attrs_json" in one["nodes"][0])
    p("slice 固定 depth", one["depth"])
    limited = cli(root, "slice", "--ids", '["operation:demo:app.py:Svc.run","operation:demo:app.py:helper"]',
                  "--limit", "1")
    p("slice --limit 1", {k: limited.get(k) for k in ("nodes_total", "edges_total", "truncated")})
    got = cli(root, "get", "--id", "operation:demo:app.py:helper")["node"]
    p("get 节点字段带 attrs", "attrs" in got and "attrs_json" not in got)
    p("get 不存在节点", cli(root, "get", "--id", "operation:demo:app.py:nope", expect=2)["error"])
    p("find 全量", cli(root, "find")["total"])
    p("find --path-prefix '%'（LIKE 通配泄漏）", cli(root, "find", "--path-prefix", "%")["total"])
    p("find --path-prefix 'pkg/'", [n["id"] for n in cli(root, "find", "--path-prefix", "pkg/")["nodes"]])
    p("find --from-id", [n["id"] for n in
                         cli(root, "find", "--from-id", "operation:demo:app.py:Svc.run")["nodes"]])
    p("find --limit -1", cli(root, "find", "--limit", "-1", expect=2)["error"])
    zero = cli(root, "find", "--limit", "0")
    p("find --limit 0", {"n": len(zero["nodes"]), "total": zero["total"], "truncated": zero["truncated"]})

    conn = sqlite3.connect(root / "graph.sqlite")
    conn.execute("UPDATE nodes SET stale=1 WHERE id='operation:demo:app.py:helper'")
    conn.commit()
    conn.close()
    p("find 含 stale 节点", any(n["id"] == "operation:demo:app.py:helper"
                                for n in cli(root, "find")["nodes"]))
    p("slice 含 stale 节点", [n["id"] for n in
                              cli(root, "slice", "--ids", "operation:demo:app.py:helper")["nodes"]])

    print("\n== CLI：import-file 的文件类型 ==")
    # 单独开一个 feature，避免往已 passed 的 scan 工单里并入 target_ids
    cli(root, "feature-declare", "--id", "g", "--name", "G", "--statement", "s",
        "--acceptance", '["a"]', "--constraints", '["c"]', "--no-coverage")
    notes = repo / "notes.txt"
    notes.write_text("def f():\n    return 1\n", encoding="utf-8")
    p("import-file 非 .py（语法合法）", cli(root, "import-file", "--file", str(notes),
                                           "--feature", "g", "--prepare").get("nodes"))
    gbk = repo / "gbk.py"
    gbk.write_bytes("def g():\n    return '中文'\n".encode("gbk"))
    p("import-file 非 UTF-8", cli(root, "import-file", "--file", str(gbk),
                                  "--feature", "g", "--prepare", expect=2)["error"][:60])

    print("\n== CLI：derive ==")
    # 清掉查询探针里手工置的 stale，下面只观察 derive 自己标 stale 的节点
    conn = sqlite3.connect(root / "graph.sqlite")
    conn.execute("UPDATE nodes SET stale=0")
    conn.commit()
    conn.close()
    cli(root, "work-open", "--feature", "f", "--kind", "model-architecture",
        "--target-ids", '["component:demo:*"]')
    arch = cli(root, "work-claim", "--role", "model-architecture", "--actor", "a3")
    p("--apply 缺 token", cli(root, "derive", "--repo", "demo", "--feature", "f",
                              "--apply", expect=2)["error"])
    dry = cli(root, "derive", "--repo", "demo", "--feature", "f", "--depth", "1")
    p("dry-run", {"components": [c["id"] for c in dry["components"]],
                  "depends": [(d["src"], d["dst"]) for d in dry["depends"]]})
    p("dry-run 成员包含 target_ids 外的代码节点",
      sorted({m for c in dry["components"] for m in c["members"]}))
    # 人工声明一个与 derive 同 id 的组件，观察 apply 是否覆盖 origin/attrs
    cli(root, "upsert-node", "--token", arch["claim_token"], "--data",
        '{"id":"component:demo:pkg","kind":"component","name":"手工组件",'
        '"attrs":{"duty":"人工职责：包边界"}}')
    # 把一个代码节点置 stale，观察它是否还参与分组
    conn = sqlite3.connect(root / "graph.sqlite")
    conn.execute("UPDATE nodes SET stale=1 WHERE id='operation:demo:app.py:helper'")
    conn.commit()
    conn.close()
    stale_dry = cli(root, "derive", "--repo", "demo", "--feature", "f", "--depth", "1")
    p("dry-run 是否把 stale 代码节点分进组件",
      sorted({m for c in stale_dry["components"] for m in c["members"]
              if m == "operation:demo:app.py:helper"}))
    first = cli(root, "derive", "--repo", "demo", "--feature", "f", "--apply",
                "--token", arch["claim_token"], "--depth", "1")
    p("apply", {k: first[k] for k in ("components", "depends", "nodes_written", "edges_written")})
    conn = sqlite3.connect(root / "graph.sqlite")
    row = conn.execute("SELECT origin, name, attrs_json FROM nodes WHERE id='component:demo:pkg'").fetchone()
    member_edges = conn.execute(
        "SELECT src, dst FROM edges WHERE kind='contains' AND dst='operation:demo:app.py:helper'").fetchall()
    targets = json.loads(conn.execute(
        "SELECT target_ids FROM work_items WHERE id=?", (arch["work_item_id"],)).fetchone()[0])
    conn.close()
    p("同名人工组件被 apply 后的 origin/name/attrs", row)
    p("工单 target_ids", targets)
    p("apply 写的成员 contains 边", member_edges)
    p("成员 id 是否在 target_ids 内", [
        dst for _src, dst in member_edges
        if not any(t == dst or (t.endswith("*") and dst.startswith(t[:-1])) for t in targets)])
    # 清掉手工置的 stale，让后面的重跑观察只反映 derive 自己的行为
    conn = sqlite3.connect(root / "graph.sqlite")
    conn.execute("UPDATE nodes SET stale=0 WHERE id='operation:demo:app.py:helper'")
    conn.commit()
    conn.close()
    second = cli(root, "derive", "--repo", "demo", "--feature", "f", "--apply",
                 "--token", arch["claim_token"], "--depth", "1", "--exclude", "pkg")
    p("换 --exclude 重跑", {k: second[k] for k in ("components", "depends", "stale_derived")})
    conn = sqlite3.connect(root / "graph.sqlite")
    depends_edges = conn.execute("SELECT src, dst FROM edges WHERE kind='depends'").fetchall()
    contains_edges = conn.execute("SELECT src, dst FROM edges WHERE kind='contains'").fetchall()
    stale = {r[0] for r in conn.execute("SELECT id FROM nodes WHERE stale=1").fetchall()}
    conn.close()
    p("重跑后留下的 depends 边", depends_edges)
    p("重跑后留下的 contains 边", contains_edges)
    p("旧边指向 stale 组件", [e for e in depends_edges + contains_edges if e[0] in stale or e[1] in stale])
    third = cli(root, "derive", "--repo", "demo", "--feature", "f", "--apply",
                "--token", arch["claim_token"], "--exclude", "app.py,pkg")
    p("0 组件 apply", {k: third[k] for k in
                       ("mode", "components", "depends", "nodes_written", "stale_derived")})


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="wxg-probe07-"))
    try:
        probe_importer(tmp)
        probe_derive()
        probe_cli(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
