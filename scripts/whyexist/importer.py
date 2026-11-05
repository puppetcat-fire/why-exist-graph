"""Python AST 导入器：把源码文件解析成节点/边。

只支持 Python；认不出的调用按 I7 建 unmapped 节点，不静默丢弃。
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from .errors import Reject
from .graph import edge_id

# ------------------------------------------------------------------ 导入器（Python AST）

def _node_id(kind: str, repo: str, rel: str, symbol: str) -> str:
    return f"{kind}:{repo}:{rel}:{symbol}"


def plan_python(repo: dict, absolute: Path) -> tuple[dict, dict]:
    """返回 (nodes, edges)，都是 id -> payload 的字典。"""
    rel = absolute.resolve().relative_to(Path(repo["path"]).resolve()).as_posix()
    source = absolute.read_text(encoding="utf-8-sig")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise Reject(f"Python 语法无法解析：{exc}") from exc
    nodes: dict[str, dict] = {}
    edges: dict[str, dict] = {}

    def add_node(payload):
        nodes[payload["id"]] = payload
        return payload["id"]

    def add_edge(kind, src, dst, line=None, unmapped=False):
        if src not in nodes or dst not in nodes:
            return
        eid = edge_id(kind, src, dst)
        edges[eid] = {
            "id": eid,
            "kind": kind,
            "src": src,
            "dst": dst,
            "evidence_path": rel,
            "evidence_line": line,
            "unmapped": unmapped,
        }

    class_ops: dict[str, dict[str, str]] = {}

    for top in tree.body:
        if isinstance(top, ast.ClassDef):
            cid = add_node({
                "id": _node_id("classifier", repo["id"], rel, top.name),
                "kind": "classifier",
                "name": top.name,
                "repo": repo["id"],
                "path": rel,
                "symbol": top.name,
                "line_start": top.lineno,
                "line_end": getattr(top, "end_lineno", top.lineno),
                "attrs": {"x_lang": "python"},
                "origin": "scan",
            })
            class_ops[top.name] = {}
            for member in top.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    symbol = f"{top.name}.{member.name}"
                    oid = add_node({
                        "id": _node_id("operation", repo["id"], rel, symbol),
                        "kind": "operation",
                        "name": member.name,
                        "repo": repo["id"],
                        "path": rel,
                        "symbol": symbol,
                        "line_start": member.lineno,
                        "line_end": getattr(member, "end_lineno", member.lineno),
                        "attrs": {"x_lang": "python"},
                        "origin": "scan",
                    })
                    class_ops[top.name][member.name] = oid
                    add_edge("contains", cid, oid, member.lineno)
                elif isinstance(member, ast.Assign):
                    for target in member.targets:
                        if isinstance(target, ast.Name):
                            pid = add_node({
                                "id": _node_id("property", repo["id"], rel, f"{top.name}.{target.id}"),
                                "kind": "property",
                                "name": target.id,
                                "repo": repo["id"],
                                "path": rel,
                                "symbol": f"{top.name}.{target.id}",
                                "line_start": member.lineno,
                                "line_end": member.lineno,
                                "attrs": {"x_lang": "python"},
                                "origin": "scan",
                            })
                            add_edge("contains", cid, pid, member.lineno)
        elif isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            oid = add_node({
                "id": _node_id("operation", repo["id"], rel, top.name),
                "kind": "operation",
                "name": top.name,
                "repo": repo["id"],
                "path": rel,
                "symbol": top.name,
                "line_start": top.lineno,
                "line_end": getattr(top, "end_lineno", top.lineno),
                "attrs": {"x_lang": "python"},
                "origin": "scan",
            })

    def walk_calls(class_name: str | None, op_id: str, func: ast.AST):
        def unmapped_call(display: str, note: str, line, key: str | None = None):
            # 未解析调用按名字聚合：同一文件里多个 len()/range() 只建一个节点。
            # 旧实现把行号放进 id（@21:len），代码一移动就整批伪 missing/new，
            # 重构或格式化都会污染回扫结果；行号改记在 line_start/line_end。
            key = key or display
            target = _node_id("operation", repo["id"], rel, key)
            if target not in nodes:
                add_node({
                    "id": target,
                    "kind": "operation",
                    "name": display,
                    "repo": repo["id"],
                    "path": rel,
                    "symbol": display,
                    "line_start": line,
                    "line_end": line,
                    "attrs": {"x_note": note},
                    "origin": "scan",
                    "unmapped": 1,
                })
            add_edge("calls", op_id, target, line, unmapped=True)

        for node in ast.walk(func):
            if not isinstance(node, ast.Call):
                continue
            func_expr = node.func
            line = getattr(node, "lineno", None)
            if isinstance(func_expr, ast.Attribute) and isinstance(func_expr.value, ast.Name):
                receiver = func_expr.value.id
                name = func_expr.attr
                if receiver == "self" and class_name and name in class_ops.get(class_name, {}):
                    add_edge("calls", op_id, class_ops[class_name][name], line)
                else:
                    unmapped_call(f"{receiver}.{name}", "未解析的接收者调用", line)
            elif isinstance(func_expr, ast.Name):
                name = func_expr.id
                target = class_ops.get("__module__", {}).get(name)
                if target:
                    add_edge("calls", op_id, target, line)
                else:
                    candidate = _node_id("operation", repo["id"], rel, name)
                    if candidate in nodes:
                        add_edge("calls", op_id, candidate, line)
                    else:
                        # 裸名调用认不出（如内置函数/外部导入）：按 I7 建 unmapped 节点+边。
                        unmapped_call(name, "未解析的裸名调用", line)
            else:
                # 链式属性/下标/复杂表达式调用（如 self.conn.execute(...)、data['k'].append(...)）：
                # 同样认不出，按 I7 建 unmapped 节点+边，不静默丢弃。
                try:
                    display = ast.unparse(func_expr)
                except Exception:  # pragma: no cover - 防御性
                    display = type(func_expr).__name__
                # 节点 id 只允许安全字符：unparse 文本可能含 ()[]' 等，用清洗串+短 hash 防碰撞。
                safe = re.sub(r"[^A-Za-z0-9._@/\-]+", "_", display).strip("_")[:60] or "call"
                key = f"{safe}:{hashlib.sha1(display.encode('utf-8')).hexdigest()[:8]}"
                unmapped_call(display, "未解析的链式/复杂调用", line, key=key)

    module_ops: dict[str, str] = {}
    for top in tree.body:
        if isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            module_ops[top.name] = _node_id("operation", repo["id"], rel, top.name)
    class_ops["__module__"] = module_ops

    # 第二遍：self.attr 赋值 -> property + writes；调用 -> calls
    for top in tree.body:
        if isinstance(top, ast.ClassDef):
            for member in top.body:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    op_id = class_ops[top.name][member.name]
                    for node in ast.walk(member):
                        if isinstance(node, ast.Assign):
                            for target in node.targets:
                                if (
                                    isinstance(target, ast.Attribute)
                                    and isinstance(target.value, ast.Name)
                                    and target.value.id == "self"
                                ):
                                    pid = _node_id("property", repo["id"], rel, f"{top.name}.{target.attr}")
                                    if pid not in nodes:
                                        add_node({
                                            "id": pid,
                                            "kind": "property",
                                            "name": target.attr,
                                            "repo": repo["id"],
                                            "path": rel,
                                            "symbol": f"{top.name}.{target.attr}",
                                            "line_start": node.lineno,
                                            "line_end": node.lineno,
                                            "attrs": {"x_lang": "python"},
                                            "origin": "scan",
                                        })
                                    add_edge("writes", op_id, pid, node.lineno)
                    walk_calls(top.name, op_id, member)
        elif isinstance(top, (ast.FunctionDef, ast.AsyncFunctionDef)):
            walk_calls(None, module_ops[top.name], top)

    return nodes, edges


