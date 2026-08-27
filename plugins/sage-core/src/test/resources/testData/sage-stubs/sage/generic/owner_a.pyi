from sage.generic.curve import Curve
from sage.rings.integer import Integer

class OwnerA:
    def compute(self): ...
    def curve(self) -> Curve: ...
    def order(self) -> Integer: ...

class DerivedOwner(OwnerA):
    pass
