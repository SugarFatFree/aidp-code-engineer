<!-- 二次切分 · phase-3 片2/6：覆盖 3.2.6 生成AI测试报告HTML（该build子页+综合首页刷新）-->
# /sprint-aiauto-test · 执行分片 分片 [2/6]（3.2.6 生成AI测试报告HTML（该build子页+综合首页刷新））

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-3-2.md`。理据见同目录 `rationale.md`。

### 3.2.6 ★ 生成 AI测试报告 HTML（该 build 子页 + 综合首页刷新）

> 测试报告**唯一形态 = HTML**（不产出 markdown）。本步把本轮结果渲染进 `docs/reports/{version}/AI测试报告/` 离线静态项目（图表 + 综合首页 + 各 build 子页）。

> ⛔⛔ **本段（step 2 ~ 5bis）整体受 `SKIP_REPORT` 守卫，且必须是【可执行判据】**：
> `phase-3-1.md` 已立下「3.1 / 3.2.5 / 3.2.6 每步开头必须先判 `SKIP_REPORT`，散文写了跳过不算数」。
> ⛔ 缺这道判据时：`REPORT_ENABLED=0` 下 3.2.5 被跳过、本段照跑 →
> step2 会在 `AI测试报告/` 拷出整套官方 SPA（正是 3.0 存在理由所禁止的散落）→
> step4 的 `BUILD` 取到**空串**、`emit-report.py --build ""` 被 argparse 接受 →
> 落盘一份**没有 build 归属**的官方报告 → 5bis 必 FAIL → 3 tick 冻结；
> 且 `exit 0` 落在 Phase 3.3 之前，**本轮真实测试结论一条都没写进 baseline**。
>
> <!-- bashsyntax-check: ignore 本块是"守卫怎么包"的骨架示意，故意只给 if/else/fi 框架、
>      中间是省略号，单独抽出来必然语法不完整；真正可执行的语句在 step 2~5bis 各自块内 -->
> ```bash
> eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> if [ "${SKIP_REPORT:-0}" = "1" ]; then
>   echo "⏭️ SKIP_REPORT=1（非 autopilot 驱动，本轮不产 AI测试报告）→ 整段跳过 step 2~5bis，直接进 Phase 3.3 写结论"
>   # …… 直接进 Phase 3.3 ……
> else
>   # …… 下面 step 2 ~ 5bis 全部在此分支内 ……
>   :
> fi   # ← SKIP_REPORT 守卫结束（务必包到 5bis 之后、step 6 之前）
> ```

1. **取 build 号**：用 Phase 0.2 步骤 2.5 已读到的 `current_build`（autopilot Phase 3.1.5 铸造）作为 `$BUILD`。
   - 注：本步只在 `REPORT_ENABLED=1`（current_build 存在 = autopilot 驱动）时执行；非 autopilot 驱动已在 3.0 门拦下、不进本步，故此处 `$BUILD` 必为 autopilot 铸造的真实 build 号。
2. **确保静态项目存在 + shell 版本对账**：缺失则从 `.aidp/templates/reports/AI测试报告/` 拷入 `index.html`+`assets/`+空 `data/`+`screenshots/`+README；**已存在则比对 `report-shell-version`**（模板 index.html 顶部 `<!-- report-shell-version: N -->` vs 项目），模板更新（项目 < 模板）则刷新 `index.html`+`assets/`、保留 `data/`+`screenshots/`、并把 `data/` 下历史 build 脚本在 `app.js` 前重注册（消除「模板升级后停在旧样式」；同 `/sprint-autopilot` Phase 3.4 step 2 对账循环）：
   ```bash
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
   D="docs/reports/$TARGET_VERSION/AI测试报告"; T=".aidp/templates/reports/AI测试报告"
   if [ ! -f "$D/index.html" ]; then
     mkdir -p "$D/data" "$D/assets" "$D/screenshots"; cp "$T/index.html" "$D/"; cp -r "$T/assets/." "$D/assets/"; sed -i '/data\/示例_/d' "$D/index.html"
   else
     TV=$(grep -oE 'report-shell-version: *[0-9]+' "$T/index.html"|grep -oE '[0-9]+$'); TV=${TV:-0}
     CV=$(grep -oE 'report-shell-version: *[0-9]+' "$D/index.html"|grep -oE '[0-9]+$'); CV=${CV:-0}
     if [ "$TV" -gt "$CV" ]; then
       cp "$T/index.html" "$D/"; cp -r "$T/assets/." "$D/assets/"; sed -i '/data\/示例_/d' "$D/index.html"
       for f in "$D"/data/*.js; do [ -f "$f" ]||continue; b=$(basename "$f"); grep -q "data/$b" "$D/index.html"||sed -i 's#<script src="assets/app.js"></script>#<script src="data/'"$b"'"></script>\n  <script src="assets/app.js"></script>#' "$D/index.html"; done
       echo "🔄 AI测试报告 shell v$CV→v$TV 已刷新（data/+screenshots/ 保留，历史 build 重注册）"
     fi
   fi
   ```
3. **截图已在 AI测试报告/screenshots/{BUILD}/**（Phase 2 直接落此，3.2.5 已核验）；data 里截图引用用相对 `index.html` 的相对路径 `screenshots/{BUILD}/xxx.png`。
3bis. **★ 环境事实字段一律【消费 SKILL 的运行取证对象】，命令端不自行探测、不复刻判定判据（约定 21 + SKILL 单一信源）**：`auto-test-runner`「运行环境取证」原子步骤**每轮产出 `round-{M}/env-facts.json`**（形状见其 `assets/env-facts-schema.json`），是环境事实字段的**唯一数据源**。命令端组装下面结果 JSON 时**直接消费它**——`renderMode`/`renderModeSource`/`testUrl`/`loginRole` 等取自 env-facts.json 对应字段：
   - **⛔ 绝不用 Phase 0.1.2 的 `RENDER_MODE`**（那是测试方案解析的意图/启动决策值、非运行事实，正是"报告恒显有头"的根因）、**⛔ 绝不用模板示例值**。
   - **⛔ 命令端不自行探测、不复刻端专有取证判据**：`navigator.*` / 窗口尺寸等信号的取舍**随被测端版本漂移、其单一信源是 SKILL `references/driver-<端>.md` + `execution-methodology.md §10`**（例：Web 端 `navigator.webdriver` 与窗口外框尺寸对渲染模式判定「不能用/新版无头已失效」，SKILL 只认「运行配置 → UA 含 `HeadlessChrome` → 取不到写 null」）——命令端复刻必判错，**故本处不写任何具体取证配方，只消费结果**。
   - **SKILL 未产出 env-facts.json 时**（旧版 SKILL / 取证缺失）→ 视为取证缺失：`renderMode=null` + `renderModeSource="未取到(原因)"`，**绝不回落成有头/意图值**（取不到就不许编）。
   - 字段名 / 来源枚举（显式指定|复用已有实例|无头不可用降级|运行取证|未取到）/ null↔未取到 互为充要 / 复用实例时不得声称「显式指定」等口径的**单一信源 = SKILL `env-facts-schema.json` + `execution-methodology.md §10`，命令端不复述**（SPA 报告的字段名/数据形状仍以 `templates/reports/README.md` + `data/示例_build1001.js` 为准）。
4. **★ 产 AI测试报告 SPA = 调确定性脚本 `emit-report.py`（不手搓 data / 注册）**；⛔ 调用前先断言 `: "${BUILD:?本段需要 build 归属，空 BUILD 会落盘一份无归属的官方报告}"`**：把本轮测试结论（Phase 2 用例执行结果 + Phase 2.4 运行时错误 + 截图清单 + **3bis 实测环境事实**，即原 markdown 报告的同源内容）**结构化成一份结果 JSON**（★ `summary` 的 `total/eligible_total/counts/pass_rate` 一律取自 `python3 .aidp/skills/auto-test-runner/scripts/gen_report.py <round目录> --json`，⛔ 不手工累加——`na` 使通过率分母变为 `total-na`，手算必与 SKILL 口径不一致；其余按 `data/示例_build1001.js` 数据契约：`{build,version,buildNo,startedAt,finishedAt,deployMode,testUrl,renderMode,renderModeSource,driver, summary:{total,pass,fail,block,skip,na,passRate}, suites,cases,defects,runtimeErrors,screenshots}`；**★ `renderMode`/`renderModeSource` 取 3bis 实测值、不用 `RENDER_MODE` 意图值**；**★ `cases[]` 逐字段名（不可自创同义词）= `{id, title, suite, result:"pass|fail|block|skip|na", note, screenshot}`——不是 `name`/`status`/`detail`；**`na`（不适用）必须带非空 `note` 写明理由**，`emit-report.py` 空理由直接拒写**），写到**本报告目录下的临时输入** `docs/reports/{V}/AI测试报告/.build-input-{BUILD}.json`（★ 不放 `memory/` 根目录——放对应报告目录；写前先 `mkdir -p docs/reports/{V}/AI测试报告`；`.` 前缀隐藏 + gitignore + emit-report.py 用完自动删），再调：
   > **★ 数据契约唯一信源 = `.aidp/templates/reports/{AI执行报告|AI测试报告}/data/示例_build1001.js` + `templates/reports/README.md` schema 表**。写结果 JSON 前必须先读该示例文件，字段名/结构/单位以它为准：**禁止自创同义字段名、禁止改数组↔对象结构、比率字段一律 0~1 小数**。校验由 `emit-report.py` 强制执行（不符 exit 3 拒绝写盘），约定 21 命令端不复述具体字段清单、以示例文件为准。
   ```bash
   # ⛔ 用真实变量，不留字面 {V}/{BUILD}：花括号在 bash 里不展开，会真的去找名为 `{V}` 的目录 →
   #    骨架钢门指向不存在的 docs/reports/{V}/ 恒 FAIL，而 streak 记在真实版本上，3 tick 后
   #    冻成 handoff-exhausted（交接类、仅人工解冻），#F/#3 永不发。
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
   BUILD=$(python3 .aidp/scripts/baseline_edit.py --version "$TARGET_VERSION" get current_build --default "")
   python3 .aidp/scripts/emit-report.py --kind test --version "$TARGET_VERSION" --build "$BUILD" \
     --data "docs/reports/$TARGET_VERSION/AI测试报告/.build-input-$BUILD.json" --json
   # 脚本自动：① 缺骨架则 cp 模板 → ② 写 data/{BUILD}.js（window.__BUILDS__.push）→ ③ 注册 index.html
   #          → ④ 报告落本地 docs/reports/（不上传）→ ⑤ 回写 baseline report_deliveries
   # 返回 JSON 的 access_url（仓库相对路径，带 #/build/{BUILD}）供 #F 里程碑通知使用；同一 build 多轮收敛 → 覆盖 data、不重复注册（幂等）
   ```
   截图引用用相对 `index.html` 的 `screenshots/{BUILD}/xxx.png`。**⛔ 严禁自己写 markdown 测试报告 / 手工 cp+拼 `<script>`**——一律经 `emit-report.py`（HTML SPA 是唯一形态，见 `phase-3-1.md` 顶部 RED FLAG）。
5. **★ finalize 后确定性校验（残留占位符 / 环境事实未取证 = 报告不合格，不静默产出 —— 缺陷反馈第四·命令层要求）**：`emit-report.py` 成功后，扫本 build data `docs/reports/{V}/AI测试报告/data/{BUILD}.js`：
   ```bash
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
   BE="python3 .aidp/scripts/baseline_edit.py"
   BUILD=$($BE --version "$TARGET_VERSION" get current_build --default "")
   DATA="docs/reports/$TARGET_VERSION/AI测试报告/data/$BUILD.js"
   GATE_BAD=""
   # ① 未替换占位符（残留 {渲染模式}/{中文或英文占位} 花括号）
   grep -nE '\{[一-龥A-Za-z_][^}]*\}' "$DATA" && GATE_BAD="残留未替换占位符 → 回 3bis 重取证重写"
   # ② 环境事实未取证：renderMode 非 null 却缺 renderModeSource（= 值无取证来源，疑意图/示例穿透）
   if [ -z "$GATE_BAD" ] && grep -qE 'renderMode\s*:\s*"(headless|headed)"' "$DATA" && ! grep -qE 'renderModeSource\s*:' "$DATA"; then
     GATE_BAD="renderMode 有值但无 renderModeSource（未取证/意图穿透）→ 回 3bis 补运行取证"
   fi
   if [ -n "$GATE_BAD" ]; then
     # ⛔ 本 tick 内先按提示回 3bis 重取证 / 重写 data / 重跑 emit-report 并复跑本门；**复跑仍不过**才走下面这套记账。
     #    只 echo+exit 1 = /loop 每 tick 撞同一处、零 #4、零 streak、零冻结 —— 无人值守下静默空转。
     N=$($BE --version "$TARGET_VERSION" bump report_gate_fail_streak)
     echo "⛔ 报告不合格（连续 $N tick）：$GATE_BAD"
     # ★ 无唤醒源（HAS_WAKE_SOURCE=0：--once / 无 /loop）时没有下一 tick 叠 streak ⇒ 阈值恒不
     #   可达、永不冻结，而 exit 0 被上游读成"跑过了"。故当场按达阈处置（宁可早冻，不要静默）。
     # 记账已在上面的 bump 完成 → 这里按已知 streak 判阈并收口（交接类：解冻 = 人工）
     if [ "$N" -ge "${REPORT_GATE_FREEZE_THRESHOLD:-3}" ] || [ "${HAS_WAKE_SOURCE:-0}" = "0" ]; then
       python3 .aidp/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --freeze-now \
         --phase 3.2.6-report-gate --reason handoff-exhausted \
         --why "AI测试报告 finalize 校验连续 $N tick 不合格：$GATE_BAD"
       echo "⛔ 连续 $N tick 报告门未过 → 已冻结本版并发最后一张 #4，后续 tick 静默跳过"
     else
       python3 .aidp/scripts/notify.py --node "#4" --auto --header-color red \
         --title "AI 测试受阻：报告门未过" --version "$TARGET_VERSION" --build "${BUILD:-?}" \
         --section "第 $N 次（阈值 ${REPORT_GATE_FREEZE_THRESHOLD:-3}）：$GATE_BAD" || true
     fi
     exit 0   # ⛔ 不用 exit 1：已记账 + 已告警，让位本 tick
   fi
   $BE --version "$TARGET_VERSION" del report_gate_fail_streak || true   # 全通过 → 清零
   ```
   命中任一 → 终端 `⛔` 告警 + `report_gate_fail_streak` 记账，**回 3bis 重取证、重写 data、重跑 emit-report**，**不静默产出、不发 #F**（与"取不到就不许编"同口径）。全通过才继续 R-4 收尾。
   > 📌 **分工（不与 SKILL 重复）**：`env-facts.json` 本身的取证硬门（字段↔Source 成对 / null↔未取到 充要 / 无占位残留 / 复用实例约束）由 `auto-test-runner` 内置 `check_env_facts.py` + 其 8 维度质量检查负责；本 step 5 只校**命令端自有的 SPA 报告数据文件 `data/{BUILD}.js`**（JS，非 markdown，`check_env_facts.py --report` 解析不了），是约定 21 允许的项目级产物守卫，非重复实现。
5bis. **骨架钢门（发 #F 之前必过 · `--stage skeleton`）**：调 `autopilot-ceremony-gate.py check --stage skeleton`（`REPORT_ENABLED=1` 时）校验本 build「AI执行报告 SPA 骨架 + **AI测试报告 SPA**（本步刚由 emit-report 产）+ 无 markdown」——**此处不校交付台账**（exec 交付要到 Phase 3.7 R-4 才写，skeleton 阶段校它会时序死锁；交付台账留给 Phase 3.7 的 `--stage final` 门）：
   ```bash
   # ★ 跨分片取回本 tick 变量（BUILD / NOTIFY_ENABLED / REPORT_ENABLED 等真源在 baseline，自动回落）
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
   GATE=.aidp/scripts/autopilot-ceremony-gate.py
   BE="python3 .aidp/scripts/baseline_edit.py"   # baseline 唯一加锁写入口
   REPORT_GATE_BAD=""
   if [ -f "$GATE" ]; then
     python3 "$GATE" check --version "$TARGET_VERSION" --build "$BUILD" \
       --stage skeleton --will-browser-test 1 --notify "${NOTIFY_ENABLED:-1}" \
       --baseline memory/.sprint-autopilot-baseline.json || { REPORT_GATE_BAD="报告 SPA 骨架未过（ceremony-gate --stage skeleton）"; }
   else
     # ★ B4 兜底：gate 脚本缺失（脚手架未下发 / 旧下游）→ 内联轻量校验关键产物，绝不因脚本缺失静默 exit 1 阻死 #F
     if [ -f "docs/reports/$TARGET_VERSION/AI执行报告/index.html" ] && [ -f "docs/reports/$TARGET_VERSION/AI执行报告/data/$BUILD.js" ] && [ -f "docs/reports/$TARGET_VERSION/AI测试报告/index.html" ]; then
       echo "⚠️ autopilot-ceremony-gate.py 缺失 → 内联兜底校验通过（AI执行/测试报告 SPA 骨架在位）；建议重跑 aidp-code-engineer upgrade 补回 gate 脚本以获完整校验"
     else
       REPORT_GATE_BAD="骨架未过（内联兜底：报告 SPA 缺失）"
     fi
   fi
   # ── 统一处置 ─────────────────────────────────────────────────────────────
   # ⛔ **本门用自己的计数 `skeleton_gate_fail_streak`**，绝不与 step 5 的 finalize 校验
   #   共用 `report_gate_fail_streak` —— 三道门（3.2.5 截图 / 3.2.6 step5 finalize /
   #   本门骨架）共用一个计数时，同 tick 内前门通过即 `del`，后两门的阈值**恒不可达**：
   #   每 5 分钟跑一整轮全量实测 + 一张 #4，一天 288 轮，`needs_human` 永不置位。
   #   （禁令原文见 `phase-3-1.md`「只清本门自己的计数」；`phase-3-5.md` 的最终门同样单开了
   #   `final_gate_fail_streak`，本门照它办。）
   if [ -n "$REPORT_GATE_BAD" ]; then
     # 本 tick 内先 emit-report.py 补齐产物、复跑本门；**复跑仍不过**才走下面记账。
     N=$($BE --version "$TARGET_VERSION" bump skeleton_gate_fail_streak)
     echo "⛔ $REPORT_GATE_BAD（连续 $N tick）→ 补齐(emit-report.py)后复跑，禁止发 #F"
     # ★ 无唤醒源（HAS_WAKE_SOURCE=0：--once / 无 /loop）时没有下一 tick 叠 streak ⇒ 阈值恒不
     #   可达、永不冻结，而 exit 0 被上游读成"跑过了"。故当场按达阈处置（宁可早冻，不要静默）。
     if [ "$N" -ge "${REPORT_GATE_FREEZE_THRESHOLD:-3}" ] || [ "${HAS_WAKE_SOURCE:-0}" = "0" ]; then
       python3 .aidp/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --freeze-now \
         --phase 3.2.6-skeleton --reason handoff-exhausted \
         --why "报告骨架钢门连续 $N tick 未过：$REPORT_GATE_BAD"
       echo "⛔ 连续 $N tick 骨架钢门未过 → 已冻结本版并发最后一张 #4"
     else
       python3 .aidp/scripts/notify.py --node "#4" --auto --header-color red \
         --title "AI 测试受阻：报告骨架未过" --version "$TARGET_VERSION" --build "${BUILD:-?}" \
         --section "第 $N 次（阈值 ${REPORT_GATE_FREEZE_THRESHOLD:-3}）：$REPORT_GATE_BAD" || true
     fi
     exit 0   # ⛔ 不用 exit 1：已记账 + 已告警，让位本 tick
   fi
   $BE --version "$TARGET_VERSION" del skeleton_gate_fail_streak || true   # ⛔ 只清本门自己的计数
   ```
   **未过 → 不更新 baseline、不发 #F/#3**（把「只落 markdown / 未产 SPA」在发 #F 前拦死；交付台账由 Phase 3.7 的 final 门兜底），并按上面「记账 → 达阈冻结 → 发 #4 → 让位本 tick」处置，**不裸 `exit 1` 让 `/loop` 每 tick 重撞**。`REPORT_ENABLED=0`（standalone 无 `current_build`）→ 跳过报告产出与本门（不期望官方报告）。
6. **回写 baseline**：`builds[]` 中该 build 条目刷 `status:"tested"` + `pass_rate`（供 autopilot 读取）。

> 同一 build 多轮测试（无头收敛迭代）→ 覆盖该 build 的 `data/{BUILD}.js` 为最新一轮收敛结果（历史轮次差异由 git 历史追溯，不再每轮另存文件）。

