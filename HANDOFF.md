# Sage IDE Support — 交接提示词（给接手 AI 的完整上下文）

## 任务背景

用户目标：在 PyCharm 中编写 `.sage` 文件时，获得与 `.py` 文件**完全一致**的代码提示体验——语法糖（`R.<x> = GF(2)[]`）不报错、`F.`/`e.` 补全带彩色图标（红 m 方法标志）+ 类型文本 + 形参列表 + Ctrl+Q 中文文档，右键运行用 `sage` 命令（非 Python）。**保持独立的 Sage 文件类型（不是把 .sage 识别成 Python）。**

## 当前状态（v1.6.0 / stubgen 0.8.1，2026-08-17 晚）

四项目整合完成，类型知识全部住在数据层；另有三样「stubgen → Sage PR」贡献已推进（2026-08-17 凌晨）：

| 项目 | 路径 | 状态 |
|---|---|---|
| ① stubgen | `C:\Users\星记\Documents\CTF练习\sage-pycharm-stubgen` | **0.7.1 已发 PyPI**：`FiniteField._first_ngens -> tuple[元素union,...]`（a/x 定型为元素）、三元素类 `__pow__`/`multiplicative_order` 注解、enrich 支持引用本文件声明名 + 内联体保留；降级安装保护 + curated 落盘（0.7.0 起）；工厂声明类型优先收敛；CI 3.11-3.13 + 可信发布全自动 |
| ② 插件 | 本仓库 | **v1.6.4**：Sage-only 后缀模板集（Python 自带模板经 base-language 链自动并入）+ 完整 caret 词法重映射（`SageCaretLexer`：`^`→EXP、`^=`→EXPEQ、`^^=`→XOREQ 合并、`^^`→XOR），`e^254` 按 `__pow__` 类型化；**后缀补全 popup 修复**（`SageFile.getFileType()` 覆写仿 PyiFile + `.b2i`/`.i2b` key 补点与 `\$expr\$` 模板变量 + DumbAware）；**设置页**：Sage 模板独立顶级分组（注册于 Python 族 meta-language `SageMathPostfix`）+ 「+」可新建 Sage 后缀模板（`SageEditablePostfixTemplate` + **sage 精准条件集** v1.6.4）+ 内建可双击改名（isEditable 红线已按用户要求解除，往返完整）+ per-key 预览资源（无多余点、.py.template 命名自带 Python 语法高亮）；inspection 改检测「文本为 ^ 的 EXP / 文本为 ^= 的 EXPEQ」；idea-version 放宽 **261–263.***（2026.1–2026.3 全年）；**GitHub Actions CI**（push 构建 zip 上传 artifact，v* tag 自动挂 Release）；SDK 双模式（CI 下载 `pycharm("2026.2.1")` + `bundledPlugin("PythonCore")`，本地用 D:\JetBrains\PyCharm）；CI 已绿 |
| ③ JetBrains PR #3614 | `G:\Projects\intellij-community-sage-pr` | 2 commits（EP + preparse action），PR 描述已重写，OPEN。**待追加的上游特性请求要点（v1.6.0 popup 根因引出）**：Python 方言感知的语言解析——现状 `PyElementType` 构造硬编码 `PythonFileType.INSTANCE.getLanguage()`（python-parser/PyElementType.java）、`CompositePsiElement/LeafPsiElement.getLanguage() = getElementType().getLanguage()`、`PyFileElementType` 构造传 `PythonLanguage`、`PsiFileImpl.getLanguage() = myElementType.getLanguage()`、`PsiUtilCore.getLanguageAtOffset → findLanguageFromElement → 元素语言`；后果：方言（Sage/Jupyter）文件在一切语言键控机制（LanguageExtension EP：postfix provider/completion 等）中一律解析为基语言，方言专属注册永远不被咨询（本插件探针实证：provider 构造 ✓ 但补全流程零咨询）。请求：让 Py 元素类型/文件元素类型在方言文件中报告方言语言，或让 `LanguageSubstitutor` 覆盖 `getLanguageAtOffset` 路径。承接 #3614「.sage 一等公民」主题。 |
| ④ Sage 上游 PR #42670 | `G:\Projects\sage-fork` | **2026-08-18 三轮评审已处理（head `4e2fa5a`）**：① vincentmacri（CHANGES_REQUESTED）+ nbruin 要求消除转发式 `def __call__` 的每次调用开销 → 改**类体裸注解**（无赋值 → `type(GF).__call__` 仍是继承的 `UniqueFactory.__call__`，零运行时开销）；② vincentmacri 要求去引号 → `integer_mod_ring.py` 加 `from __future__ import annotations` + 无引号前向引用（`IntegerModRing_generic` 同文件后定义）；③ vincentmacri 要求 TC003 豁免不放 pyproject per-file-ignores → 改 import 行本地 `# noqa: TC003` + 理由注释。**关键权衡（血泪）**：`Callable` 必须保持**运行时可见导入**（不进 TYPE_CHECKING）——`get_type_hints` 在模块命名空间求值注解字符串，本文件 TESTS doctest 和 stubgen 都依赖它（TYPE_CHECKING 内导入会 NameError，10.9 overlay 已复现）；ruff 的 TC003 与 UP035 互斥。cxzhong 别名要求同步落地（`FiniteField as FiniteField_base`——PEP 649 下 3.14 惰性求值走活模块命名空间，裸名会解析到工厂实例，CPython 3.14.4 已复现）。验证：mypy + pyright 1.1.332（`types.yml` 钉版）/1.1.411 全推断正确、overlay 10.9 真机 TESTS 全绿、ruff CI 配置双模式通过、3.14 future-annotations 检查通过。评论 issuecomment-5318318884（stubgen/插件项目论证静态类型价值）+ issuecomment-5318501533（去引号 + CI 批准请求）+ issuecomment-5318599868（noqa 移动）。ecl.pyx 崩溃已提 issue #42680。 |
| ⑤ Sage 上游 PR #42672（draft） | `G:\Projects\sage-fork` 分支 `annotate-finite-field-element-returns` | FiniteField 四元素方法 `-> FinitePolyExtElement`；head `12b80f9`（doctest 命名空间两连修：元素类导入 + 类 vs 工厂实例）；https://github.com/sagemath/sage/pull/42672 |
| ⑥ Sage 上游 PR #42675（draft，第四波） | `G:\Projects\sage-fork` 分支 `annotate-factory-function-returns` | PowerSeriesRing → `PowerSeriesRing_generic`、LaurentPolynomialRing → `LaurentPolynomialRing_generic`、QuotientRing → `QuotientRing_generic`；head `fb1a079`（future annotations 修复 3.13 前向引用）；https://github.com/sagemath/sage/pull/42675 |

**⑤⑥ 草稿保持决定（2026-08-17 用户拍板）**：等 #42670 出结果（全绿+评审）再转正，避免 3 个同主题 PR 并行评审返工。转正条件已全部满足并核验过：base=develop 且 MERGEABLE、已推送同步（head `12b80f9` / `fb1a079`）、无 3.14 脆弱断言、fork CI 预验证基本全绿（#42672 修复套件在跑、#42675 已全绿）。转正命令：`gh pr ready 42672` / `gh pr ready 42675`。
**上游注解分批推进计划（2026-08-17 用户要求写文档）**：[docs/sage-upstream-annotation-plan.md](docs/sage-upstream-annotation-plan.md)——波次：PolynomialRing → MatrixSpace → VectorSpace+FreeModule → NumberField → 精度环三兄弟 → FreeAlgebra，每波一个 PR、同模块家族、fork CI 预验证；配套 stubgen **conformance 模式（0.8.1 已发 PyPI）**：`sage-pycharm-stubgen conformance` 把 curated 修补与源码声明交叉核对（基线：sage 10.9 源码 13,413 个带注解可调用项、569 条 curated 全部 unannotated、0 冲突）。
| ⑦ PR #3614 契约评论 | — | generation-report.json 作为 typeInformationGenerator EP 输出契约（issuecomment-5308973640） |
| ⑧ PR #42670 strict-CI 评论 | — | 提议 sage 加 `sage-pycharm-stubgen --strict` 类型桩回归 CI（issuecomment-5308973767） |

**四个已知边角的状态（0.7.1 后）**：
- ✅ a/x 生成元 → 元素类 union（`_first_ngens` declare，数据层修复）
- ✅ `e^(-1)`/`e^254` → 元素类型（三元素类 `__pow__` 注解）
- ✅ `multiplicative_order` → Integer（三元素类注解）
- ✅ 插件版本范围 → 2026 全年（261–263.*）
- 仍待上游：`F.characteristic` Ctrl+Q 中文文档的最终点检

## 历史 bug 与根因（已定位，v1.2.0 修复）

1. **`.sage` 文件中 `GF` 等未导入的 Sage 名字报"未解析引用"**（红线）。
2. **`e.` 补全无彩色图标/类型文本/形参**（`e = F.from_integer(0x57)`），且 `F` 类型断链。

### 根因（v1.2.0 从 JetBrains 源码确认，非猜测）

**`PsiReferenceContributor` 方案从架构上就无效**。证据链（intellij-community-sage-pr checkout）：

- `PyReferenceExpressionImpl.getReference()` 只返回**主引用**（PyImportReference / PyQualifiedReference / PyReferenceImpl），**从不调用 `PsiReferenceService`** → contributor 注册的引用永远不会出现在主引用里。
- 红线检查 `PyUnresolvedReferencesVisitor.visitPyElement`：`PyReferenceOwner`（PyReferenceExpression 是）只 `processReference(node, node.getReference(resolveContext))` → **只看主引用**。
- 类型推断 `PyReferenceExpressionImpl.getType` → `getTypeFromTargets(PyUtil.multiResolveTopPriority(getReference(resolveContext)))` → 同样只看主引用。
- 因此 contributor 完全不影响红线、类型、补全。实测 v1.1.1（warn 级日志）**没有任何 "Sage stub" 日志**——因为打开文件→检查→推断的全程没有人调用过 `getReferences()`。这本身就是 contributor 无效的实证。

### 正确机制（v1.2.0 采用）

**`Pythonid.pyReferenceResolveProvider` 扩展点**：`PyReferenceImpl` 正常解析失败后调用 `resolveByReferenceResolveProviders()`（PyReferenceImpl.java:339/378），把 provider 返回的 `RatedResolveResult` 并入主引用解析结果。这是 PyCharm 官方解析内置名（`PythonBuiltinReferenceResolveProvider`）和 IPython magic（`PyIPythonBuiltinReferenceResolveProvider`，.ipynb 隐式名字，与 .sage 场景同构）的机制。

v1.2.0 组件：

| 组件 | 文件 | 作用 |
|---|---|---|
| SageReferenceResolveProvider | `sugar/SageReferenceResolveProvider.kt` | 主引用兜底解析：.sage 文件 + 无显式 sage.all import + 普通解析失败 → stub 索引查声明；同时处理糖语句 RHS 内生成元引用 |
| SageStubIndex | `sugar/SageStubIndex.kt` | PyFunctionNameIndex + PyClassNameIndex 全局查名 → 路径过滤**精确匹配 `site-packages/sage/` 段**（`/` 和 `\` 都试；**绝不能用 `contains("sage")`——conda 环境名 `envs/sage` 会污染匹配**，v1.2.1 实测 print 被误判为 sage stub）；新增 `findClass` + `isSageStubFile` |
| SageTypeProvider.getReturnType | `type/SageTypeProvider.kt` | 补 stub 缺的返回注解：`from_integer`/`random_element`/`multiplicative_generator` → 三个具体元素类 union（givaro/ntl_gf2e/pari_ffelt，各自都有 to_integer/polynomial/log/multiplicative_order）；`multiplicative_order`/`log` → Integer。`PyFunctionImpl.getReturnType` 与 `PyFunctionTypeImpl.getCallType` 都先咨询本 EP（first-non-null-wins） |

**stub 现状**（用户 WSL sage env，已确认）：`all.pyi:3892 def GF(*args, **kwargs) -> _FactoryReturn_GF`（= `from sage.rings.finite_rings.finite_field_base import FiniteField as _FactoryReturn_GF`）→ F 类型链 OK；`finite_field_base.pyi:291 from_integer` 无注解（docstring "返回: 域元素" stubgen 未映射）→ 需要 getReturnType 补；`element_base.pyi:622 to_integer -> int` 已注解；`_first_ngens -> tuple[Any, ...]` 已注解（a/x 得 Any）。

## 验证/继续调试步骤（v1.2.2 起）

**v1.2.2 已在真实 IDE 验证通过**（idea.log 交叉验证）：GF 无红线、`F.`/`a.`/`e.` 补全带红色 m 图标 + 类型 + 形参、`from_integer -> PyUnionType`（元素类 union）、右键运行正常。git 仓库已初始化（提交 8c48cc5 v1.2.0 / 5b12b2a v1.2.1 / e222af4 v1.2.2）。

安装：`build/distributions/sage-ide-support-1.2.2.zip`（Settings → Plugins → ⚙ → Install Plugin from Disk → 重启）→ 打开 test.sage → 搜 idea.log 中 `Sage:`。

诊断分支（v1.2.2 实测沉淀）：
- `sugar target 'F' factoryType=FiniteField` → F 链 OK；为 null → `context.getType(call)` 断（查 GF 解析/别名）
- `getReturnType ...from_integer -> PyUnionType` → e 链 OK；为 null 且无 class index 日志 → 类名匹配没命中（**qname 的 `sage.` 前缀有无随项目/索引状态变化，已实测两种形态**——必须用简单类名匹配）；有 `class index miss (candidates: 0)` → 元素类未进索引
- `resolved implicit name 'GF' to all.pyi` → 隐式命名空间 OK；`miss for 'print' (candidates: 23...)` 是严格路径过滤的正常拒绝（勿再放宽为 `contains("sage")`——会匹配 conda 环境名 `envs/sage`）
- 无 `Sage:` 日志 → 插件未加载/未装当前版本（查 `Loaded custom plugins ... Sage IDE Support (x.y.z)`）

遗留可选：修 stubgen 的"返回: 域元素"→ 元素类映射（`C:\Users\星记\Documents\CTF练习\sage-pycharm-stubgen\src\sage_pycharm_stubgen\docstring_enrich.py` 的 curated 返回类型表），从源头给 from_integer 等加注解，可删掉插件侧 getReturnType 补丁。生成元 a/x 目前是 Any 或回退 FiniteField（`_first_ngens -> tuple[Any, ...]` 无元素类型信息），如需 `a.` 完整类型可后续精化。

## 项目全景（5 条线）

1. **Sage IDE 插件**（本仓库 `G:\Projects\sage-ide-support`）：Sage 方言（base=Python）+ 真 Sage 解析器（SageParser 覆盖 PythonParser.parseRoot 拦截 IDENT DOT LT）+ typeProvider + 隐式命名空间（v1.2.0 改为 pyReferenceResolveProvider）+ 运行配置（Native/WSL/Docker）+ 图标 + Live Templates。
2. **stubgen**（`C:\Users\星记\Documents\CTF练习\sage-pycharm-stubgen`）：PyPI 包，生成含中文文档的 .pyi stubs。**警告：WSL 里 pip 装的是 0.6.1（无文档增强），不要跑它的 `--install`（会抹掉中文文档）**；WSL 环境已装好 0.7.0 主分支产出的 stubs（98.5% 函数体文档）。
3. **JetBrains PR #3614**（`G:\Projects\intellij-community-sage-pr`，分支 codex/sagemath-type-information，3 commits）：类型信息生成 action + .sage 文件类型 + preparse 转换 action。YouTrack PY-91641。不解决隐式解析（已核实）。
4. **Sage 上游 PR #42670**（`G:\Projects\sage-fork`，分支 annotate-ring-factory-return-types）：GF/Zmod 工厂返回类型注解（stub 里 `_FactoryReturn_GF` 即此产物）。
5. **Bazel 环境**：`.bazelrc-user.bazelrc` 已配（ASCII user.name 修复），测试目标 `//python:python-community-tests_test`，filter 格式 `FQN#method`。

## 关键架构（插件）

| 组件 | 文件 | 要点 |
|---|---|---|
| SageLanguage | `sugar/SageLanguage.kt` | `Language(PythonLanguage.INSTANCE, "Sage")` 双参构造（base 链是全部 Python 服务生效的关键）+ DependentLanguage |
| SageFileType | `sugar/SageFileType.kt` | 继承 PythonFileType（protected ctor），name "Sage" |
| SageParser | `com/jetbrains/python/parsing/SageParser.kt` | **必须在该包**（parseSimpleStatement 是 protected 包可见）；覆盖 parseRoot，`IDENT DOT LT` 前瞻拦截糖语句 → 构建 tuple-unpack 赋值树（targets=[R,x]，EQ 留作 token 叶子——calcTargets 依赖） |
| SageParserDefinition | `parser/SageParserDefinition.kt` | 继承 PythonParserDefinition，覆盖 createParser + getFileNodeType（SageFileElementType）+ createLexer（v1.6.0：`SageCaretLexer { MergingLexerAdapter(超类 lexer, TokenSet(XOR)) }` 双层） |
| SageCaretLexer | `parser/SageCaretLexer.kt` | **v1.6.0 完整 caret 词法重映射（方案 A）**：`^`→EXP、`^=`→EXPEQ、`^^=`→合并单 XOREQ（前瞻 = 第二个同状态 lexer 实例）、`^^`→XOR；文本一律不变、语义对齐 Sage preparser |
| SageTypeProvider | `type/SageTypeProvider.kt` | PyTypeProviderBase.getReferenceType：工厂目标 F ← context.getType(call)；生成元 a/x ← `_first_ngens` 元素类型。**v1.3.0 起无 getReturnType 补丁**——stub 层已带注解。**注册 order="first"**（EP 循环 Ref-非空即短路，last 会被前置 provider 的 Ref(null) 遮蔽） |
| SageSugarAnalyzer | `sugar/SageSugarAnalyzer.kt` | 糖语句判定 = statement 直接子节点含 PyTokenTypes.LT 叶子 |
| **隐式命名空间（v1.2.0）** | `sugar/SageReferenceResolveProvider.kt` + `sugar/SageStubIndex.kt` | **Pythonid.pyReferenceResolveProvider**。教训（血泪）：**PsiReferenceContributor 对 Python 引用无效**——检查/类型推断只看主引用，绝不再走 contributor 路线；provider 里不要调 reference.resolve()（递归）；不缓存 null |
| 运行配置 | `run/*` | WSL 直接调用（无 bash 包装）；Windows 路径 → /mnt/c 转换；Detect 按钮自动检测 |

## 构建/验证命令

```powershell
$env:JAVA_HOME = "D:\Java\jdk-21"
cd G:\Projects\sage-ide-support
& "G:\Bazel\gradle\gradle-8.14\bin\gradle.bat" buildPlugin --no-daemon   # 产出 build/distributions/*.zip
& "G:\Bazel\gradle\gradle-8.14\bin\gradle.bat" runIde --no-daemon        # 实验实例（注意：实验实例退出前不能再跑 buildPlugin 的 buildSearchableOptions——已禁用该任务）
```

用户环境：PyCharm 2026.1.4（`D:\JetBrains\PyCharm`，local SDK）；Sage 在 WSL Ubuntu `~/miniconda3/envs/sage`（python3.13，stubs 在 `\\wsl.localhost\Ubuntu\home\starnotes\miniconda3\envs\sage\lib\python3.13\site-packages\sage`）；用户测试文件 `C:\Users\星记\Downloads\test.sage`（无 import 语句的 Sage 语法糖文件）。

## 已知坑清单（避免重蹈）

- PyCharm 2026.1 插件布局 split：Python 插件 jar 在 `plugins/python/lib` + **`plugins/python-ce/lib/modules/`**（PSI 类在 `intellij.python.psi.jar`）；插件 id 是 `Pythonid`
- Kotlin 必须 **2.3.0**（匹配 IDE 元数据）；JVM toolchain 21
- `PyTokenTypes` 在 `com.jetbrains.python` 包；`RecursionManager` 在 `com.intellij.openapi.util`
- **`PsiReferenceContributor` 对 Python 引用表达式无效**（检查/类型推断只用主引用，见根因）——Python 系扩展点：`Pythonid.pyReferenceResolveProvider`（隐式名字解析）、`Pythonid.typeProvider`（类型）、`PyInspectionExtension`（检查抑制）
- `RunConfigurationOptions` 的 `string()` 委托是模块内部扩展（外部不可用）→ 用 writeExternal/readExternal JDOM
- `ExecutorAction.getActions` / `RunConfigurationBase.setModule` 在 2026.x 已移除
- ExecUtil.execAndGetOutput 返回 ProcessOutput（非 ExecOutput）；startProcess 在 EDT 执行（勿阻塞）
- 测试运行器坏（PathClassLoader/GradleWorkerMain 冲突）——测试源码保留但 `enabled=false`
- 图标用 renpe 插件的 PNG（sagemath.png + @2x），不要用 pluginIcon.svg（40×40 会渲染异常）
- GF 隐式解析不得劫持用户显式 import（当前用 `file.text.contains("from sage.all import")` 快速门控）
- `PyFunctionTypeImpl.getCallType` / `PyFunctionImpl.getReturnType` 都是 EP first-non-null-wins → 插件 provider 必须对不处理的 callable 返回 null
- **Python 方言的语言键控陷阱（v1.6.0 popup 根因）**：`PyElementType` 硬编码 `PythonFileType.INSTANCE.getLanguage()`，PSI 元素的 `getLanguage()` 一律返回 **Python**（`PsiUtilCore.getLanguageAtOffset`/`PsiFile.getLanguage()` 同理）→ 所有按语言收集实现的机制（LanguageExtension EP、postfix provider 收集等）对 .sage 文件看到的都是 Python，**注册在方言语言上的 EP 永远不被咨询**。方言插件要用这类功能必须**注册到基语言** + 在实现里按文件类型/PSI 自行把关（见 `SagePostfixTemplateProvider` 注册 language="Python" + `isApplicable` 的 SageFile 门）。
- **`PyFileImpl` 的文件类型/图标硬编码（v1.6.1 popup 根因，必读）**：发行版 `PyFileImpl` 有两处无条件 Python 身份覆写（`getIcon()` 返回 Python 图标、**`getFileType()` 返回 `PythonFileType.INSTANCE`**；fork 源码 253-256 行 + javap 实证）。`getFileType()` 不是装饰性的：`PostfixLiveTemplate.copyFile` 用 `file.getFileType()` 经 `LanguageUtil.getLanguageForPsi` 推 **copy 文件的语言**——方言文件 PSI 若不覆写，copy 会被基语言解析器创建成基语言 PSI，一切「containingFile is 方言File」的门都恒 false。**方言文件 PSI 必须仿 `PyiFile` 覆写 `getFileType()` 为方言 FileType**（`getLanguage()` 保持 Python 不动）。本插件 `SageFile` 已覆写。
- **Postfix 模板 key 必须带点（平台契约）**：`PostfixTemplate` 标准构造 = `"." + name`；`computeTemplateKeyWithoutContextChecking` 回走**含终止符**（`m.ZZ` → key `".ZZ"`），lookup string = 带点 key，matcher 按带点 key 精确匹配。传裸 key（如 `"b2i"`）→ popup 条目在 `CompletionResult.wrap` 被过滤丢弃 + 展开时 key 不等报「Template not found by key」。自定义 key 一律写 `".b2i"` 形式。
- **后缀补全 popup 机制速查（2026.2.x，源码已定论）**：PyCharm 里 `ide.completion.group.enabled` 默认关 → `isShowAsSeparateGroup()` 恒 false → 走 `LiveTemplateCompletionContributor.showCustomLiveTemplates` → `CustomLiveTemplateBase.addCompletions`（`PostfixTemplatesCompletionProvider` 早退）。Java 的 `completion.command.suffixProvider` 属 command completion 特性，Python 无 CommandCompletionFactory 走不到，Python 的 '.' 靠 key 自带点隐式处理——方言插件无需注册 suffixProvider。`isTerminalSymbol` 必须对 `.`(46)/`!`(33) 返回 true（回走含终止符）。
- **MetaLanguage 要点（v1.6.2）**：① `MetaLanguage.all()` 每次查询都调 `MetaLanguageProvider.getLanguage()`——provider 形式必须返回**单例**（每次 new 会撞 `Language` 构造的「同 class 已注册」检查，第二次即抛 `ImplementationConflictException`）；直接 `<metaLanguage implementation=.../>` EP 形式每插件只实例化一次，无此问题；② **`metaLanguageProvider` EP 在 2026.1 不存在**（262 才有）——跨 261–263 只能用 deprecated 的直接 `com.intellij.metaLanguage` EP；③ MetaLanguage 的 ID 必须全局唯一：避开任何现成语言 ID（撞车 = 插件加载失败，如 JetBrains 商城 SageMath 插件的 `SageMath`），且不要复用本插件已注册语言（Sage/Python）的 ID——否则**其他** LanguageExtension EP 对同 key 的查询也会收集到同 key 的注册实现（parserDefinition 等，有连带风险）。独立 ID（如 `SageMathPostfix`）零附带影响。
- **可编辑后缀模板三件套**：设置页「+」新建模板要求 provider 实现 `createEditor`（null 或本插件 editable 类型时返回编辑器，否则返回 null=不弹）+ `readExternalTemplate` + `writeExternalTemplate`（PostfixTemplateStorage 的读写往返都走这两个；缺了新建的模板重启即丢）。Python 的 `PyPostfixTemplateEditor` 构造限死 `PyPostfixTemplateProvider`（final）不可复用——但平台 `PostfixTemplateEditorBase` 接受任意 provider，照 PyEditor 复刻即可；可编辑模板复用 `PyEditablePostfixTemplate`（构造接受泛型 provider）+ 子类覆写 `getExpressions` 加方言文件门。
- **设置页预览资源三件套（v1.6.5 血泪）**：每个模板类的 `resources/postfixTemplates/<SimpleClassName>/` 下 **description.html + before/after.py.template 三份缺一不可**。before/after 由 `PostfixTemplateMetaData.decorateTextDescriptorWithKey` 读（`$key` 占位符会被**带点 key 原样替换**，per-key 类硬编码裸名才能避免 after 多一个点）；description 由 `PostfixTemplateMetaData.getResourceLocation` 按 SimpleClassName 静态查找——**模板类覆写 `getDescription()` 对设置页无效**（`PostfixDescriptionPanel` 只读资源），缺 description.html 每次点击模板就一条 SEVERE「Resource not found」。生成器脚本与 TestPostfix 断言都必须覆盖三件套。
- **v1.6.0 词法包装教训（更新版，含 bugfix）**：① 2026.x 的 `MergingLexerAdapter` 是 **MergeFunction 新设计**（`MergingLexerAdapterBase`）——合并 run 整段折叠为**一个** token 且类型保持原类型（无 `MergedTokenType`；旧设计的 `TokenSet.contains` 分支保留即可兼容）；② **`MergingLexerAdapterBase.advance()` 是惰性的**（只清缓存，底层推进在下一次 `getTokenType()`）——锁步双实例会静默落后、peek 到陈旧 token；跳过多 token 必须显式「`tokenType`+`advance()`」逐次进行；③ 区分 `^`/`^^` 靠 **token 文本长度**不靠类型；④ 一 token 前瞻用**按需重启且每次 fresh instance** 的 scratch lexer（`start(同 buffer, delegate.tokenEnd, bufferEnd, delegate.state)` + 读首 token）——**复用实例必死**：`PythonIndentingProcessor.start()` 不清空 `myTokenQueue`，一旦某次重启落在空白上，processIndent 塞入的 INDENT/SPACE pending token 永久残留，后续前瞻全返回陈旧 token（v1.6.0 第三轮 bug 的根因，血泪）；单字符运算符不改 flex 状态所以 state 安全。

## 验证成功标准

在正式 PyCharm（WSL sage SDK 已配）打开 test.sage：
1. ✅ `GF` 无红色未解析标注（v1.2.0 起，用户确认）
2. ✅ `e.` 补全项带红色 m 图标 + 类型文本 + 形参列表（v1.2.2 起；**v1.3.0 数据层路径已复验**：用户确认 + 日志证实 v1.3.0 会话零 getReturnType 行，类型来自 stub union 注解）
3. `F.characteristic` Ctrl+Q 显示中文文档（F 已定型 FiniteField，待最终确认）
4. ✅ 右键 Run 通过 sage 命令执行成功（用户确认）
5. ✅ 语法糖行无波浪线（用户确认）
6. ✅ 项目树 `.sage` 文件显示 Sage 图标（v1.3.2 起，用户确认）
7. **v1.6.0 待验证（本轮交付，用户侧 IDE 实测）**：`e^254` 无错误且 hover 类型为元素类（`__pow__` 链）；`x ^^ y`/`x ^^= y` 无语法错、按异或/异或赋值解析；bytes 上下文的 `x ^ y`/`x ^= y` 仍标红、quick fix 到 `^^`/`^^=`；**后缀 popup 同时含 Sage 集与 Python 内建集（v1.6.1 已修 copy 文件语言链，理论应弹——待用户装 1.6.1 实测 `m.ZZ`/`m.CC`/`m.b2i`）**；`R.<x> = GF(2)[]` 糖语句不受影响。

**v1.5.0（2026-08-17）**：新增 **Sage 后缀补全**（`SagePostfixTemplateProvider`）——`.ZZ/.QQ/.RR/.CC/.SR/.Integer/.N/.factor/.show/.vector/.matrix` + CTF 数论 15 个（`.euler_phi` 等）+ `.b2i`/`.i2b`（`SageFixedPostfixTemplate` 固定参数模板类）。**本轮三连修（9c25ed8）**：① `isTerminalSymbol` 必须对 `.`(46)/`!`(33) 返回 true（字节码实证：`PostfixLiveTemplate` 循环中任一 provider 返回 false 直接 return null → popup 永不弹出，这是「看不到后缀选项」的真根因）；② `SageParserDefinition.createLexer` 用 `MergingLexerAdapter(TokenSet(XOR))` 合并 `^^`（Python 词法器给两个 `^` token → parser 报「应为表达式」）；③ `SageXorInspection`（红色 ERROR + quick fix `^`→`^^`）：bytes 字面量/调用/注解名/喂 bytes(...) 时才报，sage 幂不误报；`^=` 的提示改用 `x = x ^^ y`（`^^=` 暂未解析支持）。
- **两个排队任务（v1.5.1/v1.6.0）——已于 2026-08-17 晚完成，见下方「v1.6.0」节**：
  1. ✅ **Provider 改为 Sage-only 模板集**（`getTemplates()` 不再合并 `PyPostfixTemplateProvider().getTemplates()`）。字节码实证：`PostfixLiveTemplate` 用 `LanguagePostfixTemplate.allForLanguage(language)` 自动收集语言+全部基语言的 provider → Python 自带模板会自动并入 .sage，无需手动合并（手动合并反而有重复风险）。
  2. ✅ **完整 caret 词法重映射（方案 A）**：`MergingLexerAdapter` 之上再加一层 `LexerBase` 包装（`SageCaretLexer`）：单字符 `^`(XOR) → `PyTokenTypes.EXP`（文本保留 "^"）、`^=`(XOREQ) → `PyTokenTypes.EXPEQ`、`^^=`(XOR 后紧跟 XOREQ) → 合并为单个 XOREQ（一 token 前瞻：第二个同状态同步 lexer 实例）。`SageXorInspection` 检测目标改为「文本为 `^` 的 EXP token / 文本为 `^=` 的 EXPEQ token」，quick fix 相应为 `^`→`^^`、`^=`→`^^=`（`^^=` 已可解析，不再用 `x = x ^^ y` 提示）。
- 设置页后缀预览显示 `list(...)` 是平台约定（`$EXPR$` 占位符示例=列表字面量 "list"），非 bug。

## v1.6.0（2026-08-17 晚）——两项排队任务完成

**构建已绿**（2026-08-17 19:54，gradle buildPlugin，无警告；含 v1.6.0-bugfix 四轮：惰性 advance 修复 + 后缀模板资源/类重做 + 前瞻 scratch 状态泄漏修复 + **popup 语言注册修复（Python 注册 + SageFile 门）**）：产物 **`build/distributions/sage-ide-support-1.6.0.zip`**（93,948 字节）。已核验 zip 内层 jar 含 `SageCaretLexer.class`、`SageCallWrapPostfixTemplate`/`SageBytesToIntPostfixTemplate`/`SageIntToBytesPostfixTemplate` 及各自的 `postfixTemplates/<类名>/{description.html,before.py.template,after.py.template}`。**未 commit/未 tag**——发版照旧流程：升版本（已升 1.6.0）→ commit → `git tag v1.6.0` → push（CI 双发布）。**回归测试**：`.lexer-test/` 下 TestLexer（PythonLexer 链）、TestIndentLexer（真实 PythonIndentingLexer 链）、TestLookahead（前瞻插桩对照）、TestSageParse（**真实解析器全文复现**）、TestPostfix（key 计算/拷贝解析/适用性判定）——均用 `D:\JetBrains\PyCharm\jbr\bin\java` 跑，假平台环境搭法见各文件头。

**版本已升至 1.6.0**（build.gradle.kts 两处 + plugin.xml + change-notes）。改动文件：`SagePostfixTemplateProvider.kt`（Sage-only）、新增 `parser/SageCaretLexer.kt`、`SageParserDefinition.kt`（接入包装器）、`SageXorInspection.kt`（新检测目标 + `^^=` quick fix）、`plugin.xml`（版本/注释）、README（`^`/`^^` 表 + lexer 语义说明）。

### ① Sage-only 后缀模板集

`getTemplates()` 只返回 `sageTemplates`。依据（HANDOFF 已记）：`PostfixLiveTemplate` 用 `LanguagePostfixTemplate.allForLanguage(language)` 沿 base-language 链收集所有 provider → Python 自带模板自动并入 .sage。Python 自带模板与 Sage 集无 key 冲突。

### ② 完整 caret 词法重映射（方案 A）——`SageCaretLexer`

新文件 `src/main/kotlin/com/starnotesxj/sageide/parser/SageCaretLexer.kt`：`LexerBase` 包装在 XOR 合并层**之外**（`SageCaretLexer { MergingLexerAdapter(super.createLexer(project), TokenSet(XOR)) }`）。重映射表（与 Sage preparser 运行期语义逐一对应，文本全部不变）：

| 文本 | 入流 | 出流 | Sage 预解析语义 |
|---|---|---|---|
| `^` | XOR(1 字符) | EXP | 幂 `**` |
| `^^` | XOR(合并 run) | XOR | 异或 `^` |
| `^=` | XOREQ | EXPEQ | 幂赋值 `**=` |
| `^^=` | XOR + XOREQ | **合并为单个 XOREQ** | 异或赋值 `^=` |

实现要点（**必读，防返工**）：
- **一 token 前瞻 = 按需「重启」一个同工厂 scratch lexer**（`myAhead.start(delegate.bufferSequence, delegate.tokenEnd, delegate.bufferEnd, delegate.state)` 后读第一个 token）。**绝对不要用「两个实例锁步 advance」**——见下方 v1.6.0-bugfix 血泪：`MergingLexerAdapterBase.advance()` 是**惰性**的（只清缓存，底层真正推进发生在下一次 `getTokenType()`），锁步实例会悄悄落后、peek 到陈旧 token。重启式前瞻每次只花一次 flex reset（O(1)），且结果只用于 `=== XOREQ` / is-XOR 判定，即使 indent 栈重置产生 INDENT 之类的怪 token 也正确落入「非 XOREQ → EXP」分支。
- 区分 `^` 与 `^^` 靠**文本长度**（`tokenEnd - tokenStart == 1`），不靠 token 类型：2026.x 平台（本地 SDK 2026.2.1 已 javap 实证；fork master 同）的 `MergingLexerAdapter` 是 **MergeFunction 新设计**——合并 run **整段折叠为一个 token 且类型保持原类型**（`MergingLexerAdapterBase` + `MergeFunction`，旧的 `MergedTokenType` 已从 platform 删除）。`TokenSet.contains` 分支仍保留，兼容旧平台每个 caret 单独标 MergedTokenType 的情形。
- `^^=` 合并 token：type=XOREQ、start=主实例当前 token start、end=scratch 实例首 token end；`advance()` 时主实例要跳过**两个** delegate token——同样因为惰性 advance，必须显式「`tokenType` 查询 + `advance()`」×2（只调两次 `advance()` 等于两个 no-op，XOREQ 会重复出现）。
- `SageXorInspection` 相应翻转：二元→`findChildByType(EXP)` 且文本 `"^"`；增强赋值→`findChildByType(EXPEQ)` 且文本 `"^="`；quick fix 新增 `^=`→`^^=`（**`^^=` 现已可解析**，v1.5.0 的「写 `x = x ^^ y`」提示退役）。`x ^^= y` 本身不再被报。
- 已知退化输入：`^^^`（Sage 预解析为 `^ **`）仍是一个 XOR token——无人写，文档已注明。
- 连带收益：`e^254`/`2^8` 现在按 EXP 解析 → 自动走 stubs `__pow__` 类型链（元素类 union 注解），无需 inspection 兜底；`.sage` 里 `^` 的 AST 语义与运行期一致。

### v1.6.0-bugfix（2026-08-17 晚）——`^^=` 报「应为表达式 / 无法赋值给运算符」

**症状（用户实测）**：`e^254` 类型 ✓、`x ^^ y` 无语法错 ✓，但 `e ^^= b` 报「应为表达式」+「无法赋值给运算符」。

**根因**：`MergingLexerAdapterBase.advance()` 是**惰性**的——只把内部缓存置 null，底层 lexer 的真正推进发生在**下一次 `getTokenType()`**（`locateToken` 里 `orig.advance()`）。初版 `SageCaretLexer` 假设「第二个同状态实例与主实例锁步 advance」：每步 advance 里对前瞻实例调 `myAhead.advance()`（惰性 no-op），而它的 `tokenType` 直到第一次 peek 才被查询 → 前瞻实例的底层停在**文件开头**，`lookAhead()` 返回陈旧 token（第一个 peek 甚至返回文件第一个 token），`^^=` 的 XOREQ 永远探测不到 → 流变成 EXP + EXPEQ 两段 → Python parser 产出「`e ** <应为表达式>` + `^= b` 增强赋值（目标=二元表达式）」→ annotator 报「无法赋值给运算符」。另一处连带 bug：合并后 `advance()` 连调两次 `myDelegate.advance()` 也是惰性 no-op，XOREQ 会重复出现。

**修复**：前瞻改为**按需重启 scratch lexer**（见上方实现要点）；合并后跳两 token 改为显式「`tokenType` + `advance()`」×2。**已用独立词法测试验证**（`.lexer-test/TestLexer.java`，SDK jar 直跑，勿用 JDK21——python-ce 插件 jar 是 class v69/Java 25，须用 `D:\JetBrains\PyCharm\jbr\bin\java` 跑）：`e ^^= b` → 单 XOREQ[2-5]、连续 `^^=` 各自合并、`e^2^3` → EXP+EXP、`x ^ ^= y` 不合并、`^^`/`^=`/糖语句流不变，全绿。

**idea.log 交叉验证（2026-08-17 晚）**：当前 PyCharm 会话 17:18:36 启动、加载的是**初版（带 bug）1.6.0**（`Loaded custom plugins: ... Sage IDE Support (1.6.0)` 行 42058）——用户的 `^^=` 报错即来自该构建；会话内 `com.starnotesxj` 日志行全部 WARN 级、**0 条 ERROR**（无异常，纯逻辑 bug）；17:21/17:28 的隐式解析（zip/str/range）与 bytes/len/print 拒绝均正常。修复版 zip（17:40:53）**尚未安装**——日志无重启记录；用户需 Install Plugin from Disk → 重启（两个构建版本号同为 1.6.0，日志无法区分，须以行为复测为准：重启后 `e ^^= b` 无「应为表达式/无法赋值给运算符」即新构建生效）。

**教训**：`MergingLexerAdapterBase` 系（含 PythonIndentingLexer）都是惰性 advance——任何「保持两个 lexer 同步」的代码必须每次 `tokenType` 查询后才能算真推进；做一 token 前瞻就用重启式，别维护锁步状态。

### v1.6.0 解析器级复现（2026-08-17 深夜，决定性证据）

`.lexer-test/TestSageParse.java`：**真实全链路**（PythonIndentingLexer → MergingLexerAdapter(XOR) → SageCaretLexer → **PsiBuilderImpl → SageParser**）在假平台环境（Proxy Application + `Extensions.setRootArea` + 注册 `PythonDialectsTokenSetContributor`/`com.intellij.lang.ast.factory` EP + `PyElementTypesFacadeImpl` 假服务 + `LazyParseableElement.putUserData(CharTable.CHAR_TABLE_KEY)`）下复现解析。

**最终根因（第三轮 bugfix）——前瞻 scratch 实例的状态泄漏**：用户实验发现「最小文件干净、全文文件红」→ 全文喂真实解析器**精确复现**：`m ^^=1` 被解析成 `EXP(^)+EXPEQ(^=)` 两段（binary target `m ^` + ERROR_ELEMENT「应为表达式」+ annotator「无法赋值给运算符」）→ `.lexer-test/TestLookahead.java` 插桩对照（fresh scratch vs **复用同一 scratch**）锁定：**`PythonIndentingProcessor.start()` 不清空 `myTokenQueue`**——复用的 scratch 只要某次前瞻的重启点落在空白字符（全文里 `x^8 + ...` 的第 3 个 `^` 即触发），`setStartState→processIndent` 就向队列塞入 INDENT/SPACE pending token 且**永不清理**；此后每次前瞻都返回队列头的陈旧 token（含陈旧偏移），`^^=` 处前瞻读到 SPACE 而非 XOREQ → 合并失效。最小文件在 `^^=` 前没有任何落空白的前瞻 → 干净。**修复**：`lookAhead()` 每次 `delegateFactory()` **新建实例**（免疫队列/f-string 栈/indent 栈/addFinalBreak 等一切内部残留；每次 `^` 一次 flex 对象分配，代价可忽略）。已用 TestSageParse 全文验证：`m ^^=1` → 干净 `Py:AUG_ASSIGNMENT_STATEMENT` + 单 `Py:XOREQ '^^='`。**教训（写入已知坑）**：任何「重启式复用 lexer 实例」在 Python 系 lexer 上都不安全——`start()` 不清 pending queue；要做一次性前瞻只能 fresh instance。

**已核验**：用户当前安装 jar（18:51:28，103,054B）== 18:43 构建；18:51 会话无本插件异常。**Marketplace 验证（verifyPlugin，本地等效商城 Verification 页）**：`pluginVerification { ides { create(PyCharm, "2026.1.4"); create(PyCharm, "2026.2.1") } }`（`PyCharmCommunity` 已停发、2026.3 无发布版——两坑已踩掉）。**最终结果（19:30，全绿）**：261（2026.1.4）**Compatible ✓**、262（2026.2.1）**Compatible ✓**。修复过的真 bug：`SageXorInspection` 曾用 `PyAugAssignmentStatement.getAssignmentTarget()`（2026.2 才有的方法，261 会 NoSuchMethodError）→ 改为经 `node.node.getChildren(null)` 读第一个 PyExpression 子节点（跨版本安全）。遗留 6 处 experimental API 警告（PyAstTargetExpression.getName / PyAstReferenceExpression.isQualified / getReferencedName——不阻塞，后续可显式转型 PSI 接口消除）。报告在 `build/reports/pluginVerifier/{PY-261.26222.68,PY-262.9437.214}/`。

### v1.6.0-bugfix 第二轮（2026-08-17 深夜）——设置页崩溃 +「list」预览 + `^^=` 交叉验证

**用户报告三问题**：`m ^^=1` 仍红、后缀补全 popup 不弹、设置页后缀预览全变 "list"。逐一定位：

1. **`^^=` 已修复且经双重实证**：① 新词法测试 `.lexer-test/TestIndentLexer.java`——用 **Proxy 伪造 `Application` + `Extensions.setRootArea(new ExtensionsAreaImpl(假 ComponentManager))` + 注册 `PythonDialectsTokenSetContributor` EP** 后，**真实 `PythonIndentingLexer`** 链路（`MergingLexerAdapter(XOR)` → `SageCaretLexer`）对用户原文 `m = 1\nn = 1\nm ^^=1\nprint(m)\n` 输出正确流：`XOREQ '^^=' [14-17]` 单 token ✓；② idea.log 17:49:20 栈：`PyTypeCheckerInspection$Visitor.visitPyAugAssignmentStatement` 正在访问**增强赋值语句**——证明 PSI 已正确解析 `^^=`（不再是语法错）。**用户看到的红**可能与 17:49 的 `PsiInvalidElementAccessException`（PyTypeChecker 崩溃，栈全在 Python CE 代码、`Plugin to blame: Python Community Edition`，疑似 2026.2.1 自身 bug）有关——待用户给准确红字确认。
2. **设置页 "list" 预览 + 崩溃（真根因，官方文档硬性要求）**：官方 SDK 文档要求每个模板类提供 `resources/postfixTemplates/<SimpleClassName>/{description.html, before.*.template, after.*.template}`（https://plugins.jetbrains.com/docs/intellij/postfix-templates.html）。我们复用 `PyCallWrapPostfixTemplate`（类在 python 插件、其静态资源是 `expr.list`/`list(expr)`）→ 所有 Sage wrap 模板的 Before/After 预览全显示 "list"；`SageFixedPostfixTemplate` 无资源 → `PostfixDescriptionPanel` 抛 `Resource not found` SEVERE + `PostfixTemplatesConfigurableUi` 协程 UnhandledException（idea.log 17:52:22）。**修复**：自有类 `SageCallWrapPostfixTemplate`（资源用 `$key` 占位符）+ 固定模板拆成 `SageBytesToIntPostfixTemplate`/`SageIntToBytesPostfixTemplate` 两个子类（各自独立静态 before/after 资源）。
3. **`postfixTemplates.xml` 损坏条目**：用户设置里存了一条 `.ZZ` 的 PostfixChangedBuiltinTemplate 但无 `<template>` 子节点（我们 provider 未实现 writeExternalTemplate → 半写条目）。已从用户配置删除；**预防**：全部模板 `isEditable() = false`（不做 live-template 往返就不允许编辑，杜绝再损坏）。
4. **popup 不弹——最终根因（2026-08-17 深夜，探针实证）**：加探针日志（provider 构造/getTemplates/isTerminalSymbol/preCheck/isApplicable）实测：**provider 构造 ✓ 但补全流程从不咨询**（m.ZZ 输入零探针），而 m.if 正常 → 追源码确认：**`PyElementType` 构造硬编码 `PythonFileType.INSTANCE.getLanguage()`**（`CompositePsiElement/LeafPsiElement.getLanguage() = getElementType().getLanguage()`），`PsiUtilCore.getLanguageAtOffset` / `PsiFile.getLanguage()` 对 .sage 全部解析为 **Python** → 补全流程 `allForLanguage(Python)` 永远看不到注册在 Sage 语言上的 provider。**修复一（19:54 版）**：`plugin.xml` 的 `codeInsight.template.postfixTemplateProvider` 注册语言从 `Sage` 改为 **`Python`**；两个模板类的 `isApplicable` 加门 `context.containingFile is SageFile`。**⚠️ 用户实测（19:56 会话，jar 哈希核验 == 19:54 构建）：`m.ZZ`/`m.CC` 仍不弹——此修复不充分，popup 问题仍未闭环。** 下一步诊断（已备好工具，勿重走弯路）：重加探针（构造/getTemplates/isTerminalSymbol×每次调用/preCheck/isApplicable）确认新注册后 provider 是否被咨询、`isApplicable` 是否 true；若 true 而弹窗仍空 → 失败在**补全匹配层**（`PostfixTemplatesCompletionProvider` 的 `MyGroupPrefixMatcher`/`restartCompletionOnPrefixChange` 前缀机制：Java 有 suffixProvider 使 '.' 进入前缀，Python 无 suffixProvider 却 .if 正常——机制未完全解明，需反编译 `CompletionInitializationContext`/`LookupImpl` 的补全前缀推导）；若 isApplicable false → 查 `context.containingFile is SageFile` 门（copy 文件由 `PsiFileFactory.createFileFromText` 生成，需确认走的是 `SageParserDefinition.createFile`）。**教训**：Python 方言插件的「语言键控」功能（LanguageExtension EP）绝不能只注册方言语言——运行期语言解析对 Python 方言一律返回 Python，必须注册到基语言 + 在实现里按文件类型自行把关。

### v1.6.1（2026-08-17 深夜）——后缀补全 popup 不弹：最终根因、修复与证据链

**症状回顾**：`m.ZZ`/`m.CC` 无弹窗；`m.if` 在 .sage 正常、`x.str`/`x.if` 在 .py 正常（用户 19:56 会话实测，jar 核验 == 19:54 构建）。

**补全前缀匹配层机制定论**（读官方源码 G:\Projects\intellij-community-sage-pr，与 2026.2.1 SDK 字节码逐类核对一致；origin/master 已同步至 2026-08-17，94 个新提交未触碰相关文件）：

1. **模板 key 自带点**：`PostfixTemplate` 标准构造 = `"." + name`（`.if` 的 key 是 `".if"`；`isEditable` javadoc 明说 key starts with `.`）。lookup string = 带点 key，弹窗文本 = trimStart 后裸名。
2. **前缀推导**：`PostfixLiveTemplate.computeTemplateKeyWithoutContextChecking` 回走**包含终止符**（`m.ZZ` → key `".ZZ"`）→ 会话 matcher `cloneWithPrefix(".ZZ")` → `CamelHumpMatcher(".ZZ")` 精确匹配 lookup `".ZZ"`。**Java 的 suffixProvider 属 2025.3+ command completion 特性，Python 未注册 CommandCompletionFactory 走不到——Python 的 '.' 靠「key 自带点」隐式处理，无需注册 suffixProvider**。
3. PyCharm 里 `ide.completion.group.enabled` 注册表默认关 → `isShowAsSeparateGroup()` 恒 false → 走经典路径（`LiveTemplateCompletionContributor.showCustomLiveTemplates` → `PostfixLiveTemplate.addCompletions`；`PostfixTemplatesCompletionProvider` 早退）。
4. **copy 文件链（真根因）**：`PostfixLiveTemplate.copyFile` 用 **`file.getFileType()`**（文件 PSI 的！）经 `LanguageUtil.getLanguageForPsi` 推 copy 文件语言。而发行版 **`PyFileImpl.getFileType()` 硬编码返回 `PythonFileType.INSTANCE`**（与 getIcon 同族的发行版覆写，fork 源码 253-256 行 + javap 实证）→ 我们的 `SageFile` 继承它 → 对 .sage 文件解析出 **PythonLanguage** → `createFileFromText(name, Python, …)` 走 **PythonParserDefinition** → copy 是普通 **PyFileImpl 而非 SageFile** → 每个模板的 `context.containingFile is SageFile` 门**恒 false** → Sage 模板全部被拒 → `.ZZ` 不弹而 `.if`（无此门）正常。**与用户症状完全吻合。**

**修复（1.6.1）**：
- `SageFile` 覆写 `getFileType()` → `SageFileType.INSTANCE`（**照抄官方方言先例**：`PyiFile` 覆写 `getFileType() = PyiFileType`；`PyDoctestFile`/`PyTypeRepresentationFile` 同模式）。`getLanguage()` **故意不动**（维持 Python——插件设计就是 .sage 在 PSI 层读作 Python，只在需要 Sage 身份处覆写，避免扰动既有正常功能）。copy 链随即变为 SageLanguage → `SageParserDefinition.createFile` → SageFile → 门通过。
- **`.b2i`/`.i2b` key 补点**：`SageFixedPostfixTemplate` 传的裸 key `"b2i"`/`"i2b"` 违反平台「key 带点」契约 → 匹配层拿 `".b2i"` 对 lookup `"b2i"` 过滤必丢弃 + 展开时 `findApplicableTemplate` key 不等。已改为 `".b2i"`/`".i2b"`。
- `SageFixedPostfixTemplate` 补 **DumbAware**（索引期间 `isDumbEnough` 恒 false 会跳过这两个模板）。

**证据链**：
- `.lexer-test/TestPostfix.java` 重建假平台（FileElement 根 + `setPsi(SageFile)` + AbstractFileViewProvider/PsiManagerEx stub + `com.intellij.lang.parserDefinition` EP 注册 Sage/Python 两个 ParserDefinition + fakeBus/loadClass 代理），真实复现 `m.ZZ` 链：key='.ZZ' → copy 解析 → context=Py:IDENTIFIER 'm' → 28/28 模板 `isApplicable -> true`（`containingFile=SageFile type=Sage isSageFile=true, super=true`）→ selector 1 表达式。修复前同 harness 门恒 false（type=Python）。
- 五个 `.lexer-test` 全绿 + `gradle buildPlugin` + `gradle verifyPlugin`（2026.1.4/2026.2.1 Compatible）。
- 红线复核：仍 language="Python" 注册、isEditable=false、自有模板类（未复用 PyCallWrapPostfixTemplate）。

**探针已移除**（诊断版 20:48 构建含全套探针；1.6.1 为干净版）。若用户侧仍不弹：重加探针（构造/getTemplates/isTerminalSymbol×每次/preCheck/isApplicable + SageParserDefinition.createFile 探针）→ 让用户输入 m.ZZ 读 idea.log。

### v1.6.2（2026-08-17 深夜）——设置页：独立分组 + 可新建 Sage 后缀模板

**用户实测（v1.6.1 七组清单）**：除第 7 组外全绿（popup/展开/.py 隔离/预览均 ✓）。第 7 组两个问题：① 设置页「+」新建模板弹窗点 SageMath 无反应；② Sage 模板挂在 Python 组下，未与 ts/js/py/SQL 并列。

**根因与修复**：

1. **新建模板无弹窗**：`PostfixTemplatesCheckboxTree.addTemplate` 调 `provider.createEditor(null)`，null → 不弹（默认实现返回 null）。Python 的编辑器 `PyPostfixTemplateEditor` 构造参数限死 `PyPostfixTemplateProvider`（final，无法复用）。修复：自建 `SagePostfixTemplateEditor`（继承平台 `PostfixTemplateEditorBase`——它接受任意 provider；条件列表/建模板逻辑照搬 PyEditor），产出 `SageEditablePostfixTemplate`（继承 `PyEditablePostfixTemplate`，加 SageFile 门：`getExpressions` 里 `containingFile is SageFile` 否则空——用户新建的模板只在 .sage 生效，与内建一致）。provider 补三件套：`createEditor`（null 或 SageEditable 类型时给编辑器）、`readExternalTemplate`（`PostfixTemplatesUtils.readExternalLiveTemplate` + readExternalConditions + topmost → SageEditablePostfixTemplate）、`writeExternalTemplate`（`PostfixTemplatesUtils.writeExternalTemplate`）——**没有 read/write 往返，新建的模板重启即丢**（PostfixTemplateStorage 走 provider 的这两个方法）。内建模板 `isEditable=false` 不动（红线）。
2. **分组挂在 Python 下**：设置树按 `LanguageExtensionPoint.getKey()`（EP 的 language 属性）分组；而 popup 收集 `allForLanguage(Python)` 只走基语言链——注册在 Sage（Python 方言）下永远不被咨询（v1.6.0 已实证）。修复：**meta-language 机制**（平台为此设计，`MetaLanguage` javadoc：「在 plugin.xml 的 language 属性里指定 meta-language 的 ID」）：`SagePostfixLanguage : MetaLanguage("SageMathPostfix")`，`matchesLanguage = isKindOf(PythonLanguage)`；provider 注册改为 `language="SageMathPostfix"` + **直接注册 deprecated 的 `<metaLanguage implementation=.../>` EP**（现代替代 `metaLanguageProvider` 在 2026.1 **不存在**——verifyPlugin 对 261 报 unresolved class，这是唯一跨 261–263 的注册形式）。效果：Python 键查询经 `LanguageExtension.buildExtensions` 的 meta 分支收集到我们（popup ✓）；设置树按 key 分组 → 独立顶级节点 "SageMathPostfix" ✓；`.py` 里照样被收集但模板被 SageFile 门挡住 ✓。
   - **血泪（写入已知坑）**：`MetaLanguage.all()` 每次查询都调 `MetaLanguageProvider.getLanguage()`——若走 provider 形式必须返回**单例**（每次 new 会撞 `Language` 构造的「同 class 已注册」检查，第二次即抛 `ImplementationConflictException`，症状是语言查询全炸）；直接 EP 形式每插件只实例化一次，无此问题。
   - **ID 选择**：避开 `Sage`/`Python`/`SageMath`。`SageMath` 可能与 JetBrains 商城 SageMath 插件的语言 ID 撞车（Language 构造会抛冲突、整个插件加载失败）；`Sage`/`Python` 会让**其他** LanguageExtension EP 的 Python 查询也收集到本插件注册在相同 key 下的实现（parserDefinition 等，虽然实践中被排序遮蔽但有风险）。用独立 ID `SageMathPostfix` → 全平台零附带影响（TestPostfix 契约测试实证：`allForLanguage(Python)` 含 Sage provider、`allForLanguage(Language.ANY)` 为 0）。
   - 树节点标签 = `Language.findLanguageByID(key)?.displayName ?: key`——meta-language 不进语言注册表，故标签就是 "SageMathPostfix" 字面量。

**验证**：`.lexer-test` 五测试全绿（TestPostfix 新增第 6 节 meta-language 收集契约：`allForLanguage(Python) collected 1, contains sage = true`、`allForLanguage(Language.ANY) collected 0`；harness 同步注册 `com.intellij.metaLanguage`/`metaLanguageProvider`/`postfixTemplateProvider` 三个 EP + ast.factory EP 类名修正为 LanguageExtensionPoint）+ buildPlugin + verifyPlugin 双版本 Compatible。**用户侧待测（1.6.2 清单）**：① 设置页树出现独立 "SageMathPostfix" 顶级组（含 28 个模板，不再挂在 Python 下）；② 「+」→ SageMath → 新建模板弹窗正常，建一个 `.foo` → `m.foo` 在 .sage 弹出并展开、.py 不弹；③ 新建模板重启 IDE 后仍在（存储往返）；④ 删除新建模板正常；⑤ 旧 1.6.1 全清单回归（popup/展开/.py 隔离/预览）。

### v1.6.3（2026-08-17 深夜）——四修：b2i/i2b 变量丢失、预览多余点、双击编辑、编辑器条件 sage 化

**用户实测 1.6.2 报告四个问题**，逐一定位修复：

1. **`.b2i`/`.i2b` 展开后丢变量**（`m.b2i` → `int.from_bytes(expr, "big")`——"expr" 是字面文本未替换）：`SageFixedPostfixTemplate` 的 templateText 用了 `${StringBasedPostfixTemplate.EXPR}`（Kotlin 插值出**裸词 "expr"**，没有 `$expr$` 模板语法）——`TemplateImpl` 找不到 `$expr$` 变量段 → 原样输出。修复：改字面 `\$expr\$`（`"int.from_bytes(\$expr\$, \"big\")\$END\$"` / `"int(\$expr\$).to_bytes(\$END\$, \"big\")"`）。TestPostfix 第 7 节断言模板串含 `$expr$`。
2. **预览 after 多余点**（`.CC(expr)`）：平台预览把资源里的 `$key` **原样**替换为**带点 key**（`PostfixTemplateMetaData.decorateTextDescriptorWithKey`，无去点钩子）——共享类的 26 个 key 无法避免。修复：**per-key 子类**（`tools/gen-wrap-template-classes.ps1` 生成 26 个 `Sage<Key>PostfixTemplate` 类 + 52 个 per-key before/after 资源，硬编码裸名；base `SageCallWrapPostfixTemplate` 改为 open + 覆写 `getDescription()` 共享家族描述）。before 保持 `expr.CC`（带点是正确的前态），after 变为 `CC(expr)`。
3. **双击编辑不可用**：内建模板 `isEditable()=false` 所致。**红线解除（用户 v1.6.3 明确要求）**：v1.5.0 设 false 的原因是「provider 未实现 live-template 往返 → 半写损坏条目」；v1.6.2 已补全 `createEditor`/`readExternalTemplate`/`writeExternalTemplate`，且平台 `PostfixTemplateStorage.loadState` 对无 `<template>` 体的 builtin 条目有 wrapper 兜底（改名不丢）→ 半写风险消除。恢复平台默认 `isEditable=true`（与 Python 内建一致：双击弹**改名**对话框——`DefaultPostfixTemplateEditor` 只改 key，正文编辑仅对 `SageEditablePostfixTemplate` 开放；改名经 `PostfixChangedBuiltinTemplate` 持久化）。新红线：**不得重新加回 isEditable=false**（往返已完整）。
4. **新建模板编辑器的条件用 Python 的**：`fillConditions` 改为 sage 集——**v1.6.4 精简为「对 sage 判断准确」的最小集**：字符串/list/dict/set/tuple（sage 用 builtins 容器，Py 条件可正确判断）/非 None（纯结构判断）+ **sage 常用类型即点条件**（`PyClassCondition` 预设：Integer/Rational/RealNumber/ComplexNumber/FinitePolyExtElement/Polynomial/Matrix/FreeModuleElement，继承匹配，经 stub 索引生效）+ 类选择器/输入类。**逐条审计结论（Py 类别在 sage 的准确性，v1.6.4 记录）**：number ✗（sage Integer/Rational/RealNumber 在类型系统里不继承 builtins int/float/complex → PyNumberExpression 只命中 Python 数值字面量）；iterable ✗（sage 容器 Matrix/FreeModuleElement 等未注册 abc.Iterable）；boolean ✗（只命中 builtin bool 字面量，符号布尔不中）；exception ✗（Python 专用）；string/list/dict/set/tuple ✓；non-none ✓。故前四类**不提供**（提供即误导），数值类需求由 sage 类条件覆盖。

**变量约定（用户拍板，勿再改）**：内建模板（StringBasedPostfixTemplate 家族）引用目标表达式用 **`$expr$`（小写）**——平台注册名 `StringBasedPostfixTemplate.EXPR="expr"`（PyCharm 自带 `PyCallWrapPostfixTemplate` 字节码实证同款）；**新建模板编辑器**（EditablePostfixTemplate 家族）用 **`$EXPR$`（大写）**——平台注册名（`EditablePostfixTemplate.expand` L177 `addVariable("EXPR",…)`）。变量查找**大小写敏感**（`TemplateState` L1131 `getVariableNameAt(j).equals(name)`），两类各自保持自己的拼写，混用不解析。

**预览语法高亮机制（已核实，自动生效）**：`PostfixDescriptionPanel.showUsages` 按 `ResourceTextDescriptor.getFileName()`（资源名去 `.template` 后缀 → `before.py`）经 `FileTypeManager` 解析出 **PythonFileType** → `ActionUsagePanel.reset` 挂 **Python 语法高亮器**。因此只要资源命名保持 `before/after.py.template`（与 Python 内建一致），预览自动有 Python 语法高亮 + `<spot>` 蓝色选区；可见颜色取决于文本内容（纯标识符只有默认色 + 选区，与 Python 内建同款表现）。**生成 per-key 资源时勿改此命名。**

**验证**：`.lexer-test` 五测试全绿（TestPostfix 第 7 节新增：b2i/ZZ 模板串含 `$expr$`、per-key 预览资源可解析且 after 无点）+ buildPlugin + verifyPlugin 双版本 Compatible。**用户实测（1.6.3）**：① `m.b2i`/`m.i2b` 展开正确、② 预览无点且带高亮、③ 双击改名生效——**三点均通过**。

### v1.6.4（2026-08-17 深夜）——新建模板编辑器条件精简为 Sage 精准集

**用户问**：条件有必要这么多吗？像 Python 那样分类可以吗？Python 的类别在 sage 下能判准吗？**逐条审计 Py 条件的 `value()` 实现 × sage stub 类型系统**：

| Py 类别 | sage 下判准？ | 依据 | 处理 |
|---|---|---|---|
| number | ✗ | sage `Integer`/`Rational`/`RealNumber` 不继承 builtins `int`/`float`/`complex`（`PyTypeChecker.match` 走继承链）→ 只命中 Python 数值字面量 | 移除 |
| iterable | ✗ | sage 容器（Matrix/FreeModuleElement 等）stub 未注册 `abc.Iterable` | 移除 |
| boolean | ✗ | 只命中 builtin bool 字面量，符号布尔不中 | 移除 |
| exception | ✗ | Python 专用 | 移除 |
| string / list / dict / set / tuple | ✓ | sage 直接使用 Python builtins 容器 | 保留 |
| non-none | ✓ | 纯结构判断 | 保留 |

**最终条件集**：字符串/list/dict/set/tuple/非 None（6 通用）+ 8 个 sage 类型即点条件（`PyClassCondition` 继承匹配，经 stub 索引：Integer/Rational/RealNumber/ComplexNumber/FinitePolyExtElement/Polynomial/Matrix/FreeModuleElement）+ 选择类/输入类。**红线**：不得把 number/iterable/boolean/exception 加回（提供即误导）。

**验证**：`.lexer-test` 五测试全绿 + buildPlugin + verifyPlugin 双版本 Compatible。**用户侧待测（1.6.4）**：新建模板编辑器条件列表 = 上述精准集（不再有数字/可迭代/布尔/异常），其余沿用 1.6.3 清单回归。

### v1.6.5（2026-08-17 深夜）——设置页预览面板 SEVERE「Resource not found: description.html」

**症状（用户 1.6.4 实测 + idea.log 实证）**：用户 23:42:42 会话加载 `Sage IDE Support (1.6.4)`（日志确认），23:44:52 打开设置页后缀模板树点击 `.CC`/`.Integer` 时，`PostfixDescriptionPanel` 抛 `java.io.IOException: Resource not found: postfixTemplates/SageCCPostfixTemplate/description.html`（SEVERE ×2，每次点击一次）。

**根因（平台源码定论，非猜测）**：`PostfixDescriptionPanel.readHtml` → `getDescription(actionMetaData.getDescription())`，而 `PostfixTemplateMetaData` 构造用 `template.getClass().getClassLoader()` + `getSimpleName()`，`getResourceLocation` 拼 `postfixTemplates/<SimpleClassName>/description.html`——**设置页描述走静态 per-class 资源，根本不调用模板的 `getDescription()` 方法**（我们 base 类覆写共享家族描述的那个方法只在别处生效）。v1.6.3 的生成脚本 `tools/gen-wrap-template-classes.ps1` 只为每个 per-key 类生成了 before/after 两个资源，**漏了 description.html**（b2i/i2b 两个固定模板类手写资源时带了，wrap 家族 26 个全缺）→ 每次点击一个 SEVERE。描述面板显示空白描述，但 before/after 示例面板不受影响（showUsages 仍执行）——用户看到的是「描述区空 + idea.log 刷 SEVERE」。

**修复（1.6.5）**：
- 生成脚本为每个 per-key 类补 `description.html`（内容 = 该 key 的一句话描述 `<code>ZZ(expr)</code>` 形式），重新生成 26 个文件。
- `TestPostfix` 第 7 节新增断言：**遍历 provider 全部模板**，断言每个类的 `postfixTemplates/<SimpleClassName>/description.html` 资源可解析且非空（正是本次漏网的盲区——原断言只查了 3 个 key 的 before/after）。
- 版本升 **1.6.5**（build.gradle.kts 两处 + plugin.xml + change-notes）——1.6.4 已装到用户 IDE，升版本让 `Loaded custom plugins ... (1.6.5)` 可区分新旧构建。

**教训（补入已知坑）**：设置页预览的三件套是 **before/after/description 三份资源缺一不可**——before/after 走 `PostfixTemplateMetaData.decorateTextDescriptorWithKey`（带 `$key` 替换），description 走同一目录下按 SimpleClassName 的静态查找；模板类覆写 `getDescription()` **不影响设置页**（`PostfixDescriptionPanel` 只读资源）。生成器/测试都要覆盖三件套。

### v1.6.6（2026-08-17 深夜）——设置页描述中文化

**用户反馈（1.6.5 实测）**：设置页描述区有文字了，但是英文，要求中文。**修复**：三处散文描述全部中文化——① 生成脚本的 per-key `description.html`（「用 sage.all 的 ZZ(expr) 包裹所选表达式（.sage 文件中无需导入）」）重生成 26 个；② b2i/i2b 两个手写 `description.html`（「CTF 字节转整数 / 整数转字节」）；③ base 类 `FAMILY_DESCRIPTION`（`getDescription()` 覆写，设置页虽不走它，保持一致性）。popup 条目文本（name/example = `int.from_bytes(expr, 'big')` 等）是代码形态，保持不译。版本升 **1.6.6**（1.6.5 已装到用户 IDE，升版本让日志可区分）。

**已发布（2026-08-18 凌晨）**：用户全清单实测通过 → README（EN/zh）补「可定制的 Sage 后缀模板集」与 zh 版 `^^=` 行/词法说明 → commit → `git tag v1.6.6` → push → **CI 双发布成功**：GitHub Release [v1.6.6](https://github.com/starnotes-xj/sage-ide-support/releases/tag/v1.6.6)（zip 附件 131,607 字节）+ `gradle publishPlugin` 已上传商城（1.6.6，可能仍在审核）。发布前累计 commit：v1.6.1 `d626000` → v1.6.2 `b0424f0` → v1.6.3 `4a8d453` → v1.6.4 `a657e95` → v1.6.5 `74465db` → v1.6.6 `0d54739` → README `11fad8f`。

### v1.7.0（2026-08-18）——右键 New 菜单的「Sage File」入口

**用户问**：① .sage 里能直接写 Python 代码吗（Python 补全 + Sage 补全共存、正常运行）？② 装插件后目录右键 New 菜单没有新建 SageMath 文件的选项。

**① 答复（已写入 README「混写」节）**：可以——`.sage` = 纯 Python + sage.all 注入 + preparser，Python 代码、Python 补全、Sage 补全、后缀补全全部共存，运行走 `sage` 命令；唯一注意 `^` 是幂（异或写 `^^`）。用户确认以后密码学题全部直接新建 .sage。

**② 修复（平台机制，两件套）**：
- 资源 `src/main/resources/fileTemplates/Sage File.sage.ft`——`FileTemplatesLoader`（platform lang-impl）扫描各插件 classpath 的 `fileTemplates/` 目录，`<名>.<扩展>.ft` 自动成为默认文件模板（name="Sage File"、extension="sage"，经 velocity 渲染），建出的文件天然是 SageFileType 的 .sage 文件。
- `SageFileTemplatesFactory`（`com.intellij.fileTemplateGroup` EP，Maven/DevKit 插件同款机制）：`FileTemplateGroupDescriptor("SageMath", SageIcons.SAGE)` + `FileTemplateDescriptor("Sage File")`——New 菜单出现 "SageMath" 组内 "Sage File" 条目。
- 模板内容：两行注释提示（`^` 是幂 / `^^` 是异或 / sage.all 隐式注入）。
- **条目名本地化（用户要求：中文界面显示「Sage 文件」）**：`SageBundle`（`com.intellij.DynamicBundle`）+ `messages/SageBundle.properties`（EN）与 `SageBundle_zh_CN.properties`（zh）——IDE locale 自动选文件；descriptor 覆写 `getDisplayName()` 返回 bundle 消息（**getFileName() 保持模板名 "Sage File" 不变**，`FileTemplateManager.getTemplate` 才能找到资源；DevKit 插件同款模式：`new FileTemplateDescriptor(name, icon) { override getDisplayName() = DevKitBundle.message(...) }`）。**v1.7.1 推翻**：用户实测（IDE locale=zh-CN、localization-zh 语言包）条目仍英文——见 v1.7.1 节，此方案的 bundle 文件已删除。
- 版本升 **1.7.0**（新功能，非 bugfix）。

**验证**：jar 内 `fileTemplates/Sage File.sage.ft` + plugin.xml `<fileTemplateGroup>` EP ✓（解包核验）；五测试全绿；verifyPlugin 双版本 Compatible。**用户实测（1.7.0）**：右键 New 出现条目，但**显示英文 "Sage File"**（中文界面应为「Sage 文件」）→ v1.7.1 修复。

### v1.7.1（2026-08-18）——New 菜单条目名本地化（replacer 路径）

**症状（用户 1.7.0 实测）**：New 菜单条目显示英文 "Sage File"，中文界面（localization-zh，i18n.locale=zh-CN 已从用户 options 确认）未显示「Sage 文件」。

**根因（2026.2 平台行为定论，发行版 jar 字符串扫描实证）**：`com.intellij.fileTemplateGroup` EP 的 **New 菜单消费端在 2026.2 已不存在**——全 lib jar 扫描 `FileTemplateGroupDescriptor` 的引用只有 Settings 页（`AllFileTemplatesConfigurable`/`FileTemplateTabAsTree`）；用户看到的条目来自 `CreateFromTemplateGroup`（New → 从模板，`NewGroup` 组里的 `NewFromTemplate` 引用），其 `getChildren` 遍历 `FileTemplateManager.getAllTemplates()`（插件 jar 的 `fileTemplates/Sage File.sage.ft` 自动成为 default 模板），action 文本 = **`FileTemplate.getName()`（资源文件名 "Sage File"，无法本地化）**——descriptor 的 `getDisplayName()` 覆写与 properties bundle 都**不被这条链路调用**。

**修复（1.7.1，官方钩子）**：`com.intellij.createFromTemplateActionReplacer` EP（`CreateFromTemplateGroup.getChildren` 对每个模板先咨询它，Python/官方插件同款钩子）——`SageCreateFromTemplateActionReplacer` 对 "Sage File" 模板返回 `fileTemplates.actions.CreateFromTemplateAction(本地化文本, SageIcons, { template })`（**注意包**：`com.intellij.ide.fileTemplates.actions.CreateFromTemplateAction` 是具体类；`com.intellij.ide.actions.CreateFromTemplateAction` 是抽象泛型类，import 错包编译即炸）。文本来源 `SageUiText.sageFileEntry()`：**直接读 `DynamicBundle.getLocale()`（public static，i18n.locale 服务值）判断 language=="zh" → 「Sage 文件」**——因为这条链路完全不经过插件 properties bundle，bundle 方案无效；`SageBundle` + 两个 properties 文件删除。descriptor 的 displayName 覆写保留同款判断（Settings 树路径仍走 descriptor）。**教训（补入已知坑）**：fileTemplateGroup 的 New 菜单消费 2026.2 已移除，方言/小插件要本地化 New 菜单模板条目名必须走 createFromTemplateActionReplacer + 运行时 locale 判断，不要指望 properties bundle。

**验证**：jar 内 replacer/SageUiText/EP 就位；五测试全绿；verifyPlugin 双版本 Compatible。**用户实测（1.7.1）**：右键 New 条目显示「Sage 文件」✓、建文件正常 ✓ → **已发布**：`git tag v1.7.1` → push → **双发布完成**：商城 1.7.1（CI `publishPlugin` 成功）+ GitHub Release [v1.7.1](https://github.com/starnotes-xj/sage-ide-support/releases/tag/v1.7.1)（zip 附件 131,869 字节）。

**CI 事故记录（2026-08-18）**：v1.7.1 tag 的 release job 中 `publishPlugin` 步骤成功，但 `action-gh-release` 附件步骤撞 GitHub API 503（连续重试后 Too many retries，job 红、Release 未创建）。处理：① **没有 rerun 失败 job**——rerun 会重跑 publishPlugin，商城已有 1.7.1 → 严格模式撞「already contains version 1.7.1」必红（已手动取消一次误发的 rerun）；② 本地 `gh release create v1.7.1 --notes ... build/distributions/sage-ide-support-1.7.1.zip` 手动创建 Release + 附件（一次 503 重试后成功）。**教训**：tag 发布的「商城发布」与「GitHub Release」在同一 job 的两个步骤，任一步骤失败后**不可整体 rerun**（会重复发布撞版本）；正确姿势是按步骤补——gh-release 失败用本地 `gh release create` 补，publishPlugin 失败则需先确认商城侧是否已入库再决定。

### v1.7.2（2026-08-18）——隐式命名空间两处修复：注释 import 门控 + sage.all 变量（ZZ 等）

**用户实测（1.7.1）报告**：① 把 `from sage.all import *` **注释**掉后 GF/ZZ 报未解析（运行正常）；② **删除**该行后 GF 恢复、**ZZ 仍报未解析**。

**根因一（注释行门控误判）**：`SageReferenceResolveProvider` 的显式 import 门控是文本扫描 `file.text.contains("from sage.all import")`——注释掉的行文本仍在文件里 → 被误判为「用户有显式 import」→ 隐式解析整体禁用 → GF/ZZ 全红。**修复**：门控改为 **PSI 语义判断**——`PsiTreeUtil.collectElementsOfType(file, PyFromImportStatement::class.java).any { it.importSource?.asQualifiedName()?.toString() == "sage.all" }`（注释掉的 import 不进解析树，天然排除；`asQualifiedName()` 返回 `QualifiedName?`，必须 `?.toString()` 才能 == String，直接比较编译报错）。

**根因二（sage.all 变量名无索引）**：删除注释行后 GF 走函数索引（`PyFunctionNameIndex`）正常恢复；但 **`ZZ`/`QQ`/`RR`/`CC`/`SR` 是 sage.all 的模块级实例**——生成的 `all.pyi` 里是注解变量形式（`ZZ: _Type_ZZ`，已读用户 WSL stub 确认），`PyFunctionNameIndex`/`PyClassNameIndex` **都不覆盖变量**，`ZZ` 永远查不到声明。**修复**：`SageStubIndex.findDeclaration` 加第三步 `findSageAllAttribute`——`PyModuleNameIndex.findByShortName("all", project, allScope)` 找 `sage.all` 模块（`isSageStubFile` 路径过滤，排除其他包的 all 模块）→ `PyFile.findTopLevelAttribute(name)` 拿带注解的 `PyTargetExpression`（类型链自动生效）→ 复用 positiveCache + isValid 守卫。GF 之前一直不红是因为用户 test.sage 有显式 `from sage.all import *`（星导入默认解析器处理）；删掉后 GF 靠函数索引、ZZ 靠本次新增的变量路径。

**验证**：五测试全绿 + buildPlugin + verifyPlugin 双版本 Compatible。**用户实测（1.7.2）**：注释/删除 import 行后 **ZZ 仍报未解析**（GF 已好）。

### v1.7.3（2026-08-18）——ZZ 仍未解析：定位 sage.all 模块改用 GF 锚点

**idea.log 证据（1.7.2 会话）**：1.7.2 已加载、`resolved implicit name 'GF'` 多条（门控修复生效、函数索引路径正常）、**ZZ 零日志**——`findSageAllAttribute` 静默 null（当时 miss 无日志分支）。1.7.2 的实现用 `PyModuleNameIndex.findByShortName("all", ...)` 定位 all.pyi——**该索引不覆盖 .pyi stub 模块**（实测空结果），allFile 为 null 直接返回。

**修复（1.7.3）**：定位 `sage.all` stub 模块改用**函数索引锚点**——`PyFunctionNameIndex.find("GF", allScope)` 命中 all.pyi 里的 `def GF`（用户日志实证同一索引路径已解析 GF），`safeContainingFile(anchor) as PyFile` 得 all.pyi → `findTopLevelAttribute(name)` 拿 `ZZ: _Type_ZZ` 的 PyTargetExpression。**三分支日志齐备**：`anchor not found`（GF 索引断）/ `attribute miss`（findTopLevelAttribute null，下一轮再分诊）/ `attribute hit`。版本升 1.7.3（1.7.2 已装到用户 IDE，升版保证日志区分）。

**验证**：五测试全绿 + buildPlugin + verifyPlugin 双版本 Compatible。**用户实测（1.7.3）**：ZZ/GF 红错消失 ✓；但出现新一批**黄色警告**（用户列表 + 行号），逐条分析见下。

### v1.7.4（2026-08-18）——N(1) 撞名解析修复：sage.all 声明优先

**用户 1.7.3 实测黄警四类（行号已核）**：
1. L3 `F.<a> = GF(2^8, ...)`「应为元素union 但实际 FiniteField」——**字节码级定论（2026.2 新 Kotlin `PyTypeCheckerInspection` 反编译）**：`visitPyTargetExpression` 对**每个赋值目标**做 `expected=context.getType(target)`（我们 provider 给的 union）vs `got=tryPromotingType(findAssignedValue, expected)`（GF 调用=FiniteField）→ 不匹配报 BAD_ASSIGNMENT。检查器不懂 Sage 糖语义（a 实来自 `F._first_ngens(1)[0]`）。**插件侧抑制钩子已穷尽**：新检查器不咨询 PyInspectionExtension/PyInspectionsSuppressor 仅做注释识别、HighlightErrorFilter 只管 parser 错误、TypeEvalContext 无公开语境 flag、树形态两种都被检查。**用户拍板：注释方案**——`# noinspection bad-assignment`（**IDE Alt+Enter 快修生成的正是此形式**，不是 `PyTypeChecker[bad-assignment]`）；已写入 README EN/zh「已知限制」节。插件侧不自动处理（union 加 FiniteField 的方案会污染 a 的补全/hover，被否）。
2. L18 `RR(1)`「RealField_class 对象不可调用」——**真·数据层缺口，stubgen 已修**：`real_mpfr.pyi` 的 RealField_class 无基类（stubgen-pyx 掉基类）→ 继承不到 `Parent.__call__(self, x=0, *args, **kwds)`。修复 = enhance_parent_chain bridges 加 `RealField_class(Parent)`（commit `0b82efd`，已 push + 用户 WSL 重装生效，用户实测警告消失）。
3. L19 `N(1)`「意外实参」——**真 bug（1.7.4 修复）**：idea.log 实证 `index hit: 'N' -> ...modular/modsym/p1list.pyi`——**N 撞名**！`all.pyi` 里 N 是 `from sage.misc.functional import numerical_approx as N`（import 别名），但 v1.7.3 的 findDeclaration **先查全局函数/类索引**，单字符名 N 命中无关模块 p1list.pyi 的 N → 错误签名 → N(1) 意外实参。（stubgen 只生成 .pyx 的 pyi，misc/functional 是纯 .py 无 pyi 属设计如此，非 stubgen bug。）
4. 多处 print 的「Literal/int 没有定义 __str__/__repr__」——Python 插件自带检查 `PyStringConversionWithoutDunderMethodInspection`，用户 .py 对照**同报** → 平台行为与 Sage 插件无关；建议用户关检查（Inspections 搜 string conversion）。

**修复（1.7.4）**：`SageStubIndex.findDeclaration` 重排——**① `findSageAllDeclaration` 优先**（all.pyi 顶层属性 `ZZ: _Type_ZZ` + **from-import 别名**：遍历 `allFile.fromImports` 的 `importElements` 匹配 `visibleName`，返回 PyImportElement——类型链自动跟随 numerical_approx 签名）；② 全局函数/类索引兜底，候选**优先 all.pyi 文件**（`isSageAllFile`）再任意 sage stub。miss 不打 warn（用户标识符会刷屏）。版本升 1.7.4。

**配套 stubgen 修复（已 push + WSL 重装生效）**：① RealField 桥接（上 2）；② `FiniteField.__iter__ -> Iterator[元素union]`（commit `1e1daf1`）——本想治 L3 但检查器不走迭代路径（字节码实证 got 直接取 value 类型），**保留**（对 `for x in F:` 循环变量类型化是真实增益）；教训：enhance 类补丁必须跑在 docstring enrich **之后**（enrich 重写 import 区，先加的 import 会被覆盖——实测 Iterator import 被丢）。

**验证**：五测试全绿 + buildPlugin + verifyPlugin 双版本 Compatible。**用户实测（1.7.4）**：L19 意外实参消失 ✓、ZZ/RR/CC/GF 无红错 ✓、L18 RR 消失（数据层）✓、L3 用 `# noinspection bad-assignment` 快修压制（用户拍板）✓、④ 平台行为由用户关检查。**已发布**：`git tag v1.7.4` → push → CI 双发布一次成功（无 503）：商城 1.7.4 + GitHub Release [v1.7.4](https://github.com/starnotes-xj/sage-ide-support/releases/tag/v1.7.4)（zip 附件）。v1.7.2/v1.7.3 跳过不发布。

### 待 IDE 实测（用户侧）

1. `e^254` 无错误、hover 类型为元素类（`__pow__` 链）；2. `x ^^ y`/`x ^^= y` 无语法错且按异或/异或赋值解析（**`^^=` 已在独立词法测试验证流正确，但请用户装新 zip 复测一次**——旧 17:10 zip 有惰性 advance bug）；3. bytes 上下文 `x ^ y` 仍标红且 quick fix 到 `^^`，`x ^= y`（bytes 上下文）标红且 quick fix 到 `^^=`；4. 后缀补全 popup 同时含 Sage 集与 Python 内建集；5. `R.<x> = GF(2)[]` 等糖语句不受影响。

## .sage 混写 Python 的 `^`/`^^` 坑（2026-08-17 实测）

`.sage` = 纯 Python + sage.all 注入 + preparser；`requests`/bytes 等 Python 代码原样可跑。唯一坑：**`^` 在 .sage 里是幂（预解析为 `**`）**——Python 的异或必须写 `^^`（预解析回 `^`）。实测案例：`bytes(x ^ y for x, y in zip(a, b))` → `x ** y` → `ValueError: bytes must be in range(0, 256)`；改成 `^^` 后整份 test.sage（GF(2^8) AES 域 + CryptoHack ECB CBC WTF 网络题）一次跑通。已写入插件 README（EN/zh）。
- **v1.5.0 配套 inspection**（`SageXorInspection`）：无歧义的 Python 异或意图场景（bytes 字面量/调用/注解名/喂 bytes(...)）标红色 ERROR + quick fix 替换 `^`→`^^`；sage 幂运算不误报。**v1.6.0 起**：专用 lexer（`^`→EXP、`^^`→XOR、`^=`→EXPEQ、`^^=`→XOREQ）已落地（`SageCaretLexer`），inspection 只做**语义**误用标记（检测「文本为 ^ 的 EXP / 文本为 ^= 的 EXPEQ」），`e^254` 已按 `__pow__` 正确类型化；`^=` 的 quick fix 改为直接写 `^^=`。

## 2026.2.1 失效 PSI 事故（v1.4.0 → v1.4.1，必读）症状：PyCharm 升到 2026.2.1 后，高亮/类型提示阶段抛 `PsiInvalidElementAccessException: Invalid PSI Element: PyFunctionImpl`，栈顶在我们 `SageReferenceResolveProvider.resolveName` 第 66 行——**对 stub 索引返回的元素调用 `containingFile`（触发 getNode → InvalidRef）**。

根因：2026.2 的 **impatient-reader** 高亮在读锁不完整持有的窗口里跑，PSI AST 会被更激进地丢弃——索引元素（`PyFunctionImpl` 等）持有的 AST 节点变成悬空引用，而我们的 LOG 行 `declaration.containingFile?.name` 和 `SageStubIndex` 里的路径过滤/日志都在解引用它。

修复（v1.4.1，`1eb0494`）：
- `SageStubIndex`：正缓存每次命中先 `isValid` 复查（失效即移除）；所有 containingFile 读取走 `safeContainingFile`（isValid 守卫 + try/catch `PsiInvalidElementAccessException`）；日志用安全路径。
- `SageReferenceResolveProvider`：返回前 `declaration.isValid` 检查；日志不再解引用元素（路径细节由 index 的安全日志提供）。
- `SageTypeProvider.generatorType`：`pyClass` 加 `takeIf { it.isValid }`。
- 构建 SDK 升到 **2026.2.1**（CI `pycharm("2026.2.1")`，本地 D:\JetBrains\PyCharm 已同步更新）。
- 教训：**任何索引来的元素，凡要 touching AST（containingFile/getParent/getNode）都必须先 isValid + 容错**；缓存 PsiElement 必须复查有效性。

**后续动作（2026-08-18 四更）**：
- 上游 PR #42670：vincentmacri 已发评论「**LGTM. I am okay with approving after the CI finishes on your fork**」（issuecomment-5318660729）——代码侧全部需求已闭环（`c5bdfdf` 裸注解 → `581bf4d` 去引号 → `4e2fa5a` 本地 noqa）。**fork CI（head `4e2fa5a`）证据已回评论 issuecomment-5319090366**：Lint ✓、Static type check（ty+pyright）✓、docker Build & Test 四 shard 全绿（ecl.pyx 中止本轮未复现）；唯一红项 = doc-html 的 `Download old doc` 步骤（fork 无 develop 基线 artifact，**基础设施缺口、与改动无关**）；Meson 全矩阵/meson-minimal/PDF 文档在跑（承诺跑完回帖最终结果）。主仓 7 组 run 仍 `action_required` 未批准。**用户结论（已传达）**：只要修好该基础设施（或该 lane 在主仓跑，artifact 存在），PR 即全绿，无任何失败归因于改动代码。
- **提醒**：vincentmacri 复审通过后若主仓 CI 批准仍无人响应，可考虑在评论里请 tobiasdiez（已 APPROVED 过）帮忙批准 run。
- sage-lsp issue #3：已回评论 issuecomment-5311787391——认同"注解长期归 sage 仓"（三个上游 PR 正是此路线），但 stubgen 保持**独立仓库/独立发布**（PyPI CLI，不并入 LSP 也不依赖 LSP，仅可选消费关系）。
- JetBrains 插件商城：**已打通**（2026-08-17）：用户已手动完成首次上传（插件 `com.starnotesxj.sageide` 已存在于商城，版本 1.4.1 已在 channel——注意可能仍在审核/未公开，用户可在 https://plugins.jetbrains.com/author/me 查状态）。`PUBLISH_TOKEN` 已存为仓库 secret；CI 的 `v*` tag release job 现在**同时**跑 `gradle publishPlugin`（严格模式：重复版本会让 job 红，即发布前必须升 `build.gradle.kts` 版本号）+ `action-gh-release` 附件。测试 tag v1.4.1-test 已清理；报错 "already contains version 1.4.1" 即 token/secret 注入正常、仅版本重复。下一次发版流程：升版本号（**当前已升 1.6.0，未 tag**）→ commit → `git tag v1.6.0` → push → 全自动双发布。
- **许可证 2026-08-17 已从 MIT 换成 GPL-3.0（两仓库统一，用户拍板）**：注意 PyPI 已发布的 ≤0.8.0 与 GitHub 已发布的 ≤v1.4.1 在法律上仍是 MIT，新版本才适用 GPL。**PEP 639 坑**：pyproject 用 SPDX `license = "GPL-3.0-only"` 时**不得**同时保留 `License ::` classifier（setuptools≥77 直接 InvalidConfigError，CI 的 `pip install -e .` 在跑测试前就炸；本地 PYTHONPATH 跑 unittest 不经过打包所以假绿）——修复 `864a445` 删 classifier。**教训：改打包元数据后必须本地 `python -m build` + `pip install -e .` 验证，不能只跑 unittest。**
- README：两个仓库的 EN/zh-CN 均已加「Quick start / 快速开始」章节；插件 README 修正过时的版本范围行。

## 图标血泪史（v1.3.1 → v1.3.2，必读）症状：编辑器标签 = Sage 图标，项目树 = Python 图标。排查历程：

- v1.3.1 加 `fileIconProvider` + `iconProvider`（order="first"）→ **无效**。
- 真正根因（反编译 **发行版** `plugins/python-ce/lib/modules/intellij.python.psi.impl.jar` 的 `PyFileImpl.class` 才找到，**fork master 源码里没有这个覆写**）：
  ```java
  public Icon getIcon(int flags) { return PythonFileType.INSTANCE.getIcon(); }  // 无条件 Python 图标
  ```
  项目树 `PsiFileNode.computeIcon → value.getIcon()` 是虚方法直调，**完全绕过 IconProvider/FileIconProvider 链**；而 Sage 文件的 PSI 就是 PyFileImpl（SageFileType 继承 PythonFileType）。
- 修复：`SageParserDefinition.createFile`（Python 官方创建文件 PSI 的钩子，原实现 `new PyFileImpl(viewProvider)`）改返回 `SageFile`（`sugar/SageFile.kt`），覆写 `getIcon()` → Sage 图标。
- 教训：**查插件行为差异时，发行版 jar 反编译（javap -p -c）优先于 fork 源码**——发行版可能有源码里没有的覆写。对照参考：renpe 插件树图标正常是因为其文件 PSI 不是 PyFile（独立语言，非 Python 方言）。

## stub 重新生成命令（WSL，勿用 pip 0.6.1 的 --install）

```bash
cd /mnt/c/Users/星记/Documents/CTF练习/sage-pycharm-stubgen
PYTHONPATH=/mnt/c/Users/星记/Documents/CTF练习/sage-pycharm-stubgen/src \
  ~/miniconda3/envs/sage/bin/python -m sage_pycharm_stubgen --install
# 576/576 生成、580 安装；manifest: site-packages/sage/.sage-pycharm-stubgen-in-place.json
# 生成后 PyCharm 需 Invalidate Caches 重索引
```

## fork CI 自验证机制（2026-08-17 建立，绕过 sagemath 审批门槛）

sagemath 上游对外部 fork PR 每次推送都要维护者手动批准 run（`action_required`）。绕过办法：**在用户自己的 fork（starnotes-xj/sage）里建内部 PR**（分支 → fork develop）——pull_request 语义与上游完全一致（含 merge-fixes 步骤、changed-files 分片、editable 不翻倍），且无审批门槛。fork develop 已与上游同步（`c9c8381`）；fork 的 Actions 曾被默认禁用，用户已在仓库 Settings 启用。

- PR #1（`annotate-ring-factory-return-types`，验 #42670 bea9305）：https://github.com/starnotes-xj/sage/pull/1
- PR #2（`annotate-finite-field-element-returns`，验 #42672）：https://github.com/starnotes-xj/sage/pull/2
- PR #3（`annotate-factory-function-returns`，验 #42675）：https://github.com/starnotes-xj/sage/pull/3
- 触发技巧：若错过 pull_request 事件（如启用 Actions 后），`gh pr close` + `gh pr reopen` 重新触发。
- 监控：后台 job pwsh-30（上游 31968571473）、pwsh-33（修复后新 run 全套）。
- 成本警示：三个全套 ≈ 30-40 小时 runner 分钟（免费档月配额 2000 分钟），用户已知情仍要求全套。
- **fork CI 已抓到的真实 bug（上游 CI 永远没跑到的）**：
  1. PR#3（#42675）：3.13 对函数注解**即时求值**——`QuotientRing_generic`/`PowerSeriesRing_generic` 在同类文件里定义于函数**之后** → 3.13 一导入就 NameError（3.14 的 PEP 649 延迟求值掩盖了它，meson 全关只跑 3.14 所以假绿）。修复 `fb1a079`：两个文件加 `from __future__ import annotations`（laurent 的基类在别的模块且顶部已导入，无需改）。
  2. PR#2（#42672）：doctest 里直接用 `FinitePolyExtElement`，但 sage doctest 运行器**不注入模块级 import**（`FiniteField` 能用是因为它在 sage.all 里）→ 全平台 NameError。修复 `2f7a53d`：doctest 内显式 `from sage.rings.finite_rings.element_base import FinitePolyExtElement`。**第二坑（`12b80f9`）**：sage doctest 全局命名空间里 `FiniteField` 是 **FiniteFieldFactory 实例**（sage.all 把工厂暴露为 FiniteField 这个名字），不是类——`FiniteField.from_integer` 抛 AttributeError；须再显式 `from sage.rings.finite_rings.finite_field_base import FiniteField` 拿类。**教训：doctest 里任何类型检查用的名字都要显式 import，别信 sage.all 命名空间。**
  3. PR#3（#42675）：3.13 对函数注解**即时求值**——`QuotientRing_generic`/`PowerSeriesRing_generic` 在同类文件里定义于函数**之后** → 3.13 一导入就 NameError（3.14 的 PEP 649 延迟求值掩盖了它，meson 全关只跑 3.14 所以假绿）。修复 `fb1a079`：两个文件加 `from __future__ import annotations`（laurent 的基类在别的模块且顶部已导入，无需改）。**已验绿**：fork meson 8/9 job success（3.13/3.14 × 三平台 + editable + 3.12 + changed-files），docker 版 ✓，全关 ✓，Lint/静态 ✓。
  3. fork 的 doc-html 构建必失败（"Download old doc" 下载不到 develop 的基线 artifact）——基础设施缺口非代码问题；doc-pdf 能跑且有用（正是它先报出 NameError）。
  4. docker 版 Build & Test 的 `ecl.pyx # Killed due to abort`（cysignals 崩溃，3.14）在 fork 里也复现 → 铁证与我们的改动无关。**已提上游 issue [sagemath/sage#42680](https://github.com/sagemath/sage/issues/42680)**（2026-08-17，附三分支对照证据与崩溃签名），并在 PR #42670 留言引用（issuecomment-5312720648）。另一类无关 flake：meson 3.12 的 `gap.py`（`gap(123)` 空输出，GAP 接口启动时序）——重跑验证中，若复现同样提 issue。
- PR#1（bea9305）fork CI 结果：**Meson 全套绿**（3.12/3.13/3.14 × 三平台）、meson 全关绿、Lint/静态检查绿；docs 失败均为上述基础设施原因。修复得到完整验证，可把此证据贴上游 PR。

## 全量中文翻译批处理（translate-docs，0.8.0 里程碑）

状态：**0.8.0 已发 PyPI**（首批 991 条缓存 + 代码块还原机制）；WSL sage 环境已装 0.8.0 并 `--install` + `--apply-only`（**982 条已应用**，已验证：Clifford stub 中文散文 + `TESTS::` 还原 + 0 处「圣人」）。**批处理暂停在 991/11799（8%）**——百度账户余额耗尽（LLM 与标准 MT 双双 54004），用户选择先发部分版；充值后重跑批处理（断点续传）→ 缓存拷入 `src/sage_pycharm_stubgen/translations.json` → 发 0.8.1。缓存 `C:\Users\星记\.sage-pycharm-stubgen\translations.json`，每 200 条落盘一次、可随时中断续跑。

```bash
# WSL 内运行（本地文件系统 + 百度直连）：
wsl.exe -d Ubuntu bash -lc "unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy; \
  export BAIDU_APPID=...; export BAIDU_API_KEY=...; \
  export PYTHONPATH=/mnt/c/Users/星记/Documents/CTF练习/sage-pycharm-stubgen/src; \
  ~/miniconda3/envs/sage/bin/python -m sage_pycharm_stubgen translate-docs \
  --stubs ~/miniconda3/envs/sage/lib/python3.13/site-packages/sage \
  --cache /mnt/c/Users/星记/.sage-pycharm-stubgen/translations.json \
  --backend baidu --workers 4 2>&1 | tee /mnt/c/Users/星记/.sage-pycharm-stubgen/translate-batch.log"
```

**本批的血泪教训（0.8.0 调试记录）**：

1. **harness 会设置 `HTTP_PROXY/HTTPS_PROXY=127.0.0.1:7897`**（本地 Clash）。Windows 侧 urllib 走代理正常；但该变量泄漏进 WSL 后 NAT 模式连不上 localhost 代理 → 连接被拒。WSL 内跑网络任务必须 `unset` 全部代理变量（百度国内主机直连即可）。
2. **百度 LLM 端点 (aiTextTranslate) 会逐行返回 `trans_result` 条目**（src/dst 对齐输入行）——和标准 MT API 结构一致。
3. **`<<<SPLIT>>>` 标记被 LLM 当文本翻译成 `<<<拆分>>>`** → `joined.split(标记)` 永远 count=0 → 每包都降级成单文本请求，批处理看起来"卡死"（10 分钟零 Progress，实为慢速推进）。修复：改用不透明标记 `QXZ73M` + 按 src 行检测边界分组（`_group_entries_by_marker`）。
4. **标准 MT API**（fanyi-api.baidu.com/api/trans/vip/translate，同 appid+secret 签名）：0.4s/请求但**不严格按行切分**（67 行 → 50 条目）、不保留标记、**会把代码 token 译坏**（`Matrix` → `矩阵`，91% 文档含 doctest）→ 质量不可用，弃用。
5. `model_type='mt'` 在 aiTextTranslate 端点报 58004 不支持；仅 `llm`。
6. **并发可用**：4 并发 LLM 请求无 54003。吞吐实测：5000 字符包 13.5s；~2,000 包 × 14s / 4 workers ≈ 2 小时（比串行 8 小时好）。`--workers` 默认 4。
7. **LLM 规模化后仍会译坏代码**：`sage:` → 「圣人：」/「鼠尾草：」、`TESTS::`→「测试::」、`True`→「真实」、`\wedge`→「\楔形」、`:meth:` 目标加空格。修复：`_restore_code_blocks`（translate.py）——行数对齐时按行状态机还原（doctest 块/RST 头/LaTeX 行）；不对齐时按**锚点+块内位置**还原（首行锚 = 提示符后存活代码 token，块内行序 LLM 保序，短输出如 True 也可靠还原）。一次性脚本 `scripts/restore_cache_blocks.py` 重刷已有缓存（991 条中 502 条被修复）。
8. **已装 stub 里若有旧中文，apply 会跳过**（只匹配英文 key）——修复流程 = `--install` 重生 + `--apply-only` 重应用（实测 950 → 982 条）。
9. urllib timeout 是**每 socket 操作**的：响应慢慢滴流时超时不触发（"卡死"假象的另一半）。

**后续（0.8.1）**：百度充值后按上方命令重跑批处理 → 缓存重刷还原脚本 → 拷入 `src/sage_pycharm_stubgen/translations.json` → bump 0.8.1 发版 → WSL `--install` + `--apply-only` → 用户 Invalidate Caches。

## 独立 Sage 语法树路线——可行性分析（2026-08-17 深夜，用户问询）

用户问题与本答复要点（结论：**不推荐全量独立树；维持 Python 方言树**，理由与证据如下）：

### Q1. SageMath 官方有没有官方 Sage 解析器？

- **权威变换是 preparser**（[src/sage/misc/preparser.py](https://gitlab.com/sagemath/dev/sage/-/blob/4f68ee003ad3d2147a81b8e5ea0c64798ed32a59/src/sage/misc/preparser.py)）：.sage → 纯 Python 文本（`^`→`**`、`^^`→`^`、整数字面量、`R.<x> = ...` 糖……），然后交给 **CPython 自己的 parser**。本插件 v1.6.0 的 `SageCaretLexer` 就是在词法层镜像这套语义——**方向上与官方一致**。
- **sage.misc.parser**（[文档](https://doc.sagemath.org/pdf/en/reference/misc/misc.pdf)）：pynac/GiNaC 支持的**符号表达式**解析器（`sage: x^2 + 1` 这类输入 → `SymbolicExpression`）。它**不是**全语言 CST：只覆盖表达式、产物是运行期 Sage 对象、无源码位置信息——不能直接当 IDE 语法树。
- **结论**：没有可复用的官方 CST。任何「独立 Sage 语法树」都必须自研或从 BNF 生成。

### Q2. 元素类型/PSI 类能否用 JetBrains SDK 减少开发量？

- **能减负，但只覆盖骨架**：Grammar-Kit（BNF → lexer/parser/PSI 生成器）、PsiViewer、ParsingTestCase、`com.intellij.platform.syntax`（新语法引擎）可以自动产出元素类型与 PSI 壳。Python 语法 ≈ 600-700 条 BNF 规则 + Sage 方言扩展，语法层工作量从「手写万行」降到「维护一份 BNF」。
- **减不了的部分**：类型推断、补全、引用解析、inspection、annotator——这些全部是 PSI 之上的行为逻辑，生成器不覆盖，且它们是本插件**全部用户价值**所在。
- 关键取舍：生成的 PSI 与 `PyExpression` 类型**不兼容** → Python 生态（PyTypeProvider、补全、解析、inspection）整体失联。

### Q3. 类型推断能否仿照 PyTypeProvider/TypeEvalContext 写？

- **架构上可仿**（EP 回调 + 上下文缓存 + stub 索引驱动 + union 合并），但 `TypeEvalContext` 是 Python 专属、上万行量级、操作 PyExpression——**无法复用**。
- 自研一个「够用」的 Sage 类型推断器（stub 签名驱动 + 有限数据流 + 工厂返回类型 + 生成元类型）估计 **核心 2-4 周**，随后长期打磨。只能逼近 Python 插件现有质量的下界。

### Q4. 补全/引用解析/隐式命名空间/inspections/后缀模板，花时间能做出吗？

都能做（纯工程），独立树路线的粗略估计：

| 能力 | 估计 | 备注 |
|---|---|---|
| 基础解析（BNF+生成） | 1-2 周 | Grammar-Kit 起步 |
| 补全（成员/形参/类型文本/文档） | 2-3 周 | 需自建补全 contributor + stub 索引对接 |
| 引用解析 + 隐式 sage.all 命名空间 | 1-2 周 | 自建 resolve 链（Python 的 pyReferenceResolveProvider 不可用） |
| inspections/annotator（红字类） | 1-2 周 | 自建 visitor 框架 |
| 后缀模板 | 1-3 天 | 本轮已有现成模板类，只换 provider 门 |
| **合计** | **2-4 个月** | 且最终体验≈现状，还丢失「与 .py 完全一致」承诺 |

对照：**当前 Python 方言树方案已交付上述全部能力**（类型链、补全、隐式解析、红字、图标、运行配置均经用户实测），popup 匹配层问题已在 v1.6.1 定论并修复（见 v1.6.1 节）。

### 结论与推荐路线

1. **不重写独立树**——投入 2-4 个月换回现在已有的东西，且 Jupyter 生态（同构的 Python 方言）同样没有走独立树，证明平台意图就是「方言共享基语言 PSI」。
2. **popup 收尾已完成**（v1.6.1–v1.6.4 连修：popup 根因/设置页分组与新建模板/展开变量/预览/双击编辑/条件精准集），用户侧装 v1.6.4 实测为最终确认。
3. **上游特性请求**（PyElementType 方言感知语言解析）已写入 PR #3614 行——若被采纳，方言插件可重新注册到方言语言，届时本插件的 Python 注册 + SageFile 门可简化。**新增实证素材**：`PyFileImpl.getFileType()` 硬编码 Python（与 getIcon 同族发行版覆写）导致方言文件在 `LanguageUtil.getLanguageForPsi`/copy-file 链上被识别为基语言——这正是「方言感知语言解析」缺陷的又一具体后果，已写入 v1.6.1 节与已知坑。

## 交接提示词（给接手 AI 的完整 prompt，可直接粘贴）

> 继续 G:\Projects\sage-ide-support 插件工作。先读 HANDOFF.md 全文（重点是「v1.6.0」四轮 bugfix、「v1.6.1 popup 根因与修复」、「v1.6.2 设置页分组+新建模板」、「v1.6.3 四修」、「v1.6.4 条件精准集」、「v1.6.5 description.html 三件套修复」、「v1.6.6 设置页描述中文化」、「v1.7.0/v1.7.1 New 菜单 Sage 文件入口与本地化」、「已知坑清单」、「独立 Sage 语法树可行性分析」与「.lexer-test」测试设施）。
> 当前状态：**v1.7.1 已正式发布**（v1.6.6 双发布后，新增右键 New 菜单「Sage 文件」条目——fileTemplates 资源 + fileTemplateGroup EP + createFromTemplateActionReplacer 本地化，中文界面「Sage 文件」/英文 "Sage File"；1.7.0 跳过、v1.7.1 已 tag+push：商城 publishPlugin 成功 + GitHub Release 附件手动补）。功能全景：popup（v1.6.1）、设置页分组/新建模板（v1.6.2）、b2i/i2b 展开/预览无点/双击编辑（v1.6.3）、条件精准集（v1.6.4）、预览 description.html 三件套（v1.6.5）、设置页描述中文化（v1.6.6）、New 菜单入口（v1.7.1）。红线（永久）：不得回退到复用 PyCallWrapPostfixTemplate（预览会变 list）、不得改回 language="Python"/"Sage" 注册（用 SageMathPostfix meta-language）、不得重新加回 isEditable=false、不得把 Py 的 number/iterable/boolean/exception 条件加回编辑器、不得删除 per-key 的 description.html/before/after 三件套任一资源、设置页描述保持中文、New 菜单条目本地化必须走 createFromTemplateActionReplacer + DynamicBundle.getLocale()（fileTemplateGroup 的 New 菜单消费 2026.2 已移除、bundle 无效，见 v1.7.1 节）。后续候选工作：stubgen 0.8.1 翻译批处理续跑、上游 PR #42670/#42672/#42675 推进、PR #3614 方言语言解析特性请求。
