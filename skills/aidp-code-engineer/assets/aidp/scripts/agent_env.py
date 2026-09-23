#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_env.py —— 识别本项目启用的 AI 编码 Agent，并解析项目记忆文件落点。

单一信源 `AIDP_HOME/` 同时服务多个 Agent（Claude Code / Codex / DeepSeek Harness）；
各 Agent 读的项目记忆文件不同：

  · 只有 Claude Code          → `CLAUDE.md`
  · 含 Codex / DeepSeek Harness → `AGENTS.md`（二者并存时 `CLAUDE.md` 是 `@AGENTS.md` 薄壳）

读写项目记忆文件的脚本一律经 `memory_file(root)` 取路径，⛔ 不自行拼 `CLAUDE.md` / `AGENTS.md`。

判定顺序（`detect_agents`）：
  1. 环境变量 `AIDP_AGENT`（逗号分隔，如 `claude,codex`）—— 显式声明优先；
  2. 根目录标记目录：`.codex/` → codex、`.dsh/` → dsh、`.claude/` → claude；
  3. 都没有 → `["claude"]`。

`memory_file` 额外规则：`AGENTS.md` 已存在且 `CLAUDE.md` 仅为 `@AGENTS.md` 薄壳 → `AGENTS.md`
（真正的正文在 AGENTS.md，写进薄壳会把导入结构冲掉）。

CLI：
  python3 AIDP_HOME/scripts/agent_env.py detect      [--root .]   # {"agents": [...], "source": "env|markers|default"}
  python3 AIDP_HOME/scripts/agent_env.py memory-file [--root .]   # {"memory_file": "AGENTS.md", "agents": [...], ...}
  python3 AIDP_HOME/scripts/agent_env.py --self-check
"""
import argparse
import json
import os
import re
import sys

KNOWN_AGENTS = ("claude", "codex", "dsh")
# 根目录标记目录 → Agent（顺序即输出顺序）
MARKER_DIRS = ((".codex", "codex"), (".dsh", "dsh"), (".claude", "claude"))
_ALIASES = {"claude-code": "claude", "claudecode": "claude", "deepseek": "dsh",
            "deepseek-harness": "dsh", "openai-codex": "codex"}


def _normalize(name):
    n = (name or "").strip().lower()
    return _ALIASES.get(n, n)


def detect_agents_detail(root="."):
    """→ {"agents": [...], "source": "env" | "markers" | "default"}。"""
    env = os.environ.get("AIDP_AGENT", "")
    if env.strip():
        seen = []
        for part in env.split(","):
            n = _normalize(part)
            if n and n not in seen:
                seen.append(n)
        if seen:
            return {"agents": seen, "source": "env"}
    found = [agent for d, agent in MARKER_DIRS if os.path.isdir(os.path.join(root, d))]
    if found:
        return {"agents": found, "source": "markers"}
    return {"agents": ["claude"], "source": "default"}


def detect_agents(root="."):
    """本项目启用的 Agent 列表（至少一个）。"""
    return detect_agents_detail(root)["agents"]


_IMPORT_LINE = re.compile(r"^@\.?/?AGENTS\.md\s*$")


def is_thin_shell(path):
    """`CLAUDE.md` 是否仅为 `@AGENTS.md` 薄壳（除标题 / 注释 / 空行外只有导入行）。"""
    try:
        text = open(path, encoding="utf-8").read()
    except (OSError, ValueError):
        return False
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    has_import = False
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        if _IMPORT_LINE.match(s):
            has_import = True
            continue
        return False
    return has_import


def memory_file(root="."):
    """项目记忆文件的相对文件名（`CLAUDE.md` 或 `AGENTS.md`）。"""
    agents = detect_agents(root)
    agents_md = os.path.join(root, "AGENTS.md")
    claude_md = os.path.join(root, "CLAUDE.md")
    if os.path.isfile(agents_md) and os.path.isfile(claude_md) and is_thin_shell(claude_md):
        return "AGENTS.md"
    if agents == ["claude"]:
        return "CLAUDE.md"
    return "AGENTS.md"


def memory_file_path(root="."):
    """项目记忆文件的完整路径。"""
    return os.path.join(root, memory_file(root))


def _self_check():
    import shutil
    import tempfile
    ok = []
    saved = os.environ.pop("AIDP_AGENT", None)
    d = tempfile.mkdtemp()
    try:
        ok.append(("无标记 → 默认 claude", detect_agents(d) == ["claude"]))
        ok.append(("仅 claude → CLAUDE.md", memory_file(d) == "CLAUDE.md"))
        os.makedirs(os.path.join(d, ".claude"))
        os.makedirs(os.path.join(d, ".codex"))
        ok.append(("标记目录 → codex + claude", detect_agents(d) == ["codex", "claude"]))
        ok.append(("含 codex → AGENTS.md", memory_file(d) == "AGENTS.md"))
        os.environ["AIDP_AGENT"] = "claude"
        ok.append(("AIDP_AGENT 优先于标记目录", detect_agents(d) == ["claude"]))
        open(os.path.join(d, "AGENTS.md"), "w", encoding="utf-8").write("# 正文\n")
        open(os.path.join(d, "CLAUDE.md"), "w", encoding="utf-8").write("# 薄壳\n\n@AGENTS.md\n")
        ok.append(("★ CLAUDE.md 为 @AGENTS.md 薄壳 → AGENTS.md（即便只有 claude）",
                   memory_file(d) == "AGENTS.md"))
        open(os.path.join(d, "CLAUDE.md"), "w", encoding="utf-8").write("# 正文\n\n@AGENTS.md\n内容\n")
        ok.append(("CLAUDE.md 含正文 → 非薄壳，仅 claude 时仍 CLAUDE.md",
                   memory_file(d) == "CLAUDE.md"))
        os.environ["AIDP_AGENT"] = "Claude-Code, deepseek"
        ok.append(("环境变量别名归一", detect_agents(d) == ["claude", "dsh"]))
    finally:
        os.environ.pop("AIDP_AGENT", None)
        if saved is not None:
            os.environ["AIDP_AGENT"] = saved
        shutil.rmtree(d, ignore_errors=True)
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if all(r for _, r in ok) else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="识别启用的 AI Agent 与项目记忆文件落点")
    ap.add_argument("cmd", nargs="?", choices=["detect", "memory-file"])
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    if not a.cmd:
        ap.print_usage(sys.stderr)
        return 2
    det = detect_agents_detail(a.root)
    if a.cmd == "detect":
        print(json.dumps(det, ensure_ascii=False))
        return 0
    print(json.dumps({"memory_file": memory_file(a.root), "agents": det["agents"],
                      "source": det["source"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
