# SageMath CTF IDE 交接快照

> 更新时间：2026-08-23。当前只推进 SageMath 代码智能；CTF 暂停，不合入 `main`。

## 1. 当前结论

- 目标：完成可验证、可使用的 SageMath API、补全、类型、签名和文档智能。
- 当前状态：真实 Sage 10.9 external index 已可被 JVM query 层完整消费；PSI 语义消费仍在推进。
- 当前状态：indexed METHOD 的 callable bridge、真实 sparse fixture 的调用返回类型和 EOF qualified completion 已有 fresh BUILD SUCCESSFUL 证据；Sage-focused gate 已通过，完整 plugin gate 仍被独立的 WSL Conda debug 命令断言阻塞。
- 不能宣称：runtime-semantic FULL、所有 PSI 上下文等价、full index 已 bundled/product、正式 release-ready。

## 2. 已验证证据

### Real Sage 10.9 artifact

- Artifact：`build/sage-api-real/final-live-9/sage-api-index.json`（ignored external artifact）。
- Sage `10.9` / Python `3.13.15`；`2,839` source digests；`84,187` raw declarations；`84,159` normalized entries。
- Fresh generator：`24` duplicate diagnostics、`conflicts=0`、无 `--allow-conflicts` 仍 exit `0`；index SHA-256 以 `4f8bd2fc…` 开头，treeDigest 以 `69d0524a…` 开头。
- 已证明的 query 数据范围：
  - `FULL_SYMBOLS`：`84,159/84,159`；
  - `FULL_CANONICAL_LOOKUP`：全部 `(qualifiedName, kind)` 可回取；
  - `FULL_ROOT_COMPLETION_METADATA`：`2,158` 个 `sage.all` exports；
  - `FULL_MEMBER_METADATA`：`49,348` 个 member entries；
  - `FULL_SIGNATURE_METADATA`：`52,236` 个带 signature entries；
  - `FULL_DOCUMENTATION_METADATA`：`57,425` 个带 documentation entries；
  - 安全 unique-known return 子集：`5,525` 个 METHOD。
- Full index 只通过 `-Psage.external.fullIndex=<path>` 验证，未复制进 bundled/resource/product。上述范围是 artifact/query 可达性证明，不是运行时或任意 IDE 场景语义证明。

### 已完成的 Sage 代码路径

- `core:sage-api`：immutable schema/domain/index/query；支持 namespace-local lookup、canonical lookup、members、signatures、documentation 和保守 return-type 查询。
- `plugins:sage-core`：implicit `sage.all` root completion、external-index documentation、canonical Sage stub owner、indexed member provider、factory return type propagation。
- 关键策略：native `.pyi` PSI 优先；external metadata 只做 additive/fail-closed 补充；UNKNOWN、DYNAMIC、union、ambiguous overload 不传播为确定类型。

## 3. 当前证据

- 实现文件：`plugins/sage-core/src/main/kotlin/com/starnotesxj/sageide/completion/SageApiClassMembersProvider.kt`。
- 测试：`SageIntelligenceHarnessTest.testIndexedMemberCallableTypePropagatesThroughSparseStub`。
- callback-backed `PyCustomMember` bridge 已编译；在真正 sparse Matrix fixture（`matrix-sparse.pyi` 位于实际导入路径）中，`solve_right` 可解析，索引 callable 的用户参数为 `[rhs]`，返回类型为 canonical `sage.matrix.matrix.Matrix`。
- 根因已定位：EOF qualified completion 的 recovered reference 需要 Python 的 `codeCompletion`/`getCompletionVariants` 路径，且结果必须使用 member-local prefix matcher；否则 `CompletionResultSet` 会按完整 EOF/qualified 前缀过滤掉已经生成的 indexed lookup。
- 修复：从当前/前一可见 leaf、`parameters.offset - 1` 和文件末字符恢复 qualified reference；使用 `TypeEvalContext.codeCompletion`，并委托 `PyClassType.getCompletionVariants(reference.name, reference, ProcessingContext())`，让 Python 引擎正常调用已注册的 `PyClassMembersProvider`。
- 单测独跑的新鲜 run 曾 `BUILD SUCCESSFUL`，但随后完整 focused gate 暴露非稳定性：`core:sage-api:test` 全部通过，plugin 测试共 `19` completed、`1` failed；同一 sparse regression 又在 `SageIntelligenceHarnessTest.kt:225` 返回空 completion。失败 XML 显示 `BType=PyClassType: sage.matrix.matrix.Matrix`，说明问题可能是测试顺序/全局 completion 或 service 状态，而非类型传播本身。
- 新错误已记录；在修复并重新验证前，不宣称 sparse bridge 完成。
- 2026-08-23 新鲜 truly-sparse 重跑把 `matrix-sparse.pyi` 放到实际导入路径 `sage/matrix/matrix.pyi`，并移除 native `solve_right` fixture；索引 callable 的用户参数已校准为 `[rhs]`。member completion 现通过 `CompletionResultSet.withPrefixMatcher(memberPrefix)` 使用属性局部前缀，避免 EOF 的完整 token 前缀过滤 indexed lookup。

## 3A. 本轮 WSL Conda 支持增量与新鲜错误

- 已确认真实 `Ubuntu` WSL：`/home/starnotes/miniconda3/bin/conda`，环境 `sage`，Sage `10.9`，Python `3.13.15`；直接执行 Sage `-c 'print(2+2)'` 返回 `4`。
- 已发现原有 `wsl.exe ... bash -lc` 不可靠：该发行版默认 shell 为 zsh，且 Windows 参数展开会把 `${'$'}HOME` 等脚本变量提前吞掉；固定 `conda.sh` 探测因此误报 `NO_CONDA`。
- 本轮实现方向：WSL 命令和自动发现强制 `wsl.exe --exec /bin/bash`，优先用 `conda shell.bash hook`，并新增可持久化的可选 `wslCondaExecutable`；未选择 managed Sage SDK 时，WSL 运行配置可 fail-closed 地解析该外部 conda 环境，显式 Sage SDK 仍保持 manifest 校验。
- 新鲜构建恢复：Kotlin cache mode 错误使用 `--no-build-cache` 绕过，修正 WSL 路径引号断言、标准 conda.sh 动态路径记录、`ExecUtil` 超时类型、项目 SDK fallback 与 WSL home resolver 后，`:plugins:sage-core:test --tests com.starnotesxj.sageide.run.SageDebugCommandLineStateTest -PrunSageCoreTests=true --rerun-tasks --no-build-cache` 已 `BUILD SUCCESSFUL`、`21 actionable tasks`；WSL 命令/探测/调试回归真实执行并通过。最终 `:core:runtime:test :plugins:sage-core:test -PrunRuntimeTests=true -PrunSageCoreTests=true --rerun-tasks --no-build-cache` 也已 `BUILD SUCCESSFUL`、`23 actionable tasks`，`git diff --check` 无错误（仅 CRLF 提示）。真实包装 smoke：Sage `10.9`、Python `3.13.15`、`print(2+2)` 输出 `4`、exit `0`。随后 fresh `:plugins:sage-core:buildPlugin :plugins:sage-core:verifyPlugin --no-build-cache` 已 `BUILD SUCCESSFUL`、`19 actionable tasks`，PY-261/PY-262 均 Compatible。

## 3B. 产品/安装包新鲜状态

- staged `BuildDev` / `BuildInstaller` 使用 `G:\sage-build\staging-build6` 与 JDK 25；DSH 单次前台调用的 600 秒墙钟上限在安装器后段中断了多次调用。新鲜 trace 已证明 `sage-core` Bazel plugin、`dist.win.x64` 和 `dist.win.aarch64` 布局已生成，但当前 artifacts 目录尚无本轮 Windows installer `.exe/.sha256/.sha512`；不能把旧产物算作本轮安装包证据。
- nested Bazel cwd 修复已生效：installer trace 不再出现 output-tree cwd 错误，`build plugins by Bazel` 与 `copy plugins built by Bazel` 均完成；为生成可验证的 Windows archives，overlay installer target 不再跳过 `WINDOWS_ZIP_STEP`（仍跳过签名与跨平台分发）。新鲜 artifacts 已生成：`sageMath-263.SNAPSHOT.win.zip`（674,130,070 bytes）及 `.sha256/.sha512`、`sageMath-263.SNAPSHOT-aarch64.win.zip`（639,592,978 bytes）及 `.sha256/.sha512`，时间均为本轮 2026/8/24 04:18。x64 archive 已解压并运行 `bin/sage64.exe --version`，输出 `SageMath CTF IDE 2026.3 EAP`、`Build #SMC-263.SNAPSHOT`、exit `0`；`--help` 与 `--list-commands` 也 exit `0`。archive 形态的产品包与 x64 smoke 已完成，但启用 `useBigNsisInstaller = true` 后 fresh NSIS .exe 构建在生成约 303 MB 的临时安装包时因 G: 盘仅剩约 209.87 MB 报 `java.io.IOException: 磁盘空间不足`；当前 artifacts 中的两个 .win.zip 是该失败轮留下的同尺寸 partial/无 sidecar 产物，不得作为 fresh release 证据。已释放旧 `nested-bazel`/`bazel-output` scratch 后 G: 约剩 18.7 GB，待清理/重新构建。`release audit` 首次 fresh 运行准确报告正式 .exe、uninstaller、SPDX 缺失；脚本已额外记录 archive 形态但仍保留正式 installer 缺失错误。`verify-upstream-staging.ps1 -FinalCheck` 已实际执行并因官方 checkout 当前 SHA 为 `3b652e714c12009bb69f0a2d2416dad02259fe5d`、而脚本要求冻结 SHA `b0001cd6c53979b384def7a1e3febe061e2ef687` 而失败；用当前官方 SHA 作为临时期望值再次执行则准确暴露 staging 仍为冻结基线 `b0001cd6c53979b384def7a1e3febe061e2ef687`，因此未绕过基线保护。官方 checkout 工作树仅有允许忽略的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore`。

## 4. Runtime 扩展本轮增量与新鲜错误

- 本轮开始实现既定优先级：先修复 WSL Settings 的 Native/WSL executable 跨模式污染，并补充无 managed SDK 的 Native fallback；随后建立 Docker/Podman image-owned Sage Run 命令模型，容器 Debug 保持 fail-closed；SSH transport 尚未接入。
- 首次 focused 编译发现 `ContainerCommandBuilder.kt:111` 误写入 `EOF`，已删除；随后新测试误用了 core 未声明的 JUnit 4 API，已改用 `kotlin.test`；删除单个 generated runtime JAR 后，容器/WSL focused `:core:runtime:test :plugins:sage-core:test --tests ContainerCommandBuilderTest --tests SageDebugCommandLineStateTest` 已 `BUILD SUCCESSFUL`、`23 actionable tasks`。
- 新增 Settings state isolation 测试并重跑 plugin focused 后，编译曾被现有未提交 Sage Intelligence 文件 `SageApiModuleMembersProvider.kt:28` 的 `PsiElement` unresolved 阻塞；已补上该文件缺失 import（仅编译修复，不改变 Runtime 设计）。随后 `:plugins:sage-core:test --tests SageRunSettingsConfigurableTest --tests SageDebugCommandLineStateTest` 已 `BUILD SUCCESSFUL`、`21 actionable tasks`。
- 最新 Runtime + Sage core 联合 gate 首次未通过：现有未提交 `SageTypeProviderTest.kt:30-56` 含未闭合多行字符串/错误 `configureByText` 调用；已修复该测试语法后重跑，Gradle 又在 `core/runtime:compileTestKotlin` 触发 Kotlin FIR 内部错误（`RuntimeCatalog.class` 不存在）。停止残留 Gradle JVM、删除被锁 generated runtime JAR 后，单独 `:core:runtime:test --tests ContainerCommandBuilderTest` 与 `:plugins:sage-core:test --tests SageRunSettingsConfigurableTest --tests SageDebugCommandLineStateTest` 均 `BUILD SUCCESSFUL`；再次联合 gate 曾在 `core:sage-api:compileKotlin` 删除 `build/kotlin/compileKotlin/cacheable/caches-jvm` 时失败，清理该 generated cache 和残留 JDK 25 构建 JVM 后，最终联合 `:core:runtime:test :plugins:sage-core:test -PrunRuntimeTests=true -PrunSageCoreTests=true` 已 `BUILD SUCCESSFUL`、`23 actionable tasks`。
- UI/产品只读审查新发现：`sageParametersField` 被三个 Swing card 共享导致 Native/WSL 实际缺字段；Configurable create 非幂等且无 dispose；detect 裸 Thread 读取 Swing 字段并在 EDT 可能做 PATH 探测；Docker detect 固定 docker 且只 discovery 不 probe；container dir 未 fail-closed 校验；Native external fallback 没有 Python 导致 Native Debug 必然 fail。按此顺序修复，修复期间不宣称 UI click-flow 或 Docker real probe 完成。
- 本轮已新增 `SshCommandBuilder.kt`：严格 `ssh -F none -T`、host-key、known_hosts、publickey/agent、无 password/Proxy/forwarding；远端命令固定 `cd -- && exec` 并逐词 POSIX 单引号 quoting；新增 SSH Settings 字段、SSH fallback 和 Run wiring。容器 probe 已改为 production `JdkContainerRuntimeExecutor`，共享 `RuntimeControl`/bounded output，要求 version 非空且表达式精确为 `4`，`resolveContainerExecutables` 现在先做 profile 校验再 probe。首次 core test 编译已通过，但 SSH 测试有一条错误负断言，已改为禁止挂载参数；随后 `:core:runtime:test --tests ContainerCommandBuilderTest --tests SshCommandBuilderTest` 已 `BUILD SUCCESSFUL`、`4 actionable tasks`。补充容器 non-Sage expression、profile directory 和 production executor no-mount 回归后，core focused 再次 `BUILD SUCCESSFUL`、`4 actionable tasks`。最新 SSH path parsing 与容器/Settings 联合 focused 仍 `BUILD SUCCESSFUL`、`23 actionable tasks`。
- 接入 SSH Settings card、异步 detect 生命周期与 service probe 后，首次 plugin Kotlin 编译失败：`SageRunSettingsConfigurable.kt:175` 缺 `RuntimeOperationResult` import；`SageRuntimeService.kt:75` submit 返回可空泛型；新增 `SSH` 后 `detectAndProbeAsync` 与 `SageRuntimeDetectionResult.isReady` 两处 when 非穷尽。已补 imports、改 submit、补 SSH branches，并将 Configurable 生命周期改为 `disposeUIResources()`；随后 `:plugins:sage-core:compileKotlin :plugins:sage-core:compileTestKotlin -PrunSageCoreTests=true` 已 `BUILD SUCCESSFUL`、`14 actionable tasks`，仅保留已有 warning 与一条新 cast warning。之后 focused `:plugins:sage-core:test --tests SageRunSettingsConfigurableTest --tests SageDebugCommandLineStateTest` 的旧断言阶段曾 `BUILD SUCCESSFUL`、`21 actionable tasks`；扩展 create/dispose 回归后曾因 root child 数断言失败，已把共享 `sageParametersField` 移至 cards 外的单一 parent 并修正行号/测试。最新联合 focused `:core:runtime:test :plugins:sage-core:test --tests ContainerCommandBuilderTest --tests SshCommandBuilderTest --tests SageRunSettingsConfigurableTest --tests SageDebugCommandLineStateTest` 已 `BUILD SUCCESSFUL`、`23 actionable tasks`。随后又将 Settings detect 的 native/container 分支接入共享 `RuntimeControl`（WSL保留有界调用）；plugin compile/test Kotlin 重跑已 `BUILD SUCCESSFUL`、`14 actionable tasks`。安全审查后新增 stale detect generation/mode invalidation、Docker mount-dir snapshot、Apply numeric/profile validation、SSH script regular-file/request checks、NOFOLLOW trust-file policy 和 generic SSH builder fail-closed；最新 core 重编译首先暴露两处真实回归：`RuntimeBundledPythonTest` 因全局 mapper 拒绝 runtime root 映射而失败，`RuntimeManagerHardeningTest` 因 JDK target executor 仍先构造已禁用 generic SSH argv 而失败。已恢复通用 mapper 的 runtime-root 兼容性，并让 `JdkRuntimeTargetExecutor` 仅对本地目标构造 argv、SSH 直接走注入式 remote executor；受影响 core tests 已恢复，仅新加的通用 mapper root-as-file 负断言与既有 runtime-root 设计冲突，已移除（SSH Run 入口仍单独拒绝 root script）。随后受影响 core focused（RuntimeBundledPython、RuntimeManagerHardening、RuntimeManagerFeature、SshCommandBuilder）已 `BUILD SUCCESSFUL`、`4 actionable tasks`。plugin 重编译首个错误为 `SageRuntimeService.kt:189-190` 缺 `SshSageRunRequest` import/类型推断；已补 import，随后 `:plugins:sage-core:compileKotlin :plugins:sage-core:compileTestKotlin -PrunSageCoreTests=true` 已 `BUILD SUCCESSFUL`、`14 actionable tasks`（保留既有 warnings）。新增 Apply numeric regression 初次因 focused fixture 直接调用未注册 application service 而 NPE，已改为验证原始 State 未变；最新 `SageRunSettingsConfigurableTest` + `SageDebugCommandLineStateTest` 已 `BUILD SUCCESSFUL`、`21 actionable tasks`。随后移除了未使用、WSL cancellation-blind 且将 Docker discovery 当作 ready 的旧 `detectAndProbeAsync`/`SageRuntimeDetectionResult` API，并让 `SageRuntimeProbeHandle.cancel()` 同时 interrupt future；plugin compile/test Kotlin 已重新 `BUILD SUCCESSFUL`、`14 actionable tasks`。最新完整 `:core:runtime:test :plugins:sage-core:test -PrunRuntimeTests=true -PrunSageCoreTests=true --rerun-tasks --no-build-cache` 已 `BUILD SUCCESSFUL`、`23 actionable tasks`，保留既有 Kotlin warnings，无测试失败；最后补充 SSH resolver NOFOLLOW trust-file 检查后，同一 full gate 再次 `BUILD SUCCESSFUL`、`23 actionable tasks`。随后 fresh `:plugins:sage-core:buildPlugin :plugins:sage-core:verifyPlugin --rerun-tasks --no-build-cache` 已 `BUILD SUCCESSFUL`、`19 actionable tasks`；PY-261/PY-262 均 Compatible，报告为 2 deprecated API、31 experimental API。按完成纪律尝试 fresh x64 release audit：`G:\sage-build\staging-build6\artifacts` 不存在；对现有 `G:\sage-build\release-final` 只读审计真实 exit `1`，9 个 Error（installer/uninstaller/archive 与 product-info/SPDX/third-party/dependencies/sources 均缺），不能宣称 product/release-ready。随后 `verify-upstream-staging.ps1 -FinalCheck` 真实 exit `1`，官方 checkout 实际 SHA `3b652e714c12009bb69f0a2d2416dad02259fe5d` 与冻结要求 `b0001cd6c53979b384def7a1e3febe061e2ef687` 不符；未修改官方 checkout。最后一次 core-only `:core:runtime:test --rerun-tasks --no-build-cache`（移除恒真 mapper 校验后）仍 `BUILD SUCCESSFUL`、`4 actionable tasks`；`git diff --check` 无错误，仅有 Git LF/CRLF warnings。随后源码状态一致的最终联合 `:core:runtime:test :plugins:sage-core:test --rerun-tasks --no-build-cache` 再次 `BUILD SUCCESSFUL`、`23 actionable tasks`。最后对同一源码状态重新运行 `:plugins:sage-core:buildPlugin :plugins:sage-core:verifyPlugin --rerun-tasks --no-build-cache`，`BUILD SUCCESSFUL`、`19 actionable tasks`；PY-261/PY-262 均 Compatible，2 deprecated API、31 experimental API。Verifier 的 documented API 页面网络抓取曾 timeout，但不影响两目标 Compatible 结果；该网络异常已保留在构建日志中。


## 4. 下一步

1. WSL Conda 正式支持的下一阶段是 IDE UI / 真实运行配置端到端验收：在 Settings | Tools | SageMath 中确认 `Ubuntu`、`sage`、`/home/starnotes/miniconda3/bin/conda`，再运行真实 `.sage` 文件；当前已有命令层和真实 WSL smoke，但尚未有 product UI click-flow 证据。

### 2026-08-24 fresh verification increment

- Fresh `:core:sage-api:test` focused run：`BUILD SUCCESSFUL`；fresh complete `:core:sage-api:test :plugins:sage-core:test` run：`BUILD SUCCESSFUL`，测试 XML 合计 `74 tests, 0 failures, 0 errors, 0 skipped`。其中 `SageIntelligenceHarnessTest` `12/0/0`、`SageApiIndexServiceTest` `4/0/0`、`SageApiDocumentationProviderTest` `2/0/0`、`SageTypeProviderTest` `2/0/0`、`SageDebugCommandLineStateTest` `8/0/0`、`SageApiIndexTest` `27/0/0`。保留 `SageApiIndexJsonReader.kt:136` unchecked-cast warning 与测试中 5 个非阻塞 Kotlin warning。
- Fresh WSL evidence：`Ubuntu` explicit `/bin/bash`，`/home/starnotes/miniconda3/bin/conda`，`conda activate sage`，Sage `10.9`，Python `3.13.15`；`sage -c "print(2+2)"` 返回 `4`；代表性 `factor(84)` 返回 `2^2 * 3 * 7`，`matrix(...).det()` 返回 `-2`，exit `0`. PowerShell 调用会额外出现本机 WSL localhost 转发的乱码 warning，但 Linux 命令与 exit code 成功。
- `git diff --check` exit `0`，仅有 LF/CRLF conversion warnings。fresh x64 release audit 仍为 findings：正式 NSIS installer/uninstaller 缺失、SPDX 缺失、当前 `.win.zip` 无 sidecar（因前一轮 NSIS 磁盘空间失败留下 partial artifact）；不能宣称 formal release-ready。
- Fresh artifact repair evidence：从生成的 `idea.nsi` 直接用 staged NSIS `makensis.exe` 重跑成功，exit `0`；生成 `sageMath-263.SNAPSHOT.exe`（497,071,939 bytes）与 `Uninstall-SMC-amd64.exe`（220,191 bytes），并确认 G: 盘约剩 18.5 GB。该 direct NSIS run 尚未生成 installer SHA sidecar；SPDX 仍缺失。当前 `.win.zip` 仍为先前空间失败轮的 partial artifact，未作为 release 证据。
- 已在 product overlay 中启用 `useBigNsisInstaller = true`；并为 Sage product 配置 SPDX creator/license/document namespace，待下一轮完整 target 重新生成 `.spdx.json` 和带 sidecar 的新鲜 archives/installer 后再审计。
- 新错误：删除旧 Bazel scratch 后重新分析 `//python/build:sage_i_build_target`，Bazel 的 LLVM external repository cache 不完整，先报 `utils/bazel is not a package`（缺 `configure.bzl`）；用 clean `bazel-output2` 重试又在 Windows symlink 创建 `catboost-shadow-need-slf4j-1.2.5.jar` 时 I/O 失败，并把 G: 临时耗尽到约 15 MB，随后已删除该 disposable output root，恢复约 18.6 GB。尚未重新运行完整 product target；不能把 direct NSIS 重跑替代完整 product build。
- 在不改动 staging 源码的前提下，已对 direct NSIS 产物生成并校验 installer/uninstaller SHA-256/SHA-512 sidecars；audit 显示 hashes 全部通过，正式 exe/uninstaller 均存在，但均为 `NotSigned` warning，archive sidecars 缺失且 SPDX 仍是唯一 Error。`-FailOnFindings` 真实 exit `1`，因此仍不宣称 release-ready。
- Protected `verify-upstream-staging.ps1 -FinalCheck` 仍按设计拒绝：official checkout 实际 SHA `3b652e714c12009bb69f0a2d2416dad02259fe5d`，要求冻结 SHA `b0001cd6c53979b384def7a1e3febe061e2ef687`；official checkout 未修改，仅有允许的 `?? hashcat_sessions.db`、`?? jupyter/.gitignore`、`?? notebooks/.gitignore`。
2. SSH/HPC 暂不作为首版 WSL 之后的必做项：当前 `RemoteSsh` 只有元数据、路径解析和注入式 target executor 契约，Sage run/debug 明确 fail-closed；若要正式支持，需独立 transport、认证/密钥、远程工作区同步、端口转发、取消/超时、作业队列和远程 Python debugger，不应只把 `ssh` 拼进命令行。
3. 继续定位 `B = A.solve_right(A)` 的 return type 到 `B.det` completion 之间的断点；优先检查 completion fixture 重建、typed target 类型和 indexed owner 闭包，不增加方法名特例。
4. 让 sparse callable regression test 通过，并保留对 canonical owner、callable 参数和返回类成员的断言。
5. 依次执行 core/plugin focused tests、完整 Sage API/plugin suites 和 `git diff --check`；Gradle 不并发。
6. Sage gate 全部稳定后，再单独执行 product build、Windows x64 smoke、release audit 和 `verify-upstream-staging.ps1 -FinalCheck`；旧产物不得冒充本轮证据。

建议的 focused 命令：

```powershell
.\gradlew.bat :core:sage-api:test :plugins:sage-core:test `
  --tests com.starnotesxj.sageide.completion.SageIntelligenceHarnessTest `
  --tests com.starnotesxj.sageide.type.SageTypeProviderTest `
  -PrunSageApiTests=true -PrunSageCoreTests=true `
  "-Psage.ide.localSdk=D:/JetBrains/PyCharm" `
  "-Psage.external.fullIndex=G:/Projects/sage-math-ctf-ide/build/sage-api-real/final-live-9/sage-api-index.json" `
  --no-daemon --max-workers=1 --no-build-cache --console=plain --rerun-tasks
```

## 4A. 当前 Runtime 扩展轮次与新鲜错误

- 本轮开始实现优先级：先修复 WSL Settings 的 Native/WSL executable 跨模式污染，并补充无 managed SDK 的 Native fallback；随后建立 Docker/Podman image-owned Sage Run 命令模型，容器 Debug 保持 fail-closed；SSH transport 尚未接入。
- 新增 core 容器命令与 probe 文件后，首次 focused 编译失败：`ContainerCommandBuilder.kt:111` 误写入 `EOF`，已删除。第二次 focused 编译继续失败：新测试使用了 core 未声明的 JUnit 4 依赖（`org.junit.Assert`/`org.junit.Test` unresolved）；已改用 `kotlin.test`。第三次重跑在生成 `core/runtime/build/libs/runtime-0.1.0-dev.jar` 时失败（`Could not create ZIP`），删除单个 generated JAR 后继续发现测试第 56 行嵌套 Pair 断言泛型推断失败；已拆分断言。随后 focused `:core:runtime:test :plugins:sage-core:test --tests ContainerCommandBuilderTest --tests SageDebugCommandLineStateTest` 已 `BUILD SUCCESSFUL`、`23 actionable tasks`。

## 4B. Sage intelligence expansion increment

- 新增普通 Python 显式 Sage 调用的保守类型路径：仅接受 Python PSI 唯一解析且 qualified name 以 sage. 开头的 callee；移除了普通 .py 中按短名称回退到索引的碰撞风险，.sage 的隐式 sage.all 路径仍保持单独处理。新增 SageApiModuleMembersProvider，使用官方 PyModuleMembersProvider EP、PyPsiFacade.findShortestImportableName 和 canonical PyPsiPath 解析，普通 Python 仅获得已显式导入的 sage.* 模块 direct exports。
- 新增普通 .py 显式 Sage factory 正向/非 Sage 负向测试，以及 bundled/full-index coverage matrix 的 symbol-kind、module/member endpoint、signature/documentation、KNOWN/UNKNOWN/DYNAMIC/union 分区断言。模块 EP descriptor、Kotlin main/test compile 和 targeted Sage tests 均已 fresh BUILD SUCCESSFUL；targeted XML 为 SageIntelligenceHarnessTest 13/0/0、SageTypeProviderTest 4/0/0。
- 首次完整 :core:sage-api:test 曾因残留/不一致的 generated output 报 SageApiNormalizer 等约 700 个级联 unresolved；已用 clean + --no-build-cache 前台重跑，随后完整 :core:sage-api:test :plugins:sage-core:test fresh BUILD SUCCESSFUL。测试 XML 合计 82 tests, 0 failures, 0 errors, 0 skipped；其中 SageApiIndexTest 27、SageIntelligenceHarnessTest 13、SageTypeProviderTest 4。

## 5. 工作边界

- 工作区：`G:\Projects\sage-math-ctf-ide`；允许的 staging：`G:\sage-build\staging-build6`。
- 官方 checkout `G:\Projects\intellij-community-sage-ide` 只读；不得修改，也不以其他 checkout 作为官方基线。
- 不修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr`。
- 使用 `D:\Java\jdk-25`；`USERPROFILE/HOME/APPDATA/LOCALAPPDATA/TEMP/TMP` 使用 `G:\sage-build` 下 ASCII 路径。
- 保留所有现有未提交改动；不要 `git add .`、不要提交、不要清理无关文件。`.agent-teams/` 仅为本地协作状态。
- 已知非阻塞 warning：`SageApiIndexJsonReader.kt:136` unchecked cast。

## 6. 完成判定

- 必须先看到 sparse callable test 真实 `BUILD SUCCESSFUL`，再报告该 bridge 完成。
- 必须重新读取完整 Gradle 输出、测试 XML 和 `git diff --check`；没有新鲜证据，不报告 product、installer、smoke、FinalCheck 或 release 完成。
- CTF、Math Lab、远端 Runtime endpoint 和正式发行继续作为后续工作，不得混入当前 Sage 完成结论。
