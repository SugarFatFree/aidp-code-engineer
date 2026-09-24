#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selfcheck.py — 契约检查脚本的**阳性对照自检**统一骨架（约定 35）。

## 为什么必须有这个东西

静态检查、lint、契约扫描的**失效形态恰好是「输出 0 错误」**——与「通过」在字面上完全一致。
真实实证：`vue-tsc` 因 `tsconfig.json` 的 `types` 指向未安装的包而提前中止，
源码零检查却输出「0 错误」，据其得出的「零新增」结论全是假绿；
同族还有上游 400 被吞成「0 条」、通用子串误判成功。

**不做阳性对照就无法区分「没问题」与「根本没跑」。** 故每个检查脚本在被当作判据之前，
都必须能自证有效：**注入一个必然被抓到的探针 → 确认它确实报红 → 才可以采信它的绿。**

## 为什么探针用「克隆真实契约树 + 注入」，而不是手搓最小 fixture

手搓 fixture 要求探针作者**准确复现每个检查器所需的目录脚手架**——写少一层目录，
检查器就扫不到探针、返回 0 命中，而这**与"检查器坏了"完全同形**：
本该发现问题的自检，自己先变成了假绿。克隆真实树则天然满足一切前置。

代价是每轮一次全树复制，用「先做一份种子副本，再 `cp -al` 硬链接分发」摊平：
种子只复制一次，每个探针的工作副本是硬链接，注入时**先 `os.remove` 再写新文件**
（断开硬链接、不回写种子）。

## 两侧对照，缺一不可

- **阳性对照**：注入探针 → 必须**报红**（退出码非 0 或 findings 非空）。抓不到 = 该检查未生效。
- **阴性对照**：同一份未注入的克隆 → 必须**不因探针而红**。只跑阳性对照证明得了"能红"，
  证明不了"不是恒红"——恒红的检查同样毫无判别力。

## 用法

    python3 AIDP_HOME/scripts/selfcheck.py                 # 跑全部已登记探针
    python3 AIDP_HOME/scripts/selfcheck.py --only check_md_anchors.py
    python3 AIDP_HOME/scripts/selfcheck.py --json
    python3 AIDP_HOME/scripts/<某个检查脚本>.py --self-check   # 单个脚本自检（等价于 --only）

退出码：0 = 全部已登记探针自证有效；1 = 有探针未报红（该检查已失效）；2 = 入参错。
**未登记探针的脚本不判失败**，但会计入 `unregistered` 并在摘要里点名——
⛔ 覆盖缺口必须可见，不许静默当成"全都自检过了"。
"""
import sys as _aidp_sys
from pathlib import Path as _AidpPath
_aidp_scripts = str(_AidpPath(__file__).resolve().parent)
if _aidp_scripts not in _aidp_sys.path:
    _aidp_sys.path.insert(0, _aidp_scripts)
from aidp_runtime import project_root, runtime_relpath, runtime_text
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = str(project_root(__file__))
RUNTIME_REL = runtime_relpath("", __file__)
# 克隆到工作副本里的内容（检查器的扫描面全在这些路径下）
SEED_ITEMS = (RUNTIME_REL, "docs/init", "docs/deployment", "设计目标.md",
              "README.md", "AGENTS.md", "CLAUDE.md", "版本变更历史.md")


# ————————————————————————— 注入工具 —————————————————————————

def _append(root, rel, text):
    """断开硬链接后追加——⛔ 不能直接以 'a' 打开：那会写穿到种子副本。"""
    p = os.path.join(root, rel)
    old = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
    if os.path.exists(p):
        os.remove(p)
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(old + text)


def _write(root, rel, text):
    p = os.path.join(root, rel)
    if os.path.exists(p):
        os.remove(p)
    d = os.path.dirname(p)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def _first(root, rel_dir, suffix=".md", exclude=()):
    d = os.path.join(root, rel_dir)
    if not os.path.isdir(d):
        return None
    for fn in sorted(os.listdir(d)):
        if fn.endswith(suffix) and fn not in exclude:
            return os.path.join(rel_dir, fn)
    return None


# ————————————————————————— 探针登记表 —————————————————————————
# 每项：mutate(root) 注入一个**必然被该检查抓到**的违规；args 为附加参数（--root 自动补）。
# unsupported 项写明原因——⛔ 留空等于把覆盖缺口藏起来。

PROBES = {}


def probe(name, args=("--json",)):
    def deco(fn):
        PROBES[name] = {"mutate": fn, "args": list(args)}
        return fn
    return deco


def unsupported(name, reason):
    PROBES[name] = {"unsupported": reason}


@probe("check_doc_numbering.py")
def _p_doc_numbering(root):
    _append(root, runtime_text('__AIDP_HOME__/reference/命令速查.md', __file__),
            "\n\n## 探针\n\n- **1. 甲**\n- **2. 乙**\n- **2. 丙**\n")


@probe("check_case_ledger_pending.py", args=("--json", "--version", "SELFCHECK"))
def _p_case_ledger(root):
    # 阴性侧：种子树无 docs/testing/SELFCHECK → pending=0 → 绿（不恒红）。
    # 阳性侧：造一份带待级联条目的用例增量册 → 必须报 pending。
    _write(root, "docs/testing/SELFCHECK/研发自测/_开发期用例增量.md",
           "## 待级联\n\n- C-001 · 01-02 10:00 · 加了个筛选项 · sprint-001\n")


@probe("check_private_markers.py")
def _p_private_markers(root):
    # 地址用拼接构造：本文件自身也在扫描面内，不能出现点分内网地址字面量
    addr = ".".join(["10", "20", "30", "40"])
    _append(root, runtime_text('__AIDP_HOME__/reference/命令速查.md', __file__), "\n\n探针：连 `http://%s:8080` 看看\n" % addr)


@probe("check_runtime_paths.py")
def _p_runtime_paths(root):
    _append(root, runtime_text('__AIDP_HOME__/reference/命令速查.md', __file__),
            runtime_text('\n\n探针：`python3 __AIDP_HOME__/scripts/runtime-path-probe.py`\n', __file__))


@probe("check_code_symbol_refs.py")
def _p_code_symbol_refs(root):
    # "::" 拼接：本文件自身也在扫描面内，字面量会被当成悬空引用
    ref = "selfcheck.py" + "::" + "_selfcheck_probe_missing_symbol"
    _append(root, runtime_text('__AIDP_HOME__/reference/命令速查.md', __file__), "\n\n探针：单一信源见 `%s`\n" % ref)


@probe("check_cli_invocation.py")
def _p_cli_invocation(root):
    _append(root, runtime_text('__AIDP_HOME__/reference/命令速查.md', __file__),
            runtime_text('\n\n```bash\npython3 __AIDP_HOME__/scripts/commit_gate.py --selfcheck-probe-no-such-flag\n```\n', __file__))


@probe("check_sql_ledger_comment.py", args=("--json", "--version", "SELFCHECK"))
def _p_sql_ledger_comment(root):
    # 阴性侧：种子树无 docs/deployment/SELFCHECK → no-add-column → 绿（不恒红）。
    # 阳性侧：造一份含 ADD COLUMN 的 SQL 而不给台账 → 必须报 ledger-missing。
    _write(root, "docs/deployment/SELFCHECK/sql/增量/01_加列.sql",
           "ALTER TABLE T_X ADD COLUMN STATUS INT;\n")


@probe("check_underscore_glob.py")
def _p_underscore_glob(root):
    # 注入一条四族目录的通配式 .md 扫描、且漏排 `_*` —— 必须被抓到。
    _append(root, runtime_text('__AIDP_HOME__/flows/sprint-batch/step-6.md', __file__),
            '\n\n```bash\nX=$(find "$V/研发自测" -maxdepth 2 -name "*.md" '
            '-not -name "README.md" 2>/dev/null)\n```\n')


@probe("check_testdata_prereq.py", args=("--json", "--version", "SELFCHECK"))
def _p_testdata_prereq(root):
    # 阴性对照侧：种子树没有 docs/testing/SELFCHECK/ → 判 no-casebook → 绿（不恒红）。
    # 阳性对照侧：造出用例册 + 账号文件，再植入上游标准占位符 → 必须报 GAP。
    base = "docs/testing/SELFCHECK/研发自测"
    _write(root, base + "/01_测试环境与账号.md", "# 测试环境与账号\n- 管理员: admin\n")
    _write(root, base + "/02_用例.md",
           "### 套件 SUITE-X\n前置数据：对照企业 {待用户填写: 对照企业账号}\n")


@probe("check_banned_terminology.py")
def _p_banned(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-plan.md', __file__),
            "\n\n本命令负责把今日任务映射到 Sprint / User Story，由 PM 负责用户故事拆分。\n")


@probe("check_md_anchors.py")
def _p_md_anchors(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-plan.md', __file__),
            "\n\n见 [不存在的小节](#zzz-selfcheck-dead-anchor-9871)。\n")


@probe("check_loop_examples.py")
def _p_loop(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-autopilot.md', __file__),
            "\n\n```bash\n/loop 10m /sprint-autopilot\n```\n")


@probe("check_flow_shell_escapes.py")
def _p_shell_escapes(root):
    # ⚠️ 要注入的是**两个反斜杠**：`\\n` 才是被禁的双重转义，
    #    单个 `\n` 在 shell 单引号里是 printf 的正确写法、本就不该报。
    _append(root, runtime_text('__AIDP_HOME__/flows/sprint-autopilot/phase-1.md', __file__),
            "\n\n```bash\nprintf '%s\\\\n' 001 002\n```\n")


@probe("check_flow_bash_syntax.py")
def _p_bash_syntax(root):
    _append(root, runtime_text('__AIDP_HOME__/flows/sprint-autopilot/phase-1.md', __file__),
            "\n\n```bash\nif [ -n \"$X\" ]; then\n  echo unbalanced\n```\n")


@probe("check_line_refs.py")
def _p_line_refs(root):
    # ⚠️ 必须用 .md 路径：该检查只守 Markdown 之间的行号引用（MD_NAME_RE），
    #    拿 .py:NNN 当探针会"抓不到"，那是探针写错、不是检查失效。
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-plan.md', __file__),
            runtime_text('\n\n判据见 `__AIDP_HOME__/reference/命令速查.md:1234`。\n', __file__))


@probe("check_singlesource_pointer.py")
def _p_singlesource(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-plan.md', __file__),
            runtime_text('\n\n本规则**单一信源 = `__AIDP_HOME__/reference/zzz-selfcheck-not-exist.md`**，此处不复述。\n', __file__))


@probe("check_skill_ref_drift.py")
def _p_skill_ref(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-plan.md', __file__),
            runtime_text('\n\n判据见 `__AIDP_HOME__/skills/dev-execution-planner/references/zzz-selfcheck-missing.md`。\n', __file__))


@probe("check_ghost_flags.py")
def _p_ghost_flags(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-autopilot.md', __file__),
            "\n\n可用 `/sprint-autopilot --zzz-selfcheck-ghost-flag` 跳过本步。\n")


@probe("check_shard_id_style.py")
def _p_shard_style(root):
    _write(root, runtime_text('__AIDP_HOME__/flows/sprint-autopilot/phase-9-probe.md', __file__),
           "# 探针\n\n### Step 9.1：甲\n\n正文\n\n### 9.2：乙\n\n正文\n")


@probe("check_cross_file_dup.py")
def _p_cross_dup(root):
    blob = ("\n\n" + ("本段用于自检阳性对照，逐字重复于两个文件之间，"
                      "用来验证跨文件长片段重复检测确实生效，绝不可被静默放过。" * 4) + "\n")
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-plan.md', __file__), blob)
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-start.md', __file__), blob)


@probe("check_ui_fidelity.py")
def _p_ui_fidelity(root):
    _write(root, "code/backend/probe/src/main/java/ExportProbe.java",
           "public class ExportProbe {\n"
           "  public void exportList(Integer pageNo, Integer pageSize) {\n"
           "    PageHelper.startPage(pageNo, pageSize);\n"
           "    write(mapper.selectList());\n"
           "  }\n}\n")


@probe("check_upstream_call_log.py")
def _p_upstream_log(root):
    _write(root, "code/backend/probe/src/main/java/SmsClientProbe.java",
           "public class SmsClientProbe {\n"
           "  public String send(String phone, String code) {\n"
           "    return restTemplate.postForObject(\"http://sms.example.com/v2/send\", req, String.class);\n"
           "  }\n}\n")


@probe("check_arguments_channel.py")
def _p_args_channel(root):
    # 判据 = 分片用了 $ARGUMENTS、命令正文却没声明接收通道
    _write(root, runtime_text('__AIDP_HOME__/commands/zzz-selfcheck-probe.md', __file__),
           "# /zzz-selfcheck-probe — 探针命令\n\n## 执行步骤\n\n1. 读取参数\n")
    _write(root, runtime_text('__AIDP_HOME__/flows/zzz-selfcheck-probe/step-1.md', __file__),
           "# 探针分片\n\n```bash\nARGS=\"$ARGUMENTS\"\n```\n")


@probe("check_convention30_prose.py")
def _p_conv30(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-plan.md', __file__),
            "\n\n本步骤原来是先取号再校验，现在改成先校验再取号（V4.7 起），"
            "之所以这么改是因为旧顺序会漏号。\n")


@probe("check_chain_unattended.py")
def _p_chain(root):
    _append(root, runtime_text('__AIDP_HOME__/flows/sprint-autopilot/phase-3-5.md', __file__),
            "\n\n串联下游：调用 `/sprint-batch --skip-aiauto-test` 跑完本版全部 Sprint。\n")


@probe("check_freeze_contract.py")
def _p_freeze(root):
    _append(root, runtime_text('__AIDP_HOME__/flows/sprint-autopilot/phase-2.md', __file__),
            "\n\n```bash\n$BE --version \"$V\" set needs_human true\n```\n")


@probe("check_skill_gate_list.py")
def _p_skill_gate(root):
    # 判据两个条件缺一不可：① 行内有「维度 N / N / N」枚举（ENUM_RE）
    # ② 同一行出现某个**声明过「不另立名单」的 SKILL** 的归属标识。
    # ⇒ 探针里的 SKILL 名不能随便挑，必须现取（当前是 auto-test-runner）。
    base = os.path.join(root, runtime_text('__AIDP_HOME__/skills', __file__))
    owner = None
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        d = os.path.join(base, name)
        if not os.path.isdir(d) or name == "aidp-code-engineer":
            continue
        for dp, _dn, fns in os.walk(d):
            for f in fns:
                if f.endswith(".md"):
                    try:
                        t = open(os.path.join(dp, f), encoding="utf-8", errors="replace").read()
                    except OSError:
                        continue
                    if "不另立名单" in t or "不另列名单" in t or "判据就是标记本身" in t:
                        owner = name
                        break
            if owner:
                break
        if owner:
            break
    assert owner, "没有任何 SKILL 声明「不另立名单」，本门不适用 —— 探针无从构造"
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-aiauto-test.md', __file__),
            "\n\n`%s` 的维度 1 / 3 / 5 任一不通过 → 阻断验收。\n" % owner)


@probe("check_design_goals.py")
def _p_design_goals(root):
    # ⚠️ 棘轮**放行纯新增**（那是刻意设计），所以探针必须【改动既有目标】而不是加一条新的。
    p = os.path.join(root, "设计目标.md")
    body = open(p, encoding="utf-8").read()
    marker = "- **G-AUTOPILOT-1** —"
    assert marker in body
    line = next(l for l in body.splitlines() if l.startswith(marker))
    os.remove(p)
    open(p, "w", encoding="utf-8").write(
        body.replace(line, marker + " 探针改写：本行用于验证指纹棘轮确实会拦住目标改动。"))


@probe("check_flow_var_refs.py")
def _p_flow_vars(root):
    _append(root, runtime_text('__AIDP_HOME__/flows/sprint-autopilot/phase-2.md', __file__),
            "\n\n```bash\necho \"$ZZZ_SELFCHECK_NEVER_PRODUCED\"\n```\n")


@probe("check_tick_var_supply.py")
def _p_tick_vars(root):
    # 判据面是 autopilot_tick_flags.py 的 DERIVED_VARS 登记表：
    # 「登记了、但全仓没有任何供给点」才是它要抓的。故探针改的是登记表本身。
    p = os.path.join(root, runtime_text('__AIDP_HOME__/scripts/autopilot_tick_flags.py', __file__))
    body = open(p, encoding="utf-8").read()
    anchor = "DERIVED_VARS = {"
    assert anchor in body
    os.remove(p)
    open(p, "w", encoding="utf-8").write(
        body.replace(anchor, anchor + '\n    "zzz-selfcheck": ["ZZZ_SELFCHECK_UNSUPPLIED"],', 1))


@probe("check_shard_counts.py")
def _p_shard_counts(root):
    _append(root, runtime_text('__AIDP_HOME__/flows/README.md', __file__),
            "\n\n> `sprint-autopilot/` 目录共 99 片。\n")


@probe("check_skill_ref_freshness.py")
def _p_skill_fresh(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/sprint-design.md', __file__),
            "\n\n判据见 `dev-logic-architect` 检查项 999「探针」。\n")


@probe("check_deployment_path_refs.py")
def _p_deploy_paths(root):
    _append(root, runtime_text('__AIDP_HOME__/commands/version.md', __file__),
            "\n\n产物落 `docs/deployment/{version}/sql/01_初始化.sql` 与 "
            "`docs/deployment/{version}/配置文件/配置项清单.md`。\n")


@probe("check_count_claims.py")
def _p_count_claims(root):
    _append(root, runtime_text('__AIDP_HOME__/reference/命令速查.md', __file__),
            "\n\n## 探针\n\n本范式共 99 项核心约定。\n")  # <!-- countclaim-check: ignore 探针文本，非本仓自称计数；标记刻意留在字符串外，写进字符串会让注入内容自带豁免、探针当场失效 -->


@probe("check_convention_dup.py")
def _p_conv_dup(root):
    # 判据 = 约定主行的首句被逐字复制进细则分片 ⇒ 探针必须取【真实主行】，
    # 自己编一句"像那条约定"的话是抓不到的（首句探针是子串匹配）。
    # ⛔ 入口文件名**不能写死**：项目记忆文件按启用的 Agent 可能是 `AGENTS.md` 或
    #    `CLAUDE.md`（二者并存时 `CLAUDE.md` 是 `@AGENTS.md` 薄壳，抽不出主行）。
    #    写死其一会让另一形态的项目一跑 selfcheck.py 就整个崩掉。
    #    候选顺序：agent_env 解析出的记忆文件 → AGENTS.md → CLAUDE.md。
    src = ""
    try:
        sys.path.insert(0, SCRIPTS_DIR)
        from agent_env import memory_file as _memory_file
        first = _memory_file(root)
    except ImportError:
        first = "AGENTS.md"
    cands = []
    for cand in (runtime_text('__AIDP_HOME__/AIDP-AGENTS.md', __file__), first, "AGENTS.md", "CLAUDE.md"):
        if cand not in cands:
            cands.append(cand)
    for cand in cands:
        try:
            src = open(os.path.join(root, cand), encoding="utf-8").read()
        except OSError:
            continue
        if any(l.startswith("20. **") for l in src.splitlines()):
            break
    line = next((l for l in src.splitlines() if l.startswith("20. **")), None)
    if line is None:
        raise RuntimeError(
            "项目记忆文件都取不到约定 20 主行（AGENTS.md / CLAUDE.md）—— "
            "探针无法注入真实主行，不能用自造句子冒充（首句探针是子串匹配，假句子抓不到）")
    _append(root, runtime_text('__AIDP_HOME__/reference/约定细则-1.md', __file__), "\n\n" + line + "\n")


unsupported("autopilot_reset.py",
            "它是**执行器**不是检查器：本骨架的判据是「注入探针后由绿转红」，"
            "而本脚本的两侧是「未命中 reset → 0」与「命中 → 10/11」，"
            "同一组 args 下基线侧就已非零，两边无从分辨。"
            "双侧对照（未命中 / --reset-baseline 删文件）"
            "由 tests/test_guard_scripts.py::test_autopilot_reset 的临时目录夹具覆盖。")


@probe("check_prose_vs_executable.py")
def _p_prose_exec(root):
    # 判据 = 某 flow 目录的散文承诺了某动作、该目录的 bash 围栏里却一次都没有。
    # ⚠️ 动作词取自脚本的 ACTIONS 白名单，自造名字抓不到；且必须新建目录——
    #    往 sprint-autopilot/ 里加，那边围栏本来就有 notify.py，配平后不报。
    _write(root, runtime_text('__AIDP_HOME__/flows/zzz-selfcheck-probe/step-1.md', __file__),
           "# 探针分片\n\n本步完成后经 `notify.py` 发里程碑通知并登记通知台账。\n")


@probe("check_step_index_coverage.py")
def _p_step_index(root):
    # 判据带「表里已列举 ≥2 个同级兄弟」的守卫 ⇒ 探针编号必须落在**已有的编号族**里
    # （Phase 3.x），另起 Phase 9.x 会因无兄弟而被守卫正当地放过。
    _write(root, runtime_text('__AIDP_HOME__/flows/sprint-autopilot/phase-3-99-probe.md', __file__),
           "# 探针分片\n\n### Phase 3.99：探针步骤\n\n正文。\n")


@probe("check_yield_guard.py")
def _p_yield_guard(root):
    # 阴性侧：现存 yield 站点全在 KNOWN_OPEN 里 → 只报「待修」不抬退出码 → 绿（不恒红）。
    # 阳性侧：在一个不在 KNOWN_OPEN 的分片里新起一个 yield 站点、且不带守卫 → 必须报红。
    _append(root, runtime_text('__AIDP_HOME__/flows/sprint-batch/step-6.md', __file__),
            "\n```bash\nexit 0   # 让位本 tick（探针）\n```\n")


@probe("check_release_ask_whitelist.py")
def _p_release_ask(root):
    # 阴性侧：现有 25 处 AskUserQuestion 提及都能指名归属 → 绿（不恒红）。
    # 阳性侧：在发布分片里新起一处无归属的问询 → 必须报红。
    _append(root, runtime_text('__AIDP_HOME__/flows/version/release-3.md', __file__),
            "\n\n随便问一句 AskUserQuestion 要不要继续\n")


unsupported("autopilot_fail_handle.py",
            "它是**写入器**不是检查器：跑一次就会 bump streak / 写冻结四件套 / 发里程碑通知，"
            "在共享沙箱里注入即产生真实副作用，且没有「该报红」的概念。"
            "行为验证在 tests/test_guard_scripts.py 的「失败处置五步」组（临时 baseline + --no-card）。")
unsupported("check_index_staleness.py",
            "判据要比 git index 记录的 blob 与磁盘内容，而本沙箱是 tempfile 硬链接副本、无 .git —— "
            "在这里它恒走「非 git 仓库」跳过分支，注入什么都不会变红。"
            "真实双侧对照在 tests/test_guard_scripts.py 的「隐形漂移」组："
            "那里现建一个临时 git 仓库，用 `git update-index --assume-unchanged` 精确复现"
            "「status 看不见这个文件」的状态，再改内容验证报红。")
unsupported("check_memory_loss.py",
            runtime_text('基线优先取 `--snapshot` 写前快照（memory/.aidp/memory-snapshot/），无快照时取 `git HEAD`；本沙箱是 tempfile 硬链接副本、无 .git、无快照也不含 memory/ —— 在这里它恒走「无可比基线」分支、注入什么都不会变红。真实双侧对照在 tests/test_guard_scripts.py 的「memory 整段被吞」组：那里现建一个临时 git 仓库、提交基线、再删一段验证报红，并用「填占位符」做阴性对照。', __file__))
unsupported("check_changelog_fix_scope.py",
            "判据是「被修文件的引入点是否晚于上一个已发布 tag」，要真实 git 历史 + tag；"
            "克隆树无 .git ⇒ 恒判 not-a-git-repo（不适用、绿），注入探针也红不了——"
            "这是正确行为而非失效。已由 tests/test_guard_scripts.py::test_changelog_fix_scope "
            "用 git init 夹具做完整阳性/阴性对照（含边界与豁免）。")


@probe("check_release_debt_landing.py")
def _p_release_debt(root):
    # 给发布分片加一处「失败兜底只 echo」的调用：必被判 ERROR。
    _write(root, runtime_text('__AIDP_HOME__/flows/version/release-zzz-probe.md', __file__),
           runtime_text('```bash\npython3 __AIDP_HOME__/scripts/check_zzz.py --version "$V" \\\n  || echo "⚠️ 未过 → 请自行登记欠账"\n```\n', __file__))


@probe("check_version_audit_landed.py", args=("--json", "--version", "SELFCHECK"))
def _p_version_audit_landed(root):
    # 造出 SELFCHECK 版本的规划产物、但**不产**审计报告：本门必判「审计没跑过」。
    # （基线侧没有 docs/requirements/SELFCHECK/ → 适用范围外、N/A 跳过 ⇒ 绿。）
    _write(root, "docs/requirements/SELFCHECK/01_研发需求.md", "# 研发需求\n\n- F1 登录\n")


@probe("check_comment_ratio.py")
def _p_comment_ratio(root):
    # 40 行同义反复的行内注释 + 20 行代码：注释块长度 40 > DECL_DOC_MAX_RUN，
    # 拿不到「声明文档」扣减，且不含 A 档特征 ⇒ 必被判超标。
    # （`code/` 不在 SEED_ITEMS 里，故基线侧是「无目标目录 → skipped」的绿。）
    _write(root, "code/backend/probe/Probe.java",
           "\n".join(["// 设置用户名"] * 40 + ["int x%d = %d;" % (i, i) for i in range(20)]))


unsupported("check_release_residual_gate.py",
            "本门对「用例目录不存在」是 fail-closed 的：沙箱种子不含 docs/testing/（模板项目"
            "根本没有版本目录），基线侧就已经红着、且与注入侧同为 1 条发现 —— 两边无从分辨。"
            "这是正确行为而非失效。真实双侧对照在 tests/test_release_gates.py：那里造合法表做"
            "阴性、再分别注入 skipped / 沿用上一轮日期做阳性，另跑脚本自带的 --self-check。")


unsupported("check_cascade_landing.py",
            "判据取自 git 工作区状态 / `--base-ref` 差异；克隆树无 git 历史，"
            "注入文件不会出现在任何 diff 里 ⇒ 探针必然 0 命中，与"
            "「检查失效」同形。改由 tests/test_guard_scripts.py 里的 git 夹具覆盖。")
unsupported("check_cascade_obligation.py",
            "同上：以 git 归档提交 + 台账文件的时间关系为判据，需真实 git 历史。")
unsupported("check_cascade_residue.py",
            "需 `--old/--new` 两个版本目录的真实内容差，属跨版本夹具，"
            "由 tests/test_guard_scripts.py 覆盖。")
unsupported("check_design_anchor.py",
            "需 `--version` + 该版本详细设计 + 对应源码树三者齐备的夹具；"
            "已由 tests/test_guard_scripts.py 的专用夹具覆盖。")
unsupported("check_sprint_numbering.py",
            "以 `docs/plans/{version}/` 跨版本 Sprint 序列为判据，"
            "需多版本目录夹具，由 tests/test_guard_scripts.py 覆盖。")
unsupported("check_version_identifier.py",
            "需 `--version` + 代码内自报版本标识的真实落点；克隆树不含 code/ 版本标识。")
unsupported("incremental_cases.py",
            "判据是 git diff（需要真实提交历史 + 基准 ref），克隆树无 .git；"
            "已由 tests/test_guard_scripts.py 的真 git 仓库夹具覆盖（含三态对照）。")
unsupported("aidp_scheduler.py",
            "不是契约扫描器：产出的是操作系统定时任务（systemd --user / crontab / launchd / schtasks），"
            "克隆树里注入文件不改变其判定。脚本自带 `--self-check`（临时目录内渲染并核对两条链路的"
            "定时任务单元），完整行为对照在 tests/test_aidp_scheduler.py。")
unsupported("check_webmcp.py",
            "整脚本以「本项目是否启用 WebMCP」为总门（默认关），克隆树恒判未启用、"
            "所有检查项按设计跳过——注入探针也不会红，这是**正确行为**而非失效。")


def _run(script, root, extra):
    cmd = [sys.executable, os.path.join(SCRIPTS_DIR, script), "--root", root] + list(extra)
    p = subprocess.run(cmd, capture_output=True, text=True)
    findings = None
    if "--json" in extra:
        try:
            data = json.loads(p.stdout)
            findings = 0
            # ⚠️ 计【全部】条目、不按 severity 过滤：本仓有 WARN 级检查器
            # （如 check_line_refs），只数 ERROR 会让它的探针永远"没变红"——
            # 那正是本骨架要消灭的假绿，不能在骨架自身上再犯一次。
            for k in ("errors", "warns", "warnings", "findings",
                      "violations", "problems", "importants"):
                v = data.get(k)
                if isinstance(v, list):
                    findings += len(v)
            for k in ("critical", "important"):
                if isinstance(data.get(k), int):
                    findings += data[k]
        except (ValueError, AttributeError):
            findings = None
    return p.returncode, findings, (p.stdout or "")[-400:], (p.stderr or "")[-400:]


def _make_seed():
    seed = tempfile.mkdtemp(prefix="aidp-selfcheck-seed-")
    for item in SEED_ITEMS:
        src = os.path.join(REPO_ROOT, item)
        if not os.path.exists(src):
            continue
        dst = os.path.join(seed, item)
        if os.path.isdir(src):
            shutil.copytree(src, dst,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "node_modules"))
        else:
            shutil.copy2(src, dst)
    return seed


def _clone(seed):
    work = tempfile.mkdtemp(prefix="aidp-selfcheck-work-")
    for item in os.listdir(seed):
        src, dst = os.path.join(seed, item), os.path.join(work, item)
        if os.path.isdir(src):
            subprocess.run(["cp", "-al", src, dst], check=True)
        else:
            os.link(src, dst)
    return work


def check_one(script, seed):
    spec = PROBES.get(script)
    if spec is None:
        return {"script": script, "status": "unregistered",
                "detail": "未登记探针——该脚本的绿【未经自证】"}
    if "unsupported" in spec:
        return {"script": script, "status": "unsupported", "detail": spec["unsupported"]}

    args = spec["args"]
    neg_root = _clone(seed)
    pos_root = _clone(seed)
    try:
        neg_rc, neg_find, neg_out, neg_err = _run(script, neg_root, args)
        spec["mutate"](pos_root)
        pos_rc, pos_find, pos_out, pos_err = _run(script, pos_root, args)
    finally:
        shutil.rmtree(neg_root, ignore_errors=True)
        shutil.rmtree(pos_root, ignore_errors=True)

    if neg_rc == 2 or pos_rc == 2:
        return {"script": script, "status": "fail",
                "detail": "脚本以 exit 2（入参/环境错）结束，自检无法判定",
                "neg_rc": neg_rc, "pos_rc": pos_rc, "stderr": pos_err or neg_err}
    reddened = (pos_rc != 0 and neg_rc == 0)
    if not reddened and pos_find is not None and neg_find is not None:
        reddened = pos_find > neg_find
    if reddened:
        return {"script": script, "status": "pass",
                "neg_rc": neg_rc, "pos_rc": pos_rc,
                "neg_findings": neg_find, "pos_findings": pos_find}
    return {"script": script, "status": "fail",
            "detail": "注入探针后该检查【没有变红】——它当前抓不到本该抓到的东西",
            "neg_rc": neg_rc, "pos_rc": pos_rc,
            "neg_findings": neg_find, "pos_findings": pos_find, "stdout": pos_out}


def all_check_scripts():
    return sorted(f for f in os.listdir(SCRIPTS_DIR)
                  if f.startswith("check_") and f.endswith(".py"))


def run_self_check(script, json_out=False):
    """给各检查脚本的 `--self-check` 调用：只跑自己那一个探针。"""
    seed = _make_seed()
    try:
        res = check_one(script, seed)
    finally:
        shutil.rmtree(seed, ignore_errors=True)
    if json_out:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("[%s] %s %s" % (res["status"].upper(), script, res.get("detail", "")))
    return 1 if res["status"] == "fail" else 0


def main():
    ap = argparse.ArgumentParser(description="契约检查脚本的阳性对照自检")
    ap.add_argument("--only", help="只自检指定脚本（文件名）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    targets = [args.only] if args.only else all_check_scripts()
    if args.only and not os.path.isfile(os.path.join(SCRIPTS_DIR, args.only)):
        print("[ERROR] 无此脚本: %s" % args.only, file=sys.stderr)
        return 2

    seed = _make_seed()
    try:
        results = [check_one(s, seed) for s in targets]
    finally:
        shutil.rmtree(seed, ignore_errors=True)

    tally = {}
    for r in results:
        tally[r["status"]] = tally.get(r["status"], 0) + 1
    summary = {"total": len(results), "tally": tally, "results": results}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r["status"] != "pass":
                print("[%-12s] %s — %s" % (r["status"].upper(), r["script"], r.get("detail", "")))
        print("自检 %d 个脚本：%s" % (len(results),
                                  " / ".join("%s=%d" % kv for kv in sorted(tally.items()))))
        if tally.get("unregistered"):
            print("⚠️ 有 %d 个脚本尚未登记探针，其检查结果【未经自证】——"
                  "覆盖缺口刻意报出来，不计入失败。" % tally["unregistered"])
    return 1 if tally.get("fail") else 0


if __name__ == "__main__":
    sys.exit(main())
