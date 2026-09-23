#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold_lib.py —— 脚手架各脚本共用的常量与确定性工具（仅标准库）。

被 `scaffold.py` / `migrate.py` / `verify.py` / `mirror_to_bundle.py` 共同 import，
目录清单、契约目录、忽略集、占位符渲染、gitignore 托管区、备份保留策略都只在这里定义一次。
"""
import hashlib
import importlib.util
import sys
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

SKILL_NAME = "aidp-code-engineer"
SKILL_DIR = Path(__file__).resolve().parent.parent
ASSETS = SKILL_DIR / "assets"
BUNDLE_AIDP = ASSETS / "aidp"
# 模板仓库里脚手架 skill 的落点（标准 skill 仓库结构：根级 `skills/<name>/`）。
TEMPLATE_SKILL_REL = f"skills/{SKILL_NAME}"


def template_aidp():
    """脚手架 skill 就地所在的模板仓库 `.aidp/`；不在模板仓库内（下游安装位）时返回 None。

    兼容两种落点：根级 `skills/<name>/`（当前标准结构，`parents[1]` 即仓库根）与
    历史的 `.aidp/skills/<name>/`（`parents[1]` 即 `.aidp` 本身）。
    """
    for cand in (SKILL_DIR.parents[1], SKILL_DIR.parents[1] / ".aidp"):
        if cand.name == ".aidp" and (cand / "scripts/agent_sync.py").is_file():
            return cand
    return None


def template_root():
    """脚手架 skill 就地所在的模板仓库根；不在模板仓库内时返回 None。"""
    aidp = template_aidp()
    return aidp.parent if aidp else None

# ── 契约目录 ────────────────────────────────────────────────────────────────
# 受版本门控：项目版本 < 脚手架版本才覆盖已有文件；同版本只补缺失文件。
GATED_DIRS = ("agents", "commands", "rules", "flows", "reference", "hooks", "templates", "skills", "plugins")
# 不受版本门控：字节不同即覆盖。
UNGATED_DIRS = ("scripts",)
MIRROR_DIRS = ("agents", "commands", "rules", "flows", "reference", "scripts", "hooks", "templates", "plugins")
# 模板项目自有、不下发的资产（相对 `.aidp/`）：回归单测与设计目标棘轮 baseline（`设计目标.md` 本身不下发）
TEMPLATE_OWNED = ("scripts/tests/", "scripts/design-goals-baseline.txt")
# Agent 原生运行包包含完整静态运行契约；脚手架自身与模板维护资产不递归下发。
RUNTIME_DIRS = (
    "agents", "commands", "flows", "hooks", "plugins", "reference",
    "rules", "scripts", "skills", "templates",
)
RUNTIME_EXCLUDES = (
    "skills/aidp-code-engineer/",
    "scripts/tests/",
    "scripts/design-goals-baseline.txt",
)
# 脚手架自身安装到下游时不带的子树（相对 skill 目录）：模板回归单测、下游模板真源（下游只用派生出的 assets/）
SELF_INSTALL_EXCLUDE = ("scripts/tests/", "sources/")
def is_template_owned(rel_to_aidp: str) -> bool:
    return any(rel_to_aidp == x or (x.endswith("/") and rel_to_aidp.startswith(x)) for x in TEMPLATE_OWNED)


# 用户填充型契约：脚手架发骨架、项目持续填写；填过的不覆盖，改入语义改写队列。
USER_FILLABLE_CONTRACTS = {"reference/子Agent必读.md"}
USER_FILLABLE_BASELINE = ".aidp-user-fillable.json"
# 按需安装的可选规则：(模板位, 安装位)，均相对 `.aidp/`。
OPTIONAL_RULES = (("templates/optional-rules/webmcp.md", "rules/webmcp.md"),)
OPTIONAL_INSTALLED_CONTRACTS = {inst for _, inst in OPTIONAL_RULES}

REWRITE_QUEUE_FILE = ".aidp-rewrite-queue.txt"
MANIFEST_REL = "assets/CONTRACT_MANIFEST.json"
MEMORY_TPL_REL = "assets/AGENTS.md.tpl"
PARADIGM_MEMORY_REL = ".aidp/AIDP-AGENTS.md"   # 模板仓库的下发记忆源（仅模板仓库有；不镜像、经 sync_memory_md.py 生成模板）
CONFIG_TPL_REL = "assets/aidp-config.yaml.tpl"
VERSION_REL = "assets/SCAFFOLD_VERSION"
CHANGELOG = "版本变更历史.md"

# 项目级 memory 模板（create-if-missing，绝不覆盖真实内容）
MEMORY_TEMPLATES = (
    ("projectBrief.md.tpl", "memory/projectBrief.md"),
    ("productContext.md.tpl", "memory/productContext.md"),
    ("systemPatterns.md.tpl", "memory/systemPatterns.md"),
    ("techContext.md.tpl", "memory/techContext.md"),
    ("databaseBaseline.md.tpl", "memory/databaseBaseline.md"),
)
ARCH_DOCS = ("架构约束.md", "技术选型.md", "UI规范约束.md")

# ── 忽略集（镜像、下发、指纹统一口径）────────────────────────────────────────
IGNORE_DIRS = {"__pycache__", ".git", ".pytest_cache", "node_modules"}
IGNORE_SUFFIX = {".pyc", ".pyo"}
IGNORE_FILES = {".DS_Store", "Thumbs.db", "config.json", ".env"}
_CRED_RE = re.compile(r"^auth\..+\.json$")


def is_ignored(rel_parts) -> bool:
    parts = list(rel_parts)
    if any(p in IGNORE_DIRS for p in parts):
        return True
    name = parts[-1] if parts else ""
    return (name in IGNORE_FILES or Path(name).suffix in IGNORE_SUFFIX
            or bool(_CRED_RE.match(name)))


def iter_files(base: Path):
    """base 下全部文件（排序、按忽略集过滤），yield (相对 posix 路径, Path)。"""
    if not base.is_dir():
        return
    for p in sorted(base.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(base)
        if is_ignored(rel.parts):
            continue
        yield rel.as_posix(), p


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ── 版本号 ──────────────────────────────────────────────────────────────────
def parse_ver(s):
    """`V1.2.3` / `1.2` → (1, 2, 3) / (1, 2, 0)；解析失败 → None。"""
    if not s:
        return None
    m = re.search(r"[vV]?(\d+)\.(\d+)(?:\.(\d+))?", str(s).strip())
    if not m:
        return None
    return tuple(int(x) if x is not None else 0 for x in m.groups())


def bundle_version(skill_dir: Path = SKILL_DIR):
    p = skill_dir / VERSION_REL
    try:
        return p.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def changelog_version(root: Path):
    """`版本变更历史.md`「当前范式版本」标记 `**AIDP V<x.y.z>**`。"""
    try:
        text = (root / CHANGELOG).read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"\*\*AIDP\s+(V\d+\.\d+\.\d+)\*\*", text)
    return m.group(1) if m else None


VERSION_RE = re.compile(r"^V\d+\.\d+(\.\d+)?$")
USER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


# ── 目录骨架（scaffold 创建 / verify 校验的单一信源）─────────────────────────
PROJECT_DIRS = (
    ".aidp/agents", ".aidp/commands", ".aidp/rules", ".aidp/flows", ".aidp/reference",
    ".aidp/scripts", ".aidp/hooks", ".aidp/templates", ".aidp/skills",
    "code",
    "docs/init", "docs/architecture", "docs/references", "docs/audit", "docs/deployment/tools",
    "docs/bugfix", "docs/design/detail", "docs/implementation", "docs/plans", "docs/prompts",
    "docs/prototype", "docs/reports", "docs/requirements", "docs/testing",
    "memory", "env",
)


def version_dirs(version: str, user: str):
    return (
        f"docs/requirements/{version}/产品提供",
        f"docs/requirements/{version}/研发需求",
        f"docs/design/detail/{version}",
        f"docs/prototype/{version}/code",
        f"docs/prototype/{version}/mockup",
        f"docs/deployment/{version}/sql/增量",
        f"docs/deployment/{version}/sql/全量",
        f"docs/deployment/{version}/配置文件/增量",
        f"docs/deployment/{version}/配置文件/全量",
        f"docs/deployment/{version}/部署流程",
        f"docs/testing/{version}/研发自测",
        f"docs/plans/{version}",
        f"docs/reports/{version}",
        f"docs/prompts/{version}",
        f"docs/bugfix/{version}",
        f"docs/implementation/{version}/{user}",
        f"memory/{version}/{user}/sprints",
    )


# 源码根标志：出现在 code/{side}/ 根下即缺 {子项目} 中间层
PROJECT_ROOT_MARKERS = {
    "src", "pom.xml", "build.gradle", "build.gradle.kts", "package.json", "go.mod",
    "requirements.txt", "pyproject.toml", "setup.py", "Cargo.toml", "composer.json",
}


def code_has_custom_subdirs(root: Path) -> bool:
    """code/ 下已有 frontend/backend/sql 之外的非空子目录（保留原结构，不补建规范目录）。"""
    code = root / "code"
    if not code.is_dir():
        return False
    for item in code.iterdir():
        if item.is_dir() and not item.name.startswith(".") \
                and item.name not in ("sql", "frontend", "backend") and any(item.iterdir()):
            return True
    return False


def skeleton_dirs(root: Path, version: str, user: str, include_version: bool = True):
    dirs = list(PROJECT_DIRS)
    if include_version:
        dirs += list(version_dirs(version, user))
    if not code_has_custom_subdirs(root):
        dirs += ["code/frontend", "code/backend"]
    return dirs


# ── 占位符渲染 ──────────────────────────────────────────────────────────────
PLACEHOLDER_RE = re.compile(r"\{\{(project|project_cn|user|version|date)\}\}")


def render(text: str, ctx: dict) -> str:
    return PLACEHOLDER_RE.sub(lambda m: str(ctx.get(m.group(1), m.group(0))), text)


# ── 记忆文件形态 ────────────────────────────────────────────────────────────
SHELL_BODY = "@AGENTS.md\n"
CUSTOM_HEADING = "## 项目自定义"
CUSTOM_MARK = "<!-- AIDP:PROJECT-CUSTOM"


STATUS_HEADING = "## 当前状态"
# 「当前状态」段里由 /memory-sync、/version、/sprint-* 维护的字段：升级时保留项目值
STATUS_FIELDS = ("当前版本", "当前开发者", "当前 Sprint", "Sprint 目标", "整体进度", "最后更新")
_STATUS_LINE_RE = re.compile(r"^- \*\*(.+?)\*\*[：:]")


def is_shell(text: str) -> bool:
    body = re.sub(r"<!--.*?-->", "", text or "", flags=re.S)
    lines = [l.strip() for l in body.splitlines() if l.strip() and not l.strip().startswith("#")]
    return bool(lines) and all(re.match(r"^@\.?/?AGENTS\.md$", l) for l in lines)


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def memory_bodies(root: Path) -> dict:
    """{文件名: 正文}，只收非空、非 `@AGENTS.md` 薄壳的 CLAUDE.md / AGENTS.md。"""
    out = {}
    for name in ("AGENTS.md", "CLAUDE.md"):
        t = read_text(root / name)
        if t.strip() and not is_shell(t):
            out[name] = t
    return out


def memory_target(root: Path, agents) -> str:
    """正文应落的文件：只有 Claude Code → CLAUDE.md（若 AGENTS.md 已有正文则仍用 AGENTS.md）；否则 AGENTS.md。"""
    if list(agents) == ["claude"]:
        bodies = memory_bodies(root)
        if "AGENTS.md" in bodies and "CLAUDE.md" not in bodies:
            return "AGENTS.md"
        return "CLAUDE.md"
    return "AGENTS.md"


def looks_like_aidp_body(text: str) -> bool:
    return "## 当前状态" in text and "核心约定" in text


def custom_section(text: str) -> str:
    """记忆文件「项目自定义」段正文（不含标题）；无该段 → ""。"""
    idx = text.find("\n" + CUSTOM_HEADING)
    if idx < 0:
        return ""
    return text[idx + len(CUSTOM_HEADING) + 1:]


def _section_span(lines: list, heading: str):
    """`heading` 所在行到下一个同级（`## `）标题或 `---` 分隔线之前的行区间；无 → None。"""
    try:
        start = next(i for i, l in enumerate(lines) if l.strip() == heading)
    except StopIteration:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].startswith("## ") or lines[j].strip() == "---":
            end = j
            break
    return start, end


def merge_memory_upgrade(old: str, new_rendered: str) -> str:
    """项目记忆文件升级的确定性合并（按锚点，不做语义改写）。

    - 「项目自定义」段之前：取新模板正文；
    - 其中「当前状态」段：`STATUS_FIELDS` 各行取旧文件的值；旧段里新模板没有的其他 `- **X**：` 行追加保留；
    - 「项目自定义」段（含标题）：旧文件原样保留；旧文件无该段 → 用新模板的空段。
    """
    new_idx = new_rendered.find("\n" + CUSTOM_HEADING)
    head = new_rendered if new_idx < 0 else new_rendered[:new_idx + 1]
    old_idx = old.find("\n" + CUSTOM_HEADING)
    if old_idx >= 0:
        tail = old[old_idx + 1:]
    else:
        tail = "" if new_idx < 0 else new_rendered[new_idx + 1:]

    old_lines, head_lines = old.splitlines(), head.splitlines()
    old_span, new_span = _section_span(old_lines, STATUS_HEADING), _section_span(head_lines, STATUS_HEADING)
    if old_span and new_span:
        old_vals, old_extra = {}, []
        for l in old_lines[old_span[0] + 1:old_span[1]]:
            m = _STATUS_LINE_RE.match(l)
            if m:
                old_vals[m.group(1).strip()] = l
        new_keys = set()
        out = []
        for l in head_lines[new_span[0] + 1:new_span[1]]:
            m = _STATUS_LINE_RE.match(l)
            if m:
                key = m.group(1).strip()
                new_keys.add(key)
                if key in STATUS_FIELDS and key in old_vals:
                    l = old_vals[key]
            out.append(l)
        old_extra = [line for k, line in old_vals.items() if k not in new_keys]
        if old_extra:
            last = max((i for i, l in enumerate(out) if _STATUS_LINE_RE.match(l)), default=len(out) - 1)
            out[last + 1:last + 1] = old_extra
        head_lines[new_span[0] + 1:new_span[1]] = out
        head = "\n".join(head_lines) + "\n"
    head = head.rstrip("\n") + "\n\n" if tail else head
    return head + tail if tail else head


# ── gitignore 托管区 ────────────────────────────────────────────────────────
GITIGNORE_BEGIN = "# >>> AIDP-GITIGNORE-MANAGED:BEGIN >>>"
GITIGNORE_END = "# <<< AIDP-GITIGNORE-MANAGED:END <<<"


def gitignore_block(tpl_text: str) -> list:
    lines = tpl_text.splitlines()
    if GITIGNORE_BEGIN in lines and GITIGNORE_END in lines:
        return lines[lines.index(GITIGNORE_BEGIN):lines.index(GITIGNORE_END) + 1]
    return [GITIGNORE_BEGIN] + lines + [GITIGNORE_END]


def _gi_norm(rule: str) -> str:
    return rule.strip().lstrip("/").rstrip("/")


def merge_gitignore(existing, tpl_text: str) -> str:
    """返回同步后的 .gitignore 文本：托管区整块替换，区外项目规则原样保留。

    无标记的既有文件首次收编：与托管区重复的规则行移入托管区，其余留作项目自定义。
    """
    block = gitignore_block(tpl_text)
    if existing is None:
        return "\n".join(block) + "\n"
    lines = existing.splitlines()
    if GITIGNORE_BEGIN in lines and GITIGNORE_END in lines:
        b, e = lines.index(GITIGNORE_BEGIN), lines.index(GITIGNORE_END)
        return "\n".join(lines[:b] + block + lines[e + 1:]).rstrip("\n") + "\n"
    owned = {_gi_norm(l) for l in block if l.strip() and not l.strip().startswith("#")}
    kept = [l for l in lines if not (l.strip() and not l.strip().startswith("#")
                                     and _gi_norm(l) in owned)]
    # 折叠只剩标题注释、规则已被收编的小节
    out = []
    for i, l in enumerate(kept):
        if re.match(r"^#\s*===.*===\s*$", l.strip()):
            has_rule = False
            for nxt in kept[i + 1:]:
                s = nxt.strip()
                if re.match(r"^#\s*===.*===\s*$", s):
                    break
                if s and not s.startswith("#"):
                    has_rule = True
                    break
            if not has_rule:
                continue
        out.append(l)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    parts = block[:]
    if out:
        parts += ["", "# === 项目自定义忽略规则（托管区之外，升级不覆盖）==="] + out
    return "\n".join(parts).rstrip("\n") + "\n"


# ── 用户填充型契约 ──────────────────────────────────────────────────────────
def _uf_load(root: Path) -> dict:
    try:
        return json.loads((root / USER_FILLABLE_BASELINE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def uf_record(root: Path, label: str, blob: bytes):
    data = _uf_load(root)
    data[label] = sha256(blob)
    try:
        (root / USER_FILLABLE_BASELINE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass


def _has_user_content(cur_text: str, tpl_text: str) -> bool:
    if cur_text == tpl_text:
        return False
    tpl_lines = {l.strip() for l in tpl_text.splitlines() if l.strip()}
    return any(l.strip() and l.strip() not in tpl_lines for l in cur_text.splitlines())


def decide_user_fillable(root: Path, label: str, cur_blob: bytes, new_bytes: bytes,
                         prev_delivered=None) -> str:
    """项目会填写 / 改写的下发文件（用户填充型契约、docs 结构性 README、memory/README.md）的处置：
    `uptodate` | `refresh` | `keep`。

    权威判据是指纹台账 `.aidp-user-fillable.json`（记「上次写给项目、且已合并进项目的骨架」指纹）：
    - 项目文件与台账骨架逐字节相等 ⇒ 未填写 ⇒ `refresh`；
    - 已填写，但新骨架与台账骨架相同 ⇒ 骨架没变、无可合并 ⇒ `uptodate`（不入队）；
    - 已填写且骨架变了 ⇒ `keep`（调用方入语义改写队列；finalize 收口时把台账推进到新骨架）。
    台账缺失时依次回落：与上一版 bundle 下发件（`prev_delivered`）相等 ⇒ `refresh`；内容比对（只朝「保护」一侧失真）。
    """
    if cur_blob == new_bytes:
        return "uptodate"
    recorded = _uf_load(root).get(label)
    if recorded is not None:
        if recorded == sha256(cur_blob):
            return "refresh"
        return "uptodate" if recorded == sha256(new_bytes) else "keep"
    if prev_delivered is not None and prev_delivered == cur_blob:
        return "refresh"
    cur = cur_blob.decode("utf-8", errors="replace")
    new = new_bytes.decode("utf-8", errors="replace")
    return "keep" if (not cur or _has_user_content(cur, new)) else "refresh"


# ── 语义改写队列 ────────────────────────────────────────────────────────────
QUEUE_HEADER = (
    "# AIDP 语义改写待办清单（每行：<项目内目标相对路径>\\t<新版模板相对路径>\\t<入队时目标文件 sha256>）\n"
    "# 处理方式：逐行 Read 目标文件与新版模板 → 以模板的结构/术语/路径为准、保留项目自有内容改写 → Write。\n"
    "# 模板中的 {{project}} {{user}} {{version}} {{date}} 按本项目实际值替换。\n"
    "# 全部处理完【不要手工删除本文件】：跑 finalize_upgrade.py，它逐条核验目标文件已改写后删除本文件并收口；\n"
    "# 确认某条无需改动时，用 finalize_upgrade.py --accept <目标路径> 显式标记。\n\n"
)
INSTALLED_SKILL_REL = f".aidp/skills/{SKILL_NAME}"


def queue_entries(root: Path) -> list:
    p = root / REWRITE_QUEUE_FILE
    if not p.is_file():
        return []
    return [l.strip() for l in read_text(p).splitlines() if l.strip() and not l.strip().startswith("#")]


def parse_queue_entry(line: str) -> dict:
    parts = line.split("\t")
    return {"target": parts[0], "template": parts[1] if len(parts) > 1 else "",
            "before": parts[2] if len(parts) > 2 else ""}


def project_template_rel(root: Path, tpl: Path) -> str:
    """队列模板路径指向项目内的脚手架 SKILL 安装位。"""
    tpl = Path(tpl)
    try:
        relative = tpl.resolve().relative_to(SKILL_DIR.resolve()).as_posix()
        project = Path(root)
        if (project / ".agents/aidp").is_dir():
            skill = ".agents/skills/aidp-code-engineer"
        elif (project / ".claude/aidp").is_dir():
            skill = ".claude/skills/aidp-code-engineer"
        else:
            skill = INSTALLED_SKILL_REL
        return f"{skill}/{relative}"
    except ValueError:
        pass
    try:
        return tpl.resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return tpl.name


def ledger_label(target_rel: str) -> str:
    """队列目标路径 → 指纹台账键（`.aidp/` 下的契约去前缀；docs / memory 文件原样）。"""
    return target_rel[len(".aidp/"):] if target_rel.startswith(".aidp/") else target_rel


def enqueue(root: Path, rel: str, tpl: Path):
    entries = queue_entries(root)
    if any(parse_queue_entry(e)["target"] == rel for e in entries):
        return False
    target = root / rel
    before = sha256(target.read_bytes()) if target.is_file() else ""
    entries.append(f"{rel}\t{project_template_rel(root, tpl)}\t{before}")
    (root / REWRITE_QUEUE_FILE).write_text(QUEUE_HEADER + "\n".join(entries) + "\n", encoding="utf-8")
    return True


# ── 备份与保留策略 ──────────────────────────────────────────────────────────
BACKUP_RE = re.compile(r"^\.aidp-backup-(\d{14,20})$")
PRUNE_KEEP_LAST_DEFAULT = 1
PRUNE_KEEP_DAYS_DEFAULT = 7
BACKUP_HYGIENE_MAX_DIRS = 2
BACKUP_HYGIENE_MAX_BYTES = 100 * 1024 * 1024


def _stamp(digits: str, path: Path):
    for fmt, n in (("%Y%m%d%H%M%S%f", 20), ("%Y%m%d%H%M%S", 14)):
        if len(digits) == n:
            try:
                return datetime.strptime(digits, fmt)
            except ValueError:
                break
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024.0
    return f"{size:.1f}GB"


def scan_backups(root: Path):
    """仓库根下目录名**严格匹配** `.aidp-backup-<时间戳>` 的备份，新 → 旧。"""
    found = []
    if root.is_dir():
        for child in root.iterdir():
            if child.is_dir() and not child.is_symlink():
                m = BACKUP_RE.match(child.name)
                if m:
                    found.append((child, _stamp(m.group(1), child)))
    found.sort(key=lambda t: t[1] or datetime.min, reverse=True)
    return found


def prune_backups(root: Path, keep_last=PRUNE_KEEP_LAST_DEFAULT, keep_days=PRUNE_KEEP_DAYS_DEFAULT,
                  dry_run=False, now=None) -> dict:
    """保留「最近 keep_last 个 ∪ keep_days 天内」的备份，其余删除。keep_last<=0 = 不清理。"""
    result = {"removed": [], "kept": [], "failed": [], "disabled": False, "dry_run": dry_run}
    if keep_last is not None and keep_last <= 0:
        result["disabled"] = True
        return result
    now = now or datetime.now()
    cutoff = now - timedelta(days=keep_days) if keep_days and keep_days > 0 else None
    for rank, (path, stamp) in enumerate(scan_backups(root)):
        by_count = rank < keep_last
        by_age = cutoff is not None and (stamp is None or stamp >= cutoff)
        if by_count or by_age:
            result["kept"].append(path.name)
            continue
        if dry_run:
            result["removed"].append(path.name)
            continue
        try:
            shutil.rmtree(path)
            result["removed"].append(path.name)
        except OSError:
            result["failed"].append(path.name)
    return result


# ── git 小工具 ──────────────────────────────────────────────────────────────
def git(root: Path, *args, check=False):
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=check)
    except (OSError, subprocess.SubprocessError):
        return None


def git_user(root: Path):
    r = git(root, "config", "user.name")
    return r.stdout.strip() if r is not None and r.returncode == 0 else ""


def git_tracked(root: Path, rel: str) -> bool:
    r = git(root, "ls-files", "--error-unmatch", "--", rel)
    return r is not None and r.returncode == 0


def move_path(root: Path, src_rel: str, dst_rel: str, copy=False):
    """已跟踪用 git mv（保留历史），否则普通移动；copy=True 时复制。"""
    src, dst = root / src_rel, root / dst_rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    if copy:
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
        return "copy"
    listed = git(root, "ls-files", "--", src_rel)
    if listed is not None and listed.returncode == 0 and listed.stdout.strip():
        r = git(root, "mv", src_rel, dst_rel)
        if r is not None and r.returncode == 0:
            return "git mv"
    shutil.move(str(src), str(dst))
    return "move"


# ── 项目侧共享脚本加载（readme_policy 等）──────────────────────────────────
def load_project_module(name: str):
    """从脚手架 bundle（`assets/aidp/scripts`）或模板仓库 `.aidp/scripts` 加载模块。"""
    bases = [BUNDLE_AIDP / "scripts"]
    aidp = template_aidp()
    if aidp:
        bases.append(aidp / "scripts")
    for base in bases:
        p = base / f"{name}.py"
        if p.is_file():
            spec = importlib.util.spec_from_file_location(f"_aidp_{name}", p)
            mod = importlib.util.module_from_spec(spec)
            # ⛔ 不写字节码：bundle 是镜像产物，落下 __pycache__ 会被 mirror --check 判为漂移
            saved, sys.dont_write_bytecode = sys.dont_write_bytecode, True
            try:
                spec.loader.exec_module(mod)
            finally:
                sys.dont_write_bytecode = saved
            return mod
    raise ImportError(f"找不到 {name}.py（脚手架 bundle 缺失？先跑 mirror_to_bundle.py）")


def is_template_project(root: Path) -> bool:
    """AIDP 模板项目自身：携带 `版本变更历史.md` + 下发记忆源 `.aidp/AIDP-AGENTS.md`
    + 脚手架 skill 真源（根级 `skills/aidp-code-engineer/`，兼容历史 `.aidp/skills/` 落点），
    且未被脚手架打过版本戳。"""
    import scaffold_marker  # 同目录
    if scaffold_marker.is_downstream(root):
        return False
    return ((root / CHANGELOG).is_file()
            and (root / PARADIGM_MEMORY_REL).is_file()
            and any((root / rel / "SKILL.md").is_file()
                    for rel in (TEMPLATE_SKILL_REL, INSTALLED_SKILL_REL)))
