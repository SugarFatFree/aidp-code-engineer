#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""aidp_config.py —— **人维护配置**的单一落点（`memory/aidp-config.yaml`）。

## 为什么是一份带注释的 yaml，而不是再开几个点文件

下游实测：一个仓库里散着 17 个 AIDP 运行时产物，2 个位置 × 2 套命名前缀 × 3 种格式。
使用者看到根目录一堆点文件，**分不清哪个是自己能动的**——于是要么不敢动，
要么动错（改了程序写的状态文件，下一轮被覆盖，还以为是 bug）。

收编的判据是「**谁写的**」，不是「讲的是什么」：

  · 人写的  → 本文件（`memory/aidp-config.yaml`，不带点前缀 = 人能看见、可编辑、有注释）
  · 程序写的 → `memory/.sprint-autopilot-baseline.json`（运行时状态机，人别动）

`last_deployed_at` 这类**程序写的时间戳**因此归 baseline，不进本文件——
把它混进人维护配置，会让「这份文件我能不能随便改」重新变得说不清。

## 为什么写入是**逐行外科手术**而不是重新序列化

本文件的价值有一半在注释（每个开关旁边写着关掉之后会发生什么）。
`yaml.dump()` 会把注释全部抹掉——**一次程序写入就让这份文件退化成无注释的 json**。
故 `set_scalar()` 只定位到那一行、替换冒号右边，其余字节原样保留。

## 读取顺序

本文件 → 内置缺省。脚手架版本戳只认本文件的 `scaffold` 段（与 `scaffold_marker.py` 同一落点）。
"""
import os
import sys

CONFIG_REL = os.path.join("memory", "aidp-config.yaml")

# Stop 护栏的盲打逃生舱（`touch` 即关，优先级高于 yaml 键）
STOP_GUARD_OFF_REL = os.path.join("memory", ".autopilot-stop-guard-off")

TEMPLATE = """\
# AIDP 项目配置（**人维护**，团队共享、随 git 提交）
#
# 这是你可以直接改的那一份。程序写的运行时状态在
# memory/.sprint-autopilot-baseline.json —— 那份别手动动，会被下一轮覆盖。
#
# 改完无需重启任何东西，下一次命令运行即生效。

project:
  # 应用编码（英文，用于目录 / 服务名等）。
  name: null
  # 项目中文名称（里程碑通知标题前缀优先使用）。
  name_cn: null

commit_gate:
  # 提交前门禁 commit_gate.py 总开关（约定 24）。
  # 关掉之后：commit 前不再检查约定 22 台账积压 / 约定 31.5 推送欠账，退出码恒 0。
  enabled: true

notify:
  # 里程碑通知总开关（约定 32）。关闭时 notify.py --auto 返回 3（合规静默跳过）。
  enabled: false
  # 一个渠道失败时是否继续尝试下一个。
  fallback: true
  # 渠道按顺序尝试，成功即停。⛔ webhook 地址 / 密钥只写环境变量名，不写明文。
  # 例：- {type: feishu, webhook_env: AIDP_FEISHU_WEBHOOK, secret_env: AIDP_FEISHU_SECRET}
  #     - {type: dingtalk, webhook_env: AIDP_DINGTALK_WEBHOOK, secret_env: AIDP_DINGTALK_SECRET}
  #     - {type: wecom, webhook_env: AIDP_WECOM_WEBHOOK}
  #     - {type: lark-cli, chat_id: "<chat id>"}
  #     - {type: command, command: "<读 stdin JSON 的发送命令>"}
  channels: []

cicd:
  # CICD 提供方（约定 31.5）：github-actions（默认）/ gitlab-ci / jenkins / command / none。
  provider: github-actions
  # 无人值守下是否允许自动触发 / 重试流水线。
  auto_trigger: true
  max_retries: 3
  # 部署环境 → 流水线标识。github-actions = workflow 文件名；gitlab-ci = 分支名（可留空）；
  # jenkins = Job 路径；command = 原样代入命令模板的 {pipeline}。例：{test: deploy-test.yml}
  pipelines: {}
  # 各提供方专属参数（只填所选那个）。⛔ 令牌 / 密码只写环境变量名。
  # gitlab-ci: {url: https://gitlab.com, project: group/name, token_env: AIDP_GITLAB_TOKEN}
  # jenkins:   {url: https://jenkins.example.com, user_env: AIDP_JENKINS_USER, token_env: AIDP_JENKINS_TOKEN}
  # command:   {list: "...", view: "...", trigger: "...", retry: "...", check: "..."}

stop_guard:
  # autopilot Stop 护栏（防止无人值守链路在未收口时静默停下）。
  # 关掉 = 临时逃生舱：护栏误报把你挡住时用，⛔ 排除故障后记得改回 true。
  enabled: true

scheduler:
  # 7×24 操作系统调度（.aidp/scripts/aidp_scheduler.py install）。开发链路与测试链路各一个定时任务。
  dev_interval: 10m
  test_interval: 5m
  # 执行 Agent：auto（按 agent_env.py detect）/ claude / codex / dsh
  agent: auto
  # 任一链路连续多少个周期无心跳即本地告警 + 通知
  stale_cycles: 3
  # 各 Agent 的非交互执行命令模板（{prompt} 为占位符）；留空用内置默认，
  # ⛔ 内置默认之外的 CLI 写法请按所用 Agent 当前版本的官方文档自行确认。
  exec: {}
  # 例：exec: {codex: "codex exec --sandbox workspace-write {prompt}", dsh: "<dsh 非交互命令> {prompt}"}

scaffold:
  # 本项目上次同步到的脚手架版本号。**由 aidp-code-engineer 脚手架写入，人别改**——
  # 改小会触发不必要的全量覆盖，改大会让真正的升级被跳过。
  # 模板项目自身没有这一段（它就是脚手架的出处）。
  version: null
  # 升级中途留下的待消费语义改写队列；非 null 表示**上一轮升级尚未真正交付**。
  pending: null

# autopilot 决策兜底（★ 权威是本版 PRD frontmatter 的 autopilot_decisions 段，
# 本段仅在 PRD 未声明时生效；全项目一份、无版本维度）。
autopilot_decisions: {}
"""


# ───────────────────────── 读 ─────────────────────────

def _parse(text):
    """复用 autopilot_decisions_merge 的 yaml 子集解析器（纯标准库、容忍注释）。

    子集解析器把单行流式写法（`{a: 1}` / `[x, y]`）当作字符串原样返回，
    `notify.channels` 的示例正是这种写法，故解析后再做一次流式值展开。
    """
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from autopilot_decisions_merge import parse_yaml_subset
    except ImportError:
        return None
    try:
        return _expand_flow(parse_yaml_subset(text))
    except Exception:
        return None


def _flow_scalar(tok):
    t = tok.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
        return t[1:-1]
    low = t.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if low in ("null", "~", ""):
        return None
    try:
        return int(t)
    except ValueError:
        return t


def _split_flow(body):
    """按顶层逗号切分流式集合内容（尊重引号与嵌套括号）。"""
    parts, buf, depth, quote = [], [], 0, None
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return parts


def parse_flow(text):
    """单行 YAML 流式值 → dict / list / 标量（只覆盖配置里用得到的子集）。"""
    t = (text or "").strip()
    if t.startswith("{") and t.endswith("}"):
        out = {}
        for item in _split_flow(t[1:-1]):
            if ":" not in item:
                continue
            k, v = item.split(":", 1)
            out[_flow_scalar(k)] = parse_flow(v)
        return out
    if t.startswith("[") and t.endswith("]"):
        return [parse_flow(x) for x in _split_flow(t[1:-1])]
    return _flow_scalar(t)


def _expand_flow(node):
    if isinstance(node, dict):
        return {k: _expand_flow(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand_flow(v) for v in node]
    if isinstance(node, str):
        t = node.strip()
        if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
            return parse_flow(t)
    return node


def config_path(root="."):
    return os.path.join(root, CONFIG_REL)


def load(root="."):
    """→ (dict, parse_ok)。

    ⚠️ 必须把「解析失败」与「文件不存在」分开返回：两者都给空 dict，但
    **判据相反**——不存在 = 全新/未迁移项目（可回落旧落点），解析失败 = 文件被改坏
    （此时任何缺省都可能是错的，由调用方按各自的 fail 方向处置）。
    合成一个返回值就等于把这条区别抹掉，而它恰恰是 fail-closed 的依据。
    """
    p = config_path(root)
    if not os.path.isfile(p):
        return {}, True
    try:
        text = open(p, encoding="utf-8").read()
    except (OSError, ValueError):
        # ⚠️ ValueError 覆盖 UnicodeDecodeError：文件被塞进二进制 / 存成别的编码时，
        #    没有这一支就是**当场抛异常**而不是 fail-closed —— 每个调用方都会崩，
        #    而 fail-closed 的全部意义就是「坏了也要给出一个安全的答案」。
        return {}, False
    data = _parse(text)
    if data is None:
        return {}, False
    return data, True


def _dig(data, dotted):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def get(root, dotted, default=None):
    """读一个点分键；本文件缺失/无该键 → None（由 get_bool 等上层决定回落与缺省）。"""
    data, _ = load(root)
    v = _dig(data, dotted)
    return default if v is None else v


def get_bool(root, dotted, default=True):
    """开关类读取：本文件 → 缺省。"""
    v = get(root, dotted)
    if isinstance(v, bool):
        return v
    if isinstance(v, str) and v.strip().lower() in ("true", "false"):
        return v.strip().lower() == "true"
    return default


def _str_or_none(v):
    if isinstance(v, str):
        t = v.strip()
        if t and t.lower() not in ("null", "~") and not (t.startswith("{{") or t.startswith("<")):
            return t
    return None


def project_config(root="."):
    """项目标识 → {"name": 英文应用编码|None, "name_cn": 中文名称|None}（`project` 段）。

    空串 / `null` / 模板占位（`{{…}}`、`<…>`）一律视为未填。
    """
    data, _ = load(root)
    sec = _dig(data, "project")
    sec = sec if isinstance(sec, dict) else {}
    return {"name": _str_or_none(sec.get("name")), "name_cn": _str_or_none(sec.get("name_cn"))}


def commit_gate_enabled(root="."):
    """提交前门禁总开关（约定 24）：`commit_gate.enabled`，缺省 True。"""
    return get_bool(root, "commit_gate.enabled", True)


def notify_config(root="."):
    """里程碑通知配置（约定 32）→ {enabled, fallback, channels}。

    缺省 `enabled=False` / `channels=[]`：未配置渠道的项目不发任何通知。
    """
    data, _ = load(root)
    sec = _dig(data, "notify")
    sec = sec if isinstance(sec, dict) else {}
    chans = sec.get("channels")
    chans = [c for c in chans if isinstance(c, dict)] if isinstance(chans, list) else []
    return {
        "enabled": get_bool(root, "notify.enabled", False),
        "fallback": get_bool(root, "notify.fallback", True),
        "channels": chans,
    }


def cicd_config(root="."):
    """CICD 配置（约定 31.5）→ {provider, auto_trigger, max_retries, pipelines, <provider>: {...}}。

    `provider` ∈ github-actions（默认）/ gitlab-ci / jenkins / command / none；
    `pipelines` = 部署环境 → 流水线标识（含义随 provider 而定，见 cicd_providers.py）；
    各提供方的专属参数原样透传在同名子段里。
    """
    data, _ = load(root)
    sec = _dig(data, "cicd")
    sec = sec if isinstance(sec, dict) else {}
    pl = sec.get("pipelines")
    pl = {str(k): ("" if v is None else str(v)) for k, v in pl.items()} if isinstance(pl, dict) else {}
    try:
        retries = int(sec.get("max_retries", 3))
    except (TypeError, ValueError):
        retries = 3
    out = {
        "provider": str(sec.get("provider") or "github-actions"),
        "auto_trigger": get_bool(root, "cicd.auto_trigger", True),
        "max_retries": retries,
        "pipelines": pl,
    }
    for name in ("github-actions", "gitlab-ci", "jenkins", "command"):
        if isinstance(sec.get(name), dict):
            out[name] = sec[name]
    return out


def stop_guard_enabled(root="."):
    """Stop 护栏开关。

    `touch memory/.autopilot-stop-guard-off` 逃生舱优先级最高：护栏误报把人挡住时，
    那一刻需要的是一条能盲打的命令，不是「去 yaml 里找一个键」。
    """
    if os.path.exists(os.path.join(root, STOP_GUARD_OFF_REL)):
        return False
    return get_bool(root, "stop_guard.enabled", True)


SCHEDULER_DEFAULTS = {"dev_interval": "10m", "test_interval": "5m", "agent": "auto",
                      "stale_cycles": 3, "exec": {}}


def scheduler_config(root="."):
    """7×24 操作系统调度配置（`scheduler` 段）→ {dev_interval, test_interval, agent, stale_cycles, exec}。"""
    data, _ = load(root)
    sec = _dig(data, "scheduler")
    sec = sec if isinstance(sec, dict) else {}
    out = dict(SCHEDULER_DEFAULTS)
    for k in ("dev_interval", "test_interval", "agent"):
        v = _str_or_none(sec.get(k)) if isinstance(sec.get(k), str) else None
        if v:
            out[k] = v
    try:
        out["stale_cycles"] = max(1, int(sec.get("stale_cycles", 3)))
    except (TypeError, ValueError):
        out["stale_cycles"] = 3
    ex = sec.get("exec")
    out["exec"] = {str(k): str(v) for k, v in ex.items() if v} if isinstance(ex, dict) else {}
    return out


def scaffold_version(root="."):
    """本项目上次同步到的脚手架版本号（`scaffold.version`）；未同步过 → None。"""
    v = get(root, "scaffold.version")
    if isinstance(v, str) and v.strip() and v.strip().lower() != "null":
        return v.strip()
    return None


def scaffold_pending(root="."):
    """上一轮升级遗留的待消费语义改写队列标记；无 → None。"""
    v = get(root, "scaffold.pending")
    if isinstance(v, str) and v.strip() and v.strip().lower() != "null":
        return v.strip()
    return None


def is_downstream(root="."):
    """本项目是不是**下游业务项目**（相对「AIDP 模板项目自身」）。

    ★ fail-closed 方向：配置文件存在但**解析失败 → 判下游**。
    判错的两个方向代价不对称——把下游误判成模板会让它按模板项目口径被豁免、
    且豁免是静默的（`is_template_project=true` 看起来一切正常）；
    反过来把模板误判成下游，最多是模板项目多报一次提醒，当场就能看见。
    """
    if scaffold_version(root) or scaffold_pending(root):
        return True
    _, ok = load(root)
    if not ok:
        return True
    return False


# ───────────────────────── 写 ─────────────────────────

def ensure(root="."):
    """确保配置文件存在（缺失则按模板创建），返回其路径。"""
    p = config_path(root)
    if not os.path.isfile(p):
        d = os.path.dirname(p)
        if d:
            os.makedirs(d, exist_ok=True)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(TEMPLATE)
    return p


def _fmt(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def set_scalar(root, dotted, value):
    """外科手术式写入一个 `段.键`（⛔ 只支持两层，够用且不必引入序列化器）。

    保留注释与其余字节；键不存在则在该段末尾追加；段不存在则在文件末尾新建。
    """
    parts = dotted.split(".")
    if len(parts) != 2:
        raise ValueError("set_scalar 只支持 `段.键` 两层：%s" % dotted)
    sec, key = parts
    p = ensure(root)
    lines = open(p, encoding="utf-8").read().splitlines()

    sec_at = None
    for i, ln in enumerate(lines):
        if ln.rstrip() == sec + ":" or ln.startswith(sec + ":"):
            sec_at = i
            break
    if sec_at is None:
        lines += ["", "%s:" % sec, "  %s: %s" % (key, _fmt(value))]
        open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
        return p

    end = len(lines)
    for j in range(sec_at + 1, len(lines)):
        s = lines[j]
        if s.strip() and not s.startswith((" ", "\t")):
            end = j
            break
    for j in range(sec_at + 1, end):
        st = lines[j].strip()
        if st.startswith(key + ":"):
            indent = lines[j][:len(lines[j]) - len(lines[j].lstrip())]
            lines[j] = "%s%s: %s" % (indent, key, _fmt(value))
            open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
            return p
    # 段内无该键：插在段末最后一行非空之后
    ins = end
    while ins > sec_at + 1 and not lines[ins - 1].strip():
        ins -= 1
    lines.insert(ins, "  %s: %s" % (key, _fmt(value)))
    open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return p


# ───────────────────────── 自检 ─────────────────────────

def _self_check():
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    ok = []
    try:
        # 缺省：文件不存在 → 门禁/护栏开、通知关（存量向后兼容）
        ok.append(("缺省：门禁与护栏开、通知关",
                   commit_gate_enabled(d) and stop_guard_enabled(d)
                   and notify_config(d)["enabled"] is False))
        # 建文件 + 改一个键，注释必须还在
        ensure(d)
        before = open(config_path(d), encoding="utf-8").read()
        set_scalar(d, "commit_gate.enabled", False)
        after = open(config_path(d), encoding="utf-8").read()
        ok.append(("写入后生效", commit_gate_enabled(d) is False))
        ok.append(("★ 注释未被抹掉（yaml.dump 式重写的反向对照）",
                   "关掉之后：commit 前不再检查" in after and before != after))
        ok.append(("其它段未被波及", stop_guard_enabled(d) is True))
        set_scalar(d, "commit_gate.enabled", True)
        ok.append(("改回来也生效", commit_gate_enabled(d) is True))
        # 段内新键 / 全新段
        set_scalar(d, "commit_gate.note", "x")
        set_scalar(d, "brandnew.k", 1)
        data, parsed = load(d)
        ok.append(("段内追加新键", _dig(data, "commit_gate.note") == "x"))
        ok.append(("新建段", str(_dig(data, "brandnew.k")) == "1"))
        ok.append(("追加后仍可解析", parsed))
        ok.append(("模板缺省 project 段为空", project_config(d) == {"name": None, "name_cn": None}))
        set_scalar(d, "project.name_cn", "示例平台")
        ok.append(("project.name_cn 写入后可读", project_config(d)["name_cn"] == "示例平台"))
        ok.append(("模板缺省 cicd 配置可读",
                   cicd_config(d)["provider"] == "github-actions"
                   and cicd_config(d)["pipelines"] == {}))
        # 流式写法：notify.channels / cicd.pipelines
        k = tempfile.mkdtemp()
        os.makedirs(os.path.join(k, "memory"))
        open(os.path.join(k, CONFIG_REL), "w", encoding="utf-8").write(
            "notify:\n  enabled: true\n  channels:\n"
            "    - {type: feishu, webhook_env: AIDP_FEISHU_WEBHOOK}\n"
            "    - type: command\n      command: \"cat\"\n"
            "cicd:\n  pipelines: {dev: deploy-dev.yml, test: \"deploy-test.yml\"}\n")
        nc = notify_config(k)
        ok.append(("★ notify.channels 流式映射被展开",
                   nc["enabled"] is True and len(nc["channels"]) == 2
                   and nc["channels"][0].get("type") == "feishu"
                   and nc["channels"][1].get("command") == "cat"))
        ok.append(("★ cicd.pipelines 流式映射被展开",
                   cicd_config(k)["pipelines"] == {"dev": "deploy-dev.yml", "test": "deploy-test.yml"}))
        shutil.rmtree(k, ignore_errors=True)
        e = tempfile.mkdtemp()
        os.makedirs(os.path.join(e, "memory"))
        # 逃生舱优先级
        open(os.path.join(e, STOP_GUARD_OFF_REL), "w").write("")
        ok.append(("★ touch 逃生舱优先于 yaml 键", stop_guard_enabled(e) is False))
        # 下游判定 fail-closed
        f = tempfile.mkdtemp()
        os.makedirs(os.path.join(f, "memory"))
        open(os.path.join(f, CONFIG_REL), "w", encoding="utf-8").write("commit_gate:\n  enabled: true\n")
        ok.append(("模板态（无版本戳、可解析）→ 判非下游", is_downstream(f) is False))
        set_scalar(f, "scaffold.version", "V1.0.0")
        ok.append(("有版本戳 → 判下游", is_downstream(f) is True))
        # ★ fail-closed：文件被改坏 → 必须判下游（判成模板会静默按模板口径豁免）
        h = tempfile.mkdtemp()
        os.makedirs(os.path.join(h, "memory"))
        open(os.path.join(h, CONFIG_REL), "wb").write(b"\xff\xfe not yaml at all")
        _, ok_h = load(h)
        ok.append(("★ 配置被改坏 → 解析失败可辨", ok_h is False))
        ok.append(("★ 解析失败 fail-closed 判下游（⛔ 不得静默按模板口径豁免）",
                   is_downstream(h) is True))
        shutil.rmtree(h, ignore_errors=True)
        ok.append(("scheduler 缺省：10m / 5m / auto",
                   scheduler_config(d)["dev_interval"] == "10m"
                   and scheduler_config(d)["test_interval"] == "5m"))
        g = tempfile.mkdtemp()
        os.makedirs(os.path.join(g, "memory"))
        open(os.path.join(g, CONFIG_REL), "w", encoding="utf-8").write(
            "scheduler:\n  dev_interval: 15m\n  exec: {codex: \"codex exec {prompt}\"}\n")
        sc = scheduler_config(g)
        ok.append(("scheduler 段可覆盖缺省", sc["dev_interval"] == "15m"
                   and sc["test_interval"] == "5m" and sc["exec"].get("codex") == "codex exec {prompt}"))
        for x in (e, f, g):
            shutil.rmtree(x, ignore_errors=True)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if all(r for _, r in ok) else 1


def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(description="AIDP 人维护配置（memory/aidp-config.yaml）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--self-check", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("get"); g.add_argument("key"); g.add_argument("--root", default=argparse.SUPPRESS)
    s = sub.add_parser("set"); s.add_argument("key"); s.add_argument("value")
    s.add_argument("--root", default=argparse.SUPPRESS)
    sub.add_parser("show").add_argument("--root", default=argparse.SUPPRESS)
    sub.add_parser("ensure").add_argument("--root", default=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    root = a.root
    if a.cmd == "get":
        v = get(root, a.key)
        print("" if v is None else _fmt(v))
        return 0
    if a.cmd == "set":
        raw = a.value
        val = True if raw == "true" else False if raw == "false" else raw
        set_scalar(root, a.key, val)
        return 0
    if a.cmd == "ensure":
        print(ensure(root))
        return 0
    data, okp = load(root)
    print(json.dumps({"path": config_path(root), "parse_ok": okp,
                      "project": project_config(root),
                      "commit_gate_enabled": commit_gate_enabled(root),
                      "notify": notify_config(root),
                      "cicd": cicd_config(root),
                      "stop_guard_enabled": stop_guard_enabled(root),
                      "scheduler": scheduler_config(root),
                      "scaffold_version": scaffold_version(root),
                      "is_downstream": is_downstream(root),
                      "data": data}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
