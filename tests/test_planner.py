"""planner 的纯函数测试：不连数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.planner as P  # noqa: E402


def rows(*triples):
    return list(triples)


class SelectEdgesTest(unittest.TestCase):
    def test_filters_by_kind_and_scope(self):
        nodes = ["a", "b"]
        edges = rows(
            ("a", "b", "depends"),
            ("a", "b", "calls"),
            ("a", "ghost", "depends"),
            ("x", "y", "depends"),
        )
        # 一端在界内的边保留（由内核报为悬空）；两端都在界外的丢弃
        self.assertEqual(
            [("a", "b"), ("a", "ghost")],
            P.select_edges(nodes, edges, P.DESIGN_EDGE_KINDS),
        )

    def test_deduplicates_and_sorts(self):
        nodes = ["a", "b", "c"]
        edges = rows(("b", "c", "calls"), ("a", "c", "calls"), ("b", "c", "calls"))
        self.assertEqual([("a", "c"), ("b", "c")], P.select_edges(nodes, edges, P.CODE_EDGE_KINDS))


class BuildPlanTest(unittest.TestCase):
    def test_prefers_design_edges_when_present(self):
        nodes = ["a", "b", "c"]
        edge_rows = rows(("a", "b", "depends"), ("b", "c", "calls"))
        plan = P.build_plan(nodes, edge_rows, feature_id="feat-x")
        self.assertEqual("design", plan["level"])
        self.assertEqual(1, plan["edge_count"])

    def test_falls_back_to_code_when_design_graph_is_empty(self):
        nodes = ["a", "b", "c"]
        edge_rows = rows(("a", "b", "calls"), ("b", "c", "calls"))
        plan = P.build_plan(nodes, edge_rows)
        self.assertEqual("code", plan["level"])
        self.assertEqual(2, plan["edge_count"])
        self.assertEqual([["a"], ["b"], ["c"]], plan["layers"])

    def test_explicit_level_is_respected(self):
        nodes = ["a", "b"]
        edge_rows = rows(("a", "b", "depends"), ("a", "b", "calls"))
        plan = P.build_plan(nodes, edge_rows, level="code")
        self.assertEqual("code", plan["level"])
        self.assertEqual(1, plan["edge_count"])

    def test_invalid_level_rejected(self):
        with self.assertRaises(ValueError):
            P.build_plan(["a"], [], level="nonsense")

    def test_parallelism_matches_antichain_for_dag(self):
        # a1,a2 各自独立，都汇入 b：最大反链 2
        nodes = ["a1", "a2", "b"]
        edge_rows = rows(("a1", "b", "depends"), ("a2", "b", "depends"))
        plan = P.build_plan(nodes, edge_rows)
        self.assertTrue(plan["acyclic"])
        self.assertEqual(2, plan["max_antichain"])
        self.assertEqual(2, plan["parallelism"])
        self.assertEqual([["a1", "a2"], ["b"]], plan["layers"])

    def test_cycle_is_reported_and_layers_null(self):
        nodes = ["a", "b"]
        edge_rows = rows(("a", "b", "depends"), ("b", "a", "depends"))
        plan = P.build_plan(nodes, edge_rows)
        self.assertFalse(plan["acyclic"])
        self.assertIsNone(plan["layers"])
        self.assertEqual([["a", "b"]], plan["cyclic_components"])

    def test_bottleneck_for_dag_mentions_antichain(self):
        nodes = ["a1", "a2", "b"]
        edge_rows = rows(("a1", "b", "depends"), ("a2", "b", "depends"))
        plan = P.build_plan(nodes, edge_rows)
        self.assertIn("最大反链", plan["bottleneck"])
        self.assertIn("2 层", plan["bottleneck"])

    def test_bottleneck_for_cycle_names_the_component_size(self):
        nodes = ["a", "b"]
        edge_rows = rows(("a", "b", "depends"), ("b", "a", "depends"))
        plan = P.build_plan(nodes, edge_rows)
        self.assertIn("最大环", plan["bottleneck"])
        self.assertIn("2 个节点必须串行", plan["bottleneck"])

    def test_bottleneck_for_self_loop_says_layers_unavailable(self):
        plan = P.build_plan(["a"], rows(("a", "a", "depends")))
        self.assertIn("单点自环", plan["bottleneck"])

    def test_dangling_edges_are_reported(self):
        nodes = ["a", "b"]
        edge_rows = rows(("a", "ghost", "depends"))
        plan = P.build_plan(nodes, edge_rows, level="design")
        self.assertEqual([["a", "ghost"]], plan["dangling"]["unknown_endpoint"])

    def test_output_is_deterministic(self):
        nodes = ["c", "a", "b"]
        edge_rows = rows(("a", "b", "depends"))
        first = P.build_plan(nodes, edge_rows)
        second = P.build_plan(list(reversed(nodes)), list(reversed(edge_rows)))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
