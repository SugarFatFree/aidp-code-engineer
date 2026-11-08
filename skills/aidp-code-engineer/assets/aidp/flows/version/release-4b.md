# /version · 发布测试报告生成

> 由 `release-4.md` Step 3.3.8 按需 Read；覆盖跳过判定、终态选择、证据转换与失败处置。

<!-- BODY-BELOW -->
### Step 3.3.8：★ 生成版本测试报告（取最终验收 build，单文件 HTML）

**目标**：取本版本 `AI测试报告/data/` 的最新验收候选，确认已终态后保留两路测试证据，渲染成**单文件自包含 HTML** 版本测试报告，作为版本正式发布的对外交付物，落 `docs/reports/{version}/版本测试报告/{version}-测试报告.html`。AI测试报告项目保留作 per-build 历史。

> 📌 数据来源说明：`AI测试报告/data/` 下的 per-build 数据**仅由 autopilot 流水线驱动的 `/sprint-aiauto-test` 生成**（直接调用 aiauto-test 不产报告，见其 Phase 2.5/3.0「报告生成门」）。因此本版本若全程未经 autopilot 跑过测试 → 无 build 数据可合并 → 按下方兜底**自动跳过**版本测试报告生成（不视为失败）。版本测试报告本身是 `/version` 发布期交付物，与「AI测试报告仅 autopilot 驱动生成」不冲突。

**执行时机**：Step 3.3.7（`release-3.md`；SQL 文件整理）之后、Step 3.4.1（`release-7.md`；发布提交）之前。

#### Step 3.3.8.1：跳过条件

```bash
# ★ 解耦铁律（同 release-3.md「本跳过条件仅决定本小节，绝不 exit 整个 Step」）：
#   这里**只置标志位、绝不 `exit`** —— 裸 `exit 0` 会把其后的 3.3.9 references 整理 /
#   3.3.10 收敛 / 3.3.11 全量设计 / 3.4 打 tag **全部掐掉**，
#   而"从未跑过 /sprint-aiauto-test"是很常见的版本形态。
SKIP_338=0
BTR_DATA="docs/reports/{version}/AI测试报告/data"
# 无 build 测试数据 → 跳过本小节（未跑过 /sprint-aiauto-test）
[ ! -d "$BTR_DATA" ] && { echo "SKIP: 无 AI测试报告数据目录，跳过版本测试报告生成"; SKIP_338=1; }
if [ "$SKIP_338" = "0" ]; then
  DATA_COUNT=$(ls "$BTR_DATA"/*.js 2>/dev/null | grep -v '示例_' | wc -l)
  [ "$DATA_COUNT" -eq 0 ] && { echo "SKIP: 无 build 测试数据，跳过版本测试报告生成"; SKIP_338=1; }
fi
# 下方 3.3.8.2 仅在 SKIP_338=0 时执行；无论如何都继续走 3.3.9
```

#### Step 3.3.8.2：生成版本测试报告（单文件 HTML）

> ⛔ **仅当 3.3.8.1 的 `SKIP_338 == 0` 时执行本小节**；`SKIP_338 == 1` 直接跳到 **3.3.9**（不视为失败，也**不得**因此中断发布链）。

**输出路径**：`docs/reports/{version}/版本测试报告/{version}-测试报告.html`

**定位**：这是一份**版本的正式对外测试报告**（交付/存档用），呈现最新验收轮次的联合测试结果，不做 build 趋势对比、不含应用截图；**保留验收 build / commit 供单测身份核验和追溯**。

**生成算法**：套用 `{{AIDP_HOME}}/templates/reports/版本测试报告/{version}-测试报告.html` 模板（完全自包含：CSS+JS+数据+SVG 图表全内联）：

1. 读 `$BTR_DATA/*.js`（排除 `示例_*`），沿用 **`buildNo` 最大的最新验收候选**，新增终态校验：`summary.pendingBrowserTest`、build / 联合摘要 / `browserTests` / `unitTests` / 任一单测 run 出现 `RUNNING` → **拒绝生成最终报告 + WARN**，待该轮结束重试；不能把“最大 buildNo”直接当成已验收，也不能筛选 PASS 或回退旧 PASS 掩盖最新失败。`FAIL` / `UNVERIFIED` / `TIMEOUT` 的非运行中证据可如实生成失败/未核验报告，但不表示通过发布验收。
2. **保留联合证据后内联**：完整保留 `build` / `buildNo` / `version` / `commit`、`summary`（含 `overallStatus` / `unitStatus` / `browserStatus`）、`suites` / `cases` / `defects` / `runtimeErrors`、`unitTests` / `browserTests`，以及已有的 `failureTriage`。只递归去掉 `screenshot` / `screenshots` 字段；不可删除单测的命令、run_id、计数、失败用例和首要错误。历史没有 `unitTests` 就保持缺省，不补造 PASS、不修改历史不可变 per-build 数据或已归档版本报告。仅重新生成当前未归档的派生报告。
3. **填版本元信息**：写 `window.__VERSION_META__ = { version, milestone, releaseDate, deployMode, testUrl }`（从发布上下文取里程碑/发布日期/部署环境），供报告头副标题 + 版本信息表用。内联数据必须 JSON 序列化并转义 `<`、U+2028、U+2029，防止命令或错误含 `</script>` 逃逸脚本；不能直接拼接原始字符串。
4. 模板 JS 渲染版本级视图：版本信息 + **总体结论 / 全量实测 / 全量单测独立证据** + 实测 KPI 和图表 + 套件 / 用例 / 缺陷 + 测试结论。计数未知显示“未提供”，不以实测通过率冒充联合结论；纯后端保留浏览器 `N/A` 理由与真实单测结果。
5. 标题取 `{version} 版本测试报告`；判定必须复核用例、单测 runs 和 build / commit 身份。任一路真实失败 → 未通过；超时、运行中、未核验或摘要与事实冲突 → 不能写“达到发布标准”。`summary` 的联合字符串只作交叉核验，`failureTriage` 也不能覆盖测试成败。历史无联合字段的报告沿用原展示口径。

**确定性转换（生成脚本中使用；输入为已解析的数据对象，禁止执行源 JS）**：

```javascript
function prepareReleaseBuild(builds) {
  if (!Array.isArray(builds) || !builds.length) throw new Error("无验收 build");
  const numbered = builds.map(build => {
    const no = build.buildNo ?? Number(String(build.build || "").match(/_build(\d+)$/)?.[1]);
    if (!Number.isSafeInteger(no) || no < 0) throw new Error("验收 buildNo 缺失或非法");
    return { build, no };
  }).sort((a, b) => a.no - b.no);
  const latest = numbered[numbered.length - 1];
  if (numbered.length > 1 && numbered[numbered.length - 2].no === latest.no) throw new Error("最新 buildNo 重复，需核验来源");
  const source = latest.build, summary = source.summary || {}, unit = source.unitTests || {};
  const statuses = [source.status, summary.overallStatus, summary.unitStatus, summary.browserStatus,
    source.browserTests?.status, unit.status, ...(Array.isArray(unit.runs) ? unit.runs.map(r => r?.status) : [])];
  if (summary.pendingBrowserTest || statuses.some(s => String(s).toUpperCase() === "RUNNING")) {
    throw new Error("最新验收 build 仍为 RUNNING，拒绝生成最终报告；不得回退旧 PASS");
  }
  function withoutScreenshots(value) {
    if (Array.isArray(value)) return value.map(withoutScreenshots);
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value)
      .filter(([key]) => key !== "screenshot" && key !== "screenshots")
      .map(([key, item]) => [key, withoutScreenshots(item)]));
    return value;
  }
  const keys = ["build", "buildNo", "version", "commit", "startedAt", "finishedAt", "deployMode", "testUrl",
    "summary", "suites", "cases", "defects", "runtimeErrors", "unitTests", "browserTests", "failureTriage"];
  return withoutScreenshots(Object.fromEntries(keys.filter(key => Object.prototype.hasOwnProperty.call(source, key))
    .map(key => [key, source[key]])));
}
function releaseBuildScript(builds) {
  const data = JSON.stringify([prepareReleaseBuild(builds)]).replace(/</g, "\\u003c")
    .split(String.fromCharCode(8232)).join("\\u2028").split(String.fromCharCode(8233)).join("\\u2029");
  return "window.__BUILDS__ = " + data + ";";
}
```

> 替换模板中整个示例数据脚本为 `releaseBuildScript(builds)` 的结果，版本元信息使用同样的序列化转义。先完成转换与渲染校验，再写当前未归档输出；转换拒绝时不覆盖已有报告，Step 3.6 明确本次未生成及原因，不把旧文件当作本次成功。

#### Step 3.3.8.3：失败处置（不阻塞发布）

- build 数据解析失败 → **跳过生成 + WARN**（同 3.3.8.1 的 SKIP 处置）；Step 3.6 发布报告加一行提示
- 写盘失败 → WARN；Step 3.6 发布报告加一行 "⚠️ 版本测试报告生成失败，请手工检查 `docs/reports/{version}/AI测试报告/`"
- **唯一阻塞情形**：`版本测试报告/` 目录无写权限 → 中断提示用户

#### Step 3.3.8.4：输出摘要

```
📊 版本测试报告已生成（{version}）：
   docs/reports/{version}/版本测试报告/{version}-测试报告.html（单文件，双击即看）
   共 {DATA_COUNT} 个 build，最新验收 build {build} / commit {commit}
   总体 {overallStatus} / 全量实测 {browserStatus} / 全量单测 {unitStatus}（历史无单测则注明未提供）
   per-build 历史：docs/reports/{version}/AI测试报告/index.html
```
