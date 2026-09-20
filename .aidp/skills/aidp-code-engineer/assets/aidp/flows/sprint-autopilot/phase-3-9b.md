# sprint-autopilot · Phase 3 详情分片 [9b/13]（3.4 收尾 — 内联校验 ① ~ ④ + 收尾动作）

> 本文件是 `phase-3-9.md` 的**二次切分**（前片达 20KB 上限）。前片覆盖「完成核验检测」的
> 根因分诊 + ceremony 闸调用；本片覆盖其后的**内联校验 ① ~ ④** 与收尾动作。
> ⚠️ **权威性**：与前片同级，不得因它是续片而略过任一项。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-9b.md`。

---

   ```bash
   # ★ 本围栏 = 新的 Bash 调用：前片的变量一律不存活，必须重新取回
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
   : "${BASELINE_FILE:=memory/.sprint-autopilot-baseline.json}"
   BE="python3 .aidp/scripts/baseline_edit.py"
   V="${TARGET_VERSION}"; B="${BUILD}"; BN="${BUILD_SEQ}"
   RPT_AI="docs/reports/${V}/AI执行报告"; RPT_TEST="docs/reports/${V}/AI测试报告"
   GATE=".aidp/scripts/autopilot-ceremony-gate.py"
   FAIL=0; ok(){ echo "  ✅ $1"; }; bad(){ echo "  ❌ $1 — $2"; FAIL=1; }
   # 下方内联校验 = 脚本缺失时的兜底 + 始终打印的非阻塞③测试报告提示（与脚本结论一致）
   echo "── ① autopilot 自有产物（缺失必补建后再退出）──"
   { [ -f "$RPT_AI/index.html" ] && [ -f "$RPT_AI/plan.html" ]; } && ok "AI执行报告页面（index.html 结果 + plan.html 计划）" || bad "AI执行报告页面" "回 Phase 3.4 step2 对账：cp 模板 index.html+plan.html+assets"
   { [ -f "$RPT_AI/data/${B}.js" ] && grep -q "data/${B}.js" "$RPT_AI/index.html" && grep -q "data/${B}.js" "$RPT_AI/plan.html"; } \
     && ok "执行数据 data/${B}.js（已注册 index.html + plan.html 两页）" || bad "执行数据" "回 Phase 3.4 step1：写 data/${B}.js → 注册 script 到两页"
   ls "$RPT_AI"/*_AI执行结果.md "$RPT_AI"/AI执行计划_Build*.md 2>/dev/null | grep -q . && bad "检出违规 markdown 报告" "应只产 HTML，删除该 .md" || ok "无违规 markdown 报告"
   # ★ version-auditor 终审 = 强制仪式、无合法降级（--skip-audit 仅 /version 内部开关，不豁免本终审）。
   #   判据必须**带 build**：glob `*.md` 会被 /version 内部审计的 -YYYY-MM-DD.md 顶掉 → 没跑也能过。命名见 phase-3-8.md。
   [ -f "docs/audit/${V}/version-output-audit-${B}.md" ] && ok "version-auditor 终审报告" || bad "version-auditor 终审报告缺失（本 build ${B}）" "回 Phase 3.3 启动 version-auditor 子 Agent 并指定输出 docs/audit/${V}/version-output-audit-${B}.md（强制仪式；严禁以交互式/省时为由跳过，也严禁拿 /version 的 -YYYY-MM-DD.md 顶替）"

   echo "── ② 条件产物（按本轮启用情况，缺失告警）──"
   # 部署：deployment.mode!=none 且未 --skip-deploy → baseline last_deployed_at 本轮应已更新
   # ★ #3 + 报告本体 + 链接 hash 仅在 WILL_BROWSER_TEST=0（autopilot 即 R-4 关闭方）时校；=1 时 R-4 延后到测试链路 #F 后。
   if [ "${WILL_BROWSER_TEST:-0}" = "0" ]; then
     # ★ 从 baseline 台账读：$AI_REPORT_URL 由 phase-3-8.md 设，跨 Bash 块必为空 → 恒 FAIL
     # ⛔ 台账在顶层 `report_deliveries[{build}]`，不在 versions.{V} 下（rationale.md）
     # ⛔ 台账里的键是 `url`，不是 `access_url`（后者只是 emit-report `--json` 的 stdout 字段名）。
RPT_URL=$($BE get "report_deliveries.\"$B\".exec_report.url" --default "")
     RPT_DLV=$($BE get "report_deliveries.\"$B\".exec_report.delivery" --default "")
     # ⛔ 判据与权威脚本 `autopilot-ceremony-gate.py` 3c 一致：报告落本地即合法交付（delivery=local），
     #   只有**无任何交付记录**才是缺陷；有链接时要求带 #/build hash。
     if [ -n "$RPT_URL" ]; then
       echo "$RPT_URL" | grep -q "#/build/${B}\$" && ok "AI执行报告链接带 #/build hash（静态-only，autopilot 已发 #3）" || bad "AI执行报告链接缺 #/build/${B} hash" "补 hash，否则打开是综合首页"
     elif [ -n "$RPT_DLV" ]; then
       ok "AI执行报告已交付（delivery=$RPT_DLV，报告落本地 docs/reports/）"
     else
       bad "AI执行报告无任何交付记录" "须经 emit-report.py 产 SPA 并登记交付台账（严禁只落 markdown）"
     fi
   else
     echo "  ℹ️ R-4（finalize testSummary + 报告本体 + #3）延后到测试链路 /sprint-aiauto-test #F 后，本门不校 #3/链接"
   fi

   echo "── ③ 委派/异步产物（提示，非阻塞）──"
   # ★ 「本版需浏览器实测却无测试链路活跃」这一支**已在闸前根因分诊处理并 exit 0**（见上方），
   #   故本段只剩两态：已有报告 → 清零 streak；其余 → 纯提示。
   #   ⛔ 别把那一支挪回这里：本段位于闸失败分支的 `exit 0` 之后，闸一旦 FAIL 就整段不执行，
   #   而测试链路缺失恰恰是让闸必 FAIL 的那个原因 —— 放这里等于永不生效（详见 rationale.md）。
   if [ -f "$RPT_TEST/index.html" ] && [ -f "$RPT_TEST/data/${B}.js" ]; then
     echo "  ✅ 测试报告（本 build 已有 → aiauto-test 已跑）"
     $BE --version "$V" del test_loop_missing_streak || true
   else
     # ⛔⛔ **这里绝不能清零**（本段最容易写错的一处）：
     #    `test_loop_missing_streak` 是「漏挂第二条 /loop」的**唯一熔断**，累加方在
     #    本片同目录 `phase-2.md`（准发布侧每 tick ++）与 `phase-3-9.md`（dev 完成 tick 首 ++）。
     #    而本分支的语义恰恰是「**报告没生成**」—— 正是该 streak 要计数的那件事。
     #    在这里清零 = 只要该 tick 有开发产出，计数就被抹回 0、3-tick 阈值**永远达不到**，
     #    于是「挂了 autopilot 却没挂测试 loop」这个 usage-guard 反复警告的场景**永无告警**。
     #    清零只属于「报告确已生成」那一支（上面 if 分支）。
     echo "  ℹ️ 测试报告未生成 — 由 /sprint-aiauto-test 异步产出；如尚未挂 /loop 5m /sprint-aiauto-test --unattended 请挂起（#1d 通知已提示）"
   fi
   echo "── ④ 强制仪式合法性自检（非法精简借口 = 违规，见 Phase 3「强制仪式不可精简硬门」）──"
   # 里程碑通知唯一合法降级 = NOTIFY_ENABLED=0（未配置 notify.channels / notify.enabled=false / --no-notify）；否则应发通知集（0.1bis 矩阵）必须已发
   if [ "${NOTIFY_ENABLED:-0}" = "0" ]; then
     ok "里程碑通知合法降级（NOTIFY_ENABLED=0 → 全节点静默跳过）"
   else
     echo "  ⚠️ 通知渠道已配置：确认本 ENTRY_MODE 应发通知集（0.1bis 矩阵）已发；未发 → 置 FAIL 回 0.1bis 节点补发"
   fi
   # ★ 本门只认「唯一合法降级条件」：AI执行报告 / version-auditor 终审 / 应发通知三项，凡以
   #   「交互式 / 省时 / 避免打扰 / 重型仪式 / 用户没明说」为由精简而无对应技术性降级条件 = 违规。
   echo "  ⛔ 自检：本轮若对上述三项做过无合法降级条件的精简 → 立即判违规，补齐后复跑本门"

   if [ "$FAIL" = 1 ]; then
     echo "⛔ autopilot 自有产物或强制仪式有缺失/不合格 → 先就地补建修正并复跑本核验（绝不以『已做精简』收尾）"
     # ⛔ 补建复跑仍不过（结构性不可自愈）→ 走与上方 ceremony-gate 同一套记账，**不裸 exit 1**
     #   （本行上方那句自己就写着"勿裸 exit 1"，此前却真的裸退了）。
     # 记账→判阈→冻结四件套→发 #4 一次做完（⛔ 「发 #4 通知」写成注释 = 停得住但停不响）
     python3 .aidp/scripts/autopilot_fail_handle.py --version "$V" \
       --phase 3.4-ceremony-gate --reason handoff-exhausted \
       --streak-key dev_fail_streak --threshold "${DEV_FAIL_FREEZE_THRESHOLD:-3}" \
       --why "收尾内联核验连续多 tick 未过（3.4-ceremony-gate），缺项清单见上方输出"
     DFS=$($BE --version "$V" get dev_fail_streak --default 0)   # 仅用于下面的 run-state 摘要
     $BE --version "$V" run-state "3.4-finish" "3.4-finish" "" --summary "收尾内联核验未过（连续 $DFS tick）" --pending ""
     exit 0
   fi
   echo "✅ 完成核验通过：autopilot 自有产物 + 强制仪式齐全（或命中唯一合法降级）"
   # ★ 通过即清零 —— 契约写的是「连续失败」，不清零就退化成**终身累计失败**：
   #   版本跑完全部 Sprint 后，phase-3-5 那个唯一的 del 分支不可达（它在
   #   `REMAIN_COUNT -eq 0` 的早退之后），于是收尾门每一次瞬态失败（测试链路本 tick 还没产
   #   报告、CICD 抖动、子 Agent 回传不合契约）都永久累加，跨天攒到 3 次即冻 handoff-exhausted。
   #   而那一段恰恰是 7×24 里停留时间最长的窗口。
   $BE --version "$V" del dev_fail_streak dev_fail_phase || true
   # ⛳ 本 Phase 出口：run_state 写盘（成功分支；失败分支已在上方 ceremony-gate 记账处写过）
   #    ⛔ 漏写 = 状态机不存在（详见 invariants「阶段推进不变式」）。收口即 done。
   $BE --version "$V" run-state "3.4-finish" "done" "done" \
     --summary "Phase 3.4 收尾完成：build=${B} 产物齐全、强制仪式已核验通过" --pending ""
   ```
   - ① 任一 ❌ → 本门 **`exit 1` 硬阻断**（非零退出，不得静默继续）；回对应 Phase 补建/修正（AI执行报告缺失或链接缺 hash），补全后**复跑本门直到全 ✅** 才进 step 5；**不得带 ❌ 退出，也不得在 ❌ 状态下委派 `/sprint-aiauto-test`**。
     - **★ 结构性不可自愈的兜底（防 /loop 无限空转）**：本 tick 内补建复跑**仍** ❌ → **禁止裸 `exit 1`**，按上方代码块归口「失败处置」（`dev_fail_streak` + `dev_fail_phase="3.4-ceremony-gate"`，未达阈记账退本 tick、达阈冻结并发 #4）。**瞬态漏写**仍走"复跑直到全 ✅"、不累 streak。理据见 rationale.md。
   - ② 条件产物 ❌ → 终端告警 + 指引。
   - ③ 测试报告异步：autopilot 完成时通常尚未生成（除非本会话已 delegate 跑测）→ 仅提示挂第二条 /loop，不阻塞退出。

5. 命令退出（不自动 merge master、不自动 tag、不自动推 master —— 严守约定「destructive 动作必须人工」；**feature 分支的开发提交 + 推送已在 Phase 3.2「部署触发前置」完成**，那是开发链路正常收尾、非 destructive 动作，不在此重复）

