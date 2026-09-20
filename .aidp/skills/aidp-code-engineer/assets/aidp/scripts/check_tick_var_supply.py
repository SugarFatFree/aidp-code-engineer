#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_tick_var_supply.py — tick 变量「登记了但没有供给链」巡检（脚手架契约脚本）。

## 为什么需要本脚本（一次审计抓出 13 处同形状缺陷）

`autopilot_tick_flags.py` 解决的是「分片间 shell state 不跨 Bash 调用」——变量必须落盘再读回。
但**登记进 `DERIVED_VARS` 只是声明它存在，不等于它真的会被写入**。若一个变量：

  · 全仓没有任何 `tick_flags.py set <NAME>` 落点，且
  · 不在 `BASELINE_FALLBACK`（从 baseline 回落）/ `DYNAMIC_FALLBACK`（动态计算兜底）/
    `DERIVED_FROM`（由其它变量推导）/
    `FALLBACK_DEFAULT`（兜底常量）里，

那么 `--shell` 对它**恒输出空串赋值**。而消费方写的是 `${VAR:-默认}` 或 `[ "$VAR" = "x" ]`——
于是**判据恒取默认、恒为假**，且**没有任何报错**。真实后果（均为实测确认的历史缺陷形态）：

  · `ENTRY_MODE` 恒空 → `[ "$ENTRY_MODE" = "test-only" ]` 恒假 → test-only 分支不可达，
    收尾门按 full 拼期望卡集 → 每 tick FAIL → 3 tick 后冻结版本，且冻结理由与真因无关；
  · `PLANNING_DONE` 恒空 → `${PLANNING_DONE:-0}` 恒 0 → 恒期望 `#1` 卡 → 同上恒 FAIL；
  · `NEXT_SPRINT_NO` 恒空 → `[ -n "$NEXT_SPRINT_NO" ]` 恒假 → 首个 Sprint 关闭后即写
    `next_sprint=done`，**剩余 Sprint 被静默丢弃**。

## 为什么既有守卫抓不到

`check_flow_var_refs.py --strict` 是专为这一形状写的，但它的实现里有一行：

    if TICK_EVAL_RE.search(info["text"]):
        file_allow |= tickvars      # 文件里出现 `--shell` eval → 全部已登记 tick 变量视为已取回

即**「文件里有 eval」被当成「这个变量取得到值」的证明**。而 eval 只对有供给链的变量返回真值。
本脚本补的正是这一格：不看"有没有 eval"，只看"这个变量到底有没有人写"。

## 判据

对 `DERIVED_VARS` 里每个变量：
  - **有供给** = 全仓存在 `tick_flags.py set … <NAME>` / 在 `BASELINE_FALLBACK` / `DERIVED_FROM`
    / `FALLBACK_DEFAULT` / `DYNAMIC_FALLBACK` 之一（五者任一即可）；
  - **有消费** = `.aidp/flows/` 或 `.aidp/commands/` 里出现 `$NAME` / `${NAME` 引用；
  - **无供给 + 有消费 → ERROR**（判据恒取默认值、静默失效）；
  - **无供给 + 无消费 → WARN**（登记了但全仓没人用，属死登记，清理即可）；
  - 有供给 → OK。

豁免：在变量登记行同行或上一行写 `# supply-check: ignore <原因>`（须写原因）。

## 用法

    python3 .aidp/scripts/check_tick_var_supply.py [--root <仓库根>] [--json]

退出码：`0`=全部有供给（或仅 WARN）/ `1`=检出无供给且被消费 / `2`=用法或读取错误。
"""
import argparse
import json
import os
import re
import sys

FLAGS_REL = ".aidp/scripts/autopilot_tick_flags.py"
SCAN_DIRS = [".aidp/flows", ".aidp/commands"]
IGNORE_RE = re.compile(r"#\s*supply-check:\s*ignore")


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _dict_literal_names(text, varname):
    """粗取 `NAME = {...}` 字面量里的顶层字符串键/成员名（够用即可，不做 AST 解析）。

    对 DERIVED_VARS 这类 {command: [names]} 嵌套结构，直接抓所有引号内的大写下划线标识符。
    """
    m = re.search(r"^%s\s*=\s*\{" % re.escape(varname), text, re.M)
    if not m:
        return set()
    i = m.end() - 1
    depth, j = 0, i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    body = text[i:j + 1]
    return set(re.findall(r"['\"]([A-Z][A-Z0-9_]*)['\"]", body))


def _ignored_names(text):
    """带 `# supply-check: ignore` 豁免的变量名（同行）。"""
    out = set()
    for line in text.split("\n"):
        if IGNORE_RE.search(line):
            out |= set(re.findall(r"['\"]([A-Z][A-Z0-9_]*)['\"]", line))
    return out


def _baseline_fallback_keys(text):
    """抽 BASELINE_FALLBACK 里每个变量映射到的 baseline 键：{VAR: (scope, key)}。

    ⚠️ 这是二级校验的基础——一级校验只问「变量名在不在回落表里」，
    答"在"就放行，**从不追问那个 baseline 键到底有没有人写**。
    C-1（deployment_mode 无人写）与 C-2（autopilot_entry_mode 在 test-only 路径无人写）
    两个 Critical 都是在「30 个登记变量均有来源」的全绿之下长期存活的。
    """
    m = re.search(r"BASELINE_FALLBACK\s*[:=][^{]*\{(.*?)\n\}", text, re.S)
    if not m:
        return {}
    out = {}
    for var, scope, key in re.findall(
            r'["\']([A-Z][A-Z0-9_]*)["\']\s*:\s*\(\s*["\']([a-z]+)["\']\s*,\s*["\']([^"\']+)["\']',
            m.group(1)):
        out[var] = (scope, key)
    return out


def run(root):
    flags_path = os.path.join(root, FLAGS_REL)
    text = _read(flags_path)
    if not text:
        return {"applicable": False,
                "reason": f"未找到 {FLAGS_REL}（非 AIDP 项目或脚本缺失），跳过",
                "findings": [], "passed": True}

    declared = _dict_literal_names(text, "DERIVED_VARS")
    if not declared:
        return {"applicable": False, "reason": "DERIVED_VARS 为空或解析不到，跳过",
                "findings": [], "passed": True}

    # ⚠️ `DYNAMIC_FALLBACK` 必须在列：它放的是「要算一下才知道」的动态兜底
    #    （如 `DEPLOY_MODE` ← PRD 解析、`CICD_PIPELINE_BOUND` ← aidp-config.yaml cicd.provider + cicd.pipelines），
    #    是**货真价实的供给方**。漏登记会把这类变量误报成「死登记，建议清理」——
    #    照该建议删掉，正好把真源读法一并删了。
    supplied = (_dict_literal_names(text, "BASELINE_FALLBACK")
                | _dict_literal_names(text, "DERIVED_FROM")
                | _dict_literal_names(text, "FALLBACK_DEFAULT")
                | _dict_literal_names(text, "DYNAMIC_FALLBACK"))
    exempt = _ignored_names(text)

    # 供给来源之三：`cmd_parse` 内直接写 `out["NAME"] = …`（parse 是唯一拿得到原始参数串的地方，
    # 从 $ARGUMENTS 派生的变量只能在这里落盘——不认它会把已修好的变量误报成无供给）
    set_names = set(re.findall(r'out\[\s*["\']([A-Z][A-Z0-9_]*)["\']\s*\]\s*=', text))
    # 供给来源之四：BOOL_FLAGS / VALUE_FLAGS 映射出的变量名（parse 恒为它们赋值）
    for blk in ("BOOL_FLAGS", "VALUE_FLAGS"):
        set_names |= _dict_literal_names(text, blk)

    # 全仓 `tick_flags.py set … NAME` 落点
    consumers = {}
    for rel in SCAN_DIRS:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                p = os.path.join(dirpath, fn)
                body = _read(p)
                if not body:
                    continue
                # ⚠️ 先合并 shell 反斜杠续行再匹配：`set` 与变量名常分处两行
                #   （如 `... --version "$V" \\` / `  set TARGET_VERSION "..." PRE_RELEASE_VERSION "..."`），
                #   行内正则跨不过去 → 把真写入者判成"无人写"。
                body_joined = re.sub(r"\\\s*\n\s*", " ", body)
                for m in re.finditer(r"tick_flags\.py[^\n]*?\bset\b[^\n]*", body_joined):
                    set_names |= set(re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", m.group(0)))
                for name in declared:
                    if re.search(r"\$\{?%s\b" % re.escape(name), body):
                        consumers.setdefault(name, []).append(os.path.relpath(p, root))

    findings = []

    # ── 签名校验：`tick_flags.py set` 只收【单个】 name value ─────────────
    #   ⚠️ 与 `baseline_edit.py set`（支持多对连写）签名不同，极易混写。
    #   写成多对 → argparse `unrecognized arguments` **退出码 2**，该行落盘整个失败；
    #   而分片里这类命令常带 `|| true` 或不校验退出码，于是**静默不落盘**、
    #   下游读回恒空 —— 正是本文件二级校验要堵的那类失效，只不过成因在调用侧。
    for rel in SCAN_DIRS:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if not fn.endswith(".md"):
                    continue
                fp = os.path.join(dirpath, fn)
                body = re.sub(r"\\\s*\n\s*", " ", _read(fp) or "")
                for m in re.finditer(r"autopilot_tick_flags\.py[^\n]*?\bset\b([^\n|;&]*)", body):
                    tail = m.group(1)
                    tail = re.sub(r"--command\s+\S+", "", tail)
                    # ⚠️ 先剥掉【引号包裹的值】再数名字：值里常含 "$SAME_VAR" / "${VAR:-0}"，
                    #   不剥会把「单对」误数成两个名字（实测 WILL_BROWSER_TEST 被数成 2）。
                    tail = re.sub(r'"[^"]*"|\'[^\']*\'', " ", tail)
                    names = []
                    for tok in re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", tail):
                        if tok not in names:
                            names.append(tok)
                    if len(names) > 1:
                        findings.append({
                            "level": "ERROR", "name": names[0], "kind": "set-signature",
                            "consumers": [os.path.relpath(fp, root)],
                            "detail": f"{os.path.relpath(fp, root)}：`tick_flags.py set` 一次只收"
                                      f"**单个** name value，此处连写了 {len(names)} 个（{', '.join(names)}）"
                                      f" —— argparse 会 exit 2、该行整体不落盘。"
                                      f"拆成逐条单对调用（⚠️ 勿套用 `baseline_edit.py set` 的多对写法）",
                        })

    # ── 二级校验：回落链指向的 baseline 键，本身有没有写入者？──────────────
    #   一级校验（下面那个循环）只问「变量名在不在回落表里」。但回落表是**声明**，
    #   声明一个键不等于有人写它。若那个键全仓无写入者，`--shell` 照样恒空，
    #   而一级校验全绿——这正是两个 Critical 的共同形状，故必须补这一档。
    bl_keys = _baseline_fallback_keys(text)
    dyn = _dict_literal_names(text, "DYNAMIC_FALLBACK")
    writer_hay = []
    for rel in list(SCAN_DIRS) + [".aidp/scripts"]:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for fn in filenames:
                if fn.endswith((".md", ".py")):
                    writer_hay.append(_read(os.path.join(dirpath, fn)) or "")
    # ⚠️ 先合并 shell 反斜杠续行：写入常写成
    #     `baseline_edit.py --version "$V" \\`
    #     `  set autopilot_entry_mode "$X" planning_done "$Y"`
    #   不合并的话 `set` 与键名分处两行，行内正则跨不过去 → 把真写入者判成"无人写"（假告警）。
    hay = re.sub(r"\\\s*\n\s*", " ", "\n".join(writer_hay))
    for var, (scope, key) in sorted(bl_keys.items()):
        if var in exempt:
            continue
        leaf = key.split(".")[-1]
        # 写入者形态：baseline_edit set <key> / run-state / jq 赋值 / LockedBaseline 里的键名
        if re.search(r'(set|run-state)[^\n]{0,120}\b%s\b' % re.escape(leaf), hay) \
                or re.search(r'["\']%s["\']\s*[:=]' % re.escape(leaf), hay):
            continue
        if var in dyn:
            continue    # 有动态兜底接管，可接受
        if var in set_names:
            # ⚠️ 已有 `tick_flags set` 写入者 → 本 tick 内供给成立，baseline 回落只是跨 tick 的
            #   冗余安全网，不构成缺陷。**不排除它就会对正确供给的变量报警**（实测：
            #   PRE_RELEASE_VERSION 在 phase-0-6 有 set，却被首版二级校验当成"无人写"）——
            #   而误报是检查被整体关掉的最快途径，比漏报更糟。
            continue
        findings.append({
            "level": "WARN", "name": var, "consumers": [],
            "detail": f"`{var}` 的 BASELINE_FALLBACK 指向 `{scope}:{key}`，"
                      f"但全仓找不到该键的写入者（无 `set {leaf}` / run-state / 字面量赋值），"
                      f"且无 DYNAMIC_FALLBACK 兜底 —— `--shell` 读回恒空，"
                      f"消费方判据恒取默认值且无任何报错（C-1/C-2 同形）",
        })

    for name in sorted(declared):
        if name in exempt:
            continue
        has_supply = (name in supplied) or (name in set_names)
        if has_supply:
            continue
        used = consumers.get(name) or []
        if used:
            findings.append({
                "level": "ERROR", "name": name,
                "detail": f"`{name}` 登记在 DERIVED_VARS，但全仓无 `tick_flags.py set` 落点、"
                          f"也不在 BASELINE_FALLBACK / DERIVED_FROM / FALLBACK_DEFAULT —— "
                          f"`--shell` 读回恒空，消费方判据恒取默认值且无任何报错",
                "consumers": sorted(set(used))[:6],
            })
        else:
            findings.append({
                "level": "WARN", "name": name,
                "detail": f"`{name}` 登记了但全仓既无供给也无消费（死登记），建议清理",
                "consumers": [],
            })

    # ── 三级校验：只有兜底常量、没有任何真源 ────────────────────────────────
    #   ⚠️ 一/二级都把 `FALLBACK_DEFAULT` 当作合法供给，于是「登记了兜底值、却从没有
    #   任何一步真正解析并 `set` 它」这一形态**恒判 OK**。它的失效方式极隐蔽：
    #   `--shell` 每次都吐出兜底值，消费方分支照常求值，**另一个分支结构上永不可达**。
    #   真实样本：`REQUIRES_LOGIN` 兜底为 `"1"`、零 `set` 落点 → `=0` 分支不可达 ⇒
    #   无登录系统在 7×24 下必被 `account-missing` 冻结，而本门当时判 OK。
    fb_only = _dict_literal_names(text, "FALLBACK_DEFAULT")
    for name in sorted(declared):
        if name in exempt or name in set_names:
            continue
        if name not in fb_only:
            continue
        if name in _dict_literal_names(text, "BASELINE_FALLBACK") \
                or name in _dict_literal_names(text, "DERIVED_FROM"):
            continue                      # 还有别的真源，不属本形态
        used = consumers.get(name) or []
        if not used:
            continue
        findings.append({
            "level": "ERROR", "name": name,
            "detail": f"`{name}` **只有 FALLBACK_DEFAULT 兜底、没有任何 `tick_flags.py set` 真源**——"
                      f"`--shell` 恒吐兜底值，消费方的另一个分支结构上永不可达（本门此前把兜底"
                      f"当合法供给，故这类洞恒判 OK）。请补一处真正解析并落盘它的生产者。",
            "consumers": sorted(set(used))[:6],
        })

    errs = [f for f in findings if f["level"] == "ERROR"]
    return {"applicable": True, "reason": "",
            "declared": len(declared), "supplied": len(supplied | set_names),
            "findings": findings, "passed": not errs}


def main():
    ap = argparse.ArgumentParser(description="tick 变量登记 vs 供给链一致性巡检")
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

    errs = [f for f in res["findings"] if f["level"] == "ERROR"]
    warns = [f for f in res["findings"] if f["level"] == "WARN"]
    if not errs:
        extra = f"，{len(warns)} 个死登记（WARN）" if warns else ""
        print(f"[OK] tick 变量供给链齐备：{res['declared']} 个登记变量均有 set/回落/推导来源{extra}。")
        for f in warns:
            print(f"  · [WARN] {f['name']}：{f['detail']}")
        return 0

    sig = [f for f in errs if f.get("kind") == "set-signature"]
    sup = [f for f in errs if f.get("kind") != "set-signature"]
    if sup:
        print(f"[FAIL] {len(sup)} 个 tick 变量【登记了但无供给链】（读回恒空、判据恒取默认、无报错）：")
    if sig:
        print(f"[FAIL] {len(sig)} 处 `tick_flags.py set` 【多对连写】（argparse exit 2 → 该行整体不落盘）：")
    for f in errs:
        print(f"  · {f['name']} —— {f['detail']}")
        if f["consumers"]:
            print(f"      消费方：{'; '.join(f['consumers'])}")
    for f in warns:
        print(f"  · [WARN] {f['name']}：{f['detail']}")
    print("  修复：① 在产生该值的分片补 `tick_flags.py set --command <cmd> <NAME> <值>`；"
          "或 ② 给它加 BASELINE_FALLBACK / DERIVED_FROM / FALLBACK_DEFAULT；"
          "或 ③ 确属无用即从 DERIVED_VARS 删除。确有理由保留 → 登记行加 `# supply-check: ignore <原因>`。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
