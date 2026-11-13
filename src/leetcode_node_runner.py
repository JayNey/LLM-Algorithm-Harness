"""Node adapters embedded in the isolated Python function runner."""

from collections import deque
from typing import Any, Optional


class TreeNode:
    def __init__(self, val: int = 0, left: Any = None, right: Any = None) -> None:
        self.val = val
        self.left = left
        self.right = right


class GraphNode:
    def __init__(self, val: int = 0, neighbors: list[Any] | None = None) -> None:
        self.val = val
        self.neighbors = neighbors if neighbors is not None else []


class RandomListNode:
    def __init__(self, x: int, next: Any = None, random: Any = None) -> None:
        self.val = int(x)
        self.next = next
        self.random = random


def node_globals(adapter: str) -> dict[str, Any]:
    namespace: dict[str, Any] = {"List": list, "Optional": Optional}
    if adapter == "binary_tree":
        namespace["TreeNode"] = TreeNode
    else:
        namespace["Node"] = GraphNode if adapter == "graph_clone" else RandomListNode
    return namespace


def node_arguments(adapter: str, arguments: Any) -> tuple[Any, list[Any]]:
    if adapter == "binary_tree":
        return arguments, []

    if adapter == "graph_clone":
        adjacency = arguments["node"]
        graph_nodes = [GraphNode(index) for index in range(1, len(adjacency) + 1)]
        for node, neighbors in zip(graph_nodes, adjacency):
            node.neighbors = [graph_nodes[index - 1] for index in neighbors]
        originals = [(node, node.neighbors) for node in graph_nodes]
        return {"node": graph_nodes[0] if graph_nodes else None}, originals

    pairs = arguments["head"]
    nodes = [RandomListNode(value) for value, _ in pairs]
    for index, (_, random_index) in enumerate(pairs):
        nodes[index].next = nodes[index + 1] if index + 1 < len(nodes) else None
        nodes[index].random = nodes[random_index] if random_index is not None else None
    return {"head": nodes[0] if nodes else None}, nodes


class InvalidNodeResult(ValueError):
    """The candidate returned a value outside the node result protocol."""


def _value(node: Any) -> int:
    value = node.val
    if type(value) is not int:
        raise InvalidNodeResult
    return value


def _tree_output(root: Any) -> list[int | None]:
    output: list[int | None] = []
    seen: dict[int, Any] = {}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        if node is None:
            output.append(None)
            continue
        identity = id(node)
        if identity in seen:
            raise InvalidNodeResult
        seen[identity] = node
        output.append(_value(node))
        queue.extend((node.left, node.right))
    while output and output[-1] is None:
        output.pop()
    return output


def _graph_output(root: Any, originals: list[tuple[GraphNode, list[Any]]]) -> list[list[int]]:
    if root is None:
        return []
    if not originals or _value(root) != 1:
        raise InvalidNodeResult
    original_ids = {id(node) for node, _ in originals}
    original_neighbors = {id(neighbors) for _, neighbors in originals}
    seen: dict[int, Any] = {}
    adjacency: dict[int, list[int]] = {}
    queue = deque([root])
    while queue:
        node = queue.popleft()
        identity = id(node)
        if identity in seen:
            continue
        value = _value(node)
        if identity in original_ids or value in adjacency or not 1 <= value <= len(originals):
            raise InvalidNodeResult
        seen[identity] = node
        neighbors = node.neighbors
        if id(neighbors) in original_neighbors:
            raise InvalidNodeResult
        neighbors = list(neighbors)
        adjacency[value] = sorted(_value(neighbor) for neighbor in neighbors)
        queue.extend(neighbors)
    if len(adjacency) != len(originals):
        raise InvalidNodeResult
    return [adjacency[index] for index in range(1, len(originals) + 1)]


def _random_list_output(head: Any, originals: list[Any]) -> list[list[int | None]]:
    original_ids = {id(node) for node in originals}
    nodes: list[Any] = []
    indexes: dict[int, int] = {}
    node = head
    while node is not None:
        identity = id(node)
        if identity in original_ids or identity in indexes or len(nodes) >= len(originals):
            raise InvalidNodeResult
        indexes[identity] = len(nodes)
        nodes.append(node)
        node = node.next
    if len(nodes) != len(originals):
        raise InvalidNodeResult
    output = []
    for node in nodes:
        random_node = node.random
        output.append([_value(node), indexes[id(random_node)] if random_node is not None else None])
    return output


def node_result(adapter: str, result: Any, originals: list[Any]) -> Any:
    try:
        if adapter == "binary_tree":
            return _tree_output(result)
        if adapter == "graph_clone":
            return _graph_output(result, originals)
        return _random_list_output(result, originals)
    except (AttributeError, KeyError, TypeError, InvalidNodeResult):
        # Valid node results always serialize to an array, including an empty root.
        return None
