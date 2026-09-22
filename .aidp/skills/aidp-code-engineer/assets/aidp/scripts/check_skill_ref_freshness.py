#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_skill_ref_freshness.py — 命令/Agent 引用 SKILL 内部编号时的新鲜度守卫。

## 为什么需要本脚本

`AIDP_HOME/commands/`、`AIDP_HOME/agents/`、`AIDP_HOME/flows/`、`AIDP_HOME/rules/` 大量写着
「`code-verification-loop` 维度 11」「`dev-logic-architect` 检查项 34」「共 21 个维度」
这类**对 SKILL 内部编号的引用**。SKILL 与命令各自演进，
**SKILL 加一个维度时，命令侧不会有人想起来去改数字**——而读的人会当真：

- 「不计入 11 维度」在 SKILL 已经是 12 个维度之后，读者会以为少了一维、或去找不存在的第 11 维；
- 「检查项 34」若 SKILL 插号重排，就会指到完全不相干的一项；
- 引用一个 SKILL **已删除**的脚本名，命令端照着跑会 file-not-found；
- SKILL **新增**的硬门脚本没被任何命令引用 ⇒ 门配了却永不运行（最高频的失效形态）。

真值就在 `AIDP_HOME/skills/*/` 里、数得出来。这类东西不该靠人记得回头改。

## 判定口径（三类，宁可少做不可误报）

**必须同行出现 SKILL 名**才纳入判定 —— 没有归属就无法判断「维度 11」是谁的第 11 维
（本仓 `/health-check` 有自己的 9 维度、`/sprint-design` 有 11 维度 SQL 采样，
都不是 SKILL 的维度）。这条收窄是零误报的关键，别放宽。

1. **索引引用**（数字在后）：`维度 11` / `检查项 34` ⇢ 该编号的标题必须在该 SKILL 里存在。
   失效方向：指向不存在的编号 → **ERROR**。
2. **计数声明**（数字在前）：`11 维度` / `12 个维度` / `共 21 个检查项` ⇢ 必须等于该 SKILL 的最大编号。
   失效方向：SKILL 加了维度、命令侧数字没跟 → **ERROR**。
3. **脚本引用**：`check_xxx.py` 同行出现 SKILL 名 ⇢ 该文件必须在那个 SKILL 的 `scripts/` 下。
   失效方向：引用已删脚本 → **ERROR**。
   反向（**WARN**）：SKILL 的 `scripts/` 里有、但**连它自己的文档都没提**的脚本 → SKILL 漏文档。
   ⚠️ **这条抓不到「SKILL 新增硬门、命令侧回检表没接线」**——那种情况下 SKILL 自己的派单块必然
   引用了该脚本，逃逸条件成立。那个不变量是**仓库专属**的（"某张表必须覆盖某个派单清单"），
   放在 `tests/test_guard_scripts.py` 里按清单对清单断言，比在通用脚本里猜哪张表该覆盖哪个 SKILL 更准。

## 豁免

    <!-- skillref-check: ignore -->             该行豁免（行尾即可）
    <!-- skillref-check: ignore-file 理由 -->    整份文件豁免

用法:
    python3 AIDP_HOME/scripts/check_skill_ref_freshness.py [--root <仓库根>] [--json]

退出码: 0 = 无 ERROR；1 = 有 ERROR；2 = 用法/环境错。
"""

from __future__ import annotations
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text

import argparse
import json
import os
import re
import sys
from pathlib import Path

# ⚠️ `docs/init` 必须在列（它不在 `AIDP_HOME/` 下，由 _scan_bases 单独并入）：
#    范式主文档随脚手架下发给下游，里面同样写着「N 维度验收」这类 SKILL 计数；
#    漏扫的实测代价 = `00_AIDP范式主文档.md` 的「13 维度」在 SKILL 升到 14 后无人发现。
SCAN_DIRS = ("commands", "agents", "flows", "rules", "reference")
# 命令端「委派 SKILL 派单块原样跑全部脚本」的固定措辞（与 flow-qr-dispatch.md 路径同时出现才算委派）
DELEGATE_PHRASE = "原样跑全部脚本"
EXTRA_SCAN_DIRS = ("docs/init",)
WIRING_BASELINE_NAME = "skill-script-wiring-baseline.txt"
SKILLS_DIR = "skills"

# 真值源：SKILL.md + references/**（脚本另算）
TRUTH_GLOBS = ("SKILL.md", "references/*.md", "references/**/*.md")

HEADING_RE = re.compile(r"^#+\s*(维度|检查项|约束|核心原则)\s*(\d+)", re.MULTILINE)
# ★ 「约束 / 核心原则」在部分 SKILL 里不是可数标题、而是 `## 约束` 段下的**有序列表**
#   （如 auto-test-runner 的 10 条约束）。只认标题会让「约束 10」永远查无此项 → 假红，
#   假红常驻的结局是整道门被忽略。故对这两类额外扫「该段落内的有序列表项号」。
#   ⛔ 收窄到段内：全局扫有序列表会把任何编号步骤都当成约束号，那是纯噪音。
# 标题常带括注（如 `## 核心原则(结论速查 · 判据全文见分片)`），别要求行尾即止。
LIST_SECTION_RE = re.compile(r"^#+\s*(约束|核心原则)\s*[(（]?[^\n]*$", re.MULTILINE)
LIST_ITEM_RE = re.compile(r"^(\d+)\.\s", re.MULTILINE)

IGNORE_LINE_RE = re.compile(r"<!--\s*skillref-check:\s*ignore\s*-->")
IGNORE_FILE_RE = re.compile(r"<!--\s*skillref-check:\s*ignore-file")

INDEX_RE = re.compile(r"(维度|检查项|约束|核心原则)\s*(\d+)")
COUNT_RE = re.compile(r"(\d+)\s*(?:个\s*)?(维度|检查项|约束|核心原则)")
SCRIPT_RE = re.compile(r"\b(check_[a-z0-9_]+\.py|validate_[a-z0-9_]+\.py)\b")

# 计数声明里这些词说明数字不是"总数"，而是别的东西（如"第 2 档"），跳过
COUNT_NEG_RE = re.compile(r"第\s*\d+\s*(维度|检查项|约束|核心原则)")


class Finding:
    def __init__(self, kind, severity, path, line, message, evidence=""):
        self.kind, self.severity = kind, severity
        self.path, self.line = path, line
        self.message = message
        self.evidence = evidence.strip()[:160]

    def to_dict(self):
        return {"kind": self.kind, "severity": self.severity, "file": self.path,
                "line": self.line, "message": self.message, "evidence": self.evidence}


def _scan_bases(root):
    """全部扫描根：`AIDP_HOME/<SCAN_DIRS>` + 仓库级 `EXTRA_SCAN_DIRS`（如 `docs/init`）。"""
    for d in SCAN_DIRS:
        yield root / runtime_relpath("", __file__) / d
    for d in EXTRA_SCAN_DIRS:
        yield root / d


def load_truth(skills_root: Path):
    """{skill_name: {"维度"/"检查项"/"约束"/"核心原则": set(int), "scripts": set(str)}}"""
    truth = {}
    if not skills_root.is_dir():
        return truth
    for sk in sorted(p for p in skills_root.iterdir() if p.is_dir()):
        entry = {"维度": set(), "检查项": set(), "约束": set(), "核心原则": set(), "scripts": set()}
        for pat in TRUTH_GLOBS:
            for fp in sk.glob(pat):
                if not fp.is_file():
                    continue
                try:
                    body = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for kind, num in HEADING_RE.findall(body):
                    entry[kind].add(int(num))
                for m in LIST_SECTION_RE.finditer(body):
                    seg = body[m.end():]
                    nxt = re.search(r"^#+\s", seg, re.MULTILINE)
                    for n in LIST_ITEM_RE.findall(seg[:nxt.start()] if nxt else seg):
                        entry[m.group(1)].add(int(n))
        sc = sk / "scripts"
        if sc.is_dir():
            entry["scripts"] = {p.name for p in sc.glob("*.py")}
        truth[sk.name] = entry
    return truth


def _skill_spans(line: str, names):
    """同行所有 SKILL 名的出现位置 [(start, name), ...]，按位置升序。"""
    spans = []
    for n in names:
        start = 0
        while True:
            i = line.find(n, start)
            if i < 0:
                break
            spans.append((i, n))
            start = i + 1
    # 同一位置被长短两个名字命中时（如 X 与 X-suffix），留最长的那个
    spans.sort(key=lambda t: (t[0], -len(t[1])))
    out, seen = [], set()
    for i, n in spans:
        if any(i < e for e in seen):
            continue
        out.append((i, n))
        seen.add(i + len(n))
    return out


# 归属邻近窗口（字符）。超出即视为"同一行里恰好也提到了别的 SKILL"，不构成归属。
# ★ 300 是实测标定值，不是拍脑袋：真阳性（sprint-test 的「不计入 11 维度」）距离 167，
#   假阳性（约定细则-3 的「维度 19」）距离 713；200~500 区间内结果恒定，取中值。
#   调小到 120 会漏掉真阳性、调大到 700+ 会把噪音收进来。改前先跑一遍标定。
OWNER_WINDOW = 300


def _owner_at(spans, pos):
    """把某个编号归属给它**左侧最近**的 SKILL 名，且必须在 OWNER_WINDOW 内。

    ⚠️ 一行里同时点名两个 SKILL 是常态，例如
    「该表同时是 `code-verification-loop` 维度 11 与 `dev-manual-testcase` 维度 21 的基准」——
    若按"取行内第一个/最长的 SKILL 名"归属，维度 21 会被算到 cvl 头上而报假红（实测复现）。
    左侧最近 = 中文书写顺序里的真实归属。左侧没有 SKILL 名则**不猜、直接跳过**。

    ⚠️ **还必须限距**：`AIDP_HOME/reference/` 里有单条 bullet 长达一两千字符、
    顺带点名四五个 SKILL 的写法。实测有一处「维度 19」，其左侧最近的 SKILL 名远在
    **713 字符**之外——那不是归属关系、只是同一行里恰好也提到过。不限距就会报假红。
    """
    owner, owner_pos = None, -1
    for i, n in spans:
        if i < pos:
            owner, owner_pos = n, i
        else:
            break
    if owner is None or pos - owner_pos > OWNER_WINDOW:
        return None
    return owner


def scan(root: Path):
    truth = load_truth(root / runtime_relpath("", __file__) / SKILLS_DIR)
    if not truth:
        return [], 0, truth, set()
    names = sorted(truth.keys(), key=len, reverse=True)

    findings, scanned = [], 0
    referenced_scripts = set()          # (skill, script) 被引用过的

    for base in _scan_bases(root):
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in ("__pycache__", ".git")]
            for fn in sorted(filenames):
                if not fn.endswith(".md"):
                    continue
                fp = Path(dirpath) / fn
                try:
                    text = fp.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if IGNORE_FILE_RE.search(text):
                    continue
                scanned += 1
                rel = str(fp.relative_to(root))
                for i, line in enumerate(text.splitlines(), 1):
                    if IGNORE_LINE_RE.search(line):
                        continue
                    spans = _skill_spans(line, names)
                    if not spans:
                        continue

                    # ① 索引引用
                    for m in INDEX_RE.finditer(line):
                        kind, n = m.group(1), int(m.group(2))
                        sk = _owner_at(spans, m.start())
                        if sk is None or not truth[sk][kind]:
                            continue          # 无归属 / 该 SKILL 无此编号体系 → 不猜
                        if n not in truth[sk][kind]:
                            findings.append(Finding(
                                "index", "ERROR", rel, i,
                                "引用 `%s` 的%s %d，但该 SKILL 里不存在这个编号（现有最大 %d）"
                                % (sk, kind, n, max(truth[sk][kind])), line))

                    # ② 计数声明
                    if not COUNT_NEG_RE.search(line):
                        for m in COUNT_RE.finditer(line):
                            n, kind = int(m.group(1)), m.group(2)
                            sk = _owner_at(spans, m.start())
                            if sk is None or not truth[sk][kind]:
                                continue
                            mx = max(truth[sk][kind])
                            # 只判"看起来像总数"的：数字 ≥ 该体系条目数的一半，避免把"2 维度拆两档"误判
                            if n != mx and n >= mx / 2:
                                findings.append(Finding(
                                    "count", "ERROR", rel, i,
                                    "自称 `%s` 有 %d 个%s，实际最大编号为 %d —— SKILL 已变更，此处未跟进"
                                    % (sk, n, kind, mx), line))

                    # ③ 脚本引用 —— 归属同样走 `_owner_at`（左侧最近 + 限距），与 ①② 口径一致。
                    #    此前用 `spans[0]`（行内**第一个** SKILL 名）：实测报错信息会指错 SKILL
                    #    （行内先提 A、后写「B 的 xxx.py」，却报"不在 A/scripts 下"）——检出对、指路错。
                    for m3 in SCRIPT_RE.finditer(line):
                        scr = m3.group(1)
                        sk = _owner_at(spans, m3.start()) or spans[0][1]
                        t = truth[sk]
                        if scr in t["scripts"]:
                            referenced_scripts.add((sk, scr))
                        elif any(scr in truth[o]["scripts"] for o in truth):
                            owner = next(o for o in truth if scr in truth[o]["scripts"])
                            referenced_scripts.add((owner, scr))
                        elif (root / runtime_relpath("", __file__) / "scripts" / scr).is_file():
                            pass          # 项目侧脚本，不归 SKILL 管
                        else:
                            findings.append(Finding(
                                "script", "ERROR", rel, i,
                                runtime_text('引用脚本 `%s`，但它既不在 `%s/scripts/` 下、也不在项目侧 `__AIDP_HOME__/scripts/`', __file__)
                                % (scr, sk), line))
    return findings, scanned, truth, referenced_scripts


def _wiring_baseline(root: Path):
    """已确认「SKILL 内部编排、命令端无需接线」的脚本白名单（`<skill>/<script>` 每行一条）。

    ⚠️ 白名单是**人工裁定**的结果，不是自动推断——正因为如此它才有信号：
    新脚本不在名单里就必然冒头，必须有人看一眼「该不该接命令端」。
    """
    fp = root / runtime_text('__AIDP_HOME__/scripts', __file__) / WIRING_BASELINE_NAME
    if not fp.is_file():
        return set()
    out = set()
    for ln in fp.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.split("#", 1)[0].strip()
        if ln:
            out.add(ln)
    return out


def unreferenced_scripts(root: Path, truth):
    """SKILL 带了脚本、而**命令端**（commands/agents/flows/rules/reference）无人引用。

    ★ 判据刻意**只看命令端**，不看 SKILL 自己的文档。
    曾经的写法是 `if scr not in blob and scr not in skill_blob`，意图是
    「SKILL 内部编排的脚本不算欠账」——但**SKILL 必然在自己的 references 里
    写了自己脚本的名字**，于是 `scr in skill_blob` 恒真、整条告警**永远不会触发**。
    实测代价：某轮 SKILL 一次新增 3 个硬门脚本、命令端一个都没接，本检查输出
    `unreferenced_skill_scripts: []` 全绿，欠账靠人工审计才发现。

    「SKILL 内部编排、无需命令端接线」改由**显式白名单**承担（`skill-script-wiring-baseline.txt`）：
    人工裁定一次、落盘留痕，新脚本自动冒头。⛔ 不要改回用 SKILL 自我文档做判据——
    那等于让被检查方自己出具合格证明。
    """
    # ★ 按【单份文档】保存文本，不再拼成一个大 blob —— 见下方「裸名匹配的掩盖效应」。
    docs = []
    for base in _scan_bases(root):
        if base.is_dir():
            for dp, dn, fns in os.walk(base):
                dn[:] = [x for x in dn if x != "__pycache__"]
                for fn in fns:
                    if fn.endswith(".md"):
                        try:
                            docs.append((Path(dp) / fn).read_text(encoding="utf-8", errors="replace"))
                        except OSError:
                            pass
    waived = _wiring_baseline(root)
    # ★ 委派接线：命令端文档写明「按 `<skill>/references/flow-qr-dispatch.md` … 原样跑全部脚本」时，
    #   该 SKILL 派单文件里出现的脚本即视为已接线——派单块本身就是命令端必跑清单的单一信源，
    #   新增硬门写进派单块即自动覆盖；未写进派单块的脚本仍须单独接线或登记白名单。
    delegated = {}
    for sk in truth:
        marker = "%s/references/flow-qr-dispatch.md" % sk
        if any(marker in d and DELEGATE_PHRASE in d for d in docs):
            fp = root / runtime_text('__AIDP_HOME__/skills', __file__) / sk / "references" / "flow-qr-dispatch.md"
            try:
                delegated[sk] = fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                pass
    out = []
    for sk, t in truth.items():
        for scr in sorted(t["scripts"]):
            if scr.startswith("__"):
                continue
            if "%s/%s" % (sk, scr) in waived:
                continue
            # ⛔⛔ **裸文件名全局匹配会让同名脚本互相掩盖**（实测本仓有 6 组跨 SKILL 同名：
            #    check_doc_split.py ×3 / check_no_fabricated_fallback.py / check_service_impl_stub.py /
            #    check_third_party_dep_reverse.py / check_ddl_consistency.py / scan_mock_data.py）。
            #    已实际造成掩盖：dev-logic-architect 的 check_no_fabricated_fallback.py 既没接线、
            #    也没登记白名单，却因 ux-logic-extractor 的同名脚本出现在别处而**永远不报**。
            # 判据改为**两段式**，兼容本项目「表头写一次 SKILL 路径、行内只写裸名」的写法：
            #    ① 精确路径 `<skill>/<script>` 出现在任一文档 → 已接线；
            #    ② 否则要求**同一份文档内**既出现裸名、又出现该 SKILL 名 → 才算接线。
            #    ⛔ 不能一刀切只认 ① —— 那会把大量合法的「表头 + 裸名」写法全判成未接线（大面积假红）。
            exact = "%s/%s" % (sk, scr)
            hit = sk in delegated and scr in delegated[sk]
            for d in docs:
                if exact in d:
                    hit = True
                    break
                if scr in d and sk in d:
                    hit = True
                    break
            if not hit:
                out.append((sk, scr))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="命令/Agent 对 SKILL 内部编号引用的新鲜度守卫")
    ap.add_argument("--root", default=".", help="仓库根（默认当前目录）")
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

    root = Path(args.root).resolve()
    if not (root / runtime_relpath("", __file__)).is_dir():
        sys.stderr.write(runtime_text('未找到 %s/__AIDP_HOME__/\n', __file__) % root)
        return 2

    findings, scanned, truth, _ref = scan(root)
    orphans = unreferenced_scripts(root, truth)
    errors = [f for f in findings if f.severity == "ERROR"]

    if args.json:
        print(json.dumps({
            "scanned_files": scanned,
            "errors": len(errors),
            "warns": len(orphans),
            "findings": [f.to_dict() for f in findings],
            "unreferenced_skill_scripts": [{"skill": s, "script": c} for s, c in orphans],
        }, ensure_ascii=False, indent=2))
    else:
        if not findings and not orphans:
            print("✅ SKILL 内部编号引用全部新鲜（巡检 %d 份 .md，%d 个 SKILL）" % (scanned, len(truth)))
        else:
            print("SKILL 引用新鲜度 —— 巡检 %d 份 .md，%d ERROR / %d WARN\n" % (scanned, len(errors), len(orphans)))
            for f in findings:
                print("  [%s] %s:%d\n        %s" % (f.severity, f.path, f.line, f.message))
                if f.evidence:
                    print("        > %s" % f.evidence)
            if orphans:
                print("\n── WARN：SKILL 自带脚本但全仓无人引用（新增硬门未接线？）")
                for s, c in orphans:
                    print("   %s / %s" % (s, c))
            print("\n豁免：行尾加 `<!-- skillref-check: ignore -->`；整份加 `<!-- skillref-check: ignore-file 理由 -->`")

    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
