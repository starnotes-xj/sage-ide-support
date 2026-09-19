# SageMath CTF IDE 交接

> 工作区：`G:\Projects\sage-math-ctf-ide`　更新：2026-09-09
>
> 当前阶段：先完成 SageMath 类型索引/补全/文档智能，再做插件打包和 fresh PyCharm 验收。

## 1. 硬边界

- 只修改本工作区和 `G:\sage-build\staging-build6`；不得修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr`。
- 官方基线为 `G:\Projects\intellij-community-sage-ide`，要求 SHA `b0001cd6c53979b384def7a1e3febe061e2ef687`；不得修改其 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore`。
- 返回类型必须由具体函数合同、调用参数、active Sage stub、源码/运行证据共同证明。公共基类只用于继承成员查找，不能作为最终类型；动态、条件不确定或多实现结果保持 `UNKNOWN`/`DYNAMIC`，禁止猜成 `Any`。
- 构建 JDK：`D:\Java\jdk-25`。不提交 `.agent-teams/`、`hashcat_sessions.db` 等无关文件。

## 2. 目标与实现入口

- CTF 重点：`EllipticCurve`/点、有限域、PolynomialRing/多项式、矩阵、`gcd`、CRT；需支持具体类型、成员补全、Quick Documentation 和 Sage 文档语义渲染。
- `.sage` 语法糖（如 `R.<x> = PolynomialRing(F)`）不能冻结编辑器；运行 Sage 文件不得显示 Conda 探测脚本。
- `core/sage-api`：索引 schema、继承、签名/文档和类型传播。
- `plugins/sage-core`：`.sage` PSI、类型 provider/lowering、completion、documentation、WSL 运行入口。
- `tools/sage-api-index`：`annotate_stubs.py`、`infer_source_returns.py`、`infer_cython_returns.py`、`apply_source_contracts.py`、`propagate_parent_contracts.py`、`generate.py`、`audit_contracts.py`。

## 3. 当前可复核证据

- canonical 索引：`G:\sage-build\staging-build6\sage-api-curated-type-contracts.json`
- 最终审计：`G:\sage-build\staging-build6\sage-api-curated-type-contracts.audit.final.json`
- Sage 10.9 / Python 3.13：`entries=85828`、`callableEntries=52747`、`signatures=52451`。
- 当前返回分类：`UNKNOWN=7322`、`CONCRETE=8821`、`TYPE_VARIABLE=3691`、`UNION_OR_OPTIONAL=4768`、`STRUCTURAL_BASE=77`、`NO_RETURN=338`；`audit_contracts.py` exit 0。
- 最新增量：Cython 无分支/副作用/同型条件分支/多行头规则累计应用 `54` 个；本轮修正引号联合解析并写入 `21` 个源码证明的多实现联合合同，再传播 `99` 个唯一父类实现合同（累计 UNKNOWN 由 `8142` 降至 `7857`）。父合同传播同时覆盖 METHOD/PROPERTY，且只保留最近层唯一同值合同；`*_generic` 仅在与非结构叶类或 `type` 工厂同一联合中允许；单独 `_generic`、`_base`、`_parent`、`_element`、`_factory` 仍拒绝。`PowerSeriesRing(ZZ,'t')` 实跑为 `PowerSeriesRing_domain_with_category`，`AffineSpace(GF(5),2)` 实跑为 `AffineSpace_finite_field_with_category`。
- 测试：全量回归 `311` 项通过（45.974 秒）；本轮聚焦审计/源合同测试、父合同测试与 Cython 测试均通过；`compileall`、`git diff --check` 通过；源/父/Cython 合同重复应用均 `applied=0`。重新运行既有结构化注解流水线报告 378 个文件编辑，但 canonical 声明/UNKNOWN 无变化，未计入新增减少。
- `generate.py` 产生 `missing=14`、已知 `conflicts=2`（本次命令 exit 1，索引仍已生成）；最终 `audit_contracts.py` exit 0。expected-high-value 仅是旧 fixture 覆盖清单，不能冒充 10.9 完整质量门。
- 本轮新增工厂实例合同桥：仅从 `create_object` 的已索引联合中剔除 `_generic`/`_base` 等结构臂，再传播到模块级 `Factory(...)` 绑定；普通索引合同仍保持全量 fail-closed。源码合同 `78657` 条，实际写入 `95` 个缺失返回，重复应用 `applied=0`。重建后索引为 `entries=85825`、`callableEntries=52747`、`signatures=52451`，最终审计 `UNKNOWN=7762`（`7857 -> 7762`），`CONCRETE=8756`、`UNION_OR_OPTIONAL=4696`，审计 exit 0。
- 验证：新增源合同测试 15 项通过；此前同一代码状态全量回归 314 项通过（设置 UTF-8 环境）；本轮再次启动全量回归时 WSL 子进程返回 Windows 环境码 `1073807364`，无测试断言失败输出，故不把该次启动当作新的全量证据。`compileall`、`git diff --check` 通过。
- 复核后进一步收紧推断器：只有源码继承 `UniqueFactory` 的类才建立模块级工厂绑定，且类属性分析只接收内部 `@factory:` 标记，不会把普通常量误传播为工厂结果。当前 staging 索引保留上一轮已写入的 95 个合同；后续重建将按该收紧规则复用既有具体合同并拒绝无关 `create_object`。
- 后续批次：导入常量别名通过已索引值类的精确成员合同解析可调用父对象（如 `ZZ(...)`），递归继承查找覆盖 `self/super/receiver`，并识别源码 MRO 中唯一的嵌套元素类；Sage 10.9 源码重推断 `78777` 条，实际新增写入 `12 + 24 + 1` 个仍未知返回，canonical UNKNOWN `7762 -> 7725`。新增源合同测试 `16` 项，全量索引测试 `315` 项通过，`compileall`、`git diff --check` 通过。
- 局部容器批次：对赋值后的字面量 `list/set/tuple/dict` 保留已证明元素泛型，供动态下标、`min/max` 等后续调用继续传播；Sage 10.9 源码合同 `78830` 条，实际写入 `12` 个缺失返回，canonical UNKNOWN `7725 -> 7713`，`CONCRETE=8785`。全量索引测试 `315` 项通过，`compileall`、`git diff --check` 通过。
- Self/关系泛型批次：索引桥归一化已证明的 `typing.Self` 与 `sage.type_contracts.*Element[Self]`，只把它们作为接收者/父对象关系合同传播，不降级为公共基类；Sage 10.9 源码合同 `81680` 条，实际写入 `139` 个缺失返回。重建 canonical `entries=85827`、`callableEntries=52747`、`signatures=52451`，`UNKNOWN=7574`（`7713 -> 7574`）、`TYPE_VARIABLE=3691`、`GENERIC=2302`，最终审计 exit 0。WSL Sage 实跑验证 `Polynomial_zmod_flint.zero/one/gen` 和 `EllipticCurvePoint_finite_field`；源合同测试 `18` 项、全量索引测试 `317` 项通过。
- 动态 `element_class`/索引父类批次：调用 `receiver.element_class(...)` 只有在源码证明具体 `Element` 类时才产生 `ParentElement[Self]`；索引中的 `Parent.element_class -> type` 不再泄漏为构造结果，显式嵌套 `element_class` 类仍按类对象构造处理。同步接入索引父边仅用于成员查找，并清理了 `33` 个由旧规则误写的 `-> type` 返回。WSL Sage 实跑 `Partitions(3).first/last` 为 `Partitions_n_with_category.element_class`、Affine Lie `d()` 为 `UntwistedAffineLieAlgebraElement`，证明动态工厂应保持关系/未知而非 `type`。重推断源码合同 `71529` 条，重建 canonical `entries=85828`、`callableEntries=52747`、`signatures=52451`，`UNKNOWN=7493`（`7574 -> 7493`），最终审计 exit 0；新增聚焦测试 `22` 项、全量索引测试 `321` 项通过（UTF-8 环境）。
- 外部父对象关系特化批次：对 `ParentElement[Self]` 只在接收者是索引中精确父类、且其 `__call__`/`_element_constructor_` 唯一收敛到具体 Sage 类时特化；否则保留关系合同。该规则无函数名白名单，并避免把 `ZZ.one()/zero()` 的关系误解释为调用方所属类。Sage 10.9 源码合同 `72464` 条，首轮写入 `31` 个缺失返回；复核后撤回 1 个由 `self.__class__.__base__()` 误得的公共 `Parent` 返回，保留 `30` 个可复核合同。canonical `entries=85828`，`UNKNOWN=7430`（安全批次基线 `7460 -> 7429` 后撤回误合同），`CONCRETE=8800`，最终审计 exit 0。WSL 实跑 `A001110.g(1/2)` 为 `Integer/int`、`A001055.nwf`、`Stream_zero()[1]`、`abs(RootsOfUnityGroup()(…))`、`Order.krull_dimension()` 均为 `Integer`；源合同聚焦测试 `29` 项通过。
- 父元素协议/动态工厂批次：源码推断新增“接收者与 `element_class` 首参相同”结构合同，并对 `@lazy_attribute`/`@cached_property` 返回的字符串类映射进行内部数据流传播；动态键、未证明父类和描述符映射不会泄漏为公开类。Sage 10.9 源码合同 `73260` 条，与当前 UNKNOWN 交集安全写入 `57` 条（46 条 `ParentElement[Self]`、8 条有限 `Self` 联合及 3 条其他精确关系/类合同），重建 canonical `entries=85828`、`callableEntries=52747`、`signatures=52451`，`UNKNOWN=7373`（`7430 -> 7373`）、`UNION_OR_OPTIONAL=4760`、`GENERIC=2451`，审计 exit 0。新增源合同聚焦测试 `34` 项；完整工具测试 `333` 项通过（83.606 秒）。WSL 实跑 Partition/ExteriorAlgebra 动态元素均返回具体 `element_class` 实例，支持关系合同的运行时依据。
- 固定点传播复核：在上述 57 条关系合同写入后重新推断得到 `73294` 条源码合同，再安全写入 5 条唯一父元素包装合同；重建后 `UNKNOWN=7368`、`GENERIC=2456`，审计 exit 0。再次推断未发现新的安全交集，当前规则批次收敛。
- 关系容器归一化复核：索引桥现在递归保留已验证的 `Iterator/tuple/list/set/dict` 关系元素合同，仍拒绝任意泛型和未约束 TypeVar。源码重推断 `73304` 条合同；当前 UNKNOWN 交集未出现可安全写入的具体合同（唯一候选来自任意 callable 的不充分推断，按 fail-closed 拒绝），canonical 保持 `UNKNOWN=7368`。新增源合同测试 `35` 项通过。
- 父对象工厂数据流批次：对未被源码覆盖的 `self.parent()` 建立仅供局部传播的内部父对象标记；调用父对象构造器或索引中已证明的 `*Element[Self]` 关系方法时解析为 `ParentElement[Self]`。关系方法集合由索引合同自动派生，不使用函数名白名单；任意 callable（`PoorManMap.__call__`）明确拒绝。WSL Sage 10.9 源码重推断 `73720` 条，安全交集写入 `42` 条（35 条父元素关系、7 条有限 Self/None/list 联合），重建 canonical `entries=85828`、`UNKNOWN=7326`、`UNION_OR_OPTIONAL=4767`、`GENERIC=2491`，审计 exit 0。
- 父合同固定点复核：更新后的继承/成员合同只新增 1 条可证明的 `sage.interfaces.mathematica.MathematicaElement._reduce -> str | Self`（源码文档明确字符串回退或对应 Sage 对象），没有其他安全父合同。重建 canonical 后 `UNKNOWN=7325`、`UNION_OR_OPTIONAL=4768`，`propagate_parent_contracts.py` 再次运行 `applied=0`。
- 结构叶类合同批次：新增数据驱动的索引层级规则，仅当源码合同指向 `_generic`/`_base`/`_element`/`_parent`/`_factory` 类且父边集合证明没有子类时才允许具体返回值；不维护类名白名单。WSL Sage 10.9 重复运行证明 `QuarticCurve(...)` 返回 `QuarticCurve_generic_with_category`、`toric_varieties.P2().K()` 返回 `ToricDivisor_generic`；`PoorManMap.__call__` 的任意 callable 联合、`Schemes_over_base` 和 `PolynomialSequence_generic` 均因动态/子类分支拒绝。生成并提升 canonical 后 `UNKNOWN=7323`（`7325 -> 7323`）、`CONCRETE=8820`、`STRUCTURAL_BASE=77`，索引与 formal copy SHA256 为 `c39e5ae75362bffe92d30cdb397e4b371aa05f562a5a5a6fac08e434bb2531f2`。
- Cython 叶类合同复核：全量 Sage 10.9 `.pyx/.pxd` 源码推断仅剩 `IdentityFunctor` 一个 UNKNOWN 交集；源码第 609 行明确 `return IdentityFunctor_generic(C)`，索引无子类且两次 WSL 实跑均为 `sage.categories.functor.IdentityFunctor_generic`，按同一层级规则写入。canonical/formal copy SHA256 为 `6e394f1844b3674d6f08a9208ddd60698bc8a24abeed00ea37c2aaaf9fe49c05`，`UNKNOWN=7322`（`7323 -> 7322`）、`CONCRETE=8821`，Cython 重复应用 `applied=0`。
- 可变参数防回归：源码推断新增通用 AST 检查，未注解 `*args` 取元素（`args[0]`）不再因局部数据流偶合而生成 Sage 具体合同；返回整个可变参数容器仍准确保留 `tuple`，已有 `vararg_identity` 回归测试通过。重新推断合同数为 `73694`，与当前 UNKNOWN 的交集只剩 `Schemes.__classcall_private__` 和 `Ideal_1poly_field.groebner_basis` 两个有子类结构分支，及无稳定输出的任意 callable 已被排除；应用结果 `applied=0`，canonical 保持 `UNKNOWN=7322`。

## 4. 下一步与限制

- 继续按 UNKNOWN 分布批量处理动态后端、条件返回、多实现泛型和副作用接口；下一批优先查找“同一具体接收者/参数合同在所有实现一致”的源证据。必须有源码/索引/参数或实际运行的可重复证据，不能用单样本观测或公共基类兜底。当前 `7322` 个 UNKNOWN 中，动态后端/条件分支/副作用接口仍占主要部分，继续保持 fail-closed。
- 完成后重建插件 ZIP，执行 CTF ECC/矩阵/多项式/有限域场景的 fresh PyCharm completion、Quick Documentation、语法糖和运行日志 smoke。
- Gradle 产品构建、installer smoke、`verify-upstream-staging.ps1 -FinalCheck` 尚未完成；官方 checkout 当前 SHA 为 `3b652e714c12009bb69f0a2d2416dad02259fe5d`，与规定基线不符，因此不能宣称产品验收完成。
- WSL Sage 可用；接口包装器的 `sage0` 缺失模块属于外部环境，不作为插件回归证据。

## 2026-09-09 增量（v147，当前权威审计）

- v146/v147 索引均为 `entries=86024`、`callableEntries=52747`、`signatures=52449`；`UNKNOWN=3703`，`CONCRETE=9251`。v147 重新生成 exit 3 仅因既有 `conflicts=2`，索引和 audit 均已写出，audit exit 0。
- 新增通用源码规则：当比较运算左值的具体接收者在索引中对每一段 `__eq__/__ne__/__lt__/__le__/__gt__/__ge__` 均有唯一 `bool` 合同时，链式比较解析为 `bool`；未知接收者、冲突实现和非布尔合同继续 UNKNOWN。聚焦测试通过；本批在完整 Sage 交集未新增可安全写入合同。
- 当前剩余 UNKNOWN 主要是动态后端、条件/参数分支、父对象或工厂依赖、多实现泛型、任意 callable 与副作用接口。按“具体返回值、禁止公共基类/Any/白名单猜测”的约束，不能诚实地把这些改成零；强行改写会破坏 PyCharm 补全的准确性。
- 工具回归：此前全量 `376` 项通过；本轮新增比较合同测试通过；`compileall`、`git diff --check` 通过。正式 Gradle/产品/installer/真实 PyCharm smoke 仍未完成。

## 2026-09-09 增量（v148，当前权威审计）

- Cython 源码推断新增通用 Python 协议调用（`isinstance`、`len`、`repr` 等）合同；实际 WSL Sage 10.9 交集安全写入 `4` 个固定布尔协议函数（包括 `is_Map`、`is_Morphism`、`is_Matrix`、`is_Vector`）。
- v148 audit：`entries=86024`、`callableEntries=52747`、`signatures=52449`、`KNOWN=48729`、`CONCRETE=9252`、`UNKNOWN=3702`，audit exit 0；生成器仍因既有 `conflicts=2` 返回 exit 3，但索引/报告正常写出。
- 全量工具回归 `377` 项通过（含本轮比较/Cython 测试），`git diff --check` 通过。当前 3702 个未知没有可由现有索引、源码和参数合同唯一证明的具体 Sage 返回类；把它们强行归为基类/Any/猜测会违反任务约束，不能诚实地宣称 UNKNOWN=0。

## 2026-09-09 增量（v149-v151，当前权威审计）

- v149：允许固定返回表达式前的普通 Python `from ... import`，并保持真正 `cimport` fail-closed；WSL Sage 10.9 Cython 合同 `4869`，实际新增 `4` 个，审计 `UNKNOWN=3698`。
- v150：仅对头部明确声明 C 标量参数的比较表达式推断 `bool`（普通 Sage 对象比较不放宽）；回归通过，实际新增 `1` 个，审计 `UNKNOWN=3697`。
- v151：从实际共享 `.pxd/.pyx` 声明收集全局唯一的 Cython helper 合同，冲突短名拒绝；合同 `4930`，实际新增 `1` 个，审计 `UNKNOWN=3696`。三轮生成器均仅报告既有 `conflicts=2`，audit exit 0。
- 新增 Cython 回归 `24` 项；本轮最终全量工具回归 `381` 项通过（56.819 秒），`compileall` 与 `git diff --check` 通过。仍未进行 Gradle/产品/installer/真实 PyCharm smoke；对动态后端、条件分支、多实现泛型、任意 callable 和副作用接口不能伪造具体类型。

## 2026-09-09 增量（v152，当前权威验证）

- v151 审计结果保持：`entries=86024`、`callableEntries=52747`、`signatures=52449`、`UNKNOWN=3696`；`audit_contracts.py` exit 0。当前未知集合与 v147-v150 Cython 合同无交集，纯 Python 源合同交集仅为参数标记/动态关系，应用 `0`，因此没有新的安全具体合同可写入。
- 本轮验证：`python -m unittest discover -s tools/sage-api-index -p 'test_*.py'` 为 `Ran 381 tests ... OK`；`python -m compileall -q tools/sage-api-index` exit 0；`git diff --check` exit 0。
- 仍不能把 `3696` 个动态后端、条件/参数分支、多实现泛型、任意 callable 或副作用接口改成 `0`：没有唯一具体 Sage 类证据时，强行改写为公共基类、`Any`、`object` 或白名单类型会直接破坏 PyCharm 补全准确性，也违反本交接的硬边界。

## 2026-09-09 增量（v153-v155，当前权威审计）

- v153：修正构造器字段依赖的作用域判定，新增 `85` 个可参数化 getter；v154 由 `SageTypeLowering` 只对生成的 `_SageStored…` 类 TypeVar 从接收者实际泛型实参绑定，插件回归证明 `Box[Payload].value()` 精确为 `Payload`，不退化为公共基类。
- v154：Sage 10.9 WSL 源合同 `82167` 条，安全写入 `37` 个，审计 `UNKNOWN=3574`（`3611 -> 3574`）、`TYPE_VARIABLE=4029`；生成器 exit 3 仍仅为既有 `conflicts=2`，audit exit 0。
- v155：构造器参数有默认值但未被重绑定、字段没有其他写入时，仍按实际传入值建立字段 TypeVar；条件改写默认值的构造器继续拒绝。Sage 全源重推断 `82181` 条，实际写入 `5` 个：`LieAlgebraHomomorphism_im_gens.base_map`、`CoveringDesign.k/v`、`pAdicLseries.quadratic_twist`、`Constant._mathml_`。审计 `UNKNOWN=3569`、`TYPE_VARIABLE=4034`，全量 `2843` stub 可解析，重复应用 `applied=0`。
- v155 验证：`test_source_contracts` 50 项通过；`compileall`、`git diff --check` 通过；`SageTypeProviderTest` Gradle 类级测试成功。完整工具集重跑遇到 Windows 端读取 WSL 子进程的 UTF-8 解码线程异常，未取得可报告的新全量退出码；此前 v151 的 381 项通过仍是最近完整全绿证据。
- 剩余 `3569` 项中，当前源码/索引交集只剩 `41` 个（34 个参数变换/默认分支、7 个继承或既有泛型边界）；其余主要是动态后端、父对象依赖、条件返回、多实现泛型、任意 callable 与副作用接口。不能用一次运行样本或公共基类将其伪造为具体类型；下一轮必须为这些接口建立调用参数/接收者相关的可复现合同或 IDE 运行时查询边界。

## 2026-09-09 增量（v156，运行时类型快照）

- 新增 `SageLiveTypeProbe`：固定 `sage -c` 包装器只从标准输入接收 Base64 源码/变量名，执行 Sage preparser 后输出真实 `type` 和完整 MRO；不拼接用户源码进命令或 Shell。`RuntimeProcess`/`TargetProcessRequest` 支持受限标准输入，WSL 命令仍是 `wsl.exe -d <distribution> -- <configured-sage> -c <fixed-wrapper>`，不会进入 Run 控制台或显示 Conda 探测脚本。
- `SageLiveTypeSnapshotService` 是项目级、显式 opt-in 的后台服务：仅执行光标前（赋值目标包含当前赋值）的未保存文档前缀，256 KiB/128 KiB 上限、650 ms 去抖、30 秒后台截止、同文件旧请求取消、哈希快照缓存；完成后只重启对应文件的 daemon 分析。运行样本绝不写入全局 Sage API 索引。当前插件侧支持已配置的 Native/WSL Sage；Docker/SSH 不执行探测。实际 WSL Sage 冷启动的 11–19 秒证据意味着后续若需亚秒级响应，应升级为常驻 worker，而非错误地缩短快照超时。
- 映射严格：优先真实运行类；若仅为 runtime-only `*_with_category`，只允许映射 MRO 的**直接**具体桩类父类（如 `EllipticCurve_finite_field_with_category -> EllipticCurve_finite_field`）。若直接父类也不在桩库，保持 UNKNOWN，绝不沿 MRO 降为 `EllipticCurve`、`Parent`、`Element` 等公共基类。
- WSL Sage 10.9 实测（标准输入路径）：`E = EllipticCurve(GF(11), [1,1]); P = E(0,1); G = E.gen(0)` 得到 `E=EllipticCurve_finite_field_with_category`，`P/G=EllipticCurvePoint_finite_field`；多项式/矩阵快照中 `f/g=Polynomial_zmod_flint`、`A=Matrix_modn_dense_float`、`b/s=Vector_modn_dense`。`E(1,1)` 对该曲线坐标非法，`E.gen()` 需索引，二者会保留 Sage 原始异常，不制造类型。
- 验证：`core:runtime:test` 全量 67 项（含 stdin/WSL 参数/marker-MRO）通过；`SageTypeProviderTest` 全类 Gradle 40 项通过（含 runtime-only 映射和拒绝公共 MRO 基类的回归）；`plugins:sage-core:compileKotlin`、`git diff --check` 通过。fresh ZIP 已构建为 `plugins/sage-core/build/distributions/sage-core-0.1.0-dev.zip`（SHA-256 `154065C338CA524E636D1DF662C95FE4102449B832F28893275F3B2052DA1DEF`），尚未在 fresh PyCharm 安装/UI smoke；开关默认关闭，需在 `Settings | Tools | SageMath` 勾选 “Enable live type snapshots”。

## 2026-09-10 增量（v157，常驻运行时类型 worker）

- `SageLiveTypeSnapshotService` 已从每次启动一个 Sage 进程升级为项目级 `SageLiveTypeWorker`：Sage 导入只发生一次，后续快照通过逐行协议复用同一进程；每个请求仍创建独立用户命名空间，不把前一次文档状态泄漏到下一次。源码、文件名和变量名继续只通过 Base64/固定 `-c` 包装器传递，不拼接到 shell 命令。
- worker 只接受 Native/WSL；运行时路径、分发版变化或项目销毁会关闭旧进程并清理读写线程。取消/30 秒截止会终止 worker；标准输出单行超过 128 KiB 时 fail-closed，stderr/响应均有界，不会让 IDE 阻塞或无限积压。
- 真实 WSL Sage 10.9 连续请求验证：同一 `sage -c` 进程先后处理两个请求，`E` 为 `sage.schemes.elliptic_curves.ell_finite_field.EllipticCurve_finite_field_with_category`，`P` 为 `sage.schemes.elliptic_curves.ell_point.EllipticCurvePoint_finite_field`；第二个请求无需重新导入 Sage。WSL 的 systemd 本地化警告只出现在 stderr，不污染协议。
- 验证：`core:runtime:test` 全量 69 项通过（含 worker framing/MRO 与空查询回归）；`SageTypeProviderTest` Gradle 类级 40 项通过；core/plugin Kotlin 编译通过；`git diff --check` 通过。使用 staging 的 Sage 10.9 v155 合同索引重新 `buildPlugin`（`-Psage.bundle.fullIndex=G:/sage-build/staging-build6/sage-api-curated-type-contracts-v155.json`）；fresh ZIP 为 `plugins/sage-core/build/distributions/sage-core-0.1.0-dev.zip`，SHA-256 `4BA96E6B6AAD183DC6F34E79B7A73024020BEA00DD5A29A2CFE78C4D02423F17`，嵌套 `sage-core-0.1.0-dev.jar` 中的 `sage-api-index.json` 为 140,798,386 字节，且含 `SageLiveTypeWorker`/`SageLiveTypeProbe` 类；仍未做真实 PyCharm UI smoke。
- 额外尝试用 v155 full-index 参数运行 `SageTypeProviderTest` 时 40 项中有 2 项旧 fixture 断言失败：测试导入的是 10.6 的 `sage.matrix.matrix.matrix` 并固定期望 `sage.matrix.matrix.Matrix`，而 v155 10.9 合同把公共工厂迁为 `sage.matrix.constructor.matrix`，且按参数选择 `matrix2`/具体 dense implementation；现有最小 fixture 没有该完整迁移图。这不是 worker/编译错误，未把该次运行记作全绿证据。未带 full-index 的现有 fixture 回归仍为 40/40 通过；后续应补 10.9 constructor/具体矩阵 `.pyi` fixture 后再做 full-index provider 回归。

## 2026-09-10 增量（v158，动态调用返回合同）

- `SageLiveTypeSnapshotService.typeForCall` 已接入 `SageTypeProvider.getCallType` 的静态兜底路径：当 Sage 索引没有唯一可降低的返回合同时，针对顶层调用执行“光标前缀 + `__sage_ide_live_result = <当前调用>`”的合成快照，解析真实类/MRO 后缓存并重启当前文件 daemon。静态合同明确可用时不启动 worker；函数体和 `if/for/try` 等复合语句内调用保持保守跳过，避免改变原始控制流或执行未绑定局部参数。
- 该动态索引仍是文件内容/运行时/调用表达式键控的内存快照，不回写全局 Sage 合同索引，也不把单次参数结果扩散为所有参数的静态类型；因此可以覆盖 `P.log(G)`、未知动态工厂和 `g = gcd(...)` 的当前调用，而条件分支或副作用不确定时仍保持 UNKNOWN。
- WSL Sage 10.9 直接复核 `E=EllipticCurve(GF(11),[1,1]); P=E(0,1); G=E.gen(0); P.log(G)` 返回 `<class 'sage.rings.integer.Integer'>`（值 `12`），证明该调用路径可由动态快照提供 `Integer`，而不是静态公共基类。
- 同一 worker 协议端到端发送合成赋值 `__sage_ide_live_result = P.log(G)`，响应记录为 `sage.rings.integer.Integer`；这验证了 provider 新增的调用表达式快照输入格式和结果解析，而不只是单独运行 Sage 命令。
- 修正 worker 空请求、输出上限和构造器参数校验；新增调用路径注释与回归。`core:runtime:test` 69 项通过，未带 full-index 的 `SageTypeProviderTest` 40 项通过，插件 Kotlin 编译通过，`git diff --check` 通过。使用 v155 full-index 重新构建 ZIP：`plugins/sage-core/build/distributions/sage-core-0.1.0-dev.zip`，SHA-256 `1C62CFF7D643D94513BC2A76C0531761BA46CEC9C75E486D1AE97B128661EB9E`。真实 PyCharm UI smoke 尚未完成。

## 2026-09-10 增量（v159，运行时探测稳定性与后续方案）

- `SageLiveTypeEvidenceCache` 用精确 `file/source/runtime` 键替换“满 64 条整体清空”：成功观测为 LRU，失败观测仅退避 10 秒。同一未完成源文件、Sage 异常或超时不会在每一轮 daemon 分析中重复启动 worker；成功结果仍只作用于该精确快照，绝不泛化成静态 Sage 合同。缓存单测和既有 `SageTypeProviderTest` 40 项均通过。
- 新 ZIP 已用 v155 完整索引构建，SHA-256 `8253D287BC9878AF72CC0FAE0CF036F903A7BDD79E4A611150577DE738650849`。未完成 fresh PyCharm UI smoke；完整 v155 provider fixture 的 2 个矩阵迁移断言仍待更新。
- 更优的下一层不是用一次样本伪造静态类型，而是“真实运行回传”：Sage Run 配置在用户正常运行脚本时以独立、受限协议报告实际执行路径中的变量/调用类，IDE 将其作为带运行时/源码/执行序列指纹的会话证据。静态合同优先；精确编辑快照次之；真实运行证据可覆盖条件分支和动态后端；任一指纹变化或缺少证据仍为 UNKNOWN。这样能消除用户当前上下文中的未知而不把全局 `3569` 个本质非唯一接口错误标成具体类。

## 2026-09-10 增量（v160，正常 Sage 运行类型回传）

- 已实现 v159 的第三层：开启现有 Settings | Tools | SageMath 的 “Enable live Sage type evidence” 后，Native/WSL 的正常 `.sage` 运行只执行用户脚本一次。每次运行创建私有临时 `sitecustomize`，该钩子包装 Sage 原有 `RunFileCmd.run`、在原函数结束后把**新增或改变的全局变量**真实类/MRO写入受限 sidecar；IDE 校验随机 run ID、保存文件原始字节 SHA-256 和 runtime key 后才接纳为本会话证据并重启该文件的分析。没有向 Run 控制台输出标记，也不更新全局 API 索引。
- WSL 使用短固定 `/bin/sh -c` 前缀仅将临时启动目录追加到既有 Linux `PYTHONPATH`，保留用户原有变量；所有用户路径和脚本参数仍为独立 argv，不嵌入 shell 文本，也不重现 Conda 探测脚本。Docker/SSH 继续 fail-closed，未伪造远端文件回传。
- 运行证据只影响当前保存内容：任何未保存编辑都会使源摘要不匹配、立即不再使用旧类型；运行时变更也因 key 不同而失效。`P = ...`、`g = gcd(...)` 等实际执行赋值可在随后获得具体补全；裸 `P.log(G)` 仍由 v158 的当前调用快照负责，二者互补。
- 验证：core runtime 全量 `71` 项通过（默认跳过 1 个外部 WSL 集成测试）；启用该测试后，真实 WSL Sage 10.9 正常运行回传 `P=EllipticCurvePoint_finite_field` 与 `g=Integer`，并断言控制台没有协议 marker；`SageTypeProviderTest` `41/41` 通过（包括“同一保存内容+runtime key 才采用 run evidence”，未保存编辑立即拒绝旧 evidence）；v155 full-index `buildPlugin` 成功，ZIP SHA-256 `D496F0BF4E99FEEDD347FDC4C9E774DFC227BB6F415DB18E24202E34A2342CA9`。真实 PyCharm UI smoke、v155 matrix fixture 的 2 个旧迁移断言仍待完成。

## 2026-09-11 增量（v161，运行后 `P.` 的交互回归）

- 测试发现 v160 的“任意未保存编辑即拒绝 run evidence”会把用户刚键入的 `P.` 也拒绝，因此虽安全却不能实现运行后即时成员补全。现已只在当前未保存文档仍以已运行源码为前缀、且从该前缀到新接收者之间仅有空白时采用该 run evidence；任何已执行部分的编辑、或新语句/重赋值仍 fail-closed。多个历史运行记录只选择最长的匹配前缀。
- `SageTypeProvider` 现在会先对成员接收者根引用尝试运行时证据，再执行普通 qualified-reference 拒绝；服务本身仍拒绝真正属性表达式（`obj.P`），避免把同名全局变量错误用于属性。新增回归精确模拟：运行得到动态 `P` 类型后在末尾键入 `P.log`，接收者仍为 `EllipticCurvePoint_finite_field`；编辑已运行前缀后类型为 UNKNOWN。
- 本轮验证：真实 WSL Sage 10.9 输出 `P=EllipticCurvePoint_finite_field`、`P.log(G)=12`、返回 `Integer`；`SageRunTypeFeedbackTest` `2/2`、`SageTypeProviderTest` `41/41` 通过，`git diff --check` 通过；v155 full-index fresh `buildPlugin` 成功，ZIP SHA-256 `C455A704499C5948A84F0DEF2D01B04371094819F20816ED359780960E3285F0`。当前自动化环境未暴露可控制的 PyCharm 窗口，真实弹窗 smoke 仍需在 PyCharm 安装此 ZIP 后执行。

## 2026-09-11 增量（v162，测试沙盒环境限制）

- 在 v161 已通过后再次强制重跑 IDE 测试，JetBrains 生成的 `...\.intellijPlatform\sandbox\sage-core\PY-2026.2.1\system-test\index\hashfragmentindex` 报 `IntToIntBtree` 存储损坏，导致后续多个测试在索引初始化阶段失败，未出现产品代码断言失败。该目录已确认位于工作区生成沙盒内，但当前执行环境阻止删除操作；不把该次环境失败记为回归失败，也不删除用户/仓库文件。
- 当前源代码未因该尝试保留额外测试改动；重新以 v155 完整索引构建插件成功。fresh ZIP SHA-256 为 `C455A704499C5948A84F0DEF2D01B04371094819F20816ED359780960E3285F0`；下一次干净测试沙盒应重跑 `SageTypeProviderTest`，再完成真实 PyCharm UI smoke。

## 2026-09-12 增量（v163，旧插件原位升级发布链）

- 正式插件身份已迁移为旧 Marketplace ID `com.starnotesxj.sageide`，显示名为 `SageMath Core`、版本 `1.8.0`（高于旧公开 `1.7.9`）；因此它是原位更新，不会与旧插件并存。旧 `G:\Projects\sage-ide-support` 工作树未修改。
- 新增 `sanitize_release_index.py` 和 `validate_release_index.py`：前者将完整索引文档中的构建机绝对路径转换为 `sage/...` 或安全红字，后者校验 SHA-256、Sage 10.9 / Python 3.13、完整条目数和零主机路径。实际 v155 索引已生成到工作区外 `G:\sage-build\release-assets\sage-api-index-10.9-v155.json`，为 `86,339` entries、`106,486,050` bytes、SHA-256 `418a106063f83e965c066e3253cec43500ccc3d7e6ff45c4f1e89b1a098a4ea3`。
- Gradle `publishPlugin` 现在强制完整索引 hash 和 `GITHUB_REF_NAME=v<version>` 双校验；GitHub tag workflow 还会下载同一 SHA 的脱敏索引、再次校验后才打包、发布 Marketplace 并附加同一 ZIP。缺 `PUBLISH_TOKEN`、`SAGE_RELEASE_INDEX_URL` 或 `SAGE_RELEASE_INDEX_SHA256` 时明确失败，绝不发布 32 KiB fixture 降级版。
- 验证：索引工具回归 `2/2`、Python 编译、workflow YAML 解析、`verifyReleaseVersion`、`verifyReleaseFullIndex`、v155 full-index `buildPlugin` 均通过。fresh `sage-core-1.8.0.zip` SHA-256 为 `507D254FD2528239E752B197EF5173EAFC2F20BBFAD697BF7A584D4B4165A278`；嵌套资源为 `106,486,050` bytes，并确认 descriptor 的 ID/name/version 正确。真实 PyCharm UI smoke、远端仓库/秘密变量配置、Marketplace 实际上传仍未进行。

## 2026-09-12 增量（v164，远端发布资产压缩链）

- 已将迁移提交 `2e8bfea` 非破坏性推送到旧公开仓库的新分支 `sagemath-core-1.8.0`，没有覆盖 `master`。GitHub 凭据确认该仓库已有 `PUBLISH_TOKEN`。
- 原始 `106,486,050` byte 索引在当前网络上传超时，因此生成同内容 gzip 发布资产 `G:\sage-build\release-assets\sage-api-index-10.9-v155.json.gz`（`12,810,807` bytes）；release workflow 改为下载 gzip、解压后仍以原始 JSON SHA-256 和完整条目校验为准，不会降低类型索引。
- gzip 索引资产已上传并发布到 `sage-api-index-10.9-v155` release，GitHub 报告大小 `12,810,807`、资产 SHA-256 `92a4bdfff92a780a0928aad451628c3f023dfdf4cccb032d65b673316085a5a1`；旧仓库已设置 `SAGE_RELEASE_INDEX_URL` 与原始 JSON SHA-256 变量。Windows 直连下载在 26 秒后被本机网络重置，未取得新的远端解压验证；GitHub asset digest、本地压缩 hash 与 CI 的解压后原始 JSON hash 三层校验仍可阻止错误发布。下一步推送本次 gzip workflow 更新并推送 `v1.8.0` 标签触发 Marketplace 发布。

## 2026-09-12 增量（v165，首个标签 CI 修复）

- 首次 `v1.8.0` tag CI 在 Linux runner 的第一条 Gradle 命令失败：`./gradlew: Permission denied`（exit 126）；编译、索引下载、Marketplace 上传和 GitHub release 均未执行。
- workflow 的 core/release jobs 现在均在 checkout 后执行 `chmod +x gradlew`。由于 `v1.8.0` 从未上传 Marketplace，修复提交验证后可删除刚创建的远端标签并重新创建同版本标签，不会覆盖任何公开插件版本。

## 2026-09-12 增量（v166，Linux 运行时夹具修复）

- 第二次 `v1.8.0` tag CI 已越过编译阶段，但 `core:runtime:test` 的 71 项中有 5 项失败，均为 Linux `FileRuntimeManifestVerifier` 正确拒绝测试夹具写出的非可执行 `bin/sage`。受影响的 lifecycle/SDK adapter 场景此前仅在 Windows 上执行，Windows ACL 掩盖了缺少 POSIX 执行位的问题。
- 两个测试夹具现在只在 Posix 文件属性可用时为临时 `bin/sage` 增加 `OWNER_EXECUTE`；生产运行时验证没有放宽，仍会拒绝真实 Linux 安装中的不可执行启动文件。Windows 本地 `:core:runtime:test -PrunRuntimeTests=true` 重新通过 `71/71`，`git diff --check` 通过；本机 WSL 没有 Java，Linux 行为将由下一次 GitHub Linux CI 复核。

## 2026-09-12 增量（v167，SageMath Core 1.8.0 已发布）

- `v1.8.0` 已指向 `278f155`，GitHub Actions run `34670708517` 的 core 与 release job 均成功：Linux 编译/模型与运行时测试、Sage 10.9 完整索引下载/解压/原始 SHA 校验、最终 ZIP 构建、`com.starnotesxj.sageide` 的 Marketplace 原位发布和 GitHub Release 附件均已完成。
- GitHub Release：`https://github.com/starnotes-xj/sage-ide-support/releases/tag/v1.8.0`；公开 ZIP `sage-core-1.8.0.zip` 为 `15,701,319` bytes、SHA-256 `fdb240862aa6e2fe052a5b3c065bf14bcfac93694c4e15c8cbbdc9548e2a5757`。重新下载并解开后，嵌入的 `sage-api-index.json` 为 `106,486,050` bytes、SHA-256 `418a106063f83e965c066e3253cec43500ccc3d7e6ff45c4f1e89b1a098a4ea3`，与发布门的完整 v155 索引一致。
- 仍未完成的仅是干净 PyCharm 中的人工交互 smoke；PyPI/stubgen 本次没有发布，因为该独立包没有 CLI 或生成结果改动。

## 2026-09-12 增量（v168，1.8.1 本地候选：运行控制台与本地化）

- WSL 正常运行的实时类型回传仍使用私有 `sitecustomize` 与 `/bin/sh -c` bootstrap，但 `OSProcessHandler` 现在用等价的直接 `wsl.exe -d <发行版> -- <sage> <脚本>` 作为控制台展示命令；因此运行窗口不再暴露 `--exec /bin/sh -c`、`PYTHONPATH` 或 `sage-ide-run-feedback`，实际执行和 sidecar 证据校验不变。
- `liveTypeProbingEnabled` 对新配置默认启用；旧配置缺少一次性迁移标记时也升级为启用，之后用户手动关闭会正常保留。设置页、运行配置编辑器、右键运行/调试动作、Sage SDK 对话框和新建 Sage 文件项改由 `DynamicBundle` 的英文/`zh_CN` 资源包提供文本，随 JetBrains 当前语言包切换。
- 已建立但未发布 `1.8.1` 完整索引候选包：`plugins/sage-core/build/distributions/sage-core-1.8.1.zip`，SHA-256 `06CC8F0522BE4A14BB5EF0B91C17A6454DEF6D8EA7C74B9F12BC398BAAB8B1D7`；嵌入索引 `106,486,050` bytes、SHA-256 `418a106063f83e965c066e3253cec43500ccc3d7e6ff45c4f1e89b1a098a4ea3`。`SageDebugCommandLineStateTest`、`SageRunSettingsConfigurableTest` 定向运行均通过，且 `buildPlugin`、`git diff --check` 通过；尚未在真实 PyCharm 运行窗口人工确认，也未上传 Marketplace。

## 2026-09-12 增量（v169，SageMath Core 1.8.1 已发布）

- `v1.8.1` 已指向 `3b804269`；GitHub Actions run `34684783261` 的 core 与 release job 均成功，包含 Linux 编译/模型与运行时测试、完整 Sage 10.9 索引下载/解压/原始 SHA 校验、最终 ZIP 构建、`com.starnotesxj.sageide` Marketplace 原位发布及 GitHub Release 附件上传。
- GitHub Release：`https://github.com/starnotes-xj/sage-ide-support/releases/tag/v1.8.1`。从该 release 重新下载的 `sage-core-1.8.1.zip` 为 `15,707,868` bytes、SHA-256 `8eedd76343f498e75ca47549234509bcea09d52f515501e004b9468229cca4a0`；嵌套 descriptor 为 `1.8.1`，含中文资源包，嵌入完整索引仍为 `106,486,050` bytes、SHA-256 `418a106063f83e965c066e3253cec43500ccc3d7e6ff45c4f1e89b1a098a4ea3`。
- 仍未完成的仅是干净 PyCharm 的人工 UI smoke（确认运行控制台只显示简洁命令、设置页和右键动作随中文语言包切换）；发布 CI 与远端资产验证不能替代该交互检查。

## 2026-09-16 增量（v170，1.8.2 候选：静态索引与文档内存优化）

- 完整 Sage 10.9 索引原始 JSON 为 `106,486,050` bytes，其中 `57,425` 份 `documentation` 正文约占 `55 MB`。正式 bundle 现在保留所有 `86,339` 条类型、继承、签名和补全合同在主 `sage-api-index.json`，但在打包时无损拆出文档字段；主索引实测为 `47,641,036` bytes，不再含任何 `documentation` 字段。
- 文档按键分入 `64` 个 `sage-api-docs/*.ndjson` 资源桶（最大未压缩桶 `1,084,094` bytes）。Quick Documentation 只读取当前符号的一个桶并有 `128` 条 LRU；补全、成员查询和类型推断不会加载文档正文。`SageApiIndexQuery` 同时移除重复 owner map，并将派生类图缓存限制为各 `1,024` 条；运行时 Sage worker 也已改为仅在实际 `value.member`/成员调用的动态兜底需要时启动、空闲 10 秒关闭。
- 打包脚本初版的 Kotlin DSL `const` 作用域及 sidecar 解码类型错误均已最小修正；不能把它们当作产品失败。验证：`core:sage-api:test -PrunSageApiTests=true --rerun-tasks` 通过；`SageApiDocumentationProviderTest` 定向 Gradle 测试通过；使用 `G:\sage-build\release-assets\sage-api-index-10.9-v155.json` 的完整索引 `buildPlugin` 通过。
- ZIP 内全量 round-trip 已核验：主合同索引和原索引去除文档字段后逐项相等，`57,425` 份 sidecar 文档逐项与原始 JSON 相等；`P.log` 的 `EllipticCurvePoint_finite_field.log` 也从实际包内 sidecar 成功还原。候选包为 `plugins/sage-core/build/distributions/sage-core-1.8.2.zip`，SHA-256 `9294b7bf7fa494ea6da2f0046e81c455b01bb1817d27fdbd8e58e78c2926ebe6`、大小 `19,141,264` bytes；尚未提交、推送或发布，且仍需干净 PyCharm UI smoke。

## 2026-09-17 增量（v171，迁移期间的双 classloader 崩溃）

- 用户 PyCharm 2026.2 日志已确认根因：旧开发插件 `com.starnotesxj.sagemath.ctf.sage-core@0.1.0-dev` 与新插件 `com.starnotesxj.sageide@1.8.2` 同时处于 active classloader，且两者都来自 `...\\plugins\\sage-core`。动态安装新 ID 时未卸载旧 ID，导致 `SageXor` inspection short name、`Sage`/`SageMathPostfix` language ID、`Sage.RunFile`/`Sage.DebugFile` action ID 重复注册；`SageRuntimeService cannot be cast to SageRuntimeService` 及 `SageFileElementType` 的 `ExceptionInInitializerError`/`NoClassDefFoundError` 都是同一冲突的后续症状，而不是 Sage 解析或索引逻辑故障。
- 修复要求：下一包必须从 `1.8.3` 开始在 `idea-plugin` 设置 `require-restart="true"`，阻止拥有 Language、inspection、action、application service 的插件在迁移中热替换；并以 `<incompatible-with>com.starnotesxj.sagemath.ctf.sage-core</incompatible-with>` 阻止旧 ID 与新 ID 在干净启动时共同启用。当前已损坏的 IDE 必须完整退出后才可释放旧 classloader，不能用重新索引或单独关闭文件修复。
- 已实施并验证：根版本已升至 `1.8.3`，正式 ZIP 描述符实测含 `require-restart="true"`、原 Marketplace ID 和旧开发 ID 的 incompatible-with 声明。全索引 `buildPlugin`、`verifyPluginStructure` 均成功；`verifyPluginProjectConfiguration` 只有既有 `since-build=261`/`until-build`/JVM 25 兼容性提示，不是本修复失败。候选 `sage-core-1.8.3.zip` SHA-256 为 `12bd28131326033760dd27c960e7b97956f58c44e73a7918631a470522a7d9dd`，仍未在已损坏进程中安装，必须用完全退出后的干净 PyCharm 做首次启动验收。

## 2026-09-18 增量（v172，普通 Python 离线 Quick Documentation）

- 用户实测普通 `.py` 的 Ctrl+Q 在 WSL SDK 下退化成 `docs.python.org` 外链；根因是 `SageApiDocumentationProvider` 以 Python 的 first provider 注册，却只在 `.sage`/Sage stub 上从本地 PSI 渲染，随后 Python 的远程 SDK provider 无法启动本地 formatter。`itertools.product.__new__` 还来自无 prose 的 typeshed stub，因此只剩外链。
- 修复将本地 PSI docstring 渲染扩展至普通 Python 文件；对没有 docstring 的 CPython/typeshed 声明，新增懒加载的离线 Python 3.13 标准库 sidecar。它由 `tools/python-stdlib-docs/generate_python_docs.py` 在隔离的 Python 运行中读取标准库自身 docstrings，生成 `64` 个 `python-stdlib-docs/*.ndjson` 分桶；本轮 WSL Sage Python 3.13 产物包含 `606` 个模块、`17,615` 条记录、约 `5,499,495` 未压缩字节。编辑器启动、类型推断和补全不读取该 sidecar，Ctrl+Q 才读取目标桶（8 桶 LRU），绝不在编辑器内启动 WSL/Python 或执行用户代码。
- 解析顺序为精确 owner docstring、再精确标准库键、再外层 class 键，因此 typeshed 的 `itertools.product.__new__` 能显示 `product` 的“Cartesian product...”正文及现有语义着色，而项目/第三方的本地 docstring 仍优先。定向 `SageApiDocumentationProviderTest` 5/5 通过，覆盖 Sage index、普通 `.py` 本地 docstring、无 docstring 的 `itertools.product.__new__`、builtin `len` 和代码块渲染；生成脚本 `py_compile`、`git diff --check`、全索引 `buildPlugin`/`verifyPluginStructure` 均通过。根版本已递增为 `1.8.4`，候选 ZIP 为 `plugins/sage-core/build/distributions/sage-core-1.8.4.zip`、SHA-256 `5CB7347862BC6D0DE833C85D358E94A43DC2B853503DC52EE52D53A5488110FF`；内含 64 个 Python 和 64 个 Sage 文档桶。真实 PyCharm UI smoke 仍待在完全重启后的干净进程中完成。

## 2026-09-18 增量（v173，typeshed 构造器 owner 与外链抑制）

- 用户安装 v172 候选后的真实 PyCharm 截图表明，`product()`/`zip()` 的 Ctrl+Q 仍显示继承的 `object.__new__` 文本“Create and return a new object”及 `docs.python.org` 链接；这证明实际 documentation target 可以是基类构造器，不能只用直接 owner 的 qualified name。该反馈比原先的 fixture 假设优先。
- provider 现在从原始调用引用、其 resolved declaration、documentation target 和各自的包含类一起收集 qualified names；构造器 `__new__`/`__init__` 优先用调用目标类的离线标准库正文，再退回 PSI 文本。因此 `itertools.product.__new__` 与 `builtins.zip.__new__` 不会被 `object.__new__` 通用说明遮蔽。`getUrlFor` 对已由本 provider 接管的 Sage/Python 文档显式返回空列表，阻止 remote-SDK fallback 再附加浏览器链接。
- 回归 fixture 现在故意给 `product.__new__` 加同样的通用 docstring，断言富正文仍为 “Cartesian product of input iterables”、不含通用文本、且 URL 列表为空；定向 `SageApiDocumentationProviderTest` 5/5 通过。根版本升为 `1.8.5`；完整索引 `buildPlugin`/`verifyPluginStructure` 成功，候选 `plugins/sage-core/build/distributions/sage-core-1.8.5.zip` SHA-256 为 `EA550521A9D0B9BFBCAD9444D3E21FBE7AE4EAB270CD3B93704DDFCEEFD7A519`，正式 descriptor 已复核 `1.8.5`、`require-restart=true`、含 64 个 Python 文档桶。仍需在 PyCharm 完全重启后对 `product()`/`zip()` 做此真实 smoke。

## 2026-09-18 增量（v174，typeshed 路径与构造器泛化文本修复）

- 用户对 v1.8.5 的新截图证明外链已被正确移除，但 `product()`/`zip()` 仍可能命中 CPython 的通用 `__new__` 文本；原因是实际 PSI qualified name 可能是临时的 `typeshed.stdlib...`，且离线 sidecar 中的 `*.product.__new__`/`builtins.zip.__new__` 记录本身也只有 `Create and return a new object`。
- `SageApiDocumentationProvider` 现在从 typeshed 文件路径 `/typeshed/stdlib/<module>.pyi` 与嵌套 `PyClass`/`PyFunction` 还原稳定的标准库键；对 `__new__`/`__init__` 构造器先跳过构造器记录，直接查所属类文档，再沿父模块回退。普通函数、项目 docstring 和 Sage 索引顺序不变，外链继续返回空列表。
- 新增 product 与 builtins.zip 两个真实 typeshed 路径回归：均断言显示 CPython 丰富正文、不含通用 object 文本、不产生 docs.python.org URL。定向 `SageApiDocumentationProviderTest` 已通过 `7/7`，包含原有 Sage/普通 Python/代码块测试。
- 根版本升为 `1.8.6`；完整 v155 索引 `buildPlugin` 与 `verifyPluginStructure` 均成功。候选包 `plugins/sage-core/build/distributions/sage-core-1.8.6.zip` 大小 `21,050,849` bytes、SHA-256 `16F014078A902690D328D499949E983A45FBC3AE39DAFD6684C6BB24DB8B5DBB`；包内 descriptor 为 `com.starnotesxj.sageide`/`1.8.6`、`require-restart=true`，主 `sage-api-index.json` 为 `47,641,036` bytes，含 `64` 个 Python 和 `64` 个 Sage 文档桶，且 product/zip 文档记录均在包内。提交 `4b120db` 已推送到 `https://github.com/starnotes-xj/sage-ide-support.git` 的 `sagemath-core-1.8.0` 分支；尚未打 `v1.8.6` 发布标签或发布 Marketplace。仍需完全退出并重启 PyCharm 后人工确认 `product()`、`zip()` 的 Ctrl+Q 正文与截图一致。

## 2026-09-18 增量（v175，按接收者类型防止错配文档）

- 用户实测 `intro: list[str]` 的 `intro[4].split(": ", 1)` 被显示为无关的 `Image.split`；这不是文档正文问题，而是 DocumentationProvider 同时收到原始表达式和平台 documentation target 后，无条件信任了错误 target。
- `SageApiDocumentationProvider` 现在对带接收者的原始成员表达式优先使用接收者实际 `PyClassType` 的成员声明；若接收者类型无法证明，则 fail-closed，不再把另一个同名 platform target（如 `Image.split`）作为候选。无接收者的普通函数、构造器和 Sage 索引路径不变。
- 新增两个回归：`list[str]` 场景不会显示错误 `Image.split`；已证明的本地 `Text.split` 接收者会覆盖伪造的 `Image.split` target。`SageApiDocumentationProviderTest` 全部 `9/9` 通过。
- 根版本升为 `1.8.7`；完整 v155 索引 `buildPlugin` 与 `verifyPluginStructure` 均成功。候选包 `plugins/sage-core/build/distributions/sage-core-1.8.7.zip` 大小 `21,051,643` bytes、SHA-256 `9E75C0F136A9888C8CF9D6DC56278C9AE6B77CA70586C04062A31675822656E9`；包内 descriptor 为 `com.starnotesxj.sageide`/`1.8.7`、`require-restart=true`，主索引 `47,641,036` bytes，含 `64` 个 Python 和 `64` 个 Sage 文档桶。定向 provider 测试 `9/9` 通过；待提交并推送 `sagemath-core-1.8.0` 分支。真实 PyCharm 中应确认 `intro[4].split` 显示 `str.split`，而不是 `Image.split`。
## 2026-09-18 增量（v176，GF 工厂联合类型与有限域元素成员补全）

- WSL Sage 10.9 实测：`F = GF(11)` 产生有限域父对象，`c = F(2)` 产生 `IntegerMod_int`，`c.multiplicative_order()` 返回 Sage `Integer`（值 `10`）。
- 根因：`GF` 的多个不同参数形状合同同时可行时，旧的 lowering 直接丢弃全部返回类型；后续 `F(2)` 无法沿具体 `__call__` 合同传播，补全退化为全局 Sage 名称。
- 通用修复：保留不同参数形状且每个分支均为具体类的精确联合返回类型；联合接收者的 `__call__` 和成员补全遍历每个具体类分支。相同参数形状的歧义仍保持 UNKNOWN，避免误报。
- 验证：`compileKotlin`、目标 `SageTypeProviderTest.testFiniteFieldFactoryUnionKeepsElementMembersAvailable`、完整 `SageTypeProviderTest` 均通过；`git diff --check` 通过。尚未重新打 ZIP、安装插件或做本轮全新 PyCharm UI smoke。
## 2026-09-18 增量（v177，GF 补全修复版正式安装包）

- 使用脱敏后的完整 Sage 10.9/Python 3.13 索引 `G:\sage-build\release-assets\sage-api-index-10.9.json`（86,339 entries，SHA-256 `418a106063f83e965c066e3253cec43500ccc3d7e6ff45c4f1e89b1a098a4ea3`）重新执行 `verifyReleaseFullIndex` 与 `buildPlugin`，均成功。
- 可安装包：`G:\sage-build\release-assets\sage-core-1.8.7-gf-completion.zip`；大小 `21,055,659` bytes，SHA-256 `A4CD95479329DE91BFBCC6A514F34369B814965C072774B40B2E4875E06C8B22`。
- ZIP 审计：插件 ID `com.starnotesxj.sageide`、名称 `SageMath Core`、版本 `1.8.7`；嵌入索引 `47,641,036` bytes、86,339 entries、64 个文档桶，未发现 `/home/conda/`、`G:/` 或 `C:/Users/` 主机路径。
## 2026-09-18 增量（v178，安装包中 `.sage` 接收者补全仍退化）

- 用户安装 `sage-core-1.8.7-gf-completion.zip` 后，在 `F = GF(11); c = F(2); c.` 处只看到普通 Python 的 `test.c`，没有 `multiplicative_order`。
- 该现象说明完整索引和 lowering 合同已存在，但 `.sage` 文件的实际 completion contributor 没有获得 `c` 的 Sage 接收者类型，需检查文件类型/贡献者入口及安装包加载路径；不能再归因于 `GF` 索引缺失。
## 2026-09-18 增量（v179，空成员名 `c.` 补全修复与 1.8.8 安装包）

- 根因确认：在 `c.<caret>` 的瞬间，PyCharm PSI 只有接收者引用和 `.`，尚未生成完整的 qualified member reference；旧贡献者因此走了 Sage 根命名空间分支，截图中的 `test.c` 就是该回退结果。
- `SageImplicitCompletionContributor` 现在从光标前的 `.` 恢复接收者，沿同一具体联合类型调用原生和索引成员补全；新增真实 fixture `c.<caret>` 回归，`SageTypeProviderTest` 完整套件通过。
- 为避免用户已安装的 `1.8.7` 被同版本安装器拒绝，根版本升至 `1.8.8`。新包：`G:\sage-build\release-assets\sage-core-1.8.8-gf-completion.zip`，大小 `21,056,677` bytes，SHA-256 `167C63E3ED87FCE330B7868855128778D754CB042376FB537185B8B71958CD37`。
- ZIP 审计：ID `com.starnotesxj.sageide`、名称 `SageMath Core`、版本 `1.8.8`；嵌入索引 `47,641,036` bytes、86,339 entries、64 个文档桶，无主机路径泄漏。尚未进行用户机器上的全新 PyCharm UI smoke。
## 2026-09-18 增量（v180，1.8.8 安装后接收者仍显示 `test.c`）

- 用户安装修复包后仍观察到 `c = F(2)` 上方显示普通 Python 的 `test.c`，`Ctrl+Space` 无效，`Ctrl+Shift+Space` 显示“无建议”，`c.mul` 仍有未解析提示。
- 这说明问题可能发生在 `.sage` 文件类型/解析器或 Sage 类型提供器扩展未被当前 PyCharm 进程加载的更早阶段，不能继续假设只是 `c.` 空成员名处理；需要检查实际加载的插件版本、文件类型归属、扩展注册和日志。

## 2026-09-18 增量（v181，当前日志确认插件已加载但类型边界仍依赖远程 stub PSI）

- 用户当前 PyCharm 日志的最新启动记录明确为 `SageMath Core (1.8.8)`；同一进程没有新的 `SageFileElementType`、插件 classloader 或扩展注册异常。因此这次不能再归因于安装了旧包或双插件冲突。
- 源码审计确认实际缺口：`SageTypeLowering.lowerName()`、`SageApiClassMembersProvider` 和成员补全路径都要求 `SageStubIndex.findClassByCanonicalName()` 返回当前项目可索引的 Sage `.pyi` PSI 类。WSL 远程 SDK 的 skeleton 生成日志存在失败项，完整外部索引虽有 `GF -> FiniteField_*`、`__call__ -> *Element` 合同，却不会在无本地 PSI 类时发布类型；于是 `c = F(2)` 的 Sage 类型返回 null，补全退回普通 Python 的 `test.c`。
- 下一步改为通用的索引合同解析兜底：仅当活动 Sage stub 无法提供 PSI 类时，沿赋值右值/嵌套 Sage 工厂/父对象 `__call__` 合同解析**完整 canonical 具体类集合**，成员补全直接查询这些 owner 的索引成员；不生成公共基类、`Any` 或名称白名单。先加入无 Sage PSI stub 的回归，再重新打包并做 PyCharm 验收。

## 2026-09-18 增量（v182，用户反馈输入延迟/字符堆积）

- 用户安装插件后反馈编辑时字符输入明显变慢、像“输入的字符都满了”。这要求优先做主线程性能回归，不能只验证最终补全结果。
- 重点风险是成员补全每次击键都重新扫描整个文件的引用/目标集合，以及索引兜底沿完整继承图反复查询；下一步需将路径限制为当前接收者、赋值前缀和有界 owner/member 查询，并确认实时 Sage worker 不在每次普通编辑分析中启动。

## 2026-09-18 增量（v183，输入延迟与字符串误补全收敛）

- `SageLiveTypeSnapshotService` 的普通根引用现在不读取运行时证据或快照缓存；赋值目标也不再在每轮 daemon 分析中构造整段文件快照。只有真正的顶层成员接收者才允许进入运行证据/动态探测路径；若完整索引已经证明具体 owner，则不启动 WSL Sage worker。
- `SageImplicitCompletionContributor` 的隐式 `sage.all` 根命名空间改为单字符自动输入早退；自动输入达到两个字符后只用外部索引做前缀过滤，不再扫描 PSI 全量声明，完整 PSI 候选只在明确触发 BASIC/SMART 补全时加载。成员补全仍可自动工作。目标回退扫描限制为不超过 `64 KiB` 的文件，并新增字符串/注释上下文早退，避免在字符串中显示 Sage 候选。
- SMART completion 复用同一精确 Sage provider，因此 `Ctrl+Shift+Space` 不需要重新走一套高成本根命名空间逻辑。生产代码中无 `SAGECOMP` 调试输出。
- 验证：`compileKotlin` 成功；受影响的 `SageTypeProviderTest`、`SageApiDocumentationProviderTest`、`SageCompletionTest` Gradle 测试全绿；`git diff --check` 通过。未筛选的插件全量测试为 `134` 项，其中唯一失败是既有 `SagePythonSdkSemanticTest` 的 `AssumptionViolatedException`（环境假设未满足，不是本次断言失败）。
- 已用完整脱敏 Sage 10.9 索引（`86,339` entries、原始 SHA-256 `418a106063f83e965c066e3253cec43500ccc3d7e6ff45c4f1e89b1a098a4ea3`）构建 `1.8.9` 安装包：`G:\sage-build\release-assets\sage-core-1.8.9-performance.zip`，大小 `21,070,327` bytes，SHA-256 `F7A9588163DF8352F9099319E0DA7FA3D85200B2BC4E5176A6E84D00741BA3ED`；descriptor 为 `com.starnotesxj.sageide`/`SageMath Core`/`1.8.9`，`require-restart=true`，包内主合同索引 `47,641,036` bytes、Sage 文档桶 `64` 个。
- 当前环境没有可控制的 PyCharm 窗口，尚未完成用户机器上的真实输入延迟 smoke。安装该包并完全重启 PyCharm 后，应重点测试：普通 Sage 字符输入、字符串内输入、`c.` 成员补全、`Ctrl+Space` 根补全、`Ctrl+Shift+Space` 智能补全；若仍卡顿，再依据新日志和 CPU/内存曲线定位。

## 2026-09-18 增量（v184，候选图标与换行/成员补全性能）

- 用户新截图显示索引兜底成员没有 Python 原生的彩色语义图标，且 `.sage` 中删除/插入/换行和候选弹出仍慢。索引-only `LookupElement` 现在按 `SageApiSymbolKind` 映射 `AllIcons.Nodes`：方法、函数、属性、常量、类、模块和别名恢复与 Python PSI 一致的图标颜色；根命名空间索引条目也使用同一映射。
- `SageApiIndexQuery.members(owner)` 对不可变索引增加有界 `1024` 项 LRU；同一接收者在 `c.`、`c.m`、删除字符和再次弹出候选时不重复构造 C3 继承结果、去重表和排序列表。
- `SageTypeProvider.getReferenceType` 现在先按右值形状早退：普通字符串、列表、字典等不进入 Sage 合同推断；调用表达式只有在 Sage 根合同、具体 Sage target 或 Sage receiver 有索引证据时才执行 `multiResolveCalleeFunction`/递归返回 lowering。数值字面量、`GF`/`EllipticCurve`/`gcd`/成员调用和二元 Sage 运算仍走精确合同。
- 验证：`core:sage-api:test`、`SageTypeProviderTest`、`SageCompletionTest` 共用 Gradle 回归通过；Kotlin 编译通过。完整索引校验、`buildPlugin`、`verifyPluginStructure` 通过。`git diff --check` 待最终收尾命令再次确认。
- 新安装包：`G:\sage-build\release-assets\sage-core-1.8.10-performance-icons.zip`，大小 `21,072,602` bytes，SHA-256 `F7E8FE6B270724184A819F0FB73E9A3ED5AD72E3B521E4A606872CA1002837FB`；descriptor `com.starnotesxj.sageide`/`1.8.10`，`require-restart=true`，主合同索引 `47,641,036` bytes，Sage 文档桶 `64` 个。
- 仍需用户在完全重启的 PyCharm 中确认真实键入延迟和图标颜色；本环境没有可控 PyCharm UI，不能把自动化 Gradle 结果冒充人工 smoke。

## 2026-09-18 增量（v185，删除/换行卡顿的高亮重启根因）

- 用户最新截图中的“PyCharm 没有响应”已由回归测试复现并定位：`SageLiveTypeSnapshotService` 的 WSL/运行回调在高亮分析尚未结束时调用 `DaemonCodeAnalyzer.restart(file)`，触发 `PSI/document/model changes are not allowed during highlighting`，并会在编辑器删除、换行和候选分析期间反复重启 daemon。
- 修复为不从实时 worker 回调主动重启 daemon。运行回传和隔离快照仍按精确文件/运行时键写入有界证据缓存；下一次用户编辑或显式补全请求直接消费证据，不再在后台强制重新进入 PSI/高亮。普通 Python/CTF 成员没有索引 Sage 合同时也不会启动 WSL worker。
- 这次同时移除了该服务的无用 `DaemonCodeAnalyzer`/`ApplicationManager` 依赖并修正 Kotlin 无意义安全调用警告；插件版本升至 `1.8.11`。
- 验证：`SageTypeProviderTest` 与 `SageCompletionTest` 共 `46` 项通过；`core:sage-api:test -PrunSageApiTests=true` 通过；完整 `verifyReleaseFullIndex`、`buildPlugin`、`verifyPluginStructure` 通过；`git diff --check` 待最终收尾命令确认。
- 新安装包：`G:\sage-build\release-assets\sage-core-1.8.11-unresponsive-fix.zip`，大小 `21,072,619` bytes，SHA-256 `45C96AA7A92372C63C67A03A7FB820658146E2C79E5CD9B9BFD9BA99A49330C2`。包内 descriptor 为 `com.starnotesxj.sageide`/`SageMath Core`/`1.8.11`，`require-restart=true`；主合同索引 `47,641,036` bytes，Sage/Python 文档桶各 `64` 个，未发现主机路径泄漏。
- 仍需用户完全退出并重启 PyCharm 后做人工 smoke：普通 Sage 输入、删除、换行、字符串内输入、`c.` 补全和 `Ctrl+Space`。本环境没有可控 PyCharm UI，不能把 Gradle 结果冒充真实 UI 延迟结论。

## 2026-09-19 增量（v186，1.8.11 远程发布完成）

- 提交 `b6d9d98` 已推送到远程 `sagemath-core-1.8.0`，标签 `v1.8.11` 已创建并推送；GitHub Actions run `35363359464` 的 `core` 与 `release` job 均成功。
- GitHub Release 已发布：`https://github.com/starnotes-xj/sage-ide-support/releases/tag/v1.8.11`，正式附件 `sage-core-1.8.11.zip` 大小 `21,072,634` bytes；CI 使用远程配置的完整 Sage 10.9 索引重新构建并上传，不能用本地候选包替代该发布证据。
- JetBrains Marketplace 插件 ID `com.starnotesxj.sageide` 的上传步骤已成功；Marketplace API 当前返回 `hasUnapprovedUpdate=true`，因此 `1.8.11` 处于 JetBrains 审核队列，待审核完成后才会显示为稳定版本。现有稳定版本接口仍可能暂时返回旧版本，这是平台审核状态，不是发布流水线失败。
