<!-- 二次切分 · phase-3 片2/6：覆盖 3.2.6 生成AI测试报告HTML -->
# sprint-aiauto-test · 执行分片 [2/6]（3.2.6 合并双路并生成 HTML）

> 逐项执行本片，步骤与硬门不得省略。随脚手架同步；理据见 `rationale.md`。

### 3.2.6 生成 AI测试报告 HTML（全量实测 + 全量单测）

Phase 3.0 已确认两路终止或超时。新双路调用（含 standalone、纯后端）固定 `SKIP_REPORT=0`，都产出报告。继续使用 Phase 2 冻结的 `BUILD`，不得重读 `current_build` 把晚到结果写到新 build。`REPORT_ENABLED` 只决定是否检查 autopilot 执行报告及交付台账。

1. **数据准备**。主协调者把实测子 Agent 返回的事实写入 `docs/reports/{V}/AI测试报告/.build-input-{BUILD}.json`，必含固定 build/version/commit。先读 `{{AIDP_HOME}}/templates/reports/AI测试报告/data/示例_build1001.js` 对齐浏览器字段；`unitTests` 不手填，由执行器结果原样合并，不混入 cases/suites。`browserTests` 可声明有明确 reason 的 `N/A/UNVERIFIED/TIMEOUT/RUNNING`；`RUNNING` 只能等待，不进入本步。没有任何实测用例时保留 `cases:[]` 和 0 条真实明细、`passRate:null`，不得把不适用伪造为通过。
2. **骨架与环境事实**。缺少静态项目由 `emit-report.py` 创建 index/assets/data；有 unitTests 时刷新 app.js，避免旧 SPA 忽略单测。模板 `report-shell-version` 升级仍按原规则刷新 index/assets、保留历史 data/screenshots 并重新注册历史脚本。环境事实仅消费真实 round 的 `env-facts.json`；未取到写 null/未取到，不使用 `RENDER_MODE` 意图值或示例值。纯后端不造 env-facts，不声称使用浏览器驱动。
3. **截图与质量门**。实际进入 UI 的用例沿用 3.2.5/3.2.5bis 的证据与 Critical 门，截图路径照抄真实扩展名。无适用浏览器面/工具不可用且无结果时不补假截图或 tasks。真实结果形状不合契约仍不得标 PASS。
4. **合并与发射**。有 round 时实测统计由 `gen_report.py` 聚合；它的退出码/read_errors 必须消费。明确无浏览器结果的终态不用调用一个不存在的 round。聚合失败记录实测未核验，不能抹掉已取得的真实用例；报告原有 cases/summary 仍须通过 schema 对账。不因未核验触发 audit freeze。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
: "${TARGET_VERSION:?}" "${BUILD:?需要 Phase 2 固定的 build}"
if [ "${SKIP_REPORT:-0}" = "1" ]; then
  echo "存量恢复显式跳过报告；新双路入口不得置 SKIP_REPORT=1"
else
  BTR="docs/reports/${TARGET_VERSION}/AI测试报告"
  INPUT="$BTR/.build-input-$BUILD.json"
  UNIT_RESULT="memory/.aidp/build-unit/$TARGET_VERSION/$BUILD/result.json"
  [ ! -f "memory/$TARGET_VERSION/aiauto-unit-$BUILD.json" ] || UNIT_RESULT="memory/$TARGET_VERSION/aiauto-unit-$BUILD.json"
  BUILD_COMMIT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["commit"])' "$INPUT") || exit 1
  # 主协调者保存的部署身份；emit 再与 baseline push_commit 精确校验，standalone 由 settle 校冻结部署计划。
  python3 - "$INPUT" "$BTR/build-$BUILD" <<'BROWSER_SUMMARY'
import json, subprocess, sys
from pathlib import Path
def report_summary(agg):
    if agg.get("error") or agg.get("read_errors"):
        raise ValueError("实测聚合不完整，不能覆盖可信统计")
    c = agg["counts"]
    return {"total":agg["total"],"pass":c["pass"],"fail":c["fail"],
            "block":c["block"],"skip":c.get("skip",0),"na":c["na"],"passRate":agg["pass_rate"]}

path, build_dir = map(Path, sys.argv[1:])
data = json.loads(path.read_text(encoding="utf-8"))
rounds = [p for p in build_dir.glob("round-*") if p.name[6:].isdigit()]
state = (data.get("browserTests") or {}).get("status")
if not rounds:
    if state not in ("N/A", "UNVERIFIED", "TIMEOUT"):
        raise SystemExit("无实测 round，必须明确不适用/未核验/超时；不能编通过")
    if data.get("cases"):
        raise SystemExit("有 cases 却无对应 round，不能声称完整实测")
    data["cases"] = []
    data["summary"] = {"total":0,"pass":0,"fail":0,"block":0,"skip":0,"na":0,"passRate":None}
else:
    rd = max(rounds, key=lambda p: int(p.name[6:]))
    command = [sys.executable, "{{AIDP_HOME}}/skills/auto-test-runner/scripts/gen_report.py", str(rd), "--json"]
    proc = subprocess.run(command, text=True, capture_output=True)
    try:
        agg = json.loads(proc.stdout)
    except ValueError:
        agg = {}
    if proc.returncode != 0 or agg.get("error") or agg.get("read_errors") or "counts" not in agg:
        data["browserTests"] = {"status":"UNVERIFIED", "reason":f"gen_report 聚合不可采信，exit={proc.returncode}；保留已取得事实待核验"}
        # 不用空数组覆盖真实用例，也不伪造总数；下面 emit schema 仍要逐条对账。
    else:
        data["summary"] = report_summary(agg)
path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
BROWSER_SUMMARY
  [ "$?" -eq 0 ] || exit 1
  # 显式 --unit-result 是新链路的必需契约：缺文件产生 UNVERIFIED，错 build/commit 拒写。
  python3 {{AIDP_HOME}}/scripts/emit-report.py --kind test --version "$TARGET_VERSION" --build "$BUILD" \
    --data "$INPUT" --unit-result "$UNIT_RESULT" --commit "$BUILD_COMMIT" \
    --record-baseline "${REPORT_ENABLED:-0}" --json || exit 1
fi
```

`emit-report` 的 JSON 返回 `overallStatus`、`report_ready`、`freeze_ready`、`success_ready`。**报告成功写出不等于测试成功**：两路任一真实 FAIL → 总体 FAIL；RUNNING → 等待；UNVERIFIED/TIMEOUT → 不能通过、不 freeze。未知单测 counts 原样 null，由页面显示「未提供」。单测真实命令、run_id、失败用例、首要错误和日志均在「全量单测」独立章节中展示。报告交付路径必须带 `index.html#/build/{BUILD}`。

5. **确定性数据/渲染校验**。脚本已做 schema 与身份对账；再执行同 build 的 JS 消费检查（它同样校 unitTests 与总体结论），避免正常浏览器通过率掩盖失败单测。`renderMode` 非空而无 source、残留结构占位等仍应在输入修正后重新 emit。不得手改 data.js 或 checksum。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
if [ "${SKIP_REPORT:-0}" != "1" ]; then
  BTR="docs/reports/${TARGET_VERSION}/AI测试报告"
  if command -v node >/dev/null 2>&1; then
    if ! node {{AIDP_HOME}}/scripts/report_render_smoke.js "$BTR" "$BUILD"; then
      # 此处只处理真实渲染/数据契约故障；合法 UNVERIFIED/TIMEOUT 本身不会让 smoke 失败。
      if [ "${REPORT_ENABLED:-0}" = "1" ]; then
        N=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" bump report_gate_fail_streak)
        if [ "$N" -ge "${REPORT_GATE_FREEZE_THRESHOLD:-3}" ] || [ "${HAS_WAKE_SOURCE:-0}" = "0" ]; then
          python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --freeze-now \
            --phase 3.2.6-report-gate --reason handoff-exhausted \
            --why "报告真实渲染/数据契约故障连续 $N tick，修复产物后重试；不是单测未核验"
        else
          python3 {{AIDP_HOME}}/scripts/notify.py --node "#4" --auto --header-color red \
            --title "AI 测试受阻：报告渲染故障" --version "$TARGET_VERSION" --build "$BUILD" \
            --section "第 $N 次报告渲染故障，须修复本 build 产物后继续。" || true
        fi
      fi
      exit 1
    fi
    [ "${REPORT_ENABLED:-0}" != "1" ] || python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del report_gate_fail_streak
  else
    echo "未安装 Node：渲染冒烟未执行；保留 HTML 与 Python schema 校验，不把工具缺失记代码失败"
  fi
  python3 - "$BTR/data/$BUILD.js" <<'REPORT_READY'
import sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from unit_report_merge import read_payload, report_ready, validate_report_units
import re
p = read_payload(sys.argv[1])
errors = validate_report_units(p, "test")
for key in ("build", "version", "driver", "renderMode", "renderModeSource", "testUrl"):
    if isinstance(p.get(key), str) and re.search(r"\{[^{}]+\}", p[key]):
        errors.append(f"环境/身份字段 {key} 残留占位符")
if p.get("renderMode") and not p.get("renderModeSource"):
    errors.append("renderMode 缺运行取证来源")
if errors or ("unitTests" in p and not report_ready(p)):
    raise SystemExit("报告尚未就绪：" + "; ".join(errors))
print("报告已按真实终态汇总；此门不授予 PASS")
REPORT_READY
  [ "$?" -eq 0 ] || exit 1
fi
```

数据损坏/渲染失败应修输入或模板，保留日志并让位；单测或浏览器 UNVERIFIED/TIMEOUT 是合法报告终态，不能转作「报告门失败」来累计冻结。旧无 unitTests 报告的恢复只跑既有 schema/渲染校验，不补造旧单测。

5bis. **autopilot 骨架钢门**。`REPORT_ENABLED=1` 时报告必须与 AI执行报告骨架同 build；standalone 只检查上面的测试报告，不要求不存在的执行报告。浏览器未实际执行时传 `--will-browser-test 0`，不把 N/A/工具不可用冒充 browser tested；两路报告就绪仍由上述 report_ready 与 final 门独立检查。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
if [ "${REPORT_ENABLED:-0}" = "1" ] && [ "${SKIP_REPORT:-0}" != "1" ]; then
  WILL_BROWSER_TEST=$(python3 - "docs/reports/$TARGET_VERSION/AI测试报告/data/$BUILD.js" <<'BROWSER_ACTUAL'
import sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from unit_report_merge import read_payload
p = read_payload(sys.argv[1]); print(int(bool(p.get("cases"))))
BROWSER_ACTUAL
)
  python3 {{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py check --version "$TARGET_VERSION" --build "$BUILD" \
    --stage skeleton --will-browser-test "$WILL_BROWSER_TEST" --notify "${NOTIFY_ENABLED:-1}" \
    --baseline memory/.sprint-autopilot-baseline.json || exit 1
fi
```

门未过不能发 #F/#3；补齐本 build 产物再重试，不改其它 build。继续 3.3，由 `aiauto_test_join.py settle` 写联合结果；本片**不自行写 status=tested / aiauto_tested_at / 未收敛计数**。
