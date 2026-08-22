# 下一轮任务：完成真实 Sage artifact 导入前的可执行边界与高价值入口切片



> 这是一个限定切片。完成后停止，不要自动开始全量 runtime、product/installer/release 阶段。

> **执行硬约束：** 读取本任务后必须立即写入测试、源码或文档；不准只读不写、不准反复扫描全仓库、不准以分析代替实现。



## 已确定结论



- 当前工作区没有可确认的真实 Sage runtime/stubgen `.pyi` artifact：已定位到的 `.pyi` 主要是 PyCharm/第三方 typeshed 与既有 fixture，不能冒充真实 Sage 输入。

- 因此下一轮不得把 `G:\sage-build\staging-build6` 下的普通 Python stub 或 `tools/sage-api-index/fixtures` 当作真实 Sage artifact。

- 先把真实 artifact 的输入边界做成可执行、可审计的 contract；真实 artifact 出现后只需替换 manifest 路径和版本元数据，不改 generator 语义。



## 目标



建立“真实 artifact 接入前的最小高价值切片”：



1. 为 source manifest 增加 artifact 身份与 provenance 元数据；

2. 为 generator 增加严格的 artifact manifest 校验与 CLI 入口；

3. 用一个不依赖具体函数名的高价值 contract fixture 验证普通 METHOD、工厂 return type、source digest、版本和 provenance；

4. 明确真实 artifact 缺失时的失败信息，禁止静默回退 fixture。



该切片不宣称真实 Sage runtime/stubgen 已接入，也不修改插件 bundled resource。



## 限定范围



只允许修改以下文件：



- `tools/sage-api-index/generate.py`

- `tools/sage-api-index/test_generate.py`

- `tools/sage-api-index/source-manifest.json`

- `HANDOFF.md`



不得修改官方 checkout、其他项目、product/installer 文件或 bundled artifact。



## 实施步骤



1. 先添加测试：

   - 缺少 `artifactId`、`sageVersion`、`pythonVersion`、`provenance` 或 source root 时拒绝 manifest；

   - manifest 中的 source kind/locator/digest 与生成 index 保持一致；

   - fixture contract 至少覆盖一个普通 METHOD、一个 KNOWN factory return type、source digest 和 generator/version/provenance 元数据；

   - 缺少真实 artifact 路径时返回明确错误，不能回退到 fixture。

2. 运行新增定向 Python 测试，读取真实失败输出；若失败，先把命令和真实 exit code 记录到 `HANDOFF.md`，再只读取错误指向的最小源码范围并实现最小通用修复。

3. 更新 `source-manifest.json` 为显式 schema：顶层 `artifactId`、`sageVersion`、`pythonVersion`、`provenance`、`sources`；保留现有 fixture root 作为测试输入，但标记为 `FIXTURE`，不能写成真实 runtime。

4. 让 generator 支持该 manifest 结构，同时保持旧 CLI/source-root 测试兼容；manifest 路径、artifact identity 或 source root 不可用时以 exit code `2` 失败。

5. 每次写入后立即运行：

   - `python -m unittest tools/sage-api-index/test_generate.py`

   - 必要时 `python -m py_compile tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`

   - `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`

   - `git diff --check`

6. 更新 `HANDOFF.md`，记录修改文件、真实命令与 exit code、真实 artifact 仍缺失的风险，然后停止。



## 完成标准



- 新增 manifest/provenance contract 回归通过；

- generator 对新 manifest schema 严格校验并保留旧 CLI 兼容；

- artifact 缺失时有明确错误和真实 exit code；

- 普通 METHOD、factory return type、source digest、版本/provenance 均有测试证据；

- HANDOFF.md 已更新；

- 不把 fixture 或局部测试描述成真实 Sage runtime 全量覆盖。
