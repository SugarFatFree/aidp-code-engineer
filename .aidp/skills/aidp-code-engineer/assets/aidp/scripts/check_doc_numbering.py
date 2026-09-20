#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_doc_numbering.py — 结构性文档的编号连续性 / 唯一性守卫（脚手架契约脚本）。

## 这道门堵的是什么

自动化编辑（切片替换 / 区间改写 / 批量脚本）改结构性内容时，**失败形态是"看起来成功"**：
用「起点索引 → 终点索引」的切片替换某个编号条目，把插在区间内的另外两条条目一并吞掉，
脚本 `assert 锚点==1` 通过、照常打印「成功」——**跨 4 个迭代无人发觉**，直到有人去数编号。

`assert 出现次数 == 1` 只能证明**锚点唯一**，证明不了**被替换掉的正是你以为的那一段**。
唯一能兜住这类事故的是**改完校验结构本身**：编号还连不连续、条目数守不守恒。
本脚本就是那道校验（约定 35「批量替换与切片编辑」第 3 条的机器门）。

## 判据

在**同一个编号组**内（组 = 同文件 + 同结构层级 + 同编号前缀 + 同父编号）：

- **重号**（同一编号出现 ≥2 次）→ **ERROR**。它没有任何正当场景：要么是吞并后残留，
  要么是插入时撞号，两种都是缺陷。
- **跳号**（序列中缺号）→ **WARN**。它**可能是刻意的**——本范式明确允许「已退役的编号不再复用」
  （`设计目标.md` 的 `G-XXX-N` 即如此），故不判 ERROR，只报出来让人扫一眼。

识别三类编号序列：

1. **标题编号**：`## 约定 N` / `### 检查项 N` / `#### Step 3.3.7` / `## IRON-N` / `### 维度 N`
   （前缀词白名单见 `HEADING_PREFIXES`；按「标题层级 + 前缀词 + 父编号」分组）
2. **列表项编号**：行首 `N. ` 的有序列表块（按缩进分组，**连续行块**为一组）
3. **加粗编号条目**：行首 `- **N.M ...**` / `- **①②③ ...**`（约定细则里 31.1 / ①②③ 这类写法）

## 误报控制（精度优先——本脚本一旦误报就会阻塞提交）

- 围栏代码块（``` ~~~）内一律跳过：bash 注释 `# 1. 前置…` 与一级标题同形。
- **全 `1.` 的有序列表是合法 Markdown 自动编号**（渲染器会自己排），整块跳过、不判重号。
- 圈号 / 加粗编号只认**行首**（允许缩进），不扫行内——行内 `① 视觉层 ② 内容层` 是散文枚举，
  同一段里重复出现完全正当。
- 显式豁免：受检行或其上一行写 `<!-- numbering-ignore: 理由 -->`；
  整文件豁免写 `<!-- numbering-ignore-file: 理由 -->`（**理由必填**，留空视为未豁免）。

退出码：0 = 无 ERROR；1 = 有 ERROR；2 = 入参错。`--strict` 下 WARN 也计入退出码 1。
"""
import argparse
import json
import os
import re
import sys

# —— 标题编号前缀词白名单（只认这些，避免把普通中文标题里的数字当编号）——
HEADING_PREFIXES = ("约定", "检查项", "维度", "IRON", "Step", "Phase", "阶段", "步骤", "原则", "情形")

_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# ⚠️ 编号允许带一位字母段（`Phase 0B.1.1` 是本范式的实际写法）；
#    尾部 `(?![\w.])` 不可省——否则 `Phase 0B.00` 会被截成编号 `0`，同一文件里的
#    `0B.*` 全部塌缩成同一个 "0" 而被判重号（实测在 sprint-dev.md / sprint-full.md 上误报过）。
_HEADING_RE = re.compile(
    r"^(?P<hashes>#{2,6})\s*(?:★\s*)?(?P<prefix>" + "|".join(HEADING_PREFIXES) + r")"
    r"[\s\-]*(?P<num>\d+[A-Za-z]?(?:\.\d+)*)(?![\w.])"
)
_OL_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<num>\d+)\.\s+\S")
# ⚠️ 三重限定，逐条都是实测倒逼：① 必须是多级编号（`31.1`）或 `N. ` 形态——裸 `**4 信号定义**`
#    是散文数量词（backend.md 误报过）；② 多级编号后须接非词字符——否则 `**1.3bis**` / `**1.3ter**`
#    会被截成 `1.3` 而互判重号（sprint-autopilot/rationale.md 误报过）；
#    ③ `N.` 后必须跟空白——否则 `1.3bis` 会退化匹配成 `1`。
_BOLD_NUM_RE = re.compile(
    r"^(?P<indent>[ \t]*)[-*]\s+\*\*(?:★\s*)?"
    r"(?P<num>\d+(?:\.\d+)+(?![\w])|\d+(?=\.\s))")
_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"
_BOLD_CIRCLE_RE = re.compile(r"^(?P<indent>[ \t]*)[-*]\s+\*\*(?:★\s*)?(?P<num>[" + _CIRCLED + r"](?:\.\d+)*)")
_IGNORE_LINE_RE = re.compile(r"<!--\s*numbering-ignore:\s*(?P<why>[^>]*?)\s*-->")
_IGNORE_FILE_RE = re.compile(r"<!--\s*numbering-ignore-file:\s*(?P<why>[^>]*?)\s*-->")

SCAN_DIRS = (
    ".aidp/commands", ".aidp/agents", ".aidp/flows",
    ".aidp/reference", ".aidp/rules", ".aidp/templates",
    "docs/init",
)
SCAN_ROOT_FILES = ("设计目标.md", "README.md", "AGENTS.md", "CLAUDE.md", ".aidp/AIDP-AGENTS.md")
# bundle 副本是本体的镜像，同一问题报两遍没有价值
# 叙述型文件：同一编号下从多个角度各写一节是它们的组织方式，标题同号不作数
NARRATIVE_BASENAMES = ("rationale.md", "invariants.md", "README.md", "usage-guard.md")
EXCLUDE_PARTS = ("/skills/aidp-code-engineer/assets/", "/node_modules/", "/__pycache__/")


def _circle_val(ch):
    return _CIRCLED.index(ch) + 1


def _num_key(num):
    """'3.3.7' -> (parent='3.3', last=7)；'①' -> (parent='', last=n)；'⑦.2' -> (parent='⑦', last=2)"""
    parts = num.split(".")
    last = parts[-1]
    if len(parts) == 1 and last and last[0] in _CIRCLED:
        return "", _circle_val(last[0])
    m = re.match(r"\d+", last)          # 'Phase 0B' 这类带字母段的编号取其数字部分
    return ".".join(parts[:-1]), int(m.group(0)) if m else 0


def collect_files(root, explicit_path=None):
    if explicit_path:
        p = explicit_path if os.path.isabs(explicit_path) else os.path.join(root, explicit_path)
        if os.path.isfile(p):
            return [p]
        if not os.path.isdir(p):
            return []
        bases = [p]
    else:
        bases = [os.path.join(root, d) for d in SCAN_DIRS]
    out = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                full = os.path.join(dirpath, fn)
                if any(x in full.replace(os.sep, "/") for x in EXCLUDE_PARTS):
                    continue
                out.append(full)
    if not explicit_path:
        for fn in SCAN_ROOT_FILES:
            p = os.path.join(root, fn)
            if os.path.isfile(p):
                out.append(p)
    return sorted(set(out))


def scan_file(path, root):
    """返回 (groups, exempt_reason)。groups: key -> [(num_str, lineno)]"""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        return None, "read-error: %s" % exc
    head = "\n".join(lines[:40])
    m = _IGNORE_FILE_RE.search(head)
    if m and m.group("why").strip():
        return {}, "file-exempt: " + m.group("why").strip()

    rel = os.path.relpath(path, root)
    groups = {}
    in_fence = False
    ol_block = []           # 当前有序列表连续块 [(indent, num, lineno)]
    ol_serial = 0
    heading_ctx = ""        # 最近一个标题，作分组上下文
    ignored_lines = set()

    def flush_ol():
        """把一个连续有序列表块拆成若干「真列表」再登记。

        ⚠️ 两条拆分规则缺一不可（都由全仓实测倒逼出来）：
          - **按缩进拆**：`8. / 9. / 10.` 顶层项下面嵌着 `1. / 2. / 3.` 子列表，
            不按缩进拆会把两层合成一组，子列表的 1,2,3 直接变成"重号"（误报）；
          - **`1.` 即新列表**：同一缩进下的两个兄弟子列表各自从 1 开始是常态，
            故遇到 `1.` 就切一组。⛔ 但只对 `1.` 生效——其余重复（如 3 后面又来个 3）
            仍判重号，正是本脚本要抓的吞并残留。
        """
        nonlocal ol_block, ol_serial
        by_indent = {}
        for indent, num, ln in ol_block:
            bucket = by_indent.setdefault(indent, [])
            if num == 1 or not bucket:
                bucket.append([])
            bucket[-1].append((num, ln))
        for indent, runs in by_indent.items():
            for ri, run in enumerate(runs):
                if len(run) < 2:
                    continue
                # 全 1. 的自动编号写法是合法 Markdown，整块跳过
                if all(n == 1 for n, _ in run):
                    continue
                key = (rel, "ol#%d.%d" % (ol_serial, ri), indent, "")
                groups[key] = [(str(n), ln) for n, ln in run]
        ol_block = []
        ol_serial += 1

    for i, raw in enumerate(lines, 1):
        if _FENCE_RE.match(raw):
            in_fence = not in_fence
            flush_ol()
            continue
        if in_fence:
            continue
        m = _IGNORE_LINE_RE.search(raw)
        if m and m.group("why").strip():
            ignored_lines.add(i)
            ignored_lines.add(i + 1)

        mh = _HEADING_RE.match(raw)
        if mh:
            flush_ol()
            heading_ctx = "%s|%s" % (len(mh.group("hashes")), mh.group("prefix"))
            parent, _ = _num_key(mh.group("num"))
            key = (rel, "heading", heading_ctx, parent)
            groups.setdefault(key, []).append((mh.group("num"), i))
            continue
        if raw.startswith("#"):
            flush_ol()
            heading_ctx = raw.strip()[:60]
            continue

        mo = _OL_RE.match(raw)
        if mo:
            ol_block.append((mo.group("indent"), int(mo.group("num")), i))
            continue
        if raw.strip() == "":
            continue          # 空行不断开有序列表块（项之间常有空行）
        if ol_block and not raw.startswith((" ", "\t")):
            flush_ol()

        for rx, kind in ((_BOLD_NUM_RE, "bold-num"), (_BOLD_CIRCLE_RE, "bold-circle")):
            mb = rx.match(raw)
            if mb:
                parent, _ = _num_key(mb.group("num"))
                key = (rel, kind, heading_ctx + "|" + mb.group("indent"), parent)
                groups.setdefault(key, []).append((mb.group("num"), i))
                break
    flush_ol()

    for key in list(groups):
        groups[key] = [(n, ln) for n, ln in groups[key] if ln not in ignored_lines]
        if len(groups[key]) < 2:
            del groups[key]
    return groups, None


def analyse(groups):
    """★ 严重度按编号种类分档（口径经全仓实测校准，勿一刀切）：

    - **列表类**（`ol` / `bold-num` / `bold-circle`）：一份清单里出现两个「3.」没有任何正当场景
      —— 要么切片替换吞并后残留、要么插入时撞号 ⇒ **DUP = ERROR**；跳号 ⇒ WARN。
    - **标题类**（`heading`）：本范式里同号标题**确有正当场景**——`## 约定 23` 与
      `## 约定 23 姊妹条`、rationale 里从两个角度各写一节 `## Step 3.4.2` ⇒ **DUP 降为 WARN**；
      且**跳号一律不报**——「已退役的编号不再复用」是本范式的明文规则
      （`rules/code.md` 缺 13 个约定号、`frontend.md` 缺 15 个，全部是刻意的），报出来 100% 是噪音。
    """
    errors, warns = [], []
    for (rel, kind, ctx, parent), items in sorted(groups.items()):
        is_heading = (kind == "heading")
        if is_heading and os.path.basename(rel) in NARRATIVE_BASENAMES:
            continue
        seen = {}
        vals = []
        for num, ln in items:
            _, last = _num_key(num)
            vals.append(last)
            if num in seen:
                rec = {
                    "check": "DUP", "file": rel, "line": ln,
                    "kind": kind, "group": ctx, "number": num,
                    "message": "编号重复：%s 在同一编号组内出现 ≥2 次（首次见第 %d 行）" % (num, seen[num]),
                }
                if is_heading:
                    rec["severity"] = "WARN"
                    rec["message"] += "；标题同号在本范式有正当场景（姊妹条 / 多角度分节），确认非吞并即可"
                    warns.append(rec)
                else:
                    rec["severity"] = "ERROR"
                    errors.append(rec)
            else:
                seen[num] = ln
        if is_heading:
            continue
        uniq = sorted(set(vals))
        if len(uniq) >= 2:
            missing = [v for v in range(uniq[0], uniq[-1] + 1) if v not in set(uniq)]
            if missing:
                warns.append({
                    "check": "GAP", "severity": "WARN", "file": rel,
                    "line": items[0][1], "kind": kind, "group": ctx,
                    "missing": missing,
                    "message": "编号跳号：%s 区间 %d~%d 缺 %s（退役编号属正常，确认非切片替换吞并即可）"
                               % (kind, uniq[0], uniq[-1], ",".join(str(x) for x in missing)),
                })
    return errors, warns


def run(root, path=None):
    files = collect_files(root, path)
    all_groups, exempt, read_errors = {}, [], []
    for f in files:
        g, note = scan_file(f, root)
        if g is None:
            read_errors.append({"file": os.path.relpath(f, root), "message": note})
            continue
        if note:
            exempt.append({"file": os.path.relpath(f, root), "reason": note})
        all_groups.update(g)
    errors, warns = analyse(all_groups)
    return {
        "scanned_files": len(files),
        "groups": len(all_groups),
        "errors": errors,
        "warns": warns,
        "exempt": exempt,
        "read_errors": read_errors,
        "passed": not errors and not read_errors,
    }


def main():
    ap = argparse.ArgumentParser(description="结构性文档编号连续性 / 唯一性校验")
    ap.add_argument("--root", default=".")
    ap.add_argument("--path", help="只扫指定文件或目录（相对 --root）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true", help="WARN 也计入退出码")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效")
    args = ap.parse_args()

    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        return run_self_check(os.path.basename(__file__), json_out=args.json)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("[ERROR] --root 不是目录: %s" % root, file=sys.stderr)
        return 2
    res = run(root, args.path)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for e in res["read_errors"]:
            print("[ERROR] %s: %s" % (e["file"], e["message"]))
        for e in res["errors"]:
            print("[ERROR] %s:%d %s" % (e["file"], e["line"], e["message"]))
        for w in res["warns"]:
            print("[WARN ] %s:%d %s" % (w["file"], w["line"], w["message"]))
        print("扫描 %d 个文件 / %d 个编号组：%d ERROR, %d WARN"
              % (res["scanned_files"], res["groups"], len(res["errors"]), len(res["warns"])))
    if res["errors"] or res["read_errors"]:
        return 1
    if args.strict and res["warns"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
