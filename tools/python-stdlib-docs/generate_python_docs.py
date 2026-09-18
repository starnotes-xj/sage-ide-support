#!/usr/bin/env python3
"""Build the lazy, offline CPython standard-library documentation sidecar.

The IDE consumes the resulting 64 Base64 NDJSON buckets only on Ctrl+Q.  The
generator imports CPython's own standard library in isolated mode, never a
project or third-party module, and records public module/class/callable
docstrings.  It is deliberately a release/build helper, not editor runtime
introspection: opening Quick Documentation must not start WSL or Python.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import importlib
import inspect
import io
import pkgutil
import sys
from pathlib import Path
from types import ModuleType


BUCKET_MASK = 0x3F
MAX_DOCUMENTATION_BYTES = 64 * 1024
SKIPPED_ROOT_MODULES = {
    "__main__",
    "antigravity",
    "ensurepip",
    "idlelib",
    "lib2to3",
    "site",
    "test",
    "this",
    "tkinter",
    "turtledemo",
    "venv",
}
DOCUMENTED_DUNDERS = {"__call__", "__init__", "__iter__", "__new__", "__next__"}


def java_hash_code(value: str) -> int:
    """Return String.hashCode() so Python and Kotlin choose the same bucket."""
    result = 0
    for character in value:
        result = ((31 * result) + ord(character)) & 0xFFFFFFFF
    return result


def is_public_member(name: str) -> bool:
    return not name.startswith("_") or name in DOCUMENTED_DUNDERS


def safe_docstring(value: object) -> str | None:
    try:
        documentation = inspect.getdoc(value)
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return None
    if not documentation:
        return None
    documentation = documentation.strip()
    if not documentation or len(documentation.encode("utf-8")) > MAX_DOCUMENTATION_BYTES:
        return None
    return documentation


def record_documentation(records: dict[str, str], qualified_name: str, value: object) -> None:
    documentation = safe_docstring(value)
    if documentation:
        records.setdefault(qualified_name, documentation)


def record_module(records: dict[str, str], module: ModuleType) -> None:
    module_name = module.__name__
    record_documentation(records, module_name, module)
    for name, value in vars(module).items():
        if not is_public_member(name):
            continue
        qualified_name = f"{module_name}.{name}"
        if inspect.isclass(value) or inspect.isroutine(value) or inspect.isbuiltin(value):
            record_documentation(records, qualified_name, value)
        if inspect.isclass(value):
            for member_name, member in vars(value).items():
                if is_public_member(member_name):
                    record_documentation(records, f"{qualified_name}.{member_name}", member)


def standard_library_modules() -> list[str]:
    pending = sorted(getattr(sys, "stdlib_module_names", ()))
    discovered: set[str] = set()
    while pending:
        module_name = pending.pop(0)
        root = module_name.partition(".")[0]
        if root in SKIPPED_ROOT_MODULES or module_name.endswith(".__main__") or module_name in discovered:
            continue
        discovered.add(module_name)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                module = importlib.import_module(module_name)
            except (ImportError, OSError, RuntimeError, SystemError, ValueError):
                continue
        package_path = getattr(module, "__path__", None)
        if package_path is not None:
            try:
                children = (info.name for info in pkgutil.iter_modules(package_path, module.__name__ + "."))
                pending.extend(sorted(children))
            except (OSError, RuntimeError):
                pass
    return sorted(discovered)


def collect_documentation() -> tuple[dict[str, str], list[str]]:
    records: dict[str, str] = {}
    imported: list[str] = []
    builtins_module = importlib.import_module("builtins")
    record_module(records, builtins_module)
    for module_name in standard_library_modules():
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                module = importlib.import_module(module_name)
            except (ImportError, OSError, RuntimeError, SystemError, ValueError):
                continue
        record_module(records, module)
        imported.append(module_name)
    return records, imported


def write_sidecar(output: Path, records: dict[str, str], imported: list[str]) -> None:
    if output.name != "python-stdlib-docs":
        raise ValueError(f"refusing to clean an unexpected output directory: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for stale in output.glob("*.ndjson"):
        stale.unlink()
    buckets: dict[int, list[tuple[str, str]]] = {}
    for qualified_name, documentation in records.items():
        buckets.setdefault(java_hash_code(qualified_name) & BUCKET_MASK, []).append((qualified_name, documentation))
    for bucket, values in buckets.items():
        lines = []
        for qualified_name, documentation in sorted(values):
            encoded = base64.b64encode(documentation.encode("utf-8")).decode("ascii")
            lines.append(f"{qualified_name}\t{encoded}\n")
        (output / f"{bucket:02x}.ndjson").write_text("".join(lines), encoding="utf-8")
    (output / "MANIFEST").write_text(
        "\n".join(
            (
                f"python={sys.version}",
                f"modules={len(imported)}",
                f"records={len(records)}",
                f"buckets={len(buckets)}",
            )
        ) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records, imported = collect_documentation()
    write_sidecar(args.output, records, imported)
    print(f"wrote {len(records)} documentation records from {len(imported)} standard-library modules")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
