from sage.rings.ring import RingElement as RingElement
from sage.rings.integer import Integer as Integer

class Integer(RingElement):
    """An integer in Sage."""
    def nth_root(self, n: int, truncate: bool = False) -> Integer: ...
    @property
    def numerator(self) -> Integer: ...

@overload
def factor(n: Integer, proof: bool = True) -> list[tuple[Integer, Integer]]: ...
@overload
def factor(n: int, proof: bool = True) -> list[tuple[Integer, Integer]]: ...

pi: RealNumber
