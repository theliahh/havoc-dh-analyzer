# Warcraft Logs API prototype: findings

Date: 2026-10-22. Patch 12.1.5. Code in `havoc-analyzer/wcl/`.

## What was built

| File | What it does |
|---|---|
| `wcl_client.py` | WCL v2 GraphQL client. Client credentials from `WCL_CLIENT_ID` / `WCL_CLIENT_SECRET`; token kept in memory only. Helpers: `fight`, `events` (auto-paginates), `abilities`, `player_details`, `top_havoc`, `rate_limit`. |
| `fetch_top.py` | Top 100 Havoc DPS per boss (The Venomous Abyss, Mythic) and per dungeon (Midnight M+ Season 2) with talents. Writes `data/top_rankings.json` (1,800 rankings). |
| `hero_tree.py` | Detects Aldrachi Reaver vs Fel-Scarred from WCL talent IDs, or from signature abilities in events. |
| `label_hero.py` | One-off: confirmed the tree of 24 random top logs from their casts, used to find the talent IDs. |
| `benchmarks.py` | Pulls casts, buffs and Fury for the best log per encounter (8 per content and tree, 32 logs) and measures ruleset metrics. Writes `data/benchmarks.json`. |

## What the API provides

- **Fights, pre-segmented.** Boss pulls with kill/wipe and boss %, and M+ keys with key level, affixes and time.
- **Events** for one player in one fight, filterable by type (Casts, Buffs, Debuffs, DamageDone, Resources, ...) or by an expression such as `ability.name = "Demonsurge"`. These are the combat log events in JSON:
  - Cast events carry the caster's **Fury at cast time** (`classResources`), plus HP, position and stats.
  - `resourcechange` events carry Fury gained and **Fury wasted** (overcap) directly.
  - One `combatantinfo` event per fight with talents, gear and stats.
- **Ability names** (`masterData`), so code can match by name and not hard-code IDs.
- **Rankings** per boss and per dungeon, filterable by class and spec, with each player's talents and gear. No hero-tree filter, but talents identify the tree reliably (below).
- **Limits.** 1,000 points per hour. One full analysis of a fight costs about 7 points (boss pull or full 30 min key), a ranking page about 2 to 10. This whole prototype used about 400. Token is valid for 360 days.

## Hero tree detection

Talent IDs separate the trees cleanly. Eight hero-node IDs for each tree (in `hero_tree.py`) classified all 1,758 rankings that had talent data, and matched all 24 hand-checked logs. 42 rankings (mostly M+) had no talents attached; for those, fall back to events (Reaver's Glaive / Art of the Glaive vs Demonsurge / Abyssal Gaze).

Top 100 split: raid 831 AR / 168 FS, M+ 633 AR / 126 FS. So AR dominates both, which goes against Wowhead's "Fel-Scarred for M+".

## Benchmarks from top logs (medians, 8 logs per group)

| Metric | Raid AR | Raid FS | M+ AR | M+ FS |
|---|---|---|---|---|
| Eye Beam / min | 3.00 | 2.29 | 2.76 | 1.89 |
| Essence Break / min | 1.81 | 1.69 | 1.66 | 1.48 |
| The Hunt / min | 2.01 | 1.98 | 1.85 | 1.67 |
| Metamorphosis casts / min | 0.49 | 0.57 | 0.45 | 0.43 |
| Death Sweep / min | 8.2 | 7.5 | 7.2 | 6.0 |
| Immolation Aura / min | 1.45 | 2.43 | 1.63 | 2.30 |
| Vengeful Retreat / min | 2.31 | 2.49 | 2.25 | 1.97 |
| Reaver's Glaive / min | 9.3 | - | 7.5 | - |
| Abyssal Gaze / Consuming Fire per min | - | 0.69 / 3.10 | - | 0.71 / 2.65 |
| Manual Throw Glaive / min (corrected) | 0 | 0 to 1.7 | under 0.1 | 0.8 to 3.0 |
| Fury at Meta cast | 111 | 145 | 120 | 131 |
| Fury at Essence Break cast | 100 | 138 | 100 | 148 |
| Fury wasted (% of gained) | 16.6 | 8.4 | 17.5 | 13.2 |
| VR within 2 s of Eye Beam | 26% | 47% | 36% | 27% |
| Idle s / min (rough, gaps over 2.5 s) | 0.6 | 1.2 | 3.0 | 5.8 |

Fel-Scarred Demonsurge triggers per Metamorphosis buff window: mostly 3 (short Demonic windows after Eye Beam), with 7 to 12 in full Meta windows.

## What this says about ruleset-v0

These are suggestions for whoever owns the ruleset; I did not edit it.

1. **S7 (no manual Throw Glaive): corrected.** My first count was wrong. Spell 185123 is also logged when a talent throws the glaive alongside Blade Dance, Death Sweep or Reaver's Glaive (found in the raw log by the parser thread). Excluding 185123 casts within 50 ms of 188499, 210152, 442294 or 444686, top AR players throw manually almost never (0 to 0.1 a minute). Top FS players in M+ do throw 0.8 to 3 times a minute, likely on AoE or out of range, so S7 should stay Low severity there.
2. **S4 (Vengeful Retreat paired with Eye Beam) is not what top players do.** Only 26 to 47% of their VRs land within 2 s of an Eye Beam. Use VR ready-time (on cooldown) and drop the pairing check, or widen the window.
3. **S9 (don't Meta / Essence Break with low Fury) is supported.** Top players enter with 100 to 150 Fury. A threshold around 80 to 90 would be safe.
4. **Fury waste is normal.** Even top logs waste 8 to 18%. Benchmark against these numbers, not zero.
5. **"Metamorphosis" windows include Demonic.** The buff is applied about 2.2 to 2.8 times a minute, mostly from Eye Beam (Demonic), while real Meta casts are about 0.5 a minute. S10, FS1, FS2 and FS3 have to tell the two apart (match the buff to a Meta cast vs an Eye Beam cast).
6. **Use these numbers as benchmarks** for S1, S3, S5 and FS3 instead of fixed thresholds, per the ruleset's open item 1.
7. **Open item 4:** no top log in the sample showed Inertia; Exergy and Initiative buffs were present, so Exergy still looks standard.

Spell IDs seen (open item 2): Eye Beam 198013, Essence Break 258860, The Hunt 370965, Metamorphosis cast 200166 / buff 162264, Blade Dance 188499, Death Sweep 210152, Chaos Strike 162794, Annihilation 201427, Immolation Aura 258920, Vengeful Retreat 198793, Fel Rush 195072, Felblade 232893, Throw Glaive 185123 (also 337819 and 393035, which are talent/proc casts), Reaver's Glaive 442294, Art of the Glaive 444661, Glaive Flurry 442435, Rending Strike 442442, Thrill of the Fight 442688 / 442695, Demonsurge 452416, Abyssal Gaze 452497, Consuming Fire 452487, Initiative 391215, Exergy 208628, Cycle of Hatred 1214887.

## API vs raw combat log

| | Warcraft Logs API | Raw WoWCombatLog.txt |
|---|---|---|
| Needs | Log uploaded to WCL, internet, API key | Advanced combat logging on, local file only |
| Event content | Same events, already parsed to JSON, names attached | Same events; you parse CSV-like lines yourself |
| Fight split | Done (pulls, keys, kill/wipe, key level, affixes) | Must split on ENCOUNTER_START/END, CHALLENGE_MODE_START/END |
| Fury | At cast time plus explicit waste | In advanced-log fields on each event; waste must be computed |
| Talents | Talent entry IDs (hero tree detectable) | COMBATANT_INFO talent entries, same kind of IDs |
| Top players | Rankings with talents for every boss and dungeon | Not available |
| Limits | 1,000 points/hour (about 140 fight analyses/hour) | None |

**Recommendation:** make the raw log the primary input for the user's own fights (no upload, no rate limit), and use WCL for benchmarks from top players and for analyzing any report link. Both carry the same combat log events, so the analyzer core should read one shared event model with two adapters.

## Caveats

- 8 logs per group is a small sample. Rerun `benchmarks.py 20` for tighter numbers (about 300 points).
- Demonsurge counts group hits by timestamp, which can merge two surges in the same millisecond.
- Idle time is rough and counts M+ travel between pulls.
- The 2026-10-22 talent IDs may change with a talent patch; rerun `label_hero.py` to refresh them.
