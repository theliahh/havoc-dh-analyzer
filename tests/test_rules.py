import unittest

from havoc_analyzer import events as ev
from havoc_analyzer.benchmarks import Benchmark
from havoc_analyzer.events import Event, Fight
from havoc_analyzer.rules import FLAG, INFO, OK, evaluate
from havoc_analyzer.summary import build
from havoc_analyzer.wcl_source import load_fight, to_event

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


class WclAdapterTest(unittest.TestCase):
    def test_cast_with_fury(self):
        raw = {"timestamp": 12500, "type": "cast", "sourceID": 7, "targetID": 99, "abilityGameID": 200166,
               "classResources": [{"amount": 112, "max": 120, "type": 17}]}
        e = to_event(raw, 10000, {200166: "Metamorphosis"})
        self.assertEqual((e.t, e.type, e.src, e.dst, e.spell_name, e.fury), (2.5, ev.CAST, "wcl:7", "wcl:99",
                                                                              "Metamorphosis", 112))

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
