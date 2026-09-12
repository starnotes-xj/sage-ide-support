# Sage IDE Support → SageMath Core 发布迁移

## 已固定的升级身份

正式发布仍使用既有 JetBrains Marketplace 插件 ID：

    com.starnotesxj.sageide

显示名升级为 **SageMath Core**，首个迁移版本为 1.8.0，高于旧公开版本
1.7.9。因此已安装 Sage IDE Support 的用户会收到正常更新，不能也不需要
同时安装旧插件和新的 com.starnotesxj.sagemath.ctf.sage-core 开发 ID。

该 ID 不可在 Marketplace 发布后更改；保留它也是保存既有设置、文件关联和
运行配置迁移路径的唯一安全方案。

## 发布完整类型索引

开发时的小型 sage-api-index.json 只是快速构建 fixture，绝不能作为正式
Marketplace 包的类型智能数据。标签发布工作流会下载、校验并嵌入完整的
Sage 10.9 / Python 3.13 索引。缺少下列任一项时，发布会主动失败，而不会
发布降级插件：

1. PUBLISH_TOKEN GitHub secret：旧 Marketplace 插件的发布 token；
2. SAGE_RELEASE_INDEX_URL GitHub repository variable：已上传的脱敏完整索引 URL；
3. SAGE_RELEASE_INDEX_SHA256 GitHub repository variable：该 URL 内容的 SHA-256。

从本机 v155 索引生成发布资产：

    $raw = 'G:\sage-build\staging-build6\sage-api-curated-type-contracts-v155.json'
    $release = 'G:\sage-build\release-assets\sage-api-index-10.9.json'
    python tools/sage-api-index/sanitize_release_index.py --input $raw --output $release

工具会将文档中的构建机绝对路径（例如
File: /home/.../sage/structure/element.pyx）保留为可公开的
File: sage/structure/element.pyx，并拒绝仍含主机路径的结果。上传该文件到
稳定的发布资产位置后，记录工具输出的 SHA-256 到
SAGE_RELEASE_INDEX_SHA256。可独立复核：

    python tools/sage-api-index/validate_release_index.py --index $release --sha256 '<sanitize_release_index.py 输出的 sha256>'

然后创建与 Gradle 版本完全相同的标签 v1.8.0。标签 CI 会再次下载、验
SHA-256、验 Sage/Python 版本、验完整条目数量、验没有本机路径，并将同一份
完整索引嵌入 ZIP；publishPlugin 也依赖 Gradle 侧的第二次完整索引校验。

## PyPI 与 stubgen

sage-pycharm-stubgen 是独立 PyPI 包，负责生成/安装 .pyi stub；它仍然是
完整静态 Python PSI 类型信息的来源。SageMath Core 的运行时快照、文档渲染、
.sage 语法和索引补充能力不构成 stubgen 的新 PyPI 版本。因此本迁移**不**
发布 PyPI；只有 stubgen 仓库本身的生成结果或 CLI 改动时，才发布新的 PyPI
版本。

## 发布前人工验收

CI 能验证 ZIP 和完整索引，不能替代真实 PyCharm 交互。上传 Marketplace 前
仍须在干净 PyCharm 中安装候选 ZIP，确认 .sage 编辑、R.<x> 尖括号、
P.log 补全、Quick Documentation、普通 Python 文档与 WSL Sage 运行均
正常；同时确认只安装了一个 com.starnotesxj.sageide。
