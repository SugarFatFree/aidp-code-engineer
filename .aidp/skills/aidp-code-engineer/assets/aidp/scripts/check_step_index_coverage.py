#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_step_index_coverage.py — 命令骨架表 ↔ flow 分片 Step 编号双向覆盖（脚手架契约脚本）。

## 为什么需要本脚本

大命令（`/version` / `/sprint-autopilot` / `/sprint-dev` …）的正文被外置成 `flows/<cmd>/*.md`
多个分片，命令主体只留一张**骨架索引表**告诉执行体「哪些 Step 落在哪一片」，并明确要求
「**按 Step 进度依次 Read 对应分片**」。于是这张表就是执行体**唯一的"该跑哪些步"清单**：

    ⛔ 不在表里的 Step，没有任何理由被执行——哪怕它在分片里定义得再完整。

真实事故（本仓，一次审计抓出）：新增了 `Step 2.7.4`（收口上一版本变更台账）与 `Step 3.3.9.5`
（发布前收口本版本台账，且标着"**必须先于 3.3.10**"），两者都在分片里写好了，**却都没进骨架表**
→ 三个收口点里的两个**定义了但永远不会被执行**；`--finalize-docs` 的「只跑四步 / 跳过其余全部」
清单里 3.3.9.5 **两头都不在**，补跑也无路径。人工每次改 flow 都要回头对表，必漏。

反向同样是错：表里列了而分片里没有 → 执行体按图索骥找不到，属断链。

## 判据（纯集合比对，零主观）

对每个 `commands/<cmd>.md` 与其 `flows/<cmd>/`：

  - **表内编号** = 命令正文表格行首格里的 Step/Phase 编号（`**N.N**` / `Step 0` / `Phase N.N`
    均认；⛔ 粗体不是必要条件——按粗体判会让不用粗体的命令整张表读不进来、结构上恒不可能报错）
  - **分片编号** = `flows/<cmd>/*.md` 里 `^#{2,4} .*(Step|Phase)\\s*N(.N)*` 标题定义的编号
  - `分片有 − 表内无`（且**表里已列举 ≥2 个同级兄弟**）→ **ERROR**（定义了但不会被执行）
  - ⛔ 反向（表内有 − 分片无）**不查**：骨架表登记的 Step 未必外置（部分由命令主体内联承载），
    实测该方向绝大多数是误报。断链方向由 `check_md_anchors.py` 覆盖。

**只对已外置 flow 的命令生效**（`flows/<cmd>/` 存在且有 ≥2 个分片）；未外置的命令正文自包含，
不适用。附属文件（`rationale.md` / `invariants.md` / `usage-guard.md` / `README.md`）不计入。

豁免：分片标题行加 `<!-- stepindex-check: ignore -->`；整文件用 `ignore-file`。

## 用法

    python3 .aidp/scripts/check_step_index_coverage.py [--root <仓库根>] [--json]

退出码：`0`=双向覆盖一致 / `1`=检出缺口 / `2`=用法或读取错误。
"""
import argparse
import json
import os
import re
import sys

ATTACH = {"rationale.md", "invariants.md", "usage-guard.md", "README.md"}
IGNORE_LINE = re.compile(r"<!--\s*stepindex-check:\s*ignore\s*-->")
IGNORE_FILE = re.compile(r"<!--\s*stepindex-check:\s*ignore-file\s*-->")

# 分片标题里的 Step/Phase 编号：`### Step 3.3.9.5：…` / `#### Phase 0B.1.1 …` / `### 2.7.4 …`
HEAD_RE = re.compile(
    r"^#{2,4}\s+(?:★\s*)?(?:Step|Phase)?\s*([0-9]+(?:\.[0-9]+)*(?:[A-Za-z](?:\.[0-9]+)*)?)\s*[：:·\s]",
    re.M)
# 骨架表行首格的粗体编号：`| **2.7.4** |` / `| **Phase 3.2** |` / `| **2.7 / 2.7.3 / 2.7.5** |`
# ★ `**编号**` 之后允许再跟补充说明再到 `|`（实际写法如 `| **0.2**（子步骤 1–4）| … |`）——
#   要求紧跟 `|` 会把这类登记漏读、误报成"未登记"（实测本仓最后 1 处误报即此）。
# ⚠️ 粗体**不是**必要条件：部分命令的骨架表首格写的是 `| Step 0 |`（无 `**`），
#   而原正则强制要求 `**…**` → 它的 9 个 Step 一个都读不进 `in_table` → `listed_parents`
#   恒空 → 该命令**结构上永远报不出缺口**（如 `/sprint-selftest`）。
#   判据本该是「首格是不是一个 Step/Phase 编号」，粗体只是排版偏好。
CELL_RE = re.compile(
    r"^\|\s*(?:\*\*)?(?:Step|Phase)?\s*([0-9][^|*]*)\s*(?:\*\*)?[^|]*\|")
NUM_RE = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:[A-Za-z](?:\.[0-9]+)*)?")
# 区间记法：`2.4.1–2.4.3.5` / `3.3.7.1-3.3.7.5` / `0.1 ~ 0.5`（区间内的编号视为已覆盖）
RANGE_RE = re.compile(r"([0-9][0-9.A-Za-z]*)\s*[–—~-]\s*([0-9][0-9.A-Za-z]*)")


def _key(n):
    """编号 → 可比较元组（2.4.10 > 2.4.9；字母后缀排在同数字之后）。"""
    out = []
    for part in n.split("."):
        m = re.match(r"^([0-9]*)([A-Za-z]*)$", part)
        if not m:
            return tuple(out)
        out.append((int(m.group(1)) if m.group(1) else 0, m.group(2)))
    return tuple(out)


def _read(p):
    try:
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _norm(n):
    """归一化编号：去尾部的点、统一大小写后缀（3.3.9.5 / 0B.1.1 / 2.4.1.5）。"""
    return n.strip().rstrip(".").upper()


def collect(root):
    cmds_dir = os.path.join(root, ".aidp", "commands")
    flows_dir = os.path.join(root, ".aidp", "flows")
    if not (os.path.isdir(cmds_dir) and os.path.isdir(flows_dir)):
        return None
    out = {}
    for name in sorted(os.listdir(flows_dir)):
        fdir = os.path.join(flows_dir, name)
        if not os.path.isdir(fdir):
            continue
        shards = [f for f in sorted(os.listdir(fdir))
                  if f.endswith(".md") and f not in ATTACH]
        if len(shards) < 2:
            continue                      # 未真正外置，跳过
        cmd_md = os.path.join(cmds_dir, f"{name}.md")
        if not os.path.isfile(cmd_md):
            continue

        # ① 分片里定义的编号
        in_shard, shard_of = set(), {}
        for fn in shards:
            text = _read(os.path.join(fdir, fn))
            if IGNORE_FILE.search(text):
                continue
            for line in text.split("\n"):
                if IGNORE_LINE.search(line):
                    continue
                m = HEAD_RE.match(line)
                if m:
                    n = _norm(m.group(1))
                    in_shard.add(n)
                    shard_of.setdefault(n, fn)

        # ② 骨架表里登记的编号（一格可含多个，如 `**2.7 / 2.7.3 / 2.7.5**`）
        #    ★ 还要识别【区间记法】 `**2.4.1–2.4.3.5**`：区间内的编号同样算已覆盖。
        #      不识别会把 2.4.2 / 2.4.3 这类误报成"漏登记"（实测本仓 6/7 处误报皆源于此）。
        in_table, ranges = set(), []
        for line in _read(cmd_md).split("\n"):
            m = CELL_RE.match(line)
            if not m:
                continue
            cell = m.group(1)
            for rm in RANGE_RE.finditer(cell):
                ranges.append((_key(_norm(rm.group(1))), _key(_norm(rm.group(2)))))
            for n in NUM_RE.findall(cell):
                in_table.add(_norm(n))

        out[name] = {"in_shard": in_shard, "in_table": in_table,
                     "ranges": ranges, "shard_of": shard_of}
    return out


def run(root):
    data = collect(root)
    if data is None:
        return {"applicable": False, "reason": "缺 .aidp/commands 或 .aidp/flows，跳过",
                "findings": [], "passed": True}
    findings = []
    for cmd, d in sorted(data.items()):
        # ★ 判据不是"分片里每个 Step 都必须进表"——骨架表本就只列到【分片入口粒度】，
        #   子步由分片内部承载，逐一要求会产生大量噪音（实测 85 处）。
        #   真正的缺陷形态是「**同级兄弟被逐个列举了，却漏掉其中一个**」：
        #   表里有 2.7 / 2.7.3 / 2.7.5 说明 2.7.* 这一层是【按子步列举】的，此时分片里的
        #   2.7.4 不在表内 = 遗漏（真实事故）；而表里只有 2.7、分片有 2.7.1~2.7.9 = 按父级
        #   粒度列举，不算遗漏。
        def _parent(n):
            return n.rsplit(".", 1)[0] if "." in n else ""

        # ★ 只有当某父级下表里【已列举 ≥2 个子步】时，才认定这一层是"按子步登记"的。
        #   仅 1 个不足以说明——那可能只是顺带提了一句；≥2 才是列举模式，此时漏掉中间某个
        #   才构成遗漏。这条约束把噪音从 85 → 30 → 个位数（实测）。
        from collections import Counter
        _pc = Counter(_parent(n) for n in d["in_table"] if _parent(n))
        listed_parents = {k for k, v in _pc.items() if v >= 2}
        missing = sorted(
            (n for n in d["in_shard"] - d["in_table"]
             if _parent(n) in listed_parents
             and not any(lo <= _key(n) <= hi for lo, hi in d["ranges"])),
            key=lambda x: [int(p) if p.isdigit() else p for p in re.split(r"[.]", x)])
        # ⛔ **刻意不做「表有·分片无」反向检查**：骨架表登记的 Step 未必都外置到 flow——
        #   部分 Step 由命令主体自己内联承载（`/sprint-dev` Step 0/0.0/2 即如此），
        #   表格里还可能出现非 Step 的数字（阈值、序号）。实测该方向 22 处命中里绝大多数是
        #   误报，留着只会淹没真信号。断链方向另有 `check_md_anchors.py` 覆盖。
        # ★★ 结构性盲区必须显式报出，不能装作"没发现问题"：
        #   某命令的骨架表里**一个 Step 编号都没有**（`in_table` 为空）时，`listed_parents`
        #   恒为空集 → `missing` 恒为空 → 它在结构上**永远不可能报出任何缺口**。
        #   （该盲区曾由 `CELL_RE` 只认粗体编号造成，现已按「首格是不是 Step/Phase 编号」判，
        #   两个命令的骨架表都已进入比对基准；本分支保留为**结构性兜底**：将来若有命令
        #   真的一个编号都不写，它仍会把"这道门对它无效"这件事显式说出来。）
        #   判 WARN 而非 ERROR：缺骨架表不等于流程有错，但必须让人看见这道门在这里是空的。
        if d["in_shard"] and not d["in_table"]:
            findings.append({
                "level": "WARN", "command": cmd, "step": "-", "kind": "骨架表无编号",
                "detail": f"`/{cmd}` 的命令主体里没有任何「首格为 Step/Phase 编号」的骨架表，"
                          f"而 `flows/{cmd}/` 下定义了 {len(d['in_shard'])} 个 Step 编号 —— "
                          f"本门对该命令**结构上无法报出任何缺口**（比对基准为空）。"
                          f"要么补骨架表，要么在此显式记录该命令不走骨架表索引。",
            })
        dangling = []
        for n in missing:
            findings.append({
                "level": "ERROR", "command": cmd, "step": n, "kind": "分片有·表无",
                "detail": f"`/{cmd}` 的 Step {n} 在 `flows/{cmd}/{d['shard_of'].get(n, '?')}` 里定义了，"
                          f"但**不在骨架索引表里**——而表里【已逐个列举】了它的同级兄弟"
                          f"（{_parent(n)}.* 下的其它子步），说明这一层是按子步登记的、漏了它 = 遗漏。"
                          f"执行体按表推进，不在表里的 Step 没有任何理由被执行（定义了 = 不会跑）",
            })
        for n in dangling:
            findings.append({
                "level": "ERROR", "command": cmd, "step": n, "kind": "表有·分片无",
                "detail": f"`/{cmd}` 的骨架表登记了 Step {n}，但 `flows/{cmd}/` 下无对应标题定义"
                          f" —— 执行体按表去 Read 会找不到（断链）",
            })
    return {"applicable": True, "reason": "",
            "commands": len(data), "findings": findings,
            # ★ WARN（骨架表无编号）不进退出码：它是覆盖面提示，不是流程缺陷
            "passed": not [f for f in findings if f["level"] == "ERROR"]}


def main():
    ap = argparse.ArgumentParser(description="命令骨架表 ↔ flow 分片 Step 编号双向覆盖检查")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--json", action="store_true", help="输出机读 JSON")
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
        print(f"[SKIP] {res['reason']}")
        return 0
    _warns = [f for f in res["findings"] if f["level"] == "WARN"]
    if res["passed"]:
        # ⛔ 别再自称「双向一致」：反向（表有·分片无）是**刻意不做**的（见上方 ⛔ 注释，
        #   误报率高）。声称已覆盖反向，会让读到这行的人以为断链方向也有人管。
        print(f"[OK] 骨架表已登记的 Step 在分片里都能找到（单向：分片有·表无；"
              f"巡检 {res['commands']} 个已外置命令）"
              f"；⚠️ 反向「表有·分片无」刻意不查，见脚本内注释。")
        for f in _warns:
            print(f"  ⚠️ [{f['kind']}] /{f['command']} —— {f['detail']}")
        return 0

    print(f"[FAIL] 检出 {len(res['findings'])} 处骨架表 ↔ 分片编号缺口：")
    for f in res["findings"]:
        print(f"  · [{f['kind']}] /{f['command']} Step {f['step']} —— {f['detail']}")
    print("  修复：分片有·表无 → 把该 Step 补进命令主体骨架表（含它落在哪一片）；"
          "表有·分片无 → 补分片定义或从表中删除。"
          "确属有意（如内部子步不进表）→ 标题行加 `<!-- stepindex-check: ignore -->`。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
