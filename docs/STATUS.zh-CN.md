# SageMath CTF IDE 当前状态

## 当前阶段

P1 已完成主要 Community 产品接入与 Windows 双架构 hardened installer 验证；Runtime Manager 核心已由 `a2c7fdc` 进入 main，CTF MVP/图形化 Math Lab 实现会话已完成，当前 CTF 主线整合与 Runtime/CTF 产品级端点/UI 验收按独立边界推进。下一条核心产品主线是 SageMath 全量代码智能（API 索引、类型推断、补全和提示），Jupyter 降为后续可选兼容层。

**SageMath 智能主线状态（2026-08-28）**：已完成 Sage 10.9/Python 3.13 的开发索引与严格具体返回合同链路：当前 index 为 84,304 个 identity、84,367 个原始 AST 声明、2,843 个源文件；类型 provider 按调用参数筛选唯一合同并物化 canonical active Sage `.pyi` 类型，基类只参与继承成员查找；`.sage` 隐式 `sage.all`、显式 Sage 模块、参数提示、Quick Documentation、链式返回和 UNKNOWN/DYNAMIC fail-closed 均有回归。新增安全语言协议、原子文档输出/唯一 class 合同、唯一多词源类合同、稳定 Python 容器合同、CTF crypto 工具合同、有限域椭圆曲线合同、Integer 运算合同、矩阵同父/切片/条件分支合同、有限域父对象元素合同及 `gcd`/`lcm`/阶乘 TypeVar 合同；合同质量审计（52,723 个可调用条目）显示 UNKNOWN 为 32,536，较本阶段 32,563 再减少 27，CONCRETE 为 3,681、TYPE_VARIABLE 为 236；相对历史起点 45,126，UNKNOWN 累计减少 12,590（27.89%），未把宽泛类型当作具体 Sage 类型。`SageApiIndexServiceTest` 与 `SageIntelligenceHarnessTest` 的外部索引代表性门禁已通过；当前仍缺 fresh PyCharm 安装后的编辑器 completion/停止分析 smoke，以及带 envelope/receipt 的 product-sidecar 验证。

**本轮状态同步（2026-08-23）**：Sage API 已完成 scoped sidecar/envelope 与独立 quality gate；真实 Sage 10.9 fresh LIVE imports 两次均 exit `0`，84159 entries、coverage `6/6`、`conflicts=0`，normalized artifacts 字节一致。Runtime Manager 核心提交 `a2c7fdc` 已进入 main；Runtime 核心交付签名 Catalog、已验证 mirror/cache、生命周期回滚、Settings/Project SDK binding、Native/WSL/Docker/SSH target-aware command/probe 与路径映射；旧完成会话删除前的 worktree fresh `:core:runtime:test -PrunRuntimeTests=true` 为 38 tests、0 failures/errors。CTF 实现会话最新位于 `parallel/ctf-mvp`（tip `62847f0`；与 `integration/ctf-mvp` tip `742aa3d` 共享基础 MVP 内容但不是其 Git 后继），交付独立 `plugins/ctf-tools`、challenge/profile/run history/evidence、flag scanner、Crypto/Encoding helpers、loopback CyberChef adapter、安全脚本执行和图形化 CTF Math Lab；Math Lab 覆盖群/环/域、椭圆曲线、RSA、DH、DES 的专用表单、预检、运算追踪、可视化、教学步骤和本地化。最新 worktree fresh `:core:model:test :plugins:ctf-tools:test :plugins:ctf-tools:buildPlugin -PrunModelTests=true -PrunCtfToolsTests=true` 为 `BUILD SUCCESSFUL`、15 suites/51 tests、0 failures/errors、exit `0`，plugin ZIP required libraries audit 通过。Runtime Manager 已由 `a2c7fdc` 进入 `main`；CTF 会话仍在独立 worktree，未宣称已合入 `main`。

### 本轮文档结论：未完成项与优先级

**仍未完成的高影响事项：**

1. **真实 Sage API 生成链路**：尚未从真实 Sage Runtime、`sage-pycharm-stubgen`、签名和文档生成全量、版本绑定的 index；当前 bundled JSON 只是矩阵回归 slice。
2. **Sage IDE 智能闭环**：参数/文档提示、完整类型传播、项目/用户 stub 合并、跳转、source-map、重命名、诊断和 product-level completion/type integration tests 尚未完成。
3. **插件测试工具链**：`plugins:sage-core` 的现有 completion/type 证据已恢复可运行，但真实 Sage 全量 index 驱动的 product-level completion/type integration 仍未完成。
4. **Runtime Manager 产品验收**：核心已由 `a2c7fdc` 进入 `main`；仍需完成真实 IntelliJ Settings/Project SDK UI、并发/崩溃 fault-injection 与真实 WSL/Docker/SSH 端点验收。
5. **CTF MVP/Math Lab 主线整合与产品验收**：实现会话已完成；仍需将独立 worktree 的 `plugins/ctf-tools`、Math Lab UI/model 与 `core:model` 扩展按受控范围整合到 `main`，再完成全产品默认插件/分发接入；live Node/CyberChef-server、Math Lab IDE live ToolWindow 和完整产品 smoke 仍未验证。
6. **发行门**：Authenticode、SPDX `NOASSERTION`/WIP/`GPL-2.0` 法律审批、Linux/macOS 包、真实 arm64 主机 smoke、自动更新尚未完成。

**当前正在推进的高价值目标：保持 scoped Sage API index 质量门，完成 Runtime Manager 产品验收，并受控整合 CTF/Math Lab。** Sage API 生成、sidecar/envelope、coverage 和独立 quality gate 已有真实 10.9 evidence；Runtime Manager 核心已由 `a2c7fdc` 进入 `main`，但其 UI/端点/fault-injection 仍需验收；最新 CTF MVP/图形化 Math Lab 仍在隔离 worktree，下一步是逐项审阅差异后整合到 `main`，而不是把分支绿测直接当作主线 product/release 证据。

选择理由：Sage API 质量门仍是核心差异化的最高杠杆；Runtime Manager 与 CTF/Math Lab 会话已各自完成实现，受控整合可以把已验证的运行时/解题/教学工作台能力带入主线，同时避免把独立 worktree 的局部证据夸大为完整产品或发行完成。

下一阶段的可交付边界：

- 保持首个支持矩阵（Sage 版本、Python 版本、stubgen/runtime 来源）与 sidecar/envelope provenance；
- 保持 `tools/sage-api-index/` 的 schema-validated JSON、coverage/diff、独立 quality gate 和 no-`--allow-conflicts` 生成门；
- Runtime Manager 核心已由 `a2c7fdc` 进入 `main`；只需继续补 Runtime 产品 UI/端点/fault-injection 验收；后续受控整合最新 `parallel/ctf-mvp`，`integration/ctf-mvp` 仅作为安全审计参考，不作为第二个合并来源；
- 完成真实 IntelliJ Settings/Project SDK UI、WSL/Docker/SSH 端点、并发/崩溃 fault-injection、live CyberChef-server 和完整产品 smoke；
- 首先覆盖真实 `sage.all`、matrix、vector、polynomial、finite field、number theory、crypto 等高价值域并推进全量 Sage 智能验收；
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

- 将最新 `parallel/ctf-mvp` 按受控范围整合到已包含 Runtime Manager 核心的 `main`；对 `integration/ctf-mvp` 只做安全契约对照，不整体合并；
- 真实 IntelliJ Settings/Project SDK UI、WSL/Docker/SSH 端点、并发/崩溃 fault-injection，以及 live CyberChef-server、Math Lab IDE live ToolWindow 和完整产品 smoke 验收；
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
