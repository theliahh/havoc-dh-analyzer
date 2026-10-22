"""Cooldown timeline for one fight: key casts per row, Metamorphosis windows shaded, findings marked."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from havoc_analyzer.report import FightResult
from havoc_analyzer.rules import FLAG, WARN, fmt

ROWS_SHARED = ["Eye Beam", "Metamorphosis", "Essence Break", "The Hunt", "Vengeful Retreat", "Immolation Aura"]
ROWS_TREE = {
    "Aldrachi Reaver": ["Reaver's Glaive"],
    "Fel-Scarred": ["Abyssal Gaze", "Consuming Fire"],
}
LEFT, TOP, ROW_H, RIGHT = 130, 34, 26, 16

REAL_META = QColor(140, 70, 200, 70)
DEMONIC = QColor(140, 70, 200, 28)
MARK = {FLAG: QColor(220, 60, 60), WARN: QColor(225, 170, 30)}
TICK = QColor(70, 160, 90)
HIGHLIGHT = QColor(60, 130, 230)


class Timeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: FightResult | None = None
        self.highlight: list[float] = []
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(260)

    def set_result(self, result: FightResult | None, highlight: list[float] | None = None) -> None:
        self.result = result
        self.highlight = highlight or []
        self.update()

    def rows(self) -> list[str]:
        if not self.result:
            return []
        return ROWS_SHARED + ROWS_TREE.get(self.result.data.hero_tree, [])

    def _x(self, t: float) -> float:
        width = max(self.width() - LEFT - RIGHT, 1)
        return LEFT + width * t / max(self.result.data.duration, 1)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pal = self.palette()
        p.fillRect(self.rect(), pal.base())
        if not self.result:
            p.setPen(pal.text().color())
            p.drawText(self.rect(), Qt.AlignCenter, "Pick a boss pull or key on the left.")
            return
        data = self.result.data
        rows = self.rows()
        bottom = TOP + ROW_H * len(rows)
        text = pal.text().color()

        # Metamorphosis windows behind everything.
        for w in data.meta_windows:
            p.fillRect(QRectF(self._x(w.start), TOP, self._x(w.end) - self._x(w.start), bottom - TOP),
                       REAL_META if w.from_cast else DEMONIC)

        # Time axis every 30 s.
        grid = QColor(text)
        grid.setAlpha(40)
        p.setFont(QFont(self.font().family(), 8))
        t = 0.0
        while t <= data.duration:
            x = self._x(t)
            p.setPen(QPen(grid, 1))
            p.drawLine(QPointF(x, TOP), QPointF(x, bottom))
            p.setPen(text)
            p.drawText(QRectF(x - 20, bottom + 2, 40, 14), Qt.AlignCenter, fmt(t))
            t += 30

        # Findings markers along the top.
        for f in self.result.findings:
            if f.status in MARK:
                p.setPen(QPen(MARK[f.status], 2))
                for t in f.times:
                    x = self._x(t)
                    p.drawLine(QPointF(x, 8), QPointF(x, TOP - 6))
        p.setPen(text)
        p.drawText(QRectF(0, 6, LEFT - 8, 20), Qt.AlignRight | Qt.AlignVCenter, "Findings")

        # One row per ability.
        p.setFont(QFont(self.font().family(), 9))
        for i, name in enumerate(rows):
            y = TOP + i * ROW_H
            p.setPen(text)
            p.drawText(QRectF(0, y, LEFT - 8, ROW_H), Qt.AlignRight | Qt.AlignVCenter, name)
            p.setPen(QPen(TICK, 3))
            for t in data.times(name):
                x = self._x(t)
                p.drawLine(QPointF(x, y + 5), QPointF(x, y + ROW_H - 5))

        for t in self.highlight:
            p.setPen(QPen(HIGHLIGHT, 2, Qt.DashLine))
            x = self._x(t)
            p.drawLine(QPointF(x, 6), QPointF(x, bottom))

        p.setPen(text)
        p.drawText(QRectF(LEFT, bottom + 18, self.width() - LEFT, 16), Qt.AlignLeft,
                   "Dark purple: Metamorphosis you pressed · light purple: Demonic after Eye Beam · "
                   "red/yellow ticks: findings")

    def mouseMoveEvent(self, event) -> None:
        if not self.result or event.position().x() < LEFT:
            return
        width = max(self.width() - LEFT - RIGHT, 1)
        t = (event.position().x() - LEFT) / width * self.result.data.duration
        row = int((event.position().y() - TOP) // ROW_H)
        rows = self.rows()
        tip = fmt(max(t, 0))
        if 0 <= row < len(rows):
            near = [c for c in self.result.data.times(rows[row]) if abs(c - t) < 1.5]
            if near:
                tip = f"{rows[row]} at {fmt(near[0])}"
        QToolTip.showText(event.globalPosition().toPoint(), tip, self)

    def sizeHint(self):
        from PySide6.QtCore import QSize
        return QSize(900, TOP + ROW_H * 8 + 60)
