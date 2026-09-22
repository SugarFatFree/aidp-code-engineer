#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_webmcp.py — 前端 WebMCP 能力的【启用判定】+ 脚手架侧装配守卫（脚手架契约脚本）。

## 职责边界（★ 先读这段，别把代码合规检查加回来）

WebMCP 相关检查分两处，**判据不重叠**：

| 归属 | 谁做 | 查什么 |
| :- | :- | :- |
| **代码实现合规** | 上游 `code-verification-loop` **维度 9** + 其 `scripts/check_webmcp_adapter.py` | 单一适配层 / `unregisterTool` / 错误契约死文案 / 写操作绕通道 / 敏感值外泄 / 白名单 |
| **脚手架侧装配** | **本脚本** | 启用判定 / 详规按需安装 / 「测试环境与账号」段回写 |

⛔ **不要把「单一适配层」「unregisterTool」这两项加回本脚本**——它们曾在这里实现过，
上游按需求落地后已**移交**。同一判据两份实现 = 改一处漏一处、且两处都声称自己权威，
是本仓最高频的漂移源（`check_di_resolvability.py` 有同样的先例：项目侧平行副本最终因
静默漏检而删除、统一回上游）。代码合规请调上游脚本，入参见下。

## 第一职责：**启用判定的唯一实现**

WebMCP 是一项**可选**前端能力，**绝大多数项目不启用**。它横跨 rules / agents / flows / verify /
四个上游 SKILL，每处都要回答同一个问题——「**本项目启用了吗？**」。若各处各自 `grep` PRD，
判据必然漂移，且**一处判错就会给未启用的项目凭空长出告警和产物位**，直接违反「默认关闭」总原则。

**四个上游 SKILL 全部做成「入参门控 + 明令不自行探测」**，判定权归调用方——也就是本脚本：

    python3 AIDP_HOME/scripts/check_webmcp.py --detect --json
    # → {"enabled": true, "entry_symbols": [...], "symbols_source": "..."}

命令端据此把 `webmcp_enabled` / `webmcp_entry_symbols` 传给 SKILL。
⛔ **不传 = 那些维度永不启用**：启用了该能力的项目会静默漏掉设计/用例/验收/执行四层质量门。

声明位置按序读，命中即止：

  ① PRD 头部 `autopilot_decisions.webmcp.enabled: true`
     —— **可选段，不计入必填段；段不存在 = 未启用**（默认关闭天然成立，不给未启用项目加收集负担）
  ② `docs/architecture/架构约束.md` 里显式声明 `webmcp` 启用

## 未启用时的行为（硬要求）

`applicable: false` + 退出码 `0` + **零 finding**。不得产生任何 WARN/ERROR、不得占用产物位。

## 启用时的守卫（脚手架侧装配，纯词法）

1. **详规已安装**（ERROR）：详规是**按需安装**的可选规则——默认在
   `AIDP_HOME/templates/optional-rules/webmcp.md`，启用后才装到 `AIDP_HOME/rules/webmcp.md`。
   `rules/*.md` 是**路径触发**加载的，不在那儿就永远不会被加载 = 规则等于不存在。
   跑 `--install-rule` 安装。
2. **详规未过期**（WARN）：安装副本与模板位不一致——要么脚手架升级后未刷新，要么副本被本地改过。
   判 WARN 不判 ERROR：刚升级未重装是正常中间态，且 `scaffold.py::refresh_optional_rules`
   通常已自动刷新，这里是**兜底可见性**。
3. **「测试环境与账号」已回写 WebMCP 段**（ERROR）：启用后用例会指向该文档取带参浏览器启动命令。
   下游真实踩过——**用例三处指向该文档，而文档里从未回写这一段**；文件在、内容锚点空，
   链接检查查不出来，执行者第一步就卡住。**只判最新版本**（旧版写于启用之前没有该段属正常，不连坐）。

## 能力入口标识符（⚠️ 会过期，务必看这段）

WebMCP 的挂载位置**已经迁移过一次**，规范仍在演进。故标识符**优先取项目声明**
`autopilot_decisions.webmcp.entry_symbols`（数组）；未声明才用内置默认清单 `DEFAULT_ENTRY_SYMBOLS`。
**内置默认是兜底、可能过期**——输出恒带 `symbols_source` 便于一眼看出用的是哪套。

⚠️ 上游 `check_webmcp_adapter.py` 在缺该入参时**报 exit 2 而不是猜默认值**（猜错的方向是
「扫不到 → 0 命中 → 假绿」）。命令端把本脚本的 `entry_symbols` 原样传过去即可，别让它落空。

## 用法

    python3 AIDP_HOME/scripts/check_webmcp.py [--root <仓库根>] [--detect] [--install-rule] [--force] [--json]

退出码：`0`=通过或未启用（N/A）/ `1`=检出问题 / `2`=用法或读取错误。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text
import argparse
import json
import os
import re
import subprocess
import sys

# ⚠️ 兜底清单，**可能过期**：挂载位置已迁移过一次，规范仍在演进。
#    项目应在 PRD `autopilot_decisions.webmcp.entry_symbols` 里声明本项目实测的入口标识符，
#    声明后本清单不参与判定（输出的 symbols_source 会写明用了哪套）。
#
# ★ 2026-08 实际项目中实测（Chrome 152.0.7977.64 · headless=new · 白名单已生效
#   `isSecureContext===true`）：**原有三个标识符全部 undefined，而能力其实存在**——接口类挂在
#   `window.ModelContext`（**大写 M**），其 prototype 方法集 = registerTool / getTools /
#   executeTool / ontoolchange（与本文档 §三 记录的 API 表面完全一致）。
#   一次改名（哪怕只是大小写）就让整份白名单一起失效，**而失效表现与"能力真的不存在"完全一样**——
#   于是一个可用的能力被判成不可用，下游整套 SUITE-MCP-ON（10 条用例）被记 block。
#   ⛔ 教训：白名单只是阳性猜测，**必须配全局扫描兜底**（见 --probe-snippet），否则无从区分
#      "它不存在" 与 "它改名了"。
DEFAULT_ENTRY_SYMBOLS = [
    "navigator.modelContext", "modelContext", "window.agent",
    "window.ModelContext",          # ★ Chrome 152 实测（大写 M，接口类）
    "navigator.ModelContext",
]

# 注入页面执行的探测片段：**白名单优先 + 全局扫描兜底**。
# 只查白名单 = 只做了阳性猜测，没有"如果它改名了我能不能发现"的兜底；扫到疑似入口就报出来
# 让人确认，而不是静默判"不可用"（与本仓反复强调的阴性/阳性对照是同一条方法论）。
PROBE_SNIPPET = r"""(() => {
  const want = %SYMBOLS%;
  const read = (path) => { try {
    return path.split('.').reduce((o, k) => (k === 'window' ? window : o && o[k]),
                                  window);
  } catch (e) { return undefined; } };
  const hits = {};
  for (const p of want) hits[p] = typeof read(p);
  // 兜底：白名单全落空时，扫 window / navigator / Navigator.prototype 上的疑似入口
  const suspects = [];
  const scan = (obj, label, re) => { try {
    for (const k of Object.getOwnPropertyNames(obj)) if (re.test(k)) {
      let t = 'unknown'; try { t = typeof obj[k]; } catch (e) {}
      suspects.push({ where: label, name: k, type: t });
    }
  } catch (e) {} };
  scan(window, 'window', /^(model|mcp|agent)/i);
  scan(navigator, 'navigator', /model|mcp|tool/i);
  scan(Object.getPrototypeOf(navigator), 'Navigator.prototype', /model|mcp|tool/i);
  return { isSecureContext: window.isSecureContext, whitelist: hits, suspects };
})()"""

# 「测试环境与账号」里 WebMCP 段的存在标记（与 /sprint-selftest Step 3 模板一致）
TESTENV_MARK = re.compile(r"WebMCP|unsafely-treat-insecure-origin-as-secure")

# ★ 详规是【按需安装】的可选规则，默认不在 rules/ 下 —— 见下方 install_rule() 的 Why
RULE_TEMPLATE = os.path.join(runtime_relpath("", __file__), "templates", "optional-rules", "webmcp.md")
RULE_INSTALLED = os.path.join(runtime_relpath("", __file__), "rules", "webmcp.md")


def _read(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _ver_key(name):
    """版本目录排序键：V0.10.0 必须排在 V0.9.0 之后（字符串排序会反）。"""
    return [int(x) for x in re.findall(r"\d+", name)] or [0]


def _prd_files(root):
    """PRD 目录内的 .md（各版本 docs/requirements/{V}/产品提供/）。"""
    base = os.path.join(root, "docs", "requirements")
    if not os.path.isdir(base):
        return []
    out = []
    for ver in sorted(os.listdir(base)):
        d = os.path.join(base, ver, "产品提供")
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".md"):
                out.append(os.path.join(d, fn))
    return out


def detect(root):
    """启用判定的**唯一实现**。返回 {enabled, source, entry_symbols, symbols_source}。"""
    symbols, sym_src = DEFAULT_ENTRY_SYMBOLS, "内置默认（⚠️ 可能过期，建议项目显式声明 entry_symbols）"

    # ① PRD 头部 autopilot_decisions.webmcp
    for p in _prd_files(root):
        head = "\n".join(_read(p).split("\n")[:200])
        m = re.search(r"^\s*webmcp:\s*$((?:\n[ \t]+.*|\n\s*)*)", head, re.M)
        if not m:
            continue
        block = m.group(1)
        # entry_symbols 声明（YAML 行内数组或块数组均识别）
        sm = re.search(r"entry_symbols:\s*\[([^\]]*)\]", block)
        if not sm:
            bm = re.search(r"entry_symbols:\s*$((?:\n[ \t]+-\s*.*)+)", block, re.M)
            if bm:
                got = re.findall(r"-\s*['\"]?([^'\"\n]+?)['\"]?\s*$", bm.group(1), re.M)
                if got:
                    symbols, sym_src = [g.strip() for g in got if g.strip()], f"PRD 声明（{os.path.relpath(p, root)}）"
        else:
            got = [s.strip().strip("'\"") for s in sm.group(1).split(",") if s.strip()]
            if got:
                symbols, sym_src = got, f"PRD 声明（{os.path.relpath(p, root)}）"
        if re.search(r"enabled:\s*(true|yes|on)\b", block, re.I):
            return {"enabled": True, "source": f"PRD `autopilot_decisions.webmcp.enabled`（{os.path.relpath(p, root)}）",
                    "entry_symbols": symbols, "symbols_source": sym_src}
        # 段在但 enabled 非 true → 显式关闭，不再往下找（显式声明优先）
        return {"enabled": False, "source": f"PRD 显式声明未启用（{os.path.relpath(p, root)}）",
                "entry_symbols": symbols, "symbols_source": sym_src}

    # ② 架构约束文档
    for cand in ("架构约束.md", "架构设计.md"):
        p = os.path.join(root, "docs", "architecture", cand)
        if os.path.isfile(p) and re.search(r"WebMCP.*(?:启用|开启|采用)|启用\s*WebMCP", _read(p)):
            return {"enabled": True, "source": f"docs/architecture/{cand} 显式声明",
                    "entry_symbols": symbols, "symbols_source": sym_src}

    return {"enabled": False, "source": "未声明（默认关闭）",
            "entry_symbols": symbols, "symbols_source": sym_src}


def detect_with_launch(root):
    """`detect()` + `launch_command`（供给三个上游 SKILL 的第三个入参）。"""
    d = detect(root)
    d["launch_command"] = _launch_command(root) if d["enabled"] else ""
    return d


def _launch_command(root):
    """从最新版「测试环境与账号」的 WebMCP 段解析**带参浏览器完整启动命令**。

    ★ 为什么必须由命令端供给：`dev-manual-testcase` / `dev-logic-architect` / `auto-test-runner`
    三个 SKILL 都把 `webmcp_launch_command` 列为**调用方入参并明令「不要自拟」**——
    自拟的命令跑通了也无法复现，等于把配置藏进一次性会话里。而此前**全仓零传**，
    三处调用点只传了 `webmcp_enabled` + `webmcp_entry_symbols`。

    取不到返回空串：调用方据此传空并让 SKILL 引用**文档路径**（`dev-manual-testcase` 的
    维度 20 允许「取自 `webmcp_launch_command` 或环境文档」），⛔ 不得自拟一条顶上。
    """
    tbase = os.path.join(root, "docs", "testing")
    if not os.path.isdir(tbase):
        return ""
    for ver in sorted(os.listdir(tbase), key=_ver_key, reverse=True):
        p = os.path.join(tbase, ver, "研发自测", "01_测试环境与账号.md")
        if not os.path.isfile(p):
            continue
        txt = _read(p)
        m = re.search(r"WebMCP[^\n]*\n(?:.*\n)*?\|\s*完整启动命令\s*\|\s*`?([^`|\n]+?)`?\s*\|", txt)
        if m:
            cmd = m.group(1).strip()
            # 模板占位符（`<可直接复制执行的整行命令…>`）不算已登记
            if cmd and not cmd.startswith("<"):
                return cmd
        # 兜底：段内首条含白名单参数的命令行
        m2 = re.search(r"^\s*([^\n]*--unsafely-treat-insecure-origin-as-secure[^\n]*)$", txt, re.M)
        if m2 and "<" not in m2.group(1):
            return m2.group(1).strip().lstrip("`").rstrip("`")
        return ""
    return ""


# ── 启动参数推导（`--launch-args`）───────────────────────────────────────────
#
# ★ 为什么需要它：`_launch_command()` 只**解析**环境文档里人工登记过的整行命令，没登记就返回
#   空串；而三个上游 SKILL 又被明令「不要自拟」。两条规则叠在一起的结果是——**只要没人预先
#   把命令写进 `01_测试环境与账号.md`，WebMCP 就静默地永远不可用**，且失败表现与"浏览器不支持"
#   完全一样（下游实测正是如此）。
#
#   「不要自拟」对 SKILL 是对的：它们不知道环境。但**命令端知道**——它手里有前端访问地址，
#   而且浏览器就是它启的。故这里给出一份**确定性推导**：同一个实现、可测、三处调用点共用，
#   既补上缺口，又不违反"不许各自编一条"的初衷。
#
# 关键事实（`chrome-devtools start --help` 实测，非文档推测）：
#   · `--chromeArg <arg>`（可重复）—— 透传 Chrome 启动参数，**仅在 chrome 由 CLI 自起时生效**
#   · `--categoryExperimentalWebmcp true` —— 暴露 WebMCP 调试工具面，**要求 Chrome 150+
#     且 chrome 侧带 `--enable-features=WebMCP`**（两者缺一，工具面不出现）
MIN_CHROME_FOR_WEBMCP = 150
_ORIGIN_RE = re.compile(r"^(https?)://([^/:\s]+)(?::(\d+))?$")
# secure context 天然成立的 host（不需要白名单；给它加反而多此一举）
_SECURE_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]"}


def normalize_origin(url):
    """把任意页面 URL 收敛成 `scheme://host[:port]` 三段。匹配是**逐字精确**的：
    scheme / host / port 任一不符，白名单就不生效——且不生效时**没有任何报错**，
    只是 `isSecureContext` 依旧 false。故这里宁可返回 None 让调用方报错，也不猜。"""
    if not url:
        return None
    u = url.strip().rstrip("/")
    u = re.sub(r"^(https?://[^/]+).*$", r"\1", u)
    return u if _ORIGIN_RE.match(u) else None


def origin_is_secure(origin):
    m = _ORIGIN_RE.match(origin or "")
    if not m:
        return False
    return m.group(1) == "https" or m.group(2) in _SECURE_HOSTS


def _chrome_major(executable=""):
    """本机 Chrome 主版本号；取不到返回 None（不猜、也不因此阻断）。"""
    for cmd in ([executable] if executable else []) + [
            "google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
        if not cmd:
            continue
        try:
            cp = subprocess.run([cmd, "--version"], capture_output=True, text=True, timeout=15)
        except (OSError, subprocess.SubprocessError):
            continue
        m = re.search(r"(\d+)\.\d+", cp.stdout or "")
        if m:
            return int(m.group(1))
    return None


def frontend_origin(root):
    """从最新版「测试环境与账号」里取前端访问地址并收敛成 origin。

    ★ 为什么由脚本自己读、而不是让 flow 传变量进来：flow 分片之间是**独立的 Bash 调用**，
      shell 变量不跨分片存活。让调用方传 `$FRONTEND_URL` 的写法在这里必然取到空串，
      而空 origin 会让本函数报错、报错又常被 `|| true` 吞掉 → `WEBMCP_FLAGS` 恒空 →
      **WebMCP 静默永不启用**，症状与"浏览器不支持"一模一样——正是本能力要消灭的那个坑。
      地址的权威落点由约定 38 保证一定在这份文档里，直接读它没有中间环节。
    """
    tbase = os.path.join(root, "docs", "testing")
    if not os.path.isdir(tbase):
        return ""
    for ver in sorted(os.listdir(tbase), key=_ver_key, reverse=True):
        p = os.path.join(tbase, ver, "研发自测", "01_测试环境与账号.md")
        if not os.path.isfile(p):
            continue
        txt = _read(p)
        # 优先取显式标了「前端」的那一行；否则取文档里第一个 http(s) 地址
        m = re.search(r"前端[^\n|]*\|[^|\n]*?(https?://[^\s|`）)]+)", txt)
        if not m:
            m = re.search(r"(https?://[^\s|`）)]+)", txt)
        if m:
            o = normalize_origin(m.group(1))
            if o:
                return o
    return ""


def launch_args(root, origins, driver="cli", executable=""):
    """推导本轮该带的启动参数。driver: `cli`（chrome-devtools 自起）/ `manual`（手工起 chrome）。"""
    det = detect(root)
    res = {"enabled": det["enabled"], "driver": driver, "origins": [],
           "insecure_origins": [], "chrome_major": None,
           "cli_args": [], "chrome_flags": [], "user_data_dir": "",
           "warnings": [], "error": None}
    if not det["enabled"]:
        res["error"] = "webmcp-not-enabled"
        return res
    if driver not in ("cli", "manual"):
        res["error"] = f"unknown-driver:{driver}"
        return res
    # 未显式传 --origin → 自动从「测试环境与账号」取（见 frontend_origin 的 why）
    if not origins:
        auto = frontend_origin(root)
        origins = [auto] if auto else []
    for raw in origins or []:
        o = normalize_origin(raw)
        if not o:
            res["error"] = f"bad-origin:{raw}（须形如 http://host:port，逐字精确）"
            return res
        res["origins"].append(o)
        if not origin_is_secure(o):
            res["insecure_origins"].append(o)
    if not res["origins"]:
        res["error"] = ("no-origin：既未传 --origin，也未能从最新版 "
                        "docs/testing/*/研发自测/01_测试环境与账号.md 取到前端地址"
                        "（按约定 38 该地址本应已归档在那里）")
        return res

    major = _chrome_major(executable)
    res["chrome_major"] = major
    if major is not None and major < MIN_CHROME_FOR_WEBMCP:
        res["warnings"].append(
            f"本机 Chrome {major} < {MIN_CHROME_FOR_WEBMCP}：WebMCP 工具面不会出现，"
            "本轮应按未启用处理，⛔ 不要把它报成『能力不存在』")
    elif major is None:
        res["warnings"].append("取不到本机 Chrome 版本，无法核实 150+ 前提（不阻断）")

    chrome_flags = ["--enable-features=WebMCP"]
    if res["insecure_origins"]:
        chrome_flags.append("--unsafely-treat-insecure-origin-as-secure="
                            + ",".join(res["insecure_origins"]))
    else:
        res["warnings"].append("目标 origin 本就是 secure context，无需白名单参数")
    res["chrome_flags"] = chrome_flags

    if driver == "cli":
        res["cli_args"] = ["--categoryExperimentalWebmcp", "true"]
        for f in chrome_flags:
            res["cli_args"] += ["--chromeArg", f]
        res["warnings"].append(
            "CLI daemon 跨会话长驻：改了参数必须显式 `chrome-devtools start` 重启，"
            "否则沿用旧 daemon、新参数【静默不生效】")
    else:
        # 手工起 chrome：必须换一个独立 user-data-dir。Chrome 单例机制会把 URL 转交给
        # 先启动的实例、后启动的自己退出，**新增的启动参数被静默丢弃且无任何报错**——
        # 实测表现是同一页面两次探测结论相反。
        res["user_data_dir"] = "/tmp/chrome-debug-webmcp"
        res["warnings"].append(
            "手工起 chrome 必须用独立 --user-data-dir（本结果已给）：与既有实例共用目录时，"
            "Chrome 单例机制会静默丢弃新参数")
    return res


def install_rule(root, force=False):
    """把详规从模板位安装到 `AIDP_HOME/rules/`（幂等）。

    **Why 详规默认不在 rules/ 下**：`rules/*.md` 是**路径触发**加载的——只要编辑的文件命中
    `paths:`，整份文件就进上下文。绝大多数项目根本不启用 WebMCP，却要在每次编辑前端代码时
    白读十几 KB，读完的唯一结论是"本项目不适用"。这与「未启用即零成本」的总原则直接冲突。
    故模板位存放（`templates/` 不被 rules 机制扫描）、启用后才安装。

    **⛔ 未启用时拒绝安装**：否则一次误装就让该项目永久承担这份常驻成本，
    而它恰恰是本设计要消除的东西。
    """
    det = detect(root)
    src, dst = os.path.join(root, RULE_TEMPLATE), os.path.join(root, RULE_INSTALLED)
    if not det["enabled"] and not force:
        return {"ok": False, "action": "refused",
                "detail": f"本项目未启用 WebMCP（{det['source']}）——⛔ 拒绝安装。"
                          f"未启用却装上，等于让该项目每次编辑前端代码都白读一份不适用的规则，"
                          f"正是本设计要消除的成本。确需强装用 --force"}
    if not os.path.isfile(src):
        return {"ok": False, "action": "missing-template",
                "detail": f"模板位不存在：{RULE_TEMPLATE}（重跑脚手架补全）"}
    if os.path.isfile(dst) and _read(dst) == _read(src):
        return {"ok": True, "action": "already-installed", "detail": f"{RULE_INSTALLED} 已是最新，无需重装"}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    was = os.path.isfile(dst)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(_read(src))
    return {"ok": True, "action": "updated" if was else "installed",
            "detail": f"已{'更新' if was else '安装'} {RULE_INSTALLED}（源：{RULE_TEMPLATE}）"}


def run(root):
    det = detect(root)
    if not det["enabled"]:
        # ★ 未启用 = N/A：零 finding、零告警、不占产物位（rules/webmcp.md 适用前提）
        return {"applicable": False, "enabled": False, "reason": det["source"],
                "findings": [], "passed": True, **det}

    findings = []
    # ★ 守卫 0：已启用但详规没装 → 规则永远不会被加载，静默失效。
    #   这是「模板位存放 + 按需安装」方案的闭环所在：漏装必须被硬拦，
    #   否则"启用了却没规则可读"会一路无声地走到实现期。
    rule_installed = os.path.isfile(os.path.join(root, RULE_INSTALLED))
    # ★ 守卫 0b：装了但已过期（模板位随脚手架升级更新了、安装副本还停在旧版）。
    #   判 WARN 不判 ERROR：刚升完级还没重装是正常中间态，且 scaffold 的
    #   `scaffold.py::refresh_optional_rules` 正常情况下已自动刷新——这里是**兜底可见性**，
    #   防"自动刷新没跑到 / 被判定为本地改动而跳过"时无声地长期用着旧规则。
    if rule_installed:
        tpl = os.path.join(root, RULE_TEMPLATE)
        if os.path.isfile(tpl) and _read(tpl) != _read(os.path.join(root, RULE_INSTALLED)):
            findings.append({
                "level": "WARN", "check": "rule-stale", "file": RULE_INSTALLED,
                "detail": f"已安装的详规与模板位 `{RULE_TEMPLATE}` 内容不一致——要么脚手架升级后"
                          f"未刷新（跑 `check_webmcp.py --install-rule` 重装），"
                          f"要么安装副本被本地改过（⛔ 改动应回模板位，安装副本改了无法回流、重装即丢）",
            })
    if not rule_installed:
        findings.append({
            "level": "ERROR", "check": "rule-not-installed", "file": RULE_INSTALLED,
            "detail": runtime_text(
                f"已启用 WebMCP，但详规未安装到 `{RULE_INSTALLED}` —— rules 是**路径触发**加载的，"
                "文件不在那儿就永远不会自动加载，规则等于不存在。"
                "跑 `python3 __AIDP_HOME__/scripts/check_webmcp.py --install-rule` 安装"
                f"（模板位：{RULE_TEMPLATE}）",
                __file__,
            ),
        })
    # ⛔ 「单一适配层」与「unregisterTool」两项判据【已移交上游】——
    #   由 `code-verification-loop` 维度 9 + 其 scripts/check_webmcp_adapter.py 承担。
    #   本脚本只负责把 entry_symbols 供给出去（命令端传给上游），不再自己扫前端源码。
    #   别加回来：同一判据两份实现 = 改一处漏一处、两处都自称权威（见模块 docstring「职责边界」）。

    # 启用后「测试环境与账号」必须回写 WebMCP 段（下游踩过：用例三处指向它、文档里从未写）
    # ★ 只判**最新版本**那一份：旧版本写于启用之前、没有该段是正常的，连坐会制造永远修不掉的红灯。
    testenv_ok, testenv_seen = True, []
    tbase = os.path.join(root, "docs", "testing")
    if os.path.isdir(tbase):
        for ver in sorted(os.listdir(tbase), key=_ver_key):
            p = os.path.join(tbase, ver, "研发自测", "01_测试环境与账号.md")
            if os.path.isfile(p):
                testenv_seen.append(os.path.relpath(p, root))
        if testenv_seen:
            testenv_ok = bool(TESTENV_MARK.search(_read(os.path.join(root, testenv_seen[-1]))))
    if testenv_seen and not testenv_ok:
        findings.append({
            "level": "ERROR", "check": "testenv-section", "file": testenv_seen[-1],
            "detail": "已启用 WebMCP，但「测试环境与账号」里没有 WebMCP 段（带参浏览器启动命令 + 两行自检）。"
                      "用例会指向该文档取启动命令——**文件在、内容锚点空，链接检查查不出来，"
                      "执行者第一步就卡住**（下游真实踩过）。补跑 `/sprint-selftest --capture`",
        })

    errs = [f for f in findings if f["level"] == "ERROR"]
    return {"applicable": True, "enabled": True, "reason": det["source"],
            "rule_installed": rule_installed,
            "findings": findings, "passed": not errs, **det}


def main():
    ap = argparse.ArgumentParser(description="WebMCP 启用判定 + 确定性守卫（未启用即 N/A）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--detect", action="store_true", help="只做启用判定，不跑检查")
    ap.add_argument("--install-rule", action="store_true",
                    help=runtime_text('把详规从模板位安装到 __AIDP_HOME__/rules/（幂等；未启用时拒绝）', __file__))
    ap.add_argument("--force", action="store_true", help="配合 --install-rule：未启用也强装")
    ap.add_argument("--probe-snippet", action="store_true",
                    help="打印注入页面执行的探测 JS（白名单优先 + 全局扫描兜底），供测试链路 evaluate")
    ap.add_argument("--launch-args", action="store_true",
                    help="推导本轮浏览器启动参数（含 secure context 白名单）；需配 --origin")
    ap.add_argument("--origin", action="append", default=[],
                    help="页面访问地址（可重复）；不传则自动读「测试环境与账号」。会收敛成 scheme://host[:port] 三段")
    ap.add_argument("--driver", default="cli", choices=["cli", "manual"],
                    help="cli = chrome-devtools 自起（默认）；manual = 手工起 chrome")
    ap.add_argument("--executable", default="", help="chrome 可执行路径（用于取版本号）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    try:
        if args.install_rule:
            res = install_rule(args.root, args.force)
            if args.json:
                print(json.dumps(res, ensure_ascii=False, indent=2))
            else:
                print(f"[{'OK' if res['ok'] else 'REFUSED'}] {res['detail']}")
            return 0 if res["ok"] else 1
        if args.launch_args:
            r = launch_args(args.root, args.origin, args.driver, args.executable)
            if args.json:
                print(json.dumps(r, ensure_ascii=False, indent=2))
            elif r["error"] == "webmcp-not-enabled":
                # ⛔ 这行提示必须走 **stderr**：`--launch-args` 的 stdout 会被调用方直接
                #   `$(...)` 捕获、拼进 chrome 启动命令。打到 stdout 时未启用项目拿到的
                #   不是空串而是 46 字中文 → ① 那句话被展开进三条启动命令 ② 调用方的
                #   `[ -n "$WEBMCP_FLAGS" ] && UDD_FLAG=""` 误命中，`--user-data-dir` 被清空、
                #   触发 Chrome 单例机制静默丢参。**WebMCP 默认关闭，绝大多数下游走这条路径。**
                print("[N/A] 本项目未启用 WebMCP —— 不追加任何启动参数（与本能力上线前逐字节一致）",
                      file=sys.stderr)
            elif r["error"]:
                sys.stderr.write(f"❌ 无法推导启动参数：{r['error']}\n")
            else:
                if args.driver == "cli":
                    print("chrome-devtools start " + " ".join(
                        (f'"{a}"' if a.startswith("--") and " " not in a and "=" in a else a)
                        for a in r["cli_args"]))
                else:
                    print(" ".join(r["chrome_flags"])
                          + f" --user-data-dir={r['user_data_dir']}")
            for w in r["warnings"]:
                sys.stderr.write(f"   ⚠️ {w}\n")
            return 0 if not r["error"] or r["error"] == "webmcp-not-enabled" else 2
        if args.probe_snippet:
            _r = detect_with_launch(args.root)
            print(PROBE_SNIPPET.replace(
                "%SYMBOLS%", json.dumps(_r.get("entry_symbols") or DEFAULT_ENTRY_SYMBOLS,
                                        ensure_ascii=False)))
            return 0
        res = detect_with_launch(args.root) if args.detect else run(args.root)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("passed", True) else 1

    if args.detect:
        print(f"[DETECT] WebMCP {'已启用' if res['enabled'] else '未启用'} —— {res['source']}")
        print(f"         能力入口标识符：{res['entry_symbols']}（来源：{res['symbols_source']}）")
        print("         ⚠️ 白名单只是阳性猜测——探测请用 `--probe-snippet`（白名单优先 + 全局扫描兜底）；")
        print("            白名单全 undefined **不等于**能力不存在，可能只是改了名（实测：Chrome 152 挂在 window.ModelContext）。")
        lc = res.get("launch_command") or ""
        print(f"         带参浏览器启动命令：{lc if lc else '<未登记 —— 传空并让 SKILL 引用环境文档路径，⛔ 不要自拟>'}")
        return 0
    if not res["applicable"]:
        print(f"[N/A] 本项目未启用 WebMCP（{res['reason']}）—— 本检查整体跳过，不产生任何告警。")
        return 0
    if res["passed"]:
        warns = [f for f in res["findings"] if f.get("level") == "WARN"]
        print(f"[OK] WebMCP 已启用（{res['reason']}），脚手架侧装配守卫通过（详规已安装）。"
              + (f" {len(warns)} 处 WARN。" if warns else ""))
        for f in warns:
            print(f"  · [WARN][{f['check']}] {f['detail']}")
        print(f"  代码实现合规归上游 code-verification-loop 维度 9"
              f"（entry_symbols={res['entry_symbols']}）。")
        return 0
    print(f"[FAIL] WebMCP 已启用（{res['reason']}），检出 {len(res['findings'])} 处问题：")
    for f in res["findings"]:
        print(f"  · [{f['check']}] {f['file']}")
        print(f"      {f['detail']}")
    print(runtime_text('  详规单一信源 = `__AIDP_HOME__/rules/webmcp.md`。', __file__))
    return 1


if __name__ == "__main__":
    sys.exit(main())
