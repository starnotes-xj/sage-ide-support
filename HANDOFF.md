# SageMath CTF IDE 交接文档

> 本文是新仓库 `G:\Projects\sage-math-ctf-ide` 的持续交接记录。
>
> 所有后续 Git 提交信息必须使用中文，并遵循仓库的 Lore 提交结构：第一行说明意图，正文说明背景，之后使用中文的 `约束：`、`拒绝：`、`置信度：`、`影响范围：`、`后续指引：`、`已验证：`、`未验证：` 等字段。

## 1. 项目目标

开发一个完整的、可独立发行的 **SageMath CTF IDE**：

- 基于 IntelliJ Platform/IntelliJ Community 产品构建；
- 面向 SageMath 的专业科学计算工作流；
- 对 CTF 密码学、数论、编码、逆向和取证工作流做一等公民优化；
- 不只是把现有 PyCharm 插件继续做大；
- 提供类似 IDEA 管理 JDK、PyCharm 管理 Python SDK 的 **SageMath Runtime Manager**。

目标用户必须能够在 IDE 中：

1. 创建 SageMath/CTF 工程；
2. 选择或下载 SageMath Runtime；
3. 校验、安装、切换和验证 SageMath Runtime；
4. 打开 `.sage` 文件并获得语法、类型、补全和 CTF 辅助；
5. 运行耗时超过 30 秒的真实题目，而不会被错误的固定超时杀掉；
6. 使用显式取消、输出上限和可选有限 deadline 保持控制；
7. 得到完整 IDE 产品，而不是插件 ZIP 加 PyCharm 安装目录。

## 2. 仓库边界

| 目录 | 身份 | 规则 |
|---|---|---|
| `G:\Projects\sage-ide-support` | 现有 PyCharm 插件仓库 | 保持独立，不改成产品仓库 |
| `G:\Projects\sage-math-ctf-ide` | 新产品仓库 | 产品计划、Runtime、CTF、overlay 和发行主线 |
| `G:\Projects\intellij-community-sage-pr` | SageMath 修改版 PR/研究 checkout | 仅作 API/PR 参考，不作为产品基线 |
| `G:\Projects\intellij-community-sage-ide` | 官方 JetBrains Community checkout | 已恢复并验证 clean，固定 SHA `b0001cd6c53979b384def7a1e3febe061e2ef687`；只作为 staging/worktree 的上游底座 |

当前 `intellij-community-sage-pr` 不是官方干净 master：它包含 Sage 专用提交，不能直接用于产品 release 或 CI。官方 `intellij-community-sage-ide` 已恢复到 `b0001cd6c53979b384def7a1e3febe061e2ef687`，Git 状态已验证为空；Sage 产品修改只允许进入临时 staging/worktree。

## 3. 当前 Git 状态

新产品仓库的首个提交已经改为中文：

```text
8ec38c6 建立独立 SageMath CTF IDE 产品主线
```

不要在 `sage-math-ctf-ide` 中添加英文提交信息。提交前执行：

```powershell
git status --short --branch
git diff --check
git diff --cached --check
```

本轮构建验证使用临时 `G:\sage-build\staging-build6` worktree。官方 checkout
`G:\Projects\intellij-community-sage-ide` 仍固定在
`b0001cd6c53979b384def7a1e3febe061e2ef687`，当前 `git status --porcelain` 为空；
产品改动没有写入官方 checkout。`staging-build2`、`staging-build3` 和
`staging-build5` 等遗留 staging 目录已经清理。

## 4. 已完成的产品基线

- `plugins/sage-core/`：从现有插件迁移的 Sage 语言/运行能力基线；
- `core/model/`：平台无关的执行目标、CTF Profile、结构化执行结果；
- `docs/IDE-PLAN.zh-CN.md`：完整产品计划；
- `docs/MIGRATION-MAP.zh-CN.md`：插件到产品迁移地图；
- `docs/STATUS.zh-CN.md`：推进状态和已知风险；
- `product/README.zh-CN.md`：Community product overlay 接入约定；
- `.github/workflows/build.yml`：核心编译和插件构建 CI；
- `config/ctf-default-profile.json`：默认 CTF 配置；
- `core/runtime/`：SageMath Runtime 管理基础模块（HTTPS 下载、强制 manifest、完整 sidecar codec、文件级定位校验、ZIP 安全安装、immutable versions/current 指针和定位）。

## 5. SageMath Runtime 产品决策

### 5.1 Runtime 不再只是“用户自行安装的外部命令”

完整 IDE 应提供 Runtime Manager：

- 远程 Catalog 展示版本、平台、架构、大小、SHA-256、许可证；
- 下载到 staging；
- 流式 SHA-256 校验；
- manifest 文件级校验；
- Zip Slip/绝对路径/重复条目/超大归档防护；
- 原子发布和 current 指针；
- `sage --version` 与最小表达式验证；
- Settings/Project SDK 页面选择和切换；
- 离线缓存和失败回滚。

首版实现可以先支持：

- 官方静态 HTTPS Catalog；
- Native 本机 ZIP Runtime；
- Windows/Linux/macOS 的基础平台匹配。

随后再接入：

- WSL Runtime；
- Docker/Podman 镜像 digest；
- SSH/HPC 远程 Runtime；
- 可选 Runtime bundle 和签名 Catalog。

不要把 Docker 镜像简单伪装成 ZIP，也不要让远程 Runtime 复用本机路径假设。

### 5.2 超时策略

`core:model` 的 CTF Profile 已改为：

```kotlin
val timeoutMillis: Long? = null
```

语义：

- `null`：无限制，不创建自动 watchdog/deadline；
- 正数：显式启用毫秒级 deadline；
- `0` 或负数：非法；
- 无限制不等于无法停止，用户取消和进程树清理必须始终可用；
- 输出上限仍然默认启用，防止无限输出吞噬 IDE。

现实依据：`C:\Users\星记\Downloads\test.sage` 在本机运行需要约 63 秒，固定 30 秒默认值不适合 Sage/CTF 工作负载。

### 5.3 Runtime 安装安全边界

实现必须保持：

- HTTPS artifact；
- 严格 64 位十六进制 SHA-256；
- 临时 staging 目录；
- runtime-id 文件锁；
- SHA-256 最终文件重新校验；
- Zip Slip 和路径越界阻断；
- 归档条目/总解压大小限制；
- 安装失败时清理 staging，不破坏旧版本；
- 最终目录完整后再发布；
- manifest、文件 hash、完整 sidecar codec、大小/记录上限、immutable version/current 指针和 locator 全量文件校验已进入基础实现；仍需补充 JSON Catalog/签名、版本 probe 和 IntelliJ adapter；本地可写目录下的 TOCTOU 与未签名 sidecar 风险仍需产品信任边界或签名方案解决。

SHA-256 只保证完整性，不证明来源。发行版应增加内置公钥验证的签名 Catalog/manifest。

## 6. IntelliJ Community 接入路线

### 6.1 干净官方仓库

官方 clone 已完成并恢复为 clean checkout。产品脚本必须先验证目标 checkout，再执行：

```powershell
git -C G:\Projects\intellij-community-sage-ide rev-parse HEAD
git -C G:\Projects\intellij-community-sage-ide status --porcelain
git -C G:\Projects\intellij-community-sage-ide remote -v
```

只有 `rev-parse HEAD` 成功、工作树为空且 remote 指向官方仓库时，才能填写 `product/upstream.lock.json` 的 commit。当前 SHA、clean 状态、remote、build number、Bazel/Bazelisk 和 JDK 已写入 lock。


以官方远程为来源：

```text
https://github.com/JetBrains/intellij-community.git
```

目标目录：

```text
G:\Projects\intellij-community-sage-ide
```

它必须保持：

- 官方 `upstream` remote；
- 锁定的完整 commit SHA；
- clean working tree；
- 不在官方 checkout 中提交本产品改动。

现有 `G:\Projects\intellij-community-sage-pr` 只作研究和 Sage PR 参考。

### 6.2 产品 overlay

overlay 只存在于新产品仓库：

```text
product/community-overlay/
```

后续应拆分为：

- `product-properties/`；
- `application-info/`；
- `product-layout/`；
- `plugin-inclusion/`；
- `scripts/prepare-product.ps1`；
- `scripts/run-product.ps1`；
- `scripts/build-product.ps1`；
- `upstream.lock.json`。

推荐两棵树流程：

1. 官方 checkout 保持 clean/read-only；
2. 根据锁定 SHA 创建临时 worktree/staging tree；
3. 应用 overlay；
4. 只对 staging tree 执行 `bazel run` 或 `installers.cmd`；
5. 校验变更只来自预期 overlay；
6. 产品构建完成后删除 staging。

不要把完整 Community 源码复制进产品仓库，也不要把插件 ZIP 解压到 PyCharm 目录模拟完整 IDE。

### 6.3 产品基线选择

`plugins/sage-core` 目前依赖：

- `com.intellij.modules.python`；
- `com.jetbrains.python.*`；
- Python Core；
- Python debugger；
- Jupyter/Notebook 相关能力。

因此在接入 overlay 前必须冻结并验证：

- Community base 是否包含/允许使用这些模块；
- 是否需要 PyCharm Community product base；
- Python Core、Jupyter、Debugger、Git、Terminal 的来源和许可证；
- Sage core 作为第三方 bundled/external plugin 的注入方式。

不能假设 IDEA Community 平台自动提供完整 PyCharm Python 能力。

## 7. 本轮构建结果与后续顺序

### 已完成并验证

1. 在 `staging-build6` 中修复 `repair-modules-xml.ps1` 的传递依赖闭包：原始缺失 `.iml` 约 289 个，另外移除 45 个依赖缺失模块，最终注册 1900 个模块，未解析模块依赖为 0；manifest 位于 `build/sage-overlay/iml-filter-manifest.json`。
2. 修复产品 registry 使用错误的 PyCharm 专属依赖模块名，改为上游实际存在的共享模块 `intellij.idea.community.build.dependencies`。
3. `SageMathCommunityProperties` 保留运行时 `platformPrefix = "PyCharmCore"` 以兼容 PyCharm Python 插件，同时 Sage registry target 使用 `SageMath`，并通过 Bazel JVM flag 传递 `-Didea.platform.prefix=SageMath`。
4. 为固定快照缺失 Android 源码树的情况，仅在 Sage 产品 layout 中排除 Android plugin layouts；官方 checkout 未修改。
5. `//build:sage_math` 成功完成 3638 个 action，启动了 `SageMath CTF IDE 2026.3 EAP Build #SMC-263.SNAPSHOT` 开发实例；交互进程随后手动停止，启动成功本身已验证。
6. `//python/build:sage_i_build_target -- -Dintellij.build.target.os=current` 成功完成 5539 个 action，生成 Windows x64 和 aarch64 installer、product-info、SBOM、许可证和源码归档。
7. `out\\sage-math\\dist.all\\plugins\\sage-core\\lib` 已包含 Sage Core 的 4 个 JAR；这说明 Sage Core 已进入 installer 的 common distribution payload，但 `sage-core-0.1.0-dev.zip` 仍只是插件 ZIP，不是完整 IDE。

Installer 校验值：

```text
G:\\sage-build\\staging-build6\\out\\sage-math\\artifacts\\sageMath-263.SNAPSHOT.exe
SHA-256: 1dff11ffffee6fa00e920287406e8035e38691d851d45c1993bea7eb247e548a

G:\\sage-build\\staging-build6\\out\\sage-math\\artifacts\\sageMath-263.SNAPSHOT-aarch64.exe
SHA-256: 3fe09e8eabca2628b17775135d72edd7ced9e56b1ddf60c12ace755a35da2374
```

`product-info.json` 已验证产品名为 `SageMath CTF IDE`、product code 为 `SMC`、
选择器为 `SageMath2026.3`，启动器为 `bin/sage64.exe`；Windows installer 配置使用
`SageMath CTF IDE Community` 和安装目录名 `SageMath CTF IDE`。x64 distribution
包含 `bin/sage.exe`、`bin/sage64.exe`、JBR、LICENSE/NOTICE 和 Sage Core common payload。

### 下一迭代

1. 将 Sage Core 从 `getAdditionalPluginPaths()` 外部插件注入迁移为正式 Community JPS/Bazel bundled plugin，并让同一 graph 负责 descriptor、测试、installer 和 SBOM。
2. 实现 `SageRuntimeService` IntelliJ adapter，把 Runtime 选择接入 `SageRunSettings` 和 Run Configuration。
3. 增加 `sage --version`、`1+1` probe，并对超过 63 秒的 `test.sage` 做真实运行回归。
4. 完成 Runtime Catalog、签名 manifest、许可证审计、Windows 签名和 installer 直接安装/卸载 smoke test。
5. 不要把当前 Sage Core ZIP 或 common distribution 目录单独称为完整 IDE；完整 IDE 以 staged product target 和 installer 为准。

## 8. 验证命令

当前项目 wrapper 使用 **Gradle 9.6.0-bin**，以便 Gradle 主进程、Kotlin DSL 和 Kotlin 编译都使用 JDK 25；并通过 `gradlew.bat` 在未显式设置 `GRADLE_USER_HOME` 时使用项目内 ASCII 路径 `.gradle-user-home`。这是为规避 Windows 中文用户目录导致的 Gradle worker `@argfile` 主类损坏：

```powershell
$env:JAVA_HOME = 'D:\Java\jdk-25'
Remove-Item Env:GRADLE_USER_HOME -ErrorAction SilentlyContinue
./gradlew.bat projects --no-daemon --max-workers=1
./gradlew.bat :core:model:test -PrunModelTests=true --no-daemon --max-workers=1
./gradlew.bat :core:runtime:test -PrunRuntimeTests=true --no-daemon --max-workers=1
```

Sage core 编译：

```powershell
$env:JAVA_HOME = 'D:\Java\jdk-25'
./gradlew.bat :plugins:sage-core:compileKotlin --no-daemon --max-workers=1
```

项目的 Kotlin JVM toolchain 和 Gradle 主进程现在都使用 JDK 25；Gradle 9.6.0 + Kotlin 2.3.0 已通过模块编译和核心测试。原始中文 `GRADLE_USER_HOME` 下的 worker 报错已由 wrapper 默认 ASCII 用户目录解决，不要恢复直接使用该路径。Gradle 8.14.5 仍是 IntelliJ Community checkout 中辅助项目的 wrapper 版本，但不能作为本项目 JDK 25 的 Gradle 主进程基线。

历史错误：

```text
ClassNotFoundException: worker.org.gradle.process.internal.worker.GradleWorkerMain
```

该错误不是 Gradle 发行版缺少 `GradleWorkerMain`；Gradle jar 中存在 `org/gradle/process/internal/worker/GradleWorkerMain.class`，根因是 Windows worker argfile 在非 ASCII用户目录下被错误解析。

## 9. 交接提示词

后续代理可直接使用下面的提示词继续：

```text
继续开发 G:\Projects\sage-math-ctf-ide 的完整 SageMath CTF IDE。不要修改 G:\Projects\sage-ide-support；不要使用 G:\Projects\intellij-community-sage-pr 作为产品基线。先读取 HANDOFF.md、docs/STATUS.zh-CN.md、docs/IDE-PLAN.zh-CN.md、product/README.zh-CN.md 和 product/community-overlay/README.zh-CN.md。所有 Git 提交信息必须使用中文 Lore 结构。不要使用 GPU 作为当前 JVM/Bazel 编译加速假设；优先使用 CPU 并行度、SSD、内存和 Bazel cache。

当前官方基线：
- checkout: G:\Projects\intellij-community-sage-ide
- commit: b0001cd6c53979b384def7a1e3febe061e2ef687
- build: 263.SNAPSHOT
- Bazelisk: 1.29.0
- Bazel: 9.1.0-jb_20260505_126
- JDK: D:\Java\jdk-25
- 官方 checkout 当前必须保持 clean；产品修改只能进入临时 G:\sage-build staging worktree。

已完成并验证：
1. `plugins/sage-core:buildPlugin` 成功生成 `plugins/sage-core/build/distributions/sage-core-0.1.0-dev.zip`；该 ZIP 只能称为 Sage Core 插件包。
2. `core:model:test`、`core:runtime:test` 在 Gradle 9.6.0 + JDK 25 下通过。
3. overlay 脚本已创建：`prepare-upstream-staging.ps1`、`repair-modules-xml.ps1`、`prune-missing-android-labels.ps1`、`apply-overlay.ps1`、`stage-sage-plugin.ps1`、`verify-upstream-staging.ps1`、`build-upstream-staged.ps1`。
4. `staging-build6` 已完成 `bazel query //build:sage_math`、`//build:sage_math` dev build 和 `//python/build:sage_i_build_target` Windows installer build。
5. dev runner 已显示 `SageMath CTF IDE 2026.3 EAP Build #SMC-263.SNAPSHOT`；installer 已生成 x64/aarch64 两个 EXE，产物在 `G:\sage-build\staging-build6\out\sage-math\artifacts`。
6. staging filter manifest 记录 289 个缺失 `.iml`、45 个传递依赖模块清理和 0 个未解析模块依赖；官方 checkout 保持 clean。

当前优先级：
1. 不要重新运行完整 installer，除非 overlay、JDK、官方 SHA 或产品 layout 发生变化；优先复用 `staging-build6` 的 Bazel cache。
2. 检查并提交本产品仓库的预期改动，排除 `bazel-info.log` 等生成文件；官方 checkout 仍必须保持 clean。
3. 先为 Sage Core 正式 bundled plugin 迁移补充 JPS/Bazel graph 设计和回归测试，再实施源代码迁移。
4. 实现 Runtime adapter、显式 deadline/取消语义和 `sage --version`/表达式 probe。
5. 补充 installer 安装/卸载 smoke test、Windows 签名和完整法律审计。
6. `timeoutMillis=null` 表示默认无限制，正数表示显式 deadline，不能恢复 30 秒默认值。

重要事实：
- 上游 `.idea/modules.xml` 有 289 个缺失 `.iml` 条目；缺失 Android 源码树还导致生成 BUILD 引用失效。修复脚本只能在 staging 中运行并写 manifest；
- Windows Bazel/JDK 25 必须使用 ASCII `--host_jvm_args=-Duser.home=G:\sage-build\...`、TEMP/TMP 和 output root；
- 直接运行上游 `//build:idea_community` 或原始 `python\\installers.cmd` 不会选择 Sage 产品，必须使用 staging 生成的 Sage target。

完成前必须报告：改动文件、构建命令、测试结果、官方上游 SHA/状态、`git worktree list`、构建产物路径、SHA-256、已知风险和下一步。确认不要修改 `G:\Projects\sage-ide-support`，不要使用 `G:\Projects\intellij-community-sage-pr`，不要把 Sage Core ZIP 称为完整 IDE。
```

## 10. 已知风险

- `core:runtime` 当前为 ZIP/本机基础实现，已有 JDK HTTPS 下载器和本地完整 manifest codec，但尚未完成真实 HTTP Catalog、签名和 Runtime probe；
- Windows/macOS/Linux 的 Sage 官方发行物格式和许可证尚未冻结；
- WSL、容器和远程 Runtime 需要独立适配器；
- `sage-core` 仍依赖 PyCharm Python API；当前通过外部 plugin path 注入，尚未迁移为正式 Community JPS/Bazel bundled plugin；
- 上游固定快照缺失 Android 源码树，staging 需要 Android layout 过滤和 `.iml` 依赖闭包修剪；这些修复不能写回官方 checkout；
- installer 已成功生成，但 Windows 尚未签名，也没有执行直接安装/卸载 smoke test；安装器中 common payload 的合并仍应在真实安装后再做一次验证；
- SBOM 生成有上游许可证元数据警告：`GPL-2.0` 被报告为 deprecated；这不是构建失败，但需要发行前法律审查；
- `git remote -v` 在官方 checkout 当前没有显示远程，lock 文件仍记录 JetBrains 官方仓库 URL；后续若需要远程 fetch/pull，必须先单独修复并验证该状态，不能擅自改产品基线；
- 当前 JVM/Bazel/NSIS 构建不使用 GPU；GPU 不会加速 Java/Kotlin/JPS 编译，优先优化 CPU 并行、SSD、内存和 cache；
- 当前 Runtime/model 测试已在 Gradle 9.6.0 + JDK 25、项目 wrapper 的 ASCII 默认 Gradle 用户目录下通过；若显式覆盖为包含中文的 `GRADLE_USER_HOME`，仍可能重现 Windows worker argfile 问题；
- 任何 Runtime bundling 发行都必须补充 SBOM、LICENSE、NOTICE、源码对应物和法律审查。
