#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 22 义务登记门 —— 「归档里写了要级联，台账里查无此事」。

## 它堵的是哪条路径

约定 22 的攒批机制有一组**机器可扫的载体**：四族 `_开发期{族}增量.md`。收口点靠扫它们派单、
终态门靠扫它们判断收没收干净。而增量册**在上一批级联完成后按规定被删除**（清空即删文件）——
删除只表示"当前批已清空"，**不表示本版不再需要增量册**。

于是出现这条静默路径：Sprint 后半段又产生了实现期订正，执行体把它写进了
**Sprint 归档 markdown**（"以下四条须按约定 22 回灌"，还逐条点了名），
却**没有重建增量册**。归档是给人读的叙述，没有任何脚本会扫它。结果：

  · 收口点扫增量册 → 四族都不存在 → "无待级联" → 不派单
  · 终态门扫增量册 → 文件不存在 → 合法终态 → 放行
  · 义务只活在散文里，直到 build 终审才被 `version-auditor` 判 Critical

真实回流：该同型问题在同一个下游**连续三个版本复发**（收口期 / 规划期 / 开发段），
`version-auditor` 三次判 Critical。其中一条的后果是「文档双必填 vs 实现二选一」——
按文档写校验会让某类卡片**点一次报一次 400**。

## 判据（刻意只做一层，不做逐条映射）

**归档里存在"未完成的约定 22 义务"表述 ⟹ 至少一族增量册必须存在且有未决条目。**

不做「归档第 N 条 ↔ 台账第 M 条」的逐条映射：多条订正常被合并成一条台账条目，
逐条映射会产出大量假阳性，最终被人加豁免绕过。本门只断言**载体存在**——
这恰好是三次复发的共同断点，而且是唯一能确定性判定的那一层。
归档里的义务原文**逐条打印出来**，覆盖是否完整交给读的人判断。

已在本轮完成的义务不计入（行内含 `已级联` / `已回灌` / `--cascade-now` 等完成标记）。

## 退出码

  0 = 无未登记义务（含"归档里根本没写义务"）
  2 = 归档有未完成义务、台账却查无此事
  1 = 参数或路径错误（fail-closed）

## 用法

    check_cascade_obligation.py --version V0.14.0 [--sprint 045] [--user alice]
                               [--root .] [--json]

不传 `--sprint` 扫该版本全部 Sprint 归档 + 当前 `activeContext.md`
（归档发生在 `/sprint-close` Step 3，本门在其后跑，两者都要看）。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import json
import os
import re
import subprocess
import sys

# 义务表述：出现即说明"这里承诺了一件约定 22 的事，但还没做"
_OBLIGATION_RE = re.compile(
    r"(须|需|待|应|要)(按)?约定\s*22"
    r"|约定\s*22.{0,8}(回灌|级联|同步)"
    r"|(须|需|待|应|要)(回灌|级联)"
    r"|(回灌|级联)(义务|清单|待办)"
    r"|待级联")
# 完成标记：同一行里出现即视为本轮已做完，不再要求台账登记
_DONE_RE = re.compile(
    r"已级联|已回灌|已完成回灌|已完成级联|本轮已级联|已当场级联|cascade-now|已落台账|已登记台账|已落增量册|已登记增量册")


def _pending_cascade():
    """复用 commit_gate 的增量册解析——收口点、终态门、本门必须对同一组册子读数一致。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from commit_gate import pending_cascade
    return pending_cascade


def _git_user(root):
    try:
        cp = subprocess.run(["git", "-C", root, "config", "user.name"],
                            capture_output=True, text=True, timeout=20)
        return (cp.stdout or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _archive_files(root, version, user, sprint):
    """待扫文件：Sprint 归档 + 当前 activeContext（归档在 Step 3，本门在其后，两者都要看）。"""
    base = os.path.join(root, "memory", version, user)
    if not os.path.isdir(base):
        return None, f"memory/{version}/{user}/ 不存在（--user 传对了吗）"
    files = []
    sprints_dir = os.path.join(base, "sprints")
    if os.path.isdir(sprints_dir):
        for fn in sorted(os.listdir(sprints_dir)):
            if not fn.endswith(".md") or not fn.startswith("sprint-"):
                continue
            if sprint and sprint not in fn:
                continue
            files.append(os.path.join(sprints_dir, fn))
    ac = os.path.join(base, "activeContext.md")
    if os.path.isfile(ac) and not sprint:
        files.append(ac)
    elif os.path.isfile(ac) and sprint:
        # 指定 Sprint 时 activeContext 可能还没归档，内容即该 Sprint 的
        files.append(ac)
    return files, None


def run(root, version, user, sprint):
    files, err = _archive_files(root, version, user, sprint)
    if files is None:
        return {"ok": False, "error": "no-memory-dir", "detail": err}
    if not files:
        return {"ok": False, "error": "no-archive",
                "detail": f"{version}/{user} 下没有可扫的 Sprint 归档或 activeContext"
                          f"{'（--sprint ' + sprint + ' 无匹配）' if sprint else ''}"}
    obligations, done = [], []
    for path in files:
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError as exc:
            return {"ok": False, "error": "unreadable", "detail": f"{rel}: {exc}"}
        for idx, line in enumerate(lines):
            if not _OBLIGATION_RE.search(line):
                continue
            rec = {"file": rel, "line": idx + 1, "text": line.strip()[:200]}
            (done if _DONE_RE.search(line) else obligations).append(rec)

    pc = _pending_cascade()(root)
    vinfo = (pc.get("versions") or {}).get(version) or {}
    # ★ 存在性 = 本版**四族任一**增量册（含存量单册台账）存在，由 pending_cascade 的
    #   families 聚合读数给出。⛔ 绝不用某条硬编码路径去 isfile：拆四族之后没有哪一份
    #   是"那一份"，写死任一条都会在"本版只改了设计"这类正常情形下判成不存在（静默误报）。
    fams = (vinfo.get("families") or {})
    ledger_files = [str(f.get("file")) for f in fams.values() if isinstance(f, dict)]
    ledger_exists = bool(ledger_files)
    ledger_rel = "、".join(ledger_files) if ledger_files else (
        f"docs/requirements/{version}/研发需求/_开发期需求增量.md 等四族增量册（均不存在）")
    pending = int(vinfo.get("total") or 0)
    unparsed = [u for u in (pc.get("unparsed") or []) if version in str(u)]

    res = {"ok": True, "version": version, "user": user, "sprint": sprint or "*",
           "scanned_files": [os.path.relpath(f, root).replace(os.sep, "/") for f in files],
           "obligations": obligations, "done_marked": done,
           "ledger": {"path": ledger_rel, "exists": ledger_exists,
                      "pending": pending, "unparsed": unparsed},
           "error": None}
    if obligations and not (ledger_exists and pending > 0):
        res["ok"] = False
    # 台账在、却一条都解析不出 = 格式漂移，等同于"载体形同虚设"，同样不放行
    if obligations and ledger_exists and unparsed:
        res["ok"] = False
    return res


def main():
    ap = argparse.ArgumentParser(
        description="约定 22 义务登记门：Sprint 归档写下的级联/回灌义务必须同轮落进台账")
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", required=True)
    ap.add_argument("--user", default="", help="缺省取 git config user.name")
    ap.add_argument("--sprint", default="", help="只扫某个 Sprint（如 045）；缺省扫全部")
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

    user = args.user or _git_user(args.root)
    if not user:
        sys.stderr.write("❌ 取不到 --user（git config user.name 也为空）\n")
        return 1

    res = run(args.root, args.version, user, args.sprint)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res.get("ok") else (1 if res.get("error") else 2)

    if res.get("error"):
        sys.stderr.write(f"❌ 义务登记门无法判定（{res['error']}）：{res['detail']}\n"
                         "   fail-closed：给不出结论就是不通过\n")
        return 1

    n_ob, n_done = len(res["obligations"]), len(res["done_marked"])
    led = res["ledger"]
    if res["ok"]:
        if not n_ob:
            print(f"[OK] 归档未声明未完成的约定 22 义务"
                  f"（扫 {len(res['scanned_files'])} 份；{n_done} 条已标完成）")
        else:
            print(f"[OK] 归档声明 {n_ob} 条约定 22 义务，台账已承载"
                  f"（{led['path']}，{led['pending']} 条未决）")
            for o in res["obligations"]:
                print(f"   · {o['file']}:{o['line']}  {o['text']}")
            print("   ⚠️ 本门只断言【载体存在】，不做逐条映射——覆盖是否完整请对照上面几行自查。")
        return 0

    sys.stderr.write(f"❌ 归档声明了 {n_ob} 条约定 22 义务，但台账查无此事：\n")
    for o in res["obligations"]:
        sys.stderr.write(f"   · {o['file']}:{o['line']}\n     {o['text']}\n")
    if not led["exists"]:
        sys.stderr.write(f"   台账 {led['path']} 不存在。\n"
                         "   ⛔ 台账被删只表示「当前批已清空」，不表示本版不再需要它——"
                         "它是 append-only 的活文件，新订正须重建。\n")
    elif led["unparsed"]:
        sys.stderr.write(f"   台账 {led['path']} 存在但一条都解析不出（格式漂移）"
                         "——载体形同虚设，同样不放行。\n")
    else:
        sys.stderr.write(f"   台账 {led['path']} 存在但 0 条未决条目。\n")
    sys.stderr.write(runtime_text('   处置：把这些义务**同轮**写进对应族的增量册（骨架 `__AIDP_HOME__/templates/_开发期族增量.md`），或当场级联完并在归档行内标「已级联」。\n   判定自省：**收尾门/审计能不能靠脚本发现这条义务？不能 → 它还没被登记。**\n   归档 markdown 是给人读的叙述，台账才是给机器扫的清单。\n   详规 `__AIDP_HOME__/reference/开发期族增量.md`\n', __file__))
    return 2


if __name__ == "__main__":
    sys.exit(main())
