#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_singlesource_pointer.py — 「单一信源」指针有效性 + 不分裂（脚手架契约脚本）。

## 为什么需要本脚本

「单一信源」是本范式的核心纪律——规则只写一处，别处只留指针（约定 21）。文档里因此散落着
大量 `单一信源 = X` / `详规见 X` / `本处不复述` 之类的断言。但**这些断言目前零机器校验**，
于是有两种失效方式，都很隐蔽：

1. **指针失效**：`X` 指向的文件已改名/删除/移位。读的人点过去扑空，只能回头猜规则在哪。
   本轮实例：`sprint-requirements.md` 指「具体脚本见 version.md Step 2.4.4」，而 2.4.4 早已
   外置到 `planning-4.md`，命令主体那一行只剩指针——指针指向了另一个指针。
2. **指针分裂**：同一条规则被声明了**两个不同的**"单一信源"。此时"单一信源"这个词本身
   就成了谎言，读者按哪个都对、也都不全，改动时更是必漏一处。
   本轮实例：`AGENTS.md` 的约定 35 同时指向 `rules/code.md` 与 `约定细则-4.md`。

## 判据

扫 `AIDP_HOME/{commands,agents,flows,reference,rules}` + `docs/init` 的 `.md`：

- **指针可解析**：断言里出现的**文件路径**（`AIDP_HOME/...` / `docs/...` / 同目录 `xxx.md`）
  必须存在 → 不存在 = **ERROR**。
- **指针不分裂**：同一「主题键」（约定 N / 维度 N / 某命名规则）在不同位置被声明了 ≥2 个
  **不同的**单一信源文件 → **WARN**（需人确认哪个才是权威；不判 ERROR 是因为主题键靠文本
  提取、可能把两条不同规则误并成一个键）。

**只校验能确定性判定的部分**：纯文字断言（如"见 SKILL.md 对应章节"无具体路径）不报——
那属于人读得懂、机器判不了的形态，硬报只会制造噪音。

豁免：`<!-- ssp-check: ignore <理由> -->`（作用域到空行/围栏）；整文件 `ignore-file`。

## 用法

    python3 AIDP_HOME/scripts/check_singlesource_pointer.py [--root <仓库根>] [--json]

退出码：`0`=指针全部可解析 / `1`=检出失效指针 / `2`=用法或读取错误。
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

SCAN = [runtime_text('__AIDP_HOME__/commands', __file__), runtime_text('__AIDP_HOME__/agents', __file__), runtime_text('__AIDP_HOME__/flows', __file__),
        runtime_text('__AIDP_HOME__/reference', __file__), runtime_text('__AIDP_HOME__/rules', __file__), "docs/init"]
IGNORE_LINE = re.compile(r"<!--\s*ssp-check:\s*ignore(?!-file)\b[^>]*-->")
IGNORE_FILE = re.compile(r"<!--\s*ssp-check:\s*ignore-file\b[^>]*-->")

# 「单一信源」类断言（出现其一即认为本行在声明权威落点）
ASSERT_RE = re.compile(r"单一信源|详规见|详见|权威(?:定义|判定|来源)|本处不复述|不复述")
# 行内代码里的路径：`AIDP_HOME/xxx.md` / `docs/init/xxx.md` / `xxx.md` / `flows/a/b.md`
PATH_RE = re.compile(r"`([^`\s]+\.(?:md|py|json|js|cjs|mjs|yml|yaml))`")
# 主题键：约定 N / 维度 N（用于分裂检测）
# ★ 子作用域标注：一条约定常被拆成若干子域，各有各的权威处（约定 24 = 总开关 / 判定派单 /
#   流程细则 三层）。这是**分层**、不是分裂；没有标注机制时只能按约定号聚合、必然误报。
#   用法：在声明行尾加 `<!-- singlesource-scope: 总开关 -->`，该行即归入 `约定24#总开关` 桶。
SCOPE_RE = re.compile(r"<!--\s*singlesource-scope:\s*([^\s>-]+)\s*-->")
TOPIC_RE = re.compile(r"约定\s*(\d+(?:\.\d+)?)|维度\s*(\d+[a-z]?)")

# ★ 只校验【契约文件路径】——必须带目录且落在 AIDP_HOME/ 或 docs/init/ 下。
#   不这样收窄的话，178 处命中全是误报，形态有三类、都不该报：
#     ① 运行时文件（`.mcp.json` / `config.json` / `memory/.sprint-autopilot-baseline.json`）——由命令生成，仓库里本就没有
#     ② 迭代产物（`00_索引.md` / `对外开放接口.md`）——落在 docs/{version}/ 下，模板项目里不存在
#     ③ 省略/泛指写法（`（+ -2.md）` / `phase-0-N.md`）——本就不是完整路径
#   契约文件则不同：它们随脚手架下发、必须真实存在，指不到就是真断链。
CONTRACT_REF = re.compile(r"^(?:\.aidp|docs/init)/[^\s]+$")
# 这些"路径"是占位/示例，即便落在契约目录下也不参与校验
PLACEHOLDER = re.compile(r"[{}<>*]|^\.\.\.|NN_|｛|＜|[A-Z]-?N\.|/N\.")
# ★ 运行时凭据文件：由用户按 `config.example.json` 自建、已 gitignore，仓库里本就不存在。
#   它们确实落在 AIDP_HOME/ 下，但"不存在"是设计而非断链——不排除会产生恒定的 2 处假红灯。
RUNTIME_REF = re.compile(r"/config\.json$|/auth\.[^/]+\.json$|\.env$|/\.mcp\.json$")


def _read(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _resolve(root, base_dir, ref):
    """按「仓库根相对 → 同目录相对 → 全仓 basename 唯一匹配」三级解析。"""
    cands = [os.path.join(root, ref), os.path.join(base_dir, ref)]
    for c in cands:
        if os.path.exists(c):
            return True
    # basename 兜底：同名文件在仓库里唯一存在即认为可解析（文档常只写文件名）。
    # ⛔ **搜索面必须排除脚手架 bundle**（`assets/aidp/` 下保留了每个契约文件的完整副本）：
    #    否则从 `AIDP_HOME/flows/` 删掉一个分片后，只要还没重跑 `mirror_to_bundle.py`，
    #    指向它的指针**依然判"可解析"** —— 兜底把本该报出的断链兜没了。
    bn = os.path.basename(ref)
    # ⛔ **带目录分隔符的引用不吃 basename 兜底**：写全了路径就是要求按这个路径找得到。
    #    兜底的本意是照顾「详规见 `约定细则-5.md`」这类裸文件名写法；把它扩到完整路径上，
    #    等于 `AIDP_HOME/flows/完全虚构的目录/planning-4.md` 也判"可解析" —— 路径写错
    #    （目录改名、分片迁移后没跟着改）这一整类断链就此全部隐身。
    if "/" in ref or os.sep in ref:
        return False
    # 脚手架 bundle 的位置随安装形态变（模板仓库根级 `skills/`、下游 `.claude|.agents/skills/`、
    # 历史的 `AIDP_HOME/skills/`）→ 按路径片段识别，不写死某一种落点。
    _BUNDLE = os.path.join("aidp-code-engineer", "assets")
    for rel in SCAN + [runtime_text('__AIDP_HOME__/scripts', __file__), runtime_text('__AIDP_HOME__/skills', __file__), runtime_text('__AIDP_HOME__/templates', __file__), "docs"]:
        d = os.path.join(root, rel)
        if not os.path.isdir(d):
            continue
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if not x.startswith(".")]
            if _BUNDLE in dirpath:
                continue
            if bn in filenames:
                return True
    return False


def run(root):
    findings = []
    topics = {}        # 主题键 → {信源文件: [出处]}
    scanned = 0
    for rel in SCAN:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in sorted(filenames):
                if not fn.endswith(".md"):
                    continue
                path = os.path.join(dirpath, fn)
                text = _read(path)
                if not text or IGNORE_FILE.search(text):
                    continue
                scanned += 1
                here = os.path.relpath(path, root)
                exempt = False
                for i, line in enumerate(text.split("\n"), 1):
                    if IGNORE_LINE.search(line):
                        exempt = True
                        continue
                    if exempt:
                        if not line.strip() or line.lstrip().startswith("```"):
                            exempt = False
                        continue
                    if not ASSERT_RE.search(line):
                        continue
                    refs = [r for r in PATH_RE.findall(line)
                            if CONTRACT_REF.match(r) and not PLACEHOLDER.search(r)
                            and not RUNTIME_REF.search(r)]
                    for r in refs:
                        if not _resolve(root, dirpath, r):
                            findings.append({
                                "level": "ERROR", "file": here, "line": i, "ref": r,
                                "detail": f"「单一信源/详规」指针 `{r}` 解析不到——读的人点过去扑空、"
                                          f"只能回头猜规则在哪",
                            })
                    # 分裂检测：本行同时提到主题键与信源文件
                    tm = TOPIC_RE.search(line)
                    if tm and refs:
                        key = "约定" + tm.group(1) if tm.group(1) else "维度" + tm.group(2)
                        sm = SCOPE_RE.search(line)
                        if sm:
                            key += "#" + sm.group(1)
                        topics.setdefault(key, {})
                        for r in refs:
                            topics[key].setdefault(os.path.basename(r), []).append(f"{here}:{i}")

    for key, srcs in sorted(topics.items()):
        if len(srcs) >= 2:
            # 判据：跨全仓聚合同一主题键，只报「≥2 个信源【各被声明 ≥2 次】」——单次提及
            # 多半是顺带引用、不是权威声明。⛔ 别把它写成"只报同一行内"：一条约定的
            # 多个信源恰恰散在不同文件，同行反而少见。
            multi = {k: v for k, v in srcs.items() if len(v) >= 2}
            if len(multi) >= 2:
                findings.append({
                    "level": "WARN", "file": "-", "line": 0, "ref": key,
                    "detail": f"{key} 被声明了 {len(multi)} 个不同的单一信源："
                              f"{'、'.join(multi)} —— 「单一信源」若有两个，改动时必漏一处",
                })

    errs = [f for f in findings if f["level"] == "ERROR"]
    return {"applicable": scanned > 0, "scanned": scanned,
            "findings": findings, "passed": not errs}


def main():
    ap = argparse.ArgumentParser(description="「单一信源」指针有效性 + 不分裂检查")
    ap.add_argument("--root", default=".")
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
    try:
        res = run(args.root)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[ERROR] 检查执行失败：{e}")
        return 2
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["passed"] else 1
    if not res["applicable"]:
        print("[SKIP] 无可扫描的 .md")
        return 0
    errs = [f for f in res["findings"] if f["level"] == "ERROR"]
    warns = [f for f in res["findings"] if f["level"] == "WARN"]
    if not errs:
        print(f"[OK] 「单一信源」指针全部可解析（巡检 {res['scanned']} 份 .md"
              + (f"，{len(warns)} 处指针分裂 WARN" if warns else "") + "）。")
        for f in warns:
            print(f"  · [WARN] {f['ref']}：{f['detail']}")
        return 0
    print(f"[FAIL] 检出 {len(errs)} 处失效的「单一信源」指针：")
    for f in errs:
        print(f"  · {f['file']}:{f['line']} → `{f['ref']}` —— {f['detail']}")
    for f in warns:
        print(f"  · [WARN] {f['ref']}：{f['detail']}")
    print("  修复：改指到真实存在的文件；已移位的写新落点；确属示例路径 → 加 `<!-- ssp-check: ignore <理由> -->`。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
