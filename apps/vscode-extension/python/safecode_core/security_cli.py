"""Command line entry point for deterministic SafeCode analysis."""
import argparse
import json
from pathlib import Path
from .security import analyze, render_html


def main(argv=None):
    parser = argparse.ArgumentParser(description='Analyze CST patterns and architecture changes')
    parser.add_argument('root', help='Project directory to analyze')
    parser.add_argument('--baseline', help='Previous project directory for architecture rules')
    parser.add_argument('--policy', help='JSON policy with forbidden {from,to} path globs')
    parser.add_argument('--format', choices=('html', 'json'), default='html')
    parser.add_argument('--output', help='Output report path (defaults to safecode-security.html/json in current directory)')
    args = parser.parse_args(argv)
    if args.policy and not args.baseline:
        parser.error('--policy requires --baseline')
    report = analyze(args.root, args.baseline, args.policy)
    output = Path(args.output or f'safecode-security.{args.format}').expanduser().resolve()
    content = render_html(report) if args.format == 'html' else json.dumps(report, ensure_ascii=False, indent=2)
    output.write_text(content + '\n', encoding='utf-8')
    print(f'{len(report["findings"])} findings · {report["status"]} · {output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
