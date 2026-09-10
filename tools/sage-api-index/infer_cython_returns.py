#!/usr/bin/env python3
"""Extract Python wrapper returns from explicit Cython declarations.

The wrapper's declared Python/Cython return type is used as the contract, not
method names or observed samples.  Builtin Python containers/scalars are
always exact.  Extension-class declarations are resolved only when a unique
class symbol is present in the generated Sage index; ambiguous parent/base
symbols fail closed.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import tokenize
from pathlib import Path
from infer_source_returns import _implicit_none_is_safe, _may_fall_through, _returns


INTEGER = r"(?:(?:signed|unsigned)\s+)?(?:char|short(?:\s+int)?|int|long(?:\s+long)?(?:\s+int)?)|Py_ssize_t"
PYTHON_DECLARED = r"(?:list|tuple|dict|set|str|bytes|bytearray|object)(?:\[[^\]\n]+\])?"
DECLARED_TYPE = rf"(?:bint|float|double|void|{INTEGER}|{PYTHON_DECLARED}|[A-Za-z_]\w*)"
DECLARATION = re.compile(
    rf"^cpdef\s+(?:inline\s+)?(?P<type>{DECLARED_TYPE})\s+(?P<name>[A-Za-z_]\w*)\s*\("
)
# Internal ``cdef`` helpers are not public index members, but their declared
# Python-visible result is still sound evidence when a ``def`` wrapper returns
# the helper call.  Keeping this separate from ``DECLARATION`` prevents
# private helpers from being emitted as public contracts.
CDEF_DECLARATION = re.compile(
    rf"^cdef\s+(?:inline\s+)?(?P<type>{DECLARED_TYPE})\s+(?P<name>[A-Za-z_]\w*)\s*\("
)
CLASS = re.compile(r"^(?:cdef\s+)?class\s+([A-Za-z_]\w*)\s*[:(]")
LOCAL = re.compile(rf"^cdef\s+(?P<type>bint|float|double|{INTEGER})\s+(?P<names>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)(?:\s*=.*)?$")

# Direct Python-visible wrappers in ``.pyx`` files occasionally return a
# builtin protocol result without a Cython return declaration (for example
# ``return isinstance(x, Morphism)``).  These calls have fixed Python result
# shapes independent of Sage's dynamic classes, so they are safe to reuse in
# the same branch-free/explicit-branch proof as literal returns.  Calls not
# listed here remain unresolved rather than being widened to ``object``.
PYTHON_CALL_RETURNS = {
    "all": "bool",
    "any": "bool",
    "ascii": "str",
    "bool": "bool",
    "bin": "str",
    "bytes": "bytes",
    "bytearray": "bytearray",
    "callable": "bool",
    "complex": "complex",
    "dict": "dict",
    "divmod": "tuple",
    "enumerate": "Iterator",
    "filter": "Iterator",
    "float": "float",
    "format": "str",
    "hash": "int",
    "hex": "str",
    "id": "int",
    "int": "int",
    "isinstance": "bool",
    "issubclass": "bool",
    "len": "int",
    "list": "list",
    "map": "Iterator",
    "memoryview": "memoryview",
    "oct": "str",
    "ord": "int",
    "repr": "str",
    "range": "range",
    "reversed": "Iterator",
    "set": "set",
    "slice": "slice",
    "sorted": "list",
    "str": "str",
    "tuple": "tuple",
    "type": "type",
    "zip": "Iterator",
}


def scalar_type(ctype: str) -> str | None:
    """Map a declared Cython return to a Python-visible type."""
    if ctype in {'bint'}:
        return 'bool'
    if ctype in {'float', 'double'}:
        return 'float'
    if ctype == 'void':
        return 'None'
    if re.fullmatch(INTEGER, ctype):
        return 'int'
    if ctype in {'list', 'tuple', 'dict', 'set', 'str', 'bytes', 'bytearray'} or ctype.startswith(('list[', 'tuple[', 'dict[', 'set[')):
        return ctype.split('[', 1)[0]
    # ``object`` is intentionally dynamic; Cython performs no narrower
    # conversion for it.
    return None


def _unique_class_types(index: Path | None) -> dict[str, str]:
    """Return unique final class names from a generated Sage index."""
    if index is None:
        return {}
    try:
        payload = json.loads(index.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get('entries', [])
    candidates: dict[str, set[str]] = {}
    class_entries: dict[str, dict] = {}
    for entry in entries:
        if entry.get('kind') != 'CLASS':
            continue
        qualified = entry.get('qualifiedName')
        if not isinstance(qualified, str) or not qualified.startswith('sage.'):
            continue
        name = qualified.rsplit('.', 1)[-1]
        candidates.setdefault(name, set()).add(qualified)
        class_entries[qualified] = entry

    # Some Sage factories use an abstract ABC name in their Cython-visible
    # signature (for example ``ComplexField``), while construction actually
    # returns the single concrete implementation documented by that ABC.  A
    # broad ``.abc.`` rule would be unsafe: many ABCs intentionally represent
    # a family of implementations.  Resolve only the explicit documentation
    # contract that there is a unique direct subclass, and only when the
    # referenced subclass is present in the generated class index.
    abstract_to_concrete: dict[str, str] = {}
    class_paths = set(class_entries)
    class_ref = re.compile(r":class:`~(?P<path>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+)`")
    for qualified, entry in class_entries.items():
        documentation = entry.get('documentation') or {}
        text = ' '.join(str(documentation.get(key, '')) for key in ('summary', 'body'))
        if 'unique direct subclass' not in text.lower():
            continue
        match = class_ref.search(text)
        concrete = match.group('path') if match else None
        if concrete and concrete in class_paths:
            abstract_to_concrete[qualified] = concrete

    def resolve(path: str) -> str:
        seen: set[str] = set()
        while path in abstract_to_concrete and path not in seen:
            seen.add(path)
            path = abstract_to_concrete[path]
        return path

    resolved: dict[str, str] = {}
    for name, values in candidates.items():
        if len(values) != 1:
            continue
        resolved[name] = resolve(next(iter(values)))
    return resolved


_INDEX_BUILTINS = {
    "None", "bool", "bytes", "bytearray", "complex", "dict", "float",
    "frozenset", "int", "list", "memoryview", "range", "set", "slice",
    "str", "tuple", "type", "Self", "Iterator",
}
_STRUCTURAL_SUFFIXES = ("_base", "_generic", "_element", "_parent", "_factory")


def _is_concrete_index_path(value: str) -> bool:
    if not value.startswith("sage."):
        return False
    final = value.rsplit(".", 1)[-1].lower()
    return not any(final.endswith(suffix) for suffix in _STRUCTURAL_SUFFIXES)


def _safe_index_return(expression: object) -> str | None:
    """Keep only simple index returns safe to propagate through a direct call."""
    if not isinstance(expression, str):
        return None
    # The generator stores concrete Sage classes as quoted paths.  A few
    # older contracts use ``typing.Self``/``typing.Iterator`` spellings.
    if expression == "typing.Self":
        return "Self"
    if expression == "typing.Iterator":
        return "Iterator"
    if expression in _INDEX_BUILTINS:
        return expression
    if expression.startswith("'") and expression.endswith("'"):
        path = expression[1:-1]
        return expression if _is_concrete_index_path(path) else None
    try:
        node = ast.parse(expression, mode="eval").body
    except (SyntaxError, ValueError):
        return None

    def valid(value: ast.AST) -> bool:
        if isinstance(value, ast.Name):
            return value.id in _INDEX_BUILTINS
        if isinstance(value, ast.Constant):
            return isinstance(value.value, str) and _is_concrete_index_path(value.value)
        if isinstance(value, ast.Subscript):
            return valid(value.value) and all(
                valid(item) for item in (value.slice.elts if isinstance(value.slice, ast.Tuple) else (value.slice,))
            )
        if isinstance(value, ast.BinOp) and isinstance(value.op, ast.BitOr):
            return valid(value.left) and valid(value.right)
        return False

    return expression if valid(node) else None


def _safe_index_parameter(expression: object) -> str | None:
    """Normalize one exact indexed parameter type for identity propagation."""
    if not isinstance(expression, str):
        return None
    if expression.startswith("sage.") and _is_concrete_index_path(expression):
        return f"'{expression}'"
    return _safe_index_return(expression)


def _unique_callable_returns(index: Path | None) -> dict[str, str]:
    """Index methods/functions whose every overload has one safe return."""
    if index is None:
        return {}
    try:
        payload = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, str] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "METHOD", "PROPERTY"}:
            continue
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str):
            continue
        expressions = []
        for signature in entry.get("signatures", []):
            return_type = signature.get("returnType") or {}
            if return_type.get("state") != "KNOWN":
                expressions = []
                break
            safe = _safe_index_return(return_type.get("expression"))
            if safe is None:
                expressions = []
                break
            expressions.append(safe)
        if expressions and len(set(expressions)) == 1:
            result[qualified] = expressions[0]
    return result


def _unique_parameter_contracts(index: Path | None) -> dict[str, dict[str, str]]:
    """Index parameter types that agree across every callable overload."""
    if index is None:
        return {}
    try:
        payload = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, dict[str, str]] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") not in {"FUNCTION", "METHOD", "PROPERTY"}:
            continue
        qualified = entry.get("qualifiedName")
        signatures = entry.get("signatures", [])
        if not isinstance(qualified, str) or not signatures:
            continue
        by_name: dict[str, set[str]] = {}
        seen_name: dict[str, int] = {}
        for signature in signatures:
            signature_names: set[str] = set()
            for parameter in signature.get("parameters", []):
                name = parameter.get("name")
                parameter_type = parameter.get("type") or {}
                if not isinstance(name, str) or parameter_type.get("state") != "KNOWN":
                    continue
                safe = _safe_index_parameter(parameter_type.get("expression"))
                if safe is not None:
                    by_name.setdefault(name, set()).add(safe)
                    signature_names.add(name)
            for name in signature_names:
                seen_name[name] = seen_name.get(name, 0) + 1
        stable = {
            name: next(iter(values))
            for name, values in by_name.items()
            if len(values) == 1 and seen_name.get(name) == len(signatures)
        }
        if stable:
            result[qualified] = stable
    return result


def _indexed_parameter_names(index: Path | None) -> dict[str, set[str]]:
    """Return parameter names present in any indexed overload.

    This distinguishes an unindexed Cython wrapper (eligible for a fresh
    identity TypeVar) from a known-but-conflicting overload family, where a
    generic alias would hide a real dispatch boundary.
    """
    if index is None:
        return {}
    try:
        payload = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result: dict[str, set[str]] = {}
    for entry in payload.get("entries", []):
        qualified = entry.get("qualifiedName")
        if not isinstance(qualified, str):
            continue
        names = {
            parameter.get("name")
            for signature in entry.get("signatures", [])
            for parameter in signature.get("parameters", [])
            if isinstance(parameter.get("name"), str)
        }
        if names:
            result[qualified] = names
    return result


def _cdef_helper_returns(
    text: str, class_types: dict[str, str] | None = None
) -> dict[str, str]:
    """Resolve local Cython helper declarations to Python result contracts.

    A ``def`` wrapper may return a value produced by a ``cdef``/``cdef inline``
    helper (for example ``new_BP_from_PBPoly``).  The helper's declared return
    class is stronger evidence than a runtime sample, while unresolved or
    ambiguous classes remain absent and therefore fail closed.
    """
    result: dict[str, str] = {}
    for line in text.splitlines():
        # ``cpdef`` helpers declared in a companion ``.pxd`` are also fixed
        # contracts when called by a wrapper in the same module.  Keep only
        # scalar/unique-class declarations; object-typed helpers remain
        # dynamic.
        match = CDEF_DECLARATION.match(line.strip()) or DECLARATION.match(line.strip())
        if not match:
            continue
        ctype = match.group("type")
        annotation = scalar_type(ctype)
        if annotation is None and class_types is not None:
            target = class_types.get(ctype)
            if target is not None and _is_concrete_index_path(target):
                annotation = f"'{target}'"
        if annotation is not None:
            result[match.group("name")] = annotation
    return result


def _global_helper_returns(
    sources: list[tuple[Path, bytes, str, str]],
    class_types: dict[str, str] | None = None,
) -> dict[str, str]:
    """Collect helper contracts whose short name is globally unambiguous.

    Cython ``cimport`` makes helpers such as ``rich_to_bool`` available in
    many modules without repeating their declaration.  Resolve those names
    from the actual ``.pxd``/``.pyx`` declarations and retain a result only
    when every declaration agrees on the same Python-visible shape.  This is
    data-driven and deliberately rejects same-name conflicts.
    """
    candidates: dict[str, set[str]] = {}
    for _, _, text, _ in sources:
        for name, annotation in _cdef_helper_returns(text, class_types).items():
            candidates.setdefault(name, set()).add(annotation)
    return {
        name: next(iter(values))
        for name, values in candidates.items()
        if len(values) == 1
    }


def _index_class_children(index: Path | None) -> dict[str, set[str]]:
    """Load indexed class children for fail-closed Cython field resolution."""
    if index is None:
        return {}
    try:
        payload = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    children: dict[str, set[str]] = {}
    for entry in payload.get("entries", []):
        if entry.get("kind") != "CLASS":
            continue
        child = entry.get("qualifiedName")
        if not isinstance(child, str):
            continue
        for parent in entry.get("parents", []):
            if isinstance(parent, str):
                children.setdefault(parent, set()).add(child)
    return children


def _cdef_field_types(
    text: str,
    module: str,
    class_types: dict[str, str] | None = None,
    indexed_children: dict[str, set[str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Collect concrete ``cdef`` fields from a PYX/PXD class declaration.

    A field is usable only when its declared type resolves to a unique indexed
    leaf (or a Python builtin).  Public bases such as ``ModuleElement`` have
    indexed descendants and are intentionally excluded from final contracts.
    """
    result: dict[str, dict[str, str]] = {}
    scopes: list[tuple[int, str]] = []
    for raw in text.splitlines():
        line = raw.expandtabs(8)
        stripped = line.lstrip()
        if not stripped:
            continue
        indent = len(line) - len(stripped)
        while scopes and indent <= scopes[-1][0]:
            scopes.pop()
        match_class = CLASS.match(stripped)
        if match_class:
            owner = f"{module}.{match_class.group(1)}"
            scopes.append((indent, owner))
            continue
        if not scopes or indent <= scopes[-1][0]:
            continue
        # ``readonly/public`` qualifiers do not alter the Python-visible
        # result; pointer/array declarations remain unresolved.
        field = re.match(
            r"^cdef\s+(?:(?:readonly|public|api|extern)\s+)*"
            r"(?P<type>[A-Za-z_]\w*)\s+(?P<names>[A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)"
            r"(?:\s*=.*)?$",
            stripped,
        )
        if not field:
            continue
        ctype = field.group("type")
        annotation = scalar_type(ctype)
        if annotation is None and class_types is not None:
            target = class_types.get(ctype)
            if target is not None and target not in (indexed_children or {}):
                if _is_concrete_index_path(target):
                    annotation = f"'{target}'"
        if annotation is None:
            continue
        owner_fields = result.setdefault(scopes[-1][1], {})
        for name in re.split(r"\s*,\s*", field.group("names")):
            owner_fields[name] = annotation
    return result


def _lexical_expression_type(
    expression: str,
    local_types: dict[str, str],
    class_types: dict[str, str] | None,
    helper_returns: dict[str, str] | None,
    callable_returns: dict[str, str] | None = None,
    owner_fields: dict[str, str] | None = None,
    owner_qualified: str | None = None,
    parameter_names: set[str] | None = None,
) -> str | None:
    """Classify a small Python-visible expression in a Cython ``def`` body.

    This intentionally accepts only syntax-fixed containers, exact local
    aliases, builtin constructors, unique indexed classes, and declared
    internal helpers.  Arbitrary attributes, C pointers, and dynamic calls are
    rejected instead of widening to a public base class.
    """
    value = expression.strip().rstrip(";").strip()
    if not value:
        return "None"
    if value == "self":
        return "Self"
    if value in local_types:
        return local_types[value]
    # A multiline list return in Cython is still syntactically fixed even
    # though the closing bracket is on a later line.
    if value.startswith("["):
        return "list"
    if value.startswith("{"):
        return "dict"
    # Cython frequently splits a tuple return across physical lines.  A
    # parenthesized expression containing a comma is unambiguously a tuple;
    # parenthesized calls without a comma remain unresolved.
    if value.startswith("(") and "," in value:
        return "tuple"
    try:
        node = ast.parse(value, mode="eval").body
    except (SyntaxError, ValueError):
        return None
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Tuple):
        return "tuple"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Set):
        return "set"
    if isinstance(node, ast.Constant):
        literal = node.value
        if literal is None:
            return "None"
        if isinstance(literal, bool):
            return "bool"
        if isinstance(literal, int):
            return "int"
        if isinstance(literal, float):
            return "float"
        if isinstance(literal, complex):
            return "complex"
        if isinstance(literal, bytes):
            return "bytes"
        if isinstance(literal, str):
            return "str"
        return None
    if isinstance(node, ast.Name):
        return local_types.get(node.id) or (
            f"@parameter:{node.id}"
            if parameter_names is not None and node.id in parameter_names
            else None
        )
    if isinstance(node, ast.Attribute):
        if (
            isinstance(node.value, ast.Name)
            and node.value.id == "self"
            and owner_fields is not None
        ):
            return owner_fields.get(node.attr)
        return None
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        receiver = node.func.value
        target: str | None = None
        if isinstance(receiver, ast.Name) and receiver.id == "self" and owner_qualified:
            target = owner_qualified + "." + node.func.attr
        elif isinstance(receiver, ast.Name) and receiver.id in local_types:
            receiver_type = local_types[receiver.id]
            if isinstance(receiver_type, str) and receiver_type.startswith("'"):
                target = receiver_type[1:-1] + "." + node.func.attr
        elif (
            isinstance(receiver, ast.Attribute)
            and isinstance(receiver.value, ast.Name)
            and receiver.value.id == "self"
            and owner_fields is not None
        ):
            field_type = owner_fields.get(receiver.attr)
            if isinstance(field_type, str) and field_type.startswith("'"):
                target = field_type[1:-1] + "." + node.func.attr
        if target is not None and callable_returns is not None:
            return callable_returns.get(target)
        return None
    if not isinstance(node, ast.Call):
        return None
    if isinstance(node.func, ast.Name):
        name = node.func.id
        builtin = {
            "bool": "bool", "bytes": "bytes", "bytearray": "bytearray",
            "complex": "complex", "dict": "dict", "float": "float",
            "frozenset": "frozenset", "int": "int", "list": "list",
            "memoryview": "memoryview", "range": "range", "set": "set",
            "slice": "slice", "str": "str", "tuple": "tuple", "type": "type",
        }
        if name in builtin:
            return builtin[name]
        if helper_returns is not None and name in helper_returns:
            return helper_returns[name]
        if class_types is not None:
            target = class_types.get(name)
            if target is not None and _is_concrete_index_path(target):
                return f"'{target}'"
    return None


def _def_lexical_return(
    lines: list[str],
    masked: list[list[str]],
    row: int,
    indent: int,
    starts: set[int],
    class_types: dict[str, str] | None = None,
    helper_returns: dict[str, str] | None = None,
    callable_returns: dict[str, str] | None = None,
    owner_fields: dict[str, str] | None = None,
    owner_qualified: str | None = None,
    parameter_names: set[str] | None = None,
) -> str | None:
    """Infer fixed local aliases/containers from otherwise non-Python Cython.

    Cython ``def`` bodies often contain typed declarations or pointer syntax
    that cannot be parsed by :mod:`ast`.  We still can prove a result when all
    assignments and returns reduce to a syntax-fixed expression.  Conflicting
    assignments and unresolved returns fail closed.
    """
    local_values: dict[str, set[str]] = {}
    returns: list[str] = []
    saw_top_level_terminal = False
    top_level_if_without_else = False
    open_top_level_if: int | None = None
    top_level_if_has_else = False
    for j in range(row - 1, len(lines)):
        visible = "".join(masked[j]).expandtabs(8)
        stripped = visible.strip()
        col = len(visible) - len(visible.lstrip())
        if j + 1 != row and j + 1 in starts and stripped and col <= indent:
            break
        if stripped.startswith("raise") and (
            len(stripped) == 5 or stripped[5].isspace()
        ):
            # Conditional/exception-dependent control flow is deliberately
            # outside this lexical proof; the Python AST path handles only
            # shapes it can model completely.
            return None
        if col == indent + 4 and stripped.startswith("if "):
            if open_top_level_if is not None and not top_level_if_has_else:
                top_level_if_without_else = True
            open_top_level_if = j
            top_level_if_has_else = False
        elif col == indent + 4 and stripped.startswith("else") and open_top_level_if is not None:
            top_level_if_has_else = True
        elif col == indent + 4 and stripped and not stripped.startswith(("elif ",)):
            if open_top_level_if is not None and not top_level_if_has_else:
                top_level_if_without_else = True
            open_top_level_if = None
            top_level_if_has_else = False
        if col == indent + 4 and stripped.startswith(("return", "raise")):
            saw_top_level_terminal = True
        # A method-local assignment is enough to recover fixed container and
        # constructor aliases (``face = []``, ``G = Graph(...)``).  Cython
        # declarations without an initializer carry no evidence by themselves.
        assignment = re.match(
            r"^(?:cdef\s+(?:[A-Za-z_]\w*(?:\s*\[[^\]]+\])?\s+)?)*"
            r"(?P<name>[A-Za-z_]\w*)\s*=\s*(?P<value>.+)$",
            stripped,
        )
        if assignment and not stripped.startswith(("return ", "if ", "while ", "for ")):
            name = assignment.group("name")
            known_locals = {
                key: next(iter(values))
                for key, values in local_values.items()
                if len(values) == 1 and "<unknown>" not in values
            }
            inferred = _lexical_expression_type(
                assignment.group("value"), known_locals, class_types, helper_returns,
                callable_returns, owner_fields, owner_qualified,
                parameter_names,
            )
            local_values.setdefault(name, set()).add(inferred or "<unknown>")
        if stripped.startswith("return") and (
            len(stripped) == 6 or stripped[6].isspace()
        ):
            expression = stripped[6:].strip()
            known_locals = {
                key: next(iter(values))
                for key, values in local_values.items()
                if len(values) == 1 and "<unknown>" not in values
            }
            returns.append(
                _lexical_expression_type(
                    expression, known_locals, class_types, helper_returns,
                    callable_returns, owner_fields, owner_qualified,
                    parameter_names,
                )
                or "<unknown>"
            )
    local_types = {
        name: next(iter(values))
        for name, values in local_values.items()
        if len(values) == 1 and "<unknown>" not in values
    }
    if not returns or "<unknown>" in returns:
        return None
    if open_top_level_if is not None and not top_level_if_has_else:
        top_level_if_without_else = True
    if top_level_if_without_else and not saw_top_level_terminal:
        return None
    if len(set(returns)) != 1:
        return None
    # Replace aliases that were recorded before their assignment became
    # available (the common ``G = Graph(...); return G`` shape).
    result = returns[0]
    if result in local_types:
        result = local_types[result]
    return result


def local_return(lines: list[str], masked: list[list[str]], row: int, indent: int, starts: set[int]) -> str | None:
    """Prove returns of scalar C locals in otherwise parseable Python bodies."""
    body = []
    local_types = {}
    for j in range(row, len(lines)):
        visible = ''.join(masked[j]).expandtabs(8)
        stripped = visible.strip()
        col = len(visible) - len(visible.lstrip())
        if j + 1 in starts and stripped and col <= indent:
            break
        match = LOCAL.fullmatch(stripped) if j + 1 in starts and col == indent + 4 else None
        if match:
            for name in re.split(r'\s*,\s*', match.group('names')):
                local_types[name] = scalar_type(match.group('type'))
            # C variables keep their declared type on every assignment. The
            # initializer is not used as return evidence.
            body.append('    pass\n')
        elif j + 1 in starts and col == indent + 4 and stripped.startswith('cdef ') and not stripped.endswith(':') and '(' not in stripped.split('=', 1)[0]:
            # Other single-line C variable declarations are legal statements
            # but provide no scalar evidence (objects, pointers, arrays).
            # Erase only their syntax so unrelated typed scalar returns can
            # still be checked by the Python control-flow visitor.
            body.append('    pass\n')
        else:
            body.append(lines[j].expandtabs(8)[indent:])
    if not local_types:
        return None
    try:
        function = ast.parse('def _probe_():\n' + ''.join(body)).body[0]
    except (SyntaxError, ValueError):
        return None
    if _may_fall_through(function.body):
        return None
    returns, has_yield = _returns(function.body)
    if has_yield or not returns:
        return None
    values = [local_types.get(r.value.id) if isinstance(r.value, ast.Name) else None for r in returns]
    return values[0] if values[0] is not None and all(v == values[0] for v in values) else None


def _def_always_raises(
    lines: list[str], masked: list[list[str]], row: int, indent: int, starts: set[int]
) -> bool:
    """Recognize a Python-visible ``def`` whose first executable statement raises.

    Cython ``def`` methods frequently implement abstract protocol hooks with a
    docstring followed by an unconditional ``raise NotImplementedError``.  The
    return contract is then the language-level ``NoReturn`` regardless of the
    concrete exception class.  We intentionally accept only this lexical shape:
    docstrings/comments/blank lines may precede the raise, but conditionals,
    assignments, calls, or nested statements make the result data-dependent and
    therefore fail closed.
    """
    for j in range(row, len(lines)):
        visible = "".join(masked[j]).expandtabs(8)
        stripped = visible.strip()
        if not stripped:
            continue
        col = len(visible) - len(visible.lstrip())
        if j + 1 in starts and col <= indent:
            break
        # Only a direct statement in the function body can prove that every
        # execution path terminates.  Nested ``if: raise`` blocks are not
        # accepted because their condition may be false.
        if j + 1 not in starts or col != indent + 4:
            return False
        if stripped.startswith("raise") and (len(stripped) == 5 or stripped[5].isspace()):
            return True
        # The masked representation removes docstrings/comments.  Any other
        # executable direct statement before the first raise invalidates the
        # unconditional proof.
        return False
    return False


def _def_trivial_return(
    lines: list[str],
    masked: list[list[str]],
    row: int,
    indent: int,
    starts: set[int],
    class_types: dict[str, str] | None = None,
    callable_returns: dict[str, str] | None = None,
    qualified: str | None = None,
    module: str | None = None,
    parameter_types: dict[str, str] | None = None,
    scalar_parameters: set[str] | None = None,
) -> str | None:
    """Infer a branch-free ``def`` that immediately returns a literal/value.

    This deliberately handles only expressions whose Python type is fixed by
    syntax (``self``, ``None``/scalar literals, and literal containers).  A
    direct ``return`` is terminal, so later unreachable text is irrelevant;
    any statement or nested construct before it invalidates the proof.
    """
    for j in range(row, len(lines)):
        visible = "".join(masked[j]).expandtabs(8)
        stripped = visible.strip()
        if not stripped:
            continue
        col = len(visible) - len(visible.lstrip())
        if j + 1 in starts and col <= indent:
            return None
        if j + 1 not in starts or col != indent + 4:
            return None
        if not stripped.startswith("return") or (len(stripped) > 6 and not stripped[6].isspace()):
            return None
        expression = stripped[6:].strip()
        if expression == "self":
            return "Self"
        if expression in {"None", "True", "False"}:
            return "None" if expression == "None" else "bool"
        try:
            literal = ast.literal_eval(expression)
        except (ValueError, SyntaxError):
            literal = object()
        if isinstance(literal, list):
            return "list"
        if isinstance(literal, tuple):
            return "tuple"
        if isinstance(literal, dict):
            return "dict"
        if isinstance(literal, set):
            return "set"
        if isinstance(literal, bytes):
            return "bytes"
        if isinstance(literal, str):
            return "str"
        if isinstance(literal, bool):
            return "bool"
        if isinstance(literal, int):
            return "int"
        if isinstance(literal, float):
            return "float"
        if isinstance(literal, complex):
            return "complex"
        try:
            expression_node = ast.parse(expression, mode="eval").body
        except (SyntaxError, ValueError):
            return None
        if _fixed_scalar_expression(expression_node, scalar_parameters):
            return "bool"
        if isinstance(expression_node, ast.Call) and isinstance(expression_node.func, ast.Name):
            constructor = expression_node.func.id
            builtin_result = PYTHON_CALL_RETURNS.get(constructor)
            if builtin_result is not None:
                return builtin_result
            if class_types is not None:
                target = class_types.get(constructor)
                if target is not None:
                    return f"'{target}'"
        if isinstance(expression_node, ast.Name) and parameter_types is not None:
            return parameter_types.get(expression_node.id)
        if (
            isinstance(expression_node, ast.Call)
            and callable_returns is not None
            and qualified is not None
            and module is not None
        ):
            target_name: str | None = None
            function = expression_node.func
            if isinstance(function, ast.Attribute) and isinstance(function.value, ast.Name):
                if function.value.id in {"self", "cls"} and "." in qualified:
                    target_name = qualified.rsplit(".", 1)[0] + "." + function.attr
                elif function.value.id not in {"self", "cls"}:
                    target_name = module + "." + function.value.id + "." + function.attr
            elif isinstance(function, ast.Name):
                target_name = module + "." + function.id
            if target_name is not None:
                return callable_returns.get(target_name)
        if (
            isinstance(expression_node, ast.Attribute)
            and callable_returns is not None
            and qualified is not None
            and module is not None
        ):
            target_name = None
            owner = expression_node.value
            if isinstance(owner, ast.Name) and owner.id in {"self", "cls"} and "." in qualified:
                target_name = qualified.rsplit(".", 1)[0] + "." + expression_node.attr
            elif isinstance(owner, ast.Name) and owner.id not in {"self", "cls"}:
                target_name = module + "." + owner.id + "." + expression_node.attr
            if target_name is not None:
                return callable_returns.get(target_name)
        return None


def _def_implicit_none(
    lines: list[str], masked: list[list[str]], row: int, indent: int, starts: set[int]
) -> bool:
    """Prove an ordinary Python-visible ``def`` has no return value.

    Cython wrappers often perform an in-place operation and simply fall off
    the end.  Scan only the function's own lexical scope: nested functions may
    contain ``return`` statements without changing the outer function's
    implicit ``None`` result.  Any return/yield token in the outer scope makes
    the proof fail closed and is handled by the more precise rules instead.
    """
    nested_indent: int | None = None
    for j in range(row, len(lines)):
        visible = "".join(masked[j]).expandtabs(8)
        stripped = visible.strip()
        if not stripped:
            continue
        col = len(visible) - len(visible.lstrip())
        if j + 1 in starts and col <= indent:
            break
        if nested_indent is not None:
            if col <= nested_indent:
                nested_indent = None
            else:
                continue
        if j + 1 in starts and col == indent + 4 and (
            stripped.startswith("def ") or stripped.startswith("async def ")
        ):
            nested_indent = col
            continue
        if stripped.startswith("return") and (len(stripped) == 6 or stripped[6].isspace()):
            return False
        if stripped.startswith("yield") and (len(stripped) == 5 or stripped[5].isspace()):
            return False
        # A direct raise leaves no successful return path.  Do not mislabel
        # such helpers as implicit-None merely because they have no return
        # token; the dedicated NoReturn rule may still prove the stricter
        # docstring/raise shape above.
        if col == indent + 4 and stripped.startswith("raise") and (
            len(stripped) == 5 or stripped[5].isspace()
        ):
            return False
    return True


def _def_uniform_return(
    lines: list[str],
    masked: list[list[str]],
    row: int,
    indent: int,
    starts: set[int],
    class_types: dict[str, str] | None = None,
    callable_returns: dict[str, str] | None = None,
    qualified: str | None = None,
    module: str | None = None,
    parameter_types: dict[str, str] | None = None,
    scalar_parameters: set[str] | None = None,
) -> str | None:
    """Prove a Python-visible function whose explicit branches agree.

    This is intentionally structural: parse a pure-Python body, require all
    reachable paths to terminate (or expose the ordinary implicit ``None``),
    and classify every explicit return with the same literal/index contract
    used by the branch-free rule.  Cython declarations and dynamic expressions
    fail closed instead of being widened to a public base or ``Any``.
    """
    body: list[str] = []
    for j in range(row, len(lines)):
        visible = "".join(masked[j]).expandtabs(8)
        stripped = visible.strip()
        col = len(visible) - len(visible.lstrip())
        if j + 1 in starts and stripped and col <= indent:
            break
        # Ordinary Python imports are valid statements in a Python-visible
        # wrapper and do not affect the shape of a fixed return expression.
        # Reject only Cython-only declarations here; treating every ``from``
        # import as unsupported used to hide contracts such as
        # ``from ... import helper; return isinstance(...)``.
        if stripped.startswith(("cdef ", "cpdef ", "cimport ")) or re.match(
            r"^from\s+.*\bcimport\b", stripped
        ):
            return None
        expanded = lines[j].expandtabs(8)
        prefix = indent + 4
        if expanded.strip() and len(expanded) < prefix:
            return None
        body.append("    " + expanded[prefix:])
    if not body:
        return None
    try:
        function = ast.parse("def _probe():\n" + "".join(body)).body[0]
    except (SyntaxError, ValueError):
        return None
    if not isinstance(function, ast.FunctionDef):
        return None
    returns, has_yield = _returns(function.body)
    if has_yield or not returns:
        return None
    # A conditional raise is not an implicit-None path: it either terminates
    # or reaches another branch.  Keep this data-dependent shape unresolved.
    if any(isinstance(node, ast.Raise) for node in ast.walk(function)):
        return None
    fallthrough = _may_fall_through(function.body)
    if fallthrough and not _implicit_none_is_safe(function.body):
        return None
    inferred: list[str] = []
    for result in returns:
        expression = ast.unparse(result.value) if result.value is not None else "None"
        synthetic = ["    return " + expression + "\n"]
        synthetic_masked = [list(synthetic[0])]
        annotation = _def_trivial_return(
            synthetic,
            synthetic_masked,
            0,
            0,
            {1},
            class_types,
            callable_returns,
            qualified,
            module,
            parameter_types,
            scalar_parameters,
        )
        if annotation is None:
            return None
        inferred.append(annotation)
    if len(set(inferred)) != 1:
        return None
    if fallthrough:
        inferred.append("None")
    unique = list(dict.fromkeys(inferred))
    return unique[0] if len(unique) == 1 else " | ".join(unique)


def _def_header(
    lines: list[str], masked: list[list[str]], row: int
) -> tuple[str, int] | None:
    """Read a single- or multi-line Python-visible ``def`` header.

    Cython uses multiline signatures frequently.  We only accept a header
    whose closing colon is unambiguous (outside the parameter parentheses)
    and whose line has no inline body; all body proofs remain lexical and
    fail closed as before.
    """
    if row < 1 or row > len(lines):
        return None
    first = "".join(masked[row - 1]).expandtabs(8)
    stripped = first.lstrip()
    match = re.match(r"^(?:def|cpdef)\s+([A-Za-z_]\w*)\s*\(", stripped)
    if not match:
        return None
    depth = 0
    seen_open = False
    for index in range(row - 1, min(len(lines), row + 63)):
        visible = "".join(masked[index]).expandtabs(8)
        for position, character in enumerate(visible):
            if character == "(":
                depth += 1
                seen_open = True
            elif character == ")" and depth:
                depth -= 1
            elif character == ":" and seen_open and depth == 0:
                if visible[position + 1:].strip():
                    return None
                return match.group(1), index + 1
    return None


def _def_parameter_names(
    lines: list[str], masked: list[list[str]], row: int, body_row: int
) -> set[str]:
    """Extract simple Python parameter names from a Cython ``def`` header."""
    header = "".join("".join(masked[index]).expandtabs(8) for index in range(row - 1, body_row))
    start = header.find("(")
    end = header.rfind(")")
    if start < 0 or end <= start:
        return set()
    names: set[str] = set()
    for item in header[start + 1:end].split(","):
        item = item.strip().lstrip("*")
        if not item:
            continue
        item = item.split("=", 1)[0].strip()
        item = item.split(":", 1)[0].strip()
        words = item.split()
        if not words:
            continue
        candidate = words[-1]
        if re.fullmatch(r"[A-Za-z_]\w*", candidate) and candidate not in {"self", "cls"}:
            names.add(candidate)
    return names


def _def_scalar_parameter_names(
    lines: list[str], masked: list[list[str]], row: int, body_row: int
) -> set[str]:
    """Extract names declared as Cython scalar parameters from a ``def`` header.

    Python-visible Cython functions can expose C scalar arguments while their
    return annotation is omitted.  Comparisons over those arguments always
    produce Python ``bool`` values, unlike comparisons over arbitrary Sage
    objects whose rich-comparison overload may return a non-bool object.
    """
    header = "".join(
        "".join(masked[index]).expandtabs(8)
        for index in range(row - 1, body_row)
    )
    start = header.find("(")
    end = header.rfind(")")
    if start < 0 or end <= start:
        return set()
    scalar = re.compile(
        rf"^(?:\*{{0,2}}\s*)?(?:bint|float|double|{INTEGER})\s+"
        rf"(?P<name>[A-Za-z_]\w*)$"
    )
    names: set[str] = set()
    for item in header[start + 1:end].split(","):
        item = item.strip()
        match = scalar.fullmatch(item)
        if match:
            names.add(match.group("name"))
    return names


def _fixed_scalar_expression(node: ast.AST, scalar_parameters: set[str] | None) -> bool:
    """Return whether ``node`` is a comparison over C scalar expressions."""
    if not scalar_parameters or not isinstance(node, ast.Compare):
        return False

    def scalar_expression(value: ast.AST) -> bool:
        if isinstance(value, ast.Constant):
            return isinstance(value.value, (bool, int, float, complex))
        if isinstance(value, ast.Name):
            return value.id in scalar_parameters
        if isinstance(value, ast.UnaryOp) and isinstance(
            value.op, (ast.UAdd, ast.USub, ast.Invert)
        ):
            return scalar_expression(value.operand)
        if isinstance(value, ast.BinOp) and isinstance(
            value.op,
            (
                ast.Add,
                ast.Sub,
                ast.Mult,
                ast.Div,
                ast.FloorDiv,
                ast.Mod,
                ast.Pow,
                ast.LShift,
                ast.RShift,
                ast.BitAnd,
                ast.BitOr,
                ast.BitXor,
            ),
        ):
            return scalar_expression(value.left) and scalar_expression(value.right)
        return False

    return scalar_expression(node.left) and all(
        scalar_expression(comparator) for comparator in node.comparators
    )


def declarations(
    text: str,
    class_types: dict[str, str] | None = None,
    callable_returns: dict[str, str] | None = None,
    module: str | None = None,
    parameter_contracts: dict[str, dict[str, str]] | None = None,
    helper_returns: dict[str, str] | None = None,
    field_types: dict[str, dict[str, str]] | None = None,
    allow_parameter_identity: bool = False,
    indexed_parameter_names: dict[str, set[str]] | None = None,
) -> list[tuple[str, str, int]]:
    """Read supported headers at module/class scope after masking literals.

    Tokens protect against headers in docstrings and comments. Any unsupported
    lexical structure rejects the file. Indented declarations in functions,
    conditional compilation or extern blocks are deliberately not resolved.
    """
    lines = text.splitlines(keepends=True)
    masked = [list(line) for line in lines]
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    # Only tokenized statement starts may be headers; continuation-line text
    # (including f-string content) cannot introduce a declaration.
    starts = set()
    at_start = True
    for tok in tokens:
        if tok.type in (tokenize.STRING, tokenize.COMMENT):
            for row in range(tok.start[0], tok.end[0] + 1):
                start = tok.start[1] if row == tok.start[0] else 0
                end = tok.end[1] if row == tok.end[0] else len(masked[row - 1])
                for col in range(start, end):
                    if masked[row - 1][col] not in '\r\n':
                        masked[row - 1][col] = ' '
        if tok.type == tokenize.NEWLINE:
            at_start = True
        elif tok.type not in (tokenize.INDENT, tokenize.DEDENT, tokenize.NL, tokenize.COMMENT, tokenize.ENCODING):
            if at_start:
                starts.add(tok.start[0])
            at_start = False
    result = []
    scopes: list[tuple[int, str]] = []
    for row, chars in enumerate(masked, 1):
        if row not in starts:
            continue
        line = ''.join(chars).expandtabs(8)
        stripped = line.lstrip()
        if not stripped.strip():
            continue
        indent = len(line) - len(stripped)
        while scopes and indent <= scopes[-1][0]:
            scopes.pop()
        # A class body must use the usual four-space Cython indentation. This
        # deliberate restriction avoids attributing nested control-flow code
        # to its enclosing class.
        direct = indent == (scopes[-1][0] + 4 if scopes else 0)
        cls = CLASS.match(stripped) if direct else None
        if cls:
            scopes.append((indent, cls.group(1)))
            continue
        decl = DECLARATION.match(stripped) if direct else None
        if decl:
            ctype = decl.group('type')
            annotation = scalar_type(ctype)
            if annotation is None and class_types is not None:
                target = class_types.get(ctype)
                if target is not None:
                    annotation = f"'{target}'"
            if annotation is not None:
                result.append(('.'.join([s[1] for s in scopes] + [decl.group('name')]), annotation, row))
        elif direct:
            # Only complete single-line def headers; nested definitions are
            # excluded by the same module/class scope guard as cpdef.
            header = _def_header(lines, masked, row)
            previous = next((''.join(masked[j]).strip() for j in range(row-2, -1, -1) if ''.join(masked[j]).strip()), '')
            if header:
                function_name, body_row = header
                qualified = '.'.join([s[1] for s in scopes] + [function_name])
                lookup_qualified = f"{module}.{qualified}" if module else qualified
                parameter_types = parameter_contracts.get(lookup_qualified) if parameter_contracts else None
                scalar_parameters = _def_scalar_parameter_names(
                    lines, masked, row, body_row
                )
                if _def_always_raises(lines, masked, body_row, indent, starts):
                    result.append((qualified, 'NoReturn', row))
                elif (annotation := _def_uniform_return(
                    lines, masked, body_row, indent, starts, class_types,
                    callable_returns, lookup_qualified, module,
                    parameter_types,
                    scalar_parameters,
                )):
                    result.append((qualified, annotation, row))
                elif _def_implicit_none(lines, masked, body_row, indent, starts):
                    result.append((qualified, 'None', row))
                elif (annotation := _def_trivial_return(
                    lines, masked, body_row, indent, starts, class_types,
                    callable_returns, lookup_qualified, module,
                    parameter_types,
                    scalar_parameters,
                )):
                    result.append((qualified, annotation, row))
                elif not previous.startswith('@'):
                    owner_qualified = lookup_qualified.rsplit('.', 1)[0] if '.' in lookup_qualified else None
                    parameter_names = (
                        _def_parameter_names(lines, masked, row, body_row)
                        if allow_parameter_identity
                        else set()
                    )
                    if indexed_parameter_names and lookup_qualified in indexed_parameter_names:
                        parameter_names.difference_update(
                            indexed_parameter_names[lookup_qualified]
                        )
                    annotation = _def_lexical_return(
                        lines, masked, body_row, indent, starts,
                        class_types, helper_returns, callable_returns,
                        (field_types or {}).get(owner_qualified or ''),
                        owner_qualified,
                        parameter_names,
                    )
                    if annotation is None:
                        annotation = local_return(lines, masked, body_row, indent, starts)
                    if annotation:
                        result.append((qualified, annotation, row))
    return result


def infer(root: Path, index: Path | None = None) -> tuple[dict[str, str], list[dict]]:
    evidence = []
    types: dict[str, set[str]] = {}
    class_types = _unique_class_types(index)
    callable_returns = _unique_callable_returns(index)
    parameter_contracts = _unique_parameter_contracts(index)
    indexed_parameter_names = _indexed_parameter_names(index)
    indexed_children = _index_class_children(index)
    sources: list[tuple[Path, bytes, str, str]] = []
    field_types: dict[str, dict[str, str]] = {}
    for path in sorted(p for p in root.rglob('*') if p.suffix in {'.pyx', '.pxd'}):
        data = path.read_bytes()
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            continue
        parts = list(path.relative_to(root).with_suffix('').parts)
        if parts[-1] == '__init__':
            parts.pop()
        module = '.'.join([root.name, *parts])
        sources.append((path, data, text, module))
        for owner, fields in _cdef_field_types(text, module, class_types, indexed_children).items():
            field_types.setdefault(owner, {}).update(fields)
    global_helper_returns = _global_helper_returns(sources, class_types)
    for path, data, text, module in sources:
        helper_returns = _cdef_helper_returns(text, class_types)
        helper_returns.update(global_helper_returns)
        for name, annotation, line in declarations(
            text, class_types, callable_returns, module, parameter_contracts,
            helper_returns, field_types,
            True,
            indexed_parameter_names,
        ):
            # A PXD declaration without an explicit Cython return type is an
            # interface signature, not a Python function body.  The lexical
            # fallback in ``declarations`` can otherwise interpret the
            # declaration as an empty ``def`` and emit ``None`` (or
            # ``NoReturn``), which conflicts with the real PYX implementation
            # and hides a proven body contract.  Keep explicitly typed
            # ``cpdef`` declarations (including ``void``) while ignoring
            # only this untyped interface form.
            if path.suffix == ".pxd":
                source_line = text.splitlines()[line - 1].strip()
                if source_line.startswith(("cpdef ", "cdef ")) and not DECLARATION.match(source_line):
                    continue
            qualified = module + '.' + name
            types.setdefault(qualified, set()).add(annotation)
            evidence.append({'qualifiedName': qualified, 'returnType': annotation,
                             'source': path.relative_to(root).as_posix(), 'line': line,
                             'sha256': hashlib.sha256(data).hexdigest(),
                             'rule': ('def-always-raises' if annotation == 'NoReturn' else
                                      'def-trivial-return' if annotation in {'Self', 'None', 'bool', 'bytes', 'complex', 'dict', 'float', 'int', 'list', 'set', 'str', 'tuple'} else
                                      'explicit-cpdef-scalar-wrapper' if text.splitlines()[line-1].lstrip().startswith('cpdef ') else
                                      'all-returns-c-scalar-local')})
    return {name: next(iter(values)) for name, values in types.items() if len(values) == 1}, evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--index', type=Path, help='Generated Sage index used to resolve unique extension classes.')
    args = parser.parse_args()
    contracts, evidence = infer(args.source_root, args.index.resolve() if args.index else None)
    args.output.write_text(json.dumps(contracts, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    args.evidence.write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'contracts': len(contracts), 'declarations': len(evidence)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
