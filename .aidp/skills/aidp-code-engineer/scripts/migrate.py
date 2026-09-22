#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""migrate.py —— 项目扫描与已有内容保全（`scaffold.py` 的 detect / migrate 依赖本模块）。

职责：
  · 扫描已有代码单元，按 `code/frontend|backend/{子项目}` 约定给出建议（只建议，从不移动代码）；
  · 扫描 docs/ 下非标准目录，给出对应的 AIDP 落点建议；
  · 检测项目根的产品输入（PRD 文档 / 原型目录），经确认后归位到本版本目录；
  · 把已有 CLAUDE.md / AGENTS.md 的用户内容合并进项目记忆文件的「项目自定义」段。

CLI：
    python3 migrate.py scan <root> [--json]
    python3 migrate.py place-inputs <root> --version V0.1.0 [--only a,b] [--copy] [--json]

退出码：0 成功 · 2 参数错误
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scaffold_lib as L  # noqa: E402

ENTRY_FILES = ("package.json", "pom.xml", "build.gradle", "build.gradle.kts", "go.mod",
               "requirements.txt", "pyproject.toml", "setup.py", "Cargo.toml", "composer.json",
               "Gemfile", "pubspec.yaml")
SKIP_DIRS = {".git", ".aidp", ".claude", ".codex", ".dsh", ".agents", ".github", "node_modules",
             "dist", "build", "target", "vendor", "out", "coverage", "__pycache__", ".venv", "venv",
             "docs", "memory", "env"}
FRONTEND_DEPS = ("vue", "react", "@angular/core", "vite", "next", "nuxt", "svelte", "webpack",
                 "@vitejs/plugin-vue", "element-plus", "antd")
BACKEND_DEPS = ("express", "koa", "@nestjs/core", "fastify", "egg", "hapi")
FRONTEND_NAMES = re.compile(r"(^|[-_])(web|frontend|front|ui|admin|portal|client|h5|app-web|console)($|[-_])", re.I)
BACKEND_NAMES = re.compile(r"(^|[-_])(server|backend|back|api|service|svc)($|[-_])", re.I)
SOURCE_SUFFIX = {".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".java", ".kt", ".go", ".rs", ".php",
                 ".rb", ".cs", ".c", ".cpp", ".swift", ".dart", ".scala"}

LEGACY_DOC_DIRS = {
    "docs/ui": "docs/prototype/{version}/",
    "docs/api": "docs/references/",
    "docs/test": "docs/testing/{version}/",
    "docs/tests": "docs/testing/{version}/",
    "docs/review": "docs/reports/{version}/",
    "docs/design/architecture": "docs/architecture/",
    "docs/prd": "docs/requirements/{version}/产品提供/",
    "docs/deploy": "docs/deployment/{version}/",
}
STANDARD_DOC_DIRS = {"init", "architecture", "references", "audit", "deployment", "bugfix", "design",
                     "implementation", "plans", "prompts", "prototype", "reports", "requirements", "testing"}

PRD_NAME = re.compile(r"(prd|需求|产品|requirement)", re.I)
PRD_EXT = {".md", ".markdown", ".docx", ".doc", ".pdf"}
PRD_EXCLUDE = {"readme.md", "版本变更历史.md", "版本更新日志.md", "changelog.md", "agents.md", "claude.md"}
PROTO_NAME = re.compile(r"(prototype|原型|mockup|高保真)", re.I)
MOCKUP_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".sketch", ".fig", ".xd", ".psd", ".webp"}


# ── 代码单元 ────────────────────────────────────────────────────────────────
def _side(unit: Path) -> str:
    pkg = unit / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = set({**(data.get("dependencies") or {}), **(data.get("devDependencies") or {})})
        except (OSError, ValueError, TypeError):
            deps = set()
        if any(d in deps for d in FRONTEND_DEPS):
            return "frontend"
        if any(d in deps for d in BACKEND_DEPS):
            return "backend"
    if any((unit / f).is_file() for f in ENTRY_FILES if f != "package.json"):
        return "frontend" if FRONTEND_NAMES.search(unit.name) else "backend"
    if FRONTEND_NAMES.search(unit.name):
        return "frontend"
    if BACKEND_NAMES.search(unit.name):
        return "backend"
    return "frontend" if pkg.is_file() else "unknown"


def detect_code_units(root: Path, project: str = "") -> list:
    """已有代码单元（含构建描述文件的目录，至多 3 层），附 AIDP 落点建议。"""
    root = root.resolve()
    project = project or root.name
    units = []

    def visit(d: Path, depth: int):
        if depth > 3 or d.name in SKIP_DIRS or d.name.startswith(".aidp-backup-"):
            return
        if d != root and (d.name.startswith(".") or PROTO_NAME.search(d.name)):
            return
        if any((d / f).is_file() for f in ENTRY_FILES):
            units.append(d)
            return  # 单元内部（多模块）不再下钻
        try:
            children = sorted(x for x in d.iterdir() if x.is_dir())
        except OSError:
            return
        for c in children:
            visit(c, depth + 1)

    visit(root, 0)
    out = []
    for u in units:
        rel = "." if u == root else u.relative_to(root).as_posix()
        side = _side(u)
        parts = rel.split("/")
        compliant = len(parts) == 3 and parts[0] == "code" and parts[1] in ("frontend", "backend")
        item = {"path": rel, "side": side, "compliant": compliant}
        if not compliant:
            name = project if rel == "." else u.name
            if side in ("frontend", "backend"):
                if rel == "." or name in ("frontend", "backend", "code"):
                    name = f"{project}-{'web' if side == 'frontend' else 'server'}"
                target = f"code/{side}/{name}"
                item["suggested"] = target
                item["command"] = (None if rel == "." else f"mkdir -p code/{side} && git mv {rel} {target}")
            item["note"] = ("根目录即代码单元：建议保持原位，在 memory/techContext.md「项目代码结构」写明实际路径"
                            if rel == "." else "可保持原位（在 memory/techContext.md 记录实际路径），或确认后按建议迁入")
        out.append(item)
    return out


def has_code(root: Path) -> bool:
    if detect_code_units(root):
        return True
    for name in ("code", "src", "app", "lib"):
        d = root / name
        if d.is_dir() and any(p.is_file() and p.name != ".gitkeep" for p in d.rglob("*")):
            return True
    for p in root.iterdir():
        if p.is_file() and p.suffix in SOURCE_SUFFIX:
            return True
    return False


# ── docs 非标准目录 ─────────────────────────────────────────────────────────
def scan_docs(root: Path, version: str = "{version}") -> list:
    docs = root / "docs"
    out = []
    if not docs.is_dir():
        return out
    for legacy, target in LEGACY_DOC_DIRS.items():
        if (root / legacy).exists():
            out.append({"path": legacy, "suggested": target.replace("{version}", version)})
    listed = {o["path"] for o in out}
    for child in sorted(docs.iterdir()):
        rel = f"docs/{child.name}"
        if rel in listed or child.name in STANDARD_DOC_DIRS or child.name.upper() == "README.MD":
            continue
        out.append({"path": rel, "suggested": None,
                    "note": "非 AIDP 标准目录：确认用途后归入 docs/ 对应分类，或保留原位"})
    return out


# ── 产品输入（PRD / 原型）───────────────────────────────────────────────────
def scan_inputs(root: Path) -> dict:
    prd, proto = [], []
    for p in sorted(root.iterdir()):
        if p.name.startswith("."):
            continue
        if p.is_file() and p.suffix.lower() in PRD_EXT and p.name.lower() not in PRD_EXCLUDE \
                and PRD_NAME.search(p.stem):
            prd.append(p.name)
        elif p.is_dir() and p.name not in SKIP_DIRS and p.name != "code" and PROTO_NAME.search(p.name):
            proto.append(p.name)
    return {"prd": prd, "prototype": proto}


def _proto_kind(d: Path) -> str:
    files = [p for p in d.rglob("*") if p.is_file()]
    mock = sum(1 for p in files if p.suffix.lower() in MOCKUP_EXT)
    return "mockup" if files and mock * 2 > len(files) else "code"


def place_inputs(root: Path, version: str, only=None, copy=False) -> list:
    """PRD → docs/requirements/{version}/产品提供/；原型目录 → docs/prototype/{version}/code|mockup/。"""
    found = scan_inputs(root)
    actions = []
    for name in found["prd"]:
        if only and name not in only:
            continue
        dst = f"docs/requirements/{version}/产品提供/{name}"
        if (root / dst).exists():
            actions.append({"src": name, "dst": dst, "op": "skip-exists"})
            continue
        actions.append({"src": name, "dst": dst, "op": L.move_path(root, name, dst, copy)})
    for name in found["prototype"]:
        if only and name not in only:
            continue
        dst = f"docs/prototype/{version}/{_proto_kind(root / name)}/{name}"
        if (root / dst).exists():
            actions.append({"src": name, "dst": dst, "op": "skip-exists"})
            continue
        actions.append({"src": name, "dst": dst, "op": L.move_path(root, name, dst, copy)})
    return actions


# ── 记忆文件：保全已有用户内容 ──────────────────────────────────────────────
def _demote_headings(text: str, levels: int = 2) -> str:
    out, fence = [], False
    for ln in text.splitlines():
        if ln.lstrip().startswith("```"):
            fence = not fence
        m = re.match(r"^(#{1,6})(\s.*)$", ln)
        if m and not fence:
            ln = "#" * min(6, len(m.group(1)) + levels) + m.group(2)
        out.append(ln)
    return "\n".join(out)


def merge_custom(rendered_tpl: str, bodies: dict) -> str:
    """把已有记忆文件正文并入模板「项目自定义」段（标题降两级，逐来源分节，原文一字不删）。"""
    chunks = []
    for name in ("CLAUDE.md", "AGENTS.md"):
        body = bodies.get(name, "")
        if not body.strip():
            continue
        existing_custom = L.custom_section(body) if L.looks_like_aidp_body(body) else ""
        content = existing_custom.strip() if existing_custom.strip() else body.strip()
        chunks.append(f"### 原 {name} 内容\n\n{_demote_headings(content)}\n")
    if not chunks:
        return rendered_tpl
    return rendered_tpl.rstrip("\n") + "\n\n" + "\n".join(chunks)


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="AIDP 项目扫描与已有内容保全")
    sub = ap.add_subparsers(dest="cmd")
    s1 = sub.add_parser("scan")
    s1.add_argument("root")
    s1.add_argument("--version", default="{version}")
    s1.add_argument("--json", action="store_true")
    s2 = sub.add_parser("place-inputs")
    s2.add_argument("root")
    s2.add_argument("--version", required=True)
    s2.add_argument("--only", default="", help="逗号分隔的根目录文件/目录名；缺省全部")
    s2.add_argument("--copy", action="store_true", help="复制而非移动")
    s2.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_usage(sys.stderr)
        return 2
    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"项目根不存在：{root}", file=sys.stderr)
        return 2
    if a.cmd == "scan":
        data = {"code_units": detect_code_units(root), "docs": scan_docs(root, a.version),
                "inputs": scan_inputs(root), "memory_files": sorted(L.memory_bodies(root))}
        print(json.dumps(data, ensure_ascii=False, indent=2) if a.json else json.dumps(data, ensure_ascii=False))
        return 0
    if not L.VERSION_RE.match(a.version):
        print(f"版本号格式应为 V0.1.0：{a.version}", file=sys.stderr)
        return 2
    only = {x.strip() for x in a.only.split(",") if x.strip()} or None
    acts = place_inputs(root, a.version, only, a.copy)
    if a.json:
        print(json.dumps({"actions": acts}, ensure_ascii=False, indent=2))
    else:
        for x in acts:
            print(f"  {x['op']:8} {x['src']} → {x['dst']}")
        if not acts:
            print("未检测到项目根的 PRD / 原型输入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
