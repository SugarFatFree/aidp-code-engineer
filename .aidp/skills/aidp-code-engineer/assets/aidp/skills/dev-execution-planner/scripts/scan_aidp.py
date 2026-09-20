#!/usr/bin/env python3
"""
AIDP 命令与范式文档扫描脚本

用法:
  python scan_aidp.py [项目根目录] [--json]

扫描项目中的 AIDP 配置、命令和范式文档，输出可用命令清单。

扫描位置:
  1. .aidp/ 目录或 .aidp.yml、aidp.json 配置文件
  2. 项目根目录及 docs/、doc/、.aidp/ 下的 AIDP*.md 文档
  3. package.json 的 scripts 字段
  4. Makefile / justfile / taskfile.yml 中定义的命令
  5. pom.xml 的 plugin 配置
  6. 项目 README 中的"开发工具"/"代码生成"/"脚手架"章节

跨平台支持: Linux / macOS / Windows (Python 3.6+)
"""

import json
import re
import sys
from pathlib import Path


def scan_aidp_config(root: Path) -> list:
    """扫描 .aidp/ 目录和配置文件"""
    results = []

    # .aidp/ 目录
    aidp_dir = root / '.aidp'
    if aidp_dir.is_dir():
        results.append({
            "source": str(aidp_dir),
            "type": "aidp_directory",
            "commands": [],
            "description": ".aidp/ 目录存在"
        })
        for f in aidp_dir.iterdir():
            if f.is_file():
                results[-1]["commands"].append(str(f.name))

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


def scan_aidp_docs(root: Path) -> list:
    """扫描 AIDP*.md 文档"""
    results = []
    search_dirs = [root, root / 'docs', root / 'doc', root / '.aidp']

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


def run_scan(root: Path, output_json=False):
    """执行全部扫描"""
    all_results = []

    scanners = [
        ("AIDP 配置", scan_aidp_config),
        ("AIDP 范式文档", scan_aidp_docs),
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

    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]

    output_json = '--json' in flags
    root = Path(args[0]) if args else Path('.')

    # ⚠️ exists() 与 is_dir() 必须分开判(全仓退出码约定②):合并写会把「路径根本不存在」
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

    run_scan(root, output_json=output_json)


if __name__ == "__main__":
    main()
