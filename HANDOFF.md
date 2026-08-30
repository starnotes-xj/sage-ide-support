# SageMath CTF IDE 交接说明

> 工作区：`G:\Projects\sage-math-ctf-ide`　　更新：2026-08-30
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

- Staging 索引：`2,843` 源文件、`85,034` entries、`52,431` signatures、`170` diagnostics、coverage `1.0`、missing `0`；inventory digest 为 `c9cd2dbc82f6ad3537250f62728b76382be828d1baf5e904deb6dcf9e87a57bd`。
- 合同审计：`UNKNOWN=24,080`、`CONCRETE=5,634`、`TYPE_VARIABLE=2,248`、`BROAD_BUILTIN=13,028`、`NONE=4,904`、`UNION_OR_OPTIONAL=1,804`、`DYNAMIC=17`、`STRUCTURAL_BASE=70`、`GENERIC=496`、`UNQUALIFIED=150`。相对本文件上一记录净减少 `769` 个 UNKNOWN（`24,849 -> 24,080`）；本轮优先收敛了可由源码/WSL 直接证明的 TateAlgebraTerm/Weierstrass 外层结果、PolyDict `lcmt`、TermOrder copy helper、NumberField_cyclotomic GAP/embedding 结果、functional 常用包装函数、SimplicialComplex 示例构造器、Braid 矩阵/结不变量/自运算及内部缓存、LatinSquare 行列/构造器/位交换辅助、以及 matrix benchmark 的 float/matrix/None 返回。公共基类仍只用于继承成员查找，动态父对象和无法证明的元素类型保持 UNKNOWN。
- 本轮新增以 Sage 10.9 文档为主、对可运行项用 WSL 复核：矩阵空间具体矩阵族/模块、`matrix.special` 的块矩阵/伴随矩阵/随机矩阵/旋转矩阵/Toeplitz-Hankel 等构造器、basic graph catalogue 的 `Graph` 构造器、Polynomial/PolynomialRing_generic 的生成元/随机元素/模运算/换基/符号转换/高度/幂级数截断等合同、Graph/Digraph 容器与原地 `None` 分支、符号 Expression、NumberField（含绝对域）、有限域与 IntegerMod 后端、椭圆曲线标量/多项式、matroid/design/graph/polytope/poset/partition/tableau/word/permutation catalogue 构造器、PowerSeries/MPowerSeries/LaurentSeries/LazyModuleElement、Link、FiniteStateMachine、PermutationGroup 基础协议，以及 MPolynomial/MPolynomialRing 的系数、指数、迭代器、插值、生成元、Newton polytope、`nth_root`/`crt` 等；本轮 WSL 抽样确认 `matrix.identity_matrix`、`block_matrix`、`companion_matrix`、`hilbert`、`graphs.CycleGraph`/`CompleteGraph`、`R.gen()`、`R.random_element()`、`f.derivative()`、`f.mod()`、`f.add_bigoh()` 和 `f._symbolic_(SR)` 都落到具体 Sage 类。动态参数仍保留联合或 UNKNOWN。
- 通过：`python -m unittest discover -s tools/sage-api-index -p 'test_*.py'`（`187` 项）、`compileall`、`git diff --check`、AST 检查、staging `generate.py` 和 `audit_contracts.py`。
- 当前索引文件：`G:\sage-build\staging-build6\sage-api-curated-type-contracts.json`。

## 6. 风险与下一步

- 最新可用 ZIP `G:\sage-build\staging-build6\sage-core-0.1.0-dev-ctf-output-contracts-20260829-r5.zip` 未包含本轮新增合同；本轮仍未重新打包、安装或执行 PyCharm GUI smoke。
- 尚无可用 Windows installer；`verify-upstream-staging.ps1 -FinalCheck` 仍因官方 checkout SHA 为 `3b652e714c12009bb69f0a2d2416dad02259fe5d` 而安全失败，官方 checkout 未修改。
- 下一步：以当前 staging 索引重建插件 ZIP，安装后验证 `test2.sage` 的类型/补全、Ctrl+Q、`R.<` 编辑体验和运行日志；继续按审计高频 bucket 做源码/WSL 双证据验证，动态工厂无法证明时保持 UNKNOWN。

最近提交：本轮变更已保存；具体提交号以 `git log -1` 为准。
