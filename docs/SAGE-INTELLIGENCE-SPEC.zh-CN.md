# SageMath 代码智能规格

> 目标：系统性解决 SageMath API 的类型推断、代码补全、参数提示、文档提示和跳转问题，而不是继续逐个为缺失函数打补丁。

## 1. 产品动机

现有 SageMath 插件已经覆盖了一部分 Sage 语法和类型能力，但 Sage API 数量庞大、对象类型动态且模块层次复杂。仅依靠逐个函数添加特殊规则，会不断遗漏新的函数、方法、构造器和返回类型。

本产品的首要差异化能力不是 Notebook，而是一个面向 SageMath 语义的静态分析和 IDE 智能提示系统：

- 用户输入 SageMath API 时，系统应尽可能从声明、stub、签名、文档和类型关系推断结果；
- 用户组合数学对象时，系统应根据接收者类型推断方法和返回类型；
- 类型信息应覆盖 SageMath 的模块、类、函数、方法、构造器、常量、别名和重载；
- 新增或更新 SageMath API 后，索引系统应能批量吸收数据，而不是修改一个 Kotlin 特例；
- 无法安全推断时必须明确标记未知或动态，而不是给出看似正确的错误提示。

## 2. 核心目标与非目标

### 核心目标

1. **全 API 数据驱动**：补全和类型信息主要来自可版本化的 Sage API 数据、stub、签名和文档索引。
2. **类型传播**：支持变量赋值、函数返回值、方法调用、构造器、属性、容器、泛型参数和常见运算的类型传播。
3. **Sage 语义优先**：理解 `sage.all`、generator sugar、预解析语法、隐式导入、Sage 特有运算符和数学对象层次。
4. **项目级索引**：同时分析 Sage 库、项目源码、用户 stub、当前配置的 Runtime 和外部类型数据。
5. **可解释诊断**：提示结果应能说明来源，例如 Sage stub、项目声明、运行时 probe、文档索引或动态推断。
6. **版本化兼容**：类型数据必须与 SageMath 版本和 Python 版本绑定，避免不同 Runtime 的 API 混用。
7. **增量更新**：Runtime 或 stub 数据变化后，只重建受影响索引，不要求手工维护数千条规则。

### 明确非目标

- 不把 Jupyter Notebook 作为主要 Sage 编程界面；
- 不依赖 Jupyter kernel 的运行时 completion 结果来替代静态分析；
- 不承诺对所有任意 Python/Cython 动态元编程做到绝对精确；
- 不通过复制整个 SageMath 源码到 IDE 仓库来维护领域知识；
- 不继续以“发现一个函数就增加一个特例”作为主要扩展方式。

## 3. 智能能力范围

### 3.1 符号发现与补全

- `sage.all` 隐式命名空间和显式导入的统一补全；
- 工厂调用的返回类型解析，例如 `matrix(...)`、`vector(...)`、`PolynomialRing(...)` 等；
- 方法成员解析必须计算继承、parent、mixin、category 和运行时注入成员的闭包，不能只读取一个 stub 类体；
- Sage 模块、子模块、类、函数、方法、属性和常量；
- 点号成员补全、导入补全、关键字参数补全和构造器补全；
- 根据接收者静态类型过滤方法；
- 根据上下文过滤 Sage/Python 不适用的同名 API；
- 项目自定义符号、局部变量、模块别名和用户 stub；
- generator sugar 产生的环、域、变量、元素和相关方法；
- 结果排序、类型图标、来源标签和不确定性标记。

### 3.2 类型推断

至少覆盖以下类型关系：

- Sage 标准对象：整数、有理数、实数、复数、有限域、环、域、理想、矩阵、向量、多项式、群、置换、椭圆曲线等；
- 构造器返回类型和工厂函数返回类型；
- 方法返回类型、属性类型和常量类型；
- `map`、`list`、`tuple`、字典、集合和 Sage 容器的元素类型；
- `+`、`-`、`*`、`/`、`^`、`^^`、比较、索引和切片等运算；
- 类型参数、泛型容器和有限域/多项式环中的 parent 关系；
- `None`、联合类型、未知类型和动态类型；
- 函数参数、默认值、重载和调用结果；
- generator sugar 与 preparse 后 Python 表达式的对应关系。

### 3.3 参数与文档提示

- 函数和方法签名；
- 参数名称、类型、默认值和可选性；
- Sage docstring、模块文档和示例；
- 当前 Runtime 版本对应的 API 文档；
- 对多个候选重载显示可解释的匹配结果；
- 文档提示中显示 API 来源和版本。

### 3.4 跳转、检查和重构

- 跳转到 Sage stub、声明、文档或项目实现；
- Find Usages 和 Rename 的 Sage source-map 支持；
- 未解析 Sage 名称、错误 parent、错误参数和不兼容运算检查；
- 从生成的 preparse Python 位置映射回原始 `.sage` 位置；
- 诊断、补全、跳转、重命名、断点和 traceback 使用同一套映射。

## 4. 数据与分析架构

```text
Sage Runtime / sage-pycharm-stubgen / 官方文档 / 用户 stub
                         │
              API extractor + normalizer
                         │
       versioned Sage API/type/document index
                         │
      project index + preparse-aware semantic model
                         │
 PSI ──► resolver ──► type engine ──► completion/signature/docs/diagnostics
                         │
                   original .sage source map
```

### 数据模型要求

每个 API 索引条目至少包含：

- Sage/Python 完全限定名；
- Runtime/Sage/Python 版本范围；
- 符号种类：模块、类、函数、方法、属性、常量；
- 参数签名、返回类型、类型参数和重载；
- parent/base class/协议关系；
- 文档、示例、声明来源和源码位置；
- 动态程度和推断置信度；
- 与 preparse/source-map 的关联信息。

### 数据生成原则

- 优先从 Sage Runtime 和 `sage-pycharm-stubgen` 生成或读取数据；
- 生成器应能在 SageMath 版本升级后批量重建；
- 数据生成和 IDE 消费分离；
- 生成结果可进行 schema 校验、差异比较和回滚；
- 不将生成数据手工散落在 completion contributor 中；
- 对动态 API 保留 `Unknown`/`Dynamic`，禁止伪造精确类型。

## 5. 当前实现切片与完整性定义

当前已落地的最小可验证切片不是全量实现：`core:sage-api` 已具备版本化模型、normalizer、稳定 JSON writer、严格 reader/loader、不可变 query 和 Unknown/Dynamic 安全边界；`plugins:sage-core` 已消费 generated bundled index，支持唯一 KNOWN factory return type、父类/别名成员闭包和矩阵 `solve_right`/`determinant` 等数据驱动成员补全。Python generator 已支持 canonical alias、source manifest、严格 contract validation、coverage/diff 与默认 missing/conflict gate；当前 fixture artifact 仍不能作为 Sage 全量覆盖声明。

下一阶段必须优先把真实 Sage Runtime / `sage-pycharm-stubgen` / 签名 / 文档输入接入生成流水线，再用覆盖率报告和 product-level golden tests 证明完整性。

“所有 SageMath 函数都能提示”不能只用几个示例函数证明。建议采用分层指标：

### 数据完整性门

- API index 覆盖目标 Sage Runtime 暴露的模块、类、函数、方法和属性；
- extractor 报告未解析、无签名、冲突和动态对象数量；
- 每次 Sage 版本更新生成 coverage report 和 diff；
- 目标版本的 API 符号缺失率低于项目设定阈值，并对例外有清单。

### 语义正确性门

- 构造器、方法链和常用运算的推断类型与 Sage Runtime 实际结果一致；
- 参数提示与实际签名/文档一致；
- 不同 Sage/Python 版本不会错误复用不兼容类型；
- 未知和动态结果不会被错误标记为确定类型。

### 用户体验门

- 补全延迟、索引时间和内存有可测量预算；
- 补全结果排序稳定、来源可见、错误结果可反馈；
- `.sage` 原始位置的错误、跳转和文档提示可用；
- 至少覆盖密码学、数论、代数、有限域、矩阵、多项式和常见 Python 互操作场景。

### 回归测试门

- API index schema/generator tests（当前已加入 Python generator tests、Kotlin unified generator test）；
- 版本化 fixture 和 golden completion tests；
- type inference/property-based tests；
- preparse/source-map golden tests；
- Sage Runtime integration tests；
- 每个支持的 Sage 版本生成独立报告。

## 6. Jupyter 的定位

Jupyter 不是本项目解决 SageMath 代码智能问题的基础设施，也不是首版核心验收门槛。它只保留为可选兼容层：

- Sage Console 和 IDE 原生编辑器是首选编程工作流；
- Jupyter kernel 未来可以作为执行后端；
- `.ipynb` 支持未来可以作为导入/导出和兼容入口；
- Notebook 富输出、LaTeX、SVG/PNG 只在核心语言智能完成后实现；
- Jupyter completion 不作为类型推断的权威来源；
- 不因为 Jupyter 尚未实现而阻塞 Sage 代码智能、CTF MVP 或 Community 首版。

## 7. 参考文档

- [产品开发计划](IDE-PLAN.zh-CN.md)
- [功能实现状态与版本边界](FEATURE-STATUS.zh-CN.md)
- [迁移地图](MIGRATION-MAP.zh-CN.md)
- [当前状态](STATUS.zh-CN.md)
