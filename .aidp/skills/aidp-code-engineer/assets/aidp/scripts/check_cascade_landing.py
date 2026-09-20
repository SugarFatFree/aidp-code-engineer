#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 22 收口机器门（两个模式，各管收口的一头）。

**模式 A（默认）— 落点门**：开发期级联**直接改各族内容主文档**（`01_` 等）+ 可刷 `00_索引.md`。

开发期变更记进**四族增量册**（与各族内容主文档同目录），收口时直接把结论写进主文档、
写完增量册条目即删——一次到位，中间没有第二层中转。

本门只管**一个收口批次内的落点**，不管别的：
  给定 `--base-ref`（收口开始前的 HEAD），四族目录下被改动的 .md 里
  **不得出现** `NN_<业务主题>.md`（产品侧 PRD/原型变更与口述累进的命名空间）；
  改主文档、`00_索引.md`、以及**族增量册本身**（收口时在其中删条目）均属正常落点。

⛔ 刻意**不做**全仓扫描：发布期收敛、`/version` 规划期生成、人工修订错别字
   都会合法地改主文档。范围锚在 base-ref 上，语义才是确定的。

**模式 B（`--ledger-closed`）— 台账终态门**：收口跑完后，台账**该删的必须已删**。

「成功级联的条目即删、清空即删文件」这条规则写了三处（`reference/开发期族增量.md`
「清理规则」+ `flows/version/planning-8.md` Step 2.7.4 + `flows/version/release-5.md`
Step 3.3.9.5），但三处**全是纯文字、零机器校验**——执行体级联完把台账留着，规划期与
发布期都照样通过。于是台账跨版本堆积：内容既在正式文档里、又在台账里，下一次收口还得
重新判断"这条到底级联过没有"，正是详规明令要杜绝的第二份信源。

本门两档严格度，**按收口点选**：

**① `--must-delete`（版本收口点 2 / 3 用）——目标版本台账必须【不存在】，无任何保留场景。**
  版本规划必定清掉上一版本的台账、版本发布必定清掉本版本的台账。未能级联的条目
  **不许留在台账里**充当"下次再说"：规划期把它们**迁移进当前版本台账**（继续攒批），
  发布期把它们**转记 `docs/audit/{version}/发布欠账.md`**（`--finalize-docs` 驱动补跑）。
  条目因此不会丢，而台账文件本身在这两个收口点上恒为"不存在"这一个终态。
  ⛔ `<!-- LEDGER-ARCHIVED -->` 不放行——**标记不替代删除**，任何档都要真删；
     仍被引用的 `C-NNN` 编号先在引用处改写为自然语言再删档。

**② 默认档（收口点 4 `/sprint-batch` 用）——"文件存在" ⟺ "确有未决条目"。**
  批次收尾时版本仍在开发中，未决条目留到下个收口点是正常节奏，只禁"已级联却不删"：
  · 台账文件不存在                     → PASS
  · 整档打了 `<!-- LEDGER-ARCHIVED -->`  → FAIL：标记不替代删除
  · 有条目、且并非条条都已标记级联完成    → PASS（打印剩几条）
  · 文件在、却一条未决条目都没有          → FAIL：该删没删（空台账 / 条条已级联）
  · 有实质内容却一条都解析不出            → FAIL：格式漂移，无从证明已收口（不 fail-open）

条目解析复用 `commit_gate.pending_cascade()`，**不另写一套正则**——写两套必然漂移，
而这两个门恰恰要对同一份台账给出一致的读数。

fail-closed：base-ref 解析不了 / git 读不到 / 版本目录识别不出 / 台账读不出 → 非 0 退出，
不假装通过（这类门一旦 fail-open，等于没有）。
"""
import argparse
import json
import os
import re
import subprocess
import sys

# 四族目录模板（{v} = 版本号）；与 .aidp/reference/开发期族增量.md「收口执行要点」第 3 条对齐
FAMILIES = [
    ("需求", "docs/requirements/{v}/研发需求"),
    ("设计", "docs/design/detail/{v}"),
    ("计划", "docs/plans/{v}"),
    ("用例", "docs/testing/{v}/研发自测"),
]

# ★ 四族增量册基名——它们是**开发期变更的唯一承载**，收口时在这里删条目、清空即删文件，
#   因此在收口批次里被改动是**合法落点**（只有一层承载，不存在「台账 → 增量册 → 主文档」的叠加）。
FAMILY_LEDGERS = {
    "_开发期需求增量.md", "_开发期设计增量.md",
    "_开发期计划增量.md", "_开发期用例增量.md",
}
# `NN_<业务主题>.md` 是**产品侧 PRD/原型变更 + 口述累进**的命名空间，收口级联不占它。
_NN_DOC_RE = re.compile(r"^\d{2}_.+\.md$")
_VERSION_RE = re.compile(r"^V\d+\.\d+")


def _git(root, *args):
    # ⛔ `-c core.quotepath=false` 不可省：本项目文档路径全是中文，git 默认把非 ASCII
    #    转义成 `"docs/\345\274\200..."`，路径一律匹配不上 → 本门恒报"0 份改动、合规"，
    #    正是最坏的 fail-open（实测：原地改主文档的反例也被判通过）。
    try:
        cp = subprocess.run(["git", "-C", root, "-c", "core.quotepath=false", *args],
                            capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if cp.returncode != 0:
        return None, (cp.stderr or "").strip() or f"git {' '.join(args)} 失败"
    return cp.stdout, None


def discover_versions(root):
    """扫四族的父目录，取出所有 V 开头的版本目录名。"""
    found = set()
    for parent in ("docs/requirements", "docs/design/detail", "docs/plans", "docs/testing"):
        base = os.path.join(root, parent)
        if not os.path.isdir(base):
            continue
        try:
            for name in os.listdir(base):
                if _VERSION_RE.match(name) and os.path.isdir(os.path.join(base, name)):
                    found.add(name)
        except OSError:
            continue
    return sorted(found)


def changed_files(root, base_ref, worktree):
    """收口批次内改动的文件 → [(path, is_new)]（path 为相对仓库根的 posix 路径）。

    ★ `is_new` 不可省。落点变成"直接改内容主文档"之后，**`01_研发需求.md`（主文档）与
      `07_订单主题.md`（`NN_<业务主题>.md` 增量）在文件名上完全同形**——都是两位数字前缀 +
      中文名，正则区分不了。唯一确定性的判据是**这份文件是不是本批次新建的**：
      收口级联只**改既有文档**，任何新建分册都不属它的落点。
    """
    if worktree:
        out, err = _git(root, "status", "--porcelain")
        if out is None:
            return None, err
        rows = []
        for line in out.splitlines():
            if len(line) < 4:
                continue
            code, path = line[:2], line[3:]
            if " -> " in path and code.strip().startswith("R"):
                path = path.split(" -> ", 1)[1]
            # `A`（已暂存新增）与 `??`（未跟踪）都是"本批次新建"
            rows.append((path.strip().strip('"'), "A" in code or code == "??"))
        return rows, None
    out, err = _git(root, "diff", "--name-status", f"{base_ref}..HEAD")
    if out is None:
        return None, err
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        st, path = parts[0], parts[-1]
        rows.append((path.strip(), st.startswith("A")))
    return rows, None


def run(root=".", base_ref=None, version=None, worktree=False):
    root = os.path.abspath(root)
    if not worktree and not base_ref:
        return {"ok": False, "error": "base-ref-required",
                "detail": "必须给 --base-ref（收口开始前的 HEAD）或 --worktree"}
    if not worktree:
        _, err = _git(root, "rev-parse", "--verify", f"{base_ref}^{{commit}}")
        if err:
            return {"ok": False, "error": "bad-base-ref", "detail": err}

    versions = [version] if version else discover_versions(root)
    if not versions:
        return {"ok": False, "error": "no-version-dir",
                "detail": "四族父目录下找不到任何 V 开头的版本目录；无法界定级联落点范围"}

    files, err = changed_files(root, base_ref, worktree)
    if files is None:
        return {"ok": False, "error": "git-read-failed", "detail": err}

    # 本门作用域 = 四族的版本目录（其余路径一概不管）
    scoped_dirs = [tpl.format(v=v) for _fam, tpl in FAMILIES for v in versions]
    scoped = set(scoped_dirs)

    violations, landed = [], []
    for path, is_new in files:
        path = path.replace("\\", "/")
        if not path.endswith(".md"):
            continue
        parent = os.path.dirname(path)
        if parent not in scoped:
            continue                      # 不在四族版本目录内，本门不管
        name = os.path.basename(path)
        # ★ 族增量册：收口时在这里删条目、清空即删文件 → 本批次改动它属正常落点。
        #   「内容有没有真的并进主文档」由**模式 B 终态门**负责（文件在 ⟺ 确有未决条目），
        #   本门只管落点、不重复判定（两个门正交，各管一头）。
        if name in FAMILY_LEDGERS:
            landed.append(path)
            continue
        # ⛔ 新建分册：`NN_<业务主题>.md` 属产品侧 PRD/原型变更与口述累进的命名空间，
        #    收口级联只改既有文档。**判据是"新建"而非文件名**——主文档 `01_研发需求.md`
        #    与增量 `07_订单主题.md` 名字同形，正则分不开，只有"是不是本批次新建的"确定。
        # `00_索引.md` 是导航锚、任何时候新建都合法（约定 15），不受本条约束
        if is_new and _NN_DOC_RE.match(name) and not name.startswith("00_"):
            violations.append({
                "path": path, "expected": f"{parent} 下已有的内容主文档",
                "reason": ("收口级联**只改既有主文档、不新起分册**；"
                           "`NN_<业务主题>.md` 是产品侧 PRD/原型变更与口述累进的落点"),
            })
            continue
        landed.append(path)               # 既有主文档 / 00_索引.md：本就是级联该落的地方

    return {
        "ok": not violations,
        "scope": "worktree" if worktree else f"{base_ref}..HEAD",
        "versions": versions,
        "scanned_dirs": scoped_dirs,
        "landed": sorted(landed),
        "violations": violations,
    }


def _ledger_paths():
    """复用 commit_gate 的族增量册路径表（同目录）。

    ⛔ 不在本文件另拼一份：路径拼错的失败形态是**静默漏检**（该扫的文件根本没被看到，
    输出与"都合规"完全同形）。两个门必须对同一组文件给出一致读数。
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from commit_gate import cascade_ledger_paths   # noqa: E402
    return cascade_ledger_paths


FAMILY_LABEL = {"req": "需求", "design": "设计", "plan": "计划", "case": "用例"}
ARCHIVED_MARK = "<!-- LEDGER-ARCHIVED -->"
# ⚠️ 台账解析前必须剥 HTML 注释块（`<!-- … -->`）：模板骨架里的**教学示例**
#    正是 `- C-008 · 08-27 …` 这个形态、写在注释里，不剥就会把「全新的、干净的、
#    完全合规的台账」解析成「2 条待级联」——失败态与合法态在退出码上完全同形。
#    （实测：原样拷模板 → total=2 / stale=2 → commit_gate 每次 commit 恒 return 3。）
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def _strip_html_comments(text):
    return _HTML_COMMENT_RE.sub("", text)


def _has_archived_mark(text):
    """★ 只认**独占一行**的归档标记。

    标记本身就是 HTML 注释，故不能靠剥注释区分；而教学正文里
    「`<!-- LEDGER-ARCHIVED -->` **不是出路**」这类**行内提及**必须不算数——
    否则模板一拷进来就恒判「已归档未删」。真实标记恒独占一行，判据取这一点。
    """
    for ln in text.splitlines():
        if ln.strip() == ARCHIVED_MARK:
            return True
    return False



def _pending_cascade():
    """复用 commit_gate 的台账解析（同目录）。两个门必须对同一份台账读数一致。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from commit_gate import pending_cascade   # noqa: E402
    return pending_cascade


def _open_entries_in_text(rel, text):
    """算一段台账文本里还剩几条未决条目。

    把文本落到临时目录的**相同相对路径**再交给 `pending_cascade` —— 解析口径因此与
    收口点 1 / 默认档**同一套**，不在这里重写一遍正则（写两套必然漂移）。
    """
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        dst = os.path.join(tmp, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as f:
            f.write(text)
        pc = _pending_cascade()(tmp)
        # ★ 不从路径猜版本号：新落点里 `dirname` 可能是「研发需求」而非版本目录
        #   （`docs/requirements/V1/研发需求/_开发期需求增量.md`），猜错就恒返回 0 =
        #   「删前已无未决条目」= 静默放行必删档，正是本门最不该出现的 fail-open。
        #   临时目录里只写了这一份文件，故直接跨版本求和，与路径形态无关。
        total = done = 0
        for info in (pc.get("versions") or {}).values():
            t = int(info.get("total") or 0)
            total += t
            done += min(int(info.get("cascaded_not_cleaned") or 0), t)
        return total - done


def _deleted_ledger_open_count(root, rel):
    """台账已不在工作区时，从 git 取回它、算出被带走的未决条目数。

    ⛔ 这是必删档的**配套检查**，缺了它必删档反而制造新风险：只断言"文件没了"，
       执行体直接 `git rm` 而不转出条目照样通过，未决条目静默蒸发。
    返回 (条目数, 取回来源)；取不到返回 (None, 原因)。
    """
    out, _ = _git(root, "show", f"HEAD:{rel}")          # 已 git rm、尚未提交
    if out:
        return _open_entries_in_text(rel, out), "HEAD"
    out, _ = _git(root, "log", "--diff-filter=D", "-1", "--format=%H", "--", rel)
    if out and out.strip():
        sha = out.split()[0]
        out2, _ = _git(root, "show", f"{sha}^:{rel}")
        if out2:
            return _open_entries_in_text(rel, out2), f"{sha[:8]}^"
    return None, "git 历史中查无此文件（可能从未提交过）"


def _transfer_evidence(root, transfer_to, from_version):
    """转出目的地是否确实收到了条目。返回 (是否有证据, 说明)。

    ★ `transfer_to` 支持**逗号分隔的多个路径**：拆成四族之后，规划期迁移的目的地是
    当前版本的**四族册**（一条条目按内容分派到哪一族，收口时才知道），发布期仍是单个欠账文件。
    ⛔ 只要**任一**目的地找到痕迹即算转出到位——要求"每一份都有痕迹"会把
    「本批全是设计类条目、只迁进了设计册」这种完全正常的情况判成失败。
    """
    if not transfer_to:
        return None, "未指定 --transfer-to，无法核验转出"
    targets = [t.strip() for t in str(transfer_to).split(",") if t.strip()]
    misses = []
    for t in targets:
        path = os.path.join(root, t)
        if not os.path.isfile(path):
            misses.append(f"{t}（不存在）")
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read(400_000)
        except OSError as exc:
            misses.append(f"{t}（读取失败：{exc}）")
            continue
        # 合法痕迹只认**带标记**的两种写法。
        # ⛔ 绝不能回退成裸 `from_version in text`：转出目的地通常是
        #    `docs/audit/{version}/发布欠账.md`，而该文件里任何一条**无关**欠账都写着
        #    `/version {version} --finalize-docs` —— 版本号必然出现，判据于是**近乎恒真**：
        #    「删台账时还有 N 条未决、一条都没转记」只要该版本此前有过任意一条欠账就被放行。
        if (f"承接自 {from_version}" in text
                or f"来源版本：{from_version}" in text
                or f"来源版本: {from_version}" in text
                or f"← {from_version}" in text):
            return True, f"在 {t} 找到来自 {from_version} 的**带标记**条目痕迹"
        misses.append(f"{t}（无痕迹）")
    return False, (f"以下转出目的地都找不到来自 {from_version} 的条目痕迹：{'、'.join(misses)}"
                   "（规划期迁移须带 `← 承接自 {V}`，发布期欠账须写明来源版本）")


def _check_one_ledger(root, v, fam, rel, must_delete, transfer_to, pc, unparsed):
    """判定某版本某一族的增量册终态，返回 (checked_item|None, violation|None)。

    ★ 从「一份台账」拆成「四族册 + 存量单册」后，每一份都要独立走完同一套判定——
    ⛔ 严禁"任一份合规即放行"：那会让「设计册干净、用例册攒着 8 条」判成收口完成。
    """
    label = FAMILY_LABEL.get(fam, fam)
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        if not must_delete:
            return ({"version": v, "family": fam, "path": rel, "status": "absent",
                     "detail": f"{label}增量册不存在（收口完成的正常终态）"}, None)
        # 必删档：文件没了还不够，得确认被删的那份里没有"被顺手带走"的未决条目
        n, src = _deleted_ledger_open_count(root, rel)
        if n is None:
            # ⛔ 不判违规（git 查不到确实无从核验），但必须**可见**：
            #    "从未提交过的台账被删掉"与"本就没有台账"在这里同形，静默放行等于给了条后门。
            return ({"version": v, "family": fam, "path": rel, "status": "absent-unverifiable",
                     "warn": True,
                     "detail": f"{label}增量册不存在；转出无从核验（{src}）→ 人工确认删除前是否还有未决条目"}, None)
        if n <= 0:
            return ({"version": v, "family": fam, "path": rel, "status": "absent",
                     "detail": f"{label}增量册不存在；删前已无未决条目（据 {src} 核验）"}, None)
        ok_ev, why = _transfer_evidence(root, transfer_to, v)
        if ok_ev:
            return ({"version": v, "family": fam, "path": rel, "status": "absent-transferred",
                     "transferred": n,
                     "detail": f"{label}增量册不存在；删前 {n} 条未决已转出（{why}）"}, None)
        return (None, {
            "version": v, "family": fam, "path": rel, "reason": "deleted-without-transfer",
            "open_entries": n,
            "detail": (f"{label}增量册已删，但删前还有 {n} 条未决条目（据 {src} 核验），"
                       f"未找到转出痕迹：{why}。⛔ 必删 ≠ 把账删没——"
                       "规划期须先迁移进当前版本对应族的增量册、发布期须先转记发布欠账")})

    if must_delete:
        # ⛔ 此档只有一个合法终态：文件不存在。内容如何一概不看——看了就会长出
        #    "内容还有未决所以先留着" 这类例外，而那正是本档要消灭的东西。
        return (None, {
            "version": v, "family": fam, "path": rel, "reason": "must-delete",
            "detail": (f"版本收口必定清理{label}增量册：规划期删上一版本的、发布期删本版本的，"
                       "无保留场景。未能级联的条目不许留着——规划期迁移进当前版本对应族的增量册、"
                       "发布期转记 docs/audit/{v}/发布欠账.md，然后把本文件删掉".format(v=v))})

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(400_000)
    except OSError as exc:
        return (None, {"version": v, "family": fam, "path": rel, "reason": "unreadable",
                       "detail": f"{label}增量册读取失败：{exc}"})
    if _has_archived_mark(text):
        # ⛔ 标记**不替代删除**（约定 22：成功级联的条目即删、清空即删文件）。
        return (None, {"version": v, "family": fam, "path": rel,
                       "reason": "archived-not-deleted",
                       "detail": f"{label}增量册整档打了 LEDGER-ARCHIVED 却仍留着——标记不替代删除；"
                                 "若因目标文档写了 C-NNN 编号引用而删不掉，先把引用处"
                                 "改写为变更内容与理由本身（增量册是中转站、不承担长期溯源），再真删"})
    if rel in unparsed:
        return (None, {"version": v, "family": fam, "path": rel, "reason": "unparsed",
                       "detail": f"{label}增量册有实质内容却一条条目都解析不出——格式漂移，"
                                 "无从证明已收口；请按 .aidp/templates/_开发期族增量.md 骨架修正"})
    finfo = ((pc.get("versions", {}).get(v) or {}).get("families") or {}).get(fam)
    if finfo is None:
        return (None, {"version": v, "family": fam, "path": rel, "reason": "not-scanned",
                       "detail": f"{label}增量册存在、解析器却未收录；fail-closed 不予放行"})
    total = int(finfo.get("total") or 0)
    done = min(int(finfo.get("cascaded_not_cleaned") or 0), total)
    remaining = total - done
    if remaining <= 0:
        return (None, {"version": v, "family": fam, "path": rel, "reason": "not-deleted",
                       "total": total, "cascaded_not_cleaned": done,
                       "detail": (f"{label}增量册已无未决条目（%d 条中 %d 条已标记级联完成）却仍未删除。"
                                  "约定 22：成功级联的条目逐条删、清空即删整份文件——"
                                  "留着就是与正式文档并存的第二份信源" % (total, done))})
    return ({"version": v, "family": fam, "path": rel, "status": "open", "remaining": remaining,
             "detail": f"{label}增量册保留合法：仍有 {remaining} 条未决条目（失败/未级联）"}, None)


def run_ledger_closed(root=".", version=None, must_delete=False, transfer_to=None):
    """模式 B：收口后【族增量册】终态门（四族各一份，逐份独立判定）。

    must_delete=True（版本收口点 2/3）：目标版本的**每一份**增量册都必须不存在，无保留场景；
        且若被删的那份里**还有未决条目**，必须能在 transfer_to 找到转出痕迹——
        否则"删干净"就退化成"把账删没了"。
    must_delete=False（收口点 4）：每一份都满足"文件存在 ⟺ 确有未决条目"。
    """
    root = os.path.abspath(root)
    if version:
        versions = [version]
    else:
        # ★ 版本集 = 四族根目录的**并集**：四族分居四棵树，只扫 requirements 一棵会漏掉
        #   「本版只改了设计」这类完全正常的情形，而漏检是静默的。
        versions = set()
        for base in ("docs/requirements", "docs/design/detail", "docs/plans", "docs/testing"):
            d = os.path.join(root, base)
            if os.path.isdir(d):
                versions.update(n for n in os.listdir(d)
                                if _VERSION_RE.match(n) and os.path.isdir(os.path.join(d, n)))
        versions = sorted(versions)

    try:
        pc = _pending_cascade()(root)
        ledger_paths = _ledger_paths()
    except Exception as exc:                                    # noqa: BLE001
        return {"ok": False, "error": "ledger-parse-unavailable", "detail": str(exc),
                "hint": "增量册解析器（commit_gate）不可用；fail-closed 不予放行"}

    unparsed = {p.replace("\\", "/") for p in pc.get("unparsed", [])}
    checked, violations = [], []
    for v in versions:
        for fam, abspath in ledger_paths(root, v):
            rel = os.path.relpath(abspath, root).replace("\\", "/")
            # 存量单册在必删档同样要清；默认档下它不存在是常态，不额外报。
            ok_item, bad = _check_one_ledger(root, v, fam, rel, must_delete,
                                             transfer_to, pc, unparsed)
            if bad:
                violations.append(bad)
            elif ok_item:
                checked.append(ok_item)

    return {"ok": not violations,
            "mode": "ledger-closed-must-delete" if must_delete else "ledger-closed",
            "must_delete": bool(must_delete),
            "versions": versions, "checked": checked, "violations": violations}


def main():
    ap = argparse.ArgumentParser(description="约定 22 收口机器门：级联落点 + 收口后台账终态")
    ap.add_argument("--root", default=".")
    ap.add_argument("--base-ref", default=None,
                    help="收口开始前的 HEAD；与 --worktree 二选一（落点门）")
    ap.add_argument("--worktree", action="store_true",
                    help="检查尚未 commit 的工作树改动（收口子 Agent 提交前自检）")
    ap.add_argument("--ledger-closed", action="store_true",
                    help="改跑台账终态门：收口后「该删的台账必须已删」（不需要 git 范围）")
    ap.add_argument("--must-delete", action="store_true",
                    help="严格档（版本收口点 2/3）：目标版本台账必须【不存在】，无保留场景")
    ap.add_argument("--transfer-to", default=None,
                    help="必删档配套：未决条目的转出目的地（规划期=当前版本【四族册】路径，可逗号分隔多个，"
                         "任一找到痕迹即算转出到位；发布期=docs/audit/{version}/发布欠账.md）。"
                         "删前仍有未决条目时必传")
    ap.add_argument("--version", default=None, help="只查该版本目录（默认全部）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效"
                         "（骨架与探针登记表见 selfcheck.py）")
    args = ap.parse_args()
    if args.self_check:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from selfcheck import run_self_check
        sys.exit(run_self_check(os.path.basename(__file__),
                                json_out=getattr(args, "json", False)))

    if args.ledger_closed or args.must_delete:
        res = run_ledger_closed(args.root, args.version, args.must_delete, args.transfer_to)
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif res.get("error"):
            sys.stderr.write(f"❌ 台账终态门无法判定（{res['error']}）：{res.get('detail')}\n"
                             f"   {res.get('hint', '')}\n")
        elif res["ok"]:
            notes = ([f"{c['version']} 保留 {c['remaining']} 条未决"
                      for c in res["checked"] if c["status"] == "open"]
                     + [f"{c['version']} 已留档(ARCHIVED)"
                        for c in res["checked"] if c["status"] == "archived"]
                     + [f"{c['version']} 删前 {c['transferred']} 条未决已转出"
                        for c in res["checked"] if c["status"] == "absent-transferred"]
                     + [f"⚠️{c['version']}/{c.get('family','?')} 转出无从核验（git 查无此文件）"
                        for c in res["checked"] if c["status"] == "absent-unverifiable"])
            print("[OK] 增量册终态合规%s（%d 份已查；%s）"
                  % ("（必删档）" if args.must_delete else "",
                     len(res["checked"]), "、".join(notes) if notes else "四族均无残留增量册"))
        else:
            sys.stderr.write(f"❌ 增量册该删没删 {len(res['violations'])} 处：\n")
            for v in res["violations"]:
                sys.stderr.write(f"   · {v['path']}（{v['reason']}）\n     {v['detail']}\n")
            if args.must_delete:
                sys.stderr.write("   版本收口必定清理【四族全部】增量册，不存在要保留的场景；"
                                 "条目另有去处（规划期迁移 / 发布期转记欠账），删档不会丢东西。\n")
            else:
                sys.stderr.write("   收口 = 级联 + 删除，删除不是可选收尾。"
                                 "⛔ 没有\"打标记留档\"这条出路——标记不替代删除\n")
            sys.stderr.write("   详规 `.aidp/reference/开发期族增量.md`「清理规则」\n")
        return 0 if res.get("ok") else 1

    res = run(args.root, args.base_ref, args.version, args.worktree)
    if args.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif res.get("error"):
        sys.stderr.write(f"❌ 落点门无法判定（{res['error']}）：{res.get('detail')}\n"
                         "   fail-closed：不给结论就是不通过——请补齐 --base-ref / 确认版本目录存在\n")
    elif res["ok"]:
        n = len(res["landed"])
        print(f"[OK] 级联落点合规（范围 {res['scope']}；{n} 份主文档/索引被更新，"
              f"无新建 `NN_` 分册）")
    else:
        sys.stderr.write(f"❌ 级联落点违规 {len(res['violations'])} 处（范围 {res['scope']}）：\n")
        for v in res["violations"]:
            sys.stderr.write(f"   · {v['path']}\n     应落 → {v['expected']}\n"
                             f"     原因：{v['reason']}\n")
        sys.stderr.write("   收口级联**直接改该族内容主文档**（`01_` 等）+ 可刷 `00_索引.md`；"
                         "⛔ 不新建分册、不占 `NN_<业务主题>.md` 命名空间。\n"
                         "   详规 `.aidp/reference/开发期族增量.md`「收口执行要点」第 3 条\n")
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
