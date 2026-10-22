"""Command line entry: python -m havoc_analyzer <WoWCombatLog.txt> [--player GUID] [--out report.md]"""
from __future__ import annotations

import argparse
import time

from .combatlog import find_havoc_players, parse
from .summary import FightSummary, summarize


def fmt_time(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def render(s: FightSummary) -> str:
    result = {True: "Kill", False: "Wipe", None: "?"}[s.success]
    lines = [
        f"## {s.label} - {result}, {fmt_time(s.duration)}",
        "",
        f"Hero tree: **{s.hero_tree}** · DPS: **{s.dps:,.0f}** · Pressed abilities per minute: **{s.cpm:.1f}**"
        + (f" · Died at {', '.join(fmt_time(d) for d in s.deaths)}" if s.deaths else ""),
        "",
        "| Ability | Casts | Longest gap |",
        "|---|---|---|",
    ]
    for name, count in s.casts.most_common():
        gap = s.longest_gap.get(name)
        lines.append(f"| {name} | {count} | {fmt_time(gap) if gap is not None else ''} |")
    lines += ["", "| Buff | Uptime |", "|---|---|"]
    lines += [f"| {n} | {u:.0%} |" for n, u in s.buff_uptime.items()]
    lines += ["", "Top damage: " + ", ".join(
        f"{n} {d / max(s.damage, 1):.0%}" for n, d in s.damage_by_ability)]
    if s.fury_at_meta:
        lines.append(f"Fury at Metamorphosis casts: {s.fury_at_meta}")
    if s.fury_at_essence_break:
        avg = sum(s.fury_at_essence_break) / len(s.fury_at_essence_break)
        lines.append(f"Average Fury at Essence Break: {avg:.0f}")
    lines.append(f"Idle gaps over 2.5 s: {s.idle_gaps} ({s.idle_seconds:.0f} s, not yet adjusted for forced downtime)")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(prog="havoc_analyzer")
    ap.add_argument("log")
    ap.add_argument("--player", help="player GUID (default: first Havoc DH found)")
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

    parts = [f"# Havoc report: {log.player.name if log.player else guid}", "",
             f"Game build {log.build}. {len(log.fights)} fights.", ""]
    for fight in log.fights:
        parts.append(render(summarize(fight, guid)))
        for child in fight.children:
            parts.append(render(summarize(child, guid)))
    report = "\n".join(parts)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(report)
        print(f"Wrote {args.out} in {time.time() - started:.1f} s")
    else:
        print(report)


if __name__ == "__main__":
    main()
