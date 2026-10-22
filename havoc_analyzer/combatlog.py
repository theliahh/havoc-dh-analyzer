"""Streaming parser for raw WoWCombatLog.txt files (COMBAT_LOG_VERSION 22, advanced logging).

Splits a log into fights (raid boss pulls and Mythic+ keys) and keeps only the
events that involve one player, so a 500+ MB log can be read in one pass.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterator

Progress = Callable[[float], None]   # called with the fraction of the file read, 0..1

from . import events as ev
from .events import Event, Fight

HAVOC_SPEC_ID = 577
FURY_POWER_TYPE = "17"

# Field positions after splitting a line's CSV body (index 0 is the event name).
# Advanced logging adds 19 fields after the spell prefix in v22 logs.
SRC_GUID, SRC_NAME, DST_GUID, DST_NAME = 1, 2, 5, 6
SPELL_ID, SPELL_NAME = 9, 10
ADV_START = 12
ADV_POWER_TYPE, ADV_CUR_POWER = ADV_START + 10, ADV_START + 11
SUFFIX_START = ADV_START + 19
SWING_AMOUNT = SUFFIX_START - 3   # swings have no 3-field spell prefix
NO_UNIT = "0000000000000000"

DIFFICULTY_NAMES = {14: "Normal", 15: "Heroic", 16: "Mythic", 17: "LFR", 8: "Mythic+", 23: "Mythic"}

SPELL_DAMAGE_EVENTS = {"SPELL_DAMAGE", "SPELL_PERIODIC_DAMAGE", "RANGE_DAMAGE"}
AURA_EVENTS = {"SPELL_AURA_APPLIED": ev.AURA_APPLIED, "SPELL_AURA_REMOVED": ev.AURA_REMOVED,
               "SPELL_AURA_REFRESH": ev.AURA_REFRESH}


def split_fields(body: str) -> list[str]:
    """Split a combat log CSV body, respecting quotes and (), [] nesting."""
    out, cur, depth, quoted = [], [], 0, False
    for ch in body:
        if quoted:
            if ch == '"':
                quoted = False
            else:
                cur.append(ch)
        elif ch == '"':
            quoted = True
        elif ch in "([":
            depth += 1
            cur.append(ch)
        elif ch in ")]":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out


def split_simple(body: str) -> list[str]:
    """Fast path for event lines without quotes or nested brackets."""
    if '"' in body or "[" in body or "(" in body:
        return split_fields(body)
    return body.split(",")


def parse_timestamp(stamp: str) -> datetime:
    """Parse '10/21/2026 19:59:20.878-4' into an aware datetime."""
    date_part, time_part = stamp.split(" ")
    sign_at = max(time_part.rfind("-"), time_part.rfind("+"))
    clock, offset = time_part[:sign_at], int(time_part[sign_at:])
    month, day, year = (int(x) for x in date_part.split("/"))
    hms, _, frac = clock.partition(".")
    hh, mm, ss = (int(x) for x in hms.split(":"))
    micro = int((frac + "000000")[:6]) if frac else 0
    return datetime(year, month, day, hh, mm, ss, micro, tzinfo=timezone(timedelta(hours=offset)))


def _fury(f: list[str]) -> int | None:
    if len(f) <= ADV_CUR_POWER:
        return None
    for ptype, value in zip(f[ADV_POWER_TYPE].split("|"), f[ADV_CUR_POWER].split("|")):
        if ptype == FURY_POWER_TYPE:
            return int(value)
    return None


def to_event(t: float, f: list[str]) -> Event | None:
    """Map one split log line to a normalized Event, or None if it's not one we use."""
    name = f[0]
    dst = "" if f[DST_GUID] == NO_UNIT else f[DST_GUID]
    if name == "SPELL_CAST_SUCCESS":
        return Event(t, ev.CAST, f[SRC_GUID], dst, int(f[SPELL_ID]), f[SPELL_NAME], fury=_fury(f))
    if name in SPELL_DAMAGE_EVENTS:
        return Event(t, ev.DAMAGE, f[SRC_GUID], dst, int(f[SPELL_ID]), f[SPELL_NAME],
                     amount=float(f[SUFFIX_START]))
    if name == "SWING_DAMAGE":
        return Event(t, ev.DAMAGE, f[SRC_GUID], dst, 1, "Melee", amount=float(f[SWING_AMOUNT]))
    if name in AURA_EVENTS:
        return Event(t, AURA_EVENTS[name], f[SRC_GUID], dst, int(f[SPELL_ID]), f[SPELL_NAME])
    if name == "SPELL_ENERGIZE":
        return Event(t, ev.ENERGIZE, f[SRC_GUID], dst, int(f[SPELL_ID]), f[SPELL_NAME],
                     amount=float(f[SUFFIX_START]))
    if name == "UNIT_DIED":
        return Event(t, ev.DIED, "", dst)
    return None


@dataclass
class Combatant:
    guid: str
    name: str
    spec_id: int
    talent_entries: list[tuple[int, int, int]]


@dataclass
class ParsedLog:
    build: str | None
    player: Combatant | None
    fights: list[Fight]


def _parse_talents(raw: str) -> list[tuple[int, int, int]]:
    out = []
    for chunk in raw.strip("[]").split("),("):
        parts = chunk.strip("()").split(",")
        if len(parts) == 3 and all(p.strip().lstrip("-").isdigit() for p in parts):
            out.append(tuple(int(p) for p in parts))
    return out


def iter_lines(path: str, progress: Progress | None = None) -> Iterator[tuple[str, str]]:
    size = os.path.getsize(path) or 1
    read = 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh):
            if progress is not None:
                read += len(line)
                if n % 50000 == 0:
                    progress(min(read / size, 1.0))
            stamp, sep, body = line.rstrip("\n").partition("  ")
            if sep:
                yield stamp, body


def find_havoc_players(path: str, progress: Progress | None = None) -> dict[str, str]:
    """Return {guid: name} for every Havoc DH in the log."""
    specs: dict[str, int] = {}
    names: dict[str, str] = {}
    for _, body in iter_lines(path, progress):
        if body.startswith("COMBATANT_INFO,"):
            f = split_fields(body)
            specs[f[1]] = int(f[25])
        elif body.startswith("SPELL_CAST_SUCCESS,Player-"):
            guid, rest = body[19:].split(",", 1)
            if guid not in names:
                names[guid] = rest.split(",", 1)[0].strip('"')
    return {g: names.get(g, g) for g, s in specs.items() if s == HAVOC_SPEC_ID}


def parse(path: str, player_guid: str | None = None, progress: Progress | None = None) -> ParsedLog:
    """Parse a log into fights holding only events where the player is source or target.

    If player_guid is None, the first Havoc Demon Hunter found is used.
    """
    if player_guid is None:
        havocs = find_havoc_players(path)
        if not havocs:
            raise ValueError("No Havoc Demon Hunter found in this log.")
        player_guid = next(iter(havocs))

    build = None
    zone = ""
    player: Combatant | None = None
    fights: list[Fight] = []
    key: Fight | None = None
    boss: Fight | None = None

    def close(fight: Fight, stamp: str) -> None:
        fight.duration = (parse_timestamp(stamp) - fight.start).total_seconds()

    for stamp, body in iter_lines(path, progress):
        if body.startswith(("ENCOUNTER_", "CHALLENGE_MODE_", "ZONE_CHANGE", "COMBAT_LOG_VERSION", "COMBATANT_INFO")):
            f = split_fields(body)
            event = f[0]
            if event == "COMBAT_LOG_VERSION":
                build = f[f.index("BUILD_VERSION") + 1] if "BUILD_VERSION" in f else None
            elif event == "ZONE_CHANGE":
                zone = f[2]
            elif event == "COMBATANT_INFO" and f[1] == player_guid and player is None:
                player = Combatant(player_guid, "", int(f[25]), _parse_talents(f[26]))
            elif event == "CHALLENGE_MODE_START":
                key = Fight("mythic_plus", f[1], f[1], "Mythic+", start=parse_timestamp(stamp),
                            keystone_level=int(f[4]))
                fights.append(key)
            elif event == "CHALLENGE_MODE_END" and key is not None:
                close(key, stamp)
                key.success = f[2] == "1"
                key = None
            elif event == "ENCOUNTER_START":
                diff = int(f[3])
                boss = Fight("encounter", f[2], zone, DIFFICULTY_NAMES.get(diff, str(diff)),
                             start=parse_timestamp(stamp), encounter_id=int(f[1]), in_key=key is not None)
                (key.children if key else fights).append(boss)
            elif event == "ENCOUNTER_END" and boss is not None:
                close(boss, stamp)
                boss.success = f[5] == "1"
                # Drop instant resets (pulls under 5 s, e.g. wipe-and-reset blips).
                if boss.duration < 5:
                    (key.children if key else fights).remove(boss)
                boss = None
            continue

        if (key is None and boss is None) or player_guid not in body:
            continue
        f = split_simple(body)
        if len(f) < 9 or (f[SRC_GUID] != player_guid and f[DST_GUID] != player_guid):
            continue
        if player is not None and not player.name and f[SRC_GUID] == player_guid:
            player.name = f[SRC_NAME]
        now = parse_timestamp(stamp)
        for fight in (key, boss):
            if fight is not None:
                e = to_event((now - fight.start).total_seconds(), f)
                if e is not None:
                    fight.events.append(e)

    return ParsedLog(build, player, fights)
