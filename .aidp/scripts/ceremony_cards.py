#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""里程碑卡片矩阵 —— **机器可读的单一数据源**。

## 为什么必须只有一份

`{{AIDP_HOME}}/flows/sprint-autopilot/phase-0-5.md` 的「ENTRY_MODE × 应发卡集矩阵」与收尾门的期望集此前是**两处各自实现**：
文档里是一张给人看的表，门里是一段自己推的代码。该文件自己都写着「本矩阵与收尾门的
EXPECT_CARDS 必须逐条同源」—— 一条必须靠人去维持的「同源」，就是迟早会漂的两份。

实测已漂：`incremental` 行在矩阵里含 `#D/#R/#F/#3` 条件卡、而门自算的应产清单只有
`#0/#1b/#1c/#1d`。本轮因为「期望少于实发」不报错而没暴露；反向偏差（期望多于实发）
按该文件自己的说法会造成「台账恒缺 → 每 tick FAIL → dev_fail_streak 冻结版本」。

本模块即那**一份**：门从这里取期望集，文档表由 `test_ceremony_matrix.py` 对着它校验。

## 两类卡，别混为一谈

  · **应产卡（expected）** —— 本轮**必然**要发的，收尾门逐项核验「台账里有没有」。
  · **条件卡（conditional）** —— 要不要发取决于运行期事实（有没有部署 / 有没有浏览器
    测试 / 有没有失败），门**不索要**它们。⛔ 把条件卡放进应产集 = 台账恒缺 = 版本被冻死。
"""

# 节点 → 一句话用途（供告警文案与文档校验共用）
CARD_PURPOSE = {
    "#0": "版本对识别 / 本轮起测",
    "#0a": "通道就绪（仅 notify.channel_ready_card=true 才发）",
    "#1": "版本规划开始（仅本轮真跑规划）",
    "#1b": "版本规划完成",
    "#1c": "开发阶段开始",
    "#1d": "部署完成（开发链路收尾 + 测试链路交接）",
    "#1e": "测试链路已接手（交接心跳）",
    "#2": "Sprint 关闭",
    "#3": "AI执行报告（由 build 关闭方在 #F 之后发）",
    "#4": "失败冻结告警",
    "#D": "部署探测到 / 开始测试",
    "#R": "复测轮开始",
    "#F": "最终测试结论",
    "#G": "护栏告警",
    "#pre-start": "准发布对时开始",
    "#pre-done": "准发布对时完成",
}

# ★ 各入口的**无条件应产卡**（收尾门逐项核验）
_ALWAYS = {
    "full": ("#0", "#1b", "#1c"),
    "incremental": ("#0", "#1b", "#1c"),
    "test-only": (),          # autopilot 不发开发链路卡，全归测试链路
}

# ★ **条件卡**：由运行期事实决定，⛔ 门不索要
CONDITIONAL = ("#0a", "#1", "#1e", "#D", "#R", "#F", "#G", "#4",
               "#pre-start", "#pre-done")

# ★ 各入口**明确不发**的卡（文档表「明确不发」列的机器形态）
NEVER = {
    "full": ("#0a",),
    # 增量路径无 Sprint 可关
    "incremental": ("#0a", "#2"),
    "test-only": ("#0", "#1", "#1b", "#1c", "#1d", "#2"),
}

ENTRY_MODES = tuple(_ALWAYS)


def expected_cards(entry_mode, deployed=False):
    """本轮**至少应发**的卡集（收尾门逐项核验的那一份）。

    ⛔ 刻意保守，这是**下限而非上限**：
      · `#1` 不自算 —— 它只有「本轮真跑了规划」才该期望，而门事后无法可靠区分
        「产物是本轮产的」还是「上轮就在」。宁可少期望，也不制造假 FAIL。
      · 条件卡一律不进应产集（见模块 docstring）。
    """
    mode = entry_mode if entry_mode in _ALWAYS else "full"
    cards = list(_ALWAYS[mode])
    if mode == "test-only":
        return cards
    if deployed:
        cards.append("#1d")
    else:
        # 静态-only：没有浏览器测试，autopilot 自己就是 build 关闭方，#3 归它发
        cards.append("#3")
    if mode != "incremental":
        cards.append("#2")
    return cards


# ───────────────────────── 时序校验（A1）─────────────────────────
#
# 收尾门此前只校验卡片**存在**，不校验**按时发**。台账里明明记了 `ts`，却没人用它。
# 实测后果：三张描述不同阶段的卡在**同一秒内**连发（#0 滞后真实事件 4h34m），
# 群里看到的是「一次爆发」而不是进度 —— 卡片的全部设计目的（实时里程碑播报）被摧毁。
#
# 低阻力路径就是「不发 → 等门报 → 批量补发」，而补发一样 PASS。
# 判据所需的时刻**全部已经在盘上**，不需要新增任何记录。

# 节点 → baseline 里「该节点对应的真实事件时刻」取值路径（按序回落，取第一个有值的）
CARD_EVENT_SOURCE = {
    "#0": ("run_state.phase_started_at", "builds[].started_at"),
    "#1b": ("run_state.planning_done_at", "run_state.phase_completed_at"),
    "#1c": ("builds[].started_at",),
    "#1d": ("last_deployed_at", "builds[].deployed_at"),
    "#2": ("run_state.sprint_closed_at",),
    "#3": ("builds[].ai_report_finalized_at", "builds[].finalized_at"),
    "#F": ("builds[].ai_report_finalized_at",),
}

LAG_IMPORTANT_SECONDS = 10 * 60       # 滞后超 10 分钟 → Important
LAG_CRITICAL_SECONDS = 60 * 60        # 滞后超 1 小时 → Critical
BURST_WINDOW_SECONDS = 5              # 同 version 下不同节点 5s 内连发 = 批量补发


def classify_lag(seconds):
    """滞后秒数 → 严重度（None = 正常）。"""
    if seconds is None or seconds < LAG_IMPORTANT_SECONDS:
        return None
    return "Critical" if seconds >= LAG_CRITICAL_SECONDS else "Important"


def detect_burst(entries):
    """检出「批量补发」：按 ts 排序后，相邻两张**不同节点**的卡间隔 < 5s。

    入参 = `[{"node": ..., "ts": <epoch 秒>}, ...]`（调用方负责把 ISO 转 epoch）。
    返回 `[{"prev": 节点, "node": 节点, "gap": 秒}]`。

    ⛔ **同一节点**重复发不算（重试/补发同一张是另一回事）；
      只有「描述不同阶段的卡挤在同一瞬间」才是本判据要抓的形态。
    """
    rows = sorted((e for e in entries if e.get("ts") is not None),
                  key=lambda e: e["ts"])
    out = []
    for prev, cur in zip(rows, rows[1:]):
        if prev.get("node") == cur.get("node"):
            continue
        gap = cur["ts"] - prev["ts"]
        if gap < BURST_WINDOW_SECONDS:
            out.append({"prev": prev.get("node"), "node": cur.get("node"), "gap": gap})
    return out
