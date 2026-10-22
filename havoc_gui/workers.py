"""Background loading so the window stays responsive while a 500 MB log is read."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from havoc_analyzer import benchmarks
from havoc_analyzer.combatlog import find_havoc_players, parse
from havoc_analyzer.report import FightResult, analyze_fights


@dataclass
class LoadedLog:
    source: str                     # file path or WCL report code
    player_name: str
    build: str | None
    results: list[FightResult]
    havoc_players: dict[str, str]   # guid -> name, for the player picker


class LogWorker(QObject):
    """Parse a raw combat log and run the rules. Use with QThread."""
    progress = Signal(int, str)     # percent, message
    done = Signal(object)           # LoadedLog
    failed = Signal(str)

    def __init__(self, path: str, player_guid: str | None = None):
        super().__init__()
        self.path = path
        self.player_guid = player_guid

    def run(self) -> None:
        try:
            self.progress.emit(0, "Finding Havoc Demon Hunters…")
            havocs = find_havoc_players(self.path, lambda f: self.progress.emit(int(f * 30), "Finding Havoc Demon Hunters…"))
            if not havocs:
                raise ValueError("No Havoc Demon Hunter found in this log. Is Advanced Combat Logging on?")
            guid = self.player_guid if self.player_guid in havocs else next(iter(havocs))
            log = parse(self.path, guid, lambda f: self.progress.emit(30 + int(f * 65), "Reading fights…"))
            self.progress.emit(97, "Checking rules…")
            results = analyze_fights(log.fights, guid, benchmarks.load())
            name = log.player.name if log.player and log.player.name else havocs[guid]
            self.done.emit(LoadedLog(self.path, name, log.build, results, havocs))
        except Exception as e:  # shown to the user, not raised in the thread
            self.failed.emit(str(e))


class WclWorker(QObject):
    """Load fights for one player from a Warcraft Logs report."""
    progress = Signal(int, str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, url: str, player_name: str, client_id: str, client_secret: str):
        super().__init__()
        self.url, self.player_name = url, player_name
        self.client_id, self.client_secret = client_id, client_secret

    def run(self) -> None:
        try:
            from havoc_analyzer.wcl_source import list_fights, load_fight, parse_report_url
            from wcl.wcl_client import WCLClient

            client = WCLClient(self.client_id, self.client_secret)
            code, fight_id = parse_report_url(self.url)
            ids = [fight_id] if fight_id else [f["id"] for f in list_fights(client, code)]
            if not ids:
                raise ValueError("No boss pulls or keys in that report.")
            fights, unit = [], None
            for i, fid in enumerate(ids):
                self.progress.emit(int(i / len(ids) * 95), f"Loading fight {i + 1} of {len(ids)}…")
                fight, unit = load_fight(client, code, fid, self.player_name)
                if any(e.src == unit for e in fight.events):   # skip pulls the player wasn't in
                    fights.append(fight)
            if not fights:
                raise ValueError(f"{self.player_name} has no events in that report.")
            results = analyze_fights(fights, unit, benchmarks.load())
            self.done.emit(LoadedLog(code, self.player_name, None, results, {}))
        except Exception as e:
            self.failed.emit(str(e))
