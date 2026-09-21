#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_line_refs.py — 跨文件引用里的硬编码行号（脚手架契约脚本，WARN 级）。

## 为什么需要本脚本

文档之间互相引用时写死行号 —— `06_版本与用户目录约定.md` §2.2 **行 49~52** —— 是一种
**必然失效**的引用：被引文件只要在前面插一段话，行号就整体位移，读者按行号翻过去看到的
是毫不相干的内容，却毫无察觉（真实回流：`docs/testing/V0.0.1/README.md` 引的行号已漂移
约 18 行，而两份文件本身都"没错"，任何断链/锚点检查都发现不了）。

行号是**最脆弱的引用坐标**：它不属于被引文档的语义，谁也不会为了保住别人的引用而不敢
在文件中间加行。正确做法是引**小节名 / 标题锚点**（`§2.2 版本目录约定`）——标题改名有
`check_md_anchors.py` 兜、内容位移则完全不影响。

## 判定口径

扫全仓 `.md`，匹配六种硬编码行号写法：

    行 12~34 / 行 12-34 / 行 12–34      （中文"行"前缀，含 `~`、`-`、en/em dash）
    第 12~34 行 / 第 12 行               （中文"第…行"）
    :L12-34 / :L12                       （GitHub 风格行锚）
    L12-L34                              （成对 L 锚）
    L113                                 （裸 L 锚，不带冒号也不成对）
    some-file.md:217                     （`文件:行号` 写法）

一律报 **WARN**：它不像死链那样"点了必错"，属于**必然腐烂但当下可能还准**的引用，
适合提示 + 人工换写法，不适合当场卡住流程。**退出码仍按全仓统一口径返回 1**（0=通过 /
1=检出 / 2=入参错），由调用方（`verify.py` / 命令端）决定映射成 WARN 还是 ERROR ——
同 `check_version_identifier.py` 的先例：退出码 1 ≠ 必须阻断。

**目标文件存在性分组**（提高清单可操作性）：从匹配点往前找最近提到的 `*.md` 文件名并
按引用者所在目录解析：

  · **目标存在** → 真会漂移、优先改成小节名引用；
  · **目标路径解析不到**（如文档拆分后留下的 `（原 phase-3.md 行 1–84）` 溯源注） → 行号连
    "曾经指向哪"都无从验证，属历史留痕，可低优先处理或加豁免标记。

## 豁免（显式标记）

    <!-- lineref-check: ignore -->             该行豁免
    <!-- lineref-check: ignore-file 理由 -->    整份文件豁免
    <!-- lineref-check: ignore-begin 理由 -->   区块开始
    ...
    <!-- lineref-check: ignore-end -->         区块结束

## 用法

    python3 AIDP_HOME/scripts/check_line_refs.py            # 人读报告
    python3 AIDP_HOME/scripts/check_line_refs.py --json     # 机读 JSON
    python3 AIDP_HOME/scripts/check_line_refs.py --root . --path docs

退出码：0 = 无硬编码行号；1 = 检出（WARN 级，调用方自行决定是否阻断）；2 = 用法/读取错误。
"""
import argparse
import json
import os
import re
import sys

EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv",
    "skills",  # `AIDP_HOME/skills/`：SKILL 本体 + 脚手架 bundle 镜像，由 mirror 脚本同步
}
# ★ 前缀式排除：`.aidp-backup-<时间戳>` 带时间戳，永远命中不了上面的精确名集合；
#   备份是冻结的历史副本，参与巡检只会在做过 upgrade 的下游制造恒红噪音（口径同 check_loop_examples.py）。
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)

DASH = r"[~\-–—〜]"
LINE_REF_PATTERNS = [
    # 行 49~52 / 行 49-52 / 行 49–52
    ("行 N~M", re.compile(r"行\s*\d+\s*" + DASH + r"\s*\d+")),
    # 第 49~52 行 / 第 49 行
    ("第 N~M 行", re.compile(r"第\s*\d+\s*(?:" + DASH + r"\s*\d+\s*)?行")),
    # :L12-34 / :L12（GitHub 行锚）
    (":LN-M", re.compile(r":L\d{2,}(?:" + DASH + r"\d+)?\b")),
    # L12-L34 —— ★ 只认两位以上：本范式用 `L1-L3` 表示"层级 1 到 3"（UI L1/L2 分级、
    #   上游溯源 L1-L3 等），一位数的 L 形态几乎全是层级而非行号，不设下限即恒误报。
    ("LN-LM", re.compile(r"\bL\d{2,}" + DASH + r"L\d+\b")),
    # ★ 两种此前漏掉的主流写法（各放过一处真死链）：
    #   · 裸 `L113`（不带冒号也不成对）—— 实测 `rationale.md` 里 `phase-3-3.md L113`
    #     指向一份只有 104 行的文件；
    #   · `file.md:217` —— 实测 `phase-2-1.md` 里 `sprint-batch.md:217` 指向的是
    #     一段与该处口径完全无关的正文（行号还在、内容早换了，比越界更难发现）。
    #   ⚠️ 前后都要排除成对形态：前面带连字符 = `L120-L180` 的尾巴（已由「LN-LM」计过一次），
    #   再匹配一次就是同一处引用被算两遍。
    ("裸 LN", re.compile(r"(?<![:\w])(?<!-)(?<!–)(?<!—)L\d{2,}\b(?!\s*" + DASH + r"\s*L?\d)")),
    ("file.md:N", re.compile(r"[\w一-鿿./\\-]+\.md:\d+\b")),
]
# 匹配点之前最近提到的 .md 文件名（用于判"被引文件还在不在"）
MD_NAME_RE = re.compile(r"([\w一-鿿./\\-]+\.md)")

IGNORE_LINE_RE = re.compile(r"<!--\s*lineref-check:\s*ignore\s*(?:-->|\s)")
IGNORE_FILE_RE = re.compile(r"<!--\s*lineref-check:\s*ignore-file")
IGNORE_BEGIN_RE = re.compile(r"<!--\s*lineref-check:\s*ignore-begin")
IGNORE_END_RE = re.compile(r"<!--\s*lineref-check:\s*ignore-end")


def iter_md(root, paths=None):
    if paths:
        for rel in paths:
            p = os.path.join(root, rel)
            if os.path.isfile(p) and p.endswith(".md"):
                yield p
            elif os.path.isdir(p):
                for x in _walk(p):
                    yield x
    else:
        for x in _walk(root):
            yield x


def _walk(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE_DIRS and not d.startswith(EXCLUDE_DIR_PREFIXES)]
        for fn in sorted(filenames):
            if fn.endswith(".md"):
                yield os.path.join(dirpath, fn)


def resolve_target(root, src_rel, line, upto):
    """找匹配点之前最近提到的 `.md`，返回 (目标名, 路径是否解析得到)；找不到文件名返回 (None, None)。

    **只做严格路径解析**（① 相对引用者所在目录 ② 相对仓库根），不按 basename 全仓找同名 ——
    全仓找会把 `原 phase-2.md 行 1–96`（该目录里早已拆没了）匹配到别的目录下同名的
    `phase-2.md`，报告就会写出"目标仍在"这种假结论。解析不到 = 无法核对，如实归入另一组。
    """
    names = MD_NAME_RE.findall(line[:upto])
    if not names:
        return None, None
    target = names[-1].replace("\\", "/")
    src_dir = os.path.dirname(os.path.join(root, src_rel))
    for cand in (os.path.join(src_dir, target), os.path.join(root, target)):
        if os.path.isfile(os.path.normpath(cand)):
            return target, True
    return target, False


def run(root, paths=None):
    findings, scanned = [], 0
    for path in sorted(set(iter_md(root, paths))):
        rel = os.path.relpath(path, root)
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        if IGNORE_FILE_RE.search(text):
            continue
        scanned += 1
        in_ignore = False
        for i, line in enumerate(text.split("\n"), 1):
            if IGNORE_BEGIN_RE.search(line):
                in_ignore = True
            elif IGNORE_END_RE.search(line):
                in_ignore = False
            if in_ignore or IGNORE_LINE_RE.search(line):
                continue
            for kind, pat in LINE_REF_PATTERNS:
                for m in pat.finditer(line):
                    target, exists = resolve_target(root, rel, line, m.start())
                    findings.append({
                        "file": rel,
                        "line": i,
                        "kind": kind,
                        "text": m.group(0),
                        "target": target,
                        "target_exists": exists,
                        "context": line.strip()[:100],
                    })
    live = [f for f in findings if f["target_exists"] is not False]
    stale = [f for f in findings if f["target_exists"] is False]
    return {"scanned": scanned, "findings": findings, "live": live, "stale": stale}


def main():
    ap = argparse.ArgumentParser(
        description="跨文件引用里的硬编码行号（行号必然漂移，应改引小节名）")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--path", action="append", default=None,
                    help="只扫指定相对路径（可重复）；缺省扫全仓 .md")
    ap.add_argument("--json", action="store_true", help="机读 JSON")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    try:
        res = run(args.root, args.path)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json
              else f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["findings"]:
        print(f"[OK] 无硬编码行号引用（巡检 {res['scanned']} 份 .md）")
    else:
        print(f"[WARN] 检出 {len(res['findings'])} 处硬编码行号引用"
              f"（巡检 {res['scanned']} 份 .md）——行号必然漂移，请改引小节名/标题锚点：")
        if res["live"]:
            print(f"  ▸ 被引文件仍在（{len(res['live'])} 处，优先改）：")
            for f in res["live"]:
                tgt = f"→ {f['target']}" if f["target"] else "（未识别目标文件）"
                print(f"      {f['file']}:{f['line']}  「{f['text']}」{tgt}")
        if res["stale"]:
            print(f"  ▸ 目标路径解析不到（{len(res['stale'])} 处，多为文档拆分后的溯源留痕，"
                  f"行号连「曾指向哪」都无从验证，可低优先）：")
            for f in res["stale"]:
                print(f"      {f['file']}:{f['line']}  「{f['text']}」→ {f['target']}（解析不到）")
        print("  修复：改成 `见 <文件>「<小节标题>」` 或锚点链接；"
              "确需保留（历史溯源注）→ 加 `<!-- lineref-check: ignore -->` 豁免。")
    return 1 if res["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
