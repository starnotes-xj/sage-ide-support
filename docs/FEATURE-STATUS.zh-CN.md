# 功能实现状态与版本边界

> 更新时间：2026-08-23（Runtime Manager 与 CTF 会话状态同步）。本文按代码、测试和最终构建证据整理；“实现会话完成”不等于主线整合、所有平台或最终发行均已验收。
>
> 产品首要目标已明确为 SageMath 全量代码智能：API 索引、类型推断、补全、参数/文档提示、跳转和 source-map；Jupyter 仅保留为后续可选兼容层。

> **2026-08-29 SageMath 智能增量**：Sage 10.9/Python 3.13 开发索引已达到 84,385 identities、84,491 raw AST declarations、2,843 source files。`plugins:sage-core` 已以数据驱动合同统一具体返回类型、参数绑定、成员补全和 Quick Documentation；具体 canonical active stub 才能进入最终 PSI 类型，基类只用于成员继承查找，UNKNOWN/DYNAMIC/歧义保持 fail-closed。新增 Python 数据模型协议、显式参数条件返回重载（DES/PRESENT 整数与 GF(2) 位向量、密钥调度列表元素）、CTF 位向量/二进制串/排列变换、长度/尺寸、S-box 列表、sub-key、Mini-AES 矩阵父对象 TypeVar、SR 工厂/矩阵/多项式系统、经典密码体制、LFSR 和 BooleanFunction 合同，以及既有原子 `OUTPUT:`/唯一 Sphinx class/唯一多词源类、有限域椭圆曲线、Integer、矩阵和 TypeVar 合同；只读审计显示 52,723 个可调用条目、52,299 signatures 中 UNKNOWN 为 30,895，较本轮起点 32,536 减少 1,641，CONCRETE 为 3,826、TYPE_VARIABLE 为 361。相对历史起点 45,126，UNKNOWN 累计减少 14,231（31.54%）。剩余 UNKNOWN 仍是源 stubgen 没有可证明返回合同的真实缺口，未把索引规模冒充全量精确语义。外部索引 query/harness 已通过，但 fresh PyCharm 编辑器 smoke、product-sidecar envelope/receipt 与最终 installer 验收仍未完成。

## 一、结论

设计文档描述的是完整产品路线，不是当前已完成清单。按当前设计范围划分：

- **已完成或有可运行基线：包含 Runtime Manager、CTF MVP/图形化 Math Lab 实现会话、Sage API scoped integration 和 Community 构建基线**；
- **部分实现、尚未形成完整产品闭环：主要是主线整合、产品 UI/真实端点、全量 Sage 智能和跨平台发行**；
- **发行硬化已完成构建验证，但签名和法律审批仍未完成**。

这里的“类/项”是按产品能力域统计，不是按函数或任务数量统计。旧的粗略数量口径已停止使用；当前以实现会话、主线整合、产品 UI/端点验收和发行门分别记录状态。按 P2–P5 的路线验收，P2 CTF MVP 与图形化 Math Lab 的实现会话已完成，主线整合与产品验收待完成。

## 二、已实现或已有可运行基线

| 能力域 | 当前状态 | 证据/范围 |
|---|---|---|
| Sage 文件与语言基线 | 部分实现 | `.sage` 文件类型、lexer/parser、`^/^^` 预解析相关分析、generator sugar、隐式 `sage.all`、类型 provider、postfix templates、检查和模板已有迁移基线；当前已增加数据驱动 factory return type 与 indexed member provider，但全量 API/type/document index、类型传播和覆盖率验收尚未完成。 |
| Sage 运行配置 | WSL Conda 命令层已验收，UI 端到端待验收 | Runtime Manager/Sage SDK 的 managed Runtime 与 Native/WSL/Docker/SSH target-aware 契约保留；WSL 现在支持显式 `/bin/bash`、Conda `shell.bash hook`、环境名 `sage` 和可选 conda executable，真实 Ubuntu WSL Sage 10.9/Python 3.13.15 smoke 通过；真实 Settings/Run UI click-flow 待完成。SSH/HPC 仍为 fail-closed transport backlog。 |
| Sage 调试入口 | 部分可运行 | Native/WSL 调试命令状态和 launcher 已存在；跨平台、source map、稳定调试验收仍未完成。 |
| CTF 执行模型 | 实现会话完成 | CTF 会话已补齐 project/challenge/profile、bounded execution、flag scanner、run history/evidence、Crypto/Encoding helpers、loopback CyberChef adapter、脚本完整性安全边界和图形化 Math Lab；主线整合与产品 smoke 待完成。 |
| Runtime 下载与安全安装 | 已实现基础 | HTTPS 下载、SHA-256、manifest、sidecar、ZIP 路径/条目安全检查、staging 清理、原子 current 指针、取消和输出限制已有实现/测试。 |
| Runtime probe | 已实现基础 | `sage --version` 和 `print(2+2)` probe 已有实现/测试；当前主要是本机 executable probe。 |
| Community 产品构建 | 已实现构建链 | Community overlay、Sage product properties、Sage Core bundled plugin、Windows x64/aarch64 installer 已生成并通过 x64 smoke。 |
| 发布硬化基础 | 已验证 | installer/uninstaller SHA-256/SHA-512 sidecar、Windows 根级及 `license/` 下 LICENSE/NOTICE、audit、x64 安装/启动/卸载和 FinalCheck 已验证。 |

## 三、已完成会话但主线/产品闭环待完成

1. **Runtime Manager 核心：已进入 `main`。** `a2c7fdc`（`让 Runtime Manager 统一拥有 Sage SDK 执行边界`）已提交 Runtime Manager/Sage SDK 集成；旧 Runtime 完成会话已物理清除，当前以 `main` 的 `a2c7fdc` 为唯一实现来源。仍需完成真实 Settings/Project SDK UI、并发/崩溃 fault-injection、真实端点和发布方公钥轮换验收。
2. **CTF MVP 与 Math Lab 实现会话：已完成，主线整合待完成。** 最新 `parallel/ctf-mvp`（tip `62847f0`；与 `integration/ctf-mvp` tip `742aa3d` 共享基础 MVP 内容但不是其 Git 后继）交付独立 `plugins/ctf-tools`、Challenge Project/Profile、flag scanner、bounded script execution、run history/evidence、Crypto/Encoding helpers、loopback CyberChef-server adapter 和图形化 CTF Math Lab；Math Lab 覆盖群/环/域、椭圆曲线、RSA、DH、DES 的专用表单、预检、运算追踪、可视化、教学步骤、脚本预览和本地化。最新 worktree 为 15 suites/51 tests、0 failures/errors；仍需整合到 `main`，完成默认插件/分发接入、live Node/CyberChef-server、Math Lab IDE live ToolWindow 和完整产品 smoke。
3. **Sage product 集成**：独立 Community 产品和 installer 已生成；跨平台开发实例、默认插件集合和产品依赖矩阵仍未完成。
4. **Sage 预解析双层模型**：已有 lexer/parser/分析基础，但 source-map、原始 `.sage` 到生成 Python 的诊断/跳转/重命名/断点闭环尚未完成。
5. **Sage 全量代码智能**：已形成 scoped 数据驱动链路和真实 Sage 10.9 sidecar/quality evidence；仍未完成全量 type engine、完整参数/文档/跳转/source-map 和 product-level completion/type integration。
6. **许可证/SBOM**：构建产物、SPDX、第三方库清单和根级法律文件已生成；当前 audit 仍有 warning，签名、`NOASSERTION`、WIP 和 `GPL-2.0` 审查未完成。
7. **跨平台发行**：Windows x64/aarch64 已构建；Linux/macOS installer、真实 arm64 主机 smoke 和自动更新/公证未完成。

## 四、尚未实现的设计能力

### Sage 代码智能与科学计算

- Sage API extractor/normalizer：已新增 Python 标准库 AST `.pyi`/`.py` 生成器、Kotlin generator 入口、稳定 index、canonical alias、严格 contract validation、可组合 source manifest、coverage/diagnostics/diff 和高价值域 fixture；bundled resource 已由 validated generated artifact 驱动，但尚未接入真实 Sage Runtime、`sage-pycharm-stubgen`、签名和文档批量输入；
- API 覆盖率、缺失符号、冲突、无签名和动态对象报告：生成器已支持 coverage ratio、missing、conflict、dynamic、withoutSignature 与 added/removed/changed diff；默认 gate 对 missing/conflict 返回 exit code 3，同时保留 index/coverage 审计产物；真实目标版本报告尚未生成；
- 全量模块/类/函数/方法/属性/构造器/常量补全；
- 基于接收者类型、parent 关系、方法链、构造器和常见运算的类型传播；
- 参数提示、重载匹配、文档提示、来源标签和版本提示；
- Sage stub、项目源码、用户 stub 和当前 Runtime 的统一索引；
- Sage source-map 对诊断、跳转、重命名、断点和 traceback 的完整支持；
- Sage doctest/test runner；
- `.py`、`.pyx` 与 `.sage` 混合项目的产品级验证；
- Sage SDK/Runtime 健康检查 UI、版本选择和项目 SDK 绑定。

### Jupyter 可选兼容层

- Jupyter Sage kernel、Notebook 导入/导出；
- 富输出、LaTeX、SVG/PNG 和图形预览；
- Jupyter completion 不作为 Sage 类型推断或补全的权威来源；
- 未实现 Jupyter 不得阻塞 Sage 原生编辑器、CTF MVP 或 Community 首版。

### CTF MVP（实现会话已完成，主线整合/产品验收待完成）

- 独立 `plugins/ctf-tools` 模块与 JetBrains Tool Window；
- Challenge Project/Profile、notes、payload、solve script 模型；
- flag regex/prefix scanner、stdout/stderr 结构化命中；
- bounded execution、timeout/output limit、取消与脚本 realpath/SHA-256 完整性边界；
- solve run history 与 REAL_RUNTIME/MOCK/NOT_EXECUTED evidence provenance；
- Crypto/Number Theory、encoding/hash/XOR helpers；
- 可选 loopback CyberChef-server Bake/Magic/Batch Bake adapter；
- 图形化 `CTF Math Lab` Tool Window：群/环/域、椭圆曲线、RSA、DH、DES 专用输入、预检、运算追踪、可视化、教学步骤、Sage/Python 脚本预览和中英文案；
- Math Lab 采用有界因数分解重试，并对不完整/无效输入保留显式诊断，不把本地预检冒充真实 Sage 运行。

最新实现会话测试证据：`parallel/ctf-mvp` worktree 为 15 suites/51 tests，skipped=0、failures=0、errors=0，`core:model:test`、`plugins:ctf-tools:test` 与 `buildPlugin` exit `0`；plugin ZIP required libraries audit 与 `git diff --check` 通过。CTF 当前分支仍位于独立 worktree，尚未自动宣称已整合到 `main`。

### 逆向、网络与取证

- ELF/PE/Mach-O 识别和元数据入口；
- PCAP 过滤、流/HTTP/DNS/凭据/文件对象提取；
- 常见编码、压缩、哈希和 XOR 工具入口；
- GDB/LLDB/pwndbg/gef 适配和远程调试；
- Web 请求/响应可复现记录；
- 工具结果与题目 evidence 的关联。

### Runtime 与发行能力（Runtime Manager 实现会话已完成）

- 已完成 signed Catalog、内置公钥验证、verified mirror/cache、版本 probe、生命周期选择/切换/移除/回滚和 SDK binding；
- 已完成 Native/WSL/Docker/SSH target-aware command/probe 与显式路径映射契约；
- 待完成真实 Settings/Project SDK UI、真实 WSL/Docker/SSH 端点、并发/崩溃 fault-injection 和发布方公钥轮换；
- Linux/macOS installer、自动更新、Windows/macOS 签名、公证；
- arm64 主机 smoke；
- Runtime bundle 是否随安装器提供的最终发行决策。

## 五、社区版与旗舰版边界

### Community Edition（当前已实现主线）

Community 版只能依赖开源的 IntelliJ/PyCharm Community 模块和 Sage 自有代码，当前范围是：

- Sage Core 语言、运行配置和基础调试入口；
- `core:model` 和 `core:runtime` 基础；
- Community product overlay、Python Core/Debugger 等已确认可用的开源模块；Jupyter/Notebook 仅作为后续可选兼容层；
- CTF MVP 实现会话已完成但尚未进入 `main`；Runtime Manager 核心已由 `a2c7fdc` 进入 Community 主线；产品/分发接入和平台验收仍按独立门推进；
- Windows x64/aarch64 installer 硬化链已打通。

### Pro/旗舰版（尚未实现）

当前没有已实现的旗舰版专有功能，也没有复制 JetBrains Ultimate/PyCharm Professional 闭源模块。`SageMathProProperties` 只保留了产品身份扩展点，不代表 Pro 产品完成。

未来旗舰版只能增加 Sage 自有商业代码或明确授权组件，例如：

- 企业 Runtime Catalog、签名策略和组织策略；
- 远程/HPC/集群 Sage Runtime 管理；
- 团队题目、证据和私有 artifact 协作；
- 高级 CTF/逆向/取证 adapter；
- 企业代理、镜像、审计和支持矩阵。

这些功能目前均未实现，不得在产品宣传或发行说明中写成已交付。Community 与 Pro 的技术边界已在原则上分清，但 Pro 的功能清单、授权模型、构建 target、UI 和验收矩阵仍需另行设计。

## 六、数量口径

- Runtime Manager 核心已由 `a2c7fdc` 进入 `main`；CTF MVP/图形化 Math Lab 仍未合入；二者都不等同于完整产品 UI/端点或正式发行。
- 按设计文档的 P 阶段：P0 基础骨架大部分完成；P1 产品构建已打通但跨平台/依赖矩阵仍未闭环；P2 CTF MVP/图形化 Math Lab 实现会话完成、主线整合待完成；P3 Sage 代码智能主线尚未完成，Jupyter 为可选后续层。
- 这些是工程状态口径，不是代码覆盖率，也不是精确百分比。

## 七、建议实现顺序

1. 保持 Sage/Python 支持版本、API extractor、版本化 index、sidecar、coverage 和独立 quality gate；
2. 完成 Runtime Manager 的 UI/端点/fault-injection 验收，并受控整合最新 `parallel/ctf-mvp` 到 `main`；`integration/ctf-mvp` 仅作为安全审计参考，不作为第二个合并来源，保留各自测试和安全边界；
3. 验收真实 IntelliJ Settings/Project SDK UI、WSL/Docker/SSH 端点、并发/崩溃 fault-injection，以及 live CyberChef-server/完整产品 smoke；
4. 实现统一的 Sage 类型传播、补全、参数/文档提示、跳转和 source-map 验收；
5. 补 doctest、PCAP/二进制/GDB/LLDB，最后再处理可选 Jupyter、签名、法律审批、自动更新、Linux/macOS 和 Pro 产品线。

## 参考文档

- [产品开发计划](IDE-PLAN.zh-CN.md)
- [迁移地图](MIGRATION-MAP.zh-CN.md)
- [当前状态](STATUS.zh-CN.md)
- [Community 产品构建说明](../product/README.zh-CN.md)
- [交接文档](../HANDOFF.md)
