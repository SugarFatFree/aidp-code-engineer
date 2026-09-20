#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baseline_edit.py — autopilot baseline 的**加锁读改写**编辑器（并发安全的单一写入口）。

## 为什么需要本脚本

`memory/.sprint-autopilot-baseline.json` 被**两条 `/loop` 并发写**：
  - 开发链路 `/loop 10m /sprint-autopilot` —— 写 run_state / 部署 / build / 决策字段；
  - 测试链路 `/loop 5m /sprint-aiauto-test` —— 写心跳 / 测试结果 / 冻结字段。

此前 flow 分片里散落着几十处 `jq '…' f > tmp && mv tmp f` 的裸 read-modify-write：
**只原子、不加锁**。两条 loop 的长 tick 交叉时会丢更新——典型事故是 aiauto-test 刚写的
`ai_report_finalized` 被 autopilot 的 run_state 整体回写覆盖，导致重复 finalize / 收尾门判据错乱。
`emit-report.py::record_baseline` 已有正确范式（flock + **锁内重读** + `os.replace`），
本脚本把它抽成通用工具，让所有写点共用同一把锁。

**铁律：flow / 命令端一律通过本脚本写 baseline，不要再写裸 `jq … > tmp && mv`。**
（只读 `jq -r` 查询不受限制。）

## 路径语法

点号分段；**含点的键必须加双引号**（版本号如 `V0.1.0` 天然含点）：

    versions."V0.1.0".needs_human
    report_deliveries."1001".exec_report.at
    aiauto_test_heartbeat_at

便捷写法：`--version V0.1.0` 会给后续所有相对路径自动加 `versions."V0.1.0".` 前缀。

**★ 写 build 记录必须用 `--build`，不能用点号路径**：`builds` 是**对象数组**（每条
`{build, status, pass_rate, …}`）、不是以 build 号作键的字典，点号语法压根寻址不到它。
硬写 `builds[V0.4.0_build1001].x` 的后果是**静默造出畸形嵌套键**（`builds[V0 → 4 →
0_build1001]`），真实字段一个没写进去 —— 下游 baseline 里已出现过同源畸形键：

    python3 $B --version V0.4.0 --build V0.4.0_build1001 set driver_actual cli
    python3 $B --version V0.4.0 --build V0.4.0_build1001 get pass_rate

build 记录由 autopilot Phase 3.1.5 铸造；`--build` **只寻址、不代建**，指向不存在的 build
即 `exit 2`（与"路径语法错=1"区分，让调用方能分辨"路径写错"与"时序不对、build 还没铸出来"）。

## 子命令

    get   <path>                    读；不存在打印 --default（默认空串），exit 0
                                    ★ 主文件取不到且该版本已归档 → 自动回落读
                                      `memory/.aidp-baseline-archive/baseline-<V>.json`
    set   <path> <value> [...]      写；可多组 path/value 交替；值按 JSON 解析，失败则当字符串
    del   <path> [<path> ...]       删键（不存在静默跳过）
    bump  <path> [--by N]           数值自增（缺省视为 0），打印新值
    touch <path> [...]              写当前本地时间 ISO8601（等价 set <path> <now>）
    now                             只打印当前 ISO8601 时间戳（供 shell 复用同一时刻）
    current-version                 解析「当前开发版本」= phase_beta_done_at 非空且 internal_released_at
                                    为空的候选中，**优先取待测的最老一个**（没测过 / 测后又部署过），
                                    全都测过才回到「最新优先」。无候选则打印 --default。
                                    ★ 优先待测是为防「下版一开工就把上版饿死」：上版 aiauto_tested_at
                                    再不刷新 → 准发布收敛门恒不过 → 只能靠 streak 到 12 冻结兜底。
                                    ★ 待测集内 needs_human 未冻结的优先（冻结版每 tick early-exit，
                                      若被选中会永久霸占选版、把后续版本饿死并连坐冻结）；全冻结才回落。
                                    两条 loop 共用此单一信源
    run-state <cur> <next> [sprint]  写版本级 run_state（断点续跑状态机）；配 --summary / --pending

`<value>` 支持哨兵 `@now` → 当前 ISO8601 时间戳。

## 用法示例

    B=.aidp/scripts/baseline_edit.py
    python3 $B touch aiauto_test_heartbeat_at
    python3 $B --version "$V" set needs_human true aiauto_frozen_at @now freeze_reason '"account-missing"'
    python3 $B --version "$V" del needs_human aiauto_frozen_at probe_fail_streak
    N=$(python3 $B --version "$V" bump aiauto_test_unconverged_streak)

## 退出码

  0 成功  ·  1 路径/值语法错  ·  2 IO 错（baseline 不可读写）
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

DEFAULT_BASELINE = os.path.join("memory", ".sprint-autopilot-baseline.json")

# ★ 已发布版本的历史明细归档目录（由 `baseline_archive.py` 写入，本脚本只负责**读回落**）。
#   主文件对已归档版本只留一个「墓碑节点」（KEEP 白名单里的少量标量 + `archived: true`），
#   bulk（`builds[]` / `run_state` / 各类 streak）搬到 `baseline-<V>.json`。
#   ⛔ 少了下面 `get` 的回落，归档就从"瘦身"变成"数据还在但机器读不到"——那比不归档更糟。
ARCHIVE_DIRNAME = ".aidp-baseline-archive"


def archive_file(baseline: str, version: str) -> str:
    return os.path.join(os.path.dirname(baseline) or ".", ARCHIVE_DIRNAME,
                        "baseline-%s.json" % version)


def load_archived_node(baseline: str, version: str):
    """读回已归档版本的完整节点；文件不存在 / 不可解析 → None。

    ⛔ 只读、不加锁：归档文件一经写出即不再变更（版本已发布），没有并发写方。
    """
    try:
        with open(archive_file(baseline, version), encoding="utf-8") as f:
            data = json.load(f) or {}
    except (OSError, ValueError):
        return None
    node = data.get("node")
    return node if isinstance(node, dict) else None


def warn_if_archived(data: dict, version: str, baseline: str) -> None:
    """对**已归档版本**的写入出声告警（不阻断）。

    写一个已发布版本通常意味着上游判据串了版本；即便真要写，也只会落在墓碑节点上、
    与归档文件里的历史明细分家。静默放过会让这种不一致长期存在且无人察觉。
    """
    node = ((data.get("versions") or {}).get(version)) or {}
    if isinstance(node, dict) and node.get("archived"):
        sys.stderr.write(
            "⚠️ [baseline_edit] %s 已归档（历史明细在 %s）——本次写入只落在墓碑节点上，"
            "请确认版本号没串\n" % (version, archive_file(baseline, version)))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


VERSIONISH_RE = re.compile(r"V\d+$")

# 「本阶段还没干完」的**进行时**自述。用于 run-state 拒写"自述未完成却同时宣告完成"。
# ★ 只收进行时信号，不收「未完成 / pending」等否定句里也会出现的词（见 run-state 处注释）。
_UNFINISHED_RE = re.compile(
    r"(?:执行|运行|进行|生成|处理|派发|构建|规划|审计|分析|排队|等待)中"
    r"|已派发|等待回传|待回传|等待子\s*Agent|in\s+progress")


def _detect_split_version(segs: list):
    """检出**被点号切碎的版本号 / build 号**（写路径时漏加引号）。命中返回起始下标，否则 None。

    判据：某段以 `V<数字>` 结尾，且**紧邻下一段以数字开头** —— 这是 `V0.4.0` / `V0.4.0_build1001`
    被按 `.` 切开后必然留下的形状（`['V0','4','0']` / `['V0','4','0_build1001']`）。

    ## 为什么必须拦（这是本文件最危险的静默失败）

    漏引号不会报错、不会写不进去，而是**在旁边造出一棵畸形的嵌套树**：

        versions.V0.4.0.state = "S0"
        → {"versions": {"V0": {"4": {"0": {"state": "S0"}}}}}      ← 真正的 V0.4.0 节点一字未动

    调用方 `set` 拿到 rc=0、`get` 读回空、字段"就是没生效"，而多数写点还带 `|| true`
    把一切咽掉。真实后果：实际项目的 baseline 里长期躺着 `"V0":{"4":{"0":…}}`，
    V0.4.0 的 `state` 从未写入、S 状态机对该版本恒读空。
    """
    for i in range(len(segs) - 1):
        if VERSIONISH_RE.search(segs[i]) and segs[i + 1][:1].isdigit():
            return i
    return None


def _suggest_quoted(segs: list, i: int) -> str:
    """按检出位置拼一条"应该怎么写"的建议路径。"""
    j = i + 1
    while j < len(segs) and segs[j][:1].isdigit():
        j += 1
    merged = ".".join(segs[i:j])
    if "[" in merged:          # builds[V0.4.0_build1001] 这类 —— 点号路径根本寻址不到对象数组
        return "改用 --build 寻址：--version <V> --build <build号> set <字段> <值>"
    return "应写成：" + ".".join(segs[:i] + ['"%s"' % merged] + segs[j:])


def parse_path(path: str) -> list:
    """把 `a."B.c".d` 解析成 ['a', 'B.c', 'd']；未闭合引号 / 切碎的版本号 → ValueError。"""
    segs, buf, in_q, i = [], "", False, 0
    while i < len(path):
        ch = path[i]
        if ch == '"':
            in_q = not in_q
        elif ch == "." and not in_q:
            segs.append(buf)
            buf = ""
        else:
            buf += ch
        i += 1
    if in_q:
        raise ValueError(f"路径引号未闭合: {path}")
    segs.append(buf)
    if any(s == "" for s in segs):
        raise ValueError(f"路径含空段: {path}")
    hit = _detect_split_version(segs)
    if hit is not None:
        raise ValueError(
            f"路径里的版本号/build号未加引号，会被按 `.` 切碎并静默造出畸形嵌套键: {path}\n"
            f"    {_suggest_quoted(segs, hit)}\n"
            f"    （版本号天然含点；`--version <V>` 前缀写法已自动处理，相对路径无需再写版本号）")
    return segs


def parse_value(raw: str):
    if raw == "@now":
        return now_iso()
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw  # 裸字符串（如 V0.1.0 / account-missing）


def resolve_build_idx(data: dict, version: str, build_id: str):
    """`--build <id>` → `builds` 列表下标；找不到返回 `(None, 现有 build id 列表)`。

    `builds` 是**对象数组**（每条 `{build, status, …}`），不是以 build 号作键的字典 ——
    故无法用点号路径寻址，必须先按 `build` 字段线性查出下标。
    """
    blds = (((data.get("versions") or {}).get(version) or {}).get("builds")) or []
    ids = [b.get("build") for b in blds if isinstance(b, dict)]
    for i, b in enumerate(blds):
        if isinstance(b, dict) and b.get("build") == build_id:
            return i, ids
    return None, ids


def dig(data: dict, segs: list):
    cur = data
    for s in segs:
        if isinstance(s, int):                       # 列表下标（builds[i]）
            if not isinstance(cur, list) or not -len(cur) <= s < len(cur):
                return None, False
        elif not isinstance(cur, dict) or s not in cur:
            return None, False
        cur = cur[s]
    return cur, True


def plant(data: dict, segs: list, value):
    cur = data
    for s in segs[:-1]:
        if isinstance(s, int):
            # ⛔ 列表下标只**走进已存在**的元素，绝不自动补一条：新建 build 记录是
            #    autopilot Phase 3.1.5 的职责，这里静默补会把"时序颠倒（还没铸 build 就写字段）"
            #    这类 bug 掩盖成一条凭空出现、缺 started_at 的残缺 build。
            cur = cur[s]
            continue
        nxt = cur.get(s)
        # ★ 已是 list 时不得当成"非 dict"覆盖掉 —— 否则一次 set 就把整个 builds[] 抹成 {}
        if not isinstance(nxt, (dict, list)):
            nxt = {}
            cur[s] = nxt
        cur = nxt
    cur[segs[-1]] = value


def prune(data: dict, segs: list) -> bool:
    cur = data
    for s in segs[:-1]:
        if isinstance(s, int):
            if not isinstance(cur, list) or not -len(cur) <= s < len(cur):
                return False
            cur = cur[s]
            continue
        nxt = cur.get(s) if isinstance(cur, dict) else None
        if not isinstance(nxt, (dict, list)):
            return False
        cur = nxt
    if isinstance(cur, dict) and segs[-1] in cur:
        del cur[segs[-1]]
        return True
    return False


def _to_epoch(ts) -> float:
    """ISO8601 → epoch 秒；不可解析返回 0。

    ⚠️ 时间戳一律走 epoch 比较，**不要用字符串比大小**——`+08:00` 与 `Z` 两种写法混排时
    字典序与真实先后不一致（真实事故来源）。
    """
    if not ts:
        return 0.0
    try:
        from datetime import datetime
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return 0.0


# ── 锁文件路径：**全仓单一信源** ────────────────────────────────────────────────
# ⛔ 此前 `<文件> + ".lock"` 这个约定在仓里有**三处彼此独立的实现**
#   （`baseline_edit.py` / `autopilot-ceremony-gate.py` / `emit-report.py`），
#   而后两者锁的正是**同一个 baseline**。任何一处改了路径而另两处没改 ⇒
#   两把锁互不排斥、**互斥当场归零**，失效形态是 80KB 共享状态文件的**静默丢更新** ——
#   那正是 `LockedBaseline` 被造出来要消灭的 bug。故收敛到这一个函数，三处一律调它。
#
# 锁文件收进隐藏子目录，不再与数据文件同级堆在 `memory/` 下（0 字节却出现在 `ls -la` 里）。
# ⚠️ 换路径的**唯一**风险是"新旧代码同时在跑、各锁各的"。本仓三个调用方都经
#   `ensure_root_scripts` **非版本门控**通道下发（字节不同即覆盖），三者恒同步更新；
#   且每次持锁只有毫秒级（读-改-原子写回即释放），窗口可忽略。
# 锁与其余本地运行时产物同住 `memory/.aidp/`（`RUNTIME_DIRNAME`/`locks`），
# 使 memory/ 下只剩「一个隐藏运行时目录 + 两份入库文件 + 业务 .md」。
# ⛔ 落点必须**跟着数据文件所在目录走**，不能挪到系统临时目录：那里的路径随
#    TMPDIR / XDG_RUNTIME_DIR 变化，两个进程只要环境不同就各锁各的，
#    互斥当场归零 —— 而「锁没起作用」与「锁正常」在产物上完全同形。
LOCK_DIRNAME = os.path.join(".aidp", "locks")


def lock_path(data_path: str) -> str:
    """数据文件路径 → 它的锁文件路径（⛔ 全仓唯一实现，别再各写各的）。"""
    d = os.path.dirname(os.path.abspath(data_path)) or "."
    return os.path.join(d, LOCK_DIRNAME, os.path.basename(data_path) + ".lock")


class LockedBaseline:
    """with 语句内持排他锁；退出时原子写回。锁内重读，绝不用进入时的旧快照覆盖对方字段。"""

    def __init__(self, path: str, write: bool):
        self.path, self.write = path, write
        self.data, self._lock_f = {}, None

    def __enter__(self):
        if self.write:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            _lp = lock_path(self.path)
            os.makedirs(os.path.dirname(_lp), exist_ok=True)
            self._lock_f = open(_lp, "w")
            try:
                import fcntl

                fcntl.flock(self._lock_f.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                pass  # 非 POSIX / 锁不可用：退化为无锁，仍靠原子替换避免半截写
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f) or {}
        except FileNotFoundError:
            self.data = {}
        except (OSError, ValueError) as e:
            if self._lock_f:
                self._lock_f.close()
            raise SystemExit(f"[baseline_edit] ✗ baseline 不可解析: {self.path} ({e})")
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            if self.write and exc_type is None:
                tmp = self.path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
        finally:
            if self._lock_f:
                self._lock_f.close()
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="autopilot baseline 加锁读改写编辑器")
    ap.add_argument("--baseline", default=DEFAULT_BASELINE, help=f"baseline 路径（默认 {DEFAULT_BASELINE}）")
    ap.add_argument("--version", default="", help='版本号前缀：后续相对路径自动加 versions."<V>."')
    ap.add_argument("--build", default="",
                    help='build 前缀（需配合 --version）：相对路径自动加 versions."<V>".builds[<该 build 的下标>].'
                         '；builds 是对象数组、无法用点号路径寻址，故必须走本 flag')
    ap.add_argument("--default", default="", help="get 未命中时打印的兜底值")
    ap.add_argument("--by", type=int, default=1, help="bump 步长（默认 1）")
    ap.add_argument("--raw", action="store_true", help="get 字符串值不带引号输出（默认即 raw）")
    ap.add_argument("--summary", default="", help="run-state: 本 Phase ≤20 行结论摘要")
    ap.add_argument("--pending", default="", help="run-state: 未完成动作，逗号分隔")
    ap.add_argument(
        "op",
        choices=["get", "set", "del", "bump", "touch", "now", "current-version", "run-state"],
    )
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()

    # ── ⛔ 显式传了 `--version ""` = 上游 shell 变量取空，必须响亮失败 ────────────────
    # argparse 的 default 是空串，区分不了"没传"与"传了空"，故直接看 argv。
    # 为什么必须拦：不拦时 `set`/`get`/`bump`/`del` 会**静默写进 baseline 顶层并返回 0**
    #（只有 `run-state` 校验过），于是"版本号取空"这类 bug 从"响亮失败"退化成"静默污染"——
    # 实测受害面：build 号写到顶层（下游全取不到）、环境熔断计数在顶层累加（阈值永不可达、
    # 冻结不生效）、自动修复闭环的触发信号读顶层恒 false。合法的顶层写法是**根本不传** `--version`。
    if "--version" in sys.argv and not (a.version or "").strip():
        sys.stderr.write(
            "✗ 显式传了 --version 但值为空 —— 上游变量取空了（分片间 shell state 不跨 Bash 调用，"
            "多半是本围栏缺 `eval \"$(autopilot_tick_flags.py --shell)\"`）。\n"
            "  ⛔ 不予静默写入顶层：那会让版本级字段落到错地方且返回 0。\n"
            "  · 要写版本级 → 先取到版本号再传；· 要写顶层 → 根本不要传 --version。\n")
        return 1
    if "--build" in sys.argv and not (a.build or "").strip():
        sys.stderr.write("✗ 显式传了 --build 但值为空 —— 同上，先取到 build 标识再传。\n")
        return 1

    if a.op == "now":
        print(now_iso())
        return 0

    if a.op == "current-version":
        # 「当前开发版本」= 已跑完 autopilot Phase 3（有 phase_beta_done_at）但尚未准发布
        # （internal_released_at 为空）的最近一个版本 —— 正是 AI 自动化测试的目标。
        # ★ 单一信源：`/sprint-aiauto-test` 与 `/sprint-autopilot` 都调本子命令解析，
        #   命令端不要各自内联 jq —— 否则「早期步骤用空的 $TARGET_VERSION 拼路径」这类
        #   时序倒挂会悄悄复发（路径变成 docs/testing//研发自测，恒不命中）。
        with LockedBaseline(a.baseline, write=False) as b:
            versions = (b.data or {}).get("versions") or {}
        cands = [
            (v.get("phase_beta_done_at") or "", k)
            for k, v in versions.items()
            if isinstance(v, dict) and v.get("phase_beta_done_at") and not v.get("internal_released_at")
        ]
        if not cands:
            print(a.default)
            return 0
        # ★ 「最新优先」会饿死上一版：autopilot 每 tick 同时处理「上版准发布 + 下版开发」，
        #   一旦下版写了更新的 phase_beta_done_at，测试链路就永久只测下版 →
        #   上版的 aiauto_tested_at 再也不刷新 → Phase 2 0b 的准发布收敛门恒不通过，
        #   只能靠 prerelease_test_hold_streak 到 12 冻结兜底（≈2 小时空转 + needs_human）。
        #   故先取「候选里【待测】的最老一个」（本轮部署后还没测过、或测过但之后又部署过）；
        #   全都测过了才回到「最新优先」。判据用 epoch 比较，不用字符串（+08:00 与 Z 混排会误判）。
        def _needs_test(k):
            v = versions.get(k) or {}
            tested, deployed = v.get("aiauto_tested_at"), v.get("last_deployed_at")
            if not tested:
                return True                      # 从没测过
            if not deployed:
                return False
            return _to_epoch(tested) < _to_epoch(deployed)   # 测完之后又部署过 → 需重测
        pending = sorted([c for c in cands if _needs_test(c[1])])
        # ★ 冻结版本不得饿死后续版本：`needs_human=true` 的版本每 tick 都会在测试链路冻结门 early-exit，
        #   若它恰好是「最老的待测版本」就会**永久霸占**本子命令的结果——后面的版本一次都测不上；
        #   与此同时它每 tick 回写 `aiauto_blocked_reason`，开发链路读到非空又会把后续版本**一并连坐冻结**
        #   （扣上"测试链路未挂载"的错帽子，而 loop 一直好好挂着）。这是双链路里最隐蔽的一类停摆。
        #   故待测集内**未冻结的优先**；全都冻结了才回落到冻结版本——保证它们的自动解冻判定仍有机会跑到。
        live = [c for c in pending if not (versions.get(c[1]) or {}).get("needs_human")]
        pending = live or pending
        print(pending[0][1] if pending else max(cands)[1])
        return 0

    class BuildNotFound(Exception):
        pass

    def full(p: str, data=None) -> list:
        segs = parse_path(p)
        if not a.version:
            return segs
        if not a.build:
            return ["versions", a.version] + segs
        idx, ids = resolve_build_idx(data or {}, a.version, a.build)
        if idx is None:
            raise BuildNotFound(
                f"版本 {a.version} 下无 build={a.build}（现有：{', '.join(i for i in ids if i) or '无'}）"
                f"；build 记录由 autopilot Phase 3.1.5 铸造，本工具不代建")
        return ["versions", a.version, "builds", idx] + segs

    if a.build and not a.version:
        print("[baseline_edit] ✗ --build 必须配合 --version 使用", file=sys.stderr)
        return 2

    if a.op == "run-state":
        # 写【版本级】run_state —— A3 上下文管理策略的状态机落点，也是断点续跑的唯一依据。
        # 用法：run-state <current_phase> <next_phase> [next_sprint] --summary "…" --pending "a,b"
        # ⚠️ 必须由**每个 Phase 分片末尾**调用。历史上 run_state 只在 invariants 里被"声明"、
        #    10 个执行分片一处都不写 → next_phase 恒空 → tick 中途崩溃后下一 tick 从头全量重推，
        #    "断点续跑"形同虚设。stop-guard 的 yield-tick 豁免也依赖 next_sprint，缺了会误跑收尾门。
        if not a.version or len(a.args) < 2:
            print("[baseline_edit] ✗ run-state 需要 --version 和 <current_phase> <next_phase> [next_sprint]", file=sys.stderr)
            return 1
        rs = {
            "current_phase": a.args[0],
            "next_phase": a.args[1],
            "next_sprint": a.args[2] if len(a.args) > 2 else "",
            "phase_completed_at": now_iso(),
        }
        if a.summary:
            # ⛔⛔ 「阶段完成 = 该阶段的产物与结论都已落盘可校验」，**不是"活已经派出去了"**。
            #    实测事故：21:31:34 派发规划子 Agent → 21:31:41（7 秒后）就写 phase_completed_at
            #    并推进 next_phase，而四类规划文档 21:46 才成文、version-auditor 23:08 才判出
            #    2 项 Critical —— 开发链路早已按"规划已完成"跑掉 3 笔提交，最终「计划验收标准
            #    与已交付代码相反」。规约本身写对了（`phase-3-3.md`「子 Agent **回传后**才写
            #    run_state」），但那是散文、没有任何东西拦得住"明知未完成仍推进"。
            #    本校验把它变成结构级：**摘要自述未完成，就不许同时宣告完成**。
            #    判据取"摘要措辞"而非"耗时"——耗时判据在续跑/缓存路径上会误伤（合法的秒级完成
            #    确实存在），而"执行中/已派发"这类自述是执行体自己写下的、不会假阳性。
            #    ⚠️ 判据只取**进行时**信号（「…中」+ 等待回传类），**刻意不收**「未完成 / pending」
            #       这类**易被否定句翻转**的词——"无未完成动作"「pending_actions 已清空」都是
            #       完全正常的完成摘要，收进来就会把合法推进拦死（假阳性会卡停流水线，比漏判更贵）。
            _hit = _UNFINISHED_RE.findall(a.summary)
            if _hit:
                print(f"[baseline_edit] ✗ 拒写：phase_summary 自述未完成（命中 {'/'.join(_hit)}），"
                      f"不得同时写 phase_completed_at 并推进 next_phase\n"
                      f"    摘要：{a.summary[:120]}\n"
                      f"    阶段完成 = 产物与结论已落盘可校验，不是「活已派出去」。"
                      f"请等子 Agent 回传、产物落盘后再写出口；确需记录中途进度用 --pending。",
                      file=sys.stderr)
                return 1
            rs["phase_summary"] = a.summary
        # ★ pending_actions 必须**无条件**写（空串 → 写空数组），不能用 `if a.pending:` 守卫：
        #   下面 `{**old, **rs}` 是浅合并，键不进 rs 就等于保留旧值 —— 而全部 9 处出口都用
        #   `--pending ""` 表达"本 Phase 已收口、清空未完成动作"。守卫写法让这个清空**从未生效**：
        #   一次 deploy-probe / ceremony-gate / prerelease-hold 就永久粘在 run_state 上，
        #   而 invariants「阶段推进不变式」规定 pending_actions 非空即"本 Phase 未完成"——
        #   于是要么每 tick 重做已完成的动作，要么按字面意思再也推不动。
        rs["pending_actions"] = [x.strip() for x in (a.pending or "").split(",") if x.strip()]
        with LockedBaseline(a.baseline, write=True) as b:
            warn_if_archived(b.data, a.version, a.baseline)
            node = b.data.setdefault("versions", {}).setdefault(a.version, {})
            old = node.get("run_state") if isinstance(node.get("run_state"), dict) else {}
            # ★ 通用 stuck 检测字段由本脚本**自动维护**（调用方不用管）：
            #   同一 current_phase 连续进入则计数累加、首次进入时刻保持不变；换 Phase 即重置。
            #   命令端据此判「同一 Phase 连续进入 ≥8 次且首次进入距今 >2 小时」= 卡死，
            #   补上"既不失败也不推进"这类现有失败计数式熔断覆盖不到的死循环。
            #   ★ 「真的推进了」不止"换 Phase"——`next_sprint` 游标前移同样是推进，也必须重置。
            #     漏这一条会误伤逐 tick 单 Sprint：`current_phase` 恒为 `3.2-dev`，Sprint 数较多、
            #     总耗时超 2 小时的版本会在**正常推进中**被判 stuck-phase 冻结（属交接类、只能人工解冻）。
            #   ★ 本脚本是 phase_enter_count 的**唯一**维护者：命令端 tick 开头不得再 `bump` 同一字段，
            #     否则每 tick 加两次、阈值提前一半到达。
            same_phase = old.get("current_phase") == rs["current_phase"]
            sprint_advanced = (old.get("next_sprint") or "") != (rs.get("next_sprint") or "")
            if same_phase and not sprint_advanced:
                rs["phase_enter_count"] = int(old.get("phase_enter_count") or 1) + 1
                rs["phase_first_entered_at"] = old.get("phase_first_entered_at") or rs["phase_completed_at"]
            else:
                rs["phase_enter_count"] = 1
                rs["phase_first_entered_at"] = rs["phase_completed_at"]
            # 保留历史 phase_summary 之外的自定义字段，只覆盖本次写的键
            node["run_state"] = {**old, **rs}
        print(
            f"[baseline_edit] ✅ run_state → {a.args[0]} ▸ next={a.args[1]} "
            f"sprint={rs['next_sprint'] or '-'} enter#{rs['phase_enter_count']}"
        )
        return 0

    try:
        if a.op == "get":
            if len(a.args) != 1:
                print("[baseline_edit] ✗ get 需要且仅需要 1 个路径", file=sys.stderr)
                return 1
            with LockedBaseline(a.baseline, write=False) as b:
                _bnf = None
                try:
                    val, found = dig(b.data, full(a.args[0], b.data))
                except BuildNotFound as _e:
                    val, found, _bnf = None, False, _e
                # ★ 归档回落：主文件取不到 → 去归档文件读回该版本的历史明细。
                #   `--build` 形态同样覆盖（build 记录正是被搬走的 bulk 大头）。
                #   ⛔ 没有归档文件时必须把 BuildNotFound 原样抛回去：那是"build 还没铸出来"
                #      的真实信号（exit 2），吞掉会让它退化成"取到空值、exit 0"。
                if not found and a.version:
                    _node = load_archived_node(a.baseline, a.version)
                    if _node is not None:
                        _shadow = {"versions": {a.version: _node}}
                        val, found = dig(_shadow, full(a.args[0], _shadow))
                    elif _bnf is not None:
                        raise _bnf
            if not found or val is None:
                print(a.default)
            elif isinstance(val, str):
                print(val)
            else:
                print(json.dumps(val, ensure_ascii=False))
            return 0

        if a.op == "set":
            if not a.args or len(a.args) % 2 != 0:
                print("[baseline_edit] ✗ set 需要成对的 <path> <value>", file=sys.stderr)
                return 1
            pairs = [(a.args[i], a.args[i + 1]) for i in range(0, len(a.args), 2)]
            with LockedBaseline(a.baseline, write=True) as b:
                if a.version:
                    warn_if_archived(b.data, a.version, a.baseline)
                for p, v in pairs:
                    plant(b.data, full(p, b.data), parse_value(v))
                    # ★ set current_build 时把该 build 一并登记进 builds[]（幂等）：
                    #   两者不一致时下游读方（classify_push 等）会按 "build not found"
                    #   走 fail-closed，白跑一轮 CICD 监听。写指针的同时建条目，
                    #   不给"指针指向不存在的条目"这种内部不一致留出现的机会。
                    if p.rsplit(".", 1)[-1] == "current_build" and a.version:
                        _bid = parse_value(v)
                        if isinstance(_bid, str) and _bid:
                            _vn = (b.data.setdefault("versions", {})
                                   .setdefault(a.version, {}))
                            _blds = _vn.setdefault("builds", [])
                            if not any(isinstance(x, dict) and x.get("build") == _bid
                                       for x in _blds):
                                _blds.append({"build": _bid, "status": "unknown"})
            print(f"[baseline_edit] ✅ set {len(pairs)} 项 → {a.baseline}")
            return 0

        if a.op == "touch":
            if not a.args:
                print("[baseline_edit] ✗ touch 需要至少 1 个路径", file=sys.stderr)
                return 1
            ts = now_iso()
            with LockedBaseline(a.baseline, write=True) as b:
                if a.version:
                    warn_if_archived(b.data, a.version, a.baseline)
                for p in a.args:
                    plant(b.data, full(p, b.data), ts)
            print(ts)
            return 0

        if a.op == "del":
            if not a.args:
                print("[baseline_edit] ✗ del 需要至少 1 个路径", file=sys.stderr)
                return 1
            with LockedBaseline(a.baseline, write=True) as b:
                missed = [p for p in a.args if not prune(b.data, full(p, b.data))]
            n = len(a.args) - len(missed)
            mark = "✅" if not missed else "⚠️"
            print(f"[baseline_edit] {mark} del {n}/{len(a.args)} 项 → {a.baseline}")
            if missed:
                # ★ 一个删不掉却打 ✅ 的 del 是最难发现的失败：调用方以为清理完了，
                #   残留还在（真实事故：测试造的 versions.V9.9.8 就这样被提交进了入库 baseline）。
                #   故未命中要显式点名，并对最常见的踩法给出正确写法。
                print(f"[baseline_edit]    未命中：{', '.join(missed)}", file=sys.stderr)
                for p in missed:
                    segs = p.split(".")
                    if segs[0] == "versions" and len(segs) > 2:
                        ver = ".".join(segs[1:])
                        print(
                            f"[baseline_edit]    ↳ `{p}` 里的版本号自带点号，会被路径解析拆成多层"
                            f"（{segs[1:]}）——版本键请用 `--version {ver} del <字段>` 形式；"
                            f"要整删该版本条目本 CLI 不支持，需走 LockedBaseline。",
                            file=sys.stderr,
                        )
                        break
            # ★ 仍返回 0：`del` 的语义是「有则删」，幂等清计数器时键不存在是**正常态**
            #   （多处调用形如 `del env_fail_streak`、`del preflight_frozen_at …` 且无 `|| true`，
            #    改成非 0 会误伤它们）。修的是"静默"不是"退出码"——未命中已在 stderr 点名。
            return 0

        if a.op == "bump":
            if len(a.args) != 1:
                print("[baseline_edit] ✗ bump 需要且仅需要 1 个路径", file=sys.stderr)
                return 1
            with LockedBaseline(a.baseline, write=True) as b:
                if a.version:
                    warn_if_archived(b.data, a.version, a.baseline)
                # ⚠️ 必须在锁内解析路径：--build 的下标要从**锁内重读**的 data 里查，
                #    锁外解析等于用旧快照定位，另一条 loop 刚追加的 build 会错位。
                segs = full(a.args[0], b.data)
                cur, _ = dig(b.data, segs)
                try:
                    new = int(cur) + a.by
                except (TypeError, ValueError):
                    new = a.by
                plant(b.data, segs, new)
            print(new)
            return 0
    except BuildNotFound as e:
        # 入参错（指向了不存在的 build）→ 2，与"路径/值语法错=1"区分：
        # 调用方据此可分辨"我写错了路径"与"时序不对、build 还没铸出来"。
        print(f"[baseline_edit] ✗ {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"[baseline_edit] ✗ {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"[baseline_edit] ✗ IO 错误: {e}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
