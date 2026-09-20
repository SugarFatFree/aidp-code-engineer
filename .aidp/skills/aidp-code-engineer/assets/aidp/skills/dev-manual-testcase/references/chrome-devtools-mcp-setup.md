# chrome-devtools-mcp 安装与启动指引

> 隶属 SKILL: `dev-manual-testcase`
> 用途: 当用户启用 AI 浏览器自动化时,Agent 必须把以下指令完整告知用户,并在自测方案 §2.2 中引用本文件。

**chrome-devtools** 是 Chrome DevTools 官方提供、可经 npm 全局安装(`npm i chrome-devtools-mcp@latest -g`)的 AI 浏览器自动化方案,基于 Chrome DevTools Protocol 与浏览器调试端口直连。它按**连接位置**分两条接入路径(各自决定工具形态),两条路径都可叠加**渲染模式**(无头 / 有头):

**① 接入路径(由连接位置决定工具形态):**
- **本地路径 → `chrome-devtools-cli` 技能(CLI 直调,全称技能名 `chrome-devtools-mcp:chrome-devtools-cli`)**:Claude Code 与 Chrome **同机**时,用 CLI 直连本机调试端口。
  > ⚠️ **命令名 ≠ 技能名(务必分清,否则会误判"未装"):** `chrome-devtools-cli` 是 chrome-devtools-mcp 插件里的**技能名**,**不是命令名**;它实际调用的命令是 **`chrome-devtools`**(`npm i chrome-devtools-mcp@latest -g` 安装后可用)。用法为 `chrome-devtools <tool>`(如 `chrome-devtools list_pages`),自检用 `chrome-devtools status`。**不存在名为 `chrome-devtools-cli` 的二进制**——凡自检 / 调用 CLI 一律用命令 `chrome-devtools`,**用 `command -v chrome-devtools-cli` 自检会误判"未装"→ 静默降级 MCP、驱动报告失真**。下文出现的 `chrome-devtools-cli` 均是技能名 / 路径引用(如 `/chrome-devtools-mcp:chrome-devtools-cli`),不要当命令去执行。
  
  CLI 是命令行逐次调用,`--headless=new` 等启动参数在**调用时传入**,**不依赖常驻 MCP 服务、不读 MCP 配置文件**。因此**切换无头 ↔ 有头只是给本机 chrome 加 / 去 `--headless=new`,即时生效,无需重启 Claude Code**。这是日常自测的默认路径。
- **远程路径 → `chrome-devtools-mcp`(MCP 服务)**:Claude Code 与 Chrome **异机**时(本地无 GUI 却需有头、或 WSL/SSH 跨机场景),用 MCP 服务连接远程已启动的 chrome 调试服务,端点(`<远程 IP>:9222`)写入 MCP 配置文件。**仅首次配置 / 更换远程端点时才需改 MCP 配置 + 重启 Claude Code**(见 §6)。

> **⚠️ 连接模式判定护栏(Critical,本地侧对偶,勿误连共享 / 远程实例):**
> - **同机 + 项目根无 `.mcp.json`(即未注册自己的 `chrome-<git_user>` 远程服务)→ 必判本地模式、必走 `chrome-devtools-cli`(CLI 直调)**;这是日常自测的默认场景。
> - **仅当**确为异机、**且已按 §1 注册 `chrome-<git_user>` 服务(`--scope project` 写入项目根 `.mcp.json`)**,才判远程、走 `chrome-devtools-mcp`。
> - ★ **MCP 远程变体绝不得当作"本地 CLI 的替代"**:无用户后缀的**通用名 `chrome-devtools` / 工具 `mcp__chrome-devtools__*`** 属 MCP 远程变体(驱动共享 / 远程 Chrome),本机场景误用它 = 连错实例,`list_pages` 会混入他人标签页、串测污染。这是 §1"远程注册须 `chrome-<git_user>` + `--scope project`、禁用通用名"规则的**本地侧对偶**——**本地默认走 `chrome-devtools-cli`(命令 `chrome-devtools`),不得回退到连共享 / 远程实例的通用名 MCP 变体;仅命令短期不可用时才按下条显式降级到插件自起隔离实例**。
> - **缺 CLI 入口的处理(先诊断、再显式降级、绝不静默):** 本地模式但**疑似缺 `chrome-devtools` 命令**时:
>   1. **先诊断命令名 / PATH**——多数是把技能名 `chrome-devtools-cli` 当成命令名去查(`command -v chrome-devtools-cli` 必然查不到),应改查 `command -v chrome-devtools`、跑 `chrome-devtools status`;或 npm 全局 bin 目录不在 PATH(`npm i chrome-devtools-mcp@latest -g` 后 `npm bin -g` 加进 PATH)。**多数一修即回落本地 CLI。**
>   2. **短期修不了**时,同插件的 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`(**自起本机独立隔离 Chrome**,非共享 / 远程实例)可作**显式声明的**降级,并把实际驱动如实写入报告 **driver 字段**(取值 **`cli | mcp-remote | mcp-plugin-fallback | manual`**),**不得静默切换**。
>   3. **被禁止的只是无用户后缀通用名 `mcp__chrome-devtools__*`(连共享 / 远程实例)**,**不是**插件自起的隔离实例 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`。

**② 渲染模式(优先无头,两条路径都适用):**
- **无头模式(headless,首选默认)**:Chrome 以 `--headless=new` 启动,不渲染可见窗口,**无需 GUI 桌面环境**,在纯命令行 / 服务器 / WSL / SSH 环境也能跑。**应优先使用无头模式。**
- **有头模式(headed,按需)**:Chrome 渲染可见窗口,需要 GUI 桌面环境。**仅在以下场景才切有头**:① 需被网站当成真人(反无头 / 反爬虫检测,如部分风控、验证码、`navigator.webdriver` 嗅探拦截无头)② 需测试不同分辨率 / 真实视觉渲染效果 ③ 无头模式下页面无法正常加载 / 操作(部分依赖 GPU、WebGL、媒体自动播放的页面)。

**模式选择决策树:**
1. 默认 → **无头 + 本地(CLI)**:本机装 Chrome 即可,无需 GUI 桌面,`chrome-devtools-cli` 直调免重启;
2. 命中上述 3 种有头场景之一 → **有头模式**:
   - 本地有 GUI 桌面 → **有头 + 本地(CLI)**:同样走 `chrome-devtools-cli`,给本机 chrome 加不加 `--headless=new` 即时切换,**免重启**;
   - 本地无 GUI 桌面 → **有头 + 远程(MCP)**:走 `chrome-devtools-mcp` 连接到具备 GUI 的远程 chrome 服务,端点写入 MCP 配置。

> **核心收益:** 日常的无头 ↔ 有头切换都走本地 `chrome-devtools-cli`,**免改配置、免重启 Claude Code**;只有切到远程(本地无 GUI 却需有头)这种少见场景,才需配置 MCP 端点并重启一次。

> 生成方案时,Agent 必须**自动检测本地是否安装 Chrome**(本地 CLI 路径的前置),未安装则引导用户安装,详见 §2.0。

---

## 0. 适用范围(Critical 前置门槛)

**chrome-devtools-mcp 仅适用于"前端是 Web 网页"的项目**(运行于 Chrome / Edge / Chromium 内核浏览器,通过 Chrome DevTools Protocol 接管页面)。其他客户端类型必须使用其他自动化方案,严禁强行套用本工具。

| 客户端类型 | 是否适用 chrome-devtools-mcp | 推荐替代方案(若需 AI 自动化) |
| :- | :-: | :- |
| **Web 网页**(Vue/React/Angular SPA、传统多页应用、H5、PWA、企业内部 Web 后台) | ✅ 适用 | — |
| **移动端 H5 / 混合 App 内嵌 WebView**(可拿到 WebView 调试端口) | ⚠️ 有条件适用 | 需对方 App 开放 WebView 调试,通常仅 Debug 包支持 |
| **微信小程序 / 支付宝小程序 / 抖音小程序** | ❌ 不适用 | 微信开发者工具自动化 / Minium / 小程序专用 MCP(若有) |
| **iOS 原生 APP** | ❌ 不适用 | XCUITest / Appium + iOS Driver |
| **Android 原生 APP** | ❌ 不适用 | UI Automator / Espresso / Appium + Android Driver |
| **跨平台移动端**(React Native / Flutter / uni-app 编译为 APP) | ❌ 不适用 | Appium / Detox / Flutter Driver |
| **桌面客户端**(Electron 调试包) | ⚠️ 有条件适用 | Electron 开放 `--remote-debugging-port` 时可用,与 Web 同步骤 |
| **桌面客户端**(原生 WPF / WinForms / Qt / Cocoa) | ❌ 不适用 | WinAppDriver / pywinauto / PyAutoGUI |
| **CLI / TUI 工具** | ❌ 不适用 | expect / pexpect / Bash 测试框架 |

**Agent 强制前置检查:** 用户表示要启用 AI 浏览器自动化时,Agent **必须先确认自测方案 §3.1 客户端类型**:
1. 若 §3.1 客户端类型 = `Chrome / Edge / Safari / Firefox / Chromium 浏览器` → 继续启用 chrome-devtools-mcp
2. 若 §3.1 客户端类型 = 桌面客户端 / 移动 APP / 小程序 / 其他非 Web → **拒绝**配置 chrome-devtools-mcp,向用户回复"chrome-devtools-mcp 仅适用于 Web 网页项目,你当前是 XX 类型,建议改用 YY 方案",并把上表"推荐替代方案"列发给用户
3. 若客户端类型为"Electron 桌面"或"App 内嵌 WebView" → 询问是否开放调试端口;开放则按本文档继续,未开放则同 2

**严禁的行为:**
- ❌ 用户客户端是小程序/APP/桌面客户端,Agent 仍引导用户安装 chrome-devtools-mcp 并配置 9222 端口
- ❌ 自测方案 §3.1 客户端类型为空或填了"待用户填写",Agent 跳过确认直接启用 chrome-devtools-mcp
- ❌ 用例步骤里出现"在小程序中点击按钮"但 §2.2 启用 chrome-devtools-mcp(类型不匹配)

---

## 1. 安装 chrome-devtools-mcp

```bash
# 全局安装 chrome-devtools-mcp(npm)
npm i chrome-devtools-mcp@latest -g
```

> 安装后在 Claude Code 注册 MCP 服务(服务名按 git 用户区分,`<git_user>` = `git config user.name`,如 alice → `chrome-alice`):
>
> ```bash
> claude mcp add "chrome-$(git config user.name)" --scope project chrome-devtools-mcp
> ```
>
> 重启 Claude Code 后即可在会话中使用。
>
> ⚠️ **两条强制约束**:
> - **服务名 = `chrome-<git_user>`**(取自 `git config user.name`):这样多人共享项目根 `.mcp.json` 时各自的 chrome MCP 服务名不冲突;Claude Code 中该服务的工具即以 `chrome-<git_user>` 前缀出现(如 `mcp__chrome-alice__*`)。**不要**用固定的 `chrome-devtools` 等通用名。
> - **作用域强制项目级(`--scope project`,写入项目根 `.mcp.json`)**:**禁止** `--scope user`(用户目录)或任何全局注册。MCP 服务只随项目走,不污染用户/全局配置;换项目须在该项目内重新注册。

> 安装后即同时具备**本地 CLI**(`chrome-devtools-cli`,本地路径用,免 MCP 配置)与**远程 MCP 服务**(`chrome-devtools-mcp`,远程路径用)两种形态:本地路径无需重启即可用;远程路径首次配置端点后需重启一次(见 §6)。

---

## 2.0 生成方案时:自动检测本地 Chrome 安装(无头 / 有头本地模式前置)

只要方案走**本地模式**(无头本地 或 有头本地),Chrome 必须装在 Claude Code 所在机器上。**Agent 在生成方案、写 §2.2 前必须主动跑一次检测命令**,确认本机是否已安装 Chrome / Chromium:

```bash
# Linux(检测常见可执行名)
command -v google-chrome google-chrome-stable chromium chromium-browser 2>/dev/null

# macOS(检测应用包)
ls -d "/Applications/Google Chrome.app" 2>/dev/null || mdfind "kMDItemCFBundleIdentifier == 'com.google.Chrome'" 2>/dev/null

# Windows(PowerShell,检测默认安装路径)
Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe", "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
```

**检测结果分支:**
- **已安装** → 记下**检测结论**(而非冻结绝对路径),在 §2.2「本地 Chrome 检测结果」标注 `✅ 本机已检测到 Chrome/Chromium`,继续。⚠️ §2.2 文档按版本提交、团队共享,而各成员机器安装路径不同(mac `/Applications/Google Chrome.app`、Linux `/usr/bin/google-chrome` 或 `chromium-browser`、Windows `C:\Program Files\...`、npx 拉起等),**不得**把本机绝对路径写死当团队固定配置;文档应记录"Chrome 是否可用 + 如何自行探测(上方 command -v 等命令)"这一稳定事实。**如需记录路径,须标注为本机探测值、仅供参考、非团队固定配置**(括号内路径可留可不留)。
- **未安装** → **不得静默跳过**,必须**引导用户安装**,并在 §2.2 标注 `❌ 未检测到本地 Chrome,已引导用户安装(待用户确认安装后再连接)`:
  - Linux(Debian/Ubuntu):`wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo apt install -y ./google-chrome-stable_current_amd64.deb`;或 `sudo apt install -y chromium-browser`
  - macOS:`brew install --cask google-chrome`;或访问 <https://www.google.com/chrome/> 下载安装
  - Windows:访问 <https://www.google.com/chrome/> 下载安装包,或 `winget install Google.Chrome`
- **本地无 GUI 又必须有头** → 本地装 Chrome 也无法有头渲染,改走**有头 + 远程模式**(连接到具备 GUI 的远程 chrome mcp 服务),本机无需安装 Chrome。

> 远程模式下 Chrome 装在远程机器,本机检测结果不作为阻断项,但需确认远程机已装 Chrome 且(有头时)有 GUI。

---

## 2. 个人电脑启动 Chrome 调试模式(本地/远程模式都需要)

**无头模式(首选,无需 GUI):**

```bash
# Linux / macOS(无头)
google-chrome --headless=new --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir=/tmp/chrome-debug
```

```powershell
# Windows PowerShell(无头)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --headless=new --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="$env:TEMP\chrome-debug"
```

**有头模式(需 GUI,仅反无头 / 测分辨率 / 无头不可用时):去掉 `--headless=new` 即可**

```powershell
# Windows PowerShell(有头)
& "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="$env:TEMP\chrome-debug"
```

> 提示:`--user-data-dir` 必须指向独立的临时目录,避免与日常浏览数据冲突;`--remote-allow-origins=*` 用于允许跨域调试连接(测试环境足够,生产环境慎用)。`--headless=new` 是 Chrome 新版无头模式(行为最接近有头),旧的 `--headless` 已弃用。有头模式需对应机器具备 GUI 桌面环境,否则启动会失败,应改走有头 + 远程模式。

> **本地路径切渲染模式只动这条命令:** 本地走 `chrome-devtools-cli` 时,这条 chrome 启动命令的 `--headless=new` 开关就是无头 / 有头的唯一切换点——加上即无头、去掉即有头,**重启 chrome 进程**即可,CLI 随后连同一调试端口,**Claude Code 无需重启**。

---

## 3. 远程模式追加:开启端口转发(Claude Code 与 Chrome 异机时必做)

Windows 在 IPv6 `::1:9222` 启动调试端口,需要把 IPv4 `0.0.0.0:9222` 转发到 IPv6 才能让远端 Claude Code 访问。

PowerShell(管理员):

```powershell
# 启动端口转发(把本机 0.0.0.0:9222 的请求转发到 Chrome 的 IPv6 ::1:9222)
netsh interface portproxy add v4tov6 listenaddress=0.0.0.0 listenport=9222 connectaddress=::1 connectport=9222

# 查看现有端口转发
netsh interface portproxy show all

# 删除端口转发(测试结束后清理)
netsh interface portproxy delete v4tov6 listenaddress=0.0.0.0 listenport=9222
```

> WSL 用户特别提示:WSL 中的 Claude Code 访问 Windows 宿主 Chrome 时按"远程模式"处理,使用宿主 IP(可在 PowerShell 用 `ipconfig` 查得)而非 `localhost`。

---

## 4. 验证 Chrome 调试端口可用

```bash
# 本地模式
curl http://localhost:9222/json
# 远程模式(把 ip 替换成个人电脑实际 IP)
curl http://<远程 IP>:9222/json
```

返回的 JSON 含 tab 列表即代表调试端口已就绪。

---

## 5. 启用前必须收集的信息(Agent 主动询问,缺一不可)

| 项目 | 必填条件 | 用途 |
| :- | :-: | :- |
| **客户端类型** | **始终必填(P0,前置门槛)** | 必须为 Web 浏览器(Chrome/Edge/Safari/Firefox/Chromium 内核);非 Web 类型直接拒绝启用,见 §0 适用范围 |
| **渲染模式** | **始终必填(默认无头)** | 无头(首选,无需 GUI) / 有头(仅反无头 / 测分辨率 / 无头不可用时);有头本地需 GUI,无 GUI 则走有头 + 远程,见头部决策树 |
| **本地 Chrome 检测** | 本地模式必填 | 生成方案前自动检测本机是否装 Chrome;未装则引导安装,见 §2.0 |
| 测试环境访问地址 | 始终必填 | AI 浏览器打开的入口 URL |
| 测试账号与密码 | 始终必填 | 自动化登录(默认手动登录后让 AI 接管也可,用户明确即可) |
| 调试端口模式 | 始终必填 | 本地模式(走 `chrome-devtools-cli`,免 MCP 配置、免重启)/ 远程模式(走 `chrome-devtools-mcp` 服务) |
| 调试端口 | 始终必填(默认 9222) | 与 `--remote-debugging-port` 一致 |
| 个人电脑 IP | 远程模式必填 | 端口转发与 mcp 连接目标 |
| 是否已执行端口转发 | 远程模式必填 | 远程模式必须先转发,否则 mcp 无法连通 |
| **单步操作等待上限** | 始终必填(默认值需用户确认) | 每步操作 ≤ 3 秒、首次打开页面 ≤ 30 秒;防止页面卡死 / 元素不出现时 AI 无限等待。默认值须用户确认后正式启用 |
| **关键步骤截图** | 始终必填(有头/无头都要求) | 关键步骤(登录/提交/状态变化/断言/报错)必须截图留痕;无头无可见窗口,截图是唯一执行证据,见 §5.2 |

---

## 5.1 单步操作等待上限(超时阈值)

启用 chrome-devtools-mcp 时,Agent **必须主动**为浏览器单步操作设定等待上限,写入自测方案 §2.2 与用例文档"附录:AI 浏览器执行入口":

- **默认值**:每步操作(点击 / 输入 / 等待元素 / 断言)等待 **≤ 3 秒**;**首次打开页面**(冷启动、首跳)放宽到 **≤ 30 秒**
- **超时处理**:单步超过阈值即判该步"卡死",AI 工具须记录当前 URL + 截图 + 最后操作后**继续下一步 / 下一用例**,**严禁无限等待**把整轮自测拖垮(符合"问题记录优先"原则)
- **用户确认**:默认值**需用户确认后才正式启用**,用户可调整为其它数值;确认前在 §2.2 标注 `(默认值,待用户确认)`,且不得据此默认值进入 AI 自动执行

---

## 5.2 关键步骤截图(有头 / 无头都要求)

启用 chrome-devtools-mcp 时,**无论有头还是无头模式**,Agent 都必须在自测方案 §2.2 与用例文档"附录:AI 浏览器执行入口"写明关键步骤截图要求:

- **关键步骤定义**:登录 / 提交 / 状态变化 / 断言通过或失败 / 报错弹窗 / 页面跳转完成 等对判定结果有意义的节点
- **为何无头也要截图**:无头模式没有可见浏览器窗口,**截图是唯一能留存的执行证据与验证依据**;有头模式虽可见,也必须截图存档以便事后复核与缺陷举证
- **落地要求**:AI 工具在每个关键步骤调用截图能力(如 `take_screenshot`)并保存到测试产物目录;截图文件名建议含用例 ID + 步骤号(如 `TC-USER-001-step3.png`)
- **判定约束**:关键步骤缺失截图 = 该步执行无证据,**不予判定通过**;单步超时卡死时(见 §5.1)也须先截图再继续

---

## 6. 接入配置:本地 CLI 免重启,远程 MCP 改端点才重启

接入路径决定要不要动配置、要不要重启 Claude Code:

**本地路径(`chrome-devtools-cli`)—— 免 MCP 配置、免重启:**
- CLI 直连本机 `localhost:9222` 调试端口,**不读 MCP 配置文件**;
- **无头 ↔ 有头切换** = 改本机 chrome 启动命令的 `--headless=new` 开关(见 §2)并**重启 chrome 进程**即可,**Claude Code 无需重启**;
- 这是日常自测的默认路径,切换渲染模式零中断。

**远程路径(`chrome-devtools-mcp`)—— 端点写 MCP 配置,改端点才重启:**
- 远程 chrome 的端点(`<远程 IP>:9222`)写入 Claude Code 的 MCP 配置文件(注册规则见 §1:服务名 `chrome-<git_user>`、`--scope project` 写入项目根 `.mcp.json`,禁用 `--scope user`/全局);MCP 配置项**只在 Claude Code 启动时读取一次**,运行期改动不热生效;
- **仅在以下两种情况**才需"改 MCP 配置 + 重启 Claude Code":① 首次启用远程路径、配置远程端点 ② 更换远程机器 / 端口;
- 远程的**无头 / 有头由远程机器的 chrome 启动参数决定**(在远程机加 / 去 `--headless=new` 并重启远程 chrome),与本地 Claude Code 是否重启无关。

> 一句话:**本地切渲染模式不用重启 Claude Code;只有"切到远程 / 换远程端点"才需要改 MCP 配置并重启一次。** 远程路径切换前若该重启没重启,MCP 仍按旧端点连接,会出现"以为切了、实际没切"的不一致。

> **⚠️ 本地路径默认走 CLI、不得回退通用名 / 共享远程 MCP 变体(Critical):** 本地路径(同机)默认用 `chrome-devtools-cli`,**绝不**改用连共享 / 远程实例的 MCP 远程变体顶替——尤其**无用户后缀通用名 `chrome-devtools` / `mcp__chrome-devtools__*` 是 MCP 远程变体**(驱动共享 / 远程 Chrome),本机误用会连错实例、`list_pages` 混入他人标签页串测污染。**判定口径:** 同机 + 项目根无 `.mcp.json`(未注册 `chrome-<git_user>`)→ 必走本地 `chrome-devtools-cli`;仅确为异机 + 已注册 `chrome-<git_user>`(`--scope project`)才走远程 `chrome-devtools-mcp`。本机若疑似缺 `chrome-devtools` 命令,**先诊断命令名 / PATH**(注意技能名 `chrome-devtools-cli` ≠ 命令名 `chrome-devtools`,应查 `command -v chrome-devtools` / `chrome-devtools status`;多数一修即回落本地 CLI);短期修不了才可用**显式声明的**降级——同插件 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`(自起本机隔离 Chrome),并把实际驱动如实写入报告 driver 字段(`cli | mcp-remote | mcp-plugin-fallback | manual`),**严禁静默切换到通用名 `mcp__chrome-devtools__*` / 共享远程实例**。

---

## 7. Agent 兜底行为

用户启用 AI 浏览器自动化但**未提供**测试环境地址 / 账号密码 / 调试端口模式 /(远程模式)远程 IP+端口时,Agent **必须主动追问**这些信息,**严禁**臆造默认地址(如 `https://test.example.com`)或留空 placeholder 直接生成用例;追问时把上述安装/启动/转发命令一并发送给用户,引导其按指引启动调试服务。

---

## 8. 用户拒绝启用 AI 浏览器自动化时

自测方案 §2.2 标注"未启用",AI 执行辅助指令章节可省略,默认走"用户手动浏览器执行"流程。本文档不再适用。
