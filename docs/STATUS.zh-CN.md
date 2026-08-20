# SageMath CTF IDE 当前状态

## 当前阶段

P0：仓库与产品骨架。

## 已完成

- 已确认 `G:\Projects\sage-ide-support` 是独立的 JetBrains 插件仓库；
- 已创建独立产品仓库 `G:\Projects\sage-math-ctf-ide`；
- 已将现有插件代码复制到 `plugins/sage-core` 作为迁移基线；
- 已写入产品计划、CTF 范围和迁移地图；
- 已核对 IntelliJ Platform、IntelliJ Community 和 SageMath 官方构建资料；
- 已确认 IntelliJ Community 当前使用 Bazel/installer 入口，产品构建不能假设是普通插件 Gradle 打包。

## 尚未完成

- root Gradle 多模块构建；
- platform-independent `core:model`；
- CTF project profile；
- Community product overlay；
- product run/build scripts；
- CI；
- 首次编译与测试；
- Git 初始提交。

## 验证环境记录

- `./gradlew projects --no-daemon`：通过；
- `:core:model:compileKotlin`：通过；
- 本机 Gradle test worker 在 Windows 上以 `ClassNotFoundException: worker.org.gradle.process.internal.worker.GradleWorkerMain` 失败；测试任务通过 `-PrunModelTests=true` 显式开启，默认关闭，CI 需要开启并作为权威结果；
- `:plugins:sage-core:compileKotlin`：正在验证。

## 当前硬约束

1. 不修改源仓库 `G:\Projects\sage-ide-support`；
2. 不把整个 IntelliJ Community 源码复制进产品仓库；
3. 不在首版捆绑 Sage runtime；
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
- 上游 Community checkout 目前位于 `G:\Projects\intellij-community-sage-pr`，其分支/commit 必须在产品构建接入时锁定；
- 目标仓库初始复制不等于已经完成独立 IDE 产品构建。
