"""Standalone file-to-CST service. No graph, execution or type checking."""
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from importlib.metadata import version

from tree_sitter import Language, Parser

EXTENSIONS = {'.py': 'python', '.js': 'javascript', '.mjs': 'javascript',
              '.cjs': 'javascript', '.jsx': 'javascript', '.ts': 'typescript',
              '.mts': 'typescript', '.cts': 'typescript', '.tsx': 'tsx'}
GRAMMAR_PACKAGES = {'python': 'tree-sitter-python', 'javascript': 'tree-sitter-javascript',
                    'typescript': 'tree-sitter-typescript', 'tsx': 'tree-sitter-typescript'}


class CSTError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class CSTService:
    """Sequential reusable parser service; create one instance per worker/thread."""
    def __init__(self, max_bytes=1_000_000, max_nodes=200_000):
        if max_bytes < 1 or max_nodes < 1:
            raise ValueError('Limits must be positive')
        self.max_bytes = max_bytes
        self.max_nodes = max_nodes
        self.parsers = {}

    def _parser(self, language):
        if language not in GRAMMAR_PACKAGES:
            raise CSTError('unsupported_language', f'Unsupported language: {language}')
        if language not in self.parsers:
            if language == 'python':
                import tree_sitter_python as grammar
                capsule = grammar.language()
            elif language == 'javascript':
                import tree_sitter_javascript as grammar
                capsule = grammar.language()
            else:
                import tree_sitter_typescript as grammar
                capsule = grammar.language_tsx() if language == 'tsx' else grammar.language_typescript()
            self.parsers[language] = Parser(Language(capsule))
        return self.parsers[language]

    def parse_file(self, path, language=None):
        path = Path(path).expanduser().resolve()
        language = language or EXTENSIONS.get(path.suffix.lower())
        if language not in GRAMMAR_PACKAGES:
            raise CSTError('unsupported_extension', f'Unsupported extension: {path.suffix}')
        if not path.is_file():
            raise CSTError('not_a_file', f'Not a regular file: {path}')
        try:
            with path.open('rb') as handle:
                source = handle.read(self.max_bytes + 1)
        except OSError as exc:
            raise CSTError('read_error', str(exc)) from exc
        return self.parse_bytes(source, language, str(path))

    def parse_bytes(self, source: bytes, language: str, path='<memory>'):
        if len(source) > self.max_bytes:
            raise CSTError('file_too_large', f'Maximum source size: {self.max_bytes} bytes')
        try:
            text = source.decode('utf-8')
        except UnicodeError as exc:
            raise CSTError('invalid_encoding', 'Only UTF-8 is supported') from exc
        parser = self._parser(language)
        started = perf_counter()
        tree = parser.parse(source)
        parse_ms = (perf_counter() - started) * 1000
        nodes, diagnostics = [], []
        stack = [(tree.root_node, None, None, 0)]
        # Flat adjacency preserves the entire tree without recursive JSON limits or
        # copying the source text once for every ancestor of a token.
        while stack:
            node, parent, field, depth = stack.pop()
            if len(nodes) >= self.max_nodes:
                raise CSTError('node_limit', f'Maximum CST size: {self.max_nodes} nodes')
            ident = len(nodes)
            item = {'id': ident, 'parent': parent, 'field': field, 'type': node.type,
                    'named': node.is_named, 'extra': node.is_extra,
                    'error': node.is_error, 'missing': node.is_missing,
                    'has_error': node.has_error, 'start_byte': node.start_byte,
                    'end_byte': node.end_byte,
                    'start': {'line': node.start_point.row + 1, 'byte_column': node.start_point.column},
                    'end': {'line': node.end_point.row + 1, 'byte_column': node.end_point.column},
                    'depth': depth, 'children': []}
            nodes.append(item)
            if parent is not None:
                nodes[parent]['children'].append(ident)
            if node.is_error or node.is_missing:
                diagnostics.append({'code': 'missing_token' if node.is_missing else 'syntax_error',
                                    'node_id': ident, 'type': node.type,
                                    'start': item['start'], 'end': item['end'],
                                    'start_byte': node.start_byte, 'end_byte': node.end_byte})
            children = node.children
            stack.extend((children[i], ident, node.field_name_for_child(i), depth + 1)
                         for i in range(len(children) - 1, -1, -1))
        return {'schema_version': 1, 'path': path, 'language': language,
                'status': 'syntax_errors' if tree.root_node.has_error else 'parsed',
                'encoding': 'utf-8', 'sha256': sha256(source).hexdigest(),
                'coordinates': {'line_base': 1, 'column_base': 0, 'column_unit': 'utf8_bytes', 'end_exclusive': True},
                'versions': {'tree_sitter': version('tree-sitter'), 'grammar': version(GRAMMAR_PACKAGES[language])},
                'metrics': {'bytes': len(source), 'nodes': len(nodes), 'parse_ms': round(parse_ms, 3),
                            'parse_and_extract_ms': round((perf_counter() - started) * 1000, 3)},
                'source': text, 'root_id': 0, 'nodes': nodes, 'diagnostics': diagnostics}


def tree_text(report):
    """Human-readable full tree; source excerpts only on leaves."""
    source = report['source'].encode('utf-8')
    lines = [f"{report['language']} | {report['status']} | {report['path']}"]
    for node in report['nodes']:
        marker = ' MISSING' if node['missing'] else ' ERROR' if node['error'] else ''
        field = f"{node['field']}: " if node['field'] else ''
        snippet = ''
        if not node['children']:
            snippet = ' ' + repr(source[node['start_byte']:node['end_byte']].decode('utf-8')[:80])
        lines.append(f"{'  ' * min(node['depth'], 50)}{field}{node['type']}"
                     f" [{node['start_byte']}:{node['end_byte']}]{marker}{snippet}")
    return '\n'.join(lines)
