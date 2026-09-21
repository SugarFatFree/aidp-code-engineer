#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""任务粒度 + EPIC 完整性 + AI 指令锚点检查
   (对应 dev-execution-planner 维度 3「子功能粒度」+ 维度 14「EPIC 完整性 + AI 锚点」)

扫描研发执行计划文件,识别:
1. Task 标题/描述中的聚合性词汇(等/及/相关/一系列/所有/全部/整体...)
2. 单 Task 跨越多个接口/表/页面的合并嫌疑
3. Task 引用章节跨度过大(>100 行,说明粒度太粗)
4. 缺失 `**依赖**:` 字段(扁平并列无依赖图)
5. (维度 14a) EPIC 完整性 — 每个 EPIC 章节下必须出现"前端 / 后端 / 测试"
   三类小节(除非 EPIC 头部明示「单端」)
6. (维度 14b) AI 指令上下文锚点 — 每个 Task 的 AI 执行指令代码块必须 grep
   `详见.*\\.md.*§|§A-|§B-|§[0-9]+\\.[0-9]+` 命中至少 2 处锚点

退出码:
  0  无疑似问题
  1  存在疑似粗粒度(警告) **或** 确证粗粒度 / 旧版 6 列任务表 / 9 列任务表行三锚点不全(错误,需必修)
     ⚠️ 「警告」与「错误必修」曾分别用 1 / 2 两档,2 与全仓统一约定「2 = 入参错」撞码,
        已并入 1。严重度分档改从 --json 的 findings[].severity 读(1=警告 / 2=错误必修)。
        --json 顶层为对象:{scanned_tasks, skipped, findings[]}。skipped=true 表示一个 Task
        段都没识别到——是「没扫到」不是「扫过且干净」,调用方不得当作通过。
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑

用法:
  python check_task_granularity.py <研发执行计划路径>
  python check_task_granularity.py <研发执行计划路径> --json
  python check_task_granularity.py <研发执行计划路径> --strict      # 警告也返回 1
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 聚合性词汇 — 出现在 Task 标题中即提示
AGGREGATE_WORDS = [
    "等", "及", "相关", "一系列", "所有", "全部", "整体", "全套", "若干", "多个",
]

# 明确粗粒度词汇 — 出现在 Task 标题中即视为确证粗粒度
# 注:`\w+管理(?:后端|前端)开发` 已覆盖「用户/订单/商品管理…开发」等具体表述
# (Python re 的 `\w` 在 Unicode 模式下匹配中文),无需再单列同类具体模式。
COARSE_PATTERNS = [
    r"\w+管理(?:后端|前端)开发",
    r"实现(?:所有|全部)接口",
    r"创建(?:所有|全部)(?:数据库|表)",
    r"\w+模块(?:后端|前端)开发",
    r"开发\w+模块",
]

# 强 CRUD 合并嫌疑(增删改查同时出现)
CRUD_KEYWORDS_COMBO = [
    ("增", "删", "改", "查"),
    ("新增", "编辑", "删除"),
    ("新增", "修改", "删除"),
    ("create", "read", "update", "delete"),
    ("CRUD",),
]

SECTION_RANGE_LIMIT = 100

# ⚠️ 四井号与省略冒号必须一并认：锚死「三井号 + 冒号」时，`#### Task 1.1:` 与
#    `### Task 1.1 标题`（无冒号）整段不进扫描，脚本打印「✅ 未发现粒度/EPIC/锚点问题」
#    且 --json 输出裸 [] —— 与「全部 Task 通过」完全不可区分（见 main() 的 scanned_tasks）。
TASK_HEADER_RE = re.compile(r"^#{3,4}\s+Task\s+(\d+\.\d+)[:：]?\s*(.+?)$", re.MULTILINE)
DEPENDENCY_RE = re.compile(r"\*\*依赖\*\*\s*[:：]")
LINE_RANGE_RE = re.compile(r"L\s*(\d+)\s*[-~–]\s*L?\s*(\d+)")

# 维度 14 EPIC 检测
EPIC_HEADER_RE = re.compile(r"^##\s+EPIC[-\s]?(\d+)[:：]\s*(.+?)$", re.MULTILINE)
SINGLE_END_MARK = re.compile(r"单端|仅前端|仅后端|纯前端|纯后端|前端独立|后端独立")
FRONTEND_SECTION_RE = re.compile(r"###\s+(?:前端任务|前端 Task|Frontend)", re.IGNORECASE)
BACKEND_SECTION_RE = re.compile(r"###\s+(?:后端任务|后端 Task|Backend)", re.IGNORECASE)
TEST_SECTION_RE = re.compile(r"###\s+(?:测试任务|测试 Task|Testing|QA)", re.IGNORECASE)

# 维度 14a 的 REQ↔EPIC 双向索引核验
# 在 EPIC 头部抽取 "REQ 编号:" 字段,在文档末尾找索引表
# 兼容两种文档措辞:样本用「REQ ↔ EPIC ↔ Sprint 三级索引表」,SKILL.md/checklist 用「REQ 归属对照表」
REQ_IN_EPIC_HEAD_RE = re.compile(r"REQ\s*编号[^\n]*?(REQ-\d+(?:[^\nA-Za-z]+REQ-\d+)*)")
REQ_ID_RE = re.compile(r"REQ-\d+")
INDEX_TABLE_HEADER_RE = re.compile(r"REQ.*EPIC.*Sprint.*索引|REQ\s*↔\s*EPIC\s*↔\s*Sprint|REQ\s*归属(?:对照)?表")

# AI 指令锚点正则
AI_ANCHOR_RE = re.compile(
    r"详见.*\.md.*§|§A-|§B-|§\d+\.\d+|设计来源[::].*\.md|"
    r"PRD 来源[::].*\.md|原型来源[::]",
)
# AI 执行指令代码块:围栏可为 ``` 或 ~~~(SKILL.md 任务模板/前端示例用 ~~~,样本用 ```,
# 生成的计划两者皆可能出现);用反向引用 \1 匹配同类型闭合围栏,避免只认 ``` 时把 ~~~
# 包裹的合规 AI 块误判为"缺失代码块"(假阳性)。
AI_BLOCK_RE = re.compile(
    r"\*\*AI 执行指令\*\*[\s\S]*?(`{3}|~{3})[\s\S]*?\1",
    re.MULTILINE,
)

# 维度 14c: 9 列任务表 + 三类锚点同时命中
# 9 列:Task | 描述 | REQ 关联 | 设计锚点 | 原型锚点 | 责任人 | 估时 | AI 执行指令 | 验收标准
TABLE_HEADER_RE = re.compile(
    r"^\|\s*Task\s*\|\s*描述\s*\|\s*(?:REQ\s*关联|REQ)\s*\|\s*"
    r"(?:设计锚点|设计)\s*\|\s*"
    r"(?:原型锚点|原型)\s*\|\s*"
    r"(?:责任人|负责人)\s*\|\s*"
    r"(?:估时|工时|预估)\s*\|\s*"
    r"AI\s*执行指令\s*\|\s*"
    r"验收标准\s*\|",
    re.IGNORECASE,
)
# 旧版 6 列(命中即 severity=2 硬拦 → 退出码 1 且 --json severity=2,整表强制重写;见维度 14c)
LEGACY_TABLE_HEADER_RE = re.compile(
    r"^\|\s*Task\s*\|\s*描述\s*\|\s*(?:REQ\s*关联|REQ)\s*\|\s*"
    r"(?:责任人|负责人)\s*\|\s*(?:估时|工时)\s*\|\s*验收标准\s*\|",
    re.IGNORECASE,
)
# ⚠️ 上面两条都是**精确列序**正则,只认「恰好 9 列」与「恰好旧版 6 列」两种形态。
#    实测最可能发生的偏离并不是整表退回旧版 6 列,而是**少写一两列**——8 列(删掉原型锚点)
#    或 7 列(删掉设计锚点+原型锚点)既不进 9 列校验、也不算旧版 6 列,**整表零检查**:
#    一张同时踩了「缺原型锚点 / 模糊引用『参考详细设计』/ 非 markdown 链接」三条 Critical
#    规则的 8 列表,实测 exit 0、零 finding。故补一条**宽松识别器**兜底。
# ⚠️ 首格用**宽松匹配**:写成 `Task ID` / `任务编号` 的 8 列表原先整表零检查 ——
#    「只认精确形态」正是本识别器要修的病根,别在自己身上再犯一次。
# ⚠️ 同时要求**列数 ≥5** 消歧:附录里的「| 任务 | 描述 | 状态 |」进度表不是任务汇总表,
#    无此限制会把它判成缺 7 列、severity=2 硬阻断。
LOOSE_TASK_HEADER_RE = re.compile(
    r"^\|[^|]{0,12}?(?:Task|任务)[^|]{0,8}\|\s*描述\s*\|", re.IGNORECASE)


def _cell_count(header_line: str) -> int:
    return len([c for c in header_line.strip().strip("|").split("|")])
# 规定的 9 列列名(用于给出"缺了哪几列"的具体诊断)
REQUIRED_TASK_COLUMNS = ["Task", "描述", "REQ 关联", "设计锚点", "原型锚点",
                         "责任人", "估时", "AI 执行指令", "验收标准"]
COLUMN_ALIASES = {
    "Task": ("task", "任务"), "描述": ("描述",), "REQ 关联": ("req关联", "req"),
    "设计锚点": ("设计锚点", "设计"), "原型锚点": ("原型锚点", "原型"),
    "责任人": ("责任人", "负责人"), "估时": ("估时", "工时", "预估"),
    "AI 执行指令": ("ai执行指令", "ai指令"), "验收标准": ("验收标准",),
}


def missing_task_columns(header_line: str):
    """返回规定 9 列里表头缺失的列名清单。"""
    cells = [c.strip().strip("*` ").lower().replace(" ", "")
             for c in header_line.strip().strip("|").split("|")]
    missing = []
    for col in REQUIRED_TASK_COLUMNS:
        if not any(any(a in c for a in COLUMN_ALIASES[col]) for c in cells):
            missing.append(col)
    return missing


# 任务表行三正则同时命中(行内同时含 design / requirements / prototype 三类路径)
DESIGN_PATH_RE = re.compile(r"docs/design[^\s|]*\.md|design.*\.md", re.IGNORECASE)
REQ_PATH_RE = re.compile(
    r"docs/requirements[^\s|]*\.md|docs/prd[^\s|]*\.md|requirements.*\.md|prd.*\.md|REQ-\d+",
    re.IGNORECASE,
)
PROTOTYPE_PATH_RE = re.compile(
    r"docs/prototype[^\s|]*\.(?:jsx|tsx|html|vue|js|ts|md)?|prototype.*\.(?:jsx|tsx|html|vue)|"
    r"docs/ui[^\s|]*\.(?:jsx|tsx|html|vue|js|ts)|<\w+[A-Z]\w*>",
    re.IGNORECASE,
)

# 链接合规度校验:任务表「设计锚点」/「原型锚点」列必须 markdown 链接
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
ABSOLUTE_PATH_RE = re.compile(r"^(?:https?://|/|[A-Z]:[/\\]|~/)")
FILE_EXT_RE = re.compile(
    r"\.(md|markdown|jsx|tsx|html|htm|vue|js|ts|css|less|scss|sql|fig|sketch|xd|"
    r"png|jpg|jpeg|webp|gif|svg|docx|doc|pdf|json|yaml|yml|"
    r"java|kt|py|go|cs|rb|rs|swift|xlsx|xls|csv|excalidraw|drawio)(#|$|\?|\s)",
    re.IGNORECASE,
)


# 锚点等级排序: section(最精细) > line > component > html > none
_GRADE_ORDER = {"section": 4, "line": 3, "component": 2, "html": 1, "none": 0}
def _grade_rank(g: str) -> int:
    return _GRADE_ORDER.get(g, 0)


def check_link_quality_in_row(row: str) -> Dict:
    """检查任务表行是否含合规 markdown 链接"""
    matches = MARKDOWN_LINK_RE.findall(row)
    if not matches:
        return {"has_markdown_link": False, "has_relative_path": False,
                "has_file_ext": False, "has_anchor": False, "anchor_grade": "none"}
    has_relative = all(not ABSOLUTE_PATH_RE.match(p.strip()) for p in matches)
    has_ext = any(FILE_EXT_RE.search(p) for p in matches)
    has_anchor = any("#" in p for p in matches)
    grade = "none"
    for p in matches:
        if "#" not in p:
            continue
        anchor = p.split("#", 1)[1]
        if re.search(r"L\d+", anchor):
            grade = max(grade, "line", key=_grade_rank); continue
        if re.search(r"^[一二三四五六七八九十0-9]+[-\.·]", anchor) or re.search(r"§|REQ-|FR-|B-\d|A-\d|C-\d|Task-\d", anchor):
            grade = max(grade, "section", key=_grade_rank); continue
        if re.search(r"<\w+[A-Z]\w*>|^[A-Z]\w*Page$|^[A-Z]\w*Component$", anchor):
            grade = max(grade, "component", key=_grade_rank); continue
        if anchor:
            grade = max(grade, "html", key=_grade_rank)
    return {"has_markdown_link": True, "has_relative_path": has_relative,
            "has_file_ext": has_ext, "has_anchor": has_anchor, "anchor_grade": grade}



def load_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def extract_tasks(text: str) -> List[Dict]:
    """提取所有 Task 块"""
    tasks: List[Dict] = []
    matches = list(TASK_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        task_id = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        tasks.append({
            "id": task_id,
            "title": title,
            "body": body,
            "title_line": text[:m.start()].count("\n") + 1,
        })
    return tasks


def extract_epics(text: str) -> List[Dict]:
    """提取 EPIC 块"""
    epics: List[Dict] = []
    matches = list(EPIC_HEADER_RE.finditer(text))
    for i, m in enumerate(matches):
        eid = m.group(1)
        title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end]
        epics.append({
            "id": eid,
            "title": title,
            "body": body,
            "line": text[:m.start()].count("\n") + 1,
        })
    return epics


def detect_aggregate_words(title: str) -> List[str]:
    return [w for w in AGGREGATE_WORDS if w in title]


def detect_coarse_pattern(title: str) -> Optional[str]:
    for pat in COARSE_PATTERNS:
        if re.search(pat, title):
            return pat
    return None


# 逐行护栏:声明边界的句子必然要写出被排除的动作名,不能因此把 Task 判成「CRUD 合并」
CRUD_BOUNDARY_GUARD_RE = re.compile(r"仅|只|不含|不在本\s*Task|不属于|另见|见\s*Task\s*\d+\.\d+|严禁|排除|分别由")


def detect_crud_merge(title: str, body: str) -> Optional[Tuple[str, ...]]:
    # ⚠️ body 必须逐行过护栏:实测「本 Task **仅**实现新增弹窗;编辑弹窗见 Task 4.4、删除确认见
    #    Task 4.5,严禁在本 Task 内合并实现」这句**声明排除边界**的话,同时含新增/编辑/删除三词,
    #    3 选 2 即命中 → severity 2 → 整表 QR 不通过强制重写。**Task 边界写得越清楚越容易被判死**,
    #    而同文件的表格行检查本来就有 `❌|反例|严禁示例` 豁免,这里漏了。
    kept = [ln for ln in body[:500].splitlines() if not CRUD_BOUNDARY_GUARD_RE.search(ln)]
    text = f"{title} " + " ".join(kept)
    for combo in CRUD_KEYWORDS_COMBO:
        hits = [k for k in combo if k in text]
        # 阈值: 多元素组合需命中 len-1(如 4 选 3、3 选 2);单元素组合(如 ("CRUD",))命中 1 即算
        # 注: 此前用 max(2, len-1),对单元素组合阈值恒为 2、永不触发 —— 改 max(1, ...) 修复
        if len(hits) >= max(1, len(combo) - 1):
            return tuple(hits)
    return None


def detect_oversized_reference(body: str) -> List[Tuple[int, int]]:
    oversized: List[Tuple[int, int]] = []
    for m in LINE_RANGE_RE.finditer(body):
        start = int(m.group(1))
        end = int(m.group(2))
        if end - start > SECTION_RANGE_LIMIT:
            oversized.append((start, end))
    return oversized


def has_dependency(body: str) -> bool:
    return bool(DEPENDENCY_RE.search(body[:1000]))


def check_epic_completeness(epic: Dict) -> List[str]:
    """维度 14a EPIC 完整性 + 头部链接合规度"""
    issues: List[str] = []
    # head 范围: 从 EPIC 标题起到第一个 `### ` 子标题为止;若无子标题则整个 EPIC body
    body = epic["body"]
    sub_match = re.search(r"^###\s+", body, re.MULTILINE)
    head = body[:sub_match.start()] if sub_match else body
    is_single = bool(SINGLE_END_MARK.search(head))

    # EPIC 头部链接合规度: 含 `REQ-NNN` 或 `REQ 编号` 关键词的行必须用 markdown 链接
    # 反例豁免: ❌/反例 行跳过
    head_lines = head.splitlines()
    counterexample_remaining = 0
    for line in head_lines:
        if re.search(r"❌|反例|错误示例", line):
            counterexample_remaining = 3
            continue
        if counterexample_remaining > 0:
            counterexample_remaining -= 1
            continue
        # 仅审查含 REQ-NNN 或 REQ 编号 / 关联 REQ 关键词的行
        if not (re.search(r"REQ-\d+|REQ\s*编号|关联\s*REQ", line)):
            continue
        # 跳过 N/A / 无 行
        if re.search(r"N/A|无\s*$|无\s*[)）]", line):
            continue
        link_q = check_link_quality_in_row(line)
        if not link_q["has_markdown_link"]:
            issues.append(f"EPIC 头部 REQ 引用缺 markdown 链接(纯文本路径): {line.strip()[:100]}")
        elif not link_q["has_relative_path"]:
            issues.append(f"EPIC 头部 REQ 引用使用绝对路径: {line.strip()[:100]}")

    if is_single:
        return issues

    has_fe = bool(FRONTEND_SECTION_RE.search(epic["body"]))
    has_be = bool(BACKEND_SECTION_RE.search(epic["body"]))
    has_test = bool(TEST_SECTION_RE.search(epic["body"]))
    missing = []
    if not has_fe:
        missing.append("前端任务")
    if not has_be:
        missing.append("后端任务")
    if not has_test:
        missing.append("测试任务")
    if missing:
        issues.append(f"缺失类目: {', '.join(missing)}(EPIC 必须含「前端 / 后端 / 测试」三类,除非 EPIC 头部明示「单端」)")
    return issues


def check_ai_anchors(task: Dict) -> Optional[str]:
    """维度 14b AI 指令锚点透传"""
    ai_match = AI_BLOCK_RE.search(task["body"])
    if not ai_match:
        return "缺失 `**AI 执行指令**` 代码块"
    ai_text = ai_match.group(0)
    anchor_hits = AI_ANCHOR_RE.findall(ai_text)
    if len(anchor_hits) < 2:
        return f"AI 执行指令锚点不足(命中 {len(anchor_hits)} 处, 需 ≥ 2 处:详见 X.md §A-N / 设计来源 / PRD 来源 等)"
    return None


def analyze_file(path: Path, root: Path) -> List[Dict]:
    findings: List[Dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings
    try:  # Python 3.8 兼容:不用 3.9+ 的 is_relative_to
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    # 维度 3: Task 粒度
    tasks = extract_tasks(text)
    no_dep_count = 0
    for t in tasks:
        issues: List[str] = []
        severity = 0

        agg = detect_aggregate_words(t["title"])
        if agg:
            issues.append(f"聚合性词汇: {', '.join(agg)}")
            severity = max(severity, 1)

        coarse = detect_coarse_pattern(t["title"])
        if coarse:
            issues.append(f"明确粗粒度命名(模式: {coarse})")
            severity = max(severity, 2)

        crud = detect_crud_merge(t["title"], t["body"])
        if crud:
            issues.append(f"CRUD 合并嫌疑(命中: {' / '.join(crud)})")
            severity = max(severity, 2)

        oversized = detect_oversized_reference(t["body"])
        if oversized:
            spans = ", ".join(f"L{s}-L{e}({e - s} 行)" for s, e in oversized)
            issues.append(f"引用章节跨度过大: {spans}")
            severity = max(severity, 1)

        if not has_dependency(t["body"]):
            no_dep_count += 1

        # 维度 14b AI 锚点
        anchor_issue = check_ai_anchors(t)
        if anchor_issue:
            issues.append(f"维度 14b: {anchor_issue}")
            severity = max(severity, 1)

        if issues:
            findings.append({
                "dim": "3+14b",
                "file": rel,
                "task_id": t["id"],
                "title": t["title"],
                "line": t["title_line"],
                "issues": issues,
                "severity": severity,
            })

    if tasks and no_dep_count == len(tasks) and len(tasks) >= 3:
        findings.append({
            "dim": "3",
            "file": rel,
            "task_id": "*",
            "title": "(全文件)",
            "line": 1,
            "issues": [f"全部 {len(tasks)} 个 Task 均无 **依赖**: 字段, 形成扁平并列, 缺依赖图"],
            "severity": 1,
        })

    # 维度 14a: EPIC 完整性
    epics = extract_epics(text)
    for ep in epics:
        ep_issues = check_epic_completeness(ep)
        if ep_issues:
            findings.append({
                "dim": "14a",
                "file": rel,
                "task_id": f"EPIC-{ep['id']}",
                "title": ep["title"],
                "line": ep["line"],
                "issues": ep_issues,
                "severity": 1,  # warning
            })

    # 维度 14a: REQ ↔ EPIC ↔ Sprint 双向索引核验
    if epics:
        # 抽取每个 EPIC 头部声明的 REQ 编号
        epic_req_map: Dict[str, List[str]] = {}  # EPIC-NN -> [REQ-NN, ...]
        for ep in epics:
            head = ep["body"][:1500]
            m = REQ_IN_EPIC_HEAD_RE.search(head)
            if m:
                req_ids = REQ_ID_RE.findall(m.group(1))
                epic_req_map[f"EPIC-{ep['id']}"] = req_ids

        has_index_table = bool(INDEX_TABLE_HEADER_RE.search(text))
        if not has_index_table:
            findings.append({
                "dim": "14a",
                "file": rel,
                "task_id": "*",
                "title": "(全文件)",
                "line": 1,
                "issues": ["缺失 REQ↔EPIC 索引表(需含「REQ 归属对照表」或「REQ ↔ EPIC ↔ Sprint 三级索引表」之一,且带「所属 EPIC」列)"],
                "severity": 1,
            })
        else:
            # 在索引表中抽取 REQ-NN 与 EPIC-NN 映射,与 EPIC 头部声明比对
            # 简化抽取: 在索引表段落内找 同行出现 REQ-NN 与 EPIC-NN 的 markdown 表格行
            table_match = INDEX_TABLE_HEADER_RE.search(text)
            tail = text[table_match.start():]
            table_rows = re.findall(r"^\|.*\|\s*$", tail, re.MULTILINE)
            index_pairs: Dict[str, str] = {}  # REQ-NN -> EPIC-NN
            for row in table_rows:
                req_m = REQ_ID_RE.search(row)
                epic_m = re.search(r"EPIC-\d+", row)
                if req_m and epic_m:
                    index_pairs[req_m.group(0)] = epic_m.group(0)

            # 双向校验
            for epic_id, req_ids in epic_req_map.items():
                for rid in req_ids:
                    if rid not in index_pairs:
                        findings.append({
                            "dim": "14a",
                            "file": rel,
                            "task_id": epic_id,
                            "title": f"REQ↔EPIC 索引缺失: {rid}",
                            "line": 1,
                            "issues": [f"EPIC 头部声明 {rid},但索引表中未列出该 REQ"],
                            "severity": 1,
                        })
                    elif index_pairs[rid] != epic_id:
                        findings.append({
                            "dim": "14a",
                            "file": rel,
                            "task_id": epic_id,
                            "title": f"REQ↔EPIC 索引冲突: {rid}",
                            "line": 1,
                            "issues": [f"EPIC 头部声明 {rid} 属 {epic_id},但索引表中 {rid} → {index_pairs[rid]}"],
                            "severity": 1,
                        })

    # 维度 14c: 9 列任务表 + 三类锚点同时命中
    # 识别所有 markdown 任务表
    lines = text.splitlines()
    in_table = False
    table_header_line = -1
    table_kind = None  # "9col" | "legacy"
    table_data_rows = []
    legacy_tables: List[Tuple[int, str]] = []
    malformed_tables: List[Tuple[int, str, List[str]]] = []
    nine_col_violations: List[Tuple[int, str, List[str]]] = []

    for i, line in enumerate(lines, start=1):
        if TABLE_HEADER_RE.match(line):
            in_table = True
            table_header_line = i
            table_kind = "9col"
            table_data_rows = []
            continue
        if LEGACY_TABLE_HEADER_RE.match(line) and not in_table:
            legacy_tables.append((i, line))
            continue
        # 宽松兜底:是任务汇总表,但列序既不是规定 9 列、也不是旧版 6 列 → 缺列,硬拦
        if LOOSE_TASK_HEADER_RE.match(line) and not in_table and _cell_count(line) >= 5:
            miss = missing_task_columns(line)
            if miss:
                malformed_tables.append((i, line, miss))
            else:
                # 9 列齐全但列名/顺序与精确正则不完全一致(如首列写「任务」而非「Task」):
                # 表本身合规,但**行级三锚点校验**必须照跑,否则又是一个只差一个字的逃检口。
                in_table = True
                table_header_line = i
                table_kind = "9col"
                table_data_rows = []
            continue
        # 表内行(以 | 开始 + 含 | 分隔符)
        if in_table:
            if line.strip().startswith("|") and "|" in line.strip()[1:]:
                # 跳过对齐分隔行 (--- | --- | ...)
                if re.match(r"^\|\s*[:|\-\s]+\|", line):
                    continue
                table_data_rows.append((i, line))
            else:
                # 表结束,核验每行三正则同时命中 + 链接合规度
                for row_line, row in table_data_rows:
                    has_design = bool(DESIGN_PATH_RE.search(row))
                    has_req = bool(REQ_PATH_RE.search(row))
                    has_proto = bool(PROTOTYPE_PATH_RE.search(row))
                    missing = []
                    if not has_design:
                        missing.append("设计锚点")
                    if not has_req:
                        missing.append("REQ/PRD 引用")
                    if not has_proto:
                        missing.append("原型锚点")
                    # 反例豁免: 行内出现 ❌/反例/严禁示例 时跳过链接核验(任务表反例展示场景)
                    is_counterexample = bool(re.search(r"❌|反例|错误示例|严禁的格式|严禁示例", row))
                    # 链接合规度(反例行豁免)
                    if not is_counterexample:
                        link_q = check_link_quality_in_row(row)
                        if not link_q["has_markdown_link"]:
                            missing.append("markdown 链接(必须 [文本](相对路径))")
                        elif not link_q["has_relative_path"]:
                            missing.append("相对路径(链接含绝对路径)")
                        elif not link_q["has_file_ext"]:
                            missing.append("文件后缀")
                    if missing:
                        nine_col_violations.append((row_line, row.strip()[:120], missing))
                in_table = False
                table_kind = None

    # 收尾(文件结束时表还在)
    if in_table:
        for row_line, row in table_data_rows:
            has_design = bool(DESIGN_PATH_RE.search(row))
            has_req = bool(REQ_PATH_RE.search(row))
            has_proto = bool(PROTOTYPE_PATH_RE.search(row))
            missing = []
            if not has_design:
                missing.append("设计锚点")
            if not has_req:
                missing.append("REQ/PRD 引用")
            if not has_proto:
                missing.append("原型锚点")
            # 反例豁免
            is_counterexample = bool(re.search(r"❌|反例|错误示例|严禁的格式|严禁示例", row))
            # 链接合规度(反例行豁免)
            if not is_counterexample:
                link_q = check_link_quality_in_row(row)
                if not link_q["has_markdown_link"]:
                    missing.append("markdown 链接(必须 [文本](相对路径))")
                elif not link_q["has_relative_path"]:
                    missing.append("相对路径(链接含绝对路径)")
                elif not link_q["has_file_ext"]:
                    missing.append("文件后缀")
            if missing:
                nine_col_violations.append((row_line, row.strip()[:120], missing))

    # 缺列任务表(既非规定 9 列、也非旧版 6 列)
    for line_num, line, miss in malformed_tables:
        findings.append({
            "dim": "14c",
            "file": rel,
            "task_id": "*",
            "title": "(任务表)",
            "line": line_num,
            "issues": [f"任务汇总表列不合规,缺少: {' / '.join(miss)}。"
                       f"维度 14c 规定 9 列固定顺序:"
                       f"Task | 描述 | REQ 关联 | 设计锚点 | 原型锚点 | 责任人 | 估时 | "
                       f"AI 执行指令 | 验收标准"],
            "severity": 2,
        })

    # 旧版 6 列表格警告
    for line_num, line in legacy_tables:
        findings.append({
            "dim": "14c",
            "file": rel,
            "task_id": "*",
            "title": "(任务表)",
            "line": line_num,
            "issues": [f"使用旧版 6 列任务表 (Task|描述|REQ 关联|责任人|估时|验收标准),"
                       f"应升级为 9 列含「设计锚点 / 原型锚点 / AI 执行指令」"],
            "severity": 2,  # error - 任一行不合规即整表重写
        })

    # 9 列表行不合规
    for row_line, row_snippet, missing in nine_col_violations:
        findings.append({
            "dim": "14c",
            "file": rel,
            "task_id": "*",
            "title": "(任务表行)",
            "line": row_line,
            "issues": [f"任务表行缺少 {','.join(missing)} 引用 — 设计/REQ/原型 三类锚点必须同时命中。"
                       f"行: {row_snippet}"],
            "severity": 2,  # error - 一行不合规整张表重写
        })

    return findings


def render_text(findings: List[Dict]) -> str:
    out: List[str] = []
    out.append("=== 任务粒度 + EPIC + AI 锚点检查 ===")
    if not findings:
        out.append("\n✅ 未发现粒度/EPIC/锚点问题")
        return "\n".join(out)

    errors = [f for f in findings if f["severity"] == 2]
    warnings = [f for f in findings if f["severity"] == 1]
    out.append(f"\n🔴 确证粗粒度 Task: {len(errors)}")
    for f in errors:
        out.append(f"  - {f['file']}:{f['line']}  [{f['dim']}] {f['task_id']} 「{f['title']}」")
        for i in f["issues"]:
            out.append(f"      • {i}")
    out.append(f"\n🟡 疑似粗粒度 / EPIC 缺端 / AI 锚点不足: {len(warnings)}")
    for f in warnings:
        out.append(f"  - {f['file']}:{f['line']}  [{f['dim']}] {f['task_id']} 「{f['title']}」")
        for i in f["issues"]:
            out.append(f"      • {i}")

    out.append("\n⚠️ 修复指引:")
    out.append("  [维度 3]  每个 B.2 接口 / 每张 A.3 表 / 每个 PRD 功规点 / 每个页面 → 独立 Task")
    out.append("  [维度 3]  每个 Task 必须有 **依赖**: Task X.Y 字段, 形成依赖图")
    out.append("  [维度 14a] 每个 EPIC 必须含「前端任务 + 后端任务 + 测试任务」三类小节(单端 EPIC 在头部明示「单端」)")
    out.append("  [维度 14b] AI 执行指令代码块至少含 2 处锚点(详见 X.md §A-N / 设计来源 / PRD 来源)")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="研发执行计划路径(单文件或目录)")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--strict", action="store_true", help="任何疑似都返回非零")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = load_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    all_findings: List[Dict] = []
    scanned_tasks = 0
    for f in md_files:
        try:
            scanned_tasks += len(TASK_HEADER_RE.findall(f.read_text(encoding="utf-8", errors="replace")))
        except OSError:
            pass
        all_findings.extend(analyze_file(f, root))

    if args.json:
        # ⚠️ 裸 [] 无法区分「0 个 Task 被扫描」与「全部 Task 通过」，而 QR 子 Agent 被要求
        #    读 --json 每条的 severity 来分档——它从 [] 里读不出到底有没有真的检查过。
        #    故顶层改为对象并带 scanned_tasks / skipped（全仓约定第 3 条）。
        print(json.dumps({
            "scanned_tasks": scanned_tasks,
            "skipped": scanned_tasks == 0,
            "findings": all_findings,
        }, ensure_ascii=False, indent=2))
    else:
        if scanned_tasks == 0:
            print("⚠️ 未识别到任何 Task 段（期望标题形态 `### Task X.Y: 标题`，四井号与省略冒号亦可）。")
            print("   本次**未做实质核验**，不等于通过；请确认标题形态或转 QR 子 Agent 人工核验。")
        print(render_text(all_findings))

    has_error = any(f["severity"] == 2 for f in all_findings)
    has_warning = any(f["severity"] == 1 for f in all_findings)
    if has_error:
        return 1
    if has_warning:
        return 1
    if args.strict and all_findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
