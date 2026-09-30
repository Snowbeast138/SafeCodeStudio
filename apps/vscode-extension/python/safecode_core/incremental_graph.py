"""Persistent CST and dependency graph session for directory updates.

The first scan indexes the workspace. Later scans parse only changed source files
and update their outgoing edges. File-set changes conservatively re-resolve cached
references so imports affected by additions, deletions and renames stay correct.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
import os

import networkx as nx

from .cst import EXTENSIONS
from .dependencies import extract_dependencies
from .directory_graph import DirectoryGraph, DirectoryGraphEngine, EXCLUDED


@dataclass(frozen=True)
class CachedFile:
    digest: str | None
    report: dict | None
    candidates: list[dict]
    error: str | None = None


@dataclass
class IncrementalResult:
    snapshot: DirectoryGraph
    sequence: int
    changes: dict
    metrics: dict

    def to_dict(self, directory='.'):
        payload = self.snapshot.to_dict(directory)
        payload['rebuild'] = 'incremental_cst_and_edges'
        payload['sequence'] = self.sequence
        payload['changes'] = self.changes
        payload['update_metrics'] = self.metrics
        return payload


class IncrementalDirectoryGraphEngine(DirectoryGraphEngine):
    """Long-lived workspace analyzer; one instance per workspace/worker."""

    def __init__(self, root, **kwargs):
        super().__init__(root, **kwargs)
        self._cache: dict[str, CachedFile] = {}
        self._graph = nx.MultiDiGraph()
        self._references: dict[str, list[dict]] = {}
        self._sequence = 0

    def _discover(self):
        files, directories, excluded, issues = {}, {}, [], []

        def walk_error(error):
            issues.append(dict(kind='directory_read_error', message=str(error)))

        for directory, dirs, names in os.walk(self.root, followlinks=False, onerror=walk_error):
            folder = Path(directory)
            rel_dir = folder.relative_to(self.root).as_posix()
            directories[rel_dir] = dict(parent=None if rel_dir == '.' else 'dir:' + PurePosixPath(rel_dir).parent.as_posix())
            keep = []
            for name in sorted(dirs):
                path = folder / name
                if name.startswith('.') or name in EXCLUDED or name.endswith('.egg-info') or path.is_symlink():
                    excluded.append(dict(path=path.relative_to(self.root).as_posix(), reason='directory_policy_or_symlink'))
                else:
                    keep.append(name)
            dirs[:] = keep
            for name in sorted(names):
                path = folder / name
                rel = path.relative_to(self.root).as_posix()
                if path.is_symlink() or name.startswith('.') or path.resolve() in self.excluded_paths or not path.is_file():
                    excluded.append(dict(path=rel, reason='hidden_symlink_output_or_special'))
                    continue
                if len(files) >= self.max_files:
                    raise ValueError(f'File limit exceeded: {self.max_files}')
                files[rel] = path
        return files, directories, excluded, issues

    def analyze(self):
        files, directories, excluded, issues = self._discover()
        previous = self._cache
        old_paths, new_paths = set(previous), set(files)
        added, removed = new_paths - old_paths, old_paths - new_paths
        changed = set(added)
        cache = {}
        parsed = reused = 0
        total_bytes = 0
        for rel, path in sorted(files.items()):
            language = EXTENSIONS.get(path.suffix.lower())
            if not language:
                cache[rel] = CachedFile(None, None, [])
                continue
            try:
                with path.open('rb') as handle:
                    raw = handle.read(self.cst.max_bytes + 1)
                digest = sha256(raw).hexdigest()
                old = previous.get(rel)
                if old and old.digest == digest:
                    entry = old
                    reused += 1
                else:
                    try:
                        report = self.cst.parse_bytes(raw, language, str(path))
                        entry = CachedFile(digest, report, extract_dependencies(report))
                    except ValueError as exc:
                        entry = CachedFile(digest, None, [], str(exc))
                    parsed += 1
                    changed.add(rel)
                cache[rel] = entry
                if entry.report:
                    total_bytes += entry.report['metrics']['bytes']
                    if total_bytes > self.max_total_bytes:
                        raise RuntimeError('Total source byte limit exceeded')
            except OSError as exc:
                cache[rel] = CachedFile(None, None, [], str(exc))
                changed.add(rel)
        modified = changed - added
        # A rename is still processed as one removal and one addition. Report it
        # separately for consumers of the update contract.
        removed_by_hash = {}
        for rel in sorted(removed):
            entry = previous[rel]
            if entry.digest:
                removed_by_hash.setdefault(entry.digest, []).append(rel)
        renamed = []
        for rel in sorted(added):
            entry = cache[rel]
            sources = removed_by_hash.get(entry.digest, []) if entry.digest else []
            if sources:
                renamed.append(dict(from_path=sources.pop(0), to_path=rel))

        graph = self._graph
        for rel in sorted(removed):
            node = 'file:' + rel
            if node in graph: graph.remove_node(node)
            self._references.pop(rel, None)
        for rel in sorted(new_paths):
            node = 'file:' + rel
            language = EXTENSIONS.get(files[rel].suffix.lower())
            entry = cache[rel]
            if node not in graph:
                graph.add_node(node)
            attrs = dict(path=rel, directory=PurePosixPath(rel).parent.as_posix(), language=language,
                         status=('unsupported' if not language else
                                 'analysis_error' if entry.error else entry.report['status']))
            if entry.report:
                attrs.update(sha256=entry.report['sha256'],
                             cst=dict(nodes=len(entry.report['nodes']), diagnostics=entry.report['diagnostics']))
            graph.nodes[node].clear()
            graph.nodes[node].update(attrs)

        modules, identities = {}, {}
        for rel in sorted(new_paths):
            if files[rel].suffix.lower() != '.py': continue
            identities[rel] = set()
            for source_root in self.python_roots:
                if files[rel].is_relative_to(source_root):
                    parts = list(files[rel].relative_to(source_root).with_suffix('').parts)
                    if parts[-1] == '__init__': parts.pop()
                    module = '.'.join(parts)
                    if module:
                        modules.setdefault(module, set()).add(rel)
                        identities[rel].add(module)
        # The module universe changed: cached imports may now resolve differently.
        # Content-only edits touch just their own outgoing edges.
        resolve_sources = {rel for rel in (new_paths if added or removed else changed)
                           if EXTENSIONS.get(files[rel].suffix.lower())}
        for rel in sorted(resolve_sources):
            node = 'file:' + rel
            graph.remove_edges_from(list(graph.out_edges(node, keys=True)))
            refs = []
            for index, candidate in enumerate(cache[rel].candidates):
                if candidate['evidence']['has_error']:
                    status, targets, reason = 'unresolved', [], 'malformed_dependency'
                elif files[rel].suffix.lower() == '.py':
                    status, targets, reason = self._python(rel, candidate, modules, identities)
                else:
                    status, targets, reason = self._javascript(rel, candidate, files)
                ref_id = f'ref:{rel}:{index}'
                ref = dict(id=ref_id, source=node, **candidate, status=status,
                           candidates=targets, reason=reason)
                refs.append(ref)
                if status == 'resolved_local':
                    graph.add_edge(node, 'file:' + targets[0], key=ref_id, kind=candidate['kind'],
                                   specifier=candidate['specifier'], evidence=candidate['evidence'],
                                   type_only=candidate.get('type_only', False), resolution=reason)
            self._references[rel] = refs

        csts = {}
        for rel, entry in sorted(cache.items()):
            if entry.error:
                issues.append(dict(path=rel, kind='analysis_error', message=entry.error))
            elif entry.report:
                if self.include_cst: csts['file:' + rel] = entry.report
                if entry.report['diagnostics']:
                    issues.append(dict(path=rel, kind='syntax_errors', diagnostics=entry.report['diagnostics']))
        self._cache = cache
        self._sequence += 1
        snapshot = DirectoryGraph(self.root, graph.copy(), directories,
                                  [r for rel in sorted(self._references) for r in self._references[rel]],
                                  issues, excluded, csts)
        return IncrementalResult(snapshot, self._sequence,
                                 dict(added=sorted(added), modified=sorted(modified),
                                      removed=sorted(removed), renamed=renamed),
                                 dict(parsed_files=parsed, reused_files=reused,
                                      re_resolved_files=len(resolve_sources), files=len(files)))
