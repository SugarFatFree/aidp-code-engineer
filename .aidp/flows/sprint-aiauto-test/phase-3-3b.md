<!-- 二次切分 · phase-3 片3b/6：覆盖 3.4 里程碑通知 #R（每轮结束）+ #F（最终完成）-->
<!-- flowvar-check: allow THIS_ROUND_DIRECT_NOEV 由 phase-3-3 落盘、本片经 tick_flags --shell 回读 -->
<!-- flowvar-check: allow THIS_ROUND_NA 由 phase-3-3 落盘、本片经 autopilot_tick_flags --shell 回读 -->
# sprint-aiauto-test · 执行分片 [3b/6]（3.4 里程碑通知 #R（每轮结束）+ #F（最终完成））

> 逐项执行本片，硬门不得省略；随脚手架同步，理据见 `rationale.md`。

> 每个 Bash 调用先用 tick_flags 取回本轮固定状态；不能沿用上一分片 shell 变量。

---

### 3.4 ★ 里程碑通知 #R（每轮测试结束）+ #F（最终测试完成）（见 sprint-autopilot 0.1bis）

> `python3 {{AIDP_HOME}}/scripts/notify.py --auto` 使用配置渠道，通知含项目名、工作目录、完成时间。`NOTIFY_ENABLED=0` 或退出码 3 时静默跳过，不弹问询。`ROUND` 读 baseline `versions.{V}.aiauto_test_round` 并 +1 回写（一次调用一轮）；公共模板见 sprint-autopilot 0.1bis。

本地/上传/通知独立记账；`--report-kind test` 自动选台账 URL 或附权限说明的仓库路径。仅补交付走 `{{AIDP_HOME}}/templates/reports/README.md`「只补交付」shell（含上传失败措辞）；不重测、不改 frozen 事实、不 ZIP/附件外发，FAIL 亦可交付。

**新双路优先分支**：data 含 `unitTests` 时执行下块，再到 3.5/3.7，跳过历史冻结协议。PASS 绿色、FAIL 红色、UNVERIFIED/TIMEOUT 橙色；RUNNING/缺分类不发完成卡。standalone 同样附报告链接。单测 BUG 已由 3.3 settle 幂等登记；环境/超时不登记 BUG、不累计失败 streak。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
REPORT_DATA="docs/reports/$TARGET_VERSION/AI测试报告/data/$BUILD.js"
JOINT_REPORT=$(python3 - "$REPORT_DATA" <<'JOINT_NOTICE'
import sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from unit_report_merge import read_payload
p = Path(sys.argv[1]); print(int(p.exists() and "unitTests" in read_payload(p)))
JOINT_NOTICE
)
if [ "$JOINT_REPORT" = "1" ]; then
  python3 - "$REPORT_DATA" "$TARGET_VERSION" "$BUILD" "${NOTIFY_ENABLED:-1}" <<'JOINT_CARDS'
import json, subprocess, sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from unit_report_merge import read_payload, report_ready, overall_status, browser_status, triage_state, unit_has_failure
p = read_payload(sys.argv[1]); v, b, notify = sys.argv[2:]
if not report_ready(p):
    raise SystemExit("两路仍未完成，不发 #R/#F")
routing = triage_state(p)
if routing["status"] != "COMPLETE":
    raise SystemExit("缺陷待分流，返回 3.3 补齐分类，不发完成卡：" + ", ".join(routing["missing"]))
status = overall_status(p); unit = p["unitTests"]
color = "green" if status == "PASS" else "red" if status == "FAIL" else "orange"
counts = unit.get("counts") or {}
unit_counts = " / ".join(f"{k}={counts[k] if counts.get(k) is not None else '未提供'}" for k in ("passed","failed","skipped"))
section = (f"全量实测：{browser_status(p)}；全量单测：{unit['status']}（{unit_counts}）。"
           f"总体：{status}。单测原因：{unit.get('reason','')}。"
           + ("已分类的代码缺陷交自动修复后新 build 两路重跑。" if routing["auto_fixable"] or unit_has_failure(unit)
              else "待澄清/补核验，不能通过。" if status != "PASS" else "两路共同通过。"))
for item in routing["clarifications"]:
    section += f" 待确认：{item['question']}；影响：{','.join(item['affected_cases'])}；暂行：{item['interim_verdict']}。"
for item in routing["environment"]:
    section += f" 环境未核验：{item['reason']}；引用：{','.join(item['refs'])}。"
if notify == "1":
    for node in ("#R", "#F"):
        rc = subprocess.run([sys.executable,"{{AIDP_HOME}}/scripts/notify.py","--auto","--node",node,
            "--header-color",color,"--title",f"AI 测试汇总：{status}","--version",v,"--build",b,
            "--section",section,"--link-text","查看双路测试报告","--report-kind","test"]).returncode
        if rc not in (0,3): print(f"通知 {node} 未送达，保留待重试记录", file=sys.stderr)
JOINT_CARDS
  [ "$?" -eq 0 ] || exit 1
fi
```

下方 #R/#F、冻结协议和分类追加块**仅供无 unitTests 的历史恢复**。新双路以 3.3 `failureTriage` 为准，settle 已锁内写 AFP / pending_clarifications / environment_unverified；缺分类回 3.3，不能跳过分流。

**#R 每轮测试结束必发**：header 全绿蓝色、有失败/运行时错误橙色。公共字段外须含版本、轮次、通过/失败/阻塞/忽略/**不适用**（不并入 pass）、`THIS_ROUND_DIRECT_NOEV`>0 时的无依据 direct pass 条数、新缺陷数、收敛状态和报告路径。以下首行是 `--title`（按 0.1bis 必带项目中文名），其余为正文：

- 全通过**且无运行时错误**：
  ```
  ✅ {项目名称} {TARGET_VERSION}_Build{N} · 第 {ROUND} 轮测试完成      ← 标题
  套件：smoke（通过 24 / 失败 0 / 阻塞 0 / 忽略 0 / 不适用 0）/ 运行时错误：0
  本轮新发现缺陷：0　收敛：✅ 是（→ 触发 #F 最终通知）
  报告：docs/reports/{V}/AI测试报告/index.html（{BUILD} 子页）
  ```
- **用例全通过但有运行时错误**（不算绿灯）：
  ```
  ⚠️ {项目名称} {TARGET_VERSION}_Build{N} · 第 {ROUND} 轮：用例全通过(24/24) 但捕获 3 个运行时错误（已记 bug）      ← 标题
  通过 24 / 失败 0 / 阻塞 0 / 忽略 0 / 不适用 0　本轮新发现缺陷：3　收敛：❌ 否
  📌 下一步：外层 /sprint-bugfix 修复后重新部署 → 下一轮重测
  ```
- 有失败（可能同时有运行时错误）：
  ```
  ⚠️ {项目名称} {TARGET_VERSION}_Build{N} · 第 {ROUND} 轮：部分失败 22/24 + 运行时错误 3      ← 标题
  通过 22 / 失败 2 / 阻塞 0 / 忽略 0 / 不适用 0　本轮新发现缺陷：3+2　收敛：❌ 否
  报告：docs/reports/{V}/AI测试报告/index.html（{BUILD} 子页，失败用例截图含 -fail 后缀）
  📌 下一步：外层 /sprint-bugfix 修复后重新部署 → 下一轮重测
  ```

**★ 连续未收敛护栏 + 冻结级熔断**：每轮末更新 `versions.{V}.aiauto_test_unconverged_streak`——收敛清零、未收敛 +1。
- **告警级**（`≥ aiauto_unconverged_alert_threshold`，默认 5；由本段散文判定）：#R 之外额外发一条 **#4**（红色 + @用户），列出反复出现的失败用例 / 待修复 bug 清单。不停 loop、每轮仍重测。
- **冻结级**（`≥ aiauto_unconverged_freeze_threshold`，默认 10；★ 下方围栏**真判**这个阈值，不是散文）：**冻结前必须先做仪式产物收口**，四步顺序不可颠倒——
  ① 经 `emit-report.py --kind exec`（同 3.7 R-4，仅结论为不通过）把本 build 的 AI执行报告 finalize 为「不通过·未收敛」终态：`testSummary` **从同 build 的 AI测试报告 summary 派生**（`gen_report.py --json`，⛔ 不手填），口径与 3.7 R-4 相同：`{total,pass,fail,block,skip,na,passRate,coverage,browserTested:true, unconverged:true}`（**`passRate` 分母 = `total-na`**；字段映射同 `phase-3-5.md` Step 1：`total` ← `.total`、四态 ← `.counts.*`、`skip` ← `.counts.skip // 0`、`passRate` ← `.pass_rate`、`coverage` ← `null`——`counts` 本身无 `total/skip/passRate` 键）、`overview.statusKind=fail`、`testPassRate`=实测通过率；
  ② 发终态 **#F**（红色·不通过，标注「连续 {streak} 轮未收敛，判定不通过、暂停本版自动重测待人工介入」）+ **#3**（携不通过结论 + 报告路径）；
  ③ 校 ①② 是否真落地——**⛔ 必传 `--expect-cards`**（不传即落进退化分支，「一整轮测试期通知零推送」照样 PASS，
     而本步恰恰承诺「绝不冻结仪式产物残缺的 build」）；⛔ 变量用真值、不留 `{V}`/`{BUILD}` 字面占位：
     ```bash
     eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
     python3 {{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py check \
       --version "$TARGET_VERSION" --build "$BUILD" --stage final --will-browser-test 1 \
       --notify "${NOTIFY_ENABLED:-1}" --expect-cards "#D,#R,#F" \
       --baseline memory/.sprint-autopilot-baseline.json
     ```
     **FAIL → 回 ①/② 补齐、复跑本门**，绝不冻结仪式产物残缺的 build；连续 FAIL 经专属计数熔断（未达阈只记账让位；达阈按交接类冻结，#4 + 本地告警台账）：
     ```bash
     eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
     python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --build "${BUILD:-}" \
       --phase 3.3-freeze-ceremony --reason handoff-exhausted \
       --streak-key aiauto_gate_fail_streak --threshold 3 \
       --why "未收敛冻结前的仪式收口门（#F/#3/执行报告终态）连续未过，无法安全冻结"
     exit 0
     ```
     通过后清零：`python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del aiauto_gate_fail_streak`；
  ④ 才置版本级 `needs_human=true` + `aiauto_frozen_at=@now` + `freeze_reason=unconverged` + **顶层 `aiauto_blocked_reason=frozen:unconverged@{V}`**（四件套，缺第 4 件开发链路会误判测试链路健康、双链路互等），**并同时置本 build 的 `ai_report_finalized=true` + `ai_report_finalized_at=@now`**，发最后一条 #4 后冻结本版：后续 `/loop` 跳过该版本（不再重测、不再刷 #4）。
  ①②③ 均完成才允许历史分支定稿；具体写入见下块。

  ④ 的可执行落点（③ 的 ceremony-gate 返回 0 之后才跑）：

  ```bash
  set -e
  BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell --command aiauto-test)"
  V="${TARGET_VERSION:?}"; B="${BUILD:?}"
  JOINT_REPORT=$(python3 - "$V" "$B" <<'NO_JOINT_FREEZE'
import sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from unit_report_merge import read_payload
v,b=sys.argv[1:]; p=Path(f"docs/reports/{v}/AI测试报告/data/{b}.js")
print(int(p.exists() and "unitTests" in read_payload(p)))
NO_JOINT_FREEZE
)
  if [ "$JOINT_REPORT" = "1" ]; then
    echo "双路终态走 3.7 联合收尾，不执行历史未收敛冻结四件套"
    exit 0
  fi
  STREAK=$($BE --version "$V" get aiauto_test_unconverged_streak --default 0)
  FREEZE_AT=$($BE --version "$V" get aiauto_unconverged_freeze_threshold --default 10)
  if [ "$STREAK" -lt "$FREEZE_AT" ]; then
    python3 {{AIDP_HOME}}/scripts/notify.py --node "#R" --auto --header-color orange \
      --title "AI 测试未收敛：第 $STREAK 轮" --version "$V" --build "$B" \
      --section "第 $STREAK 轮未收敛（冻结阈值 $FREEZE_AT）；下一 tick 继续重测。" || true
    echo "⚠️ 未收敛第 $STREAK 轮：#R 已尝试发送；不冻结，下一 tick 继续重测"
    exit 0
  fi
  $BE --version "$V" --build "$B" set ai_report_finalized true ai_report_finalized_at @now
  VCS_MODE=$(python3 -c 'import sys; from pathlib import Path; sys.path.insert(0, "{{AIDP_HOME}}/scripts"); from vcs import detect_mode; print(detect_mode(Path.cwd()))') || exit 1
  FROZEN_HEAD=""
  if [ "$VCS_MODE" = "git" ]; then
    FROZEN_HEAD="$(git rev-parse HEAD 2>/dev/null)" || exit 1
  elif [ "$VCS_MODE" != "none" ]; then
    echo "⛔ 无法判定 VCS 模式，停止冻结写入" >&2; exit 1
  fi
  $BE --version "$V" set needs_human true aiauto_frozen_at @now freeze_reason unconverged \
    unconverged_frozen_head "$FROZEN_HEAD" \
    needs_human_reason "连续 $STREAK 轮未收敛，判定不通过、暂停本版自动重测待人工介入"
  $BE set aiauto_blocked_reason "frozen:unconverged@$V"
  python3 {{AIDP_HOME}}/scripts/notify.py --node "#4" --auto --header-color red \
    --title "AI 测试受阻：连续未收敛" --version "$V" --build "${B:-?}" \
    --section "连续 $STREAK 轮未收敛，判定不通过、已冻结本版待人工；本 build 的 AI执行报告已定稿。" || true
  echo "🧊 已冻结 $V（unconverged，streak=$STREAK）；本 build $B 的 AI执行报告已定稿、不可再被覆盖"
  ```

解冻靠 `last_deployed_at` 刷新（外层修复后新部署）或人工 `retry`/`--reset-baseline`；收敛会自动清零 streak 并解冻。

**★ CONVERGED=0 缺陷分流（item 3 — 自动修复复测闭环的判定源，与报告不可变铁律配套）**：本轮未收敛（有失败/待修 bug）时，把每条失败/缺陷按**可自动化修复程度**二分类，写 baseline 供 autopilot 消费。

> ⛔ **分流第 0 步：先摘出环境阻塞项，不计产品缺陷**。直接消费 `auto-test-runner` 的 `gen_report.py::is_env_issue`（显式布尔值优先于枚举推断，不能另写 OR 判据）；合法枚举以 `scripts/check_result.py::BLOCK_REASON_ENUM` 为准。收敛排除严格沿用 3.3：先经 `split_entries` 剔除巡检项，`precondition-unmet` 不自动豁免、须逐条复评。
> 漏做这步的后果见 `rationale.md`「环境阻塞项不进缺陷分流」。
> 环境阻塞项的正确去向：在报告「测试概况」段如实标注为环境阻塞（不计入产品缺陷），并按 Phase 0.2「冻结字段写入契约」走对应的环境类冻结/复探路径。

分流两类：

> ⛔⛔ **分流【输入】= 本轮全部缺陷，不是"失败用例"**（用例外捕获的 console error / 未捕获异常 /
> 接口非预期状态码、观察到但未被断言的缺陷，一律进本分流）。**`fail=0` 不是跳过理由**；
> **来源与严重度都不改变它走不走闭环**。理据见 rationale.md「分流输入为何是全部缺陷」。
> ⛔ **二分类判据 = `/sprint-bugfix`「缺陷处置默认决策纪律」（单一信源，约定 21 不复述）**：对每条缺陷先问「不做这个修复，当前行为是不是错的？」——是即【可自动修复类】。
- **可自动修复类**（代码缺陷，根因明确、无语义分歧：如接口 500 / 字段映射错 / 空指针 / 校验缺失）→ 回写「问题汇总清单」（`R-`/`C-` 前缀，供`/sprint-bugfix` 拾取），并按下方落盘块置 `auto_fixable_pending=true`——**autopilot 检测到即自动 `/sprint-bugfix` → 重部署 → 铸新 build 复测**（见 sprint-autopilot「测试失败自动修复复测闭环」；**自动复测上限 3 轮/人工介入周期，达上限转人工手动修复、autopilot 检测到人工修复（新提交/新部署）即自动解冻并铸新 build 复测**）。**注意：复测是【新 build】**（本 build 一旦 R-4 finalize 即冻结，报告不可变铁律——绝不在旧 build 上重测重写）。
- **需人工确认类**（语义/范围问题，根因是"该不该这样"而非"写错了"——如入口是否该存在、字段是否本期需求）→ **不阻塞本轮**：记 baseline `versions.{V}.pending_clarifications[]`（`{question, affected_cases[], interim_verdict, raised_build, at}`），对应用例在本 build 报告记 **BLOCK/待确认**，**本轮照常 finalize 出报告**（结论按实测：有真失败=不通过、仅待确认=部分通过/带待确认标注）。#F 通知**列出待确认项清单**（问题 + 影响用例 + 暂行判定）。用户确认后由 `/sprint-autopilot --once` 铸**新 build** 复测，**严禁回头改旧 build 报告**。
- **纯待确认、无真实代码失败**时：本轮即可 finalize（待确认项不算"未收敛需自动修"，`auto_fixable_pending` 不置真），避免为纯产品分歧空跑自动修复。

> `pending_clarifications[]` 用下方加锁追加；不能用 dict 点号路径替代数组追加。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
BUILD=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" get current_build --default "")
python3 - "$TARGET_VERSION" "$BUILD" <<'PC'
import sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from baseline_edit import LockedBaseline, now_iso   # 与 autopilot phase-3-4 铸 build 同款写法
V, B = sys.argv[1], sys.argv[2]
ITEMS = [  # ← 本轮判为「需人工确认类」的每条缺陷各一项
    {"question": "<一句话说清要确认什么>", "affected_cases": ["TC-XXX"],
     "interim_verdict": "block", "raised_build": B, "at": now_iso()},
]
with LockedBaseline("memory/.sprint-autopilot-baseline.json", write=True) as lb:
    vn = lb.data.setdefault("versions", {}).setdefault(V, {})
    arr = vn.setdefault("pending_clarifications", [])
    seen = {(i.get("question") or "") for i in arr}
    arr.extend(i for i in ITEMS if (i.get("question") or "") not in seen)   # 幂等：同问题不重复追加
PC
```

> **节流门配套**：去重门第六条的跳过条件须从 `AFP == true` 放宽为
> **`AFP == true` 或 `pending_clarifications` 非空** —— 否则纯待确认轮照样每 tick 全量重跑。

**#F 最终测试完成**（★ **收敛** `CONVERGED=1` → 绿色 header；**或 未收敛冻结熔断** → 红色·不通过 header，见上「冻结级熔断收口」——两种情况都必发 #F 收口，不留悬空）——除公共字段外含 0.1bis「#F 最终通知必含字段」全部 9 项 + **待确认项清单（若 `pending_clarifications[]` 非空）** + **报告路径**：

```
🎉 {项目名称} {TARGET_VERSION}_Build{N} · 最终测试完成 —— 测试结论：✅ 通过      ← 标题（`--title`，按 0.1bis 固定前缀）
测试版本：{TARGET_VERSION} / 第 {ROUND} 轮
测试用例总数：{TOTAL}　通过：{PASS}　失败：{FAIL}　阻塞：{BLOCK}　不适用：{NA}
自动化过程发现缺陷数：{BUGS_FOUND}　回归验证通过数：{BUGS_VERIFIED}
测试报告：{TEST_REPORT_URL}（仓库相对路径 docs/reports/{V}/AI测试报告/index.html#/build/{BUILD}，直达 {BUILD} 子页）
```

> ⛔ **RED FLAG — 报告链接必带 `#/build/{BUILD}` hash**：AI测试报告是多 build 共享的 HTML SPA，访问链接**不带 hash 打开就是综合首页/概览，不是本次 build 结果页**。`TEST_REPORT_URL`（仓库相对路径 / GitHub 文件链接）**必须**以 `…/index.html#/build/{BUILD}` 结尾。**即使手动构造路径，也绝不能丢这个 `#/build/{BUILD}` hash。**

- **定报告链接（本段在 #F 通知组装前执行，先定 `TEST_REPORT_URL`）**：报告只落本地 `docs/reports/{V}/AI测试报告/`，Phase 3.2 步骤 4 的 `emit-report.py` 已写好交付台账，**直接读台账取仓库相对路径**：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
  TEST_REPORT_URL=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get "report_deliveries.\"${BUILD}\".test_report.url" --default "")
  [ -z "$TEST_REPORT_URL" ] && TEST_REPORT_URL="docs/reports/${TARGET_VERSION}/AI测试报告/index.html#/build/${BUILD}"
  ```
  > 报告产出单一信源 = `emit-report.py`，命令端不复制、不并行第二套。
- **不通过场景**：若到达流程终点仍未收敛（达到 /loop 终止 / 用户手动结束且仍有失败），#F 文案改 `测试结论：❌ 不通过`，列出未修复失败/缺陷清单，报告路径照附。

> ★ **报告字段门（按 `REPORT_ENABLED`）**：`=0` 时 #R/#F 省略「报告路径」、换一行说明，
> 结果字段（结论/用例统计/缺陷统计）照常播报；`=1` 才带报告路径。详见 rationale.md「报告字段门」。

> ★ **无头延后提醒**：#R/#F 通知，**仅 `DRIVER=mcp-remote` 远程**、**无头闭环收敛**（见 3.5 判定）**且**有「必须有头」用例延后时，才在 #F 末尾**追加** 3.5 的切有头提醒；`DRIVER=cli` 本地 / 未收敛 / 无延后则不追加（本地必须有头用例已在主循环同会话跑完）。

