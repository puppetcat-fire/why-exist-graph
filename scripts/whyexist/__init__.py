"""why-exist 引擎包。

公开入口：

    from whyexist import Engine

    with Engine("path/to/.why-exist") as engine:
        engine.plan("feat-x")              # 并行规划：SCC / 波次 / 最大反链
        engine.brief("work-id")            # 盲化任务书
        engine.blind_check("work-id", ...) # 盲执行校验
        engine.gate("feat-x")              # 交付门（只读）

纯函数层（``graph_algo`` / ``planner`` / ``briefing`` / ``blind``）不碰数据库，
也可以单独使用。
"""

from __future__ import annotations

from .blind import check_output
from .briefing import build_brief
from .engine import Engine
from .graph_algo import (
    CyclicGraph,
    GraphAnalysis,
    analyze,
    max_antichain,
    reachable,
    strongly_connected_components,
    topological_layers,
    transitive_reachable,
)
from .planner import build_plan

__all__ = [
    "CyclicGraph",
    "Engine",
    "GraphAnalysis",
    "analyze",
    "build_brief",
    "build_plan",
    "check_output",
    "max_antichain",
    "reachable",
    "strongly_connected_components",
    "topological_layers",
    "transitive_reachable",
]

__version__ = "2.23.0"
