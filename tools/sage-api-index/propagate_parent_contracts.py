#!/usr/bin/env python3
"""Propagate exact contracts through a unique parent implementation.

This pass is intentionally data-driven: it reads the generated class graph and
method contracts, then fills only a missing child return when the nearest
parent layer has one unambiguous, safe contract.  It does not contain a Sage
method/class allow-list.  Broad parent classes are rejected structurally (a
returned Sage class must be a leaf in the indexed inheritance graph), while
receiver-dependent ``Self`` and exact builtin/container contracts are kept.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from annotate_stubs import _function_header_colon, _line_offsets, ensure_typing_name


_BUILTINS = {
    "None",
    "bool",
    "bytes",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "set",
    "str",
    "tuple",
}
_SPECIAL = {"Self", "typing.Self", "Iterator", "typing.Iterator", "NoReturn", "typing.NoReturn"}
_STRUCTURAL_SUFFIXES = ("_base", "_generic", "_element", "_parent", "_factory")


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_overload(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return any(
        (isinstance(decorator, ast.Name) and decorator.id == "overload")
        or (isinstance(decorator, ast.Attribute) and decorator.attr == "overload")
        for decorator in node.decorator_list
    )


def _single_return(entry: dict[str, Any]) -> str | None:
    signatures = entry.get("signatures")
    if not isinstance(signatures, list) or not signatures:
        return None
    expressions: set[str] = set()
    for signature in signatures:
        if not isinstance(signature, dict):
            return None
        return_type = signature.get("returnType")
        if not isinstance(return_type, dict) or return_type.get("state") != "KNOWN":
            return None
        expression = return_type.get("expression")
        if not isinstance(expression, str) or not expression:
            return None
        expressions.add(expression)
    return expressions.pop() if len(expressions) == 1 else None


def _normalise_special(expression: str) -> str:
    return (
        expression.replace("typing.Self", "Self")
        .replace("typing.Iterator", "Iterator")
        .replace("typing.NoReturn", "NoReturn")
    )


def _safe_expression(
    expression: str,
    classes: dict[str, dict[str, Any]],
    children: dict[str, set[str]],
    *,
    allow_generic: bool = False,
) -> bool:
    """Accept exact values, receiver-dependent values, or leaf Sage classes."""

    expression = expression.strip()
    if expression in _BUILTINS or expression in _SPECIAL:
        return True
    if " | " in expression:
        parts = [part.strip() for part in expression.split(" | ")]
        sage_parts = [part for part in parts if part.startswith("sage.")]
        has_non_generic_leaf = any(
            not part.rsplit(".", 1)[-1].lower().endswith("_generic")
            for part in sage_parts
        )
        has_type_factory = "type" in parts
        # A generic implementation is safe to preserve only as one arm of an
        # already-proven finite union with a concrete implementation (or a
        # class-object factory).  A standalone generic remains structural.
        allow_union_generic = has_non_generic_leaf or has_type_factory
        return bool(parts) and all(
            _safe_expression(
                part,
                classes,
                children,
                allow_generic=allow_union_generic,
            )
            for part in parts
        )
    # Generic public base contracts (ParentElement[Self], CodomainElement[...])
    # are deliberately not copied as a final child type.
    if "[" in expression or not expression.startswith("sage."):
        return False
    class_entry = classes.get(expression)
    if class_entry is None:
        return False
    final = expression.rsplit(".", 1)[-1].lower()
    if final.endswith("_generic"):
        return allow_generic
    return not children.get(expression) and not final.endswith(_STRUCTURAL_SUFFIXES)


def _annotation(expression: str) -> tuple[str, str | None]:
    """Render an index expression for a .pyi annotation and its typing import."""

    expression = _normalise_special(expression)
    if "sage." in expression:
        # Existing curated stubs use a single forward-reference string for
        # unions that contain Sage classes, including mixed builtin unions.
        return f"'{expression}'", None
    if expression == "Iterator":
        return expression, "Iterator"
    if expression == "Self":
        return expression, "Self"
    if expression == "NoReturn":
        return expression, "NoReturn"
    if "Self" in expression:
        return expression, "Self"
    if "Iterator" in expression:
        return expression, "Iterator"
    return expression, None


def _ancestors(classes: dict[str, dict[str, Any]], owner: str):
    seen: set[str] = set()
    frontier = list(classes.get(owner, {}).get("parents", []))
    while frontier:
        current: list[str] = []
        next_frontier: list[str] = []
        for parent in frontier:
            if parent in seen:
                continue
            seen.add(parent)
            current.append(parent)
            next_frontier.extend(classes.get(parent, {}).get("parents", []))
        if current:
            yield current
        frontier = next_frontier


def infer_parent_contracts(index: Path) -> dict[str, str]:
    payload = json.loads(index.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    classes = {
        entry["qualifiedName"]: entry
        for entry in entries
        if entry.get("kind") == "CLASS" and isinstance(entry.get("qualifiedName"), str)
    }
    children: dict[str, set[str]] = defaultdict(set)
    for qualified_name, entry in classes.items():
        for parent in entry.get("parents", []):
            if isinstance(parent, str):
                children[parent].add(qualified_name)

    methods: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if entry.get("kind") not in {"METHOD", "PROPERTY"}:
            continue
        qualified_name = entry.get("qualifiedName")
        if not isinstance(qualified_name, str) or "." not in qualified_name:
            continue
        owner, name = qualified_name.rsplit(".", 1)
        methods[(owner, name)].append(entry)

    contracts: dict[str, str] = {}
    for (owner, name), entries_for_method in methods.items():
        if not any(
            signature.get("returnType", {}).get("state") == "UNKNOWN"
            for entry in entries_for_method
            for signature in entry.get("signatures", [])
            if isinstance(signature, dict)
        ):
            continue
        for layer in _ancestors(classes, owner):
            candidate_values: list[str] = []
            for parent in layer:
                for parent_entry in methods.get((parent, name), []):
                    value = _single_return(parent_entry)
                    if value is not None:
                        candidate_values.append(value)
            if not candidate_values:
                continue
            if len(set(candidate_values)) == 1:
                expression = candidate_values[0]
                if _safe_expression(expression, classes, children):
                    contracts[f"{owner}.{name}"] = expression
            # A nearer layer exists but is ambiguous or broad: never fall
            # through to a more distant implementation.
            break
    return contracts


def apply(stub_root: Path, contracts: dict[str, str]) -> list[str]:
    edits: list[tuple[Path, int, str, str, str | None]] = []
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
                qualified_owner = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                for child in node.body:
                    visit(child, qualified_owner)
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                expression = contracts.get(qualified)
                if expression and node.returns is None and not _is_overload(node):
                    rendered, typing_name = _annotation(expression)
                    colon = _function_header_colon(text, offsets, node)
                    if colon is not None:
                        edits.append((path, colon, rendered, qualified, typing_name))
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)

        for node in tree.body:
            visit(node)

    by_path: dict[Path, list[tuple[int, str, str, str | None]]] = defaultdict(list)
    for path, offset, annotation, qualified, typing_name in edits:
        by_path[path].append((offset, annotation, qualified, typing_name))
    changed: list[str] = []
    for path, path_edits in by_path.items():
        text = path.read_text(encoding="utf-8")
        for offset, annotation, _, _ in sorted(path_edits, reverse=True):
            text = text[:offset] + f" -> {annotation}" + text[offset:]
        path.write_text(text, encoding="utf-8")
        for typing_name in {item[3] for item in path_edits if item[3]}:
            ensure_typing_name(path, typing_name)
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
        changed.extend(item[2] for item in path_edits)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stub-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--contracts-output", type=Path)
    args = parser.parse_args()
    contracts = infer_parent_contracts(args.index.resolve())
    if args.contracts_output:
        args.contracts_output.write_text(json.dumps(contracts, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    changed = apply(args.stub_root.resolve(), contracts)
    print(json.dumps({"contracts": len(contracts), "applied": len(changed)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
