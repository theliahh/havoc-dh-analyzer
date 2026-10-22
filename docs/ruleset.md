# Havoc Demon Hunter Ruleset (v1)

Patch target: **12.1.5 (Midnight Season 2)**. Last reviewed 2026-10-22 against the guides below, 32 top-player logs (`docs/wcl-findings.md`) and the user's own raid and M+ logs.

Each rule has an id, what it asks of the player, how the analyzer checks it, a severity and its sources. Severity: **High** = clear DPS loss, **Med** = likely loss, **Low** = minor or depends on the situation. Rule ids are stable: the app's findings and Rules tab use them.

## Guide check (2026-10-22)

Both primary guides are still written for 12.1.5: Method was last updated 2026-10-16 and Wowhead 2026-10-13. Wowhead links a 12.1.7 PTR version, but neither guide lists rotation changes for it yet. Recheck when 12.1.7 goes live.

Points from the current guides that affect the rules:

- Essence Break goes on cooldown because of the 12.1 tier set, even outside demon form (M). Unchanged from v0.
- Throw Glaive "is not used actively, because Screaming Brutality spends charges automatically" (M). This is why the log shows talent-triggered Throw Glaive casts (S7). Method's Fel-Scarred single-target list still ends with "Throw Glaive, if nothing else is available".
- Exergy is still taken over Inertia (M), triggered by Vengeful Retreat and The Hunt. No top log in our sample had Inertia.
- Method's M+ Aldrachi Reaver list says "Metamorphosis, if Eye Beam is on cooldown", which matches S2.
- Wowhead still recommends Fel-Scarred for M+ and Aldrachi Reaver for raid. Top-100 logs are about 83% Aldrachi Reaver in both, so the analyzer doesn't judge the tree choice. It detects which tree was played and applies that tree's rules.
- Season 2 Fury changes (W): on-demand Fury was cut in favour of more Fury from auto attacks (Demon Blades buffed, Burning Hatred nerfed). No rule threshold changes, since the Fury checks use top-player numbers from this season.

## How the analyzer checks these (`havoc_analyzer/rules.py`)

**Pressed casts only.** Rules count button presses. Talent-triggered and proc casts are left out the same way on both sides of every comparison:

- Throw Glaive 185123 cast within 50 ms of Blade Dance 188499, Death Sweep 210152 or Reaver's Glaive 442294 / 444686 is automatic (Screaming Brutality / Furious Throws). 393035 and 337819 are also automatic throws. In the user's 2026-10-21 raid log all 368 Throw Glaive casts were automatic.
- The Hunt counts 370965 only (370966 is the follow-up). Reaver's Glaive counts 442294 only (444686 isn't a press and varies 1 to 6 a minute between top players).
- Abilities are counted by spell id, not name, because WCL and the log give the same name to the pressed and follow-up casts.

**Real Metamorphosis vs. Demonic.** The Metamorphosis buff 162264 is also applied for the short Demonic windows after Eye Beam (about 2.2 to 2.8 times a minute, against about 0.5 real Meta casts). A "pressed Metamorphosis" window is a buff window that starts with a Metamorphosis cast (200166). S13, FS2 and FS3 only look at pressed windows.

**Rates use time alive.** Casts per minute and idle seconds per minute divide by the time you were alive. Each death runs until your next cast after a battle res, and idle gaps that contain a death are skipped.

**Benchmarks, not fixed cooldowns.** Cast-rate rules compare your pressed casts per minute with the median of top-player logs for the same content (raid or M+) and hero tree, from `wcl/data/benchmarks.json`: 90% or more is ok, 75 to 90% a warning, under 75% a flag. That stands in for an exact cooldown model, which would have to follow haste, Cycle of Hatred and resets.

| Rule | Status | How it's checked |
|---|---|---|
| S1, S3, S4, S5, S8 | Checked | Pressed casts per minute vs. top players. |
| S2 | Checked | A Metamorphosis cast with no Eye Beam in the 10 s before it. Warn, or flag if half or more. |
| S6 | Proxy | Immolation Aura casts per minute vs. top players. Charges aren't in the log. |
| S7 | Checked | Pressed Throw Glaive casts only. Warns at 0.5/min or more, for both trees and both content types. |
| S9 | Checked as S9a / S9b | Fury at each Metamorphosis cast (under 90) and Essence Break cast (under 80). Top players enter at 100 to 150. |
| S11 | Checked | Gaps over 2.5 s between pressed casts, minus one GCD, vs. top players (ok within +1 s/min, warn within +3). |
| S13 | Checked | Damage potion in the first 20 s, inside a pressed Metamorphosis, or up to 10 s before one (pre-pot). |
| AR1 | Checked | Reaver's Glaive 442294 per minute vs. top players. |
| AR2 | Checked | Each Reaver's Glaive should lead to Thrill of the Fight (442695) before the next Glaive. Ok at 90%, warn at 75%. |
| AR4 | Checked | Thrill of the Fight uptime vs. top players: within 5 points ok, within 15 a warning. |
| AR5, FS4 | Checked (raid only) | First 20 s of casts vs. the Method opener order. Ok at 80% match, warn at 60%. |
| FS2 | Checked | Demonsurge hits per pressed Metamorphosis window; fewer than 7 is low. |
| FS3 | Checked | Abyssal Gaze and Consuming Fire in every pressed Metamorphosis window. |
| S10, S12, AR3, FS1 | **Not implemented** | Need Fury spend tracking, cooldown state, or buff state at each spender. Listed below for completeness; the app doesn't report them. |

### Top-player benchmarks (medians of 8 logs per group, pressed casts)

| Metric | Raid AR | Raid FS | M+ AR | M+ FS |
|---|---|---|---|---|
| Eye Beam / min | 3.00 | 2.29 | 2.76 | 1.89 |
| Essence Break / min | 1.81 | 1.69 | 1.66 | 1.48 |
| The Hunt / min | 1.01 | 0.99 | 0.93 | 0.83 |
| Metamorphosis casts / min | 0.49 | 0.57 | 0.45 | 0.43 |
| Death Sweep / min | 8.2 | 7.5 | 7.2 | 6.0 |
| Immolation Aura / min | 1.45 | 1.92 | 1.63 | 1.75 |
| Vengeful Retreat / min | 2.31 | 2.49 | 2.25 | 1.97 |
| Reaver's Glaive 442294 / min | 5.1 | - | 4.5 | - |
| Thrill of the Fight uptime | 78% | - | 70% | - |
| Abyssal Gaze / Consuming Fire per min | - | 0.69 / 3.10 | - | 0.71 / 2.65 |
| Manual Throw Glaive / min | 0 | 0 to 1.7 | under 0.1 | 0.8 to 3.0 |
| Fury at Meta cast | 111 | 145 | 120 | 131 |
| Fury at Essence Break cast | 100 | 138 | 100 | 148 |
| Idle s / min (pressed casts) | 1.2 | 2.2 | 4.4 | 7.8 |

The analyzer reads the live numbers from `wcl/data/benchmarks.json`; this table is a snapshot. Eight logs per group is a small sample, so treat differences of a few percent as noise.

## Sources

| Key | Source | Patch / date | Notes |
|---|---|---|---|
| M | [Method: Playstyle and Rotation](https://www.method.gg/guides/havoc-demon-hunter/playstyle-and-rotation) | 12.1.5, updated 2026-10-16 | Most detailed. Separate openers and priorities per hero tree and content. |
| W | [Wowhead: Havoc Overview](https://www.wowhead.com/guide/classes/demon-hunter/havoc/overview-pve-dps) | 12.1.5, updated 2026-10-13 | Hero tree advice, Season 2 changes, general rules. |
| T | Top-player logs via Warcraft Logs (`docs/wcl-findings.md`) | 12.1.5, pulled 2026-10-22 | 32 logs, best per encounter, The Venomous Abyss Mythic and M+ Season 2. |
| U | The user's own raid and M+ logs (October 2026) | 12.1.5 | Where log quirks (auto Throw Glaive, Demonic Meta buff) were found. |
| I | [Icy Veins: Rotation and Cooldowns](https://www.icy-veins.com/wow/havoc-demon-hunter-pve-dps-rotation-cooldowns-abilities) | 12.0 pre-patch | **Outdated.** Used only where M or W agree. |
| X | [Maxroll](https://maxroll.gg/wow/class-guides/havoc-demon-hunter-raid-guide), [Archon](https://www.archon.gg/wow/builds/havoc/demon-hunter/raid/overview/mythic/all-bosses) | 11.1 / 11.1.5 | **Outdated.** Background only. |

## Shared rules (both hero trees)

| ID | Rule | Detection | Sev | Src |
|---|---|---|---|---|
| S1 | Cast Eye Beam on cooldown. Don't hold it more than about 3 to 4 s unless adds spawn soon. | Eye Beam casts/min vs. top players. | High | M, W, T |
| S2 | Don't cast Metamorphosis while Eye Beam is ready or has under 10 s left. Eye Beam goes first. | Meta cast with no Eye Beam in the 10 s before. | High | M, T |
| S3 | Cast Essence Break on cooldown (12.1 tier set), even outside demon form. Don't hold it for Eye Beam. | Essence Break casts/min vs. top players. | Med | M, W, T |
| S4 | Use Vengeful Retreat on cooldown (Exergy, Initiative). Guides say to pair it with Eye Beam, but only 26 to 47% of top players' Retreats land within 2 s of one, so pairing isn't checked. | VR casts/min vs. top players. | Med | M, W, T |
| S5 | Cast The Hunt on cooldown (AR: when Reaver's Glaive isn't available). | The Hunt 370965 casts/min vs. top players. | Med | M, T |
| S6 | Don't sit at 2 Immolation Aura charges. | Proxy: Immolation Aura casts/min vs. top players. | Med | M, T |
| S7 | Don't press Throw Glaive. Exception: out of range or nothing else to press. Talent-triggered throws don't count (see above). Top AR players throw manually almost never; top FS players in M+ throw 0.8 to 3 a minute, so for Fel-Scarred in M+ treat a warning here as minor. | Pressed 185123 casts/min, warn at 0.5. | Low | M, T, U |
| S8 | Keep Blade Dance / Death Sweep on cooldown, and keep enough Fury to cast it. | BD + DS casts/min vs. top players. | Med | M, W, T |
| S9 | Don't enter Metamorphosis (S9a) or Essence Break (S9b) with low Fury. Pool before Eye Beam comes up. | Fury at cast time: under 90 for Meta, under 80 for Essence Break. | Med | W, T |
| S10 | Spend Fury during Metamorphosis (Shattered Destiny extends it). | *Not implemented.* Fury spent and Meta duration vs. expected. | Med | M |
| S11 | Avoid dead time (no GCD used while a target is in range). | Idle s/min between pressed casts vs. top players. Forced downtime (untargetable bosses, transitions) and M+ travel between pulls still count. | High | general, T |
| S12 | Fel Rush only as filler, for movement or out of range. | *Not implemented.* Fel Rush while higher-priority abilities were ready. | Low | M, I |
| S13 | Use potion and on-use trinket with the opener and Metamorphosis. Pre-potting up to 10 s before Meta is fine. | Potion timing vs. opener and pressed Meta windows. Trinkets not checked yet. | Med | M, U |

## Aldrachi Reaver rules

| ID | Rule | Detection | Sev | Src |
|---|---|---|---|---|
| AR1 | Use Reaver's Glaive as soon as it's available, on the priority target. | 442294 casts/min vs. top players (5.1 raid, 4.5 M+). | High | M, T |
| AR2 | After Reaver's Glaive, use the right spender order to get both empowerments (Rending Strike and Glaive Flurry). | Thrill of the Fight applied before the next Glaive. | High | M, W |
| AR3 | M+: Blade Dance when buffed by Glaive Flurry but not Rending Strike. Chaos Strike / Annihilation when buffed by both. | *Not implemented.* Buff state at each spender cast. | Med | M |
| AR4 | Keep Thrill of the Fight up. | Uptime vs. top players (78% raid, 70% M+). | Med | T |
| AR5 | Opener follows Method's AR opener (Immolation Aura pre-pull, The Hunt, pot + trinket, Reaver's Glaive, Eye Beam, Essence Break, ...). | First 20 s of casts vs. the template (raid). | Low | M |

## Fel-Scarred rules

| ID | Rule | Detection | Sev | Src |
|---|---|---|---|---|
| FS1 | Spend Immolation Aura charges before Metamorphosis. | *Not implemented.* Immolation charges at Meta cast. | Med | W, M |
| FS2 | In Meta, trigger every Demonsurge: Death Sweep and Annihilation first, then Abyssal Gaze and Consuming Fire. | Demonsurge hits per pressed Meta window, 7 or more (top players: raid mostly 7, M+ 7 to 11). | High | M, T |
| FS3 | Use Abyssal Gaze and Consuming Fire in every Meta window. | Both cast inside each pressed Meta window. | High | M, T |
| FS4 | Opener follows Method's FS opener (Immolation charges spent 2 to 3 s pre-pull, pot + trinket, Eye Beam, The Hunt, Essence Break, ...). | First 20 s of casts vs. the template (raid). | Low | M |

## Raid vs. Mythic+

- Raid: rules run per boss pull, with the raid-AR or raid-FS benchmark.
- M+: rules run for the whole key, with the M+ benchmark. Boss pulls inside a key are listed separately but still use the whole-key benchmark (top logs are only available per key). Method's M+ priority ranks Blade Dance / Death Sweep and Immolation Aura higher; the benchmarks already reflect that.
- Openers (AR5, FS4) are only checked in raid.

## Known gaps

1. **S10, S12, AR3, FS1** aren't implemented (see the status table).
2. **Idle time (S11)** doesn't exclude forced downtime in raid or travel between M+ pulls. Top-player M+ idle numbers include travel too, so the comparison is fair on average but noisy per key.
3. **S7** uses one threshold for both trees; Fel-Scarred in M+ will warn on normal AoE or out-of-range throws.
4. **S6** is a proxy; charge state isn't in the log.
5. **Trinkets** aren't checked in S13.
6. **Benchmark sample** is 8 logs per group. Rerun `wcl/benchmarks.py 20` for tighter numbers, and refresh `wcl/hero_tree.py` talent IDs after a talent patch.
7. **12.1.7**: recheck M and W when it goes live.
