#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aidp_scheduler.py + agent_loop.sh 单测（离线；不真装定时任务、不调用真实 Agent CLI）。

覆盖：
  · install --dry-run：systemd / cron / launchd / schtasks 渲染三条任务（链路周期、独立 watchdog、PATH、AIDP_AGENT）
  · install 在临时 HOME 下 dry-run 不落任何文件
  · 周期非法 → rc=2
  · watchdog：陈旧链路与超时从未启动链路写 alerts.jsonl + rc=3；去重、恢复清状态、启动宽限
  · agent_loop.sh --once：自动补 --unattended --no-loop、导出 AIDP_TICK_COMMAND / ARGUMENTS、写日志；
    执行失败透传 rc、锁竞争正常跳过；dsh 无执行模板 → rc=2；scheduler.exec.<agent> 生效

直接跑：`python3 .aidp/scripts/tests/test_aidp_scheduler.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
SCHED = os.path.join(SCRIPTS, "aidp_scheduler.py")
LOOP = os.path.join(SCRIPTS, "agent_loop.sh")

import aidp_scheduler as S  # noqa: E402

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _mkproj(config=""):
    d = tempfile.mkdtemp(prefix="aidp-sched-")
    subprocess.run(["git", "init", "-q", d], check=True)
    os.makedirs(os.path.join(d, ".aidp"))
    shutil.copytree(SCRIPTS, os.path.join(d, ".aidp", "scripts"),
                    ignore=shutil.ignore_patterns("tests", "__pycache__"))
    os.makedirs(os.path.join(d, "memory"))
    if config:
        with open(os.path.join(d, "memory", "aidp-config.yaml"), "w", encoding="utf-8") as fh:
            fh.write(config)
    return d


def _sched(args, root, home):
    env = dict(os.environ, HOME=home)
    return subprocess.run([sys.executable, SCHED] + args + ["--root", root],
                          capture_output=True, text=True, env=env)


def test_render():
    print("【install --dry-run 渲染】")
    root = _mkproj()
    home = tempfile.mkdtemp()
    try:
        r = _sched(["install", "--platform", "systemd", "--dry-run", "--json", "--agent", "codex"], root, home)
        res = json.loads(r.stdout)
        svc = {k: v for k, v in res["files"].items() if k.endswith(".service")}
        tmr = {k: v for k, v in res["files"].items() if k.endswith(".timer")}
        check("systemd：rc=0 且 3 service + 3 timer", r.returncode == 0 and len(svc) == 3 and len(tmr) == 3)
        check("systemd：ExecStart = agent_loop.sh --once <命令> --unattended",
              any("--once sprint-autopilot --unattended" in v for v in svc.values())
              and any("--once sprint-aiauto-test --unattended" in v for v in svc.values()))
        check("systemd：独立 watchdog 定时器在双链路未启动时也会唤醒",
              any("aidp_scheduler.py watchdog --scheduled" in v for v in svc.values())
              and any("OnUnitActiveSec=5min" in v and "OnBootSec=2min" in v for v in tmr.values()))
        check("systemd：链路服务注入 AIDP_AGENT 与 PATH",
              all('Environment="AIDP_AGENT=codex"' in v and 'Environment="PATH=' in v
                  for k, v in svc.items() if "-watchdog." not in k))
        check("systemd：默认周期 10min / 5min",
              any("OnUnitInactiveSec=10min" in v for v in tmr.values())
              and any("OnUnitInactiveSec=5min" in v for v in tmr.values()))
        check("systemd：文件落在 HOME/.config/systemd/user", all(k.startswith(home) for k in res["files"]))
        check("dry-run 不落文件", not os.path.exists(os.path.join(home, ".config")))

        r = _sched(["install", "--platform", "cron", "--dry-run", "--json",
                    "--dev-interval", "15m", "--test-interval", "2h"], root, home)
        lines = json.loads(r.stdout)["cron_lines"]
        check("cron：两条链路和独立 watchdog 均带标记", len(lines) == 3 and lines[0].startswith("*/15 ")
              and lines[1].startswith("0 */2 ") and all(S.CRON_MARK in ln for ln in lines)
              and "aidp_scheduler.py' 'watchdog' '--scheduled'" in lines[2])
        from unittest.mock import patch
        with patch.object(S, "_read_crontab", return_value=lines):
            _, status = S.do_status(root, type("A", (), {"platform": "cron"})())
        check("cron status 显示独立 watchdog 是否安装", status["installed"].get("cron:watchdog") is True)

        r = _sched(["install", "--platform", "launchd", "--dry-run", "--json"], root, home)
        files = json.loads(r.stdout)["files"]
        check("launchd：三份 plist，含独立 watchdog",
              len(files) == 3 and any("<integer>600</integer>" in v for v in files.values())
              and any("<integer>300</integer>" in v and "<string>--scheduled</string>" in v
                      for v in files.values()))

        r = _sched(["install", "--platform", "schtasks", "--dry-run", "--json"], root, home)
        cmds = json.loads(r.stdout)["commands"]
        check("schtasks：输出三条命令，含独立 watchdog", len(cmds) == 3
              and all(c.startswith("schtasks /Create") for c in cmds)
              and "aidp_scheduler.py watchdog --scheduled" in cmds[2])

        r = _sched(["install", "--platform", "cron", "--dry-run", "--dev-interval", "30s"], root, home)
        check("周期 < 1 分钟 → rc=2", r.returncode == 2)

        cfg_root = _mkproj("scheduler:\n  dev_interval: 20m\n  test_interval: 7m\n")
        r = _sched(["install", "--platform", "cron", "--dry-run", "--json"], cfg_root, home)
        lines = json.loads(r.stdout)["cron_lines"]
        check("scheduler 段周期生效", lines[0].startswith("*/20 ") and lines[1].startswith("*/7 "))
        shutil.rmtree(cfg_root, ignore_errors=True)

        r = _sched(["uninstall", "--platform", "systemd", "--dry-run", "--json"], root, home)
        res = json.loads(r.stdout)
        check("uninstall --dry-run：列出三条任务的文件与停用命令",
              r.returncode == 0 and len(res["removed"]) == 6
              and sum("disable" in c for c in res["commands"]) == 3)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_watchdog():
    print("【watchdog 心跳巡检】")
    root = _mkproj()
    try:
        now = datetime.now(timezone.utc)
        bl = {"autopilot_loop_heartbeat_at": (now - timedelta(minutes=5)).isoformat(),
              "aiauto_test_heartbeat_at": (now - timedelta(hours=3)).isoformat()}
        bp = os.path.join(root, S.BASELINE_REL)
        with open(bp, "w", encoding="utf-8") as fh:
            json.dump(bl, fh)
        ns = type("A", (), {"quiet": True, "json": True})()
        rc, res = S.do_watchdog(root, ns, send_notify=False)
        alerts = os.path.join(root, S.ALERTS_REL)
        check("测试链路 3h 无心跳 → rc=3 + stale=[test]", rc == 3 and res["stale"] == ["test"])
        check("开发链路 5 分钟前心跳 → fresh", res["chains"]["dev"]["state"] == "fresh")
        recs = [json.loads(x) for x in open(alerts, encoding="utf-8").read().splitlines()]
        check("告警台账追加一条 loop-heartbeat-stale", len(recs) == 1
              and recs[0]["kind"] == "loop-heartbeat-stale" and recs[0]["chain"] == "test")
        rc, res = S.do_watchdog(root, ns, send_notify=False)
        check("同一陈旧心跳不重复告警", rc == 3 and res["alerted"] == []
              and len(open(alerts, encoding="utf-8").read().splitlines()) == 1)
        bl["aiauto_test_heartbeat_at"] = now.isoformat()
        with open(bp, "w", encoding="utf-8") as fh:
            json.dump(bl, fh)
        rc, res = S.do_watchdog(root, ns, send_notify=False)
        check("心跳恢复 → rc=0", rc == 0 and res["stale"] == [])
        bl["aiauto_test_heartbeat_at"] = (now - timedelta(hours=5)).isoformat()
        with open(bp, "w", encoding="utf-8") as fh:
            json.dump(bl, fh)
        rc, res = S.do_watchdog(root, ns, send_notify=False)
        check("恢复后再次陈旧 → 重新告警", rc == 3 and res["alerted"] == ["test"])
        import fcntl
        lockd = os.path.join(root, "memory", ".aidp", "locks")
        os.makedirs(lockd, exist_ok=True)
        with open(os.path.join(lockd, "loop-sprint-aiauto-test.lock"), "w") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            rc, res = S.do_watchdog(root, ns, send_notify=False)
            check("陈旧但本轮仍持锁执行（长 tick）→ running、不判失联",
                  rc == 0 and res["chains"]["test"]["state"] == "running")
        os.remove(bp)
        rc, res = S.do_watchdog(root, ns, send_notify=False)
        check("baseline 缺失 → 两链路 unknown、rc=0",
              rc == 0 and all(c["state"] == "unknown" for c in res["chains"].values()))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_watchdog_never_started():
    print("【watchdog 从未启动的链路】")
    root = _mkproj()
    ns = type("A", (), {"quiet": True, "json": True, "scheduled": True})()
    try:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        rc, res = S.do_watchdog(root, ns, now=start, send_notify=False)
        check("首次无心跳观察 → unknown、无告警", rc == 0 and res["alerted"] == []
              and all(r["state"] == "unknown" for r in res["chains"].values()))
        threshold = res["chains"]["test"]["threshold_seconds"]
        rc, res = S.do_watchdog(root, ns, now=start + timedelta(seconds=threshold), send_notify=False)
        check("未超过宽限阈值 → unknown、无告警", rc == 0 and res["alerted"] == [])
        rc, res = S.do_watchdog(root, ns, now=start + timedelta(seconds=threshold + 1), send_notify=False)
        check("测试链路宽限超时且从未有心跳 → rc=3、告警", rc == 3
              and res["stale"] == ["test"] and res["alerted"] == ["test"]
              and res["chains"]["test"]["state"] == "never-started")
        alerts = os.path.join(root, S.ALERTS_REL)
        recs = [json.loads(x) for x in open(alerts, encoding="utf-8").read().splitlines()] if os.path.isfile(alerts) else []
        check("从未启动告警记录并区分于陈旧心跳", len(recs) == 1
              and recs[0]["chain"] == "test" and recs[0]["kind"] == "loop-heartbeat-never-started")
        rc, res = S.do_watchdog(root, ns, now=start + timedelta(seconds=threshold + 2), send_notify=False)
        check("同一从未启动链路只告警一次", rc == 3 and res["alerted"] == []
              and len(open(alerts, encoding="utf-8").read().splitlines()) == 1)
        import fcntl
        lockd = os.path.join(root, "memory", ".aidp", "locks")
        os.makedirs(lockd, exist_ok=True)
        with open(os.path.join(lockd, "loop-sprint-aiauto-test.lock"), "w") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            rc, res = S.do_watchdog(root, ns, now=start + timedelta(seconds=threshold + 3), send_notify=False)
            check("从未有心跳但正在运行 → running、不判失联", rc == 0
                  and res["chains"]["test"]["state"] == "running"
                  and res["stale"] == [])
        bp = os.path.join(root, S.BASELINE_REL)
        with open(bp, "w", encoding="utf-8") as fh:
            json.dump({"aiauto_test_heartbeat_at": (start + timedelta(seconds=threshold + 4)).isoformat()}, fh)
        rc, res = S.do_watchdog(root, ns, now=start + timedelta(seconds=threshold + 4), send_notify=False)
        check("首次心跳恢复后清除从未启动告警状态", rc == 0
              and res["chains"]["test"]["state"] == "fresh")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_watchdog_manual_without_install():
    print("【手动模式无安装不误报】")
    root = _mkproj()
    ns = type("A", (), {"quiet": True, "json": True, "scheduled": False})()
    try:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        S.do_watchdog(root, ns, now=start, send_notify=False)
        rc, res = S.do_watchdog(root, ns, now=start + timedelta(days=1), send_notify=False)
        check("手动模式无心跳逾期不触发 never-started 告警", rc == 0
              and res["stale"] == [] and res["alerted"] == []
              and all(r["state"] == "unknown" for r in res["chains"].values())
              and not os.path.isfile(os.path.join(root, S.ALERTS_REL)))
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _loop(root, args, env_extra):
    env = dict(os.environ, **env_extra)
    env.pop("AIDP_TICK_COMMAND", None)
    return subprocess.run(["bash", os.path.join(root, ".aidp", "scripts", "agent_loop.sh")] + args,
                          capture_output=True, text=True, cwd=root, env=env, timeout=120)


def test_agent_loop():
    print("【agent_loop.sh --once】")
    home = tempfile.mkdtemp()
    root = _mkproj()
    try:
        out = os.path.join(root, "captured.txt")
        tpl = ("printf '%s\\n' {prompt} > " + out +
               " && echo \"TICK=$AIDP_TICK_COMMAND\" >> " + out +
               " && echo \"ARGS=$ARGUMENTS\" >> " + out)
        r = _loop(root, ["--once", "sprint-autopilot", "--unattended"],
                  {"HOME": home, "AIDP_AGENT": "claude", "AIDP_AGENT_EXEC": tpl})
        text = open(out, encoding="utf-8").read() if os.path.isfile(out) else ""
        check("--once rc=0", r.returncode == 0)
        check("claude 提示词 = /<命令> + 自动补 --no-loop、不重复 --unattended",
              text.splitlines()[0:1] == ["/sprint-autopilot --unattended --no-loop"])
        check("导出 AIDP_TICK_COMMAND", "TICK=sprint-autopilot" in text)
        check("导出 ARGUMENTS", "ARGS=--unattended --no-loop" in text)
        check("日志落 memory/.aidp/logs/<命令>.log",
              os.path.isfile(os.path.join(root, "memory", ".aidp", "logs", "sprint-autopilot.log")))

        os.remove(out)
        r = _loop(root, ["--once", "sprint-aiauto-test"],
                  {"HOME": home, "AIDP_AGENT": "codex", "AIDP_AGENT_EXEC": tpl})
        text = open(out, encoding="utf-8").read() if os.path.isfile(out) else ""
        check("codex 提示词 = $<命令> + 自动补无人值守参数",
              text.splitlines()[0:1] == ["$sprint-aiauto-test --unattended --no-loop"])
        check("codex 提示词不含 aidp-cmd", "aidp-cmd" not in text.splitlines()[0])

        r = _loop(root, ["--once", "sprint-autopilot"], {"HOME": home, "AIDP_AGENT": "dsh", "AIDP_AGENT_EXEC": ""})
        check("dsh 无执行模板 → rc=2 并提示配置", r.returncode == 2 and "scheduler.exec.dsh" in r.stderr)

        with open(os.path.join(root, "memory", "aidp-config.yaml"), "w", encoding="utf-8") as fh:
            fh.write("scheduler:\n  agent: dsh\n  exec: {dsh: \"printf '%s' {prompt} > " + out + "\"}\n")
        os.path.isfile(out) and os.remove(out)
        env = {"HOME": home, "AIDP_AGENT_EXEC": ""}
        r = _loop(root, ["--once", "sprint-autopilot"], dict(env, AIDP_AGENT=""))
        text = open(out, encoding="utf-8").read() if os.path.isfile(out) else ""
        check("scheduler.agent + scheduler.exec.<agent> 使用 DSH 原生命令",
              r.returncode == 0 and text.startswith("/sprint-autopilot --unattended --no-loop"))
        check("dsh 提示词不含 aidp-cmd", "aidp-cmd" not in text.splitlines()[0])

        r = _loop(root, ["--once", "sprint-autopilot"],
                  {"HOME": home, "AIDP_AGENT": "claude", "AIDP_AGENT_EXEC": "sh -c 'exit 17'"})
        log = os.path.join(root, "memory", ".aidp", "logs", "sprint-autopilot.log")
        check("执行失败 → --once 返回原始 rc=17", r.returncode == 17)
        check("执行失败日志记录原始 rc", "结束 rc=17" in open(log, encoding="utf-8").read())

        import fcntl
        lock = os.path.join(root, "memory", ".aidp", "locks", "loop-sprint-autopilot.lock")
        with open(lock, "w") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            r = _loop(root, ["--once", "sprint-autopilot"],
                      {"HOME": home, "AIDP_AGENT": "claude", "AIDP_AGENT_EXEC": "sh -c 'exit 17'"})
            check("锁竞争跳过 → --once 正常退出", r.returncode == 0)

        r = subprocess.run(["bash", "-n", LOOP], capture_output=True, text=True)
        check("bash -n 语法检查通过", r.returncode == 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_self_check():
    print("【--self-check】")
    r = subprocess.run([sys.executable, SCHED, "--self-check"], capture_output=True, text=True)
    check("aidp_scheduler.py --self-check 通过", r.returncode == 0)


def test_scheduler_docs():
    print("【独立 watchdog 安装说明】")
    repo = os.path.dirname(os.path.dirname(SCRIPTS))
    paths = ("README.md", "memory/aidp-config.yaml", ".aidp/commands/sprint-autopilot.md",
             ".aidp/commands/sprint-aiauto-test.md", ".aidp/flows/sprint-autopilot/usage-guard.md",
             ".aidp/skills/aidp-code-engineer/sources/root/README.md.tpl", ".aidp/scripts/README.md")
    for relative in paths:
        with open(os.path.join(repo, relative), encoding="utf-8") as fh:
            text = fh.read()
        check(f"{relative} 说明第三条独立 watchdog 调度任务",
              "独立 watchdog" in text or "独立心跳巡检" in text)
    scripts_readme = open(os.path.join(repo, ".aidp/scripts/README.md"), encoding="utf-8").read()
    check("agent_sync README 不再宣称默认生成符号链接",
          "入口默认是相对符号链接" not in scripts_readme and "managed-copy" in scripts_readme)


if __name__ == "__main__":
    test_render()
    test_watchdog()
    test_watchdog_never_started()
    test_watchdog_manual_without_install()
    test_agent_loop()
    test_self_check()
    test_scheduler_docs()
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)
