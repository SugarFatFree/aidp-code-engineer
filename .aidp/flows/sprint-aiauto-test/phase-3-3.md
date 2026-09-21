<!-- 二次切分 · phase-3 片3/6：覆盖 3.2.7 AI执行报告完成核验门 / 3.2.8 环境探针档案 / 3.3 baseline更新-->
> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-3-3.md`。理据见同目录 `rationale.md`。

### 3.2.7 ★ AI执行报告完成核验门（入口无关，下沉到测试链路）

> 本门把 AI执行报告完成核验下沉到测试链路：`REPORT_ENABLED=1`（autopilot 驱动）时，AI测试报告落盘后、写 baseline 前，硬校验本 build 的 AI执行报告齐全；缺失则走与 2.5.1 同一自愈交接、绝不静默收尾。`REPORT_ENABLED=0`（standalone，无 `current_build`）→ 本门整段跳过（不期望 AI执行报告）。

```bash
# ★ 跨分片取回本 tick 变量 —— flow 每个分片是**独立的 Bash 调用**，shell 变量不持久；
#   漏这一行会让下方判据读到空串、`${VAR:-默认}` 静默落默认值（恒真/恒假）。
#   真源在 baseline 的（BUILD/DRIVER/DEPLOY_MODE/NOTIFY_ENABLED/LOOP_UNATTENDED…）由脚本自动回落。
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
if [ "$REPORT_ENABLED" = "1" ]; then
  RPT_AI="docs/reports/${TARGET_VERSION}/AI执行报告"; gate_fail=0
  [ -f "$RPT_AI/data/${BUILD}.js" ] || { echo "❌ 完成核验：缺执行数据（data/${BUILD}.js，autopilot 3.1.5 应已写计划态并注册两页）"; gate_fail=1; }
  { [ -f "$RPT_AI/index.html" ] && [ -f "$RPT_AI/plan.html" ] && grep -q "data/${BUILD}.js" "$RPT_AI/index.html" && grep -q "data/${BUILD}.js" "$RPT_AI/plan.html"; } \
    || echo "ℹ️ index.html/plan.html 或 data 注册暂缺/未注册 —— 由 autopilot Phase 3.4 对账补齐 + 校 #/build hash（data 在即非绕过，不阻塞本轮）"
  # ⛔ BE 必须定义在 if **之外**：成功分支（清零 streak）也要用它。定义在 if 内的后果不是报错——
  #   `$BE ... 2>/dev/null || true` 会把 `--version: command not found` 压成 rc=0，于是
  #   handoff_fail_streak 只增不减，三次**成功**交接照样冻成 handoff-exhausted（人工-only）。
  BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
  if [ "$gate_fail" = 1 ]; then
    HANDOFF_NO_LOOP=""   # ★ 透传无人值守（同 2.5.1）：恒带 --unattended，有唤醒源再加 --no-loop
    [ "${LOOP_UNATTENDED:-0}" = "1" ] && { [ "${HAS_WAKE_SOURCE:-0}" = "1" ] && HANDOFF_NO_LOOP=" --unattended --no-loop" || HANDOFF_NO_LOOP=" --unattended"; }
    echo "🔁 执行数据缺失（异常：2.5.1 入口门本应已交接补齐）→ 走与 2.5.1 同一自愈路径：invoke /sprint-autopilot --skip-dev [--unattended] --target $TARGET_VERSION${HANDOFF_NO_LOOP}（[--unattended] 条件透传） 补齐后由它重新委派，勿在缺失下收尾。"
    # ⛔ 绝不裸 exit 1（根因见 rationale.md「裸退让去重门恒不命中」）
    # ★ 记账 → 判阈 → 冻结四件套（交接类，解冻 = 人工）→ 发 #4，一次调用做完。
    #   内含「无唤醒源（HAS_WAKE_SOURCE=0：--once / 无 /loop）当场按达阈处置」——没有下一 tick
    #   叠 streak 时阈值恒不可达、永不冻结，而 exit 0 会被上游读成"跑过了"（宁可早冻，不要静默）。
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
      --phase 3.2.7-handoff --reason handoff-exhausted --streak-key handoff_fail_streak \
      --threshold "${HANDOFF_FAIL_THRESHOLD:-3}" \
      --why "连续多次交接仍拿不回齐全 AI执行报告（执行数据缺失）"
    exit 0   # ★ 已记账 + 已告警 + 已发起交接 → 让位本 tick，不让 /loop 空撞
  fi
  echo "✅ 完成核验：本 build 执行数据存在（结果态由 autopilot 3.4 兜底 finalize/校验）"
  # ★ 与 bump 成对：交接拿回了齐全执行数据即清零，否则"成功也计失败"，三次成功交接照样冻死
  $BE --version "$TARGET_VERSION" del handoff_fail_streak || true
fi
```
> 执行数据缺失 → 记账 `handoff_fail_streak` + 走 2.5.1 自愈交接 + `exit 0` 让位本 tick（**⛔ 不裸 `exit 1`**，理由见上方代码块注释；正常流程下 2.5.1 入口门已保证存在，本门是 tripwire 兜底）；结果态由 autopilot R-3 finalize，本门只校骨架（data + 两页注册）存在——真实 testSummary 由本命令 Phase 3.7 在 #F 后 finalize（含 `#/build` hash 校验），不在本门要求 testSummary 已 finalize。

### 3.2.8 ★ 沉淀「环境探针档案」（本轮**与用例无关、只与环境有关**的发现）

**落点**：`docs/testing/{version}/研发自测/02_环境探针档案.md`（**追加**不覆盖）。与
`01_测试环境与账号.md` 分工：**01 是配置**（地址/账号/连接），**02 是行为事实**（怎么连、
怎么取证、有哪些坑），⛔ 不互抄。收益量级见 `rationale.md`「环境探针档案」。

**只收六类**（每条须带**发现轮次 + 证据**）：驱动通道限制 · 鉴权头形态 · **未登录的真实响应
形态**（可能返 302 跳转体**而非 401**，按 401 判会误判）· 三类取证各自可用性 · 元素定位与
跳转链路、懒加载区块 · 已知需重试项。

⛔ **只记环境、不记用例结论**；⛔ **追加不覆盖**，被后轮推翻的条目**改写为"已失效 + 新结论"**、
不静默删；⛔ **不进硬门**，写失败打印一行继续。
消费方 = 下一轮 **Phase 0.0.5 必读**并注入执行子 Agent。

### 3.3 baseline 更新

> ★★ **先算收敛信号 `CONVERGED`，且必须在所有消费点之前**（baseline streak、3.4 #R/#F、3.7 finalize+#3 全部消费它）。⛔ 绝不能挪进 3.5「切有头提醒」（那段仅远程 mcp 走）。根因见 `rationale.md`。
>
<!-- flowvar-check: allow THIS_ROUND_FAIL_COUNT -->
<!-- flowvar-check: allow THIS_ROUND_NA 上游 gen_report 的 counts.na（不适用，不进通过率分母）-->
<!-- flowvar-check: allow THIS_ROUND_DIRECT_NOEV 上游 gen_report 的 direct_pass_without_evidence 条数 -->
<!-- flowvar-check: allow J 同段内 gen_report --json 的输出，紧邻两行内消费 -->
<!-- flowvar-check: allow AUTO_FIXABLE_FOUND 上方分流两类的语义判定结果，由 Claude 就地代入 -->
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> OPEN_BUGS=$(grep -rE '\|[[:space:]]*待修复[[:space:]]*\|' \
>   "docs/testing/${TARGET_VERSION}/正式用例" "docs/testing/${TARGET_VERSION}/测试验收" "docs/testing/${TARGET_VERSION}/测试执行" "docs/testing/${TARGET_VERSION}/研发自测" 2>/dev/null | wc -l)
> # ★ 统计必须走 SKILL 的 gen_report.py 聚合，⛔ 不得手工累加（rationale.md「统计为何必须走 gen_report.py」）
> GR={{AIDP_HOME}}/skills/auto-test-runner/scripts/gen_report.py
> RD=$(ls -d "docs/reports/${TARGET_VERSION}/AI测试报告/build-${BUILD}"/round-* 2>/dev/null | sort -V | tail -1)
> [ -f "$GR" ] && [ -n "$RD" ] && { J=$(python3 "$GR" "$RD" --json 2>/dev/null)
>   THIS_ROUND_FAIL_COUNT=$(echo "$J"|jq -r '.counts.fail // empty'); THIS_ROUND_NA=$(echo "$J"|jq -r '.counts.na // 0')
>   # ★ 上游 I7：direct 模式的 pass 缺轻量事实（实际值/元素文案/列表计数/产物路径）→ Important、不阻断，
>   #   但**必须让人看见**——否则"跑过且通过"与"跳过后填了 pass"在报告上无从区分。
>   THIS_ROUND_DIRECT_NOEV=$(echo "$J"|jq -r '(.direct_pass_without_evidence // []) | length')
>   # ★ 判据 3「覆盖率 100%」的**可执行落点**：没有它，40 条 block / 0 条 fail 会判「✅ 通过」
>   #   并一路发绿色通知、写 tested、归档 —— 一个只真正跑通两条用例的版本就这样发布出去。
>   # ⛔ 有豁免依据的用例应标 `na`（豁免清单，不进分母），**不是** `block`：block = 该跑而没跑到。
>   THIS_ROUND_BLOCK=$(echo "$J"|jq -r '.counts.block // 0'); }
> # ★ 不计入收敛判据的 block：环境类（走环境冻结/复探路径）与待人工确认项（pending_clarifications 影响用例）。
> #   ⛔ precondition-unmet 仍计入：「有权限造数据却没造」与「真造不出」在枚举上同形，只能逐条复评。
> EXCLUDED_BLOCK=$(python3 - "$RD" "$TARGET_VERSION" <<'PY' 2>/dev/null || echo 0
> import json, sys, glob, os
> sys.path.insert(0, "{{AIDP_HOME}}/skills/auto-test-runner/scripts")
> from gen_report import load_results, is_env_issue
> rd, v = sys.argv[1], sys.argv[2]
> try:
>     bl = json.load(open("memory/.sprint-autopilot-baseline.json", encoding="utf-8"))
> except Exception:
>     bl = {}
> pend = {c for it in ((bl.get("versions") or {}).get(v) or {}).get("pending_clarifications") or []
>         for c in (it.get("affected_cases") or [])}
> n = sum(1 for r in load_results(rd) if r.get("status") == "block" and (
>     (is_env_issue(r) and r.get("block_reason") != "precondition-unmet") or r.get("case_id") in pend))
> print(n)
> PY
> )
> CASE_LEDGER_PENDING=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" get case_ledger_pending --default 0)
> if [ -z "${THIS_ROUND_FAIL_COUNT+x}" ] || [ -z "${THIS_ROUND_FAIL_COUNT}" ]; then echo "⛔ 未从 gen_report.py 聚合到 fail 数 → fail-closed 判未收敛"; CONVERGED=0
> elif [ "${CASE_LEDGER_PENDING:-0}" -gt 0 ]; then echo "⛔ 用例台账仍有 ${CASE_LEDGER_PENDING} 条待执行（case_ledger_pending）→ 不收敛"; CONVERGED=0
> elif [ "$(( ${THIS_ROUND_BLOCK:-1} - ${EXCLUDED_BLOCK:-0} ))" -gt 0 ]; then echo "⛔ 本轮仍有 $(( THIS_ROUND_BLOCK - EXCLUDED_BLOCK )) 条 block（该跑而没跑到；已排除环境类/待确认 ${EXCLUDED_BLOCK:-0} 条）→ 判据 3 覆盖率未达 100%，不收敛"; CONVERGED=0
> elif [ "$THIS_ROUND_FAIL_COUNT" -eq 0 ] && [ "$OPEN_BUGS" -eq 0 ]; then CONVERGED=1; else CONVERGED=0; fi   # 三条同时满足才收敛>
> # ★★ 以下三类状态**必须落盘**（不落盘则跨分片/跨 tick 取空；
> #    后果与实测见 rationale.md「只写散文的状态字段」）。
> # ⬇ AUTO_FIXABLE_FOUND 由 **Claude 按上方「分流两类」结论就地代入** true/false，不是 shell 能算的。
> # ⛔ 下面这行必须由执行体**就地改成字面量 true / false**（同 phase-0-1 的 IS_LOOP_CONTEXT 范式）。
> #   原样执行会把占位串写进 baseline：读侧 `AFP==true` 恒假 → 开发链路永远等一个不会为真的信号 →
> #   测试链路发现的可修复缺陷永不被 /sprint-bugfix 拾取 → 版本永不收敛、最终误冻结为「未收敛」。
> AUTO_FIXABLE_FOUND=false   # ← 有【可自动修复类】缺陷则改为 true
> case "$AUTO_FIXABLE_FOUND" in true|false) ;; *)
>   echo "⛔ AUTO_FIXABLE_FOUND 仍是占位/非法值（$AUTO_FIXABLE_FOUND）——拒绝写入 baseline"; exit 1 ;;
> esac
> python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test CONVERGED "$CONVERGED"
> # ★ na 必须落盘：消费点 3.4 已随分片切分到 phase-3-3b.md，shell 变量跨不过去
> python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test THIS_ROUND_NA "${THIS_ROUND_NA:-0}"
> python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test THIS_ROUND_DIRECT_NOEV "${THIS_ROUND_DIRECT_NOEV:-0}"
> BEV="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version $TARGET_VERSION"
> if [ "$CONVERGED" = "1" ]; then
>   $BEV set auto_fixable_pending false aiauto_test_unconverged_streak 0
>   $BEV del auto_retest_streak auto_fix_in_progress_since >/dev/null 2>&1 || true   # 收敛即清复测计数，不跨修复周期累加
> else
>   $BEV set auto_fixable_pending "$AUTO_FIXABLE_FOUND"
>   $BEV bump aiauto_test_unconverged_streak >/dev/null
> fi
> $BEV bump aiauto_test_round >/dev/null
> # ⛔ 分属两层：status=build 级，aiauto_tested_at=**版本级**（三个读侧全读版本层，见 rationale.md「tested 写错层」）
> [ -n "$BUILD" ] && $BEV --build "$BUILD" set status tested
> # ★ 子集轮不得写 `aiauto_tested_at`：它是「整版已验收」的判据（autopilot Phase 2 准发布收敛门 +
> #   `current-version` 选版都读它）。⛔ 无守卫地无条件写 ⇒「跑了 5 条 P0 全绿」会顶替一次全量验收，
> #   而 `aiauto_subset_tested_at` 全仓零写入者。判据 SELECT_MODE 在本片开头已 eval 回读，只缺这个 if。
> if [ "${SELECT_MODE:-all}" = "all" ]; then
>   $BEV set aiauto_tested_at @now
> else
>   $BEV set aiauto_subset_tested_at @now aiauto_select_mode "$SELECT_MODE"
> fi
> # ★ 三个交接字段必须**在此可执行地落盘** —— 它们有真实消费者（`/sprint-batch` Step 6.5 读
> #   `aiauto_test_result.failed` 回写「问题汇总清单」、读 `aiauto_test_report` 解析失败汇总），
> #   ⛔ 散文与 JSON 示例块不算落盘。后果不是少个字段：失败用例恒取空 → 清单为空 →
> #   `/sprint-bugfix` 扫不到东西 → 自动修复闭环空转 3 轮 → 按 retest-cap 冻结，
> #   而冻结原因与真因（失败用例根本没被登记）毫无关系。
> V="$TARGET_VERSION"
> RPT="docs/reports/${V}/AI测试报告/index.html"; BDJS="docs/reports/${V}/AI测试报告/data/${BUILD}.js"
> BTR="docs/reports/${V}/AI测试报告"     # ⛔ 本分片内自取：shell 变量不跨围栏/分片持久
> ROUND_DIR=$(ls -d "${BTR}/build-${BUILD}"/round-* 2>/dev/null | sort -V | tail -1)
> RES=$(python3 {{AIDP_HOME}}/skills/auto-test-runner/scripts/gen_report.py "$ROUND_DIR" --json 2>/dev/null \
>       | python3 -c "import json,sys;d=json.load(sys.stdin);c=d.get('counts') or {};\
print(json.dumps({'total':d.get('total'),'pass':c.get('pass'),'failed':c.get('fail'),\
'block':c.get('block'),'na':c.get('na'),'elapsed_total_ms':d.get('elapsed_total_ms'),\
'self_heal_actual':d.get('self_heal_actual')},ensure_ascii=False))" 2>/dev/null)
> [ -n "$RES" ] && $BEV set aiauto_test_result "$RES"
> if [ "${REPORT_ENABLED:-0}" = "1" ]; then
>   $BEV set aiauto_test_report "$RPT" aiauto_test_build_data "$BDJS"
> else
>   $BEV set aiauto_test_report null      # 未生成报告，非 autopilot 驱动
> fi
> ```

测试完成后写 baseline。**两种分支按 `REPORT_ENABLED`（Phase 0.2 步骤 2.5）**：
- `REPORT_ENABLED=1`（autopilot 驱动）→ 写 `aiauto_test_report`（HTML index 路径）+ `aiauto_test_build_data`（如下例）。
- `REPORT_ENABLED=0`（直接调用 / 非 autopilot 驱动）→ **`aiauto_test_report` 置 `null`、不写 `aiauto_test_build_data`**（未生成 AI测试报告）；`aiauto_tested_at` / `aiauto_test_result` / `aiauto_test_unconverged_streak` 等测试结果字段照常写（测试已真实执行，结果供终端展示 + `/sprint-bugfix` 拾取）。
- **★ `SELECT_MODE != all`（子集轮，Phase 0.2 步骤 2.5bis 判定）→ 不写 `aiauto_tested_at`**，改写 `aiauto_subset_tested_at` + `aiauto_select_mode`（值 = `smoke`/`regression`）。
  终端摘要与（若产出）报告标题须显著标「子集轮（select=<mode>）」。理据见 `rationale.md`。

```json
{
  "versions": {
    "V0.2.0": {
      ...
      "aiauto_tested_at": "2026-06-10T14:38:00+08:00",
      "aiauto_test_unconverged_streak": 0,
      "aiauto_test_report": "docs/reports/V0.2.0/AI测试报告/index.html",
      "aiauto_test_build_data": "docs/reports/V0.2.0/AI测试报告/data/V0.2.0_build1001.js",
      "aiauto_test_result": {
        "total": 24,
        "passed": 22,
        "failed": 2,
        "runtime_errors": 3,
        "by_role": {"admin": {"total": 12, "passed": 12}, "normal-user": {"total": 12, "passed": 10}}
      }
    }
  }
}
```

> ⏭ **3.4 见 `phase-3-3b.md`**（本片超 20480B 上限后按仓内惯例二次切分，同 `phase-0-6b.md`）。
