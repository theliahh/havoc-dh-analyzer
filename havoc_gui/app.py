"""Havoc Analyzer desktop window."""
from __future__ import annotations

import glob
import html
import os
import sys
from collections import Counter

from PySide6.QtCore import QFileSystemWatcher, QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QActionGroup, QFont, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QProgressBar, QScrollArea, QSizePolicy, QSplitter,
    QTableWidget, QTableWidgetItem, QTabWidget, QToolBar, QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from havoc_analyzer.report import FightResult, render_report
from havoc_analyzer.rules import FLAG, WARN, fmt

from . import theme
from .charts import Bar, BarChart, Series, StatTile, StatusDelegate, card
from .rules_tab import RulesPage
from .timeline import Timeline
from .workers import NO_HAVOC, LoadedLog, LogWorker, WclWorker

APP_NAME = "Havoc Analyzer"
STATUS_ROLE = Qt.UserRole + 1
THEME_LABEL = {"system": "Match system", "light": "Light", "dark": "Dark"}
DEFAULT_LOG_DIRS = [
    r"C:\Program Files (x86)\World of Warcraft\_retail_\Logs",
    r"C:\Program Files\World of Warcraft\_retail_\Logs",
    os.path.expanduser("~/Applications/World of Warcraft/_retail_/Logs"),
    "/Applications/World of Warcraft/_retail_/Logs",
]
WATCH_DEBOUNCE_MS = 20_000   # reload once the log has been quiet for 20 s


def newest_log(folder: str) -> str | None:
    logs = glob.glob(os.path.join(folder, "WoWCombatLog*.txt"))
    return max(logs, key=os.path.getmtime) if logs else None


class WclDialog(QDialog):
    def __init__(self, settings: QSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Load from Warcraft Logs")
        form = QFormLayout(self)
        self.url = QLineEdit(placeholderText="https://www.warcraftlogs.com/reports/…  (add #fight=N for one pull)")
        self.player = QLineEdit(settings.value("wcl/player", ""))
        self.client_id = QLineEdit(settings.value("wcl/client_id", "") or os.environ.get("WCL_CLIENT_ID", ""))
        self.secret = QLineEdit(settings.value("wcl/client_secret", "") or os.environ.get("WCL_CLIENT_SECRET", ""))
        self.secret.setEchoMode(QLineEdit.Password)
        self.url.setMinimumWidth(460)
        form.addRow("Report link or code", self.url)
        form.addRow("Character name", self.player)
        form.addRow("WCL client ID", self.client_id)
        form.addRow("WCL client secret", self.secret)
        form.addRow(QLabel("The client ID and secret are saved on this computer only, in your user settings."))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("HavocAnalyzer", "HavocAnalyzer")
        self.loaded: LoadedLog | None = None
        self.thread: QThread | None = None
        self.worker = None
        self.quiet_load = False             # set while a watched log loads: no pop-up if it has no Havoc yet
        self.watch_folder: str | None = None
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._log_changed)
        self.watcher.fileChanged.connect(self._log_changed)
        self.debounce = QTimer(self, singleShot=True, interval=WATCH_DEBOUNCE_MS)
        self.debounce.timeout.connect(self._reload_watched)

        self.setWindowTitle(APP_NAME)
        self.resize(1280, 800)
        self._build_toolbar()
        self._build_body()
        self._build_status()

    # UI construction

    def _build_toolbar(self) -> None:
        bar = QToolBar("Main", movable=False)
        self.addToolBar(bar)
        open_act = QAction("Open log…", self, shortcut=QKeySequence.Open, triggered=self.open_log)
        self.watch_act = QAction("Watch Logs folder", self, checkable=True, toggled=self.toggle_watch)
        wcl_act = QAction("From Warcraft Logs…", self, triggered=self.open_wcl)
        self.export_act = QAction("Export report…", self, enabled=False, triggered=self.export_report)
        for act in (open_act, self.watch_act, wcl_act, self.export_act):
            bar.addAction(act)
        bar.widgetForAction(open_act).setObjectName("primary")
        bar.addSeparator()
        bar.addWidget(QLabel(" Player "))
        self.player_box = QComboBox(minimumWidth=220, enabled=False)
        self.player_box.activated.connect(self._player_changed)
        bar.addWidget(self.player_box)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        menu = QMenu(self)
        group = QActionGroup(self, exclusive=True)
        mode = self.settings.value("theme", "system")
        for key, label in THEME_LABEL.items():
            act = QAction(label, self, checkable=True, checked=key == mode)
            act.triggered.connect(lambda _=False, k=key: self.set_theme(k))
            group.addAction(act)
            menu.addAction(act)
        self.theme_button = QToolButton(text="◐  Theme", popupMode=QToolButton.InstantPopup)
        self.theme_button.setMenu(menu)
        self.theme_button.setToolTip("Light, dark, or match Windows")
        bar.addWidget(self.theme_button)

    def _build_body(self) -> None:
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Fight", "Result", "Time", "Fix", "Check"])
        self.tree.headerItem().setToolTip(3, "Rules flagged as likely DPS lost")
        self.tree.headerItem().setToolTip(4, "Rules worth a look")
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(True)
        self.tree.currentItemChanged.connect(self._fight_selected)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        split.addWidget(self.tree)

        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(10)
        self.heading = QLabel("Open a combat log to start", objectName="title")
        self.subheading = QLabel("Use Open log, Watch Logs folder or From Warcraft Logs above.", objectName="secondary")
        self.subheading.setWordWrap(True)
        self.subheading.setTextFormat(Qt.RichText)
        layout.addWidget(self.heading)
        layout.addWidget(self.subheading)
        tiles = QHBoxLayout()
        tiles.setSpacing(10)
        self.tiles = [StatTile() for _ in range(5)]
        for tile in self.tiles:
            tile.setVisible(False)
            tiles.addWidget(tile)
        layout.addLayout(tiles)
        self.tabs = QTabWidget()
        self.findings = QTableWidget(0, 4)
        self.findings.setHorizontalHeaderLabels(["Status", "Rule", "Result", "Look at"])
        self.findings.setItemDelegateForColumn(0, StatusDelegate(self.findings))
        self.findings.setShowGrid(False)
        self.findings.verticalHeader().setVisible(False)
        self.findings.setEditTriggers(QTableWidget.NoEditTriggers)
        self.findings.setSelectionBehavior(QTableWidget.SelectRows)
        self.findings.setWordWrap(True)
        fh = self.findings.horizontalHeader()
        fh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        fh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        fh.setSectionResizeMode(2, QHeaderView.Stretch)
        fh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        fh.sectionResized.connect(lambda *_: self.findings.resizeRowsToContents())
        self.findings.itemDoubleClicked.connect(self._show_on_timeline)
        self.timeline = Timeline()
        self.charts_page = QWidget()
        self.charts_layout = QVBoxLayout(self.charts_page)
        self.charts_layout.setContentsMargins(12, 12, 12, 12)
        self.charts_layout.setSpacing(12)
        self.charts_layout.addStretch()
        scroll = QScrollArea(widgetResizable=True)
        scroll.setWidget(self.charts_page)
        self.tabs.addTab(self.findings, "Findings")
        self.tabs.addTab(self.timeline, "Timeline")
        self.tabs.addTab(scroll, "Casts and buffs")
        self.rules_page = RulesPage()
        self.tabs.addTab(self.rules_page, "Rules")
        layout.addWidget(self.tabs, 1)
        split.addWidget(right)
        split.setSizes([480, 800])
        body = QWidget()
        outer = QVBoxLayout(body)
        outer.setContentsMargins(12, 0, 12, 4)
        outer.addWidget(split)
        self.setCentralWidget(body)

    def _build_status(self) -> None:
        self.progress = QProgressBar(maximumWidth=260, visible=False, textVisible=False)
        self.statusBar().addPermanentWidget(self.progress)

    # Loading

    def open_log(self) -> None:
        start = self.settings.value("last_dir", "") or next((d for d in DEFAULT_LOG_DIRS if os.path.isdir(d)), "")
        path, _ = QFileDialog.getOpenFileName(self, "Open combat log", start, "Combat logs (WoWCombatLog*.txt *.txt)")
        if path:
            self.settings.setValue("last_dir", os.path.dirname(path))
            self.load_log(path)

    def load_log(self, path: str, player_guid: str | None = None, quiet: bool = False) -> None:
        self._start(LogWorker(path, player_guid or self.settings.value("player_guid")), os.path.basename(path), quiet)

    def open_wcl(self) -> None:
        dlg = WclDialog(self.settings, self)
        if dlg.exec() != QDialog.Accepted:
            return
        url, player = dlg.url.text().strip(), dlg.player.text().strip()
        cid, secret = dlg.client_id.text().strip(), dlg.secret.text().strip()
        if not (url and player and cid and secret):
            QMessageBox.warning(self, APP_NAME, "Fill in the report, character name, client ID and secret.")
            return
        self.settings.setValue("wcl/player", player)
        self.settings.setValue("wcl/client_id", cid)
        self.settings.setValue("wcl/client_secret", secret)
        self._start(WclWorker(url, player, cid, secret), "Warcraft Logs report")

    def _start(self, worker, label: str, quiet: bool = False) -> None:
        if self.thread is not None:
            self.statusBar().showMessage("Still loading the previous log…", 4000)
            return
        self.quiet_load = quiet
        self.thread = QThread(self)
        self.worker = worker
        worker.moveToThread(self.thread)
        self.thread.started.connect(worker.run)
        worker.progress.connect(self._progress)
        worker.done.connect(self._loaded)
        worker.failed.connect(self._failed)
        worker.done.connect(self.thread.quit)
        worker.failed.connect(self.thread.quit)
        self.thread.finished.connect(self._thread_done)
        self.progress.setVisible(True)
        self.progress.setValue(0)
        self.statusBar().showMessage(f"Loading {label}…")
        self.thread.start()

    def _thread_done(self) -> None:
        self.thread.deleteLater()
        self.thread = None
        self.worker = None
        self.progress.setVisible(False)

    def _progress(self, pct: int, msg: str) -> None:
        self.progress.setValue(pct)
        self.statusBar().showMessage(msg)

    def _failed(self, msg: str) -> None:
        if self.quiet_load and msg == NO_HAVOC:
            # Entering an instance starts a log before any Havoc combat: keep watching without a pop-up.
            self.statusBar().showMessage(f"Watching {self.watch_folder}. No Havoc Demon Hunter in the log yet.")
            return
        self.statusBar().clearMessage()
        QMessageBox.warning(self, APP_NAME, msg)

    def _loaded(self, log: LoadedLog) -> None:
        self.loaded = log
        self.export_act.setEnabled(True)
        self.statusBar().showMessage(f"{log.player_name}: {len(log.results)} fights from {os.path.basename(log.source)}", 8000)
        self.player_box.clear()
        for guid, name in log.havoc_players.items():
            self.player_box.addItem(name, guid)
            if name == log.player_name:
                self.player_box.setCurrentIndex(self.player_box.count() - 1)
        self.player_box.setEnabled(len(log.havoc_players) > 1)
        self._fill_tree()

    def _player_changed(self, index: int) -> None:
        guid = self.player_box.itemData(index)
        if self.loaded and guid and os.path.isfile(self.loaded.source):
            self.settings.setValue("player_guid", guid)
            self.load_log(self.loaded.source, guid)

    # Folder watching

    def toggle_watch(self, on: bool) -> None:
        if not on:
            self.watcher.removePaths(self.watcher.directories() + self.watcher.files())
            self.watch_folder = None
            self.statusBar().showMessage("Stopped watching.", 4000)
            return
        start = self.settings.value("watch_dir", "") or next((d for d in DEFAULT_LOG_DIRS if os.path.isdir(d)), "")
        folder = QFileDialog.getExistingDirectory(self, "World of Warcraft Logs folder", start)
        if not folder:
            self.watch_act.setChecked(False)
            return
        self.settings.setValue("watch_dir", folder)
        self.watch_folder = folder
        self.watcher.addPath(folder)
        latest = newest_log(folder)
        if latest:
            self.watcher.addPath(latest)
            self.load_log(latest, quiet=True)
        self.statusBar().showMessage(f"Watching {folder}. New pulls load about 20 s after the log goes quiet.", 8000)

    def _log_changed(self, _path: str) -> None:
        if self.watch_folder:
            self.debounce.start()

    def _reload_watched(self) -> None:
        latest = newest_log(self.watch_folder) if self.watch_folder else None
        if not latest:
            return
        if latest not in self.watcher.files():
            self.watcher.addPath(latest)
        self.load_log(latest, quiet=True)

    # Display

    def _fill_tree(self) -> None:
        t = theme.current()
        current = self.tree.currentItem()
        keep = current.data(0, Qt.UserRole) if current else None
        self.tree.clear()
        log = self.loaded
        overview = QTreeWidgetItem(["Overview of all fights", "", "", "", ""])
        overview.setData(0, Qt.UserRole, None)
        font = overview.font(0)
        font.setWeight(QFont.DemiBold)
        overview.setFont(0, font)
        self.tree.addTopLevelItem(overview)
        parents = {}
        select = overview
        for result in log.results:
            f = result.fight
            flags = sum(x.status == FLAG for x in result.findings)
            warns = sum(x.status == WARN for x in result.findings)
            outcome = {True: "Kill" if f.kind == "encounter" else "Timed", False: "Wipe" if f.kind == "encounter"
                       else "Depleted", None: "?"}[f.success]
            item = QTreeWidgetItem([f.label, outcome, fmt(f.duration), str(flags), str(warns)])
            item.setData(0, Qt.UserRole, result)
            item.setForeground(1, t.status_color("ok") if f.success else t.color("muted"))
            for col, count, status in ((3, flags, FLAG), (4, warns, WARN)):
                item.setForeground(col, t.status_color(status) if count else t.color("muted"))
                item.setTextAlignment(col, Qt.AlignCenter)
                if count:
                    bold = item.font(col)
                    bold.setWeight(QFont.Bold)
                    item.setFont(col, bold)
            item.setForeground(2, t.color("text2"))
            if result is keep:
                select = item
            if f.kind == "mythic_plus":
                parents[id(f)] = item
                self.tree.addTopLevelItem(item)
            elif f.in_key:
                parent = next((parents[id(k)] for k in (r.fight for r in log.results)
                               if k.kind == "mythic_plus" and f in k.children), None)
                (parent.addChild(item) if parent else self.tree.addTopLevelItem(item))
            else:
                self.tree.addTopLevelItem(item)
        self.tree.expandAll()
        self.tree.setCurrentItem(select)

    def _fight_selected(self, item, _prev) -> None:
        if item is None or not self.loaded:
            return
        result: FightResult | None = item.data(0, Qt.UserRole)
        if result is None:
            self._show_overview()
        else:
            self._show_fight(result)

    def _set_tiles(self, tiles: list[tuple[str, str, str | None]]) -> None:
        for tile, spec in zip(self.tiles, tiles + [None] * len(self.tiles)):
            tile.setVisible(spec is not None)
            if spec:
                tile.set(*spec)

    def _show_overview(self) -> None:
        log = self.loaded
        t = theme.current()
        results = log.results
        self.heading.setText(log.player_name)
        self.subheading.setText(f"{len(results)} fights. Rules that came up most often across fights are listed first.")
        counts: dict[str, list[int]] = {}
        titles = {}
        for r in results:
            for f in r.findings:
                titles[f.rule] = f"{f.rule} {f.title}"
                c = counts.setdefault(f.rule, [0, 0])
                c[0] += f.status == FLAG
                c[1] += f.status == WARN
        rows = sorted((r for r in counts if sum(counts[r])), key=lambda r: (-counts[r][0], -counts[r][1]))
        kills = sum(r.fight.success is True for r in results)
        dps = [r.summary.dps for r in results if r.summary.duration > 0]
        self._set_tiles([
            (str(len(results)), f"fights · {kills} kills or timed", None),
            (f"{max(dps):,.0f}" if dps else "–", "best DPS", None),
            (str(sum(c[0] for c in counts.values())), "fixes across fights", t.status[FLAG]),
            (str(sum(c[1] for c in counts.values())), "checks across fights", t.status[WARN]),
        ])
        self.findings.setRowCount(0)
        self.findings.setHorizontalHeaderLabels(["Status", "Rule", "Fights flagged / warned", ""])
        for rule in rows:
            flags, warns = counts[rule]
            status = FLAG if flags else WARN
            self._add_row(status, titles[rule], f"Fix in {flags} · check in {warns}", "", None)
        self.timeline.set_result(None)
        trees = Counter(r.summary.hero_tree for r in results)
        self.rules_page.set_detected(trees.most_common(1)[0][0] if trees else None)
        self._set_charts([self._dps_chart(results), self._rules_chart(rows, counts, titles)])
        self.tabs.setTabText(2, "Charts")
        if self.tabs.currentWidget() is not self.rules_page:
            self.tabs.setCurrentWidget(self.findings)

    def _show_fight(self, r: FightResult) -> None:
        s = r.summary
        t = theme.current()
        self.heading.setText(s.label)
        deaths = f" · died at {', '.join(fmt(d) for d in s.deaths)}" if s.deaths else ""
        self.subheading.setText(f"<b>{html.escape(s.hero_tree)}</b>{deaths} · Findings {html.escape(r.bench_note)}. "
                                "Double-click a row to see it on the timeline.")
        flags = sum(f.status == FLAG for f in r.findings)
        warns = sum(f.status == WARN for f in r.findings)
        outcome = {True: "Kill" if r.fight.kind == "encounter" else "Timed", False: "Wipe" if r.fight.kind == "encounter"
                   else "Depleted", None: "?"}[s.success]
        self._set_tiles([
            (f"{s.dps:,.0f}", "DPS", None),
            (f"{s.cpm:.1f}", "abilities per minute", None),
            (fmt(s.duration), outcome, t.status["ok"] if s.success else None),
            (str(flags), "to fix", t.status[FLAG] if flags else None),
            (str(warns), "to check", t.status[WARN] if warns else None),
        ])
        self.findings.setRowCount(0)
        self.findings.setHorizontalHeaderLabels(["Status", "Rule", "Result", "Look at"])
        for f in r.findings:
            when = ", ".join(fmt(x) for x in f.times[:8]) + (" …" if len(f.times) > 8 else "")
            self._add_row(f.status, f"{f.rule} {f.title} ({f.severity})", f.detail, when, (r, f.times))
        self.timeline.set_result(r)
        self.rules_page.set_detected(s.hero_tree)
        self._set_charts(self._fight_charts(r))
        self.tabs.setTabText(2, "Casts and buffs")

    def _add_row(self, status: str, rule: str, detail: str, when: str, payload) -> None:
        t = theme.current()
        row = self.findings.rowCount()
        self.findings.insertRow(row)
        for col, text in enumerate(["", rule, detail, when]):
            cell = QTableWidgetItem(text)
            cell.setData(Qt.UserRole, payload)
            cell.setData(STATUS_ROLE, status)
            if status in (FLAG, WARN):
                cell.setBackground(t.status_color(status, 22))
            if col == 3:
                cell.setForeground(t.color("text2"))
            self.findings.setItem(row, col, cell)
        self.findings.resizeRowToContents(row)

    def _show_on_timeline(self, item: QTableWidgetItem) -> None:
        payload = item.data(Qt.UserRole)
        if payload:
            result, times = payload
            self.timeline.set_result(result, times)
            self.tabs.setCurrentWidget(self.timeline)

    # Charts

    def _set_charts(self, charts: list[BarChart]) -> None:
        while self.charts_layout.count() > 1:
            w = self.charts_layout.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        for i, chart in enumerate(charts):
            self.charts_layout.insertWidget(i, card(chart))

    @staticmethod
    def _fight_charts(r: FightResult) -> list[BarChart]:
        s = r.summary
        damage = BarChart("Damage by ability")
        damage.set_data([Bar(n, [(d, "accent")], f"{d / max(s.damage, 1):.0%}",
                             f"{n}: {d:,.0f} damage ({d / max(s.damage, 1):.1%})")
                         for n, d in s.damage_by_ability])
        buffs = BarChart("Buff uptime")
        buffs.set_data([Bar(n, [(u, "accent")], f"{u:.0%}") for n, u in s.buff_uptime.items()], max_value=1.0)
        casts = BarChart("Pressed casts")
        bars = []
        for name, count in s.casts.most_common():
            gap = s.longest_gap.get(name)
            note = f"longest gap {fmt(gap)}" if gap is not None else ""
            bars.append(Bar(name, [(count, "accent")], str(count), f"{name}: {count} casts" + (f", {note}" if note else ""),
                            note))
        casts.set_data(bars)
        return [damage, buffs, casts]

    @staticmethod
    def _dps_chart(results: list[FightResult]) -> BarChart:
        chart = BarChart("DPS per fight")
        chart.set_data([Bar(r.summary.label, [(r.summary.dps, "accent")], f"{r.summary.dps:,.0f}",
                            f"{r.summary.label}: {r.summary.dps:,.0f} DPS over {fmt(r.summary.duration)}")
                        for r in results])
        return chart

    @staticmethod
    def _rules_chart(rows: list[str], counts: dict[str, list[int]], titles: dict[str, str]) -> BarChart:
        chart = BarChart("Rules that came up")
        chart.set_data([Bar(titles[r], [(counts[r][0], f"status:{FLAG}"), (counts[r][1], f"status:{WARN}")],
                            f"{counts[r][0]} / {counts[r][1]}",
                            f"{titles[r]}: fix in {counts[r][0]} fights, check in {counts[r][1]}")
                        for r in rows],
                       [Series("Fix", f"status:{FLAG}"), Series("Check", f"status:{WARN}")])
        return chart

    # Theme

    def set_theme(self, mode: str) -> None:
        self.settings.setValue("theme", mode)
        theme.apply(QApplication.instance(), mode)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Repaint the parts that bake theme colors into items."""
        if self.loaded:
            self._fill_tree()
        self.timeline.update()

    def export_report(self) -> None:
        if not self.loaded:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export report", "havoc-report.md", "Markdown (*.md)")
        if path:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(render_report(self.loaded.player_name, self.loaded.build, self.loaded.results))
            self.statusBar().showMessage(f"Saved {path}", 6000)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 10))
    theme.apply(app, QSettings("HavocAnalyzer", "HavocAnalyzer").value("theme", "system"))
    win = MainWindow()

    def follow_system(*_):
        if win.settings.value("theme", "system") == "system":
            win.set_theme("system")
    if hasattr(app.styleHints(), "colorSchemeChanged"):
        app.styleHints().colorSchemeChanged.connect(follow_system)
    win.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.load_log(sys.argv[1])
    sys.exit(app.exec())
