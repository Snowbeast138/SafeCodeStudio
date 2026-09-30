"""Extract evidence from Python CSTs, never executing source code."""
from dataclasses import dataclass
from hashlib import sha256

from tree_sitter import Language, Node, Parser, Tree
import tree_sitter_python


def evidence(node: Node, source: bytes) -> dict:
    return {
        "node_type": node.type,
        "start_byte": node.start_byte,
        "end_byte": node.end_byte,
        "start": {"line": node.start_point.row + 1, "byte_column": node.start_point.column},
        "end": {"line": node.end_point.row + 1, "byte_column": node.end_point.column},
        "text": source[node.start_byte:node.end_byte].decode("utf-8"),
    }


@dataclass
class Parsed:
    source: bytes
    tree: Tree
    digest: str
    symbols: list[dict]
    imports: list[dict]
    issues: list[dict]

    def cst(self) -> dict:
        # Iterative traversal avoids Python recursion limits on nested source.
        root = {**evidence(self.tree.root_node, self.source), "children": []}
        stack = [(self.tree.root_node, root)]
        while stack:
            node, out = stack.pop()
            for child in node.children:
                item = {**evidence(child, self.source), "named": child.is_named,
                        "missing": child.is_missing, "error": child.is_error, "children": []}
                out["children"].append(item)
                stack.append((child, item))
        return root


class PythonParser:
    def __init__(self):
        self.parser = Parser(Language(tree_sitter_python.language()))

    def parse(self, source: bytes) -> Parsed:
        source.decode("utf-8")  # Explicit contract: reject other encodings.
        tree = self.parser.parse(source)
        result = Parsed(source, tree, sha256(source).hexdigest(), [], [], [])
        stack = [(tree.root_node, None, "")]
        while stack:
            node, owner, prefix = stack.pop()
            if node.is_error or node.is_missing:
                result.issues.append({"kind": "syntax_error", **evidence(node, source)})
            if node.type in {"function_definition", "class_definition"}:
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = source[name_node.start_byte:name_node.end_byte].decode("utf-8")
                    qualified = f"{prefix}.{name}" if prefix else name
                    local_id = f"{qualified}@{node.start_byte}"
                    result.symbols.append({"local_id": local_id, "parent": owner,
                                           "name": name, "qualified_name": qualified,
                                           "kind": "class" if node.type == "class_definition" else "function",
                                           "evidence": evidence(node, source)})
                    owner, prefix = local_id, qualified
            if node.type in {"import_statement", "import_from_statement"}:
                def text(n):
                    return source[n.start_byte:n.end_byte].decode("utf-8")
                module_node = node.child_by_field_name("module_name")
                module = text(module_node) if module_node else ""
                names = []
                for child in node.named_children:
                    if module_node is not None and child.id == module_node.id:
                        continue
                    if child.type == "aliased_import":
                        target = child.child_by_field_name("name")
                        alias = child.child_by_field_name("alias")
                        names.append({"name": text(target), "alias": text(alias) if alias else None})
                    elif child.type in {"dotted_name", "identifier", "wildcard_import"}:
                        names.append({"name": text(child), "alias": None})
                result.imports.append({"kind": node.type, "module": module, "names": names,
                                       "scope": owner, "evidence": evidence(node, source)})
            if node.type == "call":
                fn = node.child_by_field_name("function")
                if fn and source[fn.start_byte:fn.end_byte] in {b"__import__", b"importlib.import_module"}:
                    result.issues.append({"kind": "dynamic_import", **evidence(node, source)})
            stack.extend((child, owner, prefix) for child in reversed(node.children))
        return result
