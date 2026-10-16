#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""下发面不得出现「模板维护专属物」的**指令性**引用（确定性，ERROR 级）。

## 为什么需要

脚手架把 `{{AIDP_HOME}}/{commands,agents,flows,reference,rules,templates}` 与 `docs/init/` 原样下发给
下游。这些文件里只要出现一句**指令性**的模板维护内容，下游 AI 就会照做 ——
**而它照做的方式往往是「把模板项目的文件在下游建出来」**。

实测：`reference/约定细则-2.md` 的约定 30 写着
「需记录改动往 `版本变更历史.md` 追加（一条通俗摘要…）」，
而 `版本变更历史.md` 是**模板项目自己**的范式变更归档、脚手架从不下发它
（下发的根文件只有脚手架 `assets/root/` 里那几个 `.tpl`，它从来不在其中）。
下游读到这句就自己建了一份 —— 现象是「下发了模板项目的 `版本变更历史.md`」，
**真实机制却是指令泄漏，不是文件下发**。同族还有 `docs/init` 里两处
`[版本变更历史.md](../../版本变更历史.md)` 悬空链接。

## 判据：只抓【指令性】引用，放行【检测/判定/测试】

同一个名字出现在下发面，有两类完全不同的性质：

- **指令性（判违规）**：祈使句 / 流程步骤里要求下游**去读、去写、去维护**它
  —— 出现「追加 / 写入 / 维护 / 更新 / 记录到 / 见根目录 / 参见」这类动词或链接形态。
- **检测性（放行）**：代码里 grep 它的签名来判断「我是不是模板项目」、
  scaffold-only 白名单、测试夹具 —— 这些**必须**保留，删了反而让模板判定失效。

故本门只在**指令动词 / markdown 链接**同现时报，并支持
`<!-- template-only-leak: ignore <原因> -->` 就地豁免（原因必填）。

退出码：0 = 干净 / 1 = 有泄漏 / 2 = 入参错。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aidp_collect import from_result  # noqa: E402
from aidp_runtime import runtime_relpath  # noqa: E402

# 下发面（与 mirror_to_bundle 的受版本门控目录 + docs/init 对齐）
# ⚠️ 与 `mirror_to_bundle.py` 的受版本门控目录（单一信源 = `scaffold_lib.py::GATED_DIRS`）
#    + `docs/init` 对齐 —— 那就是「会被原样下发」的那一面。
SCAN = tuple(runtime_relpath(d, __file__) for d in
             ("commands", "agents", "flows", "reference", "rules", "templates")) + ("docs/init",)
# ⛔ 模板维护专属物：只存在于模板项目 / 脚手架 bundle，下游没有也不该有
TEMPLATE_ONLY_ARTIFACTS = (
    "版本变更历史.md",
    "assets/SCAFFOLD_VERSION",
    "assets/CONTRACT_MANIFEST.json",
    "bump_version.py",
    "mirror_to_bundle.py",
    "sync_memory_md.py",
    "设计目标.md",
)
# 指令性动词（要求读/写/维护它）
_IMPERATIVE = re.compile(
    r"追加|写入|写到|维护|更新|记录到|记入|补一条|加一条|新建|创建"
    r"|须跑|必须跑|先跑|跑满|执行|调用"
    r"|见根目录|参见|详见|统一见")
# markdown 链接形态（指向它 = 要求下游去打开它）
_LINK = re.compile(r"\]\([^)]*(?:%s)[^)]*\)")
_IGNORE = re.compile(r"<!--\s*template-only-leak:\s*ignore\s+(.+?)\s*-->")
# 明确的反向禁止句（「不下发 / 不该有 / 模板专属」）—— 那是在**阻止**下游用它，放行
_NEGATION = re.compile(
    r"不下发|不随[^，。；\n]{0,6}下发|不该有|不属于|不维护"
    r"|模板专属|模板项目自己|仅模板"
    # ★ 「归属声明」也是反向禁止句：它在说「这东西属于模板仓库、不在你这儿」，
    #   语义与「不下发」等价。⛔ 漏掉这几种词形的后果是**假红常驻** ——
    #   而本仓库的铁律是「假红常驻 = 硬门被绕过」，比没有这道门更糟。
    r"|模板仓库专用|模板仓库专属|模板仓库自己"
    r"|只在[^，。；\n]{0,14}模板仓库维护|在\*\*模板仓库\*\*跑"
    r"|不存在|恒跳过|恒\s*INFO|INFO\s*跳过|整维度跳过"
    r"|不要为此新建|自动生成|由\s*`?cyfw-ai-driven-dev")


def scan_file(path, rel):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.read(400_000).splitlines()
    except OSError as exc:
        return [], str(exc)

    out, in_fence = [], False
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue                       # 围栏内是可执行代码，归检测性
        if _IGNORE.search(ln):
            continue
        for art in TEMPLATE_ONLY_ARTIFACTS:
            if art not in ln:
                continue
            # ★ 反向语境按**段落窗口**判、不按行：说明性文字常把
            #   「它是模板专属、下游恒跳过」写在相邻行，只看本行会把解释判成指令。
            window = "\n".join(lines[max(0, i - 3):i + 2])
            if _NEGATION.search(window):
                continue
            linked = re.search(_LINK.pattern % re.escape(art), ln) is not None
            if linked or _IMPERATIVE.search(ln):
                out.append({
                    "file": rel, "line": i, "artifact": art,
                    "kind": "link" if linked else "imperative",
                    "excerpt": ln.strip()[:160],
                    "detail": ("下发面里以%s形态引用模板维护专属物 `%s` —— "
                               "下游会照做，而它照做的方式通常是把模板项目的文件"
                               "在自己仓库里建出来。请改写为「本项目不维护它」"
                               "或指向下游真正的落点；确属检测/判定用途请加"
                               "`<!-- template-only-leak: ignore <原因> -->`"
                               % ("链接" if linked else "指令", art)),
                })
                break
    return out, None


def run(root):
    findings, files, failed = [], 0, 0
    for scope in SCAN:
        base = os.path.join(root, scope)
        if not os.path.isdir(base):
            continue
        for dp, dn, fns in os.walk(base):
            dn[:] = [d for d in dn if d not in ("__pycache__", ".git")]
            for fn in sorted(fns):
                if not fn.endswith(".md"):
                    continue
                rel = os.path.relpath(os.path.join(dp, fn), root)
                got, err = scan_file(os.path.join(dp, fn), rel)
                files += 1
                if err:
                    failed += 1
                    continue
                findings.extend(got)
    res = {"applicable": True, "reason": "", "findings": findings,
           "files": files, "files_failed": failed, "checked": len(findings)}
    col = from_result(res, targets=files, items=files)
    res.update(col.as_json())
    res["collected"]["files_failed"] = failed
    return res


_PROBE = ("## 探针\n\n需记录改动往 `版本变更历史.md` 追加（一条通俗摘要）。\n")


def self_check():
    """阳性对照：植入一句指令性引用 → 必须报；反向禁止句 → 必须放行。"""
    import shutil
    import tempfile
    d = tempfile.mkdtemp()
    try:
        ref = os.path.join(d, runtime_relpath("reference", __file__))
        os.makedirs(ref)
        with open(os.path.join(ref, "probe.md"), "w", encoding="utf-8") as f:
            f.write(_PROBE)
        with open(os.path.join(ref, "neg.md"), "w", encoding="utf-8") as f:
            f.write("## 阴性\n\n`版本变更历史.md` 是模板项目自己的文件、不下发。\n")
        res = run(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    hits = [f for f in res["findings"] if f["file"].endswith("probe.md")]
    negs = [f for f in res["findings"] if f["file"].endswith("neg.md")]
    ok = len(hits) == 1 and not negs
    print(json.dumps({"self_check": "pass" if ok else "fail",
                      "probe_hits": len(hits), "false_positives": len(negs)},
                     ensure_ascii=False))
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-check", action="store_true")
    a = ap.parse_args()
    if a.self_check:
        return self_check()
    res = run(os.path.abspath(a.root))
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        for f in res["findings"]:
            print("ERROR %s:%d `%s`（%s）\n       %s\n       %s"
                  % (f["file"], f["line"], f["artifact"], f["kind"],
                     f["excerpt"], f["detail"]))
        print("[check_template_only_leak] 巡检 %d 份 .md，泄漏 %d 处"
              % (res["collected"]["targets"], len(res["findings"])))
    return 1 if (res["findings"] or res.get("starved")) else 0


if __name__ == "__main__":
    sys.exit(main())
