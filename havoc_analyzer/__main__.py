"""Command line entry: python -m havoc_analyzer <WoWCombatLog.txt> [--player GUID] [--out report.md]"""
from __future__ import annotations

import argparse
import time

from . import benchmarks
from .combatlog import find_havoc_players, parse
from .report import analyze_fights, render_report


def main() -> None:
    ap = argparse.ArgumentParser(prog="havoc_analyzer")
    ap.add_argument("log")
    ap.add_argument("--player", help="player GUID (default: first Havoc DH found)")
    ap.add_argument("--benchmarks", default=benchmarks.DEFAULT_PATH, help="benchmarks.json from wcl/benchmarks.py")
    ap.add_argument("--out", help="write the Markdown report here")
    args = ap.parse_args()

    started = time.time()
    guid = args.player
    if guid is None:
        havocs = find_havoc_players(args.log)
        if not havocs:
            raise SystemExit("No Havoc Demon Hunter found in this log.")
        guid, name = next(iter(havocs.items()))
        print(f"Analyzing {name} ({guid}); Havoc players in log: {list(havocs.values())}")
    log = parse(args.log, guid)
    results = analyze_fights(log.fights, guid, benchmarks.load(args.benchmarks))

    report = render_report(log.player.name if log.player else guid, log.build, results)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Wrote {args.out} in {time.time() - started:.1f} s")
    else:
        print(report)


if __name__ == "__main__":
    main()
