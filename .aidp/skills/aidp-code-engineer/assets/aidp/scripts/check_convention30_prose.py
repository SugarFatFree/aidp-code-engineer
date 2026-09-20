#!/usr/bin/env python3
"""check_convention30_prose.py — 约定 30「正文只陈述最终行为」的棘轮守卫（脚手架契约脚本）。

## 这道门堵的是什么

约定 30 要求指令/文档正文**只描述当前该做什么**，禁止铺陈「原来怎样→现在改成怎样→为什么」。
理由很实际：下游 AI 每次会话都要读这些正文，历史叙事既占上下文、又让它分不清
「哪句是现行规则、哪句是已废弃的旧做法」——实测出现过按已废除的旧分支执行的情况。

没有机器门时叙事会一路堆积，且大多落在 `flows/` `reference/` `rules/`、SKILL 正文与各级 README 里。

⚠️ **`rationale.md` 是例外**：它本就是承载「为什么这么定」的根因文件。约定 30 管的是**指令正文**，不是根因档案。

## 判据

扫约定 30 范围内的 `.md`（契约目录 + `docs/init` + 根级记忆文件 + 各 SKILL 的 `SKILL.md` + `docs/**/README.md`
+ `.aidp/scripts/README.md` + `memory/README.md`），匹配历史叙事模式（`此前` / `原来是` / `旧行为` / `已废除` /
`不再锁死` / `📌 历史` / 正文里的范式版本戳：`（Vx.y 新增）`、标题 `（Vx.y）`、文件头/页脚 `AIDP Vx.y`、
行内 `Vx.y 起`）。

**棘轮机制**：存量命中冻结进 baseline，只拦**新增**。这是唯一能让这道门当天就落地的方式——
一次性清理几十处历史叙事既费时又容易改错语义，而"报一大片红、没人看"的门等于没门。
清理存量时跑 `--update-baseline` 收缩水位。

退出码：0 无新增；1 有新增；2 参数错。
"""
import argparse
import hashlib
import json
import os
import re
import sys

SCAN_DIRS = (".aidp/commands", ".aidp/agents", ".aidp/flows",
             ".aidp/reference", ".aidp/rules", "docs/init")
# 约定 30 明文把根级文件也列进范围，但它们不在任何 SCAN_DIRS 下 —— 单独登记，
# 否则这些根级文件与项目记忆文件（AGENTS.md / CLAUDE.md）处于「规则说要管、门却不扫」的空白区。
SCAN_FILES = ("CLAUDE.md", "README.md", "AGENTS.md", ".aidp/AIDP-AGENTS.md",
              ".aidp/scripts/README.md", "memory/README.md")
# 按文件名收的扫描面：各 SKILL 正文、docs 下各级 README（下发文档，读者同样是下游 AI）
SCAN_GLOBS = ((".aidp/skills", "SKILL.md"), ("docs", "README.md"))
# 根因档案豁免：它的职责就是记录「为什么」。
# ⛔ 只豁免 rationale.md —— 与约定 30 主行「唯 rationale.md 例外」逐字一致。
#    曾一并豁免 invariants.md，与主行口径冲突；不变式文件同样只该陈述最终行为。
EXEMPT_BASENAMES = {"rationale.md"}
BASELINE = ".aidp/scripts/convention30-prose-baseline.txt"

# ⚠️ 词表宽度直接决定这道门的真实覆盖率：实测原「此前」正则（要求后接否定/范围副词）
#    只命中 SCAN_DIRS 内 39 行里的 11 行（28%），另 28 行与 `曾经`/`原先`/`历史上`/`旧版曾`/
#    `现已改为` 五类同义写法完全在检查面之外 —— 门是绿的、欠账是真的。
PATTERNS = [
    (re.compile(r"此前[^。；\n]{0,60}(没|无|未|只|从未|一直|恒|全是|都是|改|拆|收紧|废|变成|现)"),
     "此前…（旧行为叙述）"),
    (re.compile(r"(曾经|原先|历史上|旧版曾|曾误|曾一并|曾允许|实测曾|现已改为|现改为|已改成|后来改|原散落|现统一归档)"), "旧实现叙述"),
    (re.compile(r"(原来是|旧行为|旧写法|旧的「|老写法|早期实现)"), "旧实现对比"),
    (re.compile(r"(已废除|已废弃、改为|不再锁死|不再默认|收紧为|由 report-only 收紧)"), "废除/变更叙述"),
    (re.compile(r"📌\s*\*\*历史\*\*"), "📌 历史段"),
    (re.compile(r"（V\d+\.\d+(\.\d+)?\s*(新增|起|改|重写)）"), "范式版本戳"),
    (re.compile(r"（V\d+\.\d+(\.\d+)?）"), "范式版本戳（标题）"),
    (re.compile(r"基于\s*AIDP\s*V\d|AIDP\s*V\d+\.\d+"), "范式版本戳（文件头/页脚）"),
    (re.compile(r"V\d+\.\d+(\.\d+)?\s*起[，,、；;）)\s]"), "范式版本戳（行内溯源）"),
]
IGNORE_RE = re.compile(r"<!--\s*conv30:\s*ignore\b")


def _key(rel, i, tag, line=""):
    """baseline 的键：**文件 + 标签 + 内容指纹**，⛔ 不含行号。

    用行号做键有个致命弱点：在同一文件里插入任何**无关内容**都会让后面所有条目的行号
    整体漂移，于是存量被整批误报成"新增"。假红一多，门就被忽略——那是比没门更糟的结局
    （实测：本守卫上线当天就因为同文件加了一段说明而误报了一条）。
    内容指纹只取归一化后的前 120 字符，容忍排版微调、认得出实质改写。
    """
    h = hashlib.sha1(re.sub(r"\s+", "", line)[:120].encode("utf-8")).hexdigest()[:12]
    return f"{rel}:{tag}:{h}"


def _load_baseline(root):
    p = os.path.join(root, BASELINE)
    if not os.path.isfile(p):
        return set()
    return {ln.strip() for ln in open(p, encoding="utf-8")
            if ln.strip() and not ln.startswith("#")}


def run(root=".", update=False):
    base = _load_baseline(root)
    hits, scanned = [], 0
    targets = []
    for d in SCAN_DIRS:
        for dirpath, _dn, fns in os.walk(os.path.join(root, d)):
            if "__pycache__" in dirpath:
                continue
            for fn in sorted(fns):
                if fn.endswith(".md") and fn not in EXEMPT_BASENAMES:
                    targets.append(os.path.join(dirpath, fn))
    for d, basename in SCAN_GLOBS:
        for dirpath, dirnames, fns in os.walk(os.path.join(root, d)):
            # 脚手架 bundle 是镜像生成物，扫本体即可
            dirnames[:] = [x for x in dirnames if x not in ("assets", "__pycache__", "node_modules")]
            if basename in fns:
                fp = os.path.join(dirpath, basename)
                if fp not in targets:
                    targets.append(fp)
    for rel_f in SCAN_FILES:            # 约定 30 明文列入范围的根级 / .aidp 顶层文件
        fp = os.path.join(root, rel_f)
        if os.path.isfile(fp):
            targets.append(fp)
    if True:
        if True:
            for fp in targets:
                rel = os.path.relpath(fp, root).replace(os.sep, "/")
                scanned += 1
                for i, ln in enumerate(open(fp, encoding="utf-8").read().splitlines(), 1):
                    if IGNORE_RE.search(ln):
                        continue
                    for rx, tag in PATTERNS:
                        if rx.search(ln):
                            hits.append({"key": _key(rel, i, tag, ln), "file": rel,
                                         "line": i, "tag": tag,
                                         "excerpt": ln.strip()[:96]})
                            break
    if update:
        p = os.path.join(root, BASELINE)
        with open(p, "w", encoding="utf-8") as f:
            f.write("# 约定 30 历史叙事存量水位（棘轮 baseline）——只拦新增，清理存量后重跑 "
                    "`--update-baseline` 收缩\n")
            f.write("# ⛔ 新增条目前先想清楚：这句真的必须留在指令正文里吗？"
                    "根因说明该去 rationale.md。\n")
            for h in sorted({h["key"] for h in hits}):
                f.write(h + "\n")
        return {"updated": len(set(h["key"] for h in hits)), "scanned": scanned}

    new = [h for h in hits if h["key"] not in base]
    # ★ 僵尸条目 = baseline 里有、正文里已不再命中的键（内容改了却没重跑 `--update-baseline`）。
    #   它们不造成误判（键是内容指纹，新内容匹配不上旧键），但会让「存量水位」长期虚高——
    #   而棘轮的全部意义就是让这个数字**只降不升、且降下去要看得见**。不报出来，
    #   水位就永远停在历史高点，没人知道其中几条其实早已清掉。
    _live = {h["key"] for h in hits}
    stale = sorted(k for k in base if k not in _live)
    return {"applicable": scanned > 0, "scanned": scanned, "total": len(hits),
            "baseline": len(base), "new": new, "stale": stale, "passed": not new}


def main():
    ap = argparse.ArgumentParser(description="约定 30「正文只陈述最终行为」棘轮守卫")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    a = ap.parse_args()
    if a.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(a, "json", False)))
    if a.update_baseline:
        r = run(a.root, update=True)
        print(f"[OK] baseline 已更新：{r['updated']} 处存量水位 → {BASELINE}")
        return 0
    r = run(a.root)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["passed"] else 1
    for h in r["new"]:
        print(f"  [ERROR] {h['file']}:{h['line']} — 约定 30：{h['tag']}")
        print(f"        > {h['excerpt']}")
    print(f"约定 30 正文体检：巡检 {r['scanned']} 份 .md，存量水位 {r['baseline']}，"
          f"新增 {len(r['new'])}")
    if r.get("stale"):
        print(f"  ⚠️ baseline 有 {len(r['stale'])} 条僵尸条目（正文已改、键不再命中）——"
              f"实际存量只有 {r['total']}，水位虚高；跑 `--update-baseline` 收缩：")
        for k in r["stale"][:6]:
            print(f"     · {k}")
    if r["new"]:
        print("  改法：删掉历史对比、只留最终行为；确需记根因 → 移到同目录 `rationale.md`（豁免）；"
              "确属必要 → 行尾 `<!-- conv30: ignore 理由 -->` 或 `--update-baseline`")
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
