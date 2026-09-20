#!/usr/bin/env python3
"""
autopilot-ceremony-gate.py — /sprint-autopilot 强制仪式确定性收尾门（外部脚本，防执行体擅自精简）。

设计目的：把"强制仪式不可精简"从 prose 规则 + 内联 bash（执行体可自我说服跳过）升级为
一个**独立、确定性、返回退出码**的外部检查——它只认**文件产物** + 一份**里程碑通知台账**，
缺失且无合法降级即 exit 1。执行体无法用"交互式/省时/避免打扰团队/已做精简"绕过返回码。

强制仪式（与 sprint-autopilot.md Phase 3「强制仪式不可精简硬门」单一信源对齐）：
  0. ★ 版本规划产物存在性（P0-2，仅 --stage final）—— `--entry-mode full|incremental` 时须四类规划产物齐
     （研发需求+详细设计+研发执行计划+研发自测），缺任一 = FAIL→exit 1（堵"隐式跳过规划、结构上不可检测"）；
     `--entry-mode test-only` 不校；`--no-planning 1`（用户显式声明）→ DEGRADE 放行（须交付台账留痕）。
  1. AI执行报告 HTML SPA（index.html + plan.html + data/{build}.js 注册到两页；无违规 markdown）
     —— 无合法降级（autopilot 自有产物，永不可省）
  2. AI测试报告 HTML SPA（index.html + data/{build}.js 已注册）—— 仅当本 build 有浏览器测试
     （--will-browser-test 1）时强制；由 aiauto-test 经 emit-report.py --kind test 产出
  3. 报告交付（report_deliveries[build] 记录 local 交付，**非只落 markdown**）
     —— 无任何交付记录 = FAIL
  3g. ★ 报告数据契约合规（仅 --stage final）—— 解析 data/{build}.js，复用 emit-report.validate_payload（单一信源）
     校字段名/结构/单位；不符 = FAIL（堵"闸门说 OK、人看到满屏 undefined / 10000%"）
  3h. ★ 报告渲染冒烟（仅 --stage final）—— node + report_render_smoke.js 真渲染断言（无异常/非白屏/无 undefined·NaN/无 ≥1000%）；
     无 node = DEGRADE（不阻断纯 python 环境）。3g/3h FAIL → 本门 exit 1 阻断 finalize（不写交付台账、不发 #3）
  3j/3k/3l. ★★ 本轮义务清算（仅 --stage final）—— 补"只校产物存在、不校义务了结"的真空：
     3j 缺陷清算：auto_fixable_pending 仍为真却收尾 = FAIL（该走自动修复闭环，不是弹窗问用户）；
        needs_human 冻结属合法出口 → DEGRADE 上浮。
     3k pending_actions 非空即 FAIL（invariants：非空 = 本 Phase 未完成）。
     3l current_build 有值而 builds[] 空/无对应条目 = FAIL（按 build 取值的门会整体空转）。
     3m ★ 缺陷复验闭环：报告 defects[] 里有"待复验/待验证/未复验"字样的条目，却既无后继 build
        承接复测、也未 needs_human 冻结 = FAIL（下游实测缺口：3j 只校"缺陷有没有登记"、
        不校"有没有闭环"，于是"带着未复验的 P1 缺陷正常收尾"成了唯一没被机器门覆盖的收尾姿势）。
     3p ★ 缺陷分流完整性：报告 defects[] 非空，却既未置 auto_fixable_pending、也无
        pending_clarifications[]、更无 wont-fix 标记 = FAIL（"一条都没分流"恰好让 3j 与 3m
        同时静默通过）；pending_clarifications[].question 空泛或为空 = FAIL（写不出"具体要
        产品回答什么"，就是它不需要产品输入的证据）。部分未归档 = DEGRADE。
     3q ★ 上轮 block 复评（仅复测轮，即本 build 有 retest_of）：上一 build 里 result=block 的
        用例，本轮报告里整条缺席、或仍判 block 却 note 为空 = FAIL；note 与上轮逐字相同 =
        DEGRADE（"原因不变"合法，但要人确认不是照抄）。堵的是 block 原样沉淀到后续所有 build。
  3o. ★ 本轮增量用例可核对（仅 --stage final + 浏览器测试轮）—— baseline `incremental_case_ids`
     与报告 cases[] 的交集：为 0 = 级联了但执行没收到（FAIL）；部分命中 = DEGRADE；
     报告缺 incrementalCaseIds = FAIL（事后无从核对）。
  3n. ★ 测试结果挂靠用例基线（仅 --stage final + 浏览器测试轮，约定 33）—— 报告 cases[].id
     与 docs/testing/{version}/{正式用例,研发自测} 的 TC-* 求交集：交集为 0 = 自造编号、
     没挂靠基线 → FAIL；交集非空但未覆盖率 >50% → DEGRADE 告警（本轮只跑部分用例是合法的）。
     补的是「规划期强制产出基线、测试期却不以它为基准」这个"产出即沉睡"缺口。
  3i. ★ 报告 driver 如实性（仅 --stage final + 浏览器测试轮）—— 报告自述 data/{build}.js 的 driver
     ↔ 运行时独立记录 baseline builds[].driver_actual 比对；不一致 = FAIL（**报告失真**）。
     3g 只能校"值在不在枚举里"，校不出"填的是不是真的"——填 cli 而实际走 MCP 照样全绿。
     ★ 缺 driver_actual = FAIL（报告已出却无驱动记录 = 驱动选定环节没走过；逃生阀 driver_actual_waiver）
     ★ driver_actual 不在浏览器驱动白名单 = FAIL，除非 driver_downgrade_evidence 附 check-cli 举证
  4. version-auditor 终审报告（docs/audit/{version}/version-output-audit-{build}.md，**按 build 精确匹配**，
     不接受宽松 glob —— 否则会被 /version 内部 version-auditor 的同名遗留产物静默满足）
     —— 无合法降级（--skip-audit 仅 /version 内部开关，不豁免 autopilot 终审）
  5. 里程碑通知（按台账核验本 build 应发通知集已发）
     —— 唯一合法降级：--notify 0（notify.enabled=false / 无可用通知渠道 / 用户显式 --no-notify）

★ 报告本体的产出/上传/链接由确定性脚本 .aidp/scripts/emit-report.py 完成（执行体不手搓 data/注册/上传）；
  本门只校最终产物 + 交付台账，堵死"只落一个 markdown 测试记录 + 手搓通知"的退化路径。

里程碑通知为"发出去无本地痕迹"的仪式，故引入轻量台账：命令在每次发通知后调
  autopilot-ceremony-gate.py record-card --node '#1d' --version V --build B
本门据台账核验"通道可用却整次零推送 / 漏发应发通知"。台账由执行体写，无法 100% 防杜撰，
但把"静默省略 + 事后说我精简了"这条易路堵死（要么真发真记、要么显式造假，门槛大幅抬高）。

用法：
  check        强制仪式收尾门（exit 1 = 有缺失且无合法降级）
    --version V0.1.0 --build V0.1.0_build1001
    [--stage skeleton|final] 默认 final。skeleton = 委派前 / 发 #F 前只校 SPA 骨架 + 无 markdown，
                             **不校交付台账**（交付由 build 关闭方 R-4 才写，见 3c 注释）；
                             final = build 关闭方收尾门，校交付台账。堵住"要求尚未产生的台账"时序死结。
    [--notify 0|1]            默认 1（通知通道可用）；0 = 合法降级（通知整组豁免）
    [--will-browser-test 0|1] 默认 0；1 = 本 build 有浏览器测试 → 校 AI测试报告 SPA（3b）+ final 阶段校 test 交付
    [--expect-cards '#1d,#3'] 可选；命令按 0.1bis「ENTRY_MODE × 应发通知集矩阵」算出后传入，逐项核验在台账
    [--repo-root .] [--ledger memory/.aidp/ceremony-ledger.json]
  record-card  发通知后登记台账（命令在每个发通知点之后调一次）
    --node '#1d' --version V0.1.0 --build V0.1.0_build1001 [--repo-root .] [--ledger PATH]
"""
import argparse
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone

DEFAULT_LEDGER = None      # None = 走 aidp_paths（含旧落点自动迁移）


# ⚠️ 「待」与「复验」之间常夹着内容——真实写法是「已修复，⚠️ 待 build1002 复验」，
#    写成 `待复验` 这样的连写模式**恰好匹配不到那一条**（实测：两条待复验只捞出一条）。
#    故允许中间夹 ≤24 个非句读字符；夹得过长（跨句）就不该再算同一个语义。
PENDING_RETEST_RE = re.compile(
    r"待[^，。；;！!？?\n]{0,24}?(?:复验|复测|验证|回归)"
    r"|未(?:复验|复测|验证)"
    r"|pending[\s_-]*(?:retest|verify|verification|regression)",
    re.I)


# 显式「不修」标记：wont-fix 档的判据。要求是**显式**写出，不接受靠语气推断。
WONT_FIX_RE = re.compile(
    r"不予修复|暂不修复|本版不修|不修复|挂起不修"
    r"|won\u0027?t[\s_-]*fix|wontfix|by[\s_-]*design|as[\s_-]*designed",
    re.I)

# 空泛的"待澄清"问句：整句仅由这些套话构成 ⇒ 等同没写。⛔ 只 fullmatch，
# 不做子串匹配 —— 「需要产品确认：停用企业的历史工单是否仍计入统计」是**合格**的问句，
# 子串匹配会把它一并判死，那就从"堵逃逸口"变成"惩罚写得规范的人"。
VAGUE_QUESTION_RE = re.compile(
    r"(?:需要?|待|请)?(?:产品|业务|用户|人工)?(?:再)?(?:确认|澄清|明确|决策|定|拍板)(?:一下)?",
    re.I)


def _has_driver_actual(root, baseline_rel, version, build):
    """本 build 是否已落运行时驱动记录（3i 前移到 skeleton 的前提）。"""
    bl = _load_json(os.path.join(root, baseline_rel)) or {}
    blds = (((bl.get("versions") or {}).get(version) or {}).get("builds")) or []
    be = next((b for b in blds if isinstance(b, dict) and b.get("build") == build), {})
    return bool((be or {}).get("driver_actual"))


def _report_cases(root, version, build):
    """取某 build 的用例明细 `cases[]`。AI执行报告优先、AI测试报告回落。

    两处都读是因为**同一份明细有两个落点**：exec 从同 build 的 test 报告继承（见
    `emit-report.py::inherit_test_facts`），但历史 build 的 exec 里可能还没有。
    回落到 test 才能拿到旧轮次的事实——取不到就当没有基线可比，⛔ 绝不猜。
    """
    for cn in ("AI执行报告", "AI测试报告"):
        pl, _ = _extract_payload(
            os.path.join(root, "docs", "reports", version, cn, "data", f"{build}.js"))
        cases = (pl or {}).get("cases")
        if isinstance(cases, list) and cases:
            return [c for c in cases if isinstance(c, dict)]
    return []


def _build_seq(build_id):
    """从 `{V}_build{N}` 取序号 N；取不到返回 -1（不参与大小比较）。"""
    m = re.search(r"build(\d+)\s*$", str(build_id or ""))
    return int(m.group(1)) if m else -1


def _ledger_path(args):
    if args.ledger:
        return os.path.join(args.repo_root, args.ledger)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import aidp_paths
    aidp_paths.ensure_runtime_dir(args.repo_root)  # ⛔ 落点已在子目录，父目录不再天然存在
    return aidp_paths.ceremony_ledger(args.repo_root)


def _load_json(path):
    """通用 JSON 读取；缺失/损坏返回空 dict（不中断门）。"""
    if not path or not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _open_sprints(root, version):
    """返回该版本【研发执行计划里有、但未在任一协作者 progress.md 标 ✅】的 Sprint 号列表。

    判据刻意与 `phase-0-6.md` 的 S1/S2 状态机同源：
      · 计划集合取自 `docs/plans/{V}/` 下所有 `.md` 里出现的 `Sprint-NNN`；
      · 已关闭集合取自 `memory/{V}/*/progress.md` 里**同一行**同时出现 `Sprint-NNN` 与 ✅ 的条目
        —— **跨用户扫描**（baseline 已扁平化为项目级，Sprint 记录可能落在任一协作者目录下，
        只看本机 `git config user.name` 会把别人关闭的 Sprint 误判成未关闭）。
    取不到计划文件（如 `--no-planning` 的合法路径）→ 返回空列表，不制造假 FAIL。
    """
    plans_dir = os.path.join(root, "docs", "plans", version)
    if not os.path.isdir(plans_dir):
        return []
    sid = re.compile(r"Sprint-(\d{3})")
    planned = set()
    for fn in sorted(os.listdir(plans_dir)):
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(plans_dir, fn), "r", encoding="utf-8", errors="ignore") as f:
                planned |= set(sid.findall(f.read()))
        except OSError:
            continue
    if not planned:
        return []
    closed = set()
    mem = os.path.join(root, "memory", version)
    if os.path.isdir(mem):
        for user in sorted(os.listdir(mem)):
            pg = os.path.join(mem, user, "progress.md")
            if not os.path.isfile(pg):
                continue
            try:
                with open(pg, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "✅" in line:
                            closed |= set(sid.findall(line))
            except OSError:
                continue
    return sorted(f"Sprint-{n}" for n in (planned - closed))


def _load_validate_payload():
    """从同目录 emit-report.py 动态加载 validate_payload（schema 单一信源，避免双写）；失败返回 None。"""
    try:
        import importlib.util
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "emit-report.py")
        if not os.path.isfile(p):
            return None
        spec = importlib.util.spec_from_file_location("_emit_report", p)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "validate_payload", None)
    except Exception:
        return None


def _extract_payload(data_js_path):
    """从 data/{build}.js（IIFE `window.X.push({...});`）抽出 JSON 对象（string-aware 花括号匹配）。
    返回 (payload|None, err|None)。"""
    if not os.path.isfile(data_js_path):
        return None, "data 文件不存在"
    try:
        txt = open(data_js_path, "r", encoding="utf-8").read()
    except OSError as e:
        return None, f"读取失败：{e}"
    i = txt.find("push(")
    s = txt.find("{", i) if i >= 0 else -1
    if s < 0:
        return None, "未找到 push( 的对象起始 {"
    depth, j, in_str, esc = 0, s, False, False
    while j < len(txt):
        ch = txt[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    break
        j += 1
    try:
        return json.loads(txt[s:j + 1]), None
    except (json.JSONDecodeError, ValueError) as e:
        return None, f"JSON 解析失败：{e}"


def _load_ledger(path, quarantine_on_corrupt=False):
    """读里程碑通知台账。

    ⛔ **损坏时绝不静默返回空台账**：那等于把「此前发过的卡全丢了」伪装成「从来没发过卡」，
    而下游收尾门据此判 FAIL → bump `dev_fail_streak` → 3 tick 冻 handoff-exhausted（人工专属档）。
    `quarantine_on_corrupt=True`（写路径）时把损坏文件改名隔离并告警，让"丢了"这件事可见。
    """
    if not os.path.isfile(path):
        return {"cards": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict) or not isinstance(data.get("cards"), list):
            raise ValueError("台账结构不合契约（缺 cards 数组）")
        return data
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        if quarantine_on_corrupt:
            bad = path + ".corrupt-" + datetime.now().strftime("%Y%m%d%H%M%S")
            try:
                os.replace(path, bad)
            except OSError:
                bad = "(隔离失败)"
            sys.stderr.write(f"⚠️ 里程碑通知台账损坏（{exc}）→ 已隔离为 {bad}，本次从空台账重建。"
                             f"⛔ 此前的通知记录已丢失，收尾门可能判缺卡，请人工核对已发通知\n")
        else:
            sys.stderr.write(f"⚠️ 里程碑通知台账不可读（{exc}）→ 本次按空台账判定，"
                             f"⛔ 结论可能偏严（把发过的卡当成没发）\n")
        return {"cards": []}


def cmd_record_card(args):
    """登记一条已成功发送的里程碑通知。

    ★ 并发安全：同一份台账被**两条 loop** 都写（`notify.py` 发送成功后转调本子命令，
    开发链路 10m / 测试链路 5m 共用）。此前是**无锁截断写**：发通知瞬间重叠时后写者用旧快照
    覆盖前者 → 丢卡 → 收尾门恒 FAIL → 冻结。复用 baseline 侧同款 flock 范式。
    """
    path = _ledger_path(args)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    rec = {
        "node": args.node,
        "version": args.version,
        "build": args.build,
        "status": getattr(args, "status", "sent") or "sent",
        "ts": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    # ⛔ 锁路径走 baseline_edit.lock_path（全仓单一信源）：此处与 emit-report 锁的是**同一个文件**，
    #    各写各的路径拼接 ⇒ 任何一处改路径就让互斥当场归零（静默丢更新）。
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    from baseline_edit import lock_path as _lock_path
    _lp = _lock_path(path)
    os.makedirs(os.path.dirname(_lp), exist_ok=True)
    lock_fd = None
    try:
        import fcntl
        lock_fd = open(_lp, "a+")
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
    except Exception:
        lock_fd = None
        sys.stderr.write("⚠️ 里程碑通知台账降级为**无锁写**（fcntl 不可用）→ 并发发通知可能丢记录\n")
    try:
        # ★ 必须**在锁内重读**：锁外读到的快照可能已被对方 loop 改过。
        led = _load_ledger(path, quarantine_on_corrupt=True)
        led["cards"].append(rec)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(led, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)          # 原子替换，杜绝截断写被打断留下半份文件
    finally:
        if lock_fd is not None:
            try:
                import fcntl as _f
                _f.flock(lock_fd.fileno(), _f.LOCK_UN)
            finally:
                lock_fd.close()
    print(f"🗒️  已登记里程碑通知台账：{args.node}（build={args.build}）→ {path}")
    return 0


def _build_node(vnode, build):
    """在 versions.{V}.builds[] 里按 build 号取条目；取不到返回 {}。"""
    for b in (vnode or {}).get("builds") or []:
        if isinstance(b, dict) and b.get("build") == build:
            return b
    return {}


def _resolve_entry_mode(args, vnode, build=""):
    """entry_mode 的【唯一】取值口径：
    显式 `--entry-mode` > **本 build 的 `builds[].entry_mode`** > 版本级 `autopilot_entry_mode` > `full`。

    ## ★ 为什么必须优先取 build 级（实际项目第二次实测）

    `autopilot_entry_mode` 是**版本级**字段，而 entry_mode 实际是 **build 级属性**：
    同一个版本里首轮 `full`、复验轮 `test-only` **共用一个槽位**，后写的把先写的覆盖掉。
    于是 Stop hook 拿着**版本槽位里的当前值**去校**另一个 build**，通知集自然算错——
    实测表现是要求补发两条「内容必然为假」的通知（那一轮压根没发生的里程碑）。
    这与下面记载的那次死锁是**同一个失败形态的第二形态**：上次是"回退链缺一环"，
    这次是"回退到了一个粒度不对的槽位"。**粒度对不上时，回退链再完整也取不到正确值。**

    build 级值由 Phase 3.1.5 铸造时落 `builds[].entry_mode`（复用既有 build 时**只补不覆盖**——
    build 的通知集由"它是怎么开始的"决定，中途换 tick 模式不改变已发生的里程碑）。
    版本级字段保留作**向后兼容回退**（老 baseline 的 build 条目没有该字段）。

    ⛔ **本函数是该字段的单一信源，任何地方都不得再就地写 `args.entry_mode or "full"`。**

    ## 为什么必须抽出来（实际项目实测的结构性死锁）

    同一个 `entry_mode` 此前在本脚本内有**两套取值策略**：
      · `_derive_expect_cards()`  → `args.entry_mode or "full"`            ← 不回退 baseline
      · P0-2 规划产物检查          → `args.entry_mode or baseline… or "full"` ← 三级回退

    而 `.aidp/hooks/autopilot-stop-guard.py` 调本脚本时**不传** `--entry-mode`。两者叠加：
    `args.entry_mode=None` → 通知集按 `full` 算 → **test-only 轮次经 hook 路径必然索要
    `#1c` 开发开始 / `#1d` 部署完成 / `#2` Sprint 关闭**——而这三件事那一轮一件都没发生。

    死锁在于：**调用方无法用任何配置纠正**（baseline 里正确写了 `autopilot_entry_mode=test-only`
    也没用），于是执行体只剩三条坏路——补发通知就是**向团队谎报里程碑**（直接违反范式
    「占位不等于伪造」原则）、`touch .autopilot-stop-guard-off` 会**连带掩盖本轮真实的其它缺失**、
    改脚手架脚本则违反约定 16。**护栏把执行体逼向作假，比护栏不存在更糟。**

    注：本脚本 `--entry-mode` 的 help 早就写着"不传则回退读 baseline"——**承诺存在、
    一处实现、一处没实现**，正是"同字段多套策略"的典型代价。
    """
    return (args.entry_mode
            or (_build_node(vnode, build).get("entry_mode") if build else "")
            or (vnode or {}).get("autopilot_entry_mode")
            or "full")


def _derive_expect_cards(args, vnode, build=""):
    """命令端未传 `--expect-cards` 时，脚本自算「本轮至少应发」的通知集（漏跑兜底，非上限）。

    ## 为什么必须由脚本自算

    逐项核验此前**只在命令端传入期望集时才发生**，而期望集的推导写在 `phase-3-9.md` ——
    "检查有没有漏做"这件事，本身写在"可能被漏做"的那个分片里。执行体一旦没有逐片 Read
    就自行推进（实测即如此），推导代码根本没跑 → 落进退化分支 → 而退化判据又恒真（P0-1）
    → **一整轮开发期 + 测试期零通知，收尾门全程 PASS**。

    ## 判据来源与刻意的保守

    通知集矩阵单一信源 = `phase-0-5.md` 0.1bis；本函数只复刻其中**能由入参/baseline 确定**的部分：

      · `#0` / `#1b` / `#1c`  —— 恒发，无条件期望
      · `#1d`  —— 仅"本轮真的部署了"才发；判据取 baseline `deployment_mode != none`
      · `#2`   —— 增量路径无 Sprint，故仅 `entry_mode != incremental` 才期望
      · `#3`   —— 静态-only（无浏览器测试）时由 autopilot 自己发；有浏览器测试则归测试链路
      · `#1`   —— **刻意不自算**：它只有"本轮真跑了规划"才该期望，而 gate 事后无法可靠区分
                   "产物是本轮产的"还是"上轮就在"。宁可少期望，也不制造假 FAIL。

    `test-only` 入口下 autopilot 不发任何里程碑卡（全归测试链路）→ 返回空集。

    ⛔ **entry_mode 一律经 `_resolve_entry_mode()` 取**（显式参数 > baseline > full）：
    曾因本函数就地写 `args.entry_mode or "full"`、而 hook 又不传该参数，导致 test-only
    轮次恒索要 `#1c/#1d/#2` 三张不该发的卡，且无法通过任何配置纠正（详见该 helper 的 docstring）。
    """
    _em = _resolve_entry_mode(args, vnode, build)   # ★ 单一口径：build 级优先 > 版本级回退 > full
    if _em == "test-only":
        return []
    cards = ["#0", "#1b", "#1c"]
    # ★ 与 will_browser_test 同一口径（显式落盘值优先）：`deployment_mode` 只是配置形态，
    #   不含 `--skip-deploy` / `--skip-aiauto-test` 的本轮裁剪；两处若各推各的，
    #   期望通知集会与命令端**方向相反**（一边要 #1d、一边要 #3），把合规执行逼成"漏发通知"。
    _wbt = vnode.get("will_browser_test")
    deployed = (bool(_wbt) if _wbt is not None
                else (vnode.get("deployment_mode") or "none") != "none")
    if deployed:
        cards.append("#1d")
    if _em != "incremental":
        cards.append("#2")
    if not deployed:
        cards.append("#3")          # 静态-only：autopilot 自己是 build 关闭方
    return cards


# ── 中途交还控制权检测（HANDBACK）─────────────────────────────────────────────
# 「产物必须齐全」早已从自律级升级为结构级（本门 exit 1，执行体绕不过）；
# 而「不许中途把控制权交还用户」强制度还停在自律级——四处文档禁令 + 零机器门。
# 两条规则后果并不对称地轻：后者一旦失效，整轮停摆（真实事故：规划段跑完就问
# 「要我继续进入开发阶段吗？」，本轮 HAS_WAKE_SOURCE=0、没有下一 tick 会来接，
# Phase 3.2~3.4 连同全部 Sprint 被丢回给用户）。本检查把它补齐为同级机器门。
#
# ★ 判定式、不看话术（关键设计）：文档原先点名禁的是「如需无人值守请挂 /loop」
#   这一类**具体措辞**，而真实失效用的是「要我继续吗 / 你想先看看吗」这种征询式
#   变体——措辞完全不同、实质一样，于是没被自己的禁令拦住。故本检查**只看客观状态**：
#   命令返回时 run_state 是否停在非终态、且有没有人会来接。话术怎么写都逃不掉。
#
# ★ 判据（两个值都已落盘，纯确定性、无需新增采集）：
#     autopilot.wake_source_this_tick        1=/loop 或 cron（有下一 tick）；0=交互式单次/裸 --unattended
#     versions.{V}.run_state.next_phase      终态为 "done"
#     versions.{V}.run_state.next_sprint     终态为 "done"
#   VIOLATION ⟺ wake_source==0 且（next_phase 非空且≠done 或 next_sprint 非空且≠done）
#
# ⚠️ **next_phase 与 next_sprint 必须【都】看**：命令正文原有的反向硬断言只写了
#   `next_sprint != "done"`，而真实事故停在 Phase 3.1→3.2 边界——那时 next_phase="3.2-dev"
#   而 next_sprint 尚未进入循环（空/done），旧断言恰好判不出来。只看其一即留缺口。
#
# ⚠️ **空值不算违背**：next_phase 为空 = Phase 状态机从未启动，对应「Phase 1 无变化干净退出 /
#   版本已交付 / 停在配置向导」等合法 bailout——那些路径由 --no-pipeline-reason 分支各自负责
#   大声说清依据，不该在这里被误判成"丢活儿"。

DONE_STATES = ("done", "DONE", "完成")


def _handback_verdict(bl, version, wake_source=None):
    """返回 (violation:bool, info:dict)。纯读，无副作用。"""
    ap = (bl.get("autopilot") or {})
    ws = wake_source if wake_source is not None else ap.get("wake_source_this_tick")
    try:
        ws = int(ws)
    except (TypeError, ValueError):
        ws = 0                      # 读不到按 0（保守：宁可多报一次，也不放过丢活儿）
    vn = (((bl.get("versions") or {}).get(version)) or {})
    rs = vn.get("run_state") or {}
    np_, ns = (rs.get("next_phase") or "").strip(), (rs.get("next_sprint") or "").strip()
    pending = [x for x in (np_, ns) if x and x not in DONE_STATES]
    # ★ 合法冻结豁免：本函数自己的违规文案就写着「确实跑不动（熔断 / needs_human / 阻塞）
    #   才走失败处置」——意图认可冻结合法，但谓词从不读 `needs_human`，于是**按契约冻结的
    #   那一轮**反被判 VIOLATION：Stop hook 据此 exit 2 阻止收工，打印「唯一正解 = 回到该
    #   Phase 把剩余流程在本轮内跑完」，而该 Phase 正卡在等人 accept、本轮内无解 ——
    #   连撞到 STOP_GUARD_MAX_BLOCKS 才 fail-open。于是唯一的结构级兜底门在最该沉默的时刻变噪音。
    #
    #   ⚠️ 豁免**必须以冻结四件套齐备为前提**：只 echo 不写 baseline 的"半截冻结"不能拿通行证，
    #   那正是 `check_freeze_contract.py` 在防的形态。
    frozen = bool(vn.get("needs_human"))
    quartet = (frozen
               and bool(vn.get("aiauto_frozen_at"))
               and bool((vn.get("freeze_reason") or "").strip())
               and bool((bl.get("aiauto_blocked_reason") or "").strip()))
    info = {"wake_source": ws, "next_phase": np_ or None, "next_sprint": ns or None,
            "unfinished": pending, "frozen": frozen, "freeze_quartet_complete": quartet,
            "freeze_reason": vn.get("freeze_reason")}
    if quartet:
        info["exempt"] = "frozen-by-contract"   # 合法停：停得响 + 四件套齐备
        return False, info
    if frozen and not quartet:
        info["exempt"] = None
        info["note"] = "已置 needs_human 但冻结四件套不齐（半截冻结）——不豁免"
    return (ws == 0 and bool(pending)), info


def cmd_handback_check(args):
    root = args.repo_root
    bl = _load_json(os.path.join(root, args.baseline)) or {}
    violation, info = _handback_verdict(
        bl, args.version, None if args.wake_source < 0 else args.wake_source)
    info["version"] = args.version
    info["verdict"] = "VIOLATION" if violation else "PASS"

    if args.record:
        try:
            subprocess.run(
                [sys.executable, os.path.join(root, ".aidp/scripts/baseline_edit.py"),
                 "set", "autopilot.last_handback",
                 json.dumps({k: info[k] for k in ("verdict", "wake_source", "next_phase",
                                                  "next_sprint")}, ensure_ascii=False)],
                cwd=root, capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            pass                    # 留痕失败不改变判定

    if args.json:
        print(json.dumps(info, ensure_ascii=False))
    elif not violation:
        why = ("有下一 tick 会来接（/loop 或 cron）" if info["wake_source"] == 1
               else "run_state 已达终态或从未进入流水线")
        print(f"✅ HANDBACK: PASS —— {why}"
              f"（next_phase={info['next_phase'] or '-'} next_sprint={info['next_sprint'] or '-'}）")
    else:
        print("⛔ HANDBACK: VIOLATION —— 契约违背：本轮无唤醒源却把未完成的流程交还给用户")
        print(f"   wake_source_this_tick=0（无 /loop、无 cron —— 没有下一 tick 会来接）")
        print(f"   run_state 停在非终态：{'、'.join(info['unfinished'])}"
              f"（next_phase={info['next_phase'] or '-'} next_sprint={info['next_sprint'] or '-'}）")
        print("   ⛔ 唯一正解 = 回到该 Phase 把剩余流程【在本轮内】跑完；确实跑不动（熔断 /")
        print("      needs_human / 阻塞）才走失败处置：显式告警 + #4 卡讲清『还剩什么、为什么停』。")
        print("   ⛔ 禁止以任何话术收尾——包括『要我继续吗 / 你想先看看规划产物吗』这类征询式变体，")
        print("      以及『如需无人值守请挂 /loop』这类把命令自己该干的活儿说成用户配置缺失的说法。")
    return 1 if violation else 0


def cmd_check(args):
    root = args.repo_root
    V, B = args.version, args.build

    # ★ "未进流水线"结构级告警（reporter ③ · 堵"既不产物也不告警"黑洞）：
    #   命令 bailout（判增量绕过 / Phase 1 无变化 / 版本已交付 / 停在配置向导）而不产 build/报告/通知时，
    #   由命令端**无条件**调本分支——不产是"合法无操作"，但必须【大声说清依据】、绝不静默。把"文档里写着必须打印"
    #   升级为"脚本结构级必打印"（执行体无法用"我以为不用打印"绕过）。exit 0（非缺失、非 FAIL）。
    if args.no_pipeline_reason:
        # ⛔ 这条分支原本排在 --build 校验与全部闸门之前、且不与 baseline 交叉校验，
        #    于是传一个真实 build 号 + 任意字符串就能让"本轮未进流水线"与"本轮铸了 build"
        #    同时成立 —— 15 项强制仪式一项不跑而 exit 0。自由文本不能成为总旁路：
        #    "未进流水线"是可被 baseline 证伪的事实，不是一句声明。
        _bl_np = _load_json(os.path.join(root, args.baseline)) or {}
        _v_np = ((_bl_np.get("versions") or {}).get(V)) or {}
        _cur_np = _v_np.get("current_build") or ""
        _builds_np = [b for b in (_v_np.get("builds") or []) if isinstance(b, dict)]
        # 矛盾只看**本 tick 铸的 / 仍在进行的** build：历史上已关闭或已定稿的 build 不构成矛盾
        # （「Phase 1 无变化」「版本已全部交付」这类合法声明必然有历史 build）。
        _tick_at = str(((_bl_np.get("autopilot") or {}).get("tick_started_at")) or "")
        _live_np = [b for b in _builds_np
                    if (b.get("status") not in ("closed", "tested") and not b.get("ai_report_finalized"))
                    or (_tick_at and str(b.get("started_at") or "") >= _tick_at)]
        if _live_np:
            print(f"❌ 声明「本轮未进流水线」与 baseline 矛盾：current_build={_cur_np or '空'}、"
                  f"进行中 / 本 tick 铸造的 build {len(_live_np)} 条（{_live_np[0].get('build')}）—— "
                  f"请去掉 --no-pipeline-reason 并传 --build 走正常收尾门。", file=sys.stderr)
            return 2
        print("══════ /sprint-autopilot 收尾门 · 本轮未进入开发流水线 ══════")
        print(f"版本 {V}")
        print(f"⚠️ 本轮未进入开发流水线（Phase 2/3 仪式框架），不会产生 build 号 / AI执行报告 / AI测试报告 / 里程碑通知。")
        print(f"   判定依据：{args.no_pipeline_reason}")
        print("   应产 vs 实产：build号=无(未铸) · AI执行报告=无 · AI测试报告=无 · 里程碑通知=无 —— 均因未进流水线，属预期无产、非缺失。")
        print("   如需强制产出：显式跑 /version 全量规划 + /sprint-batch（已交付版本则先走版本落点决策门定 patch/minor）。")
        return 0
    if not B:
        print("❌ check 需要 --build（若本轮未进流水线，请改用 --no-pipeline-reason '<判定依据>' 声明）", file=sys.stderr)
        return 2

    # ★ --will-browser-test 未传（-1）→ 从 baseline 事实推导，并记下来源供输出标注（reporter P1）。
    #   推导判据按可靠性排序：本 build 已 finalize 测试报告 > 有测试交付台账 > 有委派证据。
    #   三者皆无才判 0 —— 那才是真的"本 build 没做浏览器测试"。
    _wbt_src = "传入"
    if args.will_browser_test == -1:
        _blw = _load_json(os.path.join(root, args.baseline)) or {}
        _vw = ((_blw.get("versions") or {}).get(V)) or {}
        _bew = next((b for b in (_vw.get("builds") or [])
                     if isinstance(b, dict) and b.get("build") == B), {})
        _has_test_delivery = bool(((_vw.get("report_deliveries") or {}).get(B) or {}).get("test_report")
                                  or ((_blw.get("report_deliveries") or {}).get(B) or {}).get("test_report"))
        # ⛔ 判据必须是「这个 build **该不该**被浏览器测」，不是「它**有没有**被测过」。
        #    原实现取 ai_report_finalized / aiauto_delegated_at / 已有 test 交付三者之一——
        #    而 3b2「测试链路运行证据」这道门（专为抓"从未真 invoke /sprint-aiauto-test"而写）
        #    的前置条件正是 will_browser_test==1：**门的开关接在它要检测的那根线上**。
        #    于是「已部署、却从未测过」的 build 三个证据全无 → 判 0 → 3b/3b2/3c/3n/3i/#F
        #    整批跳过 → 全绿关闭，恰好在最需要它成立的场景里失效。
        #    现改为确定性事实：部署模式非 none 即应测；测试证据只留给 3b2 当**被检对象**。
        _dep_mode = (_vw.get("deployment_mode")
                     or (_blw.get("autopilot_decisions") or {}).get("deployment", {}).get("mode")
                     or "")
        # ★ 显式落盘值优先：`versions.{V}.will_browser_test` 由 phase-3-8 就地算出并写盘，
        #   它**已经把本轮的裁剪 flag（--skip-aiauto-test / --skip-deploy）计算在内**。
        #   ⛔ 不读它、只按 `deployment_mode` 重推一遍，会与命令端口径**方向相反**：
        #   `deployment_mode` 是**配置形态**（取自 PRD），裁剪 flag 完全不影响它。
        #   实测后果：`deployment.mode=cloud` + `--skip-deploy` 时，命令端算出的期望通知集含 #3、不含 #1d，
        #   门自算的却含 #1d、不含 #3，且 3b/3b2/3c 三项必 FAIL → bump dev_fail_streak →
        #   3 tick 后冻进 `handoff-exhausted`（人工专属档、探针一律不解冻）。
        #   命令端「收尾门按静态-only 档核验」这句承诺，在实现里只要 mode≠none 就永不成立。
        _wbt_explicit = _vw.get("will_browser_test")
        if _wbt_explicit is not None:
            args.will_browser_test = int(bool(_wbt_explicit))
            _wbt_src = "baseline显式(phase-3-8 落盘，已含本轮裁剪 flag)"
        else:
            _should_test = str(_dep_mode).lower() not in ("", "none")
            args.will_browser_test = 1 if (_should_test
                                           or _bew.get("ai_report_finalized")
                                           or _bew.get("aiauto_delegated_at")
                                           or _has_test_delivery) else 0
            _wbt_src = "baseline推导(无显式落盘值时的回退)"

    # 通知集自算与应产清单打印都要用；定义在通知分支之外（notify=0 时也会被打印引用）
    _v5_for_cards = (((_load_json(os.path.join(root, args.baseline)) or {})
                      .get("versions") or {}).get(V)) or {}

    rpt_ai = os.path.join(root, "docs", "reports", V, "AI执行报告")
    results = []  # (level, name, verdict, detail)  verdict ∈ PASS/FAIL/DEGRADE

    def rec(name, ok, detail="", degrade=False):
        verdict = "DEGRADE" if degrade else ("PASS" if ok else "FAIL")
        results.append((name, verdict, detail))

    # 0. ★ P0-2 版本规划产物存在性（堵"隐式跳过规划、结构上不可检测"洞）：
    #    full/incremental 须**六类**规划产物齐，缺即 FAIL→exit 1；test-only 不校；
    #    用户显式 --no-planning 则 DEGRADE 放行（须台账留痕）。仅 --stage final 校（skeleton 阶段规划可能尚在跑）。
    #
    #    ⛔ 为什么是六类而不是四类：`/version` 自己的「三步落盘自检」确认的是 **6 类**——
    #    研发需求 / 详细设计 / 研发执行计划 / 研发自测**用例** / 研发自测**方案** / **测试环境与账号**。
    #    本门与 autopilot 的 `PLANNING_DONE` 判据长期只校前 4 类，却自称"与 /version 同口径"。
    #    残缺态「执行计划 + 用例已在，但自测方案 / 测试环境与账号缺失」因此被判成"规划齐全"→
    #    永久跳过 `/version` → 绕过它那道 6 类硬门 → 本门也照样全绿。而 `01_测试环境与账号.md`
    #    正是 `/sprint-aiauto-test` 的输入：缺了它，浏览器实测根本无从开始。
    def _has_md(d, needle=None):
        if not os.path.isdir(d):
            return False
        return any(fn.endswith(".md") and (needle is None or needle in fn) for fn in os.listdir(d))

    # entry_mode / no_planning：显式 --entry-mode/--no-planning 优先；否则回退 baseline（autopilot Phase 3.1 写入）；再否则默认 full/0。
    # 这样 autopilot 自跑 final 门与 aiauto-test Phase 3.7 final 门【两条路径】都自动带上 P0-2 检查，无需各调用点都传 flag。
    _bl_pln = _load_json(os.path.join(root, args.baseline)) or {}
    _bv_pln = ((_bl_pln.get("versions") or {}).get(V) or {})
    entry_mode = _resolve_entry_mode(args, _bv_pln, B)   # ★ 与通知集自算同一口径（单一信源）
    no_planning = args.no_planning if args.no_planning is not None else int(_bv_pln.get("autopilot_no_planning") or 0)
    if args.stage == "final" and entry_mode in ("full", "incremental"):
        if no_planning:
            rec(f"版本规划产物(ENTRY_MODE={entry_mode})", True,
                "用户显式 --no-planning、放行（须交付台账留痕）", degrade=True)
        else:
            test_root = os.path.join(root, "docs", "testing", V)
            test_dir = os.path.join(test_root, "研发自测")
            plan_ok = _has_md(os.path.join(root, "docs", "plans", V), "研发执行计划")
            req_ok = _has_md(os.path.join(root, "docs", "requirements", V, "研发需求"))
            design_ok = _has_md(os.path.join(root, "docs", "design", "detail", V))
            test_ok = (_has_md(test_dir, "自测用例")
                       or _has_md(test_dir, "研发自测")
                       or os.path.isfile(os.path.join(test_root, "研发自测.md"))
                       or os.path.isfile(os.path.join(test_root, "研发自测用例.md")))
            # 第 5 / 6 类：研发自测**方案**（`01_研发自测方案.md`，旧锚 `00_研发自测方案.md` grandfather）
            #             与**测试环境与账号**（`01_测试环境与账号.md`，aiauto-test 的配置输入）
            plan_test_ok = (_has_md(test_dir, "研发自测方案")
                            or os.path.isfile(os.path.join(test_root, "研发自测方案.md")))
            env_ok = _has_md(test_dir, "测试环境与账号")
            planning_ok = plan_ok and req_ok and design_ok and test_ok and plan_test_ok and env_ok
            rec(f"版本规划产物齐全(ENTRY_MODE={entry_mode}：需求+详设+计划+自测用例+自测方案+测试环境与账号)", planning_ok,
                "" if planning_ok else
                (f"缺规划产物(PLAN={int(plan_ok)} REQ={int(req_ok)} DESIGN={int(design_ok)} "
                 f"CASE={int(test_ok)} SCHEME={int(plan_test_ok)} ENV={int(env_ok)})→ "
                 f"P0-2：{entry_mode} 模式必须先跑 /version 全量规划（或用户显式 --no-planning + 台账留痕）；"
                 f"跳过规划不是合法降级，隐式免规划即在此 exit 1。"
                 f"缺 SCHEME/ENV 可单独补跑 `/sprint-selftest {V}`"))

        # 0bis. ★ Sprint 关闭度（堵"语义判 incremental → 跳过全量开发段 → 收尾全绿"）：
        #   `full`/`incremental` 收尾时，研发执行计划里不得还有未关闭 Sprint。
        #   ⛔ 缺这一项的后果：目标版本处于 S1（已规划、Sprint 没跑完）时，用户给一句自然语言
        #   增量意图 → 语义判 incremental → `PLANNING_DONE=1` 成立 → 整个全量开发段被跳过，
        #   而部署 / 报告 / 通知 / 收尾门全绿、正常收尾，剩余 N 个 Sprint 被静默丢下。
        #   顶层契约的违约本来就是结果级的——"命令返回时仍有未关闭 Sprint 却正常收尾"，
        #   而此前所有检查项都只问"东西产出来没有"，没有一项问"活干完没有"。
        if args.stage == "final" and entry_mode in ("full", "incremental"):
            open_sprints = _open_sprints(root, V)
            rec("Sprint 关闭度(执行计划内无未关闭 Sprint)", not open_sprints,
                "" if not open_sprints else
                (f"仍有 {len(open_sprints)} 个未关闭 Sprint：{', '.join(open_sprints[:6])} —— "
                 f"{entry_mode} 模式收尾时开发段必须已跑完；"
                 f"若确为只改增量，请显式 `--skip-dev`（test-only）而非用语义判定绕过"))

    # 1. AI执行报告页面
    idx = os.path.join(rpt_ai, "index.html")
    plan = os.path.join(rpt_ai, "plan.html")
    pages_ok = os.path.isfile(idx) and os.path.isfile(plan)
    rec("AI执行报告页面(index.html+plan.html)", pages_ok,
        "" if pages_ok else "缺页面 → 回 Phase 3.4 step2：cp 模板 index.html+plan.html+assets")

    # 2. AI执行报告 data 已注册两页
    data_js = os.path.join(rpt_ai, "data", f"{B}.js")
    reg_token = f"data/{B}.js"
    data_ok = os.path.isfile(data_js)
    if data_ok and pages_ok:
        for p in (idx, plan):
            try:
                with open(p, "r", encoding="utf-8", errors="ignore") as f:
                    if reg_token not in f.read():
                        data_ok = False
                        break
            except OSError:
                data_ok = False
                break
    rec(f"执行数据 data/{B}.js(已注册 index+plan 两页)", data_ok,
        "" if data_ok else "回 Phase 3.4 step1：写 data 文件 → 注册 <script> 到两页")

    # 3. 无违规 markdown 报告（执行 + 测试两目录都反检）
    #    ★ 运行态产物白名单（E1/E2）：auto-test-runner 等的合法运行态 markdown（run-context / readme 等）
    #    不是"违规报告"，须排除、绝不撞门。与 auto-test-runner SKILL.md「run-context 落
    #    {测试产物目录}/run-context.md」约定对齐（两处脚手架文件不再互相打架）；新增运行态 md
    #    在此登记即可扩展，避免后续运行态产物再次误判。违规判定仅针对"报告态 markdown"（执行结果 /
    #    执行计划 / 测试记录等——它们应产 HTML SPA 而非落 markdown）。
    RUNTIME_MD_WHITELIST = {"readme.md", "run-context.md"}
    rpt_test = os.path.join(root, "docs", "reports", V, "AI测试报告")
    stray = glob.glob(os.path.join(rpt_ai, "*_AI执行结果.md")) + \
        glob.glob(os.path.join(rpt_ai, "AI执行计划_Build*.md")) + \
        [m for m in glob.glob(os.path.join(rpt_test, "*.md"))
         if os.path.basename(m).lower() not in RUNTIME_MD_WHITELIST]
    rec("无违规 markdown 报告(应只产 HTML SPA)", not stray,
        "" if not stray else f"检出并应删除：{', '.join(os.path.basename(s) for s in stray)}（报告须 HTML SPA，见 emit-report.py）")

    # 3b. AI测试报告 SPA（仅当本 build 有浏览器测试 → aiauto-test 应经 emit-report.py --kind test 产出）
    #   ★ BUG-2 修复：本段【只在 --stage final 校】。测试报告 SPA 由测试链路在 #F 之后才产出，
    #   而 skeleton 阶段是"委派【前】只校执行报告骨架"——此时测试报告必然尚不存在，若不分 stage
    #   就校，skeleton 必 FAIL、形成"委派前跑 skeleton → FAIL → 无法委派"的时序死结。与同为测试相关的
    #   3b2/3c（均已 --stage final 守卫）对齐。执行报告骨架（1/2 段）不受影响、skeleton 照常校。
    if args.will_browser_test == 1 and args.stage == "final":
        t_idx = os.path.join(rpt_test, "index.html")
        t_data = os.path.join(rpt_test, "data", f"{B}.js")
        t_ok = os.path.isfile(t_idx) and os.path.isfile(t_data)
        if t_ok:
            try:
                with open(t_idx, "r", encoding="utf-8", errors="ignore") as f:
                    if f"data/{B}.js" not in f.read():
                        t_ok = False
            except OSError:
                t_ok = False
        rec(f"AI测试报告 SPA(index.html + data/{B}.js 已注册)", t_ok,
            "" if t_ok else "缺 → aiauto-test 经 emit-report.py --kind test 产出并注册（严禁只落 markdown 测试记录）")

    # 3b2. ★ 测试链路运行证据（仅 --stage final + 浏览器测试轮 —— reporter B：堵"内联驱动 chrome 却从未真 invoke /sprint-aiauto-test"的委派真空）：
    #      本轮既然 will_browser_test=1，就必有一条真实测试链路跑过——判据 = 本 build 落了 aiauto_delegated_at（autopilot 真 invoke 时写）
    #      或顶层 aiauto_test_heartbeat_at 在近窗内有心跳。两者皆无 = 委派落空（autopilot 自身内联跑测、测试链路 final 门/#F/#3 永不产出）→ FAIL。
    #      skeleton 阶段（委派前）豁免——那时本就还没委派。
    if args.stage == "final" and args.will_browser_test == 1:
        _bl = _load_json(os.path.join(root, args.baseline))
        _blds = ((_bl.get("versions") or {}).get(V) or {}).get("builds") or []
        _row = next((x for x in _blds if x.get("build") == B), {}) or {}
        _delegated = bool(_row.get("aiauto_delegated_at"))
        # ⛔ 判据不是"心跳新鲜"而是"真在干活"：心跳每 tick 起始无条件先写，
        #    冻结/空转的测试 loop 心跳照样新鲜 → 本门会被架空。见 test_loop_alive。
        _hb_fresh = test_loop_alive(_bl, V)
        rec("测试链路运行证据(委派标记 / 心跳且未阻塞)", _delegated or _hb_fresh,
            "" if (_delegated or _hb_fresh) else
            "委派落空：本 build 无 aiauto_delegated_at 委派证据、也无测试链路心跳 = 疑似 autopilot 内联驱动 chrome 但从未真 invoke /sprint-aiauto-test；"
            "→ 交互单次经 Step ④ 自调用 /sprint-aiauto-test --once 补跑（补产 #F/#3 + AI测试报告 + finalize），无人值守须挂第二条 /loop 5m /sprint-aiauto-test")

    # 3c. 报告交付（local；非只落 markdown）—— ★ 仅 --stage final 校验
    #     交付台账（report_deliveries）由「带上传的 emit-report」在 build 关闭方收尾时才写：
    #       · 静态-only：autopilot Phase 3.4 R-4（WILL_BROWSER_TEST=0）
    #       · 浏览器路径：aiauto-test Phase 3.7（#F 之后）
    #     故 skeleton 阶段（委派前 / 发 #F 前，交付尚未发生）**不校交付**，避免"要求尚未产生的台账"的时序死结。
    if args.stage == "final":
        bl = _load_json(os.path.join(root, args.baseline))
        deliveries = (bl.get("report_deliveries") or {}).get(B, {})
        need_nodes = ["exec_report"] + (["test_report"] if args.will_browser_test == 1 else [])
        miss_deliv = []
        for n in need_nodes:
            dv = (deliveries.get(n) or {}).get("delivery")
            if dv == "local":
                continue
            miss_deliv.append(n)          # 无任何交付记录 = 疑似只落 markdown / 未经 emit-report.py
        if miss_deliv:
            rec("报告交付(local，经 emit-report.py)", False,
                f"无交付记录：{', '.join(miss_deliv)} — 须经 emit-report.py 产 SPA 并登记交付（严禁只落 markdown + 手搓通知）")
        else:
            rec("报告交付(local，经 emit-report.py)", True, "")

    # 3d. ★ 报告不可变性校验：扫本版**全部**已 finalize 的 build（不限当前 build、不限 stage——
    #     篡改往往发生在该 build 早已不是 current_build 之后）。
    #     判据 = 内容摘要，⛔ 不用文件 mtime（新 clone / 换机 / 切分支都会刷新 mtime，历史 build 会被整批误判）：
    #       · data 内嵌 `_integrity` 缺失 → 疑似手写/删摘要；
    #       · 按内容重算摘要 ≠ 内嵌摘要 → 手改未同步摘要；
    #       · baseline `report_deliveries.<build>.<node>.integrity` 有记录且 ≠ 内嵌摘要，
    #         又没有晚于 finalize 的 amendments[] 留痕 → 改完连摘要一起重算（绕过内嵌校验）。
    bl = _load_json(os.path.join(root, args.baseline))
    builds = (((bl.get("versions") or {}).get(V) or {}).get("builds")) or []
    _deliv_all = bl.get("report_deliveries") or {}
    _tampered_all, _checked_builds = [], 0
    for b_entry in builds:
        if not isinstance(b_entry, dict):
            continue
        _b = b_entry.get("build")
        fin_at = b_entry.get("ai_report_finalized_at")
        if not (_b and b_entry.get("ai_report_finalized") and fin_at):
            continue
        _checked_builds += 1
        for df, node in ((os.path.join(rpt_ai, "data", f"{_b}.js"), "exec_report"),
                         (os.path.join(rpt_test, "data", f"{_b}.js"), "test_report")):
            if not os.path.isfile(df):
                continue
            _pl, _perr = _extract_payload(df)
            if not isinstance(_pl, dict):
                _tampered_all.append(os.path.relpath(df, root) + "（无法解析）")
                continue
            embedded = _pl.get("_integrity")
            core = {k: v for k, v in _pl.items() if k != "_integrity"}
            recomputed = "sha256:" + hashlib.sha256(json.dumps(
                core, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            recorded = ((_deliv_all.get(_b) or {}).get(node) or {}).get("integrity")
            _am = _pl.get("amendments")
            has_amend = isinstance(_am, list) and any(
                isinstance(x, dict) and str(x.get("at") or x.get("amended_at") or "") > str(fin_at)
                for x in _am)
            why = ""
            if not embedded:
                why = "缺 _integrity 摘要"
            elif recomputed != embedded:
                why = "内容与内嵌摘要不符"
            elif recorded and recorded != embedded and not has_amend:
                why = "摘要与交付台账记录不符且无 amendments[] 留痕"
            if why:
                _tampered_all.append(f"{os.path.relpath(df, root)}（{why}）")
    if _checked_builds:
        rec("报告不可变性(finalize 后 data 未被二次篡改)", not _tampered_all,
            (f"本版 {_checked_builds} 个已 finalize 的 build 的报告 data 均未被二次改动"
             if not _tampered_all else
             f"finalize 后 data 被改动：{', '.join(_tampered_all)} "
             f"— 报告一经冻结即不可改，任何结论变化须铸新 build 复测（禁回写旧 build；"
             f"如确为修正笔误须经 emit-report.py --force-amend 留痕）"))

    # 3e. ★ 部署覆盖度（半截部署）——本 build 前端有改动却无前端部署证据 → FAIL（仅 --stage final）。
    #     autopilot Phase 3.4 step1.4 写 frontend_changed（本 build code/frontend/ 是否有改动）、
    #     Phase 3.2.1 Step D 情形③前端产物特征探针通过写 frontend_deploy_verified。二者读 baseline b_entry。
    #     信号缺失（frontend_changed 未标记 = None）→ 跳过，不误判（无分端部署声明的项目不受影响）。
    if args.stage == "final":
        bl2 = _load_json(os.path.join(root, args.baseline))
        builds2 = (((bl2.get("versions") or {}).get(V) or {}).get("builds")) or []
        be2 = next((b for b in builds2 if isinstance(b, dict) and b.get("build") == B), {})
        fe_changed = be2.get("frontend_changed")
        fe_verified = be2.get("frontend_deploy_verified")
        if fe_changed is True and fe_verified is not True:
            rec("部署覆盖度(前端有改动须有前端部署证据)", False,
                "本 build 前端有改动但无前端产物特征探针证据 = 半截部署风险（后端部署了、前端产物没换）；"
                "回 Phase 3.2.1 Step D 情形③前端探针，或据 deploy_ends.frontend 触发前端部署后复跑本门")
        elif fe_changed is True and fe_verified is True:
            rec("部署覆盖度(前端有改动且已验证部署)", True, "")

    # 3f. ★ 可决策跳过留痕上浮（"留痕跳过"是低阻力路径，AI 会优先走）——区分两类跳过：
    #     技术性不可用(凭据失效/服务不可达)=合规留痕跳过；存在用户可决策替代(手工建/换部署方式/等待)
    #     =第二类，收尾必须显式上浮、不静默记进 activeContext。autopilot/version 记 baseline
    #     builds[].decidable_skips[]，本门只负责"不让它静默"（DEGRADE 上浮，不硬失败——无人值守由
    #     上游转 needs_human，交互式须逐项确认），无第二类跳过则不加噪音行。
    if args.stage == "final":
        bl3 = _load_json(os.path.join(root, args.baseline))
        builds3 = (((bl3.get("versions") or {}).get(V) or {}).get("builds")) or []
        be3 = next((b for b in builds3 if isinstance(b, dict) and b.get("build") == B), {})
        # ★ **两层都读**：写方按「有 current_build 落 build 级、没有才回落版本级」。
        #   ⛔ 只读 build 级是此前的实际状态，而 `/sprint-dev` 的写方落的是**版本级** ——
        #   两条路径完全不相交，于是「无人值守替人选了 patch」这件事**永不上浮**
        #   （写了、也读了，只是读写的不是同一个地方；产物上与"从没跳过"完全同形）。
        _vn3 = ((bl3.get("versions") or {}).get(V)) or {}
        dskips = list(be3.get("decidable_skips") or []) + list(_vn3.get("decidable_skips") or [])
        if dskips:
            rec("可决策跳过需人工确认(非技术性不可用)", True,
                f"本版有 {len(dskips)} 项存在可决策替代却被跳过：{'; '.join(str(s) for s in dskips)} "
                "— 交互式须逐项确认、无人值守应转 needs_human，不得静默记 activeContext", degrade=True)

    # 3g/3h. ★ 报告内容契约合规 + 渲染冒烟（仅 --stage final）——堵"闸门说 OK、人看到白屏/10000%/满屏 undefined"。
    #        1~3f 只查文件存在/注册/交付，查不出"打开是空白"。3g 复用 emit-report.validate_payload 查数据契约（单一信源）；
    #        3h 用 node + report_render_smoke.js 真渲染断言（无未捕获异常/innerHTML>500/无 undefined·NaN/无 ≥1000%）。
    #        无 node → DEGRADE 不阻断纯 python 环境。FAIL 会让本门 exit 1 → 阻断 finalize（不写 report_deliveries、不发 #3）。
    if args.stage == "final":
        _targets = [("exec", os.path.join(root, "docs", "reports", V, "AI执行报告"))]
        if args.will_browser_test == 1:
            _targets.append(("test", os.path.join(root, "docs", "reports", V, "AI测试报告")))
        _validate = _load_validate_payload()
        _node = shutil.which("node")
        _smoke = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report_render_smoke.js")
        for _kind, _rdir in _targets:
            _djs = os.path.join(_rdir, "data", f"{B}.js")
            if not os.path.isfile(_djs):
                continue  # 该报告不存在（如无浏览器测试的 test）→ SPA 存在性由 3b 管，不在此重复
            # 3g 数据契约合规
            if _validate is None:
                rec(f"报告数据契约合规({_kind})", True, "无法加载 emit-report.validate_payload → 跳过", degrade=True)
            else:
                _p, _e = _extract_payload(_djs)
                if _e:
                    rec(f"报告数据契约合规({_kind})", False, f"data/{B}.js 无法解析：{_e}")
                else:
                    _errs = _validate(_kind, _p)
                    rec(f"报告数据契约合规({_kind})", not _errs,
                        "" if not _errs else (f"{len(_errs)} 项不符契约：" + "；".join(_errs[:6])
                        + (" …" if len(_errs) > 6 else "") + f"（修 data/{B}.js 后重跑 emit-report.py）"))
            # 3h 渲染冒烟
            if not _node or not os.path.isfile(_smoke):
                rec(f"报告渲染冒烟({_kind})", True, "无 node 或缺 report_render_smoke.js → DEGRADE（纯 python 环境不阻断）", degrade=True)
                continue
            try:
                _r = subprocess.run([_node, _smoke, _rdir, B], capture_output=True, text=True, timeout=60)
                _out = {}
                _lines = (_r.stdout or "").strip().splitlines()
                if _lines:
                    try:
                        _out = json.loads(_lines[-1])
                    except ValueError:
                        _out = {}
                if _r.returncode == 0:
                    rec(f"报告渲染冒烟({_kind})", True, "")
                else:
                    _d = []
                    if _out.get("threw"):
                        _d.append("渲染抛异常(白屏)：" + str(_out["threw"]).split(chr(10))[0])
                    if _out.get("len", 999) <= 500:
                        _d.append(f"#view-build 过短({_out.get('len')})=疑似白屏")
                    if _out.get("undefinedCount"):
                        _d.append(f"字面量 undefined ×{_out['undefinedCount']}")
                    if _out.get("nanCount"):
                        _d.append(f"NaN ×{_out['nanCount']}")
                    if _out.get("bigPct"):
                        _d.append("≥1000% 百分比：" + ",".join(_out["bigPct"]))
                    rec(f"报告渲染冒烟({_kind})", False,
                        ("；".join(_d) or "渲染断言未通过") + f"（修 data/{B}.js 字段/单位/结构后重跑 emit-report.py）")
            except subprocess.TimeoutExpired:
                rec(f"报告渲染冒烟({_kind})", True, "渲染冒烟超时 → DEGRADE 不阻断", degrade=True)
            except OSError as _ex:
                rec(f"报告渲染冒烟({_kind})", True, f"渲染冒烟执行异常 → DEGRADE：{_ex}", degrade=True)

    # 3i. ★ 报告 driver 字段如实性（仅 --stage final + 浏览器测试轮）——堵**报告失真**。
    #     3g 查的是"字段合不合契约"（driver 值在不在枚举里），**查不出"填的是不是真的"**：
    #     填 `cli` 而实际走 MCP，契约校验照样全绿。而报告失真比测试失败严重得多——测试失败
    #     还能看见，失真是把错误结论伪装成正确结论（真实事故：下游两轮报告 driver 均填 cli
    #     与实际不符）。故本项**不比对报告内部**，而是拿报告的自述去对**运行时留下的独立记录**：
    #       · 报告自述 = data/{BUILD}.js 的 payload["driver"]（emit-report 的输入）
    #       · 运行时记录 = baseline builds[].driver_actual（由 /sprint-aiauto-test 在**驱动选定那一刻**
    #         写盘，早于测试执行、更早于出报告 —— 事后无法用"改报告"抹平二者不一致）
    #     ⚠️ 缺 driver_actual 只 DEGRADE 不 FAIL：老 build 与命令端未落值时不该被硬阻断；
    #        但必须**响**——否则这道门在"没人写记录"时会静默地什么都不校。
    #     ★ **不再限 `--stage final`**：唯一的 final 门跑在测试链路 Phase 3.7，而该 Phase 在
    #        `CONVERGED=0`（未收敛轮）时**整步跳过** ⇒ 未收敛轮已产出的中间测试报告
    #        一次都不过如实性比对，而它同样会被人看、被下一轮当基准。
    #        前移的**前提是第二信源已存在**：`driver_actual` 在「驱动选定那一刻」写盘，
    #        没写就说明测试链路还没走到那步 —— 此时报告里的 driver 本就无从比对，
    #        故 skeleton 阶段缺 `driver_actual` 直接**跳过**（⛔ 不 DEGRADE 刷屏、更不假红）。
    #        ⛔ 同期的 3p/3q **刻意不前移**：骨架期报告 `cases[]` 恒空，3q 会把
    #        「上轮 block 一条都没复评」判成必然成立 —— 那是假红，不是缺口。
    if args.will_browser_test == 1 and (args.stage == "final" or _has_driver_actual(root, args.baseline, V, B)):
        _tdjs = os.path.join(root, "docs", "reports", V, "AI测试报告", "data", f"{B}.js")
        if os.path.isfile(_tdjs):
            _bl4 = _load_json(os.path.join(root, args.baseline)) or {}
            _blds4 = (((_bl4.get("versions") or {}).get(V) or {}).get("builds")) or []
            _be4 = next((b for b in _blds4 if isinstance(b, dict) and b.get("build") == B), {})
            _actual = (_be4 or {}).get("driver_actual")
            _p4, _e4 = _extract_payload(_tdjs)
            _claim = (_p4 or {}).get("driver") if not _e4 else None
            _waiver = str((_be4 or {}).get("driver_actual_waiver") or "").strip()
            _evid = str((_be4 or {}).get("driver_downgrade_evidence") or "").strip()
            if not _actual:
                # ⛔ 此处曾是 DEGRADE（"老 build 未落值不该硬阻断"），但**缺值恰恰就是最该拦的形态**：
                #    "压根没用浏览器测、却交了一份测试报告"留下的正是空 driver_actual（下游实测：
                #    执行体撞 MCP 报错后改用 curl+JDBC 跑完 29 条，driver_actual 全程没人写）。
                #    能走到这里说明 AI测试报告 data 已存在 = 这一轮确实产出了测试结论，
                #    而 driver_actual 是在**驱动选定那一刻**（早于测试执行）写的——报告都出了却没有它，
                #    只有一种解释：驱动选定环节根本没走。老 build 不受影响：本门只校当前 --build。
                rec("报告driver如实性", bool(_waiver),
                    f"driver={_waiver} 豁免留痕" if _waiver else
                    f"⛔ 已产出 AI测试报告 data/{B}.js，却无 baseline builds[{B}].driver_actual"
                    f"（报告自述 driver={_claim or '(无)'}）——驱动选定环节未走过。"
                    f"正确动作：跑 `python3 .aidp/scripts/chrome-mcp-doctor.py check-cli` 选定驱动并写盘；"
                    f"若确有不可抗原因，须写 builds[].driver_actual_waiver 说明理由")
            elif str(_actual) not in BROWSER_DRIVERS and not _evid:
                # ★ 非浏览器驱动（curl / jdbc / http …）= 降级出了浏览器测试的范畴，必须举证。
                #   下游实测：撞 "Missing X server" 就断定"浏览器不可用"改跑 curl+JDBC，
                #   而该报错**根本不构成**浏览器不可用（见 chrome-mcp-doctor.py explain-error）。
                rec("报告driver如实性", False,
                    f"⛔ driver_actual={_actual} 不是浏览器驱动（白名单：{', '.join(BROWSER_DRIVERS)}），"
                    f"且无 builds[].driver_downgrade_evidence 举证。"
                    f"先跑 `chrome-mcp-doctor.py explain-error --error '<原始报错>'`——"
                    f"verdict=not-a-blocker 的报错**禁止**据此降级；"
                    f"确属环境不具备则把 `check-cli` 完整输出写进 driver_downgrade_evidence，"
                    f"且 UI 类用例只能记 not-run、不得记 block")
            elif _e4:
                rec("报告driver如实性", False, f"AI测试报告 data/{B}.js 无法解析：{_e4}")
            elif not _claim:
                rec("报告driver如实性", False,
                    f"运行时实际使用 driver={_actual}，但报告 data/{B}.js 未写 driver 字段")
            elif str(_claim) != str(_actual):
                rec("报告driver如实性", False,
                    f"⛔ 报告失真：报告自述 driver={_claim}，运行时实际 driver={_actual}"
                    f"（以运行时记录为准；修 data/{B}.js 后重跑 emit-report.py，"
                    f"若是运行时记录写错则先查 /sprint-aiauto-test 驱动选定环节）")
            else:
                rec("报告driver如实性", True, f"driver={_actual} 与运行时记录一致")

    # 3j/3k/3l. ★★ 本轮义务清算（仅 --stage final）——补上"只校产物存在、不校义务了结"的真空。
    #     1~3i 全在问"东西产出来没有"，没有一项问"**本轮欠下的事办了没有**"。于是出现两种
    #     荒诞态，两个下游各撞一种：
    #       · 手里攥着未处置的可自动修复缺陷，收尾门照样 PASS → 执行体自然认为"流程已完备、
    #         剩下的该问人了"，转头弹窗问用户「这条缺陷怎么处置：现在修/下版修/只修不复测」
    #         —— 直接违反「修不修从来不是选项」铁律，而闸门一声不吭。
    #       · run_state.pending_actions 挂着「外部依赖未就绪（需用户确认）」7 小时没人管，收尾照过。
    #     `invariants` 早就规定 pending_actions 非空 = 本 Phase 未完成，只是从没有东西拦收尾。
    #     本段把这三条纪律落到脚本里（与本文件自己强调的"强制性要结构级、不是自律级"一致）。
    if args.stage == "final":
        _bl5 = _load_json(os.path.join(root, args.baseline)) or {}
        _v5 = ((_bl5.get("versions") or {}).get(V)) or {}
        _blds5 = _v5.get("builds") or []
        _be5 = next((b for b in _blds5 if isinstance(b, dict) and b.get("build") == B), {})

        # 3j0 用例台账：实测时仍有未级联的用例增量（case_ledger_pending>0）= 跑的是老用例集，
        #     结论不能判「通过」—— 上浮 DEGRADE 让它可见（不冻结：级联收口后下一轮自然恢复）。
        try:
            _clp = int(_v5.get("case_ledger_pending") or 0)
        except (TypeError, ValueError):
            _clp = 0
        if _clp > 0:
            rec("用例台账已级联", True,
                f"case_ledger_pending={_clp}：本轮实测未覆盖尚未级联的用例增量，结论不代表最新用例集",
                degrade=True)

        # 3j 缺陷清算：仍挂着「可自动修复类」缺陷 → 必须已走完闭环（或显式冻结），不得就此收尾。
        #    判据用 auto_fixable_pending：测试链路对每条缺陷按 /sprint-bugfix「缺陷处置默认决策
        #    纪律」二分后，可自动修复类即置真；它到 final 门还为真 = 闭环没跑。
        #    ⚠️ needs_human 冻结是**合法**出口（转人工留痕，不是静默放过）→ 放行但记 DEGRADE 上浮。
        if _v5.get("auto_fixable_pending") is True:
            if _v5.get("needs_human") is True:
                rec("本轮缺陷清算", True,
                    "仍有可自动修复缺陷，但已 needs_human 冻结转人工（合法出口，收尾放行但须人工接手）",
                    degrade=True)
            else:
                rec("本轮缺陷清算", False,
                    "⛔ 仍挂着未处置的【可自动修复类】缺陷（auto_fixable_pending=true）却在收尾："
                    "该走「自动修复→重部署→铸新 build→复测」闭环（见 sprint-autopilot「测试失败自动"
                    "修复复测闭环」）。⛔ 严禁改为弹 AskUserQuestion 问用户修不修/何时修 —— "
                    "「修不修从来不是选项」；确实修不动才走冻结转人工（置 needs_human 留痕）")
        else:
            rec("本轮缺陷清算", True, "")

        # 3m ★ 缺陷复验闭环（实际项目实测缺口）：3j 只问"缺陷有没有【登记】"，
        #    不问"有没有【闭环】"。实证：defects[] 两条都明写「已修复，⚠️ 待 build1002 复验」，
        #    3j 因 auto_fixable_pending 已被 step 2「先记账再动手」置 false 而放行，收尾门整体 PASS
        #    ——「带着未复验的 P1 缺陷正常收尾」由此成为唯一没被机器门覆盖的收尾姿势。
        #    判据纯确定性、无需新采集：报告里存在"待复验"字样的缺陷 ⟹ 必须已铸出后继 build 承接复测。
        #    ⚠️ 不只看 status 字段：defects[] 在报告契约里只声明为 list、元素字段自由，
        #       真实写法把"待复验"塞在 status / fix / note 都出现过，故按【整条序列化后】匹配。
        _dj = os.path.join(rpt_ai, "data", f"{B}.js")
        _pl, _perr = _extract_payload(_dj)
        _pending_defects = []
        if _pl:
            for _d in (_pl.get("defects") or []):
                if PENDING_RETEST_RE.search(json.dumps(_d, ensure_ascii=False)):
                    _pending_defects.append(_d.get("id") or _d.get("title") or "(无 id)")
        if _pending_defects:
            # 后继 build = 显式 retest_of==B，或 build 序号大于本 build（铸新 build 复测的两种落法）
            _succ = [b.get("build") for b in _blds5
                     if isinstance(b, dict) and b.get("build") and b.get("build") != B
                     and (b.get("retest_of") == B or _build_seq(b.get("build")) > _build_seq(B))]
            if _succ:
                rec("缺陷复验闭环", True,
                    f"{len(_pending_defects)} 条待复验缺陷已由后继 build {'、'.join(_succ)} 承接")
            elif _v5.get("needs_human") is True:
                rec("缺陷复验闭环", True,
                    f"{len(_pending_defects)} 条待复验缺陷未复测，但已 needs_human 冻结转人工"
                    f"（合法出口，人工接手）", degrade=True)
            else:
                rec("缺陷复验闭环", False,
                    f"⛔ 报告里 {len(_pending_defects)} 条缺陷标着待复验"
                    f"（{'、'.join(str(x) for x in _pending_defects[:3])}"
                    f"{'…' if len(_pending_defects) > 3 else ''}），却既没铸后继 build 复测、"
                    f"也没冻结转人工 —— 「铸新 build 出复测报告」是【自动仪式】不是选项，"
                    f"⛔ 严禁输出「建议下一步：铸 buildNNNN 复验」这类把仪式当选项交回用户的收尾"
                    f"（交互式单次同样由本次调用在本轮内跑完，见命令正文 P0-4）")
        else:
            rec("缺陷复验闭环", True, "" if _pl else f"报告 data 未能解析（{_perr}），本项跳过")

        # 3p ★ 缺陷分流完整性（实际项目实测缺口）：3j 问的是「可自动修复类有没有
        #    走完闭环」、3m 问的是「标了待复验的有没有后继 build 承接」—— 两道门都**预设缺陷已经
        #    被分流过**。而「一条都没分流」恰好让两道门同时静默通过：`auto_fixable_pending` 不置真
        #    （3j 放行）、报告里也没有"待复验"字样（3m 放行）。实证：执行体把两条缺陷笼统判成
        #    "需要产品决策"报给用户等人，收尾门全绿——其中一条是纯技术缺陷（部门筛选口径不同源），
        #    根本不需要任何产品输入。⇒ 「从未分流」与「分流完毕」在机器看来完全同形。
        #    本项把「每条缺陷都必须落到三档之一」变成结构级判定：
        #      · auto-fix      → `auto_fixable_pending=true`（批次语义，后续由 3j / 3m 接管闭环）
        #      · needs-product → `versions.{V}.pending_clarifications[]` 有条目且**每条 question 非空**
        #      · wont-fix      → 该缺陷条目自带显式不修标记
        #    ⛔ `question` 为空 / 只写"需要产品确认"一律 FAIL —— 那正是本缺口的伪装形态：
        #       写不出「具体要产品回答什么」，就是它其实不需要产品输入的证据
        #       （判据单一信源 = `/sprint-bugfix`「必须问」正向白名单，约定 21 不复述）。
        _defects = [d for d in ((_pl or {}).get("defects") or []) if isinstance(d, dict)]
        _pcs = [c for c in (_v5.get("pending_clarifications") or []) if isinstance(c, dict)]
        _pc_blob = json.dumps(_pcs, ensure_ascii=False)
        _blank_q = [str(c.get("question") or "").strip() for c in _pcs]
        _vague_q = [q for q in _blank_q
                    if not q or VAGUE_QUESTION_RE.fullmatch(q.strip(" 。.！!？?"))]
        if _pcs and _vague_q:
            rec("缺陷分流完整性", False,
                f"⛔ pending_clarifications[] 有 {len(_vague_q)} 条没写「具体要产品回答什么」"
                f"（{'、'.join(repr(q) for q in _vague_q[:2])}）—— 空泛的「需要产品确认」不接受："
                f"写不出那个问句，就是这条其实不需要产品输入、该按默认处置直接修的证据"
                f"（见 /sprint-bugfix「必须问」正向白名单）")
        elif not _defects:
            rec("缺陷分流完整性", True,
                "" if _pl else f"报告 data 未能解析（{_perr}），本项跳过")
        elif _v5.get("auto_fixable_pending") is True:
            rec("缺陷分流完整性", True,
                f"{len(_defects)} 条缺陷已按批次归入 auto-fix（闭环由 3j / 3m 接管）")
        else:
            _unsorted = []
            for _d in _defects:
                _blob = json.dumps(_d, ensure_ascii=False)
                _did = str(_d.get("id") or _d.get("title") or "").strip()
                if WONT_FIX_RE.search(_blob):
                    continue                       # wont-fix：显式不修
                if PENDING_RETEST_RE.search(_blob):
                    continue                       # auto-fix 已修待复验：归 3m 管
                if _did and _did in _pc_blob:
                    continue                       # needs-product：被某条待澄清点名
                _unsorted.append(_did or "(无 id)")
            if not _unsorted:
                rec("缺陷分流完整性", True,
                    f"{len(_defects)} 条缺陷均已落到三档之一"
                    f"（待澄清 {len(_pcs)} 条，其余为 wont-fix / 已修待复验）")
            elif len(_unsorted) == len(_defects):
                rec("缺陷分流完整性", False,
                    f"⛔ 报告里 {len(_defects)} 条缺陷**一条都没进分流**"
                    f"（{'、'.join(_unsorted[:3])}{'…' if len(_unsorted) > 3 else ''}）："
                    f"既没置 auto_fixable_pending、也没记 pending_clarifications、"
                    f"更没标 wont-fix。⛔ 严禁用一句「需要产品决策」笼统盖住整批缺陷 —— "
                    f"逐条按 /sprint-bugfix「缺陷处置默认决策纪律」分流，"
                    f"四条「必须问」白名单都不满足的一律默认修")
            else:
                rec("缺陷分流完整性", True,
                    f"⚠️ {len(_defects)} 条缺陷中 {len(_unsorted)} 条未见归档"
                    f"（{'、'.join(_unsorted[:3])}{'…' if len(_unsorted) > 3 else ''}）—— "
                    f"请确认它们确已分流；批量 auto-fix 请置 auto_fixable_pending", degrade=True)

        # 3q ★ 上一轮 block 必须在复测轮被复评（实际项目实测缺口）：
        #    每轮测试各自独立跑，**没有任何东西要求它回头看上一轮标了 block 的用例**。
        #    实证：build1001 标了 13 条 block（原因全是 `precondition-unmet`），其中 7 条其实
        #    造个数就能解锁——若无人质问，这 13 条会**原样沉淀**到后续所有 build，
        #    「这条真的造不出」与「执行体没去造」在机器上完全同形。
        #    判据（只在复测轮生效、纯确定性）：本 build 有 `retest_of` ⇒ 上一 build 报告里
        #    `result == "block"` 的用例，**必须在本轮报告的 cases[] 里出现**（无论复评结论是
        #    仍 block 还是已解锁）。整条没出现 = 没复评。
        _retest_of = _be5.get("retest_of")
        if _retest_of and _pl:
            _prev = {str(c.get("id") or "").strip(): c
                     for c in _report_cases(root, V, _retest_of)
                     if str(c.get("result") or "").lower() == "block"}
            _prev.pop("", None)
            _cur = {str(c.get("id") or "").strip(): c
                    for c in (_pl.get("cases") or []) if isinstance(c, dict)}
            _absent, _mute, _verbatim = [], [], []
            for _cid, _pc in _prev.items():
                _cc = _cur.get(_cid)
                if _cc is None:
                    _absent.append(_cid)             # 整条没出现 = 本轮压根没碰它
                    continue
                if str(_cc.get("result") or "").lower() != "block":
                    continue                          # 已解锁 → 有实际执行结果，复评完成
                _note = str(_cc.get("note") or "").strip()
                if not _note:
                    _mute.append(_cid)                # 仍 block 却一个字理由都没有 = 原样沉淀
                elif _note == str(_pc.get("note") or "").strip():
                    _verbatim.append(_cid)            # 理由与上轮逐字相同 → 可能是照抄
            if not _prev:
                rec("上轮 block 复评", True, f"上一 build {_retest_of} 无 block 用例，无需复评")
            elif _absent or _mute:
                rec("上轮 block 复评", False,
                    f"⛔ 上一 build {_retest_of} 的 {len(_prev)} 条 block 未被复评："
                    + (f"{len(_absent)} 条在本轮报告里完全没出现"
                       f"（{'、'.join(_absent[:4])}{'…' if len(_absent) > 4 else ''}）；"
                       if _absent else "")
                    + (f"{len(_mute)} 条仍判 block 却没写任何理由"
                       f"（{'、'.join(_mute[:4])}{'…' if len(_mute) > 4 else ''}）；"
                       if _mute else "")
                    + "复测轮必须对上轮每条 block 给出三选一并写进 `note`："
                    "仍 block（原因不变）/ 仍 block（原因变更，须说明）/ 已解锁→实际执行结果。"
                    "⛔ 不复评 = 上轮 block 原样沉淀到后续所有 build，"
                    "「这条真的造不出」与「执行体没去造」从此分不开")
            elif _verbatim:
                rec("上轮 block 复评", True,
                    f"⚠️ {len(_prev)} 条上轮 block 已复评，但其中 {len(_verbatim)} 条的理由与上轮"
                    f"**逐字相同**（{'、'.join(_verbatim[:4])}{'…' if len(_verbatim) > 4 else ''}）—— "
                    f"「原因不变」是合法结论，但请确认这是复评后的判断而非照抄上轮", degrade=True)
            else:
                rec("上轮 block 复评", True,
                    f"上一 build {_retest_of} 的 {len(_prev)} 条 block 已全部复评")

        # 3n ★ 测试结果挂靠用例基线（约定 33 —— 「规划期基线产出即沉睡」的确定性拦截）
        #    实证（实际项目）：本轮用自造的 P01~P05 编号记测试证据，
        #    12 条设计用例里 8 条挂空、1 条 ID 张冠李戴，而收尾门 15 项**全绿放行**。
        #    约定 33 要防的正是这个形态：规划期强制产出用例基线，测试期却不以它为基准逐项断言，
        #    于是"基线产出即沉睡"——卡片该删没删、列漏渲染、统计口径错，AI 测试照样全绿。
        #    此前只靠 version-auditor 的语义判断兜着，没有任何确定性检查。
        #
        #    判据分两档，刻意不做成单一阈值（单阈值要么假红要么抓不住）：
        #      · **交集为 0**（两边都非空）= 报告用的是**自造编号**、根本没挂靠基线 → FAIL。
        #        这个信号零假红风险：只要真按 TC-* 记，交集不可能是空。
        #      · 交集非空但**未覆盖率 > 阈值** → DEGRADE 告警。本轮只跑部分用例是合法的
        #        （冒烟、复验轮），所以不阻断——但要让"8/12 挂空"这种量级看得见。
        if args.will_browser_test == 1 and _pl:
            _rep_ids = {str(c.get("id") or "").strip()
                        for c in (_pl.get("cases") or []) if isinstance(c, dict)}
            _rep_ids.discard("")
            _base_ids, _base_dirs = set(), []
            for _sub in ("正式用例", "研发自测"):
                _d0 = os.path.join(root, "docs", "testing", V, _sub)
                if not os.path.isdir(_d0):
                    continue
                _base_dirs.append(_sub)
                for _dp, _dn, _fns in os.walk(_d0):
                    for _fn in _fns:
                        if not _fn.endswith(".md"):
                            continue
                        try:
                            _txt = open(os.path.join(_dp, _fn), encoding="utf-8",
                                        errors="replace").read(400_000)
                        except OSError:
                            continue
                        _base_ids |= set(re.findall(r"\bTC-[A-Za-z0-9_\-]+", _txt))
            if not _base_ids:
                rec("测试结果挂靠用例基线", True,
                    f"用例库无 TC-* 基线（扫 docs/testing/{V}/{{{','.join(_base_dirs) or '正式用例,研发自测'}}}），本项跳过")
            elif not _rep_ids:
                rec("测试结果挂靠用例基线", False,
                    f"⛔ 用例库有 {len(_base_ids)} 条 TC-* 基线，报告 cases[] 却一个 id 都没有 —— "
                    f"约定 33：规划期基线必须被测试期逐项断言，否则「产出即沉睡」")
            else:
                _hit = _rep_ids & _base_ids
                _uncov = len(_base_ids - _rep_ids)
                _rate = _uncov / len(_base_ids)
                if not _hit:
                    rec("测试结果挂靠用例基线", False,
                        f"⛔ 报告 cases[] 的 {len(_rep_ids)} 个 id（{'、'.join(sorted(_rep_ids)[:3])}…）"
                        f"与用例库 {len(_base_ids)} 条 TC-* **交集为 0** —— 这是自造编号、没挂靠基线。"
                        f"约定 33 要求以基线为基准逐项断言；请把 cases[].id 改成用例库里的 TC-* 编号")
                elif _rate > 0.5:
                    rec("测试结果挂靠用例基线", True,
                        f"⚠️ 基线 {len(_base_ids)} 条中 {_uncov} 条未被本轮报告覆盖"
                        f"（未覆盖率 {_rate:.0%}）—— 本轮若非冒烟/复验轮，请补齐断言", degrade=True)
                else:
                    rec("测试结果挂靠用例基线", True,
                        f"报告 {len(_rep_ids)} 条 × 基线 {len(_base_ids)} 条，命中 {len(_hit)}，"
                        f"未覆盖 {_uncov}（{_rate:.0%}）")

        # 3o ★ 本轮增量用例真被执行到（约定 22 用例族级联 × 全量执行 的交界）
        #    AI 测试**每轮跑全量**（这是对的：增量改动最容易打破既有功能）。但级联进来的新用例
        #    在 `02_*.md` 里与三个月前那批长得一模一样，于是「114 条全绿」**证明不了**本轮
        #    那 5 条新功能被覆盖过 —— 而那恰恰是最需要被证明的部分。
        #    两个静默失败态本项各拦一个：
        #      · 级联写进了用例册，但**用例发现没收到它**（glob 漏、路径错、册子没提交）
        #        → 增量 ID 一条都不在报告 cases[] 里，而通过率照样 100%；
        #      · 报告压根没带 incrementalCaseIds → 事后无从核对"本轮增量是哪几条"。
        #    ⛔ 交集为 0 判 FAIL（零假红：真跑了不可能一条都不在）；部分命中判 DEGRADE
        #    （本轮可能是冒烟/复验轮，不阻断，但量级要看得见）。
        if args.will_browser_test == 1 and _pl:
            _inc = _be5.get("incremental_case_ids")
            if isinstance(_inc, list) and _inc:
                _inc_set = {str(x).strip() for x in _inc if str(x).strip()}
                _rep2 = {str(c.get("id") or "").strip()
                         for c in (_pl.get("cases") or []) if isinstance(c, dict)}
                _rep2.discard("")
                _hit2 = _inc_set & _rep2
                if not _pl.get("incrementalCaseIds"):
                    rec("本轮增量用例可核对", False,
                        f"⛔ baseline 记着本轮 {len(_inc_set)} 条增量用例，报告 data 却没写 "
                        f"incrementalCaseIds —— 事后无从核对增量是否被覆盖"
                        f"（该字段由 emit-report.py 自动注入，缺失说明 baseline 或注入链断了）")
                elif not _hit2:
                    rec("本轮增量用例可核对", False,
                        f"⛔ 本轮 {len(_inc_set)} 条增量用例（{'、'.join(sorted(_inc_set)[:3])}…）"
                        f"在报告 cases[] 里**一条都没有** —— 级联写进了用例册，执行却没收到它。"
                        f"通过率再高也不含这些新功能。查：用例发现 glob 是否漏收 / 册子是否已提交")
                elif len(_hit2) < len(_inc_set):
                    rec("本轮增量用例可核对", True,
                        f"⚠️ 本轮 {len(_inc_set)} 条增量用例只跑到 {len(_hit2)} 条"
                        f"（缺 {'、'.join(sorted(_inc_set - _hit2)[:3])}…）—— 冒烟/复验轮属正常，"
                        f"完整轮请补齐", degrade=True)
                else:
                    rec("本轮增量用例可核对", True,
                        f"本轮 {len(_inc_set)} 条增量用例全部在报告中")

        # 3k pending_actions 非空 = 本 Phase 按不变式定义就没完成，不得收尾。
        #   ⛔⛔ **必须排除本门自己**：门 FAIL 时收尾分片会写 `--pending "ceremony-gate"` 留痕，
        #      若把它也算进来就成了**死锁**——3k 因这一项恒 FAIL → 永远走不到清空它的成功分支 →
        #      `dev_fail_streak` 3 tick 达阈冻结，**即使原本缺失的产物早已补齐也解不开**。
        #      本门要拦的是"别的活没干完就收尾"，不是"本门上轮没过"（那个由 streak 自己管）。
        _SELF_MARKERS = {"ceremony-gate", "ceremony_gate"}
        _pa = [x for x in (((_v5.get("run_state") or {}).get("pending_actions")) or [])
               if str(x).strip() not in _SELF_MARKERS]
        rec("未完成动作已清空", not _pa,
            "" if not _pa else
            f"⛔ run_state.pending_actions 非空却在收尾：{('、'.join(map(str, _pa)))[:160]}"
            f"（invariants「阶段推进不变式」：非空 = 本 Phase 未完成）。办完并 `--pending \"\"` 清空，"
            f"或确需人工接手则显式置 needs_human 留痕，不得挂着不管")

        # 3l 结构性一致：current_build 有值而 builds[] 为空 —— 说明 build 记录压根没落盘，
        #    连带 aiauto_delegated_at / finalize 校验 / 报告不可变等一切按 build 取值的门全部空转
        #    （它们读不到条目就"没判据 → 放行"）。这不是"少个字段"，是**校验体系整体失效**。
        if _v5.get("current_build") and not _blds5:
            rec("build 记录结构一致性", False,
                f"⛔ current_build={_v5.get('current_build')} 有值但 builds[] 为空："
                f"按 build 取值的门（委派证据 / finalize 冻结 / 报告不可变 / driver 如实性）全部空转。"
                f"应由 autopilot Phase 3.1.5 铸造时同时写 build_seq + current_build + 追加 builds 条目")
        elif _v5.get("current_build") and not _be5:
            rec("build 记录结构一致性", False,
                f"⛔ current_build={_v5.get('current_build')} 在 builds[] 中无对应条目"
                f"（现有：{', '.join(str(b.get('build')) for b in _blds5 if isinstance(b, dict)) or '无'}）")
        else:
            # ★ 同一 build 号出现多条 = 字段散落在两条上，而所有读方都只取**第一条匹配**
            #   ⇒ 后写进第二条的字段（driver_actual / change_classification / aiauto_delegated_at …）
            #   对门永远不可见，表现为"明明写了却读不到"、门报"该环节没走过"（下游实证）。
            #   现有写入方（baseline_edit set current_build / 委派证据 / classify_push 补登记）
            #   都已按 build 号去重，故本项**只应在裸 read-modify-write 绕过了写入口时**才红 ——
            #   它抓的正是那种绕行，而不是正常路径。
            _seen, _dups = set(), []
            for _b in _blds5:
                if not isinstance(_b, dict):
                    continue
                _bid = str(_b.get("build") or "").strip()
                if not _bid:
                    continue
                (_dups.append(_bid) if _bid in _seen else _seen.add(_bid))
            if _dups:
                rec("build 记录结构一致性", False,
                    f"⛔ builds[] 里有重复 build 号（{'、'.join(sorted(set(_dups))[:3])}"
                    f"{'…' if len(set(_dups)) > 3 else ''}）：字段散在多条上，而读方只取第一条匹配 ⇒ "
                    f"写进后续条目的字段对所有门永远不可见。请合并为一条；"
                    f"写 build 字段一律走 `baseline_edit.py --build`（它按 build 号定位、不新增条目），"
                    f"⛔ 别裸 read-modify-write 往 builds[] 里 append")
            else:
                rec("build 记录结构一致性", True, "")

    # 4. version-auditor 终审报告 —— ★ 必须按 build 精确匹配
    #    宽松 glob（`version-output-audit*.md`）会被 `/version` 内部 version-auditor 的**同名遗留产物**
    #    静默满足：autopilot Phase 3.3 的终审明明没跑，门却因为上游早先留下的一份文件判通过。
    #    故收紧为 `version-output-audit-{BUILD}.md`（Phase 3.3 委派时显式指定该输出路径）。
    audit_exact = os.path.join(root, "docs", "audit", V, f"version-output-audit-{B}.md")
    audit_ok = os.path.isfile(audit_exact)
    legacy = [p for p in glob.glob(os.path.join(root, "docs", "audit", V, "version-output-audit*.md"))
              if os.path.basename(p) != f"version-output-audit-{B}.md"]
    rec("version-auditor 终审报告(docs/audit/%s/version-output-audit-%s.md)" % (V, B), audit_ok,
        "" if audit_ok else (
            f"回 Phase 3.3 启动 version-auditor 子 Agent 并把输出指定为该 build 专属文件名（强制仪式，--skip-audit 不豁免）"
            + (f"；注意目录下已有 {len(legacy)} 份非本 build 的终审文件（{os.path.basename(legacy[0])} 等），"
               f"那是上游 /version 的产物，**不能**当作本 build 已终审" if legacy else "")))
    if audit_ok:
        # 终审结论：读报告里的 overall（version-auditor 输出协议：pass | warn | block）。
        #   block 且本版未按契约冻结 → FAIL（Critical 未处置就收尾）；已冻结转人工 → DEGRADE；
        #   报告未标注 overall → DEGRADE（无从判断结论）。
        try:
            _atxt = open(audit_exact, encoding="utf-8", errors="replace").read()
        except OSError:
            _atxt = ""
        _m = re.search(r'["\']?overall["\']?\s*[:=]\s*["\'`]?(pass|warn|block)', _atxt, re.I)
        _ov = _m.group(1).lower() if _m else ""
        _vfz = (((_load_json(os.path.join(root, args.baseline)) or {}).get("versions") or {}).get(V)) or {}
        if _ov == "block":
            if _vfz.get("needs_human") is True:
                rec("终审结论", True, "overall=block，本版已冻结转人工（合法出口）", degrade=True)
            else:
                rec("终审结论", False, "overall=block（存在 Critical）却在收尾：须先按失败处置冻结或修复后重审")
        elif _ov in ("pass", "warn"):
            rec("终审结论", True, f"overall={_ov}")
        else:
            rec("终审结论", True, "终审报告未标注 overall（pass|warn|block），无从判断结论", degrade=True)

    # 5. 里程碑通知（台账）
    if args.notify == 0:
        # ★ 三态而非两态：sent / skipped(须举证) / missing。
        #   ⛔ 「没发」与「不需要发」在产物上完全同形——`--notify 0` 一传，整组通知就豁免了，
        #      而这个 0 可能来自「通道真的不可用」（合规），也可能来自「通道好好的，只是没去发」（违规）。
        #      实测正是后者：通知渠道配置齐全可用，整轮零通知而流程照常"完成"。
        #      故要求举证 —— baseline `notify_probe`（autopilot-preflight.py --record-probe 写）。
        #      举证显示通道当时是**可用的**，却传了 --notify 0 → 判 missing，不是 skipped。
        _blp = _load_json(os.path.join(root, args.baseline)) or {}
        _probe = _blp.get("notify_probe") or {}
        if not isinstance(_probe, dict) or not _probe:
            rec("里程碑通知", True,
                "降级为 skipped 但**无探测举证**（baseline 无 notify_probe）→ 无从判断通道当时是否可用；"
                "应在 Phase 0.0 Step 0 跑 `autopilot-preflight.py check --record-probe` 留痕",
                degrade=True)
        elif _probe.get("available"):
            rec("里程碑通知", False,
                f"⛔ 通道当时【可用】（notify_probe.available=true，探测于 {_probe.get('at') or '未知'}）"
                f"却整组跳过通知 —— 这不是合法降级，是漏发。"
                f"合法降级只有：notify.enabled=false / 无可用渠道 / 用户显式 --no-notify。"
                f"严禁以交互式 / 省时 / 避免打扰团队为由不发")
        else:
            rec("里程碑通知", True,
                f"合法降级（已举证）：通知通道不可用 —— {_probe.get('detail') or ('notify.enabled=false' if not _probe.get('enabled') else '无细节')}"
                f"（探测于 {_probe.get('at') or '未知'}）", degrade=True)
    else:
        led = _load_ledger(_ledger_path(args))
        # ★ 台账过滤须容纳「铸 build 之前发的卡」：#0/#1/#1b/#pre-* 登记时 build 为空，
        #   若严格要求 build==B 则它们永远不匹配 → 收尾门恒 missing → 每 tick FAIL → 误冻结。
        #   口径：build 相同 → 本 build 的卡；build 为空 → 本 version 的通用卡，一并计入。
        # ★ 两个口径必须分开（reporter P0-1 实证）：
        #   · **匹配口径** version_cards —— 含 build 为空的通用卡（#0/#1/#1b/#pre-* 在铸 build 前发，
        #     严格要求 build==B 会永远匹配不上 → 收尾门恒 missing → 误冻结）；
        #   · **计数口径** build_scoped —— 只认 build==B 的卡。退化判据若用匹配口径，
        #     **只要跑过版本规划就恒真**：#0/#1/#1b 三张无 build 的规划卡把"本 build 零推送"填满，
        #     于是"开发期 + 测试期一张卡都没发"照样判 PASS（实测即如此，用户只收到规划通知才发现）。
        version_cards = [c for c in led["cards"]
                         if c.get("version") == V and (c.get("build") == B or not c.get("build"))]
        build_scoped = [c for c in version_cards if c.get("build") == B]
        # ★ `status=undelivered` = 已尝试发送、渠道失败 / 无可用渠道：算「已尝试」（不判漏发），
        #   但单列 DEGRADE 上浮 —— 通知故障不能升级成流程冻结，也不能伪装成已送达。
        sent_nodes = {c.get("node") for c in version_cards}
        undelivered_nodes = {c.get("node") for c in version_cards
                             if c.get("status") == "undelivered"} - {
            c.get("node") for c in version_cards if c.get("status", "sent") == "sent"}
        # ★ P0-2：命令端没传期望集时**脚本自算**，不再把"检查有没有漏做"整个托付给
        #   `phase-3-9.md`——那个分片本身就在"可能被漏做"的路径里（实测：执行体没逐片 Read
        #   就自行推进，推导代码根本没跑，于是必然落进退化分支）。
        #   ⚠️ 自算集**刻意只取恒发通知 + 可由入参/baseline 确定的条件卡**，宁可少期望也不误报：
        #     · `#1`（规划开始）只有"本轮真跑了规划"才该期望，gate 事后无法可靠区分 → 不自算，
        #       仅当命令端显式传入时才校（命令端知道 PLANNING_DONE/FORCE_REPLAN）。
        #   故：**命令端传入 = 精确校验；脚本自算 = 漏跑兜底**，后者是下限不是上限。
        expected, _src = ([c.strip() for c in args.expect_cards.split(",") if c.strip()], "传入") \
            if args.expect_cards else (_derive_expect_cards(args, _v5_for_cards, B), "脚本自算")
        if expected:
            # ★ 分阶段豁免（时序：测试链路 Phase 3.4 发 #F → Phase 3.7 --stage final 门 → 才发 #3）：
            #   · skeleton（委派前 / 发 #F 前）：#F、#3 都尚未发 → 均豁免；
            #   · final（发 #3 之前的钢门）：#F 已发在前 → 【必须在台账、要求校验】（reporter C：至少测试结论卡 #F 要在）；#3 尚未发 → 仍豁免。
            if args.will_browser_test == 1:
                _defer = ("#3", "#F") if args.stage == "skeleton" else ("#3",)
                expected = [e for e in expected if e not in _defer]
            missing = [e for e in expected if e not in sent_nodes]
            rec(f"应发通知集已发(台账核验·{_src})", not missing,
                "" if not missing else
                f"通道可用却漏发：{', '.join(missing)}（已发：{', '.join(sorted(sent_nodes)) or '无'}）"
                f"— 严禁以交互式/避免打扰团队为由不发")
            _und = [e for e in expected if e in undelivered_nodes]
            if _und:
                rec("应发通知送达", True,
                    f"已尝试但未送达：{', '.join(_und)}（渠道失败 / 无可用渠道；详见 memory/.aidp/alerts.jsonl）",
                    degrade=True)
        # ★ 退化判据**始终跑**（不再是 else 分支）：它用 build 口径计数，与上面的逐项核验
        #   互补而非互斥 —— 逐项核验只管"该发的发了没"，本项管"这个 build 到底有没有推送过"。
        #
        # ⛔ **唯一豁免 = test-only**：通知集矩阵规定 test-only 轮次 autopilot **不发任何开发链路卡**
        #    （#1/#1b/#1c/#1d/#2/#pre-* 全不发），本 build 名下的卡数**结构上恒为 0**。
        #    不豁免就是一道必 FAIL 的门：而它恰好挡在「委派测试链路之前」——委派永远发不出去、
        #    dev_fail_streak 每 tick +1、3 tick 后按 handoff-exhausted 冻结，而该原因属 _HUMAN_ONLY
        #    永不自动解冻 ⇒ 整版停摆。本 build 的推送由测试链路 Phase 3.7 的 final 门
        #    （`--expect-cards "#D,#F"`）负责核验，此处不重复要求、也无从要求。
        if entry_mode == "test-only":
            rec("本 build 非零推送(台账≥1)", True,
                "test-only：按通知集矩阵本轮 autopilot 不发开发链路卡，本项不适用"
                "（本 build 推送由测试链路 final 门核验）", degrade=True)
            _ok = True
        else:
            _ok = len(build_scoped) > 0
            rec("本 build 非零推送(台账≥1)", _ok,
                "" if _ok else
                f"⛔ 通道可用，但台账里 build={B} 名下**零通知**"
                f"（本版另有 {len(version_cards) - len(build_scoped)} 张无 build 的通用卡，"
                f"多为版本规划期发的 #0/#1/#1b —— 它们不能证明开发期/测试期发过卡）"
                f"：疑似整轮零推送。严禁以交互式/避免打扰团队/省时为由不发")

    # ⛔ 这里【刻意不放】HANDBACK 检查项 —— 别"顺手补上"，会造出时序死结：
    #    本门（含 --stage final）在测试链路 Phase 3.7 / autopilot 3.4 step2 就跑，
    #    而 `run-state … done` 要到 phase-3-9 收尾才写。此刻 next_phase 必然还是非终态，
    #    放进来就是每轮必 FAIL 的假阳性——与当初拆 `--stage skeleton|final` 要躲的是同一类坑。
    #    HANDBACK 的正确落点是**命令返回前**的独立 `handback-check` 子命令（见其文档与
    #    invariants.md IRON-1 / 命令正文反向硬断言），那时 run_state 才是最终态。

    # ---- 输出 ----
    fail = [r for r in results if r[1] == "FAIL"]
    print("══════ /sprint-autopilot 强制仪式收尾门 ══════")
    print(f"版本 {V} · build {B} · stage={args.stage} · notify={'on' if args.notify else 'off(合法降级)'} · "
          f"will_browser_test={args.will_browser_test}({_wbt_src})")
    # ★ 应产清单（reporter ②：显式打印"本轮应产什么"，与下方逐项 ✅/❌/🟡"实产"对照，堵"静默什么都没发生"）
    _test_expect = "必产" if args.will_browser_test == 1 else "本build无浏览器测试→不产(归第二条 /loop /sprint-aiauto-test)"
    _card_expect = (f"{args.expect_cards}(传入)" if args.expect_cards
                    else ("豁免(notify=0)" if not args.notify
                          else f"{','.join(_derive_expect_cards(args, _v5_for_cards, B)) or '(空)'}(脚本自算) + 本build非零推送"))
    print(f"  📋 应产清单：build号={B} · AI执行报告=必产 · AI测试报告={_test_expect} · 里程碑通知={_card_expect}")
    print(f"  下方逐项为【实产】核验（缺项标原因 + 补产命令）：")
    icon = {"PASS": "✅", "FAIL": "❌", "DEGRADE": "🟡"}
    for name, verdict, detail in results:
        line = f"  {icon[verdict]} {name}"
        if detail:
            line += f" — {detail}"
        print(line)
    if fail:
        print(f"⛔ GATE: FAIL（{len(fail)} 项强制仪式缺失且无合法降级）→ 回对应 Phase 就地补齐、复跑本门，"
              f"通过才退出/委派；**绝不以『已做精简/交互式所以省略』收尾**")
        return 1
    print("✅ GATE: PASS（强制仪式齐全或命中唯一合法降级）")
    if args.stage == "final" and not args.no_advance_run_state:
        advance_run_state_on_final_pass(root, args.baseline, V)
    return 0


# ── 终态 PASS 后推进 run_state ────────────────────────────────────────────────
# 收尾门 PASS 了、`run_state.next_phase` 却还停在半路（下游实测停在 `3.2.1-deploy`），
# 于是 Stop hook 依据 `_handback_verdict` 继续拦着不让收工，只能人工
# `baseline_edit run-state` 推一把 —— 「仪式已全部完成」与「流程还没走完」两个信号打架，
# 而挡在出口的是后者。本函数让终态门的 PASS 结论也能落到状态机上。
#
# ⚠️ **这是让检查器去改它所检查的对象**，边界必须收紧，故有三道护栏：
#   ① 只在 `--stage final` 且**零 FAIL** 时推进（DEGRADE 属合法降级，不阻止）；
#   ② **Sprint 循环中途不推进**：`next_sprint` 非空且非终态 ⇒ 还有 Sprint 没跑完，
#      此刻置 done 会把剩下的 Sprint 丢掉 —— 宁可继续拦着，也不放走没跑完的流水线；
#   ③ 推进必须**可追责**：写 `advanced_by` / `advanced_from` / `advanced_at`，
#      并在终端大声打印。⛔ 绝不静默改状态机。
# `--no-advance-run-state` 可关闭（保持纯只读的旧行为）。
def advance_run_state_on_final_pass(root, baseline_rel, version):
    try:
        sys.path.insert(0, os.path.join(root, ".aidp", "scripts"))
        from baseline_edit import LockedBaseline   # 持 flock + 锁内重读 + 原子写回
    except ImportError as e:
        print(f"ℹ️ run_state 未推进（取不到 baseline 写入口：{e}）—— 请人工 "
              f"`baseline_edit.py --version {version} run-state --next-phase done`")
        return
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with LockedBaseline(os.path.join(root, baseline_rel), write=True) as lb:
        vn = (lb.data.setdefault("versions", {}).setdefault(version, {}))
        rs = vn.setdefault("run_state", {})
        np_ = (rs.get("next_phase") or "").strip()
        ns = (rs.get("next_sprint") or "").strip()
        if ns and ns not in DONE_STATES:
            print(f"ℹ️ run_state 未推进：next_sprint={ns!r} 仍在循环中 —— "
                  f"终态门只证明本 build 的交付齐全，不证明剩余 Sprint 已跑完")
            return
        if not np_ or np_ in DONE_STATES:
            return                                  # 已是终态 / 从未启动，无需动
        rs["next_phase"] = "done"
        rs["advanced_by"] = "ceremony-gate@final-pass"
        rs["advanced_from"] = np_
        rs["advanced_at"] = stamp
        rs["phase_completed_at"] = stamp
    print(f"🔓 run_state.next_phase: {np_} → done（依据：--stage final 零 FAIL；"
          f"已留痕 advanced_by=ceremony-gate@final-pass）")


def test_loop_alive(bl, version, ttl_min=90):
    """测试链路是否**真在干活**：心跳新鲜 AND 阻塞原因不指向本版（也不是全局阻塞）。

    ⛔ 只看心跳不够：心跳是测试链路**每 tick 起始无条件先写**的（在任何 early-exit 之前），
    所以冻结/被去重门跳过的空转 loop 心跳照样新鲜（5m 间隔 << 30min 窗口）。
    只认心跳会让「内联驱动 chrome 却从未真委派」这个本该被堵的形态直接通过。
    `phase-3-9.md` 的 TEST_LOOP_ALIVE 早已是这个口径，此处与之对齐。

    `aiauto_blocked_reason` 值形如 `frozen:<reason>@<version>`：**版本类**阻塞只说明那一版卡住，
    无 `@` 的历史值按全局处理（对任何版本都成立）。
    """
    hb = bl.get("aiauto_test_heartbeat_at")
    if not hb:
        return False
    try:
        dt = datetime.fromisoformat(str(hb))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        if (now - dt).total_seconds() > ttl_min * 60:
            return False
    except (ValueError, TypeError):
        return False
    ab = bl.get("aiauto_blocked_reason") or ""
    if ab:
        # ⛔ 归属口径必须与 `phase-2.md` 的读侧一致（该值形如 `frozen:<reason>@<version>`）：
        #    **全局类原因（chrome-unavailable，机器无浏览器/驱动）对任何版本成立**——少这一条时，
        #    A 版被 chrome-unavailable 冻住而查询 B 版会返回「活着」，于是 `phase-3-9.md` 的两个
        #    根因分诊分支（前置都是 TEST_ALIVE=0）都不进：streak 不 bump、#4 不发，
        #    autopilot 每 tick 顺利收尾，而那一版的浏览器实测一轮都没跑过。
        rsn = ab.split("@", 1)[0].replace("frozen:", "", 1)
        tgt = ab.split("@", 1)[1] if "@" in ab else ""
        if (not tgt) or tgt == version or rsn == "chrome-unavailable":
            return False
    return True


def cmd_test_loop_alive(a):
    """供 flow 判 GATE_STAGE 用：测试链路真活着 → 1，否则 0（恒 exit 0，纯查询）。"""
    bl = _load_json(os.path.join(a.root, a.baseline))
    print("1" if test_loop_alive(bl, a.version, a.ttl_min) else "0")
    return 0


# ★ 浏览器驱动白名单（3i 用）——「用浏览器测过」与「没用浏览器也交了报告」的唯一判据。
#   单一信源对齐 /sprint-aiauto-test：cli（本机无头 CLI，命令名 `chrome-devtools`）/
#   mcp-remote（远程 MCP）/ mcp-plugin-fallback（同插件 MCP 协议、自起本机隔离实例）。
#   `mcp` 为历史别名，一并认。⛔ 白名单之外的一切（curl / jdbc / http / api / sql …）都不是浏览器驱动。
BROWSER_DRIVERS = ("cli", "mcp", "mcp-remote", "mcp-plugin-fallback")


def main():
    ap = argparse.ArgumentParser(description="sprint-autopilot 强制仪式收尾门")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="强制仪式收尾门（exit 1=有缺失）")
    c.add_argument("--version", required=True)
    c.add_argument("--build", default="",
                   help="build 标识 {V}_build{N}；本轮未进流水线时可省，改用 --no-pipeline-reason")
    c.add_argument("--no-pipeline-reason", default="",
                   help="本轮未进入 Phase 2/3 流水线（判增量绕过 / Phase 1 无变化 / 版本已交付 / 配置向导态）的"
                        "具体依据：给出即结构级打印「⚠️ 本轮未进入开发流水线」告警 + 应产=无说明后 exit 0，"
                        "堵'既不产物也不告警'黑洞（reporter ③）")
    c.add_argument("--notify", type=int, choices=(0, 1), default=1,
                   help="1=通知通道可用（校台账）；0=合法降级（须有 baseline notify_probe 举证）")
    # ★ 默认 -1 = 未传 → 由 baseline 推导（reporter P1）：旧默认 0 会让「应产清单」说反话 ——
    #   同一 build 明明做完了完整浏览器测试并产出报告，人工不带 flag 补跑这道门自查时
    #   （**正是最需要它的场景**），却打印「AI测试报告=本build无浏览器测试→不产」，
    #   把真实存在的产物判成"本就不该有"。默认值绝不能把"没告诉我"当成"没有"。
    c.add_argument("--will-browser-test", type=int, choices=(-1, 0, 1), default=-1,
                   help="本 build 是否有浏览器测试（决定是否期望 test 报告/交付台账）；"
                        "缺省 -1 = 从 baseline 推导（测试报告已 finalize / 已委派 / 有测试交付台账）")
    c.add_argument("--expect-cards", default="")
    c.add_argument("--repo-root", default=".")
    c.add_argument("--ledger", default=DEFAULT_LEDGER)
    c.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json",
                   help="读 report_deliveries 校验报告交付")
    c.add_argument("--stage", choices=("skeleton", "final"), default="final",
                   help="skeleton=委派前/发#F前只校 SPA 骨架+无markdown（不校交付台账）；"
                        "final=收尾门(build 关闭方 R-4 后)校交付台账。默认 final")
    c.add_argument("--no-advance-run-state", action="store_true",
                   help="终态门 PASS 后不推进 run_state（保持纯只读）。"
                        "缺省会在 --stage final 零 FAIL 时把 next_phase 推到 done 并留痕")
    c.add_argument("--entry-mode", choices=("full", "incremental", "test-only"), default=None,
                   help="P0-2 规划产物存在性检查用：full/incremental 须四类规划产物齐（缺→exit 1）；test-only 不校。"
                        "不传则回退读 baseline versions.{V}.autopilot_entry_mode（autopilot 写入），再默认 full")
    c.add_argument("--no-planning", type=int, choices=(0, 1), default=None,
                   help="P0-2：1=用户显式 --no-planning 声明跳过规划（须台账留痕）→ 放行规划产物缺失；0=缺则 FAIL。"
                        "不传则回退读 baseline versions.{V}.autopilot_no_planning，再默认 0")
    c.set_defaults(func=cmd_check)

    h = sub.add_parser("handback-check",
                       help="中途交还控制权检测（exit 1=契约违背：无唤醒源却停在非终态）")
    h.add_argument("--version", required=True)
    h.add_argument("--repo-root", default=".")
    h.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json")
    h.add_argument("--wake-source", type=int, default=-1,
                   help="覆盖 baseline 的 autopilot.wake_source_this_tick（-1=读 baseline）")
    h.add_argument("--record", action="store_true",
                   help="把判定写回 autopilot.last_handback，供下一轮开局识别上轮是否丢过活儿")
    h.add_argument("--json", action="store_true")
    h.set_defaults(func=cmd_handback_check)

    t = sub.add_parser("test-loop-alive",
                       help="测试链路是否真在干活（心跳新鲜且未被阻塞）→ stdout 1/0")
    t.add_argument("--version", required=True)
    t.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json")
    t.add_argument("--root", default=".")
    t.add_argument("--ttl-min", type=float, default=90,
                   help="心跳新鲜度窗口（分钟）；测试链路 tick 起点与每批用例后都会续写心跳")

    r = sub.add_parser("record-card", help="发送里程碑通知后登记台账")
    r.add_argument("--node", required=True)
    r.add_argument("--version", required=True)
    # ★ --build 必须【可选】：#0 / #1 / #1b / #pre-* 等卡发在 Phase 3.1.5 铸 build 【之前】，
    #   此时根本没有 build 号（phase-0-4.md 亦明写"build 未铸造的 #0/#pre-* 等可省 --build"）。
    #   曾设 required=True → notify.py 省略该参时 argparse exit 2，它只记 ledger_warn 仍返回 0
    #   → 这几张卡【永远进不了台账】→ 收尾门 expect 里有它们就恒 missing → 每 tick FAIL → 3 tick 冻结版本。
    #   缺 build 的卡按 version 维度登记，由 cmd_check 以"本版本通用卡"计入（见其台账过滤）。
    r.add_argument("--build", default="",
                   help="所属 build；铸 build 之前发的卡（#0/#1/#1b/#pre-*）留空，按 version 维度登记")
    r.add_argument("--repo-root", default=".")
    r.add_argument("--ledger", default=DEFAULT_LEDGER)
    r.add_argument("--status", choices=("sent", "undelivered"), default="sent",
                   help="sent=已送达；undelivered=已尝试但渠道失败 / 无可用渠道（收尾门判 DEGRADE）")
    t.set_defaults(func=cmd_test_loop_alive)
    r.set_defaults(func=cmd_record_card)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
