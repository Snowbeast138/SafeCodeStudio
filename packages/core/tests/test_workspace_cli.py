import io
import json

from safecode_core.workspace import WorkspaceEngine
from safecode_core.workspace_cli import serve


def test_persistent_json_rpc_and_recoverable_errors(tmp_path):
    (tmp_path / 'main.py').write_text('x = 1\n')
    requests = [
        {'jsonrpc': '2.0', 'id': 'first', 'method': 'analyze', 'params': {'version': 1}},
        {'jsonrpc': '2.0', 'id': 'same', 'method': 'analyze', 'params': {'version': 1}},
        {'jsonrpc': '2.0', 'id': 'graph', 'method': 'graph'},
        {'jsonrpc': '2.0', 'id': 'next', 'method': 'analyze', 'params': {'version': 2}},
        {'jsonrpc': '2.0', 'id': 'done', 'method': 'shutdown'},
    ]
    source = io.StringIO('not-json\n' + ''.join(json.dumps(x) + '\n' for x in requests))
    output = io.StringIO()
    serve(WorkspaceEngine(tmp_path), source, output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert responses[0]['error']['code'] == -32700
    assert responses[1]['result']['metrics']['parsed_files'] == 1
    assert responses[2]['error']['code'] == -32602
    assert responses[3]['result']['nodes']
    assert responses[3]['result']['csts'] == {}
    assert responses[4]['result']['metrics']['parsed_files'] == 0
    assert responses[5]['result']['stopped']


def test_rejects_oversize_and_unknown_method(tmp_path):
    messages = 'x' * 1_000_001 + '\n' + json.dumps({'jsonrpc':'2.0','id':1,'method':'unknown'}) + '\n'
    output = io.StringIO()
    serve(WorkspaceEngine(tmp_path), io.StringIO(messages), output)
    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [r['error']['code'] for r in responses] == [-32600, -32601]
