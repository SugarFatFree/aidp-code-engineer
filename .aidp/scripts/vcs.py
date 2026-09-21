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
    """Return `git` only for a real Git worktree; every other case is `none`."""
    proc = _run_git(Path(root), "rev-parse", "--is-inside-work-tree")
    if proc is not None and proc.returncode == 0 and proc.stdout.strip() == "true":
        return "git"
    return "none"


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
