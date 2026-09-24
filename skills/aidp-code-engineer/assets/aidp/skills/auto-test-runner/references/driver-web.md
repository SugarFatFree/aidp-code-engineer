# Web 浏览器驱动适配

> 端专有适配层文件。端无关的四原子能力契约、能力探测与优雅降级、扩展新端 SOP 见 `driver-adapters.md`。**本文件含端专有 API，属适配层——方法论层（`../SKILL.md` / `execution-methodology.md`）不得出现这些调用。**

> **★补充能力(条件启用):** WebMCP 工具调用(`invoke`)是本适配器的**可选第五能力**——
> 端专有调用约定、驱动版本要求、两个浏览器开关与连接后自检见
> [`driver-web-webmcp.md`](./driver-web-webmcp.md);**仅 旧 Web `webmcp_enabled: true`（或 `webmcp.enabled: true`）、或 `client_mcp.enabled: true` 且客户端=Web、实现形态=WebMCP 时加载**。⚠️ **两条门都要认**——只认旧 flag 会让「只传新声明 `client_mcp`」的 Web 项目扫不到本文件，整条 Web 叶子静默消失，方向是**假绿**。

---

### Web 浏览器 · 成熟度:已验证(主场景,MCP 插件工具)

- **驱动**:**chrome-devtools-mcp** 家族(推荐,Chrome DevTools 官方,`npm i chrome-devtools-mcp@latest -g`)/ **Playwright**(playwright-mcp / playwright-cli)。
  - ⚠️ **chrome-devtools-mcp 家族含两条路径,驱动的是不同 Chrome 实例,不可等价互顶**:
    - **本地 CLI = `chrome-devtools` 命令**:CLI 直调、同机、**免 MCP 配置**、**不读 `.mcp.json`**、驱动**本机独立 Chrome 实例**。同机自动化的**首选**。`chrome-devtools-cli` 是插件里的**技能名**(`/chrome-devtools-mcp:chrome-devtools-cli`),它逐次调用的**命令**就是 `chrome-devtools`(`npm i chrome-devtools-mcp@latest -g` 装出该 bin,自检 `chrome-devtools status`,用法如 `chrome-devtools list_pages`)。**不存在名为 `chrome-devtools-cli` 的命令/二进制**,勿据它 `command -v chrome-devtools-cli` 自检——要探 `chrome-devtools`。
    - **远程 / MCP 路径 = `mcp__…__*` 工具**(非命令,是 MCP 工具名):
      - `mcp__chrome-<git_user>__*` —— **自注册远程变体**,驱动**共享/远程 Chrome**;注册须服务名 `chrome-<git_user>`(取自 git user.name)+ `--scope project` 写项目根 `.mcp.json`。**仅异机场景用**。
      - `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*` —— **插件自带变体**,**自起本机独立隔离 Chrome**(非共享实例、无串测污染),可作 CLI 短期不可用时**显式声明的 last-resort 降级**(见第三节)。
      - **通用名 `mcp__chrome-devtools__*`(无用户后缀)= 连共享/远程实例**,同机误用会串测污染,被禁。
    - **硬边界**:本地 CLI 与远程 MCP 变体**不是等价次选**——CLI 缺失时**不得静默**降级到连共享/远程实例的 MCP 变体(端专有细则见下方「三·补一」,端无关口径见 `driver-adapters.md` 三、「同端多驱动」)。
- **四能力映射**:
  - `locate` → 从操作返回的无障碍树快照取元素 `ref`(getByText / getByRole+name);或 Playwright locator。
  - `act` → click / fill / selectOption / scroll / goBack / setInputFiles / handleDialog…
  - `observe` → 动作自动返回的增量快照 / 全量快照(chrome-devtools 用 `take_snapshot`、Playwright-MCP 用 `browser_snapshot`,勿混,见下方变体说明)/ DOM;**运行时错误通道**:拉 console 消息列表 + network 请求列表(non-2xx),写入 `runtimeErrors`;**运行环境通道(env)**:见下方「三·补三、Web 运行环境取证」。
  - `capture` → 每次只生成一张 screenshot 并返回实际 artifact 路径;无障碍树快照文本由 `observe` 单独提供,需要归档时另写 evidence 条目。

### 截图格式策略(仅 Web 适配层)

- **Chrome DevTools MCP / CLI 首选 WebP quality=90**(视觉近乎无损,不宣称数学意义像素无损),文件名 `{TC-ID}-step{N}.webp`:
  - MCP:`take_screenshot(format="webp", quality=90, filePath="...webp")`
  - CLI:`chrome-devtools take_screenshot <pageId> --format webp --quality 90 --filePath "...webp"`（`pageId` 为必填位置参数，先由 `list_pages` 取得）
- **明确不支持 WebP 才回退 PNG**:若当前工具版本明确拒绝 `format=webp`,本次 capture 清理可能产生的失败半成品后,只生成 `{TC-ID}-step{N}.png`,返回该 `.png` 的真实路径。不得先留一份失败/残缺 WebP 再额外生成 PNG,也不得把一次 capture 登记成两份等价截图。
- **Playwright 保持原生 PNG**:当前 screenshot API 不原生支持 WebP 时直接输出 PNG,不增加转码步骤。其他已有驱动产出的 `.jpg/.jpeg` 可兼容,但 JPEG 不作为 UI 截图默认格式。
- **不引入转码链**:不得为统一扩展名引入 Pillow、Sharp、ImageMagick、cwebp 等依赖。每次 capture 只生成一个实际可用的图片文件,并把返回路径原样写入 `evidence[].artifact`;失败时不创建空文件或伪造路径。
- **日志如实记录**:`capture TC-USER-001-step3 → webp q90`；回退时记 `capture TC-USER-001-step3 → png（驱动不支持 WebP）`。

### 客户端故障注入(标准手段)

Web 端对只验证前端呈现的失败/变慢/空响应场景,使用浏览器初始化脚本注入方式包裹 XHR/fetch(执行参数记作 `--initScript`),在页面加载前安装拦截逻辑;只允许返回失败、延迟或 `200 + 空数据`,不得写服务端配置、改业务代码或写业务数据。

- **可验证范围:** 骨架屏、空态、错误态、重试入口、超时文案等由前端请求结果决定的表现。
- **不可替代范围:** 上游字段落库、名额扣减、幂等去重和真实事务状态等服务端状态用例仍须真实样本,不得用客户端注入冒充验证。
- **必配阳性对照:** 故障注入用例必须再执行「全端点 `200 + 空数据`」对照,确认整页合法空态出现;否则“元素 0 命中”可能只是页面没走到对应渲染路径,不能判通过。
- **证据:** 记录注入类型、命中的端点、实际返回/延迟和阳性对照结果;初始化脚本未生效、端点未命中或响应无法判定时标环境/注入失败并 block。

- **适用**:Chrome/Edge/Safari/Firefox/Chromium 内核;Electron 调试包、移动端可调试 H5(WebView 开调试端口)有条件适用。

---

### Web 适配器样例(Playwright 风格)

```python
class WebAdapter:
    def __init__(self, page):          # page = 已连接的浏览器页面
        self.page = page

    def locate(self, sem):             # sem = 语义定位符(可见文案/角色+名称)
        # 优先按可见文本 / 角色定位,拿不到再按 label
        loc = self.page.get_by_text(sem) or self.page.get_by_role("button", name=sem)
        return loc if loc.count() else None    # 空句柄交 act 触发失败分级

    def act(self, handle, action, data=None):
        return {
            "tap":    lambda: handle.click(),
            "input":  lambda: handle.fill(data),
            "select": lambda: handle.select_option(data),
            "scroll": lambda: handle.scroll_into_view_if_needed(),
            "back":   lambda: self.page.go_back(),
            "upload": lambda: handle.set_input_files(data),
        }[action]()

    def observe(self):                 # 端无关结构化状态
        return {"page": self.page.title(), "url": self.page.url,
                "texts": self.page.locator("body").inner_text()[:2000]}

    def capture(self, tag):
        # Playwright 原生截图保持 PNG,不为追求统一扩展名引入转码。
        path = f"evidence/{tag}.png"
        self.page.screenshot(path=path)
        return path                    # 返回实际生成路径;Web 另可附无障碍树快照文本
```

> chrome-devtools-mcp 变体:`locate`+`observe` 共用一次 `take_snapshot` 无障碍树快照(元素 `uid` 即句柄),`act` 调 `click`/`fill`/`fill_form` 等(chrome-devtools MCP 工具是**裸名**,不带 `browser_` 前缀),`capture` 调 `take_screenshot` 并按上节优先 WebP q90。Playwright-MCP 变体才对应 `browser_click`/`browser_fill_form`/`browser_snapshot` 等 `browser_*` 工具,截图保持原生 PNG——两者勿混。

---

## 三·补一、本地 CLI ↔ 共享/远程 MCP 变体硬边界(不可自动互顶)

> 端无关口径(禁静默降级 / 先诊断修复 / 显式声明 last-resort / driver 字段如实记录 / `manual_confirm_required`)见 `driver-adapters.md` 三、「同端多驱动」;本节是 Web 端的落地细则。

- 本地 CLI(`chrome-devtools` 命令,CLI 直调、驱动**本机独立实例**)与连**共享/远程 Chrome** 的 MCP 变体(`mcp__chrome-<git_user>__*` / 无后缀 `mcp__chrome-devtools__*`)**不是等价次选**。
- **同机 + 无项目 `.mcp.json` 远程注册(`chrome-<git_user>`)** 时,**严禁**把连共享/远程实例的 MCP 变体当作本地 CLI 缺失时的自动次选/降级目标——否则会静默连到共享/远程 Chrome,`list_pages` 混入他人标签页、串测污染。
- **缺本地 CLI 时的可执行出路(先诊断修复,再 last-resort 降级):**
  1. **先按命名/PATH 诊断修复(多数一修即回落 cli)**:命令名探错(应探 `chrome-devtools`、非 `chrome-devtools-cli`)/ npm 全局 bin 未链进 PATH —— 修好后 `chrome-devtools status` 可跑即回落本地 CLI,driver 记 **`cli`**。
  2. **短期修不了时,可显式声明降级到插件自带 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`**(自起**本机独立隔离 Chrome**、非共享实例、无串测污染)—— 这是被允许的 last-resort;driver 须如实记 **`mcp-plugin-fallback`**。
  3. **确为异机远程**才用自注册 `mcp__chrome-<git_user>__*`,driver 记 **`mcp-remote`**;仍无路时人工介入,driver 记 **`manual`**。
- **driver 字段取值枚举:`cli | mcp-remote | mcp-plugin-fallback | manual`**。**严禁静默切换、严禁用了 plugin 却把 driver 填 `cli`**。区分:被禁的是连共享/远程实例的无后缀通用名 `mcp__chrome-devtools__*`,**不是**插件自起的隔离实例 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`。
- `detect_drivers.py web`(端类型为位置参数,非 `--client` 选项)对「仅远程 MCP 变体注册可用、本地 CLI 缺失」返回 `manual_confirm_required=true`(需人工确认、非自动可用),据此先按上述诊断/降级出路处理而非静默连共享实例。
- **Playwright 仍是 CLI 缺失时的合法同机次选**(本机独立实例),不受此边界限制。
- **★探测放宽(不可据 npm 空探测 block web):** web 主驱动 `mcp__..._chrome-devtools__*` 属**会话运行时能力,`detect_drivers.py` 探不到**。脚本对 web 已按「npm 包 **或** 本机 Chrome/Chromium 任一即可用」放宽;**仅当「MCP 工具未挂载 且 本机无 Chrome 且 无 npm 驱动」三者皆空时才 block web**,否则会误杀唯一真能跑的主场景端。

---

## 三·补二、Web 驱动执行前防呆(连错共享实例拦截)

> Web 驱动**连接后、跑用例前**必做一次「连对实例」自检,防止在共享/他人 Chrome 上串测(尤其误用 MCP 变体时)。

- **检查时机**:Web 适配器完成连接、进入首个模块入口流程**之前**。
- **检查动作**:读取当前会话的页面/标签列表(Web 适配器用 `list_pages` / 页面上下文;经 `observe` 契约暴露为端无关信号),逐个核对是否属本任务:
  - 出现**非本任务测试 URL 的业务页**(他人业务系统、与被测 URL 域名/路径无关的页面),或
  - 出现明显**非目标测试标签页**(数量远超本任务应有页数、含陌生登录态/账号)。
- **命中处理(停下确认,不静默继续)**:告警「**疑似连到共享/他人 Chrome,可能连错实例**(常见于同机误用连共享/远程实例的 `mcp__chrome-devtools__*`/`mcp__chrome-<git_user>__*` MCP 变体,而非本地 `chrome-devtools` 命令或插件自起隔离实例 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`)」→ **暂停,人工确认实例归属**后再跑;确认前**不得**在该实例上执行任何用例动作,避免污染共享实例上的他人数据。
- **端相关降级**:此防呆是 Web 驱动特有(共享实例风险源自 MCP 变体/远程 Chrome);移动/桌面/小程序端各自独立会话,无此项时跳过,不影响执行(与优雅降级一致)。

---

## 三·补二之二、`resetSession` 的 Web 落地(两个触发场景共用一套动作)

> `resetSession` 有**两个触发场景**,端无关口径分别在:① **换账号**——`execution-methodology.md` 第一节「跨角色套件之间必须重建干净会话」;② **驱动卡死自愈**——同文件第四节「驱动健康探测 + 自愈重启」。**本节只答 Web 端「怎么做才真的做得掉」,两个场景共用同一套动作。**

### 健康探活(`observe` 的 `driverAlive` 通道 · Web 落地)

| 端无关信号 | Web 落地 | 说明 |
| :- | :- | :- |
| `driverAlive` | **CLI 路径**:`chrome-devtools status` 有正常输出即 `true`;**MCP 变体**:`list_pages` 能返回页面列表即 `true` | 二者都**不依赖被测页面内容**——页面渲染不出来 ≠ daemon 死了,这正是要区分的两件事 |

- 探活必须带**独立超时**(`driver_health_timeout_s`,默认 15s);探活自己卡住 = 判 `driverAlive=false`。
- **判据顺序**:连续多次原子调用全超时 → 才去探活 → 探活也无回应 → 判驱动进程级卡死,进自愈。**单个元素 `locate` 失败绝不触发探活**,那是常规重试的事。

### ⚠️ 已实测**证否**的两种做法(看着合理,实际清不掉)

2026-08-18 实测(被测系统用 **HttpOnly 的 SSO 会话**):

| 试过的做法 | 实际结果 |
| :- | :- |
| `--isolatedContext`(**页面级**隔离上下文) | ❌ **隔离不了 HttpOnly 的 SSO 会话**——隔离粒度在页面/上下文,SSO 会话在驱动实例级 |
| `evaluate_script` 清 `document.cookie` | ❌ **清不掉 HttpOnly cookie**(JS 按设计就读写不到它)。点「登录」直接跳回上一账号的结果页,**连登录表单都出不来** |

**共同的坑**:两种做法都**不会报错**——页面照常能用,只是仍是旧账号。若不做第 3 步登录角色核对,后面整个套件都会用错角色跑完,权限类结论全错且看上去正常。

### ✅ 可靠做法:重启 daemon 换全新 profile

```bash
# 重建干净会话 / 卡死自愈:重启 daemon + 全新隔离 profile
# (--isolated / --headless 都是 daemon 启动期参数,重启这一刻正是唯一能重新指定它们的时机)
chrome-devtools stop && chrome-devtools start --isolated --headless
```

> **换账号场景**可以只 `start`(若 daemon 还活着,`stop` 后再 `start` 更干净);**卡死自愈场景必须 `stop && start`** —— daemon 已经不响应了,不先 `stop` 掉僵死进程,`start` 可能连不上或复用到那个僵死实例。

- **为什么必须重启 daemon**:`--isolated` / `--headless` 都是 **daemon 启动期**参数(见「三·补三」末段),daemon 已在跑时后续调用一律继承**它启动那一刻**的配置——不重启,传什么参数都不生效。
- **重启后必做两次 `observe`**:① 确认已回到未登录态/登录页;② 登录新角色后确认**当前登录角色 = 目标角色**。缺这一步等于没切。
- **重启即换实例**:`reusedInstance` 与 `renderMode` 等环境事实**随之改变**。若本轮已落盘 `env-facts.json`(每轮一次、首模块取证),重启发生在取证之后 → 在报告「遗留风险」注明本轮中途重建过实例;**不要偷偷改已落盘的取证结论**。
- **MCP 变体无 `start` 类工具**:插件自带/自注册远程变体的工具集只有页面级工具,**拿不到 daemon 生命周期控制**。此分支下 `resetSession` 视为**本端此变体不提供**——按优雅降级退回「UI 点退出登录 + `observe` 验证登录态已清空」,验不过标 `block(precondition-unmet)`。
- **Playwright 变体**:换账号起新的 `browser.new_context()`(无存储态)或换 `--user-data-dir` 即可,不必重启整个浏览器;**卡死自愈**则须重启 browser 进程本身(context 级重建救不了挂掉的进程)。

### 卡死自愈的 Web 完整动作序列(端无关流程见方法论第四节)

1. `chrome-devtools stop && chrome-devtools start --isolated --headless`(重启参数按 run-context「期望渲染模式」重新指定);
2. 重新走入口流程**登录当前套件所需角色**;
3. `observe` 恢复检验:**登录态 = 已登录、当前页 = 起始页**——核不过算本次自愈失败;
4. 从 tasks.md 断点续跑(`[√]` 跳过、`[>]`/`[ ]` 续跑,**不跨 build/round、不从头**);
5. 连续 `driver_heal_retry_limit`(默认 3)次自愈都失败 → 判 `block(driver-hung)` + 附证据(探活输出 / `stop`·`start` 返回 / 时间戳 / 已重试次数)。

> ⚠️ **重启即换实例**,`reusedInstance` / `renderMode` 等环境事实随之改变。本轮 `env-facts.json` 已落盘时**不要回头改它**——在报告「遗留风险」注明本轮中途重建过驱动实例即可(与换账号场景同一条约束)。

---

## 三·补三、Web 运行环境取证(observe 的 env 通道落地)

> 端无关口径(三条铁律 / 五类来源枚举 / 判定顺序 / 降级)见 `execution-methodology.md` 第十节;端无关信号名见 `driver-adapters.md` 第一节「observe 的运行环境通道」。**本节是 Web 端专有落地:读什么、怎么读、哪条判据当前还成立。**
>
> **时机**:与上一节「实例归属防呆」**同一时点、共用同一次读取**(驱动连接后、首条用例前,每轮一次)。

### 各端无关信号 → Web 落地

| 端无关信号 | Web 落地 | 当前有效性 |
| :- | :- | :-: |
| `runConfig` | **本地 CLI 路径专有**:`chrome-devtools status` 输出的 `args` 数组,直接含 `--headless` / `--isolated` 等**实际启动参数** | ✅ **权威,优先用** |
| `renderSignals` | `evaluate_script` 读 `navigator.userAgent`——新版无头 Chrome 的 UA 仍带 `HeadlessChrome` 标识 | ✅ 主判据 |
| `automationSignals` | `evaluate_script` 读 `navigator.webdriver` | ⚠️ **只证「被自动化驱动」**,有头 CDP 同样为 `true`,**不能判渲染模式** |
| `viewportSize` | `evaluate_script` 读 `window.innerWidth/innerHeight`(视口) | ✅ 作 `viewport` 事实字段 |
| `instanceOwnership` | `list_pages` 的页面集合(与防呆同一次读取):出现非本任务页面 ⇒ `reusedInstance=true` | ✅ |

取证调用(CLI 形态,MCP 变体同名工具等价;共 3 条命令,对方法论层视作一次 `observe`):

```bash
# ① 运行配置(权威)。⚠️ status 不支持 --output-format,输出是纯文本,
#    从其中的 args=[...] 行解析,形如 args=["--headless","--isolated",...]
chrome-devtools status
# ② 运行时信号
chrome-devtools evaluate_script '() => ({ ua: navigator.userAgent, webdriver: navigator.webdriver, vw: window.innerWidth, vh: window.innerHeight })'
# ③ reusedInstance(与实例归属防呆共用同一次读取,不重复调)
chrome-devtools list_pages --output-format json
```

> **`--output-format {md,json}` 只有页面级子命令有**(`list_pages`/`evaluate_script` 等),`status` 没有——传了会 `Unknown arguments: output-format` 直接失败。别照抄成 `status --output-format json`。

### ⚠️ 已实测**证否**的判据(照抄会得到自信的错误答案)

**「窗口外框尺寸为 0(`window.outerWidth/outerHeight === 0`)即无头」——在新版无头模式下已失效,不要用。**

2026-08-11 实测(chrome-devtools-mcp 1.2.0 / Chrome 149 / 无图形界面的远程机器 / daemon 以 `--headless` 启动):

| 读到的值 | 结论 |
| :- | :- |
| `userAgent` = `…HeadlessChrome/149.0.0.0…` | ✅ 无头判定成立 |
| `webdriver` = `true` | 只说明被自动化驱动 |
| `outerWidth/outerHeight` = `1905 / 2140`(inner `1905 / 2053`) | ❌ **非 0,且与视口有正常帧差**——外框尺寸完全不能区分无头/有头 |

故 Web 端 `renderMode` 判定 = **运行配置(CLI `status` 的 `args`)优先 → 否则 UA 是否含 `HeadlessChrome` → 两者都拿不到写 `null` + `未取到(原因)`**;`webdriver` 与窗口尺寸**不参与**渲染模式判定。

### 其它 Web 端注意

- **MCP 变体拿不到运行配置**:插件自带 / 自注册远程等 MCP 变体的工具集里**没有** status/config 类工具(只有页面级工具),故 MCP 路径**只能靠 UA 取证**,`renderModeSource` 相应写「运行取证(…)」而非「运行配置」。
- **★复用 daemon 时命令传参不生效**:`--headless` 是 **daemon 启动期**参数(仅 `chrome-devtools start` 可改,默认 `true`)。daemon 已在运行时,后续每次工具调用都继承**它启动那一刻**的配置——所以此分支下渲染模式**必须运行探测**,`renderModeSource` 不得写「显式指定」(硬门 `check_env_facts.py` 会拦)。这不是理论风险:实测本机 daemon 起于数日前、且已挂着若干非本任务标签页。
- **UA 模拟会污染取证**:若用例或前置步骤做过 UA 模拟(`emulate --userAgent`),`navigator.userAgent` 读到的是被覆盖值。故取证须在**任何 UA 模拟之前**做(环境准备阶段本就在首条用例前),或以 CLI `status` 的运行配置为准。
- **取证失败不卡住**:MCP 变体首次拉起浏览器可能超时(实测出现过 `Target.setDiscoverTargets timed out`)。此时按第十节 10.4 降级——字段写 `null` + `未取到(原因)`、`env-facts.json` 照常落盘,**不重试到死、不挂起**。

---
