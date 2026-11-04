#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""release_baseline_check.py — 约定 37「版本发布双轨部署基线」的确定性机器门。

## 为什么需要本脚本

约定 37 的判据链大多是"要记得做"的动作，而其中最伤人的几类错误恰恰是
**人眼逐行看必漏、脚本一秒抓到**的类型（下游两个项目的实跑回流）：

  · **占位符残留**（37.4-1）—— 全量配置是「拿到即可对照使用的示例配置」，
    `${XXX:__FILL_ME__}` / `${ENV}` / `${ep-hosts.xxx}` 满篇的配置拿到手没法用（下游实跑：
    一份全量配置 30 多处占位）。每项都要写具体值。
  · **密码明文**（37.4-7）—— 只有密码类填虚构示例值，真实口令不进 git；
    IP / 账号 / 编码 / token 等按真实值填，不判凭据。
  · **环境绑定物残留**（37.3-4）—— schema 前缀 / TABLESPACE / STORAGE 没清干净，
    脚本被钉死在原环境，换环境执行必然失败。
  · **裸配置项**（37.4-9）—— 既无行内注释、上一行也非注释的配置行，部署方无从判断该不该改。
  · **失效相对链接** —— 目录调整后文档间引用断链，一次校验抓到 6 处。

「判据是确定性的，就不该靠自觉消费」——故把这些项固化成有退出码的硬门。

## 覆盖的 12 项校验

  1. 结构完整性        两轨对称落位（根下不得散落 .sql / 配置项清单）+ 全量轨目录 / 00_索引.md 就位
  2. YAML 语法         全量配置每个 .yml 逐文件解析 + .md 内 ```yaml 代码块逐块解析
  3. SQL 环境绑定物     schema 限定前缀 / TABLESPACE / STORAGE 命中数须为 0
  4. 密码明文          密码类键（password / passwd / pwd / secret-key …）与 URL userinfo、
                      HTTP Basic 里的口令须为示例值（注释声明「示例值」或值含 Example）
  5. 占位符残留        `__FILL_ME__` / `${ENV}` / `${ENV:默认值}` 一律 ERROR（37.4-1）
  6. 属性引用残留      `${a.b}` 引用一律 ERROR：重复值直接写具体值 + 注释同步关系（37.4-8）
  7. 注释完备性        「无行内注释且上一行非注释」的配置行数须为 0
  8. 生效形态唯一       多形态中间件配置同时只能有一组生效（其余整段注释）
  9. 相对链接有效性     .md 内相对链接目标存在
 10. 增量极简度        增量配置文档无 Markdown 表格、行内注释 ≤20 字符（约定 37.5-6）
 11. 全量核对可复核     `00_索引.md` 须写明**剔除结论**与**导出源**（实例地址 + schema/库名）——
                      约定 37 全量基线的定义性判据「与真实环境交叉核对」，⛔ 二者均为 ERROR 级
 12. DDL 注释实查      本版有 `ADD COLUMN` 时，注释覆盖率须【实查库】并落 SQL执行台账「三之二」
                      （⛔ 校的是库里状态、不是脚本内容；委派 check_sql_ledger_comment.py）

## 用法

    python3 AIDP_HOME/scripts/release_baseline_check.py --version V0.2.0
    python3 AIDP_HOME/scripts/release_baseline_check.py --version V0.2.0 --json
    python3 AIDP_HOME/scripts/release_baseline_check.py --version V0.2.0 --root /path/to/repo

退出码：0 = 无 ERROR（可能有 WARN/INFO）；1 = 有 ERROR；2 = 用法 / 路径错误。

★ 依赖：**标准库优先**。PyYAML 若可用则用于第 2 项严格语法校验，不可用时自动降级为
内置的轻量结构自检（Tab 缩进 / 缩进跳变 / 同层重复键）并给 INFO——**绝不因缺依赖而假通过**。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath, runtime_text
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml  # 可选：仅用于第 2 项严格语法校验
    _HAS_YAML = True
except Exception:                                   # pragma: no cover - 环境相关
    _HAS_YAML = False

# ── 判据常量（集中在此，便于下游按自身技术栈调整） ──────────────────────────────

# 3. SQL 环境绑定物：schema 限定前缀 "SCHEMA"."TABLE" / 表空间 / 存储子句
ENV_BOUND_SQL = (
    (re.compile(r'"[A-Za-z_][\w$]*"\s*\.\s*"[A-Za-z_][\w$]*"'), "schema 限定前缀（应为裸表名）"),
    (re.compile(r"\bTABLESPACE\b", re.I), "TABLESPACE 子句"),
    (re.compile(r"\bSTORAGE\s*\(", re.I), "STORAGE 存储子句"),
)

# COMMENT ON COLUMN "T"."C" IS '...' / COMMENT ON TABLE "T" IS '...'
# —— 列/表限定语法，非环境绑定物；匹配 schema 前缀前先整句摘除（见 check 3 注释）。
COMMENT_ON_RE = re.compile(
    r"COMMENT\s+ON\s+(?:COLUMN|TABLE)\b[^;]*;?", re.I | re.S)

# 3b. 全量轨迁移语句：全量是「从零建库」，出现 ALTER/迁移即说明增量轨内容混了进来。
#     约定 37 明写两轨绝不叠加执行——全量里带 ALTER，在一个空库上执行必然失败（改的表还不存在），
#     而在老库上执行又会二次改动。这是约定 37「两轨绝不叠加」最可机械判定的一面，
#     此前全文零判据：写进去也是「0 ERROR 🎉」放行。
MIGRATION_SQL = (
    (re.compile(r"\bALTER\s+TABLE\b", re.I), "ALTER TABLE（迁移语句）"),
    (re.compile(r"\bDROP\s+(?:COLUMN|CONSTRAINT|INDEX)\b", re.I), "DROP COLUMN/CONSTRAINT/INDEX"),
    (re.compile(r"\bRENAME\s+(?:TABLE|COLUMN|TO)\b", re.I), "RENAME（迁移语句）"),
    (re.compile(r"\bDROP\s+TABLE\b(?!\s+IF\s+NOT)", re.I), "DROP TABLE"),
)

# 4. 密码明文：敏感性只按「密码」划分（约定 37.4-7）。只有口令本身判 ERROR；
#    token / auth-code / api-key / access-key / 账号 / IP / 编码都按真实值填写，⛔ 不再判凭据——
#    此前把它们一并当凭据，下游按「示例值」口径填好的配置报了 14 条假 ERROR。
#    secret-key 收进来是因为它本质是口令（如 MinIO 的 secret-key 即 admin 账号口令）。
PASSWORD_KEY_RE = re.compile(r"(password|passwd|pwd|passphrase|secret[-_]?key)$", re.I)
# 非 YAML 文件（.properties / .env / nginx …）里的「密码键 = 值」
PASSWORD_KV_RE = re.compile(
    r"([\w.\-]*(?:password|passwd|pwd|passphrase|secret[-_]?key))[\"']?\s*[=:]\s*[\"']?([^\s\"';,]+)",
    re.I)
# 示例值识别：行内或上一行注释声明「示例值」，或值本身是固定示例形态（含 Example）
EXAMPLE_DECL = "示例值"
EXAMPLE_VALUE_RE = re.compile(r"example", re.I)

# 4（补）: 值里内嵌的口令——URL userinfo 的口令部分、HTTP Basic 解出的口令按密码判；
#          值里内嵌的 token 不判
URL_USERINFO_RE = re.compile(r"://([^/\s:@]+):([^/\s@]+)@")
BASIC_RE = re.compile(r"\bBasic\s+([A-Za-z0-9+/]{8,}={0,2})")

# 5 / 6. 占位符与属性引用残留（约定 37.4-1 / 37.4-8：每项写具体值）
FILL_ME = "__FILL_ME__"
REF_RE = re.compile(r"\$\{([^}]*)\}")
# nginx 原生变量 `${host}`（全小写、无点）不是占位符
NGINX_VAR_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# 8. 多形态中间件：同一组内同时生效多于一个 → ERROR
# ★ 判据绑【解析出的全路径】，不绑原始行文本：YAML 是嵌套的，集群节点那行长这样
#   `    nodes: ...`（父级才是 `redis.cluster`），用行正则找 `redis.cluster` 永远匹配不到
#   —— 本项曾因此静默空跑，被自测的合成用例抓出来。
FORM_GROUPS = {
    "redis": (("单机", re.compile(r"(^|\.)redis\.host$", re.I)),
              ("集群", re.compile(r"(^|\.)redis\.cluster(\.|$)", re.I)),
              ("哨兵", re.compile(r"(^|\.)redis\.sentinel(\.|$)", re.I))),
}

MD_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#][^)]*)\)")

# ★ 运行时部署配置文件（nginx / compose / k8s）——约定 37.2：完整文件属【全量轨】。
#   它们仍受【密码明文 / 占位残留 / 语法】校验，但**豁免 7 注释完备性**：
#   那一项是给"配置项清单式"配置用的（每项都要写业务含义与后果），
#   而 compose/k8s 大量是编排样板（image / ports / volumes），逐行要注释纯属噪音。
RUNTIME_DEPLOY_RE = re.compile(r"^(nginx.*\.conf|.*\.conf|docker-compose.*\.ya?ml|k8s-.*\.ya?ml)$", re.I)


class Report:
    """收集 ERROR / WARN / INFO 三级结论。ERROR 决定退出码。"""

    def __init__(self):
        self.errors, self.warns, self.notes = [], [], []

    def error(self, check, msg):
        self.errors.append({"check": check, "msg": msg})

    def warn(self, check, msg):
        self.warns.append({"check": check, "msg": msg})

    def note(self, check, msg):
        self.notes.append({"check": check, "msg": msg})


# ── 轻量 YAML 键抽取（不依赖 PyYAML；够用于配置文件这类扁平缩进结构） ──────────

def parse_config_lines(text):
    """把 YAML 文本解析成 [(行号, 全路径, 值原文, 是否注释行)]。

    只处理配置文件常见形态：`key:` / `key: value` / `- item` / `# 注释`。
    多行标量（`|` `>`）与流式集合不展开——它们不参与本脚本的键级判据，
    跳过比误判安全（宁可漏报也绝不错报，否则发布期天天被假红打断）。
    """
    out = []
    stack = []           # [(indent, key)]
    in_block_scalar_at = None    # 块标量的起始缩进，其下更深缩进行整体跳过
    for lineno, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if in_block_scalar_at is not None:
            if indent > in_block_scalar_at:
                continue
            in_block_scalar_at = None
        stripped = raw.strip()
        if stripped.startswith("#"):
            out.append((lineno, None, None, True))
            continue
        if stripped.startswith("- "):
            continue                          # 列表项不产生键路径
        m = re.match(r"^([^:#\s][^:#]*?)\s*:(?:\s+(.*))?$", stripped)
        if not m:
            continue
        key = m.group(1).strip().strip('"\'')
        val = (m.group(2) or "").strip()
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, key))
        path = ".".join(k for _, k in stack)
        if val in ("|", ">", "|-", ">-", "|+", ">+"):
            in_block_scalar_at = indent
            val = ""
        out.append((lineno, path, val, False))
    return out


def yaml_sanity(text):
    """PyYAML 不可用时的降级结构自检：Tab 缩进 / 同层重复键。"""
    problems = []
    seen = {}
    for lineno, raw in enumerate(text.splitlines(), 1):
        if raw.startswith("\t") or re.match(r"^ *\t", raw):
            problems.append(f"第 {lineno} 行用 Tab 缩进（YAML 禁止 Tab）")
    for lineno, path, _val, is_comment in parse_config_lines(text):
        if is_comment or not path:
            continue
        if path in seen:
            problems.append(f"第 {lineno} 行键 `{path}` 与第 {seen[path]} 行重复")
        else:
            seen[path] = lineno
    return problems


# ── 4 / 5 / 6 共用判据（YAML 键行、非 YAML 行、增量 yaml 代码块三处同口径） ──────────

PASSWORD_HINT = "密码类填虚构示例值，并在行内或上一行注释写明「示例值，非真实口令」"


def _declares_example(raw, prev):
    """行内注释或上一行注释声明了「示例值」。"""
    if "#" in raw and EXAMPLE_DECL in raw.split("#", 1)[1]:
        return True
    p = (prev or "").strip()
    return p.startswith(("#", "//", ";")) and EXAMPLE_DECL in p


def _is_example(secret, raw, prev):
    return bool(EXAMPLE_VALUE_RE.search(secret)) or _declares_example(raw, prev)


def _embedded_passwords(value):
    """值里内嵌的口令：URL userinfo 的口令部分、HTTP Basic 解出的口令。"""
    import base64
    import binascii
    out = [("URL userinfo 内嵌口令", m.group(2)) for m in URL_USERINFO_RE.finditer(value)]
    for m in BASIC_RE.finditer(value):
        try:
            decoded = base64.b64decode(m.group(1), validate=True).decode("utf-8", "replace")
        except (binascii.Error, ValueError):
            continue
        if ":" in decoded:
            out.append(("HTTP Basic 内嵌口令", decoded.split(":", 1)[1]))
    return out


def _password_findings(key, value, raw, prev):
    """返回该行的密码明文命中标签列表；示例值 / 空值 / 占位（另由 5 报）放行。"""
    hits = []
    value = value.strip().strip('"\'')
    if key and PASSWORD_KEY_RE.search(key) and value and "${" not in value \
            and FILL_ME not in value and not _is_example(value, raw, prev):
        hits.append("密码类键")
    for label, secret in _embedded_passwords(value):
        if secret and "${" not in secret and not _is_example(secret, raw, prev):
            hits.append(label)
    return hits


def _ref_findings(value, nginx=False):
    """返回 [(检查项, 原文)]：占位符残留 / 属性引用残留。"""
    out = []
    if FILL_ME in value:
        out.append(("占位符残留", FILL_ME))
    for m in REF_RE.finditer(value):
        inner = m.group(1).strip()
        name = inner.split(":", 1)[0]
        if nginx and NGINX_VAR_RE.match(inner):
            continue
        if "." in name or name != name.upper():
            out.append(("属性引用残留", m.group(0)))
        elif FILL_ME not in inner:
            out.append(("占位符残留", m.group(0)))
    return out


def _report_refs(rep, where, findings):
    for check, src in findings:
        if check == "占位符残留":
            rep.error(check, f"{where} 残留占位/注入写法 `{src}` —— 全量配置是「拿到即可对照使用的示例配置」，"
                             f"每项写具体值（取基线环境实况值，不知道怎么填就用研发环境的值；约定 37.4-1）；"
                             f"{PASSWORD_HINT}")
        else:
            rep.error(check, f"{where} 残留属性引用 `{src}` —— 不为「只改一处」把值抽成 `${{a.b}}`："
                             f"重复值直接写具体值，并注释标明「共 N 处须同步修改」（约定 37.4-8）")


def scan_entries(rep, label, text, nginx=False):
    """对一段 YAML 文本的键行跑 4 / 5 / 6。返回 parse_config_lines 结果供调用方复用。"""
    entries = parse_config_lines(text)
    lines = text.splitlines()
    for lineno, path, val, is_comment in entries:
        if is_comment or path is None or not val:
            continue
        raw = lines[lineno - 1]
        prev = lines[lineno - 2] if lineno >= 2 else ""
        bare = val.split("#")[0].strip()
        where = f"{label}:{lineno} `{path}`"
        for why in _password_findings(path.split(".")[-1], bare, raw, prev):
            rep.error("密码明文", f"{where} 疑似真实口令（{why}）—— 真实口令不进 git（历史不可逆）；"
                                  f"{PASSWORD_HINT}（如 `Nacos@Example2026`）")
        _report_refs(rep, where, _ref_findings(bare, nginx))
    return entries


# ── 各项校验 ──────────────────────────────────────────────────────────────────

def check_structure(ver_dir, rep):
    """1. 结构完整性：两轨对称落位 + 两轨是否都有交代（约定 37.2）。"""
    sql_full = ver_dir / "sql" / "全量"
    cfg_full = ver_dir / "配置文件" / "全量"
    idx = ver_dir / "00_索引.md"
    if not idx.is_file():
        # ★ ERROR 而非 WARN：它是约定 37「两套绝不叠加执行」的**唯一载体**。
        #   WARN 挡不住任何一步（本文件自陈），于是"双轨产出了、但没人说清哪套该用"可以一路发布出去。
        rep.error("结构完整性", f"缺 {ver_dir.name}/00_索引.md —— 双轨场景导航（全新部署 / 升级 各拿哪些）没有落点")
    else:
        # 存在还不够：必须真写了两条互斥路径，否则等于一张空索引
        _t = idx.read_text(encoding="utf-8", errors="replace")
        _miss = [w for w in ("全新部署", "升级") if w not in _t]
        if _miss:
            rep.error("结构完整性",
                      f"{ver_dir.name}/00_索引.md 未写明双轨场景导航（缺「{'」「'.join(_miss)}」路径）"
                      f" —— 约定 37 要求显式声明「全新部署走全量轨 / 升级走增量轨，两套绝不叠加执行」")

    # ★ 两轨落位：sql/ 与 配置文件/ 根下不得直放两轨产物（与 verify.py::check_deployment_two_track_layout
    #   同口径，但这里是**发布时刻**的门——旧结构会让新 glob 漏掉产物、运维照哪份跑说不清）
    stale = [f"sql/{f.name}" for f in sorted((ver_dir / "sql").glob("*.sql"))]
    stale += [f"配置文件/{f.name}" for f in sorted((ver_dir / "配置文件").glob("配置项清单*.md"))]
    for pat in ("*.conf", "docker-compose*.yml", "docker-compose*.yaml", "k8s-*.yaml", "k8s-*.yml"):
        stale += [f"配置文件/{f.name}" for f in sorted((ver_dir / "配置文件").glob(pat))]
    if stale:
        rep.error("结构完整性",
                  f"未按约定 37 两轨落位，以下产物仍散落在根：{', '.join(stale[:6])}"
                  + ("…" if len(stale) > 6 else "")
                  + " —— 增量轨应在 sql/增量/ 与 配置文件/增量/，nginx/compose/k8s 完整文件应在 "
                    "配置文件/全量/；按 `aidp-code-engineer` verify.py 给出的指引 `git mv` 搬迁并回写引用")
    for label, d in (("SQL 全量轨", sql_full), ("配置全量轨", cfg_full)):
        if not d.is_dir():
            rep.error("结构完整性",
                      f"{label}目录缺失：{d.relative_to(ver_dir.parent.parent)} —— "
                      f"约定 37「零变更的版本同样要产全量」，全量描述的是「当前代码要跑起来需要什么」")
            continue
        idx = d / "00_索引.md"
        if not idx.is_file():
            rep.error("结构完整性",
                      f"{label}缺 00_索引.md —— 判据（表清单怎么定的 / 导出源 / 收录矩阵）没有落点，"
                      f"产物无法自证")
            continue
        # ★ 存在性 ≠ 自证。约定 37 全量轨的**核心判据**是「表清单以代码 ORM 声明为准，
        #   再与真实库交叉核对；**代码有而库查无 → 剔除并写明理由**」——而此前机器门只断言
        #   索引文件在，索引里到底有没有写这个结论一个字都不看。于是「凭空导出一份未经核对的表」
        #   跑一遍现有实现**不会触发任何检查**：门是绿的，最难的那一步没人验。
        #   ⛔ 只做**存在性**判定（有没有交代过），不判对错——对错要连真实库才知道，
        #   那是人的活；但"连交代都没有"是确定性可判的。
        try:
            _t = idx.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            _t = ""
        if "剔除" not in _t:
            # ⛔ ERROR 不是 WARN：门的放行判据是「有无 ERROR」，WARN 挡不住任何一步
            #   （同一脚本里「空 SQL 全量轨」已因同样理由从 WARN 提到 ERROR）。
            #   而「与真实环境交叉核对」正是约定 37 全量基线的**定义性判据**——只报 WARN 时，
            #   拿客户端默认连接直接导一份 DDL 当全量、索引里既无导出源也无剔除结论，
            #   脚本照样打「🎉 无 ERROR」exit 0，细则里两起真实回流一步都拦不住。
            #   兜底话术成本极低（"本版无剔除项（已交叉核对）"），不构成误伤。
            rep.error("结构完整性",
                      f"{label} 00_索引.md 未见「剔除」相关结论 —— 约定 37 要求表清单以代码 ORM 声明为准"
                      f"再与真实库交叉核对，「代码有而库查无」的项须剔除并写明理由；"
                      f"确无剔除项也要就地写明「本版无剔除项（已交叉核对）」，否则无从区分"
                      f"「核对过、没有要剔的」与「压根没核对」")
        # ★ 导出源断言：细则 37.3-2 反复强调「导出源必须是应用实际连接的那个库、
        #   写明实例地址 + schema 名」，而此前脚本里「导出源」三字只出现在一句错误提示文案中、
        #   **零断言**。两起真实回流（迁库后工具连旧库差 8 倍、同实例两 schema 表名重叠取错）
        #   在无此断言时跑一遍不会被拦住任何一步。
        if not any(k in _t for k in ("导出源", "实例", "schema", "Schema", "SCHEMA")):
            rep.error("结构完整性",
                      f"{label} 00_索引.md 未写明**导出源**（应用实际连接的实例地址 + schema/库名）——"
                      f"约定 37：全量基线以「代码 × 真实环境」交叉核对为准，导出源不写清则无从复核"
                      f"这份基线到底来自哪个库")
        # ★ 只读采集方式断言 —— 约定 37 的另一半（「产出过程全程只读」）的落点。
        #   ⚠️ 必须说清这条能做到什么、做不到什么：「采集时有没有执行过 DDL/DML」**无法从产物反推**
        #   （真写了库，仓库里也不会留下痕迹）。所以本项不假装能验证过程，它验的是
        #   **采集方式有没有被记下来、从而可被人复核**：37.6 要求 DDL 经元数据视图导出、
        #   配置经只读 API 拉取，那就把用的是哪个视图 / 哪个只读端点写进索引。
        #   「写了但撒谎」本项拦不住；「压根没交代过用什么方式采的」是确定性可判的 ——
        #   而后者正是此前的实际状态：全仓 grep「只读」在本脚本命中 0。
        if not any(k in _t for k in ("只读", "元数据视图", "information_schema",
                                     "INFORMATION_SCHEMA", "all_tab_", "ALL_TAB_")):
            rep.error("结构完整性",
                      f"{label} 00_索引.md 未写明**只读采集方式**（DDL 走哪个元数据视图 / 配置走哪个只读 API）"
                      f" —— 约定 37.6 要求全程只读：不执行任何 DDL/DML、不改任何环境配置、不启动任何服务。"
                      f"采集方式不落文档，这条纪律就只是一句无从复核的自述")
    return sql_full, cfg_full


def check_sql_env_bound(sql_full, rep):
    """3. SQL 环境绑定物残留（命中数须为 0）+ 建表幂等。"""
    if not sql_full.is_dir():
        return
    files = sorted(sql_full.glob("*.sql"))
    if not files:
        # ★ 与配置侧同级判 ERROR，不是 WARN：约定 37 明写「**零变更的版本同样要产全量**」，
        #   而全量轨回答的是"从零怎么搭"——目录里只有一份 `00_索引.md`、一个 `.sql` 都没有，
        #   等于这个版本没法从零部署。此前两轨力度不对称（配置侧空判 ERROR、SQL 侧空判 WARN），
        #   而门的放行判据是"有无 ERROR" → 空 SQL 全量轨可以 exit 0 直接放行。
        rep.error("SQL 环境绑定物",
                  f"{sql_full.name}/ 下无 .sql 文件 —— 全量轨回答「从零怎么搭」，"
                  f"空目录等于本版无法全新部署（约定 37：零变更的版本同样要产全量）")
        return
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            rep.error("SQL 环境绑定物", f"{f.name} 读取失败：{e}")
            continue
        body = "\n".join(ln for ln in text.splitlines() if not ln.strip().startswith("--"))
        # ★ 先摘掉 COMMENT ON COLUMN/TABLE 语句再匹配 schema 前缀：
        #   `"T_USER"."NAME"` 在 COMMENT ON COLUMN 里是**列限定语法**（达梦/Oracle 必需），
        #   与 `"SCHEMA"."TABLE"` 这种真·环境绑定物同形。不排除的话，一个正常建表脚本
        #   的每条列注释都算一次命中——下游实测 5 个脚本命中 163 次、**全部是列注释**。
        #   为迎合正则删列注释就是丢掉全部字段业务含义（违反约定 17），于是这条 ERROR
        #   **永远清不掉**：一个不可能变绿的硬门只会训练人忽略它，真出现残留时也没人看。
        scan_body = COMMENT_ON_RE.sub(" ", body)
        for pat, label in ENV_BOUND_SQL:
            hits = pat.findall(scan_body if label.startswith("schema") else body)
            if hits:
                rep.error("SQL 环境绑定物",
                          f"{f.name} 残留{label} × {len(hits)} —— 全量脚本必须可落到任意 schema / "
                          f"任意表空间，换环境执行会失败")
        # 3b 全量轨迁移语句（注释与字符串已剔除的 body 上匹配）
        for pat, label in MIGRATION_SQL:
            hits = pat.findall(body)
            if hits:
                rep.error("全量轨迁移语句",
                          f"{f.name} 含{label} × {len(hits)} —— 全量轨是「从零建库」，"
                          f"迁移语句属增量轨；混进来后在空库上必然执行失败（要改的表还不存在），"
                          f"在老库上又会造成二次改动。两轨绝不叠加执行（约定 37）")
        creates = re.findall(r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?", body, re.I)
        idem = re.findall(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS", body, re.I)
        if creates and len(idem) < len(creates):
            rep.warn("SQL 环境绑定物",
                     f"{f.name} 有 {len(creates)} 处 CREATE TABLE、仅 {len(idem)} 处带幂等判断 —— "
                     f"约定 37 要求建表一律幂等（共享表重复执行才无害）")


def check_configs(cfg_full, rep):
    """2 / 4 / 5 / 6 / 7 / 8：配置侧全部逐文件判据。"""
    if not cfg_full.is_dir():
        return
    files = sorted(p for p in cfg_full.rglob("*")
                   if p.is_file() and p.suffix.lower() in (".yml", ".yaml"))
    if not files:
        rep.error("YAML 语法",
                  f"{cfg_full.name}/ 下无 .yml 配置产物 —— 配置中心层在仓库里没有第二信源，"
                  f"缺了它全新部署无从下手")
        return

    for f in files:
        rel = f.relative_to(cfg_full)
        try:
            text = f.read_text(encoding="utf-8")
        except Exception as e:
            rep.error("YAML 语法", f"{rel} 读取失败：{e}")
            continue

        # 2. YAML 语法
        if _HAS_YAML:
            try:
                yaml.safe_load(text)
            except Exception as e:
                rep.error("YAML 语法", f"{rel} 解析失败：{str(e).splitlines()[0]}")
                continue
        else:
            for p in yaml_sanity(text):
                rep.error("YAML 语法", f"{rel} {p}")

        # 4 / 5 / 6. 密码明文 / 占位符残留 / 属性引用残留
        entries = scan_entries(rep, str(rel), text)
        lines = text.splitlines()
        is_runtime_deploy = bool(RUNTIME_DEPLOY_RE.match(f.name))
        live_paths = [p for _ln, p, _v, is_c in entries if p and not is_c]
        prev_was_comment = False
        for lineno, path, val, is_comment in entries:
            if is_comment:
                prev_was_comment = True
                continue
            if path is None:
                continue
            raw = lines[lineno - 1]

            # 7. 注释完备性：既无行内注释、上一行也非注释（运行时部署编排文件豁免，见 RUNTIME_DEPLOY_RE）
            has_inline = "#" in raw.split(":", 1)[-1]
            if val and not has_inline and not prev_was_comment and not is_runtime_deploy:
                rep.warn("注释完备性",
                         f"{rel}:{lineno} `{path}` 裸配置项（无行内注释、上一行也非注释）—— "
                         f"注释要写业务含义与后果（换环境是否必改 / 配错什么后果）")
            prev_was_comment = False

        # 8. 生效形态唯一
        for group, forms in FORM_GROUPS.items():
            active = [label for label, pat in forms
                      if any(pat.search(p) for p in live_paths)]
            if len(active) > 1:
                rep.error("生效形态唯一",
                          f"{rel} {group} 同时生效 {len(active)} 种形态（{' / '.join(active)}）—— "
                          f"框架只认其一、另一套静默失效；非当前形态须整段注释")


def check_nonyaml_runtime_files(cfg_full, rep):
    """4 / 5 / 6（补）: 键路径解析器管不到的行——非 YAML 运行时文件（典型 nginx.conf）逐行扫描。

    nginx.conf 走不进 YAML 解析器，但它照样会带口令（上游 basic auth、URL 内嵌口令）与
    占位写法。约定 37.2 把它归【全量轨】后，这份文件就在 `全量/` 里随 tag 冻结入 git，
    **真实口令一旦进去 git 历史不可逆**。
    """
    if not cfg_full.is_dir():
        return
    # ⛔ 此处原本是**白名单**（只认 nginx.conf / docker-compose* / k8s-*），于是
    #    `.properties` / `.env` / `.json` **一个都不扫**——实测合成基线里
    #    `spring.datasource.password=…` 全程 0 ERROR、exit 0 放行。
    #    `全量/` 下的一切都随 tag 冻结入 git，故改为**黑名单**：
    #    除 .md（说明文档）与 YAML（走上面的键路径解析）外，逐行扫。
    SKIP_SUFFIX = {".md", ".png", ".jpg", ".jpeg", ".gif", ".svg",
                   ".pdf", ".zip", ".gz", ".jar", ".woff", ".woff2", ".ttf", ".ico"}
    # ★ YAML 也要扫，但**只扫键路径解析器跳过的那些行**——它对 `- 列表项` 与块标量
    #   （`|` / `>` 之后的缩进块）整段 `continue`，于是 `- "Authorization: Basic …"`
    #   这类写法在两条路径上都无人过问。键行本身已由 scan_entries 覆盖，这里排除以免重复报。
    #   ⚠️ 键名判据必须**收紧到真正的 YAML 键**（无空格无引号）：写宽了会把
    #   `- "Authorization: Basic …"` 和块标量里的 `curl -H "Authorization: …"` 一并当成键行
    #   跳过——而这两种恰恰是本段唯一要抓的对象。
    _KEYLINE_RE = re.compile(r"^[A-Za-z_][\w.\-]*\s*:(\s|$)")
    for f in sorted(cfg_full.rglob("*")):
        if not f.is_file() or f.suffix.lower() in SKIP_SUFFIX:
            continue
        _yaml_only_unparsed = f.suffix.lower() in (".yml", ".yaml")
        nginx = f.suffix.lower() == ".conf"
        rel = f.relative_to(cfg_full)
        try:
            lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        for i, raw in enumerate(lines, 1):
            ln = raw.split("#")[0].strip()
            if not ln:
                continue
            if _yaml_only_unparsed and _KEYLINE_RE.match(ln):
                continue                        # 键行归 YAML 路径，避免重复报
            prev = lines[i - 2] if i >= 2 else ""
            where = f"{rel}:{i}"
            whys = []
            for m in PASSWORD_KV_RE.finditer(ln):
                whys += _password_findings(m.group(1), m.group(2), raw, prev)
            whys += [w for w in _password_findings("", ln, raw, prev) if w not in whys]
            if whys:
                rep.error("密码明文",
                          f"{where} 疑似真实口令（{' / '.join(whys)}）—— {ln[:70]} · {PASSWORD_HINT}"
                          f"（本文件随 tag 入 git，真实口令进去不可逆）")
            _report_refs(rep, where, _ref_findings(ln, nginx))


def check_increment_values(ver_dir, rep):
    """4 / 5 / 6（增量轨）: `配置文件/增量/*.md` 的 yaml 代码块同口径——发布期配置两轨都不留占位、不放真实口令。"""
    inc = ver_dir / "配置文件" / "增量"
    if not inc.is_dir():
        return
    for md in sorted(inc.glob("*.md")):
        rel = md.relative_to(ver_dir)
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, block in enumerate(re.findall(r"```ya?ml\n(.*?)```", text, re.S), 1):
            scan_entries(rep, f"{rel} 第 {i} 个 yaml 代码块", block)


# 零变更声明的识别词：约定 37.5-7 要求「在 00_索引.md 写清『为什么是零』+ 判据」。
# ⛔ 只认**显式**声明，不做语义猜测——猜错的方向是"把没写当成写了"，正是本检查要堵的。
_ZERO_DECL_RE = re.compile(
    r"(无增量|零增量|本版无[^\n]{0,8}(变更|改动|脚本)|增量[^\n]{0,6}(为空|无内容|无脚本|无变更)"
    r"|无需(执行|升级)[^\n]{0,8}(增量|脚本)?)")


def check_increment_presence(ver_dir, rep):
    """9bis. 增量轨存在性（约定 37.2 两轨对称 + 37.5-7 零变更显式成文）。

    ⛔ 本项补的是一处**只断言了一半**的不对称：全量轨缺失判 ERROR（`check_configs` /
    `check_sql_env_bound` 都有"空即 ERROR"），而增量轨这一侧连"存不存在"都没人问 ——
    `check_increment_terseness` 首行就是 `if not inc.is_dir(): return`。
    于是**从未产出过增量轨的版本，12 项门照样打「🎉 无 ERROR」放行发布**。

    判据按约定 37.5-7 定，⛔ 不是"空即报错"：**零变更是合法结论**（增量轨回答的是
    "已有环境怎么升级"，本版真没改就真的无需升级动作）。不合法的是**空得没有交代** ——
    原文：「在 `00_索引.md` 写清『为什么是零』+ 判据……**不产出空文件，也不省略说明**」。
    ⇒ 三态：有内容 → 过；空但索引里有显式零变更声明 → INFO 过；空且无声明 → ERROR。

    这样「本版确实无变更」与「压根没产增量轨」才第一次在机器上可分辨 ——
    此前两者产物完全同形（都是一个不存在的目录）。
    """
    idx = ver_dir / "00_索引.md"
    idx_text = ""
    if idx.is_file():
        idx_text = idx.read_text(encoding="utf-8", errors="replace")
    declared = bool(_ZERO_DECL_RE.search(idx_text))

    for sub, pat, cn in (("sql", "*.sql", "SQL"), ("配置文件", "*.md", "配置")):
        inc = ver_dir / sub / "增量"
        has = inc.is_dir() and any(inc.glob(pat))
        if has:
            rep.note("增量轨存在性", f"{sub}/增量/ 有产出（{cn} 升级路径已交代）")
        elif declared:
            rep.note("增量轨存在性",
                     f"{sub}/增量/ 为空，但 00_索引.md 已显式声明本版零变更 —— 合法（约定 37.5-7）")
        else:
            rep.error("增量轨存在性",
                      f"{sub}/增量/ 缺失或为空，且 00_索引.md 未显式声明本版零变更 —— "
                      f"「本版真没改」与「压根没产增量轨」产物完全同形，运维无从判断升级要不要做。"
                      f"按约定 37.5-7：确为零变更就在 00_索引.md 写清「为什么是零」+ 判据"
                      f"（SQL 另附只读核验脚本让结论可自证），⛔ 不产出空文件、也不省略说明")


def check_increment_terseness(ver_dir, rep):
    """10. 增量极简度（约定 37.5-6）：增量配置文档只讲「改了什么」，不做第二份论述。

    下游实测：判定方法、执行建议、风险评估、各环境对照表全塞进增量文档 → **真正要看的被淹没**
    （6 份文档 414 行 → 精简后 168 行，-59%，信息零丢失）。判据是确定性的，就不该靠自觉：

      · **Markdown 表格** → 增量该用代码块，表格意味着"代码块 + 下方表格"两处对照（必然漂移），
        或塞进了各环境对照 / 判定依据表（那些归 `全量/00_索引.md`）；
      · **行内注释 > 20 字符** → 注释该写"是什么 / 必配可选"，写不下就说明在写论证。

    两项都是 WARN 不是 ERROR：篇幅是可读性问题，硬拦发布不成比例；但必须**被看见**。
    """
    inc = ver_dir / "配置文件" / "增量"
    if not inc.is_dir():
        return
    for md in sorted(inc.glob("*.md")):
        rel = md.relative_to(ver_dir)
        try:
            lines = md.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        in_code, tables, long_cmts = False, 0, []
        for i, raw in enumerate(lines, 1):
            s = raw.strip()
            if s.startswith("```"):
                in_code = not in_code
                continue
            if in_code:
                # 代码块内：取 # 之后的行内注释（整行注释也算，它同样承载"改了什么"）
                if "#" in raw:
                    cmt = raw.split("#", 1)[1].strip()
                    if len(cmt) > 20:
                        long_cmts.append((i, cmt))
            else:
                # 表格判定：`| a | b |` 形态的分隔行或数据行
                if s.startswith("|") and s.count("|") >= 3:
                    tables += 1
        if tables:
            rep.warn("增量极简度",
                     f"{rel} 含 {tables} 行 Markdown 表格 —— 增量只用代码块；"
                     f"「代码块 + 下方表格」两处对照必然漂移，各环境对照 / 判定依据归 全量/00_索引.md")
        for i, cmt in long_cmts[:5]:
            rep.warn("增量极简度",
                     f"{rel}:{i} 行内注释 {len(cmt)} 字符 > 20 —— 「{cmt[:24]}…」"
                     f"；注释只写\"是什么 / 必配可选\"，论证归 全量/00_索引.md")
        if len(long_cmts) > 5:
            rep.warn("增量极简度", f"{rel} 另有 {len(long_cmts) - 5} 处超长行内注释（已省略）")


def check_yaml_blocks_and_links(ver_dir, rep):
    """2（.md 内 yaml 代码块）+ 9（相对链接有效性）。"""
    for md in sorted(ver_dir.rglob("*.md")):
        rel = md.relative_to(ver_dir)
        try:
            text = md.read_text(encoding="utf-8")
        except Exception:
            continue
        for i, block in enumerate(re.findall(r"```ya?ml\n(.*?)```", text, re.S), 1):
            if _HAS_YAML:
                try:
                    yaml.safe_load(block)
                except Exception as e:
                    rep.error("YAML 语法",
                              f"{rel} 第 {i} 个 yaml 代码块解析失败：{str(e).splitlines()[0]}")
            else:
                for p in yaml_sanity(block):
                    rep.error("YAML 语法", f"{rel} 第 {i} 个 yaml 代码块 {p}")
        for target in MD_LINK_RE.findall(text):
            t = target.split("#")[0].strip()
            if not t or re.match(r"^[a-z][a-z0-9+.\-]*://", t) or t.startswith("mailto:"):
                continue
            if not (md.parent / t).exists():
                rep.error("相对链接", f"{rel} 链接目标不存在：{target}")


def check_ddl_comment_verified(root, ver_dir, version, rep):
    """12. 本版新增列的注释覆盖率**已实查库并落台账**（约定 37.5bis ②）。

    ⛔ **校的是"有没有真去查过库"，不是"脚本里有没有写 COMMENT"**——实际项目中曾出现：SQL 脚本里**写了** `COMMENT ON COLUMN`，但手工执行时只跑了 `ALTER TABLE ADD`
    那一段循环、注释语句**整段被漏掉**，而没有任何一步会发现；事后实查 `ALL_COL_COMMENTS`
    结果是新增 10 列 **10/10 无注释**。**脚本内容正确 ≠ 库里状态正确**——只校脚本会
    **恰好漏掉这次事故的形态**。

    本门不连库（CI 里连不上测试/生产库是常态），改为校验**执行方有没有把实查结果落进台账**：
    要填那张表，就得真去查一次。判定委派 `check_sql_ledger_comment.py`（单一实现，
    ⛔ 不在这里重写一遍 ADD COLUMN 的方言识别——两处各写一份必然漂移）。
    """
    script = root / runtime_relpath("", __file__) / "scripts" / "check_sql_ledger_comment.py"
    if not script.is_file():
        rep.note("DDL 注释实查", "check_sql_ledger_comment.py 不存在，本项跳过")
        return
    try:
        cp = subprocess.run([sys.executable, str(script), "--root", str(root),
                             "--version", version, "--json"],
                            capture_output=True, text=True, timeout=120)
        res = json.loads(cp.stdout or "{}")
    except Exception as exc:                                     # noqa: BLE001
        rep.note("DDL 注释实查", f"判定不可用（{exc}），本项跳过")
        return
    st = res.get("status")
    if st == "no-add-column":
        return                       # 本版不涉及改表结构，静默
    if res.get("passed"):
        rep.note("DDL 注释实查", res.get("detail") or "已实查并落台账")
        return
    rep.error("DDL 注释实查",
              (res.get("detail") or "本版新增列的注释覆盖率未实查")
              + "（约定 37.5bis ②：查 ALL_COL_COMMENTS / information_schema.COLUMNS 的"
                "**实际状态**，把结果填进 SQL执行台账.md「三之二」；脚本里写了 COMMENT 不算）")


def run(root, version):
    rep = Report()
    ver_dir = root / "docs" / "deployment" / version
    if not ver_dir.is_dir():
        return rep, None, f"部署目录不存在：docs/deployment/{version}"
    sql_full, cfg_full = check_structure(ver_dir, rep)
    check_sql_env_bound(sql_full, rep)
    check_configs(cfg_full, rep)
    check_nonyaml_runtime_files(cfg_full, rep)
    check_increment_values(ver_dir, rep)
    check_increment_presence(ver_dir, rep)
    check_increment_terseness(ver_dir, rep)
    check_yaml_blocks_and_links(ver_dir, rep)
    check_ddl_comment_verified(root, ver_dir, version, rep)
    if not _HAS_YAML:
        rep.note("YAML 语法", "PyYAML 不可用，已降级为内置结构自检（Tab 缩进 / 同层重复键）——"
                              "严格语法校验建议在有 PyYAML 的环境补跑一次")
    return rep, ver_dir, None


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="约定 37 版本发布双轨部署基线 —— 12 项确定性校验")
    ap.add_argument("--version", required=True, help="版本号，如 V0.2.0（对应 docs/deployment/<version>/）")
    ap.add_argument("--root", default=".", help="仓库根目录，默认当前目录")
    ap.add_argument("--only", choices=["links"], default=None,
                    help="只跑某一类检查：links = 相对链接有效性。"

                         "供 Step 3.3.7 B 写完部署流程/清单/checklist 后【提前】单跑——"

                         "新建双轨文档时相对深度极易差一层（下游实测写成 ../../../ 实际需 ../../../../），"

                         "等到 3.3.7.9 才发现要回头改一圈")

    ap.add_argument("--json", action="store_true", help="机读 JSON 输出")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    if args.only == "links":
        # 只跑相对链接有效性：供 3.3.7 B 写完部署文档后提前自查，不必等到 3.3.7.9 全量门
        ver_dir = root / "docs" / "deployment" / args.version
        if not ver_dir.is_dir():
            msg = f"版本目录不存在：{ver_dir.relative_to(root)}"
            print(json.dumps({"ok": False, "fatal": msg}, ensure_ascii=False)
                  if args.json else f"❌ {msg}", file=None if args.json else sys.stderr)
            return 2
        rep = Report()
        check_yaml_blocks_and_links(ver_dir, rep)
        links = [e for e in rep.errors if e["check"] == "相对链接"]
        if args.json:
            print(json.dumps({"ok": not links, "only": "links", "errors": links,
                              "count": len(links)}, ensure_ascii=False, indent=2))
        elif links:
            print(f"❌ 相对链接失效 {len(links)} 处（docs/deployment/{args.version}/）：", file=sys.stderr)
            for e in links:
                print(f"   · {e['msg']}", file=sys.stderr)
            print("   → 新建双轨文档时目录深度差一层极常见，逐条核对 ../ 层数", file=sys.stderr)
        else:
            print(f"[OK] 相对链接全部有效（docs/deployment/{args.version}/）")
        return 1 if links else 0

    rep, ver_dir, fatal = run(root, args.version)
    if fatal:
        if args.json:
            print(json.dumps({"ok": False, "fatal": fatal}, ensure_ascii=False))
        else:
            print(f"❌ {fatal}", file=sys.stderr)
        return 2

    payload = {
        "ok": not rep.errors,
        "version": args.version,
        "dir": str(ver_dir.relative_to(root)),
        "errors": rep.errors,
        "warns": rep.warns,
        "notes": rep.notes,
        "counts": {"error": len(rep.errors), "warn": len(rep.warns), "info": len(rep.notes)},
        "yaml_strict": _HAS_YAML,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"📦 约定 37 双轨部署基线校验 — docs/deployment/{args.version}/")
        for level, items, icon in (("ERROR", rep.errors, "❌"),
                                   ("WARN", rep.warns, "⚠️"),
                                   ("INFO", rep.notes, "ℹ️")):
            for it in items:
                print(f"  {icon} [{it['check']}] {it['msg']}")
        print(f"\n  合计：{len(rep.errors)} ERROR / {len(rep.warns)} WARN / {len(rep.notes)} INFO")
        if rep.errors:
            print(runtime_text('  → 有 ERROR，本版全量基线不可发布；逐条修复后重跑（判据见 __AIDP_HOME__/reference/约定细则-5.md）', __file__))
        else:
            print("  🎉 无 ERROR")
    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
