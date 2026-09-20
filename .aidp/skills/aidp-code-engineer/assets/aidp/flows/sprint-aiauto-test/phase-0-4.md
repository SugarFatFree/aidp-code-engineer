<!-- 二次切分 · phase-0 片4/9：覆盖 0.1.1.5 模式切换铁律 / 0.1.2 环境探测 / 0.1.2.1 实例归属 / 0.1.3 场景分流 / 0.1.4 自启命令-->
# /sprint-aiauto-test · 执行分片 分片 [4/9]（0.1.1.5 模式切换铁律 / 0.1.2 环境探测 / 0.1.2.1 实例归属 / 0.1.3 场景分流 / 0.1.4 自启命令）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-0-4.md`。理据见同目录 `rationale.md`。

#### 0.1.1.5 ★ 模式切换铁律（**仅 `DRIVER=mcp-remote` 远程**：改配置后须重启 — 防"首次配置错就要重启" 坑）

> ✅ **`DRIVER=cli`（本地）整节豁免**：本地浏览器走 `chrome-devtools-cli`，**不依赖 MCP 服务、不读启动期配置**——切有头/无头只需改本机 chrome 启动的 `--headless=new` 开关 + **重启本机 chrome 进程**（本地秒级），**无需重启 Claude Code**。本节「改 MCP 配置 + 重启 Claude Code」铁律**只对远程 `DRIVER=mcp-remote`** 成立；本地场景跳过本节，可在同一会话自由切模式（CLI 调用细节详见依赖 SKILL）。
>
> ⛔ **以下仅 `DRIVER=mcp-remote`（远程）适用** — chrome-devtools-mcp 的 MCP 配置（连接地址 + chrome 启动参数，含 `--headless=new` 无头开关）只在 Claude Code 启动 / plugin 加载时读取一次：
> 一旦 plugin 用错误配置初始化，**运行时改任何文件都没用** — 必须改 plugin / MCP 配置文件 + **重启 Claude Code** 才能让 MCP 用新配置重连。
>
> 这意味着：① 远程场景命令端**不能**"先收集 IP 后连接试错"；② 切换**有头 ↔ 无头**或**本地 ↔ 远程**，都必须**先改 MCP 配置文件、再重启 Claude Code** 才生效（否则"以为切到无头、实际仍是有头"）。统一走"先配置后启动"流程。
>
> ③ **由②推出的执行铁律（仅 `DRIVER=mcp-remote` 远程）**：既然远程切模式必须重启、中途切不动，**远程无头跑时绝不为了"切去跑有头用例"而中途停**，也绝不在命令内部运行时尝试切模式（必失败）；无头闭环收敛判定 + 切有头提醒见 Phase 3.5。**`DRIVER=cli`（本地）不受此条约束**——CLI 即时切有头，同会话补跑即可。

**铁律**（适用于所有"chrome 远程"场景 — `/sprint-aiauto-test` Phase 0.1.3 场景 C — 以及任何**有头/无头渲染模式切换**）：

1. **先**按 0.1.1.4 在**项目根 `.mcp.json`**（server 条目 `chrome-{git_user}`）中**写好/合并远程 chrome 地址**（`http://<远程 IP>:9222`）；
2. **后**重启 Claude Code（`claude --dangerously-skip-permissions -c`）——项目根 `.mcp.json` **启动自动加载，无需 `--mcp-config`**；首次弹一次信任批准；
3. **最后**才能跑 `/sprint-aiauto-test`。

**禁止反模式**（命令端不可走这条路径）：
- ❌ Claude Code 已经启动 → AskUserQuestion 收集 IP → 试图运行时连接 → 失败后改 baseline / 改配置文件再试 → 仍连不上 → 莫名其妙重启 Claude Code
- ❌ **去改任何用户级 / 全局 MCP 配置来切远程地址** ：详见同目录 `rationale.md`「禁改用户级/全局 MCP 配置的两条反模式」。
- ❌ **"用户级/全局那份看起来已经对了，那真正生效的源一定在别处" → 顺藤摸瓜去找/改用户级/全局 MCP 配置或历史插件缓存** ：详见同目录 `rationale.md`「禁改用户级/全局 MCP 配置的两条反模式」。

> ⛔ **决定性事实（断掉"改用户级/全局更省事"的念头）**：MCP 配置**只在 Claude Code 启动时读一次**，所以无论改用户级/全局 MCP 配置还是改项目根 `.mcp.json`，**都必须重启 Claude Code 才能生效**——改用户级/全局**省不掉这次重启**。既然两条路都要重启，就**绝无任何理由**去碰用户级/全局文件：改项目根 `.mcp.json` + 重启（启动自动加载），与改用户级/全局 + 重启，重启成本完全相同，但前者零污染、后者污染全机所有项目。**永远走项目根 `.mcp.json` 这条路。**

**正确流程**（详见 Phase 0.1.5）：
- ✅ Phase 0.1.5 检测到远程场景 + 当前 MCP 不可达 → **不试连**；改为：① 按 0.1.1.4 生成/合并项目根 `.mcp.json` + 给出重启指引；② 强制要求用户**先配文件再重启 Claude Code（启动自动加载，无需 `--mcp-config`）**；③ 当前命令**主动退出**，让用户在重启后重新跑 `/sprint-aiauto-test`
- ✅ 如果用户已正确预配且 MCP 可达 → 直接进 Phase 0.2，零交互

#### 0.1.2 命令端环境探测（按 OS 自动跑 Bash）

```bash
# ★ 跨分片取回本 tick 变量 —— flow 每个分片是**独立的 Bash 调用**，shell 变量不持久；
#   漏这一行会让下方判据读到空串、`${VAR:-默认}` 静默落默认值（恒真/恒假）。
#   真源在 baseline 的（BUILD/DRIVER/DEPLOY_MODE/NOTIFY_ENABLED/LOOP_UNATTENDED…）由脚本自动回落。
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
OS=$(uname -s)
# GUI 可用性
case "$OS" in
  Linux)   GUI_OK=$( [ -n "$DISPLAY" ] && command -v xset >/dev/null && xset q >/dev/null 2>&1 && echo 1 || echo 0 ) ;;
  Darwin)  GUI_OK=1 ;;
  *)       GUI_OK=$( [ -n "$WSLENV" ] && echo 0 || echo 1 ) ;;
esac
# Chrome 是否已装
case "$OS" in
  Linux)   CHROME_BIN=$(command -v google-chrome || command -v chromium || command -v chromium-browser) ;;
  Darwin)  [ -d "/Applications/Google Chrome.app" ] && CHROME_BIN="open -a 'Google Chrome'" ;;
  *)       [ -f "/c/Program Files/Google/Chrome/Application/chrome.exe" ] && CHROME_BIN="/c/Program Files/Google/Chrome/Application/chrome.exe" ;;
esac
# ★ 立即落盘（勿删）：两者的消费点在**别的分片**（phase-0-5 的 A0/B0 降级判据读「CHROME_BIN 非空」），
#   而分片间是不同的 Bash 调用、shell 变量不跨调用存活；其 BASELINE_FALLBACK 指向的
#   root:chrome_bin / root:gui_ok **全仓无写入者**，不落盘则读回恒空 →
#   「本机有 chrome 可兜底」永远判为假 → 远端不可达时不降级本地无头，直接落「先配后启 + 退出」。
python3 .aidp/scripts/autopilot_tick_flags.py set --command aiauto-test CHROME_BIN "${CHROME_BIN:-}"
python3 .aidp/scripts/autopilot_tick_flags.py set --command aiauto-test GUI_OK "${GUI_OK:-0}"
# 驱动模式：本地用 chrome-devtools-cli（免重启切模式）/ 远程用 chrome-devtools-mcp（须重启）
# 缺省本地 cli；Phase 0.1.3 场景 C（远端）改 mcp；本地 CLI（命令 chrome-devtools）不可用→回退 mcp-plugin-fallback（同插件隔离实例、免重启，见 0.0.7；探测走 check-cli/SKILL）
DRIVER="cli"
# ⛔ 9222 探测【仅对远程 MCP / 手工起 chrome + --browser-url 连接】有意义。chrome-devtools CLI 走 daemon + --isolated
#    【自起临时隔离实例、根本不读 9222】——在 CLI 路径下探测 9222 属【误导性信号】，会让执行体误以为"在复用某个外部
#    实例"，后续一切实例相关现象都被套进这个错误框架解释（实际项目中出现过据此编造"共享实例被抢占"的虚构故障）。故按 MODE 分流：
if [ "${MODE:-local}" = "remote" ]; then
  CHROME_RUNNING=$(curl -s -m 2 http://localhost:9222/json/version | grep -q "Browser" && echo 1 || echo 0)   # 9222 端口是否已有 Chrome（仅远程/手工场景有意义）
else
  CHROME_RUNNING=n/a   # ★ 本地 CLI 路径：实例归属以 `chrome-devtools status` 的 daemon args 为准（见 Phase 0.1.2.1），不看 curl、不看 9222
fi
# 渲染模式：取 Phase 0.0.5 从测试方案「二·渲染模式」行解析的值（TESTPLAN_RENDER_MODE）；缺省无头
RENDER_MODE="${TESTPLAN_RENDER_MODE:-headless}"   # headless（默认，无需 GUI）| headed
# ⛔ 必须落 tick 命名空间：消费点全在别的 Bash 调用，普通赋值跨不过去 →
#   回读恒落静态默认 headless，测试方案声明的「有头」必被吞掉（见 rationale.md）。
python3 .aidp/scripts/autopilot_tick_flags.py set --command aiauto-test \
  RENDER_MODE "$RENDER_MODE" >/dev/null 2>&1 || true
```

#### 0.1.2.1：★ 实例归属权威判定（CLI 路径必跑一次，结论写入报告 notes）

> **一手判据：daemon 的 args 决定连什么实例——不看 curl、不看端口 9222**。`chrome-devtools` CLI 走 daemon（unix socket、跨命令跨会话长驻），其 args 里**有无 `--browser-url`** 决定连的是外部实例还是自起隔离实例。这是区分"实例异常"与"正常隔离实例行为"的**唯一权威依据**（下游曾因缺此步、用 curl 9222 二手信号臆断出虚构故障）。

```bash
# ★ 仅 DRIVER=cli / mcp-plugin-fallback 路径必跑；读 daemon args 判定实例归属（不看 curl、不看 9222 端口）
if chrome-devtools status 2>&1 | grep -qE '"?--browser-url"?'; then
  OWNERSHIP="external-browser-url"   # 连外部实例（远程 / 手工起 chrome via --browser-url）
else
  OWNERSHIP="isolated-self-spawned"  # --isolated 自起隔离实例（daemon 跨会话长驻，历史标签页属正常残留，与任何外部 9222 无关）
fi
echo "实例归属判定：$OWNERSHIP（依据 = chrome-devtools status 的 daemon args，非 curl 9222）"
```

- **判定结论必须写入 AI测试报告 `data.notes`**（`实例归属: isolated-self-spawned` 或 `external-browser-url:<url>`），供事后排查区分"实例异常"与"正常隔离实例行为"。
- ⛔ **此后凡涉及"实例被抢占 / 被其他进程导航 / 复用了某外部实例"的现象，一律以本步 `OWNERSHIP` 为准解释**——`isolated-self-spawned` 时 daemon 里出现的历史/非目标标签页是**本执行体早先操作的正常残留、不是"他人 Chrome"**（外部进程根本连不进 `--isolated` 实例），正确动作 = `select_page` 切回目标页继续（见 Phase 0.0.7 反捏造硬约束）。

#### 0.1.3 三种场景分流

> ★ **渲染模式优先无头（对齐 dev-manual-testcase）**：无头模式 `--headless=new` **无需 GUI 桌面**，Linux 服务器 / WSL / SSH 也能本机自启；因此**本机自启不再强制 GUI**，仅"有头模式且本机无 GUI"才被迫走远程。

| 场景 | 判定 | 驱动 `DRIVER` | 命令行为 |
|------|------|------|------|
| **A. 本地 CLI（自起隔离实例·默认）** | `MODE=local`（CLI 路径；`CHROME_RUNNING=n/a`） | `cli`（本地） | `chrome-devtools` CLI daemon **自起 `--isolated` 临时隔离实例**（用完自动清理、不读 9222、与任何外部 9222 无关；⛔ **非"复用外部本机 Chrome"**）→ **先跑 Phase 0.1.2.1 实例归属判定** → 进 Phase 0.2；浏览器操作走 `chrome-devtools-cli`（详见 SKILL） |
| **B. 手工起 chrome（子模型）** | `CHROME_BIN 非空 && CHROME_RUNNING=0 && (RENDER_MODE=headless 或 GUI_OK=1)`（**仅当显式走手工起 chrome + `--browser-url` 连接、非 CLI daemon 自起时**）| `cli`（本地） | 命令端按 OS 自动启动 Chrome（无头加 `--headless=new`，详见 0.1.4）+ 等 3 秒 + 探测 9222；浏览器操作走 `chrome-devtools-cli` |
| **C. 远端用户机** | `CHROME_BIN 空` **或**（`RENDER_MODE=headed && GUI_OK=0`，即有头但本机无 GUI）| `mcp-remote`（远程） | 走「远端 Chrome 引导」（详见 0.1.5）：从项目根 `.mcp.json` 读 `chrome-{git_user}`，无则一次性 AskUserQuestion 收集 + 写入 `.mcp.json` 复用；浏览器操作走 `chrome-devtools-mcp` |

> ⛔ **场景 A/B 的实例归属澄清**：本地 CLI 路径（场景 A）默认由 `chrome-devtools` CLI daemon **自起 `--isolated` 隔离实例、根本不读 9222**——`CHROME_RUNNING`（9222 探测）对它是**误导性信号**、恒 `n/a`（见 0.1.2 分流）。**实例归属一律以 `chrome-devtools status` 的 daemon args 为一手权威判据**（见 **Phase 0.1.2.1**），**不看 curl、不看端口**。场景 B（探测 9222 + 手工起 chrome + `--browser-url`）只是"显式手工起 chrome"子模型，**不是 CLI daemon 的默认行为**；把 CLI daemon 自起隔离实例误说成"复用某个外部 9222 实例"，正是虚构"共享实例被抢占"故障的源头。

> 🔀 **驱动分流铁律**：场景判定后即定 `DRIVER` —— **本地（A/B）= `cli`**（不依赖 MCP 服务、切有头/无头即时免重启，0.1.1.5 整节豁免、Phase 2.0-E 不延后、Phase 3.5 跳过）；**远程（C）= `mcp`**（须先配后启 + 重启，0.1.1.5 全套铁律生效）。CLI 启动 / 连接 / 操作 / 渲染 flag 的具体命令**详见依赖 SKILL**（`references/chrome-devtools-mcp-setup.md`）；本命令只在编排层按 `DRIVER` 分流。
> ⚠️ **本地 CLI（命令 `chrome-devtools`，非 `chrome-devtools-cli`）不可用时的降级（按 Phase 0.0.7 序列，不再"改配置+重启+DRIVER=mcp-remote"旧口径）**：先由 `check-cli` 诊断修 PATH/装包回落 cli；短期修不了 → **`mcp-plugin-fallback`**（同插件 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`、自起本机隔离实例、**免重启**），报告 `driver` **如实填 `mcp-plugin-fallback`**（严禁填 `cli`/`mcp`）。详见 Phase 0.0.7 + `check-cli` + SKILL。
> ⛔⛔ **任何 chrome 系报错先跑 `chrome-mcp-doctor.py explain-error --error '<原文>'` 再下结论**（0=not-a-blocker ⛔禁降级 / 1=blocker 须举证 / 3=未收录 ⛔先 check-cli）。典型：`Missing X server … headful` **不是**「浏览器不可用」，只是 MCP 默认起有头，改走本机 CLI 即可。**严禁**降级为 curl/JDBC 等非浏览器驱动——3i 对「driver_actual 不在白名单且无 `driver_downgrade_evidence`」FAIL。
> 🎯 **测试方案优先（三级优先级①）**：上表 `DRIVER` 为自动探测默认值；若测试方案「二·连接模式」行**显式写明**本地 / 远程，**按测试方案覆盖自动探测**（如测试人员指定"远程模式" → 强制 `DRIVER=mcp-remote`，即便本机能跑）。测试方案的连接模式 / 渲染模式 / 切换规则字段格式详见依赖 SKILL `test-plan-template.md`。
> 🟢 **本地无头优先 — 远程已配置不抢占（铁律）**：本机 Chrome 能起就走 `cli`；`.mcp.json` 里有远程条目**只表示「具备远程能力」、不是把 `DRIVER` 翻成 `mcp` 的理由**。完整论证见 `rationale.md`「本地无头优先」。

#### 0.1.3.5 ★ WebMCP 启动参数前置注入（启用时必跑；未启用整段跳过、不留痕）

> ⛔ **必须在这里、不能等 0.1.6**：白名单与特性开关都是**浏览器启动参数**，启动之后无法追加。
> 0.1.6（`phase-0-8.md`）排在浏览器已经起来之后，**判定再准也来不及**——实测症状就是
> 「项目明明启用了 WebMCP，实测却一路当它不存在」，且失败表现与"浏览器不支持"完全一样。
> 本步只做启动参数；0.1.6 的入参供给与驱动预检照旧，不重复。

```bash
# 前端访问地址取自 01_测试环境与账号.md / 测试方案（Phase 0.0.5 已解析）
# ⛔ 不传 --origin：前端地址由脚本自己读「测试环境与账号」（约定 38 保证在那里）。
#   flow 分片间 shell 变量不持久，传 $FRONTEND_URL 必取空 → 报错被吞 → WebMCP 静默永不启用。
python3 .aidp/scripts/check_webmcp.py --launch-args --driver cli --json
#   手工起 chrome 时传 --driver manual
```

| 返回 | 动作 |
| :- | :- |
| `error: webmcp-not-enabled` | **整段跳过**，按原样启动，⛔ 不打印、不 WARN、不写 run-context |
| `error: bad-origin` / `no-origin` | 报错停下补地址——⛔ 不许拿个大概的 origin 顶上：白名单是**逐字精确**匹配，scheme/host/port 差一个字符就不生效，而**不生效时没有任何报错**，只是 `isSecureContext` 依旧 false |
| 正常返回 | 把 `cli_args`（或 `chrome_flags` + `user_data_dir`）拼进本轮启动命令 |

**两条必须照做的操作纪律**（都属"参数被静默丢弃"，且丢弃时零报错）：

- **`DRIVER=cli`（默认路径）**：CLI daemon **跨会话长驻**，隐式启动不会带上新参数。
  故启用 WebMCP 时**必须显式重启一次**：`chrome-devtools start <cli_args…>`，
  ⛔ 不能依赖"直接跑工具命令时后台自动起"。
- **手工起 chrome（场景 B）**：**必须换独立 `--user-data-dir`**（结果里已给
  `/tmp/chrome-debug-webmcp`）。与既有实例共用目录时，Chrome 单例机制会把 URL 转交给
  先启动的那个实例、后启动的自己退出，**新增参数被静默丢弃**——实测表现是同一页面
  两次探测结论相反。

**版本门**：`--categoryExperimentalWebmcp` 要求 **Chrome 150+**（且 chrome 侧须带
`--enable-features=WebMCP` <!-- flag-check: ignore Chrome 启动参数，非 AIDP 命令旗标 -->，脚本已一并给出）。脚本探到本机低于 150 会在 warnings 里说明——
此时按**未启用**处理并在报告里注明版本原因，⛔ 不得报成"能力不存在"（那是两回事）。

> 📌 与「⛔ 不要自拟启动命令」的关系：那条约束是给三个上游 SKILL 的——**它们不知道环境**。
> 命令端知道（前端地址在手、浏览器也是它启的），故这里走**确定性推导**而非自拟：
> 同一个实现、可测、三处调用点共用。项目若已在 `01_测试环境与账号.md` 登记了完整启动命令
> （`--detect` 的 `launch_command` 非空），**以登记的那条为准**，本步的推导只作缺省兜底。

#### 0.1.4 本机自启 Chrome 命令（按 OS）

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# ★ 渲染模式开关：默认无头（无需 GUI）；有头模式置空（RENDER_MODE=headed 时）
HEADLESS_FLAG=$( [ "${RENDER_MODE:-headless}" = "headless" ] && echo "--headless=new" || echo "" )
# ★ WebMCP 启动参数（0.1.3.5）：未启用时恒为空串 → 下面三条命令与本能力上线前逐字节一致
WEBMCP_FLAGS=$(python3 .aidp/scripts/check_webmcp.py --launch-args --driver manual 2>/dev/null || true)
# ★ 第二道防线：只接受真的以 `--` 开头的启动参数。脚本侧已把 N/A 提示改走 stderr，
#   但这条捕获的结果会**直接拼进 chrome 启动命令**——任何一次回归（提示语误回 stdout、
#   或新增一行 info）都会把中文塞进命令行、并让下面的 `-n` 判定误命中清空 --user-data-dir。
case "$WEBMCP_FLAGS" in --*) : ;; *) WEBMCP_FLAGS="" ;; esac
# ⛔ WEBMCP_FLAGS 自带独立 --user-data-dir（专用目录），此时不能再传默认那个：
#    重复传 --user-data-dir 行为不确定；而共用目录会触发 Chrome 单例机制静默丢弃新参数。
UDD_FLAG="--user-data-dir=/tmp/chrome-debug"
[ -n "$WEBMCP_FLAGS" ] && UDD_FLAG=""

# Linux
nohup "$CHROME_BIN" $HEADLESS_FLAG --remote-debugging-port=9222 --remote-allow-origins='*' \
  $UDD_FLAG $WEBMCP_FLAGS --no-first-run --no-default-browser-check \
  >/dev/null 2>&1 &

# macOS
open -a "Google Chrome" --args $HEADLESS_FLAG --remote-debugging-port=9222 --remote-allow-origins='*' \
  $UDD_FLAG $WEBMCP_FLAGS --no-first-run

# Windows (Git Bash / WSL)：WEBMCP_FLAGS 里的专用目录为 POSIX 路径，Windows 下改用 "$TEMP\chrome-debug-webmcp"
"/c/Program Files/Google/Chrome/Application/chrome.exe" $HEADLESS_FLAG --remote-debugging-port=9222 \
  --remote-allow-origins='*' ${UDD_FLAG:+--user-data-dir="$TEMP/chrome-debug"} $WEBMCP_FLAGS --no-first-run &
```

启动后等 3 秒，`curl -s http://localhost:9222/json/version` 验证；失败 → 改走场景 C 远端引导。
（⚠️ 本段是**本机自启（场景 A/B = `DRIVER=cli`）**：切无头/有头**只需改本机 chrome 启动的 `--headless=new` 开关 + 重启本机 chrome 进程，Claude Code 无需重启**。「改 MCP 配置 + 重启 Claude Code」仅适用**远程 `DRIVER=mcp-remote`**，见 0.1.1.5。）

