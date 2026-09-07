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

The importer probes Sage and `sage-pycharm-stubgen` through an explicit distro and Conda environment. By default, `--conda auto` resolves Conda from the current WSL user's `$HOME` and `PATH`; it does not depend on a hard-coded Linux username, interactive `conda activate`, or the default WSL distro:

```powershell
$wslUser = (wsl -d Ubuntu --exec /bin/bash -lc 'printf "%s" "$USER"').Trim()

python tools/sage-api-index/import_wsl_artifact.py `
  --distro Ubuntu `
  --conda auto `
  --conda-env sage `
  --source-root "\\wsl.localhost\Ubuntu\home\$wslUser\sage_typings_083" `
  --generation-report "\\wsl.localhost\Ubuntu\home\$wslUser\sage_typings_083\generation-report.json" `
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

`annotate_stubs.py` 在生成索引前只应用可审计的源合同：Python 数据模型协议、文档中明确的原子 `OUTPUT:` 标签、唯一 Sphinx `:class:` 引用、完整源类索引中唯一的多词类名短语、明确的标量/容器结果语义（例如 Bernoulli 有理数、素幂/除数 Integer、CTF ASCII/bit 工具、稳定的 tuple/list 外层结果），以及有明确“同一参数父类型”语义的 TypeVar 合同（`gcd`、`lcm`、`binomial`、阶乘函数）。对 CTF 密码模块，只有文档同时明确“整数输入→Integer”和“list-like 输入→GF(2) 位向量”时才生成参数重载；密钥调度列表元素合同、DES/PRESENT 位向量变换、S-DES 二进制串/排列和长度尺寸合同同样由文档语义驱动。对中文 Sage 合同，只接受明确的同类型矩阵变换、已验证的矩阵密度 Rational 和带“对象”标记且唯一的类名；有限域椭圆曲线的 cardinality/Frobenius/plot 与点的 order 使用 Sage 10.9 WSL 运行时核验的具体合同；Integer 的位运算/整除等同样依据文档语义映射。普通单词（`image`、`action`、`representation` 等）和 `matrix`/`polynomial`/`vector`/`element` 等多实现概念会主动排除；没有成对且明确参数关系的条件返回、无法确认的迭代元素和联合返回仍保持 fail-closed。重复执行补丁必须幂等；新增 Sage 版本应先重新运行该脚本和 `audit_contracts.py`，再检查 UNKNOWN 是否只因源合同缺失而存在。

### 纯 Python 源码批量合同（非白名单）

WSL Sage 安装同时包含可审计的纯 Python 实现。`infer_source_returns.py` 用 AST 扫描这些源文件：只接受所有成功返回路径形状一致的字面量/容器/迭代器/具体 Sage 构造、明确的 Python 返回注解、简单局部变量、稳定 `self.attr` 赋值、身份/成员比较与同型闭运算，以及同类或同模块包装函数传播；无条件抛异常标注为 `NoReturn`，没有显式 `return` 的普通函数按 Python 语义标注为 `None`。循环、动态属性、参数相关分支和无法解析的工厂会保留未知，不会降级为 `Any` 或公共基类。

```powershell
wsl.exe -d Ubuntu -- python3 tools/sage-api-index/infer_source_returns.py `
  --source-root /home/<user>/miniconda3/envs/sage/lib/python3.13/site-packages/sage `
  --output build/sage-source-contracts.json

python tools/sage-api-index/annotate_stubs.py `
  --stub-root build/sage-api-real/stubs `
  --source-contracts build/sage-source-contracts.json
```

`apply_source_contracts.py` 也可以单独执行，并通过 `--index` 只修改当前索引中仍为 `UNKNOWN` 的函数/方法。该批处理按限定名逐个写入 `.pyi`，保留已有更具体合同且可重复运行；应在每次 Sage 版本变更后重新生成源合同并运行审计。

当纯 Python 实现调用 Cython/生成 stub 中已有的具体成员时，可把同一版本索引传给推断器：

```powershell
wsl.exe -d Ubuntu -- python3 tools/sage-api-index/infer_source_returns.py `
  --source-root /home/<user>/miniconda3/envs/sage/lib/python3.13/site-packages/sage `
  --index build/sage-api-curated-type-contracts.json `
  --output build/sage-source-contracts-index-assisted.json
```

`--index` 只导入唯一、已知的具体 `CLASS` 成员合同，以及“返回值 TypeVar 与多个实参同型”的参数合同（例如 `gcd(a: T, b: T) -> T`）。同时，`typing.Self` 会归一化为接收者合同，`sage.type_contracts.*Element[Self]` 只作为已命名的父对象/域关系合同保留；这两类关系不是公共基类，最终由具体接收者和调用上下文解析。索引中的父边只补全 Cython/扩展类的成员查找，不改变最终返回类型。`receiver.element_class(...)` 只有在源码证明 `Element` 类时才产生父对象关系，否则保持未知；因此 `element_class -> type` 不会伪装成元素返回。多重载、公共结构基类、无约束 TypeVar 和动态工厂会被拒绝。这样可解析 `self.codomain().zero()`、`self.attr.method()` 等嵌套调用，同时保持“公共基类只用于成员查找，不能作为最终返回类型”的约束。

### 父对象合同传播（非白名单）

`propagate_parent_contracts.py` 读取已生成索引中的继承图和父类方法合同，按最近继承层传播唯一且精确的返回类型。它只接受内建/容器、`Self`、`NoReturn` 或继承图中的叶 Sage 类；公共基类、泛化 `ParentElement[...]`、多父冲突和动态分支均保持未知，因此不会把公共基类当作最终返回类型。

### 运行时动态合同探针

`probe_runtime_contracts.py` 接收经过人工检查的 JSONL 候选表达式，在 WSL Sage 中每个表达式至少独立运行两次。每项输出完整观测类型与错误；成功且类型一致时标记 `OBSERVED_STABLE`，`observedReturnType` 包括 Sage、Python 内建及第三方类型，`returnType` 始终为空。重复默认调用不能证明其他参数/状态下的结果，写入函数合同还须源码分支证明及 IDE 类索引可解析检查。进程独立不等于文件系统隔离：不得自动执行缓存写入、会话保存、进程管理等未审查候选。

默认并发 2 项，可用 `--jobs 1..4` 调整；WSL 内 `timeout` 限制每次运行，超时和无效输出会记录后继续。每完成一项就打印并保存结果。`--sage` 必须指定实际解释器位置，避免写死用户名。

```powershell
python tools/sage-api-index/probe_runtime_contracts.py `
  --candidates build/sage-runtime-candidates.jsonl `
  --output build/sage-runtime-observations.json `
  --sage /path/to/sage/env/bin/sage --jobs 2 --timeout 30
```

```powershell
python tools/sage-api-index/propagate_parent_contracts.py `
  --stub-root build/sage-api-real/stubs `
  --index build/sage-api-real/sage-api-index.json `
  --contracts-output build/sage-parent-contracts.json
```

传播后应重新运行 `generate.py` 和 `audit_contracts.py`；脚本本身幂等，重复执行不会覆盖现有合同。
