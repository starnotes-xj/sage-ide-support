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

# ADD: member name -> annotation expression for unannotated defs.
CURATED_ANNOTATIONS: dict[str, dict[str, dict[str, str]]] = {
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
        "EllipticCurvePoint_finite_field": {
            # The finite-field order algorithm returns a Sage Integer for
            # both PARI and the inherited generic-small paths.
            "_compute_order": "'sage.rings.integer.Integer'",
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
            # The generic curve API constructs a point on the curve.  More
            # specific curve classes override this below, so this remains
            # sound for non-finite base rings as well.
            "__call__": "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint'",
            "gen": "'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint'",
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
            "matrix_from_columns": "Self",
            "matrix_from_rows": "Self",
            "rank": "int",
            "swap_rows": "None",
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
        },
    },
    "sage/rings/finite_rings/finite_field_givaro.pyi": {
        "FiniteField_givaro": {
            "gen": "'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement'",
            "__iter__": "Iterator['sage.rings.finite_rings.element_givaro.FiniteField_givaroElement']",
        },
    },
    "sage/rings/finite_rings/finite_field_ntl_gf2e.pyi": {
        "FiniteField_ntl_gf2e": {
            "gen": "'sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement'",
            "__iter__": "Iterator['sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement']",
        },
    },
    "sage/rings/finite_rings/finite_field_pari_ffelt.pyi": {
        "FiniteField_pari_ffelt": {
            "gen": "'sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt'",
            "__iter__": "Iterator['sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt']",
        },
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
        "PolynomialRing_generic": {
            "gen": "'sage.rings.polynomial.polynomial_element.Polynomial'",
        },
        "PolynomialRing_dense_mod_p": {
            # Ordinary GF(p)[x] uses FLINT in Sage 10.9; this replaces the
            # historical NTL-only declaration when the generated stub has
            # already been curated once.
            "gen": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
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
        },
    },
    "sage/rings/rational_field.pyi": {
        "RationalField": {
            "__iter__": "Iterator['sage.rings.rational.Rational']",
            "range_by_height": "Iterator['sage.rings.rational.Rational']",
            "gen": "'sage.rings.rational.Rational'",
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
        },
    },
    "sage/rings/polynomial/polynomial_integer_dense_flint.pyi": {
        "Polynomial_integer_dense_flint": {
            "factor": "'sage.structure.factorization.Factorization'",
        },
    },
    "sage/rings/polynomial/polynomial_zmod_flint.pyi": {
        "Polynomial_zmod_flint": {
            "factor": "'sage.structure.factorization.Factorization'",
        },
    },
    "sage/rings/rational.pyi": {
        "Rational": {
            "factor": "'sage.structure.factorization.Factorization'",
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
    "sage/rings/polynomial/polynomial_zmod_flint.pyi": {
        "Polynomial_zmod_flint": {
            # GF(p)[x] evaluation/resultants produce the concrete modular
            # element family; polynomial transforms stay in this FLINT
            # implementation.  Rational reconstruction returns a pair of
            # polynomials in the same parent.
            "__call__": PRIME_FIELD_ELEMENT_UNION,
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
        },
    },
    "sage/rings/polynomial/polynomial_integer_dense_flint.pyi": {
        "Polynomial_integer_dense_flint": {
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
            "gen": "'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint'",
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

# OVERLOAD: documented parameter/return correlations which cannot be recovered
# from a broad union annotation alone.  These contracts are consumed by the
# generic overload machinery in the generated API index; the Kotlin plugin does
# not recognize these class or member names.
CURATED_OVERLOADS: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
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
            "def curve(self) -> 'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field': ...",
            "def _acted_upon_(self, other, side) -> 'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field': ...",
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
        ),
    },
    "sage/rings/finite_rings/finite_field_pari_ffelt.pyi": {
        "FiniteField_pari_ffelt": (
            "def __call__(self, x=0, *args, **kwds) -> 'sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt': ...",
            "def __iter__(self) -> Iterator['sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt']: ...",
        ),
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
        "PolynomialRing_dense_finite_field": (
            "def gen(self, n=0) -> 'sage.rings.polynomial.polynomial_element_generic.Polynomial_generic_dense_field': ...",
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

# Python's data-model methods have a language-level result contract that does
# not depend on a Sage class.  These are intentionally handled separately from
# CURATED_ANNOTATIONS: the pass applies to every Sage class with a missing
# annotation, while leaving an existing Sage-specific annotation untouched.
# Rich comparisons, __getitem__, arithmetic and __call__ are *not* included;
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
    "__nonzero__": "bool",
    "__int__": "int",
    "__float__": "float",
    "__complex__": "complex",
    "__dir__": "list[str]",
    "__divmod__": "tuple",
    "__len__": "int",
    "__index__": "int",
    "__hash__": "int",
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
_RETURN_RE = re.compile(r"\s*->\s*(.+):\s*$")
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
    if not line.lstrip().startswith("class "):
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
        lines[index] = stripped[: match.start(1)].rstrip() + " " + members[member] + ":\n"
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
        if current_class == class_name and line.strip() == "@overload":
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
        if any("Iterator[" in declaration for declarations in classes.values() for declaration in declarations):
            ensure_typing_name(path, "Iterator")
    return inserted


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
    if not class_index or ":class:`" not in summary:
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
    return _doc_output_class_annotation(summary, class_index)


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
    summary_class_annotation = _doc_summary_class_role_annotation(raw_summary, class_index)
    if summary_class_annotation is not None:
        return summary_class_annotation
    summary_annotation = _doc_summary_annotation(node, summary, class_index, owner_name)
    if summary_annotation is not None:
        return summary_annotation
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
        if type_head in {"integer", "sage integer"}:
            return "'sage.rings.integer.Integer'"
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
        # A collection whose *elements* have alternatives still has one
        # unambiguous outer result (for example ``a list of 0, 1 or 2
        # pairs``).  This is different from ``a list or tuple``.
        container_element_alternatives = bool(
            re.match(r"^(?:a|an|the)\s+(?:list|tuple|set|dictionary|dict)\s+of\b", output)
        )
        if re.search(r"\b(?:or|either)\b", output) and not (
            numeric_integer_alternatives
            or same_integer_alternative
            or prime_integer_alternatives
            or container_element_alternatives
            or pair_optional_contract
        ):
            return None
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
            annotation = _doc_output_annotation(node, class_index)
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
