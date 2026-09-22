#!/usr/bin/env python3
"""check_index_staleness.py — 「内容已变、`git status` 却报 clean」的隐形漂移守卫。

## 这道门堵的是什么

git 判断「文件改没改」走的是 **stat 快速路径**：index 里记的 `(size, mtime)` 与磁盘一致时
**不重新哈希**。于是只要某个写入器把**源文件的 mtime 原样带给目标文件**（`shutil.copy2`
就是这么干的），就会出现一种没有任何提示的状态——

    磁盘内容 ≠ index 记录的内容，而 `git status` / `git diff` 双双报 clean。

它比"忘了提交"严重得多，因为**所有基于工作区的检查都会绿**：

  · `mirror_to_bundle.py --check` 与 `verify.py` 比的都是工作区文件 → 永远一致；
  · 从 HEAD 重新克隆一份再跑 `verify.py` → 立刻一堆「脚手架副本漂移」ERROR；
  · `CONTRACT_MANIFEST.json` 记的是**未提交内容**的指纹 ⇒ 每个下游初始化后天生带一批
    「契约文件正文与脚手架不一致」WARN，且升级永远清不掉。

实测命中过 7 份 bundle 副本，成因正是 `mirror_to_bundle.py` 当时用的 `shutil.copy2`。
根因已修（改 `write_bytes`），本门是**防复发的兜底**：任何新写入器只要再犯同一个错，这里会红。

## 判据

对扫描面内每个已跟踪文件，比 `git hash-object <文件>` 与 index 记录的 blob：
不相等、**且 `git status` 没把它列出来** → ERROR（这就是隐形漂移）。
不相等但 `git status` 列出来了 = 正常的未提交改动，**不报**。

扫描面默认 `.aidp`（脚手架契约与 bundle 全在这里），`--path` 可加。
非 git 仓库 / git 不可用 → unsupported（退出码 3）。

退出码：0 通过；1 有 ERROR；2 参数错；3 无 Git 能力。
"""
import argparse
import json
import os
import subprocess
import sys

from vcs import detect_mode, unsupported, EXIT_UNSUPPORTED

DEFAULT_PATHS = (".aidp",)


def _git(root, args, stdin=None):
    return subprocess.run(["git", "-C", root] + args, capture_output=True,
                          text=True, input=stdin)


def run(root=".", paths=None):
    res = {"scanned": 0, "errors": [], "skipped": None}
    if detect_mode(root) != "git":
        return unsupported("index")
    paths = list(paths or DEFAULT_PATHS)

    # ⛔ 两处 git 调用都必须用 `-z`（NUL 分隔、原样输出路径）。默认的 `core.quotepath=on`
    #   会把非 ASCII 路径整条包成 C 转义串（`"\347\224\237..."`），转义串进了下面的
    #   `os.path.isfile` 恒为 False ⇒ 该类文件被**静默**踢出巡检面、scanned 计数跟着少，
    #   不留任何痕迹。而约定 14 要求 AIDP 产物**文件名也用中文** —— 于是这道门恰好对本仓
    #   最主要的命名形态完全失明（实证：1850 份里 125 份中文名被丢，7 处真实漂移一处没报）。
    # git status 列出的 = 正常可见的改动，不算隐形
    visible = set()
    for ent in _git(root, ["status", "--porcelain", "-z"] + paths).stdout.split("\0"):
        if len(ent) > 3:
            visible.add(ent[3:].strip())

    # index 记录的 blob（`ls-files -s -z` 的每条形如 `<mode> <sha> <stage>\t<path>`）
    idx = {}
    for ent in _git(root, ["ls-files", "-s", "-z"] + paths).stdout.split("\0"):
        head, _, path = ent.partition("\t")
        bits = head.split()
        if len(bits) >= 2 and path:
            idx[path] = bits[1]
    if not idx:
        res["passed"] = True
        return res

    # 批量哈希（一次 git 调用，1800 份 ≈ 1s）
    names = [p for p in idx if os.path.isfile(os.path.join(root, p))]

    # ★ 巡检面缩水本身就是一条发现 —— 上面那次失明能潜伏至今，正因为"少扫了 125 份"
    #   与"扫完没问题"在输出上完全同形。已跟踪却在磁盘上取不到、且 `git status` 也没报的
    #   路径，要么是解码问题（门瞎了），要么是文件真没了（也该有人知道），两种都不许静默。
    res["dropped"] = sorted(set(idx) - set(names))
    for miss in res["dropped"]:
        if miss not in visible:
            res["errors"].append({
                "file": miss,
                "index": idx[miss][:12],
                "actual": "<磁盘上取不到>",
                "msg": "已跟踪但磁盘读不到、`git status` 也没报 —— 巡检面在此处缩水，"
                       "这道门对该文件等同不存在",
            })
    out = _git(root, ["hash-object", "--stdin-paths"], stdin="\n".join(names) + "\n").stdout.split()
    res["scanned"] = len(names)
    for path, real in zip(names, out):
        if real != idx[path] and path not in visible:
            res["errors"].append({
                "file": path,
                "index": idx[path][:12],
                "actual": real[:12],
                "msg": "内容与 index 不一致，但 `git status` 看不见它 —— "
                       "提交面与工作区面已分叉，所有基于工作区的检查都会假绿",
            })
    res["passed"] = not res["errors"]
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description="隐形漂移（内容变了但 git status 报 clean）守卫")
    ap.add_argument("--root", "--repo-root", dest="root", default=".")
    ap.add_argument("--path", action="append", help="扫描面（可重复，默认 .aidp）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        sc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selfcheck.py")
        return subprocess.call([sys.executable, sc, "--only", os.path.basename(__file__)])
    r = run(a.root, a.path)
    if r.get("status") == "unsupported":
        print(json.dumps(r, ensure_ascii=False))
        return EXIT_UNSUPPORTED
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif r.get("skipped"):
        print("跳过：%s" % r["skipped"])
    else:
        print("巡检 %d 份已跟踪文件" % r["scanned"])
        for e in r["errors"]:
            print("❌ %s（index=%s 实际=%s）" % (e["file"], e["index"], e["actual"]))
            print("   %s" % e["msg"])
        if r["errors"]:
            print("   → 修法：`touch` 这些文件后 `git add` 提交真实内容；"
                  "并检查写入器是否用了 `shutil.copy2`（它会把源 mtime 带过去，"
                  "正好落进 git 的 stat 快速路径）——一律改 `write_bytes`")
        print("结论：%s" % ("✅ 无隐形漂移" if r["passed"] else "❌ %d 处" % len(r["errors"])))
    return 0 if r["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
