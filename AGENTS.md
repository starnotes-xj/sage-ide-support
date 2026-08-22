# SageMath CTF IDE 本地执行规则

## 按需读取

- 开始工作先读取 `HANDOFF.md` 的最新两节；不要从零扫描仓库。
- 先读取下一步计划直接需要的 BUILD、IML、overlay/build/verify 脚本和错误日志；只有错误指向具体源码 symbol 时才读取对应源码文件。
- 不批量打开全部 Kotlin/Java 源文件，不递归扫描无关目录，不重复读取已确认且与当前阻塞无关的文件。

## 结构化定位

- 结构化源码问题优先使用 CodeGraph：先 `codegraph_context`，再按需使用 `codegraph_search`、`codegraph_callers`、`codegraph_callees`、`codegraph_node` 或 `codegraph_explore`。
- CodeGraph 定位到具体文件后，才使用 `read` 获取精确上下文。literal 文本搜索才使用定向 grep。

## 验证纪律

- query/cquery 只能证明图可解析，不能证明编译或 packaging 成功。
- 必须读取真实命令输出，再报告 core build、formal plugin、product、installer 或 smoke 结果。
- 旧 installer、旧插件 ZIP、旧 SHA、旧 common distribution 和旧 audit 不得冒充本轮 fresh product build。
- 新错误先写入 `HANDOFF.md` 最新增量，再按错误最小范围读取和修复。

## 仓库边界

- 不修改 `G:\Projects\sage-ide-support`。
- 不修改 `G:\Projects\intellij-community-sage-pr`，也不将其作为产品基线。
- 官方基线只能是 `G:\Projects\intellij-community-sage-ide`，SHA 为 `b0001cd6c53979b384def7a1e3febe061e2ef687`。
- 不删除或修改官方 checkout 中现有的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore`；每次 FinalCheck 都报告其实际状态。
- 产品/staging 修改仅允许在 `G:\Projects\sage-math-ctf-ide` 和 `G:\sage-build\staging-build6`。

## 构建环境

- 使用 `D:\Java\jdk-25`。
- `USERPROFILE`、`HOME`、`APPDATA`、`LOCALAPPDATA`、`TEMP`、`TMP` 和 output root 使用 `G:\sage-build` 下 ASCII 路径。
- 完成前执行与当前阶段对应的 build、测试、x64 smoke、release audit 和 `verify-upstream-staging.ps1 -FinalCheck`；没有证据就明确报告未完成。
- 不要在 `run_code` 内启动长时间 `run_in_background` shell/pwsh 任务：这类嵌套 job 绑定临时 `run_code` owner，外层 run_code 结束时会被 DSH owner disposal 取消，并显示 `killed before exit`。长构建使用前台 `shell`，分阶段运行并读取真实 exit code；若确实需要持久后台任务，必须在外层直接启动并跟踪 job id。

## 提交

- 没有必要不要提交。若提交，第一行说明意图，使用中文 Lore 字段：`约束：`、`拒绝：`、`置信度：`、`影响范围：`、`后续指引：`、`已验证：`、`未验证：`。
