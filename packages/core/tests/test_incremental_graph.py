from pathlib import Path

from safecode_core.directory_graph import DirectoryGraphEngine
from safecode_core.incremental_graph import IncrementalDirectoryGraphEngine


def write(root, path, content):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')


def normalized(snapshot):
    return (
        {n: (d['path'], d['status'], d['language']) for n, d in snapshot.graph.nodes(data=True)},
        {(snapshot.graph.nodes[a]['path'], snapshot.graph.nodes[b]['path'], d['kind'], d['specifier'])
         for a, b, d in snapshot.graph.edges(data=True)},
        {(r['source'], r['kind'], r['specifier'], r['status'], tuple(r['candidates']))
         for r in snapshot.references},
        {(i['path'], i['kind']) for i in snapshot.issues if 'path' in i},
    )


def assert_matches_full(root, result):
    full = DirectoryGraphEngine(root).analyze()
    assert normalized(result.snapshot) == normalized(full)


def test_content_only_reparses_and_re_resolves_one_file(tmp_path):
    write(tmp_path, 'main.ts', "import './a';\n")
    write(tmp_path, 'a.ts', 'export const a = 1;\n')
    write(tmp_path, 'b.ts', 'export const b = 1;\n')
    engine = IncrementalDirectoryGraphEngine(tmp_path, include_cst=True)
    first = engine.analyze()
    assert first.metrics['parsed_files'] == 3
    assert_matches_full(tmp_path, first)
    old_edges = set(first.snapshot.graph.edges())
    write(tmp_path, 'main.ts', "import './b';\n")
    second = engine.analyze()
    assert second.changes['modified'] == ['main.ts']
    assert second.metrics['parsed_files'] == 1
    assert second.metrics['reused_files'] == 2
    assert second.metrics['re_resolved_files'] == 1
    assert_matches_full(tmp_path, second)
    assert set(first.snapshot.graph.edges()) == old_edges  # prior result is immutable
    assert set(second.snapshot.graph.edges()) != old_edges
    third = engine.analyze()
    assert third.metrics['parsed_files'] == third.metrics['re_resolved_files'] == 0
    assert_matches_full(tmp_path, third)


def test_add_delete_and_rename_update_other_files_resolution(tmp_path):
    write(tmp_path, 'main.ts', "import './target';\n")
    write(tmp_path, 'other.py', 'import pkg\n')
    engine = IncrementalDirectoryGraphEngine(tmp_path)
    assert_matches_full(tmp_path, engine.analyze())
    write(tmp_path, 'target.ts', 'export const x = 1;\n')
    added = engine.analyze()
    assert added.changes['added'] == ['target.ts']
    assert added.metrics['re_resolved_files'] == 3
    assert_matches_full(tmp_path, added)
    (tmp_path / 'target.ts').rename(tmp_path / 'target.js')
    renamed = engine.analyze()
    assert renamed.changes['renamed'] == [{'from_path': 'target.ts', 'to_path': 'target.js'}]
    assert_matches_full(tmp_path, renamed)
    (tmp_path / 'target.js').unlink()
    deleted = engine.analyze()
    assert deleted.changes['removed'] == ['target.js']
    assert_matches_full(tmp_path, deleted)
    write(tmp_path, 'pkg.py', 'value = 1\n')
    assert_matches_full(tmp_path, engine.analyze())


def test_syntax_error_and_repair(tmp_path):
    write(tmp_path, 'broken.py', 'def broken(:\n')
    engine = IncrementalDirectoryGraphEngine(tmp_path)
    broken = engine.analyze()
    assert broken.snapshot.issues
    assert_matches_full(tmp_path, broken)
    write(tmp_path, 'broken.py', 'def fixed():\n    return 1\n')
    fixed = engine.analyze()
    assert not fixed.snapshot.issues
    assert fixed.metrics['parsed_files'] == 1
    assert_matches_full(tmp_path, fixed)
