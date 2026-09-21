#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试套件结构检查脚本 - dev-manual-testcase 维度 7

检查测试用例文档是否符合"测试套件"组织方式:
- 每个测试套件必须包含入口流程 (Suite Setup),且仅出现一次
- Suite Setup 必须包含浏览器/APP 打开 + 登录(未登录套件可豁免登录)
- 套件内各用例通过菜单导航切换页面,禁止在单条用例中重复执行登录流程

套件标题写法(★规范形态在前,历史兼容形态在后):
  规范:   ## 套件 SUITE-01: 标题    ### 套件 SUITE-USER: 标题    #### 套件 SUITE-INC-01: 标题
  历史兼容:### 测试套件 TS-001: 标题(`测试套件` 前置词 / `TS-` 编号前缀,grandfather 放行,出 Info)

兼容的入口流程标题写法:
  #### Suite Setup
  #### 入口流程 (Suite Setup)
  ### 入口流程 (Suite Setup) — 套件开始时执行一次

用法:
  python check_testcase_suite.py <用例文档路径或目录>
  python check_testcase_suite.py <路径> --json
退出码: 0 = 通过, 1 = 不通过, 2 = 路径错误
"""

import argparse
import json
import re
import sys
from pathlib import Path

# 套件标题(兼容 SUITE-/TS- 前缀 + 字母数字混合编号)
SUITE_HEADER_RE = re.compile(
    r"^(#{2,4})\s+(?:测试)?套件\s+((?:SUITE|TS)-[A-Za-z0-9][A-Za-z0-9-]*)\s*[:：]?\s*(.*)$",
    re.MULTILINE,
)

# 入口流程 (Suite Setup) 标题
SUITE_SETUP_RE = re.compile(
    r"^#{3,5}\s+(?:入口流程\s*[\((]\s*Suite\s+Setup\s*[\))]|Suite\s+Setup)",
    re.MULTILINE | re.IGNORECASE,
)

# 用例标题(兼容 "#### 用例 TC-XXX:" 与 "#### TC-XXX:")
TESTCASE_HEADER_RE = re.compile(
    # ⚠️ 同宽约束见 check_testcase_format.py 同名注释：收窄=静默漏检整批用例
    r"^#{3,6}\s*(?:用例\s+)?(TC-[A-Za-z0-9_-]+)\s*[:：]?\s*(.*)$",
    re.MULTILINE,
)

# 登录类套件标题关键词(此类套件内用例可合法重复登录/登出)
LOGIN_SUITE_KEYWORDS = re.compile(r"登录|登出|未登录|登录态|单点登录|SSO", re.IGNORECASE)

# 步骤表行中重复登录的特征:数字步骤 + "打开 ... 浏览器" 或 点击"登录"按钮
STEP_OPEN_BROWSER_RE = re.compile(r"^\s*\|\s*\d+\s*\|\s*打开\s*\|[^|]*浏览器", re.MULTILINE)
STEP_LOGIN_RE = re.compile(r"^\s*\|\s*\d+\s*\|[^|]*\|[^|]*[\"“']?登录[\"”']?\s*按钮", re.MULTILINE)

# 列表/表格类套件信号(用于「列表列完整性」结构用例 report-only 提示,维度 17 子项 e)
LIST_TABLE_SIGNAL_RE = re.compile(r"表头列|表格表头|列展示名|列表页|表格各列|逐列核对")
# 「列表列完整性」结构用例关键词(命中即认为已配结构用例)
COL_INTEGRITY_RE = re.compile(r"列表列完整性|列完整性")


def check_col_integrity_case(suite, issues):
    """report-only(维度 17 子项 e):列表/表格类套件若无「列表列完整性」结构用例,给出提示。

    仅提示不判失败(level=Info,不影响退出码)——期望列序取自详设「字段实现清单」的
    结构用例应由 QR Agent 语义核验;此处只做低成本关键词提醒,避免漏配。
    """
    content = suite["content"]
    if LIST_TABLE_SIGNAL_RE.search(content) and not COL_INTEGRITY_RE.search(content):
        issues.append({
            "level": "Info",
            "line": suite["line"],
            "msg": ("套件 {} 疑似含列表/表格页,但未见「列表列完整性」结构用例关键词——"
                    "维度 17 要求每个列表类页面配一条结构用例(断言"
                    "\"表格自左至右应依次为 A / B / C / …,缺列或多出未登记列即 Fail\","
                    "期望列序取自详设「字段实现清单」);请确认或补充(report-only,不判失败)"
                    ).format(suite["id"]),
        })


def extract_suites(content):
    """提取所有测试套件块"""
    suites = []
    matches = list(SUITE_HEADER_RE.finditer(content))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        suites.append({
            "id": m.group(2),
            "title": m.group(3).strip(),
            "raw": m.group(0).strip(),
            "content": content[start:end],
            "line": content.count("\n", 0, m.start()) + 1,
        })
    return suites


def check_prefix_form(suite, issues):
    """套件/用例标题形态提示(Info,report-only,永不影响退出码)。

    规范形态 = `套件 SUITE-{编号}` + `用例 TC-*`(标题层级 2~4 / 3~5 级均可);
    历史兼容形态**三种**——`测试套件` 前置词 / `TS-` 编号前缀 / 用例标题省略「用例」二字,
    存量文档 grandfather 放行,仅提示新生成收敛。三种必须都查:契约点名三种、脚本只查两种,
    读者会以为剩下那种有机检兜底(而它恰恰是危害更大的那一种——用例扫不到 = 整条不进 tasks.md)。
    ⚠️ 刻意判 Info 不判 Important:下游 auto-test-runner 的解析端已按"宽进"同时认全部形态
    (见该 skill 的 `references/usecase-format.md` §二 前缀契约),存量文档不会漏跑,不该因此变红。
    """
    # ⚠️ 只查**编号之前的前置词段**,不得拿整行 raw 做子串查——raw 含标题正文,
    #    `### 套件 SUITE-01: 测试套件管理页面` 这种**前缀完全规范**、只是被测系统本身叫
    #    「测试套件管理」的标题会被整条误报(测试平台 / QA 工具类项目里并不罕见)。
    head = suite["raw"][:suite["raw"].find(suite["id"])]
    legacy = []
    if "测试套件" in head:
        legacy.append("`测试套件` 前置词")
    if suite["id"].startswith("TS-"):
        legacy.append("`TS-` 编号前缀")
    if legacy:
        issues.append({
            "level": "Info",
            "rule": "legacy_suite_prefix",
            "line": suite["line"],
            "msg": "{}(L{}): 使用了历史兼容形态({});新生成建议统一为 "
                   "`套件 SUITE-{{编号}}: {{标题}}`(标题层级 2~4 级均可)".format(
                       suite["id"], suite["line"], "、".join(legacy)),
        })

    # 第三种历史兼容形态:用例标题省略「用例」二字(`#### TC-USER-001: 标题`)。
    # TESTCASE_HEADER_RE 的 `(?:用例\s+)?` 分组本就可选,这里回头判原文有没有那两个字。
    bare = [m.group(1) for m in TESTCASE_HEADER_RE.finditer(suite["content"])
            if "用例" not in m.group(0)[:m.group(0).find(m.group(1))]]
    if bare:
        shown = "、".join(bare[:3]) + ("…" if len(bare) > 3 else "")
        issues.append({
            "level": "Info",
            "rule": "legacy_case_prefix",
            "line": suite["line"],
            "msg": "{}(L{}): {} 条用例标题省略了「用例」二字({});新生成建议统一为 "
                   "`#### 用例 TC-{{模块}}-{{序号}}: {{标题}}`".format(
                       suite["id"], suite["line"], len(bare), shown),
        })


# `affects:` 影响面标签(P2-9,推荐附加行)。语法见 SKILL.md「L2 套件级引用」:
#   > **affects:** modules=[A, B] pages=[/x, /y]
# ⚠️ 判 Info 不判 Important:它是**纯增量元信息**,存量文档一律没有,判 Important 会让
#    全部历史用例文档一夜变黄、噪声常驻,而常驻噪声会让整个硬门被无视。
AFFECTS_LINE_RE = re.compile(r"^>\s*\*\*affects[:：]?\*\*[:：]?\s*(.+)$", re.MULTILINE)
AFFECTS_MODULES_RE = re.compile(r"modules\s*=\s*\[([^\]]*)\]")
AFFECTS_PAGES_RE = re.compile(r"pages\s*=\s*\[([^\]]*)\]")


def check_affects_tag(suite, issues):
    """`affects:` 影响面标签检查(Info,report-only,永不影响退出码)。

    下游据它把 git diff 涉及路径与套件做包含匹配,决定本轮哪些套件要重跑、
    哪些沿用上轮结论。缺了不会出错、只是筛不出来(退化成全量跑),故只提示。
    """
    m = AFFECTS_LINE_RE.search(suite["content"])
    if not m:
        issues.append({
            "level": "Info", "rule": "missing_affects", "line": suite["line"],
            "msg": "{}(L{}): 缺 `affects:` 影响面标签;下游跨 build 回归无法按 git diff "
                   "筛选应跑套件(退化为全量重跑)。建议补 "
                   "`> **affects:** modules=[模块名] pages=[/路由]`".format(
                       suite["id"], suite["line"]),
        })
        return
    body = m.group(1)
    mods = AFFECTS_MODULES_RE.search(body)
    pages = AFFECTS_PAGES_RE.search(body)
    missing = []
    if not mods:
        missing.append("modules=[...]")
    elif not mods.group(1).strip():
        missing.append("modules 列表为空")
    if not pages:
        missing.append("pages=[...]")
    elif not pages.group(1).strip():
        missing.append("pages 列表为空")
    if missing:
        issues.append({
            "level": "Info", "rule": "bad_affects", "line": suite["line"],
            "msg": "{}(L{}): `affects:` 语法不完整({});两个列表都不得为空——"
                   "纯后端套件无路由请写 `pages=[N/A]`,留空读起来像忘了写".format(
                       suite["id"], suite["line"], "、".join(missing)),
        })


def check_suite_setup(suite, issues):
    """检查套件是否包含且仅包含一次入口流程 (Suite Setup)"""
    setups = list(SUITE_SETUP_RE.finditer(suite["content"]))
    if not setups:
        issues.append({
            "level": "Critical",
            "rule": "missing_suite_setup",
            "msg": "{}: 缺少入口流程 (Suite Setup) 章节".format(suite["id"]),
        })
        return
    if len(setups) > 1:
        issues.append({
            "level": "Important",
            "rule": "duplicate_suite_setup",
            "msg": "{}: 入口流程 (Suite Setup) 出现 {} 次,应只出现一次".format(
                suite["id"], len(setups)),
        })

    # 取第一个 Setup 到下一个标题之间的内容
    setup_start = setups[0].end()
    next_heading = re.search(r"^#{2,5}\s+", suite["content"][setup_start:], re.MULTILINE)
    setup_end = setup_start + next_heading.start() if next_heading else len(suite["content"])
    setup_content = suite["content"][setup_start:setup_end]

    if not re.search(r"打开|启动\s*APP|访问", setup_content):
        issues.append({
            "level": "Critical",
            "rule": "setup_missing_open",
            "msg": "{}: Suite Setup 缺少浏览器/APP 打开或访问首页步骤".format(suite["id"]),
        })

    # 未登录套件 / 显式声明"不登录"的套件,豁免登录步骤检查
    is_anonymous = (
        LOGIN_SUITE_KEYWORDS.search(suite["title"]) is not None
        or re.search(r"不登录|不执行登录|未登录状态", setup_content) is not None
    )
    if not is_anonymous and not re.search(r"登录|输入.*账号|输入.*用户名|输入.*密码", setup_content):
        issues.append({
            "level": "Critical",
            "rule": "setup_missing_login",
            "msg": "{}: Suite Setup 缺少登录步骤(若为未登录套件,请在标题或 Setup 中标明)".format(
                suite["id"]),
        })


def check_login_duplication(suite, issues):
    """检查套件内用例是否重复执行入口流程(打开浏览器 / 登录)"""
    # 登录类套件内用例可合法重复登录/登出
    if LOGIN_SUITE_KEYWORDS.search(suite["title"]):
        return
    matches = list(TESTCASE_HEADER_RE.finditer(suite["content"]))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(suite["content"])
        tc_id = m.group(1)
        tc_content = suite["content"][start:end]
        # 排除"退出登录"步骤(角色切换/登出场景的合法动作)
        cleaned = re.sub(r"退出登录|重新登录前先退出", "", tc_content)
        if STEP_OPEN_BROWSER_RE.search(cleaned) or STEP_LOGIN_RE.search(cleaned):
            issues.append({
                "level": "Critical",
                "rule": "duplicated_entry_in_case",
                "msg": "{}: 用例中重复执行入口流程(打开浏览器/登录),应在 Suite Setup 中统一执行".format(tc_id),
            })


def check_file(path):
    """检查单个用例文档,返回 (suites_count, issues)"""
    content = path.read_text(encoding="utf-8", errors="replace")
    suites = extract_suites(content)
    issues = []
    for suite in suites:
        check_prefix_form(suite, issues)
        check_affects_tag(suite, issues)
        check_suite_setup(suite, issues)
        check_login_duplication(suite, issues)
        check_col_integrity_case(suite, issues)
    return len(suites), issues


def main():
    parser = argparse.ArgumentParser(description="测试套件结构检查(维度 7)")
    parser.add_argument("path", help="用例文档路径或目录")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print("❌ 路径不存在: {}".format(target), file=sys.stderr)
        sys.exit(2)

    md_files = [target] if target.is_file() else sorted(target.rglob("*.md"))
    # 排除专职索引(00_) / 待澄清(99_) / 跨系统(98_)等非用例文件;02_*总览* 索引文档;
    # 研发自测方案(00_/01_,非用例分册)与 aiauto-test 的「测试环境与账号.md」配置(非用例分册)。
    # 口径对齐 check_case_stats.py / check_suite_upstream.py / check_testcase_format.py 的排除契约。
    # (总览本身不含套件,套件在 03_… 子文件;若误对总览单跑会 total_suites==0 → 假性 exit 1)
    md_files = [f for f in md_files
                if not re.match(r"^(00_|98_|99_)", f.name)
                and "总览" not in f.name
                and "研发自测方案" not in f.name
                and "测试环境与账号" not in f.name]
    if not md_files:
        print("⚠️  未发现 markdown 用例文件: {}".format(target), file=sys.stderr)
        sys.exit(2)

    results = []
    total_suites = 0
    all_issues = []
    for f in md_files:
        suites_count, issues = check_file(f)
        total_suites += suites_count
        for i in issues:
            i["file"] = str(f)
        all_issues.extend(issues)
        results.append({"file": str(f), "suites": suites_count, "issues": issues})

    passed = not any(i["level"] == "Critical" for i in all_issues)

    if args.json:
        print(json.dumps({
            "passed": passed,
            "total_suites": total_suites,
            "total_issues": len(all_issues),
            "files": results,
        }, ensure_ascii=False, indent=2))
    else:
        if total_suites == 0:
            print("⚠️  未识别到 `## 套件 SUITE-NN` 段(历史兼容形态 `### 测试套件 TS-NNN` 亦可),"
                  "请确认用例采用测试套件组织方式")
        # ⚠️ Info 级(如 legacy_suite_prefix / legacy_case_prefix)是 report-only 提示,
        #    **不得**把 `✅ 通过` 这行顶掉——QR 子 Agent 按 SKILL.md 步骤 0 要把「报告正文原样贴进
        #    报告」,一份仅前缀是历史形态、结构完全合规的 grandfather 文档若只剩「发现 N 个问题」
        #    可贴,会被判维度 7 不通过(假红灯),与 grandfather 放行的初衷相反。
        blocking = [i for i in all_issues if i["level"] != "Info"]
        if not blocking:
            print("✅ 通过: 共 {} 个测试套件,结构检查无问题".format(total_suites))
        else:
            print("发现 {} 个问题(共 {} 个测试套件):\n".format(len(blocking), total_suites))
        for i, issue in enumerate(blocking, start=1):
            icon = {"Critical": "🔴", "Important": "🟡"}.get(issue["level"], "ℹ️")
            print("  {}. {} [{}] {} ({})".format(
                i, icon, issue["level"], issue["msg"], issue["file"]))
        infos = [i for i in all_issues if i["level"] == "Info"]
        if infos:
            print("\nℹ️  另有 {} 条提示(report-only,不影响判定与退出码):".format(len(infos)))
            for i, issue in enumerate(infos, start=1):
                print("  {}. ℹ️ [Info] {} ({})".format(i, issue["msg"], issue["file"]))

    # 套件组织缺失也视为不通过(维度 7 要求套件组织)
    if total_suites == 0:
        sys.exit(1)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
