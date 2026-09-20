#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
release_scope.py —— 「本次发布实际覆盖了哪些版本」的确定性计算（版本发布收口用）

## 解决什么

AIDP 允许存在**中间过渡版本**：完成了需求/设计/开发，但**不单独打 tag**，代码随后续某个版本
一并发布（如 V0.11 的产出随 V0.11.1 发布）。

发布收口（`/version` Step 3.3.12）此前只说收口「**本版本**已交付的 Task」，于是过渡版本的任务
**无人认领**——执行体只能停下来问用户"V0.11 的 31 个任务算不算"。
这本是个**确定性可算**的问题，不该靠人判断：

    本次发布覆盖的版本 = (上一个已发布 tag 的版本, 本次发布版本]  ∩  仓库里真实存在的版本目录

其中除本次版本外、且自己没有 tag 的，就是**过渡版本**——它们的任务必须一并收口。

## 用法

    python3 .aidp/scripts/release_scope.py --version V0.11.1 [--root .] [--json]

输出 JSON：
    {
      "released_version": "V0.11.1",
      "prev_released_tag": "V0.10.2" | null,     # 上一个【已打 tag】且低于本次的版本；null=首次发布
      "covered_versions": ["V0.11", "V0.11.1"],  # 本次 tag 实际包含的全部版本（含本次），低→高
      "transitional_versions": ["V0.11"],        # 其中未单独发布的过渡版本（收口易漏的就是这些）
      "known_versions": [...],                   # 仓库里发现的全部版本目录（低→高）
      "released_tags": [...],                    # 仓库里已存在的版本 tag（低→高）
      "reason": "..."
    }

退出码：0=算出结果（含"无过渡版本"这一正常结论）；2=版本号非法或仓库不可读。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# 版本目录/tag 的通用形态：V1 / v0.11 / V0.11.1 / V1.2.3.4（段数不限），可带 `-rc1` 之类后缀
_VER_RE = re.compile(r"^[Vv](\d+(?:\.\d+)*)(.*)$")

# 版本目录会出现在这些位置（取并集——有的版本只有需求没有设计，有的只有计划）
_VERSION_DIRS = ("docs/requirements", "docs/design/detail", "docs/plans", "memory")


def parse_version(name):
    """`V0.11.1` → ((0,11,1), '')；不是版本形态返回 None。

    ⚠️ 段数不同必须可比：`V0.11` vs `V0.11.1` —— 直接比 tuple 即可（(0,11) < (0,11,1)），
    这正是我们要的语义（V0.11 早于 V0.11.1）。⛔ 绝不能按字符串比（'V0.9' > 'V0.11' 会翻车）。
    """
    m = _VER_RE.match((name or "").strip())
    if not m:
        return None
    try:
        nums = tuple(int(x) for x in m.group(1).split("."))
    except ValueError:
        return None
    return nums, (m.group(2) or "")


def _git(root, *args):
    try:
        p = subprocess.run(["git", "-C", str(root), *args],
                           capture_output=True, text=True, timeout=30)
        return p.stdout if p.returncode == 0 else ""
    except (subprocess.SubprocessError, OSError):
        return ""


def released_tags(root):
    """仓库里已存在的版本 tag（去掉非版本形态的），按版本序低→高。"""
    out = []
    for line in _git(root, "tag", "--list").splitlines():
        v = parse_version(line)
        if v:
            out.append((v[0], line.strip()))
    out.sort(key=lambda x: x[0])
    return out


def known_versions(root):
    """扫仓库里真实存在的版本目录（多来源并集，按版本序低→高）。

    并集而非单一目录：过渡版本可能只有需求没有设计（或反过来），只看一处会漏。
    """
    seen = {}
    for rel in _VERSION_DIRS:
        d = Path(root) / rel
        if not d.is_dir():
            continue
        for child in d.iterdir():
            if not child.is_dir():
                continue
            v = parse_version(child.name)
            if v:
                seen.setdefault(v[0], child.name)
    return [seen[k] for k in sorted(seen)]


def compute(root, version):
    v = parse_version(version)
    if not v:
        return None, f"版本号非法（期望 V<数字>[.<数字>…] 形态）：{version!r}"
    cur = v[0]

    tags = released_tags(root)
    tag_keys = {k for k, _ in tags}
    # 上一个【已发布 tag】且严格低于本次版本的最大者
    lower = [(k, n) for k, n in tags if k < cur]
    prev_key, prev_name = (lower[-1] if lower else (None, None))

    all_vers = known_versions(root)
    covered = []
    for name in all_vers:
        k = parse_version(name)[0]
        if k > cur:
            continue                       # 未来版本，不属本次发布
        if prev_key is not None and k <= prev_key:
            continue                       # 上一个 tag 及更早，已随那次发布收口过
        covered.append(name)
    # 本次版本目录可能尚未建（罕见：只发 tag 不留目录）→ 补进覆盖集，避免收口范围里没有它自己
    if version not in covered:
        covered.append(version)
        covered.sort(key=lambda n: parse_version(n)[0])

    # 过渡版本 = 覆盖集里除本次版本外、且自己没有 tag 的
    transitional = [n for n in covered
                    if parse_version(n)[0] != cur and parse_version(n)[0] not in tag_keys]

    if prev_key is None:
        reason = "首次发布（无更早的版本 tag）→ 覆盖全部不高于本次的版本目录"
    else:
        reason = f"覆盖区间 ({prev_name}, {version}]，按版本序取仓库中真实存在的版本目录"
    return {
        "released_version": version,
        "prev_released_tag": prev_name,
        "covered_versions": covered,
        "transitional_versions": transitional,
        "known_versions": all_vers,
        "released_tags": [n for _, n in tags],
        "reason": reason,
    }, None


def main(argv=None):
    ap = argparse.ArgumentParser(description="计算本次发布实际覆盖的版本（含未单独发布的过渡版本）")
    ap.add_argument("--version", required=True, help="本次发布版本号，如 V0.11.1")
    ap.add_argument("--root", default=".", help="仓库根，默认当前目录")
    ap.add_argument("--json", action="store_true", help="只输出 JSON（缺省同时给人读摘要到 stderr）")
    a = ap.parse_args(argv)

    info, err = compute(Path(a.root).resolve(), a.version)
    if err:
        print(json.dumps({"ok": False, "error": err}, ensure_ascii=False))
        return 2
    print(json.dumps(info, ensure_ascii=False))
    if not a.json:
        t = info["transitional_versions"]
        sys.stderr.write(
            f"📦 本次发布 {info['released_version']} 覆盖 {len(info['covered_versions'])} 个版本："
            f"{'、'.join(info['covered_versions'])}\n"
            f"   上一个已发布 tag：{info['prev_released_tag'] or '无（首次发布）'}\n")
        if t:
            sys.stderr.write(
                f"   ⚠️ 其中 {len(t)} 个是**未单独发布的过渡版本**：{'、'.join(t)}\n"
                f"      → 它们的迭代任务【必须一并收口】，否则会永远停在未完成\n")
        else:
            sys.stderr.write("   无过渡版本，收口范围即本版本自身\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
