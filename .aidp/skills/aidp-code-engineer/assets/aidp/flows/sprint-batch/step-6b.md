<!-- 本文件是 `/sprint-batch` Step 6 的后半段（6.4~6.6）执行分片，由 `step-6.md` 指向。 -->

# /sprint-batch · Step 6.4 ~ 6.6

> 本文件承接 `step-6.md`（Step 6.0 跳过判定 / 6.0.5 SQL 已应用校验 / 6.0.6 部署流程文档校验 /
> 6.1 用例存在性 / 6.2 deployment 配置 / 6.3 部署完成确认）。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本。

#### Step 6.4 baseline 预写 + 调用 `/sprint-aiauto-test --once`

> 📎 **入口判据（对齐项目记忆文件 `AGENTS.md`（Claude Code 下为 `CLAUDE.md`）「AI 测试入口前置规则」；★ "属不属 autopilot 体系"这一判据以本文件为准，`/sprint-test` 与上述同名段的表述随之）**：调用前先查 ① baseline `memory/.sprint-autopilot-baseline.json` 里本 `{version}` 是否属 **autopilot 体系**——判据 = `current_build` 存在，**或** `versions.{version}` 存在**且** `versions.{version}.source != "sprint-batch"` ② 本 build **AI执行报告**是否存在。
> - ⛔ **`versions.{version}.source == "sprint-batch"` 一律不算 autopilot 体系**：那条记录正是下方第 1 步本 Step 自己预写的，把它算进判据会让**首跑之后的每一次重跑**（bugfix 后回归 / 首跑失败重跑）都被弹回 autopilot，与预写时 `source` 标记的用意（"本 build 由 sprint-batch 直测、不弹回"）正相反。
> - **autopilot 编排链恒带 `--skip-aiauto-test`**（`phase-3-5b.md` 列为必传 flag），故链内调起时本 Step 在 **6.0 跳过条件**处即整段跳过、走不到这里；（余下理据见同目录 `rationale.md`）
> - **链外直接跑 `/sprint-batch`**（用户手动执行）且 **属 autopilot 体系（按①判据）+ 本 build AI执行报告缺失** → **改走 `/sprint-autopilot --skip-dev [--unattended]`**（⛔ 按 `/sprint-batch` 自身是否无人值守**条件透传**——不传则 autopilot 派生 `LOOP_UNATTENDED=0`，在交互门无人可答处挂死）产出 AI执行报告，由它委派浏览器实测；本 Step 6 记报告"已交 autopilot test-only 入口"后收口，不直调 `/sprint-aiauto-test`。
> - **不属 autopilot 体系**（无 baseline 记录的真正 standalone，或记录 `source="sprint-batch"` 的本链路自留痕）**或 AI执行报告已在** → 照常直调 `/sprint-aiauto-test --once`。

1. **预写 baseline**（让 aiauto-test Phase 0.2 能识别「当前开发版本」）：
   ```bash
   # ★ 本块自取版本号（分片间 shell 变量不持久；口径同 step-6.md 6.0.5 首处）
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell 2>/dev/null||true)"
   VERSION="${TARGET_VERSION:-$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version)}"
   [ -n "$VERSION" ] || { echo "⛔ 取不到版本号 → 中止本步，不静默跳过"; exit 1; }
   BASELINE_FILE="memory/.sprint-autopilot-baseline.json"
   NOW=$(date -Iseconds)
   # ⛔ 写 last_deployed_at 前须先有部署证据（约定 31.5；根因见 rationale）：classify_push.py →
   #    无正式代码变更记 cicd_skipped=true 且不写该字段；有变更须 cicd_watch 终态 + 就绪探针才写。
   #
   # ⛔⛔ 下面几行**必须是可执行语句**，⛔ 不得退回注释（根因见 rationale.md「预写 baseline」）。
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
   # 本块自取（分片间 shell 变量不持久）：部署形态取 PRD 声明、部署证据取 baseline 既有事实
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell 2>/dev/null||true)"
   DM="${DEPLOY_MODE:-$($BE --version "$VERSION" get deployment_mode --default none)}"
   $BE --version "$VERSION" set phase_beta_done_at "$NOW" deployment_mode "$DM" source "sprint-batch"
   # ★ `last_deployed_at` 只认**本轮的真实就绪证据**。
   #   ⛔ 绝不能拿「baseline 里已有旧值」当证据再刷成 $NOW：那既让首次部署永远写不进（旧值为空），
   #      又让重复部署凭上一次的值续命 —— 测试链路会去探上一次部署的 URL，
   #      环境类冻结也会被这个假新值误解冻。
   HURL=$($BE --version "$VERSION" get deployment.cloud_ready_api_url --default "")
   [ -z "$HURL" ] && HURL=$($BE --version "$VERSION" get deployment.local_backend_url --default "")
   if [ -n "$HURL" ]; then
     python3 {{AIDP_HOME}}/scripts/autopilot-deploy-watch.py --health-url "$HURL" \
       --cold-start-seconds 55 --timeout 300 --version "$VERSION"   # exit 0 时它自己写 last_deployed_at
     case "$?" in
       0) echo "✅ 就绪探针通过，last_deployed_at 已由探针写入" ;;
       5) echo "⚠️ 环境已就绪但 baseline 写入失败 → 原地重试，不冻结" ;;
       *) echo "⚠️ 就绪探针未通过 → **不写** last_deployed_at，交 aiauto-test Phase 1 自探" ;;
     esac
   else
     echo "ℹ️ 无 health URL（mode=$DM）→ **不写** last_deployed_at，就绪由 aiauto-test Phase 1 自探"
   fi
   ```
2. **调用** `/sprint-aiauto-test --once [--unattended] [--role <role>]`：⛔ `[--unattended]` **按 `/sprint-batch` 自身是否无人值守条件透传**——被调侧「显式 `--once` 未带 `--unattended` 恒交互式」（`phase-0-1.md`），漏传会在 `/sprint-batch --unattended`（未带 `--skip-aiauto-test`）这条路径上弹出无人可答的 `AskUserQuestion`。autopilot 编排链恒带 `--skip-aiauto-test`、不到本步，但那不覆盖用户手动跑 `--unattended` 的情形。
   - 用例集由 aiauto-test Phase 2.0「用例来源优先级解析」自行确定（正式用例主集 + 研发自测补集），sprint-batch 不干预选集（约定 21）
   - 不传 `--target`（让 aiauto-test 自动从 baseline 读，避免参数双写）
3. **aiauto-test 内部自己处理**（按约定 21，sprint-batch 不重复其内部行为 — chrome 检测 / credentials 收集 / 部署探测 / 仿真测试主循环 / baseline 写 / 里程碑通知等，详见 `/sprint-aiauto-test` 文档）

#### Step 6.5 问题回写「问题汇总清单」表（失败用例 C-NNN；运行时错误 R-NNN 由 aiauto-test 自写）

aiauto-test 跑完后，sprint-batch 读 baseline 的 `aiauto_test_result` 段。**`failed`（失败用例）与 `runtime_errors`（运行时错误）是两类问题**：运行时错误（含"通过用例上的接口报错"、"无用例覆盖页面的报错"）已由 `/sprint-aiauto-test` Phase 2.4/3 自行回写 `R-NNN` 行，sprint-batch **不重复写**；本步骤只负责把**失败用例**写成 `C-NNN`。如有失败用例（`aiauto_test_result.failed > 0`）：

1. 解析 `aiauto_test_report` 路径，读「失败汇总」段（Markdown 表）
2. 对每个失败用例，**追加一行到「问题汇总清单」表**（表位置按用例来源选择）：
   - 主集来自测试人员（`docs/testing/{version}/正式用例/`）→ 失败用例回写到对应测试人员文件末尾
   - 主集来自研发自测（`docs/testing/{version}/研发自测/02_自测用例-总览.md` 多文件形态 / `docs/testing/{version}/研发自测/02_全量自测用例.md` 单文件形态 / 旧锚 `01_` 用例 / 历史 `docs/testing/{version}/研发自测.md`）→ 回写到主文档末尾
3. 行格式（与 sprint-bugfix 来源 B 协议一致，6 列）：
   ```
   | C-NNN | T-005 | AI 自动化测试失败：订单分页按钮 5s 未出现 | P1 | aiauto-test 自动跑 normal-user 角色，访问 /orders；console 报 undefined is not a function（详见 AI测试报告 HTML：docs/reports/{version}/AI测试报告/index.html） | 待修复 |
   ```
   - `C-` 前缀 = 来自 AI 自动化测试（与 `B-` 零散 bug、`T-` 测试用例区分），便于审计
   - 序号 `C-001` 起，按本次 aiauto-test 失败顺序累计
   - 严重程度从 aiauto-test 报告抽取
4. **后续闭环**：用户跑 `/sprint-bugfix`（**方式 B**）时，命令端 Step 1 已声明扫描「问题汇总清单」表（来源 B），会自动拾取这些 `C-NNN` 失败用例 + aiauto-test 自写的 `R-NNN` 运行时错误 + 已有零散 bug 一并修复；修完再跑 `/sprint-aiauto-test --once` 回归验证

5. **运行时错误也要算"有问题"**：判断本次 AI 自动化测试是否"有问题需修"时用 `failed > 0 || runtime_errors > 0`——**用例全通过但 `runtime_errors > 0` 同样不是绿灯**（最终汇总报告标"用例全通过但有 N 个运行时错误已记 bug"，不可直接发布）

> ★ **回写失败的兜底**：如果「问题汇总清单」表结构不符（比如老版本仍是 5 列）→ 不强写、打印警告 + 把失败清单原样追加到「附录-Sprint-batch Step 6.5 待手动整理」段，避免污染主表

#### Step 6.6 兜底（AI 自动化测试整体失败时）

- chrome-devtools-mcp 未安装 / 部署探测超时 / 登录失败等 → aiauto-test 命令自己已发里程碑通知（已配置渠道时）并退出
- sprint-batch 不阻塞「最终汇总报告」生成：所有兜底情况在汇总报告的「浏览器仿真测试」段标出（详见输出段）
- sprint-batch 主流程已闭环（Step 1~5 通过），AI 自动化测试是补充验证；失败不回滚 Sprint 关闭状态
