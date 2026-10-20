#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跑一个**上游 SKILL 的机器门**，并断言它【真的跑过】——而不只是「没报错」。

## 它堵的是哪个洞

上游 SKILL 的脚本是 vendored 只读的（约定 16），而其中若干条路径长这样：

    什么都没扫到 → print({"passed": true, "skipped": true}) → exit 0

这个输出与「全查过且合格」在**退出码上完全同形**。于是：

- 一个用 `REQ-V0.10-A02` 这类带字母序号的项目，`check_req_upstream.py` 的
  编号正则一条都认不出 ⇒ `total_sections == 0` ⇒ 它打印 `passed:true` 并 exit 0
  ⇒ **上游溯源这道门从接入那天起就没跑过**，且全程零告警；
- 目录名偏了一个字、文档改了标题层级，都会复现同一形态。

改不了被调方，就在**调用方**这一侧判。这是约定 35「采集量自证」的机器那一半：
**「没有可检查的东西」是一个需要人看一眼的结论，不是一个可以静默吞掉的结论。**

## 用法

    python3 {{AIDP_HOME}}/scripts/assert_gate_ran.py \\
        --label "上游溯源(check_req_upstream)" \\
        -- python3 {{AIDP_HOME}}/skills/ux-logic-extractor/scripts/check_req_upstream.py \\
             docs/requirements/V0.1.0 --json

`--` 之后是**原样转发**给被调门的命令行（必须让它输出 JSON）。

退出码：
  `0` = 门真的跑过且自身通过
  `1` = 门自身判不通过（原样透传它的结论）
  `3` = **门没真的跑过**（skipped / 采集量 0）—— ⛔ 这不是通过
  `2` = 用法 / 环境错（命令起不来、输出不是 JSON）

`--allow-empty "<理由>"` 可显式表态「本轮确实没东西可查」：退出码变 0，
但**理由会打印出来留痕**。⛔ 不要拿它当默认开关——那等于把门删掉却留着它的名字。

## ⚠️ 当前接线面：**只 1 处**（`{{AIDP_HOME}}/flows/sprint-requirements/execution-steps.md`，包 `check_req_upstream.py`）

本脚本是通用的「这道门真的跑过了吗」包装器 —— 专治上游门「0 条采集 → passed:true → exit 0」
那种**与真通过同形**的失效。但命令端 / flow 里**裸调**上游 SKILL 脚本的点还有 20+ 个，
目前只有一个被包起来。

**已核实的裸调面（按出现次数）**：`check_money_field.py`(9) · `check_task_granularity.py`(8) ·
`check_semantic_change.py`(2) · `check_prd_item_coverage.py`(2) · `check_di_resolvability.py`(1)
…（完整清单跑 `grep -rhoE "check_[a-z_]+[.]py" .claude/flows .claude/commands | sort | uniq -c`）

**公允补充（⛔ 不要据此一刀切全包上）**：被抽查的上游门多数已各自硬化 ——
`check_prd_item_coverage.py` 与 `check_task_granularity.py` 在无 `.md` 时 `return 2`，
后者还在 `--json` 里给 `scanned_tasks` / `skipped`。真正仍需包的是那些
**「有输入、采集量 0、却仍 return 0」**的门。

**接线判据**：某个裸调点满足「① 该门在采集量 0 时仍 return 0 ② 命令端只读退出码、
不读 `--json` 的 skipped/采集量」两条时，才值得包 —— 逐个核，⛔ 别批量套。
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from aidp_collect import from_external_gate
except ImportError:  # pragma: no cover - 单文件误拷场景
    from_external_gate = None


def _extract_json(text):
    """从 stdout 里取 JSON —— 上游常在 JSON 前后夹杂人读行，故宽松找首个对象。"""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        pass
    i = text.find("{")
    while i >= 0:
        for j in range(len(text), i, -1):
            if text[j - 1] != "}":
                continue
            try:
                obj = json.loads(text[i:j])
            except ValueError:
                continue
            if isinstance(obj, dict):
                return obj
        i = text.find("{", i + 1)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--label", default="上游机器门", help="报告里显示的门名")
    ap.add_argument("--allow-empty", metavar="理由",
                    help="显式表态「本轮确实没东西可查」；理由必填且会留痕")
    ap.add_argument("--count-key", action="append", default=None,
                    help="该门表达采集量的字段名（可多次；缺省用通用字段名穷举）")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出本包装器的判定")
    ap.add_argument("cmd", nargs=argparse.REMAINDER,
                    help="`--` 之后原样转发给被调门的命令行（须让它输出 JSON）")
    a = ap.parse_args()

    cmd = [c for c in a.cmd if c != "--"]
    if not cmd:
        print("❌ 用法错：`--` 之后必须给出被调门的命令行", file=sys.stderr)
        return 2
    if from_external_gate is None:
        print("❌ 环境错：aidp_collect.py 不可导入（本脚本依赖它的外部门适配器）",
              file=sys.stderr)
        return 2

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except OSError as exc:
        print("❌ 环境错：被调门起不来（%s）" % exc, file=sys.stderr)
        return 2

    payload = _extract_json(proc.stdout)
    if payload is None:
        # ⛔ 取不到 JSON 时 **fail-closed**：此刻无法判断它跑没跑，
        #   而「判不出」与「跑过了」之间不能默认取后者。
        print("❌ %s：输出里取不到 JSON，无法判定它是否真的跑过（fail-closed）"
              % a.label, file=sys.stderr)
        if proc.stderr.strip():
            print("   被调门 stderr：%s" % proc.stderr.strip()[:300], file=sys.stderr)
        return 2

    col = from_external_gate(payload, count_keys=a.count_key)
    starved = col.is_starved()
    out = {"label": a.label, "gate_exit_code": proc.returncode,
           "gate_passed": bool(payload.get("passed")),
           "gate_skipped": any(bool(payload.get(k))
                               for k in ("skipped", "skip", "not_run")),
           "collected": col.as_dict() if hasattr(col, "as_dict") else {},
           "ran": not starved}

    if starved:
        if a.allow_empty and a.allow_empty.strip():
            out.update(verdict="allow-empty", allow_empty_reason=a.allow_empty.strip())
            if a.json:
                print(json.dumps(out, ensure_ascii=False, indent=2))
            else:
                print("⚠️ %s：**未实际执行**（采集量 0 / skipped），"
                      "但调用方已显式表态 —— 理由：%s" % (a.label, a.allow_empty.strip()))
            return 0
        out["verdict"] = "not-run"
        if a.json:
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print("⛔ %s：**这道门没有真的跑过** —— 它输出 passed/exit 0，"
                  "但采集量为 0（或自报 skipped）。" % a.label)
            print("   ⛔ 不得据此判「通过」。常见成因：编号 / 命名风格与它的正则对不上、"
                  "目标目录或标题层级偏了。")
            print("   先把被扫对象修到它能认出来；确实不适用则显式 "
                  "`--allow-empty \"<理由>\"` 留痕。")
            print("   被调门原始输出：%s" % json.dumps(payload, ensure_ascii=False)[:300])
        return 3

    out["verdict"] = "ran-and-passed" if proc.returncode == 0 else "ran-and-failed"
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print("%s %s：已实际执行（%s）；门自身结论 exit=%d"
              % ("✅" if proc.returncode == 0 else "❌", a.label,
                 col.describe() if hasattr(col, "describe") else "", proc.returncode))
        if proc.returncode != 0 and proc.stdout.strip():
            print(proc.stdout.strip()[-800:])
    return 0 if proc.returncode == 0 else 1


def _self_check():
    """阳性对照：造三种被调门，确认「跳过」被判 not-run 而不是通过。"""
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    ok = []
    try:
        def gate(name, body):
            p = os.path.join(d, name)
            open(p, "w", encoding="utf-8").write(
                "#!/usr/bin/env python3\nimport json\nprint(json.dumps(%s))\n" % body)
            os.chmod(p, 0o755)
            return p

        me = os.path.abspath(__file__)

        def run(path, extra=()):
            r = subprocess.run([sys.executable, me, "--label", "T", *extra,
                                "--", sys.executable, path],
                               capture_output=True, text=True)
            return r.returncode

        # ★ 核心阳性对照：上游自报 passed+skipped 且 exit 0 → 必须判 not-run(3)
        g1 = gate("skipped.py", '{"passed": True, "skipped": True}')
        ok.append(("★ skipped+passed+exit0 → 判 not-run(3)，⛔ 不算通过", run(g1) == 3))
        ok.append(("★ 同一门加 --allow-empty 显式表态 → 0",
                   run(g1, ("--allow-empty", "本版确实无功规点")) == 0))
        ok.append(("★ --allow-empty 给空理由不生效（仍判 not-run）",
                   run(g1, ("--allow-empty", "   ")) == 3))

        # 采集量 0 但没自报 skipped —— 同样是「没跑」
        g2 = gate("zero.py", '{"passed": True, "total_sections": 0}')
        ok.append(("★ 采集量 0 也判 not-run（没自报 skipped 不代表跑过）", run(g2) == 3))

        # 真的跑过且通过
        g3 = gate("ran.py", '{"passed": True, "total_sections": 12}')
        ok.append(("真跑过且通过 → 0", run(g3) == 0))

        # 真的跑过但不通过 —— 原样透传
        g4 = os.path.join(d, "failed.py")
        open(g4, "w", encoding="utf-8").write(
            "#!/usr/bin/env python3\nimport json,sys\n"
            "print(json.dumps({'passed': False, 'total_sections': 9}))\nsys.exit(1)\n")
        ok.append(("真跑过但判不通过 → 原样透传 1", run(g4) == 1))

        # 输出不是 JSON → fail-closed 2（⛔ 不能默认当跑过了）
        g5 = os.path.join(d, "noisy.py")
        open(g5, "w", encoding="utf-8").write(
            "#!/usr/bin/env python3\nprint('一切正常')\n")
        ok.append(("★ 取不到 JSON → fail-closed(2)，⛔ 不默认当跑过", run(g5) == 2))

        # JSON 夹在人读行之间也要能取到
        g6 = os.path.join(d, "mixed.py")
        open(g6, "w", encoding="utf-8").write(
            "#!/usr/bin/env python3\nimport json\nprint('=== 核验开始 ===')\n"
            "print(json.dumps({'passed': True, 'total_sections': 3}))\nprint('done')\n")
        ok.append(("JSON 夹在人读行之间仍能取到 → 0", run(g6) == 0))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for n, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + n)
    return 0 if all(r for _, r in ok) else 1


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        raise SystemExit(_self_check())
    raise SystemExit(main())
