#!/usr/bin/env python3
"""
commit_gate.py — 约定 24「提交前门禁」：每次 `git commit` 前跑一次，读 JSON 决策（确定性）。

把「约定 22 台账积压 / 攒批被绕过 · 约定 31.5 推送欠账 · 约定 41 链外档位 · 模板项目判定 ·
业务代码 / 纯脚手架改动判定」收成单一可信源。作用域 = **变更事实**，与命令入口无关：
裸对话路径（口述 → 改码 → 直接提交）同样适用。

调用：
  python3 AIDP_HOME/scripts/commit_gate.py [--quiet] [--context <ctx>] [--cascade-now] [--no-fail-on-debt]

输出 JSON（stdout）：
  {
    "commit_gate_enabled": bool,     # memory/aidp-config.yaml 的 commit_gate.enabled；缺省 true，仅显式 false 关闭
    "is_template_project": bool,     # aidp-code-engineer SKILL.md + scripts/sync_memory_md.py 都在、且非下游 = 模板项目自身
    "working_tree_dirty": bool,      # 有未提交改动
    "has_business_code_change": bool,  # 待提交改动含实际业务代码（源码扩展名 / code/ 下非文档）；纯文档/配置 = false
    "is_scaffold_only_change": bool, # 改动全落脚手架契约白名单（AIDP_HOME/、Agent 适配层、docs/init/、根 scripts/、.aidp-*、
                                     #   根项目记忆文件 / 版本变更历史.md — 约定 16 同步范围）
    "today": "YYYY-MM-DD",
    "pending_cascade": dict,         # ★ 约定 22：台账摘要 `{files, total, stale, ...}`（**dict 不是 list**）。
                                     #   ⚠️ 计入退出码 3 的是 `stale > 0`（**只含昨天及更早**的条目），不是 `total > 0`。
    "should_dispatch_cascade": bool, # ★ 约定 22：本轮是否该派台账收口子 Agent（= stale > 0）
    "cascaded_not_cleaned": int,     # 已标记级联完成却仍未删除的条目数（同 pending_cascade.cascaded_not_cleaned）
    "suspected_cascade_bypass": dict,  # ★ 约定 22 反向判据：疑似绕过攒批（见 suspected_cascade_bypass()）
    "pending_cicd": dict,            # ★ 约定 31.5：已推送正式代码却未经推送分类器，或分类后部署终态长时间未记录
    "offchain": dict,                # ★ 约定 41：链外任务动作预算 + 规模档位
    "context": str,                  # --context 原样回显（留痕）
    "debts": [str]                   # 未落地义务代号清单（非空 ⇔ 退出码 3）：cascade-stale / cascade-not-cleaned /
                                     #   cascade-unparsed / cascade-archived-not-deleted / cascade-destructive-unregistered /
                                     #   cascade-bypass / cicd-push-pending
  }

★ 未落地义务告警【恒打印到 stderr，`--quiet` 也不压制】+ 退出码说话：
  `--quiet` 的语义是"不要状态叙述"，**不是"不要告诉我欠了什么"**。约定 24 强制的调用写法恰恰是
  `--quiet`——若告警住在 `if not args.quiet:` 里，就等于在唯一被强制执行的路径上从不打印。

退出码：
  - **0** 无欠账（或 commit_gate.enabled=false，或 `--no-fail-on-debt`）；
  - **3** 有未落地义务（任一）：约定 22 台账积压〔`stale > 0`〕· 已级联未清理〔`cascaded_not_cleaned > 0`〕·
    台账格式漂移〔`unparsed` 非空〕· 打了归档标记却未删〔`archived_not_deleted`〕·
    🔴 破坏性变更未在「已知失准点」段登记〔`destructive_unregistered`〕· 疑似绕过攒批 ·
    CICD 推送欠账〔`pending_cicd.pending`〕；
  - **4** 阻塞级（保留档位：义务已升级为必须人工介入时使用；当前判据集不产生该值，消费方仍须按阻塞处理）。
  ⚠️ 3/4 的语义是"**本轮结束前有一项义务未落地**"，**不是"现在禁止 commit"**——命令端见 3/4 照常
  commit+push，之后补上义务（派台账收口子 Agent / 补推送分类与监听）；义务落地后退出码自动回 0。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import json
import os
import re
import subprocess
import sys

SCAFFOLD_SKILL_REL = runtime_text('__AIDP_HOME__/skills/aidp-code-engineer/SKILL.md', __file__)
SCAFFOLD_SYNC_REL = runtime_text('__AIDP_HOME__/skills/aidp-code-engineer/scripts/sync_memory_md.py', __file__)
SCAFFOLD_MARKER_REL = runtime_text('__AIDP_HOME__/skills/aidp-code-engineer/scripts/scaffold_marker.py', __file__)


# ───────────────────────── 配置 / 模板项目判定 ─────────────────────────

def commit_gate_enabled(root: str) -> bool:
    """门禁总开关：memory/aidp-config.yaml 的 commit_gate.enabled（缺省 True，仅显式 false 关闭）。

    读取统一委派 `aidp_config`（单一信源）；模块取不到时视为开启——
    ⛔ 不能因 import 失败就关门，那等于把所有欠账静默抹掉。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aidp_config
        return aidp_config.commit_gate_enabled(root)
    except ImportError:
        return True


def is_template_project(root: str) -> bool:
    """模板项目自身判定。

    ⚠️ 不能只看 aidp-code-engineer 脚手架是否存在——**下游业务项目也携带完整脚手架 skill**
    （供其本地重跑 upgrade），仅靠"引擎存在"会把下游误判为模板项目。故：
      ① `AIDP_HOME/skills/aidp-code-engineer/SKILL.md` 与其 `scripts/sync_memory_md.py` 都存在；
      ② 且下游标记判定为「非下游」（`scaffold_marker.py`，回落 `aidp_config.is_downstream`）。
    """
    skill = os.path.join(root, SCAFFOLD_SKILL_REL)
    sync = os.path.join(root, SCAFFOLD_SYNC_REL)
    has_engine = os.path.isfile(skill) and os.path.isfile(sync)
    return has_engine and not _downstream_marker(root)


def _downstream_marker(root: str) -> bool:
    """下游身份判定：优先 `scaffold_marker.py`，回落 `aidp_config.is_downstream`。

    ⛔ 任何一层取不到都不能直接返回 False：那等于把每个下游都判成模板（取不到 → 判下游）。
    """
    marker = os.path.join(root, SCAFFOLD_MARKER_REL)
    if os.path.isfile(marker):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("_aidp_scaffold_marker", marker)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            for name in ("is_downstream", "is_downstream_project"):
                fn = getattr(mod, name, None)
                if callable(fn):
                    return bool(fn(root))
        except Exception:  # noqa: BLE001 — 取不到就走下一层，不当成"非下游"
            pass
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aidp_config
        return aidp_config.is_downstream(root)
    except ImportError:
        return True


# ───────────────────────── git ─────────────────────────

def _git(root, *args, strip=True):
    """跑 git 子命令。strip=True 默认剔除首尾空白（多数场景要的是干净值）。

    ★ strip=False 用于 `status --porcelain`——porcelain 行首状态位含前导空格（如 ` M path`），
      整体 `.strip()` 会吃掉**首行**的前导空格，令后续按固定列宽 `line[3:]` 解析时首行路径丢首字符
      （`AIDP_HOME/x` → `aidp/x`），破坏基于路径前缀的判定（scaffold_only 等）。故 porcelain 取原文。

    ★ 必带 `-c core.quotePath=false`：默认 git 把非 ASCII 路径输出成 `"...\\347\\272\\246..."`
      （外包双引号 + 八进制转义）。约定 14 要求 AIDP 文档**文件名也用中文**——
      不关掉转义，`_is_business_code` / `_is_scaffold_contract` 这类**按路径前缀/扩展名**的判定
      全部落在错的串上。解析侧另有 `_unquote_path()` 兜底已转义的输入（双保险）。
    """
    try:
        out = subprocess.run(
            ["git", "-c", "core.quotePath=false", "-C", root, *args],
            capture_output=True, text=True, timeout=30,
        )
        return (out.stdout.strip() if strip else out.stdout), out.returncode
    except (subprocess.SubprocessError, OSError):
        return "", 1


def _date(spec=None):
    args = ["date", "+%F"] if spec is None else ["date", "-d", spec, "+%F"]
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=10).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


# ───────────────────────── 约定 22：开发期族增量册 ─────────────────────────

ARCHIVED_MARK = "<!-- LEDGER-ARCHIVED -->"
# ⚠️ 台账解析前必须剥 HTML 注释块（`<!-- … -->`）：模板骨架里的**教学示例**
#    正是 `- C-008 · 08-27 …` 这个形态、写在注释里，不剥就会把「全新的、干净的、
#    完全合规的台账」解析成「2 条待级联」——失败态与合法态在退出码上完全同形。
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _strip_html_comments(text):
    return _HTML_COMMENT_RE.sub("", text)


def _has_archived_mark(text):
    """★ 只认**独占一行**的归档标记。

    标记本身就是 HTML 注释，故不能靠剥注释区分；而教学正文里
    「`<!-- LEDGER-ARCHIVED -->` **不是出路**」这类**行内提及**必须不算数。
    """
    for ln in text.splitlines():
        if ln.strip() == ARCHIVED_MARK:
            return True
    return False


# ★ 约定 22 开发期族增量册（四族各一份，与该族内容主文档【同目录】）。
#   单一信源 = `AIDP_HOME/reference/开发期族增量.md`。
#   ⛔ 落点刻意与主文档同级：收口就是**就地合并**，不跨目录搬运。
CASCADE_FAMILIES = (
    ("req",    os.path.join("docs", "requirements"),          "研发需求", "_开发期需求增量.md"),
    ("design", os.path.join("docs", "design", "detail"),      "",         "_开发期设计增量.md"),
    ("plan",   os.path.join("docs", "plans"),                 "",         "_开发期计划增量.md"),
    ("case",   os.path.join("docs", "testing"),               "研发自测", "_开发期用例增量.md"),
)


def _parse_cascade_entries(text: str, today_md: str):
    """解析一份增量册/台账正文，返回 (n, stale, done, unreg_ids, unparsed)。

    ⛔ **条目格式必须多态识别**：写入侧未必看得到格式约定，自然会挑最顺手的写法
    （一行式 / `###` 重格式 / Markdown 表格）。只认其中一种会让 `stale` 恒 0、收口点从不触发，
    **且完全静默**。故：三种格式都认 + 认不出要吭声。
    ★ 编号允许带子编号（`C-036-01`）。
    """
    seg = text.split("## 待级联", 1)
    body = seg[1] if len(seg) > 1 else text
    body = _strip_html_comments(body)   # 教学示例写在注释里，必须先剥
    # 一行式：`- C-008 · 08-27 16:05 · 描述 · sprint-012`
    # ⚠️ 要求 `- C-NNN ·` 紧邻：「已知失准点」段是 `- 🔴 C-NNN：…`，天然不匹配。
    rows = re.findall(r"^-\s+C-[\d-]+\s*·\s*(\d{2}-\d{2})", body, re.M)
    # `### C-NNN` 形态也必须取日期，否则该形态对 stale 零贡献、永久静默。
    heads = re.findall(r"^###\s+C-[\d-]+([^\n]*)", body, re.M)
    # 表格式：`| C-036-01 | 2026-08-31 | 事实订正 | … |`，日期取第 2 列并归一化到 MM-DD
    tbl = re.findall(r"^\|\s*~{0,2}\s*(C-[\d-]+)\s*~{0,2}\s*\|\s*([^|]*?)\s*\|", body, re.M)

    def _md(raw: str) -> str:
        """从任意条目文本里取 MM-DD；取不到返回空串（调用方按 fail-closed 计 stale）。"""
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})|(?<!\d)(\d{2})-(\d{2})(?!\d)", raw)
        if not m:
            return ""
        return f"{m.group(2)}-{m.group(3)}" if m.group(2) else f"{m.group(4)}-{m.group(5)}"

    tbl_dates = [_md(raw) for _cid, raw in tbl]
    head_dates = [_md(raw) for raw in heads]
    # 已级联却没删的条目（约定 22 要求「成功级联即删」）——只统计、不并进 total
    done = len(re.findall(
        r"^(?:[-|].{0,120})?(?:~~\s*C-[\d-]+|C-[\d-]+[^\n]{0,160}?(?:✅|已级联|已完成级联))",
        body, re.M))
    n = len(rows) + len(heads) + len(tbl)
    # ★ 取不到日期一律计 stale（fail-closed）：无日期 = 无法证明"是今天记的"。
    stale = (sum(1 for md in rows if md != today_md)
             + sum(1 for md in tbl_dates if md != today_md)
             + sum(1 for md in head_dates if md != today_md))
    # ★★ 🔴 破坏性变更必须在「⚠️ 已知失准点」段登记具体失准位置（本机制唯一的缓解手段）。
    _dest_ids = set(re.findall(r"C-[\d-]+", "\n".join(
        ln for ln in body.splitlines() if "🔴" in ln)))
    _drift_seg = text.split("已知失准点", 1)
    _reg_ids = set()
    if len(_drift_seg) > 1:
        _tail = re.split(r"^##\s", _drift_seg[1], maxsplit=1, flags=re.M)[0]
        _reg_ids = set(re.findall(r"C-[\d-]+", _tail))
    unreg = sorted(_dest_ids - _reg_ids)
    # ★ 「看得见但不认识」：漂移启发式只看**条目区**（`## 待级联` 之后、第一条 `---` 之前），
    #   模板骨架在 `---` 之后的填写说明不算实质内容。⚠️ 只裁 unparsed 的判据面，不裁 `n` 的计数面。
    _entry_zone = body.split("\n---", 1)[0]
    meaningful = [ln for ln in _entry_zone.splitlines()
                  if ln.strip() and not ln.lstrip().startswith(("#", ">", "|---", "| ---"))]
    unparsed = (n == 0 and len(meaningful) >= 2)
    return n, stale, done, unreg, unparsed


def cascade_ledger_paths(root: str, version: str):
    """某版本的四族增量册绝对路径，返回 [(family, abspath), ...]。"""
    out = []
    for fam, base, sub, name in CASCADE_FAMILIES:
        parts = [root, base, version] + ([sub] if sub else []) + [name]
        out.append((fam, os.path.join(*parts)))
    return out


def pending_cascade(root: str, today: str = "") -> dict:
    """开发期【族增量册】（约定 22 攒批级联）是否有待级联条目。

    ★ `stale` = **日期不等于今天**的条目数（= 昨天及更早）。收口点只处理这些——当天新增的
    留到明天。派单判据用 `stale` 而**不是** `total`。

    返回 {files, total, stale, cascaded_not_cleaned, unparsed, versions:{V:{…, families:{}}},
          destructive_unregistered, archived_not_deleted}；无册子 → 全 0。
    `unparsed` = **文件有实质内容、却一条都没认出来**的册子（格式漂移信号）。
    """
    today_md = (today or _date())[5:]          # "2026-08-27" → "08-27"（条目日期为 MM-DD）
    out = {"files": [], "total": 0, "stale": 0, "versions": {},
           "cascaded_not_cleaned": 0, "unparsed": [], "destructive_unregistered": [],
           "archived_not_deleted": []}
    archived = out["archived_not_deleted"]

    # ★ 版本集 = 四族根目录下版本目录的**并集**（只扫一棵树会漏掉「本版只改了设计」这类情形）
    versions = set()
    for _fam, base, _sub, _name in CASCADE_FAMILIES:
        d = os.path.join(root, base)
        if os.path.isdir(d):
            versions.update(x for x in os.listdir(d)
                            if os.path.isdir(os.path.join(d, x)))
    if not versions:
        return out

    for v in sorted(versions):
        vinfo = {"total": 0, "stale": 0, "cascaded_not_cleaned": 0,
                 "destructive_unregistered": [], "families": {}}
        for fam, led in cascade_ledger_paths(root, v):
            if not os.path.isfile(led):
                continue
            try:
                with open(led, "r", encoding="utf-8", errors="replace") as f:
                    text = f.read(400_000)
            except OSError:
                continue
            rel = os.path.relpath(led, root)
            # ⛔ `<!-- LEDGER-ARCHIVED -->` **不是出路**：约定 22 要求成功级联的条目即删、
            #    册子清空即删文件——**标记不替代删除**。照常解析计数，打过标记的另行点名。
            if _has_archived_mark(text):
                archived.append(rel)
            n, stale, done, unreg, unparsed = _parse_cascade_entries(text, today_md)
            if unparsed:
                out["unparsed"].append(rel)
            if unreg:
                out["destructive_unregistered"].extend({"file": rel, "id": c} for c in unreg)
            out["files"].append(rel)
            vinfo["families"][fam] = {"file": rel, "total": n, "stale": stale,
                                      "cascaded_not_cleaned": done,
                                      "destructive_unregistered": unreg}
            vinfo["total"] += n
            vinfo["stale"] += stale
            vinfo["cascaded_not_cleaned"] += done
            vinfo["destructive_unregistered"].extend(unreg)
        if vinfo["families"]:
            out["versions"][v] = vinfo
            out["total"] += vinfo["total"]
            out["stale"] += vinfo["stale"]
            out["cascaded_not_cleaned"] += vinfo["cascaded_not_cleaned"]
    return out


# ───────────────────────── 变更路径分类 ─────────────────────────

# 业务源码扩展名（约定 24 门禁判定"实际业务代码修改"；配置/文档/数据类不计入）。
#   口径偏宽（含 .html/.css/.sql 等），宁可多算也别漏掉真实开发活动。
SOURCE_EXTS = {
    ".java", ".kt", ".kts", ".scala", ".groovy", ".go", ".rs", ".py", ".rb",
    ".php", ".cs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".m", ".mm",
    ".swift", ".dart", ".lua", ".vue", ".ts", ".tsx", ".js", ".jsx", ".mjs",
    ".cjs", ".svelte", ".astro", ".html", ".htm", ".css", ".scss", ".sass",
    ".less", ".wxml", ".wxss", ".sql", ".proto", ".graphql",
}
DOC_EXTS = {".md", ".markdown", ".txt", ".rst", ".adoc"}

# ★ 脚手架契约路径白名单（约定 16 同步范围）：由脚手架 init/migrate/upgrade 下发/管理，
#   属"范式契约"而非下游业务开发产物。
#   根因：脚手架自带 .py/.mjs/.cjs/.js 脚本（AIDP_HOME/**、根 scripts/**）本身命中 SOURCE_EXTS，
#   若不按路径排除，纯脚手架升级会被误判为"含业务代码修改"。
#   ⚠️ 边界：只要有一处改动落在白名单外（如 code/ / docs/{version}/ 迭代产物），即视为含真实活动。
#   `AIDP_HOME/` = 单一信源；`.claude/` / `.codex/` / `.dsh/` = 各 Agent 适配层。
SCAFFOLD_CONTRACT_PREFIXES = (runtime_text('__AIDP_HOME__/', __file__), ".claude/", ".codex/", ".dsh/", "docs/init/", "scripts/")
# 根级脚手架文档（下游 upgrade 会同步）：项目记忆文件（AGENTS.md / CLAUDE.md）与版本变更历史
SCAFFOLD_CONTRACT_ROOT_FILES = {"agents.md", "claude.md", "版本变更历史.md"}
# AIDP 自身的入库产物（路径单一信源 = aidp_paths.REGISTRY；此处按字面列出以保持本脚本自包含）
AIDP_RUNTIME_FILES = {"memory/.sprint-autopilot-baseline.json",
                      "memory/aidp-config.yaml"}


def _is_scaffold_contract(path: str) -> bool:
    """单个变更路径是否属"脚手架契约"（约定 16 同步范围）——非下游业务开发产物。"""
    p = path.strip().strip('"')
    low = p.lower()
    if any(low.startswith(pre) for pre in SCAFFOLD_CONTRACT_PREFIXES):
        return True
    if low.startswith(".aidp-"):              # .aidp-rewrite-queue.txt / .aidp-backup-* 等脚手架状态产物
        return True
    # ★ AIDP 自己的运行时状态与人维护配置：不是下游业务产物。
    #   ⛔ 漏登会造成**自我干扰**：AIDP 命令运行时写的状态被下一次 gate 看成"非白名单文件"，
    #   把一次纯脚手架提交改判成含业务产物 —— 判据被它自己的副作用推翻。
    if low in AIDP_RUNTIME_FILES or low.startswith(runtime_text('memory/.aidp/', __file__)):
        return True
    if low in SCAFFOLD_CONTRACT_ROOT_FILES:   # 根级脚手架文档（AGENTS.md / CLAUDE.md / 版本变更历史.md）
        return True
    return False


_C_ESCAPES = {"a": 0x07, "b": 0x08, "f": 0x0C, "n": 0x0A, "r": 0x0D,
              "t": 0x09, "v": 0x0B, "\\": 0x5C, '"': 0x22}


def _unquote_path(path: str) -> str:
    """git 输出的路径串 → 原始路径（去包裹双引号 + 解八进制/C 转义）。**双保险**。

    `_git()` 已带 `-c core.quotePath=false`，正常情况下本函数等价 `.strip()`。
    但输入不止一条来路（外部粘贴的 git 输出、旧 hook、他人脚本），一旦拿到 C-quote 形态，
    所有按路径前缀判断的门禁都会**静默判错**。解码失败 → 原样返回，绝不抛异常打断门禁判定。
    """
    p = path.strip()
    if len(p) >= 2 and p.startswith('"') and p.endswith('"'):
        p = p[1:-1]
    if "\\" not in p:
        return p
    buf = bytearray()
    i, n = 0, len(p)
    try:
        while i < n:
            ch = p[i]
            if ch != "\\":
                buf.extend(ch.encode("utf-8"))
                i += 1
                continue
            nxt = p[i + 1:i + 2]
            oct3 = p[i + 1:i + 4]
            if len(oct3) == 3 and all(c in "01234567" for c in oct3):
                buf.append(int(oct3, 8))
                i += 4
            elif nxt in _C_ESCAPES:
                buf.append(_C_ESCAPES[nxt])
                i += 2
            else:                     # 未知转义：保留反斜杠原样
                buf.extend(ch.encode("utf-8"))
                i += 1
        return buf.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return p


def _porcelain_paths(porcelain: str):
    """解析 git status --porcelain 的变更路径（处理重命名 'a -> b' 取新路径、去引号/解转义）。"""
    paths = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:]
        if " -> " in rest:            # 重命名/拷贝：取目标路径
            rest = rest.split(" -> ", 1)[1]
        paths.append(_unquote_path(rest))
    return paths


def _is_business_code(path: str) -> bool:
    """单个变更路径是否算"业务代码"：源码扩展名（任意位置）或 code/ 下的非文档文件。

    ★ `docs/` 全树一律不计（约定 18：业务源码只落 code/）——`docs/` 下即便含 `.html`/`.css`/`.sql`
      也都是**文档 + 生成产物**（需求/设计/计划/原型代码/AI 报告/部署 SQL artifact）。
      不排除会把 `docs/reports/` 下的 `.html` 报告误计为 has_business_code_change=true。
    """
    p = path.lower()
    ext = os.path.splitext(p)[1]
    if ext in DOC_EXTS:               # .md/.txt 等纯文档：永不计入（即便在 code/ 下）
        return False
    if p.startswith("docs/"):         # docs/ 全树 = 文档/生成产物
        return False
    if p.startswith("code/") and ext:  # 标准业务代码目录（约定 18）下的非文档文件
        return True
    return ext in SOURCE_EXTS         # 源码扩展名（兼容非 code/ 布局）


def has_business_code_change(porcelain: str) -> bool:
    """working tree（待提交改动）里是否有实际业务代码修改。

    ★ 先排除脚手架契约路径再判定——否则脚手架自带的 `.py`/`.mjs`/`.cjs`/`.js` 脚本会被
      SOURCE_EXTS 命中，把"纯脚手架升级"误判成业务代码改动。
    """
    return any(
        _is_business_code(p)
        for p in _porcelain_paths(porcelain)
        if not _is_scaffold_contract(p)
    )


# 约定 22 攒批：上游规划产物的四个族（研发需求 / 详细设计 / 研发执行计划 / 研发自测用例）。
#   ⛔ 只认带 `{version}` 段的迭代产物路径——`docs/requirements/README.md` 这类结构性文件不算。
_PLANNING_DIRS = ("docs/requirements/", "docs/design/", "docs/plans/", "docs/testing/")
# ★ 增量册基名集合（四族）——`suspected_cascade_bypass` 的③用它判"动没动册子"。
_LEDGER_BASENAMES = frozenset(n for _f, _b, _s, n in CASCADE_FAMILIES)

# 结构性新增信号：只认「新增行」里最无歧义的三类（约定 22 第一/二类触发的确定性子集）。
# ⛔ 刻意不认「改了某个方法体」这类——那需要语义判断，误报会让这道门当天被关掉。
_STRUCT_PATTERNS = (
    (re.compile(r"^\+.*@(?:Get|Post|Put|Delete|Patch|Request)Mapping\b"), "新增接口端点"),
    (re.compile(r"^\+.*\b(?:app|router)\.(?:get|post|put|delete|patch)\s*\("), "新增接口端点"),
    (re.compile(r"^\+\s*CREATE\s+TABLE\b", re.I), "新增建表 DDL"),
    (re.compile(r"^\+\s*ALTER\s+TABLE\b.*\bADD\b", re.I), "新增字段 DDL"),
)


def _added_structural_signals(code_files):
    """扫本次待提交 diff 的**新增行**，找结构性新增信号。取不到 diff 时返回空（不臆测）。"""
    out = []
    try:
        r = subprocess.run(["git", "diff", "HEAD", "--unified=0", "--"] + list(code_files)[:60],
                           capture_output=True, text=True, timeout=20)
        # ⚠️ diff 取不到（无 HEAD 等）只跳过新增行扫描，⛔ 不得提前 return 连带跳过下面的新增页面判定
        for ln in (r.stdout.split("\n") if r.returncode == 0 else []):
            for rx, label in _STRUCT_PATTERNS:
                if rx.search(ln):
                    out.append((label, ln.strip()[:80]))
                    break
    except (OSError, subprocess.SubprocessError):
        pass
    # 新增页面文件（未跟踪 / 新增的 .vue/.tsx 视图）
    for q in code_files:
        if re.search(r"/(?:views|pages)/[^/]+\.(?:vue|tsx|jsx)$", q):
            out.append(("新增页面", q))
    return out


def suspected_cascade_bypass(porcelain: str) -> dict:
    """约定 22「攒批被整段绕过」的**反向可检测性**判据（确定性、零语义判断）。

    ⛔ 修的不是"规则没写清楚"，是"**规则清楚但不可检测**"。绕过之后全链路零告警：
    「本轮确实没有实质变更」与「本轮有实质变更、但绕过台账当场改了上游文档」在机器上长得一模一样。

    形态一「当场级联」（三条同时成立才报）：
      ① 本次待提交变更含**正式代码**（复用 `_is_business_code`）；
      ② 同时含**上游规划产物**（`docs/{requirements,design,plans,testing}/{version}/**`）；
      ③ 本次变更里**没有**动过任何族增量册（见 `_LEDGER_BASENAMES`）。
    形态二「结构性新增零台账」：代码含新增接口端点 / 建表或加字段 DDL / 新增页面，而册子一字未动。

    合法例外 = 显式 `--cascade-now`（调用方传入即抑制本判据）。
    """
    paths = [p for p in _porcelain_paths(porcelain) if not _is_scaffold_contract(p)]
    code_hits, plan_hits, ledger_touched = [], [], False
    for p in paths:
        q = p.replace("\\", "/")
        if os.path.basename(q) in _LEDGER_BASENAMES:
            ledger_touched = True
            continue
        if _is_business_code(q):
            code_hits.append(q)
        elif any(q.startswith(d) for d in _PLANNING_DIRS):
            # ★ 必须有 `{version}` 这一段：`docs/plans/README.md` 只有两段、不是迭代产物。
            if len(q.split("/")) >= 4:
                plan_hits.append(q)
    hit = bool(code_hits) and bool(plan_hits) and not ledger_touched

    # ── 形态二：代码有【结构性新增】，却一条台账都没写 ──────────────────────
    struct = []
    if code_hits and not ledger_touched:
        for q in code_hits:
            base = os.path.basename(q)
            if base.endswith(".sql") or "/sql/" in q:
                struct.append(("新增/变更 SQL", q))
            elif q.startswith("docs/prototype/"):
                continue
        struct += _added_structural_signals(code_hits)
    hit2 = bool(struct) and not ledger_touched
    return {
        "suspected": hit or hit2,
        "shape": ("当场级联" if hit else ("结构性新增零台账" if hit2 else "")),
        "code_files": sorted(code_hits)[:5],
        "planning_files": sorted(plan_hits)[:5],
        "structural_signals": [f"{k}: {v}" for k, v in struct[:5]],
        "code_count": len(code_hits),
        "planning_count": len(plan_hits),
        "ledger_touched": ledger_touched,
    }


def is_scaffold_only_change(porcelain: str) -> bool:
    """本次待提交改动是否"全部"落在脚手架契约白名单内（下游纯脚手架升级，无任何业务/迭代产物）。

    空树返回 False。任一改动落在白名单外（`code/` / `docs/{version}/` 等）→ False。
    """
    paths = _porcelain_paths(porcelain)
    return bool(paths) and all(_is_scaffold_contract(p) for p in paths)


# ───────────────────────── 约定 31.5：推送欠账 ─────────────────────────

TERMINAL_GRACE_SECONDS = 60 * 60   # 分类后多久仍无部署终态才算欠账（给监听 / 下个 tick 留时间）


def _iso_ts(v) -> float:
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(v)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _push_records(bl: dict, head: str):
    """baseline 里与 HEAD commit 对应的推送分类记录 → [(version, build|None, record, version_node)]。"""
    out = []
    for v, vo in ((bl or {}).get("versions") or {}).items():
        if not isinstance(vo, dict):
            continue
        for it in vo.get("standalone_pushes") or []:
            if isinstance(it, dict) and str(it.get("commit") or "")[:40] == head[:40]:
                out.append((v, None, it, vo))
        for b in vo.get("builds") or []:
            if not isinstance(b, dict):
                continue
            recs = [it for it in (b.get("pushes") or []) if isinstance(it, dict)]
            if isinstance(b.get("change_classification"), dict):
                recs.append(b["change_classification"])
            for it in recs:
                if str(it.get("commit") or "")[:40] == head[:40]:
                    out.append((v, b.get("build"), dict(it, _build=b), vo))
    return out


def _head_has_formal_change(root: str) -> bool:
    """HEAD 提交是否含正式代码变更（单一信源 = classify_commit_change.py；判不出按否）。"""
    try:
        cp = subprocess.run(
            [sys.executable, os.path.join(root, runtime_text('__AIDP_HOME__/scripts/classify_commit_change.py', __file__)),
             "--root", root, "--base-ref", "HEAD~1", "--json"],
            capture_output=True, text=True, timeout=60)
        return bool(json.loads(cp.stdout or "{}").get("has_formal_code_change"))
    except Exception:  # noqa: BLE001
        return False


def pending_cicd(root: str) -> dict:
    """约定 31.5「推送 ≠ 交付完成」的**欠账信号**。作用域 = 变更事实、与命令入口无关。

    适用条件：`memory/aidp-config.yaml` 的 `cicd.provider != none`，且本地 HEAD 已与上游一致（确实推过了）。
    判据（按 HEAD commit 键控，⛔ 不看「某个 build 曾经分类过」）：
      ① HEAD 含正式代码变更，却在 baseline 里找不到该 commit 的分类记录
         （build 级 `change_classification` / `pushes[]` 或版本级 `standalone_pushes[]`）→ 欠账；
      ② 有记录且为正式代码变更（未 `cicd_skipped`），分类超过 1 小时仍无部署终态
         （记录上的 `deploy_terminal`，或所属版本 `last_deployed_at` 晚于分类时刻，或 build `probe_passed`）→ 欠账。
         `deploy_terminal=unknown:<原因>`（provider 不可用等合法降级）算已记录、不算欠账。
    """
    out = {"applicable": False, "pending": False, "version": None, "build": None, "reason": ""}
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aidp_config
        provider = str(aidp_config.cicd_config(root).get("provider") or "github-actions")
    except Exception:  # noqa: BLE001
        provider = "github-actions"
    if provider == "none":
        return out
    local, _ = _git(root, "rev-parse", "HEAD")
    remote, _ = _git(root, "rev-parse", "@{u}")
    if not local or not remote or local != remote:
        return out                        # 还没 push / 无上游 → 不适用
    out["applicable"] = True
    try:
        with open(os.path.join(root, "memory/.sprint-autopilot-baseline.json"), encoding="utf-8") as f:
            bl = json.load(f)
        bl = bl if isinstance(bl, dict) else {}
    except Exception:  # noqa: BLE001
        bl = {}
    recs = _push_records(bl, local)
    if not recs:
        if _head_has_formal_change(root):
            out.update(pending=True,
                       reason="已推送正式代码（HEAD %s）但无推送分类记录：`classify_push.py --version <V> "
                              "{--build <B> | --standalone}` 未跑（链外推送用 --standalone），部署终态无人知道" % local[:8])
        return out
    import time as _t
    for v, b, rec, vo in recs:
        if rec.get("cicd_skipped") or not (rec.get("formal_code_change") or rec.get("has_formal_code_change")):
            continue
        if rec.get("deploy_terminal"):
            continue
        cls_at = _iso_ts(rec.get("classified_at"))
        bnode = rec.get("_build") or {}
        if _iso_ts(vo.get("last_deployed_at")) >= cls_at > 0 or bnode.get("probe_passed"):
            continue
        if cls_at and _t.time() - cls_at < TERMINAL_GRACE_SECONDS:
            continue
        out.update(pending=True, version=v, build=b,
                   reason="推送（HEAD %s）已分类为正式代码变更，但超过 1 小时仍无部署终态记录："
                          "监听 CICD 后跑 `classify_push.py --record-terminal success|failed|unknown:<原因>`" % local[:8])
        return out
    return out


# ───────────────────────── 约定 41：链外档位 ─────────────────────────

def offchain_budget(root: str, context: str, porcelain: str) -> dict:
    """约定 41：链外任务的**动作预算 + 规模档位**（每次 commit 前随 gate 一并给出）。

    ⛔ 为什么挂在这里：`commit_gate.py` 是约定 24 规定的**每次 commit 前必跑**的入口，
    执行体本就要读它的 JSON。把档位放进同一份 JSON，规矩才在**该被想起的那一刻**出现。

    档位判据（与约定 41.3 同表，⛔ 判不准时从严往高一档走）：
      XS  改动 ≤2 文件 且 无接口/表/口径变更
      S   ≤5 文件、无 DDL
      M   含接口变更 / 口径反转 / DDL
      L   含新表 / 破坏性契约变更 → ⛔ 不在链外做，转正式 /sprint-* 链路

    ⚠️ 本函数只看**改动面**，看不出"口径反转"这种语义性质。故这里给的是**下限**，
    并明确标注 `semantic_check_required` —— ⛔ 别把"脚本说 XS"当成"可以按 XS 做"的免责。
    """
    files = _porcelain_paths(porcelain)
    sql = [f for f in files if f.endswith(".sql")]
    code = [f for f in files if f.startswith("code/")]
    ddl = False
    for f in sql:
        try:
            t = open(os.path.join(root, f), encoding="utf-8", errors="replace").read(20000).upper()
        except OSError:
            continue
        if "CREATE TABLE" in t:
            ddl = "new-table"
            break
        if any(k in t for k in ("ALTER TABLE", "DROP ", "ADD COLUMN")):
            ddl = ddl or "alter"
    n = len(code) or len(files)
    if ddl == "new-table":
        tier = "L"
    elif ddl:
        tier = "M"
    elif n <= 2:
        tier = "XS"
    elif n <= 5:
        tier = "S"
    else:
        tier = "M"
    actions = {
        "XS": {"unit_test": False, "sprint_archive": False, "deploy": False},
        "S": {"unit_test": True, "sprint_archive": False, "deploy": False},
        "M": {"unit_test": True, "sprint_archive": True, "deploy": "ask-user"},
        "L": {"unit_test": True, "sprint_archive": True, "deploy": "ask-user"},
    }[tier]
    return {
        "applies": context == "bare-conversation",
        "tier": tier,
        "tier_floor_only": True,
        "semantic_check_required": "口径反转 / 接口契约变更 看不出改动面，须执行体自判后可上调档位",
        "changed_files": len(files),
        "code_files": len(code),
        "ddl": ddl or None,
        # 恒定禁止项（与档位无关）——约定 41.2
        "forbidden": ["铸 build", "浏览器实测"],
        "deploy": actions["deploy"],
        "actions": actions,
        "always_required": ["约定22 增量册", "约定24 提交前门禁", "约定31.5 推送分类", "静态验证(约定35)"],
        "note": ("约定 41：链外任务 ⛔ 不铸 build、⛔ 不跑浏览器实测（归 /sprint-aiauto-test 独立链路）、"
                 "部署默认否（须用户在本次请求里显式要求）。L 档 ⛔ 不在链外做，转正式 /sprint-* 链路。"
                 "⛔ 档位只伸缩动作集，不伸缩可追溯性。"),
    }


# ───────────────────────── 汇总 ─────────────────────────

def gather(root: str, context: str = "bare-conversation", cascade_now: bool = False) -> dict:
    enabled = commit_gate_enabled(root)
    is_tpl = is_template_project(root)
    today = _date()
    porcelain, _ = _git(root, "status", "--porcelain", strip=False)  # 取原文：保首行前导空格，见 _git
    dirty = bool(porcelain.strip())
    cascade = pending_cascade(root, today)
    bypass = suspected_cascade_bypass(porcelain)
    if cascade_now:
        bypass = dict(bypass, suspected=False, suppressed_by="--cascade-now")
    return {
        "commit_gate_enabled": enabled,
        "is_template_project": is_tpl,
        "working_tree_dirty": dirty,
        "has_business_code_change": has_business_code_change(porcelain),
        "is_scaffold_only_change": is_scaffold_only_change(porcelain),
        "today": today,
        # ★ 约定 22 攒批级联台账（AIDP_HOME/reference/开发期族增量.md）
        "pending_cascade": cascade,
        # ★ 判据 = 台账有【昨天及更早】的待级联条目。同日重复收口由台账内容自然收敛
        #   （收口后条目即删、stale 归零）；多 git 用户防重靠 push 后重判。
        "should_dispatch_cascade": bool(cascade["stale"]),
        # 已标记级联完成却未删除的条目数（= pending_cascade.cascaded_not_cleaned，顶层便于命令端直读）
        "cascaded_not_cleaned": int(cascade.get("cascaded_not_cleaned") or 0),
        "suspected_cascade_bypass": bypass,
        "pending_cicd": pending_cicd(root),
        "offchain": offchain_budget(root, context, porcelain),
        "context": context,
    }


def debt_items(info: dict) -> list:
    """未落地义务清单（与退出码 3 的判据逐项对齐）。"""
    casc = info.get("pending_cascade") or {}
    items = []
    if int(casc.get("stale") or 0) > 0:
        items.append("cascade-stale")
    if int(casc.get("cascaded_not_cleaned") or 0) > 0:
        items.append("cascade-not-cleaned")
    if casc.get("unparsed"):
        items.append("cascade-unparsed")
    if casc.get("archived_not_deleted"):
        items.append("cascade-archived-not-deleted")
    if casc.get("destructive_unregistered"):
        items.append("cascade-destructive-unregistered")
    if (info.get("suspected_cascade_bypass") or {}).get("suspected"):
        items.append("cascade-bypass")
    if (info.get("pending_cicd") or {}).get("pending"):
        items.append("cicd-push-pending")
    return items


def _print_obligations(info: dict) -> None:
    """未落地义务告警区 —— 【恒打印，`--quiet` 也不压制】。"""
    casc = info.get("pending_cascade") or {}
    stale = int(casc.get("stale") or 0)
    if stale > 0:
        sys.stderr.write(
            runtime_text(f"📒 开发期变更台账有 {stale} 条昨天及更早的条目未级联"
            f"（共 {casc.get('total') or 0} 条，涉及版本 "
            f"{'/'.join((casc.get('versions') or {}).keys()) or '-'}）→ 约定 22 收口点 1："
            "本次 commit+push 完成后派后台子 Agent 批量级联并清账；"
            "详规 `__AIDP_HOME__/reference/开发期族增量.md`\n", __file__))

    byp = info.get("suspected_cascade_bypass") or {}
    if byp.get("suspected"):
        if byp.get("shape") == "结构性新增零台账":
            sys.stderr.write(
                f"🚧 疑似绕过约定 22 攒批（结构性新增零台账）：本次改了 {byp.get('code_count')} 个"
                f"正式代码文件，其中含**新增接口 / 新增建表 DDL / 新增页面**这类必然触发约定 22 的\n"
                f"   结构性新增，而四族增量册（及存量台账）**一条都没动**。\n"
                f"   信号：{'; '.join(byp.get('structural_signals') or []) or '-'}\n"
                "   → ⛔ 册子为空时，收口点 3 会因「册子不存在」判为合法终态直接放行，\n"
                "     本次变更从此无人知晓。合规路径 = **先记一行台账**。\n")
        else:
            sys.stderr.write(
                f"🚧 疑似绕过约定 22 攒批：本次同时改了 {byp.get('code_count')} 个正式代码文件与 "
                f"{byp.get('planning_count')} 份上游规划产物，但四族增量册（及存量台账）均无对应改动。\n"
                f"   代码：{', '.join(byp.get('code_files') or []) or '-'}\n"
                f"   规划：{', '.join(byp.get('planning_files') or []) or '-'}\n"
                "   → 合规路径 = **先记台账**（一行一条），由收口点批量级联；确要当场级联请显式\n"
                "     `--cascade-now`。⛔ 作用域 = **变更事实、与命令入口无关**：裸对话路径\n"
                "     （口述→直接改码→直接提交）同样必须先记台账。\n")

    unparsed = casc.get("unparsed") or []
    if unparsed:
        sys.stderr.write(
            runtime_text(f"⚠️ 台账存在但**未识别出任何条目**（疑似格式漂移）：{', '.join(unparsed)}\n"
            "   → 本机制只认三种条目形态（一行式 `- C-NNN · MM-DD ·` / `### C-NNN` / "
            "表格首列 `| C-NNN |`）。请按 `__AIDP_HOME__/templates/_开发期族增量.md` 校正格式，"
            "否则收口点永不触发、台账会无限增长且零告警。\n", __file__))

    dirty = int(casc.get("cascaded_not_cleaned") or 0)
    if dirty > 0:
        sys.stderr.write(
            f"🧹 台账有 {dirty} 条**已标记级联完成却仍未删除**的条目"
            "（约定 22：成功级联即删、清空即删文件）→ 收口时一并清理；⛔ **标记不替代删除**\n")

    arch = casc.get("archived_not_deleted") or []
    if arch:
        sys.stderr.write(
            f"🗃️ {len(arch)} 份台账打了 `<!-- LEDGER-ARCHIVED -->` 却仍留着："
            f"{', '.join(arch[:4])}\n"
            "   → 约定 22 要求**成功级联的条目即删、台账清空即删文件**——**标记不替代删除**。\n"
            "   → 若因目标文档里写了 `C-NNN` 编号引用而删不掉：先把引用处改写成\n"
            "     **变更内容与理由本身**（台账是中转站、不承担长期溯源），再把台账真删掉。\n")

    cicd = info.get("pending_cicd") or {}
    if cicd.get("pending"):
        sys.stderr.write(
            runtime_text(f"🚄 本次推送未经推送分类器（版本 {cicd.get('version')} / build {cicd.get('build')}）"
            "——约定 31.5「**推送 ≠ 交付完成**」。\n"
            "   → `git push` 之【前】跑 `python3 __AIDP_HOME__/scripts/classify_push.py --root . "
            "--version <V> --build <B> --base-ref <BASE>`；\n"
            "     无正式代码变更记 `cicd_skipped=true` 即算完成；有变更须 `cicd_watch.py` "
            "监听至终态 + 就绪探针。\n"
            "   ⛔ 作用域 = **推送这一事实、与命令入口无关**：裸对话路径同样适用。\n", __file__))

    dest = casc.get("destructive_unregistered") or []
    if dest:
        sys.stderr.write(
            f"\n⛔ 台账有 {len(dest)} 条 🔴 破坏性变更**未在「⚠️ 已知失准点」段登记**：\n"
            + "".join(f"   · {d['id']}  ({d['file']})\n" for d in dest[:8])
            + "   → 增量攒着只是「文档暂时不全」，破坏性攒着是「文档明确是错的」——\n"
              "     失准点段是唯一的缓解手段，请补登具体失准位置。\n")

    if debt_items(info):
        sys.stderr.write(
            "📋 本轮存在未落地义务 → **执行体必须在本轮回复的用户可见文本里列出该清单**"
            "（欠了什么 · 补做什么 · 何时补），不得只留在工具输出里\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="约定 24 提交前门禁：台账积压 / 推送欠账 / 链外档位 / 模板判定")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--quiet", action="store_true", help="只输出 JSON，不输出状态叙述（未落地义务告警仍打印）")
    ap.add_argument("--no-fail-on-debt", action="store_true",
                    help="有未落地义务时仍返回 0（逃生阀；⛔ 不要在约定 24 的常规判定调用里加）")
    ap.add_argument("--context", default="bare-conversation",
                    choices=["bare-conversation", "aidp-command"],
                    help="调用上下文，仅作留痕与约定 41 档位适用性判定。"
                         "AIDP 命令内的 commit 前判定传 aidp-command；自然语言对话里的直接提交用默认值")
    ap.add_argument("--cascade-now", action="store_true",
                    help="本轮显式当场级联（约定 22 唯一合法例外）→ 抑制 suspected_cascade_bypass 告警")
    args = ap.parse_args(argv)

    info = gather(args.repo_root, context=args.context, cascade_now=args.cascade_now)
    info["debts"] = debt_items(info) if info["commit_gate_enabled"] else []
    print(json.dumps(info, ensure_ascii=False))

    if not info["commit_gate_enabled"]:
        if not args.quiet:
            sys.stderr.write("⏹️ 提交前门禁已关闭（memory/aidp-config.yaml commit_gate.enabled=false）\n")
        return 0
    if not args.quiet:
        if info["is_template_project"]:
            sys.stderr.write("ℹ️ 模板项目自身\n")
        if info["is_scaffold_only_change"]:
            sys.stderr.write("ℹ️ 本次改动全落在脚手架契约白名单内（纯脚手架升级）\n")
        elif info["working_tree_dirty"] and not info["has_business_code_change"]:
            sys.stderr.write("ℹ️ 本次改动无业务代码（纯文档/配置）\n")

    _print_obligations(info)

    if args.no_fail_on_debt:
        return 0
    return 3 if info["debts"] else 0


if __name__ == "__main__":
    sys.exit(main())
