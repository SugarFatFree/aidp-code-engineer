#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 22 口径级联残留门 —— 「同一口径改了一处、漏了五处」的确定性初筛。

## 它补的是哪个洞

`check_cascade_landing.py` 管的是**落点**（改动落没落进各族内容主文档）与**增量册终态**
（该删的删没删）。两者都不看**内容**：一条口径变更把「不向用户解释」改成「列级范围说明」，
只要落点对、台账清了，两个门全绿——哪怕研发需求正文改了、而字段处置表 / 验收测试点 /
用例断言 / 索引摘要里旧口径原封不动。

真实回流（实际项目中连续两个版本同型复发）：

  · V0.13.0 收口期：三条自称「已级联」的条目，逐条复查**全部**有残留。
  · V0.14.0 规划期：设计层声明了 3 条级联义务并点名对象，实测研发需求侧 **6 处未落地**；
    其中一处使 `TC-45` 的断言与 `REQ-010 规则 7` **直接互斥**——用例跑必 Fail，
    却要等 version-auditor 判 Critical 才发现。

根因不是执行体偷懒，是**按「条目编号」改而口径按「语义」散布**：同一句口径通常同时写在
正文规则、字段处置表、验收测试点、用例断言、索引摘要。人肉 grep 能查，但没人每次都查，
查了也难判"这处到底该不该改"。

## 判定口径（两类必须分开，这是本门的全部难点）

同一个旧口径字符串，出现在文档里有两种完全相反的含义：

  · **真残留**  —— 旧口径仍作为**当前生效规则**出现 → 必须改。
  · **订正留痕** —— 旧口径出现在「原口径…已作废」「由…订正为…」「变更历史」这类
                    **说明它已被推翻**的上下文里 → **应当保留**，改掉反而抹掉审计痕迹。

反向断言写太宽 → 恒不为 0（误伤合法留痕，门变噪音）；写太窄 → 漏真残留（门形同虚设）。
故本门只做**初筛 + 分类**：`residues[]` 要求人确认改，`annotated[]` 列出供复核，
两边都打印文件:行号与原文，让判断有依据而不是从零 grep。

留痕判据（命中任一即归 annotated）：
  ① 命中行 / 上下文 ±N 行内出现留痕词（作废 / 原口径 / 旧口径 / 订正 / 改为 / 取代 /
     废弃 / deprecated / 变更历史 / 修订记录 / 删除线 `~~`）
  ② 命中行**同时**含 `--new` 的新口径（典型「由 X 订正为 Y」同行写法）
  ③ 命中行所属最近标题是留痕型章节（变更历史 / 修订记录 / 作废清单 / 待澄清 …）
  ④ 命中 `--allow` 自定义正则

## 扫描范围

约定 22 的四族文档目录（`--scope` 可裁剪）。**整族全扫**，不只扫增量文件——
口径可以写在 `01_` 主文档、`00_索引.md`、`NN_` 增量、用例文件的任何一处，
只扫增量文件恰好会漏掉最常残留的那几处。

族增量册 **不扫**：它正记着"把 X 改成 Y"这件事本身，必然含旧口径，
是过程记录不是生效规则，扫它只会产出恒定噪音。

## 退出码

  0 = 无真残留（annotated / 漏族只打印不影响退出码）
  2 = 检出真残留
  1 = 参数或路径错误（fail-closed：给不出结论就是不通过）

## 用法

    check_cascade_residue.py --version V0.14.0 \\
        --old "不向用户解释" --new "列级范围说明" \\
        [--scope requirements,design,plans,testing] [--context 2] \\
        [--allow "见变更说明"] [--root .] [--json]

`--old` 可重复传（一条口径变更常有多个旧措辞变体）。
"""
import argparse
import json
import os
import re
import sys

# 四族目录模板（{v} = 版本号）；与 check_cascade_landing.py::FAMILIES 同源，
# 但这里扫的是**整个目录**（含 01_ 主文档 / 00_索引 / NN_ 增量），不限于增量落点文件。
FAMILIES = [
    ("requirements", "需求", "docs/requirements/{v}/研发需求"),
    ("design",       "设计", "docs/design/detail/{v}"),
    ("plans",        "计划", "docs/plans/{v}"),
    ("testing",      "用例", "docs/testing/{v}/研发自测"),
]
SCOPE_KEYS = [f[0] for f in FAMILIES]

# 族增量册是过程记录、必然含旧口径（它正记着"把 X 改成 Y"这件事本身），扫它恒噪音。
# ⛔ 四族一个都不能漏：漏登记任一份，该族的增量册就会把每条口径变更都报成"残留"。
SKIP_BASENAMES = {"_开发期需求增量.md", "_开发期设计增量.md",
                  "_开发期计划增量.md", "_开发期用例增量.md"}

# 留痕词：出现即说明"这里在讲它已被推翻"，不是在把它当生效规则用
_ANNOTATION_WORDS = [
    "作废", "已废弃", "废弃", "原口径", "旧口径", "订正", "取代", "被替换", "已替换",
    "变更历史", "修订记录", "变更记录", "历史版本", "deprecated", "DEPRECATED",
    "不再使用", "已失效", "改为", "变更为", "调整为",
]
_ANNOTATION_RE = re.compile("|".join(re.escape(w) for w in _ANNOTATION_WORDS))
_STRIKE_RE = re.compile(r"~~.+?~~")
# 留痕型章节标题
_ANNOTATION_HEADING_RE = re.compile(
    r"变更历史|修订记录|变更记录|作废|废弃|待澄清|已知失准|遗留|欠账|历史")
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*\S)\s*$")


def _iter_md(base):
    """族目录下全部 .md（递归），跳过台账与隐藏目录。"""
    out = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in sorted(filenames):
            if not fn.endswith(".md") or fn in SKIP_BASENAMES:
                continue
            out.append(os.path.join(dirpath, fn))
    return sorted(out)


def _classify(lines, idx, heading, old, new, context, allow_re):
    """返回 (是否留痕, 归因说明)。命中行为 lines[idx]。"""
    line = lines[idx]
    if _STRIKE_RE.search(line):
        return True, "删除线标记"
    if new and new in line:
        return True, "同行含新口径（典型「由 X 订正为 Y」）"
    if allow_re and allow_re.search(line):
        return True, "命中 --allow 白名单"
    # ⛔ 上下文扫描**遇标题即止**（两个方向都是）。缺这条会出现最坏的一类误判：
    #    字段处置表里的真残留，因为两行之后正好开了个 `## 变更历史` 章节而被判成留痕、
    #    从此隐形——门写太宽不只是产噪音，是让真残留看不见。章节是语义边界，
    #    跨过它的留痕词说的不是这一处。
    for step in (-1, 1):
        for k in range(1, context + 1):
            j = idx + step * k
            if j < 0 or j >= len(lines):
                break
            if _HEADING_RE.match(lines[j]):
                break
            m = _ANNOTATION_RE.search(lines[j])
            if m:
                return True, f"上下文第 {j + 1} 行含留痕词「{m.group(0)}」"
    m = _ANNOTATION_RE.search(line)
    if m:
        return True, f"本行含留痕词「{m.group(0)}」"
    if heading and _ANNOTATION_HEADING_RE.search(heading):
        return True, f"位于留痕型章节「{heading}」"
    return False, ""


def scan_file(root, path, olds, new, context, allow_re):
    """单文件扫描，返回 (residues, annotated, new_hits)。"""
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except (OSError, UnicodeDecodeError) as exc:
        # fail-closed：读不了的文件不能当"没问题"
        return None, None, None, f"{rel}: {exc}"
    lines = text.splitlines()
    residues, annotated = [], []
    new_hits = 0
    heading = ""
    fence = False
    for idx, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            fence = not fence
        elif not fence:
            m = _HEADING_RE.match(line)
            if m:
                heading = m.group(1)
        if new and new in line:
            new_hits += 1
        for old in olds:
            if old not in line:
                continue
            is_annot, why = _classify(lines, idx, heading, old, new, context, allow_re)
            rec = {"file": rel, "line": idx + 1, "old": old,
                   "heading": heading, "in_code_fence": fence,
                   "text": line.strip()[:200]}
            if is_annot:
                rec["reason"] = why
                annotated.append(rec)
            else:
                residues.append(rec)
            break  # 一行只报一次，多个 old 变体不重复计数
    return residues, annotated, new_hits, None


def derive_variants(olds, min_len=3):
    """从 `--old` 派生**短形式**词表（去掉前置限定词）。

    ⛔ 这一步存在的理由：词表单一会漏检，而"补个宽词表再跑一遍"如果只是处置清单里的一句
    文字建议，就会被反复跳过（下游实证：连续三轮都没跑）。下游用 `--old 课程截止时间` 得 0 处，
    换 `--old 截止时间` 得 13 处、其中 1 条 Critical —— 同一次审计，结论天差地别。
    故把它变成**默认就跑**的动作，而不是需要人记得的可选步骤。

    派生规则（确定性、无分词依赖）：中文取长度 ≥ `min_len` 的**后缀**；ASCII 词组按
    空格/连字符/下划线切分后取尾段。派生词必然匹配原词命中的那些行，因此结果里会**剔除**
    已由原词报出的行——只有真正新增的行才会留下，噪声派生词自然什么也不贡献。
    """
    out = []
    for old in olds:
        t = old.strip()
        if not t:
            continue
        if any(ch in t for ch in " -_"):
            # 带分隔符 = 词组：只按词切，⛔ 不逐字符切
            #   （逐字符会派生出 "ourse due date"/"ue date" 这类碎片，纯噪声）
            parts = [x for x in re.split(r"[\s\-_]+", t) if x]
            for i in range(1, len(parts)):
                cand = " ".join(parts[i:])
                if len(cand) >= min_len:
                    out.append(cand)
        else:
            # 无分隔符 = 中文复合词：取后缀。限定词多为 1~3 字（课程 / 本次 / 最终 / 企业级），
            #   故只丢前 1~3 个字；再往后丢就只剩碎片，且必然被原词的命中行吸收掉。
            for i in range(1, min(4, len(t))):
                cand = t[i:]
                if len(cand) >= min_len:
                    out.append(cand)
    seen, uniq = set(olds), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def run(root, version, olds, new, scopes, context, allow, variants=()):
    allow_re = None
    if allow:
        try:
            allow_re = re.compile(allow)
        except re.error as exc:
            return {"ok": False, "error": "bad-allow-regex", "detail": str(exc)}
    result = {"ok": True, "version": version, "old": olds, "new": new,
              "scanned_files": 0, "residues": [], "annotated": [],
              "variants": list(variants), "variant_residues": [],
              "families": [], "missing_new_families": [], "error": None}
    seen_dir = False
    for key, cn, tpl in FAMILIES:
        if key not in scopes:
            continue
        base = os.path.join(root, tpl.format(v=version))
        node = {"scope": key, "name": cn,
                "dir": tpl.format(v=version), "exists": os.path.isdir(base),
                "files": 0, "residues": 0, "annotated": 0, "new_hits": 0}
        if not node["exists"]:
            result["families"].append(node)
            continue
        seen_dir = True
        for path in _iter_md(base):
            res, ann, nh, err = scan_file(root, path, olds, new, context, allow_re)
            if variants and err is None:
                vres, _vann, _vnh, verr = scan_file(root, path, variants, new, context, allow_re)
                if verr is None:
                    _known = {(x["file"], x["line"]) for x in (res or [])} | \
                             {(x["file"], x["line"]) for x in (ann or [])}
                    result["variant_residues"].extend(
                        v for v in (vres or []) if (v["file"], v["line"]) not in _known)
            if err is not None:
                return {"ok": False, "error": "unreadable", "detail": err}
            node["files"] += 1
            node["residues"] += len(res)
            node["annotated"] += len(ann)
            node["new_hits"] += nh
            result["residues"].extend(res)
            result["annotated"].extend(ann)
            result["scanned_files"] += 1
        result["families"].append(node)
    if not seen_dir:
        # 四族目录一个都不存在 → 版本号写错或没到规划期，不能静默判过
        return {"ok": False, "error": "no-family-dir",
                "detail": f"{version} 的四族目录一个都不存在（--scope={','.join(sorted(scopes))}）"}
    # 新口径 0 命中的族 = 该族很可能整族漏级联；作提示不进退出码（有的口径本就不涉及某族）
    if new:
        result["missing_new_families"] = [
            n["scope"] for n in result["families"]
            if n["exists"] and n["files"] > 0 and n["new_hits"] == 0]
    result["ok"] = not result["residues"]
    # ★ 顶层布尔，供消费方直接判。⛔ 别让调用方去数 `len(residues)`：
    #   `residues` 与 `annotated` 是并列字段，而名字不够对立——直觉上 "annotated"
    #   像是 "residues 的已处理子集"，于是"看了 annotated 就以为看了全部"。
    #   下游实证：连续三轮宣布"真残留 0"，实际每轮都还有 10+ 条。
    result["has_real_residue"] = bool(result["residues"])
    return result


def main():
    ap = argparse.ArgumentParser(
        description="约定 22 口径级联残留门：旧口径是否仍作为生效规则残留在四族文档里")
    ap.add_argument("--root", default=".", help="项目根（默认当前目录）")
    ap.add_argument("--version", required=True, help="目标版本号，如 V0.14.0")
    ap.add_argument("--old", action="append", required=True,
                    help="旧口径字符串（可重复传，覆盖多个措辞变体）")
    ap.add_argument("--new", default="", help="新口径字符串（用于留痕判定 + 落地分布统计）")
    ap.add_argument("--scope", default=",".join(SCOPE_KEYS),
                    help=f"扫描族，逗号分隔，可选 {'/'.join(SCOPE_KEYS)}（默认全部）")
    ap.add_argument("--context", type=int, default=2, help="留痕判定的上下文行数（默认 2）")
    ap.add_argument("--allow", default="", help="额外留痕白名单正则")
    ap.add_argument("--no-derive-variants", action="store_true",
                    help="关闭短形式派生词表（默认开启）。派生命中只作提示、不影响退出码")
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

    scopes = {s.strip() for s in args.scope.split(",") if s.strip()}
    bad = scopes - set(SCOPE_KEYS)
    if bad:
        sys.stderr.write(f"❌ 未知 --scope 值：{','.join(sorted(bad))}"
                         f"（可选 {'/'.join(SCOPE_KEYS)}）\n")
        return 1
    olds = [o for o in (args.old or []) if o.strip()]
    if not olds:
        sys.stderr.write("❌ --old 不能为空\n")
        return 1

    variants = () if args.no_derive_variants else derive_variants(olds)
    res = run(args.root, args.version, olds, args.new, scopes, args.context,
              args.allow, variants)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else (1 if res.get("error") else 2)

    if res.get("error"):
        sys.stderr.write(f"❌ 口径残留门无法判定（{res['error']}）：{res['detail']}\n"
                         "   fail-closed：给不出结论就是不通过——请确认 --version 与 --scope\n")
        return 1

    if res["annotated"]:
        print(f"ℹ️  以下 {len(res['annotated'])} 处**不是**残留，是订正留痕（应当保留，勿改）：")
        for a in res["annotated"][:20]:
            print(f"   · {a['file']}:{a['line']}（{a['reason']}）\n     {a['text']}")
        if len(res["annotated"]) > 20:
            print(f"   …另有 {len(res['annotated']) - 20} 处，用 --json 看全量")

    if res.get("variant_residues"):
        _vr = res["variant_residues"]
        print(f"🔎 短形式词表额外命中 {len(_vr)} 处（派生自 --old：{'、'.join(res['variants'][:6])}"
              f"{'…' if len(res['variants']) > 6 else ''}）—— **不计入退出码**，但请逐条看："
              f"原词 0 命中而短形式命中，往往意味着词表选窄了")
        for v in _vr[:20]:
            print(f"   · {v['file']}:{v['line']}（命中「{v['old']}」）\n     {v['text']}")
        if len(_vr) > 20:
            print(f"   …另有 {len(_vr) - 20} 处，用 --json 看全量")

    if res["missing_new_families"]:
        print(f"⚠️  新口径「{res['new']}」在这些族 0 命中，请确认是否整族漏级联："
              f"{'、'.join(res['missing_new_families'])}")

    if res["ok"]:
        print(f"[OK] 无旧口径残留（{res['version']}；扫 {res['scanned_files']} 份文档，"
              f"旧口径 {len(res['annotated'])} 处命中全属订正留痕）"
              + (f"；⚠️ 但短形式词表另有 {len(res['variant_residues'])} 处待人工确认"
                 if res.get("variant_residues") else ""))
        return 0

    sys.stderr.write(f"❌ 旧口径仍作为生效规则残留 {len(res['residues'])} 处"
                     f"（{res['version']}；扫 {res['scanned_files']} 份文档）：\n")
    for r in res["residues"]:
        tag = "（代码块内）" if r["in_code_fence"] else ""
        head = f" ← {r['heading']}" if r["heading"] else ""
        sys.stderr.write(f"   · {r['file']}:{r['line']}{tag}{head}\n     {r['text']}\n")
    sys.stderr.write("   同一口径通常同时写在正文规则 / 字段处置表 / 验收测试点 / 用例断言 / "
                     "索引摘要，按条目编号改只会改到第一处。\n"
                     "   逐处改完重跑本门；确属订正留痕的，在该处补一句"
                     "「原口径…已作废」即可被识别为留痕。\n")
    # ★ 最后一行必须是结论：上面的「ℹ️ 订正留痕 N 处（应当保留）」很醒目且先于残留清单打印，
    #   读的人看到它就以为看完了。把判决放在**输出的最末尾**，让"还欠 N 处"无法被滚过去。
    sys.stderr.write(f"⛔ 仍有 {len(res['residues'])} 处真残留未订正（退出码 2）"
                     f"；另有 {len(res['annotated'])} 处属订正留痕、**不是**残留、勿改"
                     + (f"；短形式词表另有 {len(res['variant_residues'])} 处待人工确认"
                        if res.get("variant_residues") else "") + "\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
