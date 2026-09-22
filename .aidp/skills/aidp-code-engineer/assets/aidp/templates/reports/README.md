# 报告模板库（docs/reports 用）

> 本目录是 AIDP 范式「版本报告」体系的模板骨架。下游项目运行 `/sprint-autopilot` / `/sprint-aiauto-test` / `/version` 时，按本目录模板在 `docs/reports/{version}/` 下生成实际报告。**本目录只放空白骨架，不放具体版本的报告内容。**

## 报告体系总览

```
docs/reports/{version}/
├── AI执行报告/                      （执行结果 + 执行计划合并为同套离线页面，同目录拍平、共享 data/ 与 style.css）
│   ├── README.md
│   ├── index.html                   ← 执行结果 SPA 主入口（综合首页 + 各 build 子页 + URL 参数直达）
│   ├── plan.html                    ← 执行计划页（结果页各 build 头部「→ 查看本 build 执行计划」链接跳转打开）
│   ├── assets/                      （app.js 结果渲染 + plan.js 计划渲染 + style.css 暗/亮双主题，零 CDN）
│   └── data/{version}_build{N}.js   ← 每 build 一份数据，index.html 与 plan.html 共用（Phase 3.1.5 写计划态 → 3.4 finalize 结果态）
├── AI测试报告/                    （离线静态 SPA，多 build 共享同一入口）
│   ├── README.md
│   ├── index.html                 ← 综合首页 + 切换各 build 子页 + 图表
│   ├── assets/                    （内联样式 + SVG 图表渲染，零 CDN）
│   ├── data/{version}_build{N}.js  ← 每 build 一份测试数据（aiauto-test 写）
│   └── screenshots/
├── AI数据清理/                    （每 build 一份数据清理文档，Markdown；仅 autopilot 驱动测试才产）
│   └── {version}_build{N}_数据清理.md  ← 测试环境 + 要清理的库 + 清理 SQL（模板 AI数据清理.md 填充；测试后询问是否执行、无人值守只生成不删）
└── 版本测试报告/                  （发布时单文件）
    ├── README.md
    └── {version}-测试报告.html    ← /version 发布时取最终验收 build 生成，完全自包含单文件
```

> **AI数据清理 结构说明**：模板 `{{AIDP_HOME}}/templates/reports/AI数据清理.md` 是**扁平单文件模板**；产出时**每 build 填充为一份** `docs/reports/{version}/AI数据清理/{version}_build{N}_数据清理.md`（子目录），与「AI测试报告 data 每 build 一份」同粒度。

## Build 号机制（单一信源）

- `/sprint-autopilot` 进入 Phase 3、规划完成（或复用）拿到 Sprint 清单后，**铸造** `{version}_build{N}`：N 从 **1001** 起，每次 Phase 3 执行 +1；计数器存 `memory/.sprint-autopilot-baseline.json` 该版本字典 `build_seq`（存"上次已用号"，初值缺省按 1000；下次 build 号 = build_seq+1，故首个 = 1001），当前 build 写 `current_build` 供 `/sprint-aiauto-test` 经 baseline 读取归属。
- **不打 git 分支 / tag**。

## 各文件谁生成

| 产物 | 生成者 | 时机 |
|------|-------|------|
| `AI执行报告/`（index.html 结果主入口 + plan.html 计划 + data/{build}.js，离线 HTML，合并拍平）| `/sprint-autopilot` | Phase 3.1.5 写计划态数据 → Phase 3.4 finalize 结果态 |
| `AI测试报告/`（data + index 刷新）| `/sprint-aiauto-test` | 每轮测试收敛后 |
| `AI数据清理/{version}_build{N}_数据清理.md`（每 build 一份，Markdown）| `/sprint-aiauto-test`（**仅 autopilot 驱动才产**）| 测试后生成（best-effort 非阻塞）；测试后询问是否执行清理、无人值守只生成不删 |
| `版本测试报告/{version}-测试报告.html` | `/version` | 正式发布（情况 B-3）时取最终验收 build |

> 离线铁律：所有 HTML 报告**零 CDN / 零网络依赖**，`file://` 双击即可打开；数据用 `<script src>` 注入（不用 `fetch`），图表手写内联 SVG。

## ★ 报告产出 = 确定性脚本 `{{AIDP_HOME}}/scripts/emit-report.py`（不手搓，防退化成 markdown）

命令**不手写 `data/{build}.js`、不手工 sed 注册 `<script>`、不手工拷贝/打包**——一律经 `emit-report.py`：执行体只产出「结果 JSON」（它的分析），脚本负责把它**确定性**地组装成 HTML SPA 落到本地 `docs/reports/` 并返回报告路径。

```bash
python3 {{AIDP_HOME}}/scripts/emit-report.py --kind exec|test --version V0.1.0 --build V0.1.0_build1001 \
  --data <结果.json> [--baseline memory/.sprint-autopilot-baseline.json] [--json]
```

脚本自动：① 缺骨架则 `cp` 模板（清示例 data）② 写 `data/{build}.js`（exec→`window.__AIRUNS__` 注册 index+plan 两页 / test→`window.__BUILDS__` 注册 index）③ 反检并拒绝违规 markdown ④ 本地交付（报告只落 `docs/reports/{version}/`，返回仓库内相对路径 + `#/build/{build}` 锚点） ⑤ 回写 baseline `report_deliveries` 供 `autopilot-ceremony-gate.py check` 校验交付 ⑥ 从 baseline 注入**复测关系** `retestOf`/`retestRound` 到 data payload（build 复测自上一 finalized build 时，SPA 渲染「🔁 复测自 buildX · 第N轮」徽标 + 元信息；`fixedDefects[]` 若命令传入则一并展示"修复了哪些"）。

> ⛔ **报告不可变**：build 一经 finalize（baseline `builds[].ai_report_finalized=true`+`ai_report_finalized_at`），`emit-report.py` 对其再写 data 直接 **拒绝 exit 2**（唯一逃生阀 `--force-amend` 修笔误 + 追加 `amendments[]` 留痕）；结论变化一律铸新 build（Phase 3.1.5 强制自增）。`autopilot-ceremony-gate.py --stage final` 另校 data mtime 不晚于 `ai_report_finalized_at`。详见两命令「报告不可变铁律」。

> 收尾钢门 `autopilot-ceremony-gate.py check` 校验：执行报告 SPA + 测试报告 SPA（有浏览器测试时）+ 无违规 markdown + `report_deliveries` 交付台账 + 里程碑通知台账——**任一路径**（含 test-only）都无法用「只落 markdown / 未交付」收尾。

## ★ 数据契约 schema（`emit-report.py validate_payload` 强制校验的单一信源）

> 结果 JSON 的字段名 / 结构 / 单位以本节 + 各 `data/示例_build1001.js` 为准。**执行体是 AI、字段必然会漂**，故由 `emit-report.py` 在写盘前 fail-fast（不符 exit 3）；渲染端 `assets/app.js` 另有兜底（口径归一 + 数组归一 + 缺失显示 `—` + 单章节异常不白屏）。二者双侧断言，注释不是断言。

### 比率类字段单位口径（钉死，任何位置不得违反）

**`passRate` / `featureRate` / `testPassRate` / `coverage` 一律 `0~1` 小数（`1.0` = 100%）**，渲染端统一 `×100` 展示；**任何位置不得出现 `0~100` 口径或字符串**（如 `100.0` 会渲染成 `10000%`、`"6/6"` 会让趋势图画到画布外）。100% 写 `1.0`、96% 写 `0.96`、无数据写 `null`。

### ★ 环境事实类字段（必须执行期【运行取证】填充 —— 取证优先于声称，三条口径）

**环境事实类字段** = `renderMode`（渲染模式）/ `testUrl`（被测 URL）/ 浏览器版本 / viewport / 是否复用已有实例 / 登录角色 等描述"实际怎么跑的"字段。三条硬口径（「未获非空数据→绝不伪造」）：

1. **取证优先于声称**：这些字段**必须来自运行期实测取证，禁止来自模板示例值或启动 flag 推断**。取证由上游 `auto-test-runner` 的「运行环境取证」原子步骤产出结构化环境事实对象（`round-{M}/env-facts.json`），命令端**只消费、不推断**（约定 21）。**具体取证判据的单一信源 = `auto-test-runner` `references/driver-<端>.md` + `execution-methodology.md §10`**（判据随被测端版本漂移、由 SKILL 维护，本 README 与命令端**都不复刻**——例：Web 端渲染模式判定「运行配置 → UA 是否含 `HeadlessChrome` → 取不到写 null」，而 `navigator.webdriver`/窗口外框尺寸对渲染模式「不能用/新版无头已失效」，勿据此臆断）。
2. **取不到就不许编**：实测取不到时该字段写 `null`（渲染为「未取到」）或 `"未取到(原因)"`，**严禁回落成模板示例值 / 启动参数推断值 / "看起来合理"的值**。`app.js` 已把 `renderMode` 展示改为三态（headless→无头 / headed→有头 / 其它→显式「⚠️ 未取到」，**不再把非 headless 兜底成「有头」**）。
3. **补记"为何是这个模式"**：`renderModeSource` 标注来源——`显式指定` / `复用已有实例(含实例来源)` / `无头不可用降级(含降级原因)` / `运行取证(方法)`。无人值守若最终跑成有头，须显式说明原因。
> ⚠️ **示例文件里的 `renderMode:"headless"` 只是示例、不是可穿透的默认**：真实报告该值由执行期取证决定。`emit-report.py` finalize 后有确定性校验，若报告仍含未替换占位符 / 模板裸示例值 → 判不合格并告警、不静默产出（见 `/sprint-aiauto-test` finalize 校验）。

### 字段 schema（必填 / 类型 / 取值域）

**共用顶层**：`build`(str,必) `version`(str,必) `buildNo`(int,必—由 emit-report.py 从 `--build` 派生，勿手填) `startedAt`/`finishedAt`(str)。

**test（AI测试报告）**：

| 字段 | 类型 | 必填 | 取值域 / 说明 |
|------|------|:--:|------|
| `summary` | obj | ✓ | `{total,pass,fail,block,skip,na, passRate:0~1}`；**`passRate` 分母 = `total - na`**（`na` 可缺省=0，存量报告兼容）|
| `cases[]` | list | ✓ | 每项 `{id, title, suite, result, note, screenshot}`；`result ∈ pass\|fail\|block\|skip\|na`。**★ 不是 `name`/`status`/`detail`**；**`na` = 本场景不存在该功能、永远不测**（⛔ 不是 pass、不是 skip），`note` 必须写明不适用理由（空理由 emit-report 报错） |
| `renderMode` | str\|null | | 环境事实字段：`headless`\|`headed`\|`null`(未取到)。★ **执行期运行取证填充**（见上「环境事实类字段」），**禁止**填示例值 / 按启动 flag 推断；取不到写 `null`（展示「未取到」，不许兜底成有头）|
| `renderModeSource` | str | | `renderMode` 来源标注：`显式指定`\|`复用已有实例(含来源)`\|`无头不可用降级(含原因)`\|`运行取证(方法)`\|`未取到(原因)` |
| `suites[]` `defects[]` `runtimeErrors[]` | list | | 数组，缺省 `[]` |

**exec（AI执行报告）**：

| 字段 | 类型 | 必填 | 取值域 / 说明 |
|------|------|:--:|------|
| `overview` | obj | ✓ | `{statusKind, featureRate:0~1, testPassRate:0~1, coverage:0~1\|null, pendingCount}` |
| `steps[]` `features[]` | list | ✓ | `features[].status ∈ done\|doing\|fail\|pend\|skip` |
| `risks[]` | list | | 每项 `{id, level:"高\|中\|低", title, what, risk, advice}`。**★ 数组，等级在每项 `level`；严禁 `{high,medium,low}` 分组对象**（否则执行报告整页白屏）|
| `todos[]` | list | | 每项 `{title[, detail]}` **对象**，非裸字符串 |
| `defects[]` `incidents[]` | list | | 数组，缺省 `[]` |
| `testSummary` | obj | | `{total,pass,fail,...,passRate:0~1,coverage:0~1\|null}`；骨架期 `pendingBrowserTest:true` |
| `cases[]` | list | | 与 test 的 `cases[]` **同结构**（`{id,title,suite,result,note,screenshot}`）。**收尾门 3n（约定 33 用例基线挂靠）读的就是这里**——⛔ 它必须在 exec 契约里有名有姓，否则就是一处「有读无写」：门报「报告 cases[] 一个 id 都没有」，而执行体翻遍 exec 契约找不到该填哪。**finalize 时不必手填**：`emit-report.py --kind exec` 会从同 build 的 AI测试报告自动继承 `cases[]` 与 `testSummary`（只补缺失，显式传入优先），继承结果记在输出的 `inherited_from_test_report` |

> 逃生阀 `--allow-schema-warn`：把 fail-fast 降级为 WARN 照常写盘（仅临时救火），并在 data 的 `schemaWarnings[]` 留痕。契约示例文件本身必须通过校验器（示例即契约、永不分叉）。
