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

版本号不在包内声明：唯一真源是仓库根的 ``VERSION`` 文件（打包后在包根）。
历史上这里维护过一份 ``__version__`` 副本，每次都落后于实际版本（最后停在
2.23.0），且全仓没有任何读取方，已删除。需要版本请读 ``VERSION`` 或跑
``python tools/check_docs.py``。
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
