"""Ruleset checks (docs/ruleset.md) run on one player's FightData.

Each check returns a Finding with a status:
  ok   - in line with top players or the rule
  warn - somewhat below, worth a look
  flag - clearly below, likely DPS lost
  info - measured, but no benchmark or rule threshold to judge it against
Cast-rate rules compare against top-player medians for the same content and
hero tree, because exact cooldowns shift with haste, talents and resets.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .benchmarks import Benchmark
from .summary import FightData

OK, WARN, FLAG, INFO = "ok", "warn", "flag", "info"
STATUS_ORDER = {FLAG: 0, WARN: 1, INFO: 2, OK: 3}
SEVERITY_ORDER = {"High": 0, "Med": 1, "Low": 2}

# Ratio of your rate to the top-player median that counts as ok / warn.
OK_RATIO, WARN_RATIO = 0.9, 0.75
LOW_FURY_META, LOW_FURY_EB = 90, 80
EYE_BEAM_BEFORE_META_S = 10.0
OPENER_WINDOW_S = 20.0
PREPOT_S = 10.0          # a potion this long before Metamorphosis still covers the window

AR, FS, BOTH = "Aldrachi Reaver", "Fel-Scarred", None

# Openers from Method (12.1.5), pull-time casts only.
OPENERS = {
    AR: ["The Hunt", "Reaver's Glaive", "Eye Beam", "Essence Break", "Death Sweep", "Annihilation",
         "Death Sweep", "Vengeful Retreat", "Metamorphosis", "Death Sweep", "Eye Beam"],
    FS: ["Eye Beam", "The Hunt", "Essence Break", "Annihilation", "Death Sweep", "Death Sweep",
         "Vengeful Retreat", "Metamorphosis", "Death Sweep", "Annihilation", "Consuming Fire", "Abyssal Gaze"],
}


@dataclass
class Finding:
    rule: str
    title: str
    severity: str
    status: str
    detail: str
    times: list[float] = field(default_factory=list)   # moments to look at, seconds into the fight


@dataclass
class Rule:
    id: str
    title: str
    severity: str
    tree: str | None
    check: Callable[[FightData, Benchmark | None], tuple[str, str, list[float]] | None] | None
    explain: str = ""   # plain-language version for the Rules tab


def fmt(t: float) -> str:
    return f"{int(t // 60)}:{int(t % 60):02d}"


def _rate_check(names: list[str], label: str):
    """Compare pressed casts per minute with the top-player median.

    Uses the pressed-cast benchmark (same counting as summary.build); falls back
    to counting by spell name for a benchmarks file that predates it.
    """
    def check(d: FightData, b: Benchmark | None):
        if b and b.pressed_cpm:
            yours = d.per_min(*names)
            top = sum(b.pressed_cpm.get(n, 0.0) for n in names)
        else:
            yours = sum(d.name_per_min(n) for n in names)
            top = sum(b.cpm.get(n, 0.0) for n in names) if b else 0.0
        if not top:
            return INFO, f"{label}: {yours:.2f}/min (no top-player benchmark).", []
        ratio = yours / top
        status = OK if ratio >= OK_RATIO else WARN if ratio >= WARN_RATIO else FLAG
        return status, f"{label}: {yours:.2f}/min vs {top:.2f}/min for top players ({ratio:.0%}).", []
    return check


def _meta_after_eye_beam(d: FightData, b):
    """S2: Eye Beam should go out right before Metamorphosis (Chaotic Transformation resets it)."""
    metas, beams = d.times("Metamorphosis"), d.times("Eye Beam")
    if not metas:
        return None
    bad = [m for m in metas if not any(0 <= m - t <= EYE_BEAM_BEFORE_META_S for t in beams)]
    if not bad:
        return OK, f"All {len(metas)} Metamorphosis casts came within {EYE_BEAM_BEFORE_META_S:.0f} s after an Eye Beam.", []
    return (FLAG if len(bad) * 2 >= len(metas) else WARN,
            f"{len(bad)} of {len(metas)} Metamorphosis casts had no Eye Beam in the "
            f"{EYE_BEAM_BEFORE_META_S:.0f} s before, so Eye Beam was likely ready or nearly ready and the reset was wasted.",
            bad)


def _manual_throws(d: FightData, b):
    """S7: pressed Throw Glaive (talent-triggered throws already excluded)."""
    times = d.times("Throw Glaive")
    rate = len(times) / d.minutes
    if not times:
        return OK, "No manual Throw Glaive casts.", []
    status = WARN if rate >= 0.5 else OK
    return status, (f"{len(times)} manual Throw Glaive casts ({rate:.1f}/min). Fine when out of range, "
                    "otherwise a wasted GCD."), times


def _fury_at(name: str, low: int, bench_attr: str):
    """S9: enough Fury going into Metamorphosis or Essence Break."""
    def check(d: FightData, b: Benchmark | None):
        casts = [e for e in d.casts.get(name, []) if e.fury is not None]
        if not casts:
            return None
        lows = [e for e in casts if e.fury < low]
        top = getattr(b, bench_attr) if b else None
        avg = sum(e.fury for e in casts) / len(casts)
        bench = f" (top players: {top:.0f})" if top else ""
        if not lows:
            return OK, f"Average {avg:.0f} Fury at {name}{bench}; none under {low}.", []
        status = FLAG if len(lows) * 2 >= len(casts) else WARN
        return (status, f"{len(lows)} of {len(casts)} {name} casts started under {low} Fury "
                        f"(lowest {min(e.fury for e in lows)}). Average {avg:.0f}{bench}.",
                [e.t for e in lows])
    return check


def _idle(d: FightData, b: Benchmark | None):
    """S11: dead time between pressed abilities."""
    # Measure the same way as the benchmark: pressed casts when it has that number.
    pressed = bool(b and b.idle_pressed_per_min is not None)
    gap_list = d.idle_gaps(all_casts=not pressed)
    gaps, seconds = len(gap_list), sum(g - 1.5 for _, g in gap_list)
    longest = [a for a, _ in sorted(gap_list, key=lambda x: -x[1])[:6]]
    yours = seconds / d.minutes
    top = (b.idle_pressed_per_min if pressed else b.idle_per_min) if b else None
    text = f"{seconds:.0f} s idle over {gaps} gaps ({yours:.1f} s/min)"
    if top is None:
        return INFO, text + ". Forced downtime is not excluded yet.", sorted(longest)
    status = OK if yours <= top + 1 else WARN if yours <= top + 3 else FLAG
    return (status, text + f" vs {top:.1f} s/min for top players. Forced downtime is not excluded yet.",
            sorted(longest) if status != OK else [])


def _potion_with_meta(d: FightData, b):
    """S13: potion in the opener, or inside or just before a real Metamorphosis (pre-potting)."""
    potions = [e.t for e in d.own_events if e.type == "cast" and e.src == d.player and "Potion of" in e.spell_name
               and "Health" not in e.spell_name]
    if not potions:
        return INFO, "No damage potion used.", []
    real = [w for w in d.meta_windows if w.from_cast]
    bad = [t for t in potions if t > OPENER_WINDOW_S and not any(w.start - PREPOT_S <= t <= w.end for w in real)]
    if not bad:
        return OK, f"{len(potions)} damage potion(s), all in the opener or a Metamorphosis.", []
    return WARN, f"{len(bad)} damage potion(s) used outside the opener and Metamorphosis.", bad


def _thrill_per_glaive(d: FightData, b):
    """AR2: each Reaver's Glaive should be followed by both empowered spenders (Thrill of the Fight)."""
    glaives = d.times("Reaver's Glaive")
    if not glaives:
        return None
    thrills = [e.t for e in d.own_events if e.spell_id == 442695 and e.dst == d.player
               and e.type in ("aura_applied", "aura_refresh")]
    missed = []
    for i, g in enumerate(glaives):
        nxt = glaives[i + 1] if i + 1 < len(glaives) else d.duration
        if not any(g < t <= nxt for t in thrills):
            missed.append(g)
    share = 1 - len(missed) / len(glaives)
    status = OK if share >= 0.9 else WARN if share >= 0.75 else FLAG
    return (status, f"{share:.0%} of Reaver's Glaive casts led to Thrill of the Fight before the next Glaive "
                    f"({len(missed)} missed).", missed)


def _thrill_uptime(d: FightData, b):
    """AR4: Thrill of the Fight uptime, against top players when the benchmark has it."""
    up = d.uptime(442695)
    top = b.thrill_uptime if b and b.thrill_uptime is not None else 0.8
    status = OK if up >= top - 0.05 else WARN if up >= top - 0.15 else FLAG
    source = "top players" if b and b.thrill_uptime is not None else "the default target"
    return status, f"Thrill of the Fight up {up:.0%} of the fight vs {top:.0%} for {source}.", []


def _fs_meta_spenders(d: FightData, b):
    """FS3: Abyssal Gaze and Consuming Fire in every real Metamorphosis."""
    real = [w for w in d.meta_windows if w.from_cast]
    if not real:
        return None
    gaze, fire = d.times("Abyssal Gaze"), d.times("Consuming Fire")
    missed = [w.start for w in real
              if not any(w.start <= t <= w.end for t in gaze) or not any(w.start <= t <= w.end for t in fire)]
    if not missed:
        return OK, f"Abyssal Gaze and Consuming Fire used in all {len(real)} Metamorphosis windows.", []
    return FLAG, f"{len(missed)} of {len(real)} Metamorphosis windows were missing Abyssal Gaze or Consuming Fire.", missed


def _fs_demonsurge(d: FightData, b):
    """FS2: Demonsurge triggers per real Metamorphosis window (grouped by timestamp)."""
    real = [w for w in d.meta_windows if w.from_cast]
    if not real:
        return None
    surge_times = sorted({round(e.t, 3) for e in d.own_events
                          if e.type == "damage" and e.src == d.player and e.spell_name == "Demonsurge"})
    counts = [sum(w.start <= t <= w.end for t in surge_times) for w in real]
    # Top Fel-Scarred logs show 7 to 12 surges in a full Metamorphosis window.
    low = [w.start for w, c in zip(real, counts) if c < 7]
    status = OK if not low else WARN if len(low) * 2 < len(real) else FLAG
    return status, f"Demonsurge per Metamorphosis window: {counts} (top players: 7 to 12).", low


def _opener(d: FightData, b):
    """AR5 / FS4: first casts against Method's opener (longest common subsequence)."""
    template = OPENERS.get(d.hero_tree)
    if not template or d.fight.content != "raid":
        return None
    seq = [name for _, name in sorted((e.t, name) for name, cs in d.casts.items()
                                      for e in cs if e.t <= OPENER_WINDOW_S)]
    m, n = len(template), len(seq)
    lcs = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            lcs[i + 1][j + 1] = lcs[i][j] + 1 if template[i] == seq[j] else max(lcs[i][j + 1], lcs[i + 1][j])
    share = lcs[m][n] / m
    status = OK if share >= 0.8 else WARN if share >= 0.6 else FLAG
    return status, (f"Opener matched {share:.0%} of the reference order. Yours: {', '.join(seq[:len(template) + 2])}."), []


RULES = [
    Rule("S1", "Eye Beam on cooldown", "High", BOTH, _rate_check(["Eye Beam"], "Eye Beam"),
         "Eye Beam is your strongest regular button. Press it whenever it's ready, unless adds spawn "
         "in the next few seconds."),
    Rule("S2", "Eye Beam before Metamorphosis", "High", BOTH, _meta_after_eye_beam,
         "Cast Eye Beam just before Metamorphosis. Metamorphosis resets Eye Beam's cooldown, so if Eye Beam "
         "was ready you throw that reset away."),
    Rule("S3", "Essence Break on cooldown", "Med", BOTH, _rate_check(["Essence Break"], "Essence Break"),
         "Press Essence Break whenever it's ready, even outside Metamorphosis. Don't hold it to line it up "
         "with Eye Beam."),
    Rule("S4", "Vengeful Retreat on cooldown", "Med", BOTH, _rate_check(["Vengeful Retreat"], "Vengeful Retreat"),
         "Use Vengeful Retreat whenever it's ready. With Exergy and Initiative it's a damage buff, not just "
         "a movement button. Guides pair it with Eye Beam, but that isn't checked."),
    Rule("S5", "The Hunt on cooldown", "Med", BOTH, _rate_check(["The Hunt"], "The Hunt"),
         "Use The Hunt whenever it's ready. As Aldrachi Reaver, throw Reaver's Glaive first if both are ready, "
         "because The Hunt gives you a new one."),
    Rule("S6", "Immolation Aura charges used", "Med", BOTH, _rate_check(["Immolation Aura"], "Immolation Aura"),
         "Immolation Aura has two charges. Don't let both sit full, or the recharge time is wasted."),
    Rule("S7", "No manual Throw Glaive", "Low", BOTH, _manual_throws,
         "Don't press Throw Glaive yourself unless you can't reach the target. Glaives your talents throw "
         "for you don't count, and a few throws as Fel-Scarred in Mythic+ are minor."),
    Rule("S8", "Blade Dance / Death Sweep on cooldown", "Med", BOTH,
         _rate_check(["Blade Dance", "Death Sweep"], "Blade Dance + Death Sweep"),
         "Keep Blade Dance (Death Sweep in Metamorphosis) on cooldown, and keep enough Fury to afford it "
         "when it comes back."),
    Rule("S9a", "Enough Fury for Metamorphosis", "Med", BOTH,
         _fury_at("Metamorphosis", LOW_FURY_META, "fury_at_meta"),
         f"Go into Metamorphosis with at least {LOW_FURY_META} Fury so you can spend right away. "
         "Top players enter with 100 to 150."),
    Rule("S9b", "Enough Fury for Essence Break", "Med", BOTH,
         _fury_at("Essence Break", LOW_FURY_EB, "fury_at_essence_break"),
         f"Go into Essence Break with at least {LOW_FURY_EB} Fury so its short damage window is full "
         "of spenders."),
    Rule("S11", "Avoid dead time", "High", BOTH, _idle,
         "Always be pressing something. Every second with nothing cast while you could hit the target is "
         "lost damage. Boss downtime and travel between Mythic+ pulls still count for now, so check the "
         "listed times."),
    Rule("S13", "Potion with burst", "Med", BOTH, _potion_with_meta,
         f"Drink your damage potion in the opener or with Metamorphosis (up to {PREPOT_S:.0f} s before it "
         "is fine), so it boosts your biggest damage."),
    Rule("AR1", "Reaver's Glaive on time", "High", AR, _rate_check(["Reaver's Glaive"], "Reaver's Glaive"),
         "Throw Reaver's Glaive as soon as it's available, at the main target. The exception is holding it a "
         "few seconds for an add wave you want to cleave."),
    Rule("AR2", "Both empowered spenders after each Glaive", "High", AR, _thrill_per_glaive,
         "After each Reaver's Glaive, use both empowered attacks (Rending Strike and Glaive Flurry) before "
         "the next Glaive. Doing both gives you Thrill of the Fight."),
    Rule("AR4", "Thrill of the Fight uptime", "Med", AR, _thrill_uptime,
         "Thrill of the Fight is a 30 s window you get from doing both empowered attacks. Don't watch it while "
         "playing: if AR2 is clean, this follows. Top players have it about 78% of a raid fight and 70% of a key."),
    Rule("AR5", "Opener", "Low", AR, _opener,
         "Start the pull with Method's Aldrachi Reaver opener: The Hunt, Reaver's Glaive, Eye Beam, "
         "Essence Break, spenders, then Metamorphosis. Checked on raid bosses only."),
    Rule("FS2", "Demonsurge in every Metamorphosis", "High", FS, _fs_demonsurge,
         "In Metamorphosis, trigger every Demonsurge: Death Sweep and Annihilation first, then Abyssal Gaze "
         "and Consuming Fire. A full window has 7 or more."),
    Rule("FS3", "Abyssal Gaze and Consuming Fire in Metamorphosis", "High", FS, _fs_meta_spenders,
         "Cast both Abyssal Gaze and Consuming Fire in every Metamorphosis you press."),
    Rule("FS4", "Opener", "Low", FS, _opener,
         "Start the pull with Method's Fel-Scarred opener: Eye Beam, The Hunt, Essence Break, spenders, "
         "then Metamorphosis with Abyssal Gaze and Consuming Fire. Checked on raid bosses only."),
]

# In the ruleset but not checked yet (docs/ruleset.md). Listed in the Rules tab only.
NOT_CHECKED = [
    Rule("S10", "Spend Fury during Metamorphosis", "Med", BOTH, None,
         "Keep spending Fury while Metamorphosis is up. Spending extends it (Shattered Destiny)."),
    Rule("S12", "Fel Rush only as filler", "Low", BOTH, None,
         "Use Fel Rush only when nothing else is ready or to get back to the target."),
    Rule("AR3", "Right spender order after a Glaive", "Med", AR, None,
         "On one target, alternate Blade Dance and Chaos Strike to build Reaver's Mark to 3 stacks, and use "
         "Chaos Strike first once you have 2 or more. With 2 or more targets, always Chaos Strike first."),
    Rule("FS1", "Immolation Aura before Metamorphosis", "Med", FS, None,
         "Spend your Immolation Aura charges before you press Metamorphosis."),
]


def rules_for(tree: str | None, rules: list[Rule] = RULES) -> list[Rule]:
    """Rules that apply to a hero tree: the shared ones, then the tree's own."""
    return [r for r in rules if r.tree is BOTH or r.tree == tree]


def evaluate(d: FightData, bench: Benchmark | None) -> list[Finding]:
    out = []
    for rule in RULES:
        if rule.tree is not None and rule.tree != d.hero_tree:
            continue
        result = rule.check(d, bench)
        if result is None:
            continue
        status, detail, times = result
        out.append(Finding(rule.id, rule.title, rule.severity, status, detail, times))
    out.sort(key=lambda f: (STATUS_ORDER[f.status], SEVERITY_ORDER[f.severity]))
    return out
