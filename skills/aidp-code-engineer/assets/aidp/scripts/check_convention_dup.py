#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核心约定主行双写守卫。

主行唯一权威为运行根的 reference/core-conventions.md；旧安装回退到
AIDP-AGENTS.md / AGENTS.md / CLAUDE.md。运行根统一由 aidp_runtime 定位，
兼容模板维护源、Claude 单独安装、共享运行根及历史嵌套布局。

细则分片与 rules 只放子项、Why、示例，不复制决策主行。检测主行的首句
探针（去强调与空白差异），小节标题不参与。超长主行只告警。

用法：python3 AIDP_HOME/scripts/check_convention_dup.py --root . [--json]
退出码：0 无重复或不适用，1 重复，2 读取错误。skip_kind 区分 not-aidp、
no-conventions（已有文件却无约定，须人工核对）与 no-detail-fragments。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text, contract_root, convention_candidates
import argparse
import json
import os
import re
import sys

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


# 主行常以「**★ <标题>**：」或「**<标题>**：」开头；复制方往往**丢掉标题前缀**只抄正文，
# 于是带标题的探针一个字都匹配不上。⛔ 不能只留一种形态 —— 2026-09-24 审计实测：
# 约定 23 的主行正文被逐字抄进 `rules/code.md`，本门照报「无一条主行被复制」。
_TITLE_PREFIX_RE = re.compile(r"^★?\s*[^：:]{2,60}[：:]\s*")


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
    home = contract_root(root)
    detail_dir = (home / "reference").relative_to(_AidpPath(root)).as_posix()
    rules_dir = (home / "rules").relative_to(_AidpPath(root)).as_posix()
    d = os.path.join(root, detail_dir)
    cands = []
    if os.path.isdir(d):
        cands += [(os.path.join(detail_dir, n), os.path.join(d, n))
                  for n in sorted(os.listdir(d))
                  if n.startswith(DETAIL_PREFIX) and n.endswith(".md")]
    # ② ★ `AIDP_HOME/rules/*.md` —— **代码向约定（4/17/18/19/20/23/26/27/28/29/35/39/40）的详规
    #    住在这里，不是 reference/**。只扫 reference/ 时，主行被复制进 rules/ 完全不查：
    #    而 rules 是**按 paths 自动加载**的，一份复制过去的主行会和 AGENTS.md 的那份
    #    同时进上下文，两处一改一没改就是最典型的漂移面。当前实测 0 处，属**无门区**而非无风险。
    rd = os.path.join(root, rules_dir)
    if os.path.isdir(rd):
        cands += [(os.path.join(rules_dir, n), os.path.join(rd, n))
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
    """共享定位器给出外置文件及旧记忆候选，取权威主行。

    返回 `(相对路径, 主行列表)`；全不命中返回 `(None, 存在但抽不出主行的候选列表)`。
    "存在但抽不出主行"要与"文件不存在"区分——前者是形态 A 的薄壳 `CLAUDE.md`
    （正常，继续试下一个候选），若**所有**候选都如此则属异常（格式漂移），须报出而非静默跳过。
    """
    present_but_empty = []
    for path in convention_candidates(root):
        rel = path.relative_to(_AidpPath(root)).as_posix()
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            mains = extract_main_lines(f.read())
        if mains:
            return rel, mains
        present_but_empty.append(rel)
        if path.name == "core-conventions.md":
            break  # 已声明的外置权威损坏，不能退到旧正文掩盖异常。
    return None, present_but_empty


# 主行长度上限（字符）：主行只留决策要点 + 详规指针，Why / 实证 / 回检细节放细则分片或 rules。
# 超限只 WARN、不进退出码——按需协议膨胀是渐进问题，报出来即可。
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
            "reason": f"{' / '.join(str(p) for p in convention_candidates(root))} 均不存在（非 AIDP 项目），跳过",
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
        probes = []
        for cand in (make_probe(body), make_probe(_TITLE_PREFIX_RE.sub("", normalize(body), count=1))):
            if cand and cand not in probes and len(cand) >= MIN_PROBE_CHARS:
                probes.append(cand)
        if not probes and len(normalize(body)) < MIN_PROBE_CHARS:
            probes = [make_probe(body)]
        for probe in probes:
            if len(probe) < MIN_PROBE_CHARS and len(normalize(body)) >= MIN_PROBE_CHARS:
                continue  # 防御性跳过过短探针，避免误报
            for rel, text in details:
                if probe and probe in text:
                    if any(d["convention"] == num and d["file"] == rel for d in dups):
                        continue   # 同一条主行两种探针命中同一文件，只登记一次
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
        description="核心约定主行双写检查：外置主行不得被细则与 rules 复制")
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
