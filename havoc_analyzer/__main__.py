"""Command line entry: python -m havoc_analyzer <WoWCombatLog.txt> [--player GUID] [--out report.md]"""
from __future__ import annotations

import argparse
import time
from collections import Counter

from . import benchmarks
from .combatlog import find_havoc_players, parse
from .events import Fight
from .rules import FLAG, WARN, Finding, evaluate, fmt
from .summary import FightSummary, build, summarize

STATUS_ICON = {"flag": "🔴", "warn": "🟡", "ok": "🟢", "info": "⚪"}


def render_fight(s: FightSummary, findings: list[Finding], bench_note: str) -> str:
    result = {True: "Kill", False: "Wipe", None: "?"}[s.success]
    lines = [
        f"## {s.label}: {result}, {fmt(s.duration)}",
        "",
        f"Hero tree: **{s.hero_tree}** · DPS: **{s.dps:,.0f}** · Pressed abilities per minute: **{s.cpm:.1f}**"
        + (f" · Died at {', '.join(fmt(d) for d in s.deaths)}" if s.deaths else ""),
        "",
        f"### Findings ({bench_note})",
        "",
        "| | Rule | Result | Look at |",
        "|---|---|---|---|",
    ]
    for f in findings:
        when = ", ".join(fmt(t) for t in f.times[:6]) + (" …" if len(f.times) > 6 else "")
        lines.append(f"| {STATUS_ICON[f.status]} | {f.rule} {f.title} ({f.severity}) | {f.detail} | {when} |")
    lines += ["", "<details><summary>Casts, buffs and damage</summary>", "",
              "| Ability | Casts | Longest gap |", "|---|---|---|"]
    for name, count in s.casts.most_common():
        gap = s.longest_gap.get(name)
        lines.append(f"| {name} | {count} | {fmt(gap) if gap is not None else ''} |")
    lines += ["", "| Buff | Uptime |", "|---|---|"]
    lines += [f"| {n} | {u:.0%} |" for n, u in s.buff_uptime.items()]
    lines += ["", "Top damage: " + ", ".join(
        f"{n} {d / max(s.damage, 1):.0%}" for n, d in s.damage_by_ability), "", "</details>", ""]
    return "\n".join(lines)


def render_overview(results: list[tuple[str, list[Finding]]]) -> str:
    """Rules that came up flag/warn across several fights, most frequent first."""
    flagged, warned = Counter(), Counter()
    titles = {}
    for _, findings in results:
        for f in findings:
            titles[f.rule] = f"{f.rule} {f.title}"
            if f.status == FLAG:
                flagged[f.rule] += 1
            elif f.status == WARN:
                warned[f.rule] += 1
    rules = sorted(set(flagged) | set(warned), key=lambda r: (-flagged[r], -warned[r]))
    if not rules:
        return "## Overview\n\nNo rule was flagged in any fight.\n"
    lines = ["## Overview", "", f"Across {len(results)} fights:", "",
             "| Rule | 🔴 Flagged | 🟡 Warned |", "|---|---|---|"]
    lines += [f"| {titles[r]} | {flagged[r]} | {warned[r]} |" for r in rules]
    return "\n".join(lines) + "\n"


def analyze_fights(fights: list[Fight], guid: str, table) -> list[tuple[FightSummary, list[Finding], str]]:
    out = []
    for fight in fights:
        for f in [fight, *fight.children]:
            data = build(f, guid)
            bench = benchmarks.lookup(table, f.content, data.hero_tree)
            note = (f"vs top {bench.logs} {data.hero_tree} {'Mythic+' if f.content == 'mplus' else 'raid'} logs"
                    if bench else "no top-player benchmark for this hero tree")
            out.append((summarize(data), evaluate(data, bench), note))
    return out


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

    parts = [f"# Havoc report: {log.player.name if log.player else guid}", "",
             f"Game build {log.build}. {len(results)} fights. "
             "🔴 likely DPS lost · 🟡 worth a look · 🟢 fine · ⚪ measured, no benchmark.", "",
             render_overview([(s.label, f) for s, f, _ in results])]
    parts += [render_fight(s, f, note) for s, f, note in results]
    report = "\n".join(parts)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Wrote {args.out} in {time.time() - started:.1f} s")
    else:
        print(report)


if __name__ == "__main__":
    main()
