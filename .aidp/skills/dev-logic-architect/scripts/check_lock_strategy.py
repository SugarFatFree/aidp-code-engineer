#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""并发加锁选型合规核验 — dev-logic-architect 维度 32(Critical,对应核心原则 24)

核心约束(核心原则 24「并发加锁选型优先级铁律」):

    P0 进程内锁(语言自带)  →  优先。Java `synchronized`/`ReentrantLock`、Go `sync.Mutex`、
                              Python `threading.Lock`/`asyncio.Lock`、C# `lock`/`SemaphoreSlim` …
    P1 Redis 分布式锁      →  其次,且**必须带自动过期**(TTL / leaseTime / 看门狗续期),
                              防持锁进程崩溃后死锁。
    P2 数据库级锁          →  **谨慎谨慎再谨慎,必须人为确认才可使用**。
                              `SELECT ... FOR UPDATE` / `LOCK TABLES` / `GET_LOCK()` /
                              `pg_advisory_lock` / 悲观锁 / 行锁 / 表锁。

⚠️ **乐观锁(version 字段 + CAS)不是锁**,是无锁并发控制,**不受 P2 约束、仍是推荐做法**;
   唯一索引幂等同理。本脚本刻意不把它们计入 P2,别"顺手"加进去。

检测项:
  L1 (Critical) P2 数据库级锁出现但**无用户确认标注** —— 沿用检查项 23「缓存机制用户确认」
                的三证据模型:① 正文"用户已确认/已征得用户同意"标注 ② 专章「数据库级锁方案(用户已确认 …)」
                ③ Module E `D-NNN` 待澄清/暂行方案条目。三者皆无 = 违规。
  L2 (Critical) P1 Redis 分布式锁出现但**未声明自动过期** —— 无 TTL / 过期 / leaseTime /
                看门狗 / watchdog / 锁超时 任一信号。
  L3 (Important) 用了 P1/P2 却未说明"为何 P0 进程内锁不够"(多实例部署 / 跨进程或跨服务竞争)。
  L4 (Important) 出现并发/竞态/互斥语境却无任何具体锁选型(选型缺失,不判死)。

⚠️ 本脚本只做**关键词级**结构性回检:锁粒度是否合理、临界区是否恰当、死锁风险、
   锁与事务边界的关系,一律由 QR 子 Agent 按检查项 32 语义核验。

⚠️ **输入是「详细设计文档」**,不是本 SKILL 自己的规则文本。SKILL.md /
   quality-review-checklist.md 这类**规范性文档**通篇在讲「数据库级锁必须人为确认」,
   拿它们当输入必然满屏命中 —— 那不是缺陷,是用错了输入。
   (⚠️ 反过来也别为了让规则文档变绿而往护栏里塞「优先使用」这类**选型采纳动词**:
    那会让照本 SKILL 话术书写的**真实设计文档**整档隐形,实测已发生过。)

用法:
  python check_lock_strategy.py <设计文档文件或目录>
  python check_lock_strategy.py <设计文档文件或目录> --json

退出码:
  0  通过 / 跳过(全文无任何加锁信号)
  1  不通过(存在 Critical)
  2  输入错误(路径不存在 / 无 .md 文件)——非维度违规,修正参数后重跑
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# ── P0 进程内锁(语言自带关键字/类型) ──
P0_RE = re.compile(
    r"\bsynchronized\b|\bReentrantLock\b|\bReentrantReadWriteLock\b|\bStampedLock\b|"
    r"\bsync\.(Mutex|RWMutex)\b|\bthreading\.(Lock|RLock)\b|\basyncio\.Lock\b|"
    r"\bSemaphoreSlim\b|\bMonitor\.Enter\b|\bstd::mutex\b|\bMutex\b|"
    r"进程内锁|本地锁|单机锁|语言自带锁|JVM\s*内(部|置)?锁", re.IGNORECASE)

# ── P1 Redis 分布式锁 ──
P1_RE = re.compile(
    r"\bRedisson\b|\bRLock\b|\bSETNX\b|\bSET\s+\w+\s+\w+\s+NX\b|\bRedLock\b|"
    r"分布式锁|redis\s*锁|Redis\s+分布式", re.IGNORECASE)

# ── P2 数据库级锁(⚠️ 不含乐观锁 / 唯一索引幂等) ──
P2_RE = re.compile(
    r"\bSELECT\b[^\n;]{0,120}\bFOR\s+UPDATE\b|\bFOR\s+SHARE\b|"
    r"\bLOCK\s+IN\s+SHARE\s+MODE\b|\bLOCK\s+TABLES?\b|\bGET_LOCK\s*\(|"
    r"\bpg_advisory_lock\w*\s*\(|\bsp_getapplock\b|"
    r"悲观锁|数据库级锁|数据库锁|表级锁|表锁|行级锁|行锁|间隙锁|next-key\s*lock",
    re.IGNORECASE)

# ⚠️ 乐观锁 / 幂等唯一索引:**明确不算锁**,命中即整行豁免 P2(防误判)
OPTIMISTIC_RE = re.compile(r"乐观锁|\bCAS\b|version\s*字段|版本号\s*字段|唯一索引幂等|幂等键")

# ── 自动过期信号(P1 必须有) ──
TTL_RE = re.compile(r"\bTTL\b|过期时间|自动过期|锁超时|超时释放|\bleaseTime\b|\bexpire\b|"
                    r"\bEX\s+\d|\bPX\s+\d|看门狗|watchdog|续期", re.IGNORECASE)

# ── 用户确认标注(三证据,沿用检查项 23 模型) ──
CONFIRM_RE = re.compile(
    r"用户已确认|用户确认|已征得用户同意|用户同意|经用户确认|已经用户确认|"
    r"#+\s*[^\n]{0,20}数据库级锁[^\n]{0,20}(方案|设计)|"
    r"D-\d{3}|🔧\s*暂行方案|❓\s*待澄清")

# ── "为何 P0 不够"的说明信号(L3) ──
WHY_NOT_P0_RE = re.compile(r"多实例|多副本|多节点|集群部署|多\s*Pod|水平扩容|横向扩展|"
                           r"跨进程|跨服务|跨节点|单机锁(?:不足|不够|失效|无法)|"
                           r"进程内锁(?:不足|不够|失效|无法)")

# ── 并发语境(L4) ──
CONCURRENCY_CTX_RE = re.compile(r"并发|竞态|竞争条件|race\s*condition|互斥|临界区|超卖|重复提交|"
                                r"并发冲突|同时(?:操作|修改|提交)", re.IGNORECASE)

# ⚠️ 禁令/排除语境护栏:设计文档要写出"不用什么"才能说清选型
#    ("本方案不使用数据库级锁""严禁 LOCK TABLES""谨慎使用数据库级锁"),
#    不加护栏则规范性表述会被当成实际用了。口径与仓库既有一致:宁可漏报不误报。
NEGATION_GUARD_RE = re.compile(
    # ⚠️ 这里只收**排除性**措辞。曾经错误地收了「优先使用|其次使用|改用|替代|排除|放弃」,
    #    而核心原则 24 的原文就是「P0 **优先使用** → P1 **其次使用** → P2」——
    #    任何照本 SKILL 话术书写的设计文档,加锁行被整行吞掉,P0/P1/P2 全部归零,
    #    脚本打印「未检测到任何加锁信号 → 跳过」并 exit 0。这些词表达的是**选中了什么**,
    #    不是**排除了什么**,绝不能进护栏。
    r"严禁|禁止|不得|不许|不可以|勿|杜绝|反模式|错误示范|❌|"
    r"不使用|未使用|不采用|不引入|无需|不需要|默认不可用|"
    r"不通过|违规|反例|类表述")


# ⚠️ **章节级**豁免:逐行护栏在这里结构上不够——「识别清单」「备选方案(未采用)」「方案对比」这类
#    章节整节都在**列举**锁写法而非采用它,而列举出来的那几行(表格里的 `SELECT ... FOR UPDATE`)
#    本身不含任何禁令词,逐行护栏一个都挡不住。实测本 SKILL 的 stack-db-mysql.md「MySQL 侧识别清单」
#    就被自家硬门判死 4 处。故按标题层级整节豁免,遇到**同级或更高级**标题才结束。
# ⚠️ 刻意**不含**「方案对比 / 选型对比」:设计文档的常规写法是
#    「## 3.2 分布式锁方案对比与选型结论」,**真正采纳的方案就写在这一节里**,
#    整节豁免等于把选型结论一起吞掉(且豁免遇子标题不复位,`### 实现要点` 一并失守)。
EXEMPT_HEADING_RE = re.compile(r"不适用|未采用|不采用|已放弃|备选方案|"
                               r"识别清单|默认不可用|反模式|禁用清单|错误示范")
HEADING_RE = re.compile(r"^(#{1,6})\s")


# ⚠️ 证据必须落在**锁的语境**里,不能全文搜。两个实测的致命假绿灯:
#   · L1 的 CONFIRM_RE 含 `D-\d{3}`,而「Module E 待澄清问题清单」是本 SKILL 的**强制章节**、
#     任何真实设计几乎必有 `D-001` → 与锁毫无关系的一条待澄清就等于「数据库级锁已获用户确认」;
#   · L2 的 TTL_RE 全文搜「过期时间」,而核心原则 17 要求 A.2 写缓存过期策略 → 缓存的 TTL
#     被当成分布式锁的 TTL 声明。
#   二者叠加,维度 32 的两个 Critical 在真实文档里**几乎永不触发**。
#   现改为:证据须与命中点**同章节**,或证据行本身就是锁语境。
LOCK_CTX_RE = re.compile(r"锁|lock|FOR\s+UPDATE|SETNX|Redisson|RLock|互斥|临界区", re.IGNORECASE)


def split_sections(lines: List[str]) -> List[tuple]:
    """按 markdown 标题层级把全文切成 [(start, end, heading), ...](含无标题的前导段)。"""
    heads = []
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m:
            heads.append((i, len(m.group(1)), line))
    if not heads:
        return [(0, len(lines), "")]
    secs = []
    if heads[0][0] > 0:
        secs.append((0, heads[0][0], ""))
    for k, (idx, level, text) in enumerate(heads):
        end = len(lines)
        for j in range(k + 1, len(heads)):
            if heads[j][1] <= level:
                end = heads[j][0]
                break
        secs.append((idx, end, text))
    return secs


def _evidence_in_scope(lines: List[str], secs: List[tuple], hit_line: int,
                       evidence_re, window: int = 25) -> bool:
    """证据是否有效:落在命中点作用域内(最内层章节 ∩ ±window 行),**且证据行本身与锁有关**。

    ⚠️ 两条缺一不可,各自堵一类假绿灯:
      · 只要求「作用域内」——文档没有标题或只有一个一级标题时,唯一 section 覆盖全文、
        最内层=全文,退化回全文搜;文档短于窗口时行窗口同样兜不住。于是
        「商品缓存过期时间 30 分钟」冒充锁的 TTL、无关的「D-001 图片尺寸待确认」
        冒充锁的用户确认 —— 本脚本要防的两个假绿灯原样复活。
      · 只要求「证据行含锁关键词」——附录里一句「历史 v1 曾用 Redis 锁,TTL 30s,现已下线」
        就能给线上的无 TTL 锁洗白。
    故取交集:证据行必须**既在作用域内、又是锁语境**。命中行自身恒算作锁语境。
    """
    idx = hit_line - 1
    lo, hi = max(0, idx - window), min(len(lines), idx + window + 1)
    enclosing = [s for s in secs if s[0] <= idx < s[1]]
    if enclosing:
        start, end, _ = max(enclosing, key=lambda s: s[0])
        lo, hi = max(lo, start), min(hi, end)
    for i in range(lo, hi):
        if evidence_re.search(lines[i]) and (i == idx or LOCK_CTX_RE.search(lines[i])):
            return True
    return False


def find_md_files(path: Path) -> List[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    return []


def scan_file(path: Path, root: Path) -> Dict:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        return {"file": str(path), "read_error": str(exc)}
    try:
        rel = str(path.relative_to(root))
    except ValueError:
        rel = str(path)

    lines = text.splitlines()
    hits = {"P0": [], "P1": [], "P2": []}
    exempt_level = None            # None = 不在豁免区;否则为进入豁免时的标题层级
    for i, line in enumerate(lines, 1):
        hm = HEADING_RE.match(line)
        if hm:
            level = len(hm.group(1))
            if EXEMPT_HEADING_RE.search(line):
                exempt_level = level
            elif exempt_level is not None and level <= exempt_level:
                exempt_level = None    # 同级/上级标题才结束豁免;子标题不复位
        if exempt_level is not None:
            continue
        if NEGATION_GUARD_RE.search(line):
            continue
        for tier, rx in (("P0", P0_RE), ("P1", P1_RE), ("P2", P2_RE)):
            if tier == "P2" and OPTIMISTIC_RE.search(line):
                continue          # 乐观锁 / 幂等键不算数据库级锁
            m = rx.search(line)
            # ⚠️ 裸「Redisson」不算加锁信号:它是**通用 Redis 客户端**,在 A.2 缓存方案的
            #    「客户端库: Lettuce / Redisson(高级特性)」这类选型行里必然出现 ——
            #    实测本 SKILL 自带的设计文档模板就因此被误判 L2。
            #    只有同行还谈到锁/互斥/临界区时,它才真指向分布式锁;`RLock` 等专有 API 不受此限。
            if m and tier == "P1" and m.group(0).lower() == "redisson" \
                    and not re.search(r"锁|互斥|临界区|RLock|getLock", line):
                m = None
            if m:
                hits[tier].append({"line": i, "match": m.group(0)[:40],
                                   "text": line.strip()[:100]})
    return {"file": rel, "text": text, "lines": lines,
            "secs": split_sections(lines), "hits": hits}


def build_findings(results: List[Dict]) -> Dict:
    criticals: List[Dict] = []
    warnings: List[Dict] = []
    for r in results:
        if r.get("read_error"):
            continue
        f, text, hits = r["file"], r["text"], r["hits"]

        # L1 数据库级锁必须人为确认(证据须同章节或落在锁语境行上)
        lines, secs = r.get("lines", []), r.get("secs", [])
        for h in hits["P2"]:
            if not _evidence_in_scope(lines, secs, h["line"], CONFIRM_RE):
                criticals.append({
                    "type": "L1 数据库级锁未经用户确认", "file": f, "line": h["line"],
                    "detail": f"出现数据库级锁「{h['match']}」但全文无用户确认标注。"
                              f"核心原则 24:数据库级锁**必须人为确认才可使用**——"
                              f"须有『用户已确认』标注 / 专章『数据库级锁方案(用户已确认 YYYY-MM-DD)』 / "
                              f"Module E D-NNN 条目三者之一。原文: {h['text']}"})

        # L2 Redis 分布式锁必须带自动过期(证据须同章节或落在锁语境行上)
        # ⚠️ 必须**逐个**命中取证(与 L1 对称)。原先只检 hits["P1"][0]:
        #    3.1 节的锁写了 leaseTime、3.2 节的锁完全没 TTL —— 只看第一个就整份放行。
        for h in [x for x in hits["P1"]
                  if not _evidence_in_scope(lines, secs, x["line"], TTL_RE)]:
            criticals.append({
                "type": "L2 分布式锁未声明自动过期", "file": f, "line": h["line"],
                "detail": f"出现 Redis 分布式锁「{h['match']}」但全文无自动过期声明"
                          f"(TTL / 过期时间 / leaseTime / 看门狗续期 / 锁超时)。"
                          f"持锁进程崩溃将死锁。原文: {h['text']}"})

        # L3 用了 P1/P2 却没说明为何 P0 不够
        if (hits["P1"] or hits["P2"]) and not WHY_NOT_P0_RE.search(text):
            tier = "P1 分布式锁" if hits["P1"] else "P2 数据库级锁"
            warnings.append({
                "type": "L3 未说明为何进程内锁不适用", "file": f, "line": 0,
                "detail": f"用了 {tier} 但未说明为何 P0 进程内锁不够"
                          f"(多实例部署 / 跨进程或跨服务竞争)。核心原则 24 要求优先 P0。"})

        # L4 有并发语境但无任何锁选型
        if CONCURRENCY_CTX_RE.search(text) and not any(hits.values()):
            warnings.append({
                "type": "L4 并发语境无锁选型", "file": f, "line": 0,
                "detail": "文档出现并发/竞态/互斥/超卖/重复提交语境,但未见任何具体加锁选型。"
                          "若确实无需加锁(如纯读、或走乐观锁/唯一索引幂等),请显式写明并说明理由。"})
    return {"criticals": criticals, "warnings": warnings}


def render_text(results: List[Dict], findings: Dict) -> str:
    out: List[str] = ["=== 并发加锁选型合规核验(维度 32 Critical · 核心原则 24) ===\n"]
    total = {t: sum(len(r.get("hits", {}).get(t, [])) for r in results) for t in ("P0", "P1", "P2")}
    out.append(f"加锁信号: P0 进程内锁 {total['P0']} 处 · P1 Redis 分布式锁 {total['P1']} 处 · "
               f"P2 数据库级锁 {total['P2']} 处\n")

    if not any(total.values()):
        out.append("ℹ️ 未检测到任何加锁信号 → 跳过(退出码 0)。")
        out.append("   若本次需求确有并发临界区却全文无锁选型,QR 子 Agent 须按检查项 32 人工核验。")
        return "\n".join(out)

    for r in results:
        if r.get("read_error"):
            out.append(f"[读取失败] {r['file']}: {r['read_error']}")
            continue
        if not any(r["hits"].values()):
            continue
        out.append(f"📄 {r['file']}")
        for tier, label in (("P0", "P0 进程内锁"), ("P1", "P1 Redis 分布式锁"),
                            ("P2", "P2 数据库级锁")):
            for h in r["hits"][tier]:
                out.append(f"   [{label}] L{h['line']}  {h['match']}")
        out.append("")

    crit, warn = findings["criticals"], findings["warnings"]
    if crit:
        out.append(f"❌ 不通过: {len(crit)} 处 Critical\n")
        for v in crit:
            out.append(f"  [{v['type']}] {v['file']}:L{v['line']}  {v['detail']}")
        out.append("")
    else:
        out.append("✅ Critical 全通过: 数据库级锁均有用户确认标注(或未使用),"
                   "Redis 分布式锁均声明了自动过期\n")

    if warn:
        out.append(f"⚠️ Important(不影响退出码,QR 子 Agent 须人工确认): {len(warn)} 处")
        for w in warn:
            out.append(f"  [{w['type']}] {w['file']}  {w['detail']}")
        out.append("")

    out.append("⚠️ 本脚本只做关键词级结构性回检。锁粒度是否合理、临界区是否恰当、"
               "死锁风险、锁与事务边界的关系,仍由 QR 子 Agent 按检查项 32 语义核验。")
    return "\n".join(out)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", type=Path, help="详细设计文档文件或目录")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args(argv)

    if not args.path.exists():
        print(f"错误: 路径不存在 {args.path}", file=sys.stderr)
        return 2

    root = args.path if args.path.is_dir() else args.path.parent
    md_files = find_md_files(args.path)
    if not md_files:
        print("⚠️ 未发现任何 .md 文件", file=sys.stderr)
        return 2

    results = [scan_file(f, root) for f in md_files
               if not (f.name.startswith("00_") or "99_" in f.name)]
    findings = build_findings(results)
    passed = not findings["criticals"]

    if args.json:
        slim = [{"file": r.get("file"), "hits": r.get("hits"),
                 "read_error": r.get("read_error")} for r in results]
        print(json.dumps({"passed": passed, **findings, "files": slim},
                         ensure_ascii=False, indent=2))
    else:
        print(render_text(results, findings))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
