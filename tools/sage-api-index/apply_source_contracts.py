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
from pathlib import Path

from annotate_stubs import _function_header_colon, _line_offsets, ensure_typing_name


_BUILTINS = {
    "None", "bool", "bytes", "bytearray", "complex", "dict", "float",
    "frozenset", "int", "list", "memoryview", "object", "range", "set",
    "slice", "str", "tuple", "type", "NoReturn",
}
_STRUCTURAL_SUFFIXES = ("_base", "_generic", "_element", "_parent", "_factory")


def _is_concrete_sage_path(value: str, *, allow_generic: bool = False) -> bool:
    """Accept only leaf-like Sage classes, never public structural bases."""
    if not value.startswith("sage."):
        return False
    final = value.rsplit(".", 1)[-1].lower()
    if final.endswith("_generic"):
        return allow_generic
    return not any(final.endswith(suffix) for suffix in _STRUCTURAL_SUFFIXES)


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _valid_annotation(annotation: str) -> bool:
    if annotation in _BUILTINS or annotation in {"Self", "Iterator"}:
        return True
    if annotation.startswith("'sage.") and annotation.endswith("'"):
        return _is_concrete_sage_path(annotation[1:-1])
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
                and _is_concrete_sage_path(node.value, allow_generic=allow_generic)
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


def apply(stub_root: Path, contracts: dict[str, str], index: Path | None = None) -> list[str]:
    only_unknown = _unknown_names(index)
    edits: list[tuple[Path, int, str, str]] = []
    for path in sorted(stub_root.rglob("*.pyi")):
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(path), type_comments=True)
        except SyntaxError:
            continue
        offsets = _line_offsets(text)
        module = _module_name(path, stub_root)

        def visit(node: ast.AST, owner: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    visit(child, f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}")
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                annotation = contracts.get(qualified)
                if not _is_overload(node) and node.returns is None and annotation and _valid_annotation(annotation):
                    if only_unknown is None or qualified in only_unknown:
                        colon = _function_header_colon(text, offsets, node)
                        if colon is not None:
                            edits.append((path, colon, annotation, qualified))
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)

        for node in tree.body:
            visit(node)

    by_path: dict[Path, list[tuple[int, str, str]]] = {}
    for path, offset, annotation, qualified in edits:
        by_path.setdefault(path, []).append((offset, annotation, qualified))
    changed: list[str] = []
    for path, path_edits in by_path.items():
        text = path.read_text(encoding="utf-8")
        for offset, annotation, _ in sorted(path_edits, reverse=True):
            text = text[:offset] + f" -> {annotation}" + text[offset:]
        path.write_text(text, encoding="utf-8")
        for marker, typing_name in (("Self", "Self"), ("Iterator", "Iterator")):
            if any(annotation == marker or annotation.startswith(marker + "[") for _, annotation, _ in path_edits):
                ensure_typing_name(path, typing_name)
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
        changed.extend(qualified for _, _, qualified in path_edits)
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
