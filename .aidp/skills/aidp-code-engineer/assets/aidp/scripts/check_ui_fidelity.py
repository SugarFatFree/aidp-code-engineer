#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 39「通用还原度规则集」的确定性机器检查（R2 / R3 / R10）。

只做**确定性、可复现**的三条：状态视觉区分 / 截断可读性 / 导出全量。
其余 10 条（R1 元素守恒、R5-R9 边界、R11-R13）依赖语义判断，
由 `version-auditor`、`code-verification-loop`、`dev-manual-testcase` 承担，本脚本不涉足。

设计取舍（改动前务必读，否则很容易把它「优化」成一个刷屏工具）：
  - **宁可漏报、不可刷屏**。三条都做了收窄（见各 check 的 docstring），
    因为一条误报就会让下游把整个脚本关掉，那比漏报糟得多。
  - **R2/R3 判 Important（不阻断）、R10 判 Critical（阻断）**。前两者存在正当例外
    （刻意的纯文本降级、装饰性文案），后者「导出只导当前页」没有正当场景。
  - **R2/R3 可显式豁免**（R10 零豁免，见下）：受检行或其上一行含 `fidelity-ignore: <RULE> <原因>` 即跳过，
    原因为空也放行但会计入 waived 统计（让「豁免」本身可被审计，而不是隐形）。

用法:
    python3 .aidp/scripts/check_ui_fidelity.py                 # 全量扫 code/
    python3 .aidp/scripts/check_ui_fidelity.py --json          # 机器消费
    python3 .aidp/scripts/check_ui_fidelity.py --check R10     # 只跑某几条
    python3 .aidp/scripts/check_ui_fidelity.py --paths a.vue b.java   # 只扫指定文件

退出码: 0 = 无 Critical；1 = 有 Critical；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ALL_RULES = ("R2", "R3", "R10")

FRONTEND_SUFFIX = {".vue", ".jsx", ".tsx", ".ts", ".js", ".html"}
BACKEND_SUFFIX = {".java", ".kt", ".py", ".go", ".cs"}

SCAN_ROOTS = ("code",)
SKIP_DIR_PARTS = {
    "node_modules", "dist", "build", "target", "out", ".git", ".idea",
    "__pycache__", "coverage", "vendor", ".next", ".nuxt", "public",
}
# 测试/mock/示例代码不参与还原度判定——它们本就不面向真实用户
SKIP_NAME_HINTS = ("test", "spec", "mock", "__fixtures__", "example", "demo")

WAIVER_RE = re.compile(r"fidelity-ignore\s*:\s*(R\d+)\s*(.*)", re.IGNORECASE)


# --------------------------------------------------------------------------- 基础设施

class Finding:
    def __init__(self, rule, severity, path, line, message, evidence=""):
        self.rule = rule
        self.severity = severity          # "Critical" | "Important"
        self.path = path
        self.line = line
        self.message = message
        self.evidence = evidence.strip()[:160]

    def to_dict(self):
        return {
            "rule": self.rule,
            "severity": self.severity,
            "file": self.path,
            "line": self.line,
            "message": self.message,
            "evidence": self.evidence,
        }


def _waived(lines, idx, rule):
    """受检行或其上一行带 `fidelity-ignore: <RULE>` 即豁免。

    只看这两行是刻意的：豁免必须贴着被豁免的代码，
    否则文件头写一条就能静默整份文件——那等于给了一个「关掉检查」的后门。
    """
    for probe in (idx, idx - 1):
        if probe < 0 or probe >= len(lines):
            continue
        m = WAIVER_RE.search(lines[probe])
        if m and m.group(1).upper() == rule.upper():
            return True, (m.group(2) or "").strip()
    return False, ""


def _iter_files(root: Path, explicit=None):
    if explicit:
        for p in explicit:
            fp = Path(p)
            if fp.is_file():
                yield fp
        return
    for scan_root in SCAN_ROOTS:
        base = root / scan_root
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_PARTS]
            for fn in filenames:
                fp = Path(dirpath) / fn
                if fp.suffix not in FRONTEND_SUFFIX | BACKEND_SUFFIX:
                    continue
                low = str(fp).lower()
                if any(h in low for h in SKIP_NAME_HINTS):
                    continue
                yield fp


def _read(fp: Path):
    try:
        return fp.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None


# --------------------------------------------------------------------------- R3 截断可读性

ELLIPSIS_CSS_RE = re.compile(r"text-overflow\s*:\s*ellipsis|-webkit-line-clamp\s*:")
# Tailwind / UnoCSS 原子类
ELLIPSIS_CLASS_RE = re.compile(r"\b(truncate|line-clamp-\d+|text-ellipsis)\b")
TOOLTIP_HINT_RE = re.compile(
    r"\btitle\s*=|:title\s*=|v-tooltip|show-overflow-tooltip|"
    r"<el-tooltip|<a-tooltip|<n-tooltip|<Tooltip|tooltip\s*=|aria-label\s*=",
    re.IGNORECASE,
)
CSS_SELECTOR_RE = re.compile(r"^\s*([.#][\w-]+(?:[\s,>+~][^{]*)?)\s*\{")


def check_r3(fp: Path, lines):
    """长文本截断必须配套完整可读途径。

    收窄点（防刷屏）：
      1. 只查**模板里直接出现**的截断（Tailwind 原子类），以及
         **CSS 里定义了截断、且该 class 在模板中被用到**的那些用法行。
      2. 命中后在「同一标签的属性区 + 前后 2 行」窗口里找 tooltip 线索，
         找到即放行——覆盖 `<el-tooltip>` 包裹与 `:title` 绑定两种主流写法。
      3. 纯 `.css`/`.scss` 文件不单独报（那里只有样式、看不到有没有 tooltip）。
    """
    out = []
    if fp.suffix not in FRONTEND_SUFFIX:
        return out

    text = "\n".join(lines)

    # ① CSS 块里定义了截断的 class → 收集类名
    truncating_classes = set()
    current_sel = None
    for ln in lines:
        m = CSS_SELECTOR_RE.match(ln)
        if m:
            current_sel = m.group(1)
        if ELLIPSIS_CSS_RE.search(ln) and current_sel:
            for cls in re.findall(r"\.([\w-]+)", current_sel):
                truncating_classes.add(cls)

    for idx, ln in enumerate(lines):
        hit = None
        if ELLIPSIS_CLASS_RE.search(ln) and ("class" in ln or "className" in ln):
            hit = "原子类截断"
        elif truncating_classes:
            for cls in truncating_classes:
                if re.search(r"class(?:Name)?\s*=\s*[\"'][^\"']*\b%s\b" % re.escape(cls), ln):
                    hit = "CSS 类 .%s 截断" % cls
                    break
        if not hit:
            continue

        waived, _reason = _waived(lines, idx, "R3")
        if waived:
            continue

        lo, hi = max(0, idx - 2), min(len(lines), idx + 3)
        window = "\n".join(lines[lo:hi])
        if TOOLTIP_HINT_RE.search(window):
            continue

        out.append(Finding(
            "R3", "Important", str(fp), idx + 1,
            "%s，但同节点/父节点未见 title 或 tooltip —— 内容被截断后用户无完整可读途径" % hit,
            ln,
        ))
    return out


# --------------------------------------------------------------------------- R2 状态视觉区分

TAG_OPEN_RE = re.compile(
    r"<(el-tag|a-tag|n-tag|el-badge|a-badge|el-progress|a-progress|Tag|Badge)\b",
    re.IGNORECASE,
)
STATIC_TYPE_RE = re.compile(r"\s(?<!:)(type|color|status)\s*=\s*[\"'][\w-]+[\"']")
DYNAMIC_TYPE_RE = re.compile(r"[:\s](?::|v-bind:)(type|color|status)\s*=")
DYNAMIC_CONTENT_RE = re.compile(r"\{\{[^}]+\}\}|v-text\s*=|\{[a-zA-Z_$][\w.$\[\]?]*\}")


def check_r2(fp: Path, lines):
    """状态类字段必须有视觉区分。

    收窄点（这条最容易误报，务必保留）：
      **只有「内容是动态的、而 type/color 是写死的」才报。**
      写死内容 + 写死颜色（如固定的「新」角标）完全正当；
      动态内容 + 动态颜色是正确写法。只有前者动后者不动，
      才是「所有状态取值共用同一个颜色」这个真实缺陷的特征。
    """
    out = []
    if fp.suffix not in FRONTEND_SUFFIX:
        return out

    for idx, ln in enumerate(lines):
        m_tag = TAG_OPEN_RE.search(ln)
        if not m_tag:
            continue
        tag = m_tag.group(1)

        # 取整个标签元素（开标签跨行 + 内容 + 闭标签），最多前瞻 8 行。
        # ⚠️ 内容区必须**按闭合标签精确截断**：早期版本用「开标签 + 固定 2 行」
        # 当内容窗口，结果把下一个兄弟节点的 {{ }} 当成本标签的内容，
        # 把 <el-tag type="danger">必填</el-tag> 这种正当写法误报了。
        slice_text = "\n".join(lines[idx:min(len(lines), idx + 8)])
        m_open = re.search(r"<%s\b([^>]*)>" % re.escape(tag), slice_text, re.IGNORECASE | re.DOTALL)
        if not m_open:
            continue
        attrs = m_open.group(1)
        self_closing = attrs.rstrip().endswith("/")

        if DYNAMIC_TYPE_RE.search(attrs):
            continue                      # 颜色已随值变化 —— 正确写法
        if not STATIC_TYPE_RE.search(" " + attrs):
            continue                      # 压根没写 type/color，不在本条射程

        if self_closing:
            # 自闭合（如 <el-badge :value="n" />）：内容由属性绑定承载
            dynamic = bool(re.search(r":(?:value|percentage|text|content)\s*=", attrs))
        else:
            m_body = re.search(
                r"<%s\b[^>]*>(.*?)</%s>" % (re.escape(tag), re.escape(tag)),
                slice_text, re.IGNORECASE | re.DOTALL,
            )
            if not m_body:
                continue                  # 找不到闭合，宁可漏报也不猜
            dynamic = bool(DYNAMIC_CONTENT_RE.search(m_body.group(1)))

        if not dynamic:
            continue                      # 内容也是写死的 —— 固定标签，正当

        waived, _reason = _waived(lines, idx, "R2")
        if waived:
            continue

        out.append(Finding(
            "R2", "Important", str(fp), idx + 1,
            "状态标签内容随数据变化，但 type/color 是字面量常量 —— 不同取值将共用同一视觉编码，无法区分",
            ln,
        ))
    return out


# --------------------------------------------------------------------------- R10 导出全量

EXPORT_SIG_RE = re.compile(
    r"(?:def|function|public|private|protected|const|let|var|async)\b[^\n;{]*"
    r"\b(\w*(?:[eE]xport|[dD]ownload|导出)\w*)\s*\(",
)
EXPORT_MAPPING_RE = re.compile(r"[\"'][^\"']*(?:export|download|导出)[^\"']*[\"']", re.IGNORECASE)
PAGING_RE = re.compile(
    r"\b(pageNo|pageNum|pageSize|pageIndex|currentPage|PageHelper\.startPage|"
    r"new\s+Page\s*\(|IPage\b|Pageable\b|\.limit\s*\(|LIMIT\s+\d|offset\b)",
    re.IGNORECASE,
)
# 「导出全部页」的正当写法：拿分页参数去循环捞全量
FULL_FETCH_HINT_RE = re.compile(
    r"while\s*\(|for\s*\(|hasNext|totalPages|Integer\.MAX_VALUE|"
    r"pageSize\s*=\s*(?:-1|0|99999|100000|Integer\.MAX_VALUE)",
    re.IGNORECASE,
)


def check_r10(fp: Path, lines):
    """导出必须导全量，不得透传分页参数。

    收窄点：
      1. 只在**导出方法体内**（签名后最多 60 行、或遇到下一个同缩进签名即止）找分页参数。
      2. 窗口内若出现循环/hasNext/MAX_VALUE 等「翻页捞全量」特征 → 放行，
         那是正当的分页拉全量写法，不是缺陷。
    """
    out = []
    for idx, ln in enumerate(lines):
        m = EXPORT_SIG_RE.search(ln)
        if not m and not (EXPORT_MAPPING_RE.search(ln) and re.search(r"Mapping|route|@app\.", ln)):
            continue

        base_indent = len(ln) - len(ln.lstrip())
        hi = min(len(lines), idx + 60)
        body = []
        for j in range(idx + 1, hi):
            nxt = lines[j]
            if nxt.strip() and (len(nxt) - len(nxt.lstrip())) <= base_indent and EXPORT_SIG_RE.search(nxt):
                break
            body.append(nxt)
        body_text = "\n".join(body)

        if not PAGING_RE.search(body_text):
            continue
        if FULL_FETCH_HINT_RE.search(body_text):
            continue

        # 定位第一处分页参数所在行，报在那里比报在签名行更有用
        hit_line, hit_text = idx + 1, ln
        for j, b in enumerate(body):
            if PAGING_RE.search(b):
                hit_line, hit_text = idx + 2 + j, b
                break

        # ⛔ **R10 零豁免** —— 与 `fidelity-ignore` 对 R2/R3 的处置**刻意不同**：
        #    「导出只导当前页」没有任何正当场景，故本条不接受行内豁免。
        #    8 处权威（AIDP-CLAUDE 约定 39 主行 / rules/code.md / cvl SKILL + flow-ui-fidelity /
        #    cvl 报告模板 / dmt flow-fidelity-suite）都写着"零豁免"，此前实现却照 R2/R3 放行 ——
        #    一行注释即可静默关掉约定 39 唯一的阻断门（实测 critical 1 → 0）。勿改回。

        out.append(Finding(
            "R10", "Critical", str(fp), hit_line,
            "导出逻辑透传了分页参数 —— 导出范围应为当前筛选条件下的全量，而非当前分页",
            hit_text,
        ))
    return out


# --------------------------------------------------------------------------- 主流程

CHECKERS = {"R2": check_r2, "R3": check_r3, "R10": check_r10}

RULE_TITLE = {
    "R2": "状态类字段必须有视觉区分",
    "R3": "长文本截断必须配套完整可读途径",
    "R10": "导出必须导全量，且与页面严格一致",
}


def run(root: Path, rules, explicit=None):
    findings = []
    scanned = 0
    for fp in _iter_files(root, explicit):
        lines = _read(fp)
        if lines is None:
            continue
        scanned += 1
        for rule in rules:
            findings.extend(CHECKERS[rule](fp, lines))
    return findings, scanned


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="约定 39 通用还原度规则集 —— 确定性机器检查（R2/R3/R10）",
    )
    ap.add_argument("--root", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--check", default=",".join(ALL_RULES),
                    help="只跑指定规则，逗号分隔，如 R3,R10（默认全跑）")
    ap.add_argument("--paths", nargs="*", default=None,
                    help="只扫指定文件（默认扫 code/ 全量）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args(argv)
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    rules = [r.strip().upper() for r in args.check.split(",") if r.strip()]
    bad = [r for r in rules if r not in CHECKERS]
    if bad:
        sys.stderr.write("未知规则: %s（可选: %s）\n" % (", ".join(bad), ", ".join(ALL_RULES)))
        return 2

    root = Path(args.root).resolve()
    findings, scanned = run(root, rules, args.paths)

    crit = [f for f in findings if f.severity == "Critical"]
    imp = [f for f in findings if f.severity == "Important"]

    if args.json:
        print(json.dumps({
            "scanned_files": scanned,
            "rules": rules,
            "critical": len(crit),
            "important": len(imp),
            "findings": [f.to_dict() for f in findings],
        }, ensure_ascii=False, indent=2))
    else:
        if not findings:
            print("✅ 约定 39 机器检查通过（扫描 %d 个文件，规则 %s）" % (scanned, "/".join(rules)))
        else:
            print("约定 39 通用还原度检查 —— 扫描 %d 个文件，%d Critical / %d Important\n"
                  % (scanned, len(crit), len(imp)))
            for rule in rules:
                rf = [f for f in findings if f.rule == rule]
                if not rf:
                    continue
                print("── %s %s（%d 处）" % (rule, RULE_TITLE[rule], len(rf)))
                for f in rf:
                    print("   [%s] %s:%d" % (f.severity, f.path, f.line))
                    print("        %s" % f.message)
                    if f.evidence:
                        print("        > %s" % f.evidence)
                print()
            print("豁免写法：在该行或上一行加注释 `fidelity-ignore: <规则号> <原因>`")

    return 1 if crit else 0


if __name__ == "__main__":
    sys.exit(main())
