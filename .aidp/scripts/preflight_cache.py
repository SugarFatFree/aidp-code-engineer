#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""同 tick 前置检查结论缓存 —— 「不重复执行同一检查」，⛔ 不是「跳过检查」。

## 为什么需要

`/sprint-autopilot` 的 Phase 0.0–0.7 与 `/sprint-aiauto-test` 的 Phase 0.0.0–0.4
实质检查高度重叠：拉码 / 读测试方案 / chrome 就绪 / 部署探测 / 账号加载 / **登录冒烟**。
autopilot 委派测试链路时，后者把同一套又跑一遍 —— 实测 **30 分钟内做了两次登录冒烟**
（每次两个账号各 2 次鉴权取数 = 8 次 OAuth2 往返）。

## 判据：缓存键必须含「判据输入」

⛔ **按时间缓存是错的**（「15 分钟内跑过就复用」会在代码刚推完的那一刻复用上一轮结论）。
键 = `check` + 该检查**真正依赖的输入指纹**：

  · 拉码类 → `git HEAD`
  · 测试方案 / 账号表类 → 对应文件的 `mtime_ns + size`
  · chrome / 部署探测类 → 目标地址 + 驱动标识

输入指纹变了即未命中，照常重跑。**同 tick** 由 `run_id` 保证（跨 tick 一律不复用：
上一 tick 的环境结论对这一 tick 没有保证）。

## 边界

- **只缓存「成功」结论**：失败/阻塞不进缓存 —— 复用一个失败结论等于把一次偶发
  网络问题变成本 tick 的永久结论。
- 命中时**必须打印复用来源**（谁、何时、凭什么指纹），⛔ 不允许静默复用：
  「这一步跑过了」与「这一步被跳过了」在日志上必须分得开。
- 缓存落 `memory/.aidp/preflight-cache.json`，整份随 `run_id` 换代即丢弃。
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

_script_dir = str(Path(__file__).resolve().parent)
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from aidp_paths import preflight_cache as cache_path

def _path(root):
    return cache_path(root)


def _load(root):
    try:
        with open(_path(root), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(root, data):
    p = _path(root)
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp.%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except OSError:
        return False


def _git_head(root):
    try:
        r = subprocess.run(["git", "-C", root, "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=10)
        return (r.stdout or "").strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def fingerprint(root, files=(), extra=()):
    """判据输入指纹：git HEAD + 各依赖文件的 (mtime_ns, size) + 调用方补充项。

    ⛔ 文件不存在也要进指纹（记 `missing`）—— 否则「账号表被删」与「账号表没变」同形。
    """
    parts = ["head=" + _git_head(root)]
    for rel in sorted(files):
        p = os.path.join(root, rel)
        try:
            st = os.stat(p)
            parts.append("%s=%d:%d" % (rel, st.st_mtime_ns, st.st_size))
        except OSError:
            parts.append("%s=missing" % rel)
    parts.extend(sorted(str(e) for e in extra))
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def get(root, run_id, check, fp):
    """命中返回缓存条目，未命中返回 None。"""
    if not str(run_id or "").strip():
        return None
    data = _load(root)
    if str(data.get("run_id") or "") != str(run_id):
        return None                     # 跨 tick 不复用
    checks = data.get("checks")
    entry = checks.get(check) if isinstance(checks, dict) else None
    if not isinstance(entry, dict) or str(entry.get("verdict")).lower() not in ("ok", "pass", "true", "verified"):
        return None
    if entry.get("fingerprint") != fp:
        return None                     # 判据输入变了 → 照常重跑
    return entry


def put(root, run_id, check, fp, verdict, detail="", stdout=None):
    """只写成功结论。返回是否写入。"""
    if not str(run_id or "").strip() or str(verdict).lower() not in ("ok", "pass", "true", "verified"):
        return False                    # ⛔ 失败/阻塞不进缓存
    data = _load(root)
    if str(data.get("run_id") or "") != str(run_id):
        data = {"run_id": str(run_id), "checks": {}}
    if not isinstance(data.get("checks"), dict):
        data["checks"] = {}
    data["checks"][check] = {
        "fingerprint": fp, "verdict": str(verdict),
        "detail": str(detail)[:400],
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "by": os.environ.get("AIDP_CHAIN") or "unknown",
    }
    if stdout is not None:
        data["checks"][check]["stdout"] = stdout
    return _save(root, data)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--run-id", required=True, help="本 tick 标识（跨 tick 不复用）")
    ap.add_argument("--check", required=True, help="检查名，如 login-smoke / chrome-ready")
    ap.add_argument("--file", action="append", default=[],
                    help="该检查依赖的文件（可重复）—— 变了即未命中")
    ap.add_argument("--extra", action="append", default=[],
                    help="补充指纹项（可重复），如被测 origin / 驱动标识")
    ap.add_argument("--cmd", default="", help="未命中时执行的 shell 命令；成功才写缓存")
    ap.add_argument("--put", default="", metavar="VERDICT",
                    help="写入结论（只写成功：ok/pass/verified）")
    ap.add_argument("--detail", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    extra = a.extra + (["cmd=" + a.cmd] if a.cmd else [])
    fp = fingerprint(root, a.file, extra)
    if a.put:
        wrote = put(root, a.run_id, a.check, fp, a.put, a.detail)
        out = {"action": "put", "check": a.check, "fingerprint": fp, "written": wrote,
               "note": "" if wrote else "非成功结论不入缓存（失败不可复用）"}
        print(json.dumps(out, ensure_ascii=False) if a.json
              else ("💾 已缓存 %s（%s）" % (a.check, fp) if wrote
                    else "ℹ️ %s 非成功结论，不入缓存" % a.check))
        return 0

    hit = get(root, a.run_id, a.check, fp)
    if a.cmd and hit and "stdout" in hit:
        print("♻️ 复用同 tick 结论：%s（run_id=%s，由 %s 于 %s 验证，指纹 %s）" % (
            a.check, a.run_id, hit.get("by"), hit.get("at"), fp), file=sys.stderr)
        print(hit["stdout"], end="")
        return 0
    if a.cmd:
        try:
            proc = subprocess.run(a.cmd, shell=True, cwd=root, capture_output=True, text=True)
        except OSError as exc:
            print(str(exc), file=sys.stderr); return 2
        if proc.stdout: print(proc.stdout, end="")
        if proc.stderr: print(proc.stderr, end="", file=sys.stderr)
        success = proc.returncode == 0
        try:
            payload = json.loads(proc.stdout)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            # JSON 信息快照、skipped 或 passed:false 不能凭 exit 0 冒充成功探针。
            success = success and (payload.get("passed") is True or payload.get("ok") is True)
            success = success and not payload.get("skipped")
        if success:
            put(root, a.run_id, a.check, fp, "ok", a.detail or a.cmd, stdout=proc.stdout)
        return proc.returncode
    out = {"action": "get", "check": a.check, "fingerprint": fp,
           "hit": bool(hit), "entry": hit or {}}
    if a.json:
        print(json.dumps(out, ensure_ascii=False))
    elif hit:
        # ⛔ 必须打印复用来源：「跑过了」与「被跳过了」在日志上要分得开
        print("♻️ 复用同 tick 结论：%s = %s（由 %s 于 %s 验证，指纹 %s）"
              % (a.check, hit.get("verdict"), hit.get("by"), hit.get("at"), fp))
    else:
        print("🔍 无同 tick 结论可复用：%s（指纹 %s）→ 照常执行本检查" % (a.check, fp))
    return 0 if hit else 1


if __name__ == "__main__":
    sys.exit(main())
