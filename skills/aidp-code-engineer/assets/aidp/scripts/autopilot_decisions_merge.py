#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot_decisions_merge.py — `autopilot_decisions` 双信源合并的**唯一可执行判定**。

## 为什么需要本脚本

`autopilot_decisions` 有两个声明位置：

  · **PRD 头部 YAML frontmatter**：`<prd_root>/<版本>/产品提供/<首份>.md`（**按版本分文件**）
  · **`memory/aidp-config.yaml` 的 `autopilot_decisions:` 段**：兜底位置（**全项目一份、无版本维度**）

两处同名字段值不同时必须有唯一判定：兜底段若长期不更新而 PRD frontmatter 持续更新，
陈旧副本**每轮仍被读进合并**，静默取胜/静默落败时没有人会发现它已经过期。

## 判定（可执行、无歧义）

1. **PRD frontmatter 优先**。同一叶子字段两处都声明且值不同 → **取 PRD 的值**，
   兜底段 的值**丢弃**。依据三条，都是事实而非偏好：
   - **机器读侧只认 PRD**：`autopilot_tick_flags.py` 的 `_prd_deploy_mode` /
     `_prd_deploy_field` / `_cloud_ready_url` 只扫 `产品提供/*.md` 的 frontmatter，
     **全仓没有任何执行体读兜底段**。让兜底段 赢 = 让一个没人读的值去覆盖唯一被读的值。
   - **只有 PRD 有版本维度**：读侧全部是「按本轮目标版本取值」（`_prd_deploy_mode` 的
     版本回落口径），兜底段 表达不了"哪一版"，让它赢就是让上一版的口径污染本版。
   - **写回方向也是 PRD**：命令端收集完决策后写回的是 PRD 目录首份 `.md` 的头部，
     兜底段 只在没有 PRD 落点时兜底 —— 它天然是快照、不是真源。
2. **赢了必须出声**。检出冲突时逐条打印 `⚠️ [decisions-conflict]`（字段路径 / PRD 值 /
   兜底段 值 / 谁生效），**⛔ 不许静默取胜**：静默取胜正是那份陈旧副本能活三个月的原因。
3. **有冲突就给可直接执行的清理建议**。兜底段 存在**且**与 PRD 有冲突字段 → 打印
   冲突/一致/单边三项计数 + 两条可照抄的清理路径（整份 `git rm` / 只删冲突字段），
   `--check` 退出码 1。mtime 还早于 PRD 的另判 `stale-fallback`（同样 1，措辞更重）。
   **只早不冲突 → 只记 INFO、退出码 0**：没冲突说明它还没造成危害，
   报成告警只会变成没人看的噪音。

## 子命令 / 参数

    --version V0.2.0        必填：按哪一版取 PRD（决策字段是版本级的）
    --prd-root <dir>        PRD 大目录（默认 docs/requirements）
    --fallback <file>       兜底 yaml（默认 memory/aidp-config.yaml）
    --get <点号路径>         只打印合并后的某个叶子值（如 deployment.mode），取不到打印空串
    --json                  机读输出（merged / conflicts / stats / verdict / prd_file …）
    --check                 只做冲突与陈旧检测，不打印合并结果

## 退出码

  0 = `--check` 无冲突（含"只旧不冲突"）/ 正常输出（默认）
  1 = `--check` 检出冲突（`conflict` 或 `stale-fallback`）
  2 = 用法错 / PRD 与兜底两处都不存在

## YAML 子集

只解析 `autopilot_decisions` 实际用到的形态：缩进嵌套映射、标量、`- ` 列表
（列表元素可以是标量或单层映射）、`#` 行尾注释、单双引号。⛔ 不实现锚点 / 多行块 /
流式集合——真出现了会被当字符串原样带过，不会静默丢字段。
"""
import argparse
import json
import os
import re
import sys

DEFAULT_PRD_ROOT = os.path.join("docs", "requirements")
# 兜底落点 = 人维护配置 `memory/aidp-config.yaml` 的 `autopilot_decisions:` 段。
# `_unwrap()` 同时认「顶层是 autopilot_decisions:」与「整个文件就是那段映射」两种写法（`--fallback` 显式指定时用）。
DEFAULT_FALLBACK = os.path.join("memory", "aidp-config.yaml")


def resolve_fallback(explicit=None, root="."):
    """兜底文件路径：显式指定 > `memory/aidp-config.yaml`。"""
    if explicit:
        return explicit
    return os.path.join(root, DEFAULT_FALLBACK)


def _declares_decisions(path):
    """该文件里的 `autopilot_decisions` 是否**非空**（空映射 / 缺段都算没声明）。"""
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return False
    try:
        d = parse_yaml_subset(text)
    except Exception:  # noqa: BLE001 — 解析不了就当没声明，回落旧文件（fail 向保守侧）
        return False
    if not isinstance(d, dict):
        return False
    if ROOT_KEY in d:
        # ⛔ 不能走 `_unwrap`：它在 `autopilot_decisions` 不是 dict 时（空映射 `{}` 被
        #    子集解析器读成字符串）会**回退成整份文件**，于是一份只有开关的配置也被
        #    判成「有决策声明」—— 正是本函数要避免的那个静默换空。
        v = d[ROOT_KEY]
        return isinstance(v, dict) and bool(v)
    return bool(d)          # 文件本身就是那段映射（`--fallback` 显式指定的独立文件）
ROOT_KEY = "autopilot_decisions"

_KV_RE = re.compile(r"^(?P<key>[A-Za-z_][\w.-]*)\s*:\s*(?P<val>.*)$")


def _strip_comment(s: str) -> str:
    """去掉行尾 `#` 注释（引号内的 `#` 不算）。"""
    out, q = [], ""
    for ch in s:
        if q:
            out.append(ch)
            if ch == q:
                q = ""
            continue
        if ch in "\"'":
            q = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out).rstrip()


def _scalar(raw: str):
    raw = raw.strip()
    if not raw:
        return ""
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    low = raw.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "~"):
        return None
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.\d+", raw):
        return float(raw)
    return raw


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _parse_block(lines, i: int, min_indent: int):
    """解析一段子块，返回 (值, 下一行下标)。值可能是 dict / list / ""。

    ⛔ 本块的缩进基准 `base` **由第一条非空行现场测出**，不能用 `父缩进+1` 硬凑：
    YAML 的子块缩进量是任意的（2 / 4 空格都合法），硬凑会让所有子行都落进
    `ind > base` 分支被跳过 —— 表现是**整段静默解析成空**，与"文件里本来就没写"同形。
    """
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i >= len(lines) or _indent(lines[i]) < min_indent:
        return "", i
    base = _indent(lines[i])
    if lines[i].lstrip().startswith("- "):
        seq = []
        while i < len(lines):
            ln = lines[i]
            if not ln.strip():
                i += 1
                continue
            ind = _indent(ln)
            if ind < base or not ln.lstrip().startswith("- "):
                break
            body = ln.lstrip()[2:]
            m = _KV_RE.match(body.strip())
            if m and m.group("key"):
                # `- vendor: x` → 该条目是单层映射，后续同缩进的 `  api: y` 并进来
                item = {m.group("key"): _scalar(m.group("val"))}
                item_ind = ind + 2
                i += 1
                while i < len(lines):
                    ln2 = lines[i]
                    if not ln2.strip():
                        i += 1
                        continue
                    if _indent(ln2) < item_ind or ln2.lstrip().startswith("- "):
                        break
                    m2 = _KV_RE.match(ln2.strip())
                    if not m2:
                        break
                    item[m2.group("key")] = _scalar(m2.group("val"))
                    i += 1
                seq.append(item)
            else:
                seq.append(_scalar(body))
                i += 1
        return seq, i
    mp = {}
    while i < len(lines):
        ln = lines[i]
        if not ln.strip():
            i += 1
            continue
        ind = _indent(ln)
        if ind < base:
            break
        if ind > base:            # 不该出现（子块由下面递归吃掉），跳过防死循环
            i += 1
            continue
        m = _KV_RE.match(ln.strip())
        if not m:
            i += 1
            continue
        key, val = m.group("key"), m.group("val").strip()
        if val == "":
            sub, i = _parse_block(lines, i + 1, base + 1)
            mp[key] = sub
        else:
            mp[key] = _scalar(val)
            i += 1
    return mp, i


def parse_yaml_subset(text: str) -> dict:
    lines = [_strip_comment(l.rstrip()) for l in (text or "").splitlines()]
    val, _ = _parse_block(lines, 0, 0)
    return val if isinstance(val, dict) else {}


def _unwrap(d: dict) -> dict:
    """允许两种写法：顶层直接是 `autopilot_decisions:`，或文件本身就是那段映射。"""
    if isinstance(d, dict) and isinstance(d.get(ROOT_KEY), dict):
        return d[ROOT_KEY]
    return d if isinstance(d, dict) else {}


def _frontmatter(text: str) -> str:
    """取 `---` 包围的头部；没有围栏时退化为前 200 行（与命令端扫描口径一致）。"""
    lines = (text or "").splitlines()
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() in ("---", "..."):
                return "\n".join(lines[1:i])
    return "\n".join(lines[:200])


def find_prd_file(prd_root: str, version: str):
    """本版 PRD 目录里**首份**声明了 autopilot_decisions 的 `.md`；没有则返回首份 `.md`。"""
    for sub in ("产品提供", ""):
        d = os.path.join(prd_root, version, sub) if sub else os.path.join(prd_root, version)
        if not os.path.isdir(d):
            continue
        mds = sorted(f for f in os.listdir(d) if f.endswith(".md"))
        first = None
        for fn in mds:
            p = os.path.join(d, fn)
            first = first or p
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    head = _frontmatter(fh.read())
            except OSError:
                continue
            if ROOT_KEY in head:
                return p
        if first:
            return first
    return None


def flatten(node, prefix=""):
    """叶子字典：点号路径 -> 值。列表整体作为一个叶子（逐元素比对噪音大于价值）。"""
    out = {}
    if isinstance(node, dict):
        for k, v in node.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    else:
        out[prefix] = node
    return out


def deep_merge(base: dict, over: dict) -> dict:
    """`over` 覆盖 `base`（同键同为 dict 才递归；其余 over 整体胜出）。"""
    out = dict(base or {})
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def dig_path(node, path: str):
    cur = node
    for seg in path.split("."):
        if not isinstance(cur, dict) or seg not in cur:
            return None
        cur = cur[seg]
    return cur


def resolve(version: str, prd_root: str, fallback: str) -> dict:
    prd_file = find_prd_file(prd_root, version)
    prd_decl, fb_decl = {}, {}
    if prd_file and os.path.isfile(prd_file):
        try:
            with open(prd_file, encoding="utf-8", errors="replace") as fh:
                prd_decl = _unwrap(parse_yaml_subset(_frontmatter(fh.read())))
        except OSError:
            prd_decl = {}
    if os.path.isfile(fallback):
        try:
            with open(fallback, encoding="utf-8", errors="replace") as fh:
                fb_decl = _unwrap(parse_yaml_subset(fh.read()))
        except OSError:
            fb_decl = {}

    # ★ PRD 优先 = PRD 作为 `over` 覆盖兜底。
    merged = deep_merge(fb_decl, prd_decl)

    flat_prd, flat_fb = flatten(prd_decl), flatten(fb_decl)
    conflicts = []
    for path, fbv in sorted(flat_fb.items()):
        if path not in flat_prd:
            continue
        if json.dumps(flat_prd[path], ensure_ascii=False, sort_keys=True) != \
           json.dumps(fbv, ensure_ascii=False, sort_keys=True):
            conflicts.append({"path": path, "prd": flat_prd[path],
                              "fallback": fbv, "winner": "prd"})

    agree = sum(1 for p in flat_fb if p in flat_prd) - len(conflicts)
    stats = {"conflict": len(conflicts), "agree": agree,
             "prd_only": sum(1 for p in flat_prd if p not in flat_fb),
             "fallback_only": sum(1 for p in flat_fb if p not in flat_prd)}

    prd_mtime = os.path.getmtime(prd_file) if prd_file and os.path.isfile(prd_file) else 0.0
    fb_mtime = os.path.getmtime(fallback) if os.path.isfile(fallback) else 0.0
    older = bool(fb_mtime and prd_mtime and fb_mtime < prd_mtime)
    stale_days = int((prd_mtime - fb_mtime) // 86400) if older else 0
    verdict = "ok"
    if os.path.isfile(fallback):
        if conflicts and older:
            verdict = "stale-fallback"
        elif conflicts:
            verdict = "conflict"
        elif older:
            verdict = "older-no-conflict"
    return {
        "version": version, "prd_root": prd_root,
        "prd_file": prd_file if prd_file and os.path.isfile(prd_file) else None,
        "fallback_file": fallback if os.path.isfile(fallback) else None,
        "prd_declared": bool(prd_decl), "fallback_declared": bool(fb_decl),
        "merged": merged, "conflicts": conflicts, "stats": stats,
        "fallback_older_than_prd": older, "stale_days": stale_days,
        "verdict": verdict,
    }


def _report(res: dict) -> None:
    """冲突必须出声（⛔ 静默取胜 = 陈旧副本能活三个月的原因）。"""
    for c in res["conflicts"]:
        sys.stderr.write(
            "⚠️ [decisions-conflict] %s：PRD=%r（生效） / 兜底段=%r（丢弃）\n"
            % (c["path"], c["prd"], c["fallback"]))
    if res["verdict"] in ("stale-fallback", "conflict"):
        st = res["stats"]
        head = ("⛔ [decisions-stale] 兜底副本 %s 比 PRD 旧 %d 天，且"
                % (res["fallback_file"], res["stale_days"])
                if res["verdict"] == "stale-fallback"
                else "⚠️ [decisions-conflict] 兜底副本 %s " % res["fallback_file"])
        sys.stderr.write(
            "%s与 PRD 冲突 %d 处 / 一致 %d 处 / 单边 %d 处 —— 冲突字段一律以 PRD 为准。\n"
            "   清理（二选一，都可直接执行）：\n"
            "     ① 整段清空（PRD 已覆盖全部字段时）：把 %s 的 autopilot_decisions 段改为 {}\n"
            "     ② 只留单边字段：把上面列出的冲突字段从 %s 中删掉，其余保持不动\n"
            % (head, st["conflict"], st["agree"], st["fallback_only"],
               res["fallback_file"], res["fallback_file"]))
    elif res["verdict"] == "older-no-conflict":
        sys.stderr.write(
            "ℹ️ [decisions-info] 兜底副本 %s 比 PRD 旧 %d 天但无冲突字段；"
            "暂无危害，PRD 仍为准\n" % (res["fallback_file"], res["stale_days"]))


def main() -> int:
    ap = argparse.ArgumentParser(description="autopilot_decisions 双信源合并（PRD frontmatter 优先）")
    ap.add_argument("--version", required=True, help="目标版本号，如 V0.2.0")
    ap.add_argument("--prd-root", default=DEFAULT_PRD_ROOT)
    ap.add_argument("--fallback", default=None,
                    help="兜底 yaml；不传 = memory/aidp-config.yaml")
    ap.add_argument("--root", default=".", help="仓库根（默认当前目录）")
    ap.add_argument("--get", default="", help="只打印合并后的某个叶子值（点号路径）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="只做冲突/陈旧检测")
    a = ap.parse_args()

    if not (a.version or "").strip():
        sys.stderr.write("✗ --version 不能为空（决策字段是版本级的）\n")
        return 2
    cwd = os.getcwd()
    try:
        os.chdir(a.root)
    except OSError as e:
        sys.stderr.write("✗ --root 不可进入: %s (%s)\n" % (a.root, e))
        return 2
    try:
        fb = resolve_fallback(a.fallback)     # 已 chdir 进 --root，故用相对路径解析
        res = resolve(a.version.strip(), a.prd_root, fb)
    finally:
        os.chdir(cwd)

    if not res["prd_file"] and not res["fallback_file"]:
        sys.stderr.write("✗ 两处声明位置都不存在：%s/%s/产品提供/ 与 %s\n"
                         % (a.prd_root, a.version, fb))
        return 2

    _report(res)

    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif a.get:
        v = dig_path(res["merged"], a.get)
        print("" if v is None else (v if isinstance(v, str) else
                                    json.dumps(v, ensure_ascii=False)))
    elif not a.check:
        print(json.dumps(res["merged"], ensure_ascii=False, indent=2))

    # ★ 有冲突就该清理 —— `stale-fallback`（旧+冲突）与 `conflict`（新但冲突）同判 1。
    #   ⛔ "只旧不冲突" 仍返回 0：它还没造成危害，报出来只会变成没人看的噪音。
    if a.check and res["verdict"] in ("stale-fallback", "conflict"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
