"""reducer 的纯函数测试：不连数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.reducer as R  # noqa: E402


def patch(label, nodes=(), edges=()):
    return {
        "work_item": label,
        "nodes": [
            {"id": node_id, "kind": kind, "name": name, "attrs": attrs or {}}
            for node_id, kind, name, attrs in nodes
        ],
        "edges": [
            {"src": src, "dst": dst, "kind": kind} for src, dst, kind in edges
        ],
    }


class NormalizePatchTest(unittest.TestCase):
    def test_dedupes_nodes_and_edges(self):
        result = R.normalize_patch(
            {
                "nodes": [
                    {"id": "b", "kind": "component", "name": "B"},
                    {"id": "a", "kind": "component", "name": "A"},
                    {"id": "a", "kind": "component", "name": "A"},
                ],
                "edges": [
                    {"src": "a", "dst": "b", "kind": "depends"},
                    {"src": "a", "dst": "b", "kind": "depends"},
                ],
            },
            work_item="w1",
        )
        self.assertEqual("w1", result["work_item"])
        self.assertEqual(["a", "b"], [node["id"] for node in result["nodes"]])
        self.assertEqual(1, len(result["edges"]))

    def test_drops_incomplete_entries(self):
        result = R.normalize_patch(
            {
                "nodes": [{"kind": "component"}, {"id": "ok", "kind": "component"}],
                "edges": [{"src": "a"}, {"src": "a", "dst": "b", "kind": "depends"}],
            }
        )
        self.assertEqual(["ok"], [node["id"] for node in result["nodes"]])
        self.assertEqual(1, len(result["edges"]))


class MergePatchesTest(unittest.TestCase):
    def test_disjoint_patches_merge(self):
        merged = R.merge_patches(
            [
                patch("w1", nodes=[("a", "component", "A", None)]),
                patch("w2", nodes=[("b", "component", "B", None)]),
            ],
            existing_ids=set(),
        )
        self.assertTrue(merged["ok"])
        self.assertEqual(["a", "b"], [node["id"] for node in merged["nodes"]])

    def test_identical_node_content_is_not_a_conflict(self):
        merged = R.merge_patches(
            [
                patch("w1", nodes=[("a", "component", "A", {"duty": "x"})]),
                patch("w2", nodes=[("a", "component", "A", {"duty": "x"})]),
            ],
            existing_ids=set(),
        )
        self.assertTrue(merged["ok"])
        self.assertEqual(1, len(merged["nodes"]))

    def test_different_content_is_a_conflict(self):
        merged = R.merge_patches(
            [
                patch("w1", nodes=[("a", "component", "A", {"duty": "x"})]),
                patch("w2", nodes=[("a", "component", "A", {"duty": "y"})]),
            ],
            existing_ids=set(),
        )
        self.assertFalse(merged["ok"])
        self.assertEqual("a", merged["conflicts"][0]["node"])
        self.assertEqual("w1", merged["conflicts"][0]["a"])
        self.assertEqual("w2", merged["conflicts"][0]["b"])

    def test_edge_endpoint_may_come_from_another_patch(self):
        merged = R.merge_patches(
            [
                patch("w1", nodes=[("a", "component", "A", None)]),
                patch("w2", nodes=[("b", "component", "B", None)], edges=[("a", "b", "depends")]),
            ],
            existing_ids=set(),
        )
        self.assertTrue(merged["ok"])

    def test_edge_endpoint_may_be_existing_node(self):
        merged = R.merge_patches(
            [patch("w1", nodes=[("a", "component", "A", None)], edges=[("a", "old", "depends")])],
            existing_ids={"old"},
        )
        self.assertTrue(merged["ok"])

    def test_unknown_edge_endpoint_fails(self):
        merged = R.merge_patches(
            [patch("w1", edges=[("a", "ghost", "depends")])],
            existing_ids=set(),
        )
        self.assertFalse(merged["ok"])
        # 两个端点都不存在时都要报出来
        self.assertEqual(
            {"a", "ghost"},
            {item["endpoint"] for item in merged["unknown_endpoints"]},
        )

    def test_merge_is_commutative(self):
        left = patch("w1", nodes=[("a", "component", "A", None)], edges=[("a", "old", "depends")])
        right = patch("w2", nodes=[("b", "component", "B", None)])
        first = R.merge_patches([left, right], existing_ids={"old"})
        second = R.merge_patches([right, left], existing_ids={"old"})
        self.assertEqual(first, second)

    def test_conflict_order_is_commutative_in_detection(self):
        left = patch("w1", nodes=[("a", "component", "A", {"duty": "x"})])
        right = patch("w2", nodes=[("a", "component", "A", {"duty": "y"})])
        first = R.merge_patches([left, right], existing_ids=set())
        second = R.merge_patches([right, left], existing_ids=set())
        # a/b 顺序会随补丁顺序变，但冲突集合与 ok 不变
        self.assertEqual(first["ok"], second["ok"])
        self.assertFalse(first["ok"])
        self.assertEqual(
            {("w1", "w2"), ("w2", "w1")},
            {(item["a"], item["b"]) for item in first["conflicts"] + second["conflicts"]},
        )


if __name__ == "__main__":
    unittest.main()
