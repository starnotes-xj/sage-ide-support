# SageMath CTF IDE 当前状态

## 当前阶段

P1 已完成主要 Community 产品接入与 Windows 双架构 hardened installer 验证；P2 CTF MVP 尚未实现。当前下一条核心产品主线是 SageMath 全量代码智能（API 索引、类型推断、补全和提示），Jupyter 降为后续可选兼容层。

**本轮状态同步（2026-08-22）**：已提交 `8e47fa8`，完成第一条可运行的数据驱动 Sage API 链路：版本化模型/normalizer、严格 JSON reader/loader、不可变 query、唯一 KNOWN factory return type、父类/别名成员闭包和矩阵成员补全消费。core 测试与 Sage Core Kotlin 编译通过；bundled index 仍是最小矩阵 slice，不代表全量 Sage 覆盖。

### 本轮文档结论：未完成项与优先级

**仍未完成的高影响事项：**

1. **真实 Sage API 生成链路**：尚未从真实 Sage Runtime、`sage-pycharm-stubgen`、签名和文档生成全量、版本绑定的 index；当前 bundled JSON 只是矩阵回归 slice。
2. **Sage IDE 智能闭环**：参数/文档提示、完整类型传播、项目/用户 stub 合并、跳转、source-map、重命名、诊断和 product-level completion/type integration tests 尚未完成。
3. **插件测试工具链**：`plugins:sage-core` 测试被本地 PyCharm module descriptor 的 `module/namespace` 字段解析错误阻塞，尚未获得真实 completion/type integration 证据。
4. **CTF MVP**：`plugins/ctf-tools`、Challenge Profile UI、flag 扫描、运行历史、evidence 和 Crypto/Encoding 工作区尚未实现。
5. **Runtime Manager 产品闭环**：Catalog、Settings/Project SDK adapter、切换/移除 UX、签名 Catalog、远程/WSL/Docker target-aware probe 尚未完成。
6. **发行门**：Authenticode、SPDX `NOASSERTION`/WIP/`GPL-2.0` 法律审批、Linux/macOS 包、真实 arm64 主机 smoke、自动更新尚未完成。

**下一步优先目标（已选定）：真实 Sage API index 生成流水线 + 可审计覆盖率报告。**

选择理由：它是当前最高杠杆、最贴合产品核心差异化且能直接解锁后续类型传播/补全/参数/文档功能的基础设施；相比继续添加单个 Kotlin 特例或提前做 CTF UI，它能一次性扩大可用 API 面，并验证“数据驱动而非函数特例”的架构是否成立。

下一阶段的可交付边界：

- 固定首个支持矩阵（Sage 版本、Python 版本、stubgen/runtime 来源）；
- 在 `tools/sage-api-index/` 建立可重复生成命令，输出 schema-validated JSON 和 coverage/diff report；
- 首先覆盖真实 `sage.all`、matrix、vector、polynomial、finite field、number theory、crypto 等高价值域；
- 为生成器写 fixture/golden/negative tests，并让 bundled index 由生成产物替换或明确标记为测试 fallback；
- 以至少一个真实 Runtime 生成 artifact 驱动 `plugins:sage-core` completion/type integration test；
- 保持 Unknown/Dynamic 安全边界，不在插件侧新增名称特例。

功能实现矩阵与 Community/Pro 边界见 [`FEATURE-STATUS.zh-CN.md`](FEATURE-STATUS.zh-CN.md)。

## 工程关系

最终目标只有一个 SageMath CTF IDE，但工程拆分为：

- `G:\Projects\sage-math-ctf-ide`：产品代码、SageMath Core、Runtime、overlay 和构建编排；
- `G:\Projects\intellij-community-sage-ide`：固定 SHA 的 IntelliJ/PyCharm Community 官方上游底座，只读、保持 clean；
- `G:\Projects\sage-ide-support`：独立旧插件仓库，不修改；
- `G:\Projects\intellij-community-sage-pr`：研究/PR checkout，不作为发行基线。

## 已完成

- 已确认完整产品主流程必须使用官方 Community Bazel/Bazelisk 与 installer，而不是 Gradle-only packaging；
- 已冻结官方 upstream：`b0001cd6c53979b384def7a1e3febe061e2ef687`；
- 已冻结 Bazelisk `1.29.0`、JetBrains Bazel `9.1.0-jb_20260505_126`、JDK 25、build number `263.SNAPSHOT`；
- 已成功构建 Sage Core ZIP：`plugins/sage-core/build/distributions/sage-core-0.1.0-dev.zip`；
- 已确认 PyCharm Community 已经内置 Python Core、HTML/XML、Git、Terminal、Markdown 等产品插件；SageMath Core 采用同一产品内置插件体验；
- 已创建独立 Sage product properties，复用 `PyCharmPropertiesBase`，定义 Sage 产品 code、launcher、应用描述、产品布局和外部插件注入；
- 已创建 staging-only 脚本：`prepare-upstream-staging.ps1`、`apply-overlay.ps1`、`stage-sage-plugin.ps1`、`repair-modules-xml.ps1`、`prune-missing-android-labels.ps1`、`verify-upstream-staging.ps1`、`build-upstream-staged.ps1`；
- 已创建 Sage 专用 Bazel dev target `//build:sage_math` 和 installer target `//python/build:sage_i_build_target` 的 staging 接入逻辑；
- 已确认官方 checkout 的中文用户目录会触发 Bazel/JDK 25 内部编码崩溃，构建脚本固定使用 ASCII `-Duser.home`、临时目录和 Bazel output root；
- 已确认上游 `.idea/modules.xml` 存在约 289 个失效生成 `.iml` 条目，且生成的 Bazel BUILD 还引用缺失 Android 源码树；staging 脚本只过滤这些明确缺失输入并记录 manifest，官方 checkout 保持 clean；
- 已通过 Gradle 9.6.0 + JDK 25 验证 core:model、core:runtime 测试与 Sage Core Kotlin 编译/插件打包。

## 当前仍需实现或验证

- `plugins/ctf-tools`、CTF Profile UI、flag 扫描、运行历史和 evidence 工作流；
- Runtime Manager Catalog、Settings/Project SDK adapter、切换/移除 UX 和签名 Catalog；
- Sage API 全量 index、类型传播、补全/参数/文档提示、source-map、doctest/test runner；Jupyter kernel 和富输出降为后续可选兼容层；
- PCAP、二进制、GDB/LLDB 和 Web evidence adapters；
- Linux/macOS 产品包、真实 arm64 主机 smoke、自动更新；
- Authenticode 签名和 SPDX/许可证法律审批；
- 远程 Sage Runtime catalog/probe。

Windows x64/aarch64 hardened installer、Sage Core bundled plugin、根级及 `license/` 法律文件、sidecar、x64 smoke 和 FinalCheck 已完成验证。

## 重要技术约束

1. 不修改 `G:\Projects\sage-ide-support`；
2. 不把完整 IntelliJ Community 源码复制进产品仓库；
3. 不在官方 checkout 直接应用或提交产品 overlay；
4. 不把 Sage Core ZIP 单独称为完整 IDE；
5. 直接运行上游 `//build:idea_community` 或原始 PyCharm installer 不会选择 Sage 产品，必须使用 staging 生成的 Sage target；
6. Runtime 是否捆绑进安装器必须等许可证/SBOM 审计后决定；
7. Pro 只能包含 Sage 自有商业代码或明确授权组件，不得复制 JetBrains Ultimate/PyCharm Professional 闭源模块。

## 已知阻塞与风险

- 上游生成 JPS metadata 与 checkout 文件快照不一致；当前只能通过 staging-only 明确过滤解决；
- `SageMathCommunityProperties` 当前是产品迁移阶段的源级 overlay，不是官方上游模块；
- Sage plugin descriptor 依赖 `com.intellij.modules.python`，必须在 PyCharm Community 产品布局中验证；
- 当前应用图标仍复用 PyCharm Community 资源路径，正式发行前必须提供 SageMath 自有品牌资源；
- 当前 product target 和 installer target 是 staging 动态注入，随上游 BUILD/registry 格式变化，需要固定 commit 校验；
- JDK/Bazel 外部依赖下载、Windows 长路径、磁盘空间和构建时间仍可能影响完整安装器验证。

## 下一轮验收

详细功能矩阵和 Community/Pro 边界见 [`FEATURE-STATUS.zh-CN.md`](FEATURE-STATUS.zh-CN.md)。

- `git -C G:\Projects\intellij-community-sage-ide status --porcelain` 为空；
- `product/upstream.lock.json` 与实际 HEAD、Bazel/JDK 版本一致；
- staging verify 通过且 filter manifest 可追溯；
- Sage-specific Bazel target 至少完成 analysis/query；
- Gradle 插件构建与现有 core 测试继续通过；
- 如资源允许，完成当前平台开发实例和 installer；否则保留完整失败日志和最小恢复步骤。
