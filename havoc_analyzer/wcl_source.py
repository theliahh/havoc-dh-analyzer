"""Warcraft Logs adapter: one WCL fight into the same Fight/Event model as the raw parser.

`client` is a wcl.wcl_client.WCLClient (anything with the same query/events/
fight/abilities methods works). Usage:

    from wcl.wcl_client import WCLClient
    fight, player = load_fight(WCLClient(), "nFqaRZJAYj7gfVbx", 42, "Mortex")
"""
from __future__ import annotations

from . import events as ev
from .events import Event, Fight

FURY = 17
DIFFICULTY_NAMES = {1: "LFR", 3: "Normal", 4: "Heroic", 5: "Mythic", 10: "Mythic+"}
TYPE_MAP = {
    "cast": ev.CAST, "damage": ev.DAMAGE,
    "applybuff": ev.AURA_APPLIED, "removebuff": ev.AURA_REMOVED, "refreshbuff": ev.AURA_REFRESH,
    "applydebuff": ev.AURA_APPLIED, "removedebuff": ev.AURA_REMOVED, "refreshdebuff": ev.AURA_REFRESH,
    "resourcechange": ev.ENERGIZE, "death": ev.DIED,
}
ACTORS_QUERY = 'query($c:String!){ reportData{ report(code:$c){ masterData{ actors(type:"Player"){ id name } } } } }'


def unit(actor_id) -> str:
    return f"wcl:{actor_id}" if actor_id not in (None, -1) else ""


def to_event(raw: dict, start_ms: float, names: dict[int, str]) -> Event | None:
    kind = TYPE_MAP.get(raw.get("type"))
    if kind is None:
        return None
    spell = raw.get("abilityGameID", 0)
    fury = next((r["amount"] for r in raw.get("classResources", []) if r.get("type") == FURY), None)
    if kind == ev.DAMAGE:
        amount = raw.get("amount", 0)   # excludes absorbed, like the raw log's amount field
    elif kind == ev.ENERGIZE:
        if raw.get("resourceChangeType") != FURY:
            return None
        amount = raw.get("resourceChange", 0)
    else:
        amount = 0
    name = "Melee" if spell == 1 else names.get(spell, str(spell))
    return Event((raw["timestamp"] - start_ms) / 1000, kind, unit(raw.get("sourceID")),
                 unit(raw.get("targetID")), spell, name, fury=fury, amount=amount)


def load_fight(client, code: str, fight_id: int, player_name: str) -> tuple[Fight, str]:
    """Fetch one player's events for one fight. Returns (fight, player unit id)."""
    actors = client.query(ACTORS_QUERY, {"c": code})["reportData"]["report"]["masterData"]["actors"]
    actor = next((a["id"] for a in actors if a["name"] == player_name), None)
    if actor is None:
        raise ValueError(f"{player_name} is not in report {code}.")
    meta = client.fight(code, fight_id)
    names = client.abilities(code)
    start, end = meta["startTime"], meta["endTime"]
    key_level = meta.get("keystoneLevel")
    is_key = bool(key_level) and not meta.get("encounterID")
    fight = Fight(
        kind="mythic_plus" if is_key else "encounter",
        name=meta["name"], zone="",
        difficulty="Mythic+" if key_level else DIFFICULTY_NAMES.get(meta.get("difficulty"), str(meta.get("difficulty"))),
        duration=(end - start) / 1000,
        success=meta.get("kill"),
        encounter_id=meta.get("encounterID") or None,
        keystone_level=key_level,
        in_key=bool(key_level) and not is_key,
    )
    span = dict(start=start, end=end)
    seen = set()
    # Casts (with Fury), own buffs, damage done and Fury changes; deaths come with "All".
    for data_type, kwargs in (("Casts", {"include_resources": True}), ("Buffs", {}), ("DamageDone", {}),
                              ("Resources", {}), ("Deaths", {})):
        for raw in client.events(code, fight_id, source_id=None if data_type == "Deaths" else actor,
                                 data_type=data_type, **kwargs, **span):
            key = (raw.get("timestamp"), raw.get("type"), raw.get("abilityGameID"), raw.get("targetID"),
                   raw.get("sourceID"), raw.get("amount"))
            if key in seen:
                continue
            seen.add(key)
            e = to_event(raw, start, names)
            if e is not None and (e.src == unit(actor) or e.dst == unit(actor)):
                fight.events.append(e)
    fight.events.sort(key=lambda e: e.t)
    return fight, unit(actor)
