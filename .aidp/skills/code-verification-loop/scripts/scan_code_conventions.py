#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""源码静态约定回检合集(对应 code-verification-loop 维度 4「代码质量」新增 5 个可机器化子项)

把维度 4 中「靠 grep/diff 就能确定性采集」的回检子项收敛到一个自包含脚本,逐项采集命中点,
输出 `文件:行号 + 命中类别 + 片段`,供 Agent 拿命中清单与详细设计 / 基线人工比对判定。

覆盖的 5 个子项(均为采集,不下最终违规结论):
  http-hardcode   HTTP 客户端配置硬编码    扫源码里硬编码的 http(s)://URL / IP / 凭证字面量
                  (对应 dev-logic-architect 核心原则 16「HTTP 客户端配置驱动铁律」——
                   base URL/IP/端口/凭证必须走配置文件,不得硬编码在代码)
  refresh-scope   配置中心热刷新漏标       Java/Kotlin 中 @Value("${...}") 注入了可变 key,
                  但所在文件无 @RefreshScope / 非 @ConfigurationProperties → 配置中心改值不热刷新
  dead-ref        死代码/死引用残留        JS/TS/Vue 的相对 import/require 指向**已不存在的文件**
                  (旧组件/模块被删后,新代码仍引用 → 编译期或运行期炸)
  dep-baseline    新增依赖/import 越界基线  git diff 新增的 import,其顶层包未声明在
                  package.json / requirements.txt / pyproject.toml(越过依赖基线)
  audit-fill      审计字段填充溯源          审计人字段(create_by/update_by/创建人/修改人 等)被写死为
                  常量字面量("system" 等),或逻辑删除写点(setDeleted(1)/deleted=1/@TableLogic)
                  邻近未同步 update_by/update_time(对应 dev-logic-architect 核心原则 22 / 检查项 30)

⚠️ 重要:本脚本只「采集命中点」,**不判定是否违规**(与 scan_cache_usage.py 一致)。
   - http-hardcode:命中的 URL/IP/凭证是否真违规,需 Agent 排除测试桩、注释、文档串、schema 命名空间。
   - refresh-scope:@Value 的 key 是否「运行时可变」(需热刷新)由 Agent 据配置中心实际判断;
                    常量类/启动期一次性读取的 key 不需 @RefreshScope。
   - dead-ref:命中即「相对 import 目标文件在磁盘不存在」,基本确定是死引用,但别名(@/、tsconfig paths)
              无法解析的已主动跳过(避免误报),Agent 复核别名引用。
   - dep-baseline:命中即「新增 import 的包未在清单声明」,需 Agent 排除内置模块 / monorepo workspace 包。
   - audit-fill:hardcoded-person 命中即「审计人字段同行有写死常量」,需 Agent 排除定时任务/无登录态且已显式
                标注的合法场景;logic-delete 附 sync_nearby=false 即「逻辑删除写点邻近未见同步修改人信号」,
                需 Agent 核对该删除路径是否真的漏更新 update_by/update_time(@TableLogic 默认删除会绕过自动填充)。
   因此本脚本退出码:有命中也返回 0(仅报告);仅「用法错误/目录不存在」返回 2。

扫描文件类型(按检查项各取所需):
   源码:    .java .kt .go .py .ts .tsx .js .jsx .vue .cs .scala .rb .mjs .cjs
   前端解析: .ts .tsx .js .jsx .vue .mjs .cjs(dead-ref 仅解析这些的相对 import)
豁免目录:   node_modules .git dist build target out .next .nuxt vendor
            __pycache__ coverage .idea .vscode .gradle bin obj

用法:
  python scan_code_conventions.py <代码目录>
  python scan_code_conventions.py <代码目录> --json
  python scan_code_conventions.py <代码目录> --checks http-hardcode,refresh-scope
  python scan_code_conventions.py <代码目录> --base origin/master   # dep-baseline 的 git diff 基线(默认 HEAD)

JSON 输出:
  {"findings": {"http-hardcode": [...], "refresh-scope": [...],
                "dead-ref": [...], "dep-baseline": [...], "audit-fill": [...]},
   "summary": {"http-hardcode": N, ...}, "total": N, "checks_run": [...], "notes": [...]}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ----------------------------------------------------------------------------- 常量
SOURCE_EXTS = {".java", ".kt", ".go", ".py", ".ts", ".tsx", ".js", ".jsx",
               ".vue", ".cs", ".scala", ".rb", ".mjs", ".cjs"}
FRONTEND_EXTS = {".ts", ".tsx", ".js", ".jsx", ".vue", ".mjs", ".cjs"}
EXCLUDE_DIRS = {"node_modules", ".git", "dist", "build", "target", "out",
                ".next", ".nuxt", "vendor", "__pycache__", "coverage",
                ".idea", ".vscode", ".gradle", "bin", "obj"}

ALL_CHECKS = ["http-hardcode", "refresh-scope", "dead-ref", "dep-baseline", "audit-fill"]

# http-hardcode:这些 host 是 schema/命名空间/文档串,不是运行时端点,直接跳过减噪
SAFE_URL_HOSTS = (
    "www.w3.org", "w3.org", "xmlns", "schemas.xmlsoap.org",
    "www.springframework.org", "springframework.org", "maven.apache.org",
    "xml.apache.org", "json-schema.org", "schema.org", "example.com",
    "example.org", "localhost", "127.0.0.1", "0.0.0.0",
)
# 凭证字面量:键名命中 + 值非占位/非环境变量引用,才算硬编码
CRED_KEY = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|secret[_-]?key|access[_-]?key|"
    r"app[_-]?id|app[_-]?secret|api[_-]?key|apikey|private[_-]?key|"
    r"client[_-]?secret|token)\b\s*[:=]\s*"
    r"""(['"])([^'"]{5,})\2"""
)
CRED_PLACEHOLDER = re.compile(
    r"(?i)^(\$\{.*\}|#\{.*\}|xxx+|your[_-]|changeme|placeholder|todo|mock|"
    r"example|test|demo|none|null|undefined|\*+|<.*>|\{\{.*\}\})"
)
URL_LITERAL = re.compile(r"""['"`](https?://([^'"`/\s]+)[^'"`\s]*)['"`]""")
IP_LITERAL = re.compile(
    r"""['"`]((?:\d{1,3}\.){3}\d{1,3})(?::\d{1,5})?['"`]"""
)
IP_SKIP = {"127.0.0.1", "0.0.0.0", "255.255.255.255", "1.1.1.1", "8.8.8.8"}

VALUE_ANNOT = re.compile(r"""@Value\s*\(\s*['"]\$\{([^}:]+)(?::[^}]*)?\}['"]\s*\)""")

# audit-fill:审计字段写死 system / 逻辑删除漏更新修改人
# (对应 dev-logic-architect 核心原则 22「审计字段操作人溯源与自动填充铁律」/ 检查项 30)
AUDIT_PERSON_TOKEN = re.compile(
    r"(?i)(set(?:Create[d]?By|Update[d]?By|Creator|Updater|Modifier|"
    r"Create[d]?User|Update[d]?User)|"
    r"\bcreate[_]?by\b|\bcreated[_]?by\b|\bupdate[_]?by\b|\bupdated[_]?by\b|"
    r"\bcreateBy\b|\bcreatedBy\b|\bupdateBy\b|\bupdatedBy\b|"
    r"\bcreator\b|\bupdater\b|\bmodifier\b|创建人|修改人|创建者|修改者)")
AUDIT_SYSTEM_LITERAL = re.compile(
    r"""['"](system|sys|admin|administrator|unknown|默认用户|系统|管理员)['"]""",
    re.IGNORECASE)
# 逻辑删除写点:把删除标记置为"已删除"
LOGIC_DELETE_SITE = re.compile(
    r"(?i)(set(?:Is)?Deleted\s*\(\s*(?:1|true)\s*\)|"
    r"setDelFlag\s*\(\s*(?:1|true)\s*\)|"
    r"\b(?:is[_]?deleted|deleted|del[_]?flag)\s*=\s*(?:1|true)\b|"
    r"@TableLogic)")
# 逻辑删除写点邻近应出现的"同步修改人"信号
# 注意:只认 setXxxBy 形式的 setter 与带词界的 snake_case update_by/update_time,
# 不认裸 camelCase updateBy —— 否则会误命中 ORM 方法名 updateById(每次 update 都出现),
# 把"漏同步修改人"的逻辑删除误判成"已同步"。
AUDIT_UPDATE_SYNC = re.compile(
    r"(?i)(setUpdate[d]?By|setUpdate[d]?Time|setModifier|setModify[d]?By|"
    r"\bupdate_by\b|\bupdated_by\b|\bupdate_time\b|\bupdated_time\b|"
    r"updateFill|修改人|修改时间|更新人|更新时间)")


# ----------------------------------------------------------------------------- 公共
def iter_files(root: Path, exts: set):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fn in filenames:
            if Path(fn).suffix.lower() in exts:
                yield Path(dirpath) / fn


def read_lines(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def strip_comment(line: str) -> str:
    """粗略剥掉行注释(// 与 #),减少注释里的 URL/凭证误报。
    关键:`http://` / `https://` 里的 `//` 紧跟 `:`,不能当注释切(否则 URL 在进正则前就被截断)。"""
    s = line
    # // 注释:取第一个「前一个字符不是 :」的 //,避免切到协议头
    start = 0
    while True:
        idx = s.find("//", start)
        if idx == -1:
            break
        if idx > 0 and s[idx - 1] == ":":
            start = idx + 2
            continue
        s = s[:idx]
        break
    # # 注释:URL fragment(#...)也可能误伤,但 # 后接 { 是 Spring SpEL,其余按行注释切
    idx = s.find("#")
    if idx != -1 and not s[idx:idx + 2] == "#{":
        s = s[:idx]
    return s


# ----------------------------------------------------------------------------- 检查 1
def check_http_hardcode(root: Path):
    """HTTP 客户端配置硬编码:源码(非配置文件)里硬编码 http(s)://URL / IP / 凭证。"""
    findings = []
    for path in iter_files(root, SOURCE_EXTS):
        for i, raw in enumerate(read_lines(path), 1):
            line = strip_comment(raw)
            if not line.strip():
                continue
            # URL 字面量
            for m in URL_LITERAL.finditer(line):
                full, host = m.group(1), m.group(2).lower()
                # host 含 ${...}/#{...}/{{...}} 占位 → 已是配置驱动,跳过(与文档「${...} 占位减噪」一致)
                if any(ph in host for ph in ("${", "#{", "{{")):
                    continue
                host_no_port = host.split(":", 1)[0]  # 先剥掉 :port 再比对安全 host(localhost:8080/127.0.0.1:3000 等)
                if any(host_no_port == h or host_no_port.endswith("." + h) for h in SAFE_URL_HOSTS):
                    continue
                findings.append({
                    "file": rel(path, root), "line": i, "category": "url",
                    "match": full[:160], "snippet": raw.strip()[:200],
                })
            # IP 字面量
            for m in IP_LITERAL.finditer(line):
                ip = m.group(1)
                octets = ip.split(".")
                if any(int(o) > 255 for o in octets):
                    continue  # 版本号/坐标之类,非 IP
                if ip in IP_SKIP:
                    continue
                findings.append({
                    "file": rel(path, root), "line": i, "category": "ip",
                    "match": ip, "snippet": raw.strip()[:200],
                })
            # 凭证字面量
            m = CRED_KEY.search(line)
            if m:
                val = m.group(3).strip()
                if not CRED_PLACEHOLDER.match(val):
                    findings.append({
                        "file": rel(path, root), "line": i, "category": "credential",
                        "match": m.group(0).strip()[:160], "snippet": raw.strip()[:200],
                    })
    return findings


# ----------------------------------------------------------------------------- 检查 2
def check_refresh_scope(root: Path):
    """配置中心热刷新漏标:Java/Kotlin 文件含 @Value("${...}") 但无 @RefreshScope /
    非 @ConfigurationProperties → 配置中心改值不热刷新。按文件粒度采集(多数 @Value bean 单类一文件)。"""
    findings = []
    for path in iter_files(root, {".java", ".kt"}):
        lines = read_lines(path)
        value_hits = []
        code_lines = []  # 仅代码行(剔注释行),用于判定是否真有 @RefreshScope/@ConfigurationProperties
        for i, raw in enumerate(lines, 1):
            st = raw.lstrip()
            if st.startswith("//") or st.startswith("*") or st.startswith("/*"):
                continue  # 注释行:既不算 @Value 命中,也不算 @RefreshScope 存在(避免被注释里的字样误导)
            code_lines.append(raw)
            for m in VALUE_ANNOT.finditer(raw):
                value_hits.append((i, m.group(1).strip(), raw.strip()[:200]))
        if not value_hits:
            continue
        code_text = "\n".join(code_lines)
        if "@RefreshScope" in code_text or "@ConfigurationProperties" in code_text:
            continue  # 已具备热刷新能力,跳过
        for line_no, key, snippet in value_hits:
            findings.append({
                "file": rel(path, root), "line": line_no, "value_key": key,
                "has_refresh_scope": False, "snippet": snippet,
            })
    return findings


# ----------------------------------------------------------------------------- 检查 3
_IMPORT_REL = re.compile(
    r"""(?:import\s[^'"]*?from\s*|import\s*|require\s*\(\s*|import\s*\(\s*)"""
    r"""['"](\.\.?/[^'"]+)['"]"""
)
_RESOLVE_EXTS = [".ts", ".tsx", ".js", ".jsx", ".vue", ".mjs", ".cjs", ".json", ".d.ts"]


def _resolves(base_dir: Path, spec: str) -> bool:
    target = (base_dir / spec).resolve()
    if target.suffix and target.exists():
        return True
    for ext in _RESOLVE_EXTS:
        if (base_dir / (spec + ext)).resolve().exists():
            return True
    # 目录式:spec/index.*
    for ext in _RESOLVE_EXTS:
        if (target / ("index" + ext)).exists():
            return True
    return target.is_dir()


def check_dead_ref(root: Path):
    """死引用残留:JS/TS/Vue 的相对 import/require 指向磁盘不存在的目标(旧文件被删后残留引用)。
    仅处理 ./ 与 ../ 开头的相对路径;别名(@/、tsconfig paths)无法离线解析,主动跳过避免误报。"""
    findings = []
    for path in iter_files(root, FRONTEND_EXTS):
        base_dir = path.parent
        for i, raw in enumerate(read_lines(path), 1):
            for m in _IMPORT_REL.finditer(raw):
                spec = m.group(1)
                if not _resolves(base_dir, spec):
                    findings.append({
                        "file": rel(path, root), "line": i,
                        "import_target": spec, "resolved": False,
                        "snippet": raw.strip()[:200],
                    })
    return findings


# ----------------------------------------------------------------------------- 检查 4
def _git(root: Path, args, notes):
    try:
        out = subprocess.run(
            ["git", "-C", str(root)] + args,
            capture_output=True, text=True, timeout=30,
        )
        return out
    except (OSError, subprocess.SubprocessError) as exc:
        notes.append(f"dep-baseline: 执行 git 失败({exc}),已跳过")
        return None


def _load_declared_packages(root: Path, notes):
    """收集已声明的依赖包名(JS package.json + Python requirements/pyproject)。"""
    js, py = set(), set()
    pkg = root / "package.json"
    if pkg.exists():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
            for key in ("dependencies", "devDependencies", "peerDependencies",
                        "optionalDependencies"):
                js.update((data.get(key) or {}).keys())
        except (OSError, ValueError) as exc:
            notes.append(f"dep-baseline: 解析 package.json 失败({exc})")
    for req in root.glob("**/requirements*.txt"):
        if any(p in EXCLUDE_DIRS for p in req.parts):
            continue
        for ln in read_lines(req):
            ln = ln.strip()
            if ln and not ln.startswith("#"):
                name = re.split(r"[<>=!~\[\s;]", ln, maxsplit=1)[0].strip()
                if name:
                    py.add(name.lower().replace("-", "_"))
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        for ln in read_lines(pyproject):
            m = re.match(r"""\s*['"]?([A-Za-z0-9_.-]+)['"]?\s*[=>~]""", ln)
            if m:
                py.add(m.group(1).lower().replace("-", "_"))
    return js, py


def _js_top_pkg(spec: str) -> str:
    if spec.startswith("@"):
        parts = spec.split("/")
        return "/".join(parts[:2])
    return spec.split("/")[0]


def _is_js_path_alias(spec: str) -> bool:
    """路径别名(非 npm 包)直接跳过,避免误报为「未声明依赖」:
    - `@/...`(空 scope,npm 不存在空 scope,必为 tsconfig/vite paths 别名)
    - `~`/`~/...`(npm 包名不可以 ~ 开头,必为别名)
    其余自定义别名(如 `@app/`)与真实 scoped 包无法离线区分,留给 Agent 复核。"""
    return spec.startswith("@/") or spec == "~" or spec.startswith("~/")


# Node/Python 内置模块(命中也不算越界基线),保守列常见项
NODE_BUILTINS = {
    "fs", "path", "os", "http", "https", "crypto", "util", "events", "stream",
    "child_process", "url", "querystring", "zlib", "net", "tls", "dns", "assert",
    "buffer", "process", "cluster", "readline", "vm", "module", "timers",
}
PY_STDLIB = {
    "os", "sys", "re", "json", "math", "time", "datetime", "pathlib", "typing",
    "collections", "itertools", "functools", "subprocess", "argparse", "logging",
    "abc", "io", "enum", "dataclasses", "asyncio", "unittest", "random", "hashlib",
    "base64", "uuid", "decimal", "csv", "sqlite3", "threading", "socket", "string",
    "copy", "traceback", "warnings", "contextlib", "shutil", "tempfile", "glob",
}

# 普通源码行(无 diff 前缀)的 import 抓取,untracked 新文件按整文件「全为新增」处理时复用
_PLAIN_JS_IMPORT = re.compile(
    r"""^.*?(?:import\s[^'"]*?from\s*|import\s*|require\s*\(\s*|import\s*\(\s*)"""
    r"""['"]([^'".][^'"]*)['"]"""
)
_PLAIN_PY_IMPORT = re.compile(r"^\s*(?:import|from)\s+([A-Za-z0-9_][\w.]*)")


def _classify_import(line: str, ext: str, js_decl: set, py_decl: set):
    """对单行源码(无 diff 前缀)判定是否引入「未声明在依赖清单」的顶层包。
    返回 finding(不含 file 字段)或 None。"""
    if ext in FRONTEND_EXTS:
        m = _PLAIN_JS_IMPORT.match(line)
        if not m:
            return None
        spec = m.group(1)
        if _is_js_path_alias(spec):
            return None
        top = _js_top_pkg(spec)
        if top in NODE_BUILTINS or top.startswith("node:"):
            return None
        if top not in js_decl:
            return {"ecosystem": "js", "import": spec,
                    "top_package": top, "declared": False,
                    "snippet": line.strip()[:200]}
    elif ext == ".py":
        m = _PLAIN_PY_IMPORT.match(line)
        if not m:
            return None
        top = m.group(1).split(".")[0]
        norm = top.lower().replace("-", "_")
        if norm in PY_STDLIB:
            return None
        if norm not in py_decl:
            return {"ecosystem": "py", "import": m.group(1),
                    "top_package": top, "declared": False,
                    "snippet": line.strip()[:200]}
    return None


def check_dep_baseline(root: Path, base: str, notes):
    """新增依赖/import 越界基线:git diff 新增的 import,其顶层包未声明在依赖清单。
    需 git 仓库 + git 可用;JS→package.json,Python→requirements/pyproject。
    Java/Go 的 import↔依赖映射无法离线可靠完成,本检查不覆盖(由 Agent 人工核对)。"""
    findings = []
    if not (root / ".git").exists():
        probe = _git(root, ["rev-parse", "--is-inside-work-tree"], notes)
        if not probe or probe.returncode != 0:
            notes.append("dep-baseline: 非 git 仓库,已跳过(无法取 diff 基线)")
            return findings
    out = _git(root, ["diff", "--unified=0", base, "--"], notes)
    if out is None:
        return findings
    if out.returncode != 0:
        # base 不存在时回退到未暂存 diff
        notes.append(f"dep-baseline: `git diff {base}` 失败,回退到工作区 diff")
        out = _git(root, ["diff", "--unified=0"], notes)
        if out is None or out.returncode != 0:
            notes.append("dep-baseline: git diff 不可用,已跳过")
            return findings
    js_decl, py_decl = _load_declared_packages(root, notes)
    cur_file = "?"
    for raw in out.stdout.splitlines():
        if raw.startswith("+++ b/"):
            cur_file = raw[6:]
            continue
        if not raw.startswith("+") or raw.startswith("+++"):
            continue
        ext = Path(cur_file).suffix.lower()
        hit = _classify_import(raw[1:], ext, js_decl, py_decl)
        if hit:
            findings.append({"file": cur_file, **hit})

    # untracked 新文件:git diff 看不到它们,但新建文件正是「新增 import」最常见来源,
    # 整文件按「全部为新增行」扫描(已被 .gitignore 排除的不在 --others --exclude-standard 内)
    others = _git(root, ["ls-files", "--others", "--exclude-standard"], notes)
    if others is not None and others.returncode == 0:
        for relpath in others.stdout.splitlines():
            relpath = relpath.strip()
            if not relpath:
                continue
            ext = Path(relpath).suffix.lower()
            if ext not in FRONTEND_EXTS and ext != ".py":
                continue
            for line in read_lines(root / relpath):
                hit = _classify_import(line, ext, js_decl, py_decl)
                if hit:
                    findings.append({"file": relpath, "untracked": True, **hit})
    return findings


# ----------------------------------------------------------------------------- 输出
# ----------------------------------------------------------------------------- 检查 5
def check_audit_fill(root: Path):
    """审计字段写死 system + 逻辑删除漏同步修改人(对应 architect 核心原则 22 / 检查项 30)。
    采集两类命中点(退出码恒 0,是否违规由 Agent 判定):
      - hardcoded-person:同一行既有审计人字段/setter 又有写死常量字面量("system" 等)
      - logic-delete:逻辑删除写点(setDeleted(1)/deleted=1/@TableLogic),附 sync_nearby
        (±5 行内是否出现同步 update_by/update_time 信号)供 Agent 判断是否漏更新修改人
    """
    findings = []
    for path in iter_files(root, SOURCE_EXTS):
        lines = read_lines(path)
        for i, raw in enumerate(lines, 1):
            line = strip_comment(raw)
            if not line.strip():
                continue
            # (a) 审计人字段写死常量
            if AUDIT_PERSON_TOKEN.search(line) and AUDIT_SYSTEM_LITERAL.search(line):
                findings.append({
                    "file": rel(path, root), "line": i, "category": "hardcoded-person",
                    "snippet": raw.strip()[:200],
                })
            # (b) 逻辑删除写点 + 邻近是否同步修改人(窗口取小,避免相邻方法误判为已同步;
            #     窗口内剥注释,避免注释里的"修改人"字样被当成真实的同步代码)
            if LOGIC_DELETE_SITE.search(line):
                lo = max(0, i - 1 - 5)
                hi = min(len(lines), i + 5)
                window = "\n".join(strip_comment(l) for l in lines[lo:hi])
                findings.append({
                    "file": rel(path, root), "line": i, "category": "logic-delete",
                    "sync_nearby": bool(AUDIT_UPDATE_SYNC.search(window)),
                    "snippet": raw.strip()[:200],
                })
    return findings


def render_text(results, summary, notes, checks):
    out = []
    out.append("【源码静态约定回检】scan_code_conventions.py")
    out.append(f"  运行检查项: {', '.join(checks)}")
    out.append(f"  命中合计: {sum(summary.values())} 处")
    out.append("")

    if "http-hardcode" in checks:
        hits = results["http-hardcode"]
        out.append(f"■ HTTP 客户端配置硬编码 (核心原则 16): {len(hits)} 处")
        for h in hits[:60]:
            out.append(f"    {h['file']}:{h['line']}  [{h['category']}] {h['match']}")
        if len(hits) > 60:
            out.append(f"    ... 余 {len(hits) - 60} 处见 --json")
        out.append("")

    if "refresh-scope" in checks:
        hits = results["refresh-scope"]
        out.append(f"■ 配置中心热刷新漏标 (@Value 无 @RefreshScope): {len(hits)} 处")
        for h in hits[:60]:
            out.append(f"    {h['file']}:{h['line']}  ${{{h['value_key']}}}")
        if len(hits) > 60:
            out.append(f"    ... 余 {len(hits) - 60} 处见 --json")
        out.append("")

    if "dead-ref" in checks:
        hits = results["dead-ref"]
        out.append(f"■ 死引用残留 (相对 import 目标不存在): {len(hits)} 处")
        for h in hits[:60]:
            out.append(f"    {h['file']}:{h['line']}  → {h['import_target']}")
        if len(hits) > 60:
            out.append(f"    ... 余 {len(hits) - 60} 处见 --json")
        out.append("")

    if "dep-baseline" in checks:
        hits = results["dep-baseline"]
        out.append(f"■ 新增依赖/import 越界基线 (未声明在清单): {len(hits)} 处")
        for h in hits[:60]:
            out.append(f"    {h['file']}  [{h['ecosystem']}] {h['import']} (顶层包 {h['top_package']})")
        if len(hits) > 60:
            out.append(f"    ... 余 {len(hits) - 60} 处见 --json")
        out.append("")

    if "audit-fill" in checks:
        hits = results["audit-fill"]
        hp = [h for h in hits if h["category"] == "hardcoded-person"]
        ld = [h for h in hits if h["category"] == "logic-delete"]
        ld_nosync = [h for h in ld if not h.get("sync_nearby")]
        out.append(f"■ 审计字段填充溯源 (核心原则 22 / architect 检查项 30): "
                   f"写死审计人 {len(hp)} 处, 逻辑删除写点 {len(ld)} 处"
                   f"(其中疑似漏同步修改人 {len(ld_nosync)} 处)")
        for h in hp[:40]:
            out.append(f"    [写死审计人] {h['file']}:{h['line']}  {h['snippet']}")
        for h in ld_nosync[:40]:
            out.append(f"    [逻辑删除·疑漏同步修改人] {h['file']}:{h['line']}  {h['snippet']}")
        if len(hp) > 40 or len(ld_nosync) > 40:
            out.append("    ... 更多见 --json")
        out.append("")

    if notes:
        out.append("  说明/跳过:")
        for n in notes:
            out.append(f"    - {n}")
        out.append("")

    out.append("  ⚠️ 本脚本仅采集命中点,是否违规由 Agent 比对详细设计/依赖基线后判定(退出码恒 0)。")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(
        description="源码静态约定回检合集(http-hardcode / refresh-scope / dead-ref / dep-baseline / audit-fill)")
    parser.add_argument("code_dir", help="待扫描的代码目录")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--checks", default=",".join(ALL_CHECKS),
                        help=f"逗号分隔,默认全部:{','.join(ALL_CHECKS)}")
    parser.add_argument("--base", default="HEAD",
                        help="dep-baseline 的 git diff 基线引用,默认 HEAD")
    args = parser.parse_args()

    root = Path(args.code_dir)
    if not root.is_dir():
        print(f"错误:目录不存在 -> {root}", file=sys.stderr)
        return 2

    checks = [c.strip() for c in args.checks.split(",") if c.strip()]
    bad = [c for c in checks if c not in ALL_CHECKS]
    if bad:
        print(f"错误:未知检查项 {bad};可选 {ALL_CHECKS}", file=sys.stderr)
        return 2

    notes = []
    results = {c: [] for c in ALL_CHECKS}
    if "http-hardcode" in checks:
        results["http-hardcode"] = check_http_hardcode(root)
    if "refresh-scope" in checks:
        results["refresh-scope"] = check_refresh_scope(root)
    if "dead-ref" in checks:
        results["dead-ref"] = check_dead_ref(root)
    if "dep-baseline" in checks:
        results["dep-baseline"] = check_dep_baseline(root, args.base, notes)
    if "audit-fill" in checks:
        results["audit-fill"] = check_audit_fill(root)

    summary = {c: len(results[c]) for c in checks}

    if args.json:
        print(json.dumps({
            "findings": {c: results[c] for c in checks},
            "summary": summary,
            "total": sum(summary.values()),
            "checks_run": checks,
            "notes": notes,
        }, ensure_ascii=False, indent=2))
    else:
        print(render_text(results, summary, notes, checks))

    return 0  # 采集器:有命中也返回 0,违规判定交给 Agent


if __name__ == "__main__":
    sys.exit(main())
