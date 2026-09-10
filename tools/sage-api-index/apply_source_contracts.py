#!/usr/bin/env python3
"""Apply verified source-return contracts to missing Sage stub returns.

The input is a qualified-name map produced by ``infer_source_returns.py``.
Only absent return annotations are edited; existing contracts and overloads
remain authoritative.  This makes the pass idempotent and prevents a broad
base type from replacing a concrete one.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

from annotate_stubs import (
    _function_header_colon,
    _line_offsets,
    ensure_typing_name,
    ensure_type_variables,
)


_BUILTINS = {
    "None", "bool", "bytes", "bytearray", "complex", "dict", "float",
    "frozenset", "int", "list", "memoryview", "object", "range", "set",
    "slice", "str", "tuple", "type", "NoReturn",
}
_STRUCTURAL_SUFFIXES = ("_base", "_generic", "_element", "_parent", "_factory")
_INDEX_CHILDREN_CACHE: dict[str, dict[str, set[str]]] = {}
_PARAMETER_IDENTITY_PREFIX = "@parameter:"
_CONSTRUCTOR_PARAMETER_PREFIX = "@constructor_parameter:"
_PARAMETER_IDENTITY_TYPEVAR = "_SageIdentityT"
_STORED_PARAMETER_TYPEVAR_PREFIX = "_SageStored"


def _is_concrete_sage_path(
    value: str,
    *,
    allow_generic: bool = False,
    indexed_children: dict[str, set[str]] | None = None,
) -> bool:
    """Accept a Sage class only when its indexed hierarchy proves it is a leaf.

    Structural suffixes are a useful fail-closed default for source maps that
    have no class index.  When a generated index is available, however, a
    source-proven class with one of those suffixes is still a valid concrete
    implementation if no indexed class derives from it.  This distinguishes
    real leaves such as ``QuarticCurve_generic`` from dispatch bases such as
    ``PolynomialSequence_generic`` without maintaining a class-name list.
    """
    if not value.startswith("sage."):
        return False
    final = value.rsplit(".", 1)[-1].lower()
    if final.endswith("_generic"):
        if indexed_children is not None and value not in indexed_children:
            return True
        return allow_generic
    if any(final.endswith(suffix) for suffix in _STRUCTURAL_SUFFIXES):
        return indexed_children is not None and value not in indexed_children
    return True


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _index_class_children(index: Path | None) -> dict[str, set[str]]:
    if index is None:
        return {}
    key = str(index.resolve())
    cached = _INDEX_CHILDREN_CACHE.get(key)
    if cached is not None:
        return cached
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
    _INDEX_CHILDREN_CACHE[key] = children
    return children


def _valid_annotation(
    annotation: str,
    index: Path | None = None,
    *,
    source_proven: bool = False,
) -> bool:
    children = _index_class_children(index)

    def valid_sage_string(value: str, *, allow_generic: bool = False) -> bool:
        if value.startswith("sage.type_contracts.") and re.fullmatch(
            r"sage\.type_contracts\.[A-Za-z_][A-Za-z0-9_]*Element\[Self\]", value
        ):
            return True
        if not value.startswith("sage."):
            return False
        # A class with indexed subclasses is a dispatch/base node, not a
        # final return type.  Keep the rejection data-driven rather than
        # relying on a class-name suffix list.
        if value in children and not source_proven:
            return False
        if source_proven and value.rsplit(".", 1)[-1].lower().endswith("_base"):
            # A source-proven factory/coercion hook may intentionally return
            # a named ``*_base`` implementation even when subclasses exist.
            # Keep ``*_generic`` dispatch classes fail-closed: those are
            # commonly abstract protocols rather than the runtime result.
            return True
        return _is_concrete_sage_path(
            value,
            allow_generic=allow_generic,
            indexed_children=children if index is not None else None,
        )

    if annotation in _BUILTINS or annotation in {"Self", "Iterator"}:
        return True
    # A quoted PEP 604 union also starts and ends with a quote.  Only use the
    # fast path for one literal; unions must go through the AST validator.
    if annotation.startswith("'sage.") and annotation.endswith("'") and annotation.count("'") == 2:
        return valid_sage_string(annotation[1:-1])
    try:
        node = ast.parse(annotation, mode="eval").body
    except SyntaxError:
        return False

    def flatten_union(node: ast.AST) -> list[ast.AST]:
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return flatten_union(node.left) + flatten_union(node.right)
        return [node]

    def valid(node: ast.AST, *, allow_generic: bool = False) -> bool:
        if isinstance(node, ast.Name):
            return node.id in _BUILTINS or node.id in {"Self", "Iterator"}
        if isinstance(node, ast.Constant):
            # ``None`` is represented as an AST constant (rather than a
            # Name), including when it appears in a proven ``T | None`` arm.
            return node.value is None or (
                isinstance(node.value, str)
                and valid_sage_string(node.value, allow_generic=allow_generic)
            )
        # Source inference may prove a finite set of successful branch
        # shapes.  Preserve that exact PEP 604 union instead of dropping the
        # contract merely because it has more than one arm.
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            arms = flatten_union(node)
            sage_paths = [
                arm.value for arm in arms
                if isinstance(arm, ast.Constant)
                and isinstance(arm.value, str)
                and arm.value.startswith("sage.")
            ]
            has_non_generic_leaf = any(
                not path.rsplit(".", 1)[-1].lower().endswith("_generic")
                for path in sage_paths
            )
            has_type_factory = any(
                isinstance(arm, ast.Name) and arm.id == "type" for arm in arms
            )
            allow_union_generic = has_non_generic_leaf or has_type_factory
            return all(valid(arm, allow_generic=allow_union_generic) for arm in arms)
        if isinstance(node, ast.Subscript):
            return valid(node.value, allow_generic=allow_generic) and all(
                valid(item, allow_generic=allow_generic)
                for item in (node.slice.elts if isinstance(node.slice, ast.Tuple) else (node.slice,))
            )
        return False

    return valid(node)


def _unknown_names(index: Path | None) -> set[str] | None:
    if index is None:
        return None
    payload = json.loads(index.read_text(encoding="utf-8"))
    return {
        entry["qualifiedName"]
        for entry in payload.get("entries", [])
        if entry.get("kind") in {"FUNCTION", "METHOD", "PROPERTY"}
        and any(signature.get("returnType", {}).get("state") == "UNKNOWN" for signature in entry.get("signatures", []))
    }


def _is_overload(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        (isinstance(decorator, ast.Name) and decorator.id == "overload")
        or (isinstance(decorator, ast.Attribute) and decorator.attr == "overload")
        for decorator in node.decorator_list
    )


def _header_colon(text: str, offsets: list[int], node: ast.ClassDef) -> int | None:
    """Locate the top-level colon in one class header without reformatting it."""
    start = offsets[node.lineno - 1] + node.col_offset
    depth = 0
    quote: str | None = None
    escaped = False
    for offset in range(start, len(text)):
        character = text[offset]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "([{" :
            depth += 1
        elif character in ")]}":
            depth -= 1
        elif character == ":" and depth == 0:
            return offset
        elif character == "\n" and depth == 0:
            return None
    return None


def _stored_parameter_typevar(owner: str, parameter: str) -> str:
    """Build a module-local TypeVar name tied to one class constructor field."""
    owner_part = re.sub(r"[^A-Za-z0-9_]", "", owner) or "Value"
    parameter_part = re.sub(r"[^A-Za-z0-9_]", "", parameter.title()) or "Value"
    return f"{_STORED_PARAMETER_TYPEVAR_PREFIX}{owner_part}{parameter_part}T"


def _class_generic_insertion(
    text: str, offsets: list[int], node: ast.ClassDef, typevar: str
) -> tuple[int, str] | None:
    """Return a safe text insertion that makes an ordinary class ``Generic[T]``.

    Existing parameterized/metadata-bearing class headers are deliberately
    rejected.  Combining an inferred parameter with a hand-written generic
    hierarchy or metaclass requires class-specific variance/constructor
    analysis, so accepting it here would overstate the source proof.
    """
    colon = _header_colon(text, offsets, node)
    if colon is None:
        return None
    header_start = offsets[node.lineno - 1] + node.col_offset
    header = text[header_start:colon]
    if re.search(r"\b(?:typing\.)?Generic\s*\[", header):
        return None
    if "metaclass=" in header or any(isinstance(base, ast.Subscript) for base in node.bases):
        return None
    trailing = len(header) - len(header.rstrip())
    insertion = colon - trailing
    if header.rstrip().endswith(")"):
        return insertion - 1, f", Generic[{typevar}]"
    return insertion, f"(Generic[{typevar}])"


def apply(stub_root: Path, contracts: dict[str, str], index: Path | None = None) -> list[str]:
    only_unknown = _unknown_names(index)
    edits: list[tuple[Path, int, str, str]] = []
    identity_edits: list[tuple[Path, int, int, str, str]] = []
    # A getter can return a constructor-stored value without taking that
    # value as its own argument.  Keep the owner/class header edit separate
    # from the method edit: one ``Generic[T]`` parameter may serve several
    # getters of the same stored field.
    stored_class_fields: dict[tuple[Path, int], dict[str, tuple[int, str]]] = {}
    stored_class_nodes: dict[tuple[Path, int], tuple[str, list[int], ast.ClassDef]] = {}
    stored_return_edits: list[tuple[Path, int, str, str, str]] = []
    for path in sorted(stub_root.rglob("*.pyi")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path), type_comments=True)
        except SyntaxError:
            continue
        offsets = _line_offsets(text)
        module = _module_name(path, stub_root)

        def visit(
            node: ast.AST,
            owner: str | None = None,
            owner_node: ast.ClassDef | None = None,
        ) -> None:
            if isinstance(node, ast.ClassDef):
                qualified_owner = (
                    f"{module}.{node.name}"
                    if owner is None
                    else f"{owner}.{node.name}"
                )
                for child in node.body:
                    visit(child, qualified_owner, node)
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                annotation = contracts.get(qualified)
                # Identity contracts may be one arm of a finite union (for
                # example ``Self | @parameter:other | list``).  Treat the
                # marker structurally rather than requiring it to be the
                # first arm; otherwise the source analyzer's proven
                # parameter relationship is silently discarded whenever an
                # alternate concrete branch is present.
                identity_arms = [
                    part.strip()
                    for part in annotation.split("|")
                    if part.strip().startswith(
                        (_PARAMETER_IDENTITY_PREFIX, _CONSTRUCTOR_PARAMETER_PREFIX)
                    )
                ] if isinstance(annotation, str) else []
                if (
                    not _is_overload(node)
                    and node.returns is None
                    and len(identity_arms) == 1
                    and (only_unknown is None or qualified in only_unknown)
                ):
                    identity_arm = identity_arms[0]
                    stored_constructor_parameter = identity_arm.startswith(
                        _CONSTRUCTOR_PARAMETER_PREFIX
                    )
                    payload = identity_arm[
                        len(
                            _CONSTRUCTOR_PARAMETER_PREFIX
                            if stored_constructor_parameter
                            else _PARAMETER_IDENTITY_PREFIX
                        ):
                    ]
                    # Source inference may append a proven alternate arm
                    # (for example ``@parameter:value |
                    # 'sage.type_contracts.ParentElement[Self]'`` when a
                    # parent factory returns the input unchanged or creates
                    # a fresh element).  Strip separator whitespace and keep
                    # every such arm in the published return contract; the
                    # old ``partition`` implementation accidentally retained
                    # a trailing space in the parameter name and dropped all
                    # non-``None`` alternatives, causing these safe source
                    # contracts to be silently ignored.
                    parts = [part.strip() for part in payload.split("|")]
                    parameter_name = parts[0] if parts else ""
                    extra_arms = [
                        part.strip()
                        for part in annotation.split("|")
                        if part.strip()
                        and not part.strip().startswith(
                            (_PARAMETER_IDENTITY_PREFIX, _CONSTRUCTOR_PARAMETER_PREFIX)
                        )
                    ]
                    parameter = next(
                        (
                            argument
                            for argument in (
                                *node.args.posonlyargs,
                                *node.args.args,
                                *node.args.kwonlyargs,
                            )
                            if argument.arg == parameter_name
                        ),
                        None,
                    )
                    colon = _function_header_colon(text, offsets, node)
                    if parameter is not None and colon is not None:
                        # If the stub already gives this parameter a precise
                        # type, the source proof is a direct identity and we
                        # can publish that exact type without introducing a
                        # synthetic TypeVar.  This is especially useful for
                        # generated Sage properties/methods whose constructor
                        # parameter was recovered by stubgen but whose return
                        # annotation was omitted.  Keep the TypeVar path for
                        # genuinely untyped parameters so call-site inference
                        # remains polymorphic.
                        parameter_expression = (
                            ast.unparse(parameter.annotation)
                            if parameter.annotation is not None
                            else None
                        )
                        if parameter_expression and _valid_annotation(
                            parameter_expression, index, source_proven=True
                        ):
                            return_annotation = " | ".join(
                                [parameter_expression, *extra_arms]
                            )
                            edits.append((path, colon, return_annotation, qualified))
                        elif parameter.annotation is None:
                            parameter_offset = offsets[parameter.end_lineno - 1] + parameter.end_col_offset
                            return_annotation = " | ".join(
                                [_PARAMETER_IDENTITY_TYPEVAR, *extra_arms]
                            )
                            identity_edits.append((path, parameter_offset, colon, return_annotation, qualified))
                    elif (
                        parameter is None
                        and stored_constructor_parameter
                        and colon is not None
                        and owner is not None
                        and owner_node is not None
                        and all(
                            _valid_annotation(arm, index, source_proven=True)
                            for arm in extra_arms
                        )
                    ):
                        # ``return self._field`` is an exact constructor
                        # dependency when the source pass traced ``_field``
                        # back to ``__init__(..., field, ...)``.  Publish it
                        # as a class type parameter so callers retain the
                        # concrete input class instead of receiving a base or
                        # an unbound method-local TypeVar.
                        initializer = next(
                            (
                                child
                                for child in owner_node.body
                                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                                and child.name == "__init__"
                                and not _is_overload(child)
                            ),
                            None,
                        )
                        stored_parameter = next(
                            (
                                argument
                                for argument in (
                                    (*initializer.args.posonlyargs, *initializer.args.args, *initializer.args.kwonlyargs)
                                    if initializer is not None else ()
                                )
                                if argument.arg == parameter_name
                            ),
                            None,
                        )
                        typevar = _stored_parameter_typevar(owner, parameter_name)
                        generic_insertion = _class_generic_insertion(
                            text, offsets, owner_node, typevar
                        )
                        if (
                            initializer is not None
                            and stored_parameter is not None
                            and stored_parameter.annotation is None
                            and generic_insertion is not None
                        ):
                            class_key = (path, owner_node.lineno)
                            stored_class_fields.setdefault(class_key, {}).setdefault(
                                parameter_name,
                                (
                                    offsets[stored_parameter.end_lineno - 1]
                                    + stored_parameter.end_col_offset,
                                    typevar,
                                ),
                            )
                            stored_class_nodes.setdefault(
                                class_key, (text, offsets, owner_node)
                            )
                            return_annotation = " | ".join(
                                [typevar, *extra_arms]
                            )
                            stored_return_edits.append(
                                (path, colon, return_annotation, qualified, typevar)
                            )
                    return
                if (
                    node.returns is None
                    and annotation
                    and not (
                        isinstance(annotation, str)
                        and annotation.startswith(_PARAMETER_IDENTITY_PREFIX)
                        and _is_overload(node)
                    )
                    and _valid_annotation(annotation, index, source_proven=True)
                ):
                    if only_unknown is None or qualified in only_unknown:
                        colon = _function_header_colon(text, offsets, node)
                        if colon is not None:
                            edits.append((path, colon, annotation, qualified))
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner, owner_node)

        for node in tree.body:
            visit(node)

    # Apply ordinary and identity contracts in one offset-ordered pass.  The
    # offsets are computed against the same original file text; applying the
    # two batches separately used to shift the second batch and could corrupt
    # a function header (for example ``def _meet_`` becoming ``def _me:``).
    by_path: dict[Path, list[tuple[int, str, str, str]]] = {}
    for path, offset, annotation, qualified in edits:
        by_path.setdefault(path, []).append((offset, f" -> {annotation}", qualified, annotation))
    for path, parameter_offset, colon, annotation, qualified in identity_edits:
        by_path.setdefault(path, []).append(
            (parameter_offset, f": {_PARAMETER_IDENTITY_TYPEVAR}", qualified, annotation)
        )
        by_path.setdefault(path, []).append((colon, f" -> {annotation}", qualified, annotation))
    stored_typevars: dict[Path, set[str]] = {}
    for class_key, fields in stored_class_fields.items():
        path, _ = class_key
        original_text, original_offsets, class_node = stored_class_nodes[class_key]
        ordered_fields = [fields[name] for name in sorted(fields)]
        typevars = tuple(typevar for _, typevar in ordered_fields)
        generic_insertion = _class_generic_insertion(
            original_text, original_offsets, class_node, ", ".join(typevars)
        )
        # This was pre-checked before the getter edit was recorded.  Keep the
        # guard here because the final edit is assembled after every stub has
        # been scanned and must never emit a malformed class header.
        if generic_insertion is None:
            continue
        header_offset, header_insertion = generic_insertion
        by_path.setdefault(path, []).append(
            (header_offset, header_insertion, "", ", ".join(typevars))
        )
        for parameter_offset, typevar in ordered_fields:
            by_path.setdefault(path, []).append((parameter_offset, f": {typevar}", "", typevar))
            stored_typevars.setdefault(path, set()).add(typevar)
    for path, colon, annotation, qualified, typevar in stored_return_edits:
        by_path.setdefault(path, []).append((colon, f" -> {annotation}", qualified, annotation))
        stored_typevars.setdefault(path, set()).add(typevar)
    changed: list[str] = []
    for path, path_edits in by_path.items():
        text = path.read_text(encoding="utf-8")
        for offset, insertion, _, _ in sorted(path_edits, key=lambda item: item[0], reverse=True):
            text = text[:offset] + insertion + text[offset:]
        path.write_text(text, encoding="utf-8")
        annotations = [annotation for _, _, _, annotation in path_edits]
        for marker, typing_name in (("Self", "Self"), ("Iterator", "Iterator")):
            if any(re.search(rf"\b{marker}\b", annotation) for annotation in annotations):
                ensure_typing_name(path, typing_name)
        if any(annotation.startswith(_PARAMETER_IDENTITY_TYPEVAR) for annotation in annotations):
            ensure_type_variables(path, (_PARAMETER_IDENTITY_TYPEVAR,))
        if path in stored_typevars:
            ensure_typing_name(path, "Generic")
            ensure_type_variables(path, tuple(sorted(stored_typevars[path])))
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
        changed.extend(qualified for _, _, qualified, _ in path_edits if qualified)
    # A previous batch may have already written a ``NoReturn`` annotation.
    # Keep its typing import synchronized even when this invocation is
    # otherwise idempotent and performs no new edits.
    for path in sorted(stub_root.rglob("*.pyi")):
        text = path.read_text(encoding="utf-8")
        if "-> NoReturn" in text:
            ensure_typing_name(path, "NoReturn")
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stub-root", type=Path, required=True)
    parser.add_argument("--contracts", type=Path, required=True)
    parser.add_argument("--index", type=Path, help="Optional generated index; apply only to UNKNOWN callables.")
    args = parser.parse_args()
    contracts = json.loads(args.contracts.read_text(encoding="utf-8"))
    changed = apply(args.stub_root.resolve(), contracts, args.index.resolve() if args.index else None)
    print(json.dumps({"contracts": len(contracts), "applied": len(changed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
