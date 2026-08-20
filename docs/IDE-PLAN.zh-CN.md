# SageMath CTF IDE 开发计划

> 项目定位：面向 SageMath 的专业科学计算 IDE，并对 CTF（尤其是密码学、数论、逆向与取证工作流）做一等公民优化。
>
> 当前状态：规划与产品仓库初始化阶段。
>
> 创建日期：2026-08-19

## 1. 决策摘要

### 1.1 产品决策

本项目不再以“PyCharm 插件的长期增强版”为最终形态，而是开发一个基于 IntelliJ Platform 的独立产品：

**SageMath CTF IDE**

产品的核心价值不是复刻 PyCharm 的全部功能，而是把以下三件事放在同一个可复现工作区内：

1. SageMath 数学计算与符号/数值编程；
2. CTF 解题所需的密码学、编码、二进制、网络和脚本工具；
3. 类似 IDEA/PyCharm 的工程、编辑、运行、调试、索引和版本控制体验。

### 1.2 仓库边界

现有仓库与新产品仓库职责明确分离：

| 仓库 | 路径 | 职责 | 处理原则 |
|---|---|---|---|
| 现有插件 | `G:\\Projects\\sage-ide-support` | JetBrains 插件发布与 PyCharm 兼容性 | 保持独立，不改成 IDE 仓库 |
| 新产品 | `G:\\Projects\\sage-math-ctf-ide` | 独立 IDE 产品、产品配置、CTF 工作流和迁移后的核心插件 | 本仓库是后续 IDE 开发主线 |
| Sage 类型数据 | 外部 `sage-pycharm-stubgen` 项目 | Sage 类型存根和文档数据 | 通过环境/项目配置消费，不复制领域知识 |
| IntelliJ 上游 | 外部 `intellij-community` checkout | 平台和社区产品构建基础 | 通过固定版本/构建脚本接入，不复制整个上游到本仓库 |

现有插件的源代码已经迁移到新仓库的 `plugins/sage-core`，作为迁移基线。迁移的第一原则是**保留现有能力、逐步抽象平台无关契约、再替换产品入口**，而不是重写一遍插件。

### 1.3 第一阶段的真实目标

第一阶段先交付“可运行的独立产品开发骨架”，而不是立即声称已经完成完整安装器：

- 新产品仓库可独立构建；
- 现有 Sage 语言/运行能力作为 `sage-core` 产品插件保留；
- CTF 领域模型与执行目标模型不依赖 IntelliJ API；
- 有固定的 IntelliJ Community 产品构建接入点；
- 有可验证的开发实例、测试和迁移记录；
- 后续可把同一份 `sage-core` 安装到独立产品，而不是再从 PyCharm 插件复制代码。

## 2. 依据与现状基线

### 2.1 IntelliJ Platform

JetBrains 官方资料确认 IntelliJ Platform 可复用编辑器、项目模型、索引、导航、运行/调试、测试、工具窗口、版本控制和插件机制，并通过自定义语言支持扩展 Lexer、Parser、PSI、补全、检查、导航、重构等能力：

- [IntelliJ 平台开源页](https://www.jetbrains.com/zh-cn/opensource/intellij-platform/)
- [IntelliJ Platform](https://plugins.jetbrains.com/docs/intellij/intellij-platform.html)
- [IntelliJ Platform SDK Welcome](https://plugins.jetbrains.com/docs/intellij/welcome.html)
- [Custom Language Support](https://plugins.jetbrains.com/docs/intellij/custom-language-support.html)
- [IntelliJ Platform Gradle Plugin](https://plugins.jetbrains.com/docs/intellij/tools-intellij-platform-gradle-plugin.html)

`intellij-community` 当前 README 说明社区源码可构建开源 IntelliJ Platform/IDEA/PyCharm 部分，同时构建正在向 Bazel 迁移；因此产品构建应使用上游支持的 Bazel/installer 入口，而不是臆造一个“纯 Gradle 打包完整 IDE”的路径：

- [intellij-community README](https://github.com/JetBrains/intellij-community/blob/master/README.md)

### 2.2 SageMath

SageMath 官方资料说明 Sage 是集成 Python、Cython 和大量数学软件/原生库的数学系统，能够启动 Sage console 和 Jupyter；源码开发还涉及 doctest、Cython、C/C++/Fortran 与复杂的构建依赖：

- [SageMath 官方主页](https://www.sagemath.org/)
- [SageMath README](https://github.com/sagemath/sage/blob/develop/README.md)
- [Sage 安装指南](https://doc.sagemath.org/html/en/installation/index.html)
- [Launching SageMath](https://doc.sagemath.org/html/en/installation/launching.html)
- [Sage Developer Guide](https://doc.sagemath.org/html/en/developer/index.html)

因此，本产品采用“完整 IntelliJ IDE + IDE 管理的 Sage Runtime”的边界：Runtime 生命周期由 IDE 负责发现、下载、校验、安装、选择、切换和回滚，但 Sage 解释器及原生数学依赖仍在受控外部 Runtime 进程中运行。Native、WSL、Docker、Conda、SSH/HPC 通过统一适配器接入；不把 Sage 解释器和所有原生数学依赖直接嵌入 JVM 进程作为首要方案。

## 3. 产品范围

### 3.1 必须支持的核心能力

#### A. SageMath 语言与项目

- `.sage` 独立文件类型；
- Sage `^` 幂、`^^` XOR、`^=` 与 `^^=` 的预解析语义；
- `R.<x> = GF(2)[]` 等 generator sugar；
- 隐式 `sage.all` 命名空间；
- Sage 存根索引、文档和类型推断；
- `.py`、`.pyx`、`.ipynb` 与 `.sage` 混合项目；
- Sage SDK/环境检测与健康检查；
- 当前文件运行、运行配置、REPL/Console；
- doctest/test runner；
- Jupyter Sage kernel 与富输出；
- LaTeX、图像、SVG/HTML 结果预览。

#### B. CTF 优先能力

CTF 能力必须进入产品架构，而不是最后通过零散插件补充。

**第一优先级：密码学与数论**

- 大整数、模运算、逆元、gcd/egcd；
- 素性测试、因式分解、离散对数；
- RSA 常见攻击实验工作区：低指数、共模、广播、Wiener、共因子等；
- 有限域、椭圆曲线和群运算；
- continued fraction、CRT、Pell/Diophantine 辅助；
- bytes/int/hex/base64/URL/整数序列转换；
- Sage 表达式结果直接复制为 Python/Sage 代码。

**第二优先级：题目执行与证据管理**

- CTF Project Profile：题目目录、输入文件、输出目录、环境变量、超时、输出上限；
- flag 正则/前缀配置与结果扫描；
- challenge run configuration；
- 标准输入、参数和环境的可复现记录；
- stdout/stderr/退出码/耗时/目标环境的执行记录；
- 题目 notes、payload、solve 脚本和结果文件的项目化组织。

**第三优先级：二进制、网络与取证入口**

- ELF/PE/Mach-O 文件识别和基本元数据入口；
- PCAP 打开、过滤器、流/HTTP/DNS/凭据提取入口；
- 常见编码、压缩、哈希和 XOR 工具入口；
- GDB/LLDB、pwndbg/gef、远程调试的集成边界；
- Web 请求/响应和脚本调用的可复现记录。

这些功能优先以“调用本机工具、Sage API 或独立 adapter”的方式实现，避免在 IDE 核心中复制一套安全工具库。

### 3.2 完整 IDE 的首版定义

“完整 IDE”在本项目中不是把 SageMath 解释器塞进 JVM，而是交付完整的 IntelliJ 产品壳、内置 Sage 功能、可管理的 SageMath SDK/Runtime 和 CTF 工作台：

- 产品启动器、项目模型、编辑器、索引、终端、Git、运行/调试和设置均由独立 IntelliJ 产品提供；
- SageMath Runtime 由 IDE Catalog/Manager 下载、校验、安装、切换和验证；
- Sage 运行通过已选 Runtime 执行，不把 Runtime 进程误当成插件开发时的外部手工依赖；
- Runtime 可选随安装器提供，也可首次启动后下载；两种发行策略共享同一 Runtime Manager 协议；
- CTF Profile 默认无限制运行，但保留显式取消、输出上限和用户可选 deadline；
- 产品安装包、Runtime 安装包和许可证/SBOM 是独立交付物，分别审核。

### 3.3 明确不作为首版目标

- 首版不把 SageMath Runtime 硬编码进 IDE 安装器；
- 产品必须提供类似 IDEA/PyCharm SDK 管理器的 SageMath Runtime Catalog、下载、校验、安装、切换和卸载入口；
- 首版优先支持官方 HTTPS 归档的本机 Native Runtime，WSL、Docker/Podman 和 SSH/HPC 采用独立目标适配器；
- 首版不承诺原生 Windows Sage 的完整支持，优先支持 Windows + WSL/容器；
- 首版不追求覆盖 Sage 全部动态类型；
- 首版不重写完整 Python/Cython 语言服务；
- 首版不复制 PyCharm 专有功能；
- 首版不实现完整的 Ghidra、Wireshark、IDA、pwndbg 替代品；
- 首版不在 IDE 进程内嵌入 Python/Sage；
- 首版不在没有构建产物级许可证审计前发布捆绑运行时。

## 4. 产品架构

```text
SageMath CTF IDE
│
├── IntelliJ Community Product
│   ├── Platform / editor / project model / indexing
│   ├── Git / terminal / run / debug / test infrastructure
│   ├── Python Core / Jupyter / debugger capabilities
│   └── Sage product branding and default plugin layout
│
├── sage-core plugin
│   ├── .sage language and Sage PSI
│   ├── Sage preparse-aware analysis
│   ├── Sage stubs and documentation integration
│   ├── Sage run/debug configuration
│   ├── Sage console/Jupyter integration
│   └── Sage live/postfix templates
│
├── core:model (platform-independent)
│   ├── SageExecutionTarget
│   ├── CtfProjectProfile
│   ├── execution limits and result contracts
│   └── future runtime protocol types
│
├── ctf-tools (future product plugins)
│   ├── Crypto/Number Theory
│   ├── Encoding/Hash/XOR
│   ├── Forensics/PCAP
│   ├── Binary/Reverse
│   └── Challenge evidence and flag workflow
│
└── external runtimes and adapters
    ├── Native Sage
    ├── WSL Sage
    ├── Docker/Podman Sage
    ├── Conda environments
    └── SSH/HPC/remote kernels
```

### 4.1 运行时边界

SageMath Runtime 不应只被当作用户手工安装的外部命令。完整 IDE 应像 IDEA 管理 JDK、PyCharm 管理 Python SDK 一样，提供 `SageMath Runtime Manager`：

1. 从受信任的 HTTPS Catalog 展示 SageMath 版本、Python 版本、操作系统、CPU 架构、libc、大小和许可证信息；
2. 下载到用户可写的 staging 目录，流式计算 SHA-256，校验大小与 manifest；
3. 防止 Zip Slip、绝对路径、符号链接/设备文件、重复条目、超大归档和路径越界；
4. 解压后执行 `sage --version` 与最小表达式 smoke probe；
5. 通过版本目录和 current 指针原子切换，安装失败不能破坏正在使用的 Runtime；
6. 在 Settings/Project SDK 页面选择、切换、验证和移除 Runtime；
7. 对 Native、WSL、Docker/Podman、SSH/HPC 使用不同目标适配器，不能把远程容器镜像伪装成本地归档。

当前实现边界：

- `core:runtime`：JDK/Kotlin-only 的平台模型、Catalog、artifact 校验、下载和安全安装；
- `plugins:sage-core`：IntelliJ Settings、Run Configuration 和 Runtime 服务适配器；
- `product`：完整 IDE 默认 Runtime 管理入口、产品目录和发行策略。

统一运行时契约需要表达：

- 目标类型；
- 可执行入口；
- 工作目录；
- 文件映射；
- 参数与环境变量；
- 超时和最大输出；
- 中止/重启能力；
- 目标路径到本地路径的映射；
- Sage 版本、Python 版本、kernel 信息；
- 运行结果、诊断、退出码和 flag 命中。

`plugins/sage-core` 当前已有 Native/WSL/Docker 的运行配置和自动检测逻辑，见：

- `plugins/sage-core/src/main/kotlin/com/starnotesxj/sageide/run/SageAutoDetect.kt`
- `plugins/sage-core/src/main/kotlin/com/starnotesxj/sageide/run/SageCommandLineState.kt`
- `plugins/sage-core/src/main/kotlin/com/starnotesxj/sageide/run/SageRunConfiguration.kt`

这些类先保持平台适配层；新建的 `core:model` 只存放不依赖 IntelliJ 的协议和约束，逐步降低迁移沉默成本。

### 4.2 Sage 预解析双层模型

必须把用户源码和执行源码分开建模：

```text
原始 .sage 文本
   │
   ├── Sage Lexer / PSI / diagnostics
   │
   ├── preparse translation + source map
   │
   └── sage runtime / debugger / traceback
```

所有诊断、补全、跳转、重命名、断点和 traceback 都要优先回到原始 `.sage` 文件。任何只在生成 Python 文件上工作的实现，都必须有明确的 source-map 测试。

## 5. 迁移策略：降低插件到 IDE 的沉默成本

### 5.1 不复制重写，先保留可运行基线

现有插件仓库已经具有实际能力：

- 独立 Sage 文件类型和 Python 方言；
- generator sugar 解析；
- 隐式 `sage.all`；
- Sage 数字预解析类型；
- Sage/CTF postfix templates；
- Native/WSL/Docker 运行；
- Native/WSL 调试尝试；
- Sage 文件模板、图标、检查和测试。

这些实现随当前工作区复制到 `plugins/sage-core`，以此作为产品插件基线。不能在新产品仓库中另起炉灶实现相同功能。

### 5.2 立刻抽离平台无关契约

迁移顺序：

1. `core:model`：运行目标、CTF profile、执行限制、结果契约；
2. `core:runtime`：纯 JVM 的命令构造、路径映射和目标描述；
3. `plugins:sage-core`：IntelliJ action、run configuration、PSI、设置页；
4. `plugins:ctf-tools`：CTF UI 和工具 adapter；
5. `product`：品牌、默认插件集合、产品 build overlay。

原则：

- 平台无关模块不能 import `com.intellij.*`；
- `plugins:sage-core` 只负责把平台事件映射到 domain/runtime 契约；
- CTF 工具适配器不直接写入编辑器状态；
- 外部工具失败必须变成结构化诊断，而不是只打印日志。

### 5.3 Python 依赖的迁移门

当前插件明确依赖 Python 模块和 Python PSI：

- `plugins/sage-core/src/main/resources/META-INF/plugin.xml` 中声明 `com.intellij.modules.python`；
- `plugins/sage-core/build.gradle.kts` 需要 PythonCore/bundled Python plugin；
- 当前 Kotlin 源码有大量 `com.jetbrains.python.*` import。

因此，不能在第一天假设“换成社区平台后自动可用”。必须设置迁移门：

| 门 | 通过条件 |
|---|---|
| M0 | Sage core 在新的产品开发实例中加载，`.sage` 可打开 |
| M1 | Python Core/Python PSI 的模块依赖在目标产品中可解析 |
| M2 | generator sugar、隐式 namespace、`^/^^`、类型测试全绿 |
| M3 | Sage run/debug 和 Jupyter 在目标产品中可用 |
| M4 | 产品构建将 Python Core、Sage core 和 CTF 插件放入默认插件集合 |
| M5 | 不再依赖 PyCharm 专有实现，或依赖已形成书面支持矩阵 |

在 M5 之前，开发实例可以使用 PyCharm/Community-compatible base 进行快速验证，但文档和 CI 必须标明这只是开发基线，不是最终产品发行形态。

## 6. 里程碑计划

### P0：仓库和产品骨架（当前迭代）

**目标**：建立新产品主线，证明迁移不是重新开发插件。

交付物：

- 独立 Git 仓库；
- `plugins/sage-core` 迁移基线；
- `core:model` 平台无关模型；
- 产品定义、CTF 默认 profile 和构建接入文档；
- root Gradle 构建和基础测试；
- IntelliJ Community 外部 checkout 配置说明；
- CI 先构建核心插件/模型，产品构建作为显式可选 job。

验收：

- `gradlew build` 能完成核心模块编译和测试；
- `gradlew :plugins:sage-core:buildPlugin` 能产出插件 zip；
- 新仓库不修改 `sage-ide-support`；
- 当前插件 commit、未提交变更和迁移来源被记录。

### P1：独立产品开发实例

**目标**：从 PyCharm 插件开发转为产品插件开发。

工作项：

- 固定 IntelliJ Community 上游版本/commit；
- 建立 `product/community-overlay`；
- 定义产品 code、prefix、品牌资源、默认插件列表；
- 把 Sage core 放入产品开发实例的默认插件集合；
- 建立 `run-product` 和 `build-product` 脚本；
- 在 Windows、Linux、macOS 至少运行一次 smoke test；
- 验证 Python Core、Jupyter、Git、Terminal、Debugger 的产品依赖。

退出条件：

- 不通过 PyCharm 的安装目录启动 Sage 产品开发实例；
- 打开 `.sage`、运行 Sage、打开 CTF profile 的基本流程成功。

### P2：CTF MVP

**目标**：让 CTF 用户得到比普通 Python IDE 更短的解题路径。

工作项：

- Challenge Project Profile；
- flag pattern 和输出扫描；
- timeout/output limit；
- stdin、参数、环境变量和工作目录可复现；
- Crypto/Number Theory 工具窗口或 action；
- encoding/hash/XOR 快捷工具；
- solve run history；
- CTF 专用 Sage postfix/template 扩展；
- 可复制的 Sage/Python 代码片段输出。

验收场景：

1. 新建题目项目并选择 Crypto profile；
2. 运行 RSA/CRT/有限域 Sage 脚本；
3. 将题目输入文件作为 stdin 或路径传入；
4. 超时或输出过大时被安全终止；
5. 输出中出现 `flag{...}` 时显示结构化命中；
6. 执行记录包含 runtime、参数、退出码和结果摘要。

### P3：科学计算工作流

- Jupyter Sage kernel；
- 富输出、LaTeX、SVG/PNG、图形预览；
- 文档和示例搜索；
- doctest/test runner；
- Sage 环境锁定与可复现配置；
- WSL/Docker/SSH 运行目标；
- 断点和源映射改进。

### P4：逆向/取证集成

- ELF/PE/Mach-O 基础信息；
- PCAP 流、HTTP、DNS、凭据和文件对象入口；
- GDB/LLDB/pwndbg/gef 适配；
- Web 请求/响应记录；
- 二进制/网络工具的结果与题目 evidence 关联。

### P5：发行版和可选 Runtime

- Windows、macOS、Linux 安装包；
- JDK/JBR、签名、公证和自动更新；
- 默认 Sage runtime discovery；
- 可选 runtime bundle；
- SBOM、LICENSE、NOTICE、源码对应物；
- 离线安装、代理和镜像支持。

P5 之前不承诺“一键安装即包含 SageMath”。

## 7. 测试与质量门

### 7.1 单元与平台测试

- `core:model`：纯 JVM 单元测试，覆盖校验、默认值和序列化边界；
- Sage parser/type tests：沿用 `plugins/sage-core/src/test`；
- runtime command tests：Native/WSL/Docker/SSH 命令参数、转义和路径映射；
- source-map golden tests：原始 `.sage` 到 preparse Python 的位置映射；
- CTF profile tests：flag pattern、超时、输出上限和环境继承；
- 产品 smoke tests：打开项目、打开 `.sage`、运行、终止、输出窗口。

### 7.2 兼容矩阵

首个正式支持矩阵另行冻结；在此之前 CI 至少覆盖：

| 维度 | 初始目标 |
|---|---|
| JVM | JDK 25 |
| IntelliJ Platform | 一个固定上游 commit/发布版本 |
| OS | Windows、Linux、macOS |
| Windows Sage | WSL 优先，Native 标记实验性 |
| Runtime | Native Sage、WSL Sage、Docker Sage |
| Sage | 至少两个受支持版本 |
| Python | 与 Sage runtime 配套 |

### 7.3 安全质量门

Sage 和 CTF 项目会执行任意 Python/Cython/本地代码，因此产品必须：

- 明确工作区是可信代码边界；
- 执行前显示目标、目录和环境；
- 默认不设置自动执行 deadline（`null` 表示无限制），但默认设置输出上限；
- UI 必须明确显示“无限制”，并提供用户取消和可选有限 deadline；
- 对自动运行 notebook/外部 kernel 做显式提示；
- 不把 flag、题目输入或 secrets 写入遥测；
- 对远程/容器执行显示连接目标和挂载目录。

## 8. 许可证与发行决策

当前插件仓库是 GPL-3.0，并且 `NOTICE` 记录了 SageMath 图标 CC-BY-SA-4.0 与部分来源插件 Apache-2.0。新产品暂时继承现有开源方向，但产品构建前必须重新审计最终产物：

- IntelliJ Platform/community 模块；
- Python/Jupyter/Debugger 组件；
- JBR/JDK 和 native helper；
- SageMath 及所有 bundled runtime 依赖；
- 图标、模板、文档和第三方工具；
- 插件 zip、IDE 安装器、更新包和源码归档。

默认架构是 IDE 管理的外部 Sage Runtime：安装后可按需下载、校验、安装和切换，或由组织预置。若未来把 Sage Runtime 直接捆绑进发行版，仍必须完成 SBOM、许可证清单、源码对应物和法律审查；外部进程边界降低集成风险，但不自动消除再分发义务。

## 9. 当前迭代执行清单

- [x] 建立独立产品仓库目录；
- [x] 把插件源代码迁移到 `plugins/sage-core`；
- [ ] 建立 root Gradle 多模块构建；
- [ ] 建立 `core:model` 运行目标和 CTF profile；
- [ ] 记录迁移来源 commit 和已知 Python 依赖；
- [ ] 添加产品定义与默认 CTF profile；
- [ ] 添加 IntelliJ Community product overlay 占位；
- [ ] 添加开发/构建脚本；
- [ ] 运行核心模块测试和 Sage plugin build；
- [ ] 初始化 Git 并提交首个 Lore 格式决策记录；
- [ ] 下一迭代接入真实 Community product 开发实例。

## 10. 首个决策记录

- **为什么新建仓库**：现有插件仓库已经承担 Marketplace 发布、PyCharm 兼容矩阵和插件回归；直接把它改成独立产品会让发布、依赖和历史语义混在一起。
- **为什么先迁移插件而不是重写**：插件当前已经实现 Sage 语义、CTF postfix 和运行配置；重写会重新引入已解决的平台兼容问题。
- **为什么先采用外部进程 Runtime**：Sage 安装包含大量原生依赖，且官方安装路径存在平台差异；由 IDE 管理生命周期、由 Runtime 进程承载解释器，更容易支持 Native/WSL/Docker/远程目标并降低首版发行风险。
- **为什么先抽 `core:model`**：防止产品层、CTF 层和 IntelliJ action 直接耦合，降低以后从开发实例迁移到安装版的沉默成本。

## 11. 参考资料

- [JetBrains IntelliJ 平台开源页](https://www.jetbrains.com/zh-cn/opensource/intellij-platform/)
- [IntelliJ Platform SDK](https://plugins.jetbrains.com/docs/intellij/welcome.html)
- [The IntelliJ Platform](https://plugins.jetbrains.com/docs/intellij/intellij-platform.html)
- [Custom Language Support](https://plugins.jetbrains.com/docs/intellij/custom-language-support.html)
- [IntelliJ Platform Gradle Plugin](https://plugins.jetbrains.com/docs/intellij/tools-intellij-platform-gradle-plugin.html)
- [IntelliJ Platform tasks](https://plugins.jetbrains.com/docs/intellij/tools-intellij-platform-gradle-plugin-tasks.html)
- [JetBrains intellij-community README](https://github.com/JetBrains/intellij-community/blob/master/README.md)
- [SageMath 官方主页](https://www.sagemath.org/)
- [SageMath README](https://github.com/sagemath/sage/blob/develop/README.md)
- [Sage 安装指南](https://doc.sagemath.org/html/en/installation/index.html)
- [Launching SageMath](https://doc.sagemath.org/html/en/installation/launching.html)
- [Sage Developer Guide](https://doc.sagemath.org/html/en/developer/index.html)

> 本文是工程规划，不构成法律意见。所有许可证结论以最终构建产物和专业法律审查为准。

## Implementation links

- [Repository README](../README.md)
- [Migration map](MIGRATION-MAP.zh-CN.md)
- [Current status](STATUS.zh-CN.md)
- [Community product build notes](../product/README.zh-CN.md)
