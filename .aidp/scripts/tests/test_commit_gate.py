#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交前门禁 `commit_gate.py`（约定 24）+ 提交/推送分类器单测（stdlib only）。

覆盖：
  · commit_gate：模板项目判定 / 业务代码判定 / 纯脚手架判定 / 约定 22 台账积压与多态识别 /
    suspected_cascade_bypass / 约定 41 链外档位（offchain）/ CICD 推送欠账（pending_cicd）/
    CLI 退出码 0·3 与 `--quiet` 下告警恒打印 / `commit_gate.enabled` 总开关；
  · classify_commit_change / classify_push：正式代码变更分类 + push/CICD 分流；

直接跑：`python3 .aidp/scripts/tests/test_commit_gate.py`
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
sys.path.insert(0, SCRIPTS)
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))

import commit_gate as G
import classify_commit_change as CCM

GATE = os.path.join(SCRIPTS, "commit_gate.py")
_passed = 0
_failed = 0
_skipped = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def skip(name, reason):
    global _skipped
    _skipped += 1
    print(f"  ⏭️ SKIP: {name}（{reason}）")


def mkfile(path, content="x\n"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _git(d, *a):
    return subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)


def _init_repo(d):
    _git(d, "init", "-q")
    _git(d, "config", "user.email", "alice@example.com")
    _git(d, "config", "user.name", "alice")


def _run_gate(d, *args):
    cp = subprocess.run([sys.executable, GATE, "--repo-root", d, *args],
                        capture_output=True, text=True, cwd=d)
    try:
        info = json.loads(cp.stdout)
    except ValueError:
        info = {}
    return cp, info


# ── commit_gate：纯函数判定 ──
def test_gate_pure():
    print("【commit_gate 纯函数：模板判定 / 业务代码 / 纯脚手架】")
    with tempfile.TemporaryDirectory() as d:
        check("空目录 → 非模板项目", G.is_template_project(d) is False)
        mkfile(os.path.join(d, G.SCAFFOLD_SKILL_REL))
        check("只有 SKILL.md、缺同步脚本 → 非模板项目", G.is_template_project(d) is False)
        mkfile(os.path.join(d, G.SCAFFOLD_SYNC_REL))
        check("SKILL.md + 同步脚本都在、无下游标记 → 模板项目", G.is_template_project(d) is True)
        mkfile(os.path.join(d, "memory/aidp-config.yaml"), "scaffold:\n  version: V1.0.0\n")
        check("★ 有 scaffold.version（下游标记）→ 即便带脚手架也不是模板项目",
              G.is_template_project(d) is False)

    with tempfile.TemporaryDirectory() as d:
        check("无配置 → commit_gate 默认开启", G.commit_gate_enabled(d) is True)
        mkfile(os.path.join(d, "memory/aidp-config.yaml"), "commit_gate:\n  enabled: false\n")
        check("commit_gate.enabled=false → 关闭", G.commit_gate_enabled(d) is False)
        mkfile(os.path.join(d, "memory/aidp-config.yaml"), "commit_gate:\n  enabled: true\n")
        check("commit_gate.enabled=true → 开启", G.commit_gate_enabled(d) is True)

    H = G.has_business_code_change
    check("纯文档提交 → 无代码", H(" M docs/x.md\n M README.md") is False)
    check("规则文档 → 无代码", H(" M .aidp/commands/a.md\n M AGENTS.md") is False)
    check("code/ 下 java → 有代码", H(" M code/backend/A.java") is True)
    check("源码扩展名(非 code/) → 有代码", H(" M src/App.vue") is True)
    check("纯配置(root yml/json) → 无代码", H(" M app.yml\n M x.json") is False)
    check("重命名 code 源文件 → 有代码", H("R  code/a.java -> code/b.java") is True)
    check("code/ 下 README → 无代码", H(" M code/frontend/README.md") is False)
    check("混合(文档+代码) → 有代码", H(" M docs/a.md\n M code/b.py") is True)
    check("空 working tree → 无代码", H("") is False)
    check("docs/ 下 html 报告 → 无代码", H(" M docs/reports/V0.1.0/index.html") is False)
    check("脚手架 .py 脚本(.aidp/skills) → 非业务代码",
          H(" M .aidp/skills/aidp-code-engineer/scripts/scaffold.py") is False)
    check("脚手架 .aidp/scripts/.py → 非业务代码", H(" M .aidp/scripts/commit_gate.py") is False)
    check("脚手架 .mjs → 非业务代码", H(" M .aidp/skills/x/helper.mjs") is False)
    check("Agent 适配层 .codex/.dsh 下脚本 → 非业务代码",
          H(" M .codex/hooks/a.py\n M .dsh/hooks/b.js") is False)
    check("混合(脚手架+code源码) → 仍有代码",
          H(" M .aidp/commands/version.md\n M code/backend/A.java") is True)

    C = G._is_scaffold_contract
    for p in (".aidp/commands/x.md", ".claude/settings.json", ".codex/config.toml", ".dsh/x.json",
              "docs/init/06_x.md", "scripts/x.py", ".aidp-rewrite-queue.txt", "AGENTS.md",
              "CLAUDE.md", "版本变更历史.md", "memory/aidp-config.yaml",
              "memory/.sprint-autopilot-baseline.json"):
        check(f"_is_scaffold_contract {p} → 是", C(p) is True)
    for p in ("code/backend/A.java", "docs/design/detail/V0.1.0/01_详细设计.md", "README.md"):
        check(f"_is_scaffold_contract {p} → 否", C(p) is False)

    S = G.is_scaffold_only_change
    sc = (" M .aidp/commands/version.md\n M scripts/scaffold.py\n M .aidp-rewrite-queue.txt\n"
          " M AGENTS.md\n M docs/init/06_x.md")
    check("纯脚手架升级 → is_scaffold_only_change True", S(sc) is True)
    check("混合(脚手架+码) → False", S(" M .aidp/x.md\n M code/A.java") is False)
    check("含迭代产物 → False", S(" M .aidp/x.md\n M docs/V0.1.0/研发需求/00_研发需求.md") is False)
    check("空树 → False", S("") is False)
    check("_porcelain_paths 首行路径完整(前导空格不丢)",
          G._porcelain_paths(" M .aidp/x.md\n M code/y.java")[0] == ".aidp/x.md")
    check("C-quote 路径被解码", G._porcelain_paths(' M "code/\\344\\270\\255.java"')[0] == "code/中.java")
    check("首行即脚手架路径 → True", S(" M AGENTS.md\n M .aidp/scripts/commit_gate.py") is True)


# ── commit_gate：约定 22 台账 + CLI 退出码 ──
def test_gate_cli_cascade():
    print("【commit_gate CLI：台账积压 stale / 退出码 3 / --quiet 告警恒打印】")
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d)
        mkfile(os.path.join(d, "README.md"), "doc\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "docs: init")
        cp, info = _run_gate(d, "--quiet")
        check("干净仓库 → 退出码 0 且 debts 为空", cp.returncode == 0 and info.get("debts") == [])
        expect = {"commit_gate_enabled", "is_template_project", "working_tree_dirty",
                  "has_business_code_change", "is_scaffold_only_change", "today",
                  "pending_cascade", "should_dispatch_cascade", "cascaded_not_cleaned",
                  "suspected_cascade_bypass", "pending_cicd", "offchain", "context", "debts"}
        check("JSON 字段集合与契约一致", set(info) == expect)
        check("today 为 YYYY-MM-DD", len(info.get("today") or "") == 10)
        check("context 默认 bare-conversation", info.get("context") == "bare-conversation")

        mkfile(os.path.join(d, "README.md"), "doc2\n")
        _git(d, "add", "-A")
        cp, info = _run_gate(d)
        check("纯文档改动 → 无业务代码、非纯脚手架",
              info["working_tree_dirty"] is True and info["has_business_code_change"] is False
              and info["is_scaffold_only_change"] is False and cp.returncode == 0)
        _git(d, "commit", "-qm", "docs: 2")

        mkfile(os.path.join(d, ".aidp/commands/foo.md"), "x\n")
        _git(d, "add", "-A")
        cp, info = _run_gate(d, "--context", "aidp-command")
        check("只改 .aidp/ → is_scaffold_only_change=True", info["is_scaffold_only_change"] is True)
        check("--context 原样回显", info["context"] == "aidp-command")
        _git(d, "commit", "-qm", "chore: scaffold")

        # ★ 一行式条目；「已知失准点」段 `- 🔴 C-NNN：…` 不重复计入
        led_dir = os.path.join(d, "docs", "requirements", "V0.2.0", "研发需求")
        led = os.path.join(led_dir, "_开发期需求增量.md")
        yd = (date.today() - timedelta(days=1)).strftime("%m-%d")
        td = date.today().strftime("%m-%d")
        mkfile(led, "# 开发期变更台账 — V0.2.0\n\n"
                    "## ⚠️ 已知失准点\n\n- 🔴 C-008：详设 §4.2 仍含 XLSX\n\n"
                    "## 待级联\n\n"
                    f"- C-008 · {yd} 16:05 · 🔴 导出去掉 XLSX 选项 · sprint-012\n"
                    f"- C-007 · {yd} 14:32 · 列表加筛选项 · sprint-012\n")
        cp, info = _run_gate(d, "--quiet")
        pc = info.get("pending_cascade") or {}
        check("★ 一行式条目被正确计数（失准点行不重复计入）", pc.get("total") == 2 and pc.get("stale") == 2)
        check("★ 按版本归集台账", (pc.get("versions", {}).get("V0.2.0") or {}).get("total") == 2)
        check("★ 有 stale → should_dispatch_cascade=True", info.get("should_dispatch_cascade") is True)
        check("★★ 有欠账 → 退出码 3 + debts 含 cascade-stale",
              cp.returncode == 3 and "cascade-stale" in info.get("debts", []))
        check("★★ --quiet 下欠账告警仍打印到 stderr", "开发期变更台账" in cp.stderr)
        check("告警要求把义务清单写进用户可见回复", "未落地义务" in cp.stderr)

        cp2, _ = _run_gate(d, "--quiet", "--no-fail-on-debt")
        check("逃生阀 --no-fail-on-debt → 强制返 0", cp2.returncode == 0)

        mkfile(led, "# 台账\n\n## 待级联\n\n"
                    f"- C-010 · {td} 09:10 · 今天刚记 · sprint-013\n"
                    f"- C-009 · {yd} 16:05 · 昨天的 · sprint-012\n")
        _, info = _run_gate(d, "--quiet")
        pc = info["pending_cascade"]
        check("★ stale 只数昨天及更早（今天的不计）", pc.get("total") == 2 and pc.get("stale") == 1)
        mkfile(led, f"# 台账\n\n## 待级联\n\n- C-010 · {td} 09:10 · 今天刚记 · sprint-013\n")
        cp, info = _run_gate(d, "--quiet")
        check("★ 全是今天的条目 → 不派收口单、退出码 0",
              info["pending_cascade"].get("stale") == 0
              and info.get("should_dispatch_cascade") is False and cp.returncode == 0)

        # 已级联未删 / 归档标记未删
        mkfile(led, f"# 台账\n\n## 待级联\n\n- C-010 · {td} 09:10 · 今天刚记 ✅ 已级联 · sprint-013\n")
        cp, info = _run_gate(d, "--quiet")
        check("★ 已标记级联却未删 → cascade-not-cleaned + 退出码 3",
              info.get("cascaded_not_cleaned", 0) >= 1 and "cascade-not-cleaned" in info["debts"]
              and cp.returncode == 3)
        mkfile(led, "<!-- LEDGER-ARCHIVED -->\n# 台账\n\n## 待级联\n\n")
        cp, info = _run_gate(d, "--quiet")
        check("★ 归档标记不替代删除 → cascade-archived-not-deleted",
              "cascade-archived-not-deleted" in info["debts"] and cp.returncode == 3)
        mkfile(led, "# 台账\n\n## 待级联\n\n* 导出改了点东西\n* 列表也改了\n")
        _, info = _run_gate(d, "--quiet")
        check("★ 有实质内容却一条没认出 → cascade-unparsed（格式漂移要吭声）",
              "cascade-unparsed" in info["debts"])

        os.remove(led)
        cp, info = _run_gate(d, "--quiet")
        check("★ 台账删除后 total=0 且不再派收口单",
              info["pending_cascade"].get("total") == 0
              and info.get("should_dispatch_cascade") is False and cp.returncode == 0)

        # 总开关关闭 → 恒 0 且 debts 为空
        mkfile(led, f"# 台账\n\n## 待级联\n\n- C-001 · {yd} 10:00 · 旧条目 · sprint-1\n")
        mkfile(os.path.join(d, "memory/aidp-config.yaml"), "commit_gate:\n  enabled: false\n")
        cp, info = _run_gate(d, "--quiet")
        check("★ commit_gate.enabled=false → 退出码 0 且 debts 为空",
              cp.returncode == 0 and info.get("commit_gate_enabled") is False and info["debts"] == [])


# ── 约定 22 四族增量册 ──
def test_family_ledgers():
    print("【commit_gate 四族增量册 + cascade_ledger_paths】")
    root = tempfile.mkdtemp()
    try:
        paths = dict(G.cascade_ledger_paths(root, "V0.3.0"))
        check("四族共 4 个落点", set(paths) == {"req", "design", "plan", "case"})
        check("需求增量册与研发需求主文档同目录",
              paths["req"].endswith(os.path.join("docs", "requirements", "V0.3.0", "研发需求", "_开发期需求增量.md")))
        mkfile(paths["design"], "# 设计增量\n\n## 待级联\n\n- C-001 · 01-02 10:00 · 改接口 · sprint-1\n")
        mkfile(paths["case"], "# 用例增量\n\n## 待级联\n\n| C-002 | 2026-01-03 | 补用例 |\n")
        r = G.pending_cascade(root, "2026-09-01")
        v = r["versions"].get("V0.3.0") or {}
        check("★ 只改设计族的版本也被扫到（版本集取四族并集）", "design" in v.get("families", {}))
        check("★ 表格式条目被识别并按日期计 stale", (v.get("families", {}).get("case") or {}).get("stale") == 1)
        check("合计 total=2 stale=2", r["total"] == 2 and r["stale"] == 2)
        mkfile(paths["plan"], "# 计划增量\n\n## 待级联\n\n<!-- - C-009 · 08-27 10:00 · 教学示例 -->\n")
        r = G.pending_cascade(root, "2026-09-01")
        check("★ 注释里的教学示例不计入", (r["versions"]["V0.3.0"]["families"].get("plan") or {}).get("total") == 0)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# ── 约定 22 反向判据：疑似绕过攒批 ──
def test_cascade_bypass():
    print("【commit_gate suspected_cascade_bypass】")
    SB = G.suspected_cascade_bypass
    r = SB(" M code/backend/A.java\n M docs/design/detail/V0.1.0/01_详细设计.md\n")
    check("★ 代码 + 上游规划产物 + 册子未动 → 当场级联疑似绕过",
          r["suspected"] is True and r["shape"] == "当场级联")
    r = SB(" M code/backend/A.java\n M docs/design/detail/V0.1.0/01_详细设计.md\n"
           " M docs/design/detail/V0.1.0/_开发期设计增量.md\n")
    check("动了增量册 → 不报", r["suspected"] is False)
    r = SB(" M docs/design/detail/V0.1.0/01_详细设计.md\n")
    check("只改规划产物、无代码 → 不报", r["suspected"] is False)
    r = SB(" M code/backend/A.java\n M docs/plans/README.md\n")
    check("结构性 README（无版本段）不算规划产物", r["planning_count"] == 0)
    r = SB(" A code/backend/sql/V2__add.sql\n")
    check("★ 形态二：新增 SQL 零台账 → 结构性新增零台账",
          r["suspected"] is True and r["shape"] == "结构性新增零台账")
    r = SB(" M .aidp/scripts/x.py\n M docs/design/detail/V0.1.0/01_详细设计.md\n")
    check("脚手架脚本不算正式代码 → 不报", r["suspected"] is False)

    with tempfile.TemporaryDirectory() as d:
        _init_repo(d)
        mkfile(os.path.join(d, "README.md")); _git(d, "add", "-A"); _git(d, "commit", "-qm", "init")
        mkfile(os.path.join(d, "code/backend/A.java"), "class A {}\n")
        mkfile(os.path.join(d, "docs/design/detail/V0.1.0/01_详细设计.md"), "# d\n")
        _git(d, "add", "-A")
        cp, info = _run_gate(d, "--quiet")
        check("★ CLI：疑似绕过 → debts 含 cascade-bypass + 退出码 3",
              "cascade-bypass" in info.get("debts", []) and cp.returncode == 3)
        cp, info = _run_gate(d, "--quiet", "--cascade-now")
        check("★ --cascade-now 显式当场级联 → 抑制告警",
              info["suspected_cascade_bypass"].get("suppressed_by") == "--cascade-now"
              and "cascade-bypass" not in info["debts"])


# ── 约定 41：链外档位 ──
def test_offchain():
    print("【commit_gate offchain 档位】")
    with tempfile.TemporaryDirectory() as d:
        b = G.offchain_budget(d, "bare-conversation", " M code/a.vue\n M code/b.ts\n")
        check("XS：≤2 代码文件", b["tier"] == "XS" and b["deploy"] is False and b["applies"] is True)
        b = G.offchain_budget(d, "aidp-command", " M code/a.ts\n M code/b.ts\n M code/c.ts\n")
        check("S：≤5 文件；aidp-command 下 applies=False", b["tier"] == "S" and b["applies"] is False)
        mkfile(os.path.join(d, "code/sql/1.sql"), "ALTER TABLE t ADD COLUMN c INT;\n")
        b = G.offchain_budget(d, "bare-conversation", " M code/sql/1.sql\n")
        check("M：ALTER DDL", b["tier"] == "M" and b["ddl"] == "alter" and b["deploy"] == "ask-user")
        mkfile(os.path.join(d, "code/sql/2.sql"), "CREATE TABLE t (id INT);\n")
        b = G.offchain_budget(d, "bare-conversation", " A code/sql/2.sql\n")
        check("L：新表", b["tier"] == "L" and b["ddl"] == "new-table")
        check("恒定禁止项含铸 build 与浏览器实测", {"铸 build", "浏览器实测"} <= set(b["forbidden"]))
        check("档位只是下限（须语义自判）", b["tier_floor_only"] is True)


# ── 约定 31.5：CICD 推送欠账 ──
def test_pending_cicd():
    print("【commit_gate pending_cicd】")
    with tempfile.TemporaryDirectory() as base:
        remote = os.path.join(base, "remote.git")
        d = os.path.join(base, "work")
        subprocess.run(["git", "init", "-q", "--bare", remote], capture_output=True)
        os.makedirs(d)
        _init_repo(d)
        # classify_commit_change 由 _standalone_push_pending 按仓库内路径调用
        mkfile(os.path.join(d, ".aidp/scripts/classify_commit_change.py"),
               open(os.path.join(SCRIPTS, "classify_commit_change.py"), encoding="utf-8").read())
        mkfile(os.path.join(d, "package.json"), "{}\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "init")
        _git(d, "remote", "add", "origin", remote)
        _git(d, "checkout", "-q", "-B", "main")
        _git(d, "push", "-q", "-u", "origin", "main")
        mkfile(os.path.join(d, "memory/aidp-config.yaml"), "cicd:\n  provider: none\n")
        check("cicd.provider=none → 不适用", G.pending_cicd(d)["applicable"] is False)
        os.remove(os.path.join(d, "memory/aidp-config.yaml"))
        check("★ 默认 provider（未跑过 autopilot、无 baseline）→ 适用", G.pending_cicd(d)["applicable"] is True)
        check("HEAD 无正式代码变更 → 不报", G.pending_cicd(d)["pending"] is False)

        mkfile(os.path.join(d, "src/App.ts"), "export {}\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "feat: app")
        _git(d, "push", "-q", "origin", "main")
        head = _git(d, "rev-parse", "HEAD").stdout.strip()
        r = G.pending_cicd(d)
        check("★ 无 baseline 的项目：推送正式代码未经分类器 → pending", r["pending"] is True)
        bl = os.path.join(d, "memory/.sprint-autopilot-baseline.json")
        mkfile(bl, json.dumps({"versions": {"V0.1.0": {"current_build": "V0.1.0_build1001",
               "builds": [{"build": "V0.1.0_build1001", "cicd_skipped": True,
                           "change_classification": {"commit": "0" * 40}}]}}}))
        check("★ 某 build 曾分类过但不是本次 HEAD → 仍 pending（按 commit 键控）",
              G.pending_cicd(d)["pending"] is True)
        import time as _time
        old = _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime(_time.time() - 7200))
        rec = {"commit": head, "classified_at": old, "formal_code_change": True, "cicd_skipped": False}
        mkfile(bl, json.dumps({"versions": {"V0.1.0": {"standalone_pushes": [rec]}}}))
        r = G.pending_cicd(d)
        check("★ 已分类为正式代码、2 小时仍无部署终态 → pending", r["pending"] is True and "终态" in r["reason"])
        rec["deploy_terminal"] = "unknown:provider CLI 不可用"
        mkfile(bl, json.dumps({"versions": {"V0.1.0": {"standalone_pushes": [rec]}}}))
        check("★ deploy_terminal=unknown:<原因> → 显式记录，不算欠账", G.pending_cicd(d)["pending"] is False)
        rec.pop("deploy_terminal")
        rec["classified_at"] = _time.strftime("%Y-%m-%dT%H:%M:%S")
        mkfile(bl, json.dumps({"versions": {"V0.1.0": {"standalone_pushes": [rec]}}}))
        check("分类不足 1 小时（监听中）→ 不报", G.pending_cicd(d)["pending"] is False)


# ── classify_commit_change / classify_push ──
def test_classify_commit_change():
    print("【classify_commit_change 正式代码变更分类】")

    def classify(files, roots=()):
        with tempfile.TemporaryDirectory() as d:
            for root in roots:
                os.makedirs(os.path.join(d, root), exist_ok=True)
            return CCM.classify_commit_change(d, files)

    r = classify(["README.md", "docs/说明.md"])
    check("仅 Markdown → 不触发", r["has_formal_code_change"] is False
          and r["cicd_should_watch"] is False and r["skip_reason"] == "no-formal-code-change")
    r = classify(["docs/deployment/V0.1.0/sql/增量/01_init.sql", "docs/deployment/tools/apply.py"])
    check("部署 SQL/工具 → 不触发", r["has_formal_code_change"] is False
          and r["cicd_should_watch"] is False)
    r = classify(["docs/deployment/V0.1.0/reports/报告.html", "README.md"])
    check("部署报告/README → 不触发", r["has_formal_code_change"] is False
          and r["cicd_should_watch"] is False)
    r = classify(["deploy.sh", "scripts/publish.py"])
    check("根级部署工具 → 不触发", r["has_formal_code_change"] is False
          and r["cicd_should_watch"] is False)
    r = classify(["memory/data.py"])
    check("memory 记忆文件 → 不触发", r["has_formal_code_change"] is False
          and r["cicd_should_watch"] is False)
    r = classify(["src/main.ts"], ["src"])
    check("根 src 源码 → 触发", r["has_formal_code_change"] is True
          and r["cicd_should_watch"] is True)
    r = classify(["code/frontend/app/package.json"], ["code/frontend/app"])
    check("项目入口 package.json → 触发", r["has_formal_code_change"] is True
          and r["cicd_should_watch"] is True)
    r = classify(["package.json"], [])
    check("根级 package.json → 触发", r["has_formal_code_change"] is True
          and r["formal_code_files"] == ["package.json"])
    r = classify(["appsettings.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
                  "Cargo.lock", "go.sum", "poetry.lock"], [])
    check("JSON 配置与常见锁文件 → 触发", r["has_formal_code_change"] is True
          and r["formal_code_files"] == ["Cargo.lock", "appsettings.json", "go.sum",
                                          "package-lock.json", "pnpm-lock.yaml",
                                          "poetry.lock", "yarn.lock"])
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], check=True, capture_output=True)
        subprocess.run(["git", "-C", d, "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", d, "config", "user.name", "test"], check=True)
        mkfile(os.path.join(d, "README.md"), "base\n")
        subprocess.run(["git", "-C", d, "add", "README.md"], check=True)
        subprocess.run(["git", "-C", d, "commit", "-qm", "base"], check=True)
        for name in ("appsettings.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
                     "Cargo.lock", "go.sum", "poetry.lock"):
            mkfile(os.path.join(d, name), "x\n")
        r = CCM.classify_commit_change(d, None)
        check("正式项目根实际 JSON/锁文件 → 触发", r["has_formal_code_change"] is True
              and set(r["formal_code_files"]) == {"appsettings.json", "package-lock.json",
              "pnpm-lock.yaml", "yarn.lock", "Cargo.lock", "go.sum", "poetry.lock"})
    r = classify(["pom.xml", "go.mod"], [])
    check("根级 pom.xml/go.mod → 触发", r["has_formal_code_change"] is True
          and r["formal_code_files"] == ["go.mod", "pom.xml"])
    check("输出字段完整且无多余字段",
          set(r) == {"has_formal_code_change", "changed_files", "formal_code_files",
                     "non_formal_files", "cicd_should_watch", "skip_reason",
                     "classification_error", "source_roots"})
    with tempfile.TemporaryDirectory() as d:
        mkfile(os.path.join(d, "package.json"), "{}\n")
        mkfile(os.path.join(d, "mystery/package.json"), "{}\n")
        mkfile(os.path.join(d, "mystery/App.vue"), "<template />\n")
        r = CCM.classify_commit_change(d, ["package.json", "mystery/package.json", "mystery/App.vue"])
        check("已有根入口但未知一级目录仍 fail-closed", r["classification_error"] is True
              and r["cicd_should_watch"] is True
              and r["formal_code_files"] == ["package.json"]
              and r["skip_reason"] == "unrecognized-source-layout")
    with tempfile.TemporaryDirectory() as d:
        cli = subprocess.run([sys.executable, CCM.__file__, "--root", d, "--json", "说明.md"],
                             capture_output=True, text=True, check=False)
        data = json.loads(cli.stdout)
        check("CLI 接受可选 --json", cli.returncode == 0 and set(data) == set(r))
        check("CLI 非 ASCII 路径稳定转义", "\\u8bf4\\u660e.md" in cli.stdout)
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["git", "init", "-q", d], capture_output=True, check=False)
        r = CCM.classify_commit_change(d)
        check("无 HEAD 的 Git 仓库 → fail-closed", r["classification_error"] is True
              and r["cicd_should_watch"] is True)
    with tempfile.TemporaryDirectory() as d:
        r = CCM.classify_commit_change(d, None, "not-a-ref")
        check("无效 base_ref → fail-closed", r["classification_error"] is True
              and r["cicd_should_watch"] is True)
        r = CCM.classify_commit_change(d, ["src/a -> b.ts"])
        check("合法文件名含箭头不按重命名拆分", r["changed_files"] == ["src/a -> b.ts"])
        r = CCM.classify_commit_change(d, ["/tmp/App.vue", "src/../App.vue"])
        check("绝对路径与 .. 路径 → fail-closed", r["classification_error"] is True
              and r["cicd_should_watch"] is True)
        r = CCM.classify_commit_change(d, ["dist/App.js", "vendor/lib.js", "node_modules/x.js"])
        check("生成物/依赖目录 → 不触发", r["has_formal_code_change"] is False
              and r["cicd_should_watch"] is False)
    r = classify(["code/frontend/app/src/App.vue"], ["code/frontend/app/src"])
    check("前端源码 → 触发", r["has_formal_code_change"] is True
          and r["cicd_should_watch"] is True
          and r["formal_code_files"] == ["code/frontend/app/src/App.vue"])
    r = classify(["code/backend/app/src/main/java/App.java"], ["code/backend/app/src/main/java"])
    check("后端源码 → 触发", r["has_formal_code_change"] is True
          and r["cicd_should_watch"] is True)
    r = classify(["code/backend/app/requirements.txt", "code/backend/app/main.py"],
                 ["code/backend/app"])
    check("Python 项目 requirements.txt + main.py → 触发",
          r["has_formal_code_change"] is True
          and r["formal_code_files"] == ["code/backend/app/main.py",
                                          "code/backend/app/requirements.txt"])
    r = classify(["code/backend/app/requirements.txt"], ["code/backend/app"])
    check("仅 requirements.txt → 正式入口", r["has_formal_code_change"] is True
          and r["formal_code_files"] == ["code/backend/app/requirements.txt"])
    r = classify(["code/frontend/app/src/App.vue", "docs/设计.md"], ["code/frontend/app/src"])
    check("源码+文档 → 仅源码正式", r["formal_code_files"] == ["code/frontend/app/src/App.vue"]
          and r["non_formal_files"] == ["docs/设计.md"])
    r = classify(["code/web/src/App.vue", "code/server/src/App.java"],
                 ["code/web/src", "code/server/src"])
    check("code/web+code/server → 触发", r["has_formal_code_change"] is True
          and len(r["formal_code_files"]) == 2)
    r = classify(["mystery/App.vue"])
    check("未知源码布局 → fail-closed", r["classification_error"] is True
          and r["cicd_should_watch"] is True
          and r["skip_reason"] == "unrecognized-source-layout")


def test_classify_push_flow():
    print("【classify_push push/CICD 分流流程】")
    import classify_push as CP
    valid, reason = CP.validate_payload({"has_formal_code_change": "yes"})
    check("分类结果缺字段/布尔类型错误 → schema fail-closed", valid is False and reason)
    base_payload = {
        "has_formal_code_change": False, "changed_files": [], "formal_code_files": [],
        "non_formal_files": [], "cicd_should_watch": False,
        "skip_reason": "no-formal-code-change", "classification_error": False,
        "source_roots": [],
    }
    valid, _ = CP.validate_payload({**base_payload, "unexpected": True})
    check("分类结果未知字段 → schema fail-closed", valid is False)
    valid, _ = CP.validate_payload({**base_payload, "cicd_should_watch": True})
    check("非正式代码却 watch=true → 关系校验 fail-closed", valid is False)
    valid, _ = CP.validate_payload({**base_payload, "has_formal_code_change": True,
                                    "formal_code_files": ["src/App.ts"]})
    check("formal_code_files 与 has_formal 不一致 → fail-closed", valid is False)
    valid, _ = CP.validate_payload({**base_payload, "changed_files": ["docs/a.md"],
                                    "non_formal_files": []})
    check("changed_files 集合不守恒 → fail-closed", valid is False)
    valid, _ = CP.validate_payload({**base_payload, "changed_files": [""],
                                    "non_formal_files": [""]})
    check("空路径 → fail-closed", valid is False)
    valid, _ = CP.validate_payload({**base_payload, "has_formal_code_change": True,
                                    "changed_files": ["docs/a.md"],
                                    "formal_code_files": ["docs/a.md"],
                                    "non_formal_files": ["docs/a.md"],
                                    "cicd_should_watch": True, "skip_reason": None})
    check("formal/non-formal 文件重叠 → fail-closed", valid is False)
    valid, _ = CP.validate_payload({**base_payload, "classification_error": True,
                                    "skip_reason": "unrecognized-source-layout",
                                    "cicd_should_watch": True})
    check("classification_error 必须 watch=true 且使用错误原因", valid is True)
    with tempfile.TemporaryDirectory() as d:
        baseline = os.path.join(d, "baseline.json")
        mkfile(baseline, json.dumps({"versions": {"V0.1.0": {}}}))
        CP.persist(d, "V0.1.0", "", CP.normalize_result(base_payload),
                   __import__("pathlib").Path(baseline), standalone=True)
        with open(baseline, encoding="utf-8") as f:
            standalone_record = json.load(f)["versions"]["V0.1.0"]["release_change_classification"]
        check("无 current_build 的 standalone 发布写版本级分类", standalone_record["cicd_skipped"] is True)
    script = os.path.join(os.path.dirname(HERE), "classify_push.py")
    bundle_script = os.path.join(os.path.dirname(HERE),
                                 "../skills/aidp-code-engineer/assets/aidp/scripts/classify_push.py")

    def run_case(files, changed, script_path=script, uncommitted=()):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run(["git", "init", "-q", d], check=True, capture_output=True)
            subprocess.run(["git", "-C", d, "config", "user.email", "test@example.com"], check=True)
            subprocess.run(["git", "-C", d, "config", "user.name", "test"], check=True)
            for rel, body in files.items():
                mkfile(os.path.join(d, rel), body)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "commit", "-qm", "base"], check=True)
            base_ref = subprocess.check_output(["git", "-C", d, "rev-parse", "HEAD"], text=True).strip()
            for rel, body in changed.items():
                mkfile(os.path.join(d, rel), body)
            subprocess.run(["git", "-C", d, "add", "-A"], check=True)
            subprocess.run(["git", "-C", d, "commit", "-qm", "change"], check=True)
            for rel in uncommitted:
                mkfile(os.path.join(d, rel), "uncommitted\n")
            baseline = os.path.join(d, "memory/.sprint-autopilot-baseline.json")
            mkfile(baseline, json.dumps({"versions": {"V0.1.0": {
                "builds": [{"build": "V0.1.0_build1001"}]
            }}}))
            proc = subprocess.run([sys.executable, script_path, "--root", d,
                                   "--version", "V0.1.0", "--build", "V0.1.0_build1001",
                                   "--base-ref", base_ref],
                                  capture_output=True, text=True, check=False,
                                  # ⛔ 不写字节码：跑 bundle 副本时会在 assets/ 下落 __pycache__，被 mirror --check 判为漂移
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            with open(baseline, encoding="utf-8") as f:
                record = json.load(f)["versions"]["V0.1.0"]["builds"][0]
            return proc, record

    if not os.path.isfile(bundle_script):
        # 脚手架 bundle 由 aidp-code-engineer skill 维护；未就位时用本体脚本跑同一组断言
        skip("bundle 含分类器与 push 入口", "脚手架 skill 的 assets 未就位，改用本体脚本")
        bundle_script = script
    else:
        check("bundle 含分类器与 push 入口",
              os.path.isfile(os.path.join(os.path.dirname(bundle_script), "classify_commit_change.py")))
    proc, record = run_case({"package.json": "{}\n"}, {"docs/guide.md": "# docs\n"},
                            bundle_script, ["src/Uncommitted.ts"])
    change = record["change_classification"]
    check("bundle docs-only push 写 cicd_skipped=true", proc.returncode == 0
          and record["cicd_skipped"] is True
          and change["changed_files"] == ["docs/guide.md"]
          and change["non_formal_files"] == ["docs/guide.md"])
    check("docs-only 不进入 phase-3-6", classify_push_decision(record) == "skip")
    proc, record = run_case({"package.json": "{}\n", "src/App.ts": "old\n"},
                            {"src/App.ts": "new\n"})
    check("源码 push 进入监听", proc.returncode == 0
          and record["cicd_skipped"] is False
          and classify_push_decision(record) == "watch")
    proc, record = run_case({"package.json": "{}\n", "src/App.ts": "old\n"},
                            {"src/App.ts": "new\n", "docs/guide.md": "# docs\n"}, bundle_script)
    change = record["change_classification"]
    check("源码+文档 mixed push 保留两类文件并监听", proc.returncode == 0
          and record["cicd_skipped"] is False
          and change["formal_code_files"] == ["src/App.ts"]
          and "docs/guide.md" in change["non_formal_files"])
    flow = os.path.join(os.path.dirname(HERE), "../flows/sprint-autopilot/phase-3-6.md")
    with open(flow, encoding="utf-8") as f:
        flow_text = f.read()
    check("phase-3-6 明确跳过分类路径", "cicd_skipped=true" in flow_text and "整段跳过" in flow_text)
    phase_35 = os.path.join(os.path.dirname(HERE), "../flows/sprint-autopilot/phase-3-5.md")
    with open(phase_35, encoding="utf-8") as f:
        phase_35_text = f.read()
    # ★ READY_CFG 不读 baseline（该键全仓只有读、没有写入方，读回恒空 ⇒ Phase 3.2 出口恒落
    #   3.3-audit、整段 3.2.1 被跳过）。改由 tick_flags 读真源：CLOUD_READY_URL ← PRD（按版本取）。
    check("READY_CFG 读真源而非 baseline 空键",
          'READY_CFG="${CLOUD_READY_URL:-}"' in phase_35_text)
    check("★ 不再从 baseline 读那两个无写入方的键（回归防线）",
          "cloud_ready_api_url" not in phase_35_text)



def test_autopilot_flow_contracts():
    """静态回归：逐 tick、空集合 fail-closed、出口 V 围栏与发布监听不可退化。"""
    print("【sprint-autopilot / version release 静态契约】")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(HERE)))
    phase = os.path.join(repo, "flows/sprint-autopilot/phase-3-5.md")
    command = os.path.join(repo, "commands/sprint-autopilot.md")
    release = os.path.join(repo, "flows/version/release-7.md")
    with open(phase, encoding="utf-8") as f:
        p = f.read()
    with open(command, encoding="utf-8") as f:
        c = f.read()
    with open(release, encoding="utf-8") as f:
        r = f.read()
    check("HAS_WAKE_SOURCE 逐 tick 分支有五步执行命令",
          "HAS_WAKE_SOURCE=1" in p
          and "/sprint-start" in p and "/sprint-dev" in p
          and "/sprint-test" in p and "/sprint-bugfix" in p and "/sprint-close" in p)
    # ★ 判据已从「读 baseline 的 sprints.*.last_result + jq .closed==true」改为「close 归档产物存在」：
    #   那两个键（last_result / sprints.remaining）全仓**零写入方**，读它恒得空 → 每 tick 必 exit 1、
    #   游标永不推进。归档文件是 /sprint-close 的既有产物，用它当判据无需引入新写入方。
    check("逐 tick 分支以 close 归档产物为判据并写 run_state",
          "无 close 归档产物" in p and "run-state" in p and "UNATTENDED_YIELD" in p)
    # ★ 失败分支必须记账让位，不得裸 exit 1——裸退时 phase_enter_count 不自增，
    #   stuck 熔断（要求 ≥8）永远达不到阈值，形成零告警零冻结的永久空转。
    check("★ close 失败走记账让位而非裸 exit 1",
          "bump dev_fail_streak" in p and "让位本 tick" in p)
    # ★ 斜杠命令不是 shell 命令，写进 bash 围栏必 127
    check("★ 单 Sprint 执行走子 Agent 委派、不在 bash 围栏内写斜杠命令",
          "/sprint-full ${SPRINT_NO} --unattended --from-batch" in p
          and "\n   /sprint-start " not in p)
    check("★ 不再 get 零写入方的 baseline 键",
          'get "sprints.remaining"' not in p
          and 'get "sprints.$SPRINT_NO.last_result"' not in p)
    # ★ 「计划缺失 / 解析不出 Sprint 时 fail-closed」的实现已下沉到 plan_sprints.py
    #   （它内建 exit 1，且刻意不返回"空集 + exit 0"——空集会被读成「全部已关闭」）。
    #   故此处断言的是**接线正确**：调它 + 非零即退，而不是内联 bash 的那几句文案。
    # ⛔ 判据是 `_PS=$(...) || exit 1` 而不是 `eval "$(...)" || exit 1`：后者里命令替换的退出码
    #   **被 eval 吞掉**（`eval ""` 恒 0），守卫恒不触发 —— 实测 `eval "$(exit 1)" || echo X` 不打印 X。
    #   而 plan_sprints.py fail-closed 时 stdout 一个字节都不打印（诊断走 stderr），于是 REMAIN_COUNT
    #   unset → `[ "$REMAIN_COUNT" -eq 0 ]` 报 integer expression expected → 不进"全部关闭"分支 →
    #   委派一个没有 Sprint 号的 /sprint-full → 3 tick 后按 handoff-exhausted 冻结（人工-only），
    #   冻结原因写"结构性不可自愈"、与真因（计划文件不存在）毫无关系。
    check("★ Sprint 集合走 plan_sprints.py 唯一口径 + 非零即退（⛔ 不得写 eval \"$(...)\" || exit）",
          "plan_sprints.py --version" in p
          and '_PS=$(python3 {{AIDP_HOME}}/scripts/plan_sprints.py' in p
          and 'eval "$(python3 {{AIDP_HOME}}/scripts/plan_sprints.py' not in p)
    check("★ eval 后强制回读 REMAIN_COUNT（fail-closed 静默时兜底）",
          'REMAIN_COUNT:?plan_sprints fail-closed' in p)
    # ⚠️ 只看**可执行行**：文件里那条「⛔ 别改回 …」的警示注释本身就含这两个字样，
    #   连注释一起扫会把警示语判成回归（写警示反而触发告警）。
    _exec_lines = "\n".join(ln for ln in p.split("\n") if not ln.strip().startswith("#"))
    check("★ 不得回退到只取一份计划的 `-print -quit` / 硬编码 `01_研发执行计划.md`",
          "-print -quit" not in _exec_lines and "01_研发执行计划.md" not in _exec_lines)
    check("未关闭集合为空才判 done（REMAIN_COUNT 来自计划↔归档差集）",
          "全部 Sprint 已关闭" in p and '[ "$REMAIN_COUNT" -eq 0 ]' in p)
    # ★ 该分支的 exit 0 是全仓唯一「只结束本围栏、不让位本 tick」的用法，必须就地写明；
    #   被读成"让位本 tick"会让最后一个 Sprint 关闭的那个 tick 直接退出、部署段永不执行。
    check("★ 全部关闭分支的 exit 0 语义须显式区别于「让位本 tick」",
          "不退本 tick" in p)
    # ★ 游标为空必须显式 fail：`printf '%s\n' "${arr[@]}"` 在空数组上输出一个空行，
    #   `grep -qx ""` 恰好命中 → 「一个都没关闭 + 游标丢失」这个最坏组合反被判成功。
    check("★ 游标为空显式 fail（不落进空模式匹配空行的假成功）",
          'if [ -z "$SPRINT_NO" ]; then' in p and "游标丢失" in p)
    check("phase-3-5 出口 eval 后强制回读非空 TARGET_VERSION",
          'V="${TARGET_VERSION:?TARGET_VERSION 未由 tick flags 提供}"' in p)
    check("READY_CFG 取自 tick_flags 的真源派生变量（不读 baseline 空键）",
          'READY_CFG="${CLOUD_READY_URL:-}"' in p)
    check("裸探路与执行入口行为已统一",
          "裸探路调用默认只跑配置向导" in c
          and "明确执行意图" in c and "--once" in c)
    check("发布期 docs-only 跳过 CICD",
          "docs-only" in r and "不触发 CICD、不监听、不跑就绪探针" in r)


def classify_push_decision(record):
    return "skip" if record.get("cicd_skipped") is True and not record.get("classification_error") else "watch"



def test_ledger_forms():
    """静默洞：`### C-NNN` 台账形态永不 stale；无日期条目；🔴 未登记失准点。"""
    print("【台账形态 stale + 破坏性变更登记】")
    root = tempfile.mkdtemp()
    led = os.path.join(root, "docs/requirements/V0.1.0/研发需求/_开发期需求增量.md")
    # `### C-NNN` 形态 + 一个明显过期的日期
    mkfile(led, "# 台账\n\n## 待级联\n\n### C-001 · 01-02 10:00 · 导出去掉 XLSX\n"
                "\n### C-002 · 01-03 11:00 · 列表加筛选\n")
    r = G.pending_cascade(root)
    check("★ `### C-NNN` 形态被计入 total", r["total"] == 2)
    check("★ `### C-NNN` 形态会 stale（原先对 stale 零贡献 → 整份台账永久静默）",
          r["stale"] == 2)

    # 无日期条目 = fail-closed 计 stale（否则等于给出一个「写了就永不到期」的形态）
    led2 = os.path.join(root, "docs/requirements/V0.2.0/研发需求/_开发期需求增量.md")
    mkfile(led2, "# 台账\n\n## 待级联\n\n### C-009 · 导出改动（忘了写日期）\n")
    r2 = G.pending_cascade(root)
    v2 = r2["versions"]["V0.2.0"]
    check("★ 无日期条目按 fail-closed 计 stale", v2["total"] == 1 and v2["stale"] == 1)

    # 🔴 破坏性变更未登记「已知失准点」——机制自述这是**唯一的风险敞口**、失准点段是
    # **唯一的缓解手段**，而它此前是纯散文（全仓 .py 对「已知失准点」零命中）。
    led3 = os.path.join(root, "docs/requirements/V0.3.0/研发需求/_开发期需求增量.md")
    mkfile(led3, "# 台账\n\n## ⚠️ 已知失准点\n\n- 🔴 C-001：详设 §4.2 仍含已删的 XLSX\n"
                 "\n## 待级联\n\n- C-001 · 01-02 10:00 · 🔴 导出去掉 XLSX · sprint-1\n"
                 "- C-002 · 01-02 10:05 · 🔴 推翻退款规则 · sprint-1\n")
    r3 = G.pending_cascade(root)
    ids = {d["id"] for d in (r3.get("destructive_unregistered") or [])}
    check("★ 已登记的 🔴 条目不报（C-001 在失准点段）", "C-001" not in ids)
    check("★ 未登记的 🔴 条目被报出（C-002 只在待级联）", "C-002" in ids)

    import shutil
    shutil.rmtree(root, ignore_errors=True)


def main():
    test_gate_pure()
    test_gate_cli_cascade()
    test_family_ledgers()
    test_cascade_bypass()
    test_offchain()
    test_pending_cicd()
    test_ledger_forms()
    test_classify_commit_change()
    test_classify_push_flow()
    test_autopilot_flow_contracts()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed / {_skipped} skipped ══")
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
