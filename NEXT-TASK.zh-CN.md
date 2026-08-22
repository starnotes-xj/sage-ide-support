# 下一轮任务：接入 WSL Conda SageMath 10.9 的真实 stubgen artifact

> 限定切片：把本机 WSL Ubuntu 中现有 Sage 10.9 / Python 3.13 / sage-pycharm-stubgen 0.8.3 产物变成可重建、可审计的本地 artifact 并生成真实 API index；完成后停止，不更新 bundled resource，不进入 product/installer/release。
> 必须先写失败回归测试，再实现最小通用采集/导入工具；每次失败先记录 HANDOFF.md。

## 已确认真实环境

- WSL distro：`Ubuntu`（默认 distro 是 `docker-desktop`，所以命令必须显式 `-d Ubuntu`）；
- Conda：`/home/starnotes/miniconda3/bin/conda`；实际环境名为小写 `sage`；
- SageMath：`10.9`；Python：`3.13.15`；
- stubgen package：`sage-pycharm-stubgen 0.8.3`，GPL-3.0-only；
- 真实 stub root：`/home/starnotes/sage_typings_083`，2839 个 `.pyi`；
- generation report：discovered=2837、generated=2837、failed=0，并明确记录 runtime import failures/fallbacks；
- 该外部 artifact 不直接提交到 Git，也不将 70 MiB stubs 复制进产品 resource。

## 目标

新增一个 stdlib-only 的本地 artifact importer：从显式 WSL distro、Conda 路径/环境和 stub root 读取真实版本、stubgen package metadata 与 generation report；在仓库 `build/` 下生成 source manifest、artifact receipt、真实 Sage API index、coverage 与 diagnostics。任何版本/报告/文件数量不一致都 fail-closed。

## 高价值范围

1. importer 不依赖交互式 `conda activate`，使用显式 `wsl -d Ubuntu -- <conda> run -n sage ...`，避免默认 distro 和 shell 初始化差异。
2. provenance.kind 必须是 `STUBGEN`；receipt/manifest 记录 Sage、Python、stubgen 版本、distro、Conda env、source root、generation report 摘要、tree digest 与生成命令边界。
3. 只接受 report 中 `failed == 0` 且 `generated == discovered` 的 artifact；report 的 Sage 版本必须匹配 runtime probe。
4. 调用现有 `generate.py` 生成真实 index，保留 source tree/index consistency contract；输出写入 ignored `build/sage-api-real/`。
5. 生成真实 coverage 报告，并如实记录 extractor 不兼容或 coverage 缺口；本切片不生成 diff，因为 importer 没有 previous index 输入；不为特定函数硬编码规则。

## 限定文件

- `tools/sage-api-index/import_wsl_artifact.py`
- `tools/sage-api-index/test_import_wsl_artifact.py`
- `tools/sage-api-index/README.zh-CN.md`
- `tools/sage-api-index/support-matrix.json`
- `HANDOFF.md`
- `NEXT-TASK.zh-CN.md`
- 运行时输出：`build/sage-api-real/**`（不提交）

不得修改外部 WSL stubgen 项目/产物、fixture、bundled index、插件源码、product 或 installer。

## 验证

- 先添加 importer 单元测试：report/version fail-closed、STUBGEN provenance、receipt/manifest deterministic、命令参数边界。
- `python -m unittest tools/sage-api-index/test_import_wsl_artifact.py tools/sage-api-index/test_generate.py`。
- `python -m py_compile tools/sage-api-index/import_wsl_artifact.py tools/sage-api-index/test_import_wsl_artifact.py tools/sage-api-index/generate.py tools/sage-api-index/test_generate.py`。
- 对真实 WSL artifact 执行 importer，读取真实命令 exit code 和输出摘要。
- `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`。
- `git diff --check`，更新 HANDOFF 后停止。

## 完成标准

- 真实 Sage 10.9 artifact 的来源、版本、生成报告、tree digest 和 index 可审计；
- 真实 index/coverage 在本机重建成功，或 extractor 缺口以真实失败证据被明确定位；
- 不把外部 stubs、fixture 或旧 installer 冒充可发布 bundled artifact；
- 本轮不宣称整产品或发行完成。
