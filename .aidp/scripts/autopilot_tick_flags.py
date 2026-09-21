#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""autopilot_tick_flags.py — 7×24 两条 loop 的「本 tick 变量」解析 / 落盘 / 读回（脚手架契约脚本）。

## 为什么必须有本脚本

`/sprint-autopilot` 与 `/sprint-aiauto-test` 的正文被拆成几十份 flow 分片，**每份分片是一次
独立的 Bash 工具调用** —— shell state 不跨调用持久。于是长期存在同一个形状的 Critical：

    A 分片 `WILL_BROWSER_TEST=…`  →  B 分片 `if [ "${WILL_BROWSER_TEST:-0}" = 1 ]`

读的那一侧**必然取空**，`${VAR:-默认}` 静默落到默认值，判据恒真或恒假。已确认的实例：

  · `SKIP_DEV` / `SKIP_DEPLOY` / `NO_PLANNING` / `FORCE_REPLAN` / `--target` / `--select`
    **全仓没有任何解析落点** —— 即"流程裁剪的唯一来源是用户显式声明"这条铁律，
    它所依赖的"显式声明"根本没被读进来：`--skip-dev` 恒失效、test-only 入口不可达。
  · `PROBE_PASSED`（就绪探针出口条件）零赋值 → 游标永远停在 `3.2.1-probe`、build 永不收口。
  · `GATE_STAGE` / `EXPECT_CARDS` 依赖跨分片的 `WILL_BROWSER_TEST`、`PLANNING_DONE`
    → 收尾门期望集恒错 → `dev_fail_streak` 累计 → 3 tick 后冻结待人。

"在每个分片里重新赋一遍值"治不了（默认路径会漂），"把派生提前"也治不了（还是跨调用）。
唯一可靠解 = **落盘到 baseline + 下游读回**，而落盘/读回的样板代码若散写在分片里，
既撑爆分片体积上限（20480B），又会再次滋生同类手写错误。故收成本脚本：

⛔ **每一条都必须带 `--command`**（见下方「命名空间」）——漏了就落回默认的 `autopilot` 键，
在 aiauto-test 侧表现为"写进去了却读不回来"的静默失效。

    解析：python3 AIDP_HOME/scripts/autopilot_tick_flags.py parse --command autopilot   --arguments "$ARGUMENTS"
    落盘：python3 AIDP_HOME/scripts/autopilot_tick_flags.py set  --command autopilot   WILL_BROWSER_TEST 1
    读回：eval "$(python3 AIDP_HOME/scripts/autopilot_tick_flags.py --command autopilot --shell)"   # ← 分片里只此一行
    （aiauto-test 侧把三处 `autopilot` 换成 `aiauto-test`。）

## 命名空间

**按 `--command` 分键**：`autopilot.tick.<command>`。两条 7×24 链路（`/loop 10m /sprint-autopilot`
与 `/loop 5m /sprint-aiauto-test`）**都**在 tick 起点调 `parse`，而 `parse` 会先 `del` 再整段重写 ——
曾共用一个 `autopilot.tick` 键，于是任一方开 tick 就把对方本轮已落盘的变量**全部清空**；
10min tick 必然跨越 ≥1 次 5min tick，标准挂法下 100% 发生。分键后两侧互不影响。

**每个 tick 在 `parse` 时整段重写**，不残留上一 tick 的值 —— 与 `autopilot.unattended_confirmed`
那种"只写不读的诊断留痕"是两回事，绝不能拿历史值当本轮判据。

⚠️ 需要跨链路可见的值（如 `WILL_BROWSER_TEST`）**不要指望 tick 命名空间**，走 baseline 版本级字段。

## 写入纪律

所有写操作一律 shell out 到 `baseline_edit.py`（`.json.lock` 加锁 + 原子替换），
**绝不自己开文件写 JSON** —— baseline 由两条 `/loop` 并发读写，直写必丢写（约定见
`memory/README.md`「并发写铁律」）。

退出码：0 = 成功；1 = 落盘失败；2 = 用法错误。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str((_AidpPath(__file__).resolve().parent if _AidpPath(__file__).resolve().parent.name == "scripts" else _AidpPath(__file__).resolve().parents[1] / "scripts"))
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_relpath
import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time

BASELINE_EDIT = os.path.join(runtime_relpath("", __file__), "scripts", "baseline_edit.py")
# ⚠️ **按命令分命名空间**（曾是同一个常量 `"autopilot.tick"`）：
#    两条 7×24 链路（`/loop 10m /sprint-autopilot` 与 `/loop 5m /sprint-aiauto-test`）**都**在
#    tick 起点调 `parse`，而 `parse` 会先 `del NS` 再整段重写。共用一个键 ⇒ 任一方开 tick
#    就把对方本轮已落盘的变量**全部清空**——而 10min tick 必然跨越 ≥1 次 5min tick，
#    标准挂法下 100% 发生。受害面包括 SKIP_DEV / AUDIT_VERDICT / WILL_BROWSER_TEST 等无回落的变量，
#    以及 TARGET_FLAG_VALUE / NO_NOTIFY / HAS_UNATTENDED_FLAG 这些**两命令同名**的（直接串值）。
#    ⛔ 分开后，`--shell` / `parse` / `set` 必须显式传 `--command`，否则默认 `autopilot` 会读错命名空间。
NS_BASE = "autopilot.tick"


def _ns(command: str) -> str:
    return f"{NS_BASE}.{command}"

# ── flag → 变量名。布尔 flag 出现即 1、否则 0；带值 flag 取其后一个 token ──────────
# ⚠️ 新增 flag 时**必须同时**加进这里 —— 参数表里写了、这里没解析，就等于那个 flag 不存在
#    （`--skip-dev` 就是这么"存在于文档、失效于实现"了很久）。
# LOOP_EVIDENCE 的回看窗口：取 autopilot 10m 周期的 ~4 倍，容得下一次长 tick + 一次跳拍。
LOOP_EVIDENCE_WINDOW_SECONDS = int(os.environ.get("LOOP_EVIDENCE_WINDOW_SECONDS", "2400"))

BOOL_FLAGS = {
    "autopilot": {
        "--unattended": "HAS_UNATTENDED_FLAG",
        "--once": "HAS_ONCE_FLAG",
        "--no-loop": "HAS_NO_LOOP_FLAG",
        "--skip-dev": "SKIP_DEV",
        "--skip-deploy": "SKIP_DEPLOY",
        "--skip-pre-release": "SKIP_PRE_RELEASE",
        "--skip-aiauto-test": "SKIP_AIAUTO_TEST",
        "--no-planning": "NO_PLANNING",
        "--force-replan": "FORCE_REPLAN",
        "--batch-one-tick": "BATCH_ONE_TICK",
        "--no-notify": "NO_NOTIFY",
        "--strict-prd": "STRICT_PRD",
        "--single-sprint": "SINGLE_SPRINT",
        "--watch": "WATCH_MODE",
    },
    "aiauto-test": {
        "--unattended": "HAS_UNATTENDED_FLAG",
        "--once": "HAS_ONCE_FLAG",
        "--no-loop": "HAS_NO_LOOP_FLAG",
        "--skip-login": "SKIP_LOGIN",
        "--no-notify": "NO_NOTIFY",
        # ⛔ 以下四个是本命令**已正式定义并写明行为**的 flag，此前未登记 ⇒ `parse` 解析不出、
        #    跨分片传不了；`--free-scan` / `--capture-warnings` 还需透传进 Phase 2 run-context。
        "--free-scan": "FREE_SCAN",
        "--capture-warnings": "CAPTURE_WARNINGS",
        "--skip-mcp-check": "SKIP_MCP_CHECK",
        "--headed-glance": "HEADED_GLANCE",
    },
}
# ⛔ 本表必须覆盖两条命令**全部**取值型 flag（判据 = 命令文档里 `--x <y>` 形态的全集）。
#    漏登一个不是"少一个变量"——下面 USER_INTENT 的自由文本提取用 `_vf = set(VALUE_FLAGS[...])`
#    判断"下一个 token 是不是某 flag 的值"，漏登的 flag 其值会被当成**用户口述意图**收进
#    USER_INTENT：若 `--watch-interval` 漏登，`/sprint-autopilot --watch-interval 5m` → USER_INTENT="5m"，
#    phase-3-2 的意图分流于是拿一个参数值去 grep 关键词。
VALUE_FLAGS = {
    "autopilot": {"--target": "TARGET_FLAG_VALUE", "--watch-interval": "WATCH_INTERVAL"},
    "aiauto-test": {"--target": "TARGET_FLAG_VALUE", "--select": "SELECT_FLAG_VALUE",
                    "--role": "ROLE_FLAG_VALUE"},
}

# ★ 由分片在运行中派生、需要被**后续分片**读到的变量（非 flag）。
#   登记在此的名字才允许 `set`，防止拼错变量名后静默写进一个没人读的键
#   —— 那正是 `report_deliveries.access_url`（写 `url`、读 `access_url`）那类事故的形状。
DERIVED_VARS = {
    "autopilot": {
        "ENTRY_MODE",            # full | test-only（由 SKIP_DEV / 用户意图派生，phase-3-2）
        "PLANNING_DONE",         # 本版规划产物是否齐全（phase-3-3）
        "DEPLOY_MODE",           # cloud | local | none（读 PRD autopilot_decisions，phase-3-5）
        "CLOUD_READY_URL",       # 就绪探针 URL（读 PRD，phase-3-5 出口路由）
        "CLOUD_READY_TIMEOUT",   # 就绪探针总超时秒（PRD deployment.cloud_ready_timeout_seconds，缺省 600）
        "CLOUD_READY_INTERVAL",  # 就绪探针间隔秒（PRD deployment.cloud_ready_interval_seconds，缺省 15）
        "CICD_PIPELINE_BOUND",   # 是否已接入 CICD 流水线 0/1（读 memory/aidp-config.yaml cicd 段，phase-3-5 出口路由）
        "WILL_BROWSER_TEST",     # 本 build 是否由测试链路关闭（phase-3-8）
        "PROBE_PASSED",          # 就绪探针是否通过（phase-3-7 Step D 的出口条件）
        "CURRENT_SPRINT",  # supply-check: ignore phase-3-5.md 内就地按计划↔已关闭差集算        # 本 tick 正在跑的 Sprint 号
        "REMAINING_SPRINTS",     # supply-check: ignore phase-3-5.md 内就地按计划↔已关闭差集算
        "NEXT_SPRINT_NO",  # supply-check: ignore 同上：就地算，不跨分片传递        # 下一个待跑 Sprint 号（空 = 全部跑完）
        "FIRST_SPRINT",  # supply-check: ignore phase-3-4.md 内就地 grep 研发执行计划赋值          # 本轮首个 Sprint 号（yield-tick 豁免判据）
        "AUDIT_VERDICT",         # version-auditor 终审结论
        "TRIGGER_REASON",  # supply-check: ignore 通知文案里的 {占位符}、非 shell 变量        # 本轮触发原因（诊断用）
        "PRE_RELEASE_VERSION",   # 本轮准发布版本号（Phase 2）
        # ★★ TARGET_VERSION 此前【根本不在本表里】——而 autopilot 侧有 21 份分片读它、
        #    无一自赋值（唯二"赋值"是占位符文本 `TARGET_VERSION="<Phase 0.3.4 识别结果>"`）。
        #    后果不是少一个变量，是**整个 run_state 状态机不存在**：每个 Phase 出口的
        #    `baseline_edit.py --version "$TARGET_VERSION" run-state …` 因缺 --version 全部 rc=1，
        #    run_state 一次都没落盘 → 下一 tick 的「1.3bis 续跑短路门」取空失效 → 回落 PRD
        #    变化检测判 no-change → 立即退出，**Sprint-002 起永不执行**；通用 stuck 熔断也因
        #    传空版本返回 2 被当作"入参错跳过"，唯一的兜底熔断同时失效。
        "TARGET_VERSION",        # 本轮目标版本号（真源 autopilot.target_version，兜底 current-version）
        "USER_INTENT",           # 交互式下用户输入原文（意图判定）
        # ⛔ 未登记时 Phase 0.4 只有散文「记 PENDING_MERGE_TO」、无处可写，而 Phase 3.2 推送围栏
        #    只有 `PENDING_MERGE_TO="${PENDING_MERGE_TO:-}"` 自我兜空 → 合并回部署源整段**不可达**：
        #    feature 分支推上去了、部署源没有本轮代码 → CICD 构建旧产物、探针照样绿、
        #    测试链路对着**旧版本**跑全套并判「通过」。全程零报错，是最危险的一类。
        "PENDING_MERGE_TO",      # 需合并回的部署源分支（branch_strategy=feature 时由 Phase 0.4 落盘）
        # ↓ 真源在 baseline，由 BASELINE_FALLBACK / DERIVED_FROM 自动供给，无需任何分片 set
        "BUILD",                 # 当前 build 标识（versions.{V}.current_build）
        "BUILD_SEQ",             # build 序号（由 BUILD 推导）
        "NOTIFY_ENABLED",        # 里程碑通知开关（memory/aidp-config.yaml notify 段 + baseline notify_enabled，缺省 0）
        "LOOP_UNATTENDED",       # 本 tick 是否无人值守（autopilot.loop_unattended_this_tick）
        # ★ 与 aiauto-test 侧对称登记：autopilot 的 phase-0-1 只把它写进 baseline 根键
        #   `autopilot.wake_source_this_tick`，未登记时 `set --command autopilot` 直接 rc=2、
        #   `--shell` 读回恒空 ⇒ 各 yield/熔断点的 `${HAS_WAKE_SOURCE:-0}` 拿不到真值。
        "HAS_WAKE_SOURCE",       # 1=有下一 tick（/loop 或 cron）→ 可 yield；0=不许 yield
        # ★ 由 parse 自动写：本命令近期是否被反复唤起（确定性旁证，见 parse 里的说明）。
        #   它只**增补** IS_LOOP_CONTEXT，绝不反向否定。
        "LOOP_EVIDENCE",
    },
    "aiauto-test": {
        # ★ TARGET_VERSION 必须登记在本侧：测试链路 Phase 0.2 用 current-version **自己选版**，
        #   而未登记时 `set --command aiauto-test TARGET_VERSION` 直接 rc=2 写不进去，
        #   union 级回落又指向 `autopilot.target_version` —— 下游于是一律解析成 autopilot 的开发版本：
        #   从下版目录找用例、报告写进下版、emit-report 覆盖 autopilot 正在跑的 build、
        #   冻结与 streak 全记到错版本上。常态 tick（上版待测 + 下版已开工）必然命中。
        "TARGET_VERSION",
        "REQUIRES_LOGIN",        # 被测应用是否需要登录（真源 = Phase 0.0.5 解析测试方案「连接模式/登录」）
        # ★ 测试链路此前**完全没有唤醒源概念**（全仓零命中），而它同样有 `UNATTENDED_YIELD` 点：
        #   P0-4 交互式单次补测与 2.5.1 自愈交接都是 `--once --unattended`（LOOP_UNATTENDED=1）
        #   却**没有下一 tick** ⇒ 任一 yield 直接 exit、测试半途而废且无结构级拦截
        #   （Stop hook 只读 autopilot 的 run_state，测试链路根本不写）。
        "HAS_WAKE_SOURCE",       # 1=有下一 tick（/loop 上下文或 --no-loop）→ 可 yield；0=不许 yield
        "LOOP_EVIDENCE",         # 同 autopilot 侧：parse 自动写的反复唤起旁证
        "THIS_ROUND_FAIL_COUNT",  # supply-check: ignore phase-3-3.md 就地赋值 + fail-closed 兜底 # 本轮失败用例数（收敛判据）
        # ⛔ CONVERGED 此前【未登记】：算出点在 phase-3-3.md，消费点在 3-4 / 3-5 三处**别的分片**，
        #    而 `set` 对未登记名直接 exit 2 ⇒ 跨分片传不过去 ⇒ `[ "$CONVERGED" = "1" ]` 恒假 ⇒
        #    #3 通知永不发、AI执行报告永停骨架态，开发链路 Phase 2 收敛门恒不过。
        "CONVERGED",             # 本轮是否收敛（1=收敛；由 phase-3-3 判定后 set，3-4/3-5 消费）
        # ⛔ 同 CONVERGED 的理由：3.4 通知段已随 3.4 外置到 **phase-3-3b.md**，与算出点
        #    phase-3-3.md 不再同片；不登记则 `set` exit 2、回读恒空 ⇒ 通知「不适用 N 条」
        #    恒显示为空或 0，而 na 恰恰是"别把不适用读成通过"这条纪律的可见性来源。
        "THIS_ROUND_NA",         # 本轮 n/a（不适用）条数，来自上游 gen_report 的 counts.na
        # 上游 I7：direct pass 缺轻量事实的条数。不阻断，但必须出现在通知与报告里——
        # 不然"跑过且通过"与"跳过后填 pass"在交付物上完全无从区分。
        "THIS_ROUND_DIRECT_NOEV",
        # ⛔ 以下两个此前**未登记**：算出点与消费点不在同一分片，`export` 跨不过 Bash 调用，
        #    `set` 又因未登记而 exit 2 ⇒ 回读恒空。
        #    SELECT_MODE 恒空 ⇒ `[ "$SELECT_MODE" != "all" ]` 为真 ⇒ 走子集分支并把空值传给 `--select`，
        #    "跑了 5 条 P0 全绿就当测过了"的风险复活（无人值守本应强制 all）。
        #    SKIP_REPORT 恒空 ⇒ standalone 轮次照样进截图硬核验，SHOT_DIR 拼出空 BUILD 段。
        "SELECT_MODE",           # all | subset（无人值守强制 all）
        "SKIP_REPORT",           # 1=本轮不产 AI测试报告（standalone 直接调用）
        "GUI_OK",                # 图形环境是否可用
        "CHROME_BIN",            # 实际使用的 chrome 可执行路径
        "CUR_PHASE",  # supply-check: ignore invariants.md 内就地 baseline_edit get 赋值，非跨分片传递             # 当前 Phase 游标
        # ↓ 由 Phase 0 派生、后续 Phase 消费（真源在本轮推导，须显式 set）
        # ⛔ 同 CONVERGED / SELECT_MODE 的理由：`DECLARED_REMOTE` 算出点在 phase-0-1（0.0.5 解析
        #    测试方案「二·连接模式」），消费点在 phase-0-2（0.0.7 护栏）——**两个分片、两次独立
        #    Bash 调用**，原先只 `export`，跨不过去。回读恒空 ⇒ `${DECLARED_REMOTE:-0}` 落 0 ⇒
        #    `MODE=remote` 分支**结构上不可达**，「驱动由声明决定」这条设计目标在确定性层失效。
        #    （失效方向 fail-safe：恒落本地 CLI，故不炸；但声明就是不起作用。）
        "DECLARED_REMOTE",       # 1=测试方案/用户意图显式声明远程 MCP
        "MODE",                  # local | remote（连接模式）
        "RENDER_MODE",           # headless | headed（本轮渲染模式）
        "TESTPLAN_RENDER_MODE",  # 测试方案声明的渲染模式
        "TESTPLAN_CREDS_READY",  # 测试方案里账号是否已填全
        "DEFERRED_HEADED_CASES", # 无头轮次里被推迟到有头轮的用例
        # ↓ 真源在 baseline，自动供给（同 autopilot 侧）
        "BUILD", "BUILD_SEQ", "REPORT_ENABLED", "DRIVER",
        "NOTIFY_ENABLED", "LOOP_UNATTENDED",
    },
}

# 供 `--shell` 输出、也供 check_flow_var_refs.py 识别的**全集**（两个命令合并）。
ALL_VARS = sorted(
    set(v for m in BOOL_FLAGS.values() for v in m.values())
    | set(v for m in VALUE_FLAGS.values() for v in m.values())
    | set(v for s in DERIVED_VARS.values() for v in s)
)

_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _be(args, capture=True):
    """shell out 到 baseline_edit.py（唯一加锁写入口）。"""
    cmd = [sys.executable, BASELINE_EDIT] + args
    return subprocess.run(cmd, capture_output=capture, text=True)


def _get_tick(command: str = "autopilot") -> dict:
    r = _be(["get", _ns(command), "--default", "{}"])
    raw = (r.stdout or "").strip()
    if not raw:
        return {}
    try:
        val = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return val if isinstance(val, dict) else {}


def _normalize_argv(argv):
    """把 `--arguments <值>` 归一为 `--arguments=<值>`，让 argparse 接受以 `--` 开头的值。

    ⛔ **不做这步会在最常见的调用形态上直接崩掉**：argparse 的规则是「以 `-` 开头的 token
    不作为选项值」，而本参数的值恰恰常常**就是一个 flag 串**——`$ARGUMENTS` 在
    `/loop 10m /sprint-autopilot --unattended`（文档钉死的 7×24 标准挂法）下正是单个
    `--unattended`。实测：`--arguments --unattended` → **exit 2**；
    `--arguments "--skip-dev --unattended"`（含空格、被当成一个 token）→ 正常。
    于是缺陷只在"单 flag"这一格出现，日常带两个 flag 调试时看不见。

    崩在 argparse 层的后果比"少解析一个参数"严重得多：`cmd_parse` 一行都没跑，
    其中的「先清空本 tick 命名空间」也没执行 → **上一 tick 的 `SKIP_DEV=1` 继续生效** →
    此后每个无人值守 tick 都静默走 test-only、开发永不发生，而流程裁剪的来源
    不再是「用户显式声明」（违反 autopilot 的裁剪唯一来源契约）。
    """
    out, i = [], 0
    while i < len(argv):
        if argv[i] == "--arguments" and i + 1 < len(argv):
            out.append("--arguments=" + argv[i + 1])
            i += 2
        else:
            out.append(argv[i])
            i += 1
    return out


def cmd_parse(a) -> int:
    """解析本轮参数串 → 整段重写 `autopilot.tick`（不残留上一 tick）。"""
    if a.command not in BOOL_FLAGS:
        print(f"未知 --command：{a.command}（应为 autopilot / aiauto-test）", file=sys.stderr)
        return 2
    # ★ 先无条件清空本 tick 命名空间，再写新值——即便后续解析出任何意外，
    #   也绝不让上一 tick 的裁剪 flag 残留生效（残留 = 流程裁剪来源不再是用户显式声明）。
    _be(["del", _ns(a.command)])
    # ⚠️ `$ARGUMENTS` 是**斜杠命令正文**的文本替换，不是 Bash 环境变量；而本行位于经 Read 加载的
    #    flow 分片里 —— 宿主未注入时它就是空串，于是**全部 flag 恒 0**（含 `--unattended`），
    #    `LOOP_UNATTENDED=0` ⇒ phase-1 打印配置向导后退出、永不进 Phase 2/3。
    #    这条静默失效此前只有散文兜底（"由 Claude 读用户原文补判"），没有任何机器信号。
    #    现在改成响亮告警：空入参一定打到 stderr，让"没注入"这件事可见。
    if not (a.arguments or "").strip():
        print("⚠️ [tick_flags] --arguments 为空：若本轮用户确实传了参数（如 --unattended），"
              "说明 $ARGUMENTS 未被宿主注入 —— 全部 flag 将恒 0。"
              "请由 Claude 用本轮用户输入原文重跑本行，⛔ 绝不留空。", file=sys.stderr)
    try:
        toks = shlex.split(a.arguments or "")
    except ValueError:
        toks = (a.arguments or "").split()

    out = {}
    for flag, var in BOOL_FLAGS[a.command].items():
        out[var] = "1" if flag in toks else "0"
    for flag, var in VALUE_FLAGS[a.command].items():
        out[var] = ""
        if flag in toks:
            i = toks.index(flag)
            if i + 1 < len(toks) and not toks[i + 1].startswith("--"):
                out[var] = toks[i + 1]
        else:  # 同时支持 `--target=V0.2.0` 写法
            for t in toks:
                if t.startswith(flag + "="):
                    out[var] = t.split("=", 1)[1]

    # ★ USER_INTENT = `$ARGUMENTS` 里【非 flag、非 flag 值】的自由文本（用户口述意图）。
    #   此前它登记在 DERIVED_VARS 却全仓无人写 → `--shell` 读回恒空 →
    #   `echo "$USER_INTENT" | grep -qE …`（phase-3-2.md）恒不命中、意图分流整条失效。
    #   在这里落盘是唯一正确的位置：只有 parse 拿得到原始参数串。
    if "USER_INTENT" in DERIVED_VARS.get(a.command, []):
        _vf = set(VALUE_FLAGS[a.command])
        _skip, _free = False, []
        for t in toks:
            if _skip:
                _skip = False
                continue
            if t.startswith("--"):
                _skip = t in _vf and "=" not in t   # `--target V0.2.0` 的值要跳过
                continue
            _free.append(t)
        out["USER_INTENT"] = " ".join(_free)

    # ★★ LOOP_EVIDENCE —— `IS_LOOP_CONTEXT` 的**确定性第二信源**。
    #   `IS_LOOP_CONTEXT` 是本架构最承重的信号，却只能靠模型就地把字面量改成 0/1：纯 shell
    #   读不到"当前 prompt 有没有 /loop"。漏改的后果不是报错，而是 `HAS_WAKE_SOURCE=0` ⇒
    #   `autopilot_fail_handle` 的 `freeze = streak >= threshold or wake == "0"` 当场生效，
    #   **任何一次瞬态失败（529 / 网络抖动 / CICD 接口超时）直接冻版本，3 次重试配额一次都用不上**。
    #   这里给它一个不依赖模型的旁证：**本命令近期是否被反复唤起**。
    #   ⛔ 判据刻意要求「窗口内 ≥2 次历史 tick」而不是 1 次 —— 手工连跑两遍不该被误升级为
    #   loop；而真正的 /loop 在一个窗口里必然留下远多于 2 条记录。
    #   ⛔ 它只**增补**唤醒源、绝不反向否定：模型已判 1 时本值无作用，避免把真 loop 判死。
    hist, now_ts = [], time.time()
    try:
        _h = json.loads((_be(["get", _ns(a.command) + "_history", "--default", "[]"]).stdout or "[]").strip() or "[]")
        hist = [float(x) for x in _h if isinstance(x, (int, float, str)) and str(x).replace(".", "", 1).isdigit()]
    except (ValueError, TypeError):
        hist = []
    recent = [t for t in hist if now_ts - t <= LOOP_EVIDENCE_WINDOW_SECONDS]
    out["LOOP_EVIDENCE"] = "1" if len(recent) >= 2 else "0"
    _be(["set", _ns(a.command) + "_history", json.dumps((recent + [now_ts])[-12:])])

    # tick 起点时刻 + 链路心跳：Stop hook / 收尾门据 tick_started_at 判「本 tick 铸的 build」，
    #   调度巡检（aidp_scheduler.py watchdog）据心跳判链路是否掉线——tick 早退也照样刷新。
    _root_key = "autopilot" if a.command == "autopilot" else "aiauto"
    _hb_key = "autopilot_loop_heartbeat_at" if a.command == "autopilot" else "aiauto_test_heartbeat_at"
    _be(["set", _root_key + ".tick_started_at", "@now", _hb_key, "@now"])

    # ★ 整段重写：先删再写，杜绝上一 tick 的裁剪 flag 残留把本轮流程悄悄砍掉。
    _be(["del", _ns(a.command)])
    r = _be(["set", _ns(a.command), json.dumps(out, ensure_ascii=False)])
    if r.returncode != 0:
        print(f"⛔ tick 变量落盘失败：{(r.stderr or '').strip()[:300]}", file=sys.stderr)
        return 1
    on = [f"{k}={v}" for k, v in sorted(out.items()) if v not in ("", "0")]
    print(f"🔧 本 tick 参数（{a.command}）：{' '.join(on) if on else '(全部默认)'}")
    return 0


def cmd_set(a) -> int:
    """落盘一个【派生变量】，供后续分片读回。"""
    name = a.name
    allowed = DERIVED_VARS.get(a.command, set()) | set(
        BOOL_FLAGS.get(a.command, {}).values()) | set(VALUE_FLAGS.get(a.command, {}).values())
    if name not in allowed:
        print(f"⛔ `{name}` 未在 autopilot_tick_flags.py 登记（{a.command}）——"
              f"拼错的变量名会静默写进一个没人读的键。请先在 DERIVED_VARS 里登记。", file=sys.stderr)
        return 2
    cur = _get_tick(a.command)
    cur[name] = a.value
    r = _be(["set", _ns(a.command), json.dumps(cur, ensure_ascii=False)])
    if r.returncode != 0:
        print(f"⛔ 落盘失败：{(r.stderr or '').strip()[:300]}", file=sys.stderr)
        return 1
    # ★ 该变量若另有 ("root", key) 回落源，把根键**一并**落盘。
    #   ⛔ 别让调用方在 flow 里自己补第二条 `baseline_edit.py set <根键>`：
    #   写 namespace 与写根键是同一件事的两半，分成两处写就必然有人只写一半 ——
    #   而只写 namespace 的那一半，在**断点续跑**（namespace 已空）的 tick 上读回空，
    #   判据吃兜底默认值，与「本来就是那个值」完全同形。
    spec = (BASELINE_FALLBACK_BY_COMMAND.get(a.command) or {}).get(name) \
        or BASELINE_FALLBACK.get(name)
    if spec and spec[0] == "root":
        _be(["set", spec[1], str(a.value)])
    return 0


# ★ 少数变量的事实真源在 baseline 的版本节点上，本 tick 没人显式落盘时从那里回落，
#   免得每个消费分片各写一遍兜底（写漏一处就是一条恒真/恒假判据）。
#   `DEPLOY_MODE` 尤其典型：它在 autopilot 侧**从来没有派生点**，只由部署阶段写进
#   `versions.{V}.deployment_mode`；消费方当裸 shell 变量用 → 取空 → `[ "" = "cloud" ]`
#   恒假 → 配了 CICD 的项目断点续跑时整段跳过 Phase 3.2.1（触发/监听/重试/就绪探针）。
#
# 取值域二分：
#   ("version", key) → `versions.{当前版本}.{key}`；("root", key) → baseline 顶层（支持点路径）。
#
# ★ 为什么要把回落做厚（而不是让每个派生点各自 `set`）：`set` 链是**写的人**的自觉，
#   写漏一处就是一条恒空判据，且静默——实测 19 个已登记变量里只有 4 个真被 set 过，
#   直接后果是「云端部署整段跳过 → last_deployed_at 永不写 → 测试链路永不启动」这条断链。
#   而这些变量的事实真源**本来就已经持久化在 baseline 里**，从那儿回落是确定性的、
#   不依赖任何人记得写。故：凡真源在 baseline 的，一律走回落；只有真源在本轮 prompt /
#   一次性推导里的（如 TESTPLAN_*）才需要显式 set。
BASELINE_FALLBACK = {
    "DEPLOY_MODE":     ("version", "deployment_mode"),
    "BUILD":           ("version", "current_build"),
    "DRIVER":          ("version", "driver_actual_pending"),
    "LOOP_UNATTENDED": ("root", "autopilot.loop_unattended_this_tick"),
    # ★ 真源 = 两条链路各自 Phase 0 第三步派生后落盘的根键。⛔ 必须有回落：
    #   它是「本 tick 让位合不合法」的唯一判据，读回恒空时下游 `${HAS_WAKE_SOURCE:-0}`
    #   只能吃兜底默认，等于把判据废掉。
    "HAS_WAKE_SOURCE": ("root", "autopilot.wake_source_this_tick"),
    "NOTIFY_ENABLED":  ("root", "notify_enabled"),
    # ★ ENTRY_MODE：本轮入口模式（full / incremental / test-only）。**必须有回落**——
    #   它此前既无 `set` 落点也无回落，`--shell` 读回恒空，于是：
    #     · `[ "$ENTRY_MODE" = "test-only" ]` 恒假 → test-only 分支不可达；
    #     · 收尾门 `--entry-mode "${ENTRY_MODE:-full}"` 恒展开成**显式的 full**，把
    #       `autopilot-ceremony-gate.py::_resolve_entry_mode` 的 baseline 回退整个旁路掉
    #       （那条回退正是为 test-only 死锁专门实现的）→ test-only 轮次每 tick 索要
    #       #1c/#1d/#2 三条本轮没发生的通知 → 3 tick 后冻结版本。
    #   真源 = Phase 3.1.0 写入的 `versions.{V}.autopilot_entry_mode`。
    "ENTRY_MODE":      ("version", "autopilot_entry_mode"),
    # ★ WILL_BROWSER_TEST 同样必须有回落：它只在 phase-3-8 写一次，而 3-8 与 3-9 的出口
    #   都把游标写成 `3.4-finish` —— 凡从这个游标**断点续跑**的 tick 都不会重跑 3-8 的派生，
    #   于是 `${WILL_BROWSER_TEST:-0}` 恒落到 0：云端 build 被当成静态-only，收尾门去要
    #   exec 交付台账（那在双 loop 下由测试链路产、此刻多半还没写）→ FAIL → bump dev_fail_streak。
    #   而一次瞬态 FAIL 就保证后两 tick 也 FAIL —— 3 tick 冻成 handoff-exhausted 的自锁。
    "WILL_BROWSER_TEST": ("version", "will_browser_test"),
    # ★ 以下五项此前同样"登记了但没人写"，`--shell` 读回恒空、判据静默失效。
    #   给出 baseline 真源 + 下方 FALLBACK_DEFAULT 兜底，消除"恒空"这一档：
    "PLANNING_DONE":   ("version", "planning_done"),        # 六类规划产物齐全（phase-3-3b 判定后写）
    "PRE_RELEASE_VERSION": ("root", "autopilot.pre_release_version"),  # Phase 0.3.3 S2 态识别后写
    "TARGET_VERSION":  ("root", "autopilot.target_version"),  # Phase 0.3.4 选版后写；空则走 DYNAMIC_FALLBACK
    "DEPLOY_MODE":     ("version", "deployment_mode"),        # 部署动作落盘；空则从 PRD 解析（见 DYNAMIC_FALLBACK）
    "CHROME_BIN":      ("root", "chrome_bin"),              # 0.0.4 本机 chrome 探测结果
    "GUI_OK":          ("root", "gui_ok"),                  # 0.0.4 显示环境探测结果
    "DEFERRED_HEADED_CASES": ("version", "deferred_headed_cases"),     # 3.4 延后的有头用例
}

# 由其它变量就地推导（无独立真源）。值为 (依赖变量, 推导函数)。
DERIVED_FROM = {
    # `V0.1.0_build1002` → `1002`；取不到 BUILD 时留空（下游 `[ -z ]` 能显式识别）
    "BUILD_SEQ":      ("BUILD", lambda b: b.rsplit("_build", 1)[-1] if "_build" in b else ""),
    # 有 current_build = autopilot 驱动 → 该产 AI测试报告 / finalize；无则直接调用，两者都不产
    "REPORT_ENABLED": ("BUILD", lambda b: "1" if b else "0"),
}

# 回落取不到时的兜底默认（避免"空串"被下游当成有意义的值）
# ★ ENTRY_MODE 缺省 full：与各消费点 `${ENTRY_MODE:-full}` 的既有口径一致，
#   保证"未显式声明入口模式"= 走全量流程（保守方向，不会把 full 误判成 test-only 而跳过开发）。
FALLBACK_DEFAULT = {
    "NOTIFY_ENABLED": "0", "LOOP_UNATTENDED": "0", "ENTRY_MODE": "full",
    # ★ fail-closed：`phase-0-7.md` 明写「取空时**不得**当成"不需要登录"——那会跳过账号收集、
    #   让需要登录的应用整批用例 block」。故缺省取 1（需要登录），宁可多问一次账号。
    "REQUIRES_LOGIN": "1",
    # ★ 无头是无人值守的安全默认（有头需 GUI/显示器，7×24 环境通常没有）
    "RENDER_MODE": "headless",
    # ★ 未判定时按"规划未完成"走：宁可多跑一次规划（幂等、可重入），也不要因恒空被当成
    #   "已完成"而跳过 /version —— 后者会让整版没有需求/设计/计划/自测就直接进开发。
    "PLANNING_DONE": "0",
    # ★ 本机 chrome / GUI 能力未探测到时按"没有"走（fail-closed）：据此只会走无头或委派远程，
    #   不会误判成"本机能开有头"而卡在无显示环境的机器上。
    "CHROME_BIN": "", "GUI_OK": "0", "DEFERRED_HEADED_CASES": "",
    # ★ 判不出唤醒源时按"没有下一 tick"走（fail-closed）：据此各熔断点会**当场**冻结并发 #4，
    #   人能看见；反向兜底成 1 则是"以为还有下一 tick"→ streak 永远停在 1、阈值恒不可达 →
    #   静默 exit 0 被上游读成"跑过了"，正是本判据要防的那种失效。
    "HAS_WAKE_SOURCE": "0",
}


def _cur_version(cur: dict | None = None) -> str:
    return (_be(["current-version"]).stdout or "").strip()


def _scope_version(cur: dict, command: str = "autopilot") -> str:
    """`("version", …)` 类回落该按【哪个版本】取值。

    ⛔ **不能直接用 `current-version`**：它的定义是「`phase_beta_done_at` 非空且
    `internal_released_at` 为空」= **Phase 2 的准发布版本**，而本轮在开发的是 Phase 3 的
    `TARGET_VERSION`。两者在标准同 tick 形态（Phase 2 归档上版 + Phase 3 开发下版）里**必然不同**，
    于是 BUILD / DEPLOY_MODE / ENTRY_MODE / PLANNING_DONE 全部取到**上一版**的值。
    更普遍的第二种失效：版本尚在开发（`phase_beta_done_at` 未写）时它返回**空串**，
    所有 version 类回落一律取空 —— `ENTRY_MODE` 恒 full、`BUILD` 恒空，正是本脚本注释里
    描述的那场灾难（test-only 轮次每 tick 索要三张没发生的卡 → 3 tick 冻结版本）。

    正确优先级：本 tick 已解析的 TARGET_VERSION → baseline `autopilot.target_version`
    （跨 tick 持久，由 Phase 0.3.4 落盘）→ 最后才回落 `current-version`。
    """
    v = str(cur.get("TARGET_VERSION", "") or "").strip()
    if v:
        return v
    # ★ 必须按命令分流：`BASELINE_FALLBACK_BY_COMMAND` 已经分流了，作用域解析没跟上时，
    #   `--command aiauto-test --shell` 会在同一次输出里自相矛盾——`TARGET_VERSION` 取
    #   **被测版本**（current-version），而 `BUILD`/`DRIVER`/`WILL_BROWSER_TEST`/
    #   `DEFERRED_HEADED_CASES` 全部取自 **autopilot 正在开发的那一版**。后果：别版本的
    #   build 号被写进被测版本节点，`REPORT_ENABLED` 由该 BUILD 推导 ⇒ standalone 轮次
    #   被误判成 autopilot 驱动。测试链路的作用域**只能是被测版本**。
    if command == "aiauto-test":
        v = _cur_version()
        if v:
            return v
    v = (_be(["get", "autopilot.target_version", "--default", ""]).stdout or "").strip()
    if v:
        return v
    return _cur_version()


def _semver_key(v: str):
    """`V0.10.0` → (0,10,0)；解析不了给 (-1,) 让它排在最后（不参与"≤ 目标版本"的选取）。"""
    m = re.match(r"^[Vv]?(\d+)\.(\d+)\.(\d+)", str(v or ""))
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (-1, -1, -1)


def _prd_deploy_mode(cur: dict | None = None) -> str:
    """从 PRD `autopilot_decisions.deployment.mode` 解析部署形态（DEPLOY_MODE 的最后兜底）。

    ★ 为什么要有这条：`versions.{V}.deployment_mode` 的**唯一写入点**在
    `flows/sprint-batch/step-6.md`，而 autopilot 链内恒传 `--skip-aiauto-test`、
    `/sprint-batch` Step 6 首行即整段跳过 —— 于是该字段在 autopilot 链内**从来没人写**。
    读回恒空后 `${DEPLOY_MODE:-none}` 展开成 `none`，连锁三处误判：
      ① `WILL_BROWSER_TEST` 恒 0 → 云端项目被当成"静态-only"就地 finalize 并发 #3，
         真实浏览器测试结论撞上「报告不可变铁律」永远进不了报告；
      ② 断点续跑时整段跳过 Phase 3.2.1（CICD 触发/监听/重试/就绪探针）；
      ③ 收尾门自算期望通知集永不含 #1d、却多要一张 #3。
    PRD 是这个事实的**原始声明处**，比 baseline 更早也更稳，故用它兜底。

    ⚠️ **必须按版本取，不能"扫到第一个声明就返回"**：本函数不接版本参数、按字典序取第一个
    命中的 PRD 时，仓库里同时存在上版与下版 PRD（autopilot「每轮处理最近的一对」的常态）
    就会取到**别的版本**的声明。真实后果：`V0.1.0` 声明 `none`、`V0.2.0` 声明 `cloud`，
    开发 V0.2.0 时取回 `none` → 上面①，云端 build 被就地静态 finalize，
    此后真实测试结论撞上「报告不可变铁律」永远写不进去。触发路径从"读空"变成"读到别的版本"，
    连锁失效完全一样，但更难发现——因为它读出来的是一个**看起来合法**的值。

    取值优先级：本轮目标版本的 PRD → 次之取**版本号 ≤ 目标版本**里最新的那个声明
    （部署形态是项目级属性、跨版本极少改，继承上一次声明远好过回落 `none`）→ 都没有才空。
    """
    import glob as _glob
    ver = _scope_version(cur or {}, (cur or {}).get("_command", "autopilot"))
    declared = {}                      # {版本目录名: mode}
    for p in sorted(_glob.glob("docs/requirements/*/产品提供/*.md")):
        pv = p.split(os.sep)[2] if len(p.split(os.sep)) > 2 else ""
        if pv in declared:
            continue
        try:
            head = "\n".join(open(p, encoding="utf-8", errors="replace").read().split("\n")[:200])
        except OSError:
            continue
        m = re.search(r"^\s*deployment:\s*$((?:\n[ \t]+.*|\n\s*)*)", head, re.M)
        if m:
            mm = re.search(r"^\s*mode:\s*([a-zA-Z-]+)", m.group(1), re.M)
            if mm:
                declared[pv] = mm.group(1).strip()
    if not declared:
        return ""
    if ver and ver in declared:
        return declared[ver]
    if ver:
        tk = _semver_key(ver)
        older = [k for k in declared if _semver_key(k) <= tk and _semver_key(k) != (-1, -1, -1)]
        if older:
            return declared[max(older, key=_semver_key)]
        return ""                      # 目标版本已知、但没有任何 ≤ 它的声明 → 不猜
    return declared[max(declared, key=_semver_key)]


def _prd_deploy_field(field: str, cur: dict | None = None) -> str:
    """按【本轮目标版本】从 PRD `autopilot_decisions.deployment.<field>` 取一个标量字段。

    ⚠️ 与 `_prd_deploy_mode` 同款按版本取值（复用其解析与版本回落口径），**不要另写一套**：
    「扫到第一个声明就返回」在「仓库里同时存在上下两版 PRD」这个 autopilot 常态下会取到别的版本。
    """
    import glob as _glob
    ver = _scope_version(cur or {}, (cur or {}).get("_command", "autopilot"))
    declared = {}
    for p in sorted(_glob.glob("docs/requirements/*/产品提供/*.md")):
        pv = p.split(os.sep)[2] if len(p.split(os.sep)) > 2 else ""
        if pv in declared:
            continue
        try:
            head = "\n".join(open(p, encoding="utf-8", errors="replace").read().split("\n")[:200])
        except OSError:
            continue
        m = re.search(r"^\s*deployment:\s*$((?:\n[ \t]+.*|\n\s*)*)", head, re.M)
        if m:
            mm = re.search(r"^\s*" + re.escape(field) + r":\s*[\"']?([^\"'\n#]+)", m.group(1), re.M)
            if mm:
                declared[pv] = mm.group(1).strip()
    if not declared:
        return ""
    if ver and ver in declared:
        return declared[ver]
    if ver:
        tk = _semver_key(ver)
        older = [k for k in declared if _semver_key(k) <= tk and _semver_key(k) != (-1, -1, -1)]
        if older:
            return declared[max(older, key=_semver_key)]
    return ""


def _cloud_ready_url(cur: dict | None = None) -> str:
    """就绪探针 URL（主：自身鉴权接口；回退：页面 URL）。真源 = PRD，⛔ 不是 baseline。

    ★ 这条修的是一个结构性不可达：`phase-3-5.md` 的 Phase 3.2 出口原本读
    `versions.{V}.cloud_ready_api_url` —— 而该键**全仓只有读、没有任何写入方**
    （它只在 PRD `autopilot_decisions.deployment` 里声明过，从未被搬进 baseline）。
    读回恒空 ⇒ 出口恒路由到 `3.3-audit` ⇒ **整段 Phase 3.2.1（CICD 触发/监听/重试/就绪探针）
    在跨 tick 续跑时被跳过**，`last_deployed_at` 永不写入，测试链路选不出版本却又心跳新鲜，
    两条 loop 一起空转且零告警。
    """
    return (_prd_deploy_field("cloud_ready_api_url", cur)
            or _prd_deploy_field("cloud_ready_page_url", cur))


def _cicd_pipeline_bound(cur: dict | None = None) -> str:
    """项目是否已接入 CICD 流水线 → "1"/"0"。

    ★ 真源 = `memory/aidp-config.yaml` 的 `cicd` 段（与 `cicd_watch.py` 定位流水线**同一处**，
    ⛔ 不得另认 baseline 里的任何副本）：
    - `provider: none` → 恒 "0"；
    - `cicd.pipelines` 声明了目标环境（PRD `autopilot_decisions.deployment.env`；未声明时任一环境）→ "1"；
    - 流水线随提交自动运行、无需逐环境映射的提供方（gitlab-ci）：其专属子段已配置即 "1"。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aidp_config
        import cicd_providers
        cfg = aidp_config.cicd_config(".")
        provider = cicd_providers.get_provider(".", cfg)
    except Exception:
        return "0"
    if provider is None:
        return "0"
    pipelines = cfg.get("pipelines") or {}
    env = _prd_deploy_field("env", cur)
    if env and env in pipelines and (pipelines[env] or not provider.needs_pipeline()):
        return "1"
    if not env and any(v or not provider.needs_pipeline() for v in pipelines.values()):
        return "1"
    if not provider.needs_pipeline() and cfg.get(provider.name):
        return "1"
    return "0"


def _notify_enabled(cur: dict | None = None) -> str:
    """里程碑通知是否可用 → "1"/"0"：`notify.enabled` 为真且至少一个渠道**本地具备发送条件**
    （webhook 环境变量已设置 / 命令存在；判据单一信源 = `notify.channel_ready`，与 Stop hook、preflight 同源）。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import notify
        return "1" if notify.notify_ready(".") else "0"
    except Exception:
        return "0"


def _cloud_ready_timeout(cur: dict | None = None) -> str:
    v = _prd_deploy_field("cloud_ready_timeout_seconds", cur)
    return v if v.isdigit() else "600"


def _cloud_ready_interval(cur: dict | None = None) -> str:
    v = _prd_deploy_field("cloud_ready_interval_seconds", cur)
    return v if v.isdigit() else "15"


# ★ 动态兜底（`FALLBACK_DEFAULT` 只能放静态字面量，这里放"要算一下才知道"的）。
#   在 baseline 回落之后、静态默认之前生效。
# ⛔ `TARGET_VERSION` **刻意不在本表内**（autopilot 语境下）：`current-version` 的定义是
#    「`phase_beta_done_at` 非空且 `internal_released_at` 为空」= **Phase 2 的准发布版**，
#    那是 `PRE_RELEASE_VERSION` 的定义、不是 TARGET 的。把它当 TARGET 的兜底会造成两个后果：
#    ① 「有 PRE_RELEASE / TARGET=null → 仅跑 Phase 2」这一行决策矩阵**结构上不可达** ——
#       而"上一版开发完等准发布、产品还没提新 PRD"正是 7×24 稳态里最常见的局面；
#       实际命中的是「TARGET == PRE_RELEASE → 数据冲突」→ 3 tick 后前置熔断冻结，
#       #4 通知指引"人工 --reset-baseline 重建状态机"，而状态机根本没坏。
#    ② 0.3.4 末尾那道「TARGET_VERSION 落盘失败 → 中止本 tick」自检因回落恒非空而不可触发。
#    测试链路要的确实是 current-version，那条由 `BASELINE_FALLBACK_BY_COMMAND["aiauto-test"]`
#    在**更早的 baseline 回落层**单独供给，不受本表影响。
DYNAMIC_FALLBACK = {
    "DEPLOY_MODE": _prd_deploy_mode,
    "CLOUD_READY_URL": _cloud_ready_url,
    "CICD_PIPELINE_BOUND": _cicd_pipeline_bound,
    "NOTIFY_ENABLED": _notify_enabled,
    "CLOUD_READY_TIMEOUT": _cloud_ready_timeout,
    "CLOUD_READY_INTERVAL": _cloud_ready_interval,
}


# ★ 值域归一：baseline 里若干开关存的是 **JSON 布尔**（`"notify_enabled": true`），
# 而下游消费方要的是 **0/1**（`autopilot-ceremony-gate.py` 声明 `--notify type=int, choices=(0,1)`）。
# 不归一的后果是**确定性崩溃**而非降级：`--notify true` 直接让 argparse 报
# `invalid int value: 'true'` → 收尾门非零 → bump dev_fail_streak → **3 tick 后冻结并写
# `freeze_reason=handoff-exhausted`（理由写成"结构性不可自愈"，与真因完全无关）**。
# 命中面 = 任何启用了里程碑通知的项目，即文档推荐的标准 7×24 配置。
# 对照：`hooks/autopilot-stop-guard.py` 传的是 `"1" if notify_on else "0"`——同一字段只允许一套取值域。
_BOOLEAN_FLAGS = {"NOTIFY_ENABLED", "LOOP_UNATTENDED"}
_TRUE_WORDS = {"true", "yes", "on", "1"}
_FALSE_WORDS = {"false", "no", "off", "0", "null", "none"}


def _normalize_flag(name: str, val: str) -> str:
    """把布尔类开关的取值归一为 `0`/`1`；非布尔类原样返回。无法识别的值保持原样（不臆造）。"""
    if name not in _BOOLEAN_FLAGS:
        return val
    v = (val or "").strip().lower()
    if v in _TRUE_WORDS:
        return "1"
    if v in _FALSE_WORDS:
        return "0"
    return val


# ★ 按命令覆盖 baseline 回落源。**默认表是以 autopilot 为主写的**，直接共享给测试链路会串版本。
#   `TARGET_VERSION` 的默认回落是 `autopilot.target_version` = **autopilot 正在开发的版本**；
#   而测试链路测的是「当前待测版本」（`baseline_edit.py current-version`）。标准同 tick 形态
#   （Phase 2 归档上版 + Phase 3 开发下版）里两者**必然不同**，于是 aiauto-test 的
#   Phase 0.0.5/0.0.6/0.0.7 会对着**下一版**去拼 `docs/testing/{V}/研发自测` —— 恒不命中，
#   无人值守据此按 `testplan-incomplete` 冻结，而研发自测其实好端端躺在被测版本目录里。
#   连带 `testplan_deploy_url` / `driver_actual_pending` 也写进错版本，反失真门 3i 恒 DEGRADE。
#   ⚠️ 分片里那句 `: "${TARGET_VERSION:=…}"` 兜不住：`--shell` 已把它填成非空，`:=` 整段失效；
#   `--target` 同样被遮蔽。故必须在**供给侧**按命令分流，而不是让分片补救。
BASELINE_FALLBACK_BY_COMMAND = {
    "aiauto-test": {
        "TARGET_VERSION": ("current-version", ""),
        # ★★ 两条 loop 的 tick 级信号必须**按链路分键**，⛔ 不能共用一个根键。
        #   两条 loop 的周期不同（10m / 5m），autopilot 的一个 tick 内必然穿插 1~2 个测试 tick。
        #   共用根键时：用户手工跑一次交互式 `/sprint-aiauto-test`（不带 --unattended）
        #   就把该键写成 0，autopilot 后续分片读回 0 → **在无人值守 tick 内退化为交互式**
        #   → 命中 AskUserQuestion → 挂死，且每个 tick 重犯（无人可答、无人知道）。
        #   `wake_source` 同理：一条链路的"有没有人叫我"不能替另一条链路回答。
        "LOOP_UNATTENDED": ("root", "aiauto.loop_unattended_this_tick"),
        "HAS_WAKE_SOURCE": ("root", "aiauto.wake_source_this_tick"),
    },
}


def _baseline_fallback(name: str, ver: str, command: str = "autopilot") -> str:
    spec = (BASELINE_FALLBACK_BY_COMMAND.get(command) or {}).get(name) \
        or BASELINE_FALLBACK.get(name)
    if not spec:
        return ""
    if spec[0] == "current-version":
        return (_be(["current-version"]).stdout or "").strip()
    scope, key = spec
    if scope == "version":
        if not ver:
            return ""
        r = _be(["--version", ver, "get", key, "--default", ""])
    else:
        r = _be(["get", key, "--default", ""])
    return _normalize_flag(name, (r.stdout or "").strip())


def cmd_shell(a) -> int:
    """输出可 `eval` 的赋值行：分片里只需 `eval "$(… --shell)"` 一行即可拿到全部 tick 变量。

    未落盘的变量一律输出**空串赋值**而非留空——留空会让下游 `${VAR:-默认}` 悄悄落默认值，
    赋空串则至少让 `[ -z "$VAR" ]` 这类判据能显式识别"没取到"。
    """
    # ★ 顺手确保运行时产物目录存在（本脚本在几乎每个 tick 的第一行被 eval，是最稳的兜底点）。
    #   ⛔ 为什么需要：追加写日志的写方通常只 `open(path, "a")`、不建父目录；
    #   目录不在时写失败只打一行 WARN、业务写照常继续 —— 记录**静默丢失**。
    #   落点从仓库根挪进 `memory/.aidp/` 之后，「目录存在」就得由我们保证。
    #   失败不抛：这行只是兜底，绝不能因为它让整个 tick 起不来。
    try:
        import aidp_paths
        aidp_paths.ensure_runtime_dir(".")
    except Exception:
        pass
    cur = _get_tick(getattr(a, "command", "autopilot"))
    ver = _scope_version(cur, getattr(a, "command", "autopilot")) if any(
        cur.get(v, "") == "" and BASELINE_FALLBACK.get(v, ("", ""))[0] == "version"
        for v in ALL_VARS
    ) else ""   # 只在真需要时查一次版本号，避免每个变量各 shell out 一遍
    out = {}
    for v in ALL_VARS:
        val = str(cur.get(v, ""))
        if val == "" and v in BASELINE_FALLBACK:
            val = _baseline_fallback(v, ver, getattr(a, "command", "autopilot"))
        # ★ 动态兜底：必须在 baseline 回落【之后】、静态默认【之前】——顺序即语义。
        #   ⛔ 这一档曾经【定义了却没接进来】，是纯死代码：DEPLOY_MODE / TARGET_VERSION
        #   于是恒取空串，连锁三处静默失效——① phase-3-8 的 WILL_BROWSER_TEST 恒 0，
        #   云端项目被当成静态-only 就地 finalize，真实浏览器测试结论此后撞上「报告不可变铁律」
        #   永远进不了报告；② phase-3-5 的 cloud 分支恒假，断点续跑整段跳过 CICD 触发/监听/探针；
        #   ③ ceremony-gate 自算期望通知集永不含 #1d 却多要一张 #3。
        #   `DEPLOY_MODE` 的 baseline 真源只有 sprint-batch Step 6 会写，而 autopilot 链恒传
        #   `--skip-aiauto-test` 使 Step 6 整段跳过 → **该键在 autopilot 链内从来没有写入者**，
        #   本档就是它唯一的供给来源。删这段 = 恢复上述三处静默失效。
        if val == "" and v in DYNAMIC_FALLBACK:
            try:
                # ★ 传入已算出的 out：DEPLOY_MODE 的兜底必须知道**本轮目标版本**，
                #   否则会取到仓库里另一个版本的 PRD 声明（见 _prd_deploy_mode 的 ⚠️ 段）。
                val = str(DYNAMIC_FALLBACK[v](out) or "")
            except Exception:
                val = ""      # 兜底求值失败不得让整条 --shell 崩掉，退回静态默认
        if val == "":
            val = FALLBACK_DEFAULT.get(v, "")
        out[v] = val
    # 推导型放在最后：依赖的变量此时已完成落盘值 + baseline 回落
    for v, (dep, fn) in DERIVED_FROM.items():
        if not out.get(v):
            out[v] = fn(out.get(dep, ""))
    # ★ 显式关断旗标覆盖一切来源（最后一步，压过落盘值/baseline/默认）。
    #   `--no-notify` 若只被解析、无生效路径，用户以为关了通知，实际照发；而若渠道恰好不可用，
    #   收尾门仍按 --notify 1 索要通知台账 → 恒 FAIL → 3 tick 冻结。关断语义必须在此兜死，不能靠分片散文。
    #   同理：配置侧 `notify.enabled=false` / 无渠道时，baseline 里残留的 notify_enabled=1 不得生效。
    if str(out.get("NO_NOTIFY", "")) == "1" or _notify_enabled(out) == "0":
        out["NOTIFY_ENABLED"] = "0"
    for v in sorted(out):
        print(f"{v}={shlex.quote(out[v])}")
    return 0


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="autopilot/aiauto-test 本 tick 变量解析·落盘·读回")
    ap.add_argument("--shell", action="store_true", help="输出可 eval 的赋值行（读回）")
    ap.add_argument("--command", default="autopilot", choices=sorted(BOOL_FLAGS))
    sub = ap.add_subparsers(dest="op")

    # ★ `--command` 在父子两层都挂：分片里写 `... parse --command autopilot` 是最自然的语序，
    #   只挂父层会因 argparse 的"子命令之后的参数归子解析器"而报 unrecognized。
    #   子层用 SUPPRESS 默认值，未显式传时不覆盖父层已解析的值。
    def _with_command(p_):
        p_.add_argument("--command", choices=sorted(BOOL_FLAGS), default=argparse.SUPPRESS)
        return p_

    p = _with_command(sub.add_parser("parse", help="解析 $ARGUMENTS → 整段重写本 tick 变量"))
    # ⛔ `nargs="?"` 不可省：`$ARGUMENTS` 常常是**单个以 `--` 开头的 token**（`--unattended` /
    #    `--once` / `--skip-dev`），此时 argparse 会把它当成"下一个选项"而非本选项的值，
    #    报 `expected one argument` 并 **exit 2**——而那正是文档钉死的 7×24 标准挂法
    #    `/loop 10m /sprint-autopilot --unattended`。崩在 argparse 层意味着 cmd_parse 一行没跑，
    #    「整段重写、不残留上一 tick」的承诺当场失效：上一 tick 的 SKIP_DEV=1 会继续生效，
    #    后续每个无人值守 tick 静默走 test-only、开发永不发生。
    #    实测：'--unattended' → rc=2；'--skip-dev --unattended'（含空格）→ rc=0，故此前从未被发现。
    p.add_argument("--arguments", default="", help="本次调用的原始参数串（值常以 -- 开头，见 _normalize_argv）")

    s = _with_command(sub.add_parser("set", help="落盘一个派生变量"))
    s.add_argument("name")
    s.add_argument("value")

    _with_command(sub.add_parser("list", help="列出已登记的变量名（供排查拼写）"))

    a = ap.parse_args(_normalize_argv(argv))
    if a.shell and not a.op:
        return cmd_shell(a)
    if a.op == "parse":
        return cmd_parse(a)
    if a.op == "set":
        if not _NAME_RE.match(a.name):
            print("变量名须为大写下划线形式", file=sys.stderr)
            return 2
        return cmd_set(a)
    if a.op == "list":
        print("\n".join(ALL_VARS))
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
