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
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import os
import sys

CONFIG_REL = os.path.join("memory", "aidp-config.yaml")

# Stop 护栏的盲打逃生舱（`touch` 即关，优先级高于 yaml 键）
STOP_GUARD_OFF_REL = os.path.join("memory", ".autopilot-stop-guard-off")

TEMPLATE = runtime_text("# AIDP 项目配置（**人维护**，团队共享、随 git 提交）\n#\n# 这是你可以直接改的那一份。程序写的运行时状态在\n# memory/.sprint-autopilot-baseline.json —— 那份别手动动，会被下一轮覆盖。\n#\n# 改完无需重启任何东西，下一次命令运行即生效。\n# 例外：scheduler.dev_interval / test_interval（调度周期）已写进操作系统定时任务，改后须重跑\n# aidp_scheduler.py install 才生效（watchdog / status 优先读上次安装快照）。\n\nproject:\n  # 项目标识。name = 英文应用编码（默认 git 仓库目录名）；name_cn = 对外中文名称，\n  # 里程碑通知标题、OpenAPI 文档标题、子项目默认命名取它（缺省回退 name → git 仓库名）。\n  name: null\n  name_cn: null\n  # 目标数据库方言（可空，通用键）。null = 通用，不启用任何库专项规则；非空时原样透传给\n  # SKILL 脚本的 --db / --sql-db 参数（可取值以 SKILL 当前识别的为准，本文件不枚举）。\n  # 由用户在技术选型确认数据库后记录，Agent 不自行推断。\n  sql_dialect: null\n\ndevelopment:\n  # 首次修改需求或修复漏洞前由用户选择，之后在本项目沿用。\n  # null = 尚未选择；current = 直接在当前分支修改；new = 每次独立任务新建分支。\n  # 只记录开发偏好，不创建分支，也不替代部署源对齐或版本发布规则。\n  branch_policy: null\n\n# 可选执行策略；null 表示普通开发/修复默认实现、必要静态检查及本任务相关单测。\n# 额外动作仅采纳明确用户选择的 project-policy 来源，不迁移旧模板自动开关。\n# 来源键 authorization_source 由 Agent 在用户明确选择后记录，不要自行手填；形如：\n#   execution_policy: {authorization_source: {kind: project-policy, user_selected: true, request_id: <请求标识>, text: <用户原话>}}\nexecution_policy: null\n\ncommit_gate:\n  # 提交前门禁总开关（约定 24：每次 git commit 前跑 __AIDP_HOME__/scripts/commit_gate.py）。\n  # 关掉之后：不再检查台账积压 / CICD 推送欠账。\n  enabled: true\n\nnotify:\n  # 里程碑通知总开关（约定 32：__AIDP_HOME__/scripts/notify.py）。\n  # 未开启或未配置任何渠道时，播报节点静默跳过，不阻断链路。\n  enabled: false\n  # 一个渠道失败时是否尝试下一个\n  fallback: true\n  # autopilot 启动时是否发 #0a「渠道已连通」通知（默认不发，避免噪音）\n  channel_ready_card: false\n  # 渠道按顺序尝试，成功即停。⛔ webhook 地址 / 密钥只经环境变量引用，不明文入库。\n  channels: []\n  # 例：\n  #   - {type: feishu, webhook_env: AIDP_FEISHU_WEBHOOK, secret_env: AIDP_FEISHU_SECRET}\n  #   - {type: dingtalk, webhook_env: AIDP_DINGTALK_WEBHOOK, secret_env: AIDP_DINGTALK_SECRET}\n  #   - {type: wecom, webhook_env: AIDP_WECOM_WEBHOOK}\n  #   - {type: lark-cli, chat_id: \"<chat id>\"}\n  #   - {type: command, command: \"<读 stdin JSON 的发送命令>\"}\n\ncicd:\n  # CICD 提供方（约定 31.5）：github-actions（默认）/ gitlab-ci / jenkins / command / none。\n  provider: github-actions\n  # 兼容旧键（默认值 false，不表达禁令）：单独设 true 或 false 都不改变行为（旧布尔不是授权，是否触发以当次 deploy 授权为准）。\n  # 只有同时存在用户明确选择的禁用来源 auto_trigger_source（kind: project-policy，结构同\n  # execution_policy.authorization_source，由 Agent 在用户明确要求禁止自动触发后记录，不要手填）\n  # 且 auto_trigger: false，才拦截自动触发 / 重试。\n  auto_trigger: false\n  max_retries: 3\n  # 部署环境 → 流水线标识。github-actions = workflow 文件名；gitlab-ci = 分支名（可留空）；\n  # jenkins = Job 路径；command = 原样代入命令模板的 {pipeline}。例：{test: deploy-test.yml}\n  pipelines: {}\n  # 各提供方专属参数（只填所选那个）。⛔ 令牌 / 密码只写环境变量名。\n  # gitlab-ci: {url: https://gitlab.com, project: group/name, token_env: AIDP_GITLAB_TOKEN}\n  # jenkins:   {url: https://jenkins.example.com, user_env: AIDP_JENKINS_USER, token_env: AIDP_JENKINS_TOKEN}\n  # command:   {list: \"...\", view: \"...\", trigger: \"...\", retry: \"...\", check: \"...\"}\n  # ★ 本项目「推送即自动部署」吗（约定 31.5）：true = 推送本身就是触发，⛔ 不再主动触发流水线。\n  # 只记事实、不改 CICD 配置。由 `__AIDP_HOME__/scripts/aidp_state.py cicd-push-autodeploy-yes|-no` 写。\n  push_auto_deploy: false\n  # 推送即自动部署时，推送后最短等待秒数：等满仍取不到流水线状态 → cicd_watch.py 返回 rc=4\n  # （降级放行就绪探针），⛔ 不冻结。防的是「流水线无法被单独触发 + 平台取不到状态」时链路被误冻\n  # 且无恢复路径 —— 那种项目里主动触发恒失败，按失败熔断等于永不放行。\n  push_deploy_min_wait_seconds: 300\n\ndeployment:\n  # 备份策略沿项目既有设置；null 不授权备份，也不假定当天零次。\n  # 接入字段与真实记录格式见 __AIDP_HOME__/reference/部署操作约定.md。\n  # DB/完整冷备/迁移快照共用 record_file、max_per_day、timezone。\n  # commands 仅填既有 argv，skip_args 仅填现有部署脚本实际支持的参数。\n  # 可选 timeout_seconds：项目备份命令的超时秒数（缺省 3600）。\n  backup: null\n\nstop_guard:\n  # autopilot Stop 护栏（防止无人值守链路在未收口时静默停下）。\n  # 关掉 = 临时逃生舱：护栏误报把你挡住时用，⛔ 排除故障后记得改回 true。\n  enabled: true\n\nscheduler:\n  # 7×24 操作系统调度（python3 __AIDP_HOME__/scripts/aidp_scheduler.py install）：\n  # 开发、测试链路各一个用户级定时任务，另装独立 watchdog 巡检（默认 5m）；两链路互不阻塞。\n  dev_interval: 10m\n  test_interval: 5m\n  # 执行 Agent：auto（按 agent_env.py detect）/ claude / codex / dsh\n  agent: auto\n  # 任一链路连续多少个周期无心跳即本地告警（memory/.aidp/alerts.jsonl）+ 里程碑通知\n  stale_cycles: 3\n  # 单轮 tick 的硬上限（秒）。⛔ 它防的是最安静的一种故障：Agent 进程挂死 → 互斥锁被永久\n  # 持有 → 之后每次调度都「上一轮仍在运行，跳过」→ watchdog 永远判 running → 零告警停摆。\n  # agent_loop.sh 用它给 tick 套 timeout（环境变量 AIDP_TICK_MAX_SECONDS 优先，默认 7200）；\n  # watchdog 用 max(stale 阈值, 本值 + 180s 收尾宽限, 1h) 作「持锁超期 = 挂死」的判据（环境变量覆盖后同样生效）。\n  # 0 = 不设上限（不推荐）。\n  tick_max_seconds: 7200\n  # 各 Agent 的非交互执行命令模板（{prompt} 为占位符）；留空用内置默认。\n  # ⛔ 内置默认之外的 CLI 写法请按所用 Agent 当前版本的官方文档自行确认。\n  exec: {}\n  # 例：exec: {codex: \"codex exec --sandbox workspace-write {prompt}\"}\n\nscaffold:\n  # 本项目上次同步到的脚手架版本号。**由 aidp-code-engineer 脚手架写入，人别改**——\n  # 改小会触发不必要的全量覆盖，改大会让真正的升级被跳过。\n  version: null\n  # 升级中途留下的待消费语义改写队列；非 null 表示**上一轮升级尚未真正交付**。\n  pending: null\n\n# autopilot 决策兜底（★ 权威是本版 PRD frontmatter 的 autopilot_decisions 段，\n# 本段仅在 PRD 未声明时生效；全项目一份、无版本维度）。\nautopilot_decisions: {}\n", __file__)


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
        text = _AidpPath(p).read_text(encoding="utf-8")
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


def sql_dialect(root="."):
    """目标数据库方言（`project.sql_dialect`）→ 非空字符串 | None（None = 通用，不透传）。

    只做原样读取，不枚举库名、不推断；空串 / `null` / 模板占位一律视为未配置。
    """
    data, _ = load(root)
    sec = _dig(data, "project")
    return _str_or_none(sec.get("sql_dialect")) if isinstance(sec, dict) else None


def validate_branch_policy(value):
    """仅接受未选择或两种用户偏好；非法值不能静默退回当前分支。"""
    if value is not None and value not in ("current", "new"):
        raise ValueError("development.branch_policy 必须为 null、current 或 new")
    return value


def read_branch_policy(root="."):
    """读取项目偏好，不创建配置、不探测或修改 Git。"""
    data, ok = load(root)
    if not ok or not isinstance(data, dict):
        raise ValueError("无法解析 memory/aidp-config.yaml")
    section = data.get("development")
    if section is None:
        return None
    if not isinstance(section, dict):
        raise ValueError("development 必须是配置映射")
    return validate_branch_policy(section.get("branch_policy"))


def read_execution_policy(root="."):
    """只读用户明确选择的执行策略；旧模板开关、缺来源和占位值不产生授权。"""
    data, ok = load(root)
    if not ok or not isinstance(data, dict):
        raise ValueError("无法解析 memory/aidp-config.yaml")
    policy = data.get("execution_policy")
    if policy is None:
        return None
    if not isinstance(policy, dict):
        return None  # 旧模板 true/auto 等值不是用户选择。
    source = policy.get("authorization_source")
    if not isinstance(source, dict) or source.get("kind") != "project-policy":
        return None
    from execution_policy import validate_source
    try:
        validate_source(source)
    except ValueError:
        return None
    return policy


def branch_policy(root="."):
    """只读业务修改前置：未选择的 Git 项目需交互，无 Git 项目不适用。"""
    from vcs import detect_mode

    mode = detect_mode(root)
    policy = read_branch_policy(root)
    needs_choice = mode == "git" and policy is None
    return {"vcs_mode": mode, "policy": policy, "needs_choice": needs_choice,
            "status": "not-applicable" if mode == "none" else
                      "needs-choice" if needs_choice else "ready"}


def commit_gate_enabled(root="."):
    """提交前门禁总开关（约定 24）：`commit_gate.enabled`，缺省 True。"""
    return get_bool(root, "commit_gate.enabled", True)


def notify_config(root="."):
    """里程碑通知配置（约定 32）→ {enabled, fallback, channel_ready_card, channels}。

    缺省 `enabled=False` / `channels=[]`：未配置渠道的项目不发任何通知。

    ⚠️ `channel_ready_card` 必须在返回集里：流程正文写「仅当它为 true 才发 #0a」，
    读方取不到该键就只能按缺省的 false 走 —— 用户打开了开关却没有任何确定性效果，
    与「没打开」完全同形（正是「只说不做」的配置项）。
    """
    data, _ = load(root)
    sec = _dig(data, "notify")
    sec = sec if isinstance(sec, dict) else {}
    chans = sec.get("channels")
    chans = [c for c in chans if isinstance(c, dict)] if isinstance(chans, list) else []
    return {
        "enabled": get_bool(root, "notify.enabled", False),
        "fallback": get_bool(root, "notify.fallback", True),
        "channel_ready_card": get_bool(root, "notify.channel_ready_card", False),
        "channels": chans,
    }


def cicd_config(root="."):
    """CICD 配置（约定 31.5）→ {provider, auto_trigger, max_retries, pipelines,
    push_auto_deploy, push_deploy_min_wait_seconds, <provider>: {...}}。

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
    try:
        min_wait = int(sec.get("push_deploy_min_wait_seconds", 300))
    except (TypeError, ValueError):
        min_wait = 300
    source = sec.get("auto_trigger_source")
    from execution_policy import validate_source
    try:
        source = validate_source(source)
        if source["kind"] != "project-policy":
            source = None
    except ValueError:
        source = None
    auto_trigger = get_bool(root, "cicd.auto_trigger", False)
    out = {
        "provider": str(sec.get("provider") or "github-actions"),
        "auto_trigger": auto_trigger,
        "auto_trigger_source": source,
        "auto_trigger_explicitly_disabled": bool(source and not auto_trigger),
        "max_retries": retries,
        "pipelines": pl,
        # ⛔ 新增键必须在这里显式登记：本函数是**白名单式构造**，不是原样透传 ——
        #    漏登记的键对所有消费者恒取缺省，且不报错（配置写了也不生效）。
        "push_auto_deploy": get_bool(root, "cicd.push_auto_deploy", False),
        "push_deploy_min_wait_seconds": min_wait if min_wait > 0 else 300,
    }
    for name in ("github-actions", "gitlab-ci", "jenkins", "command"):
        if isinstance(sec.get(name), dict):
            out[name] = sec[name]
    return out

def cicd_push_deploy_min_wait(root="."):
    """推送即自动部署时，推送后最短等待秒数（`cicd.push_deploy_min_wait_seconds`，缺省 300）。

    ⛔ 不接受 0/负数：那等于"不等就降级放行"，把「推送后还没来得及起跑」误判成
    「平台取不到状态」，于是每次都降级、CICD 观测形同虚设。
    """
    raw = (cicd_config(root) or {}).get("push_deploy_min_wait_seconds")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 300
    return value if value > 0 else 300


def cicd_push_auto_deploy(root="."):
    """本项目是否已记录「推送即自动部署」（`cicd.push_auto_deploy`，缺省 False）。"""
    return bool((cicd_config(root) or {}).get("push_auto_deploy"))


def stop_guard_enabled(root="."):
    """Stop 护栏开关。

    `touch memory/.autopilot-stop-guard-off` 逃生舱优先级最高：护栏误报把人挡住时，
    那一刻需要的是一条能盲打的命令，不是「去 yaml 里找一个键」。
    """
    if os.path.exists(os.path.join(root, STOP_GUARD_OFF_REL)):
        return False
    return get_bool(root, "stop_guard.enabled", True)


SCHEDULER_DEFAULTS = {"dev_interval": "10m", "test_interval": "5m", "agent": "auto",
                      "stale_cycles": 3, "tick_max_seconds": 7200, "exec": {}}


def scheduler_config(root="."):
    """7×24 操作系统调度配置（`scheduler` 段）→
    {dev_interval, test_interval, agent, stale_cycles, tick_max_seconds, exec}。

    ⚠️ `tick_max_seconds` 必须在返回集里：挂死判据按它取 `max(stale 阈值, 本值, 1h)`，
    读方取不到就恒取 0，用户配的 `7200` 静默失效 —— 而「配了但读不到」与「没配」同形。
    """
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
    try:
        tick_max = int(sec.get("tick_max_seconds", 7200))
    except (TypeError, ValueError):
        tick_max = 7200
    # 0 = 显式关闭上限（合法），负数按非法落回缺省
    out["tick_max_seconds"] = tick_max if tick_max >= 0 else 7200
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


def _set_inline_branch_policy(line, value):
    """仅处理 development 内联映射；按原始跨度替换，保留额外键与注释。"""
    from autopilot_decisions_merge import _strip_comment

    content = _strip_comment(line)
    raw = content.split(":", 1)[1].lstrip()
    if not raw.startswith("{"):
        return None
    if not raw.endswith("}"):
        raise ValueError("development 内联映射不完整")
    begin = content.index("{", content.index(":") + 1) + 1
    end = len(content) - 1
    body = line[begin:end]
    matches, cursor = [], 0
    for item in _split_flow(body):
        offset = body.index(item, cursor)
        cursor = offset + len(item)
        key, separator, old = item.partition(":")
        if separator and _flow_scalar(key) == "branch_policy":
            start = offset + len(key) + 1 + len(old) - len(old.lstrip())
            matches.append((begin + start, begin + offset + len(item)))
    if len(matches) > 1:
        raise ValueError("development.branch_policy 重复，无法确定写入位置")
    if matches:
        start, stop = matches[0]
        return line[:start] + _fmt(value) + line[stop:]
    # 没有此键时追加到同一映射中，不能在映射后另塞一份块式配置。
    trimmed = body.rstrip()
    at = begin + len(trimmed)
    separator = (" " if trimmed.endswith(",") else ", ") if trimmed else ""
    return line[:at] + separator + "branch_policy: " + _fmt(value) + line[at:]


def set_scalar(root, dotted, value):
    """外科手术式写入一个 `段.键`（⛔ 只支持两层，够用且不必引入序列化器）。

    保留注释与其余字节；键不存在则在该段末尾追加；段不存在则在文件末尾新建。
    """
    parts = dotted.split(".")
    if len(parts) != 2:
        raise ValueError("set_scalar 只支持 `段.键` 两层：%s" % dotted)
    sec, key = parts
    if dotted == "development.branch_policy":
        validate_branch_policy(value)
    p = ensure(root)
    lines = _AidpPath(p).read_text(encoding="utf-8").splitlines()

    sec_at = None
    for i, ln in enumerate(lines):
        if ln.rstrip() == sec + ":" or ln.startswith(sec + ":"):
            sec_at = i
            break
    if sec_at is None:
        lines += ["", "%s:" % sec, "  %s: %s" % (key, _fmt(value))]
        _AidpPath(p).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    if dotted == "development.branch_policy":
        inline = _set_inline_branch_policy(lines[sec_at], value)
        if inline is not None:
            lines[sec_at] = inline
            _AidpPath(p).write_text("\n".join(lines) + "\n", encoding="utf-8")
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
            _AidpPath(p).write_text("\n".join(lines) + "\n", encoding="utf-8")
            return p
    # 段内无该键：插在段末最后一行非空之后
    ins = end
    while ins > sec_at + 1 and not lines[ins - 1].strip():
        ins -= 1
    lines.insert(ins, "  %s: %s" % (key, _fmt(value)))
    _AidpPath(p).write_text("\n".join(lines) + "\n", encoding="utf-8")
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
                   "关掉之后：不再检查台账积压" in after and before != after))
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
        ok.append(("模板缺省 sql_dialect 为空（通用）", sql_dialect(d) is None))
        set_scalar(d, "project.sql_dialect", "x-db")
        ok.append(("project.sql_dialect 写入后原样可读", sql_dialect(d) == "x-db"))
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
    sub.add_parser("branch-policy", help="只读查询开发分支偏好与首次选择状态").add_argument(
        "--root", default=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    if a.self_check:
        return _self_check()
    root = a.root
    if a.cmd == "branch-policy":
        try:
            result = branch_policy(root)
        except ValueError as exc:
            from vcs import detect_mode
            print(json.dumps({"vcs_mode": detect_mode(root), "policy": None,
                              "needs_choice": False, "status": "invalid",
                              "error": str(exc)}, ensure_ascii=False))
            return 2
        print(json.dumps(result, ensure_ascii=False))
        return 3 if result["needs_choice"] else 0
    if a.cmd == "get":
        v = get(root, a.key)
        print("" if v is None else _fmt(v))
        return 0
    if a.cmd == "set":
        raw = a.value
        val = True if raw == "true" else False if raw == "false" else raw
        if a.key == "development.branch_policy" and raw == "null":
            val = None
        try:
            set_scalar(root, a.key, val)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return 0
    if a.cmd == "ensure":
        print(ensure(root))
        return 0
    data, okp = load(root)
    print(json.dumps({"path": config_path(root), "parse_ok": okp,
                      "project": project_config(root),
                      "sql_dialect": sql_dialect(root),
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
