# sprint-autopilot · Phase 3 详情分片 [6/13]（3.2.1 CICD Step A0/A/B/C 触发与监听重试）

> 本文件是 `/sprint-autopilot` 命令 **Phase 3** 详情的**第 6/13 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：3.2.1（CICD 编排 Step A0/A/B/C：流水线解析 / 防重复触发 / 主动触发 / 监控+失败重试；平台 = `cicd.provider`，默认 GitHub Actions）
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md；清单见命令主体 Phase 3 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-6.md`。理据见同目录 `rationale.md`。

---

### 3.2.1 CICD 编排 + 部署就绪探针（`cicd-provider` 触发，或正式代码 push 触发）

> **`vcs_mode=none` 优先出口**：仅跳过依赖 push commit 的 cloud CICD 触发/监听与远端就绪探针，记 `status=skipped, reason=unsupported:vcs-disabled`，不得标记通过，也不得借 `cicd_skipped=true` 冒充「已成功推送且无需流水线」。`mode=cloud` 不写 `last_deployed_at` / `phase_beta_done_at`，不发 #1d、不等待旧部署；转 Phase 3.3/3.4 继续本地审计和报告。**`mode=local` 的本地就绪不依赖 Git**：依 `phase-3-5b.md` 先探实际服务/端口，未就绪不得写证据；本地就绪后写 `last_deployed_at` + `phase_beta_done_at`，保留测试交接与可验证部署证据，不能把本地部署同远端 CICD 一起跳过。不因 Git 能力缺失冻结本地开发。仅 `git` 模式走下方分类缺失 fail-closed 与推送绑定逻辑。

> **★ 进入本 Phase 前置判定**：读取当前 build 的 `change_classification`（由 Phase 3.2 push 前分类写入）。`cicd_skipped=true` 且 `classification_error=false` 时，本 Phase **整段跳过**：push 已成功校验，直接记录 push 完成，不触发/监听远端 CICD、不等待部署、不跑就绪探针，也不读取远端状态反推分类。分类记录缺失、脚本失败或 `classification_error=true` 时一律按正式代码路径进入本 Phase（fail-closed）。
> **适用条件**：分类允许监听，且项目已接入 CICD（`memory/aidp-config.yaml` 的 `cicd.provider` ≠ `none`、`cicd.pipelines.<env>` 已配、提供方 CLI/凭据可用）。`cicd-provider` 模式可主动触发（`cicd_watch.py --mode trigger`，要求该流水线在平台侧允许手动/API 触发，如 GitHub Actions 的 `workflow_dispatch`）；`git-push`/`ci-pipeline` 由 push/外部自动触发后只检测并接管运行。两类 trigger 的失败监控、最多 `cicd.max_retries`（默认 3）次重试和就绪探针相同。
> **不适用（回落轻量路径）**：分类明确跳过，或 `cicd.provider=none`、未配置 `cicd.pipelines`、提供方 CLI/凭据不可用（`cicd_watch.py` 退出码 3）、`manual-script`、`mode=local`、`mode=none`。分类明确跳过按上条直接完成；其余按 Phase 3.2 轻量分支处理。
> 检测 / 轮询 / 触发 / 重试一律经 `{{AIDP_HOME}}/scripts/cicd_watch.py`（`--mode detect|poll|trigger|retry`，平台差异收在 `cicd_providers.py`，⛔ 命令端不直接调任何平台 CLI）。读模式只给结论（`next_action`），写模式由命令端按结论显式调用；命令端只做编排（何时触发 / 何时重试 / 就绪判定）。
>
> ⛔ **本片引用的 `GIT_PUSH_COMMIT` / `GIT_PUSH_AT` 一律从 baseline 读，不要当成上一分片传下来的 shell 变量**——它们赋在 `phase-3-5b.md` 的推送围栏里，跨不过 Bash 调用边界；取空会让下面所有 commit 强绑定判据退化成"抓最近一条运行"，而那正是本片反复禁止的事：
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
> BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
> B=$($BE get current_build --default "")
> GIT_PUSH_COMMIT=$([ -n "$B" ] && $BE --build "$B" get push_commit --default "" || echo "")
> GIT_PUSH_AT=$([ -n "$B" ] && $BE --build "$B" get push_at --default "" || echo "")
> [ -n "$GIT_PUSH_COMMIT" ] || echo "⛔ 取不到 push_commit → 禁止用弱信号认领运行，回 Phase 3.2 确认推送是否真的成功"
> ```

**Step A0 — 流水线解析（★ 禁止用环境词机械选流水线；优先「观测哪条流水线因本次提交起跑」，再「触发分支 + 部署目标」核验，仍识别不出提前问用户）**

⛔ **不得**直接拿 `cicd_env`（dev/test/prod）→ `cicd.pipelines[env]` 机械选中一个就用而不核验——用户口语环境词、配置里的 env key、流水线显示名、流水线实际监听/构建的分支、流水线部署目标 URL **五者常不对齐**，机械映射几乎必错（典型：把口语"测试环境"映射到一个实际构建旧版本分支的演示流水线，只查这一个就误判"被旧版本阻塞"）。按下列优先级解析（**观测法最直接**，识别不出再构建分支核验、再问人）：
1. **★ 优先·观测法 + commit 强绑定**（多数项目配置「push 即触发」，直接看哪条流水线因**本次提交**起跑）：Phase 3.2「部署触发前置」已把代码 push 到 origin（时间 `GIT_PUSH_AT`、提交 `GIT_PUSH_COMMIT`）。等 `cicd_post_push_wait_seconds`（默认 10s）后执行检测：
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
   B=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "${TARGET_VERSION:?}" get current_build --default "")
   GIT_PUSH_COMMIT=$([ -n "$B" ] && python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" --build "$B" get push_commit --default "" || echo "")
   CENV="<dev|test|prod>"; mkdir -p memory/.aidp
   python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode detect --commit "${GIT_PUSH_COMMIT:?}" --env "$CENV" \
     --version "$TARGET_VERSION" --timeout 480 > memory/.aidp/cicd-detect.json
   DRC=$?; cat memory/.aidp/cicd-detect.json
   # ★ 命中（rc=0 且 next_action=poll）→ 输出 JSON 直接回写 baseline（⛔ 散文声明不算写入）
   if [ "$DRC" = "0" ] && [ "$(jq -r '.next_action' memory/.aidp/cicd-detect.json)" = "poll" ]; then
     python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" set \
       cicd_run.env "$CENV" \
       cicd_run.pipeline "$(jq -r '.pipeline // ""' memory/.aidp/cicd-detect.json)" \
       cicd_run.run_id "$(jq -r '.run_id // ""' memory/.aidp/cicd-detect.json)" \
       cicd_run.run_commit "$(jq -r '.run_commit // ""' memory/.aidp/cicd-detect.json)" \
       cicd_run.commit_verified "$(jq -r '.commit_verified // false' memory/.aidp/cicd-detect.json)"
   fi
   # rc=2 unreachable / rc=3 CLI 类 → 按 phase-3-6b.md「瞬时故障记账」（CJ=memory/.aidp/cicd-detect.json）
   # 需要跨多条流水线观测时，对 cicd.pipelines 里的每个 env（或 --pipeline <标识>）各跑一次 detect
   ```
   **匹配优先级（commit 是唯一能区分"我的提交"与"他人同期提交 / 上一条旧运行"的信号）**：
   - **① commit 强绑定（首选）**：运行的 commit `== GIT_PUSH_COMMIT`（`cicd_watch.py` 内按前缀兼容短 SHA）命中的那条运行为本次部署运行，`cicd_run.commit_verified=true`。**⛔ 不得仅凭「有一条运行时间在我 push 之后」就认领。**
   - **② 回退·时间+触发类型（弱信号，仅当平台运行记录取不到 commit 时——罕见）**：`createdAt` 晚于 `GIT_PUSH_AT` **且** `event` 属 push 自动触发。此路 `commit_verified=false`——**未经 commit 核验**，Step C 遇异常不得据它当"确已是我的运行"。
   命中 → 上面代码块已把 `RESOLVED_PIPELINE`（`pipeline`）+ **`RESOLVED_RUN_ID`**（`run_id`，Step C 按它精确轮询、不滑最新）+ `RESOLVED_RUN_COMMIT`（`run_commit`）+ `cicd_run.env` 写入 baseline，`RUN_TRIGGERED=auto`，**直接进 Step C**（Step A/B 跳过）。观测到**多条**流水线的候选运行 → 交步骤 2/3 核验收敛；**有运行却无一条 commit 等于 `GIT_PUSH_COMMIT`** = 本次提交的运行尚未起跑（非"抓最近一条顶替"）→ 交 Step B 主动触发。
2. **触发分支 == 本轮 DEV_BRANCH（观测命中的核验 / 未观测到时的主匹配）**：观测命中后仍**核对**其构建分支 == DEV_BRANCH（防止拿到一条恰好在跑、却构建别的分支的运行）；**没观测到任何自动触发**（未配 push 触发 / 尚未起跑）→ 拉 `cicd.pipelines` 对照表（`env / 流水线标识 / 监听分支（读平台流水线定义的触发分支，如 GitHub Actions 的 on.push.branches、GitLab CI 的 rules / only）/ 最近一次运行`），以「监听/构建分支 == DEV_BRANCH」为**唯一可机械核验的强信号**主匹配（排除分支不符者），未自动触发者交 Step B 主动触发。
3. **辅匹配 = 部署目标 + 声明的部署 URL**：候选仍多于一个时，用 `cloud_deploy_url`/`cloud_backend_url` 的 host 与流水线里声明的部署 environment / 目标 URL 做二次收敛，靠拢"新代码实际部署到的那个环境"。
4. **★ 仍识别不出 → 提前找用户确认哪条流水线执行部署**：多个命中 / 零命中 / 分支与 DEV_BRANCH 全不匹配 → **交互式**用 `AskUserQuestion` 把对照表（env/流水线/分支/部署目标/最近运行）给用户选；**`/loop` 无人值守**下→ **绝不机械猜定**：按「冻结字段写入契约」写齐（本片无 `freeze()` 助手，它在 `phase-3-6b.md`）：
     ```bash
     eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
     # 冻结四件套 + #4 一次做完（⛔ 「发 #4 @用户」必须由这一行真的发出去，写成散文等于没发）
     python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "${TARGET_VERSION:?}" --freeze-now \
       --phase 3.2.1-pipeline --reason pipeline-unknown \
       --why "CICD 流水线无法自动识别（观测+触发分支均未唯一命中，候选对照表见终端输出），请确认哪条流水线执行部署"
     ```
   （环境类）+ 原因「CICD 流水线无法自动识别（观测+触发分支均未唯一命中，对照表见日志），请确认哪条流水线执行部署」，发 #4 @用户、冻结本版（不重试、不放行测试链路空跑）。
5. **就绪探针用对目标**：Step D 的 `cloud_ready_*` URL 必须指向 `RESOLVED_PIPELINE` 实际部署的那个环境，别探到部署了旧代码的另一环境得出假绿。

> ⛔⛔ **`cicd_watch.py` 调不通时【不得自行实现轮询】**（自写轮询丢掉 `next_action`/`run_id` 判定）：
> 报修脚本 + 按约定 31.5 最保守口径**直接重试**、⛔ 不查业务代码。详规见 31.5，自检 `--selftest`。
>
> ★ 下方 Step A/B/C/D 的所有 CICD 调用**一律锚定 `RESOLVED_PIPELINE` / `RESOLVED_RUN_ID`**（经 `--pipeline "$RESOLVED_PIPELINE"` 传入，不用 `--env <env>` 机械取流水线）。`cicd_env` 仅在对照表无歧义时作默认提示，最终以本 Step A0 的触发分支 + 部署目标核验为准。
>
> ⛔ **运行绑定不变式**：Step A/B/C 全程必须把「本次 push 的 commit」与「被监控的流水线运行」强绑定，不得只按时间+触发类型猜（会盯错别人的运行、把他人失败算到本轮头上，或把本轮失败误判成成功）。判据与取值见下方各 Step；根因见 `rationale.md`。

**Step A — 防重复触发确认（★ 仅当 Step A0 未经观测法确定 `RUN_TRIGGERED=auto` 时的回退检测；已由 A0 point1 观测命中则整个 Step A 跳过）**

> Step A0 point1「观测法」已在 push 后等 `cicd_post_push_wait_seconds` 检测、命中自动起跑即记 `RUN_TRIGGERED=auto`+`RESOLVED_PIPELINE` 直接进 Step C。本 Step A 只在 **A0 未走观测法**（如 A0 靠触发分支主匹配选定流水线、尚未确认它是否已被本次 push 自动起跑）时做一次针对 `RESOLVED_PIPELINE` 的防重复触发确认，避免一次推送跑两次构建。
- **若 A0 已置 `RUN_TRIGGERED=auto`** → 本 Step A 整体跳过，直接进 Step C。
- **否则**：流水线常配「push 触发」，`RESOLVED_PIPELINE` 可能已被本轮 push 起跑——`python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode detect --commit "$GIT_PUSH_COMMIT" --pipeline "$RESOLVED_PIPELINE" --timeout 480 > memory/.aidp/cicd-detect.json` 读最近运行（命中后同 A0 代码块回写 baseline），**优先按运行 commit `== GIT_PUSH_COMMIT` 命中**（强绑定，`commit_verified=true`）；取不到 commit 时才回退弱信号（`commit_verified=false`）——弱信号的三个条件与「为何不能只看时间」见 rationale.md「自动触发运行的强弱绑定」。
  - **已自动触发**（`next_action=poll`）→ 记 `RUN_TRIGGERED=auto` + `RESOLVED_RUN_ID`（命中运行的 run id）+ `RESOLVED_RUN_COMMIT`（= 命中运行的 commit），跳过 Step B 直接进 Step C 监控**这条 `RESOLVED_RUN_ID`**。
  - **未自动触发**（`next_action=trigger`：无新运行 / **有运行却无一条 commit 等于 `GIT_PUSH_COMMIT`** / 最近运行早于本次 push）→ 进 Step B 主动触发；**绝不**把一条 commit 不符的旧运行（他人提交 / 上一版旧部署）当成本次运行放行。

**Step B — 主动触发流水线（未自动触发时）**

- **触发授权 = `cicd.auto_trigger`（默认 true，无需人工 accept；交互式与无人值守一致）**：
  - **`auto_trigger=true`** → 执行：
    ```bash
    eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
    BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
    B=$($BE get current_build --default "")
    GIT_PUSH_COMMIT=$([ -n "$B" ] && $BE --build "$B" get push_commit --default "" || echo "")
    RESOLVED_PIPELINE=$($BE get cicd_run.pipeline --default "")
    DEV_BRANCH="${DEV_BRANCH:-$(git branch --show-current)}"
    mkdir -p memory/.aidp; CJ=memory/.aidp/cicd-trigger.json
    python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode trigger --pipeline "${RESOLVED_PIPELINE:?}" --ref "$DEV_BRANCH" \
      --version "$TARGET_VERSION" --timeout 480 > "$CJ"
    # next_action=poll → 输出已带新 run_id；next_action=detect → 平台不回显 run id，用 commit 强绑定重新锁定
    if [ "$(jq -r '.next_action' "$CJ")" = "detect" ]; then
      CJ=memory/.aidp/cicd-detect.json
      python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode detect --commit "$GIT_PUSH_COMMIT" --pipeline "$RESOLVED_PIPELINE" \
        --version "$TARGET_VERSION" --timeout 480 > "$CJ"
    fi
    RID=$(jq -r '.run_id // empty' "$CJ")
    [ -n "$RID" ] && $BE set cicd_run.run_id "$RID" cicd_run.run_commit "$(jq -r '.run_commit // ""' "$CJ")"
    ```
    ⚠️ 按分支触发构建的是**分支当前 HEAD**：锁定运行后核对其 commit `== GIT_PUSH_COMMIT`，不等（期间分支又被推进）→ 记 `commit_verified=false` 并在报告中注明，不冒充本次提交的部署。
  - **`auto_trigger=false`** → **不触发**，按「冻结字段写入契约」写齐 `needs_human=true` + `aiauto_frozen_at=@now` + `freeze_reason=cicd-auto-trigger-off` + 顶层 `aiauto_blocked_reason`，发 #4 后冻结本版；`needs_human_reason` 写明「`cicd.auto_trigger=false`，需人工触发部署」+ 已解析的 `pipeline` / 待构建 commit。
  - 与 Step C 的差别：**重试**（`cicd_watch.py --mode retry`）重跑的是已失败运行的原 commit；**首次触发**跑的是分支 HEAD，二者同受 `cicd.auto_trigger` 控制。
  - 触发被平台拒绝（`--mode trigger` exit 2 / `verdict=trigger-failed`，如 GitHub Actions 未声明 `workflow_dispatch`、Jenkins Job 不允许远程构建）→ 按环境类失败处置：发 #4 说明「流水线不支持手动触发，请配置 push 触发或在平台侧开启手动/API 触发」+ 原样抄录 `reason`，冻结 `freeze_reason=pipeline-unknown`。
- 触发并锁定运行成功 → 上面代码块已写 `cicd_run.run_id` / `cicd_run.run_commit`（应 == `GIT_PUSH_COMMIT`），`RUN_TRIGGERED=manual`，进 Step C。锁定未命中（`run_id` 空）→ 出口游标留 `3.2.1-deploy`，下 tick 再 detect。


> ⬇️ **Step C（监控执行 + 失败重试）与出口 run-state 已外置到 `phase-3-6b.md`**
> （本片达 20KB 上限，按本目录二次切分约定拆）。**进入 Step C 前必须 `Read` 它**——
> 那里有 `freeze()` 四件套助手、`CICD_RETRY` 的 baseline 读回、以及按 Step C 结论分流的出口游标，
> ⛔ 都不是可选附录。
