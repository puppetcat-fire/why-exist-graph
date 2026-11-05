"""并行规划：把设计图变成可执行的波次与理论并行上限。

这个模块是纯函数层：输入节点 id 与边记录，不碰数据库。取数由 CLI 层完成，
这样引擎包不会反向 import 入口脚本（避免 ``__main__`` / 模块双份实例）。

两级依赖图：

- ``design``：节点是构件/设计元素，边是 ``depends``。图质量取决于是否有人
  显式写了依赖；空图会得出"全部可并行"，因此 ``auto`` 在无设计边时退到代码层。
- ``code``：节点是操作，边是 ``calls`` / ``reads`` / ``writes``。由扫描器产生，
  信息量大但粒度细。

设计层还支持按节点 kind 过滤：代码节点混进设计层会把反链顶到「节点数」，
让并行度失去意义。调用方传入 ``node_kinds`` 时，``design`` 层只保留
``DESIGN_NODE_KINDS``。
"""

from __future__ import annotations

from . import graph_algo

__all__ = [
    "CODE_EDGE_KINDS",
    "DESIGN_EDGE_KINDS",
    "DESIGN_NODE_KINDS",
    "LEVELS",
    "build_plan",
    "select_edges",
]

#: 设计层依赖边：a -> b 表示 a 依赖 b。
DESIGN_EDGE_KINDS: tuple[str, ...] = ("depends",)

#: 代码层依赖边：调用、读、写都意味着执行顺序约束。
CODE_EDGE_KINDS: tuple[str, ...] = ("calls", "reads", "writes")

#: 设计层参与的节点 kind；其余（operation / classifier 等代码节点）不参与。
DESIGN_NODE_KINDS: tuple[str, ...] = ("component", "port", "pattern")

LEVELS: tuple[str, ...] = ("auto", "design", "code")

_EDGE_KINDS_BY_LEVEL = {
    "design": DESIGN_EDGE_KINDS,
    "code": CODE_EDGE_KINDS,
}


def select_edges(
    nodes: list[str],
    edge_rows: list[tuple[str, str, str]],
    kinds: tuple[str, ...],
) -> list[tuple[str, str]]:
    """从 ``(src, dst, kind)`` 记录里选出与作用域相关的依赖边。

    只保留**至少一端在作用域内**的边：一端在界外的边是"依赖了未纳入本次规划的
    节点"，这是重要信号，交给 :func:`graph_algo.analyze` 作为悬空边报告；两端
    都在界外的边与本次规划无关，直接丢弃。

    返回去重并排序后的 ``(src, dst)``，保证输出确定。
    """
    scope = set(nodes)
    selected = {
        (src, dst)
        for src, dst, kind in edge_rows
        if kind in kinds and (src in scope or dst in scope)
    }
    return sorted(selected)


def build_plan(
    nodes: list[str],
    edge_rows: list[tuple[str, str, str]],
    *,
    level: str = "auto",
    feature_id: str | None = None,
    node_kinds: dict[str, str] | None = None,
) -> dict:
    """生成并行规划报告。

    ``level="auto"`` 时优先用设计层；没有 ``depends`` 边就退到代码层，并在
    输出里标明实际用了哪一级——避免把"没有依赖信息"误读成"全部可并行"。

    ``node_kinds`` 提供 ``id -> kind``；给出时设计层只保留 ``DESIGN_NODE_KINDS``，
    防止代码节点把反链顶到节点数。
    """
    if level not in LEVELS:
        raise ValueError(f"未知的规划层级：{level}（可选 {', '.join(LEVELS)}）")
    ordered_nodes = sorted(dict.fromkeys(nodes))

    chosen = level
    if level == "auto":
        design_edges = select_edges(ordered_nodes, edge_rows, DESIGN_EDGE_KINDS)
        if design_edges:
            chosen = "design"
            edges = design_edges
        else:
            chosen = "code"
            edges = select_edges(ordered_nodes, edge_rows, CODE_EDGE_KINDS)
    else:
        edges = select_edges(ordered_nodes, edge_rows, _EDGE_KINDS_BY_LEVEL[level])

    if chosen == "design" and node_kinds is not None:
        design = {
            node for node in ordered_nodes if node_kinds.get(node) in DESIGN_NODE_KINDS
        }
        ordered_nodes = [node for node in ordered_nodes if node in design]
        edges = [(src, dst) for src, dst in edges if src in design and dst in design]

    analysis = graph_algo.analyze(ordered_nodes, edges)

    # parallelism 这一个数字有两种来源，读者分不清：无环时是最大反链，有环时是最大
    # 强连通分量的大小。直接写清楚它受限于什么，省得把"3"读成"只能并行做 3 件事"。
    blocking = [component for component in analysis.cyclic_components if len(component) > 1]
    if analysis.acyclic:
        bottleneck = f"无环：最大反链 {analysis.max_antichain} 个节点可同时做"
        if analysis.layers is not None:
            widest = max(len(layer) for layer in analysis.layers)
            bottleneck += f"（{len(analysis.layers)} 层，最宽 {widest} 个）"
    elif blocking:
        largest = max(blocking, key=len)
        shown = ", ".join(largest[:5]) + ("..." if len(largest) > 5 else "")
        bottleneck = f"受限于最大环：{len(largest)} 个节点必须串行（{shown}）"
    else:
        bottleneck = "只有单点自环：不阻断并行，但拓扑分层不可用"

    return {
        "feature": feature_id,
        "level": chosen,
        "node_count": analysis.node_count,
        "edge_count": analysis.edge_count,
        "acyclic": analysis.acyclic,
        "cyclic_components": analysis.cyclic_components,
        "layers": analysis.layers,
        "layer_count": len(analysis.layers) if analysis.layers is not None else None,
        "max_antichain": analysis.max_antichain,
        "parallelism": analysis.parallelism,
        "bottleneck": bottleneck,
        "dangling": {
            "unknown_endpoint": [list(edge) for edge in analysis.dangling.unknown_endpoint],
            "self_loop": [list(edge) for edge in analysis.dangling.self_loop],
            "duplicate": [list(edge) for edge in analysis.dangling.duplicate],
        },
    }
