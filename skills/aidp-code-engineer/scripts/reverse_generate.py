#!/usr/bin/env python3
"""反向生成架构文档：当 docs/architecture/ 下文件为空模板时，扫描代码反向生成。

用法: python3 reverse_generate.py <project_root>

★ 关键约束：
- 仅扫描真实代码目录（`docs/init/06_版本与用户目录约定.md` §2.5）：
  - 前端：code/frontend/{子项目}/；后端：code/backend/{子项目}/
  - 已有项目保留原位置的代码目录（backend/ / frontend/ / server/ / web/ / src/）同样扫描
- 严格排除 docs/prototype/（vibe coding 原型代码，技术栈不代表实际项目）
- 排除 .aidp-backup-*, node_modules/, target/, dist/, build/, .git/

扫描内容：
- 后端：pom.xml / build.gradle / requirements.txt
- 前端：package.json (排除原型代码下的 package.json)
- 数据库：docs/deployment/*/sql/**/*.sql、code/sql、sql/、db/ 下的 .sql / env/.env
- 部署：Dockerfile / docker-compose.* / nginx.conf / k8s/*.yaml

生成内容：
- docs/architecture/技术选型.md（仅当为空模板时）

仅使用 Python 标准库。
"""
import os
import re
import sys
import json
from pathlib import Path
from datetime import datetime


# 排除路径：原型代码、备份、依赖、构建产物等
EXCLUDE_PATH_PARTS = (
    "docs/prototype",      # ★ 原型代码目录：vibe coding 产物，技术栈不代表实际项目
    "docs/ui",             # 非标准原型目录
    ".aidp-backup",        # 迁移备份
    "node_modules",        # 前端依赖
    ".git",                # git 内部
    "target",              # Maven 构建产物
    "dist",                # 前端构建产物
    "build",               # 通用构建产物
)


def _excluded(path: Path) -> bool:
    """判断路径是否应该被排除。"""
    s = str(path).replace("\\", "/")
    return any(part in s for part in EXCLUDE_PATH_PARTS)


PLACEHOLDER_MARKERS = ["本文件为 AIDP 模板", "待团队补充", "由 /sprint-design 填充", "待 /sprint-design", "待填充", "（待填充）", "由 Architect Agent 填充"]


def is_template_empty(path: Path) -> bool:
    """判断架构文档是否为未填充的空模板。"""
    if not path.exists() or path.stat().st_size == 0:
        return True
    content = path.read_text(encoding="utf-8", errors="ignore")
    if len(content) < 500:
        return True
    for marker in PLACEHOLDER_MARKERS:
        if marker in content:
            return True
    return False


def scan_backend(root: Path) -> dict:
    """扫描后端项目（Maven/Gradle/Node/Python）。

    ★ 关键：仅扫描真实代码目录，不扫描 docs/prototype/ 下的原型代码。
    """
    info = {"language": None, "framework": None, "deps": []}

    # 真实代码目录候选（明确排除 docs/，避免扫到原型代码）
    code_roots = [root / "code", root / "backend", root / "server", root / "src"]

    for code_root in code_roots:
        if not code_root.exists() or _excluded(code_root):
            continue
        for pom in code_root.rglob("pom.xml"):
            if _excluded(pom):
                continue
            info["language"] = "Java"
            info["framework"] = "Maven"
            try:
                content = pom.read_text(encoding="utf-8", errors="ignore")
                if "spring-boot" in content.lower():
                    # 优先匹配 parent 版本
                    parent = re.search(
                        r"<artifactId>spring-boot-starter-parent</artifactId>\s*<version>([\d.]+)</version>",
                        content,
                        re.DOTALL,
                    )
                    if parent:
                        info["framework"] = f"Spring Boot {parent.group(1)}"
                    else:
                        sb_match = re.search(r"<spring-boot[^>]*>(\d+\.\d+\.\d+)", content)
                        info["framework"] = f"Spring Boot {sb_match.group(1) if sb_match else '?'}"
                # 提取 java.version
                jv = re.search(r"<java\.version>(\d+)</java\.version>", content)
                if jv:
                    info["java_version"] = jv.group(1)
                # 提取关键依赖
                for dep in re.finditer(r"<artifactId>([^<]+)</artifactId>", content):
                    name = dep.group(1)
                    if any(kw in name for kw in ["mybatis", "redis", "elasticsearch", "kafka", "nacos", "spring-cloud", "feign"]):
                        info["deps"].append(name)
            except Exception:
                pass
            return info

        for gradle in code_root.rglob("build.gradle"):
            if _excluded(gradle):
                continue
            info["language"] = "Java/Kotlin"
            info["framework"] = "Gradle"
            return info

        for req in code_root.rglob("requirements.txt"):
            if _excluded(req):
                continue
            info["language"] = "Python"
            info["framework"] = "pip"
            return info

    return info


def scan_frontend(root: Path) -> dict:
    """扫描前端项目。

    ★ 关键：仅扫描真实代码目录，不扫描 docs/prototype/ 下的原型代码。
    原型代码（vibe coding 产物）的技术栈往往与实际项目不一致，必须排除。
    """
    info = {"framework": None, "build_tool": None, "deps": []}

    # 真实代码目录候选（明确排除 docs/，避免扫到原型代码）
    code_roots = [root / "code", root / "frontend", root / "web"]

    for code_root in code_roots:
        if not code_root.exists() or _excluded(code_root):
            continue
        for pkg in code_root.rglob("package.json"):
            if _excluded(pkg):
                continue
            try:
                data = json.loads(pkg.read_text(encoding="utf-8", errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                if "vue" in deps:
                    info["framework"] = f"Vue {deps['vue']}"
                elif "react" in deps:
                    info["framework"] = f"React {deps['react']}"
                elif "@angular/core" in deps:
                    info["framework"] = f"Angular {deps['@angular/core']}"

                if "vite" in deps:
                    info["build_tool"] = f"Vite {deps['vite']}"
                elif "webpack" in deps:
                    info["build_tool"] = f"Webpack {deps['webpack']}"

                # 关键 UI 库
                for lib in ["element-plus", "ant-design-vue", "@arco-design/web-vue", "naive-ui", "antd", "@mui/material"]:
                    if lib in deps:
                        info["deps"].append(f"{lib} {deps[lib]}")

                if info["framework"]:
                    return info
            except Exception:
                pass

    return info


def scan_database(root: Path) -> dict:
    """扫描数据库类型。"""
    info = {"type": None, "sql_files": []}

    sql_dirs = [root / "docs" / "deployment", root / "code" / "sql", root / "sql", root / "db"]
    for sd in sql_dirs:
        if not sd.exists() or _excluded(sd):
            continue
        for sql in sd.rglob("*.sql"):
            if _excluded(sql):
                continue
            info["sql_files"].append(str(sql.relative_to(root)))
            content = sql.read_text(encoding="utf-8", errors="ignore")[:2000].upper()
            if "DM" in content[:500] or "达梦" in sql.read_text(encoding="utf-8", errors="ignore")[:500]:
                info["type"] = "DM (达梦)"
            elif "MYSQL" in content or "AUTO_INCREMENT" in content:
                info["type"] = "MySQL"
            elif "POSTGRESQL" in content or "SERIAL" in content:
                info["type"] = "PostgreSQL"

    # 从 .env 文件推断
    for env_file in [root / "env" / ".env", root / ".env"]:
        if env_file.exists():
            content = env_file.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"DM[\.\-_]", content, re.IGNORECASE):
                info["type"] = info["type"] or "DM (达梦)"
            elif "mysql" in content.lower():
                info["type"] = info["type"] or "MySQL"
            elif "postgres" in content.lower():
                info["type"] = info["type"] or "PostgreSQL"

    return info


def scan_deployment(root: Path) -> dict:
    """扫描部署配置（排除原型代码、备份目录）。"""
    info = {"docker": False, "nginx": False, "kubernetes": False}
    for p in root.rglob("Dockerfile"):
        if not _excluded(p):
            info["docker"] = True
            break
    for p in root.rglob("nginx.conf"):
        if not _excluded(p):
            info["nginx"] = True
            break
    for pattern in ["k8s/*.yaml", "kubernetes/*.yaml"]:
        for p in root.rglob(pattern):
            if not _excluded(p):
                info["kubernetes"] = True
                break
        if info["kubernetes"]:
            break
    return info


def generate_tech_selection(backend: dict, frontend: dict, db: dict, deploy: dict) -> str:
    """生成技术选型文档。"""
    lines = [
        "# 技术选型",
        "",
        f"> ⚠️ 此文件由 `aidp-code-engineer` SKILL 的 reverse_generate.py 反向扫描代码生成。",
        f"> 扫描时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "> 扫描结果作为初稿，**请人工 review 并补充缺失项**（选型理由、版本约束等）。",
        "",
        "## 技术栈总览",
        "",
        "| 层级 | 技术 | 版本 | 选型理由 | 关联 Sprint |",
        "|------|------|------|---------|-------------|",
    ]

    if frontend.get("framework"):
        lines.append(f"| 前端框架 | {frontend['framework'].split(' ')[0]} | {frontend['framework'].split(' ', 1)[-1] if ' ' in frontend['framework'] else '-'} | 待补充 | - |")
    if frontend.get("build_tool"):
        lines.append(f"| 前端构建工具 | {frontend['build_tool'].split(' ')[0]} | {frontend['build_tool'].split(' ', 1)[-1] if ' ' in frontend['build_tool'] else '-'} | 待补充 | - |")
    for d in frontend.get("deps", []):
        parts = d.split(" ", 1)
        lines.append(f"| 前端 UI 组件库 | {parts[0]} | {parts[1] if len(parts) > 1 else '-'} | 待补充 | - |")

    if backend.get("framework"):
        lines.append(f"| 后端框架 | {backend['framework'].split(' ')[0] if ' ' in backend['framework'] else backend['framework']} | {backend['framework'].split(' ', 1)[-1] if ' ' in backend['framework'] else '-'} | 待补充 | - |")
    if backend.get("java_version"):
        lines.append(f"| 运行时 | JDK | {backend['java_version']} | 待补充 | - |")
    if backend.get("language"):
        lines.append(f"| 后端语言 | {backend['language']} | - | 待补充 | - |")
    for dep in backend.get("deps", []):
        lines.append(f"| 后端依赖 | {dep} | - | 待补充 | - |")

    if db.get("type"):
        lines.append(f"| 主数据库 | {db['type']} | - | 待补充 | - |")

    if deploy.get("docker"):
        lines.append(f"| 容器化 | Docker | - | 待补充 | - |")
    if deploy.get("nginx"):
        lines.append(f"| 反向代理 | Nginx | - | 待补充 | - |")
    if deploy.get("kubernetes"):
        lines.append(f"| 容器编排 | Kubernetes | - | 待补充 | - |")

    lines.extend([
        "",
        "## 选型决策记录",
        "",
        "（由 `/sprint-design` 追加每次 Sprint 引入的新技术决策）",
        "",
        "## 变更历史",
        "",
        "| 时间 | 变更人 | 变更内容 | 关联 Sprint |",
        "|------|--------|---------|-------------|",
        f"| {datetime.now().strftime('%Y-%m-%d')} | aidp-code-engineer | 反向扫描代码自动生成初稿 | - |",
        "",
    ])

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("用法: python3 reverse_generate.py <project_root>\n\n"
              "从已有代码反向生成 docs/architecture/技术选型.md（仅当该文件仍是模板时生成）。")
        sys.exit(0 if len(sys.argv) >= 2 else 1)

    root = Path(sys.argv[1]).resolve()
    if not root.exists():
        print(f"错误: 项目根目录不存在: {root}")
        sys.exit(1)

    print(f"[reverse-gen] 项目根: {root}")
    print(f"[reverse-gen] ★ 扫描范围：仅真实代码目录（code/, backend/, frontend/, server/, web/, src/）")
    print(f"[reverse-gen] ★ 排除目录：docs/prototype/（原型代码）, .aidp-backup-*, node_modules/, target/, dist/, build/")
    print()

    arch_dir = root / "docs" / "architecture"
    if not arch_dir.exists():
        arch_dir.mkdir(parents=True, exist_ok=True)
        print(f"[reverse-gen] 创建 {arch_dir}")

    tech_doc = arch_dir / "技术选型.md"

    if not is_template_empty(tech_doc):
        print(f"[reverse-gen] {tech_doc.relative_to(root)} 已有真实内容，跳过反向生成")
        print("[reverse-gen] 如需强制重新生成，请先备份后删除该文件")
        return

    print("[reverse-gen] 扫描后端...")
    backend = scan_backend(root)
    print(f"  → {backend}")

    print("[reverse-gen] 扫描前端...")
    frontend = scan_frontend(root)
    print(f"  → {frontend}")

    print("[reverse-gen] 扫描数据库...")
    db = scan_database(root)
    print(f"  → {db}")

    print("[reverse-gen] 扫描部署...")
    deploy = scan_deployment(root)
    print(f"  → {deploy}")

    print()
    print("[reverse-gen] 生成技术选型.md ...")
    content = generate_tech_selection(backend, frontend, db, deploy)
    tech_doc.write_text(content, encoding="utf-8")
    print(f"  → 写入 {tech_doc.relative_to(root)} ({len(content)} 字节)")

    print()
    print("[reverse-gen] 完成。请人工 review 并补充选型理由。")
    print("[reverse-gen] 注：架构约束.md 和 UI规范约束.md 内容更具主观性，")
    print("           建议由 Architect/UI Agent 在 /sprint-design 阶段填充。")


if __name__ == "__main__":
    main()
