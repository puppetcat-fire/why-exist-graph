"""impact 的纯函数测试：不连数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.impact as I  # noqa: E402


NODES = {
    "requirement:feat-a:main": "requirement",
    "use_case:feat-a:uc": "use_case",
    "component:feat-a:x": "component",
    "component:feat-a:y": "component",
    "component:feat-a:orphan": "component",
}

# x -> y（x 依赖 y）；use_case 通过 satisfies 挂到 requirement；x 通过 associates 挂到用例。
EDGES = [
    ("component:feat-a:x", "component:feat-a:y", "depends"),
    ("use_case:feat-a:uc", "requirement:feat-a:main", "satisfies"),
    ("component:feat-a:x", "use_case:feat-a:uc", "associates"),
]


def impact(changed, *, feature="feat-a", scope=None, all_scopes=None):
    return I.build_impact(
        feature_id=feature,
        scope=scope if scope is not None else list(NODES),
        changed=changed,
        edge_rows=EDGES,
        node_kinds=NODES,
        all_scopes=all_scopes,
    )


class DirectIndirectTest(unittest.TestCase):
    """affected 按跳数拆成 direct / indirect。"""

    def _impact(self, edge_rows, changed):
        nodes = sorted({n for row in edge_rows for n in row[:2]})
        return I.build_impact(
            feature_id="f",
            scope=nodes,
            changed=changed,
            edge_rows=edge_rows,
            node_kinds={n: "component" for n in nodes},
        )

    def test_one_hop_is_direct(self):
        result = self._impact([("x", "y", "depends")], ["y"])
        self.assertEqual(["x"], result["direct"])
        self.assertEqual([], result["indirect"])

    def test_multi_hop_is_indirect(self):
        rows = [("x", "m", "depends"), ("m", "y", "depends")]
        result = self._impact(rows, ["y"])
        self.assertEqual(["m"], result["direct"])
        self.assertEqual(["x"], result["indirect"])
        self.assertEqual(["m", "x", "y"], result["affected"])

    def test_diamond_uses_shortest_hop(self):
        rows = [
            ("b", "a", "depends"),
            ("c", "a", "depends"),
            ("d", "b", "depends"),
            ("d", "c", "depends"),
        ]
        result = self._impact(rows, ["a"])
        self.assertEqual(["b", "c"], result["direct"])
        self.assertEqual(["d"], result["indirect"])


class BuildImpactTest(unittest.TestCase):
    def test_changing_dependency_affects_dependents(self):
        result = impact(["component:feat-a:y"])
        self.assertEqual(["component:feat-a:x", "component:feat-a:y"], result["affected"])
        self.assertTrue(result["closed"])  # x 挂在 use_case -> requirement 上

    def test_forward_closure_is_what_changed_depends_on(self):
        result = impact(["component:feat-a:x"])
        self.assertEqual(["component:feat-a:y"], result["depends_on"])

    def test_requirement_hit_is_reported(self):
        result = impact(["component:feat-a:y"])
        self.assertEqual(["requirement:feat-a:main"], result["requirements"])

    def test_orphan_change_is_uncovered(self):
        # orphan 与原图没有依赖边，也连不到任何 requirement
        result = impact(["component:feat-a:orphan"])
        self.assertFalse(result["closed"])
        self.assertEqual(["component:feat-a:orphan"], result["uncovered"])

    def test_requirement_node_itself_counts_as_covered(self):
        result = impact(["requirement:feat-a:main"])
        self.assertEqual(["requirement:feat-a:main"], result["requirements"])
        self.assertTrue(result["closed"])

    def test_cross_feature_is_flagged_with_owner(self):
        result = impact(
            ["component:feat-a:y"],
            scope=["component:feat-a:y"],
            all_scopes={
                "feat-a": ["component:feat-a:y"],
                "feat-b": ["component:feat-a:x"],
            },
        )
        self.assertEqual(
            [{"node": "component:feat-a:x", "features": ["feat-b"]}],
            result["cross_feature"],
        )

    def test_non_dependency_edges_do_not_propagate(self):
        # associates / satisfies 不是依赖边，不会被当成影响传播
        result = impact(["use_case:feat-a:uc"])
        self.assertEqual(["use_case:feat-a:uc"], result["affected"])

    def test_empty_changed_set(self):
        result = impact([])
        self.assertEqual([], result["affected"])
        self.assertTrue(result["closed"])

    def test_is_deterministic(self):
        first = impact(["component:feat-a:y", "component:feat-a:x"])
        second = impact(["component:feat-a:x", "component:feat-a:y"])
        self.assertEqual(first, second)


class EdgeRemovalImpactTest(unittest.TestCase):
    def test_chain_loses_downstream(self):
        edges = [("a", "b", "depends"), ("b", "c", "depends")]
        rows = I.edge_removal_impact(["a", "b", "c"], edges, {("a", "b")})
        self.assertEqual(1, len(rows))
        self.assertEqual(["b", "c"], rows[0]["lost_reachable"])

    def test_alternative_path_keeps_reachability(self):
        # a 还能经 c 到 b，断 a->b 不丢可达
        edges = [("a", "b", "depends"), ("a", "c", "depends"), ("c", "b", "depends")]
        rows = I.edge_removal_impact(["a", "b", "c"], edges, {("a", "b")})
        self.assertEqual([], rows[0]["lost_reachable"])

    def test_leaf_edge_loses_only_its_target(self):
        rows = I.edge_removal_impact(["a", "b"], [("a", "b", "depends")], {("a", "b")})
        self.assertEqual(["b"], rows[0]["lost_reachable"])


if __name__ == "__main__":
    unittest.main()
