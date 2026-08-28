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

The importer accepts `--probe-timeout` and `--generator-timeout` (both default to 900 seconds) so WSL probing and generator execution have explicit bounds. To create a bounded live checkpoint without invoking the generator, use `--probe-only --probe-json build/sage-api-real/probe.json`; the envelope records the exact command, `mode=LIVE`, runtime probe, and canonical `probeDigest`.

A captured envelope is usable only with explicit `--allow-probe-replay`; the importer checks its schema, LIVE mode, distro/Conda/environment binding, exact command identity, and digest. `probeDigest` is only a canonical consistency digest: it is not a signature or proof of source authenticity. `REPLAY` is local recovery/debug evidence only, never a signature, release attestation, bundled/product support claim, or release evidence; the default import path still performs a live probe.

Import output also includes the independent `sage-api-index-envelope.json` sidecar. Its `schemaVersion` is separate from the index schema, and it binds the artifact/version/provenance, source manifest digest, probe identity, source tree digest, index path/hash/count, coverage, diagnostics/conflicts, and quality result. The receipt binds the final envelope hash; it intentionally does not claim a recursive receipt hash inside the envelope. This is an audit envelope, not a cryptographic signature.

`expected-sage-10.9.json` is deliberately hand-maintained: its six quality entries are a small semantic oracle reviewed against the real ignored index, not a projection generated from that same index. A versioned quality contract requires non-empty `quality` entries and checks source kind/locator/digest, signature count, parameter names/defaults/optionality/keyword-only/variadic flags and type state/expression, return type state/expression, and required non-empty documentation. Scoped coverage identities are cross-checked against the expected symbol set, including duplicate/partition/count/completeness checks. Legacy contracts without `qualityContractVersion` remain coverage-only and report no quality gate.

For the real Sage 10.9 artifact, `expected-sage-10.9.json` is a small, manually audited, non-empty expected contract bound to artifact `wsl-ubuntu-sage-10.9-stubgen-0.8.3`, Sage `10.9`, Python `3.13`, `sage-pycharm-stubgen 0.8.3`, `STUBGEN` provenance, and the recorded probe/tree digests. It must not be replaced by the Sage 10.6 `expected-high-value.json` fixture. Pass it explicitly with `--expected`; an import without an expected contract is recorded as `coverage.scope=UNSCOPED`, so a generator-reported ratio of `1.0` for an empty expected set is not a coverage promise. Non-empty contracts are recorded as `SCOPED` with counts, ratio, completeness, and conflicts. Post-generator output/JSON/summary validation is fail-closed and persists `generator.status=failed` even when the process returned `0`.

The importer requires `failed == 0`, `generated == discovered`, matching Sage/package versions, and at least `generated` `.pyi` files. Generator command/receipt and envelope artifact paths are stored relative to the selected output directory, so two fresh runs in different output roots can be compared byte-for-byte; the receipt records a canonical command digest and binds the final envelope digest without a circular receipt-hash claim. Sage stubgen may add aggregate files such as `all.pyi` and `__init__.pyi`; extra `.pyi` files are allowed and included in `sourceFileCount` and `treeDigest`. It writes an auditable `STUBGEN` manifest and receipt before invoking the existing generator. The currently verified local environment is Sage 10.9, Python 3.13.15, and sage-pycharm-stubgen 0.8.3. These facts describe this machine artifact, not a bundled or release support guarantee.

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

Run it with `--source-manifest manifest.json` instead of `--source-root`. Every extracted entry keeps the source kind, locator, and SHA-256 digest. A same-name group containing `@overload` declarations exposes only those overload variants; the paired implementation declaration is treated as an implementation detail and is not emitted as a third signature. This applies to `typing.overload`, `typing_extensions.overload`, and imported aliases. Receiver annotations on `self`/`cls` are intentionally omitted from the public parameter list, so receiver-specialized overloads remain conservative until the schema has a persistent receiver-domain field. Literal/wide overlap, unknown types, and ordinary duplicate declarations are not guessed away: without an overload group, conflicting signatures become Dynamic and remain visible in diagnostics. Conflict diagnostics expose deterministic `sourceDigest`/`sourceDigests`, declaration and distinct-signature counts, plus sorted canonical `signatureKeys`.

## Reports

- `--output`: schemaVersion=1 index;
- `--raw-output`: raw extractor records;
- `--expected` + `--coverage-output`: missing, alias-aware coverage ratio, dynamic, no-signature, and conflict reports; `--min-coverage` enforces a numeric threshold;
- `--previous` + `--diff-output`: added/removed/changed symbol report;
- malformed source, invalid manifest, unsupported schema fields, or empty roots return exit code 2.

Unknown and Dynamic are preserved. The generator never fabricates a precise type from an unannotated return or `Any`.

## 合同质量审计

`audit_contracts.py` 对生成后的索引做只读质量审计，把“符号已进入索引”和“调用返回值有可证明的类型合同”分开统计。它不会把公共基类、Python 宽泛内建类型、`Any`、未知返回或动态返回伪装成具体 Sage 类型：

```powershell
python tools/sage-api-index/audit_contracts.py `
  --index build/sage-api-real/sage-api-index.json `
  --source-root build/sage-api-real/stubs `
  --output build/sage-api-real/contract-audit.json `
  --markdown build/sage-api-real/contract-audit.md
```

报告中的 `CONCRETE` 只表示源合同给出了限定名；`TYPE_VARIABLE` 表示返回值随调用参数绑定（例如 `gcd(a: T, b: T) -> T`），而 `UNKNOWN`/`DYNAMIC` 保持 fail-closed。`source.missingReturnCount` 是 stubgen 源文件仍未声明返回值的真实数量，不能用空 expected set 的 `coverageRatio=1.0` 替代。

`annotate_stubs.py` 在生成索引前只应用可审计的源合同：Python 数据模型协议、文档中明确的原子 `OUTPUT:` 标签、唯一 Sphinx `:class:` 引用、完整源类索引中唯一的多词类名短语、明确的标量/容器结果语义（例如 Bernoulli 有理数、素幂/除数 Integer、CTF ASCII/bit 工具、稳定的 tuple/list 外层结果），以及有明确“同一参数父类型”语义的 TypeVar 合同（`gcd`、`lcm`、`binomial`、阶乘函数）。对中文 Sage 合同，只接受明确的同类型矩阵变换、已验证的矩阵密度 Rational 和带“对象”标记且唯一的类名；有限域椭圆曲线的 cardinality/Frobenius/plot 与点的 order 使用 Sage 10.9 WSL 运行时核验的具体合同；Integer 的位运算/整除等同样依据文档语义映射。普通单词（`image`、`action`、`representation` 等）和 `matrix`/`polynomial`/`vector`/`element` 等多实现概念会主动排除；联合返回、条件返回、`iterator` 等依赖运行时父对象的描述不会被猜测。重复执行补丁必须幂等；新增 Sage 版本应先重新运行该脚本和 `audit_contracts.py`，再检查 UNKNOWN 是否只因源合同缺失而存在。
