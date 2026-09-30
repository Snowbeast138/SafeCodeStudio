import json

import pytest

from safecode_core.workspace import WorkspaceEngine


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_versioned_findings_and_graph_delta(tmp_path):
    write(tmp_path, 'main.py', "api_key = 'synthetic-test-token'\n")
    engine = WorkspaceEngine(tmp_path)
    initial = engine.update('first', 1)
    assert initial['request_id'] == 'first'
    assert initial['version'] == 1
    assert initial['status'] == 'partial'  # no architecture baseline
    assert [f['rule_id'] for f in initial['findings']] == ['SEG-03']
    assert len(initial['graph_delta']['nodes_added']) == 1
    assert len(initial['findings_delta']['added']) == 1
    assert 'csts' in engine.graph_snapshot()
    assert not engine.graph_snapshot()['csts']
    with pytest.raises(ValueError): engine.update('stale', 1)
    assert engine.last_version == 1
    write(tmp_path, 'main.py', "api_key = settings['API_KEY']\n")
    second = engine.update('second', 2)
    assert second['metrics']['parsed_files'] == 1
    assert second['findings'] == []
    assert len(second['findings_delta']['resolved']) == 1
    assert second['graph_delta']['nodes_updated']
    third = engine.update(3, 3)
    assert third['metrics']['parsed_files'] == 0
    assert third['graph_delta']['nodes_updated'] == []
    assert third['findings_delta'] == {'added': [], 'resolved': []}
    assert json.dumps(third, ensure_ascii=False)


def test_architecture_and_content_updates_share_session(tmp_path):
    previous = tmp_path / 'previous'; current = tmp_path / 'current'
    previous.mkdir(); current.mkdir()
    for root in (previous, current):
        write(root, 'ui/a.ts', 'export const a = 1;\n')
        write(root, 'data/b.ts', 'export const b = 1;\n')
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'forbidden': [{'from': 'ui/*', 'to': 'data/*'}]}))
    engine = WorkspaceEngine(current, baseline=previous, policy=policy)
    first = engine.update('1', 1)
    assert first['status'] == 'complete_for_supported_scope'
    assert first['findings'] == []
    write(current, 'ui/a.ts', "import { b } from '../data/b';\nexport const a = b;\n")
    second = engine.update('2', 2)
    assert second['metrics']['parsed_files'] == 1
    assert second['metrics']['re_resolved_files'] == 1
    assert {f['rule_id'] for f in second['findings']} == {'ARQ-02'}
    assert second['graph_delta']['edges_added']
    assert second['reference_delta']['added']
    write(current, 'data/b.ts', "import { a } from '../ui/a';\nexport const b = a;\n")
    third = engine.update('3', 3)
    assert {f['rule_id'] for f in third['findings']} == {'ARQ-01', 'ARQ-02'}
    assert [f['rule_id'] for f in third['findings_delta']['added']] == ['ARQ-01']


def test_missing_reference_becomes_resolved_after_file_added(tmp_path):
    write(tmp_path, 'main.ts', "import './future';\n")
    engine = WorkspaceEngine(tmp_path)
    first = engine.update('1', 1)
    assert first['reference_delta']['added'][0]['status'] == 'unresolved'
    write(tmp_path, 'future.ts', 'export const value = 1;\n')
    second = engine.update('2', 2)
    assert second['metrics']['parsed_files'] == 1
    assert second['reference_delta']['updated'][0]['status'] == 'resolved_local'
    assert second['graph_delta']['edges_added']


def test_invalid_policy_and_versions(tmp_path):
    with pytest.raises(ValueError): WorkspaceEngine(tmp_path, policy=tmp_path / 'missing.json')
    engine = WorkspaceEngine(tmp_path)
    with pytest.raises(ValueError): engine.update('bad', True)
    with pytest.raises(ValueError): engine.update(None, 1)
