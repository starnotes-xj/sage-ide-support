# SageMath 语义智能覆盖矩阵

> 本矩阵记录当前实现的可验证边界，不把“索引中存在声明”误报为“所有 IDE PSI 场景都已验证”。
> CTF、Notebook 和产品打包不属于本轮 Sage 语义交付范围。

## 状态定义

- **已验证**：有当前源码测试和可复现的测试报告证据。
- **部分已验证**：主路径已实现并有回归，但仍有明确的输入/上下文边界。
- **故意 fail-closed**：元数据存在但无法安全映射时不制造确定类型。
- **未验证**：本轮没有足够的 runtime、产品或发布证据，不能宣称完成。

## 能力矩阵

| 能力 | .sage | 普通 .py | 当前结论 | 主要实现/证据 |
| --- | --- | --- | --- | --- |
| Sage 10.9 全量 API 索引读取 | 外部索引 | 外部索引 | **已验证（开发索引/query）**：84,188 normalized identities、84,221 raw AST declarations、2,843 source files、conflicts=0；当前 staging 目录未提供 envelope/receipt，因此 product-sidecar 验证仍未完成 | core/sage-api query；SageIntelligenceHarnessTest.testConfiguredFullIndexCoverageMatrix |
| sage.all 隐式根补全 | 隐式可用 | 不注入 | **已验证**：根命名空间、external-only symbol、alias、constant | SageImplicitCompletionContributor；testConfiguredFullIndexExposesEveryRootCompletionIdentity |
| 显式 Sage 模块导入/模块成员 | 支持显式导入 | 支持显式导入 | **已验证**；只向 sage.* 模块提供索引成员，native PSI 优先 | SageApiModuleMembersProvider；testExplicitPythonModuleUsesIndexedDirectExports |
| 普通非 Sage Python 隔离 | 不适用 | 不注入 Sage 索引 | **已验证** | SageApiDocumentationProviderTest.testPlainPythonFileDoesNotConsumeSageIndex；provider context gate |
| import alias / root alias | 支持 | 支持显式导入 | **已验证**：alias resolve、completion 和 call chain | SageReferenceResolveProvider；testExplicitAliasImportPropagatesMatrixChainInSageAndPython |
| 类、函数、方法、属性、常量、模块 | 支持 | Sage 显式导入时支持 | **已验证**：索引 kind 保留，重复 Python 属性按有效 callable 视图合并 | SageApiClassMembersProvider、SageApiModuleMembersProvider；full-index kind matrix |
| C3/继承成员与 shadowing | 支持 | Sage 显式类型时支持 | **已验证**：继承 METHOD/PROPERTY/CONSTANT 和 owner resolution | SageApiIndexQuery；testInheritedPropertyAndConstantTypesPropagateThroughIndexedMembers |
| native .pyi PSI 导航/解析优先级 | 支持 | 支持 | **已验证**：外部索引只作 additive 补充，不伪造缺失 PSI 类 | SageApiClassMembersProvider、SageReferenceResolveProvider |
| 工厂/构造器返回类型 | 支持 | 显式导入时支持 | **已验证**：矩阵链和 external-only RealField() 工厂返回 | SageTypeProvider、SageTypeLowering；testConfiguredFullIndexPropagatesExternalFactoryReturnToPsiMembers |
| 方法调用返回类型与链式补全 | 支持 | Sage 显式导入时支持 | **已验证**：唯一安全 known return；嵌套/链式调用有回归 | SageTypeLowering.lowerCallReturnType；harness call-chain tests |
| 参数类型绑定（位置、关键字、默认值、*args/**kwargs） | 支持 indexed callable lowering | 支持 Sage callable lowering | **部分已验证**：确定性 call binding 参与 return-type 传播；未知参数类型不强行选 overload | SageTypeLowering.signatureBindings、lowerSignature |
| 调用点参数提示 / signature help | 支持 | Sage 显式导入时支持 | **已验证（native path）**：索引签名降为平台 PyCallableType，由 Python 原生 codeInsight.parameterInfo 消费；本插件不重复注册 handler | SageTypeLowering.lowerSignature；SageIntelligenceHarnessTest.testNativePythonParameterInfoConsumesIndexedSignature |
| Quick Documentation / signature | 支持 | 仅 Sage stub/source context | **已验证**：signature、参数、return、summary/body；普通 .py 不消费 Sage 文档 provider | SageApiDocumentationProvider；SageApiDocumentationProviderTest |
| 隐式 root / generator sugar 引用解析 | 支持 | 不注入隐式 root | **已验证**：sage.all root 和 sugar RHS generator；注释中的 import 不改变 gate | SageReferenceResolveProvider、SageImplicitCompletionContributor |
| .sage 与 .py alias/call-chain 对等性 | 支持隐式 Sage 语义 | 仅显式 import | **部分已验证**：关键 alias/call-chain 已在两种文件类型覆盖，不等于所有 Python PSI 上下文等价 | testExplicitAliasImportPropagatesMatrixChainInSageAndPython |
| 容器、泛型、literal、union lowering | 支持 | Sage 显式导入时支持 | **部分已验证**：builtin collection、tuple、literal、optional/union 有实现；不能 materialize 时原子失败 | SageTypeLowering.lowerGeneric/lowerLiteral/lowerUnionAtomically |
| 常见算术/一元/幂运算 | `.sage` Sage 运算符语义 | 显式导入的 Sage 类型 | **已验证（native path）**：真实 PSI 回归中 `Integer.__add__`、`__mul__`、`__pow__`、`__neg__` 由 Python 原生 operator resolver 调用，`+`、`*`、Sage `^`、一元 `-` 均保留 `Integer`；无需重复实现 operator provider | SageIntelligenceHarnessTest.testSageArithmeticOperatorsPreserveIndexedIntegerType |
| TypeVar / ParamSpec 元数据解析 | 支持索引解析 | 支持索引解析 | **部分已验证**：scope、bound、constraint、Callable[P, R]、P.args/P.kwargs 解析；variance/default 未建模 | SageStubExtractor、SageTypeRefExpression tests |
| ParamSpec 运行时调用拼接 | 不承诺 | 不承诺 | **故意 fail-closed**：不生成合成参数列表或确定平台类型 | SageTypeLowering ParamSpec branch |
| UNKNOWN / DYNAMIC / union / ambiguous overload | 支持文档/补全元数据 | Sage 显式上下文同样 | **故意 fail-closed**：不传播为确定 receiver/return type | SageApiIndexQuery.uniqueKnownReturnType；full-index unsafe-return assertions |
| arbitrary dynamic metaprogramming、runtime injection 完整等价 | 未验证 | 未验证 | **未验证/非目标**：不承诺绝对精确 | 规格中的 dynamic non-goal |
| real Sage runtime 与产品 bundled full index | 未验证 | 未验证 | **未验证**：full 10.9 index 目前是 external/staged artifact，不是已证明的产品分发 | 当前 HANDOFF.md packaging/provenance blockers |
| x64 product、installer、smoke、release audit | 未验证 | 未验证 | **未验证**：没有 fresh distribution/archive/installer 证据 | 当前 staging logs；FinalCheck 仍受官方 checkout SHA 阻塞 |

## 当前测试证据

### 已通过的源码/插件门禁

当前 fresh SDK-backed plugin gate 的报告为：

- SageIntelligenceHarnessTest：20 tests, 0 failures, 0 errors；
- SagePythonSdkSemanticTest：1 test, 0 failures, 0 errors；
- plugin test reports 合计 80 tests, 0 skipped, 0 failures, 0 errors；
- 证据日志：G:\\sage-build\\sage-semantic-gate-round7-signature.log。

另有 enabled core gate：34 个 SageApiIndexTest 与 6 个 SageTypeRefExpressionTest，0 failures/errors。

本轮数字已由 round-7 enabled plugin gate 刷新；旧 round-6 报告不作为新回归证据。

### 参数提示验证原则

Python 插件已经注册 codeInsight.parameterInfo 的原生 PyParameterInfoHandler。Sage 插件只负责把安全的索引签名降低为真实 PyCallableType/PyCallableParameter，因此不再复制一套容易与 Python UI 漂移的参数提示 handler。回归测试验证的是：

1. Sage call-site 能被 Python 参数信息工具找到；
2. indexed parameter name 在参数列表中保留；
3. 同一个 lowered callable 仍提供确定的 Matrix return type；
4. 参数类型/default 的 lowering 由 SageTypeLowering 与 SDK-backed callable regression 覆盖；本 round-7 call-site regression 使用 bundled matrix(rows: list[list[int]]) -> Matrix，因此直接证明 rows 与 Matrix 返回，而不是凭空构造 UI 文本；
5. 普通 Python 文件不会因索引存在而获得 Sage 结果。

## 明确未覆盖的边界

- 没有宣称所有 PyCharm PSI provider、所有 import 形态、所有 stub 形态、所有 operator/descriptor 场景都已等价。
- 没有宣称 external full index 已进入可发布产品；当前 artifact 含开发机 provenance 路径，发布前必须 sanitize 或显式批准。
- 没有宣称产品打包、installer、x64 smoke、release audit 或 FinalCheck 成功。
- sage.all 的隐式语义只适用于 .sage；普通 .py 仍必须显式 import。
