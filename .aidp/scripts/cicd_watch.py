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
    冷启动等待 / 就绪探针 / 写 last_deployed_at → 归 `autopilot-deploy-watch.py`

平台差异全部收在 `cicd_providers.py`：`memory/aidp-config.yaml` 的 `cicd.provider` 选
`github-actions`（默认）/ `gitlab-ci` / `jenkins` / `command`（任意平台自定义命令）/ `none`；
`cicd.pipelines.<env>` 给出各环境的流水线标识。

★ 读写分离：`detect` / `poll` / `watch` **只读**，把"该不该触发 / 该不该重试"判成结论
（`next_action`），写动作由调用方显式再调 `--mode trigger` / `--mode retry`。
是否允许无人值守自动执行写动作由调用方按 `cicd.auto_trigger` 决定，本脚本不越权代判。

## 用法

    # 全流程（默认）：先 detect，命中则 poll 到终态
    python3 AIDP_HOME/scripts/cicd_watch.py --commit "$GIT_PUSH_COMMIT" --env test \
        --version V0.1.0 [--push-at "2026-08-20T10:00:00"] [--post-push-wait 10]

    python3 AIDP_HOME/scripts/cicd_watch.py --mode detect  --commit <sha> --env test
    python3 AIDP_HOME/scripts/cicd_watch.py --mode poll    --run-id <id> --commit <push-sha> --env test
    python3 AIDP_HOME/scripts/cicd_watch.py --mode trigger --env test [--ref <branch>]
    python3 AIDP_HOME/scripts/cicd_watch.py --mode retry   --run-id <id>  --env test
    python3 AIDP_HOME/scripts/cicd_watch.py --selftest     # 离线自测（假平台输出，不访问网络）

## 退出码（★ 与闸门类脚本的 0/1/2 语义不同，按本文档为准）

    0 —— 运行**终态成功**（next_action=probe）；detect 已命中运行（next_action=poll）；
         trigger / retry 已受理（next_action=poll：已拿到 run_id；=detect：需按 commit 再探测）；
         poll / watch 到 `--timeout` 仍在运行（verdict=running，next_action=poll：下个 tick 继续 poll 同一 run_id，
         不交人工、不耗重试配额；`--timeout` 默认 480s，保证单次调用短于宿主工具的 10 分钟上限）
    1 —— **需要调用方做写动作**：next_action=trigger（未被触发）或 next_action=retry（失败且配额未尽）
    2 —— **需人工介入或按 streak 记账**：重试已用尽 / 锚定运行消失 / 平台不可达 / 写动作被拒
         （★ parse-error / unreachable / failed 三态分开：**解析不了** ≠ **取不到状态**
           ≠ **取到了失败态**——处置方向完全不同：报修脚本 / 修环境 / 直接重试。
           前两者绝不空耗重试配额。）
    3 —— 未接入或环境不满足：verdict ∈ disabled / not-configured（未接入 CICD → 只 push、不监听）；
         cli-missing / unauthenticated / provider-unavailable（CLI 未装 / 未登录 / 凭据失效 → 调用方按
         streak 记账后冻结为可自动复探的 `cicd-cli-unavailable`）；bad-args（参数缺失）

输出键：verdict / next_action / run_id / run_commit（命中运行的 commit，取不到为 null）/ run_url / reason …

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
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cicd_providers as cp  # noqa: E402

DEFAULT_BASELINE = Path("memory") / ".sprint-autopilot-baseline.json"
SELF = runtime_text('python3 __AIDP_HOME__/scripts/cicd_watch.py', __file__)


def log(msg):
    print(msg, file=sys.stderr, flush=True)


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


def _cmd(mode, env, pipeline, run_id=None):
    parts = [SELF, "--mode", mode]
    parts += ["--env", env] if env else (["--pipeline", pipeline] if pipeline else [])
    if run_id:
        parts += ["--run-id", str(run_id)]
    return " ".join(parts)


def run(argv, root_override=None):
    ap = argparse.ArgumentParser(description="CICD 推送即监听（平台无关）")
    ap.add_argument("--mode", choices=("watch", "detect", "poll", "trigger", "retry"), default="watch")
    ap.add_argument("--selftest", action="store_true", help="离线自测（假平台输出，不访问网络）")
    ap.add_argument("--commit", help="本次 push 的 HEAD commit（detect 的强绑定依据）")
    ap.add_argument("--push-at", help="push 完成时刻 ISO 串；同一 commit 多次运行时取其后最新的一条")
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
    out = {"ok": False, "mode": a.mode, "checked_at": datetime.now().isoformat(timespec="seconds")}

    def emit(code, **kw):
        out.update(kw)
        out.setdefault("run_commit", None)
        print(json.dumps(out, ensure_ascii=False))
        return code

    if a.mode in ("watch", "detect") and not a.commit:
        return emit(3, verdict="bad-args", next_action="abort", reason=f"{a.mode} 模式必须传 --commit")
    if a.mode in ("poll", "retry") and not a.run_id:
        return emit(3, verdict="bad-args", next_action="abort", reason=f"{a.mode} 模式必须传 --run-id")
    if a.mode == "poll" and not (a.commit or "").strip():
        return emit(3, verdict="bad-args", next_action="abort", reason="poll 模式必须传 --commit（本次 push SHA）")

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

    p_ok, p_verdict, p_reason = provider.check()
    if not p_ok:
        return emit(3, verdict=p_verdict, next_action="abort", reason=p_reason)

    max_retries = a.max_retries if a.max_retries is not None else int(cfg.get("max_retries", 3))
    try:
        retried = a.retry_count if a.retry_count is not None else int(bl.get("cicd_retry_count") or 0)
    except (TypeError, ValueError):
        retried = 0
    out.update(retry_count=retried, max_retries=max_retries)

    # ── 写动作 ────────────────────────────────────────────────────────────────
    if a.mode == "trigger":
        ref = a.ref or current_branch(root) or "main"
        ok, res = provider.trigger(pipeline, ref)
        if not ok:
            return emit(2, verdict="trigger-failed", next_action="abort", reason=str(res))
        return emit(0, ok=True, verdict="triggered", ref=ref, run_id=res, run_commit=a.commit,
                    next_action="poll" if res else "detect",
                    reason="已受理" + ("" if res else "，运行 id 需按 commit 探测"))
    if a.mode == "retry":
        ok, res = provider.retry(pipeline, a.run_id)
        if not ok:
            return emit(2, verdict="retry-failed", next_action="abort", reason=str(res))
        return emit(0, ok=True, verdict="retried", run_id=res, retried_from=a.run_id, run_commit=a.commit,
                    next_action="poll" if res else "detect",
                    reason="已受理" + ("" if res else "，新运行 id 需按 commit 探测"))

    # ── 只读：detect / poll ─────────────────────────────────────────────────────
    hit = None
    if a.mode in ("watch", "detect"):
        hit, verified, reason = do_detect(provider, pipeline, a)
        out["commit_verified"] = verified
        if hit is None and reason.startswith("parse-error:"):
            return emit(2, triggered=False, verdict="parse-error", next_action="abort",
                        reason=reason[len("parse-error:"):] + "｜⚠️ 平台输出解析失败，请检查 CICD 适配配置或报修脚本")
        if hit is None and reason.startswith("unreachable:"):
            return emit(2, triggered=False, verdict="unreachable", next_action="abort",
                        reason=reason[len("unreachable:"):])
        if hit is None:
            return emit(1, ok=True, triggered=False, verdict="not-triggered", next_action="trigger",
                        reason="本次 commit 未起跑该流水线的任何运行",
                        trigger_cmd=_cmd("trigger", a.env, a.pipeline))
        out.update(triggered=True, run_id=hit.get("id"), trigger=hit.get("event"),
                   run_url=hit.get("url"), detect_reason=reason, run_commit=hit.get("commit"))
        if a.mode == "detect":
            return emit(0, ok=True, verdict="triggered", next_action="poll", status=status_text(hit))

    run_id = a.run_id or (hit or {}).get("id")
    out["run_id"] = run_id
    verdict, got, why = do_poll(provider, pipeline, run_id, a)
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
                        retry_cmd=_cmd("retry", a.env, a.pipeline, run_id))
        return emit(2, ok=False, next_action="abort", reason=f"{why}；重试已用尽（{retried}/{max_retries}）")
    if verdict == "commit-mismatch":
        return emit(2, ok=False, next_action="abort")
    if verdict == "parse-error":
        return emit(2, ok=False, next_action="abort",
                    reason=f"{why}｜⚠️ 这是解析缺陷（非平台不可达），请检查 CICD 适配配置或报修脚本；"
                           f"报修前若需推进，按约定 31.5 口径**直接重试**（CICD 失败的第一动作恒为重试），"
                           f"**不要回头查业务代码**")
    # unreachable / vanished / unknown-status —— 交调用方处置（unreachable 按 streak 记账），不消耗重试配额
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
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.write(text)

        cp.EXEC, cp.HTTP = fake_exec, fake_http

        def go(argv):
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                code = run(argv + ["--post-push-wait", "0", "--interval", "0"], root_override=tmp)
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
