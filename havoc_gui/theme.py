"""Light and dark themes: color tokens, the Qt palette and the app stylesheet."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from havoc_analyzer.rules import FLAG, INFO, OK, WARN

MODES = ("system", "light", "dark")


@dataclass(frozen=True)
class Theme:
    name: str
    window: str        # page behind the cards
    surface: str       # cards, tables, charts
    surface_alt: str   # hover, zebra rows, chart lanes
    border: str
    text: str
    text2: str         # secondary ink
    muted: str         # axis labels, captions
    grid: str
    accent: str        # selection and the primary button
    accent_text: str
    meta: str          # Metamorphosis windows
    meta_alpha: tuple  # fill alpha for (pressed, Demonic)
    status: dict       # rule status -> color
    series: tuple      # categorical slots, fixed order

    def color(self, token: str, alpha: int | None = None) -> QColor:
        c = QColor(getattr(self, token))
        if alpha is not None:
            c.setAlpha(alpha)
        return c

    def status_color(self, status: str, alpha: int | None = None) -> QColor:
        c = QColor(self.status[status])
        if alpha is not None:
            c.setAlpha(alpha)
        return c


# Status colors are the same in both modes and always shown with a label.
STATUS = {FLAG: "#d03b3b", WARN: "#e8a20c", OK: "#0ca30c", INFO: "#898781"}
STATUS_LABEL = {FLAG: "Fix", WARN: "Check", OK: "Good", INFO: "Info"}

LIGHT = Theme(
    name="light", window="#f1f1ee", surface="#fcfcfb", surface_alt="#f4f3ef", border="#e1e0d9",
    text="#0b0b0b", text2="#52514e", muted="#898781", grid="#e8e7e1",
    accent="#6250d6", accent_text="#ffffff", meta="#6250d6", meta_alpha=(60, 24), status=STATUS,
    series=("#008300", "#6250d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#2a78d6", "#e34948"),
)
DARK = Theme(
    name="dark", window="#111111", surface="#1a1a19", surface_alt="#222220", border="#2f2f2c",
    text="#f0efec", text2="#c3c2b7", muted="#898781", grid="#2c2c2a",
    accent="#9085e9", accent_text="#111111", meta="#9085e9", meta_alpha=(80, 40), status=STATUS,
    series=("#008300", "#9085e9", "#d95926", "#199e70", "#c98500", "#d55181", "#3987e5", "#e66767"),
)

_current = LIGHT


def current() -> Theme:
    return _current


def system_is_dark(app: QApplication) -> bool:
    hints = app.styleHints()
    return hasattr(hints, "colorScheme") and hints.colorScheme() == Qt.ColorScheme.Dark


def apply(app: QApplication, mode: str = "system") -> Theme:
    """Switch the whole app to light, dark, or whatever the OS uses."""
    global _current
    dark = system_is_dark(app) if mode == "system" else mode == "dark"
    _current = t = DARK if dark else LIGHT
    app.setStyle("Fusion")
    app.setPalette(_palette(t))
    app.setStyleSheet(_stylesheet(t))
    return t


def _palette(t: Theme) -> QPalette:
    p = QPalette()
    roles = {
        QPalette.Window: t.window, QPalette.WindowText: t.text, QPalette.Base: t.surface,
        QPalette.AlternateBase: t.surface_alt, QPalette.Text: t.text, QPalette.Button: t.surface,
        QPalette.ButtonText: t.text, QPalette.ToolTipBase: t.surface, QPalette.ToolTipText: t.text,
        QPalette.Highlight: t.accent, QPalette.HighlightedText: t.accent_text,
        QPalette.PlaceholderText: t.muted, QPalette.Link: t.accent, QPalette.BrightText: t.status[FLAG],
        QPalette.Light: t.surface_alt, QPalette.Midlight: t.border, QPalette.Mid: t.border,
        QPalette.Dark: t.border, QPalette.Shadow: t.window,
    }
    for role, hex_ in roles.items():
        p.setColor(role, QColor(hex_))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(t.muted))
    return p


def _stylesheet(t: Theme) -> str:
    return f"""
    QMainWindow, QDialog {{ background: {t.window}; }}
    QWidget {{ font-size: 10pt; }}
    QToolTip {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
                border-radius: 6px; padding: 6px 8px; }}

    QToolBar {{ background: {t.window}; border: none; padding: 8px 10px; spacing: 6px; }}
    QToolBar QToolButton {{ background: transparent; color: {t.text}; border: 1px solid transparent;
                            border-radius: 7px; padding: 6px 12px; }}
    QToolBar QToolButton:hover {{ background: {t.surface_alt}; border-color: {t.border}; }}
    QToolBar QToolButton:checked {{ background: {t.surface}; border-color: {t.accent}; color: {t.accent}; }}
    QToolBar QToolButton:disabled {{ color: {t.muted}; }}
    QToolBar QToolButton#primary {{ background: {t.accent}; color: {t.accent_text}; font-weight: 600; }}
    QToolBar QToolButton#primary:hover {{ border-color: {t.text2}; }}
    QToolBar QToolButton::menu-indicator {{ image: none; width: 0; }}
    QToolBar QLabel {{ color: {t.text2}; }}

    QComboBox, QLineEdit {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
                            border-radius: 7px; padding: 5px 8px; selection-background-color: {t.accent}; }}
    QComboBox:focus, QLineEdit:focus {{ border-color: {t.accent}; }}
    QComboBox:disabled {{ color: {t.muted}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: 6px;
                                   selection-background-color: {t.surface_alt}; selection-color: {t.text}; }}

    QPushButton {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
                   border-radius: 7px; padding: 6px 14px; }}
    QPushButton:hover {{ background: {t.surface_alt}; }}
    QPushButton:default {{ background: {t.accent}; color: {t.accent_text}; border-color: {t.accent}; }}

    QFrame#card, QTreeWidget, QTableWidget, QTextBrowser, QTabWidget::pane {{
        background: {t.surface}; border: 1px solid {t.border}; border-radius: 10px; }}
    QTabWidget::pane {{ top: -1px; }}
    QTabBar::tab {{ background: transparent; color: {t.text2}; border: none; border-bottom: 2px solid transparent;
                    padding: 8px 14px; margin-right: 4px; }}
    QTabBar::tab:hover {{ color: {t.text}; }}
    QTabBar::tab:selected {{ color: {t.text}; border-bottom-color: {t.accent}; font-weight: 600; }}

    QTreeWidget, QTableWidget {{ padding: 4px; outline: none; gridline-color: transparent;
                                 alternate-background-color: {t.surface_alt}; }}
    QTreeWidget::item, QTableWidget::item {{ padding: 6px 4px; border: none; }}
    QTreeWidget::item:hover, QTableWidget::item:hover {{ background: {t.surface_alt}; }}
    QTreeWidget::item:selected, QTableWidget::item:selected {{ background: {mix(t.accent, t.surface, 0.18)};
                                                               color: {t.text}; }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{ background: {t.surface}; color: {t.muted}; border: none;
                            border-bottom: 1px solid {t.border}; padding: 6px 6px; font-weight: 600; }}

    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
    QScrollBar::handle {{ background: {t.border}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
    QScrollBar::handle:hover {{ background: {t.muted}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    QSplitter::handle {{ background: transparent; width: 10px; }}
    QStatusBar {{ background: {t.window}; color: {t.text2}; padding-left: 12px; }}
    QStatusBar::item {{ border: none; }}
    QProgressBar {{ background: {t.surface_alt}; border: none; border-radius: 4px; height: 8px;
                    max-height: 8px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}
    QMenu {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 18px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t.surface_alt}; }}
    QFrame#divider {{ background: {t.border}; border: none; max-height: 1px; }}
    QLabel#muted {{ color: {t.muted}; }}
    QLabel#secondary {{ color: {t.text2}; }}
    QLabel#title {{ font-size: 17pt; font-weight: 700; }}
    QLabel#statValue {{ font-size: 15pt; font-weight: 650; }}
    QLabel#statCaption {{ color: {t.muted}; font-size: 9pt; }}
    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """


def mix(a: str, b: str, amount: float) -> str:
    """amount of color a over color b, as hex."""
    ca, cb = QColor(a), QColor(b)
    r, g, bl = (round(x * amount + y * (1 - amount)) for x, y in
                ((ca.red(), cb.red()), (ca.green(), cb.green()), (ca.blue(), cb.blue())))
    return QColor(r, g, bl).name()
