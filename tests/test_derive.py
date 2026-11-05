"""derive 的纯函数测试：不连数据库。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))

import whyexist.derive as D  # noqa: E402


class GroupKeyTest(unittest.TestCase):
    def test_first_directory(self):
        self.assertEqual("httpie", D.group_key("httpie/cli/definition.py", 1))

    def test_two_levels(self):
        self.assertEqual("httpie.cli", D.group_key("httpie/cli/definition.py", 2))

    def test_root_file(self):
        self.assertEqual(".", D.group_key("setup.py", 1))

    def test_windows_separators(self):
        self.assertEqual("httpie.cli", D.group_key("httpie\\cli\\definition.py", 2))


class DeriveComponentsTest(unittest.TestCase):
    def nodes(self):
        return [
            {"id": "operation:a.py:run", "kind": "operation", "path": "a.py"},
            {"id": "operation:b.py:run", "kind": "operation", "path": "b.py"},
            {"id": "operation:cli/x.py:go", "kind": "operation", "path": "cli/x.py"},
            {"id": "requirement:feat:main", "kind": "requirement", "path": None},
        ]

    def test_groups_by_directory(self):
        result = D.derive_components(self.nodes(), [], repo="demo", depth=1)
        ids = [component["id"] for component in result["components"]]
        self.assertEqual(["component:demo:.", "component:demo:cli"], ids)

    def test_requirement_nodes_do_not_participate(self):
        result = D.derive_components(self.nodes(), [], repo="demo")
        members = {member for component in result["components"] for member in component["members"]}
        self.assertNotIn("requirement:feat:main", members)

    def test_cross_group_calls_become_depends(self):
        edges = [("operation:cli/x.py:go", "operation:a.py:run", "calls")]
        result = D.derive_components(self.nodes(), edges, repo="demo", depth=1)
        self.assertEqual(1, len(result["depends"]))
        self.assertEqual("component:demo:cli", result["depends"][0]["src"])
        self.assertEqual("component:demo:.", result["depends"][0]["dst"])
        self.assertEqual(
            [["operation:cli/x.py:go", "operation:a.py:run"]],
            [list(pair) for pair in result["depends"][0]["evidence"]],
        )

    def test_same_group_calls_do_not_become_depends(self):
        nodes = [
            {"id": "operation:a.py:one", "kind": "operation", "path": "a.py"},
            {"id": "operation:a.py:two", "kind": "operation", "path": "a.py"},
        ]
        result = D.derive_components(
            nodes, [("operation:a.py:one", "operation:a.py:two", "calls")], repo="demo"
        )
        self.assertEqual([], result["depends"])

    def test_file_dependencies_to_ungrouped_dirs_are_dropped(self):
        # import 解析可能指向没有代码节点入图的目录（tools/ 只有脚本、没被 import 到），
        # 那种端点没有 component 可写——depends 不能引用它，否则 apply 时 upsert-edge 报错
        nodes = [{"id": "operation:pkg/a.py:f", "kind": "operation", "path": "pkg/a.py"}]
        result = D.derive_components(
            nodes, [], repo="demo", depth=1,
            file_dependencies=[("pkg/a.py", "tools/script.py")],
        )
        self.assertEqual([], result["depends"])

    def test_file_dependencies_with_both_groups_kept(self):
        nodes = [
            {"id": "operation:pkg/a.py:f", "kind": "operation", "path": "pkg/a.py"},
            {"id": "operation:other/b.py:g", "kind": "operation", "path": "other/b.py"},
        ]
        result = D.derive_components(
            nodes, [], repo="demo", depth=1,
            file_dependencies=[("pkg/a.py", "other/b.py")],
        )
        self.assertEqual(1, len(result["depends"]))

    def test_evidence_keeps_multiple_calls(self):
        nodes = [
            {"id": "operation:a/x.py:one", "kind": "operation", "path": "a/x.py"},
            {"id": "operation:b/y.py:two", "kind": "operation", "path": "b/y.py"},
            {"id": "operation:b/y.py:three", "kind": "operation", "path": "b/y.py"},
        ]
        edges = [
            ("operation:a/x.py:one", "operation:b/y.py:two", "calls"),
            ("operation:a/x.py:one", "operation:b/y.py:three", "calls"),
        ]
        result = D.derive_components(nodes, edges, repo="demo")
        self.assertEqual(2, len(result["depends"][0]["evidence"]))

    def test_non_dependency_edges_are_ignored(self):
        edges = [("operation:a.py:run", "operation:b.py:run", "satisfies")]
        result = D.derive_components(self.nodes(), edges, repo="demo")
        self.assertEqual([], result["depends"])

    def test_exclude_dirs_skips_matching_paths(self):
        nodes = [
            {"id": "operation:src/a.py:one", "kind": "operation", "path": "src/a.py"},
            {"id": "operation:tests/t.py:test", "kind": "operation", "path": "tests/t.py"},
        ]
        result = D.derive_components(
            nodes, [], repo="demo", depth=1, exclude_dirs=("tests",)
        )
        self.assertEqual(["component:demo:src"], [c["id"] for c in result["components"]])
        self.assertEqual(1, result["excluded_nodes"])

    def test_exclude_dirs_filters_file_dependencies(self):
        nodes = [
            {"id": "operation:src/a.py:one", "kind": "operation", "path": "src/a.py"},
            {"id": "operation:lib/b.py:two", "kind": "operation", "path": "lib/b.py"},
        ]
        result = D.derive_components(
            nodes,
            [],
            repo="demo",
            depth=1,
            file_dependencies=[("src/a.py", "lib/b.py"), ("tests/t.py", "src/a.py")],
            exclude_dirs=("tests",),
        )
        self.assertEqual(1, len(result["depends"]))
        self.assertEqual("component:demo:src", result["depends"][0]["src"])
        self.assertEqual("component:demo:lib", result["depends"][0]["dst"])

    def test_empty_repo(self):
        result = D.derive_components([], [], repo="demo")
        self.assertEqual([], result["components"])
        self.assertEqual([], result["depends"])


if __name__ == "__main__":
    unittest.main()
