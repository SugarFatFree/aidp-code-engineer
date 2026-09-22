#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_private_markers.py — 开源模板里的私有环境痕迹（按**模式**识别，ERROR 级）。

## 为什么需要本脚本

模板仓库会被公开分发、被任意下游复制。示例、事故叙述、占位值是最容易夹带真实环境信息的地方：
随手写的一个内网地址、一个自己机器上的数据库 MCP 服务名、一句「下游 某项目 实测事故」，
读起来都像普通示例，任何链接 / 锚点检查也都发现不了。

本脚本**只按模式识别，不内置任何真实私有名单**——名单本身写进仓库就等于再泄露一次。
项目维护者需要按具体名称扫描时，用 `--denylist <本地文件>` 传入（文件不入库）。

## 判据（任一命中 = ERROR）

| 规则 | 含义 | 合规写法 |
|------|------|---------|
| P1 内网 IPv4 | RFC 1918（10/8、172.16/12、192.168/16）、CGNAT 100.64/10、链路本地 169.254/16 | 文档示例地址段 RFC 5737：`192.0.2.x` / `198.51.100.x` / `203.0.113.x`；或 `<host>` 占位 |
| P2 内网主机名 | URL 或 `host:port` 里以 `.local` `.lan` `.internal` `.intranet` `.intra` `.corp` `.localdomain` 结尾的主机 | `example.com` / `test.example.com` |
| P3 MCP 服务名 | `mcp__<名字>__` 的名字既不是占位（含 `<` `{`），也不在公共服务白名单（`chrome-devtools*`、`chrome-<用户>` 约定、`context7`、`playwright`…）| `mcp__<db-mcp>__query` |
| P4 事故叙述点名下游项目 | 「下游 `xxx` 实测/实证/事故/build…」 | 「真实下游事故」「下游实证」 |
| P5 示例子项目名 | `<前缀>-backend` / `<前缀>-frontend` 的前缀不在示例白名单（`demo` `example` `sample` `my-app` `order-center` …）| `demo-backend` / `demo-frontend` |
| P6 本地名单 | `--denylist` 文件里的每一行（大小写不敏感的子串）| — |

## 豁免

行内写 `private-marker-ignore: <原因>`（原因必填）即豁免该行。

## 用法

    python3 AIDP_HOME/scripts/check_private_markers.py                 # 扫全仓（含脚手架 bundle）
    python3 AIDP_HOME/scripts/check_private_markers.py --json
    python3 AIDP_HOME/scripts/check_private_markers.py --denylist ~/private-words.txt
    python3 AIDP_HOME/scripts/check_private_markers.py --self-check

退出码：0 = 无命中；1 = 有命中；2 = 用法 / 读取错误。
"""
import argparse
import ipaddress
import json
import os
import re
import sys

EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)
TEXT_EXT = {".md", ".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".txt", ".tpl",
            ".html", ".css", ".toml", ".cfg", ".ini", ".sql", ".vue", ".xml", ".env", ""}
MAX_BYTES = 2 * 1024 * 1024

IGNORE_RE = re.compile(r"private-marker-ignore:\s*\S")

IPV4_RE = re.compile(r"(?<![\w.])(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(?![\w.]*\d)")
# 以 (首地址整数, 前缀长度) 声明，避免本文件自身出现点分内网地址字面量而被自己扫中
PRIVATE_NETS = [ipaddress.ip_network((a << 24 | b << 16, plen)) for a, b, plen in
                ((10, 0, 8), (172, 16, 12), (192, 168, 16), (100, 64, 10), (169, 254, 16))]

INTERNAL_TLDS = r"(?:local|lan|internal|intranet|intra|corp|localdomain)"
HOST_RE = re.compile(
    r"(?:://|@)([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\." + INTERNAL_TLDS + r")(?![A-Za-z0-9-])"
    r"|\b([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\." + INTERNAL_TLDS + r"):\d{2,5}\b")

MCP_RE = re.compile(r"mcp__([A-Za-z0-9_<>{}\-]+?)__")
MCP_PUBLIC_PREFIXES = ("chrome-", "chrome_", "plugin_chrome-devtools-mcp", "context7",
                       "plugin_context7", "playwright", "github", "filesystem", "fetch")

DOWNSTREAM_RE = re.compile(
    r"下游\s*`?([A-Za-z][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)+)`?\s*(?:项目\s*)?"
    r"(?:实测|实证|事故|根因|回流|build|复现|反馈)")

SUBPROJECT_RE = re.compile(r"(?<![\w/.-])([a-z][a-z0-9]*(?:-[a-z0-9]+)*)-(?:backend|frontend)\b")
SUBPROJECT_PREFIX_OK = {
    "demo", "example", "sample", "my", "my-app", "app", "foo", "bar", "order-center",
    "aidp", "dev", "build", "your", "project", "test", "mock",
}


def _is_private_ip(s):
    try:
        ip = ipaddress.ip_address(s)
    except ValueError:
        return False
    return any(ip in n for n in PRIVATE_NETS)


def _mcp_name_ok(name):
    if "<" in name or "{" in name:
        return True
    return name.startswith(MCP_PUBLIC_PREFIXES)


def scan_line(line, deny):
    hits = []
    for m in IPV4_RE.finditer(line):
        if _is_private_ip(m.group(1)):
            hits.append(("P1", m.group(1)))
    for m in HOST_RE.finditer(line):
        hits.append(("P2", m.group(1) or m.group(2)))
    for m in MCP_RE.finditer(line):
        if not _mcp_name_ok(m.group(1)):
            hits.append(("P3", m.group(0)))
    for m in DOWNSTREAM_RE.finditer(line):
        hits.append(("P4", m.group(0)))
    for m in SUBPROJECT_RE.finditer(line):
        if m.group(1) not in SUBPROJECT_PREFIX_OK:
            hits.append(("P5", m.group(0)))
    low = line.lower()
    for w in deny:
        if w in low:
            hits.append(("P6", "<denylist 第 %d 项>" % deny[w]))
    return hits


def iter_files(root, paths=None):
    bases = [os.path.join(root, p) for p in paths] if paths else [root]
    for base in bases:
        if os.path.isfile(base):
            yield base
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE_DIRS
                                 and not d.startswith(EXCLUDE_DIR_PREFIXES))
            for fn in sorted(filenames):
                ext = os.path.splitext(fn)[1].lower()
                if ext in TEXT_EXT or fn.startswith((".gitignore", ".env")):
                    yield os.path.join(dirpath, fn)


def load_denylist(path):
    deny = {}
    if not path:
        return deny
    with open(path, encoding="utf-8") as fh:
        for i, raw in enumerate(fh, 1):
            w = raw.strip()
            if w and not w.startswith("#"):
                deny[w.lower()] = i
    return deny


def run(root, paths=None, denylist=None):
    deny = load_denylist(denylist)
    errors, scanned = [], 0
    for p in iter_files(root, paths):
        try:
            if os.path.getsize(p) > MAX_BYTES:
                continue
            with open(p, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        rel = os.path.relpath(p, root)
        for no, line in enumerate(lines, 1):
            if IGNORE_RE.search(line):
                continue
            for rule, text in scan_line(line, deny):
                errors.append({"file": rel, "line": no, "rule": rule, "match": text})
    return {"ok": not errors, "scanned": scanned, "errors": errors}


RULE_HINT = {
    "P1": "内网 IP → 改 RFC 5737 文档地址（192.0.2.x）或 <host>",
    "P2": "内网主机名 → 改 example.com",
    "P3": "MCP 服务名 → 改占位 mcp__<name>__",
    "P4": "事故叙述点名下游项目 → 删项目名",
    "P5": "示例子项目名 → 改 demo-backend / demo-frontend",
    "P6": "命中本地名单",
}


def main():
    ap = argparse.ArgumentParser(description="开源模板私有环境痕迹检查（按模式识别）")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--path", action="append", default=None, help="只扫指定相对路径（可重复）")
    ap.add_argument("--denylist", default=os.environ.get("AIDP_PRIVATE_DENYLIST"),
                    help="本地私有名单文件（每行一个词，不入库；也可用环境变量 AIDP_PRIVATE_DENYLIST）")
    ap.add_argument("--json", action="store_true", help="机读 JSON")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__), json_out=args.json))
    if args.denylist and not os.path.isfile(args.denylist):
        print("[ERROR] denylist 文件不存在: %s" % args.denylist, file=sys.stderr)
        return 2
    try:
        res = run(args.root, args.path, args.denylist)
    except Exception as e:  # noqa: BLE001
        print("[ERROR] 检查执行失败：%s" % e, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif res["ok"]:
        print("[OK] 未发现私有环境痕迹（巡检 %d 份文本文件）" % res["scanned"])
    else:
        print("[FAIL] 检出 %d 处私有环境痕迹（巡检 %d 份）：" % (len(res["errors"]), res["scanned"]))
        for e in res["errors"]:
            print("  · %s:%d  [%s] %s — %s" % (e["file"], e["line"], e["rule"], e["match"],
                                              RULE_HINT[e["rule"]]))
        print("  豁免：行内写 `private-marker-ignore: <原因>`")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
