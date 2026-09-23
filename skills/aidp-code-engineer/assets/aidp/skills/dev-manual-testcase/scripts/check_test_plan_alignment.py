#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
研发自测方案 ↔ 用例文档双向引用闭环核验
对应 dev-manual-testcase 维度 16「自测方案对齐与引用闭环」grep 化硬核回检

检测项(对照 references/quality-review-checklist.md > 维度 16):
  A. 自测方案文件存在性
     - 测试目录下必须存在 `01_研发自测方案.md`(历史旧锚 `00_研发自测方案.md` 兼容识别)
  B. 自测方案核心内容完整性
     - §1 测试目标与范围 / §2 执行方式 / §3 测试环境与准入 / §5 通过/不通过准则 /
       §8 用例索引(8.1/8.2/8.3) 必须存在;§4/§6/§7/§9/§10 推荐存在(允许"无")
  C. 双向引用闭环
     - 用例文档头部 L1 含 `自测方案来源`(markdown 链接 + 相对路径)
     - 多文件子文档头部也含 `自测方案来源`
     - 每个测试套件 L2 含 `自测方案章节`(markdown 链接 + 相对路径)
     - 反向: 用例中出现的 SUITE-NN 在方案 §8.2 都有对应行;§8.2 列出的套件在用例中可定位
  E. 环境前提就绪度(report-only,永不影响退出码)
     - §3.2 账号表须有「账号最近验证时间」列;逐账号核 `未验证` / 超期(默认 N=7 天)
     - §3.1 数据库行改填了库连接时,须带 `environment` 环境标识(dev/test/uat/staging/demo/prod)
     - 两项都只提示、不判失败:它们是「该做登录冒烟预检 / 该核对 DB 归属」的提醒,
       方案作者可能有正当理由(如本轮不跑对账),硬拦会制造噪声
  D. 默认手动执行合规
     - §2.1 出现"手动";若启用 AI 自动化, §2.2 必须含工具名 + 抽查比例
     - 严禁默认启用 AI 自动化(没有"手动"关键词 + 直接列 chrome-devtools-cli/chrome-devtools-mcp/Playwright/OpenClaw)
     - 启用 chrome-devtools(本地 chrome-devtools-cli / 远程 chrome-devtools-mcp)时,§2.2 还需含"本地模式/远程模式" + 调试端点
       + 渲染模式(无头/有头,默认无头优先)
       + 单步操作等待上限(默认每步≤3秒/首次打开≤30秒,需用户确认)
       + 关键步骤截图要求(有头/无头都要求);
       远程模式时再追加"远程 IP" + "端口转发"两个字段

退出码:
  0 = 通过
  1 = 不通过(缺自测方案 / 缺双向引用 / 章节缺失等)
  2 = 路径错(目录不存在或不是测试目录)

使用:
  python check_test_plan_alignment.py <测试目录>
  python check_test_plan_alignment.py <测试目录> --json
  python check_test_plan_alignment.py <测试目录> --strict
    # --strict: §4/§6/§7/§9/§10 也必须存在(完整 10 章节)
  python check_test_plan_alignment.py <测试目录> --plan-only
    # --plan-only: 只跑 A(方案文件存在性) + B(方案核心内容完整性),
    #   跳过 C(双向引用)/D(默认手动执行)等依赖用例文件的检查。
    #   用于第零步 0.6「出口硬自检」——用例还没生成时单验方案已物理落盘且章节齐全,
    #   不会因找不到用例文件而误报失败。
    #   方案缺失 → 退出码 1;方案存在且关键章节齐全 → 退出码 0。
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================
# 自测方案文件名识别
# ============================================================
# AIDP 范式: 方案为 01_研发自测方案.md;历史旧锚 00_研发自测方案.md 兼容识别
TEST_PLAN_FILE_RE = re.compile(r"^(?:00|01)_研发自测方案\.md$")

# 用例文件识别(排除索引/自测方案/待澄清/跨系统)
# 覆盖: 02_全量自测用例.md / 02_增量自测用例.md(单文件默认命名,带 NN_ 前缀,可带后缀)
#       全量自测用例.md / 增量自测用例.md(旧版无前缀命名,向后兼容)
#       02_自测用例-总览.md / 03_{模块}-自测用例.md / 04_订单管理用例.md(多文件命名,补充用例文档可省"自测"二字)
CASE_FILE_PATTERNS = [
    re.compile(r"^\d{2}_.*用例.*\.md$"),  # 含"用例"即视为用例文件;索引/方案/待澄清/跨系统均不含"用例",不会误匹配
    re.compile(r"^全量自测用例(?:[-_].+)?\.md$"),
    re.compile(r"^增量自测用例(?:[-_].+)?\.md$"),
]
EXCLUDE_FILE_PATTERNS = [
    re.compile(r"^00_索引"),               # 00_索引.md(专职索引,AIDP 范式)
    re.compile(r"^(?:00|01)_研发自测方案"),  # 01_研发自测方案.md(新)/ 00_(历史旧锚)
    re.compile(r"^9[89]_"),  # 99_待澄清 / 98_跨系统
]

# ============================================================
# 章节识别
# ============================================================
# 自测方案的关键章节标题(允许中文一级数字 / 阿拉伯数字)
SECTION_PATTERNS = {
    "§1_测试目标与范围": re.compile(r"^##\s+(?:1\.|一、)\s*测试目标"),
    "§2_执行方式": re.compile(r"^##\s+(?:2\.|二、)\s*执行方式"),
    "§3_测试环境与准入": re.compile(r"^##\s+(?:3\.|三、)\s*测试环境"),
    "§4_执行人与时间": re.compile(r"^##\s+(?:4\.|四、)\s*执行人"),
    "§5_通过准则": re.compile(r"^##\s+(?:5\.|五、)\s*(?:通过|不通过|准则)"),
    "§6_缺陷跟踪": re.compile(r"^##\s+(?:6\.|六、)\s*缺陷"),
    "§7_风险与豁免": re.compile(r"^##\s+(?:7\.|七、)\s*风险"),
    "§8_用例索引": re.compile(r"^##\s+(?:8\.|八、)\s*用例索引"),
    "§9_测试结果汇总": re.compile(r"^##\s+(?:9\.|九、)\s*测试结果"),
    "§10_待澄清问题": re.compile(r"^##\s+(?:10\.|十、)\s*待澄清"),
}

CRITICAL_SECTIONS = {"§1_测试目标与范围", "§2_执行方式",
                     "§3_测试环境与准入", "§5_通过准则", "§8_用例索引"}

# §8 子章节
SUB_SECTIONS_8 = {
    "§8.1_用例文档清单": re.compile(r"^###\s+8\.1"),
    "§8.2_套件清单": re.compile(r"^###\s+8\.2"),
    "§8.3_关键用例索引": re.compile(r"^###\s+8\.3"),
}

# 用例 / 套件识别(套件编号允许字母/数字/连字符混合,如 SUITE-01 / SUITE-USER / SUITE-INC-01)
SUITE_HEADER_RE = re.compile(
    r"^#{2,4}\s+(?:测试)?套件\s+((?:SUITE|TS)-[A-Za-z0-9][A-Za-z0-9-]*)", re.MULTILINE
)
SUITE_ID_RE = re.compile(r"\b((?:SUITE|TS)-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\b")
TC_ID_RE = re.compile(r"\bTC-[A-Z0-9]+(?:-[A-Z0-9]+)+\b")  # 末段允许字母+数字后缀(I01/R01/P01)及纯数字(001)

# 引用关键词
TEST_PLAN_SOURCE_RE = re.compile(r"自测方案来源")
TEST_PLAN_SECTION_RE = re.compile(r"自测方案章节")

# Markdown 链接识别
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_PATH_RE = re.compile(r"^(?:https?://|/|[A-Z]:[/\\]|~/)")

# §2.1/§2.2 识别(执行方式子章节)
EXEC_MANUAL_RE = re.compile(r"手动")
EXEC_AI_TOOL_RE = re.compile(
    r"chrome[-_]devtools[-_](?:mcp|cli)|Playwright\s*MCP|OpenClaw|browser[-_]use|AI\s*浏览器自动化"
)
# AI 自动化"未启用"否定语:命中即视为该行不构成"启用"信号(避免把模板里
# "可选: AI 浏览器自动化(默认不启用)"、"本次不启用 AI 浏览器自动化"误判为已启用)。
EXEC_AI_DISABLED_RE = re.compile(
    r"不启用|未启用|未选用|不使用|未使用|不采用"
)


def ai_enabled_in(text: str) -> bool:
    """逐行判定 AI 自动化是否"被肯定地启用"。

    仅当某行肯定地提及 AI 工具 / "AI 浏览器自动化" **且该行不含否定语**时才算启用。
    这样模板里的 `### 2.2 可选: AI 浏览器自动化(默认不启用)` 标题行(含"不启用")、
    `本次不启用 AI 浏览器自动化` 说明行都被排除,避免纯手动方案被误判。
    """
    for line in text.splitlines():
        if EXEC_AI_TOOL_RE.search(line) and not EXEC_AI_DISABLED_RE.search(line):
            return True
    return False
# chrome-devtools 专项字段(启用该工具时必填):
#   本地路径走 chrome-devtools-cli(CLI 直调,免 MCP 配置·免重启),远程路径走 chrome-devtools-mcp(MCP 服务);
#   两种形态都按同一组 CDM 字段(连接模式 / 渲染模式 / 调试端点 / 等待上限 / 截图)校验。
CDM_TOOL_RE = re.compile(r"chrome[-_]devtools[-_](?:mcp|cli)", re.IGNORECASE)
CDM_MODE_RE = re.compile(r"本地模式|远程模式")
CDM_ENDPOINT_RE = re.compile(r"localhost:9222|:9222|<远程\s*IP>:9222|调试端点|调试端口")
CDM_REMOTE_IP_RE = re.compile(r"远程\s*IP|远程\s*chrome\s*所在主机")
CDM_PORT_FORWARD_RE = re.compile(r"端口转发|portproxy")
# 单步操作等待上限(超时阈值):启用 chrome-devtools-mcp 时必填,默认每步≤3秒/首次打开≤30秒,需用户确认
CDM_TIMEOUT_RE = re.compile(r"等待上限|超时阈值|操作等待|等待时长|单步.{0,6}等待")
# 渲染模式(无头/有头):启用 chrome-devtools-mcp 时必填,默认无头优先,有头仅反无头/测分辨率/无头不可用时
CDM_RENDER_RE = re.compile(r"无头|有头|headless|渲染模式")
# 关键步骤截图:启用 chrome-devtools-mcp 时必填(有头/无头都要求);专指"关键(步骤/节点/操作)…截图",
# 避免被等待上限行的"记录 URL+截图"误命中
CDM_SCREENSHOT_RE = re.compile(r"关键(?:步骤|节点|操作)[^。\n]{0,20}截图")

# §3.1 客户端类型识别(chrome-devtools-mcp 仅适用于 Web 浏览器项目)
# 命中 = Web 项目;未命中 + 命中"非 Web"关键词 = 非 Web 项目(误用 chrome-devtools-mcp)
CLIENT_WEB_RE = re.compile(
    r"Chrome|Chromium|Edge|Safari|Firefox|浏览器|Web(?:\s*网页|\s*应用|\s+后台|\s*项目)?|"
    r"uni-app\s+Web|H5|PWA|SPA|Electron.{0,20}?[调试Debug]",
    re.IGNORECASE,
)
CLIENT_NON_WEB_RE = re.compile(
    r"桌面客户端|原生\s*App|原生\s*APP|iOS\s*APP|Android\s*APP|安卓\s*APP|"
    r"小程序|微信小程序|支付宝小程序|抖音小程序|"
    r"WPF|WinForms|Qt\s*Widgets|Cocoa|"
    r"React\s*Native|Flutter|uni-app(?!\s+Web)|Electron",
    re.IGNORECASE,
)


# ============================================================
# 工具函数
# ============================================================
def is_case_file(name: str) -> bool:
    if any(p.search(name) for p in EXCLUDE_FILE_PATTERNS):
        return False
    return any(p.match(name) for p in CASE_FILE_PATTERNS)


def has_link(line: str) -> Tuple[bool, bool]:
    """返回 (有链接, 链接为相对路径)"""
    matches = MARKDOWN_LINK_RE.findall(line)
    if not matches:
        return False, False
    has_relative = all(not ABSOLUTE_PATH_RE.match(p.strip()) for p in matches)
    return True, has_relative


# ============================================================
# A 项: 自测方案文件存在性
# ============================================================
def find_test_plan(target_dir: Path) -> Optional[Path]:
    for f in sorted(target_dir.iterdir()):
        if f.is_file() and TEST_PLAN_FILE_RE.match(f.name):
            return f
    return None


# ============================================================
# B 项: 自测方案核心内容完整性
# ============================================================
def check_plan_sections(plan_text: str, strict: bool = False) -> Dict:
    found = {k: False for k in SECTION_PATTERNS}
    sub_found = {k: False for k in SUB_SECTIONS_8}
    for line in plan_text.splitlines():
        for k, pat in SECTION_PATTERNS.items():
            if pat.match(line):
                found[k] = True
        for k, pat in SUB_SECTIONS_8.items():
            if pat.match(line):
                sub_found[k] = True

    missing_critical = [k for k in CRITICAL_SECTIONS if not found[k]]
    missing_optional = [k for k in SECTION_PATTERNS if k not in CRITICAL_SECTIONS and not found[k]]
    missing_sub = [k for k in SUB_SECTIONS_8 if not sub_found[k]]

    passed = not missing_critical and not missing_sub
    if strict:
        passed = passed and not missing_optional
    return {
        "found": found,
        "sub_found": sub_found,
        "missing_critical": missing_critical,
        "missing_optional": missing_optional,
        "missing_sub": missing_sub,
        "passed": passed,
    }


# ============================================================
# C 项: 双向引用闭环
# ============================================================
def parse_case_file(path: Path) -> Dict:
    """读取用例文件,提取 L1 自测方案来源、套件 + 自测方案章节"""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # L1 头部: 取前 30 行内的 `自测方案来源`
    head = "\n".join(lines[:30])
    has_l1 = bool(TEST_PLAN_SOURCE_RE.search(head))
    has_l1_link = False
    has_l1_relative = False
    for line in lines[:30]:
        if TEST_PLAN_SOURCE_RE.search(line):
            link, rel = has_link(line)
            has_l1_link = has_l1_link or link
            has_l1_relative = has_l1_relative or rel

    # 套件: 头部 10 行内必须含 `自测方案章节`
    suites = []
    for m in SUITE_HEADER_RE.finditer(text):
        suite_id = m.group(1)
        line_no = text[:m.start()].count("\n") + 1
        head_start = line_no
        head_end = min(line_no + 10, len(lines))
        # 截止下一标题
        next_re = re.compile(r"^#{2,4}\s+")
        for j in range(head_start, head_end):
            if j < len(lines) and next_re.match(lines[j]):
                head_end = j
                break
        suite_head_lines = lines[head_start:head_end]
        suite_head = "\n".join(suite_head_lines)
        has_section = bool(TEST_PLAN_SECTION_RE.search(suite_head))
        section_link = False
        section_rel = False
        for line in suite_head_lines:
            if TEST_PLAN_SECTION_RE.search(line):
                link, rel = has_link(line)
                section_link = section_link or link
                section_rel = section_rel or rel
        suites.append({
            "id": suite_id,
            "line": line_no,
            "has_section": has_section,
            "section_link_ok": section_link and section_rel,
        })

    return {
        "file": path.name,
        "path": str(path),
        "has_l1": has_l1,
        "l1_link_ok": has_l1_link and has_l1_relative,
        "suites": suites,
    }


def parse_plan_index(plan_text: str) -> Dict:
    """从自测方案 §8 用例索引提取套件清单"""
    # 抽出 §8 ~ §9 之间的内容
    s8 = re.search(r"^##\s+(?:8\.|八、)\s*用例索引[\s\S]*?(?=^##\s+|\Z)",
                   plan_text, re.MULTILINE)
    body = s8.group(0) if s8 else ""
    suites = set()
    tcs = set()
    for m in SUITE_ID_RE.finditer(body):
        sid = m.group(1)
        # 排除 TC-ID 误匹配(TS-/SUITE- 前缀已限定,无需额外排除)
        suites.add(sid)
    for m in TC_ID_RE.finditer(body):
        tcs.add(m.group(0))
    return {"suites_in_plan": sorted(suites), "tcs_in_plan": sorted(tcs)}


# ============================================================
# E 项: 环境前提就绪度(report-only,不影响退出码)
# ============================================================
# 两个「默认被无条件信任、一旦错就确定性作废整轮」的前提——
#   G2 账号有效性:主测+备用两个管理员账号都已失效(登录被拦「您尚未关联任何企业」),
#      方案照常声明「已就绪」,直到执行期登录失败才发现,前置准备与套件编排全部作废;
#   H2 数据源环境归属:配的是非被测环境的库却拿去给被测环境做双源对账真值判断,
#      被测环境成功下单后该库始终 0 行——用错库的对账比不做对账更危险。
# 判 report-only 而非 Critical 的理由:方案作者可能有正当理由(本轮压根不跑对账 / 账号刚线下验过),
# 硬拦会制造常驻噪声,而常驻噪声会让整个硬门被无视。
ACCOUNT_FRESH_DAYS_DEFAULT = 7
# 「账号最近验证时间」列的表头识别(容忍「最近验证时间」「账号最近验证」等写法)
ACCOUNT_VERIFY_COL_RE = re.compile(r"最近验证")
DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
# 数据库行「已改填库连接」的信号:出现 host/port/库名/连接串/环境标识任一
DB_CONFIGURED_RE = re.compile(
    r"host|port|jdbc:|连接串|库名|数据源|environment|达梦|mysql|postgres|oracle", re.I)
# environment 环境标识枚举(与 auto-test-runner run-context datasource.environment 同口径)
DB_ENV_RE = re.compile(r"environment|环境标识|\b(?:dev|test|uat|prod)\b|staging|demo|预发|演示", re.I)


def _section_body(plan_text: str, pattern: str) -> str:
    """取某个 ### 小节正文(到下一个同级或更高级标题为止);取不到返回空串。"""
    m = re.search(pattern + r"[\s\S]*?(?=^###?\s+|\Z)", plan_text, re.MULTILINE)
    return m.group(0) if m else ""


def check_env_readiness(plan_text: str, fresh_days: int = ACCOUNT_FRESH_DAYS_DEFAULT,
                        today: "datetime.date | None" = None) -> Dict:
    """E 项:账号新鲜度 + DB 环境标识。**只产 notices,永不影响 passed/退出码。**"""
    today = today or datetime.date.today()
    notices: List[str] = []

    # —— G2 账号最近验证时间 ——
    acc_body = _section_body(plan_text, r"^###?\s+(?:3\.2|三·2)\s*测试账号")
    if acc_body:
        rows = [ln for ln in acc_body.splitlines() if ln.strip().startswith("|")]
        header = rows[0] if rows else ""
        if not ACCOUNT_VERIFY_COL_RE.search(header):
            notices.append(
                "§3.2 账号表缺「账号最近验证时间」列——账号失效(密码改/企业解绑/权限回收/被锁)"
                "在表里完全看不出来,会拖到执行期登录被拦才发现、整轮作废")
        else:
            cols = [c.strip() for c in header.strip("|").split("|")]
            try:
                idx = next(i for i, c in enumerate(cols) if ACCOUNT_VERIFY_COL_RE.search(c))
            except StopIteration:
                idx = -1
            # rows[1] 是 markdown 分隔行,数据行从 rows[2] 起
            for ln in rows[2:]:
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if idx < 0 or idx >= len(cells):
                    continue
                role = cells[0] if cells else "?"
                val = cells[idx].strip("`").strip()
                if val in ("—", "-", ""):
                    continue  # 无账号角色(未登录/访客),不适用
                if "失效" in val:
                    notices.append(f"§3.2 账号「{role}」已标失效({val})——依赖它的套件不得进入自动执行")
                    continue
                if "未验证" in val:
                    notices.append(f"§3.2 账号「{role}」为「未验证」——须先跑登录冒烟预检(只登录+校验角色归属)")
                    continue
                dm = DATE_RE.search(val)
                if not dm:
                    notices.append(f"§3.2 账号「{role}」的最近验证时间格式非 YYYY-MM-DD(实为 {val!r})")
                    continue
                try:
                    d = datetime.date(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)))
                except ValueError:
                    notices.append(f"§3.2 账号「{role}」的最近验证时间不是合法日期({val})")
                    continue
                age = (today - d).days
                if age > fresh_days:
                    notices.append(
                        f"§3.2 账号「{role}」最近验证于 {d}(距今 {age} 天 > {fresh_days} 天)"
                        f"——须先跑登录冒烟预检,通过后把日期刷成当天")

    # —— H2 数据库 environment ——
    env_body = _section_body(plan_text, r"^###?\s+(?:3\.1|三·1)\s*测试环境信息")
    if env_body:
        db_lines = [ln for ln in env_body.splitlines() if "数据库" in ln and ln.strip().startswith("|")]
        for ln in db_lines:
            if DB_CONFIGURED_RE.search(ln) and not DB_ENV_RE.search(ln):
                notices.append(
                    "§3.1 数据库行已改填库连接但未见 `environment` 环境标识"
                    "(dev/test/uat/staging/demo/prod)——下游拿它做双源对账真值判断前无从确认"
                    "「这是不是被测环境的库」;用错库的对账比不做对账更危险")
    return {"passed": True, "notices": notices, "fresh_days": fresh_days}


# ============================================================
# D 项: 默认手动执行合规
# ============================================================
def check_default_manual(plan_text: str) -> Dict:
    # 尝试取 §2 ~ §3 之间作为执行方式段
    s2 = re.search(r"^##\s+(?:2\.|二、)\s*执行方式[\s\S]*?(?=^##\s+|\Z)",
                   plan_text, re.MULTILINE)
    body = s2.group(0) if s2 else ""
    has_manual = bool(EXEC_MANUAL_RE.search(body))
    # AI 仅在"某行肯定地提及工具且该行不含否定语"时才视为启用——否则模板里的
    # "可选: AI 浏览器自动化(默认不启用)" / "本次不启用" 会被误判为已启用(假阳性)。
    has_ai = ai_enabled_in(body)
    has_sample_ratio = bool(re.search(r"抽查\s*比例|抽查\s*\d+\s*%|≥\s*\d+\s*%", body))
    # 启用 AI 时必须有抽查比例
    if has_ai and not has_sample_ratio:
        return {"passed": False, "has_manual": has_manual, "has_ai": has_ai,
                "msg": "§2 启用了 AI 自动化但未声明抽查比例"}
    if not has_manual:
        return {"passed": False, "has_manual": False, "has_ai": has_ai,
                "msg": "§2 执行方式未明确『手动』为默认"}
    # chrome-devtools-mcp 启用时的额外字段校验
    # 注:工具名与连接字段可能写在 §2.2 或附录(AI 执行入口),故 CDM 触发判定也走全文(plan_text),
    #     不局限于 §2 body——否则"AI 工具/字段只写在附录"时 has_ai(仅 §2)为假会把 5 组字段校验整体跳过。
    #     CDM_TOOL_RE 是 EXEC_AI_TOOL_RE 的子集,全文命中 chrome-devtools 即等同全文启用了 AI 自动化。
    #     同时按行排掉"未启用"语境:§2.2 标题"(默认不启用)" / "本次不启用"行不算启用信号,
    #     工具名只是模板可选项罗列时,不应据此触发 5 组连接字段校验(否则照搬模板的纯手动方案会被误判)。
    has_ai_anywhere = ai_enabled_in(plan_text)
    if has_ai_anywhere and CDM_TOOL_RE.search(plan_text):
        cdm_issues: List[str] = []
        if not CDM_MODE_RE.search(plan_text):
            cdm_issues.append("未标注本地模式/远程模式")
        if not CDM_RENDER_RE.search(plan_text):
            cdm_issues.append("未标注渲染模式(默认无头优先;有头仅反无头/测分辨率/无头不可用时)")
        if not CDM_ENDPOINT_RE.search(plan_text):
            cdm_issues.append("未标注 chrome 调试端点")
        if not CDM_TIMEOUT_RE.search(plan_text):
            cdm_issues.append("未标注单步操作等待上限(默认每步≤3秒/首次打开≤30秒,需用户确认)")
        if not CDM_SCREENSHOT_RE.search(plan_text):
            cdm_issues.append("未标注关键步骤截图要求(有头/无头都要求,无头下截图是唯一执行证据)")
        # 远程模式时,远程 IP 与端口转发状态必填
        if re.search(r"远程模式", plan_text):
            if not CDM_REMOTE_IP_RE.search(plan_text):
                cdm_issues.append("远程模式未标注远程 IP")
            if not CDM_PORT_FORWARD_RE.search(plan_text):
                cdm_issues.append("远程模式未标注端口转发状态")
        # 客户端类型核验:chrome-devtools-mcp 仅适用于 Web 浏览器项目
        # 检查 §3.1 测试环境与准入(扩大到全文,因为客户端字段可能在 §3.1 表格内)
        s31 = re.search(
            r"^###?\s+(?:3\.1|三·1)\s*测试环境信息[\s\S]*?(?=^###?\s+|\Z)",
            plan_text, re.MULTILINE,
        )
        client_body = s31.group(0) if s31 else plan_text
        has_web = bool(CLIENT_WEB_RE.search(client_body))
        has_non_web = bool(CLIENT_NON_WEB_RE.search(client_body))
        if has_non_web and not has_web:
            cdm_issues.append(
                "§3.1 客户端类型为非 Web(桌面/小程序/原生 APP),工具误用 chrome-devtools-mcp;"
                "应改用 Appium / 微信开发者工具 / WinAppDriver 等专用方案"
            )
        elif has_non_web and has_web:
            cdm_issues.append(
                "§3.1 同时含 Web 与非 Web 客户端,需确认 chrome-devtools-mcp 仅覆盖 Web 部分,"
                "非 Web 部分应另行声明工具"
            )
        elif not has_web and not has_non_web:
            cdm_issues.append(
                "§3.1 未声明客户端类型,启用 chrome-devtools-mcp 必须先确认客户端为 Web 浏览器"
            )
        if cdm_issues:
            return {
                "passed": False,
                "has_manual": has_manual,
                "has_ai": has_ai,
                "has_cdm": True,
                "msg": "§2.2 启用 chrome-devtools(本地 cli / 远程 mcp)但缺字段: " + "; ".join(cdm_issues),
            }
        return {"passed": True, "has_manual": True, "has_ai": True, "has_cdm": True}
    return {"passed": True, "has_manual": True, "has_ai": has_ai, "has_cdm": False}


# ============================================================
# 主流程
# ============================================================
def analyze(target: Path, strict: bool = False, plan_only: bool = False) -> Dict:
    if not target.exists() or not target.is_dir():
        return {"passed": False, "error": "PATH_NOT_DIR", "path": str(target)}

    result: Dict = {
        "target": str(target),
        "test_plan": None,
        "passed": True,
        "plan_only": plan_only,
        "violations": [],
    }

    # A: 找自测方案
    plan_path = find_test_plan(target)
    if not plan_path:
        result["passed"] = False
        result["violations"].append({
            "code": "A_PLAN_MISSING",
            "msg": f"目录 {target} 下不存在 01_研发自测方案.md(历史旧锚 00_研发自测方案.md 亦可)",
        })
        return result

    result["test_plan"] = str(plan_path)
    plan_text = plan_path.read_text(encoding="utf-8", errors="replace")

    # B: 章节完整性
    sec_check = check_plan_sections(plan_text, strict=strict)
    result["section_check"] = sec_check
    if not sec_check["passed"]:
        result["passed"] = False
        if sec_check["missing_critical"]:
            result["violations"].append({
                "code": "B_CRITICAL_SECTION_MISSING",
                "msg": f"自测方案缺关键章节: {','.join(sec_check['missing_critical'])}",
            })
        if sec_check["missing_sub"]:
            result["violations"].append({
                "code": "B_SUBSECTION_MISSING",
                "msg": f"自测方案 §8 缺子章节: {','.join(sec_check['missing_sub'])}",
            })

    # E: 环境前提就绪度(report-only,**不改 result["passed"]**、不进 violations)。
    # ⚠️ 必须放在 --plan-only 早退**之前**:E 只看方案自身、不依赖用例文件,
    # 而 SKILL「0.6 第零步出口硬自检」正是用 --plan-only 跑的——那里才是"在方案生成期
    # 就把账号失效/DB 归属问题暴露出来"最便宜的时点,放到早退之后等于该提示永远不出。
    result["env_readiness"] = check_env_readiness(plan_text)

    # --plan-only: 0.6 早期拦截只验 A(方案存在) + B(章节完整),
    # 跳过 C(双向引用)/D(默认手动执行)等依赖用例文件的检查,
    # 避免用例尚未生成时因"找不到用例文件"误报失败。
    if plan_only:
        return result

    # D: 默认手动执行(放在 C 之前,与 §2 校验同一文档)
    manual_check = check_default_manual(plan_text)
    result["manual_check"] = manual_check
    if not manual_check["passed"]:
        result["passed"] = False
        result["violations"].append({
            "code": "D_DEFAULT_MANUAL",
            "msg": manual_check["msg"],
        })

    # 索引出方案 §8 中声明的套件
    plan_index = parse_plan_index(plan_text)
    result["plan_index"] = plan_index

    # C: 用例文件双向引用
    case_files = [f for f in sorted(target.iterdir())
                  if f.is_file() and is_case_file(f.name)]
    if not case_files:
        result["violations"].append({
            "code": "C_NO_CASE_FILE",
            "msg": "目录下未发现用例文件(02_全量自测用例.md/02_增量自测用例.md/02_自测用例-总览.md)",
        })
        result["passed"] = False
        return result

    case_results = []
    all_suites_in_cases = set()
    for f in case_files:
        cr = parse_case_file(f)
        case_results.append(cr)
        for s in cr["suites"]:
            all_suites_in_cases.add(s["id"])

        # L1 必填
        if not cr["has_l1"]:
            result["passed"] = False
            result["violations"].append({
                "code": "C_L1_MISSING",
                "file": cr["file"],
                "msg": f"{cr['file']} 头部缺 `自测方案来源` L1 引用",
            })
        elif not cr["l1_link_ok"]:
            result["passed"] = False
            result["violations"].append({
                "code": "C_L1_LINK",
                "file": cr["file"],
                "msg": f"{cr['file']} `自测方案来源` 缺 markdown 链接 / 相对路径",
            })

        # L2 必填
        for s in cr["suites"]:
            if not s["has_section"]:
                result["passed"] = False
                result["violations"].append({
                    "code": "C_L2_MISSING",
                    "file": cr["file"],
                    "suite": s["id"],
                    "line": s["line"],
                    "msg": f"{cr['file']} {s['id']} 头部缺 `自测方案章节` L2 引用",
                })
            elif not s["section_link_ok"]:
                result["passed"] = False
                result["violations"].append({
                    "code": "C_L2_LINK",
                    "file": cr["file"],
                    "suite": s["id"],
                    "line": s["line"],
                    "msg": f"{cr['file']} {s['id']} `自测方案章节` 缺 markdown 链接 / 相对路径",
                })

    result["case_files"] = case_results

    # 反向核验: 方案 §8.2 列出的套件 vs 用例文档真实套件
    plan_suites = set(plan_index["suites_in_plan"])
    case_suites = all_suites_in_cases
    missing_in_plan = case_suites - plan_suites
    extra_in_plan = plan_suites - case_suites
    if missing_in_plan:
        result["passed"] = False
        result["violations"].append({
            "code": "C_PLAN_INDEX_INCOMPLETE",
            "msg": f"用例中出现的套件在方案 §8.2 缺失: {sorted(missing_in_plan)}",
        })
    if extra_in_plan:
        result["passed"] = False
        result["violations"].append({
            "code": "C_PLAN_INDEX_PHANTOM",
            "msg": f"方案 §8.2 列出但用例中不存在的套件: {sorted(extra_in_plan)}",
        })

    return result


def print_human(result: Dict, verbose: bool) -> None:
    print(f"扫描目录: {result['target']}")
    if result.get("test_plan"):
        print(f"自测方案: {result['test_plan']}")
    else:
        print("❌ 未找到自测方案文件 (01_研发自测方案.md,历史旧锚 00_研发自测方案.md 亦可)")
        return

    sec = result.get("section_check") or {}
    if sec:
        print("\n章节完整性:")
        for k, ok in sec["found"].items():
            mark = "✅" if ok else ("❌" if k.replace("§", "") in {
                s.replace("§", "") for s in CRITICAL_SECTIONS
            } else "⚠️ ")
            print(f"  {mark} {k}")
        if sec["missing_sub"]:
            print(f"  ❌ §8 缺子章节: {','.join(sec['missing_sub'])}")

    manual = result.get("manual_check") or {}
    if manual:
        mark = "✅" if manual.get("passed") else "❌"
        print(f"\n默认手动执行: {mark} (有 AI: {manual.get('has_ai', False)})")
        if not manual.get("passed"):
            print(f"  {manual.get('msg', '')}")

    env = result.get("env_readiness") or {}
    notices = env.get("notices") or []
    if notices:
        print(f"\nℹ️  环境前提提示 {len(notices)} 条(report-only,不影响判定与退出码):")
        for n in notices:
            print(f"  - {n}")

    print(f"\n双向引用违规: {len(result.get('violations', []))} 处")
    if result.get("violations"):
        for v in result["violations"][:20]:
            file_part = f" {v['file']}" if v.get("file") else ""
            line_part = f":L{v['line']}" if v.get("line") else ""
            print(f"  ❌ [{v['code']}]{file_part}{line_part}  {v['msg']}")
        if len(result["violations"]) > 20:
            print(f"  ... 另 {len(result['violations']) - 20} 处")

    print()
    if result.get("plan_only"):
        if result["passed"]:
            print("✅ 0.6 出口硬自检通过: 自测方案已物理落盘 + 关键章节齐全(A+B)")
            print("   (--plan-only 已跳过 C 双向引用 / D 默认手动执行,用例生成后请去掉该参数重跑完整维度 16)")
        else:
            print("❌ 0.6 出口硬自检不通过: 方案缺失或关键章节不全,不得进入用例生成")
            print("   - A 缺方案 → 创建 01_研发自测方案.md (assets/test-plan-template.md)")
            print("   - B 缺章节 → 按 10 章节模板补全 §1/§2/§3/§5/§8")
        return
    if result["passed"]:
        print("✅ 维度 16 通过: 自测方案 + 双向引用 + 默认手动执行 全部合规")
    else:
        print("❌ 维度 16 不通过: 修复以上违规后重跑")
        print("   修复方法:")
        print("   - A 缺方案 → 创建 01_研发自测方案.md (assets/test-plan-template.md)")
        print("   - B 缺章节 → 按 10 章节模板补全")
        print("   - C 缺 L1/L2 → 用例主/子文档头部补 `自测方案来源:` 行,套件头部补 `自测方案章节:` 行")
        print("   - D §2 → 明确『手动』,启用 AI 时声明抽查比例")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="研发自测方案 ↔ 用例文档双向引用闭环核验 (维度 16)"
    )
    ap.add_argument("target", help="测试文档目录(含 01_研发自测方案.md)")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--strict", action="store_true",
                    help="严格模式: §4/§6/§7/§9/§10 也必须存在")
    ap.add_argument("--plan-only", action="store_true",
                    help="只验 A(方案存在)+B(章节完整),跳过 C/D(依赖用例文件),用于 0.6 早期拦截")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    target = Path(args.target)
    if not target.exists():
        print(f"❌ 路径不存在: {target}", file=sys.stderr)
        return 2
    if not target.is_dir():
        print(f"❌ 不是目录: {target}", file=sys.stderr)
        return 2

    result = analyze(target, strict=args.strict, plan_only=args.plan_only)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_human(result, args.verbose)

    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
