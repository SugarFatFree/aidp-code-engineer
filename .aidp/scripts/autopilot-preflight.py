#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot-preflight — `/sprint-autopilot` 与 `/sprint-aiauto-test` 的「Phase 0 通道与配置就绪」
**只读检测器 + 结构化硬门**（单一信源）。

为什么需要这个脚本：
  「通知通道就绪 + 发 #0a 通知」若只写成散文铁律且排在「拉码 / 脏工作区 → 立即 exit」之后，
  工作区一脏命令就在发任何通知之前退出 →「通道全就绪却整次零推送」。散文要求无法阻止执行体在
  出现分支（脏树退出 / test-intent 捷径）时跳过，故固化成有退出码的硬门。

本脚本把「就绪检测 + 收尾校验」固化成**确定性、有退出码、跳不过去**的硬门，与命令端分工：
  • 脚本（本文件）：查得准、拦得住 —— 读 baseline / git / .mcp.json / `memory/aidp-config.yaml`
    的 `notify` 段，`check` 给就绪表，`gate` 缺必需项即 `exit 1`。**只读，绝不写配置、绝不发通知、绝不问用户。**
  • 命令端：按检测结果**按正确顺序**发 #0a 里程碑通知（`notify.py --auto`）、就脏树让用户决策 ——
    这些交互动作子进程做不到，必须留在命令。
  两者叠加 = 防御纵深：脚本拦住"带缺失往下走"，命令负责"在最前面发通知/就问"。

chrome 维度**复用** `chrome-mcp-doctor.py`（同目录）的读取逻辑，不重复实现；深度连通预检仍由
doctor 负责（命令端写 .mcp.json 时调），本脚本只判 `chrome-{git_user}` 条目是否存在（轻量、不联网）。

子命令：
  check                  就绪体检（默认）：打印就绪表 + 输出 JSON；**恒 exit 0**（纯信息态，供命令端读 JSON 分流）
  gate --require k1,k2    收尾核验门：缺任一必需项 → `exit 1`（阻断进入 Phase 1/2/3 或委派）
  gate --interactive      用户在场的交互式调用：通知启用却无可用渠道时不放行（无人值守下降级放行）

可校验项（--require 的取值）：
  notify         里程碑通知通道（约定 32）：`notify.enabled=false` 视为满足（用户选择不通知）；
                 启用时至少一个渠道**本地可用**（webhook 渠道 = 对应 `*_env` 环境变量已设置；
                 `lark-cli` = 命令在 PATH 且配了 chat_id；`command` = 命令非空）。
                 启用却无可用渠道：/loop 无人值守视为降级满足（本轮通知静默跳过，⛔ 不硬阻塞），
                 **--interactive 下不满足**（要求用户当场补齐环境变量或关掉通知）。
  mcp_chrome     项目根 .mcp.json 有 chrome-{git_user} 条目（仅"需远程 chrome"时由命令端要求）
  clean_tree     git 工作区无非 PRD 改动（一般**不**放进 gate——脏树走命令端决策门，不静默拦）

公共参数：
  --root DIR             项目根（默认当前目录）
  --json                 追加机器可读 JSON 结果到 stdout 末尾（供命令端解析分流）
  --record-probe         把通知通道探测证据写入 baseline `notify_probe`（收尾门据此区分「没发」与「不需要发」）

退出码：
  0  READY    —— check 恒 0 / gate 全部必需项就绪
  1  MISSING  —— gate 模式下有必需项缺失（命令端就地补做后复跑，不得带缺失往下）
  2  USAGE    —— 参数错误
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text

import argparse
import importlib.util
import json
import os
import subprocess
import sys

# ── 退出码（命令端按此分流；与模块 docstring 一致）─────────────────────────
EXIT_READY = 0
EXIT_MISSING = 1
EXIT_USAGE = 2

BASELINE_REL = os.path.join("memory", ".sprint-autopilot-baseline.json")
# 工作区"允许未 commit"的 PRD/baseline 白名单（与 sprint-autopilot Phase 0 拉码门同口径）：
# 产品把新 PRD 放工作区未 commit 是合规场景；baseline 由命令自身管理。其余未 commit = 非 PRD 脏改动。
CLEAN_TREE_ALLOW_PREFIXES = ("docs/requirements/",)
CLEAN_TREE_ALLOW_EXACT = ("memory/.sprint-autopilot-baseline.json",)

# gate 未显式传 --require 时的默认必需项（两命令收尾门最低要求）。
DEFAULT_REQUIRE = ("notify",)
KNOWN_KEYS = ("notify", "mcp_chrome", "clean_tree")


def _run(cmd, root, timeout=5):
    """跑外部命令，返回 (returncode, stdout)；异常一律吞为 (非0, '')，调用方按需降级。"""
    try:
        out = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=timeout)
        return out.returncode, (out.stdout or "")
    except Exception:
        return 1, ""


# ── chrome 维度：复用 chrome-mcp-doctor（不重复实现）──────────────────────────

def _load_doctor():
    """动态加载同目录 chrome-mcp-doctor.py，复用其 .mcp.json 读取逻辑（缺失返回 None 走内联兜底）。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chrome-mcp-doctor.py")
    if not os.path.exists(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("chrome_mcp_doctor", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def detect_mcp_chrome(root):
    """判项目根 .mcp.json 是否已有 chrome-{git_user} 条目；返回 (present, server_name, browser_url)。

    优先复用 doctor 的 resolve_git_user/load_mcp/extract_browser_url（单一信源）；doctor 缺失则
    内联最小读取兜底。**只判存在性**，深度连通预检交给 doctor（命令端写 .mcp.json 时跑），本脚本不联网。
    """
    doctor = _load_doctor()
    if doctor is not None:
        try:
            git_user = doctor.resolve_git_user(root)
            server_name = f"chrome-{git_user}"
            data = doctor.load_mcp(root)
            entry = (data.get("mcpServers", {}) or {}).get(server_name)
            url = doctor.extract_browser_url(entry) if entry else None
            return (entry is not None, server_name, url)
        except Exception:
            pass
    # 内联兜底：doctor 缺失时直接读 .mcp.json
    rc, name = _run(["git", "config", "user.name"], root)
    git_user = (name.strip().replace(" ", "") or "user") if rc == 0 else "user"
    server_name = f"chrome-{git_user}"
    path = os.path.join(root, ".mcp.json")
    if not os.path.exists(path):
        return (False, server_name, None)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return (False, server_name, None)
    entry = (data.get("mcpServers", {}) or {}).get(server_name)
    url = None
    if entry:
        for i, a in enumerate(entry.get("args", []) or []):
            if a == "--browser-url" and i + 1 < len(entry["args"]):
                url = entry["args"][i + 1]
            elif isinstance(a, str) and a.startswith("--browser-url="):
                url = a.split("=", 1)[1]
    return (entry is not None, server_name, url)


# ── baseline / 通知通道 / git 工作区检测 ───────────────────────────────────

def load_baseline(root):
    """读 baseline（缺失/解析失败 → 空 dict）。"""
    path = os.path.join(root, BASELINE_REL)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
    return {}


def _now_iso():
    import datetime
    return datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _which(cmd):
    import shutil
    return bool(cmd) and shutil.which(cmd) is not None


def detect_notify(root, detail=None):
    """里程碑通知通道就绪（约定 32）：读 `memory/aidp-config.yaml` 的 `notify` 段，逐渠道做**本地**可用性判定。

    ⛔ 不联网、不发消息：gate 必须离线可跑。判定只回答「这个渠道在本机具备发送条件」，
    不回答「对端一定收得到」——后者由 `notify.py` 实发时的退出码说话。

    返回 (available: bool, info: dict)；`detail` 传 dict 时把**探测证据**填进去
    （enabled / channels[{type, ok, detail}]）。
    ⛔ 为什么要留证据：某轮通道配置齐全却整轮零通知时，事后必须能区分
    「通道当时就不可用（合规降级）」与「通道好好的但根本没去发（违规）」——
    探测结果只活在执行体上下文里，一落地就没了，两者在产物上完全同形。
    """
    d = detail if isinstance(detail, dict) else {}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aidp_config
        cfg = aidp_config.notify_config(root)
    except Exception as exc:  # noqa: BLE001
        cfg = {"enabled": False, "fallback": True, "channels": [], "error": str(exc)[:160]}
    try:
        import notify as _notify
        _ready = _notify.channel_ready            # 判据单一信源（与 notify.py --auto / tick_flags / Stop hook 同源）
    except Exception:  # noqa: BLE001
        def _ready(_c):
            return False, "notify.py 不可用"
    chans = []
    for c in cfg.get("channels") or []:
        typ = str(c.get("type") or "").strip()
        ok, why = _ready(c)
        chans.append({"type": typ, "ok": ok, "detail": why})
    enabled = bool(cfg.get("enabled"))
    available = enabled and any(ch["ok"] for ch in chans)
    d["enabled"] = enabled
    d["channels"] = chans
    return available, {"enabled": enabled, "channels": chans}


def detect_dirty_non_prd(root):
    """返回工作区里"非 PRD/baseline 白名单"的未 commit 改动路径列表（空 = 工作区干净/仅 PRD 改动）。

    与 sprint-autopilot Phase 0 拉码门同口径：PRD 目录 + baseline 文件的未 commit 改动允许通过，
    其余（尤其 Claude 自己写的代码）视为脏 → 命令端走"决策门"（commit/stash/abort），不再静默 exit。
    """
    rc, out = _run(["git", "status", "--porcelain"], root)
    if rc != 0:
        return []  # 非 git 仓库 / git 不可用 → 不阻塞（命令端另有分支判定）
    dirty = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()  # porcelain: "XY <path>"，去掉 2 位状态码 + 空格
        if "->" in path:         # 重命名 "old -> new" 取新路径
            path = path.split("->", 1)[1].strip()
        if path in CLEAN_TREE_ALLOW_EXACT:
            continue
        if any(path.startswith(p) for p in CLEAN_TREE_ALLOW_PREFIXES):
            continue
        dirty.append(path)
    return dirty


# ── 体检主流程 ───────────────────────────────────────────────────────────

def _project_name(root):
    """委派 `notify.py --check-name`（解析链单一信源在那边，⛔ 此处不另写一套）。"""
    p = os.path.join(root, runtime_relpath("", __file__), "scripts", "notify.py")
    if not os.path.isfile(p):
        return {}
    try:
        cp = subprocess.run([sys.executable, p, "--check-name", "--json", "--repo-root", root],
                            capture_output=True, text=True, timeout=10)
        return json.loads(cp.stdout or "{}")
    except Exception:
        return {}


def gather(root):
    """采集全部就绪信号，返回结构化 result dict（不打印、不判定）。"""
    bl = load_baseline(root)
    _notify_detail = {}
    notify_ok, _ = detect_notify(root, _notify_detail)
    mcp_present, server_name, browser_url = detect_mcp_chrome(root)
    dirty = detect_dirty_non_prd(root)
    return {
        "baseline_path": os.path.join(root, BASELINE_REL),
        "baseline_exists": os.path.exists(os.path.join(root, BASELINE_REL)),
        "notify_enabled": bool(_notify_detail.get("enabled")),
        "notify_available": notify_ok,
        "notify_probe": _notify_detail,
        "mcp_chrome_present": mcp_present,
        "mcp_server_name": server_name,
        "mcp_browser_url": browser_url,
        "git_dirty_non_prd": dirty,
        "project_name": _project_name(root),
    }


def is_satisfied(key, r, interactive=False):
    """单个可校验项是否满足（封装通知通道不可用时的降级语义）。

    interactive=True（用户在场的交互式调用）时，通知启用却无可用渠道视为未满足。
    """
    if key == "notify":
        if not r["notify_enabled"]:
            return True               # 用户选择不通知
        if r["notify_available"]:
            return True
        # ★ 启用却无可用渠道：无人值守视为降级满足（本轮通知静默跳过），绝不硬阻塞 /loop；
        #   仅交互式才拦门（要求用户当场补齐环境变量或关掉通知）。
        return not interactive
    if key == "mcp_chrome":
        return bool(r["mcp_chrome_present"])
    if key == "clean_tree":
        return not r["git_dirty_non_prd"]
    return False


# 缺失项 → 命令端应做的下一步（打印给执行者，确保"就地补做"路径清晰）。
NEXT_ACTION = {
    "notify": runtime_text('notify.enabled=true 但无可用渠道 → 设置 notify.channels 对应的 *_env 环境变量 / 安装 lark-cli，或 `python3 __AIDP_HOME__/scripts/aidp_state.py notify-disable` 关闭通知（约定 32）', __file__),
    "mcp_chrome": runtime_text('需远程 chrome → python3 __AIDP_HOME__/scripts/chrome-mcp-doctor.py set --ip <IP:9222> 写项目根 .mcp.json', __file__),
    "clean_tree": "非 PRD 改动走命令端决策门（commit/stash/abort），不静默退出",
}


def do_check(root):
    """就绪体检：打印就绪表，恒 exit 0（信息态）。返回 (0, result)。"""
    r = gather(root)
    print("━━━━━━━━━━━━ autopilot-preflight 就绪体检 ━━━━━━━━━━━━")
    print(f"baseline          : {r['baseline_path']} （{'存在' if r['baseline_exists'] else '缺失（首跑）'}）")
    # 里程碑通知通道
    probe = r.get("notify_probe") or {}
    if not r["notify_enabled"]:
        print("里程碑通知        : —  notify.enabled=false（不发通知，合规）")
    elif r["notify_available"]:
        print("里程碑通知        : ✅ 至少一个渠道本地可用")
    else:
        print("里程碑通知        : ⚠️ 已启用但无可用渠道 → 本轮通知降级跳过（无人值守不阻塞；交互式 gate 会拦）")
    chans = probe.get("channels") or []
    for i, ch in enumerate(chans):
        branch = "└" if i == len(chans) - 1 else "├"
        print(f"  {branch} {ch['type'] or '?':<12}: {'✅' if ch['ok'] else '❌'} {ch['detail']}")
    if r["notify_enabled"] and not chans:
        print("  └ 未配置任何渠道 → " + NEXT_ACTION["notify"])
    # 项目中文名称（通知标题固定前缀取它）——英文兜底不阻塞，但必须在体检表里露面：
    # 发通知发生在无人值守 tick 里，stderr 上的一行提示没人看得到。
    pn = r.get("project_name") or {}
    if pn.get("project_name"):
        if pn.get("is_ascii_fallback"):
            print(f"项目中文名称      : ⚠️ 英文兜底「{pn['project_name']}」（来源：{pn.get('source')}）→ "
                  f"通知标题会显示英文名；在 memory/aidp-config.yaml 补 project.name_cn")
        else:
            print(f"项目中文名称      : ✅ {pn['project_name']}（来源：{pn.get('source')}）")
    # mcp chrome
    if r["mcp_chrome_present"]:
        tail = f"（browser-url {r['mcp_browser_url']}）" if r["mcp_browser_url"] else "（本地无头/无 url）"
        print(f".mcp.json chrome  : ✅ {r['mcp_server_name']} 已存在 {tail}")
    else:
        print(f".mcp.json chrome  : —  无 {r['mcp_server_name']} 条目（本机/static-only 不需要；需远程才配）")
    # git tree
    if r["git_dirty_non_prd"]:
        n = len(r["git_dirty_non_prd"])
        print(f"git 工作区         : ⚠️ {n} 处非 PRD 未 commit 改动 → 决策门（commit/stash/abort，不静默退）")
        for p in r["git_dirty_non_prd"][:8]:
            print(f"                    - {p}")
        if n > 8:
            print(f"                    …… 另有 {n - 8} 处")
    else:
        print("git 工作区         : ✅ 干净（或仅 PRD/baseline 改动，允许）")
    print()
    print("【结论】exit=0（check 恒信息态）；命令端按上表对缺失项就地补做，再进入 0.7 收尾核验门（gate）。")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r["exit_code"] = EXIT_READY
    return EXIT_READY, r


def _gate_reason(key, r, interactive):
    """gate 失败项的下一步提示。"""
    return NEXT_ACTION.get(key, "补齐后复跑")


def do_gate(root, required, interactive=False):
    """收尾核验门：逐项校验必需项，缺任一 → exit 1。返回 (code, result)。

    interactive=True（用户在场的交互式调用）时通知通道须真可用（见 is_satisfied）。
    """
    r = gather(root)
    missing = [k for k in required if not is_satisfied(k, r, interactive)]
    ctx = ("交互式（用户在场：通知启用则须有可用渠道）" if interactive
           else "无人值守（通知不可用时降级放行，告警落本地台账）")
    print("━━━━━━━━━━━━ autopilot-preflight 收尾核验门（gate）━━━━━━━━━━━━")
    print(f"  上下文：{ctx}")
    for k in required:
        ok = is_satisfied(k, r, interactive)
        print(f"  {'✅' if ok else '❌'} {k}" + ("" if ok else f"  → {_gate_reason(k, r, interactive)}"))
    r["required"] = list(required)
    r["interactive"] = interactive
    r["missing"] = missing
    if missing:
        print()
        print(f"⛔ 收尾核验门未通过：缺 {missing} → 命令端就地补做后**复跑本门**，"
              f"不得带缺失进入 Phase 1/2/3 或委派 /sprint-aiauto-test。")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        r["exit_code"] = EXIT_MISSING
        return EXIT_MISSING, r
    print()
    print("✅ 收尾核验门通过：通道/配置就绪，允许进入 Phase 1/2/3 或委派。")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    r["exit_code"] = EXIT_READY
    return EXIT_READY, r


# ── CLI ──────────────────────────────────────────────────────────────────

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="autopilot-preflight",
        description="autopilot/aiauto-test 的 Phase 0 通道与配置就绪只读检测器 + 结构化硬门")
    p.add_argument("mode", nargs="?", default="check", choices=["check", "gate"],
                  help="子命令（默认 check 信息态；gate 缺必需项 exit 1）")
    p.add_argument("--require", default="",
                  help=f"gate 必需项（逗号分隔，可选 {','.join(KNOWN_KEYS)}；省略=默认 {','.join(DEFAULT_REQUIRE)}）")
    p.add_argument("--root", default=".", help="项目根目录（默认当前目录）")
    p.add_argument("--json", action="store_true", help="末尾追加机器可读 JSON 结果")
    p.add_argument("--record-probe", action="store_true",
                  help="把通知通道探测证据写入 baseline notify_probe（默认关，保持本脚本只读缺省）")
    p.add_argument("--interactive", action="store_true",
                  help="gate：用户在场的交互式调用——通知启用却无可用渠道时不放行；省略=无人值守（降级放行）")
    a = p.parse_args(argv)
    root = os.path.abspath(a.root)

    if a.mode == "gate":
        if a.require.strip():
            required = [k.strip() for k in a.require.split(",") if k.strip()]
            unknown = [k for k in required if k not in KNOWN_KEYS]
            if unknown:
                print(f"❌ 未知 --require 项：{unknown}（可选 {KNOWN_KEYS}）", file=sys.stderr)
                return EXIT_USAGE
        else:
            required = list(DEFAULT_REQUIRE)
        code, result = do_gate(root, required, a.interactive)
    else:
        code, result = do_check(root)

    # ★ 探测证据落盘（显式 --record-probe 才写，缺省仍是只读脚本）
    #   ⛔ 为什么必须留这份证据：通道配置齐全却整轮零通知时，事后无从判断是
    #      「通道当时就不可用（合规降级）」还是「通道好好的却没去发（违规）」——
    #      探测结果只活在执行体上下文里，一落地就没了，两种情况在产物上完全同形。
    #      收尾门据此把「没发」与「不需要发」拆开：无证据的缺通知一律算 missing，不算 skipped。
    if a.record_probe:
        _probe = (result or {}).get("notify_probe") or {}
        _bad = [f"{c.get('type')}: {c.get('detail')}" for c in (_probe.get("channels") or [])
                if not c.get("ok")]
        _rec = {"available": bool((result or {}).get("notify_available")),
                "enabled": bool(_probe.get("enabled")),
                "channels": _probe.get("channels") or [],
                "detail": "; ".join(_bad) if _bad else "",
                "at": _now_iso()}
        _edit = os.path.join(root, runtime_relpath("", __file__), "scripts", "baseline_edit.py")
        if os.path.isfile(_edit):
            try:
                subprocess.run([sys.executable, _edit, "set", "notify_probe",
                                json.dumps(_rec, ensure_ascii=False)],
                               capture_output=True, text=True, timeout=60)
            except Exception:
                pass    # 留痕失败绝不影响体检结论本身

    if a.json:
        print("---JSON---")
        print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
