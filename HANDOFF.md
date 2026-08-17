# Sage IDE Support — 交接提示词（给接手 AI 的完整上下文）

## 任务背景

用户目标：在 PyCharm 中编写 `.sage` 文件时，获得与 `.py` 文件**完全一致**的代码提示体验——语法糖（`R.<x> = GF(2)[]`）不报错、`F.`/`e.` 补全带彩色图标（红 m 方法标志）+ 类型文本 + 形参列表 + Ctrl+Q 中文文档，右键运行用 `sage` 命令（非 Python）。**保持独立的 Sage 文件类型（不是把 .sage 识别成 Python）。**

## 当前状态（v1.4.0 / stubgen 0.7.1，2026-08-17 凌晨）

四项目整合完成，类型知识全部住在数据层；另有三样「stubgen → Sage PR」贡献已推进（2026-08-17 凌晨）：

| 项目 | 路径 | 状态 |
|---|---|---|
| ① stubgen | `C:\Users\星记\Documents\CTF练习\sage-pycharm-stubgen` | **0.7.1 已发 PyPI**：`FiniteField._first_ngens -> tuple[元素union,...]`（a/x 定型为元素）、三元素类 `__pow__`/`multiplicative_order` 注解、enrich 支持引用本文件声明名 + 内联体保留；降级安装保护 + curated 落盘（0.7.0 起）；工厂声明类型优先收敛；CI 3.11-3.13 + 可信发布全自动 |
| ② 插件 | 本仓库 | **v1.4.0**：idea-version 放宽 **261–263.***（2026.1–2026.3 全年）；**GitHub Actions CI**（push 构建 zip 上传 artifact，v* tag 自动挂 Release）；SDK 双模式（CI 下载 `pycharm("2026.1.4")` + `bundledPlugin("PythonCore")`，本地用 D:\JetBrains\PyCharm）；CI 已绿 |
| ③ JetBrains PR #3614 | `G:\Projects\intellij-community-sage-pr` | 2 commits（EP + preparse action），PR 描述已重写，OPEN |
| ④ Sage 上游 PR #42670 | `G:\Projects\sage-fork` | 回归 doctest（a10665b）+ bea9305 移除 get_type_hints 恒等断言（3.14 下注解对象非同一对象）。**CI 状态（2026-08-17）**：旧 head a10665b 三个 run 全部只败在 get_type_hints 行（3.14）；bea9305 已推且为 PR head，但新 run 处于 `action_required` 待维护者批准。另注：非 meson "Build & Test" 里 `libs/ecl.pyx # Killed due to abort`（系统 libecl 24.5 的 sigint 测试在 3.14 崩溃）与本 PR 无关。已发评论 issuecomment-5310875176 请维护者批准。本地验证：4 项 isinstance 断言在 WSL sage 10.9 全 True（`GF(2**8,'a',impl)`×3、`GF(29)`、`Zmod(29)`、`Integers(0)`） |
| ⑤ Sage 上游 PR #42672（draft） | `G:\Projects\sage-fork` 分支 `annotate-finite-field-element-returns` | FiniteField 四元素方法 `-> FinitePolyExtElement`；https://github.com/sagemath/sage/pull/42672 |
| ⑥ Sage 上游 PR #42675（draft，第四波） | `G:\Projects\sage-fork` 分支 `annotate-factory-function-returns` | PowerSeriesRing → `PowerSeriesRing_generic`、LaurentPolynomialRing → `LaurentPolynomialRing_generic`、QuotientRing → `QuotientRing_generic`（运行时验证共同基类 + TESTS doctest）；https://github.com/sagemath/sage/pull/42675 |
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
| SageParserDefinition | `parser/SageParserDefinition.kt` | 继承 PythonParserDefinition，覆盖 createParser + getFileNodeType（SageFileElementType） |
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

## 验证成功标准

在正式 PyCharm（WSL sage SDK 已配）打开 test.sage：
1. ✅ `GF` 无红色未解析标注（v1.2.0 起，用户确认）
2. ✅ `e.` 补全项带红色 m 图标 + 类型文本 + 形参列表（v1.2.2 起；**v1.3.0 数据层路径已复验**：用户确认 + 日志证实 v1.3.0 会话零 getReturnType 行，类型来自 stub union 注解）
3. `F.characteristic` Ctrl+Q 显示中文文档（F 已定型 FiniteField，待最终确认）
4. ✅ 右键 Run 通过 sage 命令执行成功（用户确认）
5. ✅ 语法糖行无波浪线（用户确认）
6. ✅ 项目树 `.sage` 文件显示 Sage 图标（v1.3.2 起，用户确认）

## 图标血泪史（v1.3.1 → v1.3.2，必读）

症状：编辑器标签 = Sage 图标，项目树 = Python 图标。排查历程：

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
