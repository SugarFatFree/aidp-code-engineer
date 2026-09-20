# sprint-autopilot · Phase 3 详情分片 [2/13]（3.0 入口路由 + P0-0 裁剪唯一授权 + test-only 骨架）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 2/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：3.0（入口路由 + AI执行报告前置硬门；P0-0 流程裁剪唯一授权；test-only 6 步骨架；incremental 路由）
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-2.md`。理据见同目录 `rationale.md`。

---

### 3.0 入口路由 + AI执行报告前置硬门（★ 入口无关强制产出 AI执行报告）

> 本步是进入 Phase 3.1 之前的入口分流：先产 AI执行报告骨架、再委派浏览器实测；无论从主路径还是「dev 已完成只跑测试」捷径进入，AI执行报告（index.html 结果 + plan.html 计划，同源 `data` 驱动）都被结构性地强制产出。

> ## 🚦 test-only 报告仪式 · 6 步不可跳硬门（≤1 屏 · 高频路径速查 · 顺序不可乱）
>
> ⛔ **凡 `ENTRY_MODE=test-only`（`--skip-dev` / test-intent / "只跑测试 / 远程功能验证"），在驱动任何浏览器之前先读这 6 步——每步用脚本、不手搓；缺任一步即 `exit 1`，绝不"简化成一份 markdown + 手搓通知"（这正是被反馈的退化）。**
>
> | 步 | 动作 | 用什么（确定性脚本，不手搓） |
> |---|------|------------------------------|
> | ① | **铸/复用 build 号** | Phase 3.1.5 R-1（写 baseline `current_build`；缺则铸、有则复用） |
> | ② | **产 AI执行报告骨架 + 骨架门(`--stage skeleton`)** | `emit-report.py --kind exec`（写 data 计划态 + 注册 index/plan 两页）→ 委派前 gate `--stage skeleton`（**只校 SPA 骨架+无markdown，不校交付台账**）；**未过不许碰浏览器** |
> | ③ | **浏览器实测** | 委派 `/sprint-aiauto-test`（或本机无头 cli）——**仅在 ② 过后** |
> | ④ | **产 AI测试报告 SPA + finalize 执行报告** | aiauto-test：`emit-report.py --kind test`（测试数据，finalize 落盘→写 test 交付台账）；发 #F 前再跑 gate `--stage skeleton`；R-4：`emit-report.py --kind exec --patch`（★ BUG-3：**`--patch` 增量回填**——读现有骨架 data 顶层浅合并真实 `testSummary`/`overview.testPassRate`，无需重构整份 payload / 从 data.js 正则抠；骨架输入 JSON 已删也不影响；finalize 落盘→写 exec 交付台账） |
> | ⑤ | **本地交付登记** | `emit-report.py` 内置（HTML 落本地 `docs/reports/{V}/`；写 baseline `report_deliveries`，链接 = 仓库相对路径） |
> | ⑥ | **最终钢门(`--stage final`) → 才发 #3/收尾** | 测试链路 **Phase 3.7**（exec+test 均已 finalize 落盘后）`autopilot-ceremony-gate.py check --stage final --will-browser-test 1`（校 执行+测试 SPA + **两份交付台账** + 无 markdown + 通知台账）`exit 1`；**过了才发 #3、通知只带 HTML 报告相对路径、禁止手搓通知/指向 markdown** |
>
> **staged gate（消时序死结）**：委派前 + 发 #F 前跑 `--stage skeleton`（交付台账尚未产生、不校它）；**唯一 `--stage final` 门 = 测试链路 Phase 3.7**（两份报告都 finalize 落盘后才校交付台账）。静态-only 路径（`deployment.mode=none`）无浏览器测试，autopilot Phase 3.4 自己跑一次 `--stage final`。下方 Phase 3.0~3.4 是详细展开（单一信源仍在各 Phase）。

> ⛔ **流程裁剪唯一授权原则（P0-0 总纲 · exit-1 级铁律）**：`/sprint-autopilot` 的**默认路径恒为全流程**——**版本规划(`/version`) → 全量开发(`/sprint-batch`) → 部署 → AI自动化测试**。任何流程的跳过，**唯一合法来源 = 用户显式声明**：① 显式 flag（`--skip-dev` / `--skip-deploy` / `--skip-pre-release` / `--no-planning` / `--skip-aiauto-test`）；② 交互式 `AskUserQuestion` 中用户主动选择。**禁止**由关键词 grep、需求语义判定、产物存在性推断等**任何隐式方式**触发跳过。
> - **模型对需求类型的判断（新功能 / bug修复 / 优化增量）只允许影响【在某个流程内部做什么工作】，绝不允许影响【是否执行该流程】**——即：允许 `incremental` 影响"开发阶段跑 `/sprint-dev` 累进而非全量 Sprint"，**不允许**它影响"要不要跑 `/version`"（那由 3.1.0 的 `PLANNING_DONE` 硬判据决定，见 P0-1）。
> - **按上下文分流问不问**（纠正旧"任何情况都不许问 ENTRY_MODE"的过宽禁令）：**`/loop` 无人值守（`LOOP_UNATTENDED=1`）→ 走保守默认（= 全流程、不裁剪、不弹窗）**；**交互式（用户在场）+ 裁剪意图不明 → 必须 `AskUserQuestion` 让用户定**。旧"防无人值守挂死"的初衷靠"无人值守走保守默认"达成，不再靠"一律禁问"。
> - 回检 = Phase 3.4 收尾门 `autopilot-ceremony-gate.py` 的**规划产物存在性检查**（P0-2：`full`/`incremental` 缺六类规划产物且无 `--no-planning` 台账 → `exit 1`）。

1. **识别入口模式 `ENTRY_MODE`**（决定 Phase 3 走法 + build 号铸造/复用）：
   ```bash
   # ★ 本 tick 参数由 0.0.0 解析并落盘，此处读回（分片间 shell state 不跨 Bash 调用持久）
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
   ENTRY_MODE="full"    # ★ 默认恒为 full 全流程（版本规划→全量开发→部署→AI测试）；任何流程裁剪只能来自【用户显式声明】，绝不由语义/关键词隐式触发（P0-0 唯一授权原则）
   # ── test-only（跳过开发、只部署+测）：唯一无条件来源 = 显式 flag --skip-dev ──
   [ "$SKIP_DEV" = 1 ] && ENTRY_MODE="test-only"
   # ★ test-intent 关键词【不再隐式置 test-only】（隐式裁剪会架空显式 flag，P0-0 根因）：
   #   交互式（LOOP_UNATTENDED=0）+ 命中 test-intent 且未带 --skip-dev → AskUserQuestion 问用户「全流程 / 仅部署+测试」，选「仅测试」才裁剪；
   #   /loop 无人值守（LOOP_UNATTENDED=1）→ 保守默认 full（不裁剪、不弹窗），仅 --skip-dev 才 test-only。
   # ⛔⛔ 本 AskUserQuestion 的维度【唯一且仅有：开发范围】——严格二选一「① 全流程（默认） ② 仅部署+测试(test-only)」，绝不多拆第三维（铁律，堵本次反馈根因）：
   #   ★ 严禁把「测试失败自动修复复测闭环」拆成第三个选项、也严禁把不含它的变体标「推荐」
   #     （它是每 tick 默认仪式、三模式恒开，不是用户决策点；论证见 rationale.md「维度唯一」）
   if [ "$ENTRY_MODE" = "full" ] && [ "$SKIP_DEV" != 1 ] && echo "$USER_INTENT" | grep -qE "已完成|已就绪|只.*测|后续.*(测试|自动化)|执行.*自动化测试"; then
     if [ "$(python3 .aidp/scripts/baseline_edit.py get autopilot.loop_unattended_this_tick --default 0)" = "0" ]; then
       : # 交互式：<AskUserQuestion 严格二选一「① 全流程（默认） ② 仅部署+测试(test-only)」——用户选②才置 ENTRY_MODE=test-only；不选则保持 full。两选项都恒含自动修复复测闭环，不得增设"含/不含自动修复"维度>
     else
       echo "🔒 无人值守命中 test-intent 但未带 --skip-dev → 保守默认 full（不隐式裁剪开发）"
     fi
   fi
   # ── incremental（★ 暂定，最终成立需硬判据②，缺一强制降级 full）──
   #   incremental 设计意图 = 在【已规划】版本上追加增量改动，**不是"用增量名义免除规划"**。硬判据（两条同时满足）：
   #     ① 需求语义为对已交付功能的增量（bug修复/功能优化/字段对齐）  ② 目标版本 PLANNING_DONE=1（四类规划产物齐，3.1.0 判定）
   #   本步只据①置【暂定 incremental】；②由 3.1.0 计算 PLANNING_DONE 后【最终裁定】——PLANNING_DONE=0 即强制回 full、照跑 /version（全新版本号本身即意味一个版本、版本就该有规划）。
   #   语义判不准时从严按 full。关键词仅辅助：修复/修一下/bug/缺陷/优化/调整/对齐/微调/改一下。
   # ⛔ 语义判定不能写进 && 链：`<…>` 不是 shell 语法，bash 在**解析期**就整块拒绝，
   #    同块的 ENTRY_MODE 判定与落盘会一行都不执行（`check_flow_bash_syntax` 先把 `<…>` 中和成
   #    PLACEHOLDER 再 `bash -n`，故它照样 PASS）。改为：执行体先就地把下一行的 0/1 定死，再参与判定。
   INTENT_IS_INCREMENTAL=0   # ← 执行体据需求意图语义判定「已交付功能的增量修复或优化」时就地改 1
   [ "$ENTRY_MODE" = "full" ] && [ -n "$USER_INTENT" ] && [ "$INTENT_IS_INCREMENTAL" = "1" ] && ENTRY_MODE="incremental"   # 暂定，待 3.1.0 硬判据②裁定
   echo "🚪 入口模式：$ENTRY_MODE（incremental 为暂定，最终由 3.1.0 PLANNING_DONE 裁定）"
   # ★ 立即落盘（勿删）：baseline 真源 autopilot_entry_mode 由 3.1.0 写，而 test-only 恰恰整段跳过 3.1
   #   → 不在此落盘则后续 tick 恒回落 full：test-only 被送进开发循环、收尾门索要不该发的卡、3 tick 冻结。
   python3 .aidp/scripts/autopilot_tick_flags.py set --command autopilot ENTRY_MODE "$ENTRY_MODE"
   # ⛔ 入口仪式保证（对齐顶部「autopilot 入口 = 产物仪式保证」铁律）：full / incremental / test-only **三种模式都必须经子流程 R**
   #   产出 build 号 + AI执行报告（+ 测试链路出测试报告）+ 里程碑通知。incremental 绝不退化成"裸 /sprint-bugfix 不铸 build / 不出报告 / 不发通知"。
   # ⛔ Phase 0 前置硬门已保证：进入本步前 Phase 0.0–0.7 必已跑完（通知渠道检查 + #0a/#0 通知、.mcp.json、版本扫描）。
   #   若因 test-intent 直达本步而 Phase 0 尚未跑完 → 立即回到 Phase 0 补齐（含发 #0a/#0 通知）再继续，
   #   绝不在 Phase 0 未完成时委派 /sprint-aiauto-test 或驱动浏览器（见 Phase 0 开头「前置硬门」）。
   ```

2. **★ 子流程 R · 产出本 build 的 AI执行报告【骨架】（幂等 · 入口无关 · 主路径与 test-only 委派路径共用同一个）**：定义为可被任何入口调用的幂等单元，**缺则建 / 有则复用**。**★ 产出与发送解耦**：子流程 R 只负责把 AI执行报告产到「**骨架就绪**」（写 `data` 计划态 + 注册两页 + `testSummary` 占位），**绝不在此发 #3 通知、绝不发报告本体**——「用真实测试结论 finalize `data` 的 testSummary + 发报告本体 + 发 #3」移到**整个 build 关闭之后**作为收尾（见 R-4，由 build 关闭方执行）——
   | 子步 | = 现有步骤 | 职责 |
   |------|----------|------|
   | **R-1** | Phase 3.1.5 | 铸造**或复用** build 号 + 写/补全 `data/{BUILD}.js` 计划态（steps 工作流 + features 功能点比对 + 元信息）+ 注册到 index.html/plan.html；**步骤完成即实时回写 actualStatus**，见 3.1.5 |
   | **R-2** | Phase 3.2/3.3 部署动作 | 如 `deployment.mode != none` 且未 `--skip-deploy` → 部署 + 写 `last_deployed_at`|
   | **R-3** | Phase 3.4 step 1 + 1.5 | finalize `data/{BUILD}.js` **结果态骨架**（dev/部署步骤填 actualStatus、**`testSummary` 占位待测**、`overview.testPassRate` 待回填；确认已注册两页）+ 产物硬核自检 |
   | **R-4**（**延后收尾，不在委派前跑**） | build 关闭方 | **用真实浏览器测试结论** finalize `执行结果` testSummary + 发报告本体 + 发 **#3 通知**（带 `#/build/{BUILD}` hash）。**关闭方判定**：将有浏览器测试（`deployment.mode != none`） → 由测试链路 `/sprint-aiauto-test` 在 **#F 之后** 执行（见其 Phase 3.7）；纯静态无浏览器测试（`deployment.mode=none` / `--skip-deploy`） → 由 autopilot Phase 3.4 末尾自己执行（带「静态自测、无浏览器测试」结论） |
   幂等保证：R-1~R-3 每步"缺则建、有则覆盖/复用"，重复调用不产生重复 build、不重复注册；R-4 由 build 关闭方**唯一**执行一次（#3 不早发、不重发）。

3. **【前置门 · 不可跳过】委派 `/sprint-aiauto-test` 之前必须先完整跑完子流程 R**：
   - `ENTRY_MODE=full`：按 Phase 3.1 → 3.1.5 → 3.2（开发 + 部署）→ 3.3 → 3.4 正常往下，子流程 R 在主路径内自然完成；浏览器实测由用户挂的 `/loop 5m /sprint-aiauto-test --unattended` 异步承担。
   - `ENTRY_MODE=test-only`：**跳过 Phase 1「无变化即退出」门 + 跳过 Phase 3.2 开发循环**，但**必须按顺序执行子流程 R 的骨架部分（R-1 → R-2 如需 → R-3 骨架）**；**仅当 R-3 骨架产物硬核自检通过后**，才 invoke `/sprint-aiauto-test --unattended [--no-loop]` 跑浏览器实测（⛔ **`LOOP_UNATTENDED=1` 时 `--unattended` 必带**，`--no-loop` 仅在 `HAS_WAKE_SOURCE=1` 时追加；裸委派会让被调侧判出 `LOOP_UNATTENDED=0`、在 tick 内退化成交互式挂死；铁律单一信源 = `phase-0-1.md` 「无人值守信号下传」）。**R-4（finalize testSummary + 发 #3）不在委派前跑** —— 它由 `/sprint-aiauto-test` 在 **#F 之后**作为收尾执行（见其 Phase 3.7），#3 此时才带真实测试结论发出。
   - `ENTRY_MODE=incremental`（bug 修复 / 功能优化增量经 autopilot 入口）：**能走到这里的 incremental 已经过 3.1.0 硬判据②确认 `PLANNING_DONE=1`（目标版本四类规划产物齐、已规划）**——否则已在 3.1.0 被强制降级为 `full` 照跑 `/version`（P0-1）。故此处 `/version` **天然跳过**（是"目标版本已规划"、**不是"用增量名义免除规划"**）；**确需新设计/接口才补跑 `/version` 增量补充，不推翻已有设计**。**incremental 影响的【仅是 Phase 3.2 做什么工作】**：经 `/sprint-bugfix`（缺陷）或 `/sprint-dev` 累进（功能优化/字段对齐）落地实际代码，**而非全量 `/sprint-batch` 跑所有 Sprint**——**它绝不影响"是否跑 /version"这一流程存废（那是 3.1.0 PLANNING_DONE 的职责，P0-0）**。**子流程 R 全程照跑**：R-1 铸本轮 build 号、R-3 finalize AI执行报告骨架、按 `deployment.mode` 部署、发 #1c/#1d 等通知、R-4 收尾（有浏览器测试委派 `/sprint-aiauto-test`、否则 autopilot 自 finalize）。**即 incremental 与 full 的唯一区别是 Phase 3.2 的工作内容（增量改动 vs 全量 Sprint）+ Phase 3.1 是否轻量；build/报告/通知/测试委派全部照常产出**，绝不因"是个小修复"省任何仪式。
   - ⛔ **严禁**：识别到"只跑测试 / dev 已完成"就**直接 invoke `/sprint-aiauto-test`**、跳过子流程 R 骨架。AI执行报告**骨架**（写 `data` 计划态 + 注册 index.html/plan.html 两页）必须由本命令在委派前产出；委派出去的是**浏览器实测 + R-4 收尾**（aiauto-test 在 #F 后 finalize `data` 的 testSummary + 发 #3）。
   - **★ 委派前脚本化硬门（不可靠自律，落为可执行 bash；缺失 `exit 1` 阻断委派）**：在 `invoke /sprint-aiauto-test` 这一步**之前**必须跑通下面这段（**只校骨架，不校 #3 是否已发** —— #3 延后到 #F 后）；非零退出 = 禁止委派，强制回 Phase 3.1.5/3.4 补建（模板缺失则先重跑脚手架，见 3.1.5 step 2 模板硬门）：
   ```bash
   eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
   V="$TARGET_VERSION"; B="$BUILD"; BN="${B##*_build}"; A="docs/reports/$V/AI执行报告"
   miss=0
   [ -f "$A/index.html" ] || { echo "❌ 缺 AI执行报告 结果入口：$A/index.html"; miss=1; }
   [ -f "$A/plan.html" ] || { echo "❌ 缺 AI执行报告 计划页：$A/plan.html"; miss=1; }
   [ -f "$A/data/${B}.js" ] || { echo "❌ 缺执行数据：$A/data/${B}.js"; miss=1; }
   { [ -f "$A/index.html" ] && grep -q "data/${B}.js" "$A/index.html"; } || { echo "❌ index.html 未注册 data/${B}.js"; miss=1; }
   { [ -f "$A/plan.html" ] && grep -q "data/${B}.js" "$A/plan.html"; } || { echo "❌ plan.html 未注册 data/${B}.js"; miss=1; }
   [ "$miss" = 1 ] && { echo "⛔ AI执行报告骨架不全 → 禁止委派 /sprint-aiauto-test，先跑子流程 R 骨架（Phase 3.1.5/3.4）补建后复跑本门"; exit 1; }
   echo "✅ AI执行报告骨架齐全（index.html 结果 + plan.html 计划 + data 已注册两页）→ 允许委派 /sprint-aiauto-test（#3 由测试链路在 #F 后 finalize 发送）"
   # ★ 委派证据标记（结构级堵"委派落空"真空，reporter B）：在【真正 invoke /sprint-aiauto-test 的那一刻】把 aiauto_delegated_at 落到本 build，
   #   让收尾门 / Step ④ 能确定性判"这个浏览器测试 build 到底有没有真委派出去"——绝不靠执行体记忆自证"我委派过了"。
   #   ⚠️ 只在**确实 invoke**测试链路时写；autopilot 自身内联驱动 chrome（未 invoke）时【严禁】写此标记（写了就等于伪造委派证据、掩盖真空）。
   # ⛔ 必须走加锁写入口（invariants「baseline 单一写入口不变式」）：本刻正是**委派测试链路的那一瞬间**，
   #    也正是测试 loop 每 5 分钟写心跳/结果的高频窗口——裸 read-modify-write 会整体抹掉对方刚落的
   #    aiauto_test_heartbeat_at / ai_report_finalized / 各 streak（后者会让熔断永不达阈）。
   python3 - "$V" "$B" <<'PY'
import sys, datetime, pathlib
sys.path.insert(0, ".aidp/scripts")
from baseline_edit import LockedBaseline          # 持 flock + 锁内重读 + 原子写回
V, B = sys.argv[1], sys.argv[2]
ts = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
with LockedBaseline("memory/.sprint-autopilot-baseline.json", write=True) as lb:
    d = lb.data                                   # ★ __enter__ 返回的是对象，数据在 .data
    blds = d.setdefault("versions", {}).setdefault(V, {}).setdefault("builds", [])
    row = next((x for x in blds if x.get("build") == B), None)
    if row is None:
        row = {"build": B}; blds.append(row)
    row["aiauto_delegated_at"] = ts
print("🖊️ 已落委派证据 aiauto_delegated_at =", ts)
PY
   ```

4. **收尾（D）**：无论 `full` / `incremental` / `test-only`，**结束前 + test-only 委派前**都强制跑 Phase 3.4 step 4「完成核验门」（入口无关，已落为 `exit 1` 硬阻断）；AI执行报告**骨架**缺失则就地补建、复跑核验通过后才退出/委派，**绝不带缺失收尾或带缺失委派**（#3 是否已发不在本门校验范围——委派路径下它由测试链路 #F 后收尾）。


---

## ⛳ 本 Phase 出口：`run_state` 写盘（**硬动作，不可跳过**）

> 单一信源 = `invariants.md`「阶段推进不变式」，此处只给本分片的**具体实参**。
> ⛔ 漏这一步 = 状态机不存在：`next_phase` 恒空 → tick 中途中断后下一 tick 从 Phase 3.0 全量重推；
> `next_sprint` 恒空 → Stop hook 的「中间 yield-tick 豁免」判据取不到值 → 每个中间 tick 都误跑一次
> 收尾门（必 FAIL）并白烧熔断额度。**本 Phase 的实质动作做完、离开本分片之前立即执行**：

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
BE="python3 .aidp/scripts/baseline_edit.py"; V="${TARGET_VERSION}"
$BE --version "$V" run-state "3.0-route" "3.1-plan" "" \
  --summary "Phase 3.0 入口路由完成：ENTRY_MODE=${ENTRY_MODE} / 目标版本 ${V} / AI执行报告前置门已过" --pending ""
```

> `ENTRY_MODE=test-only` 时下一 Phase 写 **`3.1.5-build`**（跳过 3.1 规划 / 3.2 开发，但**不跳 3.1.5 铸 build**——它是强制仪式，test-only 亦然，见骨架表「3.1.5 适用条件 = 总是」；3.1.5 出口按 test-only 写 **`next=3.3-audit`**—（余下理据见同目录 `rationale.md`）
