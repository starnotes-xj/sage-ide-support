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
                "    def __repr__(\n"
                "        self,\n"
                "    ): ...\n"
                "    def __len__(self): ...\n"
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
            self.assertIn("def __len__(self) -> int: ...", patched)
            self.assertIn("def __eq__(self, other): ...", patched)
            self.assertIn("def __repr__(self): ...", patched)
            second = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(0, second.returncode, second.stderr)
            self.assertEqual(patched, stub.read_text(encoding="utf-8"))

    def test_gcd_typevar_contract_is_indexed_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stub = root / "sage" / "arith" / "misc.pyi"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "\"\"\"Arithmetic helpers\"\"\"\n"
                "def gcd(a, b=None, **kwargs): ...\n",
                encoding="utf-8",
            )
            command = [sys.executable, str(PATCHER), "--stub-root", str(root)]
            first = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            patched = stub.read_text(encoding="utf-8")
            self.assertIn("def gcd(a: GcdT, b: GcdT, **kwargs) -> GcdT: ...", patched)
            self.assertTrue(patched.startswith('"""Arithmetic helpers"""\nfrom typing import TypeVar\n'))
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
""",
                encoding="utf-8",
            )
            point_stub.write_text(
                """class EllipticCurvePoint:
    def curve(self): ...

class EllipticCurvePoint_finite_field(EllipticCurvePoint):
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


if __name__ == "__main__":
    unittest.main()
