#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编排层调用协议的确定性工具:QR 分级派发 / QR 移交清单 / 紧凑回传校验 / 阶段打点。

本文件在 ux-logic-extractor / dev-logic-architect / dev-execution-planner / dev-manual-testcase
四个 SKILL 里**各持一份、逐字节相同**(SKILL 独立性原则;由仓库根
`scripts/check_shared_segment_sync.py` 的 `qr-orchestration` 段守,该门仅源仓库维护时使用),SKILL 名从所在目录推出。
协议全文见同 SKILL 的 `references/flow-orchestration.md`,本文件只实现其中可机检的部分。

子命令:
  plan             按 qr_level 推导「哪些维度做语义审 / 哪些移交编排层」
  handoff          生成(或 --write 写入 00_索引.md)「QR 移交清单」块;full 档输出为空并清掉旧块
  parse-handoff    解析产物头部的移交清单,并与本 SKILL checklist 的推导结果逐项比对
  validate-result  校验 QR 子 Agent 回传的紧凑 JSON
  stage            生成一行 [AIDP-STAGE] 阶段打点标记
  parse-stage      从日志/文本中解析并校验全部 [AIDP-STAGE] 标记

退出码:0 = 通过 / 1 = 检出违规(移交清单或回传 JSON 或打点不合格)/ 2 = 入参或环境错
        (checklist 缺「等级」「脚本可判」列也是 2:那是 SKILL 自身契约坏了,不是产物违规)。

⚠️ 唯一的设计取舍(改它之前先读 flow-orchestration.md「与总约束的冲突与取舍」):
   **Critical 维度在任何档位都不移交**。`scripts` 档里「脚本可判」≠「是」的 Critical 维度
   照样留给本 SKILL 的语义审(记 escalated),所以按现有 checklist,`scripts` 与 `critical`
   两档的语义审范围相同——这是「不放松任何 Critical 判据」的直接结果,不是漏写。
"""
# >>> SHARED-SEGMENT: qr-orchestration >>>
import argparse
import json
import re
import sys
from pathlib import Path

QR_LEVELS = ("scripts", "critical", "full")
GRADES = ("Critical", "Important", "Minor")
SCRIPT_COVERAGE = ("是", "部分", "否")
VERDICTS = ("pass", "fail", "na", "unverified", "deferred")
SCOPES = ("全量", "Δ", "前滚", "基线缩放", "N/A")
DELTA_TIERS = ("全量", "基线缩放", "Δ", "—")
# 「成本类别」与「脚本可判」一一对应;两列各写各的就会漂移(把一格「部分」改成「是」,
# Critical 维度就静默退出语义审),故由本脚本在读表时强制核对,不靠自觉
COST_TO_SCRIPT = {"机器门": "是", "兼有": "部分", "语义": "否"}
# 条件维度的唯一标记:维度名里的〔…〕括注或「（条件启用…）」。只有它们可以记 N/A / 缺行
CONDITIONAL_RE = re.compile(r"〔[^〕]*〕|（条件启用")
# 采集量读数:为 0(或 skipped:true)时该维度不得记 pass(必查维度「未核验」纪律)
COUNT_KEY_RE = re.compile(r"^(?:scanned_|total_)|_count$")
STAGES = ("generate", "qr", "fix")
EVENTS = ("start", "end")
STATUSES = ("pass", "fail", None)
HANDOFF_TO = "编排层统一审计"
INDEX_HEADING = "维度成本与裁剪索引表"
MAX_STR = 200          # 回传 JSON 里任一字符串的上限:超过即视为「长段落」
MAX_SUMMARY = 120      # blocking[].summary 上限
MAX_RESULT_BYTES = 16384

# 维度编号用 QR-NN:⛔ 不用 D-NN —— architect 的待澄清/决策条目已占用 D-NNN,同写进 00_索引.md 必混
DIM_ID_RE = re.compile(r"^QR-\d{2}$")
# 人读行(固定格式,全角分号);机器解析以下一行的 JSON 注释为准,两者必须一致
HANDOFF_LINE_RE = re.compile(
    r"^> QR 级别: (?P<level>scripts|critical)；未审维度: \[(?P<dims>[^\]]*)\]；移交: "
    + HANDOFF_TO + r"\s*$")
HANDOFF_ITEM_RE = re.compile(r"^(QR-\d{2}) (.+)$")
HANDOFF_JSON_RE = re.compile(r"^<!-- AIDP-QR-HANDOFF: (\{.*\}) -->\s*$")
STAGE_LINE_RE = re.compile(r"^\[AIDP-STAGE\] (\{.*\})\s*$")
STAGE_KEYS = ("skill", "stage", "shard", "round", "event", "status")


class ContractError(Exception):
    """checklist 自身契约坏了(入参/环境错,exit 2)。"""


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def skill_name() -> str:
    return skill_root().name


def _cells(line: str):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", s)]


def _is_sep(cells) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-+:?", c or "") for c in cells)


def _clean(cell: str) -> str:
    return re.sub(r"[*`]", "", cell).strip()


def _short_name(cell: str) -> str:
    name = _clean(cell)
    name = re.sub(r"〔[^〕]*〕|（[^）]*）|\([^)]*\)", "", name)
    name = re.sub(r"[,，\[\]]", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def load_dims(checklist: Path):
    """读 checklist 顶部「维度成本与裁剪索引表」,返回 [{id,num,name,level,script}]。"""
    try:
        lines = checklist.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as exc:
        raise ContractError(f"读不出 checklist: {checklist} ({exc})")
    start = next((i for i, ln in enumerate(lines)
                  if ln.lstrip().startswith("#") and INDEX_HEADING in ln), None)
    if start is None:
        raise ContractError(f"{checklist} 里找不到「{INDEX_HEADING}」标题")
    hdr = next((i for i in range(start + 1, len(lines))
                if lines[i].lstrip().startswith("|")), None)
    if hdr is None or hdr + 1 >= len(lines) or not _is_sep(_cells(lines[hdr + 1])):
        raise ContractError("索引表表头后没有紧跟 GFM 分隔行")
    head = [_clean(c) for c in _cells(lines[hdr])]
    need = {"#": None, "维度": None, "成本类别": None, "机器门脚本": None,
            "等级": None, "脚本可判": None, "裁剪档": None}
    for k in need:
        if k in head:
            need[k] = head.index(k)
    # 裁剪档列四份 checklist 写法不同(「语义部分 Δ 裁剪档」/「语义部分 A/B 档」),按后缀认
    tier_col = next((i for i, h in enumerate(head) if h.endswith("档") and "等级" not in h), None)
    need["裁剪档"] = tier_col
    missing = [k for k, v in need.items() if v is None]
    if missing:
        raise ContractError("索引表缺列: " + "、".join(missing))
    dims = []
    for ln in lines[hdr + 2:]:
        if not ln.lstrip().startswith("|"):
            break
        c = _cells(ln)
        if len(c) != len(head):
            raise ContractError(f"索引表数据行格数 {len(c)} ≠ 表头 {len(head)}: {ln[:60]}")
        num = _clean(c[need["#"]])
        if not num.isdigit():
            raise ContractError(f"索引表编号不是数字: {num!r}")
        level, script = _clean(c[need["等级"]]), _clean(c[need["脚本可判"]])
        if level not in GRADES:
            raise ContractError(f"维度 {num} 的等级 {level!r} 不在 {GRADES} 内")
        if script not in SCRIPT_COVERAGE:
            raise ContractError(f"维度 {num} 的脚本可判 {script!r} 不在 {SCRIPT_COVERAGE} 内")
        cost = _clean(c[need["成本类别"]])
        if COST_TO_SCRIPT.get(cost) != script:
            raise ContractError(f"维度 {num}: 成本类别「{cost}」应对应脚本可判「{COST_TO_SCRIPT.get(cost)}」,"
                                f"实际「{script}」")
        if script == "是" and _clean(c[need["机器门脚本"]]).startswith("—"):
            raise ContractError(f"维度 {num}: 机器门脚本为 —,脚本可判不得为「是」")
        raw_tier = _clean(c[need["裁剪档"]])
        tier = next((t for t in DELTA_TIERS if raw_tier.startswith(t)), None)
        if tier is None:
            raise ContractError(f"维度 {num}: 裁剪档 {raw_tier!r} 不在 {DELTA_TIERS} 内")
        dims.append({"id": "QR-%02d" % int(num), "num": int(num),
                     "name": _short_name(c[need["维度"]]), "level": level, "script": script,
                     "conditional": bool(CONDITIONAL_RE.search(c[need["维度"]])),
                     "delta_tier": tier})
    nums = [d["num"] for d in dims]
    if not dims or nums != list(range(1, len(dims) + 1)):
        raise ContractError(f"索引表编号必须从 1 连续递增,实际 {nums}")
    return dims


def plan(dims, qr_level: str):
    """三档推导。机器门在任何档位都全量跑,这里只决定语义审的范围。"""
    if qr_level not in QR_LEVELS:
        raise ValueError(qr_level)
    semantic, deferred, escalated = [], [], []
    for d in dims:
        if qr_level == "full":
            semantic.append(d)
        elif d["level"] == "Critical":
            # Critical 永不移交;scripts 档里脚本判不全的 Critical 维度照样留给语义审
            if d["script"] != "是":
                semantic.append(d)
                if qr_level == "scripts":
                    escalated.append(d)
        elif d["script"] != "是":
            deferred.append(d)
        # 非 Critical 且「脚本可判 = 是」:只有机器门、没有语义部分,三档都无须移交
    out = {"skill": skill_name(), "qr_level": qr_level,
           "machine_gates": "all",
           "semantic_dims": [d["id"] for d in semantic],
           "escalated_dims": [d["id"] for d in escalated],
           # delta_tier 随移交带走:标「全量」的维度,编排层接手后同样不得按 Δ 裁剪
           "deferred_dims": [{"id": d["id"], "name": d["name"], "level": d["level"],
                              "script_coverage": d["script"], "delta_tier": d["delta_tier"]}
                             for d in deferred]}
    if qr_level == "scripts" and len(escalated) == len(semantic):
        # 所有 Critical 维度都判不全 → scripts 与 critical 两档语义审范围相同(取舍见 flow-orchestration.md)
        out["equivalent_to"] = "critical"
    return out


def handoff_block(p) -> str:
    if p["qr_level"] == "full":
        return ""
    items = ", ".join(f'{d["id"]} {d["name"]}' for d in p["deferred_dims"])
    line = f'> QR 级别: {p["qr_level"]}；未审维度: [{items}]；移交: {HANDOFF_TO}'
    payload = {"skill": p["skill"], "qr_level": p["qr_level"],
               "deferred_dims": p["deferred_dims"], "handoff_to": HANDOFF_TO}
    js = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"{line}\n<!-- AIDP-QR-HANDOFF: {js} -->"


def _is_block_line(ln: str) -> bool:
    return ln.startswith("> QR 级别:") or ln.startswith("<!-- AIDP-QR-HANDOFF")


def _fenced(lines):
    """每行是否在代码围栏内(围栏里的示例行不是真移交块)。"""
    inside, out = False, []
    for ln in lines:
        if ln.lstrip().startswith(("```", "~~~")):
            out.append(True)
            inside = not inside
            continue
        out.append(inside)
    return out


def write_handoff(target: Path, block: str) -> None:
    """幂等写入:先删旧块(连同插入时带的那一个前置空行),非 full 档再插到 H1 之后。
    跳过代码围栏;保留原文件换行风格(CRLF 文件写回仍是 CRLF)。"""
    raw = target.read_bytes().decode("utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    lines = text.split("\n")
    trailing = lines and lines[-1] == ""
    if trailing:
        lines = lines[:-1]
    fence = _fenced(lines)
    drop = {i for i, ln in enumerate(lines) if _is_block_line(ln) and not fence[i]}
    if drop:
        first = min(drop)
        if first > 0 and lines[first - 1] == "":
            drop.add(first - 1)
    lines = [ln for i, ln in enumerate(lines) if i not in drop]
    if block:
        fence = _fenced(lines)
        h1 = next((i for i, ln in enumerate(lines) if re.match(r"^#\s", ln) and not fence[i]), None)
        if h1 is None:
            lines[0:0] = block.split("\n") + [""]
        else:
            lines[h1 + 1:h1 + 1] = [""] + block.split("\n")
    out = nl.join(lines) + (nl if trailing else "")
    target.write_bytes(out.encode("utf-8"))


def parse_handoff_text(text: str):
    lines = text.splitlines()
    fence = _fenced(lines)
    hl = [(i, HANDOFF_LINE_RE.match(ln)) for i, ln in enumerate(lines)
          if ln.startswith("> QR 级别:") and not fence[i]]
    js = [(i, HANDOFF_JSON_RE.match(ln)) for i, ln in enumerate(lines)
          if ln.startswith("<!-- AIDP-QR-HANDOFF") and not fence[i]]
    if not hl and not js:
        return {"present": False}, []
    errs = []
    if len(hl) != 1 or len(js) != 1:
        errs.append(f"移交清单必须恰好一行人读行 + 一行 JSON 注释,实际 {len(hl)} / {len(js)}")
        return {"present": True}, errs
    (li, lm), (ji, jm) = hl[0], js[0]
    if lm is None:
        errs.append(f"第 {li + 1} 行人读行格式不符(须与 flow-orchestration.md 的正则逐字一致)")
    if jm is None:
        errs.append(f"第 {ji + 1} 行 JSON 注释格式不符")
    if errs:
        return {"present": True}, errs
    if ji != li + 1:
        errs.append("JSON 注释必须紧跟在人读行的下一行")
    h1 = next((i for i, ln in enumerate(lines) if re.match(r"^#\s", ln) and not fence[i]), None)
    want_at = (h1 + 2) if h1 is not None else 0
    if li != want_at:
        errs.append(f"移交清单必须紧跟在一级标题之后(应在第 {want_at + 1} 行,实际第 {li + 1} 行)")
    try:
        payload = json.loads(jm.group(1))
    except ValueError as exc:
        return {"present": True}, [f"JSON 注释解析失败: {exc}"]
    line_ids = []
    raw = lm.group("dims").strip()
    for item in ([x.strip() for x in raw.split(",")] if raw else []):
        m = HANDOFF_ITEM_RE.match(item)
        if not m:
            errs.append(f"未审维度条目格式不符: {item!r}(须为「QR-NN 名称」)")
            continue
        line_ids.append(m.group(1))
    dd = payload.get("deferred_dims")
    if payload.get("qr_level") != lm.group("level"):
        errs.append("人读行与 JSON 的 qr_level 不一致")
    if payload.get("handoff_to") != HANDOFF_TO:
        errs.append(f"handoff_to 必须是「{HANDOFF_TO}」")
    if not isinstance(dd, list) or not all(isinstance(x, dict) for x in dd):
        errs.append("deferred_dims 必须是对象数组")
        dd = []
    json_ids = [x.get("id") for x in dd]
    if json_ids != line_ids:
        errs.append(f"人读行与 JSON 的未审维度不一致: {line_ids} vs {json_ids}")
    for x in dd:
        if not DIM_ID_RE.match(str(x.get("id", ""))):
            errs.append(f"维度编号不合法: {x.get('id')!r}")
        if x.get("level") == "Critical":
            errs.append(f"{x.get('id')} 是 Critical 维度,任何档位都不得移交")
        if x.get("level") not in GRADES:
            errs.append(f"{x.get('id')} 的 level 不合法: {x.get('level')!r}")
    payload["present"] = True
    return payload, errs


def validate_result(obj, dims, allow_missing, expect_level=None):
    errs = []
    want = ("skill", "qr_level", "round", "dims", "blocking", "deferred_dims")
    if not isinstance(obj, dict):
        return ["回传必须是 JSON 对象"]
    extra = sorted(set(obj) - set(want))
    lack = [k for k in want if k not in obj]
    if extra:
        errs.append(f"回传含协议外的顶层字段(禁止夹带正文/长段落): {extra}")
    if lack:
        errs.append(f"回传缺字段: {lack}")
        return errs

    def walk(v, path):
        if isinstance(v, str) and len(v) > MAX_STR:
            errs.append(f"{path} 字符串长 {len(v)} > {MAX_STR}(长段落禁止回传主流程)")
        elif isinstance(v, dict):
            for k, x in v.items():
                walk(x, f"{path}.{k}")
        elif isinstance(v, list):
            for i, x in enumerate(v):
                walk(x, f"{path}[{i}]")
    walk(obj, "$")
    if len(json.dumps(obj, ensure_ascii=False).encode("utf-8")) > MAX_RESULT_BYTES:
        errs.append(f"回传体积超过 {MAX_RESULT_BYTES} 字节")
    if obj["skill"] != skill_name():
        errs.append(f"skill 应为 {skill_name()!r},实际 {obj['skill']!r}")
    if obj["qr_level"] not in QR_LEVELS:
        errs.append(f"qr_level 不合法: {obj['qr_level']!r}")
        return errs
    if expect_level and obj["qr_level"] != expect_level:
        errs.append(f"回传 qr_level={obj['qr_level']} 与派发档位 {expect_level} 不一致")
    for key in ("dims", "blocking", "deferred_dims"):
        if not isinstance(obj[key], list):
            errs.append(f"{key} 必须是数组")
    if errs:
        return errs
    if not isinstance(obj["round"], int) or isinstance(obj["round"], bool) or obj["round"] < 1:
        errs.append("round 必须是 ≥1 的整数(QR 轮次从 1 起)")
    by_id = {d["id"]: d for d in dims}
    for x in sorted(allow_missing):
        if x not in by_id or not by_id[x]["conditional"]:
            errs.append(f"--allow-missing {x} 不是条件维度(只有维度名带〔…〕/「条件启用」的维度可以不留行)")
    seen = {}
    dim_keys = {"id", "level", "verdict", "findings_count"}
    opt_keys = {"scope", "gate_exit", "readings", "basis"}
    for i, d in enumerate(obj["dims"]):
        if not isinstance(d, dict):
            errs.append(f"dims[{i}] 不是对象")
            continue
        if not dim_keys <= set(d):
            errs.append(f"dims[{i}] 缺字段 {sorted(dim_keys - set(d))}")
            continue
        if set(d) - dim_keys - opt_keys:
            errs.append(f"dims[{i}] 含协议外字段 {sorted(set(d) - dim_keys - opt_keys)}")
        did = d["id"]
        if did not in by_id:
            errs.append(f"dims[{i}].id {did!r} 不是本 SKILL checklist 里的维度")
            continue
        if did in seen:
            errs.append(f"{did} 重复出现")
        seen[did] = d
        if d["level"] != by_id[did]["level"]:
            errs.append(f"{did} 的 level 应为 {by_id[did]['level']}(以 checklist 等级列为准)")
        if d["verdict"] not in VERDICTS:
            errs.append(f"{did} 的 verdict 不合法: {d['verdict']!r}")
        fc = d["findings_count"]
        if not isinstance(fc, int) or isinstance(fc, bool) or fc < 0:
            errs.append(f"{did} 的 findings_count 必须是 ≥0 的整数")
        ge = d.get("gate_exit")
        # 一个维度挂多个脚本时写成 {脚本名: 退出码};只挂一个可直接写整数
        codes = list(ge.values()) if isinstance(ge, dict) else [ge]
        if any(c not in (None, 0, 1, 2) or isinstance(c, bool) for c in codes):
            errs.append(f"{did} 的 gate_exit 只能是 0/1/2/null 或 {{脚本名: 0/1/2}}")
            codes = []
        rd = d.get("readings")
        if rd is not None and not (isinstance(rd, dict) and all(
                isinstance(v, (int, bool)) for v in rd.values())):
            errs.append(f"{did} 的 readings 只能是「名字 → 整数/布尔」的对象")
            rd = None
        if "scope" in d and d["scope"] not in SCOPES:
            errs.append(f"{did} 的 scope 只能是 {SCOPES}")
        if d.get("scope") == "前滚" and not (isinstance(d.get("basis"), str) and d["basis"].strip()):
            errs.append(f"{did} 标「前滚」必须在 basis 写明依据的上一轮报告")
        if d["verdict"] == "na" and not by_id[did]["conditional"]:
            errs.append(f"{did} 不是条件维度,不得记 na(必查维度没跑记 unverified)")
        if d["verdict"] == "pass":
            if any(c in (1, 2) for c in codes):
                errs.append(f"{did} 机器门 exit {codes} 却记 pass")
            zero = [k for k, v in (rd or {}).items()
                    if (k == "skipped" and v is True)
                    or (COUNT_KEY_RE.search(k) and not isinstance(v, bool) and v == 0)]
            if zero:
                errs.append(f"{did} 采集量 {zero} 为 0/skipped 却记 pass(应记 unverified)")
    absent = [x for x in by_id if x not in seen and x not in allow_missing]
    if absent:
        errs.append(f"台账缺行(一行不少,门控维度用 --allow-missing 声明): {absent}")
    expect = {x["id"] for x in plan(dims, obj["qr_level"])["deferred_dims"]}
    got_deferred = obj["deferred_dims"]
    if not isinstance(got_deferred, list) or not all(isinstance(x, str) for x in got_deferred):
        errs.append("deferred_dims 必须是维度编号字符串数组")
        got_deferred = []
    if set(got_deferred) != expect:
        errs.append(f"deferred_dims 与 checklist 推导不一致: 应为 {sorted(expect)},"
                    f"实际 {sorted(got_deferred)}")
    marked = {k for k, v in seen.items() if v.get("verdict") == "deferred"}
    if marked != set(got_deferred) & set(seen):
        errs.append(f"verdict=deferred 的维度 {sorted(marked)} 与 deferred_dims 不一致")
    blk_dims = set()
    for i, b in enumerate(obj["blocking"]):
        if not isinstance(b, dict) or set(b) != {"dim", "file", "line", "summary"}:
            errs.append(f"blocking[{i}] 必须恰好含 dim/file/line/summary 四个字段")
            continue
        if b["dim"] not in by_id:
            errs.append(f"blocking[{i}].dim {b['dim']!r} 不是本 SKILL 的维度")
        if not isinstance(b["line"], int) or isinstance(b["line"], bool) or b["line"] < 0:
            errs.append(f"blocking[{i}].line 必须是 ≥0 的整数(定位不到写 0)")
        if not isinstance(b["summary"], str) or not b["summary"].strip() \
                or len(b["summary"]) > MAX_SUMMARY:
            errs.append(f"blocking[{i}].summary 必须是 1~{MAX_SUMMARY} 字的一句话")
        blk_dims.add(b["dim"])
    for did, d in seen.items():
        if d.get("verdict") in ("fail", "unverified") and d["level"] == "Critical" \
                and did not in blk_dims:
            errs.append(f"{did} 是 Critical 且判 {d['verdict']},blocking 里必须至少有一条")
    return errs


def make_stage(stage, event, shard, rnd, status):
    errs = []
    if stage not in STAGES:
        errs.append(f"stage 只能是 {STAGES}")
    if event not in EVENTS:
        errs.append(f"event 只能是 {EVENTS}")
    if status not in STATUSES:
        errs.append("status 只能是 pass/fail/null")
    if event == "start" and status is not None:
        errs.append("event=start 时 status 必须是 null")
    if not isinstance(rnd, int) or isinstance(rnd, bool) or rnd < 0:
        errs.append("round 必须是 ≥0 的整数")
    elif stage == "generate" and rnd != 0:
        errs.append("stage=generate 时 round 必须是 0")
    elif stage in ("qr", "fix") and rnd < 1:
        errs.append(f"stage={stage} 时 round 从 1 起")
    if event == "end" and status is None:
        errs.append("event=end 时 status 必须是 pass/fail")
    if shard is not None and (not isinstance(shard, str) or not shard.strip()
                              or "\n" in shard):
        errs.append("shard 必须是非空单行字符串或 null")
    obj = {"skill": skill_name(), "stage": stage, "shard": shard, "round": rnd,
           "event": event, "status": status}
    return "[AIDP-STAGE] " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")), errs


def parse_stage_text(text: str):
    marks, errs = [], []
    for n, ln in enumerate(text.splitlines(), 1):
        if "[AIDP-STAGE]" not in ln:
            continue
        m = STAGE_LINE_RE.match(ln.strip())
        if not m:
            errs.append(f"第 {n} 行含 [AIDP-STAGE] 但格式不符")
            continue
        try:
            obj = json.loads(m.group(1))
        except ValueError:
            errs.append(f"第 {n} 行 JSON 解析失败")
            continue
        if not isinstance(obj, dict) or tuple(obj) != STAGE_KEYS:
            errs.append(f"第 {n} 行字段必须恰好且按序为 {STAGE_KEYS}")
            continue
        if not isinstance(obj["skill"], str) or not obj["skill"]:
            errs.append(f"第 {n} 行 skill 为空")
        _, e = make_stage(obj["stage"], obj["event"], obj["shard"], obj["round"], obj["status"])
        errs.extend(f"第 {n} 行 {x}" for x in e)
        obj["line"] = n
        marks.append(obj)
    open_keys, unpaired = {}, []
    for mk in marks:
        key = (mk["skill"], mk["stage"], mk["shard"], mk["round"])
        n = open_keys.get(key, 0) + (1 if mk["event"] == "start" else -1)
        if n < 0:  # 先 end 后 start:按序配对,单独记一条
            unpaired.append(list(key) + ["end-before-start"])
            n = 0
        open_keys[key] = n
    unpaired += [list(k) for k, v in open_keys.items() if v > 0]
    return marks, errs, unpaired


def _read_arg(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="编排层调用协议工具(QR 分级 / 移交 / 回传 / 打点)")
    ap.add_argument("--checklist", help="默认 <SKILL>/references/quality-review-checklist.md")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("plan")
    sp.add_argument("--qr-level", required=True, choices=QR_LEVELS)
    sh = sub.add_parser("handoff")
    sh.add_argument("--qr-level", required=True, choices=QR_LEVELS)
    sh.add_argument("--write", metavar="00_索引.md", help="就地写入(幂等;full 档清掉旧块)")
    sph = sub.add_parser("parse-handoff")
    sph.add_argument("file")
    sph.add_argument("--expect-level", choices=QR_LEVELS, required=True,
                     help="编排层派发时传的档位(必传:缺清单与 full 档同形,不传就分不开)")
    sv = sub.add_parser("validate-result")
    sv.add_argument("file", help="JSON 文件路径,- 表示 stdin")
    sv.add_argument("--allow-missing", action="append", default=[], metavar="QR-NN",
                    help="未触发的条件维度(只接受维度名带〔…〕/「条件启用」的维度)")
    sv.add_argument("--expect-level", choices=QR_LEVELS, help="派发时的档位;回传档位不一致即违规")
    ss = sub.add_parser("stage")
    ss.add_argument("--stage", required=True)
    ss.add_argument("--event", required=True)
    ss.add_argument("--shard", default=None)
    ss.add_argument("--round", type=int, default=0)
    ss.add_argument("--status", default=None, choices=("pass", "fail"))
    sps = sub.add_parser("parse-stage")
    sps.add_argument("file", help="日志文件路径,- 表示 stdin")
    args = ap.parse_args(argv)

    if args.cmd == "stage":
        line, errs = make_stage(args.stage, args.event, args.shard, args.round, args.status)
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 2
        print(line)
        return 0
    if args.cmd == "parse-stage":
        try:
            text = _read_arg(args.file)
        except (OSError, UnicodeDecodeError) as exc:
            print(f"读不出: {exc}", file=sys.stderr)
            return 2
        marks, errs, unpaired = parse_stage_text(text)
        print(json.dumps({"marks": marks, "errors": errs, "unpaired": unpaired},
                         ensure_ascii=False))
        return 1 if errs else 0

    checklist = Path(args.checklist) if args.checklist else \
        skill_root() / "references" / "quality-review-checklist.md"
    try:
        dims = load_dims(checklist)
    except ContractError as exc:
        print(f"checklist 契约错误: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "plan":
        print(json.dumps(plan(dims, args.qr_level), ensure_ascii=False))
        return 0
    if args.cmd == "handoff":
        block = handoff_block(plan(dims, args.qr_level))
        if args.write:
            target = Path(args.write)
            if not target.is_file():
                print(f"--write 目标不存在: {target}", file=sys.stderr)
                return 2
            write_handoff(target, block)
        elif block:
            print(block)
        return 0
    if args.cmd == "parse-handoff":
        try:
            text = Path(args.file).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"读不出: {exc}", file=sys.stderr)
            return 2
        payload, errs = parse_handoff_text(text)
        if not errs and payload.get("present"):
            if payload.get("skill") == skill_name():
                expect = plan(dims, payload["qr_level"])["deferred_dims"]
                got = payload["deferred_dims"]
                if [d.get("id") for d in got] != [d["id"] for d in expect]:
                    errs.append("移交清单与 checklist 推导不一致: 应为 "
                                f"{[d['id'] for d in expect]},实际 {[d.get('id') for d in got]}")
                else:
                    for g, e in zip(got, expect):
                        if g != e:
                            errs.append(f"{e['id']} 的字段与 checklist 推导不一致: 应为 {e},实际 {g}")
            else:
                errs.append(f"移交清单的 skill {payload.get('skill')!r} 不是本 SKILL")
        level = payload.get("qr_level") if payload.get("present") else "full"
        if not errs and level != args.expect_level:
            errs.append(f"期望 qr_level={args.expect_level},产物里是 {level}"
                        + ("(缺移交清单)" if not payload.get("present") else ""))
        print(json.dumps({"handoff": payload, "errors": errs}, ensure_ascii=False))
        return 1 if errs else 0
    if args.cmd == "validate-result":
        try:
            obj = json.loads(_read_arg(args.file))
        except (OSError, UnicodeDecodeError) as exc:
            print(f"读不出: {exc}", file=sys.stderr)
            return 2
        except ValueError as exc:
            print(json.dumps({"errors": [f"不是合法 JSON: {exc}"]}, ensure_ascii=False))
            return 1
        errs = validate_result(obj, dims, set(args.allow_missing), args.expect_level)
        print(json.dumps({"errors": errs}, ensure_ascii=False))
        return 1 if errs else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
# <<< SHARED-SEGMENT: qr-orchestration <<<
