# Havoc DH Analyzer

Finds mistakes and improvements in Havoc Demon Hunter play from World of Warcraft combat logs, per raid boss pull and per Mythic+ key, with rules for both Aldrachi Reaver and Fel-Scarred.

## Layout

- `havoc_analyzer/` - raw `WoWCombatLog.txt` parser and per-fight summary (Python 3.10+, standard library only).
- `wcl/` - Warcraft Logs v2 API client, top-player rankings and benchmarks. Needs `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` in the environment; never commit them.
- `docs/ruleset.md` - the rules the analyzer checks, each tied to a source.
- `docs/wcl-findings.md` - top-log benchmarks and the raw log vs. API comparison.
- `docs/sample-report-2026-10-21.md` - example output.

## Run

    python -m havoc_analyzer path/to/WoWCombatLog.txt --out report.md

Turn on Advanced Combat Logging in game. Built against COMBAT_LOG_VERSION 22, build 12.1.5. Mythic+ splitting is written but not yet tested on a real key.
