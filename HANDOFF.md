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
