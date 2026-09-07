# SageMath CTF IDE 交接

> 工作区：`G:\Projects\sage-math-ctf-ide`　更新：2026-09-07
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
- Sage 10.9 / Python 3.13：`entries=85823`、`callableEntries=52747`、`signatures=52451`。
- 返回分类：`UNKNOWN=7857`、`CONCRETE=8695`、`TYPE_VARIABLE=3680`、`UNION_OR_OPTIONAL=4667`、`STRUCTURAL_BASE=95`、`NO_RETURN=333`；`audit_contracts.py` exit 0。
- 最新增量：Cython 无分支/副作用/同型条件分支/多行头规则累计应用 `54` 个；本轮修正引号联合解析并写入 `21` 个源码证明的多实现联合合同，再传播 `99` 个唯一父类实现合同（累计 UNKNOWN 由 `8142` 降至 `7857`）。父合同传播同时覆盖 METHOD/PROPERTY，且只保留最近层唯一同值合同；`*_generic` 仅在与非结构叶类或 `type` 工厂同一联合中允许；单独 `_generic`、`_base`、`_parent`、`_element`、`_factory` 仍拒绝。`PowerSeriesRing(ZZ,'t')` 实跑为 `PowerSeriesRing_domain_with_category`，`AffineSpace(GF(5),2)` 实跑为 `AffineSpace_finite_field_with_category`。
- 测试：全量回归 `311` 项通过（45.974 秒）；本轮聚焦审计/源合同测试、父合同测试与 Cython 测试均通过；`compileall`、`git diff --check` 通过；源/父/Cython 合同重复应用均 `applied=0`。重新运行既有结构化注解流水线报告 378 个文件编辑，但 canonical 声明/UNKNOWN 无变化，未计入新增减少。
- `generate.py` 产生 `missing=14`、已知 `conflicts=2`（本次命令 exit 1，索引仍已生成）；最终 `audit_contracts.py` exit 0。expected-high-value 仅是旧 fixture 覆盖清单，不能冒充 10.9 完整质量门。
- 本轮新增工厂实例合同桥：仅从 `create_object` 的已索引联合中剔除 `_generic`/`_base` 等结构臂，再传播到模块级 `Factory(...)` 绑定；普通索引合同仍保持全量 fail-closed。源码合同 `78657` 条，实际写入 `95` 个缺失返回，重复应用 `applied=0`。重建后索引为 `entries=85825`、`callableEntries=52747`、`signatures=52451`，最终审计 `UNKNOWN=7762`（`7857 -> 7762`），`CONCRETE=8756`、`UNION_OR_OPTIONAL=4696`，审计 exit 0。
- 验证：新增源合同测试 15 项通过；此前同一代码状态全量回归 314 项通过（设置 UTF-8 环境）；本轮再次启动全量回归时 WSL 子进程返回 Windows 环境码 `1073807364`，无测试断言失败输出，故不把该次启动当作新的全量证据。`compileall`、`git diff --check` 通过。

## 4. 下一步与限制

- 继续按 UNKNOWN 分布批量处理动态后端、条件返回、多实现泛型和副作用接口；下一批优先查找“同一具体接收者/参数合同在所有实现一致”的源证据。必须有源码/索引/参数或实际运行的可重复证据，不能用单样本观测或公共基类兜底。
- 完成后重建插件 ZIP，执行 CTF ECC/矩阵/多项式/有限域场景的 fresh PyCharm completion、Quick Documentation、语法糖和运行日志 smoke。
- Gradle 产品构建、installer smoke、`verify-upstream-staging.ps1 -FinalCheck` 尚未完成；官方 checkout 当前 SHA 为 `3b652e714c12009bb69f0a2d2416dad02259fe5d`，与规定基线不符，因此不能宣称产品验收完成。
- WSL Sage 可用；接口包装器的 `sage0` 缺失模块属于外部环境，不作为插件回归证据。
