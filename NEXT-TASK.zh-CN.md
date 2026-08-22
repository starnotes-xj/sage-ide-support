# 下一轮任务：建立 Sage artifact 的 source tree digest 与 provenance fail-closed 契约

> 这是一个限定切片。完成后停止，不进入真实 runtime 批量抓取、product、installer 或 release 阶段。
> 继续遵守：先写回归测试，再实现最小通用修复；每次写入后立即定向验证；失败先记录 HANDOFF.md。

## 目标

在真实 Sage/stubgen artifact 尚未可用的前提下，把 manifest 的“输入是否仍是同一份可审计 artifact”做成可执行的 fail-closed contract。真实 artifact 出现后，只需填入 manifest 的声明 digest，不需要改变 extractor 语义。

## 高价值范围

1. 为每个 manifest source 增加可选的 deterministic tree digest 声明；声明存在时，generator 必须校验 root 下 `.pyi/.py` 文件集合及内容，漂移或缺失均以 exit code `2` 失败。
2. 生成 index 时输出 source tree digest、文件计数和相对文件清单摘要，保持确定性排序；旧数组 manifest 和未声明 digest 的兼容路径继续工作。
3. provenance 继续 fail-closed：限制 provenance.kind 为已知值，禁止空 generator/source；不能静默把 RUNTIME/STUBGEN 输入降级成 FIXTURE。
4. 先用 checked-in fixture 做 contract 回归，明确它仍是 `FIXTURE`，不宣称真实 Sage runtime 覆盖。

## 限定文件

- `tools/sage-api-index/generate.py`
- `tools/sage-api-index/test_generate.py`
- `tools/sage-api-index/source-manifest.json`
- `HANDOFF.md`
- `NEXT-TASK.zh-CN.md`

不得修改官方 checkout、其他项目、bundled resource、插件源码或 product/installer 产物。

## 实施与验证

- 先增加：tree digest 稳定性、正确声明通过、错误声明拒绝、文件集合漂移拒绝、非法 provenance 拒绝测试。
- 运行 `python -m unittest tools/sage-api-index/test_generate.py`；失败先将真实命令和 exit code 写入 `HANDOFF.md`。
- 实现最小通用 digest/provenance 校验，不增加 solve_right、matrix 或其他单函数规则。
- 运行 `python -m py_compile tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`。
- 运行 `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`。
- 运行 `git diff --check`，更新 `HANDOFF.md`，完成后停止。

## 完成标准

- manifest source tree digest 可复现并能拒绝内容/文件集合漂移；
- provenance 非法或不完整时明确 exit code `2`；
- 旧 CLI/source-root 与无 digest manifest 兼容；
- contract 测试、Python 编译、core 测试和 diff check 均有真实证据；
- 不把 fixture 结果描述成真实 Sage runtime/stubgen 全量接入。
