#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""驱动能力探测(优雅降级依据)。

按被测端类型探测对应自动化驱动是否就绪,输出 available/missing + 补齐建议(hint)。
方法论层据此决定:可用→加载适配器执行;缺失→标 block(driver-missing) + 继续,不硬失败、不挂起。

探测手段仅用「命令是否存在 / npm 全局包 / 端点可达 / 本机浏览器可执行 / 读项目 .mcp.json」等
非侵入检查,不实际启动会话、不触网驱动、无副作用。

★web 端两种就绪态严格区分(勿等价互顶):
  ① 本地 chrome-devtools-cli(CLI 直调、同机、免 MCP 配置、不读 .mcp.json、驱动本机独立 Chrome 实例)。
     ★探测唯一凭据 = cli 命令真正可执行;命令名是 `chrome-devtools`(`chrome-devtools-cli` 只是技能名、非命令/二进制,
     仅作 legacy 兜底)。「npm 包 chrome-devtools-mcp 已装」≠「命令能跑」(bin 可能未提供/未链进 PATH),
     npm 探测独立成信号(npm_pkg_available),不并入 cli_ok。
  ② MCP 远程变体 chrome-devtools:注册须服务名 chrome-<git_user>(取自 git user.name)+ --scope project
     写项目根 .mcp.json,工具名 mcp__chrome-<git_user>__*;通用名 chrome-devtools(无用户后缀)=远程变体,
     驱动共享/远程 Chrome。探测:项目根 .mcp.json 是否注册了 chrome-* 服务(运行时是否已挂载脚本探不到)。
  硬边界:两者**不是等价次选**。同机 + 无 .mcp.json 远程注册时,**不得把 MCP 变体作为 CLI 缺失时的
  自动次选/降级目标**——「仅 MCP 变体可用、CLI 缺失」标记为**需人工确认(非自动可用)**,应先装 CLI 或
  确认确为异机远程,勿用 MCP 变体静默顶替(否则会连到共享/他人 Chrome,list_pages 混入他人标签、串测污染)。

web 探测仍按「任一即可用」放宽避免误杀主场景(npm 包 / 本机 Chrome / .mcp.json 注册,任一命中即视 web 有路可跑),
但 MCP 插件工具属运行时能力、脚本探不到,web 全落空也不得据此 npm 空探测直接 block web
(见 execution-methodology.md 第零步「探测→block」)。

仅标准库,支持 --json。退出码:0 = 目标端至少一个驱动可用, 1 = 目标端全部驱动缺失, 2 = 输入错误。

示例: python3 detect_drivers.py web --json      # 探测 web 端
      python3 detect_drivers.py all --json      # 探测全部端
"""
import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

# web 端本机浏览器可执行候选(shutil.which 命中任一即视本机有浏览器)
CHROME_EXECUTABLES = [
    'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
    'chrome', 'msedge', 'microsoft-edge',
]
# macOS 常见浏览器绝对路径(which 探不到 .app 内可执行时兜底)
CHROME_MAC_PATHS = [
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
]

# web 端 MCP 插件工具说明(本脚本无法探测的运行时能力)
WEB_MCP_HINT = (
    'chrome-devtools MCP 变体属运行时能力,是否已挂载本脚本无法探测;'
    '若会话中已挂载该 MCP 工具(mcp__chrome-<git_user>__*)则该变体可用'
)

# 同机场景硬边界建议(CLI 与 MCP 变体不等价互顶)
WEB_CLI_MCP_BOUNDARY = (
    '同机场景应使用本地 chrome-devtools-cli(CLI 直调、驱动本机独立 Chrome 实例),'
    '勿用 chrome-devtools MCP 变体顶替:MCP 变体驱动共享/远程 Chrome,同机误用会连错实例、'
    '混入他人标签页导致串测污染。仅确为「异机 + 已在项目 .mcp.json 注册 chrome-<git_user> + 端点写入」'
    '才用 MCP 变体;「仅 MCP 变体可用、CLI 缺失」须人工确认(非自动可用)。'
)

# 各端候选驱动:name + 探测方式(web 端走专用 _detect_web,不用此表)
# probe: ('cmd', 可执行名) / ('npm', 包名) / ('port', host, port) / ('pip', 模块名) / ('browser',)
DRIVERS = {
    'web': [],  # 占位:web 走 _detect_web();保留键以便 choices 与 all 遍历
    'miniprogram': [
        {'name': 'miniprogram-automator', 'probe': ('npm', 'miniprogram-automator'),
         'hint': 'npm i -g miniprogram-automator;并在微信开发者工具开启自动化端口'},
    ],
    'mobile': [
        {'name': 'appium', 'probe': ('cmd', 'appium'),
         'hint': 'npm i -g appium && appium driver install uiautomator2 xcuitest'},
        {'name': 'appium-server', 'probe': ('port', '127.0.0.1', 4723),
         'hint': '启动 appium server(默认 4723 端口)'},
    ],
    'desktop': [
        {'name': 'playwright-electron', 'probe': ('npm', 'playwright'),
         'hint': 'npm i -g playwright(Electron 应用需开调试端口)'},
        {'name': 'winappdriver', 'probe': ('port', '127.0.0.1', 4723),
         'hint': '启动 WinAppDriver 服务(Windows)'},
    ],
}


def _probe_browser():
    """本机是否装有 Chrome/Chromium 可执行(which + macOS 常见绝对路径)。"""
    for exe in CHROME_EXECUTABLES:
        if shutil.which(exe) is not None:
            return True
    for p in CHROME_MAC_PATHS:
        if os.path.exists(p):
            return True
    return False


def _find_mcp_chrome_servers(start=None):
    """从当前目录向上查项目根 .mcp.json,读取其中注册的 chrome 系 MCP 服务名。

    纯本地文件读取,无副作用(不启动 MCP、不触网)。MCP 远程变体注册须服务名 chrome-<git_user>
    + --scope project 写项目根 .mcp.json。返回 (mcp_json_path 或 None, [chrome 系服务名])。
    """
    try:
        d = Path(start or os.getcwd()).resolve()
    except OSError:
        return None, []
    for cur in [d, *d.parents]:
        f = cur / '.mcp.json'
        if f.is_file():
            try:
                data = json.loads(f.read_text(encoding='utf-8', errors='replace'))
            except (ValueError, OSError):
                return str(f), []
            servers = {}
            if isinstance(data, dict):
                servers = data.get('mcpServers') or data.get('mcp_servers') or {}
            names = list(servers.keys()) if isinstance(servers, dict) else []
            chrome = [n for n in names if isinstance(n, str) and re.match(r'chrome[-_]', n)]
            return str(f), chrome
    return None, []


def _probe(spec):
    kind = spec[0]
    try:
        if kind == 'cmd':
            return shutil.which(spec[1]) is not None
        if kind == 'browser':
            return _probe_browser()
        if kind == 'npm':
            r = subprocess.run(['npm', 'ls', '-g', spec[1]],
                               capture_output=True, text=True, timeout=15)
            return spec[1] in (r.stdout or '')
        if kind == 'pip':
            r = subprocess.run([sys.executable, '-c', f'import {spec[1]}'],
                               capture_output=True, timeout=10)
            return r.returncode == 0
        if kind == 'port':
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1.5)
                return s.connect_ex((spec[1], spec[2])) == 0
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return False
    return False


def _cli_ok():
    """本地 CLI 是否真正可执行(唯一凭据)。

    ★命令名是 `chrome-devtools`(`npm i chrome-devtools-mcp@latest -g` 装出来的 bin,
    自检 `chrome-devtools status`,用法 `chrome-devtools <tool>` 如 `chrome-devtools list_pages`)。
    `chrome-devtools-cli` 只是 chrome-devtools-mcp 插件里的**技能名**、**不是命令/二进制**,仅作 legacy 兜底探测。
    「npm 包已装」≠「命令能跑」(该包版本可能不提供 bin / bin 未链进 PATH),故不能用「npm 包在」等价判 cli 可用。
    """
    for name in ('chrome-devtools', 'chrome-devtools-cli'):
        if shutil.which(name):
            return True
    for name in ('chrome-devtools', 'chrome-devtools-cli'):
        try:
            if subprocess.run(['npx', '--no-install', name, '--version'],
                              capture_output=True, timeout=20).returncode == 0:
                return True
        except Exception:
            pass
    return False


WEBMCP_MIN_VERSION = '1.8.0'


def _parse_version(text):
    """从任意文本里取第一个 `数字.数字[.数字…][-预发布后缀]`。取不到返回 None(绝不臆造)。

    ★预发布后缀必须一起取:剥掉它会把 `1.8.0-beta.1` 读成 `1.8.0` → 判达标 → **假绿**
    (min 版本的预发布并不含该能力)。见 `_version_ge` 的预发布规则。

    ★前界用 `(?<![\\w.])v?` 而**不是** `\\b`:`\\b` 在 `v1.8.0` 的 "1" 前不成立(v 与 1 都是
    词字符),正则会从 "8" 起匹配、把 `v1.8.0` 读成 `8.0` —— 一个凭空低两个大版本的号,
    方向恰好是"把达标读成不达标"的假红。显式允许一个前导 `v`,并禁止前面是词字符或点。
    """
    m = re.search(r'(?<![\w.])v?(\d+(?:\.\d+)+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?)', text or '')
    return m.group(1) if m else None


def _version_ge(a, b):
    """a >= b?(逐段数值比较,段数不等时短的补 0)

    ★预发布规则(只做这一条,不实现完整 semver):数值段相等时,**带预发布后缀的一方更小**
    ——`1.8.0-beta.1 < 1.8.0`。这是本处唯一会造成假绿的 semver 细节,故单独处理;
    预发布之间怎么排序不影响本判据(都只与正式的 min 版本比),不实现。
    """
    def split(v):
        core, _, pre = str(v).partition('-')
        return [int(x) for x in core.split('.') if x.isdigit()], pre

    pa, prea = split(a)
    pb, preb = split(b)
    n = max(len(pa), len(pb))
    pa += [0] * (n - len(pa))
    pb += [0] * (n - len(pb))
    if pa != pb:
        return pa > pb
    # 数值段相等:a 带预发布而 b 不带 → a 更小
    return not (prea and not preb)


def _chrome_devtools_mcp_version():
    """探 chrome-devtools-mcp 版本,返回 (version, source)。取不到 → (None, 原因)。

    ★「取不到不许编」:三条路径都拿不到就返回 None + 原因,**绝不回落成一个像样的默认值**
    (与本 skill 环境事实取证同一条纪律)。下游据此走 fail-closed:确认不了达标就不能声称可用。
    """
    try:
        r = subprocess.run(['npm', 'ls', '-g', 'chrome-devtools-mcp', '--depth=0', '--json'],
                           capture_output=True, text=True, timeout=20)
        data = json.loads(r.stdout or '{}')
        v = (data.get('dependencies') or {}).get('chrome-devtools-mcp', {}).get('version')
        if v:
            return v, 'npm ls -g --json'
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError, ValueError):
        pass
    # ⚠️ 文本回落**只认带包名的那一行**,严禁对整段 stdout 直接取版本号。
    #    实测(nvm 环境):包**未安装**时 `npm ls -g <包>` 的首行就是全局 prefix 路径,
    #    形如 `/home/x/.nvm/versions/node/v24.15.0/lib`,整段取号会把 **Node 版本 24.15.0**
    #    当成包版本 → 判「≥1.8.0 可用」→ **包根本没装却报可用**。
    #    而这条路径**恰恰只在包缺失时才会被走到**(路径 ① 拿到 version 就直接返回了),
    #    即该缺陷 100% 命中要害场景,方向正是本文件反复强调禁止的那一侧。
    try:
        r = subprocess.run(['npm', 'ls', '-g', 'chrome-devtools-mcp'],
                           capture_output=True, text=True, timeout=20)
        m = re.search(r'chrome-devtools-mcp@(\d+(?:\.\d+)+(?:-[0-9A-Za-z][0-9A-Za-z.-]*)?)',
                      r.stdout or '')
        if m:
            return m.group(1), 'npm ls -g(文本·按包名锚定)'
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        pass
    # 同理:`npx <bin> --version` 打印的是该 bin 的版本,而 bin 可能来自别的包/本地
    # node_modules。**只有输出里同时出现包名时才采信**,否则宁可返回 None 走 fail-closed。
    for name in ('chrome-devtools', 'chrome-devtools-mcp'):
        try:
            r = subprocess.run(['npx', '--no-install', name, '--version'],
                               capture_output=True, text=True, timeout=20)
            if r.returncode == 0:
                out = (r.stdout or '') + (r.stderr or '')
                if 'chrome-devtools-mcp' not in out:
                    continue
                v = _parse_version(out)
                if v:
                    return v, f'npx {name} --version(输出含包名)'
        except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
            pass
    return None, ('三条探测路径均未按包名锚定取到版本号'
                  '(npm ls --json / npm ls 文本·按包名锚定 / npx --version·输出含包名)')


def _detect_webmcp():
    """WebMCP 工具列出与调用的驱动版本校验(**仅 --webmcp 时执行**)。

    ⚠️ **不影响退出码**:退出码只表达「该端有没有驱动可用」。版本不足 ≠ 驱动缺失 —— web 端
    照样能跑非 WebMCP 用例。版本结论由 `satisfied` / `block_reason` 表达,由执行内核据此把
    **相关用例**标 block、其余照跑。把它并进退出码会让整端被误判为不可用。

    ⛔ 版本不足时**不要静默降级为「就当没有 WebMCP」** —— 那会让这一整类用例全绿式消失、
    报告看不出漏测。标 block 才会把缺口如实留在「缺陷列表 + 遗留风险」里。
    """
    version, source = _chrome_devtools_mcp_version()
    if version is None:
        satisfied = None
        reason = 'webmcp-driver-version-unknown'
        note = ('版本取不到 → **fail-closed**:确认不了达标就不能声称 WebMCP 可用,'
                '相关用例标 block(webmcp-driver-version-unknown),其余用例照跑')
    elif _version_ge(version, WEBMCP_MIN_VERSION):
        satisfied = True
        reason = None
        note = f'chrome-devtools-mcp {version} ≥ {WEBMCP_MIN_VERSION},WebMCP 工具列出与调用可用'
    else:
        satisfied = False
        reason = 'webmcp-driver-too-old'
        note = (f'chrome-devtools-mcp {version} < {WEBMCP_MIN_VERSION} → 相关用例标 '
                'block(webmcp-driver-too-old),⛔ 不要静默降级为「就当没有 WebMCP」')
    return {
        'required_min': WEBMCP_MIN_VERSION,
        'detected_version': version,
        'version_source': source,
        'satisfied': satisfied,
        'block_reason': reason,
        'note': note,
        'hint': 'npm i chrome-devtools-mcp@latest -g',
        'affects_exit_code': False,
    }


def _detect_web(webmcp=False):
    """web 端专用探测:严格区分「本地 chrome-devtools-cli」与「chrome-devtools MCP 远程变体」两种就绪态。

    `webmcp=True`(调用方传入 `webmcp_enabled: true` 时才给)才额外做 WebMCP 驱动版本校验并
    在结果里加 `webmcp` 段;否则**结果里完全没有这个字段**(不占位、不留空)。
    """
    # ① 本地 CLI 直调:cli 命令(chrome-devtools)真正可执行才算 CLI 就绪——四信号分离,cli_ok 只认命令能跑
    cli_ok = _cli_ok()
    # npm 全局包仅代表「远程 MCP 能力可安装/在场」,独立信号、不并入 cli_ok(包在 ≠ 命令能跑)
    npm_pkg_ok = _probe(('npm', 'chrome-devtools-mcp'))
    # ② MCP 远程变体:项目根 .mcp.json 是否注册 chrome-* 服务(运行时挂载与否脚本不可知)
    mcp_path, chrome_servers = _find_mcp_chrome_servers()
    mcp_registered = bool(chrome_servers)
    # 其它可跑路径
    browser_ok = _probe_browser()
    pw_ok = _probe(('npm', 'playwright'))

    # 「仅 MCP 变体注册可用、本地 CLI 缺失」→ 需人工确认(非自动可用),勿用 MCP 变体顶替 CLI
    mcp_only = mcp_registered and not cli_ok
    manual_confirm_required = mcp_only

    drivers = [
        {'name': 'chrome-devtools-cli', 'variant': 'local-cli', 'available': cli_ok,
         'note': ('cli 命令名是 `chrome-devtools`(自检 `chrome-devtools status`),'
                  '`chrome-devtools-cli` 只是技能名、不是命令/二进制,勿据它 `command -v` 自检误判。'),
         'hint': 'npm i chrome-devtools-mcp@latest -g(装出命令 `chrome-devtools`,CLI 直调、免 MCP 配置、驱动本机独立 Chrome 实例);若已装但探测为缺,多为 npm 全局 bin 未在 PATH,修好 PATH 即回落 cli'},
        {'name': 'chrome-devtools', 'variant': 'mcp-remote', 'available': mcp_registered,
         'manual_confirm': mcp_only,
         'note': ('MCP 远程变体:驱动共享/远程 Chrome。同机误用会连错实例、混入他人标签页。'
                  + ('本机已注册 chrome 系 MCP 服务(' + ','.join(chrome_servers) + ')但本地 CLI 缺失 → '
                     '需人工确认:同机应装 CLI,勿用 MCP 变体顶替;仅异机远程才用本变体。'
                     if mcp_only else
                     '仅确为异机 + 已在项目 .mcp.json 注册 chrome-<git_user> + 端点写入才用本变体。')),
         'mcp_json': mcp_path, 'chrome_servers': chrome_servers,
         'hint': '异机远程才需:注册服务名 chrome-<git_user> + --scope project 写项目根 .mcp.json'},
        {'name': 'playwright', 'variant': 'local-cli', 'available': pw_ok,
         'hint': 'npm i -g playwright && npx playwright install'},
        {'name': 'local-chrome', 'variant': 'browser', 'available': browser_ok,
         'hint': '安装本机 Chrome/Chromium(google-chrome / chromium / msedge)'},
    ]
    any_ok = cli_ok or pw_ok or browser_ok or mcp_registered

    if any_ok:
        hint = WEB_MCP_HINT
    else:
        hint = (WEB_MCP_HINT +
                ';本脚本 npm/本机浏览器/.mcp.json 均未探到 → 检查是否已在 Claude Code 挂载 '
                'chrome-devtools MCP 变体,或安装本机 Chrome / npm 驱动')

    if mcp_only:
        # 有路可跑但仅 MCP 变体注册、CLI 缺失:必须人工确认,勿静默把 MCP 变体当 CLI 次选
        degrade = ('web 端仅探到 chrome-devtools MCP 远程变体、本地 CLI 缺失 → 需人工确认(非自动可用)。'
                   + WEB_CLI_MCP_BOUNDARY)
    elif not any_ok:
        degrade = ('web 端 npm/本机浏览器/.mcp.json 均未探到,但主驱动 chrome-devtools MCP 变体属'
                   '运行时能力、本脚本探不到 → 不得据此直接 block web;'
                   '仅当"MCP 变体未挂载 且 本机无 Chrome 且 无 npm/CLI 驱动"三者皆空时才 block web。'
                   + WEB_CLI_MCP_BOUNDARY)
    else:
        # 本地 CLI(或 playwright/本机 Chrome)可用:同机首选本地 CLI,勿被 MCP 变体顶替
        degrade = WEB_CLI_MCP_BOUNDARY

    rep = {
        'client': 'web',
        'available': any_ok,
        'drivers': drivers,
        'local_cli_available': cli_ok,
        'npm_pkg_available': npm_pkg_ok,
        'mcp_variant_registered': mcp_registered,
        'mcp_chrome_servers': chrome_servers,
        'manual_confirm_required': manual_confirm_required,
        'boundary_advice': WEB_CLI_MCP_BOUNDARY,
        'degrade': degrade,
        'hint': hint,
    }
    if webmcp:
        rep['webmcp'] = _detect_webmcp()
    return rep


def detect(client, webmcp=False):
    if client == 'web':
        return _detect_web(webmcp)

    drivers = DRIVERS[client]
    results = []
    for d in drivers:
        ok = _probe(d['probe'])
        results.append({'name': d['name'], 'available': ok, 'hint': d['hint']})
    any_ok = any(r['available'] for r in results)

    degrade = None
    if not any_ok:
        degrade = f'{client} 端全部驱动缺失 → 该端用例整体标 block(driver-missing),继续执行其它端'

    rep = {
        'client': client,
        'available': any_ok,
        'drivers': results,
        'degrade': degrade,
    }
    return rep


def main():
    ap = argparse.ArgumentParser(
        description='驱动能力探测(优雅降级依据):按被测端类型探测自动化驱动是否就绪,'
                    '输出可用/缺失 + 补齐建议。web 端严格区分本地 chrome-devtools-cli(CLI 直调、'
                    '同机)与 chrome-devtools MCP 远程变体(共享/远程 Chrome),两者不等价互顶;'
                    'MCP 变体属运行时能力、本脚本探不到,故 web 按 npm 包 / 本机 Chrome / .mcp.json 注册'
                    '「任一即可用」放宽。',
        epilog='示例: python3 detect_drivers.py web --json   |   python3 detect_drivers.py all --json',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('client', nargs='?', choices=list(DRIVERS) + ['all'], default='all',
                    help='被测端类型:web / miniprogram / mobile / desktop / all(默认 all)')
    ap.add_argument('--json', action='store_true', help='JSON 输出(供子 Agent 解析)')
    ap.add_argument('--webmcp', action='store_true',
                    help='额外校验 WebMCP 工具列出与调用所需的 chrome-devtools-mcp 版本'
                         f'(≥ {WEBMCP_MIN_VERSION})。**仅调用方传入 webmcp_enabled: true 时才加**;'
                         '不加时结果里完全没有 webmcp 段。⚠️ 版本结论不影响退出码')
    args = ap.parse_args()

    clients = list(DRIVERS) if args.client == 'all' else [args.client]
    # --webmcp 只对 web 端有意义:非 web 端静默无效会让人以为「校验过了」,故显式提示一句。
    if args.webmcp and 'web' not in clients:
        sys.stderr.write('⚠️  --webmcp 仅对 web 端生效,本次目标端为 %s,已忽略\n'
                         % '/'.join(clients))
    reports = [detect(c, args.webmcp) for c in clients]

    if args.json:
        print(json.dumps({'reports': reports}, ensure_ascii=False, indent=2))
    else:
        for rep in reports:
            if rep['client'] == 'web' and rep.get('manual_confirm_required'):
                flag = '⚠️ 需人工确认(仅 MCP 变体、缺本地 CLI)'
            else:
                flag = '✅ 可用' if rep['available'] else '❌ 缺失'
            print(f"[{rep['client']}] {flag}")
            for d in rep['drivers']:
                if d.get('manual_confirm'):
                    mark = '⚠️需确认'
                elif d['available']:
                    mark = '✅'
                else:
                    mark = '⚠️'
                line = f"   {mark} {d['name']}"
                if not d['available']:
                    line += f"  → {d['hint']}"
                print(line)
                if d.get('note'):
                    print(f"       说明:{d['note']}")
            if rep.get('hint'):
                print(f"   说明:{rep['hint']}")
            if rep['client'] == 'web':
                print(f"   边界:{rep.get('boundary_advice', '')}")
            w = rep.get('webmcp')
            if w:
                mark = {True: '✅', False: '❌', None: '⚠️'}[w['satisfied']]
                print(f"   WebMCP:{mark} 需 ≥{w['required_min']},实测 "
                      f"{w['detected_version'] or '未取到'}(来源:{w['version_source']})")
                print(f"       {w['note']}")
                if w['satisfied'] is not True:
                    print(f"       升级:{w['hint']}(⚠️ 不影响本命令退出码)")
            if rep['degrade']:
                print(f"   降级:{rep['degrade']}")

    # 退出码:单端时按该端;all 时全部端都缺失才 1
    if args.client == 'all':
        return 0 if any(r['available'] for r in reports) else 1
    return 0 if reports[0]['available'] else 1


if __name__ == '__main__':
    sys.exit(main())
