# 下一轮任务：推进 Sage 10.9 conflicts 后的可消费质量门

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
- core:sage-api 的 overload 安全边界已加入回归：已知且证明不相交的参数类型可保留 overload；同形状不同返回、Unknown 参数/返回、Literal/宽类型重叠、歧义 arity 保持 Dynamic/CONFLICT。core test 已从首次红测 25 tests/5 failures 修复至真实 exit `0`。

## 下一限定切片

1. 将本轮通用 overload compatibility 规则接入真实 generator/消费链，逐项解释 5 个 10.9 conflicts；在 Unknown、同形状不同返回、Literal/宽类型重叠和歧义 arity 未有额外证据前，不降低其 Dynamic/CONFLICT gate。
2. 扩大一小组人工 expected contract，并把参数/返回/文档质量门拆成可审计的 scoped checks；不得从当前 index 自动反推全量 expected。
3. 设计可消费的 versioned API/type/document index slice，补充参数提示、文档提示和 source-map 所需的 provenance，不把 conflict resolver 当作全量智能完成。
4. 以 ignored `build/sage-api-real/` 做真实 artifact recheck；不复制 84159-entry index 到 bundled/resource，不进入 product/installer/release。

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
