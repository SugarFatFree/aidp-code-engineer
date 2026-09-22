#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agent_env.py + agent_sync.py 多 Agent 装配单测（stdlib only，临时 git 仓库）。

覆盖：
  · agent_env：AIDP_AGENT > 标记目录 > 默认；别名归一；memory-file 判定（薄壳识别）；CLI detect / memory-file / --self-check
  · agent_sync：Claude Code / Codex / DeepSeek Harness 三种入口装配（SKILL 目录、命令入口 / 包装 SKILL、Stop hook）
  · 记忆文件搬迁：仅 Claude → CLAUDE.md 正文；并存 → 正文进 AGENTS.md、CLAUDE.md 成 @AGENTS.md 薄壳；⛔ 不丢正文
  · 幂等（二次运行零动作）、--check 漂移 exit 1 且不写盘、源删除后清理自生成入口但不碰用户自有 SKILL
  · managed-copy、未知 Agent / 无运行包 → exit 2、非法 hooks JSON 拒绝覆盖、--self-check

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
    if ("--root" in args and "AIDP_HOME" not in env_extra
            and Path(script).resolve() == Path(SYNC_PY).resolve()):
        project = Path(args[args.index("--root") + 1]).resolve()
        env_extra.update(AIDP_PROJECT_ROOT=str(project), AIDP_HOME=str(project / ".aidp"))
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
    (root / ".aidp/plugins").mkdir()
    (root / ".aidp/scripts").mkdir()
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


def _move_source_into_runtime(root, runtime_rel):
    source = root / ".aidp"
    runtime = root / runtime_rel
    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(runtime))
    scripts = runtime / "scripts"
    scripts.mkdir(exist_ok=True)
    for name in ("agent_sync.py", "agent_env.py", "aidp_runtime.py"):
        candidate = Path(SCRIPTS) / name
        if candidate.is_file():
            shutil.copy2(candidate, scripts / name)
    return runtime


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
def test_sync_all_agents_managed_copy():
    print("【agent_sync：Claude Code + Codex + DeepSeek Harness 同时装配（managed-copy）】")
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
        check("Claude：.claude/skills/demo-skill 为 managed-copy",
              sk.is_dir() and not sk.is_symlink() and (sk / "SKILL.md").is_file())
        check("无 SKILL.md 的目录不装配", not (root / ".claude/skills/not-a-skill").exists())
        cmd = root / ".claude/commands/sprint-dev.md"
        check("Claude：.claude/commands/*.md 为 managed-copy",
              cmd.is_file() and not cmd.is_symlink() and "Sprint" in _read(cmd))
        check("Claude：README.md 不作为命令", not (root / ".claude/commands/README.md").exists())
        check("Claude：不生成命令包装 SKILL", not (root / ".claude/skills/sprint-dev").exists())
        st = json.loads(_read(root / ".claude/settings.json"))
        cmds = [h["command"] for g in st["hooks"]["Stop"] for h in g["hooks"]]
        check("Claude：settings.json Stop hook 用 $CLAUDE_PROJECT_DIR",
              cmds == ['python3 "$CLAUDE_PROJECT_DIR/.claude/aidp/hooks/autopilot-stop-guard.py"'])

        # Codex
        shared_skill = root / ".agents/skills/demo-skill"
        check("Codex：公共 SKILL 在 .agents/skills 且为 managed-copy",
              shared_skill.is_dir() and not shared_skill.is_symlink())
        codex_cmd = root / ".codex/skills/aidp/sprint-dev/SKILL.md"
        codex_text = _read(codex_cmd)
        check("Codex：每条命令生成独立 SKILL", codex_cmd.is_file())
        check("Codex：命令 SKILL 保留参数正文", "$ARGUMENTS" in codex_text)
        check("Codex：命令 SKILL frontmatter name 正确", codex_text.startswith("---\nname: sprint-dev\n"))
        check("Codex：显式调用策略在 agents/openai.yaml",
              "allow_implicit_invocation: false" in
              _read(root / ".codex/skills/aidp/sprint-dev/agents/openai.yaml"))
        check("Codex：README 不生成命令 SKILL", not (root / ".codex/skills/aidp/README").exists())
        check("公共 SKILL 不再暴露 aidp-cmd", not (root / ".agents/skills/aidp-cmd").exists())
        check("真源不再生成 aidp-cmd", not (root / ".aidp/skills/aidp-cmd").exists())
        hk = json.loads(_read(root / ".codex/hooks.json"))
        check("Codex：hooks.json Stop hook 带 --agent codex",
              hk["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("--agent codex"))
        check("Codex：config.toml 开启 codex_hooks", "[features]\ncodex_hooks = true" in _read(root / ".codex/config.toml"))

        # DeepSeek Harness
        dsh_command = root / ".dsh/commands/sprint-dev.md"
        check("DSH：命令以 managed-copy 生成到 .dsh/commands",
              dsh_command.is_file() and not dsh_command.is_symlink()
              and "$ARGUMENTS" in _read(dsh_command))
        check("DSH：README 不作为命令", not (root / ".dsh/commands/README.md").exists())
        check("DSH：不再生成专属 .dsh/skills", not (root / ".dsh/skills").exists())
        gi = _read(root / ".gitignore")
        check("★ 生成入口登记进 .gitignore 托管块",
              AS.GITIGNORE_BEGIN in gi and "/.claude/commands/sprint-dev.md" in gi
              and "/.claude/skills/demo-skill" in gi
              and "/.codex/skills/aidp/sprint-dev" in gi
              and "/.dsh/commands/sprint-dev.md" in gi)
        hk = json.loads(_read(root / ".dsh/hooks.json"))
        check("DSH：hooks.json Stop hook 带 --agent dsh",
              hk["hooks"]["Stop"][0]["hooks"][0]["command"].endswith("--agent dsh"))

        # 幂等 + --check
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root))
        check("★ 二次运行幂等：仅保留模式归一化信息", rc == 0
              and not any(action.get("op") not in (None, "normalized")
                          for action in out.get("actions", []))
              and out.get("drift") is False)
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
              and ".codex/skills/aidp/release/SKILL.md" in paths
              and ".dsh/commands/release.md" in paths)
        check("--check 不写盘", not (root / ".claude/commands/sprint-dev.md").exists()
              and not (root / ".codex/skills/aidp/release/SKILL.md").exists()
              and not (root / ".dsh/commands/release.md").exists())
        rc, _, _, err = _run(SYNC_PY, "--root", str(root), "--human")
        check("修复后再 --check 一致", _run(SYNC_PY, "--root", str(root), "--check")[0] == 0 and rc == 0)
        check("--human 输出动作摘要到 stderr", "copy" in err or "write" in err or "normalized" in err)

        # 源删除 → 清理自生成入口；用户自有 SKILL 不动
        (root / ".agents/skills/my-own").mkdir()
        (root / ".agents/skills/my-own/SKILL.md").write_text("---\nname: my-own\n---\n", encoding="utf-8")
        (root / ".aidp/commands/release.md").unlink()
        shutil.rmtree(root / ".aidp/skills/demo-skill")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root))
        removes = {a["path"] for a in out.get("actions", []) if a["op"] == "remove"}
        check("★ 源已删 → 清理三 Agent 命令与公共 SKILL 入口",
              {".claude/commands/release.md", ".claude/skills/demo-skill", ".agents/skills/demo-skill",
               ".codex/skills/aidp/release", ".dsh/commands/release.md"} <= removes)
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
        codex_text = _read(root / ".codex/skills/aidp/sprint-dev/SKILL.md")
        check("仅 codex → 公共 SKILL + 可执行原生命令 SKILL",
              (root / ".agents/skills/demo-skill").exists()
              and codex_text.startswith("---\nname: sprint-dev\n")
              and "$ARGUMENTS" in codex_text
              and "allow_implicit_invocation: false" in
              _read(root / ".codex/skills/aidp/sprint-dev/agents/openai.yaml"))
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
        codex_cmd = root / ".codex/skills/aidp/sprint-dev/SKILL.md"
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
              and stop[0]["hooks"][0]["command"]
              == 'python3 "$CLAUDE_PROJECT_DIR/.claude/aidp/hooks/autopilot-stop-guard.py"')
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
        _run(SYNC_PY, "--root", str(root), "--mode", "copy")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--mode", "link", "--check")
        check("显式 link 参数规范化为 managed-copy 且不制造模式漂移",
              rc == 0 and out.get("drift") is False
              and any(action.get("action") == "normalized"
                      and action.get("from") == "link"
                      and action.get("to") == "managed-copy"
                      for action in out.get("actions", [])))
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
        check("无任何 AIDP 运行包 → exit 2", rc == 2 and "error" in out)
    finally:
        shutil.rmtree(empty, ignore_errors=True)

    # AIDP_AGENT 环境变量驱动检测
    root = _mkrepo()
    try:
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), AIDP_AGENT="dsh")
        dsh_cmd = root / ".dsh/commands/sprint-dev.md"
        check("AIDP_AGENT=dsh → 公共 SKILL + 可执行原生命令", rc == 0 and out.get("agents") == ["dsh"]
              and (root / ".agents/skills/demo-skill").exists()
              and dsh_cmd.is_file() and not dsh_cmd.is_symlink()
              and "$ARGUMENTS" in _read(dsh_cmd)
              and not (root / ".dsh/skills").exists()
              and not (root / ".claude/skills").exists()
              and not (root / ".codex/skills/aidp").exists())
    finally:
        _rm(root)

    # Agent 切换：清理自生成命令入口，保留 Codex 命令目录内用户内容
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex,dsh")
        check("切换前已生成 Codex/DSH 原生命令入口",
              (root / ".codex/skills/aidp/sprint-dev/SKILL.md").is_file()
              and (root / ".dsh/commands/sprint-dev.md").exists())
        own = root / ".codex/skills/aidp/my-own/SKILL.md"
        own.parent.mkdir(parents=True, exist_ok=True)
        own.write_text("---\nname: my-own\ndescription: user\n---\n", encoding="utf-8")
        _run(SYNC_PY, "--root", str(root), "--agents", "claude")
        check("切换为 Claude-only → 清理 DSH 生成命令",
              not (root / ".dsh/commands/sprint-dev.md").exists())
        check("切换为 Claude-only → 清理 Codex 生成命令",
              not (root / ".codex/skills/aidp/sprint-dev").exists())
        check("切换 Agent → 保留 Codex 命令目录内用户自有内容", own.is_file())
    finally:
        _rm(root)

    # 命令与 SKILL 同名 → 拒绝装配（命令与 SKILL 在源头必须分离）
    root = _mkrepo(markers=(".codex",))
    try:
        (root / ".aidp/skills/sprint-dev").mkdir(parents=True)
        (root / ".aidp/skills/sprint-dev/SKILL.md").write_text("---\nname: sprint-dev\n---\n", encoding="utf-8")
        rc, out, stdout, stderr = _run(SYNC_PY, "--root", str(root))
        check("★ 命令与 SKILL 同名 → 非 0 退出并提示冲突",
              rc != 0 and "冲突" in (out.get("error", "") + stdout + stderr))
        check("冲突时不生成任何原生命令入口",
              not (root / ".codex/skills/aidp/sprint-dev").exists()
              and not (root / ".dsh/commands/sprint-dev.md").exists())
    finally:
        _rm(root)

    # 旧 Codex 命令根若是外部 symlink，保守保留且绝不遍历目标
    root = _mkrepo(markers=(".codex",))
    external = Path(tempfile.mkdtemp())
    try:
        generated = external / "generated-command"
        generated.mkdir()
        (generated / AS.GENERATED_FILE).write_text("native-command\n", encoding="utf-8")
        sentinel = external / "sentinel.txt"
        sentinel.write_text("outside\n", encoding="utf-8")
        legacy_parent = root / ".codex/aidp"
        legacy_parent.mkdir(parents=True)
        (legacy_parent / "skills").symlink_to(external, target_is_directory=True)
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("旧 Codex 命令根为 symlink → 不遍历、不删除外部内容",
              rc == 0 and (legacy_parent / "skills").is_symlink()
              and generated.is_dir() and _read(sentinel) == "outside\n")
    finally:
        _rm(root)
        shutil.rmtree(external, ignore_errors=True)

    # 旧根的祖先为 symlink 时，同样不得跟随到外部
    root = _mkrepo(markers=(".codex",))
    external = Path(tempfile.mkdtemp())
    try:
        generated = external / "skills/generated-command"
        generated.mkdir(parents=True)
        (generated / AS.GENERATED_FILE).write_text("native-command\n", encoding="utf-8")
        sentinel = external / "sentinel.txt"
        sentinel.write_text("outside ancestor\n", encoding="utf-8")
        (root / ".codex/aidp").symlink_to(external, target_is_directory=True)
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("旧 Codex 根祖先为 symlink → 不跟随、不删除外部内容",
              rc == 0 and (root / ".codex/aidp").is_symlink()
              and generated.is_dir() and _read(sentinel) == "outside ancestor\n")
    finally:
        _rm(root)
        shutil.rmtree(external, ignore_errors=True)

    # 通用 _prune 对词法位于 root 外的路径拒绝操作
    root = _mkrepo(markers=(".codex",))
    external = Path(tempfile.mkdtemp())
    try:
        generated = external / "generated-command"
        generated.mkdir()
        (generated / AS.GENERATED_FILE).write_text("native-command\n", encoding="utf-8")
        plan = AS.Plan(root, True, "link")
        try:
            AS._prune(plan, external, set())
            no_error = True
        except ValueError:
            no_error = False
        check("_prune 词法越出 root → 外部目录保持且无写动作",
              no_error and generated.is_dir()
              and not any(action.get("op") not in (None, "normalized") for action in plan.actions))
    finally:
        _rm(root)
        shutil.rmtree(external, ignore_errors=True)

    # 新 Codex 命令 namespace 必须位于真实目录，symlink/文件均原子拒绝
    root = _mkrepo(markers=(".claude", ".codex"))
    external = Path(tempfile.mkdtemp())
    try:
        sentinel = external / "sentinel.txt"
        sentinel.write_text("outside\n", encoding="utf-8")
        namespace_parent = root / ".codex/skills"
        namespace_parent.mkdir(parents=True)
        (namespace_parent / "aidp").symlink_to(external, target_is_directory=True)
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Codex 命令 namespace 为外部 symlink → exit2 且内外零副作用",
              rc == 2 and "真实目录" in out.get("error", "")
              and _read(sentinel) == "outside\n" and list(external.iterdir()) == [sentinel]
              and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists()
              and not (root / ".codex/hooks.json").exists()
              and not (root / ".claude/commands").exists())
    finally:
        _rm(root)
        shutil.rmtree(external, ignore_errors=True)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        namespace = root / ".codex/skills/aidp"
        namespace.parent.mkdir(parents=True)
        namespace.write_text("user file\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Codex 命令 namespace 为普通文件 → exit2 且仓库零副作用",
              rc == 2 and "真实目录" in out.get("error", "")
              and _read(namespace) == "user file\n" and _read(root / "CLAUDE.md") == BODY
              and not (root / "AGENTS.md").exists() and not (root / ".codex/hooks.json").exists()
              and not (root / ".claude/commands").exists())
    finally:
        _rm(root)

    # 所有适配 namespace 的自身或祖先 symlink 均须在任何写入前 fail closed
    namespace_cases = (
        (".claude", "claude", False),
        (".claude/skills", "claude", False),
        (".claude/commands", "claude", False),
        (".claude/plugins", "claude", True),
        (".codex", "codex", False),
        (".codex/skills", "codex", False),
        (".dsh", "dsh", False),
        (".dsh/commands", "dsh", False),
        (".agents", "codex", False),
        (".agents/skills", "codex", False),
        (".agents/skills/chrome-devtools-mcp", "codex", True),
        (".agents/plugins", "codex", False),
    )
    for rel, agents_arg, needs_plugin in namespace_cases:
        root = _mkrepo()
        external = Path(tempfile.mkdtemp())
        try:
            if needs_plugin:
                _add_browser_plugin(root)
            sentinel = external / "sentinel.txt"
            sentinel.write_text(f"outside {rel}\n", encoding="utf-8")
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            target.symlink_to(external, target_is_directory=True)
            external_before = sorted(path.name for path in external.iterdir())
            rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", agents_arg)
            check(f"适配 namespace symlink（{rel}）→ exit2 且内外零副作用",
                  rc == 2 and "真实目录" in out.get("error", "")
                  and target.is_symlink()
                  and sorted(path.name for path in external.iterdir()) == external_before
                  and _read(sentinel) == f"outside {rel}\n"
                  and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists()
                  and not (root / ".gitignore").exists())
        finally:
            _rm(root)
            shutil.rmtree(external, ignore_errors=True)

    # 原生命令目标已有用户内容 → fail closed，不覆盖
    root = _mkrepo(markers=(".codex",))
    try:
        user_skill = root / ".codex/skills/aidp/sprint-dev/SKILL.md"
        user_skill.parent.mkdir(parents=True)
        user_skill.write_text("---\nname: user-sprint-dev\ndescription: keep\n---\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("Codex 同名命令目标无生成标记 → fail closed 且用户内容保持",
              rc == 2 and "用户" in out.get("error", "")
              and "user-sprint-dev" in _read(user_skill))
    finally:
        _rm(root)

    root = _mkrepo(markers=(".dsh",))
    try:
        user_command = root / ".dsh/commands/sprint-dev.md"
        user_command.parent.mkdir(parents=True)
        user_command.write_text("# user command\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "dsh")
        check("DSH 同名命令目标无生成账本 → fail closed 且用户内容保持",
              rc == 2 and "用户" in out.get("error", "")
              and _read(user_command) == "# user command\n")
    finally:
        _rm(root)

    # 插件：Claude 项目插件 / Codex 项目级 skills + MCP / DSH 共享 skills + MCP
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        pl = _add_browser_plugin(root)
        (root / ".claude/settings.json").write_text(json.dumps({
            "extraKnownMarketplaces": {"user-market": {"source": {"source": "directory", "path": "./user"}}},
            "enabledPlugins": {"user-plugin@user-market": True},
        }), encoding="utf-8")
        (root / ".codex/config.toml").write_text(
            'model = "user-model"\n\n[mcp_servers.user-browser]\ncommand = "user-mcp"\n\n'
            '[plugins."user-plugin@local-repo"]\nenabled = true\n\n'
            '[plugins."chrome-devtools-mcp@local-repo"]\nenabled = true\n', encoding="utf-8")
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
        shared_skill = root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools"
        check("插件·Codex/DSH：从 .agents/skills 发现共享嵌套技能集合",
              (shared_skill / "SKILL.md").is_file()
              and not (root / ".codex/skills/chrome-devtools-mcp").exists())
        check("插件·Codex：不生成仓库 marketplace", not (root / ".agents/plugins/marketplace.json").exists())
        config = _read(root / ".codex/config.toml")
        check("插件·Codex：config.toml 注册 MCP server",
              "[mcp_servers.chrome-devtools]" in config
              and 'args = ["chrome-devtools-mcp@1.6.0"]' in config)
        check("插件·Codex：同步保留用户 config、MCP server 与 local-repo 插件项",
              'model = "user-model"' in config
              and "[mcp_servers.user-browser]" in config
              and 'command = "user-mcp"' in config
              and '[plugins."user-plugin@local-repo"]' in config
              and '[plugins."chrome-devtools-mcp@local-repo"]' not in config)
        check("插件·共享 SKILL 以 namespaced managed-copy 进入 .agents/skills",
              (shared_skill / "SKILL.md").is_file() and not shared_skill.is_symlink()
              and not (root / ".agents/skills/chrome-devtools").exists()
              and not (root / ".dsh/skills").exists())
        dsh_mcp = json.loads(_read(root / ".dsh/mcp.json"))
        check("插件·DSH：新增 chrome-devtools 且保留用户 server",
              "chrome-devtools" in dsh_mcp.get("mcpServers", {})
              and dsh_mcp.get("mcpServers", {}).get("user-browser", {}).get("command") == "user-mcp")
        check("插件·旧 Codex marketplace 包装完整清理、用户内容保留",
              not legacy.exists()
              and not (root / ".agents/plugins/marketplace.json").exists()
              and not (root / ".agents/plugins/.aidp-generated").exists()
              and user_plugin.is_file())
        source_skill = pl / "skills/chrome-devtools"
        check("插件·Codex+DSH：共享入口与 runtime plugin 同源且全实体",
              not shared_skill.is_symlink()
              and not (shared_skill / "SKILL.md").is_symlink()
              and not (shared_skill / "references/usage.md").is_symlink()
              and _read(shared_skill / "SKILL.md") == _read(source_skill / "SKILL.md")
              and _read(shared_skill / "references/usage.md") == _read(source_skill / "references/usage.md"))
        gi = _read(root / ".gitignore")
        check("插件生成物登记 .gitignore",
              "/.claude/plugins/chrome-devtools-mcp" in gi
              and "/.codex/skills/chrome-devtools-mcp" not in gi
              and "/.agents/skills/chrome-devtools-mcp" in gi)
        check("插件装配幂等", _run(SYNC_PY, "--root", str(root), "--check")[0] == 0)

        # 切换为 Codex-only：清理 DSH MCP，保留用户 server 与共享嵌套 SKILL
        _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        dsh_after_switch = json.loads(_read(root / ".dsh/mcp.json"))
        claude_after_switch = json.loads(_read(root / ".claude/settings.json"))
        check("插件·切换 Codex-only：清理 Claude/DSH 配置并保留共享 SKILL",
              (shared_skill / "SKILL.md").is_file()
              and not (root / ".codex/skills/chrome-devtools-mcp").exists()
              and "chrome-devtools" not in dsh_after_switch.get("mcpServers", {})
              and dsh_after_switch.get("mcpServers", {}).get("user-browser", {}).get("command") == "user-mcp"
              and "chrome-devtools-plugins" not in claude_after_switch.get("extraKnownMarketplaces", {})
              and claude_after_switch.get("extraKnownMarketplaces", {}).get("user-market")
              and claude_after_switch.get("enabledPlugins", {}).get("user-plugin@user-market") is True
              and (shared_skill / "SKILL.md").is_file())

        # 用户自有命令不能因切换 Agent 被清理
        (root / ".dsh/commands").mkdir(parents=True, exist_ok=True)
        (root / ".dsh/commands/my-command.md").write_text("# user\n", encoding="utf-8")
        _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("切换 Agent 不删除用户自有 DSH 命令", (root / ".dsh/commands/my-command.md").is_file())

        shutil.rmtree(pl)
        _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        config_after_delete = _read(root / ".codex/config.toml")
        dsh_after_delete = json.loads(_read(root / ".dsh/mcp.json"))
        claude_after_delete = json.loads(_read(root / ".claude/settings.json"))
        check("插件源删除 → 只清理 AIDP 入口/MCP/settings，用户配置与插件内容保留",
              not (root / ".claude/plugins/chrome-devtools-mcp").exists()
              and not (root / ".codex/skills/chrome-devtools-mcp").exists()
              and not shared_skill.exists()
              and "[mcp_servers.chrome-devtools]" not in config_after_delete
              and "[mcp_servers.user-browser]" in config_after_delete
              and '[plugins."user-plugin@local-repo"]' in config_after_delete
              and 'model = "user-model"' in config_after_delete
              and dsh_after_delete.get("mcpServers", {}).get("user-browser", {}).get("command") == "user-mcp"
              and "chrome-devtools" not in dsh_after_delete.get("mcpServers", {})
              and "chrome-devtools-plugins" not in claude_after_delete.get("extraKnownMarketplaces", {})
              and not any(key.startswith("chrome-devtools-mcp@")
                          for key in claude_after_delete.get("enabledPlugins", {}))
              and claude_after_delete.get("extraKnownMarketplaces", {}).get("user-market")
              and claude_after_delete.get("enabledPlugins", {}).get("user-plugin@user-market") is True
              and user_plugin.is_file())
    finally:
        _rm(root)

    # 未受管同名 MCP：配置一致则保留，不一致 fail closed
    root = _mkrepo(markers=(".codex",))
    try:
        _add_browser_plugin(root)
        config_path = root / ".codex/config.toml"
        unmanaged = ('model = "keep"\n\n[mcp_servers.chrome-devtools]\ncommand = "npx"\n'
                     'args = ["chrome-devtools-mcp@1.6.0"]\n')
        config_path.write_text(unmanaged, encoding="utf-8")
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        config = _read(config_path)
        check("Codex 未受管同名 MCP 一致 → 原样保留且不接管",
              rc == 0 and config.count("[mcp_servers.chrome-devtools]") == 1
              and "AIDP-MCP chrome-devtools" not in config and 'model = "keep"' in config)
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        _add_browser_plugin(root)
        config_path = root / ".codex/config.toml"
        original = '[mcp_servers.chrome-devtools]\ncommand = "user-mcp"\n'
        config_path.write_text(original, encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("Codex 未受管同名 MCP 不一致 → fail closed 且原配置保持",
              rc == 2 and "冲突" in out.get("error", "") and _read(config_path) == original)
    finally:
        _rm(root)

    root = _mkrepo(markers=(".dsh",))
    try:
        _add_browser_plugin(root)
        mcp_path = root / ".dsh/mcp.json"
        unmanaged_data = {"mcpServers": {"chrome-devtools": {
            "command": "npx", "args": ["chrome-devtools-mcp@1.6.0"]}}}
        mcp_path.write_text(json.dumps(unmanaged_data), encoding="utf-8")
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "dsh")
        marker = root / AS.DSH_MCP_MANAGED
        _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        after_switch = json.loads(_read(mcp_path) or "{}")
        check("DSH 未受管同名 MCP 一致 → 保留且切换 Agent 不删除",
              rc == 0 and "chrome-devtools" in after_switch.get("mcpServers", {})
              and "chrome-devtools" not in _read(marker))
    finally:
        _rm(root)

    root = _mkrepo(markers=(".dsh",))
    try:
        _add_browser_plugin(root)
        mcp_path = root / ".dsh/mcp.json"
        original_data = {"mcpServers": {"chrome-devtools": {"command": "user-mcp"}}}
        mcp_path.write_text(json.dumps(original_data), encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "dsh")
        check("DSH 未受管同名 MCP 不一致 → fail closed 且用户 server 保持",
              rc == 2 and "冲突" in out.get("error", "")
              and json.loads(_read(mcp_path)) == original_data)
    finally:
        _rm(root)

    # 共享插件目标存在用户目录 → fail closed
    root = _mkrepo(markers=(".codex",))
    try:
        _add_browser_plugin(root)
        user_target = root / ".agents/skills/chrome-devtools-mcp/note.txt"
        user_target.parent.mkdir(parents=True)
        user_target.write_text("keep\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("共享插件目标无生成标记 → fail closed 且用户目录保持",
              rc == 2 and "用户" in out.get("error", "") and _read(user_target) == "keep\n")
    finally:
        _rm(root)

    # Claude 插件目标存在用户目录 → preflight fail closed，无部分适配写入
    root = _mkrepo(markers=(".claude",))
    try:
        _add_browser_plugin(root)
        user_target = root / ".claude/plugins/chrome-devtools-mcp/note.txt"
        user_target.parent.mkdir(parents=True)
        user_target.write_text("keep claude plugin\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude")
        check("Claude 插件目标无生成证据 → fail closed、用户内容保持且无部分适配",
              rc == 2 and "用户" in out.get("error", "")
              and _read(user_target) == "keep claude plugin\n"
              and not (root / ".claude/commands/sprint-dev.md").exists()
              and not (root / ".claude/skills/demo-skill").exists()
              and not (root / ".claude/settings.json").exists())
    finally:
        _rm(root)

    # DSH 最后一个受管 server 删除时保留其他顶层配置
    root = _mkrepo(markers=(".dsh",))
    try:
        plugin = _add_browser_plugin(root)
        _run(SYNC_PY, "--root", str(root), "--agents", "dsh")
        mcp_path = root / ".dsh/mcp.json"
        data = json.loads(_read(mcp_path))
        data["transport"] = {"mode": "stdio", "timeout": 30}
        mcp_path.write_text(json.dumps(data), encoding="utf-8")
        shutil.rmtree(plugin)
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "dsh")
        after = json.loads(_read(mcp_path) or "{}")
        check("DSH 最后受管 server 移除 → 仅删空 mcpServers、保留顶层配置",
              rc == 0 and after == {"transport": {"mode": "stdio", "timeout": 30}})
    finally:
        _rm(root)

    # Claude 目标与配置错误必须在 memory/hooks/适配层写入前 fail closed
    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        user_skill = root / ".claude/skills/demo-skill/SKILL.md"
        user_skill.parent.mkdir(parents=True)
        user_skill.write_text("# user skill\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude SKILL 用户目标冲突 → 原子 fail closed",
              rc == 2 and "用户" in out.get("error", "") and _read(user_skill) == "# user skill\n"
              and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists()
              and not (root / ".claude/commands").exists() and not (root / ".codex/hooks.json").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        user_command = root / ".claude/commands/sprint-dev.md"
        user_command.parent.mkdir(parents=True)
        user_command.write_text("# user command\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude command 用户目标冲突 → 原子 fail closed",
              rc == 2 and "用户" in out.get("error", "") and _read(user_command) == "# user command\n"
              and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists()
              and not (root / ".claude/skills").exists() and not (root / ".codex/hooks.json").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        _add_browser_plugin(root)
        settings = root / ".claude/settings.json"
        settings.write_text("{bad json", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude settings 非法 → preflight 原子失败",
              rc == 2 and "JSON" in out.get("error", "") and _read(settings) == "{bad json"
              and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists()
              and not (root / ".claude/plugins/chrome-devtools-mcp").exists()
              and not (root / ".codex/hooks.json").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        _add_browser_plugin(root)
        settings = root / ".claude/settings.json"
        settings.write_text(json.dumps({"extraKnownMarketplaces": []}), encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude settings 字段类型错误 → preflight 原子失败",
              rc == 2 and "类型" in out.get("error", "") and not (root / "AGENTS.md").exists()
              and not (root / ".claude/plugins/chrome-devtools-mcp").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        _add_browser_plugin(root)
        settings = root / ".claude/settings.json"
        settings.write_text(json.dumps({
            "extraKnownMarketplaces": {
                "chrome-devtools-plugins": {"source": {"source": "directory", "path": "./user"}}
            }
        }), encoding="utf-8")
        original = _read(settings)
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude marketplace 用户配置冲突 → preflight 原子失败",
              rc == 2 and "冲突" in out.get("error", "") and _read(settings) == original
              and not (root / "AGENTS.md").exists()
              and not (root / ".claude/plugins/chrome-devtools-mcp").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        hooks = root / ".codex/hooks.json"
        hooks.write_text("{bad hooks", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Agent hook JSON 非法 → preflight 原子失败",
              rc == 2 and "hooks" in out.get("error", "") and _read(hooks) == "{bad hooks"
              and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists()
              and not (root / ".claude/commands").exists())
    finally:
        _rm(root)

    malformed_hooks = [
        ("hooks 非对象", {"hooks": []}),
        ("Stop 非数组", {"hooks": {"Stop": {}}}),
        ("group 非对象", {"hooks": {"Stop": ["bad-group"]}}),
        ("group hooks 非数组", {"hooks": {"Stop": [{"hooks": {}}]}}),
        ("hook 非对象", {"hooks": {"Stop": [{"hooks": ["bad-hook"]}]}}),
    ]
    for label, payload in malformed_hooks:
        root = _mkrepo(markers=(".claude", ".codex"))
        try:
            hooks = root / ".codex/hooks.json"
            hooks.write_text(json.dumps(payload), encoding="utf-8")
            settings = root / ".claude/settings.json"
            settings.write_text(json.dumps({"permissions": {"allow": ["Bash(git status)"]}}), encoding="utf-8")
            original_settings = _read(settings)
            rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
            check(f"Agent hook 结构错误（{label}）→ preflight 原子失败",
                  rc == 2 and "hooks" in out.get("error", "") and _read(hooks) == json.dumps(payload)
                  and _read(settings) == original_settings and _read(root / "CLAUDE.md") == BODY
                  and not (root / "AGENTS.md").exists() and not (root / ".claude/commands").exists())
        finally:
            _rm(root)

    # Codex features：false 精确替换，重复键/section 原子拒绝
    root = _mkrepo(markers=(".codex",))
    try:
        config = root / ".codex/config.toml"
        config.write_text('[features]\nother = true\ncodex_hooks = false # keep this comment\n', encoding="utf-8")
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        text = _read(config)
        check("Codex codex_hooks=false 带注释 → 原位替换为单个 true 并保留注释",
              rc == 0 and text.count("codex_hooks") == 1
              and "codex_hooks = true # keep this comment" in text
              and "codex_hooks = false" not in text and text.count("[features]") == 1
              and "other = true" in text)
    finally:
        _rm(root)

    for label, config_text in (
        ("重复 codex_hooks", '[features]\ncodex_hooks = false\ncodex_hooks = true\n'),
        ("重复 features section", '[features]\nother = true\n\n[features]\ncodex_hooks = false\n'),
    ):
        root = _mkrepo(markers=(".claude", ".codex"))
        try:
            config = root / ".codex/config.toml"
            config.write_text(config_text, encoding="utf-8")
            rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
            check(f"Codex features 异常（{label}）→ preflight 原子失败",
                  rc == 2 and "features" in out.get("error", "").lower()
                  and _read(config) == config_text and _read(root / "CLAUDE.md") == BODY
                  and not (root / "AGENTS.md").exists() and not (root / ".codex/hooks.json").exists()
                  and not (root / ".claude/commands").exists())
        finally:
            _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        _add_browser_plugin(root)
        marker = root / AS.CLAUDE_PLUGIN_MANAGED
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("[]", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude managed marker 类型错误 → preflight 原子失败",
              rc == 2 and "marker" in out.get("error", "").lower()
              and _read(marker) == "[]" and not (root / "AGENTS.md").exists()
              and not (root / ".claude/plugins/chrome-devtools-mcp").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        plugin = _add_browser_plugin(root)
        marketplace = plugin / ".claude-plugin/marketplace.json"
        marketplace.write_text("{bad json", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude marketplace 非法 → preflight 原子失败",
              rc == 2 and "marketplace" in out.get("error", "").lower()
              and not (root / "AGENTS.md").exists()
              and not (root / ".claude/plugins/chrome-devtools-mcp").exists()
              and not (root / ".codex/hooks.json").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        plugin = _add_browser_plugin(root)
        marketplace = plugin / ".claude-plugin/marketplace.json"
        marketplace.write_text(json.dumps({"name": "chrome-devtools-plugins", "plugins": {}}),
                               encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        check("Claude marketplace 字段类型错误 → preflight 原子失败",
              rc == 2 and "类型" in out.get("error", "") and not (root / "AGENTS.md").exists()
              and not (root / ".claude/plugins/chrome-devtools-mcp").exists())
    finally:
        _rm(root)

    # Codex MCP 声明含未支持字段 → 写入前 fail closed，错误列出 server/字段
    root = _mkrepo(markers=(".claude", ".codex"))
    try:
        plugin = _add_browser_plugin(root)
        manifest_path = plugin / ".claude-plugin/plugin.json"
        manifest = json.loads(_read(manifest_path))
        manifest["mcpServers"]["chrome-devtools"].update({
            "env": {"TOKEN": "x"}, "cwd": "/tmp", "headers": {"X-Test": "1"},
        })
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude,codex")
        error = out.get("error", "")
        check("Codex MCP 未支持字段 → preflight 原子 fail closed",
              rc == 2 and "chrome-devtools" in error and all(key in error for key in ("env", "cwd", "headers"))
              and _read(root / "CLAUDE.md") == BODY and not (root / "AGENTS.md").exists()
              and not (root / ".claude/plugins/chrome-devtools-mcp").exists()
              and not (root / ".codex/config.toml").exists()
              and not (root / ".codex/hooks.json").exists())
    finally:
        _rm(root)

    # 插件 copy 模式：三端均为内容完整的真实副本
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        pl = _add_browser_plugin(root)
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--mode", "copy")
        claude_plugin = root / ".claude/plugins/chrome-devtools-mcp"
        shared_plugin_skill = root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools"
        source_skill = pl / "skills/chrome-devtools"
        check("插件 copy·Claude：完整项目插件为真实副本",
              rc == 0 and claude_plugin.is_dir() and not claude_plugin.is_symlink()
              and not (claude_plugin / ".claude-plugin/plugin.json").is_symlink()
              and _read(claude_plugin / ".claude-plugin/plugin.json")
              == _read(pl / ".claude-plugin/plugin.json"))
        check("插件 copy·Codex/DSH：共享嵌套 skills 为内容完整的真实副本",
              shared_plugin_skill.is_dir() and not shared_plugin_skill.is_symlink()
              and not (shared_plugin_skill / "SKILL.md").is_symlink()
              and not (shared_plugin_skill / "references/usage.md").is_symlink()
              and _read(shared_plugin_skill / "SKILL.md") == _read(source_skill / "SKILL.md")
              and _read(shared_plugin_skill / "references/usage.md")
              == _read(source_skill / "references/usage.md")
              and not (root / ".codex/skills/chrome-devtools-mcp").exists()
              and not (root / ".agents/skills/chrome-devtools").exists())
    finally:
        _rm(root)

    # 旧 Codex 专属插件入口即使是悬空 symlink 也必须被识别并清理
    root = _mkrepo(markers=(".codex",))
    try:
        _add_browser_plugin(root)
        legacy = root / ".codex/skills/chrome-devtools-mcp"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.symlink_to(root / ".aidp/plugins/chrome-devtools-mcp/skills/missing-old-plugin",
                          target_is_directory=True)
        rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        shared = root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md"
        check("悬空旧 Codex 插件 symlink → 清理且改用共享嵌套 SKILL",
              rc == 0 and not os.path.lexists(legacy) and shared.is_file())
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
        rc, out, stdout, stderr = _run(SYNC_PY, "--root", str(root))
        check("插件 SKILL 与公共 SKILL 重名 → 非零退出并提示冲突",
              rc != 0 and "冲突" in (out.get("error", "") + stdout + stderr))
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        pl = root / ".aidp/plugins/demo-plugin"
        (pl / ".claude-plugin").mkdir(parents=True)
        (pl / ".claude-plugin/plugin.json").write_text('{"name":"demo-plugin"}\n', encoding="utf-8")
        (pl / "skills/demo-skill").mkdir(parents=True)
        (pl / "skills/demo-skill/SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("Codex-only 也检查插件 SKILL 与公共 SKILL 重名",
              rc == 2 and "冲突" in out.get("error", ""))
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        pl = root / ".aidp/plugins/demo-plugin"
        (pl / ".claude-plugin").mkdir(parents=True)
        (pl / ".claude-plugin/plugin.json").write_text('{"name":"demo-plugin"}\n', encoding="utf-8")
        (pl / "skills/sprint-dev").mkdir(parents=True)
        (pl / "skills/sprint-dev/SKILL.md").write_text("---\nname: sprint-dev\n---\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("插件 SKILL 与命令重名 → Codex-only fail closed",
              rc == 2 and "冲突" in out.get("error", ""))
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        for plugin_name in ("plugin-a", "plugin-b"):
            pl = root / ".aidp/plugins" / plugin_name
            (pl / ".claude-plugin").mkdir(parents=True)
            (pl / ".claude-plugin/plugin.json").write_text(
                json.dumps({"name": plugin_name}), encoding="utf-8")
            (pl / "skills/shared-name").mkdir(parents=True)
            (pl / "skills/shared-name/SKILL.md").write_text(
                "---\nname: shared-name\n---\n", encoding="utf-8")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("插件之间 SKILL 重名 → Codex-only fail closed",
              rc == 2 and "冲突" in out.get("error", ""))
    finally:
        _rm(root)

    rc, out, _, _ = _run(SYNC_PY, "--self-check")
    check("agent_sync --self-check 通过", rc == 0 and out.get("self_check") == "pass")


def test_sync_executes_from_native_runtime_without_root_aidp():
    print("【agent_sync：从 Agent 原生 runtime 执行，无根 .aidp】")
    cases = (
        ("claude", ".claude/aidp", ".claude/aidp/scripts/agent_sync.py",
         ".claude/commands/sprint-dev.md", ".claude/skills/demo-skill/SKILL.md"),
        ("codex,dsh", ".agents/aidp", ".agents/aidp/scripts/agent_sync.py",
         ".dsh/commands/sprint-dev.md", ".agents/skills/demo-skill/SKILL.md"),
    )
    for agents, runtime_rel, script_rel, command_rel, skill_rel in cases:
        root = _mkrepo(markers=tuple(f".{name}" for name in agents.split(",")))
        try:
            _add_browser_plugin(root)
            _move_source_into_runtime(root, runtime_rel)
            script = root / script_rel
            rc, out, _, _ = _run(str(script), "--root", str(root), "--agents", agents)
            check(f"{agents}：无根 .aidp 仍可装配",
                  rc == 0 and not (root / ".aidp").exists()
                  and (root / command_rel).is_file()
                  and (root / skill_rel).is_file())
            check(f"{agents}：原生 runtime 装配结果为 managed-copy",
                  not (root / command_rel).is_symlink()
                  and not (root / skill_rel).parent.is_symlink())
            rc, checked, _, _ = _run(
                str(script), "--root", str(root), "--agents", agents, "--check",
            )
            check(f"{agents}：无根 .aidp 的 --check 一致",
                  rc == 0 and checked.get("drift") is False)
        finally:
            _rm(root)


def test_native_runtime_managed_copy_contract():
    print("【Agent 原生运行包：managed-copy + DSH 嵌套 SKILL 契约】")
    root = _mkrepo(markers=(".claude", ".codex", ".dsh"))
    try:
        _add_browser_plugin(root)
        rc, out, _, _ = _run(
            SYNC_PY, "--root", str(root), "--agents", "claude,codex,dsh",
            "--mode", "link",
        )
        generated = (
            root / ".claude/skills/demo-skill",
            root / ".claude/commands/sprint-dev.md",
            root / ".agents/skills/demo-skill",
            root / ".codex/skills/aidp/sprint-dev",
            root / ".dsh/commands/sprint-dev.md",
        )
        check("新布局统一使用 managed-copy，不生成 symlink",
              rc == 0 and all(path.exists() and not path.is_symlink() for path in generated))
        nested = root / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md"
        check("DSH/Codex 插件 SKILL 使用 namespaced 嵌套布局",
              nested.is_file() and not (root / ".agents/skills/chrome-devtools").exists())
        check("旧 link 参数明确规范化为 managed-copy",
              any(action.get("action") == "normalized"
                  and action.get("from") == "link"
                  and action.get("to") == "managed-copy"
                  for action in out.get("actions", [])))
    finally:
        _rm(root)


def test_managed_copy_tree_drift_is_recursive():
    print("【managed-copy 树：symlink / 空目录 / mode 漂移】")
    root = _mkrepo(markers=(".claude",))
    source = root / ".aidp/skills/demo-skill"
    (source / "references/empty").mkdir(parents=True)
    (source / "references/usage.md").write_text("usage\n", encoding="utf-8")
    try:
        _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--mode", "copy")
        target = root / ".claude/skills/demo-skill"

        skill_file = target / "SKILL.md"
        skill_file.unlink()
        skill_file.symlink_to(source / "SKILL.md")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--check")
        check("后代文件 symlink → --check 漂移", rc == 1 and out.get("drift") is True)
        _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--mode", "copy")

        shutil.rmtree(target / "references")
        (target / "references").symlink_to(source / "references", target_is_directory=True)
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--check")
        check("后代目录 symlink → --check 漂移", rc == 1 and out.get("drift") is True)
        _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--mode", "copy")

        (target / "references/empty").rmdir()
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--check")
        check("源空目录在目标缺失 → --check 漂移", rc == 1 and out.get("drift") is True)
        _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--mode", "copy")

        (target / "references/extra-empty").mkdir()
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--check")
        check("目标额外空目录 → --check 漂移", rc == 1 and out.get("drift") is True)
        _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--mode", "copy")

        outside = Path(tempfile.mkdtemp())
        sentinel = outside / "sentinel"
        sentinel.write_text("outside\n", encoding="utf-8")
        (target / "SKILL.md").unlink()
        os.link(sentinel, target / "SKILL.md")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--check")
        check("目标 hardlink → --check 漂移且外部字节不变",
              rc == 1 and out.get("drift") is True
              and sentinel.read_text(encoding="utf-8") == "outside\n")
        shutil.rmtree(outside, ignore_errors=True)
    finally:
        _rm(root)


def _nested_plugin(root, plugin_name, rel, frontmatter_name):
    plugin = root / ".aidp/plugins" / plugin_name
    (plugin / ".claude-plugin").mkdir(parents=True, exist_ok=True)
    (plugin / ".claude-plugin/plugin.json").write_text(
        json.dumps({"name": plugin_name}), encoding="utf-8")
    skill = plugin / "skills" / rel
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        f"---\nname: {frontmatter_name}\n---\n", encoding="utf-8")
    return skill


def test_nested_plugin_skill_conflicts_fail_closed():
    print("【嵌套插件 SKILL：frontmatter name 递归冲突预检】")

    root = _mkrepo(markers=(".codex",))
    try:
        (root / ".aidp/skills/demo-skill/SKILL.md").write_text(
            "---\nname: renamed-public-skill\n---\n", encoding="utf-8")
        plugin_skill = _nested_plugin(root, "demo-skill", "group/a", "plugin-contract")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        error = out.get("error", "")
        check("公共 SKILL 目录名与插件 namespace 重名 → 写入前 fail closed",
              rc == 2 and "demo-skill" in error
              and (root / ".aidp/skills/demo-skill").as_posix() in error
              and plugin_skill.parents[2].as_posix() in error
              and not (root / ".agents").exists()
              and not (root / ".codex/skills").exists())
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        _nested_plugin(root, "nested-plugin", "group/renamed-dir", "demo-skill")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("嵌套插件 SKILL 与公共 SKILL 重名 → fail closed",
              rc == 2 and "冲突" in out.get("error", "") and "demo-skill" in out.get("error", ""))
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        first = _nested_plugin(root, "nested-plugin", "group/a", "same-name")
        second = _nested_plugin(root, "nested-plugin", "other/b", "same-name")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        error = out.get("error", "")
        check("同插件嵌套 SKILL 重名 → 错误列出两来源",
              rc == 2 and first.as_posix() in error and second.as_posix() in error)
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        first = _nested_plugin(root, "plugin-a", "group/a", "cross-name")
        second = _nested_plugin(root, "plugin-b", "other/b", "cross-name")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        error = out.get("error", "")
        check("跨插件嵌套 SKILL 重名 → 错误列出两来源",
              rc == 2 and first.as_posix() in error and second.as_posix() in error)
    finally:
        _rm(root)

    root = _mkrepo(markers=(".codex",))
    try:
        _nested_plugin(root, "nested-plugin", "group/a", "sprint-dev")
        rc, out, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "codex")
        check("嵌套插件 SKILL 与命令重名 → fail closed",
              rc == 2 and "sprint-dev" in out.get("error", ""))
    finally:
        _rm(root)


def test_materialization_is_atomic_and_source_is_safe():
    print("【managed-copy 原子替换与源树安全】")
    root = _mkrepo(markers=(".claude",))
    source = root / ".aidp/skills/demo-skill"
    target = root / ".claude/skills/demo-skill"
    try:
        _run(SYNC_PY, "--root", str(root), "--agents", "claude", "--mode", "copy")
        before = {p.relative_to(target).as_posix(): p.read_bytes()
                  for p in target.rglob("*") if p.is_file() and not p.is_symlink()}
        (source / "SKILL.md").write_text("changed\n", encoding="utf-8")

        config = root / ".claude/probe.json"
        config.write_text("old\n", encoding="utf-8")
        original_write_text = Path.write_text
        def broken_text_stage(path, text, *args, **kwargs):
            if ".stage-" in path.name:
                original_write_text(path, "partial", *args, **kwargs)
                raise OSError("text stage probe")
            return original_write_text(path, text, *args, **kwargs)
        Path.write_text = broken_text_stage
        try:
            try:
                AS.Plan(root, True, "copy").write_text(config, "new\n")
                failed = False
            except OSError:
                failed = True
        finally:
            Path.write_text = original_write_text
        check("文本 stage 写失败 → 旧文件字节保持",
              failed and config.read_text(encoding="utf-8") == "old\n")

        original_copytree = AS.shutil.copytree
        def broken_copytree(src, dst, **kwargs):
            Path(dst).mkdir(parents=True)
            (Path(dst) / "partial").write_text("partial", encoding="utf-8")
            raise OSError("copytree probe")
        AS.shutil.copytree = broken_copytree
        try:
            try:
                AS.Plan(root, True, "copy").link_dir(target, source)
                failed = False
            except OSError:
                failed = True
        finally:
            AS.shutil.copytree = original_copytree
        after = {p.relative_to(target).as_posix(): p.read_bytes()
                 for p in target.rglob("*") if p.is_file() and not p.is_symlink()}
        check("目录复制失败 → 旧实体树原样保留", failed and before == after)

        source_file = root / ".aidp/commands/sprint-dev.md"
        target_file = root / ".claude/commands/sprint-dev.md"
        old_bytes = target_file.read_bytes()
        source_file.write_text("changed command\n", encoding="utf-8")
        original_copy2 = AS.shutil.copy2
        def broken_copy2(src, dst, **kwargs):
            Path(dst).write_text("partial", encoding="utf-8")
            raise OSError("copy2 probe")
        AS.shutil.copy2 = broken_copy2
        try:
            try:
                AS.Plan(root, True, "copy").link_file(target_file, source_file)
                failed = False
            except OSError:
                failed = True
        finally:
            AS.shutil.copy2 = original_copy2
        check("文件复制失败 → 旧入口字节保持", failed and target_file.read_bytes() == old_bytes)

        original_write_text = Path.write_text
        def broken_marker(path, text, *args, **kwargs):
            if path.name == AS.GENERATED_FILE and ".stage-" in path.parent.name:
                raise OSError("marker probe")
            return original_write_text(path, text, *args, **kwargs)
        Path.write_text = broken_marker
        try:
            try:
                AS.Plan(root, True, "copy").link_dir(target, source)
                failed = False
            except OSError:
                failed = True
        finally:
            Path.write_text = original_write_text
        after = {p.relative_to(target).as_posix(): p.read_bytes()
                 for p in target.rglob("*") if p.is_file() and not p.is_symlink()}
        check("marker 写失败 → 旧实体树原样保留", failed and before == after)
    finally:
        _rm(root)

    for kind in ("file-symlink", "dir-symlink", "hardlink", "fifo"):
        root = _mkrepo(markers=(".claude",))
        outside = Path(tempfile.mkdtemp())
        sentinel = outside / "sentinel"
        sentinel.write_text("outside\n", encoding="utf-8")
        try:
            skill = root / ".aidp/skills/demo-skill"
            if kind == "file-symlink":
                (skill / "SKILL.md").unlink()
                (skill / "SKILL.md").symlink_to(sentinel)
            elif kind == "dir-symlink":
                (skill / "references").symlink_to(outside, target_is_directory=True)
            elif kind == "hardlink":
                os.link(sentinel, skill / "hard-linked.txt")
            else:
                os.mkfifo(skill / "nonregular.fifo")
            rc, _, _, _ = _run(SYNC_PY, "--root", str(root), "--agents", "claude")
            check(f"源树 {kind} → preflight fail closed 且零写入",
                  rc == 2 and sentinel.read_text(encoding="utf-8") == "outside\n"
                  and not (root / ".claude/skills/demo-skill").exists()
                  and not (root / ".claude/commands").exists())
        finally:
            _rm(root)
            shutil.rmtree(outside, ignore_errors=True)


def test_legacy_symlink_cleanup_is_lexically_contained():
    print("【legacy symlink：词法 containment 与保守清理】")
    root = Path(tempfile.mkdtemp())
    try:
        destination = root / ".claude/commands/x.md"
        destination.parent.mkdir(parents=True)
        cases = (
            ("../../.aidp/commands/x.md", True),
            ("../../.aidp/commands/../commands/missing.md", True),
            ("../../not.aidp/commands/x.md", False),
            (str(Path(tempfile.gettempdir()) / ".aidp/commands/x.md"), False),
            ("../../../outside/.aidp/commands/x.md", False),
        )
        results = []
        for raw, expected in cases:
            if os.path.lexists(destination):
                destination.unlink()
            destination.symlink_to(raw)
            results.append(AS.cleanup_legacy_link_is_generated(root, destination) == expected)
        check("仅项目内精确旧 commands/skills/plugins 子树视为生成链接", all(results))
    finally:
        _rm(root)


def main():
    test_agent_env()
    test_sync_all_agents_managed_copy()
    test_memory_migration_shapes()
    test_copy_mode_and_errors()
    test_sync_executes_from_native_runtime_without_root_aidp()
    test_native_runtime_managed_copy_contract()
    test_managed_copy_tree_drift_is_recursive()
    test_nested_plugin_skill_conflicts_fail_closed()
    test_materialization_is_atomic_and_source_is_safe()
    test_legacy_symlink_cleanup_is_lexically_contained()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
