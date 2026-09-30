import json
import subprocess
import sys

import networkx as nx
import pytest

from safecode_core import Engine
from safecode_core.parser import PythonParser


def project(tmp_path, files):
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Engine(tmp_path)


def test_import_direction_alias_and_evidence(tmp_path):
    engine = project(tmp_path, {"a.py": "import b as bee\nfrom b import value\n", "b.py": "value = 1\n"})
    result = engine.analyze()
    assert isinstance(result.graph, nx.MultiDiGraph)
    edges = list(result.graph.edges(data=True))
    assert len(edges) == 2
    assert all((a, b) == ("file:a.py", "file:b.py") for a, b, _ in edges)
    assert edges[0][2]["alias"] == "bee"
    assert edges[0][2]["evidence"]["text"] == "import b as bee"
    assert result.affected_by("b.py") == ["a.py", "b.py"]
    assert result.affected_by("a.py") == ["a.py"]


def test_relative_and_package_imports(tmp_path):
    result = project(tmp_path, {"pkg/__init__.py": "from . import worker\n",
                               "pkg/worker.py": "from .utils import helper\n",
                               "pkg/utils.py": "def helper(): pass\n"}).analyze()
    assert set(result.file_graph().edges()) == {("file:pkg/__init__.py", "file:pkg/worker.py"),
                                               ("file:pkg/worker.py", "file:pkg/utils.py")}
    assert not result.issues


def test_nested_symbols_decorators_and_unicode():
    parsed = PythonParser().parse("# á\n@decorator\nclass Café:\n    async def run(self):\n        def nested(): pass\n".encode())
    assert [s["qualified_name"] for s in parsed.symbols] == ["Café", "Café.run", "Café.run.nested"]
    for symbol in parsed.symbols:
        ev = symbol["evidence"]
        assert parsed.source[ev["start_byte"]:ev["end_byte"]].decode() == ev["text"]
    assert parsed.symbols[1]["parent"] == parsed.symbols[0]["local_id"]


def test_errors_and_external_not_silently_clean(tmp_path):
    result = project(tmp_path, {"a.py": "import unknown\ndef broken(:\n"}).analyze()
    assert {i["kind"] for i in result.issues} >= {"syntax_error", "unresolved_import"}
    assert result.to_dict()["status"] == "partial"
    assert not result.graph.nodes["file:a.py"]["syntax_valid"]


def test_no_execution(tmp_path):
    result = project(tmp_path, {"a.py": "raise RuntimeError('never execute')\nimport b\n", "b.py": ""}).analyze()
    assert result.file_graph().has_edge("file:a.py", "file:b.py")


def test_multiple_imports_wildcard_dynamic_and_ambiguity(tmp_path):
    result = project(tmp_path, {"a.py": "import b, c\nfrom c import *\n__import__('b')\n",
                               "b.py": "", "b/__init__.py": "", "c.py": ""}).analyze()
    assert any(i.get("reason") == "ambiguous_module" for i in result.issues)
    assert {i["kind"] for i in result.issues} >= {"dynamic_import", "wildcard_import"}
    assert not result.file_graph().has_edge("file:a.py", "file:b.py")


def test_refresh_equivalence_after_modify_rename_delete(tmp_path):
    engine = project(tmp_path, {"a.py": "import b\n", "b.py": "x = 1\n"})
    engine.analyze()
    cached = engine.analyze()
    assert (cached.parsed_files, cached.cached_files) == (0, 2)
    (tmp_path / "b.py").rename(tmp_path / "c.py")
    (tmp_path / "a.py").write_text("import c\n")
    (tmp_path / "c.py").write_text("x = 2\n")
    refreshed = engine.analyze().to_dict()
    fresh = Engine(tmp_path).analyze().to_dict()
    assert refreshed == fresh
    (tmp_path / "c.py").unlink()
    result = engine.analyze()
    assert "file:c.py" not in result.graph
    assert "c.py" not in engine.cache
    assert result.issues[0]["reason"] == "external_or_missing"


def test_cycle_and_transitive_consumers(tmp_path):
    result = project(tmp_path, {"a.py": "import b\n", "b.py": "import a\n", "c.py": "import a\n"}).analyze()
    assert result.to_dict()["cyclic_components"] == [["a.py", "b.py"]]
    assert result.affected_by("b.py") == ["a.py", "b.py", "c.py"]


def test_src_root_and_beyond_package(tmp_path):
    project(tmp_path, {"src/pkg/__init__.py": "", "src/pkg/a.py": "from .. import bad\n",
                       "src/main.py": "import pkg.a\n"})
    result = Engine(tmp_path, ("src",)).analyze()
    assert result.file_graph().has_edge("file:src/main.py", "file:src/pkg/a.py")
    assert any(i.get("reason") == "relative_beyond_package" for i in result.issues)
    with pytest.raises(ValueError):
        Engine(tmp_path, ("..",))


def test_limits_encoding_symlinks_and_exclusions(tmp_path):
    project(tmp_path, {"a.py": "x" * 20, ".venv/ignored.py": "invalid (", "b.py": ""})
    (tmp_path / "bad.py").write_bytes(b"\xff")
    (tmp_path / "link.py").symlink_to(tmp_path / "b.py")
    result = Engine(tmp_path, max_file_bytes=10).analyze()
    assert {i["kind"] for i in result.issues} == {"file_too_large", "read_error", "symlink_skipped"}
    assert "file:.venv/ignored.py" not in result.graph
    with pytest.raises(ValueError):
        Engine(tmp_path).inspect_cst("../outside.py")


def test_cst_and_json_cli(tmp_path):
    engine = project(tmp_path, {"a.py": "x = 1\n"})
    cst = engine.inspect_cst("a.py")
    assert cst["node_type"] == "module"
    assert cst["children"][0]["node_type"] == "expression_statement"
    completed = subprocess.run([sys.executable, "-m", "safecode_core", str(tmp_path)],
                               capture_output=True, text=True, check=True)
    assert json.loads(completed.stdout)["metrics"]["files"] == 1
