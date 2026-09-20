#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_env.py + agent_sync.py 多 Agent 装配单测（stdlib only，临时 git 仓库）。

覆盖：
  · agent_env：AIDP_AGENT > 标记目录 > 默认；别名归一；memory-file 判定（薄壳识别）；CLI detect / memory-file / --self-check
  · agent_sync：Claude Code / Codex / DeepSeek Harness 三种入口装配（SKILL 目录、命令入口 / 包装 SKILL、Stop hook）
  · 记忆文件搬迁：仅 Claude → CLAUDE.md 正文；并存 → 正文进 AGENTS.md、CLAUDE.md 成 @AGENTS.md 薄壳；⛔ 不丢正文
  · 幂等（二次运行零动作）、--check 漂移 exit 1 且不写盘、源删除后清理自生成入口但不碰用户自有 SKILL
  · --mode copy、未知 Agent / 无 .aidp → exit 2、非法 hooks JSON 拒绝覆盖、--self-check

直接跑：`python3 .aidp/scripts/tests/test_agent_sync.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
ENV_PY = os.path.join(SCRIPTS, "agent_env.py")
SYNC_PY = os.path.join(SCRIPTS, "agent_sync.py")

import agent_env as AE  # noqa: E402
import agent_sync as AS  # noqa: E402

_passed = _failed = 0
os.environ.pop("AIDP_AGENT", None)


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _clean_env(**extra):
    env = {k: v for k, v in os.environ.items() if k != "AIDP_AGENT"}
    env.update(extra)
    return env


def _run(script, *args, root=None, **env_extra):
    cp = subprocess.run([sys.executable, script, *args], cwd=str(root) if root else None,
                        capture_output=True, text=True, env=_clean_env(**env_extra), timeout=60)
    try:
        out = json.loads(cp.stdout.strip().splitlines()[-1]) if cp.stdout.strip() else {}
    except ValueError:
        out = {}
    return cp.returncode, out, cp.stdout, cp.stderr


BODY = "# demo-app 项目记忆\n\n## 核心约定\n\n1. **示例约定**：alice 维护。\n"


def _mkrepo(markers=(), claude_md=BODY, agents_md=None, hook=True):
    root = Path(tempfile.mkdtemp()) / "demo-app"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], capture_output=True)
    (root / ".aidp/skills/demo-skill").mkdir(parents=True)
    (root / ".aidp/skills/demo-skill/SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: 示例\n---\n# demo\n", encoding="utf-8")
    (root / ".aidp/skills/not-a-skill").mkdir()  # 无 SKILL.md → 不装配
    (root / ".aidp/commands").mkdir(parents=True)
    (root / ".aidp/commands/sprint-dev.md").write_text(
        '---\ndescription: 执行 "Sprint" 开发\nargument-hint: "<需求描述>"\n---\n# /sprint-dev\n\n参数：$ARGUMENTS\n',
        encoding="utf-8")
    (root / ".aidp/commands/version.md").write_text("# /version — 版本规划\n\n正文\n", encoding="utf-8")
    (root / ".aidp/commands/README.md").write_text("# 命令索引\n", encoding="utf-8")
    if hook:
        (root / ".aidp/hooks").mkdir(parents=True)
        (root / AS.STOP_GUARD_REL).write_text("# stop guard\n", encoding="utf-8")
    for m in markers:
        (root / m).mkdir(exist_ok=True)
    if claude_md is not None:
        (root / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
    if agents_md is not None:
        (root / "AGENTS.md").write_text(agents_md, encoding="utf-8")
    return root


def _add_browser_plugin(root):
    plugin = root / ".aidp/plugins/chrome-devtools-mcp"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin/plugin.json").write_text(json.dumps(
        {"name": "chrome-devtools-mcp", "version": "1.6.0", "description": "浏览器",
         "mcpServers": {"chrome-devtools": {
             "command": "npx", "args": ["chrome-devtools-mcp@1.6.0"]}}}),
        encoding="utf-8")
    (plugin / ".claude-plugin/marketplace.json").write_text(json.dumps(
        {"name": "chrome-devtools-plugins",
         "plugins": [{"name": "chrome-devtools-mcp", "source": "./"}]}), encoding="utf-8")
    (plugin / "skills/chrome-devtools/references").mkdir(parents=True)
    (plugin / "skills/chrome-devtools/SKILL.md").write_text(
        "---\nname: chrome-devtools\ndescription: 浏览器调试\n---\n", encoding="utf-8")
    (plugin / "skills/chrome-devtools/references/usage.md").write_text(
        "# usage\n\n完整参考内容\n", encoding="utf-8")
    return plugin


def _rm(root):
    shutil.rmtree(root.parent, ignore_errors=True)


def _read(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except OSError:
        return ""


# ── agent_env ────────────────────────────────────────────────────────────────
def test_agent_env():
    print("【agent_env：Agent 检测 + 记忆文件落点】")
    root = _mkrepo(claude_md=None)
    try:
        check("无标记 → 默认 claude", AE.detect_agents_detail(str(root)) == {"agents": ["claude"], "source": "default"})
        check("仅 claude → CLAUDE.md", AE.memory_file(str(root)) == "CLAUDE.md")
        (root / ".claude").mkdir()
        check("仅 .claude/ → claude / markers", AE.detect_agents_detail(str(root)) == {"agents": ["claude"], "source": "markers"})
        (root / ".dsh").mkdir()
        (root / ".codex").mkdir()
        check("三标记 → 顺序 codex,dsh,claude", AE.detect_agents(str(root)) == ["codex", "dsh", "claude"])
        check("含非 claude → AGENTS.md", AE.memory_file(str(root)) == "AGENTS.md")
        os.environ["AIDP_AGENT"] = "claude"
        try:
            check("AIDP_AGENT 优先于标记", AE.detect_agents_detail(str(root)) == {"agents": ["claude"], "source": "env"})
            check("AIDP_AGENT=claude → CLAUDE.md", AE.memory_file(str(root)) == "CLAUDE.md")
            os.environ["AIDP_AGENT"] = " Claude-Code , deepseek-harness, openai-codex, claude "
            check("别名归一 + 去重保序", AE.detect_agents(str(root)) == ["claude", "dsh", "codex"])
            os.environ["AIDP_AGENT"] = " , "
            check("AIDP_AGENT 仅分隔符 → 回落标记目录", AE.detect_agents_detail(str(root))["source"] == "markers")
            os.environ["AIDP_AGENT"] = "claude"
            (root / "AGENTS.md").write_text(BODY, encoding="utf-8")
            (root / "CLAUDE.md").write_text("# 薄壳\n<!-- 说明 -->\n\n@AGENTS.md\n", encoding="utf-8")
            check("★ CLAUDE.md 为 @AGENTS.md 薄壳 → AGENTS.md（即便只有 claude）", AE.memory_file(str(root)) == "AGENTS.md")
            check("memory_file_path 拼完整路径", AE.memory_file_path(str(root)) == os.path.join(str(root), "AGENTS.md"))
            (root / "CLAUDE.md").write_text("@./AGENTS.md\n", encoding="utf-8")
            check("薄壳写法 @./AGENTS.md 同样识别", AE.is_thin_shell(str(root / "CLAUDE.md")))
            (root / "CLAUDE.md").write_text("@AGENTS.md\n额外正文\n", encoding="utf-8")
            check("导入行 + 正文 → 非薄壳 → CLAUDE.md", not AE.is_thin_shell(str(root / "CLAUDE.md"))
                  and AE.memory_file(str(root)) == "CLAUDE.md")
            (root / "CLAUDE.md").write_text("# 只有标题\n", encoding="utf-8")
            check("无导入行 → 非薄壳", not AE.is_thin_shell(str(root / "CLAUDE.md")))
            check("文件不存在 → 非薄壳", not AE.is_thin_shell(str(root / "nope.md")))
        finally:
            os.environ.pop("AIDP_AGENT", None)

        rc, out, _, _ = _run(ENV_PY, "detect", "--root", str(root))
        check("CLI detect → JSON agents/source", rc == 0 and out == {"agents": ["codex", "dsh", "claude"], "source": "markers"})
        rc, out, _, _ = _run(ENV_PY, "memory-file", "--root", str(root), AIDP_AGENT="claude")
        check("CLI memory-file → memory_file/agents/source",
              rc == 0 and out.get("memory_file") == "CLAUDE.md" and out.get("source") == "env")
        rc, _, _, _ = _run(ENV_PY)
        check("CLI 缺子命令 → 2", rc == 2)
        rc, _, stdout, _ = _run(ENV_PY, "--self-check")
        check("agent_env --self-check 通过", rc == 0 and "FAIL" not in stdout)
    finally:
        _rm(root)


# ── agent_sync：三种 Agent 装配 ───────────────────────────────────────────────
def test_sync_all_agents_link():
    print("【agent_sync：Claude Code + Codex + DeepSeek Harness 同时装配（link）】")
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root))
        check("首次装配 exit 0 且有动作", rc == 0 and out.get("drift") is True and out.get("applied") is True)
        check("未传 --agents → 按标记检测三种", sorted(out.get("agents", [])) == ["claude", "codex", "dsh"])

        # 记忆文件搬迁
        check("★ 正文搬进 AGENTS.md（一字不丢）", _read(root / "AGENTS.md") == BODY)
        check("★ CLAUDE.md 变为 @AGENTS.md 薄壳", _read(root / "CLAUDE.md") == AS.SHELL_BODY
              and AE.is_thin_shell(str(root / "CLAUDE.md")))
        check("搬迁后 memory_file → AGENTS.md", AE.memory_file(str(root)) == "AGENTS.md")

        # Claude Code
        sk = root / ".claude/skills/demo-skill"
        check("Claude：.claude/skills/demo-skill 为相对符号链接指向 .aidp",
              sk.is_symlink() and not os.path.isabs(os.readlink(sk)) and (sk / "SKILL.md").is_file())
        check("无 SKILL.md 的目录不装配", not (root / ".claude/skills/not-a-skill").exists())
        cmd = root / ".claude/commands/sprint-dev.md"
        check("Claude：.claude/commands/*.md 链接到 .aidp/commands", cmd.is_symlink() and "Sprint" in _read(cmd))
        check("Claude：README.md 不作为命令", not (root / ".claude/commands/README.md").exists())
        check("Claude：不生成命令包装 SKILL", not (root / ".claude/skills/sprint-dev").exists())
        st = json.loads(_read(root / ".claude/settings.json"))
        cmds = [h["command"] for g in st["hooks"]["Stop"] for h in g["hooks"]]
        check("Claude：settings.json Stop hook 用 $CLAUDE_PROJECT_DIR",
              cmds == [f'python3 "$CLAUDE_PROJECT_DIR/{AS.STOP_GUARD_REL}"'])

        # Codex
        check("Codex：公共 SKILL 在 .agents/skills", (root / ".agents/skills/demo-skill").is_symlink())
        codex_cmd = root / ".codex/aidp/skills/sprint-dev/SKILL.md"
        codex_text = _read(codex_cmd)
        check("Codex：每条命令生成独立 SKILL", codex_cmd.is_file())
        check("Codex：命令 SKILL 保留参数正文", "$ARGUMENTS" in codex_text)
        check("Codex：命令 SKILL frontmatter name 正确", codex_text.startswith("---\nname: sprint-dev\n"))
        check("Codex：显式调用策略在 agents/openai.yaml",
              "allow_implicit_invocation: false" in
              _read(root / ".codex/aidp/skills/sprint-dev/agents/openai.yaml"))
        check("Codex：README 不生成命令 SKILL", not (root / ".codex/aidp/skills/README").exists())
        check("公共 SKILL 不再暴露 aidp-cmd", not (root / ".agents/skills/aidp-cmd").exists())
        check("真源不再生成 aidp-cmd", not (root / ".aidp/skills/aidp-cmd").exists())
        hk = json.loads(_read(root / ".codex/hooks.json"))
        check("Codex：hooks.json Stop hook 带 --agent codex",
              hk["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("--agent codex"))
        check("Codex：config.toml 开启 codex_hooks", "[features]\ncodex_hooks = true" in _read(root / ".codex/config.toml"))

        # DeepSeek Harness
        check("DSH：命令直接生成到 .dsh/commands",
              (root / ".dsh/commands/sprint-dev.md").is_symlink()
              and "$ARGUMENTS" in _read(root / ".dsh/commands/sprint-dev.md"))
        check("DSH：README 不作为命令", not (root / ".dsh/commands/README.md").exists())
        check("DSH：不再生成专属 .dsh/skills", not (root / ".dsh/skills").exists())
        gi = _read(root / ".gitignore")
        check("★ 生成入口登记进 .gitignore 托管块",
              AS.GITIGNORE_BEGIN in gi and "/.claude/commands/sprint-dev.md" in gi
              and "/.claude/skills/demo-skill" in gi
              and "/.codex/aidp/skills/sprint-dev" in gi
              and "/.dsh/commands/sprint-dev.md" in gi)
        hk = json.loads(_read(root / ".dsh/hooks.json"))
        check("DSH：hooks.json Stop hook 带 --agent dsh",
              hk["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("--agent dsh"))

        # 幂等 + --check
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root))
        check("★ 二次运行幂等：零动作", rc == 0 and out.get("actions") == [] and out.get("drift") is False)
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--check")
        check("--check 一致 → exit 0", rc == 0 and out.get("applied") is False)

        # 漂移：删除一个入口 + 用户改坏 hooks 命令 + 新增命令
        os.unlink(root / ".claude/commands/sprint-dev.md")
        (root / ".aidp/commands/release.md").write_text("# /release — 发布\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--check")
        paths = {a["path"] for a in out.get("actions", [])}
        check("★ --check 检出漂移 → exit 1", rc == 1 and out.get("drift") is True)
        check("漂移明细含缺失入口与三 Agent 新增命令",
              ".claude/commands/sprint-dev.md" in paths
              and ".claude/commands/release.md" in paths
              and ".codex/aidp/skills/release/SKILL.md" in paths
              and ".dsh/commands/release.md" in paths)
        check("--check 不写盘", not (root / ".claude/commands/sprint-dev.md").exists()
              and not (root / ".codex/aidp/skills/release/SKILL.md").exists()
              and not (root / ".dsh/commands/release.md").exists())
        rc, _, _, err = _run(SYNC_PY, "--root", str(root), "--human")
        check("修复后再 --check 一致", _run(SYNC_PY, "--root", str(root), "--check")[0] == 0 and rc == 0)
        check("--human 输出动作摘要到 stderr", "link" in err or "write" in err)

        # 源删除 → 清理自生成入口；用户自有 SKILL 不动
        (root / ".agents/skills/my-own").mkdir()
        (root / ".agents/skills/my-own/SKILL.md").write_text("---\nname: my-own\n---\n", encoding="utf-8")
        (root / ".aidp/commands/release.md").unlink()
        shutil.rmtree(root / ".aidp/skills/demo-skill")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root))
        removes = {a["path"] for a in out.get("actions", []) if a["op"] == "remove"}
        check("★ 源已删 → 清理三 Agent 命令与公共 SKILL 入口",
              {".claude/commands/release.md", ".claude/skills/demo-skill", ".agents/skills/demo-skill",
               ".codex/aidp/skills/release", ".dsh/commands/release.md"} <= removes)
        check("★ 用户自有 SKILL 不被清理", (root / ".agents/skills/my-own/SKILL.md").is_file())
        gi = _read(root / ".gitignore")
        check("★ 源删除后 .gitignore 托管块同步移除、用户 SKILL 不被忽略",
              "/.claude/commands/release.md" not in gi and "my-own" not in gi)
    finally:
        _rm(root)


def test_memory_migration_shapes():
    print("【记忆文件形态切换：⛔ 绝不丢正文】")
    # 仅 Claude：正文在 CLAUDE.md → 不动
    root = _mkrepo(markers=(".claude",))
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude")
        check("仅 claude + 正文在 CLAUDE.md → 不写记忆文件",
              rc == 0 and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists())
        check("仅 claude → 不生成 .agents / .dsh", not (root / ".agents").exists() and not (root / ".dsh/skills").exists())
    finally:
        _rm(root)

    # 仅 Claude：正文已在 AGENTS.md，CLAUDE.md 缺失 → CLAUDE.md 做薄壳
    root = _mkrepo(markers=(".claude",), claude_md=None, agents_md=BODY)
    try:
        _run(SYNC_PY, "--root", str(root), "--agents", "claude")
        check("仅 claude + 正文在 AGENTS.md → 补 CLAUDE.md 薄壳、正文不复制",
              _read(root / "CLAUDE.md") == AS.SHELL_BODY and _read(root / "AGENTS.md") == BODY)
    finally:
        _rm(root)

    # 仅 Codex：正文在 CLAUDE.md → 搬到 AGENTS.md，CLAUDE.md 保留原样（不做薄壳，因为没有 claude）
    root = _mkrepo(markers=(".codex",))
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("★ 仅 codex + 正文在 CLAUDE.md → 复制到 AGENTS.md",
              rc == 0 and _read(root / "AGENTS.md") == BODY)
        check("仅 codex → CLAUDE.md 不改写（不丢原文件）", _read(root / "CLAUDE.md") == BODY)
        check("仅 codex → 不生成 .claude / .dsh 入口",
              not (root / ".claude/skills").exists() and not (root / ".dsh/commands").exists())
        codex_text = _read(root / ".codex/aidp/skills/sprint-dev/SKILL.md")
        check("仅 codex → 公共 SKILL + 可执行原生命令 SKILL",
              (root / ".agents/skills/demo-skill").exists()
              and codex_text.startswith("---\nname: sprint-dev\n")
              and "$ARGUMENTS" in codex_text
              and "allow_implicit_invocation: false" in
              _read(root / ".codex/aidp/skills/sprint-dev/agents/openai.yaml"))
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex", "--check")
        check("仅 codex 二次 --check 一致", rc == 0)
    finally:
        _rm(root)

    # 两份都有正文 + 并存 → 以 AGENTS.md 为准，CLAUDE.md 变薄壳
    root = _mkrepo(markers=(".claude", ".dsh"), agents_md="# AGENTS 正文\n")
    try:
        _run(SYNC_PY, "--root", str(root), "--agents", "claude,dsh")
        check("两份正文并存 → AGENTS.md 保持，CLAUDE.md 成薄壳",
              _read(root / "AGENTS.md") == "# AGENTS 正文\n" and _read(root / "CLAUDE.md") == AS.SHELL_BODY)
    finally:
        _rm(root)

    # 反向：先并存（CLAUDE.md 薄壳）→ 切回仅 claude：正文仍在 AGENTS.md，薄壳保持
    root = _mkrepo(markers=(".claude",), claude_md=AS.SHELL_BODY, agents_md=BODY)
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude")
        check("切回仅 claude：薄壳 + AGENTS.md 正文保持，无记忆文件写动作",
              rc == 0 and _read(root / "CLAUDE.md") == AS.SHELL_BODY and _read(root / "AGENTS.md") == BODY
              and not any(a["path"] in ("CLAUDE.md", "AGENTS.md") for a in out.get("actions", [])))
    finally:
        _rm(root)


def test_copy_mode_and_errors():
    print("【--mode copy / 参数错误 / hooks 合并】")
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        (root / ".aidp/skills/demo-skill/__pycache__").mkdir()
        (root / ".aidp/skills/demo-skill/__pycache__/x.pyc").write_bytes(b"\0")
        # 预置用户已有的 hooks / config，验证合并而非覆盖
        (root / ".claude/settings.json").write_text(json.dumps({
            "permissions": {"allow": ["Bash(git status)"]},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": f"python3 old/{AS.STOP_GUARD_REL}"}]}]}}),
            encoding="utf-8")
        (root / ".codex/config.toml").write_text('model = "demo"\n\n[features]\nother = 1\n', encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--mode", "copy")
        sk = root / ".claude/skills/demo-skill"
        check("copy 模式：目录为真实副本（非链接）", rc == 0 and sk.is_dir() and not sk.is_symlink()
              and (sk / "SKILL.md").is_file())
        check("copy 模式忽略 __pycache__", not (sk / "__pycache__").exists())
        cmd = root / ".claude/commands/sprint-dev.md"
        check("copy 模式：Claude 命令文件为副本", cmd.is_file() and not cmd.is_symlink())
        codex_cmd = root / ".codex/aidp/skills/sprint-dev/SKILL.md"
        check("copy 模式：Codex 命令 SKILL 为生成文件",
              codex_cmd.is_file() and not codex_cmd.is_symlink() and "$ARGUMENTS" in _read(codex_cmd))
        dsh_cmd = root / ".dsh/commands/sprint-dev.md"
        check("copy 模式：DSH 命令文件为真实副本",
              dsh_cmd.is_file() and not dsh_cmd.is_symlink()
              and _read(dsh_cmd) == _read(root / ".aidp/commands/sprint-dev.md"))
        st = json.loads(_read(root / ".claude/settings.json"))
        stop = st["hooks"]["Stop"]
        check("★ hooks 合并：保留用户其他配置，就地更新已有 stop guard 条目（不重复追加）",
              st["permissions"]["allow"] == ["Bash(git status)"] and len(stop) == 1
              and stop[0]["hooks"][0]["command"] == f'python3 "$CLAUDE_PROJECT_DIR/{AS.STOP_GUARD_REL}"')
        toml = _read(root / ".codex/config.toml")
        check("config.toml 已有 [features] → 插入 codex_hooks，保留原内容",
              'model = "demo"' in toml and "other = 1" in toml and toml.count("[features]") == 1
              and "codex_hooks = true" in toml)
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--mode", "copy", "--check")
        check("copy 模式幂等", rc == 0 and out.get("actions") == [])
        (root / ".aidp/skills/demo-skill/SKILL.md").write_text("---\nname: demo-skill\ndescription: 改了\n---\n",
                                                               encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--mode", "copy", "--check")
        check("★ copy 模式源内容变更 → --check 漂移 exit 1", rc == 1
              and any(a["path"] == ".claude/skills/demo-skill" for a in out.get("actions", [])))
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--check")
        check("copy → link 切换同样视为漂移", rc == 1)
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude",))
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,cursor")
        check("未知 Agent → exit 2 + error", rc == 2 and "cursor" in out.get("error", ""))
        (root / ".claude/settings.json").write_text("{not json", encoding="utf-8")
        cp = subprocess.run([sys.executable, SYNC_PY, "--root", str(root), "--agents", "claude"],
                            capture_output=True, text=True, env=_clean_env(), timeout=60)
        check("★ settings.json 非法 JSON → 拒绝覆盖（非零退出、原文件不变）",
              cp.returncode != 0 and _read(root / ".claude/settings.json") == "{not json")
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude",), hook=False)
    try:
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root))
        check("无 stop guard 脚本 → 不写 hooks", rc == 0 and not (root / ".claude/settings.json").exists())
    finally:
        _rm(root)

    empty = Path(tempfile.mkdtemp())
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(empty))
        check("无 .aidp/ → exit 2", rc == 2 and "error" in out)
    finally:
        shutil.rmtree(empty, ignore_errors=True)

    # AIDP_AGENT 环境变量驱动检测
    root = _mkrepo()
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), AIDP_AGENT="dsh")
        dsh_cmd = root / ".dsh/commands/sprint-dev.md"
        check("AIDP_AGENT=dsh → 公共 SKILL + 可执行原生命令", rc == 0 and out.get("agents") == ["dsh"]
              and (root / ".agents/skills/demo-skill").exists()
              and dsh_cmd.is_symlink()
              and "$ARGUMENTS" in _read(dsh_cmd)
              and not (root / ".dsh/skills").exists()
              and not (root / ".claude/skills").exists()
              and not (root / ".codex/aidp/skills").exists())
    finally:
        _rm(root)

    # Agent 切换：清理自生成命令入口，保留 Codex 命令目录内用户内容
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex,dsh")
        check("切换前已生成 Codex/DSH 原生命令入口",
              (root / ".codex/aidp/skills/sprint-dev/SKILL.md").is_file()
              and (root / ".dsh/commands/sprint-dev.md").exists())
        own = root / ".codex/aidp/skills/my-own/SKILL.md"
        own.parent.mkdir(parents=True, exist_ok=True)
        own.write_text("---\nname: my-own\ndescription: user\n---\n", encoding="utf-8")
        _run(SYNC_PY, "--root", str(root), "--agents", "claude")
        check("切换为 Claude-only → 清理 DSH 生成命令",
              not (root / ".dsh/commands/sprint-dev.md").exists())
        check("切换为 Claude-only → 清理 Codex 生成命令",
              not (root / ".codex/aidp/skills/sprint-dev").exists())
        check("切换 Agent → 保留 Codex 命令目录内用户自有内容", own.is_file())
    finally:
        _rm(root)

    # 命令与 SKILL 同名 → 拒绝装配（命令与 SKILL 在源头必须分离）
    root = _mkrepo(markers=(".codex",))
    try:
        (root / ".aidp/skills/sprint-dev").mkdir(parents=True)
        (root / ".aidp/skills/sprint-dev/SKILL.md").write_text("---\nname: sprint-dev\n---\n", encoding="utf-8")
        p = subprocess.run([sys.executable, SYNC_PY, "--root", str(root)], capture_output=True, text=True)
        check("★ 命令与 SKILL 同名 → 非 0 退出并提示冲突", p.returncode != 0 and "冲突" in (p.stderr + p.stdout))
        check("冲突时不生成任何原生命令入口",
              not (root / ".codex/aidp/skills/sprint-dev").exists()
              and not (root / ".dsh/commands/sprint-dev.md").exists())
    finally:
        _rm(root)

    # 插件：Claude 项目插件 / Codex 项目级 skills + MCP / DSH 共享 skills + MCP
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        pl = _add_browser_plugin(root)
        (root / ".codex/config.toml").write_text(
            'model = "user-model"\n\n[mcp_servers.user-browser]\ncommand = "user-mcp"\n', encoding="utf-8")
        (root / ".dsh/mcp.json").write_text(json.dumps({
            "mcpServers": {"user-browser": {"command": "user-mcp", "args": ["--keep"]}}
        }), encoding="utf-8")

        # 旧版 Codex marketplace 包装：AIDP 生成项应清理，用户同目录内容必须保留
        legacy = root / ".agents/plugins/chrome-devtools-mcp"
        legacy.mkdir(parents=True)
        (legacy / AS.GENERATED_FILE).write_text("", encoding="utf-8")
        (legacy / "plugin.json").write_text('{"name":"chrome-devtools-mcp"}\n', encoding="utf-8")
        (root / ".agents/plugins/marketplace.json").write_text(
            '{"name":"local-repo","plugins":[]}\n', encoding="utf-8")
        (root / ".agents/plugins/.aidp-generated").write_text("marketplace\n", encoding="utf-8")
        user_plugin = root / ".agents/plugins/user-owned/note.txt"
        user_plugin.parent.mkdir(parents=True)
        user_plugin.write_text("keep me\n", encoding="utf-8")

        rc, out, _, _ = _run(SYNC_PY, "--root", str(root))
        st = json.loads(_read(root / ".claude/settings.json"))
        check("插件·Claude：完整项目级插件 + marketplace 启用",
              (root / ".claude/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").is_file()
              and st["enabledPlugins"].get("chrome-devtools-mcp@chrome-devtools-plugins") is True)
        codex_skill = root / ".codex/skills/chrome-devtools-mcp/skills/chrome-devtools"
        dsh_skill = root / ".agents/skills/chrome-devtools"
        check("插件·Codex：项目级技能集合", (codex_skill / "SKILL.md").is_file())
        check("插件·Codex：不生成仓库 marketplace", not (root / ".agents/plugins/marketplace.json").exists())
        config = _read(root / ".codex/config.toml")
        check("插件·Codex：config.toml 注册 MCP server",
              "[mcp_servers.chrome-devtools]" in config
              and 'args = ["chrome-devtools-mcp@1.6.0"]' in config)
        check("插件·Codex：同步保留用户 config 与 MCP server",
              'model = "user-model"' in config
              and "[mcp_servers.user-browser]" in config
              and 'command = "user-mcp"' in config)
        check("插件·DSH：插件 SKILL 直接进入 .agents/skills",
              (dsh_skill / "SKILL.md").is_file() and not (root / ".dsh/skills").exists())
        dsh_mcp = json.loads(_read(root / ".dsh/mcp.json"))
        check("插件·DSH：新增 chrome-devtools 且保留用户 server",
              "chrome-devtools" in dsh_mcp.get("mcpServers", {})
              and dsh_mcp.get("mcpServers", {}).get("user-browser", {}).get("command") == "user-mcp")
        check("插件·旧 Codex marketplace 包装完整清理、用户内容保留",
              not legacy.exists()
              and not (root / ".agents/plugins/marketplace.json").exists()
              and not (root / ".agents/plugins/.aidp-generated").exists()
              and user_plugin.is_file())
        check("插件·Codex+DSH：两入口解析到同一真源",
              codex_skill.resolve() == (pl / "skills/chrome-devtools").resolve()
              and dsh_skill.resolve() == (pl / "skills/chrome-devtools").resolve())
        gi = _read(root / ".gitignore")
        check("插件生成物登记 .gitignore",
              "/.claude/plugins/chrome-devtools-mcp" in gi
              and "/.codex/skills/chrome-devtools-mcp" in gi
              and "/.agents/skills/chrome-devtools" in gi)
        check("插件装配幂等", _run(SYNC_PY, "--root", str(root), "--check")[0] == 0)

        # 切换为 Codex-only：清理 DSH 的 AIDP server/技能，保留用户 server 与 Codex 入口
        _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        dsh_after_switch = json.loads(_read(root / ".dsh/mcp.json"))
        check("插件·切换 Codex-only：清理 DSH AIDP 入口、保留用户 server 与 Codex 入口",
              not dsh_skill.exists()
              and "chrome-devtools" not in dsh_after_switch.get("mcpServers", {})
              and dsh_after_switch.get("mcpServers", {}).get("user-browser", {}).get("command") == "user-mcp"
              and (codex_skill / "SKILL.md").is_file())

        # 用户自有命令不能因切换 Agent 被清理
        (root / ".dsh/commands").mkdir(parents=True, exist_ok=True)
        (root / ".dsh/commands/my-command.md").write_text("# user\n", encoding="utf-8")
        _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("切换 Agent 不删除用户自有 DSH 命令", (root / ".dsh/commands/my-command.md").is_file())

        shutil.rmtree(pl)
        _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        config_after_delete = _read(root / ".codex/config.toml")
        dsh_after_delete = json.loads(_read(root / ".dsh/mcp.json"))
        check("插件源删除 → 只清理 AIDP 入口/MCP，用户 Codex/DSH/插件内容保留",
              not (root / ".claude/plugins/chrome-devtools-mcp").exists()
              and not (root / ".codex/skills/chrome-devtools-mcp").exists()
              and "[mcp_servers.chrome-devtools]" not in config_after_delete
              and "[mcp_servers.user-browser]" in config_after_delete
              and 'model = "user-model"' in config_after_delete
              and dsh_after_delete.get("mcpServers", {}).get("user-browser", {}).get("command") == "user-mcp"
              and "chrome-devtools" not in dsh_after_delete.get("mcpServers", {})
              and user_plugin.is_file())
    finally:
        _rm(root)

    # 插件 copy 模式：三端均为内容完整的真实副本
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        pl = _add_browser_plugin(root)
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--mode", "copy")
        claude_plugin = root / ".claude/plugins/chrome-devtools-mcp"
        codex_plugin_skill = root / ".codex/skills/chrome-devtools-mcp/skills/chrome-devtools"
        dsh_plugin_skill = root / ".agents/skills/chrome-devtools"
        source_skill = pl / "skills/chrome-devtools"
        check("插件 copy·Claude：完整项目插件为真实副本",
              rc == 0 and claude_plugin.is_dir() and not claude_plugin.is_symlink()
              and not (claude_plugin / ".claude-plugin/plugin.json").is_symlink()
              and _read(claude_plugin / ".claude-plugin/plugin.json")
              == _read(pl / ".claude-plugin/plugin.json"))
        check("插件 copy·Codex：skills 集合为内容完整的真实副本",
              codex_plugin_skill.is_dir() and not codex_plugin_skill.is_symlink()
              and not (codex_plugin_skill / "SKILL.md").is_symlink()
              and _read(codex_plugin_skill / "SKILL.md") == _read(source_skill / "SKILL.md")
              and _read(codex_plugin_skill / "references/usage.md")
              == _read(source_skill / "references/usage.md"))
        check("插件 copy·DSH：.agents/skills 为内容完整的真实副本",
              dsh_plugin_skill.is_dir() and not dsh_plugin_skill.is_symlink()
              and not (dsh_plugin_skill / "SKILL.md").is_symlink()
              and _read(dsh_plugin_skill / "SKILL.md") == _read(source_skill / "SKILL.md")
              and _read(dsh_plugin_skill / "references/usage.md")
              == _read(source_skill / "references/usage.md"))
    finally:
        _rm(root)

    # 插件 SKILL 与公共 SKILL 同名 → fail closed
    root = _mkrepo(markers=(".dsh",))
    try:
        pl = root / ".aidp/plugins/demo-plugin"
        (pl / ".claude-plugin").mkdir(parents=True)
        (pl / ".claude-plugin/plugin.json").write_text('{"name":"demo-plugin"}\n', encoding="utf-8")
        (pl / "skills/demo-skill").mkdir(parents=True)
        (pl / "skills/demo-skill/SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")
        p = subprocess.run([sys.executable, SYNC_PY, "--root", str(root)], capture_output=True, text=True)
        check("插件 SKILL 与公共 SKILL 重名 → 非零退出并提示冲突",
              p.returncode != 0 and "冲突" in (p.stdout + p.stderr))
    finally:
        _rm(root)

    rc, out, _, _ = _run(SYNC_PY, "--self-check")
    check("agent_sync --self-check 通过", rc == 0 and out.get("self_check") == "pass")


def main():
    test_agent_env()
    test_sync_all_agents_link()
    test_memory_migration_shapes()
    test_copy_mode_and_errors()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
