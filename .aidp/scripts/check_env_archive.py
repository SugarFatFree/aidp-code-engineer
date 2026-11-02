#!/usr/bin/env python3
"""check_env_archive.py — 约定 38 反向对账：环境 / 账号已写进文件，却未归档到研发自测。

约定 38 正向要求「用户给出即归档」，但只靠执行体自觉：地址或账号被顺手写进需求、计划、
记忆或方案正文，而权威文件 `docs/testing/{V}/研发自测/01_测试环境与账号.md` 里没有，
下游 `/sprint-aiauto-test` 与 `auto-test-runner` 只读权威文件，照样判「缺前置」。
本门把这种「写了但没归档」找出来。

**扫描面（人工阅读面）**：`docs/**/*.md`、`memory/**/*.md`、根级 `AGENTS.md` / `CLAUDE.md`。
⛔ 不扫代码与配置文件：约定 38.2 规定代码 / 配置里本来就有的地址以原文件为权威、不复抄进 md。
不扫 `docs/init/`（范式指导，示例地址不是环境信息）与权威文件本身；
`01_研发自测方案.md` §3 只是镜像，照常扫——只写进镜像同样算未归档。

**检出**：内网 / IP / 带端口的环境地址、JDBC 连接、带标签的账号（`账号: x 密码: y`、`账号 x/y`）。
排除：回环地址、文档保留网段（192.0.2.0/24 等）、`example.*` / `.test` 等保留域名、无端口的公网域名、
`<…>` / `{…}` 占位。行内或上一行写 `<!-- env-archive: ignore 理由 -->` 即跳过（用户说「别记」的临时地址）。

**已归档**：键（`host[:port]` 或用户名）出现在权威文件，或出现在本机凭据文件
`memory/.sprint-autopilot-credentials.json`（prod / UAT 按 38.5 存这里）。
⛔ 输出只给地址与用户名，绝不回显密码。

用法：
    python3 AIDP_HOME/scripts/check_env_archive.py [--version V0.1.0] [--json]
    python3 AIDP_HOME/scripts/check_env_archive.py --self-check     # 阳性对照自检

退出码：0 = 无未归档项；1 = 有未归档项；2 = 参数或环境错误。
"""
import argparse
import glob
import ipaddress
import json
import os
import re
import sys

ACCOUNT_DOC = "01_测试环境与账号.md"
CREDENTIALS = "memory/.sprint-autopilot-credentials.json"
IGNORE_RE = re.compile(r"<!--\s*env-archive:\s*ignore\b")
URL_RE = re.compile(r"\bhttps?://([^/\s)>\]'\"`|，。；]+)", re.I)
JDBC_RE = re.compile(r"\bjdbc:[a-z0-9]+:(?:[a-z0-9]+:)*//([^/\s;?)>\]'\"`|]+)", re.I)
BARE_HOST_PORT_RE = re.compile(r"(?<![\w./:@-])((?:\d{1,3}\.){3}\d{1,3}:\d{2,5})\b")
ACCOUNT_RES = (
    re.compile(r"(?:账号|帐号|用户名|登录名|username|user)\s*[:：=]?\s*`?([A-Za-z0-9_.@-]{2,40})`?"
               r"\s*[,，;；、]?\s*(?:密码|口令|password|pwd)\s*[:：=]?\s*`?[^\s`|，,；;]{2,}", re.I),
    re.compile(r"(?:账号|帐号|登录)\s*[:：]?\s*`?([A-Za-z][A-Za-z0-9_.@-]{1,39})\s*/\s*[^\s`/|，,；;]{3,}`?"),
)
INTERNAL_SUFFIXES = (".local", ".internal", ".lan", ".corp", ".intra", ".intranet", ".svc", ".cluster.local")
RESERVED_SUFFIXES = (".test", ".example", ".invalid", ".localhost")
RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
PLACEHOLDER_RE = re.compile(r"[<>{}]|^x+$|\*{2,}|请填写|待用户填写", re.I)


def _rel(root, path):
    return os.path.relpath(path, root).replace(os.sep, "/")


def _host_key(raw):
    """`user:pw@host:port` → (host, key)；不是环境地址返回 None。"""
    hostport = raw.rsplit("@", 1)[-1].strip().rstrip(".,:")
    if PLACEHOLDER_RE.search(hostport):
        return None
    host, _, port = hostport.partition(":")
    host = host.lower().strip("[]")
    if not host or (port and not port.isdigit()):
        return None
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        if ip.is_loopback or ip.is_unspecified or any(
                ip in ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24")):
            return None
        return host, hostport.lower()
    if host == "localhost" or host.endswith(RESERVED_SUFFIXES) or any(
            host == d or host.endswith("." + d) for d in RESERVED_DOMAINS):
        return None
    if host.endswith(INTERNAL_SUFFIXES) or "." not in host or port:
        return host, hostport.lower()
    return None


def _mentions(line):
    for rx, kind in ((URL_RE, "地址"), (JDBC_RE, "DB 连接"), (BARE_HOST_PORT_RE, "地址")):
        for m in rx.finditer(line):
            hk = _host_key(m.group(1))
            if hk:
                yield kind, hk[1]
    for rx in ACCOUNT_RES:
        for m in rx.finditer(line):
            user = m.group(1)
            if not PLACEHOLDER_RE.search(user):
                yield "账号", user


def _targets(root):
    files = [os.path.join(root, n) for n in ("AGENTS.md", "CLAUDE.md") if os.path.isfile(os.path.join(root, n))]
    for base in ("docs", "memory"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, base)):
            rel = _rel(root, dirpath)
            dirnames[:] = [d for d in dirnames if d not in ("node_modules", "__pycache__")
                           and not (rel == "docs" and d == "init")]
            files += [os.path.join(dirpath, f) for f in sorted(filenames)
                      if f.endswith(".md") and f != ACCOUNT_DOC]
    return files


def _archive_text(root, version):
    pattern = os.path.join(root, "docs", "testing", version or "*", "研发自测", ACCOUNT_DOC)
    docs = sorted(glob.glob(pattern))
    parts = []
    for p in docs + [os.path.join(root, CREDENTIALS)]:
        try:
            parts.append(open(p, encoding="utf-8").read())
        except (OSError, UnicodeDecodeError):
            continue
    return "\n".join(parts).lower(), [_rel(root, p) for p in docs]


def run(root=".", version=None):
    root = os.path.abspath(root)
    archive, docs = _archive_text(root, version)
    findings, seen, scanned = [], set(), 0
    for fp in _targets(root):
        try:
            lines = open(fp, encoding="utf-8").read().splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        scanned += 1
        rel = _rel(root, fp)
        for i, line in enumerate(lines):
            if IGNORE_RE.search(line) or (i and IGNORE_RE.search(lines[i - 1])):
                continue
            for kind, key in _mentions(line):
                if key.lower() in archive or (rel, kind, key) in seen:
                    continue
                seen.add((rel, kind, key))
                findings.append({"file": rel, "line": i + 1, "kind": kind, "key": key})
    return {"version": version, "archive_docs": docs, "scanned": scanned,
            "findings": findings, "passed": not findings}


def main():
    ap = argparse.ArgumentParser(description="约定 38 反向对账：环境 / 账号已写进文件却未归档")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", help="只认该版本的权威文件（缺省认全部版本）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        return run_self_check(os.path.basename(__file__), json_out=args.json)
    if args.version and not re.fullmatch(r"V[\w.\-]+", args.version):
        print("⛔ 非法版本号", file=sys.stderr)
        return 2
    if not os.path.isdir(args.root):
        print(f"⛔ 目录不存在：{args.root}", file=sys.stderr)
        return 2
    res = run(args.root, args.version)
    if args.json:
        print(json.dumps(res, ensure_ascii=False))
    elif res["passed"]:
        print(f"[OK] 约定 38 反向对账通过（巡检 {res['scanned']} 份 .md，无未归档的环境 / 账号）")
    else:
        target = f"docs/testing/{args.version or '{V}'}/研发自测/{ACCOUNT_DOC}"
        print(f"[FAIL] {len(res['findings'])} 处环境 / 账号已写进文件，但未归档到 {target}：")
        for f in res["findings"]:
            print(f"  · {f['file']}:{f['line']} {f['kind']} {f['key']}")
        print("  处置：按约定 38 归档（`/sprint-selftest --capture`）；prod / UAT 存本机凭据文件；"
              "确属不该记的临时地址 → 行尾 `<!-- env-archive: ignore 理由 -->`")
    return 0 if res["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
