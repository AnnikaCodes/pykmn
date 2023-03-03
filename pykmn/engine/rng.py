"""Python wrappers for libpkmn's random number generation features."""
from _pkmn_engine_bindings import ffi, lib  # type: ignore # noqa: F401

class ShowdownRNG:
    """Wraps libpkmn's implementation of the random number generator used by Pokémon Showdown.

    This RNG is used by Showdown for all generations,
    but is most similar to the cartridge RNG in Generations V and VI.
    """
    def __init__(self, seed: int) -> None:
        """Create a new ShowdownRNG instance with the given seed.

        Args:
            seed (int): The seed for the RNG. Must be a 64-bit integer.
        """
        # pointer to a pkmn_psrng / PKMN_OPAQUE(PKMN_PSRNG_SIZE) / struct { uint8_t bytes[8]; }
        self._psrng = ffi.new("pkmn_psrng*")
        lib.pkmn_psrng_init(self._psrng, seed)

    def next(self) -> int:
        """Get the next number from the ShowdownRNG.

        Also advances the seed.

        Returns:
            int: The next number produced by the RNG.
        """
        return lib.pkmn_psrng_next(self._psrng)