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

命中后的动作（三件，缺一不可）——**必须可执行地落盘，⛔ 散文不算动作**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:?}"
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
2. **分支策略 + 部署源对齐（★ 不无条件强制建 feature 分支；dev 代码必须落到"部署实际构建的那个分支"，否则代码搁浅、部署拿不到、autopilot 到部署阶段才卡死）**：
   - **解析 DEV_BRANCH**（本轮代码落哪，按 `deployment.branch_strategy`）：
     - `current`（默认，尊重"直接提交部署源分支"的项目约定）→ **就在当前分支开发**（哪怕是 master/main），**不强制建 feature 分支**；PRE_RELEASE 阶段也在当前分支跑。
     - `feature` → 建/切 `feature/autopilot-{TARGET_VERSION}`；**但必须同时确定"合并回部署源"策略**（见下一致性校验），否则代码会搁浅在部署永不构建的分支上。
     - `<指定分支名>` → 建/切该分支。
     - **留空 = 自动推断**：读**部署源 ref（DEPLOY_SOURCE_REF，见下）**——当前分支 == 部署源 → 取 `current`；否则**交互式** `AskUserQuestion` 三选一（current / feature+合并 / 指定分支），**`/loop` 无人值守**默认收敛到 `current`（最保证"部署拿得到代码"）并终端 WARN。⛔ **严禁在 master 上无条件建 `feature/autopilot-{V}`**：它 + 不自动 merge master + 部署源是 master 三者组合会造成"dev 完成却部署不了"的死结，且要到部署阶段才暴露。
   - **读部署源 ref（DEPLOY_SOURCE_REF）**：`mode=local`/`none`/`manual-script` → 构建工作树/本地脚本、无远程分支约束（DEV_BRANCH 自由，默认 current）；`mode=cicd-provider`（已配置 `cicd.pipelines`）→ 经 **Phase 3.2.1 Step A0 流水线解析**（优先观测本次提交起跑的流水线运行、再取其构建分支核验）确定；`git-push`/`ci-pipeline` 未配置 `cicd.pipelines` → CI 监听的固定分支（一般 = 部署环境对应分支，如 master；无法自动读则询问/取当前分支）。
   - **★ 一致性前置校验门（共同根因：dev 分支 → 部署构建源 三者闭环一致，矛盾前置暴露、不拖到 Phase 3.2 部署）**：DEV_BRANCH == DEPLOY_SOURCE_REF → 通过（部署拿得到本轮代码）；**不一致** → **交互式** `AskUserQuestion`（①改 `branch_strategy=current` 在部署源分支直接开发·推荐最省事 ②保留 feature 分支并记 `PENDING_MERGE_TO=<DEPLOY_SOURCE_REF>`、Phase 3.2 push 前先合并回部署源 ③换一条构建源 ref==DEV_BRANCH 的流水线）；**`/loop` 无人值守**：PRD 已声明 feature+合并 → 记 `PENDING_MERGE_TO`；否则默认收敛 `current` + WARN。★ **「记」= 可执行落盘，不是散文**（⛔ 不落盘则 Phase 3.2 的合并段整段不可达）：
     ```bash
     # DEPLOY_SOURCE_REF 由上一条「读部署源 ref」得出（流水线运行的构建分支 / 本地模式为空），
     # 由执行体就地代入字面量；⛔ 空值不落盘（落空串等于没记，反而掩盖"该合并却没合"）。
     DEPLOY_SOURCE_REF=""   # ← 执行体代入上一条读到的部署源 ref
     [ -n "$DEPLOY_SOURCE_REF" ] && python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py \
       set --command autopilot PENDING_MERGE_TO "$DEPLOY_SOURCE_REF" >/dev/null 2>&1 || true
     ```
   **绝不**把代码放到部署流水线永不构建的分支、也**绝不**等到部署阶段才作为 blocker 发现。
   - **就绪探针目标一致**：校验 `cloud_ready_*` URL host 与 `cloud_deploy_url` host 同源（都指向"新代码将部署到"的环境），不一致 WARN（避免探到部署了旧代码的另一环境得假绿）。
   - **边界仍守**：切分支/合并只为"部署源对齐"这一目的；**绝不打 tag**（人工 destructive 动作）。
3. `AGENTS.md`「当前状态」有活跃 Sprint 的处置——**按是否无人值守分两条路，不得只写"退出提示"**：
   - **交互式（`LOOP_UNATTENDED=0`）**：退出，提示先 `/sprint-close`。
   - **★ `/loop` 无人值守（`LOOP_UNATTENDED=1`）**：**自动收口**——调 `/sprint-close --unattended` 把上一 tick 中断遗留的 Sprint 归档，成功即继续本 tick；与 0.5bis D3「上版收口自动收口、不问」同口径。
     收口失败 → 计入顶层 `preflight_fail_streak`（复用 0.1 的熔断记账，`preflight_fail_reason="stale-active-sprint"`），达阈冻结并发一次 #4。
     **★ 收口成功 / 本就无活跃 Sprint → 必须解冻**：`python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py stale-active-sprint || true`。0.1 的清零 case **只认它自己那 6 个 git 类 reason**，本 reason 落 `*)` 分支被明文"留给其成功路径清"——**这里就是那个成功路径**。缺这一行：遗留 Sprint 收口好了冻结也不解除，每 tick 在 0.1 静默 exit，唯一出路是 `--reset-baseline`（毁掉整份 baseline）。
     ⛔ **绝不静默退出**：只写"退出提示先 close"而无无人值守分支 = 上一 tick 一旦中断留下未 close 的 Sprint，此后**每 tick 都在这里静默退出**，既不推进、也不告警、更不熔断（7×24 表现为"挂着但什么都不干"）。
   - 无活跃 Sprint → OK
