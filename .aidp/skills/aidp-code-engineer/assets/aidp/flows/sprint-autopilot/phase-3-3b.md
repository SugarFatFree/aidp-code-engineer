# sprint-autopilot · Phase 3 详情分片 [3b/13]（3.1.0 版本规划已存在检测 · 跳过规划门 + P0-1 硬判据）

> 本文件承接 `phase-3-3.md`（Phase 3.1 版本规划 + 启动通知），单独承载 **3.1.0**——它是「要不要跑 `/version`」与「incremental 是否成立」的唯一判定处，判据多、且每条都直接决定是否少跑一整段流程，故独立成片。
> - **本片覆盖**：3.1.0 规划产物六类齐全判定（`PLANNING_DONE`）+ P0-1 incremental 硬判据②③ + P0-0 跳过规划的两个合法来源 + 裁定结果回写 baseline
> - **同 Phase 其它分片**：phase-3-1.md … phase-3-9.md（含 phase-3-3b.md）
>
> ⚠️ **权威性**：进入 Phase 3 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一判据。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-3-3b.md`。理据见同目录 `rationale.md`。

---

#### 3.1.0 版本规划已存在检测（跳过规划门）

★ **核心规则**：进入 Phase 3 后，**先判断 `TARGET_VERSION` 的版本规划产物是否已完整存在**；已存在则**跳过 `/version` 规划步骤**，直接进入 3.2 的 `/sprint-batch` 开发测试。避免重复跑 `/version` 把已生成的需求/设计/计划文档再生成一遍（既浪费工时，又可能覆盖已人工微调过的设计 / 已拆分的 Sprint 计划）。

**为什么需要这道门**：
- **S1 版本**（已规划进行中 — 典型场景：上次 autopilot 跑到 `/sprint-batch` 一半被中断、或用户先手工跑过 `/version`）被 Phase 0.3.4 选为 TARGET_VERSION 时，若不加本门判定就会**重复跑 `/version` 重新规划** → 重复劳动 + 覆盖已人工微调产物的风险
- **S0 版本**（仅 PRD 未规划）则**必须**先跑 `/version` 才有 Sprint 可执行
- 本门用「版本规划终态产物是否齐全」一刀切判定，与 Phase 0.3.3 状态机的 S0/S1 判定**同源**（以 `01_研发执行计划.md` 存在为核心信号）；**★ 但"齐全"必须六类齐（研发需求 + 详细设计 + 研发执行计划 + 研发自测用例 + 研发自测方案 + 测试环境与账号），与 `/version`「三步落盘自检」同口径**（判定条件见下方 :57 的第 5/6 类）——研发自测是 `/sprint-selftest`（Step 2.4.3.5）在执行计划**之后**才产出的，若漏检就会让"计划在、自测缺"的残缺态被误判齐全而永久跳过 `/version`（下游"甚至没生成研发自测目录"的根因）

**检测逻辑**（命令端 Bash）：

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
# ⛔ 上一行刚 eval 出正确版本号，**别再用占位符字面量覆盖它**（原写法即如此，且语法合法、零报错）：
#   覆盖后下面三个目录路径全 miss → PLANNING_DONE 恒 0；末尾还会把 autopilot_entry_mode /
#   planning_done 写进一个**伪版本节点**，真实版本恒空。
: "${TARGET_VERSION:?Phase 0.3.4 尚未落盘 target_version，拒绝继续}"
PLAN_DIR="docs/plans/$TARGET_VERSION"
REQ_DIR="docs/requirements/$TARGET_VERSION/研发需求"
DESIGN_DIR="docs/design/detail/$TARGET_VERSION"

# 主判定标记 = 01_研发执行计划.md（/version 规划链路最后生成的终态产物）
# 兼容补充模式下的多文件/子目录形态：计划目录内任一「研发执行计划」主体即视为存在
PLAN_OK=0
if [ -f "$PLAN_DIR/01_研发执行计划.md" ] || ls "$PLAN_DIR/"*研发执行计划*.md >/dev/null 2>&1; then
  PLAN_OK=1
fi

# 完整性校验：研发需求 + 详细设计目录各至少一份产物（防"计划在但上游缺"的半成品）
REQ_OK=0
{ [ -f "$REQ_DIR/01_研发需求.md" ] || [ -f "$REQ_DIR/00_索引.md" ] || ls "$REQ_DIR/"*.md >/dev/null 2>&1; } && REQ_OK=1
DESIGN_OK=0
ls "$DESIGN_DIR/"*.md >/dev/null 2>&1 && DESIGN_OK=1

# ★★ 研发自测存在性校验（本次下游反馈根因修复 — 必须与 /version「三步落盘自检」同口径）：
#   研发自测用例/方案是 /sprint-selftest（Step 2.4.3.5）在【研发执行计划之后】才产出的。
#   若只查 PLAN/REQ/DESIGN 三类，则「执行计划已在、但 Step 5 中断/被主动收尾跳过、研发自测目录根本没生成」
#   的残缺态会被误判为「规划齐全」→ 跳过 /version → 绕过 version 自身的研发自测落盘自检兜底 →
#   研发自测【永久补不回来】（重跑几次 autopilot 都跳过）。故本门必须一并校验研发自测。
#   glob 与 version.md Step 2.4「三步落盘自检」研发自测用例判定对齐（容 dedup 后序号漂移 + 历史扁平形态）。
TEST_DIR="docs/testing/$TARGET_VERSION/研发自测"
TESTCASE_OK=0
if ls "$TEST_DIR/"*自测用例*.md >/dev/null 2>&1 || \
   ls "$TEST_DIR/"0[0-9]_研发自测.md >/dev/null 2>&1 || \
   [ -f "docs/testing/$TARGET_VERSION/研发自测.md" ] || \
   [ -f "docs/testing/$TARGET_VERSION/研发自测用例.md" ]; then
  TESTCASE_OK=1
fi

# ★★ 第 5/6 类：研发自测**方案** + **测试环境与账号**（`/version` 三步落盘自检确认的是 6 类、不是 4 类）。
#   少这两类的残缺态会被判成"规划齐全"→ 永久跳过 /version → 绕过它那道 6 类硬门；而
#   `01_测试环境与账号.md` 正是 /sprint-aiauto-test 的输入，缺了浏览器实测无从开始。
SCHEME_OK=0; ENV_OK=0
{ ls "$TEST_DIR/"*研发自测方案*.md >/dev/null 2>&1 || [ -f "docs/testing/$TARGET_VERSION/研发自测方案.md" ]; } && SCHEME_OK=1
ls "$TEST_DIR/"*测试环境与账号*.md >/dev/null 2>&1 && ENV_OK=1

if [ "$PLAN_OK" = "1" ] && [ "$REQ_OK" = "1" ] && [ "$DESIGN_OK" = "1" ] && [ "$TESTCASE_OK" = "1" ] \
   && [ "$SCHEME_OK" = "1" ] && [ "$ENV_OK" = "1" ]; then
  PLANNING_DONE=1
  echo "✅ $TARGET_VERSION 版本规划产物齐全（研发需求 + 详细设计 + 研发执行计划 + 研发自测用例 + 自测方案 + 测试环境与账号 六类），跳过 /version 规划，直接进入开发测试"
else
  PLANNING_DONE=0
  # ★ 六类全打：判定条件已是六类，诊断行却只报四类 —— 缺的恰好是研发自测方案 / 测试环境与账号时，
  #   打印出来的四个值全是 1 却判 PLANNING_DONE=0，诊断信息与结论直接矛盾、无从排障。
  echo "📋 $TARGET_VERSION 版本规划缺失或不完整（PLAN=$PLAN_OK REQ=$REQ_OK DESIGN=$DESIGN_OK TESTCASE=$TESTCASE_OK SCHEME=$SCHEME_OK ENV=$ENV_OK），将跑 /version 规划补齐"
  # ★ 常见触发：TESTCASE=0 而其余=1 —— 执行计划已在、研发自测缺失。走 /version 幂等续跑：
  #   version 对已存在的研发需求/详细设计/执行计划走 supplement/幂等（不覆盖已人工微调产物），
  #   仅经 Step 2.4.3 补齐研发自测；且 version「三步落盘自检」会硬门兜底，绝不再放行「自测缺失」。
fi

# ★★ P0-1 incremental 硬判据②裁定（缺一强制降级 full）：Phase 3.0 step 1 置的【暂定 incremental】必须 PLANNING_DONE=1 才最终成立；
#    PLANNING_DONE=0（如全新版本号，六类产物全无）→ 强制降级 ENTRY_MODE=full，照跑 /version 全量规划 + Phase 3.2 全量 Sprint。
#    堵下游根因：V0.10.3 全新版本被"语义判 incremental"免除规划、六类产物全无却收尾 9/9 全绿。
if [ "$ENTRY_MODE" = "incremental" ] && [ "$PLANNING_DONE" = "0" ]; then
  ENTRY_MODE="full"
  echo "⬇️ incremental 硬判据②未满足（$TARGET_VERSION 规划产物不齐、PLANNING_DONE=0）→ 强制降级 ENTRY_MODE=full，照跑 /version 全量规划（不许用增量名义免除规划）"
fi
# ★★ P0-1 incremental 硬判据③：本版**不得还有未关闭 Sprint**。
#    ⛔ 缺这条时：版本处于 S1（已规划、Sprint 没跑完）+ 用户一句自然语言增量意图 → 语义判 incremental
#    → 硬判据② 满足（规划齐）→ **整个全量开发段被跳过**，而部署/报告/通知/收尾门全绿、正常收尾，
#    剩余 N 个 Sprint 被静默丢下。顶层契约的违约本就是结果级的——"返回时仍有未关闭 Sprint 却正常收尾"。
#    判据与 0.3.3 的 S1/S2 状态机同源，实现单一信源 = `autopilot-ceremony-gate.py::_open_sprints`（收尾门 0bis 复用同一函数）。
if [ "$ENTRY_MODE" = "incremental" ]; then
  OPEN_N=$(python3 - "$TARGET_VERSION" <<'PY'
import importlib.util, sys
s = importlib.util.spec_from_file_location("g", ".aidp/scripts/autopilot-ceremony-gate.py")
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(len(m._open_sprints(".", sys.argv[1])))
PY
)
  if [ "${OPEN_N:-0}" != "0" ]; then
    ENTRY_MODE="full"
    echo "⬇️ incremental 硬判据③未满足（$TARGET_VERSION 尚有 $OPEN_N 个未关闭 Sprint）→ 强制降级 ENTRY_MODE=full，照跑全量开发；确只改增量请显式 --skip-dev"
  fi
fi
# ★ P0-0 跳过规划的唯一两个合法来源：① PLANNING_DONE=1（已规划，天然无需重跑）② 用户显式 --no-planning（须台账留痕、收尾门认此显式声明放行）。
#   除此之外 full/incremental 一律跑 /version；--force-replan 无视 PLANNING_DONE 强制重规划（与本条正交）。
# ⛔ `--shell` 对**全部**登记变量无条件 print 赋值行，`ENTRY_MODE` / `PLANNING_DONE` 都在表内 ——
#   直接 eval 会把上面刚算出的**强制降级**与判定结果整体冲掉（P0-1 的核心保护随之失效：
#   S1 版本 + 一句增量意图 → 打印"⬇️ 强制降级 full"但不生效 → Phase 3.2 走 incremental
#   一 tick 跑完 → **剩余 N 个 Sprint 被静默丢下**，而部署/报告/通知/收尾门全绿）。
#   故先存后恢复，只取本次真正需要的 NO_PLANNING。
_KEEP_ENTRY_MODE="$ENTRY_MODE"; _KEEP_PLANNING_DONE="$PLANNING_DONE"
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"   # 读回 NO_PLANNING 等本 tick 参数
ENTRY_MODE="$_KEEP_ENTRY_MODE"; PLANNING_DONE="$_KEEP_PLANNING_DONE"
if [ "${NO_PLANNING:-0}" = "1" ] && [ "$PLANNING_DONE" = "0" ]; then
  echo "⏭️ 用户显式 --no-planning：$TARGET_VERSION 跳过 /version 规划（须在交付台账留痕；收尾门 autopilot-ceremony-gate.py --no-planning 1 认此显式声明、放行规划产物缺失）"
fi
# ★ P0-2：把【最终裁定后】的 ENTRY_MODE + NO_PLANNING 写入 baseline，供收尾门 autopilot-ceremony-gate.py 的
#   两条 final 路径（autopilot 静态-only 自跑 / aiauto-test Phase 3.7 浏览器测试）自动读取、校验规划产物存在性（无需各调用点都传 flag）。
# ⛔ 走加锁写入口，不用裸 `jq … > tmp && mv`（invariants「baseline 单一写入口不变式」）：
#    Phase 3.1 结束这一刻与测试 loop 的 5m 写窗高度重叠，裸写会整份覆盖掉对方刚落的字段。
# ★ planning_done 必须一并落盘：它是 PLANNING_DONE 的 baseline 真源，漏写则读回恒取
#   FALLBACK_DEFAULT="0" → 收尾门（phase-3-9）据此每轮都索要一条 #1 通知，而发送侧在
#   PLANNING_DONE=1 时正确地不发 → 通知核验必 FAIL → 3 tick 后冻结，且冻结原因
#   （handoff-exhausted「结构性不可自愈」）与真因（一个变量没落盘）毫无关系。
python3 .aidp/scripts/baseline_edit.py --version "$TARGET_VERSION" \
  set autopilot_entry_mode "$ENTRY_MODE" autopilot_no_planning "${NO_PLANNING:-0}" \
      planning_done "${PLANNING_DONE:-0}" || true
# ⛔ 还必须把降级后的值写回 **tick 命名空间**：`phase-3-2` 已经用 `autopilot_tick_flags.py set` 把
#    降级【前】的 ENTRY_MODE 写进去了，而 `--shell` 是**先读 tick 命名空间、取不到才回落 baseline**。
#    只写 baseline = 本 tick 后续每个分片 `eval "$(… --shell)"` 读回的仍是旧值 `incremental`：
#    这里刚判定"规划产物不齐 / 还有未关闭 Sprint、必须走全量"，下游却照 incremental 跳过全量规划
#    与全量 Sprint —— 降级判定形同虚设，且两处各自"正确"、合起来矛盾。
python3 .aidp/scripts/autopilot_tick_flags.py set --command autopilot ENTRY_MODE "$ENTRY_MODE"
python3 .aidp/scripts/autopilot_tick_flags.py set --command autopilot PLANNING_DONE "${PLANNING_DONE:-0}"
```

判定结果：

| `PLANNING_DONE` | 含义 | 3.1 行为 |
|----------------|------|---------|
| `1` | 规划产物齐全（典型 = S1 进行中 / 用户预先手工规划）| **跳过 step 2 的 `/version`**，直接走 step 3 解析 Sprint 数 → 进 3.2 开发测试 |
| `0` | 无规划 / 半成品（典型 = S0 仅 PRD / 上次规划中断在 design 之前 / **执行计划已在但研发自测缺失**）| 正常跑 step 2 的 `/version`（`/version` 自身对半成品幂等续跑、补齐缺失产物——含经 Step 2.4.3 补齐研发自测）|

★ **强制重新规划的逃生阀**：用户加 `--force-replan` flag → 无视 `PLANNING_DONE`，强制跑 `/version` 重新规划（用于 PRD 大改、需推翻已有设计重新规划的场景）。

---

> ⏭️ **接续**：裁定完成后回 `phase-3-3.md` 的 Phase 3.1 step 1（#1 规划开始通知）继续。
>
> ⛳ **本片无独立 `run_state` 出口**：3.1.0 是 Phase 3.1 **内部**的一个判定子步，Phase 3.1 的出口由 `phase-3-3.md` 末尾统一写。硬要本片也写，等于造出第二个写 `run_state` 的地方，与「出口唯一」相悖。
> <!-- phase-exit: n/a 3.1.0 是 Phase 3.1 内部判定子步，出口由 phase-3-3.md 写 -->
