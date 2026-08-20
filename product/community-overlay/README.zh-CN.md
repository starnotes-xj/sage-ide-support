# Community 产品 Overlay

这里保存可重复应用到官方 IntelliJ Community checkout 的产品接入输入，不保存完整上游源码。

## 规则

1. 官方 checkout：`G:\Projects\intellij-community-sage-ide`；
2. 上游远程：`https://github.com/JetBrains/intellij-community.git`；
3. 现有 `G:\Projects\intellij-community-sage-pr` 是 Sage PR/研究副本，不能作为发行基线；
4. 应用 overlay 前必须校验 `product/upstream.lock.json` 中的完整 commit SHA 和 clean working tree；
5. 应用过程使用临时 worktree/staging tree，不在官方 checkout 中直接提交产品修改；
6. 先验证 `bazel run //build:idea_community` 开发实例，再接 `installers.cmd`；
7. Sage core 优先作为第三方产品插件注入，不能绕过 JetBrains vendor 校验强行伪装成内建模块。

## 目录预留

```text
product/community-overlay/
├── README.zh-CN.md
├── product-properties/
├── application-info/
├── product-layout/
├── plugin-inclusion/
└── scripts/
```

首个真正 overlay 需要记录：

- 产品名称、product code、platform prefix；
- Python Core、Jupyter、Debugger、Git、Terminal 的模块来源；
- Sage core/CTF tools 的插件注入方式；
- 适用的 Community commit/build number；
- JDK、Bazel/Bazelisk、操作系统和架构；
- 许可证、NOTICE 和 SBOM 输入。

当前文件只是接入边界，不代表已经生成完整 IDE 安装包。
