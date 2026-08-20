# Sage IDE Support → SageMath CTF IDE 迁移地图

## 仓库边界

- 源仓库：`G:\Projects\sage-ide-support`
- 目标仓库：`G:\Projects\sage-math-ctf-ide`
- 目标插件模块：`plugins/sage-core`
- 源仓库保持独立，不在本迁移中改变其 Marketplace 发布职责。

## 当前迁移内容

| 源能力 | 当前来源 | 目标位置 | 状态 |
|---|---|---|---|
| Sage 文件类型、语言和图标 | `src/main/kotlin/.../sugar` | `plugins/sage-core/src/main/kotlin/.../sugar` | 已迁移基线 |
| Sage parser / lexer | `src/main/kotlin/.../parser`、`com/jetbrains/python/parsing` | `plugins/sage-core/...` | 已迁移基线 |
| Sage 类型、隐式 namespace、postfix | `src/main/kotlin/.../type`、`sugar` | `plugins/sage-core/...` | 已迁移基线 |
| Native/WSL/Docker 运行 | `src/main/kotlin/.../run` | `plugins/sage-core/...` | 已迁移基线 |
| Sage 模板、图标、plugin.xml | `src/main/resources` | `plugins/sage-core/src/main/resources` | 已迁移基线 |
| 平台测试和 testData | `src/test` | `plugins/sage-core/src/test` | 已迁移基线 |
| 运行目标模型 | 当前与 IntelliJ API 混合 | `core/model` | 待抽离 |
| CTF project profile | 尚无产品实现 | `core/model` + `plugins/ctf-tools` | 待实现 |
| CTF 运行记录和 flag 扫描 | 尚无产品实现 | `core/runtime` + `plugins/ctf-tools` | 待实现 |
| 独立产品品牌和默认插件 | 不存在 | `product` / Community overlay | 待接入 |

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

### M2：语言能力等价

以下测试在目标产品通过：

- `.sage` 文件类型身份；
- generator sugar；
- `^`/`^^` 语义；
- 隐式 `sage.all`；
- Sage 类型 provider；
- postfix templates；
- quote handler 和检查。

### M3：运行闭环

Native、WSL、Docker 至少一个目标可运行当前 `.sage` 文件，并显示标准输出、错误、退出码和终止状态。

### M4：产品默认集成

Sage core 成为 SageMath CTF IDE 的默认插件，用户无需从 Marketplace 安装。

### M5：产品发行

构建、签名、许可证、安装包和启动器在目标平台验证；不再把 PyCharm 安装目录作为产品运行时依赖。

## 下一步

1. 添加 `core:model`；
2. 添加 root 多模块构建；
3. 为 Sage core 增加产品模块入口；
4. 建立 Community overlay 的固定路径和版本记录；
5. 运行 M0；
6. 再实现 CTF profile，而不是先做孤立工具窗口。
