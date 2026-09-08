#!/usr/bin/env python3
"""Audit the *quality* of a generated Sage API contract index.

The index inventory and semantic contract coverage are different things.  A
stubgen export can contain every Sage symbol while still leaving most return
annotations unknown.  This module makes that distinction machine-readable so
regressions cannot be hidden behind an empty expected-symbol set.

The audit is deliberately read-only with respect to the index.  It never
guesses a return type and it does not treat a broad Python type as a concrete
Sage contract.  The JSON report is stable (sorted keys, sorted samples) and
can therefore be checked into a build artifact or compared between Sage
versions.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


AUDIT_SCHEMA_VERSION = 1
AUDIT_VERSION = "sage-api-contract-audit/0.1"
CALLABLE_KINDS = frozenset({"FUNCTION", "METHOD", "PROPERTY"})
TYPE_STATES = frozenset({"KNOWN", "UNKNOWN", "DYNAMIC"})
BROAD_BUILTINS = frozenset(
    {
        "bool",
        "bytes",
        "complex",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "object",
        "set",
        "str",
        "tuple",
    }
)
STRUCTURAL_SUFFIXES = ("_base", "_generic", "_element", "_parent", "_factory")
TYPEVAR_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]*\b")


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _state(value: Any) -> str:
    if not isinstance(value, dict):
        return "UNKNOWN"
    state = value.get("state")
    return state if state in TYPE_STATES else "UNKNOWN"


def _expression(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    expression = value.get("expression")
    return expression if isinstance(expression, str) and expression else None


def classify_return(
    return_type: Any,
    type_parameters: Iterable[dict[str, Any]] = (),
    structural_leaf_paths: Iterable[str] = (),
) -> str:
    """Return a conservative quality class for one indexed return type.

    ``CONCRETE`` means the expression is a named type from the source
    contract, not that it is necessarily a Sage class.  ``TYPE_VARIABLE`` is
    still a useful exact contract when the call-site binds it.  A broad
    builtin, structural base, union or generic remains visible as such and is
    never silently counted as a concrete Sage result.
    """
    state = _state(return_type)
    structural_leaves = set(structural_leaf_paths)
    if state == "UNKNOWN":
        return "UNKNOWN"
    if state == "DYNAMIC":
        return "DYNAMIC"
    expression = _expression(return_type)
    if expression is None:
        return "KNOWN_UNEXPRESSED"
    names = {item.get("name") for item in type_parameters if isinstance(item, dict)}
    if expression in names or expression in {"Self", "typing.Self"}:
        return "TYPE_VARIABLE"
    if expression in {"NoReturn", "typing.NoReturn"}:
        return "NO_RETURN"
    if expression == "None":
        return "NONE"
    if expression in BROAD_BUILTINS:
        return "BROAD_BUILTIN"
    if " | " in expression or expression.startswith(("Union[", "Optional[")):
        # A source-proven multi-implementation union may contain a concrete
        # ``*_generic`` implementation alongside a backend leaf.  Keep that
        # as a union quality class; only the other structural suffixes remain
        # a structural-base diagnostic.  Standalone ``*_generic`` expressions
        # still take the conservative STRUCTURAL_BASE path below.
        arms = [
            arm.strip().strip("'\"")
            for arm in expression.replace("Union[", "").replace("Optional[", "").strip("[]").split(" | ")
        ]
        if any(
            any(
                arm.rsplit(".", 1)[-1].lower().endswith(suffix)
                and arm not in structural_leaves
                for suffix in ("_base", "_element", "_parent", "_factory")
            )
            for arm in arms
        ):
            return "STRUCTURAL_BASE"
        # ``*_generic`` is intentionally retained as a union quality class.
        # A union has already exposed its alternatives, so the generic arm is
        # not by itself evidence that the public result is a dispatch base.
        return "UNION_OR_OPTIONAL"
    final = expression.rsplit(".", 1)[-1].lower()
    if any(final.endswith(suffix) for suffix in STRUCTURAL_SUFFIXES) and expression not in structural_leaves:
        return "STRUCTURAL_BASE"
    if "[" in expression:
        return "GENERIC"
    if "." in expression:
        return "CONCRETE"
    return "UNQUALIFIED"


def _signature_quality(
    signature: Any,
    structural_leaf_paths: Iterable[str] = (),
) -> dict[str, Any]:
    if not isinstance(signature, dict):
        signature = {}
    parameters = signature.get("parameters")
    if not isinstance(parameters, list):
        parameters = []
    parameter_states = Counter(
        _state(parameter.get("type"))
        for parameter in parameters
        if isinstance(parameter, dict)
    )
    type_parameters = signature.get("typeParameters")
    if not isinstance(type_parameters, list):
        type_parameters = []
    return_type = signature.get("returnType")
    return {
        "return": classify_return(return_type, type_parameters, structural_leaf_paths),
        "returnState": _state(return_type),
        "returnExpression": _expression(return_type),
        "parameterStates": dict(sorted(parameter_states.items())),
        "parameterCount": len(parameters),
        "typeParameterCount": len(type_parameters),
    }


def _entry_quality(
    entry: dict[str, Any],
    structural_leaf_paths: Iterable[str] = (),
) -> dict[str, Any]:
    signatures = entry.get("signatures")
    if not isinstance(signatures, list):
        signatures = []
    qualities = [_signature_quality(signature, structural_leaf_paths) for signature in signatures]
    returns = Counter(item["return"] for item in qualities)
    parameter_states = Counter()
    for item in qualities:
        parameter_states.update(item["parameterStates"])
    return {
        "qualifiedName": entry.get("qualifiedName"),
        "kind": entry.get("kind"),
        "signatureCount": len(signatures),
        "returnClasses": dict(sorted(returns.items())),
        "parameterStates": dict(sorted(parameter_states.items())),
        "hasTypeParameters": any(item["typeParameterCount"] for item in qualities),
        "hasDocumentation": bool(entry.get("documentation")),
    }


def _source_stats(root: Path) -> dict[str, Any]:
    functions = 0
    annotated_returns = 0
    files = 0
    syntax_errors: list[str] = []
    protocol_missing = Counter()
    protocol_names = {
        "__init__",
        "__del__",
        "__init_subclass__",
        "__str__",
        "__repr__",
        "__format__",
        "__bytes__",
        "__bool__",
        "__len__",
        "__index__",
        "__hash__",
    }
    for path in sorted(root.rglob("*.pyi")):
        files += 1
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
        except (OSError, SyntaxError) as error:
            syntax_errors.append(f"{path}: {error}")
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions += 1
                annotated_returns += node.returns is not None
                if node.name in protocol_names and node.returns is None:
                    protocol_missing[node.name] += 1
    return {
        "root": str(root),
        "fileCount": files,
        "functionCount": functions,
        "annotatedReturnCount": annotated_returns,
        "missingReturnCount": functions - annotated_returns,
        "annotationRatio": (annotated_returns / functions if functions else 0.0),
        "missingProtocolReturns": dict(sorted(protocol_missing.items())),
        "syntaxErrors": syntax_errors,
    }


def audit_index(index: dict[str, Any], *, source_root: Path | None = None, sample_limit: int = 10) -> dict[str, Any]:
    """Build a deterministic quality report for one parsed index object."""
    entries = index.get("entries") if isinstance(index, dict) else None
    if not isinstance(entries, list):
        raise ValueError("index entries must be an array")
    class_paths = {
        entry.get("qualifiedName")
        for entry in entries
        if isinstance(entry, dict)
        and entry.get("kind") == "CLASS"
        and isinstance(entry.get("qualifiedName"), str)
    }
    indexed_children: defaultdict[str, set[str]] = defaultdict(set)
    for entry in entries:
        if not isinstance(entry, dict) or entry.get("kind") != "CLASS":
            continue
        child = entry.get("qualifiedName")
        if not isinstance(child, str):
            continue
        for parent in entry.get("parents", ()):
            if isinstance(parent, str):
                indexed_children[parent].add(child)
    structural_leaf_paths = {
        path
        for path in class_paths
        if any(path.rsplit(".", 1)[-1].lower().endswith(suffix) for suffix in STRUCTURAL_SUFFIXES)
        and path not in indexed_children
    }
    kind_counts = Counter()
    callable_entries = [entry for entry in entries if isinstance(entry, dict) and entry.get("kind") in CALLABLE_KINDS]
    return_classes = Counter()
    parameter_states = Counter()
    signature_count = 0
    no_signature = 0
    documented = 0
    type_parameter_entries = 0
    module_buckets: dict[str, Counter[str]] = defaultdict(Counter)
    unknown_samples: list[str] = []
    broad_samples: list[str] = []
    structural_samples: list[str] = []
    dynamic_samples: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        kind_counts[kind] += 1
        if kind not in CALLABLE_KINDS:
            continue
        quality = _entry_quality(entry, structural_leaf_paths)
        signatures = entry.get("signatures") if isinstance(entry.get("signatures"), list) else []
        if not signatures:
            no_signature += 1
        else:
            signature_count += len(signatures)
        documented += quality["hasDocumentation"]
        type_parameter_entries += quality["hasTypeParameters"]
        for signature in signatures:
            detail = _signature_quality(signature, structural_leaf_paths)
            result = detail["return"]
            return_classes[result] += 1
            parameter_states.update(detail["parameterStates"])
            qualified_name = str(entry.get("qualifiedName", ""))
            module = qualified_name.rsplit(".", 1)[0] if "." in qualified_name else qualified_name
            module_buckets[module][result] += 1
            if result == "UNKNOWN" and len(unknown_samples) < sample_limit:
                unknown_samples.append(qualified_name)
            elif result == "DYNAMIC" and len(dynamic_samples) < sample_limit:
                dynamic_samples.append(qualified_name)
            elif result == "BROAD_BUILTIN" and len(broad_samples) < sample_limit:
                broad_samples.append(qualified_name)
            elif result == "STRUCTURAL_BASE" and len(structural_samples) < sample_limit:
                structural_samples.append(qualified_name)
    report: dict[str, Any] = {
        "schemaVersion": AUDIT_SCHEMA_VERSION,
        "auditVersion": AUDIT_VERSION,
        "index": {
            "schemaVersion": index.get("schemaVersion"),
            "generator": index.get("generator"),
            "sageVersion": index.get("sageVersion"),
            "pythonVersion": index.get("pythonVersion"),
        },
        "counts": {
            "entries": len(entries),
            "callableEntries": len(callable_entries),
            "signatures": signature_count,
            "noSignatureCallableEntries": no_signature,
            "documentedCallableEntries": documented,
            "typeParameterCallableEntries": type_parameter_entries,
            "kinds": dict(sorted(kind_counts.items(), key=lambda item: str(item[0]))),
            "returnClasses": dict(sorted(return_classes.items())),
            "parameterStates": dict(sorted(parameter_states.items())),
        },
        "samples": {
            "unknownReturns": sorted(unknown_samples),
            "dynamicReturns": sorted(dynamic_samples),
            "broadBuiltinReturns": sorted(broad_samples),
            "structuralBaseReturns": sorted(structural_samples),
        },
        "moduleBuckets": {
            module: dict(sorted(counts.items()))
            for module, counts in sorted(module_buckets.items())
        },
    }
    if source_root is not None:
        report["source"] = _source_stats(source_root.resolve())
    return report


def _markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    classes = counts["returnClasses"]
    lines = [
        "# Sage API contract quality audit",
        "",
        "This report measures source-proven return contracts; it is not a claim that every Sage symbol has a concrete return type.",
        "",
        f"- Index entries: `{counts['entries']}`; callable entries: `{counts['callableEntries']}`; signatures: `{counts['signatures']}`",
        f"- Return classes: `{json.dumps(classes, ensure_ascii=False, sort_keys=True)}`",
        f"- Parameter states: `{json.dumps(counts['parameterStates'], ensure_ascii=False, sort_keys=True)}`",
        f"- Callable entries without signatures: `{counts['noSignatureCallableEntries']}`",
        "",
        "## Samples",
        "",
    ]
    for title, key in (
        ("Unknown returns", "unknownReturns"),
        ("Dynamic returns", "dynamicReturns"),
        ("Broad builtin returns", "broadBuiltinReturns"),
        ("Structural/base returns", "structuralBaseReturns"),
    ):
        values = report["samples"][key]
        lines.append(f"### {title}")
        lines.append("")
        lines.extend(f"- `{value}`" for value in values or ["(none)"])
        lines.append("")
    if "source" in report:
        source = report["source"]
        lines.extend(
            [
                "## Source stub coverage",
                "",
                f"- `.pyi` files: `{source['fileCount']}`",
                f"- Function definitions: `{source['functionCount']}`",
                f"- Annotated returns: `{source['annotatedReturnCount']}`",
                f"- Missing returns: `{source['missingReturnCount']}`",
                f"- Annotation ratio: `{source['annotationRatio']:.4f}`",
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Sage API return-contract quality")
    parser.add_argument("--index", type=Path, required=True, help="Generated Sage API index JSON")
    parser.add_argument("--source-root", type=Path, help="Optional .pyi root for source annotation statistics")
    parser.add_argument("--output", type=Path, required=True, help="JSON report path")
    parser.add_argument("--markdown", type=Path, help="Optional Markdown report path")
    parser.add_argument("--sample-limit", type=int, default=10)
    args = parser.parse_args(argv)
    if args.sample_limit < 0:
        parser.error("--sample-limit must be non-negative")
    try:
        index = json.loads(args.index.read_text(encoding="utf-8"))
        report = audit_index(index, source_root=args.source_root, sample_limit=args.sample_limit)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        parser.error(str(error))
    report["index"]["path"] = str(args.index.resolve())
    report["index"]["sha256"] = _digest(args.index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(_markdown(report) + "\n", encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
