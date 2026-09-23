#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_comment_ratio.py — 约定 17 的**反向**门：注释写太多同样是缺陷。

## 它补的缺口

约定 17 已经把注释分了 A/B/C 三档，`rules/code.md` 里也明写
「⛔ 禁止为满足覆盖率而写同义反复的注释……宁可不写」，甚至承认
「生成 5000 行文本的耗时是 1500 行的三倍多」。

**但回检只有一个方向**：`code-verification-loop`「注释完备性」检的是**覆盖率不足**。
**没有任何机器门检查"是不是写太多了"** ⇒ 过度注释**零成本、零反馈信号**，
而分档规则因此只在"写少了"那一侧真正生效。
下游实证：新增的 `.vue` / `.java` 文件普遍是「20 行注释 + 15 行代码」。

## 判据

`注释行 / 有效代码行 > 阈值（默认 1.0）` **且** 该文件不含 A 档特征 → **Important**。

**A 档特征**（命中任一即豁免——那些地方本就该写足）：判据 / 口径 / 状态机 / fail-closed /
并发 / 事务 / 安全 / 鉴权 / 幂等 / 重试 / 死锁 / 时序 / 精度 / 单位 / 脱敏。

⚠️ **能力边界（先说清楚它做不到什么）**：
- 它数的是**行数比**，判不出"这句注释有没有价值"。所以只报 Important、⛔ 不阻断；
- 字符串里出现 `//` 之类会被误当注释（不做完整词法分析）。误判方向是**多报**，
  可用 `comment-ratio-ignore: <原因>` 就地豁免（原因必填 —— 不写原因的豁免等于没有豁免）；
- **⛔ 它不是"少写注释"的许可**：约定 17 的 A 档该写多少还写多少，本门只砍 B/C 档的同义反复。

退出码：0 = 无超标；1 = 有 Important；2 = 用法/路径错。
"""
import argparse
import json
import os
import re
import sys

LANG = {
    ".java": ("//", "/*", "*/"), ".ts": ("//", "/*", "*/"), ".tsx": ("//", "/*", "*/"),
    ".js": ("//", "/*", "*/"), ".jsx": ("//", "/*", "*/"), ".vue": ("//", "/*", "*/"),
    ".go": ("//", "/*", "*/"), ".kt": ("//", "/*", "*/"),
    ".py": ("#", None, None), ".sh": ("#", None, None),
}
SKIP_DIRS = {"node_modules", "dist", "build", "target", "coverage", ".git", "__pycache__", "vendor"}
# A 档特征：这些地方本就该把"为什么"写足，⛔ 不该被本门打扰
A_TIER_RE = re.compile(
    r"判据|口径|状态机|fail-closed|failclosed|并发|事务|幂等|重试|死锁|时序|精度|单位|脱敏"
    r"|安全|鉴权|权限|竞态|race|锁|回滚|补偿", re.I)
IGNORE_RE = re.compile(r"comment-ratio-ignore\s*[:：]\s*(\S.*)")
# ★ 契约型注释：JSDoc / TSDoc 的 `@typedef` `@property` `@param` `@returns` 等
#   —— 这类文件里**注释就是内容本身**（类型声明 / 对外 API 契约），行数比天然 > 1，
#   判它超标是把「文档写得好」当成缺陷。判据取"标签密度"而非文件名：
#   文件名可以叫任何东西，而带 @ 标签的结构化注释是可确定性识别的。
DOC_TAG_RE = re.compile(r"^\s*\*?\s*@(typedef|property|param|returns?|type|callback|template|interface)\b")
# 类型声明文件：注释即契约，整类豁免
TYPE_DECL_RE = re.compile(r"(^|/)(types?|typings?)\.(js|ts|jsx|tsx)$|\.d\.ts$")

# ★ 声明型注释豁免（与上面的 JSDoc 契约豁免同一原理，只是另一种语言形态）。
# 约定 17 明文要求给**声明**——类/接口/枚举/组件、方法/函数、字段/常量——逐个写业务含义注释。
# 而由声明构成的文件（接口、配置属性类、DTO、枚举、工具类）代码行本就少，再叠加 Lombok 这类
# 省掉 getter/setter 的写法，**代码行被结构性压低** —— 于是「按约定 17 写对了」必然越过 1.0。
# 判它超标等于让约定 17 的两个方向互相否定。
# ⛔ 本门真正要拦的是**声明之外的行内注释膨胀**（方法体里逐行同义反复），不是 Javadoc。
# 落地方式 = **扣减**而非整档豁免：把声明文档行从注释数里扣掉，只拿「声明之外的注释」
# 与代码行比。整档豁免会让一份塞满注释掉的死代码的工具类，因 Javadoc 占比够高而整份免检；
# 扣减则两种注释各归各位，报出的比值也才是有意义的那个。
# 单块限长 ≤8 行 —— 一段 40 行的注释后面挂一个声明，那不是文档，是堆砌。
# 已知取舍：不做语法解析就区分不了「字段」与「方法体内的局部变量」，故 3 段短注释各领一个
# 局部变量声明也会被算作声明文档。本门是 Important 不阻断，宁可漏报也不制造假红——
# 假红一多，门就被整条忽略。
DECL_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|final|abstract|synchronized|default"
    r"|native|transient|volatile|export|declare|async|suspend|open|override)\s+)*"
    r"(?:(?:class|interface|enum|record|struct|trait|def|func|function|fun)\b"      # 类型/函数声明
    r"|[\w.$<>\[\], ?]+\s+\w+\s*\([^;{]*\)\s*(?:throws [\w., ]+)?\s*[{;]\s*$"   # 带返回类型的方法
    r"|[\w.$<>\[\], ?]+\s+\w+\s*(?:=[^;]*)?;\s*$)"                            # 字段/属性
    r"|^\s*[A-Z][A-Z0-9_]*\s*(?:\([^)]*\))?\s*[,;]\s*$")                       # 枚举常量
ANNOTATION_RE = re.compile(r"^\s*@\w")
DECL_DOC_MAX_RUN = 8           # 单块注释超过此行数即不算声明文档


def analyze(path, line_c, blk_open, blk_close):
    """→ (注释行, 有效代码行, 是否 A 档, 豁免原因|None)。"""
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return None
    cm = code = doc_tag = 0
    in_blk = False
    a_tier = False
    waiver = None
    marks = []                     # 逐个非空行的 ('c' 注释 | 'x' 代码, 原文)，供字段文档配对
    for ln in lines:
        t = ln.strip()
        m = IGNORE_RE.search(t)
        if m:
            waiver = m.group(1).strip()
        if not t:
            continue                       # 空行不计入任何一侧
        if A_TIER_RE.search(t):
            a_tier = True
        if DOC_TAG_RE.match(ln):
            doc_tag += 1
        if in_blk:
            cm += 1
            marks.append(("c", t))
            if blk_close and blk_close in t:
                in_blk = False
            continue
        if blk_open and t.startswith(blk_open):
            cm += 1
            marks.append(("c", t))
            if not (blk_close and blk_close in t[len(blk_open):]):
                in_blk = True
            continue
        if t.startswith(line_c) or t.startswith("*"):
            cm += 1
            marks.append(("c", t))
            continue
        code += 1
        marks.append(("x", t))
    return cm, code, a_tier, waiver, doc_tag, _decl_doc_lines(marks)


def _decl_doc_lines(marks):
    """→ 属于「短注释块 + 紧随声明」这种成对形态的注释行数。

    注解行（`@NotNull` 等）夹在注释与字段之间是常态，跳过它们再判定；
    ⛔ 不跳过任意代码行——那会把「注释块 + 一堆逻辑 + 某个声明」也算成声明文档。
    """
    total = 0
    i = 0
    while i < len(marks):
        if marks[i][0] != "c":
            i += 1
            continue
        j = i
        while j < len(marks) and marks[j][0] == "c":
            j += 1
        run = j - i
        k = j
        while k < len(marks) and marks[k][0] == "x" and ANNOTATION_RE.match(marks[k][1]):
            k += 1
        if run <= DECL_DOC_MAX_RUN and k < len(marks) and DECL_RE.match(marks[k][1]):
            total += run
        i = j
    return total


def run(root, target, threshold, min_lines):
    res = {"ok": True, "threshold": threshold, "scanned": 0,
           "importants": [], "waived": [], "a_tier_skipped": 0, "contract_doc_skipped": 0}
    base = os.path.join(root, target)
    if not os.path.isdir(base):
        res["skipped"] = f"目标目录不存在：{target}"
        return res
    for dp, dn, fns in os.walk(base):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        for fn in sorted(fns):
            ext = os.path.splitext(fn)[1]
            if ext not in LANG:
                continue
            path = os.path.join(dp, fn)
            got = analyze(path, *LANG[ext])
            if not got:
                continue
            cm, code, a_tier, waiver, doc_tag, decl_doc = got
            if cm + code < min_lines:
                continue                   # 太小的文件比值没有意义
            res["scanned"] += 1
            # ★ 只判「声明之外的注释」：约定 17 要求的声明文档不计入分子（见 DECL_RE 处）
            eff = max(0, cm - decl_doc)
            ratio = eff / code if code else float("inf")
            if ratio <= threshold:
                continue
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if waiver:
                res["waived"].append({"file": rel, "ratio": round(ratio, 2), "reason": waiver})
                continue
            if a_tier:
                res["a_tier_skipped"] += 1
                continue                   # A 档本就该写足，不打扰
            # 契约型注释豁免：类型声明文件，或注释里 @typedef/@property 等标签占比 ≥30%
            if TYPE_DECL_RE.search(rel) or (cm and doc_tag / cm >= 0.3):
                res["contract_doc_skipped"] += 1
                continue
            res["importants"].append({
                "file": rel, "comment_lines": cm, "code_lines": code,
                "ratio": round(ratio, 2),
                "msg": f"声明文档之外的注释 {eff} 行 / 代码 {code} 行 = {ratio:.1f}×"
                       f"（> {threshold}；全文注释 {cm} 行，其中声明文档 {decl_doc} 行已扣除）"
                       f"，且未命中 A 档特征 —— 约定 17 只要求 A 档写足，"
                       f"B/C 档的同义反复属净成本（⛔ 禁止为覆盖率而写）"})
    res["ok"] = not res["importants"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="约定 17 反向门：注释/代码行数比超标（Important）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--target", default="code", help="扫描目标目录（默认 code/）")
    ap.add_argument("--threshold", type=float, default=1.0, help="注释/代码 行数比上限，默认 1.0")
    ap.add_argument("--min-lines", type=int, default=30, help="小于该行数的文件不判（比值无意义）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true", help="内置双侧对照")
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    res = run(a.root, a.target, a.threshold, a.min_lines)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["ok"] else 1
    if res.get("skipped"):
        print(f"[SKIP] {res['skipped']}")
        return 0
    if res["ok"]:
        print(f"[OK] 注释/代码比未超标（巡检 {res['scanned']} 份；"
              f"A 档豁免 {res['a_tier_skipped']} 份、契约型注释豁免 {res['contract_doc_skipped']} 份、"
              f"显式豁免 {len(res['waived'])} 份）")
        return 0
    sys.stderr.write(f"⚠️ {len(res['importants'])} 份文件注释占比超标（Important，不阻断）：\n")
    for it in res["importants"]:
        sys.stderr.write(f"   · {it['file']} —— {it['msg']}\n")
    sys.stderr.write("   ⛔ 这不是「少写注释」的许可：A 档（判据/口径/状态机/并发/安全…）该写多少还写多少，\n"
                     "     本门只砍 B/C 档的同义反复。确需保留请就地写 `comment-ratio-ignore: <原因>`\n")
    return 1


def _self_check():
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    try:
        code = os.path.join(d, "code")
        os.makedirs(code)
        # 阳性：40 行注释 + 20 行代码，无 A 档特征
        bad = "\n".join(["// 设置用户名" for _ in range(40)] + [f"int x{i} = {i};" for i in range(20)])
        open(os.path.join(code, "Bad.java"), "w", encoding="utf-8").write(bad)
        r1 = run(d, "code", 1.0, 30)
        ok1 = (not r1["ok"]) and r1["importants"]
        # 阴性①：同样比例但含 A 档特征（状态机）
        open(os.path.join(code, "Bad.java"), "w", encoding="utf-8").write(
            "// 状态机：running → done\n" + bad)
        r2 = run(d, "code", 1.0, 30)
        # 阴性②：显式豁免
        open(os.path.join(code, "Bad.java"), "w", encoding="utf-8").write(
            "// comment-ratio-ignore: 本文件是对外协议说明，注释即文档\n" + bad)
        r3 = run(d, "code", 1.0, 30)
        # 阴性③：正常比例
        open(os.path.join(code, "Bad.java"), "w", encoding="utf-8").write(
            "\n".join(["// 一行说明"] + [f"int x{i} = {i};" for i in range(40)]))
        r4 = run(d, "code", 1.0, 30)
        os.remove(os.path.join(code, "Bad.java"))
        # 阴性④：★ 声明文档扣减 —— 配置属性类每字段一段 Javadoc（Lombok 省掉 getter/setter），
        #        注释 60 / 代码 20 比值 3.0，但那正是约定 17 要求的写法，不得判缺陷
        props = "@Data\npublic class P {\n" + "".join(
            f"    /**\n     * 字段{i}的业务含义\n     */\n    String f{i};\n" for i in range(15)
        ) + "}\n"
        open(os.path.join(code, "P.java"), "w", encoding="utf-8").write(props)
        r5 = run(d, "code", 1.0, 30)
        # 阳性②：★ 扣减不是整档豁免 —— 同一份文件再塞进整段注释掉的死代码，仍须报出
        open(os.path.join(code, "P.java"), "w", encoding="utf-8").write(
            props + "\n".join(f"// int dead{i} = {i};" for i in range(60)))
        r6 = run(d, "code", 1.0, 30)
        ok6 = (not r6["ok"]) and r6["importants"]
        print(f"阳性·40 注释/20 代码 且无 A 档特征 → 报出：{bool(ok1)}")
        print(f"阴性·含 A 档特征（状态机）→ 放行：{r2['ok']} (a_tier_skipped={r2['a_tier_skipped']})")
        print(f"阴性·显式豁免 → 放行：{r3['ok']} (waived={len(r3['waived'])})")
        print(f"阴性·正常比例 → 放行：{r4['ok']}")
        print(f"阴性·逐字段 Javadoc 的属性类（声明文档扣减）→ 放行：{r5['ok']}")
        print(f"阳性·同一属性类再加整段注释掉的死代码 → 仍报出：{bool(ok6)}")
        return 0 if (ok1 and r2["ok"] and r3["ok"] and r4["ok"] and r5["ok"] and ok6) else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
