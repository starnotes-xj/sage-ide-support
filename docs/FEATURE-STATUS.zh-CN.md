# 功能实现状态与版本边界

> 更新时间：2026-08-22（本轮文档同步）。本文按代码、测试和最终构建证据整理；“已实现”不等于所有平台都已验收。
>
> 产品首要目标已明确为 SageMath 全量代码智能：API 索引、类型推断、补全、参数/文档提示、跳转和 source-map；Jupyter 仅保留为后续可选兼容层。

## 一、结论

设计文档描述的是完整产品路线，不是当前已完成清单。按当前设计范围划分：

- **已实现或有可运行基线：约 7 类能力**；
- **部分实现、尚未形成完整产品闭环：约 9 类能力**；
- **尚未实现：约 14 类能力**；
- **发行硬化已完成构建验证，但签名和法律审批仍未完成：约 4 项发布门**。

这里的“类/项”是按产品能力域统计，不是按函数或任务数量统计。设计文档没有给出可精确计算的功能总数，因此不把这些数字解释成精确百分比。若按 P2–P5 的路线验收，当前仍处于 **P1 产品接入/构建已打通，P2 CTF MVP 尚未完成**。

## 二、已实现或已有可运行基线

| 能力域 | 当前状态 | 证据/范围 |
|---|---|---|
| Sage 文件与语言基线 | 部分实现 | `.sage` 文件类型、lexer/parser、`^/^^` 预解析相关分析、generator sugar、隐式 `sage.all`、类型 provider、postfix templates、检查和模板已有迁移基线；当前已增加数据驱动 factory return type 与 indexed member provider，但全量 API/type/document index、类型传播和覆盖率验收尚未完成。 |
| Sage 运行配置 | 部分可运行 | Native/WSL/Docker 运行配置、参数、工作目录、自动检测和当前文件运行已存在；WSL/Docker 主要是命令适配与发现，不等于完整 Runtime Manager。 |
| Sage 调试入口 | 部分可运行 | Native/WSL 调试命令状态和 launcher 已存在；跨平台、source map、稳定调试验收仍未完成。 |
| CTF 执行模型 | 已实现基础 | `CtfProjectProfile`、执行目标、stdin/参数/环境/工作目录、flag pattern、可选 timeout、输出上限和 `ExecutionResult` 已有纯 JVM 模型/测试。 |
| Runtime 下载与安全安装 | 已实现基础 | HTTPS 下载、SHA-256、manifest、sidecar、ZIP 路径/条目安全检查、staging 清理、原子 current 指针、取消和输出限制已有实现/测试。 |
| Runtime probe | 已实现基础 | `sage --version` 和 `print(2+2)` probe 已有实现/测试；当前主要是本机 executable probe。 |
| Community 产品构建 | 已实现构建链 | Community overlay、Sage product properties、Sage Core bundled plugin、Windows x64/aarch64 installer 已生成并通过 x64 smoke。 |
| 发布硬化基础 | 已验证 | installer/uninstaller SHA-256/SHA-512 sidecar、Windows 根级及 `license/` 下 LICENSE/NOTICE、audit、x64 安装/启动/卸载和 FinalCheck 已验证。 |

## 三、部分实现但尚未闭环

1. **Sage Runtime Manager**：有 runtime model、下载、安装、验证、probe 和 Sage 服务，但没有完整 IDE Catalog UI、Settings/Project SDK 管理页面、移除/切换 UX、持久化 catalog 和正式 IntelliJ adapter。
2. **Native/WSL/Docker 目标**：Native probe 可用；WSL/Docker 已有发现和命令运行路径，但 target-aware probe、统一诊断、路径映射测试和完整取消/重启语义仍不完整。
3. **Sage product 集成**：独立 Community 产品和 installer 已生成；但仍依赖 Community/PyCharm Python Core 相关能力，跨平台开发实例和产品依赖矩阵未完成。
4. **CTF Profile**：领域模型存在，但没有 Challenge Project/Profile 的完整 IDE UI、持久化项目结构、运行历史、flag 命中展示和 evidence 管理。
5. **运行结果记录**：stdout/stderr/退出码/耗时等底层结果契约存在；没有完整的 solve run history、结果摘要和可追溯题目 evidence 工作流。
6. **Sage 预解析双层模型**：已有 lexer/parser/分析基础，但 source-map、原始 `.sage` 到生成 Python 的诊断/跳转/重命名/断点闭环尚未完成。
7. **Sage 全量代码智能**：已形成第一条可运行的数据驱动链路：`core:sage-api` 提供版本化模型、normalizer、稳定 JSON、严格 reader/loader、不可变 query；`plugins:sage-core` 消费 bundled/external index，支持唯一 KNOWN factory return type、矩阵成员补全、父类/别名闭包和 Unknown/Dynamic 拒绝，并已有 core 回归测试及 plugin Kotlin 编译证据。仍未完成真实 Sage Runtime/`sage-pycharm-stubgen` 全量生成、覆盖率报告、参数/文档/跳转/source-map、plugin completion/type integration tests（受本地 module descriptor 解析阻塞）和完整 type engine。
8. **许可证/SBOM**：构建产物、SPDX、第三方库清单和根级法律文件已生成；当前 audit 仍有 8 个 warning，签名、`NOASSERTION`、WIP 和 `GPL-2.0` 审查未完成。
9. **跨平台发行**：Windows x64/aarch64 已构建；Linux/macOS installer、真实 arm64 主机 smoke 和自动更新/公证未完成。

## 四、尚未实现的设计能力

### Sage 代码智能与科学计算

- Sage API extractor/normalizer：从 Sage Runtime、`sage-pycharm-stubgen`、签名和文档生成版本化索引；
- API 覆盖率、缺失符号、冲突、无签名和动态对象报告；
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

### CTF MVP

- 独立 `plugins/ctf-tools` 模块（当前仓库没有该模块）；
- Crypto/Number Theory 工具窗口或 action；
- encoding/hash/XOR 快捷工具；
- Challenge Project Profile 创建/编辑 UI；
- flag 正则/前缀扫描和结构化命中展示；
- solve run history；
- 题目 notes、payload、solve 脚本和 evidence 关联；
- RSA 低指数/共模/广播/Wiener/共因子等工作区；
- 有限域、椭圆曲线、continued fraction、CRT、Pell/Diophantine 辅助 UI；
- bytes/int/hex/base64/URL/整数序列转换工具；
- 可复制 Sage/Python 代码片段输出。

### 逆向、网络与取证

- ELF/PE/Mach-O 识别和元数据入口；
- PCAP 过滤、流/HTTP/DNS/凭据/文件对象提取；
- 常见编码、压缩、哈希和 XOR 工具入口；
- GDB/LLDB/pwndbg/gef 适配和远程调试；
- Web 请求/响应可复现记录；
- 工具结果与题目 evidence 的关联。

### Runtime 与发行能力

- 受信任 HTTPS Runtime Catalog 的实际数据源、签名和 UI；
- Settings/Project SDK 页面中的 Runtime 选择、切换、验证、移除；
- Conda、SSH/HPC、Docker/Podman 的独立 Runtime adapter；
- 远程 kernel、文件映射和目标诊断；
- Runtime 离线缓存、代理、镜像和失败回滚 UX；
- JSON Catalog 签名、内置公钥验证和版本 probe 的产品接入；
- Linux/macOS installer、自动更新、Windows/macOS 签名、公证；
- arm64 主机 smoke；
- Runtime bundle 是否随安装器提供的最终发行决策。

## 五、社区版与旗舰版边界

### Community Edition（当前已实现主线）

Community 版只能依赖开源的 IntelliJ/PyCharm Community 模块和 Sage 自有代码，当前范围是：

- Sage Core 语言、运行配置和基础调试入口；
- `core:model` 和 `core:runtime` 基础；
- Community product overlay、Python Core/Debugger 等已确认可用的开源模块；Jupyter/Notebook 仅作为后续可选兼容层；
- CTF MVP、Runtime Manager、CTF 工具和发行能力应优先在 Community 版实现；
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

- 按产品能力域：约 7 类已有实现/基线、约 9 类部分实现、约 14 类尚未实现，另有约 4 项发行门未完成；Sage 全量代码智能从“语言基线”中单独列为部分实现。
- 按设计文档的 P 阶段：P0 基础骨架大部分完成；P1 产品构建已打通但跨平台/依赖矩阵仍未闭环；P2 CTF MVP 尚未完成；P3 的 Sage 代码智能主线尚未完成，Jupyter 为可选后续层。
- 这些是工程规划统计，不是代码覆盖率，也不是精确百分比。

## 七、建议实现顺序

1. 先冻结支持的 Sage/Python 版本，并实现 API extractor、版本化 index、覆盖率报告和增量更新；
2. 实现统一的 Sage 类型传播、补全、参数/文档提示、跳转和 source-map 验收；
3. 完成 Runtime Manager 的 Catalog、Settings/Project SDK adapter 和 Native/WSL/Docker 统一验证；
4. 再实现 `plugins/ctf-tools`，交付 CTF Profile UI、flag 扫描、运行历史和 Crypto/Encoding MVP；
5. 补 doctest、PCAP/二进制/GDB/LLDB，最后再处理可选 Jupyter、签名、法律审批、自动更新、Linux/macOS 和 Pro 产品线。

## 参考文档

- [产品开发计划](IDE-PLAN.zh-CN.md)
- [迁移地图](MIGRATION-MAP.zh-CN.md)
- [当前状态](STATUS.zh-CN.md)
- [Community 产品构建说明](../product/README.zh-CN.md)
- [交接文档](../HANDOFF.md)
