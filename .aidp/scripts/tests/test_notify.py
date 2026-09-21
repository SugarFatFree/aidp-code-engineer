#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""notify.py 里程碑通知发送器单测（stdlib only，离线：本地 HTTP 桩 + 假命令，绝不联网）。

覆盖：
  · 中性卡片模型 + 各渠道渲染（feishu 卡片 / dingtalk markdown / wecom markdown 截断）
  · 飞书 / 钉钉签名算法（独立复算对照）
  · 各渠道真实发送（本地 http.server 收包）、业务错误码判失败
  · lark-cli（PATH 前置假可执行文件）/ command 渠道 / --sender 自定义命令 stdin 中性 JSON
  · --auto 回落：不可用跳过、失败回落、成功即停、fallback=false
  · 退出码 0 / 1 / 2 / 3；--print-only 与 --json 输出结构
  · 项目名解析：project.name_cn → project.name → git 根目录名；--check-name

直接跑：`python3 .aidp/scripts/tests/test_notify.py`
"""
import base64
import hashlib
import hmac
import http.server
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import urllib.parse
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
NOTIFY = os.path.join(SCRIPTS, "notify.py")

import notify as N  # noqa: E402

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


# ── 本地 HTTP 桩 ──────────────────────────────────────────────────────────────
GOT = []


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        GOT.append((self.path, json.loads(self.rfile.read(n).decode("utf-8"))))
        if self.path.startswith("/biz-fail"):
            code, body = 200, b'{"errcode": 310000, "errmsg": "keywords not in content"}'
        elif self.path.startswith("/http-fail"):
            code, body = 500, b'{"msg": "boom"}'
        else:
            code, body = 200, b'{"code": 0, "msg": "success"}'
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


SRV = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
BASE = f"http://127.0.0.1:{SRV.server_address[1]}"
threading.Thread(target=SRV.serve_forever, daemon=True).start()
os.environ["no_proxy"] = os.environ["NO_PROXY"] = "127.0.0.1,localhost"
for _k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "AIDP_PROJECT_NAME"):
    os.environ.pop(_k, None)


def _mkrepo(config_text=None, name="demo-app"):
    """临时项目根（git init，目录名可控）+ 可选 memory/aidp-config.yaml。"""
    base = Path(tempfile.mkdtemp())
    root = base / name
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], capture_output=True)
    if config_text is not None:
        (root / "memory").mkdir()
        (root / "memory" / "aidp-config.yaml").write_text(config_text, encoding="utf-8")
    return root


def _cli(root, *args, env_extra=None, path_prefix=None):
    env = dict(os.environ)
    env.update(env_extra or {})
    if path_prefix:
        env["PATH"] = path_prefix + os.pathsep + env.get("PATH", "")
    cp = subprocess.run([sys.executable, NOTIFY, "--repo-root", str(root), *args],
                        capture_output=True, text=True, env=env, timeout=60)
    return cp.returncode, cp.stdout, cp.stderr


def _json_line(text):
    for ln in reversed((text or "").strip().splitlines()):
        try:
            return json.loads(ln)
        except ValueError:
            continue
    return {}


def _msg():
    return N.build_message('🚀 发布 "引号"', "green", ["**版本：** V0.1.0\\n• 用例 12/12", "第二节"],
                           "打开报告", "docs/reports/demo.html", "自动生成\\n第二行",
                           project="示例项目", version="V0.1.0", build="V0.1.0_build1001", node="#F")


# ── 1. 中性模型 + 渲染 ───────────────────────────────────────────────────────
def test_model_and_render():
    print("【中性卡片模型 + 各渠道渲染】")
    m = _msg()
    check("schema = aidp.notify/v1", m["schema"] == "aidp.notify/v1")
    check("section 字面 \\n → 真实换行", m["sections"][0] == "**版本：** V0.1.0\n• 用例 12/12")
    check("footer 字面 \\n → 真实换行", m["footer"] == "自动生成\n第二行")
    check("link 结构", m["link"] == {"text": "打开报告", "url": "docs/reports/demo.html"})
    check("meta 带 project/version/build/node",
          m["meta"] == {"project": "示例项目", "version": "V0.1.0", "build": "V0.1.0_build1001", "node": "#F"})
    check("无 link_url → link=None", N.build_message("t", "", ["s"], "x", "", "")["link"] is None)
    check("header_color 缺省 blue", N.build_message("t", "", ["s"], "", "", "")["color"] == "blue")

    card = N.render_feishu_card(m)
    tags = [e["tag"] for e in card["elements"]]
    check("飞书卡片 header 标题/颜色",
          card["header"]["title"]["content"] == m["title"] and card["header"]["template"] == "green")
    check("飞书卡片：节间 hr + 链接 + note 页脚", tags == ["div", "hr", "div", "hr", "div", "note"])
    check("飞书卡片链接为 lark_md 链接",
          card["elements"][4]["text"]["content"] == "[打开报告](docs/reports/demo.html)")
    check("飞书 payload 无 secret → 不带 sign/timestamp",
          set(N.render_feishu_payload(m)) == {"msg_type", "card"})

    md = N.render_markdown(m)
    check("markdown：### 标题 开头 + 链接 + 引用页脚",
          md.startswith("### " + m["title"]) and "[打开报告](docs/reports/demo.html)" in md
          and "> 自动生成" in md)
    url, body = N.render_dingtalk(m, "https://example.com/robot/send?access_token=t")
    check("钉钉无 secret → URL 原样 + markdown 体",
          url == "https://example.com/robot/send?access_token=t" and body["msgtype"] == "markdown"
          and body["markdown"]["title"] == m["title"])
    w = N.render_wecom(m)
    check("企业微信 markdown.content", w["msgtype"] == "markdown" and w["markdown"]["content"] == md)
    big = N.build_message("t", "", ["汉" * 3000], "", "", "")
    wc = N.render_wecom(big)["markdown"]["content"]
    check("★ 企业微信超长截断到上限内（按字节，不切坏 UTF-8）",
          len(wc.encode("utf-8")) <= N.WECOM_MD_LIMIT + 10 and wc.endswith("…"))


# ── 2. 签名 ─────────────────────────────────────────────────────────────────
def test_signatures():
    print("【飞书 / 钉钉签名算法】")
    exp_fs = base64.b64encode(hmac.new(b"1700000000\ndemo-secret", b"", hashlib.sha256).digest()).decode()
    check("飞书签名 = base64(HmacSHA256(key=ts\\nsecret, 空串))", N.feishu_sign("1700000000", "demo-secret") == exp_fs)
    p = N.render_feishu_payload(_msg(), "demo-secret", now=1700000000)
    check("飞书 payload 带 timestamp(秒) + sign", p["timestamp"] == "1700000000" and p["sign"] == exp_fs)

    raw = hmac.new(b"demo-secret", b"1700000000000\ndemo-secret", hashlib.sha256).digest()
    exp_dd = urllib.parse.quote_plus(base64.b64encode(raw).decode())
    check("钉钉加签 = urlencode(base64(HmacSHA256(key=secret, ts\\nsecret)))",
          N.dingtalk_sign("1700000000000", "demo-secret") == exp_dd)
    u, _ = N.render_dingtalk(_msg(), "https://example.com/robot/send?access_token=t", "demo-secret", now=1700000000)
    check("钉钉 URL 已有 ? → 用 & 拼 timestamp(毫秒)/sign",
          u == "https://example.com/robot/send?access_token=t&timestamp=1700000000000&sign=" + exp_dd)
    u2, _ = N.render_dingtalk(_msg(), "https://example.com/robot/send", "demo-secret", now=1700000000)
    check("钉钉 URL 无 ? → 用 ? 拼", u2.startswith("https://example.com/robot/send?timestamp="))


# ── 3. 渠道发送（本地桩）────────────────────────────────────────────────────
def _fake_bin(dirpath, name, script):
    p = Path(dirpath) / name
    p.write_text(f"#!{sys.executable}\n" + script, encoding="utf-8")
    p.chmod(p.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return p


def test_send_channels():
    print("【各渠道发送（本地 HTTP 桩 / 假命令）】")
    m = _msg()
    os.environ["T_FS"] = BASE + "/feishu"
    os.environ["T_FS_SEC"] = "demo-secret"
    os.environ["T_DD"] = BASE + "/dingtalk?access_token=demo"
    os.environ["T_DD_SEC"] = "demo-secret"
    os.environ["T_WC"] = BASE + "/wecom"
    os.environ["T_BIZ"] = BASE + "/biz-fail"
    os.environ["T_500"] = BASE + "/http-fail"
    os.environ.pop("T_MISSING", None)

    GOT.clear()
    ok, _ = N.send_channel({"type": "feishu", "webhook_env": "T_FS", "secret_env": "T_FS_SEC"}, m)
    path, body = GOT[-1]
    check("feishu 发送成功 + interactive 卡片 + 签名可复算",
          ok and path == "/feishu" and body["msg_type"] == "interactive"
          and body["sign"] == N.feishu_sign(body["timestamp"], "demo-secret"))
    ok, _ = N.send_channel({"type": "feishu", "webhook_env": "T_FS"}, m)
    check("feishu 未配 secret_env → 不签名", ok and "sign" not in GOT[-1][1])

    ok, _ = N.send_channel({"type": "dingtalk", "webhook_env": "T_DD", "secret_env": "T_DD_SEC"}, m)
    path, body = GOT[-1]
    q = urllib.parse.parse_qs(urllib.parse.urlparse(path).query)
    check("dingtalk 发送成功 + 保留原 query + 加签可复算",
          ok and q.get("access_token") == ["demo"] and body["msgtype"] == "markdown"
          and urllib.parse.quote_plus(q["sign"][0]) == N.dingtalk_sign(q["timestamp"][0], "demo-secret"))

    ok, _ = N.send_channel({"type": "wecom", "webhook_env": "T_WC"}, m)
    check("wecom 发送成功 + markdown", ok and GOT[-1][1]["msgtype"] == "markdown")

    ok, diag = N.send_channel({"type": "wecom", "webhook_env": "T_BIZ"}, m)
    check("★ HTTP 200 但 errcode≠0 → 判失败并带错误码", ok is False and "errcode=310000" in diag)
    ok, diag = N.send_channel({"type": "feishu", "webhook_env": "T_500"}, m)
    check("HTTP 500 → 判失败", ok is False and "500" in diag)

    for ch, why in (({"type": "feishu", "webhook_env": "T_MISSING"}, "环境变量未设置"),
                    ({"type": "dingtalk"}, "未配置 webhook_env"),
                    ({"type": "command"}, "未配置 command"),
                    ({"type": "lark-cli"}, "未配置 chat_id"),
                    ({"type": "lark-cli", "chat_id": "c1", "bin": "aidp-no-such-cli-xyz"}, "命令不存在"),
                    ({"type": "slack"}, "未知渠道类型")):
        try:
            N.send_channel(ch, m)
            check(f"不可用：{why} → Unavailable", False)
        except N.Unavailable:
            check(f"不可用：{why} → Unavailable", True)

    # command 渠道：stdin = 中性 JSON
    td = tempfile.mkdtemp()
    dump = os.path.join(td, "in.json")
    fake = _fake_bin(td, "demo-sender", f"import sys\nopen({dump!r},'w',encoding='utf-8').write(sys.stdin.read())\n")
    ok, _ = N.send_channel({"type": "command", "command": str(fake)}, m)
    got = json.load(open(dump, encoding="utf-8")) if os.path.isfile(dump) else {}
    check("command 渠道 stdin 收中性 JSON（含中文与引号原样）",
          ok and got.get("schema") == "aidp.notify/v1" and got.get("title") == m["title"])
    failer = _fake_bin(td, "demo-fail", "import sys\nsys.stderr.write('denied')\nsys.exit(4)\n")
    ok, diag = N.send_channel({"type": "command", "command": str(failer)}, m)
    check("command 非零退出 → 失败 + stderr 诊断", ok is False and "denied" in diag)

    # lark-cli：PATH 前置假 lark-cli，记录 argv
    argv_dump = os.path.join(td, "argv.json")
    _fake_bin(td, "lark-cli", f"import sys,json\njson.dump(sys.argv[1:], open({argv_dump!r},'w'))\n")
    old_path = os.environ["PATH"]
    os.environ["PATH"] = td + os.pathsep + old_path
    try:
        ok, _ = N.send_channel({"type": "lark-cli", "chat_id": "chat-demo"}, m)
        argv = json.load(open(argv_dump))
        def _opt(name):
            return argv[argv.index(name) + 1] if name in argv and argv.index(name) + 1 < len(argv) else None
        check("lark-cli 默认参数表：im +messages-send --chat-id … interactive 卡片",
              ok and argv[:2] == ["im", "+messages-send"]
              and _opt("--chat-id") == "chat-demo" and _opt("--msg-type") == "interactive"
              and json.loads(_opt("--content"))["header"]["title"]["content"] == m["title"])
        ok, _ = N.send_channel({"type": "lark-cli", "chat_id": "chat-demo",
                                "args": ["send", "{chat_id}", "{title}", "{markdown}"]}, m)
        argv = json.load(open(argv_dump))
        check("lark-cli args 模板占位 {chat_id}/{title}/{markdown} 替换",
              ok and argv[:3] == ["send", "chat-demo", m["title"]] and argv[3].startswith("### "))
    finally:
        os.environ["PATH"] = old_path
    shutil.rmtree(td, ignore_errors=True)


# ── 4. --auto 回落语义 ───────────────────────────────────────────────────────
def test_send_auto():
    print("【send_auto 回落 / 成功即停 / 退出码】")
    m = _msg()
    td = tempfile.mkdtemp()
    ok_cmd = str(_fake_bin(td, "ok", "import sys\nsys.stdin.read()\n"))
    fail_cmd = str(_fake_bin(td, "fail", "import sys\nsys.exit(1)\n"))
    os.environ["T_WC"] = BASE + "/wecom"
    os.environ.pop("T_MISSING", None)

    rc, o = N.send_auto({"enabled": False, "channels": [{"type": "command", "command": ok_cmd}]}, m)
    check("notify.enabled=false → 3", rc == 3 and "enabled" in o["error"] and o["attempts"] == [])
    rc, o = N.send_auto({"enabled": True, "channels": []}, m)
    check("channels 为空 → 3", rc == 3)
    rc, o = N.send_auto({"enabled": True, "channels": [{"type": "feishu", "webhook_env": "T_MISSING"},
                                                       {"type": "command"}]}, m)
    check("★ 全部渠道不可用 → 3（合规降级，不是 1）",
          rc == 3 and [a["status"] for a in o["attempts"]] == ["unavailable", "unavailable"])

    GOT.clear()
    rc, o = N.send_auto({"enabled": True, "fallback": True, "channels": [
        {"type": "feishu", "webhook_env": "T_MISSING"},
        {"type": "command", "command": fail_cmd},
        {"type": "wecom", "webhook_env": "T_WC"},
        {"type": "command", "command": ok_cmd}]}, m)
    check("★ 跳过不可用 → 失败回落 → 成功即停（第 4 个渠道不再尝试）",
          rc == 0 and o["channel"] == "wecom"
          and [a["status"] for a in o["attempts"]] == ["unavailable", "failed", "ok"]
          and len(GOT) == 1)
    check("attempts[] 结构 = {channel,status,diag}",
          all(set(a) == {"channel", "status", "diag"} for a in o["attempts"]))
    rc, o = N.send_auto({"enabled": True, "fallback": False, "channels": [
        {"type": "command", "command": fail_cmd}, {"type": "command", "command": ok_cmd}]}, m)
    check("fallback=false：首个失败即停 → 1", rc == 1 and len(o["attempts"]) == 1)
    rc, o = N.send_auto({"enabled": True, "channels": [
        {"type": "command", "command": fail_cmd}, {"type": "feishu", "webhook_env": "T_MISSING"}]}, m)
    check("有渠道真失败、其余不可用 → 1（不是 3）", rc == 1 and o["error"])
    shutil.rmtree(td, ignore_errors=True)


# ── 5. 项目名解析 ────────────────────────────────────────────────────────────
def test_project_name():
    print("【项目名解析 + 标题前缀 + --check-name】")
    t, p = N.ensure_title_prefix("🎉 /sprint-dev 完成", "示例项目", "V0.2.0")
    check("标题补项目名+版本且不吞 /", t == "🎉 示例项目 V0.2.0 /sprint-dev 完成" and p == ["项目名称", "版本号"])
    t, p = N.ensure_title_prefix("🎉 示例项目 V0.2.0 · 完成", "示例项目", "V0.2.0")
    check("已含项目名与版本 → 不重复补", t == "🎉 示例项目 V0.2.0 · 完成" and p == [])

    root = _mkrepo("project:\n  name: demo-app\n  name_cn: 示例平台\n", name="repo-x")
    check("name_cn 优先", N.resolve_project_name(str(root)) == ("示例平台", "aidp-config project.name_cn", False))
    check("显式 --project-name（中文）最优先",
          N.resolve_project_name(str(root), "指定名")[:2] == ("指定名", "--project-name"))
    check("★ 显式给英文名 → 中文 name_cn 仍优先（判据是『是不是中文』）",
          N.resolve_project_name(str(root), "demo-web")[0] == "示例平台")
    (root / "memory/aidp-config.yaml").write_text("project:\n  name: demo-app\n  name_cn: 待填充\n", encoding="utf-8")
    check("name_cn 为占位 → 英文兜底 project.name",
          N.resolve_project_name(str(root)) == ("demo-app", "aidp-config project.name", True))
    (root / "memory/aidp-config.yaml").write_text("commit_gate:\n  enabled: true\n", encoding="utf-8")
    check("无 project 段 → git 根目录名兜底",
          N.resolve_project_name(str(root)) == ("repo-x", "git 根目录名", True))

    rc, out, _ = _cli(root, "--check-name", "--json")
    j = _json_line(out)
    check("--check-name 英文兜底 → exit 3 + JSON", rc == 3 and j.get("project_name") == "repo-x"
          and j.get("is_ascii_fallback") is True)
    rc, out, _ = _cli(root, "--check-name", "--json", env_extra={"AIDP_PROJECT_NAME": "环境变量名"})
    check("--check-name env AIDP_PROJECT_NAME 中文 → exit 0",
          rc == 0 and _json_line(out).get("source") == "env:AIDP_PROJECT_NAME")
    (root / "memory/aidp-config.yaml").write_text("project:\n  name_cn: 示例平台\n", encoding="utf-8")
    rc, out, _ = _cli(root, "--check-name")
    check("--check-name 中文名 → exit 0 + 人读输出", rc == 0 and "示例平台" in out)


# ── 6. CLI：参数错误 / print-only / --auto / --sender / --json ───────────────
def test_cli():
    print("【CLI：退出码 0/1/2/3 + --print-only / --json 结构】")
    root = _mkrepo("project:\n  name: demo-app\n  name_cn: 示例项目\n")

    rc, _, err = _cli(root, "--section", "x", "--auto")
    check("缺 --title → 2", rc == 2)
    rc, _, _ = _cli(root, "--title", "t", "--auto")
    check("缺 --section → 2", rc == 2)
    rc, _, _ = _cli(root, "--title", "t", "--section", "x", "--section-file", "/nonexistent/demo.md", "--auto")
    check("--section-file 读不到 → 2", rc == 2)
    rc, _, err = _cli(root, "--title", "t", "--section", "x", "--node", "#F", "--auto")
    check("--node 缺 --version → 2（发送前 fail-closed）", rc == 2 and "--version" in err)
    rc, _, _ = _cli(root, "--title", "t", "--section", "x", "--auto", "--sender", "true")
    check("--sender 与 --auto 互斥 → 2", rc == 2)
    rc, _, _ = _cli(root, "--title", "t", "--section", "x")
    check("未给 --sender/--auto/--print-only → 2", rc == 2)

    sf = root / "section.md"
    sf.write_text("含 `反引号` 与 $HOME 与 \\ 反斜杠\n", encoding="utf-8")
    rc, out, err = _cli(root, "--title", "🚀 发布完成", "--section", "**A：** 1", "--section-file", str(sf),
                        "--link-text", "报告", "--link-url", "docs/reports/r.html",
                        "--version", "V0.1.0", "--print-only")
    j = _json_line(out)
    msg = j.get("message", {})
    check("--print-only → 0 且输出 {message, rendered}", rc == 0 and set(j) == {"message", "rendered"})
    check("rendered 含 feishu/dingtalk/wecom 三种渲染",
          set(j.get("rendered", {})) == {"feishu", "dingtalk", "wecom"}
          and j["rendered"]["feishu"]["msg_type"] == "interactive")
    check("★ 标题按固定前缀补项目名 + 版本", msg.get("title") == "🚀 示例项目 V0.1.0 发布完成"
          and "标题已按固定前缀补齐" in err)
    check("★ --section-file 正文原样保留（反引号 / $ / 反斜杠）",
          msg.get("sections", [None, None])[1] == "含 `反引号` 与 $HOME 与 \\ 反斜杠")

    # --auto：未配置 notify → 3
    rc, out, err = _cli(root, "--title", "t", "--section", "x", "--auto")
    check("★ --auto 未配置 notify → 3（本节点跳过，不阻塞）", rc == 3 and "跳过" in err)
    rc, _, err = _cli(root, "--title", "t", "--section", "x", "--auto", "--json")
    check("--auto --json 3 → stderr 结构化 error", rc == 3 and "error" in _json_line(err))

    # --auto：配置 wecom（环境变量引用）→ 0，--json 输出 channel/attempts
    (root / "memory/aidp-config.yaml").write_text(
        "project:\n  name_cn: 示例项目\n"
        "notify:\n  enabled: true\n  fallback: true\n  channels:\n"
        "    - {type: feishu, webhook_env: AIDP_FEISHU_WEBHOOK}\n"
        "    - {type: wecom, webhook_env: AIDP_WECOM_WEBHOOK}\n", encoding="utf-8")
    env = {"AIDP_WECOM_WEBHOOK": BASE + "/wecom", "AIDP_FEISHU_WEBHOOK": ""}
    GOT.clear()
    rc, out, _ = _cli(root, "--title", "t", "--section", "x", "--auto", "--json", env_extra=env)
    j = _json_line(out)
    check("--auto 回落到 wecom 成功 → 0", rc == 0 and j.get("ok") is True and j.get("channel") == "wecom")
    check("--json attempts[]：feishu unavailable → wecom ok",
          [(a["channel"], a["status"]) for a in j.get("attempts", [])]
          == [("feishu", "unavailable"), ("wecom", "ok")] and GOT and GOT[-1][0] == "/wecom")

    env["AIDP_WECOM_WEBHOOK"] = BASE + "/biz-fail"
    rc, _, err = _cli(root, "--title", "t", "--section", "x", "--auto", "--json", env_extra=env)
    check("--auto 已尝试渠道全部失败 → 1", rc == 1 and _json_line(err).get("ok") is False)

    # --sender：stdin 中性 JSON；成功 → 0；失败 → 1
    td = tempfile.mkdtemp()
    dump = os.path.join(td, "in.json")
    snd = _fake_bin(td, "snd", f"import sys\nopen({dump!r},'w',encoding='utf-8').write(sys.stdin.read())\n")
    rc, out, _ = _cli(root, "--title", "t", "--section", "x", "--sender", str(snd), "--json")
    j = _json_line(out)
    check("--sender 成功 → 0，channel=sender", rc == 0 and j.get("channel") == "sender")
    check("--sender stdin schema=aidp.notify/v1",
          json.load(open(dump, encoding="utf-8")).get("schema") == "aidp.notify/v1")
    bad = _fake_bin(td, "bad", "import sys\nsys.exit(2)\n")
    rc, _, _ = _cli(root, "--title", "t", "--section", "x", "--sender", str(bad))
    check("--sender 失败 → 1", rc == 1)
    rc, _, _ = _cli(root, "--title", "t", "--section", "x", "--sender", "/nonexistent/demo-sender")
    check("--sender 命令不存在 → 1（不崩溃）", rc == 1)

    # 发送成功 + --node → 登记台账（用假 gate 记录 argv）
    gate_log = os.path.join(td, "gate.json")
    gate = _fake_bin(td, "gate.py", f"import sys,json\njson.dump(sys.argv[1:], open({gate_log!r},'w'))\n")
    rc, out, _ = _cli(root, "--title", "t", "--section", "x", "--sender", str(snd), "--json",
                      "--node", "#F", "--version", "V0.1.0", "--build", "V0.1.0_build1001", "--gate", str(gate))
    j = _json_line(out)
    argv = json.load(open(gate_log)) if os.path.isfile(gate_log) else []
    check("成功 + --node → 调 gate record-card 并回报 ledger_recorded",
          rc == 0 and j.get("ledger_recorded") is True and argv[:5] == ["record-card", "--node", "#F", "--version", "V0.1.0"]
          and "V0.1.0_build1001" in argv)
    os.remove(gate_log)
    rc, _, _ = _cli(root, "--title", "t", "--section", "x", "--sender", str(bad),
                    "--node", "#F", "--version", "V0.1.0", "--gate", str(gate))
    argv = json.load(open(gate_log)) if os.path.isfile(gate_log) else []
    check("★ 发送失败 → rc=1 且台账如实登记 status=undelivered（不伪装成已发）",
          rc == 1 and argv[-2:] == ["--status", "undelivered"])
    if os.path.isfile(gate_log):
        os.remove(gate_log)
    rc, _, err = _cli(root, "--title", "冻结", "--section", "x", "--auto", "--node", "#4",
                      "--version", "V0.1.0", "--gate", str(gate))
    led = os.path.join(root, "memory", ".aidp", "alerts.jsonl")
    check("★ #4 在无渠道时仍写本地告警台账 + stderr（停得响）",
          rc == 3 and os.path.isfile(led) and "AIDP-ALERT" in err
          and json.loads(open(led, encoding="utf-8").read().splitlines()[-1]).get("delivered") is False)
    shutil.rmtree(td, ignore_errors=True)

    rc, out, _ = _cli(root, "--self-check")
    check("notify.py --self-check 通过", rc == 0 and "FAIL" not in out)


def main():
    try:
        test_model_and_render()
        test_signatures()
        test_send_channels()
        test_send_auto()
        test_project_name()
        test_cli()
    finally:
        SRV.shutdown()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
