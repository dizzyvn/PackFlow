import ast
import inspect
import textwrap

from packflow import BatchNode, Flow, StartNode, TerminateNode


def get_exec_function_calls(node):
    """Extract function names called inside the exec method."""
    if not hasattr(node, "exec"):
        return []

    try:
        exec_source = inspect.getsource(node.exec)
        # Dedent the source code to remove leading whitespace
        exec_source = textwrap.dedent(exec_source)

        tree = ast.parse(exec_source)
        function_calls = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    function_calls.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    function_calls.append(node.func.attr)

        return function_calls
    except Exception:
        return []


def build_mermaid(start):
    ids, visited, lines = {}, set(), ["graph TD"]
    ctr = 1

    def get_id(n):
        nonlocal ctr
        return (
            ids[n] if n in ids else (ids.setdefault(n, f"N{ctr}"), (ctr := ctr + 1))[0]
        )

    def link(a, b, condition=None):
        if condition:
            lines.append(f"    {a} -->|{condition}| {b}")
        else:
            lines.append(f"    {a} --> {b}")

    def get_node_label(node):
        return type(node).__name__

    def walk(node, parent=None, condition=None):
        if node in visited:
            return parent and link(parent, get_id(node), condition)
        visited.add(node)
        if isinstance(node, Flow):
            node.start_node and parent and link(
                parent, get_id(node.start_node), condition
            )
            lines.append(
                f"\n    subgraph sub_flow_{get_id(node)}[{type(node).__name__}]"
            )
            node.start_node and walk(node.start_node)
            for cond, successors in node.successors.items():
                for succ in successors:
                    node.start_node and walk(succ, get_id(node.start_node), cond) or (
                        parent and link(parent, get_id(succ), cond)
                    ) or walk(succ, None, cond)
            lines.append("    end\n")
        else:
            node_id = get_id(node)
            label = get_node_label(node)

            # Choose node shape based on node type
            if isinstance(node, BatchNode):
                lines.append(f'    {node_id}@{{shape: procs, label: "{label}"}}')
            elif isinstance(node, StartNode):
                lines.append(f'    {node_id}@{{shape: circle, label: "{label}"}}')
            elif isinstance(node, TerminateNode):
                lines.append(f'    {node_id}@{{shape: doublecircle, label: "{label}"}}')
            else:
                # For regular nodes, use standard rectangle
                lines.append(f"    {node_id}[{label}]")

            parent and link(parent, node_id, condition)
            if hasattr(node, "successors"):
                for cond, successors in node.successors.items():
                    for succ in successors:
                        walk(succ, node_id, cond)

    walk(start)
    print("\n".join(lines))
    return "\n".join(lines)
