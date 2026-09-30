"""Export a directory dependency snapshot as JSON or offline HTML."""
import argparse
import json
from pathlib import Path
import sys
from .directory_graph import DirectoryGraphEngine
from .graph_view import render_graph

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--format', choices=('json', 'html'), default='json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--subgraph', default='.')
    parser.add_argument('--include-cst', action='store_true')
    parser.add_argument('--python-root', action='append')
    parser.add_argument('--alias', action='append', default=[], metavar='PREFIX=PATH')
    parser.add_argument('--max-files', type=int, default=2000)
    args = parser.parse_args()
    if args.format == 'html' and args.include_cst:
        parser.error('--include-cst requires JSON')
    try:
        aliases = {}
        for entry in args.alias:
            if '=' not in entry: raise ValueError('Aliases require PREFIX=PATH')
            key, value = entry.split('=', 1)
            if key in aliases: raise ValueError('Duplicate alias')
            aliases[key] = value
        engine = DirectoryGraphEngine(args.root, aliases=aliases, python_roots=args.python_root or ('.',),
                                      include_cst=args.include_cst, max_files=args.max_files,
                                      excluded_paths=[args.output] if args.output else [])
        selected = (engine.root / args.subgraph).resolve()
        if not selected.is_relative_to(engine.root): raise ValueError('Subgraph outside root')
        report = engine.analyze().to_dict(selected.relative_to(engine.root).as_posix())
        content = render_graph(report) if args.format == 'html' else json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            args.output.write_text(content, encoding='utf-8')
            print(f'Saved {args.output.resolve()}', file=sys.stderr)
        else: print(content)
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(json.dumps(dict(error=str(exc))), file=sys.stderr)
        return 2

if __name__ == '__main__':
    raise SystemExit(main())
