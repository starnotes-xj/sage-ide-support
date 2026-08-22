# Sage API index generation contract

This directory contains the reproducible stdlib-only generator used to turn Sage runtime/stubgen exports into the versioned API index consumed by `core:sage-api` and `plugins:sage-core`. The generator never imports or executes Sage.

## Support matrix

The first artifact contract is explicit and must be changed together with generated output:

- SageMath: `10.6` (`--sage-version`);
- Python: `3.11` (`--python-version`);
- stub source: `.pyi`/`.py` files supplied by the selected runtime or `sage-pycharm-stubgen` export;
- signature/documentation source: represented by source manifest `kind` and `locator` when richer adapters are added;
- schema: `1`;
- generator: `sage-api-index-py/0.1`.

`support-matrix.json` records this contract. `source-manifest.json` is the checked-in fixture manifest and demonstrates the same command shape used for runtime/stubgen exports.

## Generate from one root

```powershell
python tools/sage-api-index/generate.py `
  --source-root path/to/sage-stubs `
  --source-locator stubgen/10.6 `
  --sage-version 10.6 `
  --python-version 3.11 `
  --output build/sage-api-index.json `
  --expected tools/sage-api-index/expected-high-value.json `
  --coverage-output build/sage-api-coverage.json
```

## Generate from an auditable source manifest

```json
[{
  "root": "path/to/sage-stubs",
  "kind": "STUB",
  "locator": "sage-pycharm-stubgen/10.6"
},{
  "root": "path/to/sage-runtime-export",
  "kind": "RUNTIME",
  "locator": "sage-runtime/10.6"
},{
  "root": "path/to/signature-export",
  "kind": "SIGNATURE",
  "locator": "sage-signatures/10.6"
},{
  "root": "path/to/docs-export",
  "kind": "DOCUMENTATION",
  "locator": "sage-docs/10.6"
}]
```

Run it with `--source-manifest manifest.json` instead of `--source-root`. Every extracted entry keeps the source kind, locator, and SHA-256 digest. Duplicate declarations are normalized; conflicting signatures become Dynamic and remain visible in diagnostics.

## Reports

- `--output`: schemaVersion=1 index;
- `--raw-output`: raw extractor records;
- `--expected` + `--coverage-output`: missing, alias-aware coverage ratio, dynamic, no-signature, and conflict reports; `--min-coverage` enforces a numeric threshold;
- `--previous` + `--diff-output`: added/removed/changed symbol report;
- malformed source, invalid manifest, unsupported schema fields, or empty roots return exit code 2.

Unknown and Dynamic are preserved. The generator never fabricates a precise type from an unannotated return or `Any`.
