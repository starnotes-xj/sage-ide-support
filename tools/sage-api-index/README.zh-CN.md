# Sage API index generation contract

This directory contains the reproducible stdlib-only generator used to turn Sage runtime/stubgen exports into the versioned API index consumed by `core:sage-api` and `plugins:sage-core`. The generator never imports or executes Sage.

## Bundled fixture baseline

The checked-in bundled baseline is a fixture contract, not real runtime support:

- SageMath: `10.6` (`--sage-version`);
- Python: `3.11` (`--python-version`);
- provenance: `FIXTURE`;
- stub source: `.pyi`/`.py` files supplied by the selected runtime or `sage-pycharm-stubgen` export;
- signature/documentation source: represented by source manifest `kind` and `locator` when richer adapters are added;
- schema: `1`;
- generator: `sage-api-index-py/0.1`.

`support-matrix.json` separates the checked-in fixture baseline from locally verified artifacts. `source-manifest.json` remains the fixture example; local WSL outputs stay under ignored `build/sage-api-real/`.

## Import the verified WSL Conda artifact

The importer probes Sage and `sage-pycharm-stubgen` through an explicit distro and Conda command. It does not depend on interactive `conda activate` or the default WSL distro:

```powershell
python tools/sage-api-index/import_wsl_artifact.py `
  --distro Ubuntu `
  --conda /home/starnotes/miniconda3/bin/conda `
  --conda-env sage `
  --source-root "\\wsl.localhost\Ubuntu\home\starnotes\sage_typings_083" `
  --generation-report "\\wsl.localhost\Ubuntu\home\starnotes\sage_typings_083\generation-report.json" `
  --output-dir build/sage-api-real
```

The importer requires `failed == 0`, `generated == discovered`, matching Sage/package versions, and at least `generated` `.pyi` files. Sage stubgen may add aggregate files such as `all.pyi` and `__init__.pyi`; extra `.pyi` files are allowed and included in `sourceFileCount` and `treeDigest`. It writes an auditable `STUBGEN` manifest and receipt before invoking the existing generator. The currently verified local environment is Sage 10.9, Python 3.13.15, and sage-pycharm-stubgen 0.8.3. These facts describe this machine artifact, not a bundled or release support guarantee.

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
