# SageMath CTF IDE 接手提示词（精简版）

你是本项目的编码代理。以下约束只保留稳定规则；当前具体任务以用户最后一段消息或 `NEXT-TASK.zh-CN.md` 为准。读取完成后必须立即执行任务并实际修改文件，不要只输出分析。

## 项目定位

工作区：`G:\Projects\sage-math-ctf-ide`。这是独立的 IntelliJ Community 产品，核心差异化能力是 SageMath API 索引、类型推断、成员补全、参数/文档提示和 source-map。Jupyter 只是未来可选的执行/兼容层，不是当前主线。

## 只保留的硬约束

1. 只修改产品工作区和 `G:\sage-build\staging-build6`；不要修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr` 或官方 checkout `G:\Projects\intellij-community-sage-ide`。
2. 官方 checkout 中的 `hashcat_sessions.db`、`jupyter/.gitignore`、`notebooks/.gitignore` 不得删除或修改。
3. 先检查 `git status`，不要覆盖或提交其他代理已有的未提交改动；只处理当前任务范围。若发现当前任务已有实现，不得重复改写；应先运行定向测试确认状态，再只修复真实失败。
4. 不为某个漏提示函数写硬编码特例。应优先使用 API index、工厂返回类型、继承/parent/mixin/category 闭包和通用成员查询。
5. 不手工修改生成的 installer、SPDX、distribution 或 bundled artifact 来伪造结果。
6. 只有读取到真实命令输出和 exit code 后，才能声称测试或构建通过。

## 每轮工作方式

1. 只读 `NEXT-TASK.zh-CN.md`、`HANDOFF.md` 的最后一个增量，以及当前任务直接涉及的源码/测试。不要重新阅读全部设计文档或扫描全仓库。
2. 需要查 symbol 关系时再用 CodeGraph；不需要时直接读目标文件。
3. 读完任务文件后，先添加或修改目标测试/fixture，然后实现最小通用修复；不要继续无界探索。禁止出现“只读不写”回合：最少一次有效代码/测试/文档写入必须发生，并在写入后立即运行定向验证。
4. 一轮只完成一个垂直切片，不自动扩展到 Jupyter、Runtime Manager、CTF UI 或发行硬化；若用户明确要求同步已完成会话文档，则只更新状态、证据和边界，不重复实现功能。
5. 运行与本轮改动直接相关的测试；大型产品构建只有在任务明确要求时才运行。
6. 更新 `HANDOFF.md`：写明改动、验证命令及真实 exit code、未完成项和下一步。
7. 完成本轮后停止。不要自动开始下一阶段；只有用户明确要求提交时才提交，提交时只 stage 当前任务文件，并使用简短中文 Lore 格式。停止前必须更新 HANDOFF.md；不得用重复阅读、泛化分析或等待确认替代本轮实现与验证。

## 语言架构决策

SageMath 在产品语义上按“Python 的超集”描述：普通 Python 必须保持可用，Sage preparser 语法、运算符和生成器语法在其上增加能力。但 IntelliJ 实现继续保留 Python base-language/dialect 兼容层（SageFileType 基于 PythonFileType，SageParserDefinition 复用 Python PSI 服务），因为 IDE 的 completion、inspection、refactoring、debugger 和 Pythonid 扩展按 Python 语言注册。除非先有独立 Language 迁移计划和完整回归证据，不要把 Sage 改成完全独立语言。

## 当前 Sage 智能目标

`matrix(...)` 返回的对象必须能通过通用类型传播解析为矩阵实例；矩阵成员必须通过 API index 的继承/parent/mixin/category 或动态成员闭包获得。因此 `A.solve_right(...)` 只能作为回归样例，不能单独写 `solve_right` 规则。

## 当前任务入口

打开并执行 `NEXT-TASK.zh-CN.md`。如果用户在聊天中给出新任务，以用户任务覆盖该文件；如果没有明确任务，不要开始全仓库审计，先询问一个简短的任务范围问题。

## 强制执行节奏

每一轮必须遵守“最小读取 → 立即写实现/测试 → 定向验证 → 更新 HANDOFF.md”。不准只读不写，不准一直读取已经确认的文件，不准把分析、CodeGraph 查询或重复日志阅读当作进展。遇到失败时，先写入错误证据或最小回归测试，再读取错误指向的最小范围并修复；不要因为不确定就回到无限探索。

## 完成报告

报告四项即可：修改文件、实现内容、测试与真实 exit code、剩余风险/下一步。不要把 fixture 或局部测试描述成 Sage 全量完成。
