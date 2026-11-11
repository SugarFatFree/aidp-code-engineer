<!-- 二次切分 · phase-3 片3/6：覆盖 3.2.7 AI执行报告完成核验门 / 3.2.8 环境探针档案 / 3.3 baseline更新-->

# sprint-aiauto-test · 执行分片 [3/6]（3.2.7 AI 执行报告完成核验门 / 3.2.8 环境探针档案 / 3.3 baseline 回写）
> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **理据**：见同目录 `rationale.md`。

### 3.2.7 ★ AI执行报告完成核验门（入口无关，下沉到测试链路）


> 本门把 AI执行报告完成核验下沉到测试链路：`REPORT_ENABLED=1`（autopilot 驱动）时，AI测试报告落盘后、写 baseline 前，硬校验本 build 的 AI执行报告齐全；缺失则走与 2.5.1 同一自愈交接、绝不静默收尾。`REPORT_ENABLED=0`（standalone，无 `current_build`）→ 本门整段跳过（不期望 AI执行报告）。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
if [ "$REPORT_ENABLED" = "1" ]; then
  RPT_AI="docs/reports/${TARGET_VERSION}/AI执行报告"; gate_fail=0
  [ -f "$RPT_AI/data/${BUILD}.js" ] || { echo "❌ 完成核验：缺执行数据（data/${BUILD}.js，autopilot 3.1.5 应已写计划态并注册两页）"; gate_fail=1; }
  { [ -f "$RPT_AI/index.html" ] && [ -f "$RPT_AI/plan.html" ] && grep -q "data/${BUILD}.js" "$RPT_AI/index.html" && grep -q "data/${BUILD}.js" "$RPT_AI/plan.html"; } \
    || echo "ℹ️ index.html/plan.html 或 data 注册暂缺/未注册 —— 由 autopilot Phase 3.4 对账补齐 + 校 #/build hash（data 在即非绕过，不阻塞本轮）"
  BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
  if [ "$gate_fail" = 1 ]; then
    HANDOFF_NO_LOOP=""   # ★ 透传无人值守（同 2.5.1）：恒带 --unattended，有唤醒源再加 --no-loop
    [ "${LOOP_UNATTENDED:-0}" = "1" ] && { [ "${HAS_WAKE_SOURCE:-0}" = "1" ] && HANDOFF_NO_LOOP=" --unattended --no-loop" || HANDOFF_NO_LOOP=" --unattended"; }
    echo "🔁 执行数据缺失（异常：2.5.1 入口门本应已交接补齐）→ 走与 2.5.1 同一自愈路径：invoke /sprint-autopilot --skip-dev [--unattended] --target $TARGET_VERSION${HANDOFF_NO_LOOP}（[--unattended] 条件透传） 补齐后由它重新委派，勿在缺失下收尾。"
    python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
      --phase 3.2.7-handoff --reason handoff-exhausted --streak-key handoff_fail_streak \
      --threshold "${HANDOFF_FAIL_THRESHOLD:-3}" \
      --why "连续多次交接仍拿不回齐全 AI执行报告（执行数据缺失）"
    exit 0   # ★ 已记账 + 已告警 + 已发起交接 → 让位本 tick，不让 /loop 空撞
  fi
  echo "✅ 完成核验：本 build 执行数据存在（结果态由 autopilot 3.4 兜底 finalize/校验）"
  $BE --version "$TARGET_VERSION" del handoff_fail_streak || true
fi
```
> 执行数据缺失 → 记账 `handoff_fail_streak` + 走 2.5.1 自愈交接 + `exit 0` 让位本 tick（**⛔ 不裸 `exit 1`**，理由见上方代码块注释；正常流程下 2.5.1 入口门已保证存在，本门是 tripwire 兜底）；结果态由 autopilot R-3 finalize，本门只校骨架（data + 两页注册）存在——真实 testSummary 由本命令 Phase 3.7 在 #F 后 finalize（含 `#/build` hash 校验），不在本门要求 testSummary 已 finalize。

### 3.2.8 ★ 沉淀「环境探针档案」（本轮**与用例无关、只与环境有关**的发现）

**落点**：`docs/testing/{version}/研发自测/97_环境探针档案.md`（**追加**不覆盖）。与
`01_测试环境与账号.md` 分工：**01 是配置**（地址/账号/连接），**02 是行为事实**（怎么连、
怎么取证、有哪些坑），⛔ 不互抄。收益量级见 `rationale.md`「环境探针档案」。

**只收六类**（每条须带**发现轮次 + 证据**）：驱动通道限制 · 鉴权头形态 · **未登录的真实响应
形态**（可能返 302 跳转体**而非 401**，按 401 判会误判）· 三类取证各自可用性 · 元素定位与
跳转链路、懒加载区块 · 已知需重试项。

**★ 表头按 7 列产出**（`探针类别 | 上一轮观测事实 | 事实性质 | verified_at | verdict | 来源/轮次 | 本轮处置`）
—— **列定义与两个枚举（`事实性质 ∈ 不变量|绝对值`、`verdict ∈ valid|superseded`）的单一信源 =
`{{AIDP_HOME}}/skills/auto-test-runner/assets/run-context-template.md` 四·补节**，命令端不复述。
⛔ **四列表（只有类别/事实/轮次/证据）会让「已失效」无处表达** —— 下面那条「改写为已失效」就只能
靠删行或塞进备注，而删行恰好违反「追加不覆盖」；`check_probe_archive.py` 的 P1 判 Critical。
⛔ **「绝对值」类事实慎记**：上游数据会在测试窗口内被并发改动，固定条数基线必过期并制造**假性失败**；
稳定成立的是不变量（集合包含关系、差集成员名不变这一类）。

⛔ **只记环境、不记用例结论**；⛔ **追加不覆盖**，被后轮推翻的条目把该行 `verdict` 改成
`superseded`、`本轮处置` 写新结论，**⛔ 不删行**（留痕是下一轮判断该条可信度的依据，
且删行同时违反上面那条「追加不覆盖」）；
⛔ **不进硬门**，写失败打印一行继续。
消费方 = 下一轮 **Phase 0.0.5 必读**并注入执行子 Agent。

**★ 写完即核验（`check_probe_archive.py`，本步是它的调用方）**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
RC_DIR="docs/testing/${TARGET_VERSION:?}/研发自测"
python3 {{AIDP_HOME}}/skills/auto-test-runner/scripts/check_probe_archive.py "$RC_DIR" --json \
  > "$RC_DIR/.probe-archive-check.json" 2>&1 || true
python3 -c "
import json,sys
try: d=json.load(open('$RC_DIR/.probe-archive-check.json'))
except Exception as e: print('ℹ️ 探针档案核验未取到结论（%s）—— 不阻塞' % e); sys.exit(0)
bad=[f for f in (d.get('findings') or []) if f.get('level') != 'Info']
print('🔎 探针档案核验：%d 条（其中须处理 %d）' % (len(d.get('findings') or []), len(bad)))
for f in bad[:5]: print('   ⛔', '[%s] %s' % (f.get('level') or '?', str(f.get('msg') or f)[:140]))
"
```

⛔ **这一步不阻塞本轮**（档案是**下一轮**的输入、不是本轮的产物），但**必须出声**：
档案最危险的失效形态是**失效条目被当成有效结论注入下一轮子 Agent 的 prompt** ——
实测某行写着「主测账号口令失效、三条独立路径同结论」，而档案按契约会注入 prompt
⇒ 子 Agent 收到一个**错误结论**，那正是上一轮 31 条登录态用例集体 `block` 的成因。
核验报出的 `superseded` / 超期未复验条目，**下一轮 Phase 0.0.5 注入前必须过滤掉**。
⚠️ `skipped: true` 只等于「本轮没提供档案」，**⛔ 不等于档案没问题**。

### 3.3 baseline 更新

**新双路先做结构化分流**：主协调者读本 build 的实测证据，将每个失败/阻塞/运行时错误/未关闭缺陷归为 `auto_fixable`（代码根因明确）、`clarification`（产品语义未定）或 `environment`（环境未核验）。可修代码问题先写原问题汇总清单，供 `/sprint-bugfix` 拾取；单测真实 FAIL 仍由 settle 自动登记 BUG。分类写 UTF-8 JSON `memory/.aidp/test-triage-${BUILD}.json`，由下面围栏实际合入报告并传给 settle，不能只写分类散文或先写 AFP。

```json
{"schema":1,"build":"本轮固定 BUILD","commit":"部署完整 SHA","items":[
  {"refs":["defect:BUG-1","case:TC-1"],"category":"auto_fixable","reason":"接口500，日志已定位空指针"},
  {"refs":["case:TC-2"],"category":"clarification","reason":"需求对入口范围未定义","question":"该入口是否本期提供？","affected_cases":["TC-2"],"interim_verdict":"BLOCK"},
  {"refs":["case:TC-3","browser:status"],"category":"environment","reason":"测试账号失效，尚未验证业务行为"}
]}
```

`refs` 必须逐一覆盖 `unit_report_merge.triage_targets(report)` 给出的引用：`case:<id>`、`defect:<id>`、`runtime:<id>`，明细不足时有 `summary:fail/block/skip/openDefects/runtime_errors`，他人未关闭 BUG 为 `summary:openBugs`，显式浏览器未核验/超时为 `browser:status`。一条分类可覆盖多个相关引用；不能重复、漏项或引用其他 build。无问题可省略文件或传空 `items`。emit 返回 `triage_missing` 供补齐；settle 若缺分类会锁内记 `triage_pending=true` / `next_action=classify` 并 exit 2，主协调者必须补分类后重跑本块，不能静默等待下一 tick、发完成卡或冻结。分类不篡改原始 FAIL，也不把环境/澄清当可修代码。环境与澄清分别锁内写 `environment_unverified[]`、`pending_clarifications[]`，均带 `raised_build/commit`；只消费当前 build 的环境记录，历史记录保留取证。

> ★★ **先算收敛信号 `CONVERGED`，且必须在所有消费点之前**（baseline streak、3.4 #R/#F、3.7 finalize+#3 全部消费它）。⛔ 绝不能挪进 3.5「切有头提醒」（那段仅远程 mcp 走）。根因见 `rationale.md`。
>
<!-- flowvar-check: allow THIS_ROUND_FAIL_COUNT -->
<!-- flowvar-check: allow THIS_ROUND_NA 上游 gen_report 的 counts.na（不适用，不进通过率分母）-->
<!-- flowvar-check: allow THIS_ROUND_DIRECT_NOEV 上游 gen_report 的 direct_pass_without_evidence 条数 -->
<!-- flowvar-check: allow J 同段内 gen_report --json 的输出，紧邻两行内消费 -->
<!-- flowvar-check: allow AUTO_FIXABLE_FOUND 上方分流两类的语义判定结果，由 Claude 就地代入 -->
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> REPORT_DATA="docs/reports/$TARGET_VERSION/AI测试报告/data/$BUILD.js"
> JOINT_REPORT=$(python3 - "$REPORT_DATA" <<'JOINT_KIND'
> import sys
> from pathlib import Path
> sys.path.insert(0, "{{AIDP_HOME}}/scripts")
> from unit_report_merge import read_payload
> p = Path(sys.argv[1]); print(int(p.exists() and "unitTests" in read_payload(p)))
> JOINT_KIND
> )
> if [ "$JOINT_REPORT" = "1" ]; then
>   mkdir -p memory/.aidp
>   JOIN_ARGS=()
>   TRIAGE_FILE="memory/.aidp/test-triage-$BUILD.json"
>   if [ -f "$TRIAGE_FILE" ]; then
>     if ! python3 -c 'import json,sys; sys.path.insert(0,sys.argv[3]); from unit_report_merge import read_payload; sys.exit(read_payload(sys.argv[1]).get("failureTriage") != json.load(open(sys.argv[2])))' "$REPORT_DATA" "$TRIAGE_FILE" "{{AIDP_HOME}}/scripts"; then
>     TRIAGE_PATCH="docs/reports/$TARGET_VERSION/AI测试报告/.triage-input-$BUILD.json"
>     python3 -c 'import json,sys; json.dump({"build":sys.argv[1]},open(sys.argv[2],"w"))' "$BUILD" "$TRIAGE_PATCH" || exit 1
>     python3 {{AIDP_HOME}}/scripts/emit-report.py --kind test --patch --version "$TARGET_VERSION" \
>       --build "$BUILD" --data "$TRIAGE_PATCH" --failure-triage "$TRIAGE_FILE" \
>       --templates-root "{{AIDP_HOME}}/templates/reports" --record-baseline "${REPORT_ENABLED:-0}" --json || exit 1
>     fi
>     JOIN_ARGS+=(--triage "$TRIAGE_FILE")
>   fi
>   [ "${REPORT_ENABLED:-0}" = "1" ] || JOIN_ARGS+=(--standalone)
>   python3 {{AIDP_HOME}}/scripts/aiauto_test_join.py settle --root . --version "$TARGET_VERSION" \
>     --build "$BUILD" --report "$REPORT_DATA" "${JOIN_ARGS[@]}" > "memory/.aidp/test-join-$BUILD.json" || exit 1
>   CONVERGED=$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["converged"]))' "memory/.aidp/test-join-$BUILD.json") || exit 1
>   python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test CONVERGED "$CONVERGED"
> else
> OPEN_BUGS=$(grep -rE '\|[[:space:]]*待修复[[:space:]]*\|' \
>   "docs/testing/${TARGET_VERSION}/正式用例" "docs/testing/${TARGET_VERSION}/测试验收" "docs/testing/${TARGET_VERSION}/测试执行" "docs/testing/${TARGET_VERSION}/研发自测" 2>/dev/null | wc -l)
> GR={{AIDP_HOME}}/skills/auto-test-runner/scripts/gen_report.py
> GR_UNTRUSTED=1; THIS_ROUND_FAIL_COUNT=""; THIS_ROUND_BLOCK=0; J=""
> RD=$(ls -d "docs/reports/${TARGET_VERSION}/AI测试报告/build-${BUILD}"/round-* 2>/dev/null | sort -V | tail -1)
> [ -f "$GR" ] && [ -n "$RD" ] && { J=$(python3 "$GR" "$RD" --json 2>/dev/null); GR_EXIT=$?
>   GR_READ_ERR=$(echo "$J"|jq -r '(.read_errors // []) | length' 2>/dev/null); GR_READ_ERR=${GR_READ_ERR:--1}
>   if [ "$GR_EXIT" -ne 0 ] || [ "$GR_READ_ERR" != "0" ]; then GR_UNTRUSTED=1
>     echo "⛔ gen_report.py exit=${GR_EXIT} / read_errors=${GR_READ_ERR}（统计不完整或存在无证据 pass）→ 本轮结论不成立，按未收敛处置"
>   else GR_UNTRUSTED=0; fi
>   THIS_ROUND_FAIL_COUNT=$(echo "$J"|jq -r '.counts.fail // empty'); THIS_ROUND_NA=$(echo "$J"|jq -r '.counts.na // 0')
>   THIS_ROUND_DIRECT_NOEV=$(echo "$J"|jq -r '(.direct_pass_without_evidence // []) | length')
>   THIS_ROUND_BLOCK=$(echo "$J"|jq -r '.counts.block // 0'); }
> # 只消费 gen_report.py --json 的公开字段（defects[].status/block_reason/is_environment_issue），不 import SKILL 内部函数
> PEND_CASES=$(python3 -c 'import json,sys
> try: bl = json.load(open("memory/.sprint-autopilot-baseline.json", encoding="utf-8"))
> except Exception: bl = {}
> print(json.dumps(sorted({c for it in ((bl.get("versions") or {}).get(sys.argv[1]) or {}).get("pending_clarifications") or [] for c in (it.get("affected_cases") or [])})))' "$TARGET_VERSION" 2>/dev/null || echo '[]')
> EXCLUDED_BLOCK=$(echo "$J" | jq -r --argjson p "$PEND_CASES" '[.defects[]? | select(.kind=="case" and .status=="block" and (((.is_environment_issue==true) and (.block_reason!="precondition-unmet")) or (.case_id as $c | $p | index($c) != null)))] | length' 2>/dev/null || echo 0)
> CASE_LEDGER_PENDING=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" get case_ledger_pending --default 0)
> if [ -z "${THIS_ROUND_FAIL_COUNT+x}" ] || [ -z "${THIS_ROUND_FAIL_COUNT}" ]; then echo "⛔ 未从 gen_report.py 聚合到 fail 数 → fail-closed 判未收敛"; CONVERGED=0
> elif [ "${GR_UNTRUSTED:-0}" = "1" ]; then echo "⛔ gen_report.py 非 0 退出或 read_errors 非空 → 统计不可信，不收敛"; CONVERGED=0
> elif [ "${CASE_LEDGER_PENDING:-0}" -gt 0 ]; then echo "⛔ 用例台账仍有 ${CASE_LEDGER_PENDING} 条待执行（case_ledger_pending）→ 不收敛"; CONVERGED=0
> elif [ "$(( ${THIS_ROUND_BLOCK:-1} - ${EXCLUDED_BLOCK:-0} ))" -gt 0 ]; then echo "⛔ 本轮仍有 $(( THIS_ROUND_BLOCK - EXCLUDED_BLOCK )) 条 block（该跑而没跑到；已排除环境类/待确认 ${EXCLUDED_BLOCK:-0} 条）→ 判据 3 覆盖率未达 100%，不收敛"; CONVERGED=0
> elif [ "$THIS_ROUND_FAIL_COUNT" -eq 0 ] && [ "$OPEN_BUGS" -eq 0 ]; then CONVERGED=1; else CONVERGED=0; fi   # 三条同时满足才收敛>
> AUTO_FIXABLE_FOUND=false   # ← 有【可自动修复类】缺陷则改为 true
> case "$AUTO_FIXABLE_FOUND" in true|false) ;; *)
>   echo "⛔ AUTO_FIXABLE_FOUND 仍是占位/非法值（$AUTO_FIXABLE_FOUND）——拒绝写入 baseline"; exit 1 ;;
> esac
> python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test CONVERGED "$CONVERGED"
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
> [ "$GR_UNTRUSTED" = "0" ] && [ -n "$BUILD" ] && $BEV --build "$BUILD" set status tested
> if [ "$GR_UNTRUSTED" != "0" ]; then
>   echo "⛔ 统计不可信 → 不写 tested 状态、验收时间与结果摘要"
> elif [ "${SELECT_MODE:-all}" = "all" ]; then
>   $BEV set aiauto_tested_at @now
> else
>   $BEV set aiauto_subset_tested_at @now aiauto_select_mode "$SELECT_MODE"
> fi
> V="$TARGET_VERSION"
> RPT="docs/reports/${V}/AI测试报告/index.html"; BDJS="docs/reports/${V}/AI测试报告/data/${BUILD}.js"
> if [ "$GR_UNTRUSTED" = "0" ]; then
> RES=$(printf '%s' "$J" | python3 -c "import json,sys;d=json.load(sys.stdin);c=d['counts'];\
print(json.dumps({'total':d['total'],'pass':c['pass'],'failed':c['fail'],\
'block':c['block'],'na':c['na'],'elapsed_total_ms':d.get('elapsed_total_ms'),\
'self_heal_actual':d.get('self_heal_actual'),\
'runtime_errors':d.get('runtime_finding_count')},ensure_ascii=False))" 2>/dev/null)
> [ -n "$RES" ] && $BEV set aiauto_test_result "$RES"
> fi
> if [ "${REPORT_ENABLED:-0}" = "1" ]; then
>   $BEV set aiauto_test_report "$RPT" aiauto_test_build_data "$BDJS"
> else
>   $BEV set aiauto_test_report null      # 未生成报告，非 autopilot 驱动
> fi
> fi  # 新双路 settle / 历史无 unitTests 兼容分支
> ```

**双路报告以 `settle` 的 `converged/overall_status/unit_status/bug_ids` 为唯一判定源**：浏览器通过而单测失败仍不通过，浏览器失败而单测超时仍记录真实失败，任一路 RUNNING 不允许 settle。standalone 带 `--standalone`，写本 build 本地 join 账而不创建版本 baseline。单测失败的 BUG 已由脚本登记，不能再次手工分配。实测分类由 `failureTriage` 校验落盘：可修代码置 AFP，澄清/环境不盲置 AFP；缺分类禁止完成。当前 build 两路成功且无未关闭缺陷/用例欠账时，锁内清 `auto_retest_streak` 与 `auto_fix_in_progress_since`；失败、未核验、待分流均保留。只有本次固定 build 是当前活动 build 时脚本才更新版本级验收字段，不污染新 build；重复同一结果不重新消耗失败计数或重置已消费的 AFP。

以下仅说明**历史无 unitTests 兼容分支**，不得在新双路 settle 后再次执行。两种分支按 `REPORT_ENABLED`：
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
