"""Small painted widgets: horizontal bar charts, stat tiles and the status pill delegate."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath
from PySide6.QtWidgets import (
    QFrame, QLabel, QSizePolicy, QStyle, QStyledItemDelegate, QToolTip, QVBoxLayout, QWidget,
)

from . import theme
from .theme import STATUS_LABEL


@dataclass
class Bar:
    label: str
    segments: list[tuple[float, str]]   # (value, color token or status key), stacked left to right
    value_text: str
    tooltip: str = ""
    note: str = ""                       # muted text after the value


@dataclass
class Series:
    name: str
    color: str                           # "accent", "series:N" or "status:<key>"


def resolve(t: theme.Theme, color: str) -> QColor:
    kind, _, key = color.partition(":")
    if kind == "series":
        return QColor(t.series[int(key) % len(t.series)])
    if kind == "status":
        return t.status_color(key)
    return t.color(color)


class BarChart(QWidget):
    """Labelled horizontal bars on one shared scale, with an optional legend and hover tooltips."""
    ROW_H, BAR_H, GAP = 28, 12, 2

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.bars: list[Bar] = []
        self.series: list[Series] = []
        self.max_value = 1.0
        self.hover = -1
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_data(self, bars: list[Bar], series: list[Series] | None = None, max_value: float | None = None) -> None:
        self.bars = bars
        self.series = series or []
        self.max_value = max_value or max((sum(v for v, _ in b.segments) for b in bars), default=1.0) or 1.0
        self.setFixedHeight(self._top() + self.ROW_H * len(bars) + 10)
        self.update()

    def _top(self) -> int:
        return 34 + (22 if len(self.series) > 1 else 0)

    def _label_w(self) -> int:
        fm = QFontMetrics(self.font())
        return min(max((fm.horizontalAdvance(b.label) for b in self.bars), default=60) + 16, 260)

    def paintEvent(self, _event) -> None:
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bold = QFont(self.font())
        bold.setWeight(QFont.DemiBold)
        bold.setPointSizeF(self.font().pointSizeF() * 1.1)
        p.setFont(bold)
        p.setPen(t.color("text"))
        p.drawText(QRectF(0, 0, self.width(), 24), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setFont(self.font())
        fm = QFontMetrics(self.font())

        if len(self.series) > 1:          # legend: swatch + name, text in ink
            x = 0
            for s in self.series:
                p.setPen(Qt.NoPen)
                p.setBrush(resolve(t, s.color))
                p.drawRoundedRect(QRectF(x, 32, 10, 10), 3, 3)
                p.setPen(t.color("text2"))
                p.drawText(QRectF(x + 15, 26, 200, 22), Qt.AlignLeft | Qt.AlignVCenter, s.name)
                x += 15 + fm.horizontalAdvance(s.name) + 18

        if not self.bars:
            p.setPen(t.color("muted"))
            p.drawText(QRectF(0, self._top(), self.width(), self.ROW_H), Qt.AlignLeft | Qt.AlignVCenter, "Nothing to show.")
            return

        label_w = self._label_w()
        value_w = max(fm.horizontalAdvance(b.value_text + ("  " + b.note if b.note else "")) for b in self.bars) + 14
        track_w = max(self.width() - label_w - value_w, 40)
        for i, b in enumerate(self.bars):
            y = self._top() + i * self.ROW_H
            if i == self.hover:
                p.setPen(Qt.NoPen)
                p.setBrush(t.color("surface_alt"))
                p.drawRoundedRect(QRectF(-2, y, self.width() + 4, self.ROW_H), 6, 6)
            p.setPen(t.color("text2"))
            p.drawText(QRectF(0, y, label_w - 12, self.ROW_H), Qt.AlignRight | Qt.AlignVCenter,
                       fm.elidedText(b.label, Qt.ElideRight, label_w - 12))
            by = y + (self.ROW_H - self.BAR_H) / 2
            p.setPen(Qt.NoPen)
            p.setBrush(t.color("grid"))
            p.drawRoundedRect(QRectF(label_w, by, track_w, self.BAR_H), 4, 4)
            x = float(label_w)
            segs = [(v, c) for v, c in b.segments if v > 0]
            for j, (v, color) in enumerate(segs):
                w = track_w * v / self.max_value
                gap = self.GAP if j < len(segs) - 1 else 0
                p.setBrush(resolve(t, color))
                p.drawPath(_rounded(QRectF(x, by, max(w - gap, 2), self.BAR_H), 4,
                                    left=j == 0, right=j == len(segs) - 1))
                x += w
            p.setPen(t.color("text"))
            p.drawText(QRectF(label_w + track_w + 10, y, value_w, self.ROW_H), Qt.AlignLeft | Qt.AlignVCenter,
                       b.value_text)
            if b.note:
                p.setPen(t.color("muted"))
                p.drawText(QRectF(label_w + track_w + 10 + fm.horizontalAdvance(b.value_text + "  "), y,
                                  value_w, self.ROW_H), Qt.AlignLeft | Qt.AlignVCenter, b.note)

    def _row_at(self, y: float) -> int:
        row = int((y - self._top()) // self.ROW_H)
        return row if y >= self._top() and 0 <= row < len(self.bars) else -1

    def mouseMoveEvent(self, event) -> None:
        row = self._row_at(event.position().y())
        if row != self.hover:
            self.hover = row
            self.update()
        if row >= 0:
            b = self.bars[row]
            QToolTip.showText(event.globalPosition().toPoint(), b.tooltip or f"{b.label}: {b.value_text}", self)
        else:
            QToolTip.hideText()

    def leaveEvent(self, _event) -> None:
        self.hover = -1
        self.update()


def _rounded(r: QRectF, radius: float, left: bool, right: bool) -> QPainterPath:
    """A bar with rounded corners only on the ends that are bar ends, not segment joins."""
    path = QPainterPath()
    rl, rr = (radius if left else 0), (radius if right else 0)
    path.moveTo(r.left() + rl, r.top())
    path.lineTo(r.right() - rr, r.top())
    path.quadTo(r.right(), r.top(), r.right(), r.top() + rr)
    path.lineTo(r.right(), r.bottom() - rr)
    path.quadTo(r.right(), r.bottom(), r.right() - rr, r.bottom())
    path.lineTo(r.left() + rl, r.bottom())
    path.quadTo(r.left(), r.bottom(), r.left(), r.bottom() - rl)
    path.lineTo(r.left(), r.top() + rl)
    path.quadTo(r.left(), r.top(), r.left() + rl, r.top())
    return path


def card(*widgets: QWidget) -> QFrame:
    frame = QFrame(objectName="card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 12, 16, 12)
    for w in widgets:
        layout.addWidget(w)
    return frame


class StatTile(QFrame):
    """One headline number with a caption under it."""

    def __init__(self, parent=None):
        super().__init__(parent, objectName="card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        self.value = QLabel(objectName="statValue")
        self.caption = QLabel(objectName="statCaption")
        layout.addWidget(self.value)
        layout.addWidget(self.caption)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set(self, value: str, caption: str, color: str | None = None) -> None:
        self.value.setText(value)
        self.value.setStyleSheet(f"color: {color};" if color else "")
        self.caption.setText(caption)


class StatusDelegate(QStyledItemDelegate):
    """Draws a rule status as a colored pill with its word, so color never carries it alone."""

    def paint(self, painter: QPainter, option, index) -> None:
        status = index.data(Qt.UserRole + 1)
        if status not in STATUS_LABEL:
            return super().paint(painter, option, index)
        t = theme.current()
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(theme.mix(t.accent, t.surface, 0.18)))
        text = STATUS_LABEL[status]
        fm = QFontMetrics(option.font)
        w = fm.horizontalAdvance(text) + 26
        r = QRectF(option.rect.left() + 6, option.rect.center().y() - 10, w, 20)
        painter.setPen(Qt.NoPen)
        painter.setBrush(t.status_color(status, 38))
        painter.drawRoundedRect(r, 10, 10)
        painter.setBrush(t.status_color(status))
        painter.drawEllipse(QRectF(r.left() + 8, r.center().y() - 3.5, 7, 7))
        font = QFont(option.font)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(t.color("text"))
        painter.drawText(r.adjusted(19, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        fm = QFontMetrics(option.font)
        return QSize(max(fm.horizontalAdvance(w) for w in STATUS_LABEL.values()) + 40, 30)
