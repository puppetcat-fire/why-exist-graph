"""Engine：why-exist 的库入口。

    from whyexist import Engine

    with Engine(".why-exist") as engine:
        engine.plan("feat-x")
        engine.brief("work-id")
        engine.blind_check("work-id", {"nodes": [...], "edges": [...]})
        engine.gate("feat-x")

Engine 只负责取数与组装；判定逻辑在 ``planner`` / ``briefing`` / ``blind`` 三个
纯函数模块。

约定：每个方法都只读，不改变状态库；需要写库的流程仍走 CLI 命令。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from . import blind, impact as impact_mod, planner
from .commands_compiler import _brief_payload
from .commands_gates import cmd_gate
from .contract import C
from .db import connect, ensure_db
from .workflow import ensure_feature, scope_ids

__all__ = ["Engine"]


class Engine:
    """一个状态库的编程入口；每次操作复用同一条连接。"""

    def __init__(self, root, *, db_url: str | None = None):
        self._root = Path(root)
        self._db_url = db_url
        self._conn = None

    # ---------------------------------------------------------- 生命周期

    def connect(self):
        """建立并返回状态库连接（首次调用时校验库已初始化）。"""
        if self._conn is not None:
            return self._conn
        if self._db_url:
            os.environ["WXG_DB_URL"] = self._db_url
        self._conn = connect(self._root)
        ensure_db(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    # ---------------------------------------------------------- 取数

    def _feature(self, feature_id: str) -> dict:
        return ensure_feature(self.connect(), feature_id)

    def _edge_rows(self) -> list[tuple[str, str, str]]:
        rows = self.connect().execute("SELECT src, dst, kind FROM edges").fetchall()
        return [(row["src"], row["dst"], row["kind"]) for row in rows]

    # ---------------------------------------------------------- 编译器 pass

    def plan(self, feature: str, *, level: str = "auto", include_unmapped: bool = False) -> dict:
        """从 feature 依赖图算波次、最大反链与理论并行上限。

        默认排除 ``unmapped`` 节点：它们多半是内置调用（len/range/...），
        纳入会把并行度顶到假值。
        """
        spec = self._feature(feature)
        conn = self.connect()
        scope = scope_ids(conn, spec["id"])
        unmapped = {
            row["id"]
            for row in conn.execute("SELECT id, unmapped FROM nodes").fetchall()
            if row["unmapped"]
        }
        excluded = 0 if include_unmapped else sum(1 for node in scope if node in unmapped)
        if not include_unmapped:
            scope = [node for node in scope if node not in unmapped]
        stale = {
            row["id"]
            for row in conn.execute("SELECT id FROM nodes WHERE stale=1").fetchall()
        }
        stale_excluded = sum(1 for node in scope if node in stale)
        scope = [node for node in scope if node not in stale]
        node_kinds = {
            row["id"]: row["kind"]
            for row in conn.execute("SELECT id, kind FROM nodes").fetchall()
        }
        result = planner.build_plan(
            scope,
            self._edge_rows(),
            level=level,
            feature_id=spec["id"],
            node_kinds=node_kinds,
        )
        result["excluded_unmapped"] = excluded
        result["excluded_stale"] = stale_excluded
        return result

    def brief(self, work_id: str) -> dict:
        """生成一张工单的盲化任务书。"""
        return _brief_payload(self.connect(), work_id)

    def blind_check(self, work_id: str, output: dict) -> dict:
        """校验一次盲执行产出是否越界、是否引用未声明依赖、kind 是否合规。"""
        brief = self.brief(work_id)
        return blind.check_output(
            brief=brief,
            output=output,
            known_node_kinds=[kind["kind"] for kind in C.NODE_KINDS],
            known_edge_kinds=[kind["kind"] for kind in C.EDGE_KINDS],
        )

    def gate(self, feature: str) -> dict:
        """只读计算交付门结果（PASS / FAIL）。"""
        return cmd_gate(self.connect(), SimpleNamespace(feature=feature, json=True))

    def impact(self, feature: str, changed: list[str]) -> dict:
        """计算一次改动的闭包：受影响节点、需求覆盖、跨 feature 影响。"""
        spec = self._feature(feature)
        conn = self.connect()
        scope = scope_ids(conn, spec["id"])
        rows = conn.execute("SELECT src, dst, kind FROM edges").fetchall()
        edge_rows = [(row["src"], row["dst"], row["kind"]) for row in rows]
        node_rows = conn.execute("SELECT id, kind FROM nodes").fetchall()
        node_kinds = {row["id"]: row["kind"] for row in node_rows}
        features = conn.execute("SELECT id FROM features ORDER BY id").fetchall()
        all_scopes = {row["id"]: scope_ids(conn, row["id"]) for row in features}
        return impact_mod.build_impact(
            feature_id=spec["id"],
            scope=scope,
            changed=changed,
            edge_rows=edge_rows,
            node_kinds=node_kinds,
            all_scopes=all_scopes,
        )
