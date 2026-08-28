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

# ADD: member name -> annotation expression for unannotated defs.
CURATED_ANNOTATIONS: dict[str, dict[str, dict[str, str]]] = {
    "sage/schemes/elliptic_curves/ell_point.pyi": {
        "EllipticCurvePoint": {
            "curve": "'sage.schemes.elliptic_curves.ell_generic.EllipticCurve_generic'",
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
        },
    },
    "sage/matrix/matrix2.pyi": {
        "Matrix": {
            # solve_left has the same result family as solve_right in Sage 10.9.
            "solve_left": "FreeModuleElement | Matrix",
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
        },
    },
    "sage/rings/finite_rings/element_base.pyi": {
        "FiniteRingElement": {
        },
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
        "PolynomialRing_generic": {
            "gen": "'sage.rings.polynomial.polynomial_element.Polynomial'",
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
            "__pow__": "Polynomial",
            "derivative": "Polynomial",
            "gcd": "Polynomial",
            "xgcd": "tuple[Polynomial, Polynomial, Polynomial]",
            "quo_rem": "tuple[Polynomial, Polynomial]",
        },
    },
}

# REPLACE: member name -> annotation expression for defs that already have
# an annotation.  Used to point factory returns at the most capable real
# class so member completion covers the commonly used subclass surface.
CURATED_REPLACE_ANNOTATIONS: dict[str, dict[str, dict[str, str]]] = {
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
    "sage/arith/misc.pyi": {
        None: {
            # ``gcd`` coerces operands to a common parent and returns an
            # element of that parent.  This TypeVar preserves the concrete
            # operand class for calls such as ``gcd(f, f.derivative())``.
            "gcd": (
                "def gcd(a: GcdT, b: GcdT, **kwargs) -> GcdT: ...",
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
        },
    },
}

# Module-level TypeVars used by the contracts above.  The declaration is kept
# in the generated source stub so the extractor records it on each overload.
CURATED_TYPE_VARIABLES: dict[str, tuple[str, ...]] = {
    "sage/arith/misc.pyi": ("GcdT",),
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
        ),
    },
    "sage/schemes/elliptic_curves/ell_point.pyi": {
        "EllipticCurvePoint_finite_field": (
            "def curve(self) -> 'sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field': ...",
        ),
    },
    "sage/rings/polynomial/polynomial_ring.pyi": {
        "PolynomialRing_dense_mod_p": (
            "def gen(self, n=0) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
        ),
        "PolynomialRing_dense_finite_field": (
            "def gen(self, n=0) -> 'sage.rings.polynomial.polynomial_element_generic.Polynomial_generic_dense_field': ...",
        ),
    },
    "sage/rings/polynomial/polynomial_modn_dense_ntl.pyi": {
        "Polynomial_dense_mod_p": (
            "def __pow__(self, n, modulus=None) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
            "def __add__(self, other) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
            "def __mul__(self, other) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
            "def __rmul__(self, other) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
            "def derivative(self, *args) -> 'sage.rings.polynomial.polynomial_modn_dense_ntl.Polynomial_dense_mod_p': ...",
        ),
    },
    "sage/rings/polynomial/polynomial_zmod_flint.pyi": {
        "Polynomial_zmod_flint": (
            "def __pow__(self, exp, modulus=None) -> 'sage.rings.polynomial.polynomial_zmod_flint.Polynomial_zmod_flint': ...",
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
    "__str__": "str",
    "__repr__": "str",
    "__format__": "str",
    "__bytes__": "bytes",
    "__bool__": "bool",
    "__len__": "int",
    "__index__": "int",
    "__hash__": "int",
}

_DEF_RE = re.compile(r"^(?P<indent>\s*)def\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\(")
_RETURN_RE = re.compile(r"\s*->\s*(.+):\s*$")


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
    if edits and not any(line.strip() == "from typing import overload" for line in lines):
        lines.insert(_typing_import_insertion_index("".join(lines), lines), "from typing import overload\n")
    if edits:
        path.write_text("".join(lines), encoding="utf-8")
    return [member for _, _, member in edits]


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
        block = [f"{indent}{declaration}\n" for declaration in declarations]
        if all(declaration in "".join(lines) for declaration in declarations):
            continue
        insertion_index = class_index + 1
        while insertion_index < len(lines) and not lines[insertion_index].strip():
            insertion_index += 1
        if insertion_index < len(lines) and re.match(r"^\s*(?:r|u|b|f|br|rb|fr|rf)?['\"]{3}", lines[insertion_index], re.IGNORECASE):
            quote = '\"\"\"' if '\"\"\"' in lines[insertion_index] else "'''"
            insertion_index += 1
            while insertion_index < len(lines):
                if quote in lines[insertion_index]:
                    insertion_index += 1
                    break
                insertion_index += 1
        lines[insertion_index:insertion_index] = block
        inserted.extend(declaration.split("(", 1)[0].removeprefix("def ") for declaration in declarations)
    if inserted:
        path.write_text("".join(lines), encoding="utf-8")
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
    # Roll back the earlier base-class forwarding hack (matrix0 solve_right).
    matrix0 = root / "sage/matrix/matrix0.pyi"
    if matrix0.is_file() and remove_inserted(matrix0, "solve_right"):
        verify(matrix0)
        print("sage/matrix/matrix0.pyi [Matrix]: removed forwarded solve_right")
    print(f"annotate-stubs: {total} member(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
