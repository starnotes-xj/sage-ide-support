from sage.matrix.matrix import Matrix as Matrix, matrix as matrix
from sage.modules.vector import Vector as Vector, vector as vector
from sage.rings.polynomial.polynomial_ring import PolynomialRing as PolynomialRing
from sage.rings.finite_rings.finite_field_base import FiniteField as FiniteField, GF as GF
from sage.rings.integer import Integer as Integer
from sage.arith.misc import factor as factor
from sage.crypto.crypto import CryptoSystem as CryptoSystem, discrete_log as discrete_log

def dynamic_factory(value): ...
