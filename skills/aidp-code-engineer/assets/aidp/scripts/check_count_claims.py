#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check_count_claims.py — 文档里的「自称计数」必须与被数的东西对得上（脚手架契约脚本）。

## 为什么需要本脚本

范式文档到处写着「N 项核心约定」「N 个语义维度」「共 N 组」这类**自称计数**。
它们的共同点是：**加东西的人不会想起去改数字**，而读的人会当真——
「3 个语义维度」会让执行体跑完第 3 个就收工，第 4 维静默不执行；
「共 9 组」会让人以为测试套件只有 9 组、多出来的 7 组是不是野生的。
一次审计一口气抓到三处过期：`aidp-compliance`「3 个语义维度」实为 4、
`AIDP_HOME/scripts/README.md`「共 9 组」实为 16、`设计目标.md`「36 项核心约定」实为 37。

计数**天然是确定性的**——被数的东西就在仓库里、数得出来。这类东西不该靠人记得回头改。

## 判定口径（三类；宁可少做，不可误报）

只做"能确定性核出真值"的三类，其余（如「14 维度检查」散落在各 SKILL 正文里、没有可数的结构）不碰：

1. **核心约定数** —— `N 项核心约定` / `核心约定 1–N` / `约定 1-N` / `核心约定 N 条`
   ⇢ 真值 = 「核心约定」正文的**最大约定号**（`^N. **` 形态），口径复用
   `verify.py::check_convention_anchor_consistency`；正文权威文件同 `_convention_source`：
   两文件并存时 = `AGENTS.md`；仅 Claude Code 的单文件形态 = `CLAUDE.md`。
   （与 verify.py 的差别：那边只扫 4 个固定文件、本脚本扫全仓——「36 项核心约定」正是漂在
   `设计目标.md` 这种不在那 4 个之列的文件里。）
2. **语义维度数** —— `N 个语义维度`
   ⇢ 真值 = `AIDP_HOME/agents/aidp-compliance.md` 里 `### … 语义维度 N` 小节数。
3. **测试分组数** —— `共 N 组`，**且同一行提到 `test_guard_scripts`**（用行内共现锁定上下文，
   不写死文件名：换个 README 写同一句话照样被核）
   ⇢ 真值 = `AIDP_HOME/scripts/tests/test_guard_scripts.py` 里 `print("【…】")` 的分组数。

任一真值取不到（文件缺失/形态不符）→ 该类**整类跳过**、不猜、不报（下游可能没有 agents 目录）。

## `--project-claims`：业务计数声明的全库回扫（下游反馈 · 本轮最大单项耗时）

上面三类真值全是**脚手架自己的**计数。而下游最痛的是**业务计数声明**——一次「检测项固定 14 项
→ 动态 13/14」的口径变化，在设计 / 接口 / 需求 / 计划 / 自测用例 / 代码注释里散落约 **25 处**，
全靠人肉 `grep -rn "14 项\|14 行\|共 14"` 再逐条判定：哪些是「说明取值域的合法留存（全集 14 项）」、
哪些是「必须改的计数断言（恰 14 行）」、哪些是「同名但完全无关的历史表述」。
而"旧计数在文档里继续生效"正是约定 22 要防的**最高频形态**。

`--project-claims <设计目录>` 从设计文档里读「业务计数声明表」（5 列：声明名 / 当前值 /
是否动态 / 权威出处 / 散落面正则——grep BRE 的 `\|` 等转义会被自动归一化），据此全库回扫并报出两类候选：

- **值不符**：非动态声明，扫到的数字与当前值不一致；
- **疑似固定值断言**：动态声明，却扫到「共 N」「恰 N」这类把它当固定值的写法。

⚠️ 一律报 **WARN 不报 ERROR**：业务计数的判定有语境依赖（"取值域全集 14 项"是合法留存），
脚本只负责**把候选列全**、把人肉 grep 变成逐条判定；**判定权仍在人**。
表不存在 → 整段跳过，不影响原有三类检查。

## 豁免（显式标记，不硬编码文件名）

    <!-- countclaim-check: ignore -->              该行豁免（写在同一行，行尾即可）
    <!-- countclaim-check: ignore-file 理由 -->     整份文件豁免
    <!-- countclaim-check: ignore-begin 理由 -->    区块开始
    ...
    <!-- countclaim-check: ignore-end -->          区块结束

讲历史的段落（"从 36 条扩到 37 条"）请用行级豁免，**不要**在脚本里加文件名白名单——
硬编码的豁免会随文件改名静默失效，且下一个人根本不知道某文件为什么被放过。

## 用法

    python3 AIDP_HOME/scripts/check_count_claims.py            # 人读报告
    python3 AIDP_HOME/scripts/check_count_claims.py --json     # 机读 JSON

级别 **ERROR**（过期计数会直接改变执行体的行为边界，不是文风问题）。
退出码：0 = 全部计数一致；1 = 检出过期计数；2 = 用法/读取错误。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text
import argparse
import json
import os
import re
import sys

EXCLUDE_DIRS = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv",
    "skills",  # `AIDP_HOME/skills/`：SKILL 本体 + 脚手架 bundle 镜像，由 mirror 脚本同步
}
EXCLUDE_DIR_PREFIXES = (".aidp-backup",)

# ① 核心约定数（口径同 verify.py::check_convention_anchor_consistency 的 decl_re）
CONVENTION_RE = re.compile(
    r"约定\s*1\s*[–—\-]\s*(\d+)"          # 约定 1–N
    r"|核心约定\s*1\s*[–—\-]\s*(\d+)"     # 核心约定 1–N
    r"|(\d+)\s*项核心约定"                 # N 项核心约定
    r"|核心约定\s*(\d+)\s*条"              # 核心约定 N 条
    # ★ 补两类此前抓不到的写法（各让一处过期计数活了很久）：
    r"|(\d+)\+?\s*条核心约定"              # N 条核心约定 / N+ 条核心约定
    #   ——`子Agent必读.md` 曾写「37+ 条核心约定」，因带 `+` 且是「条」在后而全程漏检
    r"|约定\s*1\s*[–—\-]\s*(\d+)\s*为稳定锚点"   # 约定 1–N 为稳定锚点
)
# ② 语义维度数
DIMENSION_RE = re.compile(r"(\d+)\s*个\*{0,2}语义维度")
# ④ 约定 37 机器门校验项数（需与 release_baseline_check 同行共现）
#    真值 = 该脚本 docstring 里 `## 覆盖的 N 项校验` 之下的枚举条目数（`  N. 名称`）。
#    加这一类的直接动因：第 10 项「增量极简度」并入时，脚本自己的 docstring、argparse
#    description、约定 37 主行三处仍写着 9 —— 而 argparse 那处会直接打进 `--help`。
# ★ 两种措辞都要认：文档里既写「N 项确定性校验」也写「N 项机器门」，
#   只认前者会让后者三处过期计数全部逃检（实测漏了 4 处 9→10）。
# ⛔ 必须同时认**两种词序**：`N 项机器门` 与 `机器门 N 项`。
#    实测漏网：commands/version.md 同一文件里 :54 写「12 项机器门」被抓到、
#    :63 写「机器门 11 项」因词序相反而漏掉 —— 守卫自己假绿，正是它要防的形态。
RELEASE_GATE_RE = re.compile(
    r"(?:(\d+)\s*项\s*(?:确定性校验|机器门)|(?:确定性校验|机器门)\s*(\d+)\s*项)")
RELEASE_GATE_CONTEXT = "release_baseline_check"

# ⑤ `设计目标.md` 第三节的目标组数（`aidp-compliance` 维度 4 的**唯一完成判据**是
#    `逐组覆盖：N/N` 这个覆盖率，N 以 `truth_goal_groups()` 现算为准 ——
#    ⛔ 这里**刻意不写死数字**：本脚本只巡检 `.md`，自己的 `.py` 注释逃检，
#    写死就会变成它 docstring 举的那个失效形态「脚本自己的注释还写着旧数字」。
#    数字过期的后果是「打印了 N/N 所以算跑完，实际漏了新增的那一组」，
#    而那正是本脚本 docstring 举的失效形态。此前三类判据都不匹配「N 组目标」，
#    于是新增一个 `G-` 组后两处硬编码同时静默过期、无任何守卫报警。
GOAL_GROUP_RE = re.compile(r"(\d+)\s*组目标|逐组覆盖：\s*(\d+)\s*/\s*(\d+)")
GOAL_CONTEXT = "设计目标"

# ③ 测试分组数（需与 test_guard_scripts 同行共现）
GROUP_RE = re.compile(r"共\s*\*{0,2}(\d+)\s*组")
GROUP_CONTEXT = "test_guard_scripts"

IGNORE_LINE_RE = re.compile(r"<!--\s*countclaim-check:\s*ignore\s*(?:-->|\s)")
IGNORE_FILE_RE = re.compile(r"<!--\s*countclaim-check:\s*ignore-file")
IGNORE_BEGIN_RE = re.compile(r"<!--\s*countclaim-check:\s*ignore-begin")
IGNORE_END_RE = re.compile(r"<!--\s*countclaim-check:\s*ignore-end")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def convention_source(root):
    """「核心约定」正文权威文件。

    模板仓库 = `AIDP_HOME/AIDP-AGENTS.md`（下发记忆源；根 AGENTS.md 只是模板自身维护记忆）；
    下游项目 = AGENTS.md 优先，仅 Claude Code 时 = CLAUDE.md。同 verify.py。
    """
    paradigm = os.path.join(root, runtime_relpath("", __file__), "AIDP-AGENTS.md")
    if os.path.isfile(paradigm):
        return paradigm
    aidp = os.path.join(root, "AGENTS.md")
    if os.path.isfile(aidp):
        return aidp
    inlined = os.path.join(root, "CLAUDE.md")
    if os.path.isfile(inlined):
        t = _read(inlined)
        if t and "## 核心约定" in t:
            return inlined
    return None


def truth_max_convention(root):
    """真值：核心约定正文的最大约定号（`^N. **` 形态）；取不到返回 None。"""
    src = convention_source(root)
    if not src:
        return None
    body = _read(src)
    if not body:
        return None
    nums = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.\s+\*\*", body, re.M)]
    return max(nums) if nums else None


def truth_semantic_dimensions(root):
    """真值：aidp-compliance.md 里 `### … 语义维度 N` 小节数；取不到返回 None。"""
    path = os.path.join(root, runtime_text('__AIDP_HOME__/agents/aidp-compliance.md', __file__))
    body = _read(path)
    if not body:
        return None
    nums = {int(m.group(1))
            for m in re.finditer(r"^#{2,4}\s*.*?语义维度\s*(\d+)", body, re.M)}
    return len(nums) if nums else None


def truth_goal_groups(root):
    """`设计目标.md` 第三节的 `###` 小节数 = 目标组数（现算，不写死）。"""
    p = os.path.join(root, "设计目标.md")
    text = _read(p)
    if text is None:
        return None
    lines = text.split("\n")
    start = end = None
    for i, ln in enumerate(lines):
        if start is None and re.match(r"^##\s*三、", ln):
            start = i
        elif start is not None and re.match(r"^##\s*四、", ln):
            end = i
            break
    if start is None:
        return None
    seg = lines[start + 1:end if end is not None else len(lines)]
    return sum(1 for ln in seg if ln.startswith("### ")) or None


def truth_guard_test_groups(root):
    """真值：test_guard_scripts.py 里 `print("【…】")` 的分组数；取不到返回 None。"""
    path = os.path.join(root, runtime_text('__AIDP_HOME__/scripts/tests/test_guard_scripts.py', __file__))
    body = _read(path)
    if not body:
        return None
    # ★ 两种分组标题形态都要数：早期用 `print("【…】")`，后加的用 `print("\n[NN] …")`。
    #   只数前者会得到 34（实际 61），于是有人如实写「共 61 组」反而被本门判错。
    n = (len(re.findall(r'print\(\s*f?[\'"](?:\\n)?【', body))
         + len(re.findall(r'print\(\s*f?[\'"](?:\\n)?\[\d+\]', body)))
    return n or None


def truth_release_gate_checks(root):
    """真值：release_baseline_check.py docstring 的「## 覆盖的 N 项校验」枚举条目数。"""
    text = _read(os.path.join(root, runtime_text('__AIDP_HOME__/scripts/release_baseline_check.py', __file__)))
    if text is None:
        return None
    m = re.search(r"##\s*覆盖的\s*\d+\s*项校验(.*?)\n\s*##", text, re.S)
    if not m:
        return None
    nums = re.findall(r"^\s{1,3}(\d{1,2})\.\s+\S", m.group(1), re.M)
    return len(nums) or None


# ★ 扫描面必须含 `.py`：类④（约定 37 机器门项数）与类③（测试分组数）加进来的直接动因
#   就是「**脚本自己的 docstring、argparse description** 里还写着旧数字」，而 argparse
#   那处会直接打进 `--help`。此前实现只扫 `.md`，恰好把动因所指的那一类文件排除在外
#   —— 门在跑、恒绿，而它本来要抓的两处过期计数一直躺在 `.py` 里。
SCAN_EXTS = (".md", ".py")


def _walk(base):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames
                       if d not in EXCLUDE_DIRS and not d.startswith(EXCLUDE_DIR_PREFIXES)]
        for fn in sorted(filenames):
            if fn.endswith(SCAN_EXTS):
                yield os.path.join(dirpath, fn)


def scan_line(line, truths, file_ctx=frozenset()):
    """返回本行的过期计数 [(声明原文, 列号, 类别, 声明值, 真值)]。

    `file_ctx` = 本文件**全文**命中的上下文词集合。类③/类④ 原先要求上下文词与计数
    **同行共现**，而这两类的加入动因恰恰是「脚本自己的 docstring / argparse description
    里还写着旧数字」—— 那种写法上下文词通常在几行之外（实测：`test_guard_scripts.py`
    的函数 docstring 写 `9 项机器门`，而带 `release_baseline_check` 的 print 在 9 行之后）。
    于是这两类在最该抓的地方**结构上抓不到**。改为文件级上下文：全文提到该脚本，
    文件内的此类计数就算它的声明。已实测全仓这两个短语无第二种语义，不会引入误判。
    """
    bad = []
    if truths["convention"] is not None:
        for m in CONVENTION_RE.finditer(line):
            decl = next(int(g) for g in m.groups() if g)
            if decl != truths["convention"]:
                bad.append((m.group(0), m.start() + 1, "核心约定数", decl, truths["convention"]))
    if truths["dimension"] is not None:
        for m in DIMENSION_RE.finditer(line):
            decl = int(m.group(1))
            if decl != truths["dimension"]:
                bad.append((m.group(0), m.start() + 1, "语义维度数", decl, truths["dimension"]))
    if truths["group"] is not None and (GROUP_CONTEXT in line or GROUP_CONTEXT in file_ctx):
        for m in GROUP_RE.finditer(line):
            decl = int(m.group(1))
            if decl != truths["group"]:
                bad.append((m.group(0), m.start() + 1, "test_guard_scripts 分组数",
                            decl, truths["group"]))
    if truths.get("goal_group") is not None and (GOAL_CONTEXT in line or GOAL_CONTEXT in file_ctx):
        for m in GOAL_GROUP_RE.finditer(line):
            decl = int(m.group(1) or m.group(3))
            if decl != truths["goal_group"]:
                bad.append((m.group(0), m.start() + 1, "设计目标组数",
                            decl, truths["goal_group"]))
    if truths["release_gate"] is not None and (RELEASE_GATE_CONTEXT in line
                                               or RELEASE_GATE_CONTEXT in file_ctx):
        for m in RELEASE_GATE_RE.finditer(line):
            decl = int(m.group(1) or m.group(2))   # 两种词序各占一个捕获组
            if decl != truths["release_gate"]:
                bad.append((m.group(0), m.start() + 1, "约定37机器门校验项数",
                            decl, truths["release_gate"]))
    return bad


PROJ_TABLE_RE = re.compile(r"^#{2,4}\s*.*业务计数声明表", re.M)
# ⛔ 列匹配必须允许 `\|`（markdown 表格里的转义竖线）：散落面那一列装的是**正则**，
#   正则的 `|` 在表格里只能写成 `\|`，用 `[^|]+?` 匹配会在第一个 `\|` 处截断、
#   拿到半截式子再去 re.compile 必报 "bad escape"（实测第一条声明就这么废掉的）。
_CELL = r"(?:[^|\\]|\\.)*?"
PROJ_ROW_RE = re.compile(
    r"^\|\s*(" + _CELL + r")\s*\|\s*(" + _CELL + r")\s*\|\s*(" + _CELL +
    r")\s*\|\s*(" + _CELL + r")\s*\|\s*(" + _CELL + r")\s*\|")
FIXED_ASSERT_RE = re.compile(r"(?:共|恰|固定|应为|等于)\s*(\d+)\s*(?:项|行|条|个)")


def _load_project_claims(design_dir):
    """从设计文档读「业务计数声明表」。取不到 → 返回空（整段跳过、不猜）。"""
    rows = []
    if not design_dir or not os.path.isdir(design_dir):
        return rows
    for dp, _dn, fns in os.walk(design_dir):
        for fn in sorted(fns):
            if not fn.endswith(".md"):
                continue
            txt = _read(os.path.join(dp, fn)) or ""
            # ★ 必须 finditer：**一份文档里可以有多张**「业务计数声明表」。
            #   上游 `dev-logic-architect` 已把口径从「全设计只准一张表」改为
            #   「多册各一张、增量另起一张」（多册拆分是 M/L 档强制行为，增量按其
            #   「增量/补充生成约定」必落新 `NN_` 文件）。而本项目的 `--ledger-cascade`
            #   是**就地改同一份内容主文档**——多个主题各带一张表落在同一文件，
            #   正是 `search` 只取第一张会漏掉的形态。
            #   漏读**不报错**：那些声明的「散落面正则」从此不参与回扫，表现形式是全绿，
            #   与核心原则 28 自述的失效方式（「不会报错，只会慢慢变成假话」）完全同形。
            for m in PROJ_TABLE_RE.finditer(txt):
                for ln in txt[m.end():].split("\n"):
                    if ln.startswith("#"):
                        break
                    r = PROJ_ROW_RE.match(ln)
                    if not r:
                        continue
                    name, cur, dyn, auth, pat = (x.strip() for x in r.groups())
                    if not name or name in ("声明名", "---") or set(name) <= {"-", ":"}:
                        continue
                    rows.append({"name": name, "current": cur,
                                 "dynamic": ("是" in dyn or "y" in dyn.lower()),
                                 "authority": auth,
                                 # `\|` 是 markdown 表格的转义竖线 → 还原为正则的择一
                                 "pattern": pat.strip("`").replace("\\|", "|")})
    return rows


def scan_project_claims(root, claims):
    """按声明表的散落面回扫全库，列出【候选】供人逐条判定（一律 WARN）。"""
    out = []
    for c in claims:
        if not c["pattern"]:
            continue
        # ★ 兼容 grep BRE 写法：使用者的原痛点就是人肉 `grep -rn`，会自然把 `\|` `\(` `\{`
        #   这类 BRE 转义写进表里，而本脚本用 Python re（ERE 方言）——直接编译必报错。
        #   与其让人踩一次再回来查文档，不如就地归一化。
        _pat = re.sub(r"\\([|(){}+?])", r"\1", c["pattern"])
        try:
            rx = re.compile(_pat)
        except re.error as e:
            out.append({"level": "WARN", "file": "-", "line": 0, "claim": c["name"],
                        "detail": f"散落面 grep 式无法编译（{e}）—— 请修正声明表"})
            continue
        nums = set(re.findall(r"\d+", c["current"]))
        for path in sorted(set(_walk(root))):
            rel = os.path.relpath(path, root)
            txt = _read(path)
            if txt is None:
                continue
            for i, line in enumerate(txt.split("\n"), 1):
                if IGNORE_LINE_RE.search(line) or not rx.search(line):
                    continue
                fa = FIXED_ASSERT_RE.search(line)
                if c["dynamic"] and fa:
                    out.append({"level": "WARN", "file": rel, "line": i, "claim": c["name"],
                                "detail": f"「{c['name']}」已声明为**动态**（当前 {c['current']}），"
                                          f"此处仍写成固定值断言：{line.strip()[:80]}",
                                "hint": "若确属「取值域全集」的合法留存 → 行尾加 "
                                        "`<!-- countclaim-check: ignore -->`"})
                elif not c["dynamic"]:
                    got = set(re.findall(r"\d+", line))
                    if nums and got and not (nums & got):
                        out.append({"level": "WARN", "file": rel, "line": i, "claim": c["name"],
                                    "detail": f"「{c['name']}」权威值 {c['current']}"
                                              f"（出处 {c['authority'] or '未填'}），此处的数字对不上："
                                              f"{line.strip()[:80]}"})
    return out


def run(root, project_claims_dir=None):
    truths = {
        "convention": truth_max_convention(root),
        "dimension": truth_semantic_dimensions(root),
        "group": truth_guard_test_groups(root),
        "goal_group": truth_goal_groups(root),
        "release_gate": truth_release_gate_checks(root),
    }
    violations, scanned, claims = [], 0, 0
    for path in sorted(set(_walk(root))):
        rel = os.path.relpath(path, root)
        text = _read(path)
        if text is None:
            violations.append({"file": rel, "line": 0, "col": 0, "snippet": "",
                               "kind": "读取失败", "declared": None, "actual": None,
                               "detail": "文件读取失败"})
            continue
        # ★ 文件级上下文（类③/类④ 用）：全文提到该脚本名，本文件内的对应计数就算它的声明
        _file_ctx = frozenset(c for c in (GROUP_CONTEXT, RELEASE_GATE_CONTEXT, GOAL_CONTEXT)
                              if c in text)
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
            claims += len(CONVENTION_RE.findall(line)) + len(DIMENSION_RE.findall(line))
            if GROUP_CONTEXT in line or GROUP_CONTEXT in _file_ctx:
                claims += len(GROUP_RE.findall(line))
            for snippet, col, kind, decl, actual in scan_line(line, truths, _file_ctx):
                violations.append({
                    "file": rel, "line": i, "col": col, "snippet": snippet,
                    "kind": kind, "declared": decl, "actual": actual,
                    "detail": f"{kind}声明「{snippet}」，实际 {actual}",
                })
    proj = _load_project_claims(project_claims_dir)
    proj_hits = scan_project_claims(root, proj) if proj else []
    return {"truths": truths, "scanned": scanned, "count_claims": claims,
            "violations": violations,
            "project_claims": len(proj), "project_findings": proj_hits}


def main():
    ap = argparse.ArgumentParser(description="文档自称计数（核心约定数 / 语义维度数 / 测试分组数）与实际一致")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="机读 JSON")
    ap.add_argument("--project-claims", default=None, metavar="设计目录",
                    help="从该目录的「业务计数声明表」读业务计数并全库回扫（一律 WARN）")
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
        res = run(args.root, args.project_claims)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False) if args.json
              else f"[ERROR] 检查执行失败：{e}")
        return 2

    t = res["truths"]
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        base = (f"（巡检 {res['scanned']} 份 .md，命中 {res['count_claims']} 处计数声明；"
                f"真值：核心约定 {t['convention']} / 语义维度 {t['dimension']} / 测试分组 {t['group']}）")
        pf = res.get("project_findings") or []
        if pf:
            print(f"\n── 业务计数回扫（{res.get('project_claims', 0)} 条声明 → {len(pf)} 处候选，"
                  f"⚠️ 一律 WARN、判定权在人）")
            for f in pf:
                loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
                print(f"  [WARN] {loc} — {f['detail']}")
                if f.get("hint"):
                    print(f"         {f['hint']}")
        if not res["violations"]:
            print(f"[OK] 文档自称计数与实际一致{base}")
        else:
            print(f"[FAIL] 检出 {len(res['violations'])} 处过期计数{base}：")
            for v in res["violations"]:
                print(f"  · {v['file']}:{v['line']}:{v['col']}  {v['detail']}")
            print("  修复：把数字改成实际值（真值见上）；确属「讲历史演进」→ 加 "
                  "`<!-- countclaim-check: ignore -->` 豁免。")
    return 1 if res["violations"] else 0


if __name__ == "__main__":
    sys.exit(main())
