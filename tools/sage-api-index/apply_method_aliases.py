#!/usr/bin/env python3
"""Add source-proven class method aliases to an existing Sage API index.

Generated Sage stubs sometimes express a public method alias with a class
assignment instead of another ``def``::

    def cardinality(self) -> Integer: ...
    order = cardinality

The index generator records declarations, so an already-published complete
index produced before alias support existed can miss the second public name.
This pass reads the exact stub tree and copies a contract only when all of the
following are true:

* the right-hand side is a direct method name declared in the same class;
* the input index has exactly one METHOD or PROPERTY entry for that method;
* the alias is not already occupied by a different indexed declaration.

It is deliberately source-driven and fail-closed.  It never guesses aliases,
does not alter any existing entry, and carries the original signature,
documentation and confidence unchanged.  The copied source locator is moved
to the assignment line in the same stub file for auditability.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


MEMBER_KINDS = {"METHOD", "PROPERTY"}


@dataclass(frozen=True)
class MethodAlias:
    qualified_name: str
    target_qualified_name: str
    relative_stub_path: str
    line: int


def module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def class_method_aliases(path: Path, root: Path) -> list[MethodAlias]:
    """Return direct ``alias = method`` relationships declared by one stub."""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path), type_comments=True)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []
    module = module_name(path, root)
    relative_path = path.relative_to(root).as_posix()
    aliases: list[MethodAlias] = []

    def visit_class(node: ast.ClassDef, owner: str) -> None:
        declared = {
            member.name
            for member in node.body
            if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for member in node.body:
            if not isinstance(member, ast.Assign) or not isinstance(member.value, ast.Name):
                continue
            if member.value.id not in declared:
                continue
            for target in member.targets:
                if isinstance(target, ast.Name):
                    aliases.append(
                        MethodAlias(
                            qualified_name=f"{owner}.{target.id}",
                            target_qualified_name=f"{owner}.{member.value.id}",
                            relative_stub_path=relative_path,
                            line=member.lineno,
                        )
                    )
        for member in node.body:
            if isinstance(member, ast.ClassDef):
                visit_class(member, f"{owner}.{member.name}")

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            visit_class(node, f"{module}.{node.name}")
    return aliases


def discover_method_aliases(stub_root: Path) -> list[MethodAlias]:
    aliases: list[MethodAlias] = []
    for path in sorted(stub_root.rglob("*.pyi")):
        aliases.extend(class_method_aliases(path, stub_root))
    return sorted(aliases, key=lambda item: (item.qualified_name, item.target_qualified_name, item.relative_stub_path, item.line))


def replace_source_line(source: dict[str, Any], relative_stub_path: str, line: int) -> dict[str, Any]:
    copied = dict(source)
    locator = copied.get("locator")
    if not isinstance(locator, str):
        return copied
    source_path, separator, source_line = locator.rpartition(":")
    if not separator or not source_line.isdecimal():
        return copied
    normalized_path = source_path.replace("\\", "/")
    if normalized_path.endswith("/" + relative_stub_path):
        copied["locator"] = f"{source_path}:{line}"
    return copied


def alias_entry(target: dict[str, Any], alias: MethodAlias) -> dict[str, Any]:
    copied = copy.deepcopy(target)
    copied["qualifiedName"] = alias.qualified_name
    copied["aliases"] = sorted({
        *(
            value
            for value in copied.get("aliases", [])
            if isinstance(value, str)
        ),
        alias.target_qualified_name,
    })
    sources = copied.get("sources")
    if isinstance(sources, list):
        copied["sources"] = [
            replace_source_line(source, alias.relative_stub_path, alias.line)
            if isinstance(source, dict) else source
            for source in sources
        ]
    return copied


def apply_aliases(index: dict[str, Any], aliases: Iterable[MethodAlias]) -> tuple[dict[str, Any], dict[str, int]]:
    entries = index.get("entries")
    if not isinstance(entries, list):
        raise ValueError("input is not a Sage API index with an entries array")
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get("qualifiedName"), str):
            by_name[entry["qualifiedName"]].append(entry)

    created = 0
    already_present = 0
    skipped_ambiguous_target = 0
    skipped_conflict = 0
    for alias in aliases:
        target_entries = [
            entry for entry in by_name.get(alias.target_qualified_name, [])
            if entry.get("kind") in MEMBER_KINDS
        ]
        if len(target_entries) != 1:
            skipped_ambiguous_target += 1
            continue
        existing_aliases = by_name.get(alias.qualified_name, [])
        if existing_aliases:
            if len(existing_aliases) == 1 and existing_aliases[0] == alias_entry(target_entries[0], alias):
                already_present += 1
            else:
                skipped_conflict += 1
            continue
        copied = alias_entry(target_entries[0], alias)
        entries.append(copied)
        by_name[alias.qualified_name].append(copied)
        created += 1
    return index, {
        "created": created,
        "alreadyPresent": already_present,
        "skippedAmbiguousTarget": skipped_ambiguous_target,
        "skippedConflict": skipped_conflict,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="existing full Sage API index")
    parser.add_argument("--stub-root", type=Path, required=True, help="matching generated .pyi tree")
    parser.add_argument("--output", type=Path, required=True, help="new index path; input is never overwritten")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = args.input.resolve()
    output = args.output.resolve()
    stub_root = args.stub_root.resolve()
    if source == output:
        raise ValueError("--output must differ from --input so the source release index remains intact")
    if not source.is_file():
        raise ValueError(f"input index does not exist: {source}")
    if not stub_root.is_dir():
        raise ValueError(f"stub root does not exist: {stub_root}")
    with source.open(encoding="utf-8") as stream:
        index = json.load(stream)
    if not isinstance(index, dict) or index.get("schemaVersion") != 1:
        raise ValueError("input is not a schemaVersion 1 Sage API index")
    aliases = discover_method_aliases(stub_root)
    patched, summary = apply_aliases(index, aliases)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(patched, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
    print(json.dumps({
        "input": str(source),
        "output": str(output),
        "stubRoot": str(stub_root),
        "discovered": len(aliases),
        "entryCount": len(patched["entries"]),
        "sha256": sha256(output),
        **summary,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
