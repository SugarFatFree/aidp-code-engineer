#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check_chain_unattended.py — 「串联下游必透传 --unattended」的棘轮守卫。

## 为什么是棘轮，不是检测器

规则：**任何命令调起任何"认 `--unattended`"的下游命令时都必须带上该 flag**（有唤醒源时另加 `--no-loop`），
且不写死哪些命令要遵守、也不写死下游清单——写死的清单总会漏掉后来新增的命令。

但**"这一行到底是不是调用"判不了**。同一份文件里这三种写法长得几乎一样：

    - 循环调用 `/sprint-full {NNN}` 执行每个 Sprint          ← 真调用，必须带 flag
    - ❌ 输出"📌 下一步：/sprint-full {NNN+1}"等暗示用户手动调用的话   ← **反例**，带了才荒谬
    - 与 `/sprint-full` 的边界：本命令跑多个 Sprint            ← 边界说明

区分它们要读中文语境。任何正则做检测器都会：要么漏掉真调用（收窄过头），
要么报出几十条描述性引用（放宽过头）—— 而一道从第一天就报几十条红的门，
下游只会把它关掉，那比没有更糟。

**改成棘轮**：把当前**已人工判定为"非调用"**的站点冻进 baseline；此后
① 新出现的候选站点（baseline 里没有）→ **ERROR**，逼作者当场判一次；
② baseline 里的站点若后来补上了 flag → 自动从 baseline 移除（收紧、不回退）。
净效果：存量零噪音，增量一个都跑不掉。

## 判定口径

「候选站点」= 行内出现 `/<命令> <参数>`，且：
  · 该命令**声明了** `--unattended`（扫 `AIDP_HOME/commands/<name>.md` 得到，不写死清单）
  · 不是本文件自己的命令（自指多为用法示例）
  · 参数里带位置占位符（`{version}` / `sprint-{NNN}`）或 `--supplement`（裸 flag 多是参数说明）
  · 该行不含 **`--unattended`**（要 flag 形态、不认裸词——只认裸词时，一句括注
    「★ 不带 `--unattended`」就能让整行免检，措辞即可绕过守卫。刻意不带的分支
    应显式冻进 baseline 并写明理由，而不是靠句子里恰好出现过这个词。）

baseline 按 **(文件, 调用文本, 出现次数)** 记，**不记行号** —— 行号随任何无关编辑漂移，会让 baseline 天天失效。
⛔ **次数不能省**：同一份文件里同形调用常出现多次（`sprint-test.md` 就有两处 `/sprint-close {NNN}`），
只记 (文件, 调用文本) 时，**新增的第 3 处会被既有条目掩盖、报不出来**（实测：加一行后候选 33→34、却全绿）。

用法:
    python3 AIDP_HOME/scripts/check_chain_unattended.py [--root <仓库根>] [--json]
    python3 AIDP_HOME/scripts/check_chain_unattended.py --update-baseline   # 人工判定后重新冻结

退出码: 0 = 无新增；1 = 有新增候选待判定；2 = 用法/环境错。
"""

from __future__ import annotations
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
from pathlib import Path

RUNTIME_REL = runtime_text('__AIDP_HOME__', __file__)
BASELINE = runtime_text('__AIDP_HOME__/scripts/chain-unattended-baseline.txt', __file__)
SCAN_DIRS = ("commands", "flows")
# ⛔ 只跳 `rationale.md`：它承载「为什么/历史事故」，里面的命令行是叙述、不是执行契约。
#    `invariants.md` **不能跳**——它是 autopilot 的顶层执行铁律，是规范性契约正文；
#    整份免检等于给最该守的那份开后门（其中的链式调用既不被检查、也不进 baseline，
#    两头落空）。它里面确有的交互式豁免站点，按本门规矩**显式冻进 baseline**，
#    而不是靠文件名免检——措辞或文件名免检都会让守卫可被绕过。
SKIP_NAMES = {"rationale.md"}

INV_RE = re.compile(
    r"(/(?:sprint-[a-z-]+|version))"
    r"((?:\s+(?:\{[^}\s]+\}|--[a-z-]+(?:=\{?[^\s`]*\}?)?|sprint-\{[^}]+\}|\d{3}"
    r"|[Vv]\d+\.\d+\.\d+|[Ss]print-\d{3}"
    r"|[一-龥]{2,8}))+)")
# 候选判据：该次调用**带了任何参数**即视为真实调用点（而非散文里提命令名）。
# ⛔ 参数形态**必须含中文**：`/version` 串联四个规划子命令的实际落点写的是
#    `/sprint-requirements 全量` / `/sprint-design 增量` —— 中文参数一个都不匹配，
#    于是这四处**连候选都不是**，既不报错也不进 baseline，门报「候选 N」时从未计入它们。
# ⛔ 原先只认 `{占位符}` / `--supplement`，于是 `/sprint-aiauto-test --once`、
#    `/sprint-autopilot --skip-dev` 这类**纯 flag 调用整类**永不进候选：既不报错、
#    也进不了 baseline，守卫报 new=0 是**假绿**——而链路里恰恰大量是这种形态。
# ⛔ 第三类盲区（前两条注释各记过一次，这是第三次）：`/version V0.2.0 --unattended`、
#    `/sprint-close Sprint-003` 这种**裸版本号 / 裸 Sprint 号**参数不进候选。
#    `/version V0.2.0 --unattended` 是最自然的真实写法，漏了就是静默漏检。
ARG_RE = re.compile(r"\{[^}\s]+\}|sprint-\{|--[a-z][a-z-]*|\d{3}"
                    r"|[Vv]\d+\.\d+\.\d+|[Ss]print-\d{3}")


def accepting_commands(root: Path):
    """哪些命令**声明了** `--unattended` —— 扫命令文件得到，⛔ 不写死清单。"""
    out = set()
    d = root / RUNTIME_REL / "commands"
    if not d.is_dir():
        return out
    for p in d.glob("*.md"):
        try:
            if "unattended" in p.read_text(encoding="utf-8"):
                out.add("/" + p.stem)
        except OSError:
            pass
    return out


# ★ 第四类盲区（最难发现的一类）：**裸命令名的委派**。`INV_RE` 的参数组是**必需**的，
#   于是 `才 invoke /sprint-aiauto-test 跑浏览器实测` 这种写法**连候选都不是** ——
#   既不报错、也进不了 baseline，守卫报 `new=0` 属假绿。而它的后果正是本门要防的那条：
#   被委派方「只看本轮信号」⇒ 判出 `LOOP_UNATTENDED=0` ⇒ 在 tick 内退化成交互式挂死。
#   ⇒ 官方 test-only 路由上的 7×24 链会静默退化，而守卫全程绿着。
#
#   判据收窄到「确实是**祈使调用**」，否则会把满仓的 `⛔ 严禁直接 invoke X` 一并卷进来：
#     · 必须紧跟在 `invoke` / `委派` 之后（本仓标记真实调用点的词）；
#     · 同一行出现否定标记（严禁/不得/禁止/绝不/不 invoke/之前/那一刻）即**不是**祈使，跳过。
#   误判方向是"多出一个候选"，可经 baseline 人工冻结、可见；漏判方向才是假绿。
BARE_INV_RE = re.compile(r"(?:invoke|委派)\s*`?(/(?:sprint-[a-z-]+|version))`?(?!\s*`?\s*[-{0-9Vv])")
NEGATION_RE = re.compile(r"严禁|不得|禁止|绝不|不\s*invoke|之前|这一步|那一刻|不在本命令|只是不")


def _owner(p: Path):
    s = p.as_posix()
    if "/commands/" in s:
        return "/" + p.stem
    m = re.search(r"/flows/([^/]+)/", s)
    return "/" + m.group(1) if m else None


def collect(root: Path):
    """返回 [(相对路径, 调用文本, 行号, 整行)]。"""
    accept = accepting_commands(root)
    hits = []
    for d in SCAN_DIRS:
        base = root / RUNTIME_REL / d
        if not base.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x != "__pycache__"]
            for fn in sorted(filenames):
                if not fn.endswith(".md") or fn in SKIP_NAMES:
                    continue
                p = Path(dirpath) / fn
                own = _owner(p)
                try:
                    lines = p.read_text(encoding="utf-8").splitlines()
                except OSError:
                    continue
                actual_rel = p.relative_to(root).as_posix()
                prefix = RUNTIME_REL.rstrip("/") + "/"
                rel = ("{{AIDP_HOME}}/" + actual_rel[len(prefix):]
                       if actual_rel.startswith(prefix) else actual_rel)
                for i, ln in enumerate(lines, 1):
                    for m in INV_RE.finditer(ln):
                        if m.group(1) not in accept or m.group(1) == own:
                            continue
                        # ⛔ 免检判据 = **这次调用自己带了 flag**，不是"整行任意位置出现过"。
                        #    按整行免检会让 `调 /version {V} --from-autopilot（★ 不带 --unattended）`
                        #    这类**括注里提到该词**的行整行豁免——正是设计目标「不靠句子里恰好
                        #    出现过这个词免检」点名要防的形态。
                        #    ★ 但仓内标准写法是 `[--unattended]`（方括号 = 按条件透传），
                        #    而 INV_RE 的参数部分遇 `[` 即止 —— 只看 group(2) 会把**全部合规站点**
                        #    判成未透传（实测 101 处误报，只能靠 --update-baseline 冻掉，
                        #    棘轮自动收紧也因此永不触发）。故补认"调用后**紧邻**的方括号 flag 序列"：
                        #    只匹配紧跟的 `[--xxx]`，中文括注（首字符是 `（`）匹配不上，两头都不放过。
                        _tail = ln[m.end():]
                        # ⛔ 必须容忍「裸 token / [裸 token]」夹在中间：真实写法是
                        #    `/sprint-full {NNN} --from-batch [skip-bugfix] [--unattended]`、
                        #    `/sprint-dev {新NNN} skip-test [--unattended]`。旧正则只认紧邻的
                        #    `[--xxx]`，遇到 `[skip-bugfix]` / 裸 `skip-test` 即断 → 整行被判成
                        #    「非调用」冻进 baseline，日后有人把 [--unattended] 删掉守卫仍报绿，
                        #    正是本门设立要抓的那类回归。中文括注首字符 `（` 仍匹配不上，两头不放过。
                        _opt = re.match(r"\s*(?:\[?-{0,2}[a-z][a-z0-9-]*\]?\s*)+", _tail)
                        _sig = m.group(2) + (_opt.group(0) if _opt else "")
                        if "--unattended" in _sig or "--no-loop" in _sig:
                            continue
                        if not ARG_RE.search(m.group(2)):
                            continue
                        hits.append((rel, " ".join(m.group(0).split()), i, ln.strip()))
                    if NEGATION_RE.search(ln):
                        continue                      # 否定句里的命令名不是调用点
                    for m in BARE_INV_RE.finditer(ln):
                        if m.group(1) not in accept or m.group(1) == own:
                            continue
                        _bopt = re.match(r"\s*(?:\[?-{0,2}[a-z][a-z0-9-]*\]?\s*)+", ln[m.end():])
                        if _bopt and ("--unattended" in _bopt.group(0)
                                      or "--no-loop" in _bopt.group(0)):
                            continue                  # 带了信号（含 `[--no-loop]` 条件透传写法）
                        hits.append((rel, "裸委派 " + m.group(1), i, ln.strip()))
    return hits


def load_baseline(root: Path):
    fp = root / BASELINE
    if not fp.is_file():
        return {}          # ⚠️ dict 不是 set —— 改成按次数棘轮后这里漏改过一次
    out = {}
    for ln in fp.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) >= 3:
            try:
                out[(parts[0], parts[1])] = int(parts[2])
            except ValueError:
                out[(parts[0], parts[1])] = 1
        elif len(parts) == 2:
            out[(parts[0], parts[1])] = 1
    return out


def write_baseline(root: Path, hits):
    fp = root / BASELINE
    fp.parent.mkdir(parents=True, exist_ok=True)   # 目标目录可能不存在（新项目 / 测试沙箱）
    from collections import Counter
    cnt = Counter((h[0], h[1]) for h in hits)
    keys = sorted(cnt)
    body = [
        "# 串联透传棘轮 baseline —— 已人工判定为「不是链式调用」的站点。",
        "# 格式：<相对路径>\\t<调用文本>\\t<出现次数>（⛔ 不记行号：行号随无关编辑漂移；",
        "#   ⛔ 次数不能省：同文件同形调用常出现多次，只记前两列会让新增的那次被掩盖）",
        "#",
        "# 典型的合法条目：给用户看的「后续流程」清单 · 命令边界说明 · 明令禁止输出的反例 ·",
        "#   人工操作指引（「运维跑 …」「手动跑 …」）· 提示词模板。",
        "# ⛔ 新增条目前先确认它**真不是**调用；是调用就去补 `--unattended`，别往这里加。",
        "",
    ]
    body += ["%s\t%s\t%d" % (k[0], k[1], cnt[k]) for k in keys]
    fp.write_text("\n".join(body) + "\n", encoding="utf-8")
    return len(keys)


def main(argv=None):
    ap = argparse.ArgumentParser(description="串联透传 --unattended 的棘轮守卫")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--update-baseline", action="store_true",
                    help="把当前全部候选冻结为 baseline（人工判定完再跑）")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args(argv)
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    root = Path(args.root).resolve()
    if not (root / runtime_relpath("", __file__) / "commands").is_dir():
        sys.stderr.write(runtime_text('未找到 %s/$AIDP_HOME/commands\n', __file__) % root)
        return 2

    hits = collect(root)
    if args.update_baseline:
        n = write_baseline(root, hits)
        print("[OK] baseline 已更新：%d 个已判定站点 → %s" % (n, BASELINE))
        return 0

    base = load_baseline(root)
    from collections import Counter
    cnt = Counter((h[0], h[1]) for h in hits)
    # 超出 baseline 计数的那些次即「新增」——按出现顺序取超出的部分
    seen = Counter()
    new = []
    for h in hits:
        k = (h[0], h[1])
        seen[k] += 1
        if seen[k] > base.get(k, 0):
            new.append(h)
    gone = sorted(k for k in base if cnt.get(k, 0) < base[k])   # 已补 flag / 已删 → 可收紧

    if args.json:
        print(json.dumps({
            "candidates": len(hits), "baseline": len(base),
            "new": [{"file": h[0], "call": h[1], "line": h[2]} for h in new],
            "resolved": [{"file": a, "call": b} for a, b in gone],
        }, ensure_ascii=False, indent=2))
    elif not new:
        msg = "[OK] 串联透传：无新增未透传站点（候选 %d，已判定 %d）" % (len(hits), len(base))
        if gone:
            msg += "；%d 个 baseline 条目已解决，可跑 --update-baseline 收紧" % len(gone)
        print(msg)
    else:
        print("[FAIL] 检出 %d 处**新增**的下游调用候选，未带 `--unattended`：" % len(new))
        for h in new:
            print("  · %s:%d  %s" % (h[0], h[2], h[1]))
            print("      %s" % h[3][:110])
        print("  逐条判一次：**是链式调用** → 补 `[--unattended]`；")
        print("  **只是描述/用户指引/反例** → 跑 `--update-baseline` 冻进 baseline。")
        # ⛔ `gone` 也要在有新增时打印：只在"全绿"分支报，恰好在最该顺手收紧的时刻看不见，
        #    失效条目会一直留在 baseline 里替一个早已不存在的站点挡着。
        if gone:
            print("  ℹ️ 另有 %d 个 baseline 条目已失效（站点已补 flag 或已删除）→ "
                  "同一次 `--update-baseline` 会一并收紧。" % len(gone))

    return 1 if new else 0


if __name__ == "__main__":
    sys.exit(main())
