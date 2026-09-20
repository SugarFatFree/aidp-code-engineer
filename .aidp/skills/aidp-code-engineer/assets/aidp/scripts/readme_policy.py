#!/usr/bin/env python3
"""共享的 README 范围判定策略（代码单元 / 导航枢纽 / 平铺叶子 三档）。"""
import fnmatch
import json
import os
import re
import subprocess
from pathlib import Path

# 依赖树、构建产物、备份与废弃归档：既不判 README 需求，也不进范围外扫描。
EXCLUDED_DIR_NAMES = {
    "node_modules", "dist", "build", "target", "vendor", "out",
    "coverage", "__pycache__", "bower_components", "site-packages",
}
EXCLUDED_DIR_PREFIXES = (".aidp-backup-",)

ENTRY_FILES = {
    "package.json", "pnpm-workspace.yaml", "vite.config.js", "vite.config.ts",
    "vue.config.js", "next.config.js", "nuxt.config.ts", "angular.json",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "settings.gradle.kts", "go.mod", "go.work", "requirements.txt", "pyproject.toml",
    "setup.py", "Cargo.toml", "composer.json", "Gemfile", "mix.exs",
}


def _root(root):
    return Path(root).resolve() if root is not None else Path.cwd().resolve()


def _relative(path, root):
    p = Path(path)
    if not p.is_absolute():
        p = root / p
    try:
        return p.resolve().relative_to(root.resolve())
    except ValueError:
        return p


BASELINE_REL = "memory/.sprint-autopilot-baseline.json"


def _readme_required_entries(root):
    """显式声明：baseline `project_state.README_REQUIRED` 数组（缺失 / 损坏 / 非数组 → 空）。"""
    state = root / BASELINE_REL
    if not state.is_file():
        return []
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    ps = data.get("project_state") if isinstance(data, dict) else None
    entries = ps.get("README_REQUIRED", []) if isinstance(ps, dict) else []
    return entries if isinstance(entries, list) else []


def _explicit_paths(root):
    entries = _readme_required_entries(root)
    if not entries:
        return []
    paths = []
    for item in entries:
        required = True
        value = item
        if isinstance(item, dict):
            value = item.get("path", item.get("directory", item.get("dir")))
            required = item.get("required", True) is True
        if required and isinstance(value, str):
            candidate = (root / value.strip().strip("/")).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            paths.append(candidate)
    return paths


def _explicit_required(rel, root):
    entries = _readme_required_entries(root)
    if not entries:
        return False
    rel_text = rel.as_posix()
    for item in entries:
        required = True
        value = item
        if isinstance(item, dict):
            value = item.get("path", item.get("directory", item.get("dir")))
            required = item.get("required", True) is True
        if required and isinstance(value, str):
            candidate = (root / value.strip().strip("/")).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                continue
            if candidate.as_posix() == (root / rel_text).resolve().as_posix():
                return True
    return False


def _has_entry(path):
    return path.is_dir() and any((path / name).is_file() for name in ENTRY_FILES)


def _is_example_demo(rel):
    # 约定 19：示例子项目不纳入强制 README 范围。
    return len(rel.parts) == 3 and rel.parts[0] == "code" and rel.parts[1] in {
        "frontend", "backend", "web", "server"
    } and rel.parts[2].lower().startswith(("example-", "demo-", "samples-"))


def _normalized_child(parent, declared):
    value = str(declared).strip().replace("\\", "/")
    value = re.sub(r"\s+", "", value)
    if value.startswith(":"):
        value = value[1:]
    while value.startswith("./"):
        value = value[2:]
    if not value:
        return None
    candidate = (parent / value).resolve()
    return candidate


def _workspace_patterns(directory):
    patterns = []
    package = directory / "package.json"
    if package.is_file():
        try:
            data = json.loads(package.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        workspaces = data.get("workspaces", []) if isinstance(data, dict) else []
        if isinstance(workspaces, dict):
            workspaces = workspaces.get("packages", [])
        if isinstance(workspaces, list):
            patterns.extend(str(item).strip().lstrip("./") for item in workspaces if isinstance(item, str))
    pnpm = directory / "pnpm-workspace.yaml"
    if pnpm.is_file():
        try:
            text = pnpm.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        patterns.extend(line.strip().lstrip("- ").strip("'\"").lstrip("./")
                        for line in text.splitlines()
                        if line.strip().startswith("-") and "packages:" not in line)
    go_work = directory / "go.work"
    if go_work.is_file():
        text = go_work.read_text(encoding="utf-8", errors="replace")
        patterns.extend(value.strip().lstrip("./") for value in re.findall(r"(?:^|\n)\s*(?:use\s+)?\./([^\s)]+)", text))
    return [item for item in patterns if item]


def _is_aggregator(directory, rel=None):
    """Whether a directory is a real build or workspace aggregator root."""
    if rel is not None and len(rel.parts) >= 2 and rel.parts[:2] in {
        ("code", "sql"), ("code", "docs"), ("code", "scripts"),
        ("code", "resources"),
    }:
        return False
    if _workspace_patterns(directory):
        return True
    pom = directory / "pom.xml"
    if pom.is_file():
        try:
            text = pom.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        if re.search(r"<packaging>\s*pom\s*</packaging>", text, re.I):
            return True
        if re.search(r"<modules>\s*<module>", text, re.I | re.S):
            return True
    for name in ("settings.gradle", "settings.gradle.kts"):
        settings = directory / name
        if settings.is_file():
            try:
                text = settings.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if re.search(r"\binclude\s*(?:\(|\s*)['\"]", text):
                return True
    return False


def _has_real_parent_declaration(directory):
    """Whether an ancestor build descriptor declares this exact child path."""
    target = directory.resolve()
    ancestor = directory.parent
    while ancestor != ancestor.parent:
        pom = ancestor / "pom.xml"
        if pom.is_file():
            try:
                text = pom.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            for declared in re.findall(r"<module>\s*([^<]+?)\s*</module>", text, re.I | re.S):
                if _normalized_child(ancestor, declared) == target:
                    return True
        for name in ("settings.gradle", "settings.gradle.kts"):
            settings = ancestor / name
            if not settings.is_file():
                continue
            try:
                text = settings.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for declared in re.findall(r"\binclude\s*(?:\(([^)]*)\)|([^\n]+))", text):
                fragment = " ".join(part for part in declared if part)
                for value in re.findall(r"['\"]([^'\"]+)['\"]", fragment):
                    normalized = value.replace(":", "/")
                    if not normalized.startswith("../"):
                        normalized = normalized.replace(".", "/")
                    if _normalized_child(ancestor, normalized) == target:
                        return True
        for pattern in _workspace_patterns(ancestor):
            target_rel = target.relative_to(ancestor).as_posix() if target.is_relative_to(ancestor) else ""
            if target_rel and fnmatch.fnmatch(target_rel, pattern.rstrip("/")):
                return True
        ancestor = ancestor.parent
    return False

def _is_excluded_name(name):
    return (
        name in EXCLUDED_DIR_NAMES
        or name.startswith(EXCLUDED_DIR_PREFIXES)
        or (name.startswith(".") and name not in {".", ".."})
    )


def _is_excluded_path(rel):
    return any(_is_excluded_name(part) for part in rel.parts)


def _in_code_tree(rel):
    """Whether a path lives inside a source tree governed by the code-unit rules."""
    parts = rel.parts
    if not parts:
        return False
    return parts[0] == "code" or (parts[0] in {"web", "server", "src"} and len(parts) >= 1)


def _navigation_facts(directory):
    """Return (subdirectory_count, has_multi_level) for the navigation rule."""
    try:
        children = [p for p in directory.iterdir()
                    if p.is_dir() and not _is_excluded_name(p.name)]
    except OSError:
        return 0, False
    count = len(children)
    if count >= 2:
        return count, True
    if count == 1:
        try:
            return count, any(True for _ in children[0].iterdir())
        except OSError:
            return count, False
    return 0, False


def _is_formal_location(rel):
    parts = rel.parts
    if len(parts) in {2, 3} and parts[0] == "code" and parts[1] in {"frontend", "backend", "web", "server"}:
        return True
    if len(parts) == 2 and parts[0] == "code":
        return parts[1] in {"frontend", "backend", "web", "server"} or parts[1] not in {"sql", "docs", "scripts", "resources"}
    return len(parts) == 1 and parts[0] in {"web", "server", "src"}


def _decision(required, reason, project_root_type, is_formal_code_root,
              is_independent_module, is_navigation_hub, subdirectory_count,
              explicitly_allowed):
    return {
        "required": required,
        "reason": reason,
        "project_root_type": project_root_type,
        "is_formal_code_root": is_formal_code_root,
        "is_independent_module": is_independent_module,
        "is_navigation_hub": is_navigation_hub,
        "subdirectory_count": subdirectory_count,
        "explicitly_allowed": explicitly_allowed,
    }


def is_readme_required_directory(path, project_layout, root=None):
    """Return README policy metadata for a directory.

    Three outcomes, decided in this order:

    1. ``required=True`` code unit — formal source root, project root under
       ``code/{side}/``, or a module a real build descriptor declares.
    2. ``required=True`` navigation hub — a directory outside the source trees
       whose own subdirectory structure needs an index (``>= 2`` subdirectories,
       or one non-empty subdirectory).
    3. ``required=False`` — a flat leaf directory, a directory inside a source
       tree (its README belongs to the owning unit), or an excluded tree.

    An explicit ``README_REQUIRED`` declaration outranks every automatic rule.
    ``project_layout`` is accepted for compatibility with existing callers;
    filesystem facts and the explicit state declaration are authoritative.
    """
    del project_layout
    project_root = _root(root)
    directory = Path(path)
    if not directory.is_absolute():
        directory = project_root / directory
    directory = directory.resolve()
    rel = _relative(directory, project_root)
    explicitly_allowed = _explicit_required(rel, project_root)
    has_entry = _has_entry(directory)
    formal_location = _is_formal_location(rel)
    is_formal_code_root = formal_location and has_entry and not _is_example_demo(rel)
    under_formal_side = (
        len(rel.parts) >= 3 and rel.parts[0] == "code" and
        rel.parts[1] in {"frontend", "backend", "web", "server"}
    )
    is_independent_module = has_entry and not _is_example_demo(rel) and (
        (under_formal_side and len(rel.parts) == 3) or
        _has_real_parent_declaration(directory) or _is_aggregator(directory, rel)
    )
    subdir_count, has_multi_level = _navigation_facts(directory)

    if explicitly_allowed:
        return _decision(True, "explicit-README_REQUIRED", "explicit",
                         is_formal_code_root, is_independent_module,
                         False, subdir_count, True)
    if is_formal_code_root:
        kind = "frontend" if "frontend" in rel.parts or rel.name == "web" else "backend"
        return _decision(True, f"formal-{kind}-source-root", kind,
                         True, is_independent_module, False, subdir_count, False)
    # Custom code directories are only modules when a real parent aggregator
    # declares them; an arbitrary package.json/pom.xml under code/sql or code/docs
    # must not turn a resource tree into a README root.
    if has_entry and rel.parts and rel.parts[0] == "code" and is_independent_module:
        return _decision(True, "independent-code-module", "module",
                         False, True, False, subdir_count, False)
    if _is_excluded_path(rel):
        return _decision(False, "excluded-directory", "none",
                         False, False, False, subdir_count, False)
    if _in_code_tree(rel):
        # Inside a source tree the README belongs to the owning code unit;
        # subdirectory depth here is package structure, not navigation.
        return _decision(False, "code-tree-internal", "none",
                         False, is_independent_module, False, subdir_count, False)
    if has_multi_level:
        return _decision(True, "navigation-hub", "navigation",
                         False, False, True, subdir_count, False)
    return _decision(False, "flat-leaf-directory", "none",
                     False, False, False, subdir_count, False)


def explicit_required_directories(root):
    """Return in-project explicit README_REQUIRED paths, including missing dirs."""
    return _explicit_paths(_root(root))


def navigation_readme_body(directory):
    """Render an index README body: subdirectory list only, no code metadata."""
    try:
        children = sorted(p.name for p in directory.iterdir()
                          if p.is_dir() and not _is_excluded_name(p.name))
    except OSError:
        children = []
    lines = [f"# {directory.name}", "",
             "本目录是导航枢纽，下列子目录各自承载一类内容。", "", "## 子目录", ""]
    if children:
        lines.extend(f"- `{name}/` — 用途待补充" for name in children)
    else:
        lines.append("- 待补充")
    lines.append("")
    return "\n".join(lines)


def code_readme_body(directory):
    """Render a code-unit README body."""
    return (f"# {directory.name}\n\n"
            "本目录为项目源码根或独立模块，请补充用途、技术栈、启动命令、目录概览和主要依赖。\n")


def default_readme_body(directory, decision):
    """Pick the README body matching the decision kind."""
    if decision.get("is_navigation_hub"):
        return navigation_readme_body(directory)
    return code_readme_body(directory)


def ensure_required_readmes(root, project_layout, content_factory=None):
    """Create README.md for every directory the shared policy requires."""
    project_root = _root(root)
    candidates = []
    code = project_root / "code"
    if code.is_dir():
        candidates.extend(p for p in code.rglob("*")
                          if p.is_dir() and not _is_excluded_path(_relative(p, project_root)))
    for name in ("web", "server", "src"):
        directory = project_root / name
        if directory.is_dir():
            candidates.append(directory)
    candidates.extend(p for p in _explicit_paths(project_root) if p.is_dir())
    created = []
    for directory in sorted(set(candidates)):
        decision = is_readme_required_directory(directory, project_layout, root=project_root)
        target = directory / "README.md"
        if not decision["required"] or target.exists():
            continue
        text = (content_factory(directory, decision) if content_factory
                else default_readme_body(directory, decision))
        target.write_text(text, encoding="utf-8")
        created.append(str(target.relative_to(project_root)))
    return created


def _git_tracked_files(root):
    """Return git-tracked paths, or None when git cannot answer."""
    try:
        proc = subprocess.run(["git", "-C", str(root), "ls-files", "-z"],
                              capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    text = proc.stdout.decode("utf-8", errors="replace")
    return {item for item in text.split("\0") if item}


def scan_out_of_scope_readmes(root, project_layout, scan_roots=None):
    """List tracked README.md files that sit outside the required scope.

    Dependency trees, build output, backups and untracked third-party files are
    never reported: they are not project assets.
    """
    project_root = _root(root)
    if scan_roots is None:
        scan_roots = [project_root / name for name in ("code", "web", "server", "src")]
    tracked = _git_tracked_files(project_root)
    findings = []
    for base in scan_roots:
        base = Path(base)
        if not base.is_dir():
            continue
        for current, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if not _is_excluded_name(d))
            if "README.md" not in filenames:
                continue
            readme = Path(current) / "README.md"
            rel = _relative(readme, project_root)
            if tracked is not None and rel.as_posix() not in tracked:
                continue
            decision = is_readme_required_directory(readme.parent, project_layout,
                                                    root=project_root)
            if decision["required"]:
                continue
            findings.append({"path": rel.as_posix(), "reason": decision["reason"]})
    findings.sort(key=lambda item: item["path"])
    return findings


def format_out_of_scope_report(findings):
    """Render the scan result: a count line first, then one line per finding."""
    if not findings:
        return ["README_OUT_OF_SCOPE: 0 处（无范围外 README）"]
    lines = [f"README_OUT_OF_SCOPE: {len(findings)} 处"]
    lines.extend(f"README_OUT_OF_SCOPE {item['path']} reason={item['reason']} "
                 "action=preserve-and-report" for item in findings)
    return lines
