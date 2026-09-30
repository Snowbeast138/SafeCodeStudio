"""One-shot CLI and sequential JSON Lines request loop for file CSTs."""
import argparse
import json
import sys

from .cst import CSTError, CSTService, tree_text


def serve(service, input_stream, output_stream):
    # Each request is a path, not source code; no network service is exposed.
    while True:
        line = input_stream.readline(65_537)
        if not line:
            return
        request_id = None
        try:
            if len(line) > 65_536:
                while line and not line.endswith('\n'):
                    line = input_stream.readline(65_537)
                raise CSTError('request_too_large', 'Maximum request length: 65536 characters')
            request = json.loads(line)
            if not isinstance(request, dict):
                raise CSTError('invalid_request', 'Expected a JSON object')
            request_id = request.get('id')
            if not isinstance(request_id, (str, int, type(None))) or isinstance(request_id, bool):
                request_id = None
                raise CSTError('invalid_request', 'id must be a string, integer or null')
            if not isinstance(request.get('path'), str) or not request['path']:
                raise CSTError('invalid_request', 'path must be a nonempty string')
            language = request.get('language')
            if language is not None and not isinstance(language, str):
                raise CSTError('invalid_request', 'language must be a string')
            response = {'id': request_id, 'result': service.parse_file(request['path'], language)}
        except (ValueError, OSError) as exc:
            response = {'id': request_id, 'error': {'code': getattr(exc, 'code', 'invalid_request'), 'message': str(exc)}}
        output_stream.write(json.dumps(response, ensure_ascii=False) + '\n')
        output_stream.flush()


def main():
    parser = argparse.ArgumentParser(description='Parse Python, JavaScript or TypeScript files into a complete CST')
    parser.add_argument('path', nargs='?', help='Absolute or relative path to source file')
    parser.add_argument('--language', choices=['python', 'javascript', 'typescript', 'tsx'])
    parser.add_argument('--format', choices=['json', 'tree'], default='json')
    parser.add_argument('--stdio', action='store_true', help='Wait for JSON Lines requests containing path')
    args = parser.parse_args()
    if args.stdio:
        if args.path or args.language or args.format != 'json':
            parser.error('--stdio cannot be combined with path, --language or --format tree')
        serve(CSTService(), sys.stdin, sys.stdout)
        return 0
    if not args.path:
        parser.error('Provide a file path or --stdio')
    try:
        report = CSTService().parse_file(args.path, args.language)
        print(tree_text(report) if args.format == 'tree' else json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'error': {'code': getattr(exc, 'code', 'read_error'), 'message': str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
