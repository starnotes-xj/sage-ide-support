#!/usr/bin/env python3
"""Report source return shapes that remain UNKNOWN in a generated index."""
from __future__ import annotations

import argparse
import ast
import json
from collections import Counter, defaultdict
from pathlib import Path

import infer_source_returns as inferer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    index = json.loads(args.index.read_text(encoding="utf-8"))
    unknown = {
        entry["qualifiedName"]
        for entry in index.get("entries", [])
        for signature in entry.get("signatures", [])
        if entry.get("kind") in {"FUNCTION", "METHOD"}
        and signature.get("returnType", {}).get("state") == "UNKNOWN"
    }
    files = []
    for path in sorted(args.source_root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        files.append((path, inferer._module_name(path, args.source_root), tree))
    classes = inferer._class_names(files)
    globals_by_module = inferer._module_globals(files, classes)
    attrs = inferer._class_attributes(files, classes, globals_by_module)
    counts: Counter[str] = Counter()
    call_names: Counter[str] = Counter()
    call_samples: defaultdict[str, list[str]] = defaultdict(list)
    call_expr_samples: defaultdict[str, list[str]] = defaultdict(list)
    samples: defaultdict[str, list[str]] = defaultdict(list)
    for path, module, tree in files:
        imports = inferer._imports(tree, module, package_module=path.name == "__init__.py")

        def visit(node: ast.AST, owner: str | None = None) -> None:
            if isinstance(node, ast.ClassDef):
                qualified_owner = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                for child in node.body:
                    visit(child, qualified_owner)
                return
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualified = f"{module}.{node.name}" if owner is None else f"{owner}.{node.name}"
                if qualified in unknown:
                    returns, has_yield = inferer._returns(node.body)
                    analyzer = inferer._FunctionAnalyzer(
                        module, imports, classes, owner, attrs, globals_by_module.get(module)
                    )
                    inferer._local_types(node.body, analyzer)
                    analyzer.bind_parameters(node)
                    if has_yield:
                        shape = "Yield"
                    elif not returns:
                        shape = "NoExplicitReturn"
                    else:
                        shape = ",".join(type(item.value).__name__ for item in returns)
                    counts[shape] += 1
                    if returns and isinstance(returns[0].value, ast.Call):
                        function = returns[0].value.func
                        if isinstance(function, ast.Name):
                            call_names[function.id] += 1
                            if len(call_samples[function.id]) < 8:
                                call_samples[function.id].append(qualified)
                            if len(call_expr_samples[function.id]) < 8:
                                call_expr_samples[function.id].append(ast.unparse(returns[0].value))
                        elif isinstance(function, ast.Attribute):
                            call_names[function.attr] += 1
                            if len(call_samples[function.attr]) < 8:
                                call_samples[function.attr].append(qualified)
                            if len(call_expr_samples[function.attr]) < 8:
                                call_expr_samples[function.attr].append(ast.unparse(returns[0].value))
                    if len(samples[shape]) < 12:
                        samples[shape].append(qualified)
                return
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.ClassDef):
                    visit(child, owner)

        for node in tree.body:
            visit(node)
    payload = {
        "unknown": len(unknown),
        "shapes": counts,
        "callNames": call_names,
        "callSamples": call_samples,
        "callExprSamples": call_expr_samples,
        "samples": samples,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=dict) + "\n", encoding="utf-8")
    print(json.dumps({
        "unknown": len(unknown),
        "sourceShapes": sum(counts.values()),
        "shapes": counts,
        "callNames": call_names.most_common(40),
        "callSamples": {name: call_samples[name] for name, _ in call_names.most_common(40)},
        "callExprSamples": {name: call_expr_samples[name] for name, _ in call_names.most_common(40)},
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
