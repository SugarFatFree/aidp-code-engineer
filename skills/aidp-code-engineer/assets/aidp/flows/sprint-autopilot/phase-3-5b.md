# sprint-autopilot · Phase 3 详情分片 [5b/13]（3.2 步骤 2–4：批量执行 + 推送 + 部署动作 + #2 通知）

> 本文件是 `phase-3-5.md` 的**二次切分**（前片达 20KB 上限）。前片覆盖 3.2 步骤 0–1 与**出口 run-state 写盘**；
> 本片覆盖 **步骤 2（`/sprint-batch` 执行）/ 步骤 2.5（推送、部署前安全网、部署动作与交接信号、#1d）/ 步骤 3（#2 通知）/ 步骤 4（`--single-sprint`）**。
> ⚠️ **权威性**：与前片同级，不得因它是续片而略过任一项；本片执行完回 `phase-3-5.md` 执行出口。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-5b.md`。理据见同目录 `rationale.md`。

---

2. **跑 `/sprint-batch --skip-context-check --skip-aiauto-test --unattended`**（`--batch-one-tick` / 交互式路径；内部按其「零询问连跑铁律」严格 for 循环跑完研发执行计划全部 Sprint）：
   - ⛔ 必传 `--unattended`；所有交互门（含未枚举的范围/进度确认）均不得弹出，增量路径调用 `/sprint-dev`/`/sprint-bugfix` 同样必传。`HAS_WAKE_SOURCE=1` 可跨 tick 自动续跑，但不得向人征询。
   - ⛔ 必传 `--skip-context-check --skip-aiauto-test`：前者跳过 compact 询问，后者把部署与浏览器测试留给本命令及独立 `/sprint-aiauto-test`，并保持 AI 执行报告骨架由 autopilot 产出。
   - `/sprint-batch` 连跑全部 Sprint，不问起始 Sprint 或是否继续；`--single-sprint` 仅用于 autopilot 单 Sprint 路径。本片无 `--skip-dev` 分支，`test-only` 已在 `phase-3-2.md` 前置分流。
   - 每个 Sprint：`/sprint-start` → `/sprint-dev` → `/sprint-test`（仅静态扫描）→ `/sprint-bugfix` 循环 → `/sprint-close`；浏览器测试归 `/sprint-aiauto-test`。


2.5 **★ 部署触发前置 → 部署前安全网 → 部署动作（任何开发路径完成后都从这里执行：`/sprint-batch`、逐 tick 单 Sprint 全部关闭、incremental、自动修复复测轮；⛔ 不属于 `/sprint-batch` 步骤）**

   > **`vcs_mode=none` 独立出口（优先于下方 Git 推送围栏）**：开发/测试/Sprint 关闭成果仍留在本地。对提交、推送、推送分类、远端 CICD 各节点写当前 build `steps[]` 为 `status=skipped`、`reason=unsupported:vcs-disabled`，baseline 同步保留未推送事实；不执行 `git status/add/commit/push`，不伪造 `push_commit` / `push_at` / `cicd_skipped=true`（该字段只表示 Git push 后按内容分类跳过 CICD）。`mode=local` 不经过 Git/CICD，必须探本地服务真实就绪（启动命令成功不等于就绪）；就绪后按下方「部署完成 → 落盘交接信号」写 `last_deployed_at` + `phase_beta_done_at` 并记录本地探活 URL/结果，未就绪则不得写证据或交接测试；依赖 Git push 的 cloud 路径只记未部署，不写 `last_deployed_at` / `phase_beta_done_at`，不发 #1d 部署成功通知，不启动对旧代码的浏览器测试。随后继续 Phase 3.3 本地审计、Phase 3.4 报告和收尾；不得因跳过 Git 节点冻结本地开发。`git` 时执行下方原围栏。

   - **★ 部署触发前置：开发成果提交 + 分类 + 推送（确定性步骤，绝不可省）**：dev 循环 /（incremental）增量改动完成后、执行下方「部署动作」**之前**，必须把本轮改动提交并推到 origin。本步以 `git status --porcelain` 为准兜底，不依赖子命令是否已提交：
     1. **授权即入口**：用户执行 `/sprint-autopilot` 即授权自动 `git add`+`commit`+`push` 到本轮解析出的 **DEV_BRANCH**。只 push DEV_BRANCH；按 Phase 0.4 的 `PENDING_MERGE_TO` 对齐部署源；绝不打 tag。
     2. **确定性提交**：在提交前先确定本次 push 的分类基准并写入当前 build，再决定是否提交：
        ```bash
        eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
        BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
        : "${TARGET_VERSION:?}"; : "${BUILD:?}"
        DEV_BRANCH="${DEV_BRANCH:-$(git branch --show-current)}"
        BASE_REF=$(git rev-parse "origin/${DEV_BRANCH}" 2>/dev/null || true)
        [ -n "$BASE_REF" ] || BASE_REF=$(git rev-parse HEAD 2>/dev/null || true)
        $BE --version "$TARGET_VERSION" --build "$BUILD" set push_base_ref "$BASE_REF"
        git status --porcelain
        # porcelain 非空时：git add -A + git commit（消息按 full/incremental 模式生成，末尾带 Co-Authored-By）
        ```
        commit 前按约定 24 跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 读 JSON：退出码 3/4 = 本轮结束前有义务未落地（约定 22 台账积压 → 派台账收口子 Agent；CICD 推送欠账 → 补监听），不是禁止 commit。porcelain 为空时跳过提交。首次提交没有 HEAD 时 `BASE_REF` 为空，显式传空基准会 fail-closed。
     3. **push 前分类（唯一入口）**：在 `git push` 前执行，始终显式传入提交前保存的 `BASE_REF`（不能在提交后用默认 `HEAD` 推断）：
        ```bash
        eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
        BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
        : "${TARGET_VERSION:?}"; : "${BUILD:?}"
        BASE_REF=$($BE --version "$TARGET_VERSION" --build "$BUILD" get push_base_ref --default "")
        CLASSIFY=(python3 {{AIDP_HOME}}/scripts/classify_push.py --root .
          --version "$TARGET_VERSION" --build "$BUILD" --base-ref "$BASE_REF")
        "${CLASSIFY[@]}"
        CLASSIFY_RC=$?
        ```
        该命令内部必须调用 `classify_push.py --root . --version "$V" --build "$B"`（⛔ 不是 `classify_commit_change.py`，那个不落盘），完整结果写入当前 build。命令失败、JSON 缺字段或 baseline 无法落盘都按 **fail-closed** 处理：不得跳过监听，后续按正式代码路径执行。
     4. **确定性推送与分流**：`cicd_skipped=true` 且无错误时也必须成功 push，但跳过远端 CICD、部署等待和探针；不得用远端状态反推分类。分类为正式代码或错误时进入原有监听/重试/探针。若 `PENDING_MERGE_TO` 已声明部署源，先推 feature，再执行实际合并与推送：
        ```bash
        # ★★ 本围栏 = 独立 Bash 调用：$DEV_BRANCH / $BE / $BUILD 一律不存活，必须先取回
        #    （eval 必须在 git push **之前**；根因见 rationale.md「推送围栏的三个取空」）
        eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
        BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
        DEV_BRANCH="${DEV_BRANCH:-$(git branch --show-current)}"
        : "${TARGET_VERSION:?}"; : "${BUILD:?}"; : "${DEV_BRANCH:?取不到分支名，拒绝 push}"
        git push origin "$DEV_BRANCH" || exit 1
        PENDING_MERGE_TO="${PENDING_MERGE_TO:-}"
        if [ -n "$PENDING_MERGE_TO" ] && [ "$PENDING_MERGE_TO" != "$DEV_BRANCH" ]; then
          git fetch origin "$PENDING_MERGE_TO"
          git switch "$PENDING_MERGE_TO" && git pull --rebase origin "$PENDING_MERGE_TO"
          MERGE_BASE_REF=$(git rev-parse HEAD)
          git merge --no-edit "$DEV_BRANCH"
          python3 {{AIDP_HOME}}/scripts/classify_push.py --root . --version "$TARGET_VERSION" --build "$BUILD" --base-ref "$MERGE_BASE_REF" || exit 1
          git push origin "$PENDING_MERGE_TO" || exit 1
        fi
        GIT_PUSH_AT=$(date -Iseconds); GIT_PUSH_COMMIT=$(git rev-parse HEAD)
        $BE --version "$TARGET_VERSION" --build "$BUILD" set push_at "$GIT_PUSH_AT" push_commit "$GIT_PUSH_COMMIT"
        ```
     5. **失败兜底（不静默继续）**：push 失败（无 remote / 认证失效 / 非快进被拒）→ 绝不带着"未推送"继续进部署动作，走「失败处置」#4 通知 @用户介入，暂停本轮。
   - **★ 部署前安全网（在「部署动作」之前跑，⛔ 不可省）**：按 `{{AIDP_HOME}}/flows/sprint-batch/step-6.md` 的 **Step 6.0.5「SQL 已应用校验」+ 6.0.6「部署流程文档校验」**就地执行同款校验（判据以该文件为单一信源）。根因见 rationale.md「部署前安全网为何要在 autopilot 侧再跑一次」。
   - **部署动作**仍由本命令完成（按 `autopilot_decisions.deployment` 字段）：
     - **`--skip-deploy` 分支（用户主动跳过部署阶段）**：跳过部署、不写 `last_deployed_at`、不发 #1d；等效本轮 `mode=none` 行为，仅开发 + 静态自测
     - `mode=local`（★ 无人值守铁律：**后台启动 + 幂等复用**，否则 `/loop` 会挂死或刷屏）：**先探端口/进程 → 已在跑即复用、未跑才后台启动**（`nohup … &` + 写 PID、绝不前台常驻；探活与启动细则见 rationale.md「本地 dev server 幂等复用」）。
     - `mode=cloud`：按 `cloud_deploy_trigger` 触发部署后写 baseline `last_deployed_at`（aiauto-test 读它触发测试）：
       - **`cicd-provider`（PRD 显式声明由 CICD 流水线部署，平台 = `cicd.provider`，默认 GitHub Actions）→ 走下方 Phase 3.2.1 流水线编排 + 部署就绪探针**。
       - **`git-push` / `ci-pipeline`（推送即触发 / 外部 CI 被动触发）——按是否已接入 CICD 流水线二分（★ git-push 触发型的部署失败同样要监控/重试）**：
         - **已接入**（`memory/aidp-config.yaml` 的 `cicd.provider` ≠ `none`、`cicd.pipelines.<env>` 已配且提供方 CLI/凭据可用）→ 走 3.2.1 编排；判据细节见 `rationale.md`「部署动作的「已接入 CICD」判据」。
         - **未接入**（`provider=none` / 无 `cicd.pipelines.<env>` / 提供方 CLI·凭据不可用，即 `cicd_watch.py` 退出码 3）→ 无远端流水线可监控/重试；但**部署就绪仍应把关，别让测试链路对没起来的环境空跑**：详见同目录 `rationale.md`「部署分支的未配置 CICD 回退与 #1d 通知模板要点（phase-3-5b.md 的外置正文）」。
       - **`manual-script`（命令调 `cloud_deploy_script`）→ 直接写 `last_deployed_at`**、就绪探测留给 aiauto-test（本地脚本部署，无远端流水线可监控）。
       - 走 Phase 3.2.1 的分支：流水线成功**只代表部署完成、不代表可测** —— 必须先过部署就绪探针（判据与登录系统的特例见 `rationale.md`「部署完成 ≠ 可测」），探针过了才放行测试链路。
     - `mode=none`：跳过部署，里程碑通知里标"静态仅"
   - **部署完成 → 落盘交接信号**（⛔ **可执行语句，不是散文从句**）：`phase_beta_done_at` 是测试链路
     `baseline_edit.py current-version` 的**选版判据**，只在 Phase 3.2.1 Step D 那一条云端路径上被写过；
     `local` / `manual-script` / 未接入 CICD 的 `git-push` 三条路径下它恒空 → 测试链路每 tick 选不出版本、
     静默 `exit 0`，而开发链路因心跳仍在而判「测试链路健康」，**两条 loop 都在刷屏、什么都没测**。
     故凡走到"写 `last_deployed_at`"的分支，都必须同时写它：

     ```bash
     eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
     python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "${TARGET_VERSION:?}" \
       set last_deployed_at @now phase_beta_done_at @now
     # 新部署落地 = 自动修复闭环的「修复 + 重部署」完成 → 清进行中标记，测试链路对新部署复测
     python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del auto_fix_in_progress_since || true
     ```
     （走 Step D 的分支由该 Step 统一落盘，不重复写。）
   - **★ 里程碑通知 #1d 部署完成-代码已推送（见 0.1bis #1d 部署完成通知模板）**：详见同目录 `rationale.md`「部署分支的未配置 CICD 回退与 #1d 通知模板要点（phase-3-5b.md 的外置正文）」。

3. **里程碑通知 #2（每个 Sprint 关闭时，见 0.1bis）**——`/sprint-close` 成功后立即发送（**逐 tick 单 Sprint 与一 tick 跑满两种粒度都在每个 Sprint 关闭时发**）（公共字段 + 下列内容）：
   ```
   ✅ {项目名称} {TARGET_VERSION}_Build{N} · Sprint-{NNN} 已关闭（{已完成 Sprint 数}/{N}）
   功能：{Sprint 主标题}
   测试通过率：{X}%（静态 {a}/{b}）
   bugfix 轮次：{R}
   下一步：自动进入 Sprint-{NNN+1}
   ```

4. **`--single-sprint` 模式特殊处理**：每次 #2 通知后暂停，等用户在当前会话回 `continue` 才进下一 Sprint（里程碑通知是单向推送，不从通知渠道读回复）；30 分钟无响应自动暂停（不退出、保留状态）。
    - ⚠️ **无人值守下 `--single-sprint` 与默认同行为**（无人可答「回 `continue`」，且 `HAS_WAKE_SOURCE=1` 时逐 tick 单 Sprint 本就是默认）；⛔ `HAS_WAKE_SOURCE=0` 时它同样不得 yield，本轮内连跑到底。完整论证见 `rationale.md`「`--single-sprint` 在无人值守下…」。
