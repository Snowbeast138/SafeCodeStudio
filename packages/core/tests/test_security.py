"""Diverse, synthetic pattern examples; no source code is executed by the analyzer."""
import json
from pathlib import Path

import pytest

from safecode_core.security import analyze, render_html


@pytest.mark.parametrize('name,source,expected', [
    ('sql_fstring.py', "user = input()\nq = f'SELECT * FROM users WHERE name={user}'\ncursor.execute(q)\n", {'SEG-01'}),
    ('sql_concat.py', "from flask import request\nuid = request.args['id']\ncursor.execute('DELETE FROM users WHERE id=' + uid)\n", {'SEG-01'}),
    ('sql_format.py', "from flask import request\nq = 'SELECT * FROM users WHERE id={}'.format(request.args['id'])\nconnection.execute(q)\n", {'SEG-01'}),
    ('sql_template.ts', 'const uid = req.params.id;\nconst q = `SELECT * FROM users WHERE id=${uid}`;\ndb.query(q);\n', {'SEG-01'}),
    ('sql_direct.js', 'db.query(`DELETE FROM users WHERE id=${req.query.id}`);\n', {'SEG-01'}),
    ('sql_no_spaces.js', "const id=req.query.id; db.query('SELECT * FROM users WHERE id='+id);\n", {'SEG-01'}),
    ('sql_safe.py', "uid = input()\ncursor.execute('SELECT * FROM users WHERE id = ?', (uid,))\n", set()),
    ('sql_safe.ts', "const uid = req.query.id;\ndb.query('SELECT * FROM users WHERE id = ?', [uid]);\n", set()),
    ('sql_static.py', "cursor.execute('SELECT * FROM users')\n", set()),
    ('sql_reassigned.py', "uid = input()\nq = f'SELECT * FROM users WHERE id={uid}'\nq = 'SELECT * FROM users'\ncursor.execute(q)\n", set()),
    ('cmd_python.py', "import subprocess\nname = input()\ncmd = f'grep {name} data.txt'\nsubprocess.run(cmd, shell=True)\n", {'SEG-02'}),
    ('cmd_os.py', "import os\nfrom flask import request\nos.system('echo ' + request.args['message'])\n", {'SEG-02'}),
    ('cmd_node.js', 'const user = req.body.name;\nconst command = `echo ${user}`;\nexec(command);\n', {'SEG-02'}),
    ('cmd_spawn.ts', "const path = req.query.path;\nspawn('ls ' + path, { shell: true });\n", {'SEG-02'}),
    ('cmd_safe.py', "import subprocess\nname = input()\nsubprocess.run(['grep', name, 'data.txt'], shell=False)\n", set()),
    ('cmd_safe.js', "const user = req.query.user;\nspawn('echo', [user]);\n", set()),
    ('secret_py.py', "api_key = 'synthetic-token-for-unit-tests'\n", {'SEG-03'}),
    ('secret_js.js', "const password = 'unit-test-only-password';\n", {'SEG-03'}),
    ('secret_ts.ts', "let accessToken = 'fake-test-token-1234';\n", {'SEG-03'}),
    ('secret_env.py', "import os\napi_key = os.environ['API_KEY']\n", set()),
    ('secret_placeholder.js', "const password = 'changeme';\n", set()),
])
def test_patterns(tmp_path, name, source, expected):
    (tmp_path / name).write_text(source, encoding='utf-8')
    report = analyze(tmp_path)
    assert {f['rule_id'] for f in report['findings']} == expected
    assert report['coverage']['ARQ-01'] == 'skipped'
    for finding in report['findings']:
        assert finding['cst_node_id'] is not None
        assert finding['start']['line'] >= 1
        if finding['rule_id'] == 'SEG-03':
            assert 'unit-test-only' not in json.dumps(finding)


def test_architecture_added_cycle_and_forbidden_layer(tmp_path):
    old = tmp_path / 'old'; new = tmp_path / 'new'
    old.mkdir(); new.mkdir()
    for root in (old, new):
        (root / 'ui').mkdir(); (root / 'data').mkdir()
        (root / 'data' / 'repo.ts').write_text('export const value = 1;\n')
    (old / 'ui' / 'screen.ts').write_text('export const screen = 1;\n')
    (new / 'ui' / 'screen.ts').write_text("import { value } from '../data/repo';\nexport const screen = value;\n")
    (new / 'data' / 'repo.ts').write_text("import { screen } from '../ui/screen';\nexport const value = screen;\n")
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'forbidden': [{'from': 'ui/*', 'to': 'data/*'}]}))
    report = analyze(new, old, policy)
    assert {f['rule_id'] for f in report['findings']} == {'ARQ-01', 'ARQ-02'}
    assert all(f['cst_node_id'] is not None and f['start']['line'] == 1 for f in report['findings'])
    assert all(v == 'analyzed' for v in report['coverage'].values())
    assert report['status'] == 'complete_for_supported_scope'
    assert '<!doctype html>' in render_html(report)


def test_preexisting_cycle_is_not_new(tmp_path):
    for name in ('old', 'new'):
        root = tmp_path / name; root.mkdir()
        (root / 'a.py').write_text('import b\n')
        (root / 'b.py').write_text('import a\n')
    report = analyze(tmp_path / 'new', tmp_path / 'old')
    assert not report['findings']
    assert report['coverage']['ARQ-01'] == 'analyzed'


def test_syntax_error_is_reported_as_incomplete(tmp_path):
    (tmp_path / 'broken.py').write_text('def broken(:\n')
    report = analyze(tmp_path)
    assert report['status'] == 'partial'
    assert report['issues']


def test_policy_requires_explicit_forbidden_list(tmp_path):
    previous = tmp_path / 'previous'; current = tmp_path / 'current'
    previous.mkdir(); current.mkdir()
    policy = tmp_path / 'policy.json'
    policy.write_text('{}')
    with pytest.raises(ValueError):
        analyze(current, previous, policy)
