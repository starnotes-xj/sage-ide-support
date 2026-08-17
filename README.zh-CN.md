# Sage IDE Support

[English](README.md) | [简体中文](README.zh-CN.md)

> 以后写密码学 sage 脚本，不用再边写边查源码了。

![Sage IDE 演示](docs/demo.gif)

在 PyCharm 中获得一等公民级别的 `.sage` 文件支持——与 `.py` 文件完全一致的
代码提示体验，同时保持 `.sage` 是**独立的文件类型**（不是"换了扩展名的
Python"）：

- **独立 "Sage" 文件类型** —— 作为 Python *方言*语言实现，全部 Python 能力
  （补全、检查、类型推断、重构）通过语言基类机制对 `.sage` 生效
- **透明的 Sage 语法糖解析** —— `R.<x> = GF(2)[]`、`F.<a> = GF(2^8, ...)`
  被解析为真正的多目标赋值：无错误波浪线，`F` 有类型，`x`/`a` 可解析
- **隐式 `sage.all` 命名空间** —— `sage` 命令运行时注入的命名空间对静态分析
  可见：`GF`、`Integer` 等无需 import 即可解析（与 PyCharm 解析 IPython
  内置名同一扩展点）
- **运行配置** —— 右键用 `sage` 命令执行 `.sage` 文件（本机 / WSL / Docker），
  带运行槽图标
- **Live Templates**（多项式环、有限域等常用构造）+ 官方 SageMath 二十面体图标

## 与 sage-pycharm-stubgen 的关系

本插件是**机制层**；**类型信息与文档**全部住在配套项目
**[sage-pycharm-stubgen](https://github.com/starnotes-xj/sage-pycharm-stubgen)**
生成的存根数据层里。插件**刻意不携带任何 Sage 领域知识**：`GF` 被解析到已安装
`site-packages/sage/*.pyi` 存根中的声明，所有方法类型与中文快速文档都来自
存根。

## 快速开始

1. **生成存根**（在 Sage 环境内，WSL / 本机 / Docker 均可）：
   ```bash
   python -m pip install sage-pycharm-stubgen
   sage-pycharm-stubgen --install
   ```
2. **安装插件**：设置 → 插件 → ⚙ → 从磁盘安装插件 → 选
   [Releases](https://github.com/starnotes-xj/sage-ide-support/releases) 里的 zip → 重启。
3. **打开任意 `.sage` 文件**（例如含 `R.<x> = GF(2)[]` 与
   `e = F.from_integer(0x57)`）：`GF` 无红线、`F.`/`e.` 补全带彩色图标 +
   类型文本 + 形参列表，Ctrl+Q 显示中文文档，右键运行走 `sage` 命令。
4. （重）生成存根后执行一次 **文件 → 使缓存失效/重新启动**。
5. 可选全量中文文档：`sage-pycharm-stubgen translate-docs --apply-only`。

## 依赖条件

| 依赖 | 版本 / 条件 |
|---|---|
| PyCharm | **2026.1 – 2026.3**（build 261–263；`since-build="261"` / `until-build="263.*"`） |
| Python 插件 | PyCharm 自带（`com.intellij.modules.python`） |
| SageMath | 较新版本，WSL / 本机 / Docker 均可，并配置为项目 SDK |
| sage-pycharm-stubgen | **≥ 0.8.0**：在 Sage 环境内执行 `sage-pycharm-stubgen --install` 生成并安装存根；中文 curated 文档与有限域元素类返回注解自 0.7.0 起提供，0.8.0 新增**可选机器翻译层**——`sage-pycharm-stubgen translate-docs --apply-only` 用随包共享缓存把其余英文 Quick-Doc 补成中文 |

安装或重新生成存根后，请执行一次 **文件 → 使缓存失效/重新启动**，让 PyCharm
重新索引新存根。

## 安装

1. 获取插件 zip：
   - [Releases](https://github.com/starnotes-xj/sage-ide-support/releases)
     （打了 tag 的发布会自动附带 CI 构建的 zip），或
   - 任意一次 push 的 CI 产物：**Actions → 最新的 `build` 运行 →
     Artifacts → `sage-ide-support`**。
2. PyCharm → **设置 → 插件 → ⚙ → 从磁盘安装插件** → 选择 zip → 重启。
3. 打开 `.sage` 文件（如含 `R.<x> = GF(2)[]` 与 `e = F.from_integer(0x57)`）：
   `GF` 无未解析引用波浪线，`F.` / `e.` 补全带彩色方法图标 + 类型文本 +
   形参列表，Ctrl+Q 显示存根中的中文文档。

若曾在 **设置 → 编辑器 → 文件类型** 里手动把 `.sage` 关联给其他类型，请删除
该关联，让本插件的 Sage 文件类型生效。

## 构建

```powershell
$env:JAVA_HOME = "D:\Java\jdk-21"
gradle buildPlugin --no-daemon   # 产出 build/distributions/*.zip
```

需要 JDK 21、Kotlin 2.3.0 与 IntelliJ Platform Gradle 插件（以本机 PyCharm
安装作为插件 SDK）。

## 相关项目

- [sage-pycharm-stubgen](https://github.com/starnotes-xj/sage-pycharm-stubgen) ——
  本插件消费的存根数据层（配套，必需）。
- [JetBrains/intellij-community PR #3614](https://github.com/JetBrains/intellij-community/pull/3614) ——
  通用的 `typeInformationGenerator` 扩展点，让 PyCharm 本体能调用并刷新存根引擎。
- [sagemath/sage PR #42670](https://github.com/sagemath/sage/pull/42670) /
  [#42672](https://github.com/sagemath/sage/pull/42672) —— Sage 上游注解，
  为同一条类型信息链供数。
