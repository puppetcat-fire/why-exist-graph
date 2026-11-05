"""conflicts 的纯函数测试：不连数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.conflicts as C  # noqa: E402


class PatternsOverlapTest(unittest.TestCase):
    def test_identical_exact(self):
        self.assertTrue(C.patterns_overlap("component:demo:a", "component:demo:a"))

    def test_exact_inside_wildcard(self):
        self.assertTrue(C.patterns_overlap("component:demo:*", "component:demo:a"))
        self.assertTrue(C.patterns_overlap("component:demo:a", "component:demo:*"))

    def test_nested_wildcards(self):
        self.assertTrue(C.patterns_overlap("component:*", "component:demo:*"))

    def test_disjoint_wildcards(self):
        self.assertFalse(C.patterns_overlap("component:a*", "component:b*"))

    def test_exact_outside_wildcard(self):
        self.assertFalse(C.patterns_overlap("component:demo:*", "component:other:a"))

    def test_star_matches_everything(self):
        self.assertTrue(C.patterns_overlap("*", "component:demo:a"))


class DetectConflictsTest(unittest.TestCase):
    NODES = ["component:demo:a", "component:demo:b", "component:other:x"]

    def test_no_conflict(self):
        result = C.detect_conflicts(
            {"f1": ["component:demo:a"], "f2": ["component:demo:b"]}, self.NODES
        )
        self.assertTrue(result["coexist_ok"])
        self.assertEqual([], result["conflicts"])

    def test_overlapping_patterns_reported_with_existing_nodes(self):
        result = C.detect_conflicts(
            {"f1": ["component:demo:*"], "f2": ["component:demo:a"]}, self.NODES
        )
        self.assertFalse(result["coexist_ok"])
        conflict = result["conflicts"][0]
        self.assertEqual("f1", conflict["a"])
        self.assertEqual("f2", conflict["b"])
        self.assertEqual([["component:demo:*", "component:demo:a"]], conflict["overlapping_patterns"])
        self.assertEqual(["component:demo:a"], conflict["overlapping_nodes"])

    def test_pattern_overlap_without_existing_nodes_still_conflicts(self):
        result = C.detect_conflicts(
            {"f1": ["component:future:*"], "f2": ["component:future:x"]}, []
        )
        self.assertFalse(result["coexist_ok"])
        self.assertEqual([], result["conflicts"][0]["overlapping_nodes"])

    def test_multiple_pairs(self):
        result = C.detect_conflicts(
            {
                "f1": ["component:demo:*"],
                "f2": ["component:demo:a"],
                "f3": ["component:demo:b"],
            },
            self.NODES,
        )
        self.assertEqual(2, len(result["conflicts"]))

    def test_empty_features(self):
        result = C.detect_conflicts({}, self.NODES)
        self.assertTrue(result["coexist_ok"])
        self.assertEqual([], result["features"])

    def test_single_feature_never_conflicts(self):
        result = C.detect_conflicts({"f1": ["component:demo:*"]}, self.NODES)
        self.assertTrue(result["coexist_ok"])


if __name__ == "__main__":
    unittest.main()
