# SageMath CTF IDE 接手与继续推进提示词

你是 SageMath CTF IDE 项目的接手开发代理。以下是项目背景和边界；读取完成后必须立即执行本轮任务并实际修改文件，不要只做状态汇总或重复读取文档。

## 1. 项目定位与核心问题

项目路径：`G:\Projects\sage-math-ctf-ide`。这是面向 SageMath 与 CTF 工作流的独立 IntelliJ Community 产品，不是普通 PyCharm 插件，也不是 Jupyter Notebook 包装器。

首要产品目标是系统性解决现有 SageMath 插件和 stubgen 组合方式的类型推断、成员解析和代码提示缺陷。典型问题：

```python
A = matrix(
    F,
    [[F(x)^e for e in unknown] for x in xs]
)
coeff = A.solve_right(vector(F, B))
```

输入 `A.` 可以提示很多矩阵函数，却没有 `solve_right`。这不是一个应该单独给 `solve_right` 加补丁的问题：逐个修复必然遗漏未被调用的 API，且无法发现未覆盖的继承方法、mixin、category、parent 或运行时动态成员。

目标是让以下链路通用成立：

- `matrix(...)` 或其他工厂调用能解析到正确的矩阵实例类型；
- 类型系统能合并 stubgen、Sage Runtime introspection、签名、文档和源码数据；
- 成员解析能处理继承闭包、parent、mixin、category、别名和动态成员；
- `solve_right` 作为通用机制的回归样例自动进入成员候选；
- API coverage、missing/conflict/dynamic 报告能在用户遇到问题之前发现漏项；
- 无法安全确定时返回 `Unknown` 或 `Dynamic`，但不能静默丢弃可提取的 API。

## 2. 本轮任务：立即执行并提交保存

不要停在阅读、分析或计划阶段。当前最高优先级任务是：**把 `core/sage-api` 第一切片接入真实插件类型/补全通路，并针对 `matrix(...).solve_right(...)` 建立通用回归测试。**

执行顺序：

1. 读取 `HANDOFF.md` 最后两个章节、`docs/SAGE-INTELLIGENCE-SPEC.zh-CN.md`，检查当前 `git status`。
2. 阅读当前 `core/sage-api` 的 `SageApiIndexModels.kt`、`SageApiIndexCodec.kt`、`SageApiNormalizer.kt`、`SageStubExtractor.kt`、`SageApiIndexQuery.kt`、`SageApiIndexTest.kt`。
3. 阅读插件侧最小相关文件：`SageTypeProvider.kt`、`SageImplicitCompletionContributor.kt`、`SageStubIndex.kt`，以及对应测试。
4. 结构化源码问题先用 CodeGraph 定位 symbol/callers/callees，再用 read 精读具体文件；不要批量打开无关源码。
5. 先写失败回归测试，证明当前链路无法解析或提示 `solve_right`，再实现最小通用修复。
6. 禁止为 `solve_right` 添加硬编码特例。必须实现或接入通用的工厂返回类型、继承/parent/mixin/category 闭包和 API index 成员查询。
7. 至少新增以下验证：
   - 矩阵实例及其继承/parent/mixin/category 或动态成员来源的 API fixture；
   - API query 测试，验证 `solve_right` 出现在矩阵实例成员集合；
   - Sage/IntelliJ type-provider 或 completion 回归测试，验证 `matrix(...).solve_right` 可解析；
   - coverage/diagnostic 断言，确保 `solve_right` 不被归入 missing。
8. 运行真实测试，读取真实 exit code。至少运行：
   - `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`；
   - 相关 `plugins:sage-core` 测试；先读取 `plugins/sage-core/build.gradle.kts` 确认测试 property。
9. 更新 `HANDOFF.md`，记录实际修改文件、通用设计、测试命令和真实 exit code、未完成风险及下一步。
10. **提交保存本轮成果，然后继续推进后续任务。** 提交必须使用中文 Lore 格式：首行描述意图，正文包含 `约束：`、`拒绝：`、`置信度：`、`影响范围：`、`后续指引：`、`已验证：`、`未验证：`。提交前确认没有修改受保护 checkout，并报告 commit hash。

如果真实 Sage Runtime、stubgen 或插件测试环境尚未具备，不得伪造全量完成；先实现可验证的 index/query/service 通路，并把阻塞写入 `HANDOFF.md`。

## 3. 推荐实现架构

### 数据生产层

- Sage Runtime introspection；
- `sage-pycharm-stubgen`；
- `.pyi`、签名、docstring、文档和源码位置；
- 多版本 extractor/normalizer；
- API coverage、diff、missing/conflict/dynamic report。

### 规范化索引层

每个 API 条目至少包含：完全限定名、Sage/Python 版本、symbol kind、参数/返回类型/重载、base class、parent、mixin、category、protocol、alias/import source、文档/源码位置、dynamicity、confidence 和 runtime/generated source 标记。

### IDE 消费层

- immutable index loader；
- qualified-name resolver；
- subtype/parent/mixin/category closure；
- factory/constructor return-type resolver；
- method-chain type propagation；
- completion/signature/documentation provider；
- Sage PSI 与 preparse source-map；
- Unknown/Dynamic fallback。

不要把生成数据手工散落在 completion contributor 中，也不要继续把每个漏提示函数写成 Kotlin 特例。

## 4. Jupyter 边界

Jupyter 不是本轮目标，也不是 Sage 类型系统的基础设施：

- Sage 原生编辑器是主要编写界面；
- Sage Console 是首选交互执行方式；
- Jupyter 未来只作为可选执行后端和 `.ipynb` 兼容层；
- Jupyter kernel 返回的 completion 不能作为 Sage API/类型推断的权威来源；
- 不因 Jupyter 未实现而阻塞 Sage 原生代码智能或 CTF MVP。

## 5. 文档入口

优先读取：

1. `HANDOFF.md` 最后两个章节；
2. `docs/SAGE-INTELLIGENCE-SPEC.zh-CN.md`；
3. `docs/FEATURE-STATUS.zh-CN.md`；
4. `docs/IDE-PLAN.zh-CN.md`；
5. `docs/MIGRATION-MAP.zh-CN.md`；
6. `docs/STATUS.zh-CN.md`；
7. `product/README.zh-CN.md`。

## 6. 仓库边界

绝对不要修改：

- `G:\Projects\sage-ide-support`；
- `G:\Projects\intellij-community-sage-pr`。

官方基线只能是 `G:\Projects\intellij-community-sage-ide`，固定 SHA 为 `b0001cd6c53979b384def7a1e3febe061e2ef687`。

不要删除或修改官方 checkout 中的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore`。产品和 staging 修改只允许位于 `G:\Projects\sage-math-ctf-ide` 与 `G:\sage-build\staging-build6`。

## 7. 验证与报告纪律

- query/cquery 只能证明图可解析，不能证明编译或 packaging 成功；
- 必须读取真实命令输出和 exit code；
- 旧 installer、旧 ZIP、旧 SHA、旧 audit 不能冒充本轮 fresh build；
- 不要把“代码能编译”描述成“全量 Sage 代码智能已完成”；
- 完成本轮后报告 changed files、功能、测试、exit code、commit hash、保护仓库状态和剩余风险；
- 如果新对话只能读取不写入，检查是否明确要求了本轮具体任务、实际修改文件和提交保存。
