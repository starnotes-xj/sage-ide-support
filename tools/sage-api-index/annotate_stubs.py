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
# Power-series conversions expose concrete polynomial implementations selected
# by the univariate/multivariate parent.  Keep the implementation families
# explicit instead of returning the public ``Polynomial`` protocol base.
MULTIVARIATE_POLYNOMIAL_RETURN_UNION = (
    "'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular | "
    "sage.rings.polynomial.multi_polynomial_element.MPolynomial_polydict'"
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

# ADD: member name -> annotation expression for unannotated defs.
CURATED_ANNOTATIONS: dict[str, dict[str, dict[str, str]]] = {
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
            "gen": "'sage.rings.polynomial.polynomial_element.Polynomial'",
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
}

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
        },
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
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
# Rich comparisons are included as ``bool`` because Sage's ``_richcmp_`` hook
# is the implementation-level predicate consumed by Python's comparison
# protocol.  ``__getitem__``, arithmetic and ``__call__`` remain excluded;
# Sage is allowed to return NotImplemented, symbolic values, or a different
# parent there, so inventing a return type would violate the fail-closed rule.
PROTOCOL_RETURNS: dict[str, str] = {
    # Constructors/destructors are required by Python's data model to return
    # None.  This is a protocol guarantee, unlike Sage's dynamic factories.
    "__init__": "None",
    "__del__": "None",
    "__init_subclass__": "None",
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
    ("a sandpiledivisor", "'sage.sandpiles.sandpile.SandpileDivisor'"),
    ("sandpiledivisor", "'sage.sandpiles.sandpile.SandpileDivisor'"),
    ("a sandpileconfig", "'sage.sandpiles.sandpile.SandpileConfig'"),
    ("sandpileconfig", "'sage.sandpiles.sandpile.SandpileConfig'"),
    ("a sandpile", "'sage.sandpiles.sandpile.Sandpile'"),
    ("sandpile", "'sage.sandpiles.sandpile.Sandpile'"),
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
)

DOC_SUMMARY_COLLECTION_PATTERNS: tuple[tuple[str, str], ...] = (
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
            if not stripped or _DOC_SECTION_RE.match(stripped):
                break
            parts.append(stripped)
            cursor += 1
        if parts:
            # Bullet output descriptions are common in generated docs.  The
            # bullet is formatting, not part of the type contract.
            outputs.append(re.sub(r"^[-*]\s+", "", " ".join(parts)).strip())
    return tuple(outputs)


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
    # Key-schedule APIs declare a broad ``list`` while their docs make the
    # element type depend on the key representation.  Keep the implementation
    # declaration intact and expose precise list-element overloads alongside
    # it.  Other pre-annotated returns are left untouched.
    if declared_return is not None and declared_return not in {"list", "List"}:
        return None
    doc = ast.get_docstring(node, clean=False) or ""
    if not doc:
        return None
    compact = " ".join(doc.split())
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


def ensure_typing_name(path: Path, name: str) -> bool:
    """Add one typing import without disturbing existing import layout."""
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


def _doc_output_class_annotation(output: str, class_index: dict[str, tuple[str, ...]]) -> str | None:
    """Resolve a single Sphinx class role against the source class index.

    Sage's docstrings often use a lower-case Sphinx role (``:class:`digraph``)
    while the stub declaration is ``DiGraph``.  Resolving only one role whose
    target is unique gives a source-backed canonical class without a
    class/method allow-list.  Multiple roles, unions, iterators, and container
    descriptions remain unresolved because they do not identify one value.
    """
    roles = re.findall(r":class:`([^`]+)`", output)
    if roles:
        # ``:class:`tuple` of :class:`Foo``` describes one concrete Python
        # container even though the element role is also present.  Preserve
        # that outer container contract; unions such as ``Foo or tuple`` do
        # not match this prefix form and remain unknown.
        first = roles[0].strip().lstrip("~").casefold()
        builtin_first = DOC_OUTPUT_BUILTIN_CLASSES.get(first)
        if (
            len(roles) == 1
            and builtin_first is not None
            and not re.search(r"\b(?:or|either|iterator|sequence)\b", output)
        ):
            # Qualifiers such as ``increasing`` do not change the outer
            # builtin container.  Keep this before the ambiguity check below
            # so the role's own word (``tuple``/``list``/...) is not mistaken
            # for a union.
            return builtin_first
        if len(roles) > 1 and first in {"tuple", "list", "set", "dict", "dictionary"}:
            return {"tuple": "tuple", "list": "list", "set": "set", "dict": "dict", "dictionary": "dict"}[first]
    if output.count(":class:`") != 1 or re.search(r"\b(?:or|either|iterator|list|tuple|set|sequence)\b", output):
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
    else:
        key = re.sub(r"[^a-z0-9]", "", target.casefold())
        candidates = class_index.get(key, ())
    return f"'{candidates[0]}'" if len(candidates) == 1 else None


def _doc_plain_class_annotation(output: str, class_index: dict[str, tuple[str, ...]]) -> str | None:
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
        r"\s+(?:for|of|with|associated|corresponding|which|that|over|in|on)\b|[.,;:]",
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

    # A documented iterator is a stable Python protocol result even when the
    # yielded element type depends on the parent.  Keep that outer contract
    # explicit, but do not guess the element parameter (``Iterator[T]``).
    if re.match(r"^(?:an?|the)\s+iterator\b", normalized_rest, re.IGNORECASE):
        return "Iterator"
    if re.match(r"^(?:iterate|iterates)\s+over\b", summary, re.IGNORECASE):
        return "Iterator"

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
    if re.search(r"\b(?:or|either|depending)\b", normalized_rest):
        # A representation can depend on display options while its runtime
        # type remains a string.  Keep the general conditional guard for
        # every other value, but allow this source-level invariant before the
        # atomic return table is consulted below.
        if not re.match(r"^(?:a|an|the)\s+(?:string|latex|\\latex)\s+representation\b", normalized_rest):
            return None
    # ``if`` is a conditional payload marker except for the canonical
    # predicate form ``True/False if ...``.  Keep that one boolean contract
    # while rejecting ``a list if ...`` and similar unions.
    if re.search(r"\bif\b", normalized_rest) and not re.match(r"^(?:true|false)\b", normalized_rest, re.IGNORECASE):
        return None
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
    if container_summary:
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
    for phrase, annotation in DOC_OUTPUT_NAMED_CLASSES:
        if normalized_rest == phrase or normalized_rest.startswith(phrase + " ") or normalized_rest.startswith(phrase + "."):
            return annotation
    if node.name not in {"__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__"} and re.match(
        r"^(?:true|false)\b", normalized_rest, re.IGNORECASE
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
    return None


def _doc_summary_class_role_annotation(
    summary: str,
    class_index: dict[str, tuple[str, ...]] | None,
) -> str | None:
    """Resolve an explicitly returned Sphinx class in a summary sentence.

    Sage's generated docs often put the complete contract in the summary
    (``Return a :class:`Foo` ...`` or ``Construct an :class:`Foo` ...``)
    instead of an ``OUTPUT:`` section.  Restrict this fast path to verbs that
    construct/return a value; descriptions such as ``Generate code from an
    :class:`Expression``` are deliberately excluded because the role names an
    input rather than the result.
    """
    if not class_index or (
        ":class:" not in summary
        and not re.search(r"\b(?:object|instance|form)\b", summary, re.IGNORECASE)
    ):
        return None
    if not re.match(
        r"^(?:return|returns|construct|constructs|create|creates|build|builds|convert|converts)\s+",
        summary,
        re.IGNORECASE,
    ):
        return None
    # A role introduced by ``for``/``from``/``this`` is normally an input or
    # contextual class.  Keep explicit ``as ... of :class:`` result forms,
    # which are common in Sage conversion APIs.
    role_start = summary.find(":class:`")
    prefix = summary[:role_start].casefold()
    if re.search(r"\b(?:for|from|this|given|input|support)\s+(?:an?\s+)?$", prefix):
        return None
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


def _doc_self_preserving_summary_annotation(summary: str, owner_name: str | None) -> str | None:
    """Resolve summaries that explicitly promise a same-class result."""
    if owner_name is None:
        return None
    normalized = summary.replace(chr(96), "")
    if re.search(r"\bsame class as self\b", normalized, re.IGNORECASE):
        return "Self"
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
    if node.name == "order":
        return ORDER_RETURN_UNION
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


def _doc_output_annotation(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_index: dict[str, tuple[str, ...]] | None = None,
    owner_name: str | None = None,
) -> str | None:
    value = ast.get_docstring(node, clean=False)
    if not value:
        # Sage's ``TestSuite`` discovery contract treats every ``_test_*``
        # hook as an assertion routine: it raises on failure and returns
        # ``None`` on success.  This remains safe even when a generated stub
        # omitted the docstring entirely.
        if node.name.startswith("_test_"):
            return "None"
        # Python's data model requires ``__iter__`` to return an iterator.
        # The yielded element may depend on a dynamic Sage parent, so expose
        # only the stable outer protocol when no docstring gives a narrower
        # receiver-specific contract.
        if node.name == "__iter__":
            return "Iterator"
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
    if node.name.startswith("_test_"):
        return "None"
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
    self_preserving_annotation = _doc_self_preserving_summary_annotation(raw_summary, owner_name)
    if self_preserving_annotation is not None:
        return self_preserving_annotation
    summary_class_annotation = _doc_summary_class_role_annotation(raw_summary, class_index)
    if summary_class_annotation is not None:
        return summary_class_annotation
    numeric_summary_annotation = _doc_numeric_self_summary_annotation(raw_summary, owner_name)
    if numeric_summary_annotation is not None:
        return numeric_summary_annotation
    summary_annotation = _doc_summary_annotation(node, summary, class_index, owner_name)
    if summary_annotation is not None:
        return summary_annotation
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
        # Chinese-curated Sage docs and a few older modules put the declared
        # type before a ``--`` explanation (for example ``Integer -- ...``).
        # Read only that type token; ``any`` and mixed forms intentionally do
        # not become guesses.
        type_head = re.split(r"\s+(?:--|-)\s*", output, maxsplit=1)[0].strip()
        # Some source docstrings use ``(tuple) -- ...`` for an atomic outer
        # container.  Strip only the presentation wrapper; nested element
        # detail such as ``(tuple of Complex)`` still lowers to ``tuple``.
        parenthesized_head = re.fullmatch(
            r"\(\s*(tuple|list|set|dict|dictionary|integer|boolean|string)\s*\)",
            type_head,
        )
        if parenthesized_head:
            type_head = parenthesized_head.group(1)
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
        if re.match(r"^(?:an?\s+|the\s+)?integer\s+[a-z_]\w*\b", type_head) and not re.search(
            r"\b(?:or|either|if|depending|unless|otherwise)\b",
            output,
            re.IGNORECASE,
        ):
            return "'sage.rings.integer.Integer'"
        if re.match(r"^(?:an?\s+|the\s+)?python\s+long\b", type_head):
            return "int"
        if type_head in {"bool", "boolean"} and not node.name.startswith(
            ("__eq__", "__ne__", "__lt__", "__le__", "__gt__", "__ge__")
        ):
            return "bool"
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
                r".*\bor\s+(?:-?\d+|(?:an?\s+)?(?:positive|nonnegative|negative|prime)?\s*integer)\b",
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
        if re.search(r"\b(?:or|either)\b", output) and not (
            numeric_integer_alternatives
            or same_integer_alternative
            or prime_integer_alternatives
            or container_element_alternatives
            or atomic_container_prefix
            or pair_optional_contract
            or optional_container_contract
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
            plain_class = _doc_plain_class_annotation(output, class_index)
            if plain_class is not None:
                return plain_class

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
        for phrase, annotation in DOC_OUTPUT_NAMED_CLASSES:
            if output == phrase or output.startswith(phrase + " ") or output.startswith(phrase + "."):
                return annotation
        if class_index:
            # Resolve a source-indexed class before generic container words
            # such as ``set`` are considered (``a set partition`` is a
            # SetPartition, not a Python set).
            plain_class = _doc_plain_class_annotation(output, class_index)
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
            return _doc_output_class_annotation(output, class_index)
    # A predicate summary is a source-level boolean contract when its
    # docstring does not advertise an alternate payload (for example
    # ``get_data=True`` returning a pair).  Dunder comparisons stay
    # fail-closed because Python permits ``NotImplemented``.
    if not node.name.startswith("__") and re.match(
        r"^(?:test|check|determine)\s+(?:whether|if)|^return\s+(?:true|false)\b|^whether\s+",
        summary,
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
    if node.name.startswith(("is_", "has_", "can_", "contains_", "exists_")) and re.search(
        r"\b(?:whether|if|true|false|boolean|predicate)\b", summary, re.IGNORECASE
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
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if member.returns is None:
                    annotation = _doc_output_annotation(member, class_index, node.name)
                    if annotation is not None:
                        colon = _function_header_colon(text, line_offsets, member)
                        if colon is not None:
                            edits.append((colon, annotation, member.name))
            elif isinstance(member, ast.ClassDef):
                visit_class(member)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is None:
            annotation = _doc_output_annotation(node, class_index, module_contract_owner)
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
        def collect(node: ast.AST, owner_name: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                owner_name = node.name
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is None:
                annotation = _doc_output_annotation(node, class_index, owner_name)
                if annotation is not None:
                    colon = _function_header_colon(text, line_offsets, node)
                    if colon is not None:
                        edits.append((colon, annotation, node.name))
            for child in ast.iter_child_nodes(node):
                if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    collect(child, owner_name)
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                collect(node)
    for offset, annotation, _ in sorted(edits, reverse=True):
        text = text[:offset] + f" -> {annotation}" + text[offset:]
    if edits:
        path.write_text(text, encoding="utf-8")
        for typing_name, marker in (("Self", "Self"), ("Iterator", "Iterator")):
            if any(annotation == marker or marker + "[" in annotation for _, annotation, _ in edits):
                ensure_typing_name(path, typing_name)
    return [name for _, _, name in sorted(edits)]


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
    args = parser.parse_args()

    root = args.stub_root.resolve()
    total = 0
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
    # Roll back the earlier base-class forwarding hack (matrix0 solve_right).
    matrix0 = root / "sage/matrix/matrix0.pyi"
    if matrix0.is_file() and remove_inserted(matrix0, "solve_right"):
        verify(matrix0)
        print("sage/matrix/matrix0.pyi [Matrix]: removed forwarded solve_right")
    print(f"annotate-stubs: {total} member(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
