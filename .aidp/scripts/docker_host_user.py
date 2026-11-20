#!/usr/bin/env python3
"""以宿主机用户运行容器工具，避免产物（回执、导出文件、bind mount 内改动）变成 root 属主。

  docker_host_user.py run  [docker run 参数…] IMAGE [命令…]    自动补 --user $(id -u):$(id -g)
  docker_host_user.py exec [docker exec 参数…] CONTAINER 命令…  同上
  docker_host_user.py --dry-run run …                          只打印最终命令，不执行
  docker_host_user.py --check run_tests.sh [其他脚本…]          扫描脚本里的 docker run/exec 是否已带 --user

已显式传 --user / -u 的命令原样转发，不覆盖用户选择。确需 root 的行在脚本里加注释
`# aidp:allow-root` 即可通过 --check。--check 退出码：0 全部合规；1 有缺 --user 的容器调用；2 入参错误。
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys

VALUE_OPTIONS = {"-v", "--volume", "--mount", "-w", "--workdir", "-u", "--user", "-e", "--env", "--name",
                 "--entrypoint", "--network", "--net", "-p", "--publish", "--env-file", "-l", "--label",
                 "--add-host", "--cap-add", "--cap-drop", "-m", "--memory", "--cpus", "--platform",
                 "--restart", "--pull", "--hostname", "-h", "--device", "--group-add", "--tmpfs",
                 "--log-driver", "--ulimit", "--shm-size"}
ALLOW_MARK = "aidp:allow-root"
CONTAINER_CALL = re.compile(r"\b(?:docker(?:\s+compose)?|docker-compose|podman)\s+(?:[^\n;|&]*?\s)?(run|exec)\b")


def has_user_option(args):
    """只看镜像/容器名之前的选项；容器内命令里的 -u 不算。"""
    i = 0
    while i < len(args):
        item = args[i]
        if item in ("-u", "--user") or item.startswith("--user=") or (item.startswith("-u") and len(item) > 2 and not item.startswith("--")):
            return True
        if item in VALUE_OPTIONS:
            i += 2
            continue
        if item.startswith("-"):
            i += 1
            continue
        return False
    return False


def build_command(sub, args, uid=None, gid=None):
    uid = os.getuid() if uid is None else uid
    gid = os.getgid() if gid is None else gid
    command = ["docker", sub]
    if not has_user_option(args):
        command += ["--user", "%d:%d" % (uid, gid)]
    return command + list(args)


def scan_script(path):
    """返回 [(行号, 文本)]：缺 --user 的 docker/podman run|exec 调用（合并续行后判断）。"""
    with open(path, encoding="utf-8", errors="replace") as handle:
        lines = handle.read().splitlines()
    findings, i = [], 0
    while i < len(lines):
        start, text = i, lines[i]
        while text.rstrip().endswith("\\") and i + 1 < len(lines):
            i += 1
            text = text.rstrip()[:-1] + " " + lines[i]
        i += 1
        code = text.split("#", 1)[0] if ALLOW_MARK not in text else ""
        if ALLOW_MARK in text or not CONTAINER_CALL.search(code):
            continue
        if re.search(r"(?:^|\s)(?:--user(?:=|\s)|-u\s?\S)", code):
            continue
        if re.search(r"\$\{?\w*(?:USER|UID)\w*\}?:\$\{?\w*GID\w*\}?", code):
            continue
        findings.append((start + 1, " ".join(text.split())[:140]))
    return findings


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--check":
        paths = argv[1:]
        if not paths:
            print("用法：docker_host_user.py --check <脚本> [脚本…]", file=sys.stderr)
            return 2
        bad = 0
        for path in paths:
            try:
                findings = scan_script(path)
            except OSError as exc:
                print("无法读取 %s：%s" % (path, exc), file=sys.stderr)
                return 2
            for number, text in findings:
                bad += 1
                print("%s:%d: docker run/exec 未带 --user：%s" % (path, number, text))
        if bad:
            print("修复：加 --user \"$(id -u):$(id -g)\"，或改用 docker_host_user.py；确需 root 的行加注释 # %s" % ALLOW_MARK)
            return 1
        print("全部容器调用已带 --user")
        return 0
    dry = False
    if argv and argv[0] == "--dry-run":
        dry, argv = True, argv[1:]
    if len(argv) < 2 or argv[0] not in ("run", "exec"):
        print(__doc__, file=sys.stderr)
        return 2
    command = build_command(argv[0], argv[1:])
    if dry:
        print(shlex.join(command))
        return 0
    return subprocess.call(command)


if __name__ == "__main__":
    sys.exit(main())
