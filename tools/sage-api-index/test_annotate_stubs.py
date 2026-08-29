import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PATCHER = ROOT / "annotate_stubs.py"
GENERATOR = ROOT / "generate.py"


class AnnotateStubsTest(unittest.TestCase):
    def test_language_protocol_returns_are_generic_multiline_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "protocols.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Value:\n"
                "    def __init__(self): ...\n"
                "    def __repr__(\n"
                "        self,\n"
                "    ): ...\n"
                "    def __len__(self): ...\n"
                "    def __contains__(self, value): ...\n"
                "    def __setitem__(self, key, value): ...\n"
                "    def __delitem__(self, key): ...\n"
                "    def __set__(self, instance, value): ...\n"
                "    def __delete__(self, instance): ...\n"
                "    def __setattr__(self, name, value): ...\n"
                "    def __setslice__(self, i, j, sequence): ...\n"
                "    def __instancecheck__(self, instance): ...\n"
                "    def __subclasscheck__(self, subclass): ...\n"
                "    def __int__(self): ...\n"
                "    def __float__(self): ...\n"
                "    def __complex__(self): ...\n"
                "    def __dir__(self): ...\n"
                "    def __copy__(self): ...\n"
                "    def __deepcopy__(self, memo): ...\n"
                "    def __dealloc__(self): ...\n"
                "    def __setstate__(self, state): ...\n"
                "    def __reduce__(self): ...\n"
                "    def _repr_(self): ...\n"
                "    def _latex_(self): ...\n"
                "    def __iter__(self):\n"
                "        " + '"""Return self, as per the iterator protocol."""' + "\n"
                "    def __eq__(self, other): ...\n"
                "\n"
                "class IteratorValue:\n"
                "    def __iter__(self):\n"
                "        " + '"""Return this iterator object itself."""' + "\n"
                "\n"
                "def __repr__(self): ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            # The annotation must precede the header colon, not the body
            # ellipsis.  Keep this assertion explicit so wrapped signatures
            # cannot regress.
            self.assertIn("    ) -> str: ...", patched)
            self.assertIn("def __init__(self) -> None: ...", patched)
            self.assertIn("def __len__(self) -> int: ...", patched)
            self.assertIn("def __contains__(self, value) -> bool: ...", patched)
            self.assertIn("def __setitem__(self, key, value) -> None: ...", patched)
            self.assertIn("def __delitem__(self, key) -> None: ...", patched)
            self.assertIn("def __set__(self, instance, value) -> None: ...", patched)
            self.assertIn("def __delete__(self, instance) -> None: ...", patched)
            self.assertIn("def __setattr__(self, name, value) -> None: ...", patched)
            self.assertIn("def __setslice__(self, i, j, sequence) -> None: ...", patched)
            self.assertIn("def __instancecheck__(self, instance) -> bool: ...", patched)
            self.assertIn("def __subclasscheck__(self, subclass) -> bool: ...", patched)
            self.assertIn("def __int__(self) -> int: ...", patched)
            self.assertIn("def __float__(self) -> float: ...", patched)
            self.assertIn("def __complex__(self) -> complex: ...", patched)
            self.assertIn("def __dir__(self) -> list[str]: ...", patched)
            self.assertIn("def __copy__(self) -> Self: ...", patched)
            self.assertIn("def __deepcopy__(self, memo) -> Self: ...", patched)
            self.assertIn("def __dealloc__(self) -> None: ...", patched)
            self.assertIn("def __setstate__(self, state) -> None: ...", patched)
            self.assertIn("def __reduce__(self) -> tuple | str: ...", patched)
            self.assertIn("def _repr_(self) -> str: ...", patched)
            self.assertIn("def _latex_(self) -> str: ...", patched)
            self.assertIn("def __iter__(self) -> Self:", patched)
            self.assertIn("class IteratorValue:\n    def __iter__(self) -> Self:", patched)
            self.assertIn("def __eq__(self, other): ...", patched)
            self.assertIn("def __repr__(self): ...", patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_exact_doc_output_contracts_are_typed_and_ambiguous_output_is_ignored(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "outputs.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def exact_integer(n):\n"
                "    \"\"\"\n"
                "    OUTPUT: integer\n"
                "    \"\"\"\n"
                "\n"
                "def exact_bool(n):\n"
                "    \"\"\"OUTPUT: boolean\"\"\"\n"
                "\n"
                "def block_length():\n"
                "    \"\"\"Return the block length of this cryptosystem.\"\"\"\n"
                "\n"
                "def output_size():\n"
                "    \"\"\"OUTPUT: the output size of this S-box\"\"\"\n"
                "\n"
                "def convert_to_vector(value, length):\n"
                "    \"\"\"OUTPUT: the ``L``-bit vector representation of ``I``\"\"\"\n"
                "\n"
                "def bit_layer(state):\n"
                "    \"\"\"Apply the substitution to the bit vector ``state`` and return the result.\"\"\"\n"
                "\n"
                "def round(state, key):\n"
                "    \"\"\"Apply one round of a block cipher to ``state`` and return the result.\"\"\"\n"
                "\n"
                "def list_to_string(bits):\n"
                "    \"\"\"OUTPUT: the binary string representation of ``bits``\"\"\"\n"
                "\n"
                "def binary_cipher(block, key):\n"
                "    \"\"\"Apply Mini-AES encryption or decryption on the binary string ``block``.\"\"\"\n"
                "\n"
                "def integer_to_binary(value):\n"
                "    \"\"\"Return the binary representation of ``value``. If ``value`` is a list, concatenate it.\"\"\"\n"
                "\n"
                "def eight_bit_cipher(value, key):\n"
                "    \"\"\"Return an 8-bit ciphertext corresponding to ``value``.\"\"\"\n"
                "\n"
                "def nth_subkey(value, n=1):\n"
                "    \"\"\"Return the `n`-th subkey based on ``value``.\"\"\"\n"
                "\n"
                "def random_key():\n"
                "    \"\"\"Return a random 10-bit key.\"\"\"\n"
                "\n"
                "def permutation(bits):\n"
                "    \"\"\"Return a permutation of a 10-bit string.\"\"\"\n"
                "\n"
                "def shift(bits):\n"
                "    \"\"\"Return a circular left shift of ``bits`` by one position.\n"
                "    The input is a vector of 10 bits.\"\"\"\n"
                "\n"
                "def permuted_choice_one(key):\n"
                "    \"\"\"Return permuted choice 1 of ``key``.\"\"\"\n"
                "\n"
                "def permuted_choice_two(key):\n"
                "    \"\"\"Return permuted choice 2 of ``key``.\"\"\"\n"
                "\n"
                "def expand(right):\n"
                "    \"\"\"Apply the expansion function to ``right``.\"\"\"\n"
                "\n"
                "def sboxes():\n"
                "    \"\"\"Return the S-boxes of simplified DES.\"\"\"\n"
                "\n"
                "def subkey(r):\n"
                "    \"\"\"Compute the sub key for round ``r`` derived from the initial key.\"\"\"\n"
                "\n"
                "def cipher_function(right, subkey):\n"
                "    \"\"\"Apply the cipher function to ``right`` and ``subkey``.\"\"\"\n"
                "\n"
                "def permute_substitute(block, key):\n"
                "    \"\"\"Apply the function on the block ``block`` using subkey ``key``.\"\"\"\n"
                "\n"
                "def variable_count():\n"
                "    \"\"\"The number of variables of this function.\"\"\"\n"
                "\n"
                "def ambiguous(n):\n"
                "    \"\"\"OUTPUT: an element of the base ring\"\"\"\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def exact_integer(n) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def exact_bool(n) -> bool:", patched)
            self.assertIn("def block_length() -> int:", patched)
            self.assertIn("def output_size() -> int:", patched)
            self.assertIn(
                "def convert_to_vector(value, length) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense':",
                patched,
            )
            self.assertIn(
                "def bit_layer(state) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense':",
                patched,
            )
            self.assertIn(
                "def round(state, key) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense':",
                patched,
            )
            self.assertIn(
                "def list_to_string(bits) -> 'sage.monoids.string_monoid_element.StringMonoidElement':",
                patched,
            )
            self.assertIn(
                "def binary_cipher(block, key) -> 'sage.monoids.string_monoid_element.StringMonoidElement':",
                patched,
            )
            self.assertIn(
                "def integer_to_binary(value) -> 'sage.monoids.string_monoid_element.StringMonoidElement':",
                patched,
            )
            self.assertIn("def eight_bit_cipher(value, key) -> list:", patched)
            self.assertIn("def nth_subkey(value, n=1) -> list:", patched)
            self.assertIn("def random_key() -> list:", patched)
            self.assertIn("def permutation(bits) -> list:", patched)
            self.assertIn("def shift(bits) -> list:", patched)
            self.assertIn("def permuted_choice_one(key) -> tuple:", patched)
            self.assertIn(
                "def permuted_choice_two(key) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense':",
                patched,
            )
            self.assertIn(
                "def expand(right) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense':",
                patched,
            )
            self.assertIn("def sboxes() -> list:", patched)
            self.assertIn("def subkey(r) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn(
                "def cipher_function(right, subkey) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense':",
                patched,
            )
            self.assertIn("def permute_substitute(block, key) -> list:", patched)
            self.assertIn("def variable_count() -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def ambiguous(n):", patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_conditional_output_overloads_follow_explicit_sage_docs_and_are_idempotent(self):
        """Documented integer/list-like branches expose concrete Sage results."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "cipher.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Cipher:\n"
                "    def encrypt(self, plaintext, key):\n"
                "        \"\"\"\n"
                "        OUTPUT:\n"
                "        - If ``plaintext`` is an integer the output will be too.\n"
                "        - If ``plaintext`` is list-like the output will be a bit vector.\n"
                "        \"\"\"\n"
                "\n"
                "    def __call__(self, block, key, algorithm='encrypt'):\n"
                "        \"\"\"If ``block`` is an integer the output will be too.\n"
                "        If ``block`` is list-like the output will be a bit vector.\"\"\"\n"
                "\n"
                "    def schedule(self, key) -> list:\n"
                "        \"\"\"If ``key`` is an integer the elements of the output list will be too.\n"
                "        If ``key`` is list-like the element of the output list will be bit vectors.\"\"\"\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn(
                "def encrypt(self, plaintext: int, key) -> 'sage.rings.integer.Integer': ... # sage-generated-conditional-output",
                patched,
            )
            self.assertIn(
                "def encrypt(self, plaintext: list, key) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense': ... # sage-generated-conditional-output",
                patched,
            )
            self.assertIn(
                "def __call__(self, block: int, key, algorithm = 'encrypt') -> 'sage.rings.integer.Integer': ... # sage-generated-conditional-output",
                patched,
            )
            self.assertIn(
                "def __call__(self, block: list, key, algorithm = 'encrypt') -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense': ... # sage-generated-conditional-output",
                patched,
            )
            self.assertIn(
                "def schedule(self, key: int) -> list['sage.rings.integer.Integer']: ... # sage-generated-conditional-output",
                patched,
            )
            self.assertIn(
                "def schedule(self, key: list) -> list['sage.modules.vector_mod2_dense.Vector_mod2_dense']: ... # sage-generated-conditional-output",
                patched,
            )
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_miniaes_matrix_contracts_bind_concrete_argument_parent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "block_cipher" / "miniaes.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class MiniAES:\n"
                "    def add_key(self, block, rkey): ...\n"
                "    def decrypt(self, C, key): ...\n"
                "    def encrypt(self, P, key): ...\n"
                "    def mix_column(self, block): ...\n"
                "    def nibble_sub(self, block, algorithm='encrypt'): ...\n"
                "    def round_key(self, key, n): ...\n"
                "    def shift_row(self, block): ...\n",
                encoding="utf-8",
            )
            stub.write_text(
                stub.read_text(encoding="utf-8")
                + "    def random_key(self):\n        ...\n"
                + "    def sbox(self):\n        ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("from typing import TypeVar", patched)
            self.assertIn("from typing import overload", patched)
            self.assertIn('MiniAEST = TypeVar("MiniAEST")', patched)
            for declaration in (
                "def add_key(self, block: MiniAEST, rkey: MiniAEST) -> MiniAEST: ...",
                "def decrypt(self, C: MiniAEST, key: MiniAEST) -> MiniAEST: ...",
                "def encrypt(self, P: MiniAEST, key: MiniAEST) -> MiniAEST: ...",
                "def mix_column(self, block: MiniAEST) -> MiniAEST: ...",
                "def nibble_sub(self, block: MiniAEST, algorithm='encrypt') -> MiniAEST: ...",
                "def round_key(self, key: MiniAEST, n) -> MiniAEST: ...",
                "def shift_row(self, block: MiniAEST) -> MiniAEST: ...",
                "def random_key(self) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense':",
                "def sbox(self) -> 'sage.crypto.sbox.SBox':",
            ):
                self.assertIn(declaration, patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_present_linear_layer_contract_returns_mod2_matrix(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "block_cipher" / "present.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def _smallscale_present_linearlayer(nsboxes=16):\n"
                "    ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn(
                "def _smallscale_present_linearlayer(nsboxes=16) -> 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense':",
                patched,
            )
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_sr_factory_and_crypto_helpers_keep_concrete_generator_families(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "mq" / "sr.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def SR(n=1, r=1, c=1, e=4, star=False, **kwargs):\n"
                "    ...\n"
                "class SR_generic:\n"
                "    def new_generator(self, **kwds):\n        ...\n"
                "    def sbox(self):\n        ...\n"
                "    def sub_bytes(self, d):\n        ...\n"
                "    def state_array(self, d=None):\n        ...\n"
                "    def hex_str(self, M, typ='matrix'):\n        ...\n"
                "    def block_order(self):\n        ...\n"
                "    def _insert_matrix_into_matrix(self, dst, src, row, col):\n        ...\n"
                "    def base_ring(self):\n        ...\n"
                "    def ring(self, order=None, reverse_variables=None):\n        ...\n"
                "    def sbox_constant(self):\n        ...\n"
                "    def sub_byte(self, b):\n        ...\n"
                "    def random_vector(self, *args, **kwds):\n        ...\n"
                "    def random_element(self, elem_type='vector', *args, **kwds):\n        ...\n"
                "class SR_gf2n(SR_generic):\n"
                "    def vector(self, d=None):\n        ...\n"
                "    def shift_rows_matrix(self):\n        ...\n"
                "    def phi(self, l):\n        ...\n"
                "    def antiphi(self, l):\n        ...\n"
                "    def inversion_polynomials(self, xi, wi, length):\n        ...\n"
                "class SR_gf2(SR_generic):\n"
                "    def vector(self, d=None):\n        ...\n"
                "    def ring(self, order=None, reverse_variables=None):\n        ...\n"
                "    def random_vector(self, *args, **kwds):\n        ...\n"
                "    def random_element(self, elem_type='vector', *args, **kwds):\n        ...\n"
                "    def phi(self, l):\n        ...\n"
                "    def antiphi(self, l):\n        ...\n"
                "    def _mul_matrix(self, x):\n        ...\n",
                encoding="utf-8",
            )
            stub.write_text(
                stub.read_text(encoding="utf-8")
                + "class AllowZeroInversionsContext:\n"
                + "    def __enter__(self):\n        ...\n"
                + "    def __exit__(self, typ, value, tb):\n        ...\n"
                + "def check_consistency(max_n=2, **kwargs):\n"
                + "    ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("from typing import Self", patched)
            self.assertIn("Literal", patched)
            self.assertIn(
                "def SR(n=1, r=1, c=1, e=4, star=False, *, gf2: Literal[False] = False, **kwargs) -> 'sage.crypto.mq.sr.SR_gf2n': ...",
                patched,
            )
            self.assertIn(
                "def SR(n=1, r=1, c=1, e=4, star=False, *, gf2: Literal[True], **kwargs) -> 'sage.crypto.mq.sr.SR_gf2': ...",
                patched,
            )
            self.assertIn("def new_generator(self, **kwds) -> Self:", patched)
            self.assertIn("def sbox(self) -> 'sage.crypto.sbox.SBox':", patched)
            self.assertIn("def base_ring(self) -> 'sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro':", patched)
            self.assertIn("def ring(self, order=None, reverse_variables=None) -> 'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomialRing_libsingular':", patched)
            self.assertIn("def sbox_constant(self) -> 'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement':", patched)
            self.assertIn("def sub_byte(self, b) -> 'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement':", patched)
            self.assertIn("def random_vector(self, *args, **kwds) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense':", patched)
            self.assertIn("def random_element(self, elem_type='vector', *args, **kwds) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense':", patched)
            self.assertIn("def ring(self, order=None, reverse_variables=None) -> 'sage.rings.polynomial.pbori.pbori.BooleanPolynomialRing':", patched)
            self.assertIn("def random_vector(self, *args, **kwds) -> 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense':", patched)
            self.assertIn("def random_element(self, elem_type='vector', *args, **kwds) -> 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense':", patched)
            self.assertIn("def sub_bytes(self, d) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense':", patched)
            self.assertIn("def state_array(self, d=None) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense':", patched)
            self.assertIn("def hex_str(self, M, typ='matrix') -> str:", patched)
            self.assertIn("def block_order(self) -> 'sage.rings.polynomial.term_order.TermOrder':", patched)
            self.assertIn("def vector(self, d=None) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense':", patched)
            self.assertIn("def vector(self, d=None) -> 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense':", patched)
            self.assertIn("def _mul_matrix(self, x) -> 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense':", patched)
            self.assertIn("def _insert_matrix_into_matrix(self, dst, src, row, col) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense':", patched)
            self.assertIn("def phi(self, l: list) -> list: ...", patched)
            self.assertIn("def antiphi(self, l: list) -> list: ...", patched)
            self.assertIn(
                "def phi(self, l: 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense') -> 'sage.matrix.matrix_mod2_dense.Matrix_mod2_dense': ...",
                patched,
            )
            self.assertIn("def inversion_polynomials(self, xi, wi, length) -> list:", patched)
            self.assertIn("def __enter__(self) -> None:", patched)
            self.assertIn("def __exit__(self, typ, value, tb) -> None:", patched)
            self.assertIn("def check_consistency(max_n=2, **kwargs) -> bool:", patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_classical_cryptosystem_contracts_match_runtime_key_and_text_families(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "classical.pyi"
            stub.parent.mkdir(parents=True)
            classes = {
                "AffineCryptosystem": (
                    "brute_force(self, C, ranking='none')",
                    "deciphering(self, a, b, C)",
                    "enciphering(self, a, b, P)",
                    "encoding(self, S)",
                    "inverse_key(self, a, b)",
                    "random_key(self)",
                ),
                "HillCryptosystem": (
                    "deciphering(self, A, C)",
                    "enciphering(self, A, M)",
                    "encoding(self, M)",
                ),
                "ShiftCryptosystem": (
                    "brute_force(self, C, ranking='none')",
                    "deciphering(self, K, C)",
                    "enciphering(self, K, P)",
                    "encoding(self, S)",
                    "inverse_key(self, K)",
                    "random_key(self)",
                ),
                "SubstitutionCryptosystem": (
                    "__call__(self, K)",
                    "random_key(self)",
                    "inverse_key(self, K)",
                    "encoding(self, M)",
                    "deciphering(self, K, C)",
                    "enciphering(self, K, M)",
                ),
                "TranspositionCryptosystem": (
                    "__call__(self, K)",
                    "random_key(self)",
                    "inverse_key(self, K, check=True)",
                    "encoding(self, M)",
                    "deciphering(self, K, C)",
                    "enciphering(self, K, M)",
                ),
                "VigenereCryptosystem": (
                    "__call__(self, K)",
                    "random_key(self)",
                    "inverse_key(self, K)",
                    "encoding(self, M)",
                    "deciphering(self, K, C)",
                    "enciphering(self, K, M)",
                ),
            }
            text = ""
            for class_name, methods in classes.items():
                text += f"class {class_name}:\n"
                for method in methods:
                    text += f"    def {method}:\n        ...\n"
            stub.write_text(text, encoding="utf-8")
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def brute_force(self, C, ranking='none') -> dict:", patched)
            self.assertIn("def inverse_key(self, a, b) -> tuple:", patched)
            self.assertIn("def random_key(self) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def __call__(self, K) -> 'sage.crypto.classical_cipher.SubstitutionCipher':", patched)
            self.assertIn("def random_key(self) -> 'sage.groups.perm_gps.permgroup_element.SymmetricGroupElement':", patched)
            self.assertIn("def __call__(self, K) -> 'sage.crypto.classical_cipher.VigenereCipher':", patched)
            self.assertGreaterEqual(patched.count("StringMonoidElement"), 20)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_classical_cipher_call_and_inverse_contracts_stay_concrete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "classical_cipher.pyi"
            stub.parent.mkdir(parents=True)
            classes = {
                "AffineCipher": ("__call__(self, M)",),
                "HillCipher": ("__call__(self, M)", "inverse(self)"),
                "ShiftCipher": ("__call__(self, M)",),
                "SubstitutionCipher": ("__call__(self, M)", "inverse(self)"),
                "TranspositionCipher": ("__call__(self, M, mode='ECB')", "inverse(self)"),
                "VigenereCipher": ("__call__(self, M, mode='ECB')", "inverse(self)"),
            }
            text = ""
            for class_name, methods in classes.items():
                text += f"class {class_name}:\n"
                for method in methods:
                    text += f"    def {method}:\n        ...\n"
            stub.write_text(text, encoding="utf-8")
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            string_type = "'sage.monoids.string_monoid_element.StringMonoidElement'"
            self.assertIn(f"def __call__(self, M) -> {string_type}:", patched)
            self.assertIn("def inverse(self) -> 'sage.crypto.classical_cipher.HillCipher':", patched)
            self.assertIn("def inverse(self) -> 'sage.crypto.classical_cipher.SubstitutionCipher':", patched)
            self.assertIn("def inverse(self) -> 'sage.crypto.classical_cipher.TranspositionCipher':", patched)
            self.assertIn("def inverse(self) -> 'sage.crypto.classical_cipher.VigenereCipher':", patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_lfsr_sequence_and_correlation_contracts_match_sage_scalars(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "lfsr.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def lfsr_sequence(key, fill, n):\n"
                "    ...\n"
                "def lfsr_autocorrelation(L, p, k):\n"
                "    ...\n"
                "def lfsr_connection_polynomial(s):\n"
                "    ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def lfsr_sequence(key, fill, n) -> list:", patched)
            self.assertIn("def lfsr_autocorrelation(L, p, k) -> 'sage.rings.rational.Rational':", patched)
            self.assertIn(
                "def lfsr_connection_polynomial(s) -> 'sage.rings.polynomial.polynomial_gf2x.Polynomial_GF2X | sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint | sage.rings.polynomial.polynomial_zz_pex.Polynomial_ZZ_pEX':",
                patched,
            )
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_generic_group_contracts_cover_ctf_discrete_log_helpers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "groups" / "generic.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def _parse_group_def(parent, operation, identity, inverse, op, check=True):\n    ...\n"
                "def _ord_from_op(x, op, param_name='ord'):\n    ...\n"
                "def discrete_log_generic(a, base, ord=None, bounds=None, operation='*'):\n    ...\n"
                "def linear_relation(P, Q, operation='+'):\n    ...\n"
                "def order_from_multiple(P, m, operation='+'):\n    ...\n"
                "def order_from_bounds(P, bounds, operation='+'):\n    ...\n"
                "class multiples:\n"
                "    def __iter__(self):\n        ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def _parse_group_def(parent, operation, identity, inverse, op, check=True) -> tuple:", patched)
            self.assertIn("def _ord_from_op(x, op, param_name='ord') -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def discrete_log_generic(a, base, ord=None, bounds=None, operation='*') -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def linear_relation(P, Q, operation='+') -> tuple['sage.rings.integer.Integer', 'sage.rings.integer.Integer']:", patched)
            self.assertIn("def order_from_multiple(P, m, operation='+') -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def order_from_bounds(P, bounds, operation='+') -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def __iter__(self) -> Self:", patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_stream_cipher_contracts_cover_lfsr_and_bbs_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stream = root / "sage" / "crypto" / "stream.pyi"
            cipher = root / "sage" / "crypto" / "stream_cipher.pyi"
            stream.parent.mkdir(parents=True)
            stream.write_text(
                "class LFSRCryptosystem:\n"
                "    def __call__(self, key):\n        ...\n"
                "    def encoding(self, M):\n        ...\n"
                "class ShrinkingGeneratorCryptosystem:\n"
                "    def __call__(self, key):\n        ...\n"
                "    def encoding(self, M):\n        ...\n"
                "def blum_blum_shub(length, seed=None):\n    ...\n",
                encoding="utf-8",
            )
            cipher.write_text(
                "class LFSRCipher:\n"
                "    def __call__(self, M, mode='ECB'):\n        ...\n"
                "    def initial_state(self):\n        ...\n"
                "class ShrinkingGeneratorCipher:\n"
                "    def __call__(self, M, mode='ECB'):\n        ...\n"
                "    def keystream_cipher(self):\n        ...\n"
                "    def decimating_cipher(self):\n        ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched_stream = stream.read_text(encoding="utf-8")
            patched_cipher = cipher.read_text(encoding="utf-8")
            string_type = "'sage.monoids.string_monoid_element.StringMonoidElement'"
            self.assertIn("def __call__(self, key) -> 'sage.crypto.stream_cipher.LFSRCipher':", patched_stream)
            self.assertIn(f"def encoding(self, M) -> {string_type}:", patched_stream)
            self.assertIn("def __call__(self, key) -> 'sage.crypto.stream_cipher.ShrinkingGeneratorCipher':", patched_stream)
            self.assertIn("def blum_blum_shub(length, seed=None) -> " + string_type + ":", patched_stream)
            self.assertIn(f"def __call__(self, M, mode='ECB') -> {string_type}:", patched_cipher)
            self.assertIn("def initial_state(self) -> list:", patched_cipher)
            self.assertIn("def keystream_cipher(self) -> 'sage.crypto.stream_cipher.LFSRCipher':", patched_cipher)
            self.assertIn("def decimating_cipher(self) -> 'sage.crypto.stream_cipher.LFSRCipher':", patched_cipher)
            ast.parse(patched_stream)
            ast.parse(patched_cipher)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched_stream, stream.read_text(encoding="utf-8"))
            self.assertEqual(patched_cipher, cipher.read_text(encoding="utf-8"))

    def test_ctf_public_key_and_hill_contracts_are_concrete_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            classical = root / "sage" / "crypto" / "classical.pyi"
            blum = root / "sage" / "crypto" / "public_key" / "blum_goldwasser.pyi"
            classical.parent.mkdir(parents=True)
            blum.parent.mkdir(parents=True)
            classical.write_text(
                "class HillCryptosystem:\n"
                "    def __call__(self, A):\n        ...\n"
                "    def inverse_key(self, A):\n        ...\n",
                encoding="utf-8",
            )
            blum.write_text(
                "class BlumGoldwasser:\n"
                "    def decrypt(self, C, K):\n        ...\n"
                "    def encrypt(self, P, K, seed=None):\n        ...\n"
                "    def private_key(self, p, q):\n        ...\n"
                "    def public_key(self, p, q):\n        ...\n"
                "    def random_key(self, lbound, ubound, ntries=100):\n        ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched_classical = classical.read_text(encoding="utf-8")
            patched_blum = blum.read_text(encoding="utf-8")
            self.assertIn(
                "def __call__(self, A) -> 'sage.crypto.classical_cipher.HillCipher':",
                patched_classical,
            )
            integer_type = "'sage.rings.integer.Integer'"
            self.assertIn("def decrypt(self, C, K) -> list[list[int]]:", patched_blum)
            self.assertIn(
                "def encrypt(self, P, K, seed=None) -> tuple[list[list[int]], 'sage.rings.integer.Integer']:",
                patched_blum,
            )
            self.assertIn(
                "def private_key(self, p, q) -> tuple[" + ", ".join([integer_type] * 4) + "]:",
                patched_blum,
            )
            self.assertIn("def public_key(self, p, q) -> 'sage.rings.integer.Integer':", patched_blum)
            self.assertIn(
                "def random_key(self, lbound, ubound, ntries=100) -> tuple['sage.rings.integer.Integer', tuple["
                + ", ".join([integer_type] * 4)
                + "]]:",
                patched_blum,
            )
            ast.parse(patched_classical)
            ast.parse(patched_blum)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched_classical, classical.read_text(encoding="utf-8"))
            self.assertEqual(patched_blum, blum.read_text(encoding="utf-8"))

    def test_lwe_and_lattice_contracts_preserve_ctf_output_branches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lwe = root / "sage" / "crypto" / "lwe.pyi"
            lattice = root / "sage" / "crypto" / "lattice.pyi"
            lwe.parent.mkdir(parents=True)
            lwe.write_text(
                "class UniformSampler:\n"
                "    def __call__(self):\n        ...\n"
                "class LWE:\n"
                "    def __call__(self):\n        ...\n"
                "class RingLWE:\n"
                "    def __call__(self):\n        ...\n"
                "class RingLWEConverter:\n"
                "    def __call__(self):\n        ...\n"
                "def samples(m, n, lwe, seed=None, balanced=False, **kwds):\n    ...\n"
                "def balance_sample(s, q=None):\n    ...\n",
                encoding="utf-8",
            )
            lattice.write_text(
                "def gen_lattice(type='modular', n=4, m=8, q=11, seed=None, quotient=None, dual=False, ntl=False, lattice=False):\n"
                "    ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched_lwe = lwe.read_text(encoding="utf-8")
            patched_lattice = lattice.read_text(encoding="utf-8")
            self.assertIn("def __call__(self) -> int:", patched_lwe)
            self.assertIn("def __call__(self) -> tuple:", patched_lwe)
            self.assertIn("def samples(m, n, lwe, seed=None, balanced=False, **kwds) -> list[tuple]:", patched_lwe)
            self.assertIn("def balance_sample(s, q=None) -> tuple:", patched_lwe)
            self.assertIn("def gen_lattice(type='modular'", patched_lattice)
            self.assertIn("Literal[True]", patched_lattice)
            self.assertIn("Matrix_integer_dense", patched_lattice)
            self.assertIn("ntl_mat_ZZ", patched_lattice)
            self.assertIn("FreeModule_submodule_with_basis_integer_with_category", patched_lattice)
            ast.parse(patched_lwe)
            ast.parse(patched_lattice)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched_lwe, lwe.read_text(encoding="utf-8"))
            self.assertEqual(patched_lattice, lattice.read_text(encoding="utf-8"))

    def test_boolean_function_contracts_cover_ctf_operations_and_format_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "boolean_function.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class BooleanFunction:\n"
                "    def __invert__(self):\n        ...\n"
                "    def __add__(self, other):\n        ...\n"
                "    def derivative(self, u):\n        ...\n"
                "    def __call__(self, x):\n        ...\n"
                "    def __getitem__(self, x):\n        ...\n"
                "    def __iter__(self):\n        ...\n"
                "    def truth_table(self, format='bin'):\n        ...\n"
                "    def absolute_walsh_spectrum(self):\n        ...\n"
                "    def algebraic_normal_form(self):\n        ...\n"
                "class BooleanFunctionIterator:\n"
                "    def __iter__(self):\n        ...\n"
                "    def __next__(self):\n        ...\n"
                "def random_boolean_function(n):\n    ...\n"
                "def unpickle_BooleanFunction(bool_list):\n    ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("from typing import Self", patched)
            self.assertIn("from typing import overload", patched)
            self.assertIn("from typing import overload, Literal", patched)
            self.assertIn("def __invert__(self) -> Self:", patched)
            self.assertIn("def derivative(self, u) -> Self:", patched)
            self.assertIn("def __call__(self, x) -> bool:", patched)
            self.assertIn("def __getitem__(self, x) -> bool:", patched)
            self.assertIn(
                "def __iter__(self) -> 'sage.crypto.boolean_function.BooleanFunctionIterator':",
                patched,
            )
            self.assertIn("def __next__(self) -> bool:", patched)
            self.assertIn("def absolute_walsh_spectrum(self) -> dict:", patched)
            self.assertIn(
                "def algebraic_normal_form(self) -> 'sage.rings.polynomial.pbori.pbori.BooleanPolynomial':",
                patched,
            )
            self.assertIn("def random_boolean_function(n) -> 'sage.crypto.boolean_function.BooleanFunction':", patched)
            self.assertIn("def truth_table(self, format: Literal['hex']) -> str: ...", patched)
            self.assertIn("def truth_table(self, format: Literal['bin', 'int'] = 'bin') -> tuple: ...", patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_sbox_contracts_cover_ctf_tables_metrics_and_input_branches(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "sbox.pyi"
            stub.parent.mkdir(parents=True)
            method_names = (
                "derivative(self, u)",
                "difference_distribution_table(self)",
                "maximal_difference_probability_absolute(self)",
                "maximal_difference_probability(self)",
                "linear_approximation_table(self, scale='absolute_bias')",
                "maximal_linear_bias_absolute(self)",
                "maximal_linear_bias_relative(self)",
                "boomerang_connectivity_table(self)",
                "boomerang_uniformity(self)",
                "cnf(self)",
                "differential_branch_number(self)",
                "interpolation_polynomial(self)",
                "inverse(self)",
                "linear_branch_number(self)",
                "linearity(self)",
                "min_degree(self)",
                "max_degree(self)",
                "nonlinearity(self)",
                "ring(self)",
                "autocorrelation_table(self)",
                "__iter__(self)",
                "__call__(self, X)",
                "__getitem__(self, X)",
            )
            methods = "".join(f"    def {name}:\n        ...\n" for name in method_names)
            stub.write_text("class SBox:\n" + methods, encoding="utf-8")
            constructors = root / "sage" / "crypto" / "sbox.pyi"
            constructors.write_text(
                constructors.read_text(encoding="utf-8")
                + "def feistel_construction(*args):\n    ...\n"
                + "def misty_construction(*args):\n    ...\n",
                encoding="utf-8",
            )
            factories = root / "sage" / "crypto" / "sboxes.pyi"
            factories.write_text(
                "def bracken_leander(n):\n    ...\n"
                "def carlet_tang_tang_liao(n, c=None, bf=None):\n    ...\n"
                "def gold(n, i):\n    ...\n"
                "def kasami(n, i):\n    ...\n"
                "def niho(n):\n    ...\n"
                "def welch(n):\n    ...\n"
                "def monomial_function(n, e):\n    ...\n"
                "def inversion(n):\n    ...\n"
                "def chi(n):\n    ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("from typing import Self, Iterator", patched)
            self.assertIn("from typing import Self", patched)
            self.assertIn("from typing import overload", patched)
            expected = (
                "def derivative(self, u) -> Self:",
                "def difference_distribution_table(self) -> 'sage.matrix.matrix_integer_dense.Matrix_integer_dense':",
                "def maximal_difference_probability_absolute(self) -> 'sage.rings.integer.Integer':",
                "def maximal_difference_probability(self) -> float:",
                "def linear_approximation_table(self, scale='absolute_bias') -> 'sage.matrix.matrix_rational_dense.Matrix_rational_dense':",
                "def maximal_linear_bias_absolute(self) -> 'sage.rings.rational.Rational':",
                "def maximal_linear_bias_relative(self) -> float:",
                "def boomerang_connectivity_table(self) -> 'sage.matrix.matrix_integer_dense.Matrix_integer_dense':",
                "def boomerang_uniformity(self) -> 'sage.rings.integer.Integer':",
                "def cnf(self) -> list:",
                "def interpolation_polynomial(self) -> 'sage.rings.polynomial.polynomial_zz_pex.Polynomial_ZZ_pEX':",
                "def inverse(self) -> Self:",
                "def linearity(self) -> 'sage.rings.rational.Rational':",
                "def nonlinearity(self) -> 'sage.rings.rational.Rational':",
                "def __iter__(self) -> Iterator['sage.rings.integer.Integer']:",
            )
            for declaration in expected:
                self.assertIn(declaration, patched)
            self.assertIn(
                "def __call__(self, X: int) -> 'sage.rings.integer.Integer': ...",
                patched,
            )
            self.assertIn("def __call__(self, X: list) -> list: ...", patched)
            self.assertIn(
                "def __call__(self, X: 'sage.modules.vector_mod2_dense.Vector_mod2_dense') -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense': ...",
                patched,
            )
            self.assertIn(
                "def __getitem__(self, X: int) -> 'sage.rings.integer.Integer': ...",
                patched,
            )
            constructors_text = constructors.read_text(encoding="utf-8")
            self.assertIn("def feistel_construction(*args) -> 'sage.crypto.sbox.SBox':", constructors_text)
            self.assertIn("def misty_construction(*args) -> 'sage.crypto.sbox.SBox':", constructors_text)
            factories_text = factories.read_text(encoding="utf-8")
            self.assertIn("def gold(n, i) -> 'sage.crypto.sbox.SBox':", factories_text)
            self.assertIn("def inversion(n) -> 'sage.crypto.sbox.SBox':", factories_text)
            ast.parse(patched)
            ast.parse(constructors_text)
            ast.parse(factories_text)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))
            self.assertEqual(constructors_text, constructors.read_text(encoding="utf-8"))
            self.assertEqual(factories_text, factories.read_text(encoding="utf-8"))

    def test_rijndael_gf_contracts_preserve_matrix_and_polynomial_parents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "mq" / "rijndael_gf.pyi"
            stub.parent.mkdir(parents=True)
            methods = (
                "    def __call__(self, text, key, algorithm='encrypt', format='hex'):\n        ...\n"
                "    def number_rounds(self):\n        ...\n"
                "    def _hex_to_GF(self, H, matrix=True) -> list:\n        ...\n"
                "    def _GF_to_hex(self, GF):\n        ...\n"
                "    def _bin_to_GF(self, B, matrix=True) -> list:\n        ...\n"
                "    def _GF_to_bin(self, GF) -> 'sage.monoids.string_monoid_element.StringMonoidElement':\n        ...\n"
                "    def decrypt(self, ciphertext, key, format='hex'):\n        ...\n"
                "    def _check_valid_PRmatrix(self, PRm, keyword):\n        ...\n"
                "    def expand_key(self, key):\n        ...\n"
                "    def expand_key_poly(self, row, col, round):\n        ...\n"
                "    def apply_poly(self, state, poly_constr, algorithm='encrypt', keys=None, poly_constr_attr=None):\n        ...\n"
                "    def compose(self, f, g, algorithm='encrypt', f_attr=None, g_attr=None):\n        ...\n"
                "    def _add_round_key_pc(self, row, col, algorithm='encrypt', round=0):\n        ...\n"
                "    def add_round_key(self, state, round_key):\n        ...\n"
                "    def _sub_bytes_pc(self, row, col, algorithm='encrypt', no_inversion=False):\n        ...\n"
                "    def _srd(self, el, algorithm='encrypt'):\n        ...\n"
                "    def sub_bytes(self, state, algorithm='encrypt'):\n        ...\n"
                "    def _mix_columns_pc(self, row, col, algorithm='encrypt'):\n        ...\n"
                "    def mix_columns(self, state, algorithm='encrypt'):\n        ...\n"
                "    def _shift_rows_pc(self, row, col, algorithm='encrypt'):\n        ...\n"
                "    def shift_rows(self, state, algorithm='encrypt'):\n        ...\n"
                "    def add_round_key_poly_constr(self):\n        ...\n"
                "    def sub_bytes_poly_constr(self):\n        ...\n"
                "    def mix_columns_poly_constr(self):\n        ...\n"
                "    def shift_rows_poly_constr(self):\n        ...\n"
            )
            nested = (
                "    class Round_Component_Poly_Constr:\n"
                "        def __call__(self, row, col, algorithm='encrypt', **kwargs):\n"
                "            ...\n"
            )
            stub.write_text(
                "class RijndaelGF:\n"
                + methods
                + nested,
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn('RijndaelStateT = TypeVar("RijndaelStateT")', patched)
            self.assertIn("def __call__(self, text, key, algorithm='encrypt', format='hex') -> str:", patched)
            self.assertIn("def _GF_to_hex(self, GF) -> str:", patched)
            self.assertIn("def _GF_to_bin(self, GF) -> str:", patched)
            self.assertIn("def decrypt(self, ciphertext, key, format='hex') -> str:", patched)
            self.assertIn("def expand_key(self, key) -> list['sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense']:", patched)
            self.assertIn("def _srd(self, el, algorithm='encrypt') -> 'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement':", patched)
            self.assertIn("def __call__(self, row, col, algorithm='encrypt', **kwargs) -> 'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular':", patched)
            self.assertIn("def _hex_to_GF(self, H, matrix: Literal[False]) -> list: ...", patched)
            self.assertIn("def _hex_to_GF(self, H, matrix: Literal[True] = True) -> 'sage.matrix.matrix_gf2e_dense.Matrix_gf2e_dense': ...", patched)
            self.assertIn("def _bin_to_GF(self, B, matrix: Literal[False]) -> list: ...", patched)
            self.assertIn("def apply_poly(self, state: RijndaelStateT, poly_constr, algorithm='encrypt', keys=None, poly_constr_attr=None) -> RijndaelStateT: ...", patched)
            self.assertIn("def add_round_key(self, state: RijndaelStateT, round_key: RijndaelStateT) -> RijndaelStateT: ...", patched)
            self.assertIn("def compose(self, f: 'sage.crypto.mq.rijndael_gf.RijndaelGF.Round_Component_Poly_Constr', g: 'sage.rings.polynomial.multi_polynomial_libsingular.MPolynomial_libsingular'", patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_des_permutation_contracts_use_dense_gf2_vectors(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "block_cipher" / "des.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class DES:\n"
                "    def _ip(self, block):\n"
                "        ...\n"
                "class DES_KS:\n"
                "    def _left_shift(self, half, i):\n"
                "        ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            vector = "'sage.modules.vector_mod2_dense.Vector_mod2_dense'"
            self.assertIn(f"def _ip(self, block) -> {vector}:", patched)
            self.assertIn(f"def _left_shift(self, half, i) -> {vector}:", patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_multiline_output_sections_and_wrapped_class_roles_are_typed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            class_stub = root / "sage" / "graphs" / "digraph.pyi"
            user_stub = root / "sage" / "graphs" / "factory.pyi"
            class_stub.parent.mkdir(parents=True)
            class_stub.write_text("class DiGraph: ...\n", encoding="utf-8")
            user_stub.write_text(
                "def include_dirs():\n"
                "    \"\"\"\n"
                "    OUTPUT:\n"
                "\n"
                "    a list of include directories.\n"
                "\n"
                "    EXAMPLES::\n"
                "        ...\n"
                "    \"\"\"\n"
                "\n"
                "def make_graph():\n"
                "    \"\"\"OUTPUT: a :class:`digraph\n"
                "    <sage.graphs.digraph.DiGraph>`.\"\"\"\n"
                "def graph_tuple():\n"
                "    \"\"\"OUTPUT: :class:`tuple` of :class:`digraph`.\"\"\"\n"
                "def increasing_tuple():\n"
                "    \"\"\"OUTPUT: increasing :class:`tuple` of integers.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = user_stub.read_text(encoding="utf-8")
            self.assertIn("def include_dirs() -> list:", patched)
            self.assertIn("def make_graph() -> 'sage.graphs.digraph.DiGraph':", patched)
            self.assertIn("def graph_tuple() -> tuple:", patched)
            self.assertIn("def increasing_tuple() -> tuple:", patched)

    def test_atomic_doc_output_prefixes_and_self_copy_are_typed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "outputs.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Value:\n"
                "    def check(self):\n"
                "        \"\"\"OUTPUT: boolean; whether the value is valid\"\"\"\n"
                "    def clone(self):\n"
                "        \"\"\"OUTPUT: an exact copy of ``self``\"\"\"\n"
                "    def maybe(self):\n"
                "        \"\"\"OUTPUT: boolean or ``none``\"\"\"\n"
                "\n"
                "def render(value):\n"
                "    \"\"\"OUTPUT: string representation\"\"\"\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("from typing import Self", patched)
            self.assertIn("def check(self) -> bool:", patched)
            self.assertIn("def clone(self) -> Self:", patched)
            self.assertIn("def render(value) -> str:", patched)
            self.assertIn("def maybe(self):", patched)

    def test_documented_atomic_numeric_and_container_forms_stay_fail_closed_on_unions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "outputs.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def rational_value():\n"
                "    \"\"\"OUTPUT: a rational number > 0\"\"\"\n"
                "def integer_value():\n"
                "    \"\"\"OUTPUT: integer; the degree\"\"\"\n"
                "def list_value():\n"
                "    \"\"\"OUTPUT: list of integers\"\"\"\n"
                "def mixed_value():\n"
                "    \"\"\"OUTPUT: list of integers or none\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def rational_value() -> 'sage.rings.rational.Rational':", patched)
            self.assertIn("def integer_value() -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def list_value() -> list:", patched)
            self.assertIn("def mixed_value():", patched)

    def test_inline_code_result_words_and_rich_comparison_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "outputs.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Value:\n"
                "    def is_valid(self):\n"
                "        \"\"\"OUTPUT: ``true`` if valid and ``false`` otherwise\"\"\"\n"
                "    def __eq__(self, other):\n"
                "        \"\"\"OUTPUT: ``true`` if equal and ``false`` otherwise\"\"\"\n"
                "def walk():\n"
                "    \"\"\"OUTPUT: ``none``. (this is not an iterator.)\"\"\"\n"
                "def show():\n"
                "    \"\"\"OUTPUT: this method does not return anything.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def is_valid(self) -> bool:", patched)
            self.assertIn("def __eq__(self, other):", patched)
            self.assertIn("def walk() -> None:", patched)
            self.assertIn("def show() -> None:", patched)

    def test_unique_named_output_classes_and_pairs_are_typed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "outputs.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def asymptotic():\n"
                "    \"\"\"OUTPUT: an asymptotic expansion for f\"\"\"\n"
                "def symbolic():\n"
                "    \"\"\"OUTPUT: a symbolic expression\"\"\"\n"
                "def series():\n"
                "    \"\"\"OUTPUT: a new power series\"\"\"\n"
                "def pair_value():\n"
                "    \"\"\"OUTPUT: a pair (value, error)\"\"\"\n"
                "def maybe_series():\n"
                "    \"\"\"OUTPUT: a power series or none\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn(
                "def asymptotic() -> 'sage.rings.asymptotic.asymptotic_ring.AsymptoticExpansion':",
                patched,
            )
            self.assertIn("def symbolic() -> 'sage.symbolic.expression.Expression':", patched)
            self.assertIn(
                "def series() -> 'sage.rings.power_series_ring_element.PowerSeries':",
                patched,
            )
            self.assertIn("def pair_value() -> tuple:", patched)
            self.assertIn("def maybe_series():", patched)

    def test_return_summary_atomic_contracts_and_conditional_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "summary.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Value:\n"
                "    def __eq__(self, other):\n"
                "        \"\"\"Return a boolean indicating equality.\"\"\"\n"
                "def text():\n"
                "    \"\"\"Return a string representation of the value.\"\"\"\n"
                "def values():\n"
                "    \"\"\"Return the list of values.\"\"\"\n"
                "def pair_value():\n"
                "    \"\"\"Returns a pair of values.\"\"\"\n"
                "def maybe_values():\n"
                "    \"\"\"Return a list or ``none`` when empty.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def text() -> str:", patched)
            self.assertIn("def values() -> list:", patched)
            self.assertIn("def pair_value() -> tuple:", patched)
            self.assertIn("def __eq__(self, other):", patched)
            self.assertIn("def maybe_values():", patched)

    def test_return_summary_unique_class_role_is_resolved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            class_stub = root / "sage" / "graphs" / "digraph.pyi"
            user_stub = root / "sage" / "graphs" / "factory.pyi"
            class_stub.parent.mkdir(parents=True)
            class_stub.write_text("class DiGraph: ...\n", encoding="utf-8")
            user_stub.write_text(
                "def make_graph():\n"
                "    \"\"\"Return the :class:`digraph` associated to the value.\"\"\"\n"
                "def maybe_graph():\n"
                "    \"\"\"Return the :class:`digraph` or ``none``.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = user_stub.read_text(encoding="utf-8")
            self.assertIn("def make_graph() -> 'sage.graphs.digraph.DiGraph':", patched)
            self.assertIn("def maybe_graph():", patched)

    def test_summary_class_roles_and_predicates_use_atomic_contracts(self):
        """Summary-only Sage docs should not remain UNKNOWN when explicit."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            class_stub = root / "sage" / "combinat" / "pbw.pyi"
            user_stub = root / "sage" / "combinat" / "factory.pyi"
            class_stub.parent.mkdir(parents=True)
            class_stub.write_text("class PBWDatum: ...\nclass Expression: ...\n", encoding="utf-8")
            user_stub.write_text(
                "def make_pbw():\n"
                "    \"\"\"Return a new :class:`PBWDatum` equivalent to ``self``.\"\"\"\n"
                "def check_value(x):\n"
                "    \"\"\"Check whether ``x`` is valid or reducible.\n\n"
                "    The implementation may use one of several algorithms or\n"
                "    return early when the value is cached.\n"
                "    \"\"\"\n"
                "def generate_code(tree):\n"
                "    \"\"\"Generate code from an :class:`Expression` tree.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = user_stub.read_text(encoding="utf-8")
            self.assertIn("def make_pbw() -> 'sage.combinat.pbw.PBWDatum':", patched)
            self.assertIn("def check_value(x) -> bool:", patched)
            # The class role names an input here, not the generated string.
            self.assertIn("def generate_code(tree):", patched)

    def test_operator_summary_preserves_concrete_receiver_with_self(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "rings" / "element.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Element:\n"
                "    def __neg__(self):\n"
                "        \"\"\"Return the negative of this element.\"\"\"\n"
                "    def _add_(self, other):\n"
                "        \"\"\"Return the sum of this element and ``other``.\"\"\"\n"
                "    def inverse(self):\n"
                "        \"\"\"Return the inverse of ``self``.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def __neg__(self) -> Self:", patched)
            self.assertIn("def _add_(self, other) -> Self:", patched)
            # Inversion may change parent/type and remains fail-closed.
            self.assertIn("def inverse(self):", patched)

    def test_numeric_element_summaries_preserve_the_concrete_receiver(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "numeric.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class ComplexDoubleElement:\n"
                "    def cos(self):\n"
                "        \"\"\"This function returns the complex cosine of the complex number z.\"\"\"\n"
                "    def magnitude(self):\n"
                "        \"\"\"This function returns the magnitude of the complex number z.\"\"\"\n"
                "\n"
                "class RealNumber:\n"
                "    def log(self):\n"
                "        \"\"\"Return the logarithm of self to the given base.\"\"\"\n"
                "\n"
                "class ComplexBall:\n"
                "    def arg(self):\n"
                "        \"\"\"Return the argument of this complex ball.\"\"\"\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def cos(self) -> Self:", patched)
            self.assertIn("def log(self) -> Self:", patched)
            self.assertIn("def magnitude(self):", patched)
            self.assertIn("def arg(self):", patched)

    def test_sage_test_hooks_return_none_even_without_docstrings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "tests.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Value:\n"
                "    def _test_invariant(self):\n"
                "        pass\n"
                "    def _test_optional_payload(self):\n"
                "        \"\"\"Test helper; raises on failure.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def _test_invariant(self) -> None:", patched)
            self.assertIn("def _test_optional_payload(self) -> None:", patched)

    def test_source_scalar_and_chinese_object_contracts_are_typed(self):
        """Documented scalar invariants reduce UNKNOWN without guessing unions."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            class_stub = root / "sage" / "plot" / "graphics.pyi"
            window_stub = root / "sage" / "matrix" / "matrix_window.pyi"
            user_stub = root / "sage" / "arith" / "contracts.pyi"
            class_stub.parent.mkdir(parents=True)
            window_stub.parent.mkdir(parents=True)
            user_stub.parent.mkdir(parents=True)
            class_stub.write_text("class Graphics: ...\n", encoding="utf-8")
            window_stub.write_text("class MatrixWindow: ...\n", encoding="utf-8")
            user_stub.write_text(
                "def bernoulli_value(n):\n"
                "    \"\"\"Return the `n`-th Bernoulli number, as a rational number.\"\"\"\n"
                "def prime_power(n):\n"
                "    \"\"\"Return the smallest prime power greater than n.\"\"\"\n"
                "def hilbert(a, b, p):\n"
                "    \"\"\"OUTPUT: integer (0, -1, or 1)\"\"\"\n"
                "def bounded_integer(n):\n"
                "    \"\"\"OUTPUT: nonnegative integer or -1\"\"\"\n"
                "def prime_divisor(n):\n"
                "    \"\"\"OUTPUT: a prime p that divides n, or n if none exists\"\"\"\n"
                "class Matrix:\n"
                "    def density(self):\n"
                "        \"\"\"返回矩阵非零条目所占的比例。\"\"\"\n"
                "    def transpose(self):\n"
                "        \"\"\"返回矩阵的转置。\"\"\"\n"
                "    def window(self):\n"
                "        \"\"\"返回 MatrixWindow 对象。\"\"\"\n"
                "    def plot(self):\n"
                "        \"\"\"绘制图像并返回 Graphics 对象。\"\"\"\n"
                "    def maybe(self):\n"
                "        \"\"\"OUTPUT: integer or tuple\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = user_stub.read_text(encoding="utf-8")
            self.assertIn("def bernoulli_value(n) -> 'sage.rings.rational.Rational':", patched)
            self.assertIn("def prime_power(n) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def hilbert(a, b, p) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def bounded_integer(n) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def prime_divisor(n) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def density(self) -> 'sage.rings.rational.Rational':", patched)
            self.assertIn("def transpose(self) -> Self:", patched)
            self.assertIn("def plot(self) -> 'sage.plot.graphics.Graphics':", patched)
            self.assertIn("def window(self) -> 'sage.matrix.matrix_window.MatrixWindow':", patched)
            self.assertIn("def maybe(self):", patched)

    def test_ctf_crypto_utility_contracts_keep_runtime_scalar_and_container_types(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "crypto" / "util.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def ascii_integer(block):\n"
                "    \"\"\"OUTPUT: the ASCII integer corresponding to the 8-bit block ``B``\"\"\"\n"
                "def ascii_to_bin(text):\n"
                "    \"\"\"OUTPUT: the binary representation of ``A``\"\"\"\n"
                "def bin_to_ascii(bits):\n"
                "    \"\"\"OUTPUT: the ASCII string corresponding to ``B``\"\"\"\n"
                "def least_significant_bits(n, k):\n"
                "    \"\"\"Return the ``k`` least significant bits of ``n``.\"\"\"\n"
                "def random_blum_prime(lower, upper):\n"
                "    \"\"\"A random Blum prime within the specified bounds.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def ascii_integer(block) -> int:", patched)
            self.assertIn(
                "def ascii_to_bin(text) -> 'sage.monoids.string_monoid_element.StringMonoidElement':",
                patched,
            )
            self.assertIn("def bin_to_ascii(bits) -> str:", patched)
            self.assertIn("def least_significant_bits(n, k) -> list:", patched)
            self.assertIn(
                "def random_blum_prime(lower, upper) -> 'sage.rings.integer.Integer':",
                patched,
            )

    def test_ctf_arithmetic_and_unique_output_contracts_are_typed(self):
        """Structured Sage outputs expose their stable outer runtime type."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph_stub = root / "sage" / "graphs" / "bipartite_graph.pyi"
            util_stub = root / "sage" / "arith" / "misc.pyi"
            graph_stub.parent.mkdir(parents=True)
            util_stub.parent.mkdir(parents=True)
            graph_stub.write_text("class BipartiteGraph: ...\n", encoding="utf-8")
            util_stub.write_text(
                "def hilbert_conductor(a, b):\n"
                "    \"\"\"OUTPUT: squarefree positive integer\"\"\"\n"
                "def prime_powers(start, stop=None):\n"
                "    \"\"\"OUTPUT: The set of all prime powers.\"\"\"\n"
                "def rational_reconstruction(a, m):\n"
                "    \"\"\"This function tries to compute x/y, where x/y is a rational number.\n"
                "    OUTPUT: Numerator and denominator n, d of the unique rational number.\"\"\"\n"
                "def mqrr(u, m, bound):\n"
                "    \"\"\"OUTPUT: Either integers n,d satisfying the bound, or ``None``.\"\"\"\n"
                "def xlcm(m, n):\n"
                "    \"\"\"Extended lcm function: given two positive integers m,n, returns\n"
                "    a triple (l,m_1,n_1).\"\"\"\n"
                "class Euler_Phi:\n"
                "    def __call__(self, n):\n"
                "        \"\"\"\"\"\"\n"
                "    def plot(self, n):\n"
                "        \"\"\"\"\"\"\n"
                "class Moebius:\n"
                "    def __call__(self, n):\n"
                "        \"\"\"\"\"\"\n"
                "    def range(self, n):\n"
                "        \"\"\"\"\"\"\n"
                "class Sigma:\n"
                "    def __call__(self, n):\n"
                "        \"\"\"\"\"\"\n"
                "class Matrix:\n"
                "    def graph(self):\n"
                "        \"\"\"OUTPUT: Any -- BipartiteGraph 二部图对象\"\"\"\n"
                "    def window(self):\n"
                "        \"\"\"OUTPUT: Any -- MatrixWindow 对象\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = util_stub.read_text(encoding="utf-8")
            self.assertIn("def hilbert_conductor(a, b) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def prime_powers(start, stop=None) -> list:", patched)
            self.assertIn(
                "def rational_reconstruction(a, m) -> 'sage.rings.rational.Rational':",
                patched,
            )
            self.assertIn("def mqrr(u, m, bound) -> tuple | None:", patched)
            self.assertIn("def xlcm(m, n) -> tuple:", patched)
            self.assertIn("def __call__(self, n) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def plot(self, n) -> 'sage.plot.graphics.Graphics':", patched)
            self.assertIn("def range(self, n) -> list:", patched)
            self.assertIn("def graph(self) -> 'sage.graphs.bipartite_graph.BipartiteGraph':", patched)
            # MatrixWindow exists in more than one source module, so its
            # Chinese object marker remains fail-closed rather than choosing
            # an arbitrary implementation.
            self.assertIn("def window(self):", patched)

    def test_stable_container_outputs_are_typed_without_element_guesses(self):
        """Outer containers are exact even when their elements are dynamic."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "outputs.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def ordered_pairs(values):\n"
                "    \"\"\"Return a sorted tuple of values.\"\"\"\n"
                "def copied_values(values):\n"
                "    \"\"\"Return a new list of values.\"\"\"\n"
                "def gcd_error_count(values):\n"
                "    \"\"\"Return the number of errors as an integer.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def ordered_pairs(values) -> tuple:", patched)
            self.assertIn("def copied_values(values) -> list:", patched)
            self.assertIn(
                "def gcd_error_count(values) -> 'sage.rings.integer.Integer':",
                patched,
            )

    def test_complex_display_helpers_have_runtime_container_contracts(self):
        """The arithmetic display helpers always return tuple/list containers."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "arith" / "misc.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def _key_complex_for_display(a):\n"
                "    \"\"\"Return a key.\"\"\"\n\n"
                "def sort_complex_numbers_for_display(nums):\n"
                "    \"\"\"Return a sorted list.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def _key_complex_for_display(a) -> tuple:", patched)
            self.assertIn(
                "def sort_complex_numbers_for_display(nums) -> list:",
                patched,
            )

    def test_integer_source_operations_keep_integer_or_rational_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "rings" / "integer.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Integer:\n"
                "    def __abs__(self):\n"
                "        \"\"\"Compute ``|self|``.\"\"\"\n"
                "    def __and__(self, other):\n"
                "        \"\"\"Return the bitwise and two integers.\"\"\"\n"
                "    def __invert__(self):\n"
                "        \"\"\"Return the multiplicative inverse of self, as a rational number.\"\"\"\n"
                "    def _floordiv_(self, other):\n"
                "        \"\"\"Compute the whole part of x/y.\"\"\"\n"
                "    def unknown(self):\n"
                "        \"\"\"Return a value depending on the parent.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def __abs__(self) -> Self:", patched)
            self.assertIn("def __and__(self, other) -> Self:", patched)
            self.assertIn("def __invert__(self) -> 'sage.rings.rational.Rational':", patched)
            self.assertIn("def _floordiv_(self, other) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def unknown(self):", patched)

    def test_integer_runtime_verified_special_methods_are_concrete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "rings" / "integer.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "class Integer:\n"
                "    def __pos__(self):\n"
                "        \"\"\"\"\"\"\n"
                "    def __copy__(self):\n"
                "        \"\"\"\"\"\"\n"
                "    def __deepcopy__(self, memo):\n"
                "        \"\"\"\"\"\"\n"
                "    def __truediv__(self, other):\n"
                "        \"\"\"\"\"\"\n"
                "    def _div_(self, other):\n"
                "        \"\"\"\"\"\"\n"
                "    def _pow_(self, other):\n"
                "        \"\"\"\"\"\"\n"
                "    def _rpy_(self):\n"
                "        \"\"\"\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def __pos__(self) -> Self:", patched)
            self.assertIn("def __copy__(self) -> Self:", patched)
            self.assertIn("def __deepcopy__(self, memo) -> Self:", patched)
            self.assertIn("def __truediv__(self, other) -> 'sage.rings.rational.Rational':", patched)
            self.assertIn("def _div_(self, other) -> 'sage.rings.rational.Rational':", patched)
            self.assertIn("def _pow_(self, other) -> Self:", patched)
            self.assertIn("def _rpy_(self) -> int:", patched)

    def test_chinese_return_section_type_prefixes_are_typed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "matrix.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def determinant():\n"
                "    \"\"\"\n"
                "    返回:\n"
                "    Integer -- determinant value\n"
                "    \"\"\"\n"
                "def rows():\n"
                "    \"\"\"\n"
                "    返回值：\n"
                "    list[Integer] -- row values\n"
                "    \"\"\"\n"
                "def ambiguous():\n"
                "    \"\"\"\n"
                "    返回:\n"
                "    bool or list -- depends on the flag\n"
                "    \"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def determinant() -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def rows() -> list:", patched)
            self.assertIn("def ambiguous():", patched)

    def test_predicate_summary_is_boolean_only_without_alternate_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "predicates.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def is_squarefree(n):\n"
                "    \"\"\"Test whether n is square free.\"\"\"\n\n"
                "def is_power(n, get_data=False):\n"
                "    \"\"\"Test whether n is a power. With get_data return a pair.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def is_squarefree(n) -> bool:", patched)
            self.assertIn("def is_power(n, get_data=False):", patched)

    def test_literal_flag_contracts_keep_predicate_and_pair_branches_separate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "arith" / "misc.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def is_prime_power(n, get_data=False):\n"
                "    \"\"\"Test whether n is a prime power.\"\"\"\n"
                "def is_pseudoprime_power(n, get_data=False):\n"
                "    \"\"\"Test whether n is a pseudoprime power.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("from typing import overload, Literal", patched)
            self.assertIn(
                "def is_prime_power(n, get_data: Literal[False] = False) -> bool: ...",
                patched,
            )
            self.assertIn(
                "def is_prime_power(n, get_data: Literal[True]) -> tuple: ...",
                patched,
            )
            self.assertIn(
                "def is_pseudoprime_power(n, get_data: Literal[False] = False) -> bool: ...",
                patched,
            )

    def test_unique_sphinx_class_output_resolves_to_canonical_source_class(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            class_stub = root / "sage" / "graphs" / "digraph.pyi"
            user_stub = root / "sage" / "graphs" / "factory.pyi"
            class_stub.parent.mkdir(parents=True)
            class_stub.write_text("class DiGraph: ...\n", encoding="utf-8")
            user_stub.write_text(
                "def make_graph():\n"
                "    \"\"\"OUTPUT: a :class:`digraph`\"\"\"\n\n"
                "def ambiguous():\n"
                "    \"\"\"OUTPUT: a :class:`digraph` or ``none``\"\"\"\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            patched = user_stub.read_text(encoding="utf-8")
            self.assertIn("def make_graph() -> 'sage.graphs.digraph.DiGraph':", patched)
            self.assertIn("def ambiguous():", patched)

    def test_unique_plain_class_output_uses_source_index_and_generic_families_stay_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            classes = root / "sage" / "combinat"
            classes.mkdir(parents=True)
            (classes / "finite_state_machine.pyi").write_text(
                "class FiniteStateMachine: ...\n"
                "class Automaton: ...\n"
                "class Transducer: ...\n",
                encoding="utf-8",
            )
            (classes / "set_partition.pyi").write_text("class SetPartition: ...\n", encoding="utf-8")
            factory = root / "sage" / "combinat" / "factory.pyi"
            factory.write_text(
                "def fsm():\n"
                "    \"\"\"OUTPUT: a new finite state machine for the input.\"\"\"\n"
                "def automaton():\n"
                "    \"\"\"Return an automaton associated with the input.\"\"\"\n"
                "def partition():\n"
                "    \"\"\"OUTPUT: a set partition.\"\"\"\n"
                "def matrix():\n"
                "    \"\"\"OUTPUT: a matrix.\"\"\"\n"
                "def image():\n"
                "    \"\"\"OUTPUT: the image of the element.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = factory.read_text(encoding="utf-8")
            self.assertIn(
                "def fsm() -> 'sage.combinat.finite_state_machine.FiniteStateMachine':",
                patched,
            )
            # A single generic noun is deliberately not resolved merely
            # because one stub happens to be named Automaton.
            self.assertIn("def automaton():", patched)
            self.assertIn("def partition() -> 'sage.combinat.set_partition.SetPartition':", patched)
            self.assertIn("def matrix():", patched)
            self.assertIn("def image():", patched)

    def test_return_summary_predicates_and_latex_representation_are_atomic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "predicates.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def known(value):\n"
                "    \"\"\"Return whether value is known.\"\"\"\n"
                "def copied(value):\n"
                "    \"\"\"Return a copy of ``self``.\"\"\"\n"
                "def latex(value):\n"
                "    \"\"\"Return a LaTeX representation of value.\"\"\"\n"
                "def latex_macro(value):\n"
                "    \"\"\"Return a `\\LaTeX` representation of value.\"\"\"\n"
                "def known_true(value):\n"
                "    \"\"\"Return ``True`` if value is known.\"\"\"\n"
                "def no_value(value):\n"
                "    \"\"\"Return ``None``.\"\"\"\n"
                "def unicode_art(value):\n"
                "    \"\"\"Return a unicode art representation of value.\"\"\"\n"
                "def string_repr(value):\n"
                "    \"\"\"String representation of value.\"\"\"\n"
                "def __eq__(value, other):\n"
                "    \"\"\"Return whether value equals other.\"\"\"\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [sys.executable, str(PATCHER), "--stub-root", str(root)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def known(value) -> bool:", patched)
            self.assertIn("def copied(value) -> Self:", patched)
            self.assertIn("def latex(value) -> str:", patched)
            self.assertIn("def latex_macro(value) -> str:", patched)
            self.assertIn("def known_true(value) -> bool:", patched)
            self.assertIn("def no_value(value) -> None:", patched)
            self.assertIn("def unicode_art(value) -> 'sage.typeset.unicode_art.UnicodeArt':", patched)
            self.assertIn("def string_repr(value) -> str:", patched)
            # A method named like a rich comparison remains fail-closed even
            # when its prose is phrased as a predicate.
            self.assertIn("def __eq__(value, other):", patched)

    def test_gcd_typevar_contract_is_indexed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "arith" / "misc.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "\"\"\"Arithmetic helpers\"\"\"\n"
                "def gcd(a, b=None, **kwargs): ...\n"
                "def binomial(x, m, **kwds): ...\n"
                "def falling_factorial(x, a): ...\n"
                "def rising_factorial(x, a): ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def gcd(a: GcdT, b: GcdT, **kwargs) -> GcdT: ...", patched)
            self.assertTrue(patched.startswith('"""Arithmetic helpers"""\nfrom typing import TypeVar\n'))
            self.assertIn("GcdT = TypeVar(\"GcdT\")", patched)
            self.assertIn("BinomialT = TypeVar(\"BinomialT\")", patched)
            self.assertIn("FallingFactorialT = TypeVar(\"FallingFactorialT\")", patched)
            self.assertIn("RisingFactorialT = TypeVar(\"RisingFactorialT\")", patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))
            index_path = root / "index.json"
            indexed = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--source-root",
                    str(root),
                    "--source-locator",
                    "fixture",
                    "--sage-version",
                    "10.9",
                    "--python-version",
                    "3.13",
                    "--output",
                    str(index_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(indexed.returncode, 0, indexed.stderr)
            entries = json.loads(index_path.read_text(encoding="utf-8"))["entries"]
            gcd = next(entry for entry in entries if entry["qualifiedName"] == "sage.arith.misc.gcd")
            signature = gcd["signatures"][0]
            self.assertEqual("GcdT", signature["parameters"][0]["type"]["expression"])
            self.assertEqual("GcdT", signature["returnType"]["expression"])
            self.assertEqual("GcdT", signature["typeParameters"][0]["name"])
            for name, type_parameter in (
                ("sage.arith.misc.binomial", "BinomialT"),
                ("sage.arith.misc.falling_factorial", "FallingFactorialT"),
                ("sage.arith.misc.rising_factorial", "RisingFactorialT"),
            ):
                entry = next(item for item in entries if item["qualifiedName"] == name)
                self.assertEqual(type_parameter, entry["signatures"][0]["returnType"]["expression"])

    def test_ctf_arithmetic_helpers_have_scalar_iterator_and_parent_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "arith" / "misc.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def __GCD_sequence(v, **kwargs):\n    ...\n"
                "def get_gcd(order):\n    ...\n"
                "def get_inverse_mod(order):\n    ...\n"
                "def primes(start=2, stop=None, proof=None):\n    ...\n"
                "def smooth_part(x, base):\n    ...\n"
                "def valuation(m, *args, **kwds):\n    ...\n"
                "def continuant(v, n=None):\n    ...\n"
                "def gauss_sum(char_value, finite_field):\n    ...\n"
                "def radical(n, *args, **kwds):\n    ...\n"
                "def coprime_part(x, base):\n    ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("from typing import TypeVar", patched)
            self.assertIn("from typing import Iterator, Callable", patched)
            self.assertIn("def __GCD_sequence(v, **kwargs) -> GcdT:", patched)
            self.assertIn("def get_gcd(order) -> Callable[..., 'sage.rings.integer.Integer']:", patched)
            self.assertIn("def get_inverse_mod(order) -> Callable[..., 'sage.rings.integer.Integer']:", patched)
            self.assertIn("def primes(start=2, stop=None, proof=None) -> Iterator['sage.rings.integer.Integer']:", patched)
            self.assertIn("def smooth_part(x, base) -> 'sage.structure.factorization.Factorization':", patched)
            self.assertIn("def valuation(m, *args, **kwds) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def continuant(v: list[ContinuantT], n=None) -> ContinuantT: ...", patched)
            self.assertIn("def gauss_sum(char_value: GaussSumT, finite_field) -> GaussSumT: ...", patched)
            self.assertIn("def radical(n: RadicalT, *args, **kwds) -> RadicalT: ...", patched)
            self.assertIn("def coprime_part(x: CoprimePartT, base) -> CoprimePartT: ...", patched)
            ast.parse(patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_ctf_protocol_and_key_schedule_contracts_are_concrete(self):
        """Crypto protocol methods expose their Python/runtime result types."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {
                "sage/crypto/block_cipher/des.pyi": (
                    "class DES:\n    def __eq__(self, other): ...\n"
                    "class DES_KS:\n    def __eq__(self, other): ...\n    def __iter__(self): ...\n"
                ),
                "sage/crypto/block_cipher/present.pyi": (
                    "class PRESENT:\n    def __eq__(self, other): ...\n"
                    "class PRESENT_KS:\n    def __eq__(self, other): ...\n    def __iter__(self): ...\n"
                ),
                "sage/crypto/block_cipher/miniaes.pyi": "class MiniAES:\n    def __eq__(self, other): ...\n",
                "sage/crypto/block_cipher/sdes.pyi": "class SimplifiedDES:\n    def __eq__(self, other): ...\n",
                "sage/crypto/boolean_function.pyi": "class BooleanFunction:\n    def __setitem__(self, i, y): ...\n",
                "sage/crypto/cipher.pyi": "class Cipher:\n    def __eq__(self, other): ...\n",
                "sage/crypto/classical_cipher.pyi": (
                    "class AffineCipher:\n    def __eq__(self, other): ...\n"
                    "class HillCipher:\n    def __eq__(self, other): ...\n"
                    "class ShiftCipher:\n    def __eq__(self, other): ...\n"
                    "class SubstitutionCipher:\n    def __eq__(self, other): ...\n"
                    "class TranspositionCipher:\n    def __eq__(self, other): ...\n"
                    "class VigenereCipher:\n    def __eq__(self, other): ...\n"
                ),
                "sage/crypto/cryptosystem.pyi": (
                    "class Cryptosystem:\n    def __eq__(self, other): ...\n    def period(self): ...\n"
                    "class SymmetricKeyCryptosystem:\n    def alphabet_size(self): ...\n"
                ),
                "sage/crypto/public_key/blum_goldwasser.pyi": "class BlumGoldwasser:\n    def __eq__(self, other): ...\n",
                "sage/crypto/sbox.pyi": (
                    "class SBox:\n    def __eq__(self, other): ...\n    def __ne__(self, other): ...\n"
                ),
                "sage/crypto/stream.pyi": "class LFSRCryptosystem:\n    def __eq__(self, other): ...\n",
                "sage/crypto/mq/sr.pyi": (
                    "class SR_generic:\n    def __eq__(self, other): ...\n    def __ne__(self, other): ...\n"
                ),
            }
            for relative, content in fixtures.items():
                stub = root / relative
                stub.parent.mkdir(parents=True, exist_ok=True)
                # Curated insertion is intentionally documentation-driven;
                # give each minimal fixture the same docstring shape as the
                # real Sage stubs rather than relying on a bare ellipsis.
                stub.write_text(
                    content.replace(": ...", ":\n        \"\"\"Return the documented value.\"\"\""),
                    encoding="utf-8",
                )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            expected = {
                "sage/crypto/block_cipher/des.pyi": (
                    "def __eq__(self, other) -> bool:",
                    "def __iter__(self) -> Iterator['sage.rings.integer.Integer']:",
                ),
                "sage/crypto/block_cipher/present.pyi": (
                    "def __eq__(self, other) -> bool:",
                    "def __iter__(self) -> Iterator['sage.rings.integer.Integer']:",
                ),
                "sage/crypto/boolean_function.pyi": ("def __setitem__(self, i, y) -> None:",),
                "sage/crypto/cryptosystem.pyi": (
                    "def period(self) -> 'sage.rings.integer.Integer':",
                    "def alphabet_size(self) -> int:",
                ),
            }
            for relative, snippets in expected.items():
                patched = (root / relative).read_text(encoding="utf-8")
                for snippet in snippets:
                    self.assertIn(snippet, patched)
            first_contents = {
                relative: (root / relative).read_text(encoding="utf-8")
                for relative in fixtures
            }
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            for relative in fixtures:
                stub = root / relative
                self.assertEqual(first_contents[relative], stub.read_text(encoding="utf-8"))

    def test_elliptic_cardinality_helpers_return_sage_integers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "schemes" / "elliptic_curves" / "cardinality.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "def cardinality_exhaustive(self):\n    \"\"\"Count points.\"\"\"\n"
                "def cardinality_bsgs(self, verbose=False):\n    \"\"\"Count points.\"\"\"\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def cardinality_exhaustive(self) -> 'sage.rings.integer.Integer':", patched)
            self.assertIn("def cardinality_bsgs(self, verbose=False) -> 'sage.rings.integer.Integer':", patched)

    def test_ctf_matrix_backends_keep_concrete_parent_and_flag_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {
                "sage/matrix/matrix_modn_sparse.pyi": (
                    "class Matrix_modn_sparse:\n"
                    "    def determinant(self): ...\n    def rank(self): ...\n"
                    "    def matrix_from_rows(self, rows): ...\n    def swap_rows(self, i, j): ...\n"
                    "    def transpose(self): ...\n    def density(self, approx=False): ...\n"
                ),
                "sage/matrix/matrix_mod2_dense.pyi": (
                    "class Matrix_mod2_dense:\n"
                    "    def determinant(self): ...\n    def rank(self): ...\n"
                    "    def row(self, i): ...\n    def echelonize(self): ...\n"
                    "    def transpose(self): ...\n    def density(self, approx=False): ...\n"
                ),
                "sage/matrix/matrix_gf2e_dense.pyi": (
                    "class Matrix_gf2e_dense:\n"
                    "    def determinant(self): ...\n    def rank(self): ...\n"
                    "    def slice(self): ...\n    def cling(self, *C): ...\n"
                    "    def transpose(self): ...\n    def density(self, approx=False): ...\n"
                ),
                "sage/matrix/matrix_integer_dense.pyi": (
                    "class Matrix_integer_dense:\n"
                    "    def _add_(self, right): ...\n    def _sub_(self, right): ...\n"
                    "    def __neg__(self): ...\n    def __pow__(self, n, dummy): ...\n    def __invert__(self): ...\n"
                    "    def inverse_of_unit(self): ...\n    def augment(self, right): ...\n"
                    "    def echelon_form(self): ...\n    def transpose(self): ...\n"
                    "    def antitranspose(self): ...\n    def determinant(self): ...\n"
                    "    def charpoly(self): ...\n    def minpoly(self): ...\n"
                    "    def frobenius_form(self): ...\n    def symplectic_form(self): ...\n    def saturation(self): ...\n"
                    "    def _ntl_(self): ...\n    def _magma_init_(self, magma): ...\n    def _richcmp_(self, right, op): ...\n"
                    "    def decomposition(self, **kwds): ...\n    def row(self, i): ...\n"
                    "    def column(self, i): ...\n    def rank(self) -> 'sage.rings.integer.Integer': ...\n"
                    "    def smith_form(self, transformation=True, integral=None): ...\n"
                ),
                "sage/matrix/matrix_rational_dense.pyi": (
                    "class Matrix_rational_dense:\n"
                    "    def _add_(self, right): ...\n    def _sub_(self, right): ...\n"
                    "    def __neg__(self): ...\n    def __invert__(self): ...\n"
                    "    def inverse(self): ...\n    def augment(self, right): ...\n"
                    "    def echelon_form(self): ...\n    def transpose(self): ...\n"
                    "    def antitranspose(self): ...\n    def determinant(self): ...\n"
                    "    def charpoly(self): ...\n    def minpoly(self): ...\n"
                    "    def rank(self): ...\n    def row(self, i): ...\n"
                    "    def column(self, i): ...\n    def prod_of_row_sums(self, cols): ...\n"
                    "    def _magma_init_(self, magma): ...\n    def _richcmp_(self, right, op): ...\n"
                    "    def decomposition(self, is_diagonalizable=False, dual=False, algorithm=None, height_guess=None, proof=None): ...\n"
                    "    def smith_form(self, transformation=True, integral=None): ...\n"
                ),
            }
            for relative, content in fixtures.items():
                stub = root / relative
                stub.parent.mkdir(parents=True, exist_ok=True)
                stub.write_text(
                    content.replace(": ...", ":\n        \"\"\"Return the documented value.\"\"\""),
                    encoding="utf-8",
                )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            modn = (root / "sage/matrix/matrix_modn_sparse.pyi").read_text(encoding="utf-8")
            mod2 = (root / "sage/matrix/matrix_mod2_dense.pyi").read_text(encoding="utf-8")
            gf2e = (root / "sage/matrix/matrix_gf2e_dense.pyi").read_text(encoding="utf-8")
            integer = (root / "sage/matrix/matrix_integer_dense.pyi").read_text(encoding="utf-8")
            rational = (root / "sage/matrix/matrix_rational_dense.pyi").read_text(encoding="utf-8")
            self.assertIn("def determinant(self) -> 'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp':", modn)
            self.assertIn("def rank(self) -> int:", modn)
            self.assertIn("def swap_rows(self, i, j) -> None:", modn)
            self.assertIn("def density(self, approx: Literal[False] = False) -> 'sage.rings.rational.Rational': ...", modn)
            self.assertIn("def density(self, approx: Literal[True]) -> float: ...", mod2)
            self.assertIn("def determinant(self) -> 'sage.rings.finite_rings.integer_mod.IntegerMod_int':", mod2)
            self.assertIn("def row(self, i) -> 'sage.modules.vector_mod2_dense.Vector_mod2_dense':", mod2)
            self.assertIn("def echelonize(self) -> None:", mod2)
            self.assertIn("def determinant(self) -> 'sage.rings.finite_rings.element_givaro.FiniteField_givaroElement':", gf2e)
            self.assertIn("def slice(self) -> tuple['sage.matrix.matrix_mod2_dense.Matrix_mod2_dense', ...]:", gf2e)
            self.assertIn("def cling(self, *C) -> None:", gf2e)
            self.assertIn("def transpose(self) -> Self:", gf2e)
            self.assertIn("def __invert__(self) -> 'sage.matrix.matrix_rational_dense.Matrix_rational_dense':", integer)
            self.assertIn("def inverse_of_unit(self) -> Self:", integer)
            self.assertIn("def determinant(self) -> 'sage.rings.integer.Integer':", integer)
            self.assertIn("def rank(self) -> int:", integer)
            self.assertIn("def charpoly(self) -> 'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint':", integer)
            self.assertIn("def row(self, i) -> 'sage.modules.vector_integer_dense.Vector_integer_dense':", integer)
            self.assertIn("def smith_form(self, transformation: Literal[False] = False, integral=None) -> Self: ...", integer)
            self.assertIn("def smith_form(self, transformation: Literal[True] = True, integral=None) -> tuple[Self, Self, Self]: ...", integer)
            self.assertIn("def __pow__(self, n, dummy) -> Self | 'sage.matrix.matrix_rational_dense.Matrix_rational_dense':", integer)
            self.assertIn("def symplectic_form(self) -> tuple[Self, Self]:", integer)
            self.assertIn("def _ntl_(self) -> 'sage.libs.ntl.ntl_mat_ZZ.ntl_mat_ZZ':", integer)
            self.assertIn("def _richcmp_(self, right, op) -> bool:", integer)
            self.assertIn("def decomposition(self, **kwds) -> 'sage.structure.sequence.Sequence_generic':", integer)
            self.assertIn("def inverse(self) -> Self:", rational)
            self.assertIn("def determinant(self) -> 'sage.rings.rational.Rational':", rational)
            self.assertIn("def charpoly(self) -> 'sage.rings.polynomial.polynomial_rational_flint.Polynomial_rational_flint':", rational)
            self.assertIn("def rank(self) -> int:", rational)
            self.assertIn("def column(self, i) -> 'sage.modules.vector_rational_dense.Vector_rational_dense':", rational)
            self.assertIn("def smith_form(self, transformation: Literal[False] = False, integral=None) -> Self: ...", rational)
            self.assertIn("def smith_form(self, transformation: Literal[True] = True, integral=None) -> tuple[Self, Self, Self]: ...", rational)
            self.assertIn("def prod_of_row_sums(self, cols) -> 'sage.rings.rational.Rational':", rational)
            self.assertIn("def _magma_init_(self, magma) -> str:", rational)
            self.assertIn("def _richcmp_(self, right, op) -> bool:", rational)
            for content in (modn, mod2, gf2e, integer, rational):
                ast.parse(content)

    def test_ctf_polynomial_zmod_flint_contracts_are_concrete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "rings" / "polynomial" / "polynomial_zmod_flint.pyi"
            ntl_stub = root / "sage" / "rings" / "polynomial" / "polynomial_modn_dense_ntl.pyi"
            stub.parent.mkdir(parents=True)
            ntl_stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text(
                """class Polynomial_zmod_flint:
    def __call__(self, *args, **kwargs):
        '''Evaluate at a modular element.'''
    def resultant(self, other):
        '''Return the modular resultant.'''
    def small_roots(self, *args, **kwds):
        '''Return small modular roots.'''
    def __pow__(self, n, modulus=None):
        '''Raise to a power.'''
    def rational_reconstruction(self, m, n_deg=0, d_deg=0):
        '''Return numerator and denominator polynomials.'''
    def squarefree_decomposition(self):
        '''Return a factorization.'''
    def monic(self):
        '''Return a monic polynomial.'''
    def reverse(self):
        '''Return the reversed polynomial.'''
    def revert_series(self, n):
        '''Return the compositional inverse series.'''
    def minpoly_mod(self, other):
        '''Return the modular minimal polynomial.'''
    def compose_mod(self, other, modulus):
        '''Return the modular composition.'''
""",
                encoding="utf-8",
            )
            ntl_stub.write_text(
                """class Polynomial_dense_mod_p:
    def __pow__(self, n, modulus=None):
        '''Return modular or fraction-field exponentiation.'''
""",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            patched = stub.read_text(encoding="utf-8")
            ntl_patched = ntl_stub.read_text(encoding="utf-8")
            self.assertIn("def __call__(self, *args, **kwargs) -> 'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp':", patched)
            self.assertIn("def resultant(self, other) -> 'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp':", patched)
            self.assertIn("def small_roots(self, *args, **kwds) -> list['sage.rings.integer.Integer']:", patched)
            self.assertIn("def rational_reconstruction(self, m, n_deg=0, d_deg=0) -> tuple[Self, Self]:", patched)
            self.assertIn("def squarefree_decomposition(self) -> 'sage.structure.factorization.Factorization':", patched)
            self.assertIn("def minpoly_mod(self, other) -> Self:", patched)
            self.assertIn("def compose_mod(self, other, modulus) -> Self:", patched)
            self.assertIn("def __pow__(self, n, modulus=None) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p | sage.rings.fraction_field_element.FractionFieldElement':", ntl_patched)
            ast.parse(patched)
            ast.parse(ntl_patched)

    def test_ctf_integer_and_rational_flint_polynomials_keep_parent_contracts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {
                "sage/rings/polynomial/polynomial_integer_dense_flint.pyi": (
                    "class Polynomial_integer_dense_flint:\n"
                    "    def _add_(self, other): ...\n    def _sub_(self, other): ...\n"
                    "    def _neg_(self): ...\n    def quo_rem(self, other): ...\n"
                    "    def gcd(self, other): ...\n    def lcm(self, other): ...\n"
                    "    def xgcd(self, other): ...\n    def _mul_(self, other): ...\n"
                    "    def _lmul_(self, other): ...\n    def _rmul_(self, other): ...\n"
                    "    def __pow__(self, exp, modulus=None): ...\n    def __floordiv__(self, other): ...\n"
                    "    def squarefree_decomposition(self): ...\n    def factor_mod(self, p): ...\n"
                    "    def factor_padic(self, p, prec): ...\n    def resultant(self, other): ...\n"
                    "    def reverse(self): ...\n    def revert_series(self, n): ...\n"
                    "    def discriminant(self): ...\n    def _eval_mpfr_(self, a): ...\n    def _eval_mpfi_(self, a): ...\n"
                    "    def pseudo_divrem(self, B): ...\n    def real_root_intervals(self): ...\n"
                ),
                "sage/rings/polynomial/polynomial_rational_flint.pyi": (
                    "class Polynomial_rational_flint:\n"
                    "    def _add_(self, other): ...\n    def _sub_(self, other): ...\n"
                    "    def _neg_(self): ...\n    def quo_rem(self, other): ...\n"
                    "    def gcd(self, other): ...\n    def lcm(self, other): ...\n"
                    "    def xgcd(self, other): ...\n    def _mul_(self, other): ...\n"
                    "    def _lmul_(self, other): ...\n    def _rmul_(self, other): ...\n"
                    "    def __pow__(self, exp, modulus=None): ...\n    def __floordiv__(self, other): ...\n"
                    "    def _mod_(self, other): ...\n    def squarefree_decomposition(self): ...\n"
                    "    def factor_mod(self, p): ...\n    def factor_padic(self, p, prec): ...\n"
                    "    def resultant(self, other): ...\n    def reverse(self): ...\n"
                    "    def revert_series(self, n): ...\n    def discriminant(self): ...\n"
                    "    def __lshift__(self, n): ...\n    def __rshift__(self, n): ...\n"
                    "    def numerator(self): ...\n    def denominator(self): ...\n    def hensel_lift(self, p, e): ...\n"
                    "    def galois_group_davenport_smith_test(self, num_trials=50, assume_irreducible=False): ...\n"
                    "    def real_root_intervals(self): ...\n"
                ),
            }
            for relative, content in fixtures.items():
                stub = root / relative
                stub.parent.mkdir(parents=True, exist_ok=True)
                stub.write_text(
                    content.replace(": ...", ":\n        '''Return the documented value.'''") ,
                    encoding="utf-8",
                )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
            integer = (root / "sage/rings/polynomial/polynomial_integer_dense_flint.pyi").read_text(encoding="utf-8")
            rational = (root / "sage/rings/polynomial/polynomial_rational_flint.pyi").read_text(encoding="utf-8")
            self.assertIn("def quo_rem(self, other) -> tuple[Self, Self]:", integer)
            self.assertIn("def xgcd(self, other) -> tuple[Self, Self, Self]:", integer)
            self.assertIn("def __pow__(self, exp, modulus=None) -> Self | 'sage.rings.fraction_field_element.FractionFieldElement':", integer)
            self.assertIn("def resultant(self, other) -> 'sage.rings.integer.Integer':", integer)
            self.assertIn("def discriminant(self) -> 'sage.rings.integer.Integer':", integer)
            self.assertIn("def _eval_mpfr_(self, a) -> 'sage.rings.real_mpfr.RealNumber':", integer)
            self.assertIn("def _eval_mpfi_(self, a) -> 'sage.rings.real_mpfi.RealIntervalFieldElement':", integer)
            self.assertIn("def pseudo_divrem(self, B) -> tuple[Self, Self, 'sage.rings.integer.Integer']:", integer)
            self.assertIn("def real_root_intervals(self) -> list[tuple[tuple['sage.rings.rational.Rational', 'sage.rings.rational.Rational'], 'sage.rings.integer.Integer']]:", integer)
            self.assertIn("def _mod_(self, other) -> Self:", rational)
            self.assertIn("def resultant(self, other) -> 'sage.rings.rational.Rational':", rational)
            self.assertIn("def discriminant(self) -> 'sage.rings.rational.Rational':", rational)
            self.assertIn("def __lshift__(self, n) -> Self:", rational)
            self.assertIn("def numerator(self) -> 'sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint':", rational)
            self.assertIn("def denominator(self) -> 'sage.rings.integer.Integer':", rational)
            self.assertIn("def hensel_lift(self, p, e) -> list['sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint']:", rational)
            self.assertIn("def galois_group_davenport_smith_test(self, num_trials=50, assume_irreducible=False) -> int:", rational)
            for content in (integer, rational):
                ast.parse(content)

    def test_finite_field_elliptic_factory_and_points_are_precise_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            all_stub = root / "sage" / "all.pyi"
            generic_stub = root / "sage" / "schemes" / "elliptic_curves" / "ell_generic.pyi"
            finite_stub = root / "sage" / "schemes" / "elliptic_curves" / "ell_finite_field.pyi"
            point_stub = root / "sage" / "schemes" / "elliptic_curves" / "ell_point.pyi"
            for stub in (all_stub, generic_stub, finite_stub, point_stub):
                stub.parent.mkdir(parents=True, exist_ok=True)
            all_stub.write_text(
                """from sage.rings.finite_rings.finite_field_base import FiniteField as _FactoryReturn_GF

def EllipticCurve(*args, **kwargs) -> object: ...
def GF(*args, **kwargs) -> object: ...
def FiniteField(*args, **kwargs) -> object: ...
""",
                encoding="utf-8",
            )
            generic_stub.write_text(
                """class EllipticCurve_generic:
    \"\"\"A generic elliptic curve.\"\"\"
    def __call__(self, *args, **kwargs): ...
    def gen(self, i): ...
""",
                encoding="utf-8",
            )
            finite_stub.write_text(
                """class EllipticCurve_finite_field:
    \"\"\"An elliptic curve over a finite field.\"\"\"
    def division_field(self, n, names='t', map=False, **kwds):
        pass
    def _fetch_cached_order(self, other):
        pass
    def height_above_floor(self, ell, e):
        pass
    def frobenius_order(self):
        pass
    def endomorphism_order(self):
        pass
    def frobenius(self):
        pass
    def frobenius_endomorphism(self):
        pass
    def multiplication_by_p_isogeny(self):
        pass
    def base_ring(self):
        pass
    def gens(self) -> tuple:
        pass
    def points(self) -> Sequence[Any]:
        pass
    def cardinality_pari(self):
        pass
    def frobenius_discriminant(self):
        pass
    def frobenius_polynomial(self):
        pass
    def plot(self):
        pass

def curves_with_j_0(K):
    pass
def curves_with_j_1728(K):
    pass
def curves_with_j_0_char2(K):
    pass
def curves_with_j_0_char3(K):
    pass
def supersingular_j_polynomial(p, use_cache=True):
    pass
def EllipticCurve_with_order(m, *, D=None):
    pass
def EllipticCurve_with_prime_order(N):
    pass
def special_supersingular_curve(F, q=None, *, endomorphism=False):
    pass
""",
                encoding="utf-8",
            )
            point_stub.write_text(
                """class EllipticCurvePoint:
    def curve(self): ...

class EllipticCurvePoint_field(EllipticCurvePoint):
    def __tuple__(self):
        pass
    def _neg_(self):
        pass
    def _divide_out(self, p):
        pass
    def __pari__(self):
        pass

class EllipticCurvePoint_finite_field(EllipticCurvePoint_field):
    def _compute_order(self, algorithm):
        pass
    pass
""",
                encoding="utf-8",
            )

            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            patched = {stub: stub.read_text(encoding="utf-8") for stub in (all_stub, generic_stub, finite_stub, point_stub)}
            for content in patched.values():
                ast.parse(content)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(patched, {stub: stub.read_text(encoding="utf-8") for stub in patched})

            index_path = root / "index.json"
            indexed = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--source-root",
                    str(root),
                    "--source-locator",
                    "fixture",
                    "--sage-version",
                    "10.9",
                    "--python-version",
                    "3.13",
                    "--output",
                    str(index_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(indexed.returncode, 0, indexed.stderr)
            entries = {entry["qualifiedName"]: entry for entry in json.loads(index_path.read_text(encoding="utf-8"))["entries"]}
            factory = entries["sage.all.EllipticCurve"]["signatures"]
            self.assertEqual("sage.rings.finite_rings.finite_field_base.FiniteField", factory[0]["parameters"][0]["type"]["expression"])
            self.assertEqual("sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field", factory[0]["returnType"]["expression"])
            gf_entry = entries["sage.all.GF"]
            self.assertTrue(any("finite_field_givaro.FiniteField_givaro" in sig["returnType"]["expression"] for sig in gf_entry["signatures"]))
            self.assertTrue(any("finite_field_ntl_gf2e.FiniteField_ntl_gf2e" in sig["returnType"]["expression"] for sig in gf_entry["signatures"]))
            self.assertTrue(any("finite_field_pari_ffelt.FiniteField_pari_ffelt" in sig["returnType"]["expression"] for sig in gf_entry["signatures"]))
            self.assertTrue(any("finite_field_base.FiniteField" not in sig["returnType"].get("expression", "") for sig in gf_entry["signatures"]))
            self.assertEqual(
                "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field",
                entries["sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.__call__"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field",
                entries["sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.gen"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "sage.rings.integer.Integer",
                entries["sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.cardinality_pari"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "sage.rings.integer.Integer",
                entries["sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.frobenius_discriminant"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "sage.rings.finite_rings.finite_field_prime_modn.FiniteField_prime_modn | sage.rings.finite_rings.finite_field_givaro.FiniteField_givaro | sage.rings.finite_rings.finite_field_ntl_gf2e.FiniteField_ntl_gf2e | sage.rings.finite_rings.finite_field_pari_ffelt.FiniteField_pari_ffelt",
                entries["sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.base_ring"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "sage.rings.polynomial.polynomial_integer_dense_flint.Polynomial_integer_dense_flint",
                entries["sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.frobenius_polynomial"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "sage.plot.graphics.Graphics",
                entries["sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.plot"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "sage.rings.integer.Integer",
                entries["sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field._compute_order"]["signatures"][0]["returnType"]["expression"],
            )
            for name, expected in (
                ("_fetch_cached_order", "None"),
                ("height_above_floor", "sage.rings.integer.Integer"),
                ("frobenius_order", "sage.rings.number_field.order.Order_absolute"),
                ("endomorphism_order", "sage.rings.number_field.order.Order_absolute"),
                ("frobenius_endomorphism", "sage.schemes.elliptic_curves.hom_frobenius.EllipticCurveHom_frobenius"),
                ("multiplication_by_p_isogeny", "sage.schemes.elliptic_curves.hom_composite.EllipticCurveHom_composite"),
            ):
                self.assertEqual(
                    expected,
                    entries[f"sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field.{name}"]["signatures"][0]["returnType"]["expression"],
                )
            self.assertIn(
                "def __getitem__(self, n) -> 'sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field': ...",
                patched[finite_stub],
            )
            self.assertIn("def __iter__(self) -> Iterator[", patched[finite_stub])
            self.assertIn(
                "def gens(self) -> tuple['sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field', ...]:",
                patched[finite_stub],
            )
            self.assertIn(
                "def points(self) -> 'sage.structure.sequence.Sequence_generic[sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field]':",
                patched[finite_stub],
            )
            self.assertIn(
                "def a1(self) -> 'sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp | sage.rings.finite_rings.element_givaro.FiniteField_givaroElement | sage.rings.finite_rings.element_ntl_gf2e.FiniteField_ntl_gf2eElement | sage.rings.finite_rings.element_pari_ffelt.FiniteFieldElement_pari_ffelt': ...",
                patched[finite_stub],
            )
            for declaration in (
                "def curves_with_j_0(K) -> list['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']:",
                "def curves_with_j_1728(K) -> list['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']:",
                "def supersingular_j_polynomial(p, use_cache=True) -> 'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint':",
                "def EllipticCurve_with_order(m, *, D=None) -> Iterator['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field']:",
            ):
                self.assertIn(declaration, patched[finite_stub])
            self.assertIn(
                "def special_supersingular_curve(F, q=None, *, endomorphism: Literal[True] = True) -> tuple['sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field', 'sage.schemes.elliptic_curves.ell_curve_isogeny.EllipticCurveIsogeny']: ...",
                patched[finite_stub],
            )
            self.assertIn("def division_field(self, n, names='t', map: Literal[False] = False, **kwds) ->", patched[finite_stub])
            self.assertIn("def division_field(self, n, names='t', map: Literal[True] = True, **kwds) -> tuple[", patched[finite_stub])
            self.assertEqual(
                "tuple[typing.Self, sage.rings.integer.Integer]",
                entries["sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_field._divide_out"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "cypari2.gen.Gen",
                entries["sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_field.__pari__"]["signatures"][0]["returnType"]["expression"],
            )
            self.assertEqual(
                "tuple",
                entries["sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_field.__tuple__"]["signatures"][0]["returnType"]["expression"],
            )

    def test_matrix_solve_overloads_are_idempotent_and_indexed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "matrix" / "matrix2.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                """from sage.modules.free_module_element import FreeModuleElement

class Matrix:
    def solve_left(self, B, check=True, *, extend=True) -> FreeModuleElement | Matrix:
        \"\"\"Solve on the left.\"\"\"
    def solve_right(self, B, check=True, *, extend=True) -> FreeModuleElement | Matrix:
        \"\"\"Solve on the right.\"\"\"
""",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            ast.parse(patched)
            self.assertEqual(4, patched.count("@overload"))
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

            index_path = root / "index.json"
            indexed = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--source-root",
                    str(root),
                    "--source-locator",
                    "fixture",
                    "--sage-version",
                    "10.9",
                    "--python-version",
                    "3.13",
                    "--output",
                    str(index_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(indexed.returncode, 0, indexed.stderr)
            entries = json.loads(index_path.read_text(encoding="utf-8"))["entries"]
            solve_right = next(entry for entry in entries if entry["qualifiedName"] == "sage.matrix.matrix2.Matrix.solve_right")
            self.assertEqual(
                [
                    ("sage.modules.free_module_element.FreeModuleElement", "sage.modules.free_module_element.FreeModuleElement"),
                    ("sage.matrix.matrix2.Matrix", "sage.matrix.matrix2.Matrix"),
                ],
                [
                    (signature["parameters"][0]["type"]["expression"], signature["returnType"]["expression"])
                    for signature in solve_right["signatures"]
                ],
            )

    def test_matrix_factory_overloads_select_concrete_ctf_backends(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            constructor = root / "sage" / "matrix" / "constructor.pyi"
            all_stub = root / "sage" / "all.pyi"
            constructor.parent.mkdir(parents=True)
            all_stub.parent.mkdir(parents=True, exist_ok=True)
            constructor.write_text("def matrix(*args, **kwds) -> object:\n    ...\n", encoding="utf-8")
            all_stub.write_text("def Matrix(*args, **kwds) -> object:\n    ...\n", encoding="utf-8")
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched_constructor = constructor.read_text(encoding="utf-8")
            patched_all = all_stub.read_text(encoding="utf-8")
            for content in (patched_constructor, patched_all):
                ast.parse(content)
                self.assertEqual(6, content.count("@overload"))
                self.assertIn("Matrix_integer_dense", content)
                self.assertIn("Matrix_integer_sparse", content)
                self.assertIn("Matrix_rational_dense", content)
                self.assertIn("Matrix_rational_sparse", content)
                self.assertIn("Matrix_modn_dense_float", content)
                self.assertIn("Matrix_modn_sparse", content)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched_constructor, constructor.read_text(encoding="utf-8"))
            self.assertEqual(patched_all, all_stub.read_text(encoding="utf-8"))

    def test_explicit_source_return_heads_materialize_self_and_unique_classes(self):
        """Chinese return sections must not leave proven classes as UNKNOWN."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            matrix_stub = root / "sage" / "matrix" / "matrix2.pyi"
            polynomial_stub = root / "sage" / "rings" / "polynomial" / "polynomial_element.pyi"
            factorization_stub = root / "sage" / "structure" / "factorization.pyi"
            graphics_stub = root / "sage" / "plot" / "graphics.pyi"
            composition_stub = root / "sage" / "combinat" / "composition.pyi"
            for stub in (matrix_stub, polynomial_stub, factorization_stub, graphics_stub, composition_stub):
                stub.parent.mkdir(parents=True, exist_ok=True)
            matrix_stub.write_text(
                """class Matrix:
    def derivative(self):
        \"\"\"返回: Any -- 对每个元素求导，返回同类型矩阵。\"\"\"
    def inverse(self):
        \"\"\"返回: Matrix -- 与 self 同类型的逆矩阵。\"\"\"
    def ambiguous(self):
        \"\"\"返回: Matrix or tuple -- 取决于参数。\"\"\"
""",
                encoding="utf-8",
            )
            polynomial_stub.write_text(
                """class Polynomial:
    def factor(self):
        \"\"\"返回: Factorization 形式 -- 多项式分解。\"\"\"
""",
                encoding="utf-8",
            )
            factorization_stub.write_text("class Factorization: ...\n", encoding="utf-8")
            graphics_stub.write_text("class Graphics: ...\n", encoding="utf-8")
            composition_stub.write_text("class Composition: ...\n", encoding="utf-8")
            factory_stub = root / "sage" / "factory.pyi"
            factory_stub.write_text(
                """def graph():
    \"\"\"返回: Any -- 类型为 ``sage.plot.graphics.Graphics`` 的图像。\"\"\"

def composition():
    \"\"\"OUTPUT: Composition -- the resulting composition.\"\"\"

def tuple_value():
    \"\"\"OUTPUT: A tuple whose first component is the value.\"\"\"

def string_value():
    \"\"\"Return the :class:`String` representation of the value.\"\"\"

def generic_matroid():
    \"\"\"OUTPUT: matroid\"\"\"
""",
                encoding="utf-8",
            )

            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("from typing import Self", matrix_stub.read_text(encoding="utf-8"))
            matrix_text = matrix_stub.read_text(encoding="utf-8")
            self.assertIn("def derivative(self) -> Self:", matrix_text)
            self.assertIn("def inverse(self) -> Self:", matrix_text)
            self.assertIn("def ambiguous(self):", matrix_text)
            self.assertIn(
                "def factor(self) -> 'sage.structure.factorization.Factorization':",
                polynomial_stub.read_text(encoding="utf-8"),
            )
            factory_text = factory_stub.read_text(encoding="utf-8")
            self.assertIn("def graph() -> 'sage.plot.graphics.Graphics':", factory_text)
            self.assertIn("def composition() -> 'sage.combinat.composition.Composition':", factory_text)
            self.assertIn("def tuple_value() -> tuple:", factory_text)
            self.assertIn("def string_value() -> str:", factory_text)
            self.assertIn("def generic_matroid():", factory_text)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(matrix_text, matrix_stub.read_text(encoding="utf-8"))
            self.assertEqual(factory_text, factory_stub.read_text(encoding="utf-8"))

    def test_parent_dependent_matrix_ring_and_conditional_contracts_are_precise(self):
        """Runtime-proven parent/element contracts remain narrow and idempotent."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixtures = {
                "sage/matrix/matrix0.pyi": (
                    "class Matrix:\n"
                    "    def _add_(self, other):\n        pass\n"
                    "    def _sub_(self, other):\n        pass\n"
                    "    def __neg__(self):\n        pass\n"
                    "    def __pos__(self):\n        pass\n"
                    "    def __mod__(self, p):\n        pass\n"
                    "    def anticommutator(self, other):\n        pass\n"
                    "    def with_swapped_columns(self, c1, c2):\n        pass\n"
                    "    def with_swapped_rows(self, r1, r2):\n        pass\n"
                    "    def with_added_multiple_of_column(self, i, j, s):\n        pass\n"
                    "    def with_col_set_to_multiple_of_col(self, i, j, s):\n        pass\n"
                    "    def with_rescaled_col(self, i, s):\n        pass\n"
                    "    def commutator(self, other):\n        pass\n"
                    "    def __getitem__(self, key):\n        pass\n"
                    "    def is_symmetrizable(self, return_diag=False, positive=True):\n        pass\n"
                    "    def is_skew_symmetrizable(self, return_diag=False, positive=True):\n        pass\n"
                ),
                "sage/matrix/matrix2.pyi": (
                    "class Matrix:\n"
                    "    def fcp(self):\n        pass\n"
                    "    def LLL_gram(self):\n        pass\n"
                    "    def matrix_window(self):\n        pass\n"
                    "    def subdivision(self, i, j):\n        pass\n"
                    "    def decomposition(self, algorithm='spin', is_diagonalizable=False, dual=False):\n        pass\n"
                    "    def decomposition_of_subspace(self, M, check_restrict=True, **kwds):\n        pass\n"
                ),
                "sage/rings/integer_ring.pyi": "class IntegerRing_class:\n    def range(self, stop):\n        pass\n    def __iter__(self):\n        pass\n",
                "sage/rings/rational_field.pyi": "class RationalField:\n    def __iter__(self):\n        pass\n    def range_by_height(self, start, end=None):\n        pass\n    def gen(self, n=0):\n        pass\n",
                "sage/rings/finite_rings/element_base.pyi": "class FinitePolyExtElement:\n    def __getitem__(self, n):\n        pass\n    def __iter__(self):\n        pass\n",
                "sage/rings/finite_rings/finite_field_prime_modn.pyi": "class FiniteField_prime_modn:\n    def __iter__(self):\n        pass\n",
                "sage/rings/finite_rings/finite_field_givaro.pyi": "class FiniteField_givaro:\n    def __iter__(self):\n        pass\n",
                "sage/rings/finite_rings/finite_field_ntl_gf2e.pyi": "class FiniteField_ntl_gf2e:\n    pass\n",
                "sage/rings/finite_rings/finite_field_pari_ffelt.pyi": "class FiniteField_pari_ffelt:\n    pass\n",
                "sage/rings/polynomial/polynomial_ring.pyi": (
                    "class PolynomialRing_dense_mod_p:\n"
                    "    def gen(self, n=0) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p':\n"
                    "        pass\n"
                ),
            }
            for relative, content in fixtures.items():
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")

            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, first.returncode, first.stderr)
            patched = {relative: (root / relative).read_text(encoding="utf-8") for relative in fixtures}
            for content in patched.values():
                ast.parse(content)
            matrix0 = patched["sage/matrix/matrix0.pyi"]
            self.assertIn("from typing import overload, Literal", matrix0)
            self.assertIn("from typing import Self", matrix0)
            self.assertIn("def __neg__(self) -> Self:", matrix0)
            self.assertIn(
                "def __getitem__(self, key: tuple[slice, slice]) -> Self: ...",
                matrix0,
            )
            self.assertIn(
                "def is_symmetrizable(self, return_diag: Literal[True], positive: bool = True) -> list | Literal[False]: ...",
                matrix0,
            )
            self.assertIn("def commutator(self, other: Self) -> Self: ...", matrix0)
            matrix2 = patched["sage/matrix/matrix2.pyi"]
            self.assertIn("def fcp(self) -> 'sage.structure.factorization.Factorization':", matrix2)
            self.assertIn("def decomposition_of_subspace(self, M, check_restrict=True, **kwds) -> 'sage.structure.sequence.Sequence_generic':", matrix2)
            self.assertIn("def decomposition(self, algorithm='spin', is_diagonalizable=False, dual: Literal[True] = True) -> tuple['sage.structure.sequence.Sequence_generic', 'sage.structure.sequence.Sequence_generic']: ...", matrix2)
            self.assertIn("def __call__(self, x=0, *args, **kwds) -> 'sage.rings.integer.Integer': ...", patched["sage/rings/integer_ring.pyi"])
            self.assertIn("def __iter__(self) -> Iterator['sage.rings.rational.Rational']:", patched["sage/rings/rational_field.pyi"])
            self.assertIn("from typing import Iterator", patched["sage/rings/finite_rings/element_base.pyi"])
            self.assertIn("def __iter__(self) -> Iterator['sage.rings.finite_rings.integer_mod.IntegerMod_int | sage.rings.finite_rings.integer_mod.IntegerMod_int64 | sage.rings.finite_rings.integer_mod.IntegerMod_gmp']:", patched["sage/rings/finite_rings/finite_field_prime_modn.pyi"])
            polynomial = patched["sage/rings/polynomial/polynomial_ring.pyi"]
            self.assertEqual(1, polynomial.count("class PolynomialRing_dense_mod_p"))
            self.assertIn("def gen(self, n=0) -> 'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint':", polynomial)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, {relative: (root / relative).read_text(encoding="utf-8") for relative in fixtures})

            index_path = root / "index.json"
            indexed = subprocess.run(
                [
                    sys.executable,
                    str(GENERATOR),
                    "--source-root",
                    str(root),
                    "--source-locator",
                    "fixture",
                    "--sage-version",
                    "10.9",
                    "--python-version",
                    "3.13",
                    "--output",
                    str(index_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, indexed.returncode, indexed.stderr)
            entries = {entry["qualifiedName"]: entry for entry in json.loads(index_path.read_text(encoding="utf-8"))["entries"]}
            self.assertEqual(
                "typing.Self",
                next(
                    signature["returnType"]["expression"]
                    for signature in entries["sage.matrix.matrix0.Matrix.__neg__"]["signatures"]
                ),
            )
            self.assertEqual(
                "sage.rings.integer.Integer",
                next(
                    signature["returnType"]["expression"]
                    for signature in entries["sage.rings.integer_ring.IntegerRing_class.__call__"]["signatures"]
                ),
            )
            self.assertEqual(
                "sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint",
                next(
                    signature["returnType"]["expression"]
                    for signature in entries["sage.rings.polynomial.polynomial_ring.PolynomialRing_dense_mod_p.gen"]["signatures"]
                ),
            )


if __name__ == "__main__":
    unittest.main()
