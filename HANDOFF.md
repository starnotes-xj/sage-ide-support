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

- 这不是全量 Sage API intelligence：尚未实现真实 Sage Runtime / `sage-pycharm-stubgen` / signature / documentation 批量 extractor、增量构建、版本 diff、完整 coverage report、IDE service/resolver、类型传播、completion/signature/documentation 消费和 source-map golden tests。
- 当前 JSON writer 只负责稳定输出，不提供 JSON parser/loader；schema 资源尚未接入 runtime 校验。
- extractor 是刻意有限的 `.pyi` 语法切片，不应被描述为 Sage 全量覆盖；动态/Cython API 仍返回 Unknown/Dynamic。
- 本轮没有运行 Sage Core plugin、Community product、installer、smoke、release audit 或 FinalCheck；既有交接中的产品证据未被本轮重用为 fresh build 证据。
- 未修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr` 或官方 `G:\Projects\intellij-community-sage-ide`；本轮仅修改产品仓库。

### 下一位代理

从 `core/sage-api/src/main/kotlin/com/starnotesxj/sagemath/sageapi/SageApiIndexModels.kt` 和 `SageApiNormalizer.kt` 继续：优先加入真正的 schema loader/validator 与 Python stdlib AST extractor（建议放到 `tools/sage-api-index/`），再接入 `plugins/sage-core` 的 immutable index service；不要把 extractor 逻辑扩展成 Kotlin 函数特例。
## 交接规则

- 不修改官方 checkout、`sage-ide-support` 或 `sage-pr`。
- 不手工编辑 installer、SPDX 或 distribution 产物来伪造验证结果。
- 新构建必须使用 JDK 25、ASCII `G:\sage-build` 环境路径，并记录真实 exit code。
- 后续 Git 提交使用中文 Lore 格式，并包含 `约束：`、`拒绝：`、`置信度：`、`影响范围：`、`后续指引：`、`已验证：`、`未验证：`。
