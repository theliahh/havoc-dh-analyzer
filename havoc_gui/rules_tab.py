"""Rules tab: the rules the analyzer applies for one hero tree, in plain language."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from havoc_analyzer.rules import AR, FS, NOT_CHECKED, OK_RATIO, WARN_RATIO, Rule, rules_for

from .charts import card

TREES = [AR, FS]
IMPACT = {"High": "Big DPS loss", "Med": "Likely DPS loss", "Low": "Minor"}
INTRO = (f"Rules that count casts per minute compare you with top players on the same tree and content: "
         f"{OK_RATIO:.0%} of their rate or more is fine, {WARN_RATIO:.0%} to {OK_RATIO:.0%} is worth a check, "
         f"under {WARN_RATIO:.0%} needs a fix.")


def rule_row(rule: Rule) -> QWidget:
    row = QWidget()
    layout = QVBoxLayout(row)
    layout.setContentsMargins(0, 8, 0, 8)
    layout.setSpacing(3)
    head = QHBoxLayout()
    title = QLabel(f"<b>{rule.id}</b>&nbsp;&nbsp;{rule.title}")
    title.setTextFormat(Qt.RichText)
    head.addWidget(title, 1)
    head.addWidget(QLabel(IMPACT[rule.severity], objectName="muted"))
    layout.addLayout(head)
    text = QLabel(rule.explain, objectName="secondary")
    text.setWordWrap(True)
    layout.addWidget(text)
    return row


def section(heading: str, rules: list[Rule]) -> QFrame:
    label = QLabel(heading)
    font = label.font()
    font.setWeight(font.Weight.DemiBold)
    font.setPointSizeF(font.pointSizeF() * 1.1)
    label.setFont(font)
    widgets: list[QWidget] = [label]
    for i, rule in enumerate(rules):
        if i:
            line = QFrame(frameShape=QFrame.HLine, objectName="divider")
            widgets.append(line)
        widgets.append(rule_row(rule))
    return card(*widgets)


class RulesPage(QScrollArea):
    """Shared rules plus the chosen tree's rules. Follows the fight's detected tree; the picker overrides it."""

    def __init__(self, parent=None):
        super().__init__(parent, widgetResizable=True)
        page = QWidget()
        self.layout_ = QVBoxLayout(page)
        self.layout_.setContentsMargins(12, 12, 12, 12)
        self.layout_.setSpacing(12)
        top = QHBoxLayout()
        top.addWidget(QLabel("Hero tree"))
        self.picker = QComboBox(minimumWidth=180)
        self.picker.addItems(TREES)
        self.picker.currentTextChanged.connect(self._fill)
        top.addWidget(self.picker)
        self.note = QLabel("", objectName="muted")
        top.addWidget(self.note, 1)
        self.layout_.addLayout(top)
        intro = QLabel(INTRO, objectName="secondary")
        intro.setWordWrap(True)
        self.layout_.addWidget(intro)
        self.sections: list[QFrame] = []
        self.layout_.addStretch()
        self.setWidget(page)
        self._fill(self.picker.currentText())

    @property
    def tree(self) -> str:
        return self.picker.currentText()

    def set_detected(self, tree: str | None) -> None:
        """Show the rules for the tree found in the log ("Unknown" or None leaves the picker where it is)."""
        if tree in TREES:
            self.picker.setCurrentText(tree)
            self.note.setText("Detected from the log. Pick the other tree to compare.")
        else:
            self.note.setText("Hero tree not detected in this log. Pick one to see its rules.")

    def _fill(self, tree: str) -> None:
        for frame in self.sections:
            frame.setParent(None)
            frame.deleteLater()
        shared = rules_for(None)
        own = [r for r in rules_for(tree) if r.tree is not None]
        later = rules_for(tree, NOT_CHECKED)
        self.sections = [section("Both hero trees", shared), section(tree, own),
                         section("Not checked yet", later)]
        for i, frame in enumerate(self.sections):
            self.layout_.insertWidget(2 + i, frame)
