<!-- 二次切分 · phase-0 片6b/9：0.2 自愈交接 / 通知与报告归属 -->
# sprint-aiauto-test · 执行分片 [6b/9]（0.2 交接与归属）

> 先执行 `phase-0-6.md`。本片逐项执行，不得省略硬门；随脚手架同步。

### 当前版本测试真实委派（autopilot 唯一调用点）

autopilot Phase 3.4 的报告骨架与真实部署就绪后，在让位测试链/同步委派前执行本围栏。`VERSION_MANIFEST` 是按 `phase-2-unit.md` 从真实当前版本验收基线、正式用例索引与部署 commit 测试配置冻结的既有机器 JSON；不得临时发现全仓测试补全集。完整清单无法形成则返回具体阻塞，不能跳过本门而委派。父为真实 autopilot 根，同版本、原预算；test-only根不含 implement/commit/push/deploy。

<!-- version-test-delegation -->
```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?真实autopilot父上下文}"
TARGET_VERSION="${TARGET_VERSION:?当前版本}"
BUILD="${BUILD:?当前真实build}"
VERSION_MANIFEST="${VERSION_MANIFEST:?当前版本完整验收冻结清单路径}"
TEST_CHILD_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py fork-test-build --root . \
  --execution-context "$EXECUTION_CONTEXT" --version "$TARGET_VERSION" --build-id "$BUILD" \
  --manifest "$VERSION_MANIFEST" --json) || exit $?
TEST_EXECUTION_CONTEXT=$(printf '%s' "$TEST_CHILD_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto.execution_context "$TEST_EXECUTION_CONTEXT" || exit $?
printf '测试委派上下文：%s\n' "$TEST_EXECUTION_CONTEXT"
```

已有同 build/同 manifest 子路径直接复用；不同清单不能覆盖原证据。同步调用 `/sprint-aiauto-test --execution-context "$TEST_EXECUTION_CONTEXT" --once --unattended`；异步调度只消费该已校验路径（`AIDP_EXECUTION_CONTEXT`），不从 activeContext/current_build 重新授予权限。全部后续两路 worker 继承 child，不能传开发根。

### 0.2（续）自愈式交接

`NEED_HANDOFF=1` 表示 **current_build 已定稿，或 AI执行报告骨架缺失**。必须在 Phase 1/2 开测、认领驱动及归档待确认项之前处理。`--once` / `--target` 只豁免已测去重，不能解除报告不可变锁；无 current_build 的 standalone 不交接、不铸官方 build、不产 HTML 报告。

**① 核固定旧build与原授权根，再登记一次交接**（下方返回参数仅模板，R-1完成后必须执行②的换绑围栏）：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
BUILD=$($BE get current_build --default "")
NEED_HANDOFF=0
if [ -n "$BUILD" ]; then
  FINALIZED=$($BE --build "$BUILD" get ai_report_finalized --default false)
  if [ "$FINALIZED" = true ] || [ ! -f "docs/reports/$TARGET_VERSION/AI执行报告/data/${BUILD}.js" ]; then
    NEED_HANDOFF=1
  fi
fi
[ "$NEED_HANDOFF" = 1 ] || { echo "NEED_HANDOFF=0：真源已变化，回 phase-0-6.md 重新取归属"; exit 0; }
: "${PREFLIGHT_RUN_ID:?须沿用本次 parse 的 run id}"
PREVIOUS_HANDOFF=$($BE get aiauto_handoff_run_id --default "")
[ "$PREVIOUS_HANDOFF" != "$PREFLIGHT_RUN_ID" ] || { echo "⛔ 同 run 交接未完成，失败返回，不递归调用 autopilot"; exit 2; }
EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?沿用原固定build测试子上下文}"
HANDOFF_SOURCE=$(python3 - "$EXECUTION_CONTEXT" "$TARGET_VERSION" "$BUILD" <<'HANDOFF'
import json, sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from entry_context import load_context, _context_path, resolve_autopilot_root
from execution_policy import require_action, validate_test_binding
root = Path.cwd()
ctx = load_context(root, sys.argv[1])
version, build = sys.argv[2:]
if ctx["version"] != version:
    raise SystemExit("UNVERIFIED: 目标版本与上下文不符")
require_action(ctx, "live-tests")
target_only = not ctx.get("test_manifest")
if target_only:
    targets = ctx["task_scope"].get("acceptance", [])
    if not targets or set(ctx["allowed_actions"]) - {"static", "live-tests"}:
        raise SystemExit("UNVERIFIED: 独立目标不明确或不是仅测试上下文")
    selected = resolve_autopilot_root(root, version, existing_only=True)
    parent_path = Path(selected["execution_context"])
else:
    validate_test_binding(root, ctx, version, build)
    parent_path = _context_path(root, ctx["parent_task_id"])
parent = load_context(root, parent_path)
if parent.get("parent_task_id") or parent["entry"] != "sprint-autopilot" or parent["version"] != version:
    raise SystemExit("UNVERIFIED: 无已有可信autopilot根，保留原测试身份")
require_action(parent, "live-tests")
print(json.dumps({"root_context":str(parent_path), "target_only":target_only}))
HANDOFF
) || exit $?
HANDOFF_ROOT_CONTEXT=$(printf '%s' "$HANDOFF_SOURCE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["root_context"])') || exit $?
HANDOFF_TARGET_ONLY=$(printf '%s' "$HANDOFF_SOURCE" | python3 -c 'import json,sys; print(str(json.load(sys.stdin)["target_only"]).lower())') || exit $?
HANDOFF_FLAGS=(--skip-dev --target "$TARGET_VERSION" --preflight-run-id "$PREFLIGHT_RUN_ID" --execution-context "$HANDOFF_ROOT_CONTEXT")
RETURN_FLAGS=(--target "$TARGET_VERSION" --preflight-run-id "$PREFLIGHT_RUN_ID")
if [ "${HAS_ONCE_FLAG:-0}" = 1 ]; then
  HANDOFF_FLAGS+=(--once); RETURN_FLAGS+=(--once)
fi
if [ "${LOOP_UNATTENDED:-0}" = 1 ]; then
  HANDOFF_FLAGS+=(--unattended); RETURN_FLAGS+=(--unattended)
  if [ "${HAS_WAKE_SOURCE:-0}" = 1 ]; then
    HANDOFF_FLAGS+=(--no-loop); RETURN_FLAGS+=(--no-loop)
  fi
fi
PREPARED_DEPLOY_AT=$($BE get last_deployed_at --default '') || exit $?
PREPARED_COMMIT=$($BE --build "$BUILD" get push_commit --default '') || exit $?
HANDOFF_ARGS=""; RETURN_ARGS=""
printf -v HANDOFF_ARGS '%q ' "${HANDOFF_FLAGS[@]}"
printf -v RETURN_ARGS '%q ' "${RETURN_FLAGS[@]}"
$BE set aiauto_handoff_run_id "$PREFLIGHT_RUN_ID" aiauto_handoff_root_context "$HANDOFF_ROOT_CONTEXT" aiauto_handoff_from_context "$EXECUTION_CONTEXT" \
  aiauto_handoff_from_build "$BUILD" aiauto_handoff_target_only "$HANDOFF_TARGET_ONLY" aiauto_handoff_return_args "$RETURN_ARGS" \
  aiauto_handoff_prepared_deploy_at "$PREPARED_DEPLOY_AT" aiauto_handoff_prepared_commit "$PREPARED_COMMIT" || exit $?
$BE del aiauto_handoff_to_build aiauto_handoff_deployment || exit $?
printf '交接命令：/sprint-autopilot %s\n返回参数（待换绑）：%s\n' "$HANDOFF_ARGS" "$RETURN_ARGS"
```

**② 同步交接，仅调用一次**：保存交接命令和返回参数模板。原测试实例交还控制权；编排用原根invoke autopilot的report_handoff受限分支（真实版本委派或经existing_only核验的target_only报告交接；独立目标回调原ctx，不升版本全量），只做R-1和必要报告骨架；R-3就绪后运行下方换绑围栏。不得提前调用没有新ctx的返回模板，也不得把旧ctx直接改build_id。

- **锁与调用边界**：原测试实例按 `reference/agent-tools.md`「tick 占位收尾」用自己 Phase 0 的 token 完成收尾，session 占位释放成功后才 invoke autopilot；不得从锁文件取别人的 token。OS token=`agent_loop` 不执行 finish、不释放 wrapper 的 flock，后续同步子调用须继承原 `AIDP_TICK_COMMAND` / `AIDP_TICK_TOKEN` 环境，现有准入门只允许该 wrapper 的真实子链复用。若开发链已被其它 tick 占用，则交接未完成，走下方失败处置，不能假称已测试。
- **唯一铸号与骨架生产者仍是 autopilot R-1（`sprint-autopilot/phase-3-4.md`步骤1必读`phase-3-4a.md`）**：旧 build 已 finalized 时铸新号，记录 `retest_of`；test-only 无新代码时由该围栏登记 `deploy_reuse_of=last_deployed_at`。测试侧不改 current_build、不手造报告、不用 `--force-amend`。该报告交接不执行R-2部署；R-3只产必要骨架并核可用性；返回后按②核R-1登记的to_build与current_build一致，部署复用登记仍须匹配当前部署。
- **不递归、不重复铸号**：同一 `--preflight-run-id` 只登记一次交接。回调若仍已定稿或缺骨架，`phase-0-6.md` 硬退失败；健康的未定稿新 build 直接续测，不再次调用 R-1。新的外部请求由 parse 生成新 run id，可重试失败交接；旧标记不阻挡新请求。R-1 对已有骨架、未定稿且未收尾的活动 build 按原规则复用。
- **`--once` / 无唤醒源必须同步完成交接与新 build 实测收尾**，不能以“等下次 tick”作为成功返回。交接返回后原测试实例直接结束，不能带旧 BUILD 再测一次。若父 autopilot 已在等待本测试回调，失败应返回该父调用，不能递归 invoke 第二个 autopilot。

**R完成后的唯一回调准备围栏**（marker=`handoff-rebind-callback`）。来源、同run或当前build不符时失败返回，不能改用裸根绕过_pin_build。

<!-- handoff-rebind-callback -->
```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version ${TARGET_VERSION:?}"
: "${PREFLIGHT_RUN_ID:?必须保留原交接run}"
[ "$($BE get aiauto_handoff_run_id --default '')" = "$PREFLIGHT_RUN_ID" ] || exit 2
HANDOFF_ROOT_CONTEXT=$($BE get aiauto_handoff_root_context --default '') || exit $?
HANDOFF_FROM_CONTEXT=$($BE get aiauto_handoff_from_context --default '') || exit $?
HANDOFF_TARGET_ONLY=$($BE get aiauto_handoff_target_only --default false) || exit $?
HANDOFF_FROM_BUILD=$($BE get aiauto_handoff_from_build --default '') || exit $?
HANDOFF_TO_BUILD=$($BE get aiauto_handoff_to_build --default '') || exit $?
: "${HANDOFF_ROOT_CONTEXT:?}"; : "${HANDOFF_FROM_CONTEXT:?}"; : "${HANDOFF_FROM_BUILD:?}"; : "${HANDOFF_TO_BUILD:?}"
[ "$($BE get current_build --default '')" = "$HANDOFF_TO_BUILD" ] || exit 2
[ "$($BE --build "$HANDOFF_TO_BUILD" get ai_report_finalized --default false)" != true ] || exit 2
[ -s "docs/reports/$TARGET_VERSION/AI执行报告/data/${HANDOFF_TO_BUILD}.js" ] || exit 2
python3 - "$HANDOFF_FROM_CONTEXT" "$HANDOFF_ROOT_CONTEXT" "$TARGET_VERSION" "$HANDOFF_FROM_BUILD" "$HANDOFF_TARGET_ONLY" <<'SOURCE'
import sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from entry_context import load_context
old = load_context(Path.cwd(), sys.argv[1])
parent = load_context(Path.cwd(), sys.argv[2])
if sys.argv[5] == "true":
    if old["version"] != sys.argv[3] or not old["task_scope"].get("acceptance") or set(old["allowed_actions"]) - {"static", "live-tests"}:
        raise SystemExit("UNAUTHORIZED: 原目标范围/测试权限变化")
elif (old.get("parent_task_id"), old.get("version"), old.get("build_id")) != (parent["task_id"], sys.argv[3], sys.argv[4]):
    raise SystemExit("UNAUTHORIZED: 原交接上下文/根/版本/build不匹配")
SOURCE
[ "$?" = 0 ] || exit 2
python3 - "$TARGET_VERSION" "$PREFLIGHT_RUN_ID" "$HANDOFF_FROM_BUILD" "$HANDOFF_TO_BUILD" "$HANDOFF_ROOT_CONTEXT" <<'DEPLOY_PROOF'
import json, re, subprocess, sys
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from entry_context import load_context
version, run, before, target, parent_path = sys.argv[1:]
ver = json.loads(Path("memory/.sprint-autopilot-baseline.json").read_text())["versions"][version]
p = ver.get("aiauto_handoff_deployment")
parent = load_context(Path.cwd(), parent_path, migrate=False)
def need(ok):
    if not ok:
        raise SystemExit("UNVERIFIED: callback部署绑定缺失或准备后发生变化")
need(isinstance(p, dict))
need(isinstance(p.get("commit"), str) and re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", p["commit"]))
need((p.get("version"), p.get("run_id"), p.get("root_task_id"), p.get("from_build")) == (version, run, parent["task_id"], before))
need(p.get("deployed_at") == ver.get("last_deployed_at") == ver.get("aiauto_handoff_prepared_deploy_at"))
need(p.get("commit") == ver.get("aiauto_handoff_prepared_commit"))
def row(name):
    found = [x for x in ver.get("builds", []) if x.get("build") == name]
    need(len(found) == 1)
    return found[0]
anchor, old, new = row(p.get("probe_build")), row(before), row(target)
need(anchor.get("probe_passed") is True and anchor.get("push_commit") == anchor.get("probe_commit") == p.get("commit"))
need(anchor.get("probe_at") == p.get("probe_at") == p.get("deployed_at"))
need(old.get("push_commit") == new.get("push_commit") == p.get("commit"))
need(new.get("deploy_reuse_of") == p.get("deployed_at") and new.get("deploy_reuse_proof") == p)
obj = subprocess.run(["git", "cat-file", "-t", p["commit"]], capture_output=True, text=True)
need(obj.returncode == 0 and obj.stdout.strip() == "commit")
DEPLOY_PROOF
[ "$?" = 0 ] || exit 2
if [ "$HANDOFF_TO_BUILD" != "$HANDOFF_FROM_BUILD" ]; then
  RETEST_OF=$($BE --build "$HANDOFF_TO_BUILD" get retest_of --default '') || exit $?
  [ -z "$RETEST_OF" ] || [ "$RETEST_OF" = "$HANDOFF_FROM_BUILD" ] || exit 2
  FROM_FINAL=$($BE --build "$HANDOFF_FROM_BUILD" get ai_report_finalized --default false) || exit $?
  FROM_STATUS=$($BE --build "$HANDOFF_FROM_BUILD" get status --default '') || exit $?
  if [ "$FROM_FINAL" = true ] || [ "$FROM_STATUS" = closed ] || [ "$FROM_STATUS" = tested ]; then
    [ "$RETEST_OF" = "$HANDOFF_FROM_BUILD" ] || exit 2
  fi
fi
if [ "$HANDOFF_TARGET_ONLY" = true ]; then
  HANDOFF_REBOUND_CONTEXT="$HANDOFF_FROM_CONTEXT"
else
  VERSION_MANIFEST="${1:?回调围栏argv[1]传新build冻结清单路径}"
  REBIND_RESULT=$(python3 {{AIDP_HOME}}/scripts/entry_context.py fork-test-build --root . \
    --execution-context "$HANDOFF_ROOT_CONTEXT" --version "$TARGET_VERSION" --build-id "$HANDOFF_TO_BUILD" \
    --manifest "${VERSION_MANIFEST:?按新build真实冻结验收清单，不能改写旧manifest}" --json) || exit $?
  HANDOFF_REBOUND_CONTEXT=$(printf '%s' "$REBIND_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["execution_context"])') || exit $?
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto.execution_context "$HANDOFF_REBOUND_CONTEXT" || exit $?
fi
RETURN_ARGS=$($BE get aiauto_handoff_return_args --default '') || exit $?
[ -n "$RETURN_ARGS" ] || exit 2
CALLBACK_CONTEXT_ARG=""
printf -v CALLBACK_CONTEXT_ARG '%q' "$HANDOFF_REBOUND_CONTEXT"
RETURN_ARGS="$RETURN_ARGS --execution-context $CALLBACK_CONTEXT_ARG"
printf '返回命令：/sprint-aiauto-test %s\n' "$RETURN_ARGS"
```

只invoke该围栏输出的新返回命令；版本委派沿同根预算派生新build child；target_only返回原target ctx、不fork full、不写aiauto.execution_context。旧ctx保持不变。同run回调仍沿phase-0-6既有重入门；非本次R-1登记的baseline漂移继续拒绝。

**③ 失败才记账**：正常定稿后的新一轮不是故障，交接前不得调用失败处理器（无唤醒源会首次即冻、导致交接根本未执行）。autopilot 返回失败、被占用、未回调测试或本 run 回调仍不可测时，外层编排立即执行一次：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "$TARGET_VERSION" \
  --phase 0.6-handoff --reason handoff-exhausted --streak-key handoff_fail_streak \
  --threshold "${HANDOFF_FAIL_THRESHOLD:-3}" \
  --why "test-only 交接未取得可测的新 build/执行骨架，未完成本次实测"
```

退出码 3 已冻结，2 是处置失败；均不得继续实测或报告成功。未达阈亦结束本次失败交接；有唤醒源时后续 tick 用新 run id 重试。成功回调在 `phase-0-6.md` 可测分支清零 `handoff_fail_streak`。R-4 的真实 testSummary、两份报告定稿与 #3 通知仍由测试链路在 #F 后完成。

### 通知配置与报告归属

- **autopilot 委派路径**（current_build 存在）：继承 `memory/aidp-config.yaml` 的 notify 配置，不发 #0a；测试链路早期里程碑为 #D。
- **standalone 路径**（无 current_build，不能仅凭 `--once` 判定）：Phase 0.2 子步骤 4 自读 notify；未启用或渠道未配置则静默跳过，不弹窗收集。
- 报告路径恒为本地 `docs/reports/{V}/`，通知链接使用仓库相对路径。
