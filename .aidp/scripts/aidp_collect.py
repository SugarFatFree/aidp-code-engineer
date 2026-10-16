#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采集量自证（collection self-evidence）—— 机器门的「我到底看了多少东西」。

## 为什么必须有

约定 35 要求「静态检查在被当作判据之前先做一次阳性对照」，但那是**人的纪律**：
要有人记得去做。本模块是**机器的**那一半，强度完全不同。

机器门的失效形态与通过**同形**：两者都是「没有告警」。下游已累计实证 ≥4 次——

  · 规划审计 I-05：表 A/B/D 列名偏离 → 三道门各自以「未发现该表」exit 0，
    于是「覆盖率 100%」这个结论**零机器佐证**；
  · `requirement_query.py supersessions` 返回「看起来很完整的空数组」，
    实际是 16 个版本都缺 `98_*.json`；
  · `strip_comments.py` 自报「142 个文件读不出」，却仍然照常输出结果；
  · 目标目录不存在 → 静默 exit 0。

共同点：**扫到 0 个东西，和扫完一切都合格，在退出码上一模一样。**

## 契约

每个机器门的 `--json` 输出必须含 `collected`：

    "collected": {"items": N, "files_read": N, "files_failed": N, "targets": N}

并据 `is_starved()` 判定：**采集量为 0 或有读取失败 ⇒ 退出码非 0**，
⛔ 不许打印「通过」。「没有可检查的东西」是一个需要人看一眼的结论，
不是一个可以静默吞掉的结论。

## 用法

    from aidp_collect import Collected

    col = Collected()
    for p in paths:
        col.target()
        try:
            text = open(p, encoding="utf-8").read()
        except OSError:
            col.fail(p); continue
        col.read()
        col.add(len(findings_in(text)))

    payload = {"findings": [...], **col.as_json()}
    return col.exit_code(bool(findings))

**合法的「本项目不适用」**走 `col.not_applicable("<理由>")`：它把采集量为 0
标注成**刻意的**，退出码 0，但理由会出现在 JSON 与摘要里 —— 与「没扫到」区分开。
⛔ 理由留空等于把缺口藏起来，`not_applicable("")` 直接抛错。
"""


class Collected:
    """一次检查运行的采集量账本。"""

    __slots__ = ("items", "files_read", "files_failed", "targets",
                 "failed_paths", "_na_reason")

    def __init__(self):
        self.items = 0
        self.files_read = 0
        self.files_failed = 0
        self.targets = 0
        self.failed_paths = []
        self._na_reason = ""

    # ── 计数 ──
    def target(self, n=1):
        """登记「本该看」的目标数（文件 / 表 / 条目 …）。"""
        self.targets += n
        return self

    def read(self, n=1):
        self.files_read += n
        return self

    def fail(self, path="", n=1):
        self.files_failed += n
        if path:
            self.failed_paths.append(str(path))
        return self

    def add(self, n=1):
        """登记实际看进去的条目数（行 / 字段 / 记录 …）。"""
        self.items += n
        return self

    # ── 结论 ──
    def not_applicable(self, reason):
        """本项目确实不适用（⛔ 理由必填）。采集量为 0 由此变成**刻意的**。"""
        reason = (reason or "").strip()
        if not reason:
            raise ValueError("not_applicable 必须写明理由 —— 留空等于把覆盖缺口藏起来")
        self._na_reason = reason
        return self

    @property
    def not_applicable_reason(self):
        return self._na_reason

    def is_starved(self):
        """采集量异常 = 该结论**不构成通过**。"""
        if self._na_reason:
            return False                       # 明示不适用，不算饿死
        return self.targets == 0 and self.files_read == 0 and self.items == 0 \
            or self.files_failed > 0

    def starved_reason(self):
        if not self.is_starved():
            return ""
        if self.files_failed:
            return ("有 %d 个目标读取失败（%s）—— 读不到的部分**未经检查**，"
                    "本次结果不构成通过"
                    % (self.files_failed, ", ".join(self.failed_paths[:3]) or "未记录路径"))
        return ("采集量为 0：没有扫到任何目标 —— 「没问题」与「根本没跑」在此同形，"
                "本次结果不构成通过。确属不适用请走 not_applicable(<理由>)")

    def as_json(self):
        out = {"collected": {
            "targets": self.targets,
            "files_read": self.files_read,
            "files_failed": self.files_failed,
            "items": self.items,
        }, "starved": self.is_starved()}
        if self.failed_paths:
            out["collected"]["failed_paths"] = self.failed_paths[:20]
        if self._na_reason:
            out["not_applicable"] = self._na_reason
        if self.is_starved():
            out["starved_reason"] = self.starved_reason()
        return out

    def exit_code(self, has_findings):
        """0 = 干净且采集量正常；1 = 有发现**或**采集量异常。"""
        return 1 if (has_findings or self.is_starved()) else 0

    def summary(self):
        if self._na_reason:
            return "[不适用] %s" % self._na_reason
        return ("采集：目标 %d / 读取成功 %d / 读取失败 %d / 条目 %d"
                % (self.targets, self.files_read, self.files_failed, self.items))


# 既有机器门的常见字段名 —— `from_result()` 据此派生采集量，
# 让它们接入契约时只需两行，不必改写各自的扫描循环。
_TARGET_KEYS = ("files", "scanned", "scanned_files", "targets", "file_count", "blocks")
_ITEM_KEYS = ("checked", "items", "entries", "total", "candidates")


def from_result(res, targets=None, items=None, na=None):
    """从既有 `run()` 结果字典派生 `Collected`。

    映射规则：
      · `na` 给出非空字符串 → 明示不适用（调用方自己判断「本轮确实没东西可查」）；
      · `applicable is False` + 有 `reason`  → 明示不适用（退出码不变）；
      · `applicable is False` + **无** reason → 判饿死（⛔ 不写理由的跳过就是藏缺口）；
      · 否则取 `targets`/`items` 显式值，缺省才回落到通用字段名。

    ⛔ **`targets` / `items` 优先显式传**：通用字段名只是便利，靠猜字段名映射
      会在某个脚本上悄悄映成 0，于是「采集量自证」自己变成一条假告警 ——
      那会让这套契约很快被当噪声关掉。
    """
    col = Collected()
    if not isinstance(res, dict):
        return col
    if isinstance(na, str) and na.strip():
        return col.not_applicable(na)
    if res.get("applicable") is False:
        reason = str(res.get("reason") or res.get("skip_kind") or "").strip()
        if reason:
            return col.not_applicable(reason)
        return col          # 无理由 → 采集量 0 → is_starved()，让它出声
    if targets is None:
        targets = next((int(res[k]) for k in _TARGET_KEYS
                        if isinstance(res.get(k), int)), 0)
    if items is None:
        items = next((int(res[k]) for k in _ITEM_KEYS
                      if isinstance(res.get(k), int)), 0)
    col.target(int(targets)).read(int(targets)).add(int(items))
    return col

# ───────────────────── 外部（上游 SKILL）机器门的适配 ─────────────────────

# 上游 SKILL 的脚本**我们改不了**（约定 16：vendored、只读），而它们里有若干条
# 「什么都没扫到 → 打印 `passed:true, skipped:true` → **exit 0**」的路径。
# 这类输出与「全查过且合格」在退出码上完全同形，于是整道门静默放行。
#
# 实证路径：`ux-logic-extractor/scripts/check_req_upstream.py` 在
# `total_sections == 0` 时即如此。而 `total_sections` 取决于它能否认出项目的
# 功规点编号风格 —— 一个用 `REQ-V0.10-A02` 这类带字母序号的项目，
# 它一条都认不出 ⇒ 上游溯源这道门**从接入那天起就没跑过**，且全程零告警。
#
# 既然改不了被调方，就在**调用方**这一侧把「跳过」翻译成「未执行」。
SKIPPED_KEYS = ("skipped", "skip", "not_run")
# 上游表达「我扫到了多少」的常见字段（各 SKILL 命名不统一，故穷举）
EXT_COUNT_KEYS = ("total_sections", "total", "scanned", "scanned_files",
                  "checked", "items", "candidates", "count")


def from_external_gate(payload, count_keys=None):
    """把**上游机器门**的 `--json` 输出翻译成 `Collected`。

    判定：
      · `skipped`（或同义键）为真 ⇒ **饿死**（⛔ 不是通过）——
        「跳过」在上游的语义是「没东西可查」，而「为什么没东西可查」
        恰恰是最需要人看一眼的那个问题（通常是编号风格对不上、目录名偏了）。
      · 否则取计数字段；全为 0 同样饿死。

    ⛔ 不要为了「让它绿」而在这里给跳过开后门：那等于把一道门删掉却留着它的名字。
      确实不适用时，由**调用方**显式 `not_applicable("<理由>")` 表态并留痕。
    """
    col = Collected()
    if not isinstance(payload, dict):
        return col
    for k in SKIPPED_KEYS:
        if payload.get(k):
            return col          # 采集量 0 ⇒ is_starved() ⇒ 调用方必须出声
    keys = count_keys or EXT_COUNT_KEYS
    n = next((int(payload[k]) for k in keys if isinstance(payload.get(k), int)), 0)
    col.target(n).read(n).add(n)
    return col
