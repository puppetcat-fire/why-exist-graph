"""从代码图推导候选设计（component + depends）。

derive 产出的是**候选**，不是已确认的设计：``origin=derived``，可被咬合质疑，
确认后才提升为 ``declared``。这样既补上"从代码到设计图"的一步，又不违背
"不臆造"——推导规则可解释、来源可追溯、结果可复核。

第一版只做 ``package`` 策略：按文件路径的目录把代码节点聚成 component 候选。
组件间的依赖有两个来源：

- 跨组调用边（``calls`` / ``reads`` / ``writes``）；
- 跨组 import（由调用方解析源码后以 ``(源文件, 目标文件)`` 传入）——
  这是模块间依赖的主要形态，静态调用图里大部分调用是 unmapped，靠它不够。
"""

from __future__ import annotations

__all__ = ["component_id", "derive_components", "group_key"]

#: 参与分组的代码节点 kind；requirement / pattern 等设计节点不参与。
CODE_NODE_KINDS: tuple[str, ...] = ("classifier", "operation", "property")

#: 在组件之间构成依赖的边：调用、读、写。
DEPENDENCY_EDGE_KINDS: tuple[str, ...] = ("calls", "reads", "writes")


def group_key(path: str, depth: int = 1) -> str:
    """按目录深度取分组键。

    - ``httpie/cli/definition.py``，depth=1 -> ``httpie``
    - ``httpie/cli/definition.py``，depth=2 -> ``httpie.cli``
    - ``definition.py``，depth=1 -> ``.``（仓库根）

    ``depth`` 是取多少层目录；文件本身不参与分组键，目录不足时取全部。
    """
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    if not parts:
        return "."
    directories = parts[:-1]
    if not directories:
        return "."
    return ".".join(directories[:depth]) if depth > 0 else ".".join(directories)


def component_id(repo: str, key: str) -> str:
    """component 候选的节点 id。"""
    return f"component:{repo}:{key}"


def _is_excluded(path: str, prefixes: tuple[str, ...]) -> bool:
    """路径是否落在被排除的目录前缀下。"""
    normalized = path.replace("\\", "/")
    for prefix in prefixes:
        cleaned = prefix.replace("\\", "/").rstrip("/")
        if not cleaned:
            continue
        if normalized == cleaned or normalized.startswith(cleaned + "/"):
            return True
    return False


def derive_components(
    nodes: list[dict],
    edges: list[tuple[str, str, str]],
    *,
    repo: str,
    depth: int = 1,
    file_dependencies: list[tuple[str, str]] | None = None,
    exclude_dirs: tuple[str, ...] = (),
) -> dict:
    """按目录把代码节点聚成 component 候选，并推导组间 depends。

    ``nodes`` 每项至少含 ``id``、``kind``、``path``。``file_dependencies`` 是
    ``(源文件相对路径, 目标文件相对路径)``，通常来自 import 解析。``exclude_dirs``
    是目录前缀黑名单（如 ``tests``、``docs``），这些目录下的节点不参与分组——
    它们不是产品设计单元，混进来只会稀释并行规划。

    返回：

    - ``components``：``[{id, name, path, members}]``
    - ``depends``：``[{src, dst, evidence}]``，evidence 是节点对或文件对
    - ``excluded_nodes``：被目录黑名单排除的节点数
    """
    excluded: set[str] = set()
    membership: dict[str, list[str]] = {}
    node_to_component: dict[str, str] = {}
    component_paths: dict[str, str] = {}
    for node in nodes:
        if node.get("kind") not in CODE_NODE_KINDS:
            continue
        path = node.get("path") or ""
        if exclude_dirs and _is_excluded(path, exclude_dirs):
            excluded.add(node["id"])
            continue
        key = group_key(path, depth)
        cid = component_id(repo, key)
        membership.setdefault(cid, []).append(node["id"])
        node_to_component[node["id"]] = cid
        component_paths.setdefault(cid, path)

    depends: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for src, dst, kind in edges:
        if kind not in DEPENDENCY_EDGE_KINDS:
            continue
        left = node_to_component.get(src)
        right = node_to_component.get(dst)
        if left and right and left != right:
            depends.setdefault((left, right), []).append((src, dst))

    for source_file, target_file in file_dependencies or []:
        if exclude_dirs and (
            _is_excluded(source_file, exclude_dirs) or _is_excluded(target_file, exclude_dirs)
        ):
            continue
        left = component_id(repo, group_key(source_file, depth))
        right = component_id(repo, group_key(target_file, depth))
        # 只保留两端都真的分到组的依赖：import 解析可能指向没有代码节点入图的目录
        # （例如仓库根下只有脚本、没有 import 到的文件），那种端点没有 component 可写。
        if left != right and left in membership and right in membership:
            depends.setdefault((left, right), []).append((source_file, target_file))

    return {
        "repo": repo,
        "strategy": "package",
        "depth": depth,
        "exclude_dirs": list(exclude_dirs),
        "excluded_nodes": len(excluded),
        "components": [
            {
                "id": cid,
                "name": cid.split(":", 2)[-1],
                "path": component_paths[cid],
                "members": sorted(members),
            }
            for cid, members in sorted(membership.items())
        ],
        "depends": [
            {"src": left, "dst": right, "evidence": sorted(set(evidence))}
            for (left, right), evidence in sorted(depends.items())
        ],
    }
