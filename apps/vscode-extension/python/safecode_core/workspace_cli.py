"""Newline-delimited JSON-RPC 2.0 process for a persistent SafeCode workspace."""
import argparse
import json
import sys

from .workspace import WorkspaceEngine
from .graph_view import render_graph


def _error(identifier, code, message):
    return dict(jsonrpc='2.0', id=identifier, error=dict(code=code, message=message))


def serve(engine, input_stream=None, output_stream=None):
    source = input_stream or sys.stdin
    target = output_stream or sys.stdout
    for line in source:
        identifier = None
        try:
            if len(line) > 1_000_000:
                response = _error(None, -32600, 'Request exceeds one megabyte')
            else:
                request = json.loads(line)
                if not isinstance(request, dict):
                    response = _error(None, -32600, 'Request must be an object')
                else:
                    identifier = request.get('id')
                    if request.get('jsonrpc') != '2.0' or isinstance(identifier, bool) or not isinstance(identifier, (str, int)):
                        response = _error(None, -32600, 'Expected JSON-RPC 2.0 request with string or integer id')
                    else:
                        method = request.get('method')
                        params = request.get('params', {})
                        if not isinstance(params, dict):
                            response = _error(identifier, -32602, 'params must be an object')
                        elif method == 'analyze':
                            try:
                                result = engine.update(identifier, params['version'])
                                response = dict(jsonrpc='2.0', id=identifier, result=result)
                            except (KeyError, ValueError, TypeError) as exc:
                                response = _error(identifier, -32602, str(exc))
                        elif method == 'graph':
                            try:
                                result = engine.graph_snapshot(params.get('directory', '.'))
                                response = dict(jsonrpc='2.0', id=identifier, result=result)
                            except (ValueError, TypeError) as exc:
                                response = _error(identifier, -32602, str(exc))
                        elif method == 'graphHtml':
                            try:
                                result = render_graph(engine.graph_snapshot(params.get('directory', '.')))
                                response = dict(jsonrpc='2.0', id=identifier, result=result)
                            except (ValueError, TypeError) as exc:
                                response = _error(identifier, -32602, str(exc))
                        elif method == 'shutdown':
                            response = dict(jsonrpc='2.0', id=identifier, result=dict(stopped=True))
                            target.write(json.dumps(response, ensure_ascii=False) + '\n')
                            target.flush()
                            break
                        else:
                            response = _error(identifier, -32601, 'Unknown method')
        except json.JSONDecodeError:
            response = _error(None, -32700, 'Invalid JSON')
        except (OSError, RuntimeError, ValueError) as exc:
            response = _error(identifier, -32000, str(exc))
        target.write(json.dumps(response, ensure_ascii=False) + '\n')
        target.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Persistent SafeCode workspace process (JSON-RPC lines on stdin/stdout)')
    parser.add_argument('root')
    parser.add_argument('--baseline')
    parser.add_argument('--git-baseline-ref')
    parser.add_argument('--policy')
    args = parser.parse_args(argv)
    try:
        engine = WorkspaceEngine(args.root, baseline=args.baseline, policy=args.policy,
                                 git_baseline_ref=args.git_baseline_ref)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    serve(engine)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
