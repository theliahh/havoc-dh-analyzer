import unittest

from havoc_analyzer import events as ev
from havoc_analyzer.benchmarks import Benchmark
from havoc_analyzer.events import Event, Fight
from havoc_analyzer.rules import FLAG, INFO, OK, WARN, evaluate
from havoc_analyzer.summary import build
from havoc_analyzer.wcl_source import load_fight, parse_report_url, to_event

ME, BOSS = "me", "boss"


def cast(t, spell_id, name, fury=100):
    return Event(t, ev.CAST, ME, BOSS, spell_id, name, fury=fury)


def buff(t, kind, spell_id, name):
    return Event(t, kind, ME, ME, spell_id, name)


def fight(events, duration=60.0):
    return Fight("encounter", "Test", "", "Heroic", duration=duration, events=events)


def findings(events, bench=None, duration=60.0):
    return {f.rule: f for f in evaluate(build(fight(events, duration), ME), bench)}


class MetaWindowTest(unittest.TestCase):
    def test_demonic_window_not_counted_as_meta(self):
        events = [
            cast(1, 198013, "Eye Beam"),
            buff(1.1, ev.AURA_APPLIED, 162264, "Metamorphosis"),   # Demonic from Eye Beam
            buff(7, ev.AURA_REMOVED, 162264, "Metamorphosis"),
            cast(20, 198013, "Eye Beam"),
            cast(22, 200166, "Metamorphosis"),
            buff(22.2, ev.AURA_APPLIED, 162264, "Metamorphosis"),
            buff(42, ev.AURA_REMOVED, 162264, "Metamorphosis"),
        ]
        windows = build(fight(events), ME).meta_windows
        self.assertEqual([w.from_cast for w in windows], [False, True])


class RuleTest(unittest.TestCase):
    def test_auto_throw_glaive_ignored_manual_counted(self):
        events = [cast(1, 210152, "Death Sweep"), cast(1.01, 185123, "Throw Glaive"),
                  cast(30, 185123, "Throw Glaive")]
        data = build(fight(events), ME)
        self.assertEqual(data.times("Throw Glaive"), [30])

    def test_meta_without_eye_beam_flagged(self):
        f = findings([cast(5, 198013, "Eye Beam"), cast(8, 200166, "Metamorphosis"),
                      cast(50, 200166, "Metamorphosis")])
        self.assertEqual(f["S2"].status, FLAG)
        self.assertEqual(f["S2"].times, [50])

    def test_low_fury_meta(self):
        f = findings([cast(5, 198013, "Eye Beam"), cast(8, 200166, "Metamorphosis", fury=60)])
        self.assertEqual(f["S9a"].status, FLAG)
        f = findings([cast(5, 198013, "Eye Beam"), cast(8, 200166, "Metamorphosis", fury=110)])
        self.assertEqual(f["S9a"].status, OK)

    def test_rate_against_benchmark(self):
        bench = Benchmark("raid", "AR", 8, cpm={"Eye Beam": 3.0})
        beams = [cast(t, 198013, "Eye Beam") for t in (0, 20, 40)]    # 3 per minute
        self.assertEqual(findings(beams, bench)["S1"].status, OK)
        self.assertEqual(findings(beams[:2], bench)["S1"].status, FLAG)  # 2/min = 67%
        self.assertEqual(findings(beams)["S1"].status, INFO)            # no benchmark

    def test_rate_uses_pressed_benchmark(self):
        # Two "The Hunt" spell IDs share a name; only the pressed one (370965) counts.
        bench = Benchmark("raid", "AR", 8, cpm={"The Hunt": 2.0}, pressed_cpm={"The Hunt": 1.0})
        hunts = [cast(0, 370965, "The Hunt"), cast(0.3, 370966, "The Hunt")]
        f = findings(hunts, bench)["S5"]
        self.assertEqual(f.status, OK)
        self.assertIn("1.00/min vs 1.00/min", f.detail)

    def test_thrill_uptime_against_benchmark(self):
        events = [cast(1, 442294, "Reaver's Glaive"),
                  buff(0, ev.AURA_APPLIED, 442695, "Thrill of the Fight"),
                  buff(42, ev.AURA_REMOVED, 442695, "Thrill of the Fight")]        # 70% up
        self.assertEqual(findings(events, Benchmark("mplus", "AR", 8, thrill_uptime=0.70))["AR4"].status, OK)
        self.assertEqual(findings(events)["AR4"].status, WARN)                       # default 80% target

    def test_hero_tree_rules_only_for_that_tree(self):
        ar = findings([cast(1, 442294, "Reaver's Glaive"), buff(3, ev.AURA_APPLIED, 442695, "Thrill of the Fight")])
        self.assertIn("AR2", ar)
        self.assertNotIn("FS3", ar)
        self.assertEqual(ar["AR2"].status, OK)

    def test_idle_gap_reported(self):
        events = [cast(t, 162794, "Chaos Strike") for t in range(0, 60)]
        events = [e for e in events if not 20 < e.t < 40]                # 20 s gap
        f = findings(events, Benchmark("raid", "AR", 8, idle_per_min=0.6))
        self.assertEqual(f["S11"].status, FLAG)
        self.assertEqual(f["S11"].times, [20])


class DeathTest(unittest.TestCase):
    def test_time_dead_not_counted(self):
        # Two Eye Beams in 30 s alive, then dead for the last 30 s: 4/min, not 2/min.
        events = [cast(0, 198013, "Eye Beam"), cast(15, 198013, "Eye Beam"),
                  Event(30, ev.DIED, "", ME)]
        data = build(fight(events), ME)
        self.assertEqual(data.dead_intervals, [(30, 60.0)])
        self.assertAlmostEqual(data.per_min("Eye Beam"), 4.0)

    def test_battle_rez_ends_dead_time_and_gap_is_not_idle(self):
        events = [cast(t, 162794, "Chaos Strike") for t in range(0, 20)]
        events += [Event(20, ev.DIED, "", ME)] + [cast(t, 162794, "Chaos Strike") for t in range(40, 60)]
        data = build(fight(events), ME)
        self.assertEqual(data.dead_intervals, [(20, 40)])
        self.assertEqual(data.idle_gaps(), [])


class PotionTest(unittest.TestCase):
    def test_prepot_before_meta_is_fine(self):
        events = [cast(52, 1236994, "Potion of Recklessness"), cast(55, 198013, "Eye Beam"),
                  cast(58, 200166, "Metamorphosis"), buff(58.2, ev.AURA_APPLIED, 162264, "Metamorphosis"),
                  buff(78, ev.AURA_REMOVED, 162264, "Metamorphosis")]
        self.assertEqual(findings(events, duration=90)["S13"].status, OK)


class WclAdapterTest(unittest.TestCase):
    def test_cast_with_fury(self):
        raw = {"timestamp": 12500, "type": "cast", "sourceID": 7, "targetID": 99, "abilityGameID": 200166,
               "classResources": [{"amount": 112, "max": 120, "type": 17}]}
        e = to_event(raw, 10000, {200166: "Metamorphosis"})
        self.assertEqual((e.t, e.type, e.src, e.dst, e.spell_name, e.fury), (2.5, ev.CAST, "wcl:7", "wcl:99",
                                                                              "Metamorphosis", 112))

    def test_parse_report_url(self):
        self.assertEqual(parse_report_url("https://www.warcraftlogs.com/reports/AbC123#fight=7&type=damage-done"),
                         ("AbC123", 7))
        self.assertEqual(parse_report_url("https://www.warcraftlogs.com/reports/AbC123/"), ("AbC123", None))
        self.assertEqual(parse_report_url(" AbC123 "), ("AbC123", None))

    def test_unknown_type_and_other_resource_dropped(self):
        self.assertIsNone(to_event({"timestamp": 0, "type": "begincast"}, 0, {}))
        self.assertIsNone(to_event({"timestamp": 0, "type": "resourcechange", "resourceChangeType": 0}, 0, {}))

    def test_keystone_fight_is_a_key(self):
        # WCL reports a whole key as one fight whose encounterID is the dungeon's.
        class FakeClient:
            def query(self, q, v):
                return {"reportData": {"report": {"masterData": {"actors": [{"id": 7, "name": "Me"}]}}}}

            def fight(self, code, fid):
                return {"id": 15, "encounterID": 12993, "name": "Altar of Fangs", "difficulty": 10, "kill": True,
                        "startTime": 0, "endTime": 60000, "keystoneLevel": 23}

            def abilities(self, code):
                return {}

            def events(self, *a, **k):
                return iter(())

        fight, player = load_fight(FakeClient(), "x", 15, "Me")
        self.assertEqual((fight.kind, fight.content, fight.label, player),
                         ("mythic_plus", "mplus", "Altar of Fangs +23", "wcl:7"))


if __name__ == "__main__":
    unittest.main()
