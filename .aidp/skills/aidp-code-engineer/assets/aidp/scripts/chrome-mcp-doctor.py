#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""chrome-mcp-doctor — chrome-devtools-mcp 远程连接配置「强制校验闸门」+ 配置器。

本脚本是 `/sprint-aiauto-test` 与 `/sprint-autopilot` 连接远程 Chrome 时
「写/合并项目根 .mcp.json + 连通性预检 + 全局污染检测 + 生效验证指引」的**单一信源**，
取代两命令里原本各自重复的内联 python。核心立场：

  ⛔ 远程 Chrome 地址**只**写项目根 `.mcp.json` 的 server 条目 `chrome-{git_user}`（`--scope project`）；
  ⛔ 绝不读改 `~/.claude.json`（`claude mcp add --scope user`/全局注册落地处）/ `~/.claude/settings*.json`
     / 历史遗留 `~/.claude/plugins/` 等任何**用户级 / 全局** MCP 配置（只读探测它们是否被历史会话写脏，给复位指引，绝不动手改）。

之所以需要一个脚本而不只是文档告诫：散文式「禁改清单」无法阻止 Agent 在
「项目根 .mcp.json 看起来不生效 → 顺藤摸瓜去改用户级/全局配置」时踩坑；本脚本把
「该调哪套工具 / 配置怎么写 / 端点是否真的可连 / 用户级/全局配置是否被写脏怎么救 / 怎么验证生效」
固化成可执行、有退出码的硬闸，命令端按退出码分流，杜绝最省力但违规的路径。

子命令：
  check                 体检（默认）：读项目根 .mcp.json + 连通性预检 + 污染检测 + 生效指引
  check-cli             ★ 驱动就绪体检：四独立信号（CLI_OK/NPM_PKG_OK/CHROME_BIN_OK/REMOTE）+ 五类驱动矩阵
                        + 合法动作 + cli 不可用修复命令。堵「npm 包在≠cli 可用」误判 + 补 local-chrome-no-cli 空洞。
                        两命令共用此单一信源判驱动，避免各自 grep 探测判据漂移。
  explain-error --error '<报错原文>'  ★ 已知错误 → 处置映射：回答「这段报错算不算浏览器不可用」。
                        verdict=not-a-blocker 时**禁止**据此降级为非浏览器驱动（退出码 0）。
  set --ip IP:PORT      写/合并远程条目（JSON 合并保留其它 server）后自动 check
  set --local-headless  切「本地无头兜底」：**改走 chrome-devtools-cli**（直连 CDP、免 MCP、免重启）——
                        清掉项目根 .mcp.json 的远程 chrome 条目（避免 MCP 半截加载干扰），
                        命令端随后启本机无头 chrome + cli 连接，**不再写任何 chrome-devtools-mcp 条目**。
  reset                 删除 chrome-{git_user} 条目（= 命令端 --reset-chrome-ip）

公共参数：
  --root DIR            项目根（默认当前目录）
  --json                追加机器可读 JSON 结果到 stdout 末尾（供命令端解析分流）

退出码：
  0  READY     —— 配置就绪（远程：条目正确 + 端点可达 + 无污染 / 本地无头：已切 cli、远程条目已清、无污染）
  3  NO_CONFIG —— 项目根 .mcp.json 缺 chrome-{git_user} 条目 → 命令端应跑 `set --ip`
  4  UNREACHABLE — 远程端点连不上（含 Host/Origin 限制）→ 打印 Chrome 启动参数修复指引
  5  POLLUTED  —— 用户级/全局 MCP 配置被写脏 → 打印复位指引并 STOP（绝不手改用户级/全局）
  1  BLOCKER   —— （explain-error）确属环境不具备，可降级但须留举证
  3  （explain-error）报错未收录 —— ⛔ 未收录 ≠ 可自行解释为不可用，先跑 check-cli
  2  USAGE     —— 参数错误
"""

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import urllib.request

# ── 退出码（命令端按此分流；与模块 docstring 一致）─────────────────────────
EXIT_READY = 0
EXIT_USAGE = 2
EXIT_NO_CONFIG = 3
EXIT_UNREACHABLE = 4
EXIT_POLLUTED = 5

# 历史会话往用户级/全局 MCP 配置（~/.claude.json 的 --scope user 注册 / 历史插件缓存）注入过的
# 典型「脏参数」（仅示例，便于报告里点名）。实际判定不依赖本清单穷举，而是「纯净安装 args 只有包名、
# 绝无任何 `--` 开头参数」这一不变量 —— 见 scan_plugin_pollution()。
POLLUTION_EXAMPLES = ("--browser-url", "--headless", "--executablePath",
                      "--isolated", "--remote-debugging")


def resolve_git_user(root):
    """解析 git user.name（去空格）作为 .mcp.json server 条目后缀；取不到回落 'user'。

    与两命令端原内联逻辑保持一致：server 名 = chrome-{git_user}，按 git 用户名分键，
    使同机多用户/团队共享 .mcp.json 时各持一条、互不覆盖。
    """
    try:
        out = subprocess.run(["git", "config", "user.name"], cwd=root,
                             capture_output=True, text=True, timeout=5)
        name = (out.stdout or "").strip().replace(" ", "")
        return name or "user"
    except Exception:
        return "user"


def mcp_path(root):
    """项目根 .mcp.json 的绝对路径（Claude Code 启动时自动加载的标准项目级 MCP 配置）。"""
    return os.path.join(root, ".mcp.json")


def load_mcp(root):
    """读项目根 .mcp.json，容错返回 dict（文件缺失 / 解析失败 → 空 dict）。"""
    path = mcp_path(root)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}
    return {}


def extract_browser_url(entry):
    """从一个 mcpServers 条目的 args 里取 --browser-url 的值（取不到返回 None）。

    兼容两种写法：`--browser-url URL`（分两元素）与 `--browser-url=URL`（合一元素）。
    """
    args = (entry or {}).get("args", []) or []
    for i, a in enumerate(args):
        if a == "--browser-url" and i + 1 < len(args):
            return args[i + 1]
        if isinstance(a, str) and a.startswith("--browser-url="):
            return a.split("=", 1)[1]
    return None


def host_port_from_url(url):
    """从 http://host:port 提取 (host, port)；解析失败返回 (None, None)。"""
    if not url:
        return None, None
    m = re.search(r"https?://([^/:]+):(\d+)", url)
    if m:
        return m.group(1), int(m.group(2))
    m = re.search(r"https?://([^/:]+)", url)
    if m:
        return m.group(1), 9222
    return None, None


# ── 写入 / 复位（只动项目根 .mcp.json，JSON 合并，绝不整体覆盖）──────────────

def write_entry(root, server_name, args):
    """把单个 server 条目合并进项目根 .mcp.json（保留其它 server，只增改本 key）。

    严禁 `cat >` 整体覆盖：.mcp.json 可能托管团队其它 MCP server，整体覆盖会冲掉别人配置。
    """
    path = mcp_path(root)
    data = load_mcp(root)
    data.setdefault("mcpServers", {})
    data["mcpServers"][server_name] = {"command": "npx", "args": args}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    ensure_not_gitignored(root)


def remove_entry(root, server_name):
    """删除指定 server 条目（reset / --reset-chrome-ip 用）。返回是否删到了东西。"""
    path = mcp_path(root)
    if not os.path.exists(path):
        return False
    data = load_mcp(root)
    servers = data.get("mcpServers", {})
    if server_name in servers:
        del servers[server_name]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return True
    return False


def ensure_not_gitignored(root):
    """确保 .mcp.json 不被 .gitignore 屏蔽（它是入库共享的项目级配置）。

    顺带清掉历史遗留的旧路径条目 `.claude/mcp/chrome-devtools-mcp.json`
    （早期版本曾把远程配置放该路径并 gitignore，现统一迁到入库的项目根 .mcp.json）。
    """
    gi = os.path.join(root, ".gitignore")
    if not os.path.exists(gi):
        return
    try:
        with open(gi, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return
    kept = [ln for ln in lines
            if ln.strip() not in (".mcp.json", ".claude/mcp/chrome-devtools-mcp.json")]
    if len(kept) != len(lines):
        with open(gi, "w", encoding="utf-8") as f:
            f.writelines(kept)


# ── 连通性预检（在 Claude Code 本机直探远端，复现 MCP 实际连接行为）──────────

def probe_endpoint(host, port, timeout=5):
    """探测 http://host:port/json/version，分类返回端点状态。

    返回 dict：{tcp, http, status, detail}
      status ∈ REACHABLE / TCP_FAIL / CONN_RESET / HTTP_FAIL
    设计要点：本脚本运行在 Claude Code 机器（即远程 Chrome 的客户端），
    直探 IP 等价于 chrome-devtools-mcp server 将要做的连接 → 是最贴近真实的预检。
    «Connection reset» 几乎总是远端 Chrome 未加 --remote-allow-origins=*/未监听 0.0.0.0
    的 Host/Origin 限制症状，专门归一为 CONN_RESET 以给出对应启动参数指引。
    """
    res = {"tcp": False, "http": False, "status": "TCP_FAIL", "detail": ""}
    # 1) 先做裸 TCP 连接，区分「端口根本不通」与「TCP 通但 HTTP 被拒」
    try:
        with socket.create_connection((host, port), timeout=timeout):
            res["tcp"] = True
    except Exception as e:
        res["detail"] = f"TCP 连接失败：{e}"
        return res
    # 2) TCP 通 → 试 HTTP /json/version
    url = f"http://{host}:{port}/json/version"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
        if "webSocketDebuggerUrl" in body or "Browser" in body:
            res["http"] = True
            res["status"] = "REACHABLE"
            m = re.search(r'"Browser"\s*:\s*"([^"]+)"', body)
            res["detail"] = m.group(1) if m else "CDP 端点正常"
        else:
            res["status"] = "HTTP_FAIL"
            res["detail"] = "HTTP 通但响应不含 CDP 端点字段（可能不是 Chrome 调试端口）"
    except ConnectionResetError as e:
        res["status"] = "CONN_RESET"
        res["detail"] = f"TCP 通但 HTTP 被重置（{e}）—— 远端 Chrome 的 Host/Origin 限制"
    except Exception as e:
        # urllib 对 connection reset / 403 / 500 的包装：按文本归类到 CONN_RESET 优先
        txt = str(e).lower()
        if "reset" in txt or "403" in txt or "500" in txt or "host" in txt or "origin" in txt:
            res["status"] = "CONN_RESET"
            res["detail"] = f"HTTP 被拒（{e}）—— 疑似远端 Chrome 的 Host/Origin 限制"
        else:
            res["status"] = "HTTP_FAIL"
            res["detail"] = f"HTTP 请求失败：{e}"
    return res


# ── 全局污染检测（只读；命中只给复位指引，绝不修改全局文件）──────────────────

def _scan_pollution_in_json(fp, hits):
    """从单个 JSON 文件（.mcp.json / plugin.json / ~/.claude.json）读 mcpServers，
    命中含 chrome-devtools 且 args 带 `--` 开头参数的 server → 追加进 hits。"""
    try:
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return
    for sname, entry in (data.get("mcpServers", {}) or {}).items():
        # 只看 chrome-devtools 相关 server（server 名或 args 里含关键字）
        args = (entry or {}).get("args", []) or []
        blob = sname + " " + " ".join(a for a in args if isinstance(a, str))
        if "chrome-devtools" not in blob:
            continue
        # 纯净安装的 args 只有包名（如 ["chrome-devtools-mcp@latest"]），不含任何 `--` 开头参数。
        # 因此任何 `--` 开头的 arg 都是历史会话越界注入（browser-url/headless/executablePath…）。
        bad = [a for a in args if isinstance(a, str) and a.startswith("--")]
        if bad:
            hits.append({"file": fp, "server": sname, "bad_args": bad})


def scan_plugin_pollution():
    """只读扫描用户级/全局 MCP 配置是否被写脏（新模型：~/.claude.json 的 --scope user 注册；
    旧模型残留：~/.claude/plugins 下 chrome-devtools-mcp 缓存）。

    返回命中列表，每项 {file, server, bad_args}。判定不变量：纯净安装的 server args 只有包名、
    绝无任何 `--` 开头参数；一旦出现（典型如 --browser-url/--headless/--executablePath…，
    见 POLLUTION_EXAMPLES）即为历史会话越界写入 → 唯一正解是移除该注册再改走项目级，绝不手改（见复位指引）。
    """
    hits = []
    # ① 新模型主入口：~/.claude.json（claude mcp add --scope user/全局 的落地处）
    user_json = os.path.expanduser("~/.claude.json")
    if os.path.isfile(user_json):
        _scan_pollution_in_json(user_json, hits)
    # ② 旧模型残留：~/.claude/plugins 下 chrome-devtools 相关的 .mcp.json / plugin.json
    base = os.path.expanduser("~/.claude/plugins")
    if os.path.isdir(base):
        for dirpath, _dirs, files in os.walk(base):
            for fn in files:
                if fn not in (".mcp.json", "plugin.json"):
                    continue
                fp = os.path.join(dirpath, fn)
                if "chrome-devtools" not in fp:
                    continue
                _scan_pollution_in_json(fp, hits)
    return hits


def detect_tool_installed():
    """只读探测 chrome-devtools-mcp 是否已装（降低安装摩擦用）。

    新模型主检测点 = npm 全局包（`npm ls -g chrome-devtools-mcp` 或 `which chrome-devtools-cli`）；
    旧模型残留兜底 = ~/.claude/plugins 下含 "chrome-devtools-mcp" 的插件目录。任一命中即视为已装。
    仅用于「未装时一键打印安装命令」，**不**改远程连接逻辑——远程一律走项目根 .mcp.json 的
    chrome-{git_user}，与工具是否装相互独立；本机 chrome-devtools-cli 本地测试也依赖本包。
    """
    # ① 新模型：npm 全局包已装
    try:
        r = subprocess.run(["npm", "ls", "-g", "chrome-devtools-mcp"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and "chrome-devtools-mcp@" in (r.stdout or ""):
            return True
    except Exception:
        pass
    # ② 新模型兜底：本地 CLI / 服务二进制在 PATH 上
    for exe in ("chrome-devtools-cli", "chrome-devtools-mcp"):
        try:
            if subprocess.run(["which", exe], capture_output=True, timeout=5).returncode == 0:
                return True
        except Exception:
            pass
    # ③ 旧模型残留：~/.claude/plugins 插件目录
    base = os.path.expanduser("~/.claude/plugins")
    if os.path.isdir(base):
        for dirpath, _dirs, files in os.walk(base):
            if "chrome-devtools-mcp" in dirpath and ("plugin.json" in files or ".mcp.json" in files):
                return True
    return False


# ── 四独立信号探测（check-cli 用；★ 不再把 npm包/MCP/cli 当等价信号合并）─────

def probe_cli():
    """CLI_OK：`chrome-devtools-cli` 技能的底层 CLI 命令是否**真正可执行**（本地 cli 驱动唯一凭据）。

    ★★ 根因修复（实际项目反馈核心）：cli 技能实际调用的命令是 **`chrome-devtools`**（由
       `npm i chrome-devtools-mcp@latest -g` 安装，见 chrome-devtools-mcp 公共包文档），
       **不是** `chrome-devtools-cli`——`chrome-devtools-cli` 只是**技能名**、从来不是命令/二进制名。
       AIDP 旧检测写 `command -v chrome-devtools-cli` 探错了名字 → 命令明明可用却误判"cli 不可用"
       → 静默降级到 MCP 协议。故这里探测**真实命令 `chrome-devtools`**（旧名作兼容兜底）。
    返回 (ok: bool, how: str)。
    """
    for name in ("chrome-devtools", "chrome-devtools-cli"):
        p = shutil.which(name)
        if p:
            return True, f"PATH:{p}"
    # 包已全局装但 bin 未链进 PATH 时，npx --no-install 可能仍能定位到（能跑起来才算可用）
    for name in ("chrome-devtools", "chrome-devtools-cli"):
        try:
            r = subprocess.run(["npx", "--no-install", name, "--version"],
                               capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                return True, f"npx --no-install {name}"
        except Exception:
            pass
    return False, ""


def probe_npm_pkg():
    """NPM_PKG_OK：chrome-devtools-mcp npm 全局包是否已装（仅代表远程 MCP 能力，**不代表 cli 可用**）。"""
    try:
        r = subprocess.run(["npm", "ls", "-g", "chrome-devtools-mcp"],
                           capture_output=True, text=True, timeout=15)
        ok = r.returncode == 0 and "chrome-devtools-mcp@" in (r.stdout or "")
        ver = ""
        m = re.search(r"chrome-devtools-mcp@(\S+)", r.stdout or "")
        if m:
            ver = m.group(1)
        return ok, ver
    except Exception:
        return False, ""


def probe_chrome_bin():
    """CHROME_BIN_OK：本机 chrome/chromium 可执行文件是否存在。返回 (ok, path)。"""
    for exe in ("google-chrome", "google-chrome-stable", "chromium",
                "chromium-browser", "chrome"):
        p = shutil.which(exe)
        if p:
            return True, p
    for p in ("/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
              "/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/snap/bin/chromium", "/opt/google/chrome/chrome",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if os.path.isfile(p):
            return True, p
    return False, ""


def npm_global_bin():
    """返回 `npm bin -g` / `npm root -g` 目录（供"包装了但 cli 不在 PATH"的排查引导）。"""
    for cmd in (["npm", "bin", "-g"], ["npm", "prefix", "-g"]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and (r.stdout or "").strip():
                return (r.stdout or "").strip()
        except Exception:
            pass
    return ""


def probe_instance_ownership():
    """★ 实例归属确定性判定（下游反馈 2026-08-05 改4）：读 `chrome-devtools status` 的 daemon args 定实例归属，
    把"连的是隔离实例还是外部 --browser-url 实例"变成**确定性输出**，替代执行体用 curl 9222 二手信号臆断
    （下游曾据 9222 探测编造"共享实例被抢占"虚构故障）。返回 dict。
      - daemon args 含 `--browser-url` → `external-browser-url:<url>`（连外部/远程实例）
      - 否则（`--isolated` 自起）→ `isolated-self-spawned`（daemon 跨会话长驻，历史标签属正常残留，勿归因他人 Chrome）
      - status 取不到（daemon 未起 / 命令不可用）→ `unknown`（不臆断，连接后以 Phase 0.1.2.1 实际 status 为准）
    read-only：`status` 仅查询 daemon 状态、不改变实例。
    """
    out = ""
    try:
        r = subprocess.run(["chrome-devtools", "status"], capture_output=True, text=True, timeout=15)
        out = (r.stdout or "") + (r.stderr or "")
    except Exception:
        out = ""
    if not out.strip():
        return {"instance_ownership": "unknown", "daemon_args": [], "daemon_uptime": None,
                "note": "chrome-devtools status 无输出（daemon 未起 / 命令不可用）→ 归属未知，勿臆断；连接后以 Phase 0.1.2.1 实际 status 为准"}
    args = re.findall(r'--[A-Za-z][\w-]*(?:=[^\s"\],]+)?', out)
    m_url = re.search(r'--browser-url[=\s]+(\S+)', out)
    m_up = re.search(r'(?:uptime|已运行|运行时长)[^0-9A-Za-z]*([0-9hms:dm]+)', out, re.IGNORECASE)
    if m_url:
        return {"instance_ownership": f"external-browser-url:{m_url.group(1)}", "daemon_args": args,
                "daemon_uptime": (m_up.group(1) if m_up else None),
                "note": "连外部实例（远程 / 手工起 chrome via --browser-url）"}
    return {"instance_ownership": "isolated-self-spawned", "daemon_args": args,
            "daemon_uptime": (m_up.group(1) if m_up else None),
            "note": "isolated 实例跨会话长驻，历史标签页属正常残留，勿归因为他人 Chrome / 其他进程抢占"}


def classify_driver(cli_ok, chrome_ok, remote_configured, remote_reachable):
    """★ 五类驱动矩阵（补齐第五类 local-chrome-no-cli 空洞）。返回 (category, driver, disclose)。

    优先级（唯一合法顺序）：cli → mcp-remote → (needs-restart-has-fallback) → mcp-plugin-fallback → blocked。
      - local-cli-ready           = CLI_OK && CHROME_BIN_OK              → cli
      - remote-ready              = 远程条目已配 && 端点可达            → mcp-remote（须命令端确认 MCP 工具已加载）
      - needs-restart-has-fallback= 远程配了但不可达 && 本机有 chrome   → 提示修远端/重启，或本地兜底（cli 优先）
      - local-chrome-no-cli ★新增 = CHROME_BIN_OK && !CLI_OK && 远程不可用 → mcp-plugin-fallback（须显式声明）或 manual
      - blocked-no-fallback       = 本机无 chrome && 远程不可用           → none（终止播报）
    disclose=True 表示该驱动是「降级路径」，命令端必须显式声明（终端 + #D 卡 + 报告 driver 字段）。
    """
    if cli_ok and chrome_ok:
        return "local-cli-ready", "cli", False
    if remote_configured and remote_reachable:
        return "remote-ready", "mcp-remote", False
    if remote_configured and not remote_reachable and chrome_ok:
        # 远程配了连不上 + 本机有 chrome：cli 可用则回落 cli（首选降级），否则落第五类
        return ("needs-restart-has-fallback", "cli" if cli_ok else "mcp-plugin-fallback", True)
    if chrome_ok and not cli_ok:
        return "local-chrome-no-cli", "mcp-plugin-fallback", True
    if chrome_ok and cli_ok:
        # 本机 chrome+cli 齐，只是没配远程 → 就是 local-cli-ready
        return "local-cli-ready", "cli", False
    return "blocked-no-fallback", "none", False


def do_check_cli(root):
    """check-cli 子命令（★ 命令编排层的驱动就绪预检）：一次性输出四独立信号 +
    驱动类别 + 该类别合法动作 + cli 不可用时的可执行修复命令。返回 (exit_code, result)。

    ★ 与 auto-test-runner `scripts/detect_drivers.py` 的分层关系（约定 21，避免误当双写）：
      - 本 `check-cli` = **命令编排层预检**（`/sprint-aiauto-test` Phase 0.1.1 / `/sprint-autopilot` Phase 0.5.5
        在委派 auto-test-runner **之前**跑，判 DRIVER + 是否需降级 + 是否显式声明），产出五类矩阵 + `recommended_driver`；
      - `detect_drivers.py` = **skill 执行内核层探测**（auto-test-runner 真正跑用例时自探）。
      两者同探真实命令 `chrome-devtools`（非 `chrome-devtools-cli`——那是技能名），职责分层、非重复实现；
      driver 取值枚举以 auto-test-runner `references/report-format.md` 为单一信源，两处须保持一致。

    退出码沿用：0=有可用/可降级驱动（cli / mcp-remote / mcp-plugin-fallback 之一）；
    4=仅剩需修远端的路径（remote 不可达且本机无 cli 也无 chrome 兜底之外的 UNREACHABLE 语义保留）；
    实际以 category 判定为准，命令端读 JSON 的 recommended_driver / category 分流。
    """
    git_user = resolve_git_user(root)
    server_name = f"chrome-{git_user}"

    cli_ok, cli_how = probe_cli()
    npm_ok, npm_ver = probe_npm_pkg()
    chrome_ok, chrome_path = probe_chrome_bin()

    # 远程配置 + 可达性（MCP 工具实际加载与否是 Claude Code runtime 信号，脚本只报"配了+可达"作代理）
    data = load_mcp(root)
    entry = (data.get("mcpServers", {}) or {}).get(server_name)
    configured_url = extract_browser_url(entry)
    remote_configured = bool(configured_url)
    remote_reachable = False
    reach = None
    if remote_configured:
        h, pnum = host_port_from_url(configured_url)
        if h:
            reach = probe_endpoint(h, pnum)
            remote_reachable = reach["status"] == "REACHABLE"

    category, driver, disclose = classify_driver(cli_ok, chrome_ok, remote_configured, remote_reachable)

    # ★ 实例归属确定性判定（改4）：读 daemon args，把"连隔离实例 vs 外部实例"变成确定性字段
    ownership = probe_instance_ownership()

    plugin_prefix = "mcp__plugin_chrome-devtools-mcp_chrome-devtools__"
    result = {
        "signals": {"CLI_OK": cli_ok, "NPM_PKG_OK": npm_ok, "CHROME_BIN_OK": chrome_ok,
                    "REMOTE_CONFIGURED": remote_configured, "REMOTE_REACHABLE": remote_reachable},
        "cli_how": cli_how, "npm_version": npm_ver, "chrome_path": chrome_path,
        "server_name": server_name, "configured_url": configured_url,
        "category": category, "recommended_driver": driver, "must_disclose": disclose,
        # 实例归属（一手判据 = daemon args，非 curl 9222）；写入 AI测试报告 data.notes，见 Phase 0.1.2.1
        "instance_ownership": ownership["instance_ownership"], "daemon_args": ownership["daemon_args"],
        "daemon_uptime": ownership["daemon_uptime"], "instance_ownership_note": ownership["note"],
    }

    print("━━━━━━━━━━ chrome 驱动就绪体检（check-cli）━━━━━━━━━━")
    print("【四独立信号（不再等价合并）】")
    print(f"  CLI_OK          = {cli_ok}   （cli 技能底层命令 `chrome-devtools` 可执行 = 本地 cli 驱动唯一凭据；注：命令名是 chrome-devtools，非 chrome-devtools-cli{'；' + cli_how if cli_how else ''}）")
    print(f"  NPM_PKG_OK      = {npm_ok}   （chrome-devtools-mcp 全局包{'@' + npm_ver if npm_ver else ''}；仅代表远程 MCP 能力，≠cli 可用）")
    print(f"  CHROME_BIN_OK   = {chrome_ok}   （{chrome_path or '本机未找到 chrome/chromium'}）")
    print(f"  REMOTE_CONFIGURED={remote_configured} / REMOTE_REACHABLE={remote_reachable}   （{configured_url or '未配远程 .mcp.json 条目'}）")
    print()
    print(f"【判定驱动类别】{category}  →  recommended_driver = {driver}" + ("  （降级路径，须显式声明）" if disclose else ""))
    print(f"【实例归属（一手判据=daemon args，非 curl 9222）】instance_ownership = {ownership['instance_ownership']}"
          + (f"  args={ownership['daemon_args']}" if ownership['daemon_args'] else "")
          + (f"  uptime={ownership['daemon_uptime']}" if ownership['daemon_uptime'] else ""))
    print(f"  → {ownership['note']}（写入 AI测试报告 data.notes；勿据 curl 9222 二手信号臆断实例异常）")
    print()

    if category == "local-cli-ready":
        print("  ✅ 本地 cli 就绪：命令端 DRIVER=cli，启本机无头 chrome + chrome-devtools-cli 连接。")
    elif category == "remote-ready":
        print(f"  ✅ 远程就绪：命令端 DRIVER=mcp-remote，调 mcp__{server_name}__*（须 runtime 确认 MCP 工具已加载）。")
    elif category == "needs-restart-has-fallback":
        print("  ⚠️ 远程配了但当前不可达：① 修远端 + 重启走远程；或 ② 本地兜底" + ("（cli 可用，DRIVER=cli）" if cli_ok else "（cli 不可用 → 见下 local-chrome-no-cli）"))
    elif category == "local-chrome-no-cli":
        print("  ⚠️ ★ 第五类 local-chrome-no-cli（本机有 chrome、cli 不可用、远程不可用）——合法动作按序：")
        print("     ① 诊断修复（★ 首先确认没探错命令名——真实命令是 chrome-devtools、不是 chrome-devtools-cli）：")
        if npm_ok:
            print(f"        · 包已装（chrome-devtools-mcp@{npm_ver}）但 CLI_OK=0 → 多半是 bin 未链进 PATH（或旧文档探错名字）：")
            print("            command -v chrome-devtools     # ★ 真实命令名（cli 技能用它，不是 chrome-devtools-cli）")
            print("            npx --no-install chrome-devtools --version   # npx 能否定位到 chrome-devtools")
            gbin = npm_global_bin()
            print(f"            echo \"$PATH\" | tr ':' '\\n' | grep -F '{gbin}'  # 确认 npm 全局 bin 目录在 PATH（当前：{gbin or '未取到'}）")
            print("            # 修好 PATH 后 chrome-devtools 即可用 → 回落 local-cli-ready（无需降级）")
        else:
            print("        · 包未装 → npm i chrome-devtools-mcp@latest -g（装 chrome-devtools 命令，装完再 check-cli 复验 CLI_OK）")
        print("     ② 若 ① 短期修不了 → 降级 = mcp-plugin-fallback（同插件 MCP 协议路径，合法但本地效率低）：")
        print(f"        调插件的 chrome-devtools 技能 / {plugin_prefix}*（它自起【本机独立隔离】chrome，非共享实例 → 无串测污染，可实测）；")
        print("        ⛔ 但必须【显式声明】：终端打印 + #D 里程碑通知正文 + AI测试报告 data.driver 字段填 'mcp-plugin-fallback'，严禁静默切换。")
        print("        替代路径：手工起 chrome --remote-debugging-port=9222 再按远程连。")
    else:  # blocked-no-fallback
        print("  ❌ blocked-no-fallback（本机无 chrome 且远程不可用）→ 无任何可用驱动：")
        print("     终止浏览器实测 + 播报「本机需装 chrome / 远端需就绪」（见依赖 SKILL 安装引导），不得静默改用任何驱动。")

    print()
    print("【⛔ 驱动优先级（唯一合法顺序，任何情况不得静默切换）】")
    print("  chrome-devtools-cli（本机首选）→ mcp__chrome-{git_user}__*（远程，需 .mcp.json+重启）")
    print("  → mcp-plugin-fallback（第五类降级，须显式声明）→ blocked-no-fallback（终止播报）")
    print(f"【结论】category={category}  driver={driver}  disclose={disclose}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # 有任一可用/可降级驱动 → 0；纯 blocked → 4（UNREACHABLE 语义：无驱动可用）
    exit_code = EXIT_UNREACHABLE if category == "blocked-no-fallback" else EXIT_READY
    result["exit_code"] = exit_code
    return exit_code, result


# ── 体检主流程 ───────────────────────────────────────────────────────────

def do_check(root, override_ip=None):
    """全量体检，打印人类可读报告，返回 (exit_code, result_dict)。"""
    git_user = resolve_git_user(root)
    server_name = f"chrome-{git_user}"
    tool_prefix = f"mcp__{server_name}__"
    plugin_tool_prefix = "mcp__plugin_chrome-devtools-mcp_chrome-devtools__"

    data = load_mcp(root)
    entry = (data.get("mcpServers", {}) or {}).get(server_name)
    configured_url = extract_browser_url(entry)
    args = (entry or {}).get("args", []) or []
    # 旧版会写过 chrome-devtools-mcp --headless=true 的「MCP 无头条目」；现已弃用（本地兜底改走 cli）。
    # 仍检出此类残留条目，提示清理（reset），避免 MCP 半截加载与 cli 抢占 9222。
    is_stale_mcp_headless = entry is not None and "--headless=true" in args and configured_url is None

    if entry is None:
        mode = "absent"
    elif configured_url:
        mode = "remote"
    elif is_stale_mcp_headless:
        mode = "stale-mcp-headless"
    else:
        mode = "unknown"

    # 目标 IP：显式 --ip > 已配 --browser-url 解析
    target_host, target_port = (None, None)
    if override_ip:
        if ":" in override_ip:
            h, p = override_ip.rsplit(":", 1)
            target_host, target_port = h, int(p) if p.isdigit() else 9222
        else:
            target_host, target_port = override_ip, 9222
    elif configured_url:
        target_host, target_port = host_port_from_url(configured_url)

    pollution = scan_plugin_pollution()
    reach = None
    # 只要已知目标 IP（来自 --ip 或已配 --browser-url）就做连通预检；
    # 本地无头模式无 browser-url、无目标，跳过预检。
    if target_host:
        reach = probe_endpoint(target_host, target_port)

    result = {
        "git_user": git_user, "server_name": server_name, "tool_prefix": tool_prefix,
        "mode": mode, "configured_url": configured_url,
        "target": f"{target_host}:{target_port}" if target_host else None,
        "reachability": reach, "pollution": pollution,
        "mcp_json": mcp_path(root),
    }

    # ── 报告打印 ──
    print("━━━━━━━━━━━━━━ chrome-mcp-doctor 体检 ━━━━━━━━━━━━━━")
    print(f"项目根 .mcp.json : {mcp_path(root)}")
    print(f"git 用户          : {git_user}")
    print(f"远程 server 条目   : {server_name}  （配置模式：{mode}）")
    if configured_url:
        print(f"已配 browser-url  : {configured_url}")
    print()
    print("【该调哪套工具（gap①）】")
    print(f"  ✅ 远程连接一律调本项目 server 的工具：{tool_prefix}*")
    print(f"     例：{tool_prefix}list_pages / {tool_prefix}navigate_page")
    print(f"  ⛔ 远程场景不要调插件自带的 {plugin_tool_prefix}*（那是插件自起的本地浏览器，连不到你的远端）")
    print(f"     — 注：本地场景 cli 不可用时，该 plugin server 是**合法 last-resort 降级**（须显式声明），见 `check-cli`")
    print()

    # 安装状态（降低摩擦：未装时一键打印安装命令，不必翻文档）
    tool_installed = detect_tool_installed()
    print("【安装（chrome-devtools-mcp）】")
    if tool_installed:
        print("  ✅ 已检测到 chrome-devtools-mcp（npm 全局包 / 本地 CLI / 历史插件任一）")
    else:
        print("  ⚠️ 未检测到 chrome-devtools-mcp — 复制下面命令安装（每台机器一次性）：")
        print()
        print("      # 全局安装（含本地 CLI chrome-devtools-cli + 远程 MCP 服务）")
        print("      npm i chrome-devtools-mcp@latest -g")
        print("      # 仅远程路径需注册 MCP 服务（本地 CLI 免注册、免重启）；")
        print("      # 服务名强制 chrome-<git 用户名>、强制 --scope project，禁用通用名与 --scope user/全局")
        print('      claude mcp add "chrome-$(git config user.name)" --scope project chrome-devtools-mcp')
        print()
        print("    本地默认路径：chrome-devtools-mcp 随仓库以插件分发（.aidp/plugins/chrome-devtools-mcp/），")
        print("    跑 `python3 .aidp/scripts/agent_sync.py` 即为 Claude Code / Codex / DeepSeek Harness 装配（需 Node.js）。")
        print("    远程注册后退出并重开 Claude Code（claude --dangerously-skip-permissions -c）使其加载。")
        print("    注：远程连接一律走项目根 .mcp.json（chrome-{git_user}）；本机 chrome-devtools-cli")
        print("        本地测试免 MCP 注册、免重启。本项缺失为提示性，不影响下方退出码。")
    print()

    exit_code = EXIT_READY
    next_action = "ready"

    # 1) 配置缺失
    if mode == "absent":
        print("【配置状态】❌ 项目根 .mcp.json 缺少远程条目")
        print(f"  → 跑：python3 .aidp/scripts/chrome-mcp-doctor.py set --ip <IP:9222>")
        print(f"     （远程不可达想本地兜底 → set --local-headless，会切 chrome-devtools-cli、不写 MCP 条目）")
        exit_code = EXIT_NO_CONFIG
        next_action = "set"
    elif mode == "stale-mcp-headless":
        # 旧版遗留的 chrome-devtools-mcp --headless=true 条目：现已弃用（本地兜底改走 cli）。
        print(f"【配置状态】⚠️ 检出旧版 MCP 无头条目 `{server_name}`（chrome-devtools-mcp --headless=true）")
        print(f"  本地无头兜底已改走 chrome-devtools-cli（直连 CDP、免 MCP/重启）→ 该 MCP 条目应清除：")
        print(f"  → 跑：python3 .aidp/scripts/chrome-mcp-doctor.py set --local-headless（清条目 + 切 cli）")
        print(f"     或：python3 .aidp/scripts/chrome-mcp-doctor.py reset（仅删条目）")
        exit_code = EXIT_NO_CONFIG
        next_action = "set-local-headless"
    else:
        print(f"【配置状态】✅ 已写入 server `{server_name}`（模式：{mode}）")

    # 2) 远程连通性预检（gap⑤）
    if reach is not None:
        print()
        print("【连通性预检（gap⑤）】")
        if reach["status"] == "REACHABLE":
            print(f"  ✅ http://{target_host}:{target_port}/json/version 可达 —— {reach['detail']}")
        elif reach["status"] == "TCP_FAIL":
            print(f"  ❌ TCP 连不上 {target_host}:{target_port} —— {reach['detail']}")
            _print_chrome_start_guide(target_port)
            if exit_code == EXIT_READY:
                exit_code, next_action = EXIT_UNREACHABLE, "fix-remote-chrome"
        elif reach["status"] == "CONN_RESET":
            print(f"  ❌ {reach['detail']}")
            print("     根因：远端 Chrome 未以 --remote-debugging-address=0.0.0.0 --remote-allow-origins=* 启动，")
            print("           或未做端口转发 → 非 localhost 的请求被重置。")
            _print_chrome_start_guide(target_port)
            if exit_code == EXIT_READY:
                exit_code, next_action = EXIT_UNREACHABLE, "fix-remote-chrome"
        else:
            print(f"  ⚠️ {reach['detail']}")
            if exit_code == EXIT_READY:
                exit_code, next_action = EXIT_UNREACHABLE, "fix-remote-chrome"

    # 3) 全局污染检测（gap②③）
    print()
    print("【用户级/全局 MCP 配置污染检测（gap②③，只读）】")
    if not pollution:
        print("  ✅ 未发现 ~/.claude.json / 历史 ~/.claude/plugins 下 chrome-devtools 被写脏")
    else:
        print("  ❌ 检测到用户级/全局 MCP 配置被历史会话写脏（远程地址绝不该写进这些文件）：")
        for h in pollution:
            print(f"     - {h['file']}")
            print(f"       server `{h['server']}` 多出非纯净参数：{h['bad_args']}")
        _print_reinstall_guide()
        # 污染优先级最高：即便 .mcp.json 已就绪，也要先复位被写脏的注册，避免两 server 抢浏览器
        exit_code, next_action = EXIT_POLLUTED, "reset-user-scope"

    # 4) 生效验证 + 反模式 + 生效机制（gap③④）
    print()
    print("【生效验证 + 反模式（gap③）】")
    print(f"  写/改 .mcp.json 后必须**重启 Claude Code**（见下），重启后用以下工具验证连到目标 IP：")
    print(f"      {tool_prefix}list_pages")
    print(f"  ⚠️ 若重启后唯一可用的 chrome 工具仍是通用那套 {plugin_tool_prefix}*（用户级/全局注册或历史插件）→")
    print(f"     说明项目 server 未加载（多半首次未批准信任）→ **停止并上报**，")
    print(f"     ⛔ 严禁退而去读/改 ~/.claude.json / ~/.claude/plugins 下任何文件「修 IP」（这是已知反模式）。")
    print()
    print("【生效机制：/mcp 重连 vs 重启（gap④）】")
    print("  • 项目根 .mcp.json 只在 Claude Code **启动时**读取一次、自动加载（无需 --mcp-config）。")
    print("  • **新增 / 改动** server 条目 → 必须**整体重启** Claude Code 才注册：")
    print("      claude --dangerously-skip-permissions -c   （-c 续上本次会话不丢上下文）")
    print("  • `/mcp` 重连只对**已加载**的 server 重新握手，**加载不了新增条目** → 别指望 /mcp 生效。")
    print("  • 首次加载会弹一次「是否信任本项目 MCP server」，批准后该项目不再询问。")

    print()
    print(f"【结论】exit={exit_code}  next={next_action}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    result["ok"] = (exit_code == EXIT_READY)
    result["next_action"] = next_action
    result["exit_code"] = exit_code
    result["tool_installed"] = tool_installed
    return exit_code, result


def _print_chrome_start_guide(port):
    """打印远端 Chrome 必须的启动参数 + 端口转发指引（gap⑤）。"""
    print("     ── 远端 Chrome 启动参数修复（必须同时满足监听 0.0.0.0 + 放开 Origin）──")
    print(f"     Windows : & \"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe\" \\")
    print(f"                 --remote-debugging-port={port} --remote-debugging-address=0.0.0.0 \\")
    print(f"                 --remote-allow-origins=* --user-data-dir=\"$env:TEMP\\chrome-debug\"")
    print(f"               + 端口转发：netsh interface portproxy add v4tov6 listenaddress=0.0.0.0 listenport={port} connectaddress=::1 connectport={port}")
    print(f"     macOS/Linux: google-chrome --remote-debugging-port={port} \\")
    print(f"                 --remote-debugging-address=0.0.0.0 --remote-allow-origins='*' --user-data-dir=/tmp/chrome-debug &")
    print(f"     验证：curl -s http://<远端IP>:{port}/json/version  应返回含 webSocketDebuggerUrl 的 JSON")


def _print_reinstall_guide():
    """打印「用户级/全局 MCP 配置已被写脏」的合法复位路径（gap②）——移除该注册，绝不手改。"""
    print("     ── 复位（绝不手改用户级/全局文件，移除被写脏的注册再改走项目级）──")
    print("     1) 新模型（--scope user/全局注册被写脏）：claude mcp remove chrome-devtools --scope user")
    print("        （server 名以体检报告里点名的为准；全局注册同理用对应 --scope 移除）")
    print("     2) 旧模型残留（历史插件缓存被写脏）：/plugin uninstall chrome-devtools-mcp@chrome-devtools-plugins")
    print("     复位后通用 server `chrome-devtools` 不再带脏参数（或彻底移除）；")
    print("     远程地址一律走项目根 .mcp.json 的 chrome-{git_user} 条目（--scope project，本脚本 set --ip）。")


# ── set / reset 子命令 ───────────────────────────────────────────────────

def do_set(root, ip=None, local_headless=False, executable=None):
    """写/合并条目后自动体检。remote 用 --browser-url；local-headless 切 chrome-devtools-cli（不写任何 MCP 条目）。"""
    git_user = resolve_git_user(root)
    server_name = f"chrome-{git_user}"
    if local_headless:
        # 本地无头兜底：**改走 chrome-devtools-cli**（直连 CDP、免 MCP、免重启 Claude Code）。
        # CLI 不是 MCP server、不读 .mcp.json，故这里**绝不写 chrome-devtools-mcp 条目**——
        # 反而要**清掉**残留的远程/旧版无头 MCP 条目，避免本会话半截加载 MCP 与 cli 抢占同一 9222。
        # 实际"启本机无头 chrome + cli 连接"由命令端 Phase 0.1.3/0.1.4 执行（DRIVER=cli），脚本只负责清场 + 指引。
        removed = remove_entry(root, server_name)
        if removed:
            print(f"✅ 已清除项目根 .mcp.json 的远程 chrome 条目 `{server_name}`（本地兜底不经 MCP）")
        else:
            print(f"ℹ️ 项目根 .mcp.json 无 `{server_name}` 条目，无需清除")
        print("✅ 本地无头兜底 = chrome-devtools-cli（直连 CDP）：命令端将启本机无头 chrome（--headless=new）+ cli 连接。")
        print("   ⛔ 不写、不需要任何 chrome-devtools-mcp 条目；cli 免 MCP、免重启 Claude Code，可同会话即时切有头/无头。")
        print("   ⚠️ 服务器无 GUI 也能跑无头；如遇沙箱报错，本机 chrome 启动侧加 --no-sandbox（详见依赖 SKILL）。")
        print()
        return EXIT_READY, {
            "git_user": git_user, "server_name": server_name,
            "mode": "local-cli", "driver": "cli", "mcp_entry_cleared": removed,
            "mcp_json": mcp_path(root), "next_action": "local-cli-headless",
        }
    if not ip:
        print("❌ set 远程模式需要 --ip IP:PORT", file=sys.stderr)
        return EXIT_USAGE, {}
    url = ip if ip.startswith("http") else f"http://{ip}"
    args = ["-y", "chrome-devtools-mcp@latest", "--browser-url", url]
    write_entry(root, server_name, args)
    print(f"✅ 已写远程条目到项目根 .mcp.json（server: {server_name} / --browser-url {url} / 已合并保留其它 server）")
    print("   ⛔ 远程连接只认本文件 + 重启 Claude Code；绝不改 ~/.claude.json / ~/.claude/plugins 下用户级/全局配置。")
    print()
    return do_check(root, override_ip=ip)


def do_reset(root):
    """删除 chrome-{git_user} 条目（--reset-chrome-ip）。"""
    git_user = resolve_git_user(root)
    server_name = f"chrome-{git_user}"
    removed = remove_entry(root, server_name)
    if removed:
        print(f"✅ 已从项目根 .mcp.json 删除 server `{server_name}`")
    else:
        print(f"ℹ️ 项目根 .mcp.json 中无 server `{server_name}`，无需删除")
    return EXIT_READY, {"removed": removed, "server_name": server_name}


# ── CLI ──────────────────────────────────────────────────────────────────

# ————————————————————————— 已知错误 → 处置映射（explain-error） —————————————————————————
#
# ⛔ 为什么必须是**表**而不是散文告诫（实际项目实测根因）：
#    执行体调 chrome-devtools MCP 工具拿到 "Missing X server to start the headful browser"，
#    据此得出「本机无法跑浏览器测试」，改用 curl + JDBC 跑完 34 条中的 29 条、5 条纯 UI 判据记 block，
#    还在报告里写下「chrome-devtools-mcp 只能起有头浏览器」。
#    该结论**完全错误**：错误信息自己就提示了 headless 选项；全局装的 CLI 命令是 `chrome-devtools`，
#    CLI 模式下 --headless 默认 true；当时该 CLI 守护进程正以 `--headless --isolated` 运行。
#    ——**这些事实本脚本里全都写着**，但只有跑它的人看得到。
#    错误发生在工具返回值里、不在任何文档的阅读路径上，所以必须有一个「拿报错来问」的入口。
#
# 每条的 verdict 只有两种取值，语义是硬的：
#   · not-a-blocker —— ⛔ 该报错【不构成】"浏览器驱动不可用"，禁止据此降级为非浏览器驱动
#   · blocker       —— 确属环境不具备，可按 fallback 降级（须留举证）
KNOWN_ERRORS = (
    {
        "id": "missing-x-server",
        "match": ("missing x server", "headful browser", "cannot open display",
                  "no display environment"),
        "verdict": "not-a-blocker",
        "meaning": "MCP 变体默认起【有头】浏览器，而本机无 X server（开发机 / CI / 容器常态）。"
                   "报错文本自己就给了出路（set headless to true），它说的是"
                   "「这个启动方式不行」，不是「浏览器不可用」。",
        "do": [
            "改走本地 CLI：命令是 `chrome-devtools`（CLI 模式 --headless 默认 true，免 MCP、免重启）",
            "或给 MCP 变体补 --headless",
            "或用 --browserUrl 指向一个已在跑的调试实例",
        ],
        "dont": [
            "⛔ 不得据此判定「浏览器驱动不可用」并降级为 curl / JDBC / HTTP 等非浏览器驱动",
            "⛔ 不要去装 xvfb —— 无头模式本来就不需要 X server",
            "⛔ 不得据此在报告里写「chrome-devtools-mcp 只能起有头浏览器」（事实不成立）",
        ],
    },
    {
        "id": "cli-name-confusion",
        "match": ("chrome-devtools-cli: command not found",
                  "chrome-devtools-cli: not found", "command not found: chrome-devtools-cli"),
        "verdict": "not-a-blocker",
        "meaning": "`chrome-devtools-cli` 是**技能名 / 文档里的称呼**，不是二进制名。"
                   "npm 全局包装出来的真实命令是 `chrome-devtools`。",
        "do": ["直接用 `chrome-devtools`；仍找不到再跑 `check-cli` 看 PATH / 安装诊断"],
        "dont": ["⛔ 不得据此判定「未安装浏览器驱动」"],
    },
    {
        "id": "cli-not-on-path",
        "match": ("chrome-devtools: command not found", "command not found: chrome-devtools"),
        "verdict": "not-a-blocker",
        "meaning": "多半是 npm 全局 bin 不在 PATH，而非没装（`check-cli` 的 NPM_PKG_OK "
                   "与 CLI_OK 是两个独立信号，正是为区分这种情况）。",
        "do": ["跑 `chrome-mcp-doctor.py check-cli` 看四信号 + 修复命令",
               "PATH 短期修不好 → 降级 mcp-plugin-fallback（同插件 MCP 协议），仍是浏览器驱动"],
        "dont": ["⛔ 不得跳过 check-cli 直接判定不可用"],
    },
    {
        "id": "chrome-binary-missing",
        "match": ("could not find chrome", "chrome executable not found",
                  "no usable sandbox", "browser was not found"),
        "verdict": "blocker",
        "meaning": "本机确实没有可用的 Chrome 二进制——这是真的环境不具备。",
        "do": ["装 Chrome，或改走远程 MCP 指向别的机器",
               "两条都不通 → 按 check-cli 的 blocked-no-fallback 处置（开发照常、测试段如实报缺）"],
        "dont": ["⛔ 降级时必须附 `check-cli` 完整输出举证；无举证的 UI 用例只能记 not-run，不得记 block"],
    },
)


def do_explain_error(text):
    """拿一段工具报错文本来问「这算不算浏览器不可用」。

    退出码：0 = not-a-blocker（⛔ 禁止据此降级）；1 = blocker（可降级，须举证）；3 = 未收录。
    """
    low = (text or "").lower()
    hit = None
    for e in KNOWN_ERRORS:
        if any(m in low for m in e["match"]):
            hit = e
            break
    if not hit:
        print("【未收录】这段报错不在已知映射表里。")
        print("  ⛔ 未收录 ≠ 可以自行解释为「浏览器不可用」——先跑 "
              "`chrome-mcp-doctor.py check-cli` 拿客观四信号再判。")
        return 3, {"matched": False, "verdict": "unknown",
                   "advice": "run check-cli before concluding"}

    print("【命中】%s  →  verdict = %s" % (hit["id"], hit["verdict"]))
    print("【含义】%s" % hit["meaning"])
    print("【正确处置】")
    for d in hit["do"]:
        print("  · %s" % d)
    print("【禁止】")
    for d in hit["dont"]:
        print("  %s" % d)
    if hit["verdict"] == "not-a-blocker":
        print("\n⛔ 本条属 not-a-blocker：**不得**据此把 driver_actual 降级为非浏览器驱动"
              "（curl / JDBC / HTTP 客户端等）。收尾门 3i 会比对 driver_actual，降级无举证即 FAIL。")
    return (0 if hit["verdict"] == "not-a-blocker" else 1), {
        "matched": True, "id": hit["id"], "verdict": hit["verdict"],
        "do": hit["do"], "dont": hit["dont"],
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="chrome-mcp-doctor",
        description="chrome-devtools-mcp 远程连接配置强制校验 + 配置器（只写项目根 .mcp.json）")
    p.add_argument("mode", nargs="?", default="check",
                  choices=["check", "check-cli", "explain-error", "set", "reset"],
                  help="子命令（默认 check）")
    p.add_argument("--ip", help="远程 Chrome IP:PORT（set 远程 / check 指定目标用）")
    p.add_argument("--local-headless", action="store_true",
                  help="set 本地无头兜底：切 chrome-devtools-cli（清 MCP 条目、不写 MCP、免重启）")
    p.add_argument("--executable", help="（保留）本地 chrome 可执行路径，命令端启无头 chrome 时可用")
    p.add_argument("--error", help="explain-error：待解释的工具报错原文（或用 stdin 喂）")
    p.add_argument("--root", default=".", help="项目根目录（默认当前目录）")
    p.add_argument("--json", action="store_true", help="末尾追加机器可读 JSON 结果")
    a = p.parse_args(argv)
    root = os.path.abspath(a.root)

    if a.mode == "set":
        code, result = do_set(root, ip=a.ip, local_headless=a.local_headless,
                              executable=a.executable)
    elif a.mode == "reset":
        code, result = do_reset(root)
    elif a.mode == "check-cli":
        code, result = do_check_cli(root)
    elif a.mode == "explain-error":
        txt = a.error if a.error is not None else (
            sys.stdin.read() if not sys.stdin.isatty() else "")
        code, result = do_explain_error(txt)
    else:
        code, result = do_check(root, override_ip=a.ip)

    if a.json:
        print("---JSON---")
        print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
