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
                "    def __int__(self): ...\n"
                "    def __float__(self): ...\n"
                "    def __complex__(self): ...\n"
                "    def __dir__(self): ...\n"
                "    def __eq__(self, other): ...\n"
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
            self.assertIn("def __int__(self) -> int: ...", patched)
            self.assertIn("def __float__(self) -> float: ...", patched)
            self.assertIn("def __complex__(self) -> complex: ...", patched)
            self.assertIn("def __dir__(self) -> list[str]: ...", patched)
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
            self.assertIn("def ambiguous(n):", patched)
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
    def cardinality_pari(self):
        pass
    def frobenius_discriminant(self):
        pass
    def frobenius_polynomial(self):
        pass
    def plot(self):
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
            patched = {stub: stub.read_text(encoding="utf-8") for stub in (all_stub, generic_stub, finite_stub)}
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
