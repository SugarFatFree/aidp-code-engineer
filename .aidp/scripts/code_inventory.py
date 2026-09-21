#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""code_inventory.py — 代码现状清单的**跨版本增量缓存**（sprint-design Step 0.6.4.7 的确定性内核）。

## 为什么需要

Step 0.6.4.7「扫描代码现状清单」原文写死「扫描深度：**全扫**（不增量）」，产物又落在
`docs/design/detail/{version}/*事实清单.md` —— **每个版本都从零重扫一遍整个 `code/`，
上一版扫出来的结论下一版一点都不复用**。项目版本越多、代码越多，这一步就越慢：
它是整条 `/version` 链路里**唯一真正随累积增长**的环节（其余跨版本读取都已收敛到
`{prev_version}` 或走"变更专题重算 + 其余前滚"）。

本脚本把这份清单提到**项目级**并按内容哈希增量维护：
  - 首跑全扫，落 `memory/_facts/code-inventory.json`；
  - 之后只**重新解析内容变了的文件**（sha256 比对），未变文件直接复用上次的抽取结果；
  - 输出 `changed/added/removed` 三个 Δ 清单，供上层只对"动过的部分"做语义判断。

**为什么按 sha 而不是 `git diff <last_commit>..HEAD`**：git diff 漏掉未提交改动、
对浅克隆/变基/换分支不稳（旧 commit 可能已不可达），一旦取不到差异就得静默退回全扫、
而调用方看不出来。sha 比对是 IO-bound 的纯本地操作，**任何来源的改动都不会漏**，
代价只有读文件；真正省下来的是"解析 + 让 AI 读全量结果"这两段。
`last_scan_commit` 仍会记录，但只作溯源信息、不参与判定。

## 抽取的 5 个维度（与 Step 0.6.4.7 表格一一对应，未命中的维度不强求）

  api    后端 API 端点   Spring @*Mapping / Express-Koa router.* / FastAPI @app|@router.*
  table  数据库表        docs/deployment/**/sql/**.sql 的 CREATE TABLE（权威）+ ORM Entity 辅助
  route  前端路由        Vue Router path+name / React <Route path=> / Next.js 目录约定
  page   前端页面        views|pages 下的 .vue/.tsx/.jsx + 页面标题
  config 配置文件        application*.yml / bootstrap* / .env* / *.conf / docker-compose*（只列文件）

⛔ 边界：本脚本**只抽取事实、不做判断**。四象限对比（代码已实现 × PRD 要求）、
"该复用还是该新建"等语义结论仍归 `/sprint-design` 与 `dev-logic-architect`（约定 21）。

用法：
    python3 AIDP_HOME/scripts/code_inventory.py update            # 增量刷新缓存并打印摘要
    python3 AIDP_HOME/scripts/code_inventory.py update --json     # 结构化输出（含 delta）
    python3 AIDP_HOME/scripts/code_inventory.py update --full     # 忽略缓存全量重扫
    python3 AIDP_HOME/scripts/code_inventory.py show --json       # 只读当前缓存，不扫盘
    python3 AIDP_HOME/scripts/code_inventory.py render            # 渲染成事实清单「代码现状清单」段 Markdown
    python3 AIDP_HOME/scripts/code_inventory.py delta --since V0.1.0   # 相对某次快照的 Δ（见 snapshot）
    python3 AIDP_HOME/scripts/code_inventory.py snapshot --version V0.2.0  # 给本版打快照，供下版算 Δ

退出码：0 正常；1 缓存缺失且 show/render/delta 无从进行；2 用法错。
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

SCHEMA = 1
STATE_REL = os.path.join("memory", "_facts", "code-inventory.json")

# ── 扫描范围 ────────────────────────────────────────────────────────────────
CODE_DIRS = ("code",)
SQL_GLOB_DIRS = (os.path.join("docs", "deployment"),)
SKIP_DIR_NAMES = {
    ".git", "node_modules", "dist", "build", "target", "out", "__pycache__",
    ".idea", ".vscode", "coverage", ".next", ".nuxt", "vendor", "venv", ".venv",
}
CODE_EXT = {".java", ".kt", ".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx", ".vue", ".py", ".go"}
CONFIG_NAMES = re.compile(
    r"^(application[-\w]*\.(ya?ml|properties)|bootstrap[-\w]*\.ya?ml|\.env[\w.]*|"
    r"[\w.-]+\.conf|docker-compose[-\w]*\.ya?ml)$")

# ── 抽取规则 ────────────────────────────────────────────────────────────────
RE_SPRING = re.compile(
    r"@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']")
RE_SPRING_BARE = re.compile(r"@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*\)")
RE_CLASS_MAPPING = re.compile(r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?[\"']([^\"']*)[\"']")
RE_EXPRESS = re.compile(r"\brouter\s*\.\s*(get|post|put|patch|delete)\s*\(\s*[\"'`]([^\"'`]*)")
RE_FASTAPI = re.compile(r"@(?:app|router)\s*\.\s*(get|post|put|patch|delete)\s*\(\s*[\"']([^\"']*)")
RE_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`\"\[]?([\w.]+)[`\"\]]?", re.I)
RE_ENTITY = re.compile(r"@(?:Entity|Table)\s*\(?\s*(?:name\s*=\s*)?[\"']?([\w.]+)?")
RE_VUE_ROUTE = re.compile(r"path\s*:\s*[\"'`]([^\"'`]*)[\"'`][\s\S]{0,200}?name\s*:\s*[\"'`]([^\"'`]*)")
RE_REACT_ROUTE = re.compile(r"<Route\b[^>]*\bpath\s*=\s*[\"'{]([^\"'}]*)")
RE_H1 = re.compile(r"<h1[^>]*>\s*([^<{]{1,60}?)\s*<")
RE_VUE_COMMENT = re.compile(r"<!--\s*(.{1,60}?)\s*-->")
# pages/ 下这些目录属"就近放置的非页面单元"，不算页面、也不派生路由
NON_PAGE_SEG = re.compile(r"/(components?|composables|hooks|utils|constants|types|"
                          r"__tests__|__mocks__|api|stores?)/")


def _now():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _sha(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()[:16]


def _git_head(root):
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=15)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def enumerate_files(root):
    """列出所有需要参与抽取的文件（相对路径）。只做目录裁剪，不读内容。"""
    out = []
    for base in CODE_DIRS + SQL_GLOB_DIRS:
        top = os.path.join(root, base)
        if not os.path.isdir(top):
            continue
        for dirpath, dirnames, filenames in os.walk(top):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for fn in filenames:
                ext = os.path.splitext(fn)[1].lower()
                rel = os.path.relpath(os.path.join(dirpath, fn), root)
                if base.startswith("docs"):
                    if ext == ".sql":            # 部署目录只取 SQL（表清单的权威来源）
                        out.append(rel)
                    continue
                if ext in CODE_EXT or ext == ".sql" or CONFIG_NAMES.match(fn):
                    out.append(rel)
    return sorted(out)


def extract(root, rel):
    """从单个文件抽取实体清单。返回 [{kind, ...}]；解析失败返回 []（不阻断整体）。"""
    path = os.path.join(root, rel)
    fn = os.path.basename(rel)
    ext = os.path.splitext(fn)[1].lower()
    ents = []

    if CONFIG_NAMES.match(fn) and ext != ".sql":
        side = ("后端" if "/backend/" in "/" + rel else
                "前端" if "/frontend/" in "/" + rel else
                "部署" if rel.startswith("docs/deployment") else "其它")
        return [{"kind": "config", "purpose": side}]

    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return []
    lines = text.splitlines()

    if ext == ".sql":
        for i, ln in enumerate(lines, 1):
            for m in RE_CREATE_TABLE.finditer(ln):
                ents.append({"kind": "table", "name": m.group(1), "line": i, "src": "ddl"})
        return ents

    if ext in (".java", ".kt"):
        # 类级 @RequestMapping 作为前缀（只取文件里第一个出现在 class 之前的）
        prefix = ""
        for i, ln in enumerate(lines[:80], 1):
            m = RE_CLASS_MAPPING.search(ln)
            if m and "class " not in ln:
                prefix = m.group(1)
                break
        for i, ln in enumerate(lines, 1):
            for m in RE_SPRING.finditer(ln):
                p = m.group(2)
                full = (prefix.rstrip("/") + "/" + p.lstrip("/")) if p else prefix
                ents.append({"kind": "api", "method": m.group(1).upper(),
                             "path": full or "/", "line": i})
            if RE_SPRING_BARE.search(ln):
                ents.append({"kind": "api", "method": "REQUEST", "path": prefix or "/", "line": i})
            m = RE_ENTITY.search(ln)
            if m and m.group(1):
                ents.append({"kind": "table", "name": m.group(1), "line": i, "src": "orm"})
        return ents

    if ext == ".py":
        for i, ln in enumerate(lines, 1):
            for m in RE_FASTAPI.finditer(ln):
                ents.append({"kind": "api", "method": m.group(1).upper(),
                             "path": m.group(2), "line": i})
        return ents

    if ext in (".js", ".ts", ".mjs", ".cjs", ".jsx", ".tsx", ".vue"):
        for i, ln in enumerate(lines, 1):
            for m in RE_EXPRESS.finditer(ln):
                ents.append({"kind": "api", "method": m.group(1).upper(),
                             "path": m.group(2), "line": i})
        if "/router/" in "/" + rel or rel.endswith(("routes.ts", "routes.js", "router.ts", "router.js")):
            for m in RE_VUE_ROUTE.finditer(text):
                ents.append({"kind": "route", "path": m.group(1), "name": m.group(2)})
        for m in RE_REACT_ROUTE.finditer(text):
            ents.append({"kind": "route", "path": m.group(1), "name": ""})
        # 页面：views/ 或 pages/ 下的组件文件
        # ⛔ 排除就近放置（colocation）的非页面目录：pages/x/components/Foo.vue 是被页面引用的
        #    子组件，既不是页面也不是路由。不排会让页面数虚高、并造出一堆假路由
        #    （实际项目实测 57 个"页面"里大半是 components/ 下的子组件）。
        if (re.search(r"/(views|pages)/", "/" + rel) and ext in (".vue", ".tsx", ".jsx")
                and not NON_PAGE_SEG.search("/" + rel)):
            title = ""
            m = RE_H1.search(text) or RE_VUE_COMMENT.search(text)
            if m:
                title = m.group(1).strip()
            ents.append({"kind": "page", "title": title or os.path.splitext(fn)[0]})
            # ★ 文件式路由（unplugin-vue-router / Next.js / Nuxt）：路由不写在 router.ts 里、
            #   而由 pages/ 目录结构派生。不补这一条，这类项目的「前端路由」维度会恒为 0 ——
            #   看着像"扫过了没有路由"，实为漏抽（实际项目实测踩中）。
            r = _file_route(rel)
            if r is not None:
                ents.append({"kind": "route", "path": r, "name": "", "src": "file-based"})
    return ents


def _file_route(rel):
    """pages/ 下的文件路径 → 路由 path；非 pages/ 约定返回 None。

    index → 父路径；[id]/[[id]] → :id；[...x] → 通配；分组目录 (group) 跳过。
    """
    m = re.search(r"/pages/(.+)$", "/" + rel)
    if not m:
        return None
    seg_path = os.path.splitext(m.group(1))[0]
    parts = []
    for seg in seg_path.split("/"):
        if not seg or (seg.startswith("(") and seg.endswith(")")):
            continue                                   # 分组目录不进路径
        if seg == "index":
            continue
        mm = re.fullmatch(r"\[\[?\.{0,3}([\w-]+)\]?\]", seg)
        if mm:
            parts.append(("*" if "..." in seg else ":" + mm.group(1)))
        else:
            parts.append(seg)
    return "/" + "/".join(parts)


def load_state(root):
    p = os.path.join(root, STATE_REL)
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return d if d.get("schema") == SCHEMA else {}
    except (OSError, ValueError):
        return {}


def save_state(root, state):
    p = os.path.join(root, STATE_REL)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, p)


def do_update(root, full=False):
    old = {} if full else load_state(root)
    old_files = old.get("files") or {}
    files = enumerate_files(root)
    new_files, added, changed = {}, [], []
    reused = 0
    for rel in files:
        sha = _sha(rel if os.path.isabs(rel) else os.path.join(root, rel))
        prev = old_files.get(rel)
        if prev and prev.get("sha") == sha:
            new_files[rel] = prev            # ★ 内容没变 → 直接复用上次抽取结果，不再解析
            reused += 1
            continue
        new_files[rel] = {"sha": sha, "entities": extract(root, rel)}
        (changed if prev else added).append(rel)
    removed = sorted(set(old_files) - set(new_files))

    counts = {}
    for meta in new_files.values():
        for e in meta["entities"]:
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    state = {
        "schema": SCHEMA,
        "generated_at": _now(),
        "last_scan_commit": _git_head(root),
        "files": new_files,
        "counts": counts,
        "snapshots": old.get("snapshots") or {},
    }
    save_state(root, state)
    return state, {"added": added, "changed": changed, "removed": removed,
                   "reused": reused, "scanned": len(added) + len(changed),
                   "total_files": len(new_files), "full": bool(full) or not old_files}


def flatten(state):
    """把 files→entities 摊平成按 kind 分组的实体清单（供 render / delta 用）。"""
    by_kind = {}
    for rel, meta in sorted((state.get("files") or {}).items()):
        for e in meta.get("entities") or []:
            by_kind.setdefault(e["kind"], []).append(dict(e, file=rel))
    return by_kind


def _key(e):
    k = e["kind"]
    if k == "api":
        return f"api {e.get('method')} {e.get('path')}"
    if k == "table":
        return f"table {e.get('name')}"
    if k == "route":
        return f"route {e.get('path')}"
    if k == "page":
        return f"page {e.get('file')}"
    return f"config {e.get('file')}"


def do_snapshot(root, version):
    """给当前实体集合打快照，供下一个版本算「本版新增了哪些代码事实」。"""
    state = load_state(root)
    if not state:
        return None
    keys = sorted({_key(e) for lst in flatten(state).values() for e in lst})
    state.setdefault("snapshots", {})[version] = {"at": _now(), "keys": keys}
    save_state(root, state)
    return len(keys)


def do_delta(root, since):
    state = load_state(root)
    if not state:
        return None
    snap = (state.get("snapshots") or {}).get(since)
    if snap is None:
        return {"error": f"无版本 {since} 的快照（可用：{sorted((state.get('snapshots') or {}))}）"}
    cur = {_key(e) for lst in flatten(state).values() for e in lst}
    base = set(snap["keys"])
    return {"since": since, "added": sorted(cur - base), "removed": sorted(base - cur),
            "unchanged": len(cur & base)}


def do_render(state):
    """渲染事实清单「代码现状清单」段（格式对齐 step-0.6-事实采集-3.md 模板）。"""
    bk = flatten(state)
    out = ["## 代码现状清单（由 `code_inventory.py` 增量维护，勿手改）", "",
           f"> 生成时间：{state.get('generated_at')}　|　"
           f"扫描提交：`{(state.get('last_scan_commit') or '-')[:12]}`　|　"
           f"文件 {len(state.get('files') or {})}　|　"
           + "　".join(f"{k} {v}" for k, v in sorted((state.get('counts') or {}).items())), ""]
    if bk.get("api"):
        out += ["### 后端 API 端点", "", "| method | path | 文件:行 |", "|---|---|---|"]
        for e in sorted(bk["api"], key=lambda x: (x.get("path") or "", x.get("method") or "")):
            out.append(f"| {e.get('method')} | `{e.get('path')}` | `{e['file']}:{e.get('line','')}` |")
        out.append("")
    if bk.get("table"):
        out += ["### 数据库表", "", "| 表名 | 来源 | 文件:行 |", "|---|---|---|"]
        seen = set()
        for e in sorted(bk["table"], key=lambda x: x.get("name") or ""):
            if e.get("name") in seen:
                continue
            seen.add(e.get("name"))
            out.append(f"| `{e.get('name')}` | {e.get('src')} | `{e['file']}:{e.get('line','')}` |")
        out.append("")
    if bk.get("route"):
        out += ["### 前端路由", "", "| path | name | 文件 |", "|---|---|---|"]
        for e in sorted(bk["route"], key=lambda x: x.get("path") or ""):
            out.append(f"| `{e.get('path')}` | {e.get('name') or '-'} | `{e['file']}` |")
        out.append("")
    if bk.get("page"):
        out += ["### 前端页面", "", "| 页面标题 | 文件 |", "|---|---|"]
        for e in sorted(bk["page"], key=lambda x: x["file"]):
            out.append(f"| {e.get('title')} | `{e['file']}` |")
        out.append("")
    if bk.get("config"):
        out += ["### 配置文件（仅线索，不展开配置项 —— 约定 25）", "", "| 文件 | 归属 |", "|---|---|"]
        for e in sorted(bk["config"], key=lambda x: x["file"]):
            out.append(f"| `{e['file']}` | {e.get('purpose')} |")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="code_inventory",
                                 description="代码现状清单的跨版本增量缓存（Step 0.6.4.7 内核）")
    ap.add_argument("cmd", choices=["update", "show", "render", "snapshot", "delta"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--full", action="store_true", help="update：忽略缓存全量重扫")
    ap.add_argument("--version", default="", help="snapshot：快照归属的版本号")
    ap.add_argument("--since", default="", help="delta：与哪个版本的快照比")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)

    if a.cmd == "update":
        state, d = do_update(root, a.full)
        if a.json:
            print(json.dumps({"delta": d, "counts": state["counts"],
                              "generated_at": state["generated_at"],
                              "last_scan_commit": state["last_scan_commit"]}, ensure_ascii=False))
        else:
            mode = "全量重扫" if d["full"] else "增量刷新"
            print(f"✅ 代码现状清单已{mode}：文件 {d['total_files']}（解析 {d['scanned']}、"
                  f"复用 {d['reused']}）　实体 "
                  + "　".join(f"{k}={v}" for k, v in sorted(state["counts"].items())))
            for lab, key in (("新增文件", "added"), ("变更文件", "changed"), ("删除文件", "removed")):
                if d[key]:
                    print(f"  {lab} {len(d[key])}：" + "、".join(d[key][:6])
                          + ("…" if len(d[key]) > 6 else ""))
            if not d["full"] and d["scanned"] == 0:
                print("  （代码无变化 —— 本次零解析，直接复用缓存）")
        return 0

    state = load_state(root)
    if not state:
        print("⛔ 尚无缓存，请先跑 `code_inventory.py update`", file=sys.stderr)
        return 1

    if a.cmd == "show":
        print(json.dumps(state if a.json else state.get("counts"), ensure_ascii=False,
                         indent=2))
        return 0
    if a.cmd == "render":
        print(do_render(state))
        return 0
    if a.cmd == "snapshot":
        if not a.version:
            print("⛔ snapshot 需要 --version", file=sys.stderr)
            return 2
        n = do_snapshot(root, a.version)
        print(json.dumps({"version": a.version, "keys": n}, ensure_ascii=False) if a.json
              else f"✅ 已为 {a.version} 打代码事实快照（{n} 个实体）")
        return 0
    if a.cmd == "delta":
        if not a.since:
            print("⛔ delta 需要 --since <版本号>", file=sys.stderr)
            return 2
        d = do_delta(root, a.since)
        if d.get("error"):
            print("⛔ " + d["error"], file=sys.stderr)
            return 1
        if a.json:
            print(json.dumps(d, ensure_ascii=False))
        else:
            print(f"相对 {a.since}：新增 {len(d['added'])}　删除 {len(d['removed'])}　"
                  f"不变 {d['unchanged']}")
            for x in d["added"][:20]:
                print("  + " + x)
            for x in d["removed"][:20]:
                print("  - " + x)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
