"""Measure ruleset metrics on top Havoc logs, per content (raid / M+) and hero tree.

Reads data/top_rankings.json, samples the best log per encounter for each
(content, hero), loads it through havoc_analyzer.wcl_source and measures it with
havoc_analyzer.summary, so benchmarks use exactly the same code as the user's logs.
Writes data/benchmarks.json (per-log metrics) and prints medians.
Usage: python3 wcl/benchmarks.py [N]
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from havoc_analyzer.summary import build  # noqa: E402
from havoc_analyzer.wcl_source import load_fight  # noqa: E402
from wcl.wcl_client import WCLClient  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "data")
REAVERS_GLAIVE_CAST, REAVERS_GLAIVE_PROC = 442294, 444686
THRILL = 442695
DEMONSURGE = "Demonsurge"


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def measure(d, row):
    m = d.minutes
    fury = lambda name: _median([e.fury for e in d.casts.get(name, []) if e.fury is not None])  # noqa: E731
    _, idle_all = d.idle(all_casts=True)
    _, idle_pressed = d.idle()
    glaive_ids = [e.spell_id for e in d.own_events if e.type == "cast" and e.src == d.player
                  and e.spell_id in (REAVERS_GLAIVE_CAST, REAVERS_GLAIVE_PROC)]
    surges = sorted({round(e.t, 3) for e in d.own_events
                     if e.type == "damage" and e.src == d.player and e.spell_name == DEMONSURGE})
    real = [w for w in d.meta_windows if w.from_cast]
    return {
        **{k: row[k] for k in ("content", "hero", "encounter", "rank", "name", "dps", "keyLevel", "report", "fightID")},
        "minutes": round(m, 2),
        # Every cast by spell name, as Warcraft Logs counts them (includes proc / talent casts).
        "cpm": {n: round(c / m, 2) for n, c in d.cast_names.items() if c},
        # Pressed casts only (TRACKED_CASTS, talent-triggered Throw Glaive removed).
        "pressed_cpm": {n: round(len(cs) / m, 2) for n, cs in d.casts.items() if cs},
        "reavers_glaive_442294_pm": round(glaive_ids.count(REAVERS_GLAIVE_CAST) / m, 2),
        "reavers_glaive_444686_pm": round(glaive_ids.count(REAVERS_GLAIVE_PROC) / m, 2),
        "manual_throw_glaive": len(d.casts.get("Throw Glaive", [])),
        "fury_at_meta": fury("Metamorphosis"), "fury_at_essence_break": fury("Essence Break"),
        "idle_seconds_rough": round(idle_all, 1),        # gaps between any casts
        "idle_pressed_seconds": round(idle_pressed, 1),  # gaps between pressed casts only
        "thrill_uptime": round(d.uptime(THRILL), 3) if d.hero_tree == "Aldrachi Reaver" else None,
        "meta_windows": len(d.meta_windows), "meta_cast_windows": len(real),
        "demonsurge_per_meta": [sum(w.start <= t <= w.end for t in surges) for w in real],
    }


def main(n=8):
    c = WCLClient()
    rows = json.load(open(os.path.join(DATA, "top_rankings.json")))
    picks = []
    for content in ("raid", "mplus"):
        for hero in ("AR", "FS"):
            pool = sorted((r for r in rows if r["content"] == content and r["hero"] == hero), key=lambda r: r["rank"])
            seen = set()
            for r in pool:  # best-ranked per encounter first, so the sample spans encounters
                if r["encounter"] not in seen and len(seen) < n:
                    seen.add(r["encounter"])
                    picks.append(r)
    out = []
    for r in picks:
        try:
            fight, player = load_fight(c, r["report"], r["fightID"], r["name"])
            m = measure(build(fight, player), r)
        except Exception as e:  # keep going; private/expired reports happen
            print("skip", r["name"], r["report"], e)
            continue
        out.append(m)
        print(json.dumps(m, ensure_ascii=False))
    json.dump(out, open(os.path.join(DATA, "benchmarks.json"), "w"), ensure_ascii=False, indent=1)
    print(c.rate_limit())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
