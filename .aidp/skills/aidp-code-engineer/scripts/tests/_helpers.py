# -*- coding: utf-8 -*-
"""脚手架测试共用工具：临时 git 仓库、脚本调用。"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
SKILL_DIR = SCRIPTS.parent
REPO = SKILL_DIR.parents[2]
sys.path.insert(0, str(SCRIPTS))


def clean_env():
    env = dict(os.environ)
    env.pop("AIDP_AGENT", None)
    return env


def run_script(name, *args, cwd=None, check=True):
    p = subprocess.run([sys.executable, str(SCRIPTS / name), *map(str, args)], capture_output=True,
                       text=True, cwd=cwd, env=clean_env(), stdin=subprocess.DEVNULL)
    if check and p.returncode != 0:
        raise AssertionError(f"{name} {' '.join(map(str, args))} → exit {p.returncode}\n{p.stdout}\n{p.stderr}")
    return p


def run_json(name, *args, **kw):
    p = run_script(name, *args, **kw)
    return json.loads(p.stdout)


class TempRepo:
    """with TempRepo() as root: …（已 git init 并配置 user.name=tester）"""

    def __init__(self, name="demo"):
        self.name = name

    def __enter__(self) -> Path:
        self._tmp = tempfile.mkdtemp()
        root = Path(self._tmp) / self.name
        root.mkdir()
        for args in (["init", "-q"], ["config", "user.name", "tester"], ["config", "user.email", "t@example.com"]):
            subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)
        return root

    def __exit__(self, *exc):
        shutil.rmtree(self._tmp, ignore_errors=True)


def verify(root, version="V0.1.0", user="tester", extra=()):
    p = run_script("verify.py", root, version, user, "--read-only", "--no-guards", *extra, check=False)
    errors = [l.strip() for l in p.stdout.splitlines() if l.strip().startswith("[ERROR]")]
    return p.returncode, errors, p.stdout
