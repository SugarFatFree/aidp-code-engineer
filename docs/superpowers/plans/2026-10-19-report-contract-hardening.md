# 报告契约加固 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把上游报告模板修复中适用于本仓库的 19 条契约问题落到 `emit-report.py`、离线报告渲染器、版本测试报告和示例数据，消除 fail-open、`na` 丢失、待实测误报已测、步骤分母错误及新增页面无人冒烟覆盖。

**Architecture:** 继续保持 `.aidp/` 为契约真源，`skills/aidp-code-engineer/assets/` 由 `mirror_to_bundle.py` 派生。数据契约仍由 `emit-report.py::validate_payload` 负责硬校验，前端 `assets/app.js` 负责归一化和可视化兜底，`report_render_smoke.js` 自动枚举每个报告 HTML 页面及其渲染容器。版本级报告只消费最终 build，但必须保留 `na` 的计数与分母语义。

**Tech Stack:** Python 3 标准库、Node.js、离线 HTML/CSS/原生 JavaScript、现有 `.aidp/scripts/tests` 回归套件。

---

### Task 1: 先锁定报告契约失败形态

**Files:**
- Modify: `.aidp/scripts/tests/test_report_schema.py`
- Modify: `.aidp/scripts/tests/test_report_render.js`
- Test: `.aidp/scripts/tests/test_report_schema.py`, `.aidp/scripts/tests/test_report_render.js`

- [ ] **Step 1: 写 schema 的失败夹具测试**

在现有 `validate_payload` 测试类中增加以下三类输入，并断言结果包含明确错误：

```python
# 计数子键缺失不能静默跳过 suites/summary 对账
payload["summary"] = {"total": 3, "pass": 3, "fail": 0, "block": 0, "passRate": 1.0}
errors = emit_report.validate_payload("test", payload)
assert any("summary 缺必填计数子键 `skip`" in e for e in errors)

# exec 的 statusKind 只能是 done / pend / fail
payload["overview"]["statusKind"] = "success"
errors = emit_report.validate_payload("exec", payload)
assert any("overview.statusKind" in e for e in errors)

# test 的 na 必须有理由且进入分母扣减
payload["summary"] = {"total": 2, "pass": 1, "fail": 0, "block": 0, "skip": 0, "na": 1, "passRate": 1.0}
payload["cases"] = [{"id": "T-1", "result": "pass", "note": ""}, {"id": "T-2", "result": "na", "note": ""}]
errors = emit_report.validate_payload("test", payload)
assert any("result=na 但 note 为空" in e for e in errors)
```

同时增加 `pendingBrowserTest=True`、`stepDist` 含 `plan` 状态的 exec 夹具，断言 schema 接受它而不是把骨架态当作已执行 0 条。

- [ ] **Step 2: 写渲染端失败夹具测试**

在 `test_report_render.js` 的最小 DOM 夹具中加入：

```javascript
const data = {
  build: "V0.1.0_build1001", buildNo: 1001,
  summary: { total: 3, pass: 1, fail: 0, block: 0, skip: 0, na: 2, passRate: 1 },
  cases: [{ id: "T-1", title: "不适用一", result: "na", note: "本版无此功能", screenshot: "" },
          { id: "T-2", title: "不适用二", result: "na", note: "本端不支持", screenshot: "" },
          { id: "T-3", title: "已通过", result: "pass", note: "", screenshot: "" }],
  suites: [], defects: [], runtimeErrors: []
};
// 断言图例、KPI 和用例列表出现「不适用」，且通过率仍为 100%，不是把 na 当 skip。
```

增加一个执行报告夹具：`overview.statusKind="fail"`、`testSummary.pendingBrowserTest=true`、`steps` 含 `actualStatus="plan"`，断言页面显示待实测/失败语义，不显示「已完成 100%」。

- [ ] **Step 3: 运行新增测试确认当前实现失败**

运行：

```bash
python3 .aidp/scripts/tests/test_report_schema.py
node .aidp/scripts/tests/test_report_render.js
```

预期：至少出现计数缺键未报、`statusKind` 未校验、`na` 未完整展示或计划态被当作已测的失败。

- [ ] **Step 4: 提交测试基线**

```bash
git add .aidp/scripts/tests/test_report_schema.py .aidp/scripts/tests/test_report_render.js
git commit -m "test(report): lock fail-open and pending-state cases"
```

### Task 2: 加固 `emit-report.py` 数据契约

**Files:**
- Modify: `.aidp/scripts/emit-report.py`
- Test: `.aidp/scripts/tests/test_report_schema.py`

- [ ] **Step 1: 增加 test 报告计数子键硬校验**

在 `validate_payload("test", ...)` 的 summary 校验中先逐项检查 `total/pass/fail/block/skip/na/passRate`：

```python
for key in ("total", "pass", "fail", "block", "skip", "na"):
    value = summary.get(key)
    if value is None and key != "na":
        errors.append(f"summary 缺必填计数子键 `{key}`")
    elif value is not None and (not isinstance(value, int) or isinstance(value, bool)):
        errors.append(f"summary.{key} 必须是整数")
if summary.get("passRate") is None:
    errors.append("summary 缺必填子键 `passRate`")
```

`na` 保持存量兼容可缺省为 0；其它计数缺失必须报错。只有计数全部有效时才运行总账、cases、suites 对账。

- [ ] **Step 2: 增加 suites 子键硬校验**

对每个 suite 检查 `total/pass/fail/block/skip`，`na` 缺省为 0；发现缺失或非整数时追加明确错误并禁止执行聚合对账，避免旧的 `ok=False; break` 静默关闭门。

- [ ] **Step 3: 增加 exec overview 取值域校验**

加入：

```python
status_kind = overview.get("statusKind")
if status_kind not in ("done", "pend", "fail"):
    errors.append("overview.statusKind 应 ∈ done|pend|fail")
risk_level = overview.get("riskLevel")
if risk_level is not None and risk_level not in ("低", "中", "高"):
    errors.append("overview.riskLevel 应 ∈ 低|中|高")
```

`statusKind` 缺失也报错，避免前端把失败 build 静默渲染成完成。

- [ ] **Step 4: 保持报告生成与 schema warning 的边界**

不把 `stray_markdown` 或截图缺失等 advisory 误降成 schema 通过；硬错误仍阻断写盘，`schema_advisories` 只在已有调用方约定为非阻断时输出 stderr 和 JSON 字段。确认 `--allow-schema-warn` 不会放过路径越界、截图不存在或结构硬错误。

- [ ] **Step 5: 运行 schema 测试确认通过**

运行：

```bash
python3 .aidp/scripts/tests/test_report_schema.py
```

预期：新增缺键、非法 `statusKind`、无理由 `na` 测试全部通过，原有测试无回归。

- [ ] **Step 6: 提交数据契约修复**

```bash
git add .aidp/scripts/emit-report.py .aidp/scripts/tests/test_report_schema.py
git commit -m "fix(report): fail closed on missing summary and overview fields"
```

### Task 3: 修复 AI 测试报告渲染的 `na` 与报告结论

**Files:**
- Modify: `.aidp/templates/reports/AI测试报告/assets/app.js`
- Modify: `.aidp/templates/reports/AI测试报告/data/示例_build1001.js`
- Modify: `.aidp/templates/reports/AI测试报告/data/示例_build1002.js`
- Modify: `.aidp/templates/reports/AI测试报告/README.md`
- Test: `.aidp/scripts/tests/test_report_render.js`

- [ ] **Step 1: 让所有分布聚合包含 `na`**

统一使用：

```javascript
var dist = {
  pass: Number(s.pass || 0), fail: Number(s.fail || 0),
  block: Number(s.block || 0), skip: Number(s.skip || 0),
  na: Number(s.na || 0)
};
```

环图、套件柱状图、图例、KPI 与 cases 列表都读取同一份 `dist`，禁止单独把图例的 `na` 固定为 0。

- [ ] **Step 2: 修正通过率分母与展示文字**

通过率使用 `eligible = total - na`，当 `eligible <= 0` 显示「未取到」或 `—`；`passRate=1` 显示 `100%`，不再出现 `10000%`。KPI 明确显示「不适用」数量。

- [ ] **Step 3: 修复 cases 归一化与 na 文案**

保留旧字段兼容，但规范字段优先；`result="na"` 显示「不适用」，并渲染 `note` 的理由。不得把 `na` 归为 `skip` 或 `pass`。

- [ ] **Step 4: 修复示例数据契约**

两个示例 build 都显式补 `summary.na`，至少一个示例包含 `cases[].result="na"` 及非空理由，且 suites 计数与 summary 自洽。示例仍只作模板数据，不得成为生成端默认值。

- [ ] **Step 5: 运行渲染与冒烟测试**

运行：

```bash
node .aidp/scripts/tests/test_report_render.js
node .aidp/scripts/report_render_smoke.js .aidp/templates/reports/AI测试报告 V0.1.0_build1001
```

预期：无异常、无 `undefined`/`NaN`、无 ≥1000% 百分比，并能检测到「不适用」分布。

- [ ] **Step 6: 提交 AI 测试报告修复**

```bash
git add .aidp/templates/reports/AI测试报告 .aidp/scripts/tests/test_report_render.js
git commit -m "fix(report): render na distribution and denominator correctly"
```

### Task 4: 修复 AI 执行报告的待实测与步骤分母

**Files:**
- Modify: `.aidp/templates/reports/AI执行报告/assets/app.js`
- Modify: `.aidp/templates/reports/AI执行报告/data/示例_build1001.js`
- Modify: `.aidp/templates/reports/AI执行报告/data/示例_build1002.js`
- Modify: `.aidp/templates/reports/AI执行报告/plan.html`
- Modify: `.aidp/templates/reports/AI执行报告/README.md`
- Test: `.aidp/scripts/tests/test_report_render.js`

- [ ] **Step 1: 修复 `stepDist` 分母**

步骤统计必须把 `plan`/`pend` 留在总步骤数中：

```javascript
var planned = steps.filter(function (s) { return s.actualStatus === "plan" || s.actualStatus === "pend"; }).length;
var finished = steps.filter(function (s) { return ["done", "fail", "skip"].indexOf(s.actualStatus) >= 0; }).length;
var total = steps.length;
```

页面显示「已完成 / 总步骤」，不能在计划态把分母裁成已执行数量后显示 100%。

- [ ] **Step 2: 让 `pendingBrowserTest` 控制骨架态**

`testSummary.pendingBrowserTest === true` 或 `testSummary.total === null` 时渲染「待实测」，不得渲染「0 条用例已完成」。当数据含真实 summary 时再渲染 pass/fail/block/skip/na 分布。

- [ ] **Step 3: 修复 overview/statusKind 与风险数组消费**

执行报告读取 `overview.statusKind` 的 `done|pend|fail` 值；风险保持数组 `{id, level, title, what, risk, advice}`，不得按 `{high,medium,low}` 分组对象读取。todos 按对象渲染标题与详情。

- [ ] **Step 4: 为 `plan.html/plan.js` 增加独立渲染断言**

确认计划页有自己的 `view-*` 容器、使用同一 build data、能在 file:// 沙箱内渲染。若现有 plan 页面缺少独立脚本，补最小 `assets/plan.js` 并让页面脚本引用它；不把计划页渲染逻辑复制到结果页。

- [ ] **Step 5: 运行执行报告冒烟**

运行：

```bash
node .aidp/scripts/report_render_smoke.js .aidp/templates/reports/AI执行报告 V0.1.0_build1001
node .aidp/scripts/report_render_smoke.js .aidp/templates/reports/AI执行报告 V0.1.0_build1001 plan.js '#view-plan'
node .aidp/scripts/tests/test_report_render.js
```

预期：默认模式自动覆盖 `index.html` 与 `plan.html`，每页都有 `pages[]` 明细，计划页不白屏。

- [ ] **Step 6: 提交 AI 执行报告修复**

```bash
git add .aidp/templates/reports/AI执行报告 .aidp/scripts/report_render_smoke.js .aidp/scripts/tests/test_report_render.js
git commit -m "fix(report): preserve pending execution and planned step totals"
```

### Task 5: 修复版本级测试报告 `na` 聚合

**Files:**
- Modify: `.aidp/templates/reports/版本测试报告/{version}-测试报告.html`
- Modify: `.aidp/templates/reports/版本测试报告/README.md`
- Modify: `.aidp/templates/reports/README.md`
- Test: `.aidp/scripts/tests/test_report_render.js`

- [ ] **Step 1: 修复最终 build 聚合**

最终 build 的 `summary` 聚合必须保留 `na`，套件与用例分布也保留 `na`；版本报告的通过率分母固定为 `total - na`，全量 `na` 时显示未取到而不是除零或 100%。

- [ ] **Step 2: 修复 KPI、环图、套件表和用例结论**

版本报告的 KPI 显示总用例、通过、失败、阻塞、忽略、不适用六类数值；图例和表格使用同一 `resultDist`；缺陷表不得引入 build 列或截图列，维持版本级报告定位。

- [ ] **Step 3: 增加版本级报告夹具**

在现有渲染测试中加载模板内联数据，覆盖 `na=2`、`total=3`、`pass=1` 的最终 build，断言页面出现「不适用 2」且通过率为 100%。

- [ ] **Step 4: 运行验证并提交**

```bash
node .aidp/scripts/tests/test_report_render.js
python3 .aidp/scripts/tests/test_report_schema.py

git add .aidp/templates/reports/版本测试报告 .aidp/templates/reports/README.md .aidp/scripts/tests/test_report_render.js
git commit -m "fix(report): keep na in version-level aggregation"
```

### Task 6: 自动枚举所有报告页并完成模板同步

**Files:**
- Modify: `.aidp/scripts/report_render_smoke.js`
- Modify: `.aidp/scripts/tests/test_report_render.js`
- Modify: `.aidp/scripts/tests/README.md`（如测试说明需要更新）
- Generated: `skills/aidp-code-engineer/assets/` via `mirror_to_bundle.py`

- [ ] **Step 1: 替换固定 `assets/app.js + #view-build` 冒烟面**

`report_render_smoke.js` 默认扫描 `reportDir` 下每个 HTML，提取其中 `assets/*.js` 和 `id="view-*"`，每页在独立沙箱里加载 data script 与渲染脚本，输出：

```json
{"ok":true,"pages":[{"html":"index.html","script":"assets/app.js","view":"view-build","ok":true,"reasons":[]}],"len":1234,"undefinedCount":0,"nanCount":0,"bigPct":[]}
```

传入可选 `renderScript` 与 `containerSelector` 时保持旧调用兼容，用于单页定向测试。

- [ ] **Step 2: 增加新增页面回归夹具**

测试中复制一个 `plan.html` 到临时报告目录，故意让其脚本抛异常，断言默认冒烟失败且 `pages[]` 点名该 HTML；恢复脚本后断言整体通过。这证明新增页面不会逃出覆盖面。

- [ ] **Step 3: 运行完整报告相关检查**

```bash
python3 .aidp/scripts/tests/test_report_schema.py
node .aidp/scripts/tests/test_report_render.js
node .aidp/scripts/report_render_smoke.js .aidp/templates/reports/AI执行报告 V0.1.0_build1001
node .aidp/scripts/report_render_smoke.js .aidp/templates/reports/AI测试报告 V0.1.0_build1001
python3 .aidp/scripts/check_code_symbol_refs.py
python3 .aidp/scripts/check_cli_invocation.py
```

- [ ] **Step 4: 镜像、模板自检、轻量门**

```bash
python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py
python3 skills/aidp-code-engineer/scripts/verify.py . --template --read-only
python3 .aidp/scripts/check_convention30_prose.py
python3 .aidp/scripts/check_private_markers.py
python3 .aidp/scripts/check_runtime_paths.py --root .
```

预期：verify 无 ERROR；允许既有分片接近 20KB 的 WARN；报告相关脚本与模板 bundle 零漂移。

- [ ] **Step 5: 提交并推送本组完成结果**

```bash
git add .aidp skills/aidp-code-engineer/assets
 git commit -m "fix(report): harden report contracts and smoke every page"
git push
```

版本号保持现有值，不执行版本号变更。
