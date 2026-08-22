# 下一轮任务：推进 Sage 10.9 conflicts 到通用合并决策

> 当前主线仍是 Sage 全量代码智能；本文件只定义下一限定切片，不代表全量智能或发行完成。

## 当前已完成

- 真实 Sage 10.9 / Python 3.13.15 / sage-pycharm-stubgen 0.8.3 的 WSL artifact 已有可审计 LIVE/replay 证据。
- 非空 `expected-sage-10.9.json` contract 命中 6/6，记录为 `coverage.scope=SCOPED`；真实 generator 仍报告 5 个 conflicts，`isComplete=false`。
- conflict 诊断现在保留 Dynamic merge 和 fail-closed gate，并输出确定性的：
  - `sourceDigest` / `sourceDigests`；
  - `declarationCount`；
  - `distinctSignatureCount`；
  - 排序后的 `signatureKeys`。
- 47 个 importer/generator Python 测试、四文件 `py_compile`、`git diff --check` 已通过；本轮没有修改 product、plugin、bundled index、installer 或 release。

## 下一限定切片

1. 使用真实 10.9 的 5 个 conflict 元数据，逐项确认它们是同一 stub 文件内的重复声明、合法 overload 形状还是实际不兼容签名。
2. 先写回归测试，再设计**通用** merge/representation 规则；禁止按具体函数名写 Kotlin 特例，禁止用 `--allow-conflicts` 把问题伪装成成功。
3. 保持 Dynamic/Unknown 安全边界；只有规则和测试能解释所有来源时，才更新 `isComplete`/gate 语义。
4. 选择一小组人工扩展的 expected contract，定义可消费 index 的最小质量门；不得从当前 index 自动反推全量 expected。
5. 以 ignored `build/sage-api-real/` 做真实 artifact recheck；不复制 84159-entry index 到 bundled/resource，不进入 product/installer/release。

## 限定文件

- `tools/sage-api-index/generate.py`
- `tools/sage-api-index/test_generate.py`
- `tools/sage-api-index/README.zh-CN.md`
- `HANDOFF.md`
- `NEXT-TASK.zh-CN.md`

不得修改外部 WSL artifact、`expected-high-value.json`、bundled index、插件源码、product 或 installer。

## 验证要求

- 先运行 conflict regression red test，再运行：
  `python -m unittest tools.sage-api-index.test_import_wsl_artifact tools.sage-api-index.test_generate`
- 运行四文件 `python -m py_compile` 和 `git diff --check`。
- 对既有真实 artifact 做 generator recheck，确认 5 个 conflicts 都包含可解释且 deterministic 的诊断字段；这不是 fresh LIVE 证明。
- 若切片触及 `core:sage-api` 消费契约，再运行 `./gradlew.bat :core:sage-api:test -PrunSageApiTests=true --no-daemon --console=plain`。
- 不在本轮宣称 Sage 全量覆盖、产品完成或正式发行；fresh product/installer/release audit 另行执行。
