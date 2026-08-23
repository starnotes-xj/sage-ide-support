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
