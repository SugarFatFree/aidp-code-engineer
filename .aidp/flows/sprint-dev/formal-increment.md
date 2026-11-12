# /sprint-dev — 分支 B，Phase 0B.00 / 0B.0 / 0B.1

> 本片覆盖：分支 B，Phase 0B.00 / 0B.0 / 0B.1。入口与阶段映射见 `{{AIDP_HOME}}/commands/sprint-dev.md`；仅在该阶段适用时 Read，原参数与 `EXECUTION_CONTEXT` 原样继承。

## 分支 B：formal 累进新建 Sprint（仅 formal 父编排）

### Phase 0B.00：★ 约定 9 前置门（⛔ 最先跑，先于版本落点门与任何取号动作）

> 存在**未关闭 Sprint** 时**立即停下**要求先 `/sprint-close`，⛔ 不得继续。
> **不能等到 Phase 0B.2 的 `/sprint-start` 才拦**——那时 Sprint 号已被 `check_sprint_numbering.py next` 消耗、
> 六类 `NN_*.md` 增量已落盘；close 后重跑会拿到**又一个**新号，
> 上一轮产物成为无 Sprint 归属的孤儿。而独立分步执行时这些副作用根本不会发生。
> 判据与话术同 `/sprint-full` Phase 0B.0 前自检（那条已落地，本条照它办）。

```bash
python3 {{AIDP_HOME}}/scripts/check_open_sprints.py --version {version} --scope started --json
OPEN_RC=$?        # 0=无已启动未关闭轮次→继续；1=有→立即停下、先 /sprint-close；2=状态读错→停止并修复输入
```

> **判据单一信源 = `check_open_sprints.py`**（开工门检查跨用户的已启动记录与显式当前状态，扣除同时具备同行 ✅ 与 `sprints/sprint-NNN.md` 归档文件的关闭记录；**尚未开工的计划不阻断启动**）。
> ⛔ 不自行裁量、不记告警后继续 —— 本门漏判的方向是**放行**，而放行的代价是上面那段写的孤儿产物。

### Phase 0B.0：★ 版本落点决策门（单一信源 —— 累进前置，最先跑，先于任何持久副作用）

> **要解决的问题**：一个版本**已发布**（已归档、已打 tag、已建版本分支、已推送）之后、用户**尚未主动开始新版本规划**时，又提出新需求 / bug 修复。此刻执行体**绝不能自行裁量版本号**（如"向后兼容 → 就 patch"）**更不能静默创建新版本目录骨架、也不能静默往已发布版本累进**——版本号对外是 **SemVer 兼容性承诺 + 发布节奏**（产品/运维决策，非技术判断），re-release 还会**移动已推送的 tag**（有实际风险）。必须让用户**先选落点**。
>
> ⚠️ **本门是结构化决策门、不受「⛔ 统一决策纪律」的"禁自发反问"约束**——它满足该纪律「必须设门的正向判据」全部三条（会建持久目录 / 会产生对外承诺〔版本号·tag·分支〕/ 不可逆或回退成本高〔已推送 tag·分支〕，见本命令「⛔ 统一决策纪律」段正向判据）。**绝不能以"不许自发问"为由省掉本门**（下游越权正是这条纪律被误读为"一律别问"所致）。

**① 检测「当前版本已发布 且 未开始新版本规划」**（命令端 Bash，`{V}` = `AGENTS.md`「当前状态.当前版本」）：
```bash
V={version}                 # 形如 V0.2.0
VNUM=${V#V}                 # 去 V 前缀 → 0.2.0
VCS_MODE="${VCS_MODE:-$(python3 {{AIDP_HOME}}/scripts/vcs.py mode)}"
if [ "$VCS_MODE" = "git" ]; then
# 已发布信号（任一命中即已发布）：① 该版本存在 release tag（三风格全覆盖，与 version.md「tag 风格识别约定」同口径）
# ⛔ 必须区分「判定失败」与「判定为未发布」：两者都产出空值时，浅克隆 / 未 fetch --tags /
#    CI 无 tag 检出 / git user.name 与 memory 目录名不一致 / progress.md 格式不符 —— 任一情形
#    都会静默判"未发布"并累进，即把"版本未发布"当默认假设、不实际判定。
TAG_OK=1; git rev-parse --git-dir >/dev/null 2>&1 || TAG_OK=0
git fetch --tags --quiet 2>/dev/null || true          # 拿不到远端 tag 不致命，但要试一次
# ★ tag 识别**不自己拼 glob**，一律问 `release_scope.py` —— 它是三种风格（`V*` / `release-V*` / `v*`，
#   权威清单见 `flows/version/release-1.md`「tag 风格识别约定」）的单一信源。
#   ⛔ 别在这里自己拼 glob：与脚本各写一遍同一判据，任一处漏一种风格，
#   这道门就会把**已发布**版本判成未发布并往里累进（G-BUGFIX-1 禁止的事）。
TAGS=$(python3 {{AIDP_HOME}}/scripts/release_scope.py --version "$V" --json 2>/dev/null \
       | python3 -c 'import json,sys;d=json.load(sys.stdin);print("\n".join(t for t in (d.get("released_tags") or []) if __import__("re").sub(r"^(release-)?[Vv]","",t).split("-")[0]==sys.argv[1]))' "$VNUM" 2>/dev/null) || TAG_OK=0
RELEASED=$(printf '%s\n' "$TAGS" | head -1)
# ③ 第三信号（不依赖 tag 与文件名约定）：baseline 的 internal_released_at + 随 tag 冻结的部署基线
[ -z "$RELEASED" ] && [ -n "$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" get internal_released_at --default "" 2>/dev/null)" ] && RELEASED="internal_released_at"
[ -z "$RELEASED" ] && [ -d "docs/deployment/$V/配置文件/全量" ] && RELEASED="deployment-baseline"
# ② progress.md「版本历史」/ 版本更新日志 标本版「✅ 已发布」
# ⛔ 版本号须转义 `.` 并要求版本边界（`V0.2.1` 不得命中 `V0.2.10 ✅ 已发布`）
V_ESC=${V//./\\.}; V_PAT="${V_ESC}([^0-9.]|$)"
[ -z "$RELEASED" ] && grep -qsE "${V_PAT}.*✅ ?已发布|已发布.*${V_PAT}" "memory/$V/$(python3 {{AIDP_HOME}}/scripts/vcs.py user)/progress.md" 版本更新日志.md 2>/dev/null && RELEASED="$V(状态已发布)"
# ⛔ fail-closed：tag 判定本身失败且其余信号均未命中 → 落点未知，按「已发布」进下方决策门，⛔ 不并入"未发布"
[ "$TAG_OK" = 0 ] && [ -z "$RELEASED" ] && RELEASED="unknown(tag-query-failed)"
elif [ "$VCS_MODE" = "none" ]; then
  # 无 Git 仅使用版本级本地记录；缺少明确证据不能由“无 tag”推导未发布。
  RELEASED=""
  [ -n "$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$V" get internal_released_at --default "" 2>/dev/null)" ] && RELEASED="internal_released_at"
  [ -z "$RELEASED" ] && [ -d "docs/deployment/$V/配置文件/全量" ] && RELEASED="deployment-baseline"
  UNRELEASED=0
  V_ESC=${V//./\\.}; V_PAT="${V_ESC}([^0-9.]|$)"
  for progress in "memory/$V"/*/progress.md 版本更新日志.md; do
    [ -f "$progress" ] || continue
    if grep -qsE "${V_PAT}.*✅ ?已发布|已发布.*${V_PAT}" "$progress"; then
      [ -z "$RELEASED" ] && RELEASED="$V(状态已发布)"
    fi
    # 只有版本号同一行明确写未发布，且不存在任何已发布信号，才允许累进。
    grep -qsE "${V_PAT}.*未发布|未发布.*${V_PAT}" "$progress" && UNRELEASED=1
  done
  if [ "$UNRELEASED" = 1 ] && [ -n "$RELEASED" ]; then
    RELEASED="unknown(local-release-state-conflict)"
  elif [ "$UNRELEASED" = 0 ] && [ -z "$RELEASED" ]; then
    RELEASED="unknown(local-release-state-unverified)"
  fi
else
  RELEASED="unknown(vcs-mode-unrecognized)"
fi
echo "RELEASED=${RELEASED}"
```
> ⛔ **`TAG_OK=0`（Git tag 查询失败）或 `vcs_mode=none` 且无明确本地发布证据 → fail-closed**：将 `RELEASED` 置为 `unknown(...)`，交互式要求用户先核实并选定落点；`--unattended` 记录 `release-state-unknown` 待裁决并结束本次累进，不得自行创建 patch 版本或把无 Git 当未发布。即使本地证据命中，也仅表示需要版本落点决策，不表示已完成正式 Git 发布。
>
> 说明：Git 模式下若用户已开始新版本规划，「当前版本」已推进到未发布的新号，tag 查询成功且无已发布信号时 `RELEASED` 为空、本门自动不触发；无 Git 模式须有版本号对应的明确「未发布」本地记录且无已发布信号，才能让 `RELEASED` 为空；记录缺失或互相矛盾时需先核实发布状态。

**② ★ 决策前置铁律（不可逆序）**：`RELEASED` 非空时，**在用户选定落点并确认之前，绝不创建任何 `{新版本}` 持久副作用**——不 `mkdir docs/requirements/{新版本}/` / `docs/design/detail/{新版本}/` / `memory/{新版本}/`、不写项目记忆文件「当前状态」、不建 tag/分支。**决策 → 用户确认 → 才建目录**（事前一问，成本远低于事后 `git mv` 一批目录 + 回改状态文件）。

**③ `RELEASED` 非空 → 决策门（`RELEASED` 为空 → 跳过本门，直接进 Phase 0B.1 正常累进）**：
- **`RELEASED=unknown(...)`** → 发布状态不可核实，停止本次累进并保留原版本号；交互式请用户核实本地发布记录并明确落点，`--unattended` 记待裁决 `release-state-unknown` 并交上层失败处置，不使用下方已确认发布版本的默认 patch 路径。
- **交互式**（非 `--unattended`）→ `AskUserQuestion` **三选一**（命令端给推荐项 + 逐项讲清代价，**版本号语义 patch/minor 由用户定、执行体不自裁**）：
  - **① 落回已发布版本 `{V}`（re-release）**：增量并入 `{V}`、完成后走 `/version {V}` 情况 C 重新发布。⚠️ **风险必须明示**：re-release 会**强制移动已推送的 tag `v{VNUM}` + 强制重建版本分支 + 强制推送**；**若该 tag 已被他人拉取 / 已被 CI / 制品库消费，强制移动有实际风险**。适合：极小热修且确认 tag 未被下游消费。
  - **② 新开 patch 版本 `{x.y.z+1}`（推荐默认，风险最低）**：向后兼容的修补 / 行为补齐 → 新建版本目录 → 累进开发；**不动已发布的 tag**。
  - **③ 新开 minor 版本 `{x.y+1.0}`**：有功能语义的增量 → 新建版本目录 → 累进开发；不动已发布 tag。
  > patch vs minor 命令端可给**推荐 + 理由**（如"纯 bug 修复建议 patch、含新行为建议 minor"），但**最终由用户确认**——版本号是对外兼容性承诺，不由执行体技术判据决定。选 ①→转 `/version {V}` 情况 C；选 ②/③→以用户确认的新号继续 Phase 0B.1。
- **`--unattended`**（罕见命中——autopilot 版本发现只挑未发布的 S0/S1 版本作开发目标、通常不会把已发布版本当累进目标）→ **不弹窗**，按**保守默认 = 新开 patch 版本 `{x.y.z+1}`**（**不动已发布的 tag、风险最低**，绝不默认 re-release 去移动已推送 tag）继续，并在报告 + 终端 + baseline **`versions.{V}.builds[current_build].decidable_skips[]`**（无 `current_build` 时才回落版本级 `versions.{V}.decidable_skips[]`）（`post-release-accrue-defaulted-patch`）**留痕**：「已发布版本 {V} 收到新累进请求 → 无人值守按保守默认新开 patch {x.y.z+1}；如需落回 {V} re-release 或改 minor 请人工处置」。**绝不静默当常规累进、绝不自动 re-release 动 tag**。

### Phase 0B.1：累进 Sprint 序号

```bash
# ★ 取号一律走脚本，【绝不】自己 glob 当前版本目录（见下方 Why）
NEXT=$(python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py next)   # 形如 004
```

> ⛔ **Sprint 编号是【项目全局流水号】，跨版本连续自增、不随版本重置**（`06_版本与用户目录约定.md` §3.3）。
> ⛔ 扫描路径**不得带 `{version}` 限定**（带了就等于每个新版本从 `sprint-001` 重新开始）。
> 成因见 `{{AIDP_HOME}}/flows/sprint-dev/rationale.md`「Sprint 编号为何必须跨版本扫」。于是同一项目里存在多个
> `sprint-001`，bugfix 记录、`docs/testing/{version}/sprint-{NNN}/`、Sprint 归档
> 全部产生歧义。脚本的 `next` 子命令**跨全部版本**扫描取 MAX+1，回检见 `check` 子命令。

取得原流程真实 Sprint 号后，在任何 start/子命令派发前绑定或派生 formal 上下文。版本/批次父身份不绑定单个 Sprint；单 Sprint 的 full 无号上下文才 bind。绑定/派生不是开工批准，后续契约与 start 门照旧。`NEXT` 必须是上方原取号结果，工具调用不共享 shell 时显式重绑该结果，禁止再取一次号。

```bash
CONTEXT_ENTRY=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["entry"])' "$EXECUTION_CONTEXT") || exit $?
case "$CONTEXT_ENTRY" in
  sprint-autopilot|sprint-batch|version) CONTEXT_OPERATION=fork ;;
  *) CONTEXT_OPERATION=bind-sprint ;;
esac
SPRINT_POLICY_ARGS=()
if [ "$CONTEXT_OPERATION" = fork ]; then
  SPRINT_ALLOW=$(python3 - "$EXECUTION_CONTEXT" <<'ACTIONS'
import json, sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from execution_policy import BASE_ACTIONS, COMMAND_ACTIONS
parent = json.load(open(sys.argv[1]))
development = BASE_ACTIONS | set(COMMAND_ACTIONS["sprint-full"])
print(*["--allow-action=" + a for a in sorted(development & set(parent["allowed_actions"]))])
ACTIONS
  ) || exit $?
  [ -n "$SPRINT_ALLOW" ] || { printf '%s\n' 'NOT_REQUESTED: 无Sprint开发动作'; exit 0; }
  read -ra SPRINT_POLICY_ARGS <<< "$SPRINT_ALLOW"
fi
SPRINT_CONTEXT_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py "$CONTEXT_OPERATION" --root . \
  --execution-context "$EXECUTION_CONTEXT" --sprint "${NEXT:?原流程已分配的Sprint号缺失}" "${SPRINT_POLICY_ARGS[@]}" --json) || exit $?
EXECUTION_CONTEXT=$(printf '%s' "$SPRINT_CONTEXT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
```

**派生后重新绑定当前任务（fork / bind-sprint 均执行）**：上方返回的子路径才是后续代码任务。读取工作分支策略，再由 `entry_gate.py bind --if-writable` 检查 implement 授权与有效写集（优先 `authorization_scope`，否则 `write_set`）；所有有效任务均选择当前身份；仅可写任务放行编辑，其余明确返回 `skipped=true, ok=false`，宿主提供 `AIDP_SESSION_ID` 时显式透传，无会话时使用任务标记。不得用父上下文或任意近期任务替代。

<!-- flowvar-check: allow AIDP_SESSION_ID -->
```bash
# 独立工具调用时 EXECUTION_CONTEXT 显式取上方返回值，不重新取号或重建身份。
python3 {{AIDP_HOME}}/scripts/aidp_config.py branch-policy --root . >&2 || exit $?
BIND_ARGS=()
[ -z "${AIDP_SESSION_ID:-}" ] || BIND_ARGS+=(--session-id "$AIDP_SESSION_ID")
python3 {{AIDP_HOME}}/scripts/entry_gate.py bind --if-writable --root . \
  --execution-context "$EXECUTION_CONTEXT" "${BIND_ARGS[@]}" --json || exit $?
```

若没有 implement，仅执行获授权动作，不自行追加授权；若 implement 已授权但继承的写集为空，继续只读核实本轮需求/契约工作单，以真实目标通过 `entry_context.py revise --execution-context "$EXECUTION_CONTEXT" --write-set "{实际路径}" --json` 更新同一子上下文，再重跑本绑定围栏。**任何实现前必须已绑定且目标实际落在有效写集内**；具体文件由 `entry_gate.py check --root . --target "{实际目标文件}" --json` 校验（有会话沿用同一 `AIDP_SESSION_ID`）。不能为放行猜一个 `code/` 宽目录、硬绑空写集或把未绑定当通过。

完成回传包含真实 Sprint 号与当前子 `execution_context`；外层 bugfix/full 后续 test/close 消费该子路径。autopilot 的版本节点仍保留父路径，不用此子路径覆盖。重试已有子任务直接继承它，不能重新从版本父启动累进取号。


全部前置门通过且上下文已绑定/派生后，Read `{{AIDP_HOME}}/flows/sprint-dev/formal-docs.md`，进入 Phase 0B.1.1。
