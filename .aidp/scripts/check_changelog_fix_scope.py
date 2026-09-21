#!/usr/bin/env python3
"""check_changelog_fix_scope.py — 版本更新日志「🐛 修复」段是否混进了本版自产自消的缺陷。

## 这道门堵的是什么

`版本更新日志.md` 是**给使用者读的**。列一条「修复了 X」等于告诉他「你之前遇到的 X 现在好了」。
但 `/version` 取修复项的两个来源——`docs/bugfix/{version}/` 与 `git log | grep '^fix('`——
**都会把「本版新功能自己引入、又在本版修掉」的缺陷收进来**：那些带 bug 的版本根本没发出去，
使用者从来没遇到过 X。

下游实证：某版从 28 条 `fix(` 里挑 10 条写进日志，其中 7 条依附于本版才新增的功能，
由产品评审时当场指出。剔除后只剩 3 条，其中 1 条自五个版本前就存在——**那条才是真正
值得写的，此前被 9 条自产缺陷淹没**。

## 判据

准入判据（唯一）：**该问题在上一个已发布版本中真实存在，且使用者可触达。**

本脚本按提交粒度做**可判定的近似**：一条 `fix(` 提交若其改动的正式代码文件**全部**引入于
上一个已发布 tag 之后 → 判「疑似自产自消」。于是：

- **F1（Important）**：日志修复段条数 K > 「非自产自消的 fix 提交数」(N−M)
  → 至少 K−(N−M) 条自产的被写进了日志。列出疑似自产的提交供逐条复核。

⛔ **本脚本不做「日志条目 ↔ 提交」的逐条映射**：日志条目是中文一句话、与提交无链接，
靠关键词猜匹配只会制造比它能发现的更多的误判。计数不等式是**能确定性成立**的那部分，
剩下的判断交给人——这比一个看起来更精确、实则在猜的结果诚实。

同理，判据本身不可能 100% 准（一条修复可能同时改新旧文件），故：
**Important 级、退出码 3、⛔ 不阻断发布**，可用 `<!-- changelog-scope-ignore: 理由 -->` 显式豁免。

退出码：0 = 通过 / 不适用；3 = 有 Important（不阻断）；2 = 入参错。
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

CHANGELOG = "版本更新日志.md"
IGNORE_RE = re.compile(r"<!--\s*changelog-scope-ignore:\s*(?P<why>[^>]*?)-->")
VER_BLOCK_RE = re.compile(r"^##\s*\[(?P<v>[^\]]+)\]\s*$", re.M)
FIX_HEAD_RE = re.compile(r"^###\s*.*修复\s*$", re.M)
H3_RE = re.compile(r"^###\s", re.M)
ITEM_RE = re.compile(r"^\s*[-*]\s+(?P<t>.+?)\s*$", re.M)
EMPTY_DECL = "本版无面向已发布版本的缺陷修复"
# 非正式代码：这些路径下的改动不代表使用者可触达的行为
_LEGACY_AIDP_PREFIX = re.escape(".aidp") + "/"
NON_CODE_RE = re.compile(
    r"^(docs/|memory/|" + _LEGACY_AIDP_PREFIX
    + r"|\.claude/|\.agents/|\.codex/|\.dsh/|tests/|[^/]*\.md$|README)"
)


def _git(root, *args):
    try:
        cp = subprocess.run(["git", "-C", root, *args],
                            capture_output=True, text=True, timeout=60)
    except Exception:
        return None
    return cp.stdout if cp.returncode == 0 else None


def prev_tag(root, explicit=""):
    if explicit:
        return explicit
    out = _git(root, "describe", "--tags", "--abbrev=0")
    return (out or "").strip() or ""


def _fix_commits(root, since):
    """→ [(sha, subject)]，since..HEAD 里 subject 以 `fix(` 开头的提交。"""
    rng = f"{since}..HEAD" if since else "HEAD"
    out = _git(root, "log", rng, "--no-merges", "--pretty=%H%x00%s")
    if out is None:
        return None
    res = []
    for ln in out.splitlines():
        if "\0" not in ln:
            continue
        sha, subj = ln.split("\0", 1)
        if subj.strip().startswith("fix("):
            res.append((sha, subj.strip()))
    return res


def _changed_code_files(root, sha):
    out = _git(root, "show", "--pretty=", "--name-only", "--diff-filter=d", sha)
    if not out:
        return []
    return [f for f in (x.strip() for x in out.splitlines())
            if f and not NON_CODE_RE.match(f)]


def _introduced_after(root, path, since):
    """该文件的**首次新增**提交是否晚于 since。无法判定时返回 None（按"不确定"处理）。"""
    out = _git(root, "log", "--diff-filter=A", "--format=%H", "--follow", "--", path)
    if out is None:
        return None
    shas = [x.strip() for x in out.splitlines() if x.strip()]
    if not shas:
        return None
    first = shas[-1]                       # 最早那次新增
    if not since:
        return False                       # 无 tag = 首版，无"已发布版本"可言
    # first 是否在 since..HEAD 里 → 是则晚于 since
    out2 = _git(root, "merge-base", "--is-ancestor", first, since)
    # --is-ancestor 用退出码表达，_git 失败返回 None ⇒ 非祖先 ⇒ 引入点晚于 since
    return out2 is None


def classify_commit(root, sha, since):
    """→ (is_self_produced, files, undetermined)。全部正式代码文件都晚于 since 才判自产自消。"""
    files = _changed_code_files(root, sha)
    if not files:
        return None, files, False          # 没碰正式代码 → 不计入 N
    flags = [_introduced_after(root, f, since) for f in files]
    if any(f is None for f in flags):
        return False, files, True          # 有判不了的 → 保守判"非自产"，不误杀
    return all(flags), files, False


def _fix_section_items(text, version=""):
    """→ (items, version_used)。取指定版本块（缺省取最顶部那个）的「🐛 修复」列表项。"""
    blocks = [(m.group("v"), m.start()) for m in VER_BLOCK_RE.finditer(text)]
    if not blocks:
        return None, ""
    pick = None
    if version:
        for i, (v, st) in enumerate(blocks):
            if v.strip().lstrip("Vv") == version.strip().lstrip("Vv"):
                pick = i
                break
        if pick is None:
            return None, ""
    else:
        pick = 0
    _v, start = blocks[pick]
    end = blocks[pick + 1][1] if pick + 1 < len(blocks) else len(text)
    body = text[start:end]
    m = FIX_HEAD_RE.search(body)
    if not m:
        return [], blocks[pick][0]
    rest = body[m.end():]
    nxt = H3_RE.search(rest)
    seg = rest[:nxt.start()] if nxt else rest
    items = [x.group("t") for x in ITEM_RE.finditer(seg)]
    items = [t for t in items if EMPTY_DECL not in t and not t.startswith("...")]
    return items, blocks[pick][0]


def run(root, version="", since_tag=""):
    res = {"applicable": False, "reason": "", "version": version,
           "prev_tag": "", "fix_commits": 0, "self_produced": 0,
           "log_items": 0, "suspects": [], "importants": []}
    path = os.path.join(root, CHANGELOG)
    if not os.path.isfile(path):
        res["reason"] = "no-changelog"
        return res
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        res["reason"] = "unreadable"
        return res
    ig = IGNORE_RE.search(text)
    if ig:
        res["reason"] = "ignored: " + ig.group("why").strip()
        return res
    if _git(root, "rev-parse", "--git-dir") is None:
        res["reason"] = "not-a-git-repo"
        return res

    items, ver = _fix_section_items(text, version)
    if items is None:
        res["reason"] = "version-block-not-found"
        return res
    res["version"] = ver
    since = prev_tag(root, since_tag)
    res["prev_tag"] = since or "(首版，无已发布 tag)"
    commits = _fix_commits(root, since)
    if commits is None:
        res["reason"] = "git-log-failed"
        return res

    res["applicable"] = True
    res["log_items"] = len(items)
    n = m = 0
    for sha, subj in commits:
        self_made, files, undet = classify_commit(root, sha, since)
        if self_made is None:
            continue                        # 没碰正式代码
        n += 1
        if self_made:
            m += 1
            res["suspects"].append({"sha": sha[:9], "subject": subj,
                                    "files": files[:6]})
    res["fix_commits"] = n
    res["self_produced"] = m
    eligible = n - m
    if res["log_items"] > eligible:
        over = res["log_items"] - eligible
        res["importants"].append({
            "code": "F1", "over": over,
            "msg": (f"日志修复段列了 {res['log_items']} 条，但本版只有 {eligible} 条 fix 提交"
                    f"改到了 {res['prev_tag']} 之前就存在的代码"
                    f"（{n} 条 fix 提交中 {m} 条疑似本版自产自消）"
                    f" → 至少 {over} 条属「本版新功能自己引入、又自己修掉」，"
                    f"使用者从未遇到过，应从修复段剔除"),
            "fix": "逐条查被修文件/代码段的引入点：git log --diff-filter=A -- <文件>；"
                   "引入点晚于上一个已发布 tag 即剔除。剔除≠丢弃，缺陷仍在 docs/bugfix/ 与 git log 里。"
                   "全部剔完就写「" + EMPTY_DECL + "」，⛔ 不要为凑数填回去",
        })
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="版本更新日志「🐛 修复」段准入判据回检（Important 级、不阻断发布）")
    ap.add_argument("--root", "--repo-root", dest="root", default=".")
    ap.add_argument("--version", default="", help="要检查的版本块（默认取日志最顶部那个）")
    ap.add_argument("--since-tag", default="", help="上一个已发布 tag（默认 git describe 取）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true", help="阳性/阴性对照自检（约定 35）")
    a = ap.parse_args(argv)

    if a.self_check:
        sc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selfcheck.py")
        return subprocess.call([sys.executable, sc, "--only", os.path.basename(__file__)])

    res = run(a.root, a.version, a.since_tag)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["applicable"]:
        print(f"⏭️ 不适用（{res['reason']}）")
    else:
        print(f"版本 {res['version']} | 上一已发布 {res['prev_tag']} | "
              f"fix 提交 {res['fix_commits']} 条（疑似自产自消 {res['self_produced']}）| "
              f"日志修复段 {res['log_items']} 条")
        for it in res["importants"]:
            print(f"🟡 [{it['code']}] {it['msg']}")
            print(f"   → {it['fix']}")
        if res["suspects"]:
            print("   疑似自产自消的 fix 提交（供逐条复核）：")
            for s in res["suspects"][:12]:
                print(f"     · {s['sha']} {s['subject']}")
            if len(res["suspects"]) > 12:
                print(f"     …… 另 {len(res['suspects']) - 12} 条")
        if not res["importants"]:
            print("结论：✅ 无疑似自产自消项进入修复段")
    return 3 if res["importants"] else 0


if __name__ == "__main__":
    sys.exit(main())
