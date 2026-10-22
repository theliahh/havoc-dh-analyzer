"""Source-neutral event model shared by the raw combat log and Warcraft Logs adapters."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# Normalized event types.
CAST = "cast"
DAMAGE = "damage"
AURA_APPLIED = "aura_applied"
AURA_REMOVED = "aura_removed"
AURA_REFRESH = "aura_refresh"
ENERGIZE = "energize"
DIED = "died"


@dataclass(slots=True)
class Event:
    t: float                 # seconds since fight start
    type: str                # one of the constants above
    src: str                 # source unit id (GUID for raw logs, "wcl:<actorID>" for WCL)
    dst: str                 # target unit id, "" when there is none
    spell_id: int = 0
    spell_name: str = ""
    fury: int | None = None  # caster's Fury at the time of a cast
    amount: float = 0.0      # damage dealt or resource gained


@dataclass
class Fight:
    kind: str                    # "encounter" or "mythic_plus"
    name: str
    zone: str
    difficulty: str
    duration: float = 0.0        # seconds
    success: bool | None = None
    encounter_id: int | None = None
    keystone_level: int | None = None
    in_key: bool = False         # a boss pull inside a Mythic+ key
    start: datetime | None = None
    events: list[Event] = field(default_factory=list)
    children: list["Fight"] = field(default_factory=list)   # boss pulls inside a key

    @property
    def content(self) -> str:
        return "mplus" if self.kind == "mythic_plus" or self.in_key else "raid"

    @property
    def label(self) -> str:
        if self.kind == "mythic_plus":
            return f"{self.name} +{self.keystone_level}"
        return f"{self.name} ({self.difficulty})"
