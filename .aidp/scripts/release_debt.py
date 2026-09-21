#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release_debt.py —— 发布期欠账台账 `docs/audit/{version}/发布欠账.md` 的**唯一读写入口**。

## 为什么要有它

`/version` 的「失败兜底可追溯铁律」要求发布期各步的 WARN 级兜底都登记到台账，
Step 3.6 发布报告要数出未决条数，`--finalize-docs` / `--rebuild-baseline` 要按条勾销。
调用点各写一段 `printf … >> …` 时格式必然分叉，未决条数数不准、补跑后也无字段可勾销；
而只喊话不落账的兜底，在产物上与「这步通过了」完全同形。

## 子命令

    # 登记（幂等：同一 step+title 仍未决 → 只刷新时间戳，不重复堆积；已勾销后再失败 → 新增一条）
    python3 AIDP_HOME/scripts/release_debt.py add --version V0.2.0 --step 3.3.12bis \\
      --title "零残留断言总闸未过" --locate "<文件/章节>" --impact "<后果>" \\
      --redo "check_release_residual_gate.py --version V0.2.0"

    # 勾销（补跑成功后）：按 step（可叠 --title 精确到一条）把未决条目改 ✅ 已补齐（日期）
    python3 AIDP_HOME/scripts/release_debt.py resolve --version V0.2.0 --step 3.3.7.9

    # 列出未决（Step 3.6 顶部欠账块 / 补跑短路开场读它）
    python3 AIDP_HOME/scripts/release_debt.py list --version V0.2.0 --open --json

    # 终态落账门（Step 3.4.1 提交前）：关键产物「存在，或台账里有该步未决条目」，
    # 二者皆无 = 静默跳过 → exit 1；--register-missing 当场补登记后 exit 0
    python3 AIDP_HOME/scripts/release_debt.py gate --version V0.2.0 [--no-tag] [--register-missing]

兼容写法：不带子命令而直接给 `--version --step --title` 视为 `add`。

退出码：0 成功 / 1 gate 发现未落账的跳过 / 2 用法错。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

LEVELS = ("Important", "Critical", "Minor")
OPEN = "⏳ 待处理"
HEAD_RE = re.compile(r"^## \[Step (?P<step>[^\]]+)\] (?P<title>.+?)  —  (?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*$")
STATUS_RE = re.compile(r"^- \*\*状态\*\*：(?P<st>.+?)\s*$")


def debt_path(root, version):
    return os.path.join(root, "docs", "audit", version, "发布欠账.md")


def _now():
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M")


def parse(text):
    """→ [{step, title, ts, status, start, end}]（start/end 为行号区间，end 不含）。"""
    lines = text.split("\n")
    out = []
    for i, ln in enumerate(lines):
        m = HEAD_RE.match(ln)
        if m:
            if out:
                out[-1]["end"] = i
            out.append({"step": m["step"], "title": m["title"], "ts": m["ts"],
                        "status": "", "start": i, "end": len(lines)})
        elif out:
            s = STATUS_RE.match(ln)
            if s and not out[-1]["status"]:
                out[-1]["status"] = s["st"]
    return out


def _is_open(e):
    return not e["status"].startswith("✅")


def _read(p):
    return open(p, encoding="utf-8").read() if os.path.isfile(p) else ""


def add(root, version, step, title, redo="", level="Important", note="", locate="", impact=""):
    """登记一条欠账 → (台账路径, 动作 'added'|'refreshed')。目录不存在即建。"""
    p = debt_path(root, version)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    text = _read(p)
    ts = _now()
    for e in parse(text):
        if e["step"] == step and e["title"] == title and _is_open(e):
            lines = text.split("\n")
            lines[e["start"]] = f"## [Step {step}] {title}  —  {ts}"
            open(p, "w", encoding="utf-8").write("\n".join(lines))
            return p, "refreshed"
    body = [f"## [Step {step}] {title}  —  {ts}",
            f"- **等级**：{level}{'（不硬阻断发布）' if level == 'Important' else ''}"]
    if note:
        body.append(f"- **原因**：{note}")
    if locate:
        body.append(f"- **精确定位**：{locate}")
    if impact:
        body.append(f"- **影响**：{impact}")
    finalize = f"`/version {version} --finalize-docs`"
    body.append(f"- **补跑命令**：`{redo}`；或 {finalize}" if redo else f"- **补跑命令**：{finalize}")
    body.append(f"- **状态**：{OPEN}")
    if not text:
        text = f"# {version}' 发布欠账\n\n> 读写一律经 `python3 $AIDP_HOME/scripts/release_debt.py`。\n'"
    sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    open(p, "w", encoding="utf-8").write(text + sep + "\n".join(body) + "\n")
    return p, "added"


def resolve(root, version, step, title=None):
    """把匹配的未决条目改为 ✅ 已补齐（日期）→ 勾销条数。"""
    p = debt_path(root, version)
    text = _read(p)
    if not text:
        return 0
    lines = text.split("\n")
    n = 0
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    for e in parse(text):
        if e["step"] != step or (title and e["title"] != title) or not _is_open(e):
            continue
        for i in range(e["start"], e["end"]):
            if STATUS_RE.match(lines[i]):
                lines[i] = f"- **状态**：✅ 已补齐（{today}）"
                n += 1
                break
    if n:
        open(p, "w", encoding="utf-8").write("\n".join(lines))
    return n


def list_entries(root, version, only_open=False):
    es = parse(_read(debt_path(root, version)))
    return [{k: e[k] for k in ("step", "title", "ts", "status")} for e in es
            if not only_open or _is_open(e)]


def _nonempty_dir(d):
    return os.path.isdir(d) and any(
        f for _, _, fs in os.walk(d) for f in fs if f not in (".gitkeep",) and not f.startswith("00_索引"))


def gate(root, version, no_tag=False, register_missing=False):
    """终态落账门：每个关键产物要么存在、要么台账有该步未决条目。→ 缺账清单。"""
    dep = os.path.join(root, "docs", "deployment", version)
    checks = [
        ("3.3.7.9", "双轨部署基线全量轨未产出（约定 37）",
         _nonempty_dir(os.path.join(dep, "sql", "全量")) and _nonempty_dir(os.path.join(dep, "配置文件", "全量")),
         f"`/version {version} --rebuild-baseline`"),
    ]
    if not no_tag:
        checks.append(("3.3.11", "全量详细设计未重算",
                       _nonempty_dir(os.path.join(root, "docs", "design", "detail", "全量")),
                       f"`/version {version} --finalize-docs`"))
    open_steps = {e["step"] for e in list_entries(root, version, only_open=True)}
    missing = []
    for step, title, ok, redo in checks:
        if ok or step in open_steps:
            continue
        missing.append({"step": step, "title": title, "redo": redo})
        if register_missing:
            add(root, version, step, title, note="终态落账门发现产物缺失且无对应欠账条目",
                impact="该产物本版缺失", redo=redo.strip("`"))
    return missing


def _self_check():
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    ok = []
    try:
        p, act = add(d, "V0.1.0", "3.3.12bis", "零残留总闸未过", redo="check_x.py")
        t1 = _read(p)
        ok.append(("写出台账且含步骤号与标题", "## [Step 3.3.12bis] 零残留总闸未过" in t1 and act == "added"))
        ok.append(("含补跑指引与状态字段", "--finalize-docs" in t1 and "check_x.py" in t1 and OPEN in t1))
        _, act2 = add(d, "V0.1.0", "3.3.12bis", "零残留总闸未过")
        ok.append(("★ 幂等：同一未决项重复登记只刷新、不堆积",
                   act2 == "refreshed" and _read(p).count("## [Step 3.3.12bis]") == 1))
        add(d, "V0.1.0", "3.3.7", "另一步也失败了")
        ok.append(("不同步骤各留一条", len(list_entries(d, "V0.1.0", only_open=True)) == 2))
        ok.append(("★ resolve 勾销后未决数减一",
                   resolve(d, "V0.1.0", "3.3.7") == 1 and len(list_entries(d, "V0.1.0", True)) == 1))
        _, act3 = add(d, "V0.1.0", "3.3.7", "另一步也失败了")
        ok.append(("已勾销后再失败 → 新增一条", act3 == "added" and len(list_entries(d, "V0.1.0")) == 3))
        miss = gate(d, "V0.1.0")
        ok.append(("★ gate 阳性：全量基线/全量设计缺失且无欠账 → 报缺",
                   {m["step"] for m in miss} == {"3.3.7.9", "3.3.11"}))
        ok.append(("gate --no-tag 不要求全量设计", {m["step"] for m in gate(d, "V0.1.0", no_tag=True)} == {"3.3.7.9"}))
        gate(d, "V0.1.0", register_missing=True)
        ok.append(("gate --register-missing 补登记后再跑为空", gate(d, "V0.1.0") == []))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for n, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + n)
    return 0 if all(r for _, r in ok) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-check" in argv:
        return _self_check()
    if argv and argv[0] not in ("add", "resolve", "list", "gate", "-h", "--help"):
        argv = ["add"] + argv
    ap = argparse.ArgumentParser(description="发布期欠账台账（唯一读写入口）")
    ap.add_argument("--self-check", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    def common(sp):
        sp.add_argument("--root", default=".")
        sp.add_argument("--version", required=True)

    a_add = sub.add_parser("add", help="登记一条欠账（幂等）")
    common(a_add)
    a_add.add_argument("--step", required=True, help="失败发生的步骤号，如 3.3.12bis")
    a_add.add_argument("--title", required=True, help="一句话标题，⛔ 别写「失败了」")
    a_add.add_argument("--redo", default="", help="复现/补跑命令")
    a_add.add_argument("--level", default="Important", choices=LEVELS)
    a_add.add_argument("--note", default="", help="原因")
    a_add.add_argument("--locate", default="", help="精确定位（文件 + 章节/行号/编号）")
    a_add.add_argument("--impact", default="", help="影响")

    a_res = sub.add_parser("resolve", help="补跑成功后勾销")
    common(a_res)
    a_res.add_argument("--step", required=True)
    a_res.add_argument("--title", default=None)

    a_ls = sub.add_parser("list", help="列出条目")
    common(a_ls)
    a_ls.add_argument("--open", action="store_true", help="只列未决")
    a_ls.add_argument("--json", action="store_true")

    a_g = sub.add_parser("gate", help="终态落账门（3.4.1 提交前）")
    common(a_g)
    a_g.add_argument("--no-tag", action="store_true", help="准发布：不要求全量详细设计")
    a_g.add_argument("--register-missing", action="store_true", help="发现缺账当场补登记")
    a_g.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    if not a.cmd:
        ap.print_help()
        return 2
    if a.cmd == "add":
        if not a.title.strip() or not a.step.strip():
            sys.stderr.write("⛔ --step / --title 不得为空\n")
            return 2
        p, act = add(a.root, a.version, a.step, a.title, a.redo, a.level, a.note, a.locate, a.impact)
        print(f"⚠️ 已{'登记' if act == 'added' else '刷新'}发布欠账（Step {a.step}）→ {os.path.relpath(p, a.root)}")
        return 0
    if a.cmd == "resolve":
        n = resolve(a.root, a.version, a.step, a.title)
        print(f"✅ 勾销 {n} 条（Step {a.step}）")
        return 0
    if a.cmd == "list":
        es = list_entries(a.root, a.version, a.open)
        if a.json:
            print(json.dumps({"count": len(es), "entries": es}, ensure_ascii=False, indent=2))
        else:
            print(f"{'未决' if a.open else '全部'}欠账 {len(es)} 条")
            for e in es:
                print(f"  - [Step {e['step']}] {e['title']}（{e['status']}，{e['ts']}）")
        return 0
    miss = gate(a.root, a.version, a.no_tag, a.register_missing)
    if a.json:
        print(json.dumps({"missing": miss, "registered": a.register_missing}, ensure_ascii=False, indent=2))
    else:
        for m in miss:
            print(f"{'⚠️ 已补登记' if a.register_missing else '❌ 未落账'}：Step {m['step']} {m['title']}")
        if not miss:
            print("✅ 终态落账门：关键产物均存在或已登记欠账")
    return 0 if (not miss or a.register_missing) else 1


if __name__ == "__main__":
    sys.exit(main())
