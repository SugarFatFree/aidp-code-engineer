# 应用自有 MCP 业务工具适配（端无关契约）

本文件只在调用方 `client_mcp.enabled: true` 或旧 Web `webmcp_enabled: true` 或 `webmcp.enabled: true` 时加载;两旧别名冲突也须报错。**应用业务能力**与**测试驱动**独立:Chrome DevTools/Appium/小程序驱动经 MCP 接入,只证明 AI 能操控客户端,不证明被测应用主动提供业务工具。默认关闭时不探测技术栈、不生成 MCP 专项结果或报告行。新旧 Web 声明冲突要报错,不静默覆盖。⚠️ **本 SKILL 的「报错」= 该轮相关用例标 `block(precondition-unmet)` + 证据、其余用例照跑,⛔ 不终止本轮、不挂起等人**——本 SKILL 的硬前提是 7×24 无人值守,不写明会被读成「终止整轮」。

应用工具通道仅是四个 UI 原子能力之外的**可选补充**,不是第五个 UI 原子能力,也不改变 `locate/act/observe/capture`。它只能按已证实的客户端实现形态列出**当前应用实例**注册工具并调用该应用工具;没有跨 Web/小程序/App/桌面的统一入口、统一端点或 Chrome 启动命令。Web 用现有 `driver-web-webmcp.md` 页面注册机制;非 Web 仅在应用自有 MCP 服务或桥接的连接方式、身份来源与实例绑定均有证据时,在该端驱动文件登记真实适配;否则写“不支持/未提供”。

## 四态运行事实(每态独立取证)

| 事实 | 来源 | 未取到时 |
| :- | :- | :- |
| 项目显式声明 `declared` | 调用方输入/应用配置,含客户端类型和实现形态 | 不推断启用;无声明即关闭 |
| 应用入口 `entry` 实连 | 应用自有服务/桥接或 Web 页面入口实测返回 | 写 `unavailable` + 原因,专项用例 block |
| 当前实例 `registration` | 本页/本 App 实例真实注册工具清单(须与设计逐名对账) | 写 `unavailable`;不能拿浏览器全量工具或驱动 tools 替代 |
| 本用例 `invocation` | 实际工具名 + 返回摘要 + 本轮 `evidence[].artifact` 真实日志/JSON | 写 `not-called`/`unavailable`;不得因入口可连就报调用通过 |

每态含 `source` 与 `observed_at`,工具证据由 `scripts/check_result.py` 单一校验;`driver` 只记 UI 测试驱动,`mechanism=app-mcp` 才表示应用业务工具调用且仍须 artifact。普通业务动作可如实走 DOM/CDP/Appium;专项用例缺入口或工具 → `block(precondition-unmet)` + 证据,其余 UI 用例继续。Web 路径 A 的驱动本页清单与路径 B 页内 JS 的浏览器全量清单作用域不同,后者不证明当前应用实例注册。

| 合成场景 | 合规 | 不合规 |
| :- | :- | :- |
| Web 已实现 | Web 声明、页面注册、真实调用均有独立证据 | `driver=cli` 就声称 WebMCP 工具通过 |
| 非 Web 已实现 | App 自有服务/桥接实连且注册/调用留痕,Appium 仅操控 UI | 用 Appium MCP 的 tools 当产品 tools |
| 非 Web 未实现 | 明写“不支持/未提供”,普通 UI 继续 | 自造桥接地址或照搬 secure context |
| 只有测试驱动可用 | `driver=mcp-remote` 但应用声明关闭,只报 UI 结果 | 从驱动 MCP 推出应用能力开启 |
