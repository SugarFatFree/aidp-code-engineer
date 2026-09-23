<!-- 二次切分 · phase-0 片6a/9：覆盖 0.2 baseline读取+版本解析【子步骤 1 – 4】（心跳/去重门/冻结契约/熔断门/报告门/自愈交接判定/deployment/里程碑通知配置）-->
# /sprint-aiauto-test · 执行分片 [6/9]：0.2 baseline 读取 + 版本解析（子步骤 1–4）

> ⚠️ **权威性**：以本文件为准逐项执行，不得略过任一子步骤 / 硬门。**维护**：随脚手架下发，改动后同步 bundle 副本；理据见 `rationale.md`。

### 0.2 baseline 读取 + 版本解析（本片覆盖子步骤 1 – 4）

> ⚠️ **本片是 0.2 的前半**：只到上面这段 bash 主体（子步骤 1 版本解析 → 2 去重/冻结 → 2.5/2.5.1 build 与自愈交接判定 → 3 deployment → 4 里程碑通知配置/报告落点）。
> **0.2 的两段执行铁律**（自愈式交接执行铁律、#0a / 通知配置 / 报告落点归属分工）在 **`phase-0-6b.md`**，`NEED_HANDOFF=1` 时**必须接着 Read 它**再动作。

<!-- dup-check: ignore 分片自包含 -->
```bash
BASELINE_FILE="memory/.sprint-autopilot-baseline.json"

# 1. baseline 文件不存在 → /sprint-autopilot 还没跑过任何版本，命令退出
[ ! -f "$BASELINE_FILE" ] && echo "⚠️ baseline 文件不存在，请先跑 /sprint-autopilot" && exit 0

# ★ 心跳已在 0.0.0（phase-0-1.md）写过，⛔ 不要挪回这里（理据见 rationale.md『0.2 取版与去重门注释』）
# 乐观清空阻塞原因；任何 early-exit 分支在 exit 前必须回写它（见下方各门）
# ⛔ **只清本链路能判归属的那一版**（本行在版本解析前跑；根因见 rationale「清除归属」）
_ABR=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get aiauto_blocked_reason --default "")
case "$_ABR" in
  ""|*chrome-unavailable*|*no-testable-version*) python3 {{AIDP_HOME}}/scripts/baseline_edit.py del aiauto_blocked_reason || true ;;
  # ★ `no-testable-version` 必须在白名单里（谁写的谁必须能清；根因见 rationale 同名段）。
  *) echo "⏭️ 保留既有阻塞原因（$_ABR，非本链路可判归属）" ;;
esac

# 2. 版本号解析（自动从 baseline 读 — 不要求用户传）
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"   # 读回 0.0.0 落盘的 --target/--select/--once 等
if [ -n "$TARGET_FLAG_VALUE" ]; then
  # --target 显式锁定（边界情况兜底，通常不走这条路径）
  TARGET_VERSION="$TARGET_FLAG_VALUE"
  # ⛔ 这一支同样必须落盘（理据见 rationale.md『0.2 取版与去重门注释』）
  python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test \
    TARGET_VERSION "$TARGET_VERSION" >/dev/null 2>&1 || true
else
  # ★ 默认：取「当前开发版本」，判据单一信源 = baseline_edit.py current-version（⛔ 不内联 jq）
  TARGET_VERSION=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version)
  # ⛔ 选版后立即落盘，否则下游读回的是 autopilot 的开发版本（见 rationale「被测版本传不出去」）
  python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test \
    TARGET_VERSION "$TARGET_VERSION" >/dev/null 2>&1 || true
  if [ -z "$TARGET_VERSION" ]; then
    echo "⚠️ baseline 中无「当前开发版本」可测（所有版本要么已准发布要么未跑 sprint-autopilot Phase 3）"
    echo "👉 请先跑 /sprint-autopilot 完成 Phase 3（部署），或加 --target <V> 手动指定"
    # ⛔ early-exit 前必刷阻塞原因（漏写 = 开发链路误判健康，见 rationale.md）
    python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto_blocked_reason "no-testable-version" >/dev/null 2>&1 || true
    exit 0
  fi
fi
echo "🎯 测试目标版本：$TARGET_VERSION（来源：${TARGET_FLAG_VALUE:+--target flag 锁定}${TARGET_FLAG_VALUE:-baseline 自动读取「当前开发版本」}）"

# ★ 已测去重门（防 /loop 对同一部署重复跑全套用例 + 重刷 #R/#F 里程碑通知）
#   ⚠️ 三重豁免（缺任一都会误退）：--target / --once / current_build 是新 build。见 rationale。
if [ -z "$TARGET_FLAG_VALUE" ] && [ "${HAS_ONCE_FLAG:-0}" != "1" ]; then
  LAST_DEP=$(jq -r ".versions.\"$TARGET_VERSION\".last_deployed_at // \"\"" $BASELINE_FILE)
  LAST_TST=$(jq -r ".versions.\"$TARGET_VERSION\".aiauto_tested_at // \"\"" $BASELINE_FILE)
  STREAK=$(jq -r ".versions.\"$TARGET_VERSION\".aiauto_test_unconverged_streak // 0" $BASELINE_FILE)
  # 本 build 已测过 = current_build 在 builds[] 的 status 为 tested；无 current_build（standalone）→ 视为已测、按时间口径判。
  CUR_BUILD=$(jq -r ".versions.\"$TARGET_VERSION\".current_build // empty" $BASELINE_FILE 2>/dev/null)
  BUILD_TESTED=1
  if [ -n "$CUR_BUILD" ]; then
    BS=$(jq -r ".versions.\"$TARGET_VERSION\".builds[]? | select(.build==\"$CUR_BUILD\") | .status" $BASELINE_FILE 2>/dev/null | head -1)
    # ⚠️ 二元判定勿改回单值，成因见 rationale
    case "$BS" in tested|closed) ;; *) BUILD_TESTED=0 ;; esac
  fi
  # 判据：LAST_DEP ≤ LAST_TST（本部署已测）且 streak=0（已收敛）且 BUILD_TESTED=1。
  # ★ 时间一律 epoch 比较（⛔ 不用字符串比较，根因见 rationale.md）。
  to_ts() { date -d "$1" +%s 2>/dev/null || echo 0; }
  # ★ 第五个条件不可省（根因见 rationale.md「去重门为何会锁死收口门」）
  RPT_FIN=$(jq -r ".versions.\"$TARGET_VERSION\".builds[]? | select(.build==\"$CUR_BUILD\") | .ai_report_finalized" $BASELINE_FILE 2>/dev/null)
  [ -z "$CUR_BUILD" ] && RPT_FIN=true
  if [ -n "$LAST_TST" ] && [ -n "$LAST_DEP" ] && [ "$STREAK" = "0" ] && [ "$BUILD_TESTED" = "1" ] \
     && [ "$RPT_FIN" = "true" ] \
     && [ "$(to_ts "$LAST_DEP")" -le "$(to_ts "$LAST_TST")" ]; then
    echo "⏭️ 无新部署 / 无新 build：本部署（$LAST_DEP）已于 $LAST_TST 测过且已收敛 → 跳过本 tick（等 last_deployed_at 刷新或 autopilot 铸新 build 才重测）"
    exit 0
  fi
  # ★ 第六个条件：未收敛 + 待自动修复 + 无新部署 → 跳过（见 rationale「未收敛时的重测节流」）
  AFP=$(jq -r ".versions.\"$TARGET_VERSION\".auto_fixable_pending // false" $BASELINE_FILE 2>/dev/null)
  # ★ 纯待确认轮同样要节流（AFP 刻意不置真；只判 AFP 会让这类轮次每 5 分钟全量重跑到冻结）。
  PC=$(jq -r "(.versions.\"$TARGET_VERSION\".pending_clarifications // []) | length" $BASELINE_FILE 2>/dev/null || echo 0)
  if { [ "$AFP" = "true" ] || [ "${PC:-0}" -gt 0 ]; } && [ -n "$LAST_TST" ] && [ -n "$LAST_DEP" ] \
     && [ "$(to_ts "$LAST_DEP")" -le "$(to_ts "$LAST_TST")" ]; then
    echo "⏭️ 本轮未收敛（待自动修复=$AFP / 待人工确认=${PC:-0} 项），但自 $LAST_TST 起无新部署 → 跳过本 tick"
    exit 0
  fi
  # ★ 第七个条件：开发链路自动修复进行中（派单时写 auto_fix_in_progress_since）且其后尚无新部署 → 跳过，
  #   不对旧部署重测（重测会再置 AFP、空耗 retest_auto_cap）。
  AFIP=$(jq -r ".versions.\"$TARGET_VERSION\".auto_fix_in_progress_since // \"\"" $BASELINE_FILE 2>/dev/null)
  if [ -n "$AFIP" ] && { [ -z "$LAST_DEP" ] || [ "$(to_ts "$LAST_DEP")" -le "$(to_ts "$AFIP")" ]; }; then
    echo "⏭️ 自动修复进行中（自 $AFIP 起），尚无修复后的新部署 → 跳过本 tick"
    exit 0
  fi
fi

# ★ 部署归属门（--target / --once 同样适用）：复测轮先铸新 build 后部署，部署未落到本 build 前
#   测的是旧代码。判据：本 build 未过就绪探针（probe_passed 非真）且 last_deployed_at 为空或早于本 build 的 started_at → 跳过。
CUR_BUILD=$(jq -r ".versions.\"$TARGET_VERSION\".current_build // empty" $BASELINE_FILE 2>/dev/null)
if [ -n "$CUR_BUILD" ]; then
  _PP=$(jq -r ".versions.\"$TARGET_VERSION\".builds[]? | select(.build==\"$CUR_BUILD\") | .probe_passed // empty" $BASELINE_FILE 2>/dev/null | head -1)
  _BST=$(jq -r ".versions.\"$TARGET_VERSION\".builds[]? | select(.build==\"$CUR_BUILD\") | .started_at // empty" $BASELINE_FILE 2>/dev/null | head -1)
  _LDP=$(jq -r ".versions.\"$TARGET_VERSION\".last_deployed_at // empty" $BASELINE_FILE 2>/dev/null)
  _ts() { date -d "$1" +%s 2>/dev/null || echo 0; }
  if [ "$_PP" != "true" ] && [ -n "$_BST" ] && { [ -z "$_LDP" ] || [ "$(_ts "$_LDP")" -lt "$(_ts "$_BST")" ]; }; then
    echo "⏭️ $CUR_BUILD 尚未部署（last_deployed_at=${_LDP:-空} 早于 build 开始 $_BST，且未过就绪探针）→ 跳过本 tick，等本 build 部署完成"
    exit 0
  fi
fi

# ══ ★ 冻结字段写入契约：四件一次写齐（needs_human / aiauto_frozen_at / freeze_reason + 顶层
#   aiauto_blocked_reason="frozen:<枚举>@V"），枚举见 rationale.md「冻结分类」══
#
# ★ 熔断冻结门（对齐 autopilot needs_human 的统一放行开关）：仅默认自动选版路径（无 --target）
#   生效；--target 手动指定 = 人工介入，视为解冻重试一次。
if [ -z "$TARGET_FLAG_VALUE" ]; then
  BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version $TARGET_VERSION"
  NEEDS_HUMAN=$($BE get needs_human --default false)
  # ⚠️ 冻结时刻取统一字段 aiauto_frozen_at（兼容历史 probe_frozen_at）；缺它即永不解冻。
  FROZEN_AT=$($BE get aiauto_frozen_at --default "$($BE get probe_frozen_at --default '')")
  FREEZE_REASON=$($BE get freeze_reason --default "unknown")
  LAST_DEP=$($BE get last_deployed_at --default "")
  if [ "$NEEDS_HUMAN" = "true" ]; then
    # ⛔ 解冻证据判定**唯一实现 = `autopilot_unfreeze.py --aiauto-probe`**（只判不写）；
    #    ⛔ 严禁在此内联 case 复述枚举（根因见 rationale.md「解冻判据为何不得内联」）。
    #    返回形状：{"unfreeze":bool, "reason":<冻结原因>, "evidence":<恢复证据>|"note":<原因>}
    UNFREEZE=$(python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py --aiauto-probe "$TARGET_VERSION" --json \
                 2>/dev/null | jq -r 'if .unfreeze then (.evidence // "已具备恢复证据") else empty end')
    if [ -n "$UNFREEZE" ]; then
      # ★ 解冻必须把**所有**熔断计数一并清零（漏一个即刚解冻又达阈重冻）
      $BE del needs_human needs_human_kind aiauto_frozen_at probe_frozen_at freeze_reason \
        probe_fail_streak aiauto_test_unconverged_streak report_gate_fail_streak \
        shot_gate_fail_streak qr_gate_fail_streak \
        final_gate_fail_streak env_fail_streak case_gate_fail_streak handoff_fail_streak aiauto_gate_fail_streak \
        auto_retest_streak retest_cap_frozen_at retest_frozen_head
      python3 {{AIDP_HOME}}/scripts/baseline_edit.py del aiauto_blocked_reason || true
      echo "🔓 $TARGET_VERSION $UNFREEZE → 自动解冻重测"
    else
      # 仍冻结：/loop 无人值守跳过本版、不重测、不刷 #4（等新部署/配置更新，或人工 --target/--reset-baseline 解冻）
      # ★ 必须回写 aiauto_blocked_reason（根因见 rationale.md「心跳与阻塞原因」）
      python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto_blocked_reason "frozen:$FREEZE_REASON@$TARGET_VERSION"
      echo "⏸️ $TARGET_VERSION 已熔断待人工（needs_human=true，原因 $FREEZE_REASON，冻结于 $FROZEN_AT）→ 跳过本 tick"
      exit 0
    fi
  fi
fi

# 2.5 读 build 号 + 判定「测试报告生成门」（AI测试报告仅在 /sprint-autopilot 流水线驱动时生成）
# current_build 只由 autopilot 3.1.5 铸造 → 存在 == autopilot 流水线驱动；缺失 == 直接调用（standalone/独立 loop/他命令）
BUILD=$(jq -r ".versions.\"$TARGET_VERSION\".current_build // empty" $BASELINE_FILE 2>/dev/null)
if [ -n "$BUILD" ]; then
  REPORT_ENABLED=1
  echo "🔢 本轮测试归属 build：$BUILD（autopilot 驱动 → 截图 + AI测试报告 HTML 均归此 build）"
  # ★ 待确认项归档：新 build（复测轮）或 --once 时，把非本 build 提出的 pending_clarifications 移入
  #   pending_clarifications_archive，避免旧问题永久压住节流门与收敛判定。
  python3 - "$TARGET_VERSION" "$BUILD" "${HAS_ONCE_FLAG:-0}" <<'PC' || true
import sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from baseline_edit import LockedBaseline, now_iso
V, B, once = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
with LockedBaseline("memory/.sprint-autopilot-baseline.json", write=True) as lb:
    vn = (lb.data.get("versions") or {}).get(V)
    if isinstance(vn, dict) and vn.get("pending_clarifications"):
        keep = [i for i in vn["pending_clarifications"] if not once and i.get("raised_build") == B]
        moved = [dict(i, archived_at=now_iso()) for i in vn["pending_clarifications"] if i not in keep]
        if moved:
            vn.setdefault("pending_clarifications_archive", []).extend(moved)
            vn["pending_clarifications"] = keep
            print(f"🗂️ 已归档 {len(moved)} 条待确认项（新 build / --once）")
PC
  # ★ 认领 0.0.7 的驱动事实（不认领则收尾门 3i 恒空转，见 rationale.md）
  _BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version $TARGET_VERSION"
  _DRV=$($_BE get driver_actual_pending 2>/dev/null)
  [ -n "$_DRV" ] && $_BE --build "$BUILD" set driver_actual "$_DRV" >/dev/null 2>&1 \
    && $_BE del driver_actual_pending >/dev/null 2>&1 && echo "   driver_actual=$_DRV 已归属本 build"
else
  REPORT_ENABLED=0
  BUILD="${TARGET_VERSION}_build$(date '+%Y%m%d-%H%M')"   # 仅用于截图归档命名，不产报告
  echo "ℹ️ baseline 无 current_build（aiauto-test 直接调用 / 独立运行，非 autopilot 驱动）"
  echo "   → 只跑测试 + 终端输出 + 写 baseline + 失败回写「问题汇总清单」，跳过 HTML 报告（截图照常落盘）"
fi

# 2.5bis ★ 选集护栏（--select）：子集 ≠ 测过了。三处强制回落 all（详见命令主体 6bis）。
SELECT_MODE="${SELECT_FLAG_VALUE:-all}"
SELECT_FORCED_REASON=""
# ① 无人值守 / 编排链内调用（产官方 build 报告 + 驱动收敛门）
[ "${LOOP_UNATTENDED:-0}" = "1" ] && SELECT_FORCED_REASON="无人值守"
[ "$REPORT_ENABLED" = "1" ] && SELECT_FORCED_REASON="${SELECT_FORCED_REASON:-autopilot/编排链驱动}"
# ② 新 build 回归轮（bugfix 后复测）= build 递增，SKILL 硬边界要求全量；判据 = builds[] > 1
PRIOR_BUILDS=$(jq -r ".versions.\"$TARGET_VERSION\".builds // [] | length" $BASELINE_FILE 2>/dev/null || echo 0)
[ "${PRIOR_BUILDS:-0}" -gt 1 ] && SELECT_FORCED_REASON="${SELECT_FORCED_REASON:-新 build 回归轮}"
if [ -n "$SELECT_FORCED_REASON" ] && [ "$SELECT_MODE" != "all" ]; then
  echo "⚠️ --select $SELECT_MODE 已忽略、强制 all（原因：$SELECT_FORCED_REASON）"
  echo "   选集只服务交互式手动快验；本路径须全量"
  SELECT_MODE=all
fi
# ★ 必须落盘（消费点在别的分片；回读恒空会走子集分支并把空值传给 --select，见 rationale.md）
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test SELECT_MODE "$SELECT_MODE"
[ "$SELECT_MODE" != "all" ] && echo "🔎 【子集轮】select=$SELECT_MODE —— 准则仅对子集成立，不写 aiauto_tested_at"


# 2.5.1 ★ 自愈式交接（autopilot 驱动 current_build 存在却无 AI执行报告 → 不死胡同拦截，交接回 autopilot test-only 补齐）
#   骨架归属与触发判据见 rationale「自愈式交接」
NEED_HANDOFF=0
if [ "$REPORT_ENABLED" = "1" ]; then
  RPT_AI="docs/reports/${TARGET_VERSION}/AI执行报告"
  if [ ! -f "$RPT_AI/data/${BUILD}.js" ]; then
    echo "🔁 自愈式交接触发：autopilot 驱动（current_build=$BUILD）但执行数据缺失"
    echo "   缺：$RPT_AI/data/${BUILD}.js（autopilot Phase 3.1.5 铸造 build 时即应写计划态并注册两页）"
    # ★ 透传无人值守：恒带 --unattended；有唤醒源（/loop 或 OS 调度）再加 --no-loop，无唤醒源（如 --once --unattended）不加，
    #   否则被调侧误判「有下一 tick」而让位、却没有下一 tick 来接。
    HANDOFF_NO_LOOP=""
    if [ "${LOOP_UNATTENDED:-0}" = "1" ]; then
      [ "${HAS_WAKE_SOURCE:-0}" = "1" ] && HANDOFF_NO_LOOP=" --unattended --no-loop" || HANDOFF_NO_LOOP=" --unattended"
    fi
    echo "   → 交接：立即 invoke  /sprint-autopilot --skip-dev [--unattended] --target $TARGET_VERSION${HANDOFF_NO_LOOP}  （test-only 入口；[--unattended] 按 LOOP_UNATTENDED 条件透传）补齐 AI执行报告，再结束本轮 aiauto-test。"
    NEED_HANDOFF=1
  else
    echo "✅ AI执行报告骨架就绪（data/${BUILD}.js 已在；index.html 结果 + plan.html 计划同源渲染）→ 直接往下测"
    # ★ 清零必须落在成功分支（见 rationale「交接计数器为何只增不减」）
    python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" del handoff_fail_streak 2>/dev/null || true
  fi
fi

# 3. 读 deployment 配置（PRD 头部 autopilot_decisions.deployment）
PRD_FILE=$(ls docs/requirements/$TARGET_VERSION/产品提供/*.md 2>/dev/null | head -1)
BEP="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"   # ⚠️ 定义在 if 之外：两条分支都要用
if [ -z "$PRD_FILE" ]; then
  # ⛔ 不裸 exit 1；⚠️ 计数用**专属** prd_missing_streak（⛔ 不复用 env_fail_streak）。
  #   两条的根因见 rationale.md「PRD 缺失门」。
  # 记账→判阈→冻结四件套→发 #4 一次做完（⛔ 专属 reason `prd-missing`，不复用 config-missing）
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
    --phase 0.3-prd --reason prd-missing \
    --streak-key prd_missing_streak --threshold "${ENV_FAIL_FREEZE_THRESHOLD:-3}" \
    --why "找不到 $TARGET_VERSION 的 PRD（docs/requirements/$TARGET_VERSION/产品提供/），无法解析部署模式"
  [ "$?" = "3" ] && echo "⛔ 达阈 → 已冻结本版（补齐 PRD 目录后按 mtime 自动解冻）" || echo "❌ PRD 缺失，已发 #4、让位本 tick"
  exit 0
fi
$BEP --version "$TARGET_VERSION" del prd_missing_streak 2>/dev/null || true   # PRD 找到 → 清零
# 用 awk 抽 YAML frontmatter
DEPLOY_MODE=$(awk '/^---$/{f=!f;next} f && /^[[:space:]]*mode:/{print $2;exit}' "$PRD_FILE")

# 4. ★ 读里程碑通知配置（人维护配置 `memory/aidp-config.yaml` 的 `notify` 段，与 sprint-autopilot 共享）
# ⚠️ 值域统一 0/1；判定与 notify.py 同源（总开关开启且至少一个渠道凭据就绪，由 tick_flags 供给）
NOTIFY_ENABLED="${NOTIFY_ENABLED:-0}"
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test NOTIFY_ENABLED "$NOTIFY_ENABLED" >/dev/null 2>&1 || true  # 必须落盘
# ★ 报告只落本地 `docs/reports/{V}/`，通知里的报告链接一律用仓库内相对路径（或仓库文件链接）。
if [ "$NOTIFY_ENABLED" != "1" ]; then
  # ★ 未启用 / 未配置任何渠道 → 本轮里程碑通知静默跳过（通知是可选增强，缺失不阻塞测试主流程）。
  #   ⛔ 交互式与无人值守一致：不弹窗收集渠道；需要通知时由人自行编辑 memory/aidp-config.yaml 的 notify 段。
  NOTIFY_ENABLED=0
  python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test NOTIFY_ENABLED 0 >/dev/null 2>&1 || true
  echo "ℹ️ notify 未启用或未配置渠道 → 本轮里程碑通知静默跳过（不弹窗、不阻塞测试）"
fi
# ★ 发送统一走：python3 {{AIDP_HOME}}/scripts/notify.py --auto --title … --section … [--link-text … --link-url <仓库相对路径>]
#   退出码 0 成功 / 1 全部渠道失败（WARN 不阻塞）/ 2 参数错误（修参数重发）/ 3 未配置任何渠道（静默跳过本节点）。
```
