# Sage IDE Support

[English](README.md) | [简体中文](README.zh-CN.md)

> Writing crypto Sage scripts? Stop switching to the source for every method
> name — completion and docs are right in the IDE.

![Sage IDE demo](docs/demo.gif)

First-class `.sage` file support in PyCharm — the same code-insight experience
as `.py` files, while keeping `.sage` as its **own file type** (not "Python
with a different extension"):

- **Dedicated "Sage" file type** — a Python *dialect* language, so the full
  Python stack (completion, inspections, type inference, refactorings)
  applies to `.sage` files through the language-base mechanism.
- **Transparent Sage generator-sugar parsing** — `R.<x> = GF(2)[]` and
  `F.<a> = GF(2^8, modulus=x^8 + ...)` parse as real multi-target assignments:
  no error squiggles, `F` is typed, `x`/`a` resolve.
- **Implicit `sage.all` namespace** — the namespace the `sage` command
  injects at runtime is visible to static analysis: `GF`, `Integer`, ...
  resolve without imports, through the same extension point PyCharm uses for
  IPython built-ins.
- **Run configurations** — execute `.sage` files with the `sage` command
  (native, WSL or Docker) instead of a Python interpreter, with a gutter run
  icon.
- **Live templates** for common Sage constructs (polynomial rings, finite
  fields, ...) and the official SageMath icosahedron icon.

## How it works with sage-pycharm-stubgen

This plugin is the *mechanism* layer; the *type information and documentation*
live in the stub data layer produced by the companion project
**[sage-pycharm-stubgen](https://github.com/starnotes-xj/sage-pycharm-stubgen)**.
The plugin deliberately carries **zero Sage domain knowledge**: it resolves
`GF` to the declaration inside the installed `site-packages/sage/*.pyi`
stubs, and every method type / Chinese Quick-Doc comes from those stubs.

## Quick start

1. **Generate the stubs** inside your Sage environment (WSL / native / Docker):
   ```bash
   python -m pip install sage-pycharm-stubgen
   sage-pycharm-stubgen --install
   ```
2. **Install this plugin**: Settings → Plugins → ⚙ → Install Plugin from Disk →
   the zip from [Releases](https://github.com/starnotes-xj/sage-ide-support/releases) → restart.
3. **Open any `.sage` file** (e.g. with `R.<x> = GF(2)[]` and `e = F.from_integer(0x57)`):
   `GF` has no unresolved-reference squiggle, `F.`/`e.` complete with colored method
   icons + type text + parameter lists, Ctrl+Q shows Chinese docs, and Run uses the
   `sage` command.
4. After (re)generating stubs, run **File → Invalidate Caches / Restart** once.
5. Optional full-Chinese docs: `sage-pycharm-stubgen translate-docs --apply-only`.

## Requirements

| Dependency | Version / condition |
|---|---|
| PyCharm | **2026.1 – 2026.3** (builds 261–263; `since-build="261"` / `until-build="263.*"`) |
| Python plugin | bundled with PyCharm (`com.intellij.modules.python`) |
| SageMath | any recent version in WSL, native or Docker, configured as the project SDK |
| sage-pycharm-stubgen | **≥ 0.8.0**: generate and install the stubs with `sage-pycharm-stubgen --install` inside the Sage environment; the Chinese curated docs and the finite-field element-class return annotations ship since 0.7.0, and 0.8.0 adds an **opt-in machine-translation layer** — `sage-pycharm-stubgen translate-docs --apply-only` fills the remaining English Quick-Docs with Chinese from a bundled shared cache |

After installing or regenerating stubs, run **File → Invalidate Caches / Restart**
once so PyCharm re-indexes the updated stubs.

## Installation

1. Get the plugin zip:
   - [Releases](https://github.com/starnotes-xj/sage-ide-support/releases)
     (a tagged release attaches the CI-built zip), or
   - any push's CI artifacts: **Actions → the latest `build` run →
     Artifacts → `sage-ide-support`**.
2. PyCharm → **Settings → Plugins → ⚙ → Install Plugin from Disk** → select
   the zip → restart.
3. Open a `.sage` file (e.g. with `R.<x> = GF(2)[]` and
   `e = F.from_integer(0x57)`); `GF` has no unresolved-reference squiggle,
   `F.` and `e.` complete with colored method icons + type text + parameter
   lists, and Ctrl+Q shows the Chinese docs from the stubs.

If `.sage` was manually associated with another type in
**Settings → Editor → File Types**, remove that association so this plugin's
Sage file type applies.

## Building

```powershell
$env:JAVA_HOME = "D:\Java\jdk-21"
gradle buildPlugin --no-daemon   # produces build/distributions/*.zip
```

Requires JDK 21, Kotlin 2.3.0 and the IntelliJ Platform Gradle Plugin
(configured against the local PyCharm installation as the plugin SDK).

## Releasing

Push a `v*` tag: the CI builds the plugin and publishes it to **both**
the [JetBrains Marketplace](https://plugins.jetbrains.com) (via the
`PUBLISH_TOKEN` repository secret) and a
[GitHub Release](https://github.com/starnotes-xj/sage-ide-support/releases)
with the zip attached.  Bump the version in `build.gradle.kts` for every
release — the Marketplace rejects duplicate versions.

## Related projects

- [sage-pycharm-stubgen](https://github.com/starnotes-xj/sage-pycharm-stubgen) —
  the stub data layer consumed by this plugin (companion, required).
- [JetBrains/intellij-community PR #3614](https://github.com/JetBrains/intellij-community/pull/3614) —
  a generic `typeInformationGenerator` extension point so PyCharm can invoke
  and refresh the stub engine.
- [sagemath/sage PR #42670](https://github.com/sagemath/sage/pull/42670) /
  [#42672](https://github.com/sagemath/sage/pull/42672) — upstream Sage
  annotations feeding the same type-information chain.

## License

[GPL-3.0](LICENSE). Derivative works must remain open under the same
license, and the original copyright notice must be preserved.
