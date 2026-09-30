from io import StringIO
import json
from pathlib import Path
import subprocess
import sys

import pytest

from safecode_core.cst import CSTError, CSTService, tree_text
from safecode_core.cst_cli import serve

EXAMPLES = Path(__file__).resolve().parents[3] / 'examples' / 'cst'


@pytest.mark.parametrize('language,source,root', [
    ('python', 'def greet(name):\n    return "Hola 🌎"\n', 'module'),
    ('javascript', 'const greet = (name) => `Hola ${name} 🌎`;', 'program'),
    ('typescript', 'interface User { name: string; }', 'program'),
    ('tsx', 'const C = () => <h1>Hola 🌎</h1>;', 'program'),
])
def test_complete_tree_and_ranges(language, source, root):
    report = CSTService().parse_bytes(source.encode(), language)
    assert report['status'] == 'parsed'
    assert report['nodes'][0]['type'] == root
    assert report['source'] == source
    nodes = report['nodes']
    for node in nodes:
        assert 0 <= node['start_byte'] <= node['end_byte'] <= len(source.encode())
        source.encode()[node['start_byte']:node['end_byte']].decode('utf-8')
        for child in node['children']:
            assert nodes[child]['parent'] == node['id']
            assert node['start_byte'] <= nodes[child]['start_byte'] <= nodes[child]['end_byte'] <= node['end_byte']
    assert any(not n['named'] for n in nodes)
    assert any(n['field'] for n in nodes)
    assert sum(len(n['children']) for n in nodes) == len(nodes) - 1
    assert root in tree_text(report)


@pytest.mark.parametrize('file', sorted(EXAMPLES.rglob('*.*')))
def test_examples(file):
    report = CSTService().parse_file(file)
    expected = 'syntax_errors' if file.stem == 'broken' else 'parsed'
    assert report['status'] == expected, (file, report['diagnostics'])
    if expected == 'syntax_errors':
        assert report['diagnostics']


def test_missing_anonymous_tokens():
    result = CSTService().parse_bytes(b'def broken(:\n', 'python')
    assert any(n['missing'] and not n['named'] for n in result['nodes'])
    assert result['diagnostics']


def test_empty_comments_and_crlf():
    service = CSTService()
    assert service.parse_bytes(b'', 'javascript')['status'] == 'parsed'
    result = service.parse_bytes('// hi\r\nconst café = 1;\r\n'.encode(), 'javascript')
    comment = next(n for n in result['nodes'] if n['type'] == 'comment')
    assert comment['extra']
    assert next(n for n in result['nodes'] if n['type'] == 'lexical_declaration')['start']['line'] == 2


def test_limits_and_paths(tmp_path):
    service = CSTService(max_bytes=10)
    for raw, code in [(b'\xff','invalid_encoding'), (b'x'*11,'file_too_large')]:
        with pytest.raises(CSTError) as exc:
            service.parse_bytes(raw, 'python')
        assert exc.value.code == code
    with pytest.raises(CSTError):
        service.parse_file(tmp_path / 'missing.py')
    with pytest.raises(CSTError):
        service.parse_file(tmp_path / 'unsupported.html')
    with pytest.raises(CSTError) as exc:
        CSTService(max_nodes=1).parse_bytes(b'x=1', 'python')
    assert exc.value.code == 'node_limit'


def test_stdio_recovers_and_rereads(tmp_path):
    file = tmp_path / 'a.ts'
    file.write_text('const x: number = 1;')
    output = StringIO()
    requests = ['not JSON', '[]', '{"path": 4}', json.dumps({'id': 'ok', 'path': str(file)})]
    service = CSTService()
    serve(service, StringIO('\n'.join(requests)+'\n'), output)
    results = [json.loads(x) for x in output.getvalue().splitlines()]
    assert len(results) == 4
    assert all('error' in x for x in results[:3])
    assert results[-1]['id'] == 'ok' and results[-1]['result']['status'] == 'parsed'
    before = results[-1]['result']['sha256']
    file.write_text('const x: = ;')
    after = service.parse_file(file)
    assert after['sha256'] != before and after['status'] == 'syntax_errors'
    assert len(service.parsers) == 1


def test_standalone_cli_no_networkx(tmp_path):
    file = tmp_path / 'hello.js'
    file.write_text('console.log("hi");')
    result = subprocess.run([sys.executable, '-m', 'safecode_core.cst_cli', str(file)],
                            capture_output=True, text=True, check=True)
    assert json.loads(result.stdout)['language'] == 'javascript'
    result = subprocess.run([sys.executable, '-c',
                            'from safecode_core import CSTService; import sys; assert "networkx" not in sys.modules'],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
