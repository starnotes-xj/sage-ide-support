# 下一轮任务：建立生成 index 与 manifest source metadata 的完整一致性校验

> 限定切片：完成后停止，不进入真实 runtime 批量抓取、product、installer 或 release 阶段。
> 必须先写失败回归测试，再做最小通用实现；每次写入后立即定向验证；失败先记录 HANDOFF.md。

## 目标

把“manifest 声明的 source metadata”和“实际生成 index 的 entries/sourceDigests/sources”做成双向 contract，避免只校验输入目录 digest，却漏掉 source locator、kind、文件集合或生成器输出之间的不一致。

## 高价值范围

1. 为 object manifest 增加 source metadata contract：每个 source 的 kind、locator、treeDigest 与生成 index.sources 对应且唯一；source 顺序和文件列表确定性保持不变。
2. generator 在生成并 validate index 前后执行通用一致性校验：每个 manifest source 必须有 entries 来源，entry source locator 必须属于 manifest source locator，sourceDigests 必须覆盖实际 entry source；不允许静默丢源或多源漂移。
3. 校验 index.sources 的 `fileCount`、`files`、`treeDigest` 与实际扫描 root 一致；声明 source 没有对应 `.pyi/.py` 时以 exit code `2` 失败。
4. 继续保持旧数组 manifest、`--source-root` 和无 digest manifest 兼容；不增加 solve_right、matrix 或任何单函数特例。
5. 只用 checked-in fixture 做 contract regression，明确 provenance 仍为 `FIXTURE`，不宣称真实 Sage runtime/stubgen 全量覆盖。

## 限定文件

- `tools/sage-api-index/generate.py`
- `tools/sage-api-index/test_generate.py`
- `HANDOFF.md`
- `NEXT-TASK.zh-CN.md`

不得修改官方 checkout、其他项目、source fixture 内容、bundled resource、插件源码或 product/installer 产物。

## 实施与验证

- 先增加：source metadata 对齐通过、未知 locator 拒绝、缺少 entry source 拒绝、fileCount/files/treeDigest 漂移拒绝、多 source 稳定排序测试。
- 运行 `python -m unittest tools/sage-api-index/test_generate.py`；失败先将命令和真实 exit code 记录到 `HANDOFF.md`。
- 实现最小通用 manifest/index consistency validator。
- 运行 `python -m py_compile tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`。
- 运行 `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`。
- 运行 `git diff --check`，更新 `HANDOFF.md`，完成后停止。

## 完成标准

- manifest source metadata 与生成 index 双向一致；
- source locator/kind/tree digest/file list 漂移明确失败并返回 exit code `2`；
- 旧 CLI/source-root/无 digest 兼容路径保持通过；
- Python contract tests、py_compile、core test、diff check 均有真实证据；
- 不把 fixture 结果描述成真实 Sage runtime/stubgen 全量接入。
