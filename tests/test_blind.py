"""blind 的纯函数测试：不连数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.blind as B  # noqa: E402

BRIEF = {
    "work_item": "work:feat-x:g1:model-architecture",
    "write_boundary": ["component:demo:a"],
    "write_patterns": ["component:demo:*"],
    "inputs": [{"id": "component:other:z", "kind": "component", "name": "Z"}],
    "produces": ["component"],
}

KNOWN_NODES = ["component", "use_case", "operation"]
KNOWN_EDGES = ["depends", "calls", "satisfies"]


def check(output):
    return B.check_output(
        brief=BRIEF,
        output=output,
        known_node_kinds=KNOWN_NODES,
        known_edge_kinds=KNOWN_EDGES,
    )


class CheckOutputTest(unittest.TestCase):
    def test_clean_output_passes(self):
        result = check(
            {
                "nodes": [{"id": "component:demo:new", "kind": "component"}],
                "edges": [
                    {
                        "src": "component:demo:new",
                        "dst": "component:other:z",
                        "kind": "depends",
                    }
                ],
            }
        )
        self.assertEqual("PASS", result["verdict"])
        self.assertEqual(1.0, result["locality"])
        self.assertTrue(result["boundary"]["ok"])
        self.assertTrue(result["dependencies"]["ok"])
        self.assertTrue(result["contract"]["ok"])

    def test_wildcard_boundary_allows_new_node(self):
        result = check({"nodes": [{"id": "component:demo:brand-new", "kind": "component"}]})
        self.assertTrue(result["boundary"]["ok"])

    def test_out_of_bounds_node_fails(self):
        result = check({"nodes": [{"id": "component:other:x", "kind": "component"}]})
        self.assertEqual("FAIL", result["verdict"])
        self.assertFalse(result["boundary"]["ok"])
        self.assertEqual(["component:other:x"], result["boundary"]["out_of_bounds"])

    def test_undeclared_dependency_fails(self):
        result = check(
            {
                "edges": [
                    {"src": "component:demo:new", "dst": "component:other:q", "kind": "depends"}
                ]
            }
        )
        self.assertEqual("FAIL", result["verdict"])
        self.assertFalse(result["dependencies"]["ok"])
        self.assertEqual("component:other:q", result["dependencies"]["undeclared"][0]["endpoint"])

    def test_declared_input_is_legal_endpoint(self):
        result = check(
            {
                "nodes": [{"id": "component:demo:new", "kind": "component"}],
                "edges": [
                    {"src": "component:demo:new", "dst": "component:other:z", "kind": "depends"}
                ],
            }
        )
        self.assertTrue(result["dependencies"]["ok"])

    def test_unexpected_produce_kind_fails_new_node(self):
        result = check({"nodes": [{"id": "component:demo:case", "kind": "use_case"}]})
        self.assertEqual("FAIL", result["verdict"])
        self.assertFalse(result["contract"]["ok"])
        self.assertEqual({"id": "component:demo:case", "kind": "use_case"}, result["contract"]["unexpected_kinds"][0])

    def test_updating_existing_boundary_node_does_not_recheck_produces(self):
        # 边界内的已有节点（component:demo:a）不参与 produces 判定
        result = check({"nodes": [{"id": "component:demo:a", "kind": "component"}]})
        self.assertTrue(result["contract"]["ok"])

    def test_unknown_node_kind_fails(self):
        result = check({"nodes": [{"id": "component:demo:x", "kind": "nonsense"}]})
        self.assertFalse(result["contract"]["ok"])
        self.assertEqual("nonsense", result["contract"]["unknown_kinds"][0]["kind"])

    def test_unknown_edge_kind_fails(self):
        result = check(
            {"edges": [{"src": "component:demo:a", "dst": "component:demo:b", "kind": "bogus"}]}
        )
        self.assertFalse(result["contract"]["ok"])
        self.assertEqual(1, len(result["contract"]["unknown_edge_kinds"]))

    def test_malformed_entries_fail_contract(self):
        result = check({"nodes": [{"kind": "component"}], "edges": [{"src": "component:demo:a"}]})
        self.assertFalse(result["contract"]["ok"])
        self.assertEqual(2, len(result["contract"]["malformed"]))

    def test_locality_degrades_with_violations(self):
        clean = check({"nodes": [{"id": "component:demo:ok", "kind": "component"}]})
        dirty = check(
            {
                "nodes": [{"id": "component:other:x", "kind": "component"}],
                "edges": [{"src": "component:other:x", "dst": "component:other:q", "kind": "depends"}],
            }
        )
        self.assertEqual(1.0, clean["locality"])
        self.assertLess(dirty["locality"], clean["locality"])
        self.assertGreaterEqual(dirty["locality"], 0.0)

    def test_empty_output_passes(self):
        result = check({})
        self.assertEqual("PASS", result["verdict"])
        self.assertEqual(1.0, result["locality"])


if __name__ == "__main__":
    unittest.main()
