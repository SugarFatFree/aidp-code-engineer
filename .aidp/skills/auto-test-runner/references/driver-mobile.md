# 移动 APP 驱动适配

> 端专有适配层文件。端无关的四原子能力契约、能力探测与优雅降级、扩展新端 SOP 见 `driver-adapters.md`。**本文件含端专有 API，属适配层——方法论层（`../SKILL.md` / `execution-methodology.md`）不得出现这些调用。**

---

### 移动 APP(Android / iOS) · 成熟度:部分(Appium 伪代码,未端到端验证)

- **驱动**:**Appium**(统一入口)+ **UIAutomator2**(Android)/ **XCUITest**(iOS)。
- **四能力映射**:
  - `locate` → `driver.find_element(By.id / By.xpath / -android uiautomator / -ios predicate)`,优先 accessibility id / 可见文本。
  - `act` → element.click(tap)/ send_keys(input)/ swipe / press back / push_file+选择(upload)/ alert accept。
  - `observe` → `driver.page_source`(控件树)/ current_activity / 当前 context(NATIVE_APP↔WEBVIEW)。
  - `capture` → `driver.get_screenshot_as_file()`(截图)+ page_source(控件树)。
- **observe 的运行环境通道(env,见 `driver-adapters.md` 第一节)**:
  - `runConfig` → `driver.capabilities`(实际生效的 desired capabilities,含 platformVersion / deviceName / app —— **权威信源**,优先于任何推断)。
  - `renderSignals` → **本端不适用**:移动 APP 无"无头/有头"之分;`renderMode` 写 `null` + `未取到(本端无渲染模式概念)`。**真机与模拟器的区别**属另一事实字段(可按端扩展 `deviceType`),别塞进 `renderMode`。
  - `automationSignals` → session 已建立即为真。
  - `viewportSize` → `driver.get_window_size()`(逻辑像素);另可按端扩展 `deviceModel`/`osVersion`,同样各配 `Source`。
  - `instanceOwnership` → 本次 session 由本任务新建则 `reusedInstance=false`;attach 到已有 session 为 `true`。
  - **成熟度提示**:本端整体「部分(伪代码,未端到端验证)」,上述映射**未经实测复核**,首次落地时须按 `execution-methodology.md` 第十节 10.3 的告诫逐条验证后再采信。
- **`driverAlive`(健康探活)**:`driver.session_id` / 取 session 状态能正常返回即 `true`(Appium server 挂掉或 session 失效时抛错→`false`)。**未经实测复核**,首次落地须验证。
- **`resetSession`(换账号/清会话,动作词落地)**:Android 走 `adb shell pm clear <包名>` 清应用数据后重启 App,或起新的 Appium session 并带 `noReset=false`;iOS 走重装/重置模拟器 App 数据。**成熟度提示**:本端「部分(Appium 伪代码,未端到端验证)」,本项同样未经实测复核。
- **前置**:Appium server 运行 + 真机/模拟器 + app 包(apk/ipa)+ desired capabilities。

---

### 移动适配器样例(Appium 风格)

```python
class MobileAdapter:
    def __init__(self, driver):        # driver = Appium WebDriver(UIAutomator2/XCUITest)
        self.driver = driver

    def locate(self, sem):             # 优先 accessibility id / 可见文本
        try:
            return self.driver.find_element("accessibility id", sem)
        except NoSuchElementException:
            xpath = f"//*[@text='{sem}' or @label='{sem}' or @content-desc='{sem}']"
            els = self.driver.find_elements("xpath", xpath)
            return els[0] if els else None

    def act(self, handle, action, data=None):
        return {
            "tap":    lambda: handle.click(),
            "input":  lambda: handle.send_keys(data),
            "swipe":  lambda: self.driver.swipe(*data),      # data=(x1,y1,x2,y2)
            "back":   lambda: self.driver.back(),
            "upload": lambda: self.driver.push_file(data["remote"], data["local"]),
        }[action]()

    def observe(self):
        return {"activity": self.driver.current_activity,
                "context": self.driver.current_context,      # NATIVE_APP↔WEBVIEW
                "source": self.driver.page_source[:2000]}     # 控件树

    def capture(self, tag):
        path = f"evidence/{tag}.png"
        self.driver.get_screenshot_as_file(path)
        return path                    # 移动端另可附 page_source 控件树
```

> **注意**:`locate` 内部即便用到 xpath,那是**适配层内部实现细节**,对方法论层透明——方法论层只传"语义文案 sem",不感知 xpath。这正是两层解耦的意义。

---

---

## WebMCP `invoke`（Web 适配器可选补充能力）：**本端不适用**

原生控件树，无浏览器 WebMCP 能力入口（APP 内 WebView 若需，按 Web 适配器另行评估）。

> 本行是**显式声明**、不是留空——按本 skill 既有惯例（如 `observe` 运行环境通道），
> **留空视为漏写、不视为不适用**。契约见 [`driver-web-webmcp.md`](./driver-web-webmcp.md)。
