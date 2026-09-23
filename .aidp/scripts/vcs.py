#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""集中处理 Git 能力检测与无 VCS 降级。"""
from __future__ import annotations

import getpass
import os
import re
import subprocess
from pathlib import Path

EXIT_UNSUPPORTED = 3
GIT_TIMEOUT_SECONDS = 10


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", "-C", str(root), *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def detect_mode(root: Path | str) -> str:
    """Return `git` only when the project itself is a Git worktree root."""
    root = Path(root)
    proc = _run_git(root, "rev-parse", "--is-inside-work-tree")
    if proc is None or proc.returncode != 0 or proc.stdout.strip() != "true":
        return "none"
    top = _run_git(root, "rev-parse", "--show-toplevel")
    if top is None or top.returncode != 0 or not top.stdout.strip():
        return "none"
    return "git" if os.path.abspath(root) == os.path.abspath(top.stdout.strip()) else "none"


def unsupported(capability: str) -> dict[str, str]:
    return {"status": "unsupported", "reason": "vcs-disabled", "capability": capability}


def _identity(value: object) -> str:
    text = str(value or "").strip()
    return text if text and re.search(r"\w", text, flags=re.UNICODE) else ""


def _git_user_name(root: Path | str) -> str:
    proc = _run_git(Path(root), "config", "--local", "--get", "user.name")
    if proc is None or proc.returncode != 0:
        return ""
    return _identity(proc.stdout)


def developer_identity(root: Path | str, explicit_user: str | None = None) -> str:
    """Resolve user as explicit → local Git config → AIDP_USER → OS user."""
    explicit = _identity(explicit_user)
    if explicit:
        return explicit
    if detect_mode(Path(root)) == "git":
        git_user = _identity(_git_user_name(root))
        if git_user:
            return git_user
    env_user = _identity(os.environ.get("AIDP_USER"))
    if env_user:
        return env_user
    return _identity(getpass.getuser()) or "unknown"

def main(argv=None) -> int:
    """CLI 入口：`python3 {{AIDP_HOME}}/scripts/vcs.py mode [--root DIR]`。

    ⛔ 存在的理由是**消掉双写**：此前 flows / commands 里有 6 处逐字相同的
    `PYTHONPATH=…/scripts python3 -c 'from vcs import detect_mode; …'` 内联探测。
    那种写法既撑爆分片体积，又让「探测口径」散成 6 份 —— 改判据时必漏。
    """
    import argparse

    ap = argparse.ArgumentParser(description="Git 能力探测")
    ap.add_argument("action", choices=("mode",), help="mode = 打印 git / none")
    ap.add_argument("--root", default=".", help="项目根（缺省当前目录）")
    a = ap.parse_args(argv)
    print(detect_mode(Path(a.root)))
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
