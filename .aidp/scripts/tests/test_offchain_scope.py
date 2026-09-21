#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""约定 41（链外任务动作边界 + 规模档位）与约定 17 反向门的回归。

问题形态：AIDP 把「流程严格度」绑在了「入口」上 —— 走 `/sprint-*` = 全套，
不走 = **未定义**。而约定 22/24/31.5 都明写「作用域 = 事实、与命令入口无关」，
只规定了链外**必须做什么**，从不规定**不必做什么**；
叠加 `/sprint-autopilot` IRON 系列的重仪式措辞（且该文件原先无作用域声明），
执行体默认按最重的路走 —— 实际项目中：两个口述小需求跑出 18 文件 / +1402 行，
文档占 53%，并自行完成了部署 + CICD 监听 + 浏览器实测。

约定 17 同理：回检只有「写少了」一个方向，过度注释零成本、零反馈信号。
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  ✅ {name}")
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_convention_41_text():
    print("\n[O1] 约定 41 落点与锚点一致性")
    a = (REPO / ".aidp/AIDP-AGENTS.md").read_text(encoding="utf-8")
    check("★ 主行存在且编号为 41", "\n41. **★ 链外任务的动作边界" in a)
    check("锚点声明已从 1–40 改到 1–41", "约定编号 1–41 为稳定锚点" in a)
    check("细则分片映射已登记 41", "约定 37·38·41" in a)
    for kw in ("⛔ 不铸 build", "⛔ 不跑浏览器实测", "部署默认否"):
        check(f"主行写明「{kw}」", kw in a)
    check("★ 写明档位只伸缩动作集、不伸缩可追溯性", "档位只伸缩动作集" in a)

    d5 = (REPO / ".aidp/reference/约定细则-5.md").read_text(encoding="utf-8")
    for sec in ("41.1", "41.2", "41.3", "41.4", "41.5", "41.6"):
        check(f"细则含 {sec}", f"#### {sec}" in d5)

    inv = (REPO / ".aidp/flows/sprint-autopilot/invariants.md").read_text(encoding="utf-8")
    check("★ IRON 系列已声明反向作用域（缺它则被泛化到全场景）",
          "⛔ 不适用于「链外任务」" in inv and "约定 41" in inv)

    d4 = (REPO / ".aidp/reference/约定细则-4.md").read_text(encoding="utf-8")
    check("★ 约定 34 已有执行时机（与约定 22 攒批口径对齐，此前两条冲突）",
          "#### 34.1 执行时机：两段式" in d4)
    check("两段式不削弱「不静默改写」（当场那一行标记是必须的）",
          "两段式不削弱" in d4)


def test_offchain_budget_tiers():
    print("\n[O2] 链外动作预算与规模档位判定")
    hg = _load("hg", str(REPO / ".aidp/scripts/commit_gate.py"))
    d = Path(tempfile.mkdtemp())

    def budget(porc, ctx="bare-conversation"):
        return hg.offchain_budget(str(d), ctx, porc)

    b = budget(" M code/a.vue\n M code/b.ts\n")
    check("XS：≤2 代码文件 → 不归档、不部署",
          b["tier"] == "XS" and not b["actions"]["sprint_archive"] and b["deploy"] is False)
    b = budget(" M code/a.ts\n M code/b.ts\n M code/c.ts\n M code/d.ts\n")
    check("S：≤5 文件 → 加单测、仍不部署",
          b["tier"] == "S" and b["actions"]["unit_test"] and b["deploy"] is False)

    (d / "alter.sql").write_text("ALTER TABLE T ADD COLUMN X INT;", encoding="utf-8")
    b = budget(" M code/a.ts\n M alter.sql\n")
    check("★ M：含 DDL → 归档 + 部署须用户确认（⛔ 不是默认做）",
          b["tier"] == "M" and b["actions"]["sprint_archive"] and b["deploy"] == "ask-user")

    (d / "new.sql").write_text("CREATE TABLE T_NEW(ID INT);", encoding="utf-8")
    b = budget(" M new.sql\n")
    check("★ L：含新表 → 判 L（约定 41 要求转正式 /sprint-* 链路）",
          b["tier"] == "L" and b["ddl"] == "new-table")

    check("★ 恒定禁止项与档位无关：任何档都不铸 build、不跑浏览器实测",
          budget(" M code/a.ts\n")["forbidden"] == ["铸 build", "浏览器实测"])
    check("★ 可追溯性四项任何档都不省",
          len(budget(" M code/a.ts\n")["always_required"]) == 4)
    check("★ 链内上下文 applies=False（约定 41 只管链外）",
          budget(" M code/a.ts\n", ctx="aidp-command")["applies"] is False)
    check("★ 标注只是下限、语义触发项须执行体自判（⛔ 不当免责）",
          budget(" M code/a.ts\n")["tier_floor_only"] is True)
    shutil.rmtree(d, ignore_errors=True)

    # 必须真的出现在 gate 的 JSON 里——否则又是一条没有调用方的规矩
    cp = subprocess.run([sys.executable, str(REPO / ".aidp/scripts/commit_gate.py"), "--quiet"],
                        capture_output=True, text=True, cwd=str(REPO))
    check("★ 随 commit_gate 的 JSON 一并输出（约定 24 规定它每次 commit 前必跑）",
          "offchain" in json.loads(cp.stdout))


def test_comment_ratio_gate():
    print("\n[O3] 约定 17 反向门：注释写太多同样是缺陷")
    sc = str(REPO / ".aidp/scripts/check_comment_ratio.py")
    cr = _load("cr", sc)
    d = Path(tempfile.mkdtemp())
    code = d / "code"
    code.mkdir()
    bad = "\n".join(["// 设置用户名"] * 40 + [f"int x{i} = {i};" for i in range(20)])

    (code / "Bad.java").write_text(bad, encoding="utf-8")
    r = cr.run(str(d), "code", 1.0, 30)
    check("★ 阳性：40 注释 / 20 代码且无 A 档特征 → Important",
          not r["ok"] and r["importants"][0]["ratio"] == 2.0)

    (code / "Bad.java").write_text("// 状态机：running → done\n" + bad, encoding="utf-8")
    check("★ 阴性：含 A 档特征（状态机）→ 豁免（A 档本就该写足）",
          cr.run(str(d), "code", 1.0, 30)["ok"])

    (code / "Bad.java").write_text(
        "// comment-ratio-ignore: 对外协议说明，注释即文档\n" + bad, encoding="utf-8")
    check("阴性：显式豁免（原因必填）→ 放行", cr.run(str(d), "code", 1.0, 30)["ok"])

    # ★ 契约型注释：JSDoc 类型声明里注释就是内容本身，判它超标是把"文档写得好"当缺陷
    (code / "Bad.java").unlink()
    (code / "types.js").write_text(
        "/**\n * @typedef {Object} P\n" + "".join(f" * @property {{string}} f{i} - 字段{i}\n"
                                                  for i in range(40)) + " */\n"
        + "\n".join(f"export const c{i} = {i};" for i in range(10)), encoding="utf-8")
    r = cr.run(str(d), "code", 1.0, 30)
    check("★ 阴性：JSDoc 契约型注释豁免（下游 types.js 是真实误报类别）",
          r["ok"] and r["contract_doc_skipped"] == 1)

    # ★ 真实误报形态：@ConfigurationProperties + Lombok，每字段一段 Javadoc。
    #   本仓 code/ 下 33 份文件曾因此被判超标 —— 而那恰是约定 17 要求的写法，
    #   判它等于让约定 17 的两个方向互相否定。
    (code / "types.js").unlink()
    props = "@Data\npublic class P {\n" + "".join(
        f"    /**\n     * 字段{i}的业务含义\n     */\n    String f{i};\n" for i in range(15)) + "}\n"
    (code / "P.java").write_text(props, encoding="utf-8")
    check("★ 阴性：逐字段 Javadoc 的属性类 → 声明文档扣减后放行（曾在本仓误报 33 份）",
          cr.run(str(d), "code", 1.0, 30)["ok"])
    (code / "P.java").write_text(
        props + "\n".join(f"// int dead{i} = {i};" for i in range(60)), encoding="utf-8")
    check("★ 阳性：扣减不是整档豁免 —— 同一文件再塞整段注释掉的死代码仍报出",
          not cr.run(str(d), "code", 1.0, 30)["ok"])
    (code / "P.java").unlink()
    (code / "Ok.java").write_text(
        "\n".join(["// 一行说明"] + [f"int x{i} = {i};" for i in range(40)]), encoding="utf-8")
    check("阴性：正常比例 → 放行", cr.run(str(d), "code", 1.0, 30)["ok"])
    shutil.rmtree(d, ignore_errors=True)

    check("脚本自带双侧对照可独立跑通（--self-check）",
          subprocess.run([sys.executable, sc, "--self-check"],
                         capture_output=True, text=True).returncode == 0)

    dev = (REPO / ".aidp/flows/sprint-dev/phase-1-dev-1.md").read_text(encoding="utf-8")
    check("★ 已接线到 /sprint-dev（否则又是一条没有调用方的门）",
          "check_comment_ratio.py" in dev)
    a = (REPO / ".aidp/AIDP-AGENTS.md").read_text(encoding="utf-8")
    check("约定 17 主行写明两个方向都有回检", "check_comment_ratio.py" in a)


def test_archive_and_mutation_rounds():
    print("\n[O4] 归档篇幅分档 + 变异对照轮数")
    a = (REPO / ".aidp/AIDP-AGENTS.md").read_text(encoding="utf-8")
    check("★ 约定 9 补了归档篇幅分档（此前无任何篇幅约束）",
          "口述累进 ≤40 行" in a and "只记「事后查不到的东西」" in a)
    d5 = (REPO / ".aidp/reference/约定细则-5.md").read_text(encoding="utf-8")
    check("★ 变异对照轮数已定规（消除「已成惯例却无规定」的方差）",
          "每个新增/修改的判据各做 1 轮" in d5)
    check("★ 并写明重复多轮不增加可信度（下游同会话跑出 3 轮与 4 轮两种）",
          "不增加可信度" in d5)
    check("★ 阳性对照没报时先查夹具（本仓多次实证的真实根因）",
          "是不是夹具写错了" in d5)


def test_standalone_push_debt():
    """G-CHAIN-2：链外推送（约定 41 明规定不铸 build）也必须进欠账。

    此前 `pending_cicd` 在「取不到 build 条目」处直接 continue —— 而链外恒无 build，
    于是这条最常见的路径（口述需求 → 改代码 → commit+push）**恒不报欠账**：
    那次推送的部署终态无人知道，且与「已监听到终态」在 gate 输出里完全同形。
    """
    print("\n[O5] 链外推送的部署终态欠账")
    hg = _load("hg3", str(REPO / ".aidp/scripts/commit_gate.py"))
    d = Path(tempfile.mkdtemp())
    try:
        subprocess.run(["git", "init", "-q", str(d)], check=True)
        for k, v in (("user.email", "alice@example.com"), ("user.name", "alice")):
            subprocess.run(["git", "-C", str(d), "config", k, v], check=True)
        (d / ".aidp/scripts").mkdir(parents=True)
        for f in ("classify_commit_change.py", "classify_push.py", "baseline_edit.py",
                  "commit_gate.py", "aidp_paths.py", "aidp_config.py"):
            src = REPO / ".aidp/scripts" / f
            if src.is_file():
                shutil.copy(src, d / ".aidp/scripts" / f)
        (d / "memory").mkdir()
        (d / "README.md").write_text("x", encoding="utf-8")
        subprocess.run(["git", "-C", str(d), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(d), "commit", "-qm", "base"], check=True, capture_output=True)
        code = d / "code/backend/x/src"
        code.mkdir(parents=True)
        (code / "A.java").write_text("class A{}", encoding="utf-8")
        subprocess.run(["git", "-C", str(d), "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(d), "commit", "-qm", "feat: 链外改动"],
                       check=True, capture_output=True)
        # 造出「已推送」态（本地 HEAD == 上游）
        subprocess.run(["git", "-C", str(d), "branch", "-f", "upstream-ref", "HEAD"],
                       capture_output=True)
        br = subprocess.run(["git", "-C", str(d), "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(d), "config", f"branch.{br}.remote", "."], check=True)
        subprocess.run(["git", "-C", str(d), "config", f"branch.{br}.merge",
                        "refs/heads/upstream-ref"], check=True)
        (d / "memory/.sprint-autopilot-baseline.json").write_text(
            '{"versions":{"V0.1.0":{"cicd":true}}}', encoding="utf-8")

        r = hg.pending_cicd(str(d))
        check("★★ 阳性：链外推送未经分类器 → 报欠账（旧实现因无 build 恒 continue）",
              r["pending"] is True and "链外" in r["reason"])
        subprocess.run([sys.executable, str(d / ".aidp/scripts/classify_push.py"),
                        "--root", str(d), "--version", "V0.1.0", "--standalone"],
                       capture_output=True, cwd=str(d))
        check("★ 阴性：跑过 --standalone → 欠账消失",
              hg.pending_cicd(str(d))["pending"] is False)
        bl = json.loads((d / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
        pushes = bl["versions"]["V0.1.0"].get("standalone_pushes") or []
        check("★ 台账是 commit 键控的（单槽 release_change_classification 无 sha、后写覆盖前写，判不出覆盖的是哪次推送）",
              len(pushes) == 1 and len(str(pushes[0].get("commit") or "")) >= 40)
    finally:
        shutil.rmtree(d, ignore_errors=True)

    a = (REPO / ".aidp/AIDP-AGENTS.md").read_text(encoding="utf-8")
    check("★ 约定 31.5 主行写明链外走 --standalone（否则缺 build 直接 ValueError）",
          "--standalone" in a)


def main():
    test_convention_41_text()
    test_offchain_budget_tiers()
    test_comment_ratio_gate()
    test_archive_and_mutation_rounds()
    test_standalone_push_debt()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
