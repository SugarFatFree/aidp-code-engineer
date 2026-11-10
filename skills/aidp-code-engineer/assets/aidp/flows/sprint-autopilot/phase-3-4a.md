# sprint-autopilot · R-1 铸号与部署绑定（phase-3-4 子片）

本片是 `phase-3-4.md` 步骤1的唯一执行围栏；主片必须先Read本片，完成后回步骤2/3。普通铸号语义保留。report-handoff在同一LockedBaseline事务内先验证准备时部署、原根/from/run、完整Git SHA与可信probe/复用链，再铸号并写push_commit/to证明；任何失败均不改变current_build/build_seq。不得使用HEAD/ctx.since，也不执行R-2。

```bash
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
   : "${BASELINE_FILE:=memory/.sprint-autopilot-baseline.json}"
   BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"  # baseline唯一写入口
   BV="$TARGET_VERSION"
   RPT_AI="docs/reports/$BV/AI执行报告"
   # 仅执行数据存在、未finalize且未closed/tested的活动build可复用；其余由本R-1铸新号。
   CUR=$(jq -r ".versions.\"$BV\".current_build // empty" "$BASELINE_FILE" 2>/dev/null)
   CUR_SEQ="${CUR##*_build}"
   CUR_STATUS=$(jq -r ".versions.\"$BV\".builds[]? | select(.build==\"$CUR\") | .status // \"\"" "$BASELINE_FILE" 2>/dev/null | head -1)
   CUR_FINAL=$(jq -r ".versions.\"$BV\".builds[]? | select(.build==\"$CUR\") | .ai_report_finalized // false" "$BASELINE_FILE" 2>/dev/null | head -1)
   # 复用与ENTRY_MODE无关；定稿报告不能覆盖。
   REUSABLE=0
   if [ -n "$CUR" ] && [ -f "$RPT_AI/data/${CUR}.js" ] \
      && [ "$CUR_FINAL" != "true" ] && [ "$CUR_STATUS" != "closed" ] && [ "$CUR_STATUS" != "tested" ]; then
     REUSABLE=1
   fi
   eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command autopilot --shell)"   # 取回 ENTRY_MODE 等本 tick 变量
   HANDOFF_ACTIVE=0
   if [ "${ENTRY_MODE:-}" = test-only ] && [ -n "${PREFLIGHT_RUN_ID:-}" ] \
      && [ "$($BE --version "$BV" get aiauto_handoff_run_id --default '')" = "$PREFLIGHT_RUN_ID" ]; then
     HANDOFF_ROOT=$($BE --version "$BV" get aiauto_handoff_root_context --default '') || exit $?
     HANDOFF_FROM=$($BE --version "$BV" get aiauto_handoff_from_build --default '') || exit $?
     HANDOFF_TO=$($BE --version "$BV" get aiauto_handoff_to_build --default '') || exit $?
     EXECUTION_CONTEXT="${EXECUTION_CONTEXT:?交接须传原授权根}"
     [ "$EXECUTION_CONTEXT" = "${HANDOFF_ROOT:?}" ] || exit 2
     [ -n "$HANDOFF_FROM" ] || exit 2
     if [ -n "$HANDOFF_TO" ]; then
       [ "$CUR" = "$HANDOFF_TO" ] && [ "$REUSABLE" = 1 ] || exit 2
     else
       [ "$CUR" = "$HANDOFF_FROM" ] || exit 2
     fi
     python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . --execution-context "$EXECUTION_CONTEXT" --action live-tests || exit $?
     python3 {{AIDP_HOME}}/scripts/execution_policy.py require-action --root . --execution-context "$EXECUTION_CONTEXT" --action full-regression || exit $?
     HANDOFF_ACTIVE=1
   fi
   if [ "$HANDOFF_ACTIVE" = 1 ]; then
     HANDOFF_MINT_RESULT=$(python3 - "$BV" "$EXECUTION_CONTEXT" "$PREFLIGHT_RUN_ID" <<'DEPLOY_BIND'
import copy, json, re, subprocess, sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from baseline_edit import LockedBaseline, now_iso
from entry_context import load_context
from execution_policy import require_action
root = Path.cwd()
version, parent_path, run_id = sys.argv[1:]
parent = load_context(root, parent_path, migrate=False)
require_action(parent, "live-tests")
require_action(parent, "full-regression")
def need(condition, reason):
    if not condition:
        raise SystemExit("UNVERIFIED: " + reason)
with LockedBaseline("memory/.sprint-autopilot-baseline.json", write=True) as locked:
    ver = locked.data.get("versions", {}).get(version, {})
    need(ver.get("aiauto_handoff_run_id") == run_id, "handoff run变化")
    need(ver.get("aiauto_handoff_root_context") == str(Path(parent_path).resolve()), "handoff根变化")
    before = ver.get("aiauto_handoff_from_build")
    old = load_context(root, ver.get("aiauto_handoff_from_context", ""), migrate=False)
    need((old.get("parent_task_id"), old["version"], old.get("build_id")) == (parent["task_id"], version, before), "fixed来源不匹配")
    rows = ver.get("builds", [])
    need(isinstance(rows, list), "builds格式错误")
    def row(build):
        found = [x for x in rows if isinstance(x, dict) and x.get("build") == build]
        need(len(found) == 1, "部署来源build缺失或重复")
        return found[0]
    origin = row(before)
    deployed = ver.get("last_deployed_at")
    need(isinstance(deployed, str) and bool(deployed), "没有实际部署时间")
    try:
        stamp = datetime.fromisoformat(deployed.replace("Z", "+00:00"))
    except ValueError:
        raise SystemExit("UNVERIFIED: 部署时间不可解析")
    need(stamp.tzinfo is not None, "部署时间缺时区")
    sha = origin.get("push_commit")
    need(isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", sha), "来源缺完整部署SHA")
    need(ver.get("aiauto_handoff_prepared_deploy_at") == deployed and
         ver.get("aiauto_handoff_prepared_commit") == sha, "准备后部署或来源SHA变化")
    obj = subprocess.run(["git", "-C", str(root), "cat-file", "-t", sha], capture_output=True, text=True)
    need(obj.returncode == 0 and obj.stdout.strip() == "commit", "部署SHA不是本仓可解析commit")
    anchor, seen = origin, set()
    while True:
        key = anchor.get("build")
        need(key not in seen, "部署复用链循环")
        seen.add(key)
        need(anchor.get("push_commit") == sha, "复用链部署SHA不一致")
        if anchor.get("probe_passed") is True:
            need(anchor.get("probe_commit") == sha and anchor.get("probe_at") == deployed,
                 "push不能代替部署探活证明")
            break
        need(anchor.get("deploy_reuse_of") == deployed, "复用记录不属于当前部署")
        proof = anchor.get("deploy_reuse_proof")
        if proof is not None:
            need(isinstance(proof, dict) and proof.get("version") == version and
                 proof.get("commit") == sha and proof.get("deployed_at") == deployed and
                 proof.get("probe_at") == deployed, "既有部署复用证明不一致")
            link = proof.get("probe_build")
        else:
            link = anchor.get("retest_of")
        need(isinstance(link, str) and bool(link), "没有可信部署证明链")
        anchor = row(link)
    proof = {"schema": 1, "version": version, "commit": sha, "deployed_at": deployed,
             "probe_build": anchor["build"], "probe_at": anchor["probe_at"],
             "from_build": before, "root_task_id": parent["task_id"], "run_id": run_id}
    current = ver.get("current_build")
    target = ver.get("aiauto_handoff_to_build")
    current_row = row(current)
    reusable = (current_row.get("ai_report_finalized") is not True and
                current_row.get("status") not in ("closed", "tested") and
                (root / "docs/reports" / version / "AI执行报告/data" / (current + ".js")).is_file())
    if target:
        need(current == target and reusable, "已登记to已变化或不可复用")
        need(ver.get("aiauto_handoff_deployment") == proof, "同run部署绑定变化")
        need(current_row.get("push_commit") == sha and current_row.get("deploy_reuse_of") == deployed and
             current_row.get("deploy_reuse_proof") == proof, "既有to的部署绑定不一致")
        selected = current_row
    else:
        need(current == before, "current不属于本次handoff")
        if reusable:
            selected = current_row
        else:
            last = ver.get("build_seq", 1000)
            need(type(last) is int and last >= 0, "build_seq无效")
            seq = max(1001, last + 1)
            target = version + "_build" + str(seq)
            need(not any(x.get("build") == target for x in rows), "新build编号已存在")
            selected = {"build": target, "started_at": now_iso(), "status": "running", "entry_mode": "test-only"}
            if origin.get("ai_report_finalized") is True or origin.get("status") in ("closed", "tested"):
                selected.update(retest_of=before, retest_round=1 + sum(bool(x.get("retest_of")) for x in rows))
            rows.append(selected)
            ver["build_seq"] = seq
            for name in ("aiauto_test_unconverged_streak", "dev_fail_streak", "dev_fail_phase"):
                ver.pop(name, None)
            if isinstance(ver.get("cicd_run"), dict):
                ver["cicd_run"].pop("cicd_retry_count", None)
        selected.update(push_commit=sha, deploy_reuse_of=deployed, deploy_reuse_proof=copy.deepcopy(proof),
                        deploy_reuse_reason="report handoff：沿可信探活证明复用部署，不重新部署")
        if not selected.get("entry_mode"):
            selected["entry_mode"] = "test-only"
        ver["builds"] = rows
        ver["current_build"] = selected["build"]
        ver["aiauto_handoff_to_build"] = selected["build"]
        ver["aiauto_handoff_deployment"] = copy.deepcopy(proof)
    result = {"build": selected["build"], "build_seq": ver.get("build_seq"), "deployment_commit": sha}
print(json.dumps(result, ensure_ascii=False))
DEPLOY_BIND
) || exit $?
     BUILD=$(printf '%s' "$HANDOFF_MINT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["build"])') || exit $?
     BUILD_SEQ=$(printf '%s' "$HANDOFF_MINT_RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin)["build_seq"])') || exit $?
     printf '%s\n' "$HANDOFF_MINT_RESULT"
   elif [ "$REUSABLE" = "1" ]; then
     BUILD="$CUR"; BUILD_SEQ="$CUR_SEQ"
     # ★ entry_mode 落 build 级、复用时只补不覆盖（理由见 rationale.md「entry_mode 粒度」）；兼回填存量 build。
     [ -n "$ENTRY_MODE" ] && [ -z "$($BE --version "$BV" --build "$BUILD" get entry_mode --default "")" ] \
       && $BE --version "$BV" --build "$BUILD" set entry_mode "$ENTRY_MODE" >/dev/null || true
     echo "♻️ 复用现有 build：$BUILD（执行数据在 + 未 finalize/未收尾 → 不自增，入口=$ENTRY_MODE）"
   else
     # 复测轮：CUR 已 finalize/收尾 → 记 retest_of + round + 上轮通过率
     RETEST_OF=""; RETEST_ROUND=0; RETEST_LABEL=""
     if [ -n "$CUR" ] && { [ "$CUR_FINAL" = "true" ] || [ "$CUR_STATUS" = "closed" ] || [ "$CUR_STATUS" = "tested" ]; }; then
       RETEST_OF="$CUR"
       PREV_RATE=$(jq -r ".versions.\"$BV\".builds[]? | select(.build==\"$CUR\") | .pass_rate // \"?\"" "$BASELINE_FILE" 2>/dev/null | head -1)
       # ⛔ 不按 ai_report_finalized 计（未收敛轮从不 finalize ⇒ 恒"第 1 轮"，见 rationale.md）
       RETEST_ROUND=$(( $(jq -r "[.versions.\"$BV\".builds[]? | select(.retest_of != null)] | length" "$BASELINE_FILE" 2>/dev/null || echo 0) + 1 ))
       RETEST_LABEL="第 ${RETEST_ROUND} 轮复测（上轮 ${CUR} 通过率 ${PREV_RATE}）"
       echo "🔁 上一 build $CUR 已 finalize/收尾 → 铸新 build 跑复测：$RETEST_LABEL"
     fi
     # 读上次 build_seq（默认 1000 → 首个 build = 1001），+1
     LAST=$(jq -r ".versions.\"$BV\".build_seq // 1000" "$BASELINE_FILE" 2>/dev/null)
     BUILD_SEQ=$((LAST + 1)); [ "$BUILD_SEQ" -lt 1001 ] && BUILD_SEQ=1001
     BUILD="${BV}_build${BUILD_SEQ}"   # 如 V0.1.0_build1001
     # ★ 回写 build_seq + current_build；builds[] 是数组追加，故走 LockedBaseline 同一把锁。
     #   ⛔ 不裸 `jq … > tmp && mv`（见 invariants「baseline 单一写入口不变式」）。
     $BE --version "$BV" set build_seq "$BUILD_SEQ" current_build "$BUILD"
     # 新build清旧轮连续失败计数；原根任务预算不清零。
     $BE --version "$BV" del aiauto_test_unconverged_streak 2>/dev/null || true
     $BE --version "$BV" del cicd_run.cicd_retry_count 2>/dev/null || true
     $BE --version "$BV" del dev_fail_streak dev_fail_phase 2>/dev/null || true
     BUILD="$BUILD" BV="$BV" RETEST_OF="$RETEST_OF" RETEST_ROUND="$RETEST_ROUND" \
     ENTRY_MODE="$ENTRY_MODE" python3 - <<'PY'
import os, sys
sys.path.insert(0, "{{AIDP_HOME}}/scripts")
from baseline_edit import LockedBaseline, now_iso   # 同一把 flock + 锁内重读 + 原子替换
bv, b = os.environ["BV"], os.environ["BUILD"]
entry = {"build": b, "started_at": now_iso(), "status": "running"}
# ★ entry_mode 落【build 级】（勿删，理由见上方复用分支注释）：收尾门与 Stop hook 都优先读这里。
if os.environ.get("ENTRY_MODE"):
    entry["entry_mode"] = os.environ["ENTRY_MODE"]
if os.environ.get("RETEST_OF"):
    entry["retest_of"] = os.environ["RETEST_OF"]
    entry["retest_round"] = int(os.environ.get("RETEST_ROUND") or 0)
with LockedBaseline("memory/.sprint-autopilot-baseline.json", write=True) as bl:
    ver = bl.data.setdefault("versions", {}).setdefault(bv, {})
    # ★ test-only 复用部署：登记此刻 last_deployed_at；测试链路仅在它仍等于当前值时豁免归属门。
    #   为空 = 从没部署过，不登记。理据见同目录 rationale.md。
    if os.environ.get("ENTRY_MODE") == "test-only":
        _ld = ver.get("last_deployed_at") or ""
        if _ld:
            entry["deploy_reuse_of"] = _ld
            entry["deploy_reuse_reason"] = "test-only：本轮无新代码变更，复用最近一次部署"
    # ★ 按 build upsert：`set current_build` 已登记占位行，append 会同号两行
    builds = ver.get("builds", [])
    row = {k: v for x in builds + [entry] if x.get("build") == b for k, v in x.items()}
    ver["builds"] = [x for x in builds if x.get("build") != b] + [row]
PY
     echo "🔢 铸造 build 号：$BUILD（已落盘 build_seq=$BUILD_SEQ；下次重跑自增，不停在 1001；不打 git 分支/tag）${RETEST_LABEL:+ · $RETEST_LABEL}"
   fi
   # RETEST_LABEL非空时，#0/#D标题或首行展示复测轮次和上轮通过率。
```
