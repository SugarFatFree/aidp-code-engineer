#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aidp_scheduler.py —— 7×24 无人值守的操作系统调度装配器（开发链路 + 测试链路各一个定时任务）。

## 为什么用操作系统调度

`/sprint-autopilot`（开发链路）与 `/sprint-aiauto-test`（测试链路）都是「被反复唤起的单次执行体」。
Claude Code 会话内的 `/loop` 是会话级定时任务：会话关闭即停、定时任务 7 天后过期、只在会话空闲时触发，
同一会话里挂两条时实际串行。7×24 需要两个**独立进程**分别按周期唤起两条链路，互不阻塞，
这正是操作系统调度器（systemd timer / cron / launchd / Windows 计划任务）的职责。

每个定时任务调用 `.aidp/scripts/agent_loop.sh --once <命令> --unattended`：
agent_loop 负责选 Agent、拼非交互命令、补 `--no-loop`、flock 互斥、写日志；本脚本只负责装配与巡检。

## 子命令

    install    [--agent A] [--dev-interval 10m] [--test-interval 5m] [--platform P] [--dry-run] [--json]
    uninstall  [--platform P] [--dry-run] [--json]
    status     [--platform P] [--json]
    watchdog   [--quiet] [--json]          # 心跳巡检：任一链路超过 stale_cycles × 周期无心跳 → 本地告警 + 通知
    --self-check

平台（`--platform` 缺省自动判定）：
  systemd   Linux 且 `systemctl --user` 可用 → `~/.config/systemd/user/aidp-<项目>-{dev,test}.{service,timer}`
  cron      Linux 无 systemd 用户实例 → 用户 crontab 中带 `# AIDP-SCHEDULER <项目>` 标记的两行
  launchd   macOS → `~/Library/LaunchAgents/com.aidp.<项目>.{dev,test}.plist`
  schtasks  Windows → 只输出 `schtasks` 命令（需在 Git Bash / WSL 等可运行 bash 的环境下执行），不自动执行

配置：`memory/aidp-config.yaml` 的 `scheduler` 段（`dev_interval` / `test_interval` / `agent` / `stale_cycles` / `exec`），
命令行参数优先。心跳：开发链路 `autopilot_loop_heartbeat_at`、测试链路 `aiauto_test_heartbeat_at`（baseline 顶层）。

## 退出码

  0 = 成功（watchdog：无陈旧链路）
  2 = 用法错 / 平台不支持 / 装配命令执行失败
  3 = watchdog 检出陈旧链路（已写告警台账）
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

CHAINS = {
    "dev": {"command": "sprint-autopilot", "heartbeat": "autopilot_loop_heartbeat_at",
            "interval_key": "dev_interval", "label": "开发链路"},
    "test": {"command": "sprint-aiauto-test", "heartbeat": "aiauto_test_heartbeat_at",
             "interval_key": "test_interval", "label": "测试链路"},
}
PLATFORMS = ("systemd", "cron", "launchd", "schtasks")
BASELINE_REL = os.path.join("memory", ".sprint-autopilot-baseline.json")
ALERTS_REL = os.path.join("memory", ".aidp", "alerts.jsonl")
WATCHDOG_STATE_REL = os.path.join("memory", ".aidp", "scheduler-watchdog.json")
CRON_MARK = "# AIDP-SCHEDULER"
GRACE_SECONDS = 300


# ───────────────────────── 通用 ─────────────────────────

def parse_interval(text):
    """`30s` / `10m` / `1h` → 秒；非法返回 None。定时任务最小粒度 1 分钟。"""
    m = re.fullmatch(r"\s*(\d+)\s*([smh])\s*", str(text or ""))
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2)
    secs = n * {"s": 1, "m": 60, "h": 3600}[unit]
    return secs if secs >= 60 else None


def project_root(start="."):
    try:
        r = subprocess.run(["git", "-C", start, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.abspath(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.abspath(start)


def project_slug(root):
    """项目标识：目录名（仅保留安全字符）+ 绝对路径短哈希，避免同名目录的定时任务互相覆盖。"""
    base = re.sub(r"[^A-Za-z0-9_-]+", "-", os.path.basename(os.path.abspath(root))).strip("-") or "project"
    h = hashlib.sha1(os.path.abspath(root).encode("utf-8")).hexdigest()[:8]
    return f"{base}-{h}"


def scheduler_config(root):
    try:
        import aidp_config
        return aidp_config.scheduler_config(root)
    except Exception:  # noqa: BLE001
        return {"dev_interval": "10m", "test_interval": "5m", "agent": "auto", "stale_cycles": 3, "exec": {}}


def detect_platform():
    if sys.platform == "darwin":
        return "launchd"
    if sys.platform.startswith(("win", "cygwin", "msys")):
        return "schtasks"
    if shutil.which("systemctl"):
        try:
            r = subprocess.run(["systemctl", "--user", "show-environment"],
                               capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                return "systemd"
        except (OSError, subprocess.SubprocessError):
            pass
    return "cron"


def _q(s):
    """POSIX shell 单引号转义。"""
    return "'" + str(s).replace("'", "'\"'\"'") + "'"


def chain_argv(root, chain):
    return ["/bin/bash", os.path.join(root, ".aidp", "scripts", "agent_loop.sh"),
            "--once", CHAINS[chain]["command"], "--unattended"]


def chain_env(agent):
    """定时任务环境：装配时刻的 PATH（调度器默认 PATH 通常找不到 claude / codex 等 CLI）+ 可选 AIDP_AGENT。

    通知 webhook、CICD 令牌等凭据环境变量不写进定时任务定义：放 `~/.config/aidp/env`（KEY=VALUE 行），
    由 agent_loop.sh 每轮加载。
    """
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")}
    if agent and agent != "auto":
        env["AIDP_AGENT"] = agent
    return env


# ───────────────────────── 渲染 ─────────────────────────

def _systemd_span(secs):
    return f"{secs // 60}min" if secs % 3600 else f"{secs // 3600}h"


def render_systemd(root, agent, intervals):
    """→ {文件路径: 内容}；落 `~/.config/systemd/user/`。"""
    slug = project_slug(root)
    d = os.path.join(os.path.expanduser("~"), ".config", "systemd", "user")
    files = {}
    for chain, meta in CHAINS.items():
        unit = f"aidp-{slug}-{chain}"
        env_lines = "".join(f"Environment=\"{k}={v}\"\n" for k, v in chain_env(agent).items())
        argv = " ".join(_q(a) if " " in a else a for a in chain_argv(root, chain))
        files[os.path.join(d, unit + ".service")] = (
            "[Unit]\n"
            f"Description=AIDP {meta['label']}（{meta['command']}）· {root}\n\n"
            "[Service]\n"
            "Type=oneshot\n"
            f"WorkingDirectory={root}\n"
            f"{env_lines}"
            f"ExecStart={argv}\n"
            "TimeoutStartSec=infinity\n")
        files[os.path.join(d, unit + ".timer")] = (
            "[Unit]\n"
            f"Description=AIDP {meta['label']} 定时器 · {root}\n\n"
            "[Timer]\n"
            "OnBootSec=2min\n"
            f"OnUnitInactiveSec={_systemd_span(intervals[chain])}\n"
            f"Unit={unit}.service\n"
            "Persistent=true\n\n"
            "[Install]\n"
            "WantedBy=timers.target\n")
    return files


def _cron_schedule(secs):
    mins = max(1, secs // 60)
    if mins < 60:
        return f"*/{mins} * * * *"
    hours = max(1, mins // 60)
    return f"0 */{hours} * * *" if hours < 24 else "0 0 * * *"


def render_cron(root, agent, intervals):
    """→ 带标记的 crontab 行列表。"""
    slug = project_slug(root)
    lines = []
    for chain in CHAINS:
        env = " ".join(f"{k}={_q(v)}" for k, v in chain_env(agent).items())
        cmd = " ".join(_q(a) for a in chain_argv(root, chain))
        lines.append(f"{_cron_schedule(intervals[chain])} cd {_q(root)} && "
                     f"{(env + ' ') if env else ''}{cmd} >/dev/null 2>&1 {CRON_MARK} {slug} {chain}")
    return lines


def render_launchd(root, agent, intervals):
    slug = project_slug(root)
    d = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
    files = {}
    for chain, meta in CHAINS.items():
        label = f"com.aidp.{slug}.{chain}"
        args = "".join(f"    <string>{_xml(a)}</string>\n" for a in chain_argv(root, chain))
        env = chain_env(agent)
        env_xml = ""
        if env:
            env_xml = ("  <key>EnvironmentVariables</key>\n  <dict>\n"
                       + "".join(f"    <key>{_xml(k)}</key><string>{_xml(v)}</string>\n" for k, v in env.items())
                       + "  </dict>\n")
        log = os.path.join(root, "memory", ".aidp", "logs", f"launchd-{chain}.log")
        files[os.path.join(d, label + ".plist")] = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n<dict>\n'
            f"  <key>Label</key><string>{_xml(label)}</string>\n"
            f"  <key>ProgramArguments</key>\n  <array>\n{args}  </array>\n"
            f"  <key>WorkingDirectory</key><string>{_xml(root)}</string>\n"
            f"{env_xml}"
            f"  <key>StartInterval</key><integer>{intervals[chain]}</integer>\n"
            "  <key>RunAtLoad</key><true/>\n"
            f"  <key>StandardOutPath</key><string>{_xml(log)}</string>\n"
            f"  <key>StandardErrorPath</key><string>{_xml(log)}</string>\n"
            "</dict>\n</plist>\n")
    return files


def _xml(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_schtasks(root, agent, intervals, uninstall=False):
    slug = project_slug(root)
    cmds = []
    for chain in CHAINS:
        name = f"AIDP\\{slug}-{chain}"
        if uninstall:
            cmds.append(f'schtasks /Delete /TN "{name}" /F')
            continue
        env = "".join(f"export {k}={v}; " for k, v in chain_env(agent).items())
        inner = f"cd '{root}' && {env}.aidp/scripts/agent_loop.sh --once {CHAINS[chain]['command']} --unattended"
        mins = max(1, intervals[chain] // 60)
        cmds.append(f'schtasks /Create /SC MINUTE /MO {mins} /TN "{name}" /TR "bash -lc \\"{inner}\\"" /F')
    return cmds


# ───────────────────────── 装配 ─────────────────────────

def _run(argv):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def _read_crontab():
    rc, out = _run(["crontab", "-l"])
    return out.splitlines() if rc == 0 else []


def _write_crontab(lines):
    try:
        r = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n",
                           capture_output=True, text=True, timeout=60)
        return r.returncode, (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return 127, str(e)


def resolve_intervals(root, a):
    cfg = scheduler_config(root)
    out = {}
    for chain, meta in CHAINS.items():
        raw = getattr(a, meta["interval_key"], None) or cfg.get(meta["interval_key"])
        secs = parse_interval(raw)
        if secs is None:
            raise ValueError(f"{meta['interval_key']}={raw!r} 非法（形如 5m / 10m / 1h，最小 1 分钟）")
        out[chain] = secs
    return out


def do_install(root, a):
    cfg = scheduler_config(root)
    agent = a.agent or cfg.get("agent") or "auto"
    intervals = resolve_intervals(root, a)
    plat = a.platform or detect_platform()
    res = {"action": "install", "platform": plat, "root": root, "agent": agent,
           "intervals": intervals, "dry_run": bool(a.dry_run), "files": {}, "commands": [], "notes": []}
    if plat == "systemd":
        files = render_systemd(root, agent, intervals)
        res["files"] = files
        units = sorted(os.path.basename(p) for p in files if p.endswith(".timer"))
        res["commands"] = [["systemctl", "--user", "daemon-reload"]] + \
            [["systemctl", "--user", "enable", "--now", u] for u in units]
        res["notes"].append("注销登录后仍要运行时执行一次：loginctl enable-linger \"$USER\"")
    elif plat == "cron":
        lines = render_cron(root, agent, intervals)
        res["cron_lines"] = lines
    elif plat == "launchd":
        files = render_launchd(root, agent, intervals)
        res["files"] = files
        res["commands"] = [["launchctl", "load", "-w", p] for p in sorted(files)]
    elif plat == "schtasks":
        res["commands"] = render_schtasks(root, agent, intervals)
        res["notes"].append("Windows 计划任务需手工在管理员终端执行上述 schtasks 命令（需可运行 bash 的环境）")
        return 0, res
    else:
        res["error"] = f"不支持的平台：{plat}"
        return 2, res
    res["notes"].append("非交互执行需 Agent 预授权工具权限，详见 .aidp/reference/agent-tools.md 第三节")
    if a.dry_run:
        return 0, res
    os.makedirs(os.path.join(root, "memory", ".aidp", "logs"), exist_ok=True)
    if plat == "cron":
        slug = project_slug(root)
        keep = [ln for ln in _read_crontab() if f"{CRON_MARK} {slug} " not in ln]
        rc, err = _write_crontab(keep + res["cron_lines"])
        if rc != 0:
            res["error"] = f"crontab 写入失败：{err.strip()[:200]}"
            return 2, res
        return 0, res
    for p, body in res["files"].items():
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(body)
    for argv in res["commands"]:
        rc, out = _run(argv)
        if rc != 0:
            res["error"] = f"{' '.join(argv)} 失败（rc={rc}）：{out.strip()[:200]}"
            return 2, res
    return 0, res


def do_uninstall(root, a):
    plat = a.platform or detect_platform()
    slug = project_slug(root)
    res = {"action": "uninstall", "platform": plat, "root": root, "dry_run": bool(a.dry_run),
           "removed": [], "commands": []}
    dummy = {c: 600 for c in CHAINS}
    if plat == "systemd":
        files = sorted(render_systemd(root, "auto", dummy))
        res["commands"] = [["systemctl", "--user", "disable", "--now", os.path.basename(p)]
                           for p in files if p.endswith(".timer")] + [["systemctl", "--user", "daemon-reload"]]
        res["removed"] = files
    elif plat == "launchd":
        files = sorted(render_launchd(root, "auto", dummy))
        res["commands"] = [["launchctl", "unload", "-w", p] for p in files]
        res["removed"] = files
    elif plat == "cron":
        res["removed"] = [ln for ln in _read_crontab() if f"{CRON_MARK} {slug} " in ln] if not a.dry_run else []
    elif plat == "schtasks":
        res["commands"] = render_schtasks(root, "auto", dummy, uninstall=True)
        return 0, res
    else:
        res["error"] = f"不支持的平台：{plat}"
        return 2, res
    if a.dry_run:
        return 0, res
    if plat == "cron":
        keep = [ln for ln in _read_crontab() if f"{CRON_MARK} {slug} " not in ln]
        rc, err = _write_crontab(keep)
        if rc != 0:
            res["error"] = f"crontab 写入失败：{err.strip()[:200]}"
            return 2, res
        return 0, res
    timers_first = [c for c in res["commands"] if "daemon-reload" not in c]
    for argv in timers_first:
        _run(argv)                      # 未装过时失败无害
    for p in res["removed"]:
        try:
            os.remove(p)
        except OSError:
            pass
    for argv in res["commands"]:
        if "daemon-reload" in argv:
            _run(argv)
    return 0, res


# ───────────────────────── 心跳巡检 ─────────────────────────

def _parse_ts(v):
    if not v:
        return None
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt


def lock_held(root, command):
    """该链路的 agent_loop 互斥锁当前是否被持有（= 一轮正在执行，长 tick 不算失联）。"""
    p = os.path.join(root, "memory", ".aidp", "locks", f"loop-{command}.lock")
    if not os.path.isfile(p):
        return False
    try:
        import fcntl
    except ImportError:
        return False
    try:
        with open(p, "a") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    except OSError:
        return False
    return False


def heartbeat_report(root, now=None, intervals=None):
    cfg = scheduler_config(root)
    now = now or datetime.now(timezone.utc)
    try:
        with open(os.path.join(root, BASELINE_REL), encoding="utf-8") as fh:
            bl = json.load(fh)
        if not isinstance(bl, dict):
            bl = {}
    except (OSError, ValueError):
        bl = {}
    out = {}
    for chain, meta in CHAINS.items():
        secs = (intervals or {}).get(chain) or parse_interval(cfg.get(meta["interval_key"])) \
            or parse_interval({"dev": "10m", "test": "5m"}[chain])
        threshold = int(cfg.get("stale_cycles") or 3) * secs + GRACE_SECONDS
        raw = bl.get(meta["heartbeat"])
        dt = _parse_ts(raw)
        age = int((now - dt).total_seconds()) if dt else None
        out[chain] = {"command": meta["command"], "heartbeat_key": meta["heartbeat"],
                      "heartbeat_at": raw, "age_seconds": age, "threshold_seconds": threshold,
                      "state": "unknown" if dt is None else ("stale" if age > threshold else "fresh")}
        if out[chain]["state"] == "stale" and lock_held(root, meta["command"]):
            out[chain]["state"] = "running"     # 本轮仍在执行（长 tick），不判失联
    return out


def _append_alert(root, rec):
    path = os.path.join(root, ALERTS_REL)
    try:
        import aidp_paths
        fn = getattr(aidp_paths, "alerts_ledger", None)
        if callable(fn):
            path = fn(root)
    except Exception:  # noqa: BLE001
        pass
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return path
    except OSError:
        return None


def do_watchdog(root, a, now=None, send_notify=True):
    rep = heartbeat_report(root, now=now)
    state_p = os.path.join(root, WATCHDOG_STATE_REL)
    try:
        with open(state_p, encoding="utf-8") as fh:
            state = json.load(fh)
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    stale, alerted = [], []
    for chain, r in rep.items():
        if r["state"] != "stale":
            state.pop(chain, None)
            continue
        stale.append(chain)
        if state.get(chain) == r["heartbeat_at"]:
            continue                      # 同一陈旧心跳只告警一次
        state[chain] = r["heartbeat_at"]
        label = CHAINS[chain]["label"]
        msg = (f"{label}（{r['command']}）已 {r['age_seconds'] // 60} 分钟无心跳"
               f"（阈值 {r['threshold_seconds'] // 60} 分钟，最后心跳 {r['heartbeat_at']}）。"
               f"请检查定时任务：python3 .aidp/scripts/aidp_scheduler.py status")
        rec = {"at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
               "source": "aidp_scheduler.watchdog", "kind": "loop-heartbeat-stale",
               "chain": chain, "command": r["command"], "heartbeat_at": r["heartbeat_at"],
               "age_seconds": r["age_seconds"], "threshold_seconds": r["threshold_seconds"],
               "message": msg}
        _append_alert(root, rec)
        sys.stderr.write(f"🚨 [AIDP-ALERT] {msg}\n")
        alerted.append(chain)
        if send_notify:
            notify = os.path.join(root, ".aidp", "scripts", "notify.py")
            if os.path.isfile(notify):
                try:
                    subprocess.run([sys.executable, notify, "--auto", "--alert", "--header-color", "red",
                                    "--title", f"{label}心跳中断", "--section", msg, "--repo-root", root],
                                   capture_output=True, text=True, timeout=90, cwd=root)
                except (OSError, subprocess.SubprocessError):
                    pass              # 通知失败不阻断：告警台账已落
    try:
        os.makedirs(os.path.dirname(state_p), exist_ok=True)
        with open(state_p, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False)
    except OSError:
        pass
    return (3 if stale else 0), {"action": "watchdog", "chains": rep, "stale": stale, "alerted": alerted}


def do_status(root, a):
    plat = a.platform or detect_platform()
    slug = project_slug(root)
    installed = {}
    if plat == "systemd":
        for p in render_systemd(root, "auto", {c: 600 for c in CHAINS}):
            if p.endswith(".timer"):
                installed[os.path.basename(p)] = os.path.isfile(p)
    elif plat == "launchd":
        for p in render_launchd(root, "auto", {c: 600 for c in CHAINS}):
            installed[os.path.basename(p)] = os.path.isfile(p)
    elif plat == "cron":
        tab = _read_crontab()
        for chain in CHAINS:
            installed[f"cron:{chain}"] = any(f"{CRON_MARK} {slug} {chain}" in ln for ln in tab)
    return 0, {"action": "status", "platform": plat, "root": root, "slug": slug,
               "installed": installed, "config": scheduler_config(root),
               "heartbeats": heartbeat_report(root)}


# ───────────────────────── 自检 ─────────────────────────

def _self_check():
    import tempfile
    ok = []
    d = tempfile.mkdtemp()
    home = tempfile.mkdtemp()
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = home
    try:
        iv = {"dev": 600, "test": 300}
        sd = render_systemd(d, "codex", iv)
        ok.append(("systemd 渲染 2 service + 2 timer", len(sd) == 4))
        ok.append(("systemd ExecStart 走 agent_loop --once 且带 --unattended",
                   all("agent_loop.sh --once" in v and "--unattended" in v
                       for k, v in sd.items() if k.endswith(".service"))))
        ok.append(("systemd 周期正确", any("OnUnitInactiveSec=10min" in v for v in sd.values())
                   and any("OnUnitInactiveSec=5min" in v for v in sd.values())))
        cr = render_cron(d, "auto", iv)
        ok.append(("cron 两行带标记", len(cr) == 2 and all(CRON_MARK in ln for ln in cr)
                   and cr[0].startswith("*/10 ") and cr[1].startswith("*/5 ")))
        ok.append(("launchd 渲染 StartInterval", any("<integer>300</integer>" in v
                                                    for v in render_launchd(d, "auto", iv).values())))
        ok.append(("schtasks 输出两条", len(render_schtasks(d, "auto", iv)) == 2))
        ok.append(("周期解析", parse_interval("10m") == 600 and parse_interval("30s") is None
                   and parse_interval("x") is None))
        os.makedirs(os.path.join(d, "memory"))
        old = "2000-01-01T00:00:00+00:00"
        with open(os.path.join(d, BASELINE_REL), "w", encoding="utf-8") as fh:
            json.dump({"aiauto_test_heartbeat_at": old}, fh)
        ns = argparse.Namespace(quiet=True, json=True)
        rc, res = do_watchdog(d, ns, send_notify=False)
        ok.append(("watchdog：测试链路陈旧 → rc=3 + 告警台账", rc == 3 and res["stale"] == ["test"]
                   and os.path.isfile(os.path.join(d, ALERTS_REL))))
        ok.append(("watchdog：开发链路无心跳记录 → unknown 不告警", res["chains"]["dev"]["state"] == "unknown"))
        rc2, res2 = do_watchdog(d, ns, send_notify=False)
        ok.append(("watchdog：同一陈旧心跳不重复告警", rc2 == 3 and res2["alerted"] == []))
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home
        shutil.rmtree(d, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if all(r for _, r in ok) else 1


# ───────────────────────── CLI ─────────────────────────

def _print(res, as_json, quiet=False):
    if as_json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return
    if quiet:
        return
    act = res.get("action")
    if res.get("error"):
        sys.stderr.write(f"⛔ {res['error']}\n")
    if act in ("install", "uninstall"):
        print(f"[{act}] platform={res.get('platform')} root={res.get('root')}"
              + (" （dry-run，未写入）" if res.get("dry_run") else ""))
        for p, body in (res.get("files") or {}).items():
            print(f"--- {p}\n{body}")
        for ln in res.get("cron_lines") or []:
            print(ln)
        for p in res.get("removed") or []:
            print(f"  - {p}")
        for c in res.get("commands") or []:
            print("  $ " + (c if isinstance(c, str) else " ".join(c)))
        for n in res.get("notes") or []:
            print("  ℹ️ " + n)
    elif act == "status":
        print(f"platform={res['platform']} slug={res['slug']}")
        for k, v in res["installed"].items():
            print(f"  {'✅' if v else '❌'} {k}")
        for chain, r in res["heartbeats"].items():
            print(f"  {CHAINS[chain]['label']}: {r['state']}（{r['heartbeat_key']}={r['heartbeat_at']}）")
    elif act == "watchdog":
        for chain, r in res["chains"].items():
            print(f"  {CHAINS[chain]['label']}: {r['state']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="AIDP 7×24 操作系统调度装配（开发链路 + 测试链路）")
    ap.add_argument("action", nargs="?", choices=("install", "uninstall", "status", "watchdog"))
    ap.add_argument("--agent", choices=("auto", "claude", "codex", "dsh"), default=None)
    ap.add_argument("--dev-interval", dest="dev_interval", default=None)
    ap.add_argument("--test-interval", dest="test_interval", default=None)
    ap.add_argument("--platform", choices=PLATFORMS, default=None)
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    if not a.action:
        ap.print_help(sys.stderr)
        return 2
    root = project_root(a.root)
    try:
        if a.action == "install":
            rc, res = do_install(root, a)
        elif a.action == "uninstall":
            rc, res = do_uninstall(root, a)
        elif a.action == "status":
            rc, res = do_status(root, a)
        else:
            rc, res = do_watchdog(root, a)
    except ValueError as e:
        sys.stderr.write(f"⛔ {e}\n")
        return 2
    _print(res, a.json, quiet=a.quiet)
    return rc


if __name__ == "__main__":
    sys.exit(main())
