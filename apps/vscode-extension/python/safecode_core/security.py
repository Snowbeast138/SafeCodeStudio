"""Conservative, CST-backed deterministic checks for the SafeCode MVP catalog.

This is deliberately an intra-procedural pattern analyzer, not a proof of safety.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from fnmatch import fnmatchcase
from html import escape
import json
from pathlib import Path
import re

import networkx as nx

from .directory_graph import DirectoryGraphEngine

RULES = {
    'SEG-01': ('Consulta SQL construida con entrada externa', 'high'),
    'SEG-02': ('Comando de shell construido con entrada externa', 'high'),
    'SEG-03': ('Credencial literal', 'medium'),
    'ARQ-01': ('Ciclo nuevo entre módulos', 'medium'),
    'ARQ-02': ('Dependencia nueva prohibida entre capas', 'medium'),
}
SOURCE = re.compile(r'\b(?:input\s*\(|req\.(?:query|body|params|headers)\b|request\.(?:args|form|json|values|GET|POST)\b|process\.argv\b|sys\.argv\b|os\.environ\b)', re.I)
SQL = re.compile(r'\b(?:SELECT|INSERT|UPDATE|DELETE|REPLACE|DROP|ALTER|CREATE)\b', re.I)
SHELL = re.compile(r'\bshell\s*=\s*True\b|\bshell\s*:\s*true\b')
SECRET_NAME = re.compile(r'(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|private[_-]?key)', re.I)
PLACEHOLDER = re.compile(r'^(?:|changeme|replace[_-]?me|example|test|dummy|your[_-]?\w+|<[^>]+>|\$\{[^}]+\})$', re.I)
JS_ASSIGN = {'variable_declarator', 'assignment_expression'}
PY_ASSIGN = {'assignment', 'augmented_assignment', 'named_expression'}
CALLS = {'call', 'call_expression'}
SCOPE = {'function_definition', 'function_declaration', 'function', 'arrow_function', 'method_definition'}


def _node_text(report, node):
    return report['source'].encode('utf-8')[node['start_byte']:node['end_byte']].decode('utf-8', 'replace')


def _field(nodes, node, field):
    return next((nodes[i] for i in node['children'] if nodes[i]['field'] == field), None)


def _scope_id(nodes, node):
    parent = node['parent']
    while parent is not None:
        if nodes[parent]['type'] in SCOPE:
            return parent
        parent = nodes[parent]['parent']
    return -1


def _source_tainted(expression, tainted):
    return bool(SOURCE.search(expression) or any(re.search(r'(?<![\w.])' + re.escape(name) + r'(?!\w)', expression) for name in tainted))


def _dynamic(expression, language):
    if language == 'python':
        return bool(re.search(r'''(?:^|\W)[fF]["']|\.format\s*\(|\+|%''', expression))
    return '${' in expression or bool(re.search(r'\+|\.concat\s*\(', expression))


def _finding(rule, path, report, node, detail, excerpt=None):
    title, severity = RULES[rule]
    text = excerpt if excerpt is not None else _node_text(report, node)
    return dict(rule_id=rule, title=title, severity=severity, confidence='pattern',
                path=path, language=report['language'], start=node['start'], end=node['end'],
                cst_node_id=node['id'], cst_node_type=node['type'], source_sha256=report['sha256'],
                evidence=' '.join(text.split())[:220], explanation=detail)


def _scan_file(path, report):
    nodes = report['nodes']
    findings = []
    # Keep assignments in lexical order and within the same function/module scope.
    tainted = {}
    sql_built = {}
    command_built = {}
    for node in nodes:
        if node['error'] or node['has_error']:
            continue
        typ = node['type']
        scope = _scope_id(nodes, node)
        vars_here = tainted.setdefault(scope, set())
        sql_here = sql_built.setdefault(scope, set())
        command_here = command_built.setdefault(scope, set())
        if typ in PY_ASSIGN | JS_ASSIGN:
            left = _field(nodes, node, 'left') or _field(nodes, node, 'name')
            right = _field(nodes, node, 'right') or _field(nodes, node, 'value')
            if left is None or right is None or left['type'] not in {'identifier', 'attribute', 'member_expression'}:
                continue
            name = _node_text(report, left)
            expr = _node_text(report, right)
            if _source_tainted(expr, vars_here): vars_here.add(name)
            else: vars_here.discard(name)
            if (SQL.search(expr) and _dynamic(expr, report['language']) and _source_tainted(expr, vars_here)) or (name in sql_here and _source_tainted(expr, vars_here)):
                sql_here.add(name)
            else: sql_here.discard(name)
            if _dynamic(expr, report['language']) and _source_tainted(expr, vars_here): command_here.add(name)
            else: command_here.discard(name)
            if SECRET_NAME.search(name) and right['type'] in {'string', 'string_literal', 'template_string'}:
                value = expr.strip('"\'`')
                if len(value) >= 4 and not PLACEHOLDER.fullmatch(value) and not value.startswith(('${', 'env:', 'process.env')):
                    findings.append(_finding('SEG-03', path, report, left,
                                             'Se asigna un literal a un identificador de credencial; revisar si debe provenir de configuración segura.',
                                             excerpt=name + ' = [valor omitido]'))
        if typ not in CALLS:
            continue
        fn = _field(nodes, node, 'function')
        if fn is None: continue
        name = _node_text(report, fn)
        args = _node_text(report, node)[len(name):]
        is_sql = bool(re.search(r'\.(?:execute|executemany|query|raw)\b', name))
        if is_sql:
            first = _first_argument(args)
            if (SQL.search(first) and _dynamic(first, report['language']) and _source_tainted(first, vars_here)) or first.strip() in sql_here:
                findings.append(_finding('SEG-01', path, report, node,
                    'Una entrada externa participa en la construcción de una consulta SQL ejecutada por una API soportada. Usar parámetros enlazados.'))
        is_py_command = report['language'] == 'python' and bool(re.search(r'\b(?:subprocess\.(?:run|Popen|call|check_call|check_output)|os\.system)\b', name))
        is_js_command = report['language'] != 'python' and bool(re.search(r'\b(?:exec|execSync|spawn|spawnSync)\b$', name))
        if is_py_command or is_js_command:
            first = _first_argument(args)
            shell_enabled = bool(re.search(r'\bos\.system\b|\bexec(?:Sync)?\b$', name) or SHELL.search(args))
            if shell_enabled and (_source_tainted(first, vars_here) and _dynamic(first, report['language']) or first.strip() in command_here):
                findings.append(_finding('SEG-02', path, report, node,
                    'Una entrada externa participa en un comando ejecutado mediante shell. Usar argumentos separados y evitar shell.'))
    return findings


def _first_argument(args):
    """First top-level argument, respecting strings and nested delimiters."""
    inner = args[args.find('(')+1:args.rfind(')')] if '(' in args else args
    depth, quote, escaped = 0, '', False
    for i, char in enumerate(inner):
        if quote:
            if escaped: escaped = False
            elif char == '\\': escaped = True
            elif char == quote: quote = ''
        elif char in ('"', "'", '`'): quote = char
        elif char in '([{': depth += 1
        elif char in ')]}': depth -= 1
        elif char == ',' and depth == 0: return inner[:i].strip()
    return inner.strip()


def _edges(snapshot):
    return {(snapshot.graph.nodes[a]['path'], snapshot.graph.nodes[b]['path'])
            for a, b in snapshot.graph.edges()}


def _edge_evidence(snapshot, source, target):
    data = snapshot.graph.get_edge_data('file:' + source, 'file:' + target) or {}
    evidence = next((edge.get('evidence') for edge in data.values() if edge.get('evidence')), {})
    return dict(start=evidence.get('start'), end=evidence.get('end'),
                cst_node_id=evidence.get('id'), cst_node_type=evidence.get('type'),
                source_sha256=snapshot.graph.nodes['file:' + source].get('sha256'),
                evidence=evidence.get('text', f'{source} → {target}'))


def _cycles(snapshot):
    g = nx.DiGraph(snapshot.graph)
    return {frozenset(g.nodes[n]['path'] for n in component)
            for component in nx.strongly_connected_components(g)
            if len(component) > 1 or any(g.has_edge(n, n) for n in component)}


def validate_policy(forbidden):
    if not isinstance(forbidden, list) or any(not isinstance(x, dict) or set(x) != {'from', 'to'}
                                              or not all(isinstance(v, str) and v for v in x.values())
                                              for x in forbidden):
        raise ValueError('Policy must contain a forbidden list of {from, to} glob patterns')


def architecture_findings(current, previous, forbidden=None):
    """Compare graph snapshots; forbidden is an optional list of path-glob pairs."""
    findings = []
    added = _edges(current) - _edges(previous)
    old_cycles = _cycles(previous)
    for component in sorted(_cycles(current), key=lambda c: sorted(c)):
        if component in old_cycles: continue
        new_internal = sorted((a, b) for a, b in added if a in component and b in component)
        if not new_internal: continue
        paths = sorted(component)
        source, target = new_internal[0]
        provenance = _edge_evidence(current, source, target)
        findings.append(dict(rule_id='ARQ-01', title=RULES['ARQ-01'][0], severity='medium',
            confidence='graph', path=source, language=current.graph.nodes['file:' + source].get('language'),
            **provenance, explanation='Una dependencia añadida crea un ciclo respecto de la versión base.',
            affected_paths=paths))
    if forbidden is not None:
        validate_policy(forbidden)
        for source, target in sorted(added):
            if any(fnmatchcase(source, rule['from']) and fnmatchcase(target, rule['to']) for rule in forbidden):
                provenance = _edge_evidence(current, source, target)
                findings.append(dict(rule_id='ARQ-02', title=RULES['ARQ-02'][0], severity='medium',
                    confidence='graph', path=source, language=current.graph.nodes['file:' + source].get('language'),
                    **provenance, explanation='La importación nueva viola la política explícita de capas.',
                    affected_paths=[source, target]))
    return findings


def analyze(root, baseline=None, policy=None):
    root = Path(root).expanduser().resolve()
    current = DirectoryGraphEngine(root, include_cst=True).analyze()
    findings = []
    for node_id, report in sorted(current.csts.items()):
        if report['status'] == 'parsed':
            findings.extend(_scan_file(node_id.removeprefix('file:'), report))
    coverage = {rule: 'analyzed' if rule.startswith('SEG') else 'skipped' for rule in RULES}
    notes = []
    if baseline:
        previous = DirectoryGraphEngine(baseline).analyze()
        forbidden = None
        if policy:
            config = json.loads(Path(policy).read_text(encoding='utf-8'))
            if not isinstance(config, dict) or 'forbidden' not in config:
                raise ValueError('Policy must contain a forbidden list')
            forbidden = config['forbidden']
        findings.extend(architecture_findings(current, previous, forbidden))
        coverage['ARQ-01'] = 'analyzed'
        if policy:
            coverage['ARQ-02'] = 'analyzed'
        else:
            notes.append('ARQ-02 omitida: falta --policy.')
    else:
        notes.append('ARQ-01 y ARQ-02 omitidas: falta --baseline; ARQ-02 también requiere --policy.')
    issues = current.issues
    if issues: notes.append('Archivos con errores de análisis o sintaxis no tienen cobertura completa.')
    notes.append('SEG-01/02: flujo local a una función y APIs soportadas; no hay prueba de seguridad ni análisis global de datos.')
    notes.append('SEG-03: heurística de literales; el reporte omite el valor de posibles credenciales.')
    findings.sort(key=lambda f: (f['path'], f['start']['line'] if f['start'] else 0, f['rule_id']))
    return dict(schema_version=1, generated_at=datetime.now(timezone.utc).isoformat(), root=str(root),
                baseline=str(Path(baseline).resolve()) if baseline else None,
                policy=str(Path(policy).resolve()) if policy else None,
                status='partial' if issues or any(v == 'skipped' for v in coverage.values()) else 'complete_for_supported_scope',
                coverage=coverage, metrics=dict(files=len(current.graph), parsed_files=len(current.csts), findings=len(findings),
                by_rule=dict(Counter(f['rule_id'] for f in findings))), findings=findings,
                issues=issues, excluded=current.excluded, notes=notes)


def render_html(report):
    cards = []
    for item in report['findings']:
        place = item['path'] + (f":{item['start']['line']}" if item['start'] else '')
        cards.append(f'<article class="finding"><div class="tag">{escape(item["rule_id"])} · {escape(item["severity"])}</div>'
                     f'<h2>{escape(item["title"])}</h2><p class="path">{escape(place)}</p>'
                     f'<p>{escape(item["explanation"])}</p><code>{escape(item["evidence"])}</code></article>')
    if not cards: cards.append('<p class="empty">No se encontraron patrones en el alcance analizado.</p>')
    coverage = ''.join(f'<li><strong>{escape(k)}</strong>: {escape(v)}</li>' for k, v in report['coverage'].items())
    notes = ''.join(f'<li>{escape(x)}</li>' for x in report['notes'])
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>SafeCode · Análisis determinista</title><style>
    :root{{color-scheme:dark;font-family:system-ui,sans-serif;background:#0d1525;color:#edf5ff}}body{{max-width:1050px;margin:auto;padding:32px 20px}}header{{padding:28px;border:1px solid #346478;border-radius:18px;background:linear-gradient(120deg,#143b5b,#123c3b)}}h1{{margin:0 0 8px}}.lead{{color:#d6e9ed}}.stats{{display:flex;gap:16px;flex-wrap:wrap;margin:22px 0}}.stat,.finding,.panel{{border:1px solid #304963;border-radius:14px;background:#17253a;padding:18px}}.stat strong{{display:block;font-size:1.7rem;color:#72dfca}}.finding{{margin:14px 0}}.finding h2{{font-size:1.1rem;margin:6px 0}}.tag{{color:#82dec8;font-weight:bold;font-size:.85rem}}.path{{color:#9db7dc}}code{{display:block;padding:12px;overflow-wrap:anywhere;background:#0b1728;border-radius:8px;color:#e9d99e}}.panel{{margin-top:18px}}li{{margin:7px 0}}.empty{{padding:24px}}
    </style></head><body><header><h1>SafeCode Studio · Informe de análisis</h1><p class="lead">Reglas deterministas basadas en CST y relaciones entre archivos. Los hallazgos requieren revisión humana.</p><small>{escape(report['root'])} · {escape(report['generated_at'])}</small></header><section class="stats"><div class="stat"><strong>{report['metrics']['files']}</strong>archivos</div><div class="stat"><strong>{report['metrics']['findings']}</strong>hallazgos</div><div class="stat"><strong>{escape(report['status'])}</strong>estado</div></section><main>{''.join(cards)}</main><section class="panel"><h2>Cobertura de reglas</h2><ul>{coverage}</ul><h2>Límites y observaciones</h2><ul>{notes}</ul><p>Problemas de análisis: {len(report['issues'])}. Elementos excluidos: {len(report['excluded'])}.</p></section></body></html>'''
