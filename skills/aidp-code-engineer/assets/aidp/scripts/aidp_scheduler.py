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
               [--authorization-text "<用户原话>" [--authorization-request-id ID]]
    uninstall  [--platform P] [--dry-run] [--json]
    status     [--platform P] [--json]
    watchdog   [--quiet] [--json]          # 心跳巡检：定时唤醒时无心跳从首次巡检起计时，超时告警
    tick-result --command C --rc N [--tick-max S] [--log P] [--log-offset N]  # 所有失败归因、计数与告警
    tick-check  --command C [--token T] [--tick-args "<参数串>"] [--json]
                                           # 持链路锁后的唯一准入判据：退避 / 测试委派 / 授权来源 / 预算耗尽；
                                           # rc=4 跳过，rc=5 无授权来源（已告警）；不能调用 tick-result
    --self-check

平台（`--platform` 缺省自动判定）：
  systemd   Linux 且 `systemctl --user` 可用 → `~/.config/systemd/user/aidp-<项目>-{dev,test,watchdog}.{service,timer}`
  cron      Linux 无 systemd 用户实例 → 用户 crontab 中带 `# AIDP-SCHEDULER <项目>` 标记的三行
  launchd   macOS → `~/Library/LaunchAgents/com.aidp.<项目>.{dev,test,watchdog}.plist`
  schtasks  Windows → 只输出 `schtasks` 命令（需在 Git Bash / WSL 等可运行 bash 的环境下执行），不自动执行

配置：`memory/aidp-config.yaml` 的 `scheduler` 段（`dev_interval` / `test_interval` / `agent` / `stale_cycles` / `exec`），
安装命令行参数优先。成功装配后将周期保存到 `memory/.aidp/scheduler-installation.json`；
watchdog / status 优先使用此快照，配置周期热改须重装才生效，无安装态（含手工 loop）时使用配置。
status 的 installation 返回上次成功装配快照，config 返回当前配置。失败重装保留旧快照，
不承诺回滚已执行的系统命令；dry-run 和 schtasks 仅输出命令，不写安装态。
心跳：开发链路 `autopilot_loop_heartbeat_at`、测试链路 `aiauto_test_heartbeat_at`（baseline 顶层）。

## 无头 tick 的授权来源（绝不伪造）

调度唤起的 autopilot tick 没有“本轮用户消息”。授权来源只有两种真实出处：用户在 `install --authorization-text`
给出的持续执行原话（落盘 `memory/.aidp/scheduler-authorization.json`，卸载即撤销），或用户在
`memory/aidp-config.yaml` 明确选择的 `execution_policy.authorization_source`（project-policy）。
tick-check 仅在“已有根不带持续来源”时据前者生成 `explicit-command` 来源（request_id=本轮令牌、persistent=true、
options=被调度命令原始参数），由 agent_loop 以 `AUTHORIZATION_SOURCE_JSON` 交给执行 LLM；两者都没有则
写 `loop-no-authorization` 告警（UNVERIFIED，去重）并停止本轮，而不是让执行 LLM 自编来源。模板默认/配置存在不是授权。

## 其他确定性处置（均在 tick-check）

  · 测试链路：待测版本无可信委派 → 刷新测试心跳 + 告警（按 version+build 去重，连续 3 轮）+ 标 `manifest-missing@V`，
    开发链路据此以 reason=manifest-missing 收尾，不再误称“测试链路未挂载”。
  · 开发链路：根预算耗尽（budget.json 旁的 exhausted.json 事实且限额未续）→ 以 reason=budget-exhausted 冻结；
    续额只能 `autopilot_unfreeze.py --renew-budget`（user-text 真实来源 + 新绝对上限），`--manual` 不重置预算。

## 退出码

  0 = 成功（watchdog：无陈旧链路）
  2 = 用法错 / 平台不支持 / 装配命令执行失败
  3 = watchdog 检出故障链路 / tick-result 连续失败达阈（本地告警可见）
  4 = tick-check 本轮跳过（退避 / 待测版本无可信委派；未执行，不记成功或失败）
  5 = tick-check 无授权来源（已写 loop-no-authorization 告警，本轮不执行）
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
import shlex
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
INSTALLATION_STATE_REL = os.path.join("memory", ".aidp", "scheduler-installation.json")
# 沿用旧路径兼容升级；现记录所有非零退出，只有成功执行才清零。
TICK_TIMEOUT_STATE_REL = os.path.join("memory", ".aidp", "tick-timeouts.json")
# 连续失败达阈后，原因 + rc 分键通知一次，直到成功恢复。兼容旧环境变量名。
try:
    TICK_TIMEOUT_ALERT_AFTER = max(1, int(os.environ.get("AIDP_TICK_TIMEOUT_ALERT_AFTER", "3") or 3))
except ValueError:
    TICK_TIMEOUT_ALERT_AFTER = 3
# 用户在 install 时明确给出的持续执行指令（无头 tick 的授权来源，缺失即停并告警，绝不伪造）。
AUTHORIZATION_STATE_REL = os.path.join("memory", ".aidp", "scheduler-authorization.json")
# 调度侧诊断去重状态（委派缺口 / 无授权告警），与失败退避状态分文件。
GAP_STATE_REL = os.path.join("memory", ".aidp", "scheduler-gaps.json")
DELEGATION_GAP_ALERT_AFTER = 3     # 待测版本连续多少轮无可信委派才升级为告警 + 阻塞标记
AUTH_ALERT_EVERY_SECONDS = 6 * 3600
TIMEOUT_RCS = (124, 137)
CRON_MARK = "# AIDP-SCHEDULER"
GRACE_SECONDS = 300
TICK_FINISH_GRACE_SECONDS = 180
MAX_BACKOFF_ROUNDS = 32


def env_file_values():
    """读取可选 KEY=VALUE / export KEY=VALUE 文件；只解引号，不展开或执行 shell。

    文件值覆盖进程环境，保持 agent_loop 历史优先级。非法行忽略，值永不输出诊断。
    """
    values = {}
    path = os.path.join(os.path.expanduser("~"), ".config", "aidp", "env")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return values
    for line in lines:
        match = re.fullmatch(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)", line.rstrip("\r\n"))
        if not match:
            continue
        key, raw = match.groups()
        try:
            # comments=False 保留 webhook URL 中的 #；尾随空白注释单独处理。
            parts = shlex.split(raw, comments=False, posix=True)
        except ValueError:
            continue
        if not parts:
            value = ""
        elif len(parts) == 1 or (len(parts) > 1 and parts[1].startswith("#")):
            value = parts[0]
        else:
            continue
        if "\x00" not in value:
            values[key] = value
    return values


def scheduler_env():
    return dict(os.environ, **env_file_values())


def effective_tick_max(root, env=None):
    """wrapper 与独立巡检共享：env 文件 > 进程环境 > 项目配置 > 7200。"""
    env = scheduler_env() if env is None else env
    raw = env.get("AIDP_TICK_MAX_SECONDS") or scheduler_config(root).get("tick_max_seconds", 7200)
    text = str(raw)
    return int(text) if re.fullmatch(r"[0-9]+", text) else 7200


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
        return {"dev_interval": "10m", "test_interval": "5m", "agent": "auto", "stale_cycles": 3,
                "tick_max_seconds": 7200, "exec": {}}


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
    auth_text = (getattr(a, "authorization_text", None) or "").strip()
    if auth_text:
        from execution_policy import _text
        if not _text(auth_text):
            res["error"] = "--authorization-text 必须是用户真实的持续执行指令原文，不接受模板/占位值"
            return 2, res
    elif not authorization_available(root, "sprint-autopilot"):
        res["warnings"].append(
            "未记录用户持续执行指令：无头 autopilot tick 没有可追溯的授权来源，每轮将以 UNVERIFIED 写告警并停止"
            "（kind=loop-no-authorization）。请在用户明确要求持续运行后用 `install --authorization-text \"<用户原话>\"` 重装；"
            "模板默认或配置存在不构成授权。")
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
        if auth_text and not a.dry_run:
            res["authorization"] = record_authorization(root, auth_text, getattr(a, "authorization_request_id", None))
        return 0, res
    else:
        res["error"] = f"不支持的平台：{plat}"
        return 2, res
    res["notes"].append(runtime_text('非交互执行需 Agent 预授权工具权限，详见 __AIDP_HOME__/reference/agent-tools.md 第三节', __file__))
    if a.dry_run:
        return 0, res
    from baseline_edit import LockedBaseline
    # 装配与记录共用一把锁，避免并发重装把较早的周期覆盖到较晚的任务上。
    # 只有全部成功才写回；dry-run / schtasks 仅输出命令均不会进入此处。
    with LockedBaseline(os.path.join(root, INSTALLATION_STATE_REL), write=True) as locked:
        locked.write = False
        os.makedirs(os.path.join(root, "memory", ".aidp", "logs"), exist_ok=True)
        if plat == "cron":
            slug = project_slug(root)
            keep = [ln for ln in _read_crontab() if f"{CRON_MARK} {slug} " not in ln]
            rc, err = _write_crontab(keep + res["cron_lines"])
            if rc != 0:
                res["error"] = f"crontab 写入失败：{err.strip()[:200]}"
                return 2, res
        else:
            for p, body in res["files"].items():
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(body)
            for argv in res["commands"]:
                rc, out = _run(argv)
                if rc != 0:
                    res["error"] = f"{' '.join(argv)} 失败（rc={rc}）：{out.strip()[:200]}"
                    return 2, res
        locked.data = {"platform": plat, "intervals": intervals,
                       "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        locked.write = True
    if auth_text:
        res["authorization"] = record_authorization(root, auth_text, getattr(a, "authorization_request_id", None))
    return 0, res


def record_authorization(root, text, request_id=None):
    """落盘用户在 install 时明确给出的持续执行指令；之后每个 autopilot tick 据此生成确定性授权来源。"""
    import uuid
    rec = {"kind": "explicit-command", "persistent": True, "text": text.strip(),
           "install_request_id": (request_id or "").strip() or "scheduler-install-" + uuid.uuid4().hex,
           "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _write_json(os.path.join(root, AUTHORIZATION_STATE_REL), rec)
    return {k: rec[k] for k in ("install_request_id", "recorded_at")}


def load_authorization(root):
    """读 install 时记录的持续指令；缺失或字段不合法返回 None（不补默认、不从配置推断）。"""
    from execution_policy import _text
    try:
        with open(os.path.join(root, AUTHORIZATION_STATE_REL), encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError):
        return None
    if (not isinstance(rec, dict) or rec.get("persistent") is not True or not _text(rec.get("text"))
            or not _text(rec.get("install_request_id"))):
        return None
    return rec


def _root_has_persistent_source(root, command):
    """与 entry_context._pipeline_source(persistent=True) 同判据：已有根上是否带可持续的命令来源。

    返回 True/False；上下文不可读返回 None（由调用方按需处理，不当作有来源）。
    """
    from aidp_paths import baseline
    try:
        state = json.loads(_AidpPath(baseline(root)).read_text(encoding="utf-8"))
        path = (state.get("autopilot") or {}).get("execution_context")
        if not isinstance(path, str) or not path:
            return False
        from entry_context import load_context
        ctx = load_context(root, path)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    for src in ctx.get("authorization_source") or []:
        if not isinstance(src, dict) or str(src.get("command", "")).lstrip("/") != command:
            continue
        if src.get("kind") == "project-policy" or (src.get("kind") == "explicit-command"
                                                    and src.get("persistent") is True):
            return True
    return False


def _chosen_project_policy(root, command):
    """用户在配置里明确选择的持续执行策略（execution_policy.authorization_source，须指向本命令）。"""
    try:
        from aidp_config import read_execution_policy
        policy = read_execution_policy(root)
    except (OSError, ValueError, ImportError):
        return False
    source = (policy or {}).get("authorization_source") or {}
    return str(source.get("command", "")).lstrip("/") == command


def authorization_available(root, command):
    return load_authorization(root) is not None or _chosen_project_policy(root, command)


def tick_authorization(root, command, token, args_text):
    """无头 autopilot tick 的授权来源 -> (status, source|None, info)。

    not-needed：已有根带持续来源或用户已选 project-policy；supplied：用 install 时记录的用户指令确定性生成；
    missing：需要来源却没有用户指令（调用方必须告警并停止，不能让执行 LLM 自编来源）。
    """
    if command != "sprint-autopilot":
        return "not-needed", None, {}
    has = _root_has_persistent_source(root, command)
    if has or _chosen_project_policy(root, command):
        return "not-needed", None, {}
    rec = load_authorization(root)
    if rec is None:
        return "missing", None, {"detail": "既无已有根的持续来源，也无 install 时记录的用户持续指令"}
    try:
        options = shlex.split(args_text or "")
    except ValueError:
        options = (args_text or "").split()
    source = {"kind": "explicit-command", "request_id": token, "command": "/" + command,
              "persistent": True, "text": rec["text"], "options": [o for o in options if o.startswith("--")],
              "install_request_id": rec["install_request_id"]}
    return "supplied", source, {}


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
    from baseline_edit import LockedBaseline
    with LockedBaseline(os.path.join(root, INSTALLATION_STATE_REL), write=True) as locked:
        locked.write = False
        if plat == "cron":
            keep = [ln for ln in _read_crontab() if f"{CRON_MARK} {slug} " not in ln]
            rc, err = _write_crontab(keep)
            if rc != 0:
                res["error"] = f"crontab 写入失败：{err.strip()[:200]}"
                return 2, res
        else:
            timers_first = [c for c in res["commands"] if "daemon-reload" not in c]
            for argv in timers_first:
                rc, out = _run(argv)
                # 未装过时仍幂等；有任务文件却停用失败，不能清除其安装周期。
                if rc != 0 and any(os.path.isfile(p) for p in res["removed"]):
                    res["error"] = f"{' '.join(argv)} 失败（rc={rc}）：{out.strip()[:200]}"
                    return 2, res
            for p in res["removed"]:
                try:
                    os.remove(p)
                except FileNotFoundError:
                    pass
            for argv in res["commands"]:
                if "daemon-reload" in argv:
                    rc, out = _run(argv)
                    if rc != 0:
                        res["error"] = f"{' '.join(argv)} 失败（rc={rc}）：{out.strip()[:200]}"
                        return 2, res
        if locked.data.get("platform") == plat:
            # 空记录表示无已知安装；保留锁 inode，不能删锁文件制造第二把锁。
            locked.data = {}
            locked.write = True
    try:
        os.remove(os.path.join(root, AUTHORIZATION_STATE_REL))   # 卸载即撤销 install 时的持续指令
    except FileNotFoundError:
        pass
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


def installed_schedule(root):
    """上次成功装配的周期快照；只读原子替换后的完整文件，不把配置热改当成已重装。"""
    try:
        with open(os.path.join(root, INSTALLATION_STATE_REL), encoding="utf-8") as fh:
            state = json.load(fh)
    except FileNotFoundError:
        return {}
    if not isinstance(state, dict):
        raise ValueError("scheduler 安装态必须是 JSON 对象")
    if not state:
        return {}
    intervals = state.get("intervals")
    if state.get("platform") not in PLATFORMS or not isinstance(intervals, dict) or any(
            type(intervals.get(c)) is not int or intervals[c] < 60 for c in CHAINS):
        raise ValueError("scheduler 安装态周期无效，请重新 install")
    return state


def heartbeat_report(root, now=None, intervals=None):
    cfg = scheduler_config(root)
    installed = installed_schedule(root).get("intervals", {})
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
        secs = (intervals or {}).get(chain) or installed.get(chain) \
            or parse_interval(cfg.get(meta["interval_key"])) \
            or parse_interval({"dev": "10m", "test": "5m"}[chain])
        threshold = int(cfg.get("stale_cycles") or 3) * secs + GRACE_SECONDS
        # 允许硬超时后的 TERM/KILL 与记账通知收尾；环境覆盖与 wrapper 使用同一解析器。
        hung_threshold = max(threshold, effective_tick_max(root) + TICK_FINISH_GRACE_SECONDS, 3600)
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


def _notify_alert(root, rec, title):
    """状态锁释放后通知；失败留本地台账，不输出子进程中的凭据。"""
    notify = os.path.join(root, runtime_relpath("scripts/notify.py", __file__))
    try:
        result = subprocess.run([sys.executable, notify, "--auto", "--alert", "--header-color", "red",
                                 "--title", title, "--section", rec["message"], "--repo-root", root],
                                capture_output=True, text=True, timeout=90, cwd=root, env=scheduler_env())
        status = "sent" if result.returncode == 0 else f"exit-{result.returncode}"
    except (OSError, subprocess.SubprocessError):
        status = "unavailable"
    if status != "sent":
        failure = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                   "source": "aidp_scheduler", "kind": "loop-notify-failed", "command": rec["command"],
                   "alert_kind": rec["kind"], "status": status,
                   "message": f"通知未送达（{status}），原始告警保留在本地台账"}
        _append_alert(root, failure)
        sys.stderr.write(f"[AIDP-ALERT] {failure['message']}\n")
    return status


def do_watchdog(root, a, now=None, send_notify=True):
    from baseline_edit import LockedBaseline
    notifications = []
    with LockedBaseline(os.path.join(root, WATCHDOG_STATE_REL), write=True) as locked:
        if not isinstance(locked.data, dict):
            raise ValueError("watchdog 状态必须是 JSON 对象")
        rc, res = _watchdog(root, a, locked.data, notifications, now=now)
    res["notifications"] = [_notify_alert(root, rec, title) for rec, title in notifications] if send_notify else []
    return rc, res


def _watchdog(root, a, state, notifications, now=None):
    # 状态读取、心跳判断、去重标记与原子写回全部处于同一把锁内。
    rep = heartbeat_report(root, now=now)
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
        ledger = _append_alert(root, rec)
        sys.stderr.write(f"[AIDP-ALERT] {msg}\n")
        if ledger:
            state[chain] = marker
            alerted.append(chain)
        else:
            sys.stderr.write("[AIDP-ALERT] 告警台账写入失败，下次巡检重试\n")
        notifications.append((rec, f"{label}心跳中断"))
    return (3 if stale else 0), {"action": "watchdog", "chains": rep, "stale": stale, "alerted": alerted}


def tick_failure_kind(root, a):
    """只读本轮日志尾 16KiB 作归因；不把可能含凭据的原文写入通知或台账。"""
    rc = int(a.rc)
    if rc in TIMEOUT_RCS:
        return "loop-tick-timeout"
    text = ""
    if a.log:
        path = a.log if os.path.isabs(a.log) else os.path.join(root, a.log)
        try:
            with open(path, "rb") as fh:
                fh.seek(0, os.SEEK_END)
                fh.seek(max(0, fh.tell() - 16384, int(getattr(a, "log_offset", 0) or 0)))
                text = fh.read(16384).decode("utf-8", errors="replace").lower()
        except OSError:
            pass
    if re.search(r"insufficient[_ -]quota|quota.{0,40}(?:exceed|exhaust)|credit balance.{0,30}(?:low|insufficient)|"
                 r"(?:usage|spending|billing) limit|out of credits|额度不足|余额不足|配额.{0,12}(?:耗尽|超限)", text):
        return "loop-agent-quota"
    if re.search(r"\b429\b|rate[_ -]?limit|too many requests|请求过于频繁", text):
        return "loop-agent-rate-limit"
    if re.search(r"\b(?:401|403)\b|unauthori[sz]ed|authentication.{0,20}(?:fail|error)|invalid[_ -](?:api[_ -])?key|"
                 r"(?:token|credentials?).{0,20}(?:expir|invalid)|not logged in|鉴权失败|认证失败", text):
        return "loop-agent-auth"
    if rc == 127 or re.search(r"command not found|(?:cli|executable).{0,30}not found", text):
        return "loop-agent-cli-missing"
    return "loop-agent-failed"


def test_handoff_context(root, execution_context=None):
    """独立进程只继承明确测试交接；命令名、activeContext、历史 build 不构成委派。"""
    from entry_context import load_context
    from execution_policy import validate_test_binding
    from aidp_paths import baseline
    state = json.loads(_AidpPath(baseline(root)).read_text(encoding="utf-8"))
    handoff = state.get("aiauto") or {}
    path = execution_context or handoff.get("execution_context")
    if not isinstance(path, str) or not path:
        raise ValueError("缺可追溯测试委派 aiauto.execution_context")
    context = load_context(root, path)
    validate_test_binding(root, context, context["version"], context.get("build_id"))
    node = (state.get("versions") or {}).get(context["version"]) or {}
    if node.get("current_build") != context.get("build_id"):
        raise ValueError("测试委派不是当前版本当前 build，拒绝历史 build")
    if node.get("internal_released_at"):
        raise ValueError("测试委派所属版本已内部发布，不能重放旧交接")
    row = next((item for item in node.get("builds", []) if item.get("build") == context["build_id"]), {})
    if row.get("ai_report_finalized"):
        raise ValueError("测试委派 build 已定稿，不能重放旧交接")
    return path, context


def _pending_test_nodes(root):
    """已部署、未内部发布、且当前 build 仍需测试的版本 -> [(version, build)]。

    “需测试”= 当前 build 未定稿，且尚无晚于最近部署的测试完成时刻。已测完未发布的窗口
    （aiauto_tested_at ≥ last_deployed_at 或 build 已 finalized）不再算待测目标，
    否则会被当成“有待测却无委派”而无故跳过、停刷心跳。
    """
    from aidp_paths import baseline
    try:
        state = json.loads(_AidpPath(baseline(root)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(state, dict):
        return []
    out = []
    for version, node in sorted((state.get("versions") or {}).items()):
        if not (isinstance(node, dict) and node.get("phase_beta_done_at") and not node.get("internal_released_at")):
            continue
        build = node.get("current_build") or ""
        row = next((b for b in node.get("builds") or [] if isinstance(b, dict) and b.get("build") == build), {})
        if row.get("ai_report_finalized"):
            continue
        tested, deployed = _parse_ts(node.get("aiauto_tested_at")), _parse_ts(node.get("last_deployed_at"))
        if tested and (not deployed or tested >= deployed):
            continue
        out.append((version, build))
    return out


def _test_target_state(root):
    """返回 target（有待测版本且根允许测试）/ skipped（有待测版本但根已显式跳过测试）/ none。

    与命令入口同一判据：已部署（phase_beta_done_at）且尚未内部发布、当前 build 仍需测试的版本才算待测版本。
    根已失去 live-tests/full-regression 时是用户明确不要测试，应报 NOT_REQUESTED，
    不能说成“无目标”，也不能当作“应有委派却缺失”而报警。
    """
    from aidp_paths import baseline
    if not _pending_test_nodes(root):
        return "none"
    try:
        state = json.loads(_AidpPath(baseline(root)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "none"
    root_path = (state.get("autopilot") or {}).get("execution_context")
    if isinstance(root_path, str) and root_path:
        try:
            from entry_context import load_context
            allowed = set(load_context(root, root_path).get("allowed_actions", ()))
            if not {"live-tests", "full-regression"} & allowed:
                return "skipped"
        except (OSError, ValueError, KeyError, TypeError):
            pass  # 根不可读时保守按有目标处理，由委派校验拒绝
    return "target"


def _has_pending_test_target(root):
    return _test_target_state(root) == "target"


def _gap_update(root, mutate):
    """锁内读改写调度诊断状态；返回 mutate 的结果。状态不可写时退化为不去重，不阻断 tick。"""
    from baseline_edit import LockedBaseline
    try:
        with LockedBaseline(os.path.join(root, GAP_STATE_REL), write=True) as locked:
            if not isinstance(locked.data, dict):
                locked.data = {}
            return mutate(locked.data)
    except (OSError, SystemExit):
        return mutate({})


def _refresh_heartbeat(root, chain):
    """链路确实存活但本轮被确定性拦下：刷新该链路心跳，让 watchdog 看到的是具体告警而非“无心跳”。"""
    from baseline_edit import LockedBaseline
    try:
        with LockedBaseline(os.path.join(root, BASELINE_REL), write=True) as locked:
            if isinstance(locked.data, dict):
                locked.data[CHAINS[chain]["heartbeat"]] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    except (OSError, SystemExit):
        pass


def _set_blocked_marker(root, value, only_if=None):
    """写/清顶层 aiauto_blocked_reason；清除只在当前值恰为本模块所写的标记时发生。"""
    from baseline_edit import LockedBaseline
    try:
        with LockedBaseline(os.path.join(root, BASELINE_REL), write=True) as locked:
            if not isinstance(locked.data, dict):
                return
            cur = str(locked.data.get("aiauto_blocked_reason") or "")
            if value is None:
                if cur.startswith("manifest-missing@") and (only_if is None or cur == only_if):
                    locked.data.pop("aiauto_blocked_reason", None)
            elif not cur:
                locked.data["aiauto_blocked_reason"] = value
    except (OSError, SystemExit):
        pass


def _note_delegation_gap(root, exc):
    """待测版本无可信委派：刷新测试链路心跳；连续达阈按 version+build 去重写一次告警并标记阻塞原因。"""
    nodes = _pending_test_nodes(root)
    version, build = nodes[0] if nodes else ("", "")
    key = f"{version}|{build}"
    reason = "待测版本无可信委派/清单缺失"
    _refresh_heartbeat(root, "test")

    def mutate(data):
        gap = data.get("delegation") if isinstance(data.get("delegation"), dict) else {}
        if gap.get("key") != key:
            gap = {"key": key, "streak": 0, "alerted": False}
        gap["streak"] += 1
        due = gap["streak"] >= DELEGATION_GAP_ALERT_AFTER and not gap["alerted"]
        if due:
            gap["alerted"] = True
        data["delegation"] = gap
        return gap["streak"], due

    streak, due = _gap_update(root, mutate)
    out = {"gap_streak": streak, "gap_reason": reason, "version": version, "build": build, "alerted": False}
    if due:
        msg = (f"{reason}：{version}（{build}）已部署待测，但没有可核验的测试委派（{exc}）；测试链路保持存活但不会执行测试。"
               "请检查开发链路是否已产出并交接测试清单（manifest），补齐前测试不会启动")
        out["alerted"] = bool(_append_alert(root, {
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "source": "agent_loop",
            "kind": "test-delegation-unverified", "command": "sprint-aiauto-test", "version": version,
            "build": build, "streak": streak, "message": msg}))
        sys.stderr.write(f"[AIDP-ALERT] {msg}\n")
        _set_blocked_marker(root, f"manifest-missing@{version}")
    return out


def _clear_delegation_gap(root):
    """委派恢复（或不再有待测目标）：清去重状态与本模块写的阻塞标记。"""
    if not os.path.exists(os.path.join(root, GAP_STATE_REL)):
        return   # 健康 tick 不制造状态文件
    def mutate(data):
        gap = data.pop("delegation", None)
        return gap if isinstance(gap, dict) else None
    gap = _gap_update(root, mutate)
    if gap and gap.get("alerted") and gap.get("key"):
        _set_blocked_marker(root, None, only_if=f"manifest-missing@{gap['key'].split('|', 1)[0]}")


def _run_script(root, name, *argv):
    """以项目根为 cwd 调同目录脚本（失败处置等），返回退出码；超时/缺失按失败 2。"""
    try:
        return subprocess.run([sys.executable, os.path.join(HERE, name), *argv], cwd=root,
                              capture_output=True, text=True, timeout=120).returncode
    except (OSError, subprocess.SubprocessError):
        return 2


def _freeze_exhausted_budgets(root):
    """根任务预算耗尽且未续额：按 budget-exhausted 冻结该版（幂等；不清零任何预算）。返回已冻结版本。"""
    from aidp_paths import baseline
    try:
        state = json.loads(_AidpPath(baseline(root)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(state, dict):
        return []
    roots = {}
    for version, node in (state.get("versions") or {}).items():
        if isinstance(node, dict) and not node.get("needs_human") and node.get("autopilot_root_context"):
            roots[version] = node["autopilot_root_context"]
    frozen = []
    try:
        from execution_policy import budget_exhaustion
    except ImportError:
        return []
    for version, path in sorted(roots.items()):
        status, items = budget_exhaustion(root, path)
        if status != "exhausted":
            continue
        need = ",".join(f"{row['resource']}>={row['required']}" for row in items)
        rc = _run_script(root, "autopilot_fail_handle.py", "--version", version, "--phase", "budget-exhausted",
                         "--reason", "budget-exhausted", "--freeze-now", "--extra", f"budget_exhausted_need={need}",
                         "--why", f"根任务执行预算已耗尽（{need}），子任务不得自行扩预算；需用户明确续额")
        if rc in (0, 3):
            frozen.append(version)
    return frozen


def do_tick_check(root, a):
    """一次调度唤醒消费一个退避轮；调用方应先取得链路锁。跳过不写 tick-result。

    也是 wrapper 的唯一准入判据：测试链路的委派核验、autopilot 的授权来源与预算耗尽处置都在此一处完成，
    结果经 JSON 的 execution_context / authorization_source 交给 agent_loop，不再各处重算而漂移。
    """
    from baseline_edit import LockedBaseline
    context_path = None
    extra = {}
    if a.command == "sprint-aiauto-test":
        try:
            context_path, _ = test_handoff_context(root, getattr(a, "execution_context", None))
            _clear_delegation_gap(root)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # 没有已部署待测版本时无需委派：放行让命令入口自己输出 NO_TARGET 并保持心跳，
            # 否则空转 tick 被吞，watchdog 会把正常空闲误判成链路失联。
            if not _has_pending_test_target(root):
                context_path = None
                _clear_delegation_gap(root)
            else:
                return 4, {"action": "tick-check", "command": a.command, "skip": True,
                           "reason": "test-delegation-unverified", "error": str(exc),
                           **_note_delegation_gap(root, exc)}
    elif a.command == "sprint-autopilot":
        extra["budget_frozen"] = _freeze_exhausted_budgets(root)
        token = getattr(a, "token", None) or __import__("uuid").uuid4().hex
        status, source, info = tick_authorization(root, a.command, token, getattr(a, "tick_args", "") or "")
        extra["authorization"] = status
        if status == "missing":
            _refresh_heartbeat(root, "dev")
            first = _auth_alert_due(root)
            msg = ("UNVERIFIED：无头 autopilot tick 没有可追溯的用户授权来源——" + info["detail"]
                   + "；已停止本轮（不由执行 LLM 自编来源）。用户明确要求持续运行后请 "
                   "`aidp_scheduler.py install --authorization-text \"<用户原话>\"` 重装，"
                   "或在 memory/aidp-config.yaml 记录用户选择的 execution_policy.authorization_source。")
            if first:
                _append_alert(root, {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "source": "agent_loop", "kind": "loop-no-authorization",
                                     "command": a.command, "message": msg})
                sys.stderr.write(f"[AIDP-ALERT] {msg}\n")
            return 5, dict(extra, action="tick-check", command=a.command, skip=True,
                           reason="authorization-unverified", error=msg, alerted=first)
        extra["authorization_source"] = json.dumps(source, ensure_ascii=False) if source else None
    with LockedBaseline(os.path.join(root, TICK_TIMEOUT_STATE_REL), write=True) as locked:
        if not isinstance(locked.data, dict):
            raise ValueError("tick 状态必须是 JSON 对象")
        cur = locked.data.get(a.command) or {}
        remaining = max(0, int(cur.get("skip_remaining") or 0))
        if remaining:
            cur["skip_remaining"] = remaining - 1
        return (4 if remaining else 0), dict({"action": "tick-check", "command": a.command,
                                        "skip": bool(remaining), "skip_remaining": max(0, remaining - 1),
                                        "streak": int(cur.get("streak") or 0), "reason": "backoff" if remaining else "ok",
                                        "execution_context": context_path}, **extra)


def _auth_alert_due(root):
    """无授权告警按时间去重：每 AUTH_ALERT_EVERY_SECONDS 秒最多一条，恢复（有来源）后下次缺失立即再响。"""
    now = time.time()

    def mutate(data):
        last = data.get("authorization_alerted_at")
        if isinstance(last, (int, float)) and now - last < AUTH_ALERT_EVERY_SECONDS:
            return False
        data["authorization_alerted_at"] = now
        return True
    return _gap_update(root, mutate)


def do_tick_result(root, a, send_notify=True):
    # 开发/测试并发结束时锁内重读原子替换；网络通知不持状态锁。
    from baseline_edit import LockedBaseline
    notifications = []
    with LockedBaseline(os.path.join(root, TICK_TIMEOUT_STATE_REL), write=True) as locked:
        if not isinstance(locked.data, dict):
            raise ValueError("tick 状态必须是 JSON 对象")
        rc, res = _tick_result(root, a, locked.data, notifications)
    if send_notify and notifications:
        rec, title = notifications[0]
        res["notification_status"] = _notify_alert(root, rec, title)
    return rc, res


def _tick_result(root, a, state, notifications):
    """所有非零退出累计，原因+rc 在本次连续故障期内各通知一次；成功清除整个状态。"""
    cmd, rc = a.command, int(a.rc)
    cur = state.get(cmd) if isinstance(state.get(cmd), dict) else {}
    res = {"action": "tick-result", "command": cmd, "rc": rc, "timed_out": rc in TIMEOUT_RCS,
           "streak": 0, "skip_remaining": 0, "alerted": False, "notified": False}
    if rc == 0:
        state.pop(cmd, None)
        return 0, res
    streak = int(cur.get("streak") or 0) + 1
    kind = tick_failure_kind(root, a)
    key = f"{kind}:{rc}"
    failures = cur.get("failures") or {}
    failure = failures.setdefault(key, {"count": 0, "alerted": False})
    failure["count"] += 1
    n = max(1, TICK_TIMEOUT_ALERT_AFTER)
    skip = min(MAX_BACKOFF_ROUNDS, 2 ** min(5, streak - n)) if streak >= n else 0
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state[cmd] = {"streak": streak, "last_at": now_iso, "last_rc": rc,
                  "first_at": cur.get("first_at") or now_iso, "kind": kind, "failure_key": key,
                  "failures": failures, "skip_remaining": skip}
    label = next((m["label"] for m in CHAINS.values() if m["command"] == cmd), cmd)
    reason = {"loop-tick-timeout": f"tick 超过 {a.tick_max}s 上限被终止",
              "loop-agent-quota": "Agent 额度或余额不足", "loop-agent-rate-limit": "Agent 请求被限流",
              "loop-agent-auth": "Agent 鉴权失败", "loop-agent-cli-missing": "Agent CLI 不存在",
              "loop-agent-failed": "Agent 执行失败"}[kind]
    msg = (f"{label}（{cmd}）{reason}（rc={rc}，连续第 {streak} 次，本原因/退出码第 {failure['count']} 次）"
           + (f"，日志 {a.log}" if a.log else "") + f"；后续跳过 {skip} 轮再试")
    due = streak >= n and not failure["alerted"]
    rec = {"at": now_iso, "source": "agent_loop", "kind": kind, "command": cmd, "rc": rc,
           "tick_max_seconds": a.tick_max, "streak": streak, "failure_key": key,
           "failure_count": failure["count"], "notification_due": due,
           "skip_remaining": skip, "log": a.log or None, "message": msg}
    ledger = _append_alert(root, rec)
    sys.stderr.write(f"[AIDP-ALERT] {msg}\n")
    if due:
        # 只有落下可见台账才能消费通知去重标记；通知失败由独立记录呈现。
        failure["alerted"] = bool(ledger)
        notifications.append((rec, f"{label} tick 连续 {streak} 次失败"))
    res.update(streak=streak, kind=kind, failure_key=key, skip_remaining=skip,
               alerted=bool(ledger), notified=due)
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
               "installation": installed_schedule(root), "heartbeats": heartbeat_report(root)}


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
    ap.add_argument("action", nargs="?", choices=("install", "uninstall", "status", "watchdog", "tick-result", "tick-check"))
    ap.add_argument("--agent", choices=("auto", "claude", "codex", "dsh"), default=None)
    ap.add_argument("--dev-interval", dest="dev_interval", default=None)
    ap.add_argument("--test-interval", dest="test_interval", default=None)
    ap.add_argument("--platform", choices=PLATFORMS, default=None)
    ap.add_argument("--root", default=".")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--command", default=None, help="tick-result：链路命令名（如 sprint-autopilot）")
    ap.add_argument("--execution-context", help="测试 tick 明确继承的 autopilot 子任务；默认只读 aiauto.execution_context")
    ap.add_argument("--token", default=None, help="tick-check：本轮 tick 令牌（作为授权来源的 request_id）")
    ap.add_argument("--tick-args", dest="tick_args", default="", help="tick-check：被调度命令的原始参数串（写入来源 options）")
    ap.add_argument("--authorization-text", dest="authorization_text", default=None,
                    help="install：用户明确要求持续运行的原话，记录为无头 tick 的授权来源")
    ap.add_argument("--authorization-request-id", dest="authorization_request_id", default=None,
                    help="install：该用户请求的标识（缺省自动生成）")
    ap.add_argument("--rc", type=int, default=None, help="tick-result：本轮 tick 退出码")
    ap.add_argument("--tick-max", dest="tick_max", default="", help="tick-result：本轮硬超时秒数（仅用于告警文案）")
    ap.add_argument("--log", default="", help="tick-result：本轮日志路径（读取尾部作失败归因）")
    ap.add_argument("--log-offset", type=int, default=0, help="tick-result：本轮日志起始字节，排除旧轮次错误")
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
        elif a.action in ("tick-result", "tick-check"):
            if not a.command or (a.action == "tick-result" and a.rc is None):
                sys.stderr.write("tick-result 需要 --command 与 --rc；tick-check 需要 --command\n")
                return 2
            rc, res = do_tick_result(root, a) if a.action == "tick-result" else do_tick_check(root, a)
        else:
            rc, res = do_watchdog(root, a)
    except ValueError as e:
        sys.stderr.write(f"[aidp_scheduler] {e}\n")
        return 2
    except OSError as e:
        sys.stderr.write(f"[aidp_scheduler] 操作失败（{type(e).__name__}）\n")
        return 2
    _print(res, a.json, quiet=a.quiet)
    return rc


if __name__ == "__main__":
    sys.exit(main())
