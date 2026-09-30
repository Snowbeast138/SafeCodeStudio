import argparse
import json
import sys

from .engine import Engine


def main() -> int:
    parser = argparse.ArgumentParser(description="SafeCode Python CST and dependency graph")
    parser.add_argument("root", help="Repository directory")
    parser.add_argument("--source-root", action="append", help="Import root relative to repository; repeatable")
    parser.add_argument("--cst", metavar="FILE", help="Export a file's complete CST")
    parser.add_argument("--affected", metavar="FILE", help="List transitive importers")
    args = parser.parse_args()
    if args.cst and args.affected:
        parser.error("--cst and --affected are mutually exclusive")
    try:
        engine = Engine(args.root, tuple(args.source_root or ["."]))
        if args.cst:
            result = engine.inspect_cst(args.cst)
        else:
            analysis = engine.analyze()
            result = {"affected": analysis.affected_by(args.affected)} if args.affected else analysis.to_dict()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
