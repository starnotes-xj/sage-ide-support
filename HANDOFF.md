# SageMath CTF IDE 交接快照

> 更新时间：2026-08-23。本文只保留当前状态、可复核证据、剩余风险和下一步；历史失败过程不在此重复记录。

## 1. 总体状态

项目定位：基于 IntelliJ Community 的独立 SageMath CTF IDE。核心差异化是 **SageMath 代码智能 + 可管理 Sage Runtime + CTF 工作台**，不是把插件 ZIP 或普通 PyCharm 安装目录冒充完整产品。

当前判断：

- **P1 Community 产品接入/Windows 构建链：已完成开发基线，尚未完成最终发行门。** Community overlay、Sage product properties、Sage Core bundled plugin、Windows x64/aarch64 installer、sidecar、法律文件 overlay、x64 安装/启动/卸载 smoke 和 FinalCheck 都有历史验证证据。
- **Sage API 智能：基础链路已运行，尚未完成产品闭环。** 已有版本化模型、Python stdlib AST generator、validated loader/query、factory return type 和矩阵成员补全；真实 Sage 10.9 stubgen 已完成可审计导入，但 bundled index 尚未替换为真实全量 artifact。
- **P2 CTF MVP：尚未完成。** CTF tools、Challenge Profile UI、运行历史、flag/evidence 工作流仍待实现。
- **Runtime Manager：基础能力存在，产品 UI/adapter 闭环未完成。**
- **发行：Windows 构建链已验证，但不能称为正式 release。** 签名、法律审批、Linux/macOS、真实 arm64 主机 smoke 和自动更新仍未完成。

不能用一个精确百分比描述总体进度。按能力域的当前粗略口径：约 7 类已有实现/基线、约 9 类部分实现、约 14 类尚未实现，另有约 4 项发行门未完成；这些不是代码覆盖率。

## 2. 已完成或已有可复核基线

### 产品与构建

- 产品仓库：`G:\Projects\sage-math-ctf-ide`。
- 官方 IntelliJ Community 底座：`G:\Projects\intellij-community-sage-ide`，固定 commit `b0001cd6c53979b384def7a1e3febe061e2ef687`，只读并要求 clean。
- Staging 构建使用 JDK 25、Bazelisk `1.29.0`、JetBrains Bazel `9.1.0-jb_20260505_126`、build `263.SNAPSHOT`。
- 已有 Sage 专用 Bazel dev/installer target、Community product properties、外部 Sage Core 插件注入和 Windows 双架构构建链。
- 历史 hardened 产物和证据见：
  - `G:\sage-build\bundled-next\release-hardening-legal-fix-final.log`
  - `G:\sage-build\bundled-next\release-hardening-audit-legal-fix-all.json`
  - `G:\sage-build\bundled-next\x64-installer-smoke-legal-fix.log`
  - `G:\sage-build\bundled-next\finalcheck-legal-fix.log`

### Sage API intelligence

- `core:sage-api`：版本化 schema/domain model、normalizer、严格 JSON reader/loader、不可变 query、source/alias/parent/conflict 处理。
- `plugins:sage-core`：消费 bundled/external index；已验证唯一 KNOWN factory return type、父类/别名成员闭包和矩阵成员查询；没有 `solve_right` 名称特例。
- `tools/sage-api-index/generate.py`：Python 标准库 `.pyi`/`.py` extractor，支持稳定 index、source digest、coverage、diagnostics、diff 和 gate。
- 当前 checked-in bundled index 仍是有限 fixture/矩阵 slice，不代表 Sage 全量覆盖。

### 真实 Sage 10.9 artifact 导入

真实 Sage 10.9 artifact 证据基线提交：`1e1ba42 Make Sage 10.9 importer coverage evidence auditable`。

人工维护 contract：`tools/sage-api-index/expected-sage-10.9.json`，绑定：

- artifact `wsl-ubuntu-sage-10.9-stubgen-0.8.3`；
- Sage `10.9`、Python `3.13`/实际 `3.13.15`；
- `sage-pycharm-stubgen 0.8.3`、`STUBGEN` provenance；
- probeDigest `44945e3f...`；treeDigest `69d0524a...`；expectedDigest `58be9132...`。

两次默认 LIVE full import 均 exit `0`，分别输出到 ignored：

- `build/sage-api-real/live-1`
- `build/sage-api-real/live-2`

两次结果的 artifact/runtime/probe/tree/report/file/expected/coverage 摘要一致：

- stub files `2839`；generation report `discovered/generated=2837/2837`、`failed=0`；
- expected `6/6` 命中，`coverage.scope=SCOPED`、ratio `1.0`、missing `0`；
- fresh generator recheck 重建 `84159` entries、`24` diagnostics，`conflicts=0`、`isComplete=true`；`24` 条为 duplicate diagnostics，不是冲突；这不是全 API 覆盖证明。

显式 replay 结果：`build/sage-api-real/replay-scoped`，`probeMode=REPLAY`，probeDigest 与 LIVE 相同。Replay 只用于本机恢复/调试；probeDigest 是 canonical consistency digest，不是签名、来源真实性证明或 release attestation。

## 3. 当前剩余工作

### 最高优先级：Sage 全量代码智能

1. 将已完成 conflict-free 的真实 Sage 10.9 artifact 继续处理为可消费的版本化 API/type/document index；扩大人工 expected 集合并定义真实覆盖门。
2. 接入签名和文档来源，补全参数提示、文档提示、跳转、source-map、重命名和诊断。
3. 实现通用类型传播：factory/constructor、方法链、parent/mixin/category、运算结果和 Unknown/Dynamic 安全边界。
4. 解开 `plugins:sage-core` test classpath 的本地 PyCharm module descriptor `module/namespace` 解析阻塞，取得真实 completion/type integration test 证据。
5. 做项目/用户 stub 合并、增量索引、版本 diff 和 generated/bundled drift 检查。

### Runtime 与 CTF

- Runtime Manager Catalog、Settings/Project SDK adapter、切换/移除 UX、签名 Catalog、Native/WSL/Docker target-aware probe。
- `plugins/ctf-tools`、Challenge Profile UI、flag 扫描、运行历史、evidence 管理、Crypto/Encoding MVP，之后再扩展 PCAP/二进制/GDB/LLDB/Web adapters。
- Jupyter 继续作为可选执行/兼容层，不作为 Sage 原生编辑体验的前置条件。

### 发行与跨平台

- Authenticode/正式签名服务。
- SPDX `NOASSERTION`、`SPDX_WORK_IN_PROGRESS`、deprecated `GPL-2.0` 的法律审查。
- Linux/macOS 产品包、真实 arm64 主机 smoke、自动更新/公证。
- 远程 Sage Runtime catalog/probe。

## 4. 发行证据与已知风险

历史 hardened audit：`errors=0`、`warnings=8`、`passed=false`。已验证 sidecar、SPDX JSON 可解析、法律文件存在和 x64 smoke；但 4 个 EXE 未签名、SPDX 仍有 WIP/NOASSERTION、存在 deprecated `GPL-2.0` 法律事项。因此不能称为正式 release-ready。

已验证代码基线包含 `1e1ba42` 的 importer slice 与本轮 conflicts diagnostic slice；`.agent-teams/` 是本地协作归档，不应提交。

## 5. 仓库与实现边界

- 允许修改：`G:\Projects\sage-math-ctf-ide` 和 `G:\sage-build\staging-build6`。
- 不修改：`G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr`、官方 `G:\Projects\intellij-community-sage-ide`。
- 不手工修改生成的 installer、SPDX、distribution 或 ignored build artifact 来伪造证据。
- Runtime/Sage 解释器保持在 JVM 外部进程；IDE 负责发现、下载、校验、安装、选择、切换和回滚。
- SageMath 按“Python 的超集”描述；除非有完整迁移计划，不把 Sage 改成脱离 Python PSI 的完全独立语言。

## 6. 最近切片验证

- `python -m unittest tools.sage-api-index.test_import_wsl_artifact tools.sage-api-index.test_generate`：51 tests，exit `0`；新增 overload implementation fallback、decorator alias、Literal 域和五个真实冲突形状回归。
- `python -m py_compile tools/sage-api-index/import_wsl_artifact.py tools/sage-api-index/test_import_wsl_artifact.py tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`：exit `0`。
- `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`：`BUILD SUCCESSFUL`。
- 两次默认 LIVE full：exit `0`，deterministic fields 一致。
- 显式 replay scoped import：exit `0`，`REPLAY` 边界可审计。
- `git diff --check`：exit `0`。
- 本轮 conflict 诊断保留原 Dynamic merge 与 fail-closed gate，新增 deterministic `sourceDigest`/`sourceDigests`、声明计数、distinct signature 计数和排序后的 `signatureKeys`；fresh Sage 10.9 recheck 重建 `84159` entries/`24` diagnostics，`conflicts=0`、`isComplete=true`，24 条均为 duplicate diagnostics。
- core normalizer 红测首次运行 `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain` 真实 exit `1`：25 tests 中 5 个新增 overload 规则测试失败，暴露旧实现只按参数名分组，未能区分可证明不相交类型，也未能对 Unknown、Literal/宽类型和歧义 arity fail closed；记录此失败后再修复。
- 首次实现通用 predicate 后 core 测试仍真实 exit `1`：25 tests 中已有基线 `normalizerBuildsVersionedIndexFromRuntimeSources` 与 `extractorParsesClassesMethodsPropertiesAliasesAndOverloads` 失败，说明规则过窄/改变了既有 overload 兼容行为；新增测试未失败。已记录，先恢复既有行为，再收紧仅针对真实冲突的安全判定。

## 7. 下一步

下一切片优先做 **conflict-free Sage 10.9 artifact 的可消费 index 质量门**：扩大人工 expected contract、补全参数/文档 provenance，并保持 Unknown/Dynamic 与未证明域重叠的 fail-closed 规则；不得为单个函数增加 Kotlin 特例，不得直接把 84159 entries 的 ignored index 当作 bundled/release artifact。完成后重新运行与本阶段相关的 core/plugin 测试；若进入产品发布阶段，必须另行执行 fresh product build、x64/arm64 smoke、release audit 和 `verify-upstream-staging.ps1 -FinalCheck`。

## 8. 参考

- [`README.md`](README.md)
- [`docs/STATUS.zh-CN.md`](docs/STATUS.zh-CN.md)
- [`docs/FEATURE-STATUS.zh-CN.md`](docs/FEATURE-STATUS.zh-CN.md)
- [`docs/IDE-PLAN.zh-CN.md`](docs/IDE-PLAN.zh-CN.md)
- [`product/README.zh-CN.md`](product/README.zh-CN.md)
- [JetBrains MPS](https://github.com/JetBrains/MPS)：DSL/模型化 IDE 参考，不是本项目运行时底座。
- [JetBrainsRuntime](https://github.com/JetBrains/JetBrainsRuntime)：JetBrains JDK 参考，影响构建/运行时，不提供 Sage API 智能。
