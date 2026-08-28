# SageMath CTF IDE 交接说明

> 工作区：`G:\Projects\sage-math-ctf-ide`
> 目标：先完成 SageMath 编辑器智能（类型、补全、文档、语法糖和运行入口），CTF/Notebook 产品功能暂不扩展。
> 更新：2026-08-29

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

- Sage 10.9/Python 3.13：`2,843` 源文件、`84,499` raw symbols、`84,385` entries、`79` diagnostics；inventory digest `eb99a6e7e7f2339550d17afc54a55f84c6b0d759c910ed423a19e2cb990f8b4e`。
- 审计：`52,723` callable entries、`52,303` signatures；`UNKNOWN=30,893`、`DYNAMIC=16`、`TYPE_VARIABLE=361`、`CONCRETE=3,830`、`BROAD_BUILTIN=11,751`、`UNION_OR_OPTIONAL=441`、`GENERIC=348`、`STRUCTURAL_BASE=39`。相对本轮起点 `32,536` 减少 `1,643`；相对历史 `45,126` UNKNOWN，累计减少 `14,233`（`31.54%`）。
- Python 索引/生成/导入/审计测试：`103` 项通过；`compileall`、AST 解析、`git diff --check` 通过。新增 CTF 经典密码、LFSR、SR/AES 具体实现合同测试保持幂等。
- Gradle：默认 `:plugins:sage-core:test -PrunSageCoreTests=true`、`:core:sage-api:test -PrunSageApiTests=true --rerun-tasks` 和带外部索引的代表性 harness/coverage 测试均 `BUILD SUCCESSFUL`。外部索引混合全套仍有一个旧 `FSMState` fixture 断言失败，不作为本轮合同失败证据。
- WSL Sage 10.9 实际运行：矩阵/环/有限域/多项式实现 class 与条件返回已逐项检查；DES/PRESENT 整数→`Integer`、list-like→`Vector_mod2_dense`，密钥调度列表元素、位向量转换、S-DES 二进制串/排列/尺寸结果均已运行核对；`test1.sage`、`test2.sage` 均退出码 `0` 并得到既有 CTF 结果。

## 6. 最新安装包

- 路径：`G:\sage-build\staging-build6\sage-core-0.1.0-dev-ctf-output-contracts-20260829-r5.zip`
- 大小：`16,206,081` bytes；SHA-256：`42507C5FA0032B9747680C4C42087941BB1D4C65DAF5520532D1442D98ADCA9A`
- 内嵌 JAR：`14,053,894` bytes；SHA-256：`ECC897941384F2BB4F6D4594CF0CC6C910D5A93214923747134E147BD546E347`
- ZIP 顶层为 `sage-core/`，内嵌 JAR 含恰好一个 `META-INF/plugin.xml` 和完整 `sage-api-index.json`（`84,385` entries）；JAR 内索引 SHA 与 staging 外部索引 `42CF7F77B1EF7FFEEC7C6BEFE781ABAFD6C0585414EA0D790F6D0304D98789DD` 完全一致，并保留 documentation/type-checker/angle-bracket providers。安装必须使用 PyCharm“从磁盘安装插件”，不能二次解压成 `plugins\\sage-core\\sage-core`。

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

## 9. 本轮增量（2026-08-29）

- `annotate_stubs.py` 新增全树 Python 协议合同：`__dealloc__`/`__setstate__`→`None`、`__reduce__`→`tuple | str`、`_repr_`/`_latex_`→`str`、`__copy__`/`__deepcopy__`→`Self`；文档明确返回自身的迭代器也保留 `Self`，不猜测 `__next__` 元素。
- 新增文档驱动参数条件重载：仅当同一参数同时明确“integer→Integer”和“list-like→GF(2) bit vector”时生成 overload；DES/PRESENT 的 `__call__`/`encrypt`/`decrypt` 以及 DES/PRESENT 密钥调度的列表元素合同已进入索引。CTF 位向量转换、二进制串/排列和尺寸合同均由 Sage 文档语义触发；本轮追加 DES 内部 GF(2) 置换、MiniAES/PRESENT 辅助函数、Rijndael plain-string 修正、SR 工厂 `gf2` 分支、SR 矩阵/多项式系统、经典密码体制、经典 cipher inverse/call 和 LFSR 合同，不使用插件侧函数白名单。
- WSL Sage 10.9 运行核对与索引结果：`84,385` entries、`52,303` signatures、`UNKNOWN=30,893`；相对本轮 `32,536` 减少 `1,643`。Python 索引测试 `103/103`，两次注解幂等；Gradle 默认 core/plugin、外部索引 3 项门禁和 `buildPlugin` 均 `BUILD SUCCESSFUL`。
- 新包为第 6 节 `-r5` ZIP；fresh PyCharm 安装/GUI smoke、installer 和 FinalCheck 的官方 SHA 阻塞仍未改变。

本文件已压缩为当前边界、可复用决策、最新证据和下一步；旧轮次的重复 ZIP、重复计数和已解决堆栈不再逐轮保留。
