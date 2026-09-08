# SageMath CTF IDE 交接

> 工作区：`G:\Projects\sage-math-ctf-ide`　更新：2026-09-08
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
- 当前返回分类：`UNKNOWN=7368`、`CONCRETE=8800`、`TYPE_VARIABLE=3691`、`UNION_OR_OPTIONAL=4760`、`STRUCTURAL_BASE=95`、`NO_RETURN=338`；`audit_contracts.py` exit 0。
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

## 4. 下一步与限制

- 继续按 UNKNOWN 分布批量处理动态后端、条件返回、多实现泛型和副作用接口；下一批优先查找“同一具体接收者/参数合同在所有实现一致”的源证据。必须有源码/索引/参数或实际运行的可重复证据，不能用单样本观测或公共基类兜底。当前 `7368` 个 UNKNOWN 中，动态后端/条件分支/副作用接口仍占主要部分，继续保持 fail-closed。
- 完成后重建插件 ZIP，执行 CTF ECC/矩阵/多项式/有限域场景的 fresh PyCharm completion、Quick Documentation、语法糖和运行日志 smoke。
- Gradle 产品构建、installer smoke、`verify-upstream-staging.ps1 -FinalCheck` 尚未完成；官方 checkout 当前 SHA 为 `3b652e714c12009bb69f0a2d2416dad02259fe5d`，与规定基线不符，因此不能宣称产品验收完成。
- WSL Sage 可用；接口包装器的 `sage0` 缺失模块属于外部环境，不作为插件回归证据。
