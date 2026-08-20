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
| `G:\Projects\intellij-community-sage-ide` | 官方 JetBrains Community checkout | blobless/no-checkout clone 已取得 `b0001cd6c53979b384def7a1e3febe061e2ef687`，但当前存在大规模 staged 删除；清理并复核前不能作为 clean 产品基线 |

当前 `intellij-community-sage-pr` 不是官方干净 master：它包含 Sage 专用提交，不能直接用于产品 release 或 CI。官方 `intellij-community-sage-ide` 已取得候选 HEAD `b0001cd6c53979b384def7a1e3febe061e2ef687`，但当前 Git 状态存在大规模 staged 删除；清理并通过 clean 检查前不能冻结该 SHA，也不能直接用于产品 release 或 CI。

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

官方 clone 已完成并取得 `HEAD`，但工作树出现大规模 staged 删除，因此仍不能直接用于开发。先恢复/清理目标 checkout，再执行：

```powershell
git -C G:\Projects\intellij-community-sage-ide rev-parse HEAD
git -C G:\Projects\intellij-community-sage-ide status --porcelain
git -C G:\Projects\intellij-community-sage-ide remote -v
```

只有 `rev-parse HEAD` 成功、工作树为空且 remote 指向官方仓库时，才能填写 `product/upstream.lock.json` 的 commit。当前候选 HEAD 虽然可读，但 clean 检查失败，因此 lock 中仍保持 `commit: null`。


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

## 7. 推荐后续工作顺序

### 当前迭代

1. 完成 `core:runtime` 编译与测试源码编译；
2. 添加 Runtime Catalog/manifest JSON schema 与签名信任链；
3. 继续补充 manifest 文件级校验和 locator/下载器安全测试；
4. 清理 `G:\Projects\intellij-community-sage-ide` 的 staged 删除并验证 clean working tree；
5. 记录官方基线 SHA/build/JDK/Bazel；
6. 更新计划、状态和本 HANDOFF；
7. 用中文提交。

### 下一迭代

1. 实现 `SageRuntimeService` IntelliJ adapter；
2. 把 Sage Runtime 选择接入 `SageRunSettings`；
3. 在 Run Configuration 中区分无限制/有限 deadline；
4. 增加 `sage --version` 和 `1+1` probe；
5. 对 `test.sage` 做真实 63 秒以上运行回归；
6. 创建 Community 开发实例 overlay；
7. 通过 M0–M3 后再接 installer。

## 8. 验证命令

声明本地 Java25：

```powershell
$env:JAVA_HOME = 'D:\Java\jdk-25'
./gradlew :core:model:compileKotlin :core:runtime:compileKotlin --no-daemon --max-workers=1
./gradlew :plugins:sage-core:compileKotlin --no-daemon --max-workers=1
```

模型测试：

```powershell
./gradlew :core:model:test -PrunModelTests=true --no-daemon --max-workers=1
```

Runtime 测试：

```powershell
./gradlew :core:runtime:test -PrunRuntimeTests=true --no-daemon --max-workers=1
```

当前 Windows 主机曾出现 Gradle worker：

```text
ClassNotFoundException: worker.org.gradle.process.internal.worker.GradleWorkerMain
```

因此测试开关暂时显式控制；CI 是权威验证环境。不要把这个环境问题误判为 Kotlin 模型错误。

## 9. 交接提示词

后续代理可直接使用下面的提示词继续：

```text
继续开发 G:\Projects\sage-math-ctf-ide 的完整 SageMath CTF IDE。不要修改 G:\Projects\sage-ide-support；不要使用 G:\Projects\intellij-community-sage-pr 作为产品基线。先读取 HANDOFF.md、docs/STATUS.zh-CN.md、docs/IDE-PLAN.zh-CN.md 和 product/README.zh-CN.md。所有 Git 提交信息必须使用中文。

当前优先级：
1. 完成 core:runtime 的编译与测试；
2. 实现 IDE 可下载/校验/安装/切换 SageMath Runtime 的基础能力；
3. timeoutMillis=null 表示默认无限制，正数表示显式 deadline，不能恢复 30 秒默认值；
4. 使用 G:\Projects\intellij-community-sage-ide 作为官方 JetBrains Community 干净 checkout，记录完整 upstream commit SHA、build number、JDK/Bazel；
5. 在 product/community-overlay 中做可重复的产品接入，不把完整上游源码复制到产品仓库；
6. 真实验证 C:\Users\星记\Downloads\test.sage 这类超过 63 秒的 Sage 工作负载；
7. 更新文档、运行验证、检查 git diff，并创建中文 Lore 提交。

完成前必须报告：改动文件、构建命令、测试结果、官方上游 SHA/状态、已知风险和下一步。
```

## 10. 已知风险

- `core:runtime` 当前为 ZIP/本机基础实现，已有 JDK HTTPS 下载器和本地完整 manifest codec，但尚未完成真实 HTTP Catalog、签名和 Runtime probe；
- Windows/macOS/Linux 的 Sage 官方发行物格式和许可证尚未冻结；
- WSL、容器和远程 Runtime 需要独立适配器；
- `sage-core` 仍依赖 PyCharm Python API，Community 产品是否提供完整依赖尚未验证；
- 完整 IDE 安装器尚未生成；
- 当前 Runtime/model 测试源码编译通过，但实际测试执行仍受本机 Gradle worker 环境影响；
- 任何 Runtime bundling 发行都必须补充 SBOM、LICENSE、NOTICE、源码对应物和法律审查。
