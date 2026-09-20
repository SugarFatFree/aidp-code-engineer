#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一个版本号在整个仓库里改名（目录 / 文件名 / 正文 / 代码内自报版本）。

## 为什么需要本脚本

开发期先用一个临时编号（`V0.12.2`），发布时按 SemVer 正名（`V0.13.0`）——这是**常规操作**，
下游已连续两版手工做：12 个版本目录 `git mv` + 15 个文件/目录 basename 改名 + **1710 处**
文本替换 + 代码内 8 个 pom（含二级模块）/ package.json / Dockerfile 对齐，每次约 10 分钟。
漏一处就是隐性残留，且**没有任何机器门会拦**——版本号散落在几百个文件里，人肉 grep 必漏。

## 三条容易踩的坑（本脚本内置处理）

1. **不能无脑全库替换**：`.aidp/skills/` 与 `.aidp/scripts/tests/` 里的版本号是**范式示例
   与测试夹具**（如 SKILL 文档里的 `docs/design/detail/V0.1.0/` 例子、单测里造的假版本目录），
   改了会破坏脚手架一致性和测试。这两处默认整棵排除。
2. **pom 要扫全部层级**：多模块工程的 `<version>` 分散在父 pom 与各级子模块，
   只扫一级会漏掉二级模块。
3. **空目录 `git mv` 会失败**：版本目录常有只含 `.gitkeep` 或干脆全空的（如尚未产出的
   `docs/bugfix/{V}/`），`git mv` 对未跟踪内容报错，需回退普通 `mv`。

## 用法

    python3 .aidp/scripts/rename_version.py V0.12.2 V0.13.0            # 计划（默认，只读）
    python3 .aidp/scripts/rename_version.py V0.12.2 V0.13.0 --apply    # 执行

收尾恒打印**剩余命中清单 + 逐条豁免理由**，让人一眼确认零残留（而不是"脚本说完成了"）。
**有未在豁免清单内的残留时退出码为 1**——零残留才 0，不给"跑完了但没改干净"留出口。

⚠️ 语义前提：改名 = **这个版本本来就该叫新号**（开发期临时编号 → 发布时按 SemVer 正名），
所以 changelog / 更新日志里属于本版的条目会**一并改**。若旧号另有其人（已发布的历史版本），
它会出现在剩余清单里等人工确认——机器分不出这两种情况，也不该替人猜。

代码内自报版本（pom 各级子模块 / package.json / Dockerfile）**不在本脚本职责内**：
它们的格式是裸版本号（`0.13.0` 而非 `V0.13.0`），由 `check_version_identifier.py` 对齐并校验，
本脚本收尾会提示去跑它。
"""
import argparse
import json
import os
import re
import subprocess
import sys

VERSION_RE = re.compile(r"^V\d+\.\d+(\.\d+)?$")
# 默认排除：范式示例 / 测试夹具 / 依赖与产物 / 版本控制目录
EXCLUDE_DIR_PARTS = {".git", "node_modules", "dist", "build", "target", "vendor",
                     "__pycache__", ".idea", ".vscode", "coverage", "out"}
EXCLUDE_PREFIXES = (".aidp/skills/", ".aidp/scripts/tests/")
TEXT_SUFFIXES = {".md", ".py", ".sh", ".yml", ".yaml", ".json", ".xml", ".txt",
                 ".java", ".ts", ".js", ".vue", ".sql", ".properties", ".conf",
                 ".tpl", ".gradle", ".kts", ".toml", ".env", ".cfg", ".ini", ""}


def _git(root, *args):
    try:
        cp = subprocess.run(["git", "-C", root, "-c", "core.quotepath=false", *args],
                            capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError):
        return None
    return cp.stdout if cp.returncode == 0 else None


def _excluded(rel):
    rel = rel.replace("\\", "/")
    if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
        return True
    return any(part in EXCLUDE_DIR_PARTS for part in rel.split("/"))


def _walk(root):
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_PARTS]
        rel_cur = os.path.relpath(cur, root).replace("\\", "/")
        if rel_cur == ".":
            rel_cur = ""
        if rel_cur and _excluded(rel_cur):
            dirs[:] = []
            continue
        yield cur, rel_cur, dirs, files


def plan(root, old, new):
    """产出改名计划：目录 / 文件名 / 正文命中。"""
    root = os.path.abspath(root)
    dirs, files, texts = [], [], []
    for cur, rel_cur, subdirs, names in _walk(root):
        for d in subdirs:
            if old in d:
                rel = f"{rel_cur}/{d}" if rel_cur else d
                if not _excluded(rel):
                    dirs.append({"from": rel, "to": rel.replace(old, new)})
        for n in names:
            rel = f"{rel_cur}/{n}" if rel_cur else n
            if _excluded(rel):
                continue
            if old in n:
                files.append({"from": rel, "to": rel.replace(old, new)})
            ext = os.path.splitext(n)[1].lower()
            if ext not in TEXT_SUFFIXES:
                continue
            path = os.path.join(cur, n)
            try:
                with open(path, encoding="utf-8", errors="strict") as f:
                    body = f.read()
            except (OSError, UnicodeDecodeError):
                continue                      # 二进制/异常编码：不碰
            hits = body.count(old)
            if hits:
                texts.append({"path": rel, "hits": hits})
    # 目录深的先改，避免父目录先改掉导致子路径失效
    dirs.sort(key=lambda x: x["from"].count("/"), reverse=True)
    return {"old": old, "new": new, "dirs": dirs, "files": files,
            "texts": sorted(texts, key=lambda x: -x["hits"]),
            "text_hit_total": sum(t["hits"] for t in texts)}


def _move(root, src_rel, dst_rel):
    src, dst = os.path.join(root, src_rel), os.path.join(root, dst_rel)
    if not os.path.exists(src) or os.path.exists(dst):
        return "skipped"
    os.makedirs(os.path.dirname(dst) or root, exist_ok=True)
    if _git(root, "mv", src_rel, dst_rel) is not None:
        return "git-mv"
    try:                                       # 空目录 / 未跟踪内容：git mv 会失败，回退普通 mv
        os.rename(src, dst)
        return "mv"
    except OSError:
        return "failed"


def apply(root, p):
    root = os.path.abspath(root)
    old, new = p["old"], p["new"]
    acts = {"dirs": [], "files": [], "texts": 0}
    for d in p["dirs"]:
        acts["dirs"].append({**d, "how": _move(root, d["from"], d["to"])})
    for f in p["files"]:                       # 目录改名后路径可能已变，重算一次
        src = f["from"]
        if not os.path.exists(os.path.join(root, src)):
            src = src.replace(old, new)
            if not os.path.exists(os.path.join(root, src)):
                acts["files"].append({**f, "how": "skipped"}); continue
            dst = src
            if os.path.basename(dst) == os.path.basename(f["to"]):
                acts["files"].append({**f, "how": "already"}); continue
        acts["files"].append({**f, "how": _move(root, src, src.replace(old, new))})
    for cur, rel_cur, _sub, names in _walk(root):
        for n in names:
            rel = f"{rel_cur}/{n}" if rel_cur else n
            if _excluded(rel) or os.path.splitext(n)[1].lower() not in TEXT_SUFFIXES:
                continue
            path = os.path.join(cur, n)
            try:
                with open(path, encoding="utf-8", errors="strict") as f:
                    body = f.read()
            except (OSError, UnicodeDecodeError):
                continue
            if old not in body:
                continue
            with open(path, "w", encoding="utf-8") as f:
                f.write(body.replace(old, new))
            acts["texts"] += 1
    return acts


def residue(root, old):
    """剩余命中 + 逐条豁免理由——收尾必打印，让人确认零残留而不是信脚本一句'完成'。"""
    root = os.path.abspath(root)
    out = []
    for cur, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_PARTS]
        rel_cur = os.path.relpath(cur, root).replace("\\", "/")
        rel_cur = "" if rel_cur == "." else rel_cur
        for n in names:
            rel = f"{rel_cur}/{n}" if rel_cur else n
            if os.path.splitext(n)[1].lower() not in TEXT_SUFFIXES:
                continue
            try:
                with open(os.path.join(cur, n), encoding="utf-8", errors="strict") as f:
                    hits = f.read().count(old)
            except (OSError, UnicodeDecodeError):
                continue
            if not hits:
                continue
            if rel.startswith(".aidp/skills/"):
                why = "范式示例（SKILL 文档内的版本号样例）——刻意不改，改了会与上游 SKILL 漂移"
            elif rel.startswith(".aidp/scripts/tests/"):
                why = "测试夹具（单测自造的版本目录）——刻意不改，改了测试即失效"
            elif "版本变更历史" in rel or "版本更新日志" in rel or "changelog" in rel.lower():
                # ⚠️ 不预设对错：改名的语义是"这个版本本来就该叫新号"（发布时正名），
                #    故 changelog 里属于**本版**的条目应一并改；但若该号是**已发布的历史版本**
                #    另有其人，就必须保留。两者机器分不出来，交人判。
                why = "变更历史/更新日志——若此处是本版条目应已随之改名；仍残留说明它属于另一个已发布版本，请人工确认"
            else:
                why = "⚠️ 未在豁免清单内，请人工确认是否漏改"
            out.append({"path": rel, "hits": hits, "reason": why})
    return sorted(out, key=lambda x: (not x["reason"].startswith("⚠️"), -x["hits"]))


def main():
    ap = argparse.ArgumentParser(description="版本号全仓改名（目录/文件名/正文/代码内自报版本）")
    ap.add_argument("old"); ap.add_argument("new")
    ap.add_argument("--root", default=".")
    ap.add_argument("--apply", action="store_true", help="真正执行（默认只出计划）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not VERSION_RE.match(a.old) or not VERSION_RE.match(a.new):
        sys.stderr.write("❌ 版本号须形如 V0.13.0\n"); return 2
    if a.old == a.new:
        sys.stderr.write("❌ 新旧版本号相同\n"); return 2

    p = plan(a.root, a.old, a.new)
    result = {"plan": p}
    if a.apply:
        result["applied"] = apply(a.root, p)
        result["residue"] = residue(a.root, a.old)

    if a.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"📋 {a.old} → {a.new}：目录 {len(p['dirs'])} 个 / 文件名 {len(p['files'])} 个 / "
          f"正文 {len(p['texts'])} 份共 {p['text_hit_total']} 处")
    if not a.apply:
        for d in p["dirs"][:20]:
            print(f"   dir   {d['from']}  →  {d['to']}")
        for f in p["files"][:20]:
            print(f"   file  {f['from']}  →  {f['to']}")
        print("   （以上为计划，加 --apply 执行；正文替换逐文件进行，不在此逐条列出）")
        print("⚠️ 代码内自报版本（pom/package.json/Dockerfile）请在 --apply 后跑 "
              "`python3 .aidp/scripts/check_version_identifier.py` 对齐并复验")
        return 0

    ap_ = result["applied"]
    print(f"✅ 已执行：目录 {len(ap_['dirs'])} / 文件名 {len(ap_['files'])} / 正文 {ap_['texts']} 份")
    print("\n📌 剩余命中清单（逐条豁免理由）：")
    unresolved = 0
    for r in result["residue"]:
        print(f"   {r['hits']:>4} 处  {r['path']}\n           {r['reason']}")
        if r["reason"].startswith("⚠️"):
            unresolved += 1
    if not result["residue"]:
        print("   （无剩余命中）")
    print("\n⚠️ 下一步：跑 `python3 .aidp/scripts/check_version_identifier.py` 对齐代码内自报版本"
          "（pom 含各级子模块 / package.json / Dockerfile），再跑 verify.py 复验")
    return 1 if unresolved else 0


if __name__ == "__main__":
    sys.exit(main())
