#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mirror_to_bundle.py —— 模板项目本体 → 脚手架 bundle（`assets/`）的单向镜像器。

方向只有「本体 → bundle」；bundle 是派生物，不提供反向模式。

| 源（模板项目） | 目标（skill 内） |
| :- | :- |
| `.aidp/{agents,commands,rules,flows,reference,scripts,hooks,templates,plugins}`（不含 `L.TEMPLATE_OWNED`：模板回归单测、设计目标 baseline） | `assets/aidp/<同名>` |
| `.aidp/skills/<X>`（脚手架 skill 自身在仓库根 `skills/`，天然不在此列） | `assets/aidp/skills/<X>` |
| `docs/README.md` + `docs/**/README.md`（不含 init 与版本目录）+ `docs/architecture/` 三份约束骨架 | `assets/docs/…` |
| `docs/init/*` | `assets/docs/init/` |
| 脚手架 `sources/root/*.tpl`、`sources/memory/*.md.tpl`（下游根文件与项目级 memory 模板的真源） | `assets/root/`、`assets/memory/` |
| `memory/README.md`（TEMPLATE-ONLY 块换成下游版目录树） | `assets/memory/README.md` |
| `memory/aidp-config.yaml`（project 段换成占位符、scaffold 段置空） | `assets/aidp-config.yaml.tpl` |
| `.aidp/AIDP-AGENTS.md`（经 `sync_memory_md.py` 校验） | `assets/AGENTS.md.tpl` |
| `版本变更历史.md`「当前范式版本」 | `assets/SCAFFOLD_VERSION` |
| （派生）受版本门控契约文件的 sha256 指纹 | `assets/CONTRACT_MANIFEST.json` |

可执行位随内容一起镜像（本体 +x → bundle +x）：运行包由 `runtime_layout.render_tree` 经 `shutil.copymode` 从 bundle 取模式，bundle 丢 +x 等于下游所有脚本都丢 +x。`--check` 把模式差异也算作漂移。

`assets/` 完全由本脚本派生：本体已删除的文件会从 bundle 删除，未登记文件视为孤儿（`--check` 报漂移，执行时删除）。
忽略 `__pycache__`、`*.pyc`、`.DS_Store`、任何 `config.json` / `auth.*.json` / `.env` 凭证文件。

用法：
    python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py           # 执行镜像
    python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py --check   # 干运行，有漂移 exit 1
    python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py --json

退出码：0 已一致 / 镜像完成 · 1 `--check` 发现漂移 · 2 环境错误（非模板项目、源文件结构不符）
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import scaffold_lib as L  # noqa: E402
import sync_memory_md  # noqa: E402

# 脚手架内的下游模板真源（相对 skill 目录）→ bundle 位置
SOURCES_REL = "sources"
# bundle 巡检范围（该范围内的文件必须由镜像产出）
SCAN_ROOTS = ("assets",)

MEMORY_TREE_DOWNSTREAM = """## 目录结构

```
memory/
├── README.md                （本文件）
├── aidp-config.yaml         （项目配置·人维护·入库共享）
├── projectBrief.md          （项目级）
├── productContext.md        （项目级）
├── systemPatterns.md        （项目级）
├── techContext.md           （项目级）
├── databaseBaseline.md      （项目级）
├── .sprint-autopilot-baseline.json       （运行时状态·入库共享）
├── .sprint-autopilot-baseline.json.lock  （并发写锁·空文件，已 gitignore）
├── _facts/                  （机器可读事实清单，由命令自动维护）
│   └── code-inventory.json
└── {version}/               （版本目录，如 V1.0.0/）
    └── {user}/              （开发者目录，取 git config user.name）
        ├── activeContext.md
        ├── progress.md
        └── sprints/         （Sprint 归档）
```

> ℹ️ **迭代级 memory 文件按需生成、不预建**：`{version}/{user}/` 下脚手架只铺目录骨架——`activeContext.md` 与 `progress.md` 由 `/sprint-start`、`/memory-sync` **首次运行时自动创建**（不预置空文件，避免空占位被误读成"已有状态"）。`sprints/sprint-{NNN}.md` 则由 `/sprint-close` 归档时写入。
"""

_BLOCK_RE = re.compile(
    r"^<!--\s*TEMPLATE-ONLY:BEGIN\s+(\w+)\s*-->\n.*?^<!--\s*TEMPLATE-ONLY:END\s*-->\n", re.M | re.S)


class SourceShapeError(Exception):
    pass


def render_memory_readme(text: str) -> str:
    blocks = {"MEMORY_TREE": MEMORY_TREE_DOWNSTREAM}
    seen = set()

    def _sub(m):
        key = m.group(1)
        if key not in blocks:
            raise SourceShapeError(f"memory/README.md 出现未登记的 TEMPLATE-ONLY 块 `{key}`")
        seen.add(key)
        return blocks[key]

    out = _BLOCK_RE.sub(_sub, text)
    if seen != set(blocks):
        raise SourceShapeError(f"memory/README.md 缺少 TEMPLATE-ONLY 块：{sorted(set(blocks) - seen)}")
    for d in sorted(set(re.findall(r"`(_[A-Za-z0-9_]+)/", text))):
        if d + "/" not in MEMORY_TREE_DOWNSTREAM:
            raise SourceShapeError(f"memory/README.md 提到 `{d}/`，下游目录树未列出，请补进 MEMORY_TREE_DOWNSTREAM")
    return out


def render_config_tpl(text: str) -> str:
    """memory/aidp-config.yaml → 下游模板：project 段取占位符，scaffold 段清空。"""
    lines = text.splitlines()
    out, sec = [], None
    hit = {"name": False, "name_cn": False}
    for ln in lines:
        if ln and ln[:1] not in (" ", "\t", "#"):
            sec = ln.split(":", 1)[0].strip()
        if sec == "project":
            m = re.match(r"^(\s+)(name|name_cn)\s*:", ln)
            if m:
                val = "{{project}}" if m.group(2) == "name" else '"{{project_cn}}"'
                out.append(f"{m.group(1)}{m.group(2)}: {val}")
                hit[m.group(2)] = True
                continue
        if sec == "scaffold":
            m = re.match(r"^(\s+)(version|pending)\s*:", ln)
            if m:
                out.append(f"{m.group(1)}{m.group(2)}: null")
                continue
        out.append(ln)
    if not all(hit.values()):
        raise SourceShapeError("memory/aidp-config.yaml 缺 project.name / project.name_cn")
    return "\n".join(out) + "\n"


def docs_readme_sources(root: Path):
    """[(本体路径, bundle 相对路径)]：docs 结构性 README + architecture 骨架。"""
    pairs = []
    docs = root / "docs"
    if not docs.is_dir():
        return pairs
    for f in sorted(docs.rglob("README.md")):
        rel = f.relative_to(docs)
        if rel.parts[0] == "init" or any(re.match(r"^V\d", p) for p in rel.parts):
            continue
        pairs.append((f, f"assets/docs/{rel.as_posix()}"))
    for name in L.ARCH_DOCS:
        f = docs / "architecture" / name
        if f.is_file():
            pairs.append((f, f"assets/docs/architecture/{name}"))
    return pairs


def build_desired(root: Path, skill_dir: Path) -> dict:
    """{skill 内相对路径: 期望字节}；可执行位另由 `desired_exec()` 单独推导。"""
    want = {}
    src_aidp = root / ".aidp"
    for d in L.MIRROR_DIRS:
        for rel, p in L.iter_files(src_aidp / d):
            if L.is_template_owned(f"{d}/{rel}"):
                continue
            want[f"assets/aidp/{d}/{L.bundle_mask(rel)}"] = p.read_bytes()
    skills = src_aidp / "skills"
    if skills.is_dir():
        for s in sorted(x for x in skills.iterdir() if x.is_dir() and x.name != L.SKILL_NAME):
            for rel, p in L.iter_files(s):
                want[f"assets/aidp/skills/{s.name}/{L.bundle_mask(rel)}"] = p.read_bytes()
    for src, dst in docs_readme_sources(root):
        want[dst] = src.read_bytes()
    for rel, p in L.iter_files(root / "docs/init"):
        want[f"assets/docs/init/{rel}"] = p.read_bytes()
    sources = skill_dir / SOURCES_REL
    for sub in ("root", "memory"):
        for rel, p in L.iter_files(sources / sub):
            want[f"assets/{sub}/{rel}"] = p.read_bytes()
    missing = [f"{SOURCES_REL}/memory/{tpl}" for tpl, _ in L.MEMORY_TEMPLATES
               if not (sources / "memory" / tpl).is_file()]
    missing += [f"{SOURCES_REL}/root/{n}" for n in ("README.md.tpl", "gitignore.tpl", "env.tpl")
                if not (sources / "root" / n).is_file()]
    if missing:
        raise SourceShapeError(f"脚手架下游模板真源缺失：{missing}")

    want["assets/memory/README.md"] = render_memory_readme(
        (root / "memory/README.md").read_text(encoding="utf-8")).encode("utf-8")
    want[L.CONFIG_TPL_REL] = render_config_tpl(
        (root / "memory/aidp-config.yaml").read_text(encoding="utf-8")).encode("utf-8")
    want[L.MEMORY_TPL_REL] = sync_memory_md.build(root).encode("utf-8")

    version = L.changelog_version(root)
    if not version:
        raise SourceShapeError(f"{L.CHANGELOG} 缺「当前范式版本」标记 `**AIDP Vx.y.z**`")
    want[L.VERSION_REL] = (version + "\n").encode("utf-8")

    files = {}
    for rel in sorted(want):
        if not rel.startswith("assets/aidp/"):
            continue
        # ★ 指纹键用**安装路径**、不用 bundle 遮名：键一变，同版本下游会被整批判成契约漂移。
        sub = L.bundle_unmask(rel[len("assets/aidp/"):])
        if sub.split("/", 1)[0] in L.GATED_DIRS:
            files[sub] = L.sha256(want[rel])
    manifest = {"_doc": "受版本门控的契约文件指纹（相对 .aidp/）；由 mirror_to_bundle.py 生成。",
                "scaffold_version": version, "files": files}
    want[L.MANIFEST_REL] = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return want


def desired_exec(root: Path, skill_dir: Path) -> set:
    """应带可执行位的 bundle 相对路径集合（口径 = 本体源文件自身的 +x）。

    ⛔ 不能只镜像内容不镜像模式：`runtime_layout.render_tree` 用 `shutil.copymode(source, target)`
    从 bundle 取模式铺运行包，bundle 全是 644 就意味着**下游运行包里所有脚本都没有 +x**。
    `aidp_scheduler.py` 生成的 Windows schtasks 定时任务是 `bash -lc "… AIDP_HOME/scripts/agent_loop.sh --once …"`，
    直接执行该文件 —— 没有 +x 就是 Permission denied，7×24 链路起不来。
    """
    execs = set()
    src_aidp = root / ".aidp"
    for d in L.MIRROR_DIRS:
        for rel, p in L.iter_files(src_aidp / d):
            if L.is_template_owned(f"{d}/{rel}"):
                continue
            if p.stat().st_mode & 0o111:
                execs.add(f"assets/aidp/{d}/{L.bundle_mask(rel)}")
    skills = src_aidp / "skills"
    if skills.is_dir():
        for sk in sorted(x for x in skills.iterdir() if x.is_dir() and x.name != L.SKILL_NAME):
            for rel, p in L.iter_files(sk):
                if p.stat().st_mode & 0o111:
                    execs.add(f"assets/aidp/skills/{sk.name}/{L.bundle_mask(rel)}")
    return execs


def _is_exec(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o111)


def existing_files(skill_dir: Path) -> set:
    out = set()
    for top in SCAN_ROOTS:
        base = skill_dir / top
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if p.is_file() or p.is_symlink():
                out.add(p.relative_to(skill_dir).as_posix())
    return out


def plan(root: Path, skill_dir: Path) -> dict:
    want = build_desired(root, skill_dir)
    execs = desired_exec(root, skill_dir)
    have = existing_files(skill_dir)
    create, update, delete = [], [], []
    for rel, data in sorted(want.items()):
        p = skill_dir / rel
        if rel not in have:
            create.append(rel)
        elif p.is_symlink() or p.read_bytes() != data or _is_exec(p) != (rel in execs):
            update.append(rel)          # ★ 模式差异也是漂移：只比字节则 +x 丢了永远检不出来
    for rel in sorted(have - set(want)):
        delete.append(rel)
    return {"want": want, "execs": execs, "create": create, "update": update, "delete": delete}


def apply(skill_dir: Path, pl: dict):
    for rel in pl["create"] + pl["update"]:
        p = skill_dir / rel
        if p.is_symlink():
            p.unlink()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(pl["want"][rel])       # 只写内容、不带 mtime，避免 git stat 快速路径漏判
        p.chmod(0o755 if rel in pl["execs"] else 0o644)
    for rel in pl["delete"]:
        (skill_dir / rel).unlink()
    for top in SCAN_ROOTS:                   # 清空目录
        base = skill_dir / top
        if base.is_dir():
            for d in sorted((x for x in base.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
                try:
                    d.rmdir()
                except OSError:
                    pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="模板项目本体 → 脚手架 bundle 单向镜像")
    ap.add_argument("--root", default=None, help="模板项目根（缺省按 skill 位置推断）")
    ap.add_argument("--check", action="store_true", help="干运行，有漂移 exit 1")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    skill_dir = HERE.parent
    root = Path(a.root).resolve() if a.root else skill_dir.parents[1]
    if not ((root / ".aidp").is_dir() and (root / L.PARADIGM_MEMORY_REL).is_file()
            and (root / "skills" / skill_dir.name).resolve() == skill_dir.resolve()):
        print(f"⛔ {root} 不是本 skill 所在的模板项目根", file=sys.stderr)
        return 2
    try:
        pl = plan(root, skill_dir)
    except (OSError, SourceShapeError, sync_memory_md.TemplateShapeError) as e:
        print(f"⛔ {e}", file=sys.stderr)
        return 2
    drift = bool(pl["create"] or pl["update"] or pl["delete"])
    if drift and not a.check:
        apply(skill_dir, pl)
    summary = {"check": a.check, "drift": drift, "files": len(pl["want"]),
               "create": pl["create"], "update": pl["update"], "delete": pl["delete"]}
    if a.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        verb = "待" if a.check else "已"
        if not drift:
            print(f"✅ bundle 与本体一致（{len(pl['want'])} 个派生文件）")
        else:
            print(f"{'❌' if a.check else '✅'} bundle {verb}同步：新增 {len(pl['create'])} · "
                  f"更新 {len(pl['update'])} · 删除 {len(pl['delete'])}")
            for tag, key in (("+", "create"), ("~", "update"), ("-", "delete")):
                for rel in pl[key][:30]:
                    print(f"  {tag} {rel}")
                if len(pl[key]) > 30:
                    print(f"  {tag} …（另 {len(pl[key]) - 30} 个）")
            if a.check:
                print("→ 跑 `python3 skills/aidp-code-engineer/scripts/mirror_to_bundle.py` 修复")
    return 1 if (a.check and drift) else 0


if __name__ == "__main__":
    sys.exit(main())
