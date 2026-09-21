#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 40「上游/第三方接口调用日志强制规范」的确定性机器检查。

## 为什么需要本脚本

一个真实下游项目里，4 个上游客户端写出了 4 种日志规格：一个双向 `>>>`/`<<<` 带耗时、
一个**四条日志全是 error**（成功路径零日志）、一个**一行日志都没有**、其余各写各的。
后果是现场报「看不到数据」时，后台日志**无法区分**「前端没发请求 / 请求没到后端 /
后端没调上游 / 上游返回空」——四种情况的日志表现都是「什么都没有」，只能读源码反推。

正确写法当时就存在于同一个仓库里，但因为它只是"某个人写得比较好"而不是一条规则，
隔壁新写的客户端依然零日志。**这类问题靠自觉不会收敛。**

## 判定口径（宁可漏报，不可刷屏）

沿用 `check_ui_fidelity.py` 的取舍：**一条误报就会让下游把整个脚本关掉，比漏报糟得多。**
故每条都做了收窄，且**单位是「文件」而不是「行」**——这类缺陷天然是类级的
（"这个客户端有没有日志"），行级判定只会制造噪音。

| ID | severity | 判据 |
|----|----------|------|
| C1 | Critical | 文件有出站调用，但**一条日志都没有** |
| C2 | Critical | 文件有出站调用、有日志，但**全部是 warn/error**（成功路径不可见）|
| I1 | Important | 文件有出站调用、有日志，但**没有任何一条日志提到 URL**（多环境排查时第一个要确认的就是"调的哪个环境"）|
| I2 | Important | 成功路径**只有 debug/trace 没有 info**（生产默认 INFO ⇒ 等于看不到）|
| I3 | Important | 日志**实参**里出现疑似凭据标识符且未经掩码 |

### C2 为什么不是「全部 log 都在 catch 块里」

提案原判据是「log 语句全部位于 catch 内」。在真实样本上**该判据不成立**：
那个"成功路径零日志"的客户端里，有的 error 日志是**方法开头的配置守卫**、
有的在 `try` 内但不在 `catch` 内——按原判据一条都命中不了，而它恰恰是最该被抓的那个。
真正的失效特征是**级别**而非**位置**：所有日志都是 warn/error ⇒ 只有出事才出声 ⇒
成功路径不可观测。按级别判既准确、又不需要做括号配平和 catch 块边界分析（那本身就是误报源）。

## 已知盲区（刻意不做，别在这里"补全"）

- **`@FeignClient` 接口**：接口没有方法体，日志由 `feign.Logger` 全局配置承担，
  对它做 C1/C2 等于对每个 Feign 接口误报。故**整体排除**，本脚本对纯 Feign 项目无覆盖。
- **序列化后的对象**：`log.info("req={}", JSON.toJSONString(req))` 里若 `req` 含密码字段，
  静态不可判。I3 只抓直接把凭据变量当实参的情形，其余靠规则正文与 review。
- **个人信息类字段**（手机号/邮箱/身份证/银行卡）：默认**不检**。它们在正常业务日志里
  出现频度极高，默认开启会瞬间淹没真正的凭据泄漏。需要时显式加 `--pii`。

用法:
    python3 AIDP_HOME/scripts/check_upstream_call_log.py                # 全量扫 code/
    python3 AIDP_HOME/scripts/check_upstream_call_log.py --json         # 机器消费
    python3 AIDP_HOME/scripts/check_upstream_call_log.py --check C1,C2  # 只跑某几条
    python3 AIDP_HOME/scripts/check_upstream_call_log.py --paths a.java # 只扫指定文件
    python3 AIDP_HOME/scripts/check_upstream_call_log.py --pii          # 额外检个人信息字段

豁免: 受检行或其上一行（文件级检查看类声明行或文件头 30 行内）加注释
      `upstream-log-ignore: <ID> <原因>`。原因为空也放行，但计入 waived 统计。

退出码: 0 = 无 Critical；1 = 有 Critical；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ALL_CHECKS = ("C1", "C2", "I1", "I2", "I3")

CHECK_TITLE = {
    "C1": "出站调用类零日志",
    "C2": "成功路径不可见（日志全为 warn/error）",
    "I1": "日志中不含 URL",
    "I2": "成功路径只有 debug/trace",
    "I3": "疑似凭据明文入日志",
}

# 本脚本只覆盖服务端语言——出站调用的机制识别（RestTemplate/WebClient/OkHttp/SDK）
# 都是这两种语言的形态。其余语言按「技术栈门控」整体跳过，不猜。
SOURCE_SUFFIX = {".java", ".kt"}

SCAN_ROOTS = ("code",)
SKIP_DIR_PARTS = {
    "node_modules", "dist", "build", "target", "out", ".git", ".idea",
    "__pycache__", "coverage", "vendor", "generated",
}
# 只排测试源码。刻意**不**排 example/demo —— 那两个词在正常业务包名里也出现
# （如 `exampleService`），排掉会静默漏检。
TEST_PATH_PARTS = ("/src/test/", "/src/androidTest/", "/test/java/")
TEST_NAME_RE = re.compile(r"(Test|Tests|IT|TestCase)\.(java|kt)$")

WAIVER_RE = re.compile(r"upstream-log-ignore\s*:\s*(C\d+|I\d+)\s*(.*)", re.IGNORECASE)

# --------------------------------------------------------------------------- 出站调用识别
# 每条 = (机制名, 正则)。机制名用于「同文件内已挂日志拦截器」的抵扣判定：
# 拦截器只能覆盖它所属的那套 HTTP 客户端，覆盖不到 SDK 直连。
# ⚠️ 变量名一律用 `\w*` 前缀通配。真实项目里注入名千奇百怪
# （实测同一个仓库里并存 restTemplate / smsRestTemplate / aiStaffRestTemplate），
# 写死 `restTemplate` 会静默漏掉一半出站类——漏检比误报更隐蔽，因为它表现为"全绿"。
OUTBOUND_PATTERNS = [
    ("resttemplate", re.compile(
        r"\b\w*[Rr]estTemplate\s*\.\s*(?:getForObject|getForEntity|postForObject|postForEntity"
        r"|exchange|execute|put|delete|patchForObject|headForHeaders|optionsForAllow)\s*\(")),
    ("webclient", re.compile(
        r"\.\s*(?:retrieve|exchangeToMono|exchangeToFlux)\s*\("
        r"|\b\w*[Ww]ebClient\s*\.\s*(?:get|post|put|delete|patch|method)\s*\(")),
    ("jdkhttp", re.compile(r"\b\w*[Hh]ttpClient\s*\.\s*(?:send|sendAsync)\s*\(")),
    ("okhttp", re.compile(r"\.\s*newCall\s*\([\s\S]{0,120}?\)\s*\.\s*execute\s*\(|\bokhttp3\b")),
    ("apachehttp", re.compile(r"\b(?:CloseableHttpClient|HttpClients)\b|\b\w*[Hh]ttpclient\s*\.\s*execute\s*\(")),
    ("sdk", re.compile(
        r"\b\w*(?:[Mm]inioClient|[Oo]ssClient|[Ss]3Client|[Aa]mazonS3|[Cc]osClient|[Oo]bsClient)\s*\."
        r"\s*(?:putObject|getObject|removeObject|deleteObject|listObjects|copyObject"
        r"|statObject|presignedGetObject|presignedPutObject|getPresignedObjectUrl)\s*\(")),
]

# 同文件内注册了出站日志拦截器 ⇒ 该文件的 HTTP 类出站调用由拦截器统一打点，C1/C2 抵扣。
# 刻意**只看同文件**：真实样本里拦截器是内部私有类、只挂在自己那个 RestTemplate 上，
# 全局抵扣会让隔壁真正零日志的客户端被静默放过。
INTERCEPTOR_RE = re.compile(
    r"implements\s+[\w.]*ClientHttpRequestInterceptor"
    r"|\bExchangeFilterFunction\b"
    r"|extends\s+[\w.]*feign\.Logger"
    r"|\bgetInterceptors\s*\(\s*\)\s*\.\s*add\s*\(")
INTERCEPTOR_COVERS = {"resttemplate", "webclient", "okhttp", "apachehttp"}

FEIGN_RE = re.compile(r"@FeignClient\b")

LOG_RE = re.compile(r"\b(?:log|logger|LOG|LOGGER)\s*\.\s*(trace|debug|info|warn|error)\s*\(")

URL_TOKEN_RE = re.compile(
    r"\b(?:url|uri|endpoint|baseUrl|apiUrl|fullUrl|requestUrl|targetUrl|serverUrl)\b",
    re.IGNORECASE)

# 凭据类：泄漏即安全事件，默认检。
CREDENTIAL_WORDS = (
    "password", "passwd", "pwd", "secret", "appsecret", "clientsecret",
    "token", "accesstoken", "refreshtoken", "idtoken", "authorization",
    "apikey", "appkey", "privatekey", "signature", "verifycode", "smscode",
    "captcha", "credential",
)
# 个人信息类：默认不检（正常业务日志高频出现），--pii 显式开启。
PII_WORDS = ("phone", "mobile", "email", "idcard", "idno", "bankcard", "cardno")

# 出现这些即认为已掩码
MASK_RE = re.compile(r"\bmask|desensit|hide|anonym|\bsanitiz|\*{3,}", re.IGNORECASE)
# 变量名自身就表明已截断/已掩码
MASKED_NAME_RE = re.compile(r"preview|masked|abbrev|digest|fingerprint", re.IGNORECASE)


def _masked_vars(lines):
    """收集"赋值行本身就在做掩码"的变量名。

    真实反例：`String tokenPreview = token.substring(0,6) + "***" + token.substring(...)`
    随后 `log.info("... X-AUTH-TOKEN={}", tokenPreview)`——这是**正确写法**，
    但掩码发生在赋值行、不在日志行，只看日志语句必然误报成"凭据明文入日志"。
    """
    out = set()
    for ln in lines:
        if not MASK_RE.search(ln):
            continue
        m = re.search(r"\b(\w+)\s*=", ln)
        if m:
            out.add(_norm(m.group(1)))
    return out

# 「凭据上下文」方法名/类名——命中后连 code/key/pwd 这类过泛的名字也算凭据。
# 真实样本里最危险的一行是 `log.warn("...code={}", phone, code)`，变量就叫 `code`，
# 只靠标识符黑名单必然漏；而 `code` 进黑名单又会把每个上游的业务 code 全打成误报。
CRED_CONTEXT_RE = re.compile(
    r"verifycode|sendsms|smssend|captcha|password|passwd|credential|authenticat|\btoken\b|secret",
    re.IGNORECASE)
CRED_CONTEXT_WORDS = ("code", "pwd", "key")

METHOD_DECL_RE = re.compile(
    r"^\s*(?:@\w+\s*)*(?:public|private|protected|static|final|synchronized|\s)*"
    r"[\w<>\[\],.?\s]+\s+(\w+)\s*\([^;]*$")


# --------------------------------------------------------------------------- 基础设施

class Finding:
    def __init__(self, check, severity, path, line, message, evidence=""):
        self.check = check
        self.severity = severity          # "Critical" | "Important"
        self.path = path
        self.line = line
        self.message = message
        self.evidence = evidence.strip()[:160]

    def to_dict(self):
        return {
            "check": self.check,
            "severity": self.severity,
            "file": self.path,
            "line": self.line,
            "message": self.message,
            "evidence": self.evidence,
        }


def _strip_comments_keep_strings(text: str) -> str:
    """只去掉 `//` 行注释与 `/* */` 块注释，**保留字符串字面量**。

    ⛔ 为什么不能直接用 `_strip_noise`：那个函数会把字符串字面量也抹成 `""`，
    而日志解析要靠首个字符串实参（格式串）把"被打印的值"和格式串分开。

    ⛔ 为什么必须去注释：出站调用识别走的是去噪文本，日志识别此前却走**原文** ——
    于是一行 `// log.info("url={}", url);  TODO 以后再补日志` 就同时消掉 C1/C2/I1/I2 四档。
    而"注释掉的日志 / TODO 留个坑"恰恰是最常见的真实代码形态（实测复现）。

    `//` 出现在字符串里（如 `"http://x/y"`）不算注释起点，故必须按字符扫、不能用正则。
    """
    out = []
    i, n = 0, len(text)
    in_str = None
    esc = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in "\"'":
            in_str = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            i += 2
            while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                if text[i] == "\n":
                    out.append("\n")      # 保持行号对齐
                i += 1
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _strip_noise(line: str) -> str:
    """去掉行注释与字符串字面量，避免在注释/字面量里误命中出站调用。"""
    line = re.sub(r"//.*$", "", line)
    line = re.sub(r'"(?:\\.|[^"\\])*"', '""', line)
    line = re.sub(r"'(?:\\.|[^'\\])*'", "''", line)
    return line


def _waived_at(lines, idx, check):
    for probe in (idx, idx - 1):
        if 0 <= probe < len(lines):
            m = WAIVER_RE.search(lines[probe])
            if m and m.group(1).upper() == check.upper():
                return True, (m.group(2) or "").strip()
    return False, ""


def _waived_file(lines, check):
    """文件级检查的豁免：文件头 30 行内、或任意类声明行上出现即生效。"""
    head = lines[:30]
    for ln in head:
        m = WAIVER_RE.search(ln)
        if m and m.group(1).upper() == check.upper():
            return True, (m.group(2) or "").strip()
    for i, ln in enumerate(lines):
        if re.search(r"\b(class|interface|enum)\s+\w+", ln):
            ok, why = _waived_at(lines, i, check)
            if ok:
                return True, why
    return False, ""


def _balanced_args(text: str, open_idx: int) -> str:
    """从 `(` 处取到配平的 `)`，返回括号内原文（含字符串字面量）。"""
    depth = 0
    i = open_idx
    in_str = None
    esc = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
        elif ch in "\"'":
            in_str = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1:i]
        i += 1
    return text[open_idx + 1:min(len(text), open_idx + 600)]


def _split_top_level(args: str):
    """按顶层逗号切分实参。"""
    out, buf, depth, in_str, esc = [], [], 0, None, False
    for ch in args:
        if in_str:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == in_str:
                in_str = None
            continue
        if ch in "\"'":
            in_str = ch
            buf.append(ch)
        elif ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return [s.strip() for s in out if s.strip()]


class LogStmt:
    def __init__(self, level, line_no, full, args):
        self.level = level
        self.line_no = line_no
        self.full = full
        self.args = args          # 去掉首个格式串后的实参列表


def _collect_logs(text: str, lines):
    """收集全部日志语句（可跨行），拆出级别与实参。"""
    stmts = []
    for m in LOG_RE.finditer(text):
        level = m.group(1)
        open_idx = text.index("(", m.end() - 1)
        inner = _balanced_args(text, open_idx)
        parts = _split_top_level(inner)
        # 首个实参若是字符串字面量（格式串），不算"被打印的值"
        if parts and parts[0].lstrip().startswith('"'):
            value_args = parts[1:]
        else:
            value_args = parts
        line_no = text.count("\n", 0, m.start()) + 1
        stmts.append(LogStmt(level, line_no, m.group(0) + "(" + inner + ")", value_args))
    return stmts


def _enclosing_method(lines, line_no):
    for i in range(min(line_no, len(lines)) - 1, -1, -1):
        m = METHOD_DECL_RE.match(lines[i])
        if m and not re.match(r"^\s*(if|for|while|switch|catch|return|new)\b", lines[i]):
            return m.group(1)
    return ""


def _norm(tok: str) -> str:
    return re.sub(r"[^a-z0-9]", "", tok.lower())


# --------------------------------------------------------------------------- 单文件分析

def analyse_file(fp: Path, rel: str, checks, pii: bool):
    findings = []
    waived = 0
    try:
        raw = fp.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings, waived, False
    lines = raw.splitlines()

    if FEIGN_RE.search(raw):
        return findings, waived, False       # Feign 接口整体排除，见 docstring

    clean = "\n".join(_strip_noise(l) for l in lines)

    mechanisms = set()
    first_call_line = 0
    for name, pat in OUTBOUND_PATTERNS:
        m = pat.search(clean)
        if m:
            mechanisms.add(name)
            ln = clean.count("\n", 0, m.start()) + 1
            first_call_line = ln if not first_call_line else min(first_call_line, ln)
    if not mechanisms:
        return findings, waived, False

    # 同文件内挂了出站日志拦截器 ⇒ 抵扣它能覆盖的机制
    if INTERCEPTOR_RE.search(clean):
        mechanisms -= INTERCEPTOR_COVERS

    # ⛔ 必须传去注释后的文本（保留字面量）：走原文会让"注释掉的日志"骗过 C1/C2/I1/I2 四档
    logs = _collect_logs(_strip_comments_keep_strings(raw), lines)
    anchor = max(first_call_line, 1)

    def add(check, sev, line, msg, ev=""):
        if check not in checks:
            return
        ok, _why = _waived_file(lines, check)
        if ok:
            nonlocal waived
            waived += 1
            return
        findings.append(Finding(check, sev, rel, line, msg, ev))

    if mechanisms:
        levels = {s.level for s in logs}
        if not logs:
            add("C1", "Critical", anchor,
                "该类存在出站调用（%s）却没有任何日志——调用成功与否在日志里完全不可见。"
                "按约定 40 至少补「请求段（完整 URL + 入参）+ 响应段（status/业务 code + 出参 + 耗时）」。"
                % "/".join(sorted(mechanisms)))
        elif not (levels & {"info", "debug", "trace"}):
            add("C2", "Critical", sorted(logs, key=lambda s: s.line_no)[0].line_no,
                "该类的日志全部是 warn/error——只有出事才出声，成功路径不可观测。"
                "按约定 40 成功路径必须打 INFO。",
                ev="现有级别: " + "/".join(sorted(levels)))
        elif "info" not in levels:
            add("I2", "Important", sorted(logs, key=lambda s: s.line_no)[0].line_no,
                "成功路径只有 debug/trace 日志。生产默认 INFO ⇒ 等于看不到，"
                "而需要看日志的时刻永远在生产。按约定 40 成功用 INFO。",
                ev="现有级别: " + "/".join(sorted(levels)))

        if logs and not any(URL_TOKEN_RE.search(s.full) for s in logs):
            add("I1", "Important", anchor,
                "该类有出站调用与日志，但没有任何一条日志提到 URL。"
                "多环境排查时第一个要确认的就是「到底调的哪个环境的上游」，必须打完整 URL。")

    # I3 —— 逐条日志查实参
    if "I3" in checks:
        words = list(CREDENTIAL_WORDS) + (list(PII_WORDS) if pii else [])
        masked = _masked_vars(lines)
        for s in logs:
            if MASK_RE.search(s.full):
                continue
            method = _enclosing_method(lines, s.line_no)
            cred_ctx = bool(CRED_CONTEXT_RE.search(method) or CRED_CONTEXT_RE.search(rel))
            local = list(words) + (list(CRED_CONTEXT_WORDS) if cred_ctx else [])
            for arg in s.args:
                base = _norm(arg.split(".")[-1].split("(")[0])
                if not base or base in masked or MASKED_NAME_RE.search(arg):
                    continue
                hit = next((w for w in local if w == base or (len(w) > 4 and w in base)), None)
                if hit:
                    ok, _why = _waived_at(lines, s.line_no - 1, "I3")
                    if ok:
                        waived += 1
                        break
                    findings.append(Finding(
                        "I3", "Important", rel, s.line_no,
                        "日志实参 `%s` 疑似凭据，未见掩码处理。约定 40 要求保留首尾各 3 位、"
                        "中间 `***`；确为误判则加 `upstream-log-ignore: I3 <原因>`。" % arg.strip()[:40],
                        evidence=("凭据上下文方法 %s()" % method) if cred_ctx and hit in CRED_CONTEXT_WORDS else ""))
                    break

    return findings, waived, True


# --------------------------------------------------------------------------- 驱动

def _iter_files(root: Path, explicit=None):
    if explicit:
        for p in explicit:
            fp = Path(p)
            if fp.is_file() and fp.suffix in SOURCE_SUFFIX:
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
                if fp.suffix not in SOURCE_SUFFIX:
                    continue
                posix = fp.as_posix()
                if any(t in posix for t in TEST_PATH_PARTS) or TEST_NAME_RE.search(fn):
                    continue
                yield fp


def run(root: Path, checks, explicit=None, pii=False):
    findings, scanned, outbound, waived = [], 0, 0, 0
    for fp in _iter_files(root, explicit):
        scanned += 1
        try:
            rel = str(fp.resolve().relative_to(root))
        except ValueError:
            rel = str(fp)
        fs, wv, is_outbound = analyse_file(fp, rel, checks, pii)
        findings.extend(fs)
        waived += wv
        outbound += 1 if is_outbound else 0
    findings.sort(key=lambda f: (f.path, f.line, f.check))
    return findings, scanned, outbound, waived


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="约定 40 上游/第三方接口调用日志强制规范 —— 确定性机器检查",
    )
    ap.add_argument("--root", default=".", help="项目根目录（默认当前目录）")
    ap.add_argument("--check", default=",".join(ALL_CHECKS),
                    help="只跑指定检查，逗号分隔，如 C1,C2（默认全跑）")
    ap.add_argument("--paths", nargs="*", default=None, help="只扫指定文件（默认扫 code/ 全量）")
    ap.add_argument("--pii", action="store_true", help="I3 额外检个人信息字段（手机号/邮箱/证件号）")
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

    checks = [c.strip().upper() for c in args.check.split(",") if c.strip()]
    bad = [c for c in checks if c not in ALL_CHECKS]
    if bad:
        sys.stderr.write("未知检查项: %s（可选: %s）\n" % (", ".join(bad), ", ".join(ALL_CHECKS)))
        return 2

    root = Path(args.root).resolve()
    findings, scanned, outbound, waived = run(root, checks, args.paths, args.pii)
    crit = [f for f in findings if f.severity == "Critical"]
    imp = [f for f in findings if f.severity == "Important"]

    if args.json:
        print(json.dumps({
            "scanned_files": scanned,
            "outbound_files": outbound,
            "checks": checks,
            "pii": args.pii,
            "critical": len(crit),
            "important": len(imp),
            "waived": waived,
            "findings": [f.to_dict() for f in findings],
        }, ensure_ascii=False, indent=2))
    else:
        if not outbound:
            print("ℹ️ 约定 40 检查跳过：扫描 %d 个文件，未发现出站调用类（技术栈门控）" % scanned)
        elif not findings:
            print("✅ 约定 40 检查通过（%d 个文件中 %d 个含出站调用，检查项 %s）"
                  % (scanned, outbound, "/".join(checks)))
        else:
            print("约定 40 上游调用日志检查 —— %d 个文件中 %d 个含出站调用，%d Critical / %d Important\n"
                  % (scanned, outbound, len(crit), len(imp)))
            for c in checks:
                cf = [f for f in findings if f.check == c]
                if not cf:
                    continue
                print("── %s %s（%d 处）" % (c, CHECK_TITLE[c], len(cf)))
                for f in cf:
                    print("   [%s] %s:%d" % (f.severity, f.path, f.line))
                    print("        %s" % f.message)
                    if f.evidence:
                        print("        > %s" % f.evidence)
                print()
            print("豁免写法：在该行或上一行（文件级检查写在类声明行或文件头）加注释 "
                  "`upstream-log-ignore: <检查号> <原因>`")

    return 1 if crit else 0


if __name__ == "__main__":
    sys.exit(main())
