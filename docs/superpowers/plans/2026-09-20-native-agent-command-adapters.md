# Native Agent Command Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Claude Code、Codex、DeepSeek Harness 分别通过原生命令入口执行同一份 `.aidp/commands/` 契约，并彻底退役 `aidp-cmd` 路由。

**Architecture:** `.aidp/skills/`、`.aidp/commands/` 与 `.aidp/plugins/` 保持单一信源；`agent_sync.py` 按目标 Agent 生成原生命令目录、公共 SKILL 目录，以及 `chrome-devtools-mcp` 的 Claude 项目级插件、Codex `.codex/skills` 集合和 DSH `.agents/skills` 集合。脚手架只在 DSH init 时尽力安装 `dsh-plugin-commands`，升级流程负责保守清理旧路由真源，`verify.py` 只校验新的适配层。

**Tech Stack:** Python 3 标准库、Bash、Markdown、Git、现有自定义测试运行器。

---

## 文件结构与职责

- `.aidp/scripts/agent_sync.py`：三种 Agent 的命令、公共 SKILL、`chrome-devtools-mcp` 适配层生成、清理、漂移检测与自检。
- `.aidp/plugins/chrome-devtools-mcp/`：Claude 插件、配套 SKILL 与 MCP server 声明的单一信源。
- `.aidp/scripts/agent_loop.sh`：无人值守命令提示词使用原生 Agent 调用格式。
- `.aidp/scripts/tests/test_agent_sync.py`：适配目录、link/copy、幂等、清理和项目自有内容保护回归。
- `.aidp/scripts/tests/test_agent_sync_router.py`：改造成原生命令生成契约回归，保留文件名以减少测试登记变动。
- `.aidp/scripts/tests/test_aidp_scheduler.py`：无人值守原生命令提示词回归。
- `.aidp/skills/aidp-code-engineer/scripts/scaffold.py`：DSH init 插件安装与旧路由真源迁移。
- `.aidp/skills/aidp-code-engineer/scripts/scaffold_lib.py`：移除 `aidp-cmd` 指纹豁免。
- `.aidp/skills/aidp-code-engineer/scripts/verify.py`：新适配目录模式探测，移除路由源校验。
- `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`：DSH 插件安装、旧路由迁移和 init/migrate/upgrade 回归。
- `.aidp/skills/aidp-code-engineer/scripts/tests/test_mirror.py`：bundle 不再包含路由 SKILL 的回归。
- `.aidp/skills/aidp-cmd/`：删除。
- `AGENTS.md`、`.aidp/AIDP-AGENTS.md`、`README.md`、`.aidp/reference/*.md`、`.aidp/scripts/README.md`、`.aidp/hooks/README.md`、`docs/init/*.md`、`.aidp/skills/aidp-code-engineer/SKILL.md`：同步当前行为说明。
- `.aidp/skills/aidp-code-engineer/assets/`：只由同步脚本重建，不手工编辑。

### Task 1: 用测试锁定三种原生命令适配契约

**Files:**
- Modify: `.aidp/scripts/tests/test_agent_sync.py`
- Modify: `.aidp/scripts/tests/test_agent_sync_router.py`

- [ ] **Step 1: 把 Codex/DSH 断言改成原生命令目录**

在 `test_agent_sync.py` 的三 Agent link 模式用例中加入以下等价断言，并删除对 `.agents/skills/aidp-cmd` 的期望：

```python
codex_command = root / ".codex/aidp/skills/sprint-dev/SKILL.md"
check("codex 原生命令 SKILL", codex_command.is_file())
check("codex 命令保留参数", "$ARGUMENTS" in codex_command.read_text(encoding="utf-8"))
check("codex 命令有 frontmatter", codex_command.read_text(encoding="utf-8").startswith("---\nname: sprint-dev\n"))

check("dsh 原生命令", (root / ".dsh/commands/sprint-dev.md").exists())
check("公共 skill 不含路由", not (root / ".agents/skills/aidp-cmd").exists())
```

同时覆盖：Codex-only、DSH-only、Codex+DSH、copy 模式、切换 Agent 后旧目录清理、用户自建命令目录不被删除。

加入插件适配断言：

```python
check("claude 保持完整插件", (root / ".claude/plugins/chrome-devtools-mcp/.claude-plugin/plugin.json").exists())
check("codex 使用项目级技能集合", (root / ".codex/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").exists())
check("codex 不生成仓库 marketplace", not (root / ".agents/plugins/marketplace.json").exists())
check("codex 注册 mcp server", "[mcp_servers.chrome-devtools]" in (root / ".codex/config.toml").read_text(encoding="utf-8"))
check("dsh 发现插件 skill", (root / ".agents/skills/chrome-devtools/SKILL.md").exists())
check("dsh 注册 mcp server", "chrome-devtools" in (root / ".dsh/mcp.json").read_text(encoding="utf-8"))
```

再覆盖插件 SKILL 与公共 SKILL 重名时 fail closed，以及 Codex+DSH 生成物都指向同一 `.aidp/plugins/chrome-devtools-mcp/skills/` 真源。

- [ ] **Step 2: 将路由专项测试改成命令生成专项测试**

保留 `test_agent_sync_router.py` 文件名和 `run.sh` 登记，但将正文测试目标改为：

```python
def test_codex_skill_body(command_source, generated_skill):
    text = generated_skill.read_text(encoding="utf-8")
    assert "name: sprint-dev" in text
    assert "allow_implicit_invocation: false" in text
    assert command_source.read_text(encoding="utf-8") in text


def test_native_command_sync_does_not_create_router(root):
    run_sync(root, "--agents", "codex,dsh")
    assert not (root / ".agents/skills/aidp-cmd").exists()
    assert not (root / ".aidp/skills/aidp-cmd").exists()
```

增加 H1 缺失时稳定 description、命令与公共 SKILL 重名时 exit 2、`--check` 发现正文漂移的用例。

- [ ] **Step 3: 运行测试确认按预期失败**

Run:

```bash
python3 .aidp/scripts/tests/test_agent_sync.py
python3 .aidp/scripts/tests/test_agent_sync_router.py
```

Expected: FAIL，缺少 `.codex/aidp/skills/*` 与 `.dsh/commands/*`，且旧 `aidp-cmd` 仍被生成。

- [ ] **Step 4: 提交测试红灯**

```bash
git add .aidp/scripts/tests/test_agent_sync.py .aidp/scripts/tests/test_agent_sync_router.py
git commit -m "test: define native agent command adapters" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 2: 实现 `agent_sync.py` 原生命令生成

**Files:**
- Modify: `.aidp/scripts/agent_sync.py`
- Test: `.aidp/scripts/tests/test_agent_sync.py`
- Test: `.aidp/scripts/tests/test_agent_sync_router.py`

- [ ] **Step 1: 替换目录常量和顶层适配表**

定义：

```python
CLAUDE_SKILLS = ".claude/skills"
SHARED_SKILLS = ".agents/skills"
CLAUDE_COMMANDS = ".claude/commands"
CODEX_COMMAND_SKILLS = ".codex/aidp/skills"
DSH_COMMANDS = ".dsh/commands"
OBSOLETE_ROUTER = "aidp-cmd"
```

删除 `ROUTER_NAME`、`OPENAI_YAML` 及路由正文模板常量；顶层 docstring 明确三种原生命令目录。

- [ ] **Step 2: 实现 Codex 命令 SKILL 渲染器**

新增纯函数，名称与签名固定为：

```python
CODEX_EXPLICIT_POLICY = "policy:\n  allow_implicit_invocation: false\n"


def codex_command_skill(name: str, command_text: str) -> str:
    heading = next(
        (line[2:].strip() for line in command_text.splitlines() if line.startswith("# ")),
        f"AIDP command {name}",
    )
    description = heading.replace('"', "'")
    return (
        "---\n"
        f"name: {name}\n"
        f'description: "{description}"\n'
        "disable-model-invocation: true\n"
        "user-invocable: true\n"
        "---\n\n"
        f"{command_text.rstrip()}\n"
    )
```

每个命令同时生成 `agents/openai.yaml`，内容取 `CODEX_EXPLICIT_POLICY`。SKILL 正文不内联第二套 OpenAI 策略。

- [ ] **Step 3: 泛化命令同步函数**

保留 Claude 的 link/copy 行为，新增：

```python
def _command_files(root: Path) -> list[Path]:
    source = root / AIDP_DIR / "commands"
    if not source.is_dir():
        return []
    return [path for path in sorted(source.glob("*.md")) if path.stem.upper() != "README"]


def sync_codex_commands(plan: Plan) -> list[str]:
    destination = plan.root / CODEX_COMMAND_SKILLS
    wanted: set[str] = set()
    generated: list[str] = []
    for command in _command_files(plan.root):
        name = command.stem
        target = destination / name
        wanted.add(name)
        plan.write_text(target / "SKILL.md", codex_command_skill(name, _read(command)))
        plan.write_text(target / "agents" / "openai.yaml", CODEX_EXPLICIT_POLICY)
        plan.write_text(target / GENERATED_FILE, "native-command\n")
        generated.append(f"{CODEX_COMMAND_SKILLS}/{name}")
    _prune(plan, destination, wanted)
    return generated


def sync_dsh_commands(plan: Plan) -> list[str]:
    destination = plan.root / DSH_COMMANDS
    wanted: set[str] = set()
    generated: list[str] = []
    for command in _command_files(plan.root):
        wanted.add(command.name)
        plan.link_file(destination / command.name, command)
        generated.append(f"{DSH_COMMANDS}/{command.name}")
    _prune(plan, destination, wanted)
    return generated
```

Codex 生成目录写入 `.aidp-generated` 标记；清理时只删除符号链接或带生成标记的目录。公共 `sync_skill_dir()` 永远排除 `aidp-cmd`，即使旧真源尚未迁移清理。

- [ ] **Step 4: 重排 `run()` 分支**

行为固定为：

```python
if "claude" in agents:
    sync_skill_dir(plan, CLAUDE_SKILLS)
    sync_commands(plan, CLAUDE_COMMANDS)
else:
    prune_generated(plan, CLAUDE_SKILLS, CLAUDE_COMMANDS)

if "codex" in agents or "dsh" in agents:
    sync_skill_dir(plan, SHARED_SKILLS)
else:
    prune_generated(plan, SHARED_SKILLS)

if "codex" in agents:
    sync_codex_commands(plan)
else:
    prune_generated(plan, CODEX_COMMAND_SKILLS)

if "dsh" in agents:
    sync_dsh_commands(plan)
else:
    prune_generated(plan, DSH_COMMANDS)
```

旧 `.agents/skills/aidp-cmd` 必须在所有模式中作为已知生成入口清理；用户自有同名目录若无生成证据则保留并 WARN。

- [ ] **Step 5: 删除路由 CLI 和自检断言**

移除 `router_skill()`、`sync_router_source()`、`router_source_drift()`、`--router-sync`、`--router-check`。更新 `--self-check`，验证新的 Codex/DSH 路径、切换清理与项目自有内容保护。

- [ ] **Step 6: 运行专项测试**

Run:

```bash
python3 .aidp/scripts/tests/test_agent_sync.py
python3 .aidp/scripts/tests/test_agent_sync_router.py
python3 .aidp/scripts/agent_sync.py --self-check
```

Expected: 三条命令均 exit 0，测试汇总无 failed。

- [ ] **Step 7: 提交实现**

```bash
git add .aidp/scripts/agent_sync.py
git commit -m "feat: generate native agent command adapters" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 3: 原生装配 `chrome-devtools-mcp`

**Files:**
- Modify: `.aidp/scripts/agent_sync.py`
- Modify: `.aidp/scripts/tests/test_agent_sync.py`

- [ ] **Step 1: 运行 Task 1 的插件断言确认失败**

Run:

```bash
python3 .aidp/scripts/tests/test_agent_sync.py
```

Expected: FAIL，Codex 仍生成 `.agents/plugins` marketplace，DSH 仍生成 `.dsh/skills`，且 Codex 没有项目级 `[mcp_servers.chrome-devtools]`。

- [ ] **Step 2: 将 Codex 插件包装改成技能集合与 MCP 配置**

删除 `CODEX_PLUGINS`、`CODEX_MARKETPLACE` 和 `sync_codex_plugins()` 的 marketplace 生成逻辑，定义：

```python
CODEX_PLUGIN_SKILLS = ".codex/skills"


def sync_codex_plugin_skills(plan: Plan, plugins: list[Path]) -> list[str]:
    generated: list[str] = []
    keep: set[str] = set()
    for plugin in plugins:
        source = plugin / "skills"
        if not source.is_dir():
            continue
        destination = plan.root / CODEX_PLUGIN_SKILLS / plugin.name / "skills"
        plan.link_dir(destination, source)
        keep.add(plugin.name)
        generated.append(f"{CODEX_PLUGIN_SKILLS}/{plugin.name}/skills")
    _prune(plan, plan.root / CODEX_PLUGIN_SKILLS, keep)
    return generated
```

将每个插件的 `_plugin_mcp()` 结果合并进 `.codex/config.toml`。对当前插件生成的受管块固定为：

```toml
# >>> AIDP-MCP chrome-devtools
[mcp_servers.chrome-devtools]
command = "npx"
args = ["chrome-devtools-mcp@1.6.0"]
# <<< AIDP-MCP chrome-devtools
```

更新时只替换同名 AIDP 受管块，保留用户其他 TOML 内容；插件不再存在时只删除对应受管块。

- [ ] **Step 3: 将 DSH 插件 SKILL 合并到 `.agents/skills`**

删除 `DSH_SKILLS` 和 `.dsh/skills` 生成逻辑。扩展共享 SKILL 同步，使 DSH 启用时把插件目录内每个含 `SKILL.md` 的子目录按原名称链接到 `.agents/skills/<skill>`：

```python
def plugin_skill_dirs(plugins: list[Path]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for plugin in plugins:
        source = plugin / "skills"
        if not source.is_dir():
            continue
        for skill in sorted(source.iterdir()):
            if not (skill / "SKILL.md").is_file():
                continue
            if skill.name in result:
                raise SystemExit(f"[agent_sync] 插件 SKILL 重名: {skill.name}")
            result[skill.name] = skill
    return result
```

合并前同时检查插件 SKILL 与 `.aidp/skills/` 公共 SKILL 是否重名；重名时 exit 2，不覆盖现有入口。`sync_dsh_plugins()` 继续把 MCP server 汇总到 `.dsh/mcp.json`。

- [ ] **Step 4: 更新分支与清理行为**

- Claude 启用：保持 `sync_claude_plugins()` 不变。
- Codex 启用：调用 `sync_codex_plugin_skills()` 和 Codex MCP 配置合并器。
- DSH 启用：公共 `.agents/skills` 同步时包含插件 SKILL，并调用 `sync_dsh_plugins()`。
- Agent 未启用：只清理有 AIDP 生成证据的对应插件入口和 MCP 受管块。
- Codex+DSH：`.codex/skills/chrome-devtools-mcp/skills/` 与 `.agents/skills/<plugin-skill>/` 均指向 `.aidp/plugins/chrome-devtools-mcp/skills/`；Codex 按 `.codex/skills` 优先级使用专属入口。

- [ ] **Step 5: 运行插件与适配器测试**

Run:

```bash
python3 .aidp/scripts/tests/test_agent_sync.py
python3 .aidp/scripts/agent_sync.py --self-check
```

Expected: exit 0；不存在 `.agents/plugins/marketplace.json` 和 `.dsh/skills`，三种 Agent 的插件路径与 MCP 配置断言通过。

- [ ] **Step 6: 提交**

```bash
git add .aidp/scripts/agent_sync.py .aidp/scripts/tests/test_agent_sync.py
git commit -m "refactor: adapt browser plugin per agent" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 4: 更新无人值守命令入口

**Files:**
- Modify: `.aidp/scripts/agent_loop.sh`
- Modify: `.aidp/scripts/tests/test_aidp_scheduler.py`

- [ ] **Step 1: 添加失败测试**

在 `test_aidp_scheduler.py` 中执行 `agent_loop.sh --once` 的命令渲染路径，锁定：

```python
assert codex_prompt == "$sprint-autopilot --unattended --no-loop"
assert dsh_prompt == "/sprint-autopilot --unattended --no-loop"
assert "aidp-cmd" not in codex_prompt
assert "aidp-cmd" not in dsh_prompt
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python3 .aidp/scripts/tests/test_aidp_scheduler.py
```

Expected: FAIL，实际 prompt 仍含 `$aidp-cmd` 或 `/aidp-cmd`。

- [ ] **Step 3: 修改原生命令 prompt**

将 case 分支改为：

```bash
case "$agent" in
  codex)  prompt="\$${cmd} ${args}"; default_exec='codex exec --sandbox workspace-write {prompt}' ;;
  dsh)    prompt="/${cmd} ${args}";   default_exec='' ;;
  claude) prompt="/${cmd} ${args}";   default_exec='claude -p --permission-mode acceptEdits {prompt}' ;;
  *) echo "[agent_loop] 未知 Agent: $agent" >&2; exit 2 ;;
esac
```

同步删除文件头部关于路由 SKILL 传递 `$ARGUMENTS` 的说明，保留 export 供命令正文读取。

- [ ] **Step 4: 运行调度测试**

Run:

```bash
python3 .aidp/scripts/tests/test_aidp_scheduler.py
```

Expected: exit 0，无 failed。

- [ ] **Step 5: 提交**

```bash
git add .aidp/scripts/agent_loop.sh .aidp/scripts/tests/test_aidp_scheduler.py
git commit -m "fix: use native commands in unattended loops" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 5: 实现 DSH init 插件安装

**Files:**
- Modify: `.aidp/skills/aidp-code-engineer/scripts/scaffold.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`

- [ ] **Step 1: 添加插件安装测试**

用临时目录中的假 `dsh` 可执行文件记录 argv，覆盖：

```python
expected = ["plugin", "--profile", "web", "add", "dsh-plugin-commands@latest"]
```

四个场景：DSH init 调用一次；Claude/Codex init 不调用；DSH migrate/upgrade 不调用；退出非零时 scaffold 返回成功但报告含 WARN 和完整重试命令。

- [ ] **Step 2: 运行单测确认失败**

Run:

```bash
python3 -m unittest .aidp.skills.aidp-code-engineer.scripts.tests.test_scaffold_modes
```

若路径中的连字符导致模块导入失败，使用：

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
```

Expected: FAIL，尚无插件安装调用。

- [ ] **Step 3: 实现安装函数**

在 `scaffold.py` 新增：

```python
DSH_COMMAND_PLUGIN = [
    "dsh", "plugin", "--profile", "web", "add", "dsh-plugin-commands@latest",
]


def install_dsh_command_plugin(mode: str, agents: list[str], warnings: list[str]) -> None:
    if mode != "init" or "dsh" not in agents:
        return
    try:
        proc = subprocess.run(DSH_COMMAND_PLUGIN, text=True, capture_output=True, check=False)
    except OSError as exc:
        warnings.append(
            "DSH 命令插件安装失败："
            f"{exc}；请重试：{' '.join(DSH_COMMAND_PLUGIN)}"
        )
        return
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()
        warnings.append(
            f"DSH 命令插件安装失败：{detail}；请重试：{' '.join(DSH_COMMAND_PLUGIN)}"
        )
```

接入点位于 Agent 选择完成、适配层同步之前。复用现有 warning/report 机制，不新增持久状态文件。

- [ ] **Step 4: 运行脚手架模式测试**

Run:

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
```

Expected: exit 0，所有 DSH 插件场景通过。

- [ ] **Step 5: 提交**

```bash
git add .aidp/skills/aidp-code-engineer/scripts/scaffold.py .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
git commit -m "feat: install dsh command plugin on init" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 6: 清理旧路由真源并更新脚手架校验

**Files:**
- Modify: `.aidp/skills/aidp-code-engineer/scripts/scaffold.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/scaffold_lib.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/verify.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/tests/test_mirror.py`
- Delete: `.aidp/skills/aidp-cmd/SKILL.md`
- Delete: `.aidp/skills/aidp-cmd/agents/openai.yaml`

- [ ] **Step 1: 添加旧路由迁移与 verify 失败测试**

覆盖：

```python
assert not (project / ".aidp/skills/aidp-cmd").exists()
assert backup.exists()  # 仅用户修改场景
assert adapter_mode(project) == "copy"  # Codex-only 与 DSH-only copy 项目
```

同时将 `test_mirror.py` 期望改为 bundle 中不存在 `aidp/skills/aidp-cmd`，manifest 不再需要该目录的特殊豁免。

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_mirror.py
```

Expected: FAIL，旧路由仍存在，verify 仍只探测旧适配目录。

- [ ] **Step 3: 实现旧真源迁移**

在 `scaffold.py` 增加 `cleanup_obsolete_router()`：

```python
def cleanup_obsolete_router(root: Path, backup_root: Path, warnings: list[str]) -> None:
    router = root / ".aidp/skills/aidp-cmd"
    if not router.exists():
        return
    skill = router / "SKILL.md"
    generated = skill.is_file() and "命令表由 .aidp/scripts/agent_sync.py" in skill.read_text(
        encoding="utf-8", errors="replace"
    )
    if not generated:
        destination = backup_root / ".aidp/skills/aidp-cmd"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(router, destination, dirs_exist_ok=True)
        warnings.append(f"旧命令路由已备份：{destination}")
    shutil.rmtree(router)
```

使用脚手架已有备份根目录，不创建第二套备份命名规则；备份失败时捕获异常、保留源目录并 WARN。

- [ ] **Step 4: 移除路由特殊逻辑**

- 删除 `scaffold_lib.py` 中 `FINGERPRINT_EXEMPT = ("skills/aidp-cmd/",)`；若该常量无其他用途，一并删除辅助函数并修调用方。
- 删除 `verify.py` 中的路由源校验函数及主流程调用。
- `_adapter_mode()` 探测加入 `.codex/aidp/skills` 和 `.dsh/commands`。
- 删除 `.aidp/skills/aidp-cmd/` 源目录。

- [ ] **Step 5: 运行脚手架专项测试**

Run:

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_mirror.py
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
```

Expected: 全部 exit 0。

- [ ] **Step 6: 提交**

```bash
git add .aidp/skills/aidp-code-engineer/scripts .aidp/skills/aidp-cmd
git commit -m "refactor: retire aidp command router" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 7: 同步维护文档与下发契约

**Files:**
- Modify: `AGENTS.md`
- Modify: `.aidp/AIDP-AGENTS.md`
- Modify: `README.md`
- Modify: `.aidp/reference/agent-tools.md`
- Modify: `.aidp/reference/skills.md`
- Modify: `.aidp/reference/README.md`
- Modify: `.aidp/reference/命令速查.md`
- Modify: `.aidp/scripts/README.md`
- Modify: `.aidp/scripts/tests/README.md`
- Modify: `.aidp/hooks/README.md`
- Modify: `.aidp/agents/aidp-compliance.md`
- Modify: `.aidp/skills/aidp-code-engineer/SKILL.md`
- Modify: `docs/init/00_AIDP范式主文档.md`
- Modify: `docs/init/README.md`
- Modify: `docs/init/03_memory文件详细规范.md`
- Modify: `docs/init/06_版本与用户目录约定.md`

- [ ] **Step 1: 扫描所有旧路由引用作为红灯基线**

Run:

```bash
rg -n "aidp-cmd|router-sync|router-check|\.agents/skills.*命令路由|\.agents/plugins|\.dsh/skills" \
  AGENTS.md README.md .aidp docs/init
```

Expected: 返回现存路由引用，作为逐项清理清单。

- [ ] **Step 2: 更新三 Agent 对照表**

所有权威说明统一为：

```text
Claude Code: 公共 SKILL=.claude/skills；命令=.claude/commands；插件=.claude/plugins/chrome-devtools-mcp；调用=/<command>
Codex: 公共 SKILL=.agents/skills；命令=.codex/aidp/skills；浏览器插件 SKILL=.codex/skills/chrome-devtools-mcp/skills；调用=$<command>
DSH: 公共与浏览器插件 SKILL=.agents/skills；命令=.dsh/commands；调用=/<command>
```

DSH 初始化依赖只陈述当前行为：脚手架 init 尝试执行 `dsh plugin --profile web add dsh-plugin-commands@latest`，失败时 WARN 并给出重试命令。

- [ ] **Step 3: 删除维护者路由说明和测试表旧语义**

`AGENTS.md` 不再要求刷新 `aidp-cmd`；测试 README 中 `test_agent_sync_router.py` 描述改为“原生命令生成 + 参数保真 + gitignore 托管”。正文只描述当前行为，不写“已移除/曾使用/迁移自”。

- [ ] **Step 4: 运行引用扫描确认清零**

Run:

```bash
rg -n "aidp-cmd|router-sync|router-check|\.agents/plugins|\.dsh/skills" AGENTS.md README.md .aidp docs/init \
  --glob '!skills/aidp-code-engineer/assets/**'
```

Expected: 无输出；测试 fixture 中确需验证旧路由迁移的字符串可保留，并在命令中单独排除测试目录核验正文。

- [ ] **Step 5: 提交文档**

```bash
git add AGENTS.md README.md .aidp/AIDP-AGENTS.md .aidp/reference .aidp/scripts/README.md \
  .aidp/scripts/tests/README.md .aidp/hooks .aidp/agents/aidp-compliance.md \
  .aidp/skills/aidp-code-engineer/SKILL.md docs/init
git commit -m "docs: document native agent command paths" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 8: 重建下发模板与 bundle

**Files:**
- Generated: `.aidp/skills/aidp-code-engineer/assets/AGENTS.md.tpl`
- Generated: `.aidp/skills/aidp-code-engineer/assets/aidp/**`
- Generated: `.aidp/skills/aidp-code-engineer/assets/CONTRACT_MANIFEST.json`

- [ ] **Step 1: 同步下发记忆模板**

Run:

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/sync_memory_md.py
```

Expected: exit 0，`assets/AGENTS.md.tpl` 反映新的三 Agent 命令目录。

- [ ] **Step 2: 镜像模板到 bundle**

Run:

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py
```

Expected: exit 0，bundle 不含 `aidp/skills/aidp-cmd`，manifest 与当前版本一致。

- [ ] **Step 3: 做镜像干运行校验**

Run:

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py --check
```

Expected: exit 0，无漂移。

- [ ] **Step 4: 提交生成物**

```bash
git add .aidp/skills/aidp-code-engineer/assets
git commit -m "chore(skill): sync aidp-code-engineer" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 9: 全量验证与收口

**Files:**
- Modify only if failures identify a defect in files already in this plan.

- [ ] **Step 1: 运行模板只读验证**

Run:

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/verify.py . --template --read-only
```

Expected: exit 0，镜像类 ERROR 为 0。

- [ ] **Step 2: 运行模板全量回归**

Run:

```bash
bash .aidp/scripts/tests/run.sh
```

Expected: exit 0，所有套件 passed，允许环境依赖明确标注的 skipped。

- [ ] **Step 3: 单独运行脚手架单测**

Run:

```bash
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
```

Expected: exit 0，无 failures/errors。

- [ ] **Step 4: 运行文档引用与开源卫生门**

Run:

```bash
python3 .aidp/scripts/check_code_symbol_refs.py
python3 .aidp/scripts/check_cli_invocation.py
python3 .aidp/scripts/check_private_markers.py
```

Expected: 三条命令均 exit 0。

- [ ] **Step 5: 检查工作区和提交范围**

Run:

```bash
git status --short
git log --oneline --decorate -10
```

Expected: 本计划涉及的文件均已提交；不提交、不删除与本任务无关的用户改动。

- [ ] **Step 6: 提交必要的验证修复**

仅当上述门禁暴露本计划内缺陷时执行：

```bash
git add -u -- \
  .aidp/scripts/agent_sync.py .aidp/scripts/agent_loop.sh .aidp/scripts/tests \
  .aidp/skills/aidp-code-engineer/scripts .aidp/skills/aidp-code-engineer/SKILL.md \
  AGENTS.md README.md .aidp/AIDP-AGENTS.md .aidp/reference .aidp/hooks \
  .aidp/agents/aidp-compliance.md docs/init .aidp/skills/aidp-code-engineer/assets
git commit -m "fix: close native command adapter regressions" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

不得通过放宽断言、跳过测试或修改版本号来制造绿灯。

## 实施约束

- 不推送任何提交。
- 不执行 `bump_version.py`；本轮没有版本号自增授权。
- 不手工编辑 `.aidp/skills/aidp-code-engineer/assets/`。
- 当前仓库大量文件在设计提交前为未跟踪状态；每次只暂存任务列出的文件，避免混入无关内容。
- 共享文件可能含此前审计修复，实施时基于当前内容做小范围编辑，不回退现有改动。
- 完成后明确报告：本变更属于下发行为变更，同版本下游不会自动覆盖已有契约，建议另行授权 bump patch。
