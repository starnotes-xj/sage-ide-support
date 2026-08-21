# IntelliJ Community 产品构建接入说明

## 目的

本目录记录如何把 `plugins/sage-core` 和未来的 `plugins/ctf-tools` 接入 IntelliJ Community 的独立产品构建。

当前阶段只建立**接入约定**，不复制 `G:\Projects\intellij-community-sage-pr` 的完整源码，也不把当前插件 Gradle 打包误称为完整 IDE 构建。

## 上游 checkout

当前产品开发使用的官方干净 checkout：

```text
G:\Projects\intellij-community-sage-ide
```

现有 Sage PR/研究 checkout（不作为产品基线）：

```text
G:\Projects\intellij-community-sage-pr
```

该 checkout 的 README 说明：

- IntelliJ Community 项目当前正在向 Bazel 迁移；
- IDE 开发使用 `.bazelproject` 和 Bazel 插件；
- 安装包通过 `installers.cmd` / `OpenSourceCommunityInstallersBuildTarget` 构建；
- 产品构建基于 Community 的 product properties 和 product layout。

在真正接入前必须记录：

```text
upstream repository: https://github.com/JetBrains/intellij-community.git
checkout path: G:\Projects\intellij-community-sage-ide
commit: <待冻结>
branch/tag: <待冻结>
JDK: 25
host OS: <构建机>
```

### Gradle 模块构建基线

IntelliJ Community 的主 IDE/安装器构建入口是 Bazel/Bazelisk，不是根 Gradle 工程；其 checkout 中用于构建依赖和辅助开发项目的官方 wrapper 记录为 **Gradle 8.14.5-all**。但本仓库要求 Gradle 主进程也使用 JDK 25，实测当前 Kotlin DSL/Kotlin 2.3.0 组合需要 Gradle **9.6.0**，因此本项目 wrapper 使用 JetBrains 官方 Gradle 分发源：

```text
distributionUrl=https://cache-redirector.jetbrains.com/services.gradle.org/distributions/gradle-9.6.0-bin.zip
```

Windows 下 `gradlew.bat` 默认将 `GRADLE_USER_HOME` 放到仓库内的 ASCII 路径 `.gradle-user-home`，避免中文用户目录破坏 Gradle test worker 的 `@argfile`。Gradle 主进程和各 Kotlin 模块的 `jvmToolchain` 都使用 JDK 25。不要把该 Gradle wrapper 误称为完整 Community IDE 构建；完整 IDE 仍按上游 `bazel run //build:idea_community` 和 `installers.cmd` 流程。

## 产品接入策略

推荐新建一个上游 product overlay，而不是修改 IntelliJ IDEA Community 的身份：

1. 复用 `JetBrainsProductProperties` 的社区产品基础；
2. 定义新的 product code、platform prefix、应用名称和安装目录；
3. 默认 bundled `Python Core`、Jupyter/Notebook 所需模块、Git、Terminal 和 `sage-core`；
4. 将 `ctf-tools` 作为默认产品插件；
5. 为 Windows、macOS、Linux 定义文件关联、URL scheme、图标和安装器配置；
6. 通过 `installers.cmd` 或等价 build target 生成产品包；
7. 构建产物通过 SBOM、LICENSE、NOTICE 和源码归档检查后才允许发布。

## 与当前插件构建的区别

当前 `plugins/sage-core` 可以使用 IntelliJ Platform Gradle Plugin 构建插件 ZIP。这个 ZIP 是产品插件，不是独立 IDE 安装包。

| 任务 | 结果 |
|---|---|
| `:plugins:sage-core:buildPlugin` | Sage core 插件 ZIP |
| Community `bazel run //build:idea_community` | Community 开发实例 |
| Community `installers.cmd` / 自定义 product target | 独立 IDE 安装包 |

不要通过将一个插件 ZIP 解压到 PyCharm 安装目录来模拟产品发行。

## 首个接入任务

- [ ] 选定并冻结 Community commit；
- [ ] 确认目标版本的 Python Core/Python PSI 模块；
- [ ] 确认 Jupyter、Debugger 和 Git/Terminal 的开源模块；
- [ ] 编写 `SageMathCtfProductProperties`；
- [ ] 编写产品 product layout；
- [ ] 把 `sage-core` 和 `ctf-tools` 加入默认插件列表；
- [ ] 建立 `build-product.ps1` / `build-product.sh`；
- [ ] 建立单平台开发实例 smoke test；
- [ ] 再扩展到跨平台 installers。

## 不可提前承诺的事项

- PyCharm 的所有 Python 功能都能直接进入产品；
- PyCharm 专有 debugger 可以无修改复用；
- SageMath 可以无许可证审计直接捆绑；
- Community 的当前 product layout 永远稳定；
- 目标产品可以绕过 Bazel/上游构建工具只用 Gradle 完成安装包。

## 参考

- [IntelliJ Community README](https://github.com/JetBrains/intellij-community/blob/master/README.md)
- [IntelliJ Platform Gradle Plugin](https://plugins.jetbrains.com/docs/intellij/tools-intellij-platform-gradle-plugin.html)
- [IntelliJ Platform tasks](https://plugins.jetbrains.com/docs/intellij/tools-intellij-platform-gradle-plugin-tasks.html)
- [产品计划](../docs/IDE-PLAN.zh-CN.md)
