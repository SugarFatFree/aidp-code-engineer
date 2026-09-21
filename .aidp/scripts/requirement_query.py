#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""requirement_query.py —— 历史需求的**读时查询**（⛔ 纯读、永不落盘）。

## 它取代了什么

此前有一份 `memory/_facts/requirement-ledger.json` 台账：`index` 把各版功规点抽成索引、
`supersede` 手工登记跨版本作废判定。下游实测把它证伪了两件事：

1. **`supersessions` 是第三份副本、且信息最少**。同一条跨版本判定已经强制写在两处 ——
   `01_研发需求.md` 的「表 F-1 历史需求作废清单」（人读权威）与
   `98_语义变更与需求作废.json` 的 `table_f`（机读副本、带 `gate` 字段过机器门）。
   而台账这第三份**丢了两个关键字段**：`original_conclusion`（被推翻的原结论原文）
   与 `source`（file+line 可回跳）。12 条逐条比对，零独有信息。
2. **它会过期而不报错**。`index` 只在 `/version` 规划期跑一次，此后 `/sprint-dev` 累进的
   新 REQ 不会刷新；`supersede` 更是**没有任何自动调用方**。于是审计「先查索引」会查到一份
   **过期索引，而它不会报错** —— 这比没有索引更危险：没索引会去读原文，过期索引给出的是
   一个看起来完整的空结果。

⇒ 落盘的那份被删除（连同 216KB / 2250 行的入库产物与每次 index 产生的 2000+ 行无语义 diff）。
**但检索能力必须留下**：审计 H 要回答的是「本版反转的这个口径，历史上哪些版本提过」——
那要搜全部历史版本的 REQ 正文，**不可能从 `98_*.json` 聚合出来**（后者只有各版自己的表 E/F）。
所以这里保留解析与检索、只去掉落盘：每次现读现搜。

## 两个子命令

    # ① 搜历史 REQ（审计 H 的「找候选」）——扫 docs/requirements/*/研发需求/*.md
    python3 AIDP_HOME/scripts/requirement_query.py search 口径 统计 --before V0.3.0 --json

    # ② 聚合跨版本作废判定（审计 H 的「查已判过的」）——聚合各版 98_*.json 的 table_f
    python3 AIDP_HOME/scripts/requirement_query.py supersessions --before V0.3.0 --json

## 成本

现读现搜要读 markdown。实测规模：18 个版本 / 3.7MB。这在 Python 里是数十毫秒量级，
而审计 H 每个版本只跑一次 —— 用这点成本换掉一份会静默过期的落盘产物，是划算的。
⛔ 别为了省这几十毫秒再把它变回落盘台账：过期索引的假绿比慢几十毫秒贵得多。

退出码：0 正常；1 数据缺失（无 docs/requirements/ 或指定版本无产物）；2 用法错。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

REQ_DIR_TPL = os.path.join("docs", "requirements", "{v}", "研发需求")
DISPOSITIONS = ("沿用", "修订", "作废")

RE_VERSION_DIR = re.compile(r"^V\d+(?:\.\d+)*$")
# ★ 功规点编号在真实项目里有多种写法（同一仓库 18 个版本实测出 4 种）：
#   REQ-001 / REQ-3 / REQ-V0.10-A02 / F1、F2 …… 只认 `REQ-` 会让一半版本索引成 0 条
#   而输出看起来完全正常（"未识别到 REQ 条目"）——那是漏抽，不是"这版没需求"。
ID = r"(?:REQ[-_][\w.\-]*\d[\w.\-]*|FR[-_]?\d[\w.\-]*)"
# ⛔ 表格行**只认 `REQ-`/`FR-`**，绝不放宽到 `F\d+`：研发需求正文里 `| F1 | A | 智能体标识 | …`
#    这类行是**字段清单表的字段编号**，不是功规点（真实项目 V0.12.1 实测）。放宽会把几十个字段
#    误抽成需求条目，台账从"索引"变成噪声源，而计数看着还更"好看"。
RE_INDEX_ROW = re.compile(r"^\|\s*(" + ID + r")\s*\|([^|]*)\|?([^|]*)\|?([^|]*)")
# 标题两种形态：编号在最前（`### REQ-001：标题` / `### REQ-V0.10-A02 标题`），
# 或编号嵌在标题里（`## 三、角色与权限矩阵（REQ-V0.10-A01）`）
RE_REQ_HEAD = re.compile(r"^#{2,4}\s*(" + ID + r")\s*[:：]?\s*(.*)$")
RE_REQ_INLINE = re.compile(r"^#{2,4}\s*(.*?)[（(]\s*(" + ID + r")\s*[)）]\s*$")


def _now():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _semver_key(v):
    nums = [int(x) for x in re.findall(r"\d+", v)]
    return nums + [0] * (4 - len(nums))


def list_versions(root):
    base = os.path.join(root, "docs", "requirements")
    if not os.path.isdir(base):
        return []
    out = [d for d in os.listdir(base)
           if RE_VERSION_DIR.match(d) and os.path.isdir(os.path.join(base, d))]
    return sorted(out, key=_semver_key)


def _digest(lines, start):
    """取该 REQ 章节起始后的正文摘要（≤300 字，折叠空白，跳过引用/表格标记）。"""
    buf = []
    for ln in lines[start:start + 60]:
        if RE_REQ_HEAD.match(ln) or re.match(r"^#{1,4}\s", ln):
            break
        t = re.sub(r"[>*`|#\-]+", " ", ln).strip()
        if t:
            buf.append(t)
        if sum(len(x) for x in buf) > 300:
            break
    return re.sub(r"\s+", " ", " ".join(buf))[:300]


def parse_version(root, v):
    """解析单个版本的研发需求，返回 (items, source_note)。"""
    d = os.path.join(root, REQ_DIR_TPL.format(v=v))
    flat = ""
    if not os.path.isdir(d):
        # 旧布局兼容：docs/requirements/{V}/研发需求.md 单文件（约定 15 之前的形态）
        cand = os.path.join(root, "docs", "requirements", v, "研发需求.md")
        if os.path.isfile(cand):
            d, flat = os.path.dirname(cand), "研发需求.md"
        else:
            return [], "无 研发需求/ 目录"
    items, seen = {}, []
    idx = os.path.join(d, "00_索引.md")
    src = []
    if os.path.isfile(idx):
        with open(idx, encoding="utf-8", errors="replace") as f:
            for i, ln in enumerate(f, 1):
                m = RE_INDEX_ROW.match(ln.strip())
                if not m:
                    continue
                rid = m.group(1)
                items[rid] = {"id": rid, "title": m.group(2).strip(),
                              "owner": m.group(3).strip(), "side": m.group(4).strip().rstrip("|").strip(),
                              "anchor": f"研发需求/00_索引.md:{i}", "digest": ""}
                seen.append(rid)
        if seen:
            src.append("00_索引.md 功规点索引表")
    for fn in ([flat] if flat else sorted(os.listdir(d))):
        if not fn.endswith(".md") or fn == "00_索引.md":
            continue
        p = os.path.join(d, fn)
        with open(p, encoding="utf-8", errors="replace") as f:
            lines = f.read().splitlines()
        for i, ln in enumerate(lines):
            m = RE_REQ_HEAD.match(ln)
            if m:
                rid, title = m.group(1), m.group(2).strip()
            else:
                m2 = RE_REQ_INLINE.match(ln)
                if not m2:
                    continue
                rid, title = m2.group(2), m2.group(1).strip()
            it = items.setdefault(rid, {"id": rid, "title": title, "owner": "", "side": "",
                                        "anchor": "", "digest": ""})
            it["anchor"] = f"研发需求/{fn}:{i + 1}"        # 正文锚点优于索引表锚点
            it["digest"] = _digest(lines, i + 1)
            if not it["title"]:
                it["title"] = title
        if any(RE_REQ_HEAD.match(x) or RE_REQ_INLINE.match(x) for x in lines):
            src.append(f"{fn} 正文章节")
    return [items[k] for k in sorted(items, key=lambda x: (len(x), x))], "；".join(src) or "未识别到 REQ 条目"

# ── 表 F 聚合（跨版本作废判定的**唯一机读信源**）────────────────────────────
SEMANTIC_JSON = "98_语义变更与需求作废.json"


def load_table_f(root, v):
    """读某版的 98_*.json，返回 (table_f, gate, err)。⛔ 缺失/损坏都如实回传，不静默当空。"""
    p = os.path.join(root, REQ_DIR_TPL.format(v=v), SEMANTIC_JSON)
    if not os.path.isfile(p):
        return [], None, "缺 98_*.json"
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as exc:
        return [], None, f"解析失败：{exc}"
    return d.get("table_f") or [], d.get("gate"), None


def do_supersessions(root, before="", exclude=()):
    """聚合各版 table_f。⛔ 不做去重/合并——原样保留各版记录与其 source 锚点。"""
    out, missing = [], []
    for v in list_versions(root):
        if v in exclude or (before and _semver_key(v) >= _semver_key(before)):
            continue
        rows, gate, err = load_table_f(root, v)
        if err:
            # ⚠️ 必须报出来：「这一版没有作废记录」与「这一版的副本没产出」
            #    在聚合结果上完全同形，而后者是产出链断了。
            missing.append({"version": v, "why": err})
            continue
        for r in rows:
            out.append({"by_version": v, **r,
                        "gate_failed": bool((gate or {}).get("failed"))})
    return {"supersessions": out, "missing_copies": missing}


def do_search(root, words, before="", exclude=(), limit=50):
    """现读现搜全部历史版本的 REQ 条目（id / title / digest）。"""
    hits = []
    for v in list_versions(root):
        if v in exclude or (before and _semver_key(v) >= _semver_key(before)):
            continue
        items, _note = parse_version(root, v)
        for it in items:
            hay = f"{it['id']} {it.get('title', '')} {it.get('digest', '')}"
            matched = [w for w in words if w in hay]
            if matched:
                hits.append({"version": v, "id": it["id"], "title": it.get("title", ""),
                             "anchor": it.get("anchor", ""), "matched": matched,
                             "digest": it.get("digest", "")[:120]})
    hits.sort(key=lambda h: (-len(h["matched"]), _semver_key(h["version"]), h["id"]))
    return hits[:limit]


def main(argv=None):
    ap = argparse.ArgumentParser(description="历史需求读时查询（纯读、不落盘）")
    ap.add_argument("--root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)
    # ⛔ `--root` 两种位置都要收：`--root X search …` 与 `search … --root X`。
    #    只挂顶层时后一种写法直接 argparse 报错、stdout 为空 —— 而调用方拿到的是
    #    「解析失败」而非「查不到」，两者处置方向完全相反。用 SUPPRESS 让子命令
    #    **不给就不覆盖**顶层取到的值（给默认值会把 `--root X search` 反向覆盖成 "."）。
    def _root_opt(q):
        q.add_argument("--root", default=argparse.SUPPRESS)
    s = sub.add_parser("search", help="搜历史 REQ 条目（正文现读现搜）")
    s.add_argument("words", nargs="+")
    s.add_argument("--before", default="", help="只搜该版本之前（通常传本版版本号）")
    s.add_argument("--exclude", default="", help="逗号分隔的排除版本")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--json", action="store_true")
    _root_opt(s)
    g = sub.add_parser("supersessions", help="聚合各版 98_*.json 的 table_f")
    g.add_argument("--before", default="")
    g.add_argument("--exclude", default="")
    g.add_argument("--json", action="store_true")
    _root_opt(g)
    a = ap.parse_args(argv)

    if not os.path.isdir(os.path.join(a.root, "docs", "requirements")):
        sys.stderr.write("⛔ 无 docs/requirements/ —— 本项目尚无版本化需求产物\n")
        return 1
    ex = tuple(x for x in (a.exclude or "").split(",") if x)

    if a.cmd == "search":
        hits = do_search(a.root, a.words, a.before, ex, a.limit)
        if a.json:
            # ⛔ 单行：测试夹具与编排端按仓库惯例只取 stdout **最后一行**解析，
            #    多行 pretty JSON 会让最后一行是 `}` → 解析失败 → 被当成"空结果"。
            print(json.dumps({"hits": hits, "count": len(hits)}, ensure_ascii=False))
            return 0
        if not hits:
            print(f"未命中（关键词：{' '.join(a.words)}）—— ⛔ 这不等于「历史上没提过」，"
                  f"换个语义词再搜一次（编号写法与措辞在各版之间会变）")
            return 0
        print(f"命中 {len(hits)} 条：")
        for h in hits:
            print(f"  [{h['version']}] {h['id']:<14} {h['title']}\n"
                  f"      命中 {'/'.join(h['matched'])} · {h['anchor']}")
        return 0

    res = do_supersessions(a.root, a.before, ex)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return 0
    print(f"跨版本作废判定 {len(res['supersessions'])} 条：")
    for r in res["supersessions"]:
        rid = r.get("req_id")
        rid = rid.get("raw", rid) if isinstance(rid, dict) else rid
        print(f"  [{r['by_version']}] {rid} ← {r.get('history_version', '?')} "
              f"· {r.get('disposition', '?')} · {str(r.get('reason', ''))[:40]}")
    if res["missing_copies"]:
        print(f"\n⚠️ {len(res['missing_copies'])} 个版本缺机读副本（"
              f"{'、'.join(m['version'] for m in res['missing_copies'])}）——"
              f"这些版本的作废判定**查不到**，⛔ 别当成「该版无作废」")
    return 0


if __name__ == "__main__":
    sys.exit(main())
