"""Repository discovery and conservative module dependency resolution."""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import os

import networkx as nx

from .parser import Parsed, PythonParser

EXCLUDED = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "dist", "build"}


@dataclass
class Analysis:
    root: Path
    graph: nx.MultiDiGraph
    issues: list[dict]
    parsed_files: int
    cached_files: int

    def file_graph(self) -> nx.DiGraph:
        graph = nx.DiGraph()
        graph.add_nodes_from(n for n, data in self.graph.nodes(data=True) if data["kind"] == "file")
        graph.add_edges_from((a, b) for a, b, data in self.graph.edges(data=True)
                             if data["relation"] == "imports")
        return graph

    def affected_by(self, path: str) -> list[str]:
        """Consumers of path, including path itself. A -> B means A imports B."""
        node = f"file:{Path(path).as_posix()}"
        graph = self.file_graph()
        if node not in graph:
            raise ValueError(f"File not in graph: {path}")
        return sorted(self.graph.nodes[n]["path"] for n in nx.ancestors(graph, node) | {node})

    def to_dict(self) -> dict:
        graph = self.file_graph()
        cycles = [sorted(self.graph.nodes[n]["path"] for n in group)
                  for group in nx.strongly_connected_components(graph)
                  if len(group) > 1 or any(graph.has_edge(n, n) for n in group)]
        return {"schema_version": 1, "root": str(self.root),
                "status": "partial" if self.issues else "complete_for_supported_scope",
                "scope": "Python UTF-8; static module imports and declarations; not runtime or security verification",
                "direction": "importer -> imported module; container -> declaration",
                "metrics": {"files": len(graph), "parsed": self.parsed_files, "cached": self.cached_files},
                "nodes": [{"id": n, **data} for n, data in sorted(self.graph.nodes(data=True))],
                "edges": [{"source": a, "target": b, "key": k, **data}
                          for a, b, k, data in sorted(self.graph.edges(keys=True, data=True))],
                "cyclic_components": sorted(cycles), "issues": self.issues}


class Engine:
    def __init__(self, root: str | Path, source_roots: tuple[str, ...] = (".",),
                 max_file_bytes: int = 1_000_000):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise ValueError(f"Not a directory: {self.root}")
        self.source_roots = []
        for item in source_roots:
            source = (self.root / item).resolve()
            if not source.is_relative_to(self.root) or not source.is_dir():
                raise ValueError(f"Source root must be a directory inside project: {item}")
            if source not in self.source_roots:
                self.source_roots.append(source)
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        self.max_file_bytes = max_file_bytes
        self.parser = PythonParser()
        self.cache: dict[str, Parsed] = {}

    def analyze(self) -> Analysis:
        graph = nx.MultiDiGraph()
        issues = []
        parsed_count = cached_count = 0
        modules: dict[str, set[str]] = {}
        identities: dict[str, set[str]] = {}
        files: dict[str, Parsed] = {}
        def walk_error(error):
            issues.append({"kind": "read_error", "path": str(error.filename), "message": str(error)})
        for directory, dirs, names in os.walk(self.root, followlinks=False, onerror=walk_error):
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not d.startswith(".")
                             and not (Path(directory) / d).is_symlink())
            for name in sorted(names):
                path = Path(directory) / name
                if path.suffix != ".py":
                    continue
                rel = path.relative_to(self.root).as_posix()
                if path.is_symlink():
                    issues.append({"kind": "symlink_skipped", "path": rel})
                    continue
                graph.add_node(f"file:{rel}", kind="file", path=rel)
                identities[rel] = set()
                for source_root in self.source_roots:
                    if path.is_relative_to(source_root):
                        parts = list(path.relative_to(source_root).with_suffix("").parts)
                        if parts[-1] == "__init__":
                            parts.pop()
                        module = ".".join(parts)
                        if module:
                            modules.setdefault(module, set()).add(rel)
                            identities[rel].add(module)
                try:
                    with path.open("rb") as handle:
                        raw = handle.read(self.max_file_bytes + 1)
                    if len(raw) > self.max_file_bytes:
                        issues.append({"kind": "file_too_large", "path": rel})
                        continue
                    digest = sha256(raw).hexdigest()
                    if rel in self.cache and self.cache[rel].digest == digest:
                        parsed = self.cache[rel]
                        cached_count += 1
                    else:
                        parsed = self.parser.parse(raw)
                        parsed_count += 1
                    files[rel] = parsed
                    graph.nodes[f"file:{rel}"].update(hash=parsed.digest, syntax_valid=not parsed.tree.root_node.has_error)
                    issues.extend({"path": rel, **issue} for issue in parsed.issues)
                except (OSError, UnicodeError) as error:
                    issues.append({"kind": "read_error", "path": rel, "message": str(error)})
        self.cache = files  # Evict removed, renamed, unreadable files.
        for rel, parsed in sorted(files.items()):
            file_id = f"file:{rel}"
            for symbol in parsed.symbols:
                symbol_id = f"symbol:{rel}:{symbol['local_id']}"
                graph.add_node(symbol_id, path=rel, **{k: v for k, v in symbol.items() if k != "parent"})
                parent = f"symbol:{rel}:{symbol['parent']}" if symbol["parent"] else file_id
                graph.add_edge(parent, symbol_id, relation="contains", evidence=symbol["evidence"])
            for imp in parsed.imports:
                if imp["evidence"]["node_type"] == "import_statement":
                    requests = [(x["name"], None, x["alias"]) for x in imp["names"]]
                else:
                    requests = [(imp["module"], x["name"], x["alias"]) for x in imp["names"]]
                for module, member, alias in requests:
                    base = module
                    if module.startswith("."):
                        if len(identities[rel]) != 1:
                            issues.append({"kind": "unresolved_import", "reason": "ambiguous_package_context",
                                           "path": rel, "evidence": imp["evidence"]})
                            continue
                        identity = next(iter(identities[rel]))
                        package = identity.split(".") if Path(rel).name == "__init__.py" else identity.split(".")[:-1]
                        level = len(module) - len(module.lstrip("."))
                        if level > len(package):
                            issues.append({"kind": "unresolved_import", "reason": "relative_beyond_package",
                                           "path": rel, "evidence": imp["evidence"]})
                            continue
                        base = ".".join(package[:len(package) - level + 1] + ([module[level:]] if module[level:] else []))
                    # A from-import may name a submodule or a symbol exported by base.
                    child = f"{base}.{member}" if base and member and member != "*" else ""
                    candidate = child if child in modules else base
                    targets = modules.get(candidate, set())
                    if len(targets) != 1:
                        issues.append({"kind": "unresolved_import", "reason": "ambiguous_module" if targets else "external_or_missing",
                                       "path": rel, "module": module, "member": member, "evidence": imp["evidence"]})
                        continue
                    target = next(iter(targets))
                    graph.add_edge(file_id, f"file:{target}", relation="imports", module=candidate,
                                   imported_name=member, alias=alias, scope=imp["scope"],
                                   resolution="module_only", evidence=imp["evidence"])
                    if member == "*":
                        issues.append({"kind": "wildcard_import", "path": rel, "evidence": imp["evidence"]})
        return Analysis(self.root, graph, issues, parsed_count, cached_count)

    def inspect_cst(self, relative_path: str) -> dict:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root) or path.suffix != ".py":
            raise ValueError("CST path must be a Python file inside the project")
        with path.open("rb") as handle:
            source = handle.read(self.max_file_bytes + 1)
        if len(source) > self.max_file_bytes:
            raise ValueError("File exceeds size limit")
        return self.parser.parse(source).cst()
