#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 20「同族增量项」的确定性机器检查（F0–F4）。

## 这条检查要拦的东西

一个页面承载「每个版本各加一个同构成员」的家族（运维入口、菜单项、版本区块、
增量脚本、索引条目、枚举项、页签…）。每次新增都复发同两个问题：

  ① 新成员**没有公共外壳**——家族没抽公共单元，父页样式又是 scoped 传不进去，
     于是每个成员各自复制一份样式，漏抄即失效；
  ② 新成员**插错顺序**——顺序靠「写在文件里的物理位置」+ 一行注释提醒，无任何机器约束。

两者的共同特征才是要点：**失败形态是"看起来正常"**——类型检查、lint、单测全绿，
构建通过，只有人打开页面并排比对才看得出来；而「照着隔壁那个成员复制一份」
是执行体最自然的动作。不设机器约束，它就按版本线性复发
（实际项目中同一形态可连续复发多个版本：每加一个成员就复现一次）。

## 为什么判据是「声明驱动」而不是「自动识别家族」

自动识别（如"同目录 ≥3 个文件名符合同一命名模板"）在真实仓库里会大面积误报：
本脚手架自己的 `flows/sprint-autopilot/phase-3-*.md`、`reference/约定细则-*.md`、
下游的 `docs/deployment/{version}/sql/NN_*.sql` 全都命中——而**它们的顺序恰恰
就该由文件名序号（物理位置）决定，也不该有注册表**。对这类家族恒红，
下游第一件事就是把整个脚本关掉，那比漏报糟得多。

故：**家族必须显式声明**，脚本只对已声明的家族做 Critical 判定。
未声明的家族只保留一条极窄的 Important 提示（F4），且只看"多个成员各自定义了同名
CSS 类"这一种确定性形态——这正是"没有公共外壳"的指纹。

## 声明格式（一行，写在注册表文件头 / 家族目录 README / 任意文本文件里）

    SIBLING-FAMILY: name=ops-entries members=src/views/ops/entries/*.vue \
                    registry=src/views/ops/entries/index.ts shell=src/components/OpsEntryCard.vue order=registry

  · `name`     家族名（报告里用）                         【必填】
  · `members`  成员 glob，相对仓库根                       【必填】
  · `registry` 注册表/索引文件（成员在此登记）             【必填】
  · `shell`    公共外壳单元路径                            【可选，给了才查 F1】
  · `order`    `registry`=顺序由注册表数据计算 / `none`=本家族无顺序语义【可选，缺省 none】

声明只在 `code/` 与 `docs/` 下扫描（⛔ 不扫运行契约目录，理由见 DECL_ROOTS 处注释）。

外壳标记（可选，写在 shell 文件里，给了才查 F1）：

    SHELL-MARKERS: .ops-entry-card,.ops-entry-card__title

## 检查项

  F0 Critical  声明失效：members 命中 0 个文件，或 registry/shell 路径不存在
               （防"声明过但早已漂移"——那种状态下 F1/F2 会静默全绿）
  F1 Critical  成员自带外壳：成员文件里**定义**了 shell 声明的外壳类名
  F2 Critical  成员未登记：成员未出现在 registry 文件里
  F3 Important order=registry 时，注册表里成员缺排序键或排序键重复（顺序仍未数据化）
  F4 Important 未声明家族：同目录 ≥3 个同模板文件中，≥3 个各自定义了同一个 CSS 类名

豁免：受检文件任意处含 `sibling-family-ignore: <F号> <原因>`，**原因必填**
（空原因不放行——否则豁免就成了隐形关闭）。

用法:
    python3 AIDP_HOME/scripts/check_sibling_family.py                 # 全量
    python3 AIDP_HOME/scripts/check_sibling_family.py --json          # 机器消费
    python3 AIDP_HOME/scripts/check_sibling_family.py --changed-only  # 只看本次改动涉及的家族
    python3 AIDP_HOME/scripts/check_sibling_family.py --self-check    # 阳性对照自检

退出码: 0 = 无 Critical；1 = 有 Critical；2 = 用法错误。
"""

from __future__ import annotations

import argparse
import glob as globmod
import json
import os
import re
import subprocess
import sys
from pathlib import Path

DECL_RE = re.compile(r"SIBLING-FAMILY\s*:\s*(.+)")
MARKERS_RE = re.compile(r"SHELL-MARKERS\s*:\s*(.+)")
WAIVER_RE = re.compile(r"sibling-family-ignore\s*:\s*(F\d)\s*(.*)", re.IGNORECASE)
# CSS 类**定义**（`.cls {` / `.cls,` / `.cls::before {`），⛔ 不是"使用"（class="cls"）
CLASS_DEF_RE = re.compile(r"^\s*\.([A-Za-z_][\w-]{2,})(?:::?[\w-]+)?\s*[,{]", re.MULTILINE)
# 同模板文件名：共同前缀 + 版本/序号 + 共同后缀
TEMPLATE_RE = re.compile(r"^(?P<pre>.*?)(?P<num>V?\d[\d._-]*)(?P<post>.*)$")

SCAN_SUFFIX = {".vue", ".jsx", ".tsx", ".css", ".scss", ".less"}
SCAN_ROOTS = ("code",)
SKIP_DIR_PARTS = {"node_modules", "dist", "build", "target", "out", ".git",
                  "__pycache__", "coverage", "vendor", ".next", ".nuxt"}
# ⛔ 声明只在**项目内容**里扫（`code/` 与 `docs/`），刻意**不扫运行契约目录**：
#   规则文档、本脚本自身的 docstring 与自检夹具里都写着示例声明，扫进来会把
#   「文档里的例子」当成「真实家族」判 F0——检查器对自己恒红，是最没说服力的失效形态。
DECL_ROOTS = ("code", "docs")
DECL_SUFFIX = {".vue", ".ts", ".js", ".tsx", ".jsx", ".java", ".kt", ".py", ".go",
               ".sql", ".md", ".json", ".yaml", ".yml", ".scss", ".css", ".less"}


class Finding:
    def __init__(self, rule, severity, path, message, evidence="", family=""):
        self.rule, self.severity, self.path = rule, severity, path
        self.message, self.evidence, self.family = message, evidence, family

    def as_dict(self):
        return {"rule": self.rule, "severity": self.severity, "path": self.path,
                "family": self.family, "message": self.message, "evidence": self.evidence}


def _read(p):
    try:
        return Path(p).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _iter_files(root, roots, suffixes):
    for r in roots:
        base = Path(root) / r
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix.lower() not in suffixes:
                continue
            if SKIP_DIR_PARTS & set(p.parts):
                continue
            yield p


# 注释结束符：声明常写在注释里（`<!-- … -->` / `/* … */`），⛔ 不去掉它们会把
# `-->` 当成类名的一部分、也会把 `sibling-family-ignore: F2 -->` 当成"写了原因"——
# 后者更危险：豁免会在原因为空时静默生效，正好废掉「原因必填」这条。
_COMMENT_TAIL_RE = re.compile(r"(-->|\*/|\?>|#\}|\}\})\s*$")
_MEANINGFUL_RE = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")


def _clean(s):
    return _COMMENT_TAIL_RE.sub("", (s or "").strip()).strip()


def waived(text, rule):
    """文件内任意处 `sibling-family-ignore: <F号> <原因>` 且**原因非空** → 豁免。"""
    for m in WAIVER_RE.finditer(text or ""):
        if m.group(1).upper() != rule:
            continue
        if _MEANINGFUL_RE.search(_clean(m.group(2))):
            return True
    return False


def parse_declarations(root):
    """扫出全部 SIBLING-FAMILY 声明。返回 [{name, members, registry, shell, order, decl_path}]。"""
    out = []
    for p in _iter_files(root, DECL_ROOTS, DECL_SUFFIX):
        text = _read(p)
        if "SIBLING-FAMILY" not in text:
            continue
        for m in DECL_RE.finditer(text):
            kv = dict(re.findall(r"(\w+)\s*=\s*([^\s\\]+)", m.group(1)))
            if not {"name", "members", "registry"} <= set(kv):
                out.append({"_bad": m.group(1).strip()[:120],
                            "decl_path": str(p.relative_to(root))})
                continue
            kv["order"] = kv.get("order", "none")
            kv["decl_path"] = str(p.relative_to(root))
            out.append(kv)
    return out


def family_members(root, members_glob):
    hits = sorted(globmod.glob(os.path.join(root, members_glob), recursive=True))
    return [Path(h) for h in hits if os.path.isfile(h)]


def shell_markers(root, shell_rel):
    txt = _read(Path(root) / shell_rel)
    m = MARKERS_RE.search(txt)
    if not m:
        return []
    return [x for x in (_clean(c).lstrip(".") for c in _clean(m.group(1)).split(",")) if x]


def _entry_scope(text, key):
    """取 `key` 在注册表里**自己那一条**的范围（供找它自己的排序键）。

    ⛔ 不能按「整行」取：注册表常写成一行数组
    `[{ comp: 'A', order: 10 }, { comp: 'B', order: 20 }]` —— 按行找的话每个成员都会匹配到
    行首那个 `order: 10`，于是**全体成员被判成排序键重复**（实测复现）。
    故以 key 的位置为中心，左右各扩到最近的条目边界（`{}` / `[]` / 逗号 / 换行）。
    """
    i = text.find(key)
    if i < 0:
        return ""
    left = max((text.rfind(c, 0, i) for c in "{[\n"), default=-1)
    right_cands = [x for x in (text.find(c, i) for c in "}]\n") if x >= 0]
    right = min(right_cands) if right_cands else len(text)
    return text[left + 1:right]


def check_declared(root, fam, findings, limit_to=None):
    """F0/F1/F2/F3 —— 只对显式声明的家族生效，判据全部确定性。"""
    if "_bad" in fam:
        findings.append(Finding("F0", "Critical", fam["decl_path"],
                                "SIBLING-FAMILY 声明缺 name/members/registry 之一，无法据其检查",
                                fam["_bad"]))
        return
    name, decl = fam["name"], fam["decl_path"]
    members = family_members(root, fam["members"])
    reg_rel = fam["registry"]
    reg_abs = Path(root) / reg_rel

    if not members:
        findings.append(Finding("F0", "Critical", decl,
                                f"家族「{name}」的 members 未命中任何文件——声明已与代码漂移",
                                fam["members"], name))
        return
    if not reg_abs.is_file():
        findings.append(Finding("F0", "Critical", decl,
                                f"家族「{name}」声明的 registry 不存在", reg_rel, name))
        return
    shell_rel = fam.get("shell")
    if shell_rel and not (Path(root) / shell_rel).is_file():
        findings.append(Finding("F0", "Critical", decl,
                                f"家族「{name}」声明的 shell（公共外壳）不存在", shell_rel, name))
        return

    reg_text = _read(reg_abs)
    markers = shell_markers(root, shell_rel) if shell_rel else []

    for mp in members:
        rel = str(mp.relative_to(root))
        if limit_to is not None and rel not in limit_to:
            continue
        text = _read(mp)
        stem = mp.stem

        # F2 成员未登记
        if stem not in reg_text and rel not in reg_text and not waived(text, "F2"):
            findings.append(Finding("F2", "Critical", rel,
                                    f"家族「{name}」的成员未登记进注册表 {reg_rel}"
                                    "（顺序与渲染都由注册表驱动，未登记 = 这个成员不会出现）",
                                    stem, name))
        # F1 成员自带外壳
        if markers and not waived(text, "F1"):
            own = {c for c in CLASS_DEF_RE.findall(text)} & set(markers)
            if own:
                findings.append(Finding("F1", "Critical", rel,
                                        f"家族「{name}」的成员自己定义了公共外壳类"
                                        f"（外壳应唯一来自 {shell_rel}；各自定义 = 复制一份、必然分叉）",
                                        ",".join(sorted(own)), name))

    # F3 顺序仍未数据化
    if fam.get("order") == "registry" and not waived(reg_text, "F3"):
        seen, dups = {}, []
        for mp in members:
            scope = _entry_scope(reg_text, mp.stem) or _entry_scope(reg_text, str(mp.relative_to(root)))
            k = re.search(r"\b(?:order|sort|seq|weight)\b\W{0,3}(\d+)", scope or "")
            if not k:
                findings.append(Finding(
                    "F3", "Important", reg_rel,
                    f"家族「{name}」声明 order=registry，但成员在注册表里没有排序键"
                    "（order/sort/seq/weight=<数字>）——顺序实际仍由物理位置决定",
                    mp.stem, name))
                continue
            if k.group(1) in seen:
                dups.append((mp.stem, k.group(1), seen[k.group(1)]))
            seen.setdefault(k.group(1), mp.stem)
        for stem, k, other in dups:
            findings.append(Finding("F3", "Important", reg_rel,
                                    f"家族「{name}」排序键重复（{k}，与 {other} 相同），顺序不确定",
                                    stem, name))


def check_undeclared(root, findings, limit_to=None):
    """F4 —— 未声明家族的窄提示：同目录 ≥3 个同模板文件，≥3 个各自定义同一个 CSS 类名。

    ⛔ 刻意收窄到「≥3 个文件各自定义同名类」这一种形态：那是"没有公共外壳、各抄一份"
    的指纹。只按文件名模板判会命中一大批顺序本就该由文件名决定的合法家族（见文件头）。
    """
    bydir = {}
    for p in _iter_files(root, SCAN_ROOTS, SCAN_SUFFIX):
        bydir.setdefault(p.parent, []).append(p)

    for d, files in bydir.items():
        if len(files) < 3:
            continue
        groups = {}
        for p in files:
            m = TEMPLATE_RE.match(p.name)
            if m:
                groups.setdefault((m.group("pre"), m.group("post")), []).append(p)
        for (pre, post), fam in groups.items():
            if len(fam) < 3:
                continue
            cls_owner = {}
            for p in fam:
                text = _read(p)
                if waived(text, "F4"):
                    continue
                for c in set(CLASS_DEF_RE.findall(text)):
                    cls_owner.setdefault(c, []).append(p)
            for c, owners in cls_owner.items():
                if len(owners) < 3:
                    continue
                rels = sorted(str(o.relative_to(root)) for o in owners)
                if limit_to is not None and not (set(rels) & limit_to):
                    continue
                findings.append(Finding(
                    "F4", "Important", rels[0],
                    f"疑似同族增量项无公共外壳：{len(owners)} 个同模板文件（{pre}*{post}）"
                    f"各自定义了同一个类 .{c}——按约定 20「同族增量项」应抽公共外壳并显式声明 "
                    "SIBLING-FAMILY，或就地 `sibling-family-ignore: F4 <原因>`",
                    ",".join(rels[:5])))


def changed_paths(root):
    """本次改动涉及的文件（已跟踪改动 + 未跟踪新增）。取不到 → None（退回全量）。"""
    try:
        r = subprocess.run(["git", "-C", str(root), "status", "--porcelain"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    out = set()
    for ln in (r.stdout or "").splitlines():
        s = ln[3:].strip().strip('"')
        if "->" in s:
            s = s.split("->")[-1].strip()
        out.add(s)
    return out


def run(root, changed_only=False, checks=("F0", "F1", "F2", "F3", "F4")):
    findings = []
    limit = changed_paths(root) if changed_only else None
    fams = parse_declarations(root)
    for fam in fams:
        check_declared(root, fam, findings, limit_to=limit)
    if "F4" in checks:
        check_undeclared(root, findings, limit_to=limit)
    findings = [f for f in findings if f.rule in checks]
    return fams, findings


def self_check(argv_root=None):
    """阳性对照：注入一个必然被抓到的家族缺陷 → 必须报；修好 → 必须全绿（证明非恒红）。"""
    import shutil
    import tempfile
    d = Path(tempfile.mkdtemp())
    ok = []
    try:
        base = d / "code/frontend/app/src"
        (base / "views/ops").mkdir(parents=True)
        (base / "components").mkdir(parents=True)
        (base / "components/OpsCard.vue").write_text(
            "<!-- SHELL-MARKERS: .ops-card,.ops-card__title -->\n"
            "<style scoped>\n.ops-card { border: 1px solid; }\n</style>\n", encoding="utf-8")
        # 注册表登记了两个成员，第三个（新加的那个）漏登记，且自己抄了一份外壳样式
        (base / "views/ops/index.ts").write_text(
            "// SIBLING-FAMILY: name=ops-entries members=code/frontend/app/src/views/ops/Entry*.vue "
            "registry=code/frontend/app/src/views/ops/index.ts "
            "shell=code/frontend/app/src/components/OpsCard.vue order=registry\n"
            "export const entries = [\n"
            "  { comp: 'EntryV09', order: 10 },\n"
            "  { comp: 'EntryV10', order: 20 },\n"
            "]\n", encoding="utf-8")
        for n in ("EntryV09", "EntryV10"):
            (base / f"views/ops/{n}.vue").write_text(
                "<template><OpsCard/></template>\n", encoding="utf-8")
        (base / "views/ops/EntryV11.vue").write_text(
            "<template><div class=\"ops-card\"/></template>\n"
            "<style scoped>\n.ops-card { border: 1px solid; }\n</style>\n", encoding="utf-8")

        _f, found = run(str(d))
        rules = {f.rule for f in found}
        ok.append(("★ 漏登记的新成员被 F2 抓到", "F2" in rules))
        ok.append(("★ 成员自带外壳类被 F1 抓到", "F1" in rules))
        ok.append(("⛔ 反例自证：注册表里确实没有 EntryV11（否则本用例是空跑）",
                   "EntryV11" not in (d / "code/frontend/app/src/views/ops/index.ts")
                   .read_text(encoding="utf-8")))

        # 修好：登记 + 去掉自带外壳 → 必须全绿
        (base / "views/ops/index.ts").write_text(
            (base / "views/ops/index.ts").read_text(encoding="utf-8")
            .replace("]\n", "  { comp: 'EntryV11', order: 30 },\n]\n"), encoding="utf-8")
        (base / "views/ops/EntryV11.vue").write_text(
            "<template><OpsCard/></template>\n", encoding="utf-8")
        _f2, found2 = run(str(d))
        ok.append(("★ 修好后全绿（证明本检查不是恒红）", not found2))

        # 声明漂移（members 命中 0）必须报 F0，否则 F1/F2 会静默全绿
        (base / "views/ops/index.ts").write_text(
            (base / "views/ops/index.ts").read_text(encoding="utf-8")
            .replace("members=code/frontend/app/src/views/ops/Entry*.vue",
                     "members=code/frontend/app/src/views/ops/Gone*.vue"), encoding="utf-8")
        _f3, found3 = run(str(d))
        ok.append(("★ 声明与代码漂移 → F0（不给静默全绿）",
                   any(f.rule == "F0" for f in found3)))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if all(r for _, r in ok) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="约定 20「同族增量项」确定性检查")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--changed-only", action="store_true",
                    help="只看本次改动涉及的文件（开发期静态门用）")
    ap.add_argument("--check", action="append", default=[],
                    help="只跑某几条（F0/F1/F2/F3/F4），可多次")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return self_check()

    root = str(Path(a.root).resolve())
    checks = tuple(c.upper() for c in a.check) if a.check else ("F0", "F1", "F2", "F3", "F4")
    fams, findings = run(root, changed_only=a.changed_only, checks=checks)
    crit = [f for f in findings if f.severity == "Critical"]

    if a.json:
        print(json.dumps({"families": len([f for f in fams if "_bad" not in f]),
                          "findings": [f.as_dict() for f in findings],
                          "criticals": len(crit)}, ensure_ascii=False))
    else:
        print(f"[sibling-family] 已声明家族 {len([f for f in fams if '_bad' not in f])} 个；"
              f"发现 {len(findings)} 项（Critical {len(crit)}）")
        for f in findings:
            print(f"  [{f.severity}] {f.rule} {f.path}：{f.message}"
                  + (f"（{f.evidence}）" if f.evidence else ""))
        if findings:
            print("豁免写法：在该文件里写 `sibling-family-ignore: <F号> <原因>`（原因必填）")
    return 1 if crit else 0


if __name__ == "__main__":
    sys.exit(main())
