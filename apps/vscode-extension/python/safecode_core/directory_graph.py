"""Directory snapshots and CST-backed, directed file dependency graphs."""
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import os
import networkx as nx
from .cst import CSTService, EXTENSIONS
from .dependencies import extract_dependencies

EXCLUDED = {'node_modules', 'venv', '__pycache__', 'dist', 'build', 'out', 'coverage'}
JS_SUFFIXES = ('.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts')

@dataclass
class DirectoryGraph:
    root: Path
    graph: nx.MultiDiGraph
    directories: dict
    references: list
    issues: list
    excluded: list
    csts: dict

    def _members(self, directory):
        if directory not in self.directories:
            raise ValueError(f'Directory not in snapshot: {directory}')
        prefix = '' if directory == '.' else directory + '/'
        return {n for n, d in self.graph.nodes(data=True) if d['path'].startswith(prefix)}

    def subgraph(self, directory):
        return self.graph.subgraph(self._members(directory)).copy()

    def affected_by(self, path):
        node = 'file:' + path
        if node not in self.graph:
            raise ValueError(f'File not in snapshot: {path}')
        return sorted(self.graph.nodes[n]['path'] for n in nx.ancestors(self.graph, node) | {node})

    def to_dict(self, directory='.'):
        members = self._members(directory)
        graph = self.graph.subgraph(members)
        all_edges = [dict(id=k, source=a, target=b, **d) for a, b, k, d in sorted(self.graph.edges(keys=True, data=True))]
        edges = [e for e in all_edges if e['source'] in members and e['target'] in members]
        boundary = [e for e in all_edges if (e['source'] in members) != (e['target'] in members)]
        outside = {e[k] for e in boundary for k in ('source', 'target')} - members
        groups = []
        for path, data in sorted(self.directories.items()):
            if path != directory and not path.startswith('' if directory == '.' else directory + '/'):
                continue
            children = self._members(path)
            groups.append(dict(id='dir:' + path, path=path, **data, members=sorted(children),
                               direct_files=sorted(n for n in children if self.graph.nodes[n]['directory'] == path)))
        references = [r for r in self.references if r['source'] in members]
        issues = [i for i in self.issues if directory == '.' or 'path' not in i or i['path'].startswith(directory + '/')]
        cycles = [sorted(s) for s in nx.strongly_connected_components(graph) if len(s) > 1 or any(graph.has_edge(n,n) for n in s)]
        return dict(schema_version=1, root=str(self.root), selected_directory=directory,
                    direction='importer -> dependency', rebuild='full_snapshot',
                    status='partial' if issues or any(r['status'] != 'resolved_local' for r in references) else 'complete_for_supported_scope',
                    nodes=[dict(id=n, **d) for n,d in sorted(graph.nodes(data=True))], edges=edges,
                    directories=groups, boundary_edges=boundary,
                    boundary_nodes=[dict(id=n, **self.graph.nodes[n]) for n in sorted(outside)],
                    references=references, issues=issues, excluded=self.excluded,
                    isolated_files=sorted(n for n,d in graph.degree() if d == 0), cyclic_components=sorted(cycles),
                    metrics=dict(files=len(graph), edges=len(edges), directories=len(groups), boundary_edges=len(boundary)),
                    csts={n:r for n,r in self.csts.items() if n in members})

class DirectoryGraphEngine:
    def __init__(self, root, python_roots=('.',), aliases=None, max_files=2000,
                 include_cst=False, excluded_paths=(), max_total_bytes=20_000_000):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ValueError(f'Root is not a directory: {self.root}')
        if max_files < 1 or max_total_bytes < 1:
            raise ValueError('Limits must be positive')
        self.python_roots = [(self.root / p).resolve() for p in python_roots]
        if any(not p.is_relative_to(self.root) or not p.is_dir() for p in self.python_roots):
            raise ValueError('Python import roots must be directories inside root')
        self.aliases = aliases or {}
        if any(not k or not (self.root / v).resolve().is_relative_to(self.root) for k,v in self.aliases.items()):
            raise ValueError('Aliases must target paths inside root')
        self.max_files, self.max_total_bytes, self.include_cst = max_files, max_total_bytes, include_cst
        self.excluded_paths = {Path(p).resolve() for p in excluded_paths}
        self.cst = CSTService()

    def analyze(self):
        graph, directories, references, issues, excluded, csts = nx.MultiDiGraph(), {}, [], [], [], {}
        files, modules, identities = {}, {}, {}
        def walk_error(error):
            issues.append(dict(kind='directory_read_error', message=str(error)))
        for directory, dirs, names in os.walk(self.root, followlinks=False, onerror=walk_error):
            folder = Path(directory)
            rel_dir = folder.relative_to(self.root).as_posix()
            directories[rel_dir] = dict(parent=None if rel_dir == '.' else 'dir:' + PurePosixPath(rel_dir).parent.as_posix())
            keep = []
            for name in sorted(dirs):
                p = folder / name
                if name.startswith('.') or name in EXCLUDED or name.endswith('.egg-info') or p.is_symlink():
                    excluded.append(dict(path=p.relative_to(self.root).as_posix(), reason='directory_policy_or_symlink'))
                else:
                    keep.append(name)
            dirs[:] = keep
            for name in sorted(names):
                p = folder / name
                rel = p.relative_to(self.root).as_posix()
                if p.is_symlink() or name.startswith('.') or p.resolve() in self.excluded_paths or not p.is_file():
                    excluded.append(dict(path=rel, reason='hidden_symlink_output_or_special'))
                    continue
                if len(files) >= self.max_files:
                    raise ValueError(f'File limit exceeded: {self.max_files}')
                files[rel] = p
                language = EXTENSIONS.get(p.suffix.lower())
                graph.add_node('file:' + rel, path=rel, directory=rel_dir, language=language, status='pending' if language else 'unsupported')
                if p.suffix.lower() == '.py':
                    identities[rel] = set()
                    for source_root in self.python_roots:
                        if p.is_relative_to(source_root):
                            parts = list(p.relative_to(source_root).with_suffix('').parts)
                            if parts[-1] == '__init__': parts.pop()
                            module = '.'.join(parts)
                            if module:
                                modules.setdefault(module, set()).add(rel)
                                identities[rel].add(module)
        total = 0
        for rel, path in sorted(files.items()):
            node = 'file:' + rel
            if not graph.nodes[node]['language']: continue
            try:
                report = self.cst.parse_file(path)
                total += report['metrics']['bytes']
                if total > self.max_total_bytes:
                    raise RuntimeError('Total source byte limit exceeded')
                graph.nodes[node].update(status=report['status'], sha256=report['sha256'],
                                         cst=dict(nodes=len(report['nodes']), diagnostics=report['diagnostics']))
                if self.include_cst: csts[node] = report
                if report['diagnostics']:
                    issues.append(dict(path=rel, kind='syntax_errors', diagnostics=report['diagnostics']))
                for candidate in extract_dependencies(report):
                    if candidate['evidence']['has_error']:
                        status, targets, reason = 'unresolved', [], 'malformed_dependency'
                    elif report['language'] == 'python':
                        status, targets, reason = self._python(rel, candidate, modules, identities)
                    else:
                        status, targets, reason = self._javascript(rel, candidate, files)
                    ref = dict(id='ref:' + str(len(references)), source=node, **candidate,
                               status=status, candidates=targets, reason=reason)
                    references.append(ref)
                    if status == 'resolved_local':
                        graph.add_edge(node, 'file:' + targets[0], key=ref['id'], kind=candidate['kind'],
                                       specifier=candidate['specifier'], evidence=candidate['evidence'],
                                       type_only=candidate.get('type_only', False), resolution=reason)
            except (OSError, ValueError) as exc:
                graph.nodes[node]['status'] = 'analysis_error'
                issues.append(dict(path=rel, kind='analysis_error', message=str(exc)))
        return DirectoryGraph(self.root, graph, directories, references, issues, excluded, csts)

    def _python(self, rel, candidate, modules, identities):
        module = candidate['specifier']
        if module is None: return 'unresolved', [], 'dynamic_python_import'
        base = module
        if module.startswith('.'):
            names = identities.get(rel, set())
            if len(names) != 1: return 'unresolved', [], 'ambiguous_package_context'
            identity = next(iter(names)).split('.')
            package = identity if Path(rel).name == '__init__.py' else identity[:-1]
            level = len(module) - len(module.lstrip('.'))
            if level > len(package): return 'unresolved', [], 'relative_beyond_package'
            base = '.'.join(package[:len(package)-level+1] + ([module[level:]] if module[level:] else []))
        member = candidate.get('member')
        child = f'{base}.{member}' if member and member != '*' else ''
        targets = sorted(modules.get(child if child in modules else base, set()))
        if len(targets) > 1: return 'ambiguous', targets, 'multiple_python_modules'
        if targets: return 'resolved_local', targets, 'python_module_only'
        return 'external_or_missing', [], 'no_local_python_module'

    def _javascript(self, rel, candidate, files):
        spec = candidate['specifier']
        if spec is None or any(c in spec for c in ('\\', '\x00', '?', '#')):
            return 'unresolved', [], 'nonliteral_or_unsupported_specifier'
        base = None
        if spec.startswith(('./', '../')):
            base = self.root / PurePosixPath(rel).parent / spec
        elif spec.startswith('/'):
            return 'unresolved', [], 'absolute_specifier'
        else:
            for prefix in sorted(self.aliases, key=lambda p: (-len(p), p)):
                if spec == prefix or (prefix.endswith('/') and spec.startswith(prefix)):
                    base = self.root / self.aliases[prefix] / spec[len(prefix):]
                    break
        if base is None: return 'external_or_alias', [], 'bare_specifier_not_resolved'
        base = base.resolve()
        if not base.is_relative_to(self.root): return 'unresolved', [], 'outside_root'
        choices = [base]
        if not base.suffix:
            choices += [base.with_suffix(ext) for ext in JS_SUFFIXES] + [base / ('index' + ext) for ext in JS_SUFFIXES]
        elif Path(rel).suffix.lower() in ('.ts', '.tsx', '.mts', '.cts'):
            substitutions = {'.js': ('.ts', '.tsx'), '.jsx': ('.tsx',), '.mjs': ('.mts',), '.cjs': ('.cts',)}
            choices += [base.with_suffix(ext) for ext in substitutions.get(base.suffix, ())]
        targets = sorted({p.relative_to(self.root).as_posix() for p in choices if p.relative_to(self.root).as_posix() in files})
        if len(targets) > 1: return 'ambiguous', targets, 'multiple_local_candidates'
        if targets: return 'resolved_local', targets, 'static_file_candidate'
        return 'unresolved', [], 'local_target_missing_or_excluded'
