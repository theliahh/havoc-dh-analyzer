"""Fetch top Havoc DH rankings (raid: current mythic tier; M+: current season) with talents.

Writes data/top_rankings.json. Usage: python3 fetch_top.py
"""
import json
import os

from hero_tree import from_talents
from wcl_client import WCLClient

RAID_ZONE = 53   # The Venomous Abyss
MPLUS_ZONE = 55  # Midnight Mythic+ Season 2
OUT = os.path.join(os.path.dirname(__file__), "data", "top_rankings.json")

Q = """query($e:Int!,$d:Int){ worldData{ encounter(id:$e){ name
  characterRankings(className:"DemonHunter", specName:"Havoc", difficulty:$d, metric:dps, includeCombatantInfo:true) } } }"""


def zone_encounters(c, zone_id):
    q = "query($z:Int!){ worldData{ zone(id:$z){ name encounters{ id name } } } }"
    return c.query(q, {"z": zone_id})["worldData"]["zone"]["encounters"]


def main():
    c = WCLClient()
    out = []
    for content, zone, diff in (("raid", RAID_ZONE, 5), ("mplus", MPLUS_ZONE, None)):
        for enc in zone_encounters(c, zone):
            r = c.query(Q, {"e": enc["id"], "d": diff})["worldData"]["encounter"]["characterRankings"]
            for rank, x in enumerate(r.get("rankings", []), 1):
                out.append({
                    "content": content, "encounterID": enc["id"], "encounter": enc["name"], "rank": rank,
                    "name": x["name"], "server": (x.get("server") or {}).get("name"), "region": (x.get("server") or {}).get("region"),
                    "dps": round(x["amount"]), "duration_ms": x["duration"],
                    "keyLevel": x.get("hardModeLevel") if content == "mplus" else None,
                    "report": x["report"]["code"], "fightID": x["report"]["fightID"],
                    "talents": sorted(t["talentID"] for t in x.get("talents", [])),
                    "hero": from_talents(t["talentID"] for t in x.get("talents", [])),
                })
            print(content, enc["name"], len(r.get("rankings", [])))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"))
    print("rate limit:", c.rate_limit())


if __name__ == "__main__":
    main()
