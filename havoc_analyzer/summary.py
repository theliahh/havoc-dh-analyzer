"""Per-fight Havoc summary built from parsed combat log events.

This is the raw data layer the ruleset checks (step 3) will run on: casts,
damage, buff uptimes, Fury at key casts, cooldown gaps and deaths.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .combatlog import SUFFIX_START, Fight

DAMAGE_EVENTS = {"SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "RANGE_DAMAGE"}
SWING_AMOUNT = SUFFIX_START - 3   # swings have no 3-field spell prefix

# Abilities the player presses (not procs or passive triggers).
TRACKED_CASTS = {
    198013: "Eye Beam", 258860: "Essence Break", 200166: "Metamorphosis",
    370965: "The Hunt", 198793: "Vengeful Retreat", 258920: "Immolation Aura",
    188499: "Blade Dance", 210152: "Death Sweep", 162794: "Chaos Strike",
    201427: "Annihilation", 232893: "Felblade", 195072: "Fel Rush",
    185123: "Throw Glaive", 442294: "Reaver's Glaive",
}
# Throw Glaive (185123) also fires with 0 Fury cost at the same timestamp as
# Blade Dance, Death Sweep or Reaver's Glaive (talent-triggered throws). Only a
# 185123 cast with none of these within 50 ms counts as a button press.
AUTO_THROW_TRIGGERS = {188499, 210152, 442294, 444686}
THROW_GLAIVE = 185123

# Cooldowns whose longest idle gap is worth showing.
GAP_ABILITIES = ["Eye Beam", "Essence Break", "The Hunt", "Vengeful Retreat", "Metamorphosis"]

TRACKED_BUFFS = {
    162264: "Metamorphosis", 258920: "Immolation Aura", 442695: "Thrill of the Fight",
    391215: "Initiative", 208628: "Exergy", 343312: "Furious Gaze",
}
FEL_SCARRED_MARKERS = {"Demonsurge", "Abyssal Gaze", "Consuming Fire", "Sigil of Doom"}
ALDRACHI_MARKERS = {"Reaver's Glaive", "Art of the Glaive", "Reaver's Mark"}


@dataclass
class FightSummary:
    label: str
    duration: float
    success: bool | None
    hero_tree: str
    damage: int
    dps: float
    casts: Counter
    cpm: float
    damage_by_ability: list[tuple[str, int]]
    buff_uptime: dict[str, float]
    fury_at_meta: list[int]
    fury_at_essence_break: list[int]
    longest_gap: dict[str, float]
    idle_gaps: int
    idle_seconds: float
    deaths: list[float] = field(default_factory=list)


def detect_hero_tree(fight: Fight, player_guid: str) -> str:
    names = {e.spell_name for e in fight.events
             if e.src == player_guid and len(e.fields) > 10}
    if names & FEL_SCARRED_MARKERS:
        return "Fel-Scarred"
    if names & ALDRACHI_MARKERS:
        return "Aldrachi Reaver"
    return "Unknown"


def _uptime(fight: Fight, player_guid: str, spell_id: int) -> float:
    up_since, total = None, 0.0
    for e in fight.events:
        if e.dst != player_guid or not e.type.startswith("SPELL_AURA") or e.spell_id != spell_id:
            continue
        if e.type == "SPELL_AURA_APPLIED" and up_since is None:
            up_since = e.t
        elif e.type == "SPELL_AURA_REMOVED" and up_since is not None:
            total += e.t - up_since
            up_since = None
    if up_since is not None:
        total += fight.duration - up_since
    return total / fight.duration if fight.duration else 0.0


def summarize(fight: Fight, player_guid: str) -> FightSummary:
    casts: Counter = Counter()
    cast_times: dict[str, list[float]] = defaultdict(list)
    gcd_times: list[float] = []
    dmg_by_ability: Counter = Counter()
    fury_meta, fury_eb, deaths = [], [], []
    trigger_times = [e.t for e in fight.events if e.type == "SPELL_CAST_SUCCESS"
                     and e.src == player_guid and e.spell_id in AUTO_THROW_TRIGGERS]

    for e in fight.events:
        if e.type == "SPELL_CAST_SUCCESS" and e.src == player_guid:
            name = TRACKED_CASTS.get(e.spell_id)
            if e.spell_id == THROW_GLAIVE and any(abs(e.t - t) < 0.05 for t in trigger_times):
                name = None
            if name:
                casts[name] += 1
                cast_times[name].append(e.t)
                gcd_times.append(e.t)
                if name == "Metamorphosis":
                    fury_meta.append(e.fury())
                elif name == "Essence Break":
                    fury_eb.append(e.fury())
        elif e.src == player_guid and e.type in DAMAGE_EVENTS:
            dmg_by_ability[e.spell_name] += int(e.fields[SUFFIX_START])
        elif e.src == player_guid and e.type == "SWING_DAMAGE":
            dmg_by_ability["Melee"] += int(e.fields[SWING_AMOUNT])
        elif e.type == "UNIT_DIED" and e.dst == player_guid:
            deaths.append(e.t)

    # Idle time: gaps over 2.5 s between pressed abilities (approximate; forced
    # downtime is not excluded yet).
    idle_gaps, idle_seconds = 0, 0.0
    for a, b in zip(gcd_times, gcd_times[1:]):
        if b - a > 2.5:
            idle_gaps += 1
            idle_seconds += b - a - 1.0

    longest_gap = {}
    for name in GAP_ABILITIES:
        times = [0.0] + cast_times.get(name, []) + [fight.duration]
        longest_gap[name] = max(b - a for a, b in zip(times, times[1:]))

    damage = sum(dmg_by_ability.values())
    minutes = fight.duration / 60 if fight.duration else 1
    return FightSummary(
        label=fight.label,
        duration=fight.duration,
        success=fight.success,
        hero_tree=detect_hero_tree(fight, player_guid),
        damage=damage,
        dps=damage / fight.duration if fight.duration else 0.0,
        casts=casts,
        cpm=sum(casts.values()) / minutes,
        damage_by_ability=dmg_by_ability.most_common(8),
        buff_uptime={n: _uptime(fight, player_guid, sid) for sid, n in TRACKED_BUFFS.items()},
        fury_at_meta=[f for f in fury_meta if f is not None],
        fury_at_essence_break=[f for f in fury_eb if f is not None],
        longest_gap=longest_gap,
        idle_gaps=idle_gaps,
        idle_seconds=idle_seconds,
        deaths=deaths,
    )
