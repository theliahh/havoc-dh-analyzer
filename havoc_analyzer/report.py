"""Analysis run over parsed fights, and the Markdown report."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from . import benchmarks
from .events import Fight
from .rules import FLAG, WARN, Finding, evaluate, fmt
from .summary import FightData, FightSummary, build, summarize

STATUS_ICON = {"flag": "🔴", "warn": "🟡", "ok": "🟢", "info": "⚪"}


@dataclass
class FightResult:
    fight: Fight
    data: FightData
    summary: FightSummary
    findings: list[Finding]
    bench_note: str


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


def analyze_fights(fights: list[Fight], guid: str, table) -> list[FightResult]:
    """Run every rule on each fight, and on each boss pull inside a key."""
    out = []
    for fight in fights:
        for f in [fight, *fight.children]:
            data = build(f, guid)
            bench = benchmarks.lookup(table, f.content, data.hero_tree)
            note = (f"vs top {bench.logs} {data.hero_tree} {'Mythic+' if f.content == 'mplus' else 'raid'} logs"
                    if bench else "no top-player benchmark for this hero tree")
            out.append(FightResult(f, data, summarize(data), evaluate(data, bench), note))
    return out


def render_report(player_name: str, build_version: str | None, results: list[FightResult]) -> str:
    parts = [f"# Havoc report: {player_name}", "",
             f"Game build {build_version}. {len(results)} fights. "
             "🔴 likely DPS lost · 🟡 worth a look · 🟢 fine · ⚪ measured, no benchmark.", "",
             render_overview([(r.summary.label, r.findings) for r in results])]
    parts += [render_fight(r.summary, r.findings, r.bench_note) for r in results]
    return "\n".join(parts)
