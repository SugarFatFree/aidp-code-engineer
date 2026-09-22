#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py —— AIDP 项目确定性结构检查（脚本层），输出 ✅ FIXED / ❌ ERROR / ⚠️ WARN / ℹ️ INFO 四段。

用法：
    python3 verify.py <project_root> <version> <user> [--read-only] [--adapter-mode link|copy] [--no-guards]
    python3 verify.py <template_root> --template [--read-only]      # 模板项目自检

- `--no-guards`：跳过契约正文守卫（flow 分片体积、脚本 README 覆盖、委派 `.aidp/scripts/check_*.py` 的各项），只做结构检查。

- 默认「发现即修」只做无破坏性的补建目录；`--read-only` 下一律只报告（审计入口必须带）。
- 模板项目（根有 `版本变更历史.md` 与 `.aidp/AIDP-AGENTS.md`、未打脚手架版本戳）自动进入
  `--template` 模式：不要求迭代级目录，额外检查本体 ↔ bundle 同步。
- 委派给 `.aidp/scripts/check_*.py` 的守卫：判据单一信源在各脚本，这里只映射严重级。

退出码：0 无 ERROR · 1 有 ERROR · 2 用法错误
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scaffold_lib as L  # noqa: E402
import scaffold_marker  # noqa: E402
import runtime_layout  # noqa: E402

def _vcs_mode(root: Path) -> str:
    try:
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return "none"
    return "git" if result.returncode == 0 and result.stdout.strip() == "true" else "none"


def _runtime_homes(root: Path):
    return {source: root / home for source, home in runtime_layout.RUNTIME_HOME.items()
            if os.path.lexists(root / home)}


def _contract_root(root: Path) -> Path:
    homes = _runtime_homes(root)
    return homes.get("shared", homes.get("claude", root / ".aidp"))


def _contract_path(root: Path, relative: str, template: bool = False) -> Path:
    if not template and relative.startswith(".aidp/"):
        return _contract_root(root) / relative[len(".aidp/"):]
    return root / relative


def _runtime_source() -> Path:
    template = L.SKILL_DIR.parents[1]
    if template.name == ".aidp" and (template / "scripts/agent_sync.py").is_file():
        return template
    return L.BUNDLE_AIDP


def _source_runtime_files(source: Path):
    for dirname in runtime_layout.RUNTIME_DIRS:
        for relative, path in L.iter_files(source / dirname):
            name = f"{dirname}/{relative}"
            if not any(name == item.rstrip("/") or
                       (item.endswith("/") and name.startswith(item))
                       for item in runtime_layout.RUNTIME_EXCLUDES):
                yield name, path


def check_native_runtime(root: Path, r):
    homes = _runtime_homes(root)
    if not homes:
        r.error("缺少 Agent 原生运行包（.aidp-runtime.json）")
        return
    project_version = scaffold_marker.read_version(root)
    pending_version = scaffold_marker.read_pending(root)
    current_version = L.bundle_version()
    manifests = {}
    for source, home in homes.items():
        relative = home.relative_to(root).as_posix()
        try:
            manifest = runtime_layout.validate_runtime(home, expected_home=relative)
        except (ValueError, OSError) as exc:
            r.error(f"Agent 原生运行包 {relative} 校验失败：{exc}")
            continue
        manifests[source] = manifest
        expected_version = pending_version or project_version
        if expected_version and manifest["version"] != expected_version:
            r.error(f"Agent 原生运行包 {relative} 版本 {manifest['version']} 与项目脚手架版本 {expected_version} 不同")
        else:
            r.note(f"Agent 原生运行包 {relative} 完整（{len(manifest['files'])} 文件）")
        if manifest["version"] == current_version:
            source = _runtime_source()
            source_files = dict(_source_runtime_files(source))
            missing = sorted(set(source_files) - set(manifest["files"]))
            extra = sorted(set(manifest["files"]) - set(source_files))
            if missing or extra:
                r.error(f"Agent 原生运行包 {relative} 文件清单与当前脚手架 {current_version} 不一致："
                        f"缺失 {_head(missing)}；多出 {_head(extra)}")
            for name in sorted(set(source_files) & set(manifest["files"])):
                if name in L.USER_FILLABLE_CONTRACTS:
                    continue
                data = source_files[name].read_bytes()
                if runtime_layout._is_text(data):
                    data = runtime_layout.render_text(data.decode("utf-8"), relative,
                                                      template_root=source).encode("utf-8")
                actual = home / name
                if actual.read_bytes() != data or actual.stat().st_mode & 0o777 != source_files[name].stat().st_mode & 0o777:
                    r.error(f"Agent 原生运行包 {relative} 文件与当前脚手架 {current_version} 不一致：{name}")
                    break
    expected = set()
    if (root / ".claude").is_dir() and not (root / ".claude/.aidp-agent-disabled").is_file():
        expected.add("claude")
    if any((root / marker).is_dir() and not (root / marker / ".aidp-agent-disabled").is_file()
           for marker in (".codex", ".dsh")):
        expected.add("shared")
    for source in sorted(expected - set(homes)):
        r.error(f"Agent 原生运行包缺失：{runtime_layout.RUNTIME_HOME[source]}")
    if len(manifests) == 2:
        if manifests["claude"]["version"] != manifests["shared"]["version"]:
            r.error("Agent 原生运行包双包版本不一致")
        if set(manifests["claude"]["files"]) != set(manifests["shared"]["files"]):
            r.error("Agent 原生运行包双包文件集合不一致")
        claude, shared = (homes[source] for source in ("claude", "shared"))
        if runtime_layout.normalize_runtime(claude, runtime_layout.RUNTIME_HOME["claude"]) != \
                runtime_layout.normalize_runtime(shared, runtime_layout.RUNTIME_HOME["shared"]):
            r.error("Agent 原生运行包双包规范化内容或权限不一致")
        else:
            r.note("Agent 原生运行包双包规范化一致")
    if os.path.lexists(root / ".aidp"):
        r.error("旧运行目录 .aidp/ 仍有残留；迁移完成后应清除")

READ_ONLY = False


class VerifyResult:
    def __init__(self):
        self.errors, self.warnings, self.info, self.fixed = [], [], [], []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def note(self, msg):
        self.info.append(msg)

    def fix(self, msg):
        self.fixed.append(msg)

    def summary(self):
        total = len(self.errors) + len(self.warnings) + len(self.info)
        print(f"\n{'=' * 60}\n验证结果: {total} 个检查项\n{'=' * 60}")
        for title, items, tag in (("✅ 自动修复", self.fixed, "FIXED"), ("❌ 错误", self.errors, "ERROR"),
                                  ("⚠️  警告", self.warnings, "WARN"), ("ℹ️  信息", self.info, "INFO")):
            if items:
                print(f"\n{title} ({len(items)}):")
                for x in items:
                    print(f"  [{tag}] {x}")
        if not self.errors and not self.warnings:
            print("\n🎉 所有检查通过！")
        print()
        return not self.errors


def _may_mkdir(path: Path) -> bool:
    if READ_ONLY:
        return False
    path.mkdir(parents=True, exist_ok=True)
    return True


def _head(items, n=5, sep="；"):
    items = list(items)
    return sep.join(str(x) for x in items[:n]) + (f"（另 {len(items) - n} 处）" if len(items) > n else "")


# ── 1. 目录骨架 ─────────────────────────────────────────────────────────────
def _current_version(root: Path):
    for name in ("AGENTS.md", "CLAUDE.md"):
        m = re.search(r"当前版本\*\*[：:]\s*(V\d+\.\d+(?:\.\d+)?)", L.read_text(root / name))
        if m:
            return m.group(1)
    return None


def may_create_version_dirs(root: Path, version, user) -> bool:
    """迭代级目录只为「项目当前版本 × 本机开发者」补建（约定 11：不替他人 / 不为未启用的版本建目录）。

    传入的版本或用户与项目实际不符（典型：对真仓跑带夹具参数的 verify）时只报告不创建。
    """
    cur = _current_version(root)
    me = L.git_user(root)
    return (cur is None or cur == version) and (not me or me == user)


def check_directories(root: Path, version, user, template: bool, r: VerifyResult):
    dirs = L.skeleton_dirs(root, version or "", user or "", include_version=not template)
    if template:
        dirs = [d for d in dirs if d.startswith(".aidp/") or d in ("docs/init", "memory")]
    version_level = set() if template else set(L.version_dirs(version or "", user or ""))
    allow_version = template or may_create_version_dirs(root, version, user)
    for rel in dirs:
        p = _contract_path(root, rel, template)
        if not template and rel.startswith(".aidp/") and _runtime_homes(root):
            continue  # 运行包自身的必需目录由 validate_runtime 校验。
        if p.is_dir():
            continue
        if (rel not in version_level or allow_version) and _may_mkdir(p):
            r.fix(f"创建缺失目录: {rel}/")
        elif READ_ONLY:
            r.error(f"缺失目录: {rel}/（只读模式未创建；重跑脚手架或非只读 verify 补建）")
        else:
            r.error(f"缺失目录: {rel}/（{version}/{user} 不是项目当前版本或本机开发者，未自动创建）")


# ── 2. 契约文件与关键文件 ───────────────────────────────────────────────────
REQUIRED_SCRIPTS = ("agent_env.py", "agent_sync.py", "commit_gate.py", "aidp_config.py", "aidp_paths.py")
REQUIRED_DOCS_INIT = ("README.md", "00_AIDP范式主文档.md", "01_初始化输入指导.md", "02_迭代输入指导.md",
                      "03_memory文件详细规范.md", "04_agents详细规范.md", "05_commands详细规范.md",
                      "06_版本与用户目录约定.md")


def check_files(root: Path, template: bool, r: VerifyResult):
    for name in REQUIRED_SCRIPTS:
        if not _contract_path(root, f".aidp/scripts/{name}", template).is_file():
            r.error(f"缺失脚本: .aidp/scripts/{name}")
    if not _contract_path(root, ".aidp/hooks/autopilot-stop-guard.py", template).is_file():
        r.error("缺失 hook: .aidp/hooks/autopilot-stop-guard.py")
    if not _contract_path(root, ".aidp/agents/aidp-compliance.md", template).is_file():
        r.warn("缺失合规 Agent: .aidp/agents/aidp-compliance.md")
    for name in REQUIRED_DOCS_INIT:
        if not (root / "docs/init" / name).is_file():
            r.error(f"缺失范式文档: docs/init/{name}")
    base = ["README.md", ".gitignore", "memory/aidp-config.yaml", "memory/README.md"]
    if not template:
        base += ["docs/README.md"] + [f"docs/architecture/{n}" for n in L.ARCH_DOCS] \
            + [rel for _, rel in L.MEMORY_TEMPLATES]
    for rel in base:
        p = root / rel
        if not p.is_file():
            r.error(f"缺失文件: {rel}")
        elif p.stat().st_size == 0:
            r.warn(f"文件为空: {rel}")


def check_memory_structure(root: Path, version, user, r: VerifyResult):
    d = root / "memory" / version / user
    if not d.is_dir():
        return
    missing = [f for f in ("activeContext.md", "progress.md") if not (d / f).is_file()]
    if missing:
        r.note(f"memory/{version}/{user}/ 尚无 {'、'.join(missing)}（由 /sprint-start、/memory-sync 首次运行时创建）")


# ── 3. 多 Agent：记忆文件形态 + 适配层漂移 ───────────────────────────────────
def _agent_env(root: Path):
    p = _contract_root(root) / "scripts/agent_env.py"
    if not p.is_file():
        return None
    try:
        out = subprocess.run([sys.executable, str(p), "memory-file", "--root", str(root)],
                             capture_output=True, text=True, timeout=30)
        return json.loads(out.stdout)
    except Exception:
        return None


def check_template_memory(root: Path, r: VerifyResult):
    """模板仓库两份记忆各司其职：根 AGENTS.md = 模板自身维护记忆（不下发）；
    `.aidp/AIDP-AGENTS.md` = 下发记忆源（结构由 sync_memory_md.py 校验）。"""
    own = L.read_text(root / "AGENTS.md")
    if not own.strip():
        r.error("模板仓库根 AGENTS.md 缺失或为空（模板自身维护记忆）")
    elif "## 核心约定" in own:
        r.error("模板仓库根 AGENTS.md 混入了下发正文（「核心约定」应只在 .aidp/AIDP-AGENTS.md）")
    c = L.read_text(root / "CLAUDE.md")
    if c.strip() and not L.is_shell(c):
        r.error("模板仓库根 CLAUDE.md 应为一行 `@AGENTS.md` 薄壳")
    if not (root / L.PARADIGM_MEMORY_REL).is_file():
        r.error(f"缺少下发记忆源 {L.PARADIGM_MEMORY_REL}")
    else:
        r.note(f"模板记忆分离：根 AGENTS.md（自身维护）/ {L.PARADIGM_MEMORY_REL}（下发源）")


def check_memory_file(root: Path, r: VerifyResult):
    env = _agent_env(root)
    if env is None:
        r.warn("无法经 agent_env.py 解析项目记忆文件，跳过记忆文件形态检查")
        return
    agents, mf = env.get("agents") or [], env.get("memory_file")
    bodies = L.memory_bodies(root)
    body_path = root / mf
    text = L.read_text(body_path)
    if not text.strip():
        r.error(f"项目记忆文件 {mf} 缺失或为空（Agent：{','.join(agents)}）")
        return
    if L.is_shell(text):
        r.error(f"{mf} 只是 @AGENTS.md 薄壳但 AGENTS.md 无正文")
        return
    if agents != ["claude"] and "AGENTS.md" not in bodies:
        r.error(f"已启用 {','.join(a for a in agents if a != 'claude')}：正文必须在 AGENTS.md")
    if "claude" in agents and "AGENTS.md" in bodies:
        c = L.read_text(root / "CLAUDE.md")
        if not L.is_shell(c):
            r.error("AGENTS.md 与 CLAUDE.md 同时承载正文（两份正文会漂移）；CLAUDE.md 应为一行 `@AGENTS.md` 薄壳"
                    " → 跑 `python3 .aidp/scripts/agent_sync.py`")
    for heading in ("## 当前状态", "核心约定"):
        if heading not in text:
            r.error(f"{mf} 缺少必需区域「{heading.strip('# ')}」")
    if L.CUSTOM_HEADING not in text:
        r.note(f"{mf} 无「项目自定义」段（项目特有约定建议写在该段，升级时保留）")
    r.note(f"项目记忆文件 = {mf}（Agent：{','.join(agents)}，来源 {env.get('source')}）")


def _link_points_into_aidp(root: Path, path: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        target = (path.parent / os.readlink(path)).resolve()
        target.relative_to((root / ".aidp").resolve())
        return True
    except (OSError, ValueError):
        return False


def _managed_adapter_entries(root: Path) -> set:
    """据当前 `.aidp/` 真源列出可证明由 AIDP 管理的适配入口。"""
    out = set()
    commands = _contract_root(root) / "commands"
    if commands.is_dir():
        for command in commands.glob("*.md"):
            if command.stem.upper() == "README":
                continue
            out.update((root / ".claude/commands" / command.name,
                        root / ".dsh/commands" / command.name,
                        root / ".codex/skills/aidp" / command.stem))
    skills = _contract_root(root) / "skills"
    if skills.is_dir():
        for skill in skills.iterdir():
            if skill.name == "aidp-cmd" or not (skill / "SKILL.md").is_file():
                continue
            out.update((root / ".claude/skills" / skill.name,
                        root / ".agents/skills" / skill.name))
    plugins = _contract_root(root) / "plugins"
    if plugins.is_dir():
        for plugin in plugins.iterdir():
            source = plugin / "skills"
            if not source.is_dir():
                continue
            out.update((root / ".claude/plugins" / plugin.name,
                        root / ".codex/skills" / plugin.name / "skills",
                        root / ".agents/skills" / plugin.name / "skills"))
            for skill in source.iterdir():
                if (skill / "SKILL.md").is_file():
                    out.add(root / ".agents/skills" / skill.name)
    for marker in (root / ".codex/skills/aidp").glob("*/.aidp-generated"):
        if marker.is_file():
            out.add(marker.parent)
    return out


def _adapter_mode(root: Path, override):
    """仅依据可证明由 AIDP 管理的入口判断 link/copy，忽略用户自有 symlink。"""
    if override:
        return override
    if _runtime_homes(root):
        return "copy"
    seen = False
    for entry in _managed_adapter_entries(root):
        if _link_points_into_aidp(root, entry):
            return "link"
        if entry.exists():
            seen = True
    return "copy" if (seen or os.name == "nt") else "link"


def check_agent_adapters(root: Path, mode_override, r: VerifyResult):
    script = _contract_root(root) / "scripts/agent_sync.py"
    if not script.is_file():
        return
    mode = _adapter_mode(root, mode_override)
    try:
        p = subprocess.run([sys.executable, str(script), "--root", str(root), "--check", "--mode", mode],
                           capture_output=True, text=True, timeout=120)
        data = json.loads(p.stdout.strip().splitlines()[-1])
    except Exception as e:
        r.warn(f"Agent 适配层检查未能执行（{e}）")
        return
    if p.returncode == 1:
        acts = [f"{a['op']} {a['path']}" for a in data.get("actions") or []]
        r.error(f"Agent 适配层与 .aidp/ 漂移 {len(acts)} 处：{_head(acts)}"
                f" → 跑 `python3 .aidp/scripts/agent_sync.py --mode {mode}`")
    elif p.returncode == 0:
        r.note(f"Agent 适配层一致（{','.join(data.get('agents') or [])}，mode={mode}）")
    else:
        r.warn(f"Agent 适配层检查异常（exit {p.returncode}）：{(p.stderr or p.stdout).strip()[:200]}")


# ── 4. docs/init 与 bundle 同步 ─────────────────────────────────────────────
def check_docs_init_sync(root: Path, template: bool, r: VerifyResult):
    init = root / "docs/init"
    if not init.is_dir():
        return
    for ref in (L.ASSETS / "docs/init",):
        if not ref.is_dir():
            (r.error if template else r.warn)(f"脚手架缺 {ref.relative_to(L.SKILL_DIR)}/")
            continue
        want = dict(L.iter_files(ref))
        have = dict(L.iter_files(init))
        drift = sorted(k for k in set(want) | set(have)
                       if k not in want or k not in have or want[k].read_bytes() != have[k].read_bytes())
        label = ref.relative_to(L.SKILL_DIR).as_posix()
        if drift:
            if template:
                r.error(f"docs/init 与 {label}/ 不一致：{_head(drift)} → 跑 mirror_to_bundle.py")
            else:
                r.warn(f"docs/init 与脚手架版本不一致：{_head(drift)} → 重跑 aidp-code-engineer upgrade")
        else:
            r.note(f"docs/init 与 {label}/ 一致（{len(want)} 份）")


# ── 5. 代码目录约定 + README 策略 ───────────────────────────────────────────
def check_code_layout(root: Path, r: VerifyResult):
    code = root / "code"
    if not code.is_dir():
        return
    for side in ("frontend", "backend"):
        d = code / side
        if d.is_dir():
            direct = sorted(x.name for x in d.iterdir() if x.name in L.PROJECT_ROOT_MARKERS)
            if direct:
                r.error(f"约定 18：code/{side}/ 根直接出现源码根标志（{', '.join(direct)}），缺 {{子项目}} 中间层"
                        f" → `mkdir -p code/{side}/<子项目> && git mv code/{side}/<文件> code/{side}/<子项目>/`")
    custom = sorted(x.name for x in code.iterdir() if x.is_dir() and not x.name.startswith(".")
                    and x.name not in ("sql", "frontend", "backend") and any(x.iterdir()))
    if custom:
        r.note(f"code/ 下有自定义代码目录 {', '.join(custom)}：保留原位；请在 memory/techContext.md"
               f"「项目代码结构」写明实际路径（迁入 code/frontend|backend/{{子项目}}/ 由团队决定）")
        return
    for side in ("frontend", "backend"):
        if not (code / side).is_dir():
            if _may_mkdir(code / side):
                r.fix(f"创建缺失目录: code/{side}/")
            else:
                r.warn(f"缺失目录 code/{side}/")


NAV_SCAN_ROOTS = ("docs", "memory")
NAV_SCAN_EXCLUDED = {"docs/superpowers"}  # 模板维护规格/计划，不属于下游文档导航


def check_code_readme(root: Path, r: VerifyResult):
    try:
        policy = L.load_project_module("readme_policy")
    except ImportError as e:
        r.warn(f"README 策略检查跳过：{e}")
        return
    candidates = []
    for p in policy.explicit_required_directories(root):
        if not (p / "README.md").is_file() and policy.is_readme_required_directory(p, None, root=root)["required"]:
            r.warn(f"缺 README.md: {p.relative_to(root)}/（README_REQUIRED 显式声明）")
    for base in (root / n for n in ("code", "web", "server", "src")):
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_dir() or any(x.startswith(".") or x in L.IGNORE_DIRS for x in path.relative_to(root).parts):
                continue
            dec = policy.is_readme_required_directory(path, None, root=root)
            if dec["required"]:
                candidates.append(path)
                if not (path / "README.md").is_file():
                    r.warn(f"代码单元缺 README.md: {path.relative_to(root)}/（{dec['reason']}，约定 19）")
    for base in (root / n for n in NAV_SCAN_ROOTS):
        if not base.is_dir():
            continue
        for path in [base] + sorted(p for p in base.rglob("*") if p.is_dir()):
            rel = path.relative_to(root)
            rel_text = rel.as_posix()
            excluded = any(rel_text == prefix or rel_text.startswith(prefix + "/")
                           for prefix in NAV_SCAN_EXCLUDED)
            if any(x.startswith(".") for x in rel.parts) or excluded:
                continue
            dec = policy.is_readme_required_directory(path, None, root=root)
            if dec["required"] and dec.get("reason") == "navigation-hub" and not (path / "README.md").is_file():
                r.warn(f"导航枢纽缺 README.md: {path.relative_to(root)}/（约定 19 第②档，只列子目录与用途）")
    scan_roots = [p for p in (root / "code", root / "web", root / "server", root / "src") if p.is_dir()]
    for line in policy.format_out_of_scope_report(policy.scan_out_of_scope_readmes(root, None, scan_roots=scan_roots)):
        r.note(line)


def check_prototype_baseline(root: Path, version, r: VerifyResult):
    proto = root / f"docs/prototype/{version}/code"
    if not proto.is_dir() or not any(p.is_file() and p.name != ".gitkeep" for p in proto.rglob("*")):
        return
    detail = root / f"docs/design/detail/{version}"
    if not (detail.is_dir() and list(detail.glob("*原型内容基线.md"))):
        r.note(f"有原型 docs/prototype/{version}/code/ 但缺 docs/design/detail/{version}/NN_原型内容基线.md"
               f"（约定 4 规划期产出物）→ /sprint-design 补出")


# ── 6. 部署双轨 ─────────────────────────────────────────────────────────────
def _version_dirs(dep: Path):
    return [d for d in sorted(dep.iterdir()) if d.is_dir() and d.name not in ("tools", "归档")]


def check_deployment_two_track_layout(root: Path, r: VerifyResult):
    dep = root / "docs/deployment"
    if not dep.is_dir():
        return
    stale_sql, stale_cfg, missing_full = [], [], []
    for v in _version_dirs(dep):
        stale_sql += [f"{v.name}/sql/{f.name}" for f in sorted((v / "sql").glob("*.sql"))] if (v / "sql").is_dir() else []
        cfg = v / "配置文件"
        if cfg.is_dir():
            for pat in ("配置项清单*.md", "*.conf", "docker-compose*.yml", "docker-compose*.yaml", "k8s-*.yaml", "k8s-*.yml"):
                stale_cfg += [f"{v.name}/配置文件/{f.name}" for f in sorted(cfg.glob(pat))]
        for track in ("sql", "配置文件"):
            if (v / track / "增量").is_dir() and not (v / track / "全量").is_dir():
                missing_full.append(f"{v.name}/{track}/全量")
    if stale_sql:
        r.error(f"约定 37：{len(stale_sql)} 个 .sql 散落在 sql/ 根（应在 sql/增量/）：{_head(stale_sql, 6, ', ')}"
                f" → `git mv` 到 sql/增量/ 并回写部署文档引用")
    if stale_cfg:
        r.error(f"约定 37：{len(stale_cfg)} 份配置产物在 配置文件/ 根（清单 → 增量/；完整文件 → 全量/）："
                f"{_head(stale_cfg, 6, ', ')}")
    if missing_full:
        r.warn(f"约定 37 全量轨缺失：{_head(missing_full, 6, ', ')}（发布期由 /version 产出；未发布版本属正常）")
    if not stale_sql and not stale_cfg:
        r.note("部署产物两轨落位一致（sql/{增量,全量}/ + 配置文件/{增量,全量}/）")


def check_deployment_docs(root: Path, r: VerifyResult):
    dep = root / "docs/deployment"
    if not dep.is_dir():
        return
    miss_flow, miss_ledger = [], []
    for v in _version_dirs(dep):
        has_sql = any(re.match(r"^\d{2}_", f.name) and not f.name.startswith("99_")
                      for f in (v / "sql").glob("增量/*.sql")) if (v / "sql").is_dir() else False
        if not has_sql:
            continue
        flow = v / "部署流程/部署流程.md"
        if not flow.is_file() or re.search(r"\{(version|prev-version)\}", L.read_text(flow)):
            miss_flow.append(v.name)
        if not (v / "部署流程/SQL执行台账.md").is_file():
            miss_ledger.append(v.name)
    if miss_flow:
        r.warn("以下版本有增量 SQL 但『部署流程/部署流程.md』缺失或仍是模板占位：" + ", ".join(miss_flow)
               + " → /sprint-dev 部署文档步骤补齐")
    if miss_ledger:
        r.note("以下版本有增量 SQL 但缺『部署流程/SQL执行台账.md』：" + ", ".join(miss_ledger))


def check_deployment_tools(root: Path, r: VerifyResult):
    tools = root / "docs/deployment/tools"
    if tools.is_dir() and any(p.name != ".gitkeep" for p in tools.iterdir()) and not (tools / "README.md").is_file():
        r.note("docs/deployment/tools/ 有内容但缺 README.md 索引")


def check_sql_version_dir_consistency(root: Path, r: VerifyResult):
    dep = root / "docs/deployment"
    if not dep.is_dir():
        return
    hits = []
    for v in _version_dirs(dep):
        dv = L.parse_ver(v.name) if L.VERSION_RE.match(v.name) else None
        if dv is None or not (v / "sql").is_dir():
            continue
        for f in sorted(list((v / "sql").glob("增量/*.sql")) + list((v / "sql").glob("*.sql"))):
            head = "".join(L.read_text(f).splitlines(keepends=True)[:8])
            for tok in re.findall(r"[Vv]\d+\.\d+(?:\.\d+)?", head):
                if L.parse_ver(tok) > dv:
                    hits.append(f"{f.relative_to(root)}（文件头 {tok} > 目录 {v.name}）")
                    break
    for h in hits:
        r.warn(f"SQL 落错版本目录（约定 11）：{h}")


# ── 7. 运行时产物入库策略 / 凭证 ────────────────────────────────────────────
def check_runtime_artifact_vcs(root: Path, r: VerifyResult):
    script = _contract_root(root) / "scripts/aidp_paths.py"
    if not script.is_file() or _vcs_mode(root) != "git":
        return
    try:
        out = subprocess.run([sys.executable, str(script), "--root", str(root), "--json"],
                             capture_output=True, text=True, timeout=30)
        arts = json.loads(out.stdout).get("artifacts", [])
    except Exception as e:
        r.note(f"运行时产物入库策略：清单取不到（{e}），跳过")
        return
    bad_err, bad_warn = [], []
    for it in arts:
        if not L.git_tracked(root, it["path"]):
            continue
        if "永不入库" in it.get("vcs", ""):
            bad_err.append(it["path"])
        elif it.get("vcs") == "不入库":
            bad_warn.append(it["path"])
    if bad_err:
        r.error(f"标「永不入库」的运行时产物已被 git 跟踪：{'、'.join(bad_err)}"
                f" → `git rm --cached {' '.join(bad_err)}` 并轮换其中凭据")
    if bad_warn:
        r.warn(f"标「不入库」的运行时产物被 git 跟踪：{'、'.join(bad_warn)}")
    if not bad_err and not bad_warn:
        r.note(f"运行时产物入库策略一致（巡检 {len(arts)} 项）")


def check_tracked_credentials(root: Path, r: VerifyResult):
    res = L.git(root, "ls-files", "-z")
    if res is None or res.returncode != 0:
        return
    bad = [p for p in res.stdout.split("\0") if p and (re.search(r"(^|/)auth\.[^/]+\.json$", p)
                                                        or re.search(r"(^|/)env/\.env(\..+)?$", p))]
    if bad:
        r.error(f"凭证类文件被 git 跟踪：{_head(bad, 6, '、')} → `git rm --cached` 并轮换凭据")


# ── 8. gitignore 托管区 / 占位符 / 备份卫生 ─────────────────────────────────
def check_gitignore(root: Path, r: VerifyResult):
    gi = root / ".gitignore"
    if not gi.is_file():
        r.warn(".gitignore 不存在 → 重跑脚手架生成")
        return
    lines = gi.read_text(encoding="utf-8").splitlines()
    if L.GITIGNORE_BEGIN not in lines or L.GITIGNORE_END not in lines:
        r.warn(".gitignore 缺 AIDP 托管区标记 → 重跑脚手架 upgrade 收编")
        return
    tpl = L.ASSETS / "root/gitignore.tpl"
    if tpl.is_file():
        want = L.gitignore_block(tpl.read_text(encoding="utf-8"))
        have = lines[lines.index(L.GITIGNORE_BEGIN):lines.index(L.GITIGNORE_END) + 1]
        if want != have:
            r.warn(".gitignore 托管区落后于脚手架模板 → 重跑脚手架 upgrade")
        else:
            r.note(".gitignore 托管区为最新")


def check_unreplaced_placeholders(root: Path, r: VerifyResult):
    targets = []
    for base in ("memory", "docs"):
        d = root / base
        if d.is_dir():
            targets += [p for p in d.rglob("*.md") if not any(x.startswith(".") for x in p.relative_to(root).parts)
                        and "init" not in p.relative_to(root).parts]
    targets += [root / n for n in ("AGENTS.md", "CLAUDE.md", "README.md", "memory/aidp-config.yaml")]
    for p in targets:
        if not p.is_file():
            continue
        text = re.sub(r"`[^`\n]*`", "", L.read_text(p))
        found = sorted(set(L.PLACEHOLDER_RE.findall(text)))
        if found:
            r.warn(f"未替换占位符: {p.relative_to(root)} → {', '.join('{{' + x + '}}' for x in found)}")


def check_backup_hygiene(root: Path, r: VerifyResult):
    backups = L.scan_backups(root)
    if not backups:
        return
    total = sum(L.dir_size(p) for p, _ in backups)
    msg = f"升级备份 {len(backups)} 个 / {L.human_size(total)}：" + " ".join(p.name for p, _ in backups)
    if len(backups) > L.BACKUP_HYGIENE_MAX_DIRS or total > L.BACKUP_HYGIENE_MAX_BYTES:
        r.warn(msg + " → 确认无需回滚后删除")
    else:
        r.note(msg)
    for p, _ in backups:
        if _vcs_mode(root) != "git":
            continue
        listed = L.git(root, "ls-files", "--", p.name)
        if listed is not None and listed.stdout.strip():
            r.error(f"备份目录 {p.name}/ 被 git 跟踪 → `git rm -r --cached {p.name}`")


# ── 9. 升级收口 / 契约漂移 ──────────────────────────────────────────────────
def check_pending_rewrite_queue(root: Path, r: VerifyResult):
    pending = scaffold_marker.read_pending(root)
    entries = L.queue_entries(root)
    if entries:
        r.error(f"存在未消费的语义改写队列 {L.REWRITE_QUEUE_FILE}（{len(entries)} 条）：{_head(e.split(chr(9))[0] for e in entries)}"
                f" → 逐条语义改写后跑 `python3 .aidp/skills/aidp-code-engineer/scripts/finalize_upgrade.py`"
                f"（核验改写并删除队列；无需改动的条目加 --accept）")
    elif (root / L.REWRITE_QUEUE_FILE).is_file():
        r.warn(f"{L.REWRITE_QUEUE_FILE} 存在但无条目 → 跑 finalize_upgrade.py 清理")
    if pending:
        r.error(f"脚手架交付未收口：scaffold.pending = {pending} → 队列清空后跑 "
                f"`python3 .aidp/skills/aidp-code-engineer/scripts/finalize_upgrade.py`")


def check_contract_drift(root: Path, r: VerifyResult):
    if _runtime_homes(root):
        current = L.bundle_version()
        project = scaffold_marker.read_version(root)
        if project and L.parse_ver(project) and L.parse_ver(current) and L.parse_ver(project) < L.parse_ver(current):
            r.warn(f"项目脚手架版本 {project} 低于当前脚手架 {current} → 跑 aidp-code-engineer upgrade")
        return  # 原生运行包文件完整性由 check_native_runtime 校验。
    try:
        manifest = json.loads((L.SKILL_DIR / L.MANIFEST_REL).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    files = manifest.get("files") or {}
    ver = manifest.get("scaffold_version") or "?"
    missing, stale = [], []
    for rel, want in sorted(files.items()):
        p = root / ".aidp" / rel
        if not p.is_file():
            missing.append(rel)
        elif rel not in L.USER_FILLABLE_CONTRACTS and L.sha256(p.read_bytes()) != want:
            stale.append(rel)
    if missing:
        r.warn(f"缺 {len(missing)} 份脚手架 {ver} 契约文件：{_head(missing)} → 重跑 aidp-code-engineer upgrade")
    if stale:
        r.warn(f"{len(stale)} 份契约文件正文与脚手架 {ver} 不一致：{_head(stale)}"
               f"（本地改过契约，或脚手架同版本内容已变更；项目特有规则应写进项目记忆文件「项目自定义」段）")
    if not missing and not stale:
        r.note(f"契约文件与脚手架 {ver} 逐文件一致（{len(files)} 份）")
    proj = scaffold_marker.read_version(root)
    if proj and L.parse_ver(proj) and L.parse_ver(ver) and L.parse_ver(proj) < L.parse_ver(ver):
        r.warn(f"项目脚手架版本 {proj} 低于当前脚手架 {ver} → 跑 aidp-code-engineer upgrade")
    expected = set(files)
    skills = {k.split("/")[1] for k in expected if k.startswith("skills/")}
    orphans = []
    for d in L.GATED_DIRS:
        for rel, _ in L.iter_files(root / ".aidp" / d):
            label = f"{d}/{rel}"
            if label in expected or label in L.OPTIONAL_INSTALLED_CONTRACTS:
                continue
            if d == "skills" and (rel.split("/", 1)[0] == L.SKILL_NAME or rel.split("/", 1)[0] not in skills):
                continue
            orphans.append(f".aidp/{label}")
    if orphans:
        r.warn(f"{len(orphans)} 个契约文件已不在当前脚手架中（确认后手工删除）：{_head(orphans)}")


# ── 10. 记忆文件 / 版本号 / 环境 ────────────────────────────────────────────
BUILD_CMDS = ("pnpm build", "pnpm run build", "npm run build", "yarn build", "vite build", "mvn package",
              "mvn clean package", "gradle build", "./gradlew build", "gradle bootjar", "./gradlew bootjar")
SERVE_CMDS = ("npm run dev", "pnpm dev", "pnpm run dev", "yarn dev", "vite serve", "ng serve", "spring-boot:run",
              "bootrun", "manage.py runserver", "flask run", "uvicorn", "nodemon")
DEPLOY_OK = ("部署", "发布", "deploy", "cicd", "ci/cd", "生产", "prod", "release", "流水线", "上线")
NEGATION = ("开发期不", "绝不", "禁止", "不跑", "仅部署", "仅发布", "只做", "类型检查", "语法检查", "不擅自",
            "mode=local", "已部署", "先问")


def check_project_claude_aidp_conflict(root: Path, r: VerifyResult):
    """项目自写内容（记忆文件「项目自定义」段，或非 AIDP 形态的 CLAUDE.md）把完整构建 / 起服务列成开发期常用命令。"""
    for name, text in L.memory_bodies(root).items():
        section = L.custom_section(text) if L.looks_like_aidp_body(text) else text
        if not section.strip():
            continue
        for i, ln in enumerate(section.splitlines(), 1):
            low = ln.lower()
            if any(q in low for q in DEPLOY_OK) or any(n in low for n in NEGATION):
                continue
            if any(c in low for c in BUILD_CMDS):
                r.warn(f"{name}「项目自定义」把完整构建列成开发期命令（与约定 35「开发期只做静态验证、完整构建仅部署期」冲突，"
                       f"建议删除或改为部署期限定）：{ln.strip()[:80]}")
            elif any(c in low for c in SERVE_CMDS):
                r.warn(f"{name}「项目自定义」把启动服务列成开发期命令（与约定 35 冲突，建议删除或改为授权例外）：{ln.strip()[:80]}")


def check_version(root: Path, version, r: VerifyResult):
    if not L.VERSION_RE.match(version or ""):
        r.error(f"版本号格式不正确: {version}（应为 V{{major}}.{{minor}}[.{{patch}}]）")
        return
    for name in ("AGENTS.md", "CLAUDE.md"):
        m = re.search(r"当前版本\*\*[：:]\s*(V[\d.]+)", L.read_text(root / name))
        if m and m.group(1) != version:
            r.note(f"{name}「当前版本」为 {m.group(1)}，与传入版本 {version} 不同")


def check_env_key_freshness(root: Path, r: VerifyResult):
    tpl, tgt = L.ASSETS / "root/env.tpl", root / "env/.env"
    if not tpl.is_file() or not tgt.is_file():
        return

    def keys(p):
        return {ln.split("=", 1)[0].strip() for ln in L.read_text(p).splitlines()
                if ln.strip() and not ln.strip().startswith("#") and "=" in ln}

    have = keys(tgt)
    if have:
        miss = sorted(keys(tpl) - have)
        if miss:
            r.note(f"env/.env 缺 env.tpl 中的键（不自动写入）：{_head(miss, 12, ', ')}")


def check_convention_anchor_consistency(root: Path, r: VerifyResult):
    env = _agent_env(root) or {}
    body = L.read_text(root / (env.get("memory_file") or "AGENTS.md"))
    nums = [int(m.group(1)) for m in re.finditer(r"^(\d+)\.\s+\*\*", body, re.M)]
    if not nums:
        return
    max_n = max(nums)
    decl = re.compile(r"约定\s*1\s*[–\-]\s*(\d+)|核心约定\s*1\s*[–\-]\s*(\d+)|(\d+)\s*项核心约定")
    bad = []
    for f in (root / "AGENTS.md", root / "CLAUDE.md", root / "docs/init/03_memory文件详细规范.md"):
        for m in decl.finditer(L.read_text(f)):
            n = next(int(g) for g in m.groups() if g)
            if n != max_n:
                bad.append(f"{f.name}「{m.group(0)}」")
    for b in bad:
        r.warn(f"约定编号声明与正文最大约定号 {max_n} 不一致：{b}")


def check_scripts_readme_coverage(root: Path, r: VerifyResult):
    d = _contract_root(root) / "scripts"
    text = L.read_text(d / "README.md")
    if not text:
        return
    missing = sorted(p.name for p in d.glob("*.py") if p.name not in text)
    if missing:
        r.warn(f".aidp/scripts/README.md 漏登 {len(missing)} 个脚本：{_head(missing, 8, '、')}")


def check_flow_slice_size(root: Path, r: VerifyResult):
    flows = _contract_root(root) / "flows"
    if not flows.is_dir():
        return
    exempt = {"invariants.md", "usage-guard.md", "rationale.md", "README.md"}
    limit, warn_at = 20480, 20200
    over, near = [], []
    for p in sorted(flows.rglob("*.md")):
        if p.name in exempt:
            continue
        n = p.stat().st_size
        if n > limit:
            over.append(f"{p.relative_to(root)} = {n}B")
        elif n >= warn_at:
            near.append(f"{p.name} 余 {limit - n}B")
    if over:
        r.error(f"flows 分片超 {limit}B 上限：{_head(over)} → 把理据移到同目录 rationale.md")
    elif near:
        r.warn(f"{len(near)} 份 flows 分片接近 {limit}B 上限：{_head(near, 3)}")
    else:
        r.note(f"flows 分片体积合规（≤{limit}B）")


# ── 11. 委派守卫（判据单一信源在 .aidp/scripts/check_*.py）───────────────────
def _run_guard(root: Path, name: str, extra=None, timeout=180):
    script = _contract_root(root) / "scripts" / f"{name}.py"
    if not script.is_file():
        return None, None
    try:
        p = subprocess.run([sys.executable, str(script)] + list(extra or []) + ["--root", str(root), "--json"],
                           capture_output=True, text=True, timeout=timeout)
        data = json.loads(p.stdout or "{}")
    except Exception as e:
        return None, f"执行失败（{e}）"
    if isinstance(data, dict) and data.get("error"):
        return None, f"脚本报错（{str(data['error'])[:160]}）"
    if p.returncode not in (0, 1):
        return None, f"退出码 {p.returncode}（{(p.stderr or '').strip()[:160]}）"
    return data, None


def _loc(item):
    if not isinstance(item, dict):
        return str(item)
    if "skill" in item and "script" in item:
        return f"{item['skill']}/{item['script']}"
    if "flag" in item:
        return f"{item['flag']}@{(item.get('sites') or ['?'])[0]}"
    if "files" in item and isinstance(item["files"], list):
        return f"{len(item['files'])} 文件×{item.get('length', '?')} 字符（{', '.join(item['files'][:2])}）"
    f = (item.get("file") or item.get("command") or item.get("flow") or item.get("name")
         or item.get("var") or item.get("convention") or item.get("rule") or "")
    line = item.get("line")
    return f"{f}:{line}" if line else str(f or item)[:120]


def _level(item, default):
    if not isinstance(item, dict):
        return default
    lv = str(item.get("level") or item.get("severity") or "").upper()
    if lv in ("ERROR", "CRITICAL"):
        return "ERROR"
    if lv in ("WARN", "WARNING", "IMPORTANT"):
        return "WARN"
    if lv in ("INFO",):
        return "INFO"
    return default


# (函数名, 脚本, 标签, 读取的列表键, 缺省严重级, 额外参数, 适用判定键)
GUARDS = (
    ("check_md_anchor_links", "check_md_anchors", "站内锚点", ("broken",), "ERROR", None, None),
    ("check_webmcp", "check_webmcp", "WebMCP 装配", ("findings",), "WARN", None, "applicable"),
    ("check_underscore_glob", "check_underscore_glob", "族增量 glob 排除 `_*`", ("violations",), "WARN", None, None),
    ("check_shard_id_style", "check_shard_id_style", "flow 分片标题编号风格", ("findings",), "WARN", None, "applicable"),
    ("check_singlesource_pointer", "check_singlesource_pointer", "「单一信源」指针", ("findings",), "ERROR", None, "applicable"),
    ("check_chain_unattended", "check_chain_unattended", "--unattended 串联透传", ("new",), "ERROR", None, None),
    ("check_banned_terminology", "check_banned_terminology", "术语一致性", ("findings",), "ERROR", None, None),
    ("check_convention30_prose", "check_convention30_prose", "约定 30 正文体检", ("new",), "ERROR", None, None),
    ("check_flow_shell_escapes", "check_flow_shell_escapes", "flow shell 围栏转义", ("findings",), "ERROR", None, None),
    ("check_flow_bash_syntax", "check_flow_bash_syntax", "flow bash 围栏语法", ("findings",), "ERROR", None, None),
    ("check_count_claims", "check_count_claims", "文档自称计数", ("violations",), "ERROR", None, None),
    ("check_deployment_path_refs", "check_deployment_path_refs", "部署路径引用", ("violations",), "ERROR", None, None),
    ("check_freeze_contract_guard", "check_freeze_contract", "冻结字段写入契约", ("findings",), "ERROR", None, None),
    ("check_skill_ref_drift", "check_skill_ref_drift", "SKILL 内部文件引用", ("findings",), "ERROR", None, "applicable"),
    ("check_skill_ref_freshness", "check_skill_ref_freshness", "SKILL 引用新鲜度", ("findings", "unreferenced_skill_scripts"), "INFO", None, None),
    ("check_cross_file_dup", "check_cross_file_dup", "跨文件长片段双写", ("findings",), "INFO", None, "applicable"),
    ("check_step_index_coverage", "check_step_index_coverage", "命令骨架表 Step 覆盖", ("findings",), "ERROR", None, "applicable"),
    ("check_skill_gate_list_guard", "check_skill_gate_list", "SKILL 阻断名单", ("findings",), "ERROR", None, "applicable"),
    ("check_arguments_channel_guard", "check_arguments_channel", "$ARGUMENTS 接收通道", ("findings",), "ERROR", None, "applicable"),
    ("check_prose_vs_executable_guard", "check_prose_vs_executable", "散文承诺↔可执行落点", ("findings",), "ERROR", None, "applicable"),
    ("check_doc_numbering", "check_doc_numbering", "文档编号重号", ("errors",), "ERROR", None, None),
    ("check_tick_var_supply", "check_tick_var_supply", "tick 变量供给链", ("findings",), "INFO", None, "applicable"),
    ("check_sprint_convention", "check_sprint_numbering", "Sprint 编号 / 划分", ("findings",), "INFO", ["check"], "applicable"),
    ("check_ghost_flags", "check_ghost_flags", "幽灵旗标", ("undefined",), "ERROR", None, None),
    ("check_loop_examples", "check_loop_examples", "/loop 示例 --unattended", ("violations",), "ERROR", None, None),
    ("check_line_refs", "check_line_refs", "硬编码行号引用", ("findings",), "WARN", None, None),
    ("check_shard_counts", "check_shard_counts", "分片计数声明", ("findings",), "ERROR", None, None),
    ("check_flow_var_refs", "check_flow_var_refs", "flow 跨分片变量", ("findings",), "ERROR", ["--strict"], None),
    ("check_convention_main_line_dup", "check_convention_dup", "核心约定主行双写", ("duplicates",), "ERROR", None, None),
    ("check_yield_guard", "check_yield_guard", "yield 守卫", ("errors", "warnings"), "ERROR", None, None),
    ("check_release_ask_whitelist", "check_release_ask_whitelist", "发布期问询白名单", ("errors",), "ERROR", None, None),
    ("check_release_debt_landing", "check_release_debt_landing", "发布期欠账落账", ("errors",), "ERROR", None, None),
    ("check_index_staleness", "check_index_staleness", "index ↔ 工作区隐形漂移", ("errors",), "ERROR", None, None),
    ("check_memory_loss", "check_memory_loss", "memory 整段丢失", ("errors",), "WARN", None, None),
)


# 条目自带 WARN 级但只作提示的守卫（WARN 条目计入 INFO）
WARN_AS_INFO = {"check_cross_file_dup", "check_freeze_contract"}


def _make_guard(name, script, label, keys, default, extra, applicable_key):
    def guard(root: Path, r: VerifyResult):
        data, err = _run_guard(root, script, extra)
        if err:
            r.warn(f"{label}检查未能完成：{err}")
            return
        if data is None or (applicable_key and not data.get(applicable_key)):
            return
        buckets = {"ERROR": [], "WARN": [], "INFO": []}
        for key in keys:
            items = data.get(key)
            if not isinstance(items, list):
                continue
            dflt = "WARN" if key in ("warnings", "unreferenced_skill_scripts") else default
            for it in items:
                lv = _level(it, dflt)
                if lv == "WARN" and script in WARN_AS_INFO:
                    lv = "INFO"
                buckets[lv].append(it)
        fix = f" → `python3 .aidp/scripts/{script}.py{' ' + ' '.join(extra) if extra else ''}` 看详情"
        if buckets["ERROR"]:
            r.error(f"{label}：{len(buckets['ERROR'])} 处不通过（{_head(map(_loc, buckets['ERROR']))}）{fix}")
        if buckets["WARN"]:
            r.warn(f"{label}：{len(buckets['WARN'])} 处待处理（{_head(map(_loc, buckets['WARN']))}）{fix}")
        if not buckets["ERROR"] and not buckets["WARN"]:
            extra_info = f"，{len(buckets['INFO'])} 条提示" if buckets["INFO"] else ""
            r.note(f"{label}通过{extra_info}")
    guard.__name__ = name
    guard.__doc__ = f"委派 `.aidp/scripts/{script}.py`：{label}。"
    return guard


for _spec in GUARDS:
    globals()[_spec[0]] = _make_guard(*_spec)


def check_design_goals(root: Path, r: VerifyResult):
    """设计目标棘轮：仅当仓库根有 `设计目标.md` 时生效。"""
    if not (root / "设计目标.md").is_file():
        return
    data, err = _run_guard(root, "check_design_goals")
    if err:
        r.warn(f"设计目标棘轮检查未能完成：{err}")
        return
    if data is None or data.get("skipped"):
        return
    errs = data.get("errors") or []
    if errs:
        r.error(f"设计目标棘轮未通过（{len(errs)} 项）：{_head(str(e.get('anchor')) for e in errs)}"
                f" → 确因需求变化改目标后由人跑 `python3 .aidp/scripts/check_design_goals.py --update-baseline`")
    else:
        r.note(f"设计目标 {data.get('goals', 0)} 条：指纹与 baseline 一致")


def check_cicd_watch_selftest(root: Path, r: VerifyResult):
    sc = _contract_root(root) / "scripts/cicd_watch.py"
    if not sc.is_file():
        return
    try:
        p = subprocess.run([sys.executable, str(sc), "--selftest", "--root", str(root)],
                           capture_output=True, text=True, timeout=120)
        data = json.loads(p.stdout or "{}")
    except Exception as e:
        r.warn(f"cicd_watch 自检未能执行（{e}）")
        return
    bad = [c.get("case") for c in (data.get("cases") or []) if not c.get("ok")]
    if bad:
        r.error(f"cicd_watch.py 自检未通过：{_head(bad, 3)} → `python3 .aidp/scripts/cicd_watch.py --selftest`")
    else:
        r.note(f"cicd_watch 离线自检通过（{len(data.get('cases') or [])} 项）")


# ── 12. 模板项目自检 ────────────────────────────────────────────────────────
def _run_skill_script(name, *args):
    p = subprocess.run([sys.executable, str(HERE / name), *args], capture_output=True, text=True, timeout=300)
    return p.returncode, (p.stdout + p.stderr).strip()


def check_template_bundle(root: Path, r: VerifyResult):
    rc, out = _run_skill_script("mirror_to_bundle.py", "--check", "--root", str(root))
    if rc == 0:
        r.note("本体 ↔ 脚手架 bundle 一致（mirror_to_bundle.py --check）")
    elif rc == 1:
        r.error("本体 ↔ 脚手架 bundle 漂移 → 跑 `python3 .aidp/skills/aidp-code-engineer/scripts/mirror_to_bundle.py`："
                + " ".join(out.splitlines()[:6]))
    else:
        r.error(f"mirror_to_bundle.py --check 异常：{out[:300]}")
    cv, bv = L.changelog_version(root), L.bundle_version()
    try:
        mv = json.loads((L.SKILL_DIR / L.MANIFEST_REL).read_text(encoding="utf-8")).get("scaffold_version")
    except (OSError, ValueError):
        mv = None
    if not (cv and cv == bv == mv):
        r.error(f"范式版本不一致：{L.CHANGELOG}={cv} / SCAFFOLD_VERSION={bv} / CONTRACT_MANIFEST={mv}"
                f" → 跑 mirror_to_bundle.py")
    else:
        r.note(f"范式版本一致：{cv}")


# 根 .gitignore 里只服务模板仓库自身、不下发的规则
TEMPLATE_ONLY_GITIGNORE = {"/.claude/", "/.codex/", "/.dsh/", "/.agents/"}


def _gitignore_rules(text: str) -> set:
    return {l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")}


def check_template_gitignore_tpl(root: Path, r: VerifyResult):
    """下游 .gitignore 托管区模板（脚手架 `sources/root/gitignore.tpl`）须覆盖模板仓库根 .gitignore 的全部规则。"""
    tpl = L.SKILL_DIR / "sources/root/gitignore.tpl"
    if not tpl.is_file():
        r.error(f"缺下游 .gitignore 模板真源 {tpl}")
        return
    gi_text = re.sub(r"# >>> AIDP-AGENT-ADAPTERS.*?# <<< AIDP-AGENT-ADAPTERS <<<", "", L.read_text(root / ".gitignore"),
                     flags=re.S)      # agent_sync 生成的入口清单属本机装配结果，不要求进模板
    have = _gitignore_rules(gi_text)
    block = "\n".join(L.gitignore_block(L.read_text(tpl)))
    missing = sorted(have - _gitignore_rules(block) - TEMPLATE_ONLY_GITIGNORE)
    if missing:
        r.error(f"根 .gitignore 有 {len(missing)} 条规则未进下游模板 gitignore.tpl：{_head(missing, 8, ', ')}"
                f" → 补进 sources/root/gitignore.tpl 托管区，或登记为模板专用（verify.py::TEMPLATE_ONLY_GITIGNORE）")
    else:
        r.note("下游 gitignore.tpl 覆盖模板仓库根 .gitignore 的全部规则")


def check_memory_tpl_sync(root: Path, r: VerifyResult):
    rc, out = _run_skill_script("sync_memory_md.py", "--check", "--root", str(root))
    if rc == 0:
        r.note("assets/AGENTS.md.tpl 与 .aidp/AIDP-AGENTS.md 一致")
    else:
        r.error(f"assets/AGENTS.md.tpl 漂移或 .aidp/AIDP-AGENTS.md 结构不符：{out[:300]}")


# ── main ────────────────────────────────────────────────────────────────────
COMMON_GUARDS = ["check_flow_slice_size", "check_scripts_readme_coverage"] + [g[0] for g in GUARDS] \
    + ["check_design_goals", "check_cicd_watch_selftest"]


def main(argv=None) -> int:
    global READ_ONLY
    argv = list(sys.argv[1:] if argv is None else argv)
    READ_ONLY = "--read-only" in argv
    template = "--template" in argv
    no_guards = "--no-guards" in argv
    mode_override = None
    if "--adapter-mode" in argv:
        i = argv.index("--adapter-mode")
        mode_override = argv[i + 1] if i + 1 < len(argv) else None
        del argv[i:i + 2]
    if "-h" in argv or "--help" in argv:
        print(__doc__)
        return 0
    pos = [x for x in argv if not x.startswith("--")]
    if not pos:
        print(__doc__)
        return 2
    root = Path(pos[0]).resolve()
    if not root.is_dir():
        print(f"错误: 项目根目录不存在: {root}")
        return 2
    template = template or L.is_template_project(root)
    version = pos[1] if len(pos) > 1 else None
    user = pos[2] if len(pos) > 2 else None
    if not template and not (version and user):
        print("用法: python3 verify.py <project_root> <version> <user> [--read-only]（模板项目：--template）")
        return 2
    if template and version and version == L.bundle_version():
        print(f"错误: <version> 传入的是范式版本号 {version}；这里要项目业务版本号（模板自检可省略版本参数）")
        return 2

    print(f"[verify] 项目根: {root}")
    print(f"[verify] 模式: {'模板项目自检' if template else '下游项目'}" + ("（只读）" if READ_ONLY else ""))
    if not template:
        print(f"[verify] 版本: {version}, 用户: {user}")
    r = VerifyResult()
    vcs_mode = _vcs_mode(root)
    print(f"[verify] vcs_mode={vcs_mode}")
    if vcs_mode == "none":
        for capability in ("runtime-artifact-tracking", "credential-tracking", "backup-tracking"):
            r.note(f"{capability}: unsupported:vcs-disabled")
    if not template and _runtime_homes(root):
        check_native_runtime(root, r)

    check_directories(root, version, user, template, r)
    check_files(root, template, r)
    if template:
        check_template_memory(root, r)
    else:
        check_memory_file(root, r)
    if template:
        r.note("模板项目不携带 Agent 适配层（.claude/.codex/.dsh/.agents 由脚手架在下游按实际 Agent 生成）")
    else:
        check_agent_adapters(root, mode_override, r)
    check_docs_init_sync(root, template, r)
    check_code_layout(root, r)
    check_code_readme(root, r)
    check_deployment_two_track_layout(root, r)
    check_deployment_docs(root, r)
    check_deployment_tools(root, r)
    check_sql_version_dir_consistency(root, r)
    if vcs_mode == "git":
        check_runtime_artifact_vcs(root, r)
        check_tracked_credentials(root, r)
    if not template:
        check_gitignore(root, r)
    check_unreplaced_placeholders(root, r)
    check_backup_hygiene(root, r)
    check_pending_rewrite_queue(root, r)
    check_project_claude_aidp_conflict(root, r)
    check_convention_anchor_consistency(root, r)
    if template:
        check_template_bundle(root, r)
        check_memory_tpl_sync(root, r)
        check_template_gitignore_tpl(root, r)
    else:
        check_version(root, version, r)
        check_memory_structure(root, version, user, r)
        check_prototype_baseline(root, version, r)
        check_env_key_freshness(root, r)
        check_contract_drift(root, r)
    if not no_guards:
        for name in COMMON_GUARDS:
            globals()[name](root, r)

    return 0 if r.summary() else 1


if __name__ == "__main__":
    sys.exit(main())
