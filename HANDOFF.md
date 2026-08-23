# SageMath CTF IDE 交接快照

> 更新时间：2026-08-23（Runtime Manager 与 CTF 会话状态同步；CTF 暂不合入 main）。本文只保留当前状态、可复核证据、剩余风险和下一步；历史失败过程不在此重复记录。

## 1. 总体状态

项目定位：基于 IntelliJ Community 的独立 SageMath CTF IDE。核心差异化是 **SageMath 代码智能 + 可管理 Sage Runtime + CTF 工作台**，不是把插件 ZIP 或普通 PyCharm 安装目录冒充完整产品。

当前判断：

- **P1 Community 产品接入/Windows 构建链：已完成开发基线，尚未完成最终发行门。** Community overlay、Sage product properties、Sage Core bundled plugin、Windows x64/aarch64 installer、sidecar、法律文件 overlay、x64 安装/启动/卸载 smoke 和 FinalCheck 都有历史验证证据。
- **Sage API importer/index integration：当前进入 scoped Sage API integration。** 已完成 generator 修复后的真实 Sage 10.9 外部 index 消费验证：schema 1、84159 entries 可由 `core:sage-api` reader/query 加载；entry provenance 以 `sources` 的 `STUB` locator/digest 和顶层 `sourceDigests` 保留。它不代表 Sage 全量代码智能、正式发行或将全量 index 放入 bundled/resource/product；manifest-level `provenance`/`sourceSpecs`/`treeDigest`/coverage/diagnostics 仍属于 importer sidecar/report 质量门。
- **P2 CTF MVP/Math Lab：实现会话已完成，后续只从 `parallel/ctf-mvp` 进入主线整合。** `parallel/ctf-mvp`（当前工作分支，最新提交 `62847f0`；与 `integration/ctf-mvp` 共享基础 MVP 内容但不是其 Git 后继）交付独立 `plugins/ctf-tools`、CTF project/challenge/profile、flag 扫描、运行历史/evidence、Crypto/Encoding helpers、loopback CyberChef-server 和图形化 CTF Math Lab；Math Lab 覆盖群/环/域、椭圆曲线、RSA、DH、DES 的专用表单、预检、运算追踪、可视化、教学步骤和本地化。`integration/ctf-mvp` 是旧的基础 MVP/安全加固候选，不再与 `parallel/ctf-mvp` 并行合并或重复 cherry-pick。
- **Runtime Manager：核心实现会话已完成，产品 UI/真实端点验收仍需单独完成。** `parallel/runtime-manager`（tip `c532e09`）交付签名 Catalog、已验证 mirror/cache、选择/切换/移除/回滚生命周期、Settings/Project SDK binding、Native/WSL/Docker/SSH target-aware command/probe 和显式路径映射。
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

### 最高优先级：scoped Sage API integration

1. 保持已修复 generator 的 no-`--allow-conflicts` gate 和 deterministic 输出；没有新的实际证据时，不继续重写 conflicts 算法。
2. 定义受控的 versioned/scoped API index envelope 或 sidecar，把 artifact/provenance/treeDigest/coverage/diagnostics 与当前可消费 index 明确关联；entry source kind 继续按 schema 映射为 `STUB`，不把 `STUBGEN` 伪装成 Kotlin source kind。
3. 扩大一小组人工维护的 Sage 10.9 expected contract，并把签名、参数、返回类型、documentation 的质量门拆成可审计 scoped checks；不得从 84159-entry index 自动反推全量 expected。
4. 若将某个 slice 推进 bundled/resource，只允许经过 reviewed、versioned、scoped artifact；ignored full index 继续只走外部 `-Dsage.api.index` 验证路径。
5. Gradle 的 `plugins:sage-core` test path 已可运行；直接 IDE/.iml module classpath 尚未证明，若未来选择该路径再单独处理 module/namespace 依赖，不把它与当前成功的 Gradle integration 混淆。

### Runtime 与 CTF

- Runtime Manager 实现会话已完成：`parallel/runtime-manager` tip `c532e09` 交付 signed Catalog、verified mirror/cache、生命周期选择/切换/移除/回滚、SDK binding、Native/WSL/Docker/SSH target-aware command/probe 和显式路径映射；独立 worktree fresh `:core:runtime:test -PrunRuntimeTests=true` 为 38 tests、0 failures/errors。
- CTF MVP 实现会话已完成：最新 `parallel/ctf-mvp` tip `62847f0`（当前工作分支；与 `integration/ctf-mvp` 共享基础 MVP 内容但不是其 Git 后继）交付 `plugins/ctf-tools`、Challenge Profile UI/model、flag scanner、bounded script execution、run history/evidence、Crypto/Encoding helpers、loopback CyberChef adapter 和图形化 CTF Math Lab。Math Lab 提供群/环/域、椭圆曲线、RSA、DH、DES 的专用表单、预检、运算追踪、可视化、教学步骤与中英文案。最新独立 worktree fresh `:core:model:test :plugins:ctf-tools:test :plugins:ctf-tools:buildPlugin -PrunModelTests=true -PrunCtfToolsTests=true --no-daemon --console=plain --rerun-tasks` 为 `BUILD SUCCESSFUL`；15 suites/51 tests、skipped=0、failures=0、errors=0，exit `0`。
- Runtime Manager 会话尚未合入当前 `main`；CTF 后续只从 `parallel/ctf-mvp` 合入，`integration/ctf-mvp` 不再作为第二个待合并来源。真实 Settings/Project SDK UI、WSL/Docker/SSH 端点、live CyberChef-server、Math Lab IDE live ToolWindow、完整产品 smoke 和默认插件/分发接入仍待验证。Jupyter 继续作为可选执行/兼容层，不作为 Sage 原生编辑体验的前置条件。

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
- Runtime Manager 完整实现会话另位于 `parallel/runtime-manager`（tip `c532e09`），已在上方 Runtime 与 CTF 段落记录；当前未宣称其独立 worktree 已合入 `main`。
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
- 本增量仍未执行 fresh product build、Windows x64 installer smoke、release audit 或 `verify-upstream-staging.ps1 -FinalCheck`；也未进行真实 IntelliJ Settings/Project SDK click flow、WSL/Docker/SSH live endpoint 或 concurrency/fault-injection 验收。不要用历史 staging/release 证据替代这些门。

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
