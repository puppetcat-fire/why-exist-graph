"""cycles 的纯函数测试：不连数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.cycles as C  # noqa: E402


class FindCyclesTest(unittest.TestCase):
    def test_acyclic_graph_has_no_cycles(self):
        self.assertEqual([], C.find_cycles(["a", "b", "c"], [("a", "b"), ("b", "c")]))

    def test_two_node_cycle_reports_both_edges(self):
        cycles = C.find_cycles(["a", "b"], [("a", "b"), ("b", "a")])
        self.assertEqual(1, len(cycles))
        self.assertEqual(["a", "b"], cycles[0]["members"])
        pairs = {(edge["src"], edge["dst"]) for edge in cycles[0]["edges"]}
        self.assertEqual({("a", "b"), ("b", "a")}, pairs)

    def test_three_node_cycle_reports_three_edges(self):
        edges = [("a", "b"), ("b", "c"), ("c", "a"), ("a", "c")]
        cycles = C.find_cycles(["a", "b", "c"], edges)
        self.assertEqual(1, len(cycles))
        self.assertEqual(["a", "b", "c"], cycles[0]["members"])
        # 环内所有边都列出（a->c 也在 SCC 内，属于某条环）
        self.assertEqual(4, len(cycles[0]["edges"]))

    def test_evidence_is_attached(self):
        evidence = {("a", "b"): [["a.py", "b.py"]], ("b", "a"): [["b.py", "a.py"]]}
        cycles = C.find_cycles(["a", "b"], [("a", "b"), ("b", "a")], evidence)
        by_pair = {(edge["src"], edge["dst"]): edge["evidence"] for edge in cycles[0]["edges"]}
        self.assertEqual([["a.py", "b.py"]], by_pair[("a", "b")])

    def test_self_loop_is_reported_separately(self):
        cycles = C.find_cycles(["rec"], [("rec", "rec")])
        self.assertEqual(1, len(cycles))
        self.assertEqual(["rec"], cycles[0]["members"])
        self.assertEqual([], cycles[0]["edges"])
        self.assertEqual(1, len(cycles[0]["self_loops"]))

    def test_unknown_endpoints_are_ignored(self):
        cycles = C.find_cycles(["a"], [("a", "ghost"), ("ghost", "a")])
        self.assertEqual([], cycles)

    def test_multiple_disjoint_cycles(self):
        edges = [("a", "b"), ("b", "a"), ("c", "d"), ("d", "c")]
        cycles = C.find_cycles(["a", "b", "c", "d"], edges)
        self.assertEqual(2, len(cycles))


class MinimalBreakSetsTest(unittest.TestCase):
    def test_acyclic_has_no_break_sets(self):
        result = C.minimal_break_sets(["a", "b", "c"], [("a", "b"), ("b", "c")])
        self.assertEqual([], result["break_sets"])

    def test_two_node_cycle_needs_one_edge(self):
        result = C.minimal_break_sets(["a", "b"], [("a", "b"), ("b", "a")])
        # 断任意一条都能破环，所以有两个 size=1 的候选
        self.assertEqual(2, len(result["break_sets"]))
        self.assertEqual(1, result["break_sets"][0]["size"])

    def test_three_node_cycle_needs_one_edge(self):
        edges = [("a", "b"), ("b", "c"), ("c", "a")]
        result = C.minimal_break_sets(["a", "b", "c"], edges)
        self.assertEqual(1, result["break_sets"][0]["size"])
        # 三条边各能单独破环，所以有三个候选
        self.assertEqual(3, len(result["break_sets"]))

    def test_three_overlapping_two_cycles_need_three_edges(self):
        # httpie 的结构：a<->b、a<->c、b<->c 叠加成 3-环
        edges = [
            ("a", "b"), ("b", "a"),
            ("a", "c"), ("c", "a"),
            ("b", "c"), ("c", "b"),
        ]
        result = C.minimal_break_sets(["a", "b", "c"], edges)
        self.assertEqual(3, result["break_sets"][0]["size"])

    def test_self_loop_break_set(self):
        result = C.minimal_break_sets(["rec"], [("rec", "rec")])
        self.assertEqual(1, len(result["break_sets"]))
        self.assertEqual([["rec", "rec"]], result["break_sets"][0]["edges"])

    def test_truncated_when_too_many_edges(self):
        nodes = [f"n{i}" for i in range(25)]
        edges = [(nodes[i], nodes[i + 1]) for i in range(24)] + [(nodes[-1], nodes[0])]
        result = C.minimal_break_sets(nodes, edges)
        self.assertTrue(result["truncated"])


class AdviseBreakEdgesTest(unittest.TestCase):
    def test_preferred_when_in_break_set_and_no_lost(self):
        edges = [("a", "b"), ("b", "a")]
        result = C.advise_break_edges(["a", "b"], edges, {("a", "b"): 0, ("b", "a"): 0})
        self.assertEqual("preferred", result["advice"][0]["verdict"])

    def test_acceptable_when_break_loses_reachability(self):
        edges = [("a", "b"), ("b", "a")]
        result = C.advise_break_edges(["a", "b"], edges, {("a", "b"): 1, ("b", "a"): 0})
        verdicts = [item["verdict"] for item in result["advice"]]
        self.assertIn("preferred", verdicts)
        self.assertIn("acceptable", verdicts)
        # preferred 排在 acceptable 前面
        self.assertEqual("preferred", result["advice"][0]["verdict"])

    def test_advice_sorted_by_verdict_then_lost(self):
        edges = [("a", "b"), ("b", "a")]
        result = C.advise_break_edges(["a", "b"], edges, {("a", "b"): 5, ("b", "a"): 1})
        lost = [item["lost_count"] for item in result["advice"] if item["verdict"] == "acceptable"]
        self.assertEqual(sorted(lost), lost)


class BreakSetCostsTest(unittest.TestCase):
    def test_cost_of_breaking_two_node_cycle(self):
        edges = [("a", "b"), ("b", "a")]
        sets = [{"size": 1, "edges": [["a", "b"]]}]
        costs = C.break_set_costs(["a", "b"], edges, sets)
        self.assertEqual(1, costs[0]["lost_pairs"])
        self.assertEqual(["a", "b"], costs[0]["affected_nodes"])

    def test_cost_zero_when_alternative_path_exists(self):
        # a -> b 有两条路径（a->b 和 a->c->b），断 a->b 不丢可达
        edges = [("a", "b"), ("a", "c"), ("c", "b")]
        sets = [{"size": 1, "edges": [["a", "b"]]}]
        costs = C.break_set_costs(["a", "b", "c"], edges, sets)
        self.assertEqual(0, costs[0]["lost_pairs"])


class CycleShapeTest(unittest.TestCase):
    def test_parent_child_cycle(self):
        members = ["component:r:pkg", "component:r:pkg.sub"]
        self.assertEqual("parent-child", C.cycle_shape(members))

    def test_sibling_cycle(self):
        members = ["component:r:a", "component:r:b"]
        self.assertEqual("sibling", C.cycle_shape(members))

    def test_non_component_members_are_sibling(self):
        members = ["component:r:a", "operation:r:x.py:f"]
        self.assertEqual("sibling", C.cycle_shape(members))

    def test_self_loop_shape(self):
        result = C.find_cycles(["a"], [("a", "a")])
        self.assertEqual("self-loop", result[0]["shape"])

    def test_multi_node_cycle_carries_shape(self):
        edges = [("component:r:pkg", "component:r:pkg.sub"),
                 ("component:r:pkg.sub", "component:r:pkg")]
        result = C.find_cycles(["component:r:pkg", "component:r:pkg.sub"], edges)
        self.assertEqual("parent-child", result[0]["shape"])

    def test_guidance_matches_shape(self):
        self.assertIn("分层", C.cycle_guidance("parent-child"))
        self.assertIn("平级", C.cycle_guidance("sibling"))
        self.assertIn("递归", C.cycle_guidance("self-loop"))
        self.assertEqual("", C.cycle_guidance("unknown"))

    def test_parent_child_guidance_says_not_to_cut_edges(self):
        edges = [("component:r:pkg", "component:r:pkg.sub"),
                 ("component:r:pkg.sub", "component:r:pkg")]
        cyc = C.find_cycles(["component:r:pkg", "component:r:pkg.sub"], edges)[0]
        self.assertTrue(cyc["guidance"])
        self.assertIn("不要用断边", cyc["guidance"])


if __name__ == "__main__":
    unittest.main()
