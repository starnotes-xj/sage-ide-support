#!/usr/bin/env python3
"""Generate a deterministic, versioned Sage API index from .pyi/.py sources."""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
GENERATOR_VERSION = "sage-api-index-py/0.1"
KIND_ORDER = {name: index for index, name in enumerate(("MODULE", "CLASS", "FUNCTION", "METHOD", "PROPERTY", "CONSTANT", "ALIAS"))}
CONFIDENCE_RANK = {"UNKNOWN": 1, "LOW": 2, "MEDIUM": 3, "HIGH": 4}

@dataclass(frozen=True)
class SourceRef:
    kind: str
    locator: str
    digest: str
    def json(self) -> dict[str, str]:
        return {"kind": self.kind, "locator": self.locator, "digest": self.digest}

@dataclass
class RawSymbol:
    qualified_name: str
    kind: str
    source: SourceRef
    signatures: list[dict[str, Any]] = field(default_factory=list)
    value_type: dict[str, Any] | None = None
    parents: list[str] = field(default_factory=list)
    protocols: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    documentation: dict[str, Any] | None = None
    dynamicity: str = "STATIC"
    confidence: str = "UNKNOWN"
    def key(self) -> tuple[str, str]:
        return self.qualified_name, self.kind

@dataclass(frozen=True)
class SourceSpec:
    root: Path
    kind: str
    locator: str
    module_prefix: str = ""

class AstExtractor:
    def __init__(self, source: SourceSpec) -> None:
        self.source_root = source.root.resolve()
        self.source_kind = source.kind
        self.source_locator = source.locator.strip("/")
        self.module_prefix = source.module_prefix.strip(".")

    def extract_path(self, path: Path) -> list[RawSymbol]:
        path = path.resolve()
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path), type_comments=True)
        module = self.module_name(path)
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        relative = path.relative_to(self.source_root).as_posix()
        locator = "/".join(part for part in (self.source_locator, relative) if part)
        source = SourceRef(self.source_kind, locator, digest)
        imports = self.collect_imports(tree)
        imports.update({node.name: f"{module}.{node.name}" for node in tree.body if isinstance(node, ast.ClassDef)})
        symbols: list[RawSymbol] = [RawSymbol(module, "MODULE", source, confidence="HIGH")]
        for node in tree.body:
            symbols.extend(self.extract_top_level(node, module, imports, source))
        return sorted(symbols, key=lambda item: (item.qualified_name, KIND_ORDER[item.kind], item.source.locator))

    def module_name(self, path: Path) -> str:
        parts = list(path.relative_to(self.source_root).parts)
        filename = Path(parts.pop())
        if filename.stem == "__init__":
            value = ".".join(parts)
        else:
            value = ".".join(parts + [filename.stem])
        if self.module_prefix and value and not (value == self.module_prefix or value.startswith(self.module_prefix + ".")):
            value = self.module_prefix + "." + value
        return value or self.module_prefix or "__root__"

    @staticmethod
    def collect_imports(tree: ast.Module) -> dict[str, str]:
        imports: dict[str, str] = {}
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    if alias.name != "*":
                        imports[alias.asname or alias.name] = f"{node.module}.{alias.name}"
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[alias.asname or alias.name.split(".")[0]] = alias.name
        return imports

    def extract_top_level(self, node: ast.AST, module: str, imports: dict[str, str], source: SourceRef) -> list[RawSymbol]:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            return self.extract_aliases(node, module, source)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return [self.function_symbol(node, module, None, imports, source, "FUNCTION")]
        if isinstance(node, ast.ClassDef):
            return self.class_symbols(node, module, imports, source)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            return [RawSymbol(f"{module}.{node.target.id}", "CONSTANT", source_at(source, node.lineno), value_type=type_ref(node.annotation, imports), documentation=doc(node), confidence="MEDIUM")]
        if isinstance(node, ast.Assign):
            names = [target.id for target in node.targets if isinstance(target, ast.Name) and target.id != "__all__"]
            return [RawSymbol(f"{module}.{name}", "CONSTANT", source_at(source, node.lineno), confidence="LOW") for name in names]
        return []

    @staticmethod
    def extract_aliases(node: ast.AST, module: str, source: SourceRef) -> list[RawSymbol]:
        if not isinstance(node, ast.ImportFrom) or not node.module:
            return []
        return [RawSymbol(f"{module}.{alias.asname or alias.name}", "ALIAS", source_at(source, node.lineno), aliases=[f"{node.module}.{alias.name}"], confidence="HIGH") for alias in node.names if alias.name != "*"]

    def class_symbols(self, node: ast.ClassDef, module: str, imports: dict[str, str], source: SourceRef) -> list[RawSymbol]:
        qualified = f"{module}.{node.name}"
        result = [RawSymbol(qualified, "CLASS", source_at(source, node.lineno), parents=[annotation_text(base, imports) for base in node.bases if annotation_text(base, imports)], documentation=doc(node), confidence="HIGH")]
        for member in node.body:
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "PROPERTY" if any(isinstance(item, ast.Name) and item.id == "property" for item in member.decorator_list) else "METHOD"
                result.append(self.function_symbol(member, module, node.name, imports, source, kind))
            elif isinstance(member, ast.AnnAssign) and isinstance(member.target, ast.Name):
                result.append(RawSymbol(f"{qualified}.{member.target.id}", "PROPERTY", source_at(source, member.lineno), value_type=type_ref(member.annotation, imports), documentation=doc(member), confidence="MEDIUM"))
        return result

    def function_symbol(self, node: ast.FunctionDef | ast.AsyncFunctionDef, module: str, owner: str | None, imports: dict[str, str], source: SourceRef, kind: str) -> RawSymbol:
        qualified = ".".join(part for part in (module, owner, node.name) if part)
        return RawSymbol(qualified, kind, source_at(source, node.lineno), signatures=[signature_for(node, imports)], documentation=doc(node), confidence="HIGH")

def source_at(source: SourceRef, line: int) -> SourceRef:
    return SourceRef(source.kind, f"{source.locator}:{line}", source.digest)

def doc(node: ast.AST) -> dict[str, Any] | None:
    value = ast.get_docstring(node, clean=False)
    if not value:
        return None
    lines = value.strip().splitlines()
    return {"summary": lines[0].strip() if lines else None, "body": value.strip(), "examples": [line.strip() for line in lines if line.strip().startswith(">>>")]}

def annotation_text(node: ast.AST | None, imports: dict[str, str]) -> str | None:
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return imports.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        prefix = annotation_text(node.value, imports)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Subscript):
        base = annotation_text(node.value, imports) or ""
        values = node.slice.elts if isinstance(node.slice, ast.Tuple) else [node.slice]
        return f"{base}[{', '.join(filter(None, (annotation_text(item, imports) for item in values)))}]"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return f"{annotation_text(node.left, imports)} | {annotation_text(node.right, imports)}"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return imports.get(node.value, node.value)
    try:
        return ast.unparse(node)
    except Exception:
        return None

def type_ref(node: ast.AST | None, imports: dict[str, str]) -> dict[str, Any] | None:
    expression = annotation_text(node, imports)
    if not expression:
        return None
    if expression == "Any" or expression.endswith(".Any"):
        return {"state": "DYNAMIC", "expression": None}
    return {"state": "KNOWN", "expression": expression}

def default_text(node: ast.AST | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None

def signature_for(node: ast.FunctionDef | ast.AsyncFunctionDef, imports: dict[str, str]) -> dict[str, Any]:
    args = node.args
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    parameters = [parameter_for(argument, default, imports, False, False) for argument, default in zip(positional, defaults) if argument.arg not in {"self", "cls"}]
    if args.vararg:
        parameters.append(parameter_for(args.vararg, None, imports, False, True))
    parameters.extend(parameter_for(argument, default, imports, True, False) for argument, default in zip(args.kwonlyargs, args.kw_defaults))
    if args.kwarg:
        parameters.append(parameter_for(args.kwarg, None, imports, True, True))
    return {"parameters": parameters, "returnType": type_ref(node.returns, imports) or {"state": "UNKNOWN", "expression": None}}

def parameter_for(argument: ast.arg, default: ast.AST | None, imports: dict[str, str], keyword_only: bool, variadic: bool) -> dict[str, Any]:
    return {"name": argument.arg, "type": type_ref(argument.annotation, imports) or {"state": "UNKNOWN", "expression": None}, "defaultValue": default_text(default), "optional": default is not None, "keywordOnly": keyword_only, "variadic": variadic}

def signature_key(signature: dict[str, Any]) -> str:
    return json.dumps(signature, sort_keys=True, separators=(",", ":"))

def normalize(raw_symbols: Iterable[RawSymbol], sage_version: str, python_version: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    raw_list = list(raw_symbols)
    grouped: dict[tuple[str, str], list[RawSymbol]] = {}
    imported_aliases: dict[str, set[str]] = {}
    for symbol in raw_list:
        grouped.setdefault(symbol.key(), []).append(symbol)
        if symbol.kind == "ALIAS":
            for target in symbol.aliases:
                imported_aliases.setdefault(target, set()).add(symbol.qualified_name)
    entries: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for key in sorted(grouped, key=lambda item: (item[0], KIND_ORDER[item[1]])):
        candidates = sorted(grouped[key], key=lambda item: (item.source.kind, item.source.locator))
        signatures: list[dict[str, Any]] = []
        for candidate in candidates:
            for signature in candidate.signatures:
                if signature_key(signature) not in {signature_key(item) for item in signatures}:
                    signatures.append(signature)
        conflict = conflicting_signatures(signatures)
        if len(candidates) > 1:
            diagnostics.append({"kind": "CONFLICT" if conflict else "DUPLICATE", "qualifiedName": key[0], "message": "Conflicting declarations were merged as dynamic" if conflict else "Duplicate declarations were merged", "sources": [candidate.source.json() for candidate in candidates]})
        if conflict:
            signatures = [{"parameters": [], "returnType": {"state": "DYNAMIC", "expression": None}}]
        dynamicity = "DYNAMIC" if conflict or any(item.dynamicity == "DYNAMIC" for item in candidates) else ("UNKNOWN" if any(item.dynamicity == "UNKNOWN" for item in candidates) else "STATIC")
        confidence = max((item.confidence for item in candidates), key=lambda item: CONFIDENCE_RANK[item])
        sources = []
        seen_sources: set[tuple[str, str]] = set()
        for candidate in candidates:
            marker = (candidate.source.kind, candidate.source.locator)
            if marker not in seen_sources:
                seen_sources.add(marker)
                sources.append(candidate.source.json())
        aliases = {alias for item in candidates for alias in item.aliases}
        aliases.update(imported_aliases.get(key[0], set()))
        entry: dict[str, Any] = {"qualifiedName": key[0], "kind": key[1], "dynamicity": dynamicity, "confidence": confidence, "parents": sorted({parent for item in candidates for parent in item.parents}), "protocols": sorted({protocol for item in candidates for protocol in item.protocols}), "aliases": sorted(aliases), "sources": sources, "signatures": signatures}
        values = [item.value_type for item in candidates if item.value_type is not None]
        if values:
            entry["valueType"] = values[0]
        documents = [item.documentation for item in candidates if item.documentation is not None]
        if documents:
            entry["documentation"] = documents[0]
        entries.append(entry)
    index = {"schemaVersion": SCHEMA_VERSION, "sageVersion": sage_version, "pythonVersion": python_version, "generatorVersion": GENERATOR_VERSION, "sourceDigests": source_digests(entries), "entries": entries}
    return index, sorted(diagnostics, key=lambda item: (item["qualifiedName"], item["kind"]))

def conflicting_signatures(signatures: list[dict[str, Any]]) -> bool:
    groups: dict[tuple[str, ...], set[str]] = {}
    for signature in signatures:
        names = tuple(parameter["name"] for parameter in signature.get("parameters", []))
        groups.setdefault(names, set()).add(json.dumps(signature.get("returnType", {}), sort_keys=True))
    return any(len(values) > 1 for values in groups.values())

def source_digests(entries: list[dict[str, Any]]) -> dict[str, str]:
    result = {}
    for entry in entries:
        for source in entry["sources"]:
            result[source["locator"].split(":")[0]] = source["digest"]
    return dict(sorted(result.items()))

def validate_index(index: dict[str, Any]) -> None:
    if not isinstance(index, dict):
        raise ValueError("generated index must be a JSON object")
    if type(index.get("schemaVersion")) is not int or index["schemaVersion"] != SCHEMA_VERSION:
        raise ValueError("generated index has unsupported schemaVersion")
    for field in ("sageVersion", "pythonVersion", "generatorVersion"):
        if not isinstance(index.get(field), str) or not index[field].strip():
            raise ValueError(f"generated index requires nonblank {field}")
    source_digests_value = index.get("sourceDigests", {})
    if not isinstance(source_digests_value, dict):
        raise ValueError("generated index sourceDigests must be an object")
    for locator, digest in source_digests_value.items():
        if not isinstance(locator, str) or not locator.strip() or not isinstance(digest, str) or not is_sha256(digest):
            raise ValueError("generated index sourceDigests must map locators to SHA-256 digests")
    entries = index.get("entries")
    if not isinstance(entries, list):
        raise ValueError("generated index entries must be an array")
    seen: set[tuple[str, str]] = set()
    for entry_index, entry in enumerate(entries):
        validate_entry(entry, f"entries[{entry_index}]")
        key = (entry["qualifiedName"], entry["kind"])
        if key in seen:
            raise ValueError(f"generated index contains duplicate entry {key[0]} ({key[1]})")
        seen.add(key)

def validate_entry(entry: Any, path: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"{path} must be an object")
    for field in ("qualifiedName", "kind", "dynamicity", "confidence"):
        if not isinstance(entry.get(field), str) or not entry[field].strip():
            raise ValueError(f"{path}.{field} must be a nonblank string")
    if entry["kind"] not in KIND_ORDER:
        raise ValueError(f"{path}.kind is not a known Sage symbol kind")
    if entry["dynamicity"] not in {"STATIC", "DYNAMIC", "UNKNOWN"}:
        raise ValueError(f"{path}.dynamicity is invalid")
    if entry["confidence"] not in CONFIDENCE_RANK:
        raise ValueError(f"{path}.confidence is invalid")
    for field in ("parents", "protocols", "aliases"):
        if not isinstance(entry.get(field), list) or not all(isinstance(item, str) and item.strip() for item in entry[field]):
            raise ValueError(f"{path}.{field} must contain nonblank strings")
    signatures = entry.get("signatures")
    if not isinstance(signatures, list):
        raise ValueError(f"{path}.signatures must be an array")
    for signature_index, signature in enumerate(signatures):
        validate_signature(signature, f"{path}.signatures[{signature_index}]")
    sources = entry.get("sources")
    if not isinstance(sources, list) or not sources:
        raise ValueError(f"{path}.sources must be a nonempty array")
    for source_index, source in enumerate(sources):
        if not isinstance(source, dict) or source.get("kind") not in {"RUNTIME", "STUB", "SIGNATURE", "DOCUMENTATION", "USER_STUB", "PROBE"} or not isinstance(source.get("locator"), str) or not source["locator"].strip():
            raise ValueError(f"{path}.sources[{source_index}] is invalid")
        if "digest" in source and (not isinstance(source["digest"], str) or not is_sha256(source["digest"])):
            raise ValueError(f"{path}.sources[{source_index}].digest is invalid")
    if "valueType" in entry:
        validate_type_ref(entry["valueType"], f"{path}.valueType")
    if "documentation" in entry and not isinstance(entry["documentation"], dict):
        raise ValueError(f"{path}.documentation must be an object")

def validate_signature(signature: Any, path: str) -> None:
    if not isinstance(signature, dict) or not isinstance(signature.get("parameters"), list) or "returnType" not in signature:
        raise ValueError(f"{path} is invalid")
    for parameter_index, parameter in enumerate(signature["parameters"]):
        if not isinstance(parameter, dict) or not isinstance(parameter.get("name"), str) or not parameter["name"].strip() or not isinstance(parameter.get("type"), dict):
            raise ValueError(f"{path}.parameters[{parameter_index}] is invalid")
        validate_type_ref(parameter["type"], f"{path}.parameters[{parameter_index}].type")
        for boolean_field in ("optional", "keywordOnly", "variadic"):
            if boolean_field in parameter and type(parameter[boolean_field]) is not bool:
                raise ValueError(f"{path}.parameters[{parameter_index}].{boolean_field} must be boolean")
        if "defaultValue" in parameter and parameter["defaultValue"] is not None and not isinstance(parameter["defaultValue"], str):
            raise ValueError(f"{path}.parameters[{parameter_index}].defaultValue must be a string or null")
    validate_type_ref(signature["returnType"], f"{path}.returnType")

def validate_type_ref(value: Any, path: str) -> None:
    if not isinstance(value, dict) or value.get("state") not in {"KNOWN", "UNKNOWN", "DYNAMIC"}:
        raise ValueError(f"{path} is an invalid type reference")
    expression = value.get("expression")
    if expression is not None and (not isinstance(expression, str) or not expression.strip()):
        raise ValueError(f"{path}.expression must be a nonblank string or null")
    if value["state"] == "KNOWN" and not isinstance(expression, str):
        raise ValueError(f"{path} KNOWN type requires an expression")

def is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdefABCDEF" for character in value)

def expected_symbols(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError("expected manifest must be a JSON array")
    result = []
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("qualifiedName"), str) or not isinstance(item.get("kind"), str):
            raise ValueError("expected manifest entries require qualifiedName and kind")
        result.append({"qualifiedName": item["qualifiedName"], "kind": item["kind"]})
    return sorted({(item["qualifiedName"], item["kind"]): item for item in result}.values(), key=lambda item: (item["qualifiedName"], KIND_ORDER.get(item["kind"], 99)))

def coverage(index: dict[str, Any], diagnostics: list[dict[str, Any]], expected: list[dict[str, str]]) -> dict[str, Any]:
    entries = {(item["qualifiedName"], item["kind"]): item for item in index["entries"]}
    aliases = {}
    for key, entry in entries.items():
        for alias in entry.get("aliases", []):
            aliases.setdefault((alias, entry["kind"]), key)
    resolved = {(item["qualifiedName"], item["kind"]): ((item["qualifiedName"], item["kind"]) if (item["qualifiedName"], item["kind"]) in entries else aliases.get((item["qualifiedName"], item["kind"]))) for item in expected}
    covered = [item for item in expected if resolved[(item["qualifiedName"], item["kind"])] is not None]
    missing = [item for item in expected if resolved[(item["qualifiedName"], item["kind"])] is None]
    without_signature = [item for item in covered if resolved[(item["qualifiedName"], item["kind"])] and item["kind"] in {"FUNCTION", "METHOD", "CLASS"} and not entries[resolved[(item["qualifiedName"], item["kind"])]].get("signatures")]
    dynamic = [item for item in covered if resolved[(item["qualifiedName"], item["kind"])] and (entries[resolved[(item["qualifiedName"], item["kind"])]]["dynamicity"] != "STATIC" or any(signature.get("returnType", {}).get("state") == "DYNAMIC" for signature in entries[resolved[(item["qualifiedName"], item["kind"])]].get("signatures", [])))]
    return {"expected": expected, "covered": covered, "missing": missing, "withoutSignature": without_signature, "dynamic": dynamic, "conflicts": [item for item in diagnostics if item["kind"] == "CONFLICT"], "expectedCount": len(expected), "coveredCount": len(covered), "coverageRatio": 1.0 if not expected else len(covered) / len(expected), "isComplete": not missing and not any(item["kind"] == "CONFLICT" for item in diagnostics), "diagnostics": diagnostics}

def diff_indexes(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    before = {(item["qualifiedName"], item["kind"]): item for item in previous.get("entries", [])}
    after = {(item["qualifiedName"], item["kind"]): item for item in current.get("entries", [])}
    item = lambda key: {"qualifiedName": key[0], "kind": key[1]}
    added, removed = sorted(set(after) - set(before)), sorted(set(before) - set(after))
    changed = sorted(key for key in set(before) & set(after) if before[key] != after[key])
    return {"added": [item(key) for key in added], "removed": [item(key) for key in removed], "changed": [item(key) for key in changed], "addedCount": len(added), "removedCount": len(removed), "changedCount": len(changed)}

def discover(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*") if path.suffix in {".pyi", ".py"} and path.is_file())

def parse_source_manifest(path: Path) -> list[SourceSpec]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise ValueError("source manifest must be a nonempty JSON array")
    specs = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"source manifest entry {index} must be an object")
        root = item.get("root")
        kind = item.get("kind")
        locator = item.get("locator")
        module_prefix = item.get("modulePrefix", "")
        if not isinstance(root, str) or not root.strip() or not isinstance(kind, str) or kind not in {"RUNTIME", "STUB", "SIGNATURE", "DOCUMENTATION", "USER_STUB", "PROBE"} or not isinstance(locator, str) or not locator.strip() or not isinstance(module_prefix, str):
            raise ValueError(f"source manifest entry {index} requires root, valid kind, locator, and optional modulePrefix")
        source_root = Path(root)
        if not source_root.is_dir():
            raise ValueError(f"source manifest root does not exist: {source_root}")
        specs.append(SourceSpec(source_root, kind, locator, module_prefix))
    return specs

def build(args: argparse.Namespace) -> int:
    if args.source_manifest is None and args.source_root is None:
        raise ValueError("either --source-root or --source-manifest is required")
    specs = parse_source_manifest(args.source_manifest) if args.source_manifest else [SourceSpec(args.source_root, "STUB", args.source_locator, args.module_prefix)]
    paths = [(spec, path) for spec in specs for path in discover(spec.root)]
    if not paths:
        raise ValueError("no .pyi/.py sources found in configured source roots")
    raw = [symbol for spec, path in paths for symbol in AstExtractor(spec).extract_path(path)]
    index, diagnostics = normalize(raw, args.sage_version, args.python_version)
    validate_index(index)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.raw_output:
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        args.raw_output.write_text(json.dumps([{"qualifiedName": item.qualified_name, "kind": item.kind, "sources": [item.source.json()], "signatures": item.signatures, "parents": item.parents, "aliases": item.aliases, "dynamicity": item.dynamicity, "confidence": item.confidence} for item in raw], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    report = coverage(index, diagnostics, expected_symbols(args.expected))
    if args.coverage_output:
        args.coverage_output.parent.mkdir(parents=True, exist_ok=True)
        args.coverage_output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.previous and args.diff_output:
        previous = json.loads(args.previous.read_text(encoding="utf-8"))
        args.diff_output.parent.mkdir(parents=True, exist_ok=True)
        args.diff_output.write_text(json.dumps(diff_indexes(previous, index), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"sources": len(paths), "rawSymbols": len(raw), "entries": len(index["entries"]), "diagnostics": len(diagnostics), "coverage": report["coverageRatio"], "missing": len(report["missing"])}, ensure_ascii=False))
    return 0

def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-root", type=Path)
    result.add_argument("--module-prefix", default="")
    result.add_argument("--source-manifest", type=Path)
    result.add_argument("--source-locator", default="runtime-export")
    result.add_argument("--sage-version", required=True)
    result.add_argument("--python-version", required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--raw-output", type=Path)
    result.add_argument("--expected", type=Path)
    result.add_argument("--coverage-output", type=Path)
    result.add_argument("--previous", type=Path)
    result.add_argument("--diff-output", type=Path)
    return result

if __name__ == "__main__":
    try:
        raise SystemExit(build(parser().parse_args()))
    except (OSError, SyntaxError, ValueError, json.JSONDecodeError) as error:
        print(f"sage-api-index: error: {error}", file=sys.stderr)
        raise SystemExit(2)
