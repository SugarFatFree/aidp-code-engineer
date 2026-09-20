#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_release_debt_landing.py —— 发布期失败兜底必须**落账**，不能只喊话。

## 它拦什么

`/version` 的「失败兜底可追溯铁律」要求：发布期各步的 WARN 级兜底**都必须登记**到
`docs/audit/{version}/发布欠账.md`。但这条铁律此前只写在文档里，靠人守——
实测漏了一步（3.3.12bis 零残留断言总闸），其失败分支是一句 `echo`：

    python3 .../check_release_residual_gate.py … || echo "⚠️ 未过 → 按 3.3.13 同款登记 …"

只喊话的后果不是"少一条记录"，而是**这条欠账在产物上与「这步通过了」完全同形**：
发布报告读台账读不到它、`--finalize-docs` 驱动补跑也拿不到它，等于发布期把它吞了。

## 判据（刻意保守，宁可漏报不误报）

扫 `.aidp/flows/version/release-*.md` 的 bash 围栏，找形如
`python3 …/check_*.py …` 且紧随 `||` 兜底的语句；该兜底块内若**没有**出现
`发布欠账.md`，判 ERROR。

⛔ 不查没有 `||` 的调用——那是硬阻断（失败即 exit），本就不需要落账。
⛔ 不查 `|| echo 0` 这类取默认值的写法（兜底块里没有 `⚠️`/`登记`/`欠账` 语义词时跳过）。
"""
import os
import re
import sys

SCAN_DIR = os.path.join(".aidp", "flows", "version")
DEBT_FILE = "发布欠账.md"
# ★ 唯一写入口（推荐形态）：调它比手写 printf 样板更好 —— 格式由脚本保证、
#   调用点只剩一行，不会因为分片逼近 20480 上限而被压成一句 echo。
DEBT_WRITER = "release_debt.py"
CALL_RE = re.compile(r"python3\s+\S*?(check_[a-z_]+\.py)")
# 兜底块的语义词：只有像"失败处置"的才查（排除 `|| echo 0` 这类取默认值）
FALLBACK_HINT = re.compile(r"⚠️|登记|欠账|未过|失败|跳过|WARN")


def _fences(text):
    out, cur, inside = [], [], False
    for i, ln in enumerate(text.splitlines(), 1):
        if ln.strip().startswith("```"):
            if inside:
                out.append(cur)
                cur = []
            inside = not inside
            continue
        if inside:
            cur.append((i, ln))
    return out


def scan(root="."):
    base = os.path.join(root, SCAN_DIR)
    res = {"ok": True, "scanned": 0, "checked": 0, "errors": []}
    if not os.path.isdir(base):
        res["skipped"] = "no-release-flows"
        return res
    for fn in sorted(os.listdir(base)):
        if not (fn.startswith("release-") and fn.endswith(".md")):
            continue
        p = os.path.join(base, fn)
        res["scanned"] += 1
        text = open(p, encoding="utf-8", errors="replace").read()
        for fence in _fences(text):
            joined = "\n".join(l for _, l in fence)
            for m in CALL_RE.finditer(joined):
                # 从该调用起，取到下一个空行或围栏尾，作为它的兜底块
                start = joined.rfind("\n", 0, m.start()) + 1
                tail = joined[start:]
                blk = tail.split("\n\n", 1)[0]
                if "||" not in blk:
                    continue                    # 硬阻断，无需落账
                fb = blk.split("||", 1)[1]
                if not FALLBACK_HINT.search(fb):
                    continue                    # `|| echo 0` 这类取默认值
                res["checked"] += 1
                if DEBT_FILE in fb or DEBT_WRITER in fb:
                    continue
                line = fence[0][0] + joined[:m.start()].count("\n")
                res["errors"].append({
                    "file": f"{SCAN_DIR}/{fn}".replace(os.sep, "/"),
                    "line": line, "script": m.group(1),
                    "msg": f"{m.group(1)} 的失败兜底只喊话、未写 {DEBT_FILE} —— "
                           f"这条欠账在产物上与「本步通过」完全同形，"
                           f"发布报告与 --finalize-docs 都读不到它"})
    res["ok"] = not res["errors"]
    return res


def _self_check():
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    ok = []
    try:
        fl = os.path.join(d, SCAN_DIR)
        os.makedirs(fl)
        bad = ("```bash\n"
               'python3 .aidp/scripts/check_x.py --version "$V" \\\n'
               '  || echo "⚠️ 未过 → 请登记欠账"\n'
               "```\n")
        open(os.path.join(fl, "release-9.md"), "w", encoding="utf-8").write(bad)
        r = scan(d)
        ok.append(("★ 阳性：失败兜底只 echo → 报出", not r["ok"] and r["errors"]))
        good = ("```bash\n"
                'python3 .aidp/scripts/check_x.py --version "$V" \\\n'
                '  || { echo "⚠️ 未过"; echo "- x" >> "docs/audit/$V/发布欠账.md"; }\n'
                "```\n")
        open(os.path.join(fl, "release-9.md"), "w", encoding="utf-8").write(good)
        ok.append(("阴性：兜底里写了发布欠账.md → 放行", scan(d)["ok"]))
        viaw = ("```bash\n"
                'python3 .aidp/scripts/check_x.py --version "$V" \\\n'
                '  || python3 .aidp/scripts/release_debt.py --version "$V" --step 1 --title x\n'
                "```\n")
        open(os.path.join(fl, "release-9.md"), "w", encoding="utf-8").write(viaw)
        ok.append(("★ 阴性：走唯一写入口 release_debt.py 也算落账（推荐形态）", scan(d)["ok"]))
        hard = ("```bash\n"
                'python3 .aidp/scripts/check_x.py --version "$V" || exit 1\n'
                "```\n")
        open(os.path.join(fl, "release-9.md"), "w", encoding="utf-8").write(hard)
        r3 = scan(d)
        ok.append(("★ 阴性：硬阻断（|| exit 1）不要求落账，且不计入 checked",
                   r3["ok"] and r3["checked"] == 0))
        dflt = ("```bash\n"
                'N=$(python3 .aidp/scripts/check_x.py --count || echo 0)\n'
                "```\n")
        open(os.path.join(fl, "release-9.md"), "w", encoding="utf-8").write(dflt)
        ok.append(("★ 阴性：`|| echo 0` 取默认值不是失败兜底 → 不误报", scan(d)["ok"]))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for n, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + n)
    return 0 if all(r for _, r in ok) else 1


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(description="发布期失败兜底必须落账（不能只喊话）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    r = scan(a.root)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
        return 0 if r["ok"] else 1
    if r.get("skipped"):
        print(f"[SKIP] {r['skipped']}")
        return 0
    if r["ok"]:
        print(f"[OK] 发布期失败兜底均已落账（巡检 {r['scanned']} 份、核 {r['checked']} 处兜底）")
        return 0
    for e in r["errors"]:
        sys.stderr.write(f"  [ERROR] {e['file']}:{e['line']} — {e['msg']}\n")
    sys.stderr.write("   改法（推荐）：`|| python3 .aidp/scripts/release_debt.py "
                     "--version \"$VERSION\" --step <步骤号> --title <一句话> --redo <复现命令>`；"
                     "也可手写追加（照抄 release-7c.md 的形态）\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
