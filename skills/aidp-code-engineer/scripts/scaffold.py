#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""scaffold.py —— AIDP 脚手架主入口：init（空项目）/ migrate（已有项目改建）/ upgrade（脚手架版本升级）。

用法：
    python3 scaffold.py <root> --detect                       # 只探测，输出 JSON（模式 / Agent / 代码与输入扫描）
    python3 scaffold.py <root> [--mode auto|init|migrate|upgrade] [--version V0.1.0] [--user NAME]
                        [--agent claude,codex,dsh] [--adapter-mode link|copy] [--name-cn 中文名]
                        [--force] [--keep-backups N] [--keep-days N] [--no-agent-sync] [--json]

模式自动判定：项目根有 `.aidp/` → upgrade；无 `.aidp/` 但有代码 → migrate；否则 → init。

Agent 判定：项目根已有 `.claude/` `.codex/` `.dsh/` 之一或多者 → 按其装配；都没有 → `--agent`
→ 环境变量 `AIDP_AGENT` → 交互终端询问 → 默认 claude；并创建对应标记目录。
装配（入口、hook 接线、记忆文件形态）由目标项目的 `.aidp/scripts/agent_sync.py` 完成。

执行内容（三模式共用一条确定性流水线，差异只在已有内容的处置）：
  备份 → 目录骨架 → `.aidp/` 契约（版本门控 + 用户填充型保护 + 本地改动覆盖清单）→ `.aidp/scripts/`（字节不同即覆盖）
  → docs 范式文档与结构性 README（项目改过的进语义改写队列）→ memory 配置与模板
  → 根 README / env / .gitignore 托管区 → 项目记忆文件（按锚点确定性合并）
  → 脚手架 skill 自身受管安装到 Agent 可发现位（`.claude/skills/` 与 `.agents/skills/`）→ 导航 README 与 .gitkeep
  → 孤儿契约报告 → 版本戳（有语义改写待办时写 scaffold.pending）→ agent_sync 装配。
  任何覆盖已有文件的写入之前都先备份到 `.aidp-backup-<时间戳>/`。

退出码：0 完成（可能留有语义改写待办，见输出 `pending`）· 2 参数或环境错误
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scaffold_lib as L  # noqa: E402
import scaffold_marker  # noqa: E402
import migrate  # noqa: E402
import runtime_layout  # noqa: E402

_runtime_scripts = (L.template_aidp() or L.BUNDLE_AIDP) / "scripts"
if not (_runtime_scripts / "vcs.py").is_file():
    _runtime_scripts = L.BUNDLE_AIDP / "scripts"
sys.path.insert(0, str(_runtime_scripts))
import vcs  # noqa: E402
import agent_sync as agent_adapter  # noqa: E402

LEGACY_AIDP_DIR = ".aidp"
DISABLED_AGENT_MARK = ".aidp-agent-disabled"
KNOWN_AGENTS = ("claude", "codex", "dsh")
MARKER_DIRS = {"claude": ".claude", "codex": ".codex", "dsh": ".dsh"}
AGENT_ALIASES = {"claude-code": "claude", "claudecode": "claude", "deepseek": "dsh",
                 "deepseek-harness": "dsh", "openai-codex": "codex"}
EXEC_SUFFIX = {".py", ".sh"}
DSH_PLUGIN_PACKAGE = "github:SugarFatFree/dsh-agent-extension"
DSH_PLUGIN_NAME = "dsh-agent-extension"
DSH_COMMAND_PLUGIN = ("dsh", "plugin", "--profile", "web", "add", DSH_PLUGIN_PACKAGE)
DSH_PLUGIN_LIST_JSON = ("dsh", "plugin", "--profile", "web", "list", "--json")
DSH_PLUGIN_LIST = ("dsh", "plugin", "--profile", "web", "list")
DSH_PLUGIN_VERSION = ("dsh", "--version")
DSH_COMMAND_PLUGIN_RETRY = " ".join(DSH_COMMAND_PLUGIN)
DSH_COMMAND_PLUGIN_TIMEOUT = 120
DSH_PLUGIN_PROBE_TIMEOUT = 30
DSH_PLUGIN_DETAIL_LIMIT = 300
# 扩展状态取值；⛔ 「本进程调不起 dsh」不得推论成「扩展没装」。
DSH_STATE_READY = ("already-installed", "installed")
DSH_STATE_LABEL = {
    "already-installed": "已安装，本次未执行 add",
    "installed": "本次安装并复查命中",
    "not-installed": "add 返回 0 但清单未命中，按未装处理",
    "cli-unavailable": "本进程找不到 dsh，安装状态未验证（⛔ 不等于扩展缺失）",
    "unknown": "dsh 在但状态无从判断（⛔ 不等于扩展缺失）",
    "install-failed": "安装失败，见 WARN 与重试命令",
}

# 控制台状态记号：默认 emoji，main() 起手按实际 stdout 编码决定是否 ASCII 降级（GBK 控制台）。
MARKS = dict(L._CONSOLE_MARKS)

NAV_PURPOSES = {
    "产品提供": "产品方提供的原始输入（PRD、需求说明等）",
    "研发需求": "由 /sprint-requirements 生成的研发需求",
    "code": "原型代码（按模块）",
    "mockup": "高保真原型（图片 / PDF / 设计源文件）",
    "sql": "SQL 脚本（增量轨 / 全量轨）",
    "配置文件": "配置产物（增量轨 / 全量轨）",
    "部署流程": "部署 SOP 与 SQL 执行台账",
    "增量": "增量轨：已有环境升级所需的变更",
    "全量": "全量轨：从零搭建所需的完整产物",
    "研发自测": "研发自测方案与用例（dev-manual-testcase 生成）",
    "正式用例": "测试人员提供的正式用例",
    "sprints": "Sprint 归档（/sprint-close 写入）",
    "detail": "详细设计（按版本隔离）",
    "tools": "跨版本运维 / 一次性工具归档",
    "frontend": "前端子项目",
    "backend": "后端子项目",
}


class Report:
    def __init__(self, journal=None):
        self.actions, self.warnings, self.notes = [], [], []
        self.journal = journal

    def act(self, op, path, why=""):
        self.actions.append({"op": op, "path": path, "why": why})
        if self.journal is not None and op in {"create", "install", "update", "merge", "render"}:
            self.journal.record(path)

    def warn(self, msg):
        self.warnings.append(msg)

    def note(self, msg):
        self.notes.append(msg)


# ── 通用写入 ────────────────────────────────────────────────────────────────
def write_if_diff(dst: Path, data: bytes) -> bool:
    if dst.is_file() and not dst.is_symlink() and dst.read_bytes() == data:
        return False
    if dst.is_symlink():
        dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(data)
    if dst.suffix in EXEC_SUFFIX:
        try:
            dst.chmod(0o755)
        except OSError:
            pass
    return True


def rel_of(root: Path, p: Path) -> str:
    return p.relative_to(root).as_posix()


# ── 探测 ────────────────────────────────────────────────────────────────────
def detect_mode(root: Path):
    if (root / ".aidp").is_dir():
        return "upgrade", "项目根已有 .aidp/"
    if any((root / home / runtime_layout.RUNTIME_MANIFEST).is_file()
           for home in runtime_layout.RUNTIME_HOME.values()):
        return "upgrade", "项目已有 Agent 原生运行包"
    if migrate.has_code(root):
        return "migrate", "检测到已有代码"
    return "init", "未检测到 .aidp/ 与代码"


def parse_agents(text: str) -> list:
    out = []
    for part in (text or "").split(","):
        n = AGENT_ALIASES.get(part.strip().lower(), part.strip().lower())
        if not n:
            continue
        if n not in KNOWN_AGENTS:
            raise ValueError(f"未知 Agent：{part.strip()}（可选 {', '.join(KNOWN_AGENTS)}）")
        if n not in out:
            out.append(n)
    return out


def marker_agents(root: Path) -> list:
    return [a for a in KNOWN_AGENTS if (root / MARKER_DIRS[a]).is_dir()]


def resolve_agents(root: Path, arg: str, interactive: bool):
    if any((root / home / runtime_layout.RUNTIME_MANIFEST).is_file()
           for home in runtime_layout.RUNTIME_HOME.values()):
        active = []
        if (root / runtime_layout.RUNTIME_HOME["claude"] / runtime_layout.RUNTIME_MANIFEST).is_file():
            active.append("claude")
        codex = root / ".codex/skills/aidp"
        if codex.is_dir() and any(path.is_file() for path in codex.glob("*/SKILL.md")):
            active.append("codex")
        if (root / ".dsh/commands/.aidp-generated").is_file():
            active.append("dsh")
        for agent in marker_agents(root):
            if agent not in active and not (root / MARKER_DIRS[agent] / DISABLED_AGENT_MARK).is_file():
                active.append(agent)
        if active:
            return [agent for agent in KNOWN_AGENTS if agent in active], "runtime"
    markers = marker_agents(root)
    if markers:
        return markers, "markers"
    if arg and parse_agents(arg):
        return parse_agents(arg), "argument"
    env = os.environ.get("AIDP_AGENT", "").strip()
    if env and parse_agents(env):
        return parse_agents(env), "env"
    if interactive and sys.stdin.isatty():
        ans = input("选择要装配的 AI 编码 Agent（claude / codex / dsh，可逗号分隔多选，回车 = claude）：").strip()
        if parse_agents(ans):
            return parse_agents(ans), "prompt"
    return ["claude"], "default"


def read_project_cfg(root: Path) -> dict:
    out = {}
    text = L.read_text(root / "memory/aidp-config.yaml")
    in_sec = False
    for ln in text.splitlines():
        if ln and ln[:1] not in (" ", "\t", "#"):
            in_sec = ln.strip().startswith("project:")
            continue
        m = re.match(r"^\s+(name|name_cn)\s*:\s*(.*?)\s*$", ln) if in_sec else None
        if m:
            v = m.group(2).split(" #")[0].strip().strip('"\'')
            if v and "{{" not in v:
                out[m.group(1)] = v
    return out


def guess_version(root: Path):
    for name in ("AGENTS.md", "CLAUDE.md"):
        m = re.search(r"当前版本\*\*[：:]\s*(V\d+\.\d+(?:\.\d+)?)", L.read_text(root / name))
        if m:
            return m.group(1)
    return None


def detect(root: Path) -> dict:
    mode, reason = detect_mode(root)
    env = os.environ.get("AIDP_AGENT", "").strip()
    cfg = read_project_cfg(root)
    return {
        "root": str(root),
        "mode": mode,
        "reason": reason,
        "project": cfg.get("name") or root.name,
        "project_cn": cfg.get("name_cn"),
        "user": vcs.developer_identity(root),
        "vcs_mode": vcs.detect_mode(root),
        "version_guess": guess_version(root),
        "agents": {"markers": marker_agents(root), "env": env or None,
                   "resolved_without_prompt": (marker_agents(root) or (parse_agents(env) if env else None))},
        "scaffold": {"bundle_version": L.bundle_version(), "project_version": scaffold_marker.read_version(root),
                     "pending": scaffold_marker.read_pending(root),
                     "rewrite_queue": len(L.queue_entries(root))},
        "memory_files": sorted(L.memory_bodies(root)),
        "code_units": migrate.detect_code_units(root, cfg.get("name") or root.name),
        "docs": migrate.scan_docs(root),
        "inputs": migrate.scan_inputs(root),
        "is_template_project": L.is_template_project(root),
    }


# ── 备份 ────────────────────────────────────────────────────────────────────
BACKUP_ITEMS = (".aidp", "AGENTS.md", "CLAUDE.md", "README.md", ".gitignore", "docs/init",
                "docs/architecture", "memory/aidp-config.yaml", "memory/README.md",
                ".claude/settings.json", ".codex/hooks.json", ".codex/config.toml", ".dsh/hooks.json")


class Backup:
    """升级备份：`overwrite` / 首次接入时整体快照；其余情况在覆盖某个已有文件前按需逐文件备份。"""

    def __init__(self, root: Path, rep: Report):
        self.root, self.rep, self.dir = root, rep, None

    def _ensure_dir(self):
        if self.dir is None:
            self.dir = self.root / f".aidp-backup-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            self.dir.mkdir(parents=True)
        return self.dir

    def full(self, keep_last: int, keep_days: int):
        pr = L.prune_backups(self.root, keep_last, keep_days)
        for name in pr["removed"]:
            self.rep.act("prune", name, "超出备份保留策略")
        root = self.root
        items = [r for r in BACKUP_ITEMS if (root / r).exists()]
        items += [rel_of(root, p) for p in sorted((root / "docs").rglob("README.md"))] if (root / "docs").is_dir() else []
        items += [rel_of(root, p) for p in sorted((root / "memory").glob("*.md"))] if (root / "memory").is_dir() else []
        if not items:
            return None
        dst = self._ensure_dir()
        for rel in items:
            src = root / rel
            if src.is_dir():
                shutil.copytree(src, dst / rel, dirs_exist_ok=True, symlinks=True,
                                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.is_file():
                (dst / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst / rel)
        self.rep.act("backup", dst.name, f"{len(items)} 项")
        return dst

    def save(self, rel: str):
        """覆盖 `rel` 之前调用：文件存在且本轮尚未备份过 → 复制进备份目录。"""
        src = self.root / rel
        if not src.is_file() or src.is_symlink():
            return
        first = self.dir is None
        dst = self._ensure_dir() / rel
        if dst.exists():
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        if first:
            self.rep.act("backup", self.dir.name, "覆盖前逐文件备份")

    def save_tree(self, rel: str):
        """删除目录前备份整棵子树；失败由调用方决定是否保留源目录。"""
        src = self.root / rel
        if not src.is_dir() or src.is_symlink():
            return None
        first = self.dir is None
        dst = self._ensure_dir() / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(src, dst, symlinks=True)
        if first:
            self.rep.act("backup", self.dir.name, "删除前目录备份")
        return dst


class LegacyChangedDuringMigration(RuntimeError):
    """Keep post-backup user changes in the legacy tree during rollback."""


MIGRATION_FAILURE_LEDGER = ".aidp-migration-failure.json"
MIGRATION_FAILURE_SCHEMA = "aidp.migration-failure/v1"


def _legacy_backup_files(root: Path, legacy: Path, saved: Path, rep: Report) -> list:
    """Report each backed-up file; classify only against an available old manifest."""
    baseline = installed_manifest(root)
    if not isinstance(baseline, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            or not re.fullmatch(r"[0-9a-f]{64}", value)
            for key, value in baseline.items()):
        baseline = None
    entries = []
    for path in sorted(legacy.rglob("*")):
        if path.is_dir() and not path.is_symlink():
            continue
        rel = path.relative_to(legacy).as_posix()
        if baseline is None:
            classification = "unclassified"
        elif rel.split("/", 1)[0] not in L.GATED_DIRS:
            classification = "unclassified"
        elif rel not in baseline:
            classification = "added"
        elif path.is_symlink() or L.sha256(path.read_bytes()) != baseline[rel]:
            classification = "modified"
        else:
            continue
        entry = {"source": rel,
                 "backup": (saved / rel).relative_to(root).as_posix(),
                 "classification": classification}
        entries.append(entry)
        rep.note(f"旧运行目录备份（{classification}）：{rel} → {entry['backup']}")
    return entries


def _complete_tree_state(directory: Path) -> dict:
    """Compare a legacy backup without following links or omitting user files."""
    state = {}
    for path in (directory, *directory.rglob("*")):
        info = path.lstat()
        rel = path.relative_to(directory).as_posix()
        mode = stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            value = ("link", mode, os.readlink(path))
        elif stat.S_ISDIR(info.st_mode):
            value = ("directory", mode)
        elif stat.S_ISREG(info.st_mode):
            value = ("file", mode, L.sha256(path.read_bytes()))
        else:
            raise RuntimeError(f"旧运行目录包含无法安全备份的文件类型：{path}")
        state[rel] = value
    return state


def _legacy_state_digest(directory: Path) -> str:
    state = _complete_tree_state(directory)
    return L.sha256(json.dumps(state, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":")).encode("utf-8"))


def migration_failure_evidence(root: Path):
    """Accept a failed migration only while its complete backup matches the old tree."""
    path = root / MIGRATION_FAILURE_LEDGER
    if path.is_symlink() or not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("schema") != MIGRATION_FAILURE_SCHEMA \
                or record.get("status") != "failed" or record.get("legacy_path") != ".aidp" \
                or record.get("version") != L.bundle_version() \
                or record.get("project_version") != scaffold_marker.read_version(root) \
                or not isinstance(record.get("failure_stage"), str) \
                or not record["failure_stage"] or not isinstance(record.get("at"), str):
            return None
        backup_rel = record.get("backup_path")
        if not isinstance(backup_rel, str):
            return None
        parts = Path(backup_rel).parts
        if len(parts) != 2 or not re.fullmatch(r"\.aidp-backup-\d{20}", parts[0]) \
                or parts[1] != ".aidp":
            return None
        backup = root.joinpath(*parts)
        legacy = root / ".aidp"
        if backup.parent.is_symlink() or backup.is_symlink() \
                or not backup.is_dir() or legacy.is_symlink() or not legacy.is_dir():
            return None
        digest = _legacy_state_digest(legacy)
        if digest != record.get("legacy_digest") \
                or digest != record.get("backup_digest") \
                or _legacy_state_digest(backup) != digest:
            return None
        return record
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return None


def _write_migration_failure(root: Path, evidence: dict, stage: str, exc: Exception):
    record = {"schema": MIGRATION_FAILURE_SCHEMA, "status": "failed",
              "legacy_path": ".aidp", "version": L.bundle_version(),
              "project_version": scaffold_marker.read_version(root),
              "backup_path": evidence["backup_path"],
              "legacy_digest": evidence["legacy_digest"],
              "backup_digest": evidence["backup_digest"],
              "failure_stage": stage, "at": datetime.now().astimezone().isoformat(),
              "reason": str(exc)[:300]}
    fd, temporary = tempfile.mkstemp(prefix=".aidp-migration-failure-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            json.dump(record, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        os.replace(temporary, root / MIGRATION_FAILURE_LEDGER)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


# ── 契约 ────────────────────────────────────────────────────────────────────
def gate_decision(proj_raw, scaffold_raw, pending, queue_nonempty, force) -> str:
    pv, sv = L.parse_ver(proj_raw), L.parse_ver(scaffold_raw)
    if force or pv is None or sv is None or pv < sv:
        return "overwrite"
    if pv == sv:
        return "overwrite" if (pending or queue_nonempty) else "fill"
    return "protect"


def snapshot_optional_rules(root: Path, homes) -> dict:
    """装运行包**之前**先留一份：可选规则的「上一版模板」与「已安装副本」字节。

    ⛔ 必须在安装前取：`templates/` 是受管契约，安装后模板位已是**新版**，
    再比就分不出「用户改过」和「版本升级」了。
    """
    snapshot = {}
    for home in homes:
        for tpl_rel, inst_rel in L.OPTIONAL_RULES:
            tpl, inst = root / home / tpl_rel, root / home / inst_rel
            if not inst.is_file():
                continue
            snapshot[(home, tpl_rel, inst_rel)] = (
                tpl.read_bytes() if tpl.is_file() else None, inst.read_bytes())
    return snapshot


def refresh_optional_rules(root: Path, homes, snapshot: dict, rep: Report):
    """已安装的可选规则随模板位刷新；安装副本被本地改过则保留并告警。

    ★ 这条通道是**必须的**：可选规则的安装位（`<运行根>/rules/webmcp.md`）不在下发面里 ——
    契约真源里没有它，运行包把它当用户文件原样带过去，两条同步路径都碰不到。
    不专门刷新，它就永久停在安装那天的版本（`rules/README.md` 与 `templates/README.md`
    都对外承诺了「随升级自动刷新」）。
    """
    for home in homes:
        for tpl_rel, inst_rel in L.OPTIONAL_RULES:
            new_tpl, inst = root / home / tpl_rel, root / home / inst_rel
            if not new_tpl.is_file() or not inst.is_file():
                continue
            old_tpl, old_inst = snapshot.get((home, tpl_rel, inst_rel), (None, None))
            new = new_tpl.read_bytes()
            if inst.read_bytes() == new:
                continue
            # 「本地改过」的判据 = 安装副本 ≠ **上一版**模板；取不到上一版时保守判为改过。
            modified = old_tpl is None or old_inst is None or old_inst != old_tpl
            if modified:
                rep.warn(f"{home}/{inst_rel} 与上一版模板位不一致（疑似本地修改），未覆盖；"
                         f"确认后跑 `python3 {home}/scripts/check_webmcp.py --install-rule --force` 重装")
                continue
            write_if_diff(inst, new)
            rep.act("update", f"{home}/{inst_rel}", "已安装的可选规则随模板升级")


def installed_manifest(root: Path):
    """项目里上一版脚手架安装的契约指纹（`<运行根>/skills/aidp-code-engineer/assets/CONTRACT_MANIFEST.json`）。

    运行中的脚手架就是项目内安装位时，它已是新版指纹，无法区分「本地改动」与「版本差异」→ 返回 None。
    """
    target = L.installed_skill_dir(root, L.MANIFEST_REL)
    if target is None or target.resolve() == L.SKILL_DIR.resolve():
        return None
    try:
        return json.loads((target / L.MANIFEST_REL).read_text(encoding="utf-8")).get("files") or {}
    except (OSError, ValueError):
        return None


LEGACY_ROUTER_REL = ".aidp/skills/aidp-cmd"
LEGACY_ROUTER_MARK = "<!-- 命令表由 .aidp/scripts/agent_sync.py 按 .aidp/commands/ 维护；改命令请改 .aidp/commands/ 后重跑该脚本 -->"
LEGACY_ROUTER_OPENAI_YAML = "policy:\n  allow_implicit_invocation: false\n"


def _legacy_frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.S)
    out = {}
    if not m:
        return out
    for line in m.group(1).splitlines():
        kv = re.match(r"^([A-Za-z_-]+)\s*:\s*(.*)$", line)
        if kv:
            out[kv.group(1)] = kv.group(2).strip().strip('"').strip("'")
    return out


def _legacy_title_description(text: str) -> str:
    m = re.search(r"^#\s+/?[\w-]+\s*[—-]+\s*(.+?)\s*$", text, re.M)
    if not m:
        return ""
    desc = re.sub(r"[（(]\s*★\s*[)）]|★", "", m.group(1)).strip()
    return f"AIDP 命令：{desc}"


def _legacy_router_skill(root: Path) -> str:
    commands = []
    source = root / ".aidp/commands"
    if source.is_dir():
        for command in sorted(source.glob("*.md")):
            if command.stem.upper() == "README":
                continue
            text = L.read_text(command)
            fm = _legacy_frontmatter(text)
            desc = fm.get("description") or _legacy_title_description(text) or f"AIDP 命令 /{command.stem}"
            commands.append((command.stem, desc.replace('"', "'"), fm.get("argument-hint", "")))
    with_hint = any(hint for _name, _desc, hint in commands)
    if with_hint:
        head = "| 命令 | 用途 | 参数格式 |\n|------|------|---------|\n"
        rows = "\n".join(f"| `{name}` | {desc} | {hint or '见命令文件「参数」段'} |"
                         for name, desc, hint in commands)
    else:
        head = "| 命令 | 用途 |\n|------|------|\n"
        rows = "\n".join(f"| `{name}` | {desc} |" for name, desc, _hint in commands)
    names = " / ".join(name for name, _desc, _hint in commands)
    return (
        "---\n"
        "name: aidp-cmd\n"
        f'description: "AIDP 命令统一入口：aidp-cmd <命令> [参数]。可用命令：{names}"\n'
        "disable-model-invocation: true\n"
        "user-invocable: true\n"
        "---\n"
        f"{LEGACY_ROUTER_MARK}\n\n"
        "# aidp-cmd — AIDP 命令入口\n\n"
        "本 SKILL 是本项目全部 AIDP 命令的统一入口，**仅由用户显式调用**。\n\n"
        "## 调用方式\n\n"
        "    aidp-cmd <命令> [参数…]\n\n"
        "## 参数解析规则（确定性，⛔ 不做任何推断）\n\n"
        "1. 调用文字去掉开头的 `aidp-cmd`（连同 `$` / `/` 前缀）后，**第一个词 = 命令名**。\n"
        "2. 命令名之后的**全部文字原样**作为该命令的参数 `$ARGUMENTS`：不增删、不改写、不调整顺序与引号；"
        "没有其余文字时 `$ARGUMENTS` 为空串。\n"
        "3. 命令文件里出现的 `$ARGUMENTS`、`${ARGUMENTS}`、`${ARGUMENTS:-}` 一律**按文本替换**为第 2 步得到的参数原文；"
        "⛔ 不从环境变量、上下文或历史对话里另找参数。\n\n"
        "示例：`aidp-cmd sprint-autopilot --unattended --no-loop` → 命令名 `sprint-autopilot`，"
        "`$ARGUMENTS` = `--unattended --no-loop`。\n\n"
        "## 执行步骤\n\n"
        "1. 按上面的规则取命令名与 `$ARGUMENTS`。\n"
        "2. 命令名不在下表中，或调用时没给命令名 → 把下表列给用户、请其选择，⛔ 不要猜。\n"
        "3. 完整读取 `.aidp/commands/<命令名>.md`，代入 `$ARGUMENTS` 后按其内容逐步执行（该文件是命令的唯一权威，"
        "参数格式见其开头的「参数」段）。\n"
        "4. 文中出现的 Claude Code 专有工具名，按 `.aidp/reference/agent-tools.md` 换成当前 Agent 的等价能力。\n\n"
        "## 可用命令\n\n"
        f"{head}{rows}\n"
    )


def _legacy_router_is_generated(root: Path, router: Path) -> bool:
    expected = {"SKILL.md", "agents", "agents/openai.yaml"}
    try:
        entries = {p.relative_to(router).as_posix() for p in router.rglob("*")}
    except OSError:
        return False
    if entries != expected:
        return False
    agents = router / "agents"
    skill = router / "SKILL.md"
    policy = agents / "openai.yaml"
    if (router.is_symlink() or agents.is_symlink() or skill.is_symlink() or policy.is_symlink()
            or not agents.is_dir() or not skill.is_file() or not policy.is_file()):
        return False
    return (L.read_text(skill) == _legacy_router_skill(root)
            and L.read_text(policy) == LEGACY_ROUTER_OPENAI_YAML)


def cleanup_obsolete_router(root: Path, mode: str, bk: "Backup", rep: Report):
    if mode not in ("migrate", "upgrade"):
        return
    router = root / LEGACY_ROUTER_REL
    if not router.is_dir() or router.is_symlink():
        return
    if not _legacy_router_is_generated(root, router):
        try:
            saved = bk.save_tree(LEGACY_ROUTER_REL)
        except OSError as exc:
            rep.warn(f"旧命令路由备份失败，已保留原目录：{exc}")
            return
        if saved is None:
            rep.warn("旧命令路由无法备份，已保留原目录")
            return
        rep.warn(f"旧命令路由已备份：{saved.relative_to(root).as_posix()}")
    shutil.rmtree(router)
    rep.act("remove", LEGACY_ROUTER_REL + "/", "原生命令适配不再使用统一路由")



# ── docs / memory / 根文件 ─────────────────────────────────────────────────
def _prev_delivered(root: Path, bundle_rel: str):
    """上一版脚手架安装进项目的同名下发件字节（运行中的脚手架即安装位时无从比较 → None）。"""
    target = L.installed_skill_dir(root, bundle_rel)
    if target is None or target.resolve() == L.SKILL_DIR.resolve():
        return None
    p = target / bundle_rel
    return p.read_bytes() if p.is_file() else None


def render_home_bytes(data: bytes, home: str) -> bytes:
    """把下发文本里的 `{{AIDP_HOME}}` 渲染成本次装配的运行根。

    ⛔ 下发文档**不能**写死 `.aidp/`：那是模板仓库的维护源，下游项目根**没有**这个目录，
    于是 `docs/**/README.md`、`memory/README.md`、`memory/aidp-config.yaml` 里那批
    「见 `.aidp/agents/version-auditor.md`」「跑 `python3 .aidp/scripts/commit_gate.py`」
    在下游**全是死链 / 跑不起来的命令**。此前只有 `docs/init/*.md` 走渲染，其余三类漏了。
    """
    try:
        return data.decode("utf-8").replace("{{AIDP_HOME}}", home).encode("utf-8")
    except UnicodeDecodeError:
        return data


def sync_delivered_file(root: Path, rel: str, sp: Path, bundle_rel: str, bk: "Backup", rep: Report,
                        home: str = None):
    """项目会改写的下发文件（docs 结构性 README、memory/README.md）：未改过才刷新，改过的进语义改写队列。"""
    dp, data = root / rel, sp.read_bytes()
    prev = _prev_delivered(root, bundle_rel)
    if home:
        # ⛔ 两侧必须同口径渲染：只渲染新件、不渲染上一版下发件，会让「项目没改过」被误判成「改过了」，
        #    刷新退化成入队，用户每次升级都收到一堆本该自动完成的语义改写待办。
        data = render_home_bytes(data, home)
        if prev is not None:
            prev = render_home_bytes(prev, home)
    verdict = L.decide_user_fillable(root, rel, dp.read_bytes(), data, prev)
    if verdict == "uptodate":
        if dp.read_bytes() == data:
            L.uf_record(root, rel, data)
    elif verdict == "refresh":
        bk.save(rel)
        write_if_diff(dp, data)
        L.uf_record(root, rel, data)
        rep.act("update", rel)
    elif L.enqueue(root, rel, sp):
        rep.act("queue", rel, "项目改过的下发文件，待语义合并新版")


def sync_docs(root: Path, was_aidp: bool, rep: Report, bk: "Backup", agents: list):
    base = L.ASSETS / "docs"
    home = runtime_home_for(agents)
    for rel, sp in L.iter_files(base):
        dp = root / "docs" / rel
        data = sp.read_bytes()
        if rel.endswith(".md"):
            # ⛔ 不能只渲染 `init/`：`docs/**/README.md` 同样逐字下发给下游，
            #    写死的运行契约路径在那边一律断链（见 render_home_bytes）。
            data = render_home_bytes(data, home)
        if rel.startswith("architecture/") and rel.count("/") == 1 and not rel.endswith("README.md"):
            if not dp.exists():
                write_if_diff(dp, data)
                rep.act("create", f"docs/{rel}")
            continue
        if not dp.exists():
            write_if_diff(dp, data)
            if not rel.startswith("init/"):
                L.uf_record(root, f"docs/{rel}", data)
            rep.act("create", f"docs/{rel}")
        elif rel.startswith("init/"):
            if dp.read_bytes() != data:
                bk.save(f"docs/{rel}")
                write_if_diff(dp, data)
                rep.act("update", f"docs/{rel}")
        elif was_aidp:
            sync_delivered_file(root, f"docs/{rel}", sp, f"assets/docs/{rel}", bk, rep,
                                home=home if rel.endswith(".md") else None)
        elif dp.read_bytes() != data:
            rep.note(f"docs/{rel} 已存在且非 AIDP 版本，保留原文；AIDP 版见 {rel_of(L.SKILL_DIR.parent, sp)}")


def _yaml_top_blocks(text: str) -> dict:
    blocks, cur, buf = {}, None, []
    pending_comments = []
    for ln in text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):", ln)
        if m:
            if cur:
                blocks[cur] = "\n".join(buf).rstrip() + "\n"
            cur, buf = m.group(1), pending_comments + [ln]
            pending_comments = []
        elif cur and (ln.startswith((" ", "\t")) or not ln.strip()):
            buf.append(ln)
        elif ln.startswith("#"):
            if cur and buf and not buf[-1].strip():
                blocks[cur] = "\n".join(buf).rstrip() + "\n"
                cur, buf = None, []
            if cur:
                buf.append(ln)
            else:
                pending_comments.append(ln)
    if cur:
        blocks[cur] = "\n".join(buf).rstrip() + "\n"
    return blocks


_TOP_KEY_RE = re.compile(r"^([A-Za-z_][\w-]*):")
_SUB_KEY_RE = re.compile(r"^  ([A-Za-z_][\w-]*):")


def _yaml_sub_entries(block: str) -> "dict[str, list[str]]":
    """顶层段内**恰好两格缩进**的直接子键 → 该子键的完整行片段（含其前置注释）。

    只认两格缩进；更深的缩进、列表项、续行都并进它所属的子键。
    """
    entries: "dict[str, list[str]]" = {}
    cur, buf, pending = None, [], []
    for line in block.splitlines()[1:]:          # 跳过顶层 `key:` 那一行
        matched = _SUB_KEY_RE.match(line)
        if matched:
            if cur is not None:
                entries[cur] = buf
            cur, buf, pending = matched.group(1), pending + [line], []
        elif cur is None:
            if line.strip().startswith("#"):
                pending.append(line)
        elif line.strip().startswith("#") or not line.strip():
            pending.append(line)               # 归属未定：可能是下一个子键的前置注释
        else:
            buf.extend(pending)
            pending = []
            buf.append(line)
    if cur is not None:
        entries[cur] = buf
    return entries


def _fill_missing_sub_keys(have: str, tpl: str) -> "tuple[str, list[str]]":
    """把模板里新增的**二级配置键**补进项目已有的同名顶层段，已有键一字不动。

    ⛔ 只补不改：新版本在 `notify:` / `cicd:` / `commit_gate:` 这类**已存在**的段里加子键时，
    原先只比顶层 key 的做法会让下游永远收不到——新功能读到 `None` 静默失效，且无任何告警。
    风格不一致（项目段里一个两格子键都认不出、却又非空）时**整段跳过**，⛔ 宁可不补也不
    往里塞一份缩进对不上的 YAML。
    """
    tpl_blocks = _yaml_top_blocks(tpl)
    lines = have.splitlines()
    # 顶层段的起止行号（右开区间），尾部空行不算在段内。
    bounds, current, start = {}, None, 0
    for index, line in enumerate(lines):
        matched = _TOP_KEY_RE.match(line)
        if matched:
            if current is not None:
                bounds[current] = (start, index)
            current, start = matched.group(1), index
    if current is not None:
        bounds[current] = (start, len(lines))

    additions, filled = {}, []
    for key, (begin, end) in bounds.items():
        tpl_block = tpl_blocks.get(key)
        if tpl_block is None:
            continue
        tpl_entries = _yaml_sub_entries(tpl_block)
        if not tpl_entries:
            continue
        block_lines = lines[begin:end]
        have_names = {m.group(1) for m in
                      (_SUB_KEY_RE.match(line) for line in block_lines[1:]) if m}
        body = [line for line in block_lines[1:] if line.strip()]
        if body and not have_names:
            continue                            # 缩进风格对不上，不碰
        missing = [name for name in tpl_entries if name not in have_names]
        if not missing:
            continue
        chunk = []
        for name in missing:
            chunk.extend(tpl_entries[name])
            filled.append(f"{key}.{name}")
        tail = end
        while tail > begin and not lines[tail - 1].strip():
            tail -= 1
        additions[tail] = chunk

    if not additions:
        return have, []
    out = []
    for index, line in enumerate(lines):
        if index in additions:
            out.extend(additions.pop(index))
        out.append(line)
    for chunk in additions.values():            # 插入点落在文件末尾
        out.extend(chunk)
    return "\n".join(out).rstrip("\n") + "\n", filled


def sync_config(root: Path, ctx: dict, rep: Report, bk: "Backup", agents=("claude",)):
    tpl = L.render((L.SKILL_DIR / L.CONFIG_TPL_REL).read_text(encoding="utf-8"), ctx)
    tpl = tpl.replace("{{AIDP_HOME}}", runtime_home_for(agents))
    dst = root / "memory/aidp-config.yaml"
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        L.write_text_lf(dst, tpl)
        rep.act("create", "memory/aidp-config.yaml")
        return
    have = dst.read_text(encoding="utf-8")
    present = set(re.findall(r"^([A-Za-z_][\w-]*):", have, re.M))
    missing = [(k, v) for k, v in _yaml_top_blocks(tpl).items() if k not in present]
    if missing:
        have = have.rstrip("\n") + "\n\n" + "\n".join(v for _, v in missing)
    have, filled = _fill_missing_sub_keys(have, tpl)
    if not missing and not filled:
        return
    bk.save("memory/aidp-config.yaml")
    L.write_text_lf(dst, have)
    detail = []
    if missing:
        detail.append("补齐配置段：" + "、".join(k for k, _ in missing))
    if filled:
        detail.append("补齐配置键：" + "、".join(filled))
    rep.act("update", "memory/aidp-config.yaml", "；".join(detail))


def sync_memory(root: Path, ctx: dict, was_aidp: bool, rep: Report, bk: "Backup",
                agents=("claude",)):
    src = L.ASSETS / "memory"
    for tpl, rel in L.MEMORY_TEMPLATES:
        dst = root / rel
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            L.write_text_lf(dst, L.render((src / tpl).read_text(encoding="utf-8"), ctx))
            rep.act("create", rel)
            continue
        cur = L.read_text(dst)
        rendered = L.render(cur, ctx)          # 只替换残留的占位符本身，已填写的段落原样保留
        if rendered != cur:
            bk.save(rel)
            L.write_text_lf(dst, rendered)
            rep.act("render", rel, "替换残留占位符")
    readme_src, readme = src / "README.md", root / "memory/README.md"
    home = runtime_home_for(agents)
    data = render_home_bytes(readme_src.read_bytes(), home)
    if not readme.exists():
        write_if_diff(readme, data)
        L.uf_record(root, "memory/README.md", data)
        rep.act("create", "memory/README.md")
    elif was_aidp:
        sync_delivered_file(root, "memory/README.md", readme_src, "assets/memory/README.md",
                            bk, rep, home=home)
    elif readme.read_bytes() != data:
        rep.note("memory/README.md 已存在且非 AIDP 版本，保留原文")


def sync_root_files(root: Path, ctx: dict, agents, rep: Report, bk: "Backup"):
    readme = root / "README.md"
    home = runtime_home_for(agents)
    if not readme.exists():
        body = L.render((L.ASSETS / "root/README.md.tpl").read_text(encoding="utf-8"), ctx)
        L.write_text_lf(readme, body.replace("{{AIDP_HOME}}", home))
        rep.act("create", "README.md")
    else:
        try:
            original = readme.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            rep.warn("README.md 不是 UTF-8，保留原文件，跳过运行路径归一")
        else:
            refreshed = original
            # ⛔ 顺序必须「长在前」：`.claude/aidp` 要先于 `.claude` 匹配，否则前缀先被换掉、
            #    留下 `/aidp` 尾巴。历史两种嵌套形态与当前两种平铺形态都要能归一。
            for old_home in (".claude/aidp", ".agents/aidp", ".aidp",
                             *sorted(runtime_layout.RUNTIME_HOME.values())):
                if old_home != home:
                    refreshed = refreshed.replace(
                        f"python3 {old_home}/scripts/aidp_scheduler.py",
                        f"python3 {home}/scripts/aidp_scheduler.py")
                    refreshed = refreshed.replace(f"├── {old_home}/", f"├── {home}/")
            if refreshed != original:
                bk.save("README.md")
                L.write_text_lf(readme, refreshed)
                rep.act("update", "README.md", "仅归一调度命令与运行目录示例")
    env = root / "env/.env"
    if not env.exists():
        env.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(L.ASSETS / "root/env.tpl", env)
        rep.act("create", "env/.env")
    gi = root / ".gitignore"
    have = gi.read_text(encoding="utf-8") if gi.exists() else None
    want = L.merge_gitignore(have, (L.ASSETS / "root/gitignore.tpl").read_text(encoding="utf-8"))
    if have != want:
        bk.save(".gitignore")
        L.write_text_lf(gi, want)
        rep.act("create" if have is None else "update", ".gitignore", "AIDP 托管区")


def sync_memory_file(root: Path, agents, ctx: dict, decision: str, was_aidp: bool, rep: Report, bk: "Backup"):
    tpl_path = L.SKILL_DIR / L.MEMORY_TPL_REL
    rendered = L.render(tpl_path.read_text(encoding="utf-8"), ctx)
    home = runtime_home_for(agents)
    rendered = rendered.replace("{{AIDP_HOME}}", home)
    bodies = L.memory_bodies(root)
    target = L.memory_target(root, agents)
    if not bodies:
        L.write_text_lf(root / target, rendered)
        rep.act("create", target, "项目记忆文件")
        return
    body_file = target if target in bodies else next(iter(bodies))
    is_aidp = L.looks_like_aidp_body(bodies[body_file])
    if is_aidp:
        # 已是 AIDP 形态：按锚点确定性合并——新模板正文 +「当前状态」字段值 +「项目自定义」段原文
        if was_aidp and decision != "overwrite":
            return
        merged = L.merge_memory_upgrade(bodies[body_file], rendered)
        if merged != bodies[body_file]:
            bk.save(body_file)
            L.write_text_lf(root / body_file, merged)
            rep.act("merge", body_file, "按新版模板合并，保留「当前状态」字段值与「项目自定义」段")
        return
    bk.save(target)
    L.write_text_lf(root / target, migrate.merge_custom(rendered, bodies))
    rep.act("merge", target, "原记忆文件内容并入「项目自定义」段：" + "、".join(sorted(bodies)))
    L.enqueue(root, target, tpl_path)
    rep.act("queue", target, "复核「项目自定义」段：去重、与 AIDP 约定冲突项交用户裁决")
    if "claude" not in agents and "CLAUDE.md" in bodies and target != "CLAUDE.md":
        rep.note("CLAUDE.md 原文已并入 AGENTS.md；当前未装配 Claude Code，CLAUDE.md 保留原样")


# ── 导航 README / .gitkeep ─────────────────────────────────────────────────
def _nav_body(directory: Path, policy) -> str:
    children = sorted(p.name for p in directory.iterdir() if p.is_dir() and not p.name.startswith("."))
    lines = [f"# {directory.name}", "", "本目录是导航枢纽，下列子目录各自承载一类内容。", "", "## 子目录", ""]
    for c in children:
        if c in NAV_PURPOSES:
            purpose = NAV_PURPOSES[c]
        elif L.VERSION_RE.match(c):
            purpose = f"{c} 版本的产出"
        elif directory.parent.name == "memory" or directory.parent.parent.name in ("implementation",):
            purpose = f"开发者 {c} 的个人记录"
        else:
            purpose = "用途待补充"
        lines.append(f"- `{c}/` — {purpose}")
    return "\n".join(lines) + "\n"


def ensure_nav_readmes(root: Path, rep: Report):
    try:
        policy = L.load_project_module("readme_policy")
    except ImportError as e:
        rep.warn(f"导航 README 跳过：{e}")
        return
    for top in ("docs", "memory"):
        base = root / top
        if not base.is_dir():
            continue
        for d in [base] + sorted(p for p in base.rglob("*") if p.is_dir()):
            if any(x.startswith(".") for x in d.relative_to(root).parts):
                continue
            if (d / "README.md").exists():
                continue
            decision = policy.is_readme_required_directory(d, None, root=root)
            if decision.get("required") and decision.get("reason") == "navigation-hub":
                L.write_text_lf(d / "README.md", _nav_body(d, policy))
                rep.act("create", f"{rel_of(root, d)}/README.md", "导航 README")


def manage_gitkeep(root: Path, dirs, rep: Report):
    for rel in dirs:
        d = root / rel
        if d.is_dir() and not any(d.iterdir()):
            (d / ".gitkeep").touch()
    for rel in dirs:
        d = root / rel
        while d != root and d.is_dir():
            gk = d / ".gitkeep"
            if gk.exists() and any(p.name != ".gitkeep" for p in d.iterdir()):
                gk.unlink()
            d = d.parent


# ── Agent 依赖与 agent_sync ─────────────────────────────────────────────────
def _bounded_detail(value) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) > DSH_PLUGIN_DETAIL_LIMIT:
        return text[:DSH_PLUGIN_DETAIL_LIMIT - 1].rstrip() + "…"
    return text


def _dsh_run(command, timeout: int):
    """跑一条 dsh 子命令。返回 (returncode, stdout, stderr, failure)；failure 非空表示进程没跑起来。"""
    try:
        p = subprocess.run(list(command), capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=timeout,
                           env=L.child_env(), **L.TEXT_IO)
    except subprocess.TimeoutExpired as exc:
        return None, "", _bounded_detail(exc.stderr or exc.stdout), f"超时 {timeout} 秒"
    except OSError as exc:
        return None, "", _bounded_detail(exc), f"{type(exc).__name__}：{_bounded_detail(exc)}"
    return p.returncode, p.stdout or "", p.stderr or "", ""


def _dsh_normalize_name(token: str) -> str:
    """把一个清单 token 归一成扩展名：剥引号 → 取最后一段路径/命名空间 → 去掉 `@版本`。"""
    token = str(token).strip().strip("\"'`,;|()[]{}")
    token = token.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return token.split("@", 1)[0].strip().lower()


def _dsh_names_from_json(text: str):
    """从 `list --json` 输出里收集扩展名；不是合法 JSON 返回 None（交给文本回落）。"""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    names, stack = set(), [data]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, str) and key.lower() in {"name", "id", "package", "plugin",
                                                              "source", "spec", "ref"}:
                    names.add(_dsh_normalize_name(value))
                else:
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, str):
            names.add(_dsh_normalize_name(node))
    return {n for n in names if n}


def _dsh_names_from_text(text: str) -> set:
    """容错解析人读清单：逐行逐 token 归一后收集，⛔ 不写依赖固定列宽/表头的脆正则。"""
    names = set()
    for raw in text.splitlines():
        line = raw.strip()
        if not line or set(line) <= set("-=+*_ |"):
            continue
        for token in re.split(r"[\s,;|]+", line):
            name = _dsh_normalize_name(token)
            if name:
                names.add(name)
    return names


def _dsh_installed_plugins():
    """profile=web 已装扩展名集合；返回 (names, detail)，names 为 None = 状态无从判断。"""
    # ① 优先机器可读：CLI 不支持 `--json` 时它会非零退出或吐非 JSON，两种都安静回落到 ② 文本清单
    code, out, _err, _failure = _dsh_run(DSH_PLUGIN_LIST_JSON, DSH_PLUGIN_PROBE_TIMEOUT)
    if code == 0 and out.strip():
        names = _dsh_names_from_json(out)
        if names is not None:
            return names, "list --json"
    code, out, err, failure = _dsh_run(DSH_PLUGIN_LIST, DSH_PLUGIN_PROBE_TIMEOUT)
    if failure:
        return None, failure
    if code != 0:
        return None, f"exit {code}：{_bounded_detail(err or out)}"
    return _dsh_names_from_text(out), "list"


def _dsh_cli_diagnostics(exception_kind: str = "") -> str:
    """CLI 探测诊断串。

    脱敏口径：只报 `platform`、PATH **条目数**与 `which(dsh)` 是否命中，
    ⛔ 绝不外显 PATH 原文或解析出的绝对路径（其中常含用户名与私有目录）；
    子进程输出一律先过 `_bounded_detail` 压成单行并截断到 300 字符。
    """
    entries = [x for x in os.environ.get("PATH", "").split(os.pathsep) if x.strip()]
    found = shutil.which("dsh")
    parts = [f"platform={sys.platform}",
             f"PATH 条目 {len(entries)} 个（已脱敏，不外显具体路径）",
             f"which(dsh)={'命中' if found else '未命中'}"]
    if exception_kind:
        parts.append(f"异常={exception_kind}")
    return "；".join(parts)


def install_dsh_command_plugin(mode: str, agents, rep: Report):
    """DSH 的 commands 与嵌套 SKILL 扩展：**先探测状态，再决定是否安装**。

    ⛔ 铁律：「本进程调不起 dsh」≠「扩展没装」。Windows 上 `dsh` 往往是 PowerShell 上的
    shim，Python 子进程一句 OSError [WinError 2] 就找不到它，而同一台机器 `dsh plugin
    --profile web list` 里明明有 `dsh-agent-extension@0.1.4`。所以状态机只允许这些取值：

      already-installed  profile=web 已有目标扩展 → 不执行 add，走 INFO 不是 WARN
      installed          本次 add 成功且**复查清单命中**
      not-installed      add 返回 0，但复查清单里仍没有目标扩展（不得当成可用）
      cli-unavailable    PATH 里找不到 dsh 可执行文件 → 安装状态**未验证**
      unknown            dsh 在，但版本/清单探测失败 → 安装状态**无从判断**
      install-failed     add 非零退出 / 超时 / 起不来

    诊断信息的脱敏口径见 `_dsh_cli_diagnostics`。
    """
    if "dsh" not in agents:
        return None
    if not shutil.which("dsh"):
        rep.warn(f"当前子进程无法定位 dsh 可执行文件，插件实际安装状态**未验证**（未验证 ⛔ 不等于扩展缺失）："
                 f"{_dsh_cli_diagnostics()}。若 dsh 在你的终端里可用，请自行确认："
                 f"{' '.join(DSH_PLUGIN_LIST)}；需要时手工执行：{DSH_COMMAND_PLUGIN_RETRY}")
        return "cli-unavailable"
    code, out, err, failure = _dsh_run(DSH_PLUGIN_VERSION, DSH_PLUGIN_PROBE_TIMEOUT)
    if code != 0:
        reason = failure or f"exit {code}：{_bounded_detail(err or out)}"
        rep.warn(f"已定位 dsh，但 `{' '.join(DSH_PLUGIN_VERSION)}` 未成功（{reason}）；"
                 f"插件实际安装状态无从判断：{_dsh_cli_diagnostics()}；"
                 f"请手工复核：{' '.join(DSH_PLUGIN_LIST)}")
        return "unknown"
    version = _bounded_detail(out or err)
    installed, detail = _dsh_installed_plugins()
    if installed is None:
        rep.warn(f"dsh {version} 可用，但读不出 profile=web 扩展清单（{detail}），"
                 f"插件实际安装状态无从判断；请手工复核：{' '.join(DSH_PLUGIN_LIST)}")
        return "unknown"
    if DSH_PLUGIN_NAME in installed:
        rep.note(f"DSH 扩展 {DSH_PLUGIN_NAME} 已在 profile=web（dsh {version}），本次不执行 add")
        return "already-installed"
    code, out, err, failure = _dsh_run(DSH_COMMAND_PLUGIN, DSH_COMMAND_PLUGIN_TIMEOUT)
    if code != 0:
        reason = failure or f"exit {code}"
        extra = _bounded_detail(err or out)
        rep.warn(f"DSH 命令插件安装失败（{reason}）" + (f"：{extra}" if extra else "")
                 + f"；请手工重试：{DSH_COMMAND_PLUGIN_RETRY}")
        return "install-failed"
    confirmed, detail = _dsh_installed_plugins()
    if confirmed is None:
        rep.warn(f"DSH 命令插件 add 已返回 0，但复查清单失败（{detail}），无法确认是否真的装上；"
                 f"请手工复核：{' '.join(DSH_PLUGIN_LIST)}")
        return "unknown"
    if DSH_PLUGIN_NAME not in confirmed:
        rep.warn(f"DSH 命令插件 add 返回 0，但 profile=web 清单里仍看不到 {DSH_PLUGIN_NAME}；"
                 f"⛔ 不得据此认为可用，请手工复核：{' '.join(DSH_PLUGIN_LIST)}")
        return "not-installed"
    rep.act("dsh-plugin", DSH_PLUGIN_PACKAGE, "profile=web")
    return "installed"


def run_agent_sync(root: Path, agents, mode: str, rep: Report, strict=False) -> dict:
    home = runtime_home_for(agents)
    script = root / home / "scripts/agent_sync.py"
    if not script.is_file() and not strict:
        script = root / ".aidp/scripts/agent_sync.py"
    if not script.is_file():
        message = f"缺 {home}/scripts/agent_sync.py，跳过 Agent 装配"
        if strict:
            raise RuntimeError(message)
        rep.warn(message)
        return {}
    cmd = [sys.executable, str(script), "--root", str(root), "--agents", ",".join(agents), "--mode", mode]
    p = subprocess.run(cmd, capture_output=True, text=True, env=L.child_env(), **L.TEXT_IO)
    try:
        data = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else {}
    except ValueError:
        data = {}
    if p.returncode != 0:
        message = f"agent_sync.py 失败（exit {p.returncode}）：{(p.stderr or p.stdout).strip()[:300]}"
        if strict:
            raise RuntimeError(message)
        rep.warn(message)
    else:
        rep.act("agent-sync", ",".join(agents), f"{len(data.get('actions') or [])} 项（mode={mode}）")
    return data


# ── Agent 原生运行包 ─────────────────────────────────────────────────────────
def _target_runtime_homes(agents) -> set:
    """本次装配会铺出的全部运行根（并存时两个）。"""
    homes = set()
    if "claude" in agents:
        homes.add(runtime_layout.RUNTIME_HOME["claude"])
    if {"codex", "dsh"} & set(agents):
        homes.add(runtime_layout.RUNTIME_HOME["shared"])
    return homes


def runtime_home_for(agents) -> str:
    """本次装配的运行根。单一信源 = `runtime_layout.RUNTIME_HOME`。

    ⛔ 别再就地写 `".agents/aidp" if ... else ".claude/aidp"`：此前全文散了 7 处，
    其中两处还用了另一种等价写法（`list(agents) == ["claude"]`）—— 改运行根时必漏。
    """
    key = "shared" if {"codex", "dsh"} & set(agents) else "claude"
    return runtime_layout.RUNTIME_HOME[key]


def _runtime_source() -> Path:
    return L.template_aidp() or L.BUNDLE_AIDP


def _native_namespaces(root: Path, agents: list):
    paths = []
    if "claude" in agents:
        paths.extend((".claude", ".claude/commands",
                      ".claude/skills", ".claude/plugins"))
    if "codex" in agents or "dsh" in agents:
        paths.extend((".agents", ".agents/skills"))
    if "codex" in agents:
        paths.extend((".codex", ".codex/skills", ".codex/skills/aidp"))
    if "dsh" in agents:
        paths.extend((".dsh", ".dsh/commands"))
    for rel in paths:
        current = root
        for part in Path(rel).parts:
            current /= part
            if current.is_symlink() or (current.exists() and not current.is_dir()):
                raise ValueError(f"Agent namespace 不是项目内真实目录：{current}")
    for agent in KNOWN_AGENTS:
        disabled = root / MARKER_DIRS[agent] / DISABLED_AGENT_MARK
        if os.path.lexists(disabled) and (disabled.is_symlink() or not disabled.is_file()
                                           or disabled.read_text(encoding="utf-8") != "disabled\n"):
            raise ValueError(f"Agent 禁用标记含用户内容，拒绝修改：{disabled}")
    # 历史嵌套形态（`.claude/aidp`）若还在，同样要求受管 manifest 才允许接管；
    # 新形态的运行根是 `.claude` / `.agents` 本身，它天然含别人的东西，不能按这条判。
    for rel in (".claude/aidp", ".agents/aidp"):
        target = root / rel
        if target.is_dir() and not (target / runtime_layout.RUNTIME_MANIFEST).is_file():
            raise ValueError(f"旧运行目录没有受管 manifest，拒绝接管：{target}")


def _preflight_native_entries(root: Path, agents: list, source: Path):
    targets = []
    commands = (p.stem for p in (source / "commands").glob("*.md")
                if p.stem.upper() != "README")
    for name in commands:
        if "claude" in agents:
            if f"{runtime_layout.RUNTIME_HOME['claude']}/commands" != ".claude/commands":
                targets.append(root / ".claude/commands" / f"{name}.md")
        if "codex" in agents:
            targets.append(root / ".codex/skills/aidp" / name)
        if "dsh" in agents:
            targets.append(root / ".dsh/commands" / f"{name}.md")
    # ⛔ 恒等落点不进预登记：运行根降层之后 `.claude/skills` / `.agents/skills` 既是 Agent 的
    #    发现位、又是运行包自己的 skills 目录 —— 那里的条目由 render_runtime 铺出，天然没有
    #    适配层的生成标记。把它们当"待写入的适配入口"预检，必然一律判成"已有用户内容"。
    def _adapter_rel(agent_home: str, sub: str) -> str:
        return f"{agent_home}/{sub}"

    _identity = {f"{home}/skills" for home in runtime_layout.RUNTIME_HOME.values()}
    _identity |= {f"{home}/commands" for home in runtime_layout.RUNTIME_HOME.values()}
    _identity |= {f"{home}/plugins" for home in runtime_layout.RUNTIME_HOME.values()}
    for skill in (source / "skills").iterdir():
        if not (skill / "SKILL.md").is_file() or skill.name == L.SKILL_NAME:
            continue
        if "claude" in agents and _adapter_rel(".claude", "skills") not in _identity:
            targets.append(root / ".claude/skills" / skill.name)
        if {"codex", "dsh"} & set(agents) and _adapter_rel(".agents", "skills") not in _identity:
            targets.append(root / ".agents/skills" / skill.name)
    for plugin in (source / "plugins").iterdir():
        if not plugin.is_dir():
            continue
        if "claude" in agents and ".claude/plugins" not in _identity:
            targets.append(root / ".claude/plugins" / plugin.name)
        if {"codex", "dsh"} & set(agents) and (plugin / "skills").is_dir() \
                and ".agents/skills" not in _identity:
            targets.append(root / ".agents/skills" / plugin.name)
    if "claude" in agents:
        targets.append(root / ".claude/skills" / L.SKILL_NAME)
    if {"codex", "dsh"} & set(agents):
        targets.append(root / ".agents/skills" / L.SKILL_NAME)
    for target in targets:
        if not os.path.lexists(target):
            continue
        marker = target / ".aidp-scaffold-generated"
        if target.name == L.SKILL_NAME and (marker.is_file() or _is_self_skill_target(target)):
            continue
        if target.parent.name == "commands":
            ledger = target.parent / agent_adapter.GENERATED_FILE
            if ledger.is_file():
                try:
                    records = agent_adapter._command_ledger(ledger)
                    if target.name in records:
                        agent_adapter._check_command(
                            root, target, records[target.name], source / "commands" / target.name)
                        continue
                except SystemExit as exc:
                    raise ValueError(str(exc)) from exc
        if not agent_adapter._is_generated(target, root):
            raise ValueError(f"Agent 入口已有用户内容，拒绝覆盖：{target}")


def _preflight_native_adapter(root: Path, agents: list, source: Path):
    old_source = agent_adapter.RUNTIME_ROOT
    old_expected = agent_adapter.EXPECTED_RUNTIME_REL
    try:
        agent_adapter.RUNTIME_ROOT = source
        # 预检期运行包还没铺出，探测不到；直接告知本次**全部**目标运行根。
        # ⛔ 必须是集合：Claude 与 Codex/DSH 并存时要装两个运行包，只告知其一会让
        #    另一个的目录被当成"真适配位"，预检把运行包将要铺出的条目判成用户内容拒绝覆盖。
        agent_adapter.EXPECTED_RUNTIME_REL = _target_runtime_homes(agents)
        plugins = agent_adapter._plugin_dirs(root)
        plugin_skills = agent_adapter._plugin_skill_dirs(plugins)
        public = agent_adapter._base_skill_dirs(root)
        commands = {path.stem for path in agent_adapter._command_files(root)}
        public_names = agent_adapter._declared_skill_names(public)
        plugin_names = {plugin.name for plugin in plugins if (plugin / "skills").is_dir()}
        if set(public) & plugin_names or public_names & set(plugin_skills) \
                or commands & (public_names | set(plugin_skills)):
            raise ValueError("命令、公共 SKILL 与插件名称冲突")
        servers = agent_adapter._plugin_servers(plugins)
        agent_adapter._validate_adapter_namespaces(root, plugins)
        agent_adapter._validate_targets(root, agents, plugins, plugin_skills)
        agent_adapter._validate_hooks(root, agents)
        agent_adapter._validate_claude_plugins(root, plugins if "claude" in agents else [])
        if "codex" in agents:
            agent_adapter._validate_codex_mcp(root, servers)
        if "dsh" in agents:
            agent_adapter._validate_dsh_mcp(root, servers)
    except SystemExit as exc:
        raise ValueError(str(exc)) from exc
    finally:
        agent_adapter.RUNTIME_ROOT = old_source
        agent_adapter.EXPECTED_RUNTIME_REL = old_expected


def _is_self_skill_target(target: Path) -> bool:
    """安装目标就是本次正在执行的脚手架 skill 自身。

    下游把 skill 装在项目自己的 `.agents/skills/aidp-code-engineer/`（或 `.claude/skills/…`）里跑
    init 时，「安装源」与「安装目标」是同一个目录。它按定义不是用户内容 —— 它就是本次执行的真源，
    所以不该被「无 `.aidp-scaffold-generated` 标记即拒绝覆盖」挡住。仍然要求它长得像脚手架 skill，
    免得把一个恰好同名的用户目录误判成自举源；对真正的用户目录，标记判定原样保留。
    """
    try:
        if target.resolve() != L.SKILL_DIR.resolve():
            return False
    except OSError:
        return False
    return (target / "SKILL.md").is_file() and (target / "scripts/scaffold.py").is_file()


def _skill_tree_state(directory: Path) -> dict:
    """脚手架 SKILL 目录的受管状态：⛔ 剔除 `__pycache__` / `*.pyc`。

    ★ 幂等性铁律：下游是**跑着这份已安装的 skill** 去执行 scaffold 的，import 会就地落下
    `__pycache__/`。若把它算进比较，则「同版本第二次 upgrade」永远 `existing != desired`，
    每跑一次就多备份一次整个 skill（近 10MB）、多刷一次受管副本。字节码缓存既不是用户内容、
    也不是受管契约（journal 的 `expect_tree` 早已按同一口径排除），故比较时一并忽略。
    """
    return {rel: value for rel, value in _complete_tree_state(directory).items()
            if "__pycache__" not in rel.split("/") and not rel.endswith(".pyc")}


def _install_native_skill(root: Path, agents: list, rep: Report, bk: Backup):
    _claude_home = runtime_layout.RUNTIME_HOME["claude"]
    _shared_home = runtime_layout.RUNTIME_HOME["shared"]
    for rel, home in ((".claude/skills", _claude_home) if "claude" in agents else (None, None),
                      (".agents/skills", _shared_home) if {"codex", "dsh"} & set(agents)
                      else (None, None)):
        if rel is None:
            continue
        target = root / rel / L.SKILL_NAME
        marker = target / ".aidp-scaffold-generated"
        if os.path.lexists(target) and (target.is_symlink()
                                        or not (marker.is_file() or _is_self_skill_target(target))):
            raise ValueError(f"脚手架 SKILL 目标是用户内容，拒绝覆盖：{target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".aidp-skill-stage-", dir=target.parent) as td:
            stage = Path(td) / L.SKILL_NAME
            shutil.copytree(L.SKILL_DIR, stage, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            # 不随安装下发的子树按 `SELF_INSTALL_EXCLUDE` 剔除。⛔ 别把这份清单再抄一遍进
            # `ignore_patterns`：那是按 basename 匹配的，既表达不了 `scripts/tests/` 这种路径，
            # 又会和常量各说一套——漏掉一边的后果是把模板单测/下游模板真源也装到下游去。
            for _rel in L.SELF_INSTALL_EXCLUDE:
                victim = stage / _rel.rstrip("/")
                if victim.is_dir():
                    shutil.rmtree(victim)
                elif victim.exists():
                    victim.unlink()
            skill_file = stage / "SKILL.md"
            L.write_text_lf(skill_file,
                            skill_file.read_text(encoding="utf-8").replace("{{AIDP_HOME}}", home))
            L.write_text_lf(stage / ".aidp-scaffold-generated", "aidp-code-engineer\n")
            desired = _skill_tree_state(stage)
            if any(entry[0] == "link" for entry in desired.values()):
                raise ValueError(f"脚手架 SKILL 真源包含符号链接，拒绝安装：{L.SKILL_DIR}")
            existing = _skill_tree_state(target) if target.is_dir() else None
            if existing == desired:
                continue
            previous = Path(td) / "previous"
            if existing is not None:
                saved = bk.save_tree(f"{rel}/{L.SKILL_NAME}")
                if saved is None or _skill_tree_state(saved) != existing:
                    raise RuntimeError(f"脚手架 SKILL 完整备份失败：{target}")
                os.replace(target, previous)
            try:
                os.replace(stage, target)
            except Exception:
                if previous.exists() and not os.path.lexists(target):
                    os.replace(previous, target)
                raise
            rep.act("install", f"{rel}/{L.SKILL_NAME}/", "脚手架 SKILL 受管刷新")


def _remove_transaction_path(path: Path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _preflight_native_project_paths(root: Path, version: str, user: str):
    directories = {"docs", "memory", "env", "code", "scripts"}
    directories.update(rel for rel in L.skeleton_dirs(root, version, user)
                       if rel and not rel.startswith(".aidp/"))
    directories.update((Path("docs") / rel).parent.as_posix()
                       for rel, _source in L.iter_files(L.ASSETS / "docs"))
    for rel in sorted(directories):
        current = root
        for part in Path(rel).parts:
            current /= part
            if current.is_symlink():
                raise ValueError(f"项目目录包含 symlink，拒绝写入：{current}")
            if current.exists() and not current.is_dir():
                raise ValueError(f"项目目录不是目录，拒绝写入：{current}")
    for base_name in ("docs", "memory"):
        base = root / base_name
        if base.is_dir():
            for path in base.rglob("*"):
                if path.is_symlink():
                    raise ValueError(f"项目目录包含 symlink，拒绝写入：{path}")
    files = {"README.md", "AGENTS.md", "CLAUDE.md", ".gitignore",
             L.USER_FILLABLE_BASELINE, "memory/aidp-config.yaml", "memory/README.md", "env/.env"}
    files.update(f"docs/{rel}" for rel, _source in L.iter_files(L.ASSETS / "docs"))
    files.update(rel for _tpl, rel in L.MEMORY_TEMPLATES)
    for rel in sorted(files):
        target = root / rel
        if target.is_symlink():
            raise ValueError(f"项目文件是 symlink，拒绝写入：{target}")
        if target.exists() and not target.is_file():
            raise ValueError(f"项目文件不是普通文件，拒绝写入：{target}")
        if target.is_file() and target.stat().st_nlink > 1:
            raise ValueError(f"项目文件是硬链接，拒绝写入：{target}")


class _NativeInstallJournal:
    def __init__(self, root: Path, managed: set):
        self.root, self.managed = root, managed
        self.initial = self._paths()
        self.created = set()
        self.migration_evidence = None
        self.migration_stage = "backup"

    def _paths(self):
        paths = set()
        for name in self.managed:
            base = self.root / name
            if not os.path.lexists(base):
                continue
            paths.add(Path(name))
            if base.is_dir() and not base.is_symlink():
                paths.update(path.relative_to(self.root) for path in base.rglob("*"))
        return paths

    def expect(self, path):
        target = Path(path)
        if not target.is_absolute():
            target = self.root / target
        try:
            relative = target.relative_to(self.root)
        except ValueError as exc:
            raise ValueError(f"安装动作越出项目根：{target}") from exc
        if not relative.parts or relative.parts[0] not in self.managed:
            return
        self.created.update(parent for parent in (relative, *relative.parents)
                            if parent.parts and parent not in self.initial)

    def record(self, path):
        target = Path(path)
        if not target.is_absolute():
            target = self.root / target
        if os.path.lexists(target):
            self.expect(target)

    def expect_tree(self, destination: Path, source: Path, include=None):
        """按源树推算「本次会创建哪些路径」，供失败时整体回滚。

        ⛔ 必须与写入端同一套命名：源若是脚手架 bundle，里面的 `SKILL.md` 是遮名的 `SKILL.md.in`，
        而 `runtime_layout.render_tree` 落盘时会还原成 `SKILL.md`。这里不还原就会登记一个**不存在的**
        路径、同时漏掉真正被创建的那个 —— 回滚时它留在原地，失败后的运行包**删不干净**
        （回归 `test_downstream_portability::test_failure_during_atomic_replace_rolls_back_completely`）。
        """
        self.expect(destination)
        for path in source.rglob("*"):
            relative = path.relative_to(source)
            if include is None or include(relative):
                self.expect(destination / L.bundle_unmask(relative.as_posix()))

    def rollback_created(self):
        for relative in sorted(self.created, key=lambda path: len(path.parts), reverse=True):
            path = self.root / relative
            if path.is_symlink() or path.is_file():
                path.unlink()
            elif path.is_dir():
                try:
                    path.rmdir()
                except OSError:
                    pass  # 并发加入的用户文件仍在该目录中。


def _restore_native_snapshot(original: Path, target: Path):
    if original.is_symlink() or original.is_file():
        if os.path.lexists(target):
            _remove_transaction_path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target, follow_symlinks=False)
        return
    if os.path.lexists(target) and (not target.is_dir() or target.is_symlink()):
        _remove_transaction_path(target)
    target.mkdir(parents=True, exist_ok=True)
    directories = [original] + [path for path in original.rglob("*")
                                if path.is_dir() and not path.is_symlink()]
    for directory in sorted(directories, key=lambda path: len(path.parts)):
        destination = target / directory.relative_to(original)
        if os.path.lexists(destination) and (not destination.is_dir() or destination.is_symlink()):
            _remove_transaction_path(destination)
        destination.mkdir(parents=True, exist_ok=True)
    for source in original.rglob("*"):
        if source.is_dir() and not source.is_symlink():
            continue
        destination = target / source.relative_to(original)
        if os.path.lexists(destination):
            _remove_transaction_path(destination)
        shutil.copy2(source, destination, follow_symlinks=False)
    for directory in sorted(directories, key=lambda path: len(path.parts), reverse=True):
        shutil.copystat(directory, target / directory.relative_to(original))


def _expect_agent_adapter_writes(journal: _NativeInstallJournal, root: Path, agents: list):
    home = runtime_home_for(agents)
    cmd = [sys.executable, str(root / home / "scripts/agent_sync.py"), "--root", str(root),
           "--agents", ",".join(agents), "--mode", "copy", "--check"]
    process = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                             env=L.child_env(), **L.TEXT_IO)
    try:
        planned = json.loads(process.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError(f"Agent 入口预登记失败：{process.stderr.strip()}") from exc
    if process.returncode not in (0, 1):
        raise RuntimeError(f"Agent 入口预登记失败：{planned.get('error') or process.stderr.strip()}")
    for action in planned.get("actions", []):
        if action.get("op") not in {"copy", "write"} or not action.get("path"):
            continue
        destination = root / action["path"]
        journal.expect(destination)
        if action["op"] != "copy":
            continue
        source_name = action.get("from", "")
        if source_name.startswith("AIDP_HOME/"):
            family = (runtime_layout.RUNTIME_HOME["claude"] if action["path"].startswith(".claude/")
                      else runtime_layout.RUNTIME_HOME["shared"])
            source = root / family / source_name[len("AIDP_HOME/"):]
        else:
            source = Path(source_name)
            if not source.is_absolute():
                source = root / source
        if source.is_dir() and not source.is_symlink():
            journal.expect_tree(destination, source, include=lambda path:
                                "__pycache__" not in path.parts and path.suffix != ".pyc")
            journal.expect(destination / agent_adapter.GENERATED_FILE)


def _run_native(root: Path, a, mode: str, agents: list, agent_source: str,
                migrate_legacy: bool = False) -> dict:
    _native_namespaces(root, agents)
    if migrate_legacy and os.path.lexists(root / MIGRATION_FAILURE_LEDGER) \
            and migration_failure_evidence(root) is None:
        raise ValueError(f"迁移失败台账含用户内容或证据无效，拒绝覆盖：{root / MIGRATION_FAILURE_LEDGER}")
    version = a.version or guess_version(root) or "V0.1.0"
    user = a.user or vcs.developer_identity(root)
    _preflight_native_project_paths(root, version, user)
    source = _runtime_source()
    _preflight_native_entries(root, agents, source)
    _preflight_native_adapter(root, agents, source)
    managed = {".aidp", MIGRATION_FAILURE_LEDGER, ".claude", ".agents", ".codex", ".dsh", "docs", "memory",
               "env", "README.md", "AGENTS.md", "CLAUDE.md", ".gitignore",
               L.USER_FILLABLE_BASELINE}
    managed.update(Path(rel).parts[0] for rel in L.skeleton_dirs(root, version, user)
                   if rel and not rel.startswith(".aidp/"))
    journal = _NativeInstallJournal(root, managed)
    with tempfile.TemporaryDirectory(prefix="aidp-native-rollback-", dir=root.parent) as temp:
        backup = Path(temp)
        saved = set()
        for name in managed:
            original = root / name
            if not os.path.lexists(original):
                continue
            if original.is_dir() and not original.is_symlink():
                shutil.copytree(original, backup / name, symlinks=True)
            elif original.is_symlink():
                (backup / name).symlink_to(os.readlink(original))
            else:
                shutil.copy2(original, backup / name)
            saved.add(name)
        try:
            return _run_native_impl(root, a, mode, agents, agent_source, journal,
                                    migrate_legacy=migrate_legacy)
        except BaseException as exc:
            journal.rollback_created()
            for name in saved:
                if name == LEGACY_AIDP_DIR and isinstance(exc, LegacyChangedDuringMigration):
                    continue
                _restore_native_snapshot(backup / name, root / name)
            if (migrate_legacy and journal.migration_evidence is not None
                    and not isinstance(exc, LegacyChangedDuringMigration)
                    and isinstance(exc, Exception)):
                evidence = journal.migration_evidence
                if _legacy_state_digest(root / LEGACY_AIDP_DIR) == evidence["legacy_digest"]:
                    _write_migration_failure(root, evidence, journal.migration_stage, exc)
            raise


def _run_native_impl(root: Path, a, mode: str, agents: list, agent_source: str,
                     journal: _NativeInstallJournal, migrate_legacy: bool = False) -> dict:
    rep = Report(journal)
    source = _runtime_source()
    legacy = root / ".aidp"
    if legacy.is_symlink():
        if legacy.exists():
            raise ValueError(f"旧运行目录是 symlink，拒绝跟随：{legacy}")
        legacy.unlink()
        rep.act("remove", ".aidp", "清理悬空旧链接")
    version = a.version or guess_version(root) or "V0.1.0"
    user = a.user or vcs.developer_identity(root)
    cfg = read_project_cfg(root)
    project = cfg.get("name") or root.name
    ctx = {"project": project, "project_cn": a.name_cn or cfg.get("name_cn") or project,
           "user": user, "version": version, "date": datetime.now().strftime("%Y-%m-%d")}
    scaffold_raw = L.bundle_version()
    previous = scaffold_marker.read_version(root)
    decision = gate_decision(previous, scaffold_raw, scaffold_marker.read_pending(root),
                             bool(L.queue_entries(root)), a.force)
    if decision == "protect":
        rep.warn("项目脚手架版本高于当前脚手架包，保留原运行包和 Agent 入口")
        dsh_extensions = install_dsh_command_plugin(mode, agents, rep)
        return {"mode": mode, "project": project, "version": version, "user": user,
                "vcs_mode": vcs.detect_mode(root), "dsh_extensions": dsh_extensions,
                "agents": agents, "agent_source": agent_source, "adapter_mode": "copy",
                "scaffold_version": scaffold_raw, "previous_scaffold_version": previous,
                "contract_decision": decision, "pending": False, "rewrite_queue": [],
                "orphans": [], "local_overwritten": [], "backup": None,
                "actions": rep.actions, "warnings": rep.warnings, "notes": rep.notes}
    if migrate_legacy and a.no_agent_sync:
        rep.warn("旧运行目录迁移需要先校验 Agent 原生命令入口，不能使用 --no-agent-sync")
        return {"status": "blocked", "reason": "agent-sync-disabled",
                "mode": mode, "project": project, "version": version, "user": user,
                "vcs_mode": vcs.detect_mode(root), "dsh_extensions": None,
                "agents": agents, "agent_source": agent_source, "adapter_mode": "copy",
                "scaffold_version": scaffold_raw, "previous_scaffold_version": previous,
                "contract_decision": decision, "pending": False, "rewrite_queue": [],
                "orphans": [], "local_overwritten": [], "backup": None,
                "actions": rep.actions, "warnings": rep.warnings, "notes": rep.notes}
    bk = Backup(root, rep)
    legacy_backup_files = []
    if migrate_legacy:
        try:
            original = _complete_tree_state(legacy)
            saved = bk.save_tree(LEGACY_AIDP_DIR)
            if saved is None or _complete_tree_state(saved) != original \
                    or _complete_tree_state(legacy) != original:
                raise RuntimeError("旧运行目录完整备份校验失败")
            legacy_backup_files = _legacy_backup_files(root, legacy, saved, rep)
            journal.migration_evidence = {
                "backup_path": saved.relative_to(root).as_posix(),
                "legacy_digest": _legacy_state_digest(legacy),
                "backup_digest": _legacy_state_digest(saved),
            }
        except (OSError, RuntimeError) as exc:
            rep.warn(f"旧运行目录备份失败，已保留原目录：{exc}")
            return {"status": "blocked", "reason": "legacy-backup-failed",
                    "mode": mode, "project": project, "version": version, "user": user,
                    "vcs_mode": vcs.detect_mode(root), "dsh_extensions": None,
                    "agents": agents, "agent_source": agent_source, "adapter_mode": "copy",
                    "scaffold_version": scaffold_raw, "previous_scaffold_version": previous,
                    "contract_decision": decision, "pending": False, "rewrite_queue": [],
                    "orphans": [], "local_overwritten": [], "backup": bk.dir.name if bk.dir else None,
                    "actions": rep.actions, "warnings": rep.warnings, "notes": rep.notes}
    specs = []
    if "claude" in agents:
        specs.append(("claude", runtime_layout.RUNTIME_HOME["claude"]))
    if {"codex", "dsh"} & set(agents):
        specs.append(("shared", runtime_layout.RUNTIME_HOME["shared"]))
    overlay_updates = set()
    # ⛔ 判据是「受管 manifest 在不在」，不是「目录在不在」：运行根降层后就是 `.claude` /
    #    `.agents` 本身，而它们作为 Agent 标记目录**空着也存在**，按目录判会去读不存在的 manifest。
    def _installed(home: str) -> bool:
        return (root / home / runtime_layout.RUNTIME_MANIFEST).is_file()

    if len(specs) == 2 and all(_installed(home) for _kind, home in specs):
        overlays = {home: runtime_layout._user_overlay(root / home, home, kind)
                    for kind, home in specs}
        first, second = (home for _kind, home in specs)
        for relative in overlays[first].keys() & overlays[second].keys():
            if overlays[first][relative] != overlays[second][relative]:
                raise RuntimeError(f"双包用户文件冲突: {relative}")
        if overlays[first] != overlays[second]:
            overlay_updates.update((first, second))
    journal.migration_stage = "render-runtime"
    # ⛔ 快照必须在安装前取：`templates/` 是受管契约，安装后模板位已是新版、再比就分不出
    #    「用户改过」与「版本升级」。
    optional_rules_before = snapshot_optional_rules(root, [home for _kind, home in specs])
    for kind, home in specs:
        dest = root / home
        if _installed(home):
            current = dest / runtime_layout.RUNTIME_MANIFEST
            manifest = json.loads(current.read_text(encoding="utf-8"))
            if manifest.get("version") == scaffold_raw and not a.force and home not in overlay_updates:
                try:
                    runtime_layout.validate_runtime(dest, expected_home=home)
                except ValueError:
                    pass  # 受管文件漂移由 render_runtime 完整备份后修复。
                else:
                    continue
        journal.expect_tree(dest, source, include=lambda path:
                            path.parts[0] in runtime_layout.RUNTIME_DIRS
                            and not runtime_layout._excluded(path.as_posix()))
        journal.expect(dest / runtime_layout.RUNTIME_MANIFEST)
        journal.expect(dest.parent / ".aidp-runtime.lock")
        def backup_runtime(_destination, runtime_home=home):
            saved = bk.save_tree(runtime_home)
            if saved is not None:
                rep.warn(f"受管运行包有本地修改，完整备份：{saved.relative_to(root).as_posix()}")
            return saved

        runtime_layout.render_runtime(source, dest, home, scaffold_raw, kind,
                                      backup_callback=backup_runtime)
        rep.act("install", home + "/", "Agent 原生运行包")
    # 可选规则的安装位不在下发面里（真源没有它、运行包当用户文件原样带走），
    # 不专门刷新就永久停在安装那天的版本。失败只告警，绝不影响已完成的安装事务。
    try:
        refresh_optional_rules(root, [home for _kind, home in specs], optional_rules_before, rep)
    except OSError as exc:  # noqa: BLE001
        rep.warn(f"可选规则刷新失败（不影响本次安装）：{exc}")
    for ag in agents:
        marker = root / MARKER_DIRS[ag]
        if not marker.is_dir():
            marker.mkdir(parents=True)
            rep.act("create", MARKER_DIRS[ag] + "/", "Agent 标记目录")
    dirs = [d for d in L.skeleton_dirs(root, version, user) if not d.startswith(".aidp/")]
    for rel in dirs:
        (root / rel).mkdir(parents=True, exist_ok=True)
        journal.record(rel)
    sync_docs(root, bool(previous), rep, bk, agents)
    journal.record(L.USER_FILLABLE_BASELINE)
    sync_config(root, ctx, rep, bk, agents)
    sync_memory(root, ctx, bool(previous), rep, bk, agents)
    journal.record(L.USER_FILLABLE_BASELINE)
    sync_root_files(root, ctx, agents, rep, bk)
    if decision != "protect":
        sync_memory_file(root, agents, ctx, decision, bool(previous), rep, bk)
    for rel in (".claude/skills" if "claude" in agents else None,
                ".agents/skills" if {"codex", "dsh"} & set(agents) else None):
        if rel is not None:
            destination = root / rel / L.SKILL_NAME
            journal.expect_tree(destination, L.SKILL_DIR, include=lambda path:
                                "__pycache__" not in path.parts
                                and "sources" not in path.parts
                                and "tests" not in path.parts
                                and path.suffix != ".pyc")
            journal.expect(destination / ".aidp-scaffold-generated")
    _install_native_skill(root, agents, rep, bk)
    manage_gitkeep(root, dirs, rep)
    for rel in dirs:
        journal.record(root / rel / ".gitkeep")
    ensure_nav_readmes(root, rep)
    manage_gitkeep(root, dirs, rep)
    for rel in dirs:
        journal.record(root / rel / ".gitkeep")
    queue = L.queue_entries(root)
    if scaffold_raw and decision != "protect":
        if queue:
            scaffold_marker.write_pending(root, scaffold_raw)
        else:
            scaffold_marker.write_version(root, scaffold_raw)
        journal.record(scaffold_marker.CONFIG_REL)
    dsh_extensions = install_dsh_command_plugin(mode, agents, rep)
    if not a.no_agent_sync:
        journal.migration_stage = "agent-adapters"
        _expect_agent_adapter_writes(journal, root, agents)
        run_agent_sync(root, agents, "copy", rep, strict=True)
    active_homes = {home for _kind, home in specs}
    for home in sorted(set(runtime_layout.RUNTIME_HOME.values()) - active_homes):
        destination = root / home
        if not os.path.lexists(destination):
            continue
        if destination.is_symlink() or not destination.is_dir() \
                or not (destination / runtime_layout.RUNTIME_MANIFEST).is_file():
            raise ValueError(f"未受管运行目录不能清理：{destination}")
        if runtime_layout._runtime_modified(destination):
            old_state = _complete_tree_state(destination)
            saved = bk.save_tree(home)
            if saved is None or _complete_tree_state(saved) != old_state:
                raise RuntimeError(f"不再启用的运行包备份失败：{destination}")
        shutil.rmtree(destination)
        rep.act("remove", home + "/", "Agent 集合不再启用")
    for agent in KNOWN_AGENTS:
        marker_dir = root / MARKER_DIRS[agent]
        if not marker_dir.is_dir():
            continue
        disabled = marker_dir / DISABLED_AGENT_MARK
        if os.path.lexists(disabled) and (disabled.is_symlink() or not disabled.is_file()
                                           or disabled.read_text(encoding="utf-8") != "disabled\n"):
            raise ValueError(f"Agent 禁用标记含用户内容，拒绝修改：{disabled}")
        if agent in agents:
            if disabled.is_file():
                disabled.unlink()
                rep.act("remove", rel_of(root, disabled), "Agent 重新启用")
        elif not disabled.is_file():
            journal.expect(disabled)
            L.write_text_lf(disabled, "disabled\n")
            rep.act("create", rel_of(root, disabled), "Agent 已切换为停用")
    for agent, rel in (("claude", ".claude/skills"), ("shared", ".agents/skills")):
        enabled = ("claude" in agents if agent == "claude" else bool({"codex", "dsh"} & set(agents)))
        if enabled:
            continue
        target = root / rel / L.SKILL_NAME
        if not os.path.lexists(target):
            continue
        if target.is_symlink() or not (target / ".aidp-scaffold-generated").is_file():
            raise ValueError(f"未受管脚手架 SKILL 不能清理：{target}")
        old_state = _complete_tree_state(target)
        saved = bk.save_tree(f"{rel}/{L.SKILL_NAME}")
        if saved is None or _complete_tree_state(saved) != old_state:
            raise RuntimeError(f"脚手架 SKILL 清理前备份失败：{target}")
        shutil.rmtree(target)
        rep.act("remove", f"{rel}/{L.SKILL_NAME}/", "Agent 集合不再启用")
    for _kind, home in specs:
        runtime_layout.validate_runtime(root / home, expected_home=home)
    if not a.no_agent_sync:
        adapter_home = runtime_home_for(agents)
        check = subprocess.run(
            [sys.executable, str(root / adapter_home / "scripts/agent_sync.py"),
             "--root", str(root), "--agents", ",".join(agents), "--mode", "copy", "--check"],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            env=L.child_env(), **L.TEXT_IO)
        if check.returncode != 0:
            raise RuntimeError(f"原生 Agent 入口校验失败：{(check.stdout or check.stderr).strip()[:300]}")
    if migrate_legacy:
        journal.migration_stage = "remove-legacy"
        if _complete_tree_state(legacy) != original:
            raise LegacyChangedDuringMigration("旧运行目录在备份后发生变化，拒绝删除并保留最新修改")
        shutil.rmtree(legacy)
        rep.act("remove", LEGACY_AIDP_DIR + "/", "Agent 原生运行包已校验并安装")
        record = root / MIGRATION_FAILURE_LEDGER
        if record.is_file() and not record.is_symlink():
            record.unlink()
            rep.act("remove", MIGRATION_FAILURE_LEDGER, "旧运行目录迁移已完成")
    if a.adapter_mode == "link":
        rep.actions.append({"op": "normalized", "path": "agent-adapters", "why": "link → managed-copy",
                            "action": "normalized", "from": "link", "to": "managed-copy"})
    return {"mode": mode, "project": project, "version": version, "user": user,
            "vcs_mode": vcs.detect_mode(root), "dsh_extensions": dsh_extensions,
            "agents": agents, "agent_source": agent_source, "adapter_mode": "copy",
            "scaffold_version": scaffold_raw, "previous_scaffold_version": previous,
            "contract_decision": decision, "pending": bool(queue), "rewrite_queue": queue,
            "orphans": [], "local_overwritten": [], "backup": bk.dir.name if bk.dir else None,
            "legacy_backup_files": legacy_backup_files,
            "actions": rep.actions, "warnings": rep.warnings, "notes": rep.notes}


# ── 主流程 ──────────────────────────────────────────────────────────────────
def run(root: Path, a) -> dict:
    if (root / ".aidp").is_symlink() and (root / ".aidp").exists():
        raise ValueError(f"旧运行目录是 symlink，拒绝跟随：{root / '.aidp'}")
    rep = Report()
    mode = a.mode if a.mode != "auto" else detect_mode(root)[0]
    agents, agent_source = resolve_agents(root, a.agent, interactive=not a.json)
    if mode in ("migrate", "upgrade") and a.agent and parse_agents(a.agent):
        agents, agent_source = parse_agents(a.agent), "argument"
    if (root / LEGACY_AIDP_DIR).is_dir():
        if mode == "init":
            raise ValueError("旧运行目录已存在，不能按 init 覆盖；请使用 migrate")
        return _run_native(root, a, mode, agents, agent_source, migrate_legacy=True)
    return _run_native(root, a, mode, agents, agent_source)


def print_human(res: dict):
    print(f"[scaffold] 模式 {res['mode']} · 项目 {res['project']} · 版本 {res['version']} · 用户 {res['user']}")
    print(f"[scaffold] Agent {','.join(res['agents'])}（来源 {res['agent_source']}）· 适配层 {res['adapter_mode']}")
    print(f"[scaffold] 脚手架 {res['previous_scaffold_version'] or '未建立'} → {res['scaffold_version']}"
          f"（契约处置：{res['contract_decision']}）")
    state = res.get("dsh_extensions")
    if state:
        # ⛔ 不得把 `cli-unavailable` / `unknown` 说成「未安装」：那是本进程的探测能力问题，不是扩展状态。
        mark = MARKS["ok"] if state in DSH_STATE_READY else MARKS["warn"]
        print(f"[scaffold] {mark} DSH 扩展 {DSH_PLUGIN_NAME}：{state}"
              f"（{DSH_STATE_LABEL.get(state, '状态未知')}）")
    counts = {}
    for x in res["actions"]:
        counts[x["op"]] = counts.get(x["op"], 0) + 1
    print("[scaffold] 动作：" + (" · ".join(f"{k} {v}" for k, v in counts.items()) or "无"))
    for x in res["actions"]:
        if x["op"] not in ("create", "update") or not x["path"].startswith(".aidp/"):
            print(f"  {x['op']:10} {x['path']}" + (f"（{x['why']}）" if x["why"] else ""))
    for w in res["warnings"]:
        print(f"  {MARKS['warn']} {w}")
    for n in res["notes"]:
        print(f"  {MARKS['info']} {n}")
    if res["pending"]:
        print(f"[scaffold] {MARKS['pending']} 语义改写待办 {len(res['rewrite_queue'])} 条（{L.REWRITE_QUEUE_FILE}）："
              "逐条语义改写后跑 finalize_upgrade.py（核验每条已改写、删除队列并收口；无需改动的条目用 --accept 标记）")
    else:
        print(f"[scaffold] {MARKS['ok']} 无语义改写待办，scaffold.version 已写入")


def main(argv=None) -> int:
    # ① 先把控制台配成不会因编码抛异常（Windows GBK 下 emoji 一 print 就 UnicodeEncodeError），
    #    ② 再按实际能力决定用 emoji 还是 ASCII 记号。⛔ 绝不能让「打印」把整次执行判死。
    global MARKS
    MARKS = L.console_marks()
    ap = argparse.ArgumentParser(description="AIDP 脚手架：init / migrate / upgrade")
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--detect", action="store_true", help="只探测并输出 JSON")
    ap.add_argument("--mode", choices=("auto", "init", "migrate", "upgrade"), default="auto")
    ap.add_argument("--version", default=None, help="项目业务版本号，如 V0.1.0")
    ap.add_argument("--user", default=None, help="开发者标识（缺省 git config user.name）")
    ap.add_argument("--agent", default="", help="项目根无 Agent 标记目录时装配的 Agent：claude,codex,dsh")
    ap.add_argument("--adapter-mode", choices=("link", "copy"), default="copy" if os.name == "nt" else "link")
    ap.add_argument("--name-cn", default=None, help="项目中文名（写入 memory/aidp-config.yaml）")
    ap.add_argument("--force", action="store_true", help="无视版本门控覆盖契约文件")
    ap.add_argument("--keep-backups", type=int, default=L.PRUNE_KEEP_LAST_DEFAULT,
                    help="备份保留个数（0 = 不清理）")
    ap.add_argument("--keep-days", type=int, default=L.PRUNE_KEEP_DAYS_DEFAULT)
    ap.add_argument("--no-agent-sync", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"项目根不存在：{root}", file=sys.stderr)
        return 2
    if a.detect:
        print(json.dumps(detect(root), ensure_ascii=False, indent=2))
        return 0
    if L.is_template_project(root):
        print(f"{MARKS['block']} 目标是 AIDP 模板项目自身：模板维护请用 mirror_to_bundle.py，不在模板上运行脚手架",
              file=sys.stderr)
        return 2
    if not (L.BUNDLE_AIDP.is_dir() and L.bundle_version()):
        print(f"{MARKS['block']} 脚手架 bundle 不完整（缺 assets/aidp 或 assets/SCAFFOLD_VERSION）", file=sys.stderr)
        return 2
    user = vcs.developer_identity(root, a.user)
    if not user or not L.USER_RE.match(user):
        print(f"{MARKS['block']} 开发者标识无效：{user!r}（仅字母数字 _ . -；用 --user 指定或设置 git config user.name）",
              file=sys.stderr)
        return 2
    a.user = user
    if a.version and not L.VERSION_RE.match(a.version):
        print(f"{MARKS['block']} 版本号格式应为 V0.1.0：{a.version}", file=sys.stderr)
        return 2
    try:
        res = run(root, a)
    except (ValueError, RuntimeError) as e:
        print(f"{MARKS['block']} {e}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print_human(res)
    return 3 if res.get("status") == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
