import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    from havoc_gui import theme
    from havoc_gui.app import STATUS_ROLE, MainWindow
    from havoc_gui.workers import LoadedLog
except ImportError:   # PySide6 or its system libraries missing: skip the GUI tests
    QApplication = None

from havoc_analyzer import events as ev
from havoc_analyzer.events import Event, Fight
from havoc_analyzer.report import analyze_fights


@unittest.skipIf(QApplication is None, "PySide6 not available")
class MainWindowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_shows_overview_and_fight(self):
        events = [Event(5, ev.CAST, "me", "boss", 198013, "Eye Beam", fury=100),
                  Event(50, ev.CAST, "me", "boss", 200166, "Metamorphosis", fury=60)]
        fight = Fight("encounter", "Test Boss", "", "Heroic", duration=60, success=True, events=events)
        log = LoadedLog("test.txt", "Tester", "12.1.5", analyze_fights([fight], "me", {}), {"me": "Tester"})
        win = MainWindow()
        win._loaded(log)
        self.assertEqual(win.tree.topLevelItemCount(), 2)            # overview + one pull
        win.tree.setCurrentItem(win.tree.topLevelItem(1))
        rules = [win.findings.item(r, 1).text() for r in range(win.findings.rowCount())]
        self.assertTrue(any(r.startswith("S2 ") for r in rules))
        self.assertEqual(win.findings.item(0, 0).data(STATUS_ROLE), "flag")   # flags sort first
        win.close()

    def test_switches_theme(self):
        win = MainWindow()
        win.set_theme("dark")
        self.assertIs(theme.current(), theme.DARK)
        self.assertEqual(self.app.palette().window().color().name(), theme.DARK.window)
        win.set_theme("light")
        self.assertIs(theme.current(), theme.LIGHT)
        win.settings.remove("theme")
        win.close()


if __name__ == "__main__":
    unittest.main()
