"""Reproduce the frozen symmetric-pulse exploratory replay."""
import argparse
import json
from pathlib import Path

from .replay import FIELDS, evaluate, verify_archived, write_outputs
from .sources import load_sources
from .symmetric import SymmetricHead


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="verified, exposed source directory")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    discovery, external, provenance = load_sources(market_dir=args.source)
    frames = {panel: group[FIELDS] for panel, group in discovery.groupby("panel", sort=False)}
    frames["external"] = external["MNQ.csv"][FIELDS]
    rows = evaluate(frames, head_factory=SymmetricHead)
    verify_archived(rows["trades"])
    write_outputs(rows, args.output)
    (args.output / "source.json").write_text(json.dumps(provenance, indent=2) + "\n")


if __name__ == "__main__":
    main()
