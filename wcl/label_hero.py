"""Label hero tree for top rankings by looking for signature abilities, then find
talent IDs that separate the two trees so later rankings can be labelled for free.
"""
import collections
import json
import os
import random

from wcl_client import WCLClient

DATA = os.path.join(os.path.dirname(__file__), "data")
SIG = {"Reaver's Glaive": "AR", "Art of the Glaive": "AR",
       "Demonsurge": "FS", "Abyssal Gaze": "FS", "Consuming Fire": "FS"}


def label(c, row):
    name = row["name"].replace('"', '\\"')
    names = ",".join(f'"{n}"' for n in SIG).replace("'", "\\'")
    flt = f'source.name = "{name}" and ability.name in ({names})'
    hits = collections.Counter()
    for e in c.events(row["report"], row["fightID"], filter=flt):
        hits[e["abilityGameID"]] += 1
        if sum(hits.values()) > 50:
            break
    return hits


def main(n=24, seed=1):
    c = WCLClient()
    rows = json.load(open(os.path.join(DATA, "top_rankings.json")))
    ab_names = {}
    random.seed(seed)
    sample = random.sample(rows, n)
    for r in sample:
        hits = label(c, r)
        if not ab_names.get(r["report"]):
            ab_names[r["report"]] = c.abilities(r["report"])
        names = {ab_names[r["report"]].get(a, a): k for a, k in hits.items()}
        trees = {SIG.get(n) for n in names} - {None}
        r["hero"] = trees.pop() if len(trees) == 1 else ("mixed" if trees else "unknown")
        print(r["content"], r["encounter"], r["name"], r["hero"], names)
    json.dump(sample, open(os.path.join(DATA, "labelled_sample.json"), "w"))
    print(c.rate_limit())


if __name__ == "__main__":
    main()
