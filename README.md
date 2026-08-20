# SageMath CTF IDE

面向 SageMath 的专业科学计算 IDE，针对 CTF 密码学、数论、逆向和取证工作流优化。

This repository is the standalone product line. The existing JetBrains plugin repository remains separate:

- Existing plugin: `G:\Projects\sage-ide-support`
- Standalone IDE: `G:\Projects\sage-math-ctf-ide`
- Migrated product plugin baseline: [`plugins/sage-core`](plugins/sage-core)

## Current status

The repository is at **P0: repository and product skeleton**. The current source under `plugins/sage-core` is a migration baseline copied from the existing SageMath JetBrains plugin. It is not yet a finished standalone installer.

Read first:

- [中文产品开发计划](docs/IDE-PLAN.zh-CN.md)
- [迁移地图](docs/MIGRATION-MAP.zh-CN.md)
- [当前状态](docs/STATUS.zh-CN.md)
- [Community product build notes](product/README.zh-CN.md)

## Product principles

1. Build a SageMath-first scientific IDE instead of cloning all of PyCharm.
2. Treat CTF workflows as core product capabilities, not a late plugin collection.
3. Keep SageMath as an external runtime first: native, WSL, Docker, Conda, and later SSH/HPC.
4. Preserve existing Sage language behavior and tests before extracting platform-independent contracts.
5. Keep `sage-ide-support` stable as a separate PyCharm plugin product.
6. Do not bundle SageMath until runtime distribution, SBOM, source correspondence, and license review are complete.

## Build status

The standalone product build is intentionally introduced in stages:

- `core:model`: platform-independent execution and CTF contracts;
- `plugins:sage-core`: migrated Sage language and runtime plugin;
- `plugins:ctf-tools`: planned CTF workflow plugin;
- `product`: planned IntelliJ Community product overlay and installer entry points.

The first implementation milestone establishes the Gradle module graph and core tests. The full IntelliJ Community product build is driven by the pinned upstream checkout described in [`product/README.zh-CN.md`](product/README.zh-CN.md), not by copying the upstream source into this repository.

## License

The product source currently follows the migrated plugin's GPL-3.0 direction. Final product distributions must be audited separately for IntelliJ Platform/community modules, Python/Jupyter components, SageMath, native dependencies, icons, templates, and runtime bundles. See [`NOTICE`](NOTICE).
