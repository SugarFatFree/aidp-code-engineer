<!-- 二次切分 · phase-0 片3/9：覆盖 0.1 chrome检测启动 · 0.1.1 驱动安装检查 / 0.1.1.4 远程.mcp.json约定-->
# /sprint-aiauto-test · 执行分片 分片 [3/9]（0.1 chrome检测启动 · 0.1.1 驱动安装检查 / 0.1.1.4 远程.mcp.json约定）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-0-3.md`。理据见同目录 `rationale.md`。

### 0.1 chrome-devtools-mcp 检测 + 智能启动

> ★ **Phase 0.0.5 已读到 `TESTPLAN_CHROME_ADDR`（非空）**时：仅**跳过 0.1.3~0.1.5 的交互式 IP 收集**（不弹 AskUserQuestion 问 IP），直接以 `TESTPLAN_CHROME_ADDR` 中的 IP 连接远端 Chrome；0.1.1（MCP 检查）和 0.1.2（环境探测）仍正常执行。
> ⛔ **不跳过的部分**：IP 预填**绝不**意味着跳过 0.1.1.4 的**项目根 `.mcp.json` 生成/合并 + `chrome-{git_user}` 注册 + 重启引导**——这些动作对"IP 预填"路径**仍必须执行**（生成时机铁律见 0.1.1.4，最早在 Phase 0.0.5 即建）。换言之：跳的是"问 IP"，不是"建文件 + 连接"。

#### 0.1.1 chrome 驱动安装检查（本地 CLI / 远程 MCP 二选一可用即可）

> 编号说明：本节子步骤编号为 0.1.1 / 0.1.1.4 / 0.1.1.5（无 0.1.1.1–0.1.1.3，编号被全文多处引用，保持稳定不重排）。

> ★ 完整工具名称：**`chrome-devtools-mcp`**（**Chrome DevTools 官方提供、经 npm 全局安装** `npm i chrome-devtools-mcp@latest -g`，用于本地或远程操作 Chrome 浏览器；本命令全文统一用 `chrome-devtools-mcp` 指代该工具）。
>
> 🔀 **双驱动可用性**：本命令需要**当前场景对应的驱动可用**即可，不强制两者都装——
> - **本地（将走 `DRIVER=cli`）**：需 `chrome-devtools-cli`（chrome-devtools-mcp 包自带；**装法 / 可用性探测命令详见依赖 SKILL** `references/chrome-devtools-mcp-setup.md`）。本地 CLI 可用即可零交互直接跑，**无需** MCP plugin。
> - **远程（将走 `DRIVER=mcp-remote`）**：需 chrome-devtools-mcp 可用 + 按 0.1.1.4 在**项目根 `.mcp.json`** 配好远程地址（启动**自动加载，无需 `--mcp-config`**；下方安装引导）。
> - 判定顺序（**服从 Phase 0.0.7 护栏定死的 `MODE`；驱动可用性委派 `chrome-mcp-doctor.py check-cli`，见 0.0.7 顶部铁律**）：**`MODE=local`** → 用本地 cli（真实命令 `chrome-devtools`）；**`chrome-devtools` 真不可用**（check-cli 判 `local-chrome-no-cli`）→ 先按 check-cli 诊断修 PATH/装包，短期修不了则降级 `mcp-plugin-fallback`（同插件 MCP 协议、须显式声明 driver），**不再"绝不回退"式无路可走**；`blocked-no-fallback`（本机无 chrome）才终止播报。**`MODE=remote`**（自己的 `chrome-$GIT_USER` 已注册 + 显式远程）→ 按下方方式 1~3 探测**自己的** MCP 服务、`DRIVER=mcp-remote`；不可用 → 打印安装引导 + 退出。
> - **★ git 用户隔离铁律（绝对不可用他人的 chrome MCP 服务）**：项目根 `.mcp.json` 的 `chrome-<user>` 远程条目**按 git 用户名隔离**——先取 `GIT_USER=$(git config user.name)`，**唯一可用的 MCP chrome server = `chrome-$GIT_USER`（server 名必须精确全等）**。`.mcp.json` 里任何 `chrome-<他人名>`（`<user> != $GIT_USER`）都是**别人的远程浏览器**，**绝对禁止使用**（会连到同事机器、串测/串数据/污染）；探测 MCP tool 时**只认 `mcp__chrome-$GIT_USER__*`**，`mcp__chrome-<他人>__*` 一律视为不可用、直接无视。
> - **★ 默认本地 + 无"自己的" MCP 即回落本地 CLI（不因他人条目改走远程）**：`/sprint-autopilot` / 本命令**未显式声明远程**（测试方案「二·连接模式」未写"远程" **且** 无用户显式远程指令）→ **默认 `DRIVER=cli` 操作本机浏览器**。即便本机 CLI 探测不可用，只要**没有属于自己（`chrome-$GIT_USER`）的远程条目**，**仍走 `chrome-devtools-cli` 本地**（并提示装本机 Chrome / CLI），**绝不**因 `.mcp.json` 里存在他人的 `chrome-<other>` 就翻成 `DRIVER=mcp-remote` 连别人机器。仅当**自己的 `chrome-$GIT_USER` 条目存在且**（测试方案显式"远程" 或 用户显式远程指令）时才 `DRIVER=mcp-remote`。

**MCP server 检查方式**（`DRIVER=mcp-remote` 远程 / 本地 CLI 不可用回退时用；命令端按顺序尝试，任一命中即视为可用）：

> ⛔ **只认自己的 server（git 用户隔离铁律，见上）+ 仅 `MODE=remote` 才进本节**：下方所有对 `chrome-<user>` 远程条目的探测，`<user>` **必须精确等于 `GIT_USER=$(git config user.name)`**；探到的 `mcp__chrome-<他人>__*` **不算可用**（那是别人的机器）。**★ `mcp__chrome-devtools__*`（无用户后缀通用名）绝不得当作"本地 CLI 的替代"**——它驱动的是共享/远程 Chrome，`MODE=local` 下一律不探测、不使用（本地唯一驱动是 `chrome-devtools-cli`，见 0.0.7）；仅当**确为 `MODE=remote` 且该通用名条目就是自己项目 `.mcp.json` 注册的自有远程服务**时才可用。

```bash
GIT_USER=$(git config user.name)
# 方式 1：用 ToolSearch 探测 MCP tool（最准确）
#   本项目远程 mcp 配置：query="select:mcp__chrome-${GIT_USER}__navigate"（★ server 名精确等于 chrome-$GIT_USER；chrome-<他人> 命中也判不可用、不用）
#   通用名场景（★ 仅 MODE=remote 且该条目为自己 .mcp.json 注册的自有远程服务时）：query="select:mcp__chrome-devtools__navigate"；MODE=local 严禁用它顶替本地 CLI
#   返回非空 → ✅ 可用

# 方式 2：检查 npm 全局包是否已装（兜底）
npm ls -g chrome-devtools-mcp 2>/dev/null | grep -q chrome-devtools-mcp && echo "npm 全局包已装"

# 方式 3：直接尝试调用一个无副作用的 MCP tool（如 mcp__chrome-${GIT_USER}__list_pages / mcp__chrome-devtools__list_pages；★ 只试自己的 chrome-$GIT_USER，绝不试 chrome-<他人>）
```

**判定结果**：
- ✅ 已安装 → 清零环境熔断计数并显式解冻本门写下的冻结（幂等，仅当本版 `freeze_reason=chrome-unavailable`），再进 0.1.2 环境探测：
  ```bash
  eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
  python3 .aidp/scripts/baseline_edit.py --version "$TARGET_VERSION" del env_fail_streak 2>/dev/null || true
  python3 .aidp/scripts/autopilot_unfreeze.py --clear "$TARGET_VERSION" --reason chrome-unavailable || true
  ```
- ❌ 未安装 → 打印安装引导 + **记账/告警/达阈冻结**后退出（**不静默继续、更不静默空转**）：

  > ⛔ **"打印 + 退出" 不够（无人值守下等于静默空转）**：`/loop 5m` 会**每 tick 撞同一处**、每次打印一屏安装引导后退出——**无 #4、无 streak、无冻结**，一条通知都没有，运维以为在跑、其实一轮用例都没执行过。故本门与其它环境门共用 `env_fail_streak` 计数：
  > ```bash
  > eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
  > # 记账 → 判阈 → 冻结四件套 → 发 #4，一次调用做完（**环境类**：装好后本门检测通过即 --clear 解冻，另有 --env-reprobe 自动复探；
> #   已按同一 reason 冻结时脚本 no-op，不刷新冻结时刻、不重发 #4）
  > python3 .aidp/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
  >   --phase 0.1.1-chrome --reason chrome-unavailable --streak-key env_fail_streak \
  >   --threshold "${ENV_FAIL_FREEZE_THRESHOLD:-3}" \
  >   --why "chrome-devtools-mcp 未安装，连续多个 tick 无法开测" \
  >   --section "<下面这段安装引导原文>"
  > [ $? = 3 ] && echo "⛔ 已达阈冻结本版，后续 tick 静默跳过" || echo "⚠️ 未达阈：已记账，退出本 tick"
  > exit 0
  > ```
  > **★ 必写 `aiauto_blocked_reason`**：只写 `needs_human` 而不写它，开发链路会读到"心跳还在刷"误判测试链路健康、无限暂缓准发布（双链路互等）。安装引导原文：

  ```
  ⚠️ 未检测到 chrome-devtools-mcp 工具
     该工具用于让 Claude Code 本地或远程操作 Chrome 浏览器，是 /sprint-aiauto-test 的核心依赖。

  📦 安装步骤：

     1) 全局安装（含本地 CLI chrome-devtools-cli + 远程 MCP 服务）：
        npm i chrome-devtools-mcp@latest -g

     2) 仅远程路径需注册 MCP 服务（本地 CLI 路径免注册、免重启，可跳过 2~3）：
        claude mcp add "chrome-$(git config user.name)" --scope project chrome-devtools-mcp
        ⚠️ 服务名强制 chrome-<git 用户名>、强制 --scope project（写项目根 .mcp.json）；禁用通用名 chrome-devtools 与 --scope user/全局

     3) ★ 远程注册后重启 Claude Code（必须，否则新 MCP tool 不会被加载）
        - 先退出当前 Claude Code（Ctrl+C 两次 / 输入 /exit）
        - 再在同一项目目录重新打开，建议用：
            claude --dangerously-skip-permissions -c
          （-c 续上本次会话不丢上下文；--dangerously-skip-permissions 免权限打断，适合 /loop 守护无人值守）

     4) 重新运行 /sprint-aiauto-test

  📖 项目主页：https://github.com/ChromeDevTools/chrome-devtools-mcp
  ```

#### 0.1.1.4 ★ 远程 MCP 配置文件约定（项目根 `.mcp.json` 自动加载 + `chrome-{git_user}` 条目）

> 仅 `DRIVER=mcp-remote`（远程）适用；本地 `DRIVER=cli` 不读 MCP 配置文件，豁免本节。

远程连接 chrome-devtools-mcp 时，**不依赖、更绝不修改任何用户级 / 全局** MCP 配置（含 `claude mcp add --scope user`/全局注册），改用**项目根的 `.mcp.json`**（Claude Code 启动时**自动加载**的标准项目级 MCP 配置，随仓库入库提交、团队共享）。这是对 SKILL `references/chrome-devtools-mcp-setup.md` §1/§6「服务名 `chrome-<git_user>`、`--scope project` 写入项目根 `.mcp.json`、禁用 `--scope user`/全局」通用机制的**项目级落地约定**（约定 21，命令端项目级延伸）：

> ⛔ **禁改清单（用户级/全局 — 一律不碰，远程 IP 绝不写进这些文件）**：凡 `~/.claude.json`、`~/.claude/settings*.json`、历史遗留 `~/.claude/plugins/` 下与 chrome 相关的**任何用户级 / 全局** MCP 配置全部在禁改范围内，最容易被误改的入口（缺一即留漏洞）：
> 1. `~/.claude.json`（`claude mcp add --scope user`/全局注册的落地处 — **新模型下最主要的误改入口**）
> 2. `~/.claude/settings*.json`（用户级 settings 内的 MCP 段）
> 3. 历史遗留 `~/.claude/plugins/` 下 `chrome-devtools-mcp` 的 marketplace 源 / 缓存 `.mcp.json` / `plugin.json` manifest（旧插件安装法残留；新装法用 npm 全局包 + `--scope project`，已不再产生这些文件）
>
> 这些都是**用户级 / 全局共享**文件、server 名往往是通用 `chrome-devtools`（**不是**本约定的 `chrome-{git_user}`），改任何一处都会污染本机所有项目并互相覆盖。**远程地址只能写项目根 `.mcp.json`**——这正是远程必须用 `chrome-{git_user}`（`--scope project`）而非通用 `chrome-devtools` 的原因（二者并存、前缀不同、不冲突）。

> ✅ **强制校验闸门 = `.aidp/scripts/chrome-mcp-doctor.py`（脚手架下发到项目根，本节机制的单一信源）**：本节的「写/合并 `.mcp.json` + 连通性预检 + 全局污染检测 + 生效验证指引」全部由该脚本固化为有退出码的硬闸，命令端**只调它、不再各自内联实现**（约定 21；用法详见 `scripts/README.md`）：
> - **写/合并 + 复位**：`python3 .aidp/scripts/chrome-mcp-doctor.py set --ip <IP:9222>`（JSON 合并保留其它 server + 自动清 `.gitignore` 残留）；远程不可达/需重启想本地兜底 → `set --local-headless`（**清掉远程 MCP 条目、切 `chrome-devtools-cli` 本地无头**，免 MCP、免重启）；清空重收 → `reset`。
> - **体检 + 退出码分流**：`check` 返回 `0 就绪 / 3 缺配置 / 4 远端不可达（打印 Chrome 启动参数）/ 5 用户级/全局 MCP 配置被写脏（打印复位指引）/ 2 参数错`，命令端按码分流（见 0.0.5 / 0.1.5）。
> - **该调哪套工具**：远程一律调本项目 server 的 `mcp__chrome-{git_user}__*`（如 `mcp__chrome-{git_user}__list_pages`）；**严禁**调插件自带的 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`（那是插件自起的本地浏览器，连不到你的远端）。脚本每次 `check` 都打印当前 git_user 对应的正确前缀。
> - **用户级/全局已被写脏怎么救**：脚本**只读**探测上述禁改文件——纯净的通用 server `chrome-devtools` 的 args **只有包名、绝无任何 `--` 开头参数**；一旦发现 `--browser-url`/`--headless`/`--executablePath` 等注入 = 被历史会话写脏 → **唯一正解 = 移除该用户级/全局注册再改走项目级**（`claude mcp remove chrome-devtools --scope user`；历史插件残留则卸载插件）回到纯净，脚本与命令端**绝不手改**用户级/全局文件。
> - **生效验证 + 反模式（最易违反，必须钉死）**：写/改 `.mcp.json` 并重启后，**必须**用 `mcp__chrome-{git_user}__list_pages` 验证连到目标 IP；**若重启后唯一可用的 chrome 工具仍是通用那套 `mcp__…chrome-devtools__*`（用户级/全局注册或历史插件）** → 项目 server 未加载（多半首次未批准信任）→ **停止并上报**，⛔ **严禁退而去读/改任何用户级/全局 MCP 配置（`~/.claude.json` / `~/.claude/settings*.json` / 历史 `~/.claude/plugins`）「修 IP」**——「观察到项目根 `.mcp.json` 不生效 → 顺手去改用户级/全局配置」是**已知反模式**，明令禁止（改用户级/全局省不掉重启，只会污染全机；唯一正解永远是改项目根 `.mcp.json` + 重启）。

1. **位置 + 文件名**：**项目根** `.mcp.json`（固定路径；Claude Code 启动**自动加载**，无需任何命令行参数）。
2. **入库提交（不 gitignore）**：`.mcp.json` 是标准项目级 MCP 配置，**随仓库提交、团队共享**；命令端确保它**不在** `.gitignore`（历史遗留把它或旧路径加进 `.gitignore` 的，移除该行）。
3. **MCP server 条目名**：`chrome-{git_user}`（`{git_user}=$(git config user.name)`，由建文件的执行者解析；与通用名 `chrome-devtools` 不同名，二者并存不冲突）。
4. **写入方式（必须 JSON 合并，不可整体覆盖）**：`.mcp.json` 可能已托管团队其它 MCP server → 命令端**只增改 `chrome-{git_user}` 这一个 key、保留其余 server**（用 JSON 解析合并，严禁 `cat >` 整体覆盖把别人配置冲掉）。
5. **内容**（命令端按当前远程 IP 生成/合并该 key）：
   ```json
   {
     "mcpServers": {
       "chrome-{git_user}": {
         "command": "npx",
         "args": ["-y", "chrome-devtools-mcp@latest", "--browser-url", "http://<远程 IP>:9222"]
       }
     }
   }
   ```
6. **生效方式（无需任何启动参数；★ `/mcp` 重连 ≠ 重启）**：项目根 `.mcp.json` 由 Claude Code **仅在启动时读取一次、自动加载**——**不需要 `--mcp-config`**。改了 IP / 首次启用后，**必须整体重启 Claude Code**（`claude --dangerously-skip-permissions -c`，`-c` 续上本次会话不丢上下文）才按新配置注册；**首次加载会弹一次「是否信任本项目 MCP server」批准框**，批准后该项目不再询问。⛔ **`/mcp` 重连只对已加载的 server 重新握手、加载不了新增/改动的条目**——新增 `chrome-{git_user}` 或改 IP 后**别指望 `/mcp` 生效**，只有整体重启才行。

> ⛔ **生成时机铁律（最早时机即建，不拖到场景判定/可达性之后）**：只要能确定远程 chrome IP，命令端**必须无条件生成/合并** `.mcp.json` 的 `chrome-{git_user}` 条目——**不论 IP 来自测试方案 `TESTPLAN_CHROME_ADDR`（预填）还是交互收集**。`TESTPLAN_CHROME_ADDR` 非空只让命令**跳过交互式 IP 收集**（不弹 AskUserQuestion），**绝不跳过本条目的生成/合并 + 重启引导**。
> - **最早触发点 = Phase 0.0.5 读到测试方案 chrome 地址（`TESTPLAN_CHROME_ADDR` 非空）的那一刻**：IP 已知即建/合并 `.mcp.json`，**不等 0.1.1 MCP 检查 / 0.1.2 环境探测 / 0.1.3 场景判定 / 任何可达性验证**（0.0.5 已内置此步骤）。
> - **0.1.5 Step 0 = 兜底再确认**：当 IP 来自 baseline 或交互收集（0.0.5 未从测试方案命中 IP）时，在此补建/合并。
> - 两处都执行，确保文件在"能确定 IP 的最早一刻"就已存在——根除"IP 已知却迟迟不建 / 根本不建"。

> ⛔ **调用顺序铁律 + `.mcp.json` chrome 条目的维护方**：连接远程 chrome MCP 的顺序**只能是**——① **先写/合并** 项目根 `.mcp.json` 的 `chrome-{git_user}` 条目（0.0.5 / 0.1.5 Step 0，用已知 IP）→ ② **重启 Claude Code**（启动自动加载新配置，无需 `--mcp-config`；首次批准信任）→ ③ 才连上远程 chrome。**绝不允许**"先启动/先连接、运行时再收集 IP 改文件试连"（MCP 启动时锁定，运行时改文件不热生效）。`.mcp.json` 中 chrome 条目由 **`/sprint-aiauto-test`（本命令 0.0.5 / 0.1.5）与 `/sprint-autopilot`（Phase 0.0 Step 5）共同写/合并**——两者用**同一套合并逻辑**（只增改 `chrome-{git_user}` key、保留其它 server）、**远程地址单一信源 = `.mcp.json` 的 `chrome-{git_user}`**，谁先拿到远程 IP 谁先建，幂等不冲突；autopilot 作为前置配置收集方常先建好，本命令跑测时再确保一次。`/sprint-plan` 测试方案只记录 Chrome IP、不建本文件。**两命令都绝不改任何用户级/全局 MCP 配置（`~/.claude.json` 等，含 `claude mcp add --scope user`/全局）**。

> 🏷️ **MCP tool 前缀随 server 名**：server 条目名 = `chrome-{git_user}`，故远程下浏览器操作工具实际前缀为 **`mcp__chrome-{git_user}__*`**（如 `mcp__chrome-{git_user}__navigate`）。本文档其余处为可读性仍以 `mcp__chrome-devtools__*` 占位书写，**远程运行时一律按本节 server 名替换前缀**；检测 / 调用 MCP tool（0.1.1 方式 1、0.1.5-A、Phase 2.2）均按 `chrome-{git_user}` 前缀。

