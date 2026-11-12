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
import unittest
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
        skill_base = G.SCAFFOLD_SKILL_ROOTS[0]
        mkfile(os.path.join(d, skill_base, "SKILL.md"))
        check("只有 SKILL.md、缺同步脚本 → 非模板项目", G.is_template_project(d) is False)
        mkfile(os.path.join(d, skill_base, "scripts/sync_memory_md.py"))
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
              "memory/.sprint-autopilot-baseline.json",
              "skills/aidp-code-engineer/scripts/scaffold.py"):
        check(f"_is_scaffold_contract {p} → 是", C(p) is True)
    for p in ("code/backend/A.java", "docs/design/detail/V0.1.0/01_详细设计.md", "README.md",
              "skills/biz-skill/run.py"):
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
                  "pending_cascade", "cascaded_not_cleaned",
                  "suspected_cascade_bypass", "pending_cicd", "offchain", "context", "debts",
                  "path_scope", "id_allocation", "execution_context", "cache"}
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
        check("★ stale 仍保留在 pending_cascade 供阶段收口消费，提交门不再派单",
              cp.returncode == 0 and "cascade-stale" not in info.get("debts", []) and not cp.stderr.strip())

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
              info["pending_cascade"].get("stale") == 0 and cp.returncode == 0)

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
              info["pending_cascade"].get("total") == 0 and cp.returncode == 0)

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
        _init_repo(d)
        _git(d, "commit", "--allow-empty", "-qm", "base")
        b = G.offchain_budget(d, "bare-conversation", " M code/a.vue\n M code/b.ts\n")
        check("XS：≤2 代码文件", b["risk_tier"] == "S" and b["cost"]["band"] == "XS" and b["deploy"] is False and b["applies"] is True)
        b = G.offchain_budget(d, "aidp-command", " M code/a.ts\n M code/b.ts\n M code/c.ts\n")
        check("S：≤5 文件；aidp-command 下 applies=False", b["tier"] == "S" and b["applies"] is False)
        mkfile(os.path.join(d, "code/sql/1.sql"), "ALTER TABLE t ADD COLUMN c INT;\n")
        b = G.offchain_budget(d, "bare-conversation", " M code/sql/1.sql\n")
        check("M：ALTER DDL", b["tier"] == "M" and b["ddl"] == "alter" and b["deploy"] is False and not b["actions"]["sprint_archive"])
        mkfile(os.path.join(d, "code/sql/2.sql"), "CREATE TABLE t (id INT);\n")
        b = G.offchain_budget(d, "bare-conversation", " A code/sql/2.sql\n")
        check("L：新表", b["tier"] == "L" and b["ddl"] == "new-table")
        check("恒定禁止项含铸 build 与浏览器实测", {"铸 build", "浏览器实测"} <= set(b["forbidden"]))
        check("档位只是下限（须语义自判）", b["tier_floor_only"] is True)


# ── 约定 31.5：CICD 推送欠账 ──
def test_classify_conservative_and_readonly():
    """子模块 / 嵌套仓 / 配置类文件保守判 formal；--head；空 base-ref；全程只读（git status 无变化）。"""
    print("【classify 保守分类 + 只读验收】")
    CC = os.path.join(SCRIPTS, "classify_commit_change.py")
    CPUSH = os.path.join(SCRIPTS, "classify_push.py")

    def run(script, d, *a):
        cp = subprocess.run([sys.executable, script, "--root", d, *a], capture_output=True, text=True)
        return json.loads(cp.stdout or "{}"), cp.returncode

    def porcelain(d):
        return _git(d, "status", "--porcelain").stdout

    with tempfile.TemporaryDirectory() as d:
        _init_repo(d)
        mkfile(os.path.join(d, "package.json"), "{}\n")
        mkfile(os.path.join(d, "src/App.ts"), "export {}\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "base")
        base = _git(d, "rev-parse", "HEAD").stdout.strip()
        # gitlink：不联网，直接 update-index 构造 160000 条目
        _git(d, "update-index", "--add", "--cacheinfo", "160000," + base + ",libs/shared")
        _git(d, "commit", "-qm", "bump submodule")
        r, _ = run(CC, d, "--base-ref", base)
        check("子模块指针（gitlink）变更 → 保守 formal", r["has_formal_code_change"] is True
              and "libs/shared" in r["formal_code_files"] and "libs/shared" in r["conservative_files"])
        pr, rc = run(CPUSH, d, "--base-ref", base, "--head", "HEAD")
        check("classify_push：gitlink → watch", rc == 0 and pr["decision"] == "watch")
        # --head：不带 base 时取该提交相对父提交的变更
        r, _ = run(CC, d, "--head", "HEAD")
        check("--head 单独给出 → 以其父提交为基线", r["changed_files"] == ["libs/shared"])
        r, _ = run(CC, d, "--head", base)
        check("--head 指向根提交 → 相对空树", "package.json" in r["changed_files"] and not r["classification_error"])
        check("--base-ref \"\" 按未提供处理（工作区口径）", run(CC, d, "--base-ref", "")[0] == run(CC, d)[0])
        # 配置类文件与实际部署 SQL → 保守 formal；说明文档继续跳过
        mkfile(os.path.join(d, "src/main/resources/application.yml"), "a: 1\n")
        mkfile(os.path.join(d, "src/main/resources/db/init.sql"), "select 1;\n")
        mkfile(os.path.join(d, "docs/deployment/v1/a.sql"), "select 1;\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "config")
        r, _ = run(CC, d, "--head", "HEAD")
        check("源码配置与部署 SQL → 保守 formal",
              {"src/main/resources/application.yml", "src/main/resources/db/init.sql",
               "docs/deployment/v1/a.sql"} <= set(r["formal_code_files"]))
        assets_base = _git(d, "rev-parse", "HEAD").stdout.strip()
        mkfile(os.path.join(d, "docs/deployment/v1/配置文件/全量/application-prod.yaml"), "port: 9000\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "deployment config")
        before = porcelain(d)
        pr, rc = run(CPUSH, d, "--base-ref", assets_base, "--head", "HEAD")
        check("仅部署配置变更 → 只读 watch", rc == 0 and pr["decision"] == "watch" and not pr["error"]
              and before == porcelain(d))
        # 嵌套 .git 子仓（未登记）：其目录下任何改动保守 formal
        sub = os.path.join(d, "vendor_repo")
        os.makedirs(sub)
        subprocess.run(["git", "init", "-q", sub], check=True, capture_output=True)
        mkfile(os.path.join(sub, "README.md"), "# nested\n")
        r, _ = run(CC, d)
        check("嵌套 .git 子仓（工作区）→ 保守 formal", "vendor_repo" in r["formal_code_files"]
              and "vendor_repo" in r["conservative_files"])
        shutil_rm = __import__("shutil").rmtree
        shutil_rm(sub)
        # 只读验收：前后 git status 不变、不产生 baseline
        mkfile(os.path.join(d, "docs/x.md"), "# x\n")
        before = porcelain(d)
        run(CPUSH, d, "--base-ref", base)
        run(CC, d)
        check("★ classify_push / classify_commit_change 不改变 git status、不生成 baseline",
              porcelain(d) == before and not os.path.exists(os.path.join(d, "memory/.sprint-autopilot-baseline.json")))


def test_plain_flow_leaves_tree_untouched():
    """未启用 CICD 的仓库：提交→推送→(部署) 前后脚本不留任何改动；commit_gate 无 execution-context 也不拒绝。"""
    print("【验收：提交/推送不被脚手架脚本改动工作区】")
    with tempfile.TemporaryDirectory() as base:
        remote = os.path.join(base, "remote.git")
        d = os.path.join(base, "work")
        subprocess.run(["git", "init", "-q", "--bare", remote], capture_output=True)
        os.makedirs(d)
        _init_repo(d)
        mkfile(os.path.join(d, "package.json"), "{}\n")
        mkfile(os.path.join(d, "src/App.ts"), "export {}\n")
        mkfile(os.path.join(d, ".gitignore"), "memory/.aidp/\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "init")
        _git(d, "remote", "add", "origin", remote)
        _git(d, "checkout", "-q", "-B", "main")
        _git(d, "push", "-q", "-u", "origin", "main")
        mkfile(os.path.join(d, "src/App.ts"), "export const a = 1\n")
        _git(d, "add", "-A")
        cp, info = _run_gate(d, "--quiet")
        check("★ commit_gate 无 --execution-context：不拒绝（退出码 0，非 5）", cp.returncode == 0 and "NOT_AUTHORIZED" not in cp.stdout)
        check("未启用 CICD → pending_cicd 不检查", info["pending_cicd"]["applicable"] is False
              and info["pending_cicd"]["pending"] is False)
        _git(d, "commit", "-qm", "feat: a")
        after_commit_gate = _git(d, "status", "--porcelain").stdout
        cp2, _ = _run_gate(d, "--quiet")
        classify = subprocess.run([sys.executable, os.path.join(SCRIPTS, "classify_push.py"), "--root", d,
                                   "--base-ref", "origin/main"], capture_output=True, text=True)
        enabled = subprocess.run([sys.executable, os.path.join(SCRIPTS, "aidp_config.py"), "--root", d,
                                  "cicd-enabled", "--json"], capture_output=True, text=True)
        _git(d, "push", "-q", "origin", "main")
        cp3, _ = _run_gate(d, "--quiet")
        check("cicd-enabled：未启用 → 退出 1 且 {enabled:false}", enabled.returncode == 1
              and json.loads(enabled.stdout)["enabled"] is False)
        check("推送后 commit_gate 仍通过", cp2.returncode == 0 and cp3.returncode == 0 and classify.returncode == 0)
        check("★ 提交→推送→门禁→分类 全程 git status 无脚本造成的改动",
              _git(d, "status", "--porcelain").stdout == after_commit_gate == "")
        check("baseline 文件不随推送新增记录", not os.path.exists(os.path.join(d, "memory/.sprint-autopilot-baseline.json")))


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
        mkfile(os.path.join(d, ".aidp/scripts/vcs.py"),
               open(os.path.join(SCRIPTS, "vcs.py"), encoding="utf-8").read())
        mkfile(os.path.join(d, "package.json"), "{}\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "init")
        _git(d, "remote", "add", "origin", remote)
        _git(d, "checkout", "-q", "-B", "main")
        _git(d, "push", "-q", "-u", "origin", "main")
        mkfile(os.path.join(d, "memory/aidp-config.yaml"), "cicd:\n  provider: none\n")
        check("cicd.provider=none → 不检查、无欠账", G.pending_cicd(d)["applicable"] is False
              and G.pending_cicd(d)["pending"] is False)
        os.remove(os.path.join(d, "memory/aidp-config.yaml"))
        check("未配置流水线 → 未启用：不检查、不制造欠账", G.pending_cicd(d)["applicable"] is False
              and G.pending_cicd(d)["pending"] is False and G.pending_cicd(d)["advisory"] is False)
        mkfile(os.path.join(d, "memory/aidp-config.yaml"), "cicd:\n  pipelines: {test: deploy-test.yml}\n")
        check("★ 已启用 + HEAD 已推送 → 适用", G.pending_cicd(d)["applicable"] is True)
        mkfile(os.path.join(d, "docs/note.md"), "# n\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "docs: note"); _git(d, "push", "-q", "origin", "main")
        check("HEAD 无正式代码变更 → 无提示", G.pending_cicd(d)["advisory"] is False)

        mkfile(os.path.join(d, "src/App.ts"), "export {}\n")
        _git(d, "add", "-A"); _git(d, "commit", "-qm", "feat: app")
        _git(d, "push", "-q", "origin", "main")
        head = _git(d, "rev-parse", "HEAD").stdout.strip()
        r = G.pending_cicd(d)
        check("★ 已启用：推送正式代码 → 仅 advisory 提示（现场 git 取得 commit），永不计债",
              r["advisory"] is True and r["pending"] is False and r["commit"] == head)
        bl = os.path.join(d, "memory/.sprint-autopilot-baseline.json")
        mkfile(bl, json.dumps({"versions": {"V0.1.0": {"standalone_pushes": [
            {"commit": head, "formal_code_change": True, "cicd_skipped": False}]}}}))
        check("★ 不读 baseline：任何历史记录都不改变结果", G.pending_cicd(d) == r)
        check("advisory 不进入欠账清单", "cicd-push-pending" not in G.debt_items({"pending_cicd": r}))


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
    check("部署 SQL → 触发监听", r["has_formal_code_change"] is True
          and r["cicd_should_watch"] is True)
    for asset in ("docs/deployment/V1/config/application-prod.yaml",
                  "docs/deployment/V1/配置文件/全量/.env",
                  "docs/deployment/V1/配置文件/全量/app.json"):
        r = classify([asset])
        check("部署实际配置触发：" + asset, r["has_formal_code_change"] and r["cicd_should_watch"]
              and asset in r["conservative_files"])
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
                     "classification_error", "source_roots", "conservative_files"})
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
        "source_roots": [], "conservative_files": [],
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
    script = os.path.join(os.path.dirname(HERE), "classify_push.py")
    bundle_script = os.path.join(os.path.dirname(HERE),
                                 "../../skills/aidp-code-engineer/assets/aidp/scripts/classify_push.py")

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
            before = subprocess.check_output(["git", "-C", d, "status", "--porcelain"], text=True)
            proc = subprocess.run([sys.executable, script_path, "--root", d, "--base-ref", base_ref],
                                  capture_output=True, text=True, check=False,
                                  # ⛔ 不写字节码：跑 bundle 副本时会在 assets/ 下落 __pycache__，被 mirror --check 判为漂移
                                  env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
            after = subprocess.check_output(["git", "-C", d, "status", "--porcelain"], text=True)
            check("classify_push 只读：git status 前后一致、不产生 baseline", before == after
                  and not os.path.exists(os.path.join(d, "memory/.sprint-autopilot-baseline.json")))
            record = json.loads(proc.stdout or "{}")
            return proc, record

    if not os.path.isfile(bundle_script):
        # 脚手架 bundle 由 aidp-code-engineer skill 维护；未就位时用本体脚本跑同一组断言
        skip("bundle 含分类器与 push 入口", "脚手架 skill 的 assets 未就位，改用本体脚本")
    else:
        check("bundle 含分类器与 push 入口",
              os.path.isfile(os.path.join(os.path.dirname(bundle_script), "classify_commit_change.py")))
    # bundle 由 mirror_to_bundle.py 派生（可能滞后于本体）；行为断言只跑本体，镜像一致性由 mirror --check 保证。
    bundle_script = script
    proc, record = run_case({"package.json": "{}\n"}, {"docs/guide.md": "# docs\n"},
                            bundle_script, ["src/Uncommitted.ts"])
    check("bundle docs-only push → skip（只读）", proc.returncode == 0
          and record["decision"] == "skip" and record["error"] is False
          and record["paths"]["changed_files"] == ["docs/guide.md"]
          and record["paths"]["non_formal_files"] == ["docs/guide.md"])
    proc, record = run_case({"package.json": "{}\n", "src/App.ts": "old\n"},
                            {"src/App.ts": "new\n"})
    check("源码 push → watch", proc.returncode == 0 and record["decision"] == "watch")
    proc, record = run_case({"package.json": "{}\n", "src/App.ts": "old\n"},
                            {"src/App.ts": "new\n", "docs/guide.md": "# docs\n"}, bundle_script)
    check("源码+文档 mixed push 保留两类文件并 watch", proc.returncode == 0
          and record["decision"] == "watch"
          and record["paths"]["formal_code_files"] == ["src/App.ts"]
          and "docs/guide.md" in record["paths"]["non_formal_files"])
    with tempfile.TemporaryDirectory() as gd:
        subprocess.run(["git", "init", "-q", gd], check=True, capture_output=True)
        bad = subprocess.run([sys.executable, script, "--root", gd, "--base-ref", "no-such-ref-xyz"],
                             capture_output=True, text=True, check=False)
    check("★ 基线 ref 无效 → fail-closed：watch + error=true，退出码 0",
          bad.returncode == 0 and json.loads(bad.stdout)["decision"] == "watch"
          and json.loads(bad.stdout)["error"] is True)
    old = subprocess.run([sys.executable, script, "--root", ".", "--version", "V1", "--standalone"],
                         capture_output=True, text=True, check=False)
    check("旧落盘参数（--version/--standalone/--record-terminal）已删除 → 拒绝", old.returncode == 2)
    flow = os.path.join(os.path.dirname(HERE), "../flows/sprint-autopilot/phase-3-6.md")
    with open(flow, encoding="utf-8") as f:
        flow_text = f.read()
    check("phase-3-6 明确跳过分类路径", ("cicd_skipped=true" in flow_text or "decision" in flow_text or "skip" in flow_text)
          and "整段跳过" in flow_text)
    phase_35 = os.path.join(os.path.dirname(HERE), "../flows/sprint-autopilot/phase-3-5.md")
    with open(phase_35, encoding="utf-8") as f:
        phase_35_text = f.read()
    # ★ READY_CFG 不读 baseline（该键全仓只有读、没有写入方，读回恒空 ⇒ Phase 3.2 出口恒落
    #   3.3-audit、整段 3.2.1 被跳过）。改由 tick_flags 读真源：CLOUD_READY_URL ← PRD（按版本取）。
    check("READY_CFG 读真源而非 baseline 空键",
          'READY_CFG="${CLOUD_READY_URL:-}"' in phase_35_text)
    check("★ 不再从 baseline 读那两个无写入方的键（回归防线）",
          "cloud_ready_api_url" not in phase_35_text)



def test_standalone_release_pending_base():
    """发布推送：基线取远端已有提交（无远端 → 缺基准），只读分类；缺基准保守监听。"""
    print("【独立发布：远端待推基准的只读分类】")
    for formal in (True, False, None):
        with tempfile.TemporaryDirectory() as tmp:
            root, remote = os.path.join(tmp, "work"), os.path.join(tmp, "remote.git")
            os.makedirs(root)
            _init_repo(root)
            subprocess.run(["git", "init", "--bare", "-q", remote], check=True, capture_output=True)
            mkfile(os.path.join(root, "package.json"), '{}\n')
            mkfile(os.path.join(root, "src/app.ts"), "export const value = 1;\n")
            _git(root, "add", "."); _git(root, "commit", "-qm", "base")
            branch = _git(root, "symbolic-ref", "--short", "HEAD").stdout.strip()
            _git(root, "remote", "add", "origin", remote)
            _git(root, "push", "-u", "origin", branch)
            changed = "src/app.ts" if formal else "docs/change.md"
            mkfile(os.path.join(root, changed), "export const value = 2;\n" if formal else "# docs\n")
            _git(root, "add", "."); _git(root, "commit", "-qm", "pending change")
            base = _git(root, "rev-parse", "@{u}").stdout.strip()
            if formal is None:
                base = ""   # 缺基准
            mkfile(os.path.join(root, "docs/release.md"), "# release\n")
            _git(root, "add", "docs/release.md"); _git(root, "commit", "-qm", "release docs")
            r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "classify_push.py"), "--root", root,
                                "--base-ref", base], capture_output=True, text=True)
            out = json.loads(r.stdout)
            # 空串 base 按未提供处理 → 工作区口径（干净）→ skip；缺基准的保守监听由调用方（缺 base 即 watch）负责，
            # 这里只验证已知基准时覆盖「早已提交但尚未推送」的正式代码。
            check(f"待推区间只读分类（formal={formal}）", r.returncode == 0
                  and (out["decision"] == "watch") is bool(formal))
            check(f"分类不落盘（formal={formal}）",
                  not os.path.exists(os.path.join(root, "memory/.sprint-autopilot-baseline.json")))


def test_autopilot_flow_contracts():
    """静态回归：逐 tick、空集合 fail-closed、出口 V 围栏与发布监听不可退化。"""
    print("【sprint-autopilot / version release 静态契约】")
    repo = os.path.dirname(os.path.dirname(os.path.abspath(HERE)))
    phase = os.path.join(repo, "flows/sprint-autopilot/phase-3-5.md")
    command = os.path.join(repo, "commands/sprint-autopilot.md")
    release = os.path.join(repo, "flows/version/release-7.md")
    poll_flow = os.path.join(repo, "flows/sprint-autopilot/phase-3-6b.md")
    with open(poll_flow, encoding="utf-8") as f:
        poll_text = f.read()
    check("Step C 从本 build 的 push_commit 读取轮询预期 SHA",
          'get push_commit --default ""' in poll_text and '--commit "$GIT_PUSH_COMMIT"' in poll_text)
    check("Step C 不以轮询返回的 RUN_COMMIT 覆盖基线",
          'set cicd_run.run_commit "$RUN_COMMIT"' not in poll_text)
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
    # 记账口径 = autopilot_fail_handle（bump → 判阈 → 冻结四件套 + #4 一次做完、逐个查写盘返回码）
    check("★ close 失败走记账让位而非裸 exit 1",
          "autopilot_fail_handle.py" in p and "--streak-key dev_fail_streak" in p and "让位本 tick" in p)
    check("★ close 失败的达阈冻结不再内联 `$BE set needs_human`（不查返回码）",
          "set needs_human true" not in p)
    check("★ 派发子 Agent 前先写 run-state --enter（被硬超时杀掉也计入 stuck 判据）",
          p.index("--enter") < p.index("**② 委派子 Agent"))
    # ★ 斜杠命令不是 shell 命令，写进 bash 围栏必 127
    check("★ 单 Sprint 执行走子 Agent 委派、不在 bash 围栏内写斜杠命令",
          "/sprint-full ${SPRINT_NO}" in p and "--execution-context" in p
          and "--unattended --from-batch" in p
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
          "裸探路调用仅配置向导" in c
          and "明确执行意图" in c and "--once" in c
          and "自然语言只取得明确请求的动作" in c
          and "存在baseline不扩权" in c)
    check("发布期 docs-only 跳过 CICD",
          "docs-only" in r and "不触发 CICD、不监听、不跑就绪探针" in r)



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


def test_non_git_boundaries():
    print("【非 Git 根：提交、推送、diff、CICD SHA 与工作区门禁】")
    with tempfile.TemporaryDirectory() as d:
        scripts = [
            ("commit", "commit_gate.py", ["--repo-root", d, "--quiet"]),
            ("diff", "classify_commit_change.py", ["--root", d, "--json"]),
            ("diff", "classify_commit_change.py", ["--root", d, "--base-ref", "HEAD", "--json", "src/main.py"]),
            ("push", "classify_push.py", ["--root", d]),
            ("push", "classify_push.py", ["--root", d, "--base-ref", "HEAD", "--head", "HEAD"]),
            ("index", "check_index_staleness.py", ["--root", d, "--json"]),
            ("cicd-sha", "cicd_watch.py", ["--root", d, "--mode", "detect", "--commit", "abc"]),
            ("branch", "autopilot-preflight.py", ["gate", "--root", d, "--require", "clean_tree", "--json"]),
            ("branch", "autopilot-preflight.py", ["gate", "--root", d, "--require", "notify, clean_tree", "--json"]),
        ]
        for capability, script, args in scripts:
            cp = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                                capture_output=True, text=True)
            try:
                result = json.loads(cp.stdout.strip().split("---JSON---")[-1])
            except ValueError:
                result = {}
            check(f"{script} nonGit 拒绝 {capability}",
                  cp.returncode == 3 and result.get("status") == "unsupported"
                  and result.get("reason") == "vcs-disabled"
                  and result.get("capability") == capability)
        check("推送分类不能写入 baseline", not os.path.exists(os.path.join(d, "memory")))


def test_staged_path_allowlist():
    print("【暂存区路径白名单】")
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d)
        mkfile(os.path.join(d, "src/allowed.py"))
        mkfile(os.path.join(d, "views/页面 空格.js"))
        _git(d, "add", ".")
        _git(d, "commit", "-qm", "fixture")
        mkfile(os.path.join(d, "src/allowed.py"), "changed\n")
        mkfile(os.path.join(d, "views/页面 空格.js"), "changed\n")
        _git(d, "add", "src/allowed.py")
        cp, data = _run_gate(d, "--quiet", "--allow-path", "src/**", "--owner", "backend")
        check("只核对暂存区，其他Agent未暂存改动不误报",
              cp.returncode == 0 and data.get("path_scope", {}).get("outside") == [])
        _git(d, "add", "views/页面 空格.js")
        cp, data = _run_gate(d, "--quiet", "--allow-path", "src/**", "--owner", "backend")
        check("白名单外路径含中文空格也正确WARN且quiet不可隐藏",
              data.get("path_scope", {}).get("outside") == ["views/页面 空格.js"]
              and "WARN" in cp.stderr and cp.returncode == 0)
        cp, data = _run_gate(d, "--quiet", "--allow-path", "src/**", "--allow-path", "views/**")
        check("编排者汇合白名单可包含双方路径", data.get("path_scope", {}).get("outside") == [])
        _git(d, "reset", "--hard", "HEAD")
        _git(d, "mv", "views/页面 空格.js", "src/moved.js")
        cp, data = _run_gate(d, "--quiet", "--allow-path", "src/**")
        check("移动必须检查原路径删除权限", "views/页面 空格.js" in data.get("path_scope", {}).get("outside", []))
        cp, data = _run_gate(d, "--quiet")
        check("未声明白名单不冒充已核验", data.get("path_scope", {}).get("applicable") is False)
        cp, _ = _run_gate(d, "--allow-path", "../**")
        check("白名单不能越出仓库", cp.returncode == 2)


def test_id_allocation_gate():
    print("【编号账本提交检查】")
    from alloc_id import allocate
    from aidp_paths import id_alloc_ledger
    with tempfile.TemporaryDirectory() as d:
        _init_repo(d)
        allocate(d, "BUG", 2, "worker", version="V1.0.0")
        cp, info = _run_gate(d, "--quiet")
        check("预留未使用空洞不报欠账", cp.returncode == 0 and info.get("id_allocation", {}).get("passed"))
        with open(id_alloc_ledger(d), "a", encoding="utf-8") as stream:
            stream.write("truncated\n")
        cp, info = _run_gate(d, "--quiet")
        check("损坏账本作为可见欠账，不吞掉quiet告警", cp.returncode == 3
              and "id-allocation-invalid" in info.get("debts", []) and "编号" in cp.stderr)


class IncrementalGateTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory(prefix='aidp-gate-cache-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        _init_repo(str(self.root))
        mkfile(str(self.root / '.gitignore'), 'memory/.aidp/\n')
        mkfile(str(self.root / 'app.py'), 'value = 1\n')
        mkfile(str(self.root / 'memory/aidp-config.yaml'), 'cicd:\n  provider: none\n')
        _git(str(self.root), 'add', '.')
        _git(str(self.root), 'commit', '-qm', 'base')

    def context(self):
        import entry_context as entry
        return entry.resolve_context(self.root, 'sprint-dev', version='V1', write_set=['app.py'],
            additional_grants=['commit'], authorization_source={
                'kind': 'user-text', 'request_id': 'gate-user', 'text': '开发并提交'})

    def test_fingerprint_phase_reads_mount_metadata_once_and_refreshes_next_phase(self):
        from unittest import mock
        import project_inventory as inventory
        paths = [self.root / 'app.py', self.root / 'memory/aidp-config.yaml']
        cache = G._GateCache(self.root)
        with mock.patch.object(inventory, 'fingerprint_metadata', wraps=inventory.fingerprint_metadata) as metadata:
            before = cache.fingerprints(paths)
            self.assertEqual(metadata.call_count, 1)
            after = cache.fingerprints(paths)
            self.assertEqual(metadata.call_count, 2)
            self.assertEqual(before, after)
        # 元数据不可用时也只尝试一次，传空映射让各文件保守重读内容。
        reads = cache.stats['content_reads']
        with mock.patch.object(inventory, 'fingerprint_metadata', return_value=None) as metadata:
            fallback = cache.fingerprints(paths)
            self.assertEqual(metadata.call_count, 1)
        self.assertEqual(fallback, before)
        self.assertEqual(cache.stats['content_reads'], reads + len(paths))

    def test_development_gate_defaults_to_related_tests_and_respects_explicit_skip(self):
        import entry_context as entry
        (self.root / 'app.py').write_text('value = 2\n')
        default = G.offchain_budget(str(self.root), 'bare-conversation', ' M app.py\n')
        self.assertTrue(default['actions']['unit_test'])
        self.assertIn('full-regression', default['not_requested'])
        self.assertFalse(default['deploy'])
        limited = entry.resolve_context(self.root, 'sprint-dev', version='V1', write_set=['app.py'],
            authorization_source={'kind':'user-text', 'request_id':'skip-unit-explicit',
                                  'text':'本次修改跳过单测', 'skip_actions':['related-test']})
        facts = G.gather(str(self.root), execution_context=limited['execution_context'])
        self.assertFalse(facts['offchain']['actions']['unit_test'])
        self.assertFalse(facts['offchain']['deploy'])

    def test_same_inputs_skip_checkers_and_content_reads(self):
        from unittest import mock
        import development_scope
        (self.root / 'app.py').write_text('value = 2\n')
        with mock.patch.object(G, 'pending_cascade', wraps=G.pending_cascade) as cascade, \
             mock.patch.object(G, 'pending_cicd', wraps=G.pending_cicd) as cicd, \
             mock.patch.object(development_scope, 'analyze_changes', wraps=development_scope.analyze_changes) as analyze:
            first = G.gather(str(self.root))
            before = (cascade.call_count, cicd.call_count, analyze.call_count)
            second = G.gather(str(self.root))
            self.assertEqual(before, (cascade.call_count, cicd.call_count, analyze.call_count))
        self.assertGreater(first['cache']['content_reads'], 0)
        self.assertEqual(second['cache']['content_reads'], 0)
        self.assertTrue(all(item['hit'] for item in second['cache']['checks'].values()))

    def test_cli_reuses_persisted_checks_across_processes(self):
        first_process, first = _run_gate(str(self.root), '--quiet')
        second_process, second = _run_gate(str(self.root), '--quiet')
        self.assertEqual(first_process.returncode, 0, first_process.stdout + first_process.stderr)
        self.assertEqual(second_process.returncode, 0, second_process.stdout + second_process.stderr)
        self.assertGreater(first['cache']['content_reads'], 0)
        self.assertEqual(second['cache']['content_reads'], 0)
        self.assertTrue(all(row['hit'] for row in second['cache']['checks'].values()))
        self.assertTrue(all(row['checker_elapsed_seconds'] == 0 for row in second['cache']['checks'].values()))

    def test_same_mtime_content_change_and_config_change_invalidate_only_dependents(self):
        (self.root / 'app.py').write_text('value = 2\n')
        G.gather(str(self.root))
        info = (self.root / 'app.py').stat()
        (self.root / 'app.py').write_text('value = 3\n')
        os.utime(self.root / 'app.py', ns=(info.st_atime_ns, info.st_mtime_ns))
        changed = G.gather(str(self.root))
        self.assertFalse(changed['cache']['checks']['offchain']['hit'])
        self.assertTrue(changed['cache']['checks']['pending_cascade']['hit'])
        config = self.root / 'memory/aidp-config.yaml'
        config.write_text('cicd:\n  provider: none\ncommit_gate:\n  enabled: false\n')
        changed = G.gather(str(self.root))
        self.assertFalse(changed['commit_gate_enabled'])
        self.assertFalse(changed['cache']['checks']['config']['hit'])
        self.assertTrue(changed['cache']['checks']['pending_cascade']['hit'])
        self.assertTrue(changed['cache']['checks']['offchain']['hit'])

    def test_head_change_does_not_invalidate_unrelated_checkers(self):
        G.gather(str(self.root))
        _git(str(self.root), 'commit', '--allow-empty', '-qm', 'metadata-only head')
        result = G.gather(str(self.root))
        for name in ('config', 'template', 'pending_cascade', 'id_allocation'):
            self.assertTrue(result['cache']['checks'][name]['hit'], name)

    def test_authorization_revision_refreshes_live_actions_without_rechecking_code(self):
        from unittest import mock
        import entry_context as entry
        import development_scope
        first = self.context()
        (self.root / 'app.py').write_text('value = 2\n')
        with mock.patch.object(development_scope, 'analyze_changes', wraps=development_scope.analyze_changes) as analyze:
            G.gather(str(self.root), execution_context=first['execution_context'])
            before = analyze.call_count
            revised = entry.revise_context(self.root, first['execution_context'], additional_grants=['deploy'],
                authorization_source={'kind': 'user-text', 'request_id': 'deploy-grant', 'text': '也允许部署'})
            data = G.gather(str(self.root), execution_context=revised['execution_context'])
            self.assertEqual(analyze.call_count, before)
            self.assertTrue(data['offchain']['deploy'])
        with self.assertRaises(ValueError):
            G.gather(str(self.root), execution_context=first['context'])
        plain = entry.resolve_context(self.root, 'sprint-dev', version='V1', write_set=['app.py'])
        readonly = G.gather(str(self.root), execution_context=plain['execution_context'])
        self.assertIn('commit', readonly['offchain']['not_requested'])
        process, denied = _run_gate(str(self.root), '--execution-context', plain['execution_context'], '--quiet')
        self.assertEqual(process.returncode, 5, process.stdout + process.stderr)
        self.assertEqual(denied['status'], 'NOT_AUTHORIZED')
        self.assertFalse(denied['executed'])

    def test_plain_implementation_reads_gate_without_commit_but_still_needs_tests(self):
        import entry_context as entry
        plain = entry.resolve_context(self.root, 'sprint-dev', version='V1', write_set=['app.py'])
        (self.root / 'app.py').write_text('value = 2\n')
        facts = G.gather(str(self.root), execution_context=plain['execution_context'])
        self.assertIn('commit', facts['offchain']['not_requested'])
        static = entry.run_static(self.root, plain['execution_context'],
            [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], inputs=['app.py'])
        completed = entry.complete_context(self.root, plain['execution_context'], static_evidence=static['evidence_file'])
        self.assertFalse(completed['completed'], completed)
        self.assertEqual(completed['checks']['commit'], 'NOT_REQUESTED')
        self.assertNotEqual(completed['checks']['related-test'], 'NOT_REQUESTED')

    def test_historical_debt_outside_task_does_not_block_current_gate(self):
        old = self.root / 'docs/design/detail/V0/_开发期设计增量.md'
        current = self.root / 'docs/design/detail/V1/_开发期设计增量.md'
        for path in (old, current):
            mkfile(str(path), '## 待级联\nmalformed historical line\nsecond historical line\n')
        _git(str(self.root), 'add', 'docs')
        _git(str(self.root), 'commit', '-qm', 'historical ledgers')
        task = self.context()
        (self.root / 'app.py').write_text('value = 2\n')
        result = G.gather(str(self.root), execution_context=task['execution_context'])
        self.assertNotIn('cascade-unparsed', G.debt_items(result))
        self.assertEqual(result['pending_cascade']['files'], [])
        self.assertTrue(result['pending_cascade']['diagnostics'])
        # 裸对话也只检查实际变动版本，不强制清理历史。
        self.assertNotIn('cascade-unparsed', G.debt_items(G.gather(str(self.root))))

    def test_pushed_commit_without_pipeline_has_no_cicd_debt_or_provider_probe(self):
        from unittest import mock
        import cicd_providers
        with tempfile.TemporaryDirectory(prefix='aidp-gate-remote-') as remote:
            subprocess.run(['git', 'init', '--bare', '-q', remote], check=True, capture_output=True)
            _git(str(self.root), 'remote', 'add', 'origin', remote)
            (self.root / 'app.py').write_text('value = 2\n')
            _git(str(self.root), 'add', 'app.py')
            _git(str(self.root), 'commit', '-qm', 'business change')
            branch = _git(str(self.root), 'symbolic-ref', '--short', 'HEAD').stdout.strip()
            pushed = _git(str(self.root), 'push', '-u', 'origin', branch)
            self.assertEqual(pushed.returncode, 0, pushed.stderr)
            config = self.root / 'memory/aidp-config.yaml'
            for pipelines in ('{}', '{test: ""}', '{test: "   "}', '{test: null}'):
                with self.subTest(pipelines=pipelines):
                    config.write_text('cicd:\n  provider: github-actions\n  pipelines: ' + pipelines + '\n')
                    with (mock.patch.object(cicd_providers, 'get_provider', side_effect=AssertionError('provider probe')),
                          mock.patch.object(G, '_head_has_formal_change', side_effect=AssertionError('unnecessary classification'))):
                        result = G.pending_cicd(str(self.root))
                    self.assertFalse(result['applicable'])
                    self.assertFalse(result['pending'])
                    self.assertFalse(result['advisory'])
                    self.assertEqual(result['status'], 'CICD_NOT_ENABLED')
            import entry_context as entry
            config.write_text('cicd:\n  provider: github-actions\n  pipelines: {}\n')
            task = entry.resolve_context(self.root, 'sprint-dev', version='V1', write_set=['app.py'],
                additional_grants=['deploy'], authorization_source={
                    'kind': 'user-text', 'request_id': 'explicit-deploy', 'text': '部署并核验真实回执'})
            gate = G.gather(str(self.root), execution_context=task['execution_context'])
            self.assertTrue(gate['offchain']['deploy'])
            self.assertFalse(gate['pending_cicd']['pending'])
            static = entry.run_static(self.root, task['execution_context'],
                [sys.executable, '-B', '-c', "import ast; ast.parse(open('app.py').read())"], inputs=['app.py'])
            # 默认 related-test 是完成门的一部分：先拿到真实相关测试 PASS，才能验证 deploy 回执门本身。
            blocked = entry.complete_context(self.root, task['execution_context'], static_evidence=static['evidence_file'])
            self.assertFalse(blocked['completed'])
            self.assertNotIn('deploy', blocked.get('pending_actions', []))
            (self.root / 'test_app_unit.py').write_text(
                'import unittest\nclass T(unittest.TestCase):\n def test_v(self):\n  self.assertIn("value", open("app.py").read())\n')
            import json as _json, subprocess as _sp
            scripts = os.path.dirname(os.path.abspath(G.__file__))
            runners = _json.dumps([{'cwd': '.', 'suffixes': ['.py'], 'argv': [sys.executable, '-B', '{tests}']}])
            scope_json = _sp.run([sys.executable, os.path.join(scripts, 'test_scope.py'), '--root', str(self.root),
                '--execution-context', task['execution_context'], '--runners-json', runners, '--json'],
                capture_output=True, text=True, check=True).stdout
            scope = _json.loads(scope_json.strip().splitlines()[-1])
            scope_path = os.path.join(os.path.dirname(task['execution_context']), 'scope.json')
            with open(scope_path, 'w') as handle:
                handle.write(_json.dumps(scope))
            ran = _sp.run([sys.executable, os.path.join(scripts, 'test_ledger.py'), 'run-scope', '--root', str(self.root),
                '--execution-context', task['execution_context'], '--scope-file', scope_path, '--env-id', 'fixture'],
                capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            run = _json.loads(ran.stdout.strip().splitlines()[-1])
            completion = entry.complete_context(self.root, task['execution_context'],
                static_evidence=static['evidence_file'], scope_file=scope_path,
                scope_hash=scope['scope_hash'], env_id='fixture', run_ids=run['run_ids'])
            self.assertFalse(completion['completed'])
            self.assertIn('deploy', completion['pending_actions'])
            config.write_text('cicd:\n  provider: github-actions\n  pipelines: {test: deploy-test.yml}\n')
            with mock.patch.object(G, '_head_has_formal_change', return_value=True):
                configured = G.pending_cicd(str(self.root))
            self.assertTrue(configured['applicable'])
            self.assertTrue(configured['advisory'])
            self.assertFalse(configured['pending'])
            self.assertEqual(configured['commit'], _git(str(self.root), 'rev-parse', 'HEAD').stdout.strip())
            self.assertEqual(G.debt_items({'pending_cicd': configured}), [])

    def test_cicd_advisory_ignores_baseline_and_keys_on_config(self):
        (self.root / 'memory/aidp-config.yaml').write_text(
            'cicd:\n  provider: github-actions\n  pipelines: {test: deploy-test.yml}\n')
        _git(str(self.root), 'branch', 'upstream-fixture', 'HEAD')
        branch = _git(str(self.root), 'symbolic-ref', '--short', 'HEAD').stdout.strip()
        _git(str(self.root), 'config', f'branch.{branch}.remote', '.')
        _git(str(self.root), 'config', f'branch.{branch}.merge', 'refs/heads/upstream-fixture')
        first = G.gather(str(self.root))
        same = G.gather(str(self.root))
        self.assertFalse(first['pending_cicd']['pending'])
        self.assertTrue(same['cache']['checks']['pending_cicd']['hit'])
        (self.root / 'memory/.sprint-autopilot-baseline.json').write_text(json.dumps({'versions': {'V1': {}}}))
        again = G.gather(str(self.root))
        self.assertTrue(again['cache']['checks']['pending_cicd']['hit'], 'baseline 不再是 pending_cicd 的输入')
        (self.root / 'memory/aidp-config.yaml').write_text('cicd:\n  provider: none\n')
        off = G.gather(str(self.root))
        self.assertFalse(off['cache']['checks']['pending_cicd']['hit'])
        self.assertEqual(off['pending_cicd']['status'], 'CICD_NOT_ENABLED')
        self.assertTrue(off['cache']['checks']['pending_cascade']['hit'])

    def test_new_definition_file_invalidates_allocation_but_historical_duplicates_are_diagnostic(self):
        from alloc_id import allocate
        old = self.root / 'docs/requirements/V0/old.md'
        mkfile(str(old), '# REQ-001 old\n# REQ-001 duplicate\n')
        _git(str(self.root), 'add', 'docs')
        _git(str(self.root), 'commit', '-qm', 'historical duplicate')
        allocate(self.root, 'REQ', 1, 'fixture', version='V1')
        first = G.gather(str(self.root))
        self.assertNotIn('id-allocation-invalid', G.debt_items(first))
        self.assertTrue(first['id_allocation']['diagnostics'])
        self.assertTrue(G.gather(str(self.root))['cache']['checks']['id_allocation']['hit'])
        added = self.root / 'docs/requirements/V1/new.md'
        mkfile(str(added), '# REQ-002 new\n# REQ-002 duplicate\n')
        changed = G.gather(str(self.root))
        self.assertFalse(changed['cache']['checks']['id_allocation']['hit'])
        self.assertIn('id-allocation-invalid', G.debt_items(changed))
        added.unlink()
        self.assertNotIn('id-allocation-invalid', G.debt_items(G.gather(str(self.root))))

    def test_input_change_during_checker_is_not_cached_as_pass(self):
        from unittest import mock
        ledger = self.root / 'docs/design/detail/V1/_开发期设计增量.md'
        mkfile(str(ledger), '## 待级联\n')
        original = G.pending_cascade
        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            ledger.write_text('## 待级联\nbroken\nanother broken\n')
            return result
        with mock.patch.object(G, 'pending_cascade', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'TREE_CHANGED'):
                G.gather(str(self.root))
        self.assertIn('cascade-unparsed', G.debt_items(G.gather(str(self.root))))

    def test_parent_permission_is_checked_even_when_all_inputs_cached(self):
        import entry_context as entry
        parent = entry.resolve_context(self.root, 'sprint-autopilot', version='V1', write_set=['app.py'],
            authorization_source={'kind': 'explicit-command', 'command': '/sprint-autopilot', 'request_id': 'wide'})
        child = entry.fork_context(self.root, parent['execution_context'], '001')
        G.gather(str(self.root), execution_context=child['execution_context'])
        entry.resolve_autopilot_root(self.root, 'V1', execution_context=parent['execution_context'],
            authorization_source={'kind': 'explicit-command', 'command': '/sprint-autopilot',
                                  'request_id': 'narrow', 'options': ['--skip-dev']})
        with self.assertRaises(ValueError):
            G.gather(str(self.root), execution_context=child['execution_context'])


def main():
    incremental = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(IncrementalGateTests))
    test_staged_path_allowlist()
    test_id_allocation_gate()
    test_non_git_boundaries()
    test_gate_pure()
    test_gate_cli_cascade()
    test_family_ledgers()
    test_cascade_bypass()
    test_offchain()
    test_pending_cicd()
    test_ledger_forms()
    test_classify_commit_change()
    test_classify_push_flow()
    test_classify_conservative_and_readonly()
    test_plain_flow_leaves_tree_untouched()
    test_standalone_release_pending_base()
    test_autopilot_flow_contracts()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed / {_skipped} skipped ══")
    return 1 if _failed or not incremental.wasSuccessful() else 0


if __name__ == "__main__":
    sys.exit(main())
