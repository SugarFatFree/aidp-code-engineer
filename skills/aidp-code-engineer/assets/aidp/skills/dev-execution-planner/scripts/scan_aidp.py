#!/usr/bin/env python3
"""
AIDP 命令与范式文档扫描脚本

用法:
  python scan_aidp.py [项目根目录] [--json] [--aidp-home <目录>]

参数:
  --aidp-home <目录>  显式指定 AIDP 运行根(AIDP_HOME)。相对路径按「项目根目录」解析;
                     指定了但不存在 / 不是目录 → exit 2(入参错),⛔ 不回落自动识别。

扫描项目中的 AIDP 配置、命令和范式文档，输出可用命令清单。

AIDP_HOME(AIDP 运行根)识别顺序(--json 的 aidp_home_source 给出命中的是哪一级):
  1. --aidp-home 显式入参                                         → "explicit"
  2. 环境变量 AIDP_HOME(非空;相对路径按项目根解析)                  → "env"
     设了却不是目录 → exit 2,⛔ 同样不回落(否则写错的环境变量会静默扫到别处)
  3. 脚本自身安装位置:本脚本位于 <项目根>/<运行根>/skills/dev-execution-planner/scripts/
     时取该 <运行根>                                               → "install"
  4. 候选 .aidp(旧兼容名)/.claude/.agents/.codex/.dsh 中第一个**含 AIDP 特征**的目录
     (特征 = 有 commands/ 或 skills/ 子目录,或直接含 AIDP*.md)    → "auto-feature"
  5. 以上都没有 → 候选中第一个实际存在的目录                         → "auto-exists"
  都不存在 → 不产出 AIDP 目录条目、也不扫该目录下的 AIDP*.md,其余扫描照常,exit 0
  (aidp_home=null、aidp_home_source="none")。
  ⚠️ 第 4 级不可省:只按「存在」取第一个时,一个只放了 settings.json 的 .claude 会抢在
     真正装了命令的 .agents 前面,扫到的是空壳、看着却正常。

AIDP 目录条目只列 <运行根>/commands/ 下的 *.md(相对 commands/ 的路径,含子目录),
⛔ 不列 settings*.json / CLAUDE.md 这类运行根里的配置文件(它们不是命令)。

扫描位置:
  1. AIDP_HOME/ 目录或 .aidp.yml、aidp.json 配置文件
  2. 项目根目录及 docs/、doc/、AIDP_HOME/ 下的 AIDP*.md 文档
  3. package.json 的 scripts 字段
  4. Makefile / justfile / taskfile.yml 中定义的命令
  5. pom.xml 的 plugin 配置
  6. 项目 README 中的"开发工具"/"代码生成"/"脚手架"章节

跨平台支持: Linux / macOS / Windows (Python 3.6+)
"""

import json
import os
import re
import sys
from pathlib import Path

# AIDP_HOME 自动识别候选(第 4/5 级按此顺序)。
# ⚠️ ".aidp"(旧兼容名)必须排第一:旧版只扫这一个目录名,排到后面会让同时有它与 .claude
#    的项目改扫 .claude,缺省输出随之改变。其后才是各 Agent 的运行根。
AIDP_HOME_CANDIDATES = ('.aidp', '.claude', '.agents', '.codex', '.dsh')
NON_COMMAND_NAMES = ('CLAUDE.md',)


def _abs(p) -> str:
    """词法绝对路径(⛔ 不用 resolve():软链安装时会把运行根解析到别处)。"""
    return os.path.normcase(os.path.abspath(str(p)))


def has_aidp_feature(home: Path) -> bool:
    """运行根是否含 AIDP 特征:commands/ 或 skills/ 子目录,或直接含 AIDP*.md。"""
    if not home.is_dir():
        return False
    if (home / 'commands').is_dir() or (home / 'skills').is_dir():
        return True
    try:
        return any(f.is_file() and f.name.upper().startswith('AIDP') and f.suffix.lower() == '.md'
                   for f in home.iterdir())
    except OSError:
        return False


def install_home(root: Path, script_path=None):
    """脚本位于 <root>/<运行根>/skills/<skill>/scripts/scan_aidp.py 时返回 <root>/<运行根>。"""
    sp = Path(os.path.abspath(str(script_path or __file__)))
    parts = sp.parents
    if len(parts) < 5:
        return None
    skills_dir, home, proj = parts[2], parts[3], parts[4]
    if skills_dir.name != 'skills' or not home.name:
        return None
    if _abs(proj) != _abs(root):
        return None
    return root / home.name


def resolve_aidp_home(root: Path, override=None, env=None, script_path=None):
    """返回 (AIDP_HOME 路径或 None, 来源)。来源 ∈ explicit/env/install/auto-feature/auto-exists/none。

    explicit/env 指定了却不存在属入参错,由 main() 判 exit 2,
    ⛔ 不得静默改用自动识别结果(那会让「手滑写错路径」扫到另一个目录而看着正常)。
    """
    def _abs_under_root(v):
        h = Path(v)
        return h if h.is_absolute() else root / h

    if override is not None:
        return _abs_under_root(override), "explicit"
    if env is None:
        env = os.environ.get('AIDP_HOME', '')
    if env:
        return _abs_under_root(env), "env"
    ih = install_home(root, script_path)
    if ih is not None and ih.is_dir():
        return ih, "install"
    for name in AIDP_HOME_CANDIDATES:
        cand = root / name
        if has_aidp_feature(cand):
            return cand, "auto-feature"
    for name in AIDP_HOME_CANDIDATES:
        cand = root / name
        if cand.is_dir():
            return cand, "auto-exists"
    return None, "none"


def list_commands(home: Path) -> list:
    """列 <home>/commands/ 下的 *.md(相对 commands/,含子目录),排除配置文件。"""
    cmd_dir = home / 'commands'
    if not cmd_dir.is_dir():
        return []
    out = []
    for f in sorted(cmd_dir.rglob('*.md')):
        if not f.is_file() or f.name in NON_COMMAND_NAMES:
            continue
        out.append(f.relative_to(cmd_dir).as_posix())
    return out


def scan_aidp_config(root: Path, aidp_home=None) -> list:
    """扫描 AIDP_HOME/ 目录和配置文件"""
    results = []

    # AIDP_HOME/ 目录(由 resolve_aidp_home 识别;None = 都不存在)
    aidp_dir = aidp_home
    if aidp_dir is not None and aidp_dir.is_dir():
        results.append({
            "source": str(aidp_dir),
            "type": "aidp_directory",
            "commands": [],
            "description": f"{aidp_dir.name}/ 目录存在"
        })
        results[-1]["commands"].extend(list_commands(aidp_dir))

    # .aidp.yml
    for cfg_name in ['.aidp.yml', '.aidp.yaml', 'aidp.json']:
        cfg = root / cfg_name
        if cfg.exists():
            try:
                content = cfg.read_text(encoding='utf-8', errors='ignore')
                commands = re.findall(r'(?:command|cmd|script|run)[\s:]+["\']?([^"\'}\n]+)', content)
                results.append({
                    "source": str(cfg),
                    "type": "aidp_config",
                    "commands": commands,
                    "description": f"AIDP 配置文件: {cfg_name}"
                })
            except (OSError, PermissionError):
                pass

    return results


def scan_aidp_docs(root: Path, aidp_home=None) -> list:
    """扫描 AIDP*.md 文档"""
    results = []
    search_dirs = [root, root / 'docs', root / 'doc']
    if aidp_home is not None:
        search_dirs.append(aidp_home)

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for f in search_dir.iterdir():
            if f.is_file() and f.name.upper().startswith('AIDP') and f.suffix.lower() == '.md':
                try:
                    content = f.read_text(encoding='utf-8', errors='ignore')
                    # 提取命令
                    commands = re.findall(r'`(aidp\s+\S+[^`]*)`', content)
                    # 提取代码块中的命令
                    code_cmds = re.findall(r'(?:^|\n)\s*(?:\$\s+)?(aidp\s+\S+.*?)(?:\n|$)', content)
                    all_cmds = list(set(commands + code_cmds))

                    # 提取章节标题作为范式摘要
                    headings = re.findall(r'^#{1,3}\s+(.+)$', content, re.MULTILINE)

                    results.append({
                        "source": str(f),
                        "type": "aidp_document",
                        "commands": all_cmds[:20],
                        "headings": headings[:15],
                        "description": f"AIDP 范式文档: {f.name}"
                    })
                except (OSError, PermissionError):
                    pass

    return results


def scan_package_json(root: Path) -> list:
    """扫描 package.json scripts"""
    results = []
    pkg = root / 'package.json'
    if not pkg.exists():
        return results

    try:
        content = pkg.read_text(encoding='utf-8', errors='ignore')
        data = json.loads(content)
        scripts = data.get('scripts', {})
        if scripts:
            # 筛选可能是代码生成/构建相关的脚本
            gen_keywords = ['gen', 'generate', 'scaffold', 'create', 'init', 'build', 'migrate', 'seed']
            relevant = {k: v for k, v in scripts.items()
                       if any(kw in k.lower() for kw in gen_keywords)}
            results.append({
                "source": str(pkg),
                "type": "package_json_scripts",
                "commands": [f"pnpm {k}" for k in relevant.keys()] or [f"pnpm {k}" for k in list(scripts.keys())[:10]],
                "all_scripts": list(scripts.keys()),
                "description": f"package.json scripts ({len(scripts)} 个)"
            })
    except (OSError, json.JSONDecodeError):
        pass

    return results


def scan_makefile(root: Path) -> list:
    """扫描 Makefile / justfile / taskfile.yml"""
    results = []

    for fname in ['Makefile', 'makefile', 'GNUmakefile', 'justfile', 'Justfile']:
        f = root / fname
        if f.exists():
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                # 提取 target 名称
                targets = re.findall(r'^([a-zA-Z_][\w-]*)\s*:', content, re.MULTILINE)
                targets = [t for t in targets if not t.startswith('.')]
                tool = 'just' if 'just' in fname.lower() else 'make'
                results.append({
                    "source": str(f),
                    "type": "makefile",
                    "commands": [f"{tool} {t}" for t in targets[:20]],
                    "description": f"{fname} ({len(targets)} 个 target)"
                })
            except (OSError, PermissionError):
                pass

    # taskfile.yml
    for fname in ['taskfile.yml', 'Taskfile.yml', 'taskfile.yaml']:
        f = root / fname
        if f.exists():
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                tasks = re.findall(r'^\s+(\w[\w-]*):', content, re.MULTILINE)
                results.append({
                    "source": str(f),
                    "type": "taskfile",
                    "commands": [f"task {t}" for t in tasks[:20]],
                    "description": f"{fname} ({len(tasks)} 个 task)"
                })
            except (OSError, PermissionError):
                pass

    return results


def scan_pom_xml(root: Path) -> list:
    """扫描 pom.xml plugin 配置"""
    results = []
    pom = root / 'pom.xml'
    if not pom.exists():
        return results

    try:
        content = pom.read_text(encoding='utf-8', errors='ignore')
        plugins = re.findall(r'<artifactId>([\w-]*(?:generator|plugin|maven)[\w-]*)</artifactId>', content)
        if plugins:
            results.append({
                "source": str(pom),
                "type": "maven_plugins",
                "commands": [f"mvn {p}:generate" for p in plugins],
                "plugins": plugins,
                "description": f"pom.xml plugins ({len(plugins)} 个)"
            })
    except (OSError, PermissionError):
        pass

    return results


def scan_readme(root: Path) -> list:
    """扫描 README 中的开发工具/代码生成章节"""
    results = []
    for fname in ['README.md', 'readme.md', 'README.MD']:
        f = root / fname
        if f.exists():
            try:
                content = f.read_text(encoding='utf-8', errors='ignore')
                keywords = ['开发工具', '代码生成', '脚手架', 'scaffold', 'code gen', 'development', '快速开始']
                relevant_sections = []
                for kw in keywords:
                    pattern = rf'^#{{1,3}}\s+.*{re.escape(kw)}.*$'
                    matches = re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE)
                    for m in matches:
                        section_start = m.end()
                        next_heading = re.search(r'^#{1,3}\s+', content[section_start:], re.MULTILINE)
                        section_end = section_start + next_heading.start() if next_heading else len(content)
                        section_text = content[section_start:section_end]
                        cmds = re.findall(r'```(?:bash|sh|shell)?\n(.*?)```', section_text, re.DOTALL)
                        for cmd_block in cmds:
                            for line in cmd_block.strip().splitlines():
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    relevant_sections.append(line)

                if relevant_sections:
                    results.append({
                        "source": str(f),
                        "type": "readme",
                        "commands": relevant_sections[:15],
                        "description": "README 中的开发命令"
                    })
            except (OSError, PermissionError):
                pass
            break

    return results


def run_scan(root: Path, output_json=False, aidp_home=None, aidp_home_source="none"):
    """执行全部扫描"""
    all_results = []

    scanners = [
        ("AIDP 配置", lambda r: scan_aidp_config(r, aidp_home)),
        ("AIDP 范式文档", lambda r: scan_aidp_docs(r, aidp_home)),
        ("package.json scripts", scan_package_json),
        ("Makefile/justfile/taskfile", scan_makefile),
        ("Maven plugins", scan_pom_xml),
        ("README 开发命令", scan_readme),
    ]

    for name, scanner in scanners:
        results = scanner(root)
        all_results.extend(results)

    all_commands = []
    for r in all_results:
        for cmd in r.get("commands", []):
            all_commands.append({"command": cmd, "source": r["source"], "type": r["type"]})

    if output_json:
        output = {
            "project_root": str(root),
            "aidp_home": str(aidp_home) if aidp_home is not None else None,
            "aidp_home_source": aidp_home_source,
            "total_sources": len(all_results),
            "total_commands": len(all_commands),
            "sources": all_results,
            "commands_summary": all_commands
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print("=" * 60)
        print("AIDP 命令与范式文档扫描报告")
        print("=" * 60)
        print(f"项目根目录: {root}")
        print(f"AIDP 运行根: {aidp_home if aidp_home is not None else '(未识别)'}  (来源: {aidp_home_source})")
        print()

        if not all_results:
            print("未发现任何 AIDP 命令、范式文档或脚手架工具。")
            print("将使用 Claude Code Skill/Plugin > 通用工具 > Shell 的优先级。")
        else:
            for r in all_results:
                print(f"【{r['type']}】{r['description']}")
                print(f"  来源: {r['source']}")
                if r.get("commands"):
                    print("  命令:")
                    for cmd in r["commands"][:8]:
                        print(f"    - {cmd}")
                    if len(r["commands"]) > 8:
                        print(f"    ... 还有 {len(r['commands']) - 8} 个")
                if r.get("headings"):
                    print("  章节:")
                    for h in r["headings"][:5]:
                        print(f"    - {h}")
                print()

            print("-" * 60)
            print(f"汇总: 发现 {len(all_results)} 个来源, 共 {len(all_commands)} 个可用命令")
            print()
            print("可用 AIDP 命令清单:")
            for cmd_info in all_commands[:20]:
                src_name = Path(cmd_info["source"]).name
                print(f"  - {cmd_info['command']}  (来源: {src_name})")
            if len(all_commands) > 20:
                print(f"  ... 还有 {len(all_commands) - 20} 个")

        print("=" * 60)

    sys.exit(0)


def main():
    if '-h' in sys.argv[1:] or '--help' in sys.argv[1:]:
        print(__doc__)
        sys.exit(0)

    argv = sys.argv[1:]
    output_json = '--json' in argv
    aidp_home_arg = None
    args = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == '--aidp-home':
            # ⚠️ 必须吃掉后面那个值,否则它会被当成「项目根目录」位置参数
            if i + 1 >= len(argv) or argv[i + 1].startswith('--'):
                msg = "错误: --aidp-home 需要一个目录值"
                print(json.dumps({"error": msg}, ensure_ascii=False) if output_json else msg)
                sys.exit(2)
            aidp_home_arg = argv[i + 1]
            i += 2
            continue
        if a.startswith('--aidp-home='):
            aidp_home_arg = a.split('=', 1)[1]
            if not aidp_home_arg:
                msg = "错误: --aidp-home 需要一个目录值"
                print(json.dumps({"error": msg}, ensure_ascii=False) if output_json else msg)
                sys.exit(2)
        elif not a.startswith('--'):
            args.append(a)
        i += 1

    root = Path(args[0]) if args else Path('.')

    # ⚠️ exists() 与 is_dir() 必须分开判(统一退出码约定②):合并写会把「路径根本不存在」
    #    与「传的是个文件」混成同一句「目录不存在」,报错文案与事实相反、排错方向被带偏。
    if not root.exists():
        msg = f"错误: 路径不存在 - {root}"
    elif not root.is_dir():
        msg = f"错误: 需要传目录,但传入的是文件 - {root}"
    else:
        msg = None
    if msg is not None:
        if output_json:
            print(json.dumps({"error": msg}, ensure_ascii=False))
        else:
            print(msg)
        sys.exit(2)  # 入参错(路径不存在),非产物违规

    aidp_home, source = resolve_aidp_home(root, aidp_home_arg)
    if source in ("explicit", "env") and not aidp_home.is_dir():
        who = "--aidp-home" if source == "explicit" else "环境变量 AIDP_HOME"
        msg = f"错误: {who} 指定的目录不存在或不是目录 - {aidp_home}"
        print(json.dumps({"error": msg}, ensure_ascii=False) if output_json else msg)
        sys.exit(2)  # 显式入参错,⛔ 不回落自动识别

    run_scan(root, output_json=output_json, aidp_home=aidp_home, aidp_home_source=source)


if __name__ == "__main__":
    main()
