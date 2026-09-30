import json
import subprocess

import pytest

from safecode_core.workspace import WorkspaceEngine


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def test_git_baseline_activates_architecture_rules_without_changing_worktree(tmp_path):
    root = tmp_path / 'project'
    (root / 'ui').mkdir(parents=True)
    (root / 'data').mkdir()
    (root / 'ui' / 'screen.ts').write_text('export const screen = 1;\n')
    (root / 'data' / 'repo.ts').write_text("import '../ui/screen';\nexport const repo = 1;\n")
    _git(root, 'init', '-q')
    _git(root, 'add', '.')
    _git(root, '-c', 'user.name=SafeCode Test', '-c', 'user.email=safecode@example.invalid',
         'commit', '-qm', 'baseline')
    commit = _git(root, 'rev-parse', 'HEAD')
    changed = "import '../data/repo';\nexport const screen = 1;\n"
    (root / 'ui' / 'screen.ts').write_text(changed)
    policy = tmp_path / 'policy.json'
    policy.write_text(json.dumps({'forbidden': [{'from': 'ui/*', 'to': 'data/*'}]}))

    result = WorkspaceEngine(root, git_baseline_ref='HEAD', policy=policy).update('first', 1)
    assert {item['rule_id'] for item in result['findings']} == {'ARQ-01', 'ARQ-02'}
    assert result['coverage']['ARQ-01'] == result['coverage']['ARQ-02'] == 'analyzed'
    assert result['status'] == 'complete_for_supported_scope'
    assert result['baseline'] == {'kind': 'git', 'ref': 'HEAD', 'commit': commit}
    assert (root / 'ui' / 'screen.ts').read_text() == changed
    assert _git(root, 'status', '--short') == 'M ui/screen.ts'


def test_git_baseline_supports_workspace_subfolder(tmp_path):
    repo = tmp_path / 'repo'
    root = repo / 'app'
    root.mkdir(parents=True)
    (root / 'main.py').write_text('x = 1\n')
    _git(repo, 'init', '-q')
    _git(repo, 'add', '.')
    _git(repo, '-c', 'user.name=SafeCode Test', '-c', 'user.email=safecode@example.invalid',
         'commit', '-qm', 'baseline')
    result = WorkspaceEngine(root, git_baseline_ref='HEAD').update('first', 1)
    assert result['coverage']['ARQ-01'] == 'analyzed'
    assert result['coverage']['ARQ-02'] == 'skipped'
    assert result['metrics']['files'] == 1


def test_git_baseline_rejects_invalid_ref_and_conflicting_directory(tmp_path):
    with pytest.raises(ValueError, match='either a baseline directory or a Git baseline ref'):
        WorkspaceEngine(tmp_path, baseline=tmp_path, git_baseline_ref='HEAD')
    with pytest.raises(ValueError, match='Git baseline ref'):
        WorkspaceEngine(tmp_path, git_baseline_ref='--bad')
