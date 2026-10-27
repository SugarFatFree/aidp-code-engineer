#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aidp_scheduler.py —— 7×24 无人值守的操作系统调度装配器（开发、测试与独立巡检定时任务）。

## 为什么用操作系统调度

`/sprint-autopilot`（开发链路）与 `/sprint-aiauto-test`（测试链路）都是「被反复唤起的单次执行体」。
Claude Code 会话内的 `/loop` 是会话级定时任务：会话关闭即停、定时任务 7 天后过期、只在会话空闲时触发，
同一会话里挂两条时实际串行。7×24 需要两个**独立进程**分别按周期唤起两条链路，互不阻塞，
并用第三个任务独立巡检（两条链路均未启动时也能告警），这正是操作系统调度器
（systemd timer / cron / launchd / Windows 计划任务）的职责。

每个定时任务调用 `AIDP_HOME/scripts/agent_loop.sh --once <命令> --unattended`：
agent_loop 负责选 Agent、拼非交互命令、补 `--no-loop`、flock 互斥、写日志；本脚本只负责装配与巡检。

## 子命令

    install    [--agent A] [--dev-interval 10m] [--test-interval 5m] [--platform P] [--dry-run] [--json]
    uninstall  [--platform P] [--dry-run] [--json]
    status     [--platform P] [--json]
    watchdog   [--quiet] [--json]          # 心跳巡检：定时唤醒时无心跳从首次巡检起计时，超时告警
    tick-result --command C --rc N [--tick-max S] [--log P]   # agent_loop 每轮结束调用：超时记账 + 连续超时告警
    --self-check

平台（`--platform` 缺省自动判定）：
  systemd   Linux 且 `systemctl --user` 可用 → `~/.config/systemd/user/aidp-<项目>-{dev,test,watchdog}.{service,timer}`
  cron      Linux 无 systemd 用户实例 → 用户 crontab 中带 `# AIDP-SCHEDULER <项目>` 标记的三行
  launchd   macOS → `~/Library/LaunchAgents/com.aidp.<项目>.{dev,test,watchdog}.plist`
  schtasks  Windows → 只输出 `schtasks` 命令（需在 Git Bash / WSL 等可运行 bash 的环境下执行），不自动执行

配置：`memory/aidp-config.yaml` 的 `scheduler` 段（`dev_interval` / `test_interval` / `agent` / `stale_cycles` / `exec`），
命令行参数优先。心跳：开发链路 `autopilot_loop_heartbeat_at`、测试链路 `aiauto_test_heartbeat_at`（baseline 顶层）。

## 退出码

  0 = 成功（watchdog：无陈旧链路）
  2 = 用法错 / 平台不支持 / 装配命令执行失败
  3 = watchdog 检出陈旧链路（已写告警台账）
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
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
# 各链路连续 tick 超时计数（agent_loop 每轮结束经 `tick-result` 维护；非超时轮清零）
TICK_TIMEOUT_STATE_REL = os.path.join("memory", ".aidp", "tick-timeouts.json")
# 连续超时多少次升级为告警通知（每满一个周期再发一次，避免每轮刷屏）
try:
    TICK_TIMEOUT_ALERT_AFTER = max(1, int(os.environ.get("AIDP_TICK_TIMEOUT_ALERT_AFTER", "3") or 3))
except ValueError:
    TICK_TIMEOUT_ALERT_AFTER = 3
TIMEOUT_RCS = (124, 137)
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
    """调度目标根由调用参数决定，不依赖 Git 仓库探测。"""
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
    return ["/bin/bash", os.path.join(root, runtime_relpath("scripts/agent_loop.sh", __file__)),
            "--once", CHAINS[chain]["command"], "--unattended"]


def watchdog_argv(root):
    return [sys.executable, os.path.join(root, runtime_relpath("scripts/aidp_scheduler.py", __file__)),
            "watchdog", "--scheduled", "--root", root, "--quiet"]


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
    unit = f"aidp-{slug}-watchdog"
    argv = " ".join(_q(a) if " " in a else a for a in watchdog_argv(root))
    files[os.path.join(d, unit + ".service")] = (
        "[Unit]\n"
        f"Description=AIDP 心跳巡检 · {root}\n\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"WorkingDirectory={root}\n"
        f"ExecStart={argv}\n")
    files[os.path.join(d, unit + ".timer")] = (
        "[Unit]\n"
        f"Description=AIDP 心跳巡检定时器 · {root}\n\n"
        "[Timer]\n"
        "OnBootSec=2min\n"
        "OnUnitActiveSec=5min\n"
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
    cmd = " ".join(_q(a) for a in watchdog_argv(root))
    lines.append(f"*/5 * * * * cd {_q(root)} && {cmd} >/dev/null 2>&1 {CRON_MARK} {slug} watchdog")
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
    label = f"com.aidp.{slug}.watchdog"
    args = "".join(f"    <string>{_xml(a)}</string>\n" for a in watchdog_argv(root))
    log = os.path.join(root, "memory", ".aidp", "logs", "launchd-watchdog.log")
    files[os.path.join(d, label + ".plist")] = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"  <key>Label</key><string>{_xml(label)}</string>\n"
        f"  <key>ProgramArguments</key>\n  <array>\n{args}  </array>\n"
        f"  <key>WorkingDirectory</key><string>{_xml(root)}</string>\n"
        "  <key>StartInterval</key><integer>300</integer>\n"
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
    for chain in (*CHAINS, "watchdog"):
        name = f"AIDP\\{slug}-{chain}"
        if uninstall:
            cmds.append(f'schtasks /Delete /TN "{name}" /F')
            continue
        if chain == "watchdog":
            # ⛔ 不写死 python3：Windows 上通常只有 python / py，写死即 "不是内部或外部命令"。
            #    systemd / cron / launchd 三条路径早已走 watchdog_argv()（sys.executable），
            #    唯独这里漏了 —— 而 schtasks 恰恰只在 Windows 上用。
            argv = " ".join(_q(a) if " " in a else a for a in watchdog_argv(root))
            inner = f"cd '{root}' && {argv}"
            mins = 5
        else:
            env = "".join(f"export {k}={v}; " for k, v in chain_env(agent).items())
            inner = runtime_text(
                f"cd '{root}' && {env}__AIDP_HOME__/scripts/agent_loop.sh --once {CHAINS[chain]['command']} --unattended",
                __file__,
            )
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


# Claude Code headless（`claude -p`）下未预授权即被拒的工具：tick 至少要跑脚本、派子 Agent
CLAUDE_REQUIRED_ALLOW = ("Bash", "Agent")


def _claude_allow_gaps(root):
    """`.claude/settings.json` 的 permissions.allow 未覆盖的必需工具（读不到配置视为全缺）。"""
    allow, deny = [], []
    for path in (os.path.expanduser("~/.claude/settings.json"),
                 os.path.join(root, ".claude", "settings.json"),
                 os.path.join(root, ".claude", "settings.local.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                permissions = (json.load(fh) or {}).get("permissions") or {}
            allow.extend(permissions.get("allow") or [])
            deny.extend(permissions.get("deny") or [])
        except (OSError, ValueError, AttributeError, TypeError):
            continue
    # 细粒度规则不证明整轮可执行（Bash(python3:*) 不能覆盖 git/curl）；仍提示人工核验。
    return [t for t in CLAUDE_REQUIRED_ALLOW if t not in allow
            or any(isinstance(x, str) and (x == t or x.startswith(t + "(")) for x in deny)]


def _env_file_has(key):
    """`~/.config/aidp/env`（agent_loop 每轮加载）里是否给了非空的 KEY。"""
    try:
        with open(os.path.join(os.path.expanduser("~"), ".config", "aidp", "env"), encoding="utf-8") as fh:
            return any(ln.strip().startswith(key + "=") and ln.strip()[len(key) + 1:].strip()
                       for ln in fh)
    except OSError:
        return False


def install_preflight(root, agent, plat):
    """装配前预检 → (errors, warnings)。

    ⛔ 装上一个注定跑不起来的定时任务比不装更糟：每轮都失败、而失败只落在没人看的日志里。
    """
    errors, warns = [], []
    if plat in ("systemd", "cron", "launchd"):
        if not shutil.which("flock"):
            try:
                import fcntl  # noqa: F401
                warns.append("未找到 flock 命令：agent_loop 将退回 python3 fcntl 加锁")
            except ImportError:
                errors.append("既无 flock 命令也无 python3 fcntl：agent_loop 无法互斥，定时任务每轮都会拒绝执行")
        if not (shutil.which("timeout") or shutil.which("gtimeout")):
            warns.append("未找到 timeout / gtimeout：agent_loop 将用 python3 回退实现 tick 硬超时"
                         "（macOS 可 `brew install coreutils` 获得 gtimeout）")
    cfg = scheduler_config(root)
    eff = (os.environ.get("AIDP_AGENT") or agent).split(",", 1)[0]
    if eff == "auto":
        try:
            import agent_env
            eff = (agent_env.detect_agents(root) or ["claude"])[0]
        except Exception:  # noqa: BLE001 —— 判不出就不做按 Agent 的检查
            eff = ""
    if eff == "dsh" and not (os.environ.get("AIDP_AGENT_EXEC") or (cfg.get("exec") or {}).get("dsh")
                             or _env_file_has("AIDP_AGENT_EXEC")):
        errors.append("Agent=dsh 没有内置的非交互执行命令：请先在 memory/aidp-config.yaml 的 "
                      "scheduler.exec.dsh 配置（{prompt} 为占位符），否则每轮 agent_loop 都会 exit 2")
    if eff == "claude":
        gaps = _claude_allow_gaps(root)
        if gaps:
            warns.append(f"permissions.allow 尚不能确认覆盖 {'/'.join(gaps)}（含用户级与项目级配置）："
                         "请核验所需 Bash/Agent 与 MCP 细粒度规则及 deny；headless 未授权调用会被拒。"
                         "安装器只读检查，不改权限、不注入权限绕过参数")
    return errors, warns


def do_install(root, a):
    cfg = scheduler_config(root)
    agent = a.agent or cfg.get("agent") or "auto"
    intervals = resolve_intervals(root, a)
    plat = a.platform or detect_platform()
    res = {"action": "install", "platform": plat, "root": root, "agent": agent,
           "intervals": intervals, "dry_run": bool(a.dry_run), "files": {}, "commands": [], "notes": []}
    errs, warns = install_preflight(root, agent, plat)
    res["warnings"] = warns
    if errs:
        res["error"] = "；".join(errs)
        return 2, res
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
    res["notes"].append(runtime_text('非交互执行需 Agent 预授权工具权限，详见 __AIDP_HOME__/reference/agent-tools.md 第三节', __file__))
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


def lock_started_at(path):
    """持锁方写进锁文件的本轮起点（epoch 秒）；读不到返回 None。

    写方：`agent_loop.sh` 取得锁**之后**写 `{"owner":"agent_loop","started_at":…}`，
    直接 tick 的持久占位（`autopilot_tick_flags.py parse`）写同一格式。
    """
    try:
        with open(path, encoding="utf-8") as fh:
            raw = fh.read().strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        v = json.loads(raw)
        v = v.get("started_at") if isinstance(v, dict) else v
        return float(v)
    except (ValueError, TypeError):
        return None


def lock_hold_age(root, command, now=None):
    """锁被持有了多久（秒）。未被持有返回 None。

    ★ 判据优先取锁文件内容里的 `started_at`（持锁方取得锁后写入）；内容缺失时退回 mtime。
    ⛔ 不能只看 mtime：旧版 agent_loop 用 `9>"$lock"` 在 flock **之前**截断打开，
    每次「上一轮仍在运行，跳过」都会刷新 mtime → 持锁时长恒 ≈ 一个调度周期 → 挂死永不判出。
    """
    if not lock_held(root, command):
        return None
    p = os.path.join(root, "memory", ".aidp", "locks", f"loop-{command}.lock")
    started = lock_started_at(p)
    try:
        if started is None:
            started = os.path.getmtime(p)
        return max(0, int((time.time() if now is None else now.timestamp()) - started))
    except OSError:
        return None


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
        with open(p, "a+", encoding="utf-8") as fh:
            try:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            # 直接 tick 的持久占位跨工具调用保留，只有 finish 才清除。
            fh.seek(0)
            try:
                rec = json.loads(fh.read() or "{}")
                reserved = isinstance(rec, dict) and rec.get("owner") == "session"
            except ValueError:
                reserved = False
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            return reserved
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
        # 挂死阈值：一轮 tick 再慢也不该跑过这个数。取「stale 阈值」与 `tick_max_seconds`
        # 的较大者，且有 1h 下限 —— 单 Sprint 实测可达 1h 量级，压太低会把正常长 tick 误杀。
        hung_threshold = max(threshold, int(cfg.get("tick_max_seconds") or 0), 3600)
        raw = bl.get(meta["heartbeat"])
        dt = _parse_ts(raw)
        age = int((now - dt).total_seconds()) if dt else None
        out[chain] = {"command": meta["command"], "heartbeat_key": meta["heartbeat"],
                      "heartbeat_at": raw, "age_seconds": age, "threshold_seconds": threshold,
                      "state": "unknown" if dt is None else ("stale" if age > threshold else "fresh")}
        if lock_held(root, meta["command"]):
            # ⛔ 「持锁 = 正在跑」**不能无上限**：Agent 进程挂死（网络悬停 / 模型侧无响应 /
            #    等一个永不回来的工具结果）时锁被永久持有，后续每次调度都被
            #    `agent_loop.sh` 的 `flock -n` 判成「上一轮仍在运行，跳过」，而这里又判
            #    `running` —— 于是**永不 stale、永不告警、告警台账一行不写**。
            #    tick 内部的 stuck 熔断也救不了：那跑在 tick 里，而 tick 根本没开始。
            #    净效果 = 整条链路静默停摆、零信号、无恢复路径（G-AUTOPILOT-6 的非法形态）。
            hold = lock_hold_age(root, meta["command"], now=now)
            out[chain]["lock_hold_seconds"] = hold
            out[chain]["lock_hung_threshold_seconds"] = hung_threshold
            if hold is not None and hold > hung_threshold:
                out[chain]["state"] = "hung"    # 持锁超期 = 挂死，必须响
            else:
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
    now = now or datetime.now(timezone.utc)
    stale, alerted = [], []
    for chain, r in rep.items():
        missing_key = f"{chain}_missing_since"
        if r["state"] == "unknown" and not getattr(a, "scheduled", False):
            continue
        if r["state"] == "unknown":
            missing_since = _parse_ts(state.get(missing_key))
            if missing_since is None:
                missing_since = now
                state[missing_key] = now.isoformat()
            r["age_seconds"] = max(0, int((now - missing_since).total_seconds()))
            if r["age_seconds"] > r["threshold_seconds"]:
                r["state"] = "running" if lock_held(root, r["command"]) else "never-started"
            else:
                state.pop(chain, None)
        else:
            state.pop(missing_key, None)
        if r["state"] not in ("stale", "never-started", "hung"):
            if r["state"] == "fresh":
                state.pop(chain, None)
            continue
        stale.append(chain)
        marker = r["heartbeat_at"] if r["state"] == "stale" else r["state"]
        if state.get(chain) == marker:
            continue                      # 同一失联状态只告警一次
        state[chain] = marker
        label = CHAINS[chain]["label"]
        last = f"最后心跳 {r['heartbeat_at']}" if r["heartbeat_at"] else "从未收到心跳"
        if r["state"] == "hung":
            msg = (runtime_text(
                f"{label}（{r['command']}）本轮 tick 已持锁 {(r.get('lock_hold_seconds') or 0) // 60} 分钟"
                f"未结束（上限 {(r.get('lock_hung_threshold_seconds') or 0) // 60} 分钟，{last}）——"
                "疑似 Agent 进程挂死，后续每轮调度都会被互斥锁跳过、链路已静默停摆。"
                "处置：确认原 tick 已停止；OS tick 终止后会释放 flock，直接 tick 用其原 token 调 "
                "autopilot_tick_flags.py finish --command <链路> --lock-token <原token>。"
                "禁止删除锁文件（会形成两把不同 inode 的锁并放行并发）。"
                "再跑 python3 __AIDP_HOME__/scripts/aidp_scheduler.py status 复核", __file__))
        else:
            msg = (runtime_text(f"{label}（{r['command']}）已 {r['age_seconds'] // 60} 分钟无心跳"
                   f"（阈值 {r['threshold_seconds'] // 60} 分钟，{last}）。"
                   "请检查定时任务：python3 __AIDP_HOME__/scripts/aidp_scheduler.py status", __file__))
        rec = {"at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
               "source": "aidp_scheduler.watchdog", "kind": {
                   "never-started": "loop-heartbeat-never-started",
                   "hung": "loop-tick-hung"}.get(r["state"], "loop-heartbeat-stale"),
               "chain": chain, "command": r["command"], "heartbeat_at": r["heartbeat_at"],
               "age_seconds": r["age_seconds"], "threshold_seconds": r["threshold_seconds"],
               "message": msg}
        _append_alert(root, rec)
        sys.stderr.write(f"🚨 [AIDP-ALERT] {msg}\n")
        alerted.append(chain)
        if send_notify:
            notify = os.path.join(root, runtime_relpath("", __file__), "scripts", "notify.py")
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


def do_tick_result(root, a, send_notify=True):
    # 开发/测试由不同进程并发结束，计数共享一份文件，必须锁内重读并原子替换。
    from baseline_edit import LockedBaseline
    state_p = os.path.join(root, TICK_TIMEOUT_STATE_REL)
    with LockedBaseline(state_p, write=True) as locked:
        if not isinstance(locked.data, dict):
            raise ValueError("tick timeout 状态必须是 JSON 对象")
        return _tick_result(root, a, locked.data, send_notify=send_notify)


def _tick_result(root, a, state, send_notify=True):
    """agent_loop 每轮结束调用：超时（rc 124/137）→ 告警台账 + 连续计数，达阈发告警通知；否则清零。

    ⛔ 超时只写日志 + stderr 等于没告警：cron 丢弃 stderr，而被杀的 tick 往往连 run_state
    都没来得及写，下一轮原样重跑同一段 —— 每 tick_max 秒静默重来一遍、永不熔断。
    """
    cmd = a.command or ""
    rc = int(a.rc)
    cur = state.get(cmd) if isinstance(state.get(cmd), dict) else {}
    res = {"action": "tick-result", "command": cmd, "rc": rc, "timed_out": rc in TIMEOUT_RCS,
           "streak": 0, "alerted": False, "notified": False}
    if rc not in TIMEOUT_RCS:
        if cur.get("streak"):
            state.pop(cmd, None)
        return 0, res
    streak = int(cur.get("streak") or 0) + 1
    now_iso = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    state[cmd] = {"streak": streak, "last_at": now_iso, "last_rc": rc,
                  "first_at": cur.get("first_at") or now_iso}
    label = next((m["label"] for m in CHAINS.values() if m["command"] == cmd), cmd)
    msg = (f"{label}（{cmd}）本轮 tick 超过 {a.tick_max}s 上限被终止（rc={rc}，连续第 {streak} 次）"
           + (f"，日志 {a.log}" if a.log else "")
           + "。被杀的 tick 多半没写 run_state，下一轮会重跑同一段；"
           "请查日志定位卡点（大 Sprint / 挂死的工具调用 / 网络悬停）")
    _append_alert(root, {"at": now_iso, "source": "agent_loop", "kind": "loop-tick-timeout",
                         "command": cmd, "rc": rc, "tick_max_seconds": a.tick_max,
                         "streak": streak, "log": a.log or None, "message": msg})
    sys.stderr.write(f"🚨 [AIDP-ALERT] {msg}\n")
    res.update(streak=streak, alerted=True)
    n = max(1, TICK_TIMEOUT_ALERT_AFTER)
    if streak >= n and (streak - n) % n == 0:
        res["notified"] = True
        if send_notify:
            notify = os.path.join(root, runtime_relpath("", __file__), "scripts", "notify.py")
            if os.path.isfile(notify):
                try:
                    subprocess.run([sys.executable, notify, "--auto", "--alert", "--header-color", "red",
                                    "--title", f"{label} tick 连续 {streak} 次超时",
                                    "--section", msg, "--repo-root", root],
                                   capture_output=True, text=True, timeout=90, cwd=root)
                except (OSError, subprocess.SubprocessError):
                    pass          # 通知失败不阻断：告警台账已落
    return (3 if streak >= n else 0), res


def _write_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except OSError:
        pass


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
        for chain in (*CHAINS, "watchdog"):
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
        ok.append(("systemd 渲染 3 service + 3 timer", len(sd) == 6))
        ok.append(("systemd ExecStart 走 agent_loop --once 且带 --unattended",
                   all("agent_loop.sh --once" in v and "--unattended" in v
                       for k, v in sd.items() if k.endswith(".service") and "-watchdog." not in k)))
        ok.append(("systemd 独立 watchdog 定时唤醒", any("watchdog --scheduled" in v for v in sd.values())))
        ok.append(("systemd 周期正确", any("OnUnitInactiveSec=10min" in v for v in sd.values())
                   and any("OnUnitInactiveSec=5min" in v for v in sd.values())))
        cr = render_cron(d, "auto", iv)
        ok.append(("cron 三行带标记", len(cr) == 3 and all(CRON_MARK in ln for ln in cr)
                   and cr[0].startswith("*/10 ") and cr[1].startswith("*/5 ")
                   and "watchdog' '--scheduled'" in cr[2]))
        ld = render_launchd(d, "auto", iv)
        ok.append(("launchd 三条任务含 watchdog", len(ld) == 3 and any("<integer>300</integer>" in v
                   and "<string>--scheduled</string>" in v for v in ld.values())))
        ok.append(("schtasks 输出三条", len(render_schtasks(d, "auto", iv)) == 3))
        ok.append(("周期解析", parse_interval("10m") == 600 and parse_interval("30s") is None
                   and parse_interval("x") is None))
        os.makedirs(os.path.join(d, "memory"))
        old = "2000-01-01T00:00:00+00:00"
        with open(os.path.join(d, BASELINE_REL), "w", encoding="utf-8") as fh:
            json.dump({"aiauto_test_heartbeat_at": old}, fh)
        ns = argparse.Namespace(quiet=True, json=True, scheduled=True)
        rc, res = do_watchdog(d, ns, send_notify=False)
        ok.append(("watchdog：测试链路陈旧 → rc=3 + 告警台账", rc == 3 and res["stale"] == ["test"]
                   and os.path.isfile(os.path.join(d, ALERTS_REL))))
        ok.append(("watchdog：首次无心跳记录 → unknown 不告警", res["chains"]["dev"]["state"] == "unknown"))
        rc2, res2 = do_watchdog(d, ns, send_notify=False)
        ok.append(("watchdog：同一陈旧心跳不重复告警", rc2 == 3 and res2["alerted"] == []))
        with open(os.path.join(d, WATCHDOG_STATE_REL), encoding="utf-8") as fh:
            missing_since = _parse_ts(json.load(fh)["dev_missing_since"])
        overdue = missing_since.timestamp() + res["chains"]["dev"]["threshold_seconds"] + 1
        rc3, res3 = do_watchdog(d, ns, now=datetime.fromtimestamp(overdue, timezone.utc), send_notify=False)
        ok.append(("watchdog：无心跳超过宽限 → never-started 告警", rc3 == 3
                   and res3["chains"]["dev"]["state"] == "never-started"
                   and res3["alerted"] == ["dev"]))
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
        for w in res.get("warnings") or []:
            print("  ⚠️ " + w)
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
    ap.add_argument("action", nargs="?", choices=("install", "uninstall", "status", "watchdog", "tick-result"))
    ap.add_argument("--agent", choices=("auto", "claude", "codex", "dsh"), default=None)
    ap.add_argument("--dev-interval", dest="dev_interval", default=None)
    ap.add_argument("--test-interval", dest="test_interval", default=None)
    ap.add_argument("--platform", choices=PLATFORMS, default=None)
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--command", default=None, help="tick-result：链路命令名（如 sprint-autopilot）")
    ap.add_argument("--rc", type=int, default=None, help="tick-result：本轮 tick 退出码")
    ap.add_argument("--tick-max", dest="tick_max", default="", help="tick-result：本轮硬超时秒数（仅用于告警文案）")
    ap.add_argument("--log", default="", help="tick-result：本轮日志路径（仅用于告警文案）")
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
        elif a.action == "tick-result":
            if not a.command or a.rc is None:
                sys.stderr.write("⛔ tick-result 需要 --command 与 --rc\n")
                return 2
            rc, res = do_tick_result(root, a)
        else:
            rc, res = do_watchdog(root, a)
    except ValueError as e:
        sys.stderr.write(f"⛔ {e}\n")
        return 2
    _print(res, a.json, quiet=a.quiet)
    return rc


if __name__ == "__main__":
    sys.exit(main())
