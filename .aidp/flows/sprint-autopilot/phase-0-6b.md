# sprint-autopilot · Phase 0 详情分片 [6b/11]（0.3.4bis 自动修复复测闭环 + 0.4 项目状态检查）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的续片，承接 `phase-0-6.md`（0.3.3 版本状态机）与 `phase-0-6b2.md`（0.3.4 选版 + 熔断跳过）；**step 3bis 人工修复解冻的落点就在本片**。
> - **本片覆盖**：**0.3.4bis**「测试失败自动修复复测闭环」step 1（三分支裁定）+ step 2（派修复 → 重部署 → 铸新 build 复测）；**0.4** 项目状态检查
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：本片是该闭环 step 1/2 的**执行落点**。闭环三步（step 1/2 与 step 3bis）**必须同片承载**——只要有一步只留在命令主体正文里而没有分片落点，就是一半落地一半没落地。叠加「无人值守下 Phase 2/3 由独立子 Agent 逐片 `Read` 执行」这一事实，子 Agent 根本看不到命令正文那两段：测试链路辛苦写下的 `auto_fixable_pending=true` **无人消费**，缺陷永远停在「问题汇总清单」里，版本永不收敛，最终按 `prerelease_test_hold_streak` 12 tick 误冻结成「未收敛」。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-6b.md`。理据见同目录 `rationale.md`。

---

### 0.3.4bis 测试失败自动修复复测闭环（每 tick 跑，在 0.3.4 选完版之后、进 Phase 1 之前）

> **闭环全貌**：测试链路（`/sprint-aiauto-test` Phase 3.3）把缺陷二分类，可自动修复类回写「问题汇总清单」并置 `auto_fixable_pending=true` → **本步消费它**，派 `/sprint-bugfix` 修 → 重部署 → 铸新 build → 测试链路复测。上限 `retest_auto_cap`（默认 3）轮/人工介入周期；达上限转人工，人工修完由**本片 step 3bis** 检测新提交/新部署自动解冻。
>
> ⛔ **本步不自己跑浏览器**：只读 baseline 信号做裁定与派单，实测恒归测试链路。

#### step 1 — 判定信号 → 显式三分支裁定（不留 else 歧义）

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION}"
AFP=$($BE --version "$V" get auto_fixable_pending --default false)
NH=$($BE  --version "$V" get needs_human          --default false)
STREAK=$($BE --version "$V" get auto_retest_streak --default 0)
CAP=$($BE    --version "$V" get retest_auto_cap    --default 3)
```

**按序三选一**（⛔ 严禁把"达上限该冻结"混进"否则照常走 Phase 3"——那会既不转人工、又重部署刷新 `last_deployed_at` 干扰测试链路判据）：

| # | 条件 | 动作 |
|---|------|------|
| ① | `AFP==true` 且 `NH!=true` 且 `STREAK >= CAP` | **转人工冻结**：写 `needs_human=true` / `needs_human_kind="retest-cap"` / `retest_cap_frozen_at=@now` / `retest_frozen_head=$(git rev-parse HEAD)` + 冻结契约（`freeze_reason=unconverged` / `aiauto_frozen_at=@now` / 顶层 `aiauto_blocked_reason=frozen:unconverged@V`），发 #4 后**退出本 tick**。⛔ 不得送进正常 Phase 3。 |
| ② | `AFP==true` 且 `NH!=true` 且 `STREAK < CAP` | 进 **step 2** 自动修复闭环 |
| ③ | 其余（无 `AFP` / 已 `NH` 冻结） | 照常走 Phase 1/2/3（已冻结版本由 0.3.4 处理，含 step 3bis 的 `retest-cap` 解冻检测） |

**★ ① 的写入必须是可执行语句**（⛔ 不能只留在上面那格表格里）：`needs_human_kind` / `retest_cap_frozen_at` / `retest_frozen_head` 三个键**全仓只有 `del`、没有 `set`** 时，下面 step 3bis 的门 `needs_human_kind == "retest-cap"` **恒假、整段不可达**——「自动复测达上限 → 转人工 → 人工修完自动解冻复测」这条用户可感知的闭环就只存在于文档。

```bash
# 命中分支 ① 时执行（⛔ 每个围栏都是独立 Bash 调用，变量一律重新取回）
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
$BE --version "$V" set needs_human true needs_human_kind retest-cap \
  retest_cap_frozen_at @now aiauto_frozen_at @now freeze_reason unconverged \
  retest_frozen_head "$(git rev-parse HEAD 2>/dev/null || echo '')" \
  unconverged_frozen_head "$(git rev-parse HEAD 2>/dev/null || echo '')" \
  needs_human_reason "自动修复复测已达上限（auto_retest_streak≥CAP），转人工介入" \
  || { echo "⛔ retest-cap 冻结写盘失败，本版未冻结"; exit 1; }
# ★ 与冻结契约同口径：freeze_reason / aiauto_frozen_at / 顶层 blocked_reason 三者齐备，
#   测试链路按 unconverged 保留阻塞值、Stop hook 的冻结豁免才能成立。
$BE set aiauto_blocked_reason "frozen:unconverged@$V"
# ⛔ 冻结必须同时发 #4（口径见 phase-0-4.md）：不发 = 停了但没人知道。
python3 {{AIDP_HOME}}/scripts/notify.py --node "#4" --auto --header-color red \
  --title "自动复测达上限，转人工" --version "$V" \
  --section "连续自动修复复测已达上限，已冻结本版待人工。人工提交修复后（HEAD 变化）自动解冻复测。" || true
```

> ★ `auto_retest_streak` 是**可重置**计数（每派一轮 +1、检测到人工修复即归零 = "每个人工介入周期最多自动跑 3 轮 build"）。用累积不重置的 `builds[].retest_round` 会永久达顶、人工修复后再也拿不到配额，故上限专用本字段。

#### step 2 — 派修复（不推送）→ 铸新 build → 推送重部署 → 复测

1. **先记账再动手**（同一 tick 重入防护）：
   ```bash
   # ★ 本围栏 = 一次独立 Bash 调用：上一个围栏的 $BE / $V 一律不存活，必须重新取回。
   #   漏了这两行 → `$BE` 展开成空 → `--version: command not found` → 一字节不写 →
   #   auto_retest_streak 恒 0（三分支表的「达上限转人工冻结」永不可达）、
   #   auto_fixable_pending 永不清零（每 tick 重入「派 bugfix → 重部署 → 铸新 build」无限循环）。
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
   $BE --version "$V" set auto_fixable_pending false auto_fix_in_progress_since @now
   $BE --version "$V" bump auto_retest_streak
   $BE --version "$V" del prerelease_test_hold_streak
   ```
   修复后若仍不收敛，由测试链路在下一轮实测后**重新置真**。
   ★ `auto_fix_in_progress_since` = 「修复 + 重部署尚未完成」标记：测试链路节流门见到它且 `last_deployed_at` 早于它时**跳过本 tick**（不对旧部署整轮重测、不再置 `AFP`、不耗 `retest_auto_cap`）；新部署完成（Phase 3.2.1 写 `last_deployed_at`）时由部署出口 `del auto_fix_in_progress_since`。
2. **派 `/sprint-bugfix`** 消费「问题汇总清单」里的 `R-`/`C-` 前缀条目（双源扫描口径单一信源 = `/sprint-bugfix`，本片不复述）。**无人值守恒带 `--unattended`**；派单 prompt 显式写明「**只修复并本地 commit，⛔ 不 push**：推送由本轮 Phase 3.2 部署触发前置统一执行，带新 build」。
3. **★ 铸新 build（Phase 3.1.5，本片出口把游标推到 `3.1.5-build`）→ 再推送 + 重部署（Phase 3.2/3.2.1）**：推送的 `push_base_ref` / `push_at` / `push_commit` / `change_classification` 必须全部落到**新 build**。
   ⛔ 修复在旧 build 名下推送、或先部署后铸 build 时，推送围栏里的 `BUILD` 会回落到 `versions.{V}.current_build` = **上一轮那个 `status=tested` 的旧 build**，
   新 build 缺这些键 → Phase 3.7 的「`PROBE_COMMIT != PUSH_COMMIT` → `PROBE_PASSED=0`」与 `cicd_skipped` 判据取空误判，游标卡在 `3.2.1-probe`。
4. **重部署**：按 `deployment.mode` 与 `--skip-deploy` 走 Phase 3.2/3.2.1 既有路径，不另起流程。
5. **复测恒是【新 build】**：旧 build 一旦 R-4 finalize 即冻结（报告不可变铁律），**绝不在旧 build 上重测重写**；测试链路去重门要求 `last_deployed_at` 晚于新 build 的 `started_at` 才开测。
6. **全自动、不弹窗**：本闭环在 `/loop` 与交互式单次调用下**都自动执行**，⛔ 不得 `AskUserQuestion` 征询"要不要自动修"——它是每 tick 的默认仪式、不是用户决策点（同理：也**不得**把它做成 Phase 3.0 `AskUserQuestion` 的第三个选项，见 `phase-3-2.md` 入口模式二选一铁律）。

---

### step 3bis ★ `retest-cap` 冻结的人工修复解冻检测（0.3.4 熔断跳过时就地执行）

`needs_human_kind == "retest-cap"` 的版本，在 0.3.4 把它从候选**剔除之前**先做一次
「人工修复完成检测」——命中任一即**解冻、不剔除**：

| # | 判据 | 含义 |
|---|---|---|
| ① | `HEAD` ≠ `retest_frozen_head` **且** `HEAD` ≠ `last_autopilot_head` | 冻结之后有**人**提交过（不是 autopilot 自己推的） |
| ② | `last_deployed_at` 晚于 `retest_cap_frozen_at` | 冻结之后发生过新部署 |

判据统一由 `autopilot_unfreeze.py::aiauto_probe` 执行，与批量探针同源；先读取探针结果，命中后才清理冻结与配额：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
RETEST_PROBE=$(python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --aiauto-probe "$V" --json) || exit 1
CAN_UNFREEZE=$(printf '%s' "$RETEST_PROBE" | python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("unfreeze") is True))') || exit 1
[ "$CAN_UNFREEZE" = 1 ] || { echo "复测配额仍冻结：无有效恢复证据"; exit 0; }
# ★ 冻结四件套 + retest-cap 专属三件，成套清；⛔ 尤其不能漏 auto_retest_streak：
#   它是累加型字段，不归零则人工介入后恒 = cap，
#   下一轮一有可修复缺陷就立刻再撞上限转人工，「每周期最多自动跑 3 轮」退化成 0 轮。
$BE --version "$V" del needs_human needs_human_reason needs_human_kind \
  aiauto_frozen_at freeze_reason retest_cap_frozen_at retest_frozen_head auto_retest_streak
case "$($BE get aiauto_blocked_reason)" in *"@$V") $BE del aiauto_blocked_reason;; esac
echo "♻️ $V retest-cap 解冻：检出人工修复信号，配额已归零，重回候选铸新 build 复测"
```

无修复信号则照常剔除等待，**不刷 #4**。

> ⚠️ `retest_frozen_head` 是**冻结时刻的快照**（与活指针 `last_autopilot_head` 不同），
> 判据 ① 两者都比才成立——只比活指针会在 autopilot 自己 push 后误判成"人来修过了"。

---

> ⛳ **本片把游标交给 Phase 3 后即退出**：0.3.4bis 属 Phase 0 内的裁定与派单，但**必须可执行地把游标推到 Phase 3**，
> 否则本轮走完 Phase 0 就没有下文（闭环三步全在 Phase 3）。step 2 派单后落：
>
> ```bash
> # ⛔ 新围栏 = 新 Bash 调用：$V 必须先取回，否则 `--version ""` → rc=1，
> #    本围栏两行**都写不进去** → 游标推不到 3.1.5、自动复测闭环派完单就没有下文。
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
> V="${TARGET_VERSION:?TARGET_VERSION 取空，拒绝写入 baseline}"
> # ★ 同时把 ENTRY_MODE 落成 incremental：复测轮没有未关闭 Sprint，
> #   留在 full 会让 3.1.5 出口按「该有 Sprint 却没有」处理；命令正文说的「走增量分支」由这两行落盘兑现。
> python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" \
>   set autopilot_entry_mode incremental
> python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot ENTRY_MODE incremental
> python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" run-state "3.1.5-build" "3.1.5-build"
> ```
>
> 此后游标推进由其消费的各 Phase（3.1.5 / 3.2 / 3.2.1 / 3.4）各自出口负责。

---

### 0.4 项目状态检查

1. `git status --porcelain` 非空（含未 commit 改动）→ **按上方 0.1「脏树决策门」处理（交互三选一 / `/loop` 无人值守走安全默认），不静默退出**
   - **例外**：`PRD_ROOT` 内任一版本子目录的 unstaged 改动**允许**（命令的检测目标就是 PRD 改动）
2. **项目工作分支偏好 + 部署源对齐**：
   - **解析 DEV_BRANCH**：先按 `{{AIDP_HOME}}/reference/agent-tools.md` 的一次选择协议读取 `development.branch_policy`。已选 current → 沿用本任务当前分支，包括 main/master，不自动建/切分支；已选 new → 顶层开发任务创建一次并保存任务/分支关联，后续 tick、Sprint、BUG 修复及子 Agent 全部继承。只读测试链不创建分支。
   - **未选择**：交互式仅问当前/新分支两项并保存；无人值守返回 `needs-choice`，交已有配置缺失处置，不猜 current、不猜 feature。脚手架已记录偏好则不再问。`deployment.branch_strategy` 的 current/feature/指定名仅作既有部署配置提示，不能覆盖项目工作偏好；发现矛盾先核实，不据此自动新建或切走任务分支。
   - **读部署源 ref（DEPLOY_SOURCE_REF）**：`mode=local`/`none`/`manual-script` → 构建工作树/本地脚本、无远程分支约束（DEV_BRANCH 沿用已选工作策略）；`mode=cicd-provider`（已配置 `cicd.pipelines`）→ 经 **Phase 3.2.1 Step A0 流水线解析**（优先观测本次提交起跑的流水线运行、再取其构建分支核验）确定；`git-push`/`ci-pipeline` 未配置 `cicd.pipelines` → CI 监听的固定分支（一般 = 部署环境对应分支，如 master；无法自动读则询问/取当前分支）。
   - **一致性前置校验门**：DEV_BRANCH == DEPLOY_SOURCE_REF → 通过；不一致时保持已选工作分支。已有明确合并授权则记录 `PENDING_MERGE_TO`；否则交互式只确认本次部署方案（授权合并到部署源 / 使用构建当前分支的流水线 / 暂停部署），不重复询问开发偏好。无人值守无合并或流水线授权时按部署配置缺失处置，不能靠自动切分支、合并或更改永久偏好绕过。仅经上述授权后执行以下落盘：
     ```bash
     # DEPLOY_SOURCE_REF 由上一条「读部署源 ref」得出（流水线运行的构建分支 / 本地模式为空），
     # 由执行体就地代入字面量；⛔ 空值不落盘（落空串等于没记，反而掩盖"该合并却没合"）。
     DEPLOY_SOURCE_REF=""   # ← 执行体代入上一条读到的部署源 ref
     [ -n "$DEPLOY_SOURCE_REF" ] && python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py \
       set --command autopilot PENDING_MERGE_TO "$DEPLOY_SOURCE_REF" >/dev/null 2>&1 || true
     ```
   **绝不**把代码放到部署流水线永不构建的分支、也**绝不**等到部署阶段才作为 blocker 发现。
   - **就绪探针目标一致**：校验 `cloud_ready_*` URL host 与 `cloud_deploy_url` host 同源（都指向"新代码将部署到"的环境），不一致 WARN（避免探到部署了旧代码的另一环境得假绿）。
   - **边界仍守**：部署切分支/合并必须有对应授权，不得暗改工作偏好；**绝不打 tag**（独立发布授权）。
3. **活跃 Sprint = 在途工作，不是待自动归档垃圾**。读取项目记忆当前版本/编号，并运行 `check_open_sprints.py --version {TARGET_VERSION} --scope started --json`；退出码 2 为读取失败，不当空集。
   - 无活跃 Sprint → `python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py stale-active-sprint || true` 后继续。
   - 交互式（`LOOP_UNATTENDED=0`）→ 提示用 `/sprint-full {NNN} --resume` 继续；只有开发与验证证据齐全才可 close。
   - 无人值守：仅当**项目记忆版本 = TARGET_VERSION、唯一 open 编号 = 当前 active 编号**，并通过 `/sprint-full` 的 `--resume` 恢复门（Read 该命令并先执行其 `resume-gate`）才恢复。多个在途、跨版本/用户、游标指向另一个 Sprint 或读取失败均不自动接管。已有 `run_state.next_sprint` 为空可由已核实编号恢复；非空且不同（含 `done`）须报冲突。
   - 校验成功后执行下面围栏，将已核实编号交给 Phase 3.2（**不在 Phase 0 关闭 Sprint**）：

   <!-- resume-state -->
   ```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
   OPEN_JSON=$(python3 {{AIDP_HOME}}/scripts/check_open_sprints.py --version "$V" --scope started --json); RC=$?
   [ "$RC" = 1 ] || { echo "恢复状态已变化或读取失败，请重新核验"; exit 1; }
   SPRINT_NO=$(printf '%s' "$OPEN_JSON" | python3 -c 'import json,sys; x=json.load(sys.stdin)["open"]; assert len(x)==1; print(x[0].removeprefix("Sprint-"))') || exit 1
   CURSOR=$($BE --version "$V" get run_state.next_sprint --default "")
   [ -z "$CURSOR" ] || [ "$CURSOR" = "$SPRINT_NO" ] || { echo "resume-conflict: Sprint 游标不一致"; exit 1; }
   python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot ENTRY_MODE full || exit 1
   $BE --version "$V" set autopilot_entry_mode full || exit 1
   # 已有 build 直接续 dev；手工启动而尚无 build 的，先过规划/铸 build 仪式。
   BUILD=$($BE --version "$V" get current_build --default "")
   NEXT_PHASE="3.1-plan"; [ -n "$BUILD" ] && NEXT_PHASE="3.2-dev"
   # 仅修复续跑指针；run-state 会增加进入次数/写完成时间，留给 Phase 3 的实际派发处理。
   $BE --version "$V" set run_state.next_phase "$NEXT_PHASE" run_state.next_sprint "$SPRINT_NO" || exit 1
   python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py stale-active-sprint || true
   ```

   Phase 1 续跑门据此强制执行；Phase 3.2 派 `/sprint-full {NNN} --resume --unattended --from-batch`，走 dev→test→bugfix→close，保留当前 build 和已有上下文。`--skip-dev` 本轮不恢复开发、不自动关闭，保持在途并报告冲突；不得用它把未交付 Sprint 送入部署。
   - 任一恢复前置失败 → **实际执行** `python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --preflight --command autopilot --reason stale-active-sprint --why "active Sprint 恢复校验失败：附本轮版本/编号/用户或游标冲突证据"` 后结束本 tick（0=已记账、3=已冻结告警、2=入参错须修正）；恢复执行失败由 Phase 3.2 原有 `dev_fail_streak` 与 stuck 门记账，不伪造关闭记录。
