<!-- 本文件是 `/sprint-autopilot` Phase 0.3.4 的执行分片，由 `phase-0-6.md` 指向。 -->

# sprint-autopilot · Phase 0.3.4：选版 + 熔断冻结跳过 / 解冻

> 本片覆盖 **Phase 0.3.4** 全文。前置 0.3.1–0.3.3 与后续 0.3.5 决策矩阵见 `phase-0-6.md`。
> ⚠️ **权威性**：进入 0.3.4 后以本文件为准逐项执行。理据见同目录 `rationale.md`。

#### 0.3.4 识别"最近的一对"（用户已确认：只跑最近一对）

按 SemVer 倒序遍历所有版本，找出：

- **PRE_RELEASE_VERSION**（上版准发布候选）：第一个状态 = S2 的版本
- **TARGET_VERSION**（下版全流程候选）：**先看 `run_state` 再看 S 态**——
  1. **★ 尾段续跑优先（不论 S 态）**：`run_state.next_phase ∉ {"", "done"}` 的版本最优先作 TARGET——（见 rationale.md「尾段孤儿」）。**⛔ 但该版 `== PRE_RELEASE_VERSION` 且 `run_state.next_phase` 是 Phase 2 的 hold 游标（`2-prerelease`）时排除它**（见 rationale.md「hold 游标」）。
   ⛔ 排除**限定到 hold 游标**、不可按 `== PRE_RELEASE_VERSION` 一刀切（开发尾段游标下该版仍须可作 TARGET；见 rationale「S2 尾段孤儿」）。
  2. **★ 复测待办优先**：`auto_fixable_pending == true` 且 `needs_human != true` 的版本**入选 TARGET、不论 S 态**——⛔ 不可省，根因见 `rationale.md`「复测闭环进不了 Phase 3」。
  3. 否则：第一个状态 ∈ {S0, S1} 的版本（如有 S0 优先于 S1，因为 S0 是"新提"需求）

★ **熔断冻结跳过**：候选筛选先读 `.versions."<V>".needs_human`——**为 true 即从 PRE_RELEASE / TARGET 候选剔除**；写入方齐备性由 `check_freeze_contract.py` 守。**解冻**：新部署自动解冻 / 人工清 `needs_human` / `--reset-baseline` / **`--target <V>` 显式点名**（根因见 `rationale.md`）：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
if [ -n "${TARGET_FLAG_VALUE:-}" ]; then
  TARGET_VERSION="$TARGET_FLAG_VALUE"; BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
  # ⛔ 清单与解冻块同源，漏一个计数 = 刚解冻又达阈重冻（理据见 rationale）。
  $BE --version "$TARGET_VERSION" del needs_human needs_human_reason \
    needs_human_kind aiauto_frozen_at freeze_reason \
    dev_fail_streak dev_fail_phase auto_retest_streak retest_cap_frozen_at retest_frozen_head \
    env_reprobe_attempts env_reprobe_last_at env_reprobe_exhausted_at \
    test_loop_missing_streak probe_fail_streak push_probe_fail_streak \
    cicd_unreachable_streak cicd_cli_fail_streak \
    prerelease_deploy_block_streak prerelease_test_hold_streak
  # ⛔ 这两个字段必须用 `set run_state.*` 写：`run-state` 的签名是
  #   `run-state <current_phase> <next_phase> [next_sprint]`，按 key/value 传会把状态机写成
  #   `current_phase=phase_enter_count / next_phase=1 / next_sprint=phase_first_entered_at`，
  #   且 rc=0（`|| true` 更盖住）—— 续跑短路门与 Stop hook 的 yield 豁免都会被这堆乱值误触发。
  $BE --version "$TARGET_VERSION" set run_state.phase_enter_count 1 run_state.phase_first_entered_at @now || true
  case "$($BE get aiauto_blocked_reason)" in *"@$TARGET_VERSION") $BE del aiauto_blocked_reason;;esac
  echo "🔓 --target $TARGET_VERSION：已解冻，绕过本段剔除"
fi
```

环境类另有指数退避自动复探、配置类另有 mtime/心跳（见下）。**★ `retest-cap` 特例**：剔除前先做「人工修复完成检测」，命中即解冻重回候选——**单一信源 = `phase-0-6b.md`「step 3bis」**。

> ⛔ **★ 环境类冻结的自动复探（堵"解冻条件永不达成"的死循环）**：`freeze_reason` 为**环境类**（枚举权威表见 `/sprint-aiauto-test` `rationale.md`，含 `cicd-unreachable` / `cicd-cli-unavailable`）的冻结由脚本按**指数退避**复探——冻结后第 n 次复探的最早时刻 = 冻结时刻 + min(20min × 2^n, 4h)，最多 10 次，用尽转人工（发一次告警，`autopilot_unfreeze.py --manual <V>` 可解）。类别从枚举表实时解析，⛔ 本片不手抄 case 列表。
>
> ```bash
> # 剔除【之前】对**全部**被冻版本逐个复探（被冻版本已被候选剔除，只探本轮目标版本探不到它们）
> for _v in $(python3 - <<'PY' 2>/dev/null
> import json
> try:
>     b = json.load(open("memory/.sprint-autopilot-baseline.json"))
> except Exception:
>     b = {}
> print(" ".join(v for v, o in (b.get("versions") or {}).items() if isinstance(o, dict) and o.get("needs_human")))
> PY
> ); do
>   # --apply：到期即删冻结字段 + 以 @<V> 结尾的顶层 aiauto_blocked_reason，并累加复探次数
>   python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --env-reprobe "$_v" --apply --json 2>/dev/null \
>     | python3 -c "import json,sys;d=json.load(sys.stdin);print('🔓 %s 环境类冻结（%s）第 %s 次复探放行' % ('$_v', d.get('reason'), d.get('attempts')) if d.get('applied') else ('⏸️ $_v 环境类复探已用尽，转人工' if d.get('exhausted') else ''))" 2>/dev/null || true
> done
> ```
>
> 复探放行后仍失败会按原路径（streak 记账 → 达阈）重新冻结，下一次复探间隔翻倍，**不会**变成无节制重试。**非环境类**（`unconverged` / 交接类 / 配置类）不走本复探——它们的解冻信号是代码提交、配置文件 mtime 或人工介入。**唯一例外 = `config-missing`，见下条**。

> ⛔ **★ 配置类冻结的解冻**：配置修复不产生新部署。`cicd-auto-trigger-off` 按 `memory/aidp-config.yaml` mtime（冻结后改过配置即视为已处置）；其余配置类按配置源 mtime；`config-missing` 按心跳判。⛔ 本块必须留在 autopilot 侧，详见 `rationale.md`。
>
> ```bash
> # 剔除【之前】先探：解冻证据的判定**下沉到脚本**（各 freeze_reason 归哪一类、认什么证据，
> # 单一信源 = flows/sprint-aiauto-test/rationale.md「冻结分类」表）。⛔ 不得内联复写（理据见 rationale.md）。
> # ★ $V 与 $BE 都必须在**本围栏**取回（围栏间 shell state 不共享）：
> #   $V 取空 → UNFZ 空 → if 恒假 → 配置类冻结修好了也永不解冻（理据见 rationale）。
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
> # ⛔ 这里**不能用 `:?`**：`autopilot.target_version` 要到本步末尾才落盘，首 tick /
> #   刚跑过 `--reset-baseline` 时它恒空 —— `:?` 会让非交互 shell 当场退出，连同下面那段
> #   **专为「被冻版本已被选版剔除、只探 $V 探不到」而写的 `--aiauto-probe-all` 遍历**一起
> #   不执行，该轮所有被冻版本得不到复评。probe-all 本就不依赖 $V，单版探针另用 `[ -n "$V" ]` 守。
> BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"; V="${TARGET_VERSION:-}"
> # ★ 通知渠道复探与版本解冻同属「配置恢复了就自动重开」，放在同一处：冷启动第一个 tick
> #   把通知关掉后若无人复探，此后所有 #4 只剩终端可见（#4 是冻结时刻唯一对外信号）。
> python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --notify-reprobe 2>/dev/null || true
> # ★ 先扫全部被冻版本并**逐个解冻**：被冻版会被本步候选剔除，只探 $V 则 Phase 2 冻在
> #   PRE_RELEASE 上的三类（deploy-unreachable / unconverged / config-missing）永远探不到。
> #   ⛔ 只调 probe-all 不消费它的 `unfreezable[]` 等于没探 —— 它只打印、不写盘。
> for _v in $(python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --aiauto-probe-all --json 2>/dev/null \
>             | python3 -c "import json,sys;print(' '.join((json.load(sys.stdin).get('unfreezable') or [])))" 2>/dev/null); do
>   $BE --version "$_v" del needs_human needs_human_reason needs_human_kind aiauto_frozen_at freeze_reason \
>     dev_fail_streak dev_fail_phase auto_retest_streak test_loop_missing_streak \
>     probe_fail_streak push_probe_fail_streak cicd_unreachable_streak cicd_cli_fail_streak \
>     prerelease_deploy_block_streak prerelease_test_hold_streak
>   case "$($BE get aiauto_blocked_reason)" in *"@$_v") $BE del aiauto_blocked_reason;; esac
>   echo "🔓 $_v 具备解冻证据 → 已解冻重回候选"
> done
> [ -n "$V" ] || { echo "ℹ️ 本 tick 尚无 TARGET_VERSION（首 tick / 刚 reset）→ 单版探针跳过，probe-all 已跑完"; }
> PROBE=$([ -n "$V" ] && python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --aiauto-probe "$V" --json 2>/dev/null || echo '{}')
> UNFZ=$(printf '%s' "$PROBE" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('evidence','') if d.get('unfreeze') else '')" 2>/dev/null)
> if [ -n "$UNFZ" ]; then
>   $BE --version "$V" del needs_human needs_human_reason aiauto_frozen_at freeze_reason test_loop_missing_streak
>   # 顶层 aiauto_blocked_reason 只在指向本版时才清（可能是别的版本写的）
>   case "$($BE get aiauto_blocked_reason)" in *"@$V") $BE del aiauto_blocked_reason;; esac
>   echo "🔓 $V $UNFZ → 解冻重回候选，下轮铸新 build 复测"
> fi
> ```

★ **覆盖规则**：
- 用户传 `--target <V>` → `TARGET_VERSION = <V>`（不论自动发现结果；**显式点名即解冻该版本一次**，绕过上面的 `needs_human` 跳过）
- 用户传 `--skip-pre-release` → `PRE_RELEASE_VERSION = null`

★★ **选完立即落盘（本步结束前必做，⛔ 漏写 = 后续所有分片读回恒空）**：这两个变量由本步选出，
而消费它们的是**另外的分片、另一次 Bash 调用**——不落盘就跨不过去。

<!-- flowvar-check: allow TARGET_VERSION PRE_RELEASE_VERSION 本步散文判定（SemVer 倒序找首个 S2 / 首个 S0·S1）的产物，由执行体代入实值 -->
```bash
# ⛔ 代入**实际版本号**，绝不原样执行占位形态、绝不留 `<...>`（留占位符与不落盘等价）。
# ⚠️ `autopilot_tick_flags.py set` 一次只收【单个】 name value（不同于 baseline_edit.py），连写 argparse exit 2
#    → 两个变量一个都落不了盘（理据见 rationale）。
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot TARGET_VERSION "<0.3.4 判定的 TARGET_VERSION，无则空串>"
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command autopilot PRE_RELEASE_VERSION "<0.3.4 判定的 PRE_RELEASE_VERSION，无则空串>"
# ★ 两个版本号必须**成对**持久化到 baseline 顶层（tick 命名空间每 tick 整段重写、跨不了 tick）；
#   `autopilot.{target,pre_release}_version` 是二者声明真源，本两行是唯一供给点。
#   ⛔ 任一行漏写 = 断点续跑取空 → 该版全部 jq 打空、门恒判失败（理据见 rationale）。
python3 {{AIDP_HOME}}/scripts/baseline_edit.py set autopilot.target_version "<0.3.4 判定的 TARGET_VERSION，无则空串>"
python3 {{AIDP_HOME}}/scripts/baseline_edit.py set autopilot.pre_release_version "<0.3.4 判定的 PRE_RELEASE_VERSION，无则空串>"
# 落盘后立即自检：读回应与判定值一致，不一致说明代入失败或落盘失败 —— ⛔ 空值即中止本 tick，别带病往下跑
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell | grep -E "^(TARGET_VERSION|PRE_RELEASE_VERSION)="
_TV=$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell | sed -n "s/^TARGET_VERSION=//p" | tr -d \"\'\")
# ⛔ 只判非空**不够**：占位串「<0.3.4 判定的…>」原样写入时它也非空，自检照样放行 —— 此后所有
#   `--version "<0.3.4 判定的…>"` 的 baseline 路径与 `docs/*/<占位>/` 的 glob 全部落空但不报错，
#   run_state 还会写进一个幽灵版本节点。故必须**校形状**（本自检要覆盖的恰是"代入失败"那一档）。
_PRV=$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell | sed -n "s/^PRE_RELEASE_VERSION=//p" | tr -d \"\')
case "$_TV" in
  # ⛔ **空 ≠ 落盘失败**：「本版等准发布、产品还没提新 PRD」是 7×24 最常见的稳态
  #   （0.3.4 决策矩阵里的合法行 `| 有 | null | 仅跑 Phase 2 |`）。这里裸 exit 1 会把它
  #   打成每 10 分钟重撞一次的静默空转，且终端打的是与真因完全相反的话。
  #   判别：还有 PRE_RELEASE_VERSION ⇒ 合法稳态，放行去跑 Phase 2；两者皆空才是真的没活干。
  "")  if [ -n "$_PRV" ]; then
         # ⛔ 这一支**必须继续往下跑、不能 exit**：本 flow 里 `exit 0` 的既定语义是「让位本 tick」
         #   （见 phase-0-3/0-9/1 各处），在这里退出就等于把决策矩阵 `| 有 | null | 仅跑 Phase 2 |`
         #   这一行重新变成结构上不可达 —— 而 Phase 1 的模式表本就写明「SHOULD_RUN=0 但
         #   PRE_RELEASE_VERSION 非 null → 仍进执行主流程」，它需要这个 tick 活着走到那里。
         echo "📭 无待开发版本，仅有准发布版本 $_PRV → 跳过 Phase 3，本 tick 继续跑 Phase 2"
       else
         echo "📭 无待开发、也无准发布版本 → 本 tick 无事可做，正常让位"
         exit 0
       fi ;;
  V[0-9]*.[0-9]*.[0-9]*) : ;;
  *)             echo "❌ TARGET_VERSION=「$_TV」不是版本号形态（占位未代入？），中止本 tick"; exit 1 ;;
esac
```

- 漏写的代价（`run_state` 不落盘 / 准发布双门恒判未收敛）见 `rationale.md`「0.3.4 选版落盘」。
- ⛔ **`TARGET_VERSION` 没有动态回落，空就是空**：`current-version` 是 `PRE_RELEASE_VERSION` 的定义
  （`phase_beta_done_at` 非空且 `internal_released_at` 为空），拿它兜 TARGET 会让下方矩阵
  「有 PRE_RELEASE / TARGET=null → 仅跑 Phase 2」那一档结构上不可达，实际落到
  「TARGET = PRE_RELEASE（`auto_fixable_pending` 非真）」= 数据冲突熔断那一档。
  **本步不落盘，下游就是空** —— 上面那道自检正是为此而设。
