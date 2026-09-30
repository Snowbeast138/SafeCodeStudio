import json
import pytest
from safecode_core.directory_graph import DirectoryGraphEngine
from safecode_core.graph_view import render_graph

def write(root, files):
    for name,content in files.items():
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(content)

def pairs(result):
    return {(a[5:],b[5:]) for a,b in result.graph.edges()}

def test_multilanguage_evidence(tmp_path):
    write(tmp_path, {'pkg/__init__.py':'', 'pkg/a.py':'from . import b\nimport os\n', 'pkg/b.py':'x=1',
       'main.ts':'import type { T } from "./types.js";\nexport { x } from "./lib.js";\nconst a = require("./lib.js"); import("./lib.js"); import(name);',
       'types.ts':'export interface T {x:number}', 'lib.js':'export const x=1;', 'isolated.js':'// import "./lib.js"\nconst x="require(a)";',
       'view.tsx':'import {x} from "./lib.js"; export const view=<div>{x}</div>;'} )
    result=DirectoryGraphEngine(tmp_path,include_cst=True).analyze()
    assert pairs(result)=={('pkg/a.py','pkg/b.py'),('main.ts','types.ts'),('main.ts','lib.js'),('view.tsx','lib.js')}
    assert result.graph.number_of_edges()==6
    assert 'file:isolated.js' in result.to_dict()['isolated_files']
    for ref in result.references:
        report=result.csts[ref['source']]; e=ref['evidence']; n=report['nodes'][e['id']]
        assert report['source'].encode()[n['start_byte']:n['end_byte']].decode()==e['text']
    assert any(r['status']=='unresolved' for r in result.references)

def test_subgraphs_cycles_changes(tmp_path):
    write(tmp_path,{'a.js':'import "./sub/b.js";', 'sub/b.js':'import "../a.js";', 'sub/note.md':'hello'})
    (tmp_path/'empty').mkdir()
    engine=DirectoryGraphEngine(tmp_path); result=engine.analyze(); sub=result.to_dict('sub')
    assert len(sub['boundary_edges'])==2 and len(sub['nodes'])==2 and not sub['edges']
    assert len(result.to_dict()['cyclic_components'])==1
    assert not result.subgraph('empty').nodes
    assert result.affected_by('sub/b.js')==['a.js','sub/b.js']
    (tmp_path/'sub/b.js').unlink()
    assert not engine.analyze().graph.edges
    with pytest.raises(ValueError): result.subgraph('../')

def test_resolution_and_limits(tmp_path):
    write(tmp_path,{'main.ts':'import "./x"; import "@/asset.css"; import "missing"; import "../outside.js";',
                    'x.ts':'','x.js':'','sub/asset.css':'body{}','.env':'secret','node_modules/a.js':''})
    result=DirectoryGraphEngine(tmp_path,aliases={'@/':'sub'}).analyze()
    assert pairs(result)=={('main.ts','sub/asset.css')}
    assert result.references[0]['status']=='ambiguous'
    assert len(result.excluded)==2
    with pytest.raises(ValueError): DirectoryGraphEngine(tmp_path,max_files=1).analyze()
    with pytest.raises(RuntimeError): DirectoryGraphEngine(tmp_path,max_total_bytes=1).analyze()
    with pytest.raises(ValueError): DirectoryGraphEngine(tmp_path,aliases={'@/':'../'})

def test_errors_and_safe_html(tmp_path):
    write(tmp_path,{'broken.py':'def :','bad.js':'import "./missing.js"; // </script><script>alert(1)</script>'})
    (tmp_path/'encoding.py').write_bytes(b'\xff')
    r=DirectoryGraphEngine(tmp_path).analyze().to_dict()
    assert len(r['issues'])==2 and r['status']=='partial'
    r['root']='</script><script>alert(1)</script>'
    html=render_graph(r)
    assert r['root'] not in html
    assert json.loads(html.split('id="data">')[1].split('</script>')[0])['root']==r['root']

def test_python_ambiguous_and_dynamic(tmp_path):
    write(tmp_path,{'main.py':'import x\n__import__(name)\n','one/x.py':'','two/x.py':''})
    r=DirectoryGraphEngine(tmp_path,python_roots=('.', 'one','two')).analyze()
    assert [r['status'] for r in r.references]==['ambiguous','unresolved']

def test_empty_and_cli(tmp_path, monkeypatch, capsys):
    from safecode_core.graph_cli import main
    output=tmp_path/'report.html'
    monkeypatch.setattr('sys.argv',['safecode-graph',str(tmp_path),'--format','html','--output',str(output)])
    assert main()==0 and output.is_file()
    assert main()==0
    payload=json.loads(output.read_text().split('id="data">')[1].split('</script>')[0])
    assert not payload['nodes']
    monkeypatch.setattr('sys.argv',['safecode-graph',str(tmp_path),'--subgraph','../'])
    assert main()==2
