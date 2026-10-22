"""Per-fight Havoc summary built from normalized events.

This is the data layer the ruleset checks run on: pressed casts, damage, buff
uptimes, real Metamorphosis windows, Fury at key casts, idle time and deaths.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from . import events as ev
from .events import Event, Fight

# Abilities the player presses (not procs or passive triggers).
TRACKED_CASTS = {
    198013: "Eye Beam", 258860: "Essence Break", 200166: "Metamorphosis",
    370965: "The Hunt", 198793: "Vengeful Retreat", 258920: "Immolation Aura",
    188499: "Blade Dance", 210152: "Death Sweep", 162794: "Chaos Strike",
    201427: "Annihilation", 232893: "Felblade", 195072: "Fel Rush",
    185123: "Throw Glaive", 442294: "Reaver's Glaive",
    452497: "Abyssal Gaze", 452487: "Consuming Fire",
}
# Throw Glaive (185123) also fires with 0 Fury cost at the same timestamp as
# Blade Dance, Death Sweep or Reaver's Glaive (talent-triggered throws). Only a
# 185123 cast with none of these within 50 ms counts as a button press.
AUTO_THROW_TRIGGERS = {188499, 210152, 442294, 444686}
THROW_GLAIVE = 185123
META_CAST, META_BUFF = 200166, 162264
DEMONSURGE = 452416

# Cooldowns whose longest idle gap is worth showing.
GAP_ABILITIES = ["Eye Beam", "Essence Break", "The Hunt", "Vengeful Retreat", "Metamorphosis"]

TRACKED_BUFFS = {
    162264: "Metamorphosis (incl. Demonic)", 258920: "Immolation Aura", 442695: "Thrill of the Fight",
    391215: "Initiative", 208628: "Exergy", 343312: "Furious Gaze",
}
FEL_SCARRED_MARKERS = {"Demonsurge", "Abyssal Gaze", "Consuming Fire", "Sigil of Doom"}
ALDRACHI_MARKERS = {"Reaver's Glaive", "Art of the Glaive", "Reaver's Mark"}


@dataclass
class MetaWindow:
    start: float
    end: float
    from_cast: bool          # True for a pressed Metamorphosis, False for Demonic (Eye Beam)


@dataclass
class FightData:
    """Everything the rules need about one player in one fight."""
    fight: Fight
    player: str
    hero_tree: str
    casts: dict[str, list[Event]]          # pressed casts by ability name
    cast_names: Counter                    # every cast by spell name, as Warcraft Logs counts them
    meta_windows: list[MetaWindow]
    damage_by_ability: Counter
    deaths: list[float]
    own_events: list[Event]

    @property
    def duration(self) -> float:
        return self.fight.duration

    @property
    def dead_intervals(self) -> list[tuple[float, float]]:
        """(death, back in action) for each death: until the next cast after a battle
        rez, or the end of the fight."""
        out = []
        for t in self.deaths:
            back = next((e.t for e in self.own_events
                         if e.type == ev.CAST and e.src == self.player and e.t > t), self.duration)
            out.append((t, back))
        return out

    @property
    def alive_seconds(self) -> float:
        return max(self.duration - sum(b - a for a, b in self.dead_intervals), 0.0)

    @property
    def minutes(self) -> float:
        """Minutes alive, so rates aren't diluted by time spent dead."""
        return self.alive_seconds / 60 if self.alive_seconds else 1.0

    def count(self, *names: str) -> int:
        return sum(len(self.casts.get(n, [])) for n in names)

    def per_min(self, *names: str) -> float:
        return self.count(*names) / self.minutes

    def name_per_min(self, name: str) -> float:
        """Casts per minute counted by spell name, comparable with WCL benchmarks."""
        return self.cast_names.get(name, 0) / self.minutes

    def times(self, name: str) -> list[float]:
        return [e.t for e in self.casts.get(name, [])]

    def uptime(self, spell_id: int) -> float:
        up_since, total = None, 0.0
        for e in self.own_events:
            if e.spell_id != spell_id or e.dst != self.player:
                continue
            if e.type == ev.AURA_APPLIED and up_since is None:
                up_since = e.t
            elif e.type == ev.AURA_REMOVED and up_since is not None:
                total += e.t - up_since
                up_since = None
        if up_since is not None:
            total += self.duration - up_since
        return total / self.duration if self.duration else 0.0

    def idle_gaps(self, threshold: float = 2.5, all_casts: bool = False) -> list[tuple[float, float]]:
        """(start, length) of each gap over `threshold` s between casts.

        all_casts=True also counts proc and talent-triggered casts, which is how
        the Warcraft Logs benchmark measures it. Rough either way: forced downtime
        (untargetable bosses, M+ travel) is not excluded yet.
        """
        if all_casts:
            times = sorted(e.t for e in self.own_events if e.type == ev.CAST and e.src == self.player)
        else:
            times = sorted(e.t for cs in self.casts.values() for e in cs)
        dead = self.dead_intervals
        return [(a, b - a) for a, b in zip(times, times[1:])
                if b - a > threshold and not any(a <= d < b for d, _ in dead)]

    def idle(self, threshold: float = 2.5, all_casts: bool = False) -> tuple[int, float]:
        """(number of gaps, seconds lost beyond a 1.5 s GCD)."""
        gaps = self.idle_gaps(threshold, all_casts)
        return len(gaps), sum(g - 1.5 for _, g in gaps)


def detect_hero_tree(events: list[Event], player: str) -> str:
    names = {e.spell_name for e in events if e.src == player}
    if names & FEL_SCARRED_MARKERS:
        return "Fel-Scarred"
    if names & ALDRACHI_MARKERS:
        return "Aldrachi Reaver"
    return "Unknown"


def _meta_windows(events: list[Event], player: str, duration: float) -> list[MetaWindow]:
    cast_times = [e.t for e in events if e.type == ev.CAST and e.src == player and e.spell_id == META_CAST]
    windows, start = [], None
    for e in events:
        if e.spell_id != META_BUFF or e.dst != player:
            continue
        if e.type == ev.AURA_APPLIED and start is None:
            start = e.t
        elif e.type == ev.AURA_REMOVED and start is not None:
            windows.append((start, e.t))
            start = None
    if start is not None:
        windows.append((start, duration))
    # A pressed Meta applies the buff within a GCD of the cast. Recasting Meta
    # inside a Demonic window turns that window into a real one too.
    return [MetaWindow(a, b, any(a - 0.5 <= t <= b for t in cast_times)) for a, b in windows]


def build(fight: Fight, player: str) -> FightData:
    own = [e for e in fight.events if e.src == player or e.dst == player]
    triggers = [e.t for e in own if e.type == ev.CAST and e.src == player and e.spell_id in AUTO_THROW_TRIGGERS]
    casts: dict[str, list[Event]] = defaultdict(list)
    damage: Counter = Counter()
    deaths = []
    cast_names: Counter = Counter()
    for e in own:
        if e.type == ev.CAST and e.src == player:
            cast_names[e.spell_name] += 1
            name = TRACKED_CASTS.get(e.spell_id)
            if e.spell_id == THROW_GLAIVE and any(abs(e.t - t) < 0.05 for t in triggers):
                name = None
            if name:
                casts[name].append(e)
        elif e.type == ev.DAMAGE and e.src == player:
            damage[e.spell_name] += e.amount
        elif e.type == ev.DIED and e.dst == player:
            deaths.append(e.t)
    return FightData(fight, player, detect_hero_tree(own, player), dict(casts), cast_names,
                     _meta_windows(own, player, fight.duration), damage, deaths, own)


@dataclass
class FightSummary:
    label: str
    duration: float
    success: bool | None
    hero_tree: str
    damage: float
    dps: float
    casts: Counter
    cpm: float
    damage_by_ability: list[tuple[str, float]]
    buff_uptime: dict[str, float]
    fury_at_meta: list[int]
    fury_at_essence_break: list[int]
    longest_gap: dict[str, float]
    idle_gaps: int
    idle_seconds: float
    deaths: list[float] = field(default_factory=list)


def summarize(data: FightData) -> FightSummary:
    casts = Counter({n: len(cs) for n, cs in data.casts.items()})
    longest_gap = {}
    for name in GAP_ABILITIES:
        times = [0.0] + data.times(name) + [data.duration]
        longest_gap[name] = max(b - a for a, b in zip(times, times[1:]))
    idle_gaps, idle_seconds = data.idle()
    damage = sum(data.damage_by_ability.values())
    return FightSummary(
        label=data.fight.label,
        duration=data.duration,
        success=data.fight.success,
        hero_tree=data.hero_tree,
        damage=damage,
        dps=damage / data.duration if data.duration else 0.0,
        casts=casts,
        cpm=sum(casts.values()) / data.minutes,
        damage_by_ability=data.damage_by_ability.most_common(8),
        buff_uptime={n: data.uptime(sid) for sid, n in TRACKED_BUFFS.items()},
        fury_at_meta=[e.fury for e in data.casts.get("Metamorphosis", []) if e.fury is not None],
        fury_at_essence_break=[e.fury for e in data.casts.get("Essence Break", []) if e.fury is not None],
        longest_gap=longest_gap,
        idle_gaps=idle_gaps,
        idle_seconds=idle_seconds,
        deaths=data.deaths,
    )
