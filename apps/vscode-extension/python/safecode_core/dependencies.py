"""Extract static references from CST nodes, never from source regexes."""
def extract_dependencies(report):
    nodes = report['nodes']
    source = report['source'].encode('utf-8')
    def text(n):
        return source[n['start_byte']:n['end_byte']].decode('utf-8') if n else ''
    def children(n):
        return [nodes[i] for i in n['children']] if n else []
    def field(n, name):
        return next((c for c in children(n) if c['field'] == name), None)
    def literal(n):
        value = text(n)
        return value[1:-1] if n and n['type'] == 'string' and len(value) >= 2 and '\\' not in value else None
    def emit(n, kind, specifier, **extra):
        evidence = {k: n[k] for k in ('id', 'type', 'start_byte', 'end_byte', 'start', 'end', 'has_error')}
        return dict(kind=kind, specifier=specifier, evidence={**evidence, 'text': text(n)}, **extra)
    result = []
    for n in nodes:
        if report['language'] == 'python':
            if n['type'] in ('import_statement', 'import_from_statement'):
                module = text(field(n, 'module_name'))
                for child in children(n):
                    if child['field'] == 'name' or child['type'] == 'wildcard_import':
                        name = text(field(child, 'name')) if child['type'] == 'aliased_import' else text(child)
                        result.append(emit(n, 'python_from' if module else 'python_import', module or name,
                                           member=name if module else None))
            elif n['type'] == 'call' and text(field(n, 'function')) in ('__import__', 'importlib.import_module'):
                result.append(emit(n, 'python_dynamic', None))
        else:
            if n['type'] in ('import_statement', 'export_statement'):
                target = field(n, 'source')
                if target is None:
                    clause = next((c for c in children(n) if c['type'] == 'import_require_clause'), None)
                    target = field(clause, 'source')
                if target:
                    result.append(emit(n, 'reexport' if n['type'] == 'export_statement' else 'import', literal(target),
                                       type_only=any(c['type'] == 'type' for c in children(n))))
            elif n['type'] == 'call_expression':
                function = field(n, 'function')
                name = text(function)
                if name == 'import' or (name == 'require' and function['type'] == 'identifier'):
                    args = [c for c in children(field(n, 'arguments')) if c['named'] and not c['extra']]
                    result.append(emit(n, 'dynamic_import' if name == 'import' else 'require', literal(args[0]) if args else None,
                                       binding_verified=name == 'import'))
    return result
