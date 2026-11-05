"""graph_algo 的纯算法测试：不连数据库、不依赖 wxg.py。

运行：python -m unittest discover -s tests -p "test_graph_algo.py" -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.graph_algo as G  # noqa: E402


class NormalizeTest(unittest.TestCase):
    def test_drops_unknown_self_loop_and_duplicate_but_reports(self):
        nodes, edges, dropped = G.normalize(
            ["a", "b", "a"],
            [("a", "b"), ("a", "b"), ("a", "a"), ("a", "zzz")],
        )
        self.assertEqual(["a", "b"], nodes)
        self.assertEqual([("a", "b")], edges)
        self.assertEqual((("a", "zzz"),), dropped.unknown_endpoint)
        self.assertEqual((("a", "a"),), dropped.self_loop)
        self.assertEqual((("a", "b"),), dropped.duplicate)

    def test_empty_graph(self):
        nodes, edges, dropped = G.normalize([], [])
        self.assertEqual([], nodes)
        self.assertEqual([], edges)
        self.assertEqual(G.DanglingEdges(), dropped)


class SccTest(unittest.TestCase):
    def test_dag_components_are_singletons(self):
        components = G.strongly_connected_components(
            ["a", "b", "c"], [("a", "b"), ("b", "c")]
        )
        self.assertEqual(3, len(components))
        self.assertTrue(all(len(component) == 1 for component in components))

    def test_cycle_merges_into_one_component(self):
        components = G.strongly_connected_components(
            ["a", "b", "c"], [("a", "b"), ("b", "c"), ("c", "a")]
        )
        self.assertEqual(1, len(components))
        self.assertEqual({"a", "b", "c"}, set(components[0]))

    def test_disjoint_cycles(self):
        components = G.strongly_connected_components(
            ["a", "b", "c", "d"],
            [("a", "b"), ("b", "a"), ("c", "d"), ("d", "c")],
        )
        self.assertEqual(2, len(components))
        self.assertEqual(
            {frozenset({"a", "b"}), frozenset({"c", "d"})},
            {frozenset(component) for component in components},
        )

    def test_component_order_puts_dependent_first(self):
        # x 依赖环 a<->b：拓扑序里 x 的分量先出现
        components = G.strongly_connected_components(
            ["x", "a", "b"], [("x", "a"), ("a", "b"), ("b", "a")]
        )
        dependent = next(component for component in components if "x" in component)
        dependency = next(component for component in components if "a" in component)
        self.assertLess(components.index(dependent), components.index(dependency))


class TopologicalLayersTest(unittest.TestCase):
    def test_chain_has_one_node_per_layer(self):
        layers = G.topological_layers(["a", "b", "c"], [("a", "b"), ("b", "c")])
        self.assertEqual([["a"], ["b"], ["c"]], layers)

    def test_diamond_shares_middle_layer(self):
        layers = G.topological_layers(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        self.assertEqual([["a"], ["b", "c"], ["d"]], layers)

    def test_isolated_nodes_share_first_layer(self):
        layers = G.topological_layers(["a", "b", "c"], [])
        self.assertEqual([["a", "b", "c"]], layers)

    def test_cycle_raises_with_components(self):
        with self.assertRaises(G.CyclicGraph) as caught:
            G.topological_layers(["a", "b"], [("a", "b"), ("b", "a")])
        self.assertEqual({"a", "b"}, set(caught.exception.components[0]))

    def test_self_loop_raises(self):
        with self.assertRaises(G.CyclicGraph) as caught:
            G.topological_layers(["a"], [("a", "a")])
        self.assertEqual([["a"]], caught.exception.components)


class MaxAntichainTest(unittest.TestCase):
    def test_chain_antichain_is_one(self):
        self.assertEqual(1, G.max_antichain(["a", "b", "c"], [("a", "b"), ("b", "c")]))

    def test_v_shape_antichain_is_two(self):
        self.assertEqual(2, G.max_antichain(["a", "b", "c"], [("a", "b"), ("a", "c")]))

    def test_diamond_antichain_is_two(self):
        self.assertEqual(
            2,
            G.max_antichain(
                ["a", "b", "c", "d"],
                [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
            ),
        )

    def test_independent_nodes_form_full_antichain(self):
        self.assertEqual(4, G.max_antichain(["a", "b", "c", "d"], []))

    def test_two_chains_antichain_is_two(self):
        self.assertEqual(
            2, G.max_antichain(["a", "b", "c", "d"], [("a", "b"), ("c", "d")])
        )

    def test_three_parallel_chains(self):
        nodes = ["a1", "a2", "b1", "b2", "c1", "c2"]
        edges = [("a1", "a2"), ("b1", "b2"), ("c1", "c2")]
        self.assertEqual(3, G.max_antichain(nodes, edges))

    def test_contracts_cycle_into_super_node(self):
        # a<->b 收缩成一个宏节点，c 可与其并行 -> 反链 2
        self.assertEqual(
            2,
            G.max_antichain(["a", "b", "c"], [("a", "b"), ("b", "a")]),
        )

    def test_empty(self):
        self.assertEqual(0, G.max_antichain([], []))


class ReachabilityTest(unittest.TestCase):
    NODES = ["a", "b", "c", "d"]
    EDGES = [("a", "b"), ("b", "c"), ("c", "d")]

    def test_downstream_closure(self):
        self.assertEqual({"b", "c", "d"}, G.reachable(self.NODES, self.EDGES, "a"))

    def test_leaf_has_no_downstream(self):
        self.assertEqual(set(), G.reachable(self.NODES, self.EDGES, "d"))

    def test_upstream_closure(self):
        self.assertEqual(
            {"a", "b", "c"}, G.reachable(self.NODES, self.EDGES, "d", reverse=True)
        )

    def test_unknown_start_is_empty(self):
        self.assertEqual(set(), G.reachable(self.NODES, self.EDGES, "missing"))

    def test_transitive_reachable_matches_reachable(self):
        closure = G.transitive_reachable(self.NODES, self.EDGES)
        for node in self.NODES:
            self.assertEqual(G.reachable(self.NODES, self.EDGES, node), closure[node])


class AnalyzeTest(unittest.TestCase):
    def test_diamond(self):
        result = G.analyze(
            ["a", "b", "c", "d"],
            [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")],
        )
        self.assertTrue(result.acyclic)
        self.assertIsNotNone(result.layers)
        self.assertEqual(2, result.max_antichain)
        self.assertEqual(2, result.parallelism)
        self.assertEqual(3, len(result.layers))

    def test_cyclic(self):
        result = G.analyze(["a", "b"], [("a", "b"), ("b", "a")])
        self.assertFalse(result.acyclic)
        self.assertIsNone(result.layers)
        self.assertEqual(1, len(result.cyclic_components))
        self.assertEqual({"a", "b"}, set(result.cyclic_components[0]))

    def test_self_loop_does_not_collapse_parallelism(self):
        # 递归函数是自环：分层不可用，但不应把整个图的并行度归为 1。
        result = G.analyze(["a", "b"], [("a", "a")])
        self.assertFalse(result.acyclic)
        self.assertIsNone(result.layers)
        self.assertEqual(2, result.parallelism)

    def test_dangling_edges_are_reported_not_swallowed(self):
        result = G.analyze(["a", "b"], [("a", "b"), ("a", "ghost")])
        self.assertEqual((("a", "ghost"),), result.dangling.unknown_endpoint)
        self.assertEqual(1, result.edge_count)

    def test_same_input_is_deterministic(self):
        nodes = ["a", "b", "c", "d", "e"]
        edges = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")]
        self.assertEqual(G.analyze(nodes, edges), G.analyze(nodes, edges))

    def test_component_set_is_order_independent(self):
        nodes = ["a", "b", "c", "d", "e"]
        edges = [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e")]
        forward = {
            frozenset(component)
            for component in G.strongly_connected_components(nodes, edges)
        }
        backward = {
            frozenset(component)
            for component in G.strongly_connected_components(
                list(reversed(nodes)), list(reversed(edges))
            )
        }
        self.assertEqual(forward, backward)


if __name__ == "__main__":
    unittest.main()
