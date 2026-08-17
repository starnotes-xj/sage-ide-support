# Sage 上游类型注解分批推进计划

> 目标：把 stubgen 数据层「猜/补」的返回类型，分批转正为 Sage 源码里的真实注解。
> 配套机制：`sage-pycharm-stubgen conformance`（0.8.1 起）——每个上游注解落地后，
> 对应的 curated 修补从「承重」变为「被校验」，冲突可双向定位（数据层错 / 上游错）。

## 已确立的 PR 模板（每波照抄）

1. 修改点：`# This override is only there for the typing info: ...` 注释 + `-> X` 注解。
2. TESTS doctest：**纯 isinstance 断言**（禁止 `get_type_hints(...) is X` 恒等比较——
   Python 3.14 下注解对象非同一对象，#42670 教训）；断言覆盖**每种具体实现类**。
3. doctest 内所有类型名**显式 import**（sage doctest 不注入模块级 import；且注意
   `sage.all` 里的 `FiniteField` 是工厂实例不是类，#42672 教训）。
4. 纯 Python 文件：先加 `from __future__ import annotations`（3.13 对注解即时求值，
   前向引用会 NameError，#42675 教训）；.pyx 文件用顶部显式 import 即可。
5. 每波先跑本地 WSL sage 10.9 的 isinstance 验证脚本（各实现类清单记入 PR 表格）。
6. fork（starnotes-xj/sage）内部 CI PR 预验证全套，全绿后再转正上游。
7. 每个 PR 只动**一个模块家族**，全部基于 develop、互相独立可合。

## 分批原则

- **同一 PR 只收同类**：同一文件簇 / 同一类层次（如精度环三兄弟）；
  跨域拆开（评审者好批，回归好定位）。
- **按 CTF 杠杆排序**：有限域（已在途）→ 多项式 → 线性代数 → 数域 → 精度环 → 代数。
- **注解选型**：优先共同基类（成员覆盖最全）；基类覆盖不足时用 `|` union
  （#42670 的 Zmod 先例）。
- **一波一个 PR**，避免同主题并行评审返工；上游合并不影响后续波次推进。

## 波次计划

| 波次 | 内容 | 文件 | 注解（待运行时验证） | PR |
|---|---|---|---|---|
| 0 ✅ | GF/Zmod 工厂、FiniteField 元素方法、三个环工厂 | 已提交 | 已定 | #42670 / #42672 / #42675 |
| 1 | **PolynomialRing** | `src/sage/rings/polynomial/polynomial_ring_constructor.py` | `-> PolynomialRing_general \| MPolynomialRing_base`（union；先验 QQ[x]→PolynomialRing_field、ZZ[x]→PolynomialRing_integral_domain、QQ[x,y]→MPolynomialRing_libsingular 的基类） | 独立 PR |
| 2 | **MatrixSpace** | `src/sage/matrix/matrix_space.py` | `-> MatrixSpace_generic`（验 ZZ/QQ/GF 稠密+稀疏） | 独立 PR |
| 3 | **VectorSpace + FreeModule**（同一模块家族，合一个 PR） | `src/sage/modules/free_module.py` | `VectorSpace -> FreeModule_ambient_field`（精确）；`FreeModule -> FreeModule_generic`（ZZ→ambient_pid、QQ→ambient_field 共同基类） | 独立 PR |
| 4 | **NumberField**（调查成本最高，单独一波） | `src/sage/rings/number_field/number_field.py` | 工厂 `NumberFieldFactory.__call__ -> NumberField_generic`（验证 quadratic/absolute/relative/cyclotomic 均为其子类；**命名冲突坑**：模块内 `NumberField` 名已指工厂实例，基类在 `number_field_base.py`，导入别名与注解写法需绕开） | 独立 PR |
| 5 | **精度环三兄弟**（同模式，合一个 PR） | `real_mpfr.pyx` / `real_mpfi.pyx` / `complex_mpfr.pyx` | `RealField -> RealField_class`、`RealIntervalField -> RealIntervalField_class`、`ComplexField -> ComplexField_class` | 独立 PR |
| 6 | **FreeAlgebra** | `src/sage/algebras/free_algebra.py` | `-> FreeAlgebra_generic` | 独立 PR |

**后续低杠杆候选**（视精力，不进承诺表）：groups/combinat 构造器、
manifolds、SymbolicRing(SR)、Integers/QQ 工厂等。

## 与 stubgen conformance 的联动节奏

1. PR 合并 → 进入新版本 sage 发布 → 装有该版本的环境跑 `sage-pycharm-stubgen conformance`。
2. 预期：对应 curated 条目 `unannotated → ok`（源码声明接管，数据层修补自动退居校验位）。
3. 出现 `conflict`：双向排查——数据层写错（修 supplemental_docs 发 patch 版）
   或上游注解写错（追加修正 PR）。
4. curated 条目**保留不删**：工具支持任意已装 sage 版本，老版本仍需兜底；
   conformance 报告按环境自然区分新旧。

## 推进节奏（用户已拍板）

- 等 **#42670 系（第 0 波）合并**后，逐波把后续 PR 从 draft 转正。
- 每波固定流程：fork 分支 → isinstance 验证脚本 → 注释 + doctest →
  fork CI 预验证（全套）→ 转正上游 → 合并进发布版后 conformance 复核。
