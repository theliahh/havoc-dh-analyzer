# Havoc Demon Hunter Ruleset (v0, draft)

Patch target: **12.1.5 (Midnight)**. Drafted 2026-10-22 from guides, then corrected against 32 top-player logs (see `docs/wcl-findings.md`).

Each rule has an id, what it checks, how a log can detect it, a default severity, and its sources. Severity: **High** = clear DPS loss, **Med** = likely loss, **Low** = minor or context-dependent.

## How the analyzer checks these (v1, `havoc_analyzer/rules.py`)

Cast-rate rules compare your pressed casts per minute (talent-triggered and proc casts left out, counted the same way on both sides) with the median of top-player logs for the same content (raid or M+) and hero tree, from `wcl/data/benchmarks.json`: 90% or more is fine, 75 to 90% is a warning, under 75% is a flag. That stands in for an exact cooldown model, which would have to follow haste, Cycle of Hatred and resets.

| Rule | Status | How it's checked |
|---|---|---|
| S1, S3, S4, S5, S8 | Checked | Casts per minute vs. top players. |
| S2 | Checked | A Metamorphosis cast with no Eye Beam in the 10 s before it is flagged (Eye Beam was likely ready or nearly ready). |
| S6 | Proxy | Immolation Aura casts per minute vs. top players. Charges aren't in the log. |
| S7 | Checked | Pressed Throw Glaive casts only (talent-triggered ones excluded). Warns at 0.5/min or more. |
| S9 | Checked | Fury at each Metamorphosis (under 90) and Essence Break (under 80). Top players enter at 100 to 150. |
| S11 | Checked | Gaps over 2.5 s between pressed casts vs. top players (1.2 s/min raid AR, 2.2 raid FS, 4.4 M+ AR, 7.8 M+ FS). Forced downtime isn't excluded yet. |
| S13 | Checked | Damage potion in the first 20 s or inside a pressed Metamorphosis. |
| AR1 | Checked | Reaver's Glaive (spell 442294) per minute vs. top players (about 5.1/min in raid, 4.5 in M+). |
| AR2 | Checked | Each Reaver's Glaive should be followed by Thrill of the Fight before the next Glaive. |
| AR4 | Checked | Thrill of the Fight uptime vs. top players (78% raid, 70% M+): within 5 points fine, within 15 a warning. |
| AR5, FS4 | Checked (raid) | First 20 s of casts vs. the Method opener order. |
| FS2 | Checked | Demonsurge hits per pressed Metamorphosis window, 7 or more expected. |
| FS3 | Checked | Abyssal Gaze and Consuming Fire in every pressed Metamorphosis window. |
| S10, S12, AR3, FS1 | Not yet | Need Fury spend tracking, cooldown state or buff state per spender. |

"Pressed Metamorphosis" means a Meta buff window that starts with a Metamorphosis cast. Demonic windows after Eye Beam use the same buff and are told apart this way.

## Sources

| Key | Source | Patch / date | Notes |
|---|---|---|---|
| M | [Method: Playstyle and Rotation](https://www.method.gg/guides/havoc-demon-hunter/playstyle-and-rotation) | 12.1.5 | Most detailed. Separate openers and priorities per hero tree. |
| W | [Wowhead: Havoc Overview](https://www.wowhead.com/tw/guide/classes/demon-hunter/havoc/overview-pve-dps) | 12.1.5, updated 2026-10-13 | Hero tree advice and general rules. |
| I | [Icy Veins: Rotation and Cooldowns](https://www.icy-veins.com/wow/havoc-demon-hunter-pve-dps-rotation-cooldowns-abilities) | 12.0 pre-patch, Jan 2026 | **Outdated.** Use only where M or W agree. |
| X | [Maxroll Raid Guide](https://maxroll.gg/wow/class-guides/havoc-demon-hunter-raid-guide), [Archon builds](https://www.archon.gg/wow/builds/havoc/demon-hunter/raid/overview/mythic/all-bosses) | 11.1 / 11.1.5 | **Outdated.** Kept for background only. |

**Hero tree picks disagree.** W says Aldrachi Reaver for raid and single target, Fel-Scarred for M+. I (older) says Fel-Scarred for both. The analyzer won't judge the hero tree choice. It detects which tree was played and applies that tree's rules.

## Shared rules (both hero trees)

| ID | Rule | Detection | Sev | Src |
|---|---|---|---|---|
| S1 | Cast Eye Beam on cooldown. Don't hold it more than about 3 to 4 s unless adds spawn soon. | Time Eye Beam sits ready (cooldown model incl. Cycle of Hatred). | High | M, W, X |
| S2 | Don't cast Metamorphosis while Eye Beam is ready or has under 10 s left. Eye Beam goes first. | At each Meta cast, check Eye Beam's cooldown state. | High | M, I, X |
| S3 | Cast Essence Break on cooldown (12.1 tier set). Don't hold it to line up with Eye Beam. | Ready time for Essence Break. | Med | M |
| S4 | Use Vengeful Retreat on cooldown (Exergy, Initiative). Guides say to pair it with Eye Beam, but only 26 to 47% of top players' VRs land within 2 s of one, so pairing is not checked. | VR ready time. | Med | M, W, WCL top logs |
| S5 | Cast The Hunt on cooldown (AR: when Reaver's Glaive isn't available). | Ready time for The Hunt. | Med | M, I |
| S6 | Don't sit at 2 Immolation Aura charges. | Time at max charges. | Med | M, I, X |
| S7 | Don't cast Throw Glaive manually. Exception: out of range or nothing else to press. Spell 185123 also fires automatically (0 Fury cost, same timestamp as Blade Dance, Death Sweep or Reaver's Glaive), as do 393035 and 337819; only a 185123 cast with none of those within 50 ms is a button press. In the 2026-10-21 sample all 368 were automatic. | Manual 185123 casts while in melee with other options ready. | Low | M, I |
| S8 | Keep Blade Dance / Death Sweep on cooldown, and keep enough Fury to cast it. | BD/DS ready time; casts of Chaos Strike that left BD unaffordable. | Med | W, I |
| S9 | Don't enter Metamorphosis or Essence Break with low Fury. | Fury at cast time (from resource events). | Med | I, W |
| S10 | Spend Fury during Metamorphosis (Shattered Destiny extends it). | Fury spent and Meta duration vs. expected. | Med | M |
| S11 | Avoid dead time (no GCD used while a target is in range). | Gaps between casts, excluding forced downtime. | High | general |
| S12 | Fel Rush only as filler or out of range. | Fel Rush casts while higher-priority abilities were ready. | Low | X, I |
| S13 | Use potion and on-use trinket with the opener and Meta. | Potion/trinket buff overlap with Meta. | Med | M |

## Aldrachi Reaver rules

| ID | Rule | Detection | Sev | Src |
|---|---|---|---|---|
| AR1 | Use Reaver's Glaive as soon as it's available, on the priority target. | Time between proc and cast. | High | M, X |
| AR2 | After Reaver's Glaive, alternate the right spender order to get both empowerments (Rending Strike and Glaive Flurry). | Sequence check on casts after each Glaive. | High | M, X |
| AR3 | M+: Blade Dance when buffed by Glaive Flurry but not Rending Strike. Chaos Strike / Annihilation when buffed by both. | Buff state at each spender cast. | Med | M |
| AR4 | Keep Thrill of the Fight up. | Buff uptime. | Med | X |
| AR5 | Opener follows Method's AR opener (Immo pre-pull, Hunt, pot + trinket, Glaive, Eye Beam, Essence Break, ...). | Compare first 15 casts to the template. | Low | M |

## Fel-Scarred rules

| ID | Rule | Detection | Sev | Src |
|---|---|---|---|---|
| FS1 | Spend Immolation Aura charges before Metamorphosis (Demonic Intensity changes the order). | Immo charges at Meta cast. | Med | W, M |
| FS2 | In Meta, trigger every Demonsurge: Death Sweep and Annihilation first, then Abyssal Gaze and Consuming Fire. | Count Demonsurge events per Meta window vs. maximum. | High | M |
| FS3 | Use Abyssal Gaze and Consuming Fire in every Meta window. | Casts per Meta window. | High | M |
| FS4 | Opener follows Method's FS opener (Immo charges spent pre-pull, pot + trinket, Eye Beam, Hunt, Essence Break, ...). | Compare first 16 casts to the template. | Low | M |

## Raid vs. Mythic+

- Raid: apply rules per boss pull. Exclude forced downtime (boss untargetable, phase transitions) from S1, S5, S11.
- M+: apply rules per pull and for the whole key. Add an "AoE pull" mode where Blade Dance/Death Sweep and Immolation Aura rank higher (M's M+ priority). Exclude travel time between pulls from dead time.

## Open items

1. **Validate against top logs.** Pull top 10 to 20 Havoc parses per boss and per dungeon for each hero tree, measure cooldown ready-time, casts per minute and Demonsurge counts, and use them as benchmarks instead of fixed thresholds. Blocked for now: this environment can't reach `www.warcraftlogs.com`.
2. **Spell IDs** for every ability, buff and proc, plus exact cooldowns (Cycle of Hatred reduction is reported differently across sources).
3. **Hero-tree detection** from talent info in the log header (COMBATANT_INFO) or WCL talent data.
4. Confirm Exergy vs. Inertia is still the standard pick; rules S4 and S12 change if Inertia is taken.
