# SageMath CTF IDE 当前状态

## 当前阶段

P1：完整 IDE 产品基础设施与 SageMath Runtime Manager 原型。

## 已完成

- 已确认 `G:\Projects\sage-ide-support` 是独立的 JetBrains 插件仓库；
- 已创建独立产品仓库 `G:\Projects\sage-math-ctf-ide`；
- 已将现有插件代码复制到 `plugins/sage-core` 作为迁移基线；
- 已写入产品计划、CTF 范围和迁移地图；
- 已核对 IntelliJ Platform、IntelliJ Community 和 SageMath 官方构建资料；
- 已确认 IntelliJ Community 当前使用 Bazel/installer 入口，产品构建不能假设是普通插件 Gradle 打包；
- 已把产品目标升级为完整 IDE，并加入可下载/校验/安装/切换 SageMath Runtime 的设计；
- 已将 `core:model` 默认 CTF 超时改为 `null`（无限制），正数才启用 deadline；
- 已新增 `core:runtime` 的平台模型、Catalog、HTTPS/SHA-256 下载、强制 manifest、ZIP 安全安装、immutable versions/current 指针和 Runtime Manager 原型；
- 已建立官方 Community checkout 目标 `G:\Projects\intellij-community-sage-ide` 的独立目录约定，与 `-pr` 研究 checkout 分离；blobless/no-checkout clone 已取得候选 HEAD `b0001cd6c53979b384def7a1e3febe061e2ef687`，但当前 Git 状态存在大规模 staged 删除，尚未达到 clean 产品基线，故未冻结 commit；
- 已创建 `HANDOFF.md` 和 `product/upstream.lock.json`。

## 尚未完成

- Runtime Catalog/manifest JSON 序列化、签名与远程 manifest 下载；当前本地 sidecar 已有完整无依赖 codec、大小/记录限制和 locator 全量文件校验，但尚未形成签名信任链；
- `sage --version` / `1+1` Runtime probe；
- IntelliJ Settings/Project SDK Runtime adapter；
- Community product properties/layout/plugin injection；
- product run/build scripts；
- 完整 IDE 开发实例和安装器；
- Runtime 测试在当前 Windows Gradle worker 环境执行；本轮 Java25 测试源码编译通过，但测试执行仍受 worker 启动问题阻塞；
- 官方 Community checkout 已有候选完整 SHA，但必须清理 staged 删除并重新验证 clean working tree；因此 upstream lock 的 commit 仍为 null，build number/Bazel 与产品 overlay 仍未冻结。

## 验证环境记录

- `./gradlew projects --no-daemon`：通过；
- `:core:model:compileKotlin`：通过；
- 本机 Gradle test worker 在 Windows 上以 `ClassNotFoundException: worker.org.gradle.process.internal.worker.GradleWorkerMain` 失败；测试任务通过 `-PrunModelTests=true` 显式开启，默认关闭，CI 需要开启并作为权威结果；
- `:plugins:sage-core:compileKotlin`：首个产品基线验证已通过；本轮改动后需再次运行；
- `:core:runtime:compileKotlin` 与 `:core:runtime:compileTestKotlin`：通过；
- `:core:runtime:test -PrunRuntimeTests=true`：测试代码编译通过，但当前 Windows Gradle worker 仍以 `ClassNotFoundException: worker.org.gradle.process.internal.worker.GradleWorkerMain` 失败；
- `:core:model:test -PrunModelTests=true`：同一 Gradle worker 环境问题失败，不能归因于模型编译。

## 当前硬约束

1. 不修改源仓库 `G:\Projects\sage-ide-support`；
2. 不把整个 IntelliJ Community 源码复制进产品仓库；
3. Runtime 必须由 IDE 管理生命周期，但 IDE 安装器是否捆绑 Runtime 需独立完成许可证/SBOM 审计后决定；
4. 不把 CTF 能力做成只能依赖 PyCharm 的功能；
5. 先通过可测试的模块边界降低迁移成本，再接真实产品构建。

## 下一轮验收

- `gradlew projects` 能识别新模块；
- `gradlew :core:model:test` 通过；
- `gradlew :plugins:sage-core:compileKotlin` 或等价构建成功；
- `git status` 只显示产品仓库自身文件；
- 计划和迁移地图中的链接有效。

## 已知风险

- 当前 Sage core 大量依赖 `com.jetbrains.python.*`；
- 当前调试实现依赖 PyCharm Python debugger；
- 目标独立产品的 Python/Jupyter/Debugger 模块集合尚未冻结；
- 官方 Community checkout 目标为 `G:\Projects\intellij-community-sage-ide`，当前 `intellij-community-sage-pr` 仅为研究/PR 参考；官方 clone 已取得 `b0001cd6c53979b384def7a1e3febe061e2ef687`，但工作树存在大规模 staged 删除，清理并复核前禁止作为 clean 产品基线；
- 目标仓库初始复制不等于已经完成独立 IDE 产品构建。
