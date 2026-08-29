# SageMath CTF IDE 交接说明

> 工作区：`G:\Projects\sage-math-ctf-ide`　　更新：2026-08-29
>
> 当前目标：先完成 SageMath 编辑器智能支持（类型、补全、文档、语法糖、运行入口），暂不扩展 Notebook/CTF 产品界面。

## 1. 边界与原则

- 只修改本工作区和 `G:\sage-build\staging-build6`；不得修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr`。
- 官方基线为 `G:\Projects\intellij-community-sage-ide`，要求 SHA `b0001cd6c53979b384def7a1e3febe061e2ef687`；官方 checkout 中既有的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore` 不得删除或修改。
- 返回类型必须由具体函数合同、调用参数和 active Sage stub 推导；公共基类只用于继承成员查找，不能作为最终返回类型。不确定、动态、条件联合结果必须保持 `UNKNOWN`/`DYNAMIC`，不能猜成 `Any`。
- 构建使用 `D:\Java\jdk-25`。当前工作树仅保留未跟踪的 `.agent-teams/` 和 `hashcat_sessions.db`，不得加入提交。

## 2. 验收目标

在 PyCharm 2026.2 打开 `C:\Users\星记\Downloads\test2.sage`，应能验证：

- `P`、`E=P.curve()`、`F=GF(...)`、`R.<x>=PolynomialRing(F)`、`f`、`g=gcd(f,f.derivative())` 的具体类型，以及 `P.log(G)`、`f.derivative()`、矩阵 `solve_right`/切片的补全和 Quick Documentation。
- Sage 文档的签名、参数/返回分栏、代码块和语义颜色正常；普通 Python 文档不再要求本地 SDK。
- `R.<`/`F.<` 不冻结编辑器，分析最终停止；运行 Sage 文件不显示 Conda 多路径探测脚本。

Gradle、索引和 ZIP 静态结果不能替代 fresh PyCharm GUI smoke。

## 3. 实现位置

- `core/sage-api`：索引 schema、qualified-name 查询、C3 继承成员、签名/文档和保守返回类型传播。
- `plugins/sage-core`：`.sage` parser、语法糖、类型 provider/lowering、completion、documentation、运行入口和 WSL SDK 边界。
- `tools/sage-api-index/annotate_stubs.py`：从 Sage stub 文档/协议补充可证明的返回合同；`generate.py` 生成索引；`audit_contracts.py` 审计覆盖。
- 关键类型实现：`plugins/sage-core/src/main/kotlin/com/starnotesxj/sageide/type/SageTypeProvider.kt`、`SageTypeLowering.kt`、`sugar/SageStubIndex.kt`。

## 4. 已完成的关键能力

- 具体 receiver、函数调用、运算符和赋值会传播唯一可证明的 concrete return；不再用公共基类抢答。
- 矩阵、环、有限域、多项式、椭圆曲线和 CTF 密码 API 已加入具体实现/TypeVar/条件 overload 合同；`gcd(a: GcdT,b: GcdT)->GcdT` 按实参具体化。
- Sage `.py`/`.pyi` 不注入 synthetic PSI；Sage 文档 provider 直接渲染索引/PSI 文档和语义高亮；不完整语法回退 Python parser；WSL 运行命令避免 EDT 同步探测。
- 最近一轮还补齐了迭代器外层 `Iterator`、多项式 `Factorization`、商余 `tuple`、有限域元素运算 `Self` 合同；多项式逆元、同态逆和父对象动态选择继续 fail-closed。

## 5. 当前验证状态（Sage 10.9 / Python 3.13）

- Staging 索引：`2,843` 源文件、`84,969` entries、`52,363` signatures、`104` diagnostics、coverage `1.0`、missing `0`；generator 报告保留 `1` 个既有 conflicts gate warning。
- 合同审计：`UNKNOWN=27,478`、`CONCRETE=4,844`、`TYPE_VARIABLE=1,414`、`BROAD_BUILTIN=12,216`、`NONE=4,690`、`UNION_OR_OPTIONAL=1,117`、`DYNAMIC=17`、`STRUCTURAL_BASE=45`。本轮补充动态元素/父对象/条件矩阵合同后，相对上一记录再减少 `1,712`。
- 通过：`python -m unittest discover -s tools/sage-api-index -p 'test_*.py'`（`125` 项）、`compileall`、`git diff --check`、重复字典键检查、staging `generate.py` 和 `audit_contracts.py`。
- WSL 运行抽样：矩阵 `find(indices=False/True)` 为具体矩阵/`dict`，`krylov_basis(output_rows=...)` 为矩阵或带行 profile 的元组；有限域 `from_integer`、`prime_subfield`、`polynomial`、元素 `_vector_`/`_integer_` 与 Pari/Givaro/NTL 元素运算均按实现类收窄。
- 当前索引文件：`G:\sage-build\staging-build6\sage-api-curated-type-contracts.json`。

## 6. 风险与下一步

- 最新可用 ZIP `G:\sage-build\staging-build6\sage-core-0.1.0-dev-ctf-output-contracts-20260829-r5.zip` 未包含本轮新增合同；本轮仍未重新打包、安装或执行 PyCharm GUI smoke。
- 尚无可用 Windows installer；`verify-upstream-staging.ps1 -FinalCheck` 仍因官方 checkout SHA 为 `3b652e714c12009bb69f0a2d2416dad02259fe5d` 而安全失败，官方 checkout 未修改。
- 下一步：以当前 staging 索引重建插件 ZIP，安装后验证 `test2.sage` 的类型/补全、Ctrl+Q、`R.<` 编辑体验和运行日志；继续新增合同时必须先用 Sage 源码或 WSL 10.9 运行类型证明，动态工厂无法证明时保持 UNKNOWN。

最近提交：`884362d`（迭代器、因式分解、商余和有限域元素返回合同）。
