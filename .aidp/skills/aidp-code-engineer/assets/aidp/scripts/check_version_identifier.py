#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_version_identifier.py — 「发布版本 ↔ 代码内自报版本」对齐检查（脚手架契约脚本）。

## 为什么需要本脚本

`/version` 发布流程原本覆盖了关 Sprint / 版本日志 / 部署产物整理 / 文档收敛 / 打 tag，
**唯独没有一步检查「代码里自报的版本号」是否等于本次发布版本**。于是会出现：

    tag = v0.3.0，但 /health 返回 {"service":"demo-service","version":"0.2.0"}

运维/测试据 `/health` 判断线上版本 → 误判。发布完成后再改就得走 bugfix + 重新部署，
所以**发布期是唯一能兜住它的环节**（同类护栏：SQL 版本落位巡检）。实际项目中出现过此类回流。

## 扫描落点（取到即比对，扫不到任何落点 → 不适用、不误报）

| 类别 | 落点 |
| :- | :- |
| 代码常量 | `*_VERSION`（`SERVICE_VERSION` / `APP_VERSION` / `BUILD_VERSION` …）赋值为 semver 字面量 |
| 构建描述符 | `pom.xml` 自身 `<version>`、`build.gradle(.kts)` 的 `version =`、`package.json` `"version"`、`Cargo.toml`、`pyproject.toml` |
| 运行时配置 | `application.y(a)ml` 的 `info.app.version` / `app.version` / `spring.application.version` |
| 容器镜像 | `Dockerfile` / `Containerfile` 的 `LABEL version` / `LABEL org.opencontainers.image.version`、`ARG`/`ENV APP_VERSION` 等、`COPY`/`ADD` 产物名内嵌版本（`app-0.2.0.jar`）|

## 判定口径

- **归一化**：去掉前导 `V`/`v`、去掉 `-SNAPSHOT`/`-RELEASE` 后缀后逐字比较（`V0.3.0` ↔ `0.3.0` 视为一致）。
- **占位值豁免**：`0.0.0` / `${...}` / `@...@`（构建期替换占位）→ 记 `placeholder`，不算不一致。
- **非制品版本豁免**：`API_VERSION` / `SCHEMA_VERSION` / `JAVA_VERSION` 等**协议 / 依赖 / 工具链**版本
  常量走 deny-list 排除——它们与"本制品自报版本"无关，纳入只会制造噪音。
- **继承版本不算落点**：`pom.xml` 只取**自身直接子节点** `<version>`；只有 `<parent><version>` 的模块
  属继承、不自报，跳过。
- **★ 第三方代码不算落点**（写回时这条从"降噪"升级为"防破坏"）：① 对象属性赋值 `a.VERSION="3.4.1"`
  是第三方 JS 库写法、不是本应用自报；② `*.min.js` / `*.bundle.js` 等压缩产物整文件跳过；
  ③ `bower_components` / `third_party` / `site-packages` 等第三方落地目录不下钻；
  ④ **vendored 进来的整个第三方工程**（连 `pom.xml`/`package.json` 一起拷进来，长得和自家子模块
  一模一样、启发式猜不准）由项目在根目录 `.aidp-version-ignore` 里逐条声明（每行一个 glob，
  `#` 注释），或用 `--exclude <glob>` 临时传入。真实回流：本仓 `adminlte/bootstrap.min.js`
  一次误报 11 处、`xxl-job/pom.xml`（第三方 3.1.0）被当成自家模块。
- **★ Dockerfile 只认白名单**：容器文件里**基础镜像 / 工具链 / 组件版本满天飞**
  （`FROM ...jre-noble:17.0.20_8`、`ARG BASE_IMAGE=…`、`ARG NGINX_VERSION=1.21.6`、
  `ENV JAVA_VERSION 17.0.2`），宽匹配写回 = 拉错基础镜像 / 构建直接失败。故 `LABEL` 键与
  `ARG`/`ENV` 变量名都走白名单，`FROM` 行永不产生落点，通配写法 `app-*.jar` 天然不匹配。
  裸 `ARG VERSION=` 更常指被装组件的版本 → **算落点照常报告，但归 `runtime-config`
  需人复核档、不进默认自动改档**（既不漏报也不误改）。

## 写回（`--apply`）：把落点同步改成目标版本

只检查不改，等于每次 bump 版本号都要人手动去改 `pom.xml` / `package.json`——漏改就是上面那个
`/health` 误判。故本脚本同时是**写回器**：`--apply` 把 `mismatched[]` 逐处改成目标版本。

- **保后缀、剥前缀**：只换 semver 主体，后缀 `-SNAPSHOT`/`-RELEASE` 原样保留
  （`0.2.0-SNAPSHOT` → `0.3.0-SNAPSHOT`，Maven 开发期惯例不被破坏）；**`V`/`v` 前缀一律剥掉**
  （`V0.11.2` → `0.12.0`）——匹配时三种形态都兼容（`V0.11.2` / `v0.11.2` / `0.11.2`），
  但写回统一归一到**纯 semver**：前缀是 AIDP 文档与 git tag 的写法，Maven `<version>`、
  npm `"version"`、Cargo、OCI `org.opencontainers.image.version` 带 `V` 不规范甚至非法。
- **不重排文件**：全部走**文本级定点替换**（不用 `ET.write` / `json.dumps` 回写），
  注释、缩进、键序一律不动。
- **`--apply-scope` 分两档**（默认 `build-descriptor`，即安全档）：

  | 档位 | 覆盖 | 为什么这样分 |
  | :- | :- | :- |
  | `build-descriptor`（默认）| `pom.xml` / `build.gradle(.kts)` / `package.json` / `Cargo.toml` / `pyproject.toml` / **Dockerfile 白名单落点** | 构建描述符里的版本**就是制品版本本身**，纯机械、无业务语义，改它零风险。Dockerfile 的 `COPY app-<版本>.jar` 尤其**必须**跟着改——pom 版本一改这里就找不到文件，镜像构建直接失败 |
  | `all` | 再加上代码常量 + `application.y(a)ml` + Dockerfile 裸 `VERSION` | 这几类**可能被业务逻辑读取 / 更可能指别的组件**，改动需要人复核，故不进默认档 |

  scope 外的不一致落点记入 `skipped_out_of_scope[]`，仍照常报告，绝不静默吞掉。

## 用法

    python3 .aidp/scripts/check_version_identifier.py --version V0.3.0
    python3 .aidp/scripts/check_version_identifier.py --version V0.3.0 --json
    python3 .aidp/scripts/check_version_identifier.py --version V0.3.0 --path code --path deploy
    python3 .aidp/scripts/check_version_identifier.py --version V0.3.0 --apply
    python3 .aidp/scripts/check_version_identifier.py --version V0.3.0 --apply --apply-scope all

退出码：0 = 全部对齐（或无落点/不适用；`--apply` 下含"本次已改齐"）；
1 = 仍有不一致（未改 / scope 外 / 写回失败）；2 = 用法/读取错误。

★ **退出码 1 不代表阻断发布**：调用方（`/version` Step 3.3.13）按 Important 级处置——
交互式让用户三选一、无人值守 WARN + 自动登记 `docs/audit/{version}/发布欠账.md`。
规划期调用方（Step 2.7.3）则默认带 `--apply` 直接改齐构建描述符。
"""
import argparse
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

# 扫描根（相对仓库根）；AIDP 约定 18 把业务代码统一收在 code/ 下
DEFAULT_PATHS = ["code"]

# 不下钻的目录：依赖 / 构建产物 / 版本库内部 / 第三方前端库落地目录
SKIP_DIRS = {
    "node_modules", "target", "build", "dist", "out", ".git", "__pycache__",
    ".gradle", ".idea", ".vscode", "venv", ".venv", "vendor", "coverage",
    ".next", ".nuxt", "bin", "obj",
    # ★ 第三方库落地目录：里面的版本号是**别人的制品版本**，写回即改坏第三方代码
    "bower_components", "jspm_packages", "web_modules", "third_party",
    "thirdparty", "vendors", "site-packages", ".pnpm", "Pods",
}

# ★ 压缩 / 打包产物：`bootstrap.min.js` 里满是 `a.VERSION="3.4.1"`，
# 既非本应用自报版本，写回还会破坏已压缩的第三方库。真实回流：本仓 adminlte。
SKIP_FILE_RE = re.compile(r"\.(min|bundle|pack|chunk)\.[A-Za-z0-9]+$|[.-]min\.[A-Za-z]+$")

# 项目级排除清单：每行一个 glob（`#` 开头为注释），相对仓库根匹配。
# 用于声明"这块不是本应用"——典型是 vendored 进来的完整第三方工程（连 pom.xml 一起拷进来的）。
VERSION_IGNORE_FILE = ".aidp-version-ignore"

# 代码常量落点：源文件后缀
CODE_EXTS = {".kt", ".java", ".go", ".py", ".ts", ".js", ".tsx", ".jsx",
             ".rs", ".cs", ".scala", ".groovy", ".rb", ".php"}

# 形如：SERVICE_VERSION = "0.2.0" / const APP_VERSION: String = "1.4.2" / VERSION := "2.0.0"
# ★ 前置负向后视排除 `a.VERSION="3.4.1"` 这类**对象属性赋值**——第三方 JS 库的标准写法，
#   不是本应用自报版本（`\b` 拦不住点号，真实回流：bootstrap.min.js 一次误报 11 处）。
CONST_RE = re.compile(
    r"(?<![.\w$])"
    r"\b([A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*_VERSION|VERSION)\b"
    r"\s*(?::\s*[\w<>\[\], .?]+)?\s*(?:=|:=)\s*"
    r"""["']([vV]?\d+\.\d+(?:\.\d+)?(?:[-.+][0-9A-Za-z.-]+)?)["']"""
)

# ★ 非制品版本 deny-list：协议 / 数据 / 工具链 / 依赖版本，与"本制品自报版本"无关
DENY_CONST_NAMES = {
    "API_VERSION", "SCHEMA_VERSION", "PROTOCOL_VERSION", "CONFIG_VERSION",
    "DB_VERSION", "DATABASE_VERSION", "MIGRATION_VERSION", "FORMAT_VERSION",
    "MIN_VERSION", "MAX_VERSION", "MINIMUM_VERSION", "TARGET_VERSION",
    "TLS_VERSION", "SSL_VERSION", "HTTP_VERSION",
    "JAVA_VERSION", "KOTLIN_VERSION", "SCALA_VERSION", "NODE_VERSION",
    "PYTHON_VERSION", "GO_VERSION", "GRADLE_VERSION", "MAVEN_VERSION",
    "SPRING_VERSION", "SPRING_BOOT_VERSION", "JDK_VERSION", "COMPILER_VERSION",
    "PLUGIN_VERSION", "SDK_VERSION", "CLIENT_VERSION",
}

# 占位值（构建期替换 / 未版本化），不判为不一致
PLACEHOLDER_RE = re.compile(r"^(0\.0\.0|\$\{.*\}|@.*@|)$")

YAML_VERSION_KEYS = ("info.app.version", "app.version", "spring.application.version")
MVN_NS = "{http://maven.apache.org/POM/4.0.0}"

# ── Dockerfile 落点 ───────────────────────────────────────────────────────────
# ★ 这里**只能用白名单**，不能像其它文件那样宽泛匹配 semver：Dockerfile 里满是
# **基础镜像 / 工具链版本**（`FROM ...temurin-jre-noble:17.0.20_8`、`ARG BASE_IMAGE=…:17.0.20_8`、
# `FROM openjdk:21-jdk-slim`），把它们当"本应用版本"改掉 = 拉错基础镜像 / 构建直接失败。
# 真实样本（实际项目中的三份 Dockerfile） 无一硬编码
# 应用版本，却各有 1–2 处基础镜像版本——宽匹配在真实项目里是纯误伤。
SEMVER_SUB = r"\d+\.\d+(?:\.\d+)?(?:[-.+][0-9A-Za-z.-]+)?"

# LABEL 键白名单：其余 `*.version` 一律不算（如 `java.version`）
DOCKER_LABEL_KEYS = {
    "version", "org.opencontainers.image.version",
    "app.version", "application.version", "service.version", "image.version",
}
# ARG/ENV 变量名白名单：必须**明确指向本应用**才进自动写回档
DOCKER_ARG_NAMES = {
    "APP_VERSION", "APPLICATION_VERSION", "SERVICE_VERSION",
    "PROJECT_VERSION", "BUILD_VERSION", "IMAGE_VERSION",
}
# ★ 裸 `VERSION`：Dockerfile 里它更常指"被安装组件的版本"（`ARG VERSION=1.21.6` 装 nginx），
# 但也可能是本应用。故**算落点、照常报告，但不进默认自动改档**（归 runtime-config，需人复核）——
# 既不漏报，也不误改。
DOCKER_BARE_VERSION = "VERSION"

DOCKER_KV_RE = re.compile(
    r"(?:^|\s)([A-Za-z][\w.]*)\s*=\s*[\"']?([vV]?" + SEMVER_SUB + r")[\"']?(?=\s|$)")
# 旧式 `ENV NAME value`（空格分隔、无等号）
DOCKER_ENV_LEGACY_RE = re.compile(
    r"^\s*ENV\s+([A-Za-z][\w.]*)\s+[\"']?([vV]?" + SEMVER_SUB + r")[\"']?\s*$", re.I)
# `COPY target/app-0.2.0.jar` —— 产物名里写死了版本。pom 版本一改这里就找不到文件，
# 是**必须同步**的一类（通配写法 `app-*.jar` 天然自适应，不匹配 semver、不算落点）。
DOCKER_ARTIFACT_RE = re.compile(
    r"[-_](" + SEMVER_SUB + r")\.(?:jar|war|zip|tgz|whl)\b|"
    r"[-_](" + SEMVER_SUB + r")\.tar\.gz\b")


def is_denied_const(name):
    """deny-list 判定走**后缀匹配**而非精确名。

    真实误报：`CURRENT_FORMAT_VERSION`（快照格式版本）精确名不在 deny-list、被判成制品版本漂移。
    带修饰前缀（`CURRENT_` / `DEFAULT_` / `SNAPSHOT_` …）是常见写法，故只要**以某个被拒语义结尾**
    就同样排除。
    """
    return name in DENY_CONST_NAMES or any(
        name.endswith("_" + denied) for denied in DENY_CONST_NAMES
    )


def normalize(v):
    """归一化版本串：去前导 V/v、去 -SNAPSHOT/-RELEASE 后缀、去首尾空白。"""
    if v is None:
        return ""
    v = v.strip().strip("\"'")
    if v[:1] in ("V", "v") and v[1:2].isdigit():
        v = v[1:]
    return re.sub(r"-(SNAPSHOT|RELEASE|FINAL|GA)$", "", v, flags=re.I)


def is_placeholder(v):
    return bool(PLACEHOLDER_RE.match((v or "").strip()))


def load_ignore_patterns(root, extra=None):
    """读项目级排除清单 `.aidp-version-ignore` + `--exclude` 传入的 glob。

    存在的意义：项目里 **vendored 了一整个第三方 Maven/Node 工程**（连 `pom.xml`/`package.json`
    一起拷进来）时，那份构建描述符里的版本是**别人的版本**，既不该报也绝不能写回。
    这种归属靠启发式猜不准（它长得和自家子模块一模一样），故交由项目显式声明。
    """
    pats = list(extra or [])
    path = os.path.join(root, VERSION_IGNORE_FILE)
    text = _read(path)
    if text:
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith("#"):
                pats.append(line)
    return pats


def is_ignored(rel, patterns):
    """相对路径匹配任一 glob 即排除；目录型 glob（`a/b` 或 `a/b/`）连同其子树一起排除。"""
    import fnmatch
    rel = rel.replace(os.sep, "/")
    for pat in patterns:
        p = pat.rstrip("/")
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(rel, p) \
                or rel.startswith(p + "/") or fnmatch.fnmatch(rel, p + "/*"):
            return True
    return False


def walk_files(root, rel_paths, ignore_patterns=None):
    """遍历指定子路径下的文件，跳过依赖/产物目录、压缩产物与项目声明的排除路径。"""
    ignore_patterns = ignore_patterns or []
    for rel in rel_paths:
        base = os.path.join(root, rel)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
            # 目录级剪枝：命中排除清单的整棵子树不下钻
            dirnames[:] = [
                d for d in dirnames
                if not is_ignored(os.path.relpath(os.path.join(dirpath, d), root),
                                  ignore_patterns)
            ]
            for fn in filenames:
                if SKIP_FILE_RE.search(fn):
                    continue
                full = os.path.join(dirpath, fn)
                if is_ignored(os.path.relpath(full, root), ignore_patterns):
                    continue
                yield full


def _read(path, limit=400_000):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(limit)
    except OSError:
        return None


def scan_code_constants(path, rel):
    """代码内 `*_VERSION = "x.y.z"` 常量落点。"""
    text = _read(path)
    if not text or "VERSION" not in text:
        return []
    hits = []
    for m in CONST_RE.finditer(text):
        name = m.group(1)
        if is_denied_const(name):
            continue
        line = text.count("\n", 0, m.start()) + 1
        hits.append({"kind": "code-constant", "file": rel, "line": line,
                     "name": name, "value": m.group(2)})
    return hits


def scan_pom(path, rel, skipped_inherited=None):
    """pom.xml：只取 project 自身直接子 <version>；只有 <parent><version> 的模块属继承、跳过。

    `skipped_inherited` 传入一个 list 时，把被跳过的继承型模块记进去——**只为让输出说人话**。
    多模块工程里"共扫 3 个落点"读起来像"本项目就 3 处"，而实际可能有 8 个 pom；
    人据此手工只改那 3 处，反应堆立刻解析不到父 POM。落点口径没错（继承版本不自报版本、
    `--apply` 写回父 pom 时由 `_sync_maven_parent_refs` 自动同步子模块），
    错的是**不说**——扫到的都对齐 ≠ 全都对齐，两者在措辞上必须可区分。
    """
    try:
        root_el = ET.parse(path).getroot()
    except Exception:
        return []
    for tag in (f"{MVN_NS}version", "version"):
        node = root_el.find(tag)
        if node is not None and (node.text or "").strip():
            return [{"kind": "build-descriptor", "file": rel, "line": None,
                     "name": "pom.xml <project><version>", "value": node.text.strip()}]
    if skipped_inherited is not None:
        for tag in (f"{MVN_NS}parent", "parent"):
            if root_el.find(tag) is not None:
                skipped_inherited.append(rel)
                break
    return []


def scan_gradle(path, rel):
    text = _read(path)
    if not text:
        return []
    m = re.search(r"""^\s*version\s*=?\s*["']([vV]?[0-9][^"']*)["']""", text, re.M)
    if not m:
        return []
    return [{"kind": "build-descriptor", "file": rel,
             "line": text.count("\n", 0, m.start()) + 1,
             "name": "gradle version", "value": m.group(1)}]


def scan_package_json(path, rel):
    text = _read(path)
    if not text:
        return []
    try:
        data = json.loads(text)
    except Exception:
        return []
    v = data.get("version")
    if not isinstance(v, str) or not v.strip():
        return []
    return [{"kind": "build-descriptor", "file": rel, "line": None,
             "name": 'package.json "version"', "value": v.strip()}]


def scan_toml(path, rel, section_hint):
    """Cargo.toml / pyproject.toml：取 [package] / [project] / [tool.poetry] 段内的 version。"""
    text = _read(path)
    if not text:
        return []
    section, hits = None, []
    for i, line in enumerate(text.split("\n"), 1):
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            section = s[1:-1].strip()
            continue
        if section not in section_hint:
            continue
        m = re.match(r"""^version\s*=\s*["']([vV]?[0-9][^"']*)["']""", s)
        if m:
            hits.append({"kind": "build-descriptor", "file": rel, "line": i,
                         "name": f"[{section}] version", "value": m.group(1)})
    return hits


def scan_dockerfile(path, rel):
    """Dockerfile / Containerfile：LABEL 版本键、ARG/ENV 应用版本、COPY/ADD 产物名内嵌版本。

    逐**物理行**扫描并跟踪当前指令（`\\` 续行时指令延续），这样每个命中天然归属一个行号，
    写回可精确定位；`FROM` 行与非白名单键**一律不产生落点**（见上方常量处的 Why）。
    """
    text = _read(path)
    if not text:
        return []
    hits, instr, cont = [], None, False
    for i, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip()
        stripped = line.strip()
        if not cont:
            if not stripped or stripped.startswith("#"):
                continue
            m = re.match(r"^([A-Za-z]+)\b", stripped)
            instr = m.group(1).upper() if m else None
        if instr == "LABEL":
            for m in DOCKER_KV_RE.finditer(line):
                if m.group(1).lower() in DOCKER_LABEL_KEYS:
                    hits.append({"kind": "build-descriptor", "file": rel, "line": i,
                                 "name": f"LABEL {m.group(1)}", "value": m.group(2)})
        elif instr in ("ARG", "ENV"):
            pairs = [(m.group(1), m.group(2)) for m in DOCKER_KV_RE.finditer(line)]
            lm = DOCKER_ENV_LEGACY_RE.match(line)
            if lm and not pairs:
                pairs = [(lm.group(1), lm.group(2))]
            for name, val in pairs:
                up = name.upper()
                if is_denied_const(up):
                    continue
                if up in DOCKER_ARG_NAMES:
                    kind = "build-descriptor"
                elif up == DOCKER_BARE_VERSION:
                    kind = "runtime-config"   # 需人复核档，见常量处 Why
                else:
                    continue                  # 基础镜像 / 组件 / 工具链版本，绝不碰
                hits.append({"kind": kind, "file": rel, "line": i,
                             "name": f"{instr} {name}", "value": val})
        elif instr in ("COPY", "ADD"):
            for m in DOCKER_ARTIFACT_RE.finditer(line):
                val = m.group(1) or m.group(2)
                hits.append({"kind": "build-descriptor", "file": rel, "line": i,
                             "name": f"{instr} 产物名内嵌版本", "value": val})
        cont = line.endswith("\\")
    return hits


def scan_app_yaml(path, rel):
    """application.y(a)ml：按缩进还原 info.app.version / app.version 等点分键。"""
    text = _read(path)
    if not text:
        return []
    hits, stack = [], []  # stack: [(indent, key)]
    for i, raw in enumerate(text.split("\n"), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        m = re.match(r"^([A-Za-z0-9_.\-]+)\s*:\s*(.*)$", raw.strip())
        if not m:
            continue
        key, val = m.group(1), m.group(2).strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        dotted = ".".join(k for _, k in stack)
        if dotted in YAML_VERSION_KEYS and val:
            hits.append({"kind": "runtime-config", "file": rel, "line": i,
                         "name": dotted, "value": val.strip("\"'")})
    return hits


# ── 写回（--apply）─────────────────────────────────────────────────────────────

# 拆解版本串：前缀（v/V）+ semver 主体 + 后缀（-SNAPSHOT / -RELEASE / +build …）
VERSION_PARTS_RE = re.compile(
    r"^(?P<prefix>[Vv]?)(?P<core>\d+\.\d+(?:\.\d+)?)(?P<suffix>.*)$")

# 可写回的落点类别 → 归属档位
SCOPE_KINDS = {
    "build-descriptor": {"build-descriptor"},
    "all": {"build-descriptor", "code-constant", "runtime-config"},
}


def retarget(old_value, want):
    """按目标版本改写旧值：**保留后缀（-SNAPSHOT 等）、剥掉 V/v 前缀**。

    `0.2.0-SNAPSHOT` + want=`0.3.0` → `0.3.0-SNAPSHOT`；`V0.11.2` → `0.12.0`。

    ★ **为什么剥前缀而不是保留**：`V0.3.0` 是 AIDP 文档 / git tag 的写法，
    **代码内自报版本应当是纯 semver**——semver 规范本身不含前缀，Maven `<version>`、
    npm `"version"`、Cargo、OCI `org.opencontainers.image.version` 带 `V` 都是不规范甚至非法的
    （npm 会拒绝）。故写回一律归一到无前缀，顺带把历史遗留的 `V` 写法纠正掉。
    后缀不同——`-SNAPSHOT` 是 Maven 开发期必需语义，必须原样保留。
    解析不出 semver 主体时退化为直接用 want（不硬造后缀）。
    """
    m = VERSION_PARTS_RE.match((old_value or "").strip())
    if not m:
        return want
    return f"{want}{m.group('suffix')}"


def _mask_parent(text):
    """把 `<parent>…</parent>` 段落替换成等长空白，保持字符偏移不变。

    用于 pom.xml 写回时排除继承版本——`<parent><version>` 属父 POM 坐标，
    改它会把模块指到另一个父版本上去，是真正的破坏性误改。
    """
    return re.sub(r"<parent\b.*?</parent>",
                  lambda m: " " * (m.end() - m.start()), text, flags=re.S)


def _apply_pom(text, hit, new_value):
    """pom.xml：在屏蔽掉 `<parent>` 后定位自身 `<version>`，定点替换。"""
    masked = _mask_parent(text)
    m = re.search(r"<version>\s*" + re.escape(hit["value"]) + r"\s*</version>", masked)
    if not m:
        return None
    return text[:m.start()] + f"<version>{new_value}</version>" + text[m.end():]


def _pom_self_artifact(path):
    """读 pom 自身坐标 (groupId, artifactId)；groupId 缺省时继承 parent 的。"""
    try:
        root_el = ET.parse(path).getroot()
    except Exception:
        return None, None

    def _txt(el, tag):
        if el is None:
            return None
        for t in (f"{MVN_NS}{tag}", tag):
            node = el.find(t)
            if node is not None and (node.text or "").strip():
                return node.text.strip()
        return None

    parent_el = root_el.find(f"{MVN_NS}parent")
    if parent_el is None:
        parent_el = root_el.find("parent")
    gid = _txt(root_el, "groupId") or _txt(parent_el, "groupId")
    return gid, _txt(root_el, "artifactId")


def _pom_parent_ref(path):
    """读 pom 的 `<parent>` 坐标 (groupId, artifactId, version)。"""
    try:
        root_el = ET.parse(path).getroot()
    except Exception:
        return None
    parent_el = root_el.find(f"{MVN_NS}parent")
    if parent_el is None:
        parent_el = root_el.find("parent")
    if parent_el is None:
        return None
    out = {}
    for tag in ("groupId", "artifactId", "version"):
        for t in (f"{MVN_NS}{tag}", tag):
            node = parent_el.find(t)
            if node is not None and (node.text or "").strip():
                out[tag] = node.text.strip()
                break
    return out if out.get("artifactId") else None


def _sync_maven_parent_refs(root, pom_rel, old_value, new_value):
    """父 pom 自身 `<version>` 改动后，同步反应堆内子模块的 `<parent><version>`。

    **为什么必须做**：`scan_pom` 有意跳过继承版本（子模块不自报版本，检查它属误报）。
    但一旦写回父 pom，子模块的 `<parent><version>` 就指向了一个**不存在的父 POM**，
    `mvn` 直接解析失败——"只改父不改子"是比不改更糟的破坏性结果。
    这正是 `mvn versions:set` 会连带改子模块 parent 引用的原因。

    匹配口径：子 pom 的 `<parent>` 中 artifactId 等于被改 pom 的 artifactId、
    version 等于其**旧值**，且 groupId 一致（任一方缺省则不以 groupId 否决）。
    """
    pom_abs = os.path.join(root, pom_rel)
    gid, aid = _pom_self_artifact(pom_abs)
    if not aid:
        return []
    reactor = os.path.dirname(pom_abs)
    synced = []
    # ★ 必须**传递**同步：孙模块的 parent 指的是中间模块、不是根 pom。
    #   只匹配「parent.artifactId == 被改 pom 的 artifactId」时，多层反应堆里
    #   `根 → A → A-core` 的 A-core 永远同步不到 —— 而 A 自己不自报版本（继承），
    #   不构成落点，于是没有任何一步会去改 A-core。
    #   ⛔ 后果不是"少改一处"：`mvn` 报 `Non-resolvable parent POM ... has not been downloaded`，
    #   tag 带着必然构建失败的 pom 推出去，而脚本自己报 [OK]（它只复检落点，不复检可解析性）。
    #   传播规则：某模块的 parent 引用被改掉后，**若它自己不声明 `<version>`**（= 版本继承自父），
    #   它的有效版本也跟着变了 ⇒ 它的子模块也要改。自己声明了版本的模块（独立版本线）则到此为止。
    queue = [(gid, aid)]
    seen = {aid}
    while queue:
        cur_gid, cur_aid = queue.pop(0)
        for child in _sync_parent_refs_one(root, reactor, pom_abs, cur_gid, cur_aid,
                                           old_value, new_value):
            synced.append(child["record"])
            if child["inherits"] and child["aid"] and child["aid"] not in seen:
                seen.add(child["aid"])
                queue.append((child["gid"], child["aid"]))
    return synced


def _pom_declares_own_version(pom_abs):
    """该 pom 是否**自己声明**了 `<version>`（而非继承父版本）。"""
    text = _read(pom_abs)
    if text is None:
        return False
    masked = _mask_parent(text)
    return re.search(r"<version>\s*[^<\s][^<]*</version>", masked) is not None


def _sync_parent_refs_one(root, reactor, pom_abs, gid, aid, old_value, new_value):
    """同步**直接**引用 (gid, aid, old_value) 作为 parent 的子 pom；返回可继续传播的条目。"""
    synced = []
    for dirpath, dirnames, filenames in os.walk(reactor):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if "pom.xml" not in filenames:
            continue
        child_abs = os.path.join(dirpath, "pom.xml")
        if os.path.abspath(child_abs) == os.path.abspath(pom_abs):
            continue
        ref = _pom_parent_ref(child_abs)
        if not ref or ref.get("artifactId") != aid or ref.get("version") != old_value:
            continue
        if gid and ref.get("groupId") and ref["groupId"] != gid:
            continue
        text = _read(child_abs)
        if text is None:
            continue
        # 只在 <parent>…</parent> span 内替换，绝不误伤 dependencies 里的同版本串
        pm = re.search(r"<parent\b.*?</parent>", text, re.S)
        if not pm:
            continue
        block = pm.group(0)
        new_block, n = re.subn(r"(<version>\s*)" + re.escape(old_value) + r"(\s*</version>)",
                               lambda m: m.group(1) + new_value + m.group(2), block, count=1)
        if not n:
            continue
        try:
            with open(child_abs, "w", encoding="utf-8") as f:
                f.write(text[:pm.start()] + new_block + text[pm.end():])
        except OSError:
            continue
        c_gid, c_aid = _pom_self_artifact(child_abs)
        synced.append({
            "record": {
                "kind": "build-descriptor", "file": os.path.relpath(child_abs, root),
                "line": None, "name": "pom.xml <parent><version>（反应堆同步）",
                "value": old_value, "new_value": new_value,
            },
            "aid": c_aid, "gid": c_gid or gid,
            # 自己不声明版本 = 有效版本随父变 ⇒ 它的子模块也要跟着改
            "inherits": not _pom_declares_own_version(child_abs),
        })
    return synced



def check_reactor_resolvable(root, scan_dirs=None):
    """纯静态的 Maven 反应堆可解析性自检：每个 `<parent>` 坐标能否在仓库内解析到。

    ⛔ 为什么落点复检不够：`--apply` 之后脚本只比对「落点文本是不是新值」，
    而反应堆能不能解析取决于**子模块的 parent 引用**——落点全对、反应堆照样崩。
    实测代价：`mvn` 报 `Non-resolvable parent POM … has not been downloaded`，
    而脚本报 `[OK] 4 处对齐`，tag 带着必然构建失败的 pom 推了出去。

    ★ 刻意**不跑 `mvn`**（约定 35：开发期只做静态验证）：外部 parent（如
    `spring-boot-starter-parent`）本就不在仓库内，判据只针对**能在仓库内找到同 artifactId
    的那些**——找到了就必须版本一致，找不到视为外部依赖、跳过。
    """
    poms = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        if "pom.xml" not in filenames:
            continue
        pom = os.path.join(dirpath, "pom.xml")
        gid, aid = _pom_self_artifact(pom)
        if not aid:
            continue
        ver = None
        text = _read(pom)
        if text is not None:
            m = re.search(r"<version>\s*([^<\s][^<]*?)\s*</version>", _mask_parent(text))
            if m:
                ver = m.group(1).strip()
        if ver is None:                       # 继承版本 → 有效版本 = parent 声明的版本
            ref = _pom_parent_ref(pom) or {}
            ver = ref.get("version")
        poms[aid] = {"path": pom, "version": ver}
    broken = []
    for aid, info in poms.items():
        ref = _pom_parent_ref(info["path"])
        if not ref or not ref.get("artifactId"):
            continue
        parent = poms.get(ref["artifactId"])
        if parent is None:
            continue                          # 仓库外 parent（三方 starter 等）→ 不判
        if parent["version"] and ref.get("version") and parent["version"] != ref["version"]:
            broken.append({
                "file": os.path.relpath(info["path"], root),
                "parent": ref["artifactId"],
                "ref_version": ref["version"], "actual_version": parent["version"],
                "msg": "parent 引用的版本与该父 POM 实际版本不一致 → Maven 反应堆解析不到父 POM",
            })
    return broken


def _apply_gradle(text, hit, new_value):
    m = re.search(r"""^(\s*version\s*=?\s*["'])""" + re.escape(hit["value"])
                  + r"""(["'])""", text, re.M)
    if not m:
        return None
    return text[:m.start()] + m.group(1) + new_value + m.group(2) + text[m.end():]


def _json_depth_at(text, pos):
    """`pos` 处的大括号嵌套深度（跳过字符串字面量与其中的转义）。顶层键深度 == 1。"""
    depth, in_str, esc = 0, False, False
    for c in text[:pos]:
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
    return depth


def _apply_package_json(text, hit, new_value):
    """package.json：只改**顶层** `"version"`，用大括号嵌套深度精确判定。

    不走 `json.dumps` 回写——那会重排键序、丢掉原缩进风格，把一行改动变成整文件 diff。
    也不用"缩进 ≤4 空格"近似顶层——紧凑/单行 JSON（`{"name":"x","version":"1.0.0"}`）
    整个文件只有一行，缩进判据直接失效、写回失败；而深度判据对格式化与紧凑两种都成立，
    且严格排除 `dependencies` 里恰好叫 `version` 的包（那在深度 2）。
    """
    for m in re.finditer(r'("version"\s*:\s*")(' + re.escape(hit["value"]) + r')(")', text):
        if _json_depth_at(text, m.start()) == 1:
            return text[:m.start(2)] + new_value + text[m.end(2):]
    return None


def _apply_on_line(text, hit, new_value, const_aware=False):
    """行级落点（toml / yaml / 代码常量）：只在 `hit['line']` 那一行内定点替换。

    `const_aware=True` 时先用 CONST_RE 复定位赋值右值的精确 span，避免同行出现
    相同数字串（如注释里重复写了版本号）时替换错位置。
    """
    lines = text.split("\n")
    idx = (hit.get("line") or 0) - 1
    if idx < 0 or idx >= len(lines):
        return None
    line = lines[idx]
    if const_aware:
        m = CONST_RE.search(line)
        if not m or m.group(2) != hit["value"]:
            return None
        s, e = m.span(2)
        lines[idx] = line[:s] + new_value + line[e:]
        return "\n".join(lines)
    if hit["value"] not in line:
        return None
    lines[idx] = line.replace(hit["value"], new_value, 1)
    return "\n".join(lines)


def _apply_dockerfile(text, hit, new_value):
    """Dockerfile：按 `name` 记录的键名/类型在目标行**复定位精确 span** 再替换。

    不能用整行 `replace(旧值)` —— `LABEL a=1.0.0 version=1.0.0` 这类一行多 KV 会替换错位置。
    """
    lines = text.split("\n")
    idx = (hit.get("line") or 0) - 1
    if idx < 0 or idx >= len(lines):
        return None
    line, name = lines[idx], hit["name"]

    def _sub(span):
        s, e = span
        lines[idx] = line[:s] + new_value + line[e:]
        return "\n".join(lines)

    if name.startswith(("LABEL ", "ARG ", "ENV ")):
        key = name.split(" ", 1)[1]
        for m in DOCKER_KV_RE.finditer(line):
            if m.group(1) == key and m.group(2) == hit["value"]:
                return _sub(m.span(2))
        lm = DOCKER_ENV_LEGACY_RE.match(line)
        if lm and lm.group(1) == key and lm.group(2) == hit["value"]:
            return _sub(lm.span(2))
        return None

    for m in DOCKER_ARTIFACT_RE.finditer(line):   # COPY/ADD 产物名内嵌版本
        gi = 1 if m.group(1) else 2
        if m.group(gi) == hit["value"]:
            return _sub(m.span(gi))
    return None


def is_dockerfile(base):
    """`Dockerfile` / `Dockerfile.prod` / `prod.Dockerfile` / `Containerfile` 全认。"""
    b = base.lower()
    return (b in ("dockerfile", "containerfile")
            or b.startswith(("dockerfile.", "containerfile."))
            or b.endswith(".dockerfile"))


def _writer_for(hit):
    """按落点选写回器；返回 None 表示该落点不支持写回。"""
    base = os.path.basename(hit["file"])
    if is_dockerfile(base):
        return _apply_dockerfile
    if base == "pom.xml":
        return _apply_pom
    if base in ("build.gradle", "build.gradle.kts"):
        return _apply_gradle
    if base == "package.json":
        return _apply_package_json
    if base in ("Cargo.toml", "pyproject.toml"):
        return _apply_on_line
    if hit["kind"] == "code-constant":
        return lambda t, h, v: _apply_on_line(t, h, v, const_aware=True)
    if hit["kind"] == "runtime-config":
        return _apply_on_line
    return None


def apply_fixes(root, mismatched, want, scope):
    """把 `mismatched[]` 中属于 scope 的落点改成目标版本。

    同一文件的多处命中**逐处串行改、每处改完立即回写**——因为行级替换依赖行号，
    批量攒改再一次性写会让先前的替换影响后续定位。版本号是等长/近似等长替换，
    行号不会漂移，串行改是安全的。
    """
    allow = SCOPE_KINDS.get(scope, SCOPE_KINDS["build-descriptor"])
    applied, skipped, failed = [], [], []
    for hit in mismatched:
        if hit["kind"] not in allow:
            skipped.append(hit)
            continue
        writer = _writer_for(hit)
        if writer is None:
            failed.append(dict(hit, error="该落点类型不支持自动写回"))
            continue
        path = os.path.join(root, hit["file"])
        text = _read(path)
        if text is None:
            failed.append(dict(hit, error="文件读取失败"))
            continue
        new_value = retarget(hit["value"], want)
        try:
            new_text = writer(text, hit, new_value)
        except Exception as e:  # 单点写回异常不连坐其余落点
            failed.append(dict(hit, error=f"写回异常：{e}"))
            continue
        if new_text is None or new_text == text:
            failed.append(dict(hit, error="未能在原文中定位该落点（文件已变化？）"))
            continue
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_text)
        except OSError as e:
            failed.append(dict(hit, error=f"写入失败：{e}"))
            continue
        applied.append(dict(hit, new_value=new_value))
        # 父 pom 改完立刻同步子模块 parent 引用，否则反应堆解析不到父 POM
        if os.path.basename(hit["file"]) == "pom.xml":
            applied += _sync_maven_parent_refs(root, hit["file"], hit["value"], new_value)
    return applied, skipped, failed


def collect(root, rel_paths, ignore_patterns=None, skipped_inherited=None):
    """扫全部落点，返回命中列表。`skipped_inherited` 见 scan_pom 的同名参数。"""
    found = []
    for path in walk_files(root, rel_paths, ignore_patterns):
        rel = os.path.relpath(path, root)
        base, ext = os.path.basename(path), os.path.splitext(path)[1]
        if base == "pom.xml":
            found += scan_pom(path, rel, skipped_inherited)
        elif base in ("build.gradle", "build.gradle.kts"):
            found += scan_gradle(path, rel)
        elif base == "package.json":
            found += scan_package_json(path, rel)
        elif base == "Cargo.toml":
            found += scan_toml(path, rel, {"package"})
        elif base == "pyproject.toml":
            found += scan_toml(path, rel, {"project", "tool.poetry"})
        elif is_dockerfile(base):
            found += scan_dockerfile(path, rel)
        elif re.match(r"^application([-.].+)?\.ya?ml$", base):
            found += scan_app_yaml(path, rel)
        elif ext in CODE_EXTS:
            found += scan_code_constants(path, rel)
    return found


def run(root, release_version, rel_paths, ignore_patterns=None):
    want = normalize(release_version)
    if not want:
        raise ValueError("--version 不能为空")
    if ignore_patterns is None:
        ignore_patterns = load_ignore_patterns(root)
    skipped_inherited = []
    found = collect(root, rel_paths, ignore_patterns, skipped_inherited)
    if not found:
        return {
            "applicable": False,
            "reason": f"扫描 {'/'.join(rel_paths)} 未发现任何版本标识落点（无自报版本的项目），跳过",
            "release_version": release_version, "normalized": want,
            "scanned": 0, "matched": [], "mismatched": [], "placeholders": [],
            "inherited_poms": skipped_inherited,
        }
    matched, mismatched, placeholders = [], [], []
    for h in found:
        if is_placeholder(h["value"]):
            placeholders.append(h)
        elif normalize(h["value"]) == want:
            matched.append(h)
        else:
            mismatched.append(h)
    return {
        "applicable": True, "reason": "",
        "release_version": release_version, "normalized": want,
        "scanned": len(found),
        "matched": matched, "mismatched": mismatched, "placeholders": placeholders,
        "inherited_poms": skipped_inherited,
    }


def main():
    ap = argparse.ArgumentParser(
        description="发布版本 ↔ 代码内自报版本 对齐检查（发布期护栏，Important 级、不硬阻断）")
    ap.add_argument("--version", required=True, help="本次发布版本，如 V0.3.0 或 0.3.0")
    ap.add_argument("--root", default=".", help="仓库根目录（默认当前目录）")
    ap.add_argument("--path", action="append", default=None,
                    help=f"扫描子路径，可多次传（默认 {DEFAULT_PATHS}）")
    ap.add_argument("--json", action="store_true", help="只输出机读 JSON")
    ap.add_argument("--apply", action="store_true",
                    help="把不一致落点写回为目标版本（保留 -SNAPSHOT 后缀，剥掉 V/v 前缀）")
    ap.add_argument("--apply-scope", choices=sorted(SCOPE_KINDS), default="build-descriptor",
                    help="写回档位：build-descriptor=仅构建描述符（默认，安全档）；"
                         "all=再加代码常量与 application.yml（可能被业务逻辑读取，需人复核）")
    ap.add_argument("--exclude", action="append", default=None,
                    help=f"排除路径 glob，可多次传；与项目根 {VERSION_IGNORE_FILE} 合并。"
                         "用于声明 vendored 的第三方工程（那里的版本是别人的，不该报更不该写回）")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    rel_paths = args.path or DEFAULT_PATHS
    ignore_patterns = load_ignore_patterns(args.root, args.exclude)
    try:
        result = run(args.root, args.version, rel_paths, ignore_patterns)
    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}, ensure_ascii=False))
        else:
            print(f"[ERROR] 检查执行失败：{e}")
        return 2

    if args.apply and result["applicable"] and result["mismatched"]:
        applied, skipped, failed = apply_fixes(
            args.root, result["mismatched"], result["normalized"], args.apply_scope)
        # 写回后**强制复验**：以重扫结果为准，不拿"我改过了"当已对齐
        try:
            result = run(args.root, args.version, rel_paths, ignore_patterns)
        except Exception as e:
            if args.json:
                print(json.dumps({"error": f"写回后复验失败：{e}"}, ensure_ascii=False))
            else:
                print(f"[ERROR] 写回后复验失败：{e}")
            return 2
        result["apply_scope"] = args.apply_scope
        result["applied"] = applied
        result["skipped_out_of_scope"] = skipped
        result["apply_failed"] = failed

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["mismatched"] else 0

    if result.get("applied") is not None:
        print(f"[APPLY] 已写回 {len(result['applied'])} 处（档位 {result['apply_scope']}）：")
        for h in result["applied"]:
            loc = f"{h['file']}:{h['line']}" if h["line"] else h["file"]
            print(f"  · {loc} —— {h['name']}：{h['value']} → {h['new_value']}")
        for h in result.get("skipped_out_of_scope") or []:
            loc = f"{h['file']}:{h['line']}" if h["line"] else h["file"]
            print(f"  · [scope 外未改] {loc} —— {h['name']} = {h['value']}"
                  f"（{h['kind']}；如需一并改用 --apply-scope all）")
        for h in result.get("apply_failed") or []:
            loc = f"{h['file']}:{h['line']}" if h["line"] else h["file"]
            print(f"  · [写回失败] {loc} —— {h['name']}：{h['error']}")

    if not result["applicable"]:
        print(f"[SKIP] {result['reason']}")
        return 0
    inherited = result.get("inherited_poms") or []
    inherit_note = ""
    if inherited:
        # 「扫到的都对齐」≠「全都对齐」——多模块工程里这句话必须说出来，
        # 否则人手工只改被扫的那几处，反应堆立刻解析不到父 POM。
        inherit_note = (f"\n  ⚠️ 另有 {len(inherited)} 个 pom.xml 只有 `<parent><version>`（继承、不自报版本），"
                        f"按设计不计落点：{'、'.join(inherited[:5])}"
                        + ("…" if len(inherited) > 5 else "")
                        + "\n     手工改版本号时它们需一并改，否则 Maven 反应堆解析不到父 POM；"
                          "用 `--apply` 写回则由脚本自动同步，无需手改。")
    # ★ 落点全对 ≠ 反应堆能解析：写回只保证"落点文本是新值"，而 `mvn` 解析靠的是
    #   子模块的 `<parent><version>`。这道自检必须在 [OK] **之前**，否则
    #   「落点 4 处对齐」会盖住「反应堆解析不到父 POM」，tag 带着崩掉的 pom 推出去。
    broken = check_reactor_resolvable(args.root)
    # ★ `--apply` 必须能自愈已坏的反应堆：上一次半截 apply 之后根 pom 已是新值、
    #   不再构成"落点不一致"，传递同步没有触发点 ⇒ 光靠重跑 --apply 永远修不好。
    #   故这里直接按"父 POM 的实际版本"定点改回子模块的 parent 引用。
    if broken and args.apply:
        fixed = []
        for b_ in broken:
            cp = os.path.join(args.root, b_["file"])
            text = _read(cp)
            if text is None:
                continue
            pm = re.search(r"<parent\b.*?</parent>", text, re.S)
            if not pm:
                continue
            nb, n = re.subn(r"(<version>\s*)" + re.escape(b_["ref_version"]) + r"(\s*</version>)",
                            lambda m: m.group(1) + b_["actual_version"] + m.group(2),
                            pm.group(0), count=1)
            if not n:
                continue
            try:
                with open(cp, "w", encoding="utf-8") as f:
                    f.write(text[:pm.start()] + nb + text[pm.end():])
            except OSError:
                continue
            fixed.append(b_["file"])
        if fixed:
            print(f"🔧 反应堆自愈：修正 {len(fixed)} 处 parent 引用 → "
                  + "、".join(fixed[:5]) + ("…" if len(fixed) > 5 else ""))
            broken = check_reactor_resolvable(args.root)   # 修完复检，⛔ 不凭"改过了"判成功

    if broken:
        print(f"[FAIL] 落点已对齐，但 Maven 反应堆**解析不通** {len(broken)} 处 —— "
              f"⛔ 不得据此宣告版本标识对齐：")
        for b_ in broken:
            print(f"  · {b_['file']} —— parent {b_['parent']} 引用 {b_['ref_version']}，"
                  f"实际 {b_['actual_version']}")
        print("  修复：重跑 `--apply`（传递同步会连带改子模块 parent 引用）；"
              "仍不通说明有跨反应堆引用，需人工核。")
        return 1

    if not result["mismatched"]:
        extra = f"，{len(result['placeholders'])} 处占位值豁免" if result["placeholders"] else ""
        print(f"[OK] **已扫落点**均与发布版本 {result['release_version']} 一致："
              f"{len(result['matched'])} 处对齐{extra}（共扫 {result['scanned']} 个落点）"
              f"，且 Maven 反应堆 parent 引用全部可解析。{inherit_note}")
        return 0

    print(f"[FAIL] 检出 {len(result['mismatched'])} 处代码内自报版本 ≠ 发布版本 "
          f"{result['release_version']}（归一化后应为 {result['normalized']}）：")
    for h in result["mismatched"]:
        loc = f"{h['file']}:{h['line']}" if h["line"] else h["file"]
        print(f"  · {loc} —— {h['name']} = {h['value']}（应为 {result['normalized']}）")
    print(f"  已对齐 {len(result['matched'])} 处 / 占位豁免 {len(result['placeholders'])} 处"
          f" / 共扫 {result['scanned']} 个落点。{inherit_note}")
    print("  处置：交互式由用户三选一（自动改为本版本 / 保持不变并说明理由 / 中止发布）；"
          "无人值守 WARN + 登记 docs/audit/{version}/发布欠账.md。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
