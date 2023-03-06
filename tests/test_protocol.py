"""Tests for protocol parsing."""
import unittest
from pykmn.engine.protocol import parse_protocol
from pykmn.data.gen1 import LIBPKMN_SPECIES_IDS, LIBPKMN_MOVE_IDS, TYPES
from pykmn.data.protocol import MESSAGES, REASONS
from typing import List

# TODO: unit tests for LastMiss etc
# TODO: replace hardcoded Reasons


class TestProtocolParsing(unittest.TestCase):
    """Test parsing protocol to PS protocol messages."""

    def case(self, protocol: List[int], expected: List[str]):
        """Assert that the protocol parses to the expected message."""
        self.assertListEqual(parse_protocol(protocol), expected)

    def test_move(self):
        """Should parse a |move| message."""
        self.case(
            [MESSAGES.index('Move'), 1, 94, 9, 0],
            ["|move|p1a: Pokémon #1|Psychic|p2a: Pokémon #1"],
        )
        self.case(
            [MESSAGES.index('Move'), 3, 126, 9, 1, 118],
            ["|move|p1a: Pokémon #3|Fire Blast|p2a: Pokémon #1|[from] Metronome"],
        )

    def test_switch(self):
        """Should parse a |switch| message."""
        self.case([
            MESSAGES.index('Switch'), 3, LIBPKMN_SPECIES_IDS['Charizard'], 73,
            189 & 0xFF, 189 >> 8, 314 & 0xFF, 314 >> 8, 128
        ], ["|switch|p1a: Pokémon #3|Charizard, L73|189/314 tox"])

    def test_cant(self):
        """Should parse a |cant| message."""
        self.case([MESSAGES.index('Cant'), 9, 7], ["|cant|p2a: Pokémon #1|nopp"])
        # Disable case
        self.case(
            [MESSAGES.index('Cant'), 9, 5, LIBPKMN_MOVE_IDS['Acid Armor']],
            ["|cant|p2a: Pokémon #1|Disable|Acid Armor"]
        )

    def test_faint(self):
        """Should parse a |faint| message."""
        self.case([MESSAGES.index('Faint'), 13], ["|faint|p2a: Pokémon #5"])

    def test_turn(self):
        """Should parse a |turn| message."""
        for turn in [0, 1, 50, 27453]:
            self.case([MESSAGES.index('Turn'), turn & 0xFF, turn >> 8], [f"|turn|{turn}"])

    def test_win(self):
        """Should parse a |win message."""
        self.case([MESSAGES.index('Win'), 0], ["|win|p1"])

    def test_tie(self):
        """Should parse a |tie message."""
        self.case([MESSAGES.index('Tie')], ["|tie"])

    def test_damage(self):
        """Should parse a |-damage| message."""
        self.case(
            [MESSAGES.index('Damage'), 9, 0, 0, 250, 2, 0, 0],
            ["|-damage|p2a: Pokémon #1|0/762"],
        )
        self.case(
            [MESSAGES.index('Damage'), 4, 63 & 0xFF, 63 >> 8, 250, 2, 16, 3],
            ["|-damage|p1a: Pokémon #4|63/762 brn|[from] confusion"],
        )
        # Recoil case
        self.case(
            [MESSAGES.index('Damage'), 4, 382 & 0xFF, 382 >> 8, 30, 2, 64, 5, 10],
            ["|-damage|p1a: Pokémon #4|382/542 par|[from] recoil|[of] p2a: Pokémon #2"],
        )

    def test_heal(self):
        """Should parse a |-heal| message."""
        # base case
        self.case(
            [MESSAGES.index('Heal'), 9, 91, 0, 30, 1, 8, 0],
            ["|-heal|p2a: Pokémon #1|91/286 psn"]
        )
        # silent case
        self.case(
            [MESSAGES.index('Heal'), 9, 91, 0, 30, 1, 4, 1],
            ["|-heal|p2a: Pokémon #1|91/286 slp|[silent]"],
        )
        # from drain case
        self.case(
            [MESSAGES.index('Heal'), 2, 91, 0, 30, 1, 16, 2, 12],
            ["|-heal|p1a: Pokémon #2|91/286 brn|[from] drain|[of] p2a: Pokémon #4"],
        )

    @unittest.skip("Not yet implemented.")
    def test_status(self):
        """Should parse a |-status| message."""
        self.case([MESSAGES.index('Status'), 9, 4, 0], ["|-status|p2a: Pokémon #1|slp"])
        self.case([MESSAGES.index('Status'), 9, 8, 0], ["|-status|p2a: Pokémon #1|psn"])
        self.case([MESSAGES.index('Status'), 9, 16, 1], ["|-status|p2a: Pokémon #1|brn|silent"])
        self.case([MESSAGES.index('Status'), 9, 32, 0], ["|-status|p2a: Pokémon #1|frz"])
        self.case([MESSAGES.index('Status'), 9, 64, 1], ["|-status|p2a: Pokémon #1|par|silent"])
        self.case(
            [MESSAGES.index('Status'), 9, 128, 2, LIBPKMN_MOVE_IDS['Toxic']],
            ["|-status|p2a: Pokémon #1|tox|[from] Toxic"],
        )

    @unittest.skip("Not yet implemented.")
    def test_curestatus(self):
        """Should parse a |-curestatus| message."""
        self.case([MESSAGES.index('CureStatus'), 10, 4, 0], ["|-curestatus|p2a: Pokémon #2|slp"])
        self.case([MESSAGES.index('CureStatus'), 11, 8, 0], ["|-curestatus|p2a: Pokémon #3|psn"])
        self.case(
            [MESSAGES.index('CureStatus'), 6, 16, 1],
            ["|-curestatus|p1a: Pokémon #6|brn|[msg]"],
        )
        self.case(
            [MESSAGES.index('CureStatus'), 5, 32, 2],
            ["|-curestatus|p1a: Pokémon #5|frz|[silent]"],
        )

    @unittest.skip("Not yet implemented.")
    def test_boost_unboost(self):
        """Should parse |-boost| and |-unboost| messages."""
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('Rage'), 7],
            ["|-boost|p1a: Pokémon #3|atk|1|[from] Rage"],
        )
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('Attack'), 4],
            ["|-unboost|p1a: Pokémon #3|atk|2"],
        )
        # Defense
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('Defense'), 12],
            ["|-boost|p1a: Pokémon #3|def|6"],
        )
        # Speed
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('Speed'), 3],
            ["|-unboost|p1a: Pokémon #3|spe|3"],
        )
        # Special Attack
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('SpecialAttack'), 8],
            ["|-boost|p1a: Pokémon #3|spa|2"],
        )
        # Special Defense
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('SpecialDefense'), 2],
            ["|-unboost|p1a: Pokémon #3|spd|4"]
        ),
        # Accuracy
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('Accuracy'), 1],
            ["|-unboost|p1a: Pokémon #3|accuracy|5"],
        )
        # Evasion
        self.case(
            [MESSAGES.index('Boost'), 3, REASONS['Boost'].index('Evasion'), 5],
            ["|-unboost|p1a: Pokémon #3|evasion|1"],
        )

    @unittest.skip("Not yet implemented.")
    def test_clearallboost(self):
        """Should parse a |-clearallboost| message."""
        self.case([MESSAGES.index('ClearAllBoost')], ["|-clearallboost"])

    @unittest.skip("Not yet implemented.")
    def test_fail(self):
        """Should parse a |-fail| message."""
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('None')],
            ["|-fail|p2a: Pokémon #2"],
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Sleep')],
            ["|-fail|p2a: Pokémon #2|slp"]
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Paralysis')],
            ["|-fail|p2a: Pokémon #2|par"]
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Freeze')],
            ["|-fail|p2a: Pokémon #2|frz"]
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Burn')],
            ["|-fail|p2a: Pokémon #2|brn"]
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Poison')],
            ["|-fail|p2a: Pokémon #2|psn"]
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Toxic')],
            ["|-fail|p2a: Pokémon #2|tox"],
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Substitute')],
            ["|-fail|p2a: Pokémon #2|move: Substitute"],
        )
        self.case(
            [MESSAGES.index('Fail'), 10, REASONS['Fail'].index('Weak')],
            ["|-fail|p2a: Pokémon #2|move: Substitute|[weak]"],
        )

    @unittest.skip("Not yet implemented.")
    def test_miss(self):
        """Should parse a |-miss| message."""
        self.case([MESSAGES.index('Miss'), 14], ["|-miss|p2a: Pokémon #6"])

    @unittest.skip("Not yet implemented.")
    def test_hitcount(self):
        """Should parse a |-hitcount| message."""
        self.case([MESSAGES.index('HitCount'), 1, 3], ["|-hitcount|p1a: Pokémon #1|3"])

    @unittest.skip("Not yet implemented.")
    def test_prepare(self):
        """Should parse a |-prepare| message."""
        self.case(
            [MESSAGES.index('Prepare'), 5, LIBPKMN_MOVE_IDS['Solar Beam']],
            ["|-prepare|p1a: Pokémon #5|Solar Beam"]
        )

    @unittest.skip("Not yet implemented.")
    def test_mustrecharge(self):
        """Should parse a |-mustrecharge| message."""
        self.case([MESSAGES.index('MustRecharge'), 10], ["|-mustrecharge|p2a: Pokémon #2"])

    @unittest.skip("Not yet implemented.")
    def test_active(self):
        """Should parse an |-activate| message."""
        self.case(
            [MESSAGES.index('Activate'), 10, REASONS['Activate'].index('Bide')],
            ["|-activate|p2a: Pokémon #2|Bide"],
        )
        self.case(
            [MESSAGES.index('Activate'), 10, REASONS['Activate'].index('Confusion')],
            ["|-activate|p2a: Pokémon #2|confusion"],
        )
        self.case(
            [MESSAGES.index('Activate'), 10, REASONS['Activate'].index('Haze')],
            ["|-activate|p2a: Pokémon #2|move: Haze"],
        )
        self.case(
            [MESSAGES.index('Activate'), 10, REASONS['Activate'].index('Mist')],
            ["|-activate|p2a: Pokémon #2|move: Mist"],
        )
        self.case(
            [MESSAGES.index('Activate'), 10, REASONS['Activate'].index('Struggle')],
            ["|-activate|p2a: Pokémon #2|move: Struggle"],
        )
        self.case(
            [MESSAGES.index('Activate'), 10, REASONS['Activate'].index('Substitute')],
            ["|-activate|p2a: Pokémon #2|Substitute|[damage]"],
        )
        self.case(
            [MESSAGES.index('Activate'), 10, REASONS['Activate'].index('Splash')],
            ["|-activate|p2a: Pokémon #2||move: Splash"],
        )

    @unittest.skip("Not yet implemented.")
    def test_fieldactivate(self):
        """Should parse a |-fieldactivate| message."""
        self.case([MESSAGES.index('FieldActivate')], ["|-fieldactivate|"])

    @unittest.skip("Not yet implemented.")
    def test_start(self):
        """Should parse a |-start| message."""
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('Bide')],
            ["|-start|p1a: Pokémon #4|Bide"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('Confusion')],
            ["|-start|p1a: Pokémon #4|confusion"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('ConfusionSilent')],
            ["|-start|p1a: Pokémon #4|confusion|[silent]"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('FocusEnergy')],
            ["|-start|p1a: Pokémon #4|move: Focus Energy"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('LeechSeed')],
            ["|-start|p1a: Pokémon #4|move: Leech Seed"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('LightScreen')],
            ["|-start|p1a: Pokémon #4|Light Screen"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('Mist')],
            ["|-start|p1a: Pokémon #4|Mist"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('Reflect')],
            ["|-start|p1a: Pokémon #4|Reflect"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('Substitute')],
            ["|-start|p1a: Pokémon #4|Substitute"],
        )
        self.case([
            MESSAGES.index('Start'), 4, REASONS['Start'].index('TypeChange'),
            TYPES.index('Fire') >> 4 + TYPES.index('Electric'),
        ], ["|-start|p1a: Pokémon #4|typechange|Fire/Electric|[from] move: Conversion|[of]"])
        self.case(
            [
                MESSAGES.index('Start'), 4, REASONS['Start'].index('Disable'),
                LIBPKMN_MOVE_IDS['Splash']
            ],
            ["|-start|p1a: Pokémon #4|Disable|move: Splash"],
        )
        self.case(
            [MESSAGES.index('Start'), 4, REASONS['Start'].index('Mimic'), LIBPKMN_MOVE_IDS['Surf']],
            ["|-start|p1a: Pokémon #4|Mimic|move: Surf"],
        )

    @unittest.skip("Not yet implemented.")
    def test_end(self):
        """Should parse a |-end| message."""
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('Disable')],
            ["|-end|p1a: Pokémon #5|Disable"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('Confusion')],
            ["|-end|p1a: Pokémon #5|confusion"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('Bide')],
            ["|-end|p1a: Pokémon #5|move: Bide"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('Substitute')],
            ["|-end|p1a: Pokémon #5|Substitute"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('DisableSilent')],
            ["|-end|p1a: Pokémon #5|Disable|[silent]"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('ConfusionSilent')],
            ["|-end|p1a: Pokémon #5|confusion|[silent]"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('Mist')],
            ["|-end|p1a: Pokémon #5|mist|[silent]"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('FocusEnergy')],
            ["|-end|p1a: Pokémon #5|focusenergy|[silent]"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('LeechSeed')],
            ["|-end|p1a: Pokémon #5|leechseed|[silent]"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('Toxic')],
            ["|-end|p1a: Pokémon #5|Toxic counter|[silent]"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('LightScreen')],
            ["|-end|p1a: Pokémon #5|lightscreen|[silent]"],
        )
        self.case(
            [MESSAGES.index('End'), 5, REASONS['End'].index('Reflect')],
            ["|-end|p1a: Pokémon #5|reflect|[silent]"],
        )

    @unittest.skip("Not yet implemented.")
    def test_ohko(self):
        """Should parse a |-ohko| message."""
        self.case([MESSAGES.index('OHKO')], ["|-ohko|"])

    @unittest.skip("Not yet implemented.")
    def test_crit(self):
        """Should parse a |-crit| message."""
        self.case([MESSAGES.index('Crit'), 11], ["|-crit|p2a: Pokémon #3"])

    def test_supereffective(self):
        """Should parse a |-supereffective| message."""
        self.case([MESSAGES.index('SuperEffective'), 9], ["|-supereffective|p2a: Pokémon #1"])

    @unittest.skip("Not yet implemented.")
    def test_resisted(self):
        """Should parse a |-resisted| message."""
        self.case([MESSAGES.index('Resisted'), 10], ["|-resisted|p2a: Pokémon #2"])

    @unittest.skip("Not yet implemented.")
    def test_immune(self):
        """Should parse a |-immune| message."""
        self.case(
            [MESSAGES.index('Immune'), 11, REASONS['Immune'].index('None')],
            ["|-immune|p2a: Pokémon #3"]
        )
        self.case(
            [MESSAGES.index('Immune'), 11, REASONS['Immune'].index('OHKO')],
            ["|-immune|p2a: Pokémon #3|[ohko]"]
        )

    @unittest.skip("Not yet implemented.")
    def test_transform(self):
        """Should parse a |-transform| message."""
        self.case(
            [MESSAGES.index('Transform'), 2, 13],
            ["|-transform|p1a: Pokémon #2|p2a: Pokémon #6"]
        )
