#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_convention_dup.py — 核心约定「主行双写」确定性护栏（脚手架契约脚本）。

## 为什么需要本脚本

核心约定有两处落点，职责必须严格二分：

  · **主行文件**「核心约定」段 —— **决策要点主行**（常驻上下文、唯一权威）；
  · `AIDP_HOME/reference/约定细则-N.md`   —— 该条的**子项 / Why / 示例 / 实现子项**（按需 Read）。

★ **主行文件按形态探测，不写死**（两种形态都是合法下发结果）：

  · **形态 A `AGENTS.md`**（含 Codex / DeepSeek Harness，或模板项目自身）：`AGENTS.md` 承载正文，
    并存的 `CLAUDE.md` 只是薄壳 + `@AGENTS.md` 导入；
  · **形态 B `CLAUDE.md`**（仅 Claude Code）：**无 `AGENTS.md`**，正文就在 `CLAUDE.md` 单文件。

  写死 A 会让**所有形态 B 项目 100% 走 SKIP、exit 0** —— 那是**假通过**而非"不适用"，
  等于新铁律在下游零护栏（真实回流：某下游项目升级后该脚本永久空跑；
  此处不写具体版本号——事故是历史事实，写死版本号会随每次 bump 变成假话）。

一旦细则分片把主行原样复制一份，就形成**双写**：两处各自演进、悄悄漂移，
"见约定 N"到底以哪份为准全靠猜（真实事故：约定 35 两处文本已不同，一处 704 字符、
公共前缀只到 514 字符）。本脚本把「细则分片不得复制主行」固化成有退出码的硬门。

## 判定口径

1. 从项目记忆文件（`AGENTS.md` / `CLAUDE.md`）的「## 核心约定」段提取每条主行：形如 `N. **标题**：正文…`；
2. 取该主行的 **首句探针**——正文去掉 `N. ` 序号后，切到第一个句末标点（`。；;`）；
   不足 40 字符则继续向后取，直到 ≥40 字符或整行用完（整行不足 40 字符则用整行）；
3. 把探针与各 `AIDP_HOME/reference/约定细则-*.md` 全文**同样归一化**（去 Markdown 强调符 `*`、
   折叠空白）后做子串匹配；命中 = 该条主行被复制进细则分片 → 报重复。

归一化去掉 `*` 与空白差异，是为了让"改了两个星号/换了个空格"的伪装式复制同样被抓到。

## 用法

    python3 AIDP_HOME/scripts/check_convention_dup.py            # 人读报告
    python3 AIDP_HOME/scripts/check_convention_dup.py --json     # 机读 JSON
    python3 AIDP_HOME/scripts/check_convention_dup.py --root /path/to/repo

退出码：0 = 无重复（或缺文件不适用）；1 = 检出重复；2 = 用法/读取错误。

JSON 输出含 `skip_kind` 区分跳过原因，供 `verify.py` 把"真不适用"与"路径假设不匹配"分开报：
`not-aidp`（两个候选主行文件都不存在，非 AIDP 项目）/ `no-conventions`（主行文件在但抽不出
「## 核心约定」主行 —— 格式变更或文件被裁剪，**属异常、需人看**）/ `no-detail-fragments`
（无 `约定细则-N.md` 分片，无从比对）。
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
import sys

# ★ 主行文件候选（按序探测，命中即用）——形态 A 在前、形态 B 在后。
#   顺序不可颠倒：两个文件都在时只有 AGENTS.md 才是主行权威，
#   `CLAUDE.md` 在形态 A 下仅是薄壳（`@AGENTS.md` 一行，抽不出主行）。
MAIN_FILE_CANDIDATES = (
    runtime_text('__AIDP_HOME__/AIDP-AGENTS.md', __file__),  # 模板仓库：下发记忆源（根 AGENTS.md 是模板自身维护记忆，无约定主行）
    "AGENTS.md",  # 形态 A：含 Codex / DeepSeek Harness，或二者并存
    "CLAUDE.md",  # 形态 B：仅 Claude Code
)
DETAIL_GLOB_DIR = runtime_text('__AIDP_HOME__/reference', __file__)
RULES_GLOB_DIR = runtime_text('__AIDP_HOME__/rules', __file__)
DETAIL_PREFIX = "约定细则-"

# 主行形如：`12. **文档动态同步**：…`
MAIN_LINE_RE = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")
SECTION_START_RE = re.compile(r"^##\s+核心约定")
SECTION_END_RE = re.compile(r"^##\s+(?!核心约定)")
# 细则分片的小节标题：`### 约定 N — **<标题>**`（保留项，不参与双写判定）
DETAIL_HEADING_RE = re.compile(r"^#{2,4}\s*约定\s*\d{1,2}\b")
SENTENCE_END = "。；;"
MIN_PROBE_CHARS = 40


def normalize(text):
    """归一化：去 Markdown 强调符 `*`、折叠所有空白为单空格。"""
    text = text.replace("*", "")
    return re.sub(r"\s+", " ", text).strip()


def extract_main_lines(main_text):
    """从「## 核心约定」段提取 [(编号, 主行正文)]（正文已去掉 `N. ` 序号）。"""
    out = []
    in_section = False
    for line in main_text.split("\n"):
        if SECTION_START_RE.match(line):
            in_section = True
            continue
        if in_section and SECTION_END_RE.match(line):
            break
        if not in_section:
            continue
        m = MAIN_LINE_RE.match(line)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def make_probe(body):
    """取首句探针：切到首个句末标点；不足 MIN_PROBE_CHARS 则继续向后取。"""
    norm = normalize(body)
    if len(norm) <= MIN_PROBE_CHARS:
        return norm
    for i, ch in enumerate(norm):
        if ch in SENTENCE_END and i + 1 >= MIN_PROBE_CHARS:
            return norm[: i + 1]
    return norm[:MIN_PROBE_CHARS] if len(norm) > MIN_PROBE_CHARS else norm


def load_details(root):
    """读取所有 约定细则-*.md，返回 [(相对路径, 归一化正文)]。

    ★ 扫描面**排除 `### 约定 N — **<标题>**` 小节标题行**：分片保留标题是设计要求
    （标题即分片的自解释锚点、且它取自主行的粗体标题，天然与主行前缀重合）；
    只有标题之外的正文里再出现主行首句才算双写。
    """
    out = []
    # ① `AIDP_HOME/reference/约定细则-N.md`
    d = os.path.join(root, DETAIL_GLOB_DIR)
    cands = []
    if os.path.isdir(d):
        cands += [(os.path.join(DETAIL_GLOB_DIR, n), os.path.join(d, n))
                  for n in sorted(os.listdir(d))
                  if n.startswith(DETAIL_PREFIX) and n.endswith(".md")]
    # ② ★ `AIDP_HOME/rules/*.md` —— **代码向约定（4/17/18/19/20/23/26/27/28/29/35/39/40）的详规
    #    住在这里，不是 reference/**。只扫 reference/ 时，主行被复制进 rules/ 完全不查：
    #    而 rules 是**按 paths 自动加载**的，一份复制过去的主行会和 AGENTS.md 的那份
    #    同时进上下文，两处一改一没改就是最典型的漂移面。当前实测 0 处，属**无门区**而非无风险。
    rd = os.path.join(root, RULES_GLOB_DIR)
    if os.path.isdir(rd):
        cands += [(os.path.join(RULES_GLOB_DIR, n), os.path.join(rd, n))
                  for n in sorted(os.listdir(rd))
                  if n.endswith(".md") and n != "README.md"]
    for rel, path in cands:
        with open(path, "r", encoding="utf-8") as f:
            body = "\n".join(
                ln for ln in f.read().split("\n")
                if not DETAIL_HEADING_RE.match(ln)
            )
        out.append((rel, normalize(body)))
    return out


def resolve_main_file(root):
    """探测主行文件：按 MAIN_FILE_CANDIDATES 取**第一个存在且真能抽出主行**的候选。

    返回 `(相对路径, 主行列表)`；全不命中返回 `(None, 存在但抽不出主行的候选列表)`。
    "存在但抽不出主行"要与"文件不存在"区分——前者是形态 A 的薄壳 `CLAUDE.md`
    （正常，继续试下一个候选），若**所有**候选都如此则属异常（格式漂移），须报出而非静默跳过。
    """
    present_but_empty = []
    for rel in MAIN_FILE_CANDIDATES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            mains = extract_main_lines(f.read())
        if mains:
            return rel, mains
        present_but_empty.append(rel)
    return None, present_but_empty


# 主行长度上限（字符）：主行只留决策要点 + 详规指针，Why / 实证 / 回检细节放细则分片或 rules。
# 超限只 WARN、不进退出码——常驻上下文膨胀是渐进问题，报出来即可。
MAX_MAIN_CHARS = 600


def run(root):
    main_file, mains = resolve_main_file(root)
    if main_file is None:
        present = mains  # 复用返回槽：此时是"存在但抽不出主行"的候选列表
        if present:
            return {
                "applicable": False,
                "skip_kind": "no-conventions",
                "main_file": None,
                "reason": f"{'、'.join(present)} 存在但抽不出「## 核心约定」主行"
                          f"（格式漂移或文件被裁剪）——非「不适用」，请人工核对",
                "checked": 0,
                "duplicates": [],
            }
        return {
            "applicable": False,
            "skip_kind": "not-aidp",
            "main_file": None,
            "reason": f"{' / '.join(MAIN_FILE_CANDIDATES)} 均不存在（非 AIDP 项目），跳过",
            "checked": 0,
            "duplicates": [],
        }
    details = load_details(root)
    if not details:
        return {
            "applicable": False,
            "skip_kind": "no-detail-fragments",
            "main_file": main_file,
            "reason": f"{DETAIL_GLOB_DIR}/ 下无 {DETAIL_PREFIX}N.md 分片，无从比对，跳过",
            "checked": len(mains),
            "duplicates": [],
        }

    dups = []
    for num, body in mains:
        probe = make_probe(body)
        if len(probe) < MIN_PROBE_CHARS and len(normalize(body)) >= MIN_PROBE_CHARS:
            continue  # 理论不可达；防御性跳过过短探针，避免误报
        for rel, text in details:
            if probe and probe in text:
                dups.append({
                    "convention": num,
                    "file": rel,
                    "probe": probe,
                    "probe_chars": len(probe),
                })
    overlong = [{"convention": num, "chars": len(body)}
                for num, body in mains if len(body) > MAX_MAIN_CHARS]
    return {
        "applicable": True,
        "skip_kind": None,
        "main_file": main_file,
        "reason": "",
        "checked": len(mains),
        "detail_files": [rel for rel, _ in details],
        "duplicates": dups,
        "overlong": overlong,
    }


def main():
    ap = argparse.ArgumentParser(
        description="核心约定主行双写检查：AGENTS.md 主行不得被 约定细则-N.md 复制")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="只输出机读 JSON")
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
        result = run(args.root)
    except Exception as e:  # 读取/解析异常按用法错处理，不伪装成"通过"
        if args.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        if not result["applicable"]:
            # 跳过必须自带 kind：让上游（verify.py / 人）能区分"真不适用"与"路径假设不匹配"
            print(f"[SKIP:{result['skip_kind']}] {result['reason']}")
        elif not result["duplicates"]:
            print(f"[OK] 核心约定主行无双写：已扫 {result['main_file']} 的 "
                  f"{result['checked']} 条主行 × {len(result['detail_files'])} 份细则分片，"
                  f"无一条主行被复制。")
        else:
            print(f"[FAIL] 检出 {len(result['duplicates'])} 处主行双写"
                  f"（主行唯一权威 = {result['main_file']}，细则分片只放子项/Why/示例）：")
            for d in result["duplicates"]:
                print(f"  · 约定 {d['convention']} 的主行首句出现在 {d['file']}")
                print(f"    探针（{d['probe_chars']} 字符）：{d['probe'][:120]}")
            print(f"  修复：删除 {DETAIL_GLOB_DIR}/{DETAIL_PREFIX}N.md 中复制的编号主行，"
                  f"只保留 `### 约定 N — <标题>` 标题 + 该条的子项/Why/示例。")

        for o in result.get("overlong") or []:
            print(f"  [WARN] 约定 {o['convention']} 主行 {o['chars']} 字符 > {MAX_MAIN_CHARS}："
                  f"Why / 实证 / 回检细节移入细则分片或 rules，主行只留决策要点 + 指针")

    return 1 if result["applicable"] and result["duplicates"] else 0


if __name__ == "__main__":
    sys.exit(main())
