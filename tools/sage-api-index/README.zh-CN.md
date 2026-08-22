# Sage API index generation contract

This directory contains the reproducible stdlib-only generator used to turn Sage runtime/stubgen exports into the versioned API index consumed by `core:sage-api` and `plugins:sage-core`. The generator never imports or executes Sage.

## Support matrix

The first artifact contract is intentionally explicit and must be changed together with generated output:

- SageMath: `10.6` (`--sage-version`);
- Python: `3.11` (`--python-version`);
- stub source: `.pyi`/`.py` files supplied by the selected runtime or `sage-pycharm-stubgen` export;
- signature/documentation source: represented by the source kind and locator when richer adapters are added;
- schema: `1`;
- generator: `sage-api-index-py/0.1`.

`support-matrix.json` is machine-readable metadata for CI and artifact review.
