#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_marker.py —— 项目侧「脚手架版本戳」的读写单一信源。

落点是 `memory/aidp-config.yaml` 的 `scaffold:` 段：

    scaffold:
      version: V1.0.0   # 上次同步到的脚手架版本；模板项目自身恒为 null
      pending: V1.0.0   # 非 null = 本轮升级尚未交付（语义改写队列未消费完）

本模块自包含、不 import 项目侧 `.aidp/scripts/`（init 时目标项目还没有它们），
写入是外科手术式的：只改 `scaffold.version` / `scaffold.pending` 两个键，保留其余字节与注释。

CLI：
    python3 scaffold_marker.py [<root>]      # 打印 version / pending / downstream
    python3 scaffold_marker.py --self-check
"""
import os
import re
import sys

CONFIG_REL = os.path.join("memory", "aidp-config.yaml")

_SEC_RE = re.compile(r"^scaffold:\s*$")
_KEY_RE = re.compile(r"^\s+(version|pending)\s*:\s*(.*?)\s*$")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    # newline="" —— 关掉平台行尾翻译，Windows 上也恒写 LF（版本戳落在 memory/aidp-config.yaml，
    # 混入 CRLF 会让同一份配置在两端算出不同字节指纹）。
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _read_cfg(root):
    out = {"version": None, "pending": None}
    try:
        lines = _read(os.path.join(str(root), CONFIG_REL)).splitlines()
    except (OSError, ValueError):
        return out
    in_sec = False
    for ln in lines:
        if ln[:1] not in (" ", "\t") and ln.strip():
            in_sec = bool(_SEC_RE.match(ln.strip()))
            continue
        if not in_sec:
            continue
        m = _KEY_RE.match(ln)
        if m:
            v = m.group(2).split("#")[0].strip().strip('"\'')
            out[m.group(1)] = None if v in ("", "null", "~") else v
    return out


def read_version(root):
    """项目上次同步到的脚手架版本号；从未同步 → None。"""
    return _read_cfg(root)["version"]


def read_pending(root):
    """待交付升级的目标版本号；无 → None。"""
    return _read_cfg(root)["pending"]


def is_downstream(root):
    """任一标记非空 = 经脚手架初始化 / 升级的项目（模板项目自身两者皆为 null）。"""
    return bool(read_version(root) or read_pending(root))


def _ensure_cfg(root):
    p = os.path.join(str(root), CONFIG_REL)
    if not os.path.isfile(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        _write(p, "# AIDP 项目配置（人维护，团队共享、随 git 提交）\n")
    return p


def _set(root, key, value):
    p = _ensure_cfg(root)
    lines = _read(p).splitlines()
    val = "null" if value is None else str(value)
    sec = next((i for i, ln in enumerate(lines)
                if ln[:1] not in (" ", "\t") and _SEC_RE.match(ln.strip())), None)
    if sec is None:
        lines += ["", "scaffold:", "  %s: %s" % (key, val)]
    else:
        end = next((j for j in range(sec + 1, len(lines))
                    if lines[j].strip() and lines[j][:1] not in (" ", "\t")), len(lines))
        hit = next((j for j in range(sec + 1, end)
                    if _KEY_RE.match(lines[j]) and _KEY_RE.match(lines[j]).group(1) == key), None)
        if hit is not None:
            lines[hit] = "  %s: %s" % (key, val)
        else:
            ins = end
            while ins > sec + 1 and not lines[ins - 1].strip():
                ins -= 1
            lines.insert(ins, "  %s: %s" % (key, val))
    _write(p, "\n".join(lines) + "\n")


def write_version(root, raw):
    """写正式版本戳并清 pending（升级已交付）。"""
    _set(root, "version", raw)
    _set(root, "pending", None)


def write_pending(root, raw):
    """写待交付标记，不推进正式版本戳。"""
    _set(root, "pending", raw)


def _self_check():
    import shutil
    import tempfile
    ok = []
    d = tempfile.mkdtemp()
    try:
        ok.append(("空项目 → 非下游", is_downstream(d) is False))
        write_version(d, "V1.0.0")
        ok.append(("写后读到版本", read_version(d) == "V1.0.0"))
        ok.append(("写后判下游", is_downstream(d) is True))
        write_pending(d, "V1.1.0")
        ok.append(("pending 不推进正式版本", read_pending(d) == "V1.1.0" and read_version(d) == "V1.0.0"))
        write_version(d, "V1.1.0")
        ok.append(("交付后 pending 清空", read_pending(d) is None and read_version(d) == "V1.1.0"))
        cfg = os.path.join(d, CONFIG_REL)
        _write(cfg, "notify:\n  # 说明行\n  enabled: false\n\nscaffold:\n  version: null\n  pending: null\n")
        write_version(d, "V2.0.0")
        txt = _read(cfg)
        ok.append(("写入保留其余注释与键", "# 说明行" in txt and "enabled: false" in txt
                   and "version: V2.0.0" in txt))
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if all(r for _, r in ok) else 1


if __name__ == "__main__":
    if "-h" in sys.argv or "--help" in sys.argv:
        print(__doc__)
        sys.exit(0)
    if "--self-check" in sys.argv:
        sys.exit(_self_check())
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    print("version=%s pending=%s downstream=%s"
          % (read_version(root), read_pending(root), is_downstream(root)))
