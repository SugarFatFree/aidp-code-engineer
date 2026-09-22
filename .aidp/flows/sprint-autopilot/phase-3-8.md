# sprint-autopilot · Phase 3 详情分片 [8/13]（3.3 终审 + 3.4 收尾 Step 1–3 关闭方判定与发报告）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 8/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：3.3（终审 version-auditor）+ 3.4 收尾 Step 1–3（finalize 结果态 / emit-report 产报告 / #3 通知）
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-8.md`。理据见同目录 `rationale.md`。

---

### 3.3 终审（无单独通知，并入 3.4）

1. 启动 `version-auditor` Agent（独立子 Agent，审计八项 A–H）—— **强制仪式**：由 Phase 3.4 完成核验门的外部脚本 `autopilot-ceremony-gate.py` 校验，**任何入口模式（含交互式 / test-only）都不得跳过**（`--skip-audit` 仅 `/version` 内部开关，**不豁免**本终审）

   > ⛔ **产物文件名必须带 build，不得与 `/version` 内部审计同名（否则本终审可被上游遗留文件"静默满足"）**：`/version` Step 2.4.7 内部跑的 version-auditor 写的是 `docs/audit/{V}/version-output-audit-YYYY-MM-DD.md`；若 autopilot 终审也落同一命名空间，收尾门只要 glob 到**任意**一份 `version-output-audit*.md` 就判通过——**本终审压根没跑也能过**（尤其 `PLANNING_DONE=1` 跳过规划、上游文件早已存在时）。
   > 故 autopilot 终审**固定写独立文件**：
   > ```
   > docs/audit/{V}/version-output-audit-{BUILD}.md      # 如 docs/audit/V0.2.0/version-output-audit-V0.2.0_build1001.md
   > ```
   > 委派 `version-auditor` 子 Agent 时**显式传入 `trigger=autopilot`、`build={BUILD}`、`output_path=docs/audit/{V}/version-output-audit-{BUILD}.md`**，并在报告头注明「autopilot Phase 3.3 终审 · build={BUILD}」。这三个字段已纳入 Agent 交互协议；Agent 不得自行回退到日期文件名。
   > 📌 **gate 侧按 build 校验**：`autopilot-ceremony-gate.py` 对本项只认 `version-output-audit-{BUILD}.md`（经 `--build` 传入），同版本其他 build 的终审文件不算数。
2. 任一审计 Critical → 走「失败处置」流程（⛔ 散文不算处置，必须**可执行地**跑）：

  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${TARGET_VERSION:?}" \
    --phase 3.3-audit --reason audit-critical \
    --why "Phase 3.3 version-auditor 终审检出 Critical"
  # 退出码：0=已记账让位本 tick／3=已冻结（达阈或无唤醒源）／2=入参错（⛔ 此时什么都没写）
  ```

3. 全部通过 → 进 Phase 3.4

### 3.4 完成通知 + 收尾

1. **finalize 本 build 执行数据（结果态）+ 收尾 build**（数据文件已在 Phase 3.1.5 以计划态创建；本步补全结果态字段。★ **骨架**：dev/部署步骤 `actualStatus` 填实际、`testSummary` **占位待测**；真实测试结论的 finalize + 报告交付登记 + #3 通知见下方 **1.6 R-4 分流**——不在本步发）：

   ⛔ **RED FLAG**：AI 执行报告唯一形态 = **离线 HTML**（index.html 结果 + plan.html 计划，与 AI测试报告同构，多 build 共享 `AI执行报告/index.html` + `plan.html`）。**禁止**生成 `Build{N}_AI执行结果.md` / `AI执行计划_Build{N}.md` 等任何 markdown 报告；正确动作 = **补全 `data/${BUILD}.js` 数据 → 确认已注册 `<script>` 到两页**（计划由 plan.js、结果由 app.js 从同一份数据渲染）。

   **1.1 补全 build 执行数据（结果态）**：按 `{{AIDP_HOME}}/templates/reports/AI执行报告/data/示例_build1001.js` 数据契约，把 Phase 3.1.5 计划态数据补全为结果态（`overview`/`steps[].actualStatus`/`features[].status`；`testSummary` 此步仍占位待测）后，**仍经 `emit-report.py` 确定性写盘 + 注册**（不手改文件）：序列化完整结果态对象到本报告目录下的 `docs/reports/$V/AI执行报告/.build-input-${BUILD}.json`（不放 `memory/` 根；目录已存在，无需再 mkdir）→ `python3 {{AIDP_HOME}}/scripts/emit-report.py --kind exec --version "$V" --build "$BUILD" --data "docs/reports/$V/AI执行报告/.build-input-${BUILD}.json" --record-baseline 0`（骨架 finalize 带 `--record-baseline 0`，不写 `report_deliveries` 交付台账，交付登记留 R-4；emit-report 用完自动删该输入）。
   - **★ `links` 内相对路径以 `AI执行报告/index.html` 为基准**（目录已拍平，index.html 直接在 `AI执行报告/` 下）。**★ 不写 `testReport` / `reportLink` 兄弟报告路径**——AI测试报告链接由 `app.js`/`plan.js` 按当前页所在目录【运行时推导】（本地中文目录 `AI测试报告` / 静态托管英文 slug `ai-test-report` 两端都通），写死中文目录会在发布到英文 slug 后 404。**不再有 `planDoc`**——执行计划由同目录 `plan.html#/build/${BUILD}` 承载，app.js 按 build 自动拼链接。
   - 字段：
   - **执行概览（overview）**：`statusKind` / `featureRate` / `testPassRate` / `coverage` / `pendingCount`（待人工决策数）/ `autoFixedCount`（自动修复缺陷数）/ `riskLevel`（+ 可选 `riskBasis`）
   - **步骤执行结果（steps[].actualStatus）**：把 Phase 3.1.5 计划态步骤（**含已回填 done 的 0/1/2 步**）对照实际跑的结果填 `actualStatus`（`done/doing/fail/pend/skip`）+ 实际 `duration` + `output`
   - **需求功能（features[].status）**：把 Phase 3.1.5 写的 features（`status:pend`）**逐功能点**对照实际刷新为 `done/doing/fail/skip`（plan.html 与 index.html 同源渲染本数组）；**严禁**只填 Sprint 级粗粒度 → 否则"哪些功能点已完成"无法逐条对照
   - **测试摘要（testSummary）**：★ **骨架阶段占位**——将有浏览器测试时填 `{total:0, pass:0, fail:0, passRate:null, coverage:null, pendingBrowserTest:true}`；`overview.testPassRate` 同置 `null`/待测。**真实数值由 build 关闭方 finalize 回填**（测试链路 #F 后 / 静态-only 时 autopilot 1.6）。 / **缺陷（defects）** / **风险与建议（`risks: [{id, level:"高|中|低", title, what, risk, advice}]` —— ★ 数组，等级写在每项 `level` 字段里，严禁按 `{high, medium, low}` 分组，否则 app.js `.map` 抛错致执行报告整页白屏、且被 emit-report.py 校验拒绝）** / **异常处置（incidents）** / **剩余待办（`todos: [{title[, detail]}]` —— ★ 对象数组，非裸字符串数组）** / **关联链接（links）★ 不写 `testReport`/兄弟报告路径——AI测试报告链接由 app.js/plan.js 按当前页目录运行时推导（本地中文目录 / 静态托管英文 slug 两端都通），写死中文目录会在发布后 404**

   **1.2 确保已注册到两页**：`data/${BUILD}.js` 应已在 Phase 3.1.5 注册到 `AI执行报告/index.html`（`assets/app.js` 之前）与 `AI执行报告/plan.html`（`assets/plan.js` 之前）；若任一页缺该注册行则补追加（`src` 相对各页面仍是 `data/${BUILD}.js`，因 data 与两页同在 `AI执行报告/`）。同一 build 重跑则**覆盖** data 文件、不重复注册。

   **1.3 确认 steps/features 已刷新为实际态**：本步只需把 1.1 的 `steps[].actualStatus` / `features[].status` 对照实际结果刷新到这一份 data——plan.html 读 `plannedStatus` 看计划态、index.html 读 `actualStatus`/`status` 看实际态，**同源无双写（不再刷任何计划 md）**。未在 `code/` 落地的功能点 `status` 标 `fail`（严禁"列了即完成"）。

   **1.4 回写 baseline**：`versions.{V}.current_build` 对应的 `builds[]` 条目 `status: "dev_done"` + `finished_at`（测试结果待 aiauto-test 回填）。★ **同时标 `frontend_changed`（部署覆盖度信号）**：本 build 是否改动 `code/frontend/**`——`git diff --name-only <build 起始 commit>..HEAD | grep -q '^code/frontend/'`（取不到起始 commit 则按本轮开发是否触碰前端目录判）；`true` 且 Step D 情形③前端探针已过则同置 `frontend_deploy_verified: true`。二者供 `autopilot-ceremony-gate.py` 3e「部署覆盖度」校验半截部署（前端有改动却无前端部署证据 → FAIL）。

   ⛔ **必须是可执行语句**——3e 是 `if/elif` 无 `else`：字段不是 `True` 时该门**连一行都不输出**，
   于是"前端改了却没部署"这类半截部署静默通过。散文声明不算写入：

   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   BEB="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?} --build ${BUILD:?}"
   # 起始 commit 取 builds[].push_base_ref；不得凭 HEAD~1 推断本 build 前端改动。
   BUILD_BASE_COMMIT=$($BEB get push_base_ref --default "")
   VCS_MODE=$(python3 -c 'from pathlib import Path; import sys; sys.path.insert(0, "{{AIDP_HOME}}/scripts"); from vcs import detect_mode; print(detect_mode(Path.cwd()))') || exit 1
   if [ "$VCS_MODE" = none ]; then
     # X.0.0 的逐文件哈希清单含新增/修改/删除；缺证据时保守置 true，让 3e 要求部署覆盖度复核。
     CHANGES_ROOT="memory/${TARGET_VERSION}"
     FE_CHANGED=$(CHANGES_ROOT="$CHANGES_ROOT" python3 -c 'import json,os; from pathlib import Path; paths=list(Path(os.environ["CHANGES_ROOT"]).glob("*/sprints/sprint-*-local-changes.json")); print("true" if not paths or any(x["path"].startswith("code/frontend/") for p in paths for x in json.loads(p.read_text(encoding="utf-8"))) else "false")') || exit 1
   else
     FE_CHANGED=$(git diff --name-only "${BUILD_BASE_COMMIT:-HEAD~1}"..HEAD 2>/dev/null \
                    | grep -q '^code/frontend/' && echo true || echo false)
   fi
   $BEB set status dev_done finished_at @now frontend_changed "$FE_CHANGED"
   ```

   **1.5 ★ 产物硬核自检**：index.html + plan.html + data/${BUILD}.js 都必须在且 data 已注册到两页：
     ```bash
     eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
     RPT="docs/reports/${TARGET_VERSION}/AI执行报告"   # ⛔ 花括号占位符不是 shell 变量：写成 {TARGET_VERSION} 会让下面三项硬核自检恒不命中、每轮刷假红
     { [ -f "$RPT/index.html" ] && [ -f "$RPT/plan.html" ]; } || echo "❌ 缺 AI执行报告 页面（回 Phase 3.4 step2 对账：cp 模板 index.html+plan.html+assets）"
     { [ -f "$RPT/data/${BUILD}.js" ] && grep -q "data/${BUILD}.js" "$RPT/index.html" && grep -q "data/${BUILD}.js" "$RPT/plan.html"; } \
        || echo "❌ 执行数据缺失/未注册到两页（回本步：写 data/${BUILD}.js → 注册 script 到 index.html + plan.html）"
     STRAY=$(ls "$RPT"/*_AI执行结果.md "$RPT"/AI执行计划_Build*.md 2>/dev/null); [ -n "$STRAY" ] && { echo "❌ 检出违规 markdown 报告（应只产 HTML）：$STRAY"; rm -f $STRAY; }
     ```
     任一缺失 → **必须就地补建**，不得跳过 AI 执行报告骨架直接进后续。

   **1.6 ★ 关闭方判定 + R-4 分流（「产出骨架」与「finalize + 发送」解耦的核心）**：
   ```bash
   # 从 baseline 读回 DEPLOY_MODE/SKIP_DEPLOY；不得用跨 Bash 调用的裸变量决定关闭方。
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   # 将有浏览器测试 = 有本 build 就绪的部署（test-only 可复用已核实的部署）；mode 字段本身不是就绪证据。
   # 用户显式 --skip-aiauto-test 或 --skip-deploy 时不得交接浏览器测试。
   VCS_MODE=$(python3 -c 'from pathlib import Path; import sys; sys.path.insert(0, "{{AIDP_HOME}}/scripts"); from vcs import detect_mode; print(detect_mode(Path.cwd()))') || exit 1
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
   DEPLOYED_AT=$($BE --version "$TARGET_VERSION" get last_deployed_at --default "")
   HANDOFF_AT=$($BE --version "$TARGET_VERSION" get phase_beta_done_at --default "")
   BUILD_STARTED=$($BE --version "$TARGET_VERSION" --build "$BUILD" get started_at --default "")
   DEPLOY_READY=0
   # test-only 可复用已有可测部署；开发路径必须看到本 build 开始后真实就绪的部署证据。
   # vcs_mode=none + cloud 即便遗留旧 last_deployed_at 也不具备本轮部署能力。
   if { [ "$VCS_MODE" = git ] || [ "${DEPLOY_MODE:-none}" = local ]; } \
      && [ -n "$DEPLOYED_AT" ] && [ -n "$HANDOFF_AT" ]; then
     if [ "${ENTRY_MODE:-}" = test-only ]; then
       DEPLOY_READY=1
     elif [ -n "$BUILD_STARTED" ] && [ "$(date -d "$DEPLOYED_AT" +%s 2>/dev/null || echo 0)" -ge "$(date -d "$BUILD_STARTED" +%s 2>/dev/null || echo 1)" ]; then
       DEPLOY_READY=1
     fi
   fi
   WILL_BROWSER_TEST=$( { [ "${SKIP_AIAUTO_TEST:-0}" != 1 ] && [ "${SKIP_DEPLOY:-0}" != 1 ] && { [ "${ENTRY_MODE:-}" = test-only ] || [ "${DEPLOY_MODE:-none}" != none ]; } && [ "$DEPLOY_READY" = 1 ]; } && echo 1 || echo 0 )
   [ "$DEPLOY_READY" = 0 ] && echo "⚠️ 无可验证部署（vcs_mode=$VCS_MODE，mode=${DEPLOY_MODE:-none}）：浏览器测试不交接旧服务，报告如实标记未执行"
   # ★ 落盘供下游收尾门（phase-3-9.md）读回 —— 它据此定 GATE_STAGE 与期望通知集
   python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot WILL_BROWSER_TEST "$WILL_BROWSER_TEST"
   # 同时落版本级真源，供从 3.4-finish 游标恢复时回读。
   python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" \
     set will_browser_test "$WILL_BROWSER_TEST"
   ```
   - **`WILL_BROWSER_TEST=1`（将有浏览器测试 → 本 build 由测试链路关闭）**：**跳过下面 Step 2/3**。打印「✅ AI执行报告骨架就绪；testSummary + 报告交付登记 + #3 通知 = R-4 收尾，由 `/sprint-aiauto-test` 在 #F 之后 finalize/发送（见其 Phase 3.7），autopilot 不在此发」。直接进 Step 4 完成核验门（只校骨架）。开发链路的 dev-done 里程碑由 **#1d 部署通知**承担（不是 #3）。
   - **`WILL_BROWSER_TEST=0`（纯静态 / `--skip-deploy`，无浏览器测试 → autopilot 即 build 关闭方）**：autopilot **就地执行 R-4**——先 finalize `data/${BUILD}.js` 的 `testSummary` 为**静态自测结论**（⛔ **形状按【维度】不按【用例】**：`code-verification-loop` 的产出是各维度 Pass/Fail 汇总 + 问题清单，全 SKILL **无「用例数 / 通过率」概念**，写成用例形状只能让执行体编数字、与同段「计数口径按真实点算，不臆造」自相矛盾。落 `total`=已核维度数 + `unit:"dimension"`, `pass/fail`=各维度 Pass/Fail 计数, `passRate`=维度通过率, `coverage:null`, `browserTested:false`；维度数取不到则 `total:null` + `note:"静态验收无用例计数"`）+ 刷 `overview.testPassRate` + data steps「AI 测试」步 `actualStatus: "skip"`（纯静态无浏览器测试），**再**跑下面 Step 2（定稿报告 + 交付登记）+ Step 3（发 #3，结论=静态自测、无浏览器测试）。

2. **★【R-4 收尾·仅 `WILL_BROWSER_TEST=0` 时由 autopilot 执行】定稿报告 + 交付登记 = 调 `emit-report.py`（不手工拷贝/改文件；**必须经它以写 `report_deliveries` 交付台账，否则收尾钢门交付检查会误判缺失**）**：先把含**真实静态 testSummary** 的完整执行数据序列化到本报告目录下的 `docs/reports/$TARGET_VERSION/AI执行报告/.build-input-${BUILD}.json`（不放 `memory/` 根），再调（**这次不带 `--record-baseline 0`**，让它回写交付台账；emit-report 用完自动删该输入）：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"; mkdir -p memory/.aidp
   python3 {{AIDP_HOME}}/scripts/emit-report.py --kind exec --version "$TARGET_VERSION" --build "$BUILD" \
     --data "docs/reports/$TARGET_VERSION/AI执行报告/.build-input-${BUILD}.json" \
     --baseline memory/.sprint-autopilot-baseline.json --json > memory/.aidp/emit-exec-${BUILD}.json
   # 脚本自动：写 data 结果态 + 注册两页（报告落本地 docs/reports/）→ 回写 baseline report_deliveries.exec_report
   AI_REPORT_URL=$(jq -r '.access_url // .report_path' memory/.aidp/emit-exec-${BUILD}.json)   # 报告仓库内相对路径
   ```
   - `AI_REPORT_URL` = 报告在仓库内的相对路径（`docs/reports/${TARGET_VERSION}/AI执行报告/index.html#/build/${BUILD}`）；项目配置了 GitHub Pages 等静态托管（由 CI 发布）时可换成对应站点链接，或用 GitHub 文件链接。#3 通知发它。
   - **`WILL_BROWSER_TEST=1` 时本步整段跳过**（exec 报告的定稿 + 交付台账由测试链路在 #F 后经同一 `emit-report.py --kind exec` 执行，见 aiauto-test Phase 3.7）。

2bis. **★【R-4 收尾·必做】把本 build 标为「报告已定稿」**：

   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "${TARGET_VERSION:?}" --build "${BUILD:?}" \
     set ai_report_finalized true ai_report_finalized_at @now
   ```

   ⛔ 静态-only 由 autopilot 关闭 build，必须写 `ai_report_finalized`；Stop hook 和准发布门均消费该字段。三条终局写入路径的根因见 `rationale.md`。

3. **★【R-4 收尾·仅 `WILL_BROWSER_TEST=0` 时由 autopilot 执行】里程碑通知 #3（AI 执行报告里程碑，绿色 header；完整模板见 0.1bis「#3 AI执行报告通知完整模板」）**——经 `python3 {{AIDP_HOME}}/scripts/notify.py --node '#3' --auto --version "$V" --build "$BUILD" …` 发出——⛔ 不要手工拼发送命令：渠道选择与台账登记已收编进 `--auto`（按 `notify.channels` 依次尝试，见 0.1bis）。退出码 3（未配置任何渠道）= 静默跳过本节点、不算失败。通知正文按该模板填充：执行情况 / 需求功能执行清单 / **测试结论（纯静态：「静态自测、无浏览器测试」+ code-verification-loop 通过率）** / 缺陷统计 / 风险建议 / 下一步导航；「查看完整报告」= `$AI_REPORT_URL`（报告相对路径 / 静态托管链接，直达本次 build 结果页）。**`WILL_BROWSER_TEST=1` 时本步整段跳过** —— #3 改由测试链路在 **#F 之后**发出、且携带**真实浏览器测试结论**（见 aiauto-test Phase 3.7）。

---

## ⛳ 本 Phase 出口：`run_state` 写盘（**硬动作，不可跳过**）

> 单一信源 = `invariants.md`「阶段推进不变式」，此处只给本分片的**具体实参**。
> ⛔ 漏这一步 = 状态机不存在：`next_phase` 恒空 → tick 中途中断后下一 tick 从 Phase 3.0 全量重推；
> `next_sprint` 恒空 → Stop hook 的「中间 yield-tick 豁免」判据取不到值 → 每个中间 tick 都误跑一次
> 收尾门（必 FAIL）并白烧熔断额度。**本 Phase 的实质动作做完、离开本分片之前立即执行**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION}"
# ⛔ 进 3.4 收尾之前先自问 IRON-10：本轮测出的缺陷是否已走完「修复→重部署→铸新 build→复测」。
#    交互式单次（HAS_WAKE_SOURCE=0）同样由本次调用在本轮内跑完——0.3.4bis 那个触发点是 /loop
#    语境、本轮早已跑过，"没有下一 tick" 不是把缺陷连同处置决定交还用户的理由。
#    结构级兜底 = 收尾门 3m（报告 defects[] 有"待复验"却无后继 build 也未冻结 = FAIL）。
$BE --version "$V" run-state "3.3-audit" "3.4-finish" "done" \
  --summary "Phase 3.3 终审完成 + Phase 3.4 完成通知已发" --pending ""
```

