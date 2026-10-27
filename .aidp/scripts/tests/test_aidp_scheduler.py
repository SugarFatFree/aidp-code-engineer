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
  · agent_loop 硬超时：超时写 alerts.jsonl + 连续计数（tick-result）；跳过不截断锁文件、取锁后写起点；
    后台常驻进程不继承锁 fd；无 flock / timeout 时退回 python3（macOS 形态）
  · watchdog 持锁时长优先读锁内容 started_at；install 预检（dsh 未配 exec → rc=2，claude 权限缺口 WARN）
  · autopilot_tick_flags：LOOP_EVIDENCE 按 tick 间隔自适应；tick 级互斥（并发 → rc=4 + 告警，agent_loop 内不自锁）
  · baseline_edit epoch：跨平台 ISO8601 → epoch

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
        # ★★ 持锁超期 = 挂死，必须响。⛔ 「持锁即 running」不能无上限：Agent 进程挂死时
        #    锁被永久持有 → 后续每轮调度被 `flock -n` 跳过 → watchdog 永远判 running
        #    → 永不 stale、永不告警、台账一行不写 = 整条链路静默停摆（G-AUTOPILOT-6 非法形态）。
        lock_path = os.path.join(lockd, "loop-sprint-aiauto-test.lock")
        with open(lock_path, "w") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            os.utime(lock_path, (0, 0))          # mtime 拉到远古 = 持锁已远超上限
            before = len(open(alerts, encoding="utf-8").read().splitlines()) \
                if os.path.isfile(alerts) else 0
            rc, res = S.do_watchdog(root, ns, send_notify=False)
            chain = res["chains"]["test"]
            after = open(alerts, encoding="utf-8").read().splitlines()
            check("★★持锁超期（挂死）→ state=hung、rc=3、进 stale 名单",
                  chain["state"] == "hung" and rc == 3 and res["stale"] == ["test"])
            check("★★挂死必落告警台账 kind=loop-tick-hung（没有通知渠道也要停得响）",
                  len(after) == before + 1
                  and json.loads(after[-1])["kind"] == "loop-tick-hung")
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


def _alerts(root):
    p = os.path.join(root, S.ALERTS_REL)
    return [json.loads(x) for x in open(p, encoding="utf-8").read().splitlines()] if os.path.isfile(p) else []


def _lock_free(path):
    import fcntl
    with open(path, "a") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return False
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return True


def test_agent_loop_timeout_and_lock():
    print("【agent_loop 超时记账 / 锁文件口径 / fd 9 不外泄】")
    home = tempfile.mkdtemp()
    root = _mkproj()
    try:
        env = {"HOME": home, "AIDP_AGENT": "claude", "AIDP_AGENT_EXEC": "sleep 5", "AIDP_TICK_MAX_SECONDS": "1"}
        r = _loop(root, ["--once", "sprint-autopilot"], env)
        recs = [x for x in _alerts(root) if x.get("kind") == "loop-tick-timeout"]
        check("超时 → rc=124", r.returncode == 124)
        check("★超时必落告警台账 kind=loop-tick-timeout（cron 丢 stderr 也要停得响）",
              len(recs) == 1 and recs[0]["command"] == "sprint-autopilot" and recs[0]["streak"] == 1)
        _loop(root, ["--once", "sprint-autopilot"], env)
        _loop(root, ["--once", "sprint-autopilot"], env)
        st = json.load(open(os.path.join(root, S.TICK_TIMEOUT_STATE_REL), encoding="utf-8"))
        check("连续超时计数累加到 3", st.get("sprint-autopilot", {}).get("streak") == 3)
        r = _loop(root, ["--once", "sprint-autopilot"], dict(env, AIDP_AGENT_EXEC="true"))
        st = json.load(open(os.path.join(root, S.TICK_TIMEOUT_STATE_REL), encoding="utf-8"))
        check("非超时轮清零连续计数", r.returncode == 0 and "sprint-autopilot" not in st)

        lock = os.path.join(root, "memory", ".aidp", "locks", "loop-sprint-autopilot.lock")
        body = json.load(open(lock, encoding="utf-8"))
        check("取得锁后写入本轮起点 started_at", body.get("owner") == "agent_loop"
              and abs(body.get("started_at", 0) - __import__("time").time()) < 120)
        import fcntl
        with open(lock, "a") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            with open(lock, "w") as fh:
                fh.write('{"owner":"agent_loop","started_at":123}\n')
            r = _loop(root, ["--once", "sprint-autopilot"], dict(env, AIDP_AGENT_EXEC="true"))
            check("★「跳过」不截断锁文件（起点不被刷新）", r.returncode == 0
                  and json.load(open(lock, encoding="utf-8")).get("started_at") == 123)

        r = _loop(root, ["--once", "sprint-autopilot"],
                  dict(env, AIDP_TICK_MAX_SECONDS="60",
                       AIDP_AGENT_EXEC="sleep 30 >/dev/null 2>&1 & printf '%s' $! > bg.pid"))
        check("★后台常驻进程不继承 fd 9：tick 结束即释放锁", r.returncode == 0 and _lock_free(lock))
        with open(os.path.join(root, "bg.pid")) as fh:
            bg_pid = int(fh.read())
        try:
            os.kill(bg_pid, 15)   # 仅清理本用例明确创建的进程，禁止按进程名扫杀。
        except ProcessLookupError:
            pass

        # macOS 形态：PATH 里没有 flock / timeout → python3 回退
        fake = tempfile.mkdtemp()
        for tool in ("bash", "sh", "python3", "dirname", "basename", "sed", "mkdir", "date", "sleep", "true", "cat", "git"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, os.path.join(fake, tool))
        envm = dict(env, PATH=fake)
        r = _loop(root, ["--once", "sprint-autopilot"], envm)
        log = open(os.path.join(root, "memory", ".aidp", "logs", "sprint-autopilot.log"), encoding="utf-8").read()
        check("无 flock/timeout：python3 回退仍硬超时（rc=124）", r.returncode == 124 and "上限，已终止" in log)
        with open(lock, "a") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            r = _loop(root, ["--once", "sprint-autopilot"], dict(envm, AIDP_AGENT_EXEC="exit 9"))
            check("★无 flock：锁竞争仍判「跳过」而非把 127 当被占", r.returncode == 0
                  and "上一轮仍在运行，跳过" in open(os.path.join(root, "memory", ".aidp", "logs",
                                                         "sprint-autopilot.log"), encoding="utf-8").read())
        r = _loop(root, ["--once", "sprint-autopilot"], dict(envm, AIDP_AGENT_EXEC="exit 9"))
        check("无 flock：取得锁后照常执行并透传 rc", r.returncode == 9)
        shutil.rmtree(fake, ignore_errors=True)
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_tick_result_and_lock_age():
    print("【tick-result 连续超时 / 持锁时长取锁内容】")
    root = _mkproj()
    try:
        A = lambda rc: type("A", (), {"command": "sprint-aiauto-test", "rc": rc, "tick_max": "60", "log": ""})()
        rcs = [S.do_tick_result(root, A(124), send_notify=False) for _ in range(3)]
        check("前两次超时 rc=0、第 3 次达阈 rc=3 且 notified", [x[0] for x in rcs] == [0, 0, 3]
              and rcs[2][1]["notified"] and not rcs[1][1]["notified"])
        check("每次超时都写告警台账", len([x for x in _alerts(root) if x["kind"] == "loop-tick-timeout"]) == 3)
        rc, res = S.do_tick_result(root, A(0), send_notify=False)
        check("成功轮清零", rc == 0 and res["streak"] == 0
              and S.do_tick_result(root, A(137), send_notify=False)[1]["streak"] == 1)

        import fcntl
        import time as _t
        lockd = os.path.join(root, "memory", ".aidp", "locks")
        os.makedirs(lockd, exist_ok=True)
        lp = os.path.join(lockd, "loop-sprint-aiauto-test.lock")
        with open(lp, "w") as lk:
            lk.write(json.dumps({"owner": "agent_loop", "started_at": int(_t.time()) - 99999}) + "\n")
            lk.flush()
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            os.utime(lp, None)                   # mtime 刷到「刚才」—— 旧口径会判持锁很短
            age = S.lock_hold_age(root, "sprint-aiauto-test")
            check("★持锁时长优先取锁内容 started_at（不被 mtime 刷新骗过）", age is not None and age >= 99990)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_install_preflight():
    print("【install 预检】")
    root = _mkproj()
    home = tempfile.mkdtemp()
    try:
        r = _sched(["install", "--platform", "cron", "--dry-run", "--json", "--agent", "dsh"], root, home)
        res = json.loads(r.stdout or "{}")
        check("★dsh 未配 exec → install rc=2（不装注定失败的任务）", r.returncode == 2
              and "scheduler.exec.dsh" in (res.get("error") or ""))
        r = _sched(["install", "--platform", "cron", "--dry-run", "--json", "--agent", "claude"], root, home)
        res = json.loads(r.stdout or "{}")
        check("claude 未放行 Bash/Agent → WARN 但照装", r.returncode == 0
              and any("Bash/Agent" in w for w in res.get("warnings") or []))
        os.makedirs(os.path.join(root, ".claude"))
        with open(os.path.join(root, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
            json.dump({"permissions": {"allow": ["Bash", "Agent"]}}, fh)
        r = _sched(["install", "--platform", "cron", "--dry-run", "--json", "--agent", "claude"], root, home)
        res = json.loads(r.stdout or "{}")
        check("permissions.allow 覆盖后不再 WARN", r.returncode == 0
              and not any("permissions.allow" in w for w in res.get("warnings") or []))
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_tick_flags_loop_evidence_and_mutex():
    print("【tick_flags：LOOP_EVIDENCE 自适应 / tick 级互斥】")
    import autopilot_tick_flags as TF
    now = 100000.0
    check("固定 40 分钟内两次 → 成立", TF.loop_evidence([now - 1200, now - 600], now, 2400))
    check("★1h 长 tick 节奏（间隔 70 分钟）在 tick_max=7200 下成立",
          TF.loop_evidence([now - 8400, now - 4200], now, 7200))
    check("同节奏在旧固定 2400s 口径下不成立（回归对照）",
          not TF.loop_evidence([now - 8400, now - 4200], now, 2400))
    check("只有 1 次历史 → 不成立（手工连跑两遍不升级）", not TF.loop_evidence([now - 60], now, 7200))
    check("链中有一段超限 → 不成立", not TF.loop_evidence([now - 20000, now - 600], now, 7200))

    root = _mkproj()
    try:
        with open(os.path.join(root, S.BASELINE_REL), "w", encoding="utf-8") as fh:
            json.dump({}, fh)
        script = os.path.join(root, ".aidp", "scripts", "autopilot_tick_flags.py")
        lock = os.path.join(root, "memory", ".aidp", "locks", "loop-sprint-autopilot.lock")
        env = dict(os.environ)
        env.pop("AIDP_TICK_COMMAND", None)

        def parse(extra_env=None, token=""):
            args = [sys.executable, script, "parse", "--command", "autopilot", "--arguments=--unattended"]
            if token:
                args += ["--lock-token", token]
            return subprocess.run(args, cwd=root, capture_output=True, text=True,
                                  env=dict(env, **(extra_env or {})), timeout=60)

        def finish(token):
            return subprocess.run([sys.executable, script, "finish", "--command", "autopilot",
                                   "--lock-token", token], cwd=root, capture_output=True, text=True)

        r = parse()
        body = json.load(open(lock, encoding="utf-8"))
        token = body.get("token", "")
        check("会话 tick 在 parse 退出后保留持久占位", r.returncode == 0 and body.get("owner") == "session"
              and token and S.lock_held(root, "sprint-autopilot"))
        check("另一 parse 不得猜测同会话而接管", parse().returncode == 4)
        check("本轮显式沿用 token 才允许重新解析", parse(token=token).returncode == 0)
        check("错误 token 不释放别人占位", finish("wrong").returncode == 1
              and S.lock_held(root, "sprint-autopilot"))
        check("本轮 finish 释放占位", finish(token).returncode == 0 and not S.lock_held(root, "sprint-autopilot"))
        import fcntl
        with open(lock, "a") as lk:
            fcntl.flock(lk.fileno(), fcntl.LOCK_EX)
            with open(lock, "w") as fh:
                fh.write('{"owner":"agent_loop","token":"wrapper-token","started_at":1}\n')
            r = parse()
            check("★另一 tick（OS 调度）持锁 → rc=4 退本 tick", r.returncode == 4)
            check("★并发冲突落告警台账 kind=tick-concurrent",
                  any(x.get("kind") == "tick-concurrent" for x in _alerts(root)))
            check("仅设置命令环境变量不构成复用锁证据",
                  parse({"AIDP_TICK_COMMAND": "sprint-autopilot"}).returncode == 4)
            r = parse({"AIDP_TICK_COMMAND": "sprint-autopilot", "AIDP_TICK_TOKEN": "wrapper-token"})
            check("★agent_loop 拉起的 tick 不自锁（整轮 shell 仍持有锁）", r.returncode == 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_session_reservation_lifecycle():
    print("【直接 tick 持久占位生命周期】")
    root, home = _mkproj(), tempfile.mkdtemp()
    try:
        lock = os.path.join(root, "memory", ".aidp", "locks", "loop-sprint-autopilot.lock")
        os.makedirs(os.path.dirname(lock), exist_ok=True)
        with open(lock, "w") as fh:
            json.dump({"owner": "session", "token": "live-tick", "started_at": 1}, fh)
        # 模拟跨工具调用：没有短命 Python 持有 flock，但占位仍必须挡住 OS tick。
        r = _loop(root, ["--once", "sprint-autopilot"],
                  {"HOME": home, "AIDP_AGENT": "claude", "AIDP_AGENT_EXEC": "touch ran"})
        check("直接 tick 占位持续挡住 OS tick", r.returncode == 0
              and not os.path.exists(os.path.join(root, "ran")))
        with open(lock, "w") as fh:
            json.dump({"owner": "session", "token": "live-tick", "started_at": 1}, fh)
        ns = type("A", (), {"scheduled": True})()
        rc, res = S.do_watchdog(root, ns, send_notify=False)
        check("没有首次心跳的陈旧占位也判 hung", rc == 3 and res["chains"]["dev"]["state"] == "hung")
    finally:
        shutil.rmtree(root, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)


def test_fallback_lock_lifetime():
    print("【无 flock 时的真实并发互斥】")
    root, home, fake = _mkproj(), tempfile.mkdtemp(), tempfile.mkdtemp()
    proc = None
    try:
        for tool in ("bash", "sh", "python3", "dirname", "basename", "sed", "mkdir", "date", "sleep", "git"):
            src = shutil.which(tool)
            if src:
                os.symlink(src, os.path.join(fake, tool))
        env = dict(os.environ, HOME=home, PATH=fake, AIDP_AGENT="claude",
                   AIDP_AGENT_EXEC="touch started; sleep 3", AIDP_TICK_MAX_SECONDS="10")
        # touch 用 bash 内建替代，避免依赖裁剪后的 PATH。
        env["AIDP_AGENT_EXEC"] = "printf started > started; sleep 3"
        proc = subprocess.Popen(["bash", os.path.join(root, ".aidp", "scripts", "agent_loop.sh"),
                                 "--once", "sprint-autopilot"], cwd=root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        import time
        deadline = time.monotonic() + 10
        while not os.path.isfile(os.path.join(root, "started")) and time.monotonic() < deadline:
            time.sleep(0.05)
        lock = os.path.join(root, "memory", ".aidp", "locks", "loop-sprint-autopilot.lock")
        check("fallback 加锁子进程退出后，执行中的 shell 仍持锁", os.path.exists(lock) and not _lock_free(lock))
        second = _loop(root, ["--once", "sprint-autopilot"], dict(env, AIDP_AGENT_EXEC="exit 19"))
        check("fallback 第二个真实 tick 被跳过", second.returncode == 0)
        proc.communicate(timeout=15)
        check("fallback 整轮结束即释放锁", proc.returncode == 0 and _lock_free(lock))
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            proc.communicate(timeout=15)
        for p in (root, home, fake):
            shutil.rmtree(p, ignore_errors=True)


def test_cicd_retry_priority_and_poll():
    print("【PRD 重试上限真实消费】")
    from pathlib import Path
    import autopilot_tick_flags as TF
    root = _mkproj("cicd:\n  max_retries: 8\n")
    old_cwd = os.getcwd()
    try:
        os.chdir(root)
        prd = Path("docs/requirements/V1.0.0/产品提供/PRD.md")
        prd.parent.mkdir(parents=True)
        prd.write_text("autopilot_decisions:\n  deployment:\n    cicd_max_retries: 0\n", encoding="utf-8")
        check("PRD 的 0 次重试覆盖配置 8", TF._cicd_max_retries({"TARGET_VERSION": "V1.0.0"}) == "0")
        data = {"autopilot": {"target_version": "V1.0.0"}, "versions": {"V1.0.0": {
            "current_build": "V1.0.0_build1001", "builds": [{"build": "V1.0.0_build1001", "push_commit": "abc"}],
            "cicd_run": {"run_id": "123", "pipeline": "deploy"}}}}
        Path(S.BASELINE_REL).write_text(json.dumps(data), encoding="utf-8")
        # 用替身拦截 CICD 平台边界；真实执行 flow、tick flags 与 baseline 读取。
        Path(".aidp/scripts/cicd_watch.py").write_text(
            'import sys,json\nn=sys.argv[sys.argv.index("--max-retries")+1] if "--max-retries" in sys.argv else "missing"\n'
            'print(json.dumps({"verdict":"failed","received_max_retries":n}))\nsys.exit(2)\n', encoding="utf-8")
        flow = Path(SCRIPTS).parent / "flows/sprint-autopilot/phase-3-6b.md"
        code = flow.read_text(encoding="utf-8").split("```bash\n", 1)[1].split("```", 1)[0]
        result = subprocess.run(["bash", "-c", code.replace("{{AIDP_HOME}}", ".aidp")],
                                capture_output=True, text=True, timeout=30)
        rec = json.loads(Path("memory/.aidp/cicd-poll.json").read_text())
        check("实际 poll 调用收到 PRD max-retries=0", rec.get("received_max_retries") == "0")
        prd.write_text("autopilot_decisions:\n  deployment:\n    cicd_max_retries: invalid\n", encoding="utf-8")
        check("非法 PRD 值回落项目配置", TF._cicd_max_retries({"TARGET_VERSION": "V1.0.0"}) == "8")
        Path("memory/aidp-config.yaml").unlink()
        # aidp_config 按路径缓存，清缓存后验证缺省。
        import aidp_config
        if hasattr(aidp_config, "load") and hasattr(aidp_config.load, "cache_clear"):
            aidp_config.load.cache_clear()
        # 默认路径用独立进程，避免测试配置缓存掩盖真实结果。
        r = subprocess.run([sys.executable, ".aidp/scripts/autopilot_tick_flags.py", "--command", "autopilot", "--shell"],
                           capture_output=True, text=True, timeout=30)
        check("项目配置缺失回落默认3", "CICD_MAX_RETRIES=3" in r.stdout)
    finally:
        os.chdir(old_cwd)
        shutil.rmtree(root, ignore_errors=True)


def test_authorization_take():
    print("【强推授权原子消费】")
    root = _mkproj()
    try:
        be = os.path.join(root, ".aidp", "scripts", "baseline_edit.py")
        base = [sys.executable, be, "--version", "V1.0.0"]
        subprocess.run(base + ["set", "release_force_authorized", "1"], cwd=root, capture_output=True, check=True)
        procs = [subprocess.Popen(base + ["take", "release_force_authorized", "--default", "0"],
                                  cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        vals = [p.communicate(timeout=10)[0].strip() for p in procs]
        check("并发消费仅一方取到授权，另一方默认拒绝", sorted(vals) == ["0", "1"])
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_baseline_epoch():
    print("【baseline_edit epoch】")
    be = os.path.join(SCRIPTS, "baseline_edit.py")
    run = lambda v: subprocess.run([sys.executable, be, "epoch", v], capture_output=True, text=True)
    a, b, bad = run("2026-10-26T10:00:00+08:00"), run("2026-10-26T02:00:00Z"), run("garbage")
    check("+08:00 与 Z 同一时刻 → 同一 epoch", a.returncode == 0 and a.stdout.strip() == b.stdout.strip() != "")
    check("不可解析 → 无输出、rc=1（调用方自定兜底）", bad.returncode == 1 and bad.stdout.strip() == "")


def test_self_check():
    print("【--self-check】")
    r = subprocess.run([sys.executable, SCHED, "--self-check"], capture_output=True, text=True)
    check("aidp_scheduler.py --self-check 通过", r.returncode == 0)


def test_scheduler_docs():
    print("【独立 watchdog 安装说明】")
    repo = os.path.dirname(os.path.dirname(SCRIPTS))
    paths = ("README.md", "memory/aidp-config.yaml", ".aidp/commands/sprint-autopilot.md",
             ".aidp/commands/sprint-aiauto-test.md", ".aidp/flows/sprint-autopilot/usage-guard.md",
             "skills/aidp-code-engineer/sources/root/README.md.tpl", ".aidp/scripts/README.md")
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
    test_agent_loop_timeout_and_lock()
    test_tick_result_and_lock_age()
    test_install_preflight()
    test_tick_flags_loop_evidence_and_mutex()
    test_session_reservation_lifecycle()
    test_fallback_lock_lifetime()
    test_cicd_retry_priority_and_poll()
    test_authorization_take()
    test_baseline_epoch()
    test_self_check()
    test_scheduler_docs()
    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)
