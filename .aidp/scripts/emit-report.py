#!/usr/bin/env python3
"""
emit-report.py — AI执行报告 / AI测试报告 的确定性产出器（防执行体手搓退化成 markdown）。

设计目的：把「写 data/{build}.js + 注册到 index.html/plan.html + 拼 `#/build/{BUILD}` 报告链接 +
写交付台账」这一整套**机械动作**从散文步骤（执行体极易"精简"成一段 markdown）升级为一个
**输入 = 结果 JSON、输出 = HTML SPA + 报告链接**的确定性脚本。
执行体只负责产出「结果 JSON」（它的分析），SPA 组装 / 注册 / 链接 / 台账一律由本脚本完成。

强制铁律（与 templates/reports/README.md + autopilot-ceremony-gate.py 单一信源对齐）：
  - 报告本体**必须是 HTML SPA**（零 CDN、file:// 可开），**严禁 markdown 报告**（本脚本反检并拒绝残留）。
  - data 用 `<script src>` 注入全局容器：执行报告 → window.__AIRUNS__（注册 index.html + plan.html 两页）；
    测试报告 → window.__BUILDS__（注册 index.html 一页）。
  - 报告只落本地 `docs/reports/`，随仓库提交。交付链接 = 仓库内相对路径
    `docs/reports/{V}/{类型}/index.html#/build/{BUILD}`。

用法：
  emit-report.py --kind exec|test --version V0.1.0 --build V0.1.0_build1001 --data result.json
  emit-report.py verify-reports [--repo-root .] [--reports-root docs/reports] [--json]
      批量巡检：扫全仓所有历史 build 的 data/*.js，逐个跑数据契约校验（发现存量白屏根因，
        如 risks 写成分组 dict / passRate 写成百分数）+ 校 `_integrity` checksum（发现手改；
        带 buildNo 的产物缺 `_integrity` 同样判疑似手改）。任一不过 → 退出码 4。
  emit 参数：
      [--repo-root .] [--templates-root AIDP_HOME/templates/reports] [--reports-root docs/reports]
      [--baseline memory/.sprint-autopilot-baseline.json]
      [--record-baseline 0|1]   默认 1：把交付结果（报告链接）回写 baseline `report_deliveries.<build>.<exec_report|test_report>.url`
                                供 ceremony-gate --stage final 校验；骨架阶段（ceremony-gate --stage skeleton 不校交付）传 0
      [--force-amend]           ★ 逃生阀：目标 build 已冻结（ai_report_finalized）时，仅用于修正明显笔误强制写入；
                                会在报告数据里追加 amendments[] 留痕（时间 + 原因），绝不静默覆盖
      [--amend-reason TEXT]     --force-amend 时的修订原因（写入 amendments[]；缺省提示待补）
      [--json]                  结构化输出（供命令 / gate 解析）

退出码：0 = 本地 SPA 产出成功（交付链接已生成）；1 = 本地 SPA 产出失败（严重，须补建）；
       2 = ★ 目标 build 报告已冻结（ai_report_finalized）且未带 --force-amend → 拒绝写入（须铸新 build 复测）；
       3 = ★ 数据契约校验未通过（字段名/结构/单位不符契约，见 validate_payload）→ 拒绝写盘（除非 --allow-schema-warn 降级留痕）；
       4 = ★ verify-reports 巡检发现契约不过 / 疑似手改 / 无法解析的历史 build 报告。

★ 报告不可变铁律（与 sprint-autopilot.md/sprint-aiauto-test.md「报告不可变铁律」+ autopilot-ceremony-gate.py 单一信源对齐）：
  build 一经 finalize（R-4 收尾置 baseline `versions.{V}.builds[].ai_report_finalized=true`）即冻结不可改。
  此后任何测试结论变化——无论源于代码修复、产品口径澄清、还是用例范围调整——一律**铸新 build 跑新一轮**，
  绝不回写旧 build 的 data。本脚本检测目标 build 已 finalized → 拒绝写入并 exit 2（除非 --force-amend 修正笔误 + 留痕）。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

# ★ 用例结果五态。`na`（不适用）是第五态，**不是** pass 的同义词，也不是 skip。
#
#   为什么必须单列：模板化用例族（如约定 39 还原度套件的四类页面固定模板）会为每个页面
#   逐条生成同一批检查项，其中总有几条**在该页根本不存在对应功能**——典型是"导出全量"
#   落在一个没有导出入口的列表页上。规则要求"缺项须标不适用"，但从没规定"标"落成什么
#   result；机器门又要求条目连号完整。执行体被夹在中间，只能记 pass。
#
#   后果是**分子分母同时失真**：下游实测一份 145 条的报告，4 条"本页无导出"记成 pass，
#   通过率 51.72% 实为 48.97%；且看报告的人会以为"导出全量"这项已被验证——等哪天真加了
#   导出，没人知道这条用例从未真正跑过。
#
#   语义边界（三者不可互替）：
#     · `block` = 前置没就绪、**以后能测**
#     · `skip`  = 本轮跳过、**以后要测**
#     · `na`    = 本场景不存在这个东西、**永远不测**
#
#   这是本仓「不得伪装」纪律的第四种形态：前三种是 *失败→空态* / *未生效→已生效* /
#   *未执行→无问题*，这一种是 ***不适用→通过***。
RESULT_STATES = ("pass", "fail", "block", "skip", "na")

# kind → (中文报告目录名, 全局容器变量, 需注册的页面, 远程英文目录名 slug)
# ★ slug 与两命令既有约定对齐：exec=ai-execution-report / test=ai-test-report（改此处须同步命令）
KIND_MAP = {
    "exec": ("AI执行报告", "__AIRUNS__", ["index.html", "plan.html"], "ai-execution-report"),
    "test": ("AI测试报告", "__BUILDS__", ["index.html"], "ai-test-report"),
}
REG_MARKER = "↑ 下游每新增一个 build"          # 数据注入区结束标记（在此行之前插入）
APP_MARKER = 'src="assets/app.js"'             # 兜底：app.js 之前插入


def _load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def get_build_entry(baseline_path, version, build):
    """读 baseline，返回 `versions.{V}.builds[]` 中 build==<build> 的条目 dict（无则 {}）。"""
    data = _load_json(baseline_path, {}) or {}
    builds = (((data.get("versions") or {}).get(version) or {}).get("builds")) or []
    for b in builds:
        if isinstance(b, dict) and b.get("build") == build:
            return b
    return {}


def build_finalized(baseline_path, version, build):
    """读 baseline，判目标 build 是否已冻结（report 不可变）。

    返回 (finalized: bool, finalized_at: str|None)。
    冻结标记 = `versions.{V}.builds[]` 中该 build 条目 `ai_report_finalized == True`
    （R-4 收尾置真，见 sprint-aiauto-test.md R-4 Step3）。缺 baseline / 无该条目 → 未冻结。
    """
    b = get_build_entry(baseline_path, version, build)
    return bool(b.get("ai_report_finalized")), b.get("ai_report_finalized_at")


def enrich_retest(payload, baseline_path, version, build):
    """item 6：从 baseline builds[] 把复测关系 retest_of/retest_round 注入 data payload
    （camelCase `retestOf`/`retestRound`，供 SPA 渲染「复测自 buildX · 第N轮」）。已在 payload 中则不覆盖。"""
    if not isinstance(payload, dict):
        return
    b = get_build_entry(baseline_path, version, build)
    if b.get("retest_of") and "retestOf" not in payload:
        payload["retestOf"] = b["retest_of"]
    if b.get("retest_round") and "retestRound" not in payload:
        payload["retestRound"] = b["retest_round"]


def enrich_incremental(payload, baseline_path, version, build):
    """把 baseline `builds[].incremental_case_ids` 注入 test payload（`incrementalCaseIds`）。

    ⛔ **为什么不让执行体手填**（同 enrich_retest / enrich_build_no 的立场）：AI 测试**每轮跑全量**，
    级联进来的新用例在 `02_*.md` 里与三个月前那批长得一模一样。报告若不点名本轮增量，
    「114 条全绿」就证明不了本轮 5 条新功能被覆盖过——而这正是最需要被证明的那部分。
    手填必然漏，漏了之后报告看起来照样完整（少一个字段没人会发现）。

    值由 `incremental_cases.py` 从 git 算出（新增的用例标题行），已在 payload 中则不覆盖。
    """
    if not isinstance(payload, dict):
        return
    b = get_build_entry(baseline_path, version, build)
    ids = b.get("incremental_case_ids")
    if isinstance(ids, list) and "incrementalCaseIds" not in payload:
        payload["incrementalCaseIds"] = ids


def enrich_build_no(payload, build):
    """P1-6：从 --build（形如 V0.10.2_build1002）用正则派生 buildNo（1002）回填。
    payload 已有非空则不覆盖（与 enrich_retest 同款语义）。buildNo 是排序键 + 图表 X 轴 + 报告编号 + 元信息四处共用，
    100% 可从 --build 派生，不让执行体手填（漏填即满页 #undefined）。"""
    if not isinstance(payload, dict):
        return
    if payload.get("buildNo") in (None, ""):
        m = re.search(r"_build(\d+)$", build or "")
        if m:
            payload["buildNo"] = int(m.group(1))


# 契约（单一信源见 AIDP_HOME/templates/reports/{cn_dir}/data/示例_build1001.js + templates/reports/README.md）
_REQUIRED = {
    "test": ["build", "version", "buildNo", "summary", "cases"],
    "exec": ["build", "version", "buildNo", "overview", "steps", "features"],
}
_ARRAY_FIELDS = {
    "test": ["suites", "cases", "defects", "runtimeErrors"],
    "exec": ["steps", "features", "defects", "risks", "todos", "incidents", "cases"],
}
# 比率类字段一律 0~1 小数（1.0=100%）——单位口径单一信源
_RATE_PATHS = {
    "test": ["summary.passRate"],
    "exec": ["testSummary.passRate", "testSummary.coverage",
             "overview.featureRate", "overview.testPassRate", "overview.coverage"],
}


def validate_payload(kind, payload):
    """P0-1：数据契约 fail-fast 校验。返回 errors[]（list[str]），空 = 通过。
    一次性收齐全部问题（不是只报第一个），每条带「期望 vs 实际 + 修正示例」。"""
    errs = []
    if not isinstance(payload, dict):
        return [f"payload 必须是对象，实际 {type(payload).__name__}"]
    for k in _REQUIRED.get(kind, []):
        if payload.get(k) is None:
            errs.append(f"缺失顶层必填字段 `{k}`")
    # 数组字段类型（risks 用分组对象是 #③ 白屏根因，专项点名）
    for k in _ARRAY_FIELDS.get(kind, []):
        v = payload.get(k)
        if v is not None and not isinstance(v, list):
            hint = ""
            if isinstance(v, dict):
                hint = f"（收到 dict keys={list(v.keys())}）"
                if k == "risks":
                    hint += "——请勿按 {high,medium,low}/等级分组，等级写在每项 level 字段里"
            errs.append(f"字段 `{k}` 期望 list[...]，实际 {type(v).__name__}{hint}")
    # cases[] 元素字段 + result 枚举 + 同义名点名
    if kind == "test" and isinstance(payload.get("cases"), list):
        for i, c in enumerate(payload["cases"]):
            if not isinstance(c, dict):
                errs.append(f"cases[{i}] 应为对象，实际 {type(c).__name__}")
                continue
            for f, alias in (("id", None), ("title", "name"), ("result", "status")):
                if c.get(f) is None:
                    a = f"（不是 `{alias}`——字段名不可自创同义词）" if alias and c.get(alias) is not None else ""
                    errs.append(f"cases[{i}] 缺字段 `{f}`{a}")
            r = c.get("result")
            if r is not None and r not in RESULT_STATES:
                errs.append(f"cases[{i}].result=`{r}` 非法，应 ∈ {'|'.join(RESULT_STATES)}")
            if r == "na" and not str(c.get("note") or "").strip():
                # ⛔ 无理由的 na 是最便宜的逃逸口：不写理由就能把任何该做的检查记成"不适用"
                errs.append(f"cases[{i}].result=na 但 note 为空 —— 不适用必须写明理由")
    # ★ 环境事实类字段：`renderMode` 必须带取证来源 —— 此前**零校验**（全脚本 grep 命中 0），
    #   于是契约里那句「严禁回落成模板示例值 / 启动参数推断值」没有任何东西在拦。
    #   ⚠️ 说清这条能做到什么：「填的是不是真的」**静态验不了**（报告里没有第二信源可比对，
    #   不像 driver 有 baseline `driver_actual` 作运行时独立记录）。所以它验的是
    #   **取证来源有没有被记下来**——契约已规定 `renderModeSource` 四选一
    #   （显式指定 / 复用已有实例 / 无头不可用降级 / 运行取证）。
    #   「填了但撒谎」拦不住；「填了值却说不出怎么取到的」是确定性可判的，而那正是
    #   模板示例值 `headless` 被原样留下时的样子。
    if kind == "test":
        _rm = payload.get("renderMode")
        if _rm is not None and _rm not in ("headless", "headed"):
            errs.append(f"renderMode=`{_rm}` 非法，应 ∈ headless|headed，取不到写 null（展示为「未取到」）")
        if _rm is not None:
            _src = str(payload.get("renderModeSource") or "").strip()
            if not _src:
                errs.append("renderMode 有值却缺 `renderModeSource` —— 环境事实类字段必须补记"
                            "「为何是这个模式」；填不出来源的值多半是模板示例值被原样留下，"
                            "按契约应改写 null")
            elif not any(k in _src for k in ("显式指定", "复用", "降级", "运行取证", "未取到")):
                errs.append(f"renderModeSource=`{_src[:30]}` 不在契约四选一内"
                            f"（显式指定 / 复用已有实例(含来源) / 无头不可用降级(含原因) / 运行取证(方法)）")

    # risks[] 元素（已是数组时）
    if kind == "exec" and isinstance(payload.get("risks"), list):
        for i, r in enumerate(payload["risks"]):
            if isinstance(r, dict):
                if r.get("level") not in ("高", "中", "低"):
                    errs.append(f"risks[{i}].level=`{r.get('level')}` 应 ∈ 高|中|低")
                if r.get("title") is None:
                    errs.append(f"risks[{i}] 缺 `title`")
    # todos[] 必须对象数组而非裸字符串
    if kind == "exec" and isinstance(payload.get("todos"), list):
        for i, t in enumerate(payload["todos"]):
            if not isinstance(t, dict):
                errs.append(f"todos[{i}] 应为 {{title[,detail]}} 对象，实际裸 {type(t).__name__}")
    # features[].status 枚举
    if kind == "exec" and isinstance(payload.get("features"), list):
        for i, f in enumerate(payload["features"]):
            if isinstance(f, dict) and f.get("status") not in (None, "done", "doing", "fail", "pend", "skip"):
                errs.append(f"features[{i}].status=`{f.get('status')}` 应 ∈ done|doing|fail|pend|skip")
    # 单位口径：0~1 小数，收到 >1 或字符串一律报错并给换算
    for path in _RATE_PATHS.get(kind, []):
        obj_key, _, field = path.partition(".")
        obj = payload.get(obj_key)
        if isinstance(obj, dict) and obj.get(field) is not None:
            v = obj[field]
            if isinstance(v, bool):  # bool 是 int 子类，先排除
                errs.append(f"{path}=`{v}` 非法：应为 0~1 小数")
            elif isinstance(v, str):
                errs.append(f"{path}=`{v}`（字符串）非法：单位为 0~1 小数（数字），如「6/6」应写 1.0、100% 写 1.0")
            elif isinstance(v, (int, float)) and v > 1.001:
                errs.append(f"{path}={v} 非法：单位为 0~1 小数（1.0=100%），应写 {round(v / 100, 4)}")

    # ★ 通过率**溯源**校验：`summary.passRate` 必须等于 `cases[]` 里 pass 的占比。
    #   此前只校"单位口径"（是不是 0~1 小数）与"字段结构"，从不校**数值是否与逐条用例自洽**——
    #   于是「实际用的驱动、通过率、证据必须与报告字段一致」这条设计目标里，
    #   驱动有门（ceremony-gate 3i 比对 baseline `driver_actual`）、证据有门（check_result 的
    #   `verified_pass_without_evidence`），**唯独通过率一道门都没有**。
    #   报告失真比测试失败严重得多：一份"通过率 100%、cases 里躺着 3 条 fail"的报告，
    #   看的人不会去数 cases，只会看那个数字。
    #   容差 ±0.005 兜住四舍五入；`cases` 缺失/为空时不判（那是别的校验项的事）。
    if kind == "test":
        cases = payload.get("cases")
        summary = payload.get("summary")
        if isinstance(cases, list) and cases and isinstance(summary, dict):
            rate = summary.get("passRate")
            valid = [c for c in cases if isinstance(c, dict) and c.get("result") in RESULT_STATES]
            # ★ n/a 不进通过率分母：它是"本场景不存在这个东西、永远不测"，
            #   与 block（"前置没就绪、以后能测"）语义不同，更不是"已验证通过"。
            denom = [c for c in valid if c.get("result") != "na"]
            if isinstance(rate, (int, float)) and not isinstance(rate, bool) and denom:
                passed = sum(1 for c in denom if c.get("result") == "pass")
                expect = passed / len(denom)
                if abs(float(rate) - expect) > 0.005:
                    errs.append(
                        f"summary.passRate={rate} 与 cases[] 不自洽：{len(denom)} 条可执行用例中 "
                        f"（已扣除 {len(valid) - len(denom)} 条 n/a）{passed} 条 pass → 应为 {round(expect, 4)}。"
                        f"⛔ 统计字段须由 `gen_report.py` 从 results/*.json 聚合得来，不得手填")

            # ★ 计数溯源（与 passRate 同源同理，此前缺门）：passRate 校的是"比例"，
            #   但**分母本身**可以整个是编的——一份 summary 写 total=50、cases[] 只躺 13 条的报告，
            #   passRate 若按 50 算恰好能对上比例、却把 37 条"没跑的用例"计成了已测。
            #   看报告的人不会去数 cases[]，只会看 total。故此处校三件事：
            #     ① summary 四态之和 == summary.total（自洽）
            #     ② summary.total == len(cases[])（分母可溯源到明细，不许注水）
            #     ③ suites[] 各计数之和 == summary 各计数（套件分解不许与总账打架）
            #   任一不符即报错——因为 gen_report.py 是从同一份 results/*.json 聚合出这三处的，
            #   真实报告不可能不一致；不一致 ⇒ 必是手填。
            # `na` 可缺省（存量报告没有这个字段）→ 视作 0，五态求和退化为原来的四态。
            counters = RESULT_STATES
            nums = {k: summary.get(k, 0) if k == "na" else summary.get(k) for k in counters}
            nums["total"] = summary.get("total")
            if all(isinstance(v, int) and not isinstance(v, bool) for v in nums.values()):
                s = sum(nums[k] for k in counters)
                if s != nums["total"]:
                    errs.append(
                        f"summary 五态之和={s} 与 summary.total={nums['total']} 不符"
                        f"（{'/'.join(counters)} = "
                        f"{'/'.join(str(nums[k]) for k in counters)}）")
                elif valid and nums["total"] != len(valid):
                    errs.append(
                        f"summary.total={nums['total']} 与 cases[] 明细条数={len(valid)} 不符。"
                        f"⛔ 分母必须可溯源到逐条明细：cases[] 须是完整用例清单，"
                        f"不得只列摘录（摘录会把未列出的用例静默计入已测）")
                elif valid:
                    actual = {k: sum(1 for c in valid if c.get("result") == k)
                              for k in counters}
                    bad = [f"{k}: summary={nums[k]} vs cases[]={actual[k]}"
                           for k in counters if nums[k] != actual[k]]
                    if bad:
                        errs.append("summary 各态计数与 cases[] 不自洽：" + "；".join(bad))

            suites = payload.get("suites")
            if (isinstance(suites, list) and suites
                    and all(isinstance(v, int) and not isinstance(v, bool)
                            for v in nums.values())):
                agg = {k: 0 for k in counters + ("total",)}
                ok = True
                for st in suites:
                    if not isinstance(st, dict):
                        ok = False
                        break
                    for k in agg:
                        # `na` 与 summary 同规则可缺省=0（存量套件没有这个键）。
                        # ⛔ 缺这条兼容会让整段 `ok=False`、**本门被静默跳过** ——
                        #    一道门无声关掉，比它报错更危险。
                        v = st.get(k, 0) if k == "na" else st.get(k)
                        if not isinstance(v, int) or isinstance(v, bool):
                            ok = False
                            break
                        agg[k] += v
                    if not ok:
                        break
                if ok:
                    bad = [f"{k}: suites[]合计={agg[k]} vs summary={nums[k]}"
                           for k in counters + ("total",) if agg[k] != nums[k]]
                    if bad:
                        errs.append("suites[] 分解与 summary 总账不符：" + "；".join(bad))
    return errs


def ensure_skeleton(report_dir, tpl_dir):
    """报告目录缺 index.html → 从模板拷骨架，并清掉示例 data + 其注册行。返回 True=本次新建。"""
    if os.path.isfile(os.path.join(report_dir, "index.html")):
        return False
    if not os.path.isdir(tpl_dir):
        raise FileNotFoundError(runtime_text(f"报告模板缺失：{tpl_dir}'（请先重跑脚手架补 __AIDP_HOME__/templates/reports/）'", __file__))
    os.makedirs(os.path.dirname(report_dir) or ".", exist_ok=True)
    shutil.copytree(tpl_dir, report_dir, dirs_exist_ok=True)
    # 清掉示例 data 文件 + 从各页移除其 <script> 注册行
    for ex in glob.glob(os.path.join(report_dir, "data", "示例_*.js")):
        os.remove(ex)
    for page in ("index.html", "plan.html"):
        p = os.path.join(report_dir, page)
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
        kept = [ln for ln in lines if not ("data/示例_" in ln and "<script" in ln)]
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(kept)
    return True


def inherit_test_facts(payload, reports_root, version, build):
    """exec 报告缺失的 `cases[]` / `testSummary` 从**同 build 的 AI测试报告**继承。

    ⛔ 这里补的是一处「有读无写」：收尾门 3n（约定 33 用例基线挂靠）读的是
    **AI执行报告**的 `cases[]`，而 exec 的字段契约从未声明过这个字段 ——
    于是 finalize 时不显式传 `cases[]`，门就报「用例库有 N 条基线、报告 cases[] 一个 id 都没有」，
    而执行体翻遍 exec 契约也找不到该填哪里（下游实证）。同一份用例明细要求填两遍本身也无意义：
    测试报告里已经有了，exec 直接继承。

    只补**缺失**的字段，⛔ 绝不覆盖显式传入的值（显式 > 继承）。返回继承说明（无继承则 None）。
    """
    if not isinstance(payload, dict):
        return None
    need_cases = not payload.get("cases")
    need_summary = not payload.get("testSummary")
    if not (need_cases or need_summary):
        return None
    test_js = os.path.join(reports_root, version, KIND_MAP["test"][0], "data", f"{build}.js")
    if not os.path.isfile(test_js):
        return None
    try:
        src = _extract_payload_from_js(test_js)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(src, dict):
        return None
    got = []
    if need_cases and isinstance(src.get("cases"), list) and src["cases"]:
        payload["cases"] = src["cases"]
        got.append(f"cases[]×{len(src['cases'])}")
    if need_summary and isinstance(src.get("summary"), dict):
        payload["testSummary"] = dict(src["summary"])
        got.append("testSummary")
    return {"from": test_js, "fields": got} if got else None


def _payload_checksum(payload):
    """对 payload（排除 `_integrity` 字段本身）做 sha256，用于防手改。
    规范化 = sorted-keys + 紧凑分隔符的 UTF-8 JSON，确保同一数据恒得同一摘要。"""
    if not isinstance(payload, dict):
        return None
    core = {k: v for k, v in payload.items() if k != "_integrity"}
    canon = json.dumps(core, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canon.encode("utf-8")).hexdigest()


def write_data_file(report_dir, build, payload, global_var):
    """写 data/{build}.js（IIFE push 到全局容器）。覆盖式，幂等。
    ★ 防手改：写盘前把 `_integrity`（payload 内容 sha256）嵌进 data。手改任一字段而不同步
    改 `_integrity` → verify-reports 子命令 / 渲染期校验即可判「数据被手工篡改」，而非白屏后无从溯因。"""
    data_dir = os.path.join(report_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    if isinstance(payload, dict):
        payload["_integrity"] = _payload_checksum(payload)  # 恒对「排除 _integrity 后」的内容计算
    body = json.dumps(payload, ensure_ascii=False, indent=2)
    body = "\n".join(("    " + ln) if ln else ln for ln in body.splitlines())  # 缩进进 push()
    js = (
        f"/**\n"
        f" * AI 报告数据 — {build}（由 emit-report.py 确定性生成，请勿手改）\n"
        f" */\n"
        f"(function () {{\n"
        f"  window.{global_var} = window.{global_var} || [];\n"
        f"  window.{global_var}.push(\n{body}\n  );\n"
        f"}})();\n"
    )
    fp = os.path.join(data_dir, f"{build}.js")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(js)
    return fp


def register_script(report_dir, build, pages):
    """把 <script src="data/{build}.js"> 注册进指定页面（幂等，在注入区标记前 / app.js 前插入）。"""
    tag = f'data/{build}.js'
    line = f'  <script src="data/{build}.js"></script>\n'
    registered = []
    for page in pages:
        p = os.path.join(report_dir, page)
        if not os.path.isfile(p):
            continue
        with open(p, "r", encoding="utf-8") as f:
            content = f.read()
        if tag in content:
            registered.append(page)
            continue
        lines = content.splitlines(keepends=True)
        idx = next((i for i, ln in enumerate(lines) if REG_MARKER in ln), None)
        if idx is None:
            idx = next((i for i, ln in enumerate(lines) if APP_MARKER in ln), None)
        if idx is None:
            # 极端：两个标记都没有 → 追加到 </body> 前
            idx = next((i for i, ln in enumerate(lines) if "</body>" in ln), len(lines))
        lines.insert(idx, line)
        with open(p, "w", encoding="utf-8") as f:
            f.writelines(lines)
        registered.append(page)
    return registered


def scan_stray_markdown(report_dir):
    """反检违规 markdown 报告（HTML SPA 铁律）：报告目录下除 README.md 外的 .md 一律视为违规残留。"""
    return [os.path.basename(m) for m in glob.glob(os.path.join(report_dir, "*.md"))
            if os.path.basename(m).lower() != "readme.md"]


def delivery_link(reports_root, version, cn_dir, build):
    """→ (delivery, url, detail)。报告只落本地；链接恒带 `#/build/{BUILD}`。"""
    rel = "/".join([reports_root.strip("/").replace(os.sep, "/"), version, cn_dir, "index.html"])
    return ("local", f"{rel}#/build/{build}", "报告落在仓库内，随提交共享")


def derive_test_summary(payload, reports_root, version, build):
    """exec 报告的 `testSummary` 恒从同 build AI测试报告的 `summary` 派生（两份报告口径唯一）。

    测试报告尚不存在（骨架阶段）→ 不动；存在且与传入值不一致 → 以测试报告为准覆盖并返回说明。
    """
    if not isinstance(payload, dict):
        return None
    test_js = os.path.join(reports_root, version, KIND_MAP["test"][0], "data", f"{build}.js")
    if not os.path.isfile(test_js):
        return None
    try:
        src = _extract_payload_from_js(test_js)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    summ = src.get("summary") if isinstance(src, dict) else None
    if not isinstance(summ, dict):
        return None
    derived = dict(summ)
    given = payload.get("testSummary")
    if given == derived:
        return None
    payload["testSummary"] = derived
    return {"from": test_js, "given": given, "derived": derived}


def record_baseline(baseline_path, kind, build, version, delivery, url, integrity=None):
    """把交付结果回写 baseline，供 autopilot-ceremony-gate.py check 确定性校验。

    ★ 并发安全（两条 /loop 共享同一 baseline：autopilot 10m 写部署字段、aiauto-test 5m 写测试字段）：
      ① 取排他 advisory 锁（fcntl.flock，POSIX 可用；不可用则退化为无锁但仍原子）→
      ② **锁内重新读取**最新 baseline（字段级 merge，绝不用函数入口时的旧快照覆盖对方刚写的字段）→
      ③ 写临时文件 + `os.replace` 原子替换（消除并发读者看到半截 JSON / 写者互相截断丢字段）。
    """
    node = "exec_report" if kind == "exec" else "test_report"
    entry = {"delivery": delivery, "url": url,
             "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")}
    if integrity:
        entry["integrity"] = integrity      # 收尾门 3d 以此比对 data 内嵌摘要（与文件 mtime 无关）
    try:
        os.makedirs(os.path.dirname(baseline_path) or ".", exist_ok=True)
        # ⛔ 锁路径走 baseline_edit.lock_path（全仓单一信源，理由见该处注释）
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from baseline_edit import lock_path as _lock_path
        _lp = _lock_path(baseline_path)
        os.makedirs(os.path.dirname(_lp), exist_ok=True)
        lock_f = open(_lp, "w")
        try:
            try:
                import fcntl
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass  # 非 POSIX / 锁不可用：退化为无锁，仍靠原子替换避免半截写
            # 锁内重读最新态，只并入本次字段，不覆盖对方字段。
            # ⛔ **解析失败绝不能回落 `{}` 继续往下写**：那会把 `versions` / `run_state` /
            #   冻结四件套 / 全部 streak 一次性抹掉，只剩一个 `report_deliveries`，
            #   而函数还 `return True` 报「台账已写」—— 全链路状态归零且无人察觉。
            #   同 `autopilot-deploy-watch.py` 对损坏 baseline 的既定纪律：宁可不写。
            if not os.path.exists(baseline_path):
                sys.stderr.write("⚠️ baseline 不存在 → 放弃写 report_deliveries（⛔ 不新建桩文件）\n")
                return False
            try:
                with open(baseline_path, encoding="utf-8") as _bf:
                    data = json.load(_bf)
                if not isinstance(data, dict):
                    raise ValueError("baseline 顶层不是对象")
            except Exception as _exc:
                sys.stderr.write("⚠️ baseline 解析失败（%s）→ 放弃写 report_deliveries，"
                                 "⛔ 不以空对象重建（会抹掉 versions / run_state / 冻结字段）\n" % _exc)
                return False
            deliveries = data.setdefault("report_deliveries", {})
            deliveries[build] = {**deliveries.get(build, {}), node: entry}
            tmp = baseline_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, baseline_path)  # 原子替换
        finally:
            lock_f.close()
        return True
    except OSError:
        return False


def _extract_payload_from_js(js_path):
    """从 data/{build}.js 的 IIFE `window.X.push( <JSON> );` 里抽出 payload 对象。
    用 JSONDecoder.raw_decode 从第一个 `{` 起解析首个 JSON 值、忽略尾部包裹，稳健不靠正则。"""
    with open(js_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    marker = content.find(".push(")
    if marker < 0:
        raise ValueError("未找到 `.push(`（非 emit-report 生成的 data 文件？）")
    start = content.find("{", marker)
    if start < 0:
        raise ValueError("`.push(` 后未找到 JSON 对象起始 `{`")
    obj, _ = json.JSONDecoder().raw_decode(content[start:])
    return obj


def verify_reports(reports_root, as_json):
    """批量契约校验 + 防篡改巡检——扫全仓 docs/reports/*/{AI执行报告,AI测试报告}/data/*.js，
    对每个历史 build 跑 validate_payload（发现存量白屏根因）+ 校 `_integrity`（发现手改）。
    任一文件契约不过 / 被篡改 → 退出码 4；全绿 → 0。"""
    kind_by_dir = {"AI执行报告": "exec", "AI测试报告": "test"}
    files = []
    for cn_dir in kind_by_dir:
        files += glob.glob(os.path.join(reports_root, "*", cn_dir, "data", "*.js"))
    files = sorted(f for f in files if not os.path.basename(f).startswith("示例_"))

    report = {"scanned": len(files), "clean": 0, "schema_bad": [], "tampered": [], "unparsable": []}
    for fp in files:
        cn_dir = os.path.basename(os.path.dirname(os.path.dirname(fp)))
        kind = kind_by_dir.get(cn_dir)
        rel = os.path.relpath(fp)
        try:
            payload = _extract_payload_from_js(fp)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            report["unparsable"].append({"file": rel, "error": str(e)})
            continue
        errs = validate_payload(kind, payload) if kind else ["无法从目录判定 kind"]
        embedded = payload.get("_integrity") if isinstance(payload, dict) else None
        tampered = False
        if embedded:
            recomputed = _payload_checksum(payload)
            tampered = (recomputed != embedded)
        elif isinstance(payload, dict) and payload.get("buildNo") is not None:
            tampered = True        # emit-report 产物恒带 _integrity；缺了 = 被删或手写
        if tampered:
            report["tampered"].append({"file": rel, "embedded": embedded, "recomputed": _payload_checksum(payload)})
        if errs:
            report["schema_bad"].append({"file": rel, "kind": kind, "errors": errs})
        if not errs and not tampered:
            report["clean"] += 1

    bad = len(report["schema_bad"]) + len(report["tampered"]) + len(report["unparsable"])
    if as_json:
        report["ok"] = (bad == 0)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"📋 verify-reports：扫描 {report['scanned']} 个 build 报告 data，"
              f"干净 {report['clean']} · 契约不过 {len(report['schema_bad'])} · "
              f"疑似手改 {len(report['tampered'])} · 无法解析 {len(report['unparsable'])}")
        for b in report["schema_bad"]:
            print(f"  ⛔ 契约不过 {b['file']}（kind={b['kind']}）：")
            for e in b["errors"]:
                print(f"      - {e}")
        for t in report["tampered"]:
            print(f"  🚨 疑似手改 {t['file']}：checksum 不匹配（渲染将白屏/失真，应经 emit-report.py 重新生成）")
        for u in report["unparsable"]:
            print(f"  ⚠️ 无法解析 {u['file']}：{u['error']}")
        if bad == 0:
            print("  ✅ 全部历史 build 报告契约合规、未见手改。")
    return 4 if bad else 0


def main():
    # verify-reports 子命令：批量巡检（不需 emit 的 --kind/--build/--data 必填参数，故前置短路）
    _argv = sys.argv[1:]
    if _argv and _argv[0] == "verify-reports":
        vp = argparse.ArgumentParser(prog="emit-report.py verify-reports",
                                     description="批量契约校验 + checksum 防篡改巡检所有历史 build 报告")
        vp.add_argument("--repo-root", default=".")
        vp.add_argument("--reports-root", default="docs/reports")
        vp.add_argument("--json", action="store_true")
        vargs = vp.parse_args(_argv[1:])
        os.chdir(vargs.repo_root)
        return verify_reports(vargs.reports_root, vargs.json)
    ap = argparse.ArgumentParser(
        description="AI执行/测试报告确定性产出器",
        epilog="子命令：emit-report.py verify-reports [--repo-root .] [--reports-root docs/reports] [--json]"
               " —— 批量契约校验 + checksum 防篡改巡检所有历史 build 报告（不过 → 退出码 4）")
    ap.add_argument("--kind", required=True, choices=("exec", "test"))
    ap.add_argument("--version", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--data", required=True, help="结果 JSON 文件（push 到全局容器的对象）")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--templates-root", default=runtime_text('__AIDP_HOME__/templates/reports', __file__))
    ap.add_argument("--reports-root", default="docs/reports")
    ap.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json")
    ap.add_argument("--record-baseline", type=int, choices=(0, 1), default=1)
    ap.add_argument("--force-amend", action="store_true",
                    help="目标 build 已冻结时强制写入（仅修正笔误）；追加 amendments[] 留痕")
    ap.add_argument("--amend-reason", default="",
                    help="--force-amend 的修订原因（写入 amendments[]）")
    ap.add_argument("--allow-schema-warn", action="store_true",
                    help="★ 逃生阀：把数据契约 fail-fast 降级为 WARN 后照常写盘（仅临时救火），"
                         "并在 data 里 schemaWarnings[] 留痕")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--keep-input", action="store_true",
                    help="保留 --data 输入草稿（默认成功产出报告后自动删除该临时 JSON，避免 memory/ 堆积）")
    ap.add_argument("--patch", action="store_true",
                    help="增量回填模式：读现有 data/{build}.js 的 payload → 用 --data 传入的字段【顶层浅合并】覆盖 → 写回。"
                         "用于 finalize 阶段只传变化字段（如 testSummary）增量更新骨架，无需重构整份 payload / 从 data.js 正则抠。"
                         "现有 data 不存在时降级为普通写入（等价非 --patch）。")
    args = ap.parse_args()

    os.chdir(args.repo_root)
    cn_dir, global_var, pages, type_en = KIND_MAP[args.kind]
    report_dir = os.path.join(args.reports_root, args.version, cn_dir)
    tpl_dir = os.path.join(args.templates_root, cn_dir)

    out = {"ok": False, "kind": args.kind, "build": args.build, "report_dir": report_dir}
    try:
        payload = _load_json(args.data)
        if payload is None:
            raise ValueError(f"结果 JSON 读取失败：{args.data}")
        # --patch 增量回填：读现有 data/{build}.js → 顶层浅合并（传入字段覆盖）→ 后续正常校验+写回。
        if args.patch:
            existing_js = os.path.join(report_dir, "data", f"{args.build}.js")
            if os.path.isfile(existing_js):
                try:
                    base_payload = _extract_payload_from_js(existing_js)
                    if isinstance(base_payload, dict) and isinstance(payload, dict):
                        base_payload.pop("_integrity", None)  # 旧 checksum 作废，写回时按合并后内容重算
                        merged = dict(base_payload)
                        merged.update(payload)               # 传入字段顶层覆盖（如 testSummary 整体替换）
                        payload = merged
                        out["patched_from"] = existing_js
                    else:
                        out["patch_skipped"] = "现有 data 或传入 payload 非对象，降级普通写入"
                except (OSError, ValueError, json.JSONDecodeError) as e:
                    out["patch_skipped"] = f"现有 data 解析失败({e})，降级普通写入"
            else:
                out["patch_skipped"] = "现有 data 不存在，降级普通写入"
        if args.kind == "exec":
            inherited = inherit_test_facts(payload, args.reports_root, args.version, args.build)
            if inherited:
                out["inherited_from_test_report"] = inherited
            derived = derive_test_summary(payload, args.reports_root, args.version, args.build)
            if derived:
                out["testSummary_derived"] = derived
        # ★ 报告不可变门（item 1）：目标 build 已 finalize（ai_report_finalized）→ 拒绝覆盖 data。
        #   任何结论变化都须铸新 build 复测；唯一逃生阀 = --force-amend（修正笔误，追加 amendments[] 留痕）。
        finalized, fin_at = build_finalized(args.baseline, args.version, args.build)
        if finalized and not args.force_amend:
            msg = (f"build {args.build} 报告已冻结（ai_report_finalized @ {fin_at}）→ 拒绝写入。"
                   f"任何测试结论变化（代码修复 / 口径澄清 / 用例调整）请铸新 build 跑新一轮；"
                   f"如确需修正明显笔误，用 --force-amend --amend-reason '<原因>' 强制并在报告内留痕")
            out.update({"frozen": True, "finalized_at": fin_at, "error": msg})
            print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else f"⛔ {msg}")
            return 2
        if finalized and args.force_amend:
            # ⛔ `--force-amend` 是**报告不可变门的唯一逃生阀**，缺原因即拒绝——写一个
            #   「（未填原因，待补）」占位串放行，等于两把锁一起穿过去：本门放行了，
            #   而 ceremony-gate 3d 只校「有没有晚于 finalize 的 amendments[] 条目」、
            #   不校 reason 是不是占位，于是改动无从追溯、无人知道改了什么、为什么改。
            if not (args.amend_reason or "").strip():
                sys.stderr.write("⛔ --force-amend 必须带 --amend-reason <为什么要改这份已 finalize 的报告>："
                                 "它是不可变门的唯一逃生阀，无原因的修改事后无从追溯。\n")
                return 2
            amend = {"at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
                     "reason": args.amend_reason.strip(),
                     "note": "force-amend 修正笔误，非新一轮测试结论"}
            if isinstance(payload, dict):
                payload.setdefault("amendments", []).append(amend)
            out["amended"] = amend
        enrich_retest(payload, args.baseline, args.version, args.build)  # item 6：注入复测关系
        enrich_build_no(payload, args.build)  # P1-6：从 --build 派生 buildNo 回填（防满页 #undefined）
        if args.kind == "test":
            # 注入本轮增量用例集（incremental_cases.py 从 git 算出）——报告据此
            # 把「测试类型」写成「全量（含本轮增量 N 条）」并点名逐条结果。
            enrich_incremental(payload, args.baseline, args.version, args.build)
        # ★ P0-1 数据契约 fail-fast：字段名/结构/单位漂移在写盘前拦下（执行体是 AI，必然会漂，不能靠散文契约自觉）
        schema_errs = validate_payload(args.kind, payload)
        if schema_errs:
            if args.allow_schema_warn:
                for e in schema_errs:
                    print(f"[schema WARN] {e}", file=sys.stderr)
                if isinstance(payload, dict):
                    payload["schemaWarnings"] = schema_errs  # 数据里留痕（类似 amendments[]）
                out["schema_warnings"] = schema_errs
            else:
                out["schema_errors"] = schema_errs
                tpl_ex = os.path.join(tpl_dir, "data", "示例_build1001.js")
                msg = (f"数据契约校验未通过（{len(schema_errs)} 项）：\n  - "
                       + "\n  - ".join(schema_errs)
                       + runtime_text(f"\n契约单一信源：{tpl_ex}' + __AIDP_HOME__/templates/reports/README.md；'", __file__)
                       + "写结果 JSON 前请先读示例文件对齐字段名/结构/单位。"
                       + "临时救火可加 --allow-schema-warn（会在 data 头部 schemaWarnings[] 留痕）。")
                out["error"] = msg
                print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else f"⛔ {msg}")
                return 3
        out["scaffolded"] = ensure_skeleton(report_dir, tpl_dir)
        out["data_file"] = write_data_file(report_dir, args.build, payload, global_var)
        out["registered_pages"] = register_script(report_dir, args.build, pages)
        out["stray_markdown"] = scan_stray_markdown(report_dir)
        out["ok"] = os.path.isfile(os.path.join(report_dir, "index.html")) and \
            os.path.isfile(out["data_file"])
    except (OSError, ValueError, FileNotFoundError) as e:
        out["error"] = str(e)
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json else f"⛔ 本地 SPA 产出失败：{e}")
        return 1

    # ---- 交付（报告链接 + 台账）----
    delivery, url, detail = delivery_link(args.reports_root, args.version, cn_dir, args.build)
    if args.record_baseline:
        try:
            record_baseline(args.baseline, args.kind, args.build, args.version, delivery, url,
                            integrity=(payload or {}).get("_integrity") if isinstance(payload, dict) else None)
        except Exception as e:      # noqa: BLE001 — 台账写失败必须让调用方看见
            out.setdefault("errors", []).append(f"交付台账写入失败：{e}")
    out.update({"delivery": delivery, "access_url": url,
                "report_path": os.path.join(report_dir, "index.html"),
                "delivery_detail": detail})

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"✅ {cn_dir} SPA 产出：{report_dir}")
        print(f"   data：{out['data_file']}  注册页：{', '.join(out['registered_pages'])}")
        if out["stray_markdown"]:
            print(f"   ⚠️ 检出违规 markdown（应删，HTML SPA 铁律）：{', '.join(out['stray_markdown'])}")
        print(f"   🔗 报告链接：{url}  （{detail}）")

    # ★ 成功产出报告后自动清理 --data 输入草稿（它只是喂给本脚本的临时 JSON，HTML 报告已生成即无用）；
    #   best-effort：删不掉不影响本次结果（仅提示），--keep-input 可保留供调试。命令端已把该草稿写到
    #   对应报告目录下（docs/reports/{V}/AI执行报告|AI测试报告/.build-input-{BUILD}.json，非 memory/ 根目录），
    #   配合 .gitignore 忽略，避免每个 build 堆积一份临时 JSON 污染工作区/仓库。
    if out.get("ok") and not args.keep_input:
        try:
            if os.path.isfile(args.data):
                os.remove(args.data)
                out["input_cleaned"] = args.data
        except OSError as e:
            print(f"   ⚠️ 输入草稿清理失败（不影响报告）：{args.data} — {e}", file=sys.stderr)

    # ★ 算出来的 `ok` 必须**用**在退出码上。⛔ 只算不用 = SPA 注册失败 / 交付台账写失败时
    #   脚本仍 exit 0，调用方（phase-3-4 / 3-9 / aiauto 3.2.6 / 3.7）据此判「报告已产出」
    #   继续推进；缺失要等到 ceremony-gate 按台账核验时才炸 —— 届时 dev_fail_streak 已经
    #   bump 过，诊断指向的是错误的环节。
    if not out.get("ok"):
        sys.stderr.write("⛔ 报告产出不完整（index.html 或 data 文件缺失）"
                         "—— ⛔ 别按「报告已产出」继续推进\n")
        return 1
    if out.get("errors"):
        for e in out["errors"]:
            sys.stderr.write(f"⛔ {e}\n")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
