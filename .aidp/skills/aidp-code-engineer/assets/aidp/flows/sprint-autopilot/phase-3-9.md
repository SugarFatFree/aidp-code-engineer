# sprint-autopilot · Phase 3 详情分片 [9/13]（3.4 收尾 Step 4+ 完成核验门与收尾动作）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 9/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：3.4 收尾 Step 4+（完成核验门 autopilot-ceremony-gate + 收尾动作）
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-9.md`。理据见同目录 `rationale.md`。

---

4. **★ 完成核验检测（入口无关的收尾门 — 核验各类应产报告/产物是否齐全）**：

   > ★ **入口无关**：本门是 autopilot **任何**执行路径的强制收尾门——`full` 结束前、`test-only` 委派前、失败重入退出前各跑一次（堵"test-only 捷径直跳 aiauto-test 就永不触发核验"的盲区）。
   >
   > 按本轮**实际执行范围**列出期望产物清单，逐项核验并打印 ✅/❌ 表。**autopilot 自有产物（AI执行报告）任一缺失 = 必须经 Phase 3.0 子流程 R 就地补建、复跑通过才退出/委派**；条件产物缺失 → 告警 + 指引；委派/异步产物（测试报告）缺失 → 仅提示、不阻塞不补建。

   ```bash
   : "${BASELINE_FILE:=memory/.sprint-autopilot-baseline.json}"   # ★ 统一变量名 + 兜底默认（未定义时 jq 会读 stdin 静默失败 → streak 不落盘、熔断永不达阈）
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"                   # ★ baseline 唯一加锁写入口（见 invariants「baseline 单一写入口不变式」）
   # ★★ 必须读回本 tick 变量（ENTRY_MODE / PLANNING_DONE / WILL_BROWSER_TEST / FORCE_REPLAN / NO_PLANNING）：
   #    它们全在别的分片派生，而分片间 shell state 不跨 Bash 调用持久；不读回 = 全取空 = 本门恒 FAIL
   #    → 3 tick 后按 handoff-exhausted 冻结版本。详见 rationale.md「收尾门的跨分片变量」。
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   V="${TARGET_VERSION}"; B="${BUILD}"; BN="${BUILD_SEQ}"
   # 从 3.4-finish 续跑也要读版本级决定；无 Git 云部署不等待一条根本不会产生的测试交接。
   VCS_MODE=$(python3 -c 'from pathlib import Path; import sys; sys.path.insert(0, "{{AIDP_HOME}}/scripts"); from vcs import detect_mode; print(detect_mode(Path.cwd()))') || exit 1
   WILL_BROWSER_TEST=$($BE --version "$V" get will_browser_test --default 0)
   DEPLOY_READY=1
   if [ "$VCS_MODE" = none ] && [ "${DEPLOY_MODE:-none}" = cloud ]; then DEPLOY_READY=0; fi
   if [ "$DEPLOY_READY" = 0 ]; then
     WILL_BROWSER_TEST=0
     $BE --version "$V" set will_browser_test 0
     echo "⚠️ vcs_mode=none 且云部署未执行：收尾门按静态-only 收口，不等待浏览器测试或 #1d"
   fi
   RPT_AI="docs/reports/${V}/AI执行报告"; RPT_TEST="docs/reports/${V}/AI测试报告"
   FAIL=0; ok(){ echo "  ✅ $1"; }; bad(){ echo "  ❌ $1 — $2"; FAIL=1; }

   # ★★ 强制仪式确定性收尾门（外部脚本 = 权威）：只认文件产物 + 通知台账，缺失且无合法降级 → exit 1。
   GATE="{{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py"
   # ★ stage 分流：skeleton = 本 build 已委派测试链路 **或** 测试链路真活着（谁是 build 关闭方）；
   #   其余一律 final（理据见 rationale.md，⛔ 别只看 WILL_BROWSER_TEST）。
   # ⛔ 判据里**不带 LOOP_UNATTENDED**："谁关闭这个 build" 与 "有没有人值守" 是两件事。
   #   带上它会留下一格空洞：交互式 `--once` 但机器上第二条 loop 正常挂着时，既拿不到 skeleton、
   #   也触发不了下方的内联补测分诊 —— 于是 final 去校一份要等下个 5min tick 才产的测试交付，
   #   必 FAIL → bump dev_fail_streak → Stop hook 再判 handback 违规 → 白烧 3 次阻止额度。
   DELEGATED=$($BE --version "$V" --build "$B" get aiauto_delegated_at --default "")
   # ⛔ TEST_ALIVE 这个条件不可省（根因见 rationale.md「双 loop 下收尾门为何恒判 final」）
   # ⛔ 别写 `2>/dev/null || echo 0`：`test-loop-alive` 是纯查询、**恒 exit 0**，非零只可能是
   #   gate 脚本自身故障（缺失/语法错/baseline 不可读）。把它 fail-open 成 0 会走进
   #   「测试链路未挂载」分支：每 tick bump test_loop_missing_streak、3 tick 后冻结，并写下一条
   #   **错误诊断**——让人去查一条一直好好挂着的 loop，而真因被 2>/dev/null 一起吞了。
   TEST_ALIVE=$(python3 "$GATE" test-loop-alive --version "$V"); _TLA_RC=$?
   if [ "$_TLA_RC" != "0" ]; then
     echo "⚠️ ceremony-gate test-loop-alive 自身异常（rc=$_TLA_RC）→ 本 tick 不判测试链路存活、"
     echo "   ⛔ 不计入 test_loop_missing_streak（那会把脚本故障误诊成运维少挂了一条 loop），让位本 tick"
     exit 0
   fi
   # ★ 测试链路活跃 = 缺失计数的恢复信号：就地清零（跨复测 build 不累加）
   [ "$TEST_ALIVE" = "1" ] && { $BE --version "$V" del test_loop_missing_streak >/dev/null 2>&1 || true; }
   if [ "${WILL_BROWSER_TEST:-0}" = "1" ] && { [ -n "$DELEGATED" ] || [ "$TEST_ALIVE" = "1" ]; }; then
     GATE_STAGE=skeleton; else GATE_STAGE=final; fi
   # ★★ 根因分诊 —— **必须先于 ceremony 闸**（理据见 rationale.md「测试链路缺失为何不能交给收尾门」）：
   #    本版需浏览器实测（WILL_BROWSER_TEST=1）却检测不到测试链路活跃时，上一行判 final，而 final 的
   #    3c 要的 `report_deliveries.{build}.exec_report` **正是 WILL_BROWSER_TEST=1 时 autopilot 刻意不产、
   #    留给测试链路 R-4 的那一份**（phase-3-8.md「跳过 Step 2/3」）→ 本门**按构造必 FAIL**。
   #    此时 FAIL 是症状不是病因（完整链路与损失见 rationale.md 同名段）。
   # ⛔⛔ 先分「有没有下一 tick」：交互式 --once 无下一 tick，让位=把活退回用户
   #    （根因见 rationale.md「交互式没有下一 tick」）
   HAS_WAKE=$($BE get autopilot.wake_source_this_tick --default 0)
   if [ "${WILL_BROWSER_TEST:-0}" = "1" ] && [ "$TEST_ALIVE" = "0" ] \
      && [ "${HAS_WAKE:-0}" != "1" ] \
      && ! { [ -f "$RPT_TEST/index.html" ] && [ -f "$RPT_TEST/data/${B}.js" ]; }; then
     echo "🔔 交互式单次执行（无唤醒源）且本版需浏览器实测 —— **不让位、不退回用户**："
     echo "   → 就地自调用一次 \`/sprint-aiauto-test --once --unattended\`（见下方「交互式补测」），完成后复跑本门。"
     echo "   ⛔ 严禁在此打印「请挂第二条 loop」并退出：用户已用 --once 表达了执行意图。"
     # ⛔ 必须 `echo` 出来：裸赋值的 shell 变量在围栏结束即消失（下一个围栏 = 新的 Bash 调用），
     #   且**模型看不到它** —— 于是下方「交互式补测」分支结构上不可达：本轮既不补测、也不静态
     #   降级，直接进 ceremony gate 按浏览器档索要测试链路才产的台账 → 必 FAIL → 无唤醒源当场
     #   冻 handoff-exhausted（人工专属、探针一律不解冻）。同围栏的 NEED_STATIC_ONLY_FINALIZE
     #   是 echo 的，本行此前不是——差别就在这里。
     echo "NEED_INLINE_AIAUTO=1"
   fi
   if [ "${WILL_BROWSER_TEST:-0}" = "1" ] && [ "$TEST_ALIVE" = "0" ] \
      && [ "${HAS_WAKE:-0}" = "1" ] \
      && ! { [ -f "$RPT_TEST/index.html" ] && [ -f "$RPT_TEST/data/${B}.js" ]; }; then
     TLM=$($BE --version "$V" bump test_loop_missing_streak)
     echo "⚠️ 本版需浏览器实测但**未检测到测试链路活跃**（连续 ${TLM} tick）——浏览器实测 + AI测试报告 + #F 不会自动发生！"
     echo "   · 7×24 标准挂法：python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install（开发 + 测试两个定时任务）"
     echo "   · 交互式会话：再挂一条 「/loop 5m /sprint-aiauto-test --unattended」"
     if [ "$TLM" -ge "${TEST_LOOP_MISSING_THRESHOLD:-3}" ]; then
       echo "⛔ 连续 ${TLM} tick 测试链路缺失（≥ 阈值 ${TEST_LOOP_MISSING_THRESHOLD:-3}）→ 本 build 按【静态-only 收尾 + 如实标注『浏览器实测未执行(测试链路未挂载)』】关闭，置 needs_human 冻结止损；补挂第二条 loop 后自动解冻重测"
       # 冻结四件套 + #4 + 本地告警台账一次做完（真因是测试链路没挂；测试链路心跳恢复即自动解冻）
       python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command autopilot --version "$V" --build "$B" \
         --freeze-now --phase 3.4-testloop --reason config-missing \
         --why "测试链路连续 ${TLM} tick 未活跃（未装 aidp_scheduler 测试任务 / 未挂 /loop 5m /sprint-aiauto-test --unattended），本 build 静态-only 收尾、浏览器实测未执行"
       # ★ 达阈 → 由本围栏之后的「静态-only 收尾」步骤接手（⛔ 不在此 exit，见下）
       python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot \
         WILL_BROWSER_TEST 0 >/dev/null 2>&1 || true
       # ⛔⛔ **tick 命名空间不是收尾门读的那个真源**：`autopilot-ceremony-gate.py` 的
       #    「显式落盘值优先」读的是 **baseline `versions.{V}.will_browser_test`**，
       #    其唯一写方在 phase-3-8（写 1）。只置 tick flag 而不落版本级 → 降级完复跑 gate
       #    **仍按浏览器档**索要 AI测试报告 SPA + test 交付台账 + #F → 必 FAIL →
       #    bump dev_fail_streak → 3 tick → `handoff-exhausted`（人工专属）→ 永冻。
       #    静态-only 降级必须两处都落，缺一即"降级了个寂寞"。
       $BE --version "$V" set will_browser_test 0 >/dev/null 2>&1 || true
       echo "NEED_STATIC_ONLY_FINALIZE=1"
     else
       exit 0   # 未达阈：已记账 + 已告警，让位本 tick
     fi
   else
     :
   fi
   ```

   **★ 达阈后的静态-only 收尾（上面打印 `NEED_STATIC_ONLY_FINALIZE=1` 时执行，⛔ 不得跳过）**：
   只置 `needs_human` 就 `exit` = **报告永停骨架、#3 永不发**，与本分支承诺完全相反（它自己
   写的就是「静态-only 收尾 + 如实标注」）。故按顺序做完三件事，**任一未做完不得离开本步**：

   1. 按 `phase-3-8.md`「收尾 Step 1.1 → 2 → 3」**实跑**（单一信源在那边）——finalize
      `data/${BUILD}.js` 的 `testSummary` + 定稿报告与交付登记 + 发 #3。
   2. `testSummary` 须**如实**标『浏览器实测未执行(测试链路未挂载)』，
      ⛔ 不填 `0/0/0`、⛔ 不标「已测 / 通过」（「不适用→通过」是本仓明令禁止的伪装形态）。
   3. `WILL_BROWSER_TEST` 已在上面落盘为 0；收尾完成后**从本门开头复跑一次**成闭环
      （此时 `WILL_BROWSER_TEST=0`，根因分诊那一支不再命中）。

   **★ 交互式补测（`NEED_INLINE_AIAUTO=1` 时执行，⛔ 不得跳过）**：`Agent({run_in_background:false})`
   派子 Agent 跑 **`/sprint-aiauto-test --once --unattended`**（⛔ 斜杠命令不能进 bash 围栏，必 `127`；
   ⛔ `--unattended` 不可省：**子 Agent 答不了 `AskUserQuestion`**，裸 `--once` 会在首个交互门挂死——
   这与"用户在不在场"无关，取决于**谁在执行**），
   只回传 `{"tested":bool,"pass_rate":N,"reason":"…"}`；回来后**从本门开头复跑一次**。
   派不出 / `tested:false` → 才降级静态-only 收尾并**把原因打印给用户**（见 rationale.md）。

   ```bash
   # ★ 新围栏 = 新 Bash 调用，上一个围栏的变量一律不存活，必须重新取回
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   : "${BASELINE_FILE:=memory/.sprint-autopilot-baseline.json}"
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
   V="${TARGET_VERSION}"; B="${BUILD}"; BN="${BUILD_SEQ}"
   # 同一版本级真源；不能在新 Bash 围栏重新拾取旧 tick 的 WILL_BROWSER_TEST=1。
   WILL_BROWSER_TEST=$($BE --version "$V" get will_browser_test --default 0)
   GATE="${GATE:-{{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py}"
   # ⛔⛔ **GATE_STAGE 必须在本围栏【重新推导】**——它在上一个围栏（本片 stage 分流处）赋值，
   #    而本围栏开头那行注释说得很清楚：新围栏 = 新 Bash 调用、上个围栏的变量一律不存活。
   #    它也**不在** `autopilot_tick_flags.py --shell` 的供给清单里（实测命中 0）。
   #    漏取的后果不是"用了个默认值"：`--stage ""` 命中 argparse 的 choices 校验 → **rc=2**（实测），
   #    下方 `|| { bump dev_fail_streak … }` **每 tick 执行** → 3 tick 达阈 →
   #    `handoff-exhausted`（`_HUMAN_ONLY`，探针一律不解冻）→ **永久待人工**，
   #    而日志只会说"收尾门未过"、不会显示真因是参数为空。
   DELEGATED=$($BE --version "$V" --build "$B" get aiauto_delegated_at --default "")
   # ⛔ 别写 `2>/dev/null || echo 0`：`test-loop-alive` 是纯查询、**恒 exit 0**，非零只可能是
   #   gate 脚本自身故障（缺失/语法错/baseline 不可读）。把它 fail-open 成 0 会走进
   #   「测试链路未挂载」分支：每 tick bump test_loop_missing_streak、3 tick 后冻结，并写下一条
   #   **错误诊断**——让人去查一条一直好好挂着的 loop，而真因被 2>/dev/null 一起吞了。
   TEST_ALIVE=$(python3 "$GATE" test-loop-alive --version "$V"); _TLA_RC=$?
   if [ "$_TLA_RC" != "0" ]; then
     echo "⚠️ ceremony-gate test-loop-alive 自身异常（rc=$_TLA_RC）→ 本 tick 不判测试链路存活、"
     echo "   ⛔ 不计入 test_loop_missing_streak（那会把脚本故障误诊成运维少挂了一条 loop），让位本 tick"
     exit 0
   fi
   if [ "${WILL_BROWSER_TEST:-0}" = "1" ] && { [ -n "$DELEGATED" ] || [ "$TEST_ALIVE" = "1" ]; }; then
     GATE_STAGE=skeleton; else GATE_STAGE=final; fi
   RPT_AI="docs/reports/${V}/AI执行报告"; RPT_TEST="docs/reports/${V}/AI测试报告"
   GATE="{{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py"
   FAIL=0; ok(){ echo "  ✅ $1"; }; bad(){ echo "  ❌ $1 — $2"; FAIL=1; }
   # ★ EXPECT_CARDS 只放「本门运行时 autopilot 自己**确实应该已发出**的里程碑通知」，判据须与各节点实际发送条件
   #   **逐条同源**（通知节点矩阵单一信源 = phase-0-5.md 0.1bis；理据见 rationale.md「收尾门期望集」）：
   #     · 测试链路必发节点 #D/#R/#F 归 aiauto-test 的 final 门校（其期望集须与此处逐字对齐）；#3 由 build 关闭方发、#G 是条件节点，两侧均不无条件期望 → 浏览器路径下本门都不期望；
   #     · 条件节点：#1 仅 `PLANNING_DONE=0`/`--force-replan`；#1d 仅真会部署；#2 仅非 incremental；
   #     · #1b 规划完成**恒发**（含「复用已有规划」）→ 恒期望、不随 PLANNING_DONE 变；test-only → 整体留空。
   if [ "${ENTRY_MODE}" = "test-only" ]; then
     EXPECT_CARDS=""
   else
     EXPECT_CARDS="#0"                                                     # #0 恒发（版本扫描启动，铸 build 前，登记时无 --build）
     # 规划【开始】通知：只有本轮真的跑了规划才期望（规划【完成】通知 #1b 恒发，见下行）
     if [ "${PLANNING_DONE:-0}" = "0" ] || [ "${FORCE_REPLAN:-0}" = "1" ]; then
       EXPECT_CARDS="${EXPECT_CARDS},#1"
     fi
     EXPECT_CARDS="${EXPECT_CARDS},#1b,#1c"                                # #1b 规划完成 / #1c 开发开始，均恒发
     # 部署通知：仅真的会触发部署时才期望（等价 WILL_BROWSER_TEST=1）
     [ "${WILL_BROWSER_TEST:-0}" = "1" ] && EXPECT_CARDS="${EXPECT_CARDS},#1d"
     # Sprint 关闭通知：增量路径无 Sprint，不期望
     [ "${ENTRY_MODE:-full}" != "incremental" ] && EXPECT_CARDS="${EXPECT_CARDS},#2"
     # 静态-only 时 autopilot 自己是 build 关闭方、自己发 #3
     [ "${WILL_BROWSER_TEST:-0}" = "0" ] && EXPECT_CARDS="${EXPECT_CARDS},#3"
   fi
   echo "🗂️ 本轮期望通知集：${EXPECT_CARDS:-(空，test-only 交测试链路校)}（ENTRY_MODE=${ENTRY_MODE:-full} PLANNING_DONE=${PLANNING_DONE:-0} WILL_BROWSER_TEST=${WILL_BROWSER_TEST:-0}）"
   # ⛔ **脚本非零 → 先记账再判，绝不裸 `exit 1`**（本片末尾「勿裸 exit 1 让 /loop 每 tick 重撞」的落地）：
   #    先按下方 ① 清单就地补建、复跑本门；**仍不过**才记账：bump dev_fail_streak →
   #    未达阈只记账 + exit 0 让位本 tick；达阈按「冻结字段写入契约」冻结本版。
   # ⛔ 同样勿加 `--will-browser-test` / `--no-planning`（曾有、已删；理由同上，见 rationale.md）
   # ⛔ 勿加 `--entry-mode`（曾有、已删，删是修复）：理由见 rationale.md「--entry-mode 为何不传」。
   if [ -f "$GATE" ]; then
     python3 "$GATE" check --version "$V" --build "$B" --stage "$GATE_STAGE" \
       --notify "${NOTIFY_ENABLED:-0}" \
       --baseline "$BASELINE_FILE" \
       ${EXPECT_CARDS:+--expect-cards "$EXPECT_CARDS"}; GRC=$?
     # ⛔ **必须按码分流，不能用 `||` 接住任何非零**：`rc=2` 是「缺 --build，一项都没校验」，
     #   把它当仪式缺失记进 dev_fail_streak，3 tick 后就钉成 handoff-exhausted（人工专属、
     #   永久待人工），而日志只会说「收尾门未过」——真因是参数没供上，一个字都看不到。
     if [ "$GRC" = "2" ]; then
       echo "⛔ 收尾门入参错（rc=2，多半是 \$B 为空）→ 本 tick 不记 streak、不冻结；补齐 --build 后复跑"
       exit 0
     fi
     [ "$GRC" != "0" ] && {   # ★ P0-2：final 阶段校规划产物存在性（full/incremental 缺六类即 FAIL）
       # 记账→判阈（内含「无唤醒源即当场达阈」）→冻结四件套→发 #4，一次调用做完。
       # ⛔ 「发 #4 通知」写成注释 = 停得住但停不响：零通知，与还在正常跑完全同形。
       python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "$V" \
         --phase 3.4-ceremony-gate --reason handoff-exhausted \
         --streak-key dev_fail_streak --threshold "${DEV_FAIL_FREEZE_THRESHOLD:-3}" \
         --why "收尾 ceremony 闸连续多 tick 未过（3.4-ceremony-gate），结构性不可自愈；缺项清单见 gate 输出"
       DFS=$($BE --version "$V" get dev_fail_streak --default 0)   # 仅用于下面的 run-state 摘要
       $BE --version "$V" run-state "3.4-finish" "3.4-finish" "" \
         --summary "收尾 ceremony 闸未过（连续 $DFS tick）" --pending ""   # ⛔ 不写本门自己：3k 会因它死锁，见 rationale.md
       exit 0   # ⛔ 不是 exit 1：已记账 + 已告警 + 已写 run_state，让位本 tick 而非让 /loop 空撞
     }
   else
     echo "⚠️ 缺 $GATE（重跑脚手架补全）→ 回退下方内联校验（弱于脚本，仅兜底）"
   fi
   ```

> ⬇️ **内联校验（① ~ ④）+ 收尾动作已外置到 `phase-3-9b.md`**（本片达 20KB 上限，按本目录二次切分约定拆）。
> **进入下一步前必须 `Read` 它**：那是脚本缺失时的兜底 + 始终打印的非阻塞③提示 + 强制仪式合法性自检，
> 不是可选附录。⛔ 别只跑上面的 ceremony 闸就收工。