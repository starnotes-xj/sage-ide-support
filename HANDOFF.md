# SageMath CTF IDE 交接快照

> 更新时间：2026-08-23（Runtime Manager 与 CTF 会话状态同步；CTF 暂不合入 main）。本文只保留当前状态、可复核证据、剩余风险和下一步；历史失败过程不在此重复记录。

## 1. 总体状态

项目定位：基于 IntelliJ Community 的独立 SageMath CTF IDE。核心差异化是 **SageMath 代码智能 + 可管理 Sage Runtime + CTF 工作台**，不是把插件 ZIP 或普通 PyCharm 安装目录冒充完整产品。

当前判断：

- **P1 Community 产品接入/Windows 构建链：已完成开发基线，尚未完成最终发行门。** Community overlay、Sage product properties、Sage Core bundled plugin、Windows x64/aarch64 installer、sidecar、法律文件 overlay、x64 安装/启动/卸载 smoke 和 FinalCheck 都有历史验证证据。
- **Sage API importer/index integration：当前进入 scoped Sage API integration。** 已完成 generator 修复后的真实 Sage 10.9 外部 index 消费验证：schema 1、84159 entries 可由 `core:sage-api` reader/query 加载；entry provenance 以 `sources` 的 `STUB` locator/digest 和顶层 `sourceDigests` 保留。它不代表 Sage 全量代码智能、正式发行或将全量 index 放入 bundled/resource/product；manifest-level `provenance`/`sourceSpecs`/`treeDigest`/coverage/diagnostics 仍属于 importer sidecar/report 质量门。
- **P2 CTF MVP/Math Lab：实现会话已完成，后续只从 `parallel/ctf-mvp` 进入主线整合。** `parallel/ctf-mvp`（当前工作分支，最新提交 `62847f0`；与 `integration/ctf-mvp` 共享基础 MVP 内容但不是其 Git 后继）交付独立 `plugins/ctf-tools`、CTF project/challenge/profile、flag 扫描、运行历史/evidence、Crypto/Encoding helpers、loopback CyberChef-server 和图形化 CTF Math Lab；Math Lab 覆盖群/环/域、椭圆曲线、RSA、DH、DES 的专用表单、预检、运算追踪、可视化、教学步骤和本地化。`integration/ctf-mvp` 是旧的基础 MVP/安全加固候选，不再与 `parallel/ctf-mvp` 并行合并或重复 cherry-pick。
- **Runtime Manager：核心实现已进入当前 `main`，产品 UI/真实端点验收仍需单独完成。** 当前 `main` 已包含 `a2c7fdc`（`让 Runtime Manager 统一拥有 Sage SDK 执行边界`），其提交包含 Runtime Manager/Sage SDK 集成；旧 Runtime 完成会话已物理清除，不再作为独立分支归档或直接 rebase/merge。已交付 signed Catalog、verified mirror/cache、选择/切换/移除/回滚生命周期、Settings/Project SDK binding、Native/WSL/Docker/SSH target-aware command/probe 和显式路径映射。
- **发行：Windows 构建链已验证，但不能称为正式 release。** 签名、法律审批、Linux/macOS、真实 arm64 主机 smoke 和自动更新仍未完成。

当前不再使用旧的“7/9/14 类能力”粗略计数；以下状态以已完成会话、当前主线整合状态和可复核测试证据分别记录。

## 2. 已完成或已有可复核基线

### 产品与构建

- 产品仓库：`G:\Projects\sage-math-ctf-ide`。
- 官方 IntelliJ Community 底座：`G:\Projects\intellij-community-sage-ide`，固定 commit `b0001cd6c53979b384def7a1e3febe061e2ef687`，只读并要求 clean。
- Staging 构建使用 JDK 25、Bazelisk `1.29.0`、JetBrains Bazel `9.1.0-jb_20260505_126`、build `263.SNAPSHOT`。
- 已有 Sage 专用 Bazel dev/installer target、Community product properties、外部 Sage Core 插件注入和 Windows 双架构构建链。
- 历史 hardened 产物和证据见：
  - `G:\sage-build\bundled-next\release-hardening-legal-fix-final.log`
  - `G:\sage-build\bundled-next\release-hardening-audit-legal-fix-all.json`
  - `G:\sage-build\bundled-next\x64-installer-smoke-legal-fix.log`
  - `G:\sage-build\bundled-next\finalcheck-legal-fix.log`

### Sage API intelligence

- `core:sage-api`：版本化 schema/domain model、normalizer、严格 JSON reader/loader、不可变 query、source/alias/parent/conflict 处理。
- `plugins:sage-core`：消费 bundled/external index；已验证唯一 KNOWN factory return type、父类/别名成员闭包和矩阵成员查询；没有 `solve_right` 名称特例。
- `tools/sage-api-index/generate.py`：Python 标准库 `.pyi`/`.py` extractor，支持稳定 index、source digest、coverage、diagnostics、diff 和 gate。
- 当前 checked-in bundled index 仍是有限 fixture/矩阵 slice，不代表 Sage 全量覆盖。

### 真实 Sage 10.9 artifact 导入

真实 Sage 10.9 artifact 证据基线提交：`1e1ba42 Make Sage 10.9 importer coverage evidence auditable`。

人工维护 contract：`tools/sage-api-index/expected-sage-10.9.json`，绑定：

- artifact `wsl-ubuntu-sage-10.9-stubgen-0.8.3`；
- Sage `10.9`、Python `3.13`/实际 `3.13.15`；
- `sage-pycharm-stubgen 0.8.3`、`STUBGEN` provenance；
- probeDigest `44945e3f...`；treeDigest `69d0524a...`；expectedDigest `58be9132...`。

两次默认 LIVE full import 均 exit `0`，分别输出到 ignored：

- `build/sage-api-real/live-1`
- `build/sage-api-real/live-2`

两次结果的 artifact/runtime/probe/tree/report/file/expected/coverage 摘要一致：

- stub files `2839`；generation report `discovered/generated=2837/2837`、`failed=0`；
- expected `6/6` 命中，`coverage.scope=SCOPED`、ratio `1.0`、missing `0`；
- final fresh generator recheck（无 `--allow-conflicts`）重建 `84159` entries、`24` diagnostics，`coverage.scope=SCOPED`、expected `6/6`、`coverageRatio=1.0`、`conflicts=0`、`isComplete=true`；`24` 条为 duplicate diagnostics，不是冲突；这不是 Sage 全量代码智能证明。

显式 replay 结果：`build/sage-api-real/replay-scoped`，`probeMode=REPLAY`，probeDigest 与 LIVE 相同。Replay 只用于本机恢复/调试；probeDigest 是 canonical consistency digest，不是签名、来源真实性证明或 release attestation。

### 本轮 scoped API index consumption

- fresh generator recheck 使用 `build/sage-api-real/live-1/source-manifest.json`，命令未传 `--allow-conflicts` 或 `--allow-missing`，输出到 ignored `build/sage-api-real/integration-recheck-1/`；exit `0`，summary 为 `sources=2839`、`rawSymbols=84187`、`entries=84159`、`diagnostics=24`、`missing=0`。coverage report 为 expected `6/6`、`coverageRatio=1.0`、`conflicts=[]`、`isComplete=true`；24 条是 duplicate diagnostics。
- 同一真实输入第二次生成到 `integration-recheck-2/` 仍 exit `0`。两次 `index.json` SHA-256 均为 `4f8bd2fc2d26ee5b6f14dbbf1eab920e72d46d8573ef10fac95249f700df91f6`；`raw.json` 与 `coverage.json` 也逐字节一致。
- JVM consumer probe 通过 `SageApiIndexLoader.fromPath` + `SageApiIndexQuery` 读取真实 10.9 index，exit `0`；断言 `schemaVersion=1`、Sage `10.9`/Python `3.13`、84159 entries、2839 source digests、`STUB` entry source/digest、签名参数、KNOWN return type、documentation summary/body，以及 `Matrix.solve_right`/`determinant` member query 均成功。
- core reader/query 只消费版本字段、`sourceDigests`、entries、entry sources/signatures/parameters/returnType/documentation；manifest 的 `artifactId`、`provenance=STUBGEN`、`sourceSpecs`、`treeDigest`、coverage、diagnostics 不进入当前 `SageApiIndex`，后续应以 versioned sidecar/envelope 保留，不把 `STUBGEN` 直接写成 Kotlin entry source kind。
- 消费路径保持受控：`-Dsage.api.index` 外部路径经 `SageApiIndexService.reload`/`SageApiIndexLoader` 加载；full 84159-entry output 仍是 ignored validation artifact，没有复制进 bundled/resource/product。

## 3. 当前剩余工作

### 最高优先级：Sage intelligence verification and scoped API integration

0. 当前 full-index/query 与 representative completion/type gates 已通过；继续推进时优先扩大人工 expected contract 与外部 artifact 的可审计语义质量，不重复枚举同一 root popup。下一项高价值验证是：从 full artifact 选取带 KNOWN return 的外部-only factory/class path，证明 assignment 后 PSI member completion/type propagation；当前 `SageApiClassMembersProvider` 仍以真实 PyClass qualifiedName 为 owner，不能仅凭 query metadata 宣称所有 external-only owner 已进入 PSI。

1. 保持已修复 generator 的 no-`--allow-conflicts` gate 和 deterministic 输出；没有新的实际证据时，不继续重写 conflicts 算法。
2. 定义受控的 versioned/scoped API index envelope 或 sidecar，把 artifact/provenance/treeDigest/coverage/diagnostics 与当前可消费 index 明确关联；entry source kind 继续按 schema 映射为 `STUB`，不把 `STUBGEN` 伪装成 Kotlin source kind。
3. 扩大一小组人工维护的 Sage 10.9 expected contract，并把签名、参数、返回类型、documentation 的质量门拆成可审计 scoped checks；不得从 84159-entry index 自动反推全量 expected。
4. 若将某个 slice 推进 bundled/resource，只允许经过 reviewed、versioned、scoped artifact；ignored full index 继续只走外部 `-Dsage.api.index` 验证路径。
5. Gradle 的 `plugins:sage-core` test path 已可运行；直接 IDE/.iml module classpath 尚未证明，若未来选择该路径再单独处理 module/namespace 依赖，不把它与当前成功的 Gradle integration 混淆。
6. 下一项高价值 Sage gate：从 full artifact 选择带 KNOWN return 的 external-only factory/class path，证明 assignment 后 PSI member completion/type propagation；当前 `SageApiClassMembersProvider` 仍依赖真实 PyClass qualifiedName 作为 owner，不能仅凭 query metadata 宣称所有 external-only owner 已进入 PSI。

### Runtime 与 CTF

- Runtime Manager 核心实现已落入当前 `main`：`a2c7fdc`（`让 Runtime Manager 统一拥有 Sage SDK 执行边界`）已提交 14 个 Runtime Manager/Sage SDK 集成文件，并保留其 Lore 字段；提交前验证包含 `:core:runtime:test`、`:plugins:sage-core:test`、`:plugins:sage-core:buildPlugin`、`verifyPluginProjectConfiguration` 和 `verifyPlugin`（PY-261/PY-262 Compatible）。旧 Runtime 完成会话删除前的 fresh `:core:runtime:test -PrunRuntimeTests=true` 为 8 suites/38 tests、0 failures/errors，作为历史补充证据。
- CTF MVP 实现会话已完成：最新 `parallel/ctf-mvp` tip `62847f0`（当前工作分支；与 `integration/ctf-mvp` 共享基础 MVP 内容但不是其 Git 后继）交付 `plugins/ctf-tools`、Challenge Profile UI/model、flag scanner、bounded script execution、run history/evidence、Crypto/Encoding helpers、loopback CyberChef adapter 和图形化 CTF Math Lab。Math Lab 提供群/环/域、椭圆曲线、RSA、DH、DES 的专用表单、预检、运算追踪、可视化、教学步骤与中英文案。最新独立 worktree fresh `:core:model:test :plugins:ctf-tools:test :plugins:ctf-tools:buildPlugin -PrunModelTests=true -PrunCtfToolsTests=true --no-daemon --console=plain --rerun-tasks` 为 `BUILD SUCCESSFUL`；15 suites/51 tests、skipped=0、failures=0、errors=0，exit `0`。
- Runtime Manager 核心已在当前 `main`；后续只补真实 Settings/Project SDK UI、WSL/Docker/SSH 端点、并发锁和 crash fault-injection。CTF 仍暂不合入：后续只从 `parallel/ctf-mvp` 进入主线，`integration/ctf-mvp` 不再作为第二个待合并来源。真实 Settings/Project SDK UI、WSL/Docker/SSH 端点、live CyberChef-server、Math Lab IDE live ToolWindow、完整产品 smoke 和默认插件/分发接入仍待验证。Jupyter 继续作为可选执行/兼容层，不作为 Sage 原生编辑体验的前置条件。

### 发行与跨平台

- Authenticode/正式签名服务。
- SPDX `NOASSERTION`、`SPDX_WORK_IN_PROGRESS`、deprecated `GPL-2.0` 的法律审查。
- Linux/macOS 产品包、真实 arm64 主机 smoke、自动更新/公证。
- 远程 Sage Runtime catalog/probe。

## 4. 发行证据与已知风险

历史 hardened audit：`errors=0`、`warnings=8`、`passed=false`。已验证 sidecar、SPDX JSON 可解析、法律文件存在和 x64 smoke；但 4 个 EXE 未签名、SPDX 仍有 WIP/NOASSERTION、存在 deprecated `GPL-2.0` 法律事项。因此不能称为正式 release-ready。

已验证代码基线包含 `1e1ba42` 的 importer slice 与本轮 conflicts diagnostic slice；`.agent-teams/` 是本地协作归档，不应提交。

## 5. 仓库与实现边界

- 允许修改：`G:\Projects\sage-math-ctf-ide` 和 `G:\sage-build\staging-build6`。
- 不修改：`G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr`、官方 `G:\Projects\intellij-community-sage-ide`。
- 不手工修改生成的 installer、SPDX、distribution 或 ignored build artifact 来伪造证据。
- Runtime/Sage 解释器保持在 JVM 外部进程；IDE 负责发现、下载、校验、安装、选择、切换和回滚。
- SageMath 按“Python 的超集”描述；除非有完整迁移计划，不把 Sage 改成脱离 Python PSI 的完全独立语言。

## 6. 最近切片验证

- Python importer/generator 回归：`python -m unittest tools.sage-api-index.test_import_wsl_artifact tools.sage-api-index.test_generate`，53 tests，exit `0`；`py_compile` 与 `git diff --check` 均 exit `0`。
- `:core:sage-api:test -PrunSageApiTests=true`、`:plugins:sage-core:test -PrunSageCoreTests=true` 和 focused completion/type tests 均重新取得 `BUILD SUCCESSFUL`；这些测试使用 checked-in scoped fixture，不声称把 84159-entry artifact 放入 bundled resource。
- fresh generator recheck 使用实际 WSL Sage 10.9 manifest、未传 `--allow-conflicts`：exit `0`，`sources=2839`、`rawSymbols=84187`、`entries=84159`、`diagnostics=24`、`coverage.scope=SCOPED`、expected `6/6`、`coverageRatio=1.0`、`conflicts=0`、`isComplete=true`。
- JVM consumer probe 对 ignored full output 的 `SageApiIndexLoader`/`SageApiIndexQuery` 断言 exit `0`；full output 仍未进入 bundled/resource/plugin/product/installer/release。
- Runtime Manager 独立 worktree fresh 验证：`:core:runtime:test -PrunRuntimeTests=true --no-daemon --console=plain`，38 tests、skipped=0、failures=0、errors=0，exit `0`。
- 本轮主线 bundled-Python focused verification：`:core:runtime:test :plugins:sage-core:test -PrunRuntimeTests=true -PrunSageCoreTests=true "-Psage.ide.localSdk=D:/JetBrains/PyCharm" --no-daemon`，`BUILD SUCCESSFUL`；之后 service-owned Runtime Manager API 增量再次执行 `:plugins:sage-core:compileKotlin :core:runtime:test :plugins:sage-core:test -PrunRuntimeTests=true -PrunSageCoreTests=true "-Psage.ide.localSdk=D:/JetBrains/PyCharm" --no-daemon --console=plain`，`BUILD SUCCESSFUL`。
- service API 增量后的 fresh packaging：`:plugins:sage-core:buildPlugin :plugins:sage-core:verifyPluginProjectConfiguration --no-daemon --console=plain "-Psage.ide.localSdk=D:/JetBrains/PyCharm"`，`BUILD SUCCESSFUL`；configuration warnings 仍为 since-build `261` < target `262`、until-build 限制未来版本、Java/Kotlin target `25` 与 since-build `261` 的 Java `21` 要求不一致。随后 fresh `:plugins:sage-core:verifyPlugin` 也 `BUILD SUCCESSFUL`：PY-261.27258.51 与 PY-262.10315.23 均 `Compatible`，2 deprecated / 28 experimental notices。
- CTF `parallel/ctf-mvp` 最新 worktree fresh 验证：`:core:model:test :plugins:ctf-tools:test :plugins:ctf-tools:buildPlugin -PrunModelTests=true -PrunCtfToolsTests=true --no-daemon --console=plain --rerun-tasks`，`BUILD SUCCESSFUL`；CTF XML 汇总 15 suites/51 tests、skipped=0、failures=0、errors=0，exit `0`。Math Lab 相关 `MathLabCompleteTest`、`MathLabPanelSmokeTest`、`MathLabPanelTest`、`MathLabPresenterTest` 与 factor-analysis tests 均包含在该汇总中。
- CTF plugin ZIP fresh audit 通过：`ctf-tools/build/distributions/ctf-tools-0.1.0-dev.zip` 含 `ctf-tools/lib/ctf-tools-0.1.0-dev.jar`、`model-0.1.0-dev.jar`、`runtime-0.1.0-dev.jar`；`git diff --check` exit `0`；最新分支提交前 worktree clean，当前并行 worktree 仍有未提交的 UI/recipe polish，必须在合并前单独审阅或提交，不可遗漏。
- 当前 `main` 保留原有未提交 Runtime/Sage API/plugin 改动；本轮 Runtime/SDK 增量仍不执行 `git add .` 或提交，未修改官方 upstream 或其他仓库；`.agent-teams/` 继续保持不纳入提交。

## 7. 下一步

### Sage intelligence external-index and completion increment

- 本轮已完成并验证 real Sage 10.9 external-index consumer path：84,159 normalized entries / 84,187 raw declarations / 2,839 source digests；full index 保持 ignored external artifact，不进入 bundled/resource/product。
- `SageApiIndexQuery` 现在对 canonical methods/aliases 统一提供 signatures、call return types 与保守 `uniqueKnownReturnType()`；UNKNOWN、DYNAMIC、blank、union 和 ambiguous overload 不会被传播为确定类型。
- `.sage` root completion 已同时注册 Sage/Python language extension，并在无 reference PSI、dumb mode 时保留 external namespace fallback；full artifact 的 root candidates 通过 2,158/2,158 metadata/canonical checks，代表性 `AffineSpace` FUNCTION、`var` ALIAS、`RR` CONSTANT 均通过真实 `myFixture.completeBasic()` popup harness。
- Fresh final Gradle suite：core `SageApiIndexTest` 26/26；plugin `SageCompletionTest` 1/1、`SageApiIndexServiceTest` 4/4、`SageApiDocumentationProviderTest` 2/2、`SageIntelligenceHarnessTest` 9/9；`git diff --check` 通过。
- 当前严谨可宣称：`FULL_SYMBOLS`、`FULL_CANONICAL_LOOKUP`、`FULL_ROOT_COMPLETION_METADATA`、`FULL_MEMBER_METADATA`、`FULL_SIGNATURE_METADATA`、`FULL_DOCUMENTATION_METADATA`，以及 representative popup/type harness gates。仍不可宣称 runtime-semantic FULL、全上下文 PSI 全等价、bundled full-index、product/release 完成。

### Scoped Sage API sidecar and quality-gate increment

- 继续限定在 `tools/sage-api-index/import_wsl_artifact.py`、`test_import_wsl_artifact.py`、`expected-sage-10.9.json` 与审计文档；不修改 `generate.py` 的 conflicts 算法，不把 ignored full index 放入 bundled/resource/product/installer/release。
- `expected-sage-10.9.json` 现在明确包含 `qualityContractVersion: 1` 与六项独立人工维护 quality oracle；真实 ignored index probe 已验证 `checkedCount=6`、`contractVersion=1`。质量门覆盖 source kind/locator/digest 与 `sourceDigests` 绑定、签名数量、参数/default/optional/keyword-only/variadic/type state/expression、return type state/expression、required/non-empty documentation。
- importer 现在对 generated index 做严格结构/source digest 校验；scoped coverage 交叉校验 expected/covered/missing identity 的 duplicate、partition、count、completeness，且命令不传 `--allow-conflicts`/`--allow-missing`。
- `sage-api-index-envelope.json` 是独立 sidecar schema，记录 artifact/version/provenance、manifest/probe/tree/index/coverage/diagnostics/quality；receipt 只绑定最终 envelope digest，避免 receipt↔envelope 递归 digest 声称。
- 本轮新增/修复后的 Python 验证：`python -m unittest tools.sage-api-index.test_import_wsl_artifact tools.sage-api-index.test_generate`，53 tests，exit `0`；`py_compile` 与 `git diff --check` 均 exit `0`。
- fresh LIVE imports `final-live-7` / `final-live-8` 均 exit `0`，不使用 `--allow-conflicts` 或 `--allow-missing`；两次均 Sage `10.9`、Python `3.13.15`、stubgen `0.8.3`、stub files `2839`、index entries `84159`、coverage `6/6`、ratio `1.0`、`conflicts=0`、`isComplete=true`、quality `checkedCount=6`/contract `1`。
- 两次 normalized artifact 的 `index/raw/coverage/source-manifest/expected-symbols/receipt/envelope` 字节完全一致：index SHA-256 `4f8bd2fc2d26ee5b6f14dbbf1eab920e72d46d8573ef10fac95249f700df91f6`，receipt SHA-256 `eed904565b888e7435898f19dcf29cbe1452dd78bc00b42996383d5a02f9a804`，envelope SHA-256 `211f0b4fc4d4442454736ee704361984eb269f1b398e8cce84ad6fb33b5185a8`；receipt 对最终 envelope digest 校验为 true，envelope 不包含递归 receipt digest claim。
- 未完成/未声称：独立 envelope read/tamper validator、Sage 全量智能补全、真实产品 UI、正式发行或签名；本轮 core/plugin Gradle 命令虽重新取得 `BUILD SUCCESSFUL`，仍不把它解释为 full-index bundled 或产品级智能补全证明。

### Runtime SDK adapter 与实现会话归档

- 主线已 cherry-pick `38efdbeda17e5476dec6d1b92c7c6517e6cf30ac`，生成本地提交 `77309df`；Sage SDK type/additional-data adapter、target compatibility、生命周期 validation 和 stale binding revalidation 已有 core/plugin build/test 证据。
- Runtime Manager 核心已由 `a2c7fdc` 进入当前 `main`；原 `parallel/runtime-manager` 分支与 `G:\Projects\worktrees\runtime-manager` 已在确认 clean 且提交内容由 main 覆盖后删除。随后已执行 reflog expire 与 `git gc --prune=now`，旧 Runtime 分支对象已物理清除。
- 历史 `plugins:sage-core:buildPlugin`、`verifyPluginProjectConfiguration`、`verifyPlugin` 均有 `BUILD SUCCESSFUL` 证据；这些结果证明编译、测试和 verifier 边界，不证明真实 Settings/Project SDK click flow。
- 当前保留的未完成项：Runtime 真实 Settings/Project SDK click flow、WSL/Docker/SSH 端点、并发锁、crash fault-injection、发布方 Catalog 公钥轮换；CTF live Node/CyberChef-server、默认插件/分发接入和完整产品 smoke。SDK target editor 已提供 SSH runtime root 与 WSL/Docker/SSH explicit mapping 字段，但未声称真实端点连通性。
- 本轮 bundled-Python increment 已落地：`RuntimeManifest.pythonExecutable` 是显式、受校验且必须出现在 `files` 中的相对路径；Native/WSL/Docker/SSH 只通过 `RuntimeExecutableResolver` 解析，缺失、未验证或缺少远程 root/mapping 时 fail-closed。`SageRuntimeSdkType` 保持独立身份，不伪装成 `PythonSdkType`，也不持久化猜测的 Python SDK 名称。
- Sage run/debug 已改为使用已验证 Runtime Manager 的 manifest launcher；debug wrapper 仅接受显式 bundled Python，移除了 `/sage -> /python` 与 launcher-as-Python fallback。WSL/Docker/SSH 的真实端点与目标环境仍需产品级验收。
- 本轮文档更新未执行 `git add .`、未提交；未修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr` 或官方 upstream。历史 staging verify/release audit/smoke 仍按其原有历史边界解释，不冒充本轮 fresh product build。
- 本轮未执行 fresh product build、x64 installer smoke、release audit 或 `verify-upstream-staging.ps1 -FinalCheck`；因此本 increment 只宣称 core/plugin/runtime verification，不宣称发行门完成。
- 后续 SDK 选择/Runtime Manager 增量开始后，首次 compile 命令误把 PowerShell 引号传给 Gradle：`-Psage.ide.localSdk='D:/JetBrains/PyCharm'` 被解析为任务 `.ide.localSdk=D:/JetBrains/PyCharm`，导致 `Selection failed`；第二次未正确传成单一参数时仍复现同类错误；正确 PowerShell 写法是 `"-Psage.ide.localSdk=D:/JetBrains/PyCharm"`。
- 正确 Gradle 参数后首次 Kotlin 编译发现 `ProjectRootManager` 实际位于 `com.intellij.openapi.roots`，不是 `com.intellij.openapi.projectRoots`；已修复并取得后续 `:plugins:sage-core:compileKotlin` `BUILD SUCCESSFUL`。
- 后续尝试把尚未存在的 core `RuntimeManager` 类型引入插件，导致 `SageRuntimeSdkAdapter.kt:16` unresolved reference；已删除该无效 import。Runtime Manager owner 仍由 plugin-side `SageRuntimeManagerService` 承担，不能声称已有 core `RuntimeManager` orchestration。
- 本轮尝试在 core `RuntimeManagerFeatureTest` 直接把 `VerifiedRuntimeCatalog` 传给旧 `SageRuntimeManager`，并用 lambda 构造非 `fun interface` 的 `RuntimeInstaller`；focused test 曾因测试代码类型错误失败（`RuntimeCatalog`/`installRoot`/constructor diagnostics），已改为 `StaticRuntimeCatalog` + `object : RuntimeInstaller` 并重新取得 focused `BUILD SUCCESSFUL`。
- `SageRuntimeManagerService` 现已提供 canonical install root/lifecycle 的 current/validate/select/remove/rollback、signed catalog load（只保存最近 load result）和 verified install delegation；install 要求传入对象必须是该 service 最近一次签名验证返回的 `trustedCatalog`，避免绕过 service catalog boundary。兼容 `SageRuntimeSdkService` 仅做代理。
- Runtime Manager 完成会话在删除前为 clean：`parallel/runtime-manager` tip `c532e09`；该分支相对 `445fd76` 只包含 Runtime Manager 文件与测试，未包含交接文档、Sage API 或 CTF 越界差异。删除前独立 `:core:runtime:test -PrunRuntimeTests=true` fresh 结果为 8 suites/38 tests、skipped=0、failures=0、errors=0，exit `0`，`git diff --check` 通过；worktree、分支及其不可达 Git 对象现已删除。
- 当前 main 已有等价 Runtime 基础实现 `77309df`，并在其后有 `4080468` 与 `a2c7fdc` 的 bundled-Python/Sage SDK 执行边界增量；旧 Runtime 分支曾与当前 main 在共同文件上产生 add/add 冲突，因此未直接 rebase/merge。Runtime 功能继续以当前 main 为基线；旧分支已在归档证据确认后删除。
- 本增量仍未执行 fresh product build、Windows x64 installer smoke、release audit 或 `verify-upstream-staging.ps1 -FinalCheck`；也未进行真实 IntelliJ Settings/Project SDK click flow、WSL/Docker/SSH live endpoint 或 crash fault-injection 验收。不要用历史 staging/release 证据替代这些门。当前测试只证明 JVM/UI-model 与 mock target boundaries：plugin `src/test` 无 UI Robot/IDE fixture；`SageRuntimeSdkType` editor 代码存在，但没有可执行的 Settings > Project SDK click-flow 证据。Native/WSL/Docker command construction 与 core target probe 可测，实际 `wsl.exe`/Docker/Podman/SSH/HPC endpoint 未连接；SSH run/debug 明确 fail-closed 为未实现 transport。不要将这些 mock/string/path tests 记为 live endpoint VERIFIED。
- 本轮 follow-up 首次尝试加入 Runtime 根目录 operation lock 后，`:core:runtime:test --rerun-tasks` 在 `RuntimeInstaller.kt` 报大量 cascading unresolved/syntax errors；已补齐新增 `withRuntimeOperationLock` 嵌套块的闭合 `}`，随后 Runtime 全套测试取得 `BUILD SUCCESSFUL`。新增并发 lifecycle stress 测试已通过；仍未完成跨进程 installer/select 真实压力或 crash fault-injection。
- Catalog rotation 边界测试曾错误地把旧签名 envelope 的 `keyId` 改为 transition id，却未重新签名，导致预期失败断言方向错误（51 tests / 1 failure）；已改为独立 transition Ed25519 keypair + 独立签名，不改变 production key，并补充 revoked-key 明确拒绝断言。随后 fresh Runtime XML 显示 `RuntimeManagerFeatureTest` 12/12、`ZipRuntimeInstallerTest` 9/9 通过，含 old/transition/unknown/revoked key、并发 lifecycle、并发 duplicate install、failed replacement preservation；最终补丁后的 Runtime suite 仍 `BUILD SUCCESSFUL`。
- fresh `:plugins:sage-core:buildPlugin`、`:plugins:sage-core:verifyPluginProjectConfiguration`、`:plugins:sage-core:verifyPluginStructure` 与 `:plugins:sage-core:verifyPlugin` 均 `BUILD SUCCESSFUL`。Plugin Verifier 1.409 对 PY-261.27258.51 与 PY-262.10315.23 均报告 Compatible；各报告 2 deprecated API、28 experimental API。Project configuration verifier 仍报告 since-build 261 低于目标 262、until-build 应移除、JVM/Kotlin target 25 高于 since-build 261 的 Java 21 要求；本轮未擅自扩大兼容性策略修改。
- 本轮端点探测：官方 checkout `G:\Projects\intellij-community-sage-ide` SHA 仍为 `b0001cd6c53979b384def7a1e3febe061e2ef687`，仅保留约定的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore` 未跟踪文件；`verify-upstream-staging.ps1 -FinalCheck` fresh 通过。WSL2 Ubuntu 可启动但 `sage` 不存在（仅 Python 3.14.4），因此 WSL Sage endpoint NOT VERIFIED。Docker CLI 29.2.1 存在但 Docker Desktop Linux daemon 的 named pipe 不存在，Docker endpoint NOT VERIFIED；Podman 未安装。当前 PATH 无 Native `sage.exe`，staging x64 `sage.exe` 调用触发 WSL 环境错误，不能记为 Native endpoint VERIFIED。PyCharm 可执行文件存在于 `D:\JetBrains\PyCharm\bin`，但插件项目没有 UI Robot/IDE fixture，真实 Settings/Project SDK click flow 仍 NOT VERIFIED。
- 下一步开始 fresh staged product build；使用现有 `G:\sage-build\staging-build6` 作为允许的 staging 输出，build root 使用新的 ASCII `G:\sage-build\product-followup`，不修改官方 checkout。
- fresh staged development product build 已启动：`build-upstream-staged.ps1 -BuildDev -KeepStaging -AsciiBuildRoot G:\sage-build\product-followup`；首次运行在 600 秒工具上限时停在约 `[2,907 / 3,641] compile //platform/platform-impl:ide-impl`，检查后未发现残留 Bazel/Java 构建进程。随后利用缓存续跑，编译推进到 jar/distribution 阶段，但 Bazel 最终 exit code 1；完整 stdout/stderr 保存在本轮 DSH 临时日志，最终异常是 nested Bazel 从 `G:\sage-build\product-followup\bazel-output\...\execroot\_main` 启动，触发 `bazel should not be called from a bazel output directory`，不能记为 product build VERIFIED。
- 针对上述真实失败已做最小脚本修复：`build-upstream-staged.ps1` 将 `SAGEMATH_BAZEL_ASCII_ROOT` 从 `bazel-output` 改为独立的 `G:\sage-build\product-followup\nested-bazel`，并创建该目录；续跑发现 `apply-overlay.ps1` 的兼容分支仍重复追加 `nested-bazel`，导致实际参数变成 `nested-bazel\nested-bazel`，再次触发 Bazel workspace/output-dir 错误。已进一步修正 overlay 的幂等分支，使它把旧的 `.resolve("nested-bazel")` 恢复为直接 root；未修改官方 checkout 或无关 Runtime/importer/CTF 文件。必须重新对 staging 应用 overlay 后再 fresh 续跑。
- 随后对现有 staging artifact 的无安装 `/?` 尝试在 180 秒内超时；该 artifact 时间早于本轮且不能作为 fresh installer smoke 证据，未将其记为成功，也未继续使用旧产物冒充本轮 release 验收。需等待 fresh installer build 成功后再执行 `windows-installer-smoke.ps1`。
- 额外探测显示 staged `dist.win.x64\bin\sage64.exe` 实际是 SageMath CTF IDE 的 JVM launcher（同目录 `sage.bat` 明确写有 `SageMath CTF IDE startup script`），不是 SageMath bundled runtime `sage` executable；因此该路径不能作为 Native SageMath execution endpoint。UI 自动化工具 pywinauto/pyautogui/uiautomation/WinAppDriver 均不可用；SSH localhost connection refused，且无 SSH config，SSH/HPC endpoint NOT VERIFIED。
- 真实 `:plugins:sage-core:runIde` 使用隔离 `G:\sage-build\ide-smoke\{user-home,appdata,localappdata}` 启动 PyCharm，Gradle compile/prepareSandbox 成功，但 IDE 进程退出码 2，日志为 IntelliJ dispose 阶段 `CE must not be thrown from a dispose() implementation`；未取得 IDE 启动成功或可点击 Settings/Project SDK 的证据。该错误尚未证明由 Sage Runtime 改动引起，已启动另一套隔离 baseline 对照，但第一次对照命令错误地使用了 Gradle 参数 `-Didea.auto.exit=true`，被解析为任务 `.auto.exit=true`（exit 1），因此尚未取得有效 baseline 结论；不能直接改 Runtime。
- product build 修复后的下一步是先在允许的 `G:\sage-build\staging-build6` 上重新执行 `apply-overlay.ps1`；该步骤已完成，staged `BazelRunner.kt` 现在直接使用 `Path.of(asciiBuildRoot)`，不再追加第二个 `nested-bazel`。随后重新运行 fresh product build。
- 第二次 IDE baseline 对照仍误把 `-Didea.auto.exit=true` 作为 Gradle task 参数，exit 1（`.auto.exit=true` not found）；因此目前仍没有有效的无插件对照。后续不再重复该参数形式，改用环境隔离 + 正常 `runIde`，必要时通过 `--args`/IDE 运行参数传递，或直接把 runIde 作为启动 smoke 而不强制 auto-exit。
- 修复 nested Bazel root 后的第三次 fresh product build `product-followup2` 已绕过原 workspace/output-dir 错误，但在 Bazel analysis 阶段真实失败：`plugins/sage-core/BUILD.bazel` 依赖 `//core/sage-api:sage-api`，而 `G:\sage-build\staging-build6\core\sage-api\BUILD.bazel` 不存在（source `core/sage-api/BUILD.bazel` 存在）。因此本轮 product build 仍 NOT VERIFIED；下一步只修 staging overlay 的缺失 core/sage-api 文件并重新验证，不改官方 checkout。
- 真实隔离 `:plugins:sage-core:runIde` 已取得成功证据：`shell/powershell-16` exit 0，Gradle `BUILD SUCCESSFUL`，18 tasks（2 executed/16 up-to-date），IDE 日志显示 PyCharm 2026.2.1 已完成启动；仍未完成可操作的 Settings > Project SDK click flow。
- fresh `product-followup2` 已绕过 nested Bazel 错误，但暴露 staged overlay 缺失 `core/sage-api/BUILD.bazel`；已在 `apply-overlay.ps1` 增加仅写入允许 staging tree 的 Sage API 模块复制，并在 `verify-upstream-staging.ps1` 增加对应存在性检查。重新应用 overlay 后，`verify-upstream-staging.ps1 -FinalCheck` fresh 通过（官方/staging SHA 均为 `b0001cd6c53979b384def7a1e3febe061e2ef687`）。
- `product-followup3` 在 Sage API overlay 后已通过初始 Bazel analysis 继续推进至约 2,990 packages / 105,891 targets，但中途曾被外部停止残留 Bazel/Java 进程，脚本收到 exit code `-1`；续跑复用缓存后完成全部 3,642 actions，外层 `//build:sage_math` 成功，但 dev product 的 nested plugin build 再次失败：子命令使用 `G:\sage-build\product-followup3\bazel-output\...\execroot\_main\bazel.cmd`，触发 `bazel should not be called from a bazel output directory`。因此仍无成功 product 产物证据。
- 已针对该精确根因做最小 staging 修复：`apply-overlay.ps1` 给 staged `BazelRunner.kt` 注入 `SAGEMATH_BAZEL_WORKSPACE_ROOT`，从 `build-upstream-staged.ps1` 传入 `G:\sage-build\staging-build6`，nested plugin build 改用 staging 根的 `bazel.cmd` 与 workspace cwd；重新应用 overlay 后 `verify-upstream-staging.ps1 -FinalCheck` 通过。
- 续跑 `product-followup3` 已证明 nested plugin Bazel 命令实际改为 `G:\sage-build\staging-build6\bazel.cmd`、cwd 为 staging，且成功完成 10m02s、47 个 plugin 目标；但随后 dev server 以 `kotlin.UninitializedPropertyAccessException: lateinit property platformClassPath has not been initialized` 退出（`DevMainImpl.kt:96`）。因此 nested wrapper 问题已解决，product build 仍 NOT VERIFIED。该异常来自 `BuildRequest.platformClassPathConsumer` 的异步发布协程在 `buildProductInProcess` 返回前未完成；当前暂不改官方构建核心，先用 installer target 验证 release 路径。
- fresh installer target `build-upstream-staged.ps1 -BuildInstaller -KeepStaging -AsciiBuildRoot G:\sage-build\product-installer1` 已完成约 1,092 秒、5,151 processes 后真实失败：`Target //python/build:sage_i_build_target failed to build`；Kotlin 编译首先在 staged `plugins/sage-core` test sources 报 `SageIntelligenceHarnessTest` 的 `members`/helper 未解析，随后 `SageRuntimeSdkDataTest`/其它测试报 `com.starnotesxj.sagemath.*`、`kotlin.test`、JDOM 等 classpath 缺失。检查发现先前 overlay 复制的 staged `core/sage-api` 文件被截断/多为零字节，导致这些级联缺失；已从 source 完整重建并改为只复制 core module 的 BUILD/IML/src，排除 Gradle `build/test-results` 生成物；overlay 与 FinalCheck 的零字节规则也已限制为异常生成物，重新应用 `verify-upstream-staging.ps1 -FinalCheck` 通过。本轮无 fresh installer 产物，不能运行 fresh installer smoke 或 fresh release audit。
- fresh installer `product-installer4` 首次已完成 Bazel 主 target：5,547 processes、约 999 秒，`//python/build:sage_i_build_target` 与 47 个 nested Sage Core plugin targets 均成功；随后曾在 `createDevModeProductRunner(DevModeProductRunner.kt:52)` 以 `NullPointerException` 失败（`build distributions` 阶段，退出码 1）。堆栈唯一失败点是 `newClassPath!!`，而 `platformClassPathConsumer` 在 `IdeBuilder.kt:412` 的异步 `launch` 中赋值；已在 staging overlay 注入 `CompletableDeferred`/`await()` 修复，不修改官方 checkout。
- 复用 `product-installer4` Bazel cache 直接重跑 installer target 成功，exit 0：x64 与 aarch64 NSIS installer/uninstaller 均生成，SBOM 也生成；日志仍记录 upstream SPDX `GPL-2.0 is deprecated` validation warning，且 sign step skipped（无 sign tool）。fresh artifacts 位于 `G:\sage-build\staging-build6\out\sage-math\artifacts`，下一步执行 x64 installer smoke、x64 release audit、FinalCheck。
- 对清洁 staging 直接执行 `@community//plugins/sage-core:sage-core_test_lib`，production `sage-core` 与 `core/sage-api` 均编译成功，但 test_lib 仍失败；首次缺失是 `Cannot access class com.starnotesxj.sagemath.sageapi.SageApiIndexQuery`，已在 overlay 中补入 core model/runtime/Sage API 及其 test_lib 依赖。重跑后的真实错误进一步表明 test classpath 仍缺 `kotlin.test`、JDOM `Element`，且 `core/sage-api.abi.jar` 虽在 `--cp` 中仍未提供测试导入可见性；需检查 ABI jar 内容与直接 test deps（`@lib//:kotlin-test*`、`//platform/util/jdom(:jdom_test_lib)`），不得再次长跑 installer。
- 最新直接 Bazel 验证 `shell/powershell-29` 在 54.7 秒后仍 exit 1：`sage-core`、`sage-api`、`sage-api_test_lib` 均完成，但 `sage-core_test_lib` 仍报告 `Unresolved reference sagemath/test/Element` 及 `Cannot access SdkAdditionalData`。这确认问题限于 test classpath/ABI 可见性，不是 production 源编译；先补齐 Kotlin test 与 JDOM/Test SDK 依赖并检查 Sage API ABI 内容。
- 补入 `@lib//:kotlin-test`、`kotlin-test-junit5`、`//platform/util/jdom(:jdom_test_lib)`、`//platform/platform-api:ide` 后，`shell/powershell-30` 的 test classpath 已包含这些条目，Kotlin/Sage API/JDOM 其它错误消失；但 `SageRuntimeSdkDataTest` 仍单独报 `Cannot access com.intellij.openapi.projectRoots.SdkAdditionalData`（8 处），说明 projectRoots 类型不在当前 test ABI 可见集合或需要对应 SDK/project-model module 依赖。
- 继续补入 `//platform/projectModel-api:projectModel(_test_lib)` 与 `//platform/platform-api:ide_test_lib` 后，首次重跑因重复注入已有 `//platform/lang-api:lang(_test_lib)` 而被 Bazel 分析拒绝；已移除重复项。最新 `shell/powershell-32` 直接构建 `@community//plugins/sage-core:sage-core_test_lib` 成功：分析 1,324 packages/89,936 targets，718 actions，exit 0；staged Sage Core test classpath 已收敛。
- 对现有 staging artifact 执行了只读 `windows-release-audit.ps1 -Architecture x64`：SHA-256/SHA-512 sidecar 全部匹配，SPDX/third-party/dependencies/sources 文件存在，errors=0；但因 installer/uninstaller 未签名、SPDX work-in-progress/NOASSERTION、分发包内 LICENSE/NOTICE 未找到，warnings=8、summary `passed=false`。该结果是历史 staging artifact 的审计证据，不是 fresh product release 通过。
- 对同一现有 x64 artifact 执行 `windows-installer-smoke.ps1`：installerExitCode=0、安装 launcher/product process、Sage Core plugin JAR、uninstaller 均发现，uninstallerExitCode=0，installed/uninstalled/launched 全为 true。由于 artifact 早于本轮 fresh product build 且 fresh build 超时，该结果仅为历史 staging smoke VERIFIED，不替代 fresh release smoke。
- fresh installer target 在 staging-only `CompletableDeferred`/`await()` classpath race 修复后复跑成功（缓存重用，Bazel `run //python/build:sage_i_build_target` exit 0）。fresh x64 artifact `sageMath-263.SNAPSHOT.exe` 482,122,694 bytes，x64 uninstaller 214,360 bytes；aarch64 installer/uninstaller 也生成。x64 `windows-installer-smoke.ps1` 通过：installer/uninstaller exit 0，安装 launcher/product process、Sage Core plugin JAR 均发现，installed/launched/uninstalled=true，安装目录已清除。
- fresh x64 `windows-release-audit.ps1 -Architecture x64` 完成：errors=0，SHA-256/SHA-512 installer 与 uninstaller sidecar 全部匹配，SPDX/third-party/dependencies/sources/product-info 均存在；summary `passed=false` 且 warnings=8，原因是 x64 installer/uninstaller 未签名、两个 SPDX 报 work-in-progress 与各 248 个 NOASSERTION、distribution artifact root 未含 LICENSE/NOTICE。该 audit 是 fresh 证据，但不是 release clean pass。
- fresh artifact 后执行 `verify-upstream-staging.ps1 -FinalCheck` 通过：官方与 staging SHA 均为 `b0001cd6c53979b384def7a1e3febe061e2ef687`，manifest、Sage Core/Sage API staged files、JDK 25 与 zero-byte 检查通过；脚本同时确认官方 checkout 无非豁免 dirty 状态，受保护 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore` 的豁免规则未触发异常。

## 8. CTF 分支核查与后续合并来源

- 本轮核查以共同祖先 `445fd76` 为基准：`integration/ctf-mvp` 与 `parallel/ctf-mvp` 是两条独立、重叠的实现线；`parallel/ctf-mvp` **并不包含** `integration/ctf-mvp` 的 Git 祖先。此前“包含 integration 历史”的表述不准确，后续不再使用。
- `integration/ctf-mvp` tip `742aa3d` 保留旧基础 MVP及其独立安全加固提交（包括脚本完整性/TOCTOU 与有界 CyberChef 响应处理）；`parallel/ctf-mvp` 的 `aecf6df` 也有独立的进程/CyberChef 加固，但不能仅凭提交标题视为逐项等价，合并前必须对安全契约逐项复核。
- `parallel/ctf-mvp` 当前是唯一后续 CTF 合并来源：worktree `G:\Projects\worktrees\ctf-mvp`，tip `62847f04b793a555b8251405bf90cf583c12acaa`（`Polish CTF tool windows and local recipes`）；提交 `62847f0` 时 worktree clean，但当前 worktree 又有未提交 UI/recipe polish 改动，必须在合并前单独审阅或提交。它保留完整 Math Lab 及最新 UI/recipe polish。`integration/ctf-mvp` 不再作为第二个候选分支整合，也不应整体 merge/cherry-pick 到 parallel。
- 证据：`git range-diff 445fd76..integration/ctf-mvp 445fd76..parallel/ctf-mvp` 显示两条线只共享基础 MVP 的等价提交；parallel 线新增 `3b326e3`、`aecf6df`、`a1c18ab`、`62847f0`，integration 线独有 `3370906`、`ac3f26f`、`742aa3d` 等安全提交。两分支直接合并会在 `core/model`、`plugins/ctf-tools`、`plugin.xml`、构建和测试文件上产生 add/add/内容冲突；不应把冲突算法当作自动整合方案。
- `git merge-tree main parallel/ctf-mvp` 在 pristine main 模拟下无冲突；曾进行过一次带 `--no-commit --no-ff --autostash` 的直接合并演练，但因当前仍在 parallel 分支开发，已撤回临时 merge commit `ad572f8`，main 恢复到 `4080468`，并恢复原未提交改动。当前不再执行 CTF 合并，直到用户明确要求。
- 当前工作约束：用户仍在 `parallel/ctf-mvp` 开发，暂不向 `main` 整合。未来若用户明确要求合并，仍以 `parallel/ctf-mvp` 为唯一功能来源，以 integration 线作安全审计参考；若发现缺少脚本 realpath/SHA-256 二次校验、受控临时副本或 response byte limit 等契约，只移植经过测试的最小安全补丁，不整体合并 integration 分支。

## 9. 参考

- [`README.md`](README.md)
- [`docs/STATUS.zh-CN.md`](docs/STATUS.zh-CN.md)
- [`docs/FEATURE-STATUS.zh-CN.md`](docs/FEATURE-STATUS.zh-CN.md)
- [`docs/IDE-PLAN.zh-CN.md`](docs/IDE-PLAN.zh-CN.md)
- [`product/README.zh-CN.md`](product/README.zh-CN.md)
- [JetBrains MPS](https://github.com/JetBrains/MPS)：DSL/模型化 IDE 参考，不是本项目运行时底座。
- [JetBrainsRuntime](https://github.com/JetBrains/JetBrainsRuntime)：JetBrains JDK 参考，影响构建/运行时，不提供 Sage API 智能。

## 10. Sage Intelligence 当前增量（进行中）

- 用户已明确将 CTF 延后，当前优先级为 SageMath API、代码提示、补全、类型、签名与文档智能；禁止以当前 bundled 45-entry fixture 或 6/6 scoped oracle 声称全量完成。
- 最新真实 WSL 验证使用显式 Ubuntu conda Sage 10.9 endpoint（默认 WSL 无 `sage` 命令）：Python 3.13.15 可执行 Matrix determinant/solve_right 与 factor；fresh LIVE import 输出 84,159 entries、2,839 source digests、index SHA-256 `4f8bd2fc…`、treeDigest `69d0524a…`、24 duplicate diagnostics、conflicts=0。但 envelope 仍是 `SCOPED`（6 项人工 quality oracle），不是全量 API 覆盖证明。
- 当前已新增 indexed query/facade、authoritative external-index service load state、headless completion/type harness 和 index-backed documentation provider；full artifact/query gates 与 representative popup gate 已完成，仍不把它们等同于 runtime-semantic FULL。full index 仍仅为 ignored external artifact，未复制进 bundled/resource/product。
- 2026-08-23：运行 Sage documentation provider focused Gradle test 时，`:core:sage-api:jar` 无法创建 `core/sage-api/build/libs/sage-api-0.1.0-dev.jar`（ZIP 创建失败）。此前该模块 core tests 已通过；该错误发生在并发构建后，尚未将 documentation provider 测试标记为通过。后续应在停止并发 Gradle 后清理并重建该单个 build output，再重跑 focused test；不得据此修改 Sage 语义代码。
- 2026-08-23：并发服务改动短暂令 `SageApiIndexService.install` 调用 `toLoadState(..., sizeBytes = null)`，但扩展函数仅接收 `(origin, path)`；这是编译阻塞，不是 API/index 语义问题。已在隔离验证前将该调用改为匹配签名；后续须以单 worker 隔离 plugin test 复核。
- 2026-08-23：隔离单 worker plugin suite 在 service 调用修复后完成编译，但 `SageIntelligenceHarnessTest.testPsiCompletionCoversSageArithmeticFunctionsAndIntegerMember` 于第 168 行断言失败（9 tests / 1 failure）。这是具体 completion 行为回归，不能将此前 4/4 harness 或本轮 suite 标为全绿；修复前应先读取该测试断言、相关 completion provider 与 test XML，最小化调整。
- 2026-08-23：并发 query map 编辑还留下 `moduleEntriesByOwner` 的未初始化声明：构建报 `SageApiIndexQuery.kt:9 Property must be initialized or be abstract`。这是局部 map 初始化遗漏；应仅把已构建的 `byModuleOwner` freeze 赋回该字段，再以单 worker core test 验证。
- 2026-08-23：上述并发 Gradle/局部 map 问题已在安静的单 worker 环境收敛。最终验证：`core:sage-api:test` 成功；plugin focused suite 成功，XML 为 DocumentationProvider 2/2、IndexService 3/3、IntelligenceHarness 5/5；Python importer/generator tests 53/53。SageIntelligenceHarness 的整数成员场景修正为真实 `.sage` preparser 数字字面量（`value = 17`）路径，避免把缺少稳定 PSI 类型桥接的显式 `Integer(17)` 误作同一契约。
- 2026-08-23：fresh LIVE importer 生成 ignored `build/sage-api-real/final-live-9`：schema 1，Sage 10.9/Python 3.13.15，84,159 normalized entries，84,187 raw declarations，2,839 source digests，index SHA-256 `4f8bd2fc…`，treeDigest `69d0524a…`。新 `api-inventory.json` 以 `RAW_AST_DECLARATIONS` 记录 84,159 unique identity；envelope `apiCoverage.scope=FULL`、84159/84159、identityDigest `445c4818…`，仅表示 source/stub AST identity 全量。原 `coverage.scope=SCOPED` 仍为独立的 6/6 semantic quality oracle，不能将 `FULL` 解读为全运行时动态语义、所有签名/文档正确性或产品发布完成。
- 2026-08-23：用户要求全量 API 覆盖证明后，新增 opt-in external full-index integration probe（`-Psage.external.fullIndex=<index>`），不把 139 MB artifact 纳入资源。它实际加载 `final-live-9/sage-api-index.json`，断言 EXTERNAL 状态、Sage 10.9/Python 3.13、2,839 source digests、84,159 entries，并解析 `factor`、`Matrix`、`Matrix.solve_right`、Matrix 文档和 method signature。该探针发现且修复 `SageApiIndexQuery.signatures()` 只查询 FUNCTION、漏掉 METHOD 的真实缺口；现在函数和唯一可解析的方法均返回已有签名且不猜测冲突。fresh core suite 成功，fresh plugin suite 成功：DocumentationProvider 2/2、IndexService 4/4（含 full artifact）、IntelligenceHarness 5/5。
- 2026-08-23：当前可证明的全量范围为 `FULL_SYMBOLS`/source-stub identity：独立 raw AST inventory 的 84,159 identities 与 normalized external index 84,159/84,159 对齐，且完整 plugin consumer 实际加载该 artifact。仍不可称为 runtime-semantic FULL：Python 动态导出、每个成员的运行时可调用性、全部 overload/doc/type 精确性、所有 IDE completion 场景及 bundled/product/release remain separate unproven gates。
- 2026-08-23：进一步把 consumer proof 提升到全量 canonical lookup：external full-index probe 遍历加载后的全部 84,159 entries，逐项执行 `query.find(qualifiedName, kind)` 并要求零 unresolved；fresh headless Gradle run `BUILD SUCCESSFUL`。因此现在可严谨宣称 `FULL_SYMBOLS + FULL_CANONICAL_LOOKUP`：每个 inventory identity 都进入外部 index，且每个 indexed canonical `(qualifiedName, kind)` 都能被插件的只读 query 层取回。该证明仍不等于每条 API 在 IDE 任意上下文中的 completion/type/doc 语义或 Sage runtime behavior FULL。
- 2026-08-23：语义消费继续扩展：query 新增 stable `namespaceEntries()`，能取回 schema 中无 ownerName 的顶层 namespace exports；implicit `.sage` completion 先保持带 PSI 导航的 stub candidates，再从已验证 external index 补齐未出现的 `sage.all` entries（不虚构 PSI 目标）。fresh full artifact probe 证明 `sage.all` 直接 export 为 2,158 个 distinct names，且每一个仍可 canonical lookup；同一 complete headless plugin suite 成功，IndexService 4/4、IntelligenceHarness 6/6、DocumentationProvider 2/2。该项是 `FULL_ROOT_COMPLETION_METADATA`（完整 root candidate universe），不是对每个候选均完成真实 popup/UI/运行时行为的声称。
- 2026-08-23：full external consumer probe 继续遍历验证：49,348 个 METHOD/PROPERTY/CONSTANT 均具有 ownerName 且能由 `query.members(owner)` 返回；52,236 个带 signatures 的 entries 全部可由 `query.signatures(qualifiedName)` 返回；57,425 个带 documentation 的 entries 全部可由 `query.documentation(qualifiedName)` 返回。fresh combined headless run 成功：core `SageApiIndexTest` 26/26，plugin IndexService 4/4、DocumentationProvider 2/2、IntelligenceHarness 6/6。可称 `FULL_MEMBER_METADATA + FULL_SIGNATURE_METADATA + FULL_DOCUMENTATION_METADATA` 为 artifact/query 数据可达性证明；它仍不证明每个 dynamic/UNKNOWN type 在任意 PSI call-site 的推断正确性、每个文档均有原生 PSI 定位，或运行时 API 等价。
- 2026-08-23：type propagation round 增加 `callReturnTypes()` 对 canonical methods/aliases 的统一读取，并保持 `uniqueKnownReturnType()` 仅接受全部 KNOWN、非空、无 union `|` 且唯一表达式；real artifact 统计 5,525 个 METHOD 属于安全 unique-known 子集，另有 UNKNOWN/DYNAMIC/union/多 overload 情况被拒绝传播。headless external type harness 最初误把 KNOWN union (`Matrix.solve_right`) 期待成 null，随后按 contract 修正为保留原始 KNOWN union metadata、仅拒绝 `uniqueKnownReturnType` 传播；fresh combined suite 成功：core 26/26，IndexService 4/4，DocumentationProvider 2/2，IntelligenceHarness 7/7。该项证明的是 full artifact type metadata 的保守 query/propagation gate，不是所有 PSI call-site 的运行时语义等价。
- 2026-08-23：新增真实 `myFixture.completeBasic()` 外部 root popup probe，选择 bundled fixture 不含、full artifact 含的 `sage.all.AffineSpace`（FUNCTION）。初次空 popup 已定位为 provider 仅注册在 `Python`、而实际 `.sage` 文件 PSI 语言为 `Sage`；现在同时注册 `Sage` 与 `Python`，并放宽新 bare identifier 无 reference PSI / dumb-mode 时的 external fallback。fresh popup probe 成功，之后完整 suite 成功：core `SageApiIndexTest` 26/26，SageCompletion 1/1，IndexService 4/4，DocumentationProvider 2/2，IntelligenceHarness 8/8。当前可称 `FULL_ROOT_POPUP_COMPLETION` 仅针对该 external-only representative plus callable insertion path；仍不将单代表提升为所有 2,158 candidates 的 UI 全量等价。
- 2026-08-23：Agent Teams verification round completed. Direct audit confirms dual `Sage` + `Python` completion registration is intentional: the file PSI language is `Sage`, while nested Python PSI elements use `Python`; the `.sage` file gate prevents plain `.py` leakage. Full artifact root shape is 2,158 identities: 60 FUNCTION, 1,852 ALIAS, 246 CONSTANT, no root CLASS/PROPERTY, so the representative `AffineSpace` FUNCTION popup plus callable insertion is the highest-value popup gate without enumerating UI variants redundantly. No additional production change was recommended. Next promotion gates remain runtime semantics, all-context PSI inference, full bundled-index packaging, and product/release verification.
- 2026-08-23：补充 root popup representative coverage：full external index 的 `sage.all.var`（ALIAS）和 `sage.all.RR`（CONSTANT）均通过真实 `myFixture.completeBasic()` popup harness；fresh final suite 通过 core `SageApiIndexTest` 26/26、SageCompletion 1/1、IndexService 4/4、DocumentationProvider 2/2、IntelligenceHarness 9/9。`git diff --check` 通过。该代表性 popup 证据仍不等于 2,158 个候选在所有 IDE 上下文的 UI/语义全等。
- 2026-08-23：新增 external-only factory assignment probe：`RealField()` 的 full-index return metadata 为 KNOWN `sage.rings.real_mpfr.RealField_class`，query 层安全传播断言通过；但真实 `R = RealField(); R.pre<caret>cision` popup 返回空列表。该失败已写入当前增量，说明 full query metadata 尚未自动转化为所有 external-only factory assignment 的 PSI member type；不得将该 gate 标为通过或宣称全量类型补全。下一步应最小化定位 call callee resolution / `SageTypeProvider.genericFactoryAssignedType` / class stub availability 的断点。
- 2026-08-23：为 factory probe 增加最小 `sage/all.pyi` 与 `sage/rings/real_mpfr.pyi` fixtures（均放在 `site-packages/sage` 路径，含 `GF` anchor 与 `RealField -> RealField_class`，故日志已确认 implicit `RealField` 命中 `sage/all.pyi`）；但 `TypeEvalContext.getType(R)` 仍为 `null`，popup 仍为空。该新证据把断点从缺少 `sage.all` anchor 收窄到 `SageTypeProvider` assignment dispatch / PyCall callee callable resolution / returned class type construction；尚未修改生产逻辑。
- 2026-08-23：官方 checkout `G:\Projects\intellij-community-sage-ide` 已执行 `git pull --ff-only upstream master`，由 `b0001cd6c539` 快进至 `3b652e714c12`，共新增 285 个上游提交；官方 checkout 仅保留约定豁免的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore`，没有非豁免改动。上游未改动 staging overlay 依赖的 `DevModeProductRunner.kt`、`IdeBuilder.kt`、`BazelRunner.kt` 和 Sage product properties 文件；当前项目仍以旧官方 SHA staging-build6 为可复现产品基线，未未经验证升级 staging。
- 2026-08-23：已将本轮通过 Runtime 回归的根级 operation lock、installer/lifecycle 并发保护、catalog rotation 边界测试和 installer failure-preservation 测试提交为 `4a815d0`（`让 Runtime 并发生命周期操作保持可恢复`）。提交前后 `:core:runtime:test :plugins:sage-core:test --no-daemon --console=plain -PrunRuntimeTests=true --rerun-tasks` 均取得 `BUILD SUCCESSFUL`；本提交不包含未完成 Sage Intelligence、CTF、UI 或真实远端 endpoint 修改。首次 targeted test 因 `core/sage-api/build/libs/sage-api-0.1.0-dev.jar` ZIP 输出异常失败，删除无残留进程后的生成物后重跑通过。
- 2026-08-23：`4a815d0`/`d46eeb7` 提交后再次执行 `:plugins:sage-core:buildPlugin :plugins:sage-core:verifyPlugin`，`BUILD SUCCESSFUL`（19 tasks，PY-261/PY-262 均 Compatible；2 deprecated、29 experimental API usages）。
- 2026-08-23：官方 checkout 拉取到 `3b652e714c12` 后，旧 staging-build6 仍固定在已验证的 `b0001cd6c539`。再次直接运行 `verify-upstream-staging.ps1 -FinalCheck` 按预期在 official SHA 检查失败，不能把旧 staging 宣称为新官方基线的 FinalCheck 通过；官方上游相对旧基线未改动 overlay 依赖的关键 `DevModeProductRunner.kt`、`IdeBuilder.kt`、`BazelRunner.kt`。在不重新同步 staging、重建产品前，不升级 ExpectedCommit，也不伪造 FinalCheck 结果。
