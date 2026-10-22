"""Top-player benchmarks, read from wcl/data/benchmarks.json (built by wcl/benchmarks.py)."""
from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass, field

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "wcl", "data", "benchmarks.json")
HERO_CODES = {"Aldrachi Reaver": "AR", "Fel-Scarred": "FS"}


@dataclass
class Benchmark:
    content: str                      # "raid" or "mplus"
    hero: str                         # "AR" or "FS"
    logs: int
    cpm: dict[str, float] = field(default_factory=dict)
    fury_at_meta: float | None = None
    fury_at_essence_break: float | None = None
    idle_per_min: float | None = None


def _median(values):
    values = [v for v in values if v is not None]
    return statistics.median(values) if values else None


def load(path: str = DEFAULT_PATH) -> dict[tuple[str, str], Benchmark]:
    """Median metrics per (content, hero code). Empty if the file is missing."""
    try:
        with open(path, encoding="utf-8") as fh:
            rows = json.load(fh)
    except FileNotFoundError:
        return {}
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        groups.setdefault((r["content"], r["hero"]), []).append(r)
    out = {}
    for (content, hero), rs in groups.items():
        abilities = {a for r in rs for a in r.get("cpm", {})}
        out[(content, hero)] = Benchmark(
            content, hero, len(rs),
            # A log that never cast an ability counts as 0 casts per minute.
            cpm={a: statistics.median(r.get("cpm", {}).get(a, 0.0) for r in rs) for a in abilities},
            fury_at_meta=_median(r.get("fury_at_meta") for r in rs),
            fury_at_essence_break=_median(r.get("fury_at_essence_break") for r in rs),
            idle_per_min=_median(r["idle_seconds_rough"] / r["minutes"] for r in rs
                                 if r.get("idle_seconds_rough") is not None and r.get("minutes")),
        )
    return out


def lookup(table: dict[tuple[str, str], Benchmark], content: str, hero_tree: str) -> Benchmark | None:
    hero = HERO_CODES.get(hero_tree)
    return table.get((content, hero)) if hero else None
