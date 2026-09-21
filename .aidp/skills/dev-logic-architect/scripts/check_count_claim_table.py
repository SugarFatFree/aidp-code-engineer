#!/usr/bin/env python3
r"""
check_count_claim_table.py — 「业务计数声明表」结构性核验(检查项 36 / 核心原则 28)

用法:
  python3 check_count_claim_table.py <设计文档目录> [--json]      # ← 推荐:传**目录**
  python3 check_count_claim_table.py <单个 .md>     [--json]      # ← 合法，但 C6/C7 只判该文件
                                                                  #    (会打作用域告警,见下)

核验固定 5 列「业务计数声明表」:
  | 声明名 | 当前值 | 是否动态 | 权威出处 | 散落面正则 |

判据(全部 Critical，均只占 exit 1，严重度分档走 --json，不占退出码):
  C1 表头 5 列不齐 / 缺 GFM 分隔行(不是一张合法表)
  C2 逐格空或占位(待定 / TBD / — / ? / {...})
  C3 「是否动态」取值不在 {动态, 静态} 内 —— 这一格决定了「散落面里能不能出现字面数字」，
     写成「是/否/部分」会让消费侧回扫无从判定
  C4 「散落面正则」不可编译 —— 编译不过的正则等于没写，且会让消费侧回扫直接崩
  C5 疑似 `|` 未转义(数据行被切出的格数多于表头) —— ⭐ 见下方「为什么单列这一条」
  C6 同一「声明名」的**当前值**不一致
  C7 同一「声明名」的**权威出处**不一致
     —— C6/C7 与 check_metric_spec.py 的 M4 **同构且同作用域**:**按本次扫描范围跨表跨文件
     聚合**判定，不是逐表判定。⚠️ C7 才是核心原则 28 立论的正主:不可退让的是**权威出处唯一**、
     不是**表唯一**(SKILL.md 原则 28 / core-principles.md 落位段原话)，而它正对应 M4 比对的
     那一列(M4 比「权威取数口径」)。⛔ **勿只留 C6** —— 只比当前值等于把「同一个计数有两个
     权威出处」这一整类缺陷放走，而文档正声称该项由硬门守。

⚠️ **C6 / C7 必须跨表跨文件聚合，勿改回 per-table**(与 `check_metric_spec.py` 的 M4 是同一个坑，
   那边已经踩过并写进了注释):本 SKILL 在 M/L 档**强制多册拆分**，且增量产物按
   `SKILL.md` >「增量 / 补充生成约定」第 2 条走**新的 `NN_<业务主题>.md`、不改主文档正文** ——
   即同名声明分散到第二张表 / 第二册在本 SKILL 的正常工作流里**几乎必然发生**。
   C6 / C7 若逐表判，跨表自相矛盾完全不触发 → **必假绿**，且人读输出还会主动断言「已核验」。
   **因此调用方应传目录**;传单个 `.md` 只判该文件范围，多册 / 有增量的场景会漏判。

⚠️ **传单文件时必须把「作用域被缩窄」这件事说出来**(实测:改成跨文件聚合之后，传单个 `.md`
   仍原样打印「✅ 通过」，与真·全范围通过**在输出里长得一模一样**)——那正是本仓库
   「N/A 跳过必须可区分 / 不让假绿静默存在」这条纪律要治的形态。故:
   `--json` 出 `scope` = `directory` | `single-file`(+ `aggregation_scope_note`)，
   人读模式在传单文件时**必打一行显式告警**。⛔ 勿以「反正文档写了要传目录」为由删掉它 ——
   文档管不住调用方手滑，输出管得住。

⚠️ **比对前必须归一化**(`_norm`，与 `check_metric_spec.py` 同一实现同一理由):不归一化时
   实测两个方向同时翻车 —— `**告警类型数**`(8) 与 `告警类型数`(9) 分散在两册**被当成两个声明、
   真矛盾漏判**(假绿,恰恰是本判据存在的理由);`5` 与 `` `5` `` 又**被当成矛盾**(假红)。
   跨册的粗体 / 反引号写法差异在本仓库是常态，不是个例。

⭐ 为什么把 C5 单列而不是让它并进 C1:
   「散落面正则」这一格天然含 `|`(择一分支)，而 GFM 表格里 `|` 是**列分隔符**，
   **反引号代码段并不能保护它** —— 写 `` `(共|计) (\d+) 种` `` 会被切成 6 格而不是 5 格。
   正确写法是转义成 `\|`。这是本表**实测第一次就会踩到**的坑(下游反馈原话)，
   而它的表象是「列数对不上」，若并进 C1 只会报「表头 5 列不齐」，
   排查方向被带偏到表头上去 —— 报错必须直接说出「是正则里的 | 没转义」。

⚠️ **刻意不做「缺表判定」**:计数声明的信号词(「共 N 个」「支持 N 种」「N 类」)在设计文档正文里
   几乎必然出现(「共 3 张表」「分 5 个阶段」)，扫正文会让每份合规设计满屏假红 ——
   与 check_metric_spec.py「刻意不扫正文散文」是同一条理由。
   **表该不该有由 QR 子 Agent 按检查项 36 判**，本脚本只在表**存在时**核验它。
   未找到表 → exit 0 + --json 出 `"skipped": true`(全仓退出码约定③:N/A 跳过必须可区分)。

★ 去重边界(硬约束):**散落面回扫**(拿正则去代码/文档里找过期副本)由**被测项目侧**
   `check_count_claims.py --project-claims` 承担，⛔ **本脚本严禁重写那套回扫** ——
   同一判据两份实现是本仓库最高频的漂移源(改一处漏一处、两处都自称权威)。
   本脚本只管「声明期表结构对不对」，回扫管「声明与现实符不符」。

退出码:
  0 = 通过 / N/A 跳过(未找到该表)     1 = 检出违规     2 = 入参或环境错
"""

import json
import re
import sys
from pathlib import Path

EXPECTED_COLS = ["声明名", "当前值", "是否动态", "权威出处", "散落面正则"]
DYNAMIC_VALUES = {"动态", "静态"}

# 占位判定必须**全串锚定**:`{上游中文名}服务无法连接` 这类「已填实、只留名称槽位」的合规写法
# 若用非锚定的 `\{...\}` 会被整格判空 —— 本仓库 check_error_contract.py / check_metric_spec.py
# 都踩过同一个坑，此处照抄它们的口径。
PLACEHOLDER_RE = re.compile(r"^\s*(?:待定|TBD|tbd|待补充|—|-{1,2}|\?|N/?A|\{[^{}]*\})\s*$")
_ESCAPED_PIPE = "\x00PIPE\x00"
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})\s*(\S*)")
# ⚠️ 本仓库表格分隔行普遍写作 `| :- | :- |`(**单个**连字符)，不是 GFM 严格要求的 `---`。
#    首版按 `-{2,}` 写，结果**一张表都找不到、脚本整体空转**(实测:自家 fixture 直接跳过)。
SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
# 正则特征:含这些元字符才提示「可能是没转义的正则」，避免把普通多列表格误诊成 C5
REGEXISH = re.compile(r"[\\()\[\]{}*+?^$]")


def _norm(s):
    """归一化:去粗体 / 反引号 / 引用符 / 空白，全角括号→半角。

    ⚠️ 与 `check_metric_spec.py` 的 `_norm` **刻意逐字同款**(C6/C7 与 M4 是同一形态的判据)。
       不归一化会让 `**告警类型数**` 与 `告警类型数` 变成两个声明 —— 真矛盾漏判(假绿);
       也会让 `5` 与 `` `5` `` 变成一个矛盾 —— 无中生有(假红)。两个方向都实测踩到过。
    """
    s = re.sub(r"[*`>\s]", "", s)
    return s.replace("（", "(").replace("）", ")")


def split_row(line):
    """按 GFM 规则切一行表格，先把 `\\|` 转义位摘出来再切。"""
    s = line.replace(r"\|", _ESCAPED_PIPE).strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.replace(_ESCAPED_PIPE, r"\|").strip() for c in s.split("|")]


def fence_mask(lines):
    """标出代码围栏内的行 —— 文档必然要写出表格样例才能规定它，样例不参与判定。

    ⚠️ **按 CommonMark 规则判闭合，不是「见 ``` 就翻转」**:闭合行必须是**裸**围栏
    (无语言标记)且长度 ≥ 开启行。本仓库大量文档在 ```markdown 例子里套 ```yaml/```sql,
    朴素翻转模型会在那里**失相** —— 相位一错，围栏内的样例表就被当成正文里的真表来判，
    而写在样例里的**故意写错的反例**会被判死(实测本仓库有 4 份文档命中这一形态)。
    """
    mask = [False] * len(lines)
    opener = None                      # 当前开启围栏的长度;None = 不在围栏内
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if m:
            marker, info = m.group(1), m.group(2)
            if opener is None:
                opener = len(marker)
                mask[i] = True
                continue
            if not info and len(marker) >= opener:
                opener = None
                mask[i] = True
                continue
        mask[i] = opener is not None
    return mask


def find_tables(lines):
    """找出全部「业务计数声明表」:表头 5 列齐 + 紧跟 GFM 分隔行。

    ⚠️ 表头必须校验**紧跟分隔行** —— 否则散文里「旧版「声明名 | 当前值」两列表已作废」
    这类**说明文字**会被当成一张缺列的表(check_error_contract.py 实测踩过)。
    """
    mask = fence_mask(lines)
    tables = []
    for i, line in enumerate(lines):
        if mask[i] or "|" not in line:
            continue
        cells = split_row(line)
        if not any(c == EXPECTED_COLS[0] for c in cells):
            continue
        if i + 1 >= len(lines) or not SEPARATOR_RE.match(lines[i + 1]):
            # 缺失/非法分隔行仍是一个明确的表格候选：只有下一行也含 `|`
            # 才纳入，避免把散文中的旧格式说明误当成业务表。这样 C1
            # 能覆盖“表头 + 数据行但忘写 GFM 分隔行”，而不会削弱“缺表不判定”。
            if i + 1 < len(lines) and "|" in lines[i + 1] and lines[i + 1].strip():
                tables.append({"header_line": i + 1, "header": cells,
                               "rows": [], "missing_separator": True})
            continue
        rows = []
        j = i + 2
        while j < len(lines) and "|" in lines[j] and not mask[j] and lines[j].strip():
            rows.append((j + 1, lines[j]))
            j += 1
        tables.append({"header_line": i + 1, "header": cells, "rows": rows})
    return tables


def check_file(path):
    findings = []
    claim_rows = []          # 供 main() 做**跨表跨文件**的 C6 / C7 聚合
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except (OSError, PermissionError) as e:
        # 读不出来 ≠ 没问题:静默计为通过正是假绿的来源(CLAUDE.md 已登记的全仓缺口方向)。
        return None, [{"code": "E-READ", "level": "Critical", "file": str(path),
                       "line": 0, "msg": f"文件无法读取: {e}"}], []

    tables = find_tables(lines)
    if not tables:
        return 0, [], []

    for t in tables:
        if t.get("missing_separator"):
            findings.append({"code": "C1", "level": "Critical", "file": str(path),
                             "line": t["header_line"],
                             "msg": "业务计数声明表表头后缺失或未正确填写 GFM 分隔行"})
            continue
        if t["header"] != EXPECTED_COLS:
            findings.append({"code": "C1", "level": "Critical", "file": str(path),
                             "line": t["header_line"],
                             "msg": f"表头 5 列不齐或列名/顺序不符。期望 {EXPECTED_COLS}，实际 {t['header']}"})
            continue

        for lineno, raw in t["rows"]:
            cells = split_row(raw)
            if len(cells) != len(EXPECTED_COLS):
                if len(cells) > len(EXPECTED_COLS) and REGEXISH.search(raw):
                    findings.append({
                        "code": "C5", "level": "Critical", "file": str(path), "line": lineno,
                        "msg": f"本行被切出 {len(cells)} 格(表头 {len(EXPECTED_COLS)} 格)，"
                               f"且含正则元字符 —— 极可能是「散落面正则」里的 `|` 未转义。"
                               f"GFM 里 `|` 是列分隔符，**反引号代码段保护不了它**，必须写成 `\\|`"})
                else:
                    findings.append({"code": "C1", "level": "Critical", "file": str(path),
                                     "line": lineno,
                                     "msg": f"数据行 {len(cells)} 格，与表头 {len(EXPECTED_COLS)} 格不符"})
                continue

            name, value, dyn, source, pattern = cells
            for col, cell in zip(EXPECTED_COLS, cells):
                if not cell or PLACEHOLDER_RE.match(cell):
                    findings.append({"code": "C2", "level": "Critical", "file": str(path),
                                     "line": lineno,
                                     "msg": f"「{col}」格为空或占位(`{cell}`)——不可核对等于没写"})
            if dyn and dyn not in DYNAMIC_VALUES and not PLACEHOLDER_RE.match(dyn):
                findings.append({"code": "C3", "level": "Critical", "file": str(path),
                                 "line": lineno,
                                 "msg": f"「是否动态」= `{dyn}`，只能填「动态」或「静态」"
                                        f"(这一格决定散落面里能不能出现字面数字)"})
            body = pattern.strip().strip("`").replace(r"\|", "|")
            if body and not PLACEHOLDER_RE.match(pattern):
                try:
                    re.compile(body)
                except re.error as e:
                    findings.append({"code": "C4", "level": "Critical", "file": str(path),
                                     "line": lineno,
                                     "msg": f"「散落面正则」无法编译: {e}(`{body}`)"})
            # C6 / C7 只在这里**采集**，判定放到 main() 做跨表跨文件聚合(理由见模块 docstring)。
            # ⚠️ 勿改回在本函数里用局部 seen 判 —— 那是 per-table，多册/增量场景必假绿。
            # ⚠️ 占位名(空 / 待定 / TBD / {...})**必须在这里就跳过**，与 check_metric_spec.py
            #    的 `_is_empty(name)` 跳过同款:这些行已由 C2 逐格判过，再进聚合只会叠出一条
            #    「两个 TBD 自相矛盾」的无意义 C6/C7，把作者的排查方向从「把名字填实」带偏。
            if name and not PLACEHOLDER_RE.match(name):
                claim_rows.append({"key": _norm(name), "display": name[:30],
                                   "value": _norm(value), "value_raw": value,
                                   "source": _norm(source), "source_raw": source,
                                   "file": str(path), "line": lineno})
    return len(tables), findings, claim_rows


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    if "-h" in sys.argv[1:] or "--help" in flags:
        print(__doc__)
        return 0
    known = {"--json"}
    unknown = [f for f in flags if f not in known]
    if unknown:
        print(f"错误: 未知参数 {' '.join(unknown)}(可用: --json)", file=sys.stderr)
        return 2
    if not args:
        print("错误: 缺少位置参数 <设计文档路径或目录>", file=sys.stderr)
        return 2
    output_json = "--json" in flags

    target = Path(args[0])
    # ⚠️ exists() 与 is_dir() 分开判(全仓退出码约定②):合并写会把「路径不存在」与
    #    「传的是单个文件(合法)」混成同一句，手滑写错路径等于整个检查静默放行。
    if not target.exists():
        print(f"错误: 路径不存在 - {target}", file=sys.stderr)
        return 2
    docs = sorted(target.rglob("*.md")) if target.is_dir() else [target]
    if not docs:
        print(f"错误: 未在 {target} 下发现任何 .md", file=sys.stderr)
        return 2

    findings, tables_found, all_rows = [], 0, []
    for d in docs:
        n, f, rows = check_file(d)
        findings.extend(f)
        all_rows.extend(rows)
        if n:
            tables_found += n

    # ── C6 / C7 做**跨表跨文件聚合**判定，勿改回 per-table(理由见模块 docstring)──
    # 本 SKILL 多册拆分是强制的、增量产物又必落新文件，同名声明分散是**正常工作流**，
    # 不是异常;逐表判等于把这条判据在它最该生效的场景里整个关掉。
    # C6 比「当前值」、C7 比「权威出处」——**两列都要比**:核心原则 28 的立论是
    # 「权威出处唯一，不是表唯一」，只比当前值会放走「同一计数两个权威出处」这一整类缺陷。
    seen = {}
    for row in all_rows:
        prev = seen.get(row["key"])
        if prev is None:
            seen[row["key"]] = row
            continue
        for code, field, raw_field, label, tail in (
                ("C6", "value", "value_raw", "当前值",
                 "同一声明只能有一个权威当前值，要改就一起改"),
                ("C7", "source", "source_raw", "权威出处",
                 "核心原则 28 不可退让的正是「权威出处唯一」——同一计数不得有两个信源")):
            if prev[field] != row[field]:
                findings.append({
                    "code": code, "level": "Critical",
                    "file": row["file"], "line": row["line"],
                    "msg": f"声明名「{row['display']}」的「{label}」不一致:"
                           f"{prev['file']}:{prev['line']} 为 `{prev[raw_field]}`，"
                           f"此处为 `{row[raw_field]}` —— {tail}"})

    # ⚠️ 传单文件时把「C6/C7 的聚合作用域被缩窄到这一个文件」显式说出来。
    #    不说的话，单文件的「✅ 通过」与全目录的「✅ 通过」在输出里完全无法区分 ——
    #    正是本仓库「N/A 跳过必须可区分、不让假绿静默存在」这条纪律要治的形态。
    single_file = not target.is_dir()
    scope_note = ("本次只扫了单个 .md:C6/C7 的跨表跨文件聚合作用域被缩窄到该文件内，"
                  "多册与增量场景的跨册矛盾不会被发现。请改传设计文档目录。") if single_file else None

    skipped = tables_found == 0 and not findings
    payload = {
        "target": str(target), "scanned_files": len(docs),
        "scope": "single-file" if single_file else "directory",
        "aggregation_scope_note": scope_note,
        "tables_found": tables_found, "claim_rows": len(all_rows), "skipped": skipped,
        "skip_reason": "未找到「业务计数声明表」(表该不该有由 QR 检查项 36 判，本脚本不做缺表判定)"
                       if skipped else None,
        "critical": len([x for x in findings if x["level"] == "Critical"]),
        "findings": findings,
    }
    if output_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif skipped:
        print("⏭️  N/A 跳过:未找到「业务计数声明表」。")
        print("   ⚠️ 这不等于通过 —— 表该不该有，由 QR 子 Agent 按检查项 36 判。")
        if scope_note:
            print(f"   ⚠️ 作用域告警:{scope_note}")
    else:
        print("=" * 60)
        print(f"业务计数声明表核验 — 扫描 {len(docs)} 份文档，发现 {tables_found} 张表")
        print("=" * 60)
        for f in findings:
            print(f"  🔴 [{f['code']}] {f['file']}:{f['line']}\n       {f['msg']}")
        print("=" * 60)
        print("✅ 通过" if not findings else f"❌ {len(findings)} 项不通过")
        # ⚠️ 必须打在结论行**之后**:读者的视线停在最后一行，作用域限定写在前面等于没写。
        if scope_note:
            print(f"⚠️  作用域告警:{scope_note}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
