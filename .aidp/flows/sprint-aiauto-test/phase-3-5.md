<!-- flowvar-check: allow PASS_RATE 本轮通过率，由上方 gen_report 聚合后就地代入 -->
<!-- 二次切分 · phase-3 片5/6：覆盖 3.7 finalize AI执行报告+发#3-->
# sprint-aiauto-test · 执行分片 [5/6]（3.7 finalize AI执行报告+发#3）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-3-5.md`。理据见同目录 `rationale.md`。

### 3.7 ★ finalize AI执行报告 + 发 #3 里程碑通知（#F 之后 · 本 build 收尾 · R-4）

> **本步落实 sprint-autopilot 子流程 R-4 收尾**：委派前的 AI执行报告仅有骨架（计划态 data、两页注册、占位 `testSummary`）。本步用真实测试结论 finalize，再发报告本体和 #3。顺序固定为部署 → 测试 → AI测试报告 + #F → **AI执行报告结果态 + #3**；#3 必须在 #F 之后。

> 仅补交付走 `{{AIDP_HOME}}/templates/reports/README.md`「只补交付」（exec / #3），不重走 emit/settle/测试、不 force-amend；FAIL 亦可交付。

### 新双路终态收尾（优先于下方历史分支）

本 build 测试 data 含 `unitTests` 时执行下块，然后直接到 Step 4 数据清理判定，**不得再执行下方历史 CONVERGED-only Step 1–3**。两路完成或超时都要交付明确结论；`report_ready` 控制能否收尾，`success_ready` 控制绿灯，`finalize_ready` 单独控制报告不可变冻结。RUNNING 不得进入 final。UNVERIFIED/TIMEOUT 出报告、可发橙色终态通知，但不写 closed/finalized、不冻结、不设 tested_at。真实失败发红色；只有结构化分类确认可自动修复的实测问题和单测 FAIL 交修复新 build。缺分类时返回 3.3 补齐，不等待、不发完成卡、不冻结；环境未核验不冒充代码失败。下块再次幂等 settle，校验报告分类已真实落盘和当前用例/缺陷欠账未变化，不能跳过 3.3 后仅凭报告 FAIL 收尾。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
python3 - "$TARGET_VERSION" "$BUILD" "${REPORT_ENABLED:-0}" "${NOTIFY_ENABLED:-1}" <<'JOINT_FINAL'
import json, shutil, subprocess, sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from unit_report_merge import read_payload, report_ready, finalize_ready, overall_status
from aiauto_test_join import settle
v,b,official,notify=sys.argv[1:]
root=Path.cwd(); script=Path("{{AIDP_HOME}}/scripts")
test_dir=root / "docs/reports" / v / "AI测试报告"
p=read_payload(test_dir / "data" / (b+".js"))
if "unitTests" not in p:
    print("历史无单测报告：继续下方原收尾分支")
    raise SystemExit(0)
if not report_ready(p):
    raise SystemExit("仍有运行中分支；不能 final/发 #3/冻结")
if official=="1":
    joined=settle(root,v,b,p,standalone=False,triage=p.get("failureTriage"))
    if joined["triage_status"] != "COMPLETE":
        raise SystemExit("缺陷待分流：返回 3.3 补分类并 emit/settle，不发 #3、不冻结")
    status=joined["overall_status"]
else:
    # 独立目标不写版本汇合/join.json
    status=overall_status(p)
color="green" if status=="PASS" else "red" if status=="FAIL" else "orange"
if official=="1":
    exec_dir=root / "docs/reports" / v / "AI执行报告"
    old=read_payload(exec_dir / "data" / (b+".js"))
    overview=dict(old.get("overview") or {})
    overview.update(statusKind="done" if status=="PASS" else "fail" if status=="FAIL" else "pend",
                    testPassRate=p["summary"].get("passRate"))
    patch={"build":b,"commit":p["commit"],"overview":overview,
           "result":"success" if status=="PASS" else "failed" if status=="FAIL" else "partial"}
    draft=exec_dir / (".build-input-"+b+".json")
    draft.write_text(json.dumps(patch,ensure_ascii=False),encoding="utf-8")
    unit=root / "memory" / v / ("aiauto-unit-"+b+".json")
    if not unit.exists(): unit=root / "memory/.aidp/build-unit" / v / b / "result.json"
    subprocess.run([sys.executable,str(script/"emit-report.py"),"--kind","exec","--patch",
        "--version",v,"--build",b,"--data",str(draft),"--unit-result",str(unit),
        "--commit",p["commit"],"--json"],check=True)
    if shutil.which("node"):
        subprocess.run(["node",str(script/"report_render_smoke.js"),str(exec_dir),b],check=True)
    else:
        print("Node 不可用：exec HTML 已生成，渲染冒烟未执行")
    has_browser=bool(p.get("cases"))
    subprocess.run([sys.executable,str(script/"autopilot-ceremony-gate.py"),"check",
        "--version",v,"--build",b,"--stage","final","--will-browser-test",str(int(has_browser)),
        "--notify",notify,"--expect-cards","#D,#R,#F" if has_browser else "#R,#F",
        "--baseline","memory/.sprint-autopilot-baseline.json"],check=True)
    if notify=="1":
        rc=subprocess.run([sys.executable,str(script/"notify.py"),"--auto","--node","#3",
            "--header-color",color,"--title",f"AI 执行报告：{status}","--version",v,"--build",b,
            "--section",f"全量实测：{p['summary']['browserStatus']}；全量单测：{p['unitTests']['status']}；总体：{status}。",
            "--link-text","查看完整报告","--report-kind","exec"]).returncode
        if rc not in (0,3): print("#3 通知未送达，保留通知台账重试",file=sys.stderr)
    executed=read_payload(exec_dir / "data" / (b+".js"))
    if finalize_ready(p) and finalize_ready(executed):
        subprocess.run([sys.executable,str(script/"baseline_edit.py"),"--version",v,"--build",b,
            "set","status","closed","ai_report_finalized","true","ai_report_finalized_at","@now",
            "finished_at","@now","pass_rate",json.dumps(p["summary"].get("passRate"))],check=True)
    else:
        print("报告已交付，但验证尚不完整：不 closed、不 ai_report_finalized、不冻结；按原预算/重试协议补核验")
else:
    if shutil.which("node"):
        subprocess.run(["node",str(script/"report_render_smoke.js"),str(test_dir),b],check=True)
    else:
        print("Node 不可用：test HTML 已生成，渲染冒烟未执行")
    print(f"standalone 联合报告已交付：{status}；不创建版本 baseline 或执行报告")
JOINT_FINAL
```

上述任一步失败不得继续发绿灯或写 frozen 标记；保留失败输出。缺工具/超时/未核验不转作旧未收敛计数触发冻结。实际失败保留settle证据；原开发父任务有implement/deploy才修复并新build复验，test-only只返回失败。

### 历史无 unitTests 的收尾兼容

**触发前置**（都满足才执行；任一不满足整步跳过）：
1. `REPORT_ENABLED=1`（autopilot 驱动，有 `current_build`）—— standalone 直接调用无 AI执行报告，不 finalize；
2. Phase 3.5 判定**收敛** `CONVERGED=1`（#F 已发）—— 未收敛说明本 build 还在「修复→重测」循环中，本步**不发** #3（等收敛轮再发，避免 #3 带未收敛的中间结论）；
3. AI执行报告骨架存在（`docs/reports/{V}/AI执行报告/data/{BUILD}.js` 在 + 已注册 index.html/plan.html，autopilot R-3 已产）—— 不在则 2.5.1 早已自愈交接补建，正常到此必在。

**Step 1 — finalize 执行数据 = 调 `emit-report.py --kind exec --patch`（**必须经它以写 `report_deliveries.exec_report` 台账，否则本 build 收尾钢门交付检查会误判缺失**）**：只把**变化字段**写入 `docs/reports/{V}/AI执行报告/.build-input-${BUILD}.json`（`.` 前缀隐藏 + gitignore + emit-report 用完自动删），`--patch` 对现有 `data/${BUILD}.js` 顶层浅合并，autopilot 写的 dev/部署 steps、features 原样保留：
- `testSummary` ← **从同 build 的 AI测试报告 summary 派生（`gen_report.py --json`，⛔ 不手填）**：`{ total, pass, fail, block, skip, na, passRate:<0~1，分母 = total−na>, coverage:<有则填/无则 null>, browserTested:true }`。★ **字段映射**（`counts` 只有 `pass/fail/block/na` 四键，⛔ 没有 `total/skip/passRate`，照键名直取会落空）：`total` ← 顶层 `.total`（已剔除自由巡检项）；`pass/fail/block/na` ← `.counts.pass/.fail/.block/.na`；`skip` ← `.counts.skip // 0`（auto-test-runner 结果四态无 skip，恒为 0）；`passRate` ← 顶层 `.pass_rate`（分母已是 `total−na`，0~1 小数，原样写入）；`coverage` 无对应键 → `null`（⛔ 不拿 `.auto_cover_rate` 顶替，那是自动化覆盖率）（去骨架 `pendingBrowserTest`；**不写 `reportLink`**，链接由 `app.js` 运行时推导）。与 3.3b 冻结收口 ① 同一口径（后者另加 `unconverged:true`）。**★ `passRate`/`coverage` 单位 = 0~1 小数：写 `100.0` 或 `"6/6"`/`"100%"` 将被 `emit-report.py` 拒绝写盘（exit 3）**；
- `overview.testPassRate` ← 同一 passRate；`result` ← success|partial|failed；`steps` ← 完整 steps 数组中「AI 自动化测试」一步改 `actualStatus:"done"` + 耗时（数组是顶层字段，须整体传入）；`defects`/`incidents` ← 追加本轮缺陷/运行时错误后的完整数组。
- 再调（R-4 收尾）：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"   # 取回 BUILD/NOTIFY_ENABLED（跨分片不持久）
  mkdir -p memory/.aidp
  python3 {{AIDP_HOME}}/scripts/emit-report.py --kind exec --patch --version "$TARGET_VERSION" --build "${BUILD}" \
    --data "docs/reports/${TARGET_VERSION}/AI执行报告/.build-input-${BUILD}.json" --baseline memory/.sprint-autopilot-baseline.json --json > "memory/.aidp/emit-exec-${BUILD}.json"
  AI_REPORT_URL=$(jq -r '.access_url' "memory/.aidp/emit-exec-${BUILD}.json")   # 仓库相对路径（带 #/build/<BUILD> hash）
  ```
  脚本自动：写结果态 data + 注册两页（报告只落本地 `docs/reports/`）→ 回写 baseline `report_deliveries.exec_report`；返回的 `access_url` 为仓库相对路径（带 `#/build` hash），#3 通知直接附该路径。**⛔ 不手工写 data / 注册**。

> ⛔ **本段 bash 一律用真实变量 `$TARGET_VERSION` / `$BUILD`，绝不写字面 `{V}`/`{BUILD}` 占位符**：
> 否则 ① 门指向不存在的路径恒 FAIL；② `bump`/`set` 会把 streak 与冻结字段**记进一个字面名为 `{V}` 的假版本键**，
> 真实版本的熔断永不触发。

**Step 1.5 — ★ 最终收尾钢门（`--stage final` · 发 #3 之前必过 · 本 build 唯一权威仪式门）**：此刻 exec + test 两份报告都已 finalize 落盘（交付台账 `report_deliveries.{exec_report,test_report}` 均已由 emit-report 写入），跑**全量校验**——执行报告 SPA + 测试报告 SPA + **两份交付台账** + 无 markdown + 通知台账：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
   GATE={{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"   # ⚠️ 必须定义在 if 之外：通过分支也要用它清 streak
   if [ -f "$GATE" ]; then
     python3 "$GATE" check --version "$TARGET_VERSION" --build "$BUILD" \
       --stage final --will-browser-test 1 --notify "${NOTIFY_ENABLED:-1}" \
       --expect-cards "#D,#R,#F" \
       --baseline memory/.sprint-autopilot-baseline.json || FINAL_GATE_BAD="最终仪式门未过（ceremony-gate --stage final）"
   else
     EXEC_D=$(jq -r ".report_deliveries.\"${BUILD}\".exec_report // empty" memory/.sprint-autopilot-baseline.json 2>/dev/null)
     TEST_D=$(jq -r ".report_deliveries.\"${BUILD}\".test_report // empty" memory/.sprint-autopilot-baseline.json 2>/dev/null)
     if [ -f "docs/reports/${TARGET_VERSION}/AI执行报告/index.html" ] && [ -f "docs/reports/${TARGET_VERSION}/AI测试报告/index.html" ] && [ -n "$EXEC_D" ] && [ -n "$TEST_D" ]; then
       echo "⚠️ autopilot-ceremony-gate.py 缺失 → 内联兜底 final 校验通过（exec+test SPA + 两份交付台账在位）；建议重跑 aidp-code-engineer upgrade 补回 gate 脚本"
     else
       FINAL_GATE_BAD="最终仪式门未过（内联兜底：SPA / 交付台账缺失）"
     fi
   fi
   if [ -n "$FINAL_GATE_BAD" ]; then
     python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" --build "${BUILD:-}" \
       --phase 3.7-final-gate --reason deploy-unreachable \
       --streak-key final_gate_fail_streak --threshold "${REPORT_GATE_FREEZE_THRESHOLD:-3}" \
       --why "最终仪式门未过（报告交付缺失）：$FINAL_GATE_BAD；补齐（emit-report.py 重跑）后复跑，禁止发 #3/收尾"
     exit 0   # ★ 已记账 + 已告警，让位本 tick
   fi
   $BE --version "$TARGET_VERSION" del final_gate_fail_streak || true   # 全通过 → 清零
   ```
   **这是浏览器路径的唯一 `final` 门**（autopilot Phase 3.4 对浏览器路径只跑 `skeleton`，把交付判定权交到此处，避免"要求尚未产生的交付台账"死结）；未过不发 #3、不收尾。

**Step 2 — 发里程碑通知 #3（AI执行报告里程碑，绿色 header）**：`python3 {{AIDP_HOME}}/scripts/notify.py --auto --node "#3" --header-color green --title … --section … --link-text "查看完整报告" --report-kind exec --version "$TARGET_VERSION" --build "$BUILD"`（退出码 3 = 未配置渠道 → 静默跳过；1 = 全部渠道失败 → WARN 不阻塞），正文按 sprint-autopilot 0.1bis「#3 AI执行报告通知完整模板」填充——「测试结论」段填**本 build 真实浏览器测试**（`总数 $TOTAL / 通过 $PASS / 失败 $FAIL / 阻塞 $BLOCK / 忽略 $SKIP / 不适用 $THIS_ROUND_NA / 通过率 N%`（**通过率分母 = 总数−不适用**，与 SKILL `gen_report.py` 同口径））；「查看完整报告」= `$AI_REPORT_URL`（Step 1 emit-report.py 返回，禁止指向 markdown / 手搓通知）。**#3 是本 build 的末尾里程碑**（在 #F 之后），与 #F（测试报告）各司其职：#F = AI测试报告，#3 = AI执行报告（含 dev 全流程 + 真实测试结论）。

**Step 3 — baseline 收尾（★ 报告冻结）** —— ⛔ **必须是可执行语句**（同分片 3.3 的 `tested` 就是围栏；
`closed` + `finalized` 此前停在句子里，而它有 4 处可执行读侧：准发布 0b 门 / 已测去重门 /
Stop hook / emit-report 不可变锁。恒读 false 的后果是 0b 门永不通过、`prerelease_test_hold_streak`
每 tick +1，第 12 tick 冻结在 `unconverged`——**而测试其实早就跑完并通过了**）：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
BEV="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
PASS_RATE=$(grep -oE '"passRate"[[:space:]]*:[[:space:]]*[0-9.]+' \
  "docs/reports/${TARGET_VERSION}/AI执行报告/data/${BUILD}.js" 2>/dev/null \
  | head -1 | grep -oE '[0-9.]+$')
$BEV --build "${BUILD:?}" set status closed ai_report_finalized true \
  ai_report_finalized_at @now finished_at @now pass_rate "${PASS_RATE:-0}"
```
**`ai_report_finalized` / `ai_report_finalized_at` 是「报告不可变铁律」的冻结基准**：此后 `emit-report.py` 对本 build 再写 data 直接拒绝 exit 2（除非 `--force-amend` 留痕）、`autopilot-ceremony-gate.py --stage final` 校 data mtime 不得晚于 `ai_report_finalized_at`（详见两脚本 + 命令主体文首 ⛔「报告不可变铁律」）。

> ⛔ **不重发 / 不早发铁律**：#3 仅在收敛轮（`CONVERGED=1`）由本步发**一次**；未收敛轮只发 #R（见 3.4），绝不发 #3。`REPORT_ENABLED=0`（standalone）整步跳过——AI执行报告是 autopilot 流水线产物，非 autopilot 驱动不 finalize、不发 #3。

**Step 4 — ★ 数据清理文档生成（每 build 一份，落 `docs/reports/{version}/AI数据清理/`）**：本 build 的 AI 自动化测试通过浏览器造了测试数据（新增/编辑记录），会污染测试环境库，故 finalize 时**自动**生成一份**数据清理文档**供测试后清库。**非阻塞 best-effort**（无人值守自动跑、不弹确认；生成失败仅终端 WARN、不阻塞收尾）。

- **触发条件**：`REPORT_ENABLED=1`（autopilot 驱动、有 `BUILD`）→ 生成；**与 `CONVERGED` 无关**——无论本轮通过/部分通过/不通过，只要跑了测试就造了数据、就要能清（standalone 无 `BUILD` 概念 → 跳过本步）。
- **落位**：`docs/reports/{version}/AI数据清理/${BUILD}_数据清理.md`（目录不存在先 `mkdir -p`；属 `docs/reports/{version}/` 报告族、与 `AI执行报告/`·`AI测试报告/`·`版本测试报告/` 同处，遵约定 11 版本落位一致性——恒落当前被测版本目录）。
- **生成方式**：`cp {{AIDP_HOME}}/templates/reports/AI数据清理.md` 到落位路径后逐字段填充（模板即字段规范，本命令不复述）：
  - **测试执行信息**：`BUILD` / 版本 / 测试时间窗（本轮开始~结束）/ 环境名 / 被测 URL / `driver` / 测试账号（脱敏）/ 本轮结论——取自 Phase 0 已读的「测试环境与账号」配置 + baseline build 记录。
  - **需清理的数据库**：DB 连接**优先取** `docs/testing/{version}/研发自测/` 的「测试环境与账号」配置的 DB 段；缺失则回退后端 `application.yml` 生效 profile 的 datasource（host/port/库名/账号）；**两者都缺 → 填 `{待补}` 占位 + 文档标注「需人工补数据库连接」，不静默留空**。
  - **涉及写库表 + 清理 SQL**：由本 build 实际跑过的用例/模块（auto-test-runner 本轮 `results/*.json` / 覆盖的 SUITE）映射到详细设计「数据库设计」对应业务表；**优先按「测试账号 create_by + 本轮时间窗 create_time」双条件生成逐表 `DELETE`**（表含审计字段时，安全、不误删真实数据）；无审计字段的表按业务标记/主键区间并标「需人工核对」；有外键依赖按子表→父表顺序。**严禁**生成整库 `DROP`/无条件 `DELETE`（除非该库为独占测试专用库才给 `TRUNCATE` 兜底选项）。
- **报告不可变对齐**：本 build 一旦 finalize（Step 3 冻结），其数据清理文档**随之定稿**；后续测试结论变化走新 build → 另生成 `${下一 BUILD}_数据清理.md`，**绝不回改旧 build 的清理文档**。
- **提交**：仅原开发父任务另有commit授权时由其提交；test-only不提交/推送/部署。

**Step 4.1 — ★ 主动询问是否执行数据清理（交互式问用户；无人值守默认不执行）**：数据清理文档生成后**不自动执行**其中的清理 SQL（`DELETE` 属破坏性操作），而是把「是否现在清库」的决定权交用户：

- **交互式调用**（非 `LOOP_UNATTENDED`）→ 用 `AskUserQuestion` 问：**「本 build 已生成数据清理文档 `${BUILD}_数据清理.md`，是否现在执行其中的清理 SQL？」** 选项 **[① 暂不执行（仅保留文档，默认推荐）/ ② 现在执行清理]**。
  - 选 **①** → 跳过执行，仅保留文档供人工后续手动清理。
  - 选 **②** → 按文档「二、需清理的数据库」的测试库 datasource，用对应 DB 客户端执行「五、清理 SQL」——**执行前硬校验：确认目标是测试库、非生产**（库名/host 命中生产特征或无法判定则**拒绝执行 + 提示人工**）；执行结果（各表删除行数）回显终端 + 追加到文档末尾「执行记录」段。
- **无人值守**（`LOOP_UNATTENDED` / autopilot `/loop` 驱动）→ **绝不弹问询、绝不自动执行清理 SQL**（无人值守自动跑破坏性删除有风险）；仅在终端 + `#F`/`#3` 通知正文标注一行「📄 数据清理文档已生成 `${路径}`，需人工决定是否执行」，把执行决策留给人。
- **安全铁律**：任何情形下清理 SQL 只在文档记录的**测试库**执行、**生产库严禁**；执行走「测试账号 + 时间窗」双条件精准删（见文档「六、安全铁律」）。
