# SageMath CTF IDE

面向 SageMath 的专业科学计算 IDE，针对 CTF 密码学、数论、逆向和取证工作流优化。

This repository is the standalone product line. The existing JetBrains plugin repository remains separate:

- Existing plugin: `G:\Projects\sage-ide-support`
- Standalone IDE: `G:\Projects\sage-math-ctf-ide`
- Migrated product plugin baseline: [`plugins/sage-core`](plugins/sage-core)

## Current status

The repository is at **P1: Community product integration and SageMath Runtime Manager foundation**. The current source under `plugins/sage-core` is a migration baseline copied from the existing SageMath JetBrains plugin; `core/runtime` provides the local ZIP install/verification foundation. The next primary product track is versioned Sage API indexing, type inference, completion, signatures, documentation, navigation, and source maps. Jupyter remains an optional compatibility layer. It is not yet a finished standalone installer.

Read first:

- [中文产品开发计划](docs/IDE-PLAN.zh-CN.md)
- [迁移地图](docs/MIGRATION-MAP.zh-CN.md)
- [当前状态](docs/STATUS.zh-CN.md)
- [Community product build notes](product/README.zh-CN.md)

## Product principles

1. Build a complete SageMath-first IntelliJ product instead of cloning all of PyCharm.
2. Treat CTF workflows as core product capabilities, not a late plugin collection.
3. Provide a SageMath Runtime Manager like IDEA JDK and PyCharm Python SDK management.
4. Keep SageMath execution outside the JVM, while making Runtime download/install/select a first-class IDE capability.
5. Default CTF execution to unlimited time (`null`); require explicit deadlines when desired and keep cancellation/output limits.
6. Make Sage API indexing, type inference, completion, signatures, documentation, navigation, and source maps the primary product differentiator; use versioned data instead of one-off function patches.
7. Treat Jupyter as an optional execution/compatibility layer, not the primary Sage editing experience.
8. Preserve existing Sage language behavior and tests before extracting platform-independent contracts.
9. Keep `sage-ide-support` stable as a separate PyCharm plugin product.
10. Separate IDE distribution, SageMath Runtime distribution, SBOM, source correspondence, and license review.

The primary motivation and specification for Sage language intelligence is documented in [`docs/SAGE-INTELLIGENCE-SPEC.zh-CN.md`](docs/SAGE-INTELLIGENCE-SPEC.zh-CN.md).

## Build status

The standalone product build is intentionally introduced in stages:

- `core:model`: platform-independent execution and CTF contracts;
- `plugins:sage-core`: migrated Sage language/runtime plugin and future Sage intelligence host;
- `plugins:ctf-tools`: planned CTF workflow plugin;
- `product`: Community IntelliJ product overlay and installer entry points, with further cross-platform work pending.

The first implementation milestone establishes the Gradle module graph and core tests. The full IntelliJ Community product build is driven by the pinned upstream checkout described in [`product/README.zh-CN.md`](product/README.zh-CN.md), not by copying the upstream source into this repository.

## License

The product source currently follows the migrated plugin's GPL-3.0 direction. Final product distributions must be audited separately for IntelliJ Platform/community modules, Python/Jupyter components, SageMath, native dependencies, icons, templates, and runtime bundles. See [`NOTICE`](NOTICE).
