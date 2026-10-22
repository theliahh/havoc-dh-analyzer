import os
import tempfile
import unittest

from havoc_analyzer import events as ev
from havoc_analyzer.combatlog import find_havoc_players, parse, split_fields

ME = "Player-3684-0EAAAF1A"
BOSS = "Creature-0-3882-3004-17581-259927-0000594F48"
ADV = "{me},0000000000000000,916561,916561,3302,640,1127,700,453,0,17,{fury},120,30,196.05,-5.64,2606,0.4260,328"


def line(sec: float, body: str) -> str:
    m, s = divmod(sec, 60)
    return f"10/21/2026 20:{int(m):02d}:{s:06.3f}-4  {body}"


def cast(sec, spell_id, name, fury=100, target=BOSS, target_name="Boss"):
    return line(sec, f'SPELL_CAST_SUCCESS,{ME},"Theliahh-Mal\'Ganis-US",0x511,0x80000000,{target},"{target_name}",'
                     f'0x10a48,0x80000000,{spell_id},"{name}",0x7c,' + ADV.format(me=ME, fury=fury))


def aura(sec, kind, spell_id, name):
    return line(sec, f'SPELL_AURA_{kind},{ME},"Theliahh-Mal\'Ganis-US",0x511,0x80000000,{ME},'
                     f'"Theliahh-Mal\'Ganis-US",0x511,0x80000000,{spell_id},"{name}",0x1,BUFF')


def damage(sec, spell_id, name, amount):
    adv = (f"{BOSS},0000000000000000,472833073,473413140,0,0,1470,0,0,0,3,0,100,0,206.68,-0.05,2606,3.1241,92")
    return line(sec, f'SPELL_DAMAGE,{ME},"Theliahh-Mal\'Ganis-US",0x511,0x80000000,{BOSS},"Boss",0x10a48,'
                     f'0x80000000,{spell_id},"{name}",0x7c,{adv},{amount},{amount},-1,124,0,0,0,nil,nil,nil,ST')


SAMPLE = [
    line(0, "COMBAT_LOG_VERSION,22,ADVANCED_LOG_ENABLED,1,BUILD_VERSION,12.1.5,PROJECT_ID,1"),
    line(0.1, 'ZONE_CHANGE,2987,"The Tidebound Grotto",8'),
    line(1, 'CHALLENGE_MODE_START,"The Tidebound Grotto",2987,505,12,[10,147,9]'),
    line(1.001, f"COMBATANT_INFO,{ME},0,512,2503,43234,640,0,0,0,0,1434,1434,1434,85,0,600,600,600,167,1078,169,"
                "169,169,1127,577,[(90914,112823,1),(90919,112828,1)],(0,1,2,3),[],[],38,0,0,0"),
    cast(2, 442294, "Reaver's Glaive"),
    cast(3, 210152, "Death Sweep"),
    cast(3, 185123, "Throw Glaive", target="0000000000000000", target_name="nil"),   # talent-triggered
    damage(3.2, 210152, "Death Sweep", 50000),
    line(10, 'ENCOUNTER_START,3379,"Nymrissa Wavecaller",8,5,2987'),
    cast(11, 198013, "Eye Beam"),
    aura(11.1, "APPLIED", 162264, "Metamorphosis"),
    cast(14, 200166, "Metamorphosis", fury=60),
    cast(20, 185123, "Throw Glaive"),                                                # pressed
    aura(30, "REMOVED", 162264, "Metamorphosis"),
    line(40, 'ENCOUNTER_END,3379,"Nymrissa Wavecaller",8,5,1,30000'),
    line(41, 'ENCOUNTER_START,3380,"Reset",8,5,2987'),
    line(42, 'ENCOUNTER_END,3380,"Reset",8,5,0,1000'),
    line(50, f'UNIT_DIED,0000000000000000,nil,0x80000000,0x80000000,{ME},"Theliahh-Mal\'Ganis-US",0x511,0x80000000,0'),
    line(60, "CHALLENGE_MODE_END,2987,1,12,59000,3500.5,600.0"),
]


class CombatLogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fd, cls.path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write("\n".join(SAMPLE) + "\n")
        cls.log = parse(cls.path)

    @classmethod
    def tearDownClass(cls):
        os.remove(cls.path)

    def test_split_fields_respects_quotes_and_brackets(self):
        self.assertEqual(split_fields('A,"b,c",[(1,2),(3,4)],d'), ["A", "b,c", "[(1,2),(3,4)]", "d"])

    def test_finds_havoc_player(self):
        self.assertEqual(find_havoc_players(self.path), {ME: "Theliahh-Mal'Ganis-US"})

    def test_key_with_boss_inside_and_reset_dropped(self):
        self.assertEqual(self.log.build, "12.1.5")
        self.assertEqual(len(self.log.fights), 1)
        key = self.log.fights[0]
        self.assertEqual((key.kind, key.keystone_level, key.success), ("mythic_plus", 12, True))
        self.assertAlmostEqual(key.duration, 59.0)
        self.assertEqual([c.name for c in key.children], ["Nymrissa Wavecaller"])
        boss = key.children[0]
        self.assertTrue(boss.in_key)
        self.assertEqual(boss.content, "mplus")
        self.assertAlmostEqual(boss.duration, 30.0)

    def test_events_normalized(self):
        key = self.log.fights[0]
        casts = [e for e in key.events if e.type == ev.CAST]
        self.assertEqual(casts[0].spell_name, "Reaver's Glaive")
        self.assertEqual(casts[0].fury, 100)
        self.assertEqual(casts[0].dst, BOSS)
        meta = next(e for e in casts if e.spell_id == 200166)
        self.assertEqual(meta.fury, 60)
        dmg = next(e for e in key.events if e.type == ev.DAMAGE)
        self.assertEqual(dmg.amount, 50000)
        self.assertTrue(any(e.type == ev.DIED and e.dst == ME for e in key.events))
        # Boss pull times are relative to the pull, key times to the key start.
        boss_cast = next(e for e in key.children[0].events if e.spell_id == 198013)
        self.assertAlmostEqual(boss_cast.t, 1.0)


if __name__ == "__main__":
    unittest.main()
