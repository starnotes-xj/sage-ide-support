# SageMath CTF IDE 交接说明

> 工作区：`G:\Projects\sage-math-ctf-ide`
> 目标：先完成 SageMath 编辑器智能（类型、补全、文档、语法糖和运行入口），CTF/Notebook 产品功能暂不扩展。
> 更新：2026-08-28

## 1. 不可违反的边界

- 只修改本工作区和 `G:\sage-build\staging-build6`；不得修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr`。
- 官方基线是 `G:\Projects\intellij-community-sage-ide`，规则要求 SHA `b0001cd6c53979b384cf7a1e3febe061e2ef687`。
- 不维护 Sage 类名/方法名白名单。类型必须由具体函数契约、调用参数和 active Sage stub 推导；公共基类只用于继承成员查找，不能作为最终返回类型。
- 对 `UNKNOWN`、`DYNAMIC`、歧义 overload、无法确认的父对象实现必须 fail-closed，不能猜成 `Any`、公共基类或单一具体类。
- 构建使用 JDK `D:\Java\jdk-25`。官方 checkout 中既有的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore` 不得删除或修改。

## 2. 目标与验收

在 PyCharm 2026.2 中打开 `C:\Users\星记\Downloads\test2.sage`，应能实际看到：

- `P`、`E = P.curve()`、`F = GF(...)`、`R.<x> = PolynomialRing(F)`、`f`、`g = gcd(f, f.derivative())` 的具体可用类型；
- `P.log(G)`、`E.a_invariants()`、`f.derivative()`、矩阵 `solve_right`/切片等成员补全和 Quick Documentation；
- Sage 文档的签名、参数/返回分栏、代码块和语义颜色正常；普通 Python 文档不再因 WSL SDK 显示“需要本地 Python SDK”；
- 输入不完整的 `R.<`/`F.<` 不冻结编辑器，补全尖括号后分析指示器最终停止；运行 Sage 文件不显示多路径 Conda 探测脚本。

Gradle、索引和 ZIP 静态证据不能替代上述 fresh PyCharm GUI smoke。

## 3. 当前实现位置

- `core/sage-api`：索引 schema、qualified-name 查询、C3 继承成员、签名/文档和保守返回类型降低。
- `plugins/sage-core`：`.sage` parser、Sage sugar、类型 provider/lowering、completion、documentation provider、运行/调试入口、WSL SDK 边界。
- `tools/sage-api-index/annotate_stubs.py`：从 Sage stub 源码补充可证明的返回合同；`generate.py` 生成索引；`audit_contracts.py` 审计未知返回；对应测试位于同目录。
- 关键类型文件：`plugins/sage-core/src/main/kotlin/com/starnotesxj/sageide/type/SageTypeProvider.kt`、`SageTypeLowering.kt`、`sugar/SageStubIndex.kt`。

## 4. 已完成的通用修复

- 具体 receiver 的成员查询、普通函数调用、运算符和赋值边界会传播唯一可证明的 concrete return；结构化成员集合、`Any`、未知/动态返回不会抢答。
- 矩阵：同 receiver 运算和交换行列返回 `Self`；切片 `__getitem__` 返回 `Self`；整数坐标索引保留父对象相关类型；条件方法使用 `Literal` overload；`decomposition(dual=...)` 保留单序列/二元组分支。
- 环与元素：`ZZ`/`QQ`/有限域的 `__call__`、`gen`、`__iter__`，有限扩域元素系数索引/迭代器均有具体实现联合；多项式默认 `GF(p)[x].gen()` 为 `Polynomial_zmod_flint`。显式 NTL 实现因父类型未编码实现选择，仍 fail-closed。
- `gcd(a: GcdT, b: GcdT) -> GcdT` 使用 TypeVar 按实参具体化，不依赖公共基类。
- SDK 内 Sage `.py`/`.pyi` 不注入 synthetic PSI，避免 `parent is null`；Sage 文档 provider 直接渲染远程索引/PSI 文档和语义高亮；WSL 运行命令不在 EDT 同步探测；不完整 Sage sugar 回退原生 Python parser；生成器赋值误报由 Sage 专用 suppressor 限定抑制。

## 5. 当前合同索引与验证证据

- Sage 10.9/Python 3.13：`2,843` 源文件、`84,367` raw symbols、`84,304` entries、`48` diagnostics；inventory digest `b394d93c7adaefeb7ad4f00f62d624369a25bbf961b885dfc1d6a889506af0dc`。
- 审计：`52,723` callable entries、`52,283` signatures；`UNKNOWN=32,536`、`DYNAMIC=16`、`TYPE_VARIABLE=236`、`CONCRETE=3,681`、`BROAD_BUILTIN=10,923`、`UNION_OR_OPTIONAL=111`、`GENERIC=342`、`STRUCTURAL_BASE=39`。相对历史 `45,126` UNKNOWN，已减少 `12,590`（`27.89%`）。
- Python 索引/生成/导入/审计测试：`92` 项通过；`compileall`、AST 解析、`git diff --check` 通过。
- Gradle：默认 `:plugins:sage-core:test -PrunSageCoreTests=true`、`:core:sage-api:test -PrunSageApiTests=true --rerun-tasks` 和带外部索引的代表性 harness/coverage 测试均 `BUILD SUCCESSFUL`。外部索引混合全套仍有一个旧 `FSMState` fixture 断言失败，不作为本轮合同失败证据。
- WSL Sage 10.9 实际运行：矩阵/环/有限域/多项式实现 class 与条件返回已逐项检查；`test1.sage`、`test2.sage` 均退出码 `0` 并得到既有 CTF 结果。

## 6. 最新安装包

- 路径：`G:\sage-build\staging-build6\sage-core-0.1.0-dev-parent-dependent-contracts-20260828.zip`
- 大小：`16,173,030` bytes；SHA-256：`1131DCAC32E33223663B5500692B415F2B48B92370F00733D435F136C362D884`
- 内嵌 JAR：`14,020,498` bytes；SHA-256：`8E867FB9779A996B5F0A0EAED5D8F8A14A2535C113408B7CF360D31C22C17230`
- ZIP 顶层为 `sage-core/`，包含 `META-INF/plugin.xml`、完整 `sage-api-index.json`（`84,304` entries）以及 documentation/type-checker/angle-bracket providers。安装必须使用 PyCharm“从磁盘安装插件”，不能二次解压成 `plugins\\sage-core\\sage-core`。

## 7. 当前未完成项与风险

- 最新 ZIP 尚未在本轮从磁盘安装并重启 PyCharm；真实 completion、Ctrl+Q 富文档、分析指示器和编辑器冻结修复仍未 fresh 验收。
- `verify-upstream-staging.ps1 -FinalCheck` 按规则安全失败：官方 checkout 当前 SHA `3b652e714c12009bb69f0a2d2416dad02259fe5d`，不是要求的 `b0001cd6c53979b384cf7a1e3febe061e2ef687`。未修改官方 checkout。
- 当前没有可用 Windows installer，因此未宣称 x64 installer smoke、release audit 或产品分发 provenance 完成。
- 若 PyCharm 仍报告 `DirectoryLock`，先在 PyCharm 完全退出后处理单一 stale `.port` 锁，再确认实际加载的 JAR SHA 与上方一致。

## 8. 下一步（接手者直接执行）

1. 校验工作树，仅 stage 当前任务文件；不要加入 `.agent-teams/` 或 `hashcat_sessions.db`。
2. 从磁盘安装第 6 节 ZIP，重启 PyCharm，打开 `test2.sage`，验证 `P.log(G)`、`f.derivative()`、矩阵切片和 `gcd` 的类型/补全，以及 Ctrl+Q 和 `R.<` 编辑体验。
3. 读取 fresh `idea.log`；若失败，只按新堆栈指向的最小源码和回归测试修复。
4. 重新运行当前阶段所需 build/test、ZIP 静态核验和 `verify-upstream-staging.ps1 -FinalCheck`，报告真实 exit code；没有 GUI/installer 证据就明确写未完成。

本文件已压缩为当前边界、可复用决策、最新证据和下一步；旧轮次的重复 ZIP、重复计数和已解决堆栈不再逐轮保留。
