#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分片硬门索引：帮助定位章节，适用性判定仍以命令骨架表与分片正文为准。

输出只包含匹配到的标题和脚本入口，不证明未列出的义务不存在；摘要不授予跳过硬门的权限。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aidp_collect import from_result  # noqa: E402
from aidp_runtime import runtime_relpath  # noqa: E402

_HEADING = re.compile(r"^(#{2,6})\s+(.+?)\s*$")
_GATE_TITLE = re.compile(r"硬门|必须|不可跳过|铁律|门\b")
_GATE_LINE = re.compile(r"exit\s*1|判\s*FAIL|Critical|⛔")
_CMD = re.compile(r"^\s*(?:>\s*)?(python3|bash)\s+(?:" + re.escape("{{AIDP_HOME}}")
                  + "|" + re.escape(runtime_relpath("", __file__)) + r")/scripts/([\w\-./]+)")


def digest(path):
    """返回 {headings:[...], commands:[...], gate_hits:int}。"""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read(400_000).splitlines()
    except OSError as exc:
        return None, str(exc)

    cur, out, cmds, hits, in_fence = "", [], [], 0, False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if not in_fence:
            m = _HEADING.match(ln)
            if m:
                cur = m.group(2)
                if _GATE_TITLE.search(cur):
                    out.append(cur)
                continue
        if _GATE_LINE.search(ln):
            hits += 1
            if cur and cur not in out:
                out.append(cur)
        m2 = _CMD.match(ln) if in_fence else None
        if m2:
            c = m2.group(1) + " " + "{{AIDP_HOME}}/scripts/" + m2.group(2)
            if c not in cmds:
                cmds.append(c)
    return {"headings": out, "commands": cmds, "gate_hits": hits}, None


def run(root, rel_dir):
    base = os.path.join(root, rel_dir)
    res = {"applicable": os.path.isdir(base), "dir": rel_dir, "shards": [],
           "files": 0, "files_failed": 0}
    if not res["applicable"]:
        res["reason"] = "目录不存在：%s" % rel_dir
        res.update(from_result(res).as_json())
        return res
    for fn in sorted(os.listdir(base)):
        if not fn.endswith(".md") or fn in ("README.md", "rationale.md", "invariants.md"):
            continue
        d, err = digest(os.path.join(base, fn))
        res["files"] += 1
        if d is None:
            res["files_failed"] += 1
            res["shards"].append({"file": fn, "error": err})
            continue
        res["shards"].append({
            "file": fn,
            "size": os.path.getsize(os.path.join(base, fn)),
            "gate_sections": d["headings"][:6],
            "gate_hits": d["gate_hits"],
            "commands": d["commands"][:6],
        })
    res.update(from_result(res, targets=res["files"],
                           items=sum(s.get("gate_hits", 0) for s in res["shards"])).as_json())
    return res


HEADER = "⚠️ 本摘要只帮助定位章节；读取与适用性以命令骨架表和分片正文为准，不能依据摘要缺项跳过硬门。"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--dir", default=runtime_relpath("flows/sprint-autopilot", __file__),
                    help="相对运行真源的分片目录")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = run(os.path.abspath(a.root), a.dir)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["applicable"] and res["files"] and not res["files_failed"] else 2
    if not res["applicable"]:
        print("[ERROR] %s" % res.get("reason"))
        return 2
    print(HEADER)
    print()
    for s in res["shards"]:
        if s.get("error"):
            print("❌ %s —— 读取失败：%s" % (s["file"], s["error"]))
            continue
        print("── %s（%.1fKB · 硬门信号 %d）" % (s["file"], s["size"] / 1024, s["gate_hits"]))
        if s["gate_sections"]:
            print("   硬门小节：%s" % " / ".join(s["gate_sections"]))
        if s["commands"]:
            print("   确定性脚本：%s" % " · ".join(s["commands"]))
    print()
    print("共 %d 片 / 硬门信号合计 %d" % (res["files"], res["collected"]["items"]))
    return 0 if res["files"] and not res["files_failed"] else 2


if __name__ == "__main__":
    sys.exit(main())
