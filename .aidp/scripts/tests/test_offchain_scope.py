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
    convention = next((line for line in a.splitlines() if line.startswith("41. ")), "")
    policy = (REPO / ".aidp/flows/sprint-dev/light-context.md").read_text(encoding="utf-8")
    check("主行保留编号41及light/formal身份，并指向动作策略单一源",
          "light/formal" in convention and "身份" in convention
          and "flows/sprint-dev/light-context.md" in convention)
    check("稳定锚点保持 1–41", "约定编号 1–41 为稳定锚点" in a)
    check("细则分片映射已登记 41", "约定 37·38·41" in a)
    check("单一策略保留light不铸build边界", "light 不铸 build" in policy)
    check("普通开发含实现、静态与本任务相关单测，部署及live须各自授权",
          "普通开发/修复默认 `implement + static + related-test`" in policy
          and "light 不铸 build、默认不部署" in policy
          and "在已有任务上分别增加 `commit`、`push`、`deploy`" in policy
          and "自然语言浏览器/页面请求只授权所指页面或流程的 live-tests，不借用 autopilot 版本全量组合" in policy)
    check("light不认领旧Sprint且不重置既有状态",
          "light 无 Sprint 卡/归档，不认领旧 Sprint" in convention
          and "light 收尾不创建 Sprint 归档、不重置已有 activeContext/progress" in a)
    check("风险复杂度成本分开，formal身份及历史不能扩大授权",
          "规模风险、复杂度、成本分别判断" in convention
          and "formal 保留编号、规格、归档，但不增授权" in convention
          and "复杂度、已有 activeContext 或历史计划不能升级身份或授权" in a)

    d5 = (REPO / ".aidp/reference/约定细则-5.md").read_text(encoding="utf-8")
    for sec in ("41.1", "41.2", "41.3", "41.4", "41.5", "41.6"):
        check(f"细则含 {sec}", f"#### {sec}" in d5)

    inv = (REPO / ".aidp/flows/sprint-autopilot/invariants.md").read_text(encoding="utf-8")
    check("★ IRON作用域限于autopilot且受父授权约束，未请求项不变欠账",
          "⛔ 不适用于「链外任务」" in inv and "约定41" in "".join(inv.split())
          and "下文必须项仅对父授权范围生效" in inv
          and "NOT_REQUESTED不执行、不作欠账/PASS或freeze" in inv)

    d4 = (REPO / ".aidp/reference/约定细则-4.md").read_text(encoding="utf-8")
    check("★ 约定 34 已有执行时机（与约定 22 攒批口径对齐，此前两条冲突）",
          "#### 34.1 执行时机：两段式" in d4)
    check("两段式不削弱「不静默改写」（当场那一行标记是必须的）",
          "两段式不削弱" in d4)


def test_offchain_budget_tiers():
    print("\n[O2] 链外动作预算与规模档位判定")
    hg = _load("hg", str(REPO / ".aidp/scripts/commit_gate.py"))
    d = Path(tempfile.mkdtemp())
    for args in (("init", "-q"), ("config", "user.name", "fixture"),
                 ("config", "user.email", "fixture@example.invalid"), ("commit", "--allow-empty", "-qm", "base")):
        subprocess.run(["git", "-C", str(d), *args], check=True, capture_output=True)

    def budget(porc, ctx="bare-conversation"):
        return hg.offchain_budget(str(d), ctx, porc)

    b = budget(" M code/a.vue\n M code/b.ts\n")
    check("XS：≤2 代码文件 → 不归档、不部署",
          b["risk_tier"] == "S" and b["cost"]["band"] == "XS" and not b["actions"]["sprint_archive"] and b["deploy"] is False)
    b = budget(" M code/a.ts\n M code/b.ts\n M code/c.ts\n M code/d.ts\n")
    check("S：开发默认相关单测，文件数量不扩大范围或授权部署",
          b["tier"] == "S" and b["actions"]["unit_test"] and b["deploy"] is False)

    (d / "alter.sql").write_text("ALTER TABLE T ADD COLUMN X INT;", encoding="utf-8")
    b = budget(" M code/a.ts\n M alter.sql\n")
    check("★ M：含 DDL 增加影响分析，不自动取得Sprint身份",
          b["tier"] == "M" and not b["actions"]["sprint_archive"] and b["deploy"] is False)

    (d / "new.sql").write_text("CREATE TABLE T_NEW(ID INT);", encoding="utf-8")
    b = budget(" M new.sql\n")
    check("★ L：含新表只提高风险分析，仍不自动建Sprint",
          b["tier"] == "L" and b["ddl"] == "new-table" and not b["actions"]["sprint_archive"])

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
                  "commit_gate.py", "aidp_paths.py", "aidp_config.py", "vcs.py",
                  "aidp_runtime.py"):
            src = REPO / ".aidp/scripts" / f
            if src.is_file():
                shutil.copy(src, d / ".aidp/scripts" / f)
        (d / "memory").mkdir()
        (d / "memory/aidp-config.yaml").write_text(
            "cicd:\n  provider: github-actions\n  pipelines: {test: deploy-test.yml}\n", encoding="utf-8")
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


def test_dispatch_and_deletion_contracts():
    print("\n[O6] AIDP 派发、删除证据与角色收口契约")

    def text(relative):
        return (REPO / relative).read_text(encoding="utf-8")

    dev = text(".aidp/commands/sprint-dev.md")
    flow = text(".aidp/flows/sprint-dev/phase-1-dev-2.md")
    dispatch = flow.split("### Phase 1.4：", 1)[1]
    check("并行实现由 AIDP 编排，不借串行 SKILL 的调度语义",
          "AIDP 主流程直接使用 Agent 工具编排" in dispatch
          and "不调用 `superpowers:subagent-driven-development`" in dispatch)
    check("写集覆盖新增/删除/测试/锁文件，冲突和依赖均控制并行准入",
          all(s in dispatch for s in ("write_set", "create_dirs", "dependencies",
                                      "写集无交集", "改为串行", "未知冲突按有冲突处理")))
    check("共享文档和 Git 动作归主流程，子 Agent 不自行提交或关闭",
          "Git index/commit/push" in dispatch and "由主流程统一处理" in dispatch
          and "子 Agent 不自行提交或关闭 Sprint" in dispatch)
    protocol = text(".aidp/flows/sprint-dev/incremental-contract.md")
    check("汇合只消费获准审查，CVL复用review证据且修复仅复核delta",
          "review未授权则NOT_REQUESTED" in dispatch
          and "review已授权且无full-cvl时派一次只读reviewer" in dispatch
          and "一次CVL并复用为review证据" in dispatch
          and "不先叠整轮契约reviewer" in dispatch
          and "只修已授权scope" in dispatch and "复核delta" in dispatch)
    check("M docs 独占写集，开发偏差回专属工作单",
          "docs Agent 独占正式文档写集" in dispatch
          and "开发 Agent 只回各自工作单" in dispatch
          and "contract_revision" in dispatch and "work_order" in dispatch)
    check("默认主流程唯一 Git 写者，用户授权 worker 也须串行交接",
          "默认编排者是唯一 Git 写者" in protocol
          and "用户显式授权 worker 提交" in protocol
          and "绝不多人同时 `git add/commit`" in protocol)
    check("commit_gate 校验汇合写集并集，外路径只核对不重置他人索引",
          "--owner orchestrator" in protocol and "--allow-path" in protocol
          and "并集" in protocol and "不擅自 reset 他人暂存" in protocol)

    rule = text(".aidp/rules/code.md").split("## 约定 29", 1)[1].split("## 约定 35", 1)[0]
    frontend = text(".aidp/agents/frontend.md").split("11. **", 1)[1].split("12. **", 1)[0]
    check("四类信号仅提供候选，重构不是删除授权",
          "4 类候选线索" in rule and "④ 也不是删除授权" in rule
          and "任一命中即死代码" not in rule and "④ 强信号命中 →" not in frontend)
    check("自动删除须全部证据，仍在使用的重构优先 C",
          "删除证据门（B 的必要条件，全部满足）" in rule
          and "C 优先于 B，分支互斥" in rule
          and "无存活入口/调用方，且删除证据门全部满足" in rule)
    check("详情页路由、动态加载和外部消费者不能被零命中误杀",
          all(s in rule for s in ("无菜单但仍有路由", "动态/自动注册", "外部调用",
                                 "扫描失败", "未知，保留原文件"))
          and "未核部分填“无”" in dev)
    check("关联文件逐项证明独占，数据库无登记不被解释为空库",
          "每个连带文件也已证明仅由该候选使用" in rule
          and "未证实的不删除" in frontend
          and "基线未登记不等于表不存在或无生产数据" in dev
          and "不能生成或执行 DROP" in dev)

    for relative in (".aidp/rules/frontend.md", ".aidp/agents/ui.md",
                     ".aidp/flows/sprint-dev/phase-1-dev-2.md"):
        body = text(relative)
        check(relative + "：L2 非阻断仅管 loop，不再承诺验收通过",
              "不阻塞验收" not in body and "loop" in body and "验收仍不通过" in body
              if relative != ".aidp/rules/frontend.md" else
              "不阻塞验收" not in body and "验收结论为不通过" in body)

    pm = text(".aidp/agents/pm.md")
    architect = text(".aidp/agents/architect.md")
    check("PM 只回填脚手架根记忆，归档保留判断而不整份复制",
          "只定点回填" in pm and "不重写规范正文" in pm
          and "不整份复制" in pm and "将 activeContext 完整复制" not in pm)
    for relative, body in (("pm", pm), ("architect", architect)):
        check(relative + "：共享主文档可级联，正式发布与 Sprint 历史仍保护",
              "未发布版本的共享" in body and "--ledger-cascade" in body
              and "改写授权门" in body and "Sprint" in body
              and ("归档记录保持只读" in body or "永不修改" in body))
    policy = text(".aidp/flows/sprint-dev/light-context.md")
    for relative in ("docs/init/02_迭代输入指导.md", "docs/init/05_commands详细规范.md",
                     "docs/init/00_AIDP范式主文档.md"):
        body = text(relative)
        # 命令总览明确只作索引：检查它链接的权威执行策略，不要求复制派单细则。
        if relative == "docs/init/05_commands详细规范.md":
            scope_bound = ("总览和索引" in body and "不再重复" in body
                           and "commands/sprint-dev.md" in body
                           and "flows/sprint-dev/light-context.md" in body
                           and all(flag in policy for flag in ("--write-set", "--acceptance", "--execution-context"))
                           and any(clause in policy for clause in ("并行写集不交叉", "并行写集必须不相交")))
        else:
            scope_bound = "写集" in body
        check(relative + "：开发调用描述及权威写集边界已同步",
              "subagent-driven-development" not in body and scope_bound)


def test_worker_contract_inputs_and_write_scope():
    """直接检查会被开发子 Agent Read 的角色，防父协议正确而角色仍强制旧读写。"""
    print('\n[O7] S/M 开发角色的契约输入与独占写集')
    protocol = (REPO / '.aidp/flows/sprint-dev/incremental-contract.md').read_text(encoding='utf-8')
    light = (REPO / '.aidp/flows/sprint-dev/light-context.md').read_text(encoding='utf-8')
    command = (REPO / '.aidp/commands/sprint-dev.md').read_text(encoding='utf-8')
    for role in ('backend', 'frontend'):
        body = (REPO / f'.aidp/agents/{role}.md').read_text(encoding='utf-8')
        entry = body.split('## 一、身份定义', 1)[0]
        startup = body.split('## 二、会话启动检查清单', 1)[1].split('## 三、核心工作流程', 1)[0]
        check(f'{role} 开头接收契约身份、实际接口路径与具体写集',
              all(field in entry for field in ('contract_path', 'contract_revision',
                                               'interface_documents', 'write_set', 'work_order')))
        check(f'{role} 先校验已批准修订，失配不开始实现',
              'incremental-contract.md' in entry and '不开始实现' in entry
              and 'approved_revision=contract_revision' in protocol and 'status=approved' in protocol)
        check(f'{role} S/M 不读取成文中的正文或强求固定分册',
              'S/M' in startup and '不读取 docs Agent 尚未交付的正文' in startup
              and '不要求固定 `02_数据库设计.md` / `03_接口设计.md`' in startup)
        check(f'{role} formal 普通计划/L 仍读完整正式规格',
              'formal 普通计划 / L' in startup and '00_索引.md' in startup)
        check(f'{role} light 在卡片门之前分流并保留写集限制',
              'light-context.md' in entry and '**仅 formal**' in entry
              and entry.index('light-context.md') < entry.index('**仅 formal**')
              and '**light**' in startup and 'formal 完整规格清单不用于 light' in startup
              and 'write_set' in entry and '--write-set' in light and '--acceptance' in light
              and 'light 不建 Sprint/卡片/审批文档' in light
              and command.index('return') < command.index('## formal 流程'))
        check(f'{role} 共享内容统一回主流程，不能直接改 bug/memory/事实',
              '共享写入统一交主流程' in entry
              and all(term in entry for term in ('memory', 'bugfix', '事实清单', '子Agent必读')))
        check(f'{role} 原宽泛 bugfix 写权限已撤回工作单',
              '| `docs/bugfix/{version}/bugfix-*.md` | 创建' not in body
              and '本 Agent 独占的 `work_order`' in body)
        check(f'{role} 不再命令 worker 就地更新公共踩坑资料',
              '当轮**就补进去' not in entry and '不自行 git add/commit/push' in entry)


def test_documented_entry_routes():
    """执行真实命令的入口围栏，防文档声称light但实际仍认领历史Sprint。"""
    print('\n[O8] 命令入口围栏执行与历史Sprint隔离')
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        active = root / 'memory/V0.1.0/alice/activeContext.md'
        active.parent.mkdir(parents=True)
        active.write_text('当前 Sprint：Sprint-077\n旧任务仍在执行\n', encoding='utf-8')
        original = active.read_bytes()
        plan = root / 'docs/plans/V0.1.0/01_研发执行计划.md'
        plan.parent.mkdir(parents=True)
        plan.write_text('# 历史计划\nSprint-078 待开发\n', encoding='utf-8')
        for command in ('sprint-start', 'sprint-dev', 'sprint-test',
                        'sprint-bugfix', 'sprint-close', 'sprint-full', 'version'):
            body = (REPO / f'.aidp/commands/{command}.md').read_text(encoding='utf-8')
            fence = body.split('```bash\n', 1)[1].split('\n```', 1)[0]
            shell = fence.replace('{{AIDP_HOME}}', str(REPO / '.aidp')).replace('{version}', 'V0.1.0')
            env = dict(os.environ)
            env.pop('EXECUTION_CONTEXT', None)
            env.pop('EXPLICIT_SPRINT', None)
            cp = subprocess.run(['bash', '-c', shell], cwd=root, env=env,
                                capture_output=True, text=True)
            expected = 'formal' if command in ('sprint-full', 'version') else 'light'
            try:
                result = json.loads(cp.stdout)
            except ValueError:
                result = {}
            check(f'{command} 真实入口解析为 {expected}',
                  cp.returncode == 0 and result.get('mode') == expected)
            if expected == 'light':
                check(f'{command} light在formal正文前明确return',
                      body.index('return') < body.index('## formal 流程'))
                context = result.get('execution_context')
                if context:
                    env['EXECUTION_CONTEXT'] = context
                    resumed = subprocess.run(['bash', '-c', shell], cwd=root, env=env,
                                             capture_output=True, text=True)
                    try:
                        inherited = json.loads(resumed.stdout)
                    except ValueError:
                        inherited = {}
                    check(f'{command} 嵌套重试继承原task_id',
                          resumed.returncode == 0 and inherited.get('task_id') == result.get('task_id'))
        check('既有active状态与历史计划未被入口改写',
              active.read_bytes() == original and 'Sprint-078 待开发' in plan.read_text(encoding='utf-8'))
        check('入口未分配Sprint卡片、started或归档',
              not list(root.rglob('_sprint-*-契约卡.md'))
              and not list(root.rglob('.started*'))
              and not (active.parent / 'sprints').exists())


def main():
    test_documented_entry_routes()
    test_worker_contract_inputs_and_write_scope()
    test_convention_41_text()
    test_offchain_budget_tiers()
    test_comment_ratio_gate()
    test_archive_and_mutation_rounds()
    test_standalone_push_debt()
    test_dispatch_and_deletion_contracts()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
