#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cicd_watch.py —— CICD「推送即监听」确定性内核（约定 31.5，平台无关）

职责边界（`autopilot-deploy-watch.py` 的姊妹件）：

    detect  —— push 后查对应流水线**是否已被本次 commit 起跑**（commit 强绑定）
    poll    —— 按 run id **精确**轮询锚定的那次运行至终态，失败时告知调用方"该重试第几次"
    watch   —— detect + poll（默认）
    trigger —— 主动触发一次运行（写动作）
    retry   —— 重试一次失败的运行（写动作）
    consume —— 显式消费 JSON + 原始退出码，记录本 build 证据、冻结与出口（不调用平台）
    冷启动等待 / 就绪探针 / 写 last_deployed_at → 归 `autopilot-deploy-watch.py`

平台差异全部收在 `cicd_providers.py`：`memory/aidp-config.yaml` 的 `cicd.provider` 选
`github-actions`（默认）/ `gitlab-ci` / `jenkins` / `command`（任意平台自定义命令）/ `none`；
`cicd.pipelines.<env>` 给出各环境的流水线标识。

★ 读写分离：`detect` / `poll` / `watch` **只读**，把"该不该触发 / 该不该重试"判成结论
（`next_action`），写动作由调用方显式再调 `--mode trigger` / `--mode retry`。
trigger/retry 必须传 --execution-context，校验当前任务 deploy grant 后占用共享预算。
cicd.auto_trigger 缺省 false；旧布尔不是授权。当前明确 deploy grant 可复用现有 provider，
只有带用户来源的明确项目禁用仍阻止写入。只读监听不获得写权限或部署探针权限。
未授权写建议/探针转 NOT_REQUESTED + next_action=none + readonly=true，保留 observed_verdict；
真实失败仍 rc2/ok=false，不能假绿。consume 对该状态不冻结、不记部署成功、不留部署待办。
已授权 deploy 后，Command 原始 rc=4 仍独立表示 need-accept，不自动追加 --accept。

## 用法

    # 全流程（默认）：先 detect，命中则 poll 到终态
    python3 AIDP_HOME/scripts/cicd_watch.py --commit "$GIT_PUSH_COMMIT" --env test \
        --version V0.1.0 [--push-at "2026-08-20T10:00:00"] [--post-push-wait 10]

    python3 AIDP_HOME/scripts/cicd_watch.py --mode detect  --commit <sha> --env test
    python3 AIDP_HOME/scripts/cicd_watch.py --mode poll    --run-id <id> --commit <push-sha> --env test
    python3 AIDP_HOME/scripts/cicd_watch.py --mode trigger --env test --commit <sha> --execution-context <context.json> [--ref <branch>]
    python3 AIDP_HOME/scripts/cicd_watch.py --mode retry --run-id <id> --commit <sha> --env test --execution-context <context.json>
    python3 AIDP_HOME/scripts/cicd_watch.py --mode consume --version V0.1.0 --execution-context <context.json> --result result.json --result-code 4
    # detect/poll/watch 同样传当前 --execution-context；缺省仅观测，不交接部署探针。
    python3 AIDP_HOME/scripts/cicd_watch.py --selftest     # 离线自测（假平台输出，不访问网络）

## 退出码（★ 与闸门类脚本的 0/1/2 语义不同，按本文档为准）

    0 —— NOT_REQUESTED/none（未请求部署，仅只读观测，ok=false，绝非部署成功）；
         已授权部署时运行终态成功（next_action=probe）；detect 已命中运行（next_action=poll）；
         trigger / retry 已受理（next_action=poll：已拿到 run_id；=detect：需按 commit 再探测）；
         poll / watch 到 `--timeout` 仍在运行（verdict=running，next_action=poll：下个 tick 继续 poll 同一 run_id，
         不交人工、不耗重试配额；`--timeout` 默认 480s，保证单次调用短于宿主工具的 10 分钟上限）
    1 —— **需要调用方做写动作**：next_action=trigger（未被触发）或 next_action=retry（失败且配额未尽）
    4 —— 先看 JSON：`verdict=need-accept,next_action=accept` = 平台授权请求，不能放行。
         仅 `next_action=probe,degraded=true` 才是**降级放行就绪探针**
         （仅当 `cicd.push_auto_deploy` 已记录为 true）：
         平台给不出状态（不可达 / 运行消失 / 状态未知）或压根没观测到本次 commit 起跑的运行时，
         补等满 `cicd.push_deploy_min_wait_seconds`（缺省 300）后以 `verdict=…` `next_action=probe`
         `degraded=true` 放行 —— 调用方**照 rc=0 进就绪探针，⛔ 不冻结**。
         ★ 它防的是一个**自锁**的误冻：那类项目的流水线无法被单独触发（推送本身就是触发），
         于是「未起跑 → 主动触发」恒失败、「取不到状态 → 熔断」必然冻结，
         而冻结的解冻证据又是部署成功。⛔ 代价要记进部署证据：未经平台确认、失败不会自动重试、
         构建慢于等待时长时可能探到旧服务（故输出带 `degraded=true`，不得当作"确认成功"）。
         ⛔ `failed`（取到了明确失败态）**绝不降级**——那是真失败。
         ⛔ `cli-missing` / `unauthenticated` / `provider-unavailable`（rc=3）**同样不降级**：
         它们冻结成**可自动复探**的 `cicd-cli-unavailable`，装上 CLI / 重新登录即自行恢复，
         不是本路径要救的自锁形态；对它们降级只会让「CLI 没装」永久静默、CICD 观测形同虚设。
    2 —— **需人工介入或按 streak 记账**：重试已用尽 / 锚定运行消失 / 平台不可达 / 写动作被拒
         （★ parse-error / unreachable / failed 三态分开：**解析不了** ≠ **取不到状态**
           ≠ **取到了失败态**——处置方向完全不同：报修脚本 / 修环境 / 直接重试。
           前两者绝不空耗重试配额。）
    3 —— 未接入或环境不满足：verdict ∈ disabled / not-configured（未接入 CICD → 只 push、不监听）；
         cli-missing / unauthenticated / provider-unavailable（CLI 未装 / 未登录 / 凭据失效 → 调用方按
         streak 记账后冻结为可自动复探的 `cicd-cli-unavailable`）；bad-args（参数缺失）

consume 退出码：0=已记录可继续的结论（看 next_action）；1=已记账、让位；
2=拒绝推进/输入错误；3=已冻结。consume 不重试、不接受授权，也不写部署就绪时间。

输出键：verdict / next_action / expected_commit（请求 SHA，不是已观测 SHA）/
run_id / run_commit（命中运行的 commit，取不到为 null）/ run_url / reason …

stdout 恒为一行 JSON；诊断/进度写 stderr。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
from vcs import detect_mode, unsupported, EXIT_UNSUPPORTED
import argparse
import hashlib
import shlex
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cicd_providers as cp  # noqa: E402
import execution_policy as policy
from entry_context import load_context

DEFAULT_BASELINE = Path("memory") / ".sprint-autopilot-baseline.json"
SELF = runtime_text('python3 __AIDP_HOME__/scripts/cicd_watch.py', __file__)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def push_autodeploy_policy(root, override="auto", min_wait=None):
    """→ `(enabled, min_wait_seconds)`。`override`：auto 读配置 / yes / no；`min_wait` 显式给出时优先。"""
    enabled, wait = False, 300
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import aidp_config
        enabled = bool(aidp_config.cicd_push_auto_deploy(str(root)))
        wait = int(aidp_config.cicd_push_deploy_min_wait(str(root)))
    except Exception:  # noqa: BLE001 —— 读不到配置 → 保持「未记录」，⛔ 绝不凭空降级
        pass
    if override == "yes":
        enabled = True
    elif override == "no":
        enabled = False
    if min_wait is not None and min_wait >= 0:
        wait = min_wait
    return enabled, wait


def _epoch(iso):
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def remaining_wait(push_at, min_wait, now=None):
    """推送后还需等几秒才满最短时长。

    `push_at` 缺失 / 解析不了 → **从现在起等满**（保守侧）：宁可多等，也不要把
    「推送后还没来得及起跑」当成「平台取不到状态」而立刻降级。
    """
    now = time.time() if now is None else now
    pushed = _epoch(push_at)
    if pushed is None:
        return float(min_wait)
    return max(0.0, float(min_wait) - (now - pushed))


def degrade_to_probe(out, verdict, why, push_at, min_wait):
    """已记录「推送即自动部署」+ 平台给不出状态 → 补等满最短时长后以 **rc=4** 放行就绪探针。

    ★ 这条通道防的是一个**无恢复路径**的误冻：那类项目里流水线**无法被单独触发**
    （推送本身就是触发），于是「未起跑 → 主动触发」恒失败、「取不到状态 → 按 streak 熔断」
    必然冻结，而冻结的解冻证据又是部署成功 —— 自锁。
    ⛔ 代价必须讲明：本路径**未经平台确认**流水线结果，部署失败不会自动重试，
    构建慢于等待时长时就绪探针可能探到**旧服务**。故 `degraded=true` 必须落进输出，
    调用方要把它记进部署证据、不得当作"确认成功"。
    """
    left = remaining_wait(push_at, min_wait)
    if left > 0:
        log(f"⏳ 平台取不到流水线状态，本项目已记录推送即自动部署："
            f"补等 {int(left)}s（推送后至少 {min_wait}s）再交就绪探针…")
        time.sleep(left)
    log("⚠️ 未经平台确认流水线结果 → 降级为就绪探针；"
        "部署失败不会自动重试，构建慢于等待时长时可能探到旧服务")
    out.setdefault('run_commit', None)
    out.update(ok=True, verdict=verdict, next_action="probe", degraded=True, reason=why,
               degraded_reason=why, min_wait_seconds=min_wait, waited_seconds=int(left),
               push_at=push_at or None)
    print(json.dumps(out, ensure_ascii=False))
    return 4


def classify(run):
    """归一运行 → failed / success / running / unknown（穷尽，不留悬空态）。"""
    s = (run or {}).get("status")
    if s == "success":
        return "success"
    if s in ("failure", "cancelled"):
        return "failed"
    if s in ("queued", "running"):
        return "running"
    return "unknown"  # skipped / unknown：含糊终态，既不放行也不重试，交人工


def status_text(run):
    run = run or {}
    return str(run.get("raw_status") or run.get("status") or "")


def load_cicd_config(root):
    import aidp_config
    return aidp_config.cicd_config(str(root))


def _baseline_version(baseline, version):
    if not (baseline and version and Path(baseline).is_file()):
        return {}
    try:
        data = json.loads(Path(baseline).read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}
    return ((data.get("versions") or {}).get(version) or {}).get("cicd_run") or {}


def resolve_pipeline(cfg, provider, env, pipeline, baseline_pipeline=None):
    """定位流水线：显式 --pipeline > cicd.pipelines[env] > baseline cicd_run.pipeline > 唯一一条时自动取。

    返回 (pipeline, source)；解析不出返回 (None, 原因)。
    不需要逐环境映射的提供方（gitlab-ci）允许返回空串。
    """
    if pipeline:
        return pipeline, "--pipeline"
    pls = cfg.get("pipelines") or {}
    if env and env in pls and (pls[env] or not provider.needs_pipeline()):
        return pls[env], f"cicd.pipelines.{env}"
    if baseline_pipeline:
        return baseline_pipeline, "baseline versions.{V}.cicd_run.pipeline"
    if not provider.needs_pipeline():
        return "", f"{provider.name} 按提交自动运行，无需指定流水线"
    if not pls:
        return None, "memory/aidp-config.yaml 的 cicd.pipelines 为空（未配置流水线）"
    if env:
        return None, f"cicd.pipelines 无 env={env}（已配置：{','.join(pls)}）"
    if len(pls) == 1:
        k, v = next(iter(pls.items()))
        return v, f"cicd.pipelines.{k}（唯一一条，自动选中）"
    return None, f"已配置多条流水线（{','.join(pls)}），须显式 --env 或 --pipeline"


def current_branch(root):
    try:
        p = subprocess.run(["git", "-C", str(root), "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        b = (p.stdout or "").strip()
        return b if p.returncode == 0 and b and b != "HEAD" else None
    except (OSError, subprocess.SubprocessError):
        return None


def do_detect(provider, pipeline, args):
    """push 后查是否已被本次 commit 起跑。返回 (run|None, commit_verified, reason)。"""
    if args.post_push_wait > 0:
        log(f"⏳ push 后等 {args.post_push_wait}s，等待 {provider.name} 自动触发…")
        time.sleep(args.post_push_wait)
    ok, res = provider.list_runs(pipeline, args.commit, args.size)
    if not ok:
        if str(res).startswith(cp.PARSE_ERR):
            return None, False, "parse-error:" + str(res)[len(cp.PARSE_ERR):]
        return None, False, f"unreachable:{str(res).replace(cp.NOT_FOUND, '')}"
    # ★ commit 强绑定：服务端过滤之外本地再校验一次，防平台忽略过滤参数
    hits = [r for r in res if cp.match_commit(r, args.commit)]
    if args.push_at:
        later = [r for r in hits if str(r.get("created_at") or "") >= args.push_at]
        hits = later or hits
    if hits:
        hits.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return hits[0], True, "commit-matched"
    return None, False, "not-triggered"


def do_poll(provider, pipeline, run_id, args):
    """按 run id 精确轮询至终态。返回 (verdict, run|None, reason)。"""
    deadline = time.time() + args.timeout
    unknown_streak = 0
    while True:
        ok, res = provider.view_run(pipeline, run_id)
        if not ok:
            s = str(res)
            if s.startswith(cp.PARSE_ERR):
                return "parse-error", None, s[len(cp.PARSE_ERR):]
            if s.startswith(cp.NOT_FOUND):
                return "vanished", None, f"锚定运行 {run_id} 不存在（疑被删除或配置不符）：{s[len(cp.NOT_FOUND):]}"
            return "unreachable", None, s
        verdict = classify(res)
        observed = str((res or {}).get("commit") or "").strip()
        if (observed or verdict != "running") and not cp.match_commit(res, args.commit):
            return "commit-mismatch", None, (f"锚定运行 {run_id} 的 commit "
                                             f"{observed or '<empty>'} 与本次 push {args.commit} 不一致")
        if verdict in ("success", "failed"):
            return verdict, res, status_text(res)
        if verdict == "unknown":
            unknown_streak += 1
            if unknown_streak >= args.unknown_tolerance:
                return "unknown-status", res, f"运行状态连续 {unknown_streak} 次无法归类：{status_text(res)!r}"
        else:
            unknown_streak = 0
        if time.time() >= deadline:
            return "timeout", res, f"轮询超过 {args.timeout}s 仍未终态（当前 {status_text(res)!r}）"
        log(f"… 运行 {run_id} 状态 {status_text(res)!r}，{args.interval}s 后重查")
        time.sleep(args.interval)


def deployment_context(root, path, version=None):
    """授权只取当前任务的可验真上下文；配置和脚本调用本身不是用户来源。"""
    if not path:
        return None, '未提供 execution-context；主动部署未请求'
    try:
        ctx = load_context(root, path)
        if version and ctx['version'] != version:
            raise ValueError('execution-context 与请求 version 不一致')
        return policy.require_action(ctx, 'deploy'), None
    except (OSError, ValueError, TypeError) as exc:
        return None, str(exc)


def not_requested(out, reason, observed=None):
    """保留平台事实，撤销可执行写建议和探针授权。"""
    observed = observed or out.get('verdict')
    for key in ('trigger_cmd', 'retry_cmd', 'next_retry_count', 'retry_run_id', 'retry_commit'):
        out.pop(key, None)
    out.update(ok=False, verdict='NOT_REQUESTED', execution_status='NOT_REQUESTED',
               next_action='none', readonly=True, degraded=False, authorization_reason=reason)
    if observed and observed != 'NOT_REQUESTED':
        out['observed_verdict'] = observed
    return out


def write_operation(root, ctx, provider, cfg, pipeline, a):
    """每次主动平台操作先验权和占预算；真实工具错误按同输入持久化停止。"""
    ref = (a.ref or current_branch(root) or 'main') if a.mode == 'trigger' else None
    inputs = {'mode': a.mode, 'pipeline': pipeline, 'commit': a.commit,
              'ref': ref, 'run_id': a.run_id if a.mode == 'retry' else None, 'config': cfg}
    input_hash = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
    try:
        policy.require_action(ctx, 'deploy')
        policy.reserve_budget(root, ctx, 'processes', 1, input_hash, action='deploy')
        if a.mode == 'retry':
            policy.reserve_budget(root, ctx, 'retries', 1, input_hash, action='deploy')
    except (OSError, ValueError) as exc:
        return 2, dict(ok=False, verdict='execution-stopped', next_action='abort',
                      execution_status=getattr(exc, 'status', 'UNAUTHORIZED'), reason=str(exc),
                      policy_details=getattr(exc, 'details', {}))

    def finish(code, status, **result):
        policy.record_outcome(root, ctx, 'deploy', status, input_hash,
                              root_cause=result.get('reason'), evidence=result)
        return code, dict(result, execution_status=status)

    try:
        good, verdict, reason = provider.check()
        if not good:
            return finish(3, 'ENV_UNAVAILABLE', ok=False, verdict=verdict, next_action='abort', reason=reason)
        if a.mode == 'retry':
            found, observed = provider.view_run(pipeline, a.run_id)
            if not found:
                return finish(2, 'TOOL_ERROR', ok=False, verdict='retry-failed', next_action='abort',
                              reason=str(observed))
            if not cp.match_commit(observed, a.commit):
                return finish(2, 'FAIL', ok=False, verdict='commit-mismatch', next_action='abort',
                              reason='重试运行与本 build push_commit 不一致或未知，禁止写动作')
        ok, res = (provider.trigger(pipeline, ref) if a.mode == 'trigger'
                   else provider.retry(pipeline, a.run_id))
        if not ok:
            return finish(2, 'TOOL_ERROR', ok=False, verdict=a.mode + '-failed', next_action='abort',
                          reason=str(res))
        details = {'ref': ref} if a.mode == 'trigger' else {'retried_from': a.run_id}
        return finish(0, 'PASS', ok=True, verdict='triggered' if a.mode == 'trigger' else 'retried',
                      run_id=res, run_commit=None, next_action='poll' if res else 'detect',
                      reason='已受理' + ('' if res else '，运行 id 需按 commit 探测'), **details)
    except cp.NeedAccept as exc:
        policy.record_outcome(root, ctx, 'deploy', 'UNAUTHORIZED', input_hash,
                              root_cause=str(exc), evidence=exc.response)
        raise
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return finish(2, 'TOOL_ERROR', ok=False, verdict=a.mode + '-failed', next_action='abort', reason=str(exc))


def _cmd(mode, env, pipeline, run_id=None, *, context=None, commit=None):
    parts = ['--mode', mode]
    parts += ['--env', env] if env else (['--pipeline', pipeline] if pipeline else [])
    if run_id:
        parts += ['--run-id', str(run_id)]
    if context:
        parts += ['--execution-context', str(context)]
    if commit:
        parts += ['--commit', commit]
    return SELF + ' ' + shlex.join(parts)


def consume_result(a, root):
    """显式消费本次平台输出；独立围栏共用证据、冻结和出口，绝不执行平台写动作。"""
    baseline = Path(a.baseline)
    if not baseline.is_absolute():
        baseline = root / baseline
    here = Path(__file__).resolve().parent

    def call(script, *args):
        proc = subprocess.run([sys.executable, str(here / script), '--baseline', str(baseline),
                               *args], cwd=root, capture_output=True, text=True, timeout=60)
        if proc.returncode not in (0, 3):
            raise ValueError(f'{script} exit={proc.returncode}: {proc.stderr or proc.stdout}')
        return proc.returncode

    def edit(*args):
        return call('baseline_edit.py', '--version', a.version, *args)

    def done(code, action, reason, **details):
        print(json.dumps({'ok': code == 0, 'mode': 'consume', 'next_action': action,
                          'reason': reason, **details}, ensure_ascii=False))
        return code

    try:
        if not a.version or not a.result or a.result_code is None:
            raise ValueError('consume 必须传 --version / --result / --result-code')
        path = Path(a.result)
        result = json.loads((path if path.is_absolute() else root / path).read_text(encoding='utf-8'))
        if not isinstance(result, dict):
            raise ValueError('consume 输入必须是 CICD JSON 对象')
        node = json.loads(baseline.read_text(encoding='utf-8'))['versions'][a.version]
        build = next((b for b in node.get('builds', []) if b.get('build') == node.get('current_build')), {})
        push = build.get('push_commit') or ''
        classification = build.get('change_classification') or {}
        if classification.get('cicd_skipped') is True and not classification.get('classification_error'):
            return done(0, 'skip', '本 build 分类明确跳过 CICD')
        if not push:
            raise ValueError('本 build 缺 push_commit，禁止消费流水线证据')
        old = node.get('cicd_run') or {}
        verdict, action = result.get('verdict'), result.get('next_action')
        rc = a.result_code
        reason = result.get('reason') or result.get('degraded_reason') or verdict or 'invalid-result'
        edit('set', 'cicd_run.observation', json.dumps({'build': build['build'], 'push_commit': push,
             'exit_code': rc, 'result': result}, ensure_ascii=False),
             'cicd_run.status', 'unknown', 'cicd_run.degraded', 'false', 'cicd_run.commit_verified', 'false')
        edit('del', 'cicd_run.degraded_reason')
        ctx, authorization_reason = deployment_context(root, a.execution_context, a.version)
        # 未授权可选部署只记观测。旧结果不能把新任务的 push 权限升级为部署权限。
        if verdict == 'NOT_REQUESTED' or (ctx is None and action != 'poll'):
            bound = (result.get('mode') in ('detect', 'watch', 'poll', 'trigger', 'retry') and
                     result.get('expected_commit') == push and
                     (not old.get('pipeline') or result.get('pipeline') == old['pipeline']) and
                     (result.get('mode') != 'poll' or result.get('run_id') == old.get('run_id')))
            edit('run-state', '3.2.1-deploy', '3.3-audit' if bound else '3.2.1-deploy',
                 'done', '--pending', '', '--summary',
                 'NOT_REQUESTED：仅记录只读观测；主动部署与探针不执行' if bound else '只读观测未绑定本 build，拒绝推进')
            if not bound:
                return done(2, 'abort', '拒绝未绑定本 build 的只读观测')
            observed = result.get('observed_verdict') or verdict
            failed = observed in ('failed', 'trigger-failed', 'retry-failed', 'commit-mismatch',
                                  'parse-error', 'unreachable', 'vanished', 'unknown-status')
            edit('set', 'cicd_run.status', 'not_requested')
            return done(2 if failed else 0, 'none', reason, ok=False, verdict='NOT_REQUESTED',
                        execution_status='NOT_REQUESTED', readonly=True, observed_verdict=observed,
                        authorization_reason=result.get('authorization_reason') or authorization_reason)
        # 每次新结果先撤销旧 probe 游标；下面只有可核验成功或合法降级能再次前进。
        edit('run-state', '3.2.1-deploy', '3.2.1-deploy', 'done', '--pending', 'cicd-watch',
             '--summary', 'CI/CD 结果已记录；本次部署证据待核验')
        fail_args = ['--command', 'autopilot', '--version', a.version, '--build', build['build'],
                     '--phase', '3.2.1-deploy']

        def frozen(code):
            if code != 3:
                raise ValueError('即时冻结未成功落盘，禁止宣称已冻结')
            return done(3, 'abort', reason)

        if verdict in ('need-accept', 'auto-trigger-off'):
            # 平台授权边界独立于 auto_trigger。保留原请求，交互确认/无人值守冻结；不拼 --accept。
            return frozen(call('autopilot_fail_handle.py', *fail_args, '--freeze-now',
                               '--reason', 'cicd-auto-trigger-off', '--why', str(reason)))
        if verdict in ('trigger-failed', 'unknown-status') and not (rc == 4 and action == 'probe'):
            return frozen(call('autopilot_fail_handle.py', *fail_args, '--freeze-now',
                               '--reason', 'pipeline-unknown', '--why', str(reason)))
        if verdict == 'retry-failed':
            return frozen(call('autopilot_fail_handle.py', *fail_args, '--freeze-now',
                               '--reason', 'cicd-unreachable', '--why', str(reason)))
        if verdict == 'commit-mismatch':
            return frozen(call('autopilot_fail_handle.py', *fail_args, '--freeze-now',
                               '--reason', 'cicd-run-vanished', '--why', str(reason)))

        # push_commit 是锚点；未知平台结果仅绑定请求 SHA，不得伪造 run_commit/commit_verified。
        bound = (result.get('mode') in ('detect', 'watch', 'poll', 'trigger', 'retry') and
                 result.get('expected_commit') == push and
                 (not old.get('pipeline') or result.get('pipeline') == old['pipeline']) and
                 (result.get('mode') != 'poll' or result.get('run_id') == old.get('run_id')))
        if bound and rc in (0, 1, 2) and verdict in ('success', 'failed', 'running', 'triggered', 'retried'):
            # 确实取到平台响应才清连续环境故障；降级 unknown 不构成恢复证据。
            edit('del', 'cicd_unreachable_streak', 'cicd_cli_fail_streak')
        degraded = (result.get('mode') in ('detect', 'watch', 'poll') and
                    rc == 4 and action == 'probe' and result.get('degraded') is True and
                    result.get('push_auto_deploy') is True and
                    verdict in ('not-observed', 'unreachable', 'vanished', 'unknown-status'))
        success = (result.get('mode') in ('watch', 'poll') and rc == 0 and verdict == 'success' and
                   action == 'probe' and result.get('run_id') and
                   cp.match_commit({'commit': result.get('run_commit')}, push))
        if (degraded or success) and bound and not node.get('needs_human'):
            evidence = ['cicd_run.status', 'unknown' if degraded else 'success',
                        'cicd_run.degraded', json.dumps(degraded), 'cicd_run.expected_commit', push,
                        'cicd_run.commit_verified', json.dumps(not degraded)]
            if degraded:
                evidence += ['cicd_run.degraded_reason', str(result.get('degraded_reason') or reason)]
            edit('set', *evidence)
            if success:
                call('autopilot_fail_handle.py', *fail_args, '--success')
                for phase in ('3.2.1-deploy', '3.2.1-cicd'):
                    call('autopilot_fail_handle.py', '--command', 'autopilot', '--version', a.version,
                         '--phase', phase, '--success')
            edit('run-state', '3.2.1-deploy', '3.2.1-probe', 'done', '--pending', 'deploy-probe',
                 '--summary', ('流水线状态 unknown：' + str(reason) + '；降级交接就绪探针'
                               if degraded else '流水线成功；交接就绪探针'))
            return done(0, 'probe', reason)
        if rc == 4 or (action == 'probe' and not success) or (success and not bound):
            return done(2, 'abort', '拒绝无效、过期或未绑定本 build 的 probe 结果')
        if node.get('needs_human'):
            return done(3, 'abort', '版本已冻结，先按恢复契约处理')
        if verdict == 'failed' and rc == 2:
            return frozen(call('autopilot_fail_handle.py', *fail_args, '--freeze-now',
                               '--reason', 'deploy-unreachable', '--why', str(reason)))
        if verdict == 'vanished':
            return frozen(call('autopilot_fail_handle.py', *fail_args, '--freeze-now',
                               '--reason', 'cicd-run-vanished', '--why', str(reason)))
        # 平台环境计数保持版本级，与 env-reprobe 的恢复字段一致。
        if verdict == 'unreachable':
            code = call('autopilot_fail_handle.py', '--command', 'autopilot', '--version', a.version,
                        '--phase', '3.2.1-deploy', '--reason', 'cicd-unreachable',
                        '--streak-key', 'cicd_unreachable_streak', '--threshold', '3', '--why', str(reason))
            return done(code or 1, 'abort', reason)
        if verdict in ('cli-missing', 'unauthenticated', 'provider-unavailable'):
            code = call('autopilot_fail_handle.py', '--command', 'autopilot', '--version', a.version,
                        '--phase', '3.2.1-deploy', '--reason', 'cicd-cli-unavailable',
                        '--streak-key', 'cicd_cli_fail_streak', '--threshold', '3', '--why', str(reason))
            return done(code or 1, 'abort', reason)
        if action in ('poll', 'detect', 'trigger', 'retry') and not bound:
            return done(2, 'abort', '拒绝未绑定本 build 的继续监听或写动作结论')
        if rc == 0 and action == 'detect' and result.get('mode') in ('trigger', 'retry'):
            edit('del', 'cicd_run.run_id')
        if rc == 0 and action == 'poll' and not result.get('run_id'):
            return done(2, 'abort', 'poll 结论缺运行 id，禁止沿用旧运行')
        if rc == 0 and action == 'poll' and result.get('run_id') and bound:
            edit('set', 'cicd_run.run_id', str(result['run_id']), 'cicd_run.pipeline', result.get('pipeline') or '',
                 'cicd_run.run_commit', result.get('run_commit') or '',
                 'cicd_run.commit_verified', json.dumps(cp.match_commit({'commit': result.get('run_commit')}, push)))
        if rc in (0, 1) and action in ('poll', 'detect', 'trigger', 'retry'):
            return done(0, action, reason)
        return done(2, 'abort', reason)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        return done(2, 'abort', str(exc))


def run(argv, root_override=None):
    try:
        return _run(argv, root_override)
    except cp.NeedAccept as exc:
        result = dict(getattr(exc, 'cicd_result', {}), ok=False, verdict='need-accept', next_action='accept',
                      need_accept=True, provider_exit_code=4, action=exc.action,
                      reason=str(exc), provider_response=exc.response)
        denied = getattr(exc, 'authorization_reason', '缺少当前部署授权')
        if denied:
            not_requested(result, denied)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if denied else 4


def _run(argv, root_override=None):
    ap = argparse.ArgumentParser(description="CICD 推送即监听（平台无关）")
    ap.add_argument("--mode", choices=("watch", "detect", "poll", "trigger", "retry", "consume"), default="watch")
    ap.add_argument('--execution-context', help='当前任务 context.json；trigger/retry 必须有可追溯 deploy 授权')
    ap.add_argument('--result', help='consume：本次 cicd_watch JSON 文件')
    ap.add_argument('--result-code', type=int, help='consume：本次 cicd_watch 的原始退出码')
    ap.add_argument("--selftest", action="store_true", help="离线自测（假平台输出，不访问网络）")
    ap.add_argument("--commit", help="本次 push 的 HEAD commit（detect 的强绑定依据）")
    ap.add_argument("--push-at", help="push 完成时刻 ISO 串；同一 commit 多次运行时取其后最新的一条")
    ap.add_argument("--push-auto-deploy", choices=("auto", "yes", "no"), default="auto",
                    help="本项目是否推送即自动部署：auto 读 cicd.push_auto_deploy（缺省 false）/ yes / no")
    ap.add_argument("--min-wait", type=int, default=None,
                    help="推送即自动部署时，推送后最短等待秒数；不传读 cicd.push_deploy_min_wait_seconds（缺省 300）")
    ap.add_argument("--run-id", help="poll / retry 模式必填：平台上的运行 id")
    ap.add_argument("--env", help="dev|test|prod…（取 cicd.pipelines[env]）")
    ap.add_argument("--pipeline", help="显式流水线标识，优先于 --env")
    ap.add_argument("--ref", help="trigger 用的分支 / tag，缺省为当前分支")
    ap.add_argument("--post-push-wait", type=int, default=10, help="detect 前等待秒数，默认 10")
    ap.add_argument("--interval", type=int, default=25, help="轮询间隔秒，默认 25")
    ap.add_argument("--timeout", type=int, default=480,
                    help="单次调用内轮询上限秒，默认 480；到时仍在运行 → verdict=running（rc=0，下 tick 继续 poll）")
    ap.add_argument("--size", type=int, default=10, help="detect 时取最近 N 条运行，默认 10")
    ap.add_argument("--unknown-tolerance", type=int, default=5, help="状态连续无法归类多少次后交人工，默认 5")
    ap.add_argument("--max-retries", type=int, default=None, help="失败重试上限；不传读 cicd.max_retries（缺省 3）")
    ap.add_argument("--retry-count", type=int, default=None,
                    help="已重试次数；不传则读 baseline versions.{V}.cicd_run.cicd_retry_count")
    ap.add_argument("--version", help="baseline 版本号（读 retry_count / pipeline 用）")
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--root", default=".", help="仓库根，默认当前目录")
    a = ap.parse_args(argv)
    if a.selftest:
        r = selftest()
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["passed"] else 1

    root = Path(root_override or a.root).resolve()
    if detect_mode(root) != "git":
        print(json.dumps(unsupported("cicd-sha"), ensure_ascii=False))
        return EXIT_UNSUPPORTED
    if a.mode == 'consume':
        return consume_result(a, root)
    out = {"ok": False, "mode": a.mode, "expected_commit": a.commit,
           "checked_at": datetime.now().isoformat(timespec="seconds")}

    ctx, authorization_reason = deployment_context(root, a.execution_context, a.version)
    out['readonly'] = ctx is None

    def emit(code, **kw):
        out.update(kw)
        out.setdefault('run_commit', None)
        if ctx is None and (out.get('next_action') in ('trigger', 'retry', 'probe') or
                            out.get('verdict') == 'failed'):
            observed = out.get('verdict')
            not_requested(out, authorization_reason)
            code = 2 if observed in ('failed', 'unreachable', 'vanished', 'unknown-status') else 0
        print(json.dumps(out, ensure_ascii=False))
        return code

    def invoke(operation, *args):
        try:
            return operation(*args)
        except cp.NeedAccept as exc:
            exc.cicd_result = dict(out)
            exc.authorization_reason = authorization_reason
            raise

    def degrade(verdict, reason):
        if ctx is None:
            return emit(2 if verdict != 'not-observed' else 0, verdict=verdict,
                        next_action='probe', reason=reason)
        return degrade_to_probe(out, verdict, reason, a.push_at, push_min_wait)

    # ⛔ 用归一后的 `root`（它吃 `root_override`），不是原始 `a.root` ——
    #    否则离线自测与任何传 override 的调用方都会去读**当前目录**的配置，判据静默取错。
    push_auto, push_min_wait = push_autodeploy_policy(root, a.push_auto_deploy, a.min_wait)
    out["push_auto_deploy"] = push_auto

    if a.mode in ("watch", "detect") and not a.commit:
        return emit(3, verdict="bad-args", next_action="abort", reason=f"{a.mode} 模式必须传 --commit")
    if a.mode in ("poll", "retry") and not a.run_id:
        return emit(3, verdict="bad-args", next_action="abort", reason=f"{a.mode} 模式必须传 --run-id")
    if a.mode in ('poll', 'trigger', 'retry') and not (a.commit or '').strip():
        return emit(3, verdict='bad-args', next_action='abort', reason=f'{a.mode} 模式必须传 --commit（本次 push SHA）')

    try:
        cfg = load_cicd_config(root)
        provider = cp.get_provider(str(root), cfg)
    except Exception as e:  # noqa: BLE001
        return emit(3, verdict="not-configured", next_action="abort", reason=f"CICD 配置无效：{e}")
    out["provider"] = cfg.get("provider")
    if provider is None:
        return emit(3, verdict="disabled", next_action="abort", reason="cicd.provider=none（未接入 CICD）")

    bl = _baseline_version(a.baseline, a.version)
    pipeline, src = resolve_pipeline(cfg, provider, a.env, a.pipeline, bl.get("pipeline"))
    if pipeline is None:
        return emit(3, verdict="not-configured", next_action="abort", reason=src)
    out.update(pipeline=pipeline, pipeline_source=src)

    if a.mode in ('trigger', 'retry') and ctx is None:
        not_requested(out, authorization_reason)
        return emit(0, reason='本任务未授权主动部署；不执行平台写操作')

    max_retries = a.max_retries if a.max_retries is not None else int(cfg.get("max_retries", 3))
    try:
        retried = a.retry_count if a.retry_count is not None else int(bl.get("cicd_retry_count") or 0)
    except (TypeError, ValueError):
        retried = 0
    out.update(retry_count=retried, max_retries=max_retries)

    # 默认/旧布尔不是授权或禁令；仅保留有用户来源的明确项目禁用冲突。
    if a.mode in ('trigger', 'retry') and cfg.get('auto_trigger_explicitly_disabled') is True:
        return emit(2, verdict='auto-trigger-off', next_action='abort',
                    authorization_source=cfg.get('auto_trigger_source'),
                    reason='项目已明确禁止主动触发/重跑部署，保留用户策略来源；未执行平台写操作')
    if a.mode == 'retry' and retried >= max_retries:
        return emit(2, verdict='failed', next_action='abort',
                    reason=f'重试已用尽（{retried}/{max_retries}）')
    # ── 写动作：预算与错误记录覆盖实际平台调用 ─────────────────────────────────
    if a.mode in ('trigger', 'retry'):
        code, result = invoke(write_operation, root, ctx, provider, cfg, pipeline, a)
        return emit(code, **result)

    # ── 只读：detect / poll ─────────────────────────────────────────────────────
    p_ok, p_verdict, p_reason = invoke(provider.check)
    if not p_ok:
        return emit(3, verdict=p_verdict, next_action='abort', reason=p_reason)
    hit = None
    if a.mode in ("watch", "detect"):
        hit, verified, reason = invoke(do_detect, provider, pipeline, a)
        out["commit_verified"] = verified
        if hit is None and reason.startswith("parse-error:"):
            return emit(2, triggered=False, verdict="parse-error", next_action="abort",
                        reason=reason[len("parse-error:"):] + "｜⚠️ 平台输出解析失败，请检查 CICD 适配配置或报修脚本")
        if hit is None and reason.startswith("unreachable:"):
            why = reason[len("unreachable:"):]
            if push_auto:
                return degrade('unreachable', why)
            return emit(2, triggered=False, verdict="unreachable", next_action="abort",
                        reason=why)
        if hit is None:
            # ⛔ 推送即自动部署的项目不得走 trigger：那类流水线**无法被单独触发**，
            #    主动触发恒失败 → 按失败熔断 → 冻结，而解冻证据又是部署成功（自锁）。
            #    改为补等满最短时长后降级放行就绪探针（rc=4）。
            if push_auto:
                return degrade('not-observed', '已记录推送即自动部署，但未观测到本次 commit 起跑的运行')
            return emit(1, ok=True, triggered=False, verdict="not-triggered", next_action="trigger",
                        reason="本次 commit 未起跑该流水线的任何运行",
                        trigger_cmd=_cmd('trigger', a.env, a.pipeline, context=a.execution_context, commit=a.commit))
        out.update(triggered=True, run_id=hit.get("id"), trigger=hit.get("event"),
                   run_url=hit.get("url"), detect_reason=reason, run_commit=hit.get("commit"))
        if a.mode == "detect":
            return emit(0, ok=True, verdict="triggered", next_action="poll", status=status_text(hit))

    run_id = a.run_id or (hit or {}).get("id")
    out["run_id"] = run_id
    verdict, got, why = invoke(do_poll, provider, pipeline, run_id, a)
    out.update(verdict=verdict, reason=why, status=status_text(got) if got else None)
    if got and got.get("url"):
        out["run_url"] = got.get("url")
    if got and got.get("commit"):
        out["run_commit"] = got.get("commit")

    if verdict == "timeout":
        return emit(0, ok=True, verdict="running", next_action="poll",
                    reason=f"{why}｜单次调用已到 {a.timeout}s 上限，下个 tick 继续 poll 同一 run_id")

    if verdict == "success":
        return emit(0, ok=True, next_action="probe")
    if verdict == "failed":
        if retried < max_retries:
            return emit(1, ok=True, next_action="retry", next_retry_count=retried + 1,
                        retry_run_id=run_id, retry_commit=(got or {}).get("commit"),
                        retry_cmd=_cmd('retry', a.env, a.pipeline, run_id, context=a.execution_context, commit=a.commit))
        return emit(2, ok=False, next_action="abort", reason=f"{why}；重试已用尽（{retried}/{max_retries}）")
    if verdict == "commit-mismatch":
        return emit(2, ok=False, next_action="abort")
    if verdict == "parse-error":
        return emit(2, ok=False, next_action='abort',
                    reason=f'{why}｜这是解析缺陷（非平台不可达）；保留原错误并停止本次工具链，'
                           '修复输入或 CICD 适配后再运行，不触发平台重跑')
    # unreachable / vanished / unknown-status —— 交调用方处置（unreachable 按 streak 记账），不消耗重试配额
    # ★ 例外：已记录推送即自动部署时，"取不到状态"不构成冻结理由（见 degrade_to_probe）。
    #   ⛔ 但 `failed`（取到了明确失败态）绝不降级 —— 那是真失败，上面已先行返回。
    if push_auto and verdict in ("unreachable", "vanished", "unknown-status"):
        return degrade(verdict, why or verdict)
    return emit(2, ok=False, next_action="abort")


# ── 自测 ─────────────────────────────────────────────────────────────────────
def selftest():
    """`--selftest`：以假平台输出离线验证四类提供方 + 退出码路径（不访问网络）。"""
    import io
    import shutil
    import tempfile
    from contextlib import redirect_stdout, redirect_stderr

    res = {"cases": [], "passed": True}

    def case(name, cond):
        res["cases"].append({"case": name, "ok": bool(cond)})
        if not cond:
            res["passed"] = False

    sha = "0123456789abcdef0123456789abcdef01234567"
    sc = {}

    def fake_exec(argv, cwd, timeout, shell=False):
        if shell:  # command 提供方
            if "boom" in argv:
                return 1, "", "run 404 not found"
            if argv.startswith("list"):
                return 0, json.dumps([{"id": "c1", "status": "passed", "commit": sha}]), ""
            if argv.startswith("view"):
                return 0, "log line\n" + json.dumps({"id": "c1", "status": "failed", "commit": sha}), ""
            if argv.startswith("trigger"):
                return 0, json.dumps({"run_id": "c2"}), ""
            return 1, "", "unexpected"
        args = argv[1:]
        if args[:1] == ["--version"]:
            if sc.get("missing"):
                raise FileNotFoundError("gh")
            return 0, "gh version 2.50.0\n", ""
        if args[:2] == ["auth", "status"]:
            return (1, "", "not logged in") if sc.get("unauth") else (0, "Logged in", "")
        if args[:2] == ["run", "list"]:
            return 0, json.dumps(sc.get("list", []), indent=2), ""
        if args[:2] == ["run", "view"]:
            v = sc.get("view")
            if v == "404":
                return 1, "", "HTTP 404: Not Found"
            if v == "garbage":
                return 0, "not json at all", ""
            return 0, json.dumps(v, indent=2), ""
        if args[:2] == ["workflow", "run"]:
            sc["triggered"] = args
            return 0, "", ""
        if args[:2] == ["run", "rerun"]:
            return 0, "", ""
        return 1, "", "unexpected"

    def fake_http(method, url, headers, data, timeout):
        sc.setdefault("http", []).append((method, url, dict(headers)))
        if "/api/v4/projects/" in url:
            if not headers.get("PRIVATE-TOKEN"):
                return 401, "{}", {}
            if url.endswith("/pipeline?ref=main") and method == "POST":
                return 201, json.dumps({"id": 901}), {}
            if "/pipelines?" in url:
                return 200, json.dumps([{"id": 900, "status": "running", "sha": sha, "ref": "main"}]), {}
            if url.endswith("/pipelines/900"):
                return 200, json.dumps({"id": 900, "status": "success", "sha": sha}), {}
            return 200, json.dumps({"id": 1}), {}
        if url.startswith("https://ci.example.com"):
            if "crumbIssuer" in url:
                return 200, json.dumps({"crumbRequestField": "Jenkins-Crumb", "crumb": "x"}), {}
            if url.endswith("/build") and method == "POST":
                return 201, "", {}
            if "/job/team/job/deploy-test/api/json" in url:
                return 200, json.dumps({"builds": [
                    {"number": 12, "building": False, "result": "FAILURE",
                     "actions": [{"lastBuiltRevision": {"SHA1": sha, "branch": [{"name": "origin/main"}]}}]},
                    {"number": 11, "building": False, "result": "SUCCESS",
                     "actions": [{"lastBuiltRevision": {"SHA1": "f" * 40}}]}]}), {}
            if "/job/team/job/deploy-test/12/api/json" in url:
                view = sc.get("jenkins_views")
                if view:
                    return 200, json.dumps(view.pop(0)), {}
                return 200, json.dumps({"number": 12, "building": True, "result": None,
                                        "actions": [{"lastBuiltRevision": {"SHA1": sha}}]}), {}
            return 200, json.dumps({"mode": "NORMAL"}), {}
        raise OSError("unreachable host")

    tmp = tempfile.mkdtemp()
    saved = (cp.EXEC, cp.HTTP)
    env_saved = {k: os.environ.get(k) for k in ("AIDP_T_GL", "AIDP_T_JU", "AIDP_T_JT")}
    try:
        subprocess.run(["git", "init", "-q", tmp], check=True, capture_output=True)
        os.makedirs(os.path.join(tmp, "memory"))
        cfg_path = os.path.join(tmp, "memory", "aidp-config.yaml")

        def write_cfg(text):
            # 这是离线 provider 夹具的能力配置，授权另由真实 context 提供。
            with open(cfg_path, 'w', encoding='utf-8') as f:
                f.write(text.replace('cicd:\n', 'cicd:\n  auto_trigger: true\n', 1))

        cp.EXEC, cp.HTTP = fake_exec, fake_http
        from entry_context import resolve_context
        context = resolve_context(Path(tmp), 'sprint-dev', version='V0.1.0',
            additional_grants=['deploy'], authorization_source={'kind': 'user-text',
            'request_id': 'offline-selftest', 'text': '离线夹具授权部署；平台 I/O 全部由假实现替代'})['execution_context']

        def go(argv):
            if '--mode' in argv and argv[argv.index('--mode') + 1] in ('trigger', 'retry') and '--commit' not in argv:
                argv = argv + ['--commit', sha]
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = run(argv + ['--post-push-wait', '0', '--interval', '0',
                                   '--execution-context', context], root_override=tmp)
            return code, json.loads(buf.getvalue().strip().splitlines()[-1])

        case("状态归一：passed→success / canceled→cancelled / waiting_for_resource→queued",
             cp.normalize_status("passed") == "success" and cp.normalize_status("canceled") == "cancelled"
             and cp.normalize_status("waiting_for_resource") == "queued")
        case("classify：skipped → unknown（含糊终态不放行）", classify({"status": "skipped"}) == "unknown")
        d, _ = cp.parse_json_blob("[warn] log\n" + json.dumps({"a": 1}, indent=2))
        case("JSON 前混入日志行可解析", isinstance(d, dict))

        # provider=none
        write_cfg("cicd:\n  provider: none\n")
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("provider=none → exit 3 / disabled", code == 3 and o["verdict"] == "disabled")

        # github-actions
        write_cfg("cicd:\n  provider: github-actions\n  max_retries: 3\n  pipelines: {test: deploy-test.yml}\n")
        sc.clear(); sc["missing"] = True
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("[github] gh 未安装 → exit 3 / cli-missing", code == 3 and o["verdict"] == "cli-missing")
        sc.clear(); sc["unauth"] = True
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("[github] gh 未登录 → exit 3 / unauthenticated", code == 3 and o["verdict"] == "unauthenticated")
        sc.clear()
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "prod"])
        case("[github] env 未配置 → exit 3 / not-configured", code == 3 and o["verdict"] == "not-configured")
        sc.clear(); sc["list"] = []
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("[github] 未触发 → exit 1 / trigger + trigger_cmd 指向 --mode trigger",
             code == 1 and o["next_action"] == "trigger" and "--mode trigger --env test" in o["trigger_cmd"])
        code, o = go(["--mode", "trigger", "--env", "test", "--ref", "main"])
        case("[github] trigger → exit 0 / next_action=detect / gh workflow run 带 --ref",
             code == 0 and o["next_action"] == "detect"
             and sc.get("triggered") == ["workflow", "run", "deploy-test.yml", "--ref", "main"])
        sc["list"] = [{"databaseId": 77, "status": "in_progress", "conclusion": "", "headSha": sha,
                       "event": "push", "createdAt": "2026-09-01T00:00:00Z"},
                      {"databaseId": 78, "status": "queued", "conclusion": "", "headSha": "f" * 40,
                       "event": "push", "createdAt": "2026-09-02T00:00:00Z"}]
        code, o = go(["--mode", "detect", "--commit", sha[:8], "--env", "test"])
        case("[github] detect 命中（短 SHA、排除他人 commit）→ run_id=77",
             code == 0 and o["run_id"] == "77" and o["next_action"] == "poll")
        sc["view"] = {"databaseId": 77, "status": "completed", "conclusion": "success", "headSha": sha}
        code, o = go(["--commit", sha, "--env", "test"])
        case("[github] watch 成功 → exit 0 / probe", code == 0 and o["next_action"] == "probe")
        code, o = go(["--mode", "poll", "--run-id", "77", "--env", "test"])
        case("[github] poll 缺预期 commit → bad-args", code == 3 and o["verdict"] == "bad-args")
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha[:8], "--env", "test"])
        case("[github] poll 短 SHA 匹配 → probe", code == 0 and o["next_action"] == "probe")
        sc["view"]["headSha"] = "f" * 40
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha, "--env", "test"])
        case("[github] poll 错提交成功态 → fail-closed", code == 2 and o["next_action"] == "abort"
             and o["verdict"] == "commit-mismatch" and o["run_commit"] is None)
        sc["view"].pop("headSha")
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha, "--env", "test"])
        case("[github] poll 缺提交成功态 → fail-closed", code == 2 and o["next_action"] == "abort"
             and o["verdict"] == "commit-mismatch" and o["run_commit"] is None)
        sc["view"] = {"databaseId": 77, "status": "completed", "conclusion": "failure", "headSha": sha}
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha, "--env", "test", "--retry-count", "1"])
        case("[github] 失败且配额未尽 → exit 1 / retry",
             code == 1 and o["next_action"] == "retry" and o["next_retry_count"] == 2
             and o["retry_commit"] == sha and "--mode retry --env test --run-id 77" in o["retry_cmd"])
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha, "--env", "test", "--retry-count", "3"])
        case("[github] 重试已用尽 → exit 2", code == 2 and o["next_action"] == "abort")
        code, o = go(["--mode", "retry", "--run-id", "77", "--env", "test"])
        case("[github] retry → exit 0 / 沿用 run_id 继续 poll", code == 0 and o["run_id"] == "77"
             and o["next_action"] == "poll")
        sc["view"] = "404"
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha, "--env", "test"])
        case("[github] 运行不存在 → exit 2 / vanished", code == 2 and o["verdict"] == "vanished")
        sc["view"] = "garbage"
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha, "--env", "test"])
        case("[github] 输出不可解析 → exit 2 / parse-error", code == 2 and o["verdict"] == "parse-error")
        sc["view"] = {"databaseId": 77, "status": "completed", "conclusion": "neutral", "headSha": sha}
        code, o = go(["--mode", "poll", "--run-id", "77", "--commit", sha, "--env", "test", "--unknown-tolerance", "1"])
        case("[github] 含糊终态 → exit 2 / unknown-status", code == 2 and o["verdict"] == "unknown-status")

        # gitlab-ci
        write_cfg("cicd:\n  provider: gitlab-ci\n  pipelines: {test: main}\n  gitlab-ci:\n"
                  "    url: https://gitlab.example.com\n    project: group/demo\n    token_env: AIDP_T_GL\n")
        os.environ.pop("AIDP_T_GL", None)
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("[gitlab] 缺令牌 → exit 3 / unauthenticated", code == 3 and o["verdict"] == "unauthenticated")
        os.environ["AIDP_T_GL"] = "tok"
        sc.clear()
        code, o = go(["--commit", sha, "--env", "test"])
        case("[gitlab] watch：detect 命中 900 → poll success → exit 0",
             code == 0 and o["run_id"] == "900" and o["next_action"] == "probe")
        case("[gitlab] 项目路径 URL 编码 + 令牌头",
             any("projects/group%2Fdemo/pipelines?" in u and h.get("PRIVATE-TOKEN") == "tok"
                 for _, u, h in sc["http"]))
        code, o = go(["--mode", "trigger", "--env", "test"])
        case("[gitlab] trigger 返回新 pipeline id → next_action=poll",
             code == 0 and o["run_id"] == "901" and o["next_action"] == "poll")
        write_cfg("cicd:\n  provider: gitlab-ci\n  gitlab-ci:\n    project: group/demo\n    token_env: AIDP_T_GL\n")
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("[gitlab] 未配 pipelines 也可按提交探测", code == 0 and o["run_id"] == "900")

        # jenkins
        write_cfg("cicd:\n  provider: jenkins\n  pipelines: {test: team/deploy-test}\n  jenkins:\n"
                  "    url: https://ci.example.com\n    user_env: AIDP_T_JU\n    token_env: AIDP_T_JT\n")
        os.environ["AIDP_T_JU"], os.environ["AIDP_T_JT"] = "bot", "tok"
        sc.clear()
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("[jenkins] 按 lastBuiltRevision.SHA1 命中构建 12", code == 0 and o["run_id"] == "12")
        code, o = go(["--mode", "poll", "--run-id", "12", "--commit", sha, "--env", "test", "--timeout", "0"])
        case("[jenkins] building → 单次调用到上限仍在运行 → exit 0 / running / next_action=poll",
             code == 0 and o["verdict"] == "running" and o["next_action"] == "poll" and o["run_id"] == "12")
        case("输出恒带 run_commit 键", "run_commit" in o)
        queued = {"number": 12, "building": False, "result": None, "actions": []}
        building = {"number": 12, "building": True, "result": None,
                    "actions": [{"lastBuiltRevision": {"SHA1": sha}}]}
        success = {"number": 12, "building": False, "result": "SUCCESS",
                   "actions": [{"lastBuiltRevision": {"SHA1": sha}}]}
        sc["jenkins_views"] = [queued, dict(building, actions=[]), building, success]
        code, o = go(["--mode", "poll", "--run-id", "12", "--commit", sha, "--env", "test", "--timeout", "0"])
        case("[jenkins] queued 无 SHA → 继续 poll，无部署证据",
             code == 0 and o["verdict"] == "running" and o["next_action"] == "poll"
             and o["run_commit"] is None and "retry_commit" not in o)
        code, o = go(["--mode", "poll", "--run-id", "12", "--commit", sha, "--env", "test", "--timeout", "0"])
        case("[jenkins] building 无 SHA → 继续 poll，无部署证据",
             code == 0 and o["verdict"] == "running" and o["next_action"] == "poll"
             and o["run_commit"] is None and "retry_commit" not in o)
        code, o = go(["--mode", "poll", "--run-id", "12", "--commit", sha, "--env", "test", "--timeout", "0"])
        case("[jenkins] building SHA 出现且匹配 → 继续 poll",
             code == 0 and o["verdict"] == "running" and o["run_commit"] == sha)
        code, o = go(["--mode", "poll", "--run-id", "12", "--commit", sha, "--env", "test", "--timeout", "0"])
        case("[jenkins] success SHA 匹配 → probe", code == 0 and o["next_action"] == "probe"
             and o["run_commit"] == sha)
        sc["jenkins_views"] = [dict(success, actions=[]),
                                dict(success, actions=[{"lastBuiltRevision": {"SHA1": "f" * 40}}]),
                                dict(building, actions=[{"lastBuiltRevision": {"SHA1": "f" * 40}}])]
        for label in ("success 无 SHA", "success SHA 不匹配", "building SHA 不匹配"):
            code, o = go(["--mode", "poll", "--run-id", "12", "--commit", sha, "--env", "test", "--timeout", "0"])
            case(f"[jenkins] {label} → abort", code == 2 and o["verdict"] == "commit-mismatch"
                 and o["next_action"] == "abort" and o["run_commit"] is None)
        code, o = go(["--mode", "trigger", "--env", "test"])
        posted = [h for m, u, h in sc["http"] if m == "POST" and u.endswith("/job/team/job/deploy-test/build")]
        case("[jenkins] trigger 带 crumb 与 Basic 认证 → next_action=detect",
             code == 0 and o["next_action"] == "detect" and posted
             and posted[0].get("Jenkins-Crumb") == "x" and posted[0].get("Authorization", "").startswith("Basic "))

        # command
        write_cfg('cicd:\n  provider: command\n  pipelines: {test: web}\n  command:\n'
                  '    list: "list {pipeline} {commit}"\n    view: "view {run_id}"\n    trigger: "trigger {pipeline}"\n')
        sc.clear()
        code, o = go(["--commit", sha, "--env", "test", "--retry-count", "0"])
        case("[command] detect 命中 c1 → poll failed → exit 1 / retry",
             code == 1 and o["run_id"] == "c1" and o["next_action"] == "retry")
        code, o = go(["--mode", "trigger", "--env", "test"])
        case("[command] trigger 返回 run_id", code == 0 and o["run_id"] == "c2")
        code, o = go(["--mode", "retry", "--run-id", "c1", "--env", "test"])
        case("[command] 未配置 retry 模板 → exit 2 / retry-failed", code == 2 and o["verdict"] == "retry-failed")
        write_cfg('cicd:\n  provider: command\n  pipelines: {test: web}\n  command:\n    list: "list"\n')
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("[command] 缺 view 模板 → exit 3 / not-configured", code == 3 and o["verdict"] == "not-configured")

        write_cfg("cicd:\n  provider: circleci\n")
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test"])
        case("未知 provider → exit 3 / not-configured", code == 3 and o["verdict"] == "not-configured")

        # ── 推送即自动部署的降级通道（rc=4）★ 含阴性对照，证明它不是恒降级 ─────────
        # 平台给不出状态（list/view 恒失败）+ 已记录推送即自动部署 → 补等后 rc=4 放行就绪探针。
        # 夹具口径：`check` 走假平台的成功分支（preflight 通过），`list` 带 boom 触发失败
        # —— 必须让 preflight 先过，否则停在 `provider-unavailable`(rc=3) 根本走不到降级分支。
        dead = ('cicd:\n  provider: command\n  pipelines: {test: web}\n'
                '  push_auto_deploy: %s\n  push_deploy_min_wait_seconds: 1\n'
                '  command: {list: "list boom", view: "view", check: "trigger"}\n')
        write_cfg(dead % "true")
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test",
                      "--push-at", "2020-01-01T00:00:00", "--min-wait", "0"])
        case("★★[降级] 已记录推送即自动部署 + 取不到状态 → exit 4 / next_action=probe / degraded",
             code == 4 and o["next_action"] == "probe" and o.get("degraded") is True
             and o["verdict"] == "unreachable")
        # ⛔ 阴性对照：未记录推送即自动部署时**绝不降级** —— 否则任何平台故障都会被静默放行。
        write_cfg(dead % "false")
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test",
                      "--push-at", "2020-01-01T00:00:00"])
        case("★★[阴性] 未记录推送即自动部署 → 仍 exit 2 / abort，⛔ 不降级",
             code == 2 and o["next_action"] == "abort" and not o.get("degraded"))
        # 显式 --push-auto-deploy yes 覆盖配置（供演练与一次性放行）
        code, o = go(["--mode", "detect", "--commit", sha, "--env", "test",
                      "--push-auto-deploy", "yes", "--min-wait", "0"])
        case("[降级] --push-auto-deploy yes 覆盖配置 → exit 4", code == 4 and o.get("degraded") is True)
        # push_at 缺失 → 从现在起等满（保守侧），⛔ 不得当成"已等够"立刻降级
        case("★remaining_wait：push_at 缺失 → 返回完整 min_wait（保守侧，不得归零）",
             remaining_wait(None, 300) == 300.0)
        case("remaining_wait：推送已过半 → 只等剩余部分",
             int(remaining_wait("2026-01-01T00:00:00", 300,
                                now=_epoch("2026-01-01T00:02:00"))) == 180)
        case("★push_autodeploy_policy：读不到配置时保持未记录（⛔ 不凭空降级）",
             push_autodeploy_policy("/nonexistent-aidp-root")[0] is False)
    finally:
        cp.EXEC, cp.HTTP = saved
        for k, v in env_saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)
    return res


def main(argv=None):
    return run(sys.argv[1:] if argv is None else argv)


if __name__ == "__main__":
    sys.exit(main())
