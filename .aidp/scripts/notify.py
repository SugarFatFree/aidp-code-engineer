#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notify.py —— 里程碑通知发送器（约定 32）。

调用方只给**字段**（--title / --section / --link-* / --footer），本脚本构造一个**中性卡片模型**，
再按渠道渲染并发送；成功后（给了 --node 时）登记 ceremony gate 通知台账。

为什么是字段入参 + 脚本渲染：
  1. 手拼 JSON：正文含中文 + 一个 ASCII 双引号就让整份 JSON 解析失败。
     → 序列化与转义全部交给 json.dumps，调用方⛔ 不手拼 JSON。
  2. 台账必须如实：发送失败不得记成「已发」。
     → 发送成功登记 `status=sent`；失败 / 无可用渠道登记 `status=undelivered` 并非零退出。
  3. 标题漏项目名：每条通知标题恒为 `{emoji} {项目名称} {version}[_Build{N}] · {本卡标题}`。
     → 发送前确定性补齐项目名称与版本号（见 ensure_title_prefix），不依赖执行体自律。
  4. 渠道回落写在散文里就会在没被读到时整体失效。
     → `--auto` 在代码里按 `memory/aidp-config.yaml` 的 `notify.channels` 依次尝试，成功即停。
  5. 告警在无渠道时也必须「停得响」。
     → `--node #4` 或 `--alert` 的调用无论发送成败都追加本地告警台账 `memory/.aidp/alerts.jsonl`
       并在 stderr 打印 `🚨 [AIDP-ALERT]` 一行（`delivered` 字段记录是否送达）。
  6. 里程碑节点发送失败 / 无可用渠道时，`--node` 仍以 `status=undelivered` 登记台账，
     收尾门据此判「已尝试、未送达」= DEGRADE，不把通知故障升级成流程冻结。

渠道（`notify.channels[].type`）：
  feishu    飞书自定义机器人 webhook（interactive 卡片；可选签名校验）
            {type: feishu, webhook_env: AIDP_FEISHU_WEBHOOK, secret_env: AIDP_FEISHU_SECRET}
  dingtalk  钉钉自定义机器人 webhook（markdown 消息；可选加签）
            {type: dingtalk, webhook_env: AIDP_DINGTALK_WEBHOOK, secret_env: AIDP_DINGTALK_SECRET}
  wecom     企业微信群机器人 webhook（markdown 消息）
            {type: wecom, webhook_env: AIDP_WECOM_WEBHOOK}
  lark-cli  飞书官方 CLI 发到指定会话；命令不存在视为该渠道不可用
            {type: lark-cli, chat_id: "<chat id>"[, args: [...]]}
            args 可覆盖默认参数表，支持占位 {chat_id} {card_json} {markdown} {title}
  command   自定义命令，从 stdin 读中性 JSON；退出码 0 = 成功、3 = 渠道不可用、其它非零 = 发送失败
            {type: command, command: "<命令>"}
  ⛔ webhook 地址与密钥只经 `*_env` 指定的环境变量读取，配置文件里不出现明文。

两种发送形态（互斥）：
  --sender '<命令>'  调用方指定发送命令（stdin 收中性 JSON，退出码约定同 command 渠道）。
  --auto             ★ 推荐：按 notify.channels 依次尝试。

用法：
  notify.py --title "标题" [--header-color blue] \\
    --section "**字段：** 值　|　**状态：** ✅" \\
    --section-file /tmp/section.md \\
    [--link-text "打开报告" --link-url "docs/reports/xxx.html"] \\
    [--footer "自动生成 · sprint-autopilot"] \\
    --auto \\
    [--node '#F' --version V0.11 --build V0.11_build1001 \\
     --gate AIDP_HOME/scripts/autopilot-ceremony-gate.py]    # 登记台账（成功 = sent，失败 = undelivered）
    [--alert]                                             # 告警类：恒写本地告警台账
    [--project-name '<项目中文名>']                       # 不传则自动解析
  notify.py --title ... --section ... --print-only        # 只构造并打印中性 JSON 与各渠道渲染结果
  notify.py --check-config [--repo-root .] [--json]        # 离线查通用 schema/本地条件，不发送探测
  notify.py --title ... --section ... --auto --report-kind test --version V0.1 --build V0.1_build1001
                                                        # 读已有报告和交付台账，URL/回落说明确定性生成
  notify.py --check-name [--json]                         # 只查项目名称解析结果
  notify.py --self-check                                  # 离线自测（本地 HTTP 桩，不发外网）

退出码：0 = 发送成功（给了 --node 则已尝试登记台账）；1 = 已尝试的渠道全部失败（--node 登记为 undelivered）；
       2 = 参数 / 构造错误；3 = 未配置任何可用渠道（notify.enabled=false / channels 为空 /
       所有渠道缺凭据或命令 / 自定义命令返回 3）——合规降级：调用方静默跳过本播报节点。
       ⛔ 1 与 3 都不是「去问用户」的信号：两种情况都静默跳过本节点、不阻塞主流程。
       `--check-name` 只拿到英文兜底名时也返回 3。
--section / --footer 里的字面 "\\n" 会被转成真实换行（书写便利）。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import runtime_text
import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHANNEL_TYPES = ("feishu", "lark-cli", "dingtalk", "wecom", "command")
HTTP_TIMEOUT = 15
WECOM_MD_LIMIT = 4000   # 企业微信 markdown content 上限 4096 字节，留余量


def _unescape_nl(s):
    return s.replace("\\n", "\n") if s else s


# ── 标题前缀兜底：项目中文名称解析 + 补齐 ────────────────────────────────────
# 项目标识来自 memory/aidp-config.yaml 的 `project` 段：
#   `name_cn` —— 对外中文名，标题**首选**
#   `name`    —— 英文应用编码，只作兜底
# 未填写的占位值（模板残留），一律不当作有效项目名。
# ⚠️ 必须逐个登记：`_CJK` 只判「有没有汉字」，「待填充」三个字全是汉字。
_PLACEHOLDER = {"", "-", "—", "待填写", "待填充", "待补充", "{{project}}", "{project}",
                "<项目名称>", "<中文名>", "TBD", "N/A"}
# 标题开头的 emoji / 符号串（只认 emoji 相关码位 + 空白，绝不吞掉 `/` `#` 等正文字符）
_EMOJI_LEAD = re.compile(
    "^(?:["
    "←-⇿"
    "⌀-⏿"
    "①-⓿"
    "■-➿"
    "⬀-⯿"
    "\U0001F000-\U0001FAFF"
    "️‍⃣"
    "]|\\s)+"
)
_CJK = re.compile("[一-鿿]")


def _project_field(repo_root, key):
    """读 aidp_config.project_config 的 name / name_cn；缺配置 / 占位值一律返回空串。"""
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import aidp_config
        v = (aidp_config.project_config(repo_root).get(key) or "").strip()
    except Exception:  # noqa: BLE001 — 读不到就走下一档兜底
        return ""
    return "" if v in _PLACEHOLDER else v


def _git_root_name(repo_root):
    try:
        r = subprocess.run(["git", "-C", repo_root, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return os.path.basename(r.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.basename(os.path.abspath(repo_root))


def resolve_project_name(repo_root, explicit=""):
    """解析标题用的项目名称 → (name, source, is_ascii_fallback)。

    ★ 判据是「这个值是不是中文名」，不是「哪一层先有值」：中文候选整体优先于英文候选。
      中文档：--project-name → env AIDP_PROJECT_NAME → project.name_cn → project.name
      英文档：同序的英文值 → git 根目录名
    任何分支都返回非空值。
    """
    ascii_fallbacks = []
    for v, src in (
        (explicit, "--project-name"),
        (os.environ.get("AIDP_PROJECT_NAME"), "env:AIDP_PROJECT_NAME"),
        (_project_field(repo_root, "name_cn"), "aidp-config project.name_cn"),
        (_project_field(repo_root, "name"), "aidp-config project.name"),
    ):
        v = (v or "").strip()
        if not v:
            continue
        if _CJK.search(v):
            return v, src, False
        ascii_fallbacks.append((v, src))
    if ascii_fallbacks:
        v, src = ascii_fallbacks[0]
        return v, src, True
    return (_git_root_name(repo_root) or "未命名项目"), "git 根目录名", True


def ensure_title_prefix(title, project_name, version=""):
    """补齐 `{emoji} {项目名称} {version}[_Build{N}] · {本卡标题}`，返回 (new_title, patched_parts)。

    - 项目名称不在标题里 → 插到 emoji 之后（恒补）；
    - 给了 --version 且标题里没有 → 一并补在项目名称之后；
    - `_Build{N}` 是条件段，由调用方按语义写，这里不臆造。
    """
    patched = []
    t = (title or "").strip()
    lead = _EMOJI_LEAD.match(t)
    prefix = lead.group(0).rstrip() if lead else ""
    rest = t[lead.end():] if lead else t
    inject = []
    if project_name and project_name not in t:
        inject.append(project_name)
        patched.append("项目名称")
    if version and version not in t:
        inject.append(version)
        patched.append("版本号")
    if not inject:
        return t, patched
    parts = ([prefix] if prefix else []) + inject + ([rest] if rest else [])
    return " ".join(parts), patched


# ── 中性卡片模型 ──────────────────────────────────────────────────────────────

def build_message(title, header_color, sections, link_text, link_url, footer,
                  project="", version="", build="", node=""):
    """中性卡片模型：与渠道无关，所有渲染器都只读它。"""
    return {
        "schema": "aidp.notify/v1",
        "title": title,
        "color": header_color or "blue",
        "sections": [_unescape_nl(s) for s in sections],
        "link": ({"text": link_text or "打开链接", "url": link_url} if link_url else None),
        "footer": _unescape_nl(footer) or "",
        "meta": {"project": project, "version": version, "build": build, "node": node},
    }


def render_feishu_card(msg):
    """飞书 interactive 卡片体（card 字段）。"""
    elements = []
    for i, sec in enumerate(msg["sections"]):
        if i > 0:
            elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {"tag": "lark_md", "content": sec}})
    if msg.get("link"):
        elements.append({"tag": "hr"})
        elements.append({"tag": "div", "text": {
            "tag": "lark_md", "content": f"[{msg['link']['text']}]({msg['link']['url']})"}})
    if msg.get("footer"):
        elements.append({"tag": "note", "elements": [{"tag": "plain_text", "content": msg["footer"]}]})
    return {
        "config": {"wide_screen_mode": True},
        "header": {"template": msg.get("color") or "blue",
                   "title": {"tag": "plain_text", "content": msg["title"]}},
        "elements": elements,
    }


def render_markdown(msg):
    """通用 markdown 正文（钉钉 / 企业微信 / lark-cli 的 {markdown} 占位）。"""
    parts = [f"### {msg['title']}"]
    parts += [s for s in msg["sections"]]
    if msg.get("link"):
        parts.append(f"[{msg['link']['text']}]({msg['link']['url']})")
    if msg.get("footer"):
        parts.append(f"> {msg['footer']}")
    return "\n\n".join(parts)


def feishu_sign(timestamp, secret):
    """飞书：string_to_sign = timestamp + "\\n" + secret 作 HmacSHA256 的 key、对空串签名，再 base64。"""
    key = f"{timestamp}\n{secret}".encode("utf-8")
    return base64.b64encode(hmac.new(key, b"", hashlib.sha256).digest()).decode("ascii")


def dingtalk_sign(timestamp_ms, secret):
    """钉钉：以 secret 为 key 对 timestamp + "\\n" + secret 做 HmacSHA256 → base64 → urlencode。"""
    raw = hmac.new(secret.encode("utf-8"), f"{timestamp_ms}\n{secret}".encode("utf-8"),
                   hashlib.sha256).digest()
    return urllib.parse.quote_plus(base64.b64encode(raw).decode("ascii"))


def render_feishu_payload(msg, secret="", now=None):
    body = {"msg_type": "interactive", "card": render_feishu_card(msg)}
    if secret:
        ts = str(int(now if now is not None else time.time()))
        body["timestamp"] = ts
        body["sign"] = feishu_sign(ts, secret)
    return body


def render_dingtalk(msg, webhook, secret="", now=None):
    body = {"msgtype": "markdown", "markdown": {"title": msg["title"], "text": render_markdown(msg)}}
    url = webhook
    if secret:
        ts = str(int((now if now is not None else time.time()) * 1000))
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}timestamp={ts}&sign={dingtalk_sign(ts, secret)}"
    return url, body


def render_wecom(msg):
    content = render_markdown(msg)
    raw = content.encode("utf-8")
    if len(raw) > WECOM_MD_LIMIT:
        content = raw[:WECOM_MD_LIMIT].decode("utf-8", errors="ignore") + "\n…"
    return {"msgtype": "markdown", "markdown": {"content": content}}


# ── 渠道发送 ─────────────────────────────────────────────────────────────────

class Unavailable(Exception):
    """渠道当前不可用（缺环境变量 / 缺命令 / 缺 chat_id）——不算一次失败的发送。"""


# command 渠道 / --sender 的自定义命令用退出码 3 声明「渠道不可用」（未登录、未配置等），
# 与本脚本自身的 3 同义；其它非零才是「发送失败」
COMMAND_UNAVAILABLE_RC = 3


def _env(ch, key, required):
    name = str(ch.get(key) or "").strip()
    if not name:
        if required:
            raise Unavailable(f"未配置 {key}")
        return ""
    val = os.environ.get(name, "").strip()
    if not val and required:
        raise Unavailable(f"环境变量 {name} 未设置")
    return val


def _post_json(url, body, timeout=HTTP_TIMEOUT):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except (urllib.error.URLError, OSError, ValueError) as e:
        return False, f"请求失败：{e}"
    try:
        j = json.loads(text) if text.strip() else {}
    except ValueError:
        j = None
    if status >= 300:
        return False, f"HTTP {status}: {text[:200]}"
    if isinstance(j, dict):
        for k in ("code", "errcode", "StatusCode"):
            if k in j and j[k] not in (0, "0", None):
                return False, f"{k}={j[k]} {j.get('msg') or j.get('errmsg') or j.get('StatusMessage') or ''}".strip()
    return True, text[:200]


def _run_stdin(argv, payload, timeout=60):
    try:
        r = subprocess.run(argv, input=payload, text=True, capture_output=True, timeout=timeout)
    except FileNotFoundError as e:
        raise Unavailable(f"命令不存在：{e}")
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"调用异常：{e}"
    diag = (r.stderr or r.stdout or "").strip()[:300]
    if r.returncode == COMMAND_UNAVAILABLE_RC:
        raise Unavailable(diag or f"命令返回 {COMMAND_UNAVAILABLE_RC}：渠道不可用")
    return r.returncode == 0, diag or f"rc={r.returncode}"


def _lark_cli_argv(ch, msg):
    chat_id = str(ch.get("chat_id") or "").strip()
    if not chat_id:
        raise Unavailable("未配置 chat_id")
    exe = shutil.which(str(ch.get("bin") or "lark-cli"))
    if not exe:
        raise Unavailable("lark-cli 命令不存在")
    card_json = json.dumps(render_feishu_card(msg), ensure_ascii=False)
    subs = {"chat_id": chat_id, "card_json": card_json, "markdown": render_markdown(msg),
            "title": msg["title"]}
    tmpl = ch.get("args")
    if isinstance(tmpl, list) and tmpl:
        return [exe] + [str(a).format(**subs) for a in tmpl]
    # 飞书官方 CLI（larksuite/cli）：`im +messages-send --msg-type interactive --content <卡片 JSON>`，
    # 以机器人身份发送；卡片 JSON 为 card 体本身（不含 webhook 的 msg_type 外壳）。
    return [exe, "im", "+messages-send", "--as", str(ch.get("as") or "bot"), "--chat-id", chat_id,
            "--msg-type", "interactive", "--content", card_json]


def send_channel(ch, msg):
    """用一个渠道发送。返回 (ok, diag)；渠道不可用抛 Unavailable。"""
    ready, detail = channel_ready(ch)
    if not ready:
        raise Unavailable(detail + "；修复 memory/aidp-config.yaml 的 notify.channels 后运行 notify.py --check-config --json")
    typ = str(ch.get("type") or "").strip()
    if typ == "feishu":
        url = _env(ch, "webhook_env", True)
        return _post_json(url, render_feishu_payload(msg, _env(ch, "secret_env", False)))
    if typ == "dingtalk":
        url = _env(ch, "webhook_env", True)
        u, body = render_dingtalk(msg, url, _env(ch, "secret_env", False))
        return _post_json(u, body)
    if typ == "wecom":
        return _post_json(_env(ch, "webhook_env", True), render_wecom(msg))
    if typ == "lark-cli":
        argv = _lark_cli_argv(ch, msg)
        try:
            r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            raise Unavailable("lark-cli 命令不存在")
        except (OSError, subprocess.SubprocessError) as e:
            return False, f"调用异常：{e}"
        return r.returncode == 0, ((r.stderr or r.stdout or "").strip()[:300] or f"rc={r.returncode}")
    if typ == "command":
        cmd = str(ch.get("command") or "").strip()
        if not cmd:
            raise Unavailable("未配置 command")
        return _run_stdin(shlex.split(cmd), json.dumps(msg, ensure_ascii=False))
    raise Unavailable(f"未知渠道类型：{typ or '(空)'}")


def _channel_config_error(ch):
    """只检通用 schema；不推断 command 的目标参数，也不把本地能力当迁移证据。"""
    if not isinstance(ch, dict):
        return "渠道必须是对象"
    typ = str(ch.get("type") or "").strip()
    if typ not in CHANNEL_TYPES:
        return f"未知渠道类型：{typ or '空'}"
    required = "webhook_env" if typ in ("feishu", "dingtalk", "wecom") else "chat_id" if typ == "lark-cli" else "command"
    value = ch.get(required)
    if not isinstance(value, str) or not value.strip() or value.strip().startswith(("<", "{{")):
        return f"未配置有效 {required}"
    if typ == "command":
        try:
            argv = shlex.split(value)
        except ValueError:
            return "command 参数无法解析（检查引号）"
        if not argv:
            return "command 为空"
        if any(re.match(r"^\$(?:[A-Za-z_][A-Za-z_0-9]*|\{[^}]+\})(?:/|$)", arg)
               or re.fullmatch(r"\{\{[^}]*\}\}|<[^>]+>", arg) for arg in argv):
            return "command 含未展开的环境变量或模板；命令以 argv 执行，不经过 shell"
    if typ == "lark-cli" and "args" in ch:
        if not isinstance(ch["args"], list) or not ch["args"]:
            return "lark-cli args 必须是非空列表"
        try:
            for arg in ch["args"]:
                str(arg).format(chat_id="", card_json="", markdown="", title="")
        except (KeyError, ValueError, IndexError):
            return "lark-cli args 含未知或非法占位符"
    return ""


def channel_ready(ch, root="."):
    """本地字段、环境变量和可执行文件检查；不联网/运行命令/验证目标或鉴权。"""
    error = _channel_config_error(ch)
    if error:
        return False, error
    typ = ch["type"].strip()
    if typ in ("feishu", "dingtalk", "wecom"):
        env = ch["webhook_env"].strip()
        if not os.environ.get(env, "").strip():
            return False, f"环境变量 {env} 未设置"
        secret = ch.get("secret_env")
        if secret and not os.environ.get(str(secret), "").strip():
            return False, f"环境变量 {secret} 未设置"
        return True, f"环境变量 {env} 已设置；未发送探测"
    executable = str(ch.get("bin") or "lark-cli") if typ == "lark-cli" else shlex.split(ch["command"])[0]
    if os.sep in executable and not os.path.isabs(executable):
        executable = os.path.join(root, executable)
    if not shutil.which(executable):
        return False, f"{typ} 可执行程序不存在"
    return True, f"{typ} 可执行程序存在；目标参数/鉴权/送达需下游确认，未发送探测"


def migrate_notify_config(section, root="."):
    """只补历史通用契约已定义的顶层缺键；原 channels/参数原样保留，不猜私有迁移。"""
    import copy
    if not isinstance(section, dict):
        raise ValueError("notify 必须是配置映射")
    result = copy.deepcopy(section)
    defaults = {"enabled": False, "fallback": True, "channel_ready_card": False, "channels": []}
    added = []
    for key, value in defaults.items():
        if key not in result:
            result[key] = value
            added.append(key)
    diagnostics = []
    channels = result.get("channels")
    if not isinstance(channels, list):
        diagnostics.append({"field": "channels", "status": "unavailable", "reason": "channels 必须是列表"})
        channels = []
    for index, channel in enumerate(channels):
        ready, reason = channel_ready(channel, root)
        diagnostics.append({"field": f"channels[{index}]", "status": "ready" if ready else "unavailable",
                            "reason": reason,
                            "repair": f"编辑 memory/aidp-config.yaml 的 notify.channels[{index}]，补齐该 type 所需字段；再运行 notify.py --check-config --json"})
    invalid_flags = [key for key in ("enabled", "fallback", "channel_ready_card")
                     if not isinstance(result.get(key), bool)]
    for key in invalid_flags:
        diagnostics.append({"field": key, "status": "unavailable", "reason": "必须是布尔值"})
    available = any(item["status"] == "ready" for item in diagnostics)
    schema_ok = (not invalid_flags and isinstance(result.get("channels"), list)
                 and not any(_channel_config_error(channel) for channel in channels))
    # migration_complete 只说明通用结构已齐全；不能证明旧私有目标已迁移或能发送。
    report = {"added_fields": added, "channels": diagnostics, "verification": "local-only",
              "migration_complete": not added and schema_ok,
              "migration_scope": "generic-schema-only",
              "delivery_verified": False,
              "reason": "notify.enabled=false" if result.get("enabled") is False else
                        "notify.channels 未配置" if not channels else "逐项诊断见 channels；未发送探测",
              "ready": result.get("enabled") is True and available and not invalid_flags,
              "status": "ready" if result.get("enabled") is True and available and not invalid_flags else "unavailable",
              "repair": "编辑 memory/aidp-config.yaml 的 notify 配置；运行 notify.py --check-config --json（不发送探测）"}
    return result, report


def check_notify_config(root="."):
    import aidp_config
    data, ok = aidp_config.load(root)
    if not ok or not isinstance(data, dict):
        return {"ready": False, "status": "unavailable", "reason": "memory/aidp-config.yaml 无法解析",
                "repair": "修复 YAML 后运行 notify.py --check-config --json"}
    try:
        _, report = migrate_notify_config(data.get("notify", {}), root)
        return report
    except ValueError as exc:
        return {"ready": False, "status": "unavailable", "reason": str(exc),
                "repair": "修复 memory/aidp-config.yaml 的 notify 映射"}


def notify_ready(root="."):
    """里程碑通知是否可用：`notify.enabled` 为真且至少一个渠道本地具备发送条件。"""
    return check_notify_config(root)["ready"]


def _report_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("aidp_emit_report", os.path.join(SCRIPT_DIR, "emit-report.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record_report_notification(args, snapshot, status, reason=""):
    """送达只改 delivery metadata；不动报告/冻结事实，不新建 standalone baseline。"""
    if not snapshot or not snapshot["ledger_present"]:
        return False
    from datetime import datetime, timezone
    module = _report_module()
    return module.record_baseline(args.baseline, args.report_kind, args.build, args.version,
                                  "local", snapshot["local"]["url"], snapshot["integrity"],
                                  delivery_patch={"notification": {"status": status, "node": args.node,
                                      "url": snapshot["access_url"], "reason": reason,
                                      "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}},
                                  metadata_only=True)


def record_alert(repo_root, args, title, delivered, rc, error=""):
    """告警类调用（`--node #4` / `--alert`）恒追加本地告警台账 + stderr 一行。"""
    try:
        sys.path.insert(0, SCRIPT_DIR)
        import aidp_paths
        aidp_paths.append_alert(repo_root, kind="notify", node=args.node or None,
                                version=args.version or None, build=args.build or None,
                                title=title, detail=" / ".join(args.section)[:500],
                                delivered=bool(delivered), rc=rc, error=error or None)
    except Exception as exc:  # noqa: BLE001 —— 告警台账是旁路，不影响发送结果
        print(f"🚨 [AIDP-ALERT] {title}（本地告警台账写入失败：{exc}）", file=sys.stderr)


def send_auto(cfg, msg):
    """按 notify 配置依次尝试。返回 (exit_code, out_fragment)。"""
    out = {"attempts": []}
    if not cfg.get("enabled"):
        out["error"] = "notify.enabled=false"
        return 3, out
    chans = cfg.get("channels") or []
    if not chans:
        out["error"] = "notify.channels 为空"
        return 3, out
    tried = False
    for ch in chans:
        typ = str(ch.get("type") or "") if isinstance(ch, dict) else ""
        try:
            ok, diag = send_channel(ch, msg)
        except Unavailable as e:
            out["attempts"].append({"channel": typ, "status": "unavailable", "diag": str(e)})
            continue
        tried = True
        out["attempts"].append({"channel": typ, "status": "ok" if ok else "failed", "diag": diag})
        if ok:
            out["channel"] = typ
            return 0, out
        print(f"↩️ 渠道 {typ} 发送失败：{diag}", file=sys.stderr)
        if not cfg.get("fallback", True):
            break
    if not tried:
        out["error"] = "无可用渠道：" + "；".join(f"{a['channel']}={a['diag']}" for a in out["attempts"])
        return 3, out
    out["error"] = "已尝试的渠道全部失败"
    return 1, out


def _load_notify_config(root):
    sys.path.insert(0, SCRIPT_DIR)
    try:
        import aidp_config
        return aidp_config.notify_config(root)
    except Exception as e:  # noqa: BLE001 —— 读不到配置按「未配置」处理
        print(f"⚠️ 读取 notify 配置失败：{e}", file=sys.stderr)
        return {"enabled": False, "fallback": True, "channels": []}


def record_card(gate, node, version, build, repo_root, status="sent"):
    """登记 ceremony gate 里程碑通知台账（status = sent / undelivered）。返回 (recorded, warn)。"""
    cmd = [sys.executable, gate, "record-card", "--node", node,
           "--version", version, "--repo-root", repo_root, "--status", status]
    if build:
        cmd += ["--build", build]
    try:
        rr = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return False, str(e)
    return rr.returncode == 0, ("" if rr.returncode == 0 else (rr.stderr or rr.stdout or "").strip()[:200])


# ── 自测（离线：本地 HTTP 桩 + 假命令，不发外网）─────────────────────────────

def _self_check():
    import http.server
    import tempfile
    import threading

    got = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            n = int(self.headers.get("Content-Length") or 0)
            got.append((self.path, json.loads(self.rfile.read(n).decode("utf-8"))))
            code = b'{"errcode": 1, "errmsg": "bad"}' if self.path.startswith("/fail") else b'{"code": 0}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(code)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"
    saved_env = dict(os.environ)
    os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    ok = []
    try:
        msg = build_message('🚀 测试 "引号"', "green", ["**A：** 1\\n• x", "第二节"],
                            "报告", "docs/reports/r.html", "footer", version="V0.1.0")
        ok.append(("中性模型：\\n 转真实换行 + 链接", msg["sections"][0] == "**A：** 1\n• x"
                   and msg["link"]["url"] == "docs/reports/r.html"))
        # 签名：与独立实现对照
        exp_fs = base64.b64encode(hmac.new(b"1700000000\nsec", b"", hashlib.sha256).digest()).decode()
        ok.append(("飞书签名 = base64(HmacSHA256(key=ts\\nsecret, ''))", feishu_sign("1700000000", "sec") == exp_fs))
        exp_dd = urllib.parse.quote_plus(base64.b64encode(
            hmac.new(b"sec", b"1700000000000\nsec", hashlib.sha256).digest()).decode())
        ok.append(("钉钉加签 = urlencode(base64(HmacSHA256(key=secret, ts\\nsecret)))",
                   dingtalk_sign("1700000000000", "sec") == exp_dd))
        u, _b = render_dingtalk(msg, "https://example.com/robot/send?access_token=t", "sec", now=1700000000)
        ok.append(("钉钉 URL 拼 &timestamp=&sign=", u.endswith("&timestamp=1700000000000&sign=" + exp_dd)))

        os.environ["T_FS"] = base + "/feishu"
        os.environ["T_FS_SEC"] = "sec"
        os.environ["T_DD"] = base + "/dd?access_token=x"
        os.environ["T_DD_SEC"] = "sec"
        os.environ["T_WC"] = base + "/wecom"
        os.environ["T_FAIL"] = base + "/fail"
        os.environ.pop("T_MISSING", None)

        got.clear()
        r = send_channel({"type": "feishu", "webhook_env": "T_FS", "secret_env": "T_FS_SEC"}, msg)
        p, body = got[-1]
        ok.append(("feishu 发送成功 + payload 结构",
                   r[0] and body["msg_type"] == "interactive"
                   and body["card"]["header"]["title"]["content"] == msg["title"]
                   and body["card"]["header"]["template"] == "green"
                   and body["sign"] == feishu_sign(body["timestamp"], "sec")))
        r = send_channel({"type": "dingtalk", "webhook_env": "T_DD", "secret_env": "T_DD_SEC"}, msg)
        p, body = got[-1]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(p).query)
        ok.append(("dingtalk markdown + 加签参数",
                   r[0] and body["msgtype"] == "markdown" and "### " in body["markdown"]["text"]
                   and q.get("sign") and q.get("timestamp")
                   and urllib.parse.quote_plus(q["sign"][0]) == dingtalk_sign(q["timestamp"][0], "sec")))
        r = send_channel({"type": "wecom", "webhook_env": "T_WC"}, msg)
        ok.append(("wecom markdown", r[0] and got[-1][1]["msgtype"] == "markdown"
                   and "[报告](docs/reports/r.html)" in got[-1][1]["markdown"]["content"]))
        r = send_channel({"type": "wecom", "webhook_env": "T_FAIL"}, msg)
        ok.append(("业务错误码 errcode≠0 判失败", r[0] is False and "errcode=1" in r[1]))

        # command 渠道：stdin 收中性 JSON
        td = tempfile.mkdtemp()
        dump = os.path.join(td, "in.json")
        cmd = f"{shlex.quote(sys.executable)} -c \"import sys;open({dump!r},'w').write(sys.stdin.read())\""
        r = send_channel({"type": "command", "command": cmd}, msg)
        ok.append(("command 渠道 stdin = 中性 JSON",
                   r[0] and json.load(open(dump, encoding="utf-8")).get("schema") == "aidp.notify/v1"))

        # lark-cli 不存在 → 不可用
        try:
            send_channel({"type": "lark-cli", "chat_id": "c1", "bin": "aidp-no-such-lark-cli"}, msg)
            ok.append(("lark-cli 缺命令 → Unavailable", False))
        except Unavailable:
            ok.append(("lark-cli 缺命令 → Unavailable", True))
        # lark-cli 参数模板（用 python 充当 CLI）
        r = send_channel({"type": "lark-cli", "chat_id": "c1", "bin": os.path.basename(sys.executable)
                          if shutil.which(os.path.basename(sys.executable)) else sys.executable,
                          "args": ["-c", "import sys;sys.exit(0 if sys.argv[1]=='c1' else 1)", "{chat_id}"]}, msg)
        ok.append(("lark-cli args 模板占位替换", r[0]))

        # --auto 语义
        fail_cmd = f"{shlex.quote(sys.executable)} -c \"import sys;sys.exit(1)\""
        rc, o = send_auto({"enabled": False, "channels": [{"type": "command", "command": cmd}]}, msg)
        ok.append(("notify.enabled=false → 3", rc == 3))
        rc, o = send_auto({"enabled": True, "channels": []}, msg)
        ok.append(("channels 为空 → 3", rc == 3))
        rc, o = send_auto({"enabled": True, "channels": [{"type": "feishu", "webhook_env": "T_MISSING"},
                                                          {"type": "lark-cli", "chat_id": "c",
                                                           "bin": "aidp-no-such-lark-cli"}]}, msg)
        ok.append(("全部渠道不可用 → 3", rc == 3 and all(a["status"] == "unavailable" for a in o["attempts"])))
        rc, o = send_auto({"enabled": True, "fallback": True,
                           "channels": [{"type": "feishu", "webhook_env": "T_MISSING"},
                                        {"type": "command", "command": fail_cmd},
                                        {"type": "wecom", "webhook_env": "T_WC"}]}, msg)
        ok.append(("跳过不可用 + 失败回落 → 成功即停", rc == 0 and o["channel"] == "wecom"
                   and [a["status"] for a in o["attempts"]] == ["unavailable", "failed", "ok"]))
        rc, o = send_auto({"enabled": True, "fallback": False,
                           "channels": [{"type": "command", "command": fail_cmd},
                                        {"type": "wecom", "webhook_env": "T_WC"}]}, msg)
        ok.append(("fallback=false：首个失败即停 → 1", rc == 1 and len(o["attempts"]) == 1))

        # 标题前缀
        t, pt = ensure_title_prefix("🎉 /sprint-aiauto-test 完成", "示例项目", "V0.2.0")
        ok.append(("标题前缀补齐且不吞斜杠", t == "🎉 示例项目 V0.2.0 /sprint-aiauto-test 完成"
                   and pt == ["项目名称", "版本号"]))
        os.environ.pop("AIDP_PROJECT_NAME", None)
        os.makedirs(os.path.join(td, "memory"), exist_ok=True)
        cfgp = os.path.join(td, "memory", "aidp-config.yaml")
        open(cfgp, "w", encoding="utf-8").write(
            "project:\n  name: demo-app\n  name_cn: 待填充\n")
        n = resolve_project_name(td)
        ok.append(("中文名为占位 → 英文兜底 project.name", n[0] == "demo-app" and n[2] is True))
        open(cfgp, "w", encoding="utf-8").write(
            "project:\n  name: demo-app\n  name_cn: 示例平台\n")
        ok.append(("中文名优先", resolve_project_name(td)[:2] == ("示例平台", "aidp-config project.name_cn")))
        os.remove(cfgp)
        ok.append(("无 project 段 → git 根目录名兜底", resolve_project_name(td)[1] == "git 根目录名"))
        shutil.rmtree(td, ignore_errors=True)
    finally:
        srv.shutdown()
        os.environ.clear()
        os.environ.update(saved_env)
    for name, r in ok:
        print(("  ✅ " if r else "  ❌ FAIL: ") + name)
    return 0 if all(r for _, r in ok) else 1


# ── CLI ──────────────────────────────────────────────────────────────────────

def main(argv=None):
    ap = argparse.ArgumentParser(description="里程碑通知发送器（字段入参，脚本负责渲染/转义；成功才登记台账）")
    ap.add_argument("--title")
    ap.add_argument("--header-color", default="blue",
                    help="卡片头颜色（blue/red/green/orange/...；飞书渠道生效，告警用 red）")
    ap.add_argument("--section", action="append", default=[],
                    help="一个正文小节（markdown），可重复；小节间自动加分隔")
    ap.add_argument("--section-file", action="append", default=[], metavar="PATH",
                    help="从文件读一个正文小节（UTF-8 全文），可重复，追加在 --section 之后。"
                         "⛔ 正文含反引号 / $ / \\ 时务必用本参数，避免 shell 命令替换让正文静默缺失")
    ap.add_argument("--link-text", default="")
    ap.add_argument("--link-url", default="", help="报告链接（仓库内相对路径或仓库文件链接）")
    ap.add_argument("--report-kind", choices=("exec", "test"),
                    help="读已有报告与交付台账取得 URL/本地回落措辞；与 --link-url 互斥，不重测、不改报告")
    ap.add_argument("--reports-root", default="docs/reports")
    ap.add_argument("--baseline", default="memory/.sprint-autopilot-baseline.json")
    ap.add_argument("--check-config", action="store_true", help="离线诊断配置/渠道本地条件，不发送探测")
    ap.add_argument("--footer", default="")
    ap.add_argument("--sender", default="",
                    help="自定义发送命令（stdin 收中性 JSON，退出码 0=成功）；与 --auto 互斥")
    ap.add_argument("--auto", action="store_true",
                    help="★ 按 memory/aidp-config.yaml 的 notify.channels 依次尝试，成功即停")
    ap.add_argument("--print-only", action="store_true",
                    help="只构造并打印中性 JSON 与各渠道渲染结果，不发送、不登记")
    ap.add_argument("--node", default="", help="里程碑节点标识（如 #F）；给了才登记台账（成功 sent / 失败 undelivered）")
    ap.add_argument("--alert", action="store_true",
                    help=runtime_text('告警类通知：无论发送成败都追加 memory/.aidp/alerts.jsonl 并打印 stderr（--node #4 自动视为告警）', __file__))
    # ⛔ --node 给出时 --version 结构性必需：record-card 侧 --version 为必填，缺它该卡永远进不了台账。
    #    故在发送之前 fail-closed——发出去的通知收不回来，台账却会永久缺一条。
    ap.add_argument("--version", default="")
    ap.add_argument("--build", default="")
    ap.add_argument("--gate", default=runtime_text('__AIDP_HOME__/scripts/autopilot-ceremony-gate.py', __file__),
                    help="ceremony gate 路径（record-card 用）")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--project-name", default="",
                    help="标题固定前缀里的项目名称；不传则自动解析"
                         "（env AIDP_PROJECT_NAME → project.name_cn → project.name → git 根目录名，中文优先）")
    ap.add_argument("--check-name", action="store_true",
                    help="只解析并打印项目名称来源；英文兜底时 exit 3")
    ap.add_argument("--json", action="store_true", help="结构化输出结果")
    ap.add_argument("--self-check", action="store_true", help="离线自测（本地 HTTP 桩，不发外网）")
    args = ap.parse_args(argv)

    if args.self_check:
        return _self_check()

    repo_root = os.path.abspath(args.repo_root)

    if args.check_config:
        os.chdir(repo_root)
        report = check_notify_config(repo_root)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report["ready"] else 3

    if args.check_name:
        proj, src, ascii_fb = resolve_project_name(repo_root, args.project_name)
        out = {"project_name": proj, "source": src, "is_ascii_fallback": ascii_fb}
        if args.json:
            print(json.dumps(out, ensure_ascii=False))
        elif ascii_fb:
            print(f"⚠️ 项目名称是英文兜底值「{proj}」（来源：{src}）——通知标题会显示英文名。"
                  f"补法：在 memory/aidp-config.yaml 的 project 段填 `name_cn: <中文名>`")
        else:
            print(f"✅ 项目中文名称「{proj}」（来源：{src}）")
        return 0 if not ascii_fb else 3

    if not args.title:
        print("⛔ --title 必填（--check-name 只查项目名解析结果时可省略）", file=sys.stderr)
        return 2

    os.chdir(repo_root)
    for sf in args.section_file or []:
        try:
            with open(sf, "r", encoding="utf-8") as fh:
                args.section.append(fh.read().rstrip("\n"))
        except (OSError, ValueError) as e:
            print(f"⛔ --section-file 读取失败：{sf}（{e}）；通知未发送", file=sys.stderr)
            return 2
    if not args.section:
        print("⛔ 至少需要一个 --section（或 --section-file）", file=sys.stderr)
        return 2
    if args.node and not args.version:
        print(f"⛔ --node {args.node} 已给出但缺 --version：record-card 侧 --version 为必填，"
              f"缺它该卡永远进不了台账 → 收尾门恒 missing。\n"
              f"   → 补 --version <本轮版本号> 后重跑（通知尚未发送，可安全重试）。", file=sys.stderr)
        return 2
    if args.sender and args.auto:
        print("⛔ --sender 与 --auto 互斥", file=sys.stderr)
        return 2

    report_snapshot = None
    if args.report_kind:
        if not args.version or not args.build or args.link_url:
            print("--report-kind 需要 --version/--build，且与 --link-url 互斥", file=sys.stderr)
            return 2
        try:
            report_snapshot = _report_module().delivery_snapshot(
                args.report_kind, args.version, args.build, args.reports_root, args.baseline)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            print(f"报告交付读取失败，通知未发送：{exc}", file=sys.stderr)
            return 2
        args.link_url = report_snapshot["access_url"]
        args.section.append(report_snapshot["delivery_detail"])
        if report_snapshot["upload"].get("status") == "failed":
            args.section.append("上传失败原因：" + str(report_snapshot["upload"].get("reason") or "未记录"))
    elif args.link_url and not urllib.parse.urlsplit(args.link_url).scheme:
        args.section.append("当前提供仓库路径，需要仓库访问权限。")

    proj, proj_src, proj_ascii = resolve_project_name(repo_root, args.project_name)
    title, patched = ensure_title_prefix(args.title, proj, args.version)
    if patched:
        print(f"ℹ️ 标题已按固定前缀补齐（{'/'.join(patched)}，项目名称来源：{proj_src}）：{title}",
              file=sys.stderr)
    if proj_ascii:
        print(f"⚠️ 项目名称是英文/目录名兜底值「{proj}」（来源：{proj_src}）——"
              f"在 memory/aidp-config.yaml 填 project.name_cn 后标题才会显示中文名。", file=sys.stderr)

    msg = build_message(title, args.header_color, args.section, args.link_text, args.link_url,
                        args.footer, project=proj, version=args.version, build=args.build, node=args.node)

    if args.print_only:
        print(json.dumps({
            "message": msg,
            "rendered": {
                "feishu": render_feishu_payload(msg),
                "dingtalk": {"msgtype": "markdown",
                             "markdown": {"title": msg["title"], "text": render_markdown(msg)}},
                "wecom": render_wecom(msg),
            },
        }, ensure_ascii=False))
        return 0
    if not args.sender and not args.auto:
        print("⛔ 未传 --sender / --auto；如只想构造 JSON 请加 --print-only", file=sys.stderr)
        return 2

    out = {"ok": False, "node": args.node}
    is_alert = args.alert or args.node == "#4"
    gate = args.gate if os.path.isabs(args.gate) else os.path.join(repo_root, args.gate)

    def _delivery_status(status):
        try:
            if report_snapshot and report_snapshot["ledger_present"]:
                out["delivery_recorded"] = _record_report_notification(
                    args, report_snapshot, status, out.get("error", ""))
                if not out["delivery_recorded"]:
                    out["delivery_warning"] = "通知交付台账写入失败；报告事实未改"
        except (OSError, ValueError) as exc:
            out["delivery_warning"] = str(exc)

    def _undelivered(code):
        _delivery_status("unavailable" if code == 3 else "failed")
        if is_alert:
            record_alert(repo_root, args, title, False, code, out.get("error", ""))
        if args.node and os.path.isfile(gate):
            out["ledger_recorded"], _w = record_card(gate, args.node, args.version, args.build,
                                                     repo_root, status="undelivered")
    if args.auto:
        rc, frag = send_auto(_load_notify_config(repo_root), msg)
        out.update(frag)
        if rc == 3:
            _undelivered(3)
            print(json.dumps(out, ensure_ascii=False) if args.json else
                  f"⚠️ 未配置可用的通知渠道（本节点跳过，不阻塞主流程）：{out.get('error')}",
                  file=sys.stderr)
            return 3
        if rc != 0:
            _undelivered(1)
            print(json.dumps(out, ensure_ascii=False) if args.json else
                  "⛔ 已尝试的通知渠道全部失败 → 台账记 undelivered、不阻塞主流程；⛔ 不得因此弹窗询问用户。",
                  file=sys.stderr)
            return 1
    else:
        try:
            ok, diag = _run_stdin(shlex.split(args.sender), json.dumps(msg, ensure_ascii=False))
        except Unavailable as e:
            out["attempts"] = [{"channel": "sender", "status": "unavailable", "diag": str(e)}]
            out["error"] = str(e)
            _undelivered(3)
            print(json.dumps(out, ensure_ascii=False) if args.json else
                  f"⚠️ 发送命令不可用（本节点跳过，不阻塞主流程）：{e}", file=sys.stderr)
            return 3
        out["attempts"] = [{"channel": "sender", "status": "ok" if ok else "failed", "diag": diag}]
        if not ok:
            out["error"] = diag
            _undelivered(1)
            print(json.dumps(out, ensure_ascii=False) if args.json else
                  f"⛔ 发送失败（台账记 undelivered）：{diag}", file=sys.stderr)
            return 1
        out["channel"] = "sender"

    out["ok"] = True
    _delivery_status("sent")
    if out.get("delivery_warning"):
        print(out["delivery_warning"], file=sys.stderr)
    if is_alert:
        record_alert(repo_root, args, title, True, 0)
    if args.node and os.path.isfile(gate):
        out["ledger_recorded"], warn = record_card(gate, args.node, args.version, args.build, repo_root)
        if warn:
            out["ledger_warn"] = warn

    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"✅ 通知已发送（经 {out.get('channel')}）"
              f"{'（台账已登记 ' + args.node + '）' if out.get('ledger_recorded') else ''}")
        # 台账登记失败必须当场可见：不影响本次发送，却会让收尾门以 missing 恒 FAIL。
        if args.node and os.path.isfile(gate) and not out.get("ledger_recorded"):
            print(f"⚠️ 通知台账未登记（node={args.node} version={args.version or '-'} "
                  f"build={args.build or '(未铸造)'}）：{out.get('ledger_warn', '未知原因')}"
                  f"\n   → 请补跑 `python3 {args.gate} record-card --node {args.node} "
                  f"--version {args.version or '<V>'}`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
