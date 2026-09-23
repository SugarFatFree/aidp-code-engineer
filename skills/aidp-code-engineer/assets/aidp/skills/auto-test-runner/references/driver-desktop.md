# 桌面客户端驱动适配

> 端专有适配层文件。端无关的四原子能力契约、能力探测与优雅降级、扩展新端 SOP 见 `driver-adapters.md`。**本文件含端专有 API，属适配层——方法论层（`../SKILL.md` / `execution-methodology.md`）不得出现这些调用。**

---

### 桌面客户端 · 成熟度:预留未验证

- **驱动**:**Playwright-Electron**(Electron 应用)/ **WinAppDriver**(Windows 原生,配 Appium)/ 其他。
- **四能力映射**:
  - `locate` → Electron:Playwright locator;WinAppDriver:find_element(AutomationId/Name)。
  - `act` → click / type / select / scroll / back / file dialog。
  - `observe` → Electron:DOM/快照;WinAppDriver:控件树 dump。
  - `capture` → 截图 + 控件树。
- **observe 的运行环境通道(env,见 `driver-adapters.md` 第一节)**:
  - `runConfig` → Electron:启动 `args`/`app.getVersion()`;WinAppDriver:desired capabilities(权威)。
  - `renderSignals` → **桌面客户端一般恒为有头**(GUI 应用需渲染窗口);`renderMode` 写 `headed` + `运行取证(桌面 GUI 应用恒有头)`,**不要照抄 Web 的无头判据**。
  - `automationSignals` → 调试端口/自动化服务已连接即为真。
  - `viewportSize` → 主窗口客户区尺寸(Electron:渲染进程视口;WinAppDriver:窗口 Rect)。
  - `instanceOwnership` → 本次是否由驱动拉起应用(拉起=false;attach 到已运行进程=true)。
  - **成熟度提示**:本端整体「预留未验证」,上述映射**未经实测复核**,首次落地时须按 `execution-methodology.md` 第十节 10.3 的告诫逐条验证后再采信。
- **`driverAlive`(健康探活)**:Electron 看调试端点是否仍可连;WinAppDriver 看服务端点与应用进程是否存活。**未经实测复核**,首次落地须验证。
- **`resetSession`(换账号/清会话,动作词落地)**:Electron 关闭应用后以新的 `userDataDir` 重新拉起;WinAppDriver 结束进程后重启并清应用配置目录。**成熟度提示**:本端整体「预留未验证」,本项未经实测复核。
- **前置**:Electron 开调试端口 / WinAppDriver 服务运行 + 应用可执行路径。

---

---

## WebMCP `invoke`（Web 适配器可选补充能力）：**本端不适用**

桌面客户端控件树，无浏览器 WebMCP 能力入口（Electron 内嵌页若需，按 Web 适配器另行评估）。

> 本行是**显式声明**、不是留空——按本 skill 既有惯例（如 `observe` 运行环境通道），
> **留空视为漏写、不视为不适用**。契约见 [`driver-web-webmcp.md`](./driver-web-webmcp.md)。
