"""依赖图上的纯算法：SCC、拓扑分层、最大反链、可达闭包。

这个模块不 import 项目内任何其他模块，也不碰数据库。输入只有节点 id 与
有向边 (src, dst)，因此可以被单独测试，也可以被任何编译器 pass 复用。

术语：

- 依赖图：节点是设计单元，边 ``a -> b`` 表示 a 依赖 b（a 必须先于 b 完成，
  或 a 只能看到 b 的产出）。方向由调用方保证一致；本模块只做结构分析。
- 波次（layer）：同一层内互不依赖，可以同时执行。
- 最大反链（maximum antichain）：互不可比的最大节点集合，等于理论并行上限。
  由 Dilworth 定理，DAG 上「最大反链大小 = 最小链覆盖数 = n - 二分图最大匹配」。
- 强连通分量（SCC）：内部互相可达的节点集合；大小 > 1 或带自环即为环。

所有函数对非法输入（未知端点、自环、重复边）做统一规范化，不静默丢事实：
被丢弃的边记录在 :class:`DanglingEdges` 里返回。
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = [
    "CyclicGraph",
    "DanglingEdges",
    "GraphAnalysis",
    "adjacency",
    "analyze",
    "max_antichain",
    "normalize",
    "reachable",
    "reverse_adjacency",
    "strongly_connected_components",
    "topological_layers",
    "transitive_reachable",
]


class CyclicGraph(ValueError):
    """依赖图存在环。``components`` 里是自行成环的 SCC（含自环单点）。"""

    def __init__(self, components: list[list[str]]):
        self.components = components
        detail = "；".join("{" + ", ".join(c) + "}" for c in components)
        super().__init__(f"依赖图存在环：{detail}")


@dataclass(frozen=True)
class DanglingEdges:
    """规范化时被丢弃的边及其原因。"""

    unknown_endpoint: tuple[tuple[str, str], ...] = ()
    self_loop: tuple[tuple[str, str], ...] = ()
    duplicate: tuple[tuple[str, str], ...] = ()


def normalize(
    nodes: list[str], edges: list[tuple[str, str]]
) -> tuple[list[str], list[tuple[str, str]], DanglingEdges]:
    """去重节点、去掉未知端点 / 自环 / 重复边。

    返回 ``(nodes, edges, dropped)``。调用方可以把 ``dropped`` 当作"设计图有
    悬空边"的证据去报告，而不是当作不存在。
    """
    node_list: list[str] = list(dict.fromkeys(nodes))
    known = set(node_list)
    unknown: list[tuple[str, str]] = []
    loops: list[tuple[str, str]] = []
    dupes: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    clean: list[tuple[str, str]] = []
    for edge in edges:
        src, dst = edge
        if src not in known or dst not in known:
            unknown.append(edge)
            continue
        if src == dst:
            loops.append(edge)
            continue
        if edge in seen:
            dupes.append(edge)
            continue
        seen.add(edge)
        clean.append(edge)
    return node_list, clean, DanglingEdges(tuple(unknown), tuple(loops), tuple(dupes))


def adjacency(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, list[str]]:
    """正向邻接表；保持节点与边的输入顺序，输出因此是确定的。"""
    adj: dict[str, list[str]] = {node: [] for node in nodes}
    for src, dst in edges:
        adj[src].append(dst)
    return adj


def reverse_adjacency(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, list[str]]:
    """反向邻接表：沿依赖方向的上游。"""
    rev: dict[str, list[str]] = {node: [] for node in nodes}
    for src, dst in edges:
        rev[dst].append(src)
    return rev


def strongly_connected_components(
    nodes: list[str], edges: list[tuple[str, str]]
) -> list[list[str]]:
    """Kosaraju 双遍 DFS（迭代实现，不受递归深度限制）。

    返回分量列表，顺序为拓扑序：依赖者（边 ``u -> v`` 中的 u）先出现。分量内
    按输入顺序排序，因此同样的节点/边输入顺序得到确定的输出；不同输入顺序可能
    改变分量之间的先后，但分量集合不变。
    """
    nodes, edges, _ = normalize(nodes, edges)
    adj = adjacency(nodes, edges)
    rev = reverse_adjacency(nodes, edges)
    position = {node: idx for idx, node in enumerate(nodes)}

    visited: set[str] = set()
    finish_order: list[str] = []
    for start in nodes:
        if start in visited:
            continue
        visited.add(start)
        stack: list[tuple[str, list[str], int]] = [(start, adj[start], 0)]
        while stack:
            node, neighbours, cursor = stack[-1]
            if cursor < len(neighbours):
                stack[-1] = (node, neighbours, cursor + 1)
                nxt = neighbours[cursor]
                if nxt not in visited:
                    visited.add(nxt)
                    stack.append((nxt, adj[nxt], 0))
            else:
                finish_order.append(node)
                stack.pop()

    assigned: set[str] = set()
    components: list[list[str]] = []
    for start in reversed(finish_order):
        if start in assigned:
            continue
        assigned.add(start)
        component: list[str] = []
        stack = [start]
        while stack:
            node = stack.pop()
            component.append(node)
            for nxt in rev[node]:
                if nxt not in assigned:
                    assigned.add(nxt)
                    stack.append(nxt)
        component.sort(key=position.__getitem__)
        components.append(component)
    return components


def _cyclic_components(
    nodes: list[str], edges: list[tuple[str, str]], dropped: DanglingEdges
) -> list[list[str]]:
    """非平凡 SCC：大小 > 1，或带自环的单点。"""
    self_looping = {src for src, _ in dropped.self_loop}
    cyclic: list[list[str]] = []
    for component in strongly_connected_components(nodes, edges):
        if len(component) > 1 or component[0] in self_looping:
            cyclic.append(component)
    return cyclic


def topological_layers(nodes: list[str], edges: list[tuple[str, str]]) -> list[list[str]]:
    """Kahn 分层：同一层内节点互不依赖，``layers[0]`` 是最上游。

    有环（含自环）时抛 :class:`CyclicGraph`。层内保持输入顺序。
    """
    nodes, edges, dropped = normalize(nodes, edges)
    if dropped.self_loop:
        raise CyclicGraph([[src] for src, _ in dropped.self_loop])

    adj = adjacency(nodes, edges)
    indegree = {node: 0 for node in nodes}
    for _, dst in edges:
        indegree[dst] += 1

    current = [node for node in nodes if indegree[node] == 0]
    layers: list[list[str]] = []
    placed = 0
    while current:
        layers.append(current)
        placed += len(current)
        nxt: list[str] = []
        for node in current:
            for neighbour in adj[node]:
                indegree[neighbour] -= 1
                if indegree[neighbour] == 0:
                    nxt.append(neighbour)
        current = nxt
    if placed != len(nodes):
        raise CyclicGraph(_cyclic_components(nodes, edges, dropped))
    return layers


def transitive_reachable(
    nodes: list[str], edges: list[tuple[str, str]]
) -> dict[str, set[str]]:
    """每个节点严格可达的节点集合（不含自身）。

    DAG 上用位集传递闭包（O(n·(n+e))）；有环时退化为逐点 DFS，结果相同。
    """
    nodes, edges, _ = normalize(nodes, edges)
    adj = adjacency(nodes, edges)
    index = {node: idx for idx, node in enumerate(nodes)}
    try:
        layers = topological_layers(nodes, edges)
    except CyclicGraph:
        result: dict[str, set[str]] = {}
        for start in nodes:
            seen: set[str] = set()
            stack = [start]
            while stack:
                node = stack.pop()
                for nxt in adj[node]:
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            result[start] = seen - {start}
        return result

    masks: list[int] = [0] * len(nodes)
    for layer in reversed(layers):
        for node in layer:
            mask = 0
            for nxt in adj[node]:
                mask |= (1 << index[nxt]) | masks[index[nxt]]
            masks[index[node]] = mask
    return {
        node: {other for other in nodes if masks[index[node]] & (1 << index[other])}
        for node in nodes
    }


def reachable(
    nodes: list[str],
    edges: list[tuple[str, str]],
    start: str,
    *,
    reverse: bool = False,
) -> set[str]:
    """从 ``start`` 出发的可达集（不含 start 自身）。

    ``reverse=True`` 时沿依赖反向走，得到上游集合。
    """
    nodes, edges, _ = normalize(nodes, edges)
    if start not in nodes:
        return set()
    graph = reverse_adjacency(nodes, edges) if reverse else adjacency(nodes, edges)
    seen: set[str] = set()
    stack = [start]
    while stack:
        node = stack.pop()
        for nxt in graph[node]:
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _max_matching(left: list[str], allowed: dict[str, list[str]]) -> int:
    """二分图最大匹配（Kuhn 增广路，迭代实现）。

    ``allowed[u]`` 是左节点 u 可连的右节点。返回匹配边数。

    迭代版的关键是显式维护交替路径：``parent[r]`` 记录「哪个左节点发现了右
    节点 r」，翻转时从新发现的自由右节点沿 parent 链回到起点，逐段改写匹配。
    """
    match_left: dict[str, str] = {}
    match_right: dict[str, str] = {}

    def augment(start: str) -> bool:
        visited: set[str] = set()
        parent: dict[str, str] = {}
        on_path: set[str] = {start}
        stack: list[tuple[str, int]] = [(start, 0)]
        found: str | None = None
        while stack:
            node, cursor = stack[-1]
            neighbours = allowed[node]
            if cursor >= len(neighbours):
                stack.pop()
                continue
            stack[-1] = (node, cursor + 1)
            candidate = neighbours[cursor]
            if candidate in visited:
                continue
            visited.add(candidate)
            parent[candidate] = node
            if candidate not in match_right:
                found = candidate
                break
            occupant = match_right[candidate]
            if occupant not in on_path:
                on_path.add(occupant)
                stack.append((occupant, 0))
        if found is None:
            return False
        right = found
        while True:
            left_node = parent[right]
            previous_right = match_left.get(left_node)
            match_left[left_node] = right
            match_right[right] = left_node
            if previous_right is None:
                break
            # 这个左节点此前匹配的右节点，继续交给它的前驱左节点
            right = previous_right
        return True

    for node in left:
        if node not in match_left:
            augment(node)
    return len(match_right)


def max_antichain(nodes: list[str], edges: list[tuple[str, str]]) -> int:
    """最大反链大小（Dilworth）。对 DAG 返回理论并行上限。

    构造：把偏序（传递可达关系）做成二分图，左右各一份节点，``u`` 可达 ``v``
    时连 ``L(u)-R(v)``。于是「最小链覆盖 = n - 最大匹配 = 最大反链」。

    依赖图存在环时，环内节点必须一起执行，反链意义不成立；先把每个非平凡
    SCC 收缩成一个宏节点再算，得到的是收缩后 DAG 的并行上限。
    """
    nodes, edges, _ = normalize(nodes, edges)
    if not nodes:
        return 0

    components = strongly_connected_components(nodes, edges)
    component_of: dict[str, int] = {}
    for idx, component in enumerate(components):
        for node in component:
            component_of[node] = idx

    super_nodes = [str(idx) for idx in range(len(components))]
    super_edges: set[tuple[str, str]] = set()
    for src, dst in edges:
        a, b = component_of[src], component_of[dst]
        if a != b:
            super_edges.add((str(a), str(b)))

    reach = transitive_reachable(super_nodes, sorted(super_edges))
    allowed = {node: sorted(reach[node]) for node in super_nodes}
    matched = _max_matching(super_nodes, allowed)
    return len(super_nodes) - matched


@dataclass(frozen=True)
class GraphAnalysis:
    """一次结构分析的完整结果。"""

    node_count: int
    edge_count: int
    components: list[list[str]] = field(default_factory=list)
    cyclic_components: list[list[str]] = field(default_factory=list)
    layers: list[list[str]] | None = None
    max_antichain: int = 0
    dangling: DanglingEdges = field(default_factory=DanglingEdges)

    @property
    def acyclic(self) -> bool:
        return not self.cyclic_components

    @property
    def parallelism(self) -> int:
        """理论并行上限。

        只有大小 > 1 的环会强制串行；单点自环（递归函数）不阻断并行——
        它只说明拓扑分层不可用，不说明整个图只能串行。
        """
        blocking = [component for component in self.cyclic_components if len(component) > 1]
        if not blocking:
            return self.max_antichain
        return max(len(component) for component in blocking)


def analyze(nodes: list[str], edges: list[tuple[str, str]]) -> GraphAnalysis:
    """一次性算出 SCC、波次、最大反链与悬空边。"""
    normalized_nodes, normalized_edges, dropped = normalize(nodes, edges)
    components = strongly_connected_components(normalized_nodes, normalized_edges)
    cyclic = _cyclic_components(normalized_nodes, normalized_edges, dropped)
    # 自环在 normalize 时已被丢掉，topological_layers 看不到它；但环检测知道它存在。
    # 两处必须对齐，否则会出现 "ac 有环但 layers 有值" 的自相矛盾。
    layers: list[list[str]] | None
    if dropped.self_loop:
        layers = None
    else:
        try:
            layers = topological_layers(normalized_nodes, normalized_edges)
        except CyclicGraph:
            layers = None
    return GraphAnalysis(
        node_count=len(normalized_nodes),
        edge_count=len(normalized_edges),
        components=components,
        cyclic_components=cyclic,
        layers=layers,
        max_antichain=max_antichain(normalized_nodes, normalized_edges),
        dangling=dropped,
    )
