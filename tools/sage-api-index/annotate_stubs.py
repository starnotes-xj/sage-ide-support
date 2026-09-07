#!/usr/bin/env python3
# Annotate curated Sage .pyi stubs with reliable return types.
#
# Two outputs share one curated knowledge table:
#   1) this script patches the generated .pyi stubs (what PyCharm actually
#      parses) for immediate IDE benefit;
#   2) the same contracts can be exported as source-annotation patches for
#      upstream sagemath/sage PRs.
#
# Four edit modes, all idempotent:
#   ADD     - inject a return annotation when the def has none.
#   REPLACE - retarget an existing annotation (factory returns are pointed
#             at the most capable real class instead of a thin base class,
#             e.g. matrix() -> matrix2.Matrix which owns solve_right/
#             determinant, instead of matrix0.Matrix which does not).
#   OVERLOAD - encode a documented input/output relationship as source-level
#             overloads so the general index/lowering pipeline can select an
#             exact return only when the call argument proves it.
#   INSERT  - stub-only forwarding declarations mirroring real dynamic
#             dispatch (used only when no better factory retarget exists).
from __future__ import annotations

import argparse
import ast
import io
import json
import re
import tokenize
from pathlib import Path

# Sage finite-field values are selected by the field implementation.  Keep
# the complete concrete implementation union when a point/pairing exposes a
# base-field element, rather than collapsing it to the public ``Element``
# base.  The union is shared by the finite-field curve/point contracts below.
FINITE_FIELD_ELEMENT_UNION = (
    "'sage.rings.finite_rings.integer_mod.IntegerMod_int | "
    "sage.rings.finite_rings.integer_mod.IntegerMod_int64 | "
    "sage.rings.finite_rings.integer_mod.IntegerMod_gmp | "
    "sage.rings.finite_rings.element_givaro.FiniteField_givaroElement | "
    "sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement | "
    "sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt'"
)
PRIME_FIELD_ELEMENT_UNION = (
    "'sage.rings.finite_rings.integer_mod.IntegerMod_int | "
    "sage.rings.finite_rings.integer_mod.IntegerMod_int64 | "
    "sage.rings.finite_rings.integer_mod.IntegerMod_gmp'"
)
INTEGER_MOD_ELEMENT_UNION = PRIME_FIELD_ELEMENT_UNION
POLYNOMIAL_MOD_P_ELEMENT_UNION = (
    "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint | "
    "sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p'"
)
FINITE_FIELD_POLYNOMIAL_ELEMENT_UNION = (
    "'sage.rings.polynomial.polynomial_zz_pex.Polynomial_ZZ_pEX | "
    "sage.rings.polynomial.polynomial_element_generic.Polynomial_generic_dense_field'"
)
POLYNOMIAL_POWER_UNION = "Self | 'sage.rings.fraction_field_element.FractionFieldElement'"
INTEGER_MATRIX_POWER_UNION = "Self | 'sage.matrix.matrix_rational_dense.Matrix_rational_dense'"
FINITE_FIELD_UNION = (
    "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn | "
    "sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro | "
    "sage.rings.finite_rings.finite_field_ntl_gf2e.FiniteField_ntl_gf2e | "
    "sage.rings.finite_rings.finite_field_pari_ffelt.FiniteField_pari_ffelt'"
)
FINITE_FIELD_MORPHISM_UNION = (
    "'sage.categories.morphism.IdentityMorphism | "
    "sage.rings.finite_rings.hom_finite_field.FiniteFieldHomomorphism_generic'"
)
MATROID_RETURN_UNION = (
    "'sage.matroids.circuit_closures_matroid.CircuitClosuresMatroid | "
    "sage.matroids.graphic_matroid.GraphicMatroid | "
    "sage.matroids.linear_matroid.BinaryMatroid | "
    "sage.matroids.linear_matroid.TernaryMatroid | "
    "sage.matroids.linear_matroid.QuaternaryMatroid | "
    "sage.matroids.linear_matroid.RegularMatroid'"
)
POLYHEDRON_RETURN_UNION = (
    "'sage.geometry.polyhedron.backend_ppl.Polyhedron_ZZ_ppl | "
    "sage.geometry.polyhedron.backend_ppl.Polyhedron_QQ_ppl | "
    "sage.geometry.polyhedron.backend_cdd.Polyhedron_QQ_cdd | "
    "sage.geometry.polyhedron.backend_cdd_rdf.Polyhedron_RDF_cdd | "
    "sage.geometry.polyhedron.backend_normaliz.Polyhedron_QQ_normaliz | "
    "sage.geometry.polyhedron.backend_normaliz.Polyhedron_ZZ_normaliz | "
    "sage.geometry.polyhedron.backend_polymake.Polyhedron_QQ_polymake | "
    "sage.geometry.polyhedron.backend_polymake.Polyhedron_ZZ_polymake | "
    "sage.geometry.polyhedron.backend_field.Polyhedron_field | "
    "sage.geometry.polyhedron.backend_number_field.Polyhedron_number_field'"
)
FINITE_POSET_RETURN_UNION = (
    "'sage.combinat.posets.posets.FinitePoset | "
    "sage.combinat.posets.lattices.FiniteLatticePoset'"
)
# Real-valued Sage APIs select their implementation from the requested
# precision/backend.  Keep the concrete numeric families (and the native
# Python float used by a few numerical wrappers) instead of collapsing the
# documented phrase ``a real number`` to an abstract ``Number`` base.
REAL_NUMBER_RETURN_UNION = (
    "'sage.rings.real_mpfr.RealNumber | "
    "sage.rings.real_double.RealDoubleElement | "
    "sage.rings.real_double_element_gsl.RealDoubleElement_gsl | "
    "sage.rings.real_arb.RealBall | "
    "sage.rings.real_mpfi.RealIntervalFieldElement | float'"
)
REAL_OR_INFINITY_RETURN_UNION = (
    "'sage.rings.real_mpfr.RealNumber | sage.rings.real_double.RealDoubleElement | "
    "sage.rings.real_double_element_gsl.RealDoubleElement_gsl | sage.rings.real_arb.RealBall | "
    "sage.rings.real_mpfi.RealIntervalFieldElement | sage.rings.infinity.PlusInfinity | float'"
)
INTEGER_RATIONAL_RETURN_UNION = "'sage.rings.integer.Integer | sage.rings.rational.Rational'"
# Cardinality/size metrics are not all represented by one Python/Sage scalar
# in Sage: finite objects normally return ``Integer`` while infinite parents
# return ``PlusInfinity``.  Keep the union explicit instead of collapsing to
# the abstract ``Element``/``Number`` bases.  ``int`` is included for
# combinatorial implementations which return a native Python count.
CARDINALITY_RETURN_UNION = (
    "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity'"
)
ORDER_RETURN_UNION = (
    "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity | None'"
)
# Matrix2 exposes several base-ring-valued helpers without making the matrix
# parent a generic class.  Preserve the concrete scalar implementations that
# Sage 10.9 uses for the common CTF rings instead of falling back to UNKNOWN;
# specialised matrix subclasses below still narrow these unions further.
MATRIX_SCALAR_UNION = (
    "'sage.rings.integer.Integer | sage.rings.rational.Rational | "
    "sage.rings.real_mpfr.RealNumber | sage.rings.real_double.RealDoubleElement | "
    "sage.rings.complex_mpfr.ComplexNumber | sage.rings.complex_double.ComplexDoubleElement | "
    "sage.rings.finite_rings.integer_mod.IntegerMod_int | "
    "sage.rings.finite_rings.integer_mod.IntegerMod_int64 | "
    "sage.rings.finite_rings.integer_mod.IntegerMod_gmp | "
    "sage.rings.finite_rings.element_givaro.FiniteField_givaroElement | "
    "sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement | "
    "sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt | "
    "sage.symbolic.expression.Expression'"
)
# Functional wrappers intentionally expose a small, concrete scalar union for
# symbolic summation/product.  The wrappers simplify constant expressions to
# Sage integers/rationals, numeric inputs to the real-double implementation,
# and symbolic/complex inputs to symbolic expressions; do not collapse this to
# the public ``Element``/``Number`` bases.
FUNCTIONAL_SYMBOLIC_RESULT_UNION = (
    "'sage.rings.integer.Integer | sage.rings.rational.Rational | "
    "sage.rings.real_mpfr.RealNumber | "
    "sage.rings.real_double_element_gsl.RealDoubleElement_gsl | "
    "sage.rings.complex_mpfr.ComplexNumber | "
    "sage.rings.complex_double.ComplexDoubleElement | "
    "sage.symbolic.expression.Expression | sage.rings.infinity.PlusInfinity'"
)
MATRIX_POLYNOMIAL_UNION = (
    "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint | "
    "sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint | "
    "sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint | "
    "sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p | "
    "sage.rings.polynomial.polynomial_zz_pex.Polynomial_ZZ_pEX | "
    "sage.rings.polynomial.polynomial_element_generic.Polynomial_generic_dense_field'"
)
# Poset/combinatorics polynomial methods may use the default ``ZZ`` FLINT
# implementation or a caller-supplied Sage base ring.  Keep the concrete
# univariate implementations explicit; do not expose ``Polynomial``'s public
# protocol base as the inferred result.
POLYNOMIAL_RETURN_UNION = (
    "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint | "
    "sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint | "
    "sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint | "
    "sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p | "
    "sage.rings.polynomial.polynomial_zz_pex.Polynomial_ZZ_pEX | "
    "sage.rings.polynomial.polynomial_element_generic.Polynomial_generic_dense_field'"
)
# Vector-valued Sage APIs select a concrete free-module element backend from
# the parent ring/storage requested by the caller.  Keep the concrete element
# families explicit for documented ``a vector``/``codeword`` results instead
# of exposing the public ``Vector``/``FreeModuleElement`` protocol base.
VECTOR_ELEMENT_UNION = (
    "'sage.modules.free_module_element.FreeModuleElement_generic_dense | "
    "sage.modules.free_module_element.FreeModuleElement_generic_sparse | "
    "sage.modules.vector_integer_dense.Vector_integer_dense | "
    "sage.modules.vector_rational_dense.Vector_rational_dense | "
    "sage.modules.vector_mod2_dense.Vector_mod2_dense | "
    "sage.modules.vector_modn_dense.Vector_modn_dense | "
    "sage.modules.vector_numpy_dense.Vector_numpy_dense | "
    "sage.modules.vector_numpy_integer_dense.Vector_numpy_integer_dense | "
    "sage.modules.vector_double_dense.Vector_double_dense | "
    "sage.modules.vector_complex_double_dense.Vector_complex_double_dense | "
    "sage.modules.vector_real_double_dense.Vector_real_double_dense | "
    "sage.modules.vector_symbolic_dense.Vector_symbolic_dense | "
    "sage.modules.vector_symbolic_sparse.Vector_symbolic_sparse | "
    "sage.modules.vector_callable_symbolic_dense.Vector_callable_symbolic_dense'"
)
# Elliptic-curve factories and morphisms preserve the curve/point family
# chosen by the base field.  The public ``EllipticCurve_generic`` and
# ``EllipticCurvePoint`` protocol bases are intentionally excluded: these
# concrete implementations are the ones Sage 10.9 constructs for the CTF
# finite/rational/number/p-adic field paths.
ELLIPTIC_CURVE_RETURN_UNION = (
    "'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field | "
    "sage.schemes.elliptic_curves.ell_number_field.EllipticCurve_number_field | "
    "sage.schemes.elliptic_curves.ell_rational_field.EllipticCurve_rational_field | "
    "sage.schemes.elliptic_curves.ell_padic_field.EllipticCurve_padic_field'"
)
ELLIPTIC_POINT_RETURN_UNION = (
    "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field | "
    "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field'"
)
KODAIRA_SYMBOL_RETURN = (
    "'sage.schemes.elliptic_curves.kodaira_symbol.KodairaSymbol_class'"
)
# Power-series conversions expose concrete polynomial implementations selected
# by the univariate/multivariate parent.  Keep the implementation families
# explicit instead of returning the public ``Polynomial`` protocol base.
MULTIVARIATE_POLYNOMIAL_RETURN_UNION = (
    "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular | "
    "sage.rings.polynomial.multi_polynomial_element.MPolynomial_polydict'"
)
MULTIVARIATE_POLYNOMIAL_RING_RETURN_UNION = (
    "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomialRing_libsingular | "
    "sage.rings.polynomial.multi_polynomial_ring.MPolynomialRing_polydict | "
    "sage.rings.polynomial.multi_polynomial_ring.MPolynomialRing_polydict_domain'"
)
LAURENT_POLYNOMIAL_RETURN_UNION = (
    "'sage.rings.polynomial.laurent_polynomial.LaurentPolynomial_univariate | "
    "sage.rings.polynomial.laurent_polynomial_mpair.LaurentPolynomial_mpair'"
)
POWER_SERIES_RETURN_UNION = (
    "'sage.rings.power_series_poly.PowerSeries_poly | "
    "sage.rings.power_series_pari.PowerSeries_pari'"
)
LINK_POLYNOMIAL_RETURN_UNION = (
    "'sage.rings.polynomial.laurent_polynomial.LaurentPolynomial_univariate | "
    "sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint | "
    "sage.rings.integer.Integer'"
)
JONES_POLYNOMIAL_RETURN_UNION = (
    "'sage.rings.polynomial.laurent_polynomial.LaurentPolynomial_univariate | "
    "sage.symbolic.expression.Expression | sage.rings.integer.Integer'"
)
# ``MatrixSpace`` constructs an element using the base ring's selected
# implementation.  The parent class cannot express that dispatch, so keep
# the concrete implementation family explicit for methods such as
# ``identity_matrix``/``random_element``/``from_vector``.  Every member here
# is an actual Sage matrix implementation (the public ``matrix0.Matrix``
# protocol bases are intentionally excluded).
MATRIX_ELEMENT_UNION = (
    "'sage.matrix.matrix_complex_ball_dense.Matrix_complex_ball_dense | "
    "sage.matrix.matrix_complex_double_dense.Matrix_complex_double_dense | "
    "sage.matrix.matrix_cyclo_dense.Matrix_cyclo_dense | "
    "sage.matrix.matrix_double_dense.Matrix_double_dense | "
    "sage.matrix.matrix_double_sparse.Matrix_double_sparse | "
    "sage.matrix.matrix_gap.Matrix_gap | "
    "sage.matrix.matrix_generic_dense.Matrix_generic_dense | "
    "sage.matrix.matrix_generic_sparse.Matrix_generic_sparse | "
    "sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense | "
    "sage.matrix.matrix_gfpn_dense.Matrix_gfpn_dense | "
    "sage.matrix.matrix_integer_dense.Matrix_integer_dense | "
    "sage.matrix.matrix_integer_sparse.Matrix_integer_sparse | "
    "sage.matrix.matrix_laurent_mpolynomial_dense.Matrix_laurent_mpolynomial_dense | "
    "sage.matrix.matrix_mod2_dense.Matrix_mod2_dense | "
    "sage.matrix.matrix_modn_dense_double.Matrix_modn_dense_double | "
    "sage.matrix.matrix_modn_dense_float.Matrix_modn_dense_float | "
    "sage.matrix.matrix_modn_sparse.Matrix_modn_sparse | "
    "sage.matrix.matrix_mpolynomial_dense.Matrix_mpolynomial_dense | "
    "sage.matrix.matrix_numpy_dense.Matrix_numpy_dense | "
    "sage.matrix.matrix_numpy_integer_dense.Matrix_numpy_integer_dense | "
    "sage.matrix.matrix_polynomial_dense.Matrix_polynomial_dense | "
    "sage.matrix.matrix_rational_dense.Matrix_rational_dense | "
    "sage.matrix.matrix_rational_sparse.Matrix_rational_sparse | "
    "sage.matrix.matrix_real_double_dense.Matrix_real_double_dense | "
    "sage.matrix.matrix_symbolic_dense.Matrix_symbolic_dense | "
    "sage.matrix.matrix_symbolic_sparse.Matrix_symbolic_sparse'"
)
MATRIX_SPACE_MODULE_UNION = (
    "'sage.modules.free_module.FreeModule_ambient | "
    "sage.modules.free_module.FreeModule_ambient_domain | "
    "sage.modules.free_module.FreeModule_ambient_pid | "
    "sage.modules.free_module.FreeModule_ambient_field'"
)
MATRIX_SPACE_SUBMODULE_UNION = (
    "'sage.modules.free_module.FreeModule_submodule_pid | "
    "sage.modules.free_module.FreeModule_submodule_field | "
    "sage.modules.with_basis.subquotient.SubmoduleWithBasis'"
)

# Parent/element dispatch is a real Sage contract: a parent creates elements
# through its ``element_class`` and the concrete class is selected at runtime
# from the parent instance.  A public ``Element`` base would hide the concrete
# implementation (and is therefore forbidden as a final return type).  Keep a
# symbolic contract instead; the IDE lowering layer resolves it against the
# concrete receiver when a child contract is available, and remains
# fail-closed when the parent is genuinely dynamic.
PARENT_ELEMENT_CONTRACT = "'sage.type_contracts.ParentElement[Self]'"
PARENT_ELEMENT_TUPLE_CONTRACT = "tuple['sage.type_contracts.ParentElement[Self]', ...]"
# Relation-aware parent contracts keep dynamic Sage parents concrete at the
# call site.  The lowering layer resolves the referenced parent (codomain,
# domain, base ring, or ambient object) and then follows its element factory;
# no public ``Element`` base is exposed as the final type.
RELATED_ELEMENT_CONTRACTS = {
    "codomain": "'sage.type_contracts.CodomainElement[Self]'",
    "domain": "'sage.type_contracts.DomainElement[Self]'",
    "base ring": "'sage.type_contracts.BaseRingElement[Self]'",
    "base field": "'sage.type_contracts.BaseFieldElement[Self]'",
    "ambient": "'sage.type_contracts.AmbientElement[Self]'",
}

# ADD: member name -> annotation expression for unannotated defs.
CURATED_ANNOTATIONS: dict[str, dict[str, dict[str, str]]] = {
    # A few module-level functional wrappers have stable outer results even
    # though most wrappers delegate to a receiver-dependent method.  Keep only
    # contracts proved by the documented Sage implementation.
    "sage/misc/functional.pyi": {
        None: {
            "additive_order": "'sage.rings.integer.Integer | sage.rings.infinity.PlusInfinity'",
            "basis": "list | 'sage.structure.sequence.Sequence_generic'",
            "characteristic_polynomial": POLYNOMIAL_RETURN_UNION,
            "decomposition": "list | 'sage.structure.sequence.Sequence_generic'",
            "det": MATRIX_SCALAR_UNION,
            "eta": FUNCTIONAL_SYMBOLIC_RESULT_UNION,
            "log": FUNCTIONAL_SYMBOLIC_RESULT_UNION,
            "minimal_polynomial": POLYNOMIAL_RETURN_UNION,
            "numerical_approx": FUNCTIONAL_SYMBOLIC_RESULT_UNION,
        },
    },
    "sage/misc/lazy_import.pyi": {
        "LazyImport": {
            "_instancedoc_": "str | None",
            "_sage_src_": "str",
            "_sage_argspec_": "'inspect.FullArgSpec'",
            "__oct__": "str",
            "__hex__": "str",
        },
    },
    "sage/matrix/benchmark.pyi": {
        None: {
            # Benchmark entry points return the measured ``cputime`` as a
            # native float.  The report wrappers only print tables, while the
            # Hilbert helper is the one constructor returning a matrix.
            "MatrixVector_QQ": "float",
            "charpoly_GF": "float",
            "charpoly_ZZ": "float",
            "det_GF": "float",
            "det_QQ": "float",
            "det_ZZ": "float",
            "det_hilbert_QQ": "float",
            "echelon_QQ": "float",
            "hilbert_matrix": "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'",
            "inverse_QQ": "float",
            "invert_hilbert_QQ": "float",
            "matrix_add_GF": "float",
            "matrix_add_ZZ": "float",
            "matrix_add_ZZ_2": "float",
            "matrix_multiply_GF": "float",
            "matrix_multiply_QQ": "float",
            "matrix_multiply_ZZ": "float",
            "nullspace_GF": "float",
            "nullspace_RDF": "float",
            "nullspace_RR": "float",
            "nullspace_ZZ": "float",
            "rank2_GF": "float",
            "rank2_ZZ": "float",
            "rank_GF": "float",
            "rank_ZZ": "float",
            "report": "None",
            "report_GF": "None",
            "report_ZZ": "None",
            "smithform_ZZ": "float",
            "vecmat_ZZ": "float",
        },
    },
    "sage/combinat/matrices/latin.pyi": {
        "LatinSquare": {
            "apply_isotopism": "Self",
            "__getitem__": "'sage.rings.integer.Integer'",
            "column": "'sage.modules.vector_integer_dense.Vector_integer_dense'",
            "row": "'sage.modules.vector_integer_dense.Vector_integer_dense'",
            "dumps": "bytes",
            "permissable_values": "list",
            "random_empty_cell": "list[int] | None",
            "top_left_empty_cell": "list[int] | None",
            "column_containing_sym": "int",
            "row_containing_sym": "int",
            "gcs": "Self",
        },
        None: {
            "isotopism": "'sage.combinat.permutation.Permutation'",
            "cells_map_as_square": "'sage.combinat.matrices.latin.LatinSquare'",
            "back_circulant": "'sage.combinat.matrices.latin.LatinSquare'",
            "forward_circulant": "'sage.combinat.matrices.latin.LatinSquare'",
            "direct_product": "'sage.combinat.matrices.latin.LatinSquare'",
            "elementary_abelian_2group": "'sage.combinat.matrices.latin.LatinSquare'",
            "group_to_LatinSquare": "'sage.matrix.matrix_integer_dense.Matrix_integer_dense'",
            "bitrade": "tuple",
            "bitrade_from_group": "tuple",
            "LatinSquare_generator": "Iterator['sage.combinat.matrices.latin.LatinSquare']",
            "alternating_group_bitrade_generators": "tuple",
            "beta1": "tuple",
            "beta2": "tuple",
            "beta3": "tuple",
            "genus": "int",
            "next_conjugate": "'sage.combinat.matrices.latin.LatinSquare'",
            "p3_group_bitrade_generators": "tuple",
            "pq_group_bitrade_generators": "tuple",
            "tau1": "'sage.combinat.permutation.Permutation'",
            "tau2": "'sage.combinat.permutation.Permutation'",
            "tau3": "'sage.combinat.permutation.Permutation'",
            "tau123": "tuple",
            "tau_to_bitrade": "tuple",
        },
    },
    "sage/topology/simplicial_complex_examples.pyi": {
        None: {
            # The catalogue functions explicitly construct one of these two
            # concrete implementations in Sage 10.9; the two non-unique
            # constructors are kept separate instead of widening to a base.
            "BarnetteSphere": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "BrucknerGrunbaumSphere": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "ChessboardComplex": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "ComplexProjectivePlane": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "DunceHat": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "FareyMap": "'sage.topology.simplicial_complex.SimplicialComplex'",
            "GenusSix": "'sage.topology.simplicial_complex.SimplicialComplex'",
            "K3Surface": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "KleinBottle": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "MatchingComplex": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "MooreSpace": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "NotIConnectedGraphs": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "PoincareHomologyThreeSphere": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "QuaternionicProjectivePlane": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "RandomComplex": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "RandomTwoSphere": "'sage.topology.simplicial_complex.SimplicialComplex'",
            "RealProjectivePlane": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "RealProjectiveSpace": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "RudinBall": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "ShiftedComplex": "'sage.topology.simplicial_complex.SimplicialComplex'",
            "Simplex": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "Sphere": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "SumComplex": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "SurfaceOfGenus": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "Torus": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "ZieglerBall": "'sage.topology.simplicial_complex_examples.UniqueSimplicialComplex'",
            "facets_for_K3": "list",
            "matching": "list",
        },
    },
    "sage/groups/braid.pyi": {
        "Braid": {
            # These braid operations have stable outer implementations in
            # Sage 10.9.  Matrix representations vary by coefficient ring,
            # so they use the concrete matrix-family union; knot-polynomial
            # helpers retain their documented Laurent/symbolic families.
            "LKB_matrix": MATRIX_ELEMENT_UNION,
            "TL_matrix": MATRIX_ELEMENT_UNION,
            "annular_khovanov_complex": "dict",
            "annular_khovanov_homology": "dict",
            "_annular_khovanov_complex_cached": "'sage.homology.chain_complex.ChainComplex_class'",
            "_enhanced_states": "dict",
            "_colored_jones_sum": JONES_POLYNOMIAL_RETURN_UNION,
            "_jones_polynomial": JONES_POLYNOMIAL_RETURN_UNION,
            "alexander_polynomial": "'sage.rings.polynomial.laurent_polynomial.LaurentPolynomial_univariate'",
            "burau_matrix": MATRIX_ELEMENT_UNION,
            "colored_jones_polynomial": JONES_POLYNOMIAL_RETURN_UNION,
            "conjugating_braid": "Self | None",
            "deformed_burau_matrix": MATRIX_ELEMENT_UNION,
            "gcd": "Self",
            "jones_polynomial": JONES_POLYNOMIAL_RETURN_UNION,
            "lcm": "Self",
            "links_gould_matrix": MATRIX_ELEMENT_UNION,
            "markov_trace": "'sage.rings.fraction_field_element.FractionFieldElement'",
            "mirror_image": "Self",
            "permutation": "'sage.combinat.permutation.Permutation'",
            "plot": "'sage.plot.graphics.Graphics'",
            "plot3d": "'sage.plot.plot3d.base.Graphics3dGroup'",
            "pure_conjugating_braid": "Self",
            "reverse": "Self",
            "right_normal_form": "tuple",
            "rigidity": "int",
            "strands": "int",
            "super_summit_set_element": "tuple",
            "ultra_summit_set_element": "tuple",
        },
    },
    "sage/features/all.pyi": {
        None: {
            # The package-level enumerator is a generator; individual
            # feature modules use a materialized list and are handled by the
            # generic ``all_features`` contract below.
            "all_features": "Iterator",
        },
    },
    "sage/arith/misc.pyi": {
        # These helpers have a stable Python outer result independent of the
        # complex-number implementation they sort.  The element types vary,
        # but the public functions always return the documented tuple/list
        # containers, so a broad container is safer than UNKNOWN here.
        None: {
            "_key_complex_for_display": "tuple",
            "sort_complex_numbers_for_display": "list",
            "__GCD_sequence": "GcdT",
            "get_gcd": "Callable[..., 'sage.rings.integer.Integer']",
            "get_inverse_mod": "Callable[..., 'sage.rings.integer.Integer']",
            "primes": "Iterator['sage.rings.integer.Integer']",
            "smooth_part": "'sage.structure.factorization.Factorization'",
            "valuation": "'sage.rings.integer.Integer'",
        },
        "Euler_Phi": {
            "__call__": "'sage.rings.integer.Integer'",
            "plot": "'sage.plot.graphics.Graphics'",
        },
        "Moebius": {
            "__call__": "'sage.rings.integer.Integer'",
            "plot": "'sage.plot.graphics.Graphics'",
            "range": "list",
        },
        "Sigma": {
            "__call__": "'sage.rings.integer.Integer'",
            "plot": "'sage.plot.graphics.Graphics'",
        },
    },
    "sage/crypto/boolean_function.pyi": {
        None: {
            "random_boolean_function": "'sage.crypto.boolean_function.BooleanFunction'",
            "unpickle_BooleanFunction": "'sage.crypto.boolean_function.BooleanFunction'",
        },
        "BooleanFunction": {
            # Boolean-function algebra stays in the concrete BooleanFunction
            # implementation; these operations do not widen to a generic
            # Sage element.
            "__invert__": "Self",
            "__add__": "Self",
            "__mul__": "Self",
            "__or__": "Self",
            "derivative": "Self",
            "__call__": "bool",
            "__getitem__": "bool",
            "__iter__": "'sage.crypto.boolean_function.BooleanFunctionIterator'",
            "absolute_walsh_spectrum": "dict",
            "autocorrelation": "tuple",
            "absolute_autocorrelation": "dict",
            "nonlinearity": "int",
            "absolute_indicator": "int",
            "sum_of_square_indicator": "int",
            "algebraic_immunity": "int",
            "algebraic_degree": "int",
            "correlation_immunity": "'sage.rings.integer.Integer'",
            "resiliency_order": "'sage.rings.integer.Integer'",
            "annihilator": "'sage.rings.polynomial.pbori.pbori.BooleanPolynomial'",
            "algebraic_normal_form": "'sage.rings.polynomial.pbori.pbori.BooleanPolynomial'",
            "linear_structures": "'sage.modules.free_module.FreeModule_submodule_field_with_category'",
            "__setitem__": "None",
        },
        "BooleanFunctionIterator": {
            "__iter__": "Self",
            "__next__": "bool",
        },
    },
    "sage/crypto/sbox.pyi": {
        None: {
            "feistel_construction": "'sage.crypto.sbox.SBox'",
            "misty_construction": "'sage.crypto.sbox.SBox'",
        },
        "SBox": {
            # Sage's S-box analysis API has stable concrete result families:
            # table constructors use their documented integer/rational matrix
            # implementation, algebraic transforms preserve SBox, and the
            # scalar metrics use the runtime-proven Python/Sage scalar type.
            "derivative": "Self",
            "difference_distribution_table": "'sage.matrix.matrix_integer_dense.Matrix_integer_dense'",
            "maximal_difference_probability_absolute": "'sage.rings.integer.Integer'",
            "maximal_difference_probability": "float",
            "linear_approximation_table": "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'",
            "maximal_linear_bias_absolute": "'sage.rings.rational.Rational'",
            "maximal_linear_bias_relative": "float",
            "boomerang_connectivity_table": "'sage.matrix.matrix_integer_dense.Matrix_integer_dense'",
            "boomerang_uniformity": "'sage.rings.integer.Integer'",
            "cnf": "list",
            "differential_branch_number": "int",
            "interpolation_polynomial": "'sage.rings.polynomial.polynomial_zz_pex.Polynomial_ZZ_pEX'",
            "inverse": "Self",
            "linear_branch_number": "int",
            "linearity": "'sage.rings.rational.Rational'",
            "min_degree": "int",
            "max_degree": "int",
            "nonlinearity": "'sage.rings.rational.Rational'",
            "ring": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomialRing_libsingular'",
            "autocorrelation_table": "'sage.matrix.matrix_integer_dense.Matrix_integer_dense'",
            "__iter__": "Iterator['sage.rings.integer.Integer']",
            "__eq__": "bool",
            "__ne__": "bool",
        },
    },
    "sage/crypto/sboxes.pyi": {
        None: {
            # Every named constructor in this module returns the concrete SBox
            # table described by its cryptographic construction.
            "bracken_leander": "'sage.crypto.sbox.SBox'",
            "carlet_tang_tang_liao": "'sage.crypto.sbox.SBox'",
            "gold": "'sage.crypto.sbox.SBox'",
            "kasami": "'sage.crypto.sbox.SBox'",
            "niho": "'sage.crypto.sbox.SBox'",
            "welch": "'sage.crypto.sbox.SBox'",
            "monomial_function": "'sage.crypto.sbox.SBox'",
            "inversion": "'sage.crypto.sbox.SBox'",
            "chi": "'sage.crypto.sbox.SBox'",
        },
    },
    "sage/crypto/mq/rijndael_gf.pyi": {
        "RijndaelGF": {
            # Rijndael-GF's algebraic helpers use fixed GF(2^8) matrices and
            # multivariate FLINT/libSingular objects in Sage 10.9.  State
            # transforms are kept as TypeVar overloads below so a polynomial
            # matrix is not collapsed to the finite-field matrix class.
            "__call__": "str",
            "number_rounds": "'sage.rings.integer.Integer'",
            "_GF_to_hex": "str",
            "_GF_to_bin": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "decrypt": "str",
            "_check_valid_PRmatrix": "None",
            "expand_key": "list['sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense']",
            "expand_key_poly": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'",
            "_add_round_key_pc": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'",
            "_sub_bytes_pc": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'",
            "_srd": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "_mix_columns_pc": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'",
            "_shift_rows_pc": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'",
            "add_round_key_poly_constr": "'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr'",
            "sub_bytes_poly_constr": "'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr'",
            "mix_columns_poly_constr": "'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr'",
            "shift_rows_poly_constr": "'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr'",
        },
        "Round_Component_Poly_Constr": {
            "__call__": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'",
        },
    },
    "sage/crypto/block_cipher/des.pyi": {
        "DES": {
            # DES permutation helpers always construct dense GF(2) bit
            # vectors, independent of the cipher instance's key schedule.
            "_ip": "'sage.modules.vector_mod2_dense.Vector_mod2_dense'",
            "__eq__": "bool",
        },
        "DES_KS": {
            # The key-schedule half-register is a GF(2) bit vector and the
            # documented left rotation preserves that concrete implementation.
            "_left_shift": "'sage.modules.vector_mod2_dense.Vector_mod2_dense'",
            "__eq__": "bool",
            "__iter__": "Iterator['sage.rings.integer.Integer']",
        },
    },
    "sage/crypto/block_cipher/miniaes.pyi": {
        "MiniAES": {
            # These helpers construct fixed Mini-AES objects rather than a
            # public matrix base: random_key uses the GF(2^4) dense matrix
            # implementation and sbox returns Sage's concrete SBox table.
            "random_key": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "sbox": "'sage.crypto.sbox.SBox'",
            "__eq__": "bool",
        },
    },
    "sage/crypto/block_cipher/present.pyi": {
        None: {
            # The small PRESENT linear layer is the dense GF(2) permutation
            # matrix shown by its doctest, not a generic Matrix base.
            "_smallscale_present_linearlayer": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
        },
        "PRESENT": {"__eq__": "bool"},
        "PRESENT_KS": {
            "__eq__": "bool",
            "__iter__": "Iterator['sage.rings.integer.Integer']",
        },
    },
    "sage/crypto/block_cipher/sdes.pyi": {
        "SimplifiedDES": {"__eq__": "bool"},
    },
    "sage/crypto/cipher.pyi": {
        "Cipher": {"__eq__": "bool"},
    },
    "sage/crypto/mq/sr.pyi": {
        "SR_generic": {
            # SR's state representation and AES transforms are concrete
            # GF(2^e) dense matrices for both SR_gf2n and SR_gf2 variants.
            "new_generator": "Self",
            "sbox": "'sage.crypto.sbox.SBox'",
            "sub_bytes": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "shift_rows": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "mix_columns": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "add_round_key": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "key_schedule": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "__call__": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "hex_str": "str",
            "hex_str_matrix": "str",
            "hex_str_vector": "str",
            "varformatstr": "str",
            "block_order": "'sage.rings.polynomial.term_order.TermOrder'",
            "state_array": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "random_state_array": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "round_polynomials": "tuple",
            "key_schedule_polynomials": "tuple",
            "polynomial_system": "tuple",
            "_insert_matrix_into_matrix": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "__eq__": "bool",
            "__ne__": "bool",
            "base_ring": "'sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro'",
            "ring": "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomialRing_libsingular'",
            "sbox_constant": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "sub_byte": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "random_vector": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "random_element": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
        },
        "SR_gf2n": {
            "vector": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "shift_rows_matrix": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "lin_matrix": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "mix_columns_matrix": "'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense'",
            "inversion_polynomials": "list",
        },
        "SR_gf2": {
            "vector": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
            "shift_rows_matrix": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
            "lin_matrix": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
            "mix_columns_matrix": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
            "_mul_matrix": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
            "_square_matrix": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
            "inversion_polynomials": "list",
            "inversion_polynomials_single_sbox": "list",
            "_inversion_polynomials_single_sbox": "list",
            "ring": "'sage.rings.polynomial.pbori.pbori.BooleanPolynomialRing'",
            "random_vector": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
            "random_element": "'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense'",
        },
        "SR_gf2_2": {
            "inversion_polynomials_single_sbox": "list",
        },
        "AllowZeroInversionsContext": {
            "__enter__": "None",
            "__exit__": "None",
        },
        None: {
            "check_consistency": "bool",
        },
    },
    "sage/crypto/classical.pyi": {
        "AffineCryptosystem": {
            "brute_force": "dict",
            "deciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "enciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse_key": "tuple",
            "random_key": "tuple",
        },
        "HillCryptosystem": {
            # Constructing a cipher from a valid Hill key is a stable factory
            # contract; keep the concrete cipher class visible to completion.
            "__call__": "'sage.crypto.classical_cipher.HillCipher'",
            "deciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "enciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
        },
        "ShiftCryptosystem": {
            "brute_force": "dict",
            "deciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "enciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse_key": "'sage.rings.integer.Integer'",
            "random_key": "'sage.rings.integer.Integer'",
        },
        "SubstitutionCryptosystem": {
            "__call__": "'sage.crypto.classical_cipher.SubstitutionCipher'",
            "random_key": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse_key": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "deciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "enciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
        },
        "TranspositionCryptosystem": {
            "__call__": "'sage.crypto.classical_cipher.TranspositionCipher'",
            "random_key": "'sage.groups.perm_gps.permgroup_element.SymmetricGroupElement'",
            "inverse_key": "'sage.groups.perm_gps.permgroup_element.SymmetricGroupElement'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "deciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "enciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
        },
        "VigenereCryptosystem": {
            "__call__": "'sage.crypto.classical_cipher.VigenereCipher'",
            "random_key": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse_key": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "deciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "enciphering": "'sage.monoids.string_monoid_element.StringMonoidElement'",
        },
    },
    "sage/crypto/classical_cipher.pyi": {
        "AffineCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "__eq__": "bool",
        },
        "HillCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse": "'sage.crypto.classical_cipher.HillCipher'",
            "__eq__": "bool",
        },
        "ShiftCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "__eq__": "bool",
        },
        "SubstitutionCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse": "'sage.crypto.classical_cipher.SubstitutionCipher'",
            "__eq__": "bool",
        },
        "TranspositionCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse": "'sage.crypto.classical_cipher.TranspositionCipher'",
            "__eq__": "bool",
        },
        "VigenereCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "inverse": "'sage.crypto.classical_cipher.VigenereCipher'",
            "__eq__": "bool",
        },
    },
    "sage/crypto/cryptosystem.pyi": {
        "Cryptosystem": {
            "__eq__": "bool",
            # A configured periodic cryptosystem exposes a Sage Integer;
            # non-periodic variants raise rather than returning another type.
            "period": "'sage.rings.integer.Integer'",
        },
        "SymmetricKeyCryptosystem": {
            "alphabet_size": "int",
        },
    },
    "sage/crypto/lfsr.pyi": {
        None: {
            "lfsr_sequence": "list",
            "lfsr_autocorrelation": "'sage.rings.rational.Rational'",
            # The implementation chooses the polynomial ring from the finite
            # field carried by the sequence.  These are the concrete Sage
            # polynomial implementations exercised by Sage 10.9 (GF(2),
            # prime fields, and extension fields); no abstract Polynomial
            # base is used as the final result.
            "lfsr_connection_polynomial": (
                "'sage.rings.polynomial.polynomial_gf2x.Polynomial_GF2X | "
                "sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint | "
                "sage.rings.polynomial.polynomial_zz_pex.Polynomial_ZZ_pEX'"
            ),
        },
    },
    "sage/crypto/stream.pyi": {
        "LFSRCryptosystem": {
            "__call__": "'sage.crypto.stream_cipher.LFSRCipher'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "__eq__": "bool",
        },
        "ShrinkingGeneratorCryptosystem": {
            "__call__": "'sage.crypto.stream_cipher.ShrinkingGeneratorCipher'",
            "encoding": "'sage.monoids.string_monoid_element.StringMonoidElement'",
        },
        None: {
            # BBS exposes its generated bits through Sage's binary string
            # monoid, not a plain Python list or string.
            "blum_blum_shub": "'sage.monoids.string_monoid_element.StringMonoidElement'",
        },
    },
    "sage/crypto/stream_cipher.pyi": {
        "LFSRCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "initial_state": "list",
            # LFSRCryptosystem is implemented over GF(2); its connection
            # polynomial is therefore the concrete GF(2) polynomial class.
            "connection_polynomial": "'sage.rings.polynomial.polynomial_gf2x.Polynomial_GF2X'",
        },
        "ShrinkingGeneratorCipher": {
            "__call__": "'sage.monoids.string_monoid_element.StringMonoidElement'",
            "keystream_cipher": "'sage.crypto.stream_cipher.LFSRCipher'",
            "decimating_cipher": "'sage.crypto.stream_cipher.LFSRCipher'",
        },
    },
    "sage/crypto/public_key/blum_goldwasser.pyi": {
        "BlumGoldwasser": {
            # The public-key helpers expose concrete Sage integers and fixed
            # tuple/list shapes documented by the implementation.  The
            # ciphertext's final seed is a Sage Integer while its bit blocks
            # are ordinary Python lists; decryption returns the corresponding
            # nested bit-list structure.
            "decrypt": "list[list[int]]",
            "encrypt": "tuple[list[list[int]], 'sage.rings.integer.Integer']",
            "private_key": (
                "tuple['sage.rings.integer.Integer', 'sage.rings.integer.Integer', "
                "'sage.rings.integer.Integer', 'sage.rings.integer.Integer']"
            ),
            "public_key": "'sage.rings.integer.Integer'",
            "random_key": (
                "tuple['sage.rings.integer.Integer', tuple['sage.rings.integer.Integer', "
                "'sage.rings.integer.Integer', 'sage.rings.integer.Integer', "
                "'sage.rings.integer.Integer']]"
            ),
            "__eq__": "bool",
        },
    },
    "sage/crypto/lwe.pyi": {
        "UniformSampler": {
            # ``randint`` is intentionally a Python int in Sage's sampler.
            "__call__": "int",
        },
        None: {
            # These cryptographic helpers have stable outer containers even
            # though their vector/finite-field element parents depend on q.
            "samples": "list[tuple]",
            "balance_sample": "tuple",
        },
        "LWE": {"__call__": "tuple"},
        "RingLWE": {"__call__": "tuple"},
        "RingLWEConverter": {"__call__": "tuple"},
    },
    "sage/groups/generic.pyi": {
        None: {
            # Generic group helpers have stable scalar/tuple contracts in the
            # source documentation.  Their group *element* result remains
            # argument-dependent and is intentionally handled separately.
            "_parse_group_def": "tuple",
            "_ord_from_op": "'sage.rings.integer.Integer'",
            "discrete_log_generic": "'sage.rings.integer.Integer'",
            "linear_relation": "tuple['sage.rings.integer.Integer', 'sage.rings.integer.Integer']",
            "order_from_multiple": "'sage.rings.integer.Integer'",
            "order_from_bounds": "'sage.rings.integer.Integer'",
        },
        "multiples": {
            # The iterator object itself is the only protocol result that is
            # independent of the dynamic group element yielded by __next__.
            "__iter__": "Self",
        },
    },
    "sage/schemes/elliptic_curves/ell_finite_field.pyi": {
        None: {
            "curves_with_j_0": "list['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']",
            "curves_with_j_1728": "list['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']",
            "curves_with_j_0_char2": "list['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']",
            "curves_with_j_0_char3": "list['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']",
            "supersingular_j_polynomial": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
            "EllipticCurve_with_order": "Iterator['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']",
            "EllipticCurve_with_prime_order": "Iterator['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']",
        },
        "EllipticCurve_finite_field": {
            # Sage 10.9 finite-field implementations return these concrete
            # values (verified against the WSL runtime): cardinality and
            # Frobenius discriminant are Sage Integers, the Frobenius
            # polynomial is the standard ZZ/FLINT polynomial, and plot() is
            # the 2-D Graphics container.
            "cardinality_pari": "'sage.rings.integer.Integer'",
            "base_ring": FINITE_FIELD_UNION,
            "frobenius_discriminant": "'sage.rings.integer.Integer'",
            "frobenius_polynomial": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "plot": "'sage.plot.graphics.Graphics'",
            "_fetch_cached_order": "None",
            "height_above_floor": "'sage.rings.integer.Integer'",
            "frobenius_order": "'sage.rings.number_field.order.Order_absolute'",
            "endomorphism_order": "'sage.rings.number_field.order.Order_absolute'",
            "frobenius": (
                "'sage.rings.number_field.number_field_element_quadratic.OrderElement_quadratic | "
                "sage.rings.integer.Integer'"
            ),
            "frobenius_endomorphism": "'sage.schemes.elliptic_curves.hom_frobenius.EllipticCurveHom_frobenius'",
            "multiplication_by_p_isogeny": "'sage.schemes.elliptic_curves.hom_composite.EllipticCurveHom_composite'",
        },
    },
    "sage/schemes/elliptic_curves/cardinality.pyi": {
        None: {
            "cardinality_exhaustive": "'sage.rings.integer.Integer'",
            "cardinality_bsgs": "'sage.rings.integer.Integer'",
        },
    },
    "sage/schemes/elliptic_curves/ell_generic.pyi": {
        "EllipticCurve_generic": {
            "a_invariants": "tuple",
            "b_invariants": "tuple",
            "c_invariants": "tuple",
            "is_exact": "bool",
            "is_on_curve": "bool",
            "is_isomorphic": "bool",
            "isomorphisms": "list['sage.schemes.elliptic_curves.weierstrass_morphism.WeierstrassIsomorphism']",
            "isomorphism": "'sage.schemes.elliptic_curves.weierstrass_morphism.WeierstrassIsomorphism'",
            "isomorphism_to": "'sage.schemes.elliptic_curves.weierstrass_morphism.WeierstrassIsomorphism'",
            "frobenius_isogeny": "'sage.schemes.elliptic_curves.hom_frobenius.EllipticCurveHom_frobenius'",
            "plot": "'sage.plot.graphics.Graphics'",
            # The generic curve API constructs a point on the curve.  More
            # specific curve classes override this below, so this remains
            # sound for non-finite base rings as well.
            "__call__": "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint'",
            "gen": "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint'",
        },
    },
    "sage/schemes/elliptic_curves/ell_rational_field.pyi": {
        "EllipticCurve_rational_field": {
            # The rational-curve implementation exposes stable scalar and
            # container results used by common CTF/EC workflows.  Methods
            # that change the coefficient field are intentionally omitted.
            "_set_rank": "None",
            "_set_torsion_order": "None",
            "_set_cremona_label": "None",
            "_set_conductor": "None",
            "_set_modular_degree": "None",
            "_set_gens": "None",
            "lmfdb_page": "str",
            "is_p_integral": "bool",
            "is_integral": "bool",
            "conductor": "'sage.rings.integer.Integer'",
            "Np": "'sage.rings.integer.Integer'",
            "aplist": "list['sage.rings.integer.Integer | int']",
            "anlist": "list['sage.rings.integer.Integer | int']",
            "q_expansion": "'sage.rings.power_series_poly.PowerSeries_poly'",
            "analytic_rank": "'sage.rings.integer.Integer | tuple[sage.rings.integer.Integer, sage.rings.real_mpfr.RealNumber]'",
            "analytic_rank_upper_bound": "'sage.rings.integer.Integer'",
            "three_selmer_rank": "'sage.rings.integer.Integer'",
            "rank": "'sage.rings.integer.Integer'",
            "gens": "list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']",
            "gens_certain": "bool",
            "ngens": "int",
            "regulator": "'sage.rings.real_mpfr.RealNumber'",
            "minimal_model": "Self",
            "is_minimal": "bool",
            "is_p_minimal": "bool",
            "tamagawa_number": "'sage.rings.integer.Integer'",
            "tamagawa_number_old": "'sage.rings.integer.Integer'",
            "tamagawa_exponent": "'sage.rings.integer.Integer'",
            "tamagawa_product": "'sage.rings.integer.Integer'",
            "real_components": "int",
            "has_good_reduction_outside_S": "bool",
            "selmer_rank": "'sage.rings.integer.Integer | cypari2.gen.Gen'",
            "rank_bound": "'sage.rings.integer.Integer | cypari2.gen.Gen'",
            "an": "'sage.rings.integer.Integer'",
            "ap": "'sage.rings.integer.Integer'",
            "modular_degree": "'sage.rings.integer.Integer'",
            "congruence_number": "'sage.rings.integer.Integer'",
            "cremona_label": "str",
            "reduction": "'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field'",
            "torsion_order": "'sage.rings.integer.Integer'",
            "torsion_points": "list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']",
            "root_number": "'sage.rings.integer.Integer'",
            "has_cm": "bool",
            "cm_discriminant": "'sage.rings.integer.Integer'",
            "has_rational_cm": "bool",
            "quadratic_twist": "Self",
            "minimal_quadratic_twist": "Self",
            "is_isogenous": "bool",
            "isogeny_degree": "'sage.rings.integer.Integer'",
            "optimal_curve": "Self",
            "manin_constant": "'sage.rings.integer.Integer'",
            "is_semistable": "bool",
            "is_ordinary": "bool",
            "is_good": "bool",
            "is_supersingular": "bool",
            "supersingular_primes": "list['sage.rings.integer.Integer']",
            "ordinary_primes": "list['sage.rings.integer.Integer']",
            "height": "'sage.rings.real_mpfr.RealNumber'",
            "faltings_height": "'sage.rings.real_mpfr.RealNumber'",
            "integral_x_coords_in_interval": "set['sage.rings.integer.Integer']",
            "integral_points": "list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']",
            "S_integral_points": "list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']",
            "database_curve": "Self",
            "two_descent": "bool",
            "CPS_height_bound": "float",
            "silverman_height_bound": "float",
            "antilogarithm": "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field'",
            "elliptic_exponential": "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_field'",
            "is_local_integral_model": "bool",
            "local_integral_model": "Self",
            "global_integral_model": "Self",
            "integral_short_weierstrass_model": "Self",
            "point_search": "list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']",
            "saturation": "tuple[list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field'], 'sage.rings.integer.Integer', 'sage.rings.real_mpfr.RealNumber']",
            "isogeny_graph": "'sage.graphs.graph.Graph'",
            "isogeny_class": "'sage.schemes.elliptic_curves.isogeny_class.IsogenyClass_EC_Rational'",
            "isogenies_prime_degree": "list['sage.schemes.elliptic_curves.ell_curve_isogeny.EllipticCurveIsogeny']",
            "kodaira_type": "'sage.schemes.elliptic_curves.kodaira_symbol.KodairaSymbol_class'",
            "kodaira_type_old": "'sage.schemes.elliptic_curves.kodaira_symbol.KodairaSymbol_class'",
            "mwrank_curve": "'sage.libs.eclib.interface.mwrank_EllipticCurve'",
            "modular_form": "'sage.modular.modform.element.ModularFormElement_elliptic_curve'",
            "newform": "'sage.modular.modform.element.ModularFormElement_elliptic_curve'",
            "q_eigenform": "'sage.rings.power_series_poly.PowerSeries_poly'",
            "lseries": "'sage.schemes.elliptic_curves.lseries_ell.Lseries_ell'",
            "galois_representation": "'sage.schemes.elliptic_curves.gal_reps.GaloisRepresentation'",
            "modular_symbol_space": "'sage.modular.modsym.subspace.ModularSymbolsSubspace'",
            "modular_symbol": "'sage.schemes.elliptic_curves.ell_modular_symbols.ModularSymbolECLIB | sage.schemes.elliptic_curves.ell_modular_symbols.ModularSymbolSage | sage.schemes.elliptic_curves.mod_sym_num.ModularSymbolNumerical'",
            "tate_curve": "'sage.schemes.elliptic_curves.ell_tate_curve.TateCurve'",
        },
    },
    "sage/rings/integer.pyi": {
        "Integer": {
            "nth_root": "'sage.rings.integer.Integer'",
            # Verified against Sage 10.9 runtime: these low-level integer
            # operations keep Sage's Integer parent, except division which
            # intentionally promotes to Rational and _rpy_ which exports a
            # Python int for RPy.
            "__pos__": "Self",
            "__copy__": "Self",
            "__deepcopy__": "Self",
            "__truediv__": "'sage.rings.rational.Rational'",
            "_div_": "'sage.rings.rational.Rational'",
            "_pow_": "Self",
            "_rpy_": "int",
        },
    },
    "sage/matrix/matrix2.pyi": {
        "Matrix": {
            # solve_left has the same result family as solve_right in Sage 10.9.
            "solve_left": "FreeModuleElement | Matrix",
            # These contracts are stable across matrix implementations.  The
            # source implementation constructs a Factorization for fcp(), a
            # dense ZZ matrix for LLL_gram(), and the dedicated MatrixWindow
            # wrapper for matrix_window().  subdivision() slices through the
            # receiver's own implementation and therefore preserves Self.
            "fcp": "'sage.structure.factorization.Factorization'",
            "LLL_gram": "'sage.matrix.matrix_integer_dense.Matrix_integer_dense'",
            "matrix_window": "'sage.matrix.matrix_window.MatrixWindow'",
            "subdivision": "Self",
            "decomposition_of_subspace": "'sage.structure.sequence.Sequence_generic'",
            # These exact-field transforms construct the same matrix parent
            # as the receiver.  Keeping ``Self`` here exposes the concrete
            # dense/sparse implementation selected by the caller.
            "permutation_normal_form": "Self",
            "zigzag_form": "Self",
            "krylov_matrix": "Self",
            "is_similar": "bool",
            "kernel_on": "'sage.modules.free_module.FreeModule_submodule_field_with_category'",
            "integer_kernel": "'sage.modules.free_module.FreeModule_submodule_pid_with_category'",
            "image": "'sage.modules.free_module.FreeModule_submodule_pid_with_category | sage.modules.free_module.FreeModule_submodule_field_with_category'",
            "det": MATRIX_SCALAR_UNION,
            "determinant": MATRIX_SCALAR_UNION,
            "trace": MATRIX_SCALAR_UNION,
            "trace_of_product": MATRIX_SCALAR_UNION,
            "subdivision_entry": MATRIX_SCALAR_UNION,
            "norm": "'sage.rings.real_mpfr.RealNumber | sage.rings.real_double.RealDoubleElement'",
            "pfaffian": MATRIX_SCALAR_UNION,
            "quantum_determinant": MATRIX_SCALAR_UNION,
            "wiedemann": MATRIX_POLYNOMIAL_UNION,
            "inverse_positive_definite": "Self | 'sage.matrix.matrix_rational_dense.Matrix_rational_dense' | 'sage.matrix.matrix_generic_dense.Matrix_generic_dense' | 'sage.matrix.matrix_complex_double_dense.Matrix_complex_double_dense'",
            "fitting_ideal": "'sage.rings.ideal.Ideal_pid | sage.rings.quotient_ring.QuotientRingIdeal_principal'",
        },
    },
    "sage/matrix/matrix_polynomial_dense.pyi": {
        "Matrix_polynomial_dense": {
            # The series solvers preserve the input shape: a polynomial
            # vector produces a polynomial vector, while a polynomial matrix
            # produces a matrix in this concrete implementation.  The union
            # is the implementation-safe fallback; literal overloads below
            # let PyCharm select the branch from the argument type.
            "solve_left_series_trunc": "'sage.modules.free_module_element.FreeModuleElement' | Self",
            "solve_right_series_trunc": "'sage.modules.free_module_element.FreeModuleElement' | Self",
            "inverse_series_trunc": "Self",
            "hermite_form": "Self | tuple[Self, Self]",
            "popov_form": "Self | tuple[Self, Self]",
            "weak_popov_form": "Self | tuple[Self, Self]",
            "reduced_form": "Self | tuple[Self, Self]",
            "minimal_approximant_basis": "Self",
            "minimal_interpolant_basis": "Self",
            "minimal_kernel_basis": "Self",
            "minimal_relation_basis": "Self",
            "basis_completion": "Self",
        },
    },
    "sage/matrix/matrix_double_dense.pyi": {
        "Matrix_double_dense": {
            # Real/complex double dense matrices preserve their concrete
            # matrix implementation for factorisations and matrix functions.
            # Scalar diagnostics use the RDF/CDF implementation union because
            # this shared base is used by both backends.
            "LU": "tuple[Self, Self, Self]",
            "QR": "tuple[Self, Self]",
            "SVD": "tuple[Self, Self, Self]",
            "__invert__": "Self",
            "cholesky": "Self",
            "exp": "Self",
            "round": "Self",
            "zero_at": "Self",
            "determinant": "'sage.rings.real_double.RealDoubleElement | sage.rings.complex_double.ComplexDoubleElement'",
            "condition": "'sage.rings.real_double.RealDoubleElement'",
            "log_determinant": "'sage.rings.real_double.RealDoubleElement'",
            "norm": "'sage.rings.real_double.RealDoubleElement'",
            "eigenvalues": "list['sage.rings.real_double.RealDoubleElement | sage.rings.complex_double.ComplexDoubleElement']",
        },
    },
    "sage/matrix/matrix_complex_ball_dense.pyi": {
        "Matrix_complex_ball_dense": {
            "__invert__": "Self",
            "exp": "Self",
            "determinant": "'sage.rings.complex_arb.ComplexBall'",
            "trace": "'sage.rings.complex_arb.ComplexBall'",
            "charpoly": "'sage.rings.polynomial.polynomial_complex_arb.Polynomial_complex_arb'",
            "eigenvalues": "'sage.structure.sequence.Sequence_generic'",
        },
    },
    "sage/matrix/matrix_mpolynomial_dense.pyi": {
        "Matrix_mpolynomial_dense": {
            "determinant": "'sage.rings.polynomial.multi_polynomial.MPolynomial'",
            "echelon_form": "Self",
            "echelonize": "None",
            "swapped_columns": "Self",
        },
    },
    "sage/matrix/matrix_integer_sparse.pyi": {
        "Matrix_integer_sparse": {
            "charpoly": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "minpoly": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "rational_reconstruction": "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'",
            "smith_form": "tuple[Self, Self, Self]",
        },
    },
    "sage/matrix/matrix_rational_sparse.pyi": {
        "Matrix_rational_sparse": {
            "add_to_entry": "None",
            "dense_matrix": "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'",
            "echelon_form": "Self",
            "set_row_to_multiple_of_row": "None",
        },
    },
    "sage/matrix/matrix0.pyi": {
        "Matrix": {
            # matrix0 implements these operations by allocating through the
            # receiver's own ``new_matrix``/``__copy__`` path.  Runtime
            # checks over ZZ, QQ and GF(p) therefore preserve the concrete
            # implementation rather than the abstract Matrix base.
            "_add_": "Self",
            "_sub_": "Self",
            "__neg__": "Self",
            "__pos__": "Self",
            "__mod__": "Self",
            "with_swapped_columns": "Self",
            "with_swapped_rows": "Self",
        },
    },
    "sage/matrix/matrix_modn_sparse.pyi": {
        "Matrix_modn_sparse": {
            "determinant": PRIME_FIELD_ELEMENT_UNION,
            "det": PRIME_FIELD_ELEMENT_UNION,
            "trace": PRIME_FIELD_ELEMENT_UNION,
            "trace_of_product": PRIME_FIELD_ELEMENT_UNION,
            "__invert__": "Self",
            "inverse": "Self",
            "matrix_from_columns": "Self",
            "matrix_from_rows": "Self",
            "rank": "int",
            "swap_rows": "None",
            "transpose": "Self",
        },
    },
    "sage/matrix/matrix_modn_dense_float.pyi": {
        "Matrix_modn_dense_float": {
            "determinant": PRIME_FIELD_ELEMENT_UNION,
            "det": PRIME_FIELD_ELEMENT_UNION,
            "trace": PRIME_FIELD_ELEMENT_UNION,
            "trace_of_product": PRIME_FIELD_ELEMENT_UNION,
            "__invert__": "Self",
            "inverse": "Self",
            "transpose": "Self",
        },
    },
    "sage/matrix/matrix_mod2_dense.pyi": {
        "Matrix_mod2_dense": {
            "__invert__": "Self",
            "__neg__": "Self",
            "_add_": "Self",
            "_sub_": "Self",
            "augment": "Self",
            "determinant": "'sage.rings.finite_rings.integer_mod.IntegerMod_int'",
            "doubly_lexical_ordering": "tuple['sage.groups.perm_gps.permgroup_element.SymmetricGroupElement', 'sage.groups.perm_gps.permgroup_element.SymmetricGroupElement']",
            "echelonize": "None",
            "rank": "int",
            "row": "'sage.modules.vector_mod2_dense.Vector_mod2_dense'",
            "str": "str",
            "submatrix": "Self",
            "transpose": "Self",
        },
    },
    "sage/matrix/matrix_gf2e_dense.pyi": {
        "Matrix_gf2e_dense": {
            "__invert__": "Self",
            "__neg__": "Self",
            "_add_": "Self",
            "_sub_": "Self",
            "augment": "Self",
            "cling": "None",
            "determinant": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "echelonize": "None",
            "rank": "int",
            "slice": "tuple['sage.matrix.matrix_mod2_dense.Matrix_mod2_dense', ...]",
            "submatrix": "Self",
            "transpose": "Self",
        },
    },
    "sage/matrix/matrix_gfpn_dense.pyi": {
        "Matrix_gfpn_dense": {
            # MeatAxe finite-extension matrices keep the same concrete
            # implementation for inversion, division, transpose, and kernel
            # matrix; trace is one element of the Givaro extension field.
            "__invert__": "Self",
            "__truediv__": "Self",
            "left_kernel_matrix": "Self",
            "transpose": "Self",
            "trace": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "from_filename": "Self",
            "randomize": "None",
        },
    },
    "sage/matrix/matrix_integer_dense.pyi": {
        "Matrix_integer_dense": {
            # These operations allocate through the integer-dense receiver;
            # the one deliberate exception is ``~M``, which promotes a
            # nonsingular integer matrix to a rational-dense inverse.
            "_add_": "Self",
            "_sub_": "Self",
            "__neg__": "Self",
            "__pow__": INTEGER_MATRIX_POWER_UNION,
            "_lmul_": "Self",
            "__invert__": "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'",
            "inverse_of_unit": "Self",
            "augment": "Self",
            "echelon_form": "Self",
            "transpose": "Self",
            "antitranspose": "Self",
            "determinant": "'sage.rings.integer.Integer'",
            "det": "'sage.rings.integer.Integer'",
            "trace": "'sage.rings.integer.Integer'",
            "trace_of_product": "'sage.rings.integer.Integer'",
            "inverse_positive_definite": "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'",
            "charpoly": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "minpoly": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "frobenius_form": "Self",
            "symplectic_form": "tuple[Self, Self]",
            "saturation": "Self",
            "rational_reconstruction": "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'",
            "gcd": "'sage.rings.integer.Integer'",
            "_ntl_": "'sage.libs.ntl.ntl_mat_ZZ.ntl_mat_ZZ'",
            "_magma_init_": "str",
            "_richcmp_": "bool",
            "decomposition": "'sage.structure.sequence.Sequence_generic'",
            "null_ideal": "'sage.rings.ideal.Ideal_principal'",
            "row": "'sage.modules.vector_integer_dense.Vector_integer_dense'",
            "column": "'sage.modules.vector_integer_dense.Vector_integer_dense'",
            "insert_row": "Self",
            "BKZ": "Self",
        },
    },
    "sage/matrix/matrix_rational_dense.pyi": {
        "Matrix_rational_dense": {
            # Rational-dense linear algebra stays in the same concrete
            # implementation, including inversion and echelonization.
            "_add_": "Self",
            "_sub_": "Self",
            "__neg__": "Self",
            "_lmul_": "Self",
            "__invert__": "Self",
            "inverse": "Self",
            "augment": "Self",
            "echelon_form": "Self",
            "transpose": "Self",
            "antitranspose": "Self",
            "determinant": "'sage.rings.rational.Rational'",
            "det": "'sage.rings.rational.Rational'",
            "trace": "'sage.rings.rational.Rational'",
            "trace_of_product": "'sage.rings.rational.Rational'",
            "inverse_positive_definite": "Self",
            "charpoly": "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'",
            "minpoly": "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'",
            "rank": "int",
            "row": "'sage.modules.vector_rational_dense.Vector_rational_dense'",
            "column": "'sage.modules.vector_rational_dense.Vector_rational_dense'",
            "matrix_from_columns": "Self",
            "add_to_entry": "None",
            "echelonize": "None",
            "set_row_to_multiple_of_row": "None",
            "BKZ": "Self",
            "LLL": "Self",
            "prod_of_row_sums": "'sage.rings.rational.Rational'",
            "_magma_init_": "str",
            "_richcmp_": "bool",
            "decomposition": "'sage.structure.sequence.Sequence_generic'",
        },
    },
    "sage/rings/finite_rings/finite_field_base.pyi": {
        "FiniteField": {
            "order": "'sage.rings.integer.Integer'",
            "cardinality": "'sage.rings.integer.Integer'",
        },
    },
    "sage/rings/finite_rings/finite_field_prime_modn.pyi": {
        "FiniteField_prime_modn": {
            "order": "'sage.rings.integer.Integer'",
            "gen": "'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp'",
            "__iter__": "Iterator['sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp']",
            "random_element": INTEGER_MOD_ELEMENT_UNION,
            "from_integer": INTEGER_MOD_ELEMENT_UNION,
            "prime_subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "polynomial": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
            "polynomial_ring": "'sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p'",
            "extension": FINITE_FIELD_UNION,
        },
    },
    "sage/rings/finite_rings/finite_field_givaro.pyi": {
        "FiniteField_givaro": {
            "gen": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "__iter__": "Iterator['sage.rings.finite_rings.element_givaro.FiniteField_givaroElement']",
            "random_element": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "from_integer": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "prime_subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "polynomial": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
            "polynomial_ring": "'sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p'",
            "extension": FINITE_FIELD_UNION,
        },
    },
    "sage/rings/finite_rings/finite_field_ntl_gf2e.pyi": {
        "FiniteField_ntl_gf2e": {
            "gen": "'sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement'",
            "__iter__": "Iterator['sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement']",
            "random_element": "'sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement'",
            "from_integer": "'sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement'",
            "prime_subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "polynomial": "'sage.rings.polynomial.polynomial_gf2x.Polynomial_GF2X'",
            "polynomial_ring": "'sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p'",
            "extension": FINITE_FIELD_UNION,
        },
    },
    "sage/rings/finite_rings/finite_field_pari_ffelt.pyi": {
        "FiniteField_pari_ffelt": {
            "gen": "'sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt'",
            "__iter__": "Iterator['sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt']",
            "random_element": "'sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt'",
            "from_integer": "'sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt'",
            "prime_subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "subfield": "'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn'",
            "polynomial": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
            "polynomial_ring": "'sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p'",
            "extension": FINITE_FIELD_UNION,
        },
    },
    "sage/rings/finite_rings/element_givaro.pyi": {
        "FiniteField_givaroElement": {
            "_integer_": "'sage.rings.integer.Integer'",
            "_vector_": "'sage.modules.vector_mod2_dense.Vector_mod2_dense | sage.modules.vector_modn_dense.Vector_modn_dense'",
        },
    },
    "sage/rings/finite_rings/element_ntl_gf2e.pyi": {
        "FiniteField_ntl_gf2eElement": {
            "_integer_": "'sage.rings.integer.Integer'",
            "_vector_": "'sage.modules.vector_mod2_dense.Vector_mod2_dense'",
            "trace": "'sage.rings.finite_rings.integer_mod.IntegerMod_int'",
        },
    },
    "sage/rings/finite_rings/element_pari_ffelt.pyi": {
        "FiniteFieldElement_pari_ffelt": {
            "_add_": "Self",
            "_sub_": "Self",
            "_mul_": "Self",
            "_div_": "Self",
            "__neg__": "Self",
            "__pos__": "Self",
            "__invert__": "Self",
            "__pow__": "Self",
            "pth_power": "Self",
            "_integer_": "'sage.rings.integer.Integer'",
            "polynomial": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
            "charpoly": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
            "minpoly": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
        },
    },
    "sage/rings/finite_rings/hom_finite_field.pyi": {
        "FiniteFieldHomomorphism_generic": {
            # ``section()`` constructs the concrete finite-field section
            # wrapper; it is not the abstract ``Section`` base.  The inverse
            # relation is explicit in Sage's docstring and runtime type.
            "section": "'sage.rings.finite_rings.hom_finite_field.SectionFiniteFieldHomomorphism_generic'",
        },
        "FrobeniusEndomorphism_finite_field": {
            # Frobenius powers and inverses remain endomorphisms of the same
            # concrete finite-field map.  ``order()`` is a Sage Integer in
            # Sage 10.9 (the generic metric fallback handles other classes).
            "__pow__": "Self",
            "inverse": "Self",
            "order": "'sage.rings.integer.Integer'",
        },
    },
    "sage/rings/finite_rings/hom_prime_finite_field.pyi": {
        "FrobeniusEndomorphism_prime": {
            "__pow__": "Self",
        },
    },
    "sage/rings/morphism.pyi": {
        "FrobeniusEndomorphism_generic": {
            "__pow__": "Self",
        },
    },
    "sage/rings/padics/morphism.pyi": {
        "FrobeniusEndomorphism_padics": {
            "__pow__": "Self",
        },
    },
    "sage/rings/complex_mpfr.pyi": {
        "ComplexNumber": {
            # Both index branches (real and imaginary component) use Sage's
            # concrete RealNumber implementation; the conditional index does
            # not change the result family.
            "__getitem__": "'sage.rings.real_mpfr.RealNumber'",
            # Complex arithmetic and analytic functions stay in the same
            # arbitrary-precision complex implementation.  Component and
            # magnitude helpers intentionally narrow to the concrete MPFR
            # real implementation instead of the public ``Number`` base.
            "_add_": "Self",
            "_sub_": "Self",
            "_mul_": "Self",
            "_div_": "Self",
            "__pow__": "Self",
            "__neg__": "Self",
            "__pos__": "Self",
            "__invert__": "Self",
            "conjugate": "Self",
            "real": "'sage.rings.real_mpfr.RealNumber'",
            "imag": "'sage.rings.real_mpfr.RealNumber'",
            "argument": "'sage.rings.real_mpfr.RealNumber'",
            "arg": "'sage.rings.real_mpfr.RealNumber'",
            "norm": "'sage.rings.real_mpfr.RealNumber'",
            "__abs__": "'sage.rings.real_mpfr.RealNumber'",
            "exp": "Self",
            "log": "Self",
            "sqrt": "Self",
            "nth_root": "Self",
            "agm": "Self",
            "dilog": "Self",
            "gamma": "Self",
            "gamma_inc": "Self",
            "zeta": "Self",
            "arccos": "Self",
            "arccosh": "Self",
            "arcsin": "Self",
            "arcsinh": "Self",
            "arctan": "Self",
            "arctanh": "Self",
            "coth": "Self",
            "arccoth": "Self",
            "csc": "Self",
            "csch": "Self",
            "arccsch": "Self",
            "sec": "Self",
            "sech": "Self",
            "arcsech": "Self",
            "cot": "Self",
            "cos": "Self",
            "cosh": "Self",
            "eta": "Self",
            "sin": "Self",
            "sinh": "Self",
            "tan": "Self",
            "tanh": "Self",
            "multiplicative_order": "'sage.rings.infinity.PlusInfinity'",
            "additive_order": "'sage.rings.infinity.PlusInfinity'",
            "prec": "'sage.rings.integer.Integer'",
            "__int__": "int",
            "__float__": "float",
            "__complex__": "complex",
            "algebraic_dependency": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
        },
    },
    "sage/rings/real_mpfi.pyi": {
        "RealIntervalFieldElement": {
            # MPFI interval arithmetic and elementary functions remain in the
            # interval parent.  Interval bounds/centers deliberately narrow
            # to MPFR reals, while integer-like predicates/counts retain
            # their scalar contracts.
            "__abs__": "Self",
            "__add__": "Self",
            "__sub__": "Self",
            "__mul__": "Self",
            "__truediv__": "Self",
            "__neg__": "Self",
            "__invert__": "Self",
            "__lshift__": "Self",
            "__rshift__": "Self",
            "real": "Self",
            "imag": "Self",
            "argument": "Self",
            "sqrt": "Self",
            "square_root": "Self",
            "square": "Self",
            "exp": "Self",
            "exp2": "Self",
            "log2": "Self",
            "log10": "Self",
            "sin": "Self",
            "cos": "Self",
            "tan": "Self",
            "gamma": "Self",
            "zeta": "Self",
            "factorial": "Self",
            "floor": "Self",
            "ceil": "Self",
            "round": "Self",
            "trunc": "Self",
            "frac": "Self",
            "intersection": "Self",
            "union": "Self",
            "max": "Self",
            "min": "Self",
            "center": "'sage.rings.real_mpfr.RealNumber'",
            "lower": "'sage.rings.real_mpfr.RealNumber'",
            "upper": "'sage.rings.real_mpfr.RealNumber'",
            "diameter": "'sage.rings.real_mpfr.RealNumber'",
            "absolute_diameter": "'sage.rings.real_mpfr.RealNumber'",
            "magnitude": "'sage.rings.real_mpfr.RealNumber'",
            "mignitude": "'sage.rings.real_mpfr.RealNumber'",
            "relative_diameter": "'sage.rings.real_mpfr.RealNumber'",
            "precision": "'sage.rings.integer.Integer'",
            "multiplicative_order": "'sage.rings.infinity.PlusInfinity'",
            "algebraic_dependency": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "simplest_rational": "'sage.rings.rational.Rational'",
            "unique_integer": "'sage.rings.integer.Integer'",
            "unique_sign": "int",
            "unique_trunc": "'sage.rings.integer.Integer'",
            "is_int": "bool",
            "lexico_cmp": "int",
            "fp_rank_diameter": "'sage.rings.integer.Integer'",
            "bisection": "tuple[Self, Self]",
            "alea": "'sage.rings.real_mpfr.RealNumber'",
        },
    },
    "sage/rings/real_arb.pyi": {
        "RealBall": {
            "__abs__": "Self",
            "real": "Self",
            "imag": "Self",
            "sqrt": "Self",
            "rsqrt": "Self",
            "sqrtpos": "Self",
            "sqrt1pm1": "Self",
            "__neg__": "Self",
            "__invert__": "Self",
            "__lshift__": "Self",
            "__rshift__": "Self",
            "exp": "Self",
            "expm1": "Self",
            "log": "Self",
            "log1p": "Self",
            "sin": "Self",
            "cos": "Self",
            "tan": "Self",
            "gamma": "Self",
            "gamma_inc_lower": "Self",
            "rgamma": "Self",
            "zeta": "Self",
            "zetaderiv": "Self",
            "agm": "Self",
            "erf": "Self",
            "erfi": "Self",
            "lambert_w": "Self",
            "polylog": "Self",
            "rising_factorial": "Self",
            "floor": "Self",
            "ceil": "Self",
            "round": "Self",
            "rad": "Self",
            "rad_as_ball": "Self",
            "mid": "'sage.rings.real_mpfr.RealNumber'",
            "lower": "'sage.rings.real_mpfr.RealNumber'",
            "upper": "'sage.rings.real_mpfr.RealNumber'",
            "diameter": "'sage.rings.real_mpfr.RealNumber'",
            "accuracy": "int",
            "nbits": "int",
            "union": "Self",
        },
    },
    "sage/rings/complex_arb.pyi": {
        "ComplexBall": {
            "__abs__": "'sage.rings.real_arb.RealBall'",
            "__lshift__": "Self",
            "__rshift__": "Self",
            "real": "'sage.rings.real_arb.RealBall'",
            "imag": "'sage.rings.real_arb.RealBall'",
            "arg": "'sage.rings.real_arb.RealBall'",
            "above_abs": "'sage.rings.real_arb.RealBall'",
            "below_abs": "'sage.rings.real_arb.RealBall'",
            "log": "Self",
            "log1p": "Self",
            "sqrt": "Self",
            "rsqrt": "Self",
            "exp": "Self",
            "exppii": "Self",
            "sin": "Self",
            "cos": "Self",
            "tan": "Self",
            "gamma": "Self",
            "rgamma": "Self",
            "zeta": "Self",
            "zetaderiv": "Self",
            "Chi": "Self",
            "Ci": "Self",
            "Ei": "Self",
            "Li": "Self",
            "Shi": "Self",
            "Si": "Self",
            "above_abs": "Self",
            "below_abs": "Self",
            "beta": "Self",
            "chebyshev_T": "Self",
            "chebyshev_U": "Self",
            "log_gamma": "Self",
            "squash": "Self",
            "trim": "Self",
            "max": "Self",
            "min": "Self",
            "polylog": "Self",
            "li": "Self",
            "lambert_w": "Self",
            "elliptic_e": "Self",
            "elliptic_f": "Self",
            "elliptic_k": "Self",
            "elliptic_pi": "Self",
            "elliptic_rf": "Self",
            "elliptic_rg": "Self",
            "elliptic_rj": "Self",
            "elliptic_sigma": "Self",
            "elliptic_zeta": "Self",
            "elliptic_e_inc": "Self",
            "elliptic_pi_inc": "Self",
            "elliptic_invariants": "tuple[Self, Self]",
            "elliptic_roots": "tuple[Self, Self, Self]",
            "eisenstein": "list[Self]",
            "gegenbauer_C": "Self",
            "hermite_H": "Self",
            "hypergeometric": "Self",
            "laguerre_L": "Self",
            "legendre_P": "Self",
            "legendre_Q": "Self",
            "log_barnes_g": "Self",
            "modular_delta": "Self",
            "modular_eta": "Self",
            "modular_j": "Self",
            "modular_lambda": "Self",
            "pow": "Self",
            "psi": "Self",
            "rising_factorial": "Self",
            "erf": "Self",
            "erfc": "Self",
            "airy": "Self",
            "airy_ai": "Self",
            "airy_ai_prime": "Self",
            "airy_bi": "Self",
            "airy_bi_prime": "Self",
            "bessel_I": "Self",
            "bessel_J": "Self",
            "bessel_K": "Self",
            "bessel_Y": "Self",
            "bessel_J_Y": "tuple[Self, Self]",
            "round": "Self",
            "trim": "Self",
            "union": "Self",
            "diameter": "'sage.rings.real_mpfr.RealNumber'",
            "nbits": "int",
            "accuracy": "int",
        },
    },
    "sage/rings/complex_mpc.pyi": {
        "MPComplexNumber": {
            "__abs__": "'sage.rings.real_mpfr.RealNumber'",
            "__getitem__": "'sage.rings.real_mpfr.RealNumber'",
            "real": "'sage.rings.real_mpfr.RealNumber'",
            "imag": "'sage.rings.real_mpfr.RealNumber'",
            "argument": "'sage.rings.real_mpfr.RealNumber'",
            "norm": "'sage.rings.real_mpfr.RealNumber'",
            "sqrt": "Self",
            "nth_root": "Self",
            "agm": "Self",
            "dilog": "Self",
            "gamma": "Self",
            "gamma_inc": "Self",
            "zeta": "Self",
            "prec": "int",
        },
    },
    "sage/rings/real_mpfr.pyi": {
        "RealNumber": {
            # MPFR operations documented as producing a real number remain
            # in the receiver's concrete precision/rounding domain.  The
            # sqrt overload keeps the documented negative-input extension
            # branch explicit; all=True is handled below by overloads.
            "__abs__": "Self",
            "real": "Self",
            "imag": "'sage.rings.integer.Integer'",
            "__add__": "Self",
            "__sub__": "Self",
            "__mul__": "Self",
            "__truediv__": "Self",
            "__lshift__": "Self",
            "__rshift__": "Self",
            "__invert__": "Self",
            "__pow__": "Self",
            "__neg__": "Self",
            "__pos__": "Self",
            "_integer_": "'sage.rings.integer.Integer'",
            "_complex_number_": "'sage.rings.complex_mpfr.ComplexNumber'",
            "_rpy_": "float",
            "hex": "str",
            "str": "str",
            "integer_part": "'sage.rings.integer.Integer'",
            "trunc": "'sage.rings.integer.Integer'",
            "round": "'sage.rings.integer.Integer'",
            "floor": "'sage.rings.integer.Integer'",
            "ceil": "'sage.rings.integer.Integer'",
            "sign": "int",
            "precision": "'sage.rings.integer.Integer'",
            "fp_rank": "'sage.rings.integer.Integer'",
            "fp_rank_delta": "'sage.rings.integer.Integer'",
            "multiplicative_order": "'sage.rings.infinity.PlusInfinity'",
            "ulp": "Self",
            "epsilon": "Self",
            "frac": "Self",
            "nexttoward": "Self",
            "nextabove": "Self",
            "nextbelow": "Self",
            "exact_rational": "'sage.rings.rational.Rational'",
            "simplest_rational": "'sage.rings.rational.Rational'",
            "as_integer_ratio": "tuple",
            "algebraic_dependency": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "sqrt": "Self | 'sage.rings.complex_mpfr.ComplexNumber'",
            "cube_root": "Self",
            "nth_root": "Self",
            "log": "Self",
            "log2": "Self",
            "log10": "Self",
            "log1p": "Self",
            "exp": "Self",
            "exp2": "Self",
            "exp10": "Self",
            "expm1": "Self",
            "eint": "Self",
            "cos": "Self",
            "sin": "Self",
            "tan": "Self",
            "sincos": "tuple[Self, Self]",
            "arccos": "Self",
            "arcsin": "Self",
            "arctan": "Self",
            "cosh": "Self",
            "sinh": "Self",
            "tanh": "Self",
            "coth": "Self",
            "arccoth": "Self",
            "cot": "Self",
            "csch": "Self",
            "arccsch": "Self",
            "csc": "Self",
            "sech": "Self",
            "arcsech": "Self",
            "sec": "Self",
            "arccosh": "Self",
            "arcsinh": "Self",
            "arctanh": "Self",
            "agm": "Self",
            "erf": "Self",
            "erfc": "Self",
            "j0": "Self",
            "j1": "Self",
            "jn": "Self",
            "y0": "Self",
            "y1": "Self",
            "yn": "Self",
            "gamma": "Self",
            "log_gamma": "Self",
            "zeta": "Self",
        },
    },
    "sage/rings/rational.pyi": {
        "Rational": {
            # Rational arithmetic preserves QQ; characteristic-polynomial
            # helpers use the concrete FLINT rational polynomial backend.
            "__add__": "Self",
            "__sub__": "Self",
            "__mul__": "Self",
            "__truediv__": "Self",
            "__neg__": "Self",
            "__pos__": "Self",
            "_add_": "Self",
            "_sub_": "Self",
            "_mul_": "Self",
            "_div_": "Self",
            "_neg_": "Self",
            "_pow_": "Self",
            "__mpq__": "'gmpy2.mpq'",
            "charpoly": "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'",
            "minpoly": "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'",
            "continued_fraction": "'sage.rings.continued_fraction.ContinuedFraction_periodic'",
            "sqrt": "'sage.symbolic.expression.Expression | sage.rings.rational.Rational | sage.rings.integer.Integer'",
            "log": "'sage.symbolic.expression.Expression | sage.rings.integer.Integer'",
            "gamma": "'sage.symbolic.expression.Expression | sage.rings.integer.Integer'",
            "additive_order": "'sage.rings.integer.Integer | sage.rings.infinity.PlusInfinity'",
            "multiplicative_order": "'sage.rings.integer.Integer | sage.rings.infinity.PlusInfinity'",
            "factor": "'sage.structure.factorization.Factorization'",
        },
    },
    "sage/rings/real_double.pyi": {
        "RealDoubleElement": {
            # RDF is represented by a GSL subclass at runtime, but the
            # generated public stub exposes RealDoubleElement as its stable
            # base.  These methods preserve that concrete implementation.
            "__abs__": "Self",
            "abs": "Self",
            "real": "Self",
            "imag": "Self",
            "__add__": "Self",
            "__sub__": "Self",
            "__mul__": "Self",
            "__truediv__": "Self",
            "__invert__": "Self",
            "__neg__": "Self",
            "__pos__": "Self",
            "_add_": "Self",
            "_sub_": "Self",
            "_mul_": "Self",
            "_div_": "Self",
            "conjugate": "Self",
            "sqrt": "Self",
            "cube_root": "Self",
            "agm": "Self",
            "exp": "Self",
            "log": "Self",
            "log10": "Self",
            "log_b": "Self",
            "sin": "Self",
            "cos": "Self",
            "tan": "Self",
            "sec": "Self",
            "csc": "Self",
            "cot": "Self",
            "arcsin": "Self",
            "arccos": "Self",
            "arctan": "Self",
            "sinh": "Self",
            "cosh": "Self",
            "tanh": "Self",
            "sech": "Self",
            "csch": "Self",
            "coth": "Self",
            "arcsinh": "Self",
            "arccosh": "Self",
            "arctanh": "Self",
            "arcsech": "Self",
            "arccsch": "Self",
            "arccoth": "Self",
            "eta": "Self",
            "gamma": "Self",
            "zeta": "Self",
            "integer_part": "'sage.rings.integer.Integer'",
            "trunc": "'sage.rings.integer.Integer'",
            "round": "'sage.rings.integer.Integer'",
            "floor": "'sage.rings.integer.Integer'",
            "ceil": "'sage.rings.integer.Integer'",
            "sign": "int",
            "as_integer_ratio": "tuple",
            "algebraic_dependency": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
        },
    },
    "sage/rings/complex_double.pyi": {
        "ComplexDoubleElement": {
            # CDF's arithmetic and analytic functions preserve the complex
            # double implementation; projections and magnitudes return the
            # concrete RDF implementation instead.
            "__getitem__": "'sage.rings.real_double.RealDoubleElement'",
            "_add_": "Self",
            "_sub_": "Self",
            "_mul_": "Self",
            "_div_": "Self",
            "_pow_": "Self",
            "__invert__": "Self",
            "__neg__": "Self",
            "conjugate": "Self",
            "conj": "Self",
            "sqrt": "Self",
            "nth_root": "Self",
            "exp": "Self",
            "log": "Self",
            "log10": "Self",
            "log_b": "Self",
            "sin": "Self",
            "cos": "Self",
            "tan": "Self",
            "sec": "Self",
            "csc": "Self",
            "cot": "Self",
            "arcsin": "Self",
            "arccos": "Self",
            "arctan": "Self",
            "arccsc": "Self",
            "arccot": "Self",
            "arcsec": "Self",
            "sinh": "Self",
            "cosh": "Self",
            "tanh": "Self",
            "sech": "Self",
            "csch": "Self",
            "coth": "Self",
            "arcsinh": "Self",
            "arccosh": "Self",
            "arctanh": "Self",
            "arcsech": "Self",
            "arccsch": "Self",
            "arccoth": "Self",
            "eta": "Self",
            "agm": "Self",
            "dilog": "Self",
            "gamma": "Self",
            "gamma_inc": "Self",
            "zeta": "Self",
            "real": "'sage.rings.real_double.RealDoubleElement'",
            "imag": "'sage.rings.real_double.RealDoubleElement'",
            "arg": "'sage.rings.real_double.RealDoubleElement'",
            "argument": "'sage.rings.real_double.RealDoubleElement'",
            "abs": "'sage.rings.real_double.RealDoubleElement'",
            "__abs__": "'sage.rings.real_double.RealDoubleElement'",
            "abs2": "'sage.rings.real_double.RealDoubleElement'",
            "norm": "'sage.rings.real_double.RealDoubleElement'",
            "logabs": "'sage.rings.real_double.RealDoubleElement'",
            "prec": "'sage.rings.integer.Integer'",
            "__int__": "int",
            "__float__": "float",
            "__complex__": "complex",
            "algebraic_dependency": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
        },
    },
    "sage/rings/complex_interval.pyi": {
        "ComplexIntervalFieldElement": {
            "__getitem__": "'sage.rings.real_mpfi.RealIntervalFieldElement'",
        },
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
        "PolynomialRing_generic": {
            "gen": POLYNOMIAL_RETURN_UNION,
            "_element_constructor_": POLYNOMIAL_RETURN_UNION,
            "_implementation_names": "list[str]",
            "_is_valid_homomorphism_": "bool",
            "_magma_init_": "str",
            "_macaulay2_init_": "str",
            "cyclotomic_polynomial": POLYNOMIAL_RETURN_UNION,
            "parameter": POLYNOMIAL_RETURN_UNION,
            "monomial": POLYNOMIAL_RETURN_UNION,
            "extend_variables": MULTIVARIATE_POLYNOMIAL_RING_RETURN_UNION,
            "krull_dimension": "'sage.rings.integer.Integer | int'",
            "random_element": POLYNOMIAL_RETURN_UNION,
            "_monics_degree": "Iterator",
            "_monics_max": "Iterator",
            "_polys_degree": "Iterator",
            "_polys_max": "Iterator",
            "_Karatsuba_threshold": "int",
            "karatsuba_threshold": "int",
            "set_karatsuba_threshold": "None",
        },
        "PolynomialRing_dense_mod_p": {
            # The parent class is shared by FLINT and NTL implementations;
            # the concrete element is selected by ``implementation=``.
            "gen": POLYNOMIAL_MOD_P_ELEMENT_UNION,
            "random_element": POLYNOMIAL_MOD_P_ELEMENT_UNION,
        },
        "PolynomialRing_dense_finite_field": {
            "random_element": FINITE_FIELD_POLYNOMIAL_ELEMENT_UNION,
        },
    },
    "sage/rings/finite_rings/integer_mod_ring.pyi": {
        "IntegerModRing_generic": {
            "random_element": INTEGER_MOD_ELEMENT_UNION,
        },
    },
    "sage/rings/integer_ring.pyi": {
        "IntegerRing_class": {
            # ZZ.range() and ZZ.__iter__ both yield Sage Integer values; the
            # outer range result is a Python list and iteration is a generator.
            "range": "list['sage.rings.integer.Integer']",
            "__iter__": "Iterator['sage.rings.integer.Integer']",
            "__call__": "'sage.rings.integer.Integer'",
            "gen": "'sage.rings.integer.Integer'",
            "random_element": "'sage.rings.integer.Integer'",
        },
    },
    "sage/rings/rational_field.pyi": {
        "RationalField": {
            "__iter__": "Iterator['sage.rings.rational.Rational']",
            "range_by_height": "Iterator['sage.rings.rational.Rational']",
            "gen": "'sage.rings.rational.Rational'",
            "random_element": "'sage.rings.rational.Rational'",
        },
    },
    "sage/rings/finite_rings/element_base.pyi": {
        "FinitePolyExtElement": {
            # Finite extension elements expose coefficients in their prime
            # field.  Sage's concrete IntegerMod implementation varies with
            # the modulus size, so retain the complete implementation union
            # rather than collapsing to a parent class.
            "__getitem__": "'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp'",
            "__iter__": "Iterator['sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp']",
            "_vector_": "'sage.modules.vector_mod2_dense.Vector_mod2_dense | sage.modules.vector_modn_dense.Vector_modn_dense'",
            "norm": INTEGER_MOD_ELEMENT_UNION,
            "trace": INTEGER_MOD_ELEMENT_UNION,
            "pth_power": "Self",
            "pth_root": "Self",
            "conjugate": "Self",
        },
    },
    "sage/rings/finite_rings/integer_mod.pyi": {
        "IntegerMod_abstract": {
            # Prime-modulus residue elements implement norm/trace as the
            # identity, so Self keeps IntegerMod_int/int64/gmp concrete.
            "norm": "Self",
            "trace": "Self",
        },
    },
    "sage/schemes/elliptic_curves/ell_point.pyi": {
        "EllipticCurvePoint": {
            "curve": "'sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic'",
            # Point addition, negation, subtraction and scalar action stay on
            # the same curve and preserve the concrete point implementation.
            "_add_": "Self",
            "_neg_": "Self",
            "_sub_": "Self",
            "_acted_upon_": "Self",
        },
        "EllipticCurvePoint_field": {
            # Coordinate conversion is a stable Python tuple for every field
            # implementation; the coordinate element classes themselves are
            # intentionally left parent-dependent.
            "__tuple__": "tuple",
            "_neg_": "Self",
            "_divide_out": "tuple[Self, 'sage.rings.integer.Integer']",
            "__pari__": "'cypari2.gen.Gen'",
        },
        "EllipticCurvePoint_finite_field": {
            # These methods are implemented directly by the finite-field
            # point class.  Annotate the existing documented definitions so
            # the generated stub has one authoritative declaration rather
            # than a duplicate insertion.
            "curve": "'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field'",
            "_acted_upon_": "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field'",
            # The finite-field order algorithm returns a Sage Integer for
            # both PARI and the inherited generic-small paths.
            "_compute_order": "'sage.rings.integer.Integer'",
        },
    },
    "sage/rings/polynomial/polynomial_element.pyi": {
        "Polynomial": {
            # These operations preserve the concrete polynomial receiver.
            # ``Self`` is intentional: emitting the abstract Polynomial base
            # here would make ``f.derivative()`` lose the concrete
            # Polynomial_zmod_flint/Polynomial_dense_mod_p API in PyCharm.
            "__pow__": POLYNOMIAL_POWER_UNION,
            "derivative": "Self",
            "gcd": "Self",
            "xgcd": "tuple[Self, Self, Self]",
            "quo_rem": "tuple[Self, Self]",
            "_symbolic_": "'sage.symbolic.expression.Expression'",
            "_pari_init_": "'cypari2.gen.Gen'",
            "_magma_init_": "str",
            "_giac_init_": "str",
            "global_height": "'sage.rings.real_mpfr.RealNumber'",
            "local_height": "'sage.rings.real_mpfr.RealNumber'",
            "local_height_arch": "'sage.rings.real_mpfr.RealNumber'",
            "add_bigoh": "'sage.rings.power_series_poly.PowerSeries_poly | sage.rings.power_series_pari.PowerSeries_pari'",
            "mod": "Self",
        },
    },
    "sage/rings/polynomial/multi_polynomial.pyi": {
        "MPolynomial": {
            # ``root`` selects a predicate-only result or the pair carrying a
            # square root.  The union keeps the implementation signature safe;
            # literal overloads below recover branch-specific completion.
            "is_square": "bool | tuple[bool, Self | None]",
        },
    },
    "sage/rings/polynomial/laurent_polynomial_mpair.pyi": {
        "LaurentPolynomial_mpair": {
            "is_square": "bool | tuple[bool, Self | None]",
        },
    },
    "sage/rings/polynomial/polynomial_zmod_flint.pyi": {
        "Polynomial_zmod_flint": {
            # GF(p)[x] evaluation/resultants produce the concrete modular
            # element family; polynomial transforms stay in this FLINT
            # implementation.  Rational reconstruction returns a pair of
            # polynomials in the same parent.
            "__call__": PRIME_FIELD_ELEMENT_UNION,
            "factor": "'sage.structure.factorization.Factorization'",
            "resultant": PRIME_FIELD_ELEMENT_UNION,
            "small_roots": "list['sage.rings.integer.Integer']",
            "__pow__": POLYNOMIAL_POWER_UNION,
            "rational_reconstruction": "tuple[Self, Self]",
            "squarefree_decomposition": "'sage.structure.factorization.Factorization'",
            "monic": "Self",
            "reverse": "Self",
            "revert_series": "Self",
            "minpoly_mod": "Self",
            "compose_mod": "Self",
        },
    },
    "sage/rings/polynomial/polynomial_modn_dense_ntl.pyi": {
        "Polynomial_dense_mod_p": {
            "__pow__": "'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p | sage.rings.fraction_field_element.FractionFieldElement'",
            "resultant": PRIME_FIELD_ELEMENT_UNION,
            "discriminant": PRIME_FIELD_ELEMENT_UNION,
        },
        # The NTL ZZ/nZZ implementations share the same concrete polynomial
        # receiver for composition/minimal-polynomial transforms.  Their
        # conversion helpers have stable Python/NTL outer types.
        "Polynomial_dense_mod_n": {
            "__pari__": "'cypari2.gen.Gen'",
            "int_list": "list[int]",
            "minpoly_mod": "Self",
            "compose_mod": "Self",
            "ntl_ZZ_pX": "'sage.libs.ntl.ntl_ZZ_pX.ntl_ZZ_pX'",
            "ntl_set_directly": "None",
            "small_roots": "list['sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp']",
        },
        "Polynomial_dense_modn_ntl_ZZ": {
            "int_list": "list[int]",
            "ntl_set_directly": "None",
        },
        "Polynomial_dense_modn_ntl_zz": {
            "int_list": "list[int]",
            "ntl_set_directly": "None",
        },
    },
    "sage/rings/polynomial/polynomial_quotient_ring_element.pyi": {
        "PolynomialQuotientRingElement": {
            "__pari__": "'cypari2.gen.Gen'",
            # ``field_extension`` is the documented QQ quotient-ring bridge:
            # a number field, its generator map, and the inverse homset map.
            "field_extension": "tuple['sage.rings.number_field.number_field.NumberField_absolute', 'sage.rings.morphism.RingHomomorphism_im_gens', 'sage.rings.number_field.homset.NumberFieldHomset_with_category.element_class']",
        },
    },
    "sage/rings/polynomial/polynomial_integer_dense_flint.pyi": {
        "Polynomial_integer_dense_flint": {
            "factor": "'sage.structure.factorization.Factorization'",
            "_add_": "Self",
            "_sub_": "Self",
            "_neg_": "Self",
            "quo_rem": "tuple[Self, Self]",
            "gcd": "Self",
            "lcm": "Self",
            "xgcd": "tuple[Self, Self, Self]",
            "_mul_": "Self",
            "_lmul_": "Self",
            "_rmul_": "Self",
            "__pow__": POLYNOMIAL_POWER_UNION,
            "__floordiv__": "Self",
            "squarefree_decomposition": "'sage.structure.factorization.Factorization'",
            "factor_mod": "'sage.structure.factorization.Factorization'",
            "factor_padic": "'sage.structure.factorization.Factorization'",
            "resultant": "'sage.rings.integer.Integer'",
            "reverse": "Self",
            "revert_series": "Self",
            "discriminant": "'sage.rings.integer.Integer'",
            "_eval_mpfr_": "'sage.rings.real_mpfr.RealNumber'",
            "_eval_mpfi_": "'sage.rings.real_mpfi.RealIntervalFieldElement'",
            "pseudo_divrem": "tuple[Self, Self, 'sage.rings.integer.Integer']",
            "real_root_intervals": "list[tuple[tuple['sage.rings.rational.Rational', 'sage.rings.rational.Rational'], 'sage.rings.integer.Integer']]",
        },
    },
    "sage/rings/polynomial/polynomial_rational_flint.pyi": {
        "Polynomial_rational_flint": {
            "_add_": "Self",
            "_sub_": "Self",
            "_neg_": "Self",
            "quo_rem": "tuple[Self, Self]",
            "gcd": "Self",
            "lcm": "Self",
            "xgcd": "tuple[Self, Self, Self]",
            "_mul_": "Self",
            "_lmul_": "Self",
            "_rmul_": "Self",
            "__pow__": POLYNOMIAL_POWER_UNION,
            "__floordiv__": "Self",
            "_mod_": "Self",
            "squarefree_decomposition": "'sage.structure.factorization.Factorization'",
            "factor_mod": "'sage.structure.factorization.Factorization'",
            "factor_padic": "'sage.structure.factorization.Factorization'",
            "resultant": "'sage.rings.rational.Rational'",
            "reverse": "Self",
            "revert_series": "Self",
            "discriminant": "'sage.rings.rational.Rational'",
            "__lshift__": "Self",
            "__rshift__": "Self",
            "numerator": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
            "denominator": "'sage.rings.integer.Integer'",
            "hensel_lift": "list['sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint']",
            "galois_group_davenport_smith_test": "int",
            "real_root_intervals": "list[tuple[tuple['sage.rings.rational.Rational', 'sage.rings.rational.Rational'], 'sage.rings.integer.Integer']]",
        },
    },
    # The basic graph catalogue consists entirely of concrete ``Graph``
    # constructors.  Their optional ``immutable`` flag changes mutability,
    # not the public Sage graph class, so retain one concrete completion
    # surface instead of leaving every catalogue function UNKNOWN.
    "sage/graphs/generators/basic.pyi": {
        None: {
            name: "'sage.graphs.graph.Graph'"
            for name in {
                "BullGraph", "ButterflyGraph", "CircularLadderGraph",
                "ClawGraph", "CompleteBipartiteGraph", "CompleteGraph",
                "CompleteMultipartiteGraph", "CorrelationGraph", "CycleGraph",
                "DartGraph", "DiamondGraph", "EmptyGraph", "ForkGraph",
                "GemGraph", "Grid2dGraph", "GridGraph", "HouseGraph",
                "HouseXGraph", "LadderGraph", "MoebiusLadderGraph",
                "PathGraph", "StarGraph", "Toroidal6RegularGrid2dGraph",
                "ToroidalGrid2dGraph",
            }
        },
    },
}

# Number-field elements expose a small, stable conversion/arithmetic protocol
# even though Sage implements the concrete element class in Cython.  These
# contracts are deliberately limited to methods whose result family is fixed
# by the source documentation/runtime (scalar conversions, parent-preserving
# arithmetic, and the documented square/n-th-root branches).  Ideal-valued
# and embedding-dependent methods remain unresolved rather than being forced
# through the public ``Element`` base.
CURATED_ANNOTATIONS["sage/rings/number_field/number_field_element.pyi"] = {
    "NumberFieldElement": {
        "__abs__": "Self | 'sage.rings.real_mpfr.RealNumber'",
        "_acb_": "'sage.rings.complex_arb.ComplexBall'",
        "_algebraic_": "'sage.rings.qqbar.AlgebraicNumber'",
        "_complex_double_": "'sage.rings.complex_double.ComplexDoubleElement'",
        "_div_": "Self",
        "_mpfr_": "'sage.rings.real_mpfr.RealNumber'",
        "_pari_init_": "str",
        "_symbolic_": "'sage.symbolic.expression.Expression'",
        "abs": "Self | 'sage.rings.real_mpfr.RealNumber'",
        "abs_non_arch": "'sage.rings.real_mpfr.RealNumber'",
        "gcd": "Self",
        "matrix": MATRIX_ELEMENT_UNION,
        "sign": "int",
        "sqrt": "Self | list[Self]",
        "nth_root": "Self | list[Self]",
    },
}

# Quadratic elements have fixed concrete conversion and continued-fraction
# result classes.  The real-part method is intentionally a narrow union: a
# totally-real quadratic element stays in ``Self``, while an imaginary
# quadratic element returns a rational scalar.
CURATED_ANNOTATIONS["sage/rings/number_field/number_field_element_quadratic.pyi"] = {
    "NumberFieldElement_quadratic": {
        "__abs__": "Self | 'sage.rings.real_mpfr.RealNumber'",
        "__invert__": "Self",
        "__neg__": "Self",
        "_acb_": "'sage.rings.complex_arb.ComplexBall'",
        "_add_": "Self",
        "_arb_": "'sage.rings.real_arb.RealBall'",
        "_complex_mpfi_": "'sage.rings.complex_interval.ComplexIntervalFieldElement'",
        "_integer_": "'sage.rings.integer.Integer'",
        "_lmul_": "Self",
        "_maxima_init_": "str",
        "_mul_": "Self",
        "_polymake_init_": "str",
        "_rational_": "'sage.rings.rational.Rational'",
        "_real_mpfi_": "'sage.rings.real_mpfi.RealIntervalFieldElement'",
        "_rmul_": "Self",
        "_sub_": "Self",
        "ceil": "'sage.rings.integer.Integer'",
        "charpoly": "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'",
        "continued_fraction": "'sage.rings.continued_fraction.ContinuedFraction_periodic'",
        "continued_fraction_list": "tuple",
        "denominator": "'sage.rings.integer.Integer'",
        "floor": "'sage.rings.integer.Integer'",
        "imag": "'sage.rings.rational.Rational'",
        "minpoly": "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'",
        "norm": "'sage.rings.rational.Rational'",
        "numerator": "Self",
        "real": "Self | 'sage.rings.rational.Rational'",
        "round": "'sage.rings.integer.Integer'",
        "sign": "int",
        "trace": "'sage.rings.rational.Rational'",
    },
}

# Number-field ideals have a stable PARI/scalar/container protocol.  These
# methods are independent of the concrete field element parent, so they can
# be exposed as exact implementation classes.  The two parent-dependent
# methods (``random_element`` and ``residue_symbol``) intentionally remain
# unresolved: their element class is selected by the ambient number field.
CURATED_ANNOTATIONS["sage/rings/number_field/number_field_ideal.pyi"] = {
    "NumberFieldIdeal": {
        "S_ideal_class_log": "list['sage.rings.integer.Integer']",
        "__elements_from_hnf": "list",
        "__pari__": "'cypari2.gen.Gen'",
        "_gens_repr": "tuple",
        "_magma_init_": "'sage.interfaces.magma.MagmaElement'",
        "_pari_init_": "str",
        "_quadratic_form": "'sage.quadratic_forms.binary_qf.BinaryQF'",
        "_repr_short": "str",
        "absolute_norm": "'sage.rings.rational.Rational'",
        "absolute_ramification_index": "'sage.rings.integer.Integer'",
        "artin_symbol": "'sage.rings.number_field.galois_group.GaloisGroupElement'",
        "basis": "'sage.structure.sequence.Sequence_generic'",
        "decomposition_group": "'sage.rings.number_field.galois_group.GaloisGroup_subgroup'",
        "free_module": "'sage.modules.free_module_integer.FreeModule_submodule_with_basis_integer'",
        "gens_reduced": "tuple",
        "ideal_class_log": "list['sage.rings.integer.Integer']",
        "inertia_group": "'sage.rings.number_field.galois_group.GaloisGroup_subgroup'",
        "intersection": "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'",
        "pari_hnf": "'cypari2.gen.Gen'",
        "pari_prime": "'cypari2.gen.Gen'",
        "ramification_group": "'sage.rings.number_field.galois_group.GaloisGroup_subgroup'",
        "reduce_equiv": "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'",
        "relative_norm": "'sage.rings.rational.Rational'",
        "relative_ramification_index": "'sage.rings.integer.Integer'",
        "smallest_integer": "'sage.rings.integer.Integer'",
        "valuation": "'sage.rings.integer.Integer'",
    },
}

# Number-field parents expose several fixed-shape conversion and arithmetic
# helpers.  Keep the parent-dependent field factories unresolved, while
# recording the documented tuple/list/scalar and PARI/GAP/Magma contracts.
CURATED_ANNOTATIONS["sage/rings/number_field/number_field.pyi"] = {
    "NumberField_generic": {
        "_S_class_group_and_units": "tuple",
        "_S_class_group_quotient_matrix": MATRIX_ELEMENT_UNION,
        "_fractional_ideal_class_": "type",
        "_ideal_class_": "type",
        "_libgap_": "'sage.libs.gap.element.GapElement_Ring'",
        "_magma_init_": "'sage.interfaces.magma.MagmaElement'",
        "_magma_polynomial_": "'sage.interfaces.magma.MagmaElement'",
        "_pari_absolute_structure": "tuple",
        "_pari_init_": "str",
        "_positive_integral_elements_with_trace": "list",
        "pari_rnfnorm_data": "'cypari2.gen.Gen'",
        "quadratic_defect": "'sage.rings.integer.Integer' | 'sage.rings.infinity.PlusInfinity'",
        "subfield_from_elements": "tuple",
    },
}

# Elliptic-curve isogenies have a few methods whose result is independent of
# the base field.  Keep the isogeny self-returning and expose the integer and
# polynomial contracts used by CTF code; rational-map/scaling methods stay
# dynamic because their parent is selected by the curve's coordinate ring.
CURATED_ANNOTATIONS["sage/schemes/elliptic_curves/ell_curve_isogeny.pyi"] = {
    "EllipticCurveIsogeny": {
        "__clear_cached_values": "None",
        "__compute_codomain": "None",
        "__compute_via_kohel": "tuple",
        "__compute_via_kohel_numeric": "tuple",
        "__compute_via_velu": "tuple",
        "__compute_via_velu_numeric": "tuple",
        "__init_algebraic_structs": "None",
        "__init_from_kernel_gens": "None",
        "__init_from_kernel_list": "None",
        "__init_from_kernel_point": "None",
        "__init_from_kernel_polynomial": "None",
        "__init_kernel_polynomial": "None",
        "__init_kernel_polynomial_velu": "None",
        "__initialize_rational_maps": "None",
        "__initialize_rational_maps_via_kohel": "tuple",
        "__initialize_rational_maps_via_velu": "tuple",
        "__neg__": "Self",
        "__perform_inheritance_housekeeping": "None",
        "__set_post_isomorphism": "None",
        "__set_pre_isomorphism": "None",
        "__setup_post_isomorphism": "None",
        "__update_kernel_data": "None",
        "__velu_sum_helper": "tuple",
        "dual": "Self",
        "inseparable_degree": "'sage.rings.integer.Integer'",
        "kernel_polynomial": POLYNOMIAL_RETURN_UNION,
        "_composition_impl": "Self",
    },
}

# The common elliptic-curve homomorphism protocol has a few field-independent
# scalar/serialization results.  Polynomial-producing and morphism factories
# stay unresolved because their concrete parent is selected by each child
# implementation.
CURATED_ANNOTATIONS["sage/schemes/elliptic_curves/hom.pyi"] = {
    "EllipticCurveHom": {
        "_repr_type": "str",
        "characteristic_polynomial": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
        "inseparable_degree": "'sage.rings.integer.Integer'",
        "separable_degree": "'sage.rings.integer.Integer'",
        "trace": "'sage.rings.integer.Integer'",
    },
}

# Elliptic-curve field helpers have stable predicate/container contracts.  The
# twist constructors preserve the concrete curve implementation; kernel
# polynomials use the existing backend union because their parent follows the
# curve's base field.
CURATED_ANNOTATIONS["sage/schemes/elliptic_curves/ell_field.pyi"] = {
    "EllipticCurve_field": {
        "is_quadratic_twist": "bool",
        "is_quartic_twist": "bool",
        "is_sextic_twist": "bool",
        "isogeny_ell_graph": "'sage.graphs.graph.Graph'",
        "kernel_polynomial_from_divisor": POLYNOMIAL_RETURN_UNION,
        "kernel_polynomial_from_point": POLYNOMIAL_RETURN_UNION,
        "quartic_twist": "Self",
        "sextic_twist": "Self",
        "torsion_basis": "tuple",
        "torsion_gens": "list",
        "two_torsion_rank": "'sage.rings.integer.Integer'",
    },
}

# Number-field elliptic curves document concrete outputs for their common
# CTF-facing operations.  Models preserve the receiver class; arithmetic
# invariants use the concrete number-field ideal/scalar classes; and the
# descent/search helpers retain their documented tuple/list structure.
CURATED_ANNOTATIONS["sage/schemes/elliptic_curves/ell_number_field.pyi"] = {
    "EllipticCurve_number_field": {
        "base_extend": "Self",
        "cm_discriminant": "'sage.rings.integer.Integer'",
        "conductor": "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'",
        "galois_representation": "'sage.schemes.elliptic_curves.gal_reps_number_field.GaloisRepresentation'",
        "gens_quadratic": "list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']",
        "global_integral_model": "Self",
        "global_minimal_model": "Self",
        "global_minimality_class": "'sage.rings.number_field.class_group.ClassGroup'",
        "height_function": "'sage.schemes.elliptic_curves.height.EllipticCurveCanonicalHeight'",
        "height_pairing_matrix": MATRIX_ELEMENT_UNION,
        "is_local_integral_model": "bool",
        "kodaira_symbol": "'sage.schemes.elliptic_curves.kodaira_symbol.KodairaSymbol_class'",
        "local_data": "'sage.schemes.elliptic_curves.ell_local_data.EllipticCurveLocalData' | list['sage.schemes.elliptic_curves.ell_local_data.EllipticCurveLocalData']",
        "local_integral_model": "Self",
        "local_minimal_model": "Self",
        "minimal_discriminant_ideal": "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'",
        "rank": "'sage.rings.integer.Integer'",
        "rank_bounds": "tuple['sage.rings.integer.Integer', 'sage.rings.integer.Integer']",
        "rational_points": "list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']",
        "real_components": "int",
        "reduction": "'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field'",
        "regulator_of_points": "'sage.rings.real_mpfr.RealNumber'",
        "saturation": "tuple[list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field'], 'sage.rings.integer.Integer', 'sage.rings.real_mpfr.RealNumber']",
        "simon_two_descent": "tuple['sage.rings.integer.Integer', 'sage.rings.integer.Integer', list['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_number_field']]",
        "torsion_subgroup": "'sage.schemes.elliptic_curves.ell_torsion.EllipticCurveTorsionSubgroup' | 'sage.groups.additive_abelian.additive_abelian_wrapper.AdditiveAbelianGroupWrapper'",
    },
}

# Sandpile's cache builders are explicit mutators (the docstrings show the
# cached attribute being populated and no value being returned).  Its public
# graph/algebra helpers likewise document stable outer containers, so expose
# those directly instead of leaving the whole module behind dynamic UNKNOWN
# results.
CURATED_ANNOTATIONS["sage/sandpiles/sandpile.pyi"] = {
    "Sandpile": {
        "show": "None",
        "show3d": "None",
        "laplacian": "'sage.matrix.matrix_integer_sparse.Matrix_integer_sparse'",
        "reduced_laplacian": "'sage.matrix.matrix_integer_sparse.Matrix_integer_sparse'",
        "_set_max_stable": "None",
        "_set_max_stable_div": "None",
        "_set_out_degrees": "None",
        "out_degree": "int | dict",
        "_set_in_degrees": "None",
        "in_degree": "int | dict",
        "_set_burning_config": "None",
        "_set_identity": "None",
        "identity": "'sage.sandpiles.sandpile.SandpileConfig' | list[int]",
        "_set_recurrents": "None",
        "_set_superstables": "None",
        "_set_group_gens": "None",
        "_set_min_recurrents": "None",
        "tutte_polynomial": MULTIVARIATE_POLYNOMIAL_RETURN_UNION,
        "_set_avalanche_polynomial": "None",
        "avalanche_polynomial": MULTIVARIATE_POLYNOMIAL_RETURN_UNION,
        "_set_invariant_factors": "None",
        "_set_hilbert_function": "None",
        "_set_smith_form": "None",
        "_set_jacobian_representatives": "None",
        "picard_representatives": "list",
        "stable_configs": "Iterator['sage.sandpiles.sandpile.SandpileConfig']",
        "markov_chain": "Iterator['sage.sandpiles.sandpile.SandpileConfig | sage.sandpiles.sandpile.SandpileDivisor']",
        "_set_stationary_density": "None",
        "betti_complexes": "list",
        "_set_betti_complexes": "None",
        "_set_ring": "None",
        "ring": MULTIVARIATE_POLYNOMIAL_RING_RETURN_UNION,
        "_set_ideal": "None",
        "ideal": "'sage.rings.polynomial.multi_polynomial_ideal.MPolynomialIdeal | sage.rings.polynomial.multi_polynomial_sequence.PolynomialSequence_generic'",
        "_set_resolution": "None",
        "_set_groebner": "None",
        "groebner": "'sage.rings.polynomial.multi_polynomial_sequence.PolynomialSequence_generic'",
        "betti": "list",
        "jacobian_representatives": "list",
    },
}

# Matroid's core set algorithms have backend-independent outer result types.
# Keep the concrete wrapper classes for minors/duals and polyhedra, while
# retaining explicit bool/tuple unions for the documented certificate flags.
CURATED_ANNOTATIONS["sage/matroids/matroid.pyi"] = {
    "Matroid": {
        "closure": "frozenset",
        "k_closure": "frozenset",
        "augment": "frozenset",
        "max_coindependent": "frozenset",
        "coclosure": "frozenset",
        "is_valid": "bool | tuple",
        "lattice_of_flats": "'sage.combinat.posets.lattices.FiniteLatticePoset'",
        "contract": "'sage.matroids.minor_matroid.MinorMatroid'",
        "__truediv__": "'sage.matroids.minor_matroid.MinorMatroid'",
        "delete": "'sage.matroids.minor_matroid.MinorMatroid'",
        "dual": "'sage.matroids.dual_matroid.DualMatroid'",
        "has_minor": "bool | tuple",
        "has_line_minor": "bool | tuple",
        "is_isomorphic": "bool | tuple",
        "modular_cut": "set",
        "linear_subclasses": "'sage.matroids.extension.LinearSubclasses'",
        "extensions": "'sage.matroids.extension.MatroidExtensions'",
        "coextensions": "list",
        "girth": "int | 'sage.rings.infinity.PlusInfinity'",
        "binary_matroid": "'sage.matroids.linear_matroid.BinaryMatroid' | None",
        "ternary_matroid": "'sage.matroids.linear_matroid.TernaryMatroid' | None",
        "is_circuit_chordal": "bool | tuple",
        "is_chordal": "bool | tuple",
        "chordality": "'sage.rings.integer.Integer'",
        "max_weight_independent": "frozenset",
        "max_weight_coindependent": "frozenset",
        "intersection": "frozenset",
        "intersection_unweighted": "frozenset",
        "tutte_polynomial": MULTIVARIATE_POLYNOMIAL_RETURN_UNION,
        "characteristic_polynomial": "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'",
        "flat_cover": "list",
        "matroid_polytope": POLYHEDRON_RETURN_UNION,
        "independence_matroid_polytope": POLYHEDRON_RETURN_UNION,
        "show": "None",
        "automorphism_group": "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'",
    },
}

# The generic elliptic-curve implementation documents these transformations
# as staying on the same curve/base ring.  The serialization hooks are plain
# strings and the symbolic bridge is a concrete symbolic expression; field
# changing factories intentionally remain dynamic in the base class.
CURATED_ANNOTATIONS.setdefault("sage/schemes/elliptic_curves/ell_generic.pyi", {}).setdefault("EllipticCurve_generic", {}).update({
        "_pari_init_": "str",
        "_magma_init_": "str",
        "_symbolic_": "'sage.symbolic.expression.Expression'",
        "rst_transform": "Self",
        "scale_curve": "Self",
        "change_weierstrass_model": "Self",
        "short_weierstrass_model": "Self",
})

# Integer/rational order and interface conversions have fixed scalar/foreign
# representations.  Keep these separate from parent-dependent arithmetic so
# CTF scripts get useful completion without inventing a ring type.
CURATED_ANNOTATIONS.setdefault("sage/rings/integer.pyi", {}).setdefault("Integer", {}).update({
        "additive_order": ORDER_RETURN_UNION,
        "multiplicative_order": ORDER_RETURN_UNION,
        "_libgap_": "'sage.libs.gap.element.GapElement_Integer'",
})
CURATED_ANNOTATIONS.setdefault("sage/rings/rational.pyi", {}).setdefault("Rational", {}).update({
        "__pari__": "'cypari2.gen.Gen'",
        "_magma_init_": "str",
        "_sympy_": "'sympy.core.numbers.Rational'",
})

# The integer ring's field/degree and foreign-runtime bridges have fixed
# singleton/scalar results.  ``zeta`` succeeds only for roots that actually
# lie in ``ZZ``; every successful branch is therefore a Sage Integer.
CURATED_ANNOTATIONS.setdefault("sage/rings/integer_ring.pyi", {}).setdefault("IntegerRing_class", {}).update({
        "_polymake_init_": "str",
        "_sympy_": "'sympy.sets.fancysets.Integers'",
        "absolute_degree": "int",
        "fraction_field": "'sage.rings.rational_field.RationalField'",
        "krull_dimension": "int",
        "zeta": "'sage.rings.integer.Integer'",
})

# Integer residue rings have backend-independent group/scalar protocols.  The
# constructor and ``field`` factory use the existing finite-field unions;
# parent-dependent square roots/generators remain dynamic.
CURATED_ANNOTATIONS.setdefault("sage/rings/finite_rings/integer_mod_ring.pyi", {}).setdefault("IntegerModRing_generic", {}).update({
        "_element_constructor_": INTEGER_MOD_ELEMENT_UNION,
        "_pari_order": "'cypari2.gen.Gen'",
        "_pseudo_fraction_field": "Self",
        "degree": "'sage.rings.integer.Integer'",
        "factored_order": "'sage.structure.factorization_integer.IntegerFactorization'",
        "field": FINITE_FIELD_UNION,
        "krull_dimension": "'sage.rings.integer.Integer'",
        "modulus": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
        "multiplicative_group_is_cyclic": "bool",
        "multiplicative_subgroups": "tuple",
        "square_roots_of_one": "tuple",
        "unit_group_exponent": "'sage.rings.integer.Integer'",
        "unit_group_order": "'sage.rings.integer.Integer'",
})

# Category metadata is a pure container/string protocol.  These contracts do
# not expose the dynamic parent/element factories, but make hierarchy and
# introspection helpers useful to completion without inventing a category.
CURATED_ANNOTATIONS["sage/categories/category.pyi"] = {
    "Category": {
        "_all_super_categories": "list",
        "_all_super_categories_proper": "list",
        "_label": "str",
        "_repr_object_names": "str",
        "_set_of_super_categories": "frozenset",
        "_short_name": "str",
        "axioms": "frozenset",
        "required_methods": "dict",
    },
}

# ``Category`` has a small set of hierarchy/introspection methods whose
# docstrings commit to a fixed Python outer type.  Dynamic category factories
# (``example``, ``parent_class`` construction, and ``__call__``) stay
# unresolved; these annotations cover only the source-proven booleans,
# concrete graph, class objects, and category lists.
CURATED_ANNOTATIONS["sage/categories/category.pyi"]["Category"].update({
    "_subcategory_hook_": "bool",
    "__classcontains__": "bool",
    "_is_subclass": "bool",
    "category_graph": "'sage.graphs.graph.Graph'",
    "_super_categories": "list",
    "_super_categories_for_classes": "list",
    "full_super_categories": "list",
    "_make_named_class": "type",
    "subcategory_class": "type",
    "parent_class": "type",
    "element_class": "type",
    "morphism_class": "type",
})

# Graphics accessors and mutators have stable runtime shapes independent of
# the primitive payload.  Setter/getter methods return their stored option,
# while explicit ``set_*`` methods mutate in place and return ``None``.
CURATED_ANNOTATIONS["sage/plot/graphics.pyi"] = {
    "Graphics": {
        "set_aspect_ratio": "None",
        "aspect_ratio": "float | str",
        "legend": "bool",
        "set_axes_range": "None",
        "set_flip": "None",
        "fontsize": "int | float",
        "axes_labels_size": "float",
        "axes": "bool",
        "axes_color": "tuple",
        "axes_label_color": "tuple",
        "axes_width": "float",
        "tick_label_color": "tuple",
        "__radd__": "Self",
        "__add__": "Self",
        "add_primitive": "None",
        "plot": "Self",
        "plot3d": "'sage.plot.plot3d.base.Graphics3dGroup'",
        "_extract_kwds_for_show": "dict",
        "_set_extra_kwds": "None",
        "_set_scale": "tuple",
        "xmin": "int | float",
        "xmax": "int | float",
        "ymin": "int | float",
        "ymax": "int | float",
        "_matplotlib_tick_formatter": "tuple",
        "_get_vmin_vmax": "tuple",
        "matplotlib": "'matplotlib.figure.Figure'",
        "save_image": "None",
        "description": "str",
    },
}

# The pickle-explainer opcode handlers are stack mutators: each handler
# updates the virtual machine and has no Python return value.  The two
# observable exceptions are documented explicitly by Sage: ``run_pickle``
# yields a SageInputExpression, while ``pop_to_mark`` materializes a list.
# Stack payloads from ``pop``/``share`` remain dynamic and are intentionally
# left UNKNOWN.
CURATED_ANNOTATIONS["sage/misc/explain_pickle.pyi"] = {
    "PickleExplainer": {
        "run_pickle": "'sage.misc.sage_input.SageInputExpression'",
        "check_value": "None",
        "push": "None",
        "push_and_share": "None",
        "push_mark": "None",
        "pop_to_mark": "list",
        "APPEND": "None",
        "APPENDS": "None",
        "_APPENDS_helper": "None",
        "BINFLOAT": "None",
        "BINGET": "None",
        "BININT": "None",
        "BININT1": "None",
        "BININT2": "None",
        "BINPUT": "None",
        "BINSTRING": "None",
        "BINUNICODE": "None",
        "BUILD": "None",
        "DICT": "None",
        "DUP": "None",
        "EMPTY_DICT": "None",
        "EMPTY_LIST": "None",
        "EMPTY_TUPLE": "None",
        "EXT1": "None",
        "EXT2": "None",
        "EXT4": "None",
        "FLOAT": "None",
        "GET": "None",
        "GLOBAL": "None",
        "INST": "None",
        "INT": "None",
        "LIST": "None",
        "LONG": "None",
        "LONG1": "None",
        "LONG4": "None",
        "LONG_BINGET": "None",
        "LONG_BINPUT": "None",
        "MARK": "None",
        "NEWFALSE": "None",
        "NEWTRUE": "None",
        "NEWOBJ": "None",
        "NONE": "None",
        "OBJ": "None",
        "PERSID": "None",
        "BINPERSID": "None",
        "POP": "None",
        "POP_MARK": "None",
        "PROTO": "None",
        "PUT": "None",
        "REDUCE": "None",
        "SETITEM": "None",
        "SETITEMS": "None",
        "_SETITEMS_helper": "None",
        "SHORT_BINSTRING": "None",
        "STOP": "None",
        "STRING": "None",
        "TUPLE": "None",
        "TUPLE1": "None",
        "TUPLE2": "None",
        "TUPLE3": "None",
        "UNICODE": "None",
    },
}

# 3-D graphics use the same concrete scene object for transformations and
# expose stable serialization/container results.  The renderer-specific
# payloads vary internally, but their documented outer types are fixed.
CURATED_ANNOTATIONS["sage/plot/plot3d/base.pyi"] = {
    "Graphics3d": {
        "__add__": "Self",
        "aspect_ratio": "list",
        "frame_aspect_ratio": "list",
        "bounding_box": "tuple",
        "transform": "Self",
        "translate": "Self",
        "scale": "Self",
        "rotate": "Self",
        "rotateX": "Self",
        "rotateY": "Self",
        "rotateZ": "Self",
        "viewpoint": "'sage.plot.plot3d.base.Viewpoint'",
        "x3d": "str",
        "tachyon": "str",
        "obj": "str",
        "export_jmol": "None",
        "json_repr": "list",
        "jmol_repr": "list",
        "tachyon_repr": "list",
        "obj_repr": "list",
        "threejs_repr": "list",
        "texture_set": "set",
        "mtl_str": "str",
        "flatten": "Self",
        "save_image": "None",
        "save": "None",
        "stl_binary": "bytes",
        "plot": "Self",
    },
}

# The 3-D scene base class has similarly stable transformation and
# serialization contracts.  These are outer result types verified from Sage
# 10.9 docs/runtime; primitive-specific payloads remain intentionally broad.
CURATED_ANNOTATIONS["sage/plot/plot3d/base.pyi"]["Graphics3d"].update({
    "__add__": "Self",
    "aspect_ratio": "list",
    "frame_aspect_ratio": "list",
    "bounding_box": "tuple",
    "transform": "Self",
    "translate": "Self",
    "scale": "Self",
    "rotate": "Self",
    "rotateX": "Self",
    "rotateY": "Self",
    "rotateZ": "Self",
    "viewpoint": "'sage.plot.plot3d.base.Viewpoint'",
    "x3d": "str",
    "tachyon": "str",
    "obj": "str",
    "export_jmol": "None",
    "json_repr": "list",
    "jmol_repr": "list",
    "tachyon_repr": "list",
    "obj_repr": "list",
    "threejs_repr": "list",
    "texture_set": "set",
    "mtl_str": "str",
    "flatten": "Self",
    "save_image": "None",
    "save": "None",
    "stl_binary": "bytes",
    "plot": "Self",
})

# Polynomial term orders are value objects: comparison/block composition keep
# the term-order class, exponent comparisons return tuples, and all external
# serializations are strings.  The block list/matrix accessors are the only
# parent-dependent shapes, so retain their documented outer unions.
CURATED_ANNOTATIONS["sage/rings/polynomial/term_order.pyi"] = {
    "TermOrder": {
        # The Cython copy helper mutates ``self`` and returns ``None``; it is
        # named ``__copy`` (without the trailing dunder) in Sage's stub.
        "__copy": "None",
        "sortkey_invlex": "tuple",
        "greater_tuple": "tuple",
        "greater_tuple_matrix": "tuple",
        "greater_tuple_lex": "tuple",
        "greater_tuple_invlex": "tuple",
        "greater_tuple_deglex": "tuple",
        "greater_tuple_degrevlex": "tuple",
        "greater_tuple_negdegrevlex": "tuple",
        "greater_tuple_negdeglex": "tuple",
        "greater_tuple_degneglex": "tuple",
        "greater_tuple_neglex": "tuple",
        "greater_tuple_wdeglex": "tuple",
        "greater_tuple_wdegrevlex": "tuple",
        "greater_tuple_negwdeglex": "tuple",
        "greater_tuple_negwdegrevlex": "tuple",
        "greater_tuple_block": "tuple",
        "tuple_weight": "int",
        "singular_moreblocks": "int",
        "macaulay2_str": "str",
        "magma_str": "str",
        "blocks": "list | tuple",
        "matrix": MATRIX_ELEMENT_UNION,
        "weights": "tuple",
        "__eq__": "bool",
        "__ne__": "bool",
        "__add__": "Self",
        "__getitem__": "Self",
    },
}

# PolyDict is the low-level multivariate polynomial value object.  Its
# arithmetic and calculus operations preserve the same dictionary-backed
# polynomial, formatting helpers return strings, and degree/exponent helpers
# expose stable scalar/tuple results.  Coefficient lookup remains dynamic.
CURATED_ANNOTATIONS["sage/rings/polynomial/polydict.pyi"] = {
    "PolyDict": {
        "remove_zeros": "None",
        "apply_map": "None",
        "rich_compare": "bool",
        "degree": "int",
        "total_degree": "int",
        "polynomial_coefficient": "Self",
        "coefficient": "Self",
        "homogenize": "Self",
        "latex": "str",
        "poly_repr": "str",
        "__iadd__": "Self",
        "__neg__": "Self",
        "__add__": "Self",
        "__mul__": "Self",
        "scalar_rmult": "Self",
        "scalar_lmult": "Self",
        "term_lmult": "Self",
        "term_rmult": "Self",
        "__sub__": "Self",
        "derivative_i": "Self",
        "derivative": "Self",
        "integral_i": "Self",
        "integral": "Self",
        "min_exp": "'sage.rings.polynomial.polydict.ETuple | None'",
        "max_exp": "'sage.rings.polynomial.polydict.ETuple | None'",
        "lcmt": "'sage.rings.polynomial.polydict.ETuple'",
    },
}

# Free modules have fixed outer containers and matrix/scalar invariants.  The
# element and parent-changing factories depend on the base ring and therefore
# intentionally remain dynamic instead of falling back to a shared module
# base class.
CURATED_ANNOTATIONS["sage/modules/free_module.pyi"] = {
    "FreeModule_generic": {
        "construction": "tuple",
        "_eq": "bool",
        "cardinality": CARDINALITY_RETURN_UNION,
        "basis": "list",
        "basis_matrix": MATRIX_ELEMENT_UNION,
        "matrix": MATRIX_ELEMENT_UNION,
        "codimension": "'sage.rings.integer.Integer'",
        "discriminant": "'sage.rings.integer.Integer | sage.rings.rational.Rational'",
        "free_module": "Self",
        "gram_matrix": MATRIX_ELEMENT_UNION,
        "inner_product_matrix": MATRIX_ELEMENT_UNION,
        "_magma_init_": "str",
        "_macaulay2_": "str",
        "scale": "Self",
        "__radd__": "Self",
        "_mul_": "Self",
    },
}

# Tate-algebra series operations preserve the concrete series implementation
# at fixed precision.  Scalar coefficient/index access remains parent
# dependent, while precision/degree/valuation use the documented integer or
# infinity families and Euclidean division keeps its tuple outer shape.
CURATED_ANNOTATIONS["sage/rings/tate_algebra_element.pyi"] = {
    "TateAlgebraElement": {
        "inverse_of_unit": "Self",
        "square_root": "Self",
        "sqrt": "Self",
        "nth_root": "Self",
        "__lshift__": "Self",
        "__rshift__": "Self",
        "restriction": "Self",
        "add_bigoh": "Self",
        "lift_to_precision": "Self",
        "precision_absolute": "'sage.rings.integer.Integer | int'",
        "valuation": "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity'",
        "precision_relative": "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity'",
        "log": "Self",
        "exp": "Self",
        "weierstrass_degree": "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity'",
        "degree": "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity'",
        "degrees": "tuple",
        "residue": POLYNOMIAL_RETURN_UNION,
        "quo_rem": "tuple",
        "__mod__": "Self | list[Self]",
        "__floordiv__": "Self | list[Self]",
        "reduce": "Self",
        "Spoly": "Self",
        "leading_monomial": "'sage.rings.tate_algebra_element.TateAlgebraTerm'",
        "leading_term": "'sage.rings.tate_algebra_element.TateAlgebraTerm'",
        "weierstrass_degrees": "tuple",
    },
}

# Cyclotomic number fields have concrete scalar/ideal/sequence contracts that
# are independent of the chosen embedding.  Embedding maps themselves stay
# dynamic (their homset element class depends on the codomain), while field
# elements and roots of unity use Sage's absolute number-field element class.
CURATED_ANNOTATIONS.setdefault("sage/rings/number_field/number_field.pyi", {}).setdefault("NumberField_cyclotomic", {}).update({
        "construction": "tuple",
        "_magma_init_": "str",
        "_libgap_": "'sage.libs.gap.element.GapElement_Ring'",
        "_n": "'sage.rings.integer.Integer'",
        "_log_gen": "'sage.rings.integer.Integer | None'",
        "_element_constructor_": "'sage.rings.number_field.number_field_element.NumberFieldElement_absolute'",
        "_coerce_from_other_cyclotomic_field": "'sage.rings.number_field.number_field_element.NumberFieldElement_absolute | None'",
        "_coerce_from_gap": "'sage.rings.number_field.number_field_element.NumberFieldElement_absolute'",
        "complex_embeddings": "'sage.structure.sequence.Sequence_generic'",
        "real_embeddings": "'sage.structure.sequence.Sequence_generic'",
        "embeddings": "list",
        "signature": "tuple[int, int]",
        "different": "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'",
        "discriminant": "'sage.rings.integer.Integer'",
        "next_split_prime": "'sage.rings.integer.Integer'",
        "_pari_integral_basis": "list",
        "zeta_order": "'sage.rings.integer.Integer'",
        "zeta": "'sage.rings.number_field.number_field_element.NumberFieldElement_absolute'",
        "number_of_roots_of_unity": "'sage.rings.integer.Integer'",
        "roots_of_unity": "list['sage.rings.number_field.number_field_element.NumberFieldElement_absolute']",
})

# REPLACE: member name -> annotation expression for defs that already have
# an annotation.  Used to point factory returns at the most capable real
# class so member completion covers the commonly used subclass surface.
CURATED_REPLACE_ANNOTATIONS: dict[str, dict[str, dict[str, str]]] = {
    "sage/schemes/elliptic_curves/ell_point.pyi": {
        "EllipticCurvePoint": {
            "_acted_upon_": "Self",
        },
        "EllipticCurvePoint_field": {
            "_add_": "Self",
        },
    },
    "sage/schemes/elliptic_curves/ell_finite_field.pyi": {
        "EllipticCurve_finite_field": {
            # The finite-field curve enumerators are concrete point
            # containers, not an untyped tuple/Sequence.  This keeps
            # ``E.gens()[0].log(...)`` and ``E.points()[0].order()`` visible
            # to the IDE while preserving the runtime container classes.
            "gens": "tuple['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field', ...]",
            "points": "'sage.structure.sequence.Sequence_generic[sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field]'",
        },
    },
    "sage/rings/polynomial/polynomial_element.pyi": {
        "Polynomial": {
            # Retarget an earlier broad Polynomial annotation to Self when
            # this pass is rerun over an already-curated staging tree.
            "__pow__": POLYNOMIAL_POWER_UNION,
            "derivative": "Self",
            "gcd": "Self",
            "xgcd": "tuple[Self, Self, Self]",
            "quo_rem": "tuple[Self, Self]",
            # Replace public ``Polynomial`` protocol returns with concrete
            # implementation families (or receiver-preserving ``Self``).
            "compose_trunc": "Self",
            "inverse_of_unit": POLYNOMIAL_RETURN_UNION,
            "inverse_mod": POLYNOMIAL_RETURN_UNION,
            "inverse_series_trunc": POLYNOMIAL_RETURN_UNION,
            "revert_series": POLYNOMIAL_RETURN_UNION,
            "_mul_trunc_": POLYNOMIAL_RETURN_UNION,
            "multiplication_trunc": POLYNOMIAL_RETURN_UNION,
            "square": "Self",
            "any_irreducible_factor": POLYNOMIAL_RETURN_UNION,
            "base_extend": POLYNOMIAL_RETURN_UNION,
            "change_variable_name": "Self",
            "denominator": POLYNOMIAL_RETURN_UNION,
            "numerator": POLYNOMIAL_RETURN_UNION,
            "integral": POLYNOMIAL_RETURN_UNION,
            "lcm": POLYNOMIAL_RETURN_UNION,
            "lm": "Self",
            "lt": "Self",
            "monic": "Self",
            "polynomial": POLYNOMIAL_RETURN_UNION,
            "composed_op": "Self",
            "compose_power": "Self",
            "adams_operator_on_roots": "Self",
            "symmetric_power": "Self",
            "reciprocal_transform": "Self",
            "truncate": "Self",
            "radical": "Self",
            "cyclotomic_part": "Self",
            "homogenize": POLYNOMIAL_RETURN_UNION,
            "nth_root": POLYNOMIAL_RETURN_UNION,
            "map_coefficients": POLYNOMIAL_RETURN_UNION,
            # Stable interface conversions and height values are absent from
            # the generated annotations but fixed by the source contract.
            "_symbolic_": "'sage.symbolic.expression.Expression'",
            "_pari_init_": "'cypari2.gen.Gen'",
            "_magma_init_": "str",
            "_giac_init_": "str",
            "global_height": "'sage.rings.real_mpfr.RealNumber'",
            "local_height": "'sage.rings.real_mpfr.RealNumber'",
            "local_height_arch": "'sage.rings.real_mpfr.RealNumber'",
            "add_bigoh": "'sage.rings.power_series_poly.PowerSeries_poly | sage.rings.power_series_pari.PowerSeries_pari'",
            "mod": "Self",
        },
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
        "PolynomialRing_generic": {
            "gen": POLYNOMIAL_RETURN_UNION,
        },
        "PolynomialRing_dense_mod_p": {
            "gen": POLYNOMIAL_MOD_P_ELEMENT_UNION,
        },
    },
    "sage/matrix/matrix0.pyi": {
        "Matrix": {
            # These two methods always copy and swap in-place matrix storage;
            # unlike scalar-rescaling helpers they never need to coerce into
            # a different base ring, so the concrete receiver is preserved.
            "with_swapped_columns": "Self",
            "with_swapped_rows": "Self",
        },
    },
    "sage/matrix/matrix_integer_dense.pyi": {
        "Matrix_integer_dense": {
            # Sage 10.9 returns a native Python int for rank(), even though
            # older generated stubs exposed Sage Integer here.
            "rank": "int",
        },
    },
    # .sage resolves unqualified factories through sage.all, so its aliases
    # must be corrected as well as their originating modules.  Otherwise
    # PyCharm follows _FactoryReturn_matrix / _FactoryReturn_EllipticCurve to
    # a narrow concrete implementation (Matrix_integer_dense or the rational
    # curve class) and never reaches the shared capability surface.
    "sage/matrix/constructor.pyi": {
        None: {
            "matrix": "'sage.matrix.matrix2.Matrix'",
        },
    },
    "sage/crypto/mq/rijndael_gf.pyi": {
        "RijndaelGF": {
            # Sage 10.9 returns a plain Python ``str`` here (rather than a
            # StringMonoidElement despite older generated stubs claiming the
            # latter).  Keep the index aligned with the runtime object.
            "_GF_to_bin": "str",
        },
    },
    "sage/all.pyi": {
        None: {
            "matrix": "'sage.matrix.matrix2.Matrix'",
            "Matrix": "'sage.matrix.matrix2.Matrix'",
            "vector": "'sage.modules.free_module_element.FreeModuleElement'",
            "EllipticCurve": "'sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic'",
        },
    },
}

# The generated QQ stub uses a broad NumberField alias for ``number_field``
# and unparameterized iterator/tuple aliases.  Retarget these existing
# annotations to the concrete singleton contracts so reruns remain precise.
CURATED_REPLACE_ANNOTATIONS["sage/rings/rational_field.pyi"] = {
    "RationalField": {
        "gens": "tuple['sage.rings.rational.Rational']",
        "number_field": "Self",
        "selmer_group_iterator": "Iterator['sage.rings.rational.Rational']",
    },
}

# ``sage.matrix.special`` is imported through the global ``matrix``
# constructor.  The generated module stubs historically used the public
# ``matrix0.Matrix`` protocol for only a few functions and omitted the rest;
# retarget every matrix-producing constructor to the concrete implementation
# union so ``solve_right``/``determinant`` and backend-specific members remain
# discoverable in PyCharm.
CURATED_REPLACE_ANNOTATIONS["sage/matrix/special.pyi"] = {
    None: {
        name: MATRIX_ELEMENT_UNION
        for name in {
            "column_matrix", "random_matrix", "diagonal_matrix",
            "identity_matrix", "zero_matrix",
        }
    },
}

# Most special-matrix constructors omit an annotation in the generated
# source.  Their documentation and implementation both construct a matrix
# in the selected parent; annotate the two private shape helpers with their
# stable tuple contracts and the public constructors with the same concrete
# implementation union.
CURATED_ANNOTATIONS["sage/matrix/special.pyi"] = {
    None: {
        "_determine_block_matrix_grid": "tuple[list[int], list[int]]",
        "_determine_block_matrix_rows": "tuple[list[int], list[int], int]",
        "matrix_method": "collections.abc.Callable",
        **{
            name: MATRIX_ELEMENT_UNION
            for name in {
                "block_diagonal_matrix", "block_matrix", "circulant",
                "companion_matrix", "elementary_matrix", "hankel", "hilbert",
                "ith_to_zero_rotation_matrix", "jordan_block", "lehmer",
                "ones_matrix", "random_bistochastic_matrix",
                "random_diagonalizable_matrix", "random_echelonizable_matrix",
                "random_rref_matrix", "random_subspaces_matrix",
                "random_unimodular_matrix", "random_unitary_matrix", "toeplitz",
                "vandermonde", "vector_on_axis_rotation_matrix",
            }
        },
    },
}

# Multivariate polynomial implementations are selected by the ring backend
# (Singular or the generic polydict implementation).  Their public list and
# conversion helpers nevertheless have stable outer contracts; replace the
# generated base-class annotations that would otherwise expose the abstract
# ``MPolynomial`` or the unrelated ``TermOrder`` class.
CURATED_REPLACE_ANNOTATIONS["sage/rings/polynomial/multi_polynomial_element.pyi"] = {
    "MPolynomial_element": {
        "subs": MULTIVARIATE_POLYNOMIAL_RETURN_UNION,
        "monomials": "list",
        "univariate_polynomial": POLYNOMIAL_RETURN_UNION,
    },
}
CURATED_REPLACE_ANNOTATIONS["sage/rings/polynomial/multi_polynomial_libsingular.pyi"] = {
    "MPolynomial_libsingular": {
        "monomials": "list",
        "univariate_polynomial": POLYNOMIAL_RETURN_UNION,
    },
}
CURATED_REPLACE_ANNOTATIONS["sage/rings/polynomial/multi_polynomial.pyi"] = {
    "MPolynomial": {
        # The documented result is ``(associate, unit)``; the generated
        # ``Self`` annotation loses the unit and is therefore misleading.
        "canonical_associate": "tuple",
    },
}

# OVERLOAD: documented parameter/return correlations which cannot be recovered
# from a broad union annotation alone.  These contracts are consumed by the
# generic overload machinery in the generated API index; the Kotlin plugin does
# not recognize these class or member names.
CURATED_OVERLOADS: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    "sage/schemes/elliptic_curves/ell_number_field.pyi": {
        "EllipticCurve_number_field": {
            # ``local_data`` returns one record for an explicit prime and a
            # list covering the discriminant support when omitted.
            "local_data": (
                "def local_data(self, P: Literal[None] = None, proof=None, algorithm='pari', globally=False) -> list['sage.schemes.elliptic_curves.ell_local_data.EllipticCurveLocalData']: ...",
                "def local_data(self, P, proof=None, algorithm='pari', globally=False) -> 'sage.schemes.elliptic_curves.ell_local_data.EllipticCurveLocalData': ...",
            ),
            # An omitted ``n`` constructs the dedicated elliptic-curve torsion
            # subgroup; an explicit torsion order delegates to the additive
            # group wrapper used by the generic field implementation.
            "torsion_subgroup": (
                "def torsion_subgroup(self, n: Literal[None] = None, **kwds) -> 'sage.schemes.elliptic_curves.ell_torsion.EllipticCurveTorsionSubgroup': ...",
                "def torsion_subgroup(self, n, **kwds) -> 'sage.groups.additive_abelian.additive_abelian_wrapper.AdditiveAbelianGroupWrapper': ...",
            ),
        },
    },
    "sage/sandpiles/sandpile.pyi": {
        "Sandpile": {
            # ``v=None`` asks for the complete degree dictionary; a vertex
            # argument selects one native integer degree.
            "out_degree": (
                "def out_degree(self, v: Literal[None] = None) -> dict: ...",
                "def out_degree(self, v) -> int: ...",
            ),
            "in_degree": (
                "def in_degree(self, v: Literal[None] = None) -> dict: ...",
                "def in_degree(self, v) -> int: ...",
            ),
            # The verbose flag controls whether configurations are returned as
            # SandpileConfig objects or materialized integer lists.
            "identity": (
                "def identity(self, verbose: Literal[True] = True) -> 'sage.sandpiles.sandpile.SandpileConfig': ...",
                "def identity(self, verbose: Literal[False] = False) -> list[int]: ...",
            ),
            # ``gens=True`` returns the polynomial sequence; the default gives
            # the concrete multivariate ideal.
            "ideal": (
                "def ideal(self, gens: Literal[False] = False) -> 'sage.rings.polynomial.multi_polynomial_ideal.MPolynomialIdeal': ...",
                "def ideal(self, gens: Literal[True] = True) -> 'sage.rings.polynomial.multi_polynomial_sequence.PolynomialSequence_generic': ...",
            ),
        },
    },
    "sage/rings/number_field/number_field_element.pyi": {
        "NumberFieldElement": {
            # Absolute norm/trace descend to QQ; supplying a subfield asks
            # Sage for the relative NumberFieldElement result instead.
            "norm": (
                "def norm(self, K: Literal[None] = None) -> 'sage.rings.rational.Rational': ...",
                "def norm(self, K) -> Self: ...",
            ),
            "trace": (
                "def trace(self, K: Literal[None] = None) -> 'sage.rings.rational.Rational': ...",
                "def trace(self, K) -> Self: ...",
            ),
            # ``all`` materializes the second root; with the default branch
            # Sage returns one element from the same number field.
            "sqrt": (
                "def sqrt(self, all: Literal[False] = False, extend=True) -> Self: ...",
                "def sqrt(self, all: Literal[True] = True, extend=True) -> list[Self]: ...",
            ),
            "nth_root": (
                "def nth_root(self, n, all: Literal[False] = False) -> Self: ...",
                "def nth_root(self, n, all: Literal[True] = True) -> list[Self]: ...",
            ),
        },
    },
    "sage/rings/number_field/number_field.pyi": {
        "NumberField_generic": {
            # ``all`` selects one primitive root or the complete list.
            "zeta": (
                "def zeta(self, n=2, all: Literal[False] = False) -> 'sage.rings.number_field.number_field_element.NumberFieldElement': ...",
                "def zeta(self, n=2, all: Literal[True] = True) -> list['sage.rings.number_field.number_field_element.NumberFieldElement']: ...",
            ),
        },
    },
    "sage/graphs/generic_graph.pyi": {
        "GenericGraph": {
            # ``add_vertex`` returns a generated integer only for the
            # default ``name=None`` branch; naming an explicit vertex mutates
            # in place and returns ``None``.
            "add_vertex": (
                "def add_vertex(self, name: Literal[None] = None) -> int: ...",
                "def add_vertex(self, name) -> None: ...",
            ),
            # ``subgraph`` has an explicit in-place switch.  Preserve both
            # branches and expose a conservative union for a non-literal bool.
            "subgraph": (
                "def subgraph(self, vertices=None, edges=None, inplace: Literal[False] = False, vertex_property=None, edge_property=None, algorithm=None, immutable=None) -> Self: ...",
                "def subgraph(self, vertices=None, edges=None, inplace: Literal[True] = True, vertex_property=None, edge_property=None, algorithm=None, immutable=None) -> None: ...",
                "def subgraph(self, vertices=None, edges=None, inplace: bool = False, vertex_property=None, edge_property=None, algorithm=None, immutable=None) -> Self | None: ...",
            ),
        },
    },
    "sage/groups/perm_gps/permgroup.pyi": {
        "PermutationGroup_generic": {
            # ``direct_product`` returns only the product group when GAP
            # maps are suppressed; the default branch also returns four
            # embedding/projection morphisms in a five-tuple.
            "direct_product": (
                "def direct_product(self, other, maps: Literal[False] = False) -> 'sage.groups.perm_gps.permgroup.PermutationGroup_generic': ...",
                "def direct_product(self, other, maps: Literal[True] = True) -> tuple: ...",
                "def direct_product(self, other, maps: bool = True) -> 'sage.groups.perm_gps.permgroup.PermutationGroup_generic' | tuple: ...",
            ),
        },
    },
    "sage/rings/real_mpfr.pyi": {
        "RealNumber": {
            # Negative real inputs may extend to CC; the ``all`` switch then
            # materializes every root rather than returning one element.
            "sqrt": (
                "def sqrt(self, extend=True, all: Literal[False] = False) -> Self | 'sage.rings.complex_mpfr.ComplexNumber': ...",
                "def sqrt(self, extend=True, all: Literal[True] = True) -> list[Self | 'sage.rings.complex_mpfr.ComplexNumber']: ...",
            ),
        },
    },
    "sage/rings/complex_mpfr.pyi": {
        "ComplexNumber": {
            "sqrt": (
                "def sqrt(self, all: Literal[False] = False) -> Self: ...",
                "def sqrt(self, all: Literal[True] = True) -> list[Self]: ...",
            ),
            "nth_root": (
                "def nth_root(self, n, all: Literal[False] = False) -> Self: ...",
                "def nth_root(self, n, all: Literal[True] = True) -> list[Self]: ...",
            ),
        },
    },
    "sage/rings/complex_double.pyi": {
        "ComplexDoubleElement": {
            "sqrt": (
                "def sqrt(self, all: Literal[False] = False, **kwds) -> Self: ...",
                "def sqrt(self, all: Literal[True] = True, **kwds) -> list[Self]: ...",
            ),
            "nth_root": (
                "def nth_root(self, n, all: Literal[False] = False) -> Self: ...",
                "def nth_root(self, n, all: Literal[True] = True) -> list[Self]: ...",
            ),
        },
    },
    "sage/rings/finite_rings/element_base.pyi": {
        "FinitePolyExtElement": {
            # ``all`` selects the single-root versus all-roots contract for
            # finite-field elements; ``extend`` only changes the search
            # field and not the concrete element family.
            "sqrt": (
                "def sqrt(self, extend=False, all: Literal[False] = False) -> Self: ...",
                "def sqrt(self, extend=False, all: Literal[True] = True) -> list[Self]: ...",
            ),
            "square_root": (
                "def square_root(self, extend=False, all: Literal[False] = False) -> Self: ...",
                "def square_root(self, extend=False, all: Literal[True] = True) -> list[Self]: ...",
            ),
            "nth_root": (
                "def nth_root(self, n, extend=False, all: Literal[False] = False, algorithm=None, cunningham=False) -> Self: ...",
                "def nth_root(self, n, extend=False, all: Literal[True] = True, algorithm=None, cunningham=False) -> list[Self]: ...",
            ),
        },
        # Concrete residue backends override ``sqrt`` without repeating the
        # inherited annotation in the generated stubs.  Keep the same
        # explicit all-roots contract on each implementation class.
        "IntegerMod_gmp": {
            "sqrt": (
                "def sqrt(self, extend=True, all: Literal[False] = False) -> Self: ...",
                "def sqrt(self, extend=True, all: Literal[True] = True) -> list[Self]: ...",
            ),
        },
        "IntegerMod_int": {
            "sqrt": (
                "def sqrt(self, extend=True, all: Literal[False] = False) -> Self: ...",
                "def sqrt(self, extend=True, all: Literal[True] = True) -> list[Self]: ...",
            ),
        },
        "IntegerMod_int64": {
            "sqrt": (
                "def sqrt(self, extend=True, all: Literal[False] = False) -> Self: ...",
                "def sqrt(self, extend=True, all: Literal[True] = True) -> list[Self]: ...",
            ),
        },
    },
    "sage/rings/finite_rings/integer_mod.pyi": {
        "IntegerMod_abstract": {
            "sqrt": (
                "def sqrt(self, extend=True, all: Literal[False] = False) -> Self: ...",
                "def sqrt(self, extend=True, all: Literal[True] = True) -> list[Self]: ...",
            ),
            "nth_root": (
                "def nth_root(self, n, extend=False, all: Literal[False] = False, algorithm=None, cunningham=False) -> Self: ...",
                "def nth_root(self, n, extend=False, all: Literal[True] = True, algorithm=None, cunningham=False) -> list[Self]: ...",
            ),
        },
    },
    "sage/rings/finite_rings/element_pari_ffelt.pyi": {
        "FiniteFieldElement_pari_ffelt": {
            "sqrt": (
                "def sqrt(self, extend=False, all: Literal[False] = False) -> Self: ...",
                "def sqrt(self, extend=False, all: Literal[True] = True) -> list[Self]: ...",
            ),
            "nth_root": (
                "def nth_root(self, n, extend=False, all: Literal[False] = False, algorithm=None, cunningham=False) -> Self: ...",
                "def nth_root(self, n, extend=False, all: Literal[True] = True, algorithm=None, cunningham=False) -> list[Self]: ...",
            ),
        },
    },
    "sage/crypto/classical.pyi": {
        "HillCryptosystem": {
            # Inversion is performed in the key space and preserves the
            # caller's concrete matrix implementation (including modular
            # dense matrices used by the classical CTF examples).
            "inverse_key": (
                "def inverse_key(self, A: HillKeyT) -> HillKeyT: ...",
            ),
        },
    },
    "sage/crypto/lattice.pyi": {
        None: {
            # ``lattice`` and ``ntl`` are mutually exclusive output switches:
            # the default produces Sage's dense integer matrix, ``ntl=True``
            # produces an NTL matrix, and ``lattice=True`` produces the
            # free-module lattice wrapper.
            "gen_lattice": (
                "def gen_lattice(type='modular', n=4, m=8, q=11, seed=None, quotient=None, dual=False, *, ntl: Literal[False] = False, lattice: Literal[False] = False) -> 'sage.matrix.matrix_integer_dense.Matrix_integer_dense': ...",
                "def gen_lattice(type='modular', n=4, m=8, q=11, seed=None, quotient=None, dual=False, *, ntl: Literal[True] = True, lattice: Literal[False] = False) -> 'sage.libs.ntl.ntl_mat_ZZ.ntl_mat_ZZ': ...",
                "def gen_lattice(type='modular', n=4, m=8, q=11, seed=None, quotient=None, dual=False, *, ntl: Literal[False] = False, lattice: Literal[True] = True) -> 'sage.modules.free_module_integer.FreeModule_submodule_with_basis_integer_with_category': ...",
            ),
        },
    },
    "sage/matrix/constructor.pyi": {
        None: {
            "matrix": (
                "def matrix(base_ring: 'sage.rings.integer_ring.IntegerRing_class', *args, sparse: Literal[False] = False, **kwds) -> 'sage.matrix.matrix_integer_dense.Matrix_integer_dense': ...",
                "def matrix(base_ring: 'sage.rings.integer_ring.IntegerRing_class', *args, sparse: Literal[True] = True, **kwds) -> 'sage.matrix.matrix_integer_sparse.Matrix_integer_sparse': ...",
                "def matrix(base_ring: 'sage.rings.rational_field.RationalField', *args, sparse: Literal[False] = False, **kwds) -> 'sage.matrix.matrix_rational_dense.Matrix_rational_dense': ...",
                "def matrix(base_ring: 'sage.rings.rational_field.RationalField', *args, sparse: Literal[True] = True, **kwds) -> 'sage.matrix.matrix_rational_sparse.Matrix_rational_sparse': ...",
                "def matrix(base_ring: 'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn', *args, sparse: Literal[False] = False, **kwds) -> 'sage.matrix.matrix_modn_dense_float.Matrix_modn_dense_float': ...",
                "def matrix(base_ring: 'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn', *args, sparse: Literal[True] = True, **kwds) -> 'sage.matrix.matrix_modn_sparse.Matrix_modn_sparse': ...",
            ),
        },
    },
    "sage/arith/misc.pyi": {
        None: {
            # ``gcd`` coerces operands to a common parent and returns an
            # element of that parent.  This TypeVar preserves the concrete
            # operand class for calls such as ``gcd(f, f.derivative())``.
            "gcd": (
                "def gcd(a: GcdT, b: GcdT, **kwargs) -> GcdT: ...",
            ),
            # Binomial/falling/rising factorials preserve the parent of their
            # first operand (Integer, Rational, or symbolic Expression).  A
            # TypeVar models that documented relationship without guessing a
            # single global Sage class.
            "binomial": (
                "def binomial(x: BinomialT, m, **kwds) -> BinomialT: ...",
            ),
            "falling_factorial": (
                "def falling_factorial(x: FallingFactorialT, a) -> FallingFactorialT: ...",
            ),
            "rising_factorial": (
                "def rising_factorial(x: RisingFactorialT, a) -> RisingFactorialT: ...",
            ),
            "continuant": (
                "def continuant(v: list[ContinuantT], n=None) -> ContinuantT: ...",
                "def continuant(v: tuple[ContinuantT, ...], n=None) -> ContinuantT: ...",
            ),
            "gauss_sum": (
                "def gauss_sum(char_value: GaussSumT, finite_field) -> GaussSumT: ...",
            ),
            "radical": (
                "def radical(n: RadicalT, *args, **kwds) -> RadicalT: ...",
            ),
            "coprime_part": (
                "def coprime_part(x: CoprimePartT, base) -> CoprimePartT: ...",
            ),
            # The optional ``get_data`` flag is a genuine call-argument
            # contract: the default/False branch is a predicate, while the
            # literal True branch returns the factor/exponent pair.
            "is_prime_power": (
                "def is_prime_power(n, get_data: Literal[False] = False) -> bool: ...",
                "def is_prime_power(n, get_data: Literal[True]) -> tuple: ...",
            ),
            "is_pseudoprime_power": (
                "def is_pseudoprime_power(n, get_data: Literal[False] = False) -> bool: ...",
                "def is_pseudoprime_power(n, get_data: Literal[True]) -> tuple: ...",
            ),
        },
    },
    "sage/arith/functions.pyi": {
        None: {
            # lcm first coerces scalar operands into a common parent; the
            # list/tuple form returns an element of that same parent.
            "lcm": (
                "def lcm(a: LcmT, b: LcmT) -> LcmT: ...",
                "def lcm(a: list[LcmT], b=None) -> LcmT: ...",
            ),
        },
    },
    "sage/combinat/designs/difference_family.pyi": {
        None: {
            # Difference-family builders document stable outer containers;
            # parent element types inside those containers remain dynamic.
            "_construct_gs_difference_family_from_full": (
                "def _construct_gs_difference_family_from_full(S1, S2, mu) -> list: ...",
            ),
            "_construct_gs_difference_family_from_compact": (
                "def _construct_gs_difference_family_from_compact(rep1, rep2, H, mu) -> list: ...",
            ),
            "_construction_supplementary_difference_set": (
                "def _construction_supplementary_difference_set(n, H, indices, cosets_gen, check=True) -> tuple: ...",
            ),
            "_create_m_sequence": (
                "def _create_m_sequence(q, n, check=True) -> list: ...",
            ),
            "_is_skew_set": (
                "def _is_skew_set(G, S) -> bool: ...",
            ),
            "are_mcfarland_1973_parameters": (
                "def are_mcfarland_1973_parameters(v, k, lmbda, return_parameters: Literal[False] = False) -> bool: ...",
                "def are_mcfarland_1973_parameters(v, k, lmbda, return_parameters: Literal[True]) -> tuple[bool, tuple[int, int] | None]: ...",
                "def are_mcfarland_1973_parameters(v, k, lmbda, return_parameters: bool = False) -> bool | tuple[bool, tuple[int, int] | None]: ...",
            ),
            "complementary_difference_setsI": (
                "def complementary_difference_setsI(n, check=True) -> tuple: ...",
            ),
            "complementary_difference_setsII": (
                "def complementary_difference_setsII(n, check=True) -> tuple: ...",
            ),
            "complementary_difference_setsIII": (
                "def complementary_difference_setsIII(n, check=True) -> tuple: ...",
            ),
            "complementary_difference_sets": (
                "def complementary_difference_sets(n, existence: Literal[False] = False, check=True) -> tuple: ...",
                "def complementary_difference_sets(n, existence: Literal[True], check=True) -> bool: ...",
                "def complementary_difference_sets(n, existence: bool = False, check=True) -> tuple | bool: ...",
            ),
            "df_q_6_1": (
                "def df_q_6_1(K, existence: Literal[False] = False, check=True) -> list: ...",
                "def df_q_6_1(K, existence: Literal[True], check=True) -> bool: ...",
                "def df_q_6_1(K, existence: bool = False, check=True) -> list | bool: ...",
            ),
            "difference_family": (
                "def difference_family(v, k, l=1, existence: Literal[False] = False, explain_construction: Literal[False] = False, check=True) -> tuple: ...",
                "def difference_family(v, k, l=1, existence: Literal[True] = True, explain_construction: Literal[False] = False, check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def difference_family(v, k, l=1, existence: Literal[False] = False, explain_construction: Literal[True] = True, check=True) -> str: ...",
                "def difference_family(v, k, l=1, existence: bool = False, explain_construction: bool = False, check=True) -> tuple | bool | str | 'sage.misc.unknown.Unknown': ...",
            ),
            "get_fixed_relative_difference_set": (
                "def get_fixed_relative_difference_set(G, rel_diff_set, as_elements=False) -> list: ...",
            ),
            "hadamard_difference_set_product_parameters": (
                "def hadamard_difference_set_product_parameters(N) -> tuple[int, int] | None: ...",
            ),
            "hadamard_difference_set_product": (
                "def hadamard_difference_set_product(G1, D1, G2, D2) -> tuple: ...",
            ),
            "is_fixed_relative_difference_set": (
                "def is_fixed_relative_difference_set(R, q) -> bool: ...",
            ),
            "is_relative_difference_set": (
                "def is_relative_difference_set(R, G, H, params, verbose=False) -> bool: ...",
            ),
            "is_supplementary_difference_set": (
                "def is_supplementary_difference_set(Ks, v=None, lmbda=None, G=None, verbose=False) -> bool: ...",
            ),
            "mcfarland_1973_construction": (
                "def mcfarland_1973_construction(q, s) -> tuple: ...",
            ),
            "one_cyclic_tiling": (
                "def one_cyclic_tiling(A, n) -> list: ...",
            ),
            "one_radical_difference_family": (
                "def one_radical_difference_family(K, k) -> list | None: ...",
            ),
            "radical_difference_family": (
                "def radical_difference_family(K, k, l=1, existence: Literal[False] = False, check=True) -> list: ...",
                "def radical_difference_family(K, k, l=1, existence: Literal[True] = True, check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def radical_difference_family(K, k, l=1, existence: bool = False, check=True) -> list | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "radical_difference_set": (
                "def radical_difference_set(K, k, l=1, existence: Literal[False] = False, check=True) -> list: ...",
                "def radical_difference_set(K, k, l=1, existence: Literal[True] = True, check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def radical_difference_set(K, k, l=1, existence: bool = False, check=True) -> list | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "relative_difference_set_from_homomorphism": (
                "def relative_difference_set_from_homomorphism(q, N, d, check=True, return_group: Literal[False] = False) -> list: ...",
                "def relative_difference_set_from_homomorphism(q, N, d, check=True, return_group: Literal[True] = True) -> tuple: ...",
                "def relative_difference_set_from_homomorphism(q, N, d, check=True, return_group: bool = False) -> list | tuple: ...",
            ),
            "relative_difference_set_from_m_sequence": (
                "def relative_difference_set_from_m_sequence(q, N, check=True, return_group: Literal[False] = False) -> list: ...",
                "def relative_difference_set_from_m_sequence(q, N, check=True, return_group: Literal[True] = True) -> tuple: ...",
                "def relative_difference_set_from_m_sequence(q, N, check=True, return_group: bool = False) -> list | tuple: ...",
            ),
            "skew_spin_goethals_seidel_difference_family": (
                "def skew_spin_goethals_seidel_difference_family(n, existence: Literal[False] = False, check=True) -> tuple: ...",
                "def skew_spin_goethals_seidel_difference_family(n, existence: Literal[True], check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def skew_spin_goethals_seidel_difference_family(n, existence: bool = False, check=True) -> tuple | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "skew_supplementary_difference_set": (
                "def skew_supplementary_difference_set(n, existence: Literal[False] = False, check=True, return_group: Literal[False] = False) -> list: ...",
                "def skew_supplementary_difference_set(n, existence: Literal[False] = False, check=True, return_group: Literal[True] = True) -> tuple: ...",
                "def skew_supplementary_difference_set(n, existence: Literal[True], check=True, return_group=False) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def skew_supplementary_difference_set(n, existence: bool = False, check=True, return_group: bool = False) -> list | tuple | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "skew_supplementary_difference_set_over_polynomial_ring": (
                "def skew_supplementary_difference_set_over_polynomial_ring(n, existence: Literal[False] = False, check=True) -> tuple: ...",
                "def skew_supplementary_difference_set_over_polynomial_ring(n, existence: Literal[True], check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def skew_supplementary_difference_set_over_polynomial_ring(n, existence: bool = False, check=True) -> tuple | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "skew_supplementary_difference_set_with_paley_todd": (
                "def skew_supplementary_difference_set_with_paley_todd(n, existence: Literal[False] = False, check=True) -> tuple: ...",
                "def skew_supplementary_difference_set_with_paley_todd(n, existence: Literal[True], check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def skew_supplementary_difference_set_with_paley_todd(n, existence: bool = False, check=True) -> tuple | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "spin_goethals_seidel_difference_family": (
                "def spin_goethals_seidel_difference_family(n, existence: Literal[False] = False, check=True) -> tuple: ...",
                "def spin_goethals_seidel_difference_family(n, existence: Literal[True], check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def spin_goethals_seidel_difference_family(n, existence: bool = False, check=True) -> tuple | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "supplementary_difference_set_from_rel_diff_set": (
                "def supplementary_difference_set_from_rel_diff_set(q, existence: Literal[False] = False, check=True) -> tuple: ...",
                "def supplementary_difference_set_from_rel_diff_set(q, existence: Literal[True], check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def supplementary_difference_set_from_rel_diff_set(q, existence: bool = False, check=True) -> tuple | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "supplementary_difference_set_hadamard": (
                "def supplementary_difference_set_hadamard(n, existence: Literal[False] = False, check=True) -> tuple: ...",
                "def supplementary_difference_set_hadamard(n, existence: Literal[True], check=True) -> bool | 'sage.misc.unknown.Unknown': ...",
                "def supplementary_difference_set_hadamard(n, existence: bool = False, check=True) -> tuple | bool | 'sage.misc.unknown.Unknown': ...",
            ),
            "turyn_1965_3x3xK": (
                "def turyn_1965_3x3xK(k=4) -> tuple: ...",
            ),
            "twin_prime_powers_difference_set": (
                "def twin_prime_powers_difference_set(p, check=True) -> tuple: ...",
            ),
        },
    },
    "sage/combinat/skew_tableau.pyi": {
        "SkewTableau": {
            # ``slide(return_vacated=True)`` is the one argument-dependent
            # branch: Sage returns the transformed skew tableau together with
            # the vacated coordinates.  Keep both literal branches visible.
            "slide": (
                "def slide(self, corner=None, return_vacated: Literal[False] = False) -> Self: ...",
                "def slide(self, corner=None, return_vacated: Literal[True] = True) -> tuple[Self, tuple[int, int]]: ...",
                "def slide(self, corner=None, return_vacated: bool = False) -> Self | tuple[Self, tuple[int, int]]: ...",
            ),
        },
    },
    "sage/crypto/boolean_function.pyi": {
        "BooleanFunction": {
            # ``truth_table`` has a real format-dependent contract: the
            # default/bin/int branches are tuples, while hex is a string.
            "truth_table": (
                "def truth_table(self, format: Literal['hex']) -> str: ...",
                "def truth_table(self, format: Literal['bin', 'int'] = 'bin') -> tuple: ...",
            ),
        },
    },
    "sage/crypto/sbox.pyi": {
        "SBox": {
            # The S-box documentation specifies distinct integer, list and
            # GF(2)-vector input branches.  Keep the finite-field branch
            # unresolved because its element implementation depends on the
            # caller's field parent.
            "__call__": (
                "def __call__(self, X: int) -> 'sage.rings.integer.Integer': ...",
                "def __call__(self, X: list) -> list: ...",
                "def __call__(self, X: tuple) -> list: ...",
                "def __call__(self, X: 'sage.modules.vector_mod2_dense.Vector_mod2_dense') -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense': ...",
            ),
            "__getitem__": (
                "def __getitem__(self, X: int) -> 'sage.rings.integer.Integer': ...",
            ),
        },
    },
    "sage/crypto/mq/rijndael_gf.pyi": {
        "RijndaelGF": {
            # The conversion helpers have a documented matrix/list flag.  A
            # literal overload retains the concrete Matrix_gf2e_dense result
            # for the default path without lying about matrix=False.
            "_hex_to_GF": (
                "def _hex_to_GF(self, H, matrix: Literal[False]) -> list: ...",
                "def _hex_to_GF(self, H, matrix: Literal[True] = True) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense': ...",
            ),
            "_bin_to_GF": (
                "def _bin_to_GF(self, B, matrix: Literal[False]) -> list: ...",
                "def _bin_to_GF(self, B, matrix: Literal[True] = True) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense': ...",
            ),
            # Matrix round components preserve the concrete matrix parent
            # supplied by the caller, including polynomial-state matrices.
            "apply_poly": (
                "def apply_poly(self, state: RijndaelStateT, poly_constr, algorithm='encrypt', keys=None, poly_constr_attr=None) -> RijndaelStateT: ...",
            ),
            "add_round_key": (
                "def add_round_key(self, state: RijndaelStateT, round_key: RijndaelStateT) -> RijndaelStateT: ...",
            ),
            "sub_bytes": (
                "def sub_bytes(self, state: RijndaelStateT, algorithm='encrypt') -> RijndaelStateT: ...",
            ),
            "mix_columns": (
                "def mix_columns(self, state: RijndaelStateT, algorithm='encrypt') -> RijndaelStateT: ...",
            ),
            "shift_rows": (
                "def shift_rows(self, state: RijndaelStateT, algorithm='encrypt') -> RijndaelStateT: ...",
            ),
            # compose returns a constructor for constructor inputs, and a
            # polynomial when the second input is already a polynomial.
            "compose": (
                "def compose(self, f: 'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr', g: 'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr', algorithm='encrypt', f_attr=None, g_attr=None) -> 'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr': ...",
                "def compose(self, f: 'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr', g: 'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular', algorithm='encrypt', f_attr=None, g_attr=None) -> 'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular': ...",
            ),
        },
    },
    "sage/crypto/mq/sr.pyi": {
        None: {
            # The factory selects the concrete generator from the literal
            # ``gf2`` flag; preserve that branch instead of exposing the
            # abstract SR_generic base as the final result.
            "SR": (
                "def SR(n=1, r=1, c=1, e=4, star=False, *, gf2: Literal[False] = False, **kwargs) -> 'sage.crypto.mq.sr.SR_gf2n': ...",
                "def SR(n=1, r=1, c=1, e=4, star=False, *, gf2: Literal[True], **kwargs) -> 'sage.crypto.mq.sr.SR_gf2': ...",
            ),
        },
        "SR_gf2n": {
            "phi": (
                "def phi(self, l: list) -> list: ...",
                "def phi(self, l: 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense') -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense': ...",
            ),
            "antiphi": (
                "def antiphi(self, l: list) -> list: ...",
                "def antiphi(self, l: 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense') -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense': ...",
            ),
        },
        "SR_gf2": {
            "phi": (
                "def phi(self, l: list) -> list: ...",
                "def phi(self, l: 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense') -> 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense': ...",
            ),
            "antiphi": (
                "def antiphi(self, l: list) -> list: ...",
                "def antiphi(self, l: 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense') -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense': ...",
            ),
        },
    },
    "sage/schemes/elliptic_curves/ell_finite_field.pyi": {
        "EllipticCurve_finite_field": {
            # ``map`` controls whether the division field is returned alone
            # or together with the base-field embedding.  The field and map
            # implementations vary with the finite-field backend, so the
            # overload retains the complete concrete backend unions.
            "division_field": (
                f"def division_field(self, n, names='t', map: Literal[False] = False, **kwds) -> {FINITE_FIELD_UNION}: ...",
                f"def division_field(self, n, names='t', map: Literal[True] = True, **kwds) -> tuple[{FINITE_FIELD_UNION}, {FINITE_FIELD_MORPHISM_UNION}]: ...",
            ),
        },
        None: {
            "special_supersingular_curve": (
                "def special_supersingular_curve(F, q=None, *, endomorphism: Literal[False] = False) -> 'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field': ...",
                "def special_supersingular_curve(F, q=None, *, endomorphism: Literal[True] = True) -> tuple['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field', 'sage.schemes.elliptic_curves.ell_curve_isogeny.EllipticCurveIsogeny']: ...",
            ),
        },
    },
    "sage/schemes/elliptic_curves/ell_rational_field.pyi": {
        "EllipticCurve_rational_field": {
            "analytic_rank": (
                "def analytic_rank(self, algorithm='pari', leading_coefficient: Literal[False] = False) -> 'sage.rings.integer.Integer': ...",
                "def analytic_rank(self, algorithm='pari', leading_coefficient: Literal[True] = True) -> tuple['sage.rings.integer.Integer', 'sage.rings.real_mpfr.RealNumber']: ...",
            ),
            "aplist": (
                "def aplist(self, n, python_ints: Literal[False] = False) -> list['sage.rings.integer.Integer']: ...",
                "def aplist(self, n, python_ints: Literal[True] = True) -> list[int]: ...",
            ),
            "anlist": (
                "def anlist(self, n, python_ints: Literal[False] = False) -> list['sage.rings.integer.Integer']: ...",
                "def anlist(self, n, python_ints: Literal[True] = True) -> list[int]: ...",
            ),
            "selmer_rank": (
                "def selmer_rank(self, algorithm: Literal['pari'] = 'pari') -> 'cypari2.gen.Gen': ...",
                "def selmer_rank(self, algorithm: Literal['mwrank']) -> 'sage.rings.integer.Integer': ...",
            ),
            "rank_bound": (
                "def rank_bound(self, algorithm: Literal['pari'] = 'pari') -> 'cypari2.gen.Gen': ...",
                "def rank_bound(self, algorithm: Literal['mwrank']) -> 'sage.rings.integer.Integer': ...",
            ),
            "modular_symbol": (
                "def modular_symbol(self, sign=+1, normalize=None, implementation: Literal['eclib'] = 'eclib', nap=0) -> 'sage.schemes.elliptic_curves.ell_modular_symbols.ModularSymbolECLIB': ...",
                "def modular_symbol(self, sign=+1, normalize=None, implementation: Literal['sage'] = 'sage', nap=0) -> 'sage.schemes.elliptic_curves.ell_modular_symbols.ModularSymbolSage': ...",
                "def modular_symbol(self, sign=+1, normalize=None, implementation: Literal['num'] = 'num', nap=0) -> 'sage.schemes.elliptic_curves.mod_sym_num.ModularSymbolNumerical': ...",
            ),
        },
    },
    "sage/crypto/block_cipher/miniaes.pyi": {
        "MiniAES": {
            # Mini-AES matrix transforms preserve the concrete matrix parent
            # supplied by the caller.  Bind that argument to the result so
            # PyCharm sees the actual MatrixSpace implementation instead of a
            # public Matrix base class.
            "add_key": (
                "def add_key(self, block: MiniAEST, rkey: MiniAEST) -> MiniAEST: ...",
            ),
            "decrypt": (
                "def decrypt(self, C: MiniAEST, key: MiniAEST) -> MiniAEST: ...",
            ),
            "encrypt": (
                "def encrypt(self, P: MiniAEST, key: MiniAEST) -> MiniAEST: ...",
            ),
            "mix_column": (
                "def mix_column(self, block: MiniAEST) -> MiniAEST: ...",
            ),
            "nibble_sub": (
                "def nibble_sub(self, block: MiniAEST, algorithm='encrypt') -> MiniAEST: ...",
            ),
            "round_key": (
                "def round_key(self, key: MiniAEST, n) -> MiniAEST: ...",
            ),
            "shift_row": (
                "def shift_row(self, block: MiniAEST) -> MiniAEST: ...",
            ),
        },
    },
    "sage/all.pyi": {
        None: {
            # An elliptic curve over a finite field has a materially more
            # precise runtime class than a generic curve.  Keep the original
            # implementation annotation as the fallback for all other rings.
            "EllipticCurve": (
                "def EllipticCurve(R: _FactoryReturn_GF, coefficients, *args, **kwargs) -> 'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field': ...",
            ),
            "PolynomialRing": (
                "def PolynomialRing(base_ring: 'sage.rings.finite_rings.finite_field_base.FiniteField', *args, **kwds) -> 'sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p': ...",
            ),
            # ``GF``/``FiniteField`` are factories whose implementation is
            # selected by the literal ``implementation`` keyword.  The
            # fallback is the complete concrete backend union, never the
            # public FiniteField base, so ``F.gen()`` and ``F.random_element``
            # retain backend-aware completion in CTF scripts.
            "GF": (
                "def GF(*args, implementation: Literal['givaro'] = 'givaro', **kwargs) -> 'sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro': ...",
                "def GF(*args, implementation: Literal['ntl'], **kwargs) -> 'sage.rings.finite_rings.finite_field_ntl_gf2e.FiniteField_ntl_gf2e': ...",
                "def GF(*args, implementation: Literal['pari', 'pari_ffelt'], **kwargs) -> 'sage.rings.finite_rings.finite_field_pari_ffelt.FiniteField_pari_ffelt': ...",
                f"def GF(*args, **kwargs) -> {FINITE_FIELD_UNION}: ...",
            ),
            "FiniteField": (
                "def FiniteField(*args, implementation: Literal['givaro'] = 'givaro', **kwargs) -> 'sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro': ...",
                "def FiniteField(*args, implementation: Literal['ntl'], **kwargs) -> 'sage.rings.finite_rings.finite_field_ntl_gf2e.FiniteField_ntl_gf2e': ...",
                "def FiniteField(*args, implementation: Literal['pari', 'pari_ffelt'], **kwargs) -> 'sage.rings.finite_rings.finite_field_pari_ffelt.FiniteField_pari_ffelt': ...",
                f"def FiniteField(*args, **kwargs) -> {FINITE_FIELD_UNION}: ...",
            ),
            "Matrix": (
                "def Matrix(base_ring: 'sage.rings.integer_ring.IntegerRing_class', *args, sparse: Literal[False] = False, **kwds) -> 'sage.matrix.matrix_integer_dense.Matrix_integer_dense': ...",
                "def Matrix(base_ring: 'sage.rings.integer_ring.IntegerRing_class', *args, sparse: Literal[True] = True, **kwds) -> 'sage.matrix.matrix_integer_sparse.Matrix_integer_sparse': ...",
                "def Matrix(base_ring: 'sage.rings.rational_field.RationalField', *args, sparse: Literal[False] = False, **kwds) -> 'sage.matrix.matrix_rational_dense.Matrix_rational_dense': ...",
                "def Matrix(base_ring: 'sage.rings.rational_field.RationalField', *args, sparse: Literal[True] = True, **kwds) -> 'sage.matrix.matrix_rational_sparse.Matrix_rational_sparse': ...",
                "def Matrix(base_ring: 'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn', *args, sparse: Literal[False] = False, **kwds) -> 'sage.matrix.matrix_modn_dense_float.Matrix_modn_dense_float': ...",
                "def Matrix(base_ring: 'sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn', *args, sparse: Literal[True] = True, **kwds) -> 'sage.matrix.matrix_modn_sparse.Matrix_modn_sparse': ...",
            ),
        },
    },
    "sage/matrix/matrix2.pyi": {
        "Matrix": {
            # Sage 10.9 documents that solve_left/solve_right preserve the
            # right-hand-side family: Vector -> Vector, Matrix -> Matrix.
            "solve_left": (
                "def solve_left(self, B: FreeModuleElement, check: bool = True, *, extend: bool = True) -> FreeModuleElement: ...",
                "def solve_left(self, B: Matrix, check: bool = True, *, extend: bool = True) -> Matrix: ...",
            ),
            "solve_right": (
                "def solve_right(self, B: FreeModuleElement, check: bool = True, *, extend: bool = True) -> FreeModuleElement: ...",
                "def solve_right(self, B: Matrix, check: bool = True, *, extend: bool = True) -> Matrix: ...",
            ),
            # dual=False returns one Sequence; dual=True returns the paired
            # primal/dual decomposition.  The literal flag makes this
            # conditional source contract selectable at the call site.
            "decomposition": (
                "def decomposition(self, algorithm='spin', is_diagonalizable=False, dual: Literal[False] = False) -> 'sage.structure.sequence.Sequence_generic': ...",
                "def decomposition(self, algorithm='spin', is_diagonalizable=False, dual: Literal[True] = True) -> tuple['sage.structure.sequence.Sequence_generic', 'sage.structure.sequence.Sequence_generic']: ...",
            ),
            # The translated matrix2 docs make the output flag explicit.  The
            # false branch is the concrete basis matrix; the true branch
            # carries the row-profile tuples alongside it.
            "krylov_basis": (
                "def krylov_basis(self, M, shifts=None, degrees=None, output_rows: Literal[False] = False, algorithm=None) -> Self: ...",
                "def krylov_basis(self, M, shifts=None, degrees=None, output_rows: Literal[True] = True, algorithm=None) -> tuple[Self, tuple[tuple[int, int, int], ...]]: ...",
            ),
            "krylov_kernel_basis": (
                "def krylov_kernel_basis(self, M, shifts=None, degrees=None, output_rows: Literal[False] = False, var=None, basis_algorithm=None) -> Self: ...",
                "def krylov_kernel_basis(self, M, shifts=None, degrees=None, output_rows: Literal[True] = True, var=None, basis_algorithm=None) -> tuple[Self, tuple[tuple[int, int, int], ...]]: ...",
            ),
            "cyclic_subspace": (
                "def cyclic_subspace(self, v, var: Literal[None] = None, basis='echelon') -> 'sage.modules.free_module.FreeModule_submodule_field_with_category': ...",
                "def cyclic_subspace(self, v, var: str, basis='echelon') -> tuple['sage.rings.polynomial.polynomial_element.Polynomial', 'sage.modules.free_module.FreeModule_submodule_field_with_category']: ...",
            ),
            "find": (
                "def find(self, f, indices: Literal[False] = False) -> 'sage.matrix.matrix_modn_dense_float.Matrix_modn_dense_float': ...",
                "def find(self, f, indices: Literal[True] = True) -> dict: ...",
            ),
        },
    },
    "sage/matrix/matrix_integer_dense.pyi": {
        "Matrix_integer_dense": {
            # ``transformation`` controls whether Smith normal form returns
            # only the diagonal matrix or the (D, U, V) transformation tuple.
            "smith_form": (
                "def smith_form(self, transformation: Literal[False] = False, integral=None) -> Self: ...",
                "def smith_form(self, transformation: Literal[True] = True, integral=None) -> tuple[Self, Self, Self]: ...",
            ),
        },
    },
    "sage/matrix/matrix_rational_dense.pyi": {
        "Matrix_rational_dense": {
            "smith_form": (
                "def smith_form(self, transformation: Literal[False] = False, integral=None) -> Self: ...",
                "def smith_form(self, transformation: Literal[True] = True, integral=None) -> tuple[Self, Self, Self]: ...",
            ),
        },
    },
    "sage/matrix/matrix_modn_sparse.pyi": {
        "Matrix_modn_sparse": {
            "density": (
                "def density(self, approx: Literal[False] = False) -> 'sage.rings.rational.Rational': ...",
                "def density(self, approx: Literal[True]) -> float: ...",
            ),
        },
    },
    "sage/matrix/matrix_mod2_dense.pyi": {
        "Matrix_mod2_dense": {
            "density": (
                "def density(self, approx: Literal[False] = False) -> 'sage.rings.rational.Rational': ...",
                "def density(self, approx: Literal[True]) -> float: ...",
            ),
        },
    },
    "sage/matrix/matrix_gf2e_dense.pyi": {
        "Matrix_gf2e_dense": {
            "density": (
                "def density(self, approx: Literal[False] = False) -> 'sage.rings.rational.Rational': ...",
                "def density(self, approx: Literal[True]) -> float: ...",
            ),
        },
    },
    "sage/matrix/matrix0.pyi": {
        "Matrix": {
            # Matrix slicing always constructs a matrix; scalar (int, int)
            # indexing remains parent-dependent.  These overloads preserve
            # the concrete receiver for A[:, :], A[0, :], and related forms.
            "__getitem__": (
                "def __getitem__(self, key: slice) -> Self: ...",
                "def __getitem__(self, key: tuple[slice, slice]) -> Self: ...",
                "def __getitem__(self, key: tuple[int, slice]) -> Self: ...",
                "def __getitem__(self, key: tuple[slice, int]) -> Self: ...",
            ),
            "commutator": (
                "def commutator(self, other: Self) -> Self: ...",
            ),
            "anticommutator": (
                "def anticommutator(self, other: Self) -> Self: ...",
            ),
            "is_symmetrizable": (
                "def is_symmetrizable(self, return_diag: Literal[False] = False, positive: bool = True) -> bool: ...",
                "def is_symmetrizable(self, return_diag: Literal[True], positive: bool = True) -> list | Literal[False]: ...",
            ),
            "is_skew_symmetrizable": (
                "def is_skew_symmetrizable(self, return_diag: Literal[False] = False, positive: bool = True) -> bool: ...",
                "def is_skew_symmetrizable(self, return_diag: Literal[True], positive: bool = True) -> list | Literal[False]: ...",
            ),
        },
    },
    "sage/matrix/matrix_polynomial_dense.pyi": {
        "Matrix_polynomial_dense": {
            "solve_left_series_trunc": (
                "def solve_left_series_trunc(self, B: 'sage.modules.free_module_element.FreeModuleElement', d) -> 'sage.modules.free_module_element.FreeModuleElement': ...",
                "def solve_left_series_trunc(self, B: 'sage.matrix.matrix2.Matrix', d) -> Self: ...",
            ),
            "solve_right_series_trunc": (
                "def solve_right_series_trunc(self, B: 'sage.modules.free_module_element.FreeModuleElement', d) -> 'sage.modules.free_module_element.FreeModuleElement': ...",
                "def solve_right_series_trunc(self, B: 'sage.matrix.matrix2.Matrix', d) -> Self: ...",
            ),
            "hermite_form": (
                "def hermite_form(self, include_zero_rows: bool = True, transformation: Literal[False] = False) -> Self: ...",
                "def hermite_form(self, include_zero_rows: bool = True, transformation: Literal[True] = True) -> tuple[Self, Self]: ...",
            ),
            "popov_form": (
                "def popov_form(self, transformation: Literal[False] = False, shifts=None, row_wise: bool = True, include_zero_vectors: bool = True) -> Self: ...",
                "def popov_form(self, transformation: Literal[True], shifts=None, row_wise: bool = True, include_zero_vectors: bool = True) -> tuple[Self, Self]: ...",
            ),
            "weak_popov_form": (
                "def weak_popov_form(self, transformation: Literal[False] = False, shifts=None, row_wise: bool = True, ordered: bool = False, include_zero_vectors: bool = True) -> Self: ...",
                "def weak_popov_form(self, transformation: Literal[True], shifts=None, row_wise: bool = True, ordered: bool = False, include_zero_vectors: bool = True) -> tuple[Self, Self]: ...",
            ),
            "reduced_form": (
                "def reduced_form(self, transformation: Literal[False] | None = None, shifts=None, row_wise: bool = True, include_zero_vectors: bool = True) -> Self: ...",
                "def reduced_form(self, transformation: Literal[True], shifts=None, row_wise: bool = True, include_zero_vectors: bool = True) -> tuple[Self, Self]: ...",
            ),
        },
    },
    "sage/rings/polynomial/polynomial_element.pyi": {
        "Polynomial": {
            # Polynomial indexing is conditional: an integer selects a
            # coefficient from the (dynamic) base ring, while a slice creates
            # another polynomial in the same parent.  Keep the scalar branch
            # unresolved and expose the precise slice branch to PyCharm.
            "__getitem__": (
                "def __getitem__(self, key: slice) -> Self: ...",
            ),
        },
    },
    "sage/rings/polynomial/multi_polynomial.pyi": {
        "MPolynomial": {
            "is_square": (
                "def is_square(self, root: Literal[False] = False) -> bool: ...",
                "def is_square(self, root: Literal[True]) -> tuple[bool, Self | None]: ...",
            ),
        },
    },
    "sage/rings/polynomial/laurent_polynomial_mpair.pyi": {
        "LaurentPolynomial_mpair": {
            "is_square": (
                "def is_square(self, root: Literal[False] = False) -> bool: ...",
                "def is_square(self, root: Literal[True]) -> tuple[bool, Self | None]: ...",
            ),
        },
    },
}

# Dynamic CAS interfaces still have stable outer contracts for their control
# plane.  Keep these grouped by protocol instead of scattering ad-hoc method
# exceptions through the doc parser: values crossing the interpreter boundary
# are strings/flags/handles, while element-producing operations are resolved by
# the structural backend-element rule above.
CURATED_ANNOTATIONS["sage/interfaces/interface.pyi"] = {
    "Interface": {
        "name": "str | None",
        "get_seed": "int | None",
        "rand_seed": "int",
        "set_seed": "int",
        "interact": "None",
        "_pre_interact": "None",
        "_post_interact": "None",
        "read": "None",
        "_read_in_file_command": "str",
        "eval": "str",
        "_relation_symbols": "dict",
        "set": "None",
        "get": "str",
        "get_using_file": "str",
        "clear": "None",
        "_next_var_name": "str",
        "_convert_args_kwds": "tuple",
        "_check_valid_function_name": "None",
        "_function_call_string": "str",
        "_contains": "bool",
        "console": "None",
        "help": "str",
    },
    "InterfaceElement": {
        "__iter__": "Iterator",
        "get_using_file": "str",
        "bool": "bool",
        "_integer_": "'sage.rings.integer.Integer'",
        "_rational_": "'sage.rings.rational.Rational'",
        "name": "str | None",
    },
}

CURATED_ANNOTATIONS["sage/interfaces/expect.pyi"] = {
    "Expect": {
        "set_server_and_command": "None",
        "server": "str | None",
        "command": "str",
        "_get": "str",
        "is_remote": "bool",
        "is_local": "bool",
        "user_dir": "str",
        "_change_prompt": "None",
        "path": "str",
        "expect": "int",
        "pid": "int",
        "_do_cleaner": "None",
        "_start": "None",
        "_close": "None",
        "clear_prompts": "None",
        "_reset_expect": "None",
        "quit": "None",
        "detach": "None",
        "_send_interrupt": "None",
        "_local_tmpfile": "str",
        "_remote_tmpdir": "str | None",
        "_remote_tmpfile": "str | None",
        "_send_tmpfile_to_server": "None",
        "_get_tmpfile_from_server": "None",
        "_remove_tmpfile_from_server": "None",
        "_eval_line_using_file": "str",
        "_post_process_from_file": "str",
        "_eval_line": "str",
        "_keyboard_interrupt": "None",
        "interrupt": "bool",
        "_before": "str",
        "_interrupt": "None",
        "_sendstr": "None",
        "_crash_msg": "None",
        "_synchronize": "None",
        "eval": "str",
    },
}

CURATED_ANNOTATIONS["sage/interfaces/magma.pyi"] = {
    "Magma": {
        "set_seed": "int",
        "_assign_symbol": "str",
        "_equality_symbol": "str",
        "_greaterthan_symbol": "str",
        "_left_list_delim": "str",
        "_lessthan_symbol": "str",
        "_right_list_delim": "str",
        "_true_symbol": "str",
        "_false_symbol": "str",
        "set": "None",
        "clear": "None",
        "chdir": "None",
        "attach": "None",
        "attach_spec": "None",
        "load": "str",
        "ideal": "'sage.interfaces.magma.MagmaElement'",
        "set_verbose": "None",
        "get_verbose": "int",
        "set_nthreads": "None",
        "get_nthreads": "int",
        "console": "None",
        "version": "tuple",
    },
}

CURATED_ANNOTATIONS["sage/interfaces/singular.pyi"] = {
    "Singular": {
        "set_seed": "int",
        "_equality_symbol": "str",
        "_true_symbol": "str",
        "_false_symbol": "str",
        "_quit_string": "str",
        "_send_interrupt": "None",
        "_read_in_file_command": "str",
        "set": "None",
        "get": "str",
        "clear": "None",
        "_create": "str",
        "cputime": "float",
        "lib": "None",
        "ideal": "'sage.interfaces.singular.SingularElement'",
        "list": "'sage.interfaces.singular.SingularElement'",
        "matrix": "'sage.interfaces.singular.SingularElement'",
        "ring": "'sage.interfaces.singular.SingularElement'",
        "string": "'sage.interfaces.singular.SingularElement'",
        "set_ring": "None",
        "current_ring_name": "str",
        "current_ring": "'sage.interfaces.singular.SingularElement'",
        "console": "None",
        "version": "str",
        "eval": "str",
    },
}

CURATED_ANNOTATIONS["sage/interfaces/gp.pyi"] = {
    "Gp": {
        "set_seed": "int",
        "_equality_symbol": "str",
        "_exponent_symbol": "str",
        "_false_symbol": "str",
        "_true_symbol": "str",
        "_eval_line": "str",
        "_next_var_name": "str",
        "_reset_expect": "None",
        "console": "None",
        "cputime": "float",
        "get_precision": "int",
        "set_precision": "int",
        "get_series_precision": "int",
        "set_series_precision": "int",
        "set_default": "int",
        "get_default": "str",
        "set": "None",
        "get": "str",
        "kill": "None",
        "help": "str",
        "new_with_bits_prec": "'sage.interfaces.gp.GpElement'",
        "version": "tuple",
    },
}

# Module-level TypeVars used by the contracts above.  The declaration is kept
# in the generated source stub so the extractor records it on each overload.
CURATED_TYPE_VARIABLES: dict[str, tuple[str, ...]] = {
    "sage/arith/misc.pyi": (
        "GcdT",
        "BinomialT",
        "FallingFactorialT",
        "RisingFactorialT",
        "ContinuantT",
        "GaussSumT",
        "RadicalT",
        "CoprimePartT",
    ),
    "sage/arith/functions.pyi": ("LcmT",),
    "sage/crypto/block_cipher/miniaes.pyi": ("MiniAEST",),
    "sage/crypto/mq/rijndael_gf.pyi": ("RijndaelStateT",),
    "sage/crypto/classical.pyi": ("HillKeyT",),
}

# INSERT: declarations that model a real, dynamically inherited method whose
# return changes for a concrete subclass.  These are deliberately narrow:
# only the finite-field subclass is inserted, and the generic declaration
# above remains the fallback for every other curve family.
CURATED_INSERTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "sage/schemes/elliptic_curves/ell_finite_field.pyi": {
        "EllipticCurve_finite_field": (
            "def __call__(self, *args, **kwargs) -> 'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field': ...",
            "def gen(self, i: int) -> 'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field': ...",
            "def __getitem__(self, n) -> 'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field': ...",
            "def __iter__(self) -> Iterator['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field']: ...",
            "def random_point(self, *args, **kwargs) -> 'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field': ...",
            f"def base_ring(self) -> {FINITE_FIELD_UNION}: ...",
            f"def a1(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def a2(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def a3(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def a4(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def a6(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def b2(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def b4(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def b6(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def b8(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def c4(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def c6(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def discriminant(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def j_invariant(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
        ),
    },
    "sage/schemes/elliptic_curves/ell_point.pyi": {
        "EllipticCurvePoint_finite_field": (
            f"def __getitem__(self, n) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def __iter__(self) -> Iterator[{FINITE_FIELD_ELEMENT_UNION}]: ...",
            f"def x(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def y(self) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def weil_pairing(self, Q, n, algorithm=None) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
            f"def tate_pairing(self, Q, n, k, q=None) -> {FINITE_FIELD_ELEMENT_UNION}: ...",
        ),
    },
    "sage/rings/integer_ring.pyi": {
        "IntegerRing_class": (
            "def __call__(self, x=0, *args, **kwds) -> 'sage.rings.integer.Integer': ...",
        ),
    },
    "sage/rings/rational_field.pyi": {
        "RationalField": (
            "def __call__(self, x=0, *args, **kwds) -> 'sage.rings.rational.Rational': ...",
        ),
    },
    "sage/rings/finite_rings/finite_field_prime_modn.pyi": {
        "FiniteField_prime_modn": (
            "def __call__(self, x=0, *args, **kwds) -> 'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp': ...",
            "def random_element(self, *args, **kwds) -> 'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp': ...",
        ),
    },
    "sage/rings/finite_rings/finite_field_givaro.pyi": {
        "FiniteField_givaro": (
            "def __call__(self, x=0, *args, **kwds) -> 'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement': ...",
        ),
    },
    "sage/rings/finite_rings/finite_field_ntl_gf2e.pyi": {
        "FiniteField_ntl_gf2e": (
            "def __call__(self, x=0, *args, **kwds) -> 'sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement': ...",
            "def __iter__(self) -> Iterator['sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement']: ...",
            "def random_element(self, *args, **kwds) -> 'sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement': ...",
        ),
    },
    "sage/rings/finite_rings/finite_field_pari_ffelt.pyi": {
        "FiniteField_pari_ffelt": (
            "def __call__(self, x=0, *args, **kwds) -> 'sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt': ...",
            "def __iter__(self) -> Iterator['sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt']: ...",
            "def random_element(self, *args, **kwds) -> 'sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt': ...",
        ),
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
        "PolynomialRing_dense_finite_field": (
            f"def gen(self, n=0) -> {FINITE_FIELD_POLYNOMIAL_ELEMENT_UNION}: ...",
            f"def random_element(self, degree=(-1, 2), monic=False, *args, **kwds) -> {FINITE_FIELD_POLYNOMIAL_ELEMENT_UNION}: ...",
        ),
        "PolynomialRing_dense_mod_p": (
            f"def random_element(self, degree=(-1, 2), monic=False, *args, **kwds) -> {POLYNOMIAL_MOD_P_ELEMENT_UNION}: ...",
        ),
    },
    "sage/rings/polynomial/polynomial_modn_dense_ntl.pyi": {
        "Polynomial_dense_mod_p": (
            "def __add__(self, other) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
            "def __mul__(self, other) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
            "def __rmul__(self, other) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
            "def derivative(self, *args) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
        ),
    },
    "sage/rings/polynomial/polynomial_zmod_flint.pyi": {
        "Polynomial_zmod_flint": (
            "def __add__(self, other) -> 'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint': ...",
            "def __mul__(self, other) -> 'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint': ...",
            "def __rmul__(self, other) -> 'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint': ...",
            "def derivative(self, *args) -> 'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint': ...",
        ),
    },
}

# Earlier staging passes inserted forwarding declarations for methods that
# later proved to be implemented directly by the concrete class.  Remove only
# those known forwarding lines and keep the documented implementation (which
# is annotated by ``CURATED_ANNOTATIONS`` above).  This is intentionally
# explicit; broad duplicate removal could discard legitimate overloads.
CURATED_FORWARDING_CLEANUPS: dict[str, dict[str, tuple[str, ...]]] = {
    "sage/schemes/elliptic_curves/ell_point.pyi": {
        "EllipticCurvePoint_finite_field": ("curve", "_acted_upon_"),
    },
}

# Python's data-model methods have a language-level result contract that does
# not depend on a Sage class.  These are intentionally handled separately from
# CURATED_ANNOTATIONS: the pass applies to every Sage class with a missing
# annotation, while leaving an existing Sage-specific annotation untouched.
# Rich comparisons are included as ``bool`` because Sage's concrete element
# implementations expose Python comparison slots that return a boolean (or
# raise ``TypeError`` for unsupported operands).  ``__getitem__``, arithmetic
# and ``__call__`` remain excluded because their result parent depends on the
# receiver and arguments.
PROTOCOL_RETURNS: dict[str, str] = {
    # Constructors/destructors are required by Python's data model to return
    # None.  This is a protocol guarantee, unlike Sage's dynamic factories.
    "__init__": "None",
    "__del__": "None",
    "__init_subclass__": "None",
    # The copy protocol preserves the concrete receiver class.  Unlike a
    # generic ``copy()`` helper this is a Python data-model guarantee, so a
    # missing Sage stub return can be lowered to ``Self`` safely.
    "__copy__": "Self",
    "__deepcopy__": "Self",
    "__str__": "str",
    "__repr__": "str",
    "__format__": "str",
    "__bytes__": "bytes",
    "__bool__": "bool",
    # These conversion and membership hooks have language-level result
    # contracts.  They are safe to annotate even when a generated Sage stub
    # omitted the return because the concrete Sage element is irrelevant to
    # the protocol result consumed by Python/PyCharm.
    "__contains__": "bool",
    # Sage's public comparison slots normalize the internal rich-comparison
    # result to a Python bool.  This is a language-level callable contract for
    # the generated Sage classes, not a concrete-parent guess.
    "__eq__": "bool",
    "__ne__": "bool",
    "__lt__": "bool",
    "__le__": "bool",
    "__gt__": "bool",
    "__ge__": "bool",
    # Mutable-container hooks are specified by Python to perform the update
    # in place and return no value.  Sage implementations follow that
    # protocol even when the stored element/parent is dynamic, so this does
    # not guess an element type or widen the receiver.
    "__setitem__": "None",
    "__delitem__": "None",
    # Descriptor and attribute mutation hooks also signal completion through
    # ``None``; their target/value types are intentionally left untouched.
    "__set__": "None",
    "__delete__": "None",
    "__setattr__": "None",
    "__setslice__": "None",
    # These metaclass hooks are Python predicates, independent of the Sage
    # class being inspected.
    "__instancecheck__": "bool",
    "__subclasscheck__": "bool",
    "__nonzero__": "bool",
    "__int__": "int",
    "__float__": "float",
    "__complex__": "complex",
    "__dir__": "list[str]",
    "__divmod__": "tuple",
    "__len__": "int",
    "__index__": "int",
    "__hash__": "int",
    # Cython/Sage exposes ``__richcmp__`` as the implementation hook used by
    # the six Python comparison operators.  Unlike the public ``__eq__``
    # methods (which may legally return NotImplemented), this hook returns
    # the comparison predicate consumed by the runtime.
    "__richcmp__": "bool",
    # Sage's internal rich-comparison hook feeds the Python comparison
    # protocol and returns the predicate result (the public ``__eq__``/
    # ordering methods may still be symbolic and are intentionally separate).
    "_richcmp_": "bool",
    # ``reversed()`` consumes an iterator, and context managers may return a
    # truthy suppression flag (or ``None``) from ``__exit__``.  These are
    # Python protocol contracts, independent of the Sage object being held.
    "__reversed__": "Iterator",
    "__exit__": "bool | None",
    # Legacy pickle hooks and NumPy's array protocol have fixed outer
    # containers even though their contents depend on the concrete object.
    "__getinitargs__": "tuple",
    "__array_interface__": "dict",
    # Optional gmpy2 conversion hooks return the corresponding gmpy2 scalar
    # when the optional dependency is installed.  Keep the external type
    # quoted so importing a stub never makes gmpy2 mandatory.
    "__mpz__": "'gmpy2.mpz'",
    "__mpfr__": "'gmpy2.mpfr'",
    "__mpc__": "'gmpy2.mpc'",
    # Cython's deallocator and pickle state hook follow the same no-result
    # protocol as Python's ``__del__``/``__setstate__`` methods.
    "__dealloc__": "None",
    "__setstate__": "None",
    "__reduce__": "tuple | str",
    # Sage's display hooks are stable protocol methods: every implementation
    # returns textual output, independent of the receiver's concrete class.
    "_repr_": "str",
    "_latex_": "str",
    # ``copy.copy`` and ``copy.deepcopy`` are required to produce a copy of
    # the receiver.  Self keeps the concrete Sage implementation visible to
    # PyCharm without collapsing it to a public base class.
    "__copy__": "Self",
    "__deepcopy__": "Self",
}

# A small, source-derived subset of Sage's structured docstrings.  Only an
# exact one-line ``OUTPUT:`` value is accepted; prose such as "an element",
# "an iterator", unions, and conditional result descriptions remain unknown.
# Sage's arithmetic documentation uses ``integer`` for its Integer element,
# so that phrase is mapped to the canonical Sage class rather than Python's
# literal ``int``.
DOC_OUTPUT_RETURNS: dict[str, str] = {
    "boolean": "bool",
    "string": "str",
    "float": "float",
    "double": "float",
    "none": "None",
    "nothing": "None",
    "integer": "'sage.rings.integer.Integer'",
    "nonnegative integer": "'sage.rings.integer.Integer'",
    "positive integer": "'sage.rings.integer.Integer'",
    "a positive integer": "'sage.rings.integer.Integer'",
    "a nonnegative integer": "'sage.rings.integer.Integer'",
    "list": "list",
    "dictionary": "dict",
    "tuple": "tuple",
    "a tuple": "tuple",
    "set": "set",
    "a set": "set",
    "a real number": REAL_NUMBER_RETURN_UNION,
}

# Structured Sage docstrings frequently append a human-readable explanation
# after an atomic type label (for example ``OUTPUT: boolean; whether ...``).
# These prefixes are accepted only after the union/conditional guard in
# ``_doc_output_annotation``; descriptions such as ``boolean or tuple`` remain
# deliberately unresolved.
DOC_OUTPUT_PREFIX_RETURNS: tuple[tuple[str, str], ...] = (
    ("boolean", "bool"),
    ("string", "str"),
    ("integer", "'sage.rings.integer.Integer'"),
)

DOC_OUTPUT_BUILTIN_CLASSES: dict[str, str] = {
    "bool": "bool",
    "dict": "dict",
    "float": "float",
    "frozenset": "frozenset",
    "int": "int",
    # Sage documentation frequently uses ``:class:`Integer``` as shorthand
    # for its canonical arbitrary-precision scalar.
    "integer": "'sage.rings.integer.Integer'",
    "list": "list",
    "set": "set",
    "str": "str",
    # ``:class:`String``` is used by a few Sage docstrings for a textual
    # representation, not for the unrelated Coxeter3 wrapper class.
    "string": "str",
    "tuple": "tuple",
}

# Names which are either Python builtins or abstract Sage vocabulary rather
# than a concrete class contract.  A source tree can legitimately contain a
# class named ``String`` or ``Element`` (and even a class named ``list`` in an
# extension module); documentation that uses those words must not redirect
# ordinary strings/containers to that unrelated class.
DOC_EXPLICIT_TYPE_HEAD_STOPWORDS = frozenset(
    {
        "action",
        "category",
        "dict",
        "element",
        "float",
        "function",
        "int",
        "list",
        "map",
        "module",
        "object",
        "polynomial",
        "set",
        "str",
        "string",
        "tuple",
        "type",
        "vector",
    }
)

# Generic nouns intentionally excluded from plain class-name resolution.
# Sage uses these words for families with several runtime implementations;
# resolving them through a coincidentally unique stub class would violate the
# concrete-contract rule (for example ``a matrix`` must remain parameter-
# dependent rather than becoming matrix0.Matrix).
DOC_PLAIN_CLASS_STOPWORDS = frozenset(
    {
        "category",
        "complex",
        "dict",
        "dictionary",
        "element",
        "expression",
        "field",
        "function",
        "generator",
        "graph",
        "group",
        "image",
        "action",
        "representation",
        "basis",
        "coefficient",
        "degree",
        "dimension",
        "weight",
        "order",
        "rank",
        "type",
        "term",
        "value",
        "constant",
        "product",
        "sum",
        "inverse",
        "identity",
        "intersection",
        "difference",
        "quotient",
        "composition",
        "construction",
        "restriction",
        "space",
        "class",
        "curve",
        "sign",
        "integer",
        "iterator",
        "lattice",
        "list",
        "matrix",
        "polynomial matrix",
        "graphics object",
        "maxima object",
        "growth element",
        "module",
        "number",
        "object",
        "parent",
        "pair",
        "point",
        "polynomial",
        "polyhedron",
        "rational",
        "real number",
        "ring",
        "sequence",
        "set",
        "string",
        "tuple",
        "vector",
        "word",
    }
)

# Nouns which identify one and only one runtime class in the curated Sage
# source tree.  These are deliberately not generic words such as ``matrix``
# or ``polynomial``: those have several concrete implementations selected by
# the parent ring and therefore remain unresolved without call arguments.
DOC_OUTPUT_NAMED_CLASSES: tuple[tuple[str, str], ...] = (
    # Plotting APIs use these exact output nouns in their structured
    # docstrings.  ``Graphics`` is the concrete 2-D Sage container; 3-D
    # plots have their own implementation and are kept distinct.
    ("a 2-d graphics object", "'sage.plot.graphics.Graphics'"),
    ("a graphics object", "'sage.plot.graphics.Graphics'"),
    ("a graphic object", "'sage.plot.graphics.Graphics'"),
    ("a plot", "'sage.plot.graphics.Graphics'"),
    ("a 3d plot", "'sage.plot.plot3d.base.Graphics3d'"),
    ("a 3-d plot", "'sage.plot.plot3d.base.Graphics3d'"),
    # Plain ``graph`` prose can denote either Sage's undirected Graph or
    # directed DiGraph; retain both concrete implementations instead of the
    # public GenericGraph base.
    ("a graph", "'sage.graphs.graph.Graph | sage.graphs.digraph.DiGraph'"),
    ("the graph", "'sage.graphs.graph.Graph | sage.graphs.digraph.DiGraph'"),
    ("graph", "'sage.graphs.graph.Graph | sage.graphs.digraph.DiGraph'"),
    ("a fragment of html", "str"),
    ("printed string", "str"),
    ("an asymptotic expansion", "'sage.rings.asymptotic.asymptotic_ring.AsymptoticExpansion'"),
    ("a symbolic expression", "'sage.symbolic.expression.Expression'"),
    ("symbolic expression", "'sage.symbolic.expression.Expression'"),
    ("a time series", "'sage.stats.time_series.TimeSeries'"),
    ("a new power series", "'sage.rings.power_series_ring_element.PowerSeries'"),
    ("a power series", "'sage.rings.power_series_ring_element.PowerSeries'"),
    ("a unicode art representation", "'sage.typeset.unicode_art.UnicodeArt'"),
    ("an ascii art representation", "'sage.typeset.ascii_art.AsciiArt'"),
    ("ascii art for", "'sage.typeset.ascii_art.AsciiArt'"),
    ("unicode art for", "'sage.typeset.unicode_art.UnicodeArt'"),
    ("a sandpiledivisor", "'sage.sandpiles.sandpile.SandpileDivisor'"),
    ("sandpiledivisor", "'sage.sandpiles.sandpile.SandpileDivisor'"),
    ("a sandpileconfig", "'sage.sandpiles.sandpile.SandpileConfig'"),
    ("sandpileconfig", "'sage.sandpiles.sandpile.SandpileConfig'"),
    ("a sandpile", "'sage.sandpiles.sandpile.Sandpile'"),
    ("sandpile", "'sage.sandpiles.sandpile.Sandpile'"),
    # These nouns identify stable public value classes.  They are accepted
    # only when used as the returned value; the union/conditional guard still
    # rejects prose such as ``an automaton or tuple``.
    ("a digraph", "'sage.graphs.digraph.DiGraph'"),
    ("a new digraph", "'sage.graphs.digraph.DiGraph'"),
    ("a directed graph", "'sage.graphs.digraph.DiGraph'"),
    ("directed graph", "'sage.graphs.digraph.DiGraph'"),
    ("an automaton", "'sage.combinat.finite_state_machine.Automaton'"),
    ("a new automaton", "'sage.combinat.finite_state_machine.Automaton'"),
    ("a transducer", "'sage.combinat.finite_state_machine.Transducer'"),
    ("a new transducer", "'sage.combinat.finite_state_machine.Transducer'"),
    ("a knot", "'sage.knots.knot.Knot'"),
)

DOC_SUMMARY_RETURNS: tuple[tuple[str, str], ...] = (
    ("a string", "str"),
    ("an string", "str"),
    ("string", "str"),
    ("the string", "str"),
    ("a list", "list"),
    ("an list", "list"),
    ("list", "list"),
    ("the list", "list"),
    ("a tuple", "tuple"),
    ("an tuple", "tuple"),
    ("tuple", "tuple"),
    ("the tuple", "tuple"),
    ("a pair", "tuple"),
    ("an pair", "tuple"),
    ("pair", "tuple"),
    ("a dictionary", "dict"),
    ("an dictionary", "dict"),
    ("dictionary", "dict"),
    ("the dictionary", "dict"),
    ("a dict", "dict"),
    ("dict", "dict"),
    ("a set", "set"),
    ("an set", "set"),
    ("set", "set"),
    ("the set", "set"),
    ("a real number", REAL_NUMBER_RETURN_UNION),
    ("an real number", REAL_NUMBER_RETURN_UNION),
    ("real number", REAL_NUMBER_RETURN_UNION),
    ("a boolean", "bool"),
    ("an boolean", "bool"),
    ("boolean", "bool"),
    ("a rational number", "'sage.rings.rational.Rational'"),
    ("an integer", "'sage.rings.integer.Integer'"),
    ("a positive integer", "'sage.rings.integer.Integer'"),
    ("a nonnegative integer", "'sage.rings.integer.Integer'"),
    ("integer", "'sage.rings.integer.Integer'"),
    ("none", "None"),
    ("nothing", "None"),
)

# Source documentation sometimes describes a scalar result indirectly rather
# than beginning the sentence with an atomic noun (for example, ``Return the
# smallest prime power`` or ``Return ... as a rational number``).  These
# patterns are intentionally phrased as semantic invariants, not as function
# names, so the pass remains useful for newly indexed Sage modules without a
# growing allow-list.  The conditional/union guard in ``_doc_summary_annotation``
# runs before these patterns are consulted.
DOC_SUMMARY_SCALAR_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"^return the `?n`?-th bernoulli number\b.*\bas a rational number\b", "'sage.rings.rational.Rational'"),
    (r"^return (?:the )?(?:smallest|largest|next|previous) prime power\b", "'sage.rings.integer.Integer'"),
    (r"^return the next probable prime\b", "'sage.rings.integer.Integer'"),
    (r"^return the smallest prime divisor\b", "'sage.rings.integer.Integer'"),
    (r"^return the multinomial coefficient\b", "'sage.rings.integer.Integer'"),
    (r"^return the degree\b", "'sage.rings.integer.Integer'"),
    (r"^return the number of (?:nonzero )?terms\b", "'sage.rings.integer.Integer'"),
    (r"^return the number of variables\b", "'sage.rings.integer.Integer'"),
    (r"^return the decoding radius\b", "int"),
    (r"^return maximal number of errors\b", "int"),
    (r"^return the (?:in)?separable degree\b", "'sage.rings.integer.Integer'"),
    (r"^return the number of vertices\b", "int"),
    (r"^return the number of elliptic points\b", "'sage.rings.integer.Integer'"),
    # Coding-theory metrics and class-number helpers are integral invariants;
    # implementations may expose either Sage Integer or native Python int.
    (r"^return (?:the )?designed distance\b", "'sage.rings.integer.Integer | int'"),
    (r"^return (?:the )?(?:maximal|maximum) number of errors\b", "'sage.rings.integer.Integer | int'"),
    (r"^return (?:the |an? )?class number\b", "'sage.rings.integer.Integer | int'"),
    (r"^return (?:the )?conductor\b", "'sage.rings.integer.Integer | int'"),
    (r"^return (?:the )?sign\b(?!\s+representation)", "'sage.rings.integer.Integer | int'"),
    (r"^return (?:the )?width\b", "'sage.rings.integer.Integer | int'"),
    (r"^return (?:the )?ramification index\b", "'sage.rings.integer.Integer | int'"),
    (r"^return (?:the )?absolute precision\b", "'sage.rings.integer.Integer | int'"),
    (r"^return the ratio of the minimum distance to the code length\b", "'sage.rings.rational.Rational'"),
    (r"^all bkz methods are equivalent to the lll routines\b", "int"),
    (r"^return the labels along the vertical boundary\b", "list"),
    (r"^return the polynomial obtained by shifting all coefficients\b", "Self"),
    (r"^construct polyhedron from [hv]-representation data\.?$", "None"),
    (r"^build the module generators\.?$", "None"),
    (r"^return (?:the )?multiplicity(?: parameter)?\b", "'sage.rings.integer.Integer | int'"),
    (r"^return the dimension\b", "'sage.rings.integer.Integer | int'"),
    (r"^return the coxeter number associated with\b", "'sage.rings.integer.Integer'"),
    (r"^return the (?:dual )?coxeter number\b", "'sage.rings.integer.Integer'"),
    (r"^return the level(?: associated)?\b", "'sage.rings.integer.Integer'"),
    (r"^return (?:the )?name\b", "str"),
    (r"^return a name\b", "str"),
    (r"^return (?:the )?version\b", "str"),
    (r"^return the `{1,2}index`{1,2}-th (?:row|col) name\b", "str"),
    (r"^return the index set of\b", "tuple"),
    # Cartan/crystal diagrams are rendered through Sage's dedicated ASCII
    # art value object.  Some generated docstrings contain the historical
    # article ``a ascii``; keep the wording-based contract tolerant of that
    # grammar instead of relying on a class or method allow-list.
    (r"^return an? ascii art representation\b", "'sage.typeset.ascii_art.AsciiArt'"),
    # Coding-theory implementations expose the minimum distance as a native
    # Python count (verified across the Hamming, Golay and Reed--Muller
    # implementations); it is not a Sage Integer element.
    (r"^return the minimum distance\b", "int"),
    (r"^return the nilpotency step\b", "'sage.rings.integer.Integer'"),
    (r"^return the length of\b(?!.*\bas (?:a |an )?python int\b)", "'sage.rings.integer.Integer | int'"),
    (r"^return the height of\b(?!.*\bas (?:a |an )?python int\b)", "'sage.rings.integer.Integer | int'"),
    (r"^the names of the objects of\b", "str"),
    (r"^return [`']?\\(?:varphi|varepsilon)_i[`']? of\b", "int"),
    (r"^return the index of the basis element\b", "'sage.rings.integer.Integer | int'"),
    (r"^return the index of basis element\b", "'sage.rings.integer.Integer | int'"),
    (r"^return a \*?new\*? variable\.?$", "int"),
    (r"^run a benchmark\.?$", "tuple"),
    # LaTeX printer hooks return the rendered source string.  The summary is
    # intentionally semantic so newly indexed printer implementations are
    # covered without naming individual functions.
    (r"^custom [`\"]*_print_latex_[`\"]* method\.?$", "str"),
    (r"^compute and return the approximate order of\b", "int | 'sage.rings.integer.Integer'"),
    # Cryptosystem/S-box size accessors document Python dimensions explicitly
    # as lengths or sizes.  These are ordinary Cython/Python ints (unlike
    # Sage's mathematical ``number of ...`` counters below).
    (r"^return (?:the )?(?:block(?:\s+\(or\s+key\))?|input|output|key)\s+(?:length|size)\b", "int"),
    (r"^(?:the )?(?:block(?:\s+\(or\s+key\))?|input|output|key)\s+(?:length|size)\b", "int"),
    (r"^the number of variables\b", "'sage.rings.integer.Integer'"),
    (r"^apply .* to the bit vector .*\breturn(?:\s+the)?\s+result\b", "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"),
    (r"^return .*\bas a rational number\b", "'sage.rings.rational.Rational'"),
    (r"^return .*\bas symbolic expression\b", "'sage.symbolic.expression.Expression'"),
    (r"^return mathml representation\b", "str"),
    (r"^return canonical string\b", "str"),
    (r"^return int\(self\)\b", "int"),
    (r"^return the ceiling of\b", "'sage.rings.integer.Integer'"),
    (r"^compute the whole part of\b", "'sage.rings.integer.Integer'"),
    (r"^truncate to the integer\b", "'sage.rings.integer.Integer'"),
    (r"^the odd part of the integer\b", "'sage.rings.integer.Integer'"),
    (r"^a random blum prime\b", "'sage.rings.integer.Integer'"),
    (r"^return the `{0,2}k`{0,2} least significant bits\b", "list"),
    (r"^return (?:the )?binary string representation\b", "'sage.monoids.string_monoid_element.StringMonoidElement'"),
    (r"^return the binary representation of\b", "'sage.monoids.string_monoid_element.StringMonoidElement'"),
    (r"^apply .* on the binary string\b", "'sage.monoids.string_monoid_element.StringMonoidElement'"),
    (r"^return an? \d+-bit (?:plain|cipher)text\b", "list"),
    (r"^return the [`\"]?n[`\"]?-th subkey\b", "list"),
    (r"^apply one round of .*\bto .* and return the result\b", "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"),
    (r"^return a random \d+-bit key\b", "list"),
    (r"^return (?:the )?(?:initial )?permutation .*\b(?:\d+-bit|vector of \d+ bits)\b", "list"),
    (r"^return a circular left shift .*\bvector of \d+ bits\b", "list"),
    (r"^return a permutation of a \d+-bit string\b", "list"),
    (r"^return .*squarefree positive integer\b", "'sage.rings.integer.Integer'"),
    (r"^return the number .*\bas an integer\b", "'sage.rings.integer.Integer'"),
    # The public Sage wrapper returns a Rational value; the docstring's
    # numerator/denominator wording describes its mathematical representation,
    # not a Python tuple.
    (r"^this function tries to compute .*\brational number\b", "'sage.rings.rational.Rational'"),
    # Sage documentation occasionally qualifies a value at the end of the
    # summary instead of putting the type in an OUTPUT block.  The qualifier
    # is an explicit runtime contract, so it is safe to apply by wording alone
    # (and avoids a method/class allow-list).
    (r"^return .*\bas (?:a |an )?python (?:integer|int)\b", "int"),
)

DOC_SUMMARY_COLLECTION_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"^(?:return )?(?:the )?(?:extra )?super categories of\b", "list"),
    (r"^return the vertices of the dual graded graph\b", "list"),
    (r"^return the names? of (?:the )?variables\b", "tuple"),
    (r"^return the names? of (?:the )?generators\b", "tuple"),
    (r"^return the monomial coefficients of\b", "dict"),
    (r"^return the monomial basis of the quotient ring of this ideal\.?$", "list"),
    (r"^return a new copy of the list\b", "list"),
    (r"^return a new copy of the dict\b", "dict"),
    (r"^return the coefficients\b", "list"),
    (r"^return the exponents\b", "list"),
    (r"^extended lcm function:.*\breturns\s+(?:a\s+)?triple\b", "tuple"),
    # DES's internal helpers expose GF(2) vectors; PC1 is the sole helper
    # whose documented permutation is returned as a pair/tuple.
    (r"^apply the (?:expansion|permutation) function to\b", "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"),
    (r"^apply the cipher function to\b", "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"),
    (r"^apply the inverse permutation function to\b", "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"),
    (r"^apply the sboxes to\b", "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"),
    (r"^apply the function .*using subkey\b", "list"),
    (r"^return permuted choice 1\b", "tuple"),
    (r"^return permuted choice 2\b", "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"),
    (r"^return the s-boxes\b", "list"),
    (r"^compute the sub key for round\b", "'sage.rings.integer.Integer'"),
)

_DEF_RE = re.compile(r"^(?P<indent>\s*)def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_RETURN_RE = re.compile(r"\s*->\s*(.+?)(:\s*(?:\.\.\.)?)\s*$")
_DOC_SECTION_RE = re.compile(r"^[A-Z][A-Z0-9 _-]{2,}::?\s*$")


def _doc_output_values(value: str) -> tuple[str, ...]:
    """Extract complete ``OUTPUT:`` paragraphs from a Sage docstring.

    Sage uses both ``OUTPUT: integer`` and a section form where the value is
    on the following line.  A section value may itself wrap a Sphinx role over
    several lines (``:class:`Name`` followed by ``<module.Name>``), so the
    extractor joins the contiguous paragraph before contract matching.  It
    intentionally stops at a blank line or the next all-caps doc section;
    examples and later prose are never treated as type evidence.
    """
    lines = value.splitlines()
    outputs: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:OUTPUT|返回值?|输出)\s*[:：]\s*(.*)$", line, re.IGNORECASE)
        if match is None:
            continue
        first = match.group(1).strip()
        cursor = index + 1
        if not first:
            while cursor < len(lines) and not lines[cursor].strip():
                cursor += 1
        parts = [first] if first else []
        while cursor < len(lines):
            stripped = lines[cursor].strip()
            if not stripped:
                # Definition-list OUTPUT items are commonly separated by a
                # blank line.  Continue only when the next non-empty line is
                # another bullet; a blank before EXAMPLES/INPUT/OUTPUT still
                # terminates the paragraph as before.
                lookahead = cursor + 1
                while lookahead < len(lines) and not lines[lookahead].strip():
                    lookahead += 1
                if lookahead < len(lines) and re.match(r"^\s*[-*]\s+", lines[lookahead]):
                    cursor = lookahead
                    continue
                break
            if _DOC_SECTION_RE.match(stripped):
                break
            parts.append(stripped)
            cursor += 1
        if parts:
            # Bullet output descriptions are common in generated docs.  The
            # bullet is formatting, not part of the type contract.
            outputs.append(re.sub(r"^[-*]\s+", "", " ".join(parts)).strip())
    return tuple(outputs)


def _doc_examples_literal_annotation(value: str) -> str | None:
    """Infer only an unambiguous outer Python shape from doctest output.

    A subset of generated Sage stubs has no prose at all (the summary is just
    ``EXAMPLES::``), while the executable example still shows a literal
    result.  Reading one literal line after a ``sage:`` prompt is source-backed
    evidence for the *outer* container/string/bool protocol.  Numeric values
    are deliberately excluded because Sage doctests print both Python and Sage
    integers identically.  Mixed outputs and rich reprs remain unresolved.
    """
    categories: list[str] = []
    lines = value.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^\s*(?:sage|python|gap)\s*:\s*", line, re.IGNORECASE) is None:
            continue
        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines):
            continue
        candidate = lines[cursor].strip()
        if re.match(r"^(?:sage|python|gap)\s*:", candidate, re.IGNORECASE):
            continue
        if candidate.startswith(("Traceback", "...", "File ")):
            continue
        if candidate in {"True", "False"}:
            categories.append("bool")
            continue
        if re.match(r"^(?:[\"'])(?:.*)(?:[\"'])$", candidate, re.DOTALL):
            categories.append("str")
            continue
        if candidate.startswith("[") and candidate.endswith("]"):
            categories.append("list")
            continue
        if candidate.startswith("(") and candidate.endswith(")"):
            categories.append("tuple")
            continue
        if candidate.startswith("{") and candidate.endswith("}"):
            categories.append("dict" if ":" in candidate else "set")
    if not categories or len(set(categories)) != 1:
        return None
    return categories[0]


def _class_name(line: str) -> str | None:
    # Generated docstrings frequently contain prose such as ``class are
    # reordered``.  Treat only a syntactically complete class header as a
    # declaration; otherwise the line-based walker would lose the owning
    # class for every following method and silently skip its contracts.
    if not re.match(r"^\s*class\s+[A-Za-z_]\w*(?:\s*\([^\n]*\))?\s*:\s*(?:#.*)?$", line):
        return None
    return line.lstrip()[6:].split("(")[0].split(":")[0].strip()


def _walk(path: Path):
    # Module-level defs (indent == '') belong to class_name None even when
    # the file declares classes elsewhere; class tracking is per indentation.
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    current_class: str | None = None
    for index, line in enumerate(lines):
        name = _class_name(line)
        if name is not None:
            current_class = name
            continue
        match = _DEF_RE.match(line)
        if not match:
            continue
        indent = match.group("indent")
        yield index, line, match.group("name"), (current_class if indent else None)


def annotate_add(path: Path, members: dict[str, str], class_name: str | None) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    edited: list[str] = []
    for index, line, member, current in _walk(path):
        if current != class_name or member not in members:
            continue
        if "->" in line or ")" not in line:
            continue
        stripped = line.rstrip()
        if not stripped.endswith(":"):
            continue
        lines[index] = stripped[:-1] + " -> " + members[member] + ":\n"
        edited.append(member)
    path.write_text("".join(lines), encoding="utf-8")
    return edited


def annotate_replace(path: Path, members: dict[str, str], class_name: str | None) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    edited: list[str] = []
    for index, line, member, current in _walk(path):
        if current != class_name or member not in members:
            continue
        stripped = line.rstrip()
        match = _RETURN_RE.search(stripped)
        if not match:
            continue
        if match.group(1).strip() == members[member]:
            continue
        # Keep a generated one-line ``...`` body intact while retargeting the
        # return expression.  Older versions only matched body-ending ``:``
        # declarations, so stale FLINT/NTL contracts could survive reruns.
        lines[index] = stripped[: match.start(1)] + members[member] + stripped[match.end(1) :] + "\n"
        edited.append(member)
    path.write_text("".join(lines), encoding="utf-8")
    return edited


def _typing_import_insertion_index(text: str, lines: list[str]) -> int:
    """Return a legal import position while preserving module docstrings."""
    tree = ast.parse(text)
    doc_end = 0
    if tree.body and isinstance(tree.body[0], ast.Expr) and isinstance(getattr(tree.body[0], "value", None), ast.Constant) and isinstance(tree.body[0].value.value, str):
        doc_end = tree.body[0].end_lineno or tree.body[0].lineno
    future_end = max(
        (
            node.end_lineno or node.lineno
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "__future__"
        ),
        default=0,
    )
    if future_end:
        return future_end
    return next(
        (
            index
            for index, line in enumerate(lines)
            if index >= doc_end and (line.startswith("from ") or line.startswith("import "))
        ),
        doc_end,
    )


def annotate_overloads(path: Path, members: dict[str, tuple[str, ...]], class_name: str | None) -> list[str]:
    """Prepend typed overload declarations without discarding the documented implementation.

    The index generator intentionally keeps OVERLOAD declarations and discards
    the paired broad implementation signature.  Keeping that implementation
    preserves the source documentation and remains a fallback for consumers
    that do not use the generated index.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)

    # Rebuild generated one-line overloads instead of stacking a corrected
    # contract on top of an older one.  A stale pass can leave several
    # ``@overload`` decorators immediately before a generated declaration;
    # remove that whole run while retaining the documented implementation,
    # whose header ends with ``:`` rather than ``...``.
    cleaned: list[str] = []
    current_class: str | None = None
    index = 0
    changed = False
    while index < len(lines):
        line = lines[index]
        detected_class = _class_name(line)
        if detected_class is not None:
            current_class = detected_class
        # A module-level function can appear after a class declaration (for
        # example ``matrix`` follows ``matrix.options``).  The lightweight
        # line walker does not reset ``current_class`` on dedent, so derive the
        # effective scope from indentation before cleaning module overloads.
        line_indent = len(line) - len(line.lstrip())
        effective_class = current_class if line_indent else None
        if effective_class == class_name and line.strip() == "@overload":
            cursor = index
            while cursor < len(lines) and lines[cursor].strip() == "@overload":
                cursor += 1
            declaration = lines[cursor].strip() if cursor < len(lines) else ""
            generated_member = next(
                (
                    member
                    for member in members
                    if declaration.startswith(f"def {member}(") and declaration.endswith("...")
                ),
                None,
            )
            if generated_member is not None:
                index = cursor + 1
                changed = True
                continue
        cleaned.append(line)
        index += 1
    if changed:
        path.write_text("".join(cleaned), encoding="utf-8")
        lines = cleaned

    edits: list[tuple[int, list[str], str]] = []
    for index, line, member, current in _walk(path):
        declarations = members.get(member) if current == class_name else None
        if not declarations:
            continue
        # Generated overload declarations are members too; only prepend the
        # block to the original broad implementation signature.
        if line.strip() in declarations:
            continue
        indent = _DEF_RE.match(line).group("indent")
        block = [item for declaration in declarations for item in (f"{indent}@overload\n", f"{indent}{declaration}\n")]
        if lines[max(0, index - len(block)):index] == block:
            continue
        edits.append((index, block, member))
    for index, block, _ in reversed(edits):
        lines[index:index] = block
    if edits and not any(
        re.match(r"^from typing import .*\boverload\b", line)
        for line in lines
    ):
        lines.insert(_typing_import_insertion_index("".join(lines), lines), "from typing import overload\n")
    if edits:
        path.write_text("".join(lines), encoding="utf-8")
    return [member for _, _, member in edits]


CONDITIONAL_OUTPUT_MARKER = "# sage-generated-conditional-output"


def _stub_argument_parts(node: ast.FunctionDef | ast.AsyncFunctionDef, typed_name: str, annotation: str) -> list[str]:
    """Render one function argument list for a generated conditional overload."""
    positional = list(node.args.posonlyargs) + list(node.args.args)
    positional_defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
    parts: list[str] = []
    for argument, default in zip(positional, positional_defaults):
        value = argument.arg
        if argument.arg == typed_name:
            value += f": {annotation}"
        if default is not None:
            value += f" = {ast.unparse(default)}"
        parts.append(value)
    if node.args.posonlyargs:
        parts.insert(len(node.args.posonlyargs), "/")
    if node.args.vararg is not None:
        value = "*" + node.args.vararg.arg
        if node.args.vararg.arg == typed_name:
            value += f": {annotation}"
        parts.append(value)
    elif node.args.kwonlyargs:
        parts.append("*")
    for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
        value = argument.arg
        if argument.arg == typed_name:
            value += f": {annotation}"
        if default is not None:
            value += f" = {ast.unparse(default)}"
        parts.append(value)
    if node.args.kwarg is not None:
        value = "**" + node.args.kwarg.arg
        if node.args.kwarg.arg == typed_name:
            value += f": {annotation}"
        parts.append(value)
    return parts


def _conditional_output_declarations(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[str, tuple[str, ...]] | None:
    """Extract a conservative integer/list-like output contract from docs.

    The Sage crypto block-cipher APIs document a stable relation: an integer
    input produces a Sage Integer, while a list-like bit input produces a
    dense GF(2) vector.  Only that explicit paired wording is accepted; a
    generic union or an unqualified ``input`` clause remains unresolved.
    """
    declared_return = ast.unparse(node.returns) if node.returns is not None else None
    doc = ast.get_docstring(node, clean=False) or ""
    compact = " ".join(doc.split())
    # The first paragraph is the API summary; section text and doctest
    # examples must not prevent an exact summary contract from matching.
    # Backend docstrings conventionally put INPUT/OUTPUT/EXAMPLES sections
    # after this paragraph, so matching against the whole compact document
    # would silently miss the getter/setter overload below.
    summary_lines: list[str] = []
    for line in doc.splitlines():
        stripped = line.strip()
        if not stripped:
            if summary_lines:
                break
            continue
        if re.match(r"^[A-Z][A-Z0-9 _-]{2,}::?\s*$", stripped):
            break
        summary_lines.append(stripped)
    summary_compact = " ".join(summary_lines)
    # Backend adapters share a getter/setter contract for their problem name:
    # omitting ``name`` reads the stored Python string, while supplying one
    # updates the backend and returns no value.  Detect the semantic sentence
    # and parameter shape rather than enumerating backend classes.
    if re.fullmatch(r"return or define the problem['’]s name\.?", summary_compact, re.IGNORECASE):
        arguments = list((*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs))
        bound_arguments = arguments[1:] if arguments and arguments[0].arg in {"self", "cls"} else arguments
        name_argument = next((argument for argument in arguments if argument.arg == "name"), None)
        if name_argument is not None and len(bound_arguments) == 1:
            read_parts = ", ".join(_stub_argument_parts(node, "name", "None"))
            write_parts = ", ".join(_stub_argument_parts(node, "name", "str"))
            return "name", (
                f"def {node.name}({read_parts}) -> str: ... {CONDITIONAL_OUTPUT_MARKER}",
                f"def {node.name}({write_parts}) -> None: ... {CONDITIONAL_OUTPUT_MARKER}",
            )
    # Proof preference helpers use one boolean/None flag: passing None reads
    # the current status, while True/False updates it and returns no value.
    status = re.search(
        r"\bif\s+[\x60\"]{0,2}(?P<name>[A-Za-z_]\w*)[\x60\"]{0,2}\s*(?:is|==)\s+[\x60\"]{0,2}none[\x60\"]{0,2}\s*,?\s*"
        r"returns?\s+(?:the\s+)?(?P<kind>[^.]{0,100}\bproof\s+status)\b",
        compact,
        re.IGNORECASE,
    )
    boolean_branch = re.search(
        r"\bif\s+[\x60\"]{0,2}(?P<name>[A-Za-z_]\w*)[\x60\"]{0,2}\s*(?:is|==)\s+[\x60\"]{0,2}(?:true|false)[\x60\"]{0,2}\b",
        compact,
        re.IGNORECASE,
    )
    if status is not None and boolean_branch is not None and status.group("name") == boolean_branch.group("name"):
        parameter = status.group("name")
        argument_names = {
            argument.arg
            for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
        }
        if parameter in argument_names:
            read_result = "dict" if re.search(r"\bglobal\s+sage\s+proof\s+status\b", status.group("kind"), re.IGNORECASE) else "bool"
            read_parts = ", ".join(_stub_argument_parts(node, parameter, "None"))
            write_parts = ", ".join(_stub_argument_parts(node, parameter, "bool"))
            return parameter, (
                f"def {node.name}({read_parts}) -> {read_result}: ... {CONDITIONAL_OUTPUT_MARKER}",
                f"def {node.name}({write_parts}) -> None: ... {CONDITIONAL_OUTPUT_MARKER}",
            )
    # Key-schedule APIs declare a broad ``list`` while their docs make the
    # element type depend on the key representation.  Keep the implementation
    # declaration intact and expose precise list-element overloads alongside
    # it.  Other pre-annotated returns are left untouched.
    if declared_return is not None and declared_return not in {"list", "List"}:
        return None
    if not doc:
        return None
    token = r"[`\"]{0,2}(?P<name>[A-Za-z_]\w*)[`\"]{0,2}"
    integer = re.search(
        rf"\bIf\s+{token}\s+is\s+an?\s+integer\b(?P<body>.{{0,180}}?)\boutput(?:\s+list)?\s+will\s+be\s+(?:too|an?\s+integer)\b",
        compact,
        re.IGNORECASE,
    )
    if integer is None:
        return None
    parameter = integer.group("name")
    quoted_parameter = rf"[`\"]{{0,2}}{re.escape(parameter)}[`\"]{{0,2}}"
    list_like = re.search(
        rf"\bIf\s+{quoted_parameter}\s+is\s+list-like\b.{{0,180}}?"
        rf"(?:\boutput\s+will\s+be\s+(?:a\s+)?bit\s+vectors?\b|"
        rf"\b(?:element|elements)\s+of\s+(?:the\s+)?output\s+list\s+will\s+be\s+(?:a\s+)?bit\s+vectors?\b)",
        compact,
        re.IGNORECASE,
    )
    if list_like is None:
        return None
    argument_names = {
        argument.arg
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs)
    }
    if parameter not in argument_names:
        return None
    list_result = bool(
        re.search(
            r"\b(?:element|elements)\s+of\s+(?:the\s+)?output\s+list\b|"
            r"\boutput\s+list\s+will\s+contain\b",
            compact,
            re.IGNORECASE,
        )
    )
    integer_result = (
        "list['sage.rings.integer.Integer']"
        if list_result
        else "'sage.rings.integer.Integer'"
    )
    vector_result = (
        "list['sage.modules.vector_mod2_dense.Vector_mod2_dense']"
        if list_result
        else "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"
    )
    integer_parts = ", ".join(
        _stub_argument_parts(node, parameter, "int")
    )
    list_parts = ", ".join(
        _stub_argument_parts(node, parameter, "list")
    )
    return parameter, (
        f"def {node.name}({integer_parts}) -> {integer_result}: ... {CONDITIONAL_OUTPUT_MARKER}",
        f"def {node.name}({list_parts}) -> {vector_result}: ... {CONDITIONAL_OUTPUT_MARKER}",
    )


def annotate_conditional_output_overloads(path: Path) -> list[str]:
    """Add generated overloads for explicit, parameter-dependent outputs."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    cleaned: list[str] = []
    index = 0
    removed = False
    while index < len(lines):
        if (
            lines[index].strip() == "@overload"
            and index + 1 < len(lines)
            and CONDITIONAL_OUTPUT_MARKER in lines[index + 1]
        ):
            index += 2
            removed = True
            continue
        cleaned.append(lines[index])
        index += 1
    if removed:
        text = "".join(cleaned)
        lines = cleaned
    try:
        tree = ast.parse(text, filename=str(path), type_comments=True)
    except SyntaxError:
        return []
    edits: list[tuple[int, list[str], str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        contract = _conditional_output_declarations(node)
        if contract is None:
            continue
        _, declarations = contract
        line_index = node.lineno - 1
        if line_index < 0 or line_index >= len(lines):
            continue
        indent = re.match(r"^\s*", lines[line_index]).group(0)
        block = [item for declaration in declarations for item in (f"{indent}@overload\n", f"{indent}{declaration}\n")]
        edits.append((line_index, block, node.name))
    for line_index, block, name in sorted(edits, reverse=True):
        lines[line_index:line_index] = block
    if edits or removed:
        path.write_text("".join(lines), encoding="utf-8")
    if edits:
        ensure_typing_name(path, "overload")
    return [name for _, _, name in edits]


def ensure_type_variables(path: Path, names: tuple[str, ...]) -> bool:
    """Ensure module-level TypeVar declarations required by contracts exist."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    changed = False
    if not any(re.match(r"^from typing import .*\bTypeVar\b", line) for line in lines):
        lines.insert(_typing_import_insertion_index(text, lines), "from typing import TypeVar\n")
        changed = True
    existing = {
        match.group(1)
        for line in lines
        if (match := re.match(r"^(?P<name>[A-Za-z_]\w*)\s*=\s*TypeVar\(", line))
    }
    insertion_index = next(
        (index for index, line in enumerate(lines) if line.startswith("def ") or line.startswith("class ")),
        len(lines),
    )
    # Keep a generated declaration ahead of decorators such as ``@overload``;
    # placing it between a decorator and its function makes the stub invalid.
    while insertion_index > 0 and lines[insertion_index - 1].lstrip().startswith("@"):
        insertion_index -= 1
    declarations = [f'{name} = TypeVar("{name}")\n' for name in names if name not in existing]
    if declarations:
        lines[insertion_index:insertion_index] = declarations
        changed = True
    if changed:
        path.write_text("".join(lines), encoding="utf-8")
    return changed


def remove_shadowed_typing_iterator(path: Path) -> bool:
    """Remove ``typing.Iterator`` when a module defines its own Iterator."""
    text = path.read_text(encoding="utf-8")
    if not (
        re.search(r"^class\s+Iterator\b", text, re.MULTILINE)
        and not re.search(r"\bIterator\s*\[", text)
    ):
        return False
    lines = text.splitlines(keepends=True)
    changed = False
    filtered: list[str] = []
    for line in lines:
        match = re.match(r"^(from typing import )(.+?)\s*$", line)
        if match is None:
            filtered.append(line)
            continue
        imported = [part.strip() for part in match.group(2).split(",")]
        kept = [part for part in imported if part.split(" as ", 1)[0].strip() != "Iterator"]
        if len(kept) == len(imported):
            filtered.append(line)
            continue
        changed = True
        if kept:
            filtered.append(f"{match.group(1)}{', '.join(kept)}\n")
    if changed:
        path.write_text("".join(filtered), encoding="utf-8")
    return changed


def ensure_typing_name(path: Path, name: str) -> bool:
    """Add one typing import without disturbing existing import layout."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    # A Sage extension module may define its own ``Iterator`` class.  In that
    # case a bare ``Iterator`` annotation denotes the concrete Sage class,
    # not ``typing.Iterator``; importing the typing symbol shadows the class
    # and creates duplicate index entries on every annotate pass.
    if (
        name == "Iterator"
        and re.search(r"^class\s+Iterator\b", text, re.MULTILINE)
        and not re.search(r"\bIterator\s*\[", text)
    ):
        return remove_shadowed_typing_iterator(path)
    # ``remove_shadowed_typing_iterator`` may have rewritten the file; reload
    # the current contents before checking/inserting the requested import.
    if name == "Iterator":
        text = path.read_text(encoding="utf-8")
        lines = text.splitlines(keepends=True)
    # A module may carry several ``from typing import ...`` lines after
    # independent contract passes (for example TypeVar and overload).  Check
    # every line before mutating the first one; otherwise a second idempotent
    # run would move the name between import lines and rewrite the stub.
    for index, line in enumerate(lines):
        match = re.match(r"^(from typing import )(.+?)\s*$", line)
        if match is None:
            continue
        imported = {part.strip().split(" as ", 1)[0] for part in match.group(2).split(",")}
        if name in imported:
            return False
    for index, line in enumerate(lines):
        match = re.match(r"^(from typing import )(.+?)\s*$", line)
        if match is None:
            continue
        suffix = match.group(2).rstrip()
        lines[index] = f"{match.group(1)}{suffix}, {name}\n"
        path.write_text("".join(lines), encoding="utf-8")
        return True
    lines.insert(_typing_import_insertion_index(text, lines), f"from typing import {name}\n")
    path.write_text("".join(lines), encoding="utf-8")
    return True


def annotate_insertions(path: Path, classes: dict[str, tuple[str, ...]]) -> list[str]:
    """Insert narrow subclass declarations without replacing inherited APIs.

    The generated Sage stubs retain the subclass docstring immediately below
    the ``class`` line.  Insert after that docstring so the result remains a
    normal class declaration rather than turning its documentation into a
    no-op string expression.
    """
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    # A subclass insertion may replace an older generated declaration after
    # a runtime probe discovers another implementation (for example FLINT vs
    # NTL polynomials).  Remove only one-line ``...`` declarations belonging
    # to this insertion class, retaining documented method bodies.  This also
    # collapses duplicates left by an older annotator version while keeping
    # the operation idempotent for the current declaration.
    filtered: list[str] = []
    current_class: str | None = None
    kept_declarations: set[tuple[str, str]] = set()
    desired_by_class: dict[str, dict[str, set[str]]] = {}
    for class_name, declarations in classes.items():
        member_map: dict[str, set[str]] = {}
        for declaration in declarations:
            match = re.match(r"def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", declaration)
            if match:
                member_map.setdefault(match.group(1), set()).add(declaration)
        desired_by_class[class_name] = member_map
    for line in lines:
        detected_class = _class_name(line)
        if detected_class is not None:
            current_class = detected_class
        match = _DEF_RE.match(line)
        if (
            current_class in desired_by_class
            and match is not None
            and line.strip().endswith("...")
            and match.group("name") in desired_by_class[current_class]
        ):
            normalized = line.strip()
            desired = desired_by_class[current_class][match.group("name")]
            key = (current_class, normalized)
            if normalized not in desired or key in kept_declarations:
                continue
            kept_declarations.add(key)
        filtered.append(line)
    lines = filtered
    inserted: list[str] = []
    for class_name, declarations in classes.items():
        class_index = next(
            (index for index, line in enumerate(lines) if _class_name(line) == class_name),
            None,
        )
        if class_index is None:
            continue
        indent = re.match(r"^(\s*)", lines[class_index]).group(1) + "    "
        existing = "".join(lines)
        missing = [declaration for declaration in declarations if declaration not in existing]
        if not missing:
            continue
        block = [f"{indent}{declaration}\n" for declaration in missing]
        insertion_index = class_index + 1
        while insertion_index < len(lines) and not lines[insertion_index].strip():
            insertion_index += 1
        if insertion_index < len(lines) and re.match(r"^\s*(?:r|u|b|f|br|rb|fr|rf)?['\"]{3}", lines[insertion_index], re.IGNORECASE):
            quote = '\"\"\"' if '\"\"\"' in lines[insertion_index] else "'''"
            # A generated stub may use either a multi-line class docstring or
            # a compact one-line ``\"\"\"text\"\"\"`` form.  Do not scan
            # past the class body when the opening and closing delimiters are
            # on the same line, otherwise subclass declarations are inserted
            # inside the first following top-level function.
            if lines[insertion_index].count(quote) >= 2:
                insertion_index += 1
            else:
                insertion_index += 1
                while insertion_index < len(lines):
                    if quote in lines[insertion_index]:
                        insertion_index += 1
                        break
                    insertion_index += 1
        lines[insertion_index:insertion_index] = block
        inserted.extend(declaration.split("(", 1)[0].removeprefix("def ") for declaration in missing)
    if inserted:
        path.write_text("".join(lines), encoding="utf-8")
        if any("Iterator" in declaration for declarations in classes.values() for declaration in declarations):
            ensure_typing_name(path, "Iterator")
    return inserted


def cleanup_forwarding_declarations(
    path: Path,
    classes: dict[str, tuple[str, ...]],
) -> list[str]:
    """Remove stale one-line forwarders when a real method body exists.

    A previous pass may have inserted ``def method(...) -> T: ...`` for an
    inherited method, then a later source refresh may expose a concrete method
    body in the same subclass.  Keeping both declarations makes IDE lookup
    order-dependent.  The cleanup is AST-scoped to the explicit class/member
    map above and never touches legitimate overload blocks.
    """
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path), type_comments=True)
    except SyntaxError:
        return []
    targets = {
        class_name: {
            (match.group(1) if match is not None else declaration)
            for declaration in declarations
            if (match := re.match(r"def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", declaration))
            or declaration.isidentifier()
        }
        for class_name, declarations in classes.items()
    }
    remove_lines: set[int] = set()
    removed: list[str] = []
    for cls in [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]:
        names = targets.get(cls.name)
        if not names:
            continue
        methods = [
            node
            for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
        ]
        has_real_body = any(
            not (
                len(node.body) == 1
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and node.body[0].value.value is Ellipsis
            )
            for node in methods
        )
        if not has_real_body:
            continue
        for node in methods:
            if (
                len(node.body) == 1
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and node.body[0].value.value is Ellipsis
                and node.lineno == node.end_lineno
            ):
                remove_lines.add(node.lineno - 1)
                removed.append(node.name)
    if not remove_lines:
        return []
    path.write_text(
        "".join(line for index, line in enumerate(text.splitlines(keepends=True)) if index not in remove_lines),
        encoding="utf-8",
    )
    return removed


def _line_offsets(text: str) -> list[int]:
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def _function_header_colon(text: str, line_offsets: list[int], node: ast.FunctionDef | ast.AsyncFunctionDef) -> int | None:
    """Locate the colon ending a function header, including wrapped headers."""
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    seen_def = False
    opened = False
    depth = 0
    for token in tokens:
        row, column = token.start
        if row < node.lineno:
            continue
        if not seen_def:
            if token.type == tokenize.NAME and token.string == "def" and row == node.lineno:
                seen_def = True
            continue
        if token.type == tokenize.OP and token.string == "(":
            opened = True
            depth += 1
            continue
        if not opened:
            continue
        if token.type == tokenize.OP and token.string == ")":
            depth -= 1
            continue
        if token.type == tokenize.OP and token.string == ":" and depth == 0:
            return line_offsets[row - 1] + column
        # A second def before a header colon means the source was malformed;
        # do not risk inserting text into an unrelated declaration.
        if token.type == tokenize.NAME and token.string == "def" and depth == 0:
            return None
    return None


def annotate_protocol_returns(path: Path) -> list[str]:
    """Annotate missing returns for safe Python data-model methods.

    AST traversal limits the pass to methods directly declared by a class, so
    a nested local function named ``__repr__`` is never changed.  Text offsets
    are used instead of line regexes because generated Sage stubs frequently
    wrap long parameter lists over multiple lines.
    """
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path), type_comments=True)
    except SyntaxError:
        return []
    line_offsets = _line_offsets(text)
    edits: list[tuple[int, str, str]] = []

    def visit_class(node: ast.ClassDef) -> None:
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                annotation = PROTOCOL_RETURNS.get(member.name)
                if annotation is not None and member.returns is None:
                    colon = _function_header_colon(text, line_offsets, member)
                    if colon is not None:
                        edits.append((colon, annotation, member.name))
            elif isinstance(member, ast.ClassDef):
                visit_class(member)

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            visit_class(node)
    for offset, annotation, _ in sorted(edits, reverse=True):
        text = text[:offset] + f" -> {annotation}" + text[offset:]
    if edits:
        path.write_text(text, encoding="utf-8")
        if any(annotation == "Self" for _, annotation, _ in edits):
            ensure_typing_name(path, "Self")
        if any(annotation == "Iterator" or annotation.startswith("Iterator[") for _, annotation, _ in edits):
            ensure_typing_name(path, "Iterator")
    return [name for _, _, name in sorted(edits)]


def _prefer_module_class_candidates(
    candidates: tuple[str, ...],
    module_name: str,
) -> tuple[str, ...]:
    """Prefer a unique class from the source module's package.

    A short Sphinx role can be ambiguous globally (``QuadraticForm`` is one
    example) while the enclosing Sage module makes the intended class family
    unambiguous.  Score only the shared dotted-module prefix; do not use a
    method or module allow-list.
    """
    source_parts = module_name.casefold().split(".")
    if not source_parts:
        return candidates
    scored: list[tuple[int, str]] = []
    for candidate in candidates:
        parts = candidate.rsplit(".", 1)[0].casefold().split(".")
        score = 0
        for left, right in zip(source_parts, parts):
            if left != right:
                break
            score += 1
        scored.append((score, candidate))
    best = max((score for score, _ in scored), default=0)
    if best <= 0:
        return candidates
    return tuple(candidate for score, candidate in scored if score == best)


def _doc_class_family_candidates(
    key: str,
    class_index: dict[str, tuple[str, ...]],
) -> tuple[str, ...]:
    """Resolve a documented family name to concrete implementation variants.

    Sage docs often name a family class while stubs expose ring/field or
    dense/sparse implementations.  Prefix-plus-suffix matching is kept
    narrow and source-derived; abstract/base/element variants are excluded.
    """
    if not key:
        return ()
    suffix_pattern = re.compile(
        r"(?:ring|field|finitefield|numberfield|rationalfield|dense|sparse|modp|int|int64|gmp|class)$",
        re.IGNORECASE,
    )
    values: list[str] = []
    for candidate_key, candidates in class_index.items():
        if candidate_key == key or not candidate_key.startswith(key):
            continue
        if not suffix_pattern.fullmatch(candidate_key[len(key) :]):
            continue
        for candidate in candidates:
            terminal = candidate.rsplit(".", 1)[-1]
            if re.search(r"(?:abstract|base|element)$", terminal, re.IGNORECASE):
                continue
            values.append(candidate)
    return tuple(dict.fromkeys(sorted(values)))


def _doc_marked_class_union_annotation(
    output: str,
    class_index: dict[str, tuple[str, ...]],
    module_name: str | None = None,
) -> str | None:
    """Resolve explicit class bullets in an OUTPUT contract.

    A few Sage backends document a dispatch boundary as a short list, for
    example ``- ``GAP3Record`` -- ...`` or ``- ``ExpectFunction`` -- ...``.
    These are concrete alternatives, not a public base class.  Require the
    reStructuredText definition-list marker and a unique source-indexed class
    for every item so ordinary prose and ambiguous family names remain
    unresolved.
    """
    if not output or not class_index:
        return None
    targets = re.findall(
        r"(?:^|\s)(?:-\s+)?`{1,2}(?P<target>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`{1,2}\s+--",
        output,
    )
    if len(targets) < 2:
        return None
    annotations: list[str] = []
    for target in targets:
        # A bullet naming a lowercase value (``none``/``true``) is not a
        # class alternative.  Concrete Sage classes use a capitalized
        # terminal or a qualified import path.
        if not target.rsplit(".", 1)[-1][:1].isupper():
            return None
        if target.startswith("sage."):
            candidates = tuple(
                value
                for values in class_index.values()
                for value in values
                if value.casefold() == target.casefold()
            )
            if len(candidates) != 1:
                candidates = class_index.get(
                    re.sub(r"[^a-z0-9]", "", target.rsplit(".", 1)[-1].casefold()), ()
                )
        else:
            key = re.sub(r"[^a-z0-9]", "", target.casefold())
            candidates = class_index.get(key, ())
            if len(candidates) != 1 and module_name:
                candidates = _prefer_module_class_candidates(candidates, module_name)
        if len(candidates) != 1:
            return None
        annotations.append(f"'{candidates[0]}'")
    deduped = list(dict.fromkeys(annotations))
    return " | ".join(deduped) if len(deduped) >= 2 else None


def _doc_output_class_annotation(
    output: str,
    class_index: dict[str, tuple[str, ...]],
    module_name: str | None = None,
) -> str | None:
    """Resolve a single Sphinx class role against the source class index.

    Sage's docstrings often use a lower-case Sphinx role (``:class:`digraph``)
    while the stub declaration is ``DiGraph``.  Resolving only one role whose
    target is unique gives a source-backed canonical class without a
    class/method allow-list.  Multiple roles, unions, iterators, and container
    descriptions remain unresolved because they do not identify one value.
    """
    roles = re.findall(r":class:`([^`]+)`", output)
    optional_role = False
    builtin_union: str | None = None
    # When a documented result explicitly lists multiple class roles behind
    # ``or``/``either``/a conditional, materialize that concrete union.  This
    # is distinct from the outer-container case (``tuple`` of ``Foo``), which
    # has no result-choice keyword and is handled below.
    if class_index and len(roles) > 1 and re.search(
        r"\b(?:or|either|depending|otherwise|if|when)\b", output, re.IGNORECASE
    ):
        role_annotations: list[str] = []
        for role in roles:
            target = role.strip().lstrip("~")
            if "<" in target and ">" in target:
                target = target.split("<", 1)[1].split(">", 1)[0].strip()
            builtin = DOC_OUTPUT_BUILTIN_CLASSES.get(target.casefold())
            if builtin is not None:
                role_annotations.append(builtin)
                continue
            candidates: tuple[str, ...]
            if target.startswith("sage."):
                candidates = tuple(
                    value
                    for values in class_index.values()
                    for value in values
                    if value.casefold() == target.casefold()
                )
                if len(candidates) != 1:
                    terminal = re.sub(r"[^a-z0-9]", "", target.rsplit(".", 1)[-1].casefold())
                    candidates = class_index.get(terminal, ())
                    if len(candidates) != 1:
                        candidates = _doc_class_family_candidates(terminal, class_index)
            elif re.match(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$", target) and re.match(
                r"^[A-Z_]", target.rsplit(".", 1)[-1]
            ):
                candidates = (target,)
            else:
                key = re.sub(r"[^a-z0-9]", "", target.casefold())
                candidates = class_index.get(key, ())
                if len(candidates) != 1:
                    candidates = _doc_class_family_candidates(key, class_index)
            if len(candidates) != 1:
                role_annotations = []
                break
            role_annotations.append(f"'{candidates[0]}'")
        deduped = list(dict.fromkeys(role_annotations))
        if len(deduped) > 1:
            return " | ".join(deduped)
    if roles:
        # A class role introduced by ``from/of the associated ...`` names an
        # input or contextual parent, not the value being returned (for
        # example ``a coercion map from the associated :class:`FusionRing```)
        # and must not become the result type.  Explicit result markers such
        # as ``as a :class:`` and ``an instance of :class:`` are exempt.
        role_prefix = output[: output.find(":class:`")].casefold()
        explicit_result_marker = re.search(
            r"\b(?:as\s+(?:a|an|the)|(?:a|an|the)\s+instance\s+of)\s*$",
            role_prefix,
            re.IGNORECASE,
        )
        contextual_role_prefix = re.search(
            r"\b(?:for|from|this|given|input|support|associated|element|elements|of)\s+"
            r"(?:(?:an?|the|its|their|associated)\s+){0,2}$",
            role_prefix,
            re.IGNORECASE,
        )
        if contextual_role_prefix is not None and explicit_result_marker is None:
            return None
        optional_role = bool(
            len(roles) == 1
            and (
                re.search(r"\bor\s+(?:none|nothing)\b", output, re.IGNORECASE)
                or re.search(r"\(\s*by\s+default\s*,\s*otherwise\s+(?:none|nothing)\s*\)", output, re.IGNORECASE)
            )
        )
        union_match = re.search(
            r"\bor\s+(?:(?:a|an|the)\s+)?"
            r"(list|tuple|set|dict|dictionary|float|double|integer|int|boolean|bool|"
            r"string|str|bytes|rational|real\s+number|floating[- ]point\s+number)\b",
            output,
            re.IGNORECASE,
        )
        if union_match and len(re.findall(r"\bor\b", output, re.IGNORECASE)) == 1:
            builtin_union = {
                "list": "list",
                "tuple": "tuple",
                "set": "set",
                "dict": "dict",
                "dictionary": "dict",
                "float": "float",
                "double": "float",
                "floating-point number": "float",
                "floating point number": "float",
                "integer": "'sage.rings.integer.Integer'",
                "int": "int",
                "boolean": "bool",
                "bool": "bool",
                "string": "str",
                "str": "str",
                "bytes": "bytes",
                "rational": "'sage.rings.rational.Rational'",
                "real number": REAL_NUMBER_RETURN_UNION,
            }[union_match.group(1).casefold()]
        # Documentation often repeats the same class role in a trailing
        # ``See :class:`Foo` for details`` sentence.  Repetition does not make
        # the result heterogeneous; resolve it when every role names one
        # unique source-indexed class.
        normalized_targets: list[str] = []
        for role in roles:
            target = role.strip().lstrip("~")
            if "<" in target and ">" in target:
                target = target.split("<", 1)[1].split(">", 1)[0].strip()
            normalized_targets.append(target.casefold())
        if len(normalized_targets) > 1 and len(set(normalized_targets)) == 1:
            target = normalized_targets[0]
            builtin = DOC_OUTPUT_BUILTIN_CLASSES.get(target)
            if builtin is not None:
                return builtin
            key = re.sub(r"[^a-z0-9]", "", target)
            candidates = class_index.get(key, ())
            if target.startswith("sage."):
                candidates = tuple(
                    value
                    for values in class_index.values()
                    for value in values
                    if value.casefold() == target
                )
                # Sphinx roles often retain a deprecated/re-exported module
                # path (for example ``sage.libs.flint.fmpz_poly.Fmpz_poly``)
                # while the generated source class lives in the canonical
                # ``..._sage`` module.  If the terminal class name is unique,
                # resolve the role to that canonical source class.
                if len(candidates) != 1:
                    terminal = re.sub(r"[^a-z0-9]", "", target.rsplit(".", 1)[-1].casefold())
                    candidates = class_index.get(terminal, ())
            elif re.match(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$", target) and re.match(
                r"^[A-Z_]", target.rsplit(".", 1)[-1]
            ):
                # Non-Sage Sphinx roles (``inspect.FullArgSpec``,
                # ``matplotlib.colors.Colormap`` and similar) are explicit
                # import paths; preserve them rather than collapsing to an
                # untyped object when no Sage source class exists.
                candidates = (target,)
            if len(candidates) != 1 and module_name:
                candidates = _prefer_module_class_candidates(candidates, module_name)
            if len(candidates) == 1:
                annotation = f"'{candidates[0]}'"
                if builtin_union is not None:
                    return f"{annotation} | {builtin_union}"
                return f"{annotation} | None" if optional_role else annotation
        # ``:class:`tuple` of :class:`Foo``` describes one concrete Python
        # container even though the element role is also present.  Preserve
        # that outer container contract; unions such as ``Foo or tuple`` do
        # not match this prefix form and remain unknown.
        first = roles[0].strip().lstrip("~").casefold()
        builtin_first = DOC_OUTPUT_BUILTIN_CLASSES.get(first)
        if (
            len(roles) == 1
            and builtin_first is not None
            and (optional_role or builtin_union is not None or not re.search(r"\b(?:or|either|iterator|sequence)\b", output))
        ):
            # Qualifiers such as ``increasing`` do not change the outer
            # builtin container.  Keep this before the ambiguity check below
            # so the role's own word (``tuple``/``list``/...) is not mistaken
            # for a union.
            if builtin_union is not None:
                return f"{builtin_first} | {builtin_union}"
            return f"{builtin_first} | None" if optional_role else builtin_first
        if len(roles) > 1 and first in {"tuple", "list", "set", "dict", "dictionary"}:
            return {"tuple": "tuple", "list": "list", "set": "set", "dict": "dict", "dictionary": "dict"}[first]
    role_tail = output[output.find(":class:`") :] if ":class:`" in output else output
    # ``whether or not`` and ``or one of its subclasses`` are descriptive
    # qualifiers, not alternative return types.  Remove those phrases before
    # applying the fail-closed union guard below.
    role_tail_for_guard = re.sub(
        r"\bwhether\s+or\s+not\b|\bor\s+one\s+of\s+its\s+subclasses?\b",
        "",
        role_tail,
        flags=re.IGNORECASE,
    )
    conditional_role_return = re.search(
        r"\bif\b[^.]{0,160}\b(?:returns?|is\s+returned|output)\b",
        output,
        re.IGNORECASE,
    )
    role_outer_alternative = re.search(
        r"\b(?:or|either)\s+(?:(?:a|an|the|as)\s+)?"
        r"(?:iterator|list|tuple|set|dict|dictionary|sequence|integer|int|float|double|"
        r"boolean|bool|string|str|bytes|rational|real|complex|matrix|vector|polynomial|"
        r"point|object|color|(?:`{1,2})?none(?:`{1,2})?|(?:`{1,2})?nothing(?:`{1,2})?)(?=\W|$)",
        role_tail_for_guard,
        re.IGNORECASE,
    )
    if output.count(":class:`") != 1 or conditional_role_return or (
        # Descriptive prose before a single explicit role may contain words
        # such as ``statistic or map``; only alternatives after the class
        # role can change its documented result family.
        role_outer_alternative
        and not optional_role
        and builtin_union is None
    ):
        return None
    match = re.search(r":class:`([^`]+)`", output)
    if match is None:
        return None
    inner = match.group(1).strip()
    target = inner.split("<", 1)[1].split(">", 1)[0].strip() if "<" in inner and ">" in inner else inner
    target = target.lstrip("~").strip()
    builtin = DOC_OUTPUT_BUILTIN_CLASSES.get(target.casefold())
    if builtin is not None:
        return builtin
    if target.startswith("sage."):
        candidates = tuple(
            value
            for values in class_index.values()
            for value in values
            if value.casefold() == target.casefold()
        )
        if len(candidates) != 1:
            terminal = re.sub(r"[^a-z0-9]", "", target.rsplit(".", 1)[-1].casefold())
            candidates = class_index.get(terminal, ())
            if len(candidates) != 1:
                candidates = _doc_class_family_candidates(terminal, class_index)
    elif re.match(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$", target) and re.match(
        r"^[A-Z_]", target.rsplit(".", 1)[-1]
    ):
        candidates = (target,)
    else:
        key = re.sub(r"[^a-z0-9]", "", target.casefold())
        candidates = class_index.get(key, ())
        # Prefer the enclosing source module before falling back to a family
        # expansion.  Otherwise an ambiguous short role (for example
        # ``QuadraticForm``) loses the only module-local candidate when the
        # family helper quite correctly returns no variants.
        if len(candidates) != 1 and module_name:
            preferred = _prefer_module_class_candidates(candidates, module_name)
            if len(preferred) == 1:
                candidates = preferred
        if len(candidates) != 1:
            candidates = _doc_class_family_candidates(key, class_index)
    if len(candidates) != 1 and module_name:
        candidates = _prefer_module_class_candidates(candidates, module_name)
    if len(candidates) > 1:
        annotation = " | ".join(f"'{candidate}'" for candidate in candidates)
        if builtin_union is not None:
            return f"{annotation} | {builtin_union}"
        return f"{annotation} | None" if optional_role else annotation
    if len(candidates) != 1:
        return None
    annotation = f"'{candidates[0]}'"
    if builtin_union is not None:
        return f"{annotation} | {builtin_union}"
    return f"{annotation} | None" if optional_role else annotation


def _doc_plain_class_annotation(
    output: str,
    class_index: dict[str, tuple[str, ...]],
    module_name: str | None = None,
) -> str | None:
    """Resolve a plain-text noun phrase to one unique source class.

    A number of Sage docstrings say ``OUTPUT: a finite state machine`` or
    ``Return a regular sequence`` without a Sphinx role.  We only inspect the
    short noun phrase at the beginning, strip descriptive articles/adjectives,
    and require an exact unique match in the parsed source class index.  The
    stopword set above keeps generic multi-implementation families
    fail-closed; no method/class allow-list is involved.
    """
    if not output or ":class:`" in output:
        return None
    # Interface/adapter docs often expose their concrete constructor class as
    # ``the class of GiacElements`` (or ``the class handling an element``).
    # Resolve the capitalized noun against the source class index, including a
    # conservative singular fallback for plural English names.
    class_descriptor = re.match(
        r"^(?:the\s+)?class\s+(?:used\s+for\s+|of\s+|representing\s+|handling\s+(?:an?\s+)?)(?P<name>[A-Z_]\w*)",
        output.strip(),
    )
    if class_descriptor is not None:
        names = [class_descriptor.group("name")]
        if names[0].endswith("s"):
            names.append(names[0][:-1])
        for name in names:
            key = re.sub(r"[^a-z0-9]", "", name.casefold())
            candidates = class_index.get(key, ())
            if len(candidates) != 1 and module_name:
                candidates = _prefer_module_class_candidates(candidates, module_name)
            if len(candidates) == 1:
                return f"'{candidates[0]}'"
    # Sage prose frequently writes an unqualified class followed by an
    # explicit runtime marker (``a ``Graph`` object``, ``a decoder object``
    # or ``the ... instance``) instead of a Sphinx class role.  The marker is
    # important evidence: unlike a bare noun it distinguishes a concrete
    # class name from descriptive mathematical prose.  Resolve only a unique
    # source-indexed terminal class, so overloaded names remain fail-closed.
    marked = re.match(
        r"^(?:a|an|the)\s+(?:[`]{1,2}|\\)?(?P<name>[A-Za-z_]\w*)"
        r"(?:[`]{1,2})?\s+(?:object|instance|element|class)\b",
        output.strip(),
        re.IGNORECASE,
    )
    if marked is not None:
        key = re.sub(r"[^a-z0-9]", "", marked.group("name").casefold())
        candidates = class_index.get(key, ())
        if len(candidates) != 1 and module_name:
            candidates = _prefer_module_class_candidates(candidates, module_name)
        if len(candidates) == 1:
            return f"'{candidates[0]}'"
    candidate = re.sub(r"[`'\"]", "", output.strip().casefold())
    article = re.match(r"^(?:a|an|the)\s+(.+)$", candidate)
    if article is None or re.search(r"\b(?:or|either|if|depending|unless|otherwise)\b", candidate):
        return None
    candidate = article.group(1)
    candidate = re.sub(
        r"^(?:(?:new|particular|corresponding|constructed|resulting|isomorphic|default|canonical)\s+)+",
        "",
        candidate,
    )
    # Keep only the noun phrase.  Trailing qualifiers describe the value but
    # are not part of the class name (``a transducer for ...``).
    candidate = re.split(
        r"\s+(?:for|of|with|associated|corresponding|which|that|whose|where|over|in|on)\b|[.,;:]",
        candidate,
        maxsplit=1,
    )[0].strip()
    if not candidate or candidate in DOC_PLAIN_CLASS_STOPWORDS:
        return None
    # A single lower-case noun is usually mathematical prose rather than a
    # class identity (``an image``, ``a transducer``, ``a point``).  Requiring
    # a multi-word concept keeps this resolver source-backed without creating
    # a growing class-name allow-list; explicit Sphinx roles remain available
    # for unambiguous single class names.
    if len(candidate.split()) < 2:
        return None
    key = re.sub(r"[^a-z0-9]", "", candidate)
    candidates = class_index.get(key, ())
    if len(candidates) != 1 and module_name:
        candidates = _prefer_module_class_candidates(candidates, module_name)
    return f"'{candidates[0]}'" if len(candidates) == 1 else None


def _doc_summary_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    class_index: dict[str, tuple[str, ...]] | None = None,
    owner_name: str | None = None,
) -> str | None:
    """Resolve an atomic type stated by a ``Return ...`` summary sentence.

    A large part of Sage's older documentation uses ``Return ...`` instead of
    an ``OUTPUT:`` section.  Only an atomic noun at the beginning of that
    sentence is accepted; conditional and union prose stays unknown.  This
    keeps the inference source-backed while covering common helpers such as
    ``_repr_`` and collection accessors without a function allow-list.
    """
    match = re.match(r"^(?:return|returns)\s+(?P<rest>.+)$", summary)
    if match is None:
        # The local Sage contract overlays intentionally use Chinese summary
        # lines (``返回矩阵的转置`` etc.).  Treat the complete line as the
        # payload while retaining the same atomic/conditional guards below.
        if not re.match(r"^(?:返回|返回值|输出|绘制|创建|构造)", summary, re.IGNORECASE):
            # A number of older Sage summaries put the return verb in the
            # middle of the sentence (``For M, this function returns an
            # integer B ...``).  This is still an explicit scalar/container
            # contract, but only when the verb is not inside a conditional
            # branch and its first clause contains no alternate result.  The
            # guard is deliberately lexical and generic; it does not depend
            # on a method or module allow-list.
            summary_first_clause = summary.split(".", 1)[0]
            embedded_return = re.search(
                r"\b(?:return|returns|gives|give|produces|produce|yields|yield)\s+"
                r"(?:(?:a|an|the)\s+)?"
                r"(?P<kind>integer|int|long|boolean|bool|float|double|string|str|bytes|"
                r"list|tuple|pair|set|dictionary|dict|none|nothing)\b",
                summary_first_clause,
                re.IGNORECASE,
            )
            if embedded_return is not None:
                prefix = summary_first_clause[: embedded_return.start()]
                tail = summary_first_clause[embedded_return.end() :]
                conditional_prefix = re.search(
                    r"\b(?:if|when|unless|depending|otherwise)\b", prefix, re.IGNORECASE
                )
                tail_for_guard = re.sub(
                    r"\bif\s+and\s+only\s+if\b|\bwhether\s+or\s+not\b",
                    "",
                    tail,
                    flags=re.IGNORECASE,
                )
                alternate_tail = re.search(
                    r"\b(?:if|when|unless|depending|otherwise|none|nothing)\b|"
                    r"\b(?:or|either)\s+(?:(?:a|an|the)\s+)?"
                    r"(?:integer|int|long|boolean|bool|float|double|string|str|bytes|"
                    r"list|tuple|pair|set|dictionary|dict|none|nothing)\b",
                    tail_for_guard,
                    re.IGNORECASE,
                )
                # An article-led noun after ``or`` is an outer result
                # alternative even when the second noun is not one of the
                # built-in names above (``a list ... or a plot``).  Keep the
                # small explanatory forms (``or the original``/``or rather``)
                # that describe the same value rather than another shape.
                if alternate_tail is None and re.search(
                    r"\b(?:or|either)\s+(?:a|an|the)\s+"
                    r"(?!(?:absolute|original|same|given|rather)\b)[a-z][a-z0-9_-]*\b",
                    tail_for_guard,
                    re.IGNORECASE,
                ):
                    alternate_tail = True
                if conditional_prefix is None and alternate_tail is None:
                    embedded_kind = embedded_return.group("kind").casefold()
                    return {
                        "integer": "'sage.rings.integer.Integer'",
                        "int": "int",
                        "long": "int",
                        "boolean": "bool",
                        "bool": "bool",
                        "float": "float",
                        "double": "float",
                        "string": "str",
                        "str": "str",
                        "bytes": "bytes",
                        "list": "list",
                        "tuple": "tuple",
                        "pair": "tuple",
                        "set": "set",
                        "dictionary": "dict",
                        "dict": "dict",
                        "none": "None",
                        "nothing": "None",
                    }[embedded_kind]
            if node.name == "__neg__" and re.match(
                r"^unary\s+minus\s+operator\.?$", summary, re.IGNORECASE
            ):
                return "Self"
            for pattern, annotation in DOC_SUMMARY_SCALAR_PATTERNS:
                if re.search(pattern, summary, re.IGNORECASE):
                    return annotation
            for pattern, annotation in DOC_SUMMARY_COLLECTION_PATTERNS:
                if re.search(pattern, summary, re.IGNORECASE):
                    return annotation
            if re.match(r"^return .* as a python long\b", summary, re.IGNORECASE):
                return "int"
            if (
                node.name == "prod"
                and re.search(r"\bproduct of the prime moduli\b", summary, re.IGNORECASE)
            ):
                return "'sage.rings.integer.Integer'"
            if re.match(r"^(?:iterate|iterates)\s+over\b", summary, re.IGNORECASE):
                return "Iterator"
            if re.match(
                r"^factor(?:ing|ize|ization)?\s+(?:the\s+)?(?:univariate\s+)?polynomial\b|"
                r"^factorisation\s+of\s+univariate\s+polynomials\b",
                summary,
                re.IGNORECASE,
            ):
                return "'sage.structure.factorization.Factorization'"
            if re.match(
                r"^(?:compute|return)\s+(?:the\s+|a\s+)?(?:irreducible\s+)?factorization\s+of\b",
                summary,
                re.IGNORECASE,
            ):
                return "'sage.structure.factorization.Factorization'"
            if re.match(
                r"^(?:return|divide|perform)\b.*\bquotient\s+and\s+remainder\b",
                summary,
                re.IGNORECASE,
            ):
                return "tuple"
            if re.search(r"(?:FiniteField.*Element(?:_[A-Za-z0-9_]+)?|IntegerMod_(?:int|int64|gmp))$", owner_name or ""):
                if node.name in {"_add_", "_sub_", "_mul_", "_div_"} and re.match(
                    r"^(?:add|subtract|multiply|divide)\s+two\s+elements?\b",
                    summary,
                    re.IGNORECASE,
                ):
                    return "Self"
                if node.name == "__invert__" and re.match(
                    r"^return\s+the\s+multiplicative\s+inverse\s+of\s+(?:an?\s+)?(?:element|self)\b",
                    summary,
                    re.IGNORECASE,
                ):
                    return "Self"
                if node.name in {"__lshift__", "__rshift__"} and re.match(
                    r"^perform\s+a\s+(?:left|right)\s+shift\b",
                    summary,
                    re.IGNORECASE,
                ):
                    return "Self"
            if owner_name and re.search(r"polynomial", owner_name, re.IGNORECASE) and re.match(
                r"^(?:add|subtract|multiply|divide) (?:two )?polynomials\b", summary, re.IGNORECASE
            ):
                return "Self"
            if owner_name and re.fullmatch(r"Integer", owner_name, re.IGNORECASE) and re.match(
                r"^(?:compute .*self|the bitwise|the multiplicative|shift [xy] to the|"
                r"compute the exclusive or|integer (?:addition|multiplication|subtraction)|integer\._neg_)",
                summary,
                re.IGNORECASE,
            ):
                return "Self" if not re.search(r"multiplicative", summary, re.IGNORECASE) else "'sage.rings.rational.Rational'"
            return None
        rest = summary.strip()
    else:
        rest = match.group("rest").strip()
        # Some cryptographic transformation descriptions continue with
        # conditional/formula prose (for example S-DES left-shift's ``if
        # n=1`` case).  These anchored output nouns are already complete
        # contracts, so resolve them before the general conditional guard.
        for pattern, annotation in (
            (r"^return a circular left shift\b", "list"),
            (r"^return (?:the )?(?:initial )?permutation .*\b(?:\d+-bit|vector of \d+ bits)\b", "list"),
            (r"^return a permutation of a \d+-bit string\b", "list"),
            # Mini-AES/S-DES accept several binary-string shapes in their
            # prose, but every branch returns a BinaryStrings element.
            (r"^return the binary representation of\b", "'sage.monoids.string_monoid_element.StringMonoidElement'"),
        ):
            if re.search(pattern, summary, re.IGNORECASE):
                return annotation
    normalized_rest = re.sub(r"`{1,2}(true|false|none|nothing)`{1,2}", r"\1", rest, flags=re.IGNORECASE)
    normalized_rest = normalized_rest.replace("`", "").replace('"', "").replace("'", "")
    # Sage's prose sometimes calls a backend-produced list a "set of
    # generators".  Keep this phrase unresolved unless a concrete runtime
    # contract is available; treating the mathematical noun as ``set`` would
    # hide the actual list materialization used by some local-component APIs.
    if re.match(r"^(?:a|an|the)\s+set\s+of\s+generators\b", normalized_rest, re.IGNORECASE):
        return None
    # Sage summaries frequently append a contextual ``where``/``which``
    # clause to an otherwise atomic outer container (for example, ``Return
    # the list of F-rational points ..., where F is ...``).  The alternatives
    # in that clause describe the input parent, not another output shape.
    # Strip only this explicitly contextual suffix before the union guard;
    # genuine output alternatives such as ``a list or a dictionary`` remain
    # rejected by the outer-type check below.
    contextual_container = re.match(
        r"^(?:a|an|the)\s+(?P<kind>list|tuple|pair|set|dictionary|dict)\b"
        r"(?P<body>.*?)(?:,\s+(?:where|which)\b.*|,\s+or\s+(?:in|from)\b.*)?$",
        normalized_rest,
        re.IGNORECASE,
    )
    if contextual_container and re.search(r",\s+(?:where|which)\b|,\s+or\s+(?:in|from)\b", normalized_rest, re.IGNORECASE):
        body = contextual_container.group("body")
        if not re.search(r"\b(?:if|depending|unless|otherwise|none|nothing)\b", body, re.IGNORECASE) and not re.search(
            r"\bor\s+(?:a|an|the)?\s*(?:list|tuple|pair|set|dictionary|dict|iterator|generator|string|text|matrix|vector|polynomial|object|boolean|bool|integer|int|float|double)\b",
            body,
            re.IGNORECASE,
        ):
            return {
                "list": "list",
                "tuple": "tuple",
                "pair": "tuple",
                "set": "set",
                "dictionary": "dict",
                "dict": "dict",
            }[contextual_container.group("kind").casefold()]
    # A Heegner conductor is an integral invariant (runtime Sage Integer),
    # and the NTL GF(2)X ``weight`` is the native coefficient count.  Apply
    # these source-backed refinements before broad scalar phrase tables can
    # widen them to a generic Integer|int result.
    if owner_name and re.search(r"heegnerpoint", owner_name, re.IGNORECASE) and node.name == "conductor":
        return "'sage.rings.integer.Integer'"
    if owner_name and owner_name.casefold() == "ntl_gf2x" and node.name == "weight" and re.search(
        r"number\s+of\s+nonzero\s+coefficients", normalized_rest, re.IGNORECASE
    ):
        return "int"
    # Unary negation is a closed arithmetic operation for Sage value objects;
    # the concrete receiver class is preserved by the operator protocol.  The
    # rule is driven by the operator wording, not by a class list.
    if node.name == "__neg__" and re.match(r"^unary\s+minus\s+operator\.?$", normalized_rest, re.IGNORECASE):
        return "Self"

    # A documented iterator is a stable Python protocol result even when the
    # yielded element type depends on the parent.  Keep that outer contract
    # explicit, but do not guess the element parameter (``Iterator[T]``).
    if re.match(r"^(?:an?|the)\s+iterator\b", normalized_rest, re.IGNORECASE):
        return "Iterator"
    if re.match(r"^(?:iterate|iterates)\s+over\b", summary, re.IGNORECASE):
        return "Iterator"
    if re.match(
        r"^factor(?:ing|ize|ization)?\s+(?:the\s+)?(?:univariate\s+)?polynomial\b|"
        r"^factorisation\s+of\s+univariate\s+polynomials\b",
        summary,
        re.IGNORECASE,
    ):
        return "'sage.structure.factorization.Factorization'"

    # Polynomial factorization methods return Sage's stable Factorization
    # container.  Descriptions that return a unit plus factors use a separate
    # tuple contract and intentionally do not match this anchored form.
    if re.match(
        r"^(?:(?:the|a)\s+)?(?:irreducible\s+)?factorization\s+of\b",
        normalized_rest,
        re.IGNORECASE,
    ) or re.match(
        r"^(?:compute|return)\s+(?:the\s+|a\s+)?(?:irreducible\s+)?factorization\s+of\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "'sage.structure.factorization.Factorization'"

    # Euclidean division APIs explicitly expose the quotient/remainder pair;
    # element implementations may vary with the parent, but the outer tuple
    # is fixed by the contract.
    if re.match(
        r"^(?:quotient\s+and\s+remainder\b|"
        r"(?:return|divide|perform)\b.*\bquotient\s+and\s+remainder\b)",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "tuple"

    # Unary negation and multiplicative inversion are receiver-preserving
    # operations for concrete element implementations.  Restrict this to the
    # corresponding protocol/method names and the explicit self wording;
    # parent-level ``inverse`` factories remain unresolved.
    if node.name in {"__neg__", "_neg_"} and re.match(r"^-?self\b", normalized_rest, re.IGNORECASE):
        return "Self"
    if re.search(r"(?:FiniteField.*Element(?:_[A-Za-z0-9_]+)?|IntegerMod_(?:int|int64|gmp))$", owner_name or ""):
        if node.name in {"_add_", "_sub_", "_mul_", "_div_"} and re.match(
            r"^(?:add|subtract|multiply|divide)\s+two\s+elements?\b",
            normalized_rest,
            re.IGNORECASE,
        ):
            return "Self"
        if node.name == "__invert__" and re.match(
            r"^(?:the\s+)?multiplicative\s+inverse\s+of\s+(?:an?\s+)?(?:element|self)\b",
            normalized_rest,
            re.IGNORECASE,
        ):
            return "Self"
        if node.name in {"__lshift__", "__rshift__"} and re.match(
            r"^perform\s+a\s+(?:left|right)\s+shift\b",
            normalized_rest,
            re.IGNORECASE,
        ):
            return "Self"

    # ``ellipsis_range`` is the eager counterpart of ``ellipsis_iter``:
    # Sage's implementation materializes the arithmetic sequence as a
    # Python list, while the iterator variant intentionally remains generic.
    if node.name == "ellipsis_range" and re.match(
        r"^arithmetic sequence determined by\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "list"

    if re.search(r"\bas a python long\b", normalized_rest, re.IGNORECASE):
        return "int"

    # A few numeric helpers state their scalar contract without an ``OUTPUT``
    # block.  The mathematical noun is unambiguous here: random/greatest/
    # least/smallest integer results are Python/Sage integral values, while
    # the explicit integer-or-rational lift keeps both documented branches.
    if re.match(
        r"^(?:a|an|the)?\s*(?:random|greatest|least|smallest|underlying)\s+integer\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "int" if re.match(r"^(?:a|an|the)?\s*random\s+integer\b", normalized_rest, re.IGNORECASE) else "'sage.rings.integer.Integer | int'"
    if re.match(
        r"^(?:a|an|the)?\s*integer\s+or\s+rational\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return INTEGER_RATIONAL_RETURN_UNION

    if node.name == "prod" and re.match(
        r"^the product of the prime moduli\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "'sage.rings.integer.Integer'"
    if re.match(r"^a block term ordering\b", normalized_rest, re.IGNORECASE):
        return "'sage.rings.polynomial.term_order.TermOrder'"
    if re.search(r"\bterm ordering of\b", normalized_rest, re.IGNORECASE):
        return "'sage.rings.polynomial.term_order.TermOrder'"
    if not re.search(r"\b(?:or|either|if|depending|unless|otherwise)\b", normalized_rest, re.IGNORECASE):
        if re.match(r"^a list\b", normalized_rest, re.IGNORECASE):
            return "list"
        if re.match(r"^a tuple\b", normalized_rest, re.IGNORECASE):
            return "tuple"
        if re.match(r"^(?:a|an|the)\s+(?:python\s+)?(?:string|text)\b", normalized_rest, re.IGNORECASE):
            return "str"
        if re.match(r"^(?:a|an|the)\s+(?:python\s+)?(?:boolean|bool)\b", normalized_rest, re.IGNORECASE):
            return "bool"
        if re.match(r"^(?:a|an|the)\s+(?:python\s+)?(?:float|double)\b", normalized_rest, re.IGNORECASE):
            return "float"
        if re.match(r"^(?:a|an|the)\s+bytes\b", normalized_rest, re.IGNORECASE):
            return "bytes"
        if re.match(r"^(?:a|an|the)\s+generator\b", normalized_rest, re.IGNORECASE):
            return "Iterator"
        if re.match(r"^(?:an?|the) integer\b", normalized_rest, re.IGNORECASE):
            return "'sage.rings.integer.Integer'"
    if re.match(r"^format string\b", normalized_rest, re.IGNORECASE):
        return "str"

    # ``whether or not`` is one boolean predicate, not a heterogeneous
    # ``or`` union.  Handle it before the generic union guard below; otherwise
    # hundreds of Sage predicates were left UNKNOWN even though their
    # docstrings explicitly state the Python-level result.
    if node.name not in {"__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"} and re.match(
        r"^whether\s+(?:or\s+not\s+)?", normalized_rest, re.IGNORECASE
    ):
        return "bool"
    # A few comparison/predicate hooks use ``Return if ...`` rather than the
    # usual ``Return whether ...`` wording.  The name itself supplies the
    # predicate protocol; coercion-map and data-producing helpers intentionally
    # do not match this boundary.
    predicate_name = node.name.casefold()
    predicate_named = (
        predicate_name in {"__neq__", "_eq", "_neq"}
        or re.search(r"(?:^|_)(?:is|are|has|can|contains|exists|preserves)(?:_|$)", predicate_name)
        or predicate_name.endswith("_test")
    )
    if predicate_named and re.match(r"^if\b", normalized_rest, re.IGNORECASE):
        return "bool"
    if predicate_named and re.match(r"^(?:check|determine|test)\s+(?:whether|if)\b", normalized_rest, re.IGNORECASE):
        if not re.search(
            r"\b(?:find|position|index|map|coercion|database|file|data|list|matrix|tuple|sequence)\b",
            normalized_rest,
            re.IGNORECASE,
        ):
            return "bool"
    if owner_name and re.fullmatch(r"Integer", owner_name, re.IGNORECASE) and re.match(
        r"^(?:compute .*self|the bitwise|the multiplicative|shift [xy] to the|"
        r"compute the exclusive or|integer (?:addition|multiplication|subtraction)|integer\._neg_)",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "Self" if not re.search(r"multiplicative", normalized_rest, re.IGNORECASE) else "'sage.rings.rational.Rational'"
    if owner_name and re.fullmatch(r"Integer", owner_name, re.IGNORECASE) and re.match(
        r"^返回 self 的 .*多重阶乘", normalized_rest
    ):
        return "Self"
    # Iterator implementations that explicitly return themselves satisfy the
    # Python iterator protocol.  This is a source-level invariant and does
    # not guess the element type yielded by ``__next__``.
    if node.name == "__iter__" and re.match(
        r"^self(?:\s*,?\s+as\s+per\s+the\s+iterator\s+protocol)?[.!]?$",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "Self"
    if node.name == "__iter__" and re.match(
        r"^(?:this\s+iterator(?:\s+object\s+itself)?|"
        r"the\s+iterable\s+instance\s+of\s+the\s+class|"
        r"the\s+iterator\s*\(\s*i\.e\.\s*self\s*\)|"
        r"self\s+as\s+an?\s+iterator)\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        # These phrases explicitly identify the receiver as the iterator;
        # unlike ``an iterator over ...`` they do not guess the yielded item.
        return "Self"
    explicit_optional_container = re.match(
        r"^(?:a|an|the)\s+(?P<kind>list|tuple|pair|set|dictionary|dict)\b"
        r".*\bor\s+(?:none|nothing)\b",
        normalized_rest,
        re.IGNORECASE,
    )
    # Some APIs expose two documented container shapes selected by an input
    # argument (for example, a lattice returns a list for one element and a
    # dictionary for all elements).  The outer union is exact even though a
    # parameter-sensitive overload is not available in the generated stub.
    container_union = re.match(
        r"^(?:a|an|the)\s+(?P<left>list|tuple|pair|set|dictionary|dict)\b"
        r".*\b(?:or|either)\s+(?:a|an|the)\s+(?P<right>list|tuple|pair|set|dictionary|dict)\b",
        normalized_rest,
        re.IGNORECASE,
    )
    if container_union and not re.search(
        r"\b(?:if|depending|unless|otherwise|none|nothing)\b", normalized_rest, re.IGNORECASE
    ):
        shape = {"list": "list", "tuple": "tuple", "pair": "tuple", "set": "set", "dictionary": "dict", "dict": "dict"}
        left = shape[container_union.group("left").casefold()]
        right = shape[container_union.group("right").casefold()]
        return left if left == right else f"{left} | {right}"
    # ``or`` is often used for an input/context qualifier (``or in v``), an
    # error path (``or raises``), or a representation selector (``either as
    # a space or as a functional``).  Reject only a second *outer* result
    # protocol; otherwise the leading container noun remains a valid shape.
    if re.match(r"^(?:the\s+)?set\s*\(\s*or\s+rather\s+tuple\b", normalized_rest, re.IGNORECASE):
        return "tuple"
    outer_type_alternative = re.search(
        r"\b(?:or|either)\s+(?:a|an|the)?\s*(?:matrix|polynomial|vector|list|tuple|pair|set|dict|dictionary|iterator|generator|string|text|object|class|field|ring|group|module|ideal|plot|graphics|boolean|bool|integer|int|float|double|rational|real|none|nothing)\b",
        normalized_rest,
        re.IGNORECASE,
    )
    leading_container = re.match(
        r"^(?:a|an|the)\s+(?:list|tuple|pair|set|dictionary|dict)\b",
        normalized_rest,
        re.IGNORECASE,
    )
    if re.search(r"\bdepending\b", normalized_rest) or outer_type_alternative or (
        re.search(r"\b(?:or|either)\b", normalized_rest)
        and not leading_container
    ):
        # A representation can depend on display options while its runtime
        # type remains a string.  Keep the general conditional guard for
        # every other value, but allow a homogeneous ``container or None``
        # contract: the union itself is the exact documented result family,
        # even when the branch is selected by emptiness/availability rather
        # than by an explicit argument.
        if not explicit_optional_container and not re.match(
            r"^(?:a|an|the)\s+(?:string|latex|\\latex)\s+representation\b",
            normalized_rest,
        ):
            return None
    # ``if`` is a conditional payload marker except for the canonical
    # predicate form ``True/False if ...``.  Keep that one boolean contract
    # while rejecting ``a list if ...`` and similar unions.
    if re.search(r"\bif\b", normalized_rest) and not explicit_optional_container and not re.match(r"^(?:true|false)\b", normalized_rest, re.IGNORECASE):
        return None
    if explicit_optional_container:
        return {
            "list": "list | None",
            "tuple": "tuple | None",
            "pair": "tuple | None",
            "set": "set | None",
            "dictionary": "dict | None",
            "dict": "dict | None",
        }[explicit_optional_container.group("kind").casefold()]
    if class_index and ":class:`" in rest:
        class_annotation = _doc_output_class_annotation(rest, class_index)
        if class_annotation is not None:
            return class_annotation
    if class_index and re.match(r"^(?:return|returns|返回|输出|绘制|创建|构造)", normalized_rest, re.IGNORECASE):
        explicit = _doc_explicit_type_annotation(normalized_rest, class_index, owner_name)
        if explicit is not None:
            return explicit
    if owner_name and re.search(r"matrix", owner_name, re.IGNORECASE):
        if re.match(r"^返回矩阵的(?:逐元素共轭|共轭转置|转置)\b", normalized_rest):
            return "Self"
        if re.match(r"^返回矩阵[^。；]*比例", normalized_rest):
            # Sage computes matrix density in QQ (the runtime result is a
            # Sage Rational), even though the prose calls it a ratio.
            return "'sage.rings.rational.Rational'"
    if owner_name and re.search(r"polynomial", owner_name, re.IGNORECASE):
        # These summaries describe operations whose result remains in the
        # receiver's polynomial implementation.  Parent-changing operations
        # (``change_ring``, roots, factorization, etc.) use different prose
        # and remain unresolved.
        if re.match(
                r"^(?:add two polynomials|subtract two polynomials|multiply (?:two )?polynomials|"
            r"return a \"?copy\"? of self|return the quotient upon division\b|"
            r"remainder of division\b|return this polynomial (?:multiplied|but with the coefficients reversed)\b|"
            r"return the formal derivative\b|return the polynomial of degree\b)",
            normalized_rest,
            re.IGNORECASE,
        ):
            return "Self"
    # Concrete operator implementations document their result as the
    # corresponding operation on ``self``.  This is a receiver-preserving
    # contract (unlike a generic ``Element`` base return), so materialize the
    # concrete class through ``Self``.  Keep the method-name and wording
    # guards narrow: divisions, inverses, derivatives and norms can change
    # parent/type and are intentionally left unresolved.
    if node.name in {
        "__add__",
        "__radd__",
        "__sub__",
        "__rsub__",
        "__mul__",
        "__rmul__",
        "_add_",
        "_sub_",
        "_mul_",
        "_lmul_",
        "_rmul_",
        "__neg__",
        "_neg_",
        "__pos__",
        "_pos_",
        "__transpose__",
        "transpose",
    } and re.search(
        r"\b(?:sum|difference|product|negative|opposite|negation|transpose)\b.*\b(?:self|this)\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "Self"
    if class_index:
        class_annotation = _doc_plain_class_annotation(rest, class_index)
        if class_annotation is not None:
            return class_annotation
    # Keep an explicit outer-container qualifier after the source-backed
    # class resolver.  This ordering matters for phrases such as ``a set
    # partition``: that is the concrete ``SetPartition`` class, not a Python
    # ``set``.  Conversely, ``a sorted tuple of values`` has no unique class
    # noun and is safely reduced to its tuple container.
    container_summary = re.match(
        r"^(?:a|an|the)\s+(?:(?:new|sorted|increasing|decreasing|ordered|"
        r"duplicate-free|finite|immutable|lazy|enumerated|nonempty)\s+)*"
        r"(list|tuple|pair|set|dictionary|dict)\b",
        normalized_rest,
    )
    if container_summary and not (
        container_summary.group(1) == "set"
        and re.match(r"\s+partition\b", normalized_rest[container_summary.end() :], re.IGNORECASE)
    ):
        # A few Sage APIs describe a mathematical ``set of generators`` but
        # materialize it as a Python list (for example local-component type
        # spaces).  Without a runtime-backed element contract, keep this
        # semantically ambiguous phrase UNKNOWN instead of publishing the
        # wrong outer protocol.
        if container_summary.group(1) == "set" and re.match(
            r"\s+of\s+generators\b", normalized_rest[container_summary.end() :], re.IGNORECASE
        ):
            return None
        return {
            "list": "list",
            "tuple": "tuple",
            "pair": "tuple",
            "set": "set",
            "dictionary": "dict",
            "dict": "dict",
        }[container_summary.group(1)]
    if node.name.startswith(("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__")):
        # Rich comparisons may legally return NotImplemented even when their
        # prose mentions True/False.
        blocked = {"a boolean", "an boolean", "boolean", "true", "false"}
    else:
        blocked = set()
    if node.name not in {"__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"}:
        # ``Return whether ...`` and explicit True/False predicate summaries
        # are atomic boolean contracts.  The guard is intentionally anchored
        # at the beginning so payload descriptions such as ``a list if ...``
        # remain fail-closed.
        if normalized_rest.startswith(("whether ", "true if ", "false if ", "true when ", "false when ")):
            return "bool"
    if re.fullmatch(r"(?:none|nothing)[.!]?", normalized_rest) and not blocked:
        return "None"
    if re.match(r"^(?:a|an|the)\s+(?:latex|\\latex)\s+representation\b", normalized_rest, re.IGNORECASE):
        return "str"
    if re.match(r"^(?:a|an|the)\s+copy\s+of\s+self\b", normalized_rest, re.IGNORECASE):
        return "Self"
    # Sage descriptions also qualify the copy (for example "translated copy
    # of self").  The phrase itself is an invariant: the operation preserves
    # the receiver's concrete class, so Self is more precise than the
    # abstract parent class and still materializes through the normal
    # receiver-specific lowering path.
    if re.search(r"\bcopy\s+of\s+self\b", normalized_rest, re.IGNORECASE):
        return "Self"
    if re.match(r"^(?:string|latex|\\latex)\s+representation\b", normalized_rest, re.IGNORECASE):
        return "str"
    # Every Sage Cartan/root-system implementation materializes a Dynkin
    # diagram through the single concrete graph class.  The documented noun
    # is therefore enough to select that class without depending on which
    # Cartan parent supplied the method.
    if re.match(
        r"^(?:a|an|the)\s+(?:extended\s+)?dynkin\s+diagram\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "'sage.combinat.root_system.dynkin_diagram.DynkinDiagram_class'"
    for phrase, annotation in DOC_OUTPUT_NAMED_CLASSES:
        if normalized_rest == phrase or normalized_rest.startswith(phrase + " ") or normalized_rest.startswith(phrase + "."):
            return annotation
    if node.name not in {"__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"}:
        # A bare boolean literal (or the canonical ``True or False`` form) is
        # an atomic predicate result.  Do not treat arbitrary prose beginning
        # with ``True``/``False`` as a contract: e.g. ``True or a coercion``
        # describes a conditional union and must remain UNKNOWN.
        if re.fullmatch(r"(?:true|false)[.!?]?", normalized_rest, re.IGNORECASE):
            return "bool"
        if re.fullmatch(
            r"(?:true|false)\s+or\s+(?:true|false)[.!?]?",
            normalized_rest,
            re.IGNORECASE,
        ):
            return "bool"
    for phrase, annotation in sorted(DOC_SUMMARY_RETURNS, key=lambda item: len(item[0]), reverse=True):
        if rest == phrase or rest.startswith(phrase + " ") or rest.startswith(phrase + ".") or rest.startswith(phrase + ":"):
            if phrase in blocked:
                return None
            return annotation
    for pattern, annotation in DOC_SUMMARY_SCALAR_PATTERNS:
        if re.search(pattern, summary, re.IGNORECASE):
            return annotation
    for pattern, annotation in DOC_SUMMARY_COLLECTION_PATTERNS:
        if re.search(pattern, summary, re.IGNORECASE):
            return annotation

    # Chinese-curated contracts use short, unambiguous result nouns in the
    # summary line.  Keep this deliberately narrow: a matrix/ring element is
    # parent-dependent and must not be collapsed to a public base class.
    if normalized_rest.startswith(("返回", "返回值", "输出")):
        if re.search(r"^返回[^。；]*(?:列表|list)(?:$|[：:（(。；])", normalized_rest, re.IGNORECASE):
            return "list"
        if re.search(r"^返回[^。；]*(?:元组|tuple)(?:$|[：:（(。；])", normalized_rest, re.IGNORECASE):
            return "tuple"
        if re.match(r"^(?:返回|输出)(?:是否|一个布尔值|布尔值|布尔)", normalized_rest):
            return "bool"
    # Plain Python outer nouns are stable even when the payload is caller-
    # defined.  Keep these source-level contracts separate from Sage class
    # resolution so a descriptive ``class ...`` phrase cannot be mistaken
    # for a concrete indexed implementation.
    if not re.search(r"\b(?:or|either|if|depending|unless|otherwise|none|nothing)\b", normalized_rest, re.IGNORECASE):
        if re.match(r"^(?:a|an|the)\s+(?:python\s+)?object\b", normalized_rest, re.IGNORECASE):
            return "object"
        if re.match(r"^(?:the\s+)?class\s+(?:of|used\s+to|used\s+for|by|representing|implementing)\b", normalized_rest, re.IGNORECASE):
            return "type"
        # Internal factory hooks use slightly longer but equally explicit
        # class-object wording (``class used for instantiating ...`` or
        # ``class handling an element``).  The semantic verbs distinguish
        # these Python metaclass results from domain objects such as a
        # ``class inclusion digraph`` or a graph-theoretic class.
        if re.match(
            r"^(?:the\s+)?class\b.*\b(?:used\s+(?:to\s+)?(?:implement|instantiate|instantiate)|for\s+instantiating|handling|handles?)\b",
            normalized_rest,
            re.IGNORECASE,
        ):
            return "type"
    # Cardinality/size metrics are Sage integral values when the summary
    # names the metric itself (rather than a parent such as a number field).
    # Run this conservative fallback after specific contracts so established
    # Python-int and optional-union semantics keep their precedence.
    # If an explicit OUTPUT section exists, defer to that stronger contract;
    # this is important for summaries such as ``Return the number ...`` whose
    # OUTPUT narrows the value to a native Python integer or a concrete class.
    # The caller supplies only the summary here, so the output-aware ordering
    # is handled by the metric pass in ``_doc_output_annotation``; these two
    # source-stable exceptions keep the summary path from widening them.
    if node.name.startswith("python_"):
        return None
    metric_match = re.match(
        r"^(?:the\s+)?(?P<metric>number|index|degree|rank|dimension|cardinality|size|count|genus|codimension)\s+(?:of|for|in)\b",
        normalized_rest,
        re.IGNORECASE,
    )
    if metric_match and node.name not in {
        "cardinality", "size", "length", "degree", "order", "height",
        "dimension", "rank", "characteristic", "ngens", "nrows", "ncols",
    } and not re.search(
        r"\b(?:or|either|if|depending|unless|otherwise|none|nothing)\b|\b(?:number|quaternion|order)\s+field\b|\border\s+ideal\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "'sage.rings.integer.Integer'"
    if re.match(r"^(?:the\s+)?order\s+(?:of|for|in)\b", normalized_rest, re.IGNORECASE) and not re.search(
        r"\b(?:or|either|if|depending|unless|otherwise|none|nothing)\b|\b(?:quaternion|ideal|ring|field)\s+order\b|\border\s+ideal\b",
        normalized_rest,
        re.IGNORECASE,
    ):
        return "'sage.rings.integer.Integer'"
    return None


def _doc_summary_class_role_annotation(
    summary: str,
    class_index: dict[str, tuple[str, ...]] | None,
    module_name: str | None = None,
) -> str | None:
    """Resolve an explicitly returned Sphinx class in a summary sentence.

    Sage's generated docs often put the complete contract in the summary
    (``Return a :class:`Foo` ...`` or ``Construct an :class:`Foo` ...``)
    instead of an ``OUTPUT:`` section.  Restrict this fast path to verbs that
    construct/return a value; descriptions such as ``Generate code from an
    :class:`Expression``` are deliberately excluded because the role names an
    input rather than the result.
    """
    construction_contract = re.search(
        r"\b(?:construct(?:s|ed|ing)?|creat(?:e|es|ed|ing)|build(?:s|ing)?)\s+"
        r"(?:a|an|the)\s+(?:(?:formal|new|resulting)\s+)?"
        r":class:`([^`]+)`",
        summary,
        re.IGNORECASE,
    )
    if not class_index or (
        ":class:" not in summary
        and not re.search(r"\b(?:object|instance|form)\b", summary, re.IGNORECASE)
        and not re.match(
            r"^(?:return|returns|construct|constructs|create|creates|build|builds|convert|converts)\s+(?:a|an|the)\s+",
            summary,
            re.IGNORECASE,
        )
        and construction_contract is None
    ):
        return None
    if not re.match(
        r"^(?:return|returns|construct|constructs|create|creates|build|builds|convert|converts)\s+",
        summary,
        re.IGNORECASE,
    ) and construction_contract is None:
        return None
    # A role introduced by ``for``/``from``/``this`` is normally an input or
    # contextual class.  Keep explicit ``as ... of :class:`` result forms,
    # which are common in Sage conversion APIs.
    role_start = summary.find(":class:`")
    prefix = summary[:role_start].casefold()
    explicit_result_prefix = re.search(
        r"\b(?:as\s+(?:a|an|the)|(?:a|an|the)\s+instance\s+of)\s*$",
        prefix,
        re.IGNORECASE,
    )
    if re.search(
        r"\b(?:for|from|this|given|input|support|associated|element|elements|of)\s+"
        r"(?:(?:an?|the|its|their|associated)\s+){0,2}$",
        prefix,
    ) and explicit_result_prefix is None:
        return None
    # A result role can be followed by a second role that merely identifies
    # an input/context object (for example ``self as a :class:`SplittingAlgebra`;
    # ... as a :class:`CubicHeckeRingOfDefinition```); the whole sentence is
    # intentionally rejected by the multi-role guard below.  When the first
    # role is explicitly introduced by ``as a/an/the`` or ``an instance of``,
    # truncate at that role and resolve only the result marker.  This is a
    # structural grammar rule, not a symbol allow-list, and keeps phrases such
    # as ``coercion map from ... :class:`FusionRing``` fail-closed.
    if summary.count(":class:`") > 1:
        first_role_start = summary.find(":class:`")
        first_role_end = summary.find("`", first_role_start + len(":class:`"))
        first_prefix = summary[:first_role_start]
        explicit_result_marker = bool(
            re.search(
                r"\b(?:as\s+(?:a|an|the)|(?:a|an|the)\s+instance\s+of)\s*$",
                first_prefix,
                re.IGNORECASE,
            )
        )
        if first_role_end >= 0 and explicit_result_marker:
            first_role_annotation = _doc_output_class_annotation(
                summary[: first_role_end + 1], class_index, module_name
            )
            if first_role_annotation is not None:
                return first_role_annotation
    # Construction prose may put the input role first and the concrete
    # result role after ``constructing a formal/new ...`` (for example the
    # elliptic-curve homomorphism sum).  That verb phrase is an explicit
    # producer contract, so resolve only the role immediately following it;
    # roles naming operands remain contextual and are never returned.
    constructed_role = construction_contract
    if constructed_role is not None:
        result_role = f"Return a :class:`{constructed_role.group(1)}`"
        constructed_annotation = _doc_output_class_annotation(
            result_role, class_index, module_name
        )
        if constructed_annotation is not None:
            return constructed_annotation
    annotation = _doc_output_class_annotation(summary, class_index)
    if annotation is not None:
        return annotation

    # Some generated Sage summaries use a plain class name followed by an
    # explicit object/instance marker instead of a Sphinx class role.  This is
    # still a concrete result contract, but only when the marker is present;
    # ordinary prose must remain fail-closed.
    result = re.sub(
        r"^(?:return|returns|construct|constructs|create|creates|build|builds|convert|converts)\s+",
        "",
        summary,
        flags=re.IGNORECASE,
    )
    # A large number of Sage summaries name a concrete class in plain prose
    # (``Return the chain complex of self``) instead of using a Sphinx role.
    # Resolve only an exact, unique source-indexed noun phrase; generic
    # families such as matrix/element/space remain blocked by the helper's
    # stopword and uniqueness checks.
    plain_result = _doc_plain_class_annotation(result, class_index, module_name)
    if plain_result is not None:
        return plain_result
    if not re.search(r"\b(?:object|instance|form)\b", result, re.IGNORECASE):
        return None
    annotation = _doc_explicit_type_annotation(result, class_index, None)
    if annotation is None:
        return None
    terminal = annotation.rsplit(".", 1)[-1].strip("'").casefold()
    # These names describe external CAS/interpreter wrappers, not a stable
    # Sage value class that should be exposed as a return annotation.
    if terminal in {
        "axiom",
        "gp",
        "magma",
        "maxima",
        "pari",
        "python",
        "sage",
        "scilab",
        "singular",
        "sympy",
    }:
        return None
    return annotation


def _doc_self_preserving_summary_annotation(
    summary: str,
    owner_name: str | None,
    method_name: str | None = None,
) -> str | None:
    """Resolve summaries that explicitly promise a same-class result."""
    if owner_name is None:
        return None
    normalized = summary.replace(chr(96), "")
    # Sage's unary-negation protocol is closed over the receiver's concrete
    # value family.  Cython backends often document only ``Negate the
    # matrix``/``Return the opposite morphism`` without repeating ``self``;
    # the protocol name plus that semantic wording is the contract.  Keep the
    # rule limited to ``__neg__``/``_neg_`` so ordinary functions mentioning a
    # negative value are never widened to ``Self``.
    if (
        method_name in {"__neg__", "_neg_"}
        and re.search(
            r"\b(?:negat(?:e|ion)|opposite|oppositive|oppositive|negatives?)\b|(?:-\s*self|-\s*x)\b",
            normalized,
            re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:not\s+implemented|returns?\s+(?:a\s+)?scalar|coordinate\s+conversion)\b",
            normalized,
            re.IGNORECASE,
        )
    ):
        return "Self"
    # Dense vector backends expose their Cython arithmetic hooks with little
    # or no prose.  Addition, subtraction, and scalar actions are closed over
    # the concrete vector representation; the vector class stem is the
    # contract, while multiplication is intentionally excluded because Sage
    # vectors may use it for an inner product (a scalar result).
    if (
        method_name in {"_add_", "_sub_", "_lmul_", "_rmul_"}
        and re.search(r"\bvector_", owner_name, re.IGNORECASE)
    ):
        return "Self"
    # Complements of finite bitsets, interval unions, and periodic regions
    # stay in the same concrete representation.  Other ``complement`` APIs
    # may construct a different parent/subspace, so only the representation
    # families named by the contract are eligible.
    if (
        re.search(r"\bcomplement\b", normalized, re.IGNORECASE)
        and re.search(r"(?:bitset|interval|periodic\s*region)", owner_name, re.IGNORECASE)
        and not re.search(r"\b(?:basis|subspace|space|scheme|morphism|map)\b", normalized, re.IGNORECASE)
    ):
        return "Self"
    # A few Cython backends expose only the protocol declaration (or a
    # ``TESTS::`` placeholder) for unary negation.  Their class role still
    # proves closure: vectors, formal sums, free-algebra elements, and
    # morphisms implement negation inside the same concrete parent.  Exclude
    # interface/base families whose negation is known to cross types (PARI,
    # infinities, algebraic-number wrappers).
    if (
        method_name in {"__neg__", "_neg_"}
        and re.search(
            r"(?:vector_|formal\s*sum|freealgebraelement|morphism|mumd?fordivisorclass)",
            owner_name,
            re.IGNORECASE,
        )
        and not re.search(r"(?:pari|infinity|algebraicnumber|lazyimport)", owner_name, re.IGNORECASE)
    ):
        return "Self"
    # Composition of two concrete morphisms/isomorphisms stays in the same
    # implementation family.  The owner role plus the explicit composition
    # wording is the proof; generic ``composition`` helpers without a
    # morphism owner remain unresolved.
    if (
        re.search(r"(?:morphism|isomorphism|homomorphism)", owner_name, re.IGNORECASE)
        and re.search(r"\bcomposition\s+of\s+(?:self|this)\b", normalized, re.IGNORECASE)
        and not re.search(r"\b(?:map|codomain|domain|preimage|inverse image)\b", normalized, re.IGNORECASE)
    ):
        return "Self"
    # Reversing a graph is a representation-preserving copy of the concrete
    # directed graph receiver; this is distinct from generic ``copy`` helpers
    # whose result may be a different data structure.
    if (
        re.search(r"\bcopy\s+of\s+(?:the\s+)?(?:di)?graph\b", normalized, re.IGNORECASE)
        and re.search(r"graph$", owner_name, re.IGNORECASE)
    ):
        return "Self"
    if re.search(r"\bsame class as self\b", normalized, re.IGNORECASE):
        return "Self"
    # Generated Sage docs use both ``instance of the same class`` and
    # ``instance of this class`` when describing constructors/helpers that
    # preserve the receiver implementation.  These are semantic contracts,
    # not names of individual APIs, so they remain valid for newly indexed
    # classes as well.
    if re.search(r"\b(?:instance|object) of (?:the )?same class\b", normalized, re.IGNORECASE):
        return "Self"
    if re.search(r"\b(?:instance|object) of this class\b", normalized, re.IGNORECASE):
        return "Self"
    # Relabeling a matroid changes only the ground-set names.  Sage documents
    # this as an isomorphic matroid, so the concrete implementation class is
    # preserved.  The semantic wording keeps this generic instead of adding
    # a per-method/class allow-list.
    if re.match(
        r"^return an?\s+isomorphic\s+[a-z][a-z ]*\s+with\s+relabeled\s+groundset\.?$",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    if re.match(r"^return an?\s+relabelled\s+structure\.?$", normalized, re.IGNORECASE):
        return "Self"
    # Low-level element multiplication helpers sometimes document the exact
    # expression without spaces (``Return self*right``).  When the receiver
    # is an element and the right operand is explicitly a base-ring value,
    # Sage keeps the same concrete element implementation; scalar/codomain
    # conversions are excluded by the owner and wording guards.
    if (
        re.match(r"^return\s+self\s*\*\s*(?:right|other)\b", normalized, re.IGNORECASE)
        and re.search(r"(?:Element|element)(?:_|[A-Z]|$)", owner_name, re.IGNORECASE)
        and not re.search(
            r"\b(?:convert|conversion|map|morphism|codomain|domain|quotient|scalar\s+result)\b",
            normalized,
            re.IGNORECASE,
        )
    ):
        return "Self"
    # Reduction routines that explicitly promise a reduced version of the
    # receiver keep the same concrete element/structure implementation.  The
    # wording is deliberately narrow; generic ``reduce`` methods that return
    # a residue, representative, or scalar remain unresolved below.
    if re.match(
        r"^return an?\s+reduced\s+version\s+of\s+self\b.*(?:same|class|type|parent)",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    if re.match(r"^return the image of self under the omega automorphism\.?$", normalized, re.IGNORECASE):
        return "Self"
    # Involution/automorphism operators on concrete Sage elements preserve
    # the receiver's parent and implementation class.  This wording appears
    # across Hecke, crystal, tableau and algebra element families.  Exclude
    # explicit morphism/action maps because those may cross a codomain or
    # change the element family.
    if (
        re.match(
            r"^return the image of (?:the )?(?:self|this element) under (?:the )?(?:[a-z0-9_ -]+\s+)?"
            r"(?:involution|automorphism|anti[- ]?involution|promotion|reflection|operator|isomorphism|endomorphism)\b",
            normalized,
            re.IGNORECASE,
        )
        and re.search(r"(?:element|tableau|polynomial|series|ideal|algebra)", owner_name, re.IGNORECASE)
        and not re.search(r"\b(?:morphism|homomorphism|pseudomorphism|action|map|codomain|preimage)\b", normalized, re.IGNORECASE)
    ):
        return "Self"
    if (
        re.match(
            r"^return the image of (?:the )?(?:[\w,.*()' -]+\s+)?self under (?:the )?(?:[\w,.*()' -]+\s+)?"
            r"(?:involution|automorphism|anti[- ]?involution|promotion|reflection|operator|isomorphism|endomorphism)\b",
            normalized,
            re.IGNORECASE,
        )
        and re.search(r"(?:element|tableau|polynomial|series|ideal|algebra)", owner_name, re.IGNORECASE)
        and not re.search(r"\b(?:morphism|homomorphism|pseudomorphism|action|map|codomain|preimage)\b", normalized, re.IGNORECASE)
    ):
        return "Self"
    if (
        re.match(
            r"^return the image of (?:the )?(?:[\w,.*()' -]+\s+)?(?:anti[- ]?involution|automorphism)\s+on\s+self\b",
            normalized,
            re.IGNORECASE,
        )
        and re.search(r"(?:element|tableau|polynomial|series|ideal|algebra)", owner_name, re.IGNORECASE)
    ):
        return "Self"
    if (
        re.match(r"^return the image of (?:the )?\*-\(anti\)involution on self\b", normalized, re.IGNORECASE)
        and re.search(r"(?:element|tableau|polynomial|series|ideal|algebra)", owner_name, re.IGNORECASE)
    ):
        return "Self"
    if re.match(
        r"^return the image of (?:the )?(?:noncommutative )?symmetric function self under the .*verschiebung operator\.?$",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    if re.match(r"^return the lie bracket .*\bself\b.*$", normalized, re.IGNORECASE):
        return "Self"
    # Unary negation and explicitly receiver-based arithmetic preserve the
    # concrete Sage value class.  This wording covers polynomial/vector/map
    # backends without naming owners; conversion, scalar, coordinate and
    # composition descriptions are deliberately excluded because those may
    # change the result family.
    if re.search(
        r"\b(?:negative|negation|additive\s+inverse|negate|opposite)\b.*\b(?:self|this)\b|"
        r"\b(?:self|this)\b.*\b(?:negative|negation|additive\s+inverse|negate|opposite)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:coordinate|scalar|conversion|convert|image|map|composition|not\s+implemented|no\s+sense)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    if re.search(r"\b(?:addition|sum|subtraction|difference|concatenation|product)\b", normalized, re.IGNORECASE) and re.search(
        r"\b(?:self|this)\b", normalized, re.IGNORECASE
    ) and not re.search(
        r"\b(?:coordinate|scalar|conversion|convert|image|map|composition|inner\s+product|not\s+implemented)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    # Ideal arithmetic is closed in the concrete ideal implementation.  The
    # operation names are shared by function-field and localization ideals,
    # while the explicit ideal nouns rule out unrelated scalar division.
    if (
        re.search(r"\b(?:add|multiply)\s+(?:this|the)\s+ideal\b.*\b(?:other|another)\s+ideal\b", normalized, re.IGNORECASE)
        and re.search(r"ideal", owner_name, re.IGNORECASE)
    ):
        return "Self"
    if re.search(r"\b(?:intersection|union)\b", normalized, re.IGNORECASE) and re.search(
        r"\b(?:self|this)\b.*\b(?:other|another)\b|\b(?:other|another)\b.*\b(?:self|this)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:image|map|conversion|convert|parent|base\s+change|not\s+implemented)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    if re.search(r"\bsimplified\s+version\s+of\s+(?:self|this)\b", normalized, re.IGNORECASE):
        return "Self"
    # Concrete Sage element backends use short implementation summaries such
    # as ``Add self and rhs``, ``Subtract right from the element`` or
    # ``Multiply two elements``.  These are closed operations in the
    # receiver's parent, so the exact implementation class is preserved.
    # Restrict the rule to classes whose *semantic role* is an element and
    # reject scalar/action/pairing prose; parent/functor operators are not
    # forced through a shared base type.
    if (
        re.search(r"(?:Element|element)(?:_|[A-Z]|$)", owner_name or "")
        and (owner_name or "").casefold() not in {
            "element",
            "algebraelement",
            "ringelements",
            "ringelement",
            "moduleelement",
        }
        and re.match(
            r"^(?:add|subtract|multiply|sum|difference|product|addition|subtraction|multiplication)\b",
            normalized,
            re.IGNORECASE,
        )
        and not re.search(
            r"\b(?:scalar|coefficient|coordinate|inner\s+product|pairing|action|image|map|morphism|composition|division|quotient|zero\s+element)\b",
            normalized,
            re.IGNORECASE,
        )
    ):
        return "Self"
    # The same closure proof applies to concrete matrix/vector/polynomial
    # and ideal/form families whose backend class name does not end in
    # ``Element``.  Require the documented operation and its value noun to
    # agree with the receiver family; conversions, actions and pairings are
    # intentionally excluded so a scalar/codomain result is never widened to
    # ``Self`` by accident.
    closed_families = (
        (r"polynomial", r"polynomials?"),
        (r"matrix", r"matrices?"),
        (r"vector", r"vectors?"),
        (r"ideal", r"ideals?"),
        (r"form", r"forms?"),
        (r"series", r"series"),
        (r"permutation", r"permutations?"),
    )
    if re.match(
        r"^(?:add|subtract|multiply|sum|difference|product|concatenation|addition|subtraction|multiplication)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:scalar|coefficient|coordinate|inner\s+product|pairing|action|image|map|morphism|composition|division|quotient|directed\s+union)\b",
        normalized,
        re.IGNORECASE,
    ):
        for owner_pattern, noun_pattern in closed_families:
            if re.search(owner_pattern, owner_name or "", re.IGNORECASE) and re.search(
                rf"\b{noun_pattern}\b", normalized, re.IGNORECASE
            ):
                return "Self"
    # A number of generated summaries put the operation behind a leading
    # ``Return the`` (for example ``Return the sum of two ideals``).  The
    # same-family proof above remains valid when the documented result noun
    # agrees with a semantic owner family.  Keep this independent of concrete
    # class names so newly indexed polynomial/series/ideal implementations
    # receive the same contract.
    returned_operation = re.match(
        r"^return\s+(?:the\s+)?(?:sum|product|difference|addition|subtraction|multiplication|concatenation)\b",
        normalized,
        re.IGNORECASE,
    )
    operation_lead = re.match(
        r"^(?:add|subtract|sum|difference|addition|subtraction|concatenation)\b",
        normalized,
        re.IGNORECASE,
    )
    if (returned_operation or operation_lead) and not re.search(
        r"\b(?:scalar|coefficient|coordinate|inner\s+product|pairing|action|image|map|morphism|composition|division|quotient|directed\s+union|not\s+implemented|no\s+sense)\b",
        normalized,
        re.IGNORECASE,
    ):
        returned_families = (
            (r"polynomial|fmpz[_ ]?poly|poly", r"polynomial|polynomials|poly"),
            (r"matrix|(?:^|_)mat(?:_|$)", r"matrix|matrices"),
            (r"vector", r"vector|vectors"),
            (r"ideal", r"ideal|ideals"),
            (r"factorization", r"factorization|factorizations"),
            (r"differential", r"differential|differentials"),
            (r"subgroup", r"subgroup|subgroups"),
            (r"series", r"series"),
            (r"permutation", r"permutation|permutations"),
        )
        for owner_pattern, result_pattern in returned_families:
            if re.search(owner_pattern, owner_name or "", re.IGNORECASE) and re.search(
                rf"\b(?:{result_pattern})\b", normalized, re.IGNORECASE
            ):
                return "Self"
        # Some element protocols omit the result noun but explicitly state
        # that the receiver is combined with another value.  Restrict this
        # fallback to the same semantic families and require both operands;
        # scalar/action descriptions are excluded above.
        if (returned_operation or re.match(r"^(?:add|subtract|difference|addition|subtraction|concatenation)\b", normalized, re.IGNORECASE)) and re.search(
            r"\b(?:self|this)\b", normalized, re.IGNORECASE
        ) and re.search(
            r"\b(?:other|another|right|left)\b", normalized, re.IGNORECASE
        ) and re.search(
            r"(?:ideal|factorization|differential|series|polynomial|matrix|vector|subgroup|permutation|(?:^|_)mat(?:_|$))",
            owner_name or "",
            re.IGNORECASE,
        ):
            return "Self"
    # Some concrete value classes state the closed operation directly but do
    # not repeat their type noun (``Return the product of left and right`` or
    # ``Return the component-wise sum of two forms``).  Restrict this fallback
    # to stable value-family markers, never parents/functors/maps, so a
    # product operation cannot leak a parent or morphism type as ``Self``.
    direct_closed_operation = re.match(
        r"^return\s+(?:the\s+)?(?:product|component-wise\s+(?:sum|difference)|concatenation)\b",
        normalized,
        re.IGNORECASE,
    )
    if direct_closed_operation and not re.search(
        r"\b(?:basis|generator|map|morphism|action|composition|functor|parent|space|ring|field|category|ideal\s+of)\b",
        normalized,
        re.IGNORECASE,
    ):
        if re.search(
            r"(?:fmpz[_ ]?poly|puiseux[_ ]?series|quadratic[_ ]?form|binaryqf|point[_ ]?collection|intlist|"
            r"(?:Element|element)(?:_|[A-Z]|$))",
            owner_name,
            re.IGNORECASE,
        ):
            return "Self"
    # Some concrete value classes phrase the same closure contract with the
    # result noun first (``chart function resulting from ...``), a quoted
    # operator (``'Add' MathJaxExpr ...``), or a direct ``self plus other``
    # sentence.  Derive a shared lexical stem from the owner class and the
    # documented result, rather than enumerating class names.  Parent/map/
    # action/scalar conversions stay excluded by the guards above.
    owner_words = re.findall(
        r"[a-z0-9]+",
        re.sub(r"([a-z])([A-Z])", r"\1 \2", owner_name or "").replace("_", " ").casefold(),
    )
    result_operation = re.match(
        r"^(?:the\s+)?(?P<noun>[a-z][a-z0-9_ -]+?)\s+resulting\s+from\s+(?:the\s+)?"
        r"(?:addition|subtraction|multiplication|division|product|difference|concatenation)\b",
        normalized,
        re.IGNORECASE,
    )
    if result_operation and not re.search(
        r"\b(?:image|map|morphism|composition|inner\s+product|pairing|action|conversion|convert|not\s+implemented)\b",
        normalized,
        re.IGNORECASE,
    ):
        noun_compact = re.sub(r"[^a-z0-9]", "", result_operation.group("noun").casefold())
        owner_compact = re.sub(r"[^a-z0-9]", "", (owner_name or "").casefold())
        if noun_compact and (noun_compact in owner_compact or owner_compact in noun_compact):
            return "Self"
    operation_lead = bool(
        re.match(
            r"^(?:['\"])?(?:add|subtract|multiply|sum|difference|product|concatenation|addition|subtraction|multiplication)\b|"
            r"^return\s+(?:the\s+)?self\s+(?:plus|minus|multiplied|divided)\b|"
            r"^return\s+(?:the\s+)?(?:concatenation|power)\b",
            normalized,
            re.IGNORECASE,
        )
    )
    if operation_lead and not re.search(
        r"\b(?:scalar|coefficient|coordinate|inner\s+product|pairing|action|image|map|morphism|composition|division|quotient|directed\s+union|not\s+implemented|no\s+sense|construct(?:ing|ed)?|formal|resulting\s+in|absolute)\b",
        normalized,
        re.IGNORECASE,
    ) and not (
        re.search(r"\bor\b", normalized, re.IGNORECASE)
        and not re.search(r"\bor\s+(?:a|an|the)\s+(?:string|scalar|number|coefficient)\b", normalized, re.IGNORECASE)
    ):
        normalized_compact = re.sub(r"[^a-z0-9]", "", normalized.casefold())
        generic_words = {
            "abstract",
            "algebra",
            "backend",
            "base",
            "class",
            "data",
            "dense",
            "element",
            "field",
            "generic",
            "group",
            "module",
            "object",
            "parent",
            "ring",
            "space",
            "sparse",
            "type",
            "wrapper",
        }
        meaningful_words = [word for word in owner_words if len(word) >= 4 and word not in generic_words]
        if any(
            re.search(rf"\b{re.escape(word)}(?:s|es|ed|ing)?\b", normalized, re.IGNORECASE)
            or word in normalized_compact
            for word in meaningful_words
        ):
            return "Self"
    if re.search(
        r"\b(?:restriction|restricted|scaled)\b.*\b(?:this\s+)?valuation\b|"
        r"\b(?:this\s+)?valuation\b.*\b(?:restriction|restricted|scaled)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(r"\b(?:residue|value\s+(?:group|semigroup))\b", normalized, re.IGNORECASE):
        return "Self"
    if re.search(
        r"\b(?:derivative|differentiation)\b.*\b(?:self|this|the\s+(?:element|polynomial|series|form))\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:at\s+(?:a\s+)?(?:point|x|s)\b|speed\s+and\s+direction|l[- ]?series)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    # Lazy Taylor/Laurent series derivatives stay in the same concrete
    # series backend.  Their concise docs name the series rather than
    # repeating ``self``; the owner role supplies the remaining proof.
    if (
        re.search(r"(?:power|laurent|taylor)?series", owner_name or "", re.IGNORECASE)
        and re.match(r"^return the derivative of (?:the )?(?:taylor|laurent|power) series\b", normalized, re.IGNORECASE)
        and not re.search(r"\b(?:at|evaluat|value|l[- ]?series)\b", normalized, re.IGNORECASE)
    ):
        return "Self"
    # Crystal operators explicitly describe the action of ``e_i``/``f_i``
    # on the receiver.  They stay in the same concrete crystal-element class
    # and may return ``None`` at an extremal node, so retain that documented
    # optionality instead of exposing a generic element base.
    if re.search(
        r"\baction\s+of\s+[`\\]*(?:e|f)(?:_[A-Za-z0-9]+)?[`\\]*\s+on\s+(?:self|this)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self | None"
    if re.search(r"\bnew instance of self\b", normalized, re.IGNORECASE):
        return "Self"
    if "deepcopy" not in normalized.casefold() and re.search(
        r"\b(?:exact\s+)?copy of (?:itself|[^.]*self)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    match = re.search(
        r"\bnew\s+(?:an?\s+)?([A-Z][A-Za-z0-9_]*)\s+equivalent to self\b",
        normalized,
        re.IGNORECASE,
    )
    if match and match.group(1).casefold() == owner_name.casefold():
        return "Self"
    return None


def _doc_polynomial_base_ring_scalar_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
) -> str | None:
    """Resolve coefficient/resultant-style polynomial scalar contracts.

    Polynomial element implementations expose several scalar-valued helpers
    without an ``OUTPUT`` block.  Their documentation names the coefficient,
    resultant, discriminant, or norm explicitly; these are elements of the
    receiver's base ring.  Keep polynomial *rings*, ideals, and collection
    helpers out of this relation so a parent or list result is never narrowed
    to a scalar.
    """
    if not owner_name or not re.search(r"polynomial", owner_name, re.IGNORECASE):
        return None
    if re.search(r"(?:polynomialring|ideal|morphism|ring_generic)", owner_name, re.IGNORECASE):
        return None
    normalized = re.sub(r"\s+", " ", (summary or "").replace(chr(96), "")).strip()
    scalar_phrase = re.search(
        r"\b(?:constant|leading|lc|monomial)\s+coefficient\b|"
        r"\b(?:coefficient\s+of|resultant|discriminant|content)\b",
        normalized,
        re.IGNORECASE,
    )
    if scalar_phrase is None:
        return None
    if node.name in {"content_ideal", "coefficients", "exponents", "list"}:
        return None
    if re.search(r"\b(?:ideal|list|tuple|dictionary|set|polynomial|factorization)\b", normalized, re.IGNORECASE):
        return None
    return RELATED_ELEMENT_CONTRACTS["base ring"]


def _doc_inverse_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
) -> str | None:
    """Resolve documented inverse operators that preserve the receiver type.

    Sage's multiplicative/involution operators use ``Self`` for concrete
    elements, groups, ideals, morphisms, and isometries.  Complement/region
    operators and matrix inverses are intentionally excluded because their
    result parent or concrete implementation can change.
    """
    if owner_name is None or node.name not in {"__invert__", "inverse"}:
        return None
    if owner_name in {
        "Element",
        "RingElement",
        "AdditiveGroupElement",
        "MultiplicativeGroupElement",
        "InfinityElement",
    } or owner_name.casefold().endswith("homomorphism_generic"):
        return None
    normalized = re.sub(r"\s+", " ", summary.replace(chr(96), "")).strip()
    if not re.search(
        r"\b(?:multiplicative\s+)?inverse\b|\b(?:reciprocal|inverted\s+ideal)\b|"
        r"\binverse\s+(?:element|morphism|coercion|automorphism|isometry|permutation|ideal)\b",
        normalized,
        re.IGNORECASE,
    ):
        return None
    if re.search(
        r"\b(?:complement|closure|region|matrix|cell\s+containing|not\s+implemented)\b",
        normalized,
        re.IGNORECASE,
    ):
        return None
    if re.search(r"\bas\s+(?:a|an)?\s*(?:rational|integer|number|scalar)\b", normalized, re.IGNORECASE):
        return None
    if re.search(
        r"\b(?:return|multiplicative|reciprocal|inverted\s+ideal|inverse\s+(?:element|morphism|coercion|automorphism|isometry|permutation|ideal))\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    return None


def _doc_void_contract_annotation(
    docstring: str,
    method_name: str | None = None,
) -> str | None:
    """Resolve an explicit unconditional ``None``/void documentation.

    Sage has a few Cython methods whose OUTPUT section says ``None. But ...``
    or ``Nothing, but ...`` before explaining an in-place side effect.  The
    regular atomic-output parser intentionally rejects any paragraph that
    contains ``if``/``or`` because those words often denote a union.  A
    punctuation-delimited ``None``/``Nothing`` followed only by an
    explanation is an unconditional void contract and is therefore safe to
    materialize independently of the owner or method name.
    """
    normalized = re.sub(r"\s+", " ", docstring.replace(chr(96), "")).strip()
    # Keep the first explicit OUTPUT value when present.  This avoids prose
    # and doctest examples (which may contain arbitrary ``return None`` text)
    # from becoming type evidence.
    values = _doc_output_values(docstring)
    candidates = values or (normalized,)
    for value in candidates:
        text = re.sub(r"\s+", " ", value.replace(chr(96), "")).strip()
        if re.match(r"^(?:none|nothing)\s*[.;,]\s*(?:but|the|this|that|and|it)\b", text, re.IGNORECASE):
            return "None"
        # A number of Sage OUTPUT sections lead with an unconditional
        # sentence such as ``This method returns ``None``. If ...`` and then
        # describe the state available to callers.  Inspect only that first
        # sentence: the later ``if`` clause is explanatory, not an optional
        # return branch.  This remains fail-closed for ``returns None if``
        # because the conditional appears before the sentence boundary.
        first_sentence = re.split(r"[.!?]", text, maxsplit=1)[0].strip()
        if re.match(
            r"^(?:(?:this|the)\s+(?:method|function)\s+)?returns?\s+(?:none|nothing)\b",
            first_sentence,
            re.IGNORECASE,
        ):
            return "None"
    # Some mutating methods describe the void result in ordinary prose rather
    # than an OUTPUT section.  Restrict this to the explicit phrase and only
    # inspect the documentation before examples, so examples cannot trigger
    # the contract accidentally.
    prose = re.split(r"\n\s*(?:EXAMPLES|TESTS)\s*:?\s*$", docstring, maxsplit=1, flags=re.IGNORECASE)[0]
    # Extract only the leading summary paragraph.  The section splitter above
    # intentionally remains conservative for OUTPUT prose, but generated
    # Sage docs commonly place ``EXAMPLES::`` on a line followed by content;
    # anchoring that splitter to end-of-string would otherwise leave the
    # examples in the semantic sentence and hide simple void contracts.
    summary_lines: list[str] = []
    for line in docstring.splitlines():
        stripped = line.strip()
        if not stripped:
            if summary_lines:
                break
            continue
        if re.match(r"^(?:EXAMPLES|TESTS)\s*:?(?::)?$", stripped, re.IGNORECASE):
            break
        summary_lines.append(stripped)
    summary_head = re.sub(r"\s+", " ", " ".join(summary_lines)).strip()
    # A concise summary may state an unconditional ``return None`` without
    # an OUTPUT section (for example ``Do nothing and return ``None```` or
    # Python's ``shuffle ...; return None`` contract).  Keep this narrow:
    # default/subclass/conditional wording denotes an optional value and must
    # remain unresolved until an overload can model it.
    if (
        re.search(r"\breturns?\s+`{0,2}none`{0,2}\b", summary_head, re.IGNORECASE)
        and not re.search(r"\b(?:by\s+default|subclass|override|otherwise|depending|if|or)\b", summary_head, re.IGNORECASE)
    ):
        return "None"
    if re.search(r"\bdoes not (?:return|output) anything\b", prose, re.IGNORECASE):
        return "None"
    if re.search(
        r"\b(?:should|must|does|do)\s+return\s+(?:nothing|no\s+(?:value|result))\b|"
        r"\breturns?\s+no\s+(?:value|result)\b",
        prose,
        re.IGNORECASE,
    ):
        return "None"
    # Many in-place Sage methods put their contract only in the summary
    # (``Set ...``, ``Clear ...``, ``Update ...`` and similar).  They return
    # no value unless the same sentence explicitly advertises one.  Classcall
    # normalization hooks are excluded because ``Set the default ...`` there
    # still constructs and returns an instance of the class.
    if (
        method_name not in {"__classcall__", "__classcall_private__"}
        and not (method_name or "").startswith("_")
    ):
        summary_lines: list[str] = []
        for line in prose.splitlines():
            stripped = line.strip()
            if not stripped:
                if summary_lines:
                    break
                continue
            summary_lines.append(stripped)
        summary = re.sub(r"\s+", " ", " ".join(summary_lines)).strip()
        if re.match(
            r"^(?:set|clear|reset|delete|remove|initialize|update|add|append|insert)\b",
            summary,
            re.IGNORECASE,
        ) and not re.search(
            r"\b(?:return|returns|new\s+(?:set|object|instance)|construct\w*|create\w*|produce\w*|generate\w*|build\w*)\b",
            summary,
            re.IGNORECASE,
        ):
            return "None"
        # Additional in-place verbs used by Sage's matrix/ideal/iterator
        # implementations.  Requiring an explicit receiver/mutation cue keeps
        # value-producing helpers such as ``reverse`` and ``replace`` out of
        # this void contract.
        if re.match(
            r"^(?:randomize|echelonize|set_immutable|swap(?:_|\s)|sort|fill|redefine|mutate|modify)\b",
            summary,
            re.IGNORECASE,
        ) and re.search(
            r"\b(?:self|in[- ]place|inplace|modify|change|mutat|entries|rows?|columns?|generators?)\b",
            summary,
            re.IGNORECASE,
        ) and not re.search(
            r"\b(?:return|returns|new\s+(?:set|object|instance)|construct\w*|create\w*|produce\w*|generate\w*|build\w*)\b",
            summary,
            re.IGNORECASE,
        ):
            return "None"
        # Pretty-printer entry points and editor launchers perform an external
        # side effect and do not produce a Sage value.  The wording is
        # intentionally semantic, so new ``pp``/editor helpers are covered
        # without naming individual classes.
        if re.match(r"^(?:pretty\s+print(?:ing)?|nodetex)\b", summary, re.IGNORECASE):
            return "None"
        if re.fullmatch(r"write the data to stdout\.?", summary, re.IGNORECASE):
            return "None"
        if re.search(r"\bopen\s+source\s+code\b.*\bin\s+(?:an?\s+)?editor\b", summary, re.IGNORECASE):
            return "None"
        # Validation helpers conventionally raise on invalid input and have
        # no success payload.  Sage's ``check`` methods consistently document
        # that validation role without an OUTPUT/return sentence; recognize
        # the semantic contract generically instead of enumerating classes.
        if (
            method_name == "check"
            and re.match(r"^(?:check|verify|make sure|perform checks?)\b", summary_head, re.IGNORECASE)
            and not re.search(r"\b(?:return|returns|boolean|bool|true|false)\b", prose, re.IGNORECASE)
        ):
            return "None"
        # Display helpers are side-effect-only when their summary describes
        # showing/printing a value and does not promise statistics or a
        # returned object.  ``plot`` is deliberately excluded: Sage plotting
        # APIs return Graphics and need receiver-specific contracts.
        if (
            method_name == "show"
            and re.match(r"^(?:show|display|displays|print|prints|alias for)\b", summary_head, re.IGNORECASE)
            and not re.search(r"\b(?:return|returns|statistics)\b", summary_head, re.IGNORECASE)
        ):
            return "None"
        if (
            method_name == "pretty_print"
            and re.match(r"^(?:show|display|displays|print|prints|pretty\s+print)\b", summary_head, re.IGNORECASE)
            and not re.search(r"\b(?:return|returns|statistics)\b", summary_head, re.IGNORECASE)
        ):
            return "None"
        # Output-only helpers commonly use an explicit side-effect verb in
        # their summary (``Print ...``, ``Display ...``, ``pretty print ...``
        # or ``Print help ...``) without an OUTPUT section.  Their successful
        # call has no payload; require the summary itself to avoid treating a
        # value-producing method whose examples merely print a result as
        # void.  Conversions and statistics remain unresolved because their
        # summaries advertise a result noun.
        if (
            re.match(
                r"^(?:print|prints|display|displays|show|shows|pretty\s+print(?:ing)?|pp|info|help|verbose)\b",
                summary_head,
                re.IGNORECASE,
            )
            and not re.search(
                r"\b(?:return|returns|result|as\s+(?:a|an|the))\b",
                summary_head,
                re.IGNORECASE,
            )
        ):
            return "None"
        if (
            method_name == "console"
            and re.match(r"^(?:spawn|open|launch|start|run)\b", summary_head, re.IGNORECASE)
            and not re.search(r"\b(?:return|returns|object|value)\b", summary_head, re.IGNORECASE)
        ):
            return "None"
        # Construction hooks sometimes state the void contract directly in
        # the prose (``This implementation only returns None`` or ``Return
        # None since ...``) instead of using an OUTPUT section.  Require an
        # unconditional qualifier so ``return None if ...`` stays a union.
        if (
            re.match(r"^return(?:s)?\s+(?:none|nothing)\b(?:\s+(?:since|because)\b|[.!])", summary, re.IGNORECASE)
            or re.search(r"\b(?:only|always|just)\s+returns?\s+(?:none|nothing)\b", prose, re.IGNORECASE)
        ) and not re.search(r"\b(?:if|unless|otherwise|or)\b", prose, re.IGNORECASE):
            return "None"
    return None


def _doc_nonreturning_contract_annotation(docstring: str) -> str | None:
    """Resolve helpers whose documented execution path always raises.

    ``NoReturn`` is more accurate than ``None`` for abstract/error helpers:
    callers cannot observe a successful value at all.  Require an explicit
    OUTPUT/prose clause beginning with ``raise`` and reject conditional
    branches, so validators that return normally for valid input remain
    unresolved or use their separate void contract.
    """
    values = _doc_output_values(docstring)
    candidates = values or (docstring,)
    for value in candidates:
        text = re.sub(r"\s+", " ", value.replace(chr(96), "")).strip()
        if re.match(r"^(?:raise|raises)\b", text, re.IGNORECASE) and not re.search(
            r"\b(?:if|unless|otherwise|or|return|returns)\b", text, re.IGNORECASE
        ):
            return "NoReturn"
    return None


def _doc_copy_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
) -> str | None:
    """Resolve conventional shallow/deep copy methods to the receiver type.

    Python's copy protocol preserves the concrete class unless a type opts
    into a conversion.  Sage's public ``copy``/``deepcopy`` methods document
    that same invariant in their summary.  Restricting this rule to the
    conventional method names and an explicit copy verb avoids mistaking
    unrelated prose such as ``copy_from`` or ``copy ... as a NumPy array`` for
    a receiver-preserving result.
    """
    if owner_name is None or node.name not in {"copy", "deepcopy"}:
        return None
    normalized = summary.replace(chr(96), "")
    if not re.search(r"\b(?:copy|deepcopy)\b", normalized, re.IGNORECASE):
        return None
    if re.search(r"\b(?:from|into|as|convert|conversion|numpy|array)\b", normalized, re.IGNORECASE):
        return None
    if not re.match(r"^(?:return|create|make|construct|clone)\b", normalized, re.IGNORECASE):
        return None
    return "Self"


def _doc_identity_return_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    docstring: str,
    owner_name: str | None,
) -> str | None:
    """Resolve an unconditional documentation promise to return ``self``.

    A few Sage parent/value objects state identity explicitly in prose
    (``This just returns self`` or ``Return self, since ...``) without an
    OUTPUT role.  Restrict the rule to an unconditional identity phrase and
    reject conversions (``as ...``), arithmetic, and alternate return paths.
    """
    if owner_name is None:
        return None
    prose = re.split(r"\n\s*(?:EXAMPLES|TESTS)\s*:?\s*$", docstring, maxsplit=1, flags=re.IGNORECASE)[0]
    normalized = re.sub(r"\s+", " ", prose.replace(chr(96), "")).strip()
    if re.search(
        r"\b(?:just|simply|always|only)\s+returns?\s+(?:self|this)\b",
        normalized,
        re.IGNORECASE,
    ):
        if not re.search(r"\b(?:or|otherwise|depending|if)\b", normalized, re.IGNORECASE):
            return "Self"
    first = normalized.split(". ", 1)[0].strip()
    if re.match(r"^(?:return|returns)\s+self\b", first, re.IGNORECASE):
        if not re.search(
            r"\b(?:as|in|acted|divided|multiplied|plus|minus|raised|base\s+changed)\b",
            first,
            re.IGNORECASE,
        ):
            return "Self"
    return None


def _doc_classcall_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
) -> str | None:
    """Resolve normalization-only classcall hooks to their concrete class.

    Sage's ``ClasscallMetaclass`` hooks normally canonicalize constructor
    arguments and then invoke ``cls``.  A subset are genuine factories that
    choose a parent/element subclass; their documentation names that
    dispatch explicitly and must remain unresolved.  Restrict this contract
    to the documented unique-representation/cached-instance invariant and
    reject parent/factory/dispatch wording before exposing ``Self``.
    """
    if owner_name is None or node.name not in {"__classcall__", "__classcall_private__"}:
        return None
    # ``MatrixSpace`` is a parent/factory whose classcall canonicalization
    # returns the concrete parent singleton produced by Sage's category
    # machinery.  Keep this source-defined result instead of the generic
    # ``Self`` fallback so constructor calls expose the usable parent API.
    if owner_name.casefold() == "matrixspace":
        return "'sage.matrix.matrix_space.MatrixSpace_with_category'"
    normalized = summary.replace(chr(96), "")
    # Element classcalls commonly return an implementation selected by a
    # parent, so ``Self`` would erase the actual dynamic dispatch.  An explicit
    # cached/canonical instance contract is the exception: it proves that the
    # declaring implementation is returned unchanged.
    if re.search(r"(?:Element|element)$", owner_name) and not (
        re.search(r"(?:\b(?:cached?|cache|canonical)\s+(?:an?\s+)?(?:instance|object)\b|\(?cached\)?\s+instance\b|\breturn\s+cls\s*\(\s*\))", normalized, re.IGNORECASE)
        and re.search(r"\b(?:unique representation|canonical parameters|canonicalize|standardize)\b", normalized, re.IGNORECASE)
    ):
        return None
    if re.match(
        r"^normalize\s+(?:the\s+)?(?:input|inputs|arguments|initargs|constructor\s+arguments)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(r"\b(?:into\s+a\s+set|class|object|another|parent|delegate)\b", normalized, re.IGNORECASE):
        return "Self"
    if re.match(r"^classcall\s+to\s+mend\s+the\s+input\.?$", normalized, re.IGNORECASE):
        return "Self"
    # Canonicalization hooks that explicitly cache and return an instance of
    # the declaring class preserve that concrete class.  This covers the
    # common ``return cls()``/canonical-instance wording while still
    # excluding factories that dispatch to another parent or subclass.
    if re.search(
        r"\b(?:cached?|cache|canonical)\s+(?:an?\s+)?(?:instance|object)\b|"
        r"\bcache\s+the\s+result\b|"
        r"\breturn\s+cls\s*\(\s*\)",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:factory|appropriate parent|correct parent|return the parent|parent object|"
        r"dispatch|delegate|subclass|element class|depending on|alias for)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    # Enumerated/combinatorial element classes document the canonicalization
    # invariant as "created ... are the same" and explicitly identify the
    # resulting instance with a class role.  The wording proves a receiver
    # class result without relying on the many concrete class names involved.
    if re.search(r"\b(?:are|is)\s+the\s+same\b", normalized, re.IGNORECASE) and re.search(
        r"\binstances?\s+of\s+.*:class:", normalized, re.IGNORECASE
    ) and not re.search(
        r"\b(?:factory|appropriate parent|correct parent|dispatch|delegate|subclass|depending on)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    # Unique-representation hooks also describe their normalization without
    # the words ``canonical parameters`` (for example ``normalization of
    # arguments`` or ``making the input hashable``).  These phrases prove
    # that the declaring class is the result, while factory/dispatch prose is
    # excluded below so parent-dependent constructors remain UNKNOWN.
    if re.search(
        r"\b(?:normalization|normalisation)\s+of\s+(?:the\s+)?(?:input|arguments?|parameters?)\b|"
        r"\bnormalize\s+(?:the\s+)?input\s+for\s+unique\s+representation\b|"
        r"\bmaking\s+(?:the\s+)?input\s+hashable\b|"
        r"\bonly\s+ever\s+constructed\s+as\s+(?:an?\s+)?(?:instance|object)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:factory|appropriate parent|correct parent|return the parent|parent object|"
        r"dispatch|delegate|subclass|element class|depending on|alias for)\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Self"
    if not re.search(r"\b(?:unique representation|canonical parameters|canonicalize|standardize)\b", normalized, re.IGNORECASE):
        return None
    if re.search(
        r"\b(?:factory|appropriate parent|correct parent|return the parent|parent object|dispatch|delegate|subclass|element class|correct parent|depending on)\b",
        normalized,
        re.IGNORECASE,
    ):
        return None
    return "Self"


def _doc_parent_element_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
    owner_bases: tuple[str, ...] | None = None,
) -> str | None:
    """Encode parent-to-element dispatch without leaking a protocol base.

    Sage parents are deliberately heterogeneous: ``R.gen()``, ``R.zero()``
    and ``R(x)`` return the implementation selected by the *parent instance*,
    not the parent class itself.  The old generated stubs left these methods
    untyped because a single concrete class cannot represent that dispatch.
    This source-level contract records the relationship as
    ``ParentElement[Self]``.  ``SageTypeLowering`` resolves it from a concrete
    receiver's already-proven child contracts; if no such proof exists it
    stays unresolved instead of falling back to ``Element``/``Any``.

    The matcher is intentionally semantic rather than a module allow-list.  A
    method is accepted only when its summary explicitly says it constructs or
    returns an element belonging to ``self``.  Element implementations are
    excluded: their ``gen`` methods return a generator of the element itself,
    not an element *of the element's parent*.
    """
    if not owner_name or re.search(r"(?:Element|element)$", owner_name):
        return None
    normalized = summary.replace(chr(96), "")
    owner_boundary_text = " ".join((owner_name, *(owner_bases or ())))
    # Morphism-like objects map an input into their codomain.  Sage uses a
    # deliberately heterogeneous hierarchy here (crystal morphisms,
    # derivations, homomorphisms, actions, and coercions), so the stable
    # contract is the relation to ``self.codomain()`` rather than a shared
    # public element base.  Require both the semantic owner role and the
    # documented image/value wording; ordinary element ``image`` helpers do
    # not satisfy this guard.
    if re.search(
        r"(?:morphism|homomorphism|homset|derivation|coercion|isometry|automorphism|action|map)",
        owner_name,
        re.IGNORECASE,
    ) and re.search(
        r"\b(?:image|value|result)\b[^.]{0,100}\b(?:under|by)\s+(?:this|self)\b|"
        r"\b(?:image|value|result)\b\s+of\s+``?(?:x|val|element|self)``?\s+under\s+(?:this|self)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:or|either|depending|unless|otherwise|if|when|preimage|inverse)\b",
        normalized,
        re.IGNORECASE,
    ):
        return RELATED_ELEMENT_CONTRACTS["codomain"]
    # A morphism-like callable is, by definition, evaluated in its codomain.
    # Generated stubs often phrase this as “evaluate/apply this morphism”
    # without repeating the word ``image``; retain the codomain relation
    # instead of publishing a shared map or element base.
    if re.search(
        r"(?:morphism|homomorphism|homset|derivation|coercion|isometry|automorphism|action|map)",
        owner_name,
        re.IGNORECASE,
    ) and node.name in {"__call__", "_call_", "_act_", "_act_on_", "apply", "evaluate"} and re.search(
        r"\b(?:evaluate|apply|call|act|action)\b[^.]{0,100}\b(?:morphism|homomorphism|map|action|self|this)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:or|either|depending|unless|otherwise|if|when|preimage|inverse|tuple|list)\b",
        normalized,
        re.IGNORECASE,
    ):
        return RELATED_ELEMENT_CONTRACTS["codomain"]
    if (
        node.name == "singular_vector"
        and re.search(r"\b(?:vector|element)\b.*\bcodomain\b", normalized, re.IGNORECASE)
        and re.search(r"(?:homset|homspace|morphism|module)", owner_name, re.IGNORECASE)
        and not re.search(r"\b(?:or|either|depending|otherwise|if|when)\b", normalized, re.IGNORECASE)
    ):
        return RELATED_ELEMENT_CONTRACTS["codomain"]
    # Morphisms/maps and algebraic objects often document a value as an
    # element of a *related* parent instead of ``self`` itself.  Preserve that
    # relationship so the IDE can resolve the concrete element class from the
    # receiver's ``codomain()``, ``domain()``, ``base_ring()`` or ``ambient()``
    # contract.  Conditional alternatives remain fail-closed.
    if not re.search(r"\b(?:or|either|depending|unless|otherwise|if|when)\b", normalized, re.IGNORECASE):
        relation_patterns = (
            (r"\belement\s+(?:of|in|from)\s+(?:the\s+)?base\s+field\b", "base field"),
            (r"\belement\s+(?:of|in|from)\s+(?:the\s+)?base\s+ring\b", "base ring"),
            (r"\belement\s+(?:of|in|from)\s+(?:the\s+)?codomain\b|\bbase\s+codomain\b", "codomain"),
            (r"\belement\s+(?:of|in|from)\s+(?:the\s+)?domain\b", "domain"),
            (r"\belement\s+(?:of|in|from)\s+(?:the\s+)?ambient\s+(?:space|module|ring|group|object)\b", "ambient"),
        )
        for pattern, relation in relation_patterns:
            if re.search(pattern, normalized, re.IGNORECASE):
                return RELATED_ELEMENT_CONTRACTS[relation]
    # Many parent implementations name the surrounding algebra/ring/module
    # rather than spelling out ``of self`` (for example “an element of the
    # Steenrod algebra”).  The owner class supplies the parent boundary while
    # the documented element noun supplies the construction relation.  Keep
    # this generic across Sage parent families and exclude coefficient/value
    # prose, which is not an element constructor.
    if re.search(
        r"\b(?:an?|the)\s+element\s+(?:of|in|from)\b[^.]{0,100}\b(?:algebra|ring|field|module|group|monoid|semigroup|space|basis)\b",
        normalized,
        re.IGNORECASE,
    ) and re.search(
        r"(?:algebra|ring|field|module|group|monoid|semigroup|space|basis|parent|free.?module|combinatorial)",
        owner_boundary_text,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:coefficient|coordinate|component|index|label|value|morphism|homomorphism|tuple|list|sequence)\b",
        normalized,
        re.IGNORECASE,
    ):
        return PARENT_ELEMENT_CONTRACT
    if re.search(
        r"\b(?:element|generator|non[- ]?residue|unit)\b[^.]{0,80}\b(?:of|in|from)\s+(?:this\s+|the\s+)?self\b",
        normalized,
        re.IGNORECASE,
    ) and re.search(
        r"(?:algebra|ring|field|module|group|monoid|semigroup|space|parent|basis|free.?module|combinatorial)",
        owner_boundary_text,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:coefficient|coordinate|component|index|label|value|morphism|homomorphism|tuple|list|sequence)\b",
        normalized,
        re.IGNORECASE,
    ):
        return PARENT_ELEMENT_CONTRACT
    same_parent_getitem_branches = (
        node.name == "__getitem__"
        and re.search(r"\b(?:lie\s+)?bracket\b", normalized, re.IGNORECASE)
        and re.search(r"\b(?:element|item)\s+of\s+(?:this\s+)?self\b", normalized, re.IGNORECASE)
    )
    # A guard such as “if it exists” still returns an element (or raises); it
    # is not a value-level union.  Reject only wording that explicitly offers
    # another result family.
    if re.search(r"\b(?:or|either|depending|unless|otherwise)\b", normalized, re.IGNORECASE) and not same_parent_getitem_branches:
        return None
    if same_parent_getitem_branches:
        return PARENT_ELEMENT_CONTRACT
    # Facade parents (notably finite posets) intentionally accept and return
    # plain Python objects.  They are not Sage ``ParentElement`` dispatch and
    # must stay unresolved instead of being forced through the symbolic
    # element contract.
    if re.search(
        r"\b(?:facade|plain\s+python\s+objects?|non[- ](?:sage\s+)?elements?|non[- ]sage\s+objects?)\b",
        normalized,
        re.IGNORECASE,
    ):
        return None

    # Canonical parent protocols.  These names are only considered when the
    # documentation also carries the parent/element relation below; names
    # alone are not evidence because Sage uses ``one``/``zero`` for indices,
    # basis keys and scalar helper objects too.
    parent_element_phrase = re.search(
        r"\belement\s+(?:of|in|from)\s+(?:this\s+|the\s+)?self(?!\s*\.[A-Za-z_])(?!\s*')"
        r"|\bobject\s+of\s+the\s+parent\s+of\s+self(?!\s*\.[A-Za-z_])(?!\s*')",
        normalized,
        re.IGNORECASE,
    )
    if parent_element_phrase is not None:
        if "element" in normalized.casefold() and node.name not in {"object", "element_class"}:
            return PARENT_ELEMENT_CONTRACT
        if node.name in {"_an_element_", "_element_constructor_", "__call__", "an_element", "from_vector", "from_coordinates", "retract", "zero", "one", "identity", "unit", "random_element", "gen"}:
            return PARENT_ELEMENT_CONTRACT

    # A large part of Sage's parent API uses the same contract but phrases it
    # as ``Convert x into self`` or ``Construct an element of this ring``.
    # These are unambiguous construction statements even when the generated
    # OUTPUT block is absent.  Keep the rejection list conservative: an
    # ``index``/``coefficient``/``coordinate`` is a value *of* an element, not
    # an element created by the parent, and morphisms/maps have their own
    # result classes.
    construction_words = re.search(
        r"\b(?:convert|coerce|construct|create|build|return|retract)\b.*\b(?:into|in|of|from)\s+(?:this\s+|the\s+)?(?:self|this\s+)?",
        normalized,
        re.IGNORECASE,
    )
    element_noun = re.search(r"\b(?:an?\s+)?(?:basis\s+)?elements?\b", normalized, re.IGNORECASE)
    bad_value_noun = re.search(
        r"\b(?:index|indices|coefficient|coordinate|component|entry|value|label|name|morphism|homomorphism|map|tuple|list|sequence)\b",
        normalized,
        re.IGNORECASE,
    )
    if node.name in {"_element_constructor_", "_an_element_", "an_element", "retract", "__call__"}:
        if re.search(r"\b(?:convert|coerce)\b.*\binto\s+(?:this\s+|the\s+)?self\b", normalized, re.IGNORECASE):
            return PARENT_ELEMENT_CONTRACT
        if (
            node.name == "__call__"
            and re.search(r"\bcoerc(?:e|ed|ion)\b.*\b(?:this|the)\s+(?:free\s+)?(?:monoid|ring|field|algebra|module|group|space)\b", normalized, re.IGNORECASE)
            and re.search(r"(?:monoid|ring|field|algebra|module|group|space|parent|free.?module|combinatorial)", owner_boundary_text, re.IGNORECASE)
            and not re.search(r"\b(?:or|either|depending|otherwise|if|when|none)\b", normalized, re.IGNORECASE)
        ):
            return PARENT_ELEMENT_CONTRACT
        if element_noun and not bad_value_noun and (
            construction_words
            or re.search(r"\b(?:element|basis\s+element)\b.*\b(?:self|this\s+(?:ring|algebra|space|group|magma|monoid|semigroup|module|order))\b", normalized, re.IGNORECASE)
        ):
            return PARENT_ELEMENT_CONTRACT

    # ``gen`` is a parent protocol in Sage (rings, groups, algebras and
    # bases).  Requiring a generator/basis noun prevents sequence helpers and
    # unrelated ``gen`` utilities from being assigned an element contract.
    if node.name == "gen" and re.search(
        r"\b(?:generator|basis\s+(?:element|vector)|hec(?:ke)?\s+operator)\b",
        normalized,
        re.IGNORECASE,
    ) and not bad_value_noun:
        return PARENT_ELEMENT_CONTRACT

    # Coxeter/Weyl-style parents expose a distinguished group element for a
    # simple reflection.  The singular operation is parent-element dispatch;
    # the plural ``simple_reflections`` collections remain intentionally
    # unresolved because their outer container varies by implementation.
    if node.name in {"simple_reflection", "reflection"} and re.search(
        r"\bsimple\s+reflection\b", normalized, re.IGNORECASE
    ) and re.search(r"(?:group|coxeter|weyl|root|cartan)", owner_boundary_text, re.IGNORECASE):
        return PARENT_ELEMENT_CONTRACT

    # Root/weight-space parents use a family of singular accessors whose
    # names are themselves the mathematical contract (``simple_root(i)``,
    # ``fundamental_weight(i)``, ``positive_coroot(i)``).  Their result is one
    # element of the receiver's ambient parent; the plural accessors remain
    # collection-valued and are intentionally not matched.
    if re.fullmatch(
        r"(?:simple|fundamental|positive|negative)_(?:root|coroot|weight)",
        node.name,
        re.IGNORECASE,
    ) and re.search(r"(?:ambient|root|weight|cartan|weyl)", owner_boundary_text, re.IGNORECASE):
        return PARENT_ELEMENT_CONTRACT

    # Lie-algebra parents expose the indexed generators ``e(i)``/``f(i)`` as
    # individual parent elements.  The owner role plus the documented
    # generator wording distinguishes them from unrelated one-letter helper
    # functions and from plural generator collections.
    if re.fullmatch(r"[ef]", node.name, re.IGNORECASE) and re.search(
        r"\bgenerator", normalized, re.IGNORECASE
    ) and re.search(r"(?:lie|algebra)", owner_boundary_text, re.IGNORECASE):
        return PARENT_ELEMENT_CONTRACT

    # Basis-algebra helpers construct one concrete parent element even when
    # the source names the operation rather than saying ``element of self``.
    # Keep this tied to the explicit basis/monomial result noun; generic
    # ``product``/``term`` utilities remain unresolved.
    if node.name in {"bracket", "bracket_on_basis", "product_on_basis", "monomial", "term"} and re.search(
        r"\b(?:bracket|product|monomial|term)\b.*\b(?:basis\s+elements?|monomials?|indexed|coefficient)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(r"\b(?:basis\s+indices?|index\s+set|list|tuple|dictionary|map)\b", normalized, re.IGNORECASE):
        return PARENT_ELEMENT_CONTRACT

    # Identity/random protocols conventionally return a member of the
    # receiver's parent.  Require the result noun (or an explicit ``self``)
    # so ``one_basis`` and scalar/count helpers remain unresolved.
    if node.name in {"zero", "one", "identity", "unit", "random_element"}:
        if re.search(r"\b(?:zero|one|identity|neutral|unit|random)\s+element\b", normalized, re.IGNORECASE) or re.search(
            r"\b(?:zero|one|identity|neutral|unit|random)\b.*\b(?:of|in)\s+(?:this\s+|the\s+)?(?:self|ring|algebra|group|magma|monoid|semigroup|module|space|order)\b",
            normalized,
            re.IGNORECASE,
        ):
            return PARENT_ELEMENT_CONTRACT

    # Indexing a parent by a basis/key is the same dynamic dispatch as
    # ``R(x)``.  Element implementations are excluded because their
    # ``__getitem__`` usually exposes a coefficient/coordinate instead.
    if node.name == "__getitem__" and re.search(
        r"\b(?:basis\s+item|codeword|shifting\s+operator)\b", normalized, re.IGNORECASE
    ) and re.search(
        r"(?:algebra|ring|field|module|code|space|parent|basis|free.?module|combinatorial)",
        owner_boundary_text,
        re.IGNORECASE,
    ) and not re.search(
        r"\b(?:coefficient|coordinate|component|value|list|tuple|cache)\b",
        normalized,
        re.IGNORECASE,
    ):
        return PARENT_ELEMENT_CONTRACT
    if node.name == "__getitem__" and re.search(
        r"\b(?:basis\s+element|element)\b.*\b(?:self|this|parent|algebra|ring|group|space)\b",
        normalized,
        re.IGNORECASE,
    ) and not bad_value_noun:
        return PARENT_ELEMENT_CONTRACT
    if node.name == "__getitem__" and re.search(r"\bbasis\s+element\b", normalized, re.IGNORECASE) and not re.search(
        r"\b(?:coefficient|coordinate|component|value)\b", normalized, re.IGNORECASE
    ):
        return PARENT_ELEMENT_CONTRACT

    # ``some_elements`` is allowed to be lazy.  Preserve the outer iterator
    # protocol when the docs explicitly say it yields elements instead of
    # promising an eager tuple.
    if node.name == "some_elements" and re.search(
        r"\b(?:generator|iterator)\b.*\b(?:element|self)\b", normalized, re.IGNORECASE
    ):
        return f"Iterator[{PARENT_ELEMENT_CONTRACT}]"
    if node.name == "some_elements" and re.search(
        r"\bsome\s+elements?\s+of\s+self\b", normalized, re.IGNORECASE
    ):
        return PARENT_ELEMENT_TUPLE_CONTRACT

    # Sage's category Parent protocol itself is the final structural proof
    # for these names.  Generated docstrings are often only examples (or a
    # translated one-line description), so requiring a particular noun here
    # would leave hundreds of genuinely parent-created values UNKNOWN.  The
    # exclusions are infrastructure objects whose same-named helpers are
    # factories/maps/iterators rather than parent element constructors.
    infrastructure_owner = re.search(
        r"(?:iterator|sequence|builder|factory|database|functor|morphism|map|function|generator)$",
        owner_name,
        re.IGNORECASE,
    )
    # A mathematical parent can legitimately end in ``Generator`` (for
    # example ``...AlgebraWithPrimitiveGenerator``).  Treat the suffix as
    # infrastructure only when the owner has no parent-like vocabulary; this
    # keeps the rule semantic and avoids a class-name allow-list.
    if infrastructure_owner and re.search(
        r"(?:algebra|ring|field|module|group|magma|monoid|semigroup|space|parent|basis)",
        owner_name,
        re.IGNORECASE,
    ) and not re.search(
        r"(?:iterator|sequence|builder|factory|database|functor|morphism|map|function)",
        owner_name,
        re.IGNORECASE,
    ):
        infrastructure_owner = None
    if not infrastructure_owner and node.name in {
        "_element_constructor_",
        "_an_element_",
        "an_element",
        "gen",
        "zero",
        "one",
        "identity",
        "unit",
        "random_element",
    }:
        return PARENT_ELEMENT_CONTRACT

    if not infrastructure_owner and node.name == "retract":
        # Parent/submodule retractions are coercions into the receiver's
        # element parent.  The same relation also covers quotient and
        # ambient-space implementations; it is deliberately not applied to
        # map/functor infrastructure above.
        return PARENT_ELEMENT_CONTRACT

    if not infrastructure_owner and node.name == "some_elements":
        # Implementations vary between an eager sample tuple and a generator;
        # the documented protocol guarantees only an iterable of elements.
        return f"Iterator[{PARENT_ELEMENT_CONTRACT}]"

    # Parent implementations use the private ``_some_elements_`` hook to
    # provide a lazy sample stream.  The concrete yielded parent varies, but
    # the Python-level generator protocol is exact and is enough for IDE
    # iteration/completion without inventing a common Sage element class.
    if node.name == "_some_elements_" and re.search(
        r"\b(?:generate|return|yield)\b.*\b(?:some|sample)\s+(?:points?|elements?)\b.*\bself\b",
        normalized,
        re.IGNORECASE,
    ):
        return "Iterator"

    if not infrastructure_owner and node.name == "product_on_basis" and re.search(
        r"\bproduct\b.*\bbasis\s+elements?", normalized, re.IGNORECASE
    ) and re.search(
        r"(?:algebra|ring|field|module|magma|monoid|semigroup|space|parent|basis|free.?module|combinatorial)",
        owner_boundary_text,
        re.IGNORECASE,
    ) and not re.search(r"\bbasis\s+indices?\b", normalized, re.IGNORECASE):
        return PARENT_ELEMENT_CONTRACT

    # Algebra parents expose generators through a Family (occasionally a
    # plain list in small finite implementations).  Keep the outer contract
    # explicit without guessing the family key/value element type.
    if not infrastructure_owner and node.name == "algebra_generators" and re.search(
        r"\bgenerator", normalized, re.IGNORECASE
    ):
        return "'sage.sets.family.Family | list'"

    if not infrastructure_owner and node.name == "gens" and re.search(
        r"\bgenerator|\bbasis", normalized, re.IGNORECASE
    ):
        return "tuple"

    # Some parent docs omit the words ``of self`` but make the relationship
    # explicit in the method's conventional role (for example “return the
    # i-th generator of self” or “return the zero element of self”).
    if node.name in {"zero", "one", "identity", "unit", "random_element"} and re.search(
        r"\b(?:zero|one|identity|neutral|unit|random)\s+element\b.*\bself\b",
        normalized,
        re.IGNORECASE,
    ):
        return PARENT_ELEMENT_CONTRACT
    # Crystal/module parents expose one distinguished module generator (or
    # highest-weight element).  This is a parent-to-element dispatch result;
    # keep it relational so the active concrete crystal element is selected
    # from the receiver rather than publishing a shared Crystal base.
    if (
        node.name == "module_generator"
        and re.search(r"\b(?:module\s+generator|highest\s+weight\s+element)\b", normalized, re.IGNORECASE)
        and not re.search(r"\b(?:list|tuple|family|generator\s+set)\b", normalized, re.IGNORECASE)
        and not re.search(r"(?:Element|element)$", owner_name, re.IGNORECASE)
    ):
        return PARENT_ELEMENT_CONTRACT
    if node.name == "gen" and re.search(
        r"\b(?:generator|basis\s+element)\b.*\bself\b",
        normalized,
        re.IGNORECASE,
    ):
        return PARENT_ELEMENT_CONTRACT
    # Singular generator accessors and basis-operation hooks are parent
    # protocols even when generated docs contain only an examples block.  A
    # singular ``*_generator`` or ``*_on_basis`` result is one element of the
    # declaring algebra/module; plural ``*_generators`` and index helpers are
    # deliberately excluded because they return collections or labels.
    if not infrastructure_owner and re.search(
        r"(?:^|_)(?:algebra|module|coalgebra|lie|basis)?_?generator$",
        node.name,
        re.IGNORECASE,
    ) and re.search(
        r"(?:algebra|ring|field|module|magma|monoid|semigroup|space|parent|basis|free.?module|combinatorial)",
        owner_boundary_text,
        re.IGNORECASE,
    ):
        return PARENT_ELEMENT_CONTRACT
    if not infrastructure_owner and re.search(
        r"(?:^|_)(?:product|bracket|coproduct|antipode|action)_on_basis$",
        node.name,
        re.IGNORECASE,
    ) and re.search(
        r"(?:algebra|ring|field|module|magma|monoid|semigroup|space|parent|basis|free.?module|combinatorial)",
        owner_boundary_text,
        re.IGNORECASE,
    ) and not re.search(r"\b(?:index|indices|list|tuple|dictionary|map)\b", normalized, re.IGNORECASE):
        return PARENT_ELEMENT_CONTRACT
    if node.name in {"_an_element_", "an_element"} and re.search(
        r"\b(?:typical|particular|generic|some|an?)\s+element\b.*\bself\b",
        normalized,
        re.IGNORECASE,
    ):
        return PARENT_ELEMENT_CONTRACT
    return None


def _doc_protocol_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None = None,
) -> str | None:
    """Materialize Python data-model contracts missing from generated stubs.

    These protocols are independent of Sage's parent/element hierarchy and
    therefore safe to apply across the whole index.  They remove a large,
    noisy class of UNKNOWN returns without pretending that a dynamic
    ``__getitem__`` or ``__next__`` value has a universal Sage class.
    """
    name = node.name
    # Equality/order methods are covered by ``PROTOCOL_RETURNS`` during the
    # normal pass; this fallback handles the remaining stable predicate
    # protocols when doc-based inference runs in isolation.
    if name in {"__contains__", "__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"}:
        return "bool"
    if name in {"__bool__"}:
        return "bool"
    if name in {"__len__", "__index__", "__hash__"}:
        return "int"
    # Non-dunder hash helpers are still constrained by Python's hash
    # protocol.  The explicit summary keeps this rule semantic and avoids
    # misclassifying unrelated methods merely named ``hash``.
    if name in {"_hash_", "stable_hash"} and re.match(
        r"^(?:(?:return|returns)\s+)?(?:a|the)\s+hash\s+value\b", summary, re.IGNORECASE
    ):
        return "int"
    # ``_repr_pretty_`` receives a pretty-printer and writes into it; Sage's
    # implementations do not return the rendered object.  Restrict to the
    # canonical summary so similarly named formatting helpers remain
    # unresolved when they produce a value.
    if name == "_repr_pretty_" and re.match(
        r"^for\s+pretty\s+printing\b", summary, re.IGNORECASE
    ):
        return "None"
    if name == "_repr_option" and re.match(
        r"^metadata about the\b.*_?repr", summary, re.IGNORECASE
    ):
        return "bool"
    if name == "__bytes__":
        return "bytes"
    if name == "__iter__":
        return "Iterator"
    # Context-manager entry hooks normally return the concrete context
    # object itself.  Keep this semantic rather than assigning ``Self`` to
    # temporary-directory helpers that explicitly return a path or process
    # state.  A class named ``*Context`` with an examples-only docstring is
    # still an unambiguous context protocol implementation.
    if name == "__enter__":
        normalized = re.sub(r"\s+", " ", (summary or "").replace(chr(96), "")).strip()
        if re.search(r"\bguard(?:ing)?\s+clone\s+protocol\b", normalized, re.IGNORECASE):
            return "Self"
        if re.search(r"\b(?:temporary\s+director(?:y|ies)|directory returned|path)\b", normalized, re.IGNORECASE):
            return "str"
        if not re.search(
            r"\b(?:temporary\s+director(?:y|ies)|current\s+pid|path|flush\s+the\s+standard)\b",
            normalized,
            re.IGNORECASE,
        ) and re.search(
            r"\b(?:with[- ]block|context|context\s+manager|enter(?:ing)?\s+the)\b",
            normalized,
            re.IGNORECASE,
        ):
            return "Self"
        if owner_name and re.search(
            r"(?:context|assuming|hold_class|withproof|localvars|redirection|randstate|temporaryvariables|database|disabled|children|clone|atexit)$",
            owner_name,
            re.IGNORECASE,
        ) and normalized.casefold() in {"", "examples::", "tests::"}:
            return "Self"
        # Side-effect-only context hooks often have a one-line summary (for
        # example storing the current PID) rather than the word ``context``.
        # Their owner role still identifies a context manager and the Python
        # protocol conventionally returns the concrete manager itself.
        if owner_name and re.search(
            r"(?:context|database|disabled|children|clone|atexit)$",
            owner_name,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:temporary\s+director(?:y|ies)|directory returned|path)\b", normalized, re.IGNORECASE):
            return "Self"
    # Plot primitives render directly onto a supplied matplotlib subplot and
    # cache precomputation state; both hooks are side-effect-only by Sage's
    # protocol.  The method names are shared across implementations, so this
    # rule remains generic and does not depend on a class inventory.
    if name in {"_render_on_subplot", "_precompute"}:
        return "None"
    # ``str`` is Sage's explicit textual conversion helper (the dunder
    # ``__str__`` case is handled above).  Every implementation returns a
    # native Python string, independent of the underlying mathematical type.
    if name == "str":
        return "str"
    if name == "_instancedoc_" and re.match(
        r"^(?:return|provide|retrieve|give)\b.*\b(?:doc|string|help|documentation)\b",
        summary,
        re.IGNORECASE,
    ):
        return "str"
    # ``_instancedoc_`` is the protocol behind Sage's dynamic ``__doc__``
    # values.  Generated stubs often contain only an EXAMPLES/TESTS block,
    # but the successful protocol result is still textual; exceptions are
    # control flow and do not change the return type.
    if name == "_instancedoc_":
        return "str"
    if name == "_sage_input_" and re.search(
        r"\b(?:sage command|expression)\b.*\b(?:reconstruct|reproduce)\b",
        summary,
        re.IGNORECASE,
    ):
        return "str"
    if name == "_magma_init_" and re.search(
        r"(?:\b(?:magma|mag(m|a))\b.*\b(?:version|representation|convert|initializ)|"
        r"\b(?:convert|conversion|used\s+in)\w*\b.*\b(?:magma|mag(m|a))\b)",
        summary,
        re.IGNORECASE,
    ):
        return "str"
    # Every Magma initialization hook serializes the Sage object to a
    # textual constructor expression; some generated summaries only say
    # ``return a string`` and omit the backend name.
    if name == "_magma_init_" and re.search(
        r"\breturn(?:s)?\s+(?:a|an|the)\s+string\b", summary, re.IGNORECASE
    ):
        return "str"
    if name == "_start" and not re.search(
        r"\b(?:return|returns|object|value|process)\b",
        summary,
        re.IGNORECASE,
    ):
        return "None"
    # Sage's rich text protocols have fixed outer result classes even when
    # the receiver and rendered payload are dynamic.  The category naming
    # hook likewise always supplies the textual noun phrase consumed by
    # ``_repr_``.  These are protocol contracts, not receiver-specific
    # guesses, so they apply uniformly across the generated stubs.
    if name == "_print_latex_":
        return "str"
    if name == "_ascii_art_":
        return "'sage.typeset.ascii_art.AsciiArt'"
    if name == "_unicode_art_":
        return "'sage.typeset.unicode_art.UnicodeArt'"
    if name == "_repr_object_names":
        return "str"
    if name.startswith("_inplace_"):
        return "None"
    if name in {"_repr_type", "_repr_term", "_equality_symbol", "_sage_src_"}:
        return "str"
    if name in {"_read_in_file_command", "_assign_symbol", "_true_symbol", "_install_hints", "_interface_init_"}:
        return "str"
    if name == "_repr_defn":
        return "str"
    if name == "_allowed_options":
        return "dict"
    if name == "super_categories":
        return "list"
    if name in {"positive_roots", "negative_roots"}:
        return "list"
    if name == "_integer_":
        return "'sage.rings.integer.Integer'"
    if name == "_rational_":
        return "'sage.rings.rational.Rational'"
    if name == "_mpfr_":
        return "'sage.rings.real_mpfr.RealNumber'"
    if name == "_real_double_":
        return "'sage.rings.real_double.RealDoubleElement'"
    # Some generated Cython docs use a summary-only protocol spelling, e.g.
    # ``Return a boolean indicating ...`` for non-dunder predicates.  Keep
    # this fallback narrow and anchored so payload descriptions do not become
    # accidental booleans.
    if name.startswith(("is_", "has_", "can_", "contains_", "exists_")) and re.match(
        r"^(?:return\s+)?(?:a\s+)?boolean\b", summary, re.IGNORECASE
    ):
        return "bool"
    return None


def _doc_dynamic_interface_element_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    docstring: str,
    class_index: dict[str, tuple[str, ...]] | None,
    owner_name: str | None,
) -> str | None:
    """Resolve an interface's concrete wrapper element from its own module.

    CAS interfaces intentionally expose dynamic attributes, but their wrapper
    objects are not arbitrary: ``Magma`` creates ``MagmaElement`` and
    ``Singular`` creates ``SingularElement``.  The global class index can also
    contain same-named ABC shims, so select the unique class in the matching
    ``sage.interfaces.<backend>`` module.  This is a structural relation, not
    a per-method allow-list, and is used only when the documentation explicitly
    names that wrapper (or says “a new <backend> element”).
    """
    if not class_index or not owner_name or owner_name.casefold().endswith("element"):
        return None
    owner_stem = re.sub(r"(?:Function|Class)$", "", owner_name, flags=re.IGNORECASE)
    element_key = re.sub(r"[^a-z0-9]", "", f"{owner_name}Element".casefold())
    candidates = class_index.get(element_key, ())
    if not candidates:
        return None
    module_hint = owner_stem.casefold()
    scoped = tuple(
        value for value in candidates
        if re.search(rf"\.interfaces\.{re.escape(module_hint)}\.", value.casefold())
    )
    if len(scoped) != 1:
        return None
    annotation = f"'{scoped[0]}'"
    target = re.escape(f"{owner_name}Element")
    for output in _doc_output_values(docstring):
        compact = re.sub(r"\s+", " ", output.strip())
        # A Sphinx role is the strongest evidence.  Reject conditional
        # output descriptions so ``element or tuple`` remains unresolved.
        if re.search(r"\b(?:or|either|depending|if|otherwise|tuple|list|sequence)\b", compact, re.IGNORECASE):
            continue
        if re.search(rf":class:`(?:~)?{target}(?:<[^`]+>)?`", compact, re.IGNORECASE):
            return annotation
        # A few interface docs use plain prose instead of a role, for example
        # “OUTPUT: new Magma element”.  Keep the relation fully qualified by
        # requiring the backend name and the element noun in one phrase.
        if re.search(
            rf"\b(?:a|an|the|new)\s+{re.escape(owner_stem)}\s+(?:interface\s+)?element\b",
            compact,
            re.IGNORECASE,
        ):
            return annotation
    # Backend coercion methods consistently construct their wrapper even when
    # the older docstring omits an OUTPUT section (notably
    # ``Singular.__call__``).  The class-to-element relation above is the
    # evidence; restrict this fallback to the language-level coercion hook so
    # arbitrary dynamic backend functions remain unresolved.
    if node.name == "__call__":
        return annotation
    return None


def _doc_dynamic_interface_member_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    docstring: str,
    class_index: dict[str, tuple[str, ...]] | None,
    owner_name: str | None,
) -> str | None:
    """Resolve dynamic interface members from the backend class family.

    Sage's interpreter wrappers deliberately manufacture attributes at runtime:
    ``magma.foo`` is a ``MagmaFunction`` and ``magma(1).Factorisation`` is a
    ``MagmaFunctionElement``.  The generated stubs frequently omit an OUTPUT
    block for these methods, so ordinary documentation parsing leaves them
    unknown even though the backend module contains an exact target class.  A
    target is accepted only when the class-family name and module agree and the
    docs describe function/attribute construction; this never falls back to
    ``InterfaceElement`` or another public base.
    """
    if not class_index or not owner_name or node.name != "__getattr__":
        return None
    # A class name is all that is available at this stage.  Restrict this
    # relation to interface-like names; ordinary Sage objects may also expose
    # ``__getattr__`` but do not have a backend function-class family.
    element_owner = owner_name.endswith("Element") and not owner_name.endswith("FunctionElement")
    if owner_name in {"Interface", "InterfaceElement", "Expect", "ExpectElement"}:
        return None
    if element_owner:
        backend = owner_name[: -len("Element")]
        suffixes = ("FunctionElement", "Function")
    else:
        backend = owner_name
        suffixes = ("Function",)
    if not backend:
        return None
    owner_modules = {
        value.rsplit(".", 1)[0]
        for value in class_index.get(
            re.sub(r"[^a-z0-9]", "", owner_name.casefold()),
            (),
        )
        if ".interfaces." in value.casefold()
        and not value.casefold().split(".")[-2] == "abc"
    }
    if not owner_modules:
        return None
    candidates: list[str] = []
    for suffix in suffixes:
        key = re.sub(r"[^a-z0-9]", "", f"{backend}{suffix}".casefold())
        scoped = [
            value
            for value in class_index.get(key, ())
            if value.rsplit(".", 1)[0] in owner_modules
        ]
        # Prefer the more specific ``<Backend>FunctionElement`` family when
        # both it and ``<Backend>Function`` exist in the same module.
        if scoped:
            candidates = scoped
            break
    candidates = sorted(set(candidates))
    if len(candidates) != 1:
        return None
    annotation = f"'{candidates[0]}'"
    normalized = re.sub(chr(96), "", docstring)
    # Explicit class references are decisive.  Keep alternate result families
    # unresolved (for example Polymake properties may be values or functions).
    target_name = candidates[0].rsplit(".", 1)[-1]
    if re.search(r"\b(?:or|either|property|properties|member\s+function|value)\b", normalized, re.IGNORECASE):
        if not re.search(rf"\b{re.escape(target_name)}\b", normalized):
            return None
    if re.search(rf"\b{re.escape(target_name)}\b", normalized):
        return annotation
    if re.search(r"\b(?:function|functions|manufactur|partially\s+evaluated|attribute)\w*\b", normalized, re.IGNORECASE):
        return annotation
    return None


def _doc_dynamic_interface_index_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_index: dict[str, tuple[str, ...]] | None,
    owner_name: str | None,
) -> str | None:
    """Keep backend element indexing concrete without a base-class leak."""
    if not class_index or not owner_name or node.name != "__getitem__":
        return None
    if not owner_name.endswith("Element") or owner_name.endswith("FunctionElement"):
        return None
    backend = owner_name[: -len("Element")]
    if len(backend) < 2:
        return None
    key = re.sub(r"[^a-z0-9]", "", owner_name.casefold())
    owner_modules = {
        value.rsplit(".", 1)[0]
        for value in class_index.get(
            re.sub(r"[^a-z0-9]", "", owner_name.casefold()),
            (),
        )
        if ".interfaces." in value.casefold()
        and not value.casefold().split(".")[-2] == "abc"
    }
    candidates = tuple(
        value
        for value in class_index.get(key, ())
        if value.rsplit(".", 1)[0] in owner_modules
    )
    # The owner itself is the only backend class with this exact name.  A
    # ``Self`` result lets SageTypeLowering bind the inherited method to the
    # concrete backend wrapper at the call site.
    return "Self" if len(candidates) == 1 else None


def _doc_dynamic_interface_self_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_index: dict[str, tuple[str, ...]] | None,
    owner_name: str | None,
) -> str | None:
    """Preserve concrete wrapper identity for backend element operations."""
    if not class_index or not owner_name or not owner_name.endswith("Element"):
        return None
    if owner_name.endswith("FunctionElement") or node.name not in {"__call__", "__getitem__", "gen"}:
        return None
    owner_modules = {
        value.rsplit(".", 1)[0]
        for value in class_index.get(
            re.sub(r"[^a-z0-9]", "", owner_name.casefold()),
            (),
        )
        if ".interfaces." in value.casefold()
        and not value.casefold().split(".")[-2] == "abc"
    }
    return "Self" if len(owner_modules) == 1 else None


def _doc_numeric_self_summary_annotation(summary: str, owner_name: str | None) -> str | None:
    """Resolve elementary functions that stay in a concrete numeric domain.

    Sage's MPFR/MPFI/ARB/MPC element docs explicitly describe these results as
    the sine, logarithm, exponential, etc. of the same numeric value. For the
    concrete real/complex element classes that is a receiver-preserving
    operation, so Self is more precise than a shared numeric base. Do not
    infer from method names alone: magnitudes, arguments, coefficients and
    conversions are deliberately excluded because they change the result
    domain.
    """
    if owner_name is None or not re.fullmatch(
        r"(?:Real|Complex)(?:DoubleElement(?:_gsl)?|Number|Ball|IntervalFieldElement)|MPComplexNumber",
        owner_name,
        re.IGNORECASE,
    ):
        return None
    if not re.match(r"^(?:this function )?returns?\s+", summary, re.IGNORECASE):
        return None
    if not re.search(
        r"\b(?:self|this (?:real|complex) number|this ball|this number|complex number)\b",
        summary,
        re.IGNORECASE,
    ):
        return None
    if not re.search(
        r"\b(?:sine|cosine|tangent|secant|cosecant|cotangent|"
        r"arccosine|arcsine|arctangent|arccotangent|arccosecant|arcsecant|"
        r"exponential|logarithm|hyperbolic)\b",
        summary,
        re.IGNORECASE,
    ):
        return None
    return "Self"


def _doc_metric_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None = None,
) -> str | None:
    """Resolve source-level metric protocols shared by Sage parents.

    ``cardinality()``, ``dimension()``, ``rank()`` and ``order()`` are
    deliberately *not* receiver-preserving methods: their values depend on
    the parent and often differ between finite/infinite or native/Sage scalar
    implementations.  They do, however, have stable mathematical result
    families.  Encoding those families as explicit unions gives PyCharm a
    useful, honest completion surface while retaining every runtime branch.

    This is a method-semantic contract, not a class allow-list.  Existing
    concrete annotations and overloads win because the caller invokes this
    helper only after those passes have left a return missing.
    """
    # A cardinality is a finite Sage Integer or the singleton +Infinity.  A
    # few combinatorial implementations return a native int, so retain it in
    # the union.  Explicit infinity-only documentation can be made narrower.
    if node.name == "cardinality":
        if re.search(r"(?:\\infty|\binfinity\b|\bplus\s*infinity\b)", summary, re.IGNORECASE):
            return "'sage.rings.infinity.PlusInfinity'"
        return CARDINALITY_RETURN_UNION

    # Size/length/degree/order/height are scalar invariants across Sage's
    # combinatorial, algebraic and geometric parents.  Implementations use
    # native ``int`` or Sage ``Integer`` (with the documented infinity/None
    # branches retained), while canonical heights additionally use MPFR.
    if node.name == "size":
        if re.search(r"\b(?:none|infinity|infinite|undefined)\b", summary, re.IGNORECASE):
            return "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity | None'"
        return "'sage.rings.integer.Integer | int'"
    if node.name == "length":
        if re.search(r"\b(?:none|infinity|infinite|undefined)\b", summary, re.IGNORECASE):
            return "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity | None'"
        return "'sage.rings.integer.Integer | int'"
    if node.name == "degree":
        if re.search(r"\b(?:none|infinity|infinite|undefined)\b", summary, re.IGNORECASE):
            return "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity | None'"
        return "'sage.rings.integer.Integer | int | sage.rings.infinity.PlusInfinity'"
    if node.name == "order":
        return ORDER_RETURN_UNION
    if node.name == "height":
        return (
            "'sage.rings.integer.Integer | int | sage.rings.real_mpfr.RealNumber | "
            "sage.rings.infinity.PlusInfinity'"
        )

    # Dimensions are finite Python/Sage integers for concrete spaces and
    # +Infinity for formal/infinite parents.  The source wording is not
    # required: a method named ``dimension`` has this protocol by definition.
    if node.name == "dimension":
        if re.search(r"(?:\\infty|\binfinity\b|\bplus\s*infinity\b)", summary, re.IGNORECASE):
            return "'sage.rings.infinity.PlusInfinity'"
        return CARDINALITY_RETURN_UNION

    # Rank is an integer-valued invariant in Sage's combinatorics and linear
    # algebra APIs.  Keep the native/Sage alternatives explicit; unlike
    # cardinality, rank does not use +Infinity in the documented methods.
    if node.name == "rank":
        return "'sage.rings.integer.Integer | int'"

    # Parent characteristics and generator/axis counts use either Sage's
    # Integer wrapper or a native Python count depending on the Cython/backend
    # implementation.  Both are stable scalar contracts and do not depend on
    # the receiver's concrete element parent.
    if node.name == "characteristic":
        return "'sage.rings.integer.Integer | int'"
    if node.name in {"ngens", "nrows", "ncols"}:
        return "'sage.rings.integer.Integer | int'"

    # Count-valued helpers use a wide range of names (``number_boundaries``,
    # ``number_of_words``, ``nparts`` ...), but their documentation shares a
    # precise ``number of ...`` contract.  Restrict the rule to that phrase
    # and reject number-field/ring constructors, whose result is a parent.
    if (
        (node.name.startswith("number_") or re.match(r"^n[a-z_]+$", node.name))
        and re.search(r"\b(?:return(?:s)?\s+)?(?:the\s+)?number\s+of\b", summary, re.IGNORECASE)
        and not re.search(r"\bnumber\s+(?:field|ring|module|space|theory)\b", summary, re.IGNORECASE)
    ):
        return "'sage.rings.integer.Integer | int'"

    # ``MatrixSpace`` is a parent/factory whose element implementation is
    # selected by the base ring, dimensions, sparsity and optional backend.
    # Its scalar/container protocols are independent of that dispatch and can
    # therefore be made precise directly.  Matrix-producing methods use the
    # explicit concrete implementation union above; this avoids publishing
    # the public ``matrix0.Matrix`` base while still exposing ``solve_right``
    # and the other matrix2 members in PyCharm.
    if owner_name == "MatrixSpace":
        if node.name in {"is_exact", "_has_default_implementation", "_repr_option", "is_dense", "is_sparse", "is_finite"}:
            return "bool"
        if node.name == "dims":
            return "tuple[int, int]"
        if node.name == "basis":
            return "'sage.sets.family.FiniteFamily'"
        if node.name in {"identity_matrix", "zero_matrix", "diagonal_matrix", "gen", "matrix", "from_vector", "random_element", "_an_element_", "_random_nonzero_element", "_element_constructor_", "_from_dict"}:
            return MATRIX_ELEMENT_UNION
        if node.name == "some_elements":
            return f"Iterator[{MATRIX_ELEMENT_UNION}]"
        if node.name in {"row_space", "column_space"}:
            return MATRIX_SPACE_MODULE_UNION
        if node.name == "submodule":
            return MATRIX_SPACE_SUBMODULE_UNION
        if node.name == "construction":
            return "tuple"

    # Symbolic ``Expression`` transforms are expression-preserving in Sage's
    # symbolic ring.  The generated Cython stubs omit these return annotations
    # even though the runtime class is stable; keep evaluation/solver helpers
    # out because their result depends on substitutions and backend choices.
    if owner_name == "Expression":
        if node.name == "__enter__":
            return "Self"
        if node.name in {"_ascii_art_", "_unicode_art_"}:
            return (
                "'sage.typeset.ascii_art.AsciiArt'"
                if node.name == "_ascii_art_"
                else "'sage.typeset.unicode_art.UnicodeArt'"
            )
        if node.name in {"_fricas_init_", "_interface_init_"}:
            return "str"
        if node.name in {
            "__abs__", "__invert__", "__add__", "__floordiv__", "__mul__",
            "__neg__", "__pow__", "__sub__", "__truediv__",
            "_add_", "_div_", "_mul_", "_sub_",
            "abs", "add", "add_to_both_sides", "arccos", "arccosh", "arcsin",
            "arcsinh", "arctan", "arctan2", "arctanh", "canonicalize_radical",
            "collect", "collect_common_factors", "combine", "compositional_inverse",
            "cos", "cosh", "derivative", "divide_both_sides", "distribute", "exp",
            "expand", "expand_log", "expand_sum", "exponentialize", "factor",
            "gamma", "gamma_normalize", "integral", "left_hand_side", "log",
            "log_gamma", "multiply_both_sides", "negation", "normalize", "numerator",
            "denominator", "power", "primitive_part",
            "real_part", "imag_part", "rectform", "round", "simplify",
            "simplify_factorial", "simplify_full", "simplify_hypergeometric",
            "simplify_log", "simplify_rational", "simplify_real", "simplify_rectform",
            "simplify_trig", "sin", "sinh", "sqrt", "substitute_function",
            "substitution_delayed", "subtract_from_both_sides", "tan", "tanh", "taylor",
            "to_gamma", "trailing_coefficient", "unit", "unit_content_primitive",
            "unhold", "zeta",
        }:
            return "Self"
        if node.name in {
            "content", "csgn", "demoivre", "function", "gcd", "gosper_sum",
            "gosper_term", "half_angle", "horner", "implicit_derivative",
            "inverse_laplace", "laplace", "leading_coefficient", "limit",
            "mul", "norm", "poly", "prod", "residue", "resultant", "step",
            "sum", "WZ_certificate",
        }:
            return "Self"
        if node.name == "gradient":
            return (
                "'sage.modules.free_module_element.FreeModuleElement_generic_dense | "
                "sage.modules.free_module_element.FreeModuleElement_generic_sparse'"
            )
        if node.name == "hessian":
            return "'sage.matrix.matrix_symbolic_dense.Matrix_symbolic_dense'"
        if node.name in {"find_local_maximum", "find_local_minimum"}:
            return "tuple[float, float]"
        if node.name == "match":
            return "dict | None"
        if node.name == "maxima_methods":
            return "'sage.symbolic.maxima_wrapper.MaximaWrapper'"
        if node.name == "nintegral":
            return "tuple"
        if node.name in {"arguments", "variables", "free_variables", "numerator_denominator"}:
            return "tuple"
        if node.name in {"default_variable", "right_hand_side", "subs"}:
            return "Self"
        if node.name == "fraction":
            return "tuple[Self, Self]"
        if node.name == "find_root":
            return "'sage.rings.real_mpfr.RealNumber'"
        if node.name in {"_integer_"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"_rational_"}:
            return "'sage.rings.rational.Rational'"
        if node.name in {"_complex_double_"}:
            return "'sage.rings.complex_double.ComplexDoubleElement'"
        if node.name in {"_complex_mpfi_", "_complex_mpfr_field_"}:
            return "'sage.rings.complex_mpfr.ComplexNumber'"
        if node.name in {"_real_double_"}:
            return "'sage.rings.real_double.RealDoubleElement'"
        if node.name in {"_real_mpfi_", "_mpfr_"}:
            return "'sage.rings.real_mpfr.RealNumber'"
        if node.name in {"_sympy_"}:
            return "'sympy.core.expr.Expr'"
        if node.name in {"number_of_arguments", "number_of_operands"}:
            return "int"
        if node.name in {"assume", "decl_assume", "decl_forget", "forget"}:
            return "None"
        if node.name in {"has", "test_relation"}:
            return "bool"
        if node.name in {"solve", "solve_diophantine", "find"}:
            return "list"
        if node.name == "plot":
            return "'sage.plot.graphics.Graphics'"

    # Formal power/Laurent series have a particularly stable outer protocol:
    # arithmetic and precision transforms preserve the selected series
    # implementation, while coefficient/precision helpers return documented
    # scalar or container families.  Keep substitutions and coefficient
    # access fail-closed because their result depends on the argument parent.
    series_owner = owner_name in {
        "PowerSeries", "PowerSeries_poly", "PowerSeries_pari",
        "MPowerSeries", "LaurentSeries",
    }
    if series_owner:
        if node.name in {
            "__bool__", "is_dense", "is_gen", "is_monomial", "is_nilpotent",
            "is_square", "is_unit", "is_zero",
        }:
            return "bool"
        if node.name in {"__hash__"}:
            return "int"
        if node.name in {"__copy__", "__neg__", "__pos__", "__setitem__", "_richcmp_"}:
            return "Self" if node.name != "__setitem__" and node.name != "_richcmp_" else (
                "None" if node.name == "__setitem__" else "bool"
            )
        if node.name == "__init__":
            return "None"
        if node.name == "__reduce__":
            return "tuple | str"
        if node.name in {"_repr_", "_latex_", "variable"}:
            if node.name == "variable" and owner_name == "MPowerSeries":
                return None
            return "str"
        if node.name in {
            "_add_", "_sub_", "_mul_", "_lmul_", "_rmul_",
            "__lshift__", "__rshift__", "__mod__", "add_bigoh", "O",
            "change_ring", "base_extend", "derivative", "integral", "exp",
            "log", "sin", "cos", "tan", "sinh", "cosh", "tanh", "shift",
            "egf_to_ogf", "ogf_to_egf", "valuation_zero_part", "map_coefficients",
            "lift_to_precision", "reverse", "truncate_powerseries", "_integral",
        }:
            # Multivariate shift/OGF helpers are explicitly unimplemented in
            # the Sage docs; do not expose a value for those methods.
            if owner_name == "MPowerSeries" and node.name in {
                "__lshift__", "__rshift__", "shift", "egf_to_ogf", "ogf_to_egf",
                "truncate_powerseries",
            }:
                return None
            return "Self"
        if node.name == "_div_":
            if owner_name == "LaurentSeries" or owner_name == "MPowerSeries":
                return "Self"
            return "Self | 'sage.rings.laurent_series_ring_element.LaurentSeries'"
        if node.name in {"__invert__", "inverse"}:
            if owner_name in {"LaurentSeries", "MPowerSeries"}:
                return "Self"
            return "Self | 'sage.rings.laurent_series_ring_element.LaurentSeries'"
        if node.name in {"__pow__", "nth_root"}:
            if owner_name == "LaurentSeries":
                return "Self"
            return "Self | 'sage.rings.laurent_series_ring_element.LaurentSeries'"
        if node.name in {"coefficients", "exponents", "list", "padded_list", "monomials"}:
            if owner_name == "MPowerSeries" and node.name == "coefficients":
                return "dict"
            if owner_name == "MPowerSeries" and node.name in {"list", "padded_list"}:
                return None
            return "list"
        if node.name == "monomial_coefficients":
            return "dict"
        if node.name == "variables":
            return "tuple"
        if node.name in {"degree"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {
            "prec", "precision_absolute", "precision_relative", "common_prec",
            "common_valuation", "valuation",
        }:
            return CARDINALITY_RETURN_UNION
        if node.name == "polynomial":
            return (
                MULTIVARIATE_POLYNOMIAL_RETURN_UNION
                if owner_name == "MPowerSeries"
                else POLYNOMIAL_RETURN_UNION
            )
        if node.name == "truncate":
            return "Self" if owner_name == "MPowerSeries" or owner_name == "LaurentSeries" else POLYNOMIAL_RETURN_UNION
        if node.name == "pade" and owner_name == "PowerSeries_poly":
            return "'sage.rings.fraction_field_element.FractionFieldElement'"
        if node.name == "laurent_series" and owner_name in {"PowerSeries", "PowerSeries_poly", "PowerSeries_pari"}:
            return "'sage.rings.laurent_series_ring_element.LaurentSeries'"
        if node.name == "laurent_polynomial" and owner_name == "LaurentSeries":
            return LAURENT_POLYNOMIAL_RETURN_UNION
        if node.name == "power_series" and owner_name == "LaurentSeries":
            return POWER_SERIES_RETURN_UNION
        if node.name == "__iter__" and owner_name in {"PowerSeries_poly", "LaurentSeries"}:
            return "Iterator"
        if node.name == "residue" and owner_name == "LaurentSeries":
            return None
        if node.name == "__pari__" and owner_name in {"PowerSeries_pari", "LaurentSeries"}:
            return "'cypari2.gen.Gen'"

    # Lazy formal series use the same parent-preserving contract for their
    # analytic transforms.  The coefficient stream and substitution operand
    # can change the inner value type, so indexing and scalar action remain
    # unresolved; the documented outer series/container result is stable.
    if owner_name == "LazyModuleElement":
        if node.name in {
            "arccos", "arccot", "arcsin", "arcsinh", "arctan", "arctanh",
            "cos", "cosh", "cot", "coth", "csc", "csch", "dilog", "euler",
            "exp", "hypergeometric", "jacobi_theta", "log", "polylog",
            "q_pochhammer", "sec", "sech", "sin", "sinh", "sqrt", "tan",
            "tanh", "nth_root", "change_ring", "map_coefficients", "restrict",
            "shift", "truncate", "__rshift__", "lift_to_precision",
        }:
            return "Self"
        if node.name == "coefficients":
            return "list"
        if node.name == "prec":
            return "'sage.rings.infinity.PlusInfinity'"
        if node.name == "define":
            return "None"

    # Link invariants have fixed outer Sage types even though the crossing
    # presentation is user supplied.  Keep knot/link transformations as Self
    # so a concrete Knot receiver is preserved, and expose the documented
    # polynomial and container families without falling back to ``Any``.
    if owner_name == "Link":
        if node.name in {"__eq__", "__ne__", "is_alternating", "is_colorable", "is_isotopic", "is_knot"}:
            return "bool"
        if node.name == "__hash__":
            return "int"
        if node.name == "braid":
            return "'sage.groups.braid.Braid'"
        if node.name in {
            "arcs", "gauss_code", "oriented_gauss_code", "pd_code",
            "dowker_notation", "orientation", "seifert_circles", "regions",
            "colorings", "coloring_maps",
        }:
            return "list"
        if node.name in {"number_of_components", "signature", "omega_signature", "determinant", "writhe"}:
            return "'sage.rings.integer.Integer | int'"
        if node.name == "genus":
            return "'sage.rings.rational.Rational | int'"
        if node.name in {"alexander_polynomial", "conway_polynomial"}:
            return LINK_POLYNOMIAL_RETURN_UNION
        if node.name == "jones_polynomial":
            return JONES_POLYNOMIAL_RETURN_UNION
        if node.name == "khovanov_polynomial":
            return "'sage.rings.polynomial.laurent_polynomial_mpair.LaurentPolynomial_mpair'"
        if node.name == "seifert_matrix":
            return "'sage.matrix.matrix_integer_dense.Matrix_integer_dense'"
        if node.name == "_coloring_matrix":
            return MATRIX_ELEMENT_UNION
        if node.name in {"mirror_image", "reverse", "remove_loops"}:
            return "Self"
        if node.name == "simplify":
            return "Self | None"
        if node.name == "plot":
            return "'sage.plot.graphics.Graphics'"

    # Finite-state machines expose a small, documented object protocol.  State
    # and transition payloads are concrete Sage helper classes; graph/matrix
    # views use their concrete graph/matrix implementations, while machine
    # transformations preserve the receiver family through ``Self``.
    if owner_name == "FiniteStateMachine":
        if node.name in {
            "__bool__", "__eq__", "__ne__", "__contains__", "is_Markov_chain",
            "is_deterministic", "is_complete", "is_connected", "has_state",
            "has_transition", "has_initial_state", "has_initial_states",
            "has_final_state", "has_final_states",
        }:
            return "bool"
        if node.name == "__hash__":
            return "int"
        if node.name in {"_repr_", "_latex_", "_latex_transition_label_", "format_transition_label_reversed", "default_format_transition_label"}:
            return "str"
        if node.name in {"__copy__", "__deepcopy__", "coaccessible_components", "disjoint_union", "concatenation", "completion", "kleene_star"}:
            return "Self"
        if node.name in {"merged_transitions", "markov_chain_simplification"}:
            return "Self"
        if node.name in {"states", "transitions", "initial_states", "final_states", "final_components", "equivalence_classes", "predecessors", "add_states"}:
            if node.name == "add_states":
                return "None"
            return "list"
        if node.name in {"iter_states", "iter_transitions", "_iter_transitions_all_", "iter_initial_states", "iter_final_states", "iter_process", "_iter_process_simple_", "iter_process"}:
            return "Iterator"
        if node.name in {"state", "add_state"}:
            return "'sage.combinat.finite_state_machine.FSMState'"
        if node.name in {"transition", "add_transition", "_add_fsm_transition_"}:
            return "'sage.combinat.finite_state_machine.FSMTransition'"
        if node.name == "epsilon_successors":
            return "dict"
        if node.name in {"_matrix_", "adjacency_matrix"}:
            return MATRIX_ELEMENT_UNION
        if node.name == "graph":
            return "'sage.graphs.digraph.DiGraph'"
        if node.name == "plot":
            return "'sage.plot.graphics.Graphics'"
        if node.name == "language":
            return "list"
        if node.name in {
            "add_from_transition_function", "add_transitions_from_function", "delete_transition",
            "delete_state", "set_coordinates", "determine_input_alphabet",
            "determine_output_alphabet", "determine_alphabets", "prepone_output",
            "latex_options", "construct_final_word_out",
        }:
            return "None"

    # Algebraic number elements have a fixed rational-polynomial/height
    # protocol in Sage 10.9.  These methods are independent of the defining
    # field's concrete parent; ideal-valued and embedding-selection methods
    # remain unresolved below because their class depends on the field.
    if owner_name == "NumberFieldElement":
        if node.name == "absolute_norm":
            return "'sage.rings.rational.Rational'"
        if node.name in {"charpoly", "minpoly", "polynomial"}:
            return "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'"
        if node.name in {"denominator", "floor", "round", "valuation"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"complex_embedding"}:
            return "'sage.rings.complex_mpfr.ComplexNumber'"
        if node.name in {"complex_embeddings", "galois_conjugates"}:
            return "list['sage.rings.complex_mpfr.ComplexNumber']" if node.name == "complex_embeddings" else "list[Self]"
        if node.name in {"coordinates_in_terms_of_powers", "vector"}:
            return "'sage.modules.free_module_element.FreeModuleElement'"
        if node.name in {"global_height", "global_height_arch", "global_height_non_arch", "local_height", "local_height_arch", "local_height_non_arch"}:
            return "'sage.rings.real_mpfr.RealNumber'"
        if node.name == "is_norm":
            return "bool"
        if node.name in {"multiplicative_order", "additive_order"}:
            return ORDER_RETURN_UNION
        if node.name == "__pari__":
            return "'cypari2.gen.Gen'"
        if node.name == "_rational_":
            return "'sage.rings.rational.Rational'"
        if node.name == "_integer_":
            return "'sage.rings.integer.Integer'"

    if owner_name == "NumberField_generic":
        if node.name in {"class_number", "disc", "discriminant", "zeta_order"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"gen", "random_element", "primitive_root_of_unity", "_element_constructor_"}:
            return "'sage.rings.number_field.number_field_element.NumberFieldElement'"
        if node.name in {"power_basis", "roots_of_unity", "reduced_basis", "trace_dual_basis"}:
            return "list['sage.rings.number_field.number_field_element.NumberFieldElement']"
        if node.name in {"polynomial", "defining_polynomial"}:
            return "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'"
        if node.name == "polynomial_ring":
            return "'sage.rings.polynomial.polynomial_ring.PolynomialRing_field'"
        if node.name == "algebraic_closure":
            return "'sage.rings.qqbar.AlgebraicField'"
        if node.name in {"complex_embeddings", "real_embeddings"}:
            return "'sage.structure.sequence.Sequence_generic'"
        if node.name == "regulator":
            return "'sage.rings.real_mpfr.RealNumber'"
        if node.name == "units":
            return "tuple"
        if node.name in {"unit_group", "S_unit_group"}:
            return "'sage.rings.number_field.unit_group.UnitGroup'"
        if node.name in {"class_group", "narrow_class_group"}:
            return "'sage.rings.number_field.class_group.ClassGroup | sage.rings.number_field.class_group.SClassGroup'"
        if node.name == "signature":
            return "tuple[int, int]"
        if node.name == "construction":
            return "tuple"
        if node.name == "primes_of_bounded_norm_iter":
            return "Iterator['sage.rings.number_field.number_field_ideal.NumberFieldIdeal']"
        if node.name in {"ideal", "prime_above"}:
            return "'sage.rings.number_field.number_field_ideal.NumberFieldIdeal | sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'"
        if node.name == "fractional_ideal":
            return "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'"
        if node.name == "factor":
            return "'sage.structure.factorization.Factorization'"
        if node.name == "__pari__":
            return "'cypari2.gen.Gen'"
        if node.name == "absolute_polynomial_ntl":
            return "tuple"
        if node.name == "lmfdb_page":
            return "None"
        if node.name == "_normalize_prime_list":
            return "tuple"
        if node.name == "_generator_matrix":
            return "'sage.matrix.matrix_rational_dense.Matrix_rational_dense'"
        if node.name == "_pari_integral_basis":
            return "'cypari2.gen.Gen'"
        if node.name == "uniformizer":
            return "'sage.rings.number_field.number_field_element.NumberFieldElement'"
        if node.name in {"absolute_field"}:
            return "'sage.rings.number_field.number_field.NumberField_absolute'"
        if node.name in {"absolute_polynomial"}:
            return "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'"
        if node.name == "change_generator":
            return "tuple"
        if node.name == "different":
            return "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'"
        if node.name == "maximal_order":
            return "'sage.rings.number_field.order.Order_absolute_with_category'"
        if node.name == "maximal_totally_real_subfield":
            return "list"
        if node.name in {"pari_bnf", "pari_nf", "pari_polynomial", "pari_zk", "zeta_coefficients"}:
            return "'cypari2.gen.Gen'"
        if node.name == "polynomial_ntl":
            return "tuple"
        if node.name == "polynomial_quotient_ring":
            return "'sage.rings.polynomial.polynomial_quotient_ring.PolynomialQuotientRing_field_with_category'"
        if node.name == "primitive_element":
            return "'sage.rings.number_field.number_field_element.NumberFieldElement'"
        if node.name == "reduced_gram_matrix":
            return "'sage.matrix.matrix_generic_dense.Matrix_generic_dense'"
        if node.name == "structure":
            return "tuple"
        if node.name == "subfield":
            return "tuple"
        if node.name == "trace_pairing":
            return MATRIX_ELEMENT_UNION
        if node.name == "valuation":
            return "'sage.rings.padics.padic_valuation.pAdicFromLimitValuation_with_category'"

    if owner_name == "NumberField_relative":
        if node.name in {"absolute_degree", "absolute_discriminant", "relative_degree", "number_of_roots_of_unity"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"base_field", "base_ring"}:
            return "'sage.rings.number_field.number_field.NumberField_generic | sage.rings.number_field.number_field_rel.NumberField_relative'"
        if node.name == "absolute_field":
            return "'sage.rings.number_field.number_field.NumberField_absolute'"
        if node.name == "absolute_polynomial":
            return "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'"
        if node.name == "gen":
            return "'sage.rings.number_field.number_field_element.NumberFieldElement'"
        if node.name == "roots_of_unity":
            return "list['sage.rings.number_field.number_field_element.NumberFieldElement']"
        if node.name == "subfields":
            return "list['sage.rings.number_field.number_field.NumberField_generic']"
        if node.name == "change_names":
            return "None"
        if node.name in {"absolute_base_field", "galois_closure"}:
            return "'sage.rings.number_field.number_field.NumberField_absolute'"
        if node.name in {"absolute_different", "different", "relative_different", "relative_discriminant"}:
            return "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'"
        if node.name in {"absolute_generator", "lift_to_base"}:
            return "'sage.rings.number_field.number_field_element.NumberFieldElement'"
        if node.name == "absolute_polynomial_ntl":
            return "tuple"
        if node.name == "absolute_vector_space":
            return "tuple"
        if node.name == "automorphisms":
            return "list"
        if node.name in {"defining_polynomial", "polynomial", "relative_polynomial"}:
            return "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'"
        if node.name in {"disc", "discriminant"}:
            return "'sage.rings.integer.Integer'"
        if node.name == "embeddings":
            return "list"
        if node.name in {"free_module", "vector_space", "relative_vector_space"}:
            return "tuple"
        if node.name in {"pari_absolute_base_polynomial", "pari_relative_polynomial", "pari_rnf"}:
            return "'cypari2.gen.Gen'"
        if node.name == "relativize":
            return "'sage.rings.number_field.number_field_rel.NumberField_relative'"

    if owner_name == "NumberField_absolute":
        if node.name in {"_coerce_from_other_number_field", "absolute_generator"}:
            return "'sage.rings.number_field.number_field_element.NumberFieldElement'"
        if node.name == "base_field":
            return "'sage.rings.rational_field.RationalField'"
        if node.name in {"absolute_polynomial", "relative_polynomial"}:
            return "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'"
        if node.name in {"optimized_representation", "free_module", "absolute_vector_space", "relative_vector_space"}:
            return "tuple"
        if node.name in {"optimized_subfields", "subfields", "automorphisms", "embeddings", "places", "real_places"}:
            return "list"
        if node.name == "change_names":
            return "Self"
        if node.name in {"galois_closure", "_galois_closure_and_embedding"}:
            return "'sage.rings.number_field.number_field.NumberField_absolute | tuple'"
        if node.name == "minkowski_embedding":
            return "'sage.matrix.matrix_double_dense.Matrix_double_dense'"
        if node.name == "abs_val":
            return "'sage.rings.real_mpfr.RealNumber'"
        if node.name == "relativize":
            return "'sage.rings.number_field.number_field_rel.NumberField_relative'"
        if node.name in {"absolute_degree", "relative_degree", "absolute_discriminant", "relative_discriminant"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"absolute_different", "relative_different"}:
            return "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'"
        if node.name == "hilbert_symbol":
            return "'sage.rings.integer.Integer'"
        if node.name == "hilbert_symbol_negative_at_S":
            return "'sage.rings.number_field.number_field_element.NumberFieldElement'"
        if node.name == "hilbert_conductor":
            return "'sage.rings.number_field.number_field_ideal.NumberFieldFractionalIdeal'"

    if owner_name == "Integer":
        # Integer transcendental helpers construct symbolic expressions; the
        # factorial-like gamma specialization stays in Sage's Integer class.
        # Additive/multiplicative orders are value-dependent (zero and units
        # have different orders), so they intentionally remain unresolved.
        if node.name in {"sqrt", "log", "exp"}:
            return "'sage.symbolic.expression.Expression'"
        if node.name == "gamma":
            return "'sage.rings.integer.Integer'"
        if node.name == "__pari__":
            return "'cypari2.gen.Gen'"
        if node.name == "_sympy_":
            return "'sympy.core.numbers.Integer'"
        if node.name in {"GCD_list", "make_integer"}:
            return "'sage.rings.integer.Integer'"

    if owner_name == "FiniteField":
        if node.name in {"extension", "subfield"}:
            return FINITE_FIELD_UNION
        if node.name == "factored_order":
            return "'sage.structure.factorization.Factorization'"
        if node.name == "free_module":
            return "tuple"
        if node.name == "from_bytes":
            return FINITE_FIELD_ELEMENT_UNION
        if node.name == "polynomial_ring":
            return "'sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p | sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_finite_field'"

    if owner_name and owner_name.casefold().startswith("finitefield_"):
        if node.name in {"_element_constructor_", "a_times_b_minus_c", "a_times_b_plus_c", "c_minus_a_times_b"}:
            return "Self"
        if node.name == "__pari__":
            return "'cypari2.gen.Gen'"
        if node.name in {"int_to_log", "degree"}:
            return "int"

    if owner_name == "FinitePolyExtElement":
        if node.name == "__pari__":
            return "'cypari2.gen.Gen'"
        if node.name == "charpoly":
            return "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'"
        if node.name == "matrix":
            return "'sage.matrix.matrix_modn_dense_float.Matrix_modn_dense_float'"
        if node.name == "to_bytes":
            return "bytes"

    if owner_name == "RationalField":
        # QQ is a singleton field with fixed, documented outputs for these
        # number-field compatibility helpers.  Parent-changing operations
        # (completion, extension, residue_field, coercion maps) remain open.
        if node.name in {
            "discriminant", "absolute_discriminant", "relative_discriminant",
            "class_number", "degree", "absolute_degree",
        }:
            return "'sage.rings.integer.Integer'"
        if node.name == "construction":
            return "tuple"
        if node.name == "signature":
            return "tuple"
        if node.name in {"embeddings", "automorphisms"}:
            return "'sage.structure.sequence.Sequence_generic'"
        if node.name == "places":
            return "list"
        if node.name == "complex_embedding":
            return "'sage.rings.morphism.RingHomomorphism_im_gens'"
        if node.name == "hilbert_symbol_negative_at_S":
            return "'sage.rings.rational.Rational'"
        if node.name == "gens":
            return "tuple['sage.rings.rational.Rational']"
        if node.name == "maximal_order":
            return "'sage.rings.integer_ring.IntegerRing_class'"
        if node.name == "number_field":
            return "Self"
        if node.name == "power_basis":
            return "list['sage.rings.rational.Rational']"
        if node.name == "algebraic_closure":
            return "'sage.rings.qqbar.AlgebraicField'"
        if node.name == "polynomial":
            return "'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint'"
        if node.name == "_an_element_":
            return "'sage.rings.rational.Rational'"
        if node.name in {"some_elements", "selmer_group_iterator"}:
            return "Iterator['sage.rings.rational.Rational']"
        if node.name == "primes_of_bounded_norm_iter":
            return "Iterator['sage.rings.integer.Integer']"
        if node.name == "zeta":
            return "'sage.rings.rational.Rational'"
        if node.name == "selmer_generators":
            return "list | tuple"
        if node.name == "selmer_space":
            return "tuple"
        if node.name == "quadratic_defect":
            return "'sage.rings.integer.Integer | sage.rings.infinity.PlusInfinity'"

    if owner_name == "SageObject":
        # SageObject's serialization, typesetting, and interface-init hooks
        # have language/runtime-level outer contracts shared by every Sage
        # subclass.  Conversion to a specific external interface remains
        # dynamic and is intentionally not guessed here.
        if node.name in {"rename", "reset_name", "save", "dump"}:
            return "None"
        if node.name == "get_custom_name":
            return "str | None"
        if node.name == "_ascii_art_":
            return "'sage.typeset.ascii_art.AsciiArt'"
        if node.name == "_unicode_art_":
            return "'sage.typeset.unicode_art.UnicodeArt'"
        if node.name == "dumps":
            return "bytes"
        if node.name.endswith("_init_"):
            return "str"

    if owner_name == "Tableau":
        # These tableau helpers have stable outer results regardless of the
        # element-class generated by the parent.  Transformations whose
        # result remains a parent-specific tableau stay unresolved because a
        # public Tableau base would hide the concrete implementation.
        if node.name == "_ascii_art_":
            return "'sage.typeset.ascii_art.AsciiArt'"
        if node.name == "_unicode_art_":
            return "'sage.typeset.unicode_art.UnicodeArt'"
        if node.name == "_ascii_art_table":
            return "str"
        if node.name == "_heights":
            return "list['sage.rings.integer.Integer']"
        if node.name == "bender_knuth_involution":
            return "'sage.combinat.tableau.SemistandardTableau'"
        if node.name == "catabolism_sequence":
            return "list"
        if node.name in {"flush", "level", "seg", "socle"}:
            return "int"
        if node.name == "last_letter_lequal":
            return "bool"
        if node.name == "pp":
            return "None"
        if node.name == "residue":
            return INTEGER_MOD_ELEMENT_UNION
        if node.name == "standardization":
            return "'sage.combinat.tableau.StandardTableau'"

    if owner_name == "SkewTableau":
        # Skew-tableau methods expose stable combinatorial containers and
        # documented shape/tableau families.  Sage's runtime element classes
        # are generated by their parents, so use the public concrete element
        # classes (or Self for transformations that preserve the family)
        # instead of leaking a generic parent/base type.
        if node.name == "_repr_compact":
            return "str"
        if node.name in {"_ascii_art_", "_unicode_art_"}:
            return (
                "'sage.typeset.ascii_art.AsciiArt'"
                if node.name == "_ascii_art_"
                else "'sage.typeset.unicode_art.UnicodeArt'"
            )
        if node.name in {"check", "pp"}:
            return "None"
        if node.name in {
            "cells", "cells_by_content", "entries_by_content", "filling",
            "to_chain", "to_expr", "to_list", "weight",
        }:
            return "list"
        if node.name in {"inner_shape", "outer_shape", "restriction_outer_shape"}:
            return "'sage.combinat.partition.Partition'"
        if node.name in {"shape", "restriction_shape"}:
            return "'sage.combinat.skew_partition.SkewPartition'"
        if node.name in {"inner_size", "outer_size", "size"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {
            "add_entry", "anti_restrict", "backward_slide",
            "bender_knuth_involution", "restrict",
        }:
            return "Self"
        if node.name == "rectify":
            return (
                "'sage.combinat.tableau.StandardTableau | "
                "sage.combinat.tableau.SemistandardTableau | "
                "sage.combinat.tableau.Tableau'"
            )
        if node.name in {"row_stabilizer", "column_stabilizer"}:
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'"
        if node.name == "standardization":
            return "'sage.combinat.skew_tableau.SkewTableau'"
        if node.name == "to_permutation":
            return "'sage.combinat.permutation.Permutation'"
        if node.name == "to_tableau":
            return "'sage.combinat.tableau.Tableau'"
        if node.name in {"to_word_by_column", "to_word_by_row"}:
            return "'sage.combinat.words.word.FiniteWord_list'"

    if owner_name == "ParallelogramPolyomino":
        # The polyomino implementation documents fixed scalar/container
        # results and named combinatorial bijections.  Option-dependent
        # drawing state is represented by its concrete LocalOptions object;
        # the internal classcall/parent hooks stay unresolved.
        if node.name in {"_ascii_art_", "_unicode_art_"}:
            return (
                "'sage.typeset.ascii_art.AsciiArt'"
                if node.name == "_ascii_art_"
                else "'sage.typeset.unicode_art.UnicodeArt'"
            )
        if node.name in {
            "_latex_drawing", "_latex_list", "to_tikz",
        }:
            return "str"
        if node.name in {"check", "set_options"}:
            return "None"
        if node.name == "__getitem__":
            return "'sage.combinat.parallelogram_polyomino.ParallelogramPolyomino._polyomino_row'"
        if node.name in {
            "_get_node_position_at_column", "_get_node_position_at_row",
            "get_node_position_from_box",
        }:
            return "list"
        if node.name == "_get_number_of_nodes_in_the_bounding_path":
            return "int"
        if node.name in {
            "_to_dyck_delest_viennot", "_to_dyck_delest_viennot_peaks_valleys",
        }:
            return "'sage.combinat.dyck_word.DyckWord'"
        if node.name == "_to_binary_tree_Aval_Boussicault":
            return "'sage.combinat.binary_tree.BinaryTree'"
        if node.name in {"_to_ordered_tree_Bou_Socci", "_to_ordered_tree_via_dyck"}:
            return "'sage.combinat.ordered_tree.OrderedTree'"
        if node.name in {"to_binary_tree"}:
            return "'sage.combinat.binary_tree.BinaryTree'"
        if node.name in {"to_ordered_tree"}:
            return "'sage.combinat.ordered_tree.OrderedTree'"
        if node.name == "get_options":
            return "'sage.combinat.parallelogram_polyomino.LocalOptions'"
        if node.name == "get_tikz_options":
            return "dict"
        if node.name in {"get_array", "bounce_path", "widths", "heights"}:
            return "list"
        if node.name == "cell_is_inside":
            return "int"
        if node.name in {"width", "height", "bounce", "area"}:
            return "int"

    if owner_name == "BinaryTree":
        # BinaryTree operations are concrete tree-preserving transforms or
        # stable combinatorial containers.  Use Self for transforms so a
        # labelled/subclassed tree remains visible to PyCharm; list/graph/
        # predicate helpers expose their documented outer result directly.
        if node.name in {
            "_ascii_art_",
            "_unicode_art_",
        }:
            return (
                "'sage.typeset.ascii_art.AsciiArt'"
                if node.name == "_ascii_art_"
                else "'sage.typeset.unicode_art.UnicodeArt'"
            )
        if node.name in {"check", "make_node", "make_leaf", "show"}:
            return "None"
        if node.name in {
            "canonical_labelling", "left_border_symmetry", "left_right_symmetry",
            "left_rotate", "right_rotate", "prune", "to_full", "over", "under",
            "tamari_join", "tamari_meet",
        }:
            return "Self"
        if node.name in {
            "tamari_greater", "tamari_pred", "tamari_smaller", "tamari_succ",
            "under_decomposition", "over_decomposition",
        }:
            return "list[Self]"
        if node.name in {"tamari_lequal", "is_empty"}:
            return "bool"
        if node.name in {"canopee", "in_order_traversal"}:
            return "list"
        if node.name == "in_order_traversal_iter":
            return "Iterator"
        if node.name == "graph":
            return "'sage.graphs.digraph.DiGraph'"
        if node.name == "to_undirected_graph":
            return "'sage.graphs.graph.Graph'"
        if node.name == "to_poset":
            return "'sage.combinat.posets.posets.FinitePoset'"
        if node.name in {"to_132_avoiding_permutation", "to_312_avoiding_permutation"}:
            return "'sage.combinat.permutation.Permutation'"
        if node.name in {"hook_number", "number_of_left_nodes"}:
            return "int"

    if owner_name == "ComplexIntervalFieldElement":
        # MPFI complex intervals have a stable split between interval-valued
        # component/metric methods, complex-preserving transcendental methods,
        # and scalar protocol helpers.  Keep conversion methods whose parent
        # is caller-supplied unresolved.
        if node.name in {"__abs__", "arg", "argument", "norm", "real", "imag"}:
            return "'sage.rings.real_mpfi.RealIntervalFieldElement'"
        if node.name in {"intersection", "union", "cos", "cosh", "exp", "log", "sin", "sinh", "sqrt", "tan", "tanh", "zeta"}:
            return "Self"
        if node.name in {"center", "_complex_mpfr_field_"}:
            return "'sage.rings.complex_mpfr.ComplexNumber'"
        if node.name in {"diameter", "magnitude", "mignitude"}:
            return "'sage.rings.real_mpfr.RealNumber'"
        if node.name == "prec":
            return "int"
        if node.name == "bisection":
            return "tuple[Self, Self, Self, Self]"
        if node.name == "lexico_cmp":
            return "int"
        if node.name == "multiplicative_order":
            return "'sage.rings.integer.Integer | sage.rings.infinity.PlusInfinity'"
        if node.name == "_integer_":
            return "'sage.rings.integer.Integer'"
        if node.name == "plot":
            return "'sage.plot.graphics.Graphics'"

    if owner_name == "MatroidDatabaseModule":
        # Every public constructor in ``database_matroids`` (including the
        # private relabel helper used by those constructors) returns one of
        # Sage's concrete matroid implementations.  Keep the implementation
        # union explicit instead of exposing the abstract ``Matroid`` base.
        return MATROID_RETURN_UNION

    if owner_name == "HadamardMatrixModule":
        # Hadamard/conference constructors all materialize concrete integer
        # matrices unless ``existence=True`` asks only for a predicate.  The
        # documented pair/code helpers are kept as tuple/list unions instead
        # of being collapsed to a matrix or an abstract parent.
        if node.name in {"williamson_type_quadruples_smallcases", "amicable_hadamard_matrices"}:
            return "tuple | bool"
        if node.name == "amicable_hadamard_matrices_wallis":
            return "tuple"
        if node.name in {"four_symbol_delta_code_smallcases"}:
            return "list | bool"
        if node.name == "szekeres_difference_set_pair":
            return "tuple"
        if node.name == "_get_baumert_hall_units":
            return "tuple | bool"
        if node.name in {
            "hadamard_matrix_from_symmetric_conference_matrix", "hadamard_matrix_miyamoto_construction",
            "hadamard_matrix_from_sds", "hadamard_matrix_cooper_wallis_smallcases",
            "williamson_hadamard_matrix_smallcases",
            "turyn_type_hadamard_matrix_smallcases", "hadamard_matrix_spence_construction",
            "skew_hadamard_matrix_spence_1975", "GS_skew_hadamard_smallcases",
            "skew_hadamard_matrix_from_orthogonal_design", "skew_hadamard_matrix_from_complementary_difference_sets",
            "skew_hadamard_matrix_from_good_matrices_smallcases", "symmetric_conference_matrix",
            "hadamard_matrix", "skew_hadamard_matrix",
        }:
            suffix = " | bool | str" if node.name == "hadamard_matrix" else " | bool"
            return f"{MATRIX_ELEMENT_UNION}{suffix}"
        if node.name in {"normalise_hadamard", "hadamard_matrix_paleyI", "symmetric_conference_matrix_paley", "hadamard_matrix_paleyII", "hadamard_matrix_from_sds", "_construction_goethals_seidel_matrix", "hadamard_matrix_cooper_wallis_construction", "hadamard_matrix_turyn_type", "regular_symmetric_hadamard_matrix_with_constant_diagonal", "RSHCD_324", "_helper_payley_matrix", "rshcd_from_close_prime_powers", "rshcd_from_prime_power_and_conference_matrix", "williamson_goethals_seidel_skew_hadamard_matrix", "skew_hadamard_matrix_spence_construction", "skew_hadamard_matrix_whiteman_construction", "skew_hadamard_matrix_from_good_matrices", "typeI_matrix_difference_set"}:
            return MATRIX_ELEMENT_UNION

    if owner_name == "FunctionalModule":
        # These wrappers have stable outer results independent of the receiver
        # implementation.  Keep receiver-dependent factories (base_ring,
        # gen, image, norm, etc.) unresolved so the call-site propagator can
        # use argument/parent information instead of guessing.
        if node.name == "interval":
            return "list"
        if node.name == "xinterval":
            return "range"
        if node.name in {"symbolic_sum", "symbolic_prod"}:
            return FUNCTIONAL_SYMBOLIC_RESULT_UNION
        if node.name == "krull_dimension":
            return "'sage.rings.integer.Integer | int'"
        if node.name == "regulator":
            return "'sage.rings.real_mpfr.RealNumber'"
        if node.name == "cyclotomic_polynomial":
            # This catalogue always constructs over ZZ; changing ``var`` only
            # changes the generator name, not the concrete FLINT class.
            return "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'"
        if node.name == "round":
            return "'sage.rings.integer.Integer | sage.rings.real_double_element_gsl.RealDoubleElement_gsl | sage.rings.infinity.PlusInfinity'"

    if owner_name == "StronglyRegularDatabaseModule":
        # The fixed SRG catalogue constructors all materialize Sage's
        # concrete Graph implementation.  The generic builders have explicit
        # existence/promise branches in their docstrings, so preserve those
        # outer alternatives instead of collapsing them to GenericGraph.
        if node.name.startswith("SRG_") and node.name != "SRG_from_RSHCD":
            return "'sage.graphs.graph.Graph'"
        if node.name in {"strongly_regular_from_two_weight_code", "strongly_regular_from_two_intersection_set"}:
            return "'sage.graphs.graph.Graph'"
        if node.name == "SRG_from_RSHCD":
            return "'sage.graphs.graph.Graph | bool'"
        if node.name == "strongly_regular_graph":
            return "'sage.graphs.graph.Graph | bool | sage.misc.unknown.Unknown'"
        if node.name == "strongly_regular_graph_lazy":
            return "tuple"

    if owner_name == "DesignDatabaseModule":
        # The small-design catalogue functions materialize their design data
        # as Python lists (MOLS, orthogonal arrays and block collections).
        return "list"

    if owner_name == "GraphFamiliesModule":
        if node.name in {"chang_graphs", "line_graph_forbidden_subgraphs"}:
            return "list"
        return "'sage.graphs.graph.Graph'"

    if owner_name == "DistanceRegularGraphsModule":
        if node.name in {"is_from_GQ_spread", "is_classical_parameters_graph", "is_pseudo_partition_graph"}:
            return "bool"
        if node.name == "is_near_polygon":
            return "tuple"
        # ``distance_regular_graph(..., existence=True)`` changes its result
        # from a graph to a predicate; leave this conditional factory open.
        if node.name == "distance_regular_graph":
            return None
        return "'sage.graphs.graph.Graph'"

    if owner_name == "SmallGraphsModule":
        return "'sage.graphs.graph.Graph'"

    if owner_name == "Polytopes":
        return POLYHEDRON_RETURN_UNION

    if owner_name == "Posets" and node.name != "__classcall__":
        return FINITE_POSET_RETURN_UNION

    # ``FinitePoset`` is the concrete object returned by the catalogue and
    # by most poset transforms.  Its generated stubs leave a sizeable set of
    # methods unannotated even though the source contract fixes the outer
    # result.  Keep element-valued operations (``meet``/``join``/``bottom``
    # and friends) open because facade posets may contain arbitrary user
    # objects; annotate only container, scalar, graph, matrix and poset
    # results whose runtime family is stable.
    if owner_name == "FinitePoset":
        if node.name in {
            "_list", "linear_extension", "spectrum", "atkinson", "level_sets",
            "common_upper_covers", "common_lower_covers", "dilworth_decomposition",
            "random_maximal_chain", "random_maximal_antichain", "random_linear_extension",
            "maximal_antichains", "maximal_chains",
        }:
            return "list"
        if node.name in {"show", "_macaulay2_init_"}:
            return "None"
        if node.name in {"number_of_relations", "moebius_function", "order_ideal_cardinality", "maximal_chain_length"}:
            return "'sage.rings.integer.Integer | int'"
        if node.name == "compare_elements":
            return "int | None"
        if node.name in {"height", "jump_number"}:
            return "'sage.rings.integer.Integer | int | tuple'"
        if node.name == "rank_function":
            return "'collections.abc.Callable | None'"
        if node.name in {"cover_relations_graph", "comparability_graph", "incomparability_graph", "linear_extensions_graph"}:
            return "'sage.graphs.graph.Graph'"
        if node.name in {"moebius_function_matrix", "lequal_matrix", "coxeter_transformation"}:
            return MATRIX_ELEMENT_UNION
        if node.name in {
            "coxeter_polynomial", "zeta_polynomial", "apozeta_polynomial",
            "f_polynomial", "h_polynomial", "flag_f_polynomial",
            "flag_h_polynomial", "characteristic_polynomial", "chain_polynomial",
            "order_polynomial", "degree_polynomial", "kazhdan_lusztig_polynomial",
        }:
            return POLYNOMIAL_RETURN_UNION
        if node.name in {
            "slant_sum", "rees_product", "disjoint_union", "ordinal_product",
            "ordinal_sum", "star_product", "lexicographic_sum", "dual",
            "with_bounds", "without_bounds", "relabel", "canonical_label",
            "subposet", "completion_by_cuts", "promotion", "evacuation",
        }:
            return FINITE_POSET_RETURN_UNION
        if node.name in {"order_filter", "order_ideal"}:
            return "list"
        if node.name == "greene_shape":
            return "'sage.combinat.partition.Partition'"
        if node.name in {"random_subposet"}:
            return FINITE_POSET_RETURN_UNION
        if node.name == "graphviz_string":
            return "str"
        if node.name == "order_complex":
            return "'sage.topology.simplicial_complex.SimplicialComplex'"
        if node.name in {"order_polytope", "chain_polytope"}:
            return POLYHEDRON_RETURN_UNION

    if owner_name == "Partition":
        if node.name in {"__next__", "stretch", "power", "t_completion", "to_core", "k_irreducible", "k_skew", "k_conjugate", "k_split"}:
            return "Self"
        if node.name == "__truediv__":
            return "'sage.combinat.skew_partition.SkewPartition'"
        if node.name in {"k_rim", "k_column_lengths", "remove_horizontal_border_strip"}:
            return "list"
        if node.name == "next_within_bounds":
            return "Self | None"
        if node.name == "cell_poset":
            return FINITE_POSET_RETURN_UNION
        if node.name in {"to_dyck_word"}:
            return "'sage.combinat.dyck_word.DyckWord'"
        if node.name in {"reading_tableau", "initial_column_tableau", "garnir_tableau", "top_garnir_tableau", "leg_lengths", "upper_hook_lengths", "lower_hook_lengths", "contents_tableau"}:
            return "'sage.combinat.tableau.Tableau'"
        if node.name == "ladder_tableau":
            return "'sage.combinat.tableau.Tableau' | tuple"
        if node.name in {"young_subgroup"}:
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'"
        if node.name in {"young_subgroup_generators"}:
            return "list"
        if node.name in {"arm_length", "leg_length", "hook_length", "upper_hook", "lower_hook", "_initial_degree"}:
            return "'sage.rings.integer.Integer | int'"
        if node.name == "hook_polynomial":
            return POLYNOMIAL_RETURN_UNION

        if node.name == "quotient":
            return "'sage.combinat.partition_tuple.PartitionTuple'"
        if node.name == "k_boundary":
            return "'sage.combinat.skew_partition.SkewPartition'"
        if node.name == "jacobi_trudi":
            return MATRIX_ELEMENT_UNION
        if node.name == "plancherel_measure":
            return "'sage.rings.rational.Rational'"
        if node.name == "outline":
            return "'sage.symbolic.expression.Expression'"
        if node.name in {"specht_module_dimension", "simple_module_dimension"}:
            return "'sage.rings.rational.Rational'"
        if node.name in {"add_cell", "core", "dual", "k_interior", "remove_cell", "up", "down"}:
            return "Iterator" if node.name in {"up", "down"} else "Self"
        if node.name in {
            "arm_lengths", "cells", "dominated_partitions", "evaluation", "hook_lengths",
            "k_row_lengths", "outer_rim", "rim", "to_list", "zero_one_sequence",
        }:
            return "list"
        if node.name in {"centralizer_size", "content", "get_part", "hook_product", "k_size", "residue", "size", "weighted_size"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"crank", "frobenius_rank", "length", "sign"}:
            return "int"
        if node.name == "conjugacy_class_size":
            return "'sage.rings.rational.Rational'"
        if node.name == "dimension":
            return "'sage.rings.rational.Rational'"
        if node.name == "character_polynomial":
            return "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'"
        if node.name == "dual_equivalence_graph":
            return "'sage.graphs.graph.Graph'"

    if owner_name == "PartitionTuple":
        # Partition-tuple combinatorics has stable scalar/container results;
        # only the parent-generated element class is represented by the public
        # ``PartitionTuple`` constructor in the stub surface.
        if node.name in {
            "_latex_diagram", "_latex_exp_high", "_latex_exp_low",
            "_latex_list", "_latex_young_diagram",
        }:
            return "str"
        if node.name == "pp":
            return "None"
        if node.name in {"cells", "to_list", "young_subgroup_generators"}:
            return "list"
        if node.name in {"up", "down"}:
            return "Iterator['sage.combinat.partition_tuple.PartitionTuple']"
        if node.name in {"level", "defect"}:
            return "int"
        if node.name == "size":
            return "'sage.rings.integer.Integer'"
        if node.name in {"arm_length", "leg_length", "hook_length", "_initial_degree"}:
            return "'sage.rings.integer.Integer'"
        if node.name == "content":
            return (
                "'sage.rings.integer.Integer | "
                "sage.rings.finite_rings.integer_mod.IntegerMod_int'"
            )
        if node.name == "content_tableau":
            return "'sage.combinat.tableau_tuple.TableauTuple'"
        if node.name == "initial_column_tableau":
            return "'sage.combinat.tableau_tuple.StandardTableauTuple'"
        if node.name in {"garnir_tableau", "top_garnir_tableau"}:
            return "'sage.combinat.tableau_tuple.TableauTuple' | bool"
        if node.name in {"add_cell", "remove_cell"}:
            return "'sage.combinat.partition_tuple.PartitionTuple'"
        if node.name == "dominates":
            return "bool"
        if node.name == "young_subgroup":
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'"

    if owner_name == "FiniteWord_class":
        if node.name in {
            "coerce", "concatenate", "__pow__", "schuetzenberger_involution",
            "foata_bijection", "to_integer_word", "reversal", "longest_common_suffix",
            "lps", "palindromic_closure", "border", "primitive", "longest_common_subword",
            "return_words_derivate", "delta", "delta_derivate", "delta_derivate_left",
            "delta_derivate_right", "phi", "phi_inv", "iterated_left_palindromic_closure",
            "apply_permutation_to_positions", "apply_permutation_to_letters", "minimal_conjugate",
            "swap", "swap_increase", "swap_decrease", "sturmian_desubstitute_as_possible",
            "BWT", "conjugate_position",
        }:
            return "Self" if node.name != "conjugate_position" else "int | None"
        if node.name in {"topological_entropy"}:
            return "'sage.rings.rational.Rational | sage.symbolic.expression.Expression'"
        if node.name in {"reduced_rauzy_graph"}:
            return "'sage.graphs.digraph.DiGraph'"
        if node.name in {
            "length_border", "length_maximal_palindrome", "longest_forward_extension",
            "longest_backward_extension", "number_of_factor_occurrences",
            "number_of_subword_occurrences", "defect", "abelian_complexity",
        }:
            return "'sage.rings.integer.Integer | int'"
        if node.name == "palindromic_lacunas_study":
            return "tuple"
        if node.name in {"crochemore_factorization", "overlap_partition"}:
            return "list"
        if node.name == "robinson_schensted":
            return "tuple"
        if node.name == "to_monoid_element":
            return "'sage.monoids.free_monoid_element.FreeMonoidElement'"
        if node.name in {"factor_iterator"}:
            return "Iterator"
        if node.name in {"good_suffix_table", "prefix_function_table", "quasiperiods"}:
            return "list"
        if node.name in {"charge", "factor_complexity", "find", "length", "minimal_period", "palindromic_complexity", "primitive_length", "rfind"}:
            return "int"
        if node.name in {"cocharge", "degree", "major_index", "number_of_factors", "number_of_inversions"}:
            return "'sage.rings.integer.Integer'"
        if node.name == "critical_exponent":
            return "'sage.rings.rational.Rational'"
        if node.name == "evaluation_partition":
            return "'sage.combinat.partition.Partition'"
        if node.name == "rauzy_graph":
            return "'sage.graphs.digraph.DiGraph'"
        if node.name == "standard_factorization":
            return "tuple"
        if node.name == "standard_permutation":
            return "'sage.combinat.permutation.StandardPermutation'"

    if owner_name == "Tableau":
        if node.name in {"anti_restrict"}:
            return "'sage.combinat.skew_tableau.SkewTableau'"
        if node.name in {"atom", "components", "corners", "k_weight", "reduced_column_word", "reduced_row_word", "to_chain", "to_list", "weight"}:
            return "list"
        if node.name in {"charge", "content", "height", "major_index", "size"}:
            return "int"
        if node.name in {"cocharge", "codegree", "degree", "inversion_number"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"check", "first_column_descent", "first_row_descent"}:
            return "None"
        if node.name in {"column_stabilizer", "row_stabilizer"}:
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'"
        if node.name in {"evacuation", "promotion", "promotion_inverse", "restrict", "right_key_tableau", "schensted_insert", "schuetzenberger_involution"}:
            return "Self"
        if node.name in {"restriction_shape", "shape"}:
            return "'sage.combinat.partition.Partition'"
        if node.name == "reading_word_permutation":
            return "'sage.combinat.permutation.StandardPermutation'"
        if node.name == "to_sign_matrix":
            return "'sage.matrix.matrix_integer_dense.Matrix_integer_dense'"
        if node.name in {"to_word", "to_word_by_column", "to_word_by_row"}:
            return "'sage.combinat.words.word.FiniteWord_list'"

    if owner_name == "Permutation":
        if node.name in {
            "__next__", "prev", "__mul__", "__rmul__", "left_action_product",
            "right_action_product", "ishift", "iswitch", "reverse", "complement",
            "forget_cycles", "remove_extra_fixed_points", "retract_plain",
            "retract_direct_product", "retract_okounkov_vershik", "shifted_concatenation",
        }:
            return "Self"
        if node.name == "_gap_":
            return "'cypari2.gen.Gen'"
        if node.name in {"to_tableau_by_shape", "left_tableau", "right_tableau"}:
            return "'sage.combinat.tableau.Tableau'"
        if node.name == "to_permutation_group_element":
            return "'sage.groups.perm_gps.permgroup_element.PermutationGroupElement'"
        if node.name == "to_matrix":
            return MATRIX_ELEMENT_UNION
        if node.name in {"number_of_longest_increasing_subsequences", "number_of_reduced_words", "number_of_nth_roots", "multi_major_index"}:
            return "'sage.rings.integer.Integer | int'"
        if node.name in {"cycle_type", "hyperoctahedral_double_coset_type", "increasing_tree_shape", "binary_search_tree_shape", "RS_partition"}:
            return "'sage.combinat.partition.Partition'"
        if node.name in {"fundamental_transformation_inverse", "destandardize"}:
            return "'sage.combinat.words.finite_word.FiniteWord_list'"
        if node.name in {"rothe_diagram", "idescents_signature", "to_major_code", "action"}:
            return "list"
        if node.name == "rank_matrix":
            return MATRIX_ELEMENT_UNION
        if node.name == "descent_polynomial":
            return POLYNOMIAL_RETURN_UNION
        if node.name in {"bruhat_succ_iterator", "bruhat_pred_iterator", "nth_roots"}:
            return "Iterator"
        if node.name == "permutation_poset":
            return FINITE_POSET_RETURN_UNION
        if node.name == "show":
            return "None"

    if owner_name == "EllipticCurve_generic":
        if node.name in {"a1", "a2", "a3", "a4", "a6", "b2", "b4", "b6", "b8", "c4", "c6", "discriminant", "j_invariant", "two_division_polynomial"}:
            return MATRIX_SCALAR_UNION
        if node.name in {"division_polynomial", "division_polynomial_0", "_multiple_x_denominator", "_multiple_x_numerator"}:
            return MATRIX_POLYNOMIAL_UNION
        if node.name == "_defining_params_":
            return "tuple"
        if node.name in {"__pari__", "pari_curve"}:
            return "'cypari2.gen.Gen'"
        if node.name == "assume_base_ring_is_field":
            return "None"
        if node.name == "formal_group":
            return "'sage.schemes.elliptic_curves.formal_group.EllipticCurveFormalGroup'"

    if owner_name == "PermutationGroup_generic":
        if node.name in {"gen", "one", "random_element"}:
            return "'sage.groups.perm_gps.permgroup_element.PermutationGroupElement'"
        if node.name in {"base", "gens_small"}:
            return "list"
        if node.name == "orbit":
            return "tuple"
        if node.name in {"stabilizer", "subgroup", "_subgroup_constructor", "socle"}:
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_subgroup'"
        if node.name in {"intersection", "holomorph", "semidirect_product"}:
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'"
        if node.name == "disjoint_direct_product_decomposition":
            return "set"
        if node.name == "construction":
            return "tuple | None"
        if node.name in {"exponent", "order", "group_primitive_id"}:
            return "'sage.rings.integer.Integer'"
        if node.name in {"largest_moved_point", "smallest_moved_point"}:
            return "int"
        if node.name in {"composition_series", "conjugacy_classes_representatives", "conjugacy_classes_subgroups", "derived_series", "lower_central_series", "maximal_normal_subgroups", "minimal_generating_set", "minimal_normal_subgroups", "normal_subgroups", "orbits", "transversals", "upper_central_series"}:
            return "list"
        if node.name in {"center", "centralizer", "fitting_subgroup", "frattini_subgroup", "normalizer", "solvable_radical", "sylow_subgroup"}:
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_subgroup'"
        if node.name in {"commutator", "conjugate"}:
            return "Self"
        if node.name == "as_finitely_presented_group":
            return "'sage.groups.finitely_presented.FinitelyPresentedGroup'"
        if node.name == "domain":
            return "'sage.sets.finite_enumerated_set.FiniteEnumeratedSet'"
        if node.name == "group_id":
            return "list"
        if node.name in {"character", "trivial_character"}:
            return "'sage.groups.class_function.ClassFunction'"
        if node.name == "minimal_generating_set":
            return "list"

    if owner_name == "SimplicialComplex":
        if node.name in {"h_vector", "g_vector", "f_triangle", "h_triangle", "restriction_sets"}:
            return "list"
        if node.name in {"vertices"}:
            return "tuple"
        if node.name in {"maximal_faces", "minimal_nonfaces"}:
            return "set"
        if node.name == "faces":
            return "dict"
        if node.name == "face_iterator":
            return "Iterator"
        if node.name in {"product", "join", "cone", "suspension", "disjoint_union", "wedge", "connected_sum", "link", "star", "generated_subcomplex", "alexander_dual", "barycentric_subdivision", "n_skeleton", "connected_component", "fixed_complex", "decone", "intersection"}:
            return "Self"
        if node.name in {"add_face", "remove_face", "remove_faces", "set_immutable"}:
            return "None"
        if node.name == "stellar_subdivision":
            return "Self | None"
        if node.name == "graph":
            return "'sage.graphs.graph.Graph'"
        if node.name == "delta_complex":
            return "'sage.topology.delta_complex.DeltaComplex'"
        if node.name == "chain_complex":
            return "'sage.homology.chain_complex.ChainComplex'"
        if node.name == "automorphism_group":
            return "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'"
        if node.name == "fundamental_group":
            return "'sage.groups.finitely_presented.FinitelyPresentedGroup'"
        if node.name in {"stanley_reisner_ring", "_stanley_reisner_base_ring"}:
            return "'sage.rings.polynomial.polynomial_quotient_ring.PolynomialQuotientRing_field_with_category'"
        if node.name == "is_partitionable":
            return "bool | tuple"
        if node.name == "bigraded_betti_number":
            return "'sage.rings.integer.Integer | int'"

    # Graph/Digraph share a large, stable protocol.  The generated stubs often
    # omit returns because the implementation lives in ``generic_graph.py``;
    # use the documented outer result here while leaving vertex/edge payloads
    # unresolved (they are user-defined and cannot be inferred statically).
    graph_owner = bool(
        owner_name
        and (owner_name == "GenericGraph" or owner_name.casefold().endswith("graph"))
    )
    if graph_owner:
        if node.name in {"__eq__", "__ne__"}:
            return "bool"
        if node.name in {"__add__", "__mul__", "__rmul__", "_subgraph_by_adding", "_subgraph_by_deleting"}:
            return "Self"
        if node.name in {"_matrix_"}:
            return MATRIX_ELEMENT_UNION
        if node.name in {"allow_multiple_edges", "_copy_attribute_from", "_scream_if_not_simple", "_scream_if_immutable"}:
            return "None"
        if node.name.startswith(("is_", "has_", "allows_")) or node.name in {
            "weighted", "antisymmetric", "is_immutable",
        }:
            return "bool"
        if node.name in {
            "to_dictionary", "get_vertices", "shortest_paths", "shortest_path_lengths",
            "shortest_path_all_pairs", "distance_all_pairs", "distances_distribution",
            "get_embedding", "get_pos", "pagerank", "clustering_coeff", "cluster_triangles",
            "to_networkx",
        }:
            return "dict"
        if node.name in {
            "adjacency_matrix", "incidence_matrix", "distance_matrix",
            "weighted_adjacency_matrix", "kirchhoff_matrix", "katz_matrix",
        }:
            return MATRIX_ELEMENT_UNION
        if node.name in {
            "loops", "loop_edges", "loop_vertices", "multiple_edges",
            "edge_boundary", "edges_incident", "edge_labels", "vertices", "neighbors",
            "degree_histogram", "degree_sequence", "eulerian_circuit", "minimum_cycle_basis",
            "cycle_basis", "all_paths", "all_simple_paths", "all_simple_cycles",
            "connected_components", "connected_components_subgraphs",
            "connected_component_containing_vertex", "connected_components_sizes",
            "biconnected_components", "biconnected_components_subgraphs",
            "edge_disjoint_paths", "vertex_disjoint_paths", "min_spanning_tree",
            "shortest_path", "vertex_boundary", "eigenvectors", "eigenspaces",
        }:
            return "list"
        if node.name == "random_edge":
            return "tuple"
        if node.name in {
            "random_vertex_iterator", "random_edge_iterator", "vertex_iterator",
            "neighbor_iterator", "edge_iterator", "degree_iterator", "all_paths_iterator",
            "shortest_simple_paths", "all_cycles_iterator", "connected_subgraph_iterator",
            "subgraph_search_iterator", "subgraph_decompositions", "breadth_first_search",
            "depth_first_search",
        }:
            return "Iterator"
        if node.name in {
            "order", "size", "number_of_loops", "number_of_connected_components",
            "number_of_biconnected_components", "degree_to_cell", "triangles_count",
            "shortest_path_length", "distance", "girth", "odd_girth", "edge_connectivity",
            "vertex_connectivity", "number_of_spanning_trees", "genus", "crossing_number",
        }:
            return "'sage.rings.integer.Integer | int'"
        if node.name in {"density", "average_degree", "average_distance", "wiener_index"}:
            return "'sage.rings.rational.Rational | float'"
        if node.name in {
            "random_subgraph", "complement", "line_graph", "to_simple", "disjoint_union",
            "union", "cartesian_product", "tensor_product", "lexicographic_product",
            "strong_product", "disjunctive_product", "canonical_label", "transitive_closure",
            "transitive_reduction", "planar_dual", "reduced_homeomorphic_graph",
        }:
            return "Self"
        # Graph mutators are in-place operations in both ``Graph`` and
        # ``DiGraph``; their Python contract is explicitly ``None``.  Keeping
        # this separate from the payload-producing methods above avoids
        # exposing a spurious graph value after calls such as ``G.add_edge``.
        if node.name in {
            "add_clique", "add_cycle", "add_edge", "add_edges", "add_path",
            "add_vertex", "add_vertices", "clear", "delete_edge", "delete_edges",
            "delete_multiedge", "delete_vertex", "delete_vertices", "merge_vertices",
            "remove_loops", "remove_multiple_edges", "relabel", "set_edge_label",
            "set_embedding", "set_latex_options", "set_pos", "set_vertex",
            "set_vertices", "subdivide_edge", "subdivide_edges",
        }:
            return "None"
        if node.name in {"name", "graphviz_string"}:
            return "str"
        if node.name in {"steiner_tree"}:
            return "Self"
        if node.name in {
            "automorphism_group", "centralizer", "edge_disjoint_spanning_trees",
        }:
            return "list" if node.name == "edge_disjoint_spanning_trees" else "'sage.groups.perm_gps.permgroup.PermutationGroup_generic'"
        if node.name in {
            "centrality_betweenness", "centrality_closeness", "distance_all_pairs",
        }:
            return "dict"
        if node.name in {"layout", "layout_planar", "layout_forest", "layout_graphviz"}:
            return "dict"
        if node.name in {"edge_cut", "vertex_cut", "multiway_cut", "max_cut"}:
            return "'sage.rings.integer.Integer | int | list | tuple'"
        if node.name in {"flow", "_ford_fulkerson"}:
            return "'sage.rings.integer.Integer | int | float | dict | tuple'"
        if node.name == "multicommodity_flow":
            return "dict"
        if node.name == "nowhere_zero_flow":
            return "Self | None"
        if node.name in {"edge_polytope", "symmetric_edge_polytope"}:
            return POLYHEDRON_RETURN_UNION
        if node.name == "show":
            return "None"
        if node.name in {
            "clustering_average", "cluster_transitivity", "effective_resistance",
        }:
            return "'sage.rings.rational.Rational | float'"
        if node.name in {
            "diameter", "eccentricity", "radius", "arboricity", "chromatic_number",
            "clique_number", "maximum_average_degree", "fractional_clique_number",
        }:
            return "'sage.rings.integer.Integer | int'"
        if node.name in {"bipartite_sets"}:
            return "tuple"
        if node.name in {"clique_maximum", "independent_set", "vertex_cover", "coloring", "feedback_vertex_set", "hamiltonian_cycle", "hamiltonian_path", "longest_cycle", "longest_path", "traveling_salesman_problem"}:
            return "list"
        if node.name in {"antipodal_graph", "bipartite_double", "distance_graph", "folded_graph", "join", "to_simple"}:
            return "Self"
        if node.name in {"graph6_string", "sparse6_string", "write_to_eps"}:
            return "str" if node.name != "write_to_eps" else "None"
        if node.name in {"seidel_adjacency_matrix", "common_neighbors_matrix"}:
            return MATRIX_ELEMENT_UNION
        if node.name == "plot3d":
            return "'sage.plot.plot3d.base.Graphics3d'"
        if node.name == "characteristic_polynomial":
            return "'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint'"
        if node.name in {"faces", "min_spanning_tree"}:
            return "list"
        if node.name in {"n_faces", "subgraph_search_count"}:
            return "'sage.rings.integer.Integer | int'"
        if node.name == "power":
            return "Self"
        if node.name in {"contract_edge", "contract_edges", "export_to_file", "graphviz_to_file_named", "show3d"}:
            return "None"

    # Polynomial backends frequently override these methods in Cython without
    # repeating the base-class return annotation.  Their source contracts are
    # stable across FLINT/NTL/generic implementations: degree is an integer,
    # gcd/shift/reverse/truncate stay in the polynomial parent, and Euclidean
    # division returns quotient/remainder from that same parent.  Restrict the
    # rule to polynomial owners so unrelated graph/group ``degree`` methods do
    # not inherit a false scalar contract.
    if owner_name and "polynomial" in owner_name.casefold():
        if owner_name in {
            "MPolynomialRing_base", "MPolynomialRing_libsingular",
            "MPolynomialRing_polydict", "MPolynomialRing_polydict_domain",
        }:
            if node.name in {"_repr_", "repr_long", "_latex_", "_magma_init_", "_gap_init_"}:
                return "str"
            if node.name in {"is_integral_domain", "is_noetherian", "is_exact", "is_field"}:
                return "bool"
            if node.name in {"characteristic", "ngens", "krull_dimension"}:
                return "'sage.rings.integer.Integer | int'"
            if node.name in {"construction"}:
                return "tuple"
            if node.name in {"gen", "random_element", "monomial", "interpolation"}:
                return MULTIVARIATE_POLYNOMIAL_RETURN_UNION
            if node.name in {"some_elements", "monomials_of_degree"}:
                return "list"
            if node.name == "variable_names_recursive":
                return "tuple"
        if owner_name in {
            "MPolynomial", "MPolynomial_element", "MPolynomial_polydict",
            "MPolynomial_libsingular", "MPolynomial_libsingular_base",
        }:
            if node.name in {"leading_support", "trailing_support", "args", "degrees"}:
                return "tuple"
            if node.name in {"coefficients", "gradient"}:
                return "list"
            if node.name == "monomials":
                return "list"
            if node.name in {"exponents", "monomial_coefficients"}:
                return "list" if node.name == "exponents" else "dict"
            if node.name in {"homogeneous_components"}:
                return "dict"
            if node.name in {"iterator_exp_coeff", "__iter__"}:
                return "Iterator"
            if node.name == "_symbolic_":
                return "'sage.symbolic.expression.Expression'"
            if node.name == "subs":
                return MULTIVARIATE_POLYNOMIAL_RETURN_UNION
            if node.name in {"_magma_init_", "_giac_init_"}:
                return "str"
            if node.name in {"number_of_terms"}:
                return "int"
            if node.name in {"total_degree", "weighted_degree", "nvariables"}:
                return "'sage.rings.integer.Integer | int'"
            if node.name in {"variables"}:
                return "tuple"
            if node.name in {"homogenize", "_homogenize", "inverse_of_unit", "inverse_mod", "reduce", "numerator"}:
                return "Self"
            if node.name in {"change_ring", "map_coefficients"}:
                return MULTIVARIATE_POLYNOMIAL_RETURN_UNION
            if node.name == "univariate_polynomial":
                return POLYNOMIAL_RETURN_UNION
            if node.name == "lift":
                return "list"
            if node.name == "newton_polytope":
                return POLYHEDRON_RETURN_UNION
            if node.name == "sylvester_matrix":
                return MATRIX_ELEMENT_UNION
            if node.name in {"nth_root", "crt"}:
                return "Self"
            if node.name == "polynomial":
                return POLYNOMIAL_RETURN_UNION
            if node.name == "reduced_form":
                return "Self | tuple"
            if node.name in {"__eq__", "__ne__"}:
                return "bool"
            if node.name in {"_derivative", "integral", "resultant", "lcm", "add_m_mul_q", "sub_m_mul_q"}:
                return "Self"
            if node.name in {"_singular_init_", "_repr_short_"}:
                return "str"
            if node.name == "variable":
                return MULTIVARIATE_POLYNOMIAL_RETURN_UNION
        if owner_name == "Polynomial":
            if node.name in {"is_cyclotomic", "is_square"}:
                return "bool"
            if node.name == "prec":
                return "int"
            if node.name in {"change_ring", "subs"}:
                return POLYNOMIAL_RETURN_UNION
            if node.name in {"__truediv__", "__invert__"}:
                return POLYNOMIAL_POWER_UNION
            if node.name == "squarefree_decomposition":
                return "'sage.structure.factorization.Factorization'"
            if node.name == "sylvester_matrix":
                return MATRIX_ELEMENT_UNION
            if node.name == "newton_polytope":
                return POLYHEDRON_RETURN_UNION
            if node.name in {"root_field", "splitting_field"}:
                return "'sage.rings.number_field.number_field.NumberField_absolute'"
        if node.name == "degree":
            return "'sage.rings.integer.Integer | int'"
        if node.name in {"derivative", "_derivative_"}:
            # Univariate and multivariate polynomial derivatives remain in
            # the receiver's polynomial parent (the variable/argument only
            # selects the derivation direction).
            return "Self"
        if node.name == "gcd":
            return "Self"
        if node.name == "quo_rem":
            return "tuple[Self, Self]"
        if node.name in {"shift", "reverse", "truncate"}:
            return "Self"
        if node.name in {"valuation", "ord"}:
            # The zero polynomial has +Infinity valuation; nonzero values are
            # Sage/native integers depending on the backend.
            return CARDINALITY_RETURN_UNION

    # Several low-level element implementations state the parent condition
    # explicitly (``Add two ... with the same parent``).  That is enough to
    # preserve the concrete receiver, even when the class name does not end
    # in ``Element`` (for example ``MPComplexNumber`` or ``LaurentSeries``).
    # Precision lifts carry the same parent guarantee and are likewise
    # receiver-preserving.  Rich-comparison hooks are excluded: their result
    # is a predicate, not another element.
    if re.search(r"\bsame parent(?:s)?\b", summary, re.IGNORECASE):
        if node.name in {"_add_", "_sub_", "_mul_", "_div_", "_lmul_", "_rmul_", "lift_to_precision"}:
            return "Self"

    # Concrete polynomial backends repeat the arithmetic protocol in several
    # Cython classes and often omit the inherited annotation.  These internal
    # operations are parent-preserving; public ``__mul__``/``__call__`` remain
    # unresolved because their operand can select a vector or scalar branch.
    if owner_name and "polynomial" in owner_name.casefold() and not owner_name.casefold().endswith("ring"):
        if node.name in {
            "_add_", "_sub_", "_mul_", "_lmul_", "_rmul_", "_neg_",
            "__neg__", "__pos__", "__lshift__", "__rshift__", "__mod__",
            "_mod_", "__floordiv__", "_floordiv_",
        }:
            return "Self"
        if node.name == "__pow__":
            return POLYNOMIAL_POWER_UNION

    # ``IntegerMod_int*``/``IntegerMod_gmp`` are concrete residue elements,
    # but their class names do not contain the ``Element`` suffix used by the
    # generic arithmetic rule below.  Their low-level ring operations always
    # return the same residue implementation selected by the modulus.
    if owner_name and owner_name.casefold().startswith("integermod"):
        if node.name in {"_add_", "_sub_", "_mul_", "_div_", "_neg_", "__neg__", "__pos__"}:
            return "Self"
        if node.name == "__pow__":
            return "Self"
        if node.name == "__pari__":
            return "'cypari2.gen.Gen'"
        if node.name == "_integer_":
            return "'sage.rings.integer.Integer'"
        if node.name == "_rational_":
            return "'sage.rings.rational.Rational'"
        if node.name == "valuation":
            return CARDINALITY_RETURN_UNION
        if node.name == "gcd":
            return "Self"
        if node.name == "lift":
            return "'sage.rings.integer.Integer'"

    # Matrix implementations share the same in-place storage protocol for
    # low-level elementwise arithmetic.  The public multiplication operation
    # is intentionally excluded because matrix-vector products return a
    # different parent-dependent family.
    if owner_name and owner_name.casefold().startswith("matrix"):
        if node.name in {"_add_", "_sub_", "_lmul_", "_rmul_", "__neg__", "__pos__"}:
            return "Self"
        # The matrix0 transformation helpers explicitly document that they
        # allocate and return a *new matrix*.  Their implementation delegates
        # construction to the receiver's concrete ``new_matrix`` path, so
        # ``Self`` preserves the dense/sparse implementation selected by the
        # caller without collapsing it to matrix0.Matrix.
        if node.name.startswith("with_") and re.search(
            r"\bnew\s+matrix\b|新(?:的)?矩阵", summary, re.IGNORECASE
        ):
            return "Self"

    # NTL Cython wrappers are concrete value objects rather than abstract
    # Sage parents.  Their arithmetic/linear-algebra hooks return the same
    # wrapper selected by the NTL modulus/context; matrix dimensions and rich
    # comparison are the two stable scalar protocol exceptions.  Keep
    # multiplication and indexing out because their operand/index can switch
    # between a matrix, vector, or coefficient implementation.
    if owner_name and owner_name.casefold().startswith("ntl_"):
        if node.name in {"__add__", "__sub__", "__neg__", "__pos__", "__pow__", "__invert__"}:
            return "Self"
        if node.name == "__richcmp__":
            return "bool"
        if node.name in {"NumRows", "NumCols"}:
            return "int"
        if node.name in {"transpose", "derivative", "reverse", "truncate", "square", "gcd", "lcm", "primitive_part"}:
            return "Self"
        if node.name in {"quo_rem", "pseudo_quo_rem", "xgcd"}:
            return "tuple[Self, Self]" if node.name != "xgcd" else "tuple[Self, Self, Self]"

    # Concrete element arithmetic is implemented after Sage's coercion layer
    # has selected a common parent, so these low-level operations preserve the
    # receiver implementation.  Keep the receiver suffix guard: matrix and
    # other parent-level APIs intentionally have separate overload contracts.
    # The torsion-quadratic-module ``_mul_`` is an inner product and is
    # excluded because it returns a scalar rather than another element.
    if (
        owner_name
        and re.search(r"(?:Element|element)$", owner_name)
        and node.name in {"_add_", "_sub_", "_mul_", "_lmul_", "_rmul_", "_neg_", "__neg__", "__pos__"}
        and not (owner_name == "TorsionQuadraticModuleElement" and node.name == "_mul_")
    ):
        return "Self"

    # Sage's numeric backends use a few stable names that do not end in
    # ``Element`` (``RealNumber``, ``ComplexBall``, ``MPComplexNumber``).
    # Their unary, inverse, and power operations are receiver-preserving in
    # Sage 10.9; keep this rule limited to those scalar implementation names
    # so parent factories and symbolic expressions remain fail-closed.
    scalar_owner = owner_name.rsplit(".", 1)[-1] if owner_name else ""
    scalar_owner = scalar_owner or ""
    if (
        scalar_owner.endswith(("Number", "Ball"))
        or scalar_owner.startswith(("RealInterval", "ComplexInterval", "pAdic"))
        or scalar_owner in {"FpTElement", "FractionFieldElement", "WittVector"}
    ) and node.name in {
        "_add_", "_sub_", "_mul_", "_div_", "_neg_", "_lmul_", "_rmul_",
        "__neg__", "__pos__", "__invert__", "__pow__",
    }:
        return "Self"

    # Multiplicative inverses and powers of concrete algebra/ring/group
    # elements preserve the implementation selected by their parent.  Keep
    # the abstract protocol classes and the two documented exceptions out:
    # ``Element`` delegates through coercion, while free-module inversion /
    # powering is explicitly unsupported and cluster-algebra division can
    # leave the parent.
    if (
        owner_name
        and re.search(r"(?:Element|element)$", owner_name)
        and owner_name not in {
            "Element",
            "RingElement",
            "AdditiveGroupElement",
            "MultiplicativeGroupElement",
            "InfinityElement",
            "FreeModuleElement",
            "ClusterAlgebraElement",
        }
        and node.name in {"__invert__", "__pow__"}
    ):
        return "Self"

    # Conjugation is an involution on Sage's concrete element/group/ideal
    # implementations.  The module-level combinatorics helper has no
    # receiver (``owner_name`` is absent) and therefore remains dynamic.
    if node.name == "conjugate" and owner_name:
        return "Self"

    # ``list()`` methods in Sage return a materialized Python list.  Keep the
    # two known interface methods whose names are compatibility shims for
    # non-Python containers fail-closed; their docs do not promise a Python
    # list value.
    if node.name == "list" and owner_name not in {"MPowerSeries", "Singular"}:
        return "list"

    # Feature modules expose a small list of feature descriptors.  The
    # package-level ``sage.features.all.all_features`` is the sole generator
    # variant and is overridden by its curated module contract below.
    if node.name == "all_features":
        return "list"

    # Group/element/morphism order can be finite, infinite, or intentionally
    # unknown (some APIs return ``None`` instead of raising).  This union is
    # more precise than UNKNOWN and matches Sage's documented alternatives.
    # Parent construction is represented uniformly in Sage as a
    # ``(construction_functor, base)`` pair, or ``None`` when the parent is
    # not functorial.  This fallback is intentionally after owner-specific
    # contracts so a narrower verified tuple/None result is retained.
    if node.name == "construction":
        return "tuple | None"

    # Explicit matrix/polynomial result nouns identify the outer Sage family;
    # the concrete backend remains selected by the receiver and arguments.
    # Do not infer from a bare method name because some APIs use ``matrix`` or
    # ``polynomial`` as input/configuration accessors instead.
    if node.name in {"matrix", "generator_matrix"} and re.search(
        r"\b(?:return|produce|create|convert|version|as|generator)\b.*\bmatrix\b|\bmatrix\b.*\b(?:return|version|from)\b",
        summary,
        re.IGNORECASE,
    ):
        return MATRIX_ELEMENT_UNION
    if node.name == "polynomial" and re.search(
        r"\b(?:return|produce|create|convert|underlying|associated|defining|bare)\b.*\bpolynomial\b|\bpolynomial\b.*\b(?:return|associated|defining)\b",
        summary,
        re.IGNORECASE,
    ) and not re.search(r"\bproof\s+strategy\b|\bcontrols?\b", summary, re.IGNORECASE):
        suffix = " | None" if re.search(r"\bif\b.*\b(?:actually|possible)\b", summary, re.IGNORECASE) else ""
        return f"{POLYNOMIAL_RETURN_UNION}{suffix}"

    # Group/element/morphism order can be finite, infinite, or intentionally
    # unknown (some APIs return ``None`` instead of raising).  This union is
    # more precise than UNKNOWN and matches Sage's documented alternatives.
    if node.name == "order":
        return ORDER_RETURN_UNION
    return None


def _doc_visual_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None = None,
) -> str | None:
    """Resolve stable outer types for documented visualization adapters.

    Sage's plotting APIs return either the 2-D ``Graphics`` container or a
    3-D ``Graphics3d``/primitive subclass.  This rule is driven by the
    documentation's graphical-result wording and excludes external CAS
    command adapters whose ``plot`` method sends a command and has no Sage
    graphics payload.  Matrix conversion hooks likewise promise a Sage
    matrix, whose concrete backend is selected by the receiver/parent.
    """
    normalized = re.sub(r"\s+", " ", summary or "").strip()
    if node.name == "plot":
        if not normalized or re.search(
            r"\b(?:input|command|cmd|interface|r\s+plot|save\s+to)\b",
            normalized,
            re.IGNORECASE,
        ):
            return None
        if not re.search(
            r"\b(?:plot|graphical|graphics?|picture|drawing|visuali[sz])\b",
            normalized,
            re.IGNORECASE,
        ):
            return None
        if re.search(r"\bGraphics3d\b", normalized):
            return "'sage.plot.plot3d.base.Graphics3d'"
        if re.search(r"\bGraphics\b", normalized):
            return "'sage.plot.graphics.Graphics'"
        return "'sage.plot.graphics.Graphics | sage.plot.plot3d.base.Graphics3d'"
    if node.name == "_matrix_" and re.search(
        r"\b(?:return|produce|convert|version|as)\b.*\bmatrix\b|\bmatrix\b.*\b(?:return|version|from)\b",
        normalized,
        re.IGNORECASE,
    ):
        return MATRIX_ELEMENT_UNION
    return None


def _doc_matrix_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
) -> str | None:
    """Resolve matrix-family results from explicit result nouns.

    Matrix implementations share a large protocol inherited from
    ``matrix0.Matrix``.  Their result backend is selected by the parent and
    cannot be represented by that public base; use the concrete implementation
    union only when the documentation states that the result is a matrix,
    vector, or polynomial.  The rule is deliberately wording-driven and does
    not enumerate methods/classes, while parameter-dependent unions remain
    guarded by the caller's existing conditional checks.
    """
    if not owner_name or not re.search(r"matrix", owner_name, re.IGNORECASE):
        return None
    normalized = re.sub(r"\s+", " ", (summary or "").replace(chr(96), "")).strip()
    if not normalized or re.search(r"\b(?:or|either|depending|if|otherwise)\b", normalized, re.IGNORECASE):
        return None
    if not re.search(r"\b(?:return|create|construct|produce|compute|convert|change|transpose|augment|inverse|echelon|normal)\w*\b", normalized, re.IGNORECASE):
        return None
    if re.search(r"\b(?:determinant|trace|density|coefficient\s+bound|coefficient\s+norm)\b", normalized, re.IGNORECASE):
        return MATRIX_SCALAR_UNION
    if re.search(r"\b(?:ambient\s+)?free\s+module\b", normalized, re.IGNORECASE) or re.search(
        r"模块", summary or ""
    ):
        return MATRIX_SPACE_MODULE_UNION
    if re.search(r"\b(?:vector|free\s+module)\b", normalized, re.IGNORECASE):
        return VECTOR_ELEMENT_UNION
    if re.search(r"\bpolynomial\b", normalized, re.IGNORECASE):
        return POLYNOMIAL_RETURN_UNION
    if re.search(r"\b(?:matrix|hessenberg|echelon|normal\s+form|antitranspose|transpose|augmented)\b", normalized, re.IGNORECASE):
        return MATRIX_ELEMENT_UNION
    return None


def _doc_structural_return_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
) -> str | None:
    """Resolve explicit Python container/scalar nouns in return prose.

    A substantial part of Sage's generated documentation states a stable
    outer Python shape only in the summary (for example ``Return a list`` or
    ``Return a tuple of ...``), without an ``OUTPUT`` section.  The shape is
    independent of the mathematical parent and therefore safe to expose, but
    only when the noun is syntactically tied to ``return``.  Phrases that say
    merely ``sequence``, ``array`` or ``element`` remain unresolved because
    their concrete Sage implementation depends on the call arguments.
    """
    normalized = re.sub(r"\s+", " ", summary.replace(chr(96), "")).strip()
    # Only the first summary sentence is a return-shape declaration.  Later
    # explanatory sentences frequently mention another conditional return
    # (``... or None``) or an input container and must not widen/narrow the
    # contract inferred from the leading sentence.
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0].strip()
    # ``A generator ...`` summaries omit an explicit ``Return`` verb but the
    # callable's outer Python contract is still unambiguous.  The yielded
    # element type may remain dynamic; exposing ``Iterator`` is precise for
    # completion and does not guess that element.
    if re.match(r"^(?:a|an|the)\s+generator\b", sentence, re.IGNORECASE):
        return "Iterator"
    if not re.search(
        r"\breturn(?:s|ed|ing)?\b|\b(?:compute|find|calculate|determine|construct|assemble|produce|get|display(?:s|ed)?)\b",
        sentence,
        re.IGNORECASE,
    ):
        return None
    # Limit the evidence to the clause beginning at the return verb.  This
    # prevents an input such as ``Return the value for a list`` from being
    # mistaken for a list-valued result.
    match = re.search(
        r"\b(?:return(?:s|ed|ing)?|compute|find|calculate|determine|construct|assemble|produce|get|display(?:s|ed)?)\b(?P<clause>.*)$",
        sentence,
        re.IGNORECASE,
    )
    if match is None:
        return None
    prefix = sentence[: match.start()]
    # Do not lift a secondary return clause controlled by an option or an
    # earlier conditional sentence (``With get_data return a pair`` is a
    # common predicate pattern).  Such APIs need a parameter-sensitive
    # overload instead of a summary-wide tuple/list guess.
    if re.search(r"\b(?:with|if|when|unless|depending\s+on|otherwise)\s+\w+", prefix, re.IGNORECASE):
        return None
    clause = match.group("clause").strip()
    if not clause:
        return None
    if re.match(r"^(?:a|an|the)\s+set\s+of\s+generators\b", clause, re.IGNORECASE):
        return None

    # A homogeneous container plus an explicit ``or None`` remains an exact
    # union even when the documentation qualifies the branch with
    # ``when``/``if`` (for example an empty result).  Heterogeneous branches
    # such as ``list or tuple`` still remain unresolved below.
    optional_none = bool(re.search(r"(?:,\s*)?\bor\s+(?:none|nothing)\s*[.!?]?$", clause, re.IGNORECASE))
    if optional_none:
        clause = re.sub(r"(?:,\s*)?\bor\s+(?:none|nothing)\s*[.!?]?$", "", clause, flags=re.IGNORECASE).rstrip()
    else:
        # OUTPUT prose also spells the same optional branch as
        # ``... otherwise it returns None``.  Treat only a terminal
        # otherwise/None clause as optional; other conditional alternatives
        # remain unresolved below.
        otherwise_none = re.search(
            r"\botherwise(?:,?\s+it)?\s+returns?\s+(?:none|nothing)\s*[.!?]?$",
            clause,
            re.IGNORECASE,
        )
        if otherwise_none:
            optional_none = True
            clause = clause[: otherwise_none.start()].rstrip(" ,;:")
    conditional = bool(re.search(r"\b(?:unless|otherwise|depending|either|or)\b", clause, re.IGNORECASE))
    if re.search(r"\bif\b", clause, re.IGNORECASE) and conditional is False:
        # Parenthetical qualifiers such as ``if n is specified`` may change
        # the contents or length while preserving the same outer container.
        # They are safe for an explicitly article-led shape (``a tuple``),
        # unlike ``or``/``None`` branches which require an overload.
        clause = re.sub(r"\bif\b", "", clause, flags=re.IGNORECASE)

    # Explicit truth-value alternatives are still one stable Python ``bool``
    # result (``True or False``).  Do not apply this to mixed contracts such
    # as ``True or a coercion`` or ``True and None``.
    if re.match(r"^(?:true|false)\b", clause, re.IGNORECASE):
        if re.search(r"\b(?:and)\s+none\b|\b(?:or)\s+(?:a|an|the)\s+(?!false\b|true\b)", clause, re.IGNORECASE):
            return None
        if re.search(r"\b(?:true|false)\b.*\b(?:or|return)\b.*\b(?:true|false)\b", clause, re.IGNORECASE):
            return "bool"
        if not conditional:
            return "bool"
    if re.match(r"^(?:the\s+)?empty\s+list\s+or\s+tuple\b", clause, re.IGNORECASE):
        return "list | tuple"
    if conditional:
        return None

    # A few stable outer shapes are named directly instead of as ``a
    # tuple``.  Sage's ``shape``/``variables`` accessors expose Python tuples
    # across their concrete implementations, solver backends expose their
    # original clauses as lists, and polynomial characteristic/minimal
    # polynomial APIs return one of Sage's concrete polynomial families.  The
    # noun must be the result immediately after ``return``; input mentions in
    # later prose are intentionally ignored.
    direct_shapes: tuple[tuple[str, str], ...] = (
        (r"^(?:the\s+)?shape\b", "tuple"),
        (r"^(?:the\s+)?output\s+shape\b", "tuple"),
        (r"^(?:the\s+)?variables\b", "tuple"),
        (r"^original\s+clauses\b", "list"),
        (r"^(?:the\s+)?(?:minimal|characteristic)\s+polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"^(?:compute|find|calculate|determine)\s+(?:the\s+)?(?:minimal|characteristic)\s+polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"^(?:a|an|the)\s+(?:(?:new|normalized|reduced|irreducible|monic|univariate|multivariate|Laurent)\s+)?polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"^(?:(?:new|normalized|reduced|irreducible|monic|univariate|multivariate|Laurent)\s+)?polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"^(?:a|an|the)\s+(?:[a-z][a-z0-9'_-]*\s+){1,4}polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"^(?:a|an|the)\s+(?:codeword|vector)\b", VECTOR_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+vector\s+of\b", VECTOR_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+empty\s+string\b", "str"),
        (r"^(?:codeword|vector)\b", VECTOR_ELEMENT_UNION),
        # Element conversion helpers commonly phrase the result as
        # ``Return self as a vector``.  The receiver is a scalar/finite-ring
        # element, so the outer result is still the concrete vector family.
        (r"^(?:self|this)\s+as\s+(?:a|an|the)?\s*vector\b", VECTOR_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+positive\s+real\s+number\b", REAL_NUMBER_RETURN_UNION),
        (r"^(?:a|an|the)\s+finite\s+or\s+infinite\s+real\s+number\b", REAL_OR_INFINITY_RETURN_UNION),
        (r"^as\s+(?:a|an|the)?\s*vector\b", VECTOR_ELEMENT_UNION),
        (r"^(?:an?\s+)?integer\s+or\s+rational\s+number\b", INTEGER_RATIONAL_RETURN_UNION),
        (r"^(?:the\s+)?additive\s+order\b", CARDINALITY_RETURN_UNION),
        (r"^(?:the\s+)?vacancy\s+number\b", "'sage.rings.integer.Integer | int'"),
        (r"^(?:the\s+)?next\s+index\b", "'sage.rings.integer.Integer | int'"),
        (r"^(?:the\s+)?half\s+the\s+perimeter\b", "'sage.rings.integer.Integer | int'"),
        (r"^(?:the\s+)?multiplicative\s+order\b", ORDER_RETURN_UNION),
        (r"^(?:the\s+)?labels\s+along\s+the\s+(?:horizontal|vertical)\s+boundary\b", "list"),
        (r"^(?:the\s+)?image\s+of\s+the\s+coordinates\b", "tuple"),
        (r"^(?:the\s+)?image\s+of\s+the\s+matrix\b", MATRIX_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+(?:(?:sage)\s+)?(?!(?:matrix\s+(?:group|list|morphism)))matrix\b", MATRIX_ELEMENT_UNION),
        (r"^matrix\b(?!\s+list)", MATRIX_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+(?:new|normalized|reduced|irreducible|monic|univariate|multivariate|Laurent\s+)?polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"^(?:a|an|the)\s+(?:codeword|vector)\b", VECTOR_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+vector\s+of\b", VECTOR_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+polyhedron\b", POLYHEDRON_RETURN_UNION),
        (r"^(?:a|an|the)\s+matroid\b", MATROID_RETURN_UNION),
        (r"^(?:a|an|the)\s+finite\s+lattice\b", FINITE_POSET_RETURN_UNION),
        (r"^(?:a|an|the)\s+finite\s+field\b", FINITE_FIELD_UNION),
        # Conversion summaries frequently put the stable outer shape at the
        # end (``... in infix form as a list`` / ``... as a string``).  The
        # clause has already passed the conditional/union guard above, so the
        # explicit ``as`` target is safe to expose without guessing nested
        # Sage element types.
        (r"^.*\bas\s+(?:a|an|the)\s+list\b", "list"),
        (r"^.*\bas\s+(?:a|an|the)\s+(?:tuple|pair)\b", "tuple"),
        (r"^.*\bas\s+(?:a|an|the)\s+(?:dictionary|dict)\b", "dict"),
        (r"^.*\bas\s+(?:a|an|the)\s+string\b", "str"),
        (r"^.*\bas\s+(?:a|an|the)\s+python\s+(?:integer|int|long)\b", "int"),
        (r"^.*\bas\s+(?:a|an|the)\s+integer\b", "'sage.rings.integer.Integer'"),
        (r"^.*\bas\s+(?:a|an|the)\s+(?:boolean|bool)\b", "bool"),
        (r"^(?:(?:a|an|the)\s+)?(?:new\s+)?digraph\b", "'sage.graphs.digraph.DiGraph'"),
        (r"^(?:(?:a|an|the)\s+)?(?:new\s+)?directed\s+graph\b", "'sage.graphs.digraph.DiGraph'"),
        (r"^(?:(?:a|an|the)\s+)?(?:new\s+)?automaton\b", "'sage.combinat.finite_state_machine.Automaton'"),
        (r"^(?:(?:a|an|the)\s+)?(?:new\s+)?transducer\b", "'sage.combinat.finite_state_machine.Transducer'"),
        (r"^(?:a|an|the)\s+knot\b", "'sage.knots.knot.Knot'"),
        (r"^(?:a|an|the)\s+(?:kernel|isogeny|Hilbert\s+class)\s+polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"\bas\s+(?:a|an|the)\s+(?:python\s+)?list\b", "list"),
        (r"\bas\s+(?:a|an|the)\s+(?:python\s+)?(?:tuple|pair)\b", "tuple"),
        (r"\bas\s+(?:a|an|the)\s+(?:python\s+)?(?:dictionary|dict)\b", "dict"),
        (r"\bas\s+(?:a|an|the)\s+(?:python\s+)?set\b", "set"),
        (r"\bas\s+(?:a|an|the)\s+(?:python\s+)?(?:string|str)\b", "str"),
    )
    for pattern, annotation in direct_shapes:
        if re.match(pattern, clause, re.IGNORECASE):
            return f"{annotation} | None" if optional_none else annotation

    patterns: tuple[tuple[str, str], ...] = (
        (r"^(?:a|an|the)?\s*lists?\b|\b(?:a|an|the)\s+lists?\b", "list"),
        (r"^(?:a|an|the)?\s*(?:tuples?|pairs?|triples?)\b|\b(?:a|an|the)\s+(?:tuples?|pairs?|triples?)\b", "tuple"),
        (r"^(?:a|an|the)?\s*(?:dictionaries|dicts|mappings)\b|\b(?:a|an|the)\s+(?:dictionary|dict|mapping)\b", "dict"),
        (r"^(?:a|an|the)\s+set\s+(?:of|containing|consisting)\b", "set"),
        (r"^(?:a|an|the)\s+iterator\b", "Iterator"),
        (r"^(?:a|an|the)\s+generator\b(?=\s+(?:for|over|which|that|of)\b)", "Iterator"),
        (r"^(?:a|an|the)\s+(?:string|str)\b", "str"),
        (r"\bas\s+(?:a|an|the)\s+(?:string|str)\b", "str"),
        (r"^(?:a|an|the)\s+boolean\b", "bool"),
        (r"^(?:a|an|the)\s+integer\b", "'sage.rings.integer.Integer'"),
        (r"^(?:a|an|the)\s+python\s+(?:integer|int)\b", "int"),
        (r"^(?:a|an|the)\s+python\s+(?:float|floating\s+point\s+number)\b", "float"),
    )
    for pattern, annotation in patterns:
        if not re.search(r"\b" + pattern, clause, re.IGNORECASE):
            continue
        return f"{annotation} | None" if optional_none else annotation
    return None


def _doc_structural_output_shape_annotation(output: str) -> str | None:
    """Resolve an explicit outer Python shape in an OUTPUT paragraph.

    OUTPUT sections frequently omit a leading ``Return`` verb (for example
    ``A Sage matrix ...`` or ``a list of values``).  The article-led shape is
    still a complete contract; only terminal ``otherwise None`` branches are
    widened to an optional union, while mixed alternatives stay unresolved.
    """
    normalized = re.sub(r"\s+", " ", (output or "").replace(chr(96), "")).strip()
    if not normalized:
        return None
    if re.match(r"^(?:a|an|the)\s+set\s+of\s+generators\b", normalized, re.IGNORECASE):
        return None
    # Keep only the clause after an explicit ``return`` verb when OUTPUT
    # prose wraps the shape in ``This function returns ...`` or ``If ...,
    # this returns ...``.  The optional branch handling below still sees the
    # terminal ``otherwise None`` marker.
    return_match = re.search(r"\breturns?\s+", normalized, re.IGNORECASE)
    if return_match:
        normalized = normalized[return_match.end() :].strip()
    optional_none = bool(
        re.search(
            r"\botherwise(?:,?\s+it)?\s+returns?\s+(?:none|nothing)\s*[.!?]?$",
            normalized,
            re.IGNORECASE,
        )
        or re.search(r"\bor\s+(?:none|nothing)\s*[.!?]?$", normalized, re.IGNORECASE)
    )
    if optional_none:
        normalized = re.sub(
            r"(?:,\s*)?\bor\s+(?:none|nothing)\s*[.!?]?$",
            "",
            normalized,
            flags=re.IGNORECASE,
        ).rstrip()
        normalized = re.sub(
            r"\botherwise(?:,?\s+it)?\s+returns?\s+(?:none|nothing)\s*[.!?]?$",
            "",
            normalized,
            flags=re.IGNORECASE,
        ).rstrip(" ,;:")
        # A homogeneous result is often guarded by an availability/test
        # clause before the terminal ``otherwise None`` (``a list ... if it
        # can find ... otherwise it returns None``).  The condition changes
        # whether a value exists, not the outer container.  Remove that
        # predicate only when its tail does not introduce another explicit
        # result shape; a branch mentioning ``tuple``/``dict`` remains
        # unresolved and therefore fail-closed.
        if re.search(r"\bif\b", normalized, re.IGNORECASE):
            conditional_tail = re.split(r"\bif\b", normalized, maxsplit=1, flags=re.IGNORECASE)[1]
            if re.search(
                r"\b(?:matrix|polynomial|vector|list|tuple|pair|set|dict|dictionary|object|class|field|ring|group|module|ideal)\b",
                conditional_tail,
                re.IGNORECASE,
            ):
                return None
            normalized = re.split(r"\bif\b", normalized, maxsplit=1, flags=re.IGNORECASE)[0].rstrip(" ,;:")
    # Descriptive alternatives inside a matrix/polynomial (for example
    # ``rational or symbolic coefficients``) do not change the outer result
    # family.  Reject only conditional prose or an explicit *outer* type
    # alternative such as ``a matrix or a tuple``.
    outer_alternative = re.search(
        r"\bor\s+(?:a|an|the)?\s*(?:matrix|polynomial|vector|list|tuple|pair|set|dict|dictionary|object|class|field|ring|group|module|ideal|plot|graphics|image|callable|color)\b",
        normalized,
        re.IGNORECASE,
    )
    if re.search(r"\b(?:if|unless|depending)\b", normalized, re.IGNORECASE) or outer_alternative:
        return None
    patterns: tuple[tuple[str, str], ...] = (
        (r"^(?:a|an|the)\s+(?!(?:matrix|polynomial)\s+(?:group|list|morphism))(?:(?:[a-z][a-z0-9_-]*|`[^`]+`)\s+){0,8}matrix\b", MATRIX_ELEMENT_UNION),
        (r"^(?:a|an|the)\s+(?!(?:polynomial)\s+(?:matrix|ring))(?:(?:[a-z][a-z0-9_-]*|`[^`]+`)\s+){0,8}polynomial\b", POLYNOMIAL_RETURN_UNION),
        (r"^(?:a|an|the)\s+empty\s+string\b", "str"),
        (r"^(?:a|an|the)\s+(?:python\s+)?(?:list)\b", "list"),
        (r"^(?:a|an|the)\s+(?:python\s+)?(?:tuple|pair)\b", "tuple"),
        (r"^(?:a|an|the)\s+(?:python\s+)?(?:set)\b", "set"),
        (r"^(?:a|an|the)\s+(?:python\s+)?(?:dict|dictionary)\b", "dict"),
        (r"^(?:a|an|the)\s+(?:python\s+)?(?:string|str)\b", "str"),
        (r"^(?:a|an|the)\s+(?:python\s+)?(?:boolean|bool)\b", "bool"),
        (r"^(?:a|an|the)\s+(?:python\s+)?object\b(?!\s+of\s+type\b)", "object"),
        (r"^(?:the\s+)?class\s+(?:of|used\s+to|used\s+for|by|representing|implementing)\b", "type"),
    )
    for pattern, annotation in patterns:
        if re.match(pattern, normalized, re.IGNORECASE):
            return f"{annotation} | None" if optional_none else annotation
    return None


def _doc_elliptic_point_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
) -> str | None:
    """Resolve stable finite-field elliptic-point contracts from prose.

    Elliptic-curve point methods are inherited through ``EllipticCurvePoint_field``;
    their concrete receiver is selected by the curve's finite-field parent.
    The documentation nevertheless fixes a few result families independent of
    that implementation choice: coordinates/pairings are base-field values,
    while division by a scalar stays on the same curve.  Keep this rule
    limited to the field-point protocol and never claim that Jacobian,
    number-field, or generic point results are finite-field elements.
    """
    if not owner_name or not re.search(r"Point_field$", owner_name, re.IGNORECASE):
        return None
    normalized = re.sub(r"\s+", " ", summary.replace(chr(96), "")).strip()
    if node.name in {"x", "y"} and re.search(
        r"\bcoordinate\b.*\bbase\s+field\b", normalized, re.IGNORECASE
    ):
        return FINITE_FIELD_ELEMENT_UNION
    if node.name in {"tate_pairing", "weil_pairing", "_line_", "_miller_"}:
        if re.search(r"\b(?:pairing|value|root)\b", normalized, re.IGNORECASE) and not re.search(
            r"\b(?:jacobian|number\s+field|complex)\b", normalized, re.IGNORECASE
        ):
            return FINITE_FIELD_ELEMENT_UNION
        if re.search(r"(?:配对|单位根|值)", normalized) and not re.search(
            r"(?:雅可比|数域|复数)", normalized
        ):
            return FINITE_FIELD_ELEMENT_UNION
    if node.name == "divide" and re.search(
        r"\breturn\s+(?:a\s+)?point\b.*\bthis\s+point\b", normalized, re.IGNORECASE
    ):
        return "Self"
    return None


def _doc_elliptic_curve_contract_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
) -> str | None:
    """Resolve curve/point families explicitly named by elliptic docs.

    Elliptic-curve constructors, base changes and isogeny evaluation all
    expose a result whose outer family is fixed by the curve's field.  The
    generated stubs often only retain prose such as ``the elliptic curve``
    or ``the result ... at a point``; map those statements to the concrete
    field implementations while keeping unrelated geometric ``point`` nouns
    untouched.
    """
    normalized = re.sub(r"\s+", " ", (summary or "").replace(chr(96), "")).strip()
    if not normalized:
        return None
    if re.search(r"\b(?:or|either|depending|if|otherwise)\b", normalized, re.IGNORECASE):
        return None
    curve_context = bool(
        (owner_name and re.search(r"elliptic|isogeny", owner_name, re.IGNORECASE))
        or re.search(r"\belliptic\s+curve\b", normalized, re.IGNORECASE)
    )
    if not curve_context:
        return None
    if re.match(r"^(?:a|an|the)\s+elliptic\s+curve\b", normalized, re.IGNORECASE):
        return ELLIPTIC_CURVE_RETURN_UNION
    curve_result = re.search(
        r"\b(?:return(?:s|ed)?|construct(?:s|ed)?|create(?:s|d)?|compute|produce|base\s+(?:extension|change)|model|codomain|reduced\s+model)\b"
        r"[^.]{0,80}\b(?:elliptic\s+curve|curve|model|codomain|base\s+(?:extension|change))\b",
        normalized,
        re.IGNORECASE,
    )
    if curve_result:
        return ELLIPTIC_CURVE_RETURN_UNION
    # Curve classes often describe a model/base-change result without
    # repeating the noun in the first sentence.  The owner family is the
    # proof boundary here; require the semantic result words, not a method
    # name, so point-valued helpers such as ``point_of_order`` are excluded.
    if owner_name and re.match(r"EllipticCurve", owner_name, re.IGNORECASE) and re.search(
        r"\b(?:base\s+(?:extension|change)|minimal\s+model|montgomery\s+model|codomain|reduced\s+model)\b",
        normalized,
        re.IGNORECASE,
    ) and re.search(r"\b(?:return|construct|create|compute|produce)\w*\b", normalized, re.IGNORECASE):
        return ELLIPTIC_CURVE_RETURN_UNION
    if re.search(r"\b(?:result|image|point)\b.*\b(?:point|curve)\b", normalized, re.IGNORECASE) and re.search(
        r"\b(?:return|evaluate|evaluating|evaluation|reduction|reduce|image)\b",
        normalized,
        re.IGNORECASE,
    ):
        return ELLIPTIC_POINT_RETURN_UNION
    return None


def _doc_explicit_type_annotation(
    raw_output: str,
    class_index: dict[str, tuple[str, ...]],
    owner_name: str | None,
) -> str | None:
    """Resolve a type written explicitly in a Sage return section.

    Generated Sage documentation frequently uses a local ``返回:`` section
    whose head is ``Matrix -- ...`` or ``Factorization 形式 -- ...``.  The
    previous parser only understood a handful of builtins, so these
    source-level contracts were lost even though no inference was required.
    This helper accepts only one concrete signal at a time:

    * a fully-qualified ``sage....Class`` token in the declared section;
    * the exact containing class name (``Matrix``/``Polynomial``), lowered to
      ``Self``; or
    * a capitalized class token whose normalized name is unique in the source
      class index.

    Lower-case mathematical nouns (``matrix``, ``polynomial``, ``type``,
    ``graph``...) remain fail-closed.  Union/conditional prose is rejected so
    a descriptive sentence cannot accidentally become a concrete contract.
    """
    if not raw_output or not class_index:
        return None
    compact = re.sub(r"\s+", " ", raw_output.strip())
    # Numeric alternatives such as ``integer (0, -1, or 1)`` are still one
    # scalar type; reject only prose that offers different result families.
    conditional = re.search(r"\b(?:depending|if|otherwise|或|如果|取决于|否则)\b", compact, re.IGNORECASE)
    union = re.search(r"\b(?:or|either)\b", compact, re.IGNORECASE)
    numeric_integer_alternatives = bool(
        re.match(r"^(?:an?\s+)?(?:the\s+)?integer\s*\([^)]*\b(?:or|and)\b[^)]*\)", compact, re.IGNORECASE)
    )
    if conditional or (union and not numeric_integer_alternatives):
        return None
    head = re.split(r"\s+(?:--|-)\s*", compact, maxsplit=1)[0].strip()
    head = re.sub(r"^[-*]\s+", "", head)

    # A qualified class path is the strongest possible documentation signal;
    # verify it against the source class index rather than trusting arbitrary
    # prose that happens to contain a dotted name.
    for qualified in re.findall(r"\bsage(?:\.[A-Za-z_]\w*)+\b", compact):
        candidates = tuple(
            value
            for values in class_index.values()
            for value in values
            if value.casefold() == qualified.casefold()
        )
        if len(candidates) != 1:
            terminal = re.sub(r"[^a-z0-9]", "", qualified.rsplit(".", 1)[-1].casefold())
            candidates = class_index.get(terminal, ())
        if len(candidates) == 1:
            return f"'{candidates[0]}'"

    # When a method explicitly says that the result has the same type as the
    # receiver, preserve the concrete receiver rather than publishing a
    # public Matrix/Polynomial base as the final type.
    if owner_name:
        owner_key = re.sub(r"[^a-z0-9]", "", owner_name.casefold())
        normalized_head = re.sub(r"[^a-z0-9]", "", head.casefold())
        if normalized_head == owner_key or re.search(
            r"same\s+type|同类型|类型(?:与|和)\s*self\s*(?:相同|一致)|与\s*self\s*相同",
            compact,
            re.IGNORECASE,
        ):
            return "Self"

    # Resolve a capitalized class token only when its normalized spelling is
    # unique.  Requiring capitalization is deliberate: it distinguishes
    # documented class names such as ``Composition`` and ``ECL object`` from
    # generic prose such as ``type`` or ``matroid``.
    normalized_head = re.sub(r"[^a-z0-9]", "", head.casefold())
    class_head = re.sub(r"^(?:a|an|the)\s+", "", head, flags=re.IGNORECASE).strip()
    if not any(char.isupper() for char in class_head):
        return None
    matching: list[tuple[str, str]] = []
    for key, values in class_index.items():
        # One-letter classes (``A``, ``B``, ...) occur in Sage test helpers;
        # their spelling is far too common at the beginning of prose such as
        # ``A tuple`` to serve as a return-type signal.  Never resolve those
        # from documentation text.
        if (
            len(key) < 2
            or key in DOC_EXPLICIT_TYPE_HEAD_STOPWORDS
            or len(values) != 1
            or not normalized_head.startswith(key)
        ):
            continue
        matching.append((key, values[0]))
    if matching:
        # Prefer the longest class spelling (e.g. ``OEIS sequence`` over a
        # shorter coincidental prefix), then require a unique result.
        matching.sort(key=lambda item: len(item[0]), reverse=True)
        longest = [value for key, value in matching if len(key) == len(matching[0][0])]
        if len(set(longest)) == 1:
            return f"'{longest[0]}'"

    # Chinese-curated Sage docs often place the class name in the sentence
    # (``MatrixWindow 对象``) rather than at the beginning of the OUTPUT head.
    # Accept only an explicitly marked object/instance/form token; ordinary
    # capitalized prose and one-letter variables remain fail-closed.
    inline: list[tuple[int, str]] = []
    for token in re.findall(r"\b[A-Z][A-Za-z0-9_]*\b", compact):
        key = re.sub(r"[^a-z0-9]", "", token.casefold())
        values = class_index.get(key, ())
        if (
            len(key) < 2
            or key in DOC_EXPLICIT_TYPE_HEAD_STOPWORDS
            or len(values) != 1
            # Chinese generated overlays often put a short description
            # between the class name and the marker (``BipartiteGraph
            # 二部图对象``).  Bound the gap so arbitrary prose cannot turn a
            # coincidental capitalized word into a type contract.
            or not re.search(
                rf"\b{re.escape(token)}\b(?:\s+[\u4e00-\u9fffA-Za-z0-9_-]+){{0,4}}\s*(?:object|instance|form|type|对象|实例|形式|类型)\b",
                compact,
                re.IGNORECASE,
            )
        ):
            continue
        inline.append((len(key), values[0]))
    if inline:
        inline.sort(reverse=True)
        values = [value for length, value in inline if length == inline[0][0]]
        return f"'{values[0]}'" if len(set(values)) == 1 else None
    return None


def _is_sparse_cython_doc(value: str | None) -> bool:
    """Detect a generated Cython signature/file doc without semantic prose."""
    if not value:
        return False
    compact = " ".join(value.split())
    return bool(
        re.fullmatch(
            r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*\([^)]*\)\s+File:\s+.*",
            compact,
            re.IGNORECASE,
        )
    )


def _doc_summary_outer_protocol_annotation(
    summary: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """Resolve an explicit outer result noun in a one-line Sage summary.

    A substantial portion of the generated Sage API has a useful summary but
    no ``OUTPUT`` section (for example ``Return the incidence matrix``).  The
    result noun is still a source-level contract, while details such as the
    matrix backend or element parent may be dynamic.  Restrict this pass to a
    leading ``return`` sentence and reject mixed/conditional alternatives so
    it cannot turn incidental prose into a type guess.
    """
    compact = re.sub(r"\s+", " ", summary.strip().strip(".!?"))
    if not re.match(r"^returns?\s+", compact, re.IGNORECASE):
        return None
    if node.name in {"__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"}:
        return None
    tail = compact[len(re.match(r"^returns?\s+", compact, re.IGNORECASE).group(0)) :]
    if re.match(r"^(?:a|an|the)\s+set\s+of\s+generators\b", tail, re.IGNORECASE):
        return None
    # ``or raises/throws`` is an error path, not a second return type.  Keep
    # rejecting genuine unions while allowing explicit scalar/container nouns
    # in summaries such as ``Return a string ... or raises an error``.
    result_union = re.search(
        r"\b(?:or|either)\s+(?!(?:raises?|throws?|an?\s+error|an?\s+exception)\b)",
        tail,
        re.IGNORECASE,
    )
    if result_union or re.search(r"\b(?:depending|otherwise|if|unless|none|nothing)\b", tail, re.IGNORECASE):
        return None

    # Keep the number of descriptive words bounded and reject prepositions or
    # clause markers before the noun.  This prevents ``Return the monomial
    # corresponding to a Tietze tuple`` from being mistaken for a tuple result.
    noun = r"(?:[a-z][a-z0-9_\\'`-]*\s+){0,4}"
    forbidden_prefix = r"\b(?:of|for|to|under|from|in|on|with|by|as|that|which|corresponding|associated|representing|describing|self|this|the|a|an)\b"
    def _explicit_noun(kind: str, suffixes: str = "") -> bool:
        match = re.match(rf"^(?:a|an|the)\s+(?P<prefix>{noun}){kind}(?:\s+{suffixes}\b|$)", tail, re.IGNORECASE)
        return bool(match and not re.search(forbidden_prefix, match.group("prefix"), re.IGNORECASE))

    if _explicit_noun("matrix", r"(?:of|for|associated|corresponding|describing|representing)"):
        return MATRIX_ELEMENT_UNION
    if _explicit_noun("vector", r"(?:of|for|associated|corresponding|representing|with)") and not re.match(r"^(?:a|an|the)\s+[^.]*vector\s+(?:space|bundle)\b", tail, re.IGNORECASE):
        return VECTOR_ELEMENT_UNION
    if _explicit_noun("polynomial", r"(?:of|for|associated|corresponding|in|representing)") and not re.search(r"\bpolynomial\s+(?:ring|matrix)\b", tail, re.IGNORECASE):
        return POLYNOMIAL_RETURN_UNION
    container_match = re.match(rf"^(?:a|an|the)\s+(?P<prefix>{noun})(?P<kind>list|tuple|pair|set|dictionary|dict)\b", tail, re.IGNORECASE)
    if container_match and not re.search(forbidden_prefix, container_match.group("prefix"), re.IGNORECASE) and not (
        container_match.group("kind").casefold() == "set"
        and re.match(r"\s+partition\b", tail[container_match.end() :], re.IGNORECASE)
    ):
        if container_match.group("kind").casefold() == "set" and re.match(
            r"\s+of\s+generators\b", tail[container_match.end() :], re.IGNORECASE
        ):
            return None
        kind = container_match.group("kind").casefold()
        return {"list": "list", "tuple": "tuple", "pair": "tuple", "set": "set", "dictionary": "dict", "dict": "dict"}[kind]
    if re.match(r"^(?:a|an|the)\s+(?:python\s+)?(?:iterator|generator)\b", tail, re.IGNORECASE):
        return "Iterator"
    if re.match(r"^(?:a|an|the)\s+(?:python\s+)?(?:string|text)\b", tail, re.IGNORECASE):
        return "str"
    if re.match(r"^(?:whether|if)\s+", tail, re.IGNORECASE) or re.match(r"^(?:a|an|the)\s+boolean\b", tail, re.IGNORECASE):
        return "bool"
    # Explicitly enumerated parameter tuples have a stable outer shape.
    # Match parenthesized or comma-separated parameter names without
    # narrowing the parameter element classes themselves.
    if re.match(
        r"^(?:the\s+)?parameters?\s*(?:\([^)]*,[^)]*\)|[A-Za-z_][A-Za-z0-9_]*\s*,\s*[A-Za-z_][A-Za-z0-9_]*(?:\s*,\s*(?:and\s+)?[A-Za-z_][A-Za-z0-9_]*)*)",
        tail,
        re.IGNORECASE,
    ) or re.match(
        r"^[A-Za-z_][A-Za-z0-9_]*\s*,\s*[A-Za-z_][A-Za-z0-9_]*\s*,\s*(?:and\s+)?[A-Za-z_][A-Za-z0-9_]*\b",
        tail,
        re.IGNORECASE,
    ):
        return "tuple"
    # Scalar nouns in a leading ``Return`` sentence are stable Sage numeric
    # contracts even when the generated stub omitted an OUTPUT section.  Keep
    # the rule fail-closed around parent/family nouns (``number field``,
    # ``index set``) and preserve explicitly native Python counters.
    if re.match(r"^(?:a|an|the)\s+python\s+(?:integer|int|long)\b", tail, re.IGNORECASE):
        return "int"
    if re.match(r"^(?:a|an|the)\s+python\s+(?:float|double)\b", tail, re.IGNORECASE):
        return "float"
    integer_head = re.match(
        r"^(?:a|an|the)\s+(?P<noun>integer|number|index|degree)\b(?P<rest>.*)$",
        tail,
        re.IGNORECASE,
    )
    if integer_head:
        noun = integer_head.group("noun").casefold()
        rest = integer_head.group("rest").casefold()
        # Existing metric contracts carry the implementation-specific
        # unions for these names; do not let the generic sentence parser
        # narrow them to a single Sage Integer.
        if node.name in {"cardinality", "size", "length", "degree", "order", "height", "dimension", "rank", "characteristic", "ngens", "nrows", "ncols"}:
            return None
        if node.name.startswith("python_"):
            return None
        if noun == "number" and re.match(r"\s+(?:field|ring|module|space|theory)\b", rest):
            return None
        if noun == "index" and re.match(r"\s+set\b", rest):
            return None
        if re.search(r"\b(?:sequence|list|tuple|pair|set|vector|matrix|map|function)\b", rest):
            return None
        # Sage's explicitly named ``n_*`` counters are native Python ints in
        # the generated API (for example ``n_vertices``); all other
        # mathematical scalar nouns use the arbitrary-precision Integer.
        if node.name.startswith(("n_", "num_")):
            return "int"
        return "'sage.rings.integer.Integer'"
    return None


def _doc_cartan_type_summary_annotation(
    summary: str,
    class_index: dict[str, tuple[str, ...]] | None,
) -> str | None:
    """Materialize the concrete Cartan-type family named by a summary.

    Sage's ``CartanType(...)`` factory dispatches to one of the family
    modules (``type_A``, ``type_B_affine``, ...), so the abstract
    ``CartanType_abstract`` base is not a useful IDE return type.  Build the
    union from the generated source index instead of maintaining a module or
    function allow-list.
    """
    if not class_index or not re.match(
        r"^return\s+the\s+(?:(?:associated\s+)?cartan\s+type|basic\s+untwisted\s+cartan\s+type)\b",
        summary,
        re.IGNORECASE,
    ):
        return None
    candidates = sorted(
        value
        for value in class_index.get("cartantype", ())
        if not re.search(r"(?:Factory|_abstract)$", value, re.IGNORECASE)
        and ".root_system." in value
    )
    if not candidates:
        return None
    annotation = " | ".join(f"'{value}'" for value in candidates)
    if re.search(r"\bor\s+``?self``?\b|\bself\s+if\s+unknown\b", summary, re.IGNORECASE):
        return f"Self | {annotation}"
    return annotation


def _doc_summary_runtime_scalar_annotation(
    summary: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    owner_name: str | None,
) -> str | None:
    """Resolve small scalar protocols whose concrete class is source-stable."""
    # Sphinx inline literals (``prime``, ``integer`` and similar) carry no
    # type information of their own; remove the markup before matching the
    # semantic scalar phrase so the same contract works for wrapped prose.
    lowered_summary = summary.replace(chr(96), "").casefold()
    # ``prime_divisor`` documents either the discovered prime or the original
    # ``n``.  Both branches are Sage integer values, so the source wording
    # proves one concrete scalar rather than the generic Integer|int union.
    if re.search(r"\ba\s+prime\b.*\bor\s+n\b", lowered_summary):
        return "'sage.rings.integer.Integer'"
    # Prime-characteristic accessors return a Sage integer (or the native
    # Python integer used by a few Cython wrappers).  Keep this rule tied to
    # the documented *number* contract; methods returning a prime ideal are
    # intentionally excluded because their concrete parent is unrelated.
    if node.name == "prime" and re.search(r"\bprime\b", lowered_summary) and not re.search(
        r"\bprime\s+ideal\b", lowered_summary
    ):
        return "'sage.rings.integer.Integer | int'"
    if re.search(
        r"\b(?:residue\s+characteristic|characteristic\s+of\s+the\s+residue\s+field)\b",
        lowered_summary,
    ):
        return "'sage.rings.integer.Integer'"
    if re.search(
        r"\b(?:return(?:s|ed)?\s+)?(?:the\s+)?(?:underlying\s+)?prime\s+(?!ideal\b)(?:number\b|p\b|associated\b|from\b|such\b)",
        lowered_summary,
    ):
        return "'sage.rings.integer.Integer | int'"
    # Valuation *values* are integral in Sage's element/ideal/differential
    # APIs.  A valuation *map* on a ring/order is a different object and is
    # deliberately rejected by the ``of/at`` guard below.
    if node.name == "valuation" and re.search(
        r"\bvaluation(?:s)?\s+(?:of|at)\b", lowered_summary
    ) and not re.search(r"\bvaluation\s+on\b", lowered_summary):
        return "'sage.rings.integer.Integer | int'"
    if re.match(r"^return (?:the )?image of (?:the )?integer\b.*\bunder (?:this )?permutation\b", lowered_summary):
        return "'sage.rings.integer.Integer'"
    if not owner_name:
        return None
    lowered_owner = owner_name.casefold()
    if re.match(r"^return (?:the )?(?:numerator|denominator)\b", lowered_summary) and re.search(
        r"(?:^|\.)(?:nf)?cusp$", lowered_owner
    ):
        return "'sage.rings.integer.Integer'"
    if re.match(r"^return (?:the )?(?:numerator|denominator)\b", lowered_summary) and (
        "continuedfraction" in lowered_owner or "rootofunity" in lowered_owner
    ):
        return "'sage.rings.integer.Integer'"
    if re.search(r"\b(?:denominator|common multiple of the denominators|lowest common multiple of the denominators)\b", lowered_summary) and re.search(
        r"(?:free.?module|quaternion.?algebra.?element_rational_field|"
        r"number_field_element_quadratic|orderelement_quadratic|"
        r"universalcyclotomicfieldelement|formsringelement|infinitepolynomial|multipolynomial)",
        lowered_owner,
    ):
        return "'sage.rings.integer.Integer'"
    if re.match(r"^return the determinant\b", lowered_summary) and "arithmeticsubgroupelement" in lowered_owner:
        return "'sage.rings.integer.Integer'"
    if re.match(r"^return the determinant\b", lowered_summary):
        ntl_scalar = {
            "ntl_mat_zz": "sage.libs.ntl.ntl_ZZ.ntl_ZZ",
            "ntl_mat_gf2": "sage.libs.ntl.ntl_GF2.ntl_GF2",
            "ntl_mat_gf2e": "sage.libs.ntl.ntl_GF2E.ntl_GF2E",
        }
        for matrix_name, scalar_name in ntl_scalar.items():
            if matrix_name in lowered_owner:
                return f"'{scalar_name}'"
    return None


def _doc_semantic_source_annotation(
    summary: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    owner_name: str | None,
    module_name: str | None = None,
    class_index: dict[str, tuple[str, ...]] | None = None,
) -> str | None:
    """Resolve a few source-stable families omitted by generated stubs.

    These are family rules derived from Sage's implementation contracts, not
    per-symbol overrides: scheme parents construct the point implementation
    selected by their field/ring suffix, Lie-algebra basis accessors expose a
    ``FiniteFamily``, and modular-form ``weight`` accessors return Sage
    integers.  Ambiguous crystal/combinatorial weights stay unresolved.
    """
    normalized = re.sub(r"\s+", " ", (summary or "").replace(chr(96), "")).strip()
    module = (module_name or "").casefold()
    # Module-level elliptic-curve support helpers have no receiver owner, but
    # their documented result nouns still provide complete contracts.
    if (
        module.startswith("sage.schemes.elliptic_curves.cardinality")
        and node.name.startswith("_cardinality")
        and re.search(r"\b(?:count|cardinality|number\s+of\s+points)\b", normalized, re.IGNORECASE)
    ):
        return "'sage.rings.integer.Integer'"
    if (
        module == "sage.schemes.elliptic_curves.ell_torsion"
        and node.name == "torsion_bound"
        and re.search(r"\bupper\s+bound\b.*\border\b", normalized, re.IGNORECASE)
    ):
        return "'sage.rings.integer.Integer'"
    if (
        module == "sage.schemes.elliptic_curves.ell_egros"
        and node.name == "curve_key"
        and re.match(r"^comparison\s+key\s+for\s+elliptic\s+curves\b", normalized, re.IGNORECASE)
    ):
        return "tuple"
    if (
        module == "sage.schemes.elliptic_curves.ell_field"
        and node.name == "point_of_order"
        and re.search(r"\bpoint\b.*\border\b", normalized, re.IGNORECASE)
    ):
        return ELLIPTIC_POINT_RETURN_UNION
    # Lucas helpers over ``IntegerMod`` preserve the modular residue family.
    # Their documented outputs are either one residue or a fixed pair of
    # residues; the modulus chooses the storage backend at runtime.
    if (
        module == "sage.rings.finite_rings.integer_mod"
        and node.name in {"lucas_q1", "square_root_mod_prime_power"}
        and re.search(r"\b(?:lucas|square\s+root)\b", normalized, re.IGNORECASE)
    ):
        return INTEGER_MOD_ELEMENT_UNION
    if (
        module == "sage.rings.finite_rings.integer_mod"
        and node.name == "lucas"
        and re.search(r"\blucas\b", normalized, re.IGNORECASE)
    ):
        return f"tuple[{INTEGER_MOD_ELEMENT_UNION}, {INTEGER_MOD_ELEMENT_UNION}]"
    if (
        module == "sage.rings.finite_rings.homset"
        and node.name == "index"
        and re.match(r"^return the index of", normalized, re.IGNORECASE)
    ):
        return "'sage.rings.integer.Integer'"
    # Module-level helpers have no receiver owner, but an explicit conversion
    # noun in their summary is still a complete source contract.
    if not owner_name:
        # The non-coprime CRT helper combines two ``IntegerMod`` values and
        # returns another modular residue with the combined modulus.  Its
        # concrete storage is selected by the modulus size, so retain the
        # complete implementation union rather than exposing the public
        # IntegerMod protocol base.
        if (
            node.name == "_crt_non_coprime"
            and (module_name or "").casefold() == "sage.rings.finite_rings.conway_polynomials"
            and re.search(r"\bcrt\b", normalized, re.IGNORECASE)
        ):
            return INTEGER_MOD_ELEMENT_UNION
        if (
            node.name == "crt"
            and module == "sage.rings.finite_rings.integer_mod_ring"
        ):
            return "'sage.rings.integer.Integer'"
        if (
            node.name == "_isogeny_determine_algorithm"
            and module == "sage.schemes.elliptic_curves.ell_curve_isogeny"
        ):
            return "str"
        if re.search(
            r"\b(?:python\s+)?int(?:eger)?\b.*\bbinary\s+string\s+conversion\b",
            normalized,
            re.IGNORECASE,
        ):
            return "str"
        if (
            re.search(r"\bconvert\b[^.]{0,100}\bto\s+(?:a|an|the)\s+string\b", normalized, re.IGNORECASE)
            and not re.search(r"\b(?:tuple|set|dictionary|frozenset)\b", normalized, re.IGNORECASE)
        ):
            return "str"
        return None
    owner = owner_name.casefold()

    # Elliptic-curve support code exposes a small set of scalar contracts
    # that are stable across field implementations.  The source wording is
    # explicit (point counts, torsion bounds, local valuations), so these
    # rules do not guess from a public base class or from a method allow-list.
    if (
        owner.startswith("ellipticcurvepoint_")
        and node.name == "_compute_order"
    ):
        return "'sage.rings.integer.Integer'"
    if (
        owner.endswith("ellipticcurvelocaldata")
        and re.search(r"\b(?:valuation\s+of|tamagawa\s+(?:index|number|exponent))\b", normalized, re.IGNORECASE)
    ):
        return "'sage.rings.integer.Integer'"
    if (
        owner.endswith("ellipticcurvelocaldata")
        and node.name == "kodaira_symbol"
        and re.search(r"\bkodaira\s+symbol\b", normalized, re.IGNORECASE)
    ):
        return KODAIRA_SYMBOL_RETURN
    if (
        owner.startswith("galoisgroup_")
        and node.name == "__call__"
        and re.search(r"\baction\b.*\belement\b.*\bfinite\s+field\b", normalized, re.IGNORECASE)
    ):
        return FINITE_FIELD_ELEMENT_UNION
    if (
        module == "sage.crypto.lwe"
        and owner.endswith("uniformpolynomialsampler")
        and node.name == "__call__"
        and re.match(r"^return a new sample\.?$", normalized, re.IGNORECASE)
    ):
        return POLYNOMIAL_RETURN_UNION

    # Elliptic-isogeny helpers use a fixed algorithm selector and return the
    # point image of an evaluated isogeny.  The concrete curve implementation
    # is still selected by the source/target field, so retain the point family
    # union rather than a public point base.
    if (
        owner.startswith("ellipticcurveisogeny")
        and node.name in {"_call_", "__call__"}
        and re.search(r"(?:evaluation|evaluate|image|point)", normalized, re.IGNORECASE)
    ):
        return ELLIPTIC_POINT_RETURN_UNION

    # Heegner metadata is source-stable: conductors/discriminants are Sage
    # integers, quadratic-form accessors construct QuadraticForm, and orbit/
    # conjugate helpers materialize Python lists of points/objects.
    if (
        owner.startswith("heegnerpoint")
        and node.name in {"conductor", "discriminant"}
        and re.search(r"\b(?:conductor|discriminant)\b", normalized, re.IGNORECASE)
    ):
        return "'sage.rings.integer.Integer'"
    if (
        owner.startswith("heegner")
        and re.search(r"quadratic\s+form", normalized, re.IGNORECASE)
    ):
        return "'sage.quadratic_forms.quadratic_form.QuadraticForm'"
    if (
        owner.startswith("heegnerpoint")
        and re.search(r"\b(?:conjugates?|galois\s+orbit)\b", normalized, re.IGNORECASE)
    ):
        return "list"
    if (
        owner.startswith("ellipticcurve_rational_field")
        and node.name == "_compute_gens"
        and re.search(r"generator", normalized, re.IGNORECASE)
    ):
        return "list"
    if (
        owner.startswith("ellipticcurve_field")
        and node.name == "torsion_subgroup"
        and re.search(r"torsion\s+subgroup", normalized, re.IGNORECASE)
    ):
        return "'sage.groups.additive_abelian.additive_abelian_wrapper.AdditiveAbelianGroupWrapper'"
    if (
        owner.startswith("tatecurve")
        and node.name == "prime"
        and re.search(r"residual\s+characteristic", normalized, re.IGNORECASE)
    ):
        return "'sage.rings.integer.Integer'"

    # Finite-modulus helpers have stable outer contracts even though their
    # concrete residue storage depends on the modulus.  ``sqrt`` selects one
    # residue by default and a list when ``all=True``; root lifting returns a
    # tuple/list of residues; root enumeration always materializes a list.
    if owner.startswith("integermod") and node.name == "sqrt" and re.search(
        r"square\s+root", normalized, re.IGNORECASE
    ):
        return f"Self | list[Self]"
    if (
        owner.endswith("integermodring_generic")
        and node.name == "_lift_residue_field_root"
        and re.search(r"lift(?:s|ing)?\s+a\s+root", normalized, re.IGNORECASE)
    ):
        return f"list[{INTEGER_MOD_ELEMENT_UNION}] | tuple[{INTEGER_MOD_ELEMENT_UNION}, ...]"
    if (
        owner.endswith("integermodring_generic")
        and node.name == "_roots_univariate_polynomial"
        and re.search(r"return\s+the\s+roots", normalized, re.IGNORECASE)
    ):
        return "list"
    if (
        owner.endswith("finiteringelement")
        and node.name == "minpoly_over"
        and re.search(r"(?:minimal|极小)\s+polynomial|极小多项式", normalized, re.IGNORECASE)
    ):
        return POLYNOMIAL_RETURN_UNION

    # Matrix protocol methods whose generated docs carry no explicit OUTPUT
    # still have source-stable contracts.  Powers preserve the concrete
    # receiver; ``items`` exposes an iterator; MatrixWindow ``set_to*`` hooks
    # mutate in place.  Symbolic matrix simplification/pointwise transforms
    # return the same matrix, while echelonize mutates and returns ``None``.
    if owner.startswith("matrix"):
        if node.name == "__pow__":
            return "Self"
        if node.name == "items" and re.search(r"(?:iterable|可迭代对象)", normalized, re.IGNORECASE):
            return "Iterator"
    if owner.endswith("matrixwindow"):
        if node.name.startswith("set_to"):
            return "None"
    if owner.startswith("matrix_symbolic_"):
        if node.name in {"simplify_rational", "simplify_trig"}:
            return "Self"
        if re.search(r"operate\s+point-wise|simplif|canonical\s+branch", normalized, re.IGNORECASE):
            return "Self"
        if re.match(r"^echelonize\b", normalized, re.IGNORECASE):
            return "None"
    if owner == "matrixspace" and node.name == "__classcall__":
        return "'sage.matrix.matrix_space.MatrixSpace_with_category'"

    # ``UniqueFactory.create_object`` is a class-valued factory boundary.  A
    # factory whose name maps to exactly one source-indexed class can expose
    # that concrete class without maintaining a factory allow-list; ambiguous
    # families (finite fields, function fields, etc.) remain unresolved.
    if (
        node.name == "create_object"
        and re.search(r"\b(?:construct|create)\b.*\b(?:object|algebra|field|group|lattice|ring|valuation)\b", normalized, re.IGNORECASE)
        and class_index
    ):
        owner_simple = owner_name.rsplit(".", 1)[-1]
        stem = re.sub(r"(?:_?factory)$", "", owner_simple, flags=re.IGNORECASE)
        key = re.sub(r"[^a-z0-9]", "", stem.casefold())
        candidates = list(class_index.get(key, ()))
        if module:
            scoped = [value for value in candidates if value.rsplit(".", 1)[0].casefold() == module]
            if scoped:
                candidates = scoped
        if len(candidates) == 1:
            return f"'{candidates[0]}'"

    # Combinatorial element classes expose ``_auto_parent`` as a lazy class
    # attribute.  The implementation constructs the corresponding enumerated
    # parent from the element's singular class name (for example
    # ``BinaryTree`` -> ``BinaryTrees_all``).  Derive the plural form and
    # resolve it through the generated class index instead of maintaining a
    # per-class table.  The source module and exact class-name match keep this
    # rule fail-closed for unrelated ``_auto_parent`` protocols.
    if node.name == "_auto_parent" and re.match(
        r"^the automatic parent of the elements? of this class\.?$",
        normalized,
        re.IGNORECASE,
    ) and module.startswith("sage.combinat."):
        owner_simple = owner_name.rsplit(".", 1)[-1]
        candidate_names: list[str] = []
        if owner_simple.endswith("Tree"):
            plural = owner_simple[:-4] + "Trees"
            candidate_names.append(plural)
            # Unlabelled tree families use the disjoint-union ``_all``
            # implementation; labelled families expose the plain parent.
            if not owner_simple.startswith("Labelled"):
                candidate_names.insert(0, plural + "_all")
        elif owner_simple.endswith("Polyomino"):
            candidate_names.append(owner_simple[:-9] + "Polyominoes_all")
        for candidate_name in candidate_names:
            key = re.sub(r"[^a-z0-9]", "", candidate_name.casefold())
            candidates = (class_index or {}).get(key, ())
            same_module = [
                value
                for value in candidates
                if value.rsplit(".", 1)[0].casefold() == module
                and value.rsplit(".", 1)[-1] == candidate_name
            ]
            if len(same_module) == 1:
                return f"'{same_module[0]}'"

    # Numerical solver backends expose C-level ``double`` values through the
    # documented objective/variable accessors.  The Python boundary is
    # therefore always ``float`` for every backend implementation, including
    # the high-level MILP wrapper, while the solver state only affects whether
    # the call is valid (not its result type).
    if (
        node.name in {"get_objective_value", "get_variable_value"}
        and module.startswith("sage.numerical.")
        and not module.endswith(".ppl_backend")
        and re.match(
            r"^return the value of (?:the objective function|a variable given by the solver)\.?$",
            normalized,
            re.IGNORECASE,
        )
    ):
        return "float"

    # The PPL backend deliberately keeps exact arithmetic: both accessors
    # construct Sage ``Rational`` values rather than converting to doubles.
    # Handle this backend before the generic floating-point solver contract.
    if (
        node.name in {"get_objective_value", "get_variable_value"}
        and module.endswith(".ppl_backend")
        and re.match(
            r"^return (?:the exact value of the objective function|the value of a variable given by the solver)\.?$",
            normalized,
            re.IGNORECASE,
        )
    ):
        return "'sage.rings.rational.Rational'"

    # Modular-form PARI conversion hooks all return the cypari2 ``Gen``
    # wrapper.  The generated docstrings uniformly say ``Conversion to
    # Pari``; selecting the external class from that source contract keeps
    # the result concrete without tying it to a method allow-list.
    if (
        node.name == "_pari_init_"
        and module.startswith("sage.modular.")
        and re.match(r"^conversion to pari\.?$", normalized, re.IGNORECASE)
    ):
        return "cypari2.gen.Gen"

    # Finite-field modulus helpers hand the defining polynomial to PARI and
    # therefore return cypari2's concrete ``Gen`` wrapper.  ``_pari_init_``
    # is intentionally excluded here: Sage value classes use that hook for a
    # textual constructor expression, while ``_pari_modulus`` is the explicit
    # PARI-object boundary documented by finite-field implementations.
    if node.name == "_pari_modulus" and re.search(
        r"\bpari\b", normalized, re.IGNORECASE
    ) and re.search(r"\b(?:object|modulus|equivalent)\b", normalized, re.IGNORECASE):
        return "cypari2.gen.Gen"

    # p-adic parents report the precision model as a textual selector
    # (``capped-rel``, ``fixed-mod``, ...), independent of the selected
    # implementation class.
    if (
        node.name == "_prec_type"
        and module.startswith("sage.rings.padics.")
        and re.match(r"^return the precision handling type\.?$", normalized, re.IGNORECASE)
    ):
        return "str"

    # Sage's PARI conversion protocol is uniform at the Python boundary:
    # concrete objects hand their value to cypari2 and receive a ``Gen``
    # wrapper.  Require the documentation to name PARI explicitly and leave
    # intentionally unimplemented/example-only hooks fail-closed.
    if (
        node.name == "__pari__"
        and re.search(r"\bpari\b", normalized, re.IGNORECASE)
        and not re.search(r"not\s+yet\s+implemented", normalized, re.IGNORECASE)
    ):
        return "cypari2.gen.Gen"

    # Heegner/ring-class helpers construct Sage's quadratic number-field
    # implementation for the documented ``quadratic (imaginary) field``
    # result.  Keep this semantic noun rule conditional-free; callers that
    # advertise another branch remain unresolved until an overload can tie
    # the branch to its argument.
    if re.search(r"\bquadratic\s+(?:imaginary\s+)?(?:number\s+)?field\b", normalized, re.IGNORECASE) and not re.search(
        r"\b(?:or|either|depending|otherwise|if|when)\b", normalized, re.IGNORECASE
    ):
        return "'sage.rings.number_field.number_field.NumberField_quadratic'"

    # The non-coprime CRT helper combines two ``IntegerMod`` values and
    # returns another modular residue with the combined modulus.  Its
    # concrete storage is selected by the modulus size, so retain the full
    # implementation union rather than exposing the public IntegerMod base.
    if (
        node.name == "_crt_non_coprime"
        and module == "sage.rings.finite_rings.conway_polynomials"
        and re.search(r"\bcrt\b", normalized, re.IGNORECASE)
    ):
        return INTEGER_MOD_ELEMENT_UNION

    # IntegerMod's reduction and exact-division protocols construct another
    # residue in the target ``Z/nZ`` parent.  The storage backend depends on
    # the modulus, so publish the concrete prime-modulus implementation
    # family rather than the abstract ``IntegerMod_abstract`` base.
    if (
        owner.endswith("integermod_abstract")
        and node.name in {"__mod__", "_floordiv_"}
        and re.search(r"\b(?:coerce|exact\s+division|prime\s+moduli?)\b", normalized, re.IGNORECASE)
    ):
        return INTEGER_MOD_ELEMENT_UNION

    # Givaro's fused finite-field arithmetic helpers preserve the concrete
    # extension-field element implementation selected by the receiver.
    # Their source contract is the explicit ``a*b +/- c`` operation, which is
    # sufficient evidence without enumerating individual method names.
    if (
        re.search(
            r"\breturn\s+(?:a\s*\*\s*b\s*[+-]\s*c|c\s*-\s*a\s*\*\s*b)\b",
            normalized,
            re.IGNORECASE,
        )
        and re.search(r"(?:cache_givaro|finite_field_givaro)", owner, re.IGNORECASE)
    ):
        return "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'"

    # Geometry/graph helpers sometimes put their complete conversion result
    # in the summary instead of an OUTPUT section.  The explicit destination
    # noun is enough to establish a native string result; collection wording
    # remains excluded because it can describe a tuple/list payload.
    if (
        re.search(r"\bconvert\b[^.]{0,100}\bto\s+(?:a|an|the)\s+string\b", normalized, re.IGNORECASE)
        and not re.search(r"\b(?:tuple|set|dictionary|frozenset)\b", normalized, re.IGNORECASE)
    ):
        return "str"

    # This summary is the graph helper's full contract (integer to binary
    # string conversion), despite the generated stub having no OUTPUT type.
    if re.search(
        r"\b(?:python\s+)?int(?:eger)?\b.*\bbinary\s+string\s+conversion\b",
        normalized,
        re.IGNORECASE,
    ):
        return "str"

    # Pickle hooks that explicitly build a dictionary have a stable native
    # result even though other ``__getstate__`` implementations return tuples
    # or backend-specific state.  Keep this tied to the documented noun.
    if (
        node.name == "__getstate__"
        and re.search(r"\bdictionary\b.*\bpickl", normalized, re.IGNORECASE)
    ):
        return "dict"

    # Cartan/Coxeter ``type()`` accessors return the one-letter family code,
    # not another CartanType object.  Restrict this textual contract to the
    # root-system module family; unrelated ``type`` methods remain dynamic.
    if (
        node.name == "type"
        and module.startswith("sage.combinat.root_system.")
        and re.match(r"^return the type of self\.?$", normalized, re.IGNORECASE)
    ):
        return "str"

    # The sine--Gordon Y-system stores its family letter in ``_type`` and
    # exposes it unchanged through ``type()``.  Sage's source docstring uses
    # the same short contract as the Cartan accessor, but this module is not
    # part of the root-system family and therefore needs its own source rule.
    if (
        node.name == "type"
        and module == "sage.combinat.sine_gordon"
        and re.match(r"^return the type of self\.?$", normalized, re.IGNORECASE)
    ):
        return "str"

    # Species and cycle-index implementations all build their isotype series
    # through ``OrdinaryGeneratingSeriesRing``.  The category wrapper is
    # dynamic at runtime, but its indexed source class is the stable
    # ``OrdinaryGeneratingSeries`` element family.
    if (
        node.name == "isotype_generating_series"
        and (
            module.startswith("sage.combinat.species.")
            or module.startswith("sage.rings.lazy_species")
        )
        and re.match(r"^return the isotype generating series(?: for| of) self\.?$", normalized, re.IGNORECASE)
    ):
        return "'sage.combinat.species.generating_series.OrdinaryGeneratingSeries'"

    # A representation applies a semigroup element to a vector in its own
    # module.  The concrete element class is selected by that parent at
    # runtime, so preserve the parent-to-element relation instead of exposing
    # the representation parent as the return type.
    if (
        node.name == "_semigroup_action"
        and module == "sage.modules.with_basis.representation"
        and re.match(
            r"^return the action of the semigroup element .* on the vector .* of self\.?$",
            normalized,
            re.IGNORECASE,
        )
    ):
        return PARENT_ELEMENT_CONTRACT

    # ``randstate.set_seed_*`` mutates the selected external RNG and has no
    # value result.  The source implementations end after updating the global
    # seed marker; the detailed backend (GAP/NTL/PARI/...) does not change
    # that Python-level ``None`` contract.
    if (
        node.name.startswith("set_seed_")
        and module == "sage.misc.randstate"
        and re.match(r"^check to see if self was the most recent (?:[:\w-]+)?randstate\b", normalized, re.IGNORECASE)
    ):
        return "None"

    # Interface backends expose ``get`` as a textual CAS value.  This is the
    # documented contract of ``Interface.get`` and remains stable for derived
    # backends whose generated stubs omitted the inherited annotation.
    if (
        node.name == "get"
        and module.startswith("sage.interfaces.")
        and re.match(r"^get (?:the )?(?:string )?value\b", normalized, re.IGNORECASE)
    ):
        return "str"

    # ``_magma_init_`` is Sage's Magma conversion protocol.  A few generated
    # stubs use the prose order ``Used in converting ... to MAGMA`` rather than
    # the order expected by the older protocol matcher; both forms return the
    # textual Magma initialization expression.
    if node.name == "_magma_init_" and re.search(
        r"\b(?:magma|magm)\b", normalized, re.IGNORECASE
    ) and re.search(r"\bconvert(?:ing|ed|s)?\b", normalized, re.IGNORECASE):
        return "str"

    # Sage's Singular bridge always wraps a converted value in the concrete
    # ``SingularElement`` interface object.  This includes polynomial,
    # ideal, vector and ring ``_singular_``/``_singular_init_`` hooks; the
    # receiver's Sage parent only changes the generated Singular expression,
    # not the Python wrapper class.  Require explicit Singular conversion
    # wording so unimplemented/private hooks remain fail-closed.
    if node.name in {"_singular_", "_singular_init_"} and re.search(
        r"\bsingular\b", normalized, re.IGNORECASE
    ) and re.search(
        r"\b(?:representation|represent|ring|ideal|coerc|convert|create|return)\b",
        normalized,
        re.IGNORECASE,
    ) and not re.search(r"not\s+(?:yet\s+)?implemented", normalized, re.IGNORECASE):
        return "'sage.interfaces.singular.SingularElement'"

    # Scheme ``_point`` is the parent dispatch boundary.  The concrete point
    # class follows the scheme family's field/ring suffix and is stable in the
    # Sage source tree.  Resolve only the documented point constructor path.
    if node.name in {"_point", "point"} and re.match(
        r"^(?:construct|create|return)\s+(?:a|an|the)\s+point\b", normalized, re.IGNORECASE
    ):
        suffix = next(
            (candidate for candidate in ("finite_field", "field", "ring") if owner.endswith("_" + candidate)),
            None,
        )
        if suffix is not None:
            target = None
            if "affinespace" in owner:
                target = f"sage.schemes.affine.affine_point.SchemeMorphism_point_affine_{suffix}"
            elif "productprojectivespaces" in owner:
                target = f"sage.schemes.product_projective.point.ProductProjectiveSpaces_point_{suffix}"
            elif "projectivespace" in owner:
                target = f"sage.schemes.projective.projective_point.SchemeMorphism_point_projective_{suffix}"
            elif "weightedprojectivespace" in owner:
                target = f"sage.schemes.weighted_projective.weighted_projective_point.SchemeMorphism_point_weighted_projective_{suffix}"
            if target is not None:
                return f"'{target}'"

    # The corresponding scheme ``_morphism`` factories dispatch to one
    # concrete polynomial-morphism implementation using the same suffix.  A
    # weighted-projective space has no implemented homset in Sage 10.9 and is
    # therefore deliberately excluded here.
    if node.name == "_morphism" and re.match(
        r"^(?:construct|create|return)\s+(?:a|an|the)\s+morphism\b", normalized, re.IGNORECASE
    ):
        suffix = next(
            (candidate for candidate in ("finite_field", "field", "ring") if owner.endswith("_" + candidate)),
            None,
        )
        if suffix is not None:
            target = None
            if "affinespace" in owner:
                target = f"sage.schemes.affine.affine_morphism.SchemeMorphism_polynomial_affine_space_{suffix}"
            elif "productprojectivespaces" in owner and suffix == "ring":
                target = "sage.schemes.product_projective.morphism.ProductProjectiveSpaces_morphism_ring"
            elif "projectivespace" in owner:
                target = f"sage.schemes.projective.projective_morphism.SchemeMorphism_polynomial_projective_space_{suffix}"
            if target is not None:
                return f"'{target}'"

    # Point Hom-set factories have the same parent-family dispatch and their
    # concrete classes are documented directly by the Sage implementations.
    if node.name == "_point_homset" and re.match(
        r"^(?:construct|create|return)\s+(?:a|an|the)\s+(?:point\s+)?hom[- ]set\b",
        normalized,
        re.IGNORECASE,
    ):
        target = None
        if owner == "affinescheme":
            target = "sage.schemes.affine.affine_homset.SchemeHomset_points_spec"
        else:
            suffix = next(
                (candidate for candidate in ("finite_field", "field", "ring") if owner.endswith("_" + candidate)),
                None,
            )
            if suffix is not None and "productprojectivespaces" in owner:
                target = f"sage.schemes.product_projective.homset.SchemeHomset_points_product_projective_spaces_{suffix}"
            elif suffix is not None and "projectivespace" in owner:
                target = f"sage.schemes.projective.projective_homset.SchemeHomset_points_projective_{suffix}"
            elif suffix == "ring" and "weightedprojectivespace" in owner:
                target = "sage.schemes.weighted_projective.weighted_projective_homset.SchemeHomset_points_weighted_projective_ring"
        if target is not None:
            return f"'{target}'"

    # Lie-algebra generator families are finite even for infinite-dimensional
    # algebras.  Basis accessors are finite only for the classical and
    # explicitly finite-dimensional modules; Onsager/free/infinite bases use
    # LazyFamily and are intentionally left unresolved.
    generator_summary = re.match(
        r"^return the generators of .* as a lie algebra\.?$", normalized, re.IGNORECASE
    )
    finite_basis_module = (
        "lie_algebras.classical_lie_algebra" in module
        or ("lie_algebras.heisenberg" in module and owner.endswith("_fd"))
        or ("lie_algebras.subalgebra" in module and "finite" in owner)
    )
    if generator_summary and "lie_algebras" in module:
        return "'sage.sets.family.FiniteFamily'"
    if finite_basis_module and re.match(r"^return (?:a|the) basis\b", normalized, re.IGNORECASE):
        return "'sage.sets.family.FiniteFamily'"

    # Weight values in modular-form/symbol spaces and L-function or motivic
    # data are mathematical Sage integers.  Overconvergent forms intentionally
    # return weight-space objects, so that family remains fail-closed.
    if re.match(r"^return the weight\b", normalized, re.IGNORECASE) and "overconvergent" in owner:
        return "'sage.modular.overconvergent.weightspace.AlgebraicWeight'"
    if re.match(r"^return the weight\b", normalized, re.IGNORECASE) and re.search(
        r"(?:modular|modform|modsym|drinfeld|hecke|lfunctionzerosum|hypergeometricdata|formsring|formsspace)",
        owner,
    ) and "overconvergent" not in owner:
        return "'sage.rings.integer.Integer'"
    if re.match(r"^return the number of nonzero coefficients\b", normalized, re.IGNORECASE) and owner.endswith("ntl_gf2x"):
        return "int"
    return None


def _doc_sympy_conversion_annotation(
    summary: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    owner_name: str | None,
) -> str | None:
    """Resolve conversions whose external SymPy class is runtime-stable."""
    if node.name != "_sympy_" or not owner_name:
        return None
    if re.search(r"\b(?:column\s+)?vector\s*\(?matrix\)?\b", summary, re.IGNORECASE) and re.search(
        r"freemoduleelement", owner_name, re.IGNORECASE
    ):
        return "'sympy.matrices.immutable.ImmutableDenseMatrix'"
    return None


def _doc_iterator_element_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    summary: str,
    owner_name: str | None,
    class_index: dict[str, tuple[str, ...]] | None,
    module_name: str | None,
) -> str | None:
    """Resolve an iterator's yielded class from its structural class name.

    A few Sage iterators are named ``<Element>Iterator`` and document a
    concrete yielded noun (for example ``ExpressionIterator.__next__`` says
    that it returns the next component of an expression).  When the stripped
    stem resolves to exactly one class in the source index, this is a complete
    producer/consumer contract.  Generic iterators, user-labelled vertices,
    and iterators whose stem is only a parent remain unresolved.
    """
    if node.name != "__next__" or not owner_name or not class_index:
        return None
    match = re.search(r"(?:Iterator|_iterator|Iter|_iter)$", owner_name, re.IGNORECASE)
    if match is None:
        return None
    normalized = re.sub(r"\s+", " ", (summary or "").replace(chr(96), "")).strip()
    if not re.search(
        r"\b(?:return|returns?|get|next)\b[^.]{0,80}\b(?:element|component|term|monomial|variable|word|polynomial|expression)\b",
        normalized,
        re.IGNORECASE,
    ):
        return None
    stem = owner_name[: match.start()].rstrip("_")
    if not stem:
        return None
    key = re.sub(r"[^a-z0-9]", "", stem.casefold())
    candidates = class_index.get(key, ())
    if len(candidates) != 1 and module_name:
        preferred = _prefer_module_class_candidates(candidates, module_name)
        if len(preferred) == 1:
            candidates = preferred
    if len(candidates) != 1:
        return None
    candidate = candidates[0]
    if candidate.casefold().endswith("iterator"):
        return None
    return f"'{candidate}'"


def _doc_leading_scalar_output_annotation(output: str) -> str | None:
    """Resolve an atomic scalar/container noun at the head of OUTPUT.

    A number of Sage docstrings use a bare noun (``boolean according to ...``
    or ``integer; the discriminant ...``) instead of the article-led forms
    handled by the general parser.  The first sentence/semicolon is the
    declared result; later prose may legitimately mention an input ``None``
    and must not turn that scalar into an optional union.  Explicit result
    alternatives in the first clause remain fail-closed.
    """
    normalized = re.sub(r"\s+", " ", (output or "").replace(chr(96), "")).strip()
    if not normalized:
        return None
    match = re.match(
        r"^(?:(?:a|an|the)\s+)?"
        r"(?P<kind>boolean|bool|integer|int|long|float|double|string|str|bytes|"
        r"list|tuple|pair|set|dict|dictionary|none|nothing)\b(?P<tail>.*)$",
        normalized,
        re.IGNORECASE,
    )
    if match is None:
        return None
    kind = match.group("kind").casefold()
    tail = match.group("tail")
    # ``none``/``nothing`` are only exact no-result contracts here.  Phrases
    # such as ``None, True, False, or ...`` describe a union and are handled
    # by the existing fail-closed parser.
    if kind in {"none", "nothing"}:
        return "None" if not tail.strip(" .!?;,:()") else None
    first_clause = re.split(r"[.;]", tail, maxsplit=1)[0]
    if re.search(r"\b(?:depending|otherwise|unless|when)\b", first_clause, re.IGNORECASE):
        return None
    if re.search(r"\bif\b", first_clause, re.IGNORECASE):
        return None
    # Reject a second outer type in the same declared clause.  ``or None``
    # is checked only when it is adjacent to the leading noun; explanatory
    # parentheticals later in the paragraph are not result alternatives.
    if re.search(
        r"\b(?:or|either)\s+(?:(?:a|an|the)\s+)?"
        r"(?:integer|int|long|float|double|boolean|bool|bytes|list|tuple|pair|set|dict|dictionary|"
        r"matrix|vector|polynomial|point|object|color|rational|real|complex|infinity|function|morphism)\b",
        tail,
        re.IGNORECASE,
    ) or re.match(r"^\s+(?:or|either)\s+(?:none|nothing)\b", tail, re.IGNORECASE):
        return None
    return {
        "boolean": "bool",
        "bool": "bool",
        "integer": "'sage.rings.integer.Integer'",
        "int": "int",
        "long": "int",
        "float": "float",
        "double": "float",
        "string": "str",
        "str": "str",
        "bytes": "bytes",
        "list": "list",
        "tuple": "tuple",
        "pair": "tuple",
        "set": "set",
        "dict": "dict",
        "dictionary": "dict",
    }[kind]


def _doc_output_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_index: dict[str, tuple[str, ...]] | None = None,
    owner_name: str | None = None,
    module_name: str | None = None,
    owner_bases: tuple[str, ...] | None = None,
) -> str | None:
    value = ast.get_docstring(node, clean=False)
    iterator_element_annotation = _doc_iterator_element_annotation(
        node,
        value or "",
        owner_name,
        class_index,
        module_name,
    )
    if iterator_element_annotation is not None:
        return iterator_element_annotation
    if not value or _is_sparse_cython_doc(value):
        dynamic_interface_self_annotation = _doc_dynamic_interface_self_annotation(
            node,
            class_index,
            owner_name,
        )
        if dynamic_interface_self_annotation is not None:
            return dynamic_interface_self_annotation
        dynamic_interface_index_annotation = _doc_dynamic_interface_index_annotation(
            node,
            class_index,
            owner_name,
        )
        if dynamic_interface_index_annotation is not None:
            return dynamic_interface_index_annotation
        # Interface backends inherit ``Interface.__call__`` and often omit a
        # docstring on the concrete class.  The backend/module ->
        # ``<Backend>Element`` relation remains exact even with no OUTPUT
        # prose, so resolve it before the generic no-doc fallbacks.
        dynamic_interface_annotation = _doc_dynamic_interface_element_annotation(
            node,
            "",
            class_index,
            owner_name,
        )
        if dynamic_interface_annotation is not None:
            return dynamic_interface_annotation
        # Sage's ``TestSuite`` discovery contract treats every ``_test_*``
        # hook as an assertion routine: it raises on failure and returns
        # ``None`` on success.  This remains safe even when a generated stub
        # omitted the docstring entirely.
        if node.name.startswith("_test_"):
            return "None"
        # ``_inplace_*`` is the conventional Sage naming contract for a
        # helper that mutates its argument/receiver and deliberately has no
        # value result.  This remains safe even when the generated .pyi has
        # no docstring (the common case for this private protocol).
        if node.name.startswith("_inplace_"):
            return "None"
        # Matrix-window Cython helpers are mutators: set/add operations update
        # the view in place and return no value, while window constructors
        # return another window of the same class.
        if owner_name and owner_name.casefold().endswith("window"):
            if node.name.startswith("set_to") or re.match(
                r"^(?:set(?:_unsafe)?|add(?:_prod)?|subtract(?:_prod)?|swap_rows)$",
                node.name,
            ):
                return "None"
            if node.name.endswith("window"):
                return "Self"
        if owner_name and re.search(r"(?:^|_)matrix(?:$|_)", owner_name, re.IGNORECASE) and node.name == "__pow__":
            return "Self"
        if owner_name and owner_name.casefold().startswith("matrix_symbolic_"):
            if node.name in {"simplify_rational", "simplify_trig", "expand", "factor", "simplify"}:
                return "Self"
            if node.name == "echelonize":
                return "None"
        sparse_self_annotation = _doc_self_preserving_summary_annotation(
            value or "",
            owner_name,
            node.name,
        )
        if sparse_self_annotation is not None:
            return sparse_self_annotation
        # A helper whose public name explicitly promises an iterator has the
        # fixed Python iterator protocol even when its Cython stub omitted docs.
        if node.name.endswith("_iterator") or node.name == "iterator":
            return "Iterator"
        if node.name.startswith("_running_in_"):
            return "bool"
        # Python's data model requires ``__iter__`` to return an iterator.
        # The yielded element may depend on a dynamic Sage parent, so expose
        # only the stable outer protocol when no docstring gives a narrower
        # receiver-specific contract.
        # Data-model defaults apply only to methods declared on a class.  A
        # top-level helper named ``__repr__``/``__len__`` is ordinary Sage
        # API and must still be proven from its own documentation.
        if owner_name is not None:
            protocol_annotation = _doc_protocol_annotation(node, "", owner_name)
            if protocol_annotation is not None:
                return protocol_annotation
        metric_annotation = _doc_metric_contract_annotation(node, "", owner_name)
        if metric_annotation is not None:
            return metric_annotation
        return None
    # Generated Sage docstrings wrap the first summary sentence over several
    # physical lines (``xlcm`` is a representative case).  Join only that
    # first paragraph; stopping at the first blank line prevents INPUT,
    # OUTPUT, examples, and later prose from becoming accidental type evidence.
    summary_lines: list[str] = []
    for line in value.splitlines():
        stripped = line.strip()
        if not stripped:
            if summary_lines:
                break
            continue
        summary_lines.append(stripped)
    raw_summary = re.sub(r"\s+", " ", " ".join(summary_lines))
    summary = raw_summary.lower()
    # Symbolic function backends implement the internal derivative protocol
    # by constructing a Sage symbolic ``Expression``.  The generated Cython
    # stubs frequently omit this annotation (or only retain examples), but
    # the protocol and module family together are a complete runtime
    # contract; do not expose the generic callable/base type here.
    if (
        node.name == "_derivative_"
        and module_name
        and module_name.casefold().startswith("sage.functions.")
    ):
        return "'sage.symbolic.expression.Expression'"
    # ``_object_class`` is an explicit Python data-model query: its result is
    # a class object, independent of the backend class it reports.  ``type``
    # is therefore the precise outer contract and remains useful to IDE
    # completion without guessing a concrete Sage implementation.
    if node.name == "_object_class":
        return "type"
    # Some generated members carry only an ``EXAMPLES::``/``TESTS::`` heading;
    # when no OUTPUT section exists, a consistent literal doctest result still
    # proves its stable outer Python protocol.  Do not let this evidence
    # override prose-bearing contracts or numeric values whose Sage/Python
    # distinction cannot be recovered from rendered output.
    if summary.strip().rstrip(":") in {"examples", "example", "tests", "test"} and not _doc_output_values(value):
        examples_annotation = _doc_examples_literal_annotation(value)
        if examples_annotation is not None:
            return examples_annotation
    if node.name.startswith("_test_"):
        return "None"
    # Sage exposes a small number of C-level doctest helpers as public
    # ``test_*`` functions.  Their ordinary test routines only print/assert
    # and therefore return ``None``; wrappers documented as ``cdef int`` (or
    # the Qp-solubility probe) return the native integer result instead.
    if node.name.startswith("test_"):
        if re.search(r"\bcdef\s+(?:unsigned\s+)?(?:int|long)\b", raw_summary, re.IGNORECASE) or re.match(
            r"^testing function for qp_soluble\.?$", raw_summary, re.IGNORECASE
        ):
            return "int"
        return "None"
    # Predicate methods often have a short ``Test if ...``/``Check whether
    # ...`` summary followed by a doctest block containing unrelated words
    # such as ``list``.  The summary itself is the contract; use it to retain
    # the stable Python bool result without letting example prose widen it.
    if node.name.startswith(("is_", "has_", "can_", "contains_", "exists_")) and re.match(
        r"^(?:test|check|determine)\s+(?:whether|if)\b", raw_summary, re.IGNORECASE
    ):
        # A predicate may expose an opt-in payload (for example
        # ``is_power(..., get_data=True)``).  Without an overload tying that
        # flag to the return value, publishing ``bool`` would be incorrect;
        # keep the conditional contract UNKNOWN instead.
        if not re.search(
            r"\b(?:with|if|when|using)\s+\w+\s+(?:return|gives?|produces?|yields?)\b|"
            r"\b(?:return|gives?|produces?|yields?)\s+(?:a|an|the)?\s*(?:pair|tuple|list|data|information|values?)\b",
            raw_summary,
            re.IGNORECASE,
        ):
            return "bool"
    # Rendering/name protocols have the same fixed outer result regardless of
    # whether the generated docstring contains only ``TESTS::`` or a prose
    # summary.  Resolve them before summary-specific parsing so sparse docs do
    # not leave these stable contracts UNKNOWN.
    if node.name in {
        "_print_latex_",
        "_ascii_art_",
        "_unicode_art_",
        "_repr_object_names",
        "_repr_type",
        "_repr_term",
        "_equality_symbol",
        "_sage_src_",
        "_read_in_file_command",
        "_assign_symbol",
        "_true_symbol",
        "_install_hints",
        "_interface_init_",
        "_repr_defn",
        "_hash_",
        "stable_hash",
        "_repr_pretty_",
        "_repr_option",
        "__enter__",
        "_allowed_options",
        "super_categories",
        "positive_roots",
        "negative_roots",
        "_integer_",
        "_rational_",
        "_mpfr_",
        "_real_double_",
        "_render_on_subplot",
        "_precompute",
        "str",
        "_instancedoc_",
        "_sage_input_",
        "_magma_init_",
        "_start",
    }:
        return _doc_protocol_annotation(node, raw_summary, owner_name)
    if node.name.startswith("_inplace_"):
        return "None"
    # Manifold/chart caches are initialized and deleted in place.  The
    # generated docs use this exact semantic wording for the internal hooks;
    # no value is produced by either operation.
    if re.match(
        r"^(?:delete|initialize) the derived quantities(?: of self)?\.?$",
        raw_summary,
        re.IGNORECASE,
    ):
        return "None"
    void_annotation = _doc_void_contract_annotation(value, node.name)
    if void_annotation is not None:
        return void_annotation
    nonreturning_annotation = _doc_nonreturning_contract_annotation(value)
    if nonreturning_annotation is not None:
        return nonreturning_annotation
    copy_annotation = _doc_copy_contract_annotation(node, raw_summary, owner_name)
    if copy_annotation is not None:
        return copy_annotation
    inverse_annotation = _doc_inverse_contract_annotation(node, raw_summary, owner_name)
    if inverse_annotation is not None:
        return inverse_annotation
    classcall_annotation = _doc_classcall_contract_annotation(node, raw_summary, owner_name)
    if classcall_annotation is not None:
        return classcall_annotation
    identity_annotation = _doc_identity_return_annotation(node, value, owner_name)
    if identity_annotation is not None:
        return identity_annotation
    # Explicit owner contracts must run before generic summary/class-name
    # matching.  For example, ``RationalField.number_field`` documentation
    # contains the words "number field"; resolving that prose first would
    # incorrectly select the public NumberField base instead of the singleton
    # ``Self`` contract below.  Keep this early pass limited to owners whose
    # contracts are intentionally name-specific, then let the normal parser
    # handle all other Sage prose.
    if owner_name in {"FunctionalModule", "HadamardMatrixModule", "StronglyRegularDatabaseModule", "RationalField", "SageObject", "Tableau", "SkewTableau", "PartitionTuple", "ParallelogramPolyomino", "BinaryTree", "ComplexIntervalFieldElement", "PowerSeries", "PowerSeries_poly", "PowerSeries_pari", "MPowerSeries", "LaurentSeries", "LazyModuleElement", "Link", "FiniteStateMachine"}:
        metric_annotation = _doc_metric_contract_annotation(node, raw_summary, owner_name)
        if metric_annotation is not None:
            return metric_annotation
    self_preserving_annotation = _doc_self_preserving_summary_annotation(
        raw_summary,
        owner_name,
        node.name,
    )
    if self_preserving_annotation is not None:
        return self_preserving_annotation
    polynomial_scalar_annotation = _doc_polynomial_base_ring_scalar_annotation(
        node,
        raw_summary,
        owner_name,
    )
    if polynomial_scalar_annotation is not None:
        return polynomial_scalar_annotation
    parent_element_annotation = _doc_parent_element_annotation(
        node, raw_summary, owner_name, owner_bases
    )
    if parent_element_annotation is not None:
        return parent_element_annotation
    dynamic_interface_self_annotation = _doc_dynamic_interface_self_annotation(
        node,
        class_index,
        owner_name,
    )
    if dynamic_interface_self_annotation is not None:
        return dynamic_interface_self_annotation
    dynamic_interface_member_annotation = _doc_dynamic_interface_member_annotation(
        node,
        value,
        class_index,
        owner_name,
    )
    if dynamic_interface_member_annotation is not None:
        return dynamic_interface_member_annotation
    dynamic_interface_index_annotation = _doc_dynamic_interface_index_annotation(
        node,
        class_index,
        owner_name,
    )
    if dynamic_interface_index_annotation is not None:
        return dynamic_interface_index_annotation
    dynamic_interface_annotation = _doc_dynamic_interface_element_annotation(
        node,
        value,
        class_index,
        owner_name,
    )
    if dynamic_interface_annotation is not None:
        return dynamic_interface_annotation
    summary_class_annotation = _doc_summary_class_role_annotation(raw_summary, class_index, module_name)
    if summary_class_annotation is not None:
        return summary_class_annotation
    # Every concrete Cartan-type implementation documents the default folded
    # result with the same phrase.  Resolve it through the indexed concrete
    # class rather than exposing the abstract CartanType base or Self (the
    # runtime result is a CartanTypeFolded wrapper).
    if re.match(r"^return the default folded cartan type\.?$", raw_summary, re.IGNORECASE):
        folded_candidates = (class_index or {}).get("cartantypefolded", ())
        if len(folded_candidates) == 1:
            return f"'{folded_candidates[0]}'"
    numeric_summary_annotation = _doc_numeric_self_summary_annotation(raw_summary, owner_name)
    if numeric_summary_annotation is not None:
        return numeric_summary_annotation
    summary_annotation = _doc_summary_annotation(node, summary, class_index, owner_name)
    if summary_annotation is not None:
        return summary_annotation
    cartan_summary_annotation = _doc_cartan_type_summary_annotation(raw_summary, class_index)
    if cartan_summary_annotation is not None:
        return cartan_summary_annotation
    runtime_scalar_annotation = _doc_summary_runtime_scalar_annotation(raw_summary, node, owner_name)
    if runtime_scalar_annotation is not None:
        return runtime_scalar_annotation
    semantic_source_annotation = _doc_semantic_source_annotation(
        raw_summary, node, owner_name, module_name, class_index
    )
    if semantic_source_annotation is not None:
        return semantic_source_annotation
    sympy_annotation = _doc_sympy_conversion_annotation(raw_summary, node, owner_name)
    if sympy_annotation is not None:
        return sympy_annotation
    summary_protocol_annotation = _doc_summary_outer_protocol_annotation(raw_summary, node)
    if summary_protocol_annotation is not None:
        return summary_protocol_annotation
    # Metrics are semantic contracts independent of the concrete parent.  Run
    # this pass for every owner (the helper itself guards owner-specific
    # branches) so explicit prose such as ``OUTPUT: either an integer or
    # Infinity`` does not short-circuit a documented cardinality/size result.
    metric_annotation = _doc_metric_contract_annotation(node, raw_summary, owner_name)
    if metric_annotation is not None:
        return metric_annotation
    visual_annotation = _doc_visual_contract_annotation(node, raw_summary, owner_name)
    if visual_annotation is not None:
        return visual_annotation
    matrix_annotation = _doc_matrix_contract_annotation(node, raw_summary, owner_name)
    if matrix_annotation is not None:
        return matrix_annotation
    elliptic_point_annotation = _doc_elliptic_point_contract_annotation(
        node,
        raw_summary,
        owner_name,
    )
    if elliptic_point_annotation is not None:
        return elliptic_point_annotation
    elliptic_curve_annotation = _doc_elliptic_curve_contract_annotation(
        node,
        raw_summary,
        owner_name,
    )
    if elliptic_curve_annotation is not None:
        return elliptic_curve_annotation
    structural_annotation = _doc_structural_return_annotation(node, raw_summary)
    if structural_annotation is not None:
        return structural_annotation
    # Metric/parent contracts are stronger than a translated ``OUTPUT: Any``
    # label.  Evaluate the restricted backend rules before the per-output
    # parser can fail closed on unrelated prose (for example a Chinese
    # description containing the word ``or``).
    if owner_name and (
        "polynomial" in owner_name.casefold()
        or owner_name.casefold().startswith("integermod")
        or owner_name.casefold().startswith("matrix")
        # Concrete finite-field and ring elements share the same low-level
        # parent-preserving arithmetic protocol.  Their class names vary by
        # backend (for example ``FiniteFieldElement_pari_ffelt``), so include
        # the stable ``Element`` suffix in this guarded prepass.
         or re.search(r"(?:Element|element)$", owner_name)
         or owner_name.casefold().startswith("ntl_")
         or owner_name == "Integer"
         or owner_name == "FiniteField"
         or owner_name.casefold().startswith("finitefield_")
         or owner_name == "FinitePolyExtElement"
         or owner_name == "RationalField"
         or owner_name == "SageObject"
         or owner_name == "Tableau"
         or owner_name == "SkewTableau"
         or owner_name == "PartitionTuple"
         or owner_name == "ParallelogramPolyomino"
         or owner_name == "BinaryTree"
         or owner_name == "ComplexIntervalFieldElement"
         or owner_name in {"PowerSeries", "PowerSeries_poly", "PowerSeries_pari", "MPowerSeries", "LaurentSeries", "LazyModuleElement", "Link", "FiniteStateMachine"}
         or owner_name == "MatroidDatabaseModule"
         or owner_name == "HadamardMatrixModule"
         or owner_name == "FunctionalModule"
         or owner_name == "StronglyRegularDatabaseModule"
         or owner_name in {"DesignDatabaseModule", "GraphFamiliesModule", "SmallGraphsModule"}
         or owner_name == "DistanceRegularGraphsModule"
         or owner_name == "Polytopes"
         or owner_name == "Posets"
         or owner_name == "Partition"
         or owner_name == "FiniteWord_class"
         or owner_name == "Tableau"
         or owner_name == "EllipticCurve_generic"
         or owner_name == "PermutationGroup_generic"
         or owner_name == "GenericGraph"
         or owner_name.casefold().endswith("graph")
         # These owners also have stable method-name contracts (for example
         # ``NumberField_generic.gen`` and symbolic ``Expression.derivative``)
         # even when the translated OUTPUT prose is absent or intentionally
         # broad.  Keep this list explicit so dynamic factories remain
         # fail-closed.
         or owner_name in {"NumberField_generic", "NumberField_relative", "Expression"}
     ):
        metric_annotation = _doc_metric_contract_annotation(node, raw_summary, owner_name)
        if metric_annotation is not None:
            return metric_annotation
    # Preserve capitalization for Chinese summaries that name a concrete
    # class inline (``MatrixWindow 对象`` or ``Graphics 对象``).  The regular
    # English summary path intentionally lowercases its input for stable
    # phrase matching, so this source-level pass is kept separate.
    if class_index and re.match(r"^(?:返回|返回值|输出|绘制|创建|构造)", raw_summary, re.IGNORECASE):
        explicit_summary = _doc_explicit_type_annotation(raw_summary, class_index, owner_name)
        if explicit_summary is not None:
            return explicit_summary
    for raw_output in _doc_output_values(value):
        raw_output = re.sub(r"\s+", " ", raw_output.strip())
        marked_class_union = _doc_marked_class_union_annotation(
            raw_output,
            class_index or {},
            module_name,
        )
        if marked_class_union is not None:
            return marked_class_union
        # Structured multi-value OUTPUT sections are flattened by the
        # extractor into one paragraph.  When the source names the two
        # concrete outer values (formula strings and a variable frozenset),
        # retain the documented tuple shape rather than leaving it UNKNOWN.
        if re.search(r"\blist\s+of\s+formulas?\s+as\s+strings?\b", raw_output, re.IGNORECASE) and re.search(
            r"\bfrozenset\b", raw_output, re.IGNORECASE
        ):
            return "tuple[list, frozenset]"
        elliptic_output_annotation = _doc_elliptic_curve_contract_annotation(
            node,
            raw_output,
            owner_name,
        )
        if elliptic_output_annotation is not None:
            return elliptic_output_annotation
        matrix_output_annotation = _doc_matrix_contract_annotation(
            node,
            raw_output,
            owner_name,
        )
        if matrix_output_annotation is not None:
            return matrix_output_annotation
        parent_output_annotation = _doc_parent_element_annotation(
            node,
            raw_output,
            owner_name,
            owner_bases,
        )
        if parent_output_annotation is not None:
            return parent_output_annotation
        # In-place transformation APIs document the copied result as the
        # receiver class by default and ``None`` for the in-place branch.
        # The owner/class equality proves that the non-None branch preserves
        # the concrete receiver; retain the optional union until a literal
        # argument overload is available instead of collapsing it to a base.
        if owner_name:
            same_owner_optional = re.match(
                r"^(?:a|an|the)\s+:class:`(?P<class>[^`]+)`\s*\(\s*by\s+default\s*,\s*otherwise\s+(?:none|nothing)\s*\)\s*[.!?]?",
                raw_output,
                re.IGNORECASE,
            )
            if same_owner_optional is not None:
                target = same_owner_optional.group("class").split("<", 1)[0].strip().casefold()
                owner_simple = owner_name.rsplit(".", 1)[-1].casefold()
                if target == owner_simple:
                    return "Self | None"
        # Asymptotic term arithmetic preserves the concrete term class chosen
        # by its term monoid.  The documented atomic ``a term`` result is
        # therefore a receiver-preserving contract; explicit ``or None``
        # absorption branches remain unresolved below.
        if owner_name and re.search(r"Term$", owner_name, re.IGNORECASE):
            term_output = re.sub(r"`", "", raw_output).strip().lower()
            if re.match(r"^(?:a|an|the)\s+(?:asymptotic|exact|generic)?\s*term\b", term_output) and not re.search(
                r"\b(?:or|either|none|nothing|depending|if|otherwise)\b",
                term_output,
            ):
                return "Self"
        explicit = _doc_explicit_type_annotation(raw_output, class_index or {}, owner_name)
        if explicit is not None:
            return explicit
        output = raw_output.lower()
        # Sage docstrings quote literal result words as reStructuredText
        # inline code (``true``, ``none``, ``integer``).  Remove that markup
        # only at the beginning, preserving the fail-closed checks for
        # conditional/union prose later in the sentence.
        output = re.sub(
            r"^`{1,2}(boolean|string|integer|float|double|none|nothing|true|false)`{1,2}(?=\b|\s|[.,;])",
            r"\1",
            output,
        )
        output = re.sub(
            r"^`{1,2}(matrix|polynomial|vector|iterator|generator|object|type)`{1,2}(?=\b|\s|[-.,;])",
            r"\1",
            output,
        )
        output = re.sub(r"`{1,2}(true|false)`{1,2}", r"\1", output, flags=re.IGNORECASE)
        # ``None``/``nothing`` are frequently marked as inline literals in
        # OUTPUT sections (for example ``string or ``None```); normalize the
        # markup before the scalar/optional-union contracts run.
        output = re.sub(r"`{1,2}(none|nothing)`{1,2}", r"\1", output, flags=re.IGNORECASE)
        # The scalar/Infinity contracts below operate on the semantic words;
        # unwrap only the inline marker around ``\infty``.  Keep Sphinx
        # ``:class:`...``` roles intact because they carry concrete class
        # identity and are resolved by the role parser below.
        output = re.sub(r"`{1,2}(\\infty|infty|infinity)`{1,2}", r"\1", output, flags=re.IGNORECASE)
        # Some Sage docstrings introduce an explicitly documented outer
        # container in parentheses before listing its components, e.g.
        # ``(tuple) KSp, ...`` or ``(3-tuple) (ok, index, unsatlist)``.
        # Keep only that outer protocol; component types remain intentionally
        # unresolved when the prose is heterogeneous.
        parenthesized_output = re.match(
            r"^\(\s*(?P<kind>\d+[- ]?tuple|tuple|list|dictionary|dict)\s*\)",
            output,
            re.IGNORECASE,
        )
        if parenthesized_output:
            kind = parenthesized_output.group("kind").casefold().replace(" ", "")
            return "tuple" if "tuple" in kind else "dict" if kind in {"dictionary", "dict"} else "list"
        # A result description may introduce the stable outer shape with
        # ``as a ...`` rather than at the beginning (for example ``the tree
        # in infix form as a list``).  Collect all explicit conversion shapes;
        # if they agree, the nested payload is irrelevant to the IDE type.
        as_shapes = re.findall(
            r"\bas\s+(?:a|an|the)\s+(?P<shape>list|tuple|pair|set|dict|dictionary|string|integer|python\s+integer|float|double|boolean|bool)\b",
            output,
            re.IGNORECASE,
        )
        if as_shapes and not re.search(
            r"\b(?:depending|otherwise|if|unless|when|none|nothing)\b",
            output,
            re.IGNORECASE,
        ):
            normalized_shapes = {
                "pair": "tuple",
                "dict": "dict",
                "dictionary": "dict",
                "python integer": "int",
                "integer": "'sage.rings.integer.Integer'",
                "string": "str",
                "double": "float",
                "boolean": "bool",
                "bool": "bool",
            }
            mapped_shapes = {
                normalized_shapes.get(shape.casefold(), shape.casefold()) for shape in as_shapes
            }
            if len(mapped_shapes) == 1:
                return mapped_shapes.pop()
        # A plain outer Python shape is an exact contract even when the
        # element details are intentionally omitted.  Keep this semantic
        # parser independent of method/class names and reject all conditional
        # or heterogeneous alternatives before narrowing the result.
        simple_builtin = re.match(
            r"^(?:a|an|the)\s+(?P<kind>python\s+)?(?P<name>int|integer|long|float|double|boolean|bool|bytes|list|tuple|pair|set|dict|dictionary)\b",
            output,
            re.IGNORECASE,
        )
        remainder = output[simple_builtin.end() :] if simple_builtin else ""
        if simple_builtin and not (
            simple_builtin.group("name").casefold() == "set"
            and re.match(r"\s+(?:partition\b|of\s+all\s+prime\s+powers\b)", remainder, re.IGNORECASE)
        ):
            remainder = output[simple_builtin.end() :]
            # Only a second *type* or an explicit branch marker makes the
            # result heterogeneous.  Ordinary explanatory prose such as
            # ``an integer ... precise or at least sharp`` is still one
            # scalar contract and must not be rejected by a bare ``or``.
            heterogeneous = re.search(
                r"\b(?:depending|otherwise|if|unless|when|none|nothing)\b|"
                r"\bor\s+(?:(?:a|an|the)\s+)?(?:integer|int|long|float|double|boolean|bool|bytes|list|tuple|pair|set|dict|dictionary|matrix|vector|polynomial|point|object|color)\b",
                remainder,
                re.IGNORECASE,
            )
            if heterogeneous is None:
                name = simple_builtin.group("name").casefold()
                if simple_builtin.group("kind") and name in {"int", "integer", "long"}:
                    return "int"
                if name in {"int", "long"}:
                    return "int"
                if name in {"integer"}:
                    return "'sage.rings.integer.Integer'"
                if name in {"float", "double"}:
                    return "float"
                if name in {"boolean", "bool"}:
                    return "bool"
                if name == "bytes":
                    return "bytes"
                if name in {"tuple", "pair"}:
                    return "tuple"
                if name in {"dict", "dictionary"}:
                    return "dict"
                return "list" if name == "list" else "set"
        # Sage uses ``integer or infinity`` for cardinality-like values whose
        # finite branch is a Sage Integer and whose infinite branch is
        # ``PlusInfinity``.  Keep the complete scalar union instead of
        # collapsing the phrase to a Python ``int``.
        if re.fullmatch(
            r"(?:nonnegative|positive|negative|prime)?\s*integer\s+or\s+(?:\\infty|infty|infinity)\s*[.!?]?",
            output.strip(),
            re.IGNORECASE,
        ):
            return CARDINALITY_RETURN_UNION
        if re.fullmatch(
            r"integer\s*,\s*(?:\\infty|infty|infinity)\s*,\s*or\s*none\s*[.!?]?",
            output.strip(),
            re.IGNORECASE,
        ):
            return ORDER_RETURN_UNION
        if re.match(
            r"^integer\s+if\b.*\brational\s+otherwise\b",
            output,
            re.IGNORECASE,
        ):
            return INTEGER_RATIONAL_RETURN_UNION
        if re.match(
            r"^(?:integer|a\s+integer)\s+or\s+(?:a\s+)?rational(?:\s+number)?\b",
            output,
            re.IGNORECASE,
        ):
            return INTEGER_RATIONAL_RETURN_UNION
        if re.match(
            r"^a\s+rational\s+value,?\s+or\s+a\s+string\b",
            output,
            re.IGNORECASE,
        ):
            return "'sage.rings.rational.Rational | str'"
        if re.match(
            r"^a\s+(?:list\s+of\s+polynomials?)\s+or\s+a\s+single\s+polynomial\b",
            output,
            re.IGNORECASE,
        ):
            return f"list | {POLYNOMIAL_RETURN_UNION}"
        if re.match(r"^2[- ]tuple\s+of\s+floats\b", output, re.IGNORECASE):
            return "tuple[float, float]"
        if re.match(r"^(?:an?\s+)?array\s+of\s+strings?\b", output, re.IGNORECASE):
            return "list[str]"
        if re.match(r"^bytes\s*;", output, re.IGNORECASE):
            return "bytes"
        if re.match(
            r"^a\s+string\s+or\s+3[- ]tuple\s+of\s+strings?\b",
            output,
            re.IGNORECASE,
        ):
            return "str | tuple[str, str, str]"
        if re.match(
            r"^(?:string\s*;\s*either\b|string\s+(?:giving|representing)\b|string\s+or\s+none\b|string\s+giving\b)",
            output,
            re.IGNORECASE,
        ):
            if re.search(r"\bor\s+none\b", output, re.IGNORECASE):
                return "str | None"
            return "str"
        if re.match(r"^boolean\s*[;,:]", output, re.IGNORECASE):
            return "bool"
        if re.fullmatch(r"(?:none|nothing)\s*[.!?]?", output.strip(), re.IGNORECASE):
            return "None"
        if re.fullmatch(r"type\s*[.!?]?", output.strip(), re.IGNORECASE):
            return "type"
        if re.match(r"^(?:the\s+)?boolean\s+(?:true|false)\b", output.strip(), re.IGNORECASE) and not re.search(
            r"\b(?:or|either|depending|if|otherwise|none|nothing)\b", output, re.IGNORECASE
        ):
            return "bool"
        if re.fullmatch(r"a\s+python\s+class\s*[.!?]?", output.strip(), re.IGNORECASE):
            return "type"
        if re.fullmatch(r"the\s+formula\s+as\s+a\s+string\s*[.!?]?", output.strip(), re.IGNORECASE):
            return "str"
        string_candidate = output.lstrip("- ").strip()
        string_output = re.match(
            r"^(?:a|an|the)\s+string\b|^one\s+of\s+the\s+strings\b",
            string_candidate,
            re.IGNORECASE,
        )
        if string_output:
            # Alternatives between strings do not widen the outer result.
            # Reject only alternatives whose outer value is another protocol.
            heterogeneous_string = re.search(
                r"\b(?:or|either)\s+(?:(?:a|an|the)\s+)?(?:\d+[- ]?tuple|tuple|list|set|dict|dictionary|"
                r"integer|boolean|float|double|none|nothing|object|matrix|vector|point)\b",
                string_candidate,
                re.IGNORECASE,
            )
            if heterogeneous_string is None:
                return "str"
        if re.match(r"^(?:a|an|the)\s+(?:[a-z][a-z0-9_-]*\s+)?\d+[- ]?tuple\b", output, re.IGNORECASE):
            return "tuple"
        if re.match(r"^(?:a|an|the)\s+rgb\s+\d+[- ]?tuple\b", output, re.IGNORECASE):
            return "tuple"
        if (
            re.match(r"^(?:a|an|the)\s+\d+[- ]?bit\s+rgb\s+image\b", output, re.IGNORECASE)
            or (
                re.match(r"^(?:a|an|the)\s+[^.]{0,100}\bnumpy\s+array\b", output, re.IGNORECASE)
                and not re.search(r"\b(?:or|either|depending|if|otherwise)\b", output, re.IGNORECASE)
            )
        ):
            return "numpy.ndarray"
        if re.match(r"^\d+[- ]?bit\s+rgb\s+image\b", output, re.IGNORECASE):
            return "numpy.ndarray"
        if re.match(
            r"^(?:a|an|the)\s+complex\s+number\s+representing\b",
            output,
            re.IGNORECASE,
        ):
            return "numpy.complex128"
        if re.match(r"^(?:a|an|the)\s+point\s+of\s+the\s+same\s+berkovich\s+space\b", output, re.IGNORECASE):
            if owner_name and owner_name.casefold().startswith("berkovich_element_cp_"):
                return "Self"
        if (
            owner_name
            and re.search(r"(?:quadraticform|binaryqf|ternaryqf)$", owner_name, re.IGNORECASE)
            and re.match(r"^(?:a|an|the)\s+(?:new\s+|same\s+|ternary\s+|binary\s+)?quadratic\s+form\b", output, re.IGNORECASE)
            and not re.search(r"\b(?:or|either|depending|if|otherwise|none|nothing)\b", output, re.IGNORECASE)
        ):
            return "Self"
        if (
            owner_name
            and re.search(r"(?:form|forms)$", owner_name, re.IGNORECASE)
            and re.match(r"^(?:the\s+)?same\s+algebraic\s+form\b", output, re.IGNORECASE)
        ):
            return "Self"
        if owner_name and re.match(
            r"^new\s+object\s+if\s+substitution\s+is\s+possible,\s+otherwise\s+[\x60]{0,2}self[\x60]{0,2}\s*[.!?]?",
            output,
            re.IGNORECASE,
        ):
            return "Self"
        if owner_name and re.search(
            r"\bresulting\s+from\s+(?:the\s+)?(?:addition|sum|composition)\b[^.]*\bself\b[^.]*\bother\b|"
            r"\bresulting\s+from\s+(?:the\s+)?(?:addition|sum|composition)\b[^.]*\bother\b[^.]*\bself\b",
            output,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:or|either|depending|if|otherwise)\b", output, re.IGNORECASE):
            return "Self"
        if (
            re.match(r"^-?\s*the\s+extended\s+parser\b", output, re.IGNORECASE)
            and re.search(r"\bextend(?:s|ed)?\s+the\s+parser\b", raw_summary, re.IGNORECASE)
        ):
            return "None"
        if (
            re.match(r"^-?\s*the\s+extended\s+parser\b", output, re.IGNORECASE)
            and re.search(r"\bextend(?:s|ed)?\s+the\s+parser\b", raw_summary, re.IGNORECASE)
        ):
            return "None"
        # ``object`` is an explicit Python-level contract in a handful of
        # façade/adapter APIs whose values are intentionally caller-defined.
        # Preserve that documented outer type; do not infer a Sage base class
        # from the surrounding domain prose.
        if re.match(r"^(?:a|an|the)\s+object\b", output, re.IGNORECASE) and not re.search(
            r"\b(?:of\s+type|or|either|depending|if|otherwise)\b", output, re.IGNORECASE
        ):
            return "object"
        # Chinese-curated Sage docs and a few older modules put the declared
        # type before a ``--`` explanation (for example ``Integer -- ...``).
        # Read only that type token; ``any`` and mixed forms intentionally do
        # not become guesses.
        type_head = re.split(r"\s+(?:--|-)\s*", output, maxsplit=1)[0].strip()
        type_head = re.sub(r"^`{1,2}([^`]+)`{1,2}$", r"\1", type_head).strip()
        # Some source docstrings use ``(tuple) -- ...`` for an atomic outer
        # container.  Strip only the presentation wrapper; nested element
        # detail such as ``(tuple of Complex)`` still lowers to ``tuple``.
        parenthesized_head = re.fullmatch(
            r"\(\s*(tuple|list|set|dict|dictionary|integer|boolean|string)\s*\)",
            type_head,
        )
        if parenthesized_head:
            type_head = parenthesized_head.group(1)
        # The generated WSL stubs occasionally carry a fully-qualified
        # external runtime type in the output head.  Keep that exact type
        # instead of reducing it to a generic ``array``/``object`` shape.
        if re.match(r"^(?:numpy\.)?ndarray\b", type_head, re.IGNORECASE):
            return "numpy.ndarray"
        # Local Sage documentation may be translated while preserving the
        # semantic result noun.  These checks are deliberately tied to the
        # receiver family, so a mathematical vector mentioned in unrelated
        # prose cannot become a matrix result by accident.
        if owner_name and re.search(r"matrix", owner_name, re.IGNORECASE):
            if re.search(r"(?:向量|行向量|列向量)", raw_output) and not re.search(
                r"(?:or|either|depending|if|otherwise)", output, re.IGNORECASE
            ):
                return VECTOR_ELEMENT_UNION
            if re.search(r"矩阵", raw_output) and not re.search(
                r"(?:or|either|depending|if|otherwise)", output, re.IGNORECASE
            ):
                return MATRIX_ELEMENT_UNION
        if re.search(r"最小多项式|特征多项式", raw_output):
            return POLYNOMIAL_RETURN_UNION
        # Conway/Frobenius helpers explicitly return an element of the
        # integers modulo ``n``.  This is the finite-ring implementation
        # family, not a Python ``int`` and not the public ``Element`` base.
        if re.search(r"\belement\b[^.]{0,100}\b(?:integers?|integer\s+ring)\s+modulo\b", output, re.IGNORECASE):
            return INTEGER_MOD_ELEMENT_UNION
        if re.match(r"^this\s+element\s+reduced\s+modulo\b", output, re.IGNORECASE) and re.search(
            r"\bas\s+an?\s+element\s+of\s+.+(?:integers?|integer\s+ring)\s*/", output, re.IGNORECASE
        ):
            return INTEGER_MOD_ELEMENT_UNION
        if re.match(r"^(?:a|an|the)\s+real\s+number\s+or\s+infinity\b", output, re.IGNORECASE):
            return REAL_OR_INFINITY_RETURN_UNION
        if re.match(r"^(?:a|an|the)\s+finite\s+or\s+infinite\s+real\s+number\b", output, re.IGNORECASE):
            return REAL_OR_INFINITY_RETURN_UNION
        if re.match(
            r"^(?:a|an|the)\s+[^.]{0,100}\bas\s+(?:a|an|the)\s+real\s+number\b",
            output,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:or|either|depending|if|otherwise)\b", output, re.IGNORECASE):
            return REAL_NUMBER_RETURN_UNION
        if re.match(
            r"^(?:integer|an?\s+integer)\s+or\s+(?:minus|plus|negative|positive)\s+infinity\b",
            output,
            re.IGNORECASE,
        ):
            return CARDINALITY_RETURN_UNION
        if re.fullmatch(r"[+-]?\d+\s+or\s+[+-]?\d+[.!?]?", output, re.IGNORECASE):
            return "int"
        if re.match(
            r"^(?:the\s+)?findstat\s+identifier\b[^.]{0,80}\bas\s+an?\s+integer\b",
            output,
            re.IGNORECASE,
        ):
            return "int"
        if re.match(
            r"^(?:an?|the)\s+(?:positive|nonnegative|negative|prime)?\s*integer\b[^.]{0,100}\bor\s+(?:none|nothing)\b",
            output,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:or|either)\s+(?:an?|the)?\s*(?:rational|real|float|tuple|list|point|matrix|vector)\b", output, re.IGNORECASE):
            return "'sage.rings.integer.Integer | None'"
        if re.match(
            r"^(?:a|an|the)\s+complex\b[^.]{0,100}\broot\s+of\s+unity\b",
            output,
            re.IGNORECASE,
        ) and owner_name:
            if re.search(r"ComplexDouble", owner_name, re.IGNORECASE):
                return "'sage.rings.complex_double.ComplexDoubleElement'"
            if re.search(r"ComplexInterval", owner_name, re.IGNORECASE):
                return "'sage.rings.complex_interval_field.ComplexIntervalFieldElement'"
            if re.search(r"ComplexField", owner_name, re.IGNORECASE):
                return "'sage.rings.complex_mpfr.ComplexNumber'"
            if re.search(r"NumberFieldElement", owner_name, re.IGNORECASE):
                return "Self"
        if re.match(
            r"^(?:a|an|the)\s+matrix\s+or\s+(?:a|an|the)\s+tuple\b",
            output,
            re.IGNORECASE,
        ):
            return f"{MATRIX_ELEMENT_UNION} | tuple"
        if re.match(
            r"^(?:the\s+)?edges\s+of\s+a\s+minimum\s+spanning\s+tree\b",
            output,
            re.IGNORECASE,
        ):
            return "list"
        if not re.search(r"\b(?:or|either|depending|if|otherwise)\b", output, re.IGNORECASE):
            if re.match(
                r"^(?:a|an|the)\s+[^.]{0,80}\b(?:minimal|characteristic)\s+polynomial\b",
                output,
                re.IGNORECASE,
            ):
                return POLYNOMIAL_RETURN_UNION
            if re.match(
                r"^(?:a|an|the)\s+(?!(?:vector\s+(?:space|bundle))\b)(?:[a-z][a-z0-9_-]*\s+){0,3}vector\b",
                output,
                re.IGNORECASE,
            ) or re.search(
                r"(?:^|[;,:-])\s*(?:a|an|the)\s+(?!(?:vector\s+(?:space|bundle))\b)(?:[a-z][a-z0-9_-]*\s+){0,3}vector\b",
                output,
                re.IGNORECASE,
            ):
                return VECTOR_ELEMENT_UNION
            if re.match(r"^(?:a|an|the)\s+(?:pair|triple|tuple)\b", output, re.IGNORECASE):
                return "tuple"
            if re.match(r"^(?:the\s+)?(?:output\s+is\s+)?a\s+\d+[- ]?tuple\s+of\s+lists\b", output, re.IGNORECASE):
                return "tuple"
            if re.match(r"^(?:a|an|the)\s+restricted\s+growth\s+word\b", output, re.IGNORECASE):
                return "list"
            if re.match(r"^(?:the\s+)?edges\s+of\s+a\s+minimum\s+spanning\s+tree\b", output, re.IGNORECASE):
                return "list"
            if re.match(r"^(?:a|an|the)\s+dense\s+real\s+double\s+matrix\b", output, re.IGNORECASE):
                return "'sage.matrix.matrix_real_double_dense.Matrix_real_double_dense'"
            if re.match(
                r"^(?:a|an|the)\s+(?!(?:matrix\s+(?:group|list|morphism))\b)(?:[a-z][a-z0-9_-]*\s+){0,3}matrix\b",
                output,
                re.IGNORECASE,
            ):
                return MATRIX_ELEMENT_UNION
            if re.match(r"^(?:a|an|the)\s+(?:a\s+)?(?:hyperbolic\s+)?distance\b", output, re.IGNORECASE):
                return REAL_NUMBER_RETURN_UNION
            if re.match(r"^(?:a|an|the)\s+generator\b", output, re.IGNORECASE):
                return "Iterator"
            if re.match(r"^(?:-\s*)?(?:(?:a|an|the)\s+)?(?:iterator|generator)\b", output, re.IGNORECASE):
                return "Iterator"
            if re.match(r"^(?:an?|the)\s+iterable\b", output, re.IGNORECASE):
                return "typing.Iterable"
            if re.match(
                r"^(?:a|an|the)\s+(?:(?:new|complete|simple|sorted|ordered|generating|corresponding|flat|nested)\s+)+list\b",
                output,
                re.IGNORECASE,
            ):
                return "list"
        if re.match(
            r"^(?:(?:a|an|the)\s+)?rational\s+number\s+times\s+the\s+square\s+root\s+of\s+a\s+rational\s+number\b",
            output,
            re.IGNORECASE,
        ):
            return "'sage.symbolic.expression.Expression'"
        if re.match(r"^(?:an?\s+)?expression\s+in\s+the\s+powersum\s+basis\b", output, re.IGNORECASE):
            return "'sage.combinat.sf.powersum.SymmetricFunctionAlgebra_power.Element'"
        if re.match(r"^(?:an?\s+)?element\s+of\s+the\s+schur\s+basis\b", output, re.IGNORECASE):
            return "'sage.combinat.sf.schur.SymmetricFunctionAlgebra_schur.Element'"
        if re.match(r"^(?:an?\s+)?element\s+of\s+the\s+monomial\s+basis\b", output, re.IGNORECASE):
            return "'sage.combinat.sf.monomial.SymmetricFunctionAlgebra_monomial.Element'"
        if re.match(r"^(?:the\s+)?class\s+of\s+the\s+hall[- ]littlewood\s+p\s+basis\b", output, re.IGNORECASE):
            return "'sage.combinat.sf.hall_littlewood.HallLittlewood_p'"
        if (
            owner_name
            and re.search(r"SymmetricFunctionAlgebra", owner_name, re.IGNORECASE)
            and re.match(r"^the\s+product\s+of\s+left\s+and\s+right\s+in\s+the\s+basis\s+self\b", output, re.IGNORECASE)
        ):
            return PARENT_ELEMENT_CONTRACT
        # Several polynomial and algebra element docstrings state the result
        # directly as an element of the receiver's parent.  This is stronger
        # than a public ``Element`` base and is safe to expose as ``Self``;
        # conditional coefficient/index branches use different wording and
        # remain fail-closed.
        parent_output = output.replace("`", "")
        if owner_name and (
            re.match(r"^(?:an?|the)\s+element of the same parent\b", parent_output)
            or re.match(r"^element of the parent of (?:this element|self)\b", parent_output)
        ):
            return "Self"
        if type_head in {"iterator", "python iterator"}:
            # The element parameter is intentionally unspecified; exposing
            # the stable iterator protocol still gives callers ``__next__``
            # and avoids collapsing the result to UNKNOWN.
            return "Iterator"
        if type_head in {"integer", "sage integer"}:
            return "'sage.rings.integer.Integer'"
        # Many Sage docstrings qualify an integer with a parenthesized
        # explanation (``An integer (the n-th term...)``).  The explanation
        # does not change the scalar contract; alternatives are rejected by
        # the guard below so conditional integer/None results stay unresolved.
        if re.match(
            r"^(?:a|an|the)\s+python\s+integer\b",
            output,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:or|either|depending|if|otherwise|none|nothing)\b", output, re.IGNORECASE):
            return "int"
        if re.match(
            r"^(?:a|an|the)\s+(?:positive|nonnegative|negative|prime)?\s*integer\b",
            output,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:or|either|depending|if|otherwise|none|nothing)\b", output, re.IGNORECASE):
            return "'sage.rings.integer.Integer'"
        # A compact ``float; ...``/``string; ...``/``boolean; ...`` output
        # head is an atomic native protocol followed by an explanation.  Do
        # not accept words joined by ``or``/``if`` because those describe a
        # conditional branch rather than one scalar result.
        delimited_scalar = re.match(
            r"^(?:a|an|the)?\s*(?P<kind>boolean|string|float|double|complex|integer|int)\s*[;,:()]",
            type_head,
            re.IGNORECASE,
        )
        if delimited_scalar and not re.search(
            r"\b(?:or|either|depending|if|otherwise|none|nothing)\b", output, re.IGNORECASE
        ):
            return {
                "boolean": "bool",
                "string": "str",
                "float": "float",
                "double": "float",
                "complex": "complex",
                "integer": "'sage.rings.integer.Integer'",
                "int": "int",
            }[delimited_scalar.group("kind").casefold()]
        if re.match(r"^(?:an?\s+|the\s+)?integer\s+[a-z_]\w*\b", type_head) and not re.search(
            r"\b(?:or|either|if|depending|unless|otherwise)\b",
            output,
            re.IGNORECASE,
        ):
            return "'sage.rings.integer.Integer'"
        if re.match(r"^(?:an?\s+|the\s+)?python\s+long\b", type_head):
            return "int"
        if re.match(r"^(?:an?\s+|the\s+)?python\s+(?:integer|int)\b", type_head):
            return "int"
        if type_head in {"bool", "boolean"} and not node.name.startswith(
            ("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__")
        ):
            return "bool"
        if type_head == "complex":
            return "complex"
        if type_head in {"str", "string"}:
            return "str"
        if type_head in {"float", "double"}:
            return "float"
        if re.match(
            r"^(?:the\s+)?(?:block(?:\s+\(or\s+key\))?|input|output|key)\s+(?:length|size)\b",
            output,
            re.IGNORECASE,
        ):
            return "int"
        if re.match(
            r"^(?:the\s+)?`{0,2}[a-z_]\w*`{0,2}-bit\s+vector\s+representation\b",
            output,
            re.IGNORECASE,
        ):
            # DES/PRESENT conversion helpers explicitly promise a dense
            # GF(2) bit vector, not an arbitrary parent-dependent vector.
            return "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"
        if type_head in {"list", "python list"}:
            return "list"
        if type_head in {"dict", "dictionary", "python dictionary"}:
            return "dict"
        if type_head in {"tuple", "pair"} or type_head.startswith(("tuple[", "list[")):
            if type_head in {"tuple", "pair"} or type_head.startswith("tuple["):
                return "tuple"
            return "list"
        if output.startswith(("the binary string representation", "a binary string representation")):
            return "'sage.monoids.string_monoid_element.StringMonoidElement'"
        if re.match(
            r"^(?:the\s+)?(?:initial\s+)?permutation .*\b(?:\d+-bit|vector of \d+ bits)\b|"
            r"^a circular left shift .*\bvector of \d+ bits\b|"
            r"^a permutation of a \d+-bit string\b",
            output,
            re.IGNORECASE,
        ):
            return "list"
        exact = DOC_OUTPUT_RETURNS.get(output)
        if exact is not None:
            return exact

        # Reject explicit unions and conditional result descriptions before
        # accepting a prefix.  This is the important fail-closed boundary:
        # ``boolean; whether ...`` is atomic, while ``boolean or tuple`` is
        # not a contract that can be represented by one concrete annotation.
        numeric_integer_alternatives = bool(
            re.match(r"^(?:an?\s+)?(?:the\s+)?integer\s*\([^)]*\b(?:or|and)\b[^)]*\)", output, re.IGNORECASE)
        )
        same_integer_alternative = bool(
            re.match(
                r"^(?:(?:a|an|the)\s+)?(?:positive|nonnegative|negative|prime)?\s*integer\b"
                r".*\bor\s+(?:`{0,2}-?\d+`{0,2}|(?:an?\s+)?(?:positive|nonnegative|negative|prime)?\s*integer)(?!\w)",
                output,
                re.IGNORECASE,
            )
        )
        prime_integer_alternatives = bool(
            output.startswith("a prime ") and re.search(r"\bor\b", output) and re.search(r"\bn\b", output)
        )
        pair_optional_contract = bool(
            re.match(r"^either integers?\b.*\bor\s+(?:`{1,2})?none(?:`{1,2})?\b", output)
        )
        pair_boolean_contract = bool(
            re.match(
                r"^(?:a|an|the)?\s*pair\b[^.]{0,180}\b(?:or|otherwise)\s+(?:[\x60]{0,2})?false(?:[\x60]{0,2})?\b",
                output,
                re.IGNORECASE,
            )
        )
        integer_rational_contract = bool(
            re.match(r"^(?:(?:a|an|the)\s+)?integer\s+or\s+rational\s+number\b", output, re.IGNORECASE)
        )
        optional_integer_contract = bool(
            re.match(
                r"^(?:(?:a|an|the)\s+)?(?:positive|nonnegative|negative|prime)?\s*integer\s+or\s+(?:`{0,2})?(?:none|nothing)(?:`{0,2})?\b",
                output,
                re.IGNORECASE,
            )
        )
        iterator_element_contract = bool(
            re.match(r"^(?:an?|the)\s+(?:iterator|generator)\b", output, re.IGNORECASE)
            and not re.search(r"\b(?:if|depending|otherwise|none|nothing)\b", output, re.IGNORECASE)
        )
        class_role_union_contract = bool(
            class_index
            and len(re.findall(r":class:`[^`]+`", raw_output)) > 1
            and re.search(r"\b(?:or|either|depending|otherwise|if|when)\b", raw_output, re.IGNORECASE)
        )
        # Let the dedicated structural parser inspect return-wrapper prose
        # before the generic ``or`` rejection.  It knows how to preserve a
        # homogeneous ``container | None`` contract while rejecting a true
        # outer alternative such as ``list or plot``.
        early_output_shape = None
        if re.search(r"\breturns?\s+", raw_output, re.IGNORECASE):
            early_output_shape = _doc_structural_output_shape_annotation(raw_output)
        if early_output_shape is not None:
            return early_output_shape
        role_position = raw_output.find(":class:`")
        descriptive_or_before_role = bool(
            role_position >= 0
            and re.search(r"\b(?:or|either)\b", raw_output[:role_position], re.IGNORECASE)
            and not re.search(r"\b(?:or|either)\b", raw_output[role_position:], re.IGNORECASE)
        )
        # An ``or`` joining coefficient/parameter adjectives does not make
        # the outer value heterogeneous (``a matrix with rational or
        # symbolic coefficients``).  Preserve this evidence for the later
        # matrix/polynomial shape resolver while still rejecting outer-type
        # alternatives such as ``matrix or tuple``.
        descriptive_scalar_alternative = bool(
            re.search(
                r"\b(?:rational|symbolic|real|complex|integer|finite|infinite)\b\s+or\s+\b(?:rational|symbolic|real|complex|integer|finite|infinite)\b\s+(?:coefficient|coefficients|number|numbers|values?|entries?)\b",
                output,
                re.IGNORECASE,
            )
        )
        optional_container_contract = re.match(
            r"^(?:a\s+|an\s+|the\s+)?(?P<kind>list|tuple|pair|set|dictionary|dict)\b"
            r".*\b(?:or|either)\b\s*(?:`{1,2})?(?:none|nothing)(?:`{1,2})?\b",
            output,
            re.IGNORECASE,
        )
        # A collection whose *elements* have alternatives still has one
        # unambiguous outer result (for example ``a list of 0, 1 or 2
        # pairs``).  This is different from ``a list or tuple``.
        container_element_alternatives = bool(
            re.match(r"^(?:a|an|the)\s+(?:list|tuple|set|dictionary|dict)\s+of\b", output)
        )
        atomic_container_prefix = bool(
            re.match(r"^(?:list|tuple|set|dictionary|dict)\b", output)
            and not re.search(
                r"\bor\s+(?:a\s+|an\s+|the\s+)?(?:list|tuple|set|dictionary|dict|none|integer|boolean)\b",
                output,
            )
        )
        optional_sphinx_class = bool(
            re.fullmatch(
                r"(?:a|an|the)\s+:class:`[^`]+`\s+or\s+(?:none|nothing)\s*[.!?]?",
                output,
                re.IGNORECASE,
            )
        )
        sphinx_simple_union = bool(
            re.match(
                r"^(?:either\s+)?(?:a|an|the)\s+:class:`[^`]+`\s+or\s+(?:list|tuple|set|dict|dictionary)\b",
                output,
                re.IGNORECASE,
            )
            and len(re.findall(r"\bor\b", output, re.IGNORECASE)) == 1
            and len(set(re.findall(r":class:`([^`]+)`", output, re.IGNORECASE))) == 1
        )
        sphinx_builtin_union = bool(
            re.match(
                r"^(?:either\s+)?(?:a|an|the)\s+:class:`[^`]+`\s+or\s+"
                r"(?:(?:a|an|the|as)\s+)?(?:float|double|integer|int|boolean|bool|string|str|bytes|"
                r"rational|real\s+number|floating[- ]point\s+number)\b",
                output,
                re.IGNORECASE,
            )
            and len(re.findall(r"\bor\b", output, re.IGNORECASE)) == 1
            and len(set(re.findall(r":class:`([^`]+)`", output, re.IGNORECASE))) == 1
        )
        # ``whether or not`` is a logical predicate in the explanatory
        # clause, not an alternative return type.  Remove that phrase only
        # for the outer-union guard; genuine ``class or tuple``/``class or
        # boolean`` alternatives remain fail-closed.
        output_for_union_guard = re.sub(
            r"\bwhether\s+or\s+not\b", "", output, flags=re.IGNORECASE
        )
        # A prose enumeration such as ``no '^', '->', or '<->'`` lists
        # literal tokens, rather than alternative result families.  Remove
        # only the connective immediately preceding a quoted literal before
        # applying the fail-closed union guard.  Unquoted ``list or tuple``
        # and every ordinary conditional branch remain guarded below.
        output_for_union_guard = re.sub(
            r"\bor\s+(?=(?:['\"`]))", "", output_for_union_guard, flags=re.IGNORECASE
        )
        explanatory_or_clause = bool(
            re.search(
                r"\bor\s+(?:the\s+)?(?:absolute|original|same|given)\b",
                output_for_union_guard,
                re.IGNORECASE,
            )
            and not re.search(
                r"\bor\s+(?:(?:a|an|the)\s+)?"
                r"(?:integer|int|long|float|double|boolean|bool|bytes|list|tuple|pair|set|dict|dictionary|"
                r"matrix|vector|polynomial|point|object|color|rational|real|complex|infinity|function|morphism|none|nothing)\b",
                output_for_union_guard,
                re.IGNORECASE,
            )
        )
        if re.search(r"\b(?:or|either)\b", output_for_union_guard) and not (
            numeric_integer_alternatives
            or same_integer_alternative
            or prime_integer_alternatives
            or container_element_alternatives
            or atomic_container_prefix
            or pair_optional_contract
            or pair_boolean_contract
            or optional_container_contract
            or optional_sphinx_class
            or sphinx_simple_union
            or sphinx_builtin_union
            or integer_rational_contract
            or optional_integer_contract
            or iterator_element_contract
            or class_role_union_contract
            or descriptive_or_before_role
            or descriptive_scalar_alternative
            or explanatory_or_clause
        ):
            return None
        if optional_container_contract:
            return {
                "list": "list | None",
                "tuple": "tuple | None",
                "pair": "tuple | None",
                "set": "set | None",
                "dictionary": "dict | None",
                "dict": "dict | None",
            }[optional_container_contract.group("kind").casefold()]
        if output.startswith(("none if", "nothing if")):
            return None
        if optional_integer_contract:
            return "'sage.rings.integer.Integer | None'"

        # An iterator remains a single Python protocol even when the
        # documentation describes alternative element values (for example
        # rational numbers or infinity).  The element type is deliberately
        # left open, while ``__next__``/iteration completion stays available.
        if iterator_element_contract:
            return "Iterator"

        # These two source phrases carry a concrete parent-preserving or
        # finite-field contract even though they are not written as Sphinx
        # class roles.  The residue field at a prime is one of Sage's finite
        # field implementations; addition of sandpile values preserves the
        # receiver class.
        if re.fullmatch(r"the\s+residue\s+field\s+at\s+this\s+prime\s*[.!?]?", output, re.IGNORECASE):
            return FINITE_FIELD_UNION
        if re.fullmatch(r"the\s+characteristic\s+of\s+the\s+residue\s+field\s*[.!?]?", output, re.IGNORECASE):
            return "'sage.rings.integer.Integer'"
        if owner_name and re.match(r"^(?:SandpileConfig|SandpileDivisor)$", owner_name, re.IGNORECASE):
            if re.match(r"^(?:sum|difference)\s+of\s+``self``\s+and\s+``other``(?:[.!?\s]|$)", output, re.IGNORECASE):
                return "Self"

        # A documented function/lambda is a Python callable even if its
        # argument and result domains are intentionally left abstract.  Only
        # accept an unambiguous function-valued result; conditional branches
        # and explicit alternatives stay fail-closed above.
        callable_output = output.lstrip("- ").strip()
        if (
            (
                re.match(r"^(?:a|an|the)\s+(?:[a-z][a-z0-9_-]*\s+){0,3}(?:function|lambda\s+function)\b", callable_output, re.IGNORECASE)
                or re.match(r"^returns?\s+(?:a|an|the)\s+(?:[a-z][a-z0-9_-]*\s+){0,3}function\b", callable_output, re.IGNORECASE)
            )
            and not re.search(r"\b(?:or|either|depending|if|otherwise|none|nothing)\b", callable_output, re.IGNORECASE)
        ):
            return "Callable[..., Any]"

        # ``prime_powers`` is documented as a mathematical set but returns a
        # sorted Python list in Sage.  Check this before the generic ``set``
        # container rule below so the runtime-backed correction is retained.
        if re.match(r"^the set of all prime powers\b", output):
            return "list"
        # Resolve a source-indexed multi-word class before interpreting its
        # first word as a generic container.  ``a set partition`` therefore
        # remains the unique ``SetPartition`` class, while ``a set of ...``
        # continues to lower to Python ``set`` below.
        if class_index:
            plain_class = _doc_plain_class_annotation(output, class_index, module_name)
            if plain_class is not None:
                return plain_class
        leading_scalar_annotation = _doc_leading_scalar_output_annotation(output)
        if leading_scalar_annotation is not None:
            return leading_scalar_annotation
        output_shape_annotation = _doc_structural_output_shape_annotation(output)
        if output_shape_annotation is not None:
            return output_shape_annotation

        # Sage docstrings commonly qualify an outer Python container with
        # words such as ``new``, ``sorted`` or ``increasing``.  Once the
        # union/conditional guard above has run, those adjectives do not
        # change the result family: ``a sorted tuple of ...`` is still a
        # tuple, and ``a new list ...`` is still a list.  Keep the element
        # contract deliberately broad because it may be parent-dependent.
        container_head = re.match(
            r"^(?:a|an|the)\s+(?:(?:new|sorted|increasing|decreasing|ordered|"
            r"duplicate-free|finite|immutable|lazy|enumerated|nonempty)\s+)*"
            r"(list|tuple|pair|set|dictionary|dict)\b",
            output,
        )
        if container_head:
            return {
                "list": "list",
                "tuple": "tuple",
                "pair": "tuple",
                "set": "set",
                "dictionary": "dict",
                "dict": "dict",
            }[container_head.group(1)]
        returned_container = re.search(
            r"\breturns?\s+(?:a|an|the)\s+(?:(?:new|sorted|increasing|decreasing|ordered|"
            r"duplicate-free|finite|immutable|lazy|enumerated|nonempty)\s+)*"
            r"(list|tuple|pair|set|dictionary|dict)\b",
            output,
            re.IGNORECASE,
        )
        if returned_container and not re.search(
            r"\b(?:or|either|depending|if|otherwise|unless|none|nothing)\b",
            output[returned_container.start() :],
            re.IGNORECASE,
        ):
            return {
                "list": "list",
                "tuple": "tuple",
                "pair": "tuple",
                "set": "set",
                "dictionary": "dict",
                "dict": "dict",
            }[returned_container.group(1).casefold()]
        returned_iterator = re.search(
            r"\breturns?\s+(?:a|an|the)\s+(?:python\s+)?(?:iterator|generator)\b",
            output,
            re.IGNORECASE,
        )
        if returned_iterator and not re.search(
            r"\b(?:or|either|depending|if|otherwise|unless|none|nothing)\b",
            output[returned_iterator.start() :],
            re.IGNORECASE,
        ):
            return "Iterator"

        for prefix, annotation in DOC_OUTPUT_PREFIX_RETURNS:
            if output.startswith(prefix + ";") or output.startswith(prefix + ",") or output.startswith(prefix + "."):
                return annotation
            if prefix == "boolean" and output.startswith(("boolean indicating ", "boolean stating ")):
                return annotation
            if prefix == "string" and output.startswith("string "):
                return annotation

        if output in {"int", "python integer"}:
            return "int"
        if output.startswith(("python list", "a python list")):
            return "list"
        if output.startswith(("python dictionary", "a python dictionary")):
            return "dict"
        if output.startswith(("python set", "a python set")):
            return "set"
        if output.startswith(("none", "nothing")) and " if " not in output:
            return "None"
        if output.startswith(("true", "false")) and not re.search(
            r"\b(?:or|either|tuple|dictionary|list|notimplemented)\b", output
        ):
            # Do not turn rich-comparison methods into a bool contract merely
            # because their docs say ``True``/``False``: Python permits
            # ``NotImplemented`` from those hooks.  Explicit ``__bool__``
            # remains covered by PROTOCOL_RETURNS above.
            if not node.name.startswith(("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__")):
                return "bool"
        if output.startswith(("a boolean", "an boolean")) and not node.name.startswith(
            ("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__")
        ):
            return "bool"
        if output.startswith(("a fragment of html", "an html fragment", "printed string")):
            return "str"
        if re.match(r"^squarefree positive integer\b", output):
            return "'sage.rings.integer.Integer'"
        # The maximal quotient rational-reconstruction variant explicitly
        # permits ``None``, so preserve that optionality in its pair result.
        if pair_optional_contract:
            return "tuple | None"
        if pair_boolean_contract:
            return "tuple | bool"
        if re.match(r"^(?:this method )?(?:does not )?return(?:s)? (?:nothing|anything)\b", output):
            return "None"
        if output.startswith("the nonnegative integer"):
            return "'sage.rings.integer.Integer'"
        if output.startswith("the ascii integer"):
            # ``ascii_integer`` deliberately returns a Python int, unlike
            # Sage's arithmetic helpers which return ``Integer``.
            return "int"
        if output.startswith("the binary representation of"):
            # The Sage crypto utility returns a StringMonoidElement (the
            # runtime type of ``ascii_to_bin``), not a plain Python string.
            return "'sage.monoids.string_monoid_element.StringMonoidElement'"
        if output.startswith("the ascii string corresponding"):
            return "str"
        if re.match(r"^the `{0,2}k`{0,2} least significant bits", output):
            return "list"
        if output.startswith(("positive integer", "nonnegative integer", "integer (", "integer `", "integer.")):
            return "'sage.rings.integer.Integer'"
        if re.match(
            r"^(?:(?:a|an|the)\s+)?(?:positive|nonnegative|negative|prime)?\s*integer\b.*\bor\s+(?:-?\d+|(?:an?\s+)?(?:positive|nonnegative|negative|prime)?\s*integer)\b",
            output,
            re.IGNORECASE,
        ):
            # Both branches are Sage integers; this is not a heterogeneous
            # union such as ``integer or rational``.
            return "'sage.rings.integer.Integer'"
        if output.startswith(("a sage integer", "an sage integer", "the sage integer")):
            return "'sage.rings.integer.Integer'"
        if output.startswith("a prime ") and re.search(r"\bor\b", output) and re.search(r"\bn\b", output):
            # ``trial_division`` documents both branches as integer values:
            # the discovered prime or the original integer when no divisor is
            # found.  This is one concrete Sage scalar, not a type union.
            return "'sage.rings.integer.Integer'"
        if output.startswith("the integer"):
            return "'sage.rings.integer.Integer'"
        if re.match(r"^the number of .*\bas an integer\b", output):
            return "'sage.rings.integer.Integer'"
        if output.startswith(("the carmichael function", "the `n`-th prime number")):
            return "'sage.rings.integer.Integer'"
        if output in {"rational", "rational number"} or output.startswith("a rational number"):
            return "'sage.rings.rational.Rational'"
        # Structured OUTPUT prose often uses an unqualified mathematical
        # noun.  These result families are already represented by concrete
        # implementation unions above; expose them here only after the
        # conditional/union guard so ``a matrix or a tuple`` stays UNKNOWN.
        if re.match(r"^(?:(?:a|an|the)\s+)?matrix\b", output, re.IGNORECASE) and not re.search(
            r"\b(?:matrix\s+(?:group|list|morphism)|or|either|depending|if)\b",
            output,
            re.IGNORECASE,
        ):
            return MATRIX_ELEMENT_UNION
        if re.match(
            r"^(?:(?:a|an|the)\s+)?(?:(?:new|normalized|reduced|irreducible|monic|univariate|multivariate|Laurent)\s+)?polynomial\b",
            output,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:polynomial\s+matrix|or|either|depending|if)\b", output, re.IGNORECASE):
            return POLYNOMIAL_RETURN_UNION
        if re.match(
            r"^(?:a|an|the)\s+(?:[a-z][a-z0-9'_-]*\s+){1,4}polynomial\b",
            output,
            re.IGNORECASE,
        ) and not re.search(r"\b(?:polynomial\s+matrix|or|either|depending|if)\b", output, re.IGNORECASE):
            return POLYNOMIAL_RETURN_UNION
        if re.match(r"^(?:(?:a|an|the)\s+)?(?:codeword|vector)\b", output, re.IGNORECASE) and not re.search(
            r"\b(?:or|either|depending|if)\b", output, re.IGNORECASE
        ):
            return VECTOR_ELEMENT_UNION
        if re.match(r"^(?:(?:a|an|the)\s+)?vector\s+of\b", output, re.IGNORECASE) and not re.search(
            r"\b(?:or|either|depending|if)\b", output, re.IGNORECASE
        ):
            return VECTOR_ELEMENT_UNION
        if re.match(r"^(?:a|an|the)\s+(?:positive\s+)?real\s+number\b", output, re.IGNORECASE) and not re.search(
            r"\b(?:or|either|depending|if|infinity)\b", output, re.IGNORECASE
        ):
            return REAL_NUMBER_RETURN_UNION
        if re.match(r"^real\s+number\b", output, re.IGNORECASE) and not re.search(
            r"\b(?:or|either|depending|if|infinity)\b", output, re.IGNORECASE
        ):
            return REAL_NUMBER_RETURN_UNION
        if re.match(r"^(?:a|an|the)\s+finite\s+or\s+infinite\s+real\s+number\b", output, re.IGNORECASE):
            return REAL_OR_INFINITY_RETURN_UNION
        if re.match(r"^(?:an?\s+)?integer\s+or\s+rational\s+number\b", output, re.IGNORECASE):
            return INTEGER_RATIONAL_RETURN_UNION
        if re.match(r"^matroid(?:\s|$)", output, re.IGNORECASE) and not re.search(
            r"\b(?:or|either|depending|if)\b", output, re.IGNORECASE
        ):
            return MATROID_RETURN_UNION
        if re.match(r"^(?:a|an|the)\s+polyhedron\b", output, re.IGNORECASE):
            return POLYHEDRON_RETURN_UNION
        if re.match(r"^(?:a|an|the)\s+matroid\b", output, re.IGNORECASE):
            return MATROID_RETURN_UNION
        if re.match(r"^(?:a|an|the)\s+finite\s+lattice\b", output, re.IGNORECASE):
            return FINITE_POSET_RETURN_UNION
        if re.match(r"^(?:a|an|the)\s+finite\s+field\b", output, re.IGNORECASE):
            return FINITE_FIELD_UNION
        if re.match(r"^(?:(?:a|an|the)\s+)?3[- ]?d\s+graphic\s+object\b", output, re.IGNORECASE):
            return "'sage.plot.plot3d.base.Graphics3d'"
        for phrase, annotation in DOC_OUTPUT_NAMED_CLASSES:
            if output == phrase or output.startswith(phrase + " ") or output.startswith(phrase + "."):
                return annotation
        if class_index:
            # Resolve a source-indexed class before generic container words
            # such as ``set`` are considered (``a set partition`` is a
            # SetPartition, not a Python set).
            plain_class = _doc_plain_class_annotation(output, class_index, module_name)
            if plain_class is not None:
                return plain_class
        if output.startswith("an exact copy of ``self``") or output.startswith("a copy of ``self``"):
            return "Self"
        if output.startswith(("a pair", "pair ", "a 2-tuple", "a 3-tuple", "a 4-tuple")):
            return "tuple"
        # A documented Python container is a concrete runtime type even when
        # the element type is intentionally left open.  Do not apply this to
        # union/conditional descriptions (guarded above) or to prose such as
        # ``list, dictionary`` where the result itself is ambiguous.
        if not re.search(r",\s*(?:a |an |the )?(?:list|tuple|set|dict|dictionary|boolean|none|integer)\b", output):
            if re.match(r"^(?:a |an |the |sorted )?(?:list|tuple|set|dictionary|dict|frozenset)\b", output):
                kind = re.match(r"^(?:a |an |the |sorted )?(?P<kind>list|tuple|set|dictionary|dict|frozenset)\b", output).group("kind")
                return {"list": "list", "tuple": "tuple", "set": "set", "dictionary": "dict", "dict": "dict", "frozenset": "frozenset"}[kind]
        if class_index:
                # Keep the original capitalization for Sphinx targets (e.g.
                # ``matplotlib.colors.Colormap``); the lower-case copy above
                # is reserved for prose matching.
                return _doc_output_class_annotation(raw_output, class_index, module_name)
    # A predicate summary is a source-level boolean contract when its
    # docstring does not advertise an alternate payload (for example
    # ``get_data=True`` returning a pair).  Dunder comparisons stay
    # fail-closed because Python permits ``NotImplemented``.
    boolean_literal_summary = bool(
        re.match(
            r"^return\s+(?:true|false)(?:\s+(?:if|when)\b.*|\s+or\s+(?:true|false))?[.!?]?$",
            summary,
            re.IGNORECASE,
        )
    )
    if not node.name.startswith("__") and (
        re.match(r"^(?:test|check|determine)\s+(?:whether|if)|^whether\s+", summary)
        or boolean_literal_summary
    ):
        # ``whether or not`` and ordinary explanatory prose frequently use
        # ``or`` in the body; that does not make the predicate's result a
        # union.  Only explicit alternate-payload markers keep this branch
        # fail-closed (for example a documented ``get_data`` pair).
        lowered = value.lower()
        if not re.search(r"\b(?:get_data|tuple|pair|dictionary|list|notimplemented)\b", lowered):
            return "bool"
    # Sage's predicate helpers are not uniform enough for a name-only guess,
    # but their documentation almost always states the predicate wording in
    # the summary (``is_*``/``has_*``/``contains_*`` plus ``whether``/``if``
    # or an explicit True/False).  Require that source-level wording and keep
    # the same alternate-payload guard as above; methods such as
    # ``is_planar(kuratowski=True)`` therefore remain unresolved unions.
    if node.name.startswith(("is_", "has_", "can_", "contains_", "exists_")) and (
        re.search(r"\b(?:whether|if|true|false|boolean|predicate)\b", summary, re.IGNORECASE)
        or re.match(rf"{re.escape(node.name)}\s*\(", summary, re.IGNORECASE)
    ):
        lowered = value.lower()
        if not re.search(r"\b(?:get_data|tuple|pair|dictionary|list|notimplemented)\b", lowered):
            return "bool"
    if re.match(r"^(?:string|latex|\\latex)\s+representation\b", summary, re.IGNORECASE):
        return "str"
    metric_annotation = _doc_metric_contract_annotation(node, raw_summary, owner_name)
    if metric_annotation is not None:
        return metric_annotation
    # Any remaining ``__iter__`` implementation still satisfies the Python
    # iterator protocol even when its prose is only an examples block or a
    # domain-specific description.  Do not guess the yielded element type.
    if node.name == "__iter__":
        return "Iterator"
    return None


def _build_class_index(root: Path) -> dict[str, tuple[str, ...]]:
    """Build unique lower-case class-name -> canonical source class mappings."""
    candidates: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.pyi")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
        except SyntaxError:
            continue
        relative = path.relative_to(root)
        parts = list(relative.parts)
        filename = parts.pop()
        module_parts = parts if filename == "__init__.pyi" else parts + [Path(filename).stem]
        module = ".".join(module_parts)
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            key = re.sub(r"[^a-z0-9]", "", node.name.casefold())
            candidates.setdefault(key, set()).add(f"{module}.{node.name}")
    return {key: tuple(sorted(values)) for key, values in candidates.items()}


def _replace_folded_cartan_self_returns(
    text: str,
    class_index: dict[str, tuple[str, ...]] | None = None,
) -> tuple[str, list[str]]:
    """Replace stale ``Self`` Cartan-folding contracts with the runtime type.

    A handful of generated abstract stubs predate the concrete Sage contract
    and annotate ``_default_folded_cartan_type`` as ``Self``.  The method's
    documented result is a ``CartanTypeFolded`` wrapper (and every concrete
    implementation returns that wrapper at runtime), so retaining ``Self``
    hides ``folding_orbit`` and related members in the IDE.  Match the
    semantic documentation and the existing annotation rather than a class
    or method allow-list; unrelated ``Self`` contracts remain untouched.
    """
    try:
        tree = ast.parse(text, type_comments=True)
    except SyntaxError:
        return text, []
    line_offsets = _line_offsets(text)
    folded_candidates = (class_index or {}).get("cartantypefolded", ())
    folded_annotation = (
        f"'{folded_candidates[0]}'"
        if len(folded_candidates) == 1
        else "'sage.combinat.root_system.type_folded.CartanTypeFolded'"
    )
    replacements: list[tuple[int, int, str, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or node.returns is None:
            continue
        if not (isinstance(node.returns, ast.Name) and node.returns.id == "Self"):
            continue
        docstring = ast.get_docstring(node, clean=False)
        if not docstring:
            continue
        summary_lines: list[str] = []
        for line in docstring.splitlines():
            stripped = line.strip()
            if not stripped:
                if summary_lines:
                    break
                continue
            summary_lines.append(stripped)
        summary = re.sub(r"\s+", " ", " ".join(summary_lines))
        if not re.match(r"^return the default folded cartan type\.?$", summary, re.IGNORECASE):
            continue
        start = line_offsets[node.returns.lineno - 1] + node.returns.col_offset
        end = line_offsets[node.returns.end_lineno - 1] + node.returns.end_col_offset
        if text[start:end] != "Self":
            continue
        replacements.append(
            (
                start,
                end,
                folded_annotation,
                node.name,
            )
        )
    if not replacements:
        return text, []
    for start, end, replacement, _ in sorted(replacements, reverse=True):
        text = text[:start] + replacement + text[end:]
    return text, [name for _, _, _, name in replacements]


def annotate_doc_output_returns(path: Path, class_index: dict[str, tuple[str, ...]] | None = None) -> list[str]:
    """Apply exact structured ``OUTPUT:`` contracts to missing returns."""
    text = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text, filename=str(path), type_comments=True)
    except SyntaxError:
        return []
    line_offsets = _line_offsets(text)
    edits: list[tuple[int, str, str]] = []
    # ``database_matroids`` is a generated catalogue of constructors.  Its
    # module-level functions all return concrete matroid implementations, so
    # pass an explicit contract owner to the shared metric resolver.
    module_path = path.as_posix()
    path_parts = list(path.parts)
    try:
        sage_index = next(index for index, part in enumerate(path_parts) if part == "sage")
    except StopIteration:
        source_module = None
    else:
        module_parts = path_parts[sage_index:]
        module_parts[-1] = module_parts[-1][:-4] if module_parts[-1].endswith(".pyi") else module_parts[-1]
        source_module = ".".join(module_parts)
    module_contract_owner = (
        "MatroidDatabaseModule"
        if module_path.endswith("sage/matroids/database_matroids.pyi")
        else "DesignDatabaseModule"
        if module_path.endswith("sage/combinat/designs/database.pyi")
        else "GraphFamiliesModule"
        if module_path.endswith("sage/graphs/generators/families.pyi")
        else "SmallGraphsModule"
        if module_path.endswith("sage/graphs/generators/smallgraphs.pyi")
        else "DistanceRegularGraphsModule"
        if module_path.endswith("sage/graphs/generators/distance_regular.pyi")
        else "HadamardMatrixModule"
        if module_path.endswith("sage/combinat/matrices/hadamard_matrix.pyi")
        else "FunctionalModule"
        if module_path.endswith("sage/misc/functional.pyi")
        else "StronglyRegularDatabaseModule"
        if module_path.endswith("sage/graphs/strongly_regular_db.pyi")
        else None
    )

    def visit_class(node: ast.ClassDef) -> None:
        owner_bases = tuple(
            base.id if isinstance(base, ast.Name) else base.attr
            for base in node.bases
            if isinstance(base, (ast.Name, ast.Attribute))
        )
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if member.returns is None:
                    annotation = _doc_output_annotation(
                        member, class_index, node.name, source_module, owner_bases
                    )
                    if annotation is not None:
                        colon = _function_header_colon(text, line_offsets, member)
                        if colon is not None:
                            edits.append((colon, annotation, member.name))
            elif isinstance(member, ast.ClassDef):
                visit_class(member)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is None:
            annotation = _doc_output_annotation(node, class_index, module_contract_owner, source_module)
            if annotation is not None:
                colon = _function_header_colon(text, line_offsets, node)
                if colon is not None:
                    edits.append((colon, annotation, node.name))
        elif isinstance(node, ast.ClassDef):
            visit_class(node)
    needs_self = any(annotation == "Self" for _, annotation, _ in edits)
    if needs_self and not re.search(r"^from typing import .*\bSelf\b", text, re.MULTILINE):
        lines = text.splitlines(keepends=True)
        insertion = _typing_import_insertion_index(text, lines)
        lines.insert(insertion, "from typing import Self\n")
        text = "".join(lines)
        line_offsets = _line_offsets(text)
        # The import is inserted before the offsets used below.  Recompute
        # header locations so multiline function edits remain exact.
        edits = []
        try:
            tree = ast.parse(text, filename=str(path), type_comments=True)
        except SyntaxError:
            return []
        def collect(
            node: ast.AST,
            owner_name: str | None = None,
            owner_bases: tuple[str, ...] = (),
        ) -> None:
            if isinstance(node, ast.ClassDef):
                owner_name = node.name
                owner_bases = tuple(
                    base.id if isinstance(base, ast.Name) else base.attr
                    for base in node.bases
                    if isinstance(base, (ast.Name, ast.Attribute))
                )
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is None:
                annotation = _doc_output_annotation(
                    node, class_index, owner_name, source_module, owner_bases
                )
                if annotation is not None:
                    colon = _function_header_colon(text, line_offsets, node)
                    if colon is not None:
                        edits.append((colon, annotation, node.name))
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    collect(child, owner_name, owner_bases)
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                collect(node)
    for offset, annotation, _ in sorted(edits, reverse=True):
        text = text[:offset] + f" -> {annotation}" + text[offset:]
    text, folded_edits = _replace_folded_cartan_self_returns(text, class_index)
    if edits or folded_edits:
        path.write_text(text, encoding="utf-8")
        for typing_name, marker in (
            ("Self", "Self"),
            ("Iterator", "Iterator"),
            ("NoReturn", "NoReturn"),
        ):
            if any(annotation == marker or marker + "[" in annotation for _, annotation, _ in edits):
                ensure_typing_name(path, typing_name)
    return [name for _, _, name in sorted(edits)] + folded_edits


def remove_inserted(path: Path, member: str) -> bool:
    # Remove an earlier stub-only forwarding declaration for member.
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    pattern = re.compile(r"^\s*def\s+" + re.escape(member) + r"\s*\(", re.MULTILINE)
    text = "".join(lines)
    if not pattern.search(text):
        return False
    keep = []
    removed = False
    for line in lines:
        if _DEF_RE.match(line) and _DEF_RE.match(line).group("name") == member and not removed:
            removed = True
            continue
        keep.append(line)
    if removed:
        path.write_text("".join(keep), encoding="utf-8")
    return removed


def verify(path: Path) -> None:
    ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Annotate curated Sage stubs")
    parser.add_argument(
        "--stub-root",
        type=Path,
        default=Path("G:/sage-build/sage-typings-10.9"),
        help="Root of the Sage stub tree containing the sage/ directory.",
    )
    parser.add_argument(
        "--source-contracts",
        type=Path,
        help=(
            "Optional JSON map from infer_source_returns.py.  Contracts are "
            "applied only to missing returns after the document/protocol passes."
        ),
    )
    args = parser.parse_args()

    root = args.stub_root.resolve()
    total = 0
    shadowed_iterator_cleanup = 0
    for path in sorted(root.rglob("*.pyi")):
        if remove_shadowed_typing_iterator(path):
            verify(path)
            shadowed_iterator_cleanup += 1
    if shadowed_iterator_cleanup:
        print(f"typing Iterator shadow cleanup: {shadowed_iterator_cleanup} module(s)")
    for relative, classes in CURATED_FORWARDING_CLEANUPS.items():
        path = root / relative
        if not path.is_file():
            continue
        removed = cleanup_forwarding_declarations(path, classes)
        if removed:
            verify(path)
            print(f"{relative}: removed stale forwarders {', '.join(removed)}")
    for relative, classes in CURATED_ANNOTATIONS.items():
        path = root / relative
        if not path.is_file():
            print(f"annotate-stubs: missing {path} (skipped)")
            continue
        for class_name, members in classes.items():
            edited = annotate_add(path, members, class_name)
            if edited:
                verify(path)
                total += len(edited)
                print(f"{relative} [{class_name or '<module>'}]: annotated {", ".join(edited)}")
    for relative, classes in CURATED_ANNOTATIONS.items():
        path = root / relative
        if not path.is_file():
            continue
        annotations = [annotation for members in classes.values() for annotation in members.values()]
        for typing_name, marker in (
            ("Self", "Self"),
            ("Iterator", "Iterator["),
            ("Callable", "Callable["),
        ):
            if any(marker in annotation for annotation in annotations):
                if ensure_typing_name(path, typing_name):
                    verify(path)
                    print(f"{relative}: ensured typing import {typing_name}")
    for relative, classes in CURATED_REPLACE_ANNOTATIONS.items():
        path = root / relative
        if not path.is_file():
            continue
        if any("Self" in annotation for members in classes.values() for annotation in members.values()):
            if ensure_typing_name(path, "Self"):
                verify(path)
                print(f"{relative}: ensured typing import Self")
    for relative, classes in CURATED_REPLACE_ANNOTATIONS.items():
        path = root / relative
        if not path.is_file():
            print(f"annotate-stubs: missing {path} (skipped)")
            continue
        for class_name, members in classes.items():
            edited = annotate_replace(path, members, class_name)
            if edited:
                verify(path)
                total += len(edited)
                print(f"{relative} [{class_name or '<module>'}]: replaced {", ".join(edited)}")
    for relative, classes in CURATED_OVERLOADS.items():
        path = root / relative
        if not path.is_file():
            print(f"annotate-stubs: missing {path} (skipped)")
            continue
        for class_name, members in classes.items():
            edited = annotate_overloads(path, members, class_name)
            if edited:
                verify(path)
                total += len(edited)
                print(f"{relative} [{class_name or '<module>'}]: overloaded {", ".join(edited)}")
        if any(
            "Literal[" in declaration
            for members in classes.values()
            for declarations in members.values()
            for declaration in declarations
        ):
            if ensure_typing_name(path, "Literal"):
                verify(path)
                print(f"{relative}: ensured typing import Literal")
        if any(
            "Self" in declaration
            for members in classes.values()
            for declarations in members.values()
            for declaration in declarations
        ):
            if ensure_typing_name(path, "Self"):
                verify(path)
                print(f"{relative}: ensured typing import Self")
    for relative, names in CURATED_TYPE_VARIABLES.items():
        path = root / relative
        if not path.is_file():
            print(f"annotate-stubs: missing {path} (skipped)")
            continue
        if ensure_type_variables(path, names):
            verify(path)
            total += len(names)
            print(f"{relative}: ensured TypeVar {', '.join(names)}")
    for relative, classes in CURATED_INSERTIONS.items():
        path = root / relative
        if not path.is_file():
            print(f"annotate-stubs: missing {path} (skipped)")
            continue
        edited = annotate_insertions(path, classes)
        if edited:
            verify(path)
            total += len(edited)
            print(f"{relative}: inserted {", ".join(edited)}")
    protocol_total = 0
    for path in sorted(root.rglob("*.pyi")):
        edited = annotate_protocol_returns(path)
        if edited:
            verify(path)
            protocol_total += len(edited)
    if protocol_total:
        total += protocol_total
        print(f"protocol methods: annotated {protocol_total} missing return contract(s)")
    conditional_total = 0
    for path in sorted(root.rglob("*.pyi")):
        edited = annotate_conditional_output_overloads(path)
        if edited:
            verify(path)
            conditional_total += len(edited)
    if conditional_total:
        total += conditional_total
        print(f"conditional output overloads: annotated {conditional_total} member(s)")
    doc_output_total = 0
    class_index = _build_class_index(root)
    for path in sorted(root.rglob("*.pyi")):
        edited = annotate_doc_output_returns(path, class_index)
        if edited:
            verify(path)
            doc_output_total += len(edited)
    if doc_output_total:
        total += doc_output_total
        print(f"doc OUTPUT contracts: annotated {doc_output_total} exact return contract(s)")
    if args.source_contracts:
        # Keep source evidence as a separate, reproducible batch pass.  The
        # helper imports this module for shared offset/import routines, so load
        # it here (after module initialization) to avoid an import cycle.
        from apply_source_contracts import apply as apply_source_contracts

        contracts = json.loads(args.source_contracts.read_text(encoding="utf-8"))
        source_edited = apply_source_contracts(root, contracts)
        if source_edited:
            total += len(source_edited)
            print(f"source AST contracts: annotated {len(source_edited)} missing return contract(s)")
    # Roll back the earlier base-class forwarding hack (matrix0 solve_right).
    matrix0 = root / "sage/matrix/matrix0.pyi"
    if matrix0.is_file() and remove_inserted(matrix0, "solve_right"):
        verify(matrix0)
        print("sage/matrix/matrix0.pyi [Matrix]: removed forwarded solve_right")
    print(f"annotate-stubs: {total} member(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
