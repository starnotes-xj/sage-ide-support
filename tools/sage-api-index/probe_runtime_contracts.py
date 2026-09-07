#!/usr/bin/env python3
"""Collect runtime type evidence for reviewed Sage expressions.

Input is JSONL with ``qualifiedName``, ``expression`` and optional ``runs``.
Each expression runs in a fresh process, not a filesystem/security sandbox.
Repeated observations are not universal return contracts. Source/parameter
coverage must be checked separately before changing any stub or index.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


BUILTIN_RETURN_CONTRACTS = {
    "builtins.NoneType": "None",
    "builtins.bool": "bool",
    "builtins.bytes": "bytes",
    "builtins.dict": "dict",
    "builtins.float": "float",
    "builtins.int": "int",
    "builtins.list": "list",
    "builtins.set": "set",
    "builtins.str": "str",
    "builtins.tuple": "tuple",
    "builtins.type": "type",
}


MARKER = "SAGE_TYPE_OBSERVATION:"


def probe(expression: str, *, distro: str, sage: str, runs: int, timeout: float = 30) -> dict[str, object]:
    script = (
        "from sage.all import *\n"
        f"value = ({expression})\n"
        "t = type(value)\n"
        "import json as _probe_json\n"
        f"print({MARKER!r} + _probe_json.dumps(t.__module__ + '.' + t.__qualname__))\n"
    )
    classes: list[str] = []
    errors: list[str] = []
    for _ in range(max(2, runs)):
        try:
            result = subprocess.run(
                ["wsl.exe", "-d", distro, "--", "timeout", "--kill-after=2s",
                 f"{timeout}s", sage, "-c", script],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout + 10,
            )
            lines = [line[len(MARKER):] for line in result.stdout.splitlines() if line.startswith(MARKER)]
            if result.returncode == 0 and len(lines) == 1:
                observed_type = json.loads(lines[0])
                if not isinstance(observed_type, str) or not all(x.isidentifier() for x in observed_type.split(".")):
                    raise ValueError("invalid type observation")
                classes.append(observed_type)
            else:
                errors.append(f"exit={result.returncode}: " + (result.stderr or "missing/ambiguous type observation").strip()[-500:])
        except (subprocess.TimeoutExpired, OSError, ValueError) as error:
            errors.append(f"{type(error).__name__}: {error}")
    observed = classes[0] if classes else None
    contract = BUILTIN_RETURN_CONTRACTS.get(observed or "", observed)
    stable = len(classes) == max(2, runs) and not errors and len(set(classes)) == 1
    return {"state": "OBSERVED_STABLE" if stable else "UNKNOWN", "expression": expression,
            "returnType": None, "observedReturnType": contract if stable else None,
            "scope": "exact-expression-only", "requiresSourceProof": True,
            "observations": classes, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--sage", required=True, help="Explicit WSL Sage executable")
    parser.add_argument("--jobs", type=int, choices=range(1, 5), default=2)
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    items = [json.loads(line) for line in args.candidates.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    def run(item):
        return {**item, **probe(item["expression"], distro=args.distro, sage=args.sage,
                               runs=int(item.get("runs", 2)), timeout=args.timeout)}
    output = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for result in pool.map(run, items):
            output.append(result)
            args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False), flush=True)
    if not items:
        args.output.write_text("[]\n", encoding="utf-8")
    print(json.dumps({"candidates": len(output), "stableObservations": sum(x["state"] == "OBSERVED_STABLE" for x in output), "contractsPublished": 0}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
