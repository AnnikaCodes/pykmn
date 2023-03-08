"""Battle simulation for Generation I."""
from _pkmn_engine_bindings import lib, ffi  # type: ignore
from pykmn.engine.common import Result, Player, ChoiceType, Softlock, Choice, \
    pack_u16_as_bytes, unpack_u16_from_bytes, pack_two_u4s, unpack_two_u4s # noqa: F401
from pykmn.engine.rng import ShowdownRNG
from pykmn.data.gen1 import Gen1StatData, MOVE_IDS, SPECIES_IDS, \
    SPECIES, TYPES, MOVES, LAYOUT_OFFSETS, LAYOUT_SIZES, MOVE_ID_LOOKUP, SPECIES_ID_LOOKUP

from typing import List, Tuple, cast, TypedDict
from bitstring import Bits  # type: ignore
import random
from enum import Enum
import math

# optimization possible here: don't copy in intialization if it's all 0 anyway?

MovePP = Tuple[str, int]
FullMoveset = Tuple[str, str, str, str]
Moveset = FullMoveset | Tuple[str] | Tuple[str, str] | Tuple[str, str, str]

class _InnerStatusEnum(Enum):
    HEALTHY = 0
    SLEEP = 4
    POISON = 8
    BURN = 16
    FREEZE = 32
    PARALYSIS = 64


class Status:
    """A Pokémon's status condition."""

    value: _InnerStatusEnum
    duration: int | None
    is_self_inflicted: bool | None

    # Tuple is for sleep, (duration, is_self_inflicted)
    def __init__(self, value: _InnerStatusEnum | Tuple[int, bool]):
        """Create a new Status object."""
        if isinstance(value, tuple):
            self.value = _InnerStatusEnum.SLEEP
            self.duration = value[0]
            self.is_self_inflicted = value[1]
        else:
            self.value = value
            self.duration = None
            self.is_self_inflicted = None

    @staticmethod
    def paralyzed():
        """Return a Status object for paralysis."""
        return Status(_InnerStatusEnum.PARALYSIS)

    @staticmethod
    def burned():
        """Return a Status object for burn."""
        return Status(_InnerStatusEnum.BURN)

    @staticmethod
    def poisoned():
        """Return a Status object for poison."""
        return Status(_InnerStatusEnum.POISON)

    @staticmethod
    def frozen():
        """Return a Status object for freeze."""
        return Status(_InnerStatusEnum.FREEZE)

    @staticmethod
    def healthy():
        """Return a Status object for healthy."""
        return Status(_InnerStatusEnum.HEALTHY)

    @staticmethod
    def sleep(duration: int, is_self_inflicted: bool):
        """Return a Status object for sleep."""
        return Status((duration, is_self_inflicted))

    def to_int(self) -> int:
        """Convert to int for libpkmn."""
        if self.duration is not None:
            return (0x80 | self.duration) if self.is_self_inflicted else self.duration
        return self.value.value


# should this not be a class and just a move-to-int function?
class Move:
    """A Pokémon move."""

    def __init__(self, name: str):
        """Create a new Move object."""
        if name not in MOVE_IDS:
            raise ValueError(f"'{name}' is not a valid move in Generation I.")
        self.name = name
        self.id = MOVE_IDS[name]

    def _to_bits(self) -> Bits:
        """Pack the move into a bitstring."""
        return Bits(uintne=self.id, length=8)

    def _to_slot_bits(self, pp: int | None = None) -> Bits:
        """Pack the move into a bitstring with PP."""
        if pp is None:
            pp = math.trunc(MOVES[self.name] * 8 / 5)
        return Bits().join([
            self._to_bits(),
            Bits(uintne=pp, length=8)
        ])

    def __repr__(self) -> str:
        """Return a string representation of the move."""
        return f"Move({self.name}, id={self.id})"


def statcalc(
    base_value: int,
    is_HP: bool = False,
    level: int = 100,
    dv: int = 15,
    experience: int = 65535
) -> int:
    """Calculate a Pokémon's stats based on its level, base stats, and so forth.

    Args:
        base_value (int): The base value of the stat for this species.
        dv (int): The Pokémon's DV for this stat.
        level (int): The level of the Pokémon.
        is_HP (bool, optional): Whether the stat is HP or not. Defaults to False.

    Returns:
        int: The value of the stat
    """
    # 64 = std.math.sqrt(exp) / 4 when exp = 65535 (0xFFFF)
    # const core: u32 = (2 *% (@as(u32, base) +% dv)) +% @as(u32, (std.math.sqrt(exp) / 4));
    core = (2 * (base_value + dv)) + math.trunc(math.sqrt(experience) / 4)
    # const factor: u32 = if (std.mem.eql(u8, stat, "hp")) level + 10 else 5;
    factor = (level + 10) if is_HP else 5
    # return @truncate(T, core *% @as(u32, level) / 100 +% factor);
    return (core * math.trunc(level / 100) + factor) % 2**16


SpeciesName = str
ExtraPokemonData = TypedDict('ExtraPokemonData', {
    'hp': int, 'status': int, 'level': int, 'stats': Gen1StatData,
    'types': Tuple[str, str], 'move_pp': Tuple[int, int, int, int],
    'dvs': Gen1StatData, 'exp': Gen1StatData,
}, total=False)
PokemonInitializer = Tuple[SpeciesName, Moveset] | Tuple[SpeciesName, Moveset, ExtraPokemonData]

# TODO: make all these classes simple wrappers around binary and have staticmethods to generate them
class Pokemon:
    """A Pokémon in a Generation I battle."""

    def __init__(self, _bytes):
        """Construct a new Pokemon object.

        Users shouldn't use this, but instead use Pokemon.new() and Pokemon.initialize(),
        or invoke a Battle/Side constructor directly.
        """
        assert len(_bytes) == LAYOUT_SIZES['Pokemon'], \
            f"Pokemon data bytes must be {LAYOUT_SIZES['Pokemon']} long."
        self._bytes = _bytes


    @staticmethod
    def new(initial_data: PokemonInitializer):
        """Creates a new Pokémon and initializes it."""
        p = Pokemon(_bytes=ffi.new("uint8_t[]", LAYOUT_SIZES['Pokemon']))
        p.initialize(initial_data)
        return p

    def initialize(self, data: PokemonInitializer):
        """Initializes the Pokémon's data, overwriting its data buffer with new values.

        Stats, types, and move PP are inferred based on the provided species and move names,
        but can optionally be specified.

        Args:
            data (PokemonInitializer): The data to initialize the Pokémon with.
                The first value should be the species name,
                and the second value should be a Moveset with the Pokémon's moves.
                Optionally, a third value can be specified,
                a dictionary with any of the following keys:
                    * hp (int): The amount of HP the Pokémon has; defaults to its max HP.
                    * status (int): The Pokémon's status code. Defaults to healthy.
                    * level (int): The Pokémon's level. Defaults to 100.
                    * stats (Gen1StatData): The Pokémon's stats.
                        By default, will be determined based on its species & level.
                    * types (Tuple[str, str]): The Pokémon's types.
                        By default, determined by its species.
                    * move_pp (Tuple[int, int, int, int]): PP values for each move.
                        By default, determined by the move's max PP.
                    * dvs (Gen1StatData): The Pokémon's DVs. Defaults to 15 in all stats.
                    * exp (Gen1StatData): The Pokémon's stat experience. Defaults to 65535 in all.
        """

        hp = None
        status = 0
        level = 100
        stats = None
        types = None
        move_pp = None
        dvs: Gen1StatData = {'hp': 15, 'atk': 15, 'def': 15, 'spe': 15, 'spc': 15}
        exp: Gen1StatData = {'hp': 65535, 'atk': 65535, 'def': 65535, 'spe': 65535, 'spc': 65535}
        if len(data) == 3:
            species_name, move_names, extra_data = \
                cast(Tuple[SpeciesName, Moveset, ExtraPokemonData], data)
            if 'hp' in extra_data:
                hp = extra_data['hp']
            if 'status' in extra_data:
                status = extra_data['status']
            if 'level' in extra_data:
                level = extra_data['level']
            if 'stats' in extra_data:
                stats = extra_data['stats']
            if 'types' in extra_data:
                types = extra_data['types']
            if 'move_pp' in extra_data:
                move_pp = extra_data['move_pp']
            if 'dvs' in extra_data:
                dvs = extra_data['dvs']
            if 'exp' in extra_data:
                exp = extra_data['exp']
        else:
            species_name, move_names = cast(Tuple[SpeciesName, Moveset], data)

        if species_name == 'None':
            if stats is None:
                stats = {'hp': 0, 'atk': 0, 'def': 0, 'spe': 0, 'spc': 0}
            if types is None:
                types = ('Normal', 'Normal')
        elif species_name in SPECIES:
            if stats is None:
                # optimization possible here:
                # skip the copy and just mandate that callers supply base stats
                stats = SPECIES[species_name]['stats'].copy()
                for stat in stats:
                    stats[stat] = statcalc(  # type: ignore
                        stats[stat],  # type: ignore
                        stat == 'hp',
                        level,
                        dvs[stat], # type: ignore
                        exp[stat], # type: ignore
                    )
            if types is None:
                first_type = SPECIES[species_name]['types'][0]
                second_type = SPECIES[species_name]['types'][1] \
                    if len(SPECIES[species_name]['types']) > 1 else first_type
                types = (first_type, second_type)
        else:
            raise ValueError(f"'{species_name}' is not a valid species in Generation I.")

        if hp is None:
            hp = stats['hp']

        offset = LAYOUT_OFFSETS['Pokemon']['stats']
        # pack stats
        for stat in ['hp', 'atk', 'def', 'spe', 'spc']:
            self._bytes[offset:offset + 2] = pack_u16_as_bytes(stats[stat]) # type: ignore
            offset += 2
        assert offset == LAYOUT_OFFSETS['Pokemon']['moves']

        # pack moves
        for move_index in range(4):
            if move_index >= len(move_names):
                move_id = 0
                pp = 0
            else:
                move_id = MOVE_IDS[move_names[move_index]]
                if move_pp is None:
                    if move_id == 0:  # None move
                        pp = 0
                    else:
                        pp = math.floor(MOVES[move_names[move_index]] * 8 / 5)
                else:
                    pp = move_pp[move_index]
            self._bytes[offset] = move_id
            offset += 1
            self._bytes[offset] = pp
            offset += 1
        assert offset == LAYOUT_OFFSETS['Pokemon']['hp']

        # pack HP
        self._bytes[offset:offset + 2] = pack_u16_as_bytes(hp)
        offset += 2
        assert offset == LAYOUT_OFFSETS['Pokemon']['status']

        # pack status
        self._bytes[offset] = status
        offset += 1
        assert offset == LAYOUT_OFFSETS['Pokemon']['species']

        # pack species
        self._bytes[offset] = SPECIES_IDS[species_name]
        offset += 1
        assert offset == LAYOUT_OFFSETS['Pokemon']['types']

        # pack types
        self._bytes[offset] = pack_two_u4s(TYPES.index(types[0]), TYPES.index(types[1]))
        offset += 1
        assert offset == LAYOUT_OFFSETS['Pokemon']['level']

        # pack level
        self._bytes[offset] = level
        offset += 1
        assert offset == LAYOUT_SIZES['Pokemon']

    def stats(self) -> Gen1StatData:
        """Get the Pokémon's current stats.

        Returns:
            Gen1StatData: The current stats.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['stats']
        stats = {}
        for stat in ['hp', 'atk', 'def', 'spe', 'spc']:
            (byte1, byte2) = self._bytes[offset:offset + 2]
            stats[stat] = unpack_u16_from_bytes(byte1, byte2)
            offset += 2
        return cast(Gen1StatData, stats)

    def moves(self) -> Moveset:
        """
        Get the Pokémon's moves.

        Returns:
            Tuple[str, str, str, str]: The Pokémon's moves.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['moves']
        return tuple(
            MOVE_ID_LOOKUP[self._bytes[offset + n]] \
                for n in range(0, 8, 2) \
                if self._bytes[offset + n] != 0
        ) # type: ignore

    def pp_left(self) -> Tuple[int, ...]:
        """Get the Pokémon's PP left for each move.

        Returns:
            Tuple[int, ...]: The PP left for each move. Length is equal to the number of moves.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['moves']
        return tuple(
            self._bytes[offset + n] \
                for n in range(1, 9, 2) \
                if self._bytes[offset + n - 1] != 0 # if move exists
        )

    def moves_with_pp(self) -> Tuple[MovePP, ...]:
        """Get the Pokémon's moves with their PP left.

        Returns:
            Tuple[MovePP, MovePP, MovePP, MovePP]: The moves with their PP left.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['moves']
        return tuple(
            (MOVE_ID_LOOKUP[self._bytes[offset + n]], cast(int, self._bytes[offset + n + 1])) \
                for n in range(0, 8, 2) \
                if self._bytes[offset + n] != 0
        )


    def hp(self) -> int:
        """Get the Pokémon's current HP.

        Returns:
            int: The current HP.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['hp']
        (byte1, byte2) = self._bytes[offset:offset + 2]
        return unpack_u16_from_bytes(byte1, byte2)

    # TODO: good status parsing
    def status(self) -> int:
        """Get the Pokémon's status.

        Returns:
            int: The status.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['status']
        return self._bytes[offset]

    def species(self) -> str:
        """Get the Pokémon's species.

        Returns:
            str: The species.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['species']
        return SPECIES_ID_LOOKUP[self._bytes[offset]]

    def types(self) -> Tuple[str, str]:
        """Get the Pokémon's types.

        Returns:
            Tuple[str, str]: The types.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['types']
        (type1, type2) = unpack_two_u4s(self._bytes[offset])
        return (TYPES[type1], TYPES[type2])

    def level(self) -> int:
        """Get the Pokémon's level.

        Returns:
            int: The level.
        """
        offset = LAYOUT_OFFSETS['Pokemon']['level']
        return self._bytes[offset]


def moves(*args):
    """Convert a list of move names into a list of Move objects."""
    return [Move(move) for move in args]

# MAJOR TODO!
# * reverse it so that there are _from_bits() methods as well
# * write unit tests
# * make this use raw memory and bit twiddling instead of bitstring
#   * each class's constructor just takes bits and then there's a static method for generation
#   * getters should actually parse the bits
# * make all constructors check array lengths, etc, for validity
# * write a LOT of integration tests
# * maybe more documentation?


class Boosts:
    """A Pokémon's stat boosts."""

    attack: int
    defense: int
    speed: int
    special: int
    accuracy: int
    evasion: int

    def __init__(
        self,
        attack: int = 0,
        defense: int = 0,
        speed: int = 0,
        special: int = 0,
        accuracy: int = 0,
        evasion: int = 0,
    ):
        """Construct a new Boosts object."""
        self.attack = attack
        self.defense = defense
        self.speed = speed
        self.special = special
        self.accuracy = accuracy
        self.evasion = evasion

    def _to_bits(self) -> Bits:
        """Pack the boosts into a bitstring."""
        return Bits().join([
            Bits(int=self.attack, length=4),
            Bits(int=self.defense, length=4),
            Bits(int=self.speed, length=4),
            Bits(int=self.special, length=4),
            Bits(int=self.accuracy, length=4),
            Bits(int=self.evasion, length=4),
            Bits(intne=0, length=8),  # padding
        ])


class Volatiles:
    """A Pokémon's volatile statuses."""

    Bide: bool
    Thrashing: bool
    MultiHit: bool
    Flinch: bool
    Charging: bool
    Binding: bool
    Invulnerable: bool
    Confusion: bool

    Mist: bool
    FocusEnergy: bool
    Substitute: bool
    Recharging: bool
    Rage: bool
    LeechSeed: bool
    Toxic: bool
    LightScreen: bool

    Reflect: bool
    Transform: bool

    confusion: int
    attacks: int

    state: int
    substitute: int
    transform: int
    disabled_duration: int
    disabled_move: int
    toxic: int

    def __init__(
        self,
        Bide: bool = False,
        Thrashing: bool = False,
        MultiHit: bool = False,
        Flinch: bool = False,
        Charging: bool = False,
        Binding: bool = False,
        Invulnerable: bool = False,
        Confusion: bool = False,
        Mist: bool = False,
        FocusEnergy: bool = False,
        Substitute: bool = False,
        Recharging: bool = False,
        Rage: bool = False,
        LeechSeed: bool = False,
        Toxic: bool = False,
        LightScreen: bool = False,
        Reflect: bool = False,
        Transform: bool = False,
        confusion: int = 0,
        attacks: int = 0,
        state: int = 0,
        substitute: int = 0,
        transform: int = 0,
        disabled_duration: int = 0,
        disabled_move: int = 0,
        toxic: int = 0,
    ):
        """Construct a new Volatiles object."""
        self.Bide = Bide
        self.Thrashing = Thrashing
        self.MultiHit = MultiHit
        self.Flinch = Flinch
        self.Charging = Charging
        self.Binding = Binding
        self.Invulnerable = Invulnerable
        self.Confusion = Confusion
        self.Mist = Mist
        self.FocusEnergy = FocusEnergy
        self.Substitute = Substitute
        self.Recharging = Recharging
        self.Rage = Rage
        self.LeechSeed = LeechSeed
        self.Toxic = Toxic
        self.LightScreen = LightScreen
        self.Reflect = Reflect
        self.Transform = Transform
        self.confusion = confusion
        self.attacks = attacks
        self.state = state
        self.substitute = substitute
        self.transform = transform
        self.disabled_duration = disabled_duration
        self.disabled_move = disabled_move
        self.toxic = toxic

    def _to_bits(self) -> Bits:
        """Pack the volatiles into a bitstring."""
        bits = Bits().join([
            Bits(bool=self.Bide),
            Bits(bool=self.Thrashing),
            Bits(bool=self.MultiHit),
            Bits(bool=self.Flinch),
            Bits(bool=self.Charging),
            Bits(bool=self.Binding),
            Bits(bool=self.Invulnerable),
            Bits(bool=self.Confusion),
            Bits(bool=self.Mist),
            Bits(bool=self.FocusEnergy),
            Bits(bool=self.Substitute),
            Bits(bool=self.Recharging),
            Bits(bool=self.Rage),
            Bits(bool=self.LeechSeed),
            Bits(bool=self.Toxic),
            Bits(bool=self.LightScreen),
            Bits(bool=self.Reflect),
            Bits(bool=self.Transform),

            Bits(uint=self.confusion, length=3),
            Bits(uint=self.attacks, length=3),
            Bits(uintne=self.state, length=16),
            Bits(uintne=self.substitute, length=8),
            Bits(uint=self.transform, length=4),
            Bits(uint=self.disabled_duration, length=4),
            Bits(uint=self.disabled_move, length=3),
            Bits(uint=self.toxic, length=5),
        ])
        assert bits.length == 8 * 8, \
            f"Volatiles is {bits.length} bits long, but should be 64 bits long."
        return bits


# class ActivePokemon:
#     """idk anymore."""

#     stats: Gen1StatData
#     boosts: Boosts
#     volatiles: Volatiles
#     # int is the amount of PP they have left
#     moveslots: List[MoveSlot]

#     def __init__(
#         self,
#         name: str,
#         boosts: Boosts = Boosts(),
#         volatiles: Volatiles = Volatiles(),
#         moveslots=[(Move('None'), 0)] * 4,
#     ):
#         """Construct a new ActivePokemon object."""
#         if name not in SPECIES and name != 'None':
#             raise Exception(f"'{name}' is not a valid Pokémon name in Generation I.")

#         self.stats: Gen1StatData = {'hp': 0, 'atk': 0, 'def': 0, 'spc': 0, 'spe': 0}
#         if name != 'None':
#             self.types = SPECIES[name]['types']
#             for stat in SPECIES[name]['stats']:
#                 self.stats[stat] = statcalc(  # type: ignore
#                     base_value=SPECIES[name]['stats'][stat],  # type: ignore
#                     level=level,
#                     dv=dvs[stat],  # type: ignore
#                     is_HP=stat == 'hp',
#                 )
#         else:
#             self.types = ['Normal', 'Normal']

#         self.boosts = boosts
#         self.volatiles = volatiles
#         self.moveslots = moveslots


SideInitializerDict = TypedDict('SideInitializerDict', {
    'team': List[PokemonInitializer], 'last_selected_move': str, 'last_used_move': str,
})
SideInitializer = List[PokemonInitializer] | SideInitializerDict
class Side:
    """A side in a Generation I battle."""

    def __init__(self, _bytes):
        """Construct a new Side object.

        Users shouldn't use this, but instead use Side.new() and Sude.initialize(),
        or invoke a Battle constructor directly.
        """
        self._bytes = _bytes
        team = []
        offset = LAYOUT_OFFSETS['Side']['pokemon']
        for _ in range(6):
            team.append(Pokemon(self._bytes[offset:(offset + LAYOUT_SIZES['Pokemon'])]))
            offset += LAYOUT_SIZES['Pokemon']
        assert offset == LAYOUT_OFFSETS['Side']['active']
        self.team = tuple(team)

    @staticmethod
    def new(data: SideInitializer):
        """Creates a new Side and initializes it."""
        side = Side(_bytes=ffi.new("uint8_t[]", LAYOUT_SIZES['Side']))
        side.initialize(data)
        return side

    def initialize(self, data: SideInitializer):
        """Initializes the side.

        Args:
            data (SideInitializer): Either a list of PokemonInitializers or a dictionary. TODO: docs
        """
        if isinstance(data, dict):
            data_dict = cast(SideInitializerDict, data)
            if 'last_selected_move' in data_dict:
                self._bytes[LAYOUT_OFFSETS['Side']['last_selected_move']] = \
                   MOVE_IDS[data_dict['last_selected_move']]
            if 'last_used_move' in data:
                self._bytes[LAYOUT_OFFSETS['Side']['last_used_move']] = \
                    MOVE_IDS[data_dict['last_used_move']]
            team = data_dict['team']
        else:
            team = cast(List[PokemonInitializer], data)

        order = []
        for i, pokemon_data in enumerate(team):
            self.team[i].initialize(pokemon_data)
            order.append(i + 1)

        for i, slot in enumerate(order):
            self._bytes[LAYOUT_OFFSETS['Side']['order'] + i] = slot


    def last_used_move(self) -> str:
        """Gets the last move used by the side."""
        return MOVE_ID_LOOKUP[self._bytes[LAYOUT_OFFSETS['Side']['last_used_move']]]

    def last_selected_move(self) -> str:
        """Gets the last move selected by the side."""
        return MOVE_ID_LOOKUP[self._bytes[LAYOUT_OFFSETS['Side']['last_selected_move']]]


def _pack_stats(stats: Gen1StatData) -> Bits:
    """
    Pack the stats into a bitstring.

    Use the Battle() constructor instead.
    """
    bits = Bits().join([
        Bits(uintne=stats['hp'], length=16),
        Bits(uintne=stats['atk'], length=16),
        Bits(uintne=stats['def'], length=16),
        Bits(uintne=stats['spe'], length=16),
        Bits(uintne=stats['spc'], length=16),
    ])
    assert bits.length == 10 * 8, f"Stats length is {bits.length} bits, not {10 * 8} bits."
    return bits


def _pack_move_indexes(p1: int, p2: int) -> List[Bits]:
    """
    Pack the move indexes into a bitstring.

    Use the Battle() constructor instead.
    """
    length = 16  # TODO: support non -Dshowdown here
    return Bits().join([
        Bits(uintne=p1, length=length),
        Bits(uintne=p2, length=length),
    ])


class Battle:
    """A Generation I Pokémon battle."""

    _bits: Bits | None

    def __init__(
        self,
        p1_side: Side,
        p2_side: Side,
        start_turn: int = 0,
        last_damage: int = 0,
        p1_move_idx: int = 0,
        p2_move_idx: int = 0,
        # TODO: support non-Showdown RNGs
        rng: ShowdownRNG = ShowdownRNG(random.randrange(0, 2**64)),
    ):
        """Create a new Battle object."""
        # TODO: unit tests!
        # TODO: verify initial values
        # OK, let's initialize a battle.
        # https://github.com/pkmn/engine/blob/main/src/data/layout.json gives us the layout.
        # https://github.com/pkmn/engine/blob/main/src/lib/gen1/data.zig#L40-L48 also
        battle_data = Bits().join([
            Bits(bytes(p1_side._bytes)),                    # side 1
            Bits(bytes(p2_side._bytes)),                    # side 2
            Bits(uintne=start_turn, length=16),             # turn
            Bits(uintne=last_damage, length=16),            # last damage
            _pack_move_indexes(p1_move_idx, p2_move_idx),   # move indices
            rng._to_bits(),                                 # rng
        ])
        # gbattle_data.ad
        assert battle_data.length == (lib.PKMN_GEN1_BATTLE_SIZE * 8), (
            f"The battle data should be {lib.PKMN_GEN1_BATTLE_SIZE * 8} bits long, "
            f"but it's {battle_data.length} bits long."
        )
        # uintne == unsigned integer, native endian
        self._pkmn_battle = ffi.new("pkmn_gen1_battle*")
        self._pkmn_battle.bytes = battle_data.tobytes()
        self._bits = battle_data

    def update(self, p1_choice: Choice, p2_choice: Choice) -> Tuple[Result, List[int]]:
        """Update the battle with the given choice.

        Args:
            choice (Choice): The choice to make.

        Returns:
            Tuple[Result, List[int]]: The result of the choice,
            and the trace as a list of protocol bytes
        """
        # TODO: protocol parser?
        trace_buf = ffi.new("uint8_t[]", lib.PKMN_GEN1_LOG_SIZE)
        _pkmn_result = lib.pkmn_gen1_battle_update(
            self._pkmn_battle,          # pkmn_gen1_battle *battle
            p1_choice._pkmn_choice,     # pkmn_choice c1
            p2_choice._pkmn_choice,     # pkmn_choice c2
            trace_buf,                  # uint8_t *buf
            lib.PKMN_GEN1_LOG_SIZE,     # size_t len
        )

        result = Result(_pkmn_result)
        if result.is_error():
            # per pkmn.h:
            # This can only happen if libpkmn was built with trace logging enabled and the buffer
            # provided to the update function was not large  enough to hold all of the data
            # (which is only possible if the buffer being used was smaller than the
            # generation in question's MAX_LOGS bytes).
            raise Exception(
                "An error was thrown in libpkmn while updating the battle. " +
                "This should never happen; please file a bug report with PyKMN at " +
                "https://github.com/AnnikaCodes/PyKMN/issues/new"
            )
        return (result, trace_buf)

    def possible_choices(
        self,
        player: Player,
        previous_turn_result: Result,
    ) -> List[Choice]:
        """Get the possible choices for the given player.

        Args:
            player (Player): The player to get choices for.
            previous_turn_result (Result): The result of the previous turn
                (the first turn should be two PASS choices).

        Returns:
            List[Choice]: The possible choices.
        """
        raw_choices = ffi.new("pkmn_choice[]", lib.PKMN_OPTIONS_SIZE)
        requested_kind = previous_turn_result.p1_choice_type() if player == Player.P1 \
            else previous_turn_result.p2_choice_type()
        num_choices = lib.pkmn_gen1_battle_choices(
            self._pkmn_battle,      # pkmn_gen1_battle *battle
            player.value,           # pkmn_player player
            # TODO: is IntEnum more performant?
            requested_kind.value,   # pkmn_choice_kind request
            raw_choices,            # pkmn_choice out[]
            lib.PKMN_OPTIONS_SIZE,  # size_t len
        )

        if num_choices == 0:
            raise Softlock("Zero choices are available.")

        choices: List[Choice] = []
        for i in range(num_choices):
            choices.append(Choice(raw_choices[i]))
        return choices
