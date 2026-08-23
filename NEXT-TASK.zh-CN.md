# 下一轮任务：从 parallel/ctf-mvp 受控整合 CTF Math Lab

> Runtime Manager 核心已通过 `a2c7fdc` 进入当前 `main`；CTF MVP/Math Lab 仍只以 `parallel/ctf-mvp` 为后续合并来源。本轮只处理 CTF 的受控主线整合、产品级验收和文档边界，不把独立 worktree 的绿测直接宣称为完整发行完成。`integration/ctf-mvp` 是独立的旧基础 MVP/安全加固参考，不是 parallel 的 Git 祖先，也不再单独合并。

## 已完成会话

### Runtime Manager

- 分支：
  - `parallel/runtime-manager`
  - tip：`c532e09`
- 已交付：signed Catalog、verified mirror/cache、artifact 校验与安全安装、选择/切换/移除/回滚生命周期、Settings/Project SDK binding、Native/WSL/Docker/SSH target-aware command/probe、显式路径映射。
- 独立 worktree 验证：`:core:runtime:test -PrunRuntimeTests=true --no-daemon --console=plain`，38 tests、skipped=0、failures=0、errors=0，exit `0`。

### CTF MVP

- 最新分支：
  - `parallel/ctf-mvp`，worktree：`G:\Projects\worktrees\ctf-mvp`
  - tip：`62847f0`（与 `integration/ctf-mvp` tip `742aa3d` 共享基础 MVP 内容但不是其 Git 后继）
- 已交付：独立 `plugins/ctf-tools`、Challenge Project/Profile、notes/payload/solve scripts、flag scanner、bounded script execution、run history/evidence、Crypto/Encoding helpers、loopback CyberChef-server Bake/Magic/Batch Bake adapter，以及图形化 `CTF Math Lab`。
- Math Lab：群/环/域、椭圆曲线、RSA、DH、DES 的专用输入表单、预检、运算追踪、可视化、教学步骤、Sage/Python 脚本预览和中英文案；Tool Window 已注册为 `CTF Math Lab`。
- 最新独立 worktree 验证：`:core:model:test :plugins:ctf-tools:test :plugins:ctf-tools:buildPlugin -PrunModelTests=true -PrunCtfToolsTests=true --no-daemon --console=plain`，`BUILD SUCCESSFUL`；CTF XML 为 15 suites/51 tests、skipped=0、failures=0、errors=0，exit `0`；plugin ZIP required libraries audit 通过。
- 已保持的安全边界：脚本 realpath/SHA-256 二次校验、受控 workspace 临时副本、flag regex 限制、CyberChef response byte limit、loopback-only 服务地址；Math Lab 对不完整/无效输入保留显式诊断，因数分解采用有界重试，不把本地预检冒充真实 Sage 或正式产品验证；解释器 PATH 未固定仍作为显式风险。

## 本轮 Runtime bundled-Python 增量

- `RuntimeManifest.pythonExecutable` 现在是 Sage artifact manifest 的权威、显式相对路径；必须安全、列在 `files` 中，并由 verifier 检查 regular file、非 symlink、POSIX executable bit（Windows 除外）。
- Native/WSL/Docker/SSH 的 Sage/Python 路径统一走 `RuntimeExecutableResolver`；WSL/Docker 要求显式 mapping，SSH 要求显式 remote POSIX runtime root，禁止通过 launcher 名称推断 Python。
- `SageRuntimeSdkType` 保持独立的 Sage Runtime SDK 身份，不伪造或持久化 `PythonSdkType` 投影；PyCharm Python API 的严格类型消费者不能被 additional data 绕过。
- Native/WSL/Docker Sage run/debug 已切到已验证 manifest launcher；debug wrapper 没有 Python 路径时直接失败，不再把 Sage launcher 当 Python 执行。
- 验证：core runtime + Sage plugin tests、plugin build/configuration verification、PY-261/PY-262 plugin verifier 均通过；本轮新增 WSL Conda 命令层/探测/调试回归和真实 Ubuntu Sage 10.9 smoke；fresh product/installer/release FinalCheck 未执行。

## 下一步顺序

1. 在 `main` 上审阅 `parallel/ctf-mvp` worktree 的文件边界和 Lore commit history；只整合 CTF 任务文件，不覆盖现有 Runtime、importer、Sage API 或其他未提交修改。
2. 逐项应用 CTF MVP 的受控变更，解决 `settings.gradle.kts`、`plugin.xml`、`core:model` 共享文件冲突；禁止使用 `git add .`。
3. 在主线重新运行：
   - `:core:runtime:test -PrunRuntimeTests=true`；
   - `:core:model:test -PrunModelTests=true`；
   - `:plugins:ctf-tools:test -PrunCtfToolsTests=true`；
   - `:plugins:ctf-tools:buildPlugin`；
   - `:plugins:sage-core:test -PrunSageCoreTests=true`，确认既有 Sage API/SDK adapter 回归不受影响。
4. 主线绿测后，补产品级验证：默认插件集合、真实 IntelliJ Settings/Project SDK UI、真实 WSL/Docker/SSH 端点、并发/崩溃 fault-injection、live Node/CyberChef-server 和完整产品 smoke。
5. 继续保持 Sage API sidecar/quality gate 的 no-`--allow-conflicts` 边界；不要把 ignored full Sage index 复制进 bundled/resource/product/installer/release。

## 当前仍未完成

- CTF MVP/Math Lab 尚未合入当前 `main`；Runtime Manager 核心已由 `a2c7fdc` 进入主线，但真实 Settings/Project SDK click flow、真实端点和 fault-injection 仍未完成；
- Runtime 真实 Settings/Project SDK click flow、WSL 命令层之外的 product UI/真实运行配置端到端、Docker/SSH 端点、并发/崩溃 fault-injection 和发布方 Catalog 公钥轮换；WSL 已有真实 Ubuntu Conda smoke，但尚未有 product UI click-flow 证据。
- CTF live Node/CyberChef-server、完整产品 smoke、默认插件/发行接入；
- Sage 全量智能补全、全量 type engine、完整参数/文档/source-map、独立 envelope read/tamper validator；
- Linux/macOS、arm64 主机 smoke、正式签名、法律审批和自动更新。

## 文档与仓库边界

- 本轮已同步：`HANDOFF.md`、`docs/STATUS.zh-CN.md`、`docs/FEATURE-STATUS.zh-CN.md`、`docs/MIGRATION-MAP.zh-CN.md`、`docs/IDE-PLAN.zh-CN.md`、`README.md`、`product/README.zh-CN.md`。
- 不修改 `G:\Projects\sage-ide-support`、`G:\Projects\intellij-community-sage-pr` 或官方 upstream checkout。
- 保留现有未提交改动；不执行 `git add .`，不提交，除非用户明确要求。
