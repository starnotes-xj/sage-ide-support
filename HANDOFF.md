# SageMath CTF IDE 交接文档

> 精简版：保留当前产品边界、最终构建证据、验证结果和剩余风险；历史过程不重复记录。

## 当前目标

构建可独立发行的 SageMath CTF IDE：

- 基于 IntelliJ/PyCharm Community 官方 Bazel/installer 流程；
- 集成 Sage Core、SageMath Runtime 管理基础和 CTF 工作流；
- 不把插件 ZIP 或普通 PyCharm 安装目录冒充完整产品。

## 仓库边界

- 产品仓库：`G:\Projects\sage-math-ctf-ide`
- staging 构建树：`G:\sage-build\staging-build6`
- 官方上游：`G:\Projects\intellij-community-sage-ide`（固定 SHA：`b0001cd6c53979b384def7a1e3febe061e2ef687`，只读）
- 禁止修改：`G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr`
- 官方保护文件必须保留：`hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore`

## 已实现基线

- `plugins/sage-core/`：Sage 语言/运行能力基线和 bundled plugin 接入。
- `core/model/`：执行目标、CTF Profile、结构化执行结果；默认无固定自动超时，仍支持取消和输出限制。
- `core/runtime/`：HTTPS 下载、SHA-256、manifest/sidecar 校验、ZIP 安全安装、原子发布、版本/current 指针和 locator。
- Community product overlay、staging-only Bazel target、`//build:sage_math` 和 `//python/build:sage_i_build_target`。
- 基础构建/测试、Sage Core ZIP、产品布局和双架构 Windows installer 流程已验证。

## 最新 hardened 构建

最终日志：`G:\sage-build\bundled-next\release-hardening-legal-fix-final.log`；`RELEASE_HARDENING_LEGAL_FIX_FINAL_EXIT_CODE=0`。

产物目录：`G:\sage-build\staging-build6\out\sage-math\artifacts`

| 产物 | 大小 |
|---|---:|
| `sageMath-263.SNAPSHOT.exe` | 482,073,084 bytes |
| `sageMath-263.SNAPSHOT-aarch64.exe` | 446,666,426 bytes |
| `Uninstall-SMC-amd64.exe` | 214,360 bytes |
| `Uninstall-SMC-aarch64.exe` | 213,958 bytes |

四个 EXE 均有独立 `.sha256`/`.sha512` sidecar；最终 audit 对 x64/arm64 installer 和 uninstaller 的 sidecar 全部校验通过。

## Windows 法律文件 overlay

以下两个 distribution 根目录均已验证：

- `G:\sage-build\staging-build6\out\sage-math\dist.win.x64`
- `G:\sage-build\staging-build6\out\sage-math\dist.win.aarch64`

每个目录均包含：`LICENSE.txt`（7563 bytes）、`NOTICE.txt`（110 bytes），以及 `license\LICENSE.txt`、`license\NOTICE.txt`。

实现位置：`product/community-overlay/product-properties/SageMathCommunityProperties.kt`。不得手工修改生成的 distribution 文件。

## 最终验证

### Release audit

报告：`G:\sage-build\bundled-next\release-hardening-audit-legal-fix-all.json`

- 结果：`errors=0`、`warnings=8`、`passed=false`。
- 四个 EXE 的 SHA-256/SHA-512 sidecar：全部通过。
- 两份 SPDX：`ConvertFrom-Json` 均成功，每份 468 packages。
- 剩余 warning：4 个 EXE 未签名；两份 SPDX 标记 `SPDX_WORK_IN_PROGRESS`；两份 SPDX 各有 248 个 `SPDX_NOASSERTION` package。
- 生成日志另记录 deprecated `GPL-2.0`，需要法律审查。

`passed=false` 表示 audit 将 warning 纳入总体失败判定，不表示 sidecar、JSON 或 distribution legal 文件失败。

### x64 install/launch/uninstall smoke

日志：`G:\sage-build\bundled-next\x64-installer-smoke-legal-fix.log`

- installer exit code：`0`；uninstaller exit code：`0`；
- `sage64.exe` 存活检查通过；
- `plugins\sagemath-ctf-sage-core\lib` JAR 存在；
- 安装目录已卸载删除。

### FinalCheck

日志：`G:\sage-build\bundled-next\finalcheck-legal-fix.log`；exit code：`0`。

- 官方 checkout SHA 正确，保护文件仍存在；
- 没有修改官方上游；
- 当前没有 Bazel/Java/NSIS/release 进程残留。

## 仍需完成

1. 接入 Authenticode 签名证书/服务；
2. 完成 SPDX `NOASSERTION`、WIP 标记和 deprecated `GPL-2.0` 的法律审批；
3. 在真实 arm64 主机执行 smoke；
4. 验证真实远程 Sage Runtime catalog/probe；
5. 完善 Runtime Manager 的 IntelliJ adapter、JSON Catalog 签名和版本 probe。


## 本轮增量：Sage API index 第一切片（2026-02-08）

### 实现

- 新增 `core/sage-api/` 独立 JVM 模块，并注册到 `settings.gradle.kts`；不修改既有 Sage PSI/type provider。
- 新增版本化 schema/domain model：Sage/Python 版本、模块/类/函数/方法/属性/常量/别名、重载参数、返回类型、父类、协议、文档、来源、置信度及 Unknown/Dynamic 状态。
- 新增无依赖的 `.pyi` stub extractor 与 normalizer：导入别名、类继承、方法/属性、重载、来源定位和冲突合并均保留为数据；冲突返回 Dynamic 并输出诊断。
- 新增稳定 JSON writer、schema JSON 资源和 coverage diagnostics，覆盖 missing、无签名、dynamic、conflict 分类。
- 新增 fixture/golden 风格 Kotlin tests，验证版本绑定、导入类型限定、重载、父类、属性、别名、冲突、coverage 和稳定 JSON 顺序。

### 验证（真实 exit code）

- `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`：exit code `0`，5 tests completed。
- `./gradlew.bat :core:sage-api:build --no-daemon --console=plain`：exit code `0`；默认 test task 因未传 property 而 SKIPPED，这是预期门控行为。
- `./gradlew.bat :core:model:test :core:runtime:test -PrunModelTests=true -PrunRuntimeTests=true --no-daemon --console=plain`：exit code `0`。
- `git diff --check`：exit code `0`；仅有既有 LF/CRLF warning，无 whitespace error。

### 未完成与风险

- 这不是全量 Sage API intelligence：尚未实现真实 Sage Runtime / `sage-pycharm-stubgen` / signature / documentation 批量 extractor、增量构建、版本 diff、完整 coverage report 和 source-map golden tests；当前已接入 immutable query、validated JSON loader、类型传播和成员 completion 消费的最小链路。
- JSON reader 已接入 index service，并通过模型构造器执行 schemaVersion、结构字段、Unknown/Dynamic 和重复 entry 校验；独立 schema JSON 仍未实现完整 JSON-Schema validator。
- extractor 是刻意有限的 `.pyi` 语法切片，不应被描述为 Sage 全量覆盖；动态/Cython API 仍返回 Unknown/Dynamic。
- 本轮没有运行 Sage Core plugin、Community product、installer、smoke、release audit 或 FinalCheck；既有交接中的产品证据未被本轮重用为 fresh build 证据。
- 未修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr` 或官方 `G:\Projects\intellij-community-sage-ide`；本轮仅修改产品仓库。

### 下一位代理

从 `core/sage-api/src/main/kotlin/com/starnotesxj/sagemath/sageapi/SageApiIndexModels.kt` 和 `SageApiNormalizer.kt` 继续：优先加入真正的 schema loader/validator 与 Python stdlib AST extractor（建议放到 `tools/sage-api-index/`），再接入 `plugins/sage-core` 的 immutable index service；不要把 extractor 逻辑扩展成 Kotlin 函数特例。
## 本轮增量：通用 Sage API 成员解析问题（接手重点）

- 典型复现：`matrix(...)` 返回的矩阵对象可以提示部分成员，但 `solve_right` 未出现在候选中；这类问题不能靠逐个函数补 Kotlin 特例。
- 根因方向：当前 stubgen 数据、Python PSI 和插件侧局部 `SageTypeProvider`/completion 规则没有形成统一的版本化 API index、工厂返回类型解析和继承/parent/mixin/category 成员闭包。
- 通用解决路径：Sage Runtime introspection + `sage-pycharm-stubgen` + 签名/文档 → extractor/normalizer → versioned API/type/document index → immutable loader/query → factory/constructor return type → inheritance/parent/mixin/category/dynamic closure → completion/signature/documentation。
- `solve_right` 只能作为矩阵成员闭包和 coverage/golden test 的回归样例，不能作为硬编码特例。
- 本轮新增 `HANDOFF-PROMPT.zh-CN.md`，已明确“实际修改文件、提交保存本轮成果，然后继续推进”，并要求下一轮先添加失败测试，再接入 `core:sage-api` 与 `plugins:sage-core`。
- Jupyter 不参与该问题的类型权威链路；Sage 原生编辑器和 Sage Console 仍是首要方向。

## 交接规则

- 不修改官方 checkout、`sage-ide-support` 或 `sage-pr`。
- 不手工编辑 installer、SPDX 或 distribution 产物来伪造验证结果。
- 新构建必须使用 JDK 25、ASCII `G:\sage-build` 环境路径，并记录真实 exit code。
- 后续 Git 提交使用中文 Lore 格式，并包含 `约束：`、`拒绝：`、`置信度：`、`影响范围：`、`后续指引：`、`已验证：`、`未验证：`。
## 本轮增量：矩阵工厂类型传播与 bundled index（进行中）

已实际写入：

- `SageTypeProvider` 增加通用 `target = sage_factory(...)` 路径：通过 `PyCallExpression.multiResolveCalleeFunction` 得到 callable qualified name，查询 immutable Sage API index 的唯一 KNOWN return type，再通过 Sage stub class index 构造实例类型；不包含 `solve_right` 方法名特例。
- `SageApiIndexService` 增加 application service 和外部路径加载；没有 `-Dsage.api.index` 时加载插件资源 `sage-api-index.json`，JSON 经过 schema reader 和模型构造器校验后才安装。
- 新增 `plugins/sage-core/src/main/resources/sage-api-index.json`，当前是可运行的最小矩阵 slice，包含 `matrix` factory return、`Matrix` class、`determinant` 和 `solve_right`。它是接入链路 fixture，不宣称全量 Sage 覆盖。
- `SageApiIndexTest` 新增 matrix factory return 与 generic member query 回归测试，当前 core 测试通过。
- `SageTypeProviderTest` 新增目标赋值类型回归用例，等待 plugin test classpath 可用后执行。
- 新增 `plugins/sage-core/src/test/resources/testData/completion/matrix-solve-right.sage`，固定 `A = matrix(...)` 后的 `A.sol<caret>` 回归输入。

本轮 fresh 验证：

- `:core:sage-api:test -PrunSageApiTests=true`：通过，8 tests。
- `:plugins:sage-core:compileKotlin -Psage.ide.localSdk=D:/JetBrains/PyCharm`：通过。
- `:plugins:sage-core:processResources -Psage.ide.localSdk=D:/JetBrains/PyCharm`：通过，并确认 `build/resources/main/sage-api-index.json` 已打包。
- `git diff --check`：通过；仅有 Git 的 LF/CRLF warning。

新阻塞（已记录，不能伪装成测试通过）：

- `:plugins:sage-core:compileTestKotlin` 尚未进入 Kotlin test source 编译，IntelliJ Platform Gradle Plugin 在解析本地 PyCharm module descriptor 时失败：`ModuleDescriptor ... unknown field module/namespace`。这是本地平台依赖元数据解析错误，不是当前 Kotlin 源码编译错误；需要后续用既有 plugin test 运行方式或修复/绕过该工具链版本不兼容后再执行。
- 新增 `core/sage-api/src/main/kotlin/com/starnotesxj/sagemath/sageapi/SageApiIndexLoader.kt`：统一执行 validated JSON/path/resource 加载；插件 service 失败时保持旧 index 并回退 bundled。loader 回归测试覆盖无效外部路径回退资源。
- `SageApiIndexQuery` 现在按子类→父类 rank 解析成员，子类同名成员覆盖父类；未知带点类型名不再按 simple name 猜测。
- JSON reader 严格拒绝重复 object key、非整数 schemaVersion 和错误 boolean 字段；对应 core 回归测试已加入。
- 本轮 fresh 验证：`:core:sage-api:test -PrunSageApiTests=true` exit code `0`；`:plugins:sage-core:processResources :plugins:sage-core:compileKotlin -Psage.ide.localSdk=D:/JetBrains/PyCharm` exit code `0`。
- 新增 `tools/sage-api-index/generate.py`：Python 标准库 AST `.pyi`/`.py` extractor，输出 schemaVersion=1 index、SHA-256 sourceDigests、签名/文档/父类/别名、coverage/diagnostics/diff。
- 新增 `tools/sage-api-index/test_generate.py`，4 项测试覆盖高价值域 symbol、coverage missing/ratio、Dynamic conflict、added/removed/changed diff 和空源目录负例；`python -m py_compile ...` 与测试通过。
- 新增 `core/sage-api/.../SageApiIndexGenerator.kt`，统一现有 Kotlin stub extractor + normalizer 入口；core 现有 19 项测试通过。
- 生成器 fixture 覆盖 matrix/vector/polynomial/finite-field/number-theory 高价值入口，其中 `Matrix.solve_right` 作为普通 METHOD 数据被提取，不含方法名特例。
- Sage Core Kotlin 编译继续通过；真实 Runtime/stubgen 输入尚未接入，当前生成器 artifact 仍是 fixture 验证，不得宣称全量覆盖。
- 生成器已修复 canonical function 的 re-export alias 归并：`sage.all.matrix`/`sage.all.GF` 可命中真实函数条目，而不是只留下无签名 ALIAS；coverage 同样按 alias 解析。
- fixture 已拆分覆盖 matrix、vector、polynomial、finite field、number theory、crypto，当前生成 8 个源文件、45 个 entries；高价值 manifest 16 项，alias-aware coverage 15/16（0.9375），唯一 missing 是刻意保留的 `sage.all.missing`。
- 生成器新增严格 index contract validation：schemaVersion、版本/生成器元数据、SHA-256、entry kind/dynamicity/confidence、signature/type/source 字段和重复 entry；Python 负例测试现为 5 项。
- `plugins/sage-core/src/main/resources/sage-api-index.json` 已由 validated generated artifact 替换原最小矩阵 slice；`core:sage-api` test resource 同步用于 Kotlin reader regression。
- source manifest 已提交：`tools/sage-api-index/source-manifest.json` 用相对 root 复现 fixture 输入；每条 entry 保留 source kind/locator/digest。
- generator gate 已提交实现：默认 missing/conflict 返回 exit code `3`，`--allow-missing`/`--allow-conflicts` 显式放行；gate 失败仍写出 index、coverage 和 diff 供 CI 审计。
- Python generator 当前 10 项测试通过；fixture/manifest 生成在显式 `--allow-missing` 下输出 8 sources、45 entries、coverage `0.9375`。
- 新增最小 coverage gate 回归：`--min-coverage` 低于阈值返回 exit code `3`，且仍保留 index/coverage。
- 本轮构建命令首次失败于环境准备：Gradle 指向的 ASCII `G:\sage-build\temp` 尚不存在，故 core/plugin 两条 Gradle 命令均未进入编译；这是本轮新 blocker，需创建目录后重跑，不是源码失败。
- 创建 ASCII temp 后，`:core:sage-api:test -PrunSageApiTests=true` fresh exit code `0`；plugin 重试命令因 PowerShell 未将 `-Psage.ide.localSdk=D:/JetBrains/PyCharm` 作为单个参数传给 Gradle，Gradle 将其误解析为 task/project。需以引号包裹该 `-P` 参数后重跑；这是命令调用错误，不是源码失败。
- 使用引号修正参数后，`:plugins:sage-core:processResources :plugins:sage-core:compileKotlin "-Psage.ide.localSdk=D:/JetBrains/PyCharm"` fresh exit code `0`，bundled resource 已重新处理。
- `:plugins:sage-core:compileTestKotlin "-Psage.ide.localSdk=D:/JetBrains/PyCharm"` 已真实重试但仍在 Kotlin test source 编译前被 IntelliJ Platform Gradle Plugin 阻塞：`ModuleDescriptor ... unknown field module/namespace`；这是已知平台 descriptor 兼容性 blocker。
## 本轮增量：Sage Core 测试阻塞与 indexed completion 已解除（2026-08-22）

### 实现与根因

- 删除无效的 SageFile.getLanguage() override；PyCharm 2026.2 的 PyFileImpl.getLanguage() 为 final。保留 plugin.xml 的 language="Sage" 注册，测试改为验证 Sage 是 Python 方言。
- SagePluginTestBase 固定仓库 testData 根目录；parser/analyzer/type 回归已修复，并加入测试专用 sage/matrix/matrix.pyi fixture。
- SageTypeProvider 与 SageApiIndexQuery 保持通用 factory return、simple callable lookup 和 owner/parent member closure，不增加 solve_right 等函数名特例。
- 新增 SageCompletionTest：使用 A = matrix([[1]]) 与 A.sol<caret>ve 验证普通 indexed METHOD solve_right 出现在实际 basic completion。
- 根因是 SageImplicitCompletionContributor 只匹配 PyReferenceExpression 父节点，并在 qualified reference 路径提前返回；completion caret 处于 partial token 时 contributor 未被调用。修复为覆盖 Python caret、处理 caret/前一可见 leaf 的 reference，并调用现有 SageApiClassMembersProvider 生成 indexed members。

### Fresh 验证（真实 exit code）

- :plugins:sage-core:compileTestKotlin "-Psage.ide.localSdk=D:/JetBrains/PyCharm" --no-daemon --console=plain：exit code 0。
- :plugins:sage-core:test "-Psage.ide.localSdk=D:/JetBrains/PyCharm" "-PrunSageCoreTests=true" --no-daemon --console=plain：exit code 0，21 tests completed，0 failures。
- :plugins:sage-core:test --tests com.starnotesxj.sageide.completion.SageCompletionTest "-Psage.ide.localSdk=D:/JetBrains/PyCharm" "-PrunSageCoreTests=true" --no-daemon --console=plain：exit code 0。
- :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain：exit code 0。
- git diff --check：exit code 0；仅有 Git LF/CRLF warning，无 whitespace error。

### 交接提示词（必须原样遵守）

继续任务时必须执行实现闭环：先写最小实现或回归测试，再立即运行定向验证；不准只读不写，不准连续反复读取已经确认的文件，不准用无休止探索替代代码修改和测试。每次出现新错误，先把具体错误和命令 exit code 写入 HANDOFF.md，然后只读取错误指向的最小源码范围并修复。任何完成声明都必须附真实命令输出、exit code 和未验证项；不得把 fixture 结果冒充真实 Sage runtime 全量覆盖。后续每个阶段都必须保持“写实现 → 定向验证 → 更新交接文档”的连续节奏。

下一阶段优先推进真实 Sage runtime/stubgen 产物接入和 product fresh build；若遇到问题，立即写代码或测试，不得重新进入只读循环。

## 本轮增量：交接文档与下一任务已同步（2026-08-22）

- 审核旧接手提示词：稳定约束、读取边界、真实 exit code、禁止硬编码特例和完成后停止规则仍然有效。
- 强化 `HANDOFF-PROMPT.zh-CN.md`：明确已有实现先定向测试、禁止只读不写、禁止反复读取已确认文件、停止前必须更新 HANDOFF。
- 将 `NEXT-TASK.zh-CN.md` 从已完成的 completion 回归切片切换为下一限定切片：验证 API generator、validated loader、bundled index 的 drift/contract；不得自动开始真实 runtime、product 或 installer 阶段。
- 本轮只更新交接文档，没有新增代码行为；下一轮必须先写 generator/bundled contract 回归测试，再按任务范围实现和验证。
- 文档写入后必须运行 `git diff --check`，并记录真实 exit code。
- 本轮新错误记录：首次限定文件读取调用将 `read.limit` 误设为 2200，工具参数校验拒绝（工具级 exit code：N/A，未执行命令）；已改为最大 2000 后继续。
- 本轮新错误记录：第二次限定读取误将 `generate.py` 起始 offset 设为 700，工具参数校验拒绝（工具级 exit code：N/A，未执行命令）；已改为文件实际 465 行范围后继续。

## 架构结论：SageMath 应作为 Python 超集体验、Python 兼容层实现（2026-08-22）

- 产品体验层面，SageMath 应明确定位为 Python 的超集：所有普通 Python 代码保持可用，同时增加 preparser 运算符、generator sugar、Sage API 类型和 runtime 注入命名空间。这样用户得到的是“Python + Sage 能力”，而不是需要学习另一套基础语言。
- IntelliJ 实现层面不建议现在切换为完全独立的 Superset Language。IntelliJ 没有一个能自动继承 Python 全部 IDE 服务的“superset”开关；独立语言会让 Python PSI、completion、inspection、refactoring、formatter、debugger、注入和 Pythonid 扩展逐项重新接线，工程量和回归风险显著增加，短期体验反而更差。
- 当前混合方案是正确方向：SageFileType 继承 PythonFileType，SageParserDefinition/Sage PSI 复用 Python 服务，同时用 Sage parser/lexer 和 API/member provider 增加 Sage 语义。后续文档可称“Python 超集”，代码保持 Python base-language/dialect 兼容；除非先完成独立语言迁移设计与全套回归，不要拆掉兼容层。

## 本轮增量：API generator / validated loader / bundled index 契约（2026-08-22）

### 实现

- 在 tools/sage-api-index/test_generate.py 新增 bundled drift/contract 回归：从 tools/sage-api-index/source-manifest.json 重新生成 index，并要求与插件实际加载的 plugins/sage-core/src/main/resources/sage-api-index.json 字节语义一致。
- 回归固定 schemaVersion、当前 Sage/Python 版本、generatorVersion/sourceDigests、coverage（15/16、0.9375、唯一刻意 missing）、普通 METHOD sage.matrix.matrix.Matrix.solve_right、matrix factory return type、source digest/locator 和 documentation 元数据。
- 回归直接调用既有 validated generator contract，确认 bundled artifact 可被校验，并拒绝 duplicate entry 与未知 symbol kind；没有增加 solve_right、matrix 或其他单函数特例。

### Fresh 验证（真实 exit code）

- python -m unittest tools/sage-api-index/test_generate.py：exit code 0，11 tests completed，0 failures。
- ./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain：exit code 0，BUILD SUCCESSFUL；6 actionable tasks 均 up-to-date。
- git diff --check：exit code 0；仅有既有 LF/CRLF warning，无 whitespace error。
- 读取工具参数错误已记录：read.limit=2200 和超出实际行数的 offset=700 均被工具校验拒绝，未执行命令，无 shell exit code。

### 未完成与剩余风险

- 该测试锁定的是当前 fixture/source manifest 与 checked-in bundled artifact 的一致性，不是实际 Sage runtime/stubgen 全量覆盖；真实 Runtime 输入、product fresh build、installer、smoke、release audit、FinalCheck 均未在本轮运行。
- HANDOFF-PROMPT.zh-CN.md 与现有未提交工作区改动均保留，未提交 Git；下一轮不得将 fixture contract 结果描述成真实 Sage runtime 全量完成。
- 本轮新错误记录：首次写入下一任务文档的 run_code 字符串因反斜杠转义导致工具解析失败（工具级 exit code：N/A，未执行命令）；已改用逐行字符串构造后继续。
- 本轮新错误记录：更新 NEXT-TASK.zh-CN.md 后立即运行 `git diff --check`，真实 exit code `1`，报告 `NEXT-TASK.zh-CN.md:116: new blank line at EOF`；已记录，下一步仅修复该文档末尾空行。
- 任务文档已修复末尾空行；重新运行 `git diff --check`，真实 exit code `0`（仅既有 LF/CRLF warning）。
- 本轮新错误记录：新增 manifest contract 测试首次运行 `python -m unittest tools/sage-api-index/test_generate.py`，真实 exit code `1`；两个新测试被既有 CLI 强制要求 `--sage-version/--python-version` 阻止，非源码解析错误。已记录后读取最小测试范围修复调用参数。
- 本轮新错误记录：修正测试版本参数后再次运行同一命令，真实 exit code `1`；现有 generator 只接受数组 manifest、且没有 `--source-base`，导致新对象 manifest 测试分别报 `source manifest must be a nonempty JSON array` 与 `unrecognized arguments: --source-base`。已记录后读取最小 generator CLI/manifest 处理范围。
- 本轮新错误记录：首次批量修改 generator 时，`edit` 找不到精确 normalize 函数片段，工具操作未写入（工具级 exit code：N/A，未执行命令）；已改为基于已读取的精确行片段分步修改。
- 本轮新错误记录：更新对象 source-manifest 后运行 `python -m unittest tools/sage-api-index/test_generate.py`，真实 exit code `1`；新 contract 测试暴露三处预期失败：生成 index 尚无顶层 sources 元数据、checked-in bundled drift 测试不应比较新增 manifest metadata、缺失路径错误文案为 `source manifest root does not exist` 而测试写成 `source root does not exist`。已记录后仅修复这些最小契约范围。
- 本轮新错误记录：补齐顶层 sources 后运行同一测试，真实 exit code `1`；normalize 将 sourceSpecs 字典按对象属性访问，报 `AttributeError: dict has no attribute kind`，同时缺失路径断言仍需匹配完整错误文案。已记录后读取错误行并修复。
- 本轮新错误记录：修正字典访问后运行同一测试，真实 exit code `1`；source files 聚合条件使用原始 `FIXTURE` 与归一化 `STUB` 不一致，checked-in bundled drift 预期也需明确排除新 metadata；缺失路径断言仍使用过短文案。已记录后继续最小修复。
- 本轮新错误记录：统一内部 source kind 为 `STUB` 后运行同一测试，真实 exit code `1`；测试仍要求顶层 sources kind 为 `FIXTURE`，说明输出 contract 需保留 manifest 原始 kind，不应只用内部 extractor kind。已记录后调整 metadata 输出而不改变解析语义。

## 本轮增量：artifact manifest/provenance 输入边界（2026-08-22）

### 实现

- `tools/sage-api-index/source-manifest.json` 从旧数组升级为显式对象 schema：`artifactId`、Sage/Python 版本、`provenance`、`sources`；当前唯一输入明确标记为 `FIXTURE`，没有伪称真实 Sage runtime。
- `tools/sage-api-index/generate.py` 新增对象 manifest 严格校验：缺少 identity/version/provenance/sources、source root 不存在或输入为空时失败；保留旧数组 manifest 和 `--source-root` 兼容。
- 新增 `--source-base`，支持 manifest root 相对独立 base 解析；对象 manifest 的 artifact/provenance/source metadata 写入生成 index，source digest 与 entry locator 保持一致。
- `tools/sage-api-index/test_generate.py` 新增 manifest contract 回归，覆盖缺失 artifact 路径、provenance/source metadata、普通 METHOD、KNOWN factory return type、source digest、版本和既有 bundled entry drift；没有增加单函数特例。

### Fresh 验证（真实 exit code）

- `python -m unittest tools/sage-api-index/test_generate.py`：exit code `0`，13 tests completed，0 failures。
- `python -m py_compile tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`：exit code `0`。
- `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`：exit code `0`，BUILD SUCCESSFUL；6 actionable tasks up-to-date。
- `git diff --check`：exit code `0`；仅有既有 LF/CRLF warning，无 whitespace error。

### 未完成与剩余风险

- 当前 manifest 仍然是 checked-in fixture provenance，不是真实 Sage runtime/stubgen artifact；未发现可确认的真实 Sage `.pyi` 输入，因此本轮没有伪造真实导入结果。
- 本轮未修改 bundled JSON、插件源码、product、installer、release 或官方 checkout；未执行 product fresh build、installer smoke、release audit 或 FinalCheck。
- 本轮新增错误和真实 exit code 均已在前置增量中记录；最终工作区保持未提交状态。
