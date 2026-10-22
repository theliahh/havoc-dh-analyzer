"""Measure ruleset metrics on top Havoc logs, per content (raid / M+) and hero tree.

Reads data/top_rankings.json, samples the top N per (content, hero) spread across
encounters, pulls the player's casts, own buffs and Fury changes, and writes
data/benchmarks.json (per-log metrics) and prints medians.
Usage: python3 benchmarks.py [N]
"""
import collections
import json
import os
import statistics
import sys

from wcl_client import WCLClient

DATA = os.path.join(os.path.dirname(__file__), "data")
FURY = 17
TRACK = ["Eye Beam", "Essence Break", "The Hunt", "Metamorphosis", "Blade Dance", "Death Sweep",
         "Chaos Strike", "Annihilation", "Immolation Aura", "Vengeful Retreat", "Fel Rush", "Felblade",
         "Reaver's Glaive", "Abyssal Gaze", "Consuming Fire"]
THROW_GLAIVE = 185123
# A 185123 cast within 50 ms of one of these is talent-triggered, not a button press.
GLAIVE_TRIGGERS = {188499, 210152, 442294, 444686}


def actor_id(c, code, name):
    q = 'query($c:String!){ reportData{ report(code:$c){ masterData{ actors(type:"Player"){ id name } } } } }'
    for a in c.query(q, {"c": code})["reportData"]["report"]["masterData"]["actors"]:
        if a["name"] == name:
            return a["id"]


def analyse(c, row):
    code, fid = row["report"], row["fightID"]
    sid = actor_id(c, code, row["name"])
    ab = c.abilities(code)
    fight = c.fight(code, fid)
    span = dict(start=fight["startTime"], end=fight["endTime"])
    casts = [e for e in c.events(code, fid, source_id=sid, data_type="Casts", include_resources=True, **span)
             if e["type"] == "cast" and e.get("sourceID") == sid]
    buffs = [e for e in c.events(code, fid, source_id=sid, data_type="Buffs", **span)
             if e.get("targetID") == sid]
    res = [e for e in c.events(code, fid, source_id=sid, data_type="Resources", **span)
           if e.get("resourceChangeType") == FURY and e.get("targetID") == sid]
    dmg_names = collections.Counter()
    for e in c.events(code, fid, source_id=sid, data_type="DamageDone", filter='ability.name = "Demonsurge"', **span):
        dmg_names[e["timestamp"]] += 1  # one Demonsurge proc hits several targets in the same ms

    minutes = (fight["endTime"] - fight["startTime"]) / 60000
    n = collections.Counter(ab.get(e["abilityGameID"], str(e["abilityGameID"])) for e in casts)
    cpm = {k: round(n[k] / minutes, 2) for k in TRACK if n[k]}

    def fury_at(name):
        v = [r["amount"] for e in casts if ab.get(e["abilityGameID"]) == name
             for r in e.get("classResources", []) if r["type"] == FURY]
        return statistics.median(v) if v else None

    eb = [e["timestamp"] for e in casts if ab.get(e["abilityGameID"]) == "Eye Beam"]
    vr = [e["timestamp"] for e in casts if ab.get(e["abilityGameID"]) == "Vengeful Retreat"]
    vr_paired = sum(any(abs(v - b) <= 2000 for b in eb) for v in vr)

    trig = [e["timestamp"] for e in casts if e["abilityGameID"] in GLAIVE_TRIGGERS]
    gaps = sorted(b["timestamp"] - a["timestamp"] for a, b in zip(casts, casts[1:]))
    idle = sum(g - 1500 for g in gaps if g > 2500) / 1000  # rough: >2.5 s with no cast

    meta = []  # Metamorphosis buff windows
    start = None
    for e in buffs:
        if ab.get(e["abilityGameID"]) == "Metamorphosis":
            if e["type"] == "applybuff":
                start = e["timestamp"]
            elif e["type"] == "removebuff" and start is not None:
                meta.append((start, e["timestamp"]))
                start = None
    surges = sorted(dmg_names)
    surge_per_meta = [sum(a <= t <= b for t in surges) for a, b in meta]

    gained = sum(e["resourceChange"] for e in res)
    wasted = sum(e.get("waste", 0) for e in res)
    return {
        **{k: row[k] for k in ("content", "hero", "encounter", "rank", "name", "dps", "keyLevel", "report", "fightID")},
        "minutes": round(minutes, 2), "cpm": cpm,
        "gcd_casts_per_min": round(sum(n[k] for k in TRACK) / minutes, 1),
        "manual_throw_glaive": sum(not any(abs(e["timestamp"] - t) <= 50 for t in trig)
                                   for e in casts if e["abilityGameID"] == THROW_GLAIVE),
        "fury_at_meta": fury_at("Metamorphosis"), "fury_at_essence_break": fury_at("Essence Break"),
        "vr_paired_with_eye_beam": f"{vr_paired}/{len(vr)}",
        "idle_seconds_rough": round(idle, 1),
        "meta_windows": len(meta), "meta_avg_s": round(statistics.mean(b - a for a, b in meta) / 1000, 1) if meta else None,
        "demonsurge_per_meta": surge_per_meta,
        "fury_waste_pct": round(100 * wasted / gained, 1) if gained else None,
    }


def main(n=5):
    c = WCLClient()
    rows = json.load(open(os.path.join(DATA, "top_rankings.json")))
    picks = []
    for content in ("raid", "mplus"):
        for hero in ("AR", "FS"):
            pool = sorted((r for r in rows if r["content"] == content and r["hero"] == hero), key=lambda r: r["rank"])
            seen = set()
            for r in pool:  # best-ranked per encounter first, so the sample spans encounters
                if r["encounter"] not in seen and len(seen) < n:
                    seen.add(r["encounter"]); picks.append(r)
    out = []
    for r in picks:
        try:
            m = analyse(c, r)
        except Exception as e:  # keep going; private/expired reports happen
            print("skip", r["name"], r["report"], e); continue
        out.append(m)
        print(json.dumps(m, ensure_ascii=False))
    json.dump(out, open(os.path.join(DATA, "benchmarks.json"), "w"), ensure_ascii=False, indent=1)
    print(c.rate_limit())


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 5)
