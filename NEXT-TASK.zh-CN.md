# 下一轮任务：接入真实 Sage stubgen artifact 的最小导入链路

> 这是一个限定切片。完成后停止，不要自动开始 product/installer/release 阶段。
> **执行硬约束：** 读取任务后必须立即写入测试或源码；不准只读不写、不准连续反复读取已确认文件、不准以分析或等待确认代替实现。

## 目标

把真实 Sage runtime/stubgen 生成的 `.pyi` artifact 接入现有 generator 输入边界，先完成可审计的单个真实 artifact 导入切片；不宣称全量 Sage API 覆盖。

## 范围

1. 先检查 git status，只读取 generator CLI、source manifest、现有 `.pyi` extractor 测试和真实 artifact 的实际路径/格式；不要全仓库扫描。
2. 先添加一个真实 artifact smoke/contract 回归，锁定输入文件、版本元数据、source digest、普通 METHOD 和 return type。
3. 若真实 artifact 不存在或路径不可用，立即在 HANDOFF.md 记录具体阻塞和命令 exit code；不要用 fixture 冒充真实 artifact，也不要无限寻找。
4. 如测试失败，只实现最小通用导入修复；不得为 solve_right、matrix 或其他单个函数增加特例。
5. 每次写入后立即运行定向验证，完成本轮后停止。

## 验证

- 项目已有 generator smoke/contract 测试命令；
- ./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain；
- git diff --check。

## 完成标准

- 有真实 artifact smoke，或有明确记录的真实路径阻塞；
- 记录每条命令真实 exit code；
- 更新 HANDOFF.md 后停止；
- 不自动开始全量 runtime 接入、product fresh build 或 installer 工作。
