import copy
import time
import warnings


class BaseNode:
    def __init__(self):
        self.params, self.successors = {}, {}

    def set_params(self, params):
        self.params = params

    def next(self, node, action="default"):
        if action not in self.successors:
            self.successors[action] = []
        self.successors[action].append(node)
        return node

    def prep(self, shared):
        pass

    def exec(self, prep_res):
        pass

    def post(self, shared, prep_res, exec_res):
        pass

    def _exec(self, prep_res):
        return self.exec(prep_res)

    def _run(self, shared):
        try:
            p = self.prep(shared)
            e = self._exec(p)
            r = self.post(shared, p, e)
            return r

        except Exception as e:
            raise e

    def run(self, shared):
        if self.successors:
            warnings.warn("Node won't run successors. Use Flow.")
        return self._run(shared)

    def __rshift__(self, other):
        return self.next(other)

    def __sub__(self, action):
        if isinstance(action, str):
            return _ConditionalTransition(self, action)
        raise TypeError("Action must be a string")


class _ConditionalTransition:
    def __init__(self, src, action):
        self.src, self.action = src, action

    def __rshift__(self, tgt):
        return self.src.next(tgt, self.action)


class Node(BaseNode):
    def __init__(self, max_retries=1, wait=0):
        super().__init__()
        self.max_retries, self.wait = max_retries, wait

    def exec_fallback(self, prep_res, exc):
        raise exc

    def _exec(self, prep_res):
        for self.cur_retry in range(self.max_retries):
            try:
                return self.exec(prep_res)
            except Exception as e:
                if self.cur_retry == self.max_retries - 1:
                    return self.exec_fallback(prep_res, e)
                if self.wait > 0:
                    time.sleep(self.wait)

    def _run(self, shared):
        try:
            p = self.prep(shared)
            e = self._exec(p)
            r = self.post(shared, p, e)
            return r
        except Exception as e:
            raise e


class BatchNode(Node):
    def _exec(self, items):
        return [super(BatchNode, self)._exec(i) for i in (items or [])]


class Flow(BaseNode):
    def __init__(self, start=None):
        super().__init__()
        self.start_node = start

    def start(self, start):
        self.start_node = start
        return start

    def get_next_nodes(self, curr, action):
        # Get all next nodes for the action
        action = action or "default"  # Ensure we use "default" instead of None
        next_nodes = curr.successors.get(action, [])

        if not next_nodes and curr.successors:
            warnings.warn(f"Flow ends: '{action}' not found in {list(curr.successors)}")

        return next_nodes

    def _build_dependency_graph(self, action_map):
        dependencies = {}
        reverse_deps = {}

        def add_dependency(node, action=None):
            if node not in dependencies:
                dependencies[node] = set()
            if node not in reverse_deps:
                reverse_deps[node] = set()

            actions = [action] if action else node.successors.keys()

            for curr_action in actions:
                successors = node.successors.get(curr_action, [])
                if not isinstance(successors, list):
                    successors = [successors]

                for succ in successors:
                    if succ not in dependencies:
                        dependencies[succ] = set()
                    if succ not in reverse_deps:
                        reverse_deps[succ] = set()
                    dependencies[succ].add(node)
                    reverse_deps[node].add(succ)
                    add_dependency(succ)

        start_action = action_map.get(self.start_node)
        add_dependency(self.start_node, start_action)
        return dependencies, reverse_deps

    def _orch(self, shared, params=None):
        action_map = {}
        p = params or {**self.params}

        def execute_node(node):
            if node in action_map:
                return

            node_copy = copy.copy(node)
            node_copy.set_params(p)
            prep_res = node_copy.prep(shared)
            exec_res = node_copy._exec(prep_res)
            action = node_copy.post(shared, prep_res, exec_res)
            action = action or "default"
            action_map[node] = action
            return action

        execute_node(self.start_node)

        dependencies, reverse_deps = self._build_dependency_graph(action_map)

        completed_nodes = {self.start_node}
        ready_nodes = []

        for node in dependencies:
            if dependencies[node].issubset(completed_nodes):
                ready_nodes.append(node)

        while ready_nodes:
            for node in ready_nodes:
                if node not in completed_nodes:
                    execute_node(node)
                    completed_nodes.add(node)

            ready_nodes = []
            for node in completed_nodes:
                for dependent in reverse_deps.get(node, set()):
                    if all(dep in completed_nodes for dep in dependencies[dependent]):
                        ready_nodes.append(dependent)

            ready_nodes = list(set(ready_nodes) - completed_nodes)

        return action_map.get(self.start_node)

    def _run(self, shared):
        p = self.prep(shared)
        o = self._orch(shared)
        r = self.post(shared, p, o)
        return r

    def post(self, shared, prep_res, exec_res):
        return exec_res


class BatchFlow(Flow):
    def _run(self, shared):
        pr = self.prep(shared) or []
        for bp in pr:
            self._orch(shared, {**self.params, **bp})
        return self.post(shared, pr, None)


class StartNode(Node):
    pass


class TerminateNode(Node):
    pass
