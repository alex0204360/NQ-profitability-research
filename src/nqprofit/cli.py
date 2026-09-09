"""Explicit research stages; nothing opens holdout during preparation or rounds."""

import argparse
import json
from pathlib import Path

from . import research


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="stage", required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--upstream", type=Path, required=True)
    commands.add_parser("label")
    round_parser = commands.add_parser("round")
    round_parser.add_argument("number", type=int, choices=[1, 2])
    commands.add_parser("freeze")
    terminal = commands.add_parser("terminal")
    terminal.add_argument("--holdout", type=Path, required=True)
    commands.add_parser("finalize")
    args = parser.parse_args(argv)
    try:
        if args.stage == "prepare":
            result = research.prepare(args.root, args.upstream)
        elif args.stage == "label":
            research.training_context(args.root)
            result = research.read_json(args.root / "reports/labeling.json")
        elif args.stage == "round":
            result = research.run_round(args.root, args.number)
            result = {k: v for k, v in result.items() if k != "policies"}
        elif args.stage == "freeze":
            result = research.freeze(args.root)
            result = {k: v for k, v in result.items() if k != "artifacts"}
        elif args.stage == "terminal":
            result = research.terminal_validation(args.root, holdout_path=args.holdout)
            result = {k: v for k, v in result.items() if k not in ("policies", "baseline")}
        else:
            result = research.finalize(args.root)
    except Exception as exc:
        research.event(args.root, args.stage, "failed", detail=str(exc))
        raise
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
