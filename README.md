# Havoc DH Analyzer

Finds mistakes and improvements in Havoc Demon Hunter play from World of Warcraft combat logs, per raid boss pull and per Mythic+ key, with rules for both Aldrachi Reaver and Fel-Scarred.

## Layout

- `havoc_analyzer/` - the analyzer (Python 3.10+, standard library only):
  - `events.py` - the shared event and fight model.
  - `combatlog.py` - raw `WoWCombatLog.txt` parser (boss pulls and Mythic+ keys).
  - `wcl_source.py` - loads one Warcraft Logs fight into the same model.
  - `summary.py` - per-fight data: pressed casts, real Metamorphosis windows, uptimes, idle time.
  - `rules.py` - the ruleset checks; `benchmarks.py` - top-player medians.
- `tests/` - unit tests: `python -m unittest discover -s tests -t .`
- `wcl/` - Warcraft Logs v2 API client, top-player rankings and benchmarks. Needs `WCL_CLIENT_ID` and `WCL_CLIENT_SECRET` in the environment; never commit them.
- `docs/ruleset.md` - the rules the analyzer checks, each tied to a source.
- `docs/wcl-findings.md` - top-log benchmarks and the raw log vs. API comparison.
- `docs/sample-report-2026-10-21.md` - example output.

## Run

    python -m havoc_analyzer path/to/WoWCombatLog.txt --out report.md

The report lists, for every boss pull and key, each rule as 🔴 likely DPS lost, 🟡 worth a look, 🟢 fine or ⚪ measured only, with timestamps to look at, plus an overview of rules that came up across fights.

Turn on Advanced Combat Logging in game. Built against COMBAT_LOG_VERSION 22, build 12.1.5. Mythic+ splitting is written but not yet tested on a real key.
