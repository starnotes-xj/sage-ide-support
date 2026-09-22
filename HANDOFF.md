# SageMath CTF IDE 交接

> 工作区：`G:\Projects\sage-math-ctf-ide`　更新：2026-09-22
>
> 当前产物：SageMath Core `1.8.20` 本地安装包已构建；真实 PyCharm 人工 smoke、提交和远程发布尚未进行。

## 1. 硬边界

- 只修改本工作区与 `G:\sage-build\staging-build6`；不得修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr` 或官方 checkout `G:\Projects\intellij-community-sage-ide`。
- 官方 checkout 必须保持基线 `b0001cd6c53979b384def7a1e3febe061e2ef687`；不得触碰其中的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore`。
- 不覆盖、重置、提交或 stage 既有未提交改动；尤其禁止 `git add .`。当前工作树本来就有其他功能的未提交改动。
- 具体返回类型必须由函数合同、调用参数、active Sage stub、源码或可重复运行证据证明。公共基类只用于成员查找；动态、条件或多实现不确定结果保持 `UNKNOWN`/`DYNAMIC`，禁止以 `Any` 或白名单猜测替代。
- 使用 `D:\Java\jdk-25`；构建时把 `USERPROFILE`、`HOME`、`APPDATA`、`LOCALAPPDATA`、`TEMP`、`TMP` 指向 `G:\sage-build` 下 ASCII 路径。

## 2. 代码入口

- `core/sage-api`：索引 schema、类型表达式、继承成员查询、签名与文档。
- `plugins/sage-core`：`.sage` 方言、类型 provider/lowering、completion、Quick Documentation、运行入口、内联预测器。
- `tools/sage-api-index`：stub/source/runtime 合同提取、审计、发布索引消毒与验证；`apply_method_aliases.py` 用于给历史完整索引补充源码证明的类内方法别名。
- Sage 仍是 Python dialect：保留 Python PSI/语言能力，不要在没有完整迁移方案和回归的情况下改成完全独立语言。

## 3. 当前已验证能力

- Sage 10.9 WSL 的完整索引已补为 `87,082` 条合同。`apply_method_aliases.py` 从同一 WSL stub 树发现 `838` 个 `alias = method`，安全加入 `743` 个；`94` 个歧义目标与 `1` 个冲突保持不变。
- `EllipticCurve_finite_field.order = cardinality` 已按真实 stub、源码和运行时补入 `Integer` 合同。
- PEP 673 的 `Self`、`typing.Self`、`typing_extensions.Self` 在签名作用域内统一为同一类型变量；Cython `ModuleElement._rmul_ -> Self` 可返回右侧的具体点类。
- 普通 `Q.` 补全仅注册一次，并把 active Sage stub 已由 Python 成员管线提供的索引成员让给该管线；`is_zero`、`order` 不再以“可导航 stub 项 + 索引备用项”重复显示，缺少 stub 时仍走索引兜底。
- `Ctrl+Shift+Space` 通过 Python 与 Sage 两条 SMART 兼容入口提供候选；BASIC 仅有 Python 入口，因此恢复当前 PyCharm 的智能补全不会重新产生普通补全重复项。
- 对裸 `Q.` 保持索引兜底，即使 active stub 已安装；只有已经输入成员前缀时才把同名候选让给 Python stub 管线，因此显式 BASIC/SMART 不能再因不完整 PSI 而出现空列表。
- 未运行时，以下代码的 `Q.` 已由完整索引的真实插件回归证明出现 `is_zero`、`order`：

  ```python
  bad_curve = EllipticCurve(GF(11), [1, 1])
  curve_order = bad_curve.order()
  R = ZZ(2)
  Q = (curve_order // R) * bad_curve.random_point()
  ```

- 编辑热路径已避免每次输入扫描全文件、启动 WSL worker 或在 worker 回调重启 daemon；字符串/注释中不注入 Sage root 候选。此项仍需要人工 PyCharm 延迟 A/B 验收。

## 4. 当前可安装包与索引

- 安装包：`G:\sage-build\release-assets\sage-core-1.8.20-bare-member-fallback.zip`
  - SHA-256：`A324BC2AD31DF4D0FC0CE56CE5E1B5301D3D8303656DDE52C15C9DDD2963E206`
  - `com.starnotesxj.sageide` / `SageMath Core` / `1.8.20`；安装或替换后须完全重启 PyCharm。
  - 主合同 `87,082` 条、64 个文档桶、Windows x64 native inline scorer、Full Line optional descriptor 均在包内。
- 完整索引副本：`G:\sage-build\q-contract-index\sage-api-index-with-method-aliases.json`
  - SHA-256：`86db703666894f0615cb571c910d521d8ca5a5f6b32823cbe0ba8107f3760112`
  - 构建会拆出文档正文，主 JAR 的 `sage-api-index.json` 不含 documentation 字段。
- ZIP 已用 `sanitize_release_index.find_host_path` 复核为无主机路径。普通正则把 `https://` 中的 `s:/` 当路径是误报。

## 5. 已执行验证

- Python：类方法别名生成/后处理及发布索引工具回归 `5` 项通过；`compileall` 与 `git diff --check` 通过。
- Kotlin：PEP 673 与相对父类成员查询回归通过。
- 完整索引插件回归通过（`SageCompletionTest.testConfiguredFullIndexCompletesTheUsersQBeforeRun`，1 test、0 failures）：

  ```powershell
  .\gradlew.bat :plugins:sage-core:test `
    --tests com.starnotesxj.sageide.completion.SageCompletionTest.testConfiguredFullIndexCompletesTheUsersQBeforeRun `
    --rerun-tasks --no-daemon -PrunSageCoreTests=true `
    -Psage.external.fullIndex=G:\sage-build\q-contract-index\sage-api-index-with-method-aliases.json
  ```

- `verifyReleaseFullIndex`、`buildPlugin`、`verifyPluginStructure` 均已通过；目标 PyCharm plugin verifier 为 `Compatible`。弃用/实验 API 报告是既有风险，未在本轮扩大。
- 1.8.20 的静态索引兜底和完整索引回归均通过；二者断言 `is_zero` 与 `order` 在 BASIC completion 中各只出现一次，完整索引回归也断言 SMART completion 能给出二者。

## 6. 已知限制与下一步

- 用户应从磁盘安装 1.8.20 ZIP，并完全重启 PyCharm；对第 3 节的 `Q.` 分别按 `Ctrl+Space` 与 `Ctrl+Shift+Space` 做人工确认。还需测试字符串输入、连续删除/换行的真实延迟。
- 不能把自动化 fixture 或索引回归宣称为真实 IDE UI、运行配置或性能 smoke；若仍卡顿，应采集对应 `idea.log`、CPU/线程快照，并与 JetBrains Full Line Code Completion 做 A/B。
- 未提交、未推送、未发布 Marketplace/PyPI。只有用户明确要求时才提交/推送，并用中文 Lore 提交信息。
- `verify-upstream-staging.ps1 -FinalCheck` 已运行但在首个 SHA 门停止：官方 checkout 实际为 `3b652e714c12009bb69f0a2d2416dad02259fe5d`，不是受控基线。不得为通过该检查而修改、reset 或 checkout 官方仓库。
- 官方 checkout 的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore` 仍是未跟踪既有文件，未触碰。
