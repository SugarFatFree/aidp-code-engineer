#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量阳性对照 —— 一次植入 N 个探针、一次运行、一次移除、一次复跑。

## 为什么需要

约定 35 要求「静态验证工具在被当作『零新增』判据之前，必须先做一次阳性对照」。
这条纪律本身救过命（实测两次拆穿 `vue-tsc` 静默失效），但**手工循环的成本很高**：
下游一轮 8 条永久反向断言 × 4 步（植入 → 跑 → 移除 → 跑）= **32 次**编辑-运行循环，
加 3 处变异对照 ≈ **44 次**，每次还要跑分钟级的 `mvn test` / `vue-tsc`。
于是每个下游都在手搓同一套循环，而成本高的纪律最容易被省掉。

本工具把 4N 次压成 **4 次**：一次性植入全部探针 → 跑一次 → 一次性移除 → 复跑一次，
并产出「逐条断言 期望命中 / 实际命中 / 阳性对照是否变红」的表格。

## 关键设计

- **探针按「锚点 + 注入文本」声明**，由一份 JSON 描述（见 `--probes` 的 schema）；
  植入前对每个目标文件存一份原文快照，移除走**快照还原**而非反向替换 ——
  反向替换会在注入文本恰好与原文某处重合时改错地方。
- **⛔ 失败也必须还原**：任何异常 / 中断都走 `finally` 还原，否则探针会留在工作区
  （那比不做阳性对照更危险：一个必然报错的探针被当成真实缺陷提交）。
- **判据是「对照是否变红」，不是「有没有报错」**：阴性侧（未注入）必须绿、
  阳性侧（已注入）必须红，**两侧都对**才算该检查有效。只跑阳性侧证明得了「能红」，
  证明不了「不是恒红」—— 恒红的检查同样毫无判别力。
- 命中数**必须出示**：约定 35 的结论要求「零新增」时同时给出探针命中数 ≥1。

## 用法

    python3 {{AIDP_HOME}}/scripts/batch_probe.py --probes probes.json --cmd "npx vue-tsc --noEmit"
    python3 {{AIDP_HOME}}/scripts/batch_probe.py --probes probes.json --cmd "..." --json

`probes.json`：

    {"probes": [
      {"id": "A1", "file": "code/frontend/app/src/a.ts",
       "anchor": "export function foo", "inject": "const _p: number = 'x';",
       "expect": "TS2322"},
      {"id": "A2", "file": "code/backend/svc/src/main/java/B.java",
       "anchor": "class B", "inject": "int _p = \\"x\\";", "expect": "incompatible types"}
    ]}

`anchor` 为空时追加到文件末尾。`expect` 是**期望在输出里出现的字符串**（留空则只要
退出码变红即算命中）。

退出码：0 = 全部探针都被抓到且阴性侧为绿；1 = 有探针没被抓到 / 阴性侧本就红；2 = 入参错。
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


def _run(cmd, cwd, timeout):
    try:
        r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                           text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "[batch_probe] 命令超时（%ds）" % timeout
    except OSError as exc:
        return 125, "[batch_probe] 无法执行命令：%s" % exc


def snapshot(root, probes):
    """★ **先**把涉及的全部文件原文存好，再开始改。

    ⛔ 边存边改是错的：中途某个探针锚点找不到时，已改过的文件如果还没进快照，
      调用方就**无法还原**它 —— 工作区里留着一行必然报错的代码，而那比
      不做阳性对照更危险（它会被当成真实缺陷提交）。
    """
    snaps = {}
    for p in probes:
        rel = p["file"]
        if rel in snaps:
            continue
        path = Path(root, rel)
        if not path.resolve().is_relative_to(Path(root).resolve()) or not path.is_file():
            raise ValueError("探针目标必须是项目内现有文件：%s" % rel)
        snaps[rel] = path.read_bytes()
    return snaps


def _inject(root, probes, snapshots):
    """按快照植入全部探针（快照须由 `snapshot()` 预先取好）。"""
    for p in probes:
        rel = p["file"]
        path = os.path.join(root, rel)
        cur = Path(path).read_bytes().decode("utf-8")
        anchor = p.get("anchor") or ""
        inject = p["inject"]
        if anchor:
            if anchor not in cur:
                raise ValueError("探针 %s 的锚点在 %s 里找不到：%r"
                                 % (p.get("id"), rel, anchor[:60]))
            cur = cur.replace(anchor, anchor + "\n" + inject, 1)
        else:
            cur = cur.rstrip("\n") + "\n" + inject + "\n"
        Path(path).write_bytes(cur.encode("utf-8"))


def _restore(root, snapshots):
    """按快照还原 —— ⛔ 不做反向替换：注入文本恰好与原文某处重合时会改错地方。"""
    errs = []
    for rel, text in snapshots.items():
        try:
            Path(root, rel).write_bytes(text)
        except OSError as exc:
            errs.append("%s: %s" % (rel, exc))
    return errs


def run(root, probes, cmd, timeout):
    # ① 阴性侧（未注入）：必须绿 —— 否则无从分辨「探针被抓到」与「它本来就红」
    if not probes:
        return {"ok": False, "probe_count": 0, "probe_hits": 0, "rows": [],
                "verdict": "没有探针，不能证明检查有效"}
    neg_rc, neg_out = _run(cmd, root, timeout)

    snapshots, pos_rc, pos_out, inject_err = {}, None, "", ""
    try:
        # ★ 快照必须**先**全部取好，再开始改（见 snapshot() 的注释）
        snapshots = snapshot(root, probes)
        _inject(root, probes, snapshots)
        pos_rc, pos_out = _run(cmd, root, timeout)
    except (OSError, ValueError, KeyError) as exc:
        inject_err = str(exc)
    finally:
        # ⛔ 失败也必须还原：探针留在工作区比不做阳性对照更危险
        restore_errs = _restore(root, snapshots)

    restored_rc, _ = _run(cmd, root, timeout) if not restore_errs else (None, "")
    positive_failed = pos_rc is not None and pos_rc not in (0, 124, 125, 126, 127) and pos_rc > 0
    rows = []
    for p in probes:
        want = p.get("expect") or ""
        # 多探针必须能逐条区分，不能凭一条共享诊断或一个全局失败码把全组算命中。
        unambiguous = len(probes) == 1 or (bool(want) and sum(q.get("expect") == want for q in probes) == 1)
        got = (want in pos_out) if want else (pos_rc not in (0, None))
        base = (want in neg_out) if want else (neg_rc != 0)
        rows.append({
            "id": p.get("id") or p["file"],
            "file": p["file"],
            "expect": want,
            "unambiguous": bool(unambiguous),
            "hit_with_probe": bool(got),
            "hit_without_probe": bool(base),
            # ★ 判据是「对照变红」：阳性侧命中且阴性侧未命中，两侧都对才算有效
            "reddened": bool(unambiguous and positive_failed and got and not base),
        })

    ok = (not inject_err and not restore_errs and neg_rc == 0
          and restored_rc == 0 and all(r["reddened"] for r in rows))
    return {
        "ok": ok,
        "probe_count": len(probes),
        "probe_hits": sum(1 for r in rows if r["reddened"]),
        "negative_exit_code": neg_rc,
        "positive_exit_code": pos_rc,
        "restored_exit_code": restored_rc,
        "rows": rows,
        "inject_error": inject_err,
        "restore_errors": restore_errs,
        "verdict": _verdict(ok, neg_rc, rows, inject_err, restore_errs),
    }


def _verdict(ok, neg_rc, rows, inject_err, restore_errs):
    if inject_err:
        return "探针植入失败：%s —— 本次**不构成**阳性对照" % inject_err
    if restore_errs:
        return "⛔ 探针还原失败：%s —— 请立即手工还原，工作区里留着必然报错的代码" \
            % "; ".join(restore_errs)
    if neg_rc != 0:
        return ("阴性侧（未注入）本就红（exit %s）—— 先把既有问题清掉，"
                "否则无从分辨「探针被抓到」与「它本来就红」" % neg_rc)
    miss = [r["id"] for r in rows if not r["reddened"]]
    if miss:
        return ("⛔ %d 个探针**没被抓到**：%s —— 该检查当前抓不到本该抓到的东西，"
                "⛔ 不得据其输出宣称「零新增」；多探针需逐条独有的诊断文本，不能共用全局退出码" % (len(miss), "、".join(miss)))
    if not ok:
        return "⛔ 移除探针后检查未恢复通过，阳性对照不成立"
    return ("✅ %d/%d 个探针全部被抓到、且阴性侧为绿 —— 该检查此刻有效，"
            "其「零新增」结论可采信（结论里须一并出示本命中数）"
            % (len(rows), len(rows)))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--probes", required=True, help="探针声明 JSON（schema 见文件头）")
    ap.add_argument("--cmd", required=True, help="被验证的静态检查命令")
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        with open(a.probes, encoding="utf-8") as f:
            probes = (json.load(f) or {}).get("probes") or []
    except (OSError, ValueError) as exc:
        print("[batch_probe] 探针声明读取失败：%s" % exc, file=sys.stderr)
        return 2
    if not probes:
        print("[batch_probe] 探针声明为空 —— 没有探针就没有阳性对照", file=sys.stderr)
        return 2

    res = run(os.path.abspath(a.root), probes, a.cmd, a.timeout)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("探针  期望命中                 带探针  不带探针  变红")
        for r in res["rows"]:
            print("%-6s %-24s %-7s %-9s %s"
                  % (r["id"][:6], (r["expect"] or "(仅看退出码)")[:24],
                     "是" if r["hit_with_probe"] else "否",
                     "是" if r["hit_without_probe"] else "否",
                     "✅" if r["reddened"] else "❌"))
        print()
        print("阴性侧退出码 %s / 阳性侧退出码 %s / 探针命中 %d/%d"
              % (res["negative_exit_code"], res["positive_exit_code"],
                 res["probe_hits"], res["probe_count"]))
        print(res["verdict"])
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
