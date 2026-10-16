#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨 SKILL「共享段」逐字节一致性（确定性，ERROR 级）。

## 为什么这道门归模板侧

上游若干 SKILL 之间有**刻意的逐字节副本**：SKILL 必须彼此独立（不得跨 SKILL `import`
或引用对方路径，否则 vendored 单个 SKILL 就跑不起来），于是「同一判据」只能在各自
`scripts/` 里各持一份。上游在段首写明：

    >>> SHARED-SEGMENT: <名字> >>>
    ⚠️⚠️ 本段在 N 个 SKILL 的脚本里各持一份逐字节相同的副本…
         改一处必须 N 处同改，**连空格都要一致** —— 仓库级硬门
    <<< SHARED-SEGMENT: <名字> <<<

「仓库级硬门」只能由**仓库**来提供 —— 各 SKILL 自己都看不到别人那份。
而这类副本的失效形态极隐蔽：改了一处、另外三处照旧，于是**同一个编号在
需求侧认、在计划侧不认**，表现为「覆盖率莫名少了几条」而不是任何报错。

## 判据

扫 `{{AIDP_HOME}}/skills/*/scripts/*.py`（运行真源由 `aidp_runtime` 解析），
按 `SHARED-SEGMENT: <名字>` 分组，组内逐字节比对。
⚠️ 本仓库的**脚手架引擎**在根级 `skills/aidp-code-engineer/`、不在下发 SKILL 面内，
故天然不进扫描面 —— ⛔ 别为它加排除名单，那会让读者以为它本来在里面。

- 组内出现 ≥2 种不同内容 ⇒ ERROR，并打印**逐行差异**（直接可改）。
- 段首声明的副本数（`在 N 个 SKILL`）与实际找到的份数不符 ⇒ ERROR
  —— 少了说明有人删了一份、多了说明新增的那份没登记进声明。
- 只找到 1 份 ⇒ WARN（共享段只有一份时，「共享」这个声明本身已失准）。

⛔ **不做归一化**（不剥空格、不统一换行）：上游明写「连空格都要一致」，
   归一化会让「只差空格」通过，而那恰好是最容易漏同步的那一类。
"""
import argparse
import difflib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aidp_collect import from_result  # noqa: E402
from aidp_runtime import runtime_relpath  # noqa: E402

# 运行真源由 `aidp_runtime` 解析（模板仓库与下游各不相同，⛔ 不写死任何一个）
SKILLS_DIR = runtime_relpath("skills", __file__)
# ⛔ 本仓库的脚手架引擎在根级 `skills/aidp-code-engineer/`、不在下发 SKILL 面内，
#   故此处无需排除任何名字；留空集而不删这个常量，是为了让"有没有排除面"这件事显式可见。
EXCLUDE_SKILLS = set()

_BEGIN = re.compile(r">>>\s*SHARED-SEGMENT:\s*([\w\-]+)\s*>>>")
_END = re.compile(r"<<<\s*SHARED-SEGMENT:\s*([\w\-]+)?\s*<<<")
# 段首声明的副本数：「本段在四个 SKILL 的脚本里」/「在 4 个 SKILL」都要认
_DECLARED_N = re.compile(r"在\s*([0-9一二三四五六七八九十]+)\s*个\s*SKILL")
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def _parse_n(raw):
    raw = (raw or "").strip()
    if raw.isdigit():
        return int(raw)
    return _CN_NUM.get(raw)


def extract_segments(path):
    """返回 [(名字, 段内容, 起始行, 声明副本数|None)]。未闭合的段单独标出。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read(400_000).splitlines(keepends=True)
    except OSError:
        return None

    out, i = [], 0
    while i < len(lines):
        m = _BEGIN.search(lines[i])
        if not m:
            i += 1
            continue
        name, start, body = m.group(1), i + 1, []
        i += 1
        closed = False
        while i < len(lines):
            if _END.search(lines[i]):
                closed = True
                i += 1
                break
            body.append(lines[i])
            i += 1
        blob = "".join(body)
        decl = _DECLARED_N.search(blob)
        out.append({
            "name": name, "body": blob, "line": start,
            "declared": _parse_n(decl.group(1)) if decl else None,
            "closed": closed,
        })
    return out


def run(root):
    groups, files, failed, unclosed = {}, 0, 0, []
    base = os.path.join(root, SKILLS_DIR)
    if not os.path.isdir(base):
        res = {"applicable": False, "reason": f"无 {SKILLS_DIR} 目录"}
        res.update(from_result(res).as_json())
        return res
    for skill in sorted(os.listdir(base)):
        if skill in EXCLUDE_SKILLS or not os.path.isdir(os.path.join(base, skill)):
            continue
        sdir = os.path.join(base, skill, "scripts")
        if not os.path.isdir(sdir):
            continue
        for fn in sorted(os.listdir(sdir)):
            if not fn.endswith(".py"):
                continue
            rel = os.path.join(SKILLS_DIR, skill, "scripts", fn)
            segs = extract_segments(os.path.join(root, rel))
            files += 1
            if segs is None:
                failed += 1
                continue
            for s in segs:
                if not s["closed"]:
                    unclosed.append({"file": rel, "line": s["line"], "name": s["name"]})
                    continue
                groups.setdefault(s["name"], []).append(dict(s, file=rel, skill=skill))

    findings = []
    for name, members in sorted(groups.items()):
        bodies = {}
        for m in members:
            bodies.setdefault(m["body"], []).append(m)
        if len(bodies) > 1:
            # 以**出现次数最多**的那份为基准（少数派更可能是漏同步的那几份）
            ranked = sorted(bodies.items(), key=lambda kv: -len(kv[1]))
            base_body, base_members = ranked[0]
            for other_body, other_members in ranked[1:]:
                diff = list(difflib.unified_diff(
                    base_body.splitlines(), other_body.splitlines(),
                    fromfile=base_members[0]["file"], tofile=other_members[0]["file"],
                    lineterm="", n=1))
                findings.append({
                    "segment": name, "kind": "content-drift",
                    "baseline": base_members[0]["file"],
                    "drifted": [m["file"] for m in other_members],
                    "diff": diff[:40],
                    "detail": ("共享段 `%s` 出现 %d 种不同内容 —— 上游明写「改一处必须各处同改、"
                               "连空格都要一致」。失效形态极隐蔽：同一判据在一个 SKILL 认、"
                               "在另一个不认，表现为「覆盖率莫名少了几条」而非任何报错。"
                               % (name, len(bodies))),
                })
        declared = next((m["declared"] for m in members if m["declared"]), None)
        if declared and declared != len(members):
            findings.append({
                "segment": name, "kind": "count-mismatch",
                "declared": declared, "actual": len(members),
                "files": [m["file"] for m in members],
                "detail": ("共享段 `%s` 段首声明「在 %d 个 SKILL」，实际找到 %d 份 —— "
                           "少了说明有人删了一份（那个 SKILL 的判据已失效）、"
                           "多了说明新增那份没登记进声明。"
                           % (name, declared, len(members))),
            })
        if len(members) == 1:
            findings.append({
                "segment": name, "kind": "single-copy", "severity": "WARN",
                "files": [members[0]["file"]],
                "detail": "共享段 `%s` 只找到 1 份 —— 「共享」这个声明本身已失准" % name,
            })
    for u in unclosed:
        findings.append({
            "segment": u["name"], "kind": "unclosed",
            "files": [u["file"]], "line": u["line"],
            "detail": ("共享段 `%s` 在 %s:%d 起始却没有闭合标记 —— "
                       "整段无法参与比对，等于这份副本脱离了护栏"
                       % (u["name"], u["file"], u["line"])),
        })

    res = {"applicable": True, "reason": "", "segments": len(groups),
           "findings": findings, "files": files, "files_failed": failed,
           "checked": sum(len(v) for v in groups.values())}
    res.update(from_result(res, targets=files,
                           items=sum(len(v) for v in groups.values())).as_json())
    res["collected"]["files_failed"] = failed
    return res


def self_check():
    """阳性对照：造两份同名共享段、内容只差一个空格 → 必须报。"""
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    tpl = ('# >>> SHARED-SEGMENT: probe-seg >>>\n'
           '# 本段在 2 个 SKILL 的脚本里各持一份逐字节相同的副本\n'
           'PAT = r"REQ-%s"\n'
           '# <<< SHARED-SEGMENT: probe-seg <<<\n')
    try:
        for skill, pad in (("skill-a", ""), ("skill-b", " ")):
            sd = os.path.join(d, SKILLS_DIR, skill, "scripts")
            os.makedirs(sd)
            with open(os.path.join(sd, "x.py"), "w", encoding="utf-8") as f:
                f.write(tpl % ("NNN" + pad))
        res = run(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    drift = [f for f in res.get("findings") or [] if f["kind"] == "content-drift"]
    ok = len(drift) == 1
    print(json.dumps({"self_check": "pass" if ok else "fail",
                      "probe_hits": len(drift),
                      "findings": [f["kind"] for f in res.get("findings") or []]},
                     ensure_ascii=False))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        return self_check()

    res = run(os.path.abspath(a.root))
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 1 if res.get("findings") else 0
    if not res.get("applicable"):
        print("[SKIP] %s" % res.get("reason"))
        return 0
    hard = [f for f in res["findings"] if f.get("severity") != "WARN"]
    for f in res["findings"]:
        lvl = "WARN " if f.get("severity") == "WARN" else "ERROR"
        print("%s 共享段 `%s`（%s）：%s" % (lvl, f["segment"], f["kind"], f["detail"]))
        for ln in f.get("diff") or []:
            print("       %s" % ln)
        for p in f.get("files") or f.get("drifted") or []:
            print("       · %s" % p)
    print("[check_shared_segment] 巡检 %d 份 SKILL 脚本 / 共享段 %d 组 / 副本 %d 份 / 问题 %d"
          % (res["collected"]["targets"], res["segments"],
             res["collected"]["items"], len(res["findings"])))
    return 1 if (hard or res.get("starved")) else 0


if __name__ == "__main__":
    sys.exit(main())
