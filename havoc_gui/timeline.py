"""Cooldown timeline for one fight: key casts per row, Metamorphosis windows shaded, findings marked."""
from __future__ import annotations

import html

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from havoc_analyzer.report import FightResult
from havoc_analyzer.rules import FLAG, WARN, fmt

from . import theme

ROWS_SHARED = ["Eye Beam", "Metamorphosis", "Essence Break", "The Hunt", "Vengeful Retreat", "Immolation Aura"]
ROWS_TREE = {
    "Aldrachi Reaver": ["Reaver's Glaive"],
    "Fel-Scarred": ["Abyssal Gaze", "Consuming Fire"],
}
# Each ability keeps its categorical slot whatever the hero tree, so its color never changes.
ROW_SLOT = {"Eye Beam": 0, "Metamorphosis": 1, "Essence Break": 2, "The Hunt": 3, "Vengeful Retreat": 4,
            "Immolation Aura": 5, "Reaver's Glaive": 6, "Abyssal Gaze": 6, "Consuming Fire": 7}
LEFT, TOP, ROW_H, MAX_ROW_H, RIGHT, PAD = 140, 58, 30, 46, 20, 16
LANE_Y = 30                     # findings lane centre
TICK_STEPS = (15, 30, 60, 120, 300, 600)


class Timeline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.result: FightResult | None = None
        self.highlight: list[float] = []
        self.hover_x: float | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(300)

    def set_result(self, result: FightResult | None, highlight: list[float] | None = None) -> None:
        self.result = result
        self.highlight = highlight or []
        self.update()

    def rows(self) -> list[str]:
        if not self.result:
            return []
        return ROWS_SHARED + ROWS_TREE.get(self.result.data.hero_tree, [])

    def _row_h(self) -> float:
        """Rows grow to fill the space above the axis and legend, within limits."""
        rows = len(self.rows()) or 1
        return min(max((self.height() - TOP - 90) / rows, ROW_H), MAX_ROW_H)

    def _plot_w(self) -> float:
        return max(self.width() - LEFT - RIGHT, 1)

    def _x(self, t: float) -> float:
        return LEFT + self._plot_w() * t / max(self.result.data.duration, 1)

    def _t(self, x: float) -> float:
        return (x - LEFT) / self._plot_w() * self.result.data.duration

    def paintEvent(self, _event) -> None:
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), t.color("surface"))
        if not self.result:
            p.setPen(t.color("muted"))
            p.drawText(self.rect(), Qt.AlignCenter, "Pick a boss pull or key on the left.")
            return
        data = self.result.data
        rows = self.rows()
        row_h = self._row_h()
        bottom = TOP + row_h * len(rows)
        small = QFont(self.font())
        small.setPointSizeF(self.font().pointSizeF() * 0.85)

        # Lanes: alternate rows get a faint band so the eye can follow a row across.
        for i in range(len(rows)):
            if i % 2 == 0:
                p.fillRect(QRectF(LEFT, TOP + i * row_h, self._plot_w(), row_h), t.color("surface_alt"))

        # Metamorphosis windows behind the casts.
        for w in data.meta_windows:
            x0, x1 = self._x(w.start), self._x(w.end)
            alpha = t.meta_alpha[0] if w.from_cast else t.meta_alpha[1]
            p.fillRect(QRectF(x0, TOP, x1 - x0, bottom - TOP), t.color("meta", alpha))
            p.fillRect(QRectF(x0, TOP - 4, x1 - x0, 3), t.color("meta", 220 if w.from_cast else 90))

        # Time axis: hairline grid, step chosen so labels sit at least ~70 px apart.
        step = next((s for s in TICK_STEPS if self._plot_w() * s / max(data.duration, 1) >= 70), TICK_STEPS[-1])
        p.setFont(small)
        tick = 0.0
        while tick <= data.duration:
            x = self._x(tick)
            p.setPen(QPen(t.color("grid"), 1))
            p.drawLine(QPointF(x, TOP), QPointF(x, bottom))
            p.setPen(t.color("muted"))
            p.drawText(QRectF(x - 30, bottom + 4, 60, 16), Qt.AlignCenter, fmt(tick))
            tick += step
        p.setPen(QPen(t.color("border"), 1))
        p.drawLine(QPointF(LEFT, bottom), QPointF(LEFT + self._plot_w(), bottom))

        # Findings lane: diamonds for flags and warnings, a cross for each death.
        p.setFont(self.font())
        p.setPen(t.color("text2"))
        p.drawText(QRectF(0, LANE_Y - 10, LEFT - PAD, 20), Qt.AlignRight | Qt.AlignVCenter, "Findings")
        p.setPen(QPen(t.color("grid"), 1))
        p.drawLine(QPointF(LEFT, LANE_Y), QPointF(LEFT + self._plot_w(), LANE_Y))
        for f in sorted(self.result.findings, key=lambda f: f.status == FLAG):   # flags drawn on top
            if f.status in (FLAG, WARN):
                for when in f.times:
                    _diamond(p, QPointF(self._x(when), LANE_Y), 6, t.status_color(f.status), t.color("surface"))
        for d in data.deaths:
            x = self._x(d)
            p.setPen(QPen(t.color("text2"), 2.2, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(x - 5, LANE_Y - 5), QPointF(x + 5, LANE_Y + 5))
            p.drawLine(QPointF(x - 5, LANE_Y + 5), QPointF(x + 5, LANE_Y - 5))
            p.setPen(QPen(t.color("text2", 90), 1, Qt.DotLine))
            p.drawLine(QPointF(x, TOP), QPointF(x, bottom))

        # One row per ability: rounded pills in the ability's own color, labelled with a swatch.
        for i, name in enumerate(rows):
            y = TOP + i * row_h
            color = QColor(t.series[ROW_SLOT.get(name, i) % len(t.series)])
            p.setPen(t.color("text2"))
            p.drawText(QRectF(0, y, LEFT - PAD, row_h), Qt.AlignRight | Qt.AlignVCenter, name)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawRoundedRect(QRectF(LEFT - 10, y + row_h / 2 - 3, 6, 6), 2, 2)
            pen = QPen(t.color("surface"), 1.5)
            for when in data.times(name):
                x = self._x(when)
                p.setPen(pen)                       # surface ring keeps close casts apart
                p.drawRoundedRect(QRectF(x - 2.5, y + 6, 5, row_h - 12), 2.5, 2.5)

        for when in self.highlight:
            x = self._x(when)
            p.setPen(QPen(t.color("accent"), 1.5, Qt.DashLine))
            p.drawLine(QPointF(x, LANE_Y + 10), QPointF(x, bottom))
            _bubble(p, QPointF(x, bottom + 12), fmt(when), t, small, filled=True)

        if self.hover_x is not None and LEFT <= self.hover_x <= LEFT + self._plot_w():
            p.setPen(QPen(t.color("text2", 140), 1))
            p.drawLine(QPointF(self.hover_x, TOP), QPointF(self.hover_x, bottom))
            _bubble(p, QPointF(self.hover_x, bottom + 12), fmt(max(self._t(self.hover_x), 0)), t, small)

        self._legend(p, bottom + 36, small, t)

    def _legend(self, p: QPainter, y: float, font: QFont, t: theme.Theme) -> None:
        p.setFont(font)
        fm = QFontMetrics(font)
        x = LEFT
        items = [
            ("rect", t.color("meta", t.meta_alpha[0]), "Metamorphosis you pressed"),
            ("rect", t.color("meta", t.meta_alpha[1]), "Demonic after Eye Beam"),
            ("diamond", t.status_color(FLAG), "Fix"),
            ("diamond", t.status_color(WARN), "Check"),
            ("cross", t.color("text2"), "Death"),
        ]
        for kind, color, label in items:
            cy = y + 8
            if kind == "rect":
                p.setPen(Qt.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(QRectF(x, cy - 6, 14, 12), 3, 3)
            elif kind == "diamond":
                _diamond(p, QPointF(x + 7, cy), 5.5, color, t.color("surface"))
            else:
                p.setPen(QPen(color, 2, Qt.SolidLine, Qt.RoundCap))
                p.drawLine(QPointF(x + 3, cy - 4), QPointF(x + 11, cy + 4))
                p.drawLine(QPointF(x + 3, cy + 4), QPointF(x + 11, cy - 4))
            p.setPen(t.color("text2"))
            p.drawText(QRectF(x + 20, y, 400, 16), Qt.AlignLeft | Qt.AlignVCenter, label)
            x += 20 + fm.horizontalAdvance(label) + 22

    def mouseMoveEvent(self, event) -> None:
        if not self.result:
            return
        pos = event.position()
        self.hover_x = pos.x() if pos.x() >= LEFT else None
        self.update()
        if self.hover_x is None:
            QToolTip.hideText()
            return
        t = self._t(pos.x())
        tolerance = max(1.5, 5 * self.result.data.duration / self._plot_w())   # seconds within 5 px
        tip = fmt(max(t, 0))
        row = int((pos.y() - TOP) // self._row_h())
        rows = self.rows()
        if pos.y() < TOP:
            near = [html.escape(f"{f.rule} {f.title}: {f.detail}") for f in self.result.findings
                    if f.status in (FLAG, WARN) and any(abs(x - t) < tolerance for x in f.times)]
            near += [f"Died at {fmt(d)}" for d in self.result.data.deaths if abs(d - t) < tolerance]
            if near:
                tip = f"<b>{fmt(max(t, 0))}</b><br>" + "<br>".join(near)
        elif 0 <= row < len(rows):
            near = [c for c in self.result.data.times(rows[row]) if abs(c - t) < tolerance]
            if near:
                tip = f"<b>{html.escape(rows[row])}</b> at {fmt(near[0])}"
        QToolTip.showText(event.globalPosition().toPoint(), tip, self)

    def leaveEvent(self, _event) -> None:
        self.hover_x = None
        self.update()

    def sizeHint(self):
        return QSize(900, TOP + ROW_H * 8 + 80)


def _diamond(p: QPainter, c: QPointF, r: float, fill: QColor, ring: QColor) -> None:
    path = QPainterPath()
    path.moveTo(c.x(), c.y() - r)
    path.lineTo(c.x() + r, c.y())
    path.lineTo(c.x(), c.y() + r)
    path.lineTo(c.x() - r, c.y())
    path.closeSubpath()
    p.setPen(QPen(ring, 1.5))
    p.setBrush(fill)
    p.drawPath(path)


def _bubble(p: QPainter, at: QPointF, text: str, t: theme.Theme, font: QFont, filled: bool = False) -> None:
    """A small rounded time label centred on the axis, used for the hover and highlight lines."""
    p.setFont(font)
    w = QFontMetrics(font).horizontalAdvance(text) + 12
    r = QRectF(at.x() - w / 2, at.y() - 9, w, 18)
    p.setPen(Qt.NoPen if filled else QPen(t.color("border"), 1))
    p.setBrush(t.color("accent") if filled else t.color("surface"))
    p.drawRoundedRect(r, 9, 9)
    p.setPen(t.color("accent_text") if filled else t.color("text"))
    p.drawText(r, Qt.AlignCenter, text)
