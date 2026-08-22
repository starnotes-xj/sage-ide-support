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
