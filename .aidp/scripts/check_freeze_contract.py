#!/usr/bin/env python3
"""check_freeze_contract.py — 「冻结字段写入契约」棘轮守卫（脚手架契约脚本）。

## 这道门堵的是什么

7×24 无人值守链路靠 `versions.{V}.needs_human=true` 冻结出问题的版本，等条件恢复再自动解冻。
契约（单一信源 = `AIDP_HOME/flows/sprint-aiauto-test/phase-0-6.md`「冻结字段写入契约」）要求
**一次写齐四件**：

    baseline_edit.py --version <V> set needs_human true aiauto_frozen_at @now freeze_reason <枚举>
    baseline_edit.py set aiauto_blocked_reason "frozen:<枚举>@<V>"

缺任何一件的后果都不是「少记一个字段」，而是**这一版永久停摆**：

- 缺 `aiauto_frozen_at` → 解冻判据 `last_deployed_at > frozen_at` / `配置 mtime > frozen_at` 恒假 → 永不解冻。
- 缺 `freeze_reason`   → 落 `unknown` → 既不进环境类复探窗口、也不进配置类 mtime 分支 → 永不解冻。
- 写了枚举外的值     → 同上，且 `case` 分支静默匹配不到，无任何告警。
- 缺顶层 `aiauto_blocked_reason` → autopilot 侧只看到新鲜心跳、误判「测试链路健康」→ 双链路互等。

这些全是**散文里写对了、代码里漏了**就成立的失效，且失效表现是「安静地什么都不发生」——
`/loop` 岁月静好地空转，零告警。项目已为 CLI flag、tick 变量、loop 示例、链式透传都建了棘轮门，
这条自称「缺一即冻死不解冻」的契约此前**唯独没有机器门**，于是实测一次就查出 4 处违约
（含最高频的部署探针超时路径 `probe-timeout` 零写入者）。

## 判据

1. **站点齐备**：每个「置 needs_human 为 true」的站点，其逻辑窗口内必须同时出现
   `aiauto_frozen_at` 与 `freeze_reason`（ERROR）。
2. **取值合法**：`freeze_reason` 的取值必须在契约枚举内（ERROR）。
3. **枚举无幽灵值**：契约里声明的每个枚举值都至少有一个**写入者**（WARN）——
   没有写入者的枚举值是死枚举，读侧的 `case` 分支永远匹配不到。
4. **枚举有解冻路径**：每个枚举值都至少被**读侧**（解冻判定处）提及一次（WARN）。

枚举**不硬编码**，从契约块实时解析——契约改了本脚本自动跟，不产生第二信源。

## 豁免

行内或前一行写 `<!-- freeze-contract: ignore 原因 -->` 即跳过该站点（原因必须写）。
契约定义块自身（写的是 `<枚举>` 占位）自动豁免。

退出码：0 通过（可含 WARN）；1 有 ERROR；2 参数错。
"""
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

# 枚举的唯一信源 = rationale 的权威表（体积豁免，容得下解冻类别与信号；
# 写法示例仍在 phase-0-6.md 的「冻结字段写入契约」注释块里，两者一读一写、不重复。）
ENUM_FILE = "flows/sprint-aiauto-test/rationale.md"
ENUM_MARK = "freeze_reason 枚举（权威定义"
CONTRACT_MARK = "冻结字段写入契约"
# 写法示例块所在文件（唯一允许出现 `<枚举>` 占位而不判违规的地方）
CONTRACT_SPEC_FILE = "flows/sprint-aiauto-test/phase-0-6.md"
# ★ 唯一合法变体：retest-cap 走 needs_human_kind + retest_cap_frozen_at，解冻判据是
#   「人工是否有新提交」，与 freeze_reason 的四类解冻信号都不同构，故不强制它写 freeze_reason。
VARIANT_RE = re.compile(r"needs_human_kind")

SCAN_DIRS = ("flows", "commands")
IGNORE_RE = re.compile(r"<!--\s*freeze-contract:\s*ignore\b")

# 「置 needs_human 为 true」的站点：覆盖 CLI 式（set … needs_human true）与散文式（`needs_human=true`）
# ★ 冻结站点的两种形态都要认：
#   ① 版本级四件套 `set … needs_human true`；
#   ② **顶层前置熔断** `set preflight_frozen_at`（Phase 0.1，TARGET_VERSION 解析之前，
#      冻的是所有版本）。⛔ 只认 ① 时，本仓最上游的那个冻结点整族落在检测面之外 ——
#      它曾因此长期一张 #4 都不发而无人发现（表现 = 挂着跑、通知渠道零消息）。
SET_CLI_RE = re.compile(
    r"\bset\b[^\n]*?\bneeds_human\s+true\b|\bset\b[^\n]*?\bpreflight_frozen_at\b")
# ★ 允许「四件套写在一个 shell 函数里、各站点只调它」这一合法重构：
#   函数体本身就是标准写入者（`$BE … set needs_human true aiauto_frozen_at @now freeze_reason "$1"`），
#   但它写的是 `$1` 而非字面值，逐站点的 `freeze <值> "<原因>"` 又不含 `set`。
#   不认这个形态会二选一地逼人回到「每个站点复制四行」——而那正是本门要防的漏写土壤
#   （复制五遍，漏掉其中一遍的 aiauto_frozen_at 是最容易发生的事）。
#   判据从严：**该文件里确有一个写齐四件套的 freeze() 定义**，其调用站点才算写入者。
FREEZE_FN_DEF_RE = re.compile(
    r"freeze\s*\(\)\s*\{[^}]*?\bset\b[^}]*?\bneeds_human\s+true\b[^}]*?"
    r"\baiauto_frozen_at\b[^}]*?\bfreeze_reason\b", re.S)
FREEZE_FN_CALL_RE = re.compile(r"(?:^|[\s`])freeze\s+([a-z][a-z0-9-]*)\b")
SET_PROSE_RE = re.compile(r"needs_human\s*=\s*true")
# 「发 #4 人工介入卡」的可执行痕迹。⛔ 只认**可执行调用**，不认散文里的「发 #4」——
#   散文说要发与真的发在机器上完全同形，而本门存在的意义正是区分这两者。
# ★ 两种形态都算「停得响」：
#   ① 常规 `--node "#4" --version <V>` —— 发卡 + 登台账；
#   ② **无版本号的前置站点**（跑在选版之前的门）只能 `notify.py` 裸发、**不带 `--node`**
#      —— `notify.py` 对「给了 #N 却缺 --version」是发送前 fail-closed，硬带 `--node`
#      的结果是整张卡一个字节都发不出去，比不登台账坏得多。
#   ③ `--node "#4" --version $VAR` 这类变量化写法（见 phase-0-9 的 $CARD_ID）同样命中。
CARD4_RE = re.compile(r"notify\.py(?:[^\n]*--node\s+[\"\']?#4|(?![^\n]*--node))")
# ★ 第三种合法写入形态：整套处置收敛进 `autopilot_fail_handle.py`（bump→判阈→四件套→#4 一次做完）。
#   ⛔ 不认这个形态的代价不是少报几条，而是**站点整体退出巡检面** —— 迁移过去的冻结点既不再被
#   计入 scanned、也不再为它的 reason 登记写入者，于是本门的 WARN 数会随迁移下降，看起来像
#   「修好了」，实则是「看不见了」（枚举 `chrome-unavailable` 就这样一度被误报成零写入者）。
#   本门的立身之本正是区分「真做了」与「看不见」，自己先失明是不可接受的。
FAIL_HANDLE_RE = re.compile(r"autopilot_fail_handle\.py\b")
FAIL_HANDLE_REASON_RE = re.compile(r"--reason\s+[\"\']?([a-z][a-z0-9-]*)")
# 该形态自带发卡，唯一会「停而不响」的情形是显式 `--no-card`
FAIL_HANDLE_NOCARD_RE = re.compile(r"--no-card\b")

# 读/删/回显/字段说明不算写入站点
# ⚠️ `del` 分支必须收紧到「del 与 needs_human 之间不跨反引号/句读」：
#    原写法 `\bdel\b[^\n]*\bneeds_human\b` 会把**讲解性整行**一并豁免——
#    实测：phase-1.md 里「⛔ 散文的「+1」不是写入：全仓只有 `del`、没有递增 …
#    → 置 `versions.{V}.needs_human=true` …」这一行，因前半句提到 `del`、
#    后半句才是真正的冻结站点，整行被判「非写入」直接跳过 ⇒ 该冻结点长期是散文、
#    机器门却全绿。这正是本门要抓的形态，却被自己的豁免正则放走了。
NOT_A_WRITE_RE = re.compile(r"\bget\s+needs_human\b|\bdel\b[^`。；;\n]*\bneeds_human\b"
                            r"|NEEDS_HUMAN\s*=\s*\$\(|\becho\b|\bjq\b")
# 散文式站点必须带**写入动词**才算真站点。没有这条，「跳过 `needs_human=true` 的版本」
# 「原因 $FREEZE_REASON」这类**读侧/回显侧**描述会被当成写入站点报一片假红——
# 假红常驻的结局是整道门被人忽略，比没有门更糟。
PROSE_WRITE_VERB = re.compile(r"[置写标记]|\bset\b")

FREEZE_REASON_VAL_RE = re.compile(r"freeze_reason[\s=]+[\"'`]?([a-z][a-z0-9-]*)")


def _parse_enum(root):
    """从 rationale 的权威表解析 freeze_reason 全集（不硬编码，避免第二信源）。"""
    p = os.path.join(root, runtime_relpath("", __file__), ENUM_FILE)
    if not os.path.isfile(p):
        return set(), False
    lines = open(p, encoding="utf-8").read().splitlines()
    try:
        start = next(i for i, ln in enumerate(lines) if ENUM_MARK in ln)
    except StopIteration:
        return set(), False
    vals = set()
    for ln in lines[start:]:
        if ln.startswith("## ") and ENUM_MARK not in ln:
            break
        m = re.match(r"^\|\s*`([a-z][a-z0-9-]{3,})`\s*\|", ln)
        if m:
            vals.add(m.group(1))
    return vals, bool(vals)


# ★ #4 判据的**待修清单**（棘轮；**不是豁免**）：登记在此的冻结站点当前只写了字段、没发卡，
#   判 WARN 可见、不阻断；**新出现的站点一律 ERROR**。⛔ 只能变短：补一个 notify 调用就删一条。
#   ⛔ 别往里加新条目——新增冻结点必须当场带 #4，那正是本判据存在的理由。
#   按 (文件, 行号) 记：行号会随编辑漂移，故**比对只用文件名 + 该文件内的待修条数**，
#   漂移不会让条目"假装被修好"，但新增站点会让条数变大 → 落 ERROR。
CARD4_KNOWN_OPEN = ()   # ★ 已归零（2026-09-16 实测 0 违规）
# ⛔ 清空之后再红就是真信号 —— 别再往里加条目。
#   空额度不是无害的：留着就等于给对应文件各发了若干格「新增漏发卡站点只报 WARN」的
#   通行证 —— WARN 数低不代表没问题，只代表看不见。棘轮语义是只能变短，归零即收口。
_CARD4_OPEN_BY_FILE = {}
for _f, _l in CARD4_KNOWN_OPEN:
    _CARD4_OPEN_BY_FILE[_f] = _CARD4_OPEN_BY_FILE.get(_f, 0) + 1


def _logical_window(lines, i):
    """站点的逻辑窗口：本行 + bash 续行 + 同一列表项的后续缩进行（最多 4 行）。"""
    win = [lines[i]]
    j = i
    while j < len(lines) - 1 and lines[j].rstrip().endswith("\\"):
        j += 1
        win.append(lines[j])
    # 散文式：同一 markdown 列表项内的续行（更深缩进、非新列表项）
    base = len(lines[i]) - len(lines[i].lstrip())
    k, taken = j + 1, 0
    while k < len(lines) and taken < 4:
        ln = lines[k]
        if not ln.strip():
            break
        ind = len(ln) - len(ln.lstrip())
        if ind <= base and re.match(r"\s*([-*+]|\d+\.)\s", ln):
            break
        if ind <= base and not ln.startswith((" ", "\t", ">", "#")):
            break
        win.append(ln)
        k += 1
        taken += 1
    return "\n".join(win)


# ⛔ rationale.md 整份豁免：它是「为什么」的载体（与约定 30 同口径），
#    里面必然会逐字引用冻结字段名来解释成因 —— 那不是执行面，不该被当成冻结站点。
EXEMPT_BASENAMES = {"rationale.md"}


def run(root="."):
    enum, enum_ok = _parse_enum(root)
    findings = []
    _card4_seen = {}   # 每文件已命中的 #4 待修条数（棘轮额度）
    if not enum_ok:
        return {"applicable": False, "scanned": 0, "enum": [],
                "findings": [{"level": "ERROR", "file": ENUM_FILE, "line": 0,
                              "detail": "找不到「冻结字段写入契约」块 —— 枚举无从解析，本守卫失去判据"}],
                "passed": False}

    writers, readers, scanned = {}, {}, 0

    # ★ 解冻分支已从 flow 内联下沉到 `AIDP_HOME/scripts/autopilot_unfreeze.py` 的四个集合里，
    #   而 SCAN_DIRS 只有 flows/commands —— 判据 4「每个枚举都有解冻路径」于是**结构上永不触发**：
    #   新增一个谁都不认的枚举，本门照样 0 ERROR / 0 WARN（当前 17 个枚举全覆盖是人工对齐的结果，
    #   不是这道门保证的）。故把该脚本的集合一并算作读侧。
    _unf = os.path.join(root, runtime_relpath("", __file__), "scripts", "autopilot_unfreeze.py")
    if os.path.isfile(_unf):
        try:
            with open(_unf, encoding="utf-8", errors="replace") as f:
                _ulines = f.read().splitlines()
        except OSError:
            _ulines = []
        for i, ln in enumerate(_ulines):
            # 只认集合定义里的字面量，避免把 docstring 里的举例算成"有解冻路径"
            if "_UNFREEZE_BY_" in ln or "_HUMAN_ONLY" in ln or ln.strip().startswith('"'):
                for v in enum:
                    if f'"{v}"' in ln:
                        readers.setdefault(v, []).append(f"'$AIDP_HOME/scripts/autopilot_unfreeze.py:'{i+1}")

    for d in SCAN_DIRS:
        base = os.path.join(root, runtime_relpath("", __file__), d)
        for dirpath, _dn, fns in os.walk(base):
            if "__pycache__" in dirpath:
                continue
            for fn in sorted(fns):
                if not fn.endswith(".md") or fn in EXEMPT_BASENAMES:
                    continue
                fp = os.path.join(dirpath, fn)
                rel = os.path.relpath(fp, os.path.join(root, runtime_relpath("", __file__))).replace(os.sep, "/")
                _text = open(fp, encoding="utf-8").read()
                lines = _text.splitlines()
                # 本文件是否定义了写齐四件套的 freeze() —— 定了才认它的调用站点为写入者
                has_freeze_fn = bool(FREEZE_FN_DEF_RE.search(_text))
                scanned += 1
                # ⛔ 契约定义块的识别必须**限定在写法示例所在文件、且是注释行**：
                #    只按「行内出现『冻结字段写入契约』」判，会把所有**引用**该契约的
                #    真实冻结站点（"按「冻结字段写入契约」写齐 …"正是推荐写法）一并豁免——
                #    守卫全绿、实则漏检整片站点。这个坑由变异测试当场抓出，别再改回去。
                is_spec_file = rel == CONTRACT_SPEC_FILE
                in_contract = False
                for i, ln in enumerate(lines):
                    if is_spec_file and CONTRACT_MARK in ln and ln.lstrip().startswith("#"):
                        in_contract = True
                    elif in_contract and ln.strip() and not ln.lstrip().startswith("#"):
                        in_contract = False
                    # 记录枚举值的读/写两侧
                    if has_freeze_fn:
                        for m in FREEZE_FN_CALL_RE.finditer(ln):
                            v = m.group(1)
                            if v in enum:
                                writers.setdefault(v, []).append(f"{rel}:{i+1}")
                    for m in FREEZE_REASON_VAL_RE.finditer(ln):
                        v = m.group(1)
                        if v not in enum:
                            continue
                        # ⚠️ 写入者判定必须看**逻辑行**：CLI 写法常把 `set …` 与 `freeze_reason <值>`
                        #    拆在 bash 续行上，只看本行会把真写入者误判成读侧、进而误报「零写入者」。
                        j, is_write = i, False
                        while j >= 0:
                            if SET_CLI_RE.search(lines[j]) or SET_PROSE_RE.search(lines[j]):
                                is_write = True
                                break
                            if not lines[j - 1].rstrip().endswith("\\") if j else True:
                                break
                            j -= 1
                        tgt = writers if is_write else readers
                        tgt.setdefault(v, []).append(f"{rel}:{i+1}")
                    for v in enum:
                        if v in ln and v not in FREEZE_REASON_VAL_RE.findall(ln):
                            readers.setdefault(v, []).append(f"{rel}:{i+1}")

                    if in_contract or IGNORE_RE.search(ln):
                        continue
                    if i and IGNORE_RE.search(lines[i - 1]):
                        continue
                    if NOT_A_WRITE_RE.search(ln):
                        continue
                    # ★ 形态三：`autopilot_fail_handle.py` 一次调用做完五步。它的窗口取「本行起
                    #   到反斜杠续行结束」，因为 `--reason` / `--no-card` 常在续行上。
                    if FAIL_HANDLE_RE.search(ln):
                        k, fh = i, [ln]
                        while k < len(lines) - 1 and lines[k].rstrip().endswith("\\"):
                            k += 1
                            fh.append(lines[k])
                        fh_win = "\n".join(fh)
                        scanned_sites = FAIL_HANDLE_REASON_RE.search(fh_win)
                        if scanned_sites:
                            _v = scanned_sites.group(1)
                            if _v in enum:
                                writers.setdefault(_v, []).append(f"{rel}:{i+1}")
                            else:
                                findings.append({
                                    "level": "ERROR", "file": rel, "line": i + 1, "detail":
                                    f"autopilot_fail_handle.py --reason `{_v}` 不在契约枚举内 —— "
                                    f"读侧 case 匹配不到、静默永不解冻。合法值：{'|'.join(sorted(enum))}",
                                })
                        if FAIL_HANDLE_NOCARD_RE.search(fh_win):
                            findings.append({
                                "level": "ERROR", "file": rel, "line": i + 1, "detail":
                                "autopilot_fail_handle.py 带了 `--no-card` —— 冻结「停得住」但「停不响」："
                                "通知渠道零消息，与还在正常跑完全同形。flow 里的失败处置一律不得禁用 #4",
                            })
                        continue

                    is_cli_site = bool(SET_CLI_RE.search(ln))
                    if is_cli_site:
                        pass
                    elif SET_PROSE_RE.search(ln):
                        head = ln[:SET_PROSE_RE.search(ln).start()][-30:]
                        if not PROSE_WRITE_VERB.search(head):
                            continue
                    else:
                        continue

                    win = _logical_window(lines, i)
                    # ★ 顶层前置熔断（Phase 0.1，TARGET_VERSION 解析之前）是**另一族**：
                    #   它记 `preflight_fail_reason` / `preflight_frozen_at`，**不写版本级四件套**
                    #   （那时还没有版本可写）。把它拖进四件套契约是误报。
                    #   但「停得住 ≠ 停得响」对它同样成立 —— 它恰恰是最上游、影响面最大的冻结点，
                    #   故仍要求同窗口发 #4；窗口放宽到 30 行，因为这类站点是「整块 = 一个处置器」，
                    #   `set` 与 `notify.py` 之间常隔十几行解释性注释。
                    #   ⛔ 别为此放宽**全局**窗口：那会让别处的站点蹭到不相干的 notify.py 调用。
                    is_preflight = "preflight_frozen_at" in lines[i]
                    if is_preflight:
                        win = "\n".join(lines[i:i + 30])
                    variant = bool(VARIANT_RE.search(win))
                    miss = []
                    if not is_preflight and "_frozen_at" not in win:
                        miss.append("aiauto_frozen_at")
                    vals = FREEZE_REASON_VAL_RE.findall(win)
                    if not is_preflight and "freeze_reason" not in win and not variant:
                        miss.append("freeze_reason")
                    # ★ 第 4 件套（顶层 `aiauto_blocked_reason`）：此前不在校验面内，
                    #   于是"写了版本级三件、漏了顶层第四件"的站点全程绿灯。后果不是少一个字段：
                    #   开发链路只看到测试链路心跳还在刷 → 判「测试链路健康」→ 走 prerelease 暂缓
                    #   而非熔断 ⇒ 白等十几个 tick 才再冻一次，且冻结原因与真因错位（双链路互等）。
                    #   ⚠️ 只对**测试链路**（aiauto-test）的冻结站点要求——autopilot 侧不写这个键。
                    if (not is_preflight
                            and "aiauto_blocked_reason" not in win
                            and not variant
                            and "sprint-aiauto-test" in rel.replace("\\", "/")):
                        miss.append("aiauto_blocked_reason")
                    if miss:
                        findings.append({
                            "level": "ERROR", "file": rel, "line": i + 1, "detail":
                            f"冻结站点缺 {'/'.join(miss)} —— 按契约，缺 aiauto_frozen_at 则解冻判据恒假、"
                            f"缺 freeze_reason 则落 unknown 不进任何解冻分支，两者都让本版**永久停摆**",
                        })
                    # ★ 第 5 条判据：**冻结必须同时发 #4**。四件套只保证"停得住"，不保证"停得响"——
                    #   字段全写对、通知一条不发时，冻结只存在于 baseline 与本地终端，通知渠道零消息，
                    #   而 #4 是冻结时刻**唯一对外可见的信号**（口径见 sprint-autopilot phase-0-4.md）。
                    #   实测这一类漏发过三处，且此前两道门都抓不到：本脚本只校字段，
                    #   ceremony-gate 的期望卡集不含 #4。判 ERROR —— "停了但没人知道"与"没停"
                    #   在用户那边完全同形，正是本门存在的理由。
                    #   ⛔ 只看**同一逻辑窗口**：卡发在别处等于没发（别的分支可能根本走不到）。
                    # ★ #4 的窗口比四件套宽：通知调用惯例写在四件套之后、`echo` 之前，
                    #   还常隔着 `aiauto_blocked_reason` 与几行注释。用 ±14 行的邻域，
                    #   窄到只看续行必然满屏假红（实测 35 处），而一道恒红的门只会被关掉。
                    #   ⛔ 只对 **CLI 形态**（真能执行的 `set …` 行）判：散文形态的站点本身就不可执行，
                    #     对它要求一个可执行的 card 调用没有意义，只会制造 20+ 条稳定假红。
                    # 前置熔断族窗口放宽到后 30 行（理由同上：整块 = 一个处置器，
                    # `set` 与 `notify.py` 之间隔着十几行解释性注释）
                    card_win = "\n".join(lines[max(0, i - 14): i + (31 if is_preflight else 15)])
                    if is_cli_site and not variant and not CARD4_RE.search(card_win):
                        # 棘轮：该文件的待修额度用完之前算 WARN（可见不阻断），超出即 ERROR（新增站点）
                        _quota = _card4_seen.get(rel, 0)
                        _cap = _CARD4_OPEN_BY_FILE.get(rel, 0)
                        _card4_seen[rel] = _quota + 1
                        _lvl = "WARN" if _quota < _cap else "ERROR"
                        findings.append({
                            "level": _lvl, "file": rel, "line": i + 1, "detail":
                            "冻结站点未在同一窗口发 #4 卡 —— 四件套只保证「停得住」，"
                            "#4 才是「停得响」：不发则冻结只存在于 baseline 与本地终端，"
                            "通知渠道零消息，看起来和还在正常跑一模一样。"
                            "补 `notify.py --node \"#4\" --auto …`；"
                            "确属误报加 `<!-- freeze-contract: ignore 原因 -->`",
                        })
                    for v in vals:
                        if v not in enum:
                            findings.append({
                                "level": "ERROR", "file": rel, "line": i + 1, "detail":
                                f"freeze_reason=`{v}` 不在契约枚举内 —— 读侧 case 匹配不到、静默永不解冻。"
                                f"合法值：{'|'.join(sorted(enum))}",
                            })

    for v in sorted(enum):
        if v not in writers:
            findings.append({
                "level": "WARN", "file": ENUM_FILE, "line": 0, "detail":
                f"枚举值 `{v}` 零写入者 —— 读侧为它保留的解冻分支永远匹配不到，"
                f"要么补上写入站点，要么从契约枚举里删掉",
            })
        if v not in readers:
            findings.append({
                "level": "WARN", "file": ENUM_FILE, "line": 0, "detail":
                f"枚举值 `{v}` 无解冻路径 —— 写得进、出不来，冻结即终态",
            })

    errs = [f for f in findings if f["level"] == "ERROR"]
    return {"applicable": True, "scanned": scanned, "enum": sorted(enum),
            "findings": findings, "passed": not errs}


def main():
    ap = argparse.ArgumentParser(description="「冻结字段写入契约」齐备性 + 枚举合法性检查")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    a = ap.parse_args()
    if a.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(a, "json", False)))
    r = run(a.root)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r["passed"] else 1
    if not r["applicable"]:
        for f in r["findings"]:
            print(f"  [ERROR] {f['file']}: {f['detail']}")
        return 1
    errs = [f for f in r["findings"] if f["level"] == "ERROR"]
    warns = [f for f in r["findings"] if f["level"] == "WARN"]
    for f in errs + warns:
        loc = f"{f['file']}:{f['line']}" if f["line"] else f["file"]
        print(f"  [{f['level']}] {loc} — {f['detail']}")
    print(f"冻结字段写入契约：巡检 {r['scanned']} 份 .md，枚举 {len(r['enum'])} 个"
          f"（{len(errs)} ERROR / {len(warns)} WARN）")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
