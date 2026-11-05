"""briefing 的纯函数测试：不连数据库。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.briefing as B  # noqa: E402


FEATURE = {
    "id": "feat-x",
    "statement": "创建订单。",
    "acceptance": ["返回成功"],
    "constraints": ["不改产品代码"],
}

NODES = {
    "component:demo:a": {"kind": "component", "name": "A"},
    "component:demo:b": {"kind": "component", "name": "B"},
    "component:demo:c": {"kind": "component", "name": "C"},
    "component:other:z": {"kind": "component", "name": "Z"},
}

EDGES = [
    ("component:demo:a", "component:demo:c", "depends"),
    ("component:demo:b", "component:demo:c", "depends"),
    ("component:demo:c", "component:other:z", "depends"),
    ("component:demo:a", "component:demo:b", "uses"),  # 非依赖边，不构成输入
]


class ResolveBoundaryTest(unittest.TestCase):
    def test_exact_ids(self):
        self.assertEqual(
            ["component:demo:a"], B.resolve_boundary(["component:demo:a"], sorted(NODES))
        )

    def test_prefix_wildcard(self):
        self.assertEqual(
            ["component:demo:a", "component:demo:b", "component:demo:c"],
            B.resolve_boundary(["component:demo:*"], sorted(NODES)),
        )

    def test_deduplicates_overlapping_patterns(self):
        self.assertEqual(
            ["component:demo:a", "component:demo:b"],
            B.resolve_boundary(
                ["component:demo:a", "component:demo:*", "component:demo:a"],
                ["component:demo:a", "component:demo:b"],
            ),
        )

    def test_unknown_pattern_yields_nothing(self):
        self.assertEqual([], B.resolve_boundary(["missing:*"], sorted(NODES)))


class BuildBriefTest(unittest.TestCase):
    def _work(self, target_ids, kind="model-architecture"):
        return {
            "id": "work:feat-x:g1:model-architecture",
            "role": "model-architecture",
            "kind": kind,
            "target_ids": target_ids,
        }

    def test_boundary_is_expanded(self):
        brief = B.build_brief(
            feature=FEATURE,
            work=self._work(["component:demo:*"]),
            nodes=NODES,
            edges=EDGES,
        )
        self.assertEqual(
            ["component:demo:a", "component:demo:b", "component:demo:c"],
            brief["write_boundary"],
        )

    def test_boundary_node_depending_on_outside_node_becomes_input(self):
        # 边界 {c}：c 依赖界外的 z -> z 是输入
        brief = B.build_brief(
            feature=FEATURE,
            work=self._work(["component:demo:c"]),
            nodes=NODES,
            edges=EDGES,
        )
        self.assertEqual(
            [{"id": "component:other:z", "kind": "component", "name": "Z"}],
            brief["inputs"],
        )

    def test_upstream_inside_boundary_is_not_an_input(self):
        # 边界 {a, b}：a、b 依赖 c，c 不在边界内 -> c 是输入；c 的上游不再传递
        brief = B.build_brief(
            feature=FEATURE,
            work=self._work(["component:demo:a", "component:demo:b"]),
            nodes=NODES,
            edges=EDGES,
        )
        self.assertEqual(
            [{"id": "component:demo:c", "kind": "component", "name": "C"}],
            brief["inputs"],
        )

    def test_non_dependency_edges_are_not_inputs(self):
        # a 通过 depends 依赖 c（算输入）；a -> b 是 uses（不算）
        brief = B.build_brief(
            feature=FEATURE,
            work=self._work(["component:demo:a"]),
            nodes=NODES,
            edges=EDGES,
        )
        ids = [item["id"] for item in brief["inputs"]]
        self.assertIn("component:demo:c", ids)
        self.assertNotIn("component:demo:b", ids)

    def test_brief_is_blind_by_construction(self):
        brief = B.build_brief(
            feature=FEATURE,
            work=self._work(["component:demo:*"]),
            nodes=NODES,
            edges=EDGES,
        )
        self.assertTrue(brief["blind"])
        text = json.dumps(brief, ensure_ascii=False)
        # 自己的工单 id 是必要信息；不能出现的是其它目标的 id
        self.assertNotIn("work:feat-y", text)
        self.assertNotIn("feat-y", text)
        self.assertEqual(
            {"brief_version", "blind", "work_item", "feature", "role", "kind", "goal",
             "acceptance", "constraints", "write_boundary", "write_patterns", "inputs",
             "produces", "forbidden", "definition_of_done"},
            set(brief),
        )

    def test_produces_matches_work_kind(self):
        brief = B.build_brief(
            feature=FEATURE,
            work=self._work(["component:demo:*"]),
            nodes=NODES,
            edges=EDGES,
        )
        self.assertIn("component", brief["produces"])

    def test_is_deterministic(self):
        kwargs = dict(
            feature=FEATURE,
            work=self._work(["component:demo:*"]),
            nodes=NODES,
            edges=EDGES,
        )
        first = json.dumps(B.build_brief(**kwargs), ensure_ascii=False, sort_keys=True)
        second = json.dumps(B.build_brief(**kwargs), ensure_ascii=False, sort_keys=True)
        self.assertEqual(first, second)

    def test_unknown_kind_has_no_produces(self):
        brief = B.build_brief(
            feature=FEATURE,
            work=self._work(["component:demo:a"], kind="nonsense"),
            nodes=NODES,
            edges=EDGES,
        )
        self.assertEqual([], brief["produces"])


if __name__ == "__main__":
    unittest.main()
