#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实现偏离设计门 —— 「设计里点名的字段/常量，代码里找不到」。

## 它堵的是哪一类失效

典型返工：详细设计 §5.3 写的是「取 `orderChannel=CHANNEL_PERSONAL` 结果里的 `userId`」，
实现却做成了「查订单用 `createBy` 反推」。这个偏离在本方代码里**完全看不出问题**——
编译过、类型检查过、单测过、界面完整、不报错、不空白。它直到上游反馈才被发现；
若上游没说，上线后该功能每一行都会是「未知员工」，**等于功能没做**。

现有各门都拦不住它：`code-verification-loop` 查的是代码**自身**的质量与契约，
`version-auditor` 查的是**文档之间**的贯通，没有任何一环去问「代码有没有按设计说的那样取数」。

## 判据（刻意只做一层：点名过的东西，代码里能不能找到）

⛔ **不做语义等价证明**——那既做不到也会误伤。本门只抽设计文档里**必然要在代码中出现**
的那类符号：常量字面量、被反引号标注的标识符、`键=值` 里的两侧。它们如果按设计实现了，
代码里就一定有；找不到，就说明要么没实现、要么换了别的做法（后者正是本门要抓的）。

「换了别的做法」不一定错——可能是设计过时。**故本门是 Important、不是 Critical**：
它要求的是**给出交代**（改代码 / 改设计 / 就地写 `design-anchor-ignore: <理由>`），
而不是"必须照设计做"。

## 噪音控制（不控就会被加豁免绕过，等于没有）

  · 通用词、HTTP 动词、SQL 关键字、常见类型名走 deny-list，不产生锚点
  · 长度 < 4 的 token 一律不取（`id` / `no` / `ok` 这类）
  · 纯中文反引号内容不取（那是文案不是标识符）
  · 行内 `design-anchor-ignore: <理由>` 显式豁免，**理由必须写**（空理由不生效）

## 退出码（★ 与全仓下发脚本同一套：`check_ui_fidelity.py` / `check_upstream_call_log.py` 同款）

  0 = 全部锚点在代码中可定位（或无设计文档 / 无代码目录 → N/A 跳过）
  1 = 存在找不到落点的锚点（Important），或路径不可读（fail-closed）
  2 = 用法错误（缺 `--version` 值等，由 argparse 直接给出）

⚠️ **这三个码的分配不是随手定的，反过来定会让本门整体静默失效。** 本门被
`code-verification-loop` 维度 13 以 `--version <值> --json` 调用，而那侧对
**exit 2 的处置是「入参/环境错 → 修正参数后重跑」**——既不计过也不计不过。
若把「有发现」放在 2 上，每一条真实的设计偏离都会被读成环境问题丢掉，
且报告里两侧都不留痕：**门在跑、恒绿、无人察觉**。故「有发现」必须落 1
（与同批下发脚本一致），2 只留给用法错。改动本文件退出码前先读这一段。

## 用法

    check_design_anchor.py --version V0.14.0 [--code code] [--root .]
                          [--design <额外设计目录>] [--json]
"""
import argparse
import json
import os
import re
import sys

CODE_EXTS = {".java", ".kt", ".ts", ".tsx", ".js", ".jsx", ".vue", ".py", ".go",
             ".cs", ".rb", ".php", ".scala", ".sql", ".xml", ".yml", ".yaml", ".json"}
SKIP_DIRS = {"node_modules", "dist", "build", "target", "out", ".git", "__pycache__",
             "vendor", "third_party", "bower_components", "site-packages", ".idea"}

# 通用词 / 语言关键字 / 框架名 —— 出现在设计文档里不代表它是本版的判据符号
DENY = {
    "GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS", "HTTP", "HTTPS",
    "SELECT", "INSERT", "UPDATE", "CREATE", "TABLE", "INDEX", "WHERE", "ORDER",
    "GROUP", "LEFT", "JOIN", "INNER", "NULL", "TRUE", "FALSE", "DEFAULT", "PRIMARY",
    "VARCHAR", "BIGINT", "DATETIME", "TIMESTAMP", "DECIMAL", "BOOLEAN", "INTEGER",
    "JSON", "YAML", "UTF", "UUID", "MD5", "SHA", "API", "URL", "URI", "DTO", "VO",
    "TODO", "FIXME", "README", "CLAUDE", "AIDP", "SPRINT", "REQ", "PRD",
    "String", "Integer", "Boolean", "List", "Map", "Set", "Long", "Double", "Object",
    "data", "type", "name", "code", "value", "list", "item", "index", "result",
    "true", "false", "null", "undefined", "string", "number", "object", "boolean",
}
_IGNORE_RE = re.compile(r"design-anchor-ignore:\s*(\S.*)$")
_CONST_RE = re.compile(r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+)\b")          # CHANNEL_PERSONAL
_TICK_RE = re.compile(r"`([^`\n]{1,80})`")                               # `orderChannel`
_IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_CAMEL_RE = re.compile(r"[a-z][A-Z]")                                    # orderChannel


def _is_anchor(tok):
    """够格当锚点：长度 ≥4、不在 deny-list、且形如常量或 camelCase 标识符。"""
    if len(tok) < 4 or tok in DENY or tok.upper() in DENY:
        return False
    if not _IDENT_RE.match(tok):
        return False
    if "_" in tok and tok.isupper():          # SCREAMING_SNAKE 常量
        return True
    return bool(_CAMEL_RE.search(tok))        # camelCase 标识符；全小写单词太泛，不取


def extract_anchors(root, design_dirs):
    """从设计文档抽锚点。返回 {token: [{file,line,text}]}，以及被豁免的 token。"""
    anchors, exempted = {}, {}
    scanned = 0
    for d in design_dirs:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS and not x.startswith(".")]
            for fn in sorted(filenames):
                if not fn.endswith(".md"):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        lines = fh.read().splitlines()
                except OSError:
                    continue
                scanned += 1
                for idx, line in enumerate(lines):
                    ig = _IGNORE_RE.search(line)
                    toks = set(_CONST_RE.findall(line))
                    for raw in _TICK_RE.findall(line):
                        # `orderChannel=CHANNEL_PERSONAL` → 两侧都取
                        for part in re.split(r"[=:：,，\s/|]+", raw):
                            part = part.strip().strip(".;")
                            if part:
                                toks.add(part)
                    for tok in toks:
                        if not _is_anchor(tok):
                            continue
                        rec = {"file": rel, "line": idx + 1, "text": line.strip()[:180]}
                        if ig:
                            exempted.setdefault(tok, []).append(
                                dict(rec, reason=ig.group(1).strip()))
                        else:
                            anchors.setdefault(tok, []).append(rec)
    # 同一 token 若在别处被显式豁免过，仍按未豁免处理——豁免是行级的，不是全局的
    return anchors, exempted, scanned


def load_code_text(root, code_dirs):
    """把代码目录读成一个大字符串做包含判定（token 级，不需要精确 AST）。"""
    chunks, files = [], 0
    for d in code_dirs:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS and not x.startswith(".")]
            for fn in sorted(filenames):
                if os.path.splitext(fn)[1] not in CODE_EXTS:
                    continue
                try:
                    with open(os.path.join(dirpath, fn), "r",
                              encoding="utf-8", errors="replace") as fh:
                        chunks.append(fh.read())
                    files += 1
                except OSError:
                    continue
    return "\n".join(chunks), files


def _name_variants(tok):
    """同一字段在设计与代码里天然长不一样，全都算命中。

    ⛔ 少了这一步，本门会产出**成片的假阳性**：设计写 `createTime`，Java 里是
    `getCreateTime()`（首字母大写、且前面紧贴 `get`），DDL/MyBatis 里是 `create_time`。
    用 `\\b<原样>\\b` 去搜，这三种写法**一个都匹配不上**——门会把实现得好好的字段
    统统报成"找不到落点"，然后被人整片加豁免绕过，等于没有这道门。
    """
    snake = re.sub(r"(?<!^)(?=[A-Z])", "_", tok).lower()
    return {tok, snake, snake.upper(), snake.replace("_", "-"), snake.replace("_", "")}


def _found_in_code(tok, code_text):
    """大小写不敏感 + 允许前接驼峰驼峰（`getCreateTime`），但**后面不许再跟标识符字符**
    ——后者是防 `userId` 被 `userIdentifier` 误判命中的那一半边界，不能一起放宽。"""
    for v in _name_variants(tok):
        if len(v) < 4:
            continue
        if re.search(r"%s(?![A-Za-z0-9_])" % re.escape(v), code_text, re.I):
            return True
    return False


def run(root, version, code_dirs, extra_design):
    design_dirs = [f"docs/design/detail/{version}"] + list(extra_design or [])
    anchors, exempted, n_docs = extract_anchors(root, design_dirs)
    if not n_docs:
        return {"applicable": False,
                "reason": f"docs/design/detail/{version}/ 无设计文档，跳过",
                "ok": True, "missing": [], "exempted": {}}
    code_text, n_code = load_code_text(root, code_dirs)
    if not n_code:
        return {"applicable": False,
                "reason": f"{'/'.join(code_dirs)} 下无可扫源码，跳过",
                "ok": True, "missing": [], "exempted": {}}
    missing = []
    for tok, hits in sorted(anchors.items()):
        if _found_in_code(tok, code_text):
            continue
        missing.append({"anchor": tok, "sites": hits[:3], "site_count": len(hits)})
    return {"applicable": True, "reason": "",
            "version": version, "design_docs": n_docs, "code_files": n_code,
            "anchors": len(anchors), "exempted_anchors": len(exempted),
            "missing": missing, "ok": not missing}


def main():
    ap = argparse.ArgumentParser(
        description="实现偏离设计门：设计里点名的字段/常量，代码里能不能找到")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", default=None, help="项目业务版本号（除 --self-check 外必填）")
    ap.add_argument("--code", action="append", default=[],
                    help="源码目录（可重复；缺省 code）")
    ap.add_argument("--design", action="append", default=[],
                    help="额外设计目录（可重复）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if not args.self_check and not args.version:
        ap.error("--version 为必填（仅 --self-check 可省略）")
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    code_dirs = args.code or ["code"]
    try:
        res = run(args.root, args.version, code_dirs, args.design)
    except OSError as exc:
        sys.stderr.write(f"❌ 无法判定：{exc}\n   fail-closed\n")
        return 1

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1

    if not res["applicable"]:
        print(f"[SKIP] {res['reason']}")
        return 0
    if res["ok"]:
        note = f" / 行内豁免 {res['exempted_anchors']} 个" if res["exempted_anchors"] else ""
        print(f"[OK] 设计点名的 {res['anchors']} 个锚点均能在代码中定位"
              f"（设计 {res['design_docs']} 份 / 源码 {res['code_files']} 份{note}）")
        return 0

    print(f"[Important] {len(res['missing'])} 个设计锚点在代码中找不到落点"
          f"（共 {res['anchors']} 个锚点 / 源码 {res['code_files']} 份）：")
    for m in res["missing"]:
        s = m["sites"][0]
        more = f"（另 {m['site_count'] - 1} 处）" if m["site_count"] > 1 else ""
        print(f"  · {m['anchor']}  ← {s['file']}:{s['line']}{more}\n    {s['text']}")
    print("  三种合法处置，任选其一并给出交代：\n"
          "    ① 实现确实偏了 → 改代码（本门的主要目标：换了数据来源却不报错的那类偏离）\n"
          "    ② 设计过时了 → 改设计（并按约定 22 级联）\n"
          "    ③ 该锚点本就不需在代码出现 → 在设计那一行写 `design-anchor-ignore: <理由>`（理由必填）\n"
          "  ⛔ 不做语义等价证明，只问「设计点名的符号代码里有没有」——"
          "换了个数据来源的偏离在本方代码里编译通过、界面完整、不报错。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
