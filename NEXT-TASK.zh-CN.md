# 下一轮任务：独立证明 Sage 10.9 LIVE full 可重复性与覆盖门控

> 上一轮已实现本地 WSL probe checkpoint、显式 timeout 和 fail-closed replay；下一轮先复核 fresh probe/replay 证据，再决定是否推进真实 artifact 的可审计消费。不得把 replay 或 ignored build 产物宣称为 release/bundled 支持。

> 限定切片：复核本机 WSL Ubuntu 中现有 Sage 10.9 / Python 3.13 / sage-pycharm-stubgen 0.8.3 的 LIVE probe checkpoint 与显式 replay 恢复边界；若执行真实 generator，仍只写 ignored `build/sage-api-real/`，完成后停止，不更新 bundled resource，不进入 product/installer/release。
> 必须先写失败回归测试，再实现最小通用审计修正；每次失败先记录 HANDOFF.md。

## 已确认真实环境

- WSL distro：`Ubuntu`（默认 distro 是 `docker-desktop`，所以命令必须显式 `-d Ubuntu`）；
- Conda：`/home/starnotes/miniconda3/bin/conda`；实际环境名为小写 `sage`；
- SageMath：`10.9`；Python：`3.13.15`；
- stubgen package：`sage-pycharm-stubgen 0.8.3`，GPL-3.0-only；
- 真实 stub root：`/home/starnotes/sage_typings_083`，2839 个 `.pyi`；
- generation report：discovered=2837、generated=2837、failed=0，并明确记录 runtime import failures/fallbacks；
- 该外部 artifact 不直接提交到 Git，也不将 70 MiB stubs 复制进产品 resource。

## 目标

复核 importer 的两条边界：默认路径必须执行有界 LIVE probe；只有显式 `--allow-probe-replay` 才能读取 importer 生成的 LIVE envelope。验证 schema、精确 WSL/Conda/env command identity、canonical probeDigest、receipt 的 probeMode/digest 和 generator timeout 执行状态；不把 checkpoint 当作签名或 release attestation。

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

## 本轮已完成切片增量

- importer 已增加 artifact-bound expected contract 校验、canonical expectedDigest、`SCOPED`/`UNSCOPED` coverage 摘要和 returncode=0 后置失败终态。
- `expected-sage-10.9.json` 是人工维护的非空本地 contract；不得复用 Sage 10.6 `expected-high-value.json`，也不得从当前 index 自动反推。
- REPLAY 仍仅为本机恢复/调试证据；probeDigest 不是签名或 release attestation。

## 下一步验证边界

- 顺序执行两次默认无 `--probe-json`、无 `--allow-probe-replay` 的 LIVE full importer，分别输出到 ignored `build/sage-api-real/live-1/` 与 `live-2/`；记录真实 exit code、terminal receipt、probe/tree/report digest、coverage 和墙钟结果。
- 任一次 timeout/failed 都只得出“重复性未证实”，不得使用旧 ignored 产物补齐；两次成功后才比较 deterministic fields。
- 再单独执行一次显式 replay，仅验证恢复边界和同 probeDigest。
- 不更新 bundled resource、plugin、product、installer 或 release。

## 完成标准

- 真实 Sage 10.9 artifact 的来源、版本、生成报告、tree digest 和 index 可审计；
- 真实 index/coverage 在本机重建成功，或 extractor 缺口以真实失败证据被明确定位；
- 不把外部 stubs、fixture 或旧 installer 冒充可发布 bundled artifact；
- 本轮不宣称整产品或发行完成。
