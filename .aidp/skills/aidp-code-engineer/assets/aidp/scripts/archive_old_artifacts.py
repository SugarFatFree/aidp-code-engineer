#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""archive_old_artifacts.py — 老版本大目录**留仓归档**（跨版本去重 + 打包，豁免最近 N 个版本）。

## 为什么需要

版本化产物目录只增不减：真实项目实测 `docs/reports/` 133MB、`docs/prototype/` 191MB、
`.git` 265MB。这些不进 AI 上下文，但**拖慢一切 glob / grep / clone / status**，
也让"翻翻历史版本"这种动作变得昂贵。

**处置口径（本脚本的硬边界）**：
  - ⛔ **不移出仓库**——归档产物仍在 git 里，只是从散落目录变成一个 zip；
  - **跨版本去重**：内容完全相同（sha256 一致）的文件只保留**最新版本**里的那一份，
    老副本删除并在清单里记明"同 <保留位置>"；
  - **打包**：老版本目录整体压成 `<area>/_archive/<V>.zip`，原目录删除；
  - **豁免最近 N 个版本**（默认 5）——近期版本仍要被频繁读写，绝不动。

## 安全设计（这是会删文件的脚本，默认什么都不做）

  1. **默认 dry-run**：只打印计划，必须显式 `--apply` 才执行；
  2. **脏工作区拒绝执行**：归档范围内有未提交改动 → 直接退出，不给"改了一半被打包"的机会；
  3. **先打包、再删原目录**：zip 写成功且能完整列出条目才 `rm`，中途失败原目录仍在；
  4. **留痕**：每个 area 生成 `_archive/00_归档说明.md`，记录每个 zip 的来源/文件数/原始体积/
     去重删掉了哪些（含"同哪一份"），事后可完整还原认知；
  5. **可还原**：`restore --version V` 把 zip 解回原位（去重删掉的文件按清单从保留位置补回）。

用法：
    python3 .aidp/scripts/archive_old_artifacts.py plan                    # 看计划（默认）
    python3 .aidp/scripts/archive_old_artifacts.py plan --keep 8 --area docs/reports
    python3 .aidp/scripts/archive_old_artifacts.py apply --apply           # 真正执行
    python3 .aidp/scripts/archive_old_artifacts.py restore --version V0.6 --area docs/reports --apply

退出码：0 正常；1 前置不满足（脏工作区 / 无可归档版本）；2 用法错。
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime, timezone

DEFAULT_AREAS = ("docs/reports", "docs/prototype", "docs/testing")
DEFAULT_KEEP = 5
ARCHIVE_DIRNAME = "_archive"
NOTE_NAME = "00_归档说明.md"
MANIFEST_NAME = "_manifest.json"
RE_VERSION_DIR = re.compile(r"^V\d+(?:\.\d+)*$")


def _now():
    return datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _semver_key(v):
    nums = [int(x) for x in re.findall(r"\d+", v)]
    return nums + [0] * (4 - len(nums))


def _sha(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _du(path):
    tot = 0
    for dp, _dn, fns in os.walk(path):
        for fn in fns:
            try:
                tot += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return tot


def _mb(n):
    return f"{n / 1048576:.1f} MB"


def version_dirs(root, area):
    base = os.path.join(root, area)
    if not os.path.isdir(base):
        return []
    vs = [d for d in os.listdir(base)
          if RE_VERSION_DIR.match(d) and os.path.isdir(os.path.join(base, d))]
    return sorted(vs, key=_semver_key)


def dirty_paths(root, area):
    """归档范围内是否有未提交改动（含未跟踪文件）。返回脏路径列表。"""
    try:
        r = subprocess.run(["git", "-C", root, "status", "--porcelain", "--", area],
                           capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []            # 非 git 仓库/取不到 → 不因此阻断（由调用方自担）
    if r.returncode != 0:
        return []
    return [ln[3:].strip().strip('"') for ln in r.stdout.splitlines() if ln.strip()]


def build_plan(root, area, keep):
    """算出该 area 下要归档的版本、以及跨版本重复文件的去重方案。"""
    vs = version_dirs(root, area)
    if len(vs) <= keep:
        return {"area": area, "versions": vs, "archive": [], "exempt": vs,
                "dup": [], "reason": f"版本数 {len(vs)} ≤ 豁免数 {keep}，无可归档版本"}
    exempt, archive = vs[-keep:], vs[:-keep]

    # 跨版本去重：sha → 出现过的 (version, relpath)；保留**最新版本**里的那一份
    by_sha = {}
    for v in vs:                                  # 含豁免版本，作为"保留位置"的候选
        vdir = os.path.join(root, area, v)
        for dp, dn, fns in os.walk(vdir):
            dn[:] = [d for d in dn if d != ARCHIVE_DIRNAME]
            for fn in fns:
                p = os.path.join(dp, fn)
                if os.path.islink(p) or os.path.getsize(p) == 0:
                    continue
                by_sha.setdefault(_sha(p), []).append(
                    (v, os.path.relpath(p, os.path.join(root, area))))
    dup = []
    for sha, occ in by_sha.items():
        if len(occ) < 2:
            continue
        occ.sort(key=lambda t: _semver_key(t[0]))
        keeper = occ[-1]                          # 最新版本里的那份留着
        for v, rel in occ[:-1]:
            if v not in archive:                  # 只删将被归档的老版本里的重复
                continue
            # ⛔ **同版本内不去重**：同一版本里两个文件字节相同但文件名不同，是刻意的
            #    （实测：`resolution-1920x1080.png` 与 `resolution-1366x768.png` 内容恰好一致——
            #     删掉任一份就丢掉了"这两种分辨率都截过图"这条事实）。只跨版本去重。
            if v == keeper[0]:
                continue
            dup.append({"drop": rel, "drop_version": v,
                        "keep": keeper[1], "keep_version": keeper[0], "sha": sha[:12]})
    return {"area": area, "versions": vs, "archive": archive, "exempt": exempt,
            "dup": dup, "reason": ""}


def _write_note(root, area, entries):
    d = os.path.join(root, area, ARCHIVE_DIRNAME)
    os.makedirs(d, exist_ok=True)
    mf_path = os.path.join(d, MANIFEST_NAME)
    try:
        with open(mf_path, encoding="utf-8") as f:
            mf = json.load(f)
    except (OSError, ValueError):
        mf = {"area": area, "entries": {}}
    for e in entries:
        mf["entries"][e["version"]] = e
    mf["updated_at"] = _now()
    with open(mf_path, "w", encoding="utf-8") as f:
        json.dump(mf, f, ensure_ascii=False, indent=2, sort_keys=True)

    lines = [f"# {area} 归档说明", "",
             "> 老版本产物**留在仓库内**，只是从散落目录换成了 zip；近期版本不归档。",
             f"> 由 `.aidp/scripts/archive_old_artifacts.py` 维护，最后更新 {mf['updated_at']}。",
             "> 还原：`python3 .aidp/scripts/archive_old_artifacts.py restore "
             f"--area {area} --version <V> --apply`", "",
             "| 版本 | 归档包 | 文件数 | 原始体积 | 压缩后 | 跨版本去重删除 |",
             "|---|---|---|---|---|---|"]
    for v in sorted(mf["entries"], key=_semver_key):
        e = mf["entries"][v]
        lines.append(f"| {v} | `{ARCHIVE_DIRNAME}/{v}.zip` | {e['files']} | "
                     f"{_mb(e['raw_bytes'])} | {_mb(e['zip_bytes'])} | {len(e.get('dup') or [])} |")
    dups = [(v, x) for v in mf["entries"] for x in (mf["entries"][v].get("dup") or [])]
    if dups:
        lines += ["", "## 跨版本去重明细（内容完全相同，只保留最新版本里的那一份）", "",
                  "| 已删除 | 保留于 |", "|---|---|"]
        for _v, x in sorted(dups, key=lambda t: t[1]["drop"]):
            lines.append(f"| `{x['drop']}` | `{x['keep']}`（{x['keep_version']}）|")
    with open(os.path.join(d, NOTE_NAME), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def do_apply(root, area, plan):
    adir = os.path.join(root, area, ARCHIVE_DIRNAME)
    os.makedirs(adir, exist_ok=True)
    # ① 先去重（只删将被归档版本里的重复文件）
    dropped = 0
    for x in plan["dup"]:
        p = os.path.join(root, area, x["drop"])
        if os.path.isfile(p):
            os.remove(p)
            dropped += 1
    # ② 逐版本打包 → 校验 → 删原目录
    entries = []
    for v in plan["archive"]:
        vdir = os.path.join(root, area, v)
        if not os.path.isdir(vdir):
            continue
        raw = _du(vdir)
        zpath = os.path.join(adir, f"{v}.zip")
        n = 0
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for dp, dn, fns in os.walk(vdir):
                dn[:] = [d for d in dn if d != ARCHIVE_DIRNAME]
                for fn in sorted(fns):
                    p = os.path.join(dp, fn)
                    if os.path.islink(p):
                        continue
                    z.write(p, os.path.join(v, os.path.relpath(p, vdir)))
                    n += 1
        # ★ 校验后才删：能完整打开并列出 n 个条目，才允许移除原目录
        with zipfile.ZipFile(zpath) as z:
            ok = len(z.namelist()) == n and z.testzip() is None
        if not ok:
            print(f"⛔ {v} 归档包校验未通过，保留原目录不删", file=sys.stderr)
            continue
        shutil.rmtree(vdir)
        entries.append({"version": v, "files": n, "raw_bytes": raw,
                        "zip_bytes": os.path.getsize(zpath), "at": _now(),
                        "dup": [x for x in plan["dup"] if x["drop_version"] == v]})
    _write_note(root, area, entries)
    return entries, dropped


def do_restore(root, area, version):
    adir = os.path.join(root, area, ARCHIVE_DIRNAME)
    zpath = os.path.join(adir, f"{version}.zip")
    if not os.path.isfile(zpath):
        return None, f"没有 {zpath}"
    with zipfile.ZipFile(zpath) as z:
        z.extractall(os.path.join(root, area))
    # 去重时删掉的文件按清单从保留位置补回
    restored, pending = 0, []
    try:
        with open(os.path.join(adir, MANIFEST_NAME), encoding="utf-8") as f:
            mf = json.load(f)
        for x in (mf["entries"].get(version, {}).get("dup") or []):
            src = os.path.join(root, area, x["keep"])
            dst = os.path.join(root, area, x["drop"])
            if os.path.isfile(dst):
                continue
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                restored += 1
            else:
                # 保留位置本身还在别的归档包里（该版本也已归档）→ 明确报出来，
                # 不静默跳过（否则用户以为还原完整了，实际缺文件）
                pending.append({"need": x["keep"], "in_version": x["keep_version"],
                                "for": x["drop"]})
    except (OSError, ValueError, KeyError):
        pass
    return {"version": version, "dedup_restored": restored, "pending": pending}, ""


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="archive_old_artifacts",
        description="老版本大目录留仓归档（跨版本去重 + 打包；豁免最近 N 个版本）")
    ap.add_argument("cmd", nargs="?", default="plan", choices=["plan", "apply", "restore"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--area", action="append", default=[],
                    help=f"目标目录，可重复；默认 {'、'.join(DEFAULT_AREAS)}")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP, help="豁免最近 N 个版本（默认 5）")
    ap.add_argument("--version", default="", help="restore：要还原的版本")
    ap.add_argument("--apply", action="store_true", help="真正执行（不给即只打印计划）")
    ap.add_argument("--allow-dirty", action="store_true", help="忽略脏工作区检查（不建议）")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    root = os.path.abspath(a.root)
    areas = a.area or list(DEFAULT_AREAS)
    if a.keep < 1:
        print("⛔ --keep 至少为 1（绝不允许把所有版本都归档）", file=sys.stderr)
        return 2

    if a.cmd == "restore":
        if not a.version or len(areas) != 1:
            print("⛔ restore 需要 --version <V> 且只能指定一个 --area", file=sys.stderr)
            return 2
        if not a.apply:
            print(f"[dry-run] 将把 {areas[0]}/{ARCHIVE_DIRNAME}/{a.version}.zip 解回原位；"
                  f"加 --apply 执行")
            return 0
        res, err = do_restore(root, areas[0], a.version)
        if err:
            print("⛔ " + err, file=sys.stderr)
            return 1
        if a.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            print(f"✅ 已还原 {a.version}（去重补回 {res['dedup_restored']} 个文件）")
            if res["pending"]:
                need = sorted({p["in_version"] for p in res["pending"]})
                print(f"⚠️ 另有 {len(res['pending'])} 个去重文件的保留副本仍在归档包里 —— "
                      f"请先 restore 这些版本：{'、'.join(need)}")
        return 0

    out, rc = [], 0
    for area in areas:
        plan = build_plan(root, area, a.keep)
        out.append(plan)
        if a.json:
            continue
        print(f"── {area}")
        if plan["reason"]:
            print(f"   跳过：{plan['reason']}")
            continue
        raw = sum(_du(os.path.join(root, area, v)) for v in plan["archive"])
        dup_bytes = sum(os.path.getsize(os.path.join(root, area, x["drop"]))
                        for x in plan["dup"]
                        if os.path.isfile(os.path.join(root, area, x["drop"])))
        print(f"   豁免（最近 {a.keep} 个）：{'、'.join(plan['exempt'])}")
        print(f"   归档 {len(plan['archive'])} 个版本：{'、'.join(plan['archive'])}")
        print(f"   原始体积 {_mb(raw)}　跨版本重复文件 {len(plan['dup'])} 个（{_mb(dup_bytes)}）")
        for x in plan["dup"][:5]:
            print(f"     - 删 `{x['drop']}` ← 同 `{x['keep']}`（{x['keep_version']}）")
        if len(plan["dup"]) > 5:
            print(f"     …… 另 {len(plan['dup']) - 5} 个，明细见归档说明")

    if a.cmd == "apply":
        if not a.apply:
            print("\n⚠️ 这是会删文件的操作：以上仅为计划，加 `--apply` 才真正执行。")
            return 0
        for area in areas:
            dirty = [] if a.allow_dirty else dirty_paths(root, area)
            if dirty:
                print(f"⛔ {area} 有 {len(dirty)} 处未提交改动，拒绝归档"
                      f"（先提交或 --allow-dirty）：{'、'.join(dirty[:3])}", file=sys.stderr)
                rc = 1
                continue
            plan = build_plan(root, area, a.keep)
            if not plan["archive"]:
                continue
            entries, dropped = do_apply(root, area, plan)
            saved = sum(e["raw_bytes"] - e["zip_bytes"] for e in entries)
            gain = (f"净省约 {_mb(saved)}" if saved > 0 else "体积基本持平（小目录的压缩开销 > 收益）")
            print(f"✅ {area}：归档 {len(entries)} 个版本、去重删除 {dropped} 个文件，"
                  f"{gain}；说明见 {area}/{ARCHIVE_DIRNAME}/{NOTE_NAME}")
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    return rc


if __name__ == "__main__":
    sys.exit(main())
