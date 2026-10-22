"""Havoc Analyzer desktop window."""
from __future__ import annotations

import glob
import html
import os
import sys

from PySide6.QtCore import QFileSystemWatcher, QSettings, Qt, QThread, QTimer
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHeaderView, QLabel,
    QLineEdit, QMainWindow, QMessageBox, QProgressBar, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextBrowser, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from havoc_analyzer.report import FightResult, render_overview, render_report
from havoc_analyzer.rules import FLAG, INFO, OK, WARN, fmt

from .timeline import Timeline
from .workers import LoadedLog, LogWorker, WclWorker

APP_NAME = "Havoc Analyzer"
STATUS_TEXT = {FLAG: "🔴", WARN: "🟡", OK: "🟢", INFO: "⚪"}
STATUS_TINT = {FLAG: QColor(220, 60, 60, 45), WARN: QColor(225, 170, 30, 45)}
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
        bar.addSeparator()
        bar.addWidget(QLabel(" Player: "))
        self.player_box = QComboBox(minimumWidth=200, enabled=False)
        self.player_box.activated.connect(self._player_changed)
        bar.addWidget(self.player_box)

    def _build_body(self) -> None:
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Fight", "Result", "Time", "🔴", "🟡"])
        self.tree.setRootIsDecorated(True)
        self.tree.currentItemChanged.connect(self._fight_selected)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        split.addWidget(self.tree)

        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(8, 0, 0, 0)
        self.heading = QLabel("Open a combat log to start.")
        self.heading.setTextFormat(Qt.RichText)
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        self.tabs = QTabWidget()
        self.findings = QTableWidget(0, 4)
        self.findings.setHorizontalHeaderLabels(["", "Rule", "Result", "Look at"])
        self.findings.verticalHeader().setVisible(False)
        self.findings.setEditTriggers(QTableWidget.NoEditTriggers)
        self.findings.setSelectionBehavior(QTableWidget.SelectRows)
        self.findings.setWordWrap(True)
        fh = self.findings.horizontalHeader()
        fh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        fh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        fh.setSectionResizeMode(2, QHeaderView.Stretch)
        fh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.findings.itemDoubleClicked.connect(self._show_on_timeline)
        self.timeline = Timeline()
        self.stats = QTextBrowser()
        self.tabs.addTab(self.findings, "Findings")
        self.tabs.addTab(self.timeline, "Timeline")
        self.tabs.addTab(self.stats, "Casts and buffs")
        layout.addWidget(self.tabs)
        split.addWidget(right)
        split.setSizes([460, 820])
        self.setCentralWidget(split)

    def _build_status(self) -> None:
        self.progress = QProgressBar(maximumWidth=260, visible=False)
        self.statusBar().addPermanentWidget(self.progress)

    # Loading

    def open_log(self) -> None:
        start = self.settings.value("last_dir", "") or next((d for d in DEFAULT_LOG_DIRS if os.path.isdir(d)), "")
        path, _ = QFileDialog.getOpenFileName(self, "Open combat log", start, "Combat logs (WoWCombatLog*.txt *.txt)")
        if path:
            self.settings.setValue("last_dir", os.path.dirname(path))
            self.load_log(path)

    def load_log(self, path: str, player_guid: str | None = None) -> None:
        self._start(LogWorker(path, player_guid or self.settings.value("player_guid")), os.path.basename(path))

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

    def _start(self, worker, label: str) -> None:
        if self.thread is not None:
            self.statusBar().showMessage("Still loading the previous log…", 4000)
            return
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
            self.load_log(latest)
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
        self.load_log(latest)

    # Display

    def _fill_tree(self) -> None:
        self.tree.clear()
        log = self.loaded
        overview = QTreeWidgetItem(["Overview of all fights", "", "", "", ""])
        overview.setData(0, Qt.UserRole, None)
        self.tree.addTopLevelItem(overview)
        parents = {}
        for result in log.results:
            f = result.fight
            flags = sum(x.status == FLAG for x in result.findings)
            warns = sum(x.status == WARN for x in result.findings)
            outcome = {True: "Kill" if f.kind == "encounter" else "Timed", False: "Wipe" if f.kind == "encounter"
                       else "Depleted", None: "?"}[f.success]
            item = QTreeWidgetItem([f.label, outcome, fmt(f.duration), str(flags), str(warns)])
            item.setData(0, Qt.UserRole, result)
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
        self.tree.setCurrentItem(overview)

    def _fight_selected(self, item, _prev) -> None:
        if item is None or not self.loaded:
            return
        result: FightResult | None = item.data(0, Qt.UserRole)
        if result is None:
            self._show_overview()
        else:
            self._show_fight(result)

    def _show_overview(self) -> None:
        log = self.loaded
        self.heading.setText(f"<h2>{html.escape(log.player_name)}</h2>{len(log.results)} fights. "
                             "Rules that came up most often across fights are listed first.")
        counts: dict[str, list[int]] = {}
        titles = {}
        for r in log.results:
            for f in r.findings:
                titles[f.rule] = f"{f.rule} {f.title}"
                c = counts.setdefault(f.rule, [0, 0])
                c[0] += f.status == FLAG
                c[1] += f.status == WARN
        rows = sorted((r for r in counts if sum(counts[r])), key=lambda r: (-counts[r][0], -counts[r][1]))
        self.findings.setRowCount(0)
        self.findings.setHorizontalHeaderLabels(["", "Rule", "Fights flagged / warned", ""])
        for rule in rows:
            flags, warns = counts[rule]
            status = FLAG if flags else WARN
            self._add_row(status, titles[rule], f"🔴 {flags}   🟡 {warns}", "", None)
        self.timeline.set_result(None)
        self.stats.setMarkdown(render_overview([(r.summary.label, r.findings) for r in log.results]))
        self.tabs.setCurrentWidget(self.findings)

    def _show_fight(self, r: FightResult) -> None:
        s = r.summary
        deaths = f" · died at {', '.join(fmt(d) for d in s.deaths)}" if s.deaths else ""
        self.heading.setText(
            f"<h2>{html.escape(s.label)}</h2><b>{html.escape(s.hero_tree)}</b> · {s.dps:,.0f} DPS · "
            f"{s.cpm:.1f} abilities/min · {fmt(s.duration)}{deaths}<br>"
            f"<span style='color:gray'>Findings {html.escape(r.bench_note)}. Double-click a row to see it on the timeline.</span>")
        self.findings.setRowCount(0)
        self.findings.setHorizontalHeaderLabels(["", "Rule", "Result", "Look at"])
        for f in r.findings:
            when = ", ".join(fmt(t) for t in f.times[:8]) + (" …" if len(f.times) > 8 else "")
            self._add_row(f.status, f"{f.rule} {f.title} ({f.severity})", f.detail, when, (r, f.times))
        self.timeline.set_result(r)
        self.stats.setMarkdown(self._stats_markdown(r))

    def _add_row(self, status: str, rule: str, detail: str, when: str, payload) -> None:
        row = self.findings.rowCount()
        self.findings.insertRow(row)
        cells = [STATUS_TEXT[status], rule, detail, when]
        for col, text in enumerate(cells):
            cell = QTableWidgetItem(text)
            cell.setData(Qt.UserRole, payload)
            if status in STATUS_TINT:
                cell.setBackground(STATUS_TINT[status])
            self.findings.setItem(row, col, cell)
        self.findings.resizeRowToContents(row)

    def _show_on_timeline(self, item: QTableWidgetItem) -> None:
        payload = item.data(Qt.UserRole)
        if payload:
            result, times = payload
            self.timeline.set_result(result, times)
            self.tabs.setCurrentWidget(self.timeline)

    @staticmethod
    def _stats_markdown(r: FightResult) -> str:
        s = r.summary
        lines = ["| Ability | Casts | Longest gap |", "|---|---|---|"]
        for name, count in s.casts.most_common():
            gap = s.longest_gap.get(name)
            lines.append(f"| {name} | {count} | {fmt(gap) if gap is not None else ''} |")
        lines += ["", "| Buff | Uptime |", "|---|---|"]
        lines += [f"| {n} | {u:.0%} |" for n, u in s.buff_uptime.items()]
        lines += ["", "| Damage | Share |", "|---|---|"]
        lines += [f"| {n} | {d / max(s.damage, 1):.0%} |" for n, d in s.damage_by_ability]
        return "\n".join(lines)

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
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.load_log(sys.argv[1])
    sys.exit(app.exec())
