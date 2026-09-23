# 小程序驱动适配

> 端专有适配层文件。端无关的四原子能力契约、能力探测与优雅降级、扩展新端 SOP 见 `driver-adapters.md`。**本文件含端专有 API，属适配层——方法论层（`../SKILL.md` / `execution-methodology.md`）不得出现这些调用。**

---

### 微信 / 各厂小程序 · 成熟度:预留未验证

- **驱动**:**miniprogram-automator**(微信官方)等;各厂(支付宝/抖音)对应自动化 SDK。
- **四能力映射**:
  - `locate` → `page.$(selector)` / `page.$$` 按类名/文本。
  - `act` → element.tap / input / picker 选择 / scrollTo / navigateBack。
  - `observe` → `page.data()` / `page.wxml()` / 当前路由。
  - `capture` → `miniProgram.screenshot()`(截图)。
- **observe 的运行环境通道(env,见 `driver-adapters.md` 第一节)**:
  - `runConfig` → `miniProgram.appid` / 启动时的 `projectPath` + 编译模式(权威,由 launch 配置直给)。
  - `renderSignals` → **本端不适用**:小程序由开发者工具承载,无"无头/有头"之分;`renderMode` 写 `null` + `未取到(本端无渲染模式概念)`。
  - `automationSignals` → 自动化端口已连接即为真(连不上根本无法执行)。
  - `viewportSize` → `miniProgram.systemInfo()` 的 `windowWidth/windowHeight`(模拟机型)。
  - `instanceOwnership` → 开发者工具实例为本次启动所有,`reusedInstance=false`;若连的是已开着的工具实例则为 `true`。
  - **成熟度提示**:本端整体「预留未验证」,上述映射同样**未经实测复核**,首次落地时须按 `execution-methodology.md` 第十节 10.3 的告诫逐条验证后再采信。
- **`driverAlive`(健康探活)**:自动化端口连接存活即 `true`(如 `miniProgram.pageStack()` 能返回);开发者工具进程退出时判 `false`。**未经实测复核**,首次落地须验证。
- **`resetSession`(换账号/清会话,动作词落地)**:调 `miniProgram.close()` 后重新 `automator.launch()` 起新的小程序上下文(清 storage 与登录态);或 `miniProgram.callWxMethod('clearStorage')` 后重启页面栈。**成熟度提示**:本端整体「预留未验证」,本项未经实测复核。
- **前置**:需开发者工具开启自动化端口 + 项目以测试模式启动。

---

## WebMCP `invoke`（Web 适配器可选补充能力）：**本端不适用**

小程序运行在各厂自有渲染层，无浏览器 WebMCP 能力入口。

> 本行是**显式声明**、不是留空——按本 skill 既有惯例（如 `observe` 运行环境通道），
> **留空视为漏写、不视为不适用**。契约见 [`driver-web-webmcp.md`](./driver-web-webmcp.md)。
