#!/usr/bin/env python3
"""Classify changed files for CI/CD watch decisions.

The classifier is deliberately conservative: only source files under a
recognized project source root are formal code. An otherwise source-looking
file with an unknown layout fails closed and requests a CI/CD watch.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Set


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

CANONICAL_ROOTS = ("src", "web", "server", "code/web", "code/server")
CODE_SIDE_ROOTS = ("code/frontend", "code/backend")
IGNORED_DIRS = {".git", "node_modules", "target", "dist", "build", "vendor"}


def _norm(path: str) -> str:
    return path.replace("\\", "/").strip().strip('"').rstrip("/")


def _valid_relative_path(path: str) -> bool:
    if not path or path.startswith("/"):
        return False
    return all(part not in {"", ".", ".."} for part in path.split("/"))


def _git_paths(root: str, base_ref: Optional[str]) -> tuple[List[str], bool]:
    """Read tracked diff paths plus untracked paths without shell parsing."""
    commands = []
    if base_ref is not None:
        # A base ref describes the commits that will be pushed.  Do not mix
        # in worktree files that are not part of that push.
        commands.append(["git", "-C", root, "diff", "--name-only", "-z", base_ref, "HEAD"])
    else:
        commands.append(["git", "-C", root, "diff", "--name-only", "-z", "HEAD"])
        commands.append(["git", "-C", root, "ls-files", "--others", "--exclude-standard", "-z"])
    paths: Set[str] = set()
    failed = False
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, check=False)
        except OSError:
            failed = True
            continue
        if result.returncode != 0:
            failed = True
            continue
        for raw in result.stdout.split(b"\0"):
            if raw:
                paths.add(_norm(os.fsdecode(raw)))
    return sorted(paths), failed


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
    if basename.startswith("readme") or ext in DOCUMENT_EXTENSIONS:
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
    root: str, changed_files: Optional[Iterable[str]] = None, base_ref: Optional[str] = None
) -> dict:
    """Classify a change set and decide whether CI/CD should be watched."""
    root = os.path.abspath(root)
    collection_error = False
    if changed_files is None:
        raw_changed, collection_error = _git_paths(root, base_ref)
    else:
        raw_changed = [str(path) for path in changed_files]
    changed = sorted({_norm(path) for path in raw_changed if _norm(path)})
    source_roots = sorted(_recognized_source_roots(root, changed))
    formal: List[str] = []
    non_formal: List[str] = []
    unrecognized_source = collection_error or any(not _valid_relative_path(path) for path in changed)

    for path in changed:
        if _is_non_formal_path(path, source_roots):
            non_formal.append(path)
            continue
        ext = os.path.splitext(path.lower())[1]
        basename = os.path.basename(path).lower()
        matched_root = next((candidate for candidate in source_roots if _matches_source_root(path, candidate)), None)
        is_entry = basename in PROJECT_ENTRY_FILES and matched_root is not None
        if matched_root is not None and (ext in SOURCE_EXTENSIONS or is_entry):
            formal.append(path)
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
    }


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Classify changed files for CI/CD watching")
    parser.add_argument("--root", default=".")
    parser.add_argument("--base-ref")
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args(argv)
    result = classify_commit_change(args.root, args.paths or None, args.base_ref)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
