# sprint-autopilot · Phase 3 详情分片 [4/13]（3.1.5 铸 Build 号 + 写执行数据计划态）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 4/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：3.1.5（铸造 Build 号 + 写本 build 执行数据·计划态）
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-4.md`。理据见同目录 `rationale.md`。

---

#### 3.1.5 铸造 Build 号 + 写本 build 执行数据（计划态）

> 规划完成、拿到 Sprint 清单后，铸造本轮 build 号并立即写本 build 执行数据的计划态（plan.html 据此展示计划怎么跑），供后续 3.2 开发 + aiauto-test 测试报告归属。**不打 git 分支 / tag**。
>
> 📌 **AI执行报告产出归属（产骨架 / finalize 解耦）**：**骨架**（本步写 `data` 计划态 + Phase 3.4 finalize 结果态 + `testSummary` 占位）**只由 `/sprint-autopilot` 流水线产**；**finalize + 报告本体 + #3 通知**由 build 关闭方在 **#F 之后**做（浏览器路径 = 测试链路 Phase 3.7；静态-only = autopilot Phase 3.4 末尾）。本步铸的 `current_build` 即「autopilot 驱动」信号。完整归属矩阵与「无 current_build 时两者都不产」的理由见 rationale.md「AI执行报告的产出归属」。

1. **铸造或复用 build 号**（命令端 Bash，计数器存 baseline `memory/.sprint-autopilot-baseline.json` 该版本字典 `build_seq`，**自增后必须立即 jq 落盘回写**）：
   ```bash
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
   : "${BASELINE_FILE:=memory/.sprint-autopilot-baseline.json}"   # ★ 统一变量名 + 兜底默认（未定义时 jq 读 stdin 静默失败）
   BE="python3 .aidp/scripts/baseline_edit.py"                   # ★ baseline 唯一加锁写入口（见 invariants「baseline 单一写入口不变式」）
   BV="$TARGET_VERSION"
   RPT_AI="docs/reports/$BV/AI执行报告"
   # ★ 复用判定（子流程 R 幂等性 + 报告不可变收紧，item 2）：test-only 入口（Phase 3.0 设 ENTRY_MODE=test-only）
   #   且已有可复用 current_build（存在 + 其执行数据 data/{build}.js 在）**且该 build 未 finalize、状态未收尾**
   #   （status ∈ running/dev_done，即非 closed/tested）→ 复用不自增；
   #   ⛔ 已 finalize（ai_report_finalized=true）/ 已收尾（closed/tested）→ **强制铸新 build 跑新一轮复测**——
   #   报告不可变铁律：旧 build 报告已冻结、禁覆盖；结论变化一律新 build。
   CUR=$(jq -r ".versions.\"$BV\".current_build // empty" "$BASELINE_FILE" 2>/dev/null)
   CUR_SEQ="${CUR##*_build}"
   CUR_STATUS=$(jq -r ".versions.\"$BV\".builds[]? | select(.build==\"$CUR\") | .status // \"\"" "$BASELINE_FILE" 2>/dev/null | head -1)
   CUR_FINAL=$(jq -r ".versions.\"$BV\".builds[]? | select(.build==\"$CUR\") | .ai_report_finalized // false" "$BASELINE_FILE" 2>/dev/null | head -1)
   # ★ 复用判据与 ENTRY_MODE **解耦**：只看"这个 build 还没收口"（执行数据在 + 未 finalize +
   #   状态未 closed/tested），不看是谁进来的。⛔ 不得绑死 test-only（理据见 rationale.md）。
   REUSABLE=0
   if [ -n "$CUR" ] && [ -f "$RPT_AI/data/${CUR}.js" ] \
      && [ "$CUR_FINAL" != "true" ] && [ "$CUR_STATUS" != "closed" ] && [ "$CUR_STATUS" != "tested" ]; then
     REUSABLE=1
   fi
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --command autopilot --shell)"   # 取回 ENTRY_MODE 等本 tick 变量
   if [ "$REUSABLE" = "1" ]; then
     BUILD="$CUR"; BUILD_SEQ="$CUR_SEQ"
     # ★ entry_mode 落 build 级、复用时只补不覆盖（理由见 rationale.md「entry_mode 粒度」）；兼回填存量 build。
     [ -n "$ENTRY_MODE" ] && [ -z "$($BE --version "$BV" --build "$BUILD" get entry_mode --default "")" ] \
       && $BE --version "$BV" --build "$BUILD" set entry_mode "$ENTRY_MODE" >/dev/null || true
     echo "♻️ 复用现有 build：$BUILD（执行数据在 + 未 finalize/未收尾 → 不自增，入口=$ENTRY_MODE）"
   else
     # 复测轮判定：CUR 已 finalize/收尾 → 本次是「第 N 轮复测」，记 retest_of + round + 上轮通过率（供 #0/#D 通知 + SPA 复测关系）
     RETEST_OF=""; RETEST_ROUND=0; RETEST_LABEL=""
     if [ -n "$CUR" ] && { [ "$CUR_FINAL" = "true" ] || [ "$CUR_STATUS" = "closed" ] || [ "$CUR_STATUS" = "tested" ]; }; then
       RETEST_OF="$CUR"
       PREV_RATE=$(jq -r ".versions.\"$BV\".builds[]? | select(.build==\"$CUR\") | .pass_rate // \"?\"" "$BASELINE_FILE" 2>/dev/null | head -1)
       # ⛔ 不按 ai_report_finalized 计（未收敛轮从不 finalize ⇒ 恒"第 1 轮"，见 rationale.md）
       RETEST_ROUND=$(( $(jq -r "[.versions.\"$BV\".builds[]? | select(.retest_of != null)] | length" "$BASELINE_FILE" 2>/dev/null || echo 0) + 1 ))
       RETEST_LABEL="第 ${RETEST_ROUND} 轮复测（上轮 ${CUR} 通过率 ${PREV_RATE}）"
       echo "🔁 上一 build $CUR 已 finalize/收尾 → 铸新 build 跑复测：$RETEST_LABEL"
     fi
     # 读上次 build_seq（默认 1000 → 首个 build = 1001），+1
     LAST=$(jq -r ".versions.\"$BV\".build_seq // 1000" "$BASELINE_FILE" 2>/dev/null)
     BUILD_SEQ=$((LAST + 1)); [ "$BUILD_SEQ" -lt 1001 ] && BUILD_SEQ=1001
     BUILD="${BV}_build${BUILD_SEQ}"   # 如 V0.1.0_build1001
     # ★ 必须真正回写 baseline（不回写则 build_seq 不落盘，每次重跑都停在 1001）：
     #   持久化 build_seq（自增）+ current_build（供 aiauto-test 归属测试报告）+ 追加 builds[] 条目（复测轮带 retest_of/retest_round）
     #   ⛔ 一律走 baseline_edit.py 那把 flock（+ 锁内重读），不要裸 `jq … > tmp && mv`
     #      （见 invariants「baseline 单一写入口不变式」）。
     #   标量字段用 CLI；builds[] 是**数组追加**（点号路径只走 dict、表达不了 append），故按 invariants 的既定做法
     #   `from baseline_edit import LockedBaseline` 在同一把锁内改（绝不另起一套写盘范式）。
     $BE --version "$BV" set build_seq "$BUILD_SEQ" current_build "$BUILD"
     # ★ 新 build = 新一轮，旧轮次的未收敛计数不该继续计入（见 rationale「未收敛计数为何要跨 build 清零」）
     $BE --version "$BV" del aiauto_test_unconverged_streak 2>/dev/null || true
     # ★ CICD 重试计数同样跨 build 清零（根因见 rationale「重试配额被当成版本总额」）
     $BE --version "$BV" del cicd_run.cicd_retry_count 2>/dev/null || true
     # ★ dev_fail_streak 同理跨 build 清零（契约是「连续失败」，不清即终身累计）
     $BE --version "$BV" del dev_fail_streak dev_fail_phase 2>/dev/null || true
     BUILD="$BUILD" BV="$BV" RETEST_OF="$RETEST_OF" RETEST_ROUND="$RETEST_ROUND" \
     ENTRY_MODE="$ENTRY_MODE" python3 - <<'PY'
import os, sys
sys.path.insert(0, ".aidp/scripts")
from baseline_edit import LockedBaseline, now_iso   # 同一把 flock + 锁内重读 + 原子替换
bv, b = os.environ["BV"], os.environ["BUILD"]
entry = {"build": b, "started_at": now_iso(), "status": "running"}
# ★ entry_mode 落【build 级】（勿删，理由见上方复用分支注释）：收尾门与 Stop hook 都优先读这里。
if os.environ.get("ENTRY_MODE"):
    entry["entry_mode"] = os.environ["ENTRY_MODE"]
if os.environ.get("RETEST_OF"):
    entry["retest_of"] = os.environ["RETEST_OF"]
    entry["retest_round"] = int(os.environ.get("RETEST_ROUND") or 0)
with LockedBaseline("memory/.sprint-autopilot-baseline.json", write=True) as bl:
    ver = bl.data.setdefault("versions", {}).setdefault(bv, {})
    ver.setdefault("builds", []).append(entry)
PY
     echo "🔢 铸造 build 号：$BUILD（已落盘 build_seq=$BUILD_SEQ；下次重跑自增，不停在 1001；不打 git 分支/tag）${RETEST_LABEL:+ · $RETEST_LABEL}"
   fi
   # ★ 复测轮标注（$RETEST_LABEL 非空时）：#0 起测通知 / #D 部署通知须在标题或首行带该标注（形如"第 N 轮复测（上轮通过率 X%）"）。
   ```

2. **确保报告目录骨架存在 + AI执行报告(结果 index.html + 计划 plan.html 两页) + AI测试报告 入口就位 + shell 版本对账刷新**（首个 build 按 `.aidp/templates/reports/` 创建；已有 shell 则比对 `report-shell-version`，模板更新则刷新所有页面 + 样式、数据保留）：
   ```bash
   # ★ 新围栏须重新取回 $BV（它不在 tick 白名单；取空则 SPA 铺到错目录，见 rationale.md）
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
   BV="${TARGET_VERSION:?}"
   RPT="docs/reports/$BV"; TPL=".aidp/templates/reports"
   # ★ 模板存在性硬门：报告模板由脚手架铺设（scaffold/migrate/upgrade mirror templates/reports）。
   #   缺失 = 脚手架未铺（旧版漏 mirror）→ 报错指引重跑脚手架，**严禁手搓 index.html/plan.html/assets 或跳过 AI执行报告**。
   for T in "$TPL/AI执行报告/index.html" "$TPL/AI执行报告/plan.html" "$TPL/AI执行报告/assets/app.js" "$TPL/AI执行报告/assets/plan.js" "$TPL/AI测试报告/index.html"; do
     [ -f "$T" ] || { echo "❌ 报告模板缺失：$T —— 脚手架未铺 templates/reports/。请先重跑 aidp-code-engineer 脚手架（init/migrate/upgrade）补模板，再继续；禁止手搓报告或跳过 AI执行报告。"; exit 1; }
   done
   # AI执行报告已拍平：index.html(结果) + plan.html(计划) + assets/ + data/ 同级（无子目录）
   mkdir -p "$RPT/AI执行报告/data" "$RPT/AI执行报告/assets" \
            "$RPT/AI测试报告/data" "$RPT/AI测试报告/assets" \
            "$RPT/AI测试报告/screenshots" "$RPT/版本测试报告"
   # 两个累积型离线报告（AI执行报告 = index.html 结果 + plan.html 计划，合并拍平、共享 data/；AI测试报告 = index.html）：
   #   缺→拷模板所有页面；shell 版本旧→刷新所有 *.html + assets/（保留 data/+screenshots/）。版本戳以 index.html 顶部 `<!-- report-shell-version: N -->` 为准（同套页面同版本）。
   for SPA in "AI执行报告" "AI测试报告"; do
     D="$RPT/$SPA"; DO_REFRESH=0
     if [ ! -f "$D/index.html" ]; then
       DO_REFRESH=1   # 首个 build：拷模板
     else
       TV=$(grep -oE 'report-shell-version: *[0-9]+' "$TPL/$SPA/index.html" | grep -oE '[0-9]+$'); TV=${TV:-0}
       CV=$(grep -oE 'report-shell-version: *[0-9]+' "$D/index.html"       | grep -oE '[0-9]+$'); CV=${CV:-0}
       [ "$TV" -gt "$CV" ] && { DO_REFRESH=1; echo "🔄 $SPA 报告 shell v$CV→v$TV 刷新（所有页面 + assets，data/+screenshots/ 保留）"; }
     fi
     if [ "$DO_REFRESH" = 1 ]; then
       # 拷模板所有页面（AI执行报告 = index.html + plan.html；AI测试报告 = index.html）+ assets/，删模板示例 data 注入行
       for h in "$TPL/$SPA"/*.html; do hb=$(basename "$h"); cp "$h" "$D/$hb"; sed -i '/data\/示例_/d' "$D/$hb"; done
       cp -r "$TPL/$SPA/assets/." "$D/assets/" 2>/dev/null
       # 干净 shell 丢了历史 data 注册行 → 把 data/ 下所有 build 脚本在渲染脚本(app.js/plan.js)之前重注册到【每个页面】
       for f in "$D"/data/*.js; do
         [ -f "$f" ] || continue; b=$(basename "$f")
         for h in "$D"/*.html; do
           grep -q "data/$b" "$h" || sed -i 's#<script src="assets/\(app\|plan\)\.js"></script>#<script src="data/'"$b"'"></script>\n  <script src="assets/\1.js"></script>#' "$h"
         done
       done
     fi
   done
   # 各级 README 缺失同理从 .aidp/templates/reports/ 对应骨架拷入
   ```

3. **写本 build 执行数据文件（计划态）+ 注册到两页**：详见同目录 `rationale.md`「写本 build 执行数据文件的注册细则」。
   - **build 元信息**：`build` / `version` / `trigger` / `branch` / `deployMode` / `startedAt` / `planSource`（plan.html 元信息段用）
   - **★ steps[]（stepper + 计划甘特 + 步骤依赖表的唯一数据源）**：覆盖本轮 build 完整任务链路 `Phase 0 拉码+前置检查` → `Phase 1 PRD 检测` → `Phase 2 准发布(仅 PRE_RELEASE 非空)` → `Phase 3.1 版本规划` → `Phase 3.1.5 铸造 build+本数据` → 按 `01_研发执行计划.md` 的 Sprint 清单逐个（每个 Sprint 一行 `start→dev→test→bugfix→close`）→ `Phase 3.3 终审(version-auditor)` → `部署` → `Phase 3.4 生成结果+完成核验` → `AI 自动化测试` → `AI测试报告`。每步填 `name`（★ **≤ 14 字的简短标签**，明细放 `output`）/ `type`（准备/前置/规划/构建/开发/部署/测试/报告/审计——plan.js 据 type 估算甘特耗时）/ `output`（预期产物）/ `plannedStatus`。**★ 回填已发生的前置步骤**：本步在 Phase 0/1/3.1 **之后**执行，第 0/1/3.1/3.1.5 步 `plannedStatus` 直接填 `done`（已发生）+ 实际 `duration`；其后 Sprint/部署/测试/报告步骤 `plannedStatus: "plan"`
   - **★ features[]（需求功能点比对的唯一数据源）**：从 `docs/requirements/{TARGET_VERSION}/研发需求/01_研发需求.md`（拆分目录则汇总分册 `0N_*.md`）的**功能规格清单逐点**抽取，每点一条——`reqId`（沿用需求文档原编号，无编号按章节顺序补 `FP-NN`）/ `name` / `reqSource`（来源需求章节）/ `sprint`（按 `01_研发执行计划.md` 的 Task↔Sprint 映射）/ `status`（本步统一 `pend` 未开始，Phase 3.4 刷新为 done/doing/fail/skip）。**此为"已完成功能点逐条对照需求文档"的信源**，粒度为功能点而非 Sprint
   - **★ 写盘 + 注册 = 调 `emit-report.py`（不手写文件 / 不手工 sed 注册）**：把执行数据对象（`build`/`steps[]`/`features[]`/元信息等）序列化成 JSON 存到**本报告目录下的临时输入** `docs/reports/$BV/AI执行报告/.build-input-${BUILD}.json`（写前先 `mkdir -p`；emit-report.py 用完自动删），再调 `python3 .aidp/scripts/emit-report.py --kind exec --version "$BV" --build "$BUILD" --data "docs/reports/$BV/AI执行报告/.build-input-${BUILD}.json"`（骨架态，不写交付台账）——脚本自动写 `data/${BUILD}.js`（`window.__AIRUNS__.push`）+ 注册 `<script>` 到 index.html **和** plan.html 两页（幂等，重跑覆盖 data、不重复注册）。后续 H1~H7 hook 是对该 data 的**小改 Edit**（不重走 emit-report），finalize 时再带完整结果态重调一次。
   - **★ test-only / 纯复测轮次语义**：`ENTRY_MODE=test-only`（版本已开发完成、本轮无新 dev、只跑后续 AI 自动化测试）时数据仍**必产**，语义是「测试执行轮次」——dev/Sprint 步骤 `plannedStatus: "done"`（历史已完成）、本轮 live 步骤 = 部署(如需)+AI 测试；features `status` 按既有开发成果填（非统一 `pend`）。**无新 dev ≠ 无报告**。

> 本步在 `--no-loop` / `/loop` / `--once` 下均执行；纯静态（`deployment.mode=none`）时 steps 省略部署 + AI 测试两步。

4. **★ 「步骤完成即实时回写」hook 清单（执行数据全程可追踪，非两点快照）**：`data/${BUILD}.js` 的 `steps[]` 在本步（3.1.5）只是**计划态**（已发生的 Phase 0/1/3.1/3.1.5 的 step `plannedStatus:done` + 实际耗时，其后 `plan`）。**自本步起，每完成一个主步骤就【就地回写】该 step 的 `actualStatus`（`done/doing/fail/pend/skip`）+ `duration`**（同一份 steps 驱动 plan.html / index.html 两视图）。**回写 hook 点**（每点完成即写一次，几行 Edit 级小改）：
   | Hook | 触发时机 | 回写的步骤行 |
   |------|---------|------------|
   | **H1** | Phase 0（拉码 + 前置检查）完成 | 「0 拉码」「1 前置检查」→ ✅（本步已发生，骨架即标 ✅）|
   | **H2** | Phase 3.1.5 铸造 build + 本计划生成完成 | 「铸造 build + 写执行数据」→ actualStatus done |
   | **H3** | Phase 3.2 **每个 Sprint `close` 时** | 该 Sprint 行（含 `start→dev→test→bugfix→close` 子状态）→ ✅ + 实际耗时（**每关一个 Sprint 回写一次**，不攒到最后）|
   | **H4** | Phase 3.3 终审（version-auditor）完成 | 「终审」→ ✅ |
   | **H5** | 部署动作完成（写 `last_deployed_at` 后）| 「部署」→ ✅ + 访问 URL |
   | **H6** | AI 自动化测试 | 由测试链路 `/sprint-aiauto-test` 回写：每轮刷「AI 测试」为 `🔶 进行中（第 N 轮）`、收敛后 `✅ 完成`（见其 Phase 3.7；细粒度每用例/每套件进度落 AI测试报告 SPA，不灌执行数据）|
   | **H7** | AI测试报告 + #F 完成 | 「生成 AI执行报告 / 测试报告」→ actualStatus done（由测试链路 Phase 3.7 回写）|
   > H1~H5 由 autopilot 在对应 Phase 完成时回写；H6/H7 由 `/sprint-aiauto-test` 回写（执行数据路径 = `docs/reports/{TARGET_VERSION}/AI执行报告/data/{version}_build{N}.js`，跨命令共享）。回写只改这一份 data 的 `steps[].actualStatus` + `duration`，**无 md 双写**。


---

## ⛳ 本 Phase 出口：`run_state` 写盘（**硬动作，不可跳过**）

> 单一信源 = `invariants.md`「阶段推进不变式」，此处只给本分片的**具体实参**。
> ⛔ 漏这一步 = 状态机不存在（`next_phase` / `next_sprint` 恒空的代价见 `rationale.md`）。
> **本 Phase 的实质动作做完、离开本分片之前立即执行**：

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
BE="python3 .aidp/scripts/baseline_edit.py"; V="${TARGET_VERSION}"
# ★★ 版本级 `deployment_mode` 落盘 = autopilot 链内**唯一写入者**，⛔ 别删
#    （ceremony-gate 两处读它；零写入方的后果见 rationale.md「deployment_mode 的写入者」）
$BE --version "$V" set deployment_mode "${DEPLOY_MODE:-none}"
# ★ 新 build = 新的收敛周期：Phase 2 测试暂缓计数不跨 build 累加
$BE --version "$V" del prerelease_test_hold_streak || true
# ★ 必须按 ENTRY_MODE 分流：test-only 整片跳过 Phase 3.2 开发循环（见 phase-3-5.md）；
#   ⛔ 不得硬编码 next="3.2-dev"（理据见 rationale.md）。
#   ⛔ test-only 的 next 是 **3.3-audit 而非 3.4-finish**：version-auditor 终审是
#   「任何入口都不豁免」的强制仪式（命令主体 Phase 3 骨架表 + ceremony-gate 都无条件校
#   `docs/audit/{V}/version-output-audit-{BUILD}.md`）。
if [ "${ENTRY_MODE:-full}" = "test-only" ]; then
  NEXT_PHASE="3.3-audit"; NEXT_SPRINT="done"
else
  # ★ Sprint 号口径同 phase-3-5（唯一实现 = plan_sprints.py）；⛔ 不得留空（见 rationale.md）
  # ⛔ incremental 先分流：它本就无 Sprint，落到下面必 100% 命中 fail-closed（见 rationale.md）
  if [ "${ENTRY_MODE:-full}" = "incremental" ]; then
    NEXT_PHASE="3.2-dev"; NEXT_SPRINT="done"
  else
    _PS=$(python3 .aidp/scripts/plan_sprints.py --version "$V" --shell) || exit 1
    eval "$_PS"; : "${REMAIN_COUNT:?plan_sprints fail-closed（计划文件缺失/解析不出 Sprint-NNN）}"
    # ⛔ 无未关闭 Sprint ≠ 异常：复测轮 / --target 重跑时该版 Sprint 本就全关（见 rationale.md）
    NEXT_PHASE="3.2-dev"; [ -n "$NEXT_SPRINT" ] || NEXT_SPRINT="done"
  fi
fi
$BE --version "$V" run-state "3.1.5-build" "$NEXT_PHASE" "$NEXT_SPRINT" \
  --summary "Phase 3.1.5 完成：build=${BUILD} 已铸造 + 本 build 执行数据已写" --pending ""
```

> `FIRST_SPRINT` = 本轮要跑的第一个 Sprint 号（增量路径无 Sprint 则留空）——它是 Phase 3.2 逐 tick 续跑游标的初值。
