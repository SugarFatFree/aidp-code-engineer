#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_client_mcp.py — 「客户端 MCP 能力暴露」的【跨端声明判定唯一实现】。

## 这个功能点是什么（★ 先分清两条轴，混了必错）

| 轴 | 问的问题 | 本脚本管不管 |
| :- | :- | :-: |
| **应用能力** | 被测应用**自己**是否向 AI 暴露业务工具（带 Schema、带权限、带审计） | ✅ 就是它 |
| **测试驱动** | AI 用 chrome-devtools / Appium / 小程序驱动去**操控**客户端 | ⛔ 不是 |

**测试驱动用的也是 MCP 协议，但那是「AI 操控客户端」，不是「应用提供了 MCP 能力」。**
⛔ 本脚本**一个字节的驱动信息都不读**——正因为「Appium 装好了」「chrome-devtools 能连」
与「这个 App 提供了业务工具」毫无关系，读了就会把前者当后者的证据（下游已实证：
`driver=cli` + `enabled=true` 被当成「用了 WebMCP」，而 `registered_tools` 其实是 0）。

## WebMCP 只是 Web 端的一种实现

能力是**跨客户端**的，实现形态随端而变：

| client_type | implementation | 端专有前提归谁 |
| :- | :- | :- |
| `web` | `webmcp` | `check_webmcp.py`（secure context / Chrome 版本 / 两个启动开关） |
| `miniprogram` / `mobile` / `desktop` | `app-native` / `bridge` | **项目按其真实实现登记**；⛔ 绝不继承浏览器前提 |

⛔ **不要把 Web 的运行前提泛化到其他端**：secure context、`--enable-features=WebMCP`、
Chrome 150+ 全是**浏览器专有**的，套到小程序/原生 App 上既判不出真问题、又会让
根本不跑浏览器的端凭空常驻一堆永不满足的判据。

## 声明位置（按序读，命中即止；**默认关闭**）

  ① PRD 头部 `autopilot_decisions.client_mcp`（跨端，新）：
        client_mcp:
          enabled: true
          client_type: web | miniprogram | mobile | desktop
          implementation: webmcp | app-native | bridge | none
  ② PRD 头部 `autopilot_decisions.webmcp`（**存量 Web 项目兼容输入**）
     → 归一为 `client_type=web` + `implementation=webmcp`

**两处都声明且不一致 → `exit 2` 明确报错，⛔ 不静默取其一**：静默覆盖会让
「PRD 写着 mobile、实际按 web 判」这类错配一路跑到测试期才暴露，而那时的表现是
「能力入口探不到」——与「端选错了」完全不同形态，排查必然走偏。

## 四种状态（调用方按 `capability_state` 分流，⛔ 别只看 `declared`）

| capability_state | 含义 | declared |
| :- | :- | :-: |
| `not-declared` | 没声明 = 默认关闭。零 finding、零产物位、零成本 | false |
| `explicitly-disabled` | 显式声明不启用 | false |
| `declared-unimplemented` | **声明了能力、但没登记任何实现形态** = 应用并未提供 | false |
| `declared` | 声明 + 有实现形态，能力成立 | true |

`declared-unimplemented` 刻意**不**算启用：没有实现形态的「启用」无法被任何一端验证，
当成启用只会让下游生成一整套永远 block 的用例与设计段。

## 用法

    python3 AIDP_HOME/scripts/check_client_mcp.py [--root <仓库根>] --detect [--json]

退出码：`0`=判定完成（含未声明）/ `2`=声明冲突、取值非法或用法错。
"""
import argparse
import json
import os
import sys as _sys
_sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aidp_runtime import runtime_relpath  # noqa: E402
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_webmcp  # noqa: E402  —— Web 端适配层（entry_symbols 等端专有事实的单一信源）

CLIENT_TYPES = ("web", "miniprogram", "mobile", "desktop")
# ⛔ 不写死运行根：下游的运行契约在 `.claude/` 或 `.agents/`，写死一个必然在另一个上失效。
#    口径与 `check_webmcp.py` 一致（同为可选规则的模板位 / 安装位）。
RULE_TEMPLATE = os.path.join(runtime_relpath("", __file__), "templates", "optional-rules", "client-mcp.md")
RULE_INSTALLED = os.path.join(runtime_relpath("", __file__), "rules", "client-mcp.md")
IMPLEMENTATIONS = ("webmcp", "app-native", "bridge", "none")


def _indent(line):
    return len(line[: len(line) - len(line.lstrip())].expandtabs(4))


def _block(text, key):
    """取 YAML 块：`key:` 行之后所有**缩进更深**的行。未命中返回 None。

    ⛔ 不能用「一路吃到下一个非缩进行」的宽松写法：`client_mcp:` 与 `webmcp:` 同级并列时，
    宽松版会把后者整段吞进前者，冲突检测直接失效（本文件存在的理由之一就是查这个冲突）。
    """
    m = re.search(r"^([ \t]*)%s:[ \t]*$" % re.escape(key), text, re.M)
    if not m:
        return None
    base, out = _indent(m.group(0)), []
    for line in text[m.end():].split("\n")[1:]:
        if not line.strip():
            out.append(line)
            continue
        if _indent(line) <= base:
            break
        out.append(line)
    return "\n".join(out)


def _scalar(block, key):
    m = re.search(r"^[ \t]*%s:[ \t]*['\"]?([^'\"\n#]+?)['\"]?[ \t]*(?:#.*)?$" % re.escape(key), block or "", re.M)
    return m.group(1).strip() if m else None


def _truthy(value):
    return str(value).strip().lower() in ("true", "yes", "on")


def detect(root):
    """跨端声明判定。冲突 / 非法取值抛 ValueError（调用方转 exit 2）。"""
    result = {"declared": False, "capability_state": "not-declared", "client_type": None,
              "implementation": None, "source": "未声明（默认关闭）", "findings": []}

    for path in check_webmcp._prd_files(root):
        head = "\n".join(check_webmcp._read(path).split("\n")[:200])
        cross, legacy = _block(head, "client_mcp"), _block(head, "webmcp")
        if cross is None and legacy is None:
            continue
        rel = os.path.relpath(path, root)

        legacy_on = _truthy(_scalar(legacy, "enabled")) if legacy is not None else None
        if cross is None:
            # 存量 Web 项目：只有旧声明 —— 归一到 web/webmcp 这一端
            if not legacy_on:
                return dict(result, capability_state="explicitly-disabled",
                            source=f"PRD `autopilot_decisions.webmcp` 显式未启用（{rel}）")
            return _web(result, rel, root, "PRD `autopilot_decisions.webmcp`（存量 Web 声明）")

        enabled = _truthy(_scalar(cross, "enabled"))
        client_type = (_scalar(cross, "client_type") or "").lower() or None
        implementation = (_scalar(cross, "implementation") or "").lower() or None
        where = f"PRD `autopilot_decisions.client_mcp`（{rel}）"

        if client_type and client_type not in CLIENT_TYPES:
            raise ValueError(f"illegal client_type={client_type!r}（合法值：{'/'.join(CLIENT_TYPES)}）· {rel}")
        if implementation and implementation not in IMPLEMENTATIONS:
            raise ValueError(f"illegal implementation={implementation!r}（合法值：{'/'.join(IMPLEMENTATIONS)}）· {rel}")

        if legacy is not None:
            # ⛔ 两处声明不一致一律响亮失败：静默取其一 = 端选错了也一路跑到测试期才炸
            if client_type and client_type != "web" and legacy_on:
                raise ValueError(
                    f"conflict: client_mcp.client_type={client_type} 与 webmcp.enabled=true 互斥 · {rel}"
                    "（webmcp 是 Web 端适配，非 Web 端不得同时声明；删掉 webmcp 段或改正 client_type）")
            if bool(enabled) != bool(legacy_on):
                raise ValueError(
                    f"conflict: client_mcp.enabled={enabled} 与 webmcp.enabled={legacy_on} 取值相反 · {rel}")

        if not enabled:
            return dict(result, capability_state="explicitly-disabled", client_type=client_type,
                        implementation=implementation, source=f"{where} 显式未启用")
        if not client_type:
            raise ValueError(f"client_mcp.enabled=true 但未声明 client_type · {rel}")
        if not implementation or implementation == "none":
            # 声明了能力、却没有任何实现形态 —— 应用并未提供，⛔ 不当启用
            return dict(result, capability_state="declared-unimplemented", client_type=client_type,
                        implementation=implementation, source=where,
                        findings=[{"level": "WARN", "id": "declared-unimplemented",
                                   "detail": f"{where} 声明启用 client_type={client_type}，但未登记 implementation "
                                             "—— 应用侧无可验证的 MCP 能力实现，本轮按「未提供」处理。"
                                             "确有实现请登记形态（app-native / bridge / webmcp）；"
                                             "⛔ 测试驱动（Appium / chrome-devtools 等）可用不构成应用提供能力的证据"}])
        if client_type == "web":
            return _web(result, rel, root, where, implementation)
        return dict(result, declared=True, capability_state="declared", client_type=client_type,
                    implementation=implementation, source=where)

    return result


def _web(result, rel, root, source, implementation="webmcp"):
    """Web 端：端专有事实（entry_symbols 等）一律取 `check_webmcp.py`，本脚本不另写一套。"""
    web = check_webmcp.detect(root)
    return dict(result, declared=True, capability_state="declared", client_type="web",
                implementation=implementation, source=source,
                web_adapter={"entry_symbols": web["entry_symbols"], "symbols_source": web["symbols_source"],
                             "adapter_source": web["source"],
                             "note": "端专有运行前提与带参启动命令归 check_webmcp.py，本脚本不复制"})


def guard(root):
    """脚手架侧装配守卫：**声明成立了，端无关详规有没有真的装到 `rules/`**。

    ⛔ 这条硬拦不是可选项：`rules/*.md` 是**路径触发**加载的，不在那儿就永远不会被读到 =
    规则等于不存在。而「声明了能力」与「规则没装」在终端上看不出任何区别——
    正是 `AIDP_HOME/rules/README.md`「四条配套保证」里第一条要消灭的静默失效。

    分级同 `check_webmcp.py`：漏装判 **ERROR**（占退出码）；装了但与模板不一致判 **WARN**
    （刚升级未重装是正常中间态，且 `scaffold.py::refresh_optional_rules` 通常已自动刷新，
    这里只做兜底可见性）。
    """
    det = detect(root)
    out = dict(det, applicable=bool(det["declared"]), passed=True)
    if not out["applicable"]:
        return out                       # 未声明 = 默认关闭：零 finding、零告警、零产物位
    if det["client_type"] == "web":
        # Web 端详规是 webmcp.md，归 check_webmcp.py 守；⛔ 本脚本不重复要求、也不双写判据
        return out
    findings = list(det["findings"])
    dst = os.path.join(root, RULE_INSTALLED)
    src = os.path.join(root, RULE_TEMPLATE)
    if not os.path.isfile(dst):
        findings.append({
            "level": "ERROR", "check": "rule-not-installed", "file": RULE_INSTALLED,
            "detail": f"已声明客户端 MCP 能力（client_type={det['client_type']}），但端无关详规未安装到 "
                      f"`{RULE_INSTALLED}` —— rules 是**路径触发**加载的，不在那儿就永远读不到、"
                      f"等于规则不存在。跑 `python3 AIDP_HOME/scripts/check_client_mcp.py --install-rule` 安装"})
    elif os.path.isfile(src) and check_webmcp._read(src) != check_webmcp._read(dst):
        findings.append({
            "level": "WARN", "check": "rule-stale", "file": RULE_INSTALLED,
            "detail": f"`{RULE_INSTALLED}` 与模板位 `{RULE_TEMPLATE}` 不一致——要么脚手架升级后未刷新，"
                      f"要么副本被本地改过（改动应回模板位，副本下次重装即被覆盖）。"
                      f"重装：`--install-rule --force`"})
    out["findings"] = findings
    out["passed"] = not any(f.get("level") == "ERROR" for f in findings)
    return out


def install_rule(root, force=False):
    """把**端无关**详规从模板位装到 `AIDP_HOME/rules/`（幂等）。

    ⛔ **未声明即拒装**：`rules/` 是路径触发常驻加载，一次误装就让不提供本能力的项目
    每次编辑客户端代码白读一遍——正是「未启用即零成本」要消除的东西。
    ⛔ **Web 端不装本文件**：Web 详规是 `webmcp.md`，两份都装 = 同一能力两处规则、必然漂移。
    """
    det = detect(root)
    if not det["declared"]:
        return {"ok": False, "action": "refused",
                "detail": f"本项目未提供客户端 MCP 能力（{det['capability_state']}：{det['source']}）——⛔ 拒绝安装"}
    if det["client_type"] == "web":
        return {"ok": False, "action": "delegated",
                "detail": "Web 端详规归 webmcp.md：请跑 `python3 AIDP_HOME/scripts/check_webmcp.py --install-rule`"
                          "（本文件是端无关契约，Web 项目不重复安装）"}
    src, dst = os.path.join(root, RULE_TEMPLATE), os.path.join(root, RULE_INSTALLED)
    if not os.path.isfile(src):
        return {"ok": False, "action": "missing-template", "detail": f"模板位不存在：{RULE_TEMPLATE}（重跑脚手架补全）"}
    body = check_webmcp._read(src)
    existed = os.path.isfile(dst)
    if existed and check_webmcp._read(dst) == body and not force:
        return {"ok": True, "action": "already-installed", "detail": f"{RULE_INSTALLED} 已是最新，无需重装"}
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(body)
    return {"ok": True, "action": "updated" if existed else "installed",
            "detail": f"已{'更新' if existed else '安装'} {RULE_INSTALLED}（源：{RULE_TEMPLATE}·client_type={det['client_type']}）"}


def main():
    ap = argparse.ArgumentParser(description="客户端 MCP 能力暴露：跨端声明判定（未声明即 N/A）")
    ap.add_argument("--root", default=".")
    ap.add_argument("--detect", action="store_true", help="输出声明判定结果")
    ap.add_argument("--install-rule", action="store_true", help="声明成立且非 Web 端时，安装端无关详规到 rules/")
    ap.add_argument("--force", action="store_true", help="--install-rule：覆盖本地已改副本")
    ap.add_argument("--self-check", action="store_true",
                    help="阳性对照自检：注入必然命中的探针，验证本检查确实生效")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.self_check:
        from selfcheck import run_self_check
        return run_self_check(os.path.basename(__file__), json_out=args.json)

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print("[ERROR] --root 不是目录: %s" % root, file=sys.stderr)
        return 2
    try:
        res = detect(root)
    except ValueError as exc:
        print(f"[check_client_mcp] {exc}", file=sys.stderr)
        return 2

    if args.install_rule:
        out = install_rule(root, args.force)
        print(json.dumps(out, ensure_ascii=False, indent=2) if args.json
              else f"[{out['action'].upper()}] {out['detail']}")
        return 0 if out["ok"] or out["action"] == "delegated" else 1

    if args.detect:
        if args.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        else:
            print(f"[{res['capability_state'].upper()}] client_mcp declared={res['declared']} "
                  f"client_type={res['client_type']} implementation={res['implementation']} —— {res['source']}")
            for f in res["findings"]:
                print(f"  [{f.get('level', 'WARN')}] {f.get('check', f.get('id', ''))}: {f['detail']}")
        return 0

    # 默认动作 = 脚手架侧装配守卫（与 check_webmcp.py 同形）
    g = guard(root)
    if args.json:
        print(json.dumps(g, ensure_ascii=False, indent=2))
    elif not g["applicable"]:
        print(f"[N/A] 本项目未声明客户端 MCP 能力（{g['capability_state']}：{g['source']}）"
              f"—— 本检查整体跳过，不产生任何告警。")
    elif g["passed"]:
        warns = [f for f in g["findings"] if f.get("level") == "WARN"]
        print(f"[OK] 客户端 MCP 能力已声明（client_type={g['client_type']}），装配守卫通过。"
              + (f" {len(warns)} 处 WARN。" if warns else ""))
        for f in warns:
            print(f"  · [WARN][{f.get('check', f.get('id', ''))}] {f['detail']}")
    else:
        print(f"[FAIL] 客户端 MCP 能力已声明（client_type={g['client_type']}），检出 "
              f"{len(g['findings'])} 处问题：")
        for f in g["findings"]:
            print(f"  · [{f.get('level', 'WARN')}][{f.get('check', f.get('id', ''))}] {f['detail']}")
    return 0 if g["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
