#!/usr/bin/env python3
"""Classify changed files for CI/CD watch decisions.

The classifier is deliberately conservative: only source files under a
recognized project source root are formal code. An otherwise source-looking
file with an unknown layout fails closed and requests a CI/CD watch.

Conservative classes (always formal -> watch, never silently non-formal):
git submodule pointer changes (gitlink, mode 160000), changes inside a nested
`.git` repository, and config-like files (.yml/.xml/.properties/.sql ...) that
sit under a recognized source root, plus executable SQL and actual configuration
assets under docs/deployment. The classifier is strictly read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set

from vcs import detect_mode, unsupported, EXIT_UNSUPPORTED


SOURCE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cs", ".cxx", ".dart", ".go", ".groovy",
    ".h", ".hpp", ".java", ".js", ".jsx", ".json", ".json5", ".kt",
    ".kts", ".less", ".m", ".mm", ".php", ".pl", ".py", ".pyw",
    ".rb", ".rs", ".sass", ".scala", ".scss", ".sh", ".swift",
    ".ts", ".tsx", ".vue", ".css", ".html",
}

# Build/package manifests and lockfiles are formal inputs even when they have
# no source-code extension.  Keep names lower-case because matching normalizes
# the basename before lookup.
PROJECT_ENTRY_FILES = {
    "build.gradle", "build.gradle.kts", "cargo.toml", "cargo.lock", "composer.json",
    "go.mod", "go.sum", "mix.exs", "package.json", "package-lock.json",
    "pnpm-lock.yaml", "pom.xml", "poetry.lock", "pyproject.toml",
    "requirements.txt", "setup.py", "settings.gradle", "settings.gradle.kts",
    "yarn.lock",
}

DOCUMENT_EXTENSIONS = {
    ".adoc", ".csv", ".doc", ".docx", ".md", ".pdf", ".ppt", ".pptx",
    ".rst", ".sql", ".txt", ".xls", ".xlsx",
}

# 源码根下的配置类文件：可能改变运行行为，保守视为正式变更（不静默判非正式）。
CONFIG_EXTENSIONS = {
    ".yml", ".yaml", ".xml", ".properties", ".sql", ".toml", ".ini", ".conf", ".cfg", ".env",
}

CANONICAL_ROOTS = ("src", "web", "server", "code/web", "code/server")
CODE_SIDE_ROOTS = ("code/frontend", "code/backend")
IGNORED_DIRS = {".git", "node_modules", "target", "dist", "build", "vendor"}


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip().strip('"').rstrip("/")


def _valid_relative_path(path: str) -> bool:
    if not path or path.startswith("/"):
        return False
    return all(part not in {"", ".", ".."} for part in path.split("/"))


def _run_git(root: str, *args: str) -> Optional[bytes]:
    try:
        result = subprocess.run(["git", "-C", root, *args], capture_output=True, check=False)
    except OSError:
        return None
    return result.stdout if result.returncode == 0 else None


def _empty_tree(root: str) -> str:
    out = _run_git(root, "hash-object", "-t", "tree", "/dev/null")
    return (out or b"").decode().strip() or "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _parse_raw(blob: bytes) -> tuple[List[str], Set[str]]:
    """解析 `git diff --raw -z --no-renames`：返回 (路径, 其中的 gitlink 路径)。"""
    tokens = blob.split(b"\0")
    paths: List[str] = []
    gitlinks: Set[str] = set()
    k = 0
    while k + 1 < len(tokens):
        meta = tokens[k].decode("utf-8", "replace")
        path = _norm(os.fsdecode(tokens[k + 1]))
        k += 2
        if not meta.startswith(":"):
            continue
        fields = meta[1:].split()
        if path:
            paths.append(path)
            if len(fields) >= 2 and "160000" in fields[:2]:
                gitlinks.add(path)
    return paths, gitlinks


def _git_paths(root: str, base_ref: Optional[str], head: Optional[str] = None) -> tuple[List[str], bool, Set[str]]:
    """只读取得变更路径与 gitlink（子模块指针）路径；第三项 = gitlink 集合。

    - 给了 base_ref：`base_ref..head`（head 缺省 HEAD），不混入工作区文件；
    - 只给 head：该提交相对其首个父提交的变更（根提交相对空树）；
    - 都没给：工作区相对 HEAD 的改动 + 未跟踪文件。
    """
    base_ref = base_ref or None
    head = head or None
    paths: Set[str] = set()
    gitlinks: Set[str] = set()
    failed = False
    if base_ref is not None or head is not None:
        if any(ref and ref.startswith("-") for ref in (base_ref, head)):
            return [], True, set()  # 拒绝选项形态的 ref
        tip = head or "HEAD"
        base = base_ref
        if base is None:
            base = tip + "^" if _run_git(root, "rev-parse", "--verify", "-q", tip + "^") is not None else _empty_tree(root)
        raw = _run_git(root, "diff", "--raw", "-z", "--no-renames", base, tip)
        if raw is None:
            failed = True
        else:
            found, links = _parse_raw(raw)
            paths.update(found)
            gitlinks |= links
        return sorted(paths), failed, gitlinks
    raw = _run_git(root, "diff", "--raw", "-z", "--no-renames", "HEAD")
    if raw is None:
        failed = True
    else:
        found, links = _parse_raw(raw)
        paths.update(found)
        gitlinks |= links
    others = _run_git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if others is None:
        failed = True
    else:
        paths.update(_norm(os.fsdecode(r)) for r in others.split(b"\0") if r)
    # 已登记的子模块工作区若有未提交改动，外层 diff 不一定可见：逐个只读探测，保守计入。
    staged = _run_git(root, "ls-files", "-s", "-z")
    for entry in (staged or b"").split(b"\0"):
        if entry.startswith(b"160000 "):
            sub = _norm(os.fsdecode(entry.split(b"\t", 1)[-1]))
            status = _run_git(os.path.join(root, sub), "status", "--porcelain")
            if sub and status:
                paths.add(sub)
                gitlinks.add(sub)
    return sorted(paths), failed, gitlinks


def _nested_repo_root(root: str, path: str) -> Optional[str]:
    """path 自身或其某级上层目录（不含仓库根）若带 `.git` → 返回该嵌套仓路径。"""
    parts = path.split("/")
    for n in range(1, len(parts) + 1):
        sub = "/".join(parts[:n])
        if os.path.exists(os.path.join(root, sub, ".git")):
            return sub
    return None


def _is_under(path: str, root: str) -> bool:
    if root in {"", "."}:
        return True
    return path == root or path.startswith(root + "/")


def _matches_source_root(path: str, root: str) -> bool:
    """Match a source root without letting a root project absorb mystery dirs."""
    if root in {"", "."}:
        if "/" not in path:
            return True
        return path.split("/", 1)[0] in {"src", "web", "server"}
    return _is_under(path, root)


def _walk_project_roots(root: str) -> Set[str]:
    """Find project roots that contain a known build/package entry file."""
    found: Set[str] = set()
    candidates: List[Path] = []
    root_path = Path(root)
    if any((root_path / name).is_file() for name in PROJECT_ENTRY_FILES):
        found.add(".")
    for rel in CODE_SIDE_ROOTS + ("code/web", "code/server", "web", "server"):
        candidates.append(root_path / rel)
    for candidate in candidates:
        if not candidate.is_dir():
            continue
        for current, dirs, files in os.walk(candidate):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]
            if any(name.lower() in PROJECT_ENTRY_FILES for name in files):
                found.add(os.path.relpath(current, root).replace(os.sep, "/"))
    return found


def _canonical_root_for(path: str) -> Optional[str]:
    parts = path.split("/")
    for candidate in CANONICAL_ROOTS:
        if _is_under(path, candidate):
            return candidate
    if len(parts) >= 4 and parts[0] == "code" and parts[1] in {"frontend", "backend"}:
        if parts[3] == "src":
            return "/".join(parts[:4])
    return None


def _recognized_source_roots(root: str, changed: Sequence[str]) -> Set[str]:
    roots = set(_walk_project_roots(root))
    for path in changed:
        canonical = _canonical_root_for(path)
        if canonical:
            roots.add(canonical)
        parts = path.split("/")
        basename = os.path.basename(path).lower()
        if basename in PROJECT_ENTRY_FILES:
            if len(parts) >= 3 and parts[0] == "code" and parts[1] in {"frontend", "backend"}:
                roots.add("/".join(parts[:-1]))
            elif len(parts) == 1:
                roots.add(".")
        # A conventional side-project path may be new and have no directory
        # on disk yet; its src path is still an unambiguous source root.
    return roots


def _is_deployment_input(path: str) -> bool:
    """部署目录中的可执行 SQL/实际配置须监听；操作手册和报告不算运行输入。"""
    parts = path.lower().split("/")
    if parts[:2] != ["docs", "deployment"] or len(parts) < 3:
        return False
    basename = parts[-1]
    extension = os.path.splitext(basename)[1]
    return (extension in CONFIG_EXTENSIONS or basename == ".env" or basename.startswith(".env.")
            or (extension in {".json", ".json5"}
                and any(part in {"配置文件", "config", "configs"} for part in parts[2:-1])))


def _is_non_formal_path(path: str, source_roots: Optional[Iterable[str]] = None) -> bool:
    """判定是否属"非正式变更"路径。

    ⛔ **业务语义词（`deployment` / `deploy*`）只在【源码根之外】才成立。**
       它们原本是无条件命中的，且排在源码扩展名判定**之前**——于是
       `code/backend/x/src/main/java/com/example/deployment/OrderService.java`、`.../DeployController.java`、`views/deployList.vue`
       全部被判非正式变更，`has_formal_code_change=False` 且 `classification_error=False`
       （实测三例全中）→ CICD 不监听、不部署、不探针，而 flow 侧那条 fail-closed
       因为 `classification_error` 为假**永不触发**。与本模块 docstring 自称的
       「source-looking file with an unknown layout fails closed」直接相反。

       修法：这些词只在路径**不落在任何已识别源码根之下**时才判非正式——
       业务域叫 `deployment`、控制器叫 `DeployController` 都是完全正常的源码命名。
    """
    lower = path.lower()
    parts = lower.split("/")
    basename = parts[-1]
    ext = os.path.splitext(basename)[1]
    in_source_tree = any(_matches_source_root(path, candidate) for candidate in (source_roots or ()))
    if basename in PROJECT_ENTRY_FILES:
        return False
    if basename.startswith("readme"):
        return True
    if ext in DOCUMENT_EXTENSIONS and not (in_source_tree and ext in CONFIG_EXTENSIONS):
        return True
    if parts[0] in {"docs", "tests", "test", "reports", "report", "tools", "scripts", "deploy", "deployment", "ci", "docker", "k8s", "memory"}:
        return True
    if not in_source_tree and "deployment" in parts:
        return True
    if basename in {"dockerfile", "jenkinsfile", "makefile"}:
        return True
    if not in_source_tree and basename.startswith("deploy"):
        return True
    if parts[0] in (".aidp", ".claude", ".codex", ".dsh") or lower.startswith(".aidp-"):
        return True
    if any(directory in IGNORED_DIRS for directory in parts):
        return True
    return False


def classify_commit_change(
    root: str, changed_files: Optional[Iterable[str]] = None, base_ref: Optional[str] = None,
    head: Optional[str] = None,
) -> dict:
    """Classify a change set and decide whether CI/CD should be watched."""
    root = os.path.abspath(root)
    collection_error = False
    gitlinks: Set[str] = set()
    if changed_files is None:
        raw_changed, collection_error, gitlinks = _git_paths(root, base_ref, head)
    else:
        raw_changed = [str(path) for path in changed_files]
    changed = sorted({_norm(path) for path in raw_changed if _norm(path)})
    source_roots = sorted(_recognized_source_roots(root, changed))
    formal: List[str] = []
    non_formal: List[str] = []
    unrecognized_source = collection_error or any(not _valid_relative_path(path) for path in changed)

    conservative: List[str] = []

    for path in changed:
        if _valid_relative_path(path) and (path in gitlinks or _nested_repo_root(root, path)
                                           or _is_deployment_input(path)):
            # 子仓改动和真实部署输入都可能改变运行行为，保守要求监听。
            formal.append(path)
            conservative.append(path)
            continue
        if _is_non_formal_path(path, source_roots):
            non_formal.append(path)
            continue
        ext = os.path.splitext(path.lower())[1]
        basename = os.path.basename(path).lower()
        matched_root = next((candidate for candidate in source_roots if _matches_source_root(path, candidate)), None)
        is_entry = basename in PROJECT_ENTRY_FILES and matched_root is not None
        if matched_root is not None and (ext in SOURCE_EXTENSIONS or is_entry):
            formal.append(path)
        elif matched_root is not None and ext in CONFIG_EXTENSIONS and not basename.startswith("."):
            formal.append(path)
            conservative.append(path)
        else:
            non_formal.append(path)
            if ext in SOURCE_EXTENSIONS:
                unrecognized_source = True

    classification_error = unrecognized_source
    has_formal = bool(formal)
    if classification_error:
        skip_reason = "unrecognized-source-layout"
    elif not has_formal:
        skip_reason = "no-formal-code-change"
    else:
        skip_reason = None
    return {
        "has_formal_code_change": has_formal,
        "changed_files": changed,
        "formal_code_files": sorted(formal),
        "non_formal_files": sorted(non_formal),
        "cicd_should_watch": bool(has_formal or classification_error),
        "skip_reason": skip_reason,
        "classification_error": classification_error,
        "source_roots": source_roots,
        "conservative_files": sorted(conservative),
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Classify changed files for CI/CD watching")
    parser.add_argument("--root", default=".")
    parser.add_argument("--base-ref", help="对比基线；空串按未提供处理")
    parser.add_argument("--head", help="被分类的提交（缺省 HEAD；只给 --head 时取其首个父提交为基线）")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    args.base_ref = args.base_ref or None
    args.head = args.head or None
    if (args.base_ref is not None or args.head is not None or not args.paths) and detect_mode(args.root) != "git":
        print(json.dumps(unsupported("diff")))
        return EXIT_UNSUPPORTED
    result = classify_commit_change(args.root, args.paths or None, args.base_ref, args.head)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
