# Sage IDE Support → SageMath CTF IDE 迁移地图

## 仓库边界

- 源仓库：`G:\Projects\sage-ide-support`
- 目标仓库：`G:\Projects\sage-math-ctf-ide`
- 目标插件模块：`plugins/sage-core`
- 源仓库保持独立，不在本迁移中改变其 Marketplace 发布职责。

## 当前迁移内容

> 当前实际状态：Sage Core 语言/运行基线已迁移并通过构建/测试；`core:sage-api` 与 `plugins:sage-core` 已形成 scoped 数据驱动 API 链路。Runtime Manager 核心已由 `a2c7fdc` 进入 `main`；CTF MVP/图形化 Math Lab 实现会话仍在独立 worktree，主线整合、产品 UI/真实端点和分发验收按独立边界推进。完整矩阵见 [功能实现状态与版本边界](FEATURE-STATUS.zh-CN.md)。

| 源能力 | 当前来源 | 目标位置 | 状态 |
|---|---|---|---|
| Sage 文件类型、语言和图标 | `src/main/kotlin/.../sugar` | `plugins/sage-core/src/main/kotlin/.../sugar` | 已迁移基线 |
| Sage parser / lexer | `src/main/kotlin/.../parser`、`com/jetbrains/python/parsing` | `plugins/sage-core/...` | 已迁移基线 |
| Sage 类型、隐式 namespace、postfix | `src/main/kotlin/.../type`、`sugar` | `plugins/sage-core/...` | 部分实现；已接入 `core:sage-api` immutable index、factory return type 和 indexed members；全量 index/type engine 待完成 |
| Native/WSL/Docker 运行 | `src/main/kotlin/.../run` | `plugins/sage-core/...` | 已迁移基线 |
| Sage 模板、图标、plugin.xml | `src/main/resources` | `plugins/sage-core/src/main/resources` | 已迁移基线 |
| 平台测试和 testData | `src/test` | `plugins/sage-core/src/test` | 已迁移基线 |
| 运行目标模型 | Runtime Manager 核心已由 `a2c7fdc` 进入 main，补齐 Catalog、生命周期、SDK binding、target-aware probe 和路径映射；真实 UI/端点待完成 | `core:model` + `core:runtime` + product adapter | 核心进入 main，产品验收待完成 |
| CTF project profile + Math Lab | CTF 会话已补齐 project/challenge/profile、notes、payload、solve scripts、UI 模型和图形化 Math Lab（群/环/域、ECC、RSA、DH、DES）；主线整合待完成 | `core/model` + `plugins/ctf-tools` | 实现会话完成，主线整合待完成 |
| CTF 运行记录和 flag 扫描 | CTF 会话已补齐 bounded execution、flag scanner、run history、evidence、Crypto/Encoding helpers、loopback CyberChef adapter 和脚本安全边界 | `core/runtime` + `plugins/ctf-tools` | 实现会话完成，产品/分发验收待完成 |
| 独立产品品牌和默认插件 | Community overlay 和 Sage properties 已接入；跨平台/Pro 未完成 | `product` / Community overlay | Community 已完成主要接入 |

## 迁移纪律

1. **不要直接修改源插件仓库来实现产品功能。** 源仓库继续面向 PyCharm 发布。
2. **先迁移行为，再抽象边界。** 现有 Sage 语义测试是迁移基线。
3. **领域知识留在数据层。** Sage 方法和类型优先来自 stubgen；插件只实现通用平台机制和 Sage 语言语义。
4. **平台无关模块不得导入 IntelliJ API。** 发现 `com.intellij.*` 时，应判断是否属于 product adapter。
5. **所有运行适配器必须可测试。** 不把参数拼接、路径映射和超时逻辑藏在 UI action 中。
6. **任何 PyCharm-only API 都要有迁移门。** 在目标产品未确认前标记为 compatibility dependency。

## 当前已知兼容性依赖

来自源插件 `build.gradle.kts` 和 `plugin.xml`：

- Kotlin JVM；
- IntelliJ Platform Gradle Plugin；
- JDK 25；
- `com.intellij.modules.python`；
- PythonCore/Python PSI；
- `com.jetbrains.python.*` API；
- Sage external runtime；
- `sage-pycharm-stubgen` 生成的 `.pyi` 数据；
- Native/WSL/Docker 命令行；
- PyCharm Python debugger（当前调试实现）。

## 迁移门

### M0：代码可编译

目标仓库能够编译 `plugins:sage-core` 的 Kotlin 源码。

### M1：插件元数据可加载

目标产品可以解析 Sage plugin.xml，Python/PythonCore 依赖明确且失败信息可诊断。

### M2：语言智能能力等价

以下测试在目标产品通过：

- `.sage` 文件类型身份；
- generator sugar；
- `^`/`^^` 语义；
- 隐式 `sage.all`；
- Sage API index 覆盖率和版本差异报告；
- Sage 类型 provider、类型传播和 parent 关系；
- 全量模块/类/函数/方法补全、参数提示和文档提示；
- postfix templates；
- quote handler、检查和 source-map。

### M3：运行闭环

Native、WSL、Docker 至少一个目标可运行当前 `.sage` 文件，并显示标准输出、错误、退出码和终止状态。

### M4：产品默认集成

Sage core 成为 SageMath CTF IDE 的默认插件，用户无需从 Marketplace 安装。

### M5：产品发行

构建、签名、许可证、安装包和启动器在目标平台验证；不再把 PyCharm 安装目录作为产品运行时依赖。

## 当前完成度与下一步

P0 基础骨架和 M0–M4 的主要代码/构建接入已完成；Runtime Manager 核心已由 `a2c7fdc` 进入 main，CTF MVP/图形化 Math Lab 实现会话已完成并通过定向验证；M5 的 Windows x64/aarch64 构建、x64 smoke 和 FinalCheck 已验证，但签名、法律审批、Linux/macOS 和 arm64 主机验收仍未完成。

下一步：

1. 保持 Sage/Python 支持版本与 API index sidecar/quality gate 的可审计生成；
2. Runtime Manager 核心已由 `a2c7fdc` 进入 `main`；后续只受控整合最新 `parallel/ctf-mvp`；`integration/ctf-mvp` 仅作为安全审计参考，不作为第二个合并来源，逐项保留其测试与安全边界；
3. 验收真实 IntelliJ Settings/Project SDK UI、WSL/Docker/SSH 端点、并发/崩溃 fault-injection，以及 live CyberChef-server、Math Lab IDE live ToolWindow/完整产品 smoke；
4. 实现 Sage 类型传播、补全/参数/文档提示、跳转和 source-map 验收；
5. 补 doctest、PCAP、二进制、GDB/LLDB，最后再处理可选 Jupyter、签名、法律审批、Linux/macOS、自动更新和 Pro 产品线。

详细状态见 [功能实现状态与版本边界](FEATURE-STATUS.zh-CN.md)。
