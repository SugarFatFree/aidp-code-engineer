#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""命令 / Agent / flow / reference 对 **SKILL 内部文件** 的引用必须真实存在。

## 为什么需要本脚本

命令端按约定 21 只做编排，但为了说清"我调的是哪一步"，正文里大量出现
`dev-logic-architect/scripts/check_ddl_consistency.py`、`auto-test-runner/references/report-format.md`
这类**对 SKILL 内部文件的事实性引用**。这些 SKILL 与命令端各自独立迭代：
SKILL 改个脚本名、并个 reference、删个维度，本项目这边**一个字都不会变**，
引用就此悬空——而且**完全静默**：verify 全绿、测试全过，只有真去执行那一步的
AI 才会发现"文件不存在"，那时已经在下游业务项目的运行现场了。

本轮实测就撞到同类问题：上游把 `.env.example` 从"允许填真实值"改成"只留占位"、
把 `check_env_config.py` 从判红改成 exit 0，而命令端仍写着"判红、永久 N/A、
不作为阻断依据"——**过时了三处，没有任何机器发现**。

## 判据（只查确定性的，不猜语义）

扫 `AIDP_HOME/{commands,agents,flows,reference,rules}/**.md` 正文里形如
`<skill-name>/{scripts,references,assets}/<file>` 的引用：
  · `<skill-name>` 命中 `AIDP_HOME/skills/` 下真实存在的 SKILL 目录 → 该文件必须存在，否则 **ERROR**
  · `<skill-name>` 不是已安装的 SKILL → 跳过（可能是别的项目/示例路径，不归本门管）

⛔ 刻意**不查**维度编号、参数名、章节标题：那些要语义匹配，误报率高，
   一个恒红的门比没有门更糟。本门只做"文件在不在"这一件确定的事。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str((_AidpPath(__file__).resolve().parent if _AidpPath(__file__).resolve().parent.name == "scripts" else _AidpPath(__file__).resolve().parents[1] / "scripts"))
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath
import argparse
import json
import os
import re
import sys

SCAN_DIRS = ["commands", "agents", "flows", "reference", "rules"]
# `<skill>/scripts/x.py` 或 `<skill>/references/x.md`，可带反引号
# ★ `assets/` 也必须认：命令端确实会指名 SKILL 的资产文件（`auto-test-runner` 的 `assets/env-facts-schema.json` 等），
#   它们和 scripts/references 一样会随上游改名/移位而漂——只认两个目录等于给资产引用留了个无门区。
# ★ 左边界 `(?<![\w.-])`：`AIDP_HOME/scripts/x.py` 里的 `aidp` 是目录名、不是 SKILL 名——
#   SKILL 名若恰好与目录名重合（如名为 `aidp` 的 SKILL），缺这道边界会把全部 `AIDP_HOME/scripts/` 引用误判成悬空。
REF_RE = re.compile(
    r"(?<![\w.-])([a-z][a-z0-9-]{2,})/(scripts|references|assets)/([A-Za-z0-9_.\-]+\.(?:py|md|json))")
# ★ 按安装态生成、仓库里天然不存在的文件：不算悬空。
#   `config.json` 由使用者从同目录 `config.example.json` 拷贝填写（凭据类，多数还被 gitignore），
#   而引用它的正文往往**正是在讲"它缺失时怎么办"** —— 把这类判成"上游已删除该文件"是判据错位。
#   判据不写死文件名清单之外的猜测：只豁免"同目录存在 `<名>.example.<后缀>`"这一确定性形态。
def _is_install_time_file(skill_dir, sub, fname):
    stem, dot, ext = fname.rpartition(".")
    if not dot:
        return False
    return os.path.isfile(os.path.join(skill_dir, sub, f"{stem}.example.{ext}"))


def installed_skills(root):
    base = os.path.join(root, runtime_relpath("", __file__), "skills")
    if not os.path.isdir(base):
        return set()
    return {n for n in os.listdir(base) if os.path.isdir(os.path.join(base, n))}


def scan(root="."):
    root = os.path.abspath(root)
    skills = installed_skills(root)
    if not skills:
        return {"applicable": False, "reason": "no-skills-dir", "findings": [], "checked": 0}

    findings, checked, files = [], 0, 0
    for sub in SCAN_DIRS:
        base = os.path.join(root, runtime_relpath("", __file__), sub)
        if not os.path.isdir(base):
            continue
        for cur, dirs, names in os.walk(base):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in sorted(names):
                if not name.endswith(".md"):
                    continue
                path = os.path.join(cur, name)
                rel = os.path.relpath(path, root)
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        lines = f.read().splitlines()
                except OSError:
                    continue
                files += 1
                for i, line in enumerate(lines, 1):
                    for m in REF_RE.finditer(line):
                        skill, kind, fname = m.group(1), m.group(2), m.group(3)
                        if skill not in skills:
                            continue          # 不是已安装 SKILL，不归本门管
                        checked += 1
                        skill_dir = os.path.join(root, runtime_relpath("", __file__), "skills", skill)
                        target = os.path.join(skill_dir, kind, fname)
                        if _is_install_time_file(skill_dir, kind, fname):
                            continue          # 安装态生成（有同名 .example.）—— 仓库里不存在是常态
                        if not os.path.isfile(target):
                            findings.append({
                                "level": "ERROR", "file": rel, "line": i,
                                "ref": f"{skill}/{kind}/{fname}",
                                "detail": ("引用的 SKILL 内部文件不存在——上游改名/删除后本项目未跟进，"
                                           "该步骤到执行现场才会失败"),
                            })
    return {"applicable": True, "findings": findings, "checked": checked, "files": files}


def main():
    ap = argparse.ArgumentParser(description="命令/Agent 对 SKILL 内部文件的引用有效性")
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
    res = scan(args.root)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif not res["applicable"]:
        print(runtime_text(f"'[SKIP] 无 __AIDP_HOME__/skills/ 目录（'{res['reason']}）", __file__))
    elif res["findings"]:
        sys.stderr.write(f"❌ SKILL 内部文件引用悬空 {len(res['findings'])} 处"
                         f"（巡检 {res['files']} 份 .md、{res['checked']} 处引用）：\n")
        for f in res["findings"]:
            sys.stderr.write(f"   · {f['file']}:{f['line']} → {f['ref']}\n")
        sys.stderr.write("   → 上游 SKILL 已改名/删除该文件：按当前 SKILL 事实改写引用，"
                         "或改为不硬编码文件名的表述（如 version-auditor.md 的写法）\n")
    else:
        print(f"[OK] SKILL 内部文件引用全部有效（巡检 {res['files']} 份 .md，{res['checked']} 处引用）")
    return 1 if res["findings"] else 0


if __name__ == "__main__":
    sys.exit(main())
