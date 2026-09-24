<!-- 二次切分 · phase-0 片5/9：覆盖 0.1.5 远端用户机引导-->
# /sprint-aiauto-test · 执行分片 分片 [5/9]（0.1.5 远端用户机引导）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-0-5.md`。理据见同目录 `rationale.md`。

#### 0.1.5 远端用户机引导（场景 C，按 0.1.1.5 铁律走"先配置后启动"流程）

> ⛔ **遵守 0.1.1.5 远程连接铁律**：本步骤**不**在 Claude Code 已经启动的情况下"运行时连接"，而是引导用户**先**按 0.1.1.4 在**项目根 `.mcp.json`** 配好/合并远程地址 + **后**重启 Claude Code（启动自动加载，无需 `--mcp-config`）。第一次进入本步骤通常以"提示用户配置 + 退出命令"结束，重启后再跑命令才进 Phase 0.2。

**Step 0 — 无条件先建/合并项目根 `.mcp.json`（必做、与可达性无关）**：进入本步即按 0.1.1.4 用**已知远程 IP** 生成/合并**项目根 `.mcp.json`** 的 `chrome-{git_user}` 条目（`--browser-url http://<IP>:9222`，JSON 合并保留其它 server）+ 确保它**不在** `.gitignore`（入库提交）。已知 IP 优先级：① 测试方案 `TESTPLAN_CHROME_ADDR`（非空则直接用、**不问用户**）→ ② 项目根 `.mcp.json` 已有的 `chrome-{git_user}` 远程地址 → ③ 都没有 → 才在下方 B.2 用 AskUserQuestion 收集后回填本文件。无论 IP 来源、无论 MCP 当前是否可达，文件都先建好。
> **执行 = `python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py set --ip <IP:9222>`**（写/合并 + 连通预检 + 污染检测 + 生效指引一步到位，退出码见 0.1.1.4）：`rc=5`（用户级/全局 MCP 配置被写脏）→ 先按脚本指引复位（移除 `--scope user`/全局注册、历史插件残留则卸载），**绝不手改用户级/全局**；`rc=4`（远端不可达）→ 文件仍已建好，按打印的 Chrome 启动参数让用户修远端 + 重启后复跑；`rc=0/3` → 进下方 A/B 分支。**脚本缺失（脚手架未下发/旧版）→ 由 Phase 0.0.5 的内联 python 兜底写 .mcp.json**（绝不因单点脚本缺失写不出；并建议重跑 `aidp-code-engineer upgrade` 补回脚本——已达目标版本也会自愈下发）。

**步骤分支**（Step 0 建好文件后）：

> ⛔ **本片三处降级（A0 / B0 两支）落 `DRIVER=cli` 后，必须同步重写驱动真值**——总纲
> （`phase-0-2.md`）明写「后续任何驱动降级/切换都必须同步重写本字段」，而三处一处都没落。
> 不重写的后果：收尾门 3i 拿**最初打算用的驱动**去判报告如实性——报告如实填 `cli` 反被判失真 FAIL，
> 或报告跟着填旧值（与实际不符）却全绿。每处降级后加：
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test DRIVER cli
> [ -n "$BUILD" ] \
>   && python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" --build "$BUILD" set driver_actual cli \
>   || python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" set driver_actual_pending cli
> ```
> （降级到 `mcp-plugin-fallback` 时把上面的 `cli` 换成 `mcp-plugin-fallback`。）

**A0. ★ 远端不可达 + 本机有 chrome + 非强制远程 → 自动降级本地无头 cli（零交互、不退出、不重启）**：Step 0 的 `chrome-mcp-doctor.py set` 返回 `rc=4`（远端不可达）时，**先判是否"强制远程"**——测试方案「二·连接模式」显式写"远程" **或** 用户本轮显式指令要求远程 = 强制远程（此时不静默降级，落下方 B 提示用户修远端 + 重启）；**否则**（远程只是"已配置"而非"强制"，见命令主体「本地 CLI 无头优先·远程不抢占」铁律）**且本机 chrome 可用**（`CHROME_BIN` 非空）→ **自动改走 0.1.3 场景 A/B 本地无头**：置 `DRIVER=cli` + `--headless=new`（`chrome-devtools-cli` 免 MCP、免重启、立即继续），终端只记一行 `⚠️ 远端 <ip> 不可达 → 自动降级本机无头 cli（远程非强制；如需远程请修远端后重跑）`，**直接进 Phase 0.2；绝不弹 `AskUserQuestion`（retry/换IP/abort）、绝不退出命令**。必须"有头"的用例按既有机制延后（见 3.5/3.6）。仅当**本机 chrome 也不可用**（`CHROME_BIN` 空，本就无可降级目标）才落下方 B「先配后启 + 退出」。⛔ **无人值守 `/loop` 下尤须如此**：远端不可达绝不能把无人值守卡在弹窗或退出。

**A. 当前 chrome-devtools-mcp 已可达**（任一 `mcp__chrome-{git_user}__*` tool 调用成功 / `ToolSearch` 返回非空；前缀按 0.1.1.4 server 名 = 说明 Claude Code 启动时已自动加载项目根 `.mcp.json`）→ ✅ 直接进 Phase 0.2，**零交互**。

**B. 当前 chrome-devtools-mcp 不可达**（文件已由 Step 0 建好，但本次 Claude Code 启动时它还不在 / 未被信任批准，故未加载）→ **先过下方 B0「绝不无限等待」闸门**，仅本机无可兜底时才走"先配后启"引导：

**B0. ★ 绝不无限等待重启 —— 本机 chrome 可兜底则自动降级 cli（超时上限 180s）**：进入分支 B（远程 MCP 未加载、需重启才生效）时，**先判本机能否兜底**（`CHROME_BIN` 非空 = 本机有 chrome 可起无头）：
   - **本机无 chrome 可兜底**（`CHROME_BIN` 空）→ 无降级目标，**跳过 B0**、落下方 B 标准「先配后启 + 退出」引导。**★ 按驱动源分两种收尾（无人值守降级要播报+让位，绝不静默退出）**：① **autopilot 驱动**（`REPORT_ENABLED=1` / 有 `current_build`）→ 极端兜底由 `/sprint-autopilot` 按"照常进开发 → 开发完发里程碑通知说明原因 → 退出"处理（见 autopilot Phase 0.6 / 子流程 R）；② **standalone 测试 loop**（`REPORT_ENABLED=0`、无 autopilot 驱动）→ 版本级冻结（四件套 + #4 + 本地告警台账一次做完；同 reason 已冻结时脚本 no-op、不重发 #4），退出本 tick、**不空转**；环境恢复后 0.1.1 检测通过即 `--clear` 解冻，另有环境类自动复探：
     ```bash
     eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
     python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --freeze-now \
       --phase 0.1.5-remote --reason chrome-unavailable \
       --why "本机无 chrome 且远端不可达，浏览器实测无法执行；在运行 Agent 的机器装 Chrome（npm i chrome-devtools-mcp@latest -g 提供 chrome-devtools 命令）或修复远端"
     exit 0
     ```
   - **本机 chrome 可用 + 非强制远程**（远程只是"已配置"而非测试方案「二·连接模式」显式"远程"/用户显式指令）→ **立即降级本机无头 cli**（铁律「本地 CLI 无头优先·远程不抢占」，与 A0 同款，零等待）：置 `DRIVER=cli` + `--headless=new`，记一行 `⚠️ 远程 MCP 未加载（需重启）+ 远程非强制 → 直接走本机无头 cli（免重启）`，**进 Phase 0.2，不退出、不打重启引导**。
   - **本机 chrome 可用 + 强制远程**（用户明确要远程）→ 远程需重启才生效，但**绝不无限空等**：
     - **交互式（非 `/loop`）**：打印重启 3 步指引（下方步骤 1~3）**+ 一行倒计时声明**：`⏳ 我最多等你 3 分钟重启走远程；期间可 Ctrl+C 退出去重启，若 180s 内未接管我将自动切本机无头 cli 兜底继续（免重启）`。然后**等待上限 180s**（有界轮询，每 ~30s 复探一次 `mcp__chrome-{git_user}__*` 是否已可达 / 远端是否仍在），到点仍未被接管 → **自动置 `DRIVER=cli` + `--headless=new` 进 Phase 0.2**，记一行 `⏳ 180s 超时未重启 → 自动降级本机无头 cli 兜底继续（如仍要远程请修复后重跑）`。
     - **`/loop` 无人值守**：**无人可重启 → 不空等**，直接置 `DRIVER=cli` + `--headless=new` 进 Phase 0.2，记一行 `⚠️ 无人值守 + 远程需重启 → 直接走本机无头 cli 兜底`。
   - ⛔ **共同红线**：B0 的本地兜底一律走 `chrome-devtools-cli`（直连 CDP、免 MCP、免重启），**绝不**写 `chrome-devtools-mcp --headless` 这类 MCP 无头条目（那仍要重启、与本兜底初衷相悖）；如需清理残留远程 MCP 条目用 `python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py set --local-headless`（清条目 + 切 cli）。必须"有头"的用例按既有机制延后（见 3.5/3.6）。

> ⛔ **进入分支 B 的第一道红线（最易被违反，必须先读）**：此时你能调到的往往只有通用名的用户级/全局 server `chrome-devtools`（用户级/全局注册或历史插件残留，IP 可能是旧的、连错的）。**无论它连到哪个 IP、无论你"觉得"哪个用户级/全局文件才是真正生效源**——都**禁止**去读/改 `~/.claude.json` / `~/.claude/settings*.json` / 历史 `~/.claude/plugins/` 下任何文件来"修 IP"。本分支的**唯一动作**就是：① 确认/合并项目根 `.mcp.json`（Step 0 已建）→ ② 打印重启指引（自动加载，无需 `--mcp-config`）→ ③ **主动退出命令**等用户重启。重启后项目 server `chrome-{git_user}` 才会被加载、连上正确 IP（见 0.1.1.5 禁止反模式 + 决定性事实）。**改用户级/全局文件省不掉重启，只会污染全机——零理由这么做。**

1. **读项目根 `.mcp.json` 的 `chrome-{git_user}` 地址**（仅用于打印参考值，不用于"运行时改地址重连"）：
   - 有该条目 → 打印「`.mcp.json` 已配好远程 IP `<ip>`，但本次启动时它还未被加载（首次需信任批准）— 见步骤 2 重启」
   - 无该条目 → 进 2

<!-- flowvar-check: allow REMOTE_IP Step 0 已确定的 chrome 远端 IP（测试方案预填 / baseline），由命令端在进入本围栏前注入 -->

2. **确认远端 chrome 可达性**（命令端只验证 chrome 进程在不在监听，**不**为 MCP 改任何配置）：

   ```bash
   # IP 来源：Step 0 已确定（测试方案预填 / baseline）；仅 Step 0 case ③（无任何已知 IP）+ Phase 0.0.6 Step 5 也未收到远程 IP 时才用
   # ★ 无人值守（LOOP_UNATTENDED=1）→ 绝不 AskUserQuestion：远程 IP 属测试方案配置缺失，冻结后退出本 tick
   #   （补 研发自测/「二·Chrome Remote Debugging 地址」后按 mtime 自动解冻）。
   #   ⛔ 这段**必须是可执行语句、不能写成注释**：注释态下执行体跑完围栏就穿过去了，
   #      既不冻结也不告警 —— 心跳照刷、开发链路读到「测试链路健康」走暂缓，
   #      12 tick 后按 unconverged 误冻，而真因完全不可见（散文≠落盘，见 flows/sprint-batch/rationale.md）。
   # ⛔ shell state 不跨 Bash 调用：本围栏要用 tick 变量就必须自己 eval 一次读回。
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
   if [ -z "${REMOTE_IP:-}" ] && [ "${LOOP_UNATTENDED:-0}" = 1 ]; then
     python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test \
       --version "$TARGET_VERSION" --freeze-now --phase 0.1.5-remote --reason testplan-incomplete \
       --why "强制远程但无已知 chrome 远端 IP，无人值守无法收集"
     exit 0
   fi
   # 交互式：AskUserQuestion 收集 chrome 所在电脑 IP（含 192.168.x.x / 10.x.x.x / 172.16.x.x + Other），收集后回填 Step 0 的文件。
   # ★ 正常路径下远程 IP 已在 0.0.6 Step 5「一次性收全」阶段问过，此处不重复弹窗（见 0.0.6 一次性收全守卫）。
   curl -s -m 5 "http://${REMOTE_IP}:9222/json/version"
   ```
   - 200 → chrome 监听 OK；进 3 引导用户重启
   - 失败 → 打印失败原因（chrome 没启 / portproxy 未配 / 防火墙拦截）+ 让用户先按下方"完整启动命令"在自己电脑上把 chrome 跑起来，跑通后再回来运行 `/sprint-aiauto-test`

3. **核心引导 — 项目根 `.mcp.json` 已配好 + 重启 Claude Code（启动自动加载）**（按 0.1.1.4 约定）：

   ```
   ✅ chrome 远端 9222 端口可达：http://<ip>:9222/json （已验证）

   ⛔ 但 chrome-devtools-mcp 当前不可达 — 本次启动尚未加载项目根 .mcp.json。
      MCP 只在启动时读配置一次，运行时改任何文件都不热生效，必须按以下顺序操作：

   ━━━━━━━━━━━━━━━ 必须 3 步（顺序不可颠倒）━━━━━━━━━━━━━━━

   【步骤 1 — 项目根 .mcp.json】（命令端已自动写好/合并，确认即可）
   文件：<项目根>/.mcp.json   ← 启动自动加载，无需任何参数；入库提交、团队共享
   内容（已含其它 server 时只追加了 chrome-{git_user} 这一项）：
     {
       "mcpServers": {
         "chrome-{git_user}": {
           "command": "npx",
           "args": ["-y", "chrome-devtools-mcp@latest", "--browser-url", "http://<ip>:9222"]
         }
       }
     }

   【步骤 2 — ★ 重启 Claude Code（无需 --mcp-config）】
   完全关闭 Claude Code 后在同一项目目录重新打开（不是 /clear，是关程序）：
     - 退出：Ctrl+C 两次 / 输入 /exit
     - 重新打开：
         claude --dangerously-skip-permissions -c
       （-c 续上本次会话不丢上下文；项目根 .mcp.json 启动时自动加载；--dangerously-skip-permissions 免权限打断，适合 /loop 守护）
     - ⚠️ 首次加载会弹一次「是否信任本项目的 MCP server」→ 选信任/批准（之后该项目不再问）
   MCP 只在启动时读配置一次；不重启则新地址不生效

   【步骤 3 — 重启后回来跑】
   /sprint-aiauto-test                                 # 重启后再跑，命令会从 Phase 0.1.1 重检测
   或 /sprint-aiauto-test --once                       # 单次模式

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   完成上述 3 步后 chrome-devtools-mcp（server `chrome-{git_user}`，工具前缀 `mcp__chrome-{git_user}__*`）
   应可达 Phase 0.1.1 检测，命令会自动进 Phase 0.2 不再问 IP。

   ★ 如果你以前已配过但用错了 IP：命令端会用新 IP 合并更新项目根 .mcp.json，你只需重启 — 这是同一个流程。
   ```

4. **命令端动作**：① 按 0.1.1.4 生成/合并**项目根 `.mcp.json`** 的 `chrome-{git_user}` 条目（`--browser-url http://<ip>:9222`，保留其它 server）——**远程地址只此一处，baseline 不再写 `chrome_remote_ip`**；② 确保 `.mcp.json` **不在** `.gitignore`（入库提交，旧路径残留一并移除）；③ 然后**主动退出**命令（不进 Phase 0.2），让用户重启后重新跑（无需 `--mcp-config`）。

**用户自己启动 chrome 的完整命令**（同 `docs/testing/{version}/研发自测/` 配置中「chrome-devtools-mcp 启动指南」一致）：

   ```
   ⚠️ 命令端无 GUI / 无 Chrome / 9222 未监听，需要你在自己电脑上让 chrome-devtools-mcp 能连上 Chrome：

   ━━━━━━━━━━━━━━━━━ Windows 远程方案（推荐 — 4 步） ━━━━━━━━━━━━━━━━━

   【步骤 1 — PowerShell：启动 Chrome 远程调试】
   & "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="$env:TEMP\chrome-debug"

   【步骤 2 — PowerShell（管理员）：启动端口转发，让远程 Claude Code 可连本机 9222】
   netsh interface portproxy add v4tov6 listenaddress=0.0.0.0 listenport=9222 connectaddress=::1 connectport=9222

   【步骤 3 — PowerShell：查看端口转发规则（验证步骤 2 成功）】
   netsh interface portproxy show all

   【步骤 4 — 验证 chrome-devtools-mcp 可连上】
   浏览器打开：http://<你的 IP>:9222/json
   能看到 JSON 列表 = 配置成功

   清理（任务结束后）：
   netsh interface portproxy delete v4tov6 listenaddress=0.0.0.0 listenport=9222

   ━━━━━━━━━━━━━━━━━ macOS / Linux 远程方案 ━━━━━━━━━━━━━━━━━

   【步骤 1 — 启动 Chrome 远程调试】
   # macOS：
   open -a "Google Chrome" --args --remote-debugging-port=9222 --remote-allow-origins='*' --user-data-dir=/tmp/chrome-debug
   # Linux：
   google-chrome --remote-debugging-port=9222 --remote-allow-origins='*' --user-data-dir=/tmp/chrome-debug &

   【步骤 2 — 关闭防火墙 9222 端口或反向 SSH 隧道】
   # macOS/Linux 上默认监听 0.0.0.0:9222，远端可直接连；若有防火墙开放该端口即可。

   【步骤 3 — 验证】
   curl -s http://<你的 IP>:9222/json | head

   ━━━━━━━━━━━━━━━━━ 本机有 GUI + Chrome 时（最简） ━━━━━━━━━━━━━━━━━

   命令端会自动按 OS 启动 Chrome（详见 Phase 0.1.4），无需任何手动操作；
   仅在命令端无 GUI / 无 Chrome / 9222 未监听时才走本远程引导。

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   把你电脑的 IP 告诉我（PowerShell：ipconfig | findstr IPv4 / Linux/macOS：ip addr 或 ifconfig）
   ```

