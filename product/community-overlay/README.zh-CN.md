# SageMath Community 产品 Overlay

这里保存可重复应用到官方 IntelliJ Community checkout 的产品接入输入，不保存完整上游源码。

## 工程边界

`G:\Projects\sage-math-ctf-ide` 是 SageMath CTF IDE 的产品代码和构建控制仓库；
`G:\Projects\intellij-community-sage-ide` 是固定版本的 IntelliJ/PyCharm Community 上游底座。
最终产品只有一个，但两个目录承担不同工程角色。官方 checkout 必须保持 clean，不在其中提交 SageMath 修改。

## 当前目标

本 overlay 选择 PyCharm Community 的开源模块集合，新增独立 SageMath 产品身份：

```text
PyCharm Community Python Core / HTML / Git / Terminal / Markdown
+ SageMath Core（默认随产品内置的 Community 模块）
= SageMath CTF IDE Community
```

SageMath Core 现在作为 Community JPS/Bazel 正式模块加入 `productLayout.bundledPluginModules`；旧的 `getAdditionalPluginPaths()` 仅保留为显式迁移兼容开关。全量 Sage 10.9 API 不嵌入插件资源，而是由产品构建复制到 `sage-api/10.9/` sidecar。`SageApiIndexService` 校验 sidecar 的 envelope、receipt、SHA-256、FULL 覆盖和 entry count 后才启用。

## 可重复流程

前置条件：

- 官方 checkout 为 `b0001cd6c53979b384def7a1e3febe061e2ef687` 且 `git status --porcelain` 为空；
- JDK 25；
- 已生成 `plugins/sage-core/build/distributions/sage-core-0.1.0-dev.zip`；
- Windows 构建使用 ASCII staging/cache/user-home 路径，规避 Bazel/JDK 25 在中文用户目录中的编码崩溃；
- 发布构建必须显式提供已验证的 Sage 10.9 全量 sidecar 目录（含 sage-api-index.json、envelope 和 receipt），不会把 132 MiB 级索引嵌入插件 source resources。

```powershell
$overlay = 'G:\Projects\sage-math-ctf-ide\product\community-overlay'
$pluginZip = 'G:\Projects\sage-math-ctf-ide\plugins\sage-core\build\distributions\sage-core-0.1.0-dev.zip'
$sageApi = 'G:\Projects\sage-math-ctf-ide\build\sage-api-real\final-live-9'
& "$overlay\scripts\validate-sage-api-sidecar.ps1" -ArtifactDirectory $sageApi
$stage = & "$overlay\scripts\prepare-upstream-staging.ps1" `
  -OfficialCheckout 'G:\Projects\intellij-community-sage-ide' `
  -StagingRoot 'G:\sage-build\staging' `
  -PluginZip $pluginZip `
  -SageApiArtifactDirectory $sageApi `
  -OverlayRoot $overlay `
  -Force

& "$overlay\scripts\verify-upstream-staging.ps1" `
  -OfficialCheckout 'G:\Projects\intellij-community-sage-ide' `
  -StagingTree $stage

& "$overlay\scripts\build-upstream-staged.ps1" `
  -StagingTree $stage `
  -Jdk25Home 'D:\Java\jdk-25' `
  -BuildDev `
  -BuildInstaller `
  -KeepStaging

& "$overlay\scripts\verify-upstream-staging.ps1" `
  -OfficialCheckout 'G:\Projects\intellij-community-sage-ide' `
  -StagingTree $stage `
  -FinalCheck
```

开发实例和安装器分别使用：

```text
bazel run //build:sage_math
bazel run //python/build:sage_i_build_target -- -Dintellij.build.target.os=current
```

它们是 staging overlay 生成的 Sage 专用目标；直接运行上游的 `//build:idea_community` 或原始 `python\installers.cmd` 仍然构建普通 IDEA/PyCharm，不会自动选择 Sage 产品。

## JPS 元数据修复

当前上游 checkout 的 `.idea/modules.xml` 有约 289 个不存在的生成 `.iml` 路径，同时生成的 Bazel 文件仍引用未随 checkout 提供的 Android 源码树。`repair-modules-xml.ps1` 和 `prune-missing-android-labels.ps1` 只在 staging tree 中处理这些明确缺失的生成输入，并写入：

```text
build/sage-overlay/iml-filter-manifest.json
```

官方 checkout 不会被修改。该过滤是当前固定上游快照的兼容性措施，不等同于上游正式修复；未来上游重新生成 JPS/Bazel 模型后应删除此步骤。

## 后续正式内置化

当前外部插件注入是低风险迁移阶段。长期目标是：

1. 把 SageMath Core 的源代码、`plugin.xml`、依赖和测试加入 Community JPS/Bazel 模型；
2. 在 Sage 产品 layout 中声明 SageMath bundled plugin；
3. 让开发实例、插件 classpath、installer、SBOM 和兼容性检查都由同一套 Bazel graph 产生。

## Community / Pro

`SageMathCommunityProperties` 和 `SageMathProProperties` 保持两个产品身份，但当前只实现 Community 目标。Pro 后续应加入独立的 Sage 自有商业插件和许可证服务，不能复制或重新发行 JetBrains Ultimate/PyCharm Professional 闭源模块。

## 许可证与品牌

- IntelliJ/PyCharm Community 源码、第三方依赖、LICENSE、NOTICE 和 SBOM 必须按各自许可证保留；
- 产品使用 SageMath 自有名称、product code、启动器和安装目录，不冒充 JetBrains 官方产品；
- SageMath Runtime 和数学库必须单独完成许可证、源码对应物和 SBOM 审计后再捆绑发布；
- 商业 Pro 功能只能使用自有代码或取得明确再分发/OEM 授权的组件。

当前文件记录的是构建接入，不代表完整发行许可证审查已经完成。
