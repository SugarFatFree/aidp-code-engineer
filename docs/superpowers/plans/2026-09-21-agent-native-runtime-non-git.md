# Agent Native Runtime and Non-Git Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 下游项目不再保留根 `.aidp/`，按 Agent 生成 `.claude/aidp` 或 `.agents/aidp` 运行包，并让 init/migrate/upgrade/verify 与非 Git 开发链在 `vcs_mode=none` 下可用。

**Architecture:** 模板仓库继续以 `.aidp/` 为维护真源，脚手架把运行内核渲染为 Agent 原生目录中的受管实体副本。所有运行时路径通过 `AIDP_HOME` 或脚本自身位置解析；VCS 能力集中到 `vcs.py`，无 Git 时统一返回 `unsupported: vcs-disabled`。DSH 使用 `github:SugarFatFree/dsh-agent-extension` 提供 commands 与嵌套 SKILL 发现。

**Tech Stack:** Python 3 标准库、Bash、Markdown、JSON/TOML、现有自定义测试运行器。

---

## 文件结构与职责

- `.aidp/skills/aidp-code-engineer/scripts/runtime_layout.py`：运行包规划、渲染、manifest、规范化比较与原子安装。
- `.aidp/scripts/aidp_runtime.py`：模板真源和下游运行包中的运行根、项目根解析。
- `.aidp/scripts/vcs.py`：`git|none` 检测、开发者身份、unsupported 结果和 Git 命令边界。
- `.aidp/scripts/agent_sync.py`：基于已安装运行包生成 Agent 原生 commands、SKILL、plugin、hook 和配置，不依赖根 `.aidp/`。
- `.aidp/skills/aidp-code-engineer/scripts/scaffold.py`：init/migrate/upgrade 流程、旧 `.aidp` 迁移、DSH 扩展 ensure、非 Git 报告。
- `.aidp/skills/aidp-code-engineer/scripts/scaffold_lib.py`：运行包契约清单、受管文件保护和无 Git 文件操作。
- `.aidp/skills/aidp-code-engineer/scripts/verify.py`：Agent 原生运行包、双包一致性、VCS 能力和旧目录残留校验。
- `.aidp/scripts/check_runtime_paths.py`：运行契约中的硬编码 `.aidp/` 与未解析 `{{AIDP_HOME}}` 守卫。
- `.aidp/commands/`、`.aidp/flows/`、`.aidp/agents/`、`.aidp/rules/`、`.aidp/reference/`、`.aidp/skills/`、`.aidp/hooks/`、`.aidp/templates/`：维护真源，文本运行路径改用 `{{AIDP_HOME}}`。
- `.aidp/scripts/`：Python 使用 `aidp_runtime.py`，Shell 使用渲染后的 `AIDP_HOME`。
- `.aidp/skills/aidp-code-engineer/scripts/tests/`、`.aidp/scripts/tests/`：运行布局、迁移、VCS 降级和工作流回归。

### Task 1: 锁定无 `.aidp` 的下游目录契约

**Files:**
- Modify: `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`
- Modify: `.aidp/scripts/tests/test_agent_sync.py`
- Modify: `.aidp/scripts/tests/test_agent_sync_router.py`

- [ ] **Step 1: 增加 Claude-only 初始化红灯测试**

测试必须断言：

```python
assert not (project / ".aidp").exists()
assert (project / ".claude/aidp/scripts/agent_sync.py").is_file()
assert (project / ".claude/commands/sprint-dev.md").is_file()
assert (project / ".claude/skills/aidp-code-engineer/SKILL.md").is_file()
assert not (project / ".agents").exists()
```

同时读取 `.claude/aidp/.aidp-runtime.json`，断言 `schema == "aidp.runtime/v1"`、`source == "claude"`。

- [ ] **Step 2: 增加 Codex/DSH 初始化红灯测试**

```python
assert not (project / ".aidp").exists()
assert (project / ".agents/aidp/scripts/agent_sync.py").is_file()
assert (project / ".agents/skills/aidp-code-engineer/SKILL.md").is_file()
assert (project / ".codex/skills/aidp/sprint-dev/SKILL.md").is_file()
assert (project / ".dsh/commands/sprint-dev.md").is_file()
assert (project / ".agents/skills/chrome-devtools-mcp/skills/chrome-devtools/SKILL.md").is_file()
```

Codex+DSH 共用一份 `.agents/aidp`，不能复制两份 shared runtime。

- [ ] **Step 3: 增加多 Agent 一致性红灯测试**

同时启用 Claude、Codex、DSH 后：

```python
claude_manifest = json.loads((project / ".claude/aidp/.aidp-runtime.json").read_text())
shared_manifest = json.loads((project / ".agents/aidp/.aidp-runtime.json").read_text())
assert claude_manifest["version"] == shared_manifest["version"]
assert set(claude_manifest["files"]) == set(shared_manifest["files"])
```

规范化 `.claude/aidp` 与 `.agents/aidp` 后内容一致。

- [ ] **Step 4: 增加 managed-copy 断言**

对 init 的所有 Agent 组合断言生成目录和文件均不是 symlink：

```python
assert not (project / ".claude/aidp").is_symlink()
assert not (project / ".claude/commands/sprint-dev.md").is_symlink()
assert not (project / ".agents/aidp").is_symlink()
assert not (project / ".agents/skills/aidp-code-engineer").is_symlink()
```

`--adapter-mode link` 仍可传入，但报告 action 包含 `normalized:managed-copy`。

- [ ] **Step 5: 运行测试确认红灯**

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
python3 .aidp/scripts/tests/test_agent_sync.py
python3 .aidp/scripts/tests/test_agent_sync_router.py
```

Expected: FAIL，现有实现仍创建根 `.aidp` 并依赖链接真源。

- [ ] **Step 6: 提交测试**

```bash
git add .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py \
  .aidp/scripts/tests/test_agent_sync.py .aidp/scripts/tests/test_agent_sync_router.py
git commit -m "test: define agent-native runtime layout" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 2: 实现运行根与 VCS 基础模块

**Files:**
- Create: `.aidp/scripts/aidp_runtime.py`
- Create: `.aidp/scripts/vcs.py`
- Create: `.aidp/scripts/tests/test_runtime_and_vcs.py`
- Modify: `.aidp/scripts/tests/run.sh`
- Modify: `.aidp/scripts/tests/README.md`

- [ ] **Step 1: 编写运行根解析测试**

覆盖三种脚本位置：

```python
assert runtime_root(Path("/p/.aidp/scripts/x.py")) == Path("/p/.aidp")
assert runtime_root(Path("/p/.claude/aidp/scripts/x.py")) == Path("/p/.claude/aidp")
assert runtime_root(Path("/p/.agents/aidp/scripts/x.py")) == Path("/p/.agents/aidp")
```

`project_root()` 分别返回 `/p`，不得调用 Git。

- [ ] **Step 2: 编写 VCS 模式和身份测试**

```python
assert detect_mode(non_git_root) == "none"
assert detect_mode(git_root) == "git"
assert developer_identity(non_git_root, "alice") == "alice"
```

身份回落依次覆盖显式用户、Git config、`AIDP_USER`、`getpass.getuser()`。

- [ ] **Step 3: 编写 unsupported 契约测试**

```python
result = unsupported("push")
assert result == {
    "status": "unsupported",
    "reason": "vcs-disabled",
    "capability": "push",
}
assert EXIT_UNSUPPORTED == 3
```

- [ ] **Step 4: 实现 `aidp_runtime.py`**

公开接口：

```python
def runtime_root(script_file: Path | str = __file__) -> Path:
    path = Path(script_file).resolve()
    if path.parent.name != "scripts":
        raise RuntimeError(f"无法从脚本位置解析 AIDP 运行根: {path}")
    root = path.parent.parent
    if root.name != "aidp":
        raise RuntimeError(f"非法 AIDP 运行根: {root}")
    return root


def project_root(script_file: Path | str = __file__) -> Path:
    root = runtime_root(script_file)
    parent = root.parent
    if parent.name in {".claude", ".agents"}:
        return parent.parent
    if root.name == ".aidp":
        return root.parent
    raise RuntimeError(f"无法解析项目根: {root}")
```

允许 `AIDP_HOME`、`AIDP_PROJECT_ROOT` 显式覆盖，但覆盖路径必须位于项目内且不能经过 symlink。

- [ ] **Step 5: 实现 `vcs.py`**

```python
EXIT_UNSUPPORTED = 3


def detect_mode(root: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return "git" if proc.returncode == 0 and proc.stdout.strip() == "true" else "none"


def unsupported(capability: str) -> dict:
    return {"status": "unsupported", "reason": "vcs-disabled", "capability": capability}
```

捕获 `OSError` 和 `TimeoutExpired` 并返回 `none`。

- [ ] **Step 6: 登记并运行测试**

```bash
python3 .aidp/scripts/tests/test_runtime_and_vcs.py
python3 .aidp/scripts/tests/test_guard_scripts.py
```

Expected: 运行根、非 Git、Git 身份和路径越界测试全部通过。

- [ ] **Step 7: 提交**

```bash
git add .aidp/scripts/aidp_runtime.py .aidp/scripts/vcs.py \
  .aidp/scripts/tests/test_runtime_and_vcs.py .aidp/scripts/tests/run.sh \
  .aidp/scripts/tests/README.md
git commit -m "feat: add runtime and vcs capability layers" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 3: 实现运行包渲染器

**Files:**
- Create: `.aidp/skills/aidp-code-engineer/scripts/runtime_layout.py`
- Create: `.aidp/skills/aidp-code-engineer/scripts/tests/test_runtime_layout.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/scaffold_lib.py`

- [ ] **Step 1: 编写运行包内容测试**

源 bundle 为 `assets/aidp/`，渲染后只包含：

```python
RUNTIME_DIRS = (
    "agents", "flows", "hooks", "reference", "rules", "scripts", "templates",
)
```

断言 `commands`、`skills`、`plugins`、`memory` 和 `scripts/tests` 不在运行包。

- [ ] **Step 2: 编写文本渲染测试**

```python
source = "python3 {{AIDP_HOME}}/scripts/check.py\n"
assert render_text(source, ".claude/aidp") == "python3 .claude/aidp/scripts/check.py\n"
assert render_text(source, ".agents/aidp") == "python3 .agents/aidp/scripts/check.py\n"
```

未解析 `{{UNKNOWN_TOKEN}}`、非迁移语义 `.aidp/`、绝对模板仓库路径均拒绝输出。

- [ ] **Step 3: 编写 manifest 测试**

```python
manifest = build_runtime_manifest(runtime_dir, version="V1.0.0", source="claude")
assert manifest["schema"] == "aidp.runtime/v1"
assert manifest["source"] == "claude"
assert list(manifest["files"]) == sorted(manifest["files"])
```

规范化函数把 `.claude/aidp` 和 `.agents/aidp` 还原为 `{{AIDP_HOME}}` 后比较。

- [ ] **Step 4: 实现渲染器接口**

```python
RUNTIME_MANIFEST = ".aidp-runtime.json"
RUNTIME_HOME = {"claude": ".claude/aidp", "shared": ".agents/aidp"}


def render_runtime(source_root: Path, destination: Path, home: str,
                   version: str, source: str) -> dict:
    stage = destination.with_name(destination.name + ".aidp-stage")
    previous = destination.with_name(destination.name + ".aidp-previous")
    remove_tree_safely(stage)
    remove_tree_safely(previous)
    stage.mkdir(parents=True)
    try:
        for dirname in RUNTIME_DIRS:
            render_tree(source_root / dirname, stage / dirname, home)
        manifest = build_runtime_manifest(stage, version=version, source=source)
        write_json(stage / RUNTIME_MANIFEST, manifest)
        validate_runtime(stage, expected_home=home)
        if destination.exists():
            os.replace(destination, previous)
        try:
            os.replace(stage, destination)
        except Exception:
            if previous.exists():
                os.replace(previous, destination)
            raise
        remove_tree_safely(previous)
        return manifest
    finally:
        remove_tree_safely(stage)
```

同一模块公开并测试 `render_tree()`、`build_runtime_manifest()`、`validate_runtime()`、`normalize_runtime()`、`remove_tree_safely()`。所有删除函数拒绝 symlink 祖先和项目根外路径。

- [ ] **Step 5: 实现用户修改保护**

现有运行包有 manifest 时逐文件比对；本地修改项先备份到脚手架现有 backup 根。无 manifest 的同名目录视为用户内容并 fail closed。

- [ ] **Step 6: 运行测试**

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_runtime_layout.py
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
```

Expected: 渲染、原子失败、用户修改备份、双包规范化测试通过。

- [ ] **Step 7: 提交**

```bash
git add .aidp/skills/aidp-code-engineer/scripts/runtime_layout.py \
  .aidp/skills/aidp-code-engineer/scripts/tests/test_runtime_layout.py \
  .aidp/skills/aidp-code-engineer/scripts/scaffold_lib.py
git commit -m "feat: render agent-native runtime packages" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 4: 迁移运行时路径契约

**Files:**
- Create: `.aidp/scripts/check_runtime_paths.py`
- Create: `.aidp/scripts/tests/test_runtime_paths.py`
- Modify: `.aidp/{commands,flows,agents,rules,reference,skills,hooks,templates}/**`
- Modify: `.aidp/scripts/*.py`
- Modify: `.aidp/scripts/*.sh`
- Modify: `.aidp/scripts/tests/run.sh`
- Modify: `.aidp/scripts/tests/README.md`

- [ ] **Step 1: 编写路径守卫红灯测试**

守卫扫描下发契约并报出：

```text
hardcoded-runtime-path   # 非迁移语义 `.aidp/`
unresolved-runtime-home # 生成物残留 `{{AIDP_HOME}}`
```

允许项只包括 `LEGACY_AIDP_DIR = ".aidp"`、迁移测试 fixture 和模板维护说明。

- [ ] **Step 2: 转换 Markdown/Shell 运行路径**

将下发文本中的实际运行引用从：

```text
.aidp/scripts/x.py
.aidp/flows/x.md
.aidp/reference/x.md
```

改为：

```text
{{AIDP_HOME}}/scripts/x.py
{{AIDP_HOME}}/flows/x.md
{{AIDP_HOME}}/reference/x.md
```

Shell 文件开头统一解析 `AIDP_HOME`，不得使用当前目录猜测。

- [ ] **Step 3: 转换 Python 项目根解析**

所有下发 Python 脚本导入：

```python
from aidp_runtime import project_root, runtime_root
```

使用 `project_root(__file__)` 替代按固定 `parents[N]` 层级和 Git 根解析；运行包内部资源使用 `runtime_root(__file__)`。

- [ ] **Step 4: 保留迁移字面量**

迁移代码只能通过命名常量表达：

```python
LEGACY_AIDP_DIR = ".aidp"
```

守卫允许该常量，不允许普通运行路径继续出现 `.aidp/`。

- [ ] **Step 5: 运行守卫和全量脚本测试**

```bash
python3 .aidp/scripts/check_runtime_paths.py
python3 .aidp/scripts/tests/test_runtime_paths.py
bash .aidp/scripts/tests/run.sh
```

Expected: 模板真源可在 `.aidp` 中运行，渲染后的 Claude/shared fixture 无硬编码和未解析 token。

- [ ] **Step 6: 提交**

```bash
git add .aidp/commands .aidp/flows .aidp/agents .aidp/rules .aidp/reference \
  .aidp/skills .aidp/hooks .aidp/templates .aidp/scripts
git commit -m "refactor: abstract downstream runtime paths" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 5: 重构 Agent 装配到运行包

**Files:**
- Modify: `.aidp/scripts/agent_sync.py`
- Modify: `.aidp/scripts/tests/test_agent_sync.py`
- Modify: `.aidp/scripts/tests/test_agent_sync_router.py`

- [ ] **Step 1: 改造 source discovery**

`agent_sync.py` 使用 `runtime_root(__file__)` 获取 `.claude/aidp` 或 `.agents/aidp`，commands/skills/plugins 由脚手架传入或按 Agent 原生目录读取受管源清单，不再访问项目根 `.aidp`。

- [ ] **Step 2: managed-copy 替代链接**

所有 `Plan.link_file()`、`Plan.link_dir()` 的 Agent 入口改为受管复制或生成。`--mode link` 解析为 copy，并在 JSON actions 增加：

```json
{"action": "normalized", "from": "link", "to": "managed-copy"}
```

- [ ] **Step 3: DSH namespaced 插件 SKILL**

插件技能目标：

```text
.agents/skills/chrome-devtools-mcp/skills/<skill>/SKILL.md
```

不得继续生成 `.agents/skills/<skill>` 扁平入口。Codex 从 `.agents/skills` 递归发现同一集合。

- [ ] **Step 4: 更新命令生成路径**

- Claude：`.claude/commands`
- Codex：`.codex/skills/aidp`
- DSH：`.dsh/commands`

Codex 适配前言读取正确 `AIDP_HOME` 下的命令真源映射，不引用根 `.aidp/commands`。

- [ ] **Step 5: 运行专项测试**

```bash
python3 .aidp/scripts/tests/test_agent_sync.py
python3 .aidp/scripts/tests/test_agent_sync_router.py
python3 .aidp/scripts/agent_sync.py --self-check
```

Expected: 无 symlink、无根 `.aidp` 依赖、嵌套插件 SKILL 和三类命令全部通过。

- [ ] **Step 6: 提交**

```bash
git add .aidp/scripts/agent_sync.py .aidp/scripts/tests/test_agent_sync.py \
  .aidp/scripts/tests/test_agent_sync_router.py
git commit -m "refactor: sync agents from native runtime packages" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 6: 重构 scaffold init 与 DSH 扩展

**Files:**
- Modify: `.aidp/skills/aidp-code-engineer/scripts/scaffold.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`

- [ ] **Step 1: 移除 Git 硬门测试**

非 Git 临时目录执行 init：

```python
result = run_scaffold(root, "init", agents=["claude"], user="alice")
assert result.returncode == 0
assert result.json["vcs_mode"] == "none"
assert not (root / ".aidp").exists()
```

同时从 PATH 隐藏 `git`，结果仍成功。

- [ ] **Step 2: 接入运行包渲染**

init 根据 Agent 集合调用：

```python
if "claude" in agents:
    render_runtime(bundle / "aidp", root / ".claude/aidp", ".claude/aidp", version, "claude")
if {"codex", "dsh"} & set(agents):
    render_runtime(bundle / "aidp", root / ".agents/aidp", ".agents/aidp", version, "shared")
```

然后从 bundle 直接生成 commands、skills、plugins，不创建根 `.aidp`。

- [ ] **Step 3: 替换 DSH 扩展命令**

常量固定为：

```python
DSH_AGENT_EXTENSION = [
    "dsh", "plugin", "--profile", "web", "add",
    "github:SugarFatFree/dsh-agent-extension",
]
```

init、migrate、upgrade 只要包含 DSH 都调用一次。使用 `stdin=DEVNULL`、120 秒 timeout、300 字符诊断摘要。失败 WARN 中包含完整重试命令和 `dsh_extensions=unavailable`。

- [ ] **Step 4: 删除旧插件生产引用**

生产代码、文档和 assets 中不得出现旧包名。迁移反向测试允许保留字符串并明确为旧名称。

- [ ] **Step 5: 运行脚手架测试**

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
```

Expected: Git/非 Git、三模式、DSH 三模式 ensure、失败继续、运行包布局全部通过。

- [ ] **Step 6: 提交**

```bash
git add .aidp/skills/aidp-code-engineer/scripts/scaffold.py \
  .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
git commit -m "feat: initialize agent-native runtime packages" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 7: 实现旧 `.aidp` 原子迁移

**Files:**
- Modify: `.aidp/skills/aidp-code-engineer/scripts/scaffold.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/scaffold_lib.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`

- [ ] **Step 1: 编写成功迁移测试**

旧项目含纯生成 `.aidp`：migrate/upgrade 后新运行包存在，根 `.aidp` 不存在，业务 `memory/docs/code` 保持。

- [ ] **Step 2: 编写用户修改备份测试**

修改旧 `.aidp/commands/sprint-dev.md` 并增加自有文件，迁移后备份目录完整保留修改内容，报告逐项列出备份路径。

- [ ] **Step 3: 编写回滚测试**

模拟备份失败、渲染失败、manifest 校验失败和第二运行包安装失败：

```python
assert (root / ".aidp").exists()
assert old_tree_hash(root / ".aidp") == before_hash
assert not partial_native_runtime_exists(root)
```

- [ ] **Step 4: 实现 staged migration**

流程函数：

```python
def migrate_legacy_runtime(root: Path, agents: list[str], report: Report) -> bool:
    legacy = root / LEGACY_AIDP_DIR
    if not legacy.exists():
        return True
    backup = backup_legacy_tree(root, legacy, report)
    if backup is None:
        report.warn("旧 AIDP 运行目录备份失败，保留原目录")
        return False
    installed: list[Path] = []
    try:
        for source, destination, home, source_kind in runtime_specs(root, agents):
            render_runtime(source, destination, home, report.scaffold_version, source_kind)
            installed.append(destination)
        validate_installed_runtimes(root, agents)
        remove_tree_safely(legacy)
        return True
    except Exception as exc:
        for destination in reversed(installed):
            restore_previous_runtime(destination)
        restore_legacy_tree(backup, legacy)
        report.warn(f"运行目录迁移失败，已回滚：{exc}")
        return False
```

本任务在 `scaffold.py` 中定义并测试 `backup_legacy_tree()`、`runtime_specs()`、`validate_installed_runtimes()`、`restore_previous_runtime()`、`restore_legacy_tree()`。显式 migrate 必须执行布局迁移，不受“当前版本等于脚手架版本”阻挡。

- [ ] **Step 5: 运行测试**

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
```

Expected: 成功、备份、四类回滚和同版本 migrate 通过。

- [ ] **Step 6: 提交**

```bash
git add .aidp/skills/aidp-code-engineer/scripts/scaffold.py \
  .aidp/skills/aidp-code-engineer/scripts/scaffold_lib.py \
  .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
git commit -m "feat: migrate legacy aidp runtime atomically" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 8: 重构 verify 支持新布局和非 Git

**Files:**
- Modify: `.aidp/skills/aidp-code-engineer/scripts/verify.py`
- Modify: `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`

- [ ] **Step 1: 增加新布局 verify 测试**

覆盖 Claude-only、shared-only、双运行包、一包漂移、版本不一致、未解析 token、非迁移根 `.aidp` 残留。

- [ ] **Step 2: 增加非 Git verify 测试**

非 Git 项目：

```python
assert verify(root).returncode == 0
assert "vcs_mode=none" in verify(root).stdout
assert "Git 跟踪检查: unsupported" in verify(root).stdout
assert "Git 跟踪检查通过" not in verify(root).stdout
```

- [ ] **Step 3: 实现运行包校验**

读取 `.aidp-runtime.json`，验证文件哈希、版本、source 和双包规范化一致性。新布局项目根 `.aidp` 无迁移台账时 ERROR。

- [ ] **Step 4: 实现能力态输出**

Git 跟踪、凭据跟踪、备份跟踪等检查在 `vcs_mode=none` 下输出 `unsupported: vcs-disabled`，不加入通过计数。

- [ ] **Step 5: 运行测试**

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
```

Expected: 新布局、双运行包和非 Git verify 用例全部通过。

- [ ] **Step 6: 提交**

```bash
git add .aidp/skills/aidp-code-engineer/scripts/verify.py \
  .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
git commit -m "feat: verify native runtimes without git" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 9: 将 Git 依赖脚本接入 VCS 能力层

**Files:**
- Modify: `.aidp/scripts/{commit_gate,classify_commit_change,classify_push,check_memory_loss,check_index_staleness,autopilot-preflight,cicd_watch,baseline_archive}.py`
- Modify: `.aidp/scripts/tests/test_commit_gate.py`
- Modify: `.aidp/scripts/tests/test_field_level_and_evidence.py`
- Modify: `.aidp/scripts/tests/test_unattended_recovery.py`
- Modify: `.aidp/scripts/tests/test_baseline_archive.py`

- [ ] **Step 1: 为每个 Git 能力编写非 Git红灯**

统一断言：

```python
assert proc.returncode == 3
payload = json.loads(proc.stdout or proc.stderr)
assert payload["status"] == "unsupported"
assert payload["reason"] == "vcs-disabled"
```

capability 分别使用 `commit`、`push`、`diff`、`cicd-sha`、`tag`。

- [ ] **Step 2: 接入 `vcs.require_git()`**

每个脚本在执行 Git 语义前：

```python
mode = vcs.detect_mode(root)
if mode == "none":
    print(json.dumps(vcs.unsupported("diff"), ensure_ascii=False))
    return vcs.EXIT_UNSUPPORTED
```

不得捕获后改写成成功或工作区干净。

- [ ] **Step 3: 更新编排语义**

- 开发链遇到 unsupported：记录并继续其他非 Git 步骤。
- 发布/push/tag：unsupported 后 fail closed，最终不得标记成功。
- CICD SHA 提供方：unsupported，不触发 provider。

- [ ] **Step 4: 运行专项**

```bash
python3 .aidp/scripts/tests/test_commit_gate.py
python3 .aidp/scripts/tests/test_field_level_and_evidence.py
python3 .aidp/scripts/tests/test_unattended_recovery.py
python3 .aidp/scripts/tests/test_baseline_archive.py
python3 .aidp/scripts/cicd_watch.py --selftest
```

Expected: 非 Git 全部结构化 unsupported，Git fixture 现有行为通过。

- [ ] **Step 5: 提交**

```bash
git add .aidp/scripts/commit_gate.py .aidp/scripts/classify_commit_change.py \
  .aidp/scripts/classify_push.py .aidp/scripts/check_memory_loss.py \
  .aidp/scripts/check_index_staleness.py .aidp/scripts/autopilot-preflight.py \
  .aidp/scripts/cicd_watch.py .aidp/scripts/baseline_archive.py \
  .aidp/scripts/tests/test_commit_gate.py .aidp/scripts/tests/test_field_level_and_evidence.py \
  .aidp/scripts/tests/test_unattended_recovery.py .aidp/scripts/tests/test_baseline_archive.py
git commit -m "feat: degrade git capabilities explicitly" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 10: 更新命令与工作流的非 Git 行为

**Files:**
- Modify: `.aidp/commands/{sprint-dev,sprint-test,sprint-autopilot,sprint-aiauto-test,sprint-close,version}.md`
- Modify: `.aidp/flows/{sprint-autopilot,sprint-aiauto-test,sprint-dev,sprint-close}/**`
- Modify: `.aidp/scripts/tests/test_command_skill_contracts.py`
- Modify: `.aidp/scripts/tests/test_unattended_recovery.py`

- [ ] **Step 1: 增加文档契约测试**

检查每个命令明确消费 `vcs_mode`：

- `sprint-dev/test`：Git 差异类检查 unsupported，但继续开发/本地测试。
- `sprint-autopilot`：commit/push/CICD 节点 unsupported，落账并跳过；不冻结整个开发链。
- `sprint-close`：本地文档收口可完成，Git 发布状态 unsupported。
- `version`：tag/push 发布 fail closed，不得输出发布成功。

- [ ] **Step 2: 更新命令和 flow**

统一结果表述：

```text
状态：unsupported
原因：vcs-disabled
处理：本地步骤继续 / 发布动作停止
```

不得使用“通过”“工作区干净”“已推送”。

- [ ] **Step 3: 运行契约测试**

```bash
python3 .aidp/scripts/tests/test_command_skill_contracts.py
python3 .aidp/scripts/tests/test_unattended_recovery.py
python3 .aidp/scripts/check_chain_unattended.py
```

Expected: Git 与非 Git 两种流程语义都通过。

- [ ] **Step 4: 提交**

```bash
git add .aidp/commands .aidp/flows .aidp/scripts/tests/test_command_skill_contracts.py \
  .aidp/scripts/tests/test_unattended_recovery.py
git commit -m "docs: define non-git workflow behavior" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 11: 同步维护文档和下发契约

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `.aidp/AIDP-AGENTS.md`
- Modify: `.aidp/reference/{README,agent-tools,skills,命令速查}.md`
- Modify: `.aidp/scripts/README.md`
- Modify: `.aidp/hooks/README.md`
- Modify: `.aidp/skills/aidp-code-engineer/SKILL.md`
- Modify: `docs/init/**`
- Modify: `memory/README.md`

- [ ] **Step 1: 更新 Agent 目录表**

文档统一为：

```text
Claude runtime=.claude/aidp
Shared runtime=.agents/aidp
Codex commands=.codex/skills/aidp
DSH commands=.dsh/commands
DSH extension=github:SugarFatFree/dsh-agent-extension
```

生产正文不得把根 `.aidp` 描述为下游运行目录。

- [ ] **Step 2: 更新非 Git 能力矩阵**

列出可用开发能力、unsupported Git 能力和发布 fail-closed；明确不自动 `git init`。

- [ ] **Step 3: 扫描旧口径**

```bash
rg -n "dsh-plugin-commands|下游.*\.aidp|\.aidp/scripts|\.aidp/flows" \
  AGENTS.md README.md .aidp docs/init memory/README.md \
  --glob '!scripts/tests/**' --glob '!skills/aidp-code-engineer/assets/**'
```

Expected: 只剩模板维护真源说明、迁移语义和反向测试。

- [ ] **Step 4: 运行文档门**

```bash
python3 .aidp/scripts/check_code_symbol_refs.py
python3 .aidp/scripts/check_cli_invocation.py
python3 .aidp/scripts/check_private_markers.py
python3 .aidp/scripts/check_runtime_paths.py
```

- [ ] **Step 5: 提交**

```bash
git add AGENTS.md README.md .aidp/AIDP-AGENTS.md .aidp/reference \
  .aidp/scripts/README.md .aidp/hooks/README.md \
  .aidp/skills/aidp-code-engineer/SKILL.md docs/init memory/README.md
git commit -m "docs: document native runtime and non-git mode" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 12: 重建 bundle 并执行端到端矩阵

**Files:**
- Generated: `.aidp/skills/aidp-code-engineer/assets/**`
- Test: `.aidp/skills/aidp-code-engineer/scripts/tests/test_runtime_layout.py`
- Test: `.aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py`

- [ ] **Step 1: 同步记忆和 bundle**

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/sync_memory_md.py
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py --check
```

- [ ] **Step 2: 端到端初始化矩阵**

在临时目录运行：

```text
Git + Claude
Git + Codex
Git + DSH
Git + Claude+Codex+DSH
none + Claude
none + Codex
none + DSH
none + Claude+Codex+DSH
```

每项运行 init、verify、第二次幂等 init/check。断言根 `.aidp` 不存在。

- [ ] **Step 3: 端到端迁移矩阵**

对旧 `.aidp` 项目运行 migrate/upgrade，覆盖 Git/none、单 Agent/多 Agent、用户修改/纯生成/失败回滚。

- [ ] **Step 4: 全量门禁**

```bash
python3 .aidp/skills/aidp-code-engineer/scripts/verify.py . --template --read-only
bash .aidp/scripts/tests/run.sh
python3 -m unittest discover -s .aidp/skills/aidp-code-engineer/scripts/tests
python3 .aidp/scripts/check_code_symbol_refs.py
python3 .aidp/scripts/check_cli_invocation.py
python3 .aidp/scripts/check_private_markers.py
python3 .aidp/scripts/check_runtime_paths.py
python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py --check
```

- [ ] **Step 5: 提交派生资产**

```bash
git add .aidp/skills/aidp-code-engineer/assets
git commit -m "chore(skill): sync native runtime scaffold" -m "Co-Authored-By: Claude Code <noreply@anthropic.com>"
```

## 实施约束

- 不推送。
- 不执行 `bump_version.py`；本轮没有版本号自增授权。
- 不手工编辑 assets。
- 每个任务先红灯测试、再最小实现、再规格审查和质量审查。
- 不回退当前工作区中的既有审计修复和未跟踪模板主体。
- 任何目录迁移失败必须保留旧 `.aidp`，不得留下半迁移状态。
- 非 Git 的未执行项必须是 unsupported，不能计入通过。
- 完成后明确建议至少 bump minor；同版本不会自动覆盖既有下游契约。
