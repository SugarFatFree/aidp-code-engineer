#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check_design_goals.py — `设计目标.md` 的**指纹棘轮 + 实现名词体检**。

设计目标有两条性质，别处的检查都不管：

1. **它只该写「最终要达成什么」**——不写过程、不写怎么做到的。判据是"这句话会不会
   因为实现细节变化而需要跟着改"。可这句判据是语义的，人写着写着就会带进实现名词
   （文件名 / flag / 脚本名 / 步骤号），一带进来，目标就开始跟着命令一起漂。
2. **它轻易不该被改**。目标稳定是它作为参照系的全部价值：命令天天改、目标跟着动，
   审计就变成"拿今天的实现去核对今天刚按实现改过的目标"，恒绿且毫无意义。

这两条以前都只是散文纪律，没有任何机器拦得住——实测形态正是：每次改命令都顺手把
目标改一点，几轮下来目标里塞满了"违约信号""边界例外"，体积从一页涨到 33KB。

故本脚本做两件事：

- **棘轮**：把每条 `G-<域>-<序号>` 的正文做指纹存进 baseline；改一个字 / 删一条 /
  换一处措辞都 ERROR，必须由**人**显式 `--update-baseline` 重新定基。⛔ 执行体不得
  顺手 `--update-baseline`——那等于棘轮不存在。
- **体检**：扫每条目标里的实现名词（`xxx.md` / `xxx.py` / `--flag` / `Step N.N` /
  反引号里的路径）。目标句里出现它们 = 写进来的是实现，ERROR 并点名。

**新增目标不算违约**（棘轮只拦"改动与删除"）：新增条目直接记入 baseline，因为新增
不会让老审计报告里的编号改变含义；而**改写与删除会**。

下游项目没有 `设计目标.md`（模板专属、不下发）→ 直接 INFO 跳过、退出码 0。

用法：
    python3 AIDP_HOME/scripts/check_design_goals.py [--root .] [--json]
    python3 AIDP_HOME/scripts/check_design_goals.py --update-baseline   # 人工定基
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import hashlib
import json
import os
import re
import sys

GOAL_RE = re.compile(r"^-\s+\*\*(G-[A-Z]+-\d+)\*\*\s*[—-]\s*(.+?)\s*$")
GROUP_RE = re.compile(r"^###\s+(G-[A-Z]+)\s")
BASELINE = runtime_text('__AIDP_HOME__/scripts/design-goals-baseline.txt', __file__)
DOC = "设计目标.md"

# ★ 实现名词模式：出现即说明这条写的是"怎么做"，不是"要达成什么"。
#   ⛔ 别放宽到"整份文档扫一遍"——文件头的维护纪律段本来就要点名脚本与文件，
#   那是合法的；只扫【目标句本身】。
IMPL_PATTERNS = [
    (re.compile(r"[\w./-]+\.(?:md|py|json|ya?ml|txt|sh)\b"), "文件名"),
    (re.compile(r"(?<![\w-])--[a-z][a-z0-9-]+"), "命令行 flag"),
    (re.compile(r"(?:Step|步骤)\s*\d+(?:\.\d+)*"), "步骤号"),
    (re.compile(r"Phase\s*\d"), "Phase 号"),
    (re.compile(r"`[^`]*/[^`]*`"), "路径"),
    (re.compile(r"\b[a-z_]+\.py::"), "函数落点"),
]


def _fp(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def parse_goals(root):
    """返回 [(anchor, text, lineno)]，只取第三节里的条目。"""
    path = os.path.join(root, DOC)
    if not os.path.isfile(path):
        return None
    out, in_sec3 = [], False
    with open(path, encoding="utf-8") as fh:
        for i, ln in enumerate(fh, 1):
            if re.match(r"^##\s*三、", ln):
                in_sec3 = True
                continue
            if in_sec3 and re.match(r"^##\s+(?!#)", ln):
                break
            if not in_sec3:
                continue
            m = GOAL_RE.match(ln.rstrip("\n"))
            if m:
                out.append((m.group(1), m.group(2), i))
    return out


def load_baseline(root):
    """→ (活跃锚点 {anchor: fp}, 退役锚点 set)。

    ★ 退役段用 `# RETIRED <锚点>` 行承载。⛔ 没有它时，「已退役的序号不再复用」这条纪律
      **全仓零执行**：baseline 只存活着的条目，棘轮对纯新增一律放行 —— 任何人写一条
      全新的 `G-DEV-2`（历史上它指的是别的东西）门都恒绿，而老审计报告里的同名锚点
      从此指向两件事。锚点的"永久"性质此前完全靠人记。
    """
    path = os.path.join(root, BASELINE)
    base, retired = {}, set()
    if not os.path.isfile(path):
        return base, retired
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            ln = ln.strip()
            if ln.startswith("# RETIRED "):
                parts = ln.split()
                if len(parts) >= 3:
                    retired.add(parts[2])
                continue
            if not ln or ln.startswith("#"):
                continue
            anchor, _, fp = ln.partition(" ")
            if fp:
                base[anchor] = fp
    return base, retired


def write_baseline(root, goals):
    """重新定基。★ 本次消失的锚点**自动转入退役段**，不是丢弃——丢了就等于允许复用。"""
    path = os.path.join(root, BASELINE)
    prev, retired = load_baseline(root)
    cur_anchors = {a for a, _, _ in goals}
    retired |= (set(prev) - cur_anchors)
    retired -= cur_anchors          # 退役后又被复活的，算活跃
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("# 设计目标棘轮 baseline —— `<锚点> <正文指纹>`，由 check_design_goals.py 维护。\n")
        fh.write("# ⛔ 不要手改本文件；改目标请改 `设计目标.md` 后由【人】跑 --update-baseline 定基。\n")
        fh.write("# `# RETIRED <锚点>` = 已退役、**编号永不复用**（老审计报告里还引着它）。\n")
        for anchor, text, _ in goals:
            fh.write("%s %s\n" % (anchor, _fp(text)))
        for a in sorted(retired):
            fh.write("# RETIRED %s\n" % a)


def main():
    ap = argparse.ArgumentParser(description="设计目标棘轮 + 实现名词体检")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--update-baseline", action="store_true",
                    help="把当前目标正文重新定基（⛔ 人工动作，执行体不得顺手调用）")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    goals = parse_goals(args.root)
    if goals is None:
        msg = "无 %s（模板项目专属、不下发），跳过" % DOC
        print(json.dumps({"skipped": True, "reason": msg}, ensure_ascii=False)
              if args.json else "[INFO] " + msg)
        return 0

    if args.update_baseline:
        write_baseline(args.root, goals)
        print("[OK] 已重新定基 %d 条目标 → %s" % (len(goals), BASELINE))
        return 0

    errors = []

    # ① 实现名词体检（只扫目标句本身）
    for anchor, text, lineno in goals:
        for pat, label in IMPL_PATTERNS:
            hit = pat.search(text)
            if hit:
                errors.append({
                    "type": "impl-noun", "anchor": anchor, "line": lineno,
                    "detail": "目标句里出现%s「%s」——写进来的是实现、不是目标" % (label, hit.group(0)),
                })
                break

    # ② 指纹棘轮：改动与删除都拦；新增放行
    base, retired = load_baseline(args.root)
    cur = {a: _fp(t) for a, t, _ in goals}
    lineno_of = {a: n for a, _, n in goals}
    if not base:
        errors.append({"type": "no-baseline", "anchor": "-", "line": 0,
                       "detail": "baseline 缺失：先由人跑一次 --update-baseline 定基"})
    else:
        for anchor, fp in base.items():
            if anchor not in cur:
                errors.append({"type": "goal-removed", "anchor": anchor, "line": 0,
                               "detail": "目标被删除——退役锚点应保留编号不复用；确要退役请人工 --update-baseline"})
            elif cur[anchor] != fp:
                errors.append({"type": "goal-changed", "anchor": anchor,
                               "line": lineno_of.get(anchor, 0),
                               "detail": "目标正文被改动——目标应稳定；确因需求变化要改请人工 --update-baseline"})

    added = sorted(set(cur) - set(base)) if base else []
    # ★ 复用已退役编号 = 同一个 `G-XXX-N` 在老审计报告与新文档里指两件事。
    #   棘轮对纯新增放行，故这一类**只能靠退役段拦**。
    for a in added:
        if a in retired:
            errors.append({"type": "goal-anchor-reused", "anchor": a,
                           "line": lineno_of.get(a, 0),
                           "detail": "复用了已退役的锚点编号——老审计报告仍引着它，"
                                     "同号两义无从分辨；请改用新编号"})

    if args.json:
        print(json.dumps({"skipped": False, "goals": len(goals), "added": added,
                          "errors": errors}, ensure_ascii=False, indent=2))
    else:
        if errors:
            print("[ERROR] 设计目标闸门未通过（%d 项）：" % len(errors))
            for e in errors:
                loc = "%s:%d" % (DOC, e["line"]) if e["line"] else DOC
                print("  - [%s] %s @ %s — %s" % (e["type"], e["anchor"], loc, e["detail"]))
            print("  ⛔ `设计目标.md` 轻易不得更改：命令天天改、目标跟着动，审计就退化成")
            print("     「拿今天的实现核对今天刚按实现改过的目标」——恒绿且毫无意义。")
            print("     确因【需求变化】要改目标：先改本文件、再改实现，然后由人跑")
            print(runtime_text('     `python3 __AIDP_HOME__/scripts/check_design_goals.py --update-baseline`。', __file__))
        else:
            extra = ("，新增 %d 条" % len(added)) if added else ""
            print("[OK] 设计目标 %d 条：指纹与 baseline 一致、无实现名词%s" % (len(goals), extra))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
