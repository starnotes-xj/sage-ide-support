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
- 本轮新错误记录：新增 tree digest/provenance 回归后运行 `python -m unittest tools/sage-api-index/test_generate.py`，真实 exit code `1`；generator 尚未输出 `treeDigest/fileCount`，且 provenance 尚未 fail-closed 校验，导致 3 failures、2 errors。已记录后只读取并修复对应 manifest normalize 范围。
- 本轮新错误记录：补充 tree metadata 输出后再次运行同一命令，真实 exit code `1`；生成 index 的 sources 仍缺少 treeDigest，且旧缺失路径测试的 provenance 缺少 source 字段，先触发 provenance 校验。已记录后读取最小 metadata 构造和测试 fixture 范围修复。

## 本轮增量：source tree digest 与 provenance fail-closed 契约（2026-08-22）

### 实现

- `tools/sage-api-index/generate.py` 新增确定性 tree digest：按相对路径排序，纳入 `.pyi/.py` 文件内容 SHA-256，输出 `treeDigest`、`fileCount`、`files`。
- manifest 声明 `treeDigest` 时严格校验内容和文件集合漂移；未声明时仍兼容，并在生成 index 中输出实际 digest。
- provenance.kind 限制为 `FIXTURE`、`RUNTIME`、`STUBGEN`，且 `generator`、`source` 必须为非空字符串；不允许静默降级输入来源。
- `tools/sage-api-index/test_generate.py` 新增稳定 digest、正确声明、内容漂移、文件集合漂移和非法 provenance 回归；仍未增加单函数特例。

### Fresh 验证（真实 exit code）

- `python -m unittest tools/sage-api-index/test_generate.py`：exit code `0`，16 tests completed，0 failures。
- `python -m py_compile tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`：exit code `0`。
- `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`：exit code `0`，BUILD SUCCESSFUL；6 actionable tasks up-to-date。
- `git diff --check`：exit code `0`；仅有既有 LF/CRLF warning。

### 未完成与剩余风险

- 当前 checked-in manifest 仍是 `FIXTURE`，不是真实 Sage runtime/stubgen artifact；本轮未伪造真实 runtime 证据。
- 本轮未修改 bundled JSON、插件源码、product、installer、release 或官方 checkout；未执行 product fresh build、installer smoke、release audit 或 FinalCheck。
- 该 tree digest/provenance 切片已提交：`7dc74b7 锁定 Sage artifact 的内容完整性`。
- 本轮新错误记录：新增 source metadata 一致性回归首次运行 `python -m unittest tools/sage-api-index/test_generate.py`，真实 exit code `1`；测试插入点位于 `ManifestContractTest` 类，新增方法多缩进一级，触发 `IndentationError: unexpected indent`。已记录后只修复测试缩进。
- 本轮新错误记录：修复测试缩进后运行同一命令，真实 exit code `1`；19 tests 中 2 failures：locator drift 与 missing entry source 均未被 generator 拒绝，说明 manifest/index consistency validator 尚未实现；已记录后读取对应测试与 build 范围。
- 本轮新错误记录：调整 locator drift 测试后再次运行同一命令，真实 exit code `1`；locator 修改会同步改变生成 locator，当前测试不能证明外部 drift；missing entry source 仍因复用非空 root 被重新提取而未触发。已记录后仅修正测试为直接 validator contract 与空 source root。
- 本轮新错误记录：修正 locator digest 后运行同一命令，真实 exit code `1`；locator drift 仍未触发预期文案，empty root 则在 manifest parse 阶段以 `source manifest root does not exist` 失败而非 consistency validator 文案。已记录后调整测试断言为 fail-closed 的实际边界，并继续收敛 validator。

## 本轮增量：manifest 与生成 index source metadata 一致性契约（2026-08-22）

### 实现

- `tools/sage-api-index/generate.py` 新增 `validate_source_contract`，双向校验 object manifest source 与生成 index 的 kind、locator、treeDigest、fileCount、files、entry sources 和 sourceDigests。
- source metadata 直接来自实际扫描结果，不再从归一化后 entries 反推文件清单；即使文件没有可提取 symbol，也不会从 `files` 中静默消失。
- object manifest source locator 必须唯一；空 source、未知 locator、source kind 不一致、文件 metadata 漂移和 sourceDigests 漂移均 fail-closed。
- 保持旧数组 manifest、`--source-root` 和无声明 digest 路径兼容；没有增加函数名特例。
- `tools/sage-api-index/test_generate.py` 增至 21 tests，覆盖 locator、空 source、metadata 漂移、重复 locator、多 source 顺序与旧兼容路径。

### Fresh 验证（真实 exit code）

- `python -m unittest tools/sage-api-index/test_generate.py`：exit code `0`，21 tests completed，0 failures。
- `python -m py_compile tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`：exit code `0`。
- `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`：exit code `0`，BUILD SUCCESSFUL；6 actionable tasks up-to-date。
- `git diff --check`：exit code `0`；仅有 LF/CRLF warning。

### 边界与风险

- 当前 contract 只由 checked-in `FIXTURE` 与合成临时 sources 验证，不代表真实 Sage runtime/stubgen artifact 已接入。
- 本轮未修改 source fixture、bundled resource、插件源码、product、installer、release 或官方 checkout。
- 本轮未执行 product fresh build、installer smoke、release audit 或 FinalCheck；限定切片尚未提交。
- 本轮新错误记录：补充未知 entry source locator 回归后运行 `python -m unittest tools/sage-api-index/test_generate.py`，真实 exit code `1`；21 tests 中 1 failure，`validate_source_contract` 未拒绝不属于任何 manifest source 的 entry locator。已记录后只补齐该双向覆盖校验。
- 本轮新错误记录：补充 manifest locator 前缀内的 phantom file 回归后运行同一命令，真实 exit code `1`；21 tests 中 1 failure，validator 仅校验 locator 前缀，尚未确认 entry source 文件属于实际扫描的 files。已记录后只补齐 file membership 校验。
- 补齐 unknown/phantom entry source 双向校验并增加 multi-source byte-stable 回归后，最终 Python 仍为 21 tests 全通过；验证证据以本节命令为准。
- 新阶段 WSL 探测首条命令 `wsl bash -lc ...` 真实 exit code `1`：Windows 选中了默认 `docker-desktop` distro，`/bin/sh: bash: not found`；`wsl -l -q` 同时确认存在 `Ubuntu`。已记录后改为显式 `wsl -d Ubuntu -- bash -lc ...`，不是 Sage 环境失败。
- 显式 Ubuntu 后首次执行 `/home/starnotes/miniconda3/bin/conda run -n SageMath ...` 真实 exit code `1`：`EnvironmentLocationNotFound: /home/starnotes/miniconda3/envs/SageMath`。已确认用户 shell 是 zsh 且 Conda 安装于 `~/miniconda3`；下一步读取 `conda env list` 确认环境的实际名称/路径，不将其误报为 Sage 缺失。
- importer 首轮红测 `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py` 真实 exit code `1`：`ModuleNotFoundError: import_wsl_artifact`，符合先测试后实现预期。已确认真实环境为 Conda env `sage`、Sage 10.9、Python 3.13.15、stubgen 0.8.3，下一步实现该模块。
- importer 初版写入后运行同一命令真实 exit code `1`：`import_wsl_artifact.py:140 SyntaxError: unterminated string literal`，原因是生成文件时 `"\n"` 被外层字符串展开成真实换行。已记录后仅修复 `write_json` 的换行转义。
- 首次真实导入命令 `python tools/sage-api-index/import_wsl_artifact.py --distro Ubuntu ... --output-dir build/sage-api-real` 真实 exit code `1`：WSL probe 的 stderr 在 Windows 默认 GBK 解码线程触发 `UnicodeDecodeError`，随后 importer 以 `stub file count 2839 does not match generated 2837` fail-closed。真实 report 为 generated=discovered=2837、failed=0；stubgen 源码显示其另行生成聚合 stubs。已记录后先补充回归，再最小修正 subprocess 解码与聚合文件计数契约。
- 新增上述两项回归后运行 `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py` 真实 exit code `1`：7 tests 中 2 errors，分别为 probe subprocess 未声明 UTF-8 encoding，以及 validator 仍拒绝 generated 之外的聚合 stubs。红测准确锁定真实失败，下一步只修复这两个通用边界。
- 修复后第二次真实导入仍真实 exit code `1`：importer 向现有 generator 传入不存在的 `--diagnostics-output`，argparse 以 exit code `2` 拒绝。生成器只在 stdout summary 提供 diagnostics，没有独立 diagnostics CLI 文件；已记录后先把测试改成锁定真实 CLI，再移除该虚构参数/输出。
- 移除虚构参数后第三次真实导入真实 exit code `1`：generator 以内部 exit code `2` 拒绝 importer 声明的 tree digest，expected `1e68411f...`、actual `69d0524a...`。说明 importer 重复实现的 tree digest 算法与现有 generator contract 不一致；已记录后仅复用/对齐既有通用 digest 实现。
- 对齐跨平台相对路径排序后第四次真实导入真实 exit code `1`：generator 在真实 `.pyi` 的 class-level `AnnAssign` 上调用 `ast.get_docstring`，Python 3.14 抛出 `TypeError: 'AnnAssign' can't have docstrings`。这是 fixture 未覆盖的通用 AST 节点缺口；已记录后先加回归测试，再限定 `doc()` 只处理可拥有 docstring 的节点。
- 增加 receipt diagnostics 摘要后 importer 单测真实 exit code `1`：mock generator 未创建 `coverage.json`，导致 `FileNotFoundError`。这是测试替身不完整而非生产路径失败；已记录后仅让 mock side effect 写出最小真实 coverage shape。
- 追加 output_root/sage_package/Python/stubgen/schema/receipt/编码回归后运行 `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py` 真实 exit code `1`：12 tests 中 3 failures、8 errors；新测试先于实现锁定 report/runtime binding、malformed probe、generator UTF-8 与 receipt 双向契约缺口。已记录后继续最小修正 importer 与测试夹具。
- fail-closed importer 修复后的真实重建命令再次运行至工具墙超时：命令 `python tools/sage-api-index/import_wsl_artifact.py --distro Ubuntu --conda /home/starnotes/miniconda3/bin/conda --conda-env sage --source-root "\\wsl.localhost\Ubuntu\home\starnotes\sage_typings_083" --generation-report "\\wsl.localhost\Ubuntu\home\starnotes\sage_typings_083\generation-report.json" --output-dir build/sage-api-real`，错误为 `wall-clock ceiling reached (600000ms)`，harness 未报告可用 process exit code。已记录后仅检查进程/输出状态，不把该次超时误报为成功。
- 更新 README 基线/聚合 stub 文案后运行 `git diff --check` 真实 exit code `1`：`README.zh-CN.md:11` 的 `FIXTURE` 行有 trailing whitespace；已记录后仅删除该空格。
- 本轮 probe checkpoint 红测后运行 `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py` 真实 exit code `1`：新增 4 个测试错误、总计 16 tests；`make_probe_envelope`/probe-only parser/timeout API 尚未实现，且 argparse 在 probe-only 模式仍要求 source-root/generation-report。已记录后实现最小 LIVE checkpoint/replay 与有界 probe，不绕过 runtime probe。
- 接入 probe timeout/receipt 字段后复跑 `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py` 真实 exit code `1`：16 tests 中 3 errors；旧 Namespace 夹具没有 `probe_timeout`/`generator_timeout` 属性，run_import 直接访问属性导致 AttributeError。已记录后改用兼容默认值，再继续回归。
- 新增 generator timeout receipt 红测后运行 `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py` 真实 exit code `1`：18 tests 中 1 error；TimeoutExpired 在 generator receipt 写入前直接抛出，产物 receipt 缺少 timeout 状态。已记录后改为先写入 `status=running`，超时更新并持久化 `status=timeout`、returncode=null，再返回稳定 exit 2。
- generator timeout receipt、LIVE/REPLAY probe envelope 与 parser 约束实现后，验证 `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py tools/sage-api-index/test_generate.py` 真实 exit code `0`（41 tests），`python -m py_compile tools/sage-api-index/import_wsl_artifact.py tools/sage-api-index/test_import_wsl_artifact.py tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py` 真实 exit code `0`，`:core:sage-api:test -PrunSageApiTests=true` 真实 exit code `0`（BUILD SUCCESSFUL），`git diff --check` 真实 exit code `0`。本轮尚未执行 fresh WSL probe-only/full replay；不得将 ignored 旧产物当作新证据。
- fresh probe-only 已执行：`python tools/sage-api-index/import_wsl_artifact.py --distro Ubuntu --conda /home/starnotes/miniconda3/bin/conda --conda-env sage --probe-only --probe-json build/sage-api-real/probe-live.json --probe-timeout 20` 真实 exit code `0`；stdout envelope 为 schema=1/mode=LIVE，Sage=10.9、Python=3.13.15、stubgen=0.8.3、license=GPL-3.0-only，probeDigest=44945e3f7571bcbc1a558b3af389a3e80cb472f39893373b5d913ad16e56bc9c。该 checkpoint 是 fresh live probe 证据，不代表 generator/full replay 或 release 完成。
- fresh replay full import 已执行：`python tools/sage-api-index/import_wsl_artifact.py --distro Ubuntu --conda /home/starnotes/miniconda3/bin/conda --conda-env sage --source-root "\\wsl.localhost\Ubuntu\home\starnotes\sage_typings_083" --generation-report "\\wsl.localhost\Ubuntu\home\starnotes\sage_typings_083\generation-report.json" --output-dir build/sage-api-real-replay --probe-json build/sage-api-real/probe-live.json --allow-probe-replay --probe-timeout 20 --generator-timeout 300` 真实 exit code `0`；stdout 报告 artifact=wsl-ubuntu-sage-10.9-stubgen-0.8.3、probeMode=REPLAY、probeDigest=44945e3f...、stubFileCount=2839、treeDigest=69d0524a...。fresh receipt 记录 generator status=completed、returncode=0、timeoutSeconds=300、entries=84159、diagnostics=24、conflicts=5、missing=0，并写出 index/coverage/raw/manifest/receipt 五个 ignored 输出；coverage expected=[]，所以 coverage=1.0 不是高价值覆盖证明。
- 提交尝试失败：执行本轮中文 Lore `git add HANDOFF.md NEXT-TASK.zh-CN.md tools/sage-api-index/README.zh-CN.md tools/sage-api-index/import_wsl_artifact.py tools/sage-api-index/test_import_wsl_artifact.py && git commit ...` 真实 exit code `1`，stdout/stderr 均为空；已记录后检查暂存区与 git 状态，再用等价的可审计提交命令重试。
- 第二次提交尝试失败：在 PowerShell 中使用 Bash heredoc `git commit -F - <<'EOF' ...`，shell parser 报 `Missing file specification after redirection operator`，真实 exit code `1`；未执行 git commit。已记录后改用显式提交消息文件/`git commit -F`，不改变已暂存内容。
