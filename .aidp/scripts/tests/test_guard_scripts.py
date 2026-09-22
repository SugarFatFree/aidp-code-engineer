#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确定性护栏脚本单测（stdlib only，零依赖；直接 `python3 scripts/tests/test_guard_scripts.py` 跑）。

覆盖两个"存在即必须真跑出结论"的护栏：

  · `check_convention_dup.py`     —— 核心约定主行双写（**形态 A 分离型 / 形态 B 内联型都要真检**）
  · `check_version_identifier.py` —— 发布版本 ↔ 代码内自报版本对齐

两者的共同回归点是**假通过**：脚本因路径假设不匹配而 SKIP + exit 0，看着"通过"实则没跑。
故每个脚本都配「正向（真检出）+ 负向（不误报）+ 跳过分类」三类断言。
"""
import hashlib
import json
import os
import subprocess
import sys
import re
import shutil
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))  # 让 import check_* 可用

import check_convention_dup as CD
import check_version_identifier as VI

_passed = _failed = _skipped = 0
REPO_ROOT = Path(HERE).resolve().parents[2]
SKILL_DIR = REPO_ROOT / ".aidp/skills/aidp-code-engineer"


def skip(name, reason):
    """前置条件不在（如脚手架 skill 的 bundle / 模板资产未就位）→ 显式跳过并计数，⛔ 不静默当通过。"""
    global _skipped
    _skipped += 1
    print(f"  ⏭️ SKIP: {name}（{reason}）")


def _load_aidp_state():
    import importlib.util as _iu
    from pathlib import Path as _P
    sp = _P(__file__).resolve().parents[1] / "aidp_state.py"
    sp_ = _iu.spec_from_file_location("aidp_state_t", str(sp))
    m = _iu.module_from_spec(sp_); sp_.loader.exec_module(m)
    return m


def _read_project_state(root):
    """项目级运行时状态：读 baseline 的 project_state 段（与 `aidp_state.load_state` 同口径）。"""
    import json as _j
    from pathlib import Path as _P
    b = _P(root) / "memory/.sprint-autopilot-baseline.json"
    if b.is_file():
        try:
            d = _j.loads(b.read_text(encoding="utf-8"))
            if isinstance(d.get("project_state"), dict):
                return d["project_state"]
        except ValueError:
            pass
    return {}


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print(f"  ❌ FAIL: {name}")


def _mkproj(main_rel, conventions, detail_bodies):
    """造一个最小 AIDP 项目：main_rel 放核心约定段，reference/ 放细则分片。"""
    root = Path(tempfile.mkdtemp())
    (root / ".aidp" / "reference").mkdir(parents=True)
    body = "## 核心约定\n\n" + "\n\n".join(conventions) + "\n\n## 其他段\n"
    p = root / main_rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    for i, frag in enumerate(detail_bodies, 1):
        (root / ".aidp" / "reference" / f"约定细则-{i}.md").write_text(frag, encoding="utf-8")
    return root


MAIN_1 = ("1. **版本规划期生成所有设计文档**：需求和详细设计在 `/version` 阶段一次性生成，"
          "Sprint 执行期只读取不重新生成。")
MAIN_2 = ("2. **新增功能走自动累进**：`/sprint-dev` 自动累进新 Sprint 并追加设计，"
          "仅适用于当前版本尚未发布时。")


def test_readme_policy():
    import readme_policy as RP
    print("【README 共享范围策略】")
    root = Path(tempfile.mkdtemp())
    cases = {
        "code/frontend/app": {"package.json": "{}"},
        "code/frontend/demo-app": {"package.json": "{}"},
        "code/frontend/app/src": {"package.json": "{}"},
        "code/backend/api": {"pom.xml": "<project/>"},
        "code/custom/parent": {"pom.xml": "<modules><module>\n child \n</module></modules>"},
        "code/custom/parent/child": {"pom.xml": "<project/>"},
        "code/custom/aggregate": {"pom.xml": "<packaging>pom</packaging><modules><module>modules/child</module></modules>"},
        "code/custom/aggregate/modules/child": {"pom.xml": "<project/>"},
        "code/custom-npm": {"package.json": '{"workspaces":["packages/*"]}'},
        "code/custom-npm/packages/app": {"package.json": "{}"},
        "code/custom-pnpm": {"pnpm-workspace.yaml": "packages:\n  - packages/*\n"},
        "code/custom-pnpm/packages/app": {"package.json": "{}"},
        "code/custom-go": {"go.work": "go 1.22\nuse ./modules/app\n"},
        "code/custom-go/modules/app": {"go.mod": "module example/app\n"},
        "code/backend/parent": {"pom.xml": "<modules><module>child</module></modules>"},
        "code/backend/parent/child": {"pom.xml": "<project/>"},
        "docs/deployment/tools/sso": {"tool.sql": "select 1"},
        "docs/requirements/V0.1": {"01.md": "x"},
        "docs/testing/V0.1": {"01.md": "x"},
        "code/sql": {"schema.sql": "create table x(id int);"},
        "code/sql/x": {"package.json": "{}"},
        "code/docs": {"guide.md": "# guide", "package.json": "{}"},
        "code/docs/x": {"pom.xml": "<project/>"},
    }
    for rel, files in cases.items():
        for name, body in files.items():
            p = root / rel / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body, encoding="utf-8")
    check("正式前端根 required", RP.is_readme_required_directory(root / "code/frontend/app", "layout1", root)["required"])
    check("side 子项目内部 src 不 required", not RP.is_readme_required_directory(root / "code/frontend/app/src", "layout1", root)["required"])
    check("example 子项目豁免", not RP.is_readme_required_directory(root / "code/frontend/demo-app", "layout1", root)["required"])
    check("正式后端根 required", RP.is_readme_required_directory(root / "code/backend/api", "layout1", root)["required"])
    check("自定义 Maven 聚合根 required", RP.is_readme_required_directory(root / "code/custom/parent", "layout1", root)["required"])
    check("自定义 Maven 子模块 required", RP.is_readme_required_directory(root / "code/custom/parent/child", "layout1", root)["required"])
    check("自定义 packaging=pom 聚合根 required", RP.is_readme_required_directory(root / "code/custom/aggregate", "layout1", root)["required"])
    check("modules/child 路径归一化后 required", RP.is_readme_required_directory(root / "code/custom/aggregate/modules/child", "layout1", root)["required"])
    check("NPM workspaces 聚合根 required", RP.is_readme_required_directory(root / "code/custom-npm", "layout1", root)["required"])
    check("NPM workspaces 子模块 required", RP.is_readme_required_directory(root / "code/custom-npm/packages/app", "layout1", root)["required"])
    check("pnpm workspace 聚合根 required", RP.is_readme_required_directory(root / "code/custom-pnpm", "layout1", root)["required"])
    check("pnpm workspace 子模块 required", RP.is_readme_required_directory(root / "code/custom-pnpm/packages/app", "layout1", root)["required"])
    check("Go workspace 聚合根 required", RP.is_readme_required_directory(root / "code/custom-go", "layout1", root)["required"])
    check("Go workspace 子模块 required", RP.is_readme_required_directory(root / "code/custom-go/modules/app", "layout1", root)["required"])
    check("正式多模块根 required", RP.is_readme_required_directory(root / "code/backend/parent", "layout1", root)["required"])
    check("正式多模块子模块 required", RP.is_readme_required_directory(root / "code/backend/parent/child", "layout1", root)["required"])
    for rel in ("docs/deployment/tools/sso", "docs/requirements/V0.1", "docs/testing/V0.1", "code/sql", "code/sql/x", "code/docs", "code/docs/x"):
        check(f"{rel} 默认不 required", not RP.is_readme_required_directory(root / rel, "layout1", root)["required"])
    state = root / "memory/.sprint-autopilot-baseline.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(json.dumps({"project_state": {"README_REQUIRED": ["docs/requirements/V0.1"]}}), encoding="utf-8")
    decision = RP.is_readme_required_directory(root / "docs/requirements/V0.1", "layout1", root)
    check("README_REQUIRED 相对路径显式 required", decision["required"] and decision["explicitly_allowed"])


    # 越界显式路径和 Maven 外置模块：必须不崩、不越界创建。
    outside = root.parent / "outside-readme-policy-test"
    state.write_text(json.dumps({"project_state": {"README_REQUIRED": ["../outside-readme-policy-test"]}}), encoding="utf-8")
    escaped = RP.is_readme_required_directory(outside, "layout1", root)
    check("README_REQUIRED 越界路径不 required", not escaped["required"])
    made_escape = RP.ensure_required_readmes(root, "layout1")
    check("README_REQUIRED 越界路径不触发 relative_to 崩溃/创建", "../outside-readme-policy-test/README.md" not in made_escape and not (outside / "README.md").exists())
    parent_pom = root / "code/custom/external-parent/pom.xml"
    parent_pom.parent.mkdir(parents=True, exist_ok=True)
    parent_pom.write_text("<packaging>pom</packaging><modules><module>../shared</module></modules>", encoding="utf-8")
    external = (parent_pom.parent / "../shared").resolve()
    external_decision = RP.is_readme_required_directory(external, "layout1", root)
    check("Maven 外置 ../shared 不崩且不自动 required", not external_decision["required"])


def test_convention_dup():
    print("【check_convention_dup 形态探测 + 双写检出】")

    # 形态 A（分离型）：主行在 AGENTS.md，CLAUDE.md 是薄壳 → 必须选中 AGENTS.md
    root = _mkproj("AGENTS.md", [MAIN_1, MAIN_2], ["### 约定 1 — 标题\n子项 Why 示例\n"])
    (root / "CLAUDE.md").write_text("# 薄壳\n\n@AGENTS.md\n", encoding="utf-8")
    r = CD.run(str(root))
    check("形态A: applicable", r["applicable"] is True)
    check("形态A: 两文件并存时选中 AGENTS.md（薄壳不抢主行）", r["main_file"] == "AGENTS.md")
    check("形态A: 抽到 2 条主行", r["checked"] == 2)
    check("形态A: 无双写", r["duplicates"] == [])

    # ★ 形态 B（仅 Claude Code）：无 AGENTS.md → 必须回落 CLAUDE.md 真检，不得 SKIP
    root = _mkproj("CLAUDE.md", [MAIN_1, MAIN_2], ["### 约定 1 — 标题\n子项 Why 示例\n"])
    r = CD.run(str(root))
    check("形态B: applicable(不再假通过)", r["applicable"] is True)
    check("形态B: 回落 CLAUDE.md", r["main_file"] == "CLAUDE.md")
    check("形态B: 抽到 2 条主行", r["checked"] == 2)

    # ★ 形态 B 下注入双写 → 必须检出（回归核心：单文件形态也要真拦得住）
    root = _mkproj("CLAUDE.md", [MAIN_1, MAIN_2],
                   ["### 约定 1 — 标题\n" + MAIN_1 + "\n"])
    r = CD.run(str(root))
    check("形态B: 检出 1 处双写", len(r["duplicates"]) == 1)
    check("形态B: 命中约定号=1", r["duplicates"] and r["duplicates"][0]["convention"] == 1)

    # 形态 A 下注入双写同样检出
    root = _mkproj("AGENTS.md", [MAIN_1, MAIN_2],
                   ["### 约定 2 — 标题\n" + MAIN_2 + "\n"])
    r = CD.run(str(root))
    check("形态A: 检出双写且命中约定号=2",
          len(r["duplicates"]) == 1 and r["duplicates"][0]["convention"] == 2)

    # 归一化契约：去 `*` + 折叠空白（缩进/换行/连续空格）后仍要抓到
    # ⚠️ 契约边界：折叠 ≠ 删除——在词间**插入**一个原本没有的空格可绕过。
    #    可接受：本护栏防的是**复制粘贴式**双写（原样保留空白），不是对抗性规避。
    disguised = "  " + MAIN_1.replace("**", "").replace(" ", "\n    ") + "  "
    root = _mkproj("AGENTS.md", [MAIN_1], ["### 约定 1 — 标题\n" + disguised + "\n"])
    check("去星号+折叠缩进/换行后仍检出复制", len(CD.run(str(root))["duplicates"]) == 1)

    # 跳过分类：非 AIDP 项目
    empty = Path(tempfile.mkdtemp())
    r = CD.run(str(empty))
    check("not-aidp: 分类正确", r["applicable"] is False and r["skip_kind"] == "not-aidp")

    # 跳过分类：主行文件在、却抽不出主行（格式漂移）→ 必须与"不适用"区分
    root = Path(tempfile.mkdtemp())
    (root / ".aidp" / "reference").mkdir(parents=True)
    (root / "CLAUDE.md").write_text("# 没有核心约定段\n", encoding="utf-8")
    (root / ".aidp" / "reference" / "约定细则-1.md").write_text("x\n", encoding="utf-8")
    r = CD.run(str(root))
    check("no-conventions: 分类正确", r["applicable"] is False and r["skip_kind"] == "no-conventions")

    # 跳过分类：无细则分片
    root = Path(tempfile.mkdtemp())
    (root / ".aidp" / "reference").mkdir(parents=True)
    (root / "AGENTS.md").write_text("## 核心约定\n\n" + MAIN_1 + "\n", encoding="utf-8")
    r = CD.run(str(root))
    check("no-detail-fragments: 分类正确",
          r["applicable"] is False and r["skip_kind"] == "no-detail-fragments")


def _mkcode(files):
    root = Path(tempfile.mkdtemp())
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_version_identifier():
    print("【check_version_identifier 版本标识对齐】")

    # 正向：真实回流形状 —— SERVICE_VERSION 落后于发布版本
    root = _mkcode({
        "code/backend/svc/src/HealthRoutes.kt": 'private const val SERVICE_VERSION = "0.2.0"\n',
    })
    r = VI.run(str(root), "V0.3.0", ["code"])
    check("检出 SERVICE_VERSION 漂移", len(r["mismatched"]) == 1)
    check("漂移值=0.2.0", r["mismatched"] and r["mismatched"][0]["value"] == "0.2.0")
    check("带行号定位", r["mismatched"] and r["mismatched"][0]["line"] == 1)

    # 归一化：V 前缀 / -SNAPSHOT 后缀都算一致
    root = _mkcode({
        "code/f/package.json": '{"version":"v0.3.0"}\n',
        "code/b/build.gradle.kts": 'version = "0.3.0-SNAPSHOT"\n',
        "code/b/application.yml": "info:\n  app:\n    version: 0.3.0\n",
    })
    r = VI.run(str(root), "V0.3.0", ["code"])
    check("V 前缀/-SNAPSHOT 归一化后对齐", r["mismatched"] == [] and len(r["matched"]) == 3)

    # 降噪 1：协议/工具链版本常量不误判（deny-list 后缀匹配）
    root = _mkcode({
        "code/b/A.kt": ('const val CURRENT_FORMAT_VERSION = "1.0"\n'
                        'const val API_VERSION = "2.1"\n'
                        'const val SPRING_BOOT_VERSION = "3.2.0"\n'),
    })
    r = VI.run(str(root), "V0.3.0", ["code"])
    check("deny-list 后缀匹配排除非制品版本", r["applicable"] is False and r["scanned"] == 0)

    # 降噪 2：占位值豁免，不算不一致
    root = _mkcode({"code/f/package.json": '{"version":"0.0.0"}\n'})
    r = VI.run(str(root), "V0.3.0", ["code"])
    check("0.0.0 占位豁免", r["mismatched"] == [] and len(r["placeholders"]) == 1)

    # 降噪 3：pom.xml 只取自身 <version>，纯继承模块不算落点
    root = _mkcode({
        "code/b/child/pom.xml": ('<project xmlns="http://maven.apache.org/POM/4.0.0">'
                                 '<parent><version>9.9.9</version></parent>'
                                 '<artifactId>child</artifactId></project>'),
        "code/b/self/pom.xml": ('<project xmlns="http://maven.apache.org/POM/4.0.0">'
                                '<artifactId>self</artifactId><version>0.1.0</version></project>'),
    })
    r = VI.run(str(root), "V0.3.0", ["code"])
    check("继承模块不算落点、自身 version 算", r["scanned"] == 1)
    check("自身 version 漂移被检出",
          len(r["mismatched"]) == 1 and r["mismatched"][0]["value"] == "0.1.0")

    # 降噪 4：不下钻依赖/产物目录
    root = _mkcode({"code/f/node_modules/pkg/package.json": '{"version":"1.2.3"}\n'})
    check("跳过 node_modules", VI.run(str(root), "V0.3.0", ["code"])["scanned"] == 0)

    # 无落点 → 不适用，不误报
    root = _mkcode({"code/x/a.rs": "fn main(){}\n"})
    r = VI.run(str(root), "V0.3.0", ["code"])
    check("无落点→不适用", r["applicable"] is False and r["mismatched"] == [])

    # ── 第三方代码防误伤（真实回流：本仓 adminlte/bootstrap.min.js 一次误报 11 处）──

    # 降噪 5：对象属性赋值 `a.VERSION="3.4.1"` 不是本应用自报版本
    root = _mkcode({"code/f/lib.js": 'a.VERSION="3.4.1",n.VERSION="3.4.1"\n'})
    check("对象属性赋值 .VERSION 不算落点",
          VI.run(str(root), "V0.3.0", ["code"])["scanned"] == 0)

    # 降噪 6：压缩产物整文件跳过
    root = _mkcode({"code/f/vendor.min.js": 'const VERSION = "3.4.1"\n',
                    "code/f/app.bundle.js": 'const VERSION = "3.4.1"\n'})
    check("*.min.js / *.bundle.js 整文件跳过",
          VI.run(str(root), "V0.3.0", ["code"])["scanned"] == 0)

    # 降噪 7：第三方库落地目录不下钻
    root = _mkcode({"code/f/static/bower_components/b/pkg.json": "x",
                    "code/f/static/bower_components/b/package.json": '{"version":"3.4.1"}\n'})
    check("bower_components 不下钻", VI.run(str(root), "V0.3.0", ["code"])["scanned"] == 0)

    # 降噪 8：项目级排除清单 —— vendored 的整个第三方 Maven 工程
    THIRD = ('<project xmlns="http://maven.apache.org/POM/4.0.0">'
             '<artifactId>xxl-job</artifactId><version>3.1.0</version></project>')
    MINE = ('<project xmlns="http://maven.apache.org/POM/4.0.0">'
            '<artifactId>mine</artifactId><version>0.2.0</version></project>')
    root = _mkcode({"code/b/app/xxl-job/pom.xml": THIRD, "code/b/app/pom.xml": MINE})
    check("无排除时两处都算落点", VI.run(str(root), "V0.3.0", ["code"])["scanned"] == 2)
    pats = ["code/b/app/xxl-job"]
    r = VI.run(str(root), "V0.3.0", ["code"], pats)
    check("--exclude 排除 vendored 工程", r["scanned"] == 1)
    check("排除后只剩自家 pom", r["mismatched"][0]["value"] == "0.2.0")
    # 同样内容改从 .aidp-version-ignore 文件读
    (root / VI.VERSION_IGNORE_FILE).write_text(
        "# vendored 第三方\ncode/b/app/xxl-job\n", encoding="utf-8")
    check(".aidp-version-ignore 文件生效",
          VI.run(str(root), "V0.3.0", ["code"])["scanned"] == 1)

    # ── --apply 写回（/version Step 2.7.3 规划期改齐 + 3.3.13 交互式"自动改"共用）──

    # 保留风格：只换 semver 主体，v 前缀 / -SNAPSHOT 后缀原样留
    check("retarget 保留 -SNAPSHOT", VI.retarget("0.2.0-SNAPSHOT", "0.3.0") == "0.3.0-SNAPSHOT")
    check("retarget 剥掉小写 v 前缀", VI.retarget("v1.2.3", "0.3.0") == "0.3.0")
    check("retarget 剥掉大写 V 前缀", VI.retarget("V0.11.2", "0.12.0") == "0.12.0")
    check("retarget 剥前缀同时保后缀",
          VI.retarget("V1.0.0-SNAPSHOT", "0.3.0") == "0.3.0-SNAPSHOT")
    check("retarget 无后缀原样", VI.retarget("0.2.0", "0.3.0") == "0.3.0")

    # 默认安全档：只改构建描述符；代码常量 / yaml 落 scope 外不改
    root = _mkcode({
        "code/f/package.json": '{\n  "name": "w",\n  "version": "0.2.0",\n'
                               '  "dependencies": {\n    "version": "^1.0.0"\n  }\n}\n',
        "code/b/A.kt": 'const val SERVICE_VERSION = "0.2.0"\n',
        "code/b/application.yml": "info:\n  app:\n    version: 0.2.0\n",
    })
    r0 = VI.run(str(root), "V0.3.0", ["code"])
    applied, skipped, failed = VI.apply_fixes(str(root), r0["mismatched"], "0.3.0",
                                              "build-descriptor")
    check("默认档只改构建描述符", len(applied) == 1 and failed == [])
    check("代码常量/yaml 落 scope 外", len(skipped) == 2)
    pkg = (root / "code/f/package.json").read_text(encoding="utf-8")
    check("package.json 顶层 version 已改", '"version": "0.3.0"' in pkg)
    check("依赖里的 version 未被误改", '"version": "^1.0.0"' in pkg)
    check("package.json 未被重排（键序/缩进保留）", pkg.startswith('{\n  "name": "w",'))

    # all 档：连代码常量 + yaml 一起改，复验归零
    r1 = VI.run(str(root), "V0.3.0", ["code"])
    VI.apply_fixes(str(root), r1["mismatched"], "0.3.0", "all")
    check("all 档改齐后复验归零", VI.run(str(root), "V0.3.0", ["code"])["mismatched"] == [])

    # Maven 反应堆：改父 pom 自身 version → 子模块 <parent><version> 连带同步
    POM_P = ('<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
             '  <parent><artifactId>spring-boot-starter-parent</artifactId>'
             '<version>3.2.0</version></parent>\n'
             '  <groupId>com.x</groupId><artifactId>app</artifactId>\n'
             '  <!-- 本应用版本 -->\n  <version>0.2.0-SNAPSHOT</version>\n</project>\n')
    POM_C = ('<project xmlns="http://maven.apache.org/POM/4.0.0">\n'
             '  <parent><groupId>com.x</groupId><artifactId>app</artifactId>'
             '<version>0.2.0-SNAPSHOT</version></parent>\n'
             '  <artifactId>app-api</artifactId>\n'
             '  <dependencies><dependency><artifactId>o</artifactId>'
             '<version>0.2.0-SNAPSHOT</version></dependency></dependencies>\n</project>\n')
    root = _mkcode({"code/b/app/pom.xml": POM_P, "code/b/app/api/pom.xml": POM_C})
    r2 = VI.run(str(root), "V0.3.0", ["code"])
    check("子模块继承版本不算落点（只检出父 pom 一处）", len(r2["mismatched"]) == 1)
    applied, _, failed = VI.apply_fixes(str(root), r2["mismatched"], "0.3.0", "build-descriptor")
    check("父 pom + 子模块 parent 引用共改 2 处", len(applied) == 2 and failed == [])
    parent_txt = (root / "code/b/app/pom.xml").read_text(encoding="utf-8")
    child_txt = (root / "code/b/app/api/pom.xml").read_text(encoding="utf-8")
    check("父 pom 自身 version 保留 -SNAPSHOT", "<version>0.3.0-SNAPSHOT</version>" in parent_txt)
    check("父 pom 的 <parent> 坐标未被误改（3.2.0 原样）", "<version>3.2.0</version>" in parent_txt)
    check("父 pom 注释保留", "<!-- 本应用版本 -->" in parent_txt)
    check("子模块 <parent><version> 已同步",
          "<artifactId>app</artifactId><version>0.3.0-SNAPSHOT</version></parent>" in child_txt)
    check("子模块 <dependency> 同版本串未被误伤",
          "<artifactId>o</artifactId><version>0.2.0-SNAPSHOT</version>" in child_txt)

    # 幂等：已对齐后重跑 apply 为空操作
    r3 = VI.run(str(root), "V0.3.0", ["code"])
    applied2, _, failed2 = VI.apply_fixes(str(root), r3["mismatched"], "0.3.0", "build-descriptor")
    check("已对齐后重跑 apply 幂等（0 改动）", applied2 == [] and failed2 == [])

    # ── Dockerfile（镜像自报版本；样本取自实际项目 / xxl-job 真实形态）──

    DOCKERFILE = (
        # 陷阱区：基础镜像 / 工具链 / 组件版本，一处都不能碰
        'ARG BASE_IMAGE=registry.example.com/base/eclipse-temurin-jre-noble:17.0.20_8\n'
        'FROM ${BASE_IMAGE}\n'
        'ARG NGINX_VERSION=1.21.6\n'
        'ARG ALPINE_VERSION=3.18.4\n'
        'ENV JAVA_VERSION 17.0.2\n'
        'ENV NODE_VERSION=20.11.0\n'
        'LABEL java.version="17.0.2"\n'
        'LABEL maintainer="ec-server"\n'
        # 真落点区
        'ARG APP_VERSION=0.11.2\n'          # 用户最新口径：无引号、无 V 前缀
        'LABEL org.opencontainers.image.version="${APP_VERSION}"\n'
        'LABEL version="0.2.0"\n'
        'COPY target/app-0.2.0.jar /app.jar\n'
        'ADD target/xxl-job-admin-*.jar /a.jar\n'
        # 裸 VERSION：算落点但归需人复核档（Dockerfile 里它多半是被装组件的版本）
        'ARG VERSION=1.21.6\n'
    )
    root = _mkcode({"code/b/app/Dockerfile": DOCKERFILE})
    r = VI.run(str(root), "V0.12.0", ["code"])
    names = {h["name"]: h for h in r["mismatched"]}
    check("Dockerfile 只检出 4 处（3 真落点 + 裸 VERSION）", r["scanned"] == 4)
    check("ARG APP_VERSION 检出（无引号无 V 的裸 semver 形态）",
          names.get("ARG APP_VERSION", {}).get("value") == "0.11.2")
    check("LABEL version 检出", "LABEL version" in names)
    check("COPY 产物名内嵌版本检出", "COPY 产物名内嵌版本" in names)
    check("裸 ARG VERSION 归 runtime-config（不进默认改档）",
          names.get("ARG VERSION", {}).get("kind") == "runtime-config")
    check("基础镜像 / 工具链 / LABEL java.version / 通配 jar 均不算落点",
          not any(k in names for k in
                  ("ARG BASE_IMAGE", "ARG NGINX_VERSION", "ARG ALPINE_VERSION",
                   "ENV JAVA_VERSION", "ENV NODE_VERSION", "LABEL java.version",
                   "LABEL maintainer")))
    check("LABEL 值为 ${ARG} 变量引用时不算落点",
          "LABEL org.opencontainers.image.version" not in names)

    applied, skipped, failed = VI.apply_fixes(str(root), r["mismatched"], "0.12.0",
                                              "build-descriptor")
    check("Dockerfile 写回 3 处、裸 VERSION 落 scope 外",
          len(applied) == 3 and len(skipped) == 1 and failed == [])
    dk = (root / "code/b/app/Dockerfile").read_text(encoding="utf-8")
    check("ARG APP_VERSION 写回为裸 semver（不加引号不加 V）",
          "ARG APP_VERSION=0.12.0\n" in dk)
    check("LABEL version 已写回", 'LABEL version="0.12.0"' in dk)
    check("COPY jar 名已同步（否则镜像构建找不到文件）", "target/app-0.12.0.jar" in dk)
    check("基础镜像版本原样未动", "eclipse-temurin-jre-noble:17.0.20_8" in dk)
    check("NGINX/ALPINE/JAVA/NODE 版本原样未动",
          all(s in dk for s in ("NGINX_VERSION=1.21.6", "ALPINE_VERSION=3.18.4",
                                "ENV JAVA_VERSION 17.0.2", "NODE_VERSION=20.11.0")))
    check("LABEL java.version 原样未动", 'LABEL java.version="17.0.2"' in dk)
    check("裸 ARG VERSION 原样未动（默认档不碰）", "ARG VERSION=1.21.6" in dk)
    check("通配 jar 原样未动", "xxl-job-admin-*.jar" in dk)

    # 一行多 KV：必须按键名精确定位，不能整行 replace 旧值
    root = _mkcode({"code/b/Dockerfile": 'LABEL other=0.2.0 version=0.2.0\n'})
    r = VI.run(str(root), "V0.9.0", ["code"])
    VI.apply_fixes(str(root), r["mismatched"], "0.9.0", "build-descriptor")
    check("一行多 KV 只改白名单键那个",
          (root / "code/b/Dockerfile").read_text(encoding="utf-8").strip()
          == "LABEL other=0.2.0 version=0.9.0")

    # 文件名变体全认
    for fn in ("Dockerfile.prod", "prod.Dockerfile", "Containerfile"):
        root = _mkcode({f"code/b/{fn}": 'LABEL version="0.2.0"\n'})
        check(f"{fn} 被识别", VI.run(str(root), "V0.9.0", ["code"])["scanned"] == 1)

    # ── V/v 前缀：匹配要兼容、写回一律剥掉（代码内自报版本应是纯 semver）──

    root = _mkcode({
        "code/b/Dockerfile": 'ARG APP_VERSION="V0.11.2"\n',      # 带 V 带引号（历史写法）
        "code/b/Dockerfile.lower": "LABEL version=v0.11.2\n",     # 带小写 v 无引号
        "code/b/Dockerfile.bare": "ARG APP_VERSION=0.11.2\n",     # 无 V 无引号（现口径）
        "code/b/A.kt": 'const val SERVICE_VERSION = "V0.11.2"\n',
        "code/b/build.gradle": 'version = "V0.11.2-SNAPSHOT"\n',
        "code/b/Cargo.toml": '[package]\nversion = "v0.11.2"\n',
    })
    r = VI.run(str(root), "V0.12.0", ["code"])
    check("三种前缀形态都被检出", r["scanned"] == 6 and len(r["mismatched"]) == 6)
    check("落点值含原前缀（供报告如实展示）",
          {h["value"] for h in r["mismatched"]} == {"V0.11.2", "v0.11.2", "0.11.2",
                                                   "V0.11.2-SNAPSHOT"})
    VI.apply_fixes(str(root), r["mismatched"], "0.12.0", "all")
    check("写回后复验归零", VI.run(str(root), "V0.12.0", ["code"])["mismatched"] == [])
    rd = lambda f: (root / f).read_text(encoding="utf-8")
    check("Dockerfile 带 V 写回剥前缀", 'ARG APP_VERSION="0.12.0"' in rd("code/b/Dockerfile"))
    check("Dockerfile 小写 v 写回剥前缀",
          "LABEL version=0.12.0\n" == rd("code/b/Dockerfile.lower"))
    check("Dockerfile 裸形态写回仍是裸形态",
          "ARG APP_VERSION=0.12.0\n" == rd("code/b/Dockerfile.bare"))
    check("代码常量写回剥前缀", 'SERVICE_VERSION = "0.12.0"' in rd("code/b/A.kt"))
    check("gradle 剥前缀但保 -SNAPSHOT",
          'version = "0.12.0-SNAPSHOT"' in rd("code/b/build.gradle"))
    check("Cargo.toml 写回剥前缀", 'version = "0.12.0"' in rd("code/b/Cargo.toml"))

    # package.json 顶层定位：紧凑单行 / 格式化多行都要中，且 dependencies 里
    # **同名同值**的 "version" 一律不动（值完全相同，只能靠大括号深度区分）
    COMPACT = '{"name":"x","dependencies":{"version":"V0.11.2"},"version":"V0.11.2"}\n'
    PRETTY = ('{\n  "name": "y",\n  "version": "v0.11.2",\n'
              '  "dependencies": {\n    "version": "v0.11.2"\n  }\n}\n')
    root = _mkcode({"code/a/package.json": COMPACT, "code/b/package.json": PRETTY})
    r = VI.run(str(root), "V0.12.0", ["code"])
    applied, _, failed = VI.apply_fixes(str(root), r["mismatched"], "0.12.0",
                                        "build-descriptor")
    check("紧凑 + 格式化 package.json 都写回成功", len(applied) == 2 and failed == [])
    check("紧凑单行：顶层 version 已改",
          '"version":"0.12.0"}' in rd("code/a/package.json"))
    check("紧凑单行：dependencies 里同名同值未动",
          '"dependencies":{"version":"V0.11.2"}' in rd("code/a/package.json"))
    check("格式化：顶层 version 已改", '"version": "0.12.0"' in rd("code/b/package.json"))
    check("格式化：dependencies 里同名同值未动",
          '    "version": "v0.11.2"' in rd("code/b/package.json"))


def test_baseline_run_state_and_version_pick():
    """本轮修的两个确定性行为：stuck 计数推进判定 / 当前开发版本选版口径。"""
    print("【baseline_edit run-state 推进判定 + current-version 选版】")
    import subprocess
    S = os.path.join(os.path.dirname(HERE), "baseline_edit.py")

    def run(bl, *args):
        r = subprocess.run([sys.executable, S, "--baseline", bl, *args],
                           capture_output=True, text=True)
        return r.stdout.strip()

    # ── run-state：同 Phase 同 Sprint 累加；Sprint 游标前移 / 换 Phase 即重置 ──
    d = tempfile.mkdtemp(); bl = os.path.join(d, "b.json")
    open(bl, "w").write("{}")
    for _ in range(3):
        run(bl, "--version", "V0.1.0", "run-state", "3.2-dev", "3.2-dev", "002", "--summary", "s")
    check("同 Phase 同 Sprint × 3 → enter#=3",
          run(bl, "--version", "V0.1.0", "get", "run_state.phase_enter_count") == "3")
    run(bl, "--version", "V0.1.0", "run-state", "3.2-dev", "3.2-dev", "003", "--summary", "s")
    check("Sprint 游标前移 → 重置为 1（防长版本被误判 stuck 冻结）",
          run(bl, "--version", "V0.1.0", "get", "run_state.phase_enter_count") == "1")
    run(bl, "--version", "V0.1.0", "run-state", "3.3-audit", "3.4-finish", "done", "--summary", "s")
    check("换 Phase → 重置为 1",
          run(bl, "--version", "V0.1.0", "get", "run_state.phase_enter_count") == "1")

    # ── current-version：优先待测的最老一个，防「下版把上版饿死」 ──
    d2 = tempfile.mkdtemp(); bl2 = os.path.join(d2, "c.json")
    open(bl2, "w").write(json.dumps({"versions": {
        "V0.1.0": {"phase_beta_done_at": "2026-08-18T10:00:00+08:00",
                   "last_deployed_at": "2026-08-18T10:30:00+08:00"},
        "V0.2.0": {"phase_beta_done_at": "2026-08-18T14:00:00+08:00",
                   "last_deployed_at": "2026-08-18T14:30:00+08:00",
                   "aiauto_tested_at": "2026-08-18T15:00:00+08:00"}}}))
    check("上版未测 → 选上版（旧口径会错选最新的下版）",
          run(bl2, "current-version") == "V0.1.0")
    run(bl2, "--version", "V0.1.0", "set", "aiauto_tested_at", "2026-08-18T11:00:00+08:00")
    check("全都测过 → 回到最新优先", run(bl2, "current-version") == "V0.2.0")
    run(bl2, "--version", "V0.2.0", "set", "last_deployed_at", "2026-08-18T16:00:00+08:00")
    check("测后又部署 → 该版重回待测", run(bl2, "current-version") == "V0.2.0")

    # ── 冻结版不得霸占选版：needs_human 的版本每 tick 在冻结门 early-exit，
    #    若它恰是「最老待测」就会永久占住结果、把后续版本饿死，并经 aiauto_blocked_reason
    #    把后续版本一并连坐冻结成 config-missing（错误诊断）。故待测集内未冻结优先。 ──
    d3 = tempfile.mkdtemp(); bl3 = os.path.join(d3, "f.json")
    frozen_then_live = {"versions": {
        "V0.1.0": {"phase_beta_done_at": "2026-08-18T10:00:00+08:00", "needs_human": True},
        "V0.2.0": {"phase_beta_done_at": "2026-08-19T10:00:00+08:00"}}}
    open(bl3, "w").write(json.dumps(frozen_then_live))
    check("最老版已冻结 → 跳过它选未冻结的下版（防饿死 + 连坐冻结）",
          run(bl3, "current-version") == "V0.2.0")
    all_frozen = json.loads(json.dumps(frozen_then_live))
    all_frozen["versions"]["V0.2.0"]["needs_human"] = True
    open(bl3, "w").write(json.dumps(all_frozen))
    check("全部冻结 → 回落最老（保留其自动解冻判定的机会，不是永远不选）",
          run(bl3, "current-version") == "V0.1.0")


def test_baseline_build_addressing_and_split_version_guard():
    """`builds[]` 寻址（--build）+ 未加引号版本号的静默切碎护栏。

    回归的是本文件最危险的一类静默失败：`versions.V0.4.0.state` 漏引号不会报错，
    而是在旁边造出 `{"V0":{"4":{"0":{...}}}}`，真节点一字未动、调用方还拿到 rc=0
    （多数写点带 `|| true` 更是全咽）。实际项目的 baseline 里已实际躺过该畸形键。
    同源坑：`builds` 是对象数组，点号路径压根寻址不到，硬写同样只造畸形键。
    """
    print("【baseline_edit builds[] 寻址 + 切碎版本号护栏】")
    import subprocess
    S = os.path.join(os.path.dirname(HERE), "baseline_edit.py")

    def run(bl, *args):
        r = subprocess.run([sys.executable, S, "--baseline", bl, *args],
                           capture_output=True, text=True)
        return r.returncode, r.stdout.strip()

    d = tempfile.mkdtemp(); bl = os.path.join(d, "b.json")
    open(bl, "w").write(json.dumps({
        "versions": {"V0.4.0": {"builds": [
            {"build": "V0.4.0_build1001", "status": "closed"},
            {"build": "V0.4.0_build1002", "status": "running"}]}},
        "report_deliveries": {"V0.2.0_build1001": {"exec_report": {"at": "x"}}},
        "aiauto_test_heartbeat_at": "t"}))

    # ── --build 寻址：写进目标条目、不碰兄弟条目、不把 builds[] 抹成 {} ──
    rc, _ = run(bl, "--version", "V0.4.0", "--build", "V0.4.0_build1002", "set", "driver_actual", "cli")
    check("--build set → rc=0", rc == 0)
    check("--build get → 读回写入值",
          run(bl, "--version", "V0.4.0", "--build", "V0.4.0_build1002", "get", "driver_actual")[1] == "cli")
    _d = json.load(open(bl))
    _blds = _d["versions"]["V0.4.0"]["builds"]
    check("builds[] 仍是数组、长度不变（未被 plant 覆盖成 {}）",
          isinstance(_blds, list) and len(_blds) == 2)
    check("兄弟 build 未被污染", "driver_actual" not in _blds[0])
    check("--build 指向不存在的 build → rc=2（入参错，区别于路径语法错 1）",
          run(bl, "--version", "V0.4.0", "--build", "NOPE", "set", "x", "y")[0] == 2)
    check("--build 缺 --version → rc=2",
          run(bl, "--build", "X", "set", "a", "b")[0] == 2)

    # ── 切碎护栏：拦下漏引号的版本号 / build 号，且**一个畸形键都不留** ──
    check("versions.V0.4.0.state（漏引号）→ rc=1 拦下",
          run(bl, "set", "versions.V0.4.0.state", "S0")[0] == 1)
    check("builds[V0.4.0_build1001].x（点号寻址数组）→ rc=1 拦下",
          run(bl, "--version", "V0.4.0", "set", "builds[V0.4.0_build1001].driver_actual", "cli")[0] == 1)
    check("拦下后 baseline 无畸形嵌套键（V0/4/0 三级）",
          "V0" not in json.load(open(bl))["versions"])

    # ── 不得误伤既有合法写法（护栏太宽 = 把正常写点全拦死，比不加更糟）──
    for p in ("aiauto_test_heartbeat_at",
              'versions."V0.4.0".builds',
              'report_deliveries."V0.2.0_build1001".exec_report.at'):
        check(f"合法路径放行：{p}", run(bl, "get", p)[0] == 0)
    check("--version 前缀写法放行（版本号不出现在相对路径里）",
          run(bl, "--version", "V0.4.0", "get", "builds")[0] == 0)


def test_phase_completion_and_obligation_reckoning():
    """下游两份反馈的结构级修复：阶段完成判据 + 收尾义务清算。

    ① run-state 拒写「自述未完成却同时宣告完成」——实测：派发规划子 Agent 7 秒后就写
       phase_completed_at 推进 next_phase，四类文档 15 分钟后才成文、auditor 96 分钟后才
       判出 2 项 Critical，开发链路已按"规划完成"跑掉 3 笔提交。
    ② 收尾门 3j/3k/3l——实测：攥着 1 条 P1 缺陷收尾门照样 PASS，执行体遂弹窗问用户
       「这条缺陷怎么处置：现在修/下版修/只修不复测」，直接违反「修不修从来不是选项」。
    """
    print("【阶段完成判据 + 收尾义务清算】")
    import subprocess
    BE = os.path.join(os.path.dirname(HERE), "baseline_edit.py")
    GT = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")

    # ── ① run-state 未完成措辞拒写 ──
    d = tempfile.mkdtemp(); bl = os.path.join(d, "b.json")
    def rs(summary):
        return subprocess.run([sys.executable, BE, "--baseline", bl, "--version", "V0.1.0",
                               "run-state", "3.1-plan", "3.1.5-build", "", "--summary", summary],
                              capture_output=True, text=True).returncode
    for bad in ("已派发规划子 Agent，执行中", "四类产物生成中", "等待回传 compact JSON",
                "version-auditor 审计中", "子 Agent 运行中"):
        check(f"自述未完成 → 拒写（{bad[:10]}…）", rs(bad) == 1)
    check("正常完成摘要 → 放行", rs("版本规划完成：四类产物已就位，auditor verdict=pass") == 0)
    # ★ 假阳性守卫：判据只取进行时信号，否定句里的「未完成 / pending」不得误伤 ——
    #   假阳性会把合法的阶段推进拦死（卡停流水线），比漏判更贵。
    for ok in ("Phase 3.1 完成，无未完成动作", "规划完成；pending_actions 已清空",
               "完成集成中台对接改造", "规划完成，未发现阻塞"):
        check(f"合法摘要不得误伤：{ok[:14]}…", rs(ok) == 0)
    # 拒写必须是**写盘前**返回：拿一份全新 baseline 只跑一次被拒的写，文件不得出现 run_state
    d2 = tempfile.mkdtemp(); bl2 = os.path.join(d2, "c.json")
    subprocess.run([sys.executable, BE, "--baseline", bl2, "--version", "V0.1.0",
                    "run-state", "3.1-plan", "3.1.5-build", "", "--summary", "子 Agent 执行中"],
                   capture_output=True, text=True)
    _left = json.load(open(bl2)) if os.path.exists(bl2) else {}
    check("拒写发生在写盘之前（不留半截 run_state / 不推进 next_phase）",
          "run_state" not in ((_left.get("versions") or {}).get("V0.1.0") or {}))

    # ── ②收尾门义务清算 ──
    dg = tempfile.mkdtemp()
    def gate(baseline_obj, pattern):
        p = os.path.join(dg, "g.json")
        open(p, "w").write(json.dumps(baseline_obj))
        r = subprocess.run([sys.executable, GT, "check", "--version", "V0.1.0",
                            "--build", "V0.1.0_build1001", "--repo-root", dg,
                            "--baseline", p, "--stage", "final", "--will-browser-test", "0"],
                           capture_output=True, text=True)
        return pattern in r.stdout

    _ok_build = {"current_build": "V0.1.0_build1001", "builds": [{"build": "V0.1.0_build1001"}]}
    check("3j 仍挂 auto_fixable_pending 却收尾 → FAIL（该走闭环，不是弹窗问用户）",
          gate({"versions": {"V0.1.0": dict(_ok_build, auto_fixable_pending=True)}},
               "仍挂着未处置的【可自动修复类】缺陷"))
    check("3j needs_human 冻结 = 合法出口 → 放行但上浮",
          gate({"versions": {"V0.1.0": dict(_ok_build, auto_fixable_pending=True, needs_human=True)}},
               "已 needs_human 冻结转人工"))
    check("3j 无 pending → 通过",
          not gate({"versions": {"V0.1.0": dict(_ok_build)}}, "仍挂着未处置"))
    check("3k pending_actions 非空 → FAIL（invariants：非空 = 本 Phase 未完成）",
          gate({"versions": {"V0.1.0": dict(_ok_build,
               run_state={"pending_actions": ["部署环境未确认（需用户确认）"]})}},
               "pending_actions 非空却在收尾"))
    check("3l current_build 有值但 builds[] 空 → FAIL（按 build 取值的门会整体空转）",
          gate({"versions": {"V0.1.0": {"current_build": "V0.1.0_build1003", "builds": []}}},
               "builds[] 为空"))


def test_card_gate_build_scoped_and_self_derived():
    """通知漏发无人能拦（实际项目中实测）：退化判据恒真 + 逐项核验挂在可被跳过的调用方。

    实测：一整轮开发 + 测试跑完，开发期与测试期里程碑通知一张没发，收尾门全程 PASS ——
      P0-1 退化判据把「规划期无 build 的 #0/#1/#1b」算进本 build，只要跑过规划就恒真；
      P0-2 唯一的强判据（逐项核验）只在命令端传 --expect-cards 时才发生，而推导写在
           phase-3-9.md —— "检查有没有漏做"本身写在"可能被漏做"的分片里。
    """
    print("【通知门：build 口径计数 + 脚本自算期望集】")
    import subprocess
    GT = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")
    d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, "memory"), exist_ok=True)
    bl = os.path.join(d, "memory", "b.json")
    led = os.path.join(d, "memory", "led.json")
    open(bl, "w").write(json.dumps({"versions": {"V0.1.0": {
        "deployment_mode": "cloud", "current_build": "V0.1.0_build1001",
        "builds": [{"build": "V0.1.0_build1001", "ai_report_finalized": True}]}}}))

    def gate(cards, extra=()):
        open(led, "w").write(json.dumps({"cards": cards}))
        r = subprocess.run([sys.executable, GT, "check", "--version", "V0.1.0",
                            "--build", "V0.1.0_build1001", "--repo-root", d,
                            "--baseline", bl, "--ledger", led, "--stage", "final", *extra],
                           capture_output=True, text=True)
        return r.stdout

    only_planning = [{"version": "V0.1.0", "node": n} for n in ("#0", "#1", "#1b")]
    out = gate(only_planning)
    check("P0-1 只有规划期无 build 的卡 → 本 build 非零推送判 FAIL（旧判据恒真）",
          "本 build 非零推送" in out and "零通知" in out)
    check("P0-2 未传 --expect-cards 也做逐项核验（脚本自算兜底）",
          "脚本自算" in out and "漏发" in out)
    check("自算集含部署卡 #1d（baseline deployment_mode=cloud）", "#1d" in out)

    full = only_planning + [{"version": "V0.1.0", "build": "V0.1.0_build1001", "node": n}
                            for n in ("#1c", "#1d", "#2")]
    out2 = gate(full)
    check("补齐 build 名下卡片后 → 非零推送与逐项核验都过",
          "零通知" not in out2 and "漏发" not in out2)

    # P1：--will-browser-test 缺省不得把"没告诉我"当成"没有"
    check("P1 缺省 → baseline 推导出 1（本 build 已 finalize 测试报告）",
          "will_browser_test=1(baseline推导" in out2)
    check("P1 显式传入 → 标注为传入，不被推导覆盖",
          "will_browser_test=0(传入)" in gate(full, extra=("--will-browser-test", "0")))

    # ★ P1bis：baseline 里的【显式落盘值】优先于按 deployment_mode 的推导。
    #   phase-3-8 落盘的 will_browser_test 已把本轮裁剪 flag（--skip-deploy / --skip-aiauto-test）算进去，
    #   而 deployment_mode 只是配置形态、不含裁剪。门若不读落盘值、自己按 deployment_mode 重推一遍，
    #   就会与命令端口径**方向相反**（一边要 #1d、一边要 #3），把合规执行逼成"漏发卡"并冻进人工专属档。
    open(bl, "w").write(json.dumps({"versions": {"V0.1.0": {
        "deployment_mode": "cloud", "will_browser_test": 0,
        "current_build": "V0.1.0_build1001",
        "builds": [{"build": "V0.1.0_build1001", "ai_report_finalized": True}]}}}))
    out3 = gate(full)
    check("★ P1bis baseline 显式 will_browser_test=0 覆盖 deployment_mode=cloud 的推导",
          "will_browser_test=0(baseline显式" in out3)
    check("★ P1bis 期望卡集随之翻面：含 #3、不含 #1d（--skip-deploy 形态）",
          "#3" in out3 and "#1d" not in out3.split("里程碑通知=")[-1].split("(脚本自算)")[0])

    # ── test-only 结构性死锁回归（实际项目中实测）──
    # 根因：_derive_expect_cards() 就地写 `args.entry_mode or "full"` 不回退 baseline，
    #      而 hooks/autopilot-stop-guard.py 调 gate 时又不传 --entry-mode → 叠加后
    #      test-only 轮次恒索要 #1c/#1d/#2 三张【本轮压根没发生】的里程碑卡，
    #      且调用方无法用任何配置纠正 → 执行体只能谎报里程碑 / 关掉整个护栏 / 改脚手架。
    d2 = tempfile.mkdtemp(); os.makedirs(os.path.join(d2, "memory"), exist_ok=True)
    bl2 = os.path.join(d2, "memory", "b.json")
    led2 = os.path.join(d2, "memory", "led.json")
    open(bl2, "w").write(json.dumps({"versions": {"V0.11.2": {
        "autopilot_entry_mode": "test-only", "deployment_mode": "none",
        "current_build": "V0.11.2_build1002",
        "builds": [{"build": "V0.11.2_build1002", "ai_report_finalized": True}]}}}))
    open(led2, "w").write(json.dumps({"cards": []}))

    def gate2(extra=()):
        r = subprocess.run([sys.executable, GT, "check", "--version", "V0.11.2",
                            "--build", "V0.11.2_build1002", "--repo-root", d2,
                            "--baseline", bl2, "--ledger", led2, "--stage", "final", *extra],
                           capture_output=True, text=True)
        return r.stdout

    out_noarg = gate2()                                  # ← hook 的实际调用路径（不传 entry-mode）
    out_arg = gate2(("--entry-mode", "test-only"))       # ← 手动带参数
    check("★test-only 不传 --entry-mode 时也从 baseline 回退（不再索要 #1c/#1d/#2）",
          "漏发" not in out_noarg)
    check("★不传参与显式传参的『应发卡集』判定一致（同字段单一口径）",
          ("漏发" in out_noarg) == ("漏发" in out_arg))
    check("★test-only 输出中不出现开发链路三卡（本轮该里程碑并未发生，补发即谎报）",
          not any(f"漏发：{c}" in out_noarg or f"漏发: {c}" in out_noarg
                  for c in ("#1c", "#1d", "#2")))
    # full 模式仍照常索要（不能为了修 test-only 把整个检查放空）
    open(bl2, "w").write(json.dumps({"versions": {"V0.11.2": {
        "autopilot_entry_mode": "full", "deployment_mode": "none",
        "current_build": "V0.11.2_build1002",
        "builds": [{"build": "V0.11.2_build1002", "ai_report_finalized": True}]}}}))
    check("★full 模式仍照常逐项核验（修 test-only 未把检查整体放空）",
          "漏发" in gate2())


def test_ceremony_ledger_pre_build_card():
    """收尾门台账必须容纳「铸 build 之前发的卡」（#0/#1/#1b/#pre-*）。

    回归的是一个每轮必撞的死结：record-card 曾把 --build 设为必填 →
    这几张卡永远进不了台账 → 收尾门恒 missing → 3 tick 冻结版本。
    """
    print("【ceremony-gate 台账：无 build 的卡可登记且被 check 认账】")
    import subprocess
    G = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")
    d = tempfile.mkdtemp()

    def gate(*args):
        return subprocess.run([sys.executable, G, *args, "--repo-root", d],
                              capture_output=True, text=True)

    r = gate("record-card", "--node", "#0", "--version", "V9.9.9")
    check("record-card 可省 --build（铸 build 前的卡）", r.returncode == 0)
    gate("record-card", "--node", "#1c", "--version", "V9.9.9", "--build", "1001")
    r = gate("check", "--version", "V9.9.9", "--build", "1001",
             "--stage", "skeleton", "--expect-cards", "#0,#1c")
    check("check 认账无 build 的卡（不再误报 missing #0）", "#0" not in (r.stdout.split("漏发：")[-1] if "漏发：" in r.stdout else ""))
    r2 = gate("check", "--version", "V9.9.9", "--build", "1001",
              "--stage", "skeleton", "--expect-cards", "#0,#1c,#2")
    check("真缺的卡仍被报出（未把门放水）", "#2" in r2.stdout)


def _load_notify():
    """notify.py 按路径加载（与其它脚本同口径，避免 sys.path 顺序影响）。"""
    import importlib.util
    path = os.path.join(os.path.dirname(HERE), "notify.py")
    spec = importlib.util.spec_from_file_location("notify_t", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_card_title_project_name():
    """里程碑通知标题必须恒带项目中文名称（flows/sprint-autopilot/phase-0-5.md 0.1bis）。

    回归的是一个"规范写了但没人执行"的缺陷：各通知模板首行历史上不带项目名，
    执行体照抄 → 标题时有时无。兜底必须【无跳过分支】，且解析失败也不得留空。
    """
    NT = _load_notify()
    print("【notify 标题固定前缀：项目中文名称恒在】")

    # ① 缺项目名 → 补在 emoji 之后、正文之前
    t, patched = NT.ensure_title_prefix("✅ V0.11 版本规划完成 · 订单中心", "示例商城", "V0.11")
    check("缺项目名被补齐", t == "✅ 示例商城 V0.11 版本规划完成 · 订单中心" and "项目名称" in patched)

    # ② 已有项目名 → 不重复插入
    t2, p2 = NT.ensure_title_prefix("📋 示例商城 V0.11 · 规划开始", "示例商城", "V0.11")
    check("已带项目名不重复补", t2 == "📋 示例商城 V0.11 · 规划开始" and not p2)

    # ③ emoji 后紧跟 `/命令名` 时不能把 `/` 当成 emoji 前缀吞掉（项目名插错位）
    t3, _ = NT.ensure_title_prefix("🎉 /sprint-aiauto-test V0.11 最终测试完成", "示例商城", "V0.11")
    check("斜杠不被当作 emoji 前缀", t3.startswith("🎉 示例商城 /sprint-aiauto-test"))

    # ④ 无 emoji 的裸标题也要补
    t4, _ = NT.ensure_title_prefix("部署完成", "示例商城", "")
    check("无 emoji 裸标题也补项目名", t4 == "示例商城 部署完成")

    def proj(cfg):
        d = Path(tempfile.mkdtemp()) / "demo-app"
        (d / "memory").mkdir(parents=True)
        if cfg is not None:
            (d / "memory/aidp-config.yaml").write_text(cfg, encoding="utf-8")
        return str(d)

    _saved = os.environ.pop("AIDP_PROJECT_NAME", None)
    try:
        # ⑤ project.name_cn 有值取之；无配置也必须回退目录名（绝不返回空）
        n, src, ascii_only = NT.resolve_project_name(proj("project:\n  name: demo-app\n  name_cn: 示例商城\n"))
        check("project.name_cn（中文）被读到", n == "示例商城" and "name_cn" in src and not ascii_only)
        n2, src2, ascii2 = NT.resolve_project_name(proj(None))
        check("无配置回退目录名且非空", n2 == "demo-app" and ascii2 and src2 == "git 根目录名")
        n3, src3, _ = NT.resolve_project_name(proj("project:\n  name_cn: \"{{project}}\"\n"))
        check("占位项目名不被采用（回退目录名）", n3 != "{{project}}" and src3 == "git 根目录名")

        # ⑥ ★ 判据是「这个值是不是中文名」，不是「哪一层先有值」：英文 name 不挡住中文候选
        n4, src4, a4 = NT.resolve_project_name(proj("project:\n  name: demo-app\n"), explicit="示例商城")
        check("★ 显式中文名优先，英文 name 不抢位", n4 == "示例商城" and not a4)
        n5, src5, a5 = NT.resolve_project_name(proj("project:\n  name: demo-app\n  name_cn: null\n"))
        check("中文全落空才退英文（取 project.name 而非目录名）",
              n5 == "demo-app" and a5 and "project.name" in src5)
        # ⑦ ★ 中文占位词必须被登记：`待填充` 三个字全是汉字，漏登就会被当合法中文名印上标题
        n6, _, a6 = NT.resolve_project_name(proj("project:\n  name: demo-app\n  name_cn: 待填充\n"))
        check("★ 中文占位词「待填充」不被当成项目名", n6 == "demo-app" and a6)
        # ⑧ 配置损坏 → 不抛异常，正常退目录名
        n7, _, a7 = NT.resolve_project_name(proj("project: [这不是: 合法\n"))
        check("配置损坏不炸、正常退英文", bool(n7) and a7)
    finally:
        if _saved is not None:
            os.environ["AIDP_PROJECT_NAME"] = _saved


# ─────────────────────────────────────────────────────────────
# check_changelog_fix_scope.py — 更新日志修复段是否混进本版自产自消的缺陷
# ─────────────────────────────────────────────────────────────
def test_changelog_fix_scope():
    """更新日志是给使用者读的：本版新功能自己引入又自己修掉的缺陷，使用者从没遇到过。

    实证：某版从 28 条 fix( 里挑 10 条写进日志，7 条依附于本版才新增的功能，产品评审当场指出。
    """
    import check_changelog_fix_scope as CF
    print("【check_changelog_fix_scope 修复段准入判据】")

    repo = Path(tempfile.mkdtemp())
    def g(*c):
        subprocess.run(["git", "-C", str(repo), *c], check=False, capture_output=True)
    subprocess.run(["git", "init", "-q", str(repo)], check=False, capture_output=True)
    g("config", "user.email", "t@t"); g("config", "user.name", "t")
    (repo / "src").mkdir()
    (repo / "src/old.js").write_text("old", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "feat: v1 功能"); g("tag", "v1.0.0")
    (repo / "src/new.js").write_text("new", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "feat(new): 本版新增分区功能")
    (repo / "src/new.js").write_text("new2", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "fix(new): 分区切换后列表未刷新")     # 自产自消
    (repo / "src/old.js").write_text("old2", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "fix(old): 菜单缓存切租户未刷新")     # 历史欠债

    LOG = "# 版本更新日志\n\n## [V1.1.0]\n\n### 🆕 新增\n- 企业/个人分区\n\n### 🐛 修复\n%s\n"
    cl = repo / "版本更新日志.md"

    # ① 阳性：两条都写进去 → 至少 1 条自产的混进来了
    cl.write_text(LOG % "- 修复分区切换后列表未刷新\n- 修复菜单缓存在切换租户后未刷新",
                  encoding="utf-8")
    r = CF.run(str(repo))
    check("适用性判定正确", r["applicable"] and r["prev_tag"] == "v1.0.0")
    check("fix 提交计数 = 2（feat 不计）", r["fix_commits"] == 2)
    check("★ 自产自消被识别（只改本版新增的文件）", r["self_produced"] == 1)
    f1 = [i for i in r["importants"] if i["code"] == "F1"]
    check("★ F1 命中：日志条数超出可入选数", len(f1) == 1 and f1[0]["over"] == 1)
    check("疑似清单列出该提交供复核",
          any("fix(new)" in x["subject"] for x in r["suspects"]))

    # ② 阴性：剔掉自产项后转绿（⛔ 不能恒红）
    cl.write_text(LOG % "- 修复菜单缓存在切换租户后未刷新", encoding="utf-8")
    check("剔除自产项后无 Important", not CF.run(str(repo))["importants"])

    # ③ 边界：改的是历史就存在的文件（全局机制类修复）→ 保留，不判自产
    (repo / "src/old.js").write_text("guard", encoding="utf-8")
    g("add", "-A"); g("commit", "-qm", "fix(core): 全局异常处理漏包业务码")
    cl.write_text(LOG % "- 修复菜单缓存在切换租户后未刷新\n- 修复接口报错未包业务码",
                  encoding="utf-8")
    r3 = CF.run(str(repo))
    check("★ 改历史文件的修复不被误判为自产", r3["self_produced"] == 1 and not r3["importants"])

    # ④ 显式豁免（判据不可能 100% 准，故必须留可豁免口）
    cl.write_text("<!-- changelog-scope-ignore: 跨新旧文件重构，已人工逐条核过 -->\n"
                  + (LOG % "- a\n- b\n- c"), encoding="utf-8")
    r4 = CF.run(str(repo))
    check("显式豁免后整体不适用", not r4["applicable"] and r4["reason"].startswith("ignored"))

    # ⑤ 非 git 仓库 / 无日志 → 不适用，绝不恒红
    d = Path(tempfile.mkdtemp())
    check("无日志 → 不适用", CF.run(str(d))["reason"] == "no-changelog")
    (d / "版本更新日志.md").write_text(LOG % "- a", encoding="utf-8")
    check("非 git 仓库 → 不适用", CF.run(str(d))["reason"] == "not-a-git-repo")


# ─────────────────────────────────────────────────────────────
# autopilot_tick_flags.py — TARGET_VERSION 必须能表达「本轮无目标版本」
# ─────────────────────────────────────────────────────────────
def test_tick_flags_target_version_no_fallback():
    """`current-version` 是 PRE_RELEASE 的定义，⛔ 不得当 TARGET 的兜底。

    回落一旦存在，`autopilot.target_version` 为空时两变量读回同一版本号 →
    决策矩阵「有 PRE_RELEASE / TARGET=null → 仅跑 Phase 2」结构不可达 →
    落进「TARGET == PRE_RELEASE = 数据冲突」熔断。而那正是 7×24 稳态最常见的局面。
    """
    print("【autopilot_tick_flags TARGET_VERSION 空目标可表达】")
    repo = Path(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    # 原生运行包使用实体副本；夹具至少复制执行链需要的三个脚本。
    (d / ".aidp/scripts").mkdir(parents=True)
    for name in ("autopilot_tick_flags.py", "baseline_edit.py", "aidp_runtime.py"):
        shutil.copy2(repo / ".aidp/scripts" / name, d / ".aidp/scripts" / name)
    (d / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps({
        "autopilot": {"target_version": "", "pre_release_version": "V0.1.0"},
        "versions": {"V0.1.0": {"phase_beta_done_at": "2026-09-01T10:00:00+08:00"}},
    }, ensure_ascii=False), encoding="utf-8")

    def _shell(cmd):
        r = subprocess.run([sys.executable, ".aidp/scripts/autopilot_tick_flags.py",
                            "--shell", "--command", cmd],
                           cwd=str(d), capture_output=True, text=True)
        out = {}
        for ln in (r.stdout or "").splitlines():
            if "=" in ln:
                k, v = ln.split("=", 1)
                out[k.strip()] = v.strip().strip("'\"")
        return out

    ap = _shell("autopilot")
    check("夹具有效：PRE_RELEASE 读得到（否则整条断言无意义）", ap.get("PRE_RELEASE_VERSION") == "V0.1.0")
    check("★ autopilot 下 TARGET_VERSION 保持为空（可表达『本轮无目标版本』）",
          ap.get("TARGET_VERSION") == "")
    at = _shell("aiauto-test")
    check("★ 测试链路仍取 current-version（按命令分流未被误伤）",
          at.get("TARGET_VERSION") == "V0.1.0")


# ─────────────────────────────────────────────────────────────
# check_version_identifier.py — 多层 Maven 反应堆的 parent 引用
# ─────────────────────────────────────────────────────────────
def test_version_identifier_nested_reactor():
    """孙模块的 parent 是中间模块、不是根 pom —— 只改直接子模块会让 mvn 解析失败。

    实测代价：`Non-resolvable parent POM … has not been downloaded`，
    而脚本自己报 `[OK] 4 处对齐`（它只复检落点、不复检可解析性），
    tag 带着必然构建失败的 pom 推了出去。
    """
    import importlib.util
    path = os.path.join(os.path.dirname(HERE), "check_version_identifier.py")
    spec = importlib.util.spec_from_file_location("cvi", path)
    CVI = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(CVI)
    print("【check_version_identifier 多层反应堆 parent 同步】")

    def build(d, root_v, mid_v, leaf_v):
        base = d / "code/backend/ep"
        (base / "ep-common/ep-common-core").mkdir(parents=True, exist_ok=True)
        (base / "pom.xml").write_text(
            f"<project><groupId>g</groupId><artifactId>ep</artifactId>"
            f"<version>{root_v}</version><modules><module>ep-common</module></modules></project>",
            encoding="utf-8")
        (base / "ep-common/pom.xml").write_text(
            f"<project><parent><groupId>g</groupId><artifactId>ep</artifactId>"
            f"<version>{mid_v}</version></parent><artifactId>ep-common</artifactId></project>",
            encoding="utf-8")
        (base / "ep-common/ep-common-core/pom.xml").write_text(
            f"<project><parent><groupId>g</groupId><artifactId>ep-common</artifactId>"
            f"<version>{leaf_v}</version></parent><artifactId>ep-common-core</artifactId></project>",
            encoding="utf-8")
        return base

    def run(d, extra=()):
        return subprocess.run([sys.executable, path, "--root", str(d), "--version", "V0.14.0",
                               *extra], capture_output=True, text=True)

    # ① 传递同步：--apply 后三层都应是 0.14.0
    d = Path(tempfile.mkdtemp()); base = build(d, "0.12.1", "0.12.1", "0.12.1")
    run(d, ("--apply",))
    leaf = (base / "ep-common/ep-common-core/pom.xml").read_text(encoding="utf-8")
    check("★ 孙模块 parent 引用被传递同步", "0.14.0" in leaf and "0.12.1" not in leaf)

    # ② 可解析性自检：落点全对、但孙模块被打坏 → 必须 FAIL，⛔ 不得报 OK
    (base / "ep-common/ep-common-core/pom.xml").write_text(
        leaf.replace("0.14.0", "0.12.1"), encoding="utf-8")
    r = run(d)
    check("★ 落点全对但反应堆解析不通 → FAIL（不再假绿）",
          r.returncode == 1 and "反应堆" in r.stdout)

    # ③ --apply 自愈：根 pom 已是新值、无落点可触发同步时也要能修好
    r2 = run(d, ("--apply",))
    check("★ --apply 能自愈已坏的反应堆", r2.returncode == 0 and "自愈" in r2.stdout)
    check("自愈后幂等（复跑仍 0）", run(d).returncode == 0)

    # ④ 阴性：仓库外 parent（三方 starter）不参与判定，⛔ 不恒红
    d2 = Path(tempfile.mkdtemp())
    (d2 / "code/backend/x").mkdir(parents=True)
    (d2 / "code/backend/x/pom.xml").write_text(
        "<project><parent><groupId>org.springframework.boot</groupId>"
        "<artifactId>spring-boot-starter-parent</artifactId><version>3.1.0</version></parent>"
        "<artifactId>x</artifactId><version>0.14.0</version></project>", encoding="utf-8")
    check("仓库外 parent 不判（不恒红）", not CVI.check_reactor_resolvable(str(d2)))


# ─────────────────────────────────────────────────────────────
# check_md_anchors.py — 站内锚点死链检查
# ─────────────────────────────────────────────────────────────
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))  # <repo>/.aidp/scripts/tests → <repo>


def test_md_anchors():
    import check_md_anchors as MA
    print("【check_md_anchors 站内锚点死链】")

    # ★ 跨文件锚点：脚本原先把这一整类「移交给路径断链检查」，但**接收方并不存在**
    #   （`.aidp/scripts/` 下无任何脚本做跨文件锚点校验）→ 整类死锚点全仓无人管。
    _cd = Path(tempfile.mkdtemp())
    (_cd / "a.md").write_text("见 [好](b.md#存在的标题) 与 [坏](b.md#不存在的标题)\n", encoding="utf-8")
    (_cd / "b.md").write_text("## 存在的标题\n", encoding="utf-8")
    _r = MA.run(str(_cd), [str(_cd)])
    _anchors = {x["anchor"] for x in _r["broken"]}
    check("★ 跨文件死锚点被检出", "b.md#不存在的标题" in _anchors)
    check("★ 跨文件有效锚点不误报", "b.md#存在的标题" not in _anchors)
    (_cd / "c.md").write_text("见 [外部](不存在的文件.md#随便)\n", encoding="utf-8")
    _r2 = MA.run(str(_cd), [str(_cd)])
    check("★ 目标文件解析不到 → 不报（交路径类检查，不双写同一结论）",
          not any("不存在的文件.md" in x["anchor"] for x in _r2["broken"]))
    shutil.rmtree(_cd, ignore_errors=True)

    # ① slugify 与 GitHub 口径对齐（CJK 保留、全角标点删除、空格逐个转连字符不合并）
    check("slug: Step 1：判断执行模式",
          MA.slugify("Step 1：判断执行模式") == "step-1判断执行模式")
    check("slug: ★ 与全角括号删除、` + ` 产生双连字符",
          MA.slugify("★ 输出前硬门：回检清单 + 三合一回写校验（不可跳过）")
          == "-输出前硬门回检清单--三合一回写校验不可跳过")
    check("slug: 去行内代码反引号", MA.slugify("`--no-tag` 准发布") == "--no-tag-准发布")

    # ② 围栏代码块内的 bash 注释不得被当成标题
    #    （不跳围栏会把 `# 0. 前置` 收成 slug，反而让真死链"匹配上"→ 漏报）
    slugs, links = MA.parse_md(
        "## 真标题\n\n```bash\n# 0. 前置失败熔断 helper\n```\n\n[x](#0-前置失败熔断-helper)\n")
    check("围栏内 bash 注释不计为标题", "0-前置失败熔断-helper" not in slugs)
    check("指向围栏内注释的锚点判死链", bool(links) and links[0][1] not in slugs)

    # ③ 有效锚点不误报 / ④ 重复标题追加 -1
    s2, l2 = MA.parse_md("## 真标题\n\n[x](#真标题)\n")
    check("有效锚点不误报", l2[0][1] in s2)
    s3, _ = MA.parse_md("## A\n## A\n")
    check("重复标题生成 a 与 a-1", "a" in s3 and "a-1" in s3)

    # ⑤ 豁免标记：只屏蔽链接收集，区块内标题仍计入 slug（否则会把区块外的合法引用误判死链）
    s5, l5 = MA.parse_md(
        "## 真标题\n<!-- anchor-check: ignore-begin 示例 -->\n[x](#v120)\n"
        "## 区块内标题\n<!-- anchor-check: ignore-end -->\n[y](#区块内标题)\n")
    check("豁免区内链接不收集", all(a != "v120" for _, a in l5))
    check("豁免区内标题仍计入 slug", "区块内标题" in s5)
    check("豁免区外引用区块内标题不误报", bool(l5) and l5[0][1] in s5)

    # ⑥ 本仓实跑 0 死链（回归闸）
    res = MA.run(REPO, MA.DEFAULT_PATHS)
    if res["broken"]:
        print("     残留:", "; ".join(f"{b['file']}:{b['line']}#{b['anchor']}" for b in res["broken"][:5]))
    check(f"本仓 0 死锚点（巡检 {res['scanned']} 份）", not res["broken"])


# ─────────────────────────────────────────────────────────────
# check_ghost_flags.py — 幽灵旗标（文档教用户传的 flag 必须真的存在）
# ─────────────────────────────────────────────────────────────
def _mkdocs(files):
    """造一个最小文档仓：{相对路径: 内容}。"""
    root = Path(tempfile.mkdtemp())
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def test_ghost_flags():
    import check_ghost_flags as GF
    print("【check_ghost_flags 幽灵旗标 / 零误报】")

    def ghosts(res):
        return sorted(u["flag"] for u in res["undefined"])

    # ① 正向：docs 教用户传 `--ghost`，没有任何命令定义它 → 必须检出；已定义的 `--real` 不报
    root = _mkdocs({
        ".aidp/commands/sprint-x.md": (
            "| 参数 | 默认 | 说明 |\n|---|---|---|\n| `--real` | 关 | 真旗标 |\n"),
        "docs/init/02_指导.md": "- `--ghost <name>`：传给 `/sprint-x` 的旗标\n- 也支持 `--real`\n",
    })
    r = GF.run(str(root))
    check("正向：未定义 flag 被检出", ghosts(r) == ["--ghost"])
    check("正向：定义过的 flag 不报", all(u["flag"] != "--real" for u in r["undefined"]))
    check("正向：给出出处行号", r["undefined"][0]["sites"] == ["docs/init/02_指导.md:1"])

    # ② 定义形态全覆盖：参数列表项 / 自身命令语法块 / 小标题 —— 少认一种就会把真 flag 误报
    root = _mkdocs({
        ".aidp/commands/sprint-y.md": (
            "- `--from-list`：列表项定义\n\n"
            "```\n/sprint-y --from-syntax   # 命令语法块\n```\n\n"
            "### `--from-heading` 模式\n"),
        ".aidp/flows/y/step.md": "用 `--from-list` / `--from-syntax` / `--from-heading`\n",
    })
    check("三种定义形态都认（列表项/语法块/小标题）", GF.run(str(root))["undefined"] == [])

    # ③ 语法块只认"自己那条命令"：`/loop 10m /sprint-z --x` 不能把 --x 当成本命令的定义
    root = _mkdocs({
        ".aidp/commands/sprint-z.md": "```\n/loop 10m /other-cmd --not-mine\n```\n",
        ".aidp/flows/z/s.md": "试试 `--not-mine`\n",
    })
    check("别人命令的 flag 不算本文件的定义", ghosts(GF.run(str(root))) == ["--not-mine"])

    # ④ 零误报之一（owner 判定）：第三方命令自带 flag 不归本护栏管
    root = _mkdocs({
        ".aidp/flows/a/s.md": (
            "```bash\n"
            "git log --fake-git-flag --pretty=x\n"
            "npx some-tool --fake-tool-flag\n"
            "```\n"
            "行内也一样：`git branch --fake-inline-flag`\n"),
    })
    check("owner=第三方命令 → 不报（git/npx）", GF.run(str(root))["undefined"] == [])

    # ⑤ 零误报之二（`\` 续行继承 owner）：续行以 flag 开头，段内没有命令 token
    root = _mkdocs({
        ".aidp/flows/a/s.md": ("```bash\ngit log --since=x \\\n"
                                 "        --fake-continued-flag\n```\n"),
    })
    check("续行继承上一行 owner → 不报", GF.run(str(root))["undefined"] == [])

    # ⑥ 零误报之三：CSS 自定义属性长得像 flag（约定 4 设计令牌里成片出现）
    root = _mkdocs({".aidp/flows/a/s.md": "令牌 `--el-color-primary` 与 `--el-border-radius`\n"})
    check("CSS 自定义属性前缀豁免", GF.run(str(root))["undefined"] == [])

    # ⑦ 零误报之四：本仓脚本的 flag 由 add_argument 兜底
    root = _mkdocs({
        ".aidp/scripts/foo.py": 'ap.add_argument("--quiet", action="store_true")\n',
        ".aidp/flows/a/s.md": "跑 `python3 .aidp/scripts/foo.py --quiet` 判定\n",
    })
    check("本仓脚本 flag 由 add_argument 认定", GF.run(str(root))["undefined"] == [])

    # ⑧ 假定义防护：`| \\`git log --since-fake\\` |` 这种"数据源表"首格不得被当成参数定义
    root = _mkdocs({
        ".aidp/commands/sprint-w.md": (
            "| 数据源 | 作用 |\n|---|---|\n| `git log --since-fake=<s>` | 取 commit |\n"),
        ".aidp/flows/w/s.md": "命令支持 `--since-fake`\n",
    })
    check("数据源表首格不算 flag 定义（防假定义）", ghosts(GF.run(str(root))) == ["--since-fake"])

    # ⑨ 行内豁免标记（反面教材 / 占位示例必用）
    root = _mkdocs({
        ".aidp/flows/a/s.md": "没有 `--never-existed` 这个旗标 <!-- flag-check: ignore -->\n"})
    check("行内 ignore 标记豁免", GF.run(str(root))["undefined"] == [])
    root = _mkdocs({".aidp/flows/a/s.md": "<!-- flag-check: ignore-file 示例集 -->\n`--never-existed`\n"})
    check("ignore-file 整份豁免", GF.run(str(root))["undefined"] == [])

    # ⑩ 反向 INFO：定义了却全仓无人引用 → 进 orphans，且不影响 undefined
    root = _mkdocs({
        ".aidp/commands/sprint-v.md": "| 参数 | 默认 |\n|---|---|\n| `--lonely` | 关 |\n"})
    r = GF.run(str(root))
    check("废弃提示：无人引用的定义进 orphans",
          [o["flag"] for o in r["orphans"]] == ["--lonely"] and r["undefined"] == [])

    # ⑪ 本仓实跑冒烟：真跑得动、真抽到东西（不断言 0，文档修复由维护者决定）
    res = GF.run(REPO)
    check(f"本仓实跑可用（提及 {res['mentioned']} 个 flag / 未定义 {len(res['undefined'])} 个）",
          res["mentioned"] > 50 and res["defined_in_commands"] > 20)


# ─────────────────────────────────────────────────────────────
# check_loop_examples.py — `/loop` 示例必带 --unattended
# ─────────────────────────────────────────────────────────────
def test_loop_examples():
    import check_loop_examples as LE
    print("【check_loop_examples /loop 示例必带 --unattended】")

    # ① 正向：漏写 flag 的两条链路示例都要检出
    root = _mkdocs({"README.md": "```bash\n/loop 10m /sprint-autopilot\n"
                                 "/loop 5m /sprint-aiauto-test\n```\n"})
    r = LE.run(str(root))
    check("正向：两处漏写都检出", len(r["violations"]) == 2)
    check("正向：带行号", [v["line"] for v in r["violations"]] == [2, 3])

    # ② 负向：带了 flag 不报（含多余空格 / 行尾注释）
    root = _mkdocs({"README.md": "```bash\n/loop 10m /sprint-autopilot --unattended   # 开发链路\n"
                                 "/loop 5m  /sprint-aiauto-test --unattended  # 测试链路\n```\n"})
    check("负向：带 --unattended 不报", LE.run(str(root))["violations"] == [])

    # ③ ★ 逐"出现"判而非逐行判：一行两条 loop、只有一条带 flag → 另一条必须被抓
    root = _mkdocs({"a.md": "完整 7×24 = `/loop 10m /sprint-autopilot --unattended` + "
                            "`/loop 5m /sprint-aiauto-test` 两条并行\n"})
    r = LE.run(str(root))
    check("同一行只给一条加 flag → 另一条仍被抓", len(r["violations"]) == 1)
    check("抓的是漏写的那条", "aiauto-test" in r["violations"][0]["snippet"])

    # ④ 无关命令不误报（只管 autopilot / aiauto-test 两条链路）
    root = _mkdocs({"a.md": "```\n/loop 5m /sprint-batch\n/loop 10m /health-check\n```\n"})
    check("非两条链路的 /loop 不报", LE.run(str(root))["violations"] == [])

    # ⑤ 豁免：对比反例用行内标记，**不硬编码文件名白名单**
    root = _mkdocs({"usage-guard.md": "| ❌ `/loop 10m /sprint-autopilot` | 会挂起 | "
                                      "<!-- loop-check: ignore 对比反例 -->\n"})
    check("行内 ignore 豁免对比反例", LE.run(str(root))["violations"] == [])
    root = _mkdocs({"a.md": "<!-- loop-check: ignore-begin 反例区 -->\n"
                            "/loop 5m /sprint-aiauto-test\n"
                            "<!-- loop-check: ignore-end -->\n"
                            "/loop 5m /sprint-aiauto-test\n"})
    r = LE.run(str(root))
    check("ignore-begin/end 只豁免区块内", len(r["violations"]) == 1 and r["violations"][0]["line"] == 4)

    # ⑥ 间隔缺省的写法（`/loop /sprint-aiauto-test`）同样受管
    root = _mkdocs({"a.md": "由 `/loop /sprint-aiauto-test` 产\n"})
    check("间隔缺省也判", len(LE.run(str(root))["violations"]) == 1)

    # ⑦ ★ `.aidp-backup-<时间戳>` 不下钻：目录名带时间戳、永远命中不了精确名集合，
    #    漏排会让**任一做过 upgrade 的下游**把历史备份里的旧文案当活跃违规恒报 ERROR
    #    （下游实测 313 处命中全在备份目录、活跃文件 0 处）。模板项目自身没有备份目录，
    #    所以这类缺陷只在下游显形 —— 必须由测试兜住。
    root = _mkdocs({".aidp-backup-20260810123517/commands/old.md": "/loop 10m /sprint-autopilot\n",
                    ".aidp/commands/live.md": "/loop 10m /sprint-autopilot --unattended\n"})
    r = LE.run(str(root))
    check("备份目录 .aidp-backup-* 不参与巡检", r["violations"] == [] and r["scanned"] == 1)
    # 反向：别把排除写宽了，活跃目录里的同样违规仍须抓
    (root / ".aidp/flows").mkdir(parents=True, exist_ok=True)
    (root / ".aidp/flows/bad.md").write_text("/loop 5m /sprint-aiauto-test\n", encoding="utf-8")
    check("活跃目录违规仍被抓（排除未写宽）", len(LE.run(str(root))["violations"]) == 1)


# ─────────────────────────────────────────────────────────────
# check_line_refs.py — 跨文件引用里的硬编码行号（WARN）
# ─────────────────────────────────────────────────────────────
def test_line_refs():
    import check_line_refs as LR
    print("【check_line_refs 硬编码行号引用】")

    # ① 正向：六种写法都要检出（真实回流形状 = §2.2 行 49~52）
    #    后两种是补进来的：裸 `L113` 与 `file.md:217`，各放过一处真死链——
    #    前者指向一份只有 104 行的文件，后者行号还在但正文早换了（比越界更难发现）。
    root = _mkdocs({
        "docs/a.md": ("见 `06_目录约定.md` §2.2 行 49~52\n"
                      "另见 b.md 第 12-34 行\n"
                      "还有 c.md:L12-34\n"
                      "以及 d.md L120-L180\n"
                      "以及 e.md L113\n"
                      "还有 f.md:217\n"),
    })
    r = LR.run(str(root))
    check("六种硬编码行号写法全检出", len(r["findings"]) == 6)
    check("★ 成对形态不被裸 LN 重复计一次（L120-L180 只算一处）",
          sum(1 for f in r["findings"] if "L180" in f.get("snippet", "")) == 0)
    check("行号原文被带出", {f["text"] for f in r["findings"]} ==
          {"行 49~52", "第 12-34 行", ":L12-34", "L120-L180", "L113", "f.md:217"})

    # ② 负向零误报：`L1-L3` 是本范式的**层级**表达（UI L1/L2、上游溯源 L1-L3），不是行号
    root = _mkdocs({"docs/a.md": "上游溯源 L1-L3 完整性；页面分 L1-L2 两级\n"})
    check("L1-L3 层级表达不误报", LR.run(str(root))["findings"] == [])

    # ③ 负向：普通数字 / 版本号 / 日期不误报
    root = _mkdocs({"docs/a.md": "V0.1.0-V0.2.0 共 12-34 项，2026-08-19 完成\n"})
    check("普通数字区间不误报", LR.run(str(root))["findings"] == [])

    # ④ 分组：目标文件真在 → live（优先改）；解析不到 → stale（拆分留痕）
    root = _mkdocs({
        "docs/a.md": "见 `b.md` 行 10~20\n见 `原-已删.md` 行 30~40\n",
        "docs/b.md": "# B\n",
    })
    r = LR.run(str(root))
    check("目标存在归 live", len(r["live"]) == 1 and r["live"][0]["target"] == "b.md")
    check("目标解析不到归 stale", len(r["stale"]) == 1)

    # ⑤ 豁免标记
    root = _mkdocs({"docs/a.md": "见 b.md 行 10~20 <!-- lineref-check: ignore 历史溯源 -->\n"})
    check("行内 ignore 豁免", LR.run(str(root))["findings"] == [])

    # ⑥ ★ 与 check_loop_examples 共用同一份排除集，同样必须跳过 `.aidp-backup-*`（口径见其 ⑦）
    root = _mkdocs({".aidp-backup-20260810123517/x.md": "见 `y.md` 行 10~20\n",
                    "docs/live.md": "见「小节标题」\n"})
    r = LR.run(str(root))
    check("备份目录 .aidp-backup-* 不参与巡检", r["findings"] == [] and r["scanned"] == 1)

    # ⑦ 本仓实跑冒烟（WARN 级，不断言 0）
    res = LR.run(REPO)
    check(f"本仓实跑可用（{res['scanned']} 份 .md / {len(res['findings'])} 处行号引用）",
          res["scanned"] > 50)


def test_autopilot_stuck_check():
    """通用 stuck 熔断：两条判据必须**同时**满足，且不得误伤正常推进。"""
    print("【autopilot_stuck_check 既不失败也不推进的兜底熔断】")
    import subprocess, datetime, json as _json
    S = os.path.join(os.path.dirname(HERE), "autopilot_stuck_check.py")

    def mk(**vers):
        d = tempfile.mkdtemp(); bl = os.path.join(d, "b.json")
        with open(bl, "w") as f:
            _json.dump({"versions": vers}, f)
        return bl

    now = datetime.datetime.now(datetime.timezone.utc)
    old = (now - datetime.timedelta(hours=3)).isoformat()
    fresh = now.isoformat()

    def rc(bl, v):
        return subprocess.run([sys.executable, S, "--baseline", bl, "--version", v, "--dry-run"],
                              capture_output=True, text=True).returncode

    bl = mk(**{"V1": {"run_state": {"current_phase": "3.2-dev", "phase_enter_count": 9,
                                    "phase_first_entered_at": old}}})
    check("次数够 + 滞留久 → 判 stuck", rc(bl, "V1") == 1)

    bl = mk(**{"V1": {"run_state": {"current_phase": "3.2-dev", "phase_enter_count": 9,
                                    "phase_first_entered_at": fresh}}})
    check("次数够但刚进入 → 不判（防误伤逐 tick 单 Sprint）", rc(bl, "V1") == 0)

    bl = mk(**{"V1": {"run_state": {"current_phase": "3.2-dev", "phase_enter_count": 3,
                                    "phase_first_entered_at": old}}})
    check("滞留久但次数少 → 不判（防误伤长 Sprint）", rc(bl, "V1") == 0)

    bl = mk(**{"V1": {"needs_human": True,
                      "run_state": {"current_phase": "x", "phase_enter_count": 99,
                                    "phase_first_entered_at": old}}})
    check("已冻结 → 不重复冻结/发卡", rc(bl, "V1") == 0)

    bl = mk(**{"V1": {}})
    check("无 run_state → 不适用", rc(bl, "V1") == 0)
    check("无 baseline → 不适用", rc("/nonexistent/b.json", "V1") == 0)

    # ★ 真写盘路径（非 --dry-run）：冻结三件套必须落齐，且 frozen 须如实反映 baseline_edit 的返回码
    #   （曾经无条件 frozen=True：写失败也报"已冻结"→ 调用方以为收口了，下 tick 判据未变、每 tick 重发 #4）
    bl = mk(**{"V1": {"run_state": {"current_phase": "3.2-dev", "phase_enter_count": 9,
                                    "phase_first_entered_at": old}}})
    p = subprocess.run([sys.executable, S, "--baseline", bl, "--version", "V1", "--json"],
                       capture_output=True, text=True)
    out = _json.loads(p.stdout or "{}")
    node = (_json.load(open(bl)).get("versions") or {}).get("V1") or {}
    check("真判 stuck → 退出码 1", p.returncode == 1)
    check("真判 stuck → frozen=true 且冻结三件套落齐",
          out.get("frozen") is True and node.get("needs_human") is True
          and node.get("freeze_reason") == "stuck-phase" and node.get("aiauto_frozen_at"))
    check("顶层 aiauto_blocked_reason 带版本号（供 autopilot 按版本解析）",
          _json.load(open(bl)).get("aiauto_blocked_reason") == "frozen:stuck-phase@V1")
    check("冻结后复跑 → already-frozen 不重复冻结/发卡", rc(bl, "V1") == 0)


def _mk_downstream(state: dict):
    """造一个最小【下游】项目（aidp-config.yaml 有 scaffold.version → 不被判为模板豁免）+ 待提交业务代码。"""
    import subprocess
    root = Path(tempfile.mkdtemp())
    (root / "memory").mkdir()
    (root / "code" / "backend" / "x").mkdir(parents=True)
    (root / "dev").mkdir()
    (root / "memory" / "aidp-config.yaml").write_text("scaffold:\n  version: V1.0.0\n", encoding="utf-8")
    (root / "memory" / ".sprint-autopilot-baseline.json").write_text(
        json.dumps({"project_state": state}, ensure_ascii=False), encoding="utf-8")
    (root / "code" / "backend" / "x" / "A.java").write_text("x\n", encoding="utf-8")
    for c in (["init", "-q", "."], ["config", "user.email", "a@b.c"], ["config", "user.name", "t"],
              ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *c], capture_output=True)
    # 制造未提交的业务代码改动（gate 判定在 commit 前跑，需要工作区脏）
    (root / "code" / "backend" / "x" / "A.java").write_text("x\ny\n", encoding="utf-8")
    return root


def test_release_scope_covers_transitional_versions():
    """约定 31.6 ③：发布收口范围必须自动含【未单独发布的过渡版本】，且版本序按数字段比较。"""
    import subprocess
    S = os.path.join(os.path.dirname(HERE), "release_scope.py")
    sys.path.insert(0, os.path.dirname(HERE))
    import release_scope as RS

    # 版本序：字符串比较会把 V0.9 判在 V0.11 之后 —— 这类翻车必须由 tuple 比较挡住
    check("V0.9 < V0.11（数字段序，非字符串序）",
          RS.parse_version("V0.9")[0] < RS.parse_version("V0.11")[0])
    check("V0.11 < V0.11.1（段数不同可比）",
          RS.parse_version("V0.11")[0] < RS.parse_version("V0.11.1")[0])
    check("非版本形态返回 None", RS.parse_version("全量") is None and RS.parse_version("0.1") is None)

    root = Path(tempfile.mkdtemp())
    (root / "docs" / "requirements").mkdir(parents=True)
    (root / "docs" / "plans").mkdir(parents=True)
    for v in ("V0.9.2", "V0.10", "V0.10.2", "V0.11", "V0.11.1"):
        (root / "docs" / "requirements" / v).mkdir()
    (root / "docs" / "plans" / "V0.12").mkdir()          # 未来版本，不该被本次覆盖
    (root / "f").write_text("x", encoding="utf-8")
    for c in (["init", "-q", "."], ["config", "user.email", "a@b.c"], ["config", "user.name", "t"],
              ["add", "-A"], ["commit", "-qm", "c1"], ["tag", "V0.9.2"], ["tag", "V0.10.2"]):
        subprocess.run(["git", "-C", str(root), *c], capture_output=True)

    def scope(ver):
        p = subprocess.run([sys.executable, S, "--version", ver, "--root", str(root), "--json"],
                           capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout or "{}")

    rc, o = scope("V0.11.1")
    check("覆盖区间 = (上一个已发布 tag, 本次版本]",
          rc == 0 and o.get("prev_released_tag") == "V0.10.2"
          and o.get("covered_versions") == ["V0.11", "V0.11.1"])
    check("★ 过渡版本 V0.11 被自动识别（此前无人认领、只能停下问用户）",
          o.get("transitional_versions") == ["V0.11"])
    check("未来版本 V0.12 不进覆盖集", "V0.12" not in (o.get("covered_versions") or []))

    rc, o = scope("V0.10.2")
    check("已随自己 tag 收口过的 V0.9.2 不再重复纳入",
          o.get("covered_versions") == ["V0.10", "V0.10.2"]
          and o.get("transitional_versions") == ["V0.10"])

    for c in (["tag", "-d", "V0.9.2"], ["tag", "-d", "V0.10.2"]):
        subprocess.run(["git", "-C", str(root), *c], capture_output=True)
    rc, o = scope("V0.11.1")
    check("首次发布（无任何 tag）→ 覆盖全部不高于本次的版本",
          o.get("prev_released_tag") is None and len(o.get("covered_versions") or []) == 5)

    rc, o = scope("0.11.1")
    check("版本号非法 → exit 2 且不瞎猜", rc == 2 and o.get("ok") is False)


def test_release_baseline_check():
    """约定 37：双轨部署基线的 12 项机器门必须真抓到缺陷，且干净基线不误报。

    ★ 断言绑【缺陷类别是否被抓到】，不绑具体文案——文案微调不该让测试变红。
    重点回归两处曾经/极易静默失效的判据：
      · 生效形态唯一：判据必须绑【解析出的全路径】。自测时首版写成行正则匹配
        `redis.cluster`，而 YAML 里那行其实是 `nodes:`（父级才是 cluster）→ 本项
        永远匹配不到、静默空跑；
      · 占位变量名唯一性：全路径命名的回检，撞名是下游真实注入事故的根因。
    """
    print("【release_baseline_check 双轨部署基线 12 项机器门】")
    # ★ 两轨力度必须对称：全量轨回答「从零怎么搭」，任一轨空目录都等于本版无法全新部署。
    #   此前配置侧空判 ERROR、SQL 侧空判 WARN，而门的放行判据是"有无 ERROR"
    #   → 空 SQL 全量轨可以 exit 0 直接放行（约定 37 明写「零变更的版本同样要产全量」）。
    _src = (Path(HERE).parents[0] / "release_baseline_check.py").read_text(encoding="utf-8")
    _sqlfn = _src.split("def check_sql_env_bound", 1)[1][:900]
    check("★ SQL 全量轨为空判 ERROR（与配置侧同级，不是 WARN）",
          'rep.error("SQL 环境绑定物"' in _sqlfn and 'rep.warn("SQL 环境绑定物"' not in _sqlfn.split("for f in files")[0])
    import subprocess
    S = os.path.join(os.path.dirname(HERE), "release_baseline_check.py")

    def run(root, ver):
        p = subprocess.run([sys.executable, S, "--version", ver, "--root", str(root), "--json"],
                           capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout or "{}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        # ── 有缺陷的基线：每类缺陷各埋一处 ──
        bad = root / "docs/deployment/V0.2.0"
        (bad / "sql/全量").mkdir(parents=True)
        (bad / "配置文件/全量/nacos").mkdir(parents=True)
        (bad / "00_索引.md").write_text("见 [断链](sql/全量/不存在.md)\n", encoding="utf-8")
        (bad / "sql/全量/00_索引.md").write_text(
            "# 全量索引\n\n导出源：192.0.2.10:3306 / schema `app_prod`\n本版无剔除项（已交叉核对）\n", encoding="utf-8")
        (bad / "配置文件/全量/00_索引.md").write_text(
            "# 配置全量索引\n\n导出源：nacos@192.0.2.10:8848 / namespace `prod`\n本版无剔除项（已交叉核对）\n", encoding="utf-8")
        (bad / "sql/全量/01_建表-用户.sql").write_text(
            'CREATE TABLE "APP"."T_USER" (ID VARCHAR(64)) STORAGE(ON "MAIN");\n', encoding="utf-8")
        (bad / "配置文件/全量/nacos/app.yml").write_text(
            "sso:\n"
            "  # 应用认证码\n"
            "  auth-code: ${AUTH_CODE:__FILL_ME__}\n"
            "  kop:\n"
            "    # 知识库认证码 · 现网真值与上面不同\n"
            "    auth-code: ${AUTH_CODE:__FILL_ME__}\n"
            "spring:\n"
            "  datasource:\n"
            "    # 库密码\n"
            "    password: Passw0rd-real\n"
            "  redis:\n"
            "    # 单机\n"
            "    host: 192.0.2.1\n"
            "    cluster:\n"
            "      # 集群\n"
            "      nodes: 192.0.2.2:6379\n"
            "api:\n"
            "  # 上游地址\n"
            "  base: ${ep-hosts.missing}/x\n", encoding="utf-8")

        rc, o = run(root, "V0.2.0")
        cats = {e["check"] for e in o.get("errors", [])}
        check("有 ERROR → exit 1 且 ok=False", rc == 1 and o.get("ok") is False)
        check("抓到 SQL 环境绑定物残留（schema 前缀 / STORAGE）", "SQL 环境绑定物" in cats)
        check("抓到明文凭据", "明文凭据" in cats)
        check("★ 抓到占位变量名撞名（全路径命名回检）", "占位变量名唯一性" in cats)
        check("抓到 ${a.b} 引用不可解析", "引用可解析" in cats)
        check("★ 抓到生效形态不唯一（判据绑全路径、非行文本）", "生效形态唯一" in cats)
        check("抓到失效相对链接", "相对链接" in cats)

        # ── 干净基线：不得误报 ──
        ok = root / "docs/deployment/V0.3.0"
        (ok / "sql/全量").mkdir(parents=True)
        (ok / "配置文件/全量/nacos").mkdir(parents=True)
        # 双轨场景导航是约定 37「两套绝不叠加」的唯一载体，机器门要求写明两条互斥路径
        (ok / "00_索引.md").write_text(
            "# 索引\n\n- 全新部署（从零搭）→ 只执行 sql/全量/ + 配置文件/全量/\n"
            "- 升级已有环境 → 只执行 sql/增量/ + 配置文件/增量/\n（两套绝不叠加执行）\n"
            # 本夹具刻意不产增量轨 → 按约定 37.5-7 必须显式声明零变更，
            #   否则「本版真没改」与「压根没产增量轨」在产物上同形（新 check_increment_presence 判 ERROR）
            "\n本版无增量：配置中心该区间无变更记录，SQL 亦无 DDL。\n",
            encoding="utf-8")
        (ok / "sql/全量/00_索引.md").write_text(
            "# 全量索引\n\n导出源：192.0.2.10:3306 / schema `app_prod`（应用实际连接）\n"
            "本版无剔除项（已交叉核对）\n"
            # 只读采集方式：G-RELEASE-2「全程只读」半条的可复核落点
            "DDL 经 INFORMATION_SCHEMA 元数据视图只读导出\n", encoding="utf-8")
        (ok / "配置文件/全量/00_索引.md").write_text(
            "# 配置全量索引\n\n导出源：配置中心 nacos@192.0.2.10:8848 / namespace `prod`\n"
            "本版无剔除项（已交叉核对）\n"
            "配置经配置中心只读 API 拉取\n", encoding="utf-8")
        (ok / "sql/全量/01_建表-用户.sql").write_text(
            "CREATE TABLE IF NOT EXISTS T_USER (ID VARCHAR(64));\n", encoding="utf-8")
        (ok / "配置文件/全量/nacos/app.yml").write_text(
            "sso:\n"
            "  # 应用认证码 · 换环境必改\n"
            "  auth-code: ${SSO_AUTH_CODE:__FILL_ME__}\n"
            "  kop:\n"
            "    # 知识库认证码 · 与应用认证码不同值\n"
            "    auth-code: ${SSO_KOP_AUTH_CODE:__FILL_ME__}\n"
            "spring:\n"
            "  redis:\n"
            "    # 单机形态生效；集群形态见下方注释段（切换须删 database、开拓扑刷新）\n"
            "    host: 192.0.2.1\n"
            "    # cluster:\n"
            "    #   nodes: 192.0.2.2:6379\n", encoding="utf-8")

        rc, o = run(root, "V0.3.0")
        check("干净基线 → exit 0 且零 ERROR",
              rc == 0 and o.get("ok") is True and o["counts"]["error"] == 0)
        check("★ 被整段注释的非生效形态不算「同时生效」", o["counts"]["error"] == 0)

        # ── 全量轨缺失是 ERROR：「本版零变更」不是不产全量的理由 ──
        empty = root / "docs/deployment/V0.4.0"
        empty.mkdir(parents=True)
        (empty / "00_索引.md").write_text("# 索引\n", encoding="utf-8")
        rc, o = run(root, "V0.4.0")
        check("★ 缺全量轨 → ERROR（零变更版本同样要产全量）",
              rc == 1 and "结构完整性" in {e["check"] for e in o["errors"]})

        # ── ★ 两轨落位：旧结构（增量散落在 sql/ 根）必须被抓 ──
        legacy = root / "docs/deployment/V0.5.0"
        (legacy / "sql/全量").mkdir(parents=True)
        (legacy / "配置文件/全量").mkdir(parents=True)
        (legacy / "00_索引.md").write_text("# 索引\n", encoding="utf-8")
        (legacy / "sql/全量/00_索引.md").write_text("# 全量索引\n", encoding="utf-8")
        (legacy / "配置文件/全量/00_索引.md").write_text("# 配置全量索引\n", encoding="utf-8")
        (legacy / "sql/全量/01_建表.sql").write_text(
            "CREATE TABLE IF NOT EXISTS T (ID VARCHAR(1));\n", encoding="utf-8")
        (legacy / "配置文件/全量/app.yml").write_text("a:\n  # x\n  b: 1\n", encoding="utf-8")
        (legacy / "sql/01_旧增量.sql").write_text("-- legacy\n", encoding="utf-8")
        (legacy / "配置文件/配置项清单.md").write_text("# 清单\n", encoding="utf-8")
        rc, o = run(root, "V0.5.0")
        msgs = " ".join(e["msg"] for e in o["errors"])
        check("★ 增量散落在 sql/ 根 → ERROR（约定 37 两轨落位）",
              rc == 1 and "sql/01_旧增量.sql" in msgs)
        check("★ 配置项清单滞留 配置文件/ 根 → ERROR",
              "配置文件/配置项清单.md" in msgs)

        # ── ★ nginx/compose/k8s 属【全量轨】（约定 37.2）：凭据要抓、编排样板不要求逐行注释 ──
        rt = root / "docs/deployment/V0.6.0"
        (rt / "sql/全量").mkdir(parents=True)
        (rt / "配置文件/全量").mkdir(parents=True)
        (rt / "00_索引.md").write_text("# 索引\n", encoding="utf-8")
        (rt / "sql/全量/00_索引.md").write_text("# 全量索引\n", encoding="utf-8")
        (rt / "配置文件/全量/00_索引.md").write_text("# 配置全量索引\n", encoding="utf-8")
        (rt / "sql/全量/01_建表.sql").write_text(
            "CREATE TABLE IF NOT EXISTS T (ID VARCHAR(1));\n", encoding="utf-8")
        # 本版加 WS/SSE 的典型 nginx：一处明文 Basic 凭据 + 一处已占位化
        (rt / "配置文件/全量/nginx.conf").write_text(
            "server {\n"
            "  location /ws {\n"
            '    proxy_set_header Authorization "Basic YWRtaW46cGFzcw==";\n'
            "  }\n"
            "  location /sse {\n"
            "    proxy_set_header X-Api-Key ${NGINX_SSE_API_KEY:__FILL_ME__};\n"
            "    proxy_buffering off;\n"
            "  }\n"
            "}\n", encoding="utf-8")
        # 编排样板：全裸行，不该产生 注释完备性 WARN
        (rt / "配置文件/全量/docker-compose.yml").write_text(
            "services:\n  app:\n    image: app:latest\n    restart: always\n", encoding="utf-8")
        rc, o = run(root, "V0.6.0")
        cred = [e for e in o["errors"] if e["check"] == "明文凭据"]
        check("★ nginx.conf 里的 Authorization Basic 明文凭据被抓（authorization 曾漏收）",
              rc == 1 and len(cred) == 1 and "nginx.conf" in cred[0]["msg"])
        check("★ 已 ${...:__FILL_ME__} 占位的那行不误报", len(cred) == 1)
        check("★ compose/k8s 编排样板豁免『注释完备性』（否则逐行噪音）",
              not [w for w in o["warns"] if w["check"] == "注释完备性"])

        # ── ★ 增量极简度（约定 37.5-6）：增量文档只讲改了什么，不做第二份论述 ──
        ts = root / "docs/deployment/V0.7.0"
        (ts / "sql/全量").mkdir(parents=True)
        (ts / "配置文件/全量").mkdir(parents=True)
        (ts / "配置文件/增量").mkdir(parents=True)
        (ts / "00_索引.md").write_text(
            "# 索引\n\n- 全新部署 → sql/全量/ + 配置文件/全量/\n- 升级已有环境 → sql/增量/ + 配置文件/增量/\n"
            # 本夹具只有配置增量、没有 SQL 增量（合法的「本版无 DDL」），
            #   按约定 37.5-7 必须显式声明零，否则与「压根没产 SQL 增量轨」同形
            "\n本版 SQL 无增量：配置中心该区间仅配置变更，无 DDL。\n",
            encoding="utf-8")
        (ts / "sql/全量/00_索引.md").write_text(
            "# 全量索引\n\n导出源：192.0.2.10:3306 / schema `app_prod`\n本版无剔除项（已交叉核对）\n"
            "DDL 经 INFORMATION_SCHEMA 元数据视图只读导出\n", encoding="utf-8")
        (ts / "配置文件/全量/00_索引.md").write_text(
            "# 配置全量索引\n\n导出源：nacos@192.0.2.10:8848 / namespace `prod`\n本版无剔除项（已交叉核对）\n"
            "配置经配置中心只读 API 拉取\n", encoding="utf-8")
        (ts / "sql/全量/01_建表.sql").write_text(
            "CREATE TABLE IF NOT EXISTS T (ID VARCHAR(1));\n", encoding="utf-8")
        (ts / "配置文件/全量/app.yml").write_text("a:\n  # x\n  b: 1\n", encoding="utf-8")
        inc = ts / "配置文件/增量/配置项清单.md"
        inc.write_text(
            "# 变更\n\n## 1. 变更总表\n"
            "| # | 配置项 | 变更类型 |\n|---|---|---|\n| 1 | sso.ws-timeout | 新增 |\n\n"
            "## 2. 新增\n```yaml\nsso:\n"
            "  ws-timeout: 60   # 本版新增 WebSocket 长连接超时时间，因为默认 30 秒在弱网下会断\n"
            "```\n", encoding="utf-8")
        rc, o = run(root, "V0.7.0")
        terse = [w for w in o["warns"] if w["check"] == "增量极简度"]
        check("★ 增量文档里的 Markdown 表格被抓（两处对照必然漂移）",
              any("表格" in w["msg"] for w in terse))
        check("★ 行内注释超 20 字符被抓", any("字符 > 20" in w["msg"] for w in terse))
        check("极简度只报 WARN 不阻断发布", rc == 0)

        inc.write_text(
            "# 变更\n\n> 判定依据见 `../全量/00_索引.md`。\n\n"
            "## 新增\n```yaml\nsso:\n  ws-timeout: 60   # WS 长连接超时\n"
            "  api-key: x       # 必填·敏感\n```\n\n## 删除\n无\n", encoding="utf-8")
        rc, o = run(root, "V0.7.0")
        check("★ 精简后零 WARN（代码块 + ≤20 字符注释是合规形态）",
              rc == 0 and not [w for w in o["warns"] if w["check"] == "增量极简度"])

        rc, o = run(root, "V9.9.9")
        check("版本目录不存在 → exit 2 且不瞎猜", rc == 2 and o.get("ok") is False)


def test_freeze_contract():
    """[42] 冻结字段写入契约：站点齐备 + 枚举合法 + 无幽灵值。

    7×24 最高频的失败路径是「部署就绪探针超时」，其冻结此前只写 needs_human + 一个
    零读者的私有字段 —— 解冻判据恒假、`freeze_reason` 落 unknown 不进任何解冻分支，
    净效果是这一版永久停摆且零告警。本组守住"缺一即冻死"这条契约。
    """
    print("\n[42] 冻结字段写入契约")
    repo = Path(__file__).resolve().parents[3]
    out = subprocess.run([sys.executable, str(repo / ".aidp/scripts/check_freeze_contract.py"),
                          "--root", str(repo), "--json"], capture_output=True, text=True)
    d = json.loads(out.stdout)
    # ★ 判据拆开看：四件套一条不许缺（ERROR 必须为 0），而 #4 判据是**棘轮**——
    #   现存 23 处「只写字段没发卡」登记在 CARD4_KNOWN_OPEN 里判 WARN、只能变短。
    #   ⛔ 别把两者合成 `not d["findings"]`：那会让棘轮一上线就红，逼人把整道门关掉。
    _card4 = [f for f in d["findings"] if "#4" in f.get("detail", "")]
    _other = [f for f in d["findings"] if f not in _card4]
    check("本仓 0 ERROR（全部冻结站点四件套写齐）", d["passed"] and not [
        f for f in d["findings"] if f.get("level") == "ERROR"])
    check("四件套判据零 WARN（#4 棘轮除外）", not _other)
    check("★ #4 棘轮只减不增（当前 %d 处待修，⛔ 新增站点会落 ERROR）" % len(_card4),
          len(_card4) <= 23)
    check("枚举从 rationale 权威表解析（≥12 个，不硬编码进脚本）", len(d.get("enum") or []) >= 12)
    check("★ probe-timeout 在枚举内且无「零写入者」告警（7×24 最高频失败路径）",
          "probe-timeout" in (d.get("enum") or [])
          and not any("probe-timeout" in f.get("detail", "") for f in d["findings"]))

    # 变异：抽掉一处 aiauto_frozen_at → 解冻判据恒假，必须被拦
    tmp = Path(tempfile.mkdtemp())
    shutil.copytree(repo / ".aidp", tmp / ".aidp",
                    ignore=shutil.ignore_patterns("skills", "__pycache__"))
    f = tmp / ".aidp/flows/sprint-autopilot/phase-3-6.md"
    t = f.read_text(encoding="utf-8")
    t2 = t.replace("`aiauto_frozen_at=@now` + `freeze_reason=cicd-auto-trigger-off`",
                   "`freeze_reason=cicd-auto-trigger-off`", 1)
    check("变异夹具已生效（否则本条变异测试是空跑）", t2 != t)
    f.write_text(t2, encoding="utf-8")
    out2 = subprocess.run([sys.executable, str(repo / ".aidp/scripts/check_freeze_contract.py"),
                           "--root", str(tmp), "--json"], capture_output=True, text=True)
    check("★ 变异：抽掉 aiauto_frozen_at → 被拦（否则该版冻结后永不解冻）",
          not json.loads(out2.stdout)["passed"])
    shutil.rmtree(tmp, ignore_errors=True)


def test_skill_gate_list():
    """[52] SKILL 阻断名单棘轮：上游声明「不另立名单」后，命令端不得再抄编号。

    真实失效（auto-test-runner 升级）：SKILL 把不可豁免集合从 4 条扩到 9 条，命令端仍写
    「维度 1/3/5/7 任一不通过 → 阻断」，于是维度 2「驱动适配层四能力完备」失败只告警不阻断——
    驱动四能力残缺时那一轮的"全绿"结论根本无效，build 却被当成通过关闭。
    ⚠️ 那次升级里两道既有 SKILL 引用门都返回 0 findings，本门是唯一能抓它的。
    """
    print("\n[52] SKILL 阻断名单棘轮")
    repo = Path(__file__).resolve().parents[3]
    S = str(repo / ".aidp/scripts/check_skill_gate_list.py")
    out = subprocess.run([sys.executable, S, "--root", str(repo), "--json"],
                         capture_output=True, text=True)
    d = json.loads(out.stdout)
    check("本仓 0 命中（棘轮基线归零）", d.get("passed") and not d.get("findings"))
    check("★ 判据由上游声明驱动（有 SKILL 声明过「不另立名单」才适用）", d.get("applicable"))

    # 变异①：把修复前那句写回去 → 必须被拦
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".aidp/skills/auto-test-runner/references").mkdir(parents=True)
    (tmp / ".aidp/flows/x").mkdir(parents=True)
    (tmp / ".aidp/skills/auto-test-runner/references/quality-review-checklist.md").write_text(
        "不可豁免 = 凡标 Critical 的一律不可豁免(**判据就是标记本身,不另立名单**)\n", encoding="utf-8")
    bad = ("> 其中**维度 1（两层解耦）/ 3（状态机无残留）/ 5（证据达标）/ 7（报告完整）"
           "不可豁免**（见 quality-review-checklist.md）\n")
    (tmp / ".aidp/flows/x/a.md").write_text(bad, encoding="utf-8")
    o1 = subprocess.run([sys.executable, S, "--root", str(tmp), "--json"],
                        capture_output=True, text=True)
    check("★ 变异：写死「维度 1（…）/ 3（…）/ 5（…）/ 7（…）」被拦（编号间夹括注也要抓到）",
          not json.loads(o1.stdout)["passed"])

    # 变异②：改成指向 SKILL 判据本身的写法 → 必须放行
    (tmp / ".aidp/flows/x/a.md").write_text(
        "> 不可豁免范围以清单的 Critical 标记为准（见 quality-review-checklist.md），命令端不另列名单\n",
        encoding="utf-8")
    o2 = subprocess.run([sys.executable, S, "--root", str(tmp), "--json"],
                        capture_output=True, text=True)
    check("★ 变异：改为指针写法后放行（否则本门会逼人把正确写法也改坏）",
          json.loads(o2.stdout)["passed"])

    # 变异③：上游没声明「不另立名单」→ 整门不适用（不越权管别人的编号）
    (tmp / ".aidp/skills/auto-test-runner/references/quality-review-checklist.md").write_text(
        "维度清单见下\n", encoding="utf-8")
    (tmp / ".aidp/flows/x/a.md").write_text(bad, encoding="utf-8")
    o3 = subprocess.run([sys.executable, S, "--root", str(tmp), "--json"],
                        capture_output=True, text=True)
    check("★ 上游未声明「不另立名单」→ 本门不适用（判据来自上游，不自行扩张管辖）",
          not json.loads(o3.stdout).get("applicable"))
    shutil.rmtree(tmp, ignore_errors=True)


def test_terminology_and_conv30():
    """[43] 术语一致性（User Story 禁用）+ 约定 30 正文体检棘轮。"""
    print("\n[43] 术语一致性 + 约定 30 正文体检")
    repo = Path(__file__).resolve().parents[3]

    o1 = subprocess.run([sys.executable, str(repo / ".aidp/scripts/check_banned_terminology.py"),
                         "--root", str(repo), "--json"], capture_output=True, text=True)
    d1 = json.loads(o1.stdout)
    check("本仓 0 处禁用术语（User Story / 用户故事 / US-NNN）", d1["passed"])
    check("巡检面覆盖 commands+agents+flows+reference+rules+docs-init（≥100 份）",
          d1["scanned"] >= 100)
    check("★ 「正在定义该禁令」的行被豁免（version-auditor B-02 判据行须原样保留）",
          "命中即标" in (repo / ".aidp/agents/version-auditor.md").read_text(encoding="utf-8"))

    o2 = subprocess.run([sys.executable, str(repo / ".aidp/scripts/check_convention30_prose.py"),
                         "--root", str(repo), "--json"], capture_output=True, text=True)
    d2 = json.loads(o2.stdout)
    check("约定 30 无新增历史叙事（存量已冻 baseline）", d2["passed"])
    check("★ rationale.md / invariants.md 豁免（根因档案本就该记「为什么」）",
          not any(n["file"].endswith(("rationale.md", "invariants.md"))
                  for n in (d2.get("new") or [])))
    check("约定 30 范围已含 flows/reference/rules（契约正文的大头在那里）",
          "`{{AIDP_HOME}}/flows/**`" in (repo / ".aidp/AIDP-AGENTS.md").read_text(encoding="utf-8"))


def test_ledger_format_tolerance():
    """[45] 台账多态识别 + 格式漂移告警 + 已级联未清理（实际项目中实测）。

    格式约定只写在 reference 详规里，写入侧（各 Sprint 的 agent）看不到，自然挑最顺手的写法
    ——实测 20 条条目全用 Markdown 表格，而 pending_cascade 当时只认一行式与 `### C-NNN`：
    `stale` 恒 0 → 收口点 1 从不触发 → 台账无限增长，**且完全静默**（退出码 0、字段一片干净）。
    「没有待级联」与「根本没看见」表现完全一样，正是本轮反复出现的同一类缺陷模式。
    """
    print("\n[45] 台账多态识别 + 格式漂移告警")
    sys.path.insert(0, os.path.dirname(HERE))
    import commit_gate as HG

    def mk(body):
        d = Path(tempfile.mkdtemp())
        (d / "docs/requirements/V0.12.2/研发需求").mkdir(parents=True)
        (d / "docs/requirements/V0.12.2/研发需求/_开发期需求增量.md").write_text(body, encoding="utf-8")
        return str(d)

    TODAY = "2026-09-01"
    tbl = ("# 开发期变更台账 — V0.12.2\n\n"
           "| 编号 | 日期 | 类型 | 变更内容 | 级联目标 |\n|---|---|---|---|---|\n"
           "| C-036-01 | 2026-08-31 | 事实订正 | 导出去掉 XLSX | 详设 §4.2 |\n"
           "| C-039-05 | 2026-08-31 | 新增字段 | 企业列表加筛选 | 接口设计 |\n"
           "| C-040-01 | 2026-09-01 | 新增 | 今天刚记的 | 详设 |\n")
    r = HG.pending_cascade(mk(tbl), TODAY)
    check("★ 下游真实形态（Markdown 表格 + 带子编号 C-036-01）被识别", r["total"] == 3)
    check("★ 表格式的 stale 按第 2 列日期算（今天的不计）", r["stale"] == 2)

    one = ("# 台账\n\n## 待级联\n\n"
           "- C-008 · 08-31 16:05 · 导出去掉 XLSX · sprint-012\n"
           "- C-009 · 09-01 10:00 · 今天的 · sprint-012\n")
    r = HG.pending_cascade(mk(one), TODAY)
    check("一行式旧格式不回归（total=2 stale=1）", (r["total"], r["stale"]) == (2, 1))

    prose = "# 台账\n\n本轮变更：\n\n改动一：导出去掉 XLSX，2026-08-31，需级联详设。\n改动二：企业列表加筛选。\n"
    r = HG.pending_cascade(mk(prose), TODAY)
    check("★ 认不出的格式 → unparsed 非空（根治点：没有它，格式漂移能静默攒到几十条）",
          r["total"] == 0 and bool(r["unparsed"]))

    r = HG.pending_cascade(mk("# 开发期变更台账 — V0.12.2\n\n## 待级联\n\n"), TODAY)
    check("★ 零误报：空台账（只有标题）不报 unparsed", not r["unparsed"])

    r = HG.pending_cascade(mk(tbl + "| ~~C-035-01~~ | 2026-08-30 | 旧 | 已完成 | ✅已级联 |\n"), TODAY)
    check("★ 已级联却没删被统计（只统计未级联发现不了「办完了没打扫」）",
          r["cascaded_not_cleaned"] >= 1)

    # ★ 标记不替代删除：打过 LEDGER-ARCHIVED 的台账【照常解析计数】，并另行点名
    r = HG.pending_cascade(mk("<!-- LEDGER-ARCHIVED -->\n" + tbl), TODAY)
    check("★ 打了存档标记也照常计数（⛔ 标记不替代删除，跳过=给了条静默出路）",
          r["total"] > 0 and not r["unparsed"])
    check("★ 并另行点名 archived_not_deleted",
          len(r.get("archived_not_deleted") or []) == 1)

    # 模板须真实存在且是一行式（写入侧照它拷，模板本身写成表格就前功尽弃）
    tpl = Path(__file__).resolve().parents[3] / ".aidp/templates/_开发期族增量.md"
    check("族增量册模板已下发（四族共用骨架）", tpl.is_file())
    tt = tpl.read_text(encoding="utf-8") if tpl.is_file() else ""
    check("★ 模板给的是一行式示例、且写明「别改成表格」", "- C-008 · 08-27" in tt and "为什么不用表格" in tt)
    check("★ 模板写明溯源取舍 + 标记不替代删除", "LEDGER-ARCHIVED" in tt and "必须删除" in tt)


def test_case_baseline_binding():
    """[46] 收尾门 3n：测试结果挂靠用例基线（约定 33）。

    实证：本轮用自造的 P01~P05 编号记测试证据，12 条设计用例里 8 条挂空、1 条 ID 张冠李戴，
    而收尾门 15 项全绿放行——约定 33 要防的「基线产出即沉睡」正是这个形态。
    """
    print("\n[46] 收尾门 3n 测试结果挂靠用例基线")
    gate = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")

    def scene(case_ids, baseline_ids):
        root = Path(tempfile.mkdtemp())
        d = root / "docs/reports/V0.1/AI执行报告/data"
        d.mkdir(parents=True)
        (d / "V0.1_build1001.js").write_text(
            "window.__A__=window.__A__||[];window.__A__.push("
            + json.dumps({"cases": [{"id": i} for i in case_ids]}, ensure_ascii=False) + ");",
            encoding="utf-8")
        tdir = root / "docs/testing/V0.1/正式用例"
        tdir.mkdir(parents=True)
        (tdir / "01_用例.md").write_text(
            "\n".join(f"#### 用例 {i} 说明" for i in baseline_ids), encoding="utf-8")
        (root / "memory").mkdir()
        (root / "memory/.sprint-autopilot-baseline.json").write_text(
            json.dumps({"versions": {"V0.1": {"builds": [{"build": "V0.1_build1001"}]}}}),
            encoding="utf-8")
        cp = subprocess.run([sys.executable, gate, "check", "--version", "V0.1",
                             "--build", "V0.1_build1001", "--stage", "final",
                             "--will-browser-test", "1",
                             "--repo-root", str(root), "--notify", "0"],
                            capture_output=True, text=True)
        shutil.rmtree(root, ignore_errors=True)
        return cp.stdout

    base12 = [f"TC-U-{i:03d}" for i in range(1, 13)]
    out = scene(["P01", "P02", "P03", "P04", "P05"], base12)
    check("★ 自造编号 P01~P05 与基线交集为 0 → FAIL（下游实测形态）",
          "交集为 0" in out or "自造编号" in out)

    out = scene(base12, base12)
    check("全覆盖 → 通过", "测试结果挂靠用例基线" in out and "交集为 0" not in out)

    out = scene(base12[:4], base12)
    check("★ 命中但 8/12 挂空（未覆盖率 67%）→ 告警而非阻断（本轮只跑部分用例是合法的）",
          "未覆盖" in out)

    out = scene(["TC-A-1"], [])
    check("★ 零误报：用例库无 TC-* 基线时跳过，不倒扣", "本项跳过" in out or "无 TC-* 基线" in out)


def test_subagent_cascade_contract():
    """[48] 子 Agent 派单契约：cascade_mode / dev_scale 必填（攒批唯一会整段失效的地方）。

    攒批的判定结果活在主链路 flow 里，子 Agent 读不到它 —— 只要派单简报直接罗列了待改文档
    清单，就等价于一次强制 `--cascade-now`：攒批在主链路上生效、在派单路径上 100% 失效。
    而口述累进恰恰既是最常派子 Agent 的路径、又是最需要攒批的路径。
    """
    print("\n[48] 子 Agent 派单契约（cascade_mode / dev_scale）")
    repo = Path(__file__).resolve().parents[3]
    led = (repo / ".aidp/reference/开发期族增量.md").read_text(encoding="utf-8")
    dev2 = (repo / ".aidp/flows/sprint-dev/phase-1-dev-2.md").read_text(encoding="utf-8")
    wb1 = (repo / ".aidp/flows/sprint-dev/postdev-writeback-1.md").read_text(encoding="utf-8")

    check("★ 单一信源有「子 Agent 执行时的派单契约」段", "子 Agent 执行时的派单契约" in led)
    check("契约把 cascade_mode / dev_scale 列为必填", "cascade_mode" in led and "dev_scale" in led)
    check("★ 契约内联了台账一行格式（子 Agent 读不到 reference 时的兜底）",
          "C-{NNN} · MM-DD HH:MM" in led)
    check("★ 契约明写 ledger 模式下不得罗列待改文档清单（罗列 = 强制 cascade-now）",
          "不得" in led and "待改文档清单" in led)

    check("★ 派单模板本体带这两个必填字段", "cascade_mode" in dev2 and "dev_scale" in dev2)
    check("派单模板指向单一信源、不复述契约（约定 21）",
          "开发期族增量.md" in dev2 and "此处不复述" in dev2)
    check("★ 步骤 3.8 就地提醒「本步若由子 Agent 执行」", "本步若由子 Agent 执行" in wb1)

    # 逐条目判定（请求 4）
    d2 = (repo / ".aidp/reference/约定细则-2.md").read_text(encoding="utf-8")
    check("★ 四级触发改为逐条目判定、不按整轮取最大值",
          "逐【变更条目】独立判定" in d2 and "不按整轮取最大值" in d2)
    check("★ 但给了防降级的判据（拿不准按高的算 + 看契约面变没变）",
          "按高的算" in d2 and "契约面" in d2)


def test_project_count_claims():
    """[49] 业务计数声明表的全库回扫（下游称本轮最大单项耗时）。"""
    print("\n[49] 业务计数声明表全库回扫")
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_count_claims as CC

    # ★ 一份文档里可以有**多张**声明表：上游已把口径从「全设计只准一张表」改为
    #   「多册各一张、增量另起一张」，而本项目 --ledger-cascade 是把多个业务主题
    #   就地改进同一份内容主文档 —— 多张表落在同一文件正是常态。
    #   原实现用 `search` 只取第一张，漏读的声明不报错、只是从此不参与回扫（全绿）。
    _mt = Path(tempfile.mkdtemp())
    (_mt / "d").mkdir()
    _tbl = ("\n## 业务计数声明表\n\n"
            "| 声明名 | 当前值 | 是否动态 | 权威出处 | 散落面正则 |\n"
            "| :- | :- | :- | :- | :- |\n")
    (_mt / "d/01_详细设计.md").write_text(
        "# 详细设计\n\n## 主题一\n" + _tbl + "| 告警类型数 | 8 | 静态 | `AlertTypeEnum` | `支持\\s*\\d+\\s*种` |\n"
        "\n## 主题二\n" + _tbl + "| 角色数 | 5 | 静态 | `RoleEnum` | `共\\s*\\d+\\s*个角色` |\n",
        encoding="utf-8")
    _names = [c["name"] for c in CC._load_project_claims(str(_mt / "d"))]
    check("★ 同一文件的第二张声明表也被读到（原 search 只取第一张，漏读全绿）",
          "告警类型数" in _names and "角色数" in _names)
    shutil.rmtree(_mt, ignore_errors=True)
    repo = Path(__file__).resolve().parents[3]
    sc = str(repo / ".aidp/scripts/check_count_claims.py")

    d = Path(tempfile.mkdtemp())
    dd = d / "docs/design/detail/V1"; dd.mkdir(parents=True)
    td = d / "docs/testing/V1"; td.mkdir(parents=True)
    # ⚠️ 散落面列写的是正则，其 `|` 在 markdown 表格里只能写成 `\|`
    (dd / "01_详细设计.md").write_text(
        "# 详细设计\n\n### 业务计数声明表\n\n"
        "| 声明名 | 当前值 | 是否动态 | 权威出处 | 散落面 |\n|---|---|---|---|---|\n"
        "| 检测项数 | 13/14 | 是 | `Svc.ordered()` | 检测项\\|检测.{0,4}项 |\n"
        "| 导出格式数 | 3 | 否 | `ExportFormat` | 导出格式 |\n", encoding="utf-8")
    (td / "用例.md").write_text(
        "- 断言：检测项列表恰 14 行\n"
        "- 说明：检测项全集含 14 项（取值域说明，非计数断言）\n"
        "- 断言：导出格式共 5 项\n", encoding="utf-8")

    out = subprocess.run([sys.executable, sc, "--root", str(d), "--json",
                          "--project-claims", str(dd)], capture_output=True, text=True)
    r = json.loads(out.stdout)
    pf = r.get("project_findings") or []
    check("★ 声明表被解析出 2 条（表格转义竖线 `\\|` 不再把正则截断）", r.get("project_claims") == 2)
    check("★ 动态声明却写成「恰 14 行」→ 报出（必须改的计数断言）",
          any("恰 14 行" in f["detail"] for f in pf))
    check("★ 非动态声明数字对不上（3 vs 5）→ 报出",
          any("导出格式数" in f.get("claim", "") for f in pf))
    check("★ 零误报：「全集含 14 项」是取值域说明、不是计数断言 → 不报",
          not any("全集含 14 项" in f["detail"] for f in pf))
    check("★ 无声明表时整段跳过、不影响原有三类检查",
          (json.loads(subprocess.run([sys.executable, sc, "--root", str(d), "--json"],
                                     capture_output=True, text=True).stdout)
           .get("project_findings") == []))
    shutil.rmtree(d, ignore_errors=True)

    # 速查脚本：位置参数形态必须能被看出来（下游踩坑点）
    su = str(repo / ".aidp/scripts/scripts_usage.py")
    o = subprocess.run([sys.executable, su, "--root", str(repo), "check_sprint_numbering"],
                       capture_output=True, text=True).stdout
    check("★ 速查能显示位置子命令形态（{next,check}）", "next,check" in o or "{next" in o)


def test_conv30_baseline_key():
    """[51] 约定 30 棘轮的 baseline 键不含行号（否则插入无关内容会整批误报）。"""
    print("\n[51] 约定 30 棘轮键：内容指纹而非行号")
    repo = Path(__file__).resolve().parents[3]
    sc = str(repo / ".aidp/scripts/check_convention30_prose.py")
    # 端到端夹具：先造一条存量命中并冻进 baseline，再插入无关行制造行号漂移
    d = Path(tempfile.mkdtemp())
    shutil.copytree(repo / ".aidp/scripts", d / ".aidp/scripts",
                    ignore=shutil.ignore_patterns("__pycache__", "tests"))
    for sub in ("commands", "agents", "flows", "reference", "rules"):
        shutil.copytree(repo / ".aidp" / sub, d / ".aidp" / sub,
                        ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(repo / "docs/init", d / "docs/init")
    f = d / ".aidp/reference/约定细则-3.md"
    ls = f.read_text(encoding="utf-8").splitlines()
    ls.append("\n本段此前只有散文、现改为脚本。")
    f.write_text("\n".join(ls), encoding="utf-8")
    subprocess.run([sys.executable, sc, "--root", str(d), "--update-baseline"],
                   capture_output=True, text=True)
    base = (d / ".aidp/scripts/convention30-prose-baseline.txt").read_text(encoding="utf-8")
    rows = [l for l in base.splitlines() if l and not l.startswith("#")]
    check("夹具存量已冻进 baseline", len(rows) >= 1)
    check("★ 键里不含行号（`文件:标签:指纹` 三段、中间段不是纯数字）",
          all(not r.split(":")[1].strip().isdigit() for r in rows if r.count(":") >= 2))

    ls = f.read_text(encoding="utf-8").splitlines()
    ls.insert(4, "\n> 插入一段无关内容以制造行号漂移。")
    f.write_text("\n".join(ls), encoding="utf-8")
    out = subprocess.run([sys.executable, sc, "--root", str(d), "--json"],
                         capture_output=True, text=True)
    check("★ 插入无关内容致行号漂移 → 不误报新增（假红一多门就被忽略）",
          not (json.loads(out.stdout).get("new") or []))
    shutil.rmtree(d, ignore_errors=True)


def test_readme_three_tier_and_scan_noise():
    """README 三档判定（代码单元 / 导航枢纽 / 平铺叶子）+ 范围外扫描降噪。"""
    import importlib.util
    import readme_policy as RP
    print("【README 三档判定 + 扫描降噪】")
    root = Path(tempfile.mkdtemp())

    def mk(rel, files=(), dirs=()):
        base = root / rel
        base.mkdir(parents=True, exist_ok=True)
        for name in files:
            (base / name).write_text("x", encoding="utf-8")
        for name in dirs:
            (base / name).mkdir(parents=True, exist_ok=True)

    def dec(rel):
        return RP.is_readme_required_directory(root / rel, "layout1", root)

    # 1 非代码目录、0 子目录、仅 3 个文件
    mk("docs/deployment/tools/sso", files=("a.sql", "b.md", "c.sh"))
    d = dec("docs/deployment/tools/sso")
    check("① 平铺叶子不 required + reason=flat-leaf-directory",
          not d["required"] and d["reason"] == "flat-leaf-directory")
    # 2 非代码目录、4 个子目录
    mk("docs/deployment/tools", dirs=("A", "B", "C"))
    d = dec("docs/deployment/tools")
    check("② 4 子目录 → navigation-hub",
          d["required"] and d["reason"] == "navigation-hub"
          and d["is_navigation_hub"] and d["subdirectory_count"] == 4)
    # 3 非代码目录、1 个空子目录
    mk("docs/onlyempty", dirs=("sub",))
    check("③ 1 个空子目录不 required", not dec("docs/onlyempty")["required"])
    # 4 非代码目录、1 个子目录且子目录内有文件
    mk("docs/onlyfull/sub", files=("f.txt",))
    d = dec("docs/onlyfull")
    check("④ 1 个非空子目录 → navigation-hub（存在多级结构）",
          d["required"] and d["reason"] == "navigation-hub")
    # 5 非代码目录、0 子目录但文件很多
    mk("docs/flatmany", files=tuple(f"f{i}.md" for i in range(200)))
    check("⑤ 200 个文件 0 子目录仍不 required", not dec("docs/flatmany")["required"])

    # 6-8 代码类不得回归
    mk("code/web/src/components", files=("a.vue",))
    (root / "code/web/package.json").write_text("{}", encoding="utf-8")
    mk("code/server/ec-common/ec-common-core/src", files=("A.java",))
    (root / "code/server/pom.xml").write_text(
        "<packaging>pom</packaging><modules><module>ec-common</module></modules>", encoding="utf-8")
    (root / "code/server/ec-common/pom.xml").write_text(
        "<packaging>pom</packaging><modules><module>ec-common-core</module></modules>", encoding="utf-8")
    (root / "code/server/ec-common/ec-common-core/pom.xml").write_text("<project/>", encoding="utf-8")
    mk("code/frontend/app", files=("package.json",))
    mk("code/backend/api", files=("pom.xml",))
    check("⑥ code/web 存量布局前端根 required", dec("code/web")["required"])
    check("⑦ code/server 及 Maven 子模块 required",
          dec("code/server")["required"]
          and dec("code/server/ec-common")["required"]
          and dec("code/server/ec-common/ec-common-core")["required"])
    check("⑧ code/frontend|backend 子项目根 required",
          dec("code/frontend/app")["required"] and dec("code/backend/api")["required"])
    check("★ 代码树内部多子目录不得升级为导航枢纽",
          not dec("code/web/src")["required"]
          and dec("code/web/src")["reason"] == "code-tree-internal")

    # 10 显式 README_REQUIRED 的单层目录
    (root / "memory").mkdir(exist_ok=True)
    (root / "memory/.sprint-autopilot-baseline.json").write_text(
        json.dumps({"project_state": {"README_REQUIRED": ["docs/deployment/tools/sso"]}}), encoding="utf-8")
    d = dec("docs/deployment/tools/sso")
    check("⑩ README_REQUIRED 优先于自动判据",
          d["required"] and d["reason"] == "explicit-README_REQUIRED")
    (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps({}), encoding="utf-8")

    # 11-12 扫描：node_modules 噪音 + 存量范围外 README 保留
    pnpm = root / "code/web/node_modules/.pnpm/lodash@4/node_modules/lodash"
    pnpm.mkdir(parents=True, exist_ok=True)
    (pnpm / "README.md").write_text("third party", encoding="utf-8")
    out_scope = root / "code/web/src/README.md"
    out_scope.write_text("用户自有说明", encoding="utf-8")
    findings = RP.scan_out_of_scope_readmes(root, "layout1")
    paths = [item["path"] for item in findings]
    check("⑫ node_modules 下 README 命中数为 0",
          not any("node_modules" in item for item in paths))
    check("⑪ 存量范围外 README 被报告且文件保留",
          "code/web/src/README.md" in paths and out_scope.is_file()
          and out_scope.read_text(encoding="utf-8") == "用户自有说明")
    lines = RP.format_out_of_scope_report(findings)
    check("扫描输出先给汇总行", lines[0].startswith(f"README_OUT_OF_SCOPE: {len(findings)} 处"))
    check("扫描明细带 preserve-and-report", any("preserve-and-report" in x for x in lines[1:]))
    check("N=0 明确打印无范围外 README",
          RP.format_out_of_scope_report([])[0].endswith("（无范围外 README）"))
    dist = root / "code/web/dist/assets"
    dist.mkdir(parents=True, exist_ok=True)
    (dist / "README.md").write_text("build output", encoding="utf-8")
    backup = root / "code/.aidp-backup-20260101/web"
    backup.mkdir(parents=True, exist_ok=True)
    (backup / "README.md").write_text("backup", encoding="utf-8")
    paths2 = [item["path"] for item in RP.scan_out_of_scope_readmes(root, "layout1")]
    check("dist/ 与 .aidp-backup-* 不进扫描",
          not any("dist/" in x or ".aidp-backup-" in x for x in paths2))

    # git 跟踪过滤：仓库内未跟踪的 README 不报
    repo = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", str(repo)], check=False, capture_output=True)
    (repo / "code/web/src").mkdir(parents=True)
    (repo / "code/web/package.json").write_text("{}", encoding="utf-8")
    (repo / "code/web/src/README.md").write_text("untracked", encoding="utf-8")
    untracked = [i["path"] for i in RP.scan_out_of_scope_readmes(repo, "layout1")]
    check("未被 git 跟踪的 README 不报", "code/web/src/README.md" not in untracked)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=False, capture_output=True)
    tracked = [i["path"] for i in RP.scan_out_of_scope_readmes(repo, "layout1")]
    check("已跟踪的范围外 README 仍报", "code/web/src/README.md" in tracked)


    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(repo, ignore_errors=True)


def test_cascade_residue_gate():
    """约定 22 口径残留门：旧口径仍作生效规则 = 真残留；订正留痕必须放行。"""
    print("【口径残留门】")
    script = str(Path(HERE).parents[0] / "check_cascade_residue.py")

    def mkproj(req_body, case_body="# 用例\n正常内容\n"):
        root = Path(tempfile.mkdtemp())
        for rel in ("docs/requirements/V0.1.0/研发需求", "docs/design/detail/V0.1.0",
                    "docs/plans/V0.1.0", "docs/testing/V0.1.0/研发自测"):
            (root / rel).mkdir(parents=True)
        (root / "docs/requirements/V0.1.0/研发需求/01_研发需求.md").write_text(
            req_body, encoding="utf-8")
        (root / "docs/testing/V0.1.0/研发自测/01_用例.md").write_text(case_body, encoding="utf-8")
        return root

    def gate(root, *extra):
        cp = subprocess.run([sys.executable, script, "--root", str(root),
                             "--version", "V0.1.0", "--json", *extra],
                            capture_output=True, text=True)
        try:
            return cp.returncode, json.loads(cp.stdout)
        except json.JSONDecodeError:
            return cp.returncode, {"_raw": cp.stdout + cp.stderr}

    # 正向：旧口径作为生效规则残留在字段处置表 + 用例断言
    r = mkproj("# 需求\n\n## 字段处置表\n\n| total | 不向用户解释 |\n",
               "# 用例\n- TC-45：断言页面不向用户解释统计范围。\n")
    rc, d = gate(r, "--old", "不向用户解释", "--new", "列级范围说明")
    check("真残留检出 exit 2", rc == 2)
    check("两处真残留都报出（需求 + 用例）", len(d.get("residues", [])) == 2)
    check("报出文件:行号", all(x.get("line") for x in d.get("residues", [])))

    # ★ 回归：上下文扫描【遇标题即止】。后方紧跟 `## 变更历史` 不得把真残留吞成留痕——
    #   这是本门最坏的失效形态：门写太宽不只产噪音，是让真残留隐形。
    r2 = mkproj("# 需求\n\n## 字段处置表\n\n| total | 不向用户解释 |\n\n"
                "## 变更历史\n\n- 原口径「不向用户解释」已作废。\n")
    rc2, d2 = gate(r2, "--old", "不向用户解释", "--new", "列级范围说明")
    check("★ 后方章节的留痕词不得掩盖表内真残留", rc2 == 2 and len(d2["residues"]) == 1)
    check("★ 作废声明本身仍判为留痕、不误报", len(d2["annotated"]) == 1)

    # 负向：只剩订正留痕 → 放行
    r3 = mkproj("# 需求\n\n## 变更历史\n\n- 原口径「不向用户解释」已作废，改为列级范围说明。\n")
    rc3, d3 = gate(r3, "--old", "不向用户解释", "--new", "列级范围说明")
    check("纯订正留痕 exit 0", rc3 == 0 and not d3["residues"] and d3["annotated"])

    # 族增量册是过程记录、必然含旧口径，不扫它（扫了就是恒定噪音）
    r4 = mkproj("# 需求\n正常\n")
    (r4 / "docs/requirements/V0.1.0/研发需求/_开发期需求增量.md").write_text(
        "- C-001 · 09-04 10:00 · 把「不向用户解释」改成列级范围说明 · sprint-001\n",
        encoding="utf-8")
    rc4, d4 = gate(r4, "--old", "不向用户解释")
    check("族增量册不参与扫描", rc4 == 0 and not d4["residues"])

    # 新口径落地分布只提示、不进退出码（有的口径本就不涉及某族，硬判会把门变噪音）
    rc5, d5 = gate(r4, "--old", "不存在的旧口径", "--new", "同样不存在的新口径")
    check("新口径 0 命中只提示不改退出码", rc5 == 0 and d5["missing_new_families"])

    # fail-closed：版本目录一个都没有 → 不许静默判过
    rc6, d6 = gate(r4, "--old", "x")
    rc6b = subprocess.run([sys.executable, script, "--root", str(r4), "--version", "V9.9.9",
                           "--old", "x", "--json"], capture_output=True, text=True).returncode
    check("版本目录不存在 fail-closed exit 1", rc6b == 1)
    # 未知 scope 同样拒绝，而不是当成"全扫"
    rc7 = subprocess.run([sys.executable, script, "--root", str(r4), "--version", "V0.1.0",
                          "--old", "x", "--scope", "nosuch"], capture_output=True, text=True).returncode
    check("未知 --scope exit 1", rc7 == 1)
    for d in (r, r2, r3, r4):
        shutil.rmtree(d, ignore_errors=True)


def test_version_identifier_inherited_pom_note():
    """多模块 Maven：继承版本按设计不计落点，但【必须说出来】——
    「扫到的都对齐」与「全都对齐」在措辞上不可混同。"""
    print("【版本标识 · 继承 pom 透明化】")
    script = str(Path(HERE).parents[0] / "check_version_identifier.py")
    root = Path(tempfile.mkdtemp())
    app = root / "code/backend/app"
    (app / "mod-a").mkdir(parents=True)
    (app / "mod-b").mkdir(parents=True)
    (app / "pom.xml").write_text(
        '<project xmlns="http://maven.apache.org/POM/4.0.0"><groupId>c.x</groupId>'
        '<artifactId>app</artifactId><version>0.1.0</version></project>', encoding="utf-8")
    for m in ("mod-a", "mod-b"):
        (app / m / "pom.xml").write_text(
            '<project xmlns="http://maven.apache.org/POM/4.0.0"><parent><groupId>c.x</groupId>'
            f'<artifactId>app</artifactId><version>0.1.0</version></parent>'
            f'<artifactId>{m}</artifactId></project>', encoding="utf-8")
    res = VI.run(str(root), "V0.1.0", ["code", "src", "backend", "frontend"])
    check("继承型 pom 不计落点（口径不变）", res["scanned"] == 1)
    check("★ 但被记录下来供输出交代", len(res.get("inherited_poms", [])) == 2)
    cp = subprocess.run([sys.executable, script, "--root", str(root), "--version", "V0.1.0"],
                        capture_output=True, text=True)
    out = cp.stdout + cp.stderr
    check("OK 措辞限定为「已扫落点」而非笼统「一致」", "已扫落点" in out)
    check("输出交代继承 pom 需一并改", "parent" in out and "反应堆" in out)
    shutil.rmtree(root, ignore_errors=True)


def test_cascade_obligation_gate():
    """约定 22 义务登记门：归档写下的级联义务，必须有台账这个机器可扫载体。"""
    print("【约定 22 义务登记门】")
    script = str(Path(HERE).parents[0] / "check_cascade_obligation.py")

    def mkproj(archive_text, ledger_text=None):
        root = Path(tempfile.mkdtemp())
        (root / "memory/V0.1.0/alice/sprints").mkdir(parents=True)
        (root / "docs/requirements/V0.1.0/研发需求").mkdir(parents=True)
        (root / "memory/V0.1.0/alice/sprints/sprint-045.md").write_text(
            archive_text, encoding="utf-8")
        if ledger_text is not None:
            (root / "docs/requirements/V0.1.0/研发需求/_开发期需求增量.md").write_text(
                ledger_text, encoding="utf-8")
        return root

    def gate(root, *extra):
        cp = subprocess.run([sys.executable, script, "--root", str(root),
                             "--version", "V0.1.0", "--user", "alice", "--json", *extra],
                            capture_output=True, text=True)
        try:
            return cp.returncode, json.loads(cp.stdout)
        except json.JSONDecodeError:
            return cp.returncode, {"_raw": cp.stdout + cp.stderr}

    OB = "# Sprint-045\n- 以下四条须按约定 22 回灌研发需求与用例：\n- 1) EC-N2 入参口径\n"
    LED = "- C-001 · 09-04 10:00 · EC-N2 入参口径订正 · sprint-045\n"

    # ★ 三次复发的那条路径：归档写了义务、台账根本不存在 → 收口点与终态门双双放行
    r1 = mkproj(OB)
    rc1, d1 = gate(r1)
    check("★ 归档有义务 + 台账不存在 → exit 2", rc1 == 2)
    check("★ 义务原文逐条打印（覆盖靠人对照）", len(d1["obligations"]) == 1)
    check("失败时点明台账不存在", d1["ledger"]["exists"] is False)

    r2 = mkproj(OB, LED)
    rc2, d2 = gate(r2)
    check("台账存在且有未决 → exit 0", rc2 == 0 and d2["ok"])

    # 台账在、但 0 条未决（空台账）同样不算载体
    r3 = mkproj(OB, "# 开发期变更台账\n\n## 待级联\n\n")
    rc3, _ = gate(r3)
    check("空台账不算载体 → exit 2", rc3 == 2)

    # 归档里没写义务 → 不因"台账不存在"误报
    r4 = mkproj("# Sprint-046\n本 Sprint 无实现期订正。\n")
    rc4, d4 = gate(r4)
    check("归档无义务 → exit 0，不误报", rc4 == 0 and not d4["obligations"])

    # 当轮已级联完的义务不计入（否则会逼人为过门而写假台账）
    r5 = mkproj("# Sprint-047\n- 口径订正须级联，已级联完毕。\n")
    rc5, d5 = gate(r5)
    check("行内标『已级联』不计入未完成义务", rc5 == 0 and not d5["obligations"])

    # fail-closed：用户目录不存在不得静默判过
    rc6 = subprocess.run([sys.executable, script, "--root", str(r4), "--version", "V0.1.0",
                          "--user", "nobody"], capture_output=True, text=True).returncode
    check("用户目录不存在 fail-closed exit 1", rc6 == 1)
    for d in (r1, r2, r3, r4, r5):
        shutil.rmtree(d, ignore_errors=True)


def test_tick_target_version_per_command():
    """两条链路的 TARGET_VERSION 必须各取各的版本，⛔ 不得共用 autopilot 的开发版本。

    默认回落表是以 autopilot 为主写的：`TARGET_VERSION -> autopilot.target_version`
    = **正在开发的版本**。测试链路测的却是「当前待测版本」（current-version）。标准同 tick
    形态（Phase 2 归档上版 + Phase 3 开发下版）里两者必然不同 —— 共用会让 aiauto-test 的
    Phase 0.0.5/0.0.6/0.0.7 对着下一版拼 `docs/testing/{V}/研发自测`，恒不命中，
    无人值守据此按 testplan-incomplete 冻结，而研发自测其实就在被测版本目录里。
    分片里那句 `: "${TARGET_VERSION:=…}"` 兜不住：--shell 已填非空，`:=` 整段失效。
    """
    print("【tick TARGET_VERSION 按命令分流】")
    root = Path(tempfile.mkdtemp())
    (root / "memory").mkdir()
    (root / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps({
        "versions": {"V0.1.0": {"phase_beta_done_at": "2026-01-01T00:00:00",
                                "internal_released_at": ""}},
        "autopilot": {"target_version": "V0.2.0"}}), encoding="utf-8")
    shutil.copytree(str(Path(HERE).parents[0]), str(root / ".aidp/scripts"),
                    ignore=shutil.ignore_patterns("__pycache__", "tests"))

    def tv(cmd):
        r = subprocess.run([sys.executable, ".aidp/scripts/autopilot_tick_flags.py",
                            "--command", cmd, "--shell"],
                           cwd=str(root), capture_output=True, text=True)
        for ln in r.stdout.split("\n"):
            if ln.startswith("TARGET_VERSION="):
                return ln.split("=", 1)[1].strip("'\"")
        return None

    check("★ 开发链路取 autopilot.target_version（V0.2.0）", tv("autopilot") == "V0.2.0")
    check("★ 测试链路取 current-version（V0.1.0），不串开发版本", tv("aiauto-test") == "V0.1.0")
    shutil.rmtree(root, ignore_errors=True)


def test_shard_counts_path_owner():
    """片数声明的归属优先看**文件所在目录**；且数字不得取自标识符。

    原先只在行内找命令名，而分片自己的头注释（「本文件是 … 第 9/10 片」）常不重复写命令名
    → 61 处声明里 17 处（27%）一处都没被校验过。按路径归属补上后，立刻暴露另一个 bug：
    `<!-- 二次切分 · phase-3 片2/5 -->` 里的 `3` 属于分组名 `phase-3`，被读成「3 片」整批误报。
    """
    print("【片数声明：路径归属 + 标识符不误取】")
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_shard_counts as SC
    check("★ `phase-3 片2/5` 里的 3 不是片数（属分组名）",
          not SC.COUNT_RE.search("<!-- 二次切分 · phase-3 片2/5：覆盖 x -->"))
    check("正常声明仍取得到", [m.group(1) for m in SC.COUNT_RE.finditer("本命令共 10 片")] == ["10"])
    check("「第 N 片」序号不当片数", not SC.COUNT_RE.search("这是第 3 片"))

    root = Path(tempfile.mkdtemp())
    fl = root / ".aidp/flows/demo-cmd"
    fl.mkdir(parents=True)
    for n in (1, 2):
        (fl / f"phase-{n}.md").write_text(f"> 本文件是第 {n}/9 片（片数写错了，应为 2）\n",
                                          encoding="utf-8")
    (root / ".aidp/commands").mkdir(parents=True)
    (root / ".aidp/commands/demo-cmd.md").write_text("# demo\n", encoding="utf-8")
    r = SC.run(str(root))
    kinds = {f["kind"] for f in r["findings"]}
    check("★ 头注释不写命令名也能按路径归属校验（原先整类零校验）", bool(r["findings"]))
    # ★ 斜杠形片号由**专管它的**「片号分母」判据接手（`COUNT_RE` 显式排除斜杠左侧，
    #   否则同一处错误会被两条判据各报一遍，噪音掩盖真信号）。
    check("★ `第 N/M 片` 归「片号分母」判据（分母 9 ≠ 实有 2）", "片号分母" in kinds)
    shutil.rmtree(root, ignore_errors=True)


def test_skill_ref_assets_and_install_time():
    """SKILL 内部文件引用：`assets/` 也要查；但安装态生成的文件不算悬空。

    只认 scripts/references 等于给资产引用留了无门区（命令端确实会指名
    `some-skill/assets/card-template.json` 这类文件，它们同样会随上游改名而漂）。
    反过来 `config.json` 由使用者从 `config.example.json` 拷贝生成，仓库里天然不存在，
    而引用它的正文往往正是在讲「它缺失时怎么办」——判成"上游已删除"是判据错位。
    """
    print("【SKILL 引用：assets 覆盖 + 安装态文件豁免】")
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_skill_ref_drift as SR
    root = Path(tempfile.mkdtemp())
    sk = root / ".aidp/skills/demo-skill"
    (sk / "assets").mkdir(parents=True)
    (sk / "SKILL.md").write_text("x", encoding="utf-8")
    (sk / "assets/card-template.json").write_text("{}", encoding="utf-8")
    (sk / "assets/config.example.json").write_text("{}", encoding="utf-8")
    cmd = root / ".aidp/commands"
    cmd.mkdir(parents=True)
    (cmd / "c.md").write_text(
        "见 `demo-skill/assets/card-template.json`\n"
        "缺 `demo-skill/assets/config.json` 时引导用户从 example 拷\n"
        "还有 `demo-skill/assets/removed-file.json`\n", encoding="utf-8")
    r = SR.scan(str(root))
    refs = {f["ref"] for f in r["findings"]}
    check("★ assets 下真悬空被检出", "demo-skill/assets/removed-file.json" in refs)
    check("★ 存在的 assets 文件不误报", "demo-skill/assets/card-template.json" not in refs)
    check("★ 有同名 .example. 的安装态文件不算悬空", "demo-skill/assets/config.json" not in refs)
    shutil.rmtree(root, ignore_errors=True)


def test_cross_file_dup_whole_line():
    """整行也要作为片段登记：只按句切会漏掉「一整段复制粘贴」这一类真双写。

    中文契约文档里一段 600 字符的复制，往往由 5 个各 120 字符的句子组成——每一句都够不到
    150 的 ERROR 阈值，于是整段逐字重复只报几条 WARN 甚至不报。实测本仓有 4 组真双写
    落在这个缝里（其中一组是 `--unattended` 的语义定义逐字抄在 4 个命令文件里）。
    """
    print("【跨文件双写：整行片段】")
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_cross_file_dup as CD
    root = Path(tempfile.mkdtemp())
    d = root / ".aidp/commands"
    d.mkdir(parents=True)
    # 5 句 × 各 ~40 字符：逐句都远低于阈值，整行 200+ 字符
    seg = "。".join(["这是一段被逐字复制到两个文件里的契约说明第%d句内容足够长以便测试" % i
                     for i in range(1, 6)]) + "。"
    (d / "a.md").write_text("# A\n\n" + seg + "\n", encoding="utf-8")
    (d / "b.md").write_text("# B\n\n" + seg + "\n", encoding="utf-8")
    r = CD.run(str(root))
    errs = [f for f in r["findings"] if f["level"] == "ERROR"]
    check("★ 整段复制被判 ERROR（逐句都够不到阈值）", bool(errs))
    check("★ 命中落点是两个文件", errs and len(errs[0]["files"]) == 2)
    shutil.rmtree(root, ignore_errors=True)


def test_step_index_table_forms():
    """骨架表识别不得绑死粗体：`| Step 0 |` 与 `| **0.2**（子步骤 1–4）|` 都要认。

    绑死 `**…**` 时 `/memory-sync` 与 `/sprint-selftest` 这类 `| Step N |` 形态的整张表读不进来，
    `listed_parents` 恒空 → 这两个命令**结构上永远报不出缺口**；而丢掉粗体后的尾巴
    （`（子步骤 1–4）`）又会让 `/sprint-aiauto-test` 的 0.2 被误报成漏登记。两头都要接住。
    """
    print("【骨架表编号识别的两种形态】")
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_step_index_coverage as SI
    def cell(line):
        m = SI.CELL_RE.match(line)
        return m.group(1) if m else None
    check("★ 无粗体 `| Step 0 | …`", (cell("| Step 0 | 执行前自检 | x |") or "").strip() == "0")
    check("★ 粗体带尾巴 `| **0.2**（子步骤 1–4）|`",
          cell("| **0.2**（子步骤 1–4）| `phase-0-6.md` | x |") == "0.2")
    check("粗体常规 `| **2.7** |`", cell("| **2.7** | x | y |") == "2.7")
    check("非编号首格不误取", cell("| 情况 | 默认策略 |") is None)


def test_handback_has_auto_trigger():
    """`handback-check` 自称「结构级机器门」，就必须真有自动触发点。

    此前它只出现在三份 .md 散文里（"命令返回前必跑"），`settings.json` 与 hooks 里零命中；
    而 ceremony-gate 的 `check` 刻意不含 HANDBACK（时序死结）。于是这条断言的实际强度
    仍是执行体自律 —— 与它要修复的那个事故同层级。
    """
    print("【handback-check 自动触发点】")
    repo = Path(HERE).parents[2]
    hook = (repo / ".aidp/hooks/autopilot-stop-guard.py").read_text(encoding="utf-8")
    check("★ Stop hook 真的会跑 handback-check（不是只写在散文里）",
          "handback-check" in hook)
    check("★ 违背时阻止结束，而不是打印一句就放行",
          "_exit_block" in hook.split("handback-check", 1)[1][:800])
    gate = (repo / ".aidp/scripts/autopilot-ceremony-gate.py").read_text(encoding="utf-8")
    check("ceremony-gate 仍提供 handback-check 子命令", "cmd_handback_check" in gate)


def test_tests_readme_group_table():
    """`tests/README.md` 的分组表行数必须等于实际分组数。

    该表自称「单一信源」，实测却停在 30 行、落后 45 组——因为**没有任何机器门守它**：
    `check_count_claims` 的分组数判据只认「共 N 组」这种数字声明，表有多少行它不看。
    行数漂移的表现形式恰恰是全绿。
    """
    import re as _re
    print("【tests/README 分组表行数】")
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_count_claims as CC
    repo = Path(HERE).parents[2]
    truth = CC.truth_guard_test_groups(str(repo))
    rows = len([ln for ln in (Path(HERE) / "README.md").read_text(encoding="utf-8").split("\n")
                if _re.match(r"^\|\s*\d+\s*\|", ln)])
    check("★ README 分组表行数 == 实际分组数（%s vs %s；漂了就跑 "
          "`python3 .aidp/scripts/tests/sync_group_table.py` 对齐，⛔ 别再手工重排表格——"
          "手抄正是这张表落后 45 组的根因）" % (rows, truth), rows == truth)


def test_prd_deploy_mode_version_scoped():
    """DEPLOY_MODE 的 PRD 兜底必须按**本轮目标版本**取，不是字典序第一个。

    仓库里同时有上版与下版 PRD 是 autopilot「每轮处理最近的一对」的常态。取错版本时
    读出来的是一个**看起来合法**的值（如上版的 none），比读空更难发现，而连锁失效相同：
    云端 build 被当静态-only 就地 finalize → 真实测试结论撞上报告不可变铁律永远写不进去。
    """
    print("【DEPLOY_MODE 的 PRD 兜底按版本取】")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "atf", str(Path(HERE).parents[0] / "autopilot_tick_flags.py"))
    atf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(atf)

    root = Path(tempfile.mkdtemp())
    for ver, mode in (("V0.1.0", "none"), ("V0.2.0", "cloud")):
        d = root / "docs/requirements" / ver / "产品提供"
        d.mkdir(parents=True)
        (d / "prd.md").write_text(
            "---\nautopilot_decisions:\n  deployment:\n    mode: %s\n---\n# PRD\n" % mode,
            encoding="utf-8")
    cwd = os.getcwd()
    try:
        os.chdir(root)
        check("★ 目标版本 V0.2.0 → 取 cloud（字典序第一个是 V0.1.0 的 none）",
              atf._prd_deploy_mode({"TARGET_VERSION": "V0.2.0"}) == "cloud")
        check("目标版本 V0.1.0 → 取 none", atf._prd_deploy_mode({"TARGET_VERSION": "V0.1.0"}) == "none")
        check("★ 目标版本无自己的声明 → 继承 ≤ 它的最新一版（V0.3.0 → cloud）",
              atf._prd_deploy_mode({"TARGET_VERSION": "V0.3.0"}) == "cloud")
        check("★ 目标版本早于一切声明 → 不猜，返回空",
              atf._prd_deploy_mode({"TARGET_VERSION": "V0.0.1"}) == "")
    finally:
        os.chdir(cwd)
    check("_semver_key 按数值不按字典序（V0.10.0 > V0.2.0）",
          atf._semver_key("V0.10.0") > atf._semver_key("V0.2.0"))
    shutil.rmtree(root, ignore_errors=True)


def test_plan_sprints_multifile():
    """Sprint 集合口径：必须扫**全部**研发执行计划，取第一份 = 静默丢 Sprint。

    真实失效形态：M1/M2 两份计划，`find … -print -quit` 命中 M1，M1 跑完即判「全部 Sprint
    已关闭」→ 正常部署、finalize、发报告，M2 的 Sprint 从未执行且无任何告警。
    """
    print("【研发执行计划 → Sprint 集合口径】")
    script = str(Path(HERE).parents[0] / "plan_sprints.py")
    root = Path(tempfile.mkdtemp())
    (root / "docs/plans/V0.1.0").mkdir(parents=True)
    (root / "memory/V0.1.0/alice/sprints").mkdir(parents=True)

    def run(*extra):
        cp = subprocess.run([sys.executable, script, "--root", str(root),
                             "--version", "V0.1.0", "--json", *extra],
                            capture_output=True, text=True)
        return cp.returncode, (json.loads(cp.stdout) if cp.stdout.strip() else {})

    rc0, _ = run()
    check("★ 无研发执行计划 → exit 1 fail-closed（不返回空集判完成）", rc0 == 1)

    (root / "docs/plans/V0.1.0/01_M1研发执行计划.md").write_text(
        "Sprint-001 建骨架\nSprint-002 建接口\n", encoding="utf-8")
    (root / "docs/plans/V0.1.0/02_M2研发执行计划.md").write_text(
        "Sprint-003 报表\n", encoding="utf-8")
    rc, d = run()
    check("★ 多份计划全取（M1+M2 = 3 个 Sprint，不是只取第一份的 2 个）",
          rc == 0 and d["all_sprints"] == ["001", "002", "003"])

    for n in ("001", "002"):
        (root / ("memory/V0.1.0/alice/sprints/sprint-%s.md" % n)).write_text("x", encoding="utf-8")
    rc, d = run()
    check("★ M1 全关闭时 M2 仍在剩余集（旧 -print -quit 口径此处会误判完成）",
          d["remain_sprints"] == ["003"] and d["next_sprint"] == "003")
    check("current_sprint = 最后一个已关闭", d["current_sprint"] == "002")

    (root / "docs/plans/V0.1.0/03_研发执行计划-张三.md").write_text(
        "Sprint-004 联调\n", encoding="utf-8")
    rc, d = run()
    check("多用户拆分 NN_研发执行计划-{开发者}.md 也被扫到", "004" in d["all_sprints"])

    root2 = Path(tempfile.mkdtemp())
    (root2 / "docs/plans/V0.1.0").mkdir(parents=True)
    (root2 / "docs/plans/V0.1.0/01_研发执行计划.md").write_text("正文无编号\n", encoding="utf-8")
    rc2 = subprocess.run([sys.executable, script, "--root", str(root2), "--version", "V0.1.0"],
                         capture_output=True, text=True).returncode
    check("★ 有计划但解析不出 Sprint → exit 1（不静默给空集）", rc2 == 1)

    cp = subprocess.run([sys.executable, script, "--root", str(root),
                         "--version", "V0.1.0", "--shell"], capture_output=True, text=True)
    names = {ln.split("=", 1)[0] for ln in cp.stdout.strip().split("\n") if "=" in ln}
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_flow_var_refs as CFV
    registered = next(nm for rx, nm in CFV.SCRIPT_INJECTED
                      if rx.search("plan_sprints.py --shell"))
    check("★ --shell 实际导出的变量名与 check_flow_var_refs 登记表一致（漂了就会误报未赋值）",
          names == registered)
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(root2, ignore_errors=True)


def test_design_anchor_gate():
    """实现偏离设计门：设计点名的字段/常量在代码里能不能找到。"""
    print("【实现偏离设计门】")
    script = str(Path(HERE).parents[0] / "check_design_anchor.py")
    sys.path.insert(0, str(Path(HERE).parents[0]))
    import check_design_anchor as DA

    # ★ 回归：命名风格差异不得制造假阳性。少了变体匹配，本门会把实现好好的字段
    #   整片报成"找不到落点"，然后被人整片加豁免绕过 —— 等于没有这道门。
    check("★ camelCase getter 命中（createTime ← getCreateTime）",
          DA._found_in_code("createTime", "String t = o.getCreateTime();"))
    check("★ snake_case 命中（createTime ← create_time）",
          DA._found_in_code("createTime", "select create_time from t_order"))
    check("★ 但后缀延长不得误命中（userId ✗ userIdentifier）",
          not DA._found_in_code("userId", "String x = getUserIdentifier();"))

    root = Path(tempfile.mkdtemp())
    (root / "docs/design/detail/V0.1.0").mkdir(parents=True)
    (root / "code/backend/app/src").mkdir(parents=True)
    (root / "docs/design/detail/V0.1.0/01_详细设计.md").write_text(
        "# 详细设计\n取 `orderChannel=CHANNEL_PERSONAL` 结果里的 `userId` 作为员工标识。\n"
        "字段 `createTime` 直接展示。\n"
        "字段 `legacyFlag` 保留位。 design-anchor-ignore: 保留位，本版无实现\n",
        encoding="utf-8")
    (root / "code/backend/app/src/S.java").write_text(
        "public class S {\n  String u = order.getCreateBy();\n"
        "  String t = order.getCreateTime();\n}\n", encoding="utf-8")

    def gate(*extra):
        cp = subprocess.run([sys.executable, script, "--root", str(root),
                             "--version", "V0.1.0", "--json", *extra],
                            capture_output=True, text=True)
        return cp.returncode, json.loads(cp.stdout)

    rc, d = gate()
    names = {m["anchor"] for m in d["missing"]}
    # ★ 回归：「有发现」必须落 exit 1，不是 2。维度 13 的调用方把 exit 2 当「入参/环境错 →
    #   修正后重跑」，既不计过也不计不过——把发现放在 2 上，每条真实偏离都会被静默丢掉，
    #   且两侧报告都不留痕（门在跑、恒绿）。2 只留给用法错（argparse 自己给）。
    check("★ 换了数据来源的偏离被抓住，且落 exit 1（不是被当环境错的 2）",
          rc == 1 and "CHANNEL_PERSONAL" in names)
    rc_usage = subprocess.run([sys.executable, script, "--root", str(root), "--json"],
                              capture_output=True, text=True).returncode
    check("★ 缺 --version 值 → exit 2（用法错专属，不与「有发现」混淆）", rc_usage == 2)
    check("★ 实现到位的字段不误报（createTime 不在缺失里）", "createTime" not in names)
    check("行内 design-anchor-ignore 生效（legacyFlag 不报）", "legacyFlag" not in names)

    # 无设计文档 → N/A 跳过，不阻塞
    rc2 = subprocess.run([sys.executable, script, "--root", str(root), "--version", "V9.9.9"],
                         capture_output=True, text=True).returncode
    check("无设计文档 → SKIP exit 0", rc2 == 0)
    shutil.rmtree(root, ignore_errors=True)


def test_report_na_result_state():
    """报告第五态 `na`（不适用）：不得被伪装成 pass，也不进通过率分母。

    「不适用记 pass」是本仓「不得伪装」纪律的第四种形态——前三种是 *失败→空态* /
    *未生效→已生效* / *未执行→无问题*，这一种是 ***不适用→通过***。
    """
    print("【报告 na 结果态】")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "er", str(Path(HERE).parents[0] / "emit-report.py"))
    er = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(er)

    def mk(summary, cases):
        return {"build": "V1_b1", "version": "V1", "buildNo": 1,
                "summary": summary, "cases": cases}

    P = [{"id": f"T{i}", "title": "t", "result": "pass", "note": ""} for i in range(5)]
    F = [{"id": "T5", "title": "t", "result": "fail", "note": ""}]
    NA = [{"id": f"N{i}", "title": "本页不适用", "result": "na",
           "note": "本页无导出入口（Q-102 隐私收敛）"} for i in range(4)]

    ok = mk({"total": 10, "pass": 5, "fail": 1, "block": 0, "skip": 0, "na": 4,
             "passRate": 5 / 6}, P + F + NA)
    check("★ na 合法且分母为 total-na（5/6 而非 5/10）", not er.validate_payload("test", ok))
    bad_denom = mk({"total": 10, "pass": 5, "fail": 1, "block": 0, "skip": 0, "na": 4,
                    "passRate": 0.5}, P + F + NA)
    check("★ 把 na 算进分母 → 报错（正是被虚高的那个数）",
          bool(er.validate_payload("test", bad_denom)))
    no_reason = mk({"total": 7, "pass": 5, "fail": 1, "block": 0, "skip": 0, "na": 1,
                    "passRate": 5 / 6},
                   P + F + [{"id": "X", "title": "x", "result": "na"}])
    check("★ na 无理由 → 报错（否则 na 成了最便宜的逃逸口）",
          bool(er.validate_payload("test", no_reason)))
    legacy = mk({"total": 6, "pass": 5, "fail": 1, "block": 0, "skip": 0,
                 "passRate": 5 / 6}, P + F)
    check("存量报告无 na 字段仍合法（视作 0，五态退化为四态）",
          not er.validate_payload("test", legacy))
    bad_sum = mk({"total": 11, "pass": 5, "fail": 1, "block": 0, "skip": 0, "na": 4,
                  "passRate": 5 / 6}, P + F + NA)
    check("五态之和 ≠ total → 报错", bool(er.validate_payload("test", bad_sum)))
    check("na 在合法结果态集合里", "na" in er.RESULT_STATES)

    # 渲染端必须认得第五态，否则报告页会把它画丢
    app = (Path(HERE).parents[1] / "templates/reports/AI测试报告/assets/app.js").read_text(
        encoding="utf-8")
    check("★ 渲染端 RESULT_KEYS 含 na（否则环形图/堆叠柱把它画丢）",
          '"na"' in app and "不适用" in app)


def test_classify_business_words_in_source_tree():
    """业务语义词（deployment / deploy*）只在【源码根之外】才算非正式变更。

    这些词原本无条件命中、且排在源码扩展名判定之前 —— 于是包名叫 `deploy`、业务域叫
    `deployment`、控制器叫 `DeployController` 的**正经源码**全被判非正式，
    `has_formal_code_change=False` 且 `classification_error=False` → CICD 不监听、
    不部署、不探针，而 flow 侧那条 fail-closed 因 error 为假**永不触发**。
    """
    print("【提交分类 · 业务语义词不误伤源码】")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ccm", str(Path(HERE).parents[0] / "classify_commit_change.py"))
    ccm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ccm)

    root = Path(tempfile.mkdtemp())
    (root / "code/backend/app").mkdir(parents=True)
    (root / "code/frontend/web").mkdir(parents=True)
    (root / "code/backend/app/pom.xml").write_text("<project/>", encoding="utf-8")
    (root / "code/frontend/web/package.json").write_text('{"name":"web"}', encoding="utf-8")

    def cls(paths):
        return ccm.classify_commit_change(str(root), changed_files=paths)

    for p_ in ("code/backend/app/src/main/java/com/example/deploy/UserService.java",
               "code/backend/app/src/main/java/com/x/deployment/OrderService.java",
               "code/backend/app/src/main/java/com/x/DeployController.java",
               "code/frontend/web/src/views/deployList.vue"):
        r = cls([p_])
        check(f"★ 源码树内含业务语义词仍判正式：{p_.split('/')[-1]}",
              r["has_formal_code_change"] is True and r["cicd_should_watch"] is True)

    # 源码树【之外】的同名词照旧判非正式，且不误报 error
    for p_ in ("deployment/k8s.yaml", "tools/deploy.sh", "docs/deployment/x.md"):
        r = cls([p_])
        check(f"源码树外仍判非正式：{p_}",
              r["has_formal_code_change"] is False and r["classification_error"] is False)
    shutil.rmtree(root, ignore_errors=True)


def test_release_credential_gate_coverage():
    """明文凭据门：`全量/` 下随 tag 冻结入 git，凭据进去不可逆 —— 五类写法都要拦住。"""
    print("【发布基线 · 明文凭据门覆盖面】")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rbc", str(Path(HERE).parents[0] / "release_baseline_check.py"))
    rbc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rbc)

    root = Path(tempfile.mkdtemp())
    d = root / "docs/deployment/V0.1.0/配置文件/全量"
    d.mkdir(parents=True)
    (d / "application.properties").write_text(
        "spring.datasource.password=P@sswOrd123\noss.secret-key=AKIAIOSFODNN7EXAMPLE\n"
        "server.port=8080\n", encoding="utf-8")
    (d / ".env").write_text("API_KEY=sk-live-abcdef1234567890\n", encoding="utf-8")
    (d / "app.yml").write_text(
        "spring:\n  datasource:\n    url: jdbc:mysql://root:P@ss@192.0.2.10:3306/db\n"
        "nginx:\n  headers:\n    - \"Authorization: Basic YWRtaW46cGFzc3dvcmQxMjM=\"\n"
        "  script: |\n    curl -H \"Authorization: Basic YWRtaW46cGFzc3c=\" https://x\n",
        encoding="utf-8")
    rep = rbc.Report()
    rbc.check_configs(d, rep)
    rbc.check_nonyaml_runtime_files(d, rep)
    msgs = " ".join(e["msg"] for e in rep.errors)
    check("★ .properties 的 password 被拦（此前白名单里根本不扫 .properties）",
          "application.properties" in msgs and "password" in msgs)
    check("★ .properties 的 secret-key 被拦", "secret-key" in msgs)
    check("★ .env 被拦（同样不在原白名单里）", ".env" in msgs)
    check("★ YAML 值内嵌 URL userinfo 被拦（EMBEDDED_CRED 此前只接非 YAML 路径）",
          "userinfo" in msgs or "内嵌账号口令" in msgs)
    check("★ YAML 列表项里的 Basic 凭据被拦（键路径解析器整段跳过列表项）",
          "app.yml:6" in msgs)
    check("★ YAML 块标量里的 Basic 凭据被拦（块标量同样被整段跳过）",
          "app.yml:8" in msgs)

    # 负向：干净配置不得误报
    d2 = root / "docs/deployment/V0.2.0/配置文件/全量"
    d2.mkdir(parents=True)
    (d2 / "clean.yml").write_text("server:\n  port: 8080   # 服务端口\n", encoding="utf-8")
    (d2 / "clean.properties").write_text("app.name=demo\n", encoding="utf-8")
    rep2 = rbc.Report()
    rbc.check_configs(d2, rep2)
    rbc.check_nonyaml_runtime_files(d2, rep2)
    check("干净配置零误报", not [e for e in rep2.errors if e["check"] == "明文凭据"])
    shutil.rmtree(root, ignore_errors=True)


def test_cascade_landing_gate():
    """约定 22 收口落点门：级联直接改各族内容主文档，不产中转册、不新建分册。"""
    print("【级联落点门】")
    script = str(Path(HERE).parents[0] / "check_cascade_landing.py")
    FAMS = [("docs/requirements/{v}/研发需求", "_开发期需求增量.md"),
            ("docs/design/detail/{v}", "_开发期设计增量.md"),
            ("docs/plans/{v}", "_开发期计划增量.md"),
            ("docs/testing/{v}/研发自测", "_开发期用例增量.md")]

    def mkrepo():
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=False, capture_output=True)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            subprocess.run(["git", "-C", str(root), "config", k, v], check=False, capture_output=True)
        for tpl, _inc in FAMS:
            d = root / tpl.format(v="V0.1.0")
            d.mkdir(parents=True)
            (d / "00_索引.md").write_text("# 索引\n", encoding="utf-8")
            (d / "01_主文档.md").write_text("# 主文档\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=False, capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=False, capture_output=True)
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
        return root, head

    def gate(root, *extra):
        cp = subprocess.run([sys.executable, script, "--root", str(root), *extra],
                            capture_output=True, text=True)
        return cp.returncode, cp.stdout + cp.stderr

    def commit(root, msg):
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=False, capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", msg], check=False, capture_output=True)

    # ★ 合规：就地改四族内容主文档（+ 刷索引）——这才是级联该落的地方
    #   ⛔ 中文路径必须能匹配：core.quotepath 默认把非 ASCII 转义，不关它则本门恒 fail-open
    root, base = mkrepo()
    for tpl, _inc in FAMS:
        (root / tpl.format(v="V0.1.0") / "01_主文档.md").write_text("# 主文档\n级联改\n", encoding="utf-8")
    commit(root, "cascade")
    rc, out = gate(root, "--base-ref", base)
    check("★ 就地改四族主文档 exit 0（中文路径不转义）", rc == 0)
    check("合规落点报告改了 4 份", "4 份主文档/索引被更新" in out)

    # 刷 00_索引.md 是级联的正常动作（主文档动了、索引时间戳就该动）
    root2, base2 = mkrepo()
    (root2 / "docs/plans/V0.1.0/00_索引.md").write_text("# 索引\n刷时间\n", encoding="utf-8")
    commit(root2, "idx")
    rc, out = gate(root2, "--base-ref", base2)
    check("★ 刷 00_索引.md 不误报", rc == 0)

    # ★ 族增量册在收口批次里被改动是**合法落点**（收口时在其中删条目、清空即删文件）；
    #   判违规会把每次正常收口都拦下来。
    root3, base3 = mkrepo()
    (root3 / "docs/design/detail/V0.1.0/_开发期设计增量.md").write_text("# 增量\n", encoding="utf-8")
    commit(root3, "mid")
    rc, out = gate(root3, "--base-ref", base3)
    check("★ 族增量册改动属合法落点、不判违规", rc == 0)

    # ⛔ 新建 NN_ 分册：那是产品侧/口述累进的命名空间
    root4, base4 = mkrepo()
    (root4 / "docs/plans/V0.1.0/02_业务主题.md").write_text("# NN 增量\n", encoding="utf-8")
    commit(root4, "nn")
    rc, out = gate(root4, "--base-ref", base4)
    check("★ 新建 NN_<业务主题>.md 分册被检出", rc == 1 and "不新起分册" in out)
    # ★ 判据是"新建"不是文件名：主文档 01_研发需求.md 与增量 07_订单主题.md 完全同形，
    #   正则分不开——改既有的 NN_ 文件（它很可能就是主文档）必须放行
    root4b, base4b = mkrepo()
    (root4b / "docs/plans/V0.1.0/01_主文档.md").write_text("# 主文档\n改\n", encoding="utf-8")
    commit(root4b, "edit-existing")
    rc, _ = gate(root4b, "--base-ref", base4b)
    check("★ 改既有 NN_ 形态文件放行（判新建、不判文件名）", rc == 0)

    # 四族目录之外的改动不归本门管
    root5, base5 = mkrepo()
    (root5 / "code").mkdir()
    (root5 / "code/A.java").write_text("class A {}", encoding="utf-8")
    (root5 / "README.md").write_text("# x\n", encoding="utf-8")
    commit(root5, "code")
    rc, _ = gate(root5, "--base-ref", base5)
    check("四族目录外改动不误报", rc == 0)

    # worktree 模式（收口子 Agent 提交前自检）——用**真违规**（新建 NN_ 分册）验，
    # ⛔ 不能再用族增量册：它已是合法落点，拿它当探针等于测了个恒绿的东西。
    root6, _ = mkrepo()
    (root6 / "docs/plans/V0.1.0/07_订单主题.md").write_text("# 分册\n", encoding="utf-8")
    rc, out = gate(root6, "--worktree")
    check("worktree 模式检出未提交的违规", rc == 1 and "worktree" in out)

    # fail-closed：不给结论就是不通过
    root7, _ = mkrepo()
    rc, _ = gate(root7, "--base-ref", "nonexistent-ref")
    check("坏 base-ref fail-closed", rc == 1)
    rc, _ = gate(root7)
    check("缺 base-ref 且非 worktree fail-closed", rc == 1)
    bare = Path(tempfile.mkdtemp())
    rc, out = gate(bare, "--base-ref", "HEAD")
    check("无版本目录/非仓库 fail-closed", rc == 1)

    # --version 限定 + JSON 结构
    root8, base8 = mkrepo()
    (root8 / "docs/plans/V0.1.0/01_主文档.md").write_text("# 主文档\n改\n", encoding="utf-8")
    commit(root8, "one")
    cp = subprocess.run([sys.executable, script, "--root", str(root8),
                         "--base-ref", base8, "--version", "V0.1.0", "--json"],
                        capture_output=True, text=True)
    data = json.loads(cp.stdout)
    check("JSON 输出字段齐备",
          data["ok"] is True and data["versions"] == ["V0.1.0"]
          and "docs/plans/V0.1.0/01_主文档.md" in data["landed"]
          and data["violations"] == [])

    for d in (root, root2, root3, root4, root4b, root5, root6, root7, root8, bare):
        shutil.rmtree(d, ignore_errors=True)


def test_ledger_closed_gate():
    """约定 22 终态门：收口后「该删的台账必须已删」——文件存在 ⟺ 确有未决条目。

    此前这条规则写了三处（台账详规 + planning-8 Step 2.7.4 + release-5 Step 3.3.9.5）
    却零校验，执行体级联完把台账留着照样通过、台账跨版本堆积。本组用例锁住判据。
    """
    print("【台账终态门 --ledger-closed】")
    script = str(Path(HERE).parents[0] / "check_cascade_landing.py")
    LED = "docs/requirements/{v}/研发需求/_开发期需求增量.md"

    def mkroot():
        root = Path(tempfile.mkdtemp())
        (root / "docs/requirements/V0.1.0/研发需求").mkdir(parents=True)
        return root

    def gate(root, *extra):
        cp = subprocess.run([sys.executable, script, "--root", str(root),
                             "--ledger-closed", *extra], capture_output=True, text=True)
        return cp.returncode, cp.stdout + cp.stderr

    def put(root, text, v="V0.1.0"):
        (root / LED.format(v=v)).parent.mkdir(parents=True, exist_ok=True)
        (root / LED.format(v=v)).write_text(text, encoding="utf-8")

    roots = []
    # ① 台账不存在 = 收口完成的正常终态
    r = mkroot(); roots.append(r)
    rc, out = gate(r, "--version", "V0.1.0")
    check("四族均无册子 → PASS", rc == 0 and "四族均无残留增量册" in out)

    # ② 仍有未决条目 → 合法保留（一行式 + 表格式两种写法都要认）
    r = mkroot(); roots.append(r)
    put(r, "# 台账\n## 待级联\n- C-001 · 09-01 10:00 · 新增导出接口 · sprint-003\n"
           "- C-002 · 09-02 11:00 · 用户表加字段 · sprint-004\n")
    rc, out = gate(r, "--version", "V0.1.0")
    check("有 2 条未决 → PASS 且报剩余条数", rc == 0 and "保留 2 条未决" in out)
    r = mkroot(); roots.append(r)
    put(r, "# 台账\n## 待级联\n| 编号 | 日期 | 类型 | 内容 |\n|---|---|---|---|\n"
           "| C-001 | 2026-09-01 | 新增接口 | 导出 |\n| C-002 | 2026-09-02 | 新增表 | 审计 |\n")
    rc, out = gate(r, "--version", "V0.1.0")
    check("表格式未决条目同样 PASS", rc == 0 and "保留 2 条未决" in out)

    # ③ ★ 核心反例：条条已级联却仍留着 = 该删没删
    r = mkroot(); roots.append(r)
    put(r, "# 台账\n## 待级联\n- C-001 · 09-01 10:00 · 导出接口 ✅已级联 · s3\n"
           "- C-002 · 09-02 11:00 · 加字段 ✅已级联 · s4\n")
    rc, out = gate(r, "--version", "V0.1.0")
    check("★ 条条已级联却没删 → FAIL", rc == 1 and "not-deleted" in out)
    r = mkroot(); roots.append(r)
    put(r, "# 台账\n## 待级联\n| 编号 | 日期 |\n|---|---|\n| ~~C-001~~ | 2026-09-01 |\n")
    rc, out = gate(r, "--version", "V0.1.0")
    check("表格划删线（已级联）却没删 → FAIL", rc == 1 and "not-deleted" in out)

    # ④ 空台账没删同样违规
    r = mkroot(); roots.append(r)
    put(r, "# 开发期变更台账 — V0.1.0\n\n## 待级联\n")
    rc, out = gate(r, "--version", "V0.1.0")
    check("空台账没删 → FAIL", rc == 1 and "not-deleted" in out)

    # ⑤ 有内容却一条都解析不出 = 格式漂移，fail-closed 不放行
    r = mkroot(); roots.append(r)
    put(r, "# 台账\n## 待级联\n今天改了导出接口，还加了个字段。\n另外把权限口径也调了。\n")
    rc, out = gate(r, "--version", "V0.1.0")
    check("★ 格式漂移（认不出条目）→ FAIL 而非静默放行", rc == 1 and "unparsed" in out)

    # ⑥ LEDGER-ARCHIVED 不再是出路 —— 标记不替代删除，两档一律 FAIL
    r = mkroot(); roots.append(r)
    put(r, "<!-- LEDGER-ARCHIVED -->\n# 台账\n## 待级联\n- C-001 · 09-01 10:00 · x · s1\n")
    rc, out = gate(r, "--version", "V0.1.0")
    check("★ LEDGER-ARCHIVED → FAIL（标记不替代删除）",
          rc == 1 and "archived-not-deleted" in out)

    # ⑦ 不传 --version 全扫：只对存在台账的版本判定，其余版本不误报
    r = mkroot(); roots.append(r)
    (r / "docs/requirements/V0.2.0").mkdir(parents=True)
    put(r, "# 台账\n## 待级联\n- C-001 · 09-01 10:00 · 已级联 ✅已级联 · s1\n", v="V0.2.0")
    cp = subprocess.run([sys.executable, script, "--root", str(r),
                         "--ledger-closed", "--json"], capture_output=True, text=True)
    data = json.loads(cp.stdout)
    check("全扫只报有台账的版本",
          data["ok"] is False and data["versions"] == ["V0.1.0", "V0.2.0"]
          and [v["version"] for v in data["violations"]] == ["V0.2.0"])
    check("全扫 JSON 标注 mode", data.get("mode") == "ledger-closed")

    # ⑧ 与落点门（模式 A）互不干扰：--ledger-closed 不需要 git 范围也能跑
    r = mkroot(); roots.append(r)
    rc, _ = gate(r)
    check("--ledger-closed 无需 --base-ref/--worktree", rc == 0)

    # ⑨ ★★ 必删档（版本收口点 2/3）：目标版本台账必须不存在，不存在任何保留场景
    def gate_md(root, *extra):
        cp = subprocess.run([sys.executable, script, "--root", str(root),
                             "--must-delete", *extra], capture_output=True, text=True)
        return cp.returncode, cp.stdout + cp.stderr

    r = mkroot(); roots.append(r)
    rc, out = gate_md(r, "--version", "V0.1.0")
    check("必删档：台账不存在 → PASS", rc == 0 and "必删档" in out)

    # ★ 核心：必删档下"还有未决条目"不再是保留理由（默认档同一份是 PASS 的）
    r = mkroot(); roots.append(r)
    put(r, "# 台账\n## 待级联\n- C-001 · 09-01 10:00 · 尚未级联 · s1\n")
    rc, out = gate_md(r, "--version", "V0.1.0")
    check("★ 必删档：仍有未决条目也判 FAIL（版本收口不许把账带走）",
          rc == 1 and "must-delete" in out)
    rc2, _ = gate(r, "--version", "V0.1.0")
    check("★ 同一份台账在默认档（收口点 4）仍 PASS —— 两档确实分离", rc2 == 0)

    # ★ 必删档同样不认 LEDGER-ARCHIVED
    r = mkroot(); roots.append(r)
    put(r, "<!-- LEDGER-ARCHIVED -->\n# 台账\n## 待级联\n- C-001 · 09-01 10:00 · x · s1\n")
    rc, out = gate_md(r, "--version", "V0.1.0")
    check("★ 必删档：LEDGER-ARCHIVED 也不放行", rc == 1 and "must-delete" in out)
    rc2, _ = gate(r, "--version", "V0.1.0")
    check("★ 同一份在默认档同样 FAIL（两档口径一致，不留静默出路）", rc2 == 1)

    # 失败提示必须告诉执行体条目的去处，否则它会以为删档=丢数据而不敢删
    check("必删档提示写明条目去处（迁移 / 转记欠账）",
          "迁移进当前版本" in out and "发布欠账" in out)

    # 空台账在两档都 FAIL
    r = mkroot(); roots.append(r)
    put(r, "# 台账\n\n## 待级联\n")
    rc, _ = gate_md(r, "--version", "V0.1.0")
    rc2, _ = gate(r, "--version", "V0.1.0")
    check("空台账两档都 FAIL", rc == 1 and rc2 == 1)

    # JSON 标注档位，便于调用方确认自己跑的是哪一档
    r = mkroot(); roots.append(r)
    cp = subprocess.run([sys.executable, script, "--root", str(r),
                         "--must-delete", "--json"], capture_output=True, text=True)
    d = json.loads(cp.stdout)
    check("必删档 JSON 标注 mode/must_delete",
          d["mode"] == "ledger-closed-must-delete" and d["must_delete"] is True)

    # ⑨bis ★★ 必删档的配套：删档时未决条目必须已转出，否则 = 把账删没
    #      （只断言"文件没了"会让 `git rm` + 不转出 静默通过，条目蒸发）
    def mkrepo_led(text):
        root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init", "-q", str(root)], check=False, capture_output=True)
        for k, v in (("user.name", "t"), ("user.email", "t@t")):
            subprocess.run(["git", "-C", str(root), "config", k, v], check=False, capture_output=True)
        (root / "docs/requirements/V0.1.0/研发需求").mkdir(parents=True)
        (root / "docs/requirements/V0.2.0/研发需求").mkdir(parents=True)
        (root / LED.format(v="V0.1.0")).write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], check=False, capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=False, capture_output=True)
        subprocess.run(["git", "-C", str(root), "rm", "-q", LED.format(v="V0.1.0")],
                       check=False, capture_output=True)
        return root

    OPEN2 = ("# 台账\n## 待级联\n- C-001 · 09-01 10:00 · 新增导出接口 · s3\n"
             "- C-002 · 09-02 11:00 · 用户表加字段 · s4\n")

    # 删档 + 未转出 → 必须拦下
    r = mkrepo_led(OPEN2); roots.append(r)
    rc, out = gate_md(r, "--version", "V0.1.0",
                      "--transfer-to", "docs/requirements/V0.2.0/研发需求/_开发期需求增量.md")
    check("★ 必删档：删档但未转出 → FAIL（否则 2 条未决静默蒸发）",
          rc == 1 and "deleted-without-transfer" in out)
    check("失败信息报出删前的未决条数", "还有 2 条未决条目" in out)

    # 条目已迁移进当前版本台账 → 放行
    (r / LED.format(v="V0.2.0")).write_text(
        "# 台账\n## 待级联\n- C-001 · 09-01 10:00 · 导出接口 · s3 ← 承接自 V0.1.0\n"
        "- C-002 · 09-02 11:00 · 加字段 · s4 ← 承接自 V0.1.0\n", encoding="utf-8")
    rc, out = gate_md(r, "--version", "V0.1.0",
                      "--transfer-to", "docs/requirements/V0.2.0/研发需求/_开发期需求增量.md")
    check("★ 必删档：条目已迁移 → PASS 且报出转出条数",
          rc == 0 and "删前 2 条未决已转出" in out)

    # 删前本就无未决（条条已级联）→ 无需转出证据
    r = mkrepo_led("# 台账\n## 待级联\n- C-001 · 09-01 10:00 · x ✅已级联 · s3\n"); roots.append(r)
    rc, _ = gate_md(r, "--version", "V0.1.0")
    check("必删档：删前已无未决条目 → 免转出证据，PASS", rc == 0)

    # 未传 --transfer-to 且删前有未决 → 无从核验，fail-closed
    r = mkrepo_led(OPEN2); roots.append(r)
    rc, out = gate_md(r, "--version", "V0.1.0")
    check("必删档：有未决却没给转出目的地 → FAIL（不 fail-open）",
          rc == 1 and "未指定 --transfer-to" in out)

    # 转出目的地存在但没有来源痕迹 → 仍判失败
    r = mkrepo_led(OPEN2); roots.append(r)
    (r / LED.format(v="V0.2.0")).write_text("# 台账\n## 待级联\n- C-009 · 09-05 10:00 · 别的事 · s9\n",
                                            encoding="utf-8")
    rc, out = gate_md(r, "--version", "V0.1.0",
                      "--transfer-to", "docs/requirements/V0.2.0/研发需求/_开发期需求增量.md")
    check("必删档：转出目的地无来源痕迹 → FAIL", rc == 1 and "来自 V0.1.0 的条目痕迹" in out)

    # 台账从未进过 git → 标 unverifiable，不误杀（新项目/未提交场景）
    r = mkroot(); roots.append(r)
    subprocess.run(["git", "init", "-q", str(r)], check=False, capture_output=True)
    rc, out = gate_md(r, "--version", "V0.1.0")
    check("必删档：git 查无此文件 → 不误杀，但打印无从核验",
          rc == 0 and "无从核验" in out)

    # ⑩ 三个收口点的调用档位与规则文本一致（防 flow 里写成另一档）
    repo = Path(HERE).parents[2]
    plan8 = (repo / ".aidp/flows/version/planning-8.md").read_text(encoding="utf-8")
    rel5 = (repo / ".aidp/flows/version/release-5.md").read_text(encoding="utf-8")
    batch = (repo / ".aidp/commands/sprint-batch.md").read_text(encoding="utf-8")
    check("★ 收口点 2（规划期）用必删档", "--must-delete --version {上一版本}" in plan8)
    check("★ 收口点 3（发布期）用必删档", "--must-delete --version {version}" in rel5)
    # ★ 拆四族后转出目的地是**四份**（条目按内容分派到哪一族，收口时才知道），
    #   故 --transfer-to 传逗号分隔的四条，任一找到痕迹即算转出到位。
    check("★ 收口点 2 传转出目的地=当前版本【四族册】",
          "_开发期需求增量.md," in plan8 and "_开发期用例增量.md" in plan8)
    check("★ 收口点 3 传转出目的地=发布欠账",
          "--transfer-to docs/audit/{version}/发布欠账.md" in rel5)
    check("收口点 4（批次收尾）用默认档", "--ledger-closed --version {version}" in batch)
    check("规划期写明未决条目迁移进当前版本对应族", "承接自 {上一版本}" in plan8
          and "【对应族】" in plan8)
    check("发布期写明未决条目转记发布欠账", "转记 `docs/audit/{version}/发布欠账.md`" in rel5)
    check("两版本收口点均声明「不存在要保留的场景」",
          "不存在要保留的场景" in plan8 and "不存在要保留的场景" in rel5)

    for d in roots:
        shutil.rmtree(d, ignore_errors=True)


def test_design_full_rollforward():
    """发布期 Step 3.3.11 的 section 级前滚：只重写点名 H2，其余原样保留。

    这脚本在发布关键路径上（全量设计重算，占发布主体过半耗时），却一直没有回归测试——
    它一旦把没点名的章节也重写、或把旧章节丢掉，产出的是「看起来完整、实则内容被替换」
    的全量设计，而那正是最难在事后发现的一类错误。
    """
    print("【全量设计 section 级前滚】")
    script = str(Path(HERE).parents[0] / "design_full_rollforward.py")

    def run(*args):
        cp = subprocess.run([sys.executable, script, *args, "--json"],
                            capture_output=True, text=True)
        try:
            return cp.returncode, json.loads(cp.stdout)
        except json.JSONDecodeError:
            return cp.returncode, {"_raw": cp.stdout + cp.stderr}

    root = Path(tempfile.mkdtemp())
    full = root / "全量"; full.mkdir()
    (full / "01_用户域.md").write_text(
        "# 用户域\n\n前言段\n\n## 数据模型\n旧数据模型\n\n## 接口\n旧接口\n\n## 时序\n旧时序\n",
        encoding="utf-8")
    (full / "02_订单域.md").write_text("# 订单域\n\n## 数据模型\n订单旧模型\n", encoding="utf-8")

    # --- scope：Δ 命中率
    rc, d = run("scope", "--full-dir", str(full), "--delta", "用户域")
    check("scope 正常返回", rc == 0 and d.get("ok") is True)
    check("scope 统计分册数", d["book_count"] == 2 and d["delta_books"] == 1)
    check("scope 算出 Δ 行数占比", 0 < d["delta_pct"] < 100)
    check("scope 逐分册标注是否命中 Δ",
          [b["in_delta"] for b in d["books"]] == [True, False])
    rc, d = run("scope", "--full-dir", str(root / "不存在"), "--delta", "x")
    check("★ scope 目录不存在 → JSON 模式下退出码也必须非 0（曾 fail-open 返 0）",
          rc != 0 and d.get("ok") is False and d.get("error") == "full-dir-not-found")
    # `--json` 挂在子命令后是最自然的写法，必须与挂全局位等效
    cp_a = subprocess.run([sys.executable, script, "scope", "--full-dir", str(full), "--json"],
                          capture_output=True, text=True)
    cp_b = subprocess.run([sys.executable, script, "--json", "scope", "--full-dir", str(full)],
                          capture_output=True, text=True)
    check("★ --json 放子命令后 / 放全局位 两种写法等效",
          cp_a.returncode == 0 and cp_b.returncode == 0 and cp_a.stdout == cp_b.stdout)
    rc, d = run("scope", "--full-dir", str(full))
    check("scope 不给 --delta → 0 命中（不误判全量）", d["delta_books"] == 0 and d["delta_pct"] == 0.0)

    # --- rollforward：只替换点名章节
    newbook = root / "staging_01.md"
    newbook.write_text("# 用户域\n\n新前言\n\n## 数据模型\n新数据模型\n\n## 接口\n新接口\n", encoding="utf-8")
    out = root / "out_01.md"
    rc, d = run("rollforward", "--old", str(full / "01_用户域.md"), "--new", str(newbook),
                "--sections", "数据模型", "--out", str(out))
    check("rollforward 成功", rc == 0 and d.get("ok") is True)
    merged = out.read_text(encoding="utf-8")
    check("★ 点名章节被替换为新内容", "新数据模型" in merged and "旧数据模型" not in merged)
    check("★ 未点名章节原样保留（接口没点名，必须还是旧的）",
          "旧接口" in merged and "新接口" not in merged)
    check("★ 未点名章节不丢（时序只在旧分册里，必须还在）", "旧时序" in merged)
    check("前言段保留", "前言段" in merged)
    check("报告区分 rewritten / kept", d["rewritten"] == 1 and d["kept"] == 2)

    # --- 点名章节在新内容里不存在 → 必须报错，绝不静默丢章节
    rc, d = run("rollforward", "--old", str(full / "01_用户域.md"), "--new", str(newbook),
                "--sections", "数据模型,压根不存在的章节", "--out", str(root / "x.md"))
    check("★ 点名章节新内容里缺失 → exit 非 0 且不写出文件",
          rc != 0 and d.get("error") == "sections-missing-in-new"
          and "压根不存在的章节" in d.get("missing", [])
          and not (root / "x.md").exists())

    # --- 新分册里新增、且被点名的章节 → 追加到末尾（不静默丢）
    newbook2 = root / "staging_02.md"
    newbook2.write_text("# 用户域\n\n## 数据模型\n新模型\n\n## 新增的安全章节\n安全内容\n", encoding="utf-8")
    out2 = root / "out_02.md"
    rc, d = run("rollforward", "--old", str(full / "01_用户域.md"), "--new", str(newbook2),
                "--sections", "数据模型,新增的安全章节", "--out", str(out2))
    m2 = out2.read_text(encoding="utf-8")
    check("★ 新增且点名的章节被追加，不丢", rc == 0 and "安全内容" in m2)
    check("追加的同时旧有未点名章节仍在", "旧接口" in m2 and "旧时序" in m2)
    check("报告里标 appended",
          any(r["action"] == "appended" for r in d["sections"]))

    # --- 输入不可读 → fail 而非静默产出空文件
    rc, d = run("rollforward", "--old", str(root / "没有这个文件.md"), "--new", str(newbook),
                "--sections", "数据模型", "--out", str(root / "y.md"))
    check("旧分册不可读 → 报错且不产出", rc != 0 and not (root / "y.md").exists())

    shutil.rmtree(root, ignore_errors=True)


def test_mirror_check_ignores_pyc_and_skill_ref_drift():
    """SKILL 内部文件引用有效性门。"""
    import importlib.util
    print("【SKILL 引用漂移门】")
    repo = Path(HERE).parents[2]


    # ② SKILL 内部文件引用门：正例通过、反例（引用不存在的 SKILL 文件）必须检出
    gate = repo / ".aidp/scripts/check_skill_ref_drift.py"
    cp = subprocess.run([sys.executable, str(gate), "--root", str(repo), "--json"],
                        capture_output=True, text=True)
    data = json.loads(cp.stdout)
    check("本仓 SKILL 内部文件引用全部有效",
          data["applicable"] and not data["findings"] and data["checked"] > 0)

    fake = Path(tempfile.mkdtemp())
    (fake / ".aidp/skills/demo-skill/scripts").mkdir(parents=True)
    (fake / ".aidp/skills/demo-skill/scripts/real.py").write_text("x", encoding="utf-8")
    (fake / ".aidp/commands").mkdir(parents=True)
    (fake / ".aidp/commands/c.md").write_text(
        "调 `demo-skill/scripts/real.py` 与 `demo-skill/scripts/gone.py`\n"
        "以及 `demo-skill/references/nope.md`\n"
        "还有未安装的 `other-skill/scripts/x.py`（不归本门管）\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, str(gate), "--root", str(fake), "--json"],
                        capture_output=True, text=True)
    data = json.loads(cp.stdout)
    refs = {f["ref"] for f in data["findings"]}
    check("悬空的 SKILL 脚本被检出", "demo-skill/scripts/gone.py" in refs)
    check("悬空的 SKILL reference 被检出", "demo-skill/references/nope.md" in refs)
    check("存在的 SKILL 文件不误报", "demo-skill/scripts/real.py" not in refs)
    check("未安装 SKILL 的路径不归本门管", not any("other-skill" in r for r in refs))
    check("反例退出码非 0", cp.returncode == 1)
    nos = Path(tempfile.mkdtemp())
    cp = subprocess.run([sys.executable, str(gate), "--root", str(nos), "--json"],
                        capture_output=True, text=True)
    check("无 skills 目录时 N/A 跳过 exit 0",
          cp.returncode == 0 and json.loads(cp.stdout)["applicable"] is False)
    shutil.rmtree(fake, ignore_errors=True)
    shutil.rmtree(nos, ignore_errors=True)


def test_autopilot_mainline_regressions():
    """autopilot 主干路径的四条 Critical 回归（printf 转义 / 零写入方键 / 游标越权 / 冻结无解冻）。"""
    print("【autopilot 主干：转义 / 零写入方键 / 游标越权 / 冻结解冻】")
    repo = Path(HERE).parents[2]
    fl = repo / ".aidp/flows/sprint-autopilot"

    # C1: shell 单引号内的双重转义 —— printf '%s\\n' 会输出字面 \n、grep -qx 恒不匹配
    p35 = (fl / "phase-3-5.md").read_text(encoding="utf-8")
    check("★ C1 phase-3-5 无 printf '%s\\n' 双重转义", "printf '%s\\\\n'" not in p35)
    check("C1 正确写法在位", "printf '%s\\n'" in p35)
    gate = repo / ".aidp/scripts/check_flow_shell_escapes.py"
    check("C1 有机器门守住", gate.is_file())
    cp = subprocess.run([sys.executable, str(gate), "--root", str(repo), "--json"],
                        capture_output=True, text=True)
    check("C1 全仓无双重转义", not json.loads(cp.stdout)["findings"])

    # C2: 读的 baseline 键必须有写入方 —— 否则每 tick 必 exit 1、游标永不推进
    # 判「实际 get 调用」而非「字符串出现」——注释里点名这两个键正是修复留痕，不该被判失败
    for key in ("sprints.$SPRINT_NO.last_result", "sprints.remaining"):
        check(f"★ C2 不再 get 零写入方键 {key}", f'get "{key}"' not in p35)
    check("C2 改用 close 归档产物作判据", "无 close 归档产物" in p35)

    # C3: 归档版的游标不得代写下一版的阶段
    p2 = (fl / "phase-2.md").read_text(encoding="utf-8")
    check("★ C3 Phase 2 出口 next_phase 恒 done",
          'run-state "2-prerelease" "done" ""' in p2
          and "'3.0-route'" not in p2)
    check("C3 根因已入 rationale",
          "归档版的游标不得代写下一版的阶段" in (fl / "rationale.md").read_text(encoding="utf-8"))

    # C4: 0.1 之后产生的每个 freeze reason 都必须有解冻写入者
    unfreeze = repo / ".aidp/scripts/autopilot_unfreeze.py"
    check("C4 解冻脚本存在", unfreeze.is_file())
    blob = "".join((fl / n).read_text(encoding="utf-8")
                   for n in sorted(x.name for x in fl.glob("*.md")))
    for reason in ("prd-root-missing", "stale-active-sprint", "preflight-gate"):
        check(f"★ C4 {reason} 有解冻写入者",
              f"autopilot_unfreeze.py {reason}" in blob)
    # 解冻脚本语义：只清同作用域、不误清他人
    tmp = Path(tempfile.mkdtemp())
    (tmp / ".aidp/scripts").mkdir(parents=True)
    shutil.copy(repo / ".aidp/scripts/baseline_edit.py", tmp / ".aidp/scripts/baseline_edit.py")
    (tmp / "memory").mkdir()
    (tmp / "memory/.sprint-autopilot-baseline.json").write_text(
        json.dumps({"preflight_fail_reason": "prd-root-missing",
                    "preflight_fail_streak": 3, "preflight_frozen_at": "2026-09-02T00:00:00"}),
        encoding="utf-8")
    cp = subprocess.run([sys.executable, str(unfreeze), "stale-active-sprint",
                         "--root", str(tmp), "--json"], capture_output=True, text=True)
    check("C4 不误清他人作用域的冻结", json.loads(cp.stdout)["cleared"] is False)
    cp = subprocess.run([sys.executable, str(unfreeze), "prd-root-missing",
                         "--root", str(tmp), "--json"], capture_output=True, text=True)
    check("C4 同作用域正确解冻", json.loads(cp.stdout)["cleared"] is True)
    cp = subprocess.run([sys.executable, str(unfreeze), "prd-root-missing",
                         "--root", str(tmp), "--json"], capture_output=True, text=True)
    check("C4 幂等（已清后再跑不报错）",
          cp.returncode == 0 and json.loads(cp.stdout)["cleared"] is False)
    cp = subprocess.run([sys.executable, str(unfreeze), "bogus-reason",
                         "--root", str(tmp), "--json"], capture_output=True, text=True)
    check("C4 未知 reason 被拒", cp.returncode == 2)
    shutil.rmtree(tmp, ignore_errors=True)


def test_release_speedups_and_gate_fixes():
    """发布基线相关判据：布局探测统一 / SQL 列注释误报 / 共用占位豁免 / build 补登记 / 版本改名。"""
    print("【发布基线：布局探测 / 列注释误报 / 占位豁免 / build 补登记 / 版本改名】")
    scripts = Path(HERE).parents[0]

    # P5① SQL：COMMENT ON COLUMN 的列限定不得被当成 schema 前缀
    sys.path.insert(0, str(scripts))
    import release_baseline_check as RB
    pat = RB.ENV_BOUND_SQL[0][0]
    comment_sql = ('CREATE TABLE IF NOT EXISTS "T_USER" ("ID" VARCHAR(32));\n'
                   'COMMENT ON COLUMN "T_USER"."ID" IS \'主键\';\n'
                   'COMMENT ON TABLE "T_USER" IS \'用户表\';')
    real_bound = 'CREATE TABLE "PROD_SCHEMA"."T_ORDER" ("ID" VARCHAR(32));'
    check("★ P5① 列注释不再误判为 schema 前缀",
          len(pat.findall(RB.COMMENT_ON_RE.sub(" ", comment_sql))) == 0)
    check("P5① 真 schema 前缀仍被检出",
          len(pat.findall(RB.COMMENT_ON_RE.sub(" ", real_bound))) == 1)

    # P5② 占位变量「刻意共用」豁免
    cfg = Path(tempfile.mkdtemp())
    (cfg / "bootstrap.yml").write_text(
        "spring:\n"
        "  cloud:\n"
        "    nacos:\n"
        "      config:\n"
        "        # baseline-check: shared-placeholder 配置中心与注册中心同一实例\n"
        "        server-addr: ${NACOS_SERVER_ADDR:FILL_ME}\n"
        "      discovery:\n"
        "        # baseline-check: shared-placeholder 同上\n"
        "        server-addr: ${NACOS_SERVER_ADDR:FILL_ME}\n"
        "  datasource:\n"
        "    # 主库\n"
        "    url: ${SPRING_DATASOURCE_URL:FILL_ME}\n"
        "    # 从库（未声明共用，应报错）\n"
        "    slave-url: ${SPRING_DATASOURCE_URL:FILL_ME}\n", encoding="utf-8")
    rep = RB.Report()
    RB.check_configs(cfg, rep)
    errs = [str(x) for x in rep.errors if "占位变量" in str(x)]
    notes = [str(x) for x in rep.notes if "占位变量" in str(x)]
    check("★ P5② 声明共用的占位不再判错", not any("NACOS_SERVER_ADDR" in e for e in errs))
    check("P5② 豁免项仍可见（降 note，不是静默后门）",
          any("NACOS_SERVER_ADDR" in n for n in notes))
    check("P5② 未声明的撞名仍 ERROR",
          any("SPRING_DATASOURCE_URL" in e for e in errs))
    shutil.rmtree(cfg, ignore_errors=True)

    # P6 set current_build 时自动登记 builds[]
    be = Path(tempfile.mkdtemp())
    (be / "memory").mkdir()
    (be / "memory/.sprint-autopilot-baseline.json").write_text('{"versions":{}}', encoding="utf-8")
    subprocess.run([sys.executable, str(scripts / "baseline_edit.py"),
                    "--version", "V0.1.0", "set", "current_build", "V0.1.0_build1004"],
                   capture_output=True, text=True, cwd=str(be))
    data = json.loads((be / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
    blds = data["versions"]["V0.1.0"].get("builds") or []
    check("★ P6 set current_build 自动登记进 builds[]",
          any(b.get("build") == "V0.1.0_build1004" for b in blds))
    subprocess.run([sys.executable, str(scripts / "baseline_edit.py"),
                    "--version", "V0.1.0", "set", "current_build", "V0.1.0_build1004"],
                   capture_output=True, text=True, cwd=str(be))
    data2 = json.loads((be / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
    check("P6 幂等（重复 set 不产生重复条目）",
          len(data2["versions"]["V0.1.0"]["builds"]) == 1)
    shutil.rmtree(be, ignore_errors=True)

    # P3 版本改名：目录/文件名/正文全改，范式示例与测试夹具豁免
    rv = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", str(rv)], check=False, capture_output=True)
    for d in ("docs/requirements/V0.12.2", "docs/plans/V0.12.2", "memory/V0.12.2/u",
              ".aidp/skills/demo", ".aidp/scripts/tests"):
        (rv / d).mkdir(parents=True, exist_ok=True)
    (rv / "docs/requirements/V0.12.2/01_需求.md").write_text("本版 V0.12.2", encoding="utf-8")
    (rv / "docs/V0.12.2_报告.md").write_text("x", encoding="utf-8")
    (rv / ".aidp/skills/demo/SKILL.md").write_text("示例 V0.12.2 样例", encoding="utf-8")
    (rv / ".aidp/scripts/tests/t.py").write_text("假版本 V0.12.2", encoding="utf-8")
    cp = subprocess.run([sys.executable, str(scripts / "rename_version.py"),
                         "V0.12.2", "V0.13.0", "--root", str(rv), "--apply", "--json"],
                        capture_output=True, text=True)
    res = json.loads(cp.stdout)
    check("★ P3 版本目录已改名", (rv / "docs/requirements/V0.13.0").is_dir()
          and not (rv / "docs/requirements/V0.12.2").exists())
    check("P3 空目录也改名（git mv 失败回退 mv）", (rv / "memory/V0.13.0/u").is_dir())
    check("P3 basename 含版本号的文件已改名", (rv / "docs/V0.13.0_报告.md").is_file())
    check("P3 正文已替换",
          "V0.13.0" in (rv / "docs/requirements/V0.13.0/01_需求.md").read_text(encoding="utf-8"))
    check("★ P3 范式示例未被误改",
          "V0.12.2" in (rv / ".aidp/skills/demo/SKILL.md").read_text(encoding="utf-8"))
    check("★ P3 测试夹具未被误改",
          "V0.12.2" in (rv / ".aidp/scripts/tests/t.py").read_text(encoding="utf-8"))
    paths = {r["path"] for r in res["residue"]}
    check("P3 剩余清单点名两处豁免并给理由",
          ".aidp/skills/demo/SKILL.md" in paths and ".aidp/scripts/tests/t.py" in paths
          and all(r["reason"] for r in res["residue"]))
    check("P3 豁免项不算未解决（退出码 0）", cp.returncode == 0)
    cp2 = subprocess.run([sys.executable, str(scripts / "rename_version.py"),
                          "V0.12.2", "V0.12.2", "--root", str(rv)], capture_output=True, text=True)
    check("P3 新旧同号被拒", cp2.returncode == 2)
    shutil.rmtree(rv, ignore_errors=True)


def test_autopilot_deadlocks_and_gate_bypasses():
    """收尾门 stage / 降级落盘 / 游标推进 / 解冻探针 / 去重门 / 守卫旁路。"""
    print("【无人值守死锁 + 守卫旁路】")
    repo = Path(HERE).parents[2]
    fl = repo / ".aidp/flows/sprint-autopilot"
    ft = repo / ".aidp/flows/sprint-aiauto-test"
    scripts = Path(HERE).parents[0]

    # C5 收尾门 stage：双 loop 下 DELEGATED 恒空，必须有第二个 skeleton 条件
    p39 = (fl / "phase-3-9.md").read_text(encoding="utf-8")
    check("★ C5 GATE_STAGE 有 TEST_ALIVE 兜底条件",
          "TEST_ALIVE" in p39 and 'test-loop-alive' in p39)
    # ★ 判据本身是「不再各写一套内联 python」，不是「调够几次」。原先按调用次数 >=2 断言，
    #   是因为当时 GATE_STAGE 与 ③ 各调一次；现在 ③ 复用 GATE_STAGE 那次的 $TEST_ALIVE，
    #   一次即可 —— 按次数断言会把"消除重复调用"这个改进judge成回归。
    check("C5 判据下沉到 gate（委派子命令，且无内联心跳 python）",
          "test-loop-alive --version" in p39
          and "aiauto_test_heartbeat_at" not in p39.replace("勿误读 aiauto_tested_at", ""))
    # ★ 根因分诊必须在 ceremony 闸【之前】：闸失败分支以 exit 0 收尾，排在它后面的
    #   test_loop_missing_streak 累加在"测试链路未挂载"这个唯一该生效的场景里恒不执行。
    check("★ 测试链路缺失分诊先于 ceremony 闸（否则 streak 永不累加、冻结原因写成 handoff-exhausted）",
          p39.index("test_loop_missing_streak") < p39.index('python3 "$GATE" check'))
    check("★ 达阈冻结原因 = config-missing（可随心跳自动解冻），不是人工解冻类",
          "--reason config-missing" in p39)
    gate = repo / ".aidp/scripts/autopilot-ceremony-gate.py"
    gsrc = gate.read_text(encoding="utf-8")
    check("C5/H11 gate 提供统一 test_loop_alive", "def test_loop_alive(" in gsrc)
    check("★ H11 3b2 不再只看心跳", "_hb_fresh = test_loop_alive(_bl, V)" in gsrc)

    # test_loop_alive 三态（心跳新鲜但被本版阻塞 → 不算活）
    tl = Path(tempfile.mkdtemp()); (tl / "memory").mkdir()
    import datetime
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    bl = tl / "memory/.sprint-autopilot-baseline.json"
    def probe(extra):
        d = {"aiauto_test_heartbeat_at": now}; d.update(extra)
        bl.write_text(json.dumps(d), encoding="utf-8")
        cp = subprocess.run([sys.executable, str(gate), "test-loop-alive",
                             "--version", "V0.1.0", "--root", str(tl)],
                            capture_output=True, text=True)
        return cp.stdout.strip()
    check("心跳新鲜且无阻塞 → 活", probe({}) == "1")
    check("★ 心跳新鲜但本版被阻塞 → 不算活",
          probe({"aiauto_blocked_reason": "frozen:unconverged@V0.1.0"}) == "0")
    check("阻塞指向别的版本 → 仍算活",
          probe({"aiauto_blocked_reason": "frozen:unconverged@V0.9.9"}) == "1")
    shutil.rmtree(tl, ignore_errors=True)

    # H9 通知降级必须落盘（只置 shell 变量跨调用即丢）
    p02 = (fl / "phase-0-2.md").read_text(encoding="utf-8")
    check("★ H9 通知降级落盘而非只置 shell 变量",
          "set notify_enabled false" in p02 and "shell state 不跨 Bash 调用" in p02)

    # H12 cicd_skipped 时游标必须推出 3.2.1-probe
    p37 = (ft.parent / "sprint-autopilot/phase-3-7.md").read_text(encoding="utf-8")
    check("★ H12 cicd_skipped 分支直接进 3.3-audit",
          'CICD_SKIPPED' in p37 and '"3.2.1-probe" "3.3-audit"' in p37)

    # H8/G-A8 解冻探针：unconverged 可解冻、release-blocked 仅人工
    uf = scripts / "autopilot_unfreeze.py"
    us = uf.read_text(encoding="utf-8")
    check("★ H8 unconverged 纳入新部署解冻类", '"unconverged"' in us and "_UNFREEZE_BY_DEPLOY" in us)
    check("★ G-A8 release-blocked 归仅人工类", '"release-blocked"' in us and "_HUMAN_ONLY" in us)
    uz = Path(tempfile.mkdtemp()); (uz / "memory").mkdir()
    def aiauto(reason, dep):
        (uz / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(
            {"versions": {"V0.1.0": {"freeze_reason": reason,
                                     "aiauto_frozen_at": "2026-09-01T10:00:00",
                                     "last_deployed_at": dep}}}), encoding="utf-8")
        cp = subprocess.run([sys.executable, str(uf), "--aiauto-probe", "V0.1.0",
                             "--root", str(uz), "--json"], capture_output=True, text=True)
        return json.loads(cp.stdout)
    check("H8 unconverged + 新部署 → 可解冻",
          aiauto("unconverged", "2026-09-02T10:00:00")["unfreeze"] is True)
    check("H8 unconverged + 旧部署 → 保持冻结",
          aiauto("unconverged", "2026-08-31T10:00:00")["unfreeze"] is False)
    check("★ G-A8 release-blocked 即使有新部署也不解冻",
          aiauto("release-blocked", "2026-09-02T10:00:00")["unfreeze"] is False)
    shutil.rmtree(uz, ignore_errors=True)
    # 交接类也要在 flow 的排除列表里
    # ★ flow 不再内联 case（rationale「冻结分类」明令禁止复写：曾因此让 unconverged 整类
    #   漏在 case 之外）。断言随实现迁移：flow 必须【委派脚本】，交接类由脚本的 _HUMAN_ONLY 兜。
    _f06 = (ft / "phase-0-6.md").read_text(encoding="utf-8")
    check("G-A8 flow 委派 autopilot_unfreeze.py --aiauto-probe（不内联 case）",
          "--aiauto-probe" in _f06 and "handoff-exhausted|stuck-phase|release-blocked" not in _f06)
    _uzsrc = (Path(HERE).parents[0] / "autopilot_unfreeze.py").read_text(encoding="utf-8")
    check("G-A8 交接类在脚本 _HUMAN_ONLY 里（唯一判据处）",
          all(r in _uzsrc.split("_HUMAN_ONLY")[1].split("}")[0]
              for r in ("handoff-exhausted", "stuck-phase", "release-blocked")))

    # H10 去重门第五个条件
    pt06 = (ft / "phase-0-6.md").read_text(encoding="utf-8")
    check("★ H10 去重门要求本 build 已 finalize",
          'RPT_FIN' in pt06 and '[ "$RPT_FIN" = "true" ]' in pt06)

    # G-CHAIN-1 守卫两处旁路
    cc = (scripts / "check_chain_unattended.py").read_text(encoding="utf-8")
    # ⛔ 断言钉**意图**不钉字面形状：免检面 = 「本次调用自身的参数 + 紧跟的 [--xxx] 序列」，
    #    ⛔ 不是"整行任意位置出现过该词"（那会让括注里提一句就整行豁免）。
    check("★ G-CHAIN-1 免检收窄到该次调用自身（含 `[--unattended]` 变体）",
          '_sig = m.group(2) + (_opt.group(0) if _opt else "")' in cc
          and 'if "--unattended" in ln:' not in cc)
    check("★ G-CHAIN-1 免检认 --no-loop（它同样是 LOOP_UNATTENDED=1 信号，只认前者会假红）",
          '"--no-loop" in _sig' in cc)
    check("★ G-CHAIN-1 候选面含纯 flag 调用", "--[a-z][a-z-]*" in cc)

    # H7 跨围栏：新判据 + 该分片已合并围栏
    vr = (scripts / "check_flow_var_refs.py").read_text(encoding="utf-8")
    check("★ H7 守卫新增 cross-fence 判据", '"kind": "cross-fence"' in vr)
    cf = Path(tempfile.mkdtemp())
    (cf / ".aidp/flows/x").mkdir(parents=True)
    (cf / ".aidp/flows/x/a.md").write_text(
        "> ```bash\n> NEXT_X=\"v\"\n> ```\n\n```bash\nrun \"${NEXT_X}\"\n```\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, str(scripts / "check_flow_var_refs.py"),
                         "--root", str(cf), "--json"], capture_output=True, text=True)
    kinds = {f.get("kind") for f in json.loads(cp.stdout)["findings"]}
    check("H7 反例：引用块赋值+围栏引用被检出", "cross-fence" in kinds)
    shutil.rmtree(cf, ignore_errors=True)

    # G-RELEASE-4 白名单：tag 授权门必在其中 + 两侧计数声明一致
    # ⛔ 不写死"共六处"：白名单会随门的自动化而增删，写死的数必漂（本仓已实测漂过一次）。
    #    真正要锁的是两件事——① 唯一的 destructive 门没被漏掉 ② 两处计数声明不打架。
    _CN = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
    r1 = (repo / ".aidp/flows/version/release-1.md").read_text(encoding="utf-8")
    vm = (repo / ".aidp/commands/version.md").read_text(encoding="utf-8")
    m1 = re.search(r"穷举白名单（发布路径 Step 3\.x 共\*{0,2}([一二三四五六七八九十])\*{0,2}处", r1)
    m2 = re.search(r"结构化门共\*{0,2}([一二三四五六七八九十])\*{0,2}处", vm)
    check("★ G-R4 白名单含 tag 授权门（唯一 destructive 门，绝不能漏）",
          "3.4.2.2" in r1 and "3.4.2.2" in vm)
    check("★ G-R4 两处白名单计数声明都在且一致",
          bool(m1) and bool(m2) and _CN.get(m1.group(1)) == _CN.get(m2.group(1)))
    check("★ G-R4 白名单条目数与声明数相符",
          bool(m1) and len(re.findall(r"^  \d+\. \*\*Step ", r1, re.M)) == _CN.get(m1.group(1)))
    check("G-R4 情况 C 不再宣称无条件不弹窗",
          "强制重打 tag + 强制重建版本分支" not in vm)

    # G-BATCH-2 Step 0.0 不再是询问门
    sb = (repo / ".aidp/commands/sprint-batch.md").read_text(encoding="utf-8")
    check("★ G-B2 Step 0.0 改为纯 INFO 不再二选一",
          '输入 "y" 或 "继续"' not in sb and "本提示是【纯 INFO】" in sb)
    # ⛔ 断言用「不在此列」而非「已不在此列」：后者是"原来在、现在不在"的变更叙述，
    #   违反约定 30（正文只陈述最终行为）——门与被门约束的正文口径必须一致。
    check("G-B2 体外豁免措辞已订正", "Step 0.0 不在此列" in sb)

    # G-AUTOPILOT-1/6 退出前跑 gate
    p1 = (fl / "phase-1.md").read_text(encoding="utf-8")
    check("★ G-A1 1.5 退出前内联 gate 调用",
          "autopilot-ceremony-gate.py check" in p1 and "--no-pipeline-reason" in p1)

    # 跨分片取值：TESTPLAN_DEPLOY_URL 必须落盘，否则 Phase 0.7 的优先级 1 形同虚设
    p01 = (ft / "phase-0-1.md").read_text(encoding="utf-8")
    p07 = (ft / "phase-0-7.md").read_text(encoding="utf-8")
    check("★ 测试环境 URL 赋值后落盘 baseline",
          "set testplan_deploy_url" in p01)
    check("★ Phase 0.7 从 baseline 读而非读 shell 变量",
          "versions.{V}.testplan_deploy_url" in p07
          and "get testplan_deploy_url" in p07)


def test_upstream_doc_split_underscore_exemption():
    """各 SKILL 的 check_doc_split.py 必须跳过 `_` 前缀文件（三份副本行为一致）。

    约定 15 给 `_开发期{族}增量.md` 开了「不占序号、不进索引、不参与拆分判定」的例外；
    若任一副本不跳过，增量册会被判「未使用两位数字前缀」error，四条命令会**恒红**，
    且没有别的地方会发现。
    """
    print("【SKILL doc_split 的 _ 前缀例外】")
    repo = Path(HERE).parents[2]
    d = Path(tempfile.mkdtemp()) / "d"
    d.mkdir(parents=True)
    (d / "00_索引.md").write_text("# 索引\n\n- [01_研发需求.md](01_研发需求.md)\n", encoding="utf-8")
    (d / "01_研发需求.md").write_text("# 研发需求\n" + "正文\n" * 200, encoding="utf-8")
    (d / "_开发期需求增量.md").write_text("# 增量\n\n## 待级联\n- C-001 · 09-01 10:00 · x · s1\n", encoding="utf-8")
    for skill in ("dev-execution-planner", "dev-logic-architect", "ux-logic-extractor"):
        script = repo / f".aidp/skills/{skill}/scripts/check_doc_split.py"
        if not script.is_file():
            check(f"{skill} 有 check_doc_split.py", False)
            continue
        cp = subprocess.run([sys.executable, str(script), str(d), "--json"],
                            capture_output=True, text=True)
        try:
            data = json.loads(cp.stdout)
        except ValueError:
            check(f"{skill} 输出可解析 JSON", False)
            continue
        underscore_issues = [i for i in data.get("issues", [])
                             if str(i.get("file", "")).startswith("_")]
        check(f"★ {skill} 跳过 `_` 前缀文件（0 条相关 issue）", not underscore_issues)
        check(f"{skill} sub_docs 不计入 `_` 文件",
              data.get("summary", {}).get("sub_docs") == 1)
    shutil.rmtree(d.parent, ignore_errors=True)

    # 命令端不留「过渡期已知误报」这类豁免声明
    stale = []
    for cmd in ("sprint-requirements", "sprint-design", "sprint-plan", "sprint-selftest"):
        txt = (repo / f".aidp/commands/{cmd}.md").read_text(encoding="utf-8")
        if "过渡期已知误报" in txt:
            stale.append(cmd)
    check("★ 命令端不留过期豁免声明", not stale)


def test_audit_round_fixes():
    """回归锁：免检变体 / 门接线 / 发明入参 / 选版排除 / Stop hook 判据。"""
    print("【链式调用免检变体 / SKILL 入参 / 尾段选版 / Stop hook / 分组计数】")
    repo = Path(HERE).parents[2]
    scripts = Path(HERE).parents[0]

    # ★ G-CHAIN-1 免检必须认 `[--unattended]` 变体（上轮收窄判据时把全部合规站点误判成未透传）
    cu = Path(tempfile.mkdtemp())
    (cu / ".aidp/commands").mkdir(parents=True)
    (cu / ".aidp/flows/x").mkdir(parents=True)
    for c in ("sprint-close", "sprint-start", "version"):
        (cu / f".aidp/commands/{c}.md").write_text("- `--unattended`：无人值守\n", encoding="utf-8")
    (cu / ".aidp/flows/x/a.md").write_text(
        "合规：调 `/sprint-close {NNN} [--unattended]`\n"
        "裸调：调 `/sprint-start {NNN}`\n"
        "括注：调 `/version {V} --from-autopilot`（★ 不带 --unattended）\n", encoding="utf-8")
    cp = subprocess.run([sys.executable, str(scripts / "check_chain_unattended.py"),
                         "--root", str(cu), "--json"], capture_output=True, text=True)
    calls = {x["call"] for x in json.loads(cp.stdout).get("new", [])}
    check("★ `[--unattended]` 变体不再误报", not any("sprint-close" in c for c in calls))
    check("裸调用仍被检出", any("sprint-start" in c for c in calls))
    check("★ 括注里提到该词不构成免检（措辞免检 = 守卫可绕过）",
          any("version" in c for c in calls))
    shutil.rmtree(cu, ignore_errors=True)

    # 两道此前"有守卫无闸门"的门必须挂进 verify

    # 命令端不得为上游 SKILL 发明入参
    for cmd, skill in (("sprint-requirements", "ux-logic-extractor"),
                       ("sprint-design", "dev-logic-architect"),
                       ("sprint-plan", "dev-execution-planner")):
        txt = (repo / f".aidp/commands/{cmd}.md").read_text(encoding="utf-8")
        skl = list((repo / f".aidp/skills/{skill}").rglob("*"))
        defined = any(f.is_file() and "qr_mode" in f.read_text(encoding="utf-8", errors="ignore")
                      for f in skl)
        check(f"★ {cmd} 不再传 SKILL 未定义的 qr_mode",
              not defined and "写 `qr_mode = A`" not in txt and "`qr_mode = B`" not in txt)

    # 选版必须排除准发布版（hold 游标会让同版同时是 PRE_RELEASE 和 TARGET）
    # ★ 0.3.4 已二次切分到 phase-0-6b2.md：两片合读，⛔ 别只读主片
    #   （只读主片会让这些断言在拆片后静默变绿——断言对象根本不在那里了）
    p06 = ((repo / ".aidp/flows/sprint-autopilot/phase-0-6.md").read_text(encoding="utf-8")
           + "\n"
           + (repo / ".aidp/flows/sprint-autopilot/phase-0-6b2.md").read_text(encoding="utf-8"))
    # ⛔ 排除必须**限定到 hold 游标**：末个 Sprint 一关闭该版当场就是 S2（= PRE_RELEASE_VERSION），
    #   按 `== PRE_RELEASE_VERSION` 一刀切等于排除子句恰好只在规则 1 唯一要救的场景里生效、两条规则互相归零
    #   → TARGET 恒 null → 只跑 Phase 2 → 门 0a 因 last_deployed_at 空而 hold → 3 tick 写
    #   deploy-unreachable（诊断与事实相反）→ 12 tick 复探清冻结 → 再 3 tick 重冻，15-tick 周期永动。
    check("★ 尾段续跑的排除限定到 hold 游标（⛔ 不按 == PRE_RELEASE_VERSION 一刀切）",
          "hold 游标" in p06 and "一刀切" in p06)

    # Stop hook 的 wbt 判据必须与 phase-3-9 同口径
    hk = (repo / ".aidp/hooks/autopilot-stop-guard.py").read_text(encoding="utf-8")
    check("★ Stop hook 不再只看 aiauto_delegated_at",
          "test-loop-alive" in hk and "b.get(\"aiauto_delegated_at\") or _alive" in hk)

    # 恒 exit 2 的 Critical 门必须标注真实调用式
    st = (repo / ".aidp/flows/sprint-design/step-1.6-落盘后回检.md").read_text(encoding="utf-8")
    # ★ SQL 版本隔离门按两轨布局传参（`docs/deployment --version`），脚本清单委派 SKILL QR 单一信源
    check("★ 回检委派 dla flow-qr-dispatch 且 SQL 隔离门按两轨布局传参",
          "flow-qr-dispatch.md" in st and "docs/deployment --version" in st)


    # check_count_claims 的测试分组真值须覆盖两种标题形态
    cc = (scripts / "check_count_claims.py").read_text(encoding="utf-8")
    check("★ 分组真值同时统计 `【…】` 与 `[NN]`",
          "【" in cc and "\\[\\d+\\]" in cc)


def test_leftover_batch_fixes():
    """回归锁：层级/占位符/回落/枚举拆分/新判据。"""
    print("【版本层字段 / 占位符 / 回落 / 枚举拆分】")
    repo = Path(HERE).parents[2]
    scripts = Path(HERE).parents[0]
    sys.path.insert(0, str(scripts))

    # aiauto_tested_at 是版本级，不能挤在 --build 里
    p33 = (repo / ".aidp/flows/sprint-aiauto-test/phase-3-3.md").read_text(encoding="utf-8")
    check("★ aiauto_tested_at 写版本层（三个读侧都在版本层）",
          '--build "$BUILD" set status tested\n' in p33 and "$BEV set aiauto_tested_at @now" in p33)

    # bash 围栏里不得残留 {V}/{BUILD} 字面占位符 + 门能抓到
    esc = subprocess.run([sys.executable, str(scripts / "check_flow_shell_escapes.py"),
                          "--root", str(repo), "--json"], capture_output=True, text=True)
    check("★ flows 内无字面 {V}/{BUILD} 占位符",
          not [f for f in json.loads(esc.stdout)["findings"] if f.get("kind") == "placeholder"])
    ph = Path(tempfile.mkdtemp())
    (ph / ".aidp/flows/x").mkdir(parents=True)
    (ph / ".aidp/flows/x/a.md").write_text(
        '```bash\nD="docs/reports/{V}/x"; echo "$D"\n```\n', encoding="utf-8")
    cp = subprocess.run([sys.executable, str(scripts / "check_flow_shell_escapes.py"),
                         "--root", str(ph), "--json"], capture_output=True, text=True)
    check("占位符反例被检出", any(f.get("kind") == "placeholder"
                                  for f in json.loads(cp.stdout)["findings"]))
    shutil.rmtree(ph, ignore_errors=True)

    # TARGET_VERSION / WILL_BROWSER_TEST 的登记与回落
    import autopilot_tick_flags as TF
    check("★ TARGET_VERSION 已登记进 aiauto-test",
          "TARGET_VERSION" in TF.DERIVED_VARS.get("aiauto-test", set()))
    check("★ WILL_BROWSER_TEST 有版本级回落",
          TF.BASELINE_FALLBACK.get("WILL_BROWSER_TEST") == ("version", "will_browser_test"))

    # prd-missing 与 config-missing 判据必须分离（否则自己的心跳解自己的冻）
    import autopilot_unfreeze as UF
    check("★ config-missing 走心跳专判", "config-missing" in UF._UNFREEZE_BY_HEARTBEAT)
    check("★ prd-missing 走 PRD mtime、不认心跳",
          "prd-missing" in UF._UNFREEZE_BY_PRD
          and "prd-missing" not in UF._UNFREEZE_BY_HEARTBEAT)
    uz = Path(tempfile.mkdtemp())
    (uz / "memory").mkdir(); (uz / "docs/requirements/V0.1.0/产品提供").mkdir(parents=True)
    (uz / "memory/.sprint-autopilot-baseline.json").write_text(json.dumps(
        {"aiauto_test_heartbeat_at": "2026-09-03T12:00:00+08:00",
         "versions": {"V0.1.0": {"freeze_reason": "prd-missing",
                                 "aiauto_frozen_at": "2026-09-03T10:00:00+08:00"}}}), encoding="utf-8")
    check("★ prd-missing 不被自己刷的心跳解冻",
          UF.aiauto_probe(str(uz), "V0.1.0")["unfreeze"] is False)
    shutil.rmtree(uz, ignore_errors=True)

    # 全量轨迁移语句判据
    import release_baseline_check as RB
    check("★ 全量轨迁移语句已有判据", hasattr(RB, "MIGRATION_SQL") and RB.MIGRATION_SQL)
    sq = Path(tempfile.mkdtemp())
    (sq / "bad.sql").write_text("ALTER TABLE T ADD COLUMN X INT;\n", encoding="utf-8")
    (sq / "ok.sql").write_text('CREATE TABLE IF NOT EXISTS "T" ("ID" VARCHAR(32));\n'
                               'COMMENT ON COLUMN "T"."ID" IS \'主键\';\n', encoding="utf-8")
    rep = RB.Report(); RB.check_sql_env_bound(sq, rep)
    errs = [e for e in rep.errors if e["check"] == "全量轨迁移语句"]
    check("ALTER 混进全量被检出", any("bad.sql" in e["msg"] for e in errs))
    check("合法建表 + 列注释零误报", not any("ok.sql" in e["msg"] for e in rep.errors))
    shutil.rmtree(sq, ignore_errors=True)

    # /version 两条短路必须挂推送分类
    vm = (repo / ".aidp/commands/version.md").read_text(encoding="utf-8")
    check("★ /version 短路已挂 classify_push（G-CHAIN-2 点名的漏挂）",
          vm.count("classify_push.py") >= 2 and "fail-closed" in vm)

    # 冻结契约判据 4 必须能看到解冻脚本
    fc = (scripts / "check_freeze_contract.py").read_text(encoding="utf-8")
    check("★ 冻结契约把 autopilot_unfreeze.py 算作读侧",
          "autopilot_unfreeze.py" in fc and "_UNFREEZE_BY_" in fc)


def test_stop_guard_failopen_ledger():
    """Stop hook 的 fail-open 必须**留痕**（实际项目中实测根因）。

    该 hook 有 4 层 fail-open，其中前 3 层此前**一个字都不打印**（`_exit_allow()` 就是裸
    `sys.exit(0)`）。于是「护栏看过了、判定一切正常」与「护栏因为读不到状态而弃权」
    在外部**完全同形**——事故复盘时无法区分，只能靠猜。

    ⛔ 本测试刻意是**行为级**（真跑 hook 进程、断言退出码与台账文件），不是 grep 源码：
    grep 只能证明"字面上写了"，证明不了"这条分支真的会走到"。
    """
    print("\n=== Stop hook fail-open 台账（行为级） ===")
    repo = Path(HERE).parent.parent.parent
    hook = repo / ".aidp/hooks/autopilot-stop-guard.py"
    check("★ Stop hook 存在", hook.is_file())
    if not hook.is_file():
        return

    def _run(td, baseline_obj, extra=None, stdin='{}', tick="sprint-autopilot"):
        """在临时项目里跑一次 hook，回传 (rc, stderr, 台账行列表)。tick=None 表示不注入 AIDP_TICK_COMMAND。"""
        root = Path(td)
        mem = root / "memory"
        mem.mkdir(parents=True, exist_ok=True)
        (mem / ".sprint-autopilot-baseline.json").write_text(
            json.dumps(baseline_obj, ensure_ascii=False), encoding="utf-8")
        for rel, body in (extra or {}).items():
            f = root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(body, encoding="utf-8")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
        env.pop("AIDP_TICK_COMMAND", None)
        if tick:
            env["AIDP_TICK_COMMAND"] = tick
        r = subprocess.run([sys.executable, str(hook)], input=stdin,
                           capture_output=True, text=True, env=env, timeout=120)
        led = mem / ".aidp/stop-guard-skips.jsonl"
        lines = [json.loads(x) for x in
                 led.read_text(encoding="utf-8").splitlines()] if led.is_file() else []
        return r.returncode, (r.stderr or ""), lines

    # ① 非 autopilot 会话（无 baseline 键、run_state 终态）→ 放行且【不记账】
    #    良性放行刻意不记：本 hook 每轮对话结束都触发，记了会把台账刷爆、挤掉真正可疑的。
    with tempfile.TemporaryDirectory() as td:
        rc, err, led = _run(td, {"versions": {"V1": {"run_state": {"next_phase": "done"}}}})
        check("★ 非活跃 run → 放行", rc == 0)
        check("★ 非活跃 run 属良性放行、不写台账（否则台账被高频路径刷爆）", led == [])

    # ② 活跃 run_state + 无 build → 这正是下游事故形态：护栏必须【拦住】而非静默放行
    with tempfile.TemporaryDirectory() as td:
        rc, err, led = _run(td, {"versions": {"V1": {"run_state": {"next_phase": "3.2-dev"}}}})
        check("★ 活跃 run_state 却无 build → 阻止结束（exit 2）", rc == 2)
        check("★ 阻止时明示不要停在这里等人", "没有人会来" in err or "继续推进" in err)

    # ②b 作用域：只拦 autopilot tick 轮次（裁决：会话 / 进程级判据，不看仓库级 baseline 新鲜度）
    _active = {"versions": {"V1": {"run_state": {"next_phase": "3.2-dev"}}}}
    with tempfile.TemporaryDirectory() as td:
        rc, _, _ = _run(td, _active, tick="sprint-aiauto-test")
        check("★ 测试链路轮次（AIDP_TICK_COMMAND=sprint-aiauto-test）→ 放行", rc == 0)
    with tempfile.TemporaryDirectory() as td:
        rc, _, _ = _run(td, _active, tick=None)
        check("★ 人的普通对话（无调度标记、无 transcript）→ 放行", rc == 0)
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td) / "t.jsonl"
        tp.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                  "content": "/loop 10m /sprint-autopilot --unattended"}}) + "\n"
                      + json.dumps({"type": "assistant", "message": {"role": "assistant",
                                    "content": [{"type": "text", "text": "ok"}]}}) + "\n",
                      encoding="utf-8")
        rc, _, _ = _run(td, _active, tick=None, stdin=json.dumps({"transcript_path": str(tp)}))
        check("★ transcript 最后一条用户输入是 /sprint-autopilot → 按 autopilot tick 拦截", rc == 2)
        tp.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                  "content": "$sprint-autopilot --unattended --no-loop"}}) + "\n",
                      encoding="utf-8")
        rc, _, _ = _run(td, _active, tick=None, stdin=json.dumps({"transcript_path": str(tp)}))
        check("★ Codex transcript 的 $sprint-autopilot → 按 autopilot tick 拦截", rc == 2)
        tp.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                  "content": "$aidp-cmd sprint-autopilot --unattended"}}) + "\n",
                      encoding="utf-8")
        rc, _, _ = _run(td, _active, tick=None, stdin=json.dumps({"transcript_path": str(tp)}))
        check("★ aidp-cmd 文本不是命令入口 → 放行", rc == 0)
        for ordinary in ("请解释 $sprint-autopilot", "比较 /sprint-autopilot 与手工流程",
                         "echo $sprint-autopilot", "解释一下 sprint-autopilot 的冻结机制"):
            tp.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                      "content": ordinary}}) + "\n", encoding="utf-8")
            rc, _, _ = _run(td, _active, tick=None,
                            stdin=json.dumps({"transcript_path": str(tp)}))
            check("★ 普通正文提及命令不误判：%s" % ordinary, rc == 0)
        tp.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                  "content": "前置说明\n/sprint-autopilot --unattended"}}) + "\n",
                      encoding="utf-8")
        rc, _, _ = _run(td, _active, tick=None, stdin=json.dumps({"transcript_path": str(tp)}))
        check("★ 多行输入的行首 /sprint-autopilot → 拦截", rc == 2)
        tp.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                  "content": "/loop 10m /sprint-autopilot --unattended"}}) + "\n",
                      encoding="utf-8")
        rc, _, _ = _run(td, _active, tick=None, stdin=json.dumps({"transcript_path": str(tp)}))
        check("★ 行首 /loop 内的 /sprint-autopilot → 拦截", rc == 2)
        tp.write_text(json.dumps({"type": "user", "message": {"role": "user",
                                  "content": "<command-name>sprint-autopilot</command-name>"}}) + "\n",
                      encoding="utf-8")
        rc, _, _ = _run(td, _active, tick=None, stdin=json.dumps({"transcript_path": str(tp)}))
        check("★ command-name 包装的 sprint-autopilot → 拦截", rc == 2)
    with tempfile.TemporaryDirectory() as td:
        bl = {"autopilot": {"wake_source_this_tick": "1"},
              "versions": {"V1": {"run_state": {"next_phase": "3.2.1-deploy", "next_sprint": "done"},
                                  "current_build": "b1", "builds": [{"build": "b1", "status": "open"}]}}}
        rc, _, _ = _run(td, bl)
        check("★ 有唤醒源 + 跨 tick 等待游标（3.2.1-*）→ 按中间 yield 放行", rc == 0)

    # ③ 逃生舱开着 → 放行，但【必须留痕】
    #    逃生舱一旦 touch 出来就永久生效、护栏此后全程沉默，是最该留痕的一条。
    with tempfile.TemporaryDirectory() as td:
        rc, err, led = _run(td, {"versions": {"V1": {"run_state": {"next_phase": "3.2-dev"}}}},
                            extra={"memory/.autopilot-stop-guard-off": ""})
        check("★ 逃生舱 → 放行", rc == 0)
        check("★ 逃生舱放行必留痕（分支 escape-hatch）",
              any(x.get("branch") == "escape-hatch" for x in led))
        check("★ 逃生舱放行同时打 stderr（给人的即时信号）", "护栏本轮未介入" in err)

    # ④ 收尾门脚本缺失 → 放行，但必须留痕（未经任何校验即放行 = 最危险的静默）
    with tempfile.TemporaryDirectory() as td:
        bl = {"versions": {"V1": {"run_state": {"next_phase": "3.4-final"},
                                  "current_build": "b1",
                                  "builds": [{"build": "b1", "status": "open"}]}}}
        rc, err, led = _run(td, bl)
        check("★ 收尾门脚本缺失 → 放行（不因自身故障 wedge）", rc == 0)
        check("★ 收尾门脚本缺失必留痕（分支 gate-script-missing）",
              any(x.get("branch") == "gate-script-missing" for x in led))

    # ⑤ 台账滚动截断，不无限增长
    src = hook.read_text(encoding="utf-8")
    check("★ 台账有上限、滚动截断", "SKIP_LOG_MAX" in src and "lines[-(SKIP_LOG_MAX" in src)
    check("★ 台账写失败绝不影响放行本身（_note_skip 全程吞异常）",
          "台账写不进去绝不能影响放行本身" in src)

    # ⑥ 台账必须被【消费】——只写不读等于重蹈"不可观测"覆辙
    ph1 = (repo / ".aidp/flows/sprint-autopilot/phase-0-1.md").read_text(encoding="utf-8")
    check("★ Phase 0 开局读台账（0.0.0ter）",
          "stop-guard-skips.jsonl" in ph1 and "0.0.0ter" in ph1)
    cmd = (repo / ".aidp/commands/sprint-autopilot.md").read_text(encoding="utf-8")
    check("★ 命令骨架表登记 0.0.0ter（否则执行体不知道要读）", "0.0.0ter" in cmd)
    gi = (repo / ".gitignore").read_text(encoding="utf-8")
    check("★ 本地运行态均已 gitignore（新落点 memory/.aidp/ + 旧落点残留兜底）",
          "memory/.aidp/" in gi and all(
              k in gi for k in ("autopilot-stop-guard-count",
                                "autopilot-stop-guard-skips.jsonl",
                                "autopilot-stop-guard-off")))


def test_interactive_single_shot_no_handback():
    """交互式单次调用不得把流程丢回给人（0.5bis D5 + 用例前置资源对账门）。

    实际项目中实测：交互式 `/sprint-autopilot V0.14 "<需求>"` 跑完
    部署 + 就绪探针后停下来问「需要我接着跑浏览器实测吗、我需要第二个测试企业账号」——
    而那个账号本来就在约定 38 的产物里。三处规则缝隙叠加才让它显得合理。
    """
    print("\n=== 交互式单次不得交还控制权 ===")
    repo = Path(HERE).parent.parent.parent
    p07 = (repo / ".aidp/flows/sprint-autopilot/phase-0-7.md").read_text(encoding="utf-8")
    cmd = (repo / ".aidp/commands/sprint-autopilot.md").read_text(encoding="utf-8")
    p31 = (repo / ".aidp/flows/sprint-autopilot/phase-3-1.md").read_text(encoding="utf-8")

    # 缝隙 1：白名单口径必须与 LOOP_UNATTENDED 解耦
    check("★ 0.5bis 有 D5 适用面条款", "D5 适用面" in p07)
    check("★ D5 明写与 LOOP_UNATTENDED 无关", "与 `LOOP_UNATTENDED` 无关" in p07)
    check("★ D5 明写判据是「有无确定性默认」而非「用户在不在场」",
          "不是\"用户在不在场\"" in p07 or "不是\u201c用户在不在场\u201d" in p07
          or "用户在不在场" in p07)
    check("★ 白名单条目标注两种模式共用", "两种模式共用" in p07)
    check("★ 「问一句然后结束回合」被显式判违规",
          "结束回合" in p07 and "违规" in p07)
    # ⛔ 门控写在触发条件上最隐蔽：交互式压根不 Read 这份分片，连唯一信源都看不到
    row = [l for l in cmd.splitlines() if l.startswith("| **0.5bis**")]
    check("★ 命令骨架表 0.5bis 行存在", len(row) == 1)
    if row:
        check("★ 0.5bis 不再以 LOOP_UNATTENDED=1 为触发条件（否则交互式读不到）",
              "总是" in row[0].split("|")[-2])

    # 缝隙 3 + 附带建议：借口清单必须堵住这两个说法
    check("★ 借口清单含「缺前置数据 / 缺测试账号」", "缺前置数据" in p31)
    check("★ 借口清单含「需要用户确认才能继续测试」", "需要用户确认才能继续测试" in p31)

    # 对账门：脚本 + 两处落点（只放 Phase 0 时 full 模式恒判 no-casebook = 形同虚设）
    sc = repo / ".aidp/scripts/check_testdata_prereq.py"
    check("★ 对账门脚本存在", sc.is_file())
    p09 = (repo / ".aidp/flows/sprint-autopilot/phase-0-9.md").read_text(encoding="utf-8")
    p33 = (repo / ".aidp/flows/sprint-autopilot/phase-3-3.md").read_text(encoding="utf-8")
    check("★ 落点①：Phase 0 的 0.6bis", "0.6bis" in p09 and "check_testdata_prereq.py" in p09)
    check("★ 落点②：Phase 3.1bis 补账（full 模式唯一有效落点）",
          "3.1bis" in p33 and "check_testdata_prereq.py" in p33)
    check("★ 两处落点都登记进命令骨架表", "0.6bis" in cmd and "3.1bis" in cmd)

    # 行为级：真跑对账门，两侧对照
    if sc.is_file():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            d = root / "docs/testing/V1/研发自测"
            d.mkdir(parents=True)
            (d / "01_测试环境与账号.md").write_text("# 账号\n- admin\n", encoding="utf-8")
            (d / "02_用例.md").write_text("### 套件 SUITE-A\n正常\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(sc), "--root", str(root),
                                "--version", "V1", "--json"],
                               capture_output=True, text=True)
            check("★ 对账门阴性对照：齐备时判绿", r.returncode == 0)
            # 阳性对照：植入上游标准占位符
            (d / "02_用例.md").write_text(
                "### 套件 SUITE-A\n前置：{待用户填写: 对照企业账号}\n", encoding="utf-8")
            r2 = subprocess.run([sys.executable, str(sc), "--root", str(root),
                                 "--version", "V1", "--json"],
                                capture_output=True, text=True)
            check("★ 对账门阳性对照：占位符必被抓到", r2.returncode == 1)
            try:
                gaps = json.loads(r2.stdout).get("gaps", [])
            except ValueError:
                gaps = []
            check("★ 缺口可定位到文件+行+字段名",
                  gaps and gaps[0].get("line") and "对照企业账号" in gaps[0].get("field", ""))
            # 规划期未到不算缺陷（否则 full 模式 Phase 0 恒红）
            r3 = subprocess.run([sys.executable, str(sc), "--root", str(root),
                                 "--version", "V-NOPE", "--json"],
                                capture_output=True, text=True)
            check("★ 尚无用例册判 no-casebook 而非缺陷", r3.returncode == 0
                  and '"no-casebook"' in r3.stdout)


def test_card_and_driver_reverse_cases():
    """下游要求的三条反向用例（A 零发卡 / B 无 DISPLAY / C 报错不得解释为不可用）。

    共同根因：**凡"执行体应当做某事"的契约，若其检查也依赖执行体自觉调用，
    那么在执行体从未读到该契约的场景下，规则与检查会同时失效。**
    发卡矩阵 + EXPECT_CARDS 校验同在 phase-0-5/3.4；驱动选型结论 + 探测脚本同在 auto-test-runner。
    故本组用例一律断言**脚本侧退出码 / 输出**，不断言"执行体会不会照做"。
    """
    print("\n=== 反向用例 A/B/C：通知 + 驱动选型 ===")
    repo = Path(HERE).parent.parent.parent
    sdir = repo / ".aidp/scripts"

    # ── C：已知错误 → 处置映射（最直接可测，先跑）──────────────────────
    doctor = sdir / "chrome-mcp-doctor.py"
    check("★ chrome-mcp-doctor 存在", doctor.is_file())
    if doctor.is_file():
        def _ex(text):
            r = subprocess.run([sys.executable, str(doctor), "explain-error",
                                "--error", text, "--json"],
                               capture_output=True, text=True, timeout=60)
            try:
                j = json.loads((r.stdout or "").rsplit("---JSON---", 1)[-1].strip())
            except ValueError:
                j = {}
            return r.returncode, (r.stdout or ""), j

        rc, out, j = _ex("Missing X server to start the headful browser. "
                         "Either set headless to true or use xvfb-run")
        check("★ C1 「Missing X server」判 not-a-blocker（退出码 0）",
              rc == 0 and j.get("verdict") == "not-a-blocker")
        check("★ C1 明确禁止据此降级为非浏览器驱动",
              "curl" in out and "JDBC" in out and "⛔" in out)
        check("★ C1 明确不要去装 xvfb（无头本就不需要 X server）", "xvfb" in out)
        check("★ C1 点名「只能起有头浏览器」这个结论不成立",
              "只能起有头浏览器" in out)

        rc2, out2, j2 = _ex("bash: chrome-devtools-cli: command not found")
        check("★ C2 技能名 ≠ 二进制名，判 not-a-blocker",
              rc2 == 0 and j2.get("verdict") == "not-a-blocker")
        check("★ C2 给出真实命令名 chrome-devtools", "`chrome-devtools`" in out2)

        rc3, _, j3 = _ex("Could not find Chrome")
        check("★ C3 真环境不具备判 blocker（退出码 1）",
              rc3 == 1 and j3.get("verdict") == "blocker")

        rc4, out4, _ = _ex("some unrelated failure text")
        check("★ C4 未收录 → 退出码 3，且不得放任自行解释", rc4 == 3)
        check("★ C4 未收录时要求先跑 check-cli 拿客观信号", "check-cli" in out4)

    # ── B：无 DISPLAY 环境下的驱动判定 ────────────────────────────────
    #    断言口径：check-cli 的判定**不看 $DISPLAY**（无头 CLI 本就不需要 X server）。
    #    ⛔ 不能断言"结论必为本地 CLI 可用"——本仓 CI 未必装了 chrome-devtools，
    #       那样断言会变成"环境有没有装"的检测，而不是"判定逻辑对不对"。
    if doctor.is_file():
        src = doctor.read_text(encoding="utf-8")
        check("★ B1 驱动判定不以 $DISPLAY 为判据（无头不需要 X server）",
              "DISPLAY" not in src)
        env = dict(os.environ)
        env.pop("DISPLAY", None)
        r = subprocess.run([sys.executable, str(doctor), "check-cli", "--json",
                            "--root", str(repo)],
                           capture_output=True, text=True, env=env, timeout=120)
        out = r.stdout or ""
        check("★ B2 无 DISPLAY 下仍给出确定性 category（不挂起、不要求人工确认）",
              "category" in out)
        check("★ B3 无 DISPLAY 不得输出「浏览器不可用/需人工确认」这类结论",
              "浏览器不可用" not in out and "需人工确认" not in out)

    # ── A：零发卡必须被收尾门拦住 ─────────────────────────────────────
    gate = sdir / "autopilot-ceremony-gate.py"
    check("★ A0 收尾门存在", gate.is_file())
    if gate.is_file():
        g = gate.read_text(encoding="utf-8")

        # ⛔ A1~A3 必须是**行为级**：真跑 gate 看退出码与输出。
        #    grep 源码只能证明"字面上写了"——而本报告点名的共同根因恰恰是
        #    "规则与检查同时失效"，一份只读字符串的测试对此毫无判别力
        #    （实测：把 rec(..., False) 改成 rec(..., True)，grep 版断言全绿）。
        def _run_gate(probe, notify=0):
            """造最小 baseline 跑一次 gate，回传 (rc, 合并输出)。"""
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                (root / "memory").mkdir(parents=True)
                bl = {"versions": {"V1": {"current_build": "V1_b1",
                                          "builds": [{"build": "V1_b1", "status": "open"}]}}}
                if probe is not None:
                    bl["notify_probe"] = probe
                (root / "memory/.sprint-autopilot-baseline.json").write_text(
                    json.dumps(bl, ensure_ascii=False), encoding="utf-8")
                r = subprocess.run(
                    [sys.executable, str(gate), "check", "--version", "V1",
                     "--build", "V1_b1", "--notify", str(notify),
                     "--stage", "skeleton", "--repo-root", str(root)],
                    capture_output=True, text=True, timeout=120)
                return r.returncode, (r.stdout or "") + (r.stderr or "")

        def _verdict(out, item="里程碑通知"):
            """摘出某一检查项的判定（PASS / FAIL / DEGRADE）。

            ⛔ 不能用整体退出码断言：最小夹具下 gate 因大量产物缺失**本来就非 0**，
            `rc != 0` 恒真、判别力为零（实测：把该项判定翻成 True，断言依旧全绿）。
            必须落到**这一项**的判定上。
            """
            # 判定以**图标**呈现（gate 内 icon 映射：PASS=✅ / FAIL=❌ / DEGRADE=🟡）
            icon2v = {"\u2705": "PASS", "\u274c": "FAIL", "\U0001f7e1": "DEGRADE"}
            for ln in out.splitlines():
                if item in ln:
                    for ic, v in icon2v.items():
                        if ic in ln:
                            return v
            return None

        # A1：通道当时【可用】却整组跳过发卡 → 该项必须 FAIL（这不是合法降级，是漏发）
        _, out_a = _run_gate({"enabled": True, "available": True,
                              "detail": "ok", "at": "2026-09-08T10:00:00"})
        check("★ A1 通道可用却零发卡 → 该项判 FAIL（行为级，非 grep）",
              _verdict(out_a) == "FAIL")
        check("★ A1 输出点名这不是合法降级", "不是合法降级" in out_a or "漏发" in out_a)

        # A2：探测证明通道当时确实坏了 → 合法降级，放行
        rc_b, out_b = _run_gate({"enabled": True, "available": False,
                                 "detail": "notify.channels 为空",
                                 "at": "2026-09-08T10:00:00"})
        check("★ A2 探测举证通道不可用 → 判 DEGRADE 合法降级、不误杀（阴性对照）",
              _verdict(out_b) == "DEGRADE" and "合法降级（已举证）" in out_b)

        # A3：无举证 → 只 DEGRADE，且必须把"无从判断"说出来（不静默放行）
        rc_c, out_c = _run_gate(None)
        check("★ A3 缺举证 → DEGRADE 且明说无从判断（不静默 PASS）",
              _verdict(out_c) == "DEGRADE" and "无从判断通道当时是否可用" in out_c)
        # A4：探测证据有生产方，否则举证恒缺、A1 永远只走 DEGRADE 分支
        pf = (sdir / "autopilot-preflight.py").read_text(encoding="utf-8")
        check("★ A4 探测证据有生产方（preflight --record-probe）",
              "--record-probe" in pf and "notify_probe" in pf)
        ph01 = (repo / ".aidp/flows/sprint-autopilot/phase-0-1.md").read_text(encoding="utf-8")
        check("★ A5 Phase 0.0 Step 0 真的带上了 --record-probe（否则证据永远不产生）",
              "--record-probe" in ph01)

        # A6~A8：driver 如实性收紧（问题二的结构级落点）
        check("★ A6 浏览器驱动白名单存在", "BROWSER_DRIVERS" in g)
        check("★ A7 缺 driver_actual 由 DEGRADE 提为 FAIL（报告已出却无驱动记录）",
              "驱动选定环节未走过" in g)
        check("★ A8 非浏览器驱动须 driver_downgrade_evidence 举证",
              "driver_downgrade_evidence" in g and "不是浏览器驱动" in g)
        check("★ A9 降级指引指向 explain-error（而非让执行体自行解释）",
              "explain-error" in g)


def test_family_ledgers_split():
    """约定 22 从「单册台账」改为「四族增量册」的行为级回归。

    ⛔ 本组一律**真跑脚本**、不 grep 源码：拆分改的是"扫哪些文件"，
    而扫错文件的失败形态是**静默漏检**（该看的没看到，输出与"都合规"完全同形）——
    只有拿真实目录树跑一遍才能把它区分开。
    """
    print("\n=== 约定 22 四族增量册拆分 ===")
    repo = Path(HERE).parent.parent.parent
    sys.path.insert(0, str(repo / ".aidp/scripts"))
    import commit_gate as HG

    def mktree(entries):
        """entries: {相对路径: 正文}"""
        root = Path(tempfile.mkdtemp())
        for rel, body in entries.items():
            f = root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(body, encoding="utf-8")
        return root

    HEAD = "## 待级联\n\n"
    OLD = HEAD + "- C-001 · 01-02 10:00 · 昨天及更早 · sprint-001\n"

    # ① 四族全部被扫到（⛔ 只扫 requirements 一棵树会漏掉纯设计/纯计划的版本）
    root = mktree({
        "docs/requirements/V1/研发需求/_开发期需求增量.md": OLD,
        "docs/design/detail/V1/_开发期设计增量.md": OLD,
        "docs/plans/V1/_开发期计划增量.md": OLD,
        "docs/testing/V1/研发自测/_开发期用例增量.md": OLD,
    })
    pc = HG.pending_cascade(str(root), "2026-09-08")
    check("★ 四族全部被扫到（total=4）", pc["total"] == 4)
    check("★ 四族均计入 stale（昨天及更早）", pc["stale"] == 4)
    check("★ 按族分列可定位", sorted((pc["versions"]["V1"]["families"] or {})) ==
          ["case", "design", "plan", "req"])
    shutil.rmtree(root, ignore_errors=True)

    # ② 只有设计册（"本版只改了设计"是完全正常的情形）—— 单树扫描会整个漏掉
    root = mktree({"docs/design/detail/V2/_开发期设计增量.md": OLD})
    pc = HG.pending_cascade(str(root), "2026-09-08")
    check("★ 只有设计册也能被发现（版本集取四棵树并集）",
          pc["total"] == 1 and "V2" in pc["versions"])
    shutil.rmtree(root, ignore_errors=True)


    # ④ 路径表是单一实现（收口点与两道门共用；各拼一次 = 静默漏检）
    paths = dict(HG.cascade_ledger_paths("/r", "V9"))
    check("★ cascade_ledger_paths 覆盖四族",
          set(paths) == {"req", "design", "plan", "case"})
    check("★ 需求册与 01_研发需求.md 同目录（研发需求/ 下）",
          paths["req"].endswith("docs/requirements/V9/研发需求/_开发期需求增量.md"))
    check("★ 设计册与 01_详细设计.md 同目录（版本根）",
          paths["design"].endswith("docs/design/detail/V9/_开发期设计增量.md"))
    check("★ 用例册与用例册同目录（研发自测/ 下）",
          paths["case"].endswith("docs/testing/V9/研发自测/_开发期用例增量.md"))

    # ⑤ 终态门逐族判定：⛔ 不得"某族干净即收工"
    ccl = str(repo / ".aidp/scripts/check_cascade_landing.py")
    root = mktree({
        "docs/design/detail/V1/_开发期设计增量.md": HEAD + "（无）\n",   # 空册该删没删
        "docs/testing/V1/研发自测/_开发期用例增量.md": OLD,               # 有未决，合法
    })
    r = subprocess.run([sys.executable, ccl, "--ledger-closed", "--version", "V1",
                        "--root", str(root)], capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    check("★ 一族空册未删 → 整体 FAIL（不因另一族合法而放行）", r.returncode == 1)
    check("★ 违规精确指向那一族", "_开发期设计增量.md" in out and "not-deleted" in out)
    shutil.rmtree(root, ignore_errors=True)

    # ⑥ 必删档：四族逐份都要求不存在
    root = mktree({"docs/plans/V1/_开发期计划增量.md": OLD})
    r = subprocess.run([sys.executable, ccl, "--must-delete", "--version", "V1",
                        "--root", str(root)], capture_output=True, text=True)
    check("★ 必删档下任一族残留即 FAIL", r.returncode == 1)
    shutil.rmtree(root, ignore_errors=True)

    # ⑦ 落点门：族增量册是合法落点（收口时在其中删条目），NN_ 分册仍禁
    check("★ 落点门把族增量册列为合法落点",
          "FAMILY_LEDGERS" in Path(ccl).read_text(encoding="utf-8"))

    # ⑧ 上游命名门确实豁免 `_` 前缀（本方案可行性的前提，实测 + 阳性对照）
    dla = repo / ".aidp/skills/dev-logic-architect/scripts/check_doc_split.py"
    if dla.is_file():
        d = Path(tempfile.mkdtemp())
        (d / "00_索引.md").write_text("# 索引\n", encoding="utf-8")
        (d / "01_详细设计.md").write_text("# 详设\n" * 120, encoding="utf-8")
        rc_base = subprocess.run([sys.executable, str(dla), str(d)],
                                 capture_output=True, text=True).returncode
        (d / "_开发期设计增量.md").write_text("# 增量\n", encoding="utf-8")
        rc_led = subprocess.run([sys.executable, str(dla), str(d)],
                                capture_output=True, text=True).returncode
        (d / "裸名文档.md").write_text("# x\n", encoding="utf-8")
        rc_bad = subprocess.run([sys.executable, str(dla), str(d)],
                                capture_output=True, text=True).returncode
        check("★ 上游命名门豁免 `_` 前缀（增量册不被判 error）", rc_led == rc_base)
        check("★ 阳性对照：同目录裸名文件仍被判 error（门确实在跑）", rc_bad == 1)
        shutil.rmtree(d, ignore_errors=True)

    # ⑩ 「发现型 glob 漏排 `_` 前缀」——本次拆分暴露出来的真缺陷，行为级验
    #    （增量册与交付文档同目录后，黑名单式 glob 一条都不命中新文件名 → 被当成用例源）
    ug = repo / ".aidp/scripts/check_underscore_glob.py"
    check("★ 漏排门脚本存在", ug.is_file())
    if ug.is_file():
        r = subprocess.run([sys.executable, str(ug), "--root", str(repo), "--json"],
                           capture_output=True, text=True)
        check("★ 本仓 flow/command 已无漏排（0 处）", r.returncode == 0)
        # 阳性对照：造一个漏排的 flow，必须被抓到
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / ".aidp/flows/x/y.md"
            f.parent.mkdir(parents=True)
            f.write_text('```bash\nfind "$V/研发自测" -maxdepth 2 -name "*.md" '
                         '-not -name "README.md"\n```\n', encoding="utf-8")
            r2 = subprocess.run([sys.executable, str(ug), "--root", td, "--json"],
                                capture_output=True, text=True)
            check("★ 阳性对照：漏排的通配 glob 必被抓到", r2.returncode == 1)
            # 阴性对照：带了 -not -name "_*" 就不该报（否则是恒红、同样没判别力）
            f.write_text('```bash\nfind "$V/研发自测" -maxdepth 2 -name "*.md" '
                         '-not -name "_*" -not -name "README.md"\n```\n', encoding="utf-8")
            r3 = subprocess.run([sys.executable, str(ug), "--root", td, "--json"],
                                capture_output=True, text=True)
            check("★ 阴性对照：带了 `-not -name \"_*\"` 不误报", r3.returncode == 0)

    # ⑪ 三处真实落点确实带上了排除（它们是 AI 测试链路的用例发现口）
    for rel in ("flows/sprint-aiauto-test/phase-2-1.md",
                "flows/sprint-batch/step-6.md",
                "commands/sprint-test.md"):
        body = (repo / ".aidp" / rel).read_text(encoding="utf-8")
        check("★ %s 的用例发现 glob 排除 `_*`" % rel, '-not -name "_*"' in body)

    # ⑫ 「带着未级联的用例增量去实测」门 —— 增量册不是用例，级联才是把线索变用例的那一步
    clp = repo / ".aidp/scripts/check_case_ledger_pending.py"
    check("★ 实测前门脚本存在", clp.is_file())
    if clp.is_file():
        def _clp(entries):
            root = Path(tempfile.mkdtemp())
            (root / ".aidp/scripts").mkdir(parents=True)
            shutil.copy(str(repo / ".aidp/scripts/commit_gate.py"),
                        str(root / ".aidp/scripts/commit_gate.py"))
            for rel, body in entries.items():
                f = root / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(body, encoding="utf-8")
            r = subprocess.run([sys.executable, str(clp), "--root", str(root),
                                "--version", "V1", "--json"],
                               capture_output=True, text=True)
            shutil.rmtree(root, ignore_errors=True)
            return r.returncode, (r.stdout or "")

        LED = "## 待级联\n\n- C-007 · 01-02 10:00 · 加了个筛选项 · sprint-012\n"
        rc, _ = _clp({"docs/testing/V1/研发自测/02_用例.md": "### 套件 SUITE-A\n"})
        check("★ 无用例增量 → 放行（阴性对照，非恒红）", rc == 0)
        rc, out = _clp({"docs/testing/V1/研发自测/_开发期用例增量.md": LED})
        check("★ 用例增量未级联 → 拦住（exit 1）", rc == 1)
        check("★ 点明此刻测的是老用例集", '"pending": 1' in out)
        # ⛔ 只有用例族才拦实测：设计/计划族未级联不该阻断浏览器测试
        rc, _ = _clp({"docs/design/detail/V1/_开发期设计增量.md": LED})
        check("★ 仅设计族未级联 → 不拦实测（别把无关族也拦了）", rc == 0)

    # ⑬ 门有接线点，否则又是"只写在散文里"
    p21 = (repo / ".aidp/flows/sprint-aiauto-test/phase-2-1.md").read_text(encoding="utf-8")
    check("★ 实测前门已接进 aiauto-test 用例来源解析",
          "check_case_ledger_pending.py" in p21)
    check("★ 明写不得把增量册塞进用例发现来「解决」问题",
          "不要把增量册塞进用例发现" in p21)
    check("★ 级联跑不动时报告须标注覆盖不完整、不得判通过",
          "覆盖不完整" in p21 and "不得据此判版本通过" in p21)

    # ⑭ 增量用例可见性：执行全量、报告分得清（incremental_cases.py + 收尾门 3o）
    inc = repo / ".aidp/scripts/incremental_cases.py"
    check("★ 增量用例脚本存在", inc.is_file())
    if inc.is_file():
        def _mkrepo_cases():
            root = Path(tempfile.mkdtemp())
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            for k, v in (("user.email", "t@t"), ("user.name", "t")):
                subprocess.run(["git", "-C", str(root), "config", k, v], check=True)
            d = root / "docs/testing/V1/研发自测"
            d.mkdir(parents=True)
            (d / "02_用例.md").write_text(
                "### 套件 SUITE-A\n\n#### 用例 TC-A-001: 老用例\n步骤\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "-A"], check=True,
                           capture_output=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "base"], check=True,
                           capture_output=True)
            base = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                                  capture_output=True, text=True).stdout.strip()
            return root, d, base

        def _inc(root, since=None):
            args = [sys.executable, str(inc), "--root", str(root), "--version", "V1", "--json"]
            if since:
                args += ["--since", since]
            r = subprocess.run(args, capture_output=True, text=True)
            try:
                return r.returncode, json.loads(r.stdout)
            except ValueError:
                return r.returncode, {}

        root, d, base = _mkrepo_cases()
        # 无基准 → 诚实空集，⛔ 不拿版本起点顶上把首轮全部用例报成"增量"
        rc, j = _inc(root)
        check("★ 无基准判 no-anchor + 空集（不虚报精确）",
              rc == 0 and j.get("status") == "no-anchor" and j.get("ids") == [])
        # 级联新增两条（两种标题形态：带「用例」二字 / 省略）
        (d / "02_用例.md").write_text(
            (d / "02_用例.md").read_text(encoding="utf-8")
            + "\n#### 用例 TC-A-002: 已停用筛选\n步骤\n\n##### TC-A-003: 导出去 XLSX\n步骤\n",
            encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "cascade"], capture_output=True)
        rc, j = _inc(root, base)
        check("★ 两种标题形态的新增用例都识别",
              sorted(j.get("ids") or []) == ["TC-A-002", "TC-A-003"])
        # 正文顺带提及不算（误算方向是**虚报覆盖**，比漏报危险）
        mid = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                             capture_output=True, text=True).stdout.strip()
        (d / "02_用例.md").write_text(
            (d / "02_用例.md").read_text(encoding="utf-8") + "\n补一句：参见 TC-A-001。\n",
            encoding="utf-8")
        subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True)
        subprocess.run(["git", "-C", str(root), "commit", "-qm", "prose"], capture_output=True)
        rc, j = _inc(root, mid)
        check("★ 正文顺带提及 TC-* 不算增量（不虚报覆盖）", j.get("ids") == [])
        shutil.rmtree(root, ignore_errors=True)

    # ⑮ 接线点齐备：算了没人用 = 白算；门有了没生产方 = 恒空
    gate_src = (repo / ".aidp/scripts/autopilot-ceremony-gate.py").read_text(encoding="utf-8")
    check("★ 收尾门 3o 存在（增量用例可核对）", "本轮增量用例可核对" in gate_src)
    check("★ 3o 交集为 0 判 FAIL（级联了但执行没收到）",
          "一条都没有" in gate_src and "incremental_case_ids" in gate_src)
    er = (repo / ".aidp/scripts/emit-report.py").read_text(encoding="utf-8")
    check("★ emit-report 自动注入 incrementalCaseIds（不让执行体手填）",
          "def enrich_incremental" in er and "enrich_incremental(payload" in er)
    p21b = (repo / ".aidp/flows/sprint-aiauto-test/phase-2-1.md").read_text(encoding="utf-8")
    check("★ Phase 2.0.0bis 已接线", "incremental_cases.py" in p21b)
    check("★ 明写执行仍全量、不按增量裁剪",
          "执行仍全量" in p21b and "不按增量裁剪" in p21b)

    # ⑨ 绕过判据认全部五个基名（漏登记任一 = 真收口被误报成"绕过"）
    hg_src = (repo / ".aidp/scripts/commit_gate.py").read_text(encoding="utf-8")
    check("★ suspected_cascade_bypass 用基名【集合】而非单个",
          "_LEDGER_BASENAMES" in hg_src and "in _LEDGER_BASENAMES" in hg_src)
    bypass = HG.suspected_cascade_bypass(
        " M code/backend/A.java\n M docs/design/detail/V1/01_详细设计.md\n"
        " M docs/design/detail/V1/_开发期设计增量.md\n")
    check("★ 动了设计增量册 = 真收口，不判绕过", bypass["suspected"] is False)
    bypass2 = HG.suspected_cascade_bypass(
        " M code/backend/A.java\n M docs/design/detail/V1/01_详细设计.md\n")
    check("★ 只改代码+主文档、没动任何册子 → 判绕过", bypass2["suspected"] is True)


def test_ddl_comment_and_release_order():
    """DDL 列注释实查门 + 发布顺序铁律（实际项目 V0.14.0 事故）。

    事故形态：SQL 脚本里**写了** `COMMENT ON COLUMN`，手工执行只跑了 `ALTER TABLE ADD`
    那段循环、注释语句整段漏掉，实查 `ALL_COL_COMMENTS` 新增 10 列 10/10 无注释——
    **而没有任何一步会发现**。故本门校的是"有没有真去查过库"，不是"脚本里写没写"。
    """
    print("\n=== DDL 注释实查 + 发布顺序 ===")
    repo = Path(HERE).parent.parent.parent
    sc = repo / ".aidp/scripts/check_sql_ledger_comment.py"
    tpl = repo / ".aidp/templates/deployment/SQL执行台账.md"
    check("★ 注释实查门脚本存在", sc.is_file())
    check("★ 台账模板存在", tpl.is_file())
    if not (sc.is_file() and tpl.is_file()):
        return

    def _mk(sql_body=None, ledger=None):
        root = Path(tempfile.mkdtemp())
        d = root / "docs/deployment/V1/sql/增量"
        d.mkdir(parents=True)
        if sql_body is not None:
            (d / "01_x.sql").write_text(sql_body, encoding="utf-8")
        if ledger is not None:
            (root / "docs/deployment/V1/SQL执行台账.md").write_text(ledger, encoding="utf-8")
        return root

    def _run(root):
        r = subprocess.run([sys.executable, str(sc), "--root", str(root),
                            "--version", "V1", "--json"], capture_output=True, text=True)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            return r.returncode, {}

    TPL = tpl.read_text(encoding="utf-8")

    # 阴性对照：本版无 ADD COLUMN → 不适用、放行（⛔ 恒红的门没有判别力）
    rc, j = _run(_mk("CREATE TABLE IF NOT EXISTS T_X (ID INT);\n"))
    check("★ 无 ADD COLUMN → 不适用放行", rc == 0 and j.get("status") == "no-add-column")

    # 反向用例 B（下游点名的那条）：有新增列却没台账 → 红
    rc, j = _run(_mk("ALTER TABLE T_E ADD COLUMN STATUS INT;\n"
                     "COMMENT ON COLUMN T_E.STATUS IS '状态';\n"))
    check("★ 有新增列却无台账 → FAIL", rc == 1 and j.get("status") == "ledger-missing")
    check("★ 即便脚本里写了 COMMENT 也照样红（校库不校脚本）", rc == 1)

    # ⛔ 达梦/Oracle 方言 `ADD (` 必须认——只认 ADD COLUMN 会在国产库上静默失效
    rc, j = _run(_mk("ALTER TABLE T_E ADD (ADMIN_USER_ID VARCHAR(64));\n"))
    check("★ 达梦/Oracle 的 `ADD (` 方言也识别", rc == 1 and j.get("add_column_files"))

    # 拷了模板但没填 → 红（模板占位不算实查）
    rc, j = _run(_mk("ALTER TABLE T_E ADD COLUMN STATUS INT;\n", TPL))
    check("★ 台账仅拷模板未填 → FAIL（占位不算实查）",
          rc == 1 and j.get("status") == "dev-row-unfilled")

    # 填实 → 绿
    filled = TPL.replace(
        "| 开发库 | {如 `T_ENTERPRISE.STATUS`、`T_ENTERPRISE.ADMIN_USER_ID`} | {2/2} | {无} | {YYYY-MM-DD HH:MM} |",
        "| 开发库 | `T_E.STATUS` | 1/1 | 无 | 2026-09-08 16:20 |")
    rc, j = _run(_mk("ALTER TABLE T_E ADD COLUMN STATUS INT;\n", filled))
    check("★ 填实查结果 → PASS", rc == 0 and j.get("status") == "ok")

    # 已并进约定 37 机器门（release-4 无条件调它 → 忘不掉）
    rbc = (repo / ".aidp/scripts/release_baseline_check.py").read_text(encoding="utf-8")
    check("★ 已并入 release_baseline_check 第 12 项",
          "check_ddl_comment_verified" in rbc and "12 项确定性校验" in rbc)
    check("★ 委派单一实现、不重写方言识别",
          "check_sql_ledger_comment.py" in rbc)

    # 门 4：发布顺序铁律有落点（部署流程模板 + 约定 37 细则）
    dep = (repo / ".aidp/templates/deployment/部署流程.md").read_text(encoding="utf-8")
    d5 = (repo / ".aidp/reference/约定细则-5.md").read_text(encoding="utf-8")
    check("★ 部署流程写明加列/删列顺序",
          "加列：先跑 DDL，再发代码" in dep and "删列：先发代码，再跑 DDL" in dep)
    check("★ 判据是「代码引用列集 ⊆ 库中实际列集」", "⊆" in dep and "⊆" in d5)
    check("★ 点明 ORM 整表查询全挂、非单点失效", "整表查询全部报错" in dep)
    check("★ 覆盖滚动发布混合实例期", "混合实例期" in dep and "混合实例期" in d5)
    check("★ 约定 37.5bis 已立", "37.5bis" in d5)
    check("★ 台账模板带实查 SQL 与覆盖率表", "ALL_COL_COMMENTS" in TPL and "三之二" in TPL)
    check("★ 存量无注释列只报告不阻塞", "不该拦住本版" in TPL)


def test_suite_has_invoker():
    """测试套件必须有【调用方】+ 收录必须完整（本轮审计发现的结构性缺口）。

    ⛔ 实证：`tests/run.sh` 此前**全仓无调用方**（verify.py 不跑、无 command/flow 跑、无 CI），
    于是套件可以长期红而无人知——审计期间实测了一次：某轮改动把某断言盯着的那一行换掉后，
    套件从「红在 A」变成「红在 B」，**中间没有一刻是绿的，也没有任何人看见**。
    这与本仓反复栽的「护栏无调用方」完全同族：门存在 ≠ 门被跑。
    """
    print("\n=== 测试套件的调用方与收录完整性 ===")
    repo = Path(HERE).parent.parent.parent
    run_sh = repo / ".aidp/scripts/tests/run.sh"
    check("★ run.sh 存在", run_sh.is_file())
    if not run_sh.is_file():
        return
    body = run_sh.read_text(encoding="utf-8")

    # ① 收录完整性：**全仓每一个** tests/ 下的 test_* 都必须在 run.sh 里登记。
    #   ⛔ 只扫 `.aidp/scripts/tests` 会漏掉脚手架侧那个目录 —— 而本断言的存在理由正是
    #   「没有调用方的套件可以长期红而无人知」，自己漏扫一整个目录等于给它开了个后门。
    missing = []
    for _sub in (".aidp/scripts/tests",
                 ".aidp/skills/aidp-code-engineer/scripts/tests"):
        tdir = repo / _sub
        if not tdir.is_dir():
            continue
        missing += [f.name for f in sorted(tdir.iterdir())
                    if f.is_file() and f.name.startswith("test_")
                    and f.suffix in (".py", ".js") and f.name not in body]
    check("★ run.sh 收录全部 test_* 文件（漏收 = 该套件永远绿不了也红不了）%s"
          % (missing or ""), not missing)

    # ② 调用方：约定 16 的 commit 前动作清单里必须显式有它
    #    ⛔ verify.py 刻意不跑它（那是下游也要跑的合规检查，单测是模板项目自有），
    #    所以「有没有人跑」只能靠约定 16 这份清单来保证。
    cm = (repo / "AGENTS.md").read_text(encoding="utf-8")
    check("★ 约定 16 的 commit 前动作清单里有 run.sh（否则套件无调用方）",
          "tests/run.sh" in cm)
    check("★ 并说明了为什么 verify.py 不承担它",
          "verify.py 不跑它" in cm or "单测是模板项目自有" in cm or "verify.py 不跑单测" in cm)


def test_prose_notify_runtime_home_and_negative_promise():
    print("\n[72] 通知承诺守卫：运行根占位符与否定句")
    script = REPO_ROOT / ".aidp/scripts/check_prose_vs_executable.py"
    with tempfile.TemporaryDirectory() as td:
        flow = Path(td) / ".aidp/flows/demo"
        flow.mkdir(parents=True)
        entry = flow / "phase.md"

        def findings(body):
            entry.write_text("```bash\n" + body + "\n```\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(script), "--root", td, "--json"],
                                  capture_output=True, text=True)
            return json.loads(proc.stdout)["findings"]

        check("真实 notify.py 调用中的运行根 token 不算模板占位符",
              not findings('echo "发 #4 后继续"\npython3 {{AIDP_HOME}}/scripts/notify.py --node 4'))
        check("禁止发 #F 是负向要求，不算发通知承诺",
              not findings('echo "禁止发 #F；先补齐报告"'))


def main():
    # ★ 新增 test_* 函数必须登记到这里，否则永远不执行（历史上出现过定义了却没跑的测试）
    test_readme_policy()
    test_prose_notify_runtime_home_and_negative_promise()
    test_readme_three_tier_and_scan_noise()
    test_cascade_landing_gate()
    test_cascade_residue_gate()
    test_classify_business_words_in_source_tree()
    test_release_credential_gate_coverage()
    test_report_na_result_state()
    test_cascade_obligation_gate()
    test_tick_target_version_per_command()
    test_shard_counts_path_owner()
    test_skill_ref_assets_and_install_time()
    test_cross_file_dup_whole_line()
    test_step_index_table_forms()
    test_handback_has_auto_trigger()
    test_tests_readme_group_table()
    test_prd_deploy_mode_version_scoped()
    test_plan_sprints_multifile()
    test_design_anchor_gate()
    test_version_identifier_inherited_pom_note()
    test_ledger_closed_gate()
    test_design_full_rollforward()
    test_mirror_check_ignores_pyc_and_skill_ref_drift()
    test_autopilot_mainline_regressions()
    test_release_speedups_and_gate_fixes()
    test_autopilot_deadlocks_and_gate_bypasses()
    test_upstream_doc_split_underscore_exemption()
    test_audit_round_fixes()
    test_leftover_batch_fixes()
    test_stop_guard_failopen_ledger()
    test_card_and_driver_reverse_cases()
    test_family_ledgers_split()
    test_ddl_comment_and_release_order()
    test_suite_has_invoker()
    test_interactive_single_shot_no_handback()
    test_convention_dup()
    test_version_identifier()
    test_baseline_run_state_and_version_pick()
    test_baseline_build_addressing_and_split_version_guard()
    test_phase_completion_and_obligation_reckoning()
    test_card_gate_build_scoped_and_self_derived()
    test_release_scope_covers_transitional_versions()
    test_release_baseline_check()
    test_autopilot_stuck_check()
    test_ceremony_ledger_pre_build_card()
    test_card_title_project_name()
    test_changelog_fix_scope()
    test_tick_flags_target_version_no_fallback()
    test_version_identifier_nested_reactor()
    test_md_anchors()
    test_ghost_flags()
    test_loop_examples()
    test_line_refs()
    test_shard_counts()
    test_sprint_numbering()
    test_tick_flags_parse_and_supply()
    test_step_index_coverage()
    test_cross_file_dup()
    test_singlesource_and_shard_style()
    test_webmcp()
    test_ui_fidelity()
    test_tick_supply_and_flags()
    test_upstream_call_log()
    test_skill_ref_freshness()
    test_tick_namespace_isolation()
    test_flow_bash_syntax()
    test_chain_unattended()
    test_code_inventory()
    test_requirement_query()
    test_archive_old_artifacts()
    test_handback_check()
    test_defect_retest_closure()
    test_webmcp_probe_fallback()
    test_entry_mode_build_scoped()
    test_dev_scale_and_reversal_gate()
    test_design_goals_ratchet()
    test_cascade_bypass_and_commit_gate()
    test_doc_numbering_and_selfcheck()
    test_yield_wake_source_plumbing()
    test_memory_section_loss_guard()
    test_cascade_bypass_structural_shape()
    test_index_staleness_and_mirror_copy()
    test_fail_handle_five_steps()
    test_mock_guard_split_by_marker()
    test_gates_see_the_encapsulated_form()
    test_fail_handle_freeze_now_and_enum_guard()
    test_commonmark_fence_and_env_freshness()
    test_defect_triage_and_block_review()
    test_classify_push_accumulates()
    test_residue_variants_and_verdict_line()
    test_exec_report_inherits_cases()
    test_card_section_file_and_render_scope()
    test_design_goal_formal_landings()
    test_autopilot_reset()
    test_freeze_contract()
    test_skill_gate_list()
    test_terminology_and_conv30()
    test_ledger_format_tolerance()
    test_case_baseline_binding()
    test_subagent_cascade_contract()
    test_project_count_claims()
    test_conv30_baseline_key()
    print(f"\n══ 结果：{_passed} passed / {_failed} failed / {_skipped} skipped ══")
    return 1 if _failed else 0


# ────────────────────────────────────────────────────────────
# check_shard_counts.py — 分片自称片数 / 范围记法 vs 实际文件数（ERROR）
# ────────────────────────────────────────────────────────────
def test_shard_counts():
    import check_shard_counts as SC
    print("【check_shard_counts 分片自称片数 / 范围记法】")

    files = {f".aidp/flows/demo-cmd/phase-0-{i}.md": "x\n" for i in range(1, 8)}
    files[".aidp/flows/demo-cmd/phase-0-6b.md"] = "x\n"       # 二次切分片
    files[".aidp/flows/demo-cmd/rationale.md"] = "x\n"        # 附属，不计执行分片

    bad = dict(files)
    bad[".aidp/commands/demo-cmd.md"] = "demo-cmd 的 Phase 0 已切成 **7 片**\n"
    check("片数少算 → 检出",
          any(f["kind"] == "片数" for f in SC.run(str(_mkdocs(bad)))["findings"]))

    bad2 = dict(files)
    bad2[".aidp/commands/demo-cmd.md"] = "依次 Read `phase-0-1.md` … `phase-0-7.md`\n"
    check("范围记法漏 b 分片 → 检出（这正是整片漏 Read 的形状）",
          any(f["kind"] == "范围记法" and "phase-0-6b.md" in f["actual"]
              for f in SC.run(str(_mkdocs(bad2)))["findings"]))

    ok = dict(files)
    ok[".aidp/commands/demo-cmd.md"] = (
        "依次 Read `phase-0-1.md` … `phase-0-6.md` / `phase-0-6b.md` / `phase-0-7.md`\n")
    check("显式列出 b 分片 → 零误报",
          not any(f["kind"] == "范围记法" for f in SC.run(str(_mkdocs(ok)))["findings"]))

    ordc = dict(files)
    ordc[".aidp/flows/demo-cmd/phase-0-1.md"] = "demo-cmd 第 1 片（共 8 片）\n"
    check("序数「第 N 片」不误报",
          not any(f["kind"] == "片数" for f in SC.run(str(_mkdocs(ordc)))["findings"]))

    cross = dict(files)
    cross[".aidp/flows/other-cmd/phase-0-1.md"] = "x\n"
    cross[".aidp/flows/other-cmd/phase-0-2.md"] = "x\n"
    cross[".aidp/commands/other-cmd.md"] = "依次 Read `phase-0-1.md` … `phase-0-2.md`\n"
    check("跨命令同名前缀不误报",
          not any(f["kind"] == "范围记法" and f["file"].endswith("other-cmd.md")
                  for f in SC.run(str(_mkdocs(cross)))["findings"]))


# ────────────────────────────────────────────────────────────
# check_sprint_numbering.py — Sprint 编号跨版本连续性 + 划分粒度（两个下游实测问题）
# ────────────────────────────────────────────────────────────
def test_sprint_numbering():
    import check_sprint_numbering as SN
    print("【check_sprint_numbering Sprint 编号跨版本 + 划分粒度】")

    def mk(sprints_by_ver, matrix=None, mver="V0.2.0"):
        root = Path(tempfile.mkdtemp())
        for v, nums in sprints_by_ver.items():
            d = root / "memory" / v / "alice" / "sprints"
            d.mkdir(parents=True, exist_ok=True)
            for n in nums:
                (d / f"sprint-{n:03d}.md").write_text("x\n", encoding="utf-8")
        if matrix is not None:
            pd = root / "docs" / "plans" / mver
            pd.mkdir(parents=True, exist_ok=True)
            (pd / "01_研发执行计划.md").write_text(matrix, encoding="utf-8")
        return root

    HEAD = ("## 任务分配矩阵\n\n"
            "| 功能模块 | 后端任务 | 前端任务 | 负责人 | Sprint | 对应需求章节 |\n"
            "|---|---|---|---|---|---|\n")

    # ── 问题1：新版本从 001 重来 → A1 跨版本重复 ──
    root = mk({"V0.1.0": [1, 2, 3], "V0.2.0": [1, 2]})
    r = SN.check(str(root))
    a1 = [f for f in r["findings"] if f["rule"] == "A1-跨版本重复"]
    check("新版本重置编号 → 检出 A1 跨版本重复", len(a1) == 2 and not r["passed"])
    check("A1 为 Critical", all(f["level"] == "Critical" for f in a1))

    # ── next 必须跨版本取号（问题1 的正解）──
    nxt, mx = SN.next_number(str(root))
    check("next 跨版本取 MAX+1（不是当前版本内的 003）", nxt == 4 and mx == 3)

    # ── 问题2：同一功能被拆到两个 Sprint + 各自单端 ──
    root = mk({"V0.1.0": [1, 2, 3]},
              HEAD + "| 用户管理 | 5 个接口 | - | alice | Sprint-004 | `a.md#u` |\n"
                     "| 用户管理 | - | 3 个页面 | alice | Sprint-005 | `a.md#u` |\n")
    r = SN.check(str(root))
    b1 = [f for f in r["findings"] if f["rule"] == "B1-功能跨Sprint"]
    b2 = [f for f in r["findings"] if f["rule"] == "B2-单端Sprint"]
    check("同一功能跨 Sprint → 检出 B1", len(b1) == 1 and b1[0]["level"] == "Critical")
    check("B1 文案点名两个 Sprint", "sprint-004" in b1[0]["detail"] and "sprint-005" in b1[0]["detail"])
    check("按端拆分 → 两个单端 Sprint 各报一次 B2", len(b2) == 2)
    check("B2 为 Important（不硬拦，确有单端需求）",
          all(f["level"] == "Important" for f in b2))

    # ── 合规形态：跨版本连续 + 功能内含前后端 → 零发现 ──
    root = mk({"V0.1.0": [1, 2, 3], "V0.2.0": [4, 5]},
              HEAD + "| 用户管理 | 5 个接口 | 3 个页面 | alice | Sprint-004 | `a.md#u` |\n")
    r = SN.check(str(root))
    check("合规形态 passed=True", r["passed"] is True)
    check("合规形态无 Critical/Important",
          not [f for f in r["findings"] if f["level"] in ("Critical", "Important")])

    # ── 单端豁免：标注「单端/仅前端」不误报 ──
    root = mk({"V0.1.0": [1]},
              HEAD + "| 登录页改版（单端·仅前端） | - | 2 个页面 | alice | Sprint-002 | `a.md#l` |\n")
    r = SN.check(str(root))
    check("显式标注单端 → 不报 B2",
          not [f for f in r["findings"] if f["rule"] == "B2-单端Sprint"])

    # ── 断号只报 Info、不判失败（Sprint 可能被取消/合并）──
    root = mk({"V0.1.0": [1, 2], "V0.2.0": [7]})
    r = SN.check(str(root))
    a3 = [f for f in r["findings"] if f["rule"] == "A3-断号"]
    check("断号 → Info 且 passed 仍为 True", len(a3) == 1 and r["passed"] is True)

    # ── 空项目 → 不适用，不误报；next 从 001 起 ──
    root = Path(tempfile.mkdtemp())
    r = SN.check(str(root))
    check("无 Sprint → applicable=False 且 passed", r["applicable"] is False and r["passed"])
    check("空项目 next=001", SN.next_number(str(root))[0] == 1)

    # ── 列序变化不静默错位（表头动态定位）──
    root = mk({"V0.1.0": [1]},
              "## 任务分配矩阵\n\n"
              "| Sprint | 功能模块 | 负责人 | 前端任务 | 后端任务 |\n"
              "|---|---|---|---|---|\n"
              "| Sprint-002 | 订单管理 | alice | 2 个页面 | 4 个接口 |\n")
    r = SN.check(str(root))
    check("列序调换仍能正确解析（按表头定位、不写死列序）",
          r["matrix_rows"] == 1 and r["passed"] is True)


# ────────────────────────────────────────────────────────────
# autopilot_tick_flags.py 参数解析 + check_tick_var_supply.py 供给链巡检
# ────────────────────────────────────────────────────────────
def test_tick_flags_parse_and_supply():
    print("【tick flags：单 flag 解析 + 变量供给链】")
    import importlib.util
    TF = os.path.join(os.path.dirname(HERE), "autopilot_tick_flags.py")
    SUP = os.path.join(os.path.dirname(HERE), "check_tick_var_supply.py")
    spec = importlib.util.spec_from_file_location("_tf", TF)
    TFM = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(TFM)

    # ★ 回归（单元测，无副作用）：`$ARGUMENTS` 为【单个以 -- 开头的 token】时，argparse 的
    #   「以 - 开头的 token 不作为选项值」规则会让 `--arguments --unattended` 报
    #   `expected one argument` 并 **exit 2**——而那正是文档钉死的 7×24 标准挂法
    #   `/loop 10m /sprint-autopilot --unattended`。崩在 argparse 层 = cmd_parse 一行没跑 =
    #   「整段重写、不残留上一 tick」承诺失效，上一 tick 的 SKIP_DEV=1 继续生效 →
    #   此后每个 tick 静默走 test-only、开发永不发生。修法 = 解析前归一为 `--arguments=<值>`。
    for a in ("--unattended", "--once", "--no-loop", "--skip-dev"):
        got = TFM._normalize_argv(["parse", "--command", "autopilot", "--arguments", a])
        check(f"★单 flag `{a}` 被归一为 = 形式（argparse 才不会当成下一个选项）",
              f"--arguments={a}" in got)
    check("多 flag（含空格、本就是一个 token）同样归一",
          "--arguments=--skip-dev --unattended" in
          TFM._normalize_argv(["parse", "--arguments", "--skip-dev --unattended"]))
    check("空值不报错、原样归一",
          "--arguments=" in TFM._normalize_argv(["parse", "--arguments", ""]))
    check("不含 --arguments 时原样返回",
          TFM._normalize_argv(["list", "--command", "autopilot"])
          == ["list", "--command", "autopilot"])
    # 归一后 argparse 必须真能解析（否则只是换了个崩法）
    import argparse as _ap
    _p = _ap.ArgumentParser()
    _p.add_argument("--arguments", default="")
    ns, _rest = _p.parse_known_args(TFM._normalize_argv(["--arguments", "--unattended"]))
    check("★归一后 argparse 真能取到值（不再 exit 2）", ns.arguments == "--unattended")

    # ★ 供给链巡检（只读脚本，无副作用）
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
    r = subprocess.run([sys.executable, SUP, "--root", root, "--json"],
                       capture_output=True, text=True)
    try:
        data = json.loads(r.stdout or "{}")
    except ValueError:
        data = {}
    names = {f.get("name") for f in (data.get("findings") or []) if f.get("level") == "ERROR"}
    check("★ENTRY_MODE 已有供给链（恒空会让 test-only 分支不可达 + 收尾门恒按 full 判）",
          "ENTRY_MODE" not in names)
    check("供给链巡检可运行且产出结构化结果", data.get("applicable") is True)


# ────────────────────────────────────────────────────────────
# check_step_index_coverage.py — 骨架表漏登记 Step（漏登记 = 该步永不执行）
# ────────────────────────────────────────────────────────────
def test_step_index_coverage():
    import check_step_index_coverage as SI
    print("【骨架表 ↔ flow 分片 Step 覆盖】")

    def mk(table_rows, shard_heads, shard2=("### Step 9.9：凑第二片",)):
        root = Path(tempfile.mkdtemp())
        (root / ".aidp" / "commands").mkdir(parents=True)
        (root / ".aidp" / "flows" / "demo").mkdir(parents=True)
        (root / ".aidp/commands/demo.md").write_text(
            "| Step | 分片 |\n|---|---|\n" + "\n".join(table_rows) + "\n", encoding="utf-8")
        (root / ".aidp/flows/demo/x.md").write_text("\n".join(shard_heads) + "\n", encoding="utf-8")
        (root / ".aidp/flows/demo/y.md").write_text("\n".join(shard2) + "\n", encoding="utf-8")
        return root

    # ★ 真实事故形态：表里逐个列举了 2.7.3 / 2.7.5，分片有 2.7.4 却没进表 → 该步永不执行
    r = SI.run(str(mk(["| **2.7** | x.md |", "| **2.7.3** | x.md |", "| **2.7.5** | x.md |"],
                      ["### Step 2.7.3：b", "### Step 2.7.4：漏登记的", "### Step 2.7.5：c"])))
    check("★兄弟已列举却漏一个 → 命中", not r["passed"] and r["findings"][0]["step"] == "2.7.4")

    # 按父级粒度登记（表里只有 2.7）→ 子步不进表属正常，不得误报
    r = SI.run(str(mk(["| **2.7** | x.md |", "| **3.1** | x.md |"],
                      ["### Step 2.7.1：a", "### Step 2.7.2：b", "### Step 2.7.9：c"])))
    check("★按父级粒度登记 → 子步不误报", r["passed"])

    # 同父级表里只有 1 个子步 → 不足以判定为"列举模式"，不报
    r = SI.run(str(mk(["| **2.7.3** | x.md |", "| **3.1** | x.md |"],
                      ["### Step 2.7.3：a", "### Step 2.7.4：b"])))
    check("★同父仅 1 个子步 → 不判为列举模式、不误报", r["passed"])

    # 区间记法 `2.4.1–2.4.3.5` 覆盖区间内编号
    r = SI.run(str(mk(["| **2.4.1–2.4.3.5** | x.md |", "| **2.4.4** | x.md |"],
                      ["### Step 2.4.2：a", "### Step 2.4.3：b", "### Step 2.4.4：c"])))
    check("★区间记法覆盖区间内编号（不误报 2.4.2/2.4.3）", r["passed"])

    # `**0.2**（子步骤 1–4）|` 这类带后缀说明的登记要能读到
    r = SI.run(str(mk(["| **0.1** | x.md |", "| **0.2**（子步骤 1–4）| x.md |"],
                      ["### 0.1：a", "### 0.2 baseline 读取（本片覆盖子步骤 1 – 4）"])))
    check("★带后缀说明的表格登记能被读到（不误报 0.2）", r["passed"])

    # 反向（表有·分片无）刻意不查——骨架表可能登记命令主体内联的 Step
    r = SI.run(str(mk(["| **1.1** | x.md |", "| **1.2** | x.md |", "| **1.3** | 命令主体内联 |"],
                      ["### Step 1.1：a", "### Step 1.2：b"])))
    check("★反向不查（表有分片无不报，避免误报内联 Step）", r["passed"])


# ────────────────────────────────────────────────────────────
# check_cross_file_dup.py — 跨文件双写（单一信源纪律的机器化）
# ────────────────────────────────────────────────────────────
def test_cross_file_dup():
    import check_cross_file_dup as CD
    print("【跨文件长片段双写】")
    # ★ 归一化后须 >150 字符才到 ERROR 档（80~150 只是 WARN）——样本短了测的就是另一档。
    #   用程序生成长度而非手数字符：手写样本上一版只有 146 字符、悄悄测成了 WARN 档。
    LONG = "跨文件双写检测样本用于验证阈值判定是否生效，" * 8      # 归一化后 ~176 字符
    assert len(CD._norm(LONG)) > 150, "样本长度不足，测到的是 WARN 档而非 ERROR 档"

    def mk(files):
        root = Path(tempfile.mkdtemp())
        d = root / ".aidp" / "commands"
        d.mkdir(parents=True)
        for name, body in files.items():
            (d / name).write_text(body, encoding="utf-8")
        return root

    r = CD.run(str(mk({"a.md": LONG + "\n", "b.md": LONG + "\n"})))
    check("★同一长片段出现在两个文件 → ERROR", not r["passed"])

    r = CD.run(str(mk({"a.md": LONG + "\n", "b.md": "完全不同的内容。\n"})))
    check("★只出现在一个文件 → 不报", r["passed"])

    # 同文件内重复不管（模板/示例的正常重复）
    r = CD.run(str(mk({"a.md": LONG + "\n\n" + LONG + "\n"})))
    check("★同文件内重复 → 不报（只比跨文件）", r["passed"])

    # 豁免：带理由的 ignore 必须生效（正则若要求 ignore 紧跟 -->，带理由的会静默失效）
    r = CD.run(str(mk({"a.md": "<!-- dup-check: ignore 分片自包含 -->\n" + LONG + "\n",
                       "b.md": LONG + "\n"})))
    check("★带中文理由的豁免生效（单侧豁免即不再构成跨文件重复）", r["passed"])

    # 豁免作用域覆盖到空行/围栏为止——多行代码块只标一次即可
    body = "<!-- dup-check: ignore 分片自包含 -->\n" + LONG + "\n" + LONG + "2\n"
    r = CD.run(str(mk({"a.md": body, "b.md": LONG + "\n" + LONG + "2\n"})))
    check("★豁免覆盖到空行为止（多行块只需标一次）", r["passed"])


# ────────────────────────────────────────────────────────────
# check_singlesource_pointer.py + check_shard_id_style.py
# ────────────────────────────────────────────────────────────
def test_singlesource_and_shard_style():
    import check_singlesource_pointer as SP
    import check_shard_id_style as SS
    print("【单一信源指针 + 分片标题风格】")

    def mkdoc(body, extra=None):
        root = Path(tempfile.mkdtemp())
        d = root / ".aidp" / "commands"
        d.mkdir(parents=True)
        (d / "a.md").write_text(body, encoding="utf-8")
        for rel, txt in (extra or {}).items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding="utf-8")
        return root

    # 契约路径指不到 → ERROR
    r = SP.run(str(mkdoc("单一信源见 `.aidp/flows/nope/gone.md`。\n")))
    check("★契约路径指不到 → ERROR", not r["passed"])
    # 指得到 → 不报
    r = SP.run(str(mkdoc("详规见 `.aidp/rules/code.md`。\n",
                         {".aidp/rules/code.md": "x\n"})))
    check("★契约路径指得到 → 不报", r["passed"])
    # 三类不该报的：运行时文件 / 迭代产物 / 省略泛指
    r = SP.run(str(mkdoc("单一信源见 `.mcp.json` 与 `00_索引.md` 与 `phase-0-N.md`。\n")))
    check("★运行时/产物/泛指路径不误报", r["passed"])
    # 运行时凭据（落在 .aidp/ 下但按 example 自建、已 gitignore）
    r = SP.run(str(mkdoc("详见 `.aidp/skills/demo-skill/assets/config.json`。\n")))
    check("★运行时凭据 config.json 不误报（不存在是设计而非断链）", r["passed"])
    # 无断言词的行不扫（避免把普通正文里的路径当指针）
    r = SP.run(str(mkdoc("这里只是提到 `.aidp/flows/nope/gone.md` 而已。\n")))
    check("★无「单一信源/详规」断言词 → 不扫", r["passed"])

    def mkflow(files):
        root = Path(tempfile.mkdtemp())
        d = root / ".aidp" / "flows" / "demo"
        d.mkdir(parents=True)
        for n, t in files.items():
            (d / n).write_text(t, encoding="utf-8")
        return root

    # ★ 分层（### 带前缀 + #### 裸编号）是正常设计，不得误报
    r = SS.run(str(mkflow({"a.md": "### Step 3.1：主步\n#### 3.1.1：子步\n",
                           "b.md": "### Step 3.2：主步\n#### 3.2.1：子步\n"})))
    check("★主步带前缀 + 子步裸编号的分层 → 不误报", not r["findings"])
    # 同一层级内混用 → WARN
    r = SS.run(str(mkflow({"a.md": "#### Step 3.1.1：甲\n#### Step 3.1.2：乙\n",
                           "b.md": "#### 3.1.3：丙\n"})))
    check("★同层级内两种形态并存 → 命中",
          len(r["findings"]) == 1 and r["findings"][0]["heading_level"] == 4)
    check("★给出多数派建议", r["findings"][0]["suggest"] == "with-prefix")


# ────────────────────────────────────────────────────────────
# check_webmcp.py — 可选能力的启用判定 + 三项守卫（未启用必须彻底静默）
# ────────────────────────────────────────────────────────────
def test_webmcp():
    import check_webmcp as WM
    print("【WebMCP 启用判定 + 三项守卫】")

    def mk(prd=None, srcs=None, testenv=None, rule_installed=True, tpl=True):
        root = Path(tempfile.mkdtemp())
        # 详规是「按需安装」的：模板位恒有；rule_installed=True 表示该项目已装到 rules/
        if tpl:
            t = root / ".aidp" / "templates" / "optional-rules"
            t.mkdir(parents=True)
            (t / "webmcp.md").write_text("# WebMCP 详规（模板位）\n", encoding="utf-8")
        if rule_installed:
            r = root / ".aidp" / "rules"
            r.mkdir(parents=True, exist_ok=True)
            (r / "webmcp.md").write_text("# WebMCP 详规（模板位）\n", encoding="utf-8")
        if prd is not None:
            d = root / "docs" / "requirements" / "V0.1.0" / "产品提供"
            d.mkdir(parents=True)
            (d / "PRD.md").write_text(prd, encoding="utf-8")
        for rel, txt in (srcs or {}).items():
            p = root / "code" / "frontend" / "app" / "src" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding="utf-8")
        for ver, txt in (testenv or {}).items():
            p = root / "docs" / "testing" / ver / "研发自测" / "01_测试环境与账号.md"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(txt, encoding="utf-8")
        return str(root)

    ON = "---\nautopilot_decisions:\n  webmcp:\n    enabled: true\n---\n"
    ENTRY = "navigator.modelContext"

    # ★ 最重要的一条：未声明 = 未启用 → applicable:false + 零 finding
    #   （哪怕代码里有一堆违规，也不能给未启用项目长出任何告警）
    r = WM.run(mk(prd="# 无 autopilot_decisions\n",
                  srcs={"a.ts": f"{ENTRY}\n", "b.ts": f"{ENTRY} unregisterTool\n"}))
    check("★未声明 → applicable:false", not r["applicable"])
    check("★未声明 → 零 finding（不给未启用项目长告警）", r["findings"] == [] and r["passed"])

    # 显式关闭同样静默
    r = WM.run(mk(prd="---\nautopilot_decisions:\n  webmcp:\n    enabled: false\n---\n",
                  srcs={"a.ts": f"{ENTRY}\n", "b.ts": f"{ENTRY}\n"}))
    check("★显式 enabled:false → 静默 N/A", not r["applicable"] and r["passed"])

    # ★ 边界（防回归）：单一适配层 / unregisterTool 两项判据【已移交上游】
    #   code-verification-loop 维度 9 + 其 check_webmcp_adapter.py。本脚本**不得**再报它们——
    #   同一判据两份实现 = 改一处漏一处、两处都自称权威。这条断言就是防止有人把它加回来。
    r = WM.run(mk(prd=ON, srcs={"a.ts": f"{ENTRY}\n",
                                "b.ts": f"// {ENTRY}\nctx.unregisterTool?.('x')\n"}))
    ids = [f["check"] for f in r["findings"]]
    check("★两处适配层 + unregisterTool → 本脚本【不报】（判据已移交上游 CVL 维度 9）",
          "single-adapter" not in ids and "ghost-api" not in ids and r["passed"])
    # 供给不变量：无论是否声明，entry_symbols 恒非空——命令端总有东西可传给上游，
    # 而上游缺该入参会直接 exit 2（它拒绝猜默认值）。
    check("★恒供给非空 entry_symbols（未声明则给内置默认并标明来源）",
          r["entry_symbols"] and "内置默认" in r["symbols_source"])

    # 「测试环境与账号」只判最新版本：旧版没段不连坐、新版没段要报
    r = WM.run(mk(prd=ON, srcs={"adapter.ts": f"{ENTRY}\n"},
                  testenv={"V0.9.0": "## 六、WebMCP 带参浏览器\n",
                           "V0.10.0": "# 测试环境与账号\n"}))
    fs = [f for f in r["findings"] if f["check"] == "testenv-section"]
    check("★最新版缺 WebMCP 段 → ERROR", len(fs) == 1)
    check("★指向最新版 V0.10.0（版本序不按字符串排）", "V0.10.0" in fs[0]["file"])
    r = WM.run(mk(prd=ON, srcs={"adapter.ts": f"{ENTRY}\n"},
                  testenv={"V0.9.0": "# 旧版没有该段\n",
                           "V0.10.0": "## 六、WebMCP 带参浏览器\n"}))
    check("★旧版缺段不连坐（只看最新版）",
          not [f for f in r["findings"] if f["check"] == "testenv-section"])

    # entry_symbols 声明生效（内置默认可能过期，项目声明优先）
    d = WM.detect(mk(prd="---\nautopilot_decisions:\n  webmcp:\n    enabled: true\n"
                        "    entry_symbols: [\"navigator.modelContext\"]\n---\n"))
    check("★PRD 声明的 entry_symbols 覆盖内置默认",
          d["entry_symbols"] == [ENTRY] and "PRD 声明" in d["symbols_source"])

    # ── 按需安装：详规默认不在 rules/ 下，启用后才装 ──
    # ★ 闭环所在：启用了却没装 → 规则永远不会被路径触发加载 = 静默失效，必须硬拦
    r = WM.run(mk(prd=ON, srcs={"adapter.ts": f"{ENTRY}\n"}, rule_installed=False))
    check("★启用但详规未安装 → ERROR（否则规则永不加载、静默失效）",
          "rule-not-installed" in [f["check"] for f in r["findings"]])
    # 未启用时不装是正常的，⛔ 不得因此报错
    r = WM.run(mk(prd="# 无声明\n", rule_installed=False))
    check("★未启用 + 未安装 → 静默 N/A（不报缺失）", not r["applicable"] and r["passed"])

    # install_rule：未启用拒绝 / 启用安装 / 幂等 / --force
    root = mk(prd="---\nautopilot_decisions:\n  webmcp:\n    enabled: false\n---\n",
              rule_installed=False)
    res = WM.install_rule(root)
    check("★未启用时拒绝安装（误装=永久背上本设计要消除的成本）",
          not res["ok"] and res["action"] == "refused")
    check("★--force 可强装", WM.install_rule(root, force=True)["ok"])

    root = mk(prd=ON, rule_installed=False)
    check("★启用后安装成功", WM.install_rule(root)["action"] == "installed")
    check("★重复安装幂等", WM.install_rule(root)["action"] == "already-installed")
    check("★装完即通过 rule-not-installed 守卫",
          "rule-not-installed" not in [f["check"] for f in WM.run(root)["findings"]])
    # 模板位缺失（脚手架没铺全）时给出可辨识的失败，而不是静默不装
    res = WM.install_rule(mk(prd=ON, rule_installed=False, tpl=False))
    check("★模板位缺失 → missing-template（不静默）",
          not res["ok"] and res["action"] == "missing-template")

    # 装了但过期（模板位已升级、安装副本没跟上）→ WARN 兜底可见性
    root = mk(prd=ON, srcs={"adapter.ts": f"{ENTRY}\n"})
    (Path(root) / ".aidp/templates/optional-rules/webmcp.md").write_text("# 新版\n", encoding="utf-8")
    r = WM.run(root)
    stale = [f for f in r["findings"] if f["check"] == "rule-stale"]
    check("★安装副本过期 → WARN（不判 ERROR，刚升级未重装是正常中间态）",
          len(stale) == 1 and stale[0]["level"] == "WARN" and r["passed"])


# ────────────────────────────────────────────────────────────
# check_ui_fidelity.py — 约定 39 通用还原度：R2 / R3 / R10 三条确定性检查
#   ★ 本组的重点是**零误报断言**：这类检查一旦刷屏，下游会直接把它关掉，
#     那比漏报糟得多。故每条正例都配一条「正当写法不得命中」的反例。
# ────────────────────────────────────────────────────────────
def test_ui_fidelity():
    print("\n[25] check_ui_fidelity R2/R3/R10 + 零误报")
    import subprocess
    script = Path(__file__).resolve().parents[1] / "check_ui_fidelity.py"

    def run(files: dict, extra=None):
        root = Path(tempfile.mkdtemp())
        for rel, body in files.items():
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(body, encoding="utf-8")
        cmd = [sys.executable, str(script), "--root", str(root), "--json"] + (extra or [])
        cp = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(cp.stdout), cp.returncode

    def rules_hit(res):
        return sorted({f["rule"] for f in res["findings"]})

    # ── R2 状态视觉区分 ──────────────────────────────────────
    res, _ = run({"code/frontend/a/Bad.vue":
                  '<template>\n  <el-tag type="success">{{ row.status }}</el-tag>\n</template>\n'})
    check("R2 动态内容 + 写死颜色 → 命中", "R2" in rules_hit(res))

    res, _ = run({"code/frontend/a/Ok1.vue":
                  '<template>\n  <el-tag :type="statusType(row.s)">{{ row.statusText }}</el-tag>\n</template>\n'})
    check("R2 零误报：颜色随值绑定（正确写法）", "R2" not in rules_hit(res))

    res, _ = run({"code/frontend/a/Ok2.vue":
                  '<template>\n  <el-tag type="danger">必填</el-tag>\n</template>\n'})
    check("R2 零误报：写死内容 + 写死颜色（固定角标）", "R2" not in rules_hit(res))

    # ★ 反例固化：内容区若按「开标签 + 固定 N 行」取窗口，
    #   下一个兄弟节点的 {{ }} 会被当成本标签内容 → 误报。必须按闭合标签精确截断。
    res, _ = run({"code/frontend/a/Sibling.vue":
                  '<template>\n  <el-tag type="danger">必填</el-tag>\n'
                  '  <div>{{ row.other }}</div>\n</template>\n'})
    check("★R2 零误报（反例固化）：兄弟节点的插值不得算作本标签内容",
          "R2" not in rules_hit(res))

    # ── R3 截断可读性 ────────────────────────────────────────
    res, _ = run({"code/frontend/a/Trunc.vue":
                  '<template>\n  <div class="truncate">{{ row.remark }}</div>\n</template>\n'})
    check("R3 原子类截断无 tooltip → 命中", "R3" in rules_hit(res))

    res, _ = run({"code/frontend/a/Css.vue":
                  '<template>\n  <span class="nm">{{ row.userName }}</span>\n</template>\n'
                  '<style>\n.nm { text-overflow: ellipsis; }\n</style>\n'})
    check("R3 CSS 类截断无 tooltip → 命中", "R3" in rules_hit(res))

    res, _ = run({"code/frontend/a/OkT.vue":
                  '<template>\n  <span class="nm" :title="row.userName">{{ row.userName }}</span>\n</template>\n'
                  '<style>\n.nm { text-overflow: ellipsis; }\n</style>\n'})
    check("R3 零误报：配了 :title", "R3" not in rules_hit(res))

    res, _ = run({"code/frontend/a/OkW.vue":
                  '<template>\n  <el-tooltip :content="row.r">\n'
                  '    <div class="truncate">{{ row.r }}</div>\n  </el-tooltip>\n</template>\n'})
    check("R3 零误报：被 el-tooltip 包裹（父节点）", "R3" not in rules_hit(res))

    # ── R10 导出全量 ─────────────────────────────────────────
    res, rc = run({"code/backend/s/Bad.java":
                   'public void exportPoints(Q q) {\n'
                   '    PageHelper.startPage(q.getPageNo(), q.getPageSize());\n'
                   '    write(mapper.list(q));\n}\n'})
    check("R10 导出透传分页 → 命中", "R10" in rules_hit(res))
    check("★R10 判 Critical → 退出码 1（唯一阻断项）",
          rc == 1 and any(f["severity"] == "Critical" for f in res["findings"]))

    res, _ = run({"code/backend/s/Loop.java":
                  'public void exportUsers(Q q) {\n'
                  '    int pageNo = 1;\n'
                  '    while (true) {\n'
                  '        Page<R> p = mapper.page(new Page<>(pageNo, 1000), q);\n'
                  '        if (!p.hasNext()) break;\n        pageNo++;\n    }\n}\n'})
    check("R10 零误报：循环翻页捞全量是正当写法", "R10" not in rules_hit(res))

    res, _ = run({"code/backend/s/List.java":
                  'public PageResult listUsers(Q q) {\n'
                  '    PageHelper.startPage(q.getPageNo(), q.getPageSize());\n'
                  '    return PageResult.of(mapper.list(q));\n}\n'})
    check("R10 零误报：普通分页列表接口不是导出", "R10" not in rules_hit(res))

    # ── 豁免机制 ─────────────────────────────────────────────
    res, _ = run({"code/frontend/a/W.vue":
                  '<template>\n  <!-- fidelity-ignore: R3 装饰性副标题，产品已确认 -->\n'
                  '  <div class="truncate">{{ row.remark }}</div>\n</template>\n'})
    check("豁免：上一行 fidelity-ignore 生效", "R3" not in rules_hit(res))

    res, _ = run({"code/frontend/a/W2.vue":
                  '<template>\n  <div class="truncate">{{ r.x }}</div> <!-- fidelity-ignore: R2 错的规则号 -->\n</template>\n'})
    check("★豁免不串号：标了 R2 不能豁免 R3", "R3" in rules_hit(res))

    # ── 扫描面 ───────────────────────────────────────────────
    res, _ = run({"code/frontend/a/__tests__/Spec.vue":
                  '<template>\n  <div class="truncate">{{ x }}</div>\n</template>\n'})
    check("扫描面：测试/示例代码不参与还原度判定", res["findings"] == [])

    # ── --check 过滤 ─────────────────────────────────────────
    res, _ = run({"code/frontend/a/Multi.vue":
                  '<template>\n  <el-tag type="success">{{ s }}</el-tag>\n'
                  '  <div class="truncate">{{ r }}</div>\n</template>\n'}, extra=["--check", "R3"])
    check("--check 只跑指定规则", rules_hit(res) == ["R3"])


# ────────────────────────────────────────────────────────────
# autopilot tick 变量供给链：动态兜底接线 / 关断旗标生效 / 回落键有无写入者
#   ★ 本组三条都是「定义了却永不生效」的同一形状——本仓最贵的一类缺陷：
#     所有守卫全绿，链路却在静默走默认值。
# ────────────────────────────────────────────────────────────
def test_tick_supply_and_flags():
    print("\n[26] tick 供给链：动态兜底 / 关断旗标 / 回落键写入者")
    import importlib.util, io, contextlib
    spec = importlib.util.spec_from_file_location(
        "atf_t", str(Path(".aidp/scripts/autopilot_tick_flags.py").resolve()))
    M = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(M)

    def shell_out(mod):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.cmd_shell(None)
        return dict(l.split("=", 1) for l in buf.getvalue().splitlines())

    # ── C-1：DYNAMIC_FALLBACK 必须真的接进 cmd_shell ──────────
    check("★DYNAMIC_FALLBACK 已被 cmd_shell 引用（曾是纯死代码）",
          "DYNAMIC_FALLBACK" in M.cmd_shell.__code__.co_names)

    orig = M.DYNAMIC_FALLBACK
    # ★ 兜底函数现在接收「本轮已算出的变量表」——DEPLOY_MODE 的 PRD 兜底必须知道目标版本，
    #   否则会取到仓库里另一个版本的声明。替身签名跟着改，别退回无参 lambda。
    M.DYNAMIC_FALLBACK = {"TARGET_VERSION": lambda cur=None: "V9.9.9",
                          "DEPLOY_MODE": lambda cur=None: "cloud"}
    got = shell_out(M)
    check("★动态兜底真的被取用（DEPLOY_MODE 恒空会让云端项目被当成静态-only）",
          got.get("DEPLOY_MODE") == "'cloud'" or got.get("DEPLOY_MODE") == "cloud")
    check("★动态兜底真的被取用（TARGET_VERSION）",
          got.get("TARGET_VERSION") in ("V9.9.9", "'V9.9.9'"))

    def boom():
        raise RuntimeError("兜底求值炸了")
    M.DYNAMIC_FALLBACK = {"DEPLOY_MODE": boom}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = M.cmd_shell(None)
    check("★兜底求值抛异常不得让整条 --shell 崩掉", rc == 0)
    M.DYNAMIC_FALLBACK = orig

    # ── I-3：--no-notify 必须真能关断 ─────────────────────────
    src = Path(".aidp/scripts/autopilot_tick_flags.py").read_text(encoding="utf-8")
    check("★--no-notify 有确定性生效路径（此前只被解析、全仓 shell 零引用）",
          'out.get("NO_NOTIFY"' in src and 'out["NOTIFY_ENABLED"] = "0"' in src)

    # ── I-6：二级校验必须存在（一级只看变量名在不在表里）──────
    chk = Path(".aidp/scripts/check_tick_var_supply.py").read_text(encoding="utf-8")
    check("★供给链检查含「回落键有无写入者」二级校验",
          "_baseline_fallback_keys" in chk and "DYNAMIC_FALLBACK" in chk)
    check("★二级校验先合并 shell 反斜杠续行（否则把跨行的真写入者判成无人写）",
          "\\\\\\s*\\n" in chk or "反斜杠续行" in chk)

    # ── set 签名护栏：tick_flags.py set 只收单对（≠ baseline_edit.py set 多对）──
    check("★含 tick_flags set 多对连写护栏（两脚本签名不同，实测 baseline_edit 支持多对、tick_flags 不支持）",
          "一次只收" in chk and "baseline_edit.py set" in chk)
    check("★二级校验排除「已有 tick set 供给」的变量（否则对正确供给的变量误报）",
          "if var in set_names:" in chk)

    # 全仓不得残留多对连写（存量曾有一处：0.3.4 落盘 TARGET_VERSION + PRE_RELEASE_VERSION
    # 一次写两个 → argparse exit 2 → 两个都落不了盘，而同分片正写着「TARGET_VERSION 漏写代价最大」）
    import re as _re, glob as _glob
    bad = []
    for f in _glob.glob(".aidp/flows/**/*.md", recursive=True) + _glob.glob(".aidp/commands/*.md"):
        body = _re.sub(r"\\\s*\n\s*", " ", Path(f).read_text(encoding="utf-8", errors="replace"))
        for m in _re.finditer(r"autopilot_tick_flags\.py[^\n]*?\bset\b([^\n|;&]*)", body):
            t = _re.sub(r"--command\s+\S+", "", m.group(1))
            t = _re.sub(r'"[^"]*"|\'[^\']*\'', " ", t)
            names = list(dict.fromkeys(_re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", t)))
            if len(names) > 1:
                bad.append((f, names))
    check("★★全仓无 tick_flags set 多对连写残留（连写 = 该行整体不落盘、静默失效）", not bad)

    # ── 二次切分片首部不得自称「完整」──────────────────────
    #   切分前的整段声明若留在第 1 片里，执行体读完首片就会认为已覆盖全段、
    #   不再 Read 后续分片 → 后面的 Step 静默不执行（比报错更难发现）。
    import os as _os
    stale = []
    for f in sorted(_glob.glob(".aidp/flows/**/*-1.md", recursive=True)):
        stem = f[: -len("-1.md")]
        if not _os.path.exists(stem + "-2.md"):
            continue
        if _os.path.basename(stem) == "phase":
            continue    # sprint-autopilot 的 phase-N 是不同 Phase、不是同一段的分片
        head = "\n".join(Path(f).read_text(encoding="utf-8").splitlines()[:14])
        if _re.search(r"的完整详细步骤|的完整规则", head) and not _re.search(r"第\s*1\s*[/片]|1/\d+\s*片|首片", head):
            stale.append(f)
    check("★★二次切分片首部不得自称「完整详细步骤」（读完首片即止 = 后续 Step 静默不执行）",
          not stale)


# ────────────────────────────────────────────────────────────
# check_upstream_call_log.py — 约定 40 上游/第三方接口调用日志
#   ★ 本组两条 ★★ 断言是**真实缺陷的固化**，改脚本时不许绕过：
#     ① 出站客户端的注入名不是只有 `restTemplate`（实测同仓并存 smsRestTemplate /
#        aiStaffRestTemplate）——写死变量名会静默漏掉一半出站类，且表现为"全绿"；
#     ② 掩码常发生在**赋值行**而非日志行（`String tokenPreview = t.substring(...)+"***"`），
#        只看日志语句会把正确写法误报成凭据泄漏。
# ────────────────────────────────────────────────────────────
def test_upstream_call_log():
    print("\n[27] check_upstream_call_log C1/C2/I1/I2/I3 + 零误报")
    import subprocess
    script = Path(__file__).resolve().parents[1] / "check_upstream_call_log.py"

    def run(files: dict, extra=None):
        root = Path(tempfile.mkdtemp())
        for rel, body in files.items():
            fp = root / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(body, encoding="utf-8")
        cmd = [sys.executable, str(script), "--root", str(root), "--json"] + (extra or [])
        cp = subprocess.run(cmd, capture_output=True, text=True)
        return json.loads(cp.stdout), cp.returncode

    def hits(res):
        return sorted({f["check"] for f in res["findings"]})

    B = "code/backend/s/"

    # ── C1 零日志 ────────────────────────────────────────────
    res, rc = run({B + "Minio.java":
                   'class MinioStorageClient {\n'
                   '    void up(InputStream in) {\n'
                   '        minioClient.putObject(PutObjectArgs.builder().build());\n    }\n}\n'})
    check("C1 出站调用零日志 → 命中", "C1" in hits(res))
    check("C1 判 Critical → 退出码 1", rc == 1)

    res, _ = run({B + "MinioConfig.java":
                  'class MinioConfig {\n    @Bean MinioClient c() {\n'
                  '        return MinioClient.builder().endpoint(url).build();\n    }\n}\n'})
    check("C1 零误报：只构建客户端、不发起调用的配置类不算出站类",
          not res["findings"] and res["outbound_files"] == 0)

    # ── C2 成功路径不可见（★ 判据是「级别」不是「是否在 catch 内」）────
    all_err = ('class MessageCenterClient {\n'
               '    JsonNode post(String path, Map body) {\n'
               '        if (!properties.isReady()) {\n'
               '            log.error("[MSG] 配置未就绪 base={}", base);\n'
               '            throw new BizException();\n        }\n'
               '        String url = base + path;\n        try {\n'
               '            raw = restTemplate.postForObject(url, entity, String.class);\n'
               '        } catch (Exception e) {\n'
               '            log.error("[MSG] 调用失败 url={}", url, e);\n'
               '            throw new BizException();\n        }\n'
               '        return raw;\n    }\n}\n')
    res, rc = run({B + "Msg.java": all_err})
    check("C2 日志全为 error（成功路径不可见）→ 命中", "C2" in hits(res))
    check("★C2 判据是级别而非位置：本例的 error 日志有的在守卫、有的在 catch，"
          "按「全部 log 都在 catch 内」的旧判据一条都命中不了",
          "C2" in hits(res) and "log.error" in all_err.split("try")[0])

    res, _ = run({B + "Ok.java":
                  'class C {\n    void f() {\n'
                  '        log.info("[X] >>> {} 入参={}", url, body);\n'
                  '        restTemplate.exchange(url, m, e, Map.class);\n'
                  '        log.info("[X] <<< {} status={} 出参={} 耗时={}ms", url, st, resp, ms);\n'
                  '    }\n}\n'})
    check("C2/I1 零误报：双向 INFO + 带 URL 的正确写法全不命中", not res["findings"])

    # ── I2 只有 debug ────────────────────────────────────────
    res, _ = run({B + "Dbg.java":
                  'class C {\n    void f() {\n        log.debug("call {} {}", url, body);\n'
                  '        restTemplate.getForObject(url, String.class);\n    }\n}\n'})
    check("I2 成功路径只有 debug（生产 INFO ⇒ 看不到）→ 命中", "I2" in hits(res))
    check("I2 与 C2 互斥：有 debug 即不算「成功路径不可见」", "C2" not in hits(res))

    # ── I1 日志不含 URL ──────────────────────────────────────
    res, _ = run({B + "NoUrl.java":
                  'class C {\n    void f() {\n        log.info("[KOP] 绑定成功 uid={}", uid);\n'
                  '        restTemplate.postForEntity(apiBase + path, entity, Map.class);\n    }\n}\n'})
    check("I1 有日志但无一条提到 URL → 命中", "I1" in hits(res))

    # ── ★★ 回归①：注入名不是 restTemplate 也必须识别 ────────
    res, _ = run({B + "Sms.java":
                  'class SmsService {\n'
                  '    private final RestTemplate smsRestTemplate = new RestTemplate();\n'
                  '    void send() {\n        smsRestTemplate.postForEntity(smsUrl, e, String.class);\n    }\n}\n'})
    check("★★回归①：非标准注入名 smsRestTemplate 必须被识别为出站类（写死名字会静默漏检）",
          res["outbound_files"] == 1 and "C1" in hits(res))

    res, _ = run({B + "Redis.java":
                  'class C {\n    private final StringRedisTemplate redisTemplate;\n'
                  '    void f() {\n        redisTemplate.opsForValue().set(k, v);\n    }\n}\n'})
    check("★零误报：redisTemplate 不是出站调用（本地中间件有自己的日志机制）",
          res["outbound_files"] == 0)

    # ── I3 凭据 ──────────────────────────────────────────────
    res, _ = run({B + "Leak.java":
                  'class C {\n    void f() {\n'
                  '        log.info("调用 url={} password={}", url, password);\n'
                  '        restTemplate.postForEntity(url, e, String.class);\n    }\n}\n'})
    check("I3 密码直接作为日志实参 → 命中", "I3" in hits(res))

    # ★★ 回归②：掩码发生在赋值行
    res, _ = run({B + "Masked.java":
                  'class C {\n    void f() {\n'
                  '        String tokenPreview = token.substring(0, 6) + "***" + token.substring(n);\n'
                  '        log.info("[X] >>> {} TOKEN={}", fullUrl, tokenPreview);\n'
                  '        restTemplate.exchange(fullUrl, m, e, Map.class);\n    }\n}\n'})
    check("★★回归②：变量在赋值行已掩码后再打印属正确写法，不得命中 I3",
          "I3" not in hits(res))

    # 凭据上下文：过泛的名字（code）只在凭据方法里才算
    res, _ = run({B + "Vc.java":
                  'class SmsService {\n    public boolean sendVerifyCode(String phone) {\n'
                  '        log.warn("[短信] 未配置，验证码仅存 Redis: phone={}, code={}", phone, code);\n'
                  '        smsRestTemplate.postForEntity(smsUrl, e, String.class);\n'
                  '        return true;\n    }\n}\n'})
    check("★I3 凭据上下文：sendVerifyCode() 里的 code 是验证码 → 命中", "I3" in hits(res))

    res, _ = run({B + "Biz.java":
                  'class C {\n    public void queryList(String url) {\n'
                  '        log.info("[X] <<< {} 业务返回 code={} msg={}", url, code, msg);\n'
                  '        restTemplate.getForObject(url, String.class);\n    }\n}\n'})
    check("★★I3 零误报：普通方法里的 code 是上游业务码（每个客户端都会打）→ 不得命中",
          "I3" not in hits(res))

    # ── 个人信息默认不检 ─────────────────────────────────────
    pii_src = {B + "Pii.java":
               'class C {\n    void f(String url) {\n'
               '        log.info("发送 url={} phone={}", url, phone);\n'
               '        restTemplate.postForEntity(url, e, String.class);\n    }\n}\n'}
    res, _ = run(pii_src)
    check("个人信息字段默认不检（高频出现，默认开会淹没真正的凭据泄漏）", "I3" not in hits(res))
    res, _ = run(pii_src, ["--pii"])
    check("--pii 显式开启后才检个人信息字段", "I3" in hits(res))

    # ── Feign 接口整体排除 ───────────────────────────────────
    res, _ = run({B + "Api.java":
                  '@FeignClient(name = "user")\ninterface UserApi {\n'
                  '    @GetMapping("/u") User get(@PathVariable Long id);\n}\n'})
    check("Feign 接口整体排除（无方法体，日志由 feign.Logger 全局配置承担）",
          res["outbound_files"] == 0 and not res["findings"])

    # ── 同文件拦截器抵扣 ─────────────────────────────────────
    res, _ = run({B + "WithItc.java":
                  'class C {\n    void init() {\n'
                  '        this.restTemplate.getInterceptors().add(new LoggingItc());\n    }\n'
                  '    void f() {\n        restTemplate.getForObject(url, String.class);\n    }\n'
                  '    static class LoggingItc implements ClientHttpRequestInterceptor {\n'
                  '        public ClientHttpResponse intercept(a, b, c) {\n'
                  '            log.info("[X] >>> {} {} 入参={}", m, url, body);\n'
                  '            return r;\n        }\n    }\n}\n'})
    check("同文件内挂了出站日志拦截器 → C1/C2 抵扣（拦截器是推荐写法，不能反被判违规）",
          "C1" not in hits(res) and "C2" not in hits(res))

    res, _ = run({B + "ItcButSdk.java":
                  'class C {\n    void init() {\n'
                  '        this.restTemplate.getInterceptors().add(new LoggingItc());\n    }\n'
                  '    void f() {\n        minioClient.putObject(args);\n    }\n}\n'})
    check("★HTTP 拦截器不抵扣 SDK 直连（拦截器覆盖不到对象存储 SDK）", "C1" in hits(res))

    # ── 豁免 ─────────────────────────────────────────────────
    res, rc = run({B + "Waived.java":
                   '// upstream-log-ignore: C1 心跳探针，按约定 40 例外降采样\n'
                   'class Probe {\n    void ping() {\n'
                   '        restTemplate.getForObject(healthUrl, String.class);\n    }\n}\n'})
    check("豁免生效且退出码归零", "C1" not in hits(res) and rc == 0)
    check("豁免计入 waived 统计（让豁免本身可被审计，而不是隐形）", res["waived"] >= 1)

    # ── 健壮性 ───────────────────────────────────────────────
    res, _ = run({B + "Empty.java": "", B + "NoEol.java": "class A { }"})
    check("空文件 / 无结尾换行不崩", res["scanned_files"] == 2)

    cp = subprocess.run([sys.executable, str(script), "--check", "C9"],
                        capture_output=True, text=True)
    check("未知检查项 → 退出码 2（入参错，不是维度违规）", cp.returncode == 2)


# ────────────────────────────────────────────────────────────
# check_skill_ref_freshness.py — 命令/Agent 引用上游 SKILL 内部编号的新鲜度
#   ★ 两条 ★★ 是**实测误报模式**的固化，改归属逻辑时不许绕过：
#     ① 一行里同时点名两个 SKILL 是常态，编号必须归给**左侧最近**的那个；
#     ② 还必须**限距**——reference/ 里有单条 bullet 上千字符、顺带点名四五个 SKILL，
#        实测有一处编号距最近 SKILL 名 713 字符，那不是归属、是噪音。
# ────────────────────────────────────────────────────────────
def test_skill_ref_freshness():
    print("\n[28] check_skill_ref_freshness SKILL 编号引用新鲜度 + 零误报")
    import subprocess
    script = Path(__file__).resolve().parents[1] / "check_skill_ref_freshness.py"
    repo = Path(__file__).resolve().parents[3]

    def run(files: dict, skills: dict):
        root = Path(tempfile.mkdtemp())
        for rel, body in files.items():
            fp = root / ".aidp" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(body, encoding="utf-8")
        for rel, body in skills.items():
            fp = root / ".aidp" / "skills" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(body, encoding="utf-8")
        cp = subprocess.run([sys.executable, str(script), "--root", str(root), "--json"],
                            capture_output=True, text=True)
        return json.loads(cp.stdout), cp.returncode

    SK = {"demo-skill/SKILL.md": "#### 维度 1: a\n#### 维度 2: b\n#### 维度 3: c\n",
          "other-skill/SKILL.md": "#### 维度 1: x\n" + "".join(
              "#### 维度 %d: y\n" % i for i in range(2, 22))}

    # ── 计数声明过期 ──────────────────────────────────────────
    res, rc = run({"commands/a.md": "跑 `demo-skill` 的全部 2 个维度\n"}, SK)
    check("计数声明过期（自称 2 实为 3）→ ERROR", res["errors"] == 1 and rc == 1)

    res, _ = run({"commands/a.md": "跑 `demo-skill` 的全部 3 个维度\n"}, SK)
    check("计数正确 → 零告警", res["errors"] == 0)

    # ── 索引引用不存在 ────────────────────────────────────────
    res, _ = run({"commands/a.md": "见 `demo-skill` 维度 7 的判据\n"}, SK)
    check("索引引用不存在的编号 → ERROR", res["errors"] == 1)

    res, _ = run({"commands/a.md": "见 `demo-skill` 维度 2 的判据\n"}, SK)
    check("索引引用存在的编号 → 零告警", res["errors"] == 0)

    # ── ★★ 归属①：一行两个 SKILL，各归各的 ────────────────────
    res, _ = run({"commands/a.md":
                  "该表同时是 `demo-skill` 维度 2 与 `other-skill` 维度 21 的基准\n"}, SK)
    check("★★零误报：一行两个 SKILL 时编号归左侧最近的那个（维度 21 属 other-skill）",
          res["errors"] == 0)

    # ── ★★ 归属②：限距，远距离不构成归属 ──────────────────────
    far = "`demo-skill` 开头点了一次名。" + "填充内容。" * 90 + "这里提到维度 21 的主体判据。\n"
    res, _ = run({"reference/x.md": far}, SK)
    check("★★零误报：编号距最近 SKILL 名超窗口（实测噪音 713 字符）→ 不归属、不报",
          res["errors"] == 0)

    # ── 无归属不猜 ────────────────────────────────────────────
    res, _ = run({"commands/a.md": "本命令自己的 9 维度审计\n"}, SK)
    check("零误报：行内无 SKILL 名 → 不归属、不报（本仓 /health-check 有自己的 9 维度）",
          res["errors"] == 0)

    # ── 脚本引用 ──────────────────────────────────────────────
    res, _ = run({"commands/a.md": "跑 `demo-skill` 的 `check_ghost.py`\n"}, SK)
    check("引用不存在的 SKILL 脚本 → ERROR", res["errors"] == 1)

    # ── 豁免 ──────────────────────────────────────────────────
    res, rc = run({"commands/a.md":
                   "跑 `demo-skill` 的全部 2 个维度 <!-- skillref-check: ignore -->\n"}, SK)
    check("行内豁免生效", res["errors"] == 0 and rc == 0)

    # ── 真仓库不得有 ERROR（新鲜度是常态要求，不是"努力目标"）──
    cp = subprocess.run([sys.executable, str(script), "--root", str(repo), "--json"],
                        capture_output=True, text=True)
    real = json.loads(cp.stdout)
    check("★真仓库 SKILL 编号引用零过期", real["errors"] == 0)

    # ── ★★ 仓库专属不变量：/sprint-design 回检表必须覆盖 dla 派单清单 ──
    #   通用脚本抓不到这条（SKILL 自己的派单块必然引用了自家脚本，orphan 逃逸条件成立）；
    #   而"上游新增硬门、项目侧没接线"正是本仓最高频的失效形态——门配了却永不运行。
    import re as _re2
    dispatch = (repo / ".aidp/skills/dev-logic-architect/references/flow-qr-dispatch.md")
    table = (repo / ".aidp/flows/sprint-design/step-1.6-落盘后回检.md")
    if dispatch.is_file() and table.is_file():
        tt = table.read_text(encoding="utf-8")
        # 命令端不另列清单：委派 SKILL 派单块「原样跑全部脚本」，新增硬门自动覆盖、不会漏接线
        check("★★/sprint-design Step1.6 委派 dev-logic-architect 派单块原样跑全部脚本（不另列易漏的平行清单）",
              "flow-qr-dispatch.md" in tt and "原样跑全部脚本" in tt
              and bool(_re2.findall(r"<SKILL_DIR>/scripts/(check_[a-z_]+\.py)",
                                    dispatch.read_text(encoding="utf-8"))))


# ────────────────────────────────────────────────────────────
# autopilot_tick_flags.py — 两条 7×24 链路的 tick 命名空间隔离
#   ★ 曾是同一个常量 `autopilot.tick`：两条 loop 的 tick 起点都调 `parse`，
#     而 `parse` 先 del 再整段重写 ⇒ 任一方开 tick 就清空对方本轮已落盘的变量。
#     10min tick 必然跨越 ≥1 次 5min tick，标准挂法下 100% 发生。
# ────────────────────────────────────────────────────────────
def test_tick_namespace_isolation():
    print("\n[29] tick 命名空间按命令隔离（两条 7×24 链路互不清空）")
    import subprocess, shutil
    scripts = Path(__file__).resolve().parents[1]
    root = Path(tempfile.mkdtemp())
    (root / ".aidp/scripts").mkdir(parents=True)
    for n in ("autopilot_tick_flags.py", "baseline_edit.py", "aidp_runtime.py"):
        shutil.copy(scripts / n, root / ".aidp/scripts" / n)
    (root / "memory").mkdir()
    (root / "memory/.sprint-autopilot-baseline.json").write_text('{"versions":{}}', encoding="utf-8")
    TF = str(root / ".aidp/scripts/autopilot_tick_flags.py")

    def run(*args):
        return subprocess.run([sys.executable, TF] + list(args),
                              capture_output=True, text=True, cwd=str(root))

    run("parse", "--command", "autopilot", "--arguments", "--unattended")
    rc = run("set", "--command", "autopilot", "SKIP_DEV", "1").returncode
    check("开发链路落盘 SKIP_DEV=1", rc == 0)

    # 测试链路开 tick —— 旧实现在这一步把上面的值清空
    run("parse", "--command", "aiauto-test", "--arguments", "--once")

    dev = run("--command", "autopilot", "--shell").stdout
    tst = run("--command", "aiauto-test", "--shell").stdout
    check("★★测试链路开 tick 后，开发链路的 SKIP_DEV 仍在（旧实现此处被清空）",
          "SKIP_DEV=1" in dev)
    check("★两条链路互不串值：测试链路读不到开发链路的 SKIP_DEV",
          "SKIP_DEV=1" not in tst)

    bl = json.loads((root / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
    tick = bl.get("autopilot", {}).get("tick", {})
    check("baseline 里两个命名空间并存（autopilot.tick.{autopilot,aiauto-test}）",
          isinstance(tick, dict) and {"autopilot", "aiauto-test"} <= set(tick.keys()))

    # ★ 调用点纪律：aiauto-test 侧每一处调用都必须显式带 --command，
    #   否则落回默认的 autopilot 命名空间 —— 那等于把刚分开的两个键又合到一起。
    import re as _re3
    repo = Path(__file__).resolve().parents[3]
    bad = []
    for f in sorted((repo / ".aidp/flows/sprint-aiauto-test").rglob("*.md")):
        for i, ln in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            # 只判**真实调用**（恒以 `python3 …` 起）；散文/注释里提到脚本名不算
            #（收窄前实测误报：phase-0-7 的一条解释 FALLBACK_DEFAULT 的注释）
            if _re3.search(r"python3\s+\S*autopilot_tick_flags\.py", ln) and "--command" not in ln:
                bad.append(f"{f.name}:{i}")
    check("★★aiauto-test 侧所有 tick 调用都显式带 --command（漏一处即落回 autopilot 命名空间）",
          not bad)


# ────────────────────────────────────────────────────────────
# check_flow_bash_syntax.py — flow bash 围栏语法（bash -n + 续行吞注释）
#   ★ 三类真错都要抓；三类正当写法都不许误报。占位符/heredoc/注释块三条收窄
#     全是实测误报的固化，改口径前先跑一遍本组。
# ────────────────────────────────────────────────────────────
def test_flow_bash_syntax():
    print("\n[32] check_flow_bash_syntax 三类真错 + 零误报")
    import subprocess
    script = Path(__file__).resolve().parents[1] / "check_flow_bash_syntax.py"
    repo = Path(__file__).resolve().parents[3]

    def run(files: dict):
        root = Path(tempfile.mkdtemp())
        for rel, body in files.items():
            fp = root / ".aidp/flows/x" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(body, encoding="utf-8")
        cp = subprocess.run([sys.executable, str(script), "--root", str(root), "--json"],
                            capture_output=True, text=True)
        return json.loads(cp.stdout), cp.returncode

    F = "# t\n\n```bash\n%s\n```\n"

    res, rc = run({"a.md": F % 'echo "未闭合'})
    check("A 类：字符串未闭合 → 命中 + 退出码 1", res["errors"] == 1 and rc == 1)

    res, _ = run({"b.md": F % 'case "$V" in\n  a) echo 1 ;;'})
    check("A 类：case 缺 esac → 命中", res["errors"] == 1)

    res, _ = run({"c.md": F % 'git log \\\n  # 说明\n  --oneline'})
    check("★★B 类：续行吞注释 → 命中（语法合法、语义错，bash -n 查不出）",
          res["errors"] == 1 and res["findings"][0]["kind"] == "continuation-comment")

    # ── 零误报三条 ───────────────────────────────────────────
    res, _ = run({"ok1.md": F % 'V="<0.3.4 判定的 TARGET_VERSION>"\necho "$V"'})
    check("★零误报：`<…>` 占位符（bash 会读成重定向，必须中和）", res["errors"] == 0)

    res, _ = run({"ok2.md": F % "X=$(python3 - <<'PY' 2>/dev/null || echo 0\nimport json\nprint(1)\nPY\n)"})
    check("★★零误报：heredoc `<<'PY' 2>/dev/null`（中和正则若不排除它会吃掉定界符）",
          res["errors"] == 0)

    res, _ = run({"ok3.md": F % '# 注释里的示例 cmd \\\n#   --flag\necho ok'})
    check("★零误报：注释块里贴的示例命令（注释行末的 `\\` 不是续行）", res["errors"] == 0)

    res, _ = run({"w.md": "# t\n\n<!-- bashsyntax-check: ignore -->\n```bash\necho \"未闭合\n```\n"})
    check("豁免生效", res["errors"] == 0 and res["waived"] >= 1)

    cp = subprocess.run([sys.executable, str(script), "--root", str(repo), "--json"],
                        capture_output=True, text=True)
    check("★真仓库 flow bash 围栏零语法错", json.loads(cp.stdout)["errors"] == 0)


# ────────────────────────────────────────────────────────────
# check_chain_unattended.py — G-CHAIN-1 棘轮
#   ★ 关键设计是 baseline **按出现次数**记：只记 (文件, 调用文本) 时，同文件内
#     新增的同形调用会被既有条目掩盖（实测加一行后候选 33→34 却全绿）。
# ────────────────────────────────────────────────────────────
def test_chain_unattended():
    print("\n[33] check_chain_unattended G-CHAIN-1 棘轮")
    import subprocess, shutil
    script = Path(__file__).resolve().parents[1] / "check_chain_unattended.py"
    repo = Path(__file__).resolve().parents[3]

    def mk(cmds: dict, files: dict):
        root = Path(tempfile.mkdtemp())
        (root / ".aidp/commands").mkdir(parents=True)
        for n, body in cmds.items():
            (root / ".aidp/commands" / n).write_text(body, encoding="utf-8")
        for rel, body in files.items():
            fp = root / ".aidp" / rel
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(body, encoding="utf-8")
        return root

    def run(root, *extra):
        cp = subprocess.run([sys.executable, str(script), "--root", str(root), "--json", *extra],
                            capture_output=True, text=True)
        return (json.loads(cp.stdout) if cp.stdout.strip().startswith("{") else {}), cp.returncode

    CMDS = {"sprint-close.md": "# close\n支持 `--unattended`\n",
            "sprint-x.md": "# x\n"}          # sprint-x 不认该 flag

    # 首次：无 baseline ⇒ 全部算新增
    root = mk(CMDS, {"commands/caller.md": "调用 `/sprint-close {NNN}` 关闭\n"})
    res, rc = run(root)
    check("无 baseline 时新增候选 → 报错 + 退出码 1", len(res["new"]) == 1 and rc == 1)

    # 冻结后转绿
    subprocess.run([sys.executable, str(script), "--root", str(root), "--update-baseline"],
                   capture_output=True, text=True)
    res, rc = run(root)
    check("冻结进 baseline 后转绿", not res["new"] and rc == 0)

    # ★★ 同文件再加一处同形调用 → 必须报（旧的按 (文件,文本) 去重会漏）
    f = root / ".aidp/commands/caller.md"
    f.write_text(f.read_text(encoding="utf-8") + "又一处：调用 `/sprint-close {NNN}` 关闭\n",
                 encoding="utf-8")
    res, rc = run(root)
    check("★★同文件新增同形调用 → 仍报（baseline 按出现次数记）",
          len(res["new"]) == 1 and rc == 1)

    # 带了 flag 的新增不算
    f.write_text("调用 `/sprint-close {NNN}` 关闭\n新增但带了：`/sprint-close {NNN} --unattended`\n",
                 encoding="utf-8")
    res, _ = run(root)
    check("零误报：新增调用已带 flag → 不报", not res["new"])

    # 不认该 flag 的下游不纳入
    f.write_text("调用 `/sprint-close {NNN}` 关闭\n调用 `/sprint-x {NNN}` 干活\n", encoding="utf-8")
    res, _ = run(root)
    check("★零误报：下游命令未声明 --unattended → 不纳入判定", not res["new"])

    # 自指用法示例不纳入
    root2 = mk(CMDS, {"commands/sprint-close.md": "用法：`/sprint-close {NNN}` 关闭本 Sprint\n"})
    res, _ = run(root2)
    check("★零误报：文件调用自己（用法示例）→ 不纳入", not res["new"])

    # baseline 条目补了 flag → 提示可收紧
    root3 = mk(CMDS, {"commands/c.md": "调用 `/sprint-close {NNN}` 关闭\n"})
    subprocess.run([sys.executable, str(script), "--root", str(root3), "--update-baseline"],
                   capture_output=True, text=True)
    (root3 / ".aidp/commands/c.md").write_text(
        "调用 `/sprint-close {NNN} --unattended` 关闭\n", encoding="utf-8")
    res, rc = run(root3)
    check("baseline 条目已补 flag → 记为 resolved（棘轮只紧不松）",
          rc == 0 and len(res["resolved"]) == 1)

    # 真仓库零新增
    res, rc = run(repo)
    check("★真仓库无新增未透传站点", not res["new"] and rc == 0)


# ────────────────────────────────────────────────────────────
# 跨版本增量基建：code_inventory / requirement_ledger / archive_old_artifacts
#   动机：`/version` 里唯一真正随累积增长的是 sprint-design Step 0.6.4.7「全扫 code/（不增量）」；
#   而约定 34 的历史需求清算为控成本只读 {prev_version}，等于把漏检固化。三个脚本分别解决
#   「重复全扫」「历史查不全」「产物目录只增不减」，下面按行为断言、不看文档写没写。
# ────────────────────────────────────────────────────────────
def _run(script, *args, cwd=None):
    import subprocess
    path = os.path.join(os.path.dirname(HERE), script)
    cp = subprocess.run([sys.executable, path, *args], capture_output=True, text=True, cwd=cwd)
    return cp


def _jout(cp):
    """取脚本 stdout 里的 JSON。⛔ 解析不了返回 {} —— 调用方务必断言具体键，别只判真假。

    先整体解析、再回落「最后一行」：取最后一行是为了容忍 JSON 前面的诊断输出，
    但它会把 **pretty-printed（多行）JSON** 的最后一行读成 `}` → 解析失败 → 静默 {}，
    于是「脚本输出了没法解析的东西」与「脚本返回空结果」在测试里完全同形（实测踩过）。
    """
    raw = cp.stdout.strip()
    for cand in (raw, raw.splitlines()[-1] if raw else ""):
        try:
            return json.loads(cand)
        except ValueError:
            continue
    return {}


def test_code_inventory():
    print("\n[35] code_inventory 跨版本增量缓存")
    root = Path(tempfile.mkdtemp())
    be = root / "code/backend/svc/src/main/java/com/x"
    fe = root / "code/frontend/web/src/pages"
    be.mkdir(parents=True)
    (fe / "console/agent-mgmt/components").mkdir(parents=True)
    (be / "UserController.java").write_text(
        '@RequestMapping("/api/user")\nclass C {\n  @GetMapping("/list")\n  void a(){}\n'
        '  @PostMapping("/save")\n  void b(){}\n}\n', encoding="utf-8")
    (root / "docs/deployment/V0.1/sql/增量").mkdir(parents=True)
    (root / "docs/deployment/V0.1/sql/增量/01_init.sql").write_text(
        "CREATE TABLE IF NOT EXISTS `t_user` (id int);\nCREATE TABLE t_org (id int);\n",
        encoding="utf-8")
    (fe / "console/index.vue").write_text("<h1>控制台</h1>", encoding="utf-8")
    (fe / "console/agent-mgmt/index.vue").write_text("<h1>智能体</h1>", encoding="utf-8")
    (fe / "console/agent-mgmt/components/Dlg.vue").write_text("<h1>弹窗</h1>", encoding="utf-8")
    (fe / "[...notFound].vue").write_text("<h1>404</h1>", encoding="utf-8")

    r = _jout(_run("code_inventory.py", "update", "--root", str(root), "--json"))
    c = r.get("counts", {})
    check("首扫：抽到 3 个 API（含类级 @RequestMapping 前缀拼接）", c.get("api") == 3)
    check("首扫：SQL CREATE TABLE 两张表", c.get("table") == 2)
    check("★ 文件式路由按 pages/ 目录派生（不写在 router.ts 里也能抽到）", c.get("route") == 3)
    check("★ pages/**/components/ 下的子组件不算页面、也不派生路由", c.get("page") == 3)
    inv = json.loads((root / "memory/_facts/code-inventory.json").read_text(encoding="utf-8"))
    paths = {e["path"] for m in inv["files"].values() for e in m["entities"] if e["kind"] == "api"}
    check("类级前缀 + 方法级路径拼接正确", "/api/user/list" in paths and "/api/user/save" in paths)
    routes = {e["path"] for m in inv["files"].values() for e in m["entities"] if e["kind"] == "route"}
    check("index.vue → 父路径；[...x] → 通配", "/console" in routes and "/*" in routes)

    r2 = _jout(_run("code_inventory.py", "update", "--root", str(root), "--json"))
    check("★ 第二次跑：内容没变 → 零解析、全部复用", r2["delta"]["scanned"] == 0
          and r2["delta"]["reused"] == r["delta"]["total_files"])

    _run("code_inventory.py", "snapshot", "--version", "V0.1", "--root", str(root))
    (be / "OrderController.java").write_text('@GetMapping("/api/order")\nvoid o(){}\n', encoding="utf-8")
    r3 = _jout(_run("code_inventory.py", "update", "--root", str(root), "--json"))
    check("★ 只改一个文件 → 只解析这一个（其余复用）", r3["delta"]["scanned"] == 1)
    d = _jout(_run("code_inventory.py", "delta", "--since", "V0.1", "--root", str(root), "--json"))
    check("★ delta 相对上版快照给出新增实体", d.get("added") == ["api GET /api/order"])
    check("delta 未变动实体不重复报", d.get("removed") == [] and d.get("unchanged", 0) > 0)

    cp = _run("code_inventory.py", "delta", "--since", "V9.9", "--root", str(root))
    check("无该版本快照 → exit 1 且提示可用快照（不静默给空 Δ）", cp.returncode == 1)
    md = _run("code_inventory.py", "render", "--root", str(root)).stdout
    check("render 出「代码现状清单」段且含各维度小节",
          "## 代码现状清单" in md and "### 后端 API 端点" in md and "### 数据库表" in md)


def test_requirement_query():
    """[36] 历史需求**读时查询**（纯读不落盘）。

    取代了 `requirement_ledger.py` 的落盘台账。被删掉的是 `supersessions` —— 它是
    表 F 的**第三份副本且信息最少**（丢了 original_conclusion 与 source），且靠手工
    `supersede` 登记、无自动调用方 ⇒ 审计「先查索引」会查到一份**过期索引而它不报错**。
    ⛔ 但**检索能力必须留下**：「本版反转的口径历史上哪些版本提过」要搜 REQ 正文，
    从 `98_*.json` 聚合不出来。
    """
    print("\n[36] requirement_query 历史需求读时查询")
    root = Path(tempfile.mkdtemp())

    def mkreq(v, files):
        d = root / "docs/requirements" / v / "研发需求"
        d.mkdir(parents=True)
        for n, body in files.items():
            (d / n).write_text(body, encoding="utf-8")

    # 四种真实编号写法 + 一种旧扁平布局，全部要能抽到
    mkreq("V0.1", {"00_索引.md": "## 功规点索引\n\n| 编号 | 标题 | 归属 | 端 |\n|---|---|---|---|\n"
                                 "| REQ-001 | 用量统计口径 | N-1 | 后端 |\n"
                                 "| REQ-002 | 导出全量 | N-2 | 前端 |\n"})
    mkreq("V0.2", {"01_研发需求.md": "### REQ-3：消息中心对接\n正文一句话。\n"})
    mkreq("V0.3", {"01_研发需求.md": "### REQ-V0.3-A02 员工列表主管理员标记\n说明文本。\n"
                                     "## 三、角色与权限矩阵（REQ-V0.3-A01）\n矩阵说明。\n"})
    # ★ 真实反例：正文里 `| F1 | A | 字段名 | …` 是**字段清单表的字段编号**，不是功规点。
    #    编号模式若放宽到 F\d+ 就会把几十个字段误抽成需求条目（V0.12.1 实测形态）。
    mkreq("V0.4", {"01_研发需求.md": "### REQ-020：智能体列表改版\n正文。\n\n"
                                     "| 编号 | 分组 | 字段 | 位置 |\n|---|---|---|---|\n"
                                     "| F1 | A | 智能体标识 | 列表行 |\n"
                                     "| F2 | A | 规格明细集合 | 列表行 |\n"})
    (root / "docs/requirements/V0.5").mkdir(parents=True)
    (root / "docs/requirements/V0.5/研发需求.md").write_text(
        "### REQ-010：旧扁平布局条目\n正文。\n", encoding="utf-8")
    (root / "docs/requirements/V0.6").mkdir(parents=True)   # 无产物 → 检索不到但不得当"该版无需求"

    # ① search：编号写法兼容（这套逻辑是从旧脚本原样保留的，回归它没退化）
    h = _jout(_run("requirement_query.py", "search", "口径", "对接", "标记", "改版", "布局",
                   "--root", str(root), "--json"))["hits"]
    vs = {x["version"] for x in h}
    check("★ REQ-001 型（索引表）可搜到", any(x["id"] == "REQ-001" for x in h))
    check("★ REQ-3 型（短编号正文标题）", any(x["id"] == "REQ-3" for x in h))
    check("★ REQ-V0.3-A02 型 + 编号内嵌标题括号", any(x["id"] == "REQ-V0.3-A02" for x in h))
    check("★ 字段清单表的 F1/F2 不被误抽成功规点",
          not any(x["id"] in ("F1", "F2") for x in h))
    check("★ 旧扁平布局 研发需求.md 也能抽", any(x["id"] == "REQ-010" for x in h))
    check("★ 检索跨越全部历史版本，而非只看上一版", {"V0.1", "V0.2"} <= vs)
    check("命中项带原文锚点（供只读那几条）", all(x["anchor"] for x in h))

    h2 = _jout(_run("requirement_query.py", "search", "口径", "对接", "--before", "V0.5",
                    "--root", str(root), "--json"))["hits"]
    check("--before 排除自身及更新的版本", all(x["version"] < "V0.5" for x in h2))

    # ② supersessions：聚合 98_*.json 的 table_f，且带 ledger 丢掉的两个字段
    (root / "docs/requirements/V0.3/研发需求/98_语义变更与需求作废.json").write_text(
        json.dumps({"table_e": [], "table_f": [
            {"history_version": "V0.1", "req_id": {"raw": "REQ-001"},
             "original_conclusion": "仅统计企业级", "disposition": "作废",
             "reason": "本版改为企业+个人",
             "source": {"file": "01_研发需求.md", "line": 12}}],
            "gate": {"failed": False, "exit_code": 0}}, ensure_ascii=False), encoding="utf-8")
    g = _jout(_run("requirement_query.py", "supersessions", "--root", str(root), "--json"))
    sup = g["supersessions"]
    check("★ 聚合到跨版本作废判定", len(sup) == 1 and sup[0]["by_version"] == "V0.3")
    check("★ 带 original_conclusion（旧台账丢了这个字段）",
          sup[0].get("original_conclusion") == "仅统计企业级")
    check("★ 带 source 可回跳原文（旧台账也没有）", sup[0].get("source", {}).get("line") == 12)
    check("★ 缺副本的版本被点名（「该版无作废」与「副本没产出」不得同形）",
          {"V0.1", "V0.2"} <= {m["version"] for m in g["missing_copies"]})

    # ③ 纯读：跑完不得产生任何文件
    snap = sorted(str(x) for x in root.rglob("*") if x.is_file())
    _run("requirement_query.py", "search", "口径", "--root", str(root))
    _run("requirement_query.py", "supersessions", "--root", str(root))
    check("★ 纯读不落盘：两个子命令跑完文件集合不变（⛔ 不再产生 memory/_facts/ 台账）",
          sorted(str(x) for x in root.rglob("*") if x.is_file()) == snap)
    check("★ 不创建 memory/ 目录", not (root / "memory").exists())

    # ④ 旧脚本确已删除——否则"删了"与"没删"在仓库里同形
    repo = Path(__file__).resolve().parents[3]
    check("★ requirement_ledger.py 已删除", not (repo / ".aidp/scripts/requirement_ledger.py").exists())
    va = (repo / ".aidp/agents/version-auditor.md").read_text(encoding="utf-8")
    check("★ 审计 H 改用读时查询、不再登记第三份副本",
          "requirement_query.py" in va and "requirement_ledger" not in va)


def test_archive_old_artifacts():
    print("\n[37] archive_old_artifacts 老版本留仓归档")
    import subprocess
    root = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    area = root / "docs/reports"
    for i in range(1, 9):
        d = area / f"V0.{i}"
        d.mkdir(parents=True)
        (d / "README.md").write_text("同样的说明\n", encoding="utf-8")      # 跨版本重复
        (d / f"r-{i}.html").write_text(f"独有 {i}\n", encoding="utf-8")
    (area / "V0.1/sub").mkdir()
    (area / "V0.1/sub/a.txt").write_text("A", encoding="utf-8")
    (area / "V0.1/sub/b.txt").write_text("A", encoding="utf-8")             # 同版本内重复
    subprocess.run(["git", "-C", str(root), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "-qm", "i"], capture_output=True)

    A = ("--root", str(root), "--area", "docs/reports")
    cp = _run("archive_old_artifacts.py", "plan", "--keep", "3", *A)
    check("plan 默认只读、不产生任何文件", not (area / "_archive").exists())
    check("豁免最近 3 个版本", "豁免（最近 3 个）：V0.6、V0.7、V0.8" in cp.stdout)

    cp = _run("archive_old_artifacts.py", "apply", "--keep", "3", *A)
    check("★ apply 不带 --apply → 仍是 dry-run，什么都不删",
          not (area / "_archive").exists() and (area / "V0.1").is_dir())

    _run("archive_old_artifacts.py", "apply", "--apply", "--keep", "3", *A)
    left = sorted(p.name for p in area.iterdir())
    check("老版本目录已归档、近 3 版原样保留", left == ["V0.6", "V0.7", "V0.8", "_archive"])
    import zipfile
    names = set(zipfile.ZipFile(area / "_archive/V0.1.zip").namelist())
    check("★ 跨版本重复的 README.md 已去重（不进包）", "V0.1/README.md" not in names)
    check("★ 同版本内字节相同但文件名不同 → 两份都保留（分辨率截图那类事实）",
          {"V0.1/sub/a.txt", "V0.1/sub/b.txt"} <= names)
    note = (area / "_archive/00_归档说明.md").read_text(encoding="utf-8")
    check("归档说明记录了去重明细（删了哪份、同哪份）", "跨版本去重明细" in note and "V0.1/README.md" in note)

    _run("archive_old_artifacts.py", "restore", "--version", "V0.1", "--apply", *A)
    check("★ restore 往返：独有文件与被去重的文件都回来了",
          (area / "V0.1/r-1.html").is_file() and (area / "V0.1/README.md").is_file()
          and (area / "V0.1/sub/b.txt").is_file())
    check("restore 的 README 内容与原件一致",
          (area / "V0.1/README.md").read_text(encoding="utf-8").strip() == "同样的说明")

    # V0.6 此前被 keep=3 豁免、仍在盘上；改脏它并把 keep 收到 2 让它落入归档范围
    (area / "V0.6/r-6.html").write_text("dirty", encoding="utf-8")
    cp = _run("archive_old_artifacts.py", "apply", "--apply", "--keep", "2", *A)
    check("★ 归档范围内有未提交改动 → 拒绝执行（不给「改了一半被打包」的机会）",
          cp.returncode == 1 and "拒绝归档" in cp.stderr and (area / "V0.6").is_dir())
    cp = _run("archive_old_artifacts.py", "plan", "--keep", "0", *A)
    check("--keep 0 被拒（绝不允许把所有版本都归档）", cp.returncode == 2)


# ────────────────────────────────────────────────────────────
# handback-check：中途交还控制权的结构级机器门
#   事故：/sprint-autopilot 在规划段跑完后输出「要我继续进入开发阶段吗？」并交还控制权，
#   本轮 HAS_WAKE_SOURCE=0（未挂 /loop），没有下一 tick 会来接 → Phase 3.2~3.4 全部停摆。
#   规则侧四处禁令俱在，缺的是机器门：「产物齐全」缺了 exit 1 拦得住，「中途停」只有文档谴责。
#   ★ 判定式而非枚举话术——真实失效用的是征询式变体，措辞不同实质一样。
# ────────────────────────────────────────────────────────────
def test_handback_check():
    print("\n[38] handback-check 中途交还控制权机器门")
    gate = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")
    root = Path(tempfile.mkdtemp())
    (root / "memory").mkdir()

    def run(baseline, *extra):
        (root / "memory/.sprint-autopilot-baseline.json").write_text(
            json.dumps(baseline), encoding="utf-8")
        import subprocess
        cp = subprocess.run([sys.executable, gate, "handback-check", "--version", "V0.1",
                             "--repo-root", str(root), "--json", *extra],
                            capture_output=True, text=True)
        try:
            return json.loads(cp.stdout.strip().splitlines()[-1]), cp.returncode
        except (ValueError, IndexError):
            return {}, cp.returncode

    def bl(ws, np_, ns=""):
        return {"autopilot": {"wake_source_this_tick": ws},
                "versions": {"V0.1": {"run_state": {"next_phase": np_, "next_sprint": ns}}}}

    d, rc = run(bl(0, "3.2-dev"))
    check("★ 事故复现：无唤醒源 + 停在 3.2-dev → VIOLATION exit 1",
          rc == 1 and d["verdict"] == "VIOLATION" and d["unfinished"] == ["3.2-dev"])

    d, rc = run(bl(1, "3.2-dev", "016"))
    check("挂了 /loop（有下一 tick）→ 合法 yield，PASS", rc == 0 and d["verdict"] == "PASS")

    d, rc = run(bl(0, "done", "done"))
    check("正常跑到终态 → PASS", rc == 0 and d["verdict"] == "PASS")

    # ★ 这一条是旧断言的盲区：命令正文原本只判 next_sprint != done
    d, rc = run(bl(0, "3.3-audit", "done"))
    check("★ 旧断言盲区：next_sprint=done 但 next_phase 未完 → 仍判 VIOLATION",
          rc == 1 and d["unfinished"] == ["3.3-audit"])
    d, rc = run(bl(0, "done", "016"))
    check("★ 反向：next_phase=done 但还有 Sprint 未关 → 也判 VIOLATION",
          rc == 1 and d["unfinished"] == ["016"])

    d, rc = run({"autopilot": {"wake_source_this_tick": 0}, "versions": {"V0.1": {}}})
    check("★ 从未进流水线（Phase 1 无变化干净退出）→ 不误判为丢活儿", rc == 0)
    d, rc = run(bl(0, "", ""))
    check("run_state 存在但两个游标都空 → 同样不误判", rc == 0)

    d, rc = run(bl(None, "3.2-dev"))
    check("★ wake_source 读不到 → 保守按 0（宁可多报一次，不放过丢活儿）", rc == 1)
    d, rc = run(bl(0, "3.2-dev"), "--wake-source", "1")
    check("--wake-source 可覆盖 baseline", rc == 0)

    # --record 落痕，供下一轮 Phase 0.0.0bis 开局识别
    import subprocess
    shutil_src = os.path.join(os.path.dirname(HERE), "baseline_edit.py")
    (root / ".aidp/scripts").mkdir(parents=True, exist_ok=True)
    import shutil as _sh
    _sh.copy(shutil_src, root / ".aidp/scripts/baseline_edit.py")
    run(bl(0, "3.2-dev"), "--record")
    saved = json.loads((root / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
    check("★ --record 把判定写回 autopilot.last_handback（下一轮开局可读）",
          (saved.get("autopilot") or {}).get("last_handback", {}).get("verdict") == "VIOLATION")

    # 规则侧：判据必须是判定式（看状态），不是枚举话术
    repo = Path(__file__).resolve().parents[3]
    cmd = (repo / ".aidp/commands/sprint-autopilot.md").read_text(encoding="utf-8")
    inv = (repo / ".aidp/flows/sprint-autopilot/invariants.md").read_text(encoding="utf-8")
    check("★ 命令正文的反向硬断言已接机器门", "handback-check" in cmd)
    check("★ IRON-1 已接机器门（不再只有文档谴责）", "handback-check" in inv)
    check("★ 反向硬断言同时判 next_phase 与 next_sprint（补旧盲区）",
          "next_phase" in cmd.split("反向硬断言")[1][:1500])
    check("★ 明确判据不看话术（征询式变体同样被拦）",
          "不看" in cmd and "征询式" in cmd)


# ────────────────────────────────────────────────────────────
# 收尾门 3m 缺陷复验闭环 + WebMCP 入口探测兜底（实际项目中两条实测反馈）
# ────────────────────────────────────────────────────────────
def _load_gate():
    import importlib.util
    path = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")
    spec = importlib.util.spec_from_file_location("cgate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_defect_retest_closure():
    print("\n[39] 收尾门 3m 缺陷复验闭环")
    G = _load_gate()
    R = G.PENDING_RETEST_RE
    # ★ 真实写法：「待」与「复验」之间夹着 build 号——连写模式恰好匹配不到（实测两条只捞出一条）
    check("★ 真实写法「已修复，⚠️ 待 build1002 复验」被识别",
          bool(R.search("已修复，⚠️ 待 build1002 复验")))
    check("连写「待复验」被识别", bool(R.search("待复验")))
    check("「待下一轮回归验证」被识别", bool(R.search("已修复，待下一轮回归验证")))
    check("「未复测」被识别", bool(R.search("未复测")))
    check("英文 pending retest 被识别", bool(R.search("pending retest")))
    check("★ 零误报：「已修复并复验通过」不算待复验", not R.search("已修复并复验通过"))
    check("★ 零误报：「复验通过，无遗留」不算待复验", not R.search("复验通过，无遗留"))
    check("★ 零误报：跨句读不串味（待产品确认文案。已复验通过）",
          not R.search("待产品确认文案。已复验通过"))

    check("build 序号解析：V0.1_build1002 → 1002", G._build_seq("V0.1_build1002") == 1002)
    check("build 序号解析：取不到返回 -1", G._build_seq("") == -1)

    # 端到端：造报告 + baseline，走真实 check 的 3m 分支
    import subprocess
    gate = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")

    def scene(defects, builds, needs_human=False):
        root = Path(tempfile.mkdtemp())
        d = root / "docs/reports/V0.1/AI执行报告/data"
        d.mkdir(parents=True)
        (d / "V0.1_build1001.js").write_text(
            "window.__A__=window.__A__||[];window.__A__.push("
            + json.dumps({"defects": defects}, ensure_ascii=False) + ");", encoding="utf-8")
        (root / "memory").mkdir()
        v = {"builds": builds}
        if needs_human:
            v["needs_human"] = True
        (root / "memory/.sprint-autopilot-baseline.json").write_text(
            json.dumps({"versions": {"V0.1": v}}), encoding="utf-8")
        cp = subprocess.run([sys.executable, gate, "check", "--version", "V0.1",
                             "--build", "V0.1_build1001", "--stage", "final",
                             "--repo-root", str(root), "--notify", "0"],
                            capture_output=True, text=True)
        return cp.stdout

    PEND = [{"id": "D-1", "status": "已修复，⚠️ 待 build1002 复验"},
            {"id": "D-2", "fix": "已修复", "note": "待复验"}]
    out = scene(PEND, [{"build": "V0.1_build1001"}])
    check("★ 事故复现：两条待复验 + 无后继 build → 3m FAIL",
          "❌ 缺陷复验闭环" in out)
    check("★ 两条都被点名（不是只捞出一条）", "D-1" in out and "D-2" in out)
    check("失败提示点明「仪式不是选项」", "自动仪式" in out or "不是选项" in out)

    out = scene(PEND, [{"build": "V0.1_build1001"},
                       {"build": "V0.1_build1002", "retest_of": "V0.1_build1001"}])
    check("★ 已铸后继 build 承接复测 → 3m PASS", "✅ 缺陷复验闭环" in out)

    out = scene(PEND, [{"build": "V0.1_build1001"}], needs_human=True)
    check("★ 冻结转人工 = 合法出口 → DEGRADE 不 FAIL", "🟡 缺陷复验闭环" in out)

    out = scene([{"id": "D-1", "status": "已修复并复验通过"}], [{"build": "V0.1_build1001"}])
    check("无待复验缺陷 → PASS", "✅ 缺陷复验闭环" in out)

    # 规则侧：IRON-10 单一信源 + 收尾分片承载
    repo = Path(__file__).resolve().parents[3]
    inv = (repo / ".aidp/flows/sprint-autopilot/invariants.md").read_text(encoding="utf-8")
    cmd = (repo / ".aidp/commands/sprint-autopilot.md").read_text(encoding="utf-8")
    p38 = (repo / ".aidp/flows/sprint-autopilot/phase-3-8.md").read_text(encoding="utf-8")
    check("★ IRON-10 已建小节（原 P0-4 从命令正文提升为不变式单一信源）",
          "## IRON-10" in inv)
    check("IRON 清单已同步到 10 条", "IRON-1 ~ IRON-10" in cmd and "10 条顶层铁律" in cmd)
    check("★ 收尾分片承载 IRON-10（此前只写在命令正文、子 Agent 读不到）",
          "IRON-10" in p38)


def test_webmcp_probe_fallback():
    print("\n[40] WebMCP 入口探测：白名单优先 + 全局扫描兜底")
    import subprocess
    script = os.path.join(os.path.dirname(HERE), "check_webmcp.py")
    src = Path(script).read_text(encoding="utf-8")
    check("★ 兜底清单已含实测入口 window.ModelContext（大写 M）",
          '"window.ModelContext"' in src)
    cp = subprocess.run([sys.executable, script, "--probe-snippet"],
                        capture_output=True, text=True)
    check("--probe-snippet 输出探测片段", cp.returncode == 0 and "suspects" in cp.stdout)
    snippet = cp.stdout.strip()
    check("★ 兜底扫描覆盖 window / navigator / Navigator.prototype",
          "Navigator.prototype" in snippet and "getOwnPropertyNames" in snippet)

    # 用 node vm 造一个"白名单全落空、能力其实叫 ModelContext"的页面，验证兜底能捞出来
    if shutil.which("node"):
        drv = ("const s=require('fs').readFileSync(process.argv[1],'utf8');const vm=require('vm');"
               "const nav=Object.create({});const win={isSecureContext:true,"
               "ModelContext:function(){},Object:Object};win.window=win;win.navigator=nav;"
               "const r=vm.runInContext('('+s+')',vm.createContext(win));"
               "console.log(JSON.stringify(r));")
        f = Path(tempfile.mkdtemp()) / "p.js"
        f.write_text(snippet, encoding="utf-8")
        rr = subprocess.run(["node", "-e", drv, str(f)], capture_output=True, text=True)
        try:
            res = json.loads(rr.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            res = {}
        check("★ 探测片段是合法 JS 且可执行", bool(res))
        wl = res.get("whitelist") or {}
        check("★ 旧三个入口全 undefined（复现下游误判前提）",
              all(wl.get(k) == "undefined" for k in
                  ("navigator.modelContext", "modelContext", "window.agent")))
        check("★ 大写入口被白名单命中", wl.get("window.ModelContext") == "function")
        names = {x["name"] for x in (res.get("suspects") or [])}
        check("★ 全局扫描兜底也独立捞到 ModelContext（改名也能发现）", "ModelContext" in names)

    tpl = (Path(__file__).resolve().parents[3]
           / ".aidp/templates/optional-rules/webmcp.md").read_text(encoding="utf-8")
    check("★ 判据表补第三态（接口类已暴露但实例未挂载）",
          "Illegal constructor" in tpl and "第三态" in tpl)
    check("★ 补 user-data-dir 单例导致参数静默失效的坑",
          "静默丢弃" in tpl and "/proc/" in tpl)
    check("★ 明确 suspects 非空不得静默判不可用", "不得静默判" in tpl)


# ────────────────────────────────────────────────────────────
# entry_mode 粒度：build 级 > 版本级（实际项目中第二次实测）
#   autopilot_entry_mode 是版本级槽位，而 entry_mode 实际是 build 级属性——同版本
#   首轮 full、复验轮 test-only 共用一个槽位、后写覆盖先写，于是 Stop hook 拿版本值
#   校另一个 build，卡集算错、索要那轮压根没发生的两张里程碑卡。
#   ★ 这是同一失败形态的第二形态：上次修的是"回退链缺一环"，这次是"回退到了粒度不对的槽位"。
# ────────────────────────────────────────────────────────────
def test_entry_mode_build_scoped():
    print("\n[41] entry_mode build 级优先（版本级槽位互相覆盖的回归）")
    G = _load_gate()

    class A:
        entry_mode = None
        no_planning = None
        will_browser_test = 1
        notify = 1

    a = A()
    vnode = {
        "autopilot_entry_mode": "test-only",          # 复验轮写的，覆盖了首轮的 full
        "builds": [
            {"build": "V1_build1001", "entry_mode": "full"},
            {"build": "V1_build1002", "entry_mode": "test-only", "retest_of": "V1_build1001"},
        ],
    }
    check("★ 事故复现：版本槽位=test-only，但 build1001 自己记着 full → 取 full",
          G._resolve_entry_mode(a, vnode, "V1_build1001") == "full")
    check("复验轮 build1002 取 test-only",
          G._resolve_entry_mode(a, vnode, "V1_build1002") == "test-only")
    check("★ 不传 build（老调用点）→ 回退版本级，向后兼容",
          G._resolve_entry_mode(a, vnode) == "test-only")
    check("老 baseline：build 条目无 entry_mode → 回退版本级",
          G._resolve_entry_mode(a, {"autopilot_entry_mode": "full",
                                    "builds": [{"build": "B1"}]}, "B1") == "full")
    check("两级都无 → 默认 full", G._resolve_entry_mode(a, {}, "B1") == "full")
    a2 = A(); a2.entry_mode = "incremental"
    check("显式 --entry-mode 优先级最高",
          G._resolve_entry_mode(a2, vnode, "V1_build1001") == "incremental")

    # 卡集必须跟着 build 走：full 轮该有开发链路卡，test-only 轮不该有
    cards_full = set(G._derive_expect_cards(a, vnode, "V1_build1001"))
    cards_test = set(G._derive_expect_cards(a, vnode, "V1_build1002"))
    check("★ full 轮卡集含开发链路卡（#1c/#1d/#2 任一）",
          bool(cards_full & {"#1c", "#1d", "#2"}))
    check("★ test-only 轮卡集不含开发链路卡（这正是被误索要的那几张）",
          not (cards_test & {"#1c", "#1d", "#2"}))
    check("★ 同一版本两个 build 的应发卡集确实不同（版本级取值时必然相同 = 漏判）",
          cards_full != cards_test)

    # Stop hook：build 级优先
    repo = Path(__file__).resolve().parents[3]
    hook = (repo / ".aidp/hooks/autopilot-stop-guard.py").read_text(encoding="utf-8")
    check("★ Stop hook 取 entry_mode 时 build 级在前、版本级仅作回退",
          'b.get("entry_mode") or vobj.get("autopilot_entry_mode")' in hook)

    # 写入侧：3.1.5 铸造时落 build 级；复用时只补不覆盖
    p34 = (repo / ".aidp/flows/sprint-autopilot/phase-3-4.md").read_text(encoding="utf-8")
    check("★ 铸新 build 时把当轮 ENTRY_MODE 落进 builds[].entry_mode",
          'entry["entry_mode"] = os.environ["ENTRY_MODE"]' in p34)
    check("★ 复用既有 build 时只补不覆盖（-z 判空才写）",
          "get entry_mode --default" in p34 and "set entry_mode" in p34)


def test_dev_scale_and_reversal_gate():
    print("\n[52] 口述档位门有生产方 + 口径反转清算门")
    repo = Path(__file__).resolve().parents[3]
    dev = (repo / ".aidp/commands/sprint-dev.md").read_text(encoding="utf-8")
    pw1 = (repo / ".aidp/flows/sprint-dev/postdev-writeback-1.md").read_text(encoding="utf-8")
    aidp = (repo / ".aidp/AIDP-AGENTS.md").read_text(encoding="utf-8")
    ledger = (repo / ".aidp/reference/开发期族增量.md").read_text(encoding="utf-8")

    # ★ 组合性缺陷原型：Phase 0B.1.1 三处消费 `--scale={档位}`，却没有任何一步生产它。
    #   每一处单看都自洽，合起来是"读一个没人写过的变量"——SKILL 静默回退 L 档全套，
    #   "小改动不走大流程"整条失效且无任何报错。故断言【消费方存在 ⇒ 生产方必须存在】。
    consumers = dev.count("--scale={档位}")
    check("Phase 0B.1.1 确有 `--scale={档位}` 的消费点", consumers >= 3)
    check("★ `{档位}` 有生产方：步骤 2.5 口述规模档位判定门",
          "2.5. **★ 口述规模档位判定门（`sup_scale`）" in dev)
    check("★ 生产方排在第一个消费方之前（否则传的是未定义值）",
          dev.index("口述规模档位判定门") < dev.index("--scale={档位}"))
    check("★ 档位落盘留痕 sup_scale", "sprints.{新NNN}.sup_scale" in dev)

    # ★ 语义变更不再布尔化一刀切抬档（下游实证：6 文件零建表 → 762 行四层文档）
    for name, body in (("命令端 0B.1.1", dev), ("Step X.0.0 步骤 3.5", pw1)):
        check(f"{name}：存在 S 语义子档", "S（语义子档）" in body)
        check(f"{name}：语义子档强制「受影响结论清单」", "受影响结论清单" in body)
    check("★ 两处语义子档判据一致（均要求 !HAS_API / !HAS_DDL / !HAS_CONFIG）",
          all(k in pw1 for k in ("HAS_SEMANTIC", "!HAS_API", "!HAS_DDL", "!HAS_CONFIG")))
    # 降档不降级联：清单必须在"档位不影响的东西"清单里
    idx = pw1.find("档位不影响的东西")
    check("★「受影响结论清单」列入档位不可裁剪项",
          idx > 0 and "受影响结论清单" in pw1[idx:idx + 400])
    # S 档就地追加不能变成"可以不留痕"
    check("★ S 档硬门放宽但保留下限（两者都没有 = Fail）",
          "S 档「就地追加」同样算 Pass" in dev and "两者都没有\"永远是 Fail" in dev)

    # ★ 同版本口径反转清算（约定 34 ⑥）：跨版本机制此时无"历史版本"可检索，完全是盲区
    check("★ 存在 Phase 0B.1.3 口述追加/反转决策门", "Phase 0B.1.3" in dev)
    check("★ 先判「追加 vs 反转」再动手", "先判「追加」还是「反转」" in dev)
    check("★ 反转必须逐条清算、⛔ 不许用重跑 0B.1.1 代替",
          "重跑 Phase 0B.1.1 不是本步的替代品" in dev)
    check("★ 强制回答「旧口径下安全的设计在新口径下是否仍安全」",
          "在新口径下是否仍然安全" in dev)
    check("★ 该问题明示静态检查发现不了（唯一防线是强制提问）",
          "不会被任何静态检查发现" in dev)
    check("★ 作废用显式标记、不静默改写", "显式作废标记" in dev)
    check("★ 约定 34 主行已覆盖同版本反转", "同一版本 / 同一 Sprint 内" in aidp)

    # ★ 台账边界：口述新需求是"开发的输入"，不能攒到明天
    check("★ 增量册有边界表（什么走 / 什么不走）", "什么走增量册、什么不走" in ledger)
    check("★ 明示口述累进不入增量册（否则今天在无规格下开发）",
          "不走增量册" in ledger and "开发的输入" in ledger)


def test_design_goals_ratchet():
    print("\n[53] 设计目标棘轮 + 实现名词体检")
    repo = Path(__file__).resolve().parents[3]
    script = repo / ".aidp/scripts/check_design_goals.py"

    def run(root, *a):
        r = subprocess.run([sys.executable, str(script), "--root", str(root), *a],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    # 真仓：应恒绿（本体已定基）
    rc, out = run(repo)
    check("★ 本仓设计目标闸门通过", rc == 0 and "指纹与 baseline 一致" in out)

    doc = (repo / "设计目标.md").read_text(encoding="utf-8")
    # ★ 目标必须只写「最终要达成什么」：违约信号/边界例外一进来，目标就跟着命令漂
    check("★ 目标正文不再承载违约信号列",
          "违约信号" not in doc.split("## 三、")[1])
    check("★ 明写「轻易不得更改」纪律", "轻易不得更改" in doc or "轻易不能更改" in doc)
    check("★ 明写退役编号不复用（老报告里的编号永远指同一件事）",
          "不再复用" in doc and "不连续" in doc)

    root = Path(tempfile.mkdtemp())
    (root / ".aidp/scripts").mkdir(parents=True)

    # 下游无该文件 → 跳过、退出码 0（模板专属、不下发）
    rc, out = run(root)
    check("★ 无 设计目标.md 时跳过且 rc=0", rc == 0 and "跳过" in out)

    body = ("# t\n\n## 三、命令设计目标\n\n### G-A · `/a`\n\n"
            "- **G-A-1** — 一次下达就把整件事做完。\n"
            "- **G-A-2** — 停得下来但必须停得响。\n")
    (root / "设计目标.md").write_text(body, encoding="utf-8")

    # 未定基 → ERROR（不能默认放行，否则棘轮等于不存在）
    rc, out = run(root)
    check("★ baseline 缺失判 ERROR", rc == 1 and "no-baseline" in out)

    rc, out = run(root, "--update-baseline")
    check("★ 定基成功", rc == 0)
    check("★ 定基后恒绿", run(root)[0] == 0)

    # ① 改写既有目标 → 拦
    (root / "设计目标.md").write_text(body.replace("整件事做完", "整件事做完（大部分）"),
                                     encoding="utf-8")
    rc, out = run(root)
    check("★ 改写既有目标被拦", rc == 1 and "goal-changed" in out and "G-A-1" in out)

    # ② 删除既有目标 → 拦（退役编号应保留、不复用）
    (root / "设计目标.md").write_text(
        body.replace("- **G-A-2** — 停得下来但必须停得响。\n", ""), encoding="utf-8")
    rc, out = run(root)
    check("★ 删除既有目标被拦", rc == 1 and "goal-removed" in out and "G-A-2" in out)

    # ③ 纯新增 → 放行（新增不改变老编号的含义，改写与删除会）
    (root / "设计目标.md").write_text(body + "- **G-A-3** — 交付物恒产。\n", encoding="utf-8")
    rc, out = run(root)
    check("★ 纯新增目标放行且点出新增数", rc == 0 and "新增 1 条" in out)

    # ④ 实现名词体检：文件名 / flag / 步骤号 / 路径 各一条阳性对照
    for probe, label in ((" 调 `phase-3-5.md` 决定。", "文件名"),
                         (" 必须带 --unattended。", "命令行 flag"),
                         (" 见 Step 2.4.1.5。", "步骤号"),
                         (" 落到 `docs/plans/x`。", "路径")):
        (root / "设计目标.md").write_text(body + "- **G-A-9** —" + probe + "\n",
                                         encoding="utf-8")
        rc, out = run(root)
        check(f"★ 目标句含{label}被判实现、不是目标", rc == 1 and "impl-noun" in out and label in out)

    # ⑤ 反向：合规目标句不误报（否则门开一天就被关掉）
    (root / "设计目标.md").write_text(
        body + "- **G-A-9** — 无人值守意图逐级传递到底，不在任何一层丢失。\n",
        encoding="utf-8")
    check("★ 合规目标句零误报", run(root)[0] == 0)


def test_cascade_bypass_and_commit_gate():
    print("\n[54] 约定22 绕过反向判据 + 约定24 提交前门禁")
    from importlib.machinery import SourceFileLoader
    repo = Path(__file__).resolve().parents[3]
    M = SourceFileLoader("hg_byp", str(repo / ".aidp/scripts/commit_gate.py")).load_module()

    def por(*paths):
        return "\n".join(" M " + p for p in paths)

    CODE = "code/backend/src/main/java/A.java"
    PLAN = "docs/requirements/V0.1/研发需求/01_研发需求.md"
    LEDGER = "docs/requirements/V0.1/研发需求/_开发期需求增量.md"

    # ★ 阳性：代码 + 上游规划产物同现、且没动台账 —— 合规攒批路径下两者在时间上是分离的
    r = M.suspected_cascade_bypass(por(CODE, PLAN))
    check("★ 代码+规划产物同现且台账未动 → 判疑似绕过", r["suspected"] is True)
    check("★ 点名具体文件（不是只给个布尔）",
          CODE in r["code_files"] and PLAN in r["planning_files"])

    # ★ 阴性组 —— 门要是误报，开一天就被关掉，所以每条都必须实测
    check("阴性①：动了台账 = 合规收口，不报",
          M.suspected_cascade_bypass(por(CODE, PLAN, LEDGER))["suspected"] is False)
    check("阴性②：只改代码、不碰规划文档，不报",
          M.suspected_cascade_bypass(por(CODE))["suspected"] is False)
    check("阴性③：只改规划文档、不碰代码，不报",
          M.suspected_cascade_bypass(por(PLAN))["suspected"] is False)
    check("阴性④：结构性 README 不算迭代产物（段数 <4）",
          M.suspected_cascade_bypass(por(CODE, "docs/plans/README.md"))["suspected"] is False)
    check("阴性⑤：空树不报", M.suspected_cascade_bypass("")["suspected"] is False)
    # 脚手架契约路径本身不该被当成上游规划产物
    check("阴性⑥：脚手架契约改动不参与判定",
          M.suspected_cascade_bypass(por(".aidp/commands/sprint-dev.md", CODE))["suspected"] is False)

    # 四个规划族都要认（漏一个族 = 那一族的绕过永远查不出来）
    for fam in ("requirements", "design", "plans", "testing"):
        pth = "docs/%s/V0.1/x/01_a.md" % fam
        check("★ 覆盖规划族 docs/%s/" % fam,
              M.suspected_cascade_bypass(por(CODE, pth))["suspected"] is True)

    # 中文路径经 git 引号转义后仍要能解析（真实仓库里规划产物全是中文名）
    quoted = ' M "docs/requirements/V0.1/\\347\\240\\224\\345\\217\\221/01_a.md"'
    check("★ git 引号转义的中文路径能解析",
          M.suspected_cascade_bypass(por(CODE) + "\n" + quoted)["suspected"] is True)

    # ★ gate 必须把它算进退出码：只打印不抬码 = 与"住在永不执行的分支里"同构
    gate_src = (repo / ".aidp/scripts/commit_gate.py").read_text(encoding="utf-8")
    check("★ 疑似绕过计入退出码 3", '(info.get("suspected_cascade_bypass") or {}).get("suspected")' in gate_src)
    check("★ 疑似绕过恒打印 stderr（--quiet 不压制）", '🚧 疑似绕过约定 22 攒批' in gate_src)
    check("★ --cascade-now 是唯一合法例外", '"--cascade-now"' in gate_src
          and 'suppressed_by' in gate_src)


    # ★ 约定 12 曾是"实时回写"的指挥源，与约定 22 攒批从未对过账 —— 下游观感就是
    #   "开发过程中版本规划文件在被实时更新"。它必须把时机让给约定 22。
    aidp = (repo / ".aidp/AIDP-AGENTS.md").read_text(encoding="utf-8")
    c12 = [l for l in aidp.split("\n") if l.startswith("12. ")]
    check("★ 约定 12 存在且把执行时机让给约定 22", len(c12) == 1 and "归约定 22" in c12[0])
    check("★ 约定 12 明令开发期不实时改这些文档",
          "开发过程中不实时改这些文档" in c12[0] and "以约定 22 为准" in c12[0])
    check("★ 约定 12 不再指挥「自动回写主文档 + 刷索引」", "自动回写" not in c12[0])
    # ★ bugfix 修完当场级联是第二个源头
    # ★ Step 5~6 已切到 mode-b2.md（mode-b.md 长期贴 20480B 上限，改动即越界）
    mb = (repo / ".aidp/flows/sprint-bugfix/mode-b2.md").read_text(encoding="utf-8")
    check("★ bugfix Step 5 默认攒批、不当场级联",
          "执行时机 = 攒批" in mb and "本步默认【不当场跑下面的四级级联】" in mb)
    check("★ bugfix 四级级联降级为 --cascade-now / 收口点才跑",
          "仅在 `--cascade-now` 或命中收口点时执行" in mb)
    check("★ bugfix 收口级联落主文档、不新建 NN_ 分册",
          "不新建 `NN_` 分册" in mb and "--ledger-cascade" in mb)
    check("★ bugfix 收口级联补齐 L4 自测用例",
          "L4 自测用例" in mb and "sprint-selftest" in mb)
    # ★ 已级联必须真删，标记不替代删除
    led = (repo / ".aidp/reference/开发期族增量.md").read_text(encoding="utf-8")
    check("★ 详规撤销「打标记留档」出路", "没有\"打个标记留档\"这条出路" in led
          and "标记不替代删除" in led)
    hg = (repo / ".aidp/scripts/commit_gate.py").read_text(encoding="utf-8")
    check("★ gate 不再整档跳过存档标记", "照常解析计数" in hg)
    check("★ gate 把 archived_not_deleted 计入退出码",
          'casc.get("archived_not_deleted")' in hg and "cascade-archived-not-deleted" in hg)
    ccl = (repo / ".aidp/scripts/check_cascade_landing.py").read_text(encoding="utf-8")
    check("★ 收口门把存档标记判 FAIL", '"archived-not-deleted"' in ccl)

    # ★ 幽灵 flag：被声明为「唯一合法授权」的 flag 必须有解析器之外的消费者
    p38 = (repo / ".aidp/flows/sprint-autopilot/phase-3-8.md").read_text(encoding="utf-8")
    check("★ --skip-aiauto-test 有真实消费点（此前只有解析器、零消费者）",
          'SKIP_AIAUTO_TEST:-0' in p38 and "WILL_BROWSER_TEST=" in p38)
    ap_md = (repo / ".aidp/commands/sprint-autopilot.md").read_text(encoding="utf-8")
    check("★ --skip-aiauto-test 已登记进参数表", "| `--skip-aiauto-test` ★ |" in ap_md)
    # ★ 复测闭环必须进得了 Phase 3（否则「测试失败后自动修复复测」整句落空）
    p06 = ((repo / ".aidp/flows/sprint-autopilot/phase-0-6.md").read_text(encoding="utf-8")
           + "\n"
           + (repo / ".aidp/flows/sprint-autopilot/phase-0-6b2.md").read_text(encoding="utf-8"))
    check("★ TARGET 候选给复测待办开了第二条豁免",
          "复测待办优先" in p06 and "auto_fixable_pending" in p06)
    p06b = (repo / ".aidp/flows/sprint-autopilot/phase-0-6b.md").read_text(encoding="utf-8")
    check("★ 0.3.4bis 把游标推到 Phase 3（否则走完 Phase 0 就没下文）",
          'run-state "3.1.5-build"' in p06b)
    check("★ 0.3.4bis 顺序为「派修复（不推送）→ 铸新 build → 推送重部署」", "派修复（不推送）→ 铸新 build → 推送重部署" in p06b)
    check("★ step 3bis 判据表已有正式落点", "step 3bis" in p06b and "retest_frozen_head" in p06b)
    # ★ 合法冻结不该被 handback 门判违规（G-AUTOPILOT-6「起得来」）
    cg = (repo / ".aidp/scripts/autopilot-ceremony-gate.py").read_text(encoding="utf-8")
    check("★ handback 谓词认合法冻结（四件套齐备才豁免）",
          "frozen-by-contract" in cg and "freeze_quartet_complete" in cg)
    check("★ 半截冻结不豁免（只 echo 不写 baseline 的不给通行证）",
          "半截冻结" in cg)
    sg = (repo / ".aidp/hooks/autopilot-stop-guard.py").read_text(encoding="utf-8")
    check("★ Stop hook 调 handback-check 带 --record（last_handback 的唯一写入方）",
          '"--record"' in sg)
    # ★ unconverged 解冻不能只靠活指针
    uf = (repo / ".aidp/scripts/autopilot_unfreeze.py").read_text(encoding="utf-8")
    check("★ unconverged 解冻优先读冻结时快照", "unconverged_frozen_head" in uf)
    check("★ 快照缺失时不静默判「不解冻」（那正是永久冻结的形态）",
          "冻结快照缺失" in uf)

    # ★ 三类新欠账信号：都必须【有 stderr + 计退出码】，只留 JSON 字段等于静默
    hg2 = (repo / ".aidp/scripts/commit_gate.py").read_text(encoding="utf-8")
    check("★ 约定 31.5 欠账有信号（裸对话推送此前零 CICD 信号）",
          "def pending_cicd(" in hg2 and "🚄 本次推送未经推送分类器" in hg2)
    check("★ 31.5 欠账计入退出码", '(info.get("pending_cicd") or {}).get("pending")' in hg2)
    check("★ 31.5 适用条件 = cicd.provider != none（按项目配置，不看是否跑过 autopilot）",
          'provider == "none"' in hg2)
    c3 = (repo / ".aidp/reference/约定细则-3.md").read_text(encoding="utf-8")
    check("★ 31.5 作用域补齐「与命令入口无关 / 裸对话同样适用」",
          "代码推送这一事实" in c3 and "裸对话路径" in c3)
    check("★ 约定 24 退出码 3 的补做指引按成因分流",
          "按成因补做" in aidp and "派台账收口子 Agent" in aidp)

    check("★ 约定 22 主行补「作用域=变更事实、与命令入口无关」",
          "作用域 = 变更事实、与命令入口无关" in aidp)
    check("★ 约定 22 主行不再自相矛盾地枚举收口点后又说不枚举",
          "本行不再枚举" not in aidp)
    check("★ 约定 35 补阳性对照子规则", "阳性对照" in aidp and "0 错误" in aidp)
    code_rules = (repo / ".aidp/rules/code.md").read_text(encoding="utf-8")
    check("★ rules/code.md 承载阳性对照详规", "静态验证工具的阳性对照" in code_rules)
    check("★ rules/code.md 禁既有文件全量 autofix",
          "只允许作用于【本次新建】的文件" in code_rules and "git blame" in code_rules)


def test_doc_numbering_and_selfcheck():
    print("\n[55] 文档编号连续性 + 检查脚本阳性对照骨架")
    repo = Path(__file__).resolve().parents[3]
    script = repo / ".aidp/scripts/check_doc_numbering.py"

    def run(root, *a):
        r = subprocess.run([sys.executable, str(script), "--root", str(root), *a],
                           capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    # —— 阳性对照：列表重号必须报 ERROR ——
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / ".aidp/reference"
        d.mkdir(parents=True)
        (d / "x.md").write_text("# t\n\n- **1. 甲**\n- **2. 乙**\n- **2. 丙**\n", encoding="utf-8")
        rc, out = run(Path(td))
        check("★ 列表重号判 ERROR（切片替换吞并的确定性痕迹）", rc == 1 and "编号重复" in out)
        # —— 阴性对照：连续编号必须绿 ——
        (d / "x.md").write_text("# t\n\n- **1. 甲**\n- **2. 乙**\n- **3. 丙**\n", encoding="utf-8")
        rc, out = run(Path(td))
        check("★ 连续编号不误报", rc == 0)
        # —— 嵌套子列表各自从 1 开始不是重号 ——
        (d / "x.md").write_text(
            "# t\n\n1. 甲\n\n   1. 子一\n   2. 子二\n\n2. 乙\n\n   1. 子一\n   2. 子二\n",
            encoding="utf-8")
        rc, out = run(Path(td))
        check("★ 兄弟子列表各自从 1 开始不判重号（否则满屏假红）", rc == 0)
        # —— 标题同号只判 WARN（姊妹条 / 多角度分节是本范式的正当写法）——
        (d / "x.md").write_text("# t\n\n## 约定 23 — 甲\n\n正文\n\n## 约定 23 姊妹条 — 乙\n\n正文\n",
                                encoding="utf-8")
        rc, out = run(Path(td))
        check("★ 标题同号只判 WARN、不阻断", rc == 0 and "编号重复" in out)

    # 真仓：应无 ERROR
    rc, out = run(repo)
    check("★ 本仓文档编号无重号", rc == 0)

    # —— 自检骨架：契约脚本必须全部支持 --self-check ——
    sdir = repo / ".aidp/scripts"
    missing = [f.name for f in sorted(sdir.glob("check_*.py"))
               if "--self-check" not in f.read_text(encoding="utf-8")]
    check("★ 全部 check_*.py 都接了 --self-check（%d 个）"
          % len(list(sdir.glob("check_*.py"))), not missing)

    sc = (sdir / "selfcheck.py").read_text(encoding="utf-8")
    check("★ 自检做双侧对照（只跑阳性证明不了「不是恒红」）",
          "阴性对照" in sc and "neg_rc" in sc)
    check("★ 覆盖缺口刻意可见、不计入失败（unregistered 必须被点名）",
          "unregistered" in sc and "未经自证" in sc)
    check("★ unsupported 必须写明原因（留空等于把缺口藏起来）",
          "def unsupported(name, reason)" in sc)
    check("★ 注入不回写种子副本（先 remove 再写，断开硬链接）",
          "os.remove(p)" in sc and "cp\", \"-al" in sc)

    # 全量自检必须零 fail —— 有脚本抓不到自己的探针即为失效
    r = subprocess.run([sys.executable, str(sdir / "selfcheck.py"), "--json"],
                       capture_output=True, text=True)
    try:
        data = json.loads(r.stdout)
    except ValueError:
        data = {}
    tally = data.get("tally", {})
    check("★ 全量自检零 fail（fail=有检查抓不到本该抓到的东西）%s" % tally,
          r.returncode == 0 and not tally.get("fail"))
    check("★ 已登记探针覆盖 ≥ 25 个脚本（当前 %s）" % tally.get("pass"),
          tally.get("pass", 0) >= 25)


def test_yield_wake_source_plumbing():
    print("\n[56] yield 守卫棘轮 + HAS_WAKE_SOURCE 供给链")
    repo = Path(__file__).resolve().parents[3]
    guard = repo / ".aidp/scripts/check_yield_guard.py"
    src = guard.read_text(encoding="utf-8")

    # —— 棘轮：KNOWN_OPEN 只能变短，清空后不许再长回来 ——
    ns = {}
    exec(compile(src.split("def _is_known_open")[0], str(guard), "exec"), ns)
    check("★ KNOWN_OPEN 已清空（9 处逐条判完；再加条目 = 把待修项重新藏起来）",
          ns.get("KNOWN_OPEN") == set())

    # —— 真仓：零 ERROR ——
    r = subprocess.run([sys.executable, str(guard), "--root", str(repo)],
                       capture_output=True, text=True)
    check("★ 本仓 yield 站点全部带守卫或已标 ignore", r.returncode == 0)

    # —— 阳性对照：新增无守卫站点必须 ERROR（否则这道门等于不存在）——
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / ".aidp/flows/x"
        d.mkdir(parents=True)
        (d / "a.md").write_text("```bash\nif [ 1 = 1 ]; then\n  exit 0   # 让位本 tick\nfi\n```\n",
                                encoding="utf-8")
        rc = subprocess.run([sys.executable, str(guard), "--root", str(td)],
                            capture_output=True, text=True).returncode
        check("★ 阳性对照：裸让位判 ERROR", rc == 1)
        # 阴性对照：同围栏内出现守卫即放行
        (d / "a.md").write_text('```bash\nif [ "${HAS_WAKE_SOURCE:-0}" = "1" ]; then\n'
                                "  exit 0   # 让位本 tick\nfi\n```\n", encoding="utf-8")
        rc = subprocess.run([sys.executable, str(guard), "--root", str(td)],
                            capture_output=True, text=True).returncode
        check("★ 阴性对照：带守卫不误报", rc == 0)

    # —— 供给链：判据读不到值时，守卫写了等于没写 ——
    tf = (repo / ".aidp/scripts/autopilot_tick_flags.py").read_text(encoding="utf-8")
    check("★ HAS_WAKE_SOURCE 有 BASELINE_FALLBACK（真源 = autopilot.wake_source_this_tick）",
          '"HAS_WAKE_SOURCE": ("root", "autopilot.wake_source_this_tick")' in tf)
    check("★ 兜底默认 fail-closed 取 0（兜成 1 = 以为还有下一 tick，正是要防的失效）",
          '"HAS_WAKE_SOURCE": "0"' in tf)
    for cmd in ("autopilot", "aiauto-test"):
        out = subprocess.run([sys.executable, str(repo / ".aidp/scripts/autopilot_tick_flags.py"),
                              "--shell", "--command", cmd], capture_output=True, text=True).stdout
        check("★ --shell --command %s 能供出 HAS_WAKE_SOURCE（非空）" % cmd,
              re.search(r"^HAS_WAKE_SOURCE='?\d", out, re.M) is not None)

    # —— 带阈值的门都补了「无唤醒源即当场达阈」——
    # ★ 判据必须认**两种**形态，否则它会随重构自己失效：把手抄的四件套收敛进
    #   `autopilot_fail_handle.py` 后，字面量分支被脚本内建的同款判断取代（见该脚本
    #   `freeze = streak >= threshold or wake == "0"`）—— 只数字面量会让「迁移一处 = 少一处」，
    #   最终把一次**正确的重构**判成回归，而真正的覆盖面其实没掉。
    inline = fh = 0
    for f in sorted((repo / ".aidp/flows").rglob("*.md")):
        if f.name == "rationale.md":
            continue
        txt = f.read_text(encoding="utf-8")
        inline += txt.count('[ "${HAS_WAKE_SOURCE:-0}" = "0" ]')
        fh += len(re.findall(r"autopilot_fail_handle\.py", txt))
    check("★ 带阈值的熔断门均已补无唤醒源分支（内联 %d + 经 fail_handle %d，合计应 ≥ 7）"
          % (inline, fh), inline + fh >= 7)
    # ★ 反向断言：脚本侧那份判断必须还在 —— 它是上面 fh 那一半的全部依据，
    #   被删掉的话上面的计数会继续通过，而覆盖面已经归零。
    fhs = (repo / ".aidp/scripts/autopilot_fail_handle.py").read_text(encoding="utf-8")
    check("★ fail_handle 内建「无唤醒源 = 等价已达阈」判断仍在",
          'wake == "0"' in fhs and "freeze = streak >= a.threshold" in fhs)


def test_memory_section_loss_guard():
    print("\n[58] memory 整段被吞：确定性落点")
    repo = Path(__file__).resolve().parents[3]
    script = repo / ".aidp/scripts/check_memory_loss.py"
    check("★ 脚本存在（G-INIT-3 的确定性落点；此前命令文档自陈「没有任何这类机制」）",
          script.is_file())
    if not script.is_file():
        return

    BASE = ("# 系统模式\n\n## 技术选型总览\n\n- Java 17\n- Spring Boot 3\n- Vue 3\n"
            "\n## 架构决策记录\n\n### ADR-001: （待填充）\n\n待补充。\n"
            "\n## 已知问题和技术债务\n\n- 债务一\n- 债务二\n- 债务三\n- 债务四\n- 债务五\n")

    def mkrepo(new_text):
        d = Path(tempfile.mkdtemp())
        (d / "memory").mkdir()
        (d / "memory/systemPatterns.md").write_text(BASE, encoding="utf-8")
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "base"]):
            subprocess.run(cmd, cwd=d, capture_output=True)
        (d / "memory/systemPatterns.md").write_text(new_text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(script), "--root", str(d), "--json"],
                           capture_output=True, text=True)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            return r.returncode, {}

    # 阴性①：一字未改 → 绿
    rc, d = mkrepo(BASE)
    check("★ 阴性：未改动不报（恒红的门会被关掉）", rc == 0 and not d.get("errors"))

    # 阴性②：填掉 `（待填充）` 占位符 —— 这正是约定 8 强制要求的动作，⛔ 绝不能报
    rc, d = mkrepo(BASE.replace("（待填充）", "选用 Redis 作二级缓存"))
    check("★ 阴性：填占位符不判段落消失（误伤这一条 = 阻止约定 8 要求的动作）",
          rc == 0 and not d.get("errors"))

    # 阴性③：正常追加一条 ADR → 绿
    rc, d = mkrepo(BASE.replace("- 债务五\n", "- 债务五\n- 债务六\n"))
    check("★ 阴性：追加内容不报", rc == 0 and not d.get("errors"))

    # 阳性①：整段消失 → L1 ERROR
    gone = BASE.replace("## 技术选型总览\n\n- Java 17\n- Spring Boot 3\n- Vue 3\n\n", "")
    rc, d = mkrepo(gone)
    rules = {e.get("rule") for e in (d.get("errors") or [])}
    check("★ 阳性：整段消失判 L1 ERROR", rc == 1 and "L1" in rules)

    # 阳性②：段落塌缩（5 行 → 1 行）→ L2 ERROR
    shrunk = BASE.replace("- 债务一\n- 债务二\n- 债务三\n- 债务四\n- 债务五\n", "- 债务一\n")
    rc, d = mkrepo(shrunk)
    rules = {e.get("rule") for e in (d.get("errors") or [])}
    check("★ 阳性：段落塌缩判 L2 ERROR", rc == 1 and "L2" in rules)

    # 阳性③：整份被 Write 覆盖 → L3 ERROR
    rc, d = mkrepo("# 系统模式\n\n## 技术选型总览\n\n- Java 17\n")
    rules = {e.get("rule") for e in (d.get("errors") or [])}
    check("★ 阳性：整份塌缩判 L3 ERROR", rc == 1 and ("L3" in rules or "L1" in rules))

    # 调用方：只有实现没有调用方 = 没有这道门（本仓反复栽的同一个跟头）
    ms = (repo / ".aidp/commands/memory-sync.md").read_text(encoding="utf-8")
    check("★ /memory-sync 收尾调用它（⛔ 有实现没调用方 = 没有这道门）",
          "check_memory_loss.py" in ms)


def test_cascade_bypass_structural_shape():
    print("\n[59] 约定 22 绕过检出：补「只改代码、册子零动」这一最常见形态")
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str((repo / ".aidp/scripts").resolve()))
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "hg_t", str(repo / ".aidp/scripts/commit_gate.py"))
    hg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hg)

    def f(por):
        return hg.suspected_cascade_bypass(por)

    check("★ 空树不报", not f("")["suspected"])

    por1 = " M code/backend/x/src/A.java\n M docs/design/detail/V0.1.0/01_详细设计.md\n"
    r = f(por1)
    check("★ 形态一（代码 + 上游产物同现、零台账）仍报",
          r["suspected"] and r["shape"] == "当场级联")

    r = f(por1 + " M docs/design/detail/V0.1.0/_开发期设计增量.md\n")
    check("★ 动了台账即不报（合法收口路径必然动册）", not r["suspected"])

    # ★ 本组要补的缺口：只改代码、上游文档一字未动 —— 形态一的 ② 不成立，整条判据此前不触发
    r = f(" A code/frontend/app/src/views/UserList.vue\n")
    check("★ 形态二（新增页面 + 零台账）现在能报 —— 此前恒不触发，而后果更重"
          "（收口点 3 会因「册子不存在」判合法终态放行）",
          r["suspected"] and r["shape"] == "结构性新增零台账" and r["structural_signals"])

    # 阴性：普通方法体改动不该报（误报会让这道门当天被关掉）
    r = f(" M code/backend/x/src/Helper.java\n")
    check("★ 阴性：无结构性新增的普通改动不报（零语义推断、不臆测）",
          not r["suspected"])

    src = (repo / ".aidp/scripts/commit_gate.py").read_text(encoding="utf-8")
    check("★ 两种形态的告警文案分开（形态二要说清它为什么更重）",
          "结构性新增零台账" in src and "册子不存在" in src)
    check("★ 只认最无歧义的结构信号（接口端点 / 建表 DDL / 新增页面），⛔ 不做语义判断",
          "_STRUCT_PATTERNS" in src and "CREATE\\s+TABLE" in src)


def test_index_staleness_and_mirror_copy():
    print("\n[60] 隐形漂移：内容变了但 git status 报 clean")
    repo = Path(__file__).resolve().parents[3]
    script = repo / ".aidp/scripts/check_index_staleness.py"
    check("★ 脚本存在", script.is_file())
    if not script.is_file():
        return

    # ★ 夹具文件名**必须含中文**：git 默认 `core.quotepath=on` 会把非 ASCII 路径整条包成
    #   C 转义串，转义串再去 `os.path.isfile` 恒为 False ⇒ 该类文件被静默踢出巡检面、
    #   scanned 计数跟着少、输出与"扫完没问题"完全同形。而约定 14 要求 AIDP 产物**文件名
    #   也用中文** —— 用 `a.md` 这种纯 ASCII 夹具做阳性对照，恰好绕开了唯一的失效维度
    #   （实证：这道门曾在 1850 份里只扫 1725 份、放过 7 处真实漂移，而它自己报"✅ 无漂移"）。
    REL = ".aidp/需求文档（模型相关）.md"

    def mk(assume_unchanged, change):
        d = Path(tempfile.mkdtemp())
        (d / ".aidp").mkdir()
        (d / REL).write_text("hello\n", encoding="utf-8")
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-qm", "base"]):
            subprocess.run(cmd, cwd=d, capture_output=True)
        if assume_unchanged:
            subprocess.run(["git", "update-index", "--assume-unchanged", REL],
                           cwd=d, capture_output=True)
        if change:
            (d / REL).write_text("CHANGED\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(script), "--root", str(d), "--json"],
                           capture_output=True, text=True)
        try:
            return r.returncode, json.loads(r.stdout)
        except ValueError:
            return r.returncode, {}

    # 阳性：status 看不见（assume-unchanged 精确复现 stat 快速路径失明）+ 内容已变 → 报红
    rc, d = mk(True, True)
    check("★ 阳性：status 看不见的内容变更判 ERROR", rc == 1 and d.get("errors"))

    # 阴性①：内容变了但 status 看得见 = 正常的未提交改动 → ⛔ 不报（否则每次编辑都红）
    rc, d = mk(False, True)
    check("★ 阴性：正常未提交改动不报（恒红的门会被关掉）", rc == 0 and not d.get("errors"))

    # 阴性②：一字未改 → 绿
    rc, d = mk(True, False)
    check("★ 阴性：未改动不报", rc == 0 and not d.get("errors"))

    # ★ 巡检面不得静默缩水：中文名文件必须真的进了 scanned，且 dropped 为空
    check("★ 中文名文件确实进了巡检面（scanned 覆盖到它、dropped 为空）",
          d.get("scanned") == 1 and not d.get("dropped"))

    # ★ 两处 git 调用必须关掉路径转义（-z）——这是上面那类失明的唯一结构性防线
    src = script.read_text(encoding="utf-8")
    check("★ ls-files / status 均按 NUL 分隔取路径，不吃 core.quotepath 转义",
          '"ls-files", "-s", "-z"' in src and '"status", "--porcelain", "-z"' in src)

    # 根因：镜像器不得保留源 mtime


def test_fail_handle_five_steps():
    print("\n[61] 失败处置五步：记账 → 判阈 → 冻结四件套 → 发 #4 → 让位")
    repo = Path(__file__).resolve().parents[3]
    script = repo / ".aidp/scripts/autopilot_fail_handle.py"
    check("★ 脚本存在", script.is_file())
    if not script.is_file():
        return

    def run_in(baseline, wake, extra=()):
        d = Path(tempfile.mkdtemp())
        (d / "memory").mkdir()
        (d / "memory/.sprint-autopilot-baseline.json").write_text(
            json.dumps(baseline, ensure_ascii=False), encoding="utf-8")
        os.symlink(repo / ".aidp", d / ".aidp")
        if wake is not None:
            subprocess.run([sys.executable, str(repo / ".aidp/scripts/baseline_edit.py"),
                            "set", "autopilot.wake_source_this_tick", wake],
                           cwd=d, capture_output=True)
        r = subprocess.run([sys.executable, str(script), "--version", "V0.1.0",
                            "--phase", "3.2-dev", "--reason", "unconverged",
                            "--why", "探针", "--no-card", "--json", *extra],
                           cwd=d, capture_output=True, text=True)
        try:
            out = json.loads(r.stdout)
        except ValueError:
            out = {}
        data = json.loads((d / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
        return r.returncode, out, data

    # 有唤醒源 + 首次失败 → 只记账，不冻结（rc=0）
    rc, out, data = run_in({"versions": {"V0.1.0": {}}}, "1")
    v = data.get("versions", {}).get("V0.1.0", {})
    check("★ 有唤醒源 + 未达阈 → 只记账不冻结（rc=0）",
          rc == 0 and out.get("streak") == 1 and not out.get("frozen")
          and not v.get("needs_human"))

    # ★ 无唤醒源 → 阈值恒不可达，必须**当场**冻结（rc=3），否则 exit 0 会被上游读成"跑过了"
    rc, out, data = run_in({"versions": {"V0.1.0": {}}}, "0")
    v = data.get("versions", {}).get("V0.1.0", {})
    check("★ 无唤醒源 → 当场冻结（rc=3），不等一个永远到不了的阈值",
          rc == 3 and out.get("frozen"))
    check("★ 冻结四件套一次写齐（缺任一都会永久停摆）",
          v.get("needs_human") is True and v.get("aiauto_frozen_at")
          and v.get("freeze_reason") == "unconverged" and v.get("needs_human_reason"))
    check("★ 顶层 aiauto_blocked_reason 同写（缺它开发链路会误判测试链路健康）",
          str(data.get("aiauto_blocked_reason", "")).startswith("frozen:unconverged@"))

    # 达阈 → 冻结
    rc, out, data = run_in({"versions": {"V0.1.0": {"unconverged_x": 0}}}, "1",
                           extra=("--threshold", "1"))
    check("★ 达阈 → 冻结（rc=3）", rc == 3 and out.get("frozen"))

    # 枚举非法 → rc=2 且**什么都没写**（⛔ 不得当成已处置）
    d = Path(tempfile.mkdtemp())
    (d / "memory").mkdir()
    (d / "memory/.sprint-autopilot-baseline.json").write_text('{"versions":{"V0.1.0":{}}}',
                                                              encoding="utf-8")
    os.symlink(repo / ".aidp", d / ".aidp")
    r = subprocess.run([sys.executable, str(script), "--version", "V0.1.0", "--phase", "x",
                        "--reason", "not-an-enum-value", "--why", "w", "--no-card"],
                       cwd=d, capture_output=True, text=True)
    after = json.loads((d / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
    check("★ 枚举非法 → rc=2 且一个字节都没写（⛔ 别把 2 读成「处置过了」）",
          r.returncode == 2 and after == {"versions": {"V0.1.0": {}}})

    # 枚举与冻结契约门同源，⛔ 不另写一份
    src = script.read_text(encoding="utf-8")
    check("★ 枚举复用 check_freeze_contract 的解析器（两份各自维护必然漂移）",
          "check_freeze_contract" in src)

    # 调用方：散文里的「走失败处置流程」必须有可执行落点
    hits = 0
    for f in sorted((repo / ".aidp/flows/sprint-autopilot").glob("*.md")):
        hits += f.read_text(encoding="utf-8").count("autopilot_fail_handle.py")
    check("★ flows 里已有可执行调用（命中 %d 处，应 ≥ 5）" % hits, hits >= 5)


def test_mock_guard_split_by_marker():
    print("\n[62] Mock 守卫策略按标记分流（两类目的相反，混用即出事）")
    repo = Path(__file__).resolve().parents[3]

    code = (repo / ".aidp/rules/code.md").read_text(encoding="utf-8")
    fe = (repo / ".aidp/agents/frontend.md").read_text(encoding="utf-8")
    be = (repo / ".aidp/agents/backend.md").read_text(encoding="utf-8")
    st = (repo / ".aidp/commands/sprint-test.md").read_text(encoding="utf-8")

    # ★ 旧口径「运行时可控铁律」一刀切禁构建期守卫，与上游对 DEV_MOCK 的要求正相反 ——
    #   留着它，执行体照 rules 写会被 dev_mock_runtime_switch 判 Important，
    #   照上游写又违反本仓铁律，两头都不对。
    check("★ 一刀切的「运行时可控铁律」已退场（它与 DEV_MOCK 的合规形态直接冲突）",
          "运行时可控铁律" not in code and "运行时可控铁律" not in fe
          and "运行时可控铁律" not in be)
    for name, txt in (("rules/code.md", code), ("agents/frontend.md", fe)):
        check("★ %s 写明两类分流（THIRD_PARTY_MOCK 运行时开关 / DEV_MOCK 构建期裁掉）" % name,
              "守卫策略按标记分流" in txt and "THIRD_PARTY_MOCK" in txt and "DEV_MOCK" in txt)
    check("★ 明确 DEV_MOCK 的构建期守卫是合规形态、不是违规",
          "构建期裁掉" in code and "合规形态" in code)

    # 入参门控：漏传 --third-party-mode 的失效方向是**假红**（合规代码被判 Critical + exit 1）
    check("★ /sprint-test 交代了 --third-party-mode 何时传（入参门控，漏传即假红）",
          "--third-party-mode" in st and "假红" in st)
    check("★ 并写明豁免要字段完整才买得到（否则裸标记 = 关掉 2A 的后门）",
          "字段完整" in st)

    # 上游脚本的真实行为对照 —— ⛔ 不只读散文：口径写对了而脚本不这么判，等于没改
    scan = repo / ".aidp/skills/code-verification-loop/scripts/scan_third_party_mock_antipatterns.py"
    if not scan.is_file():
        check("★ 上游扫描器存在（未下发时跳过行为对照）", True)
        return

    def hits(text, fname="i.ts"):
        d = Path(tempfile.mkdtemp())
        (d / "src").mkdir()
        (d / "src" / fname).write_text(text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(scan), str(d), "--json"],
                           capture_output=True, text=True)
        try:
            data = json.loads(r.stdout)
        except ValueError:
            return r.returncode, []
        return r.returncode, [i for x in data.get("results", []) for i in x.get("issues", [])]

    DEV_OK = ("if (import.meta.env.DEV) {\n"
              "  // DEV_MOCK: 后端接口未部署\n"
              "  // since: 2026-09-10\n  // owner: FE-x\n  // REMOVE_WHEN: 后端上线后删\n"
              "  doMock();\n}\n")
    rc, iss = hits(DEV_OK)
    check("★ 行为对照·阴性：DEV_MOCK + 构建期守卫 → 0 命中（这正是上游推荐写法）",
          rc == 0 and not iss)

    TPM_BAD = ("if (import.meta.env.DEV) {\n"
               "  // THIRD_PARTY_MOCK: 支付宝\n  // vendor: alipay\n  // api: /gw\n"
               "  // since: 2026-09-01\n  // expected_ready: 2026-09-20\n  // owner: BE-y\n"
               "  // REMOVE_WHEN: 联调通过\n  mockPay();\n}\n")
    rc, iss = hits(TPM_BAD)
    check("★ 行为对照·阳性：THIRD_PARTY_MOCK + 构建期守卫 → 仍判 Critical",
          rc == 1 and any(i.get("type") == "build_time_guard" for i in iss))

    # ★ 标注行判定的两侧边界（上游 2026-09-14 用「块注释状态机」切干净的那一刀）——
    #   锁死它，是因为这两个方向的回归**长相完全不同**：
    #     · 放宽 → Python 类型标注 `NAME: bool = True` 被判 missing_fields/Critical，
    #       假红打在一行正常业务代码上，作者除了改变量名无从修；
    #     · 收紧过头 → Java 块注释里顶格写的标注块整块隐形，从假红翻成**假绿**。
    for label, body, fname in (
        ("Py 顶格类型标注", "DEV_MOCK: bool = True\n", "a.py"),
        ("Py 缩进类型标注", "class C:\n    DEV_MOCK: bool = True\n", "b.py"),
    ):
        rc, iss = hits(body, fname)
        check("★ 行为对照·阴性：%s → 0 命中（不是标注块）" % label,
              rc == 0 and not iss)

    _T = "THIRD_PARTY" + "_MOCK"
    JAVA_OK = ("class Pay {\n  /*\n" + _T + ": 支付宝\nvendor: alipay\napi: /gw\n"
               "since: 2026-09-01\nexpected_ready: 2026-09-20\nowner: BE-y\n"
               "REMOVE_WHEN: 联调通过\n  */\n  void f(){ mockPay(); }\n}\n")
    rc, iss = hits(JAVA_OK, "Pay.java")
    check("★ 行为对照·阴性：Java 块注释顶格 marker 仍被识别（⛔ 防修成假绿）",
          rc == 0 and not iss)

    JAVA_BAD = ("class Pay {\n  /*\nDEV_MOCK: 后端未部署\nsince: 2026-09-14\nowner: FE-x\n"
                "  */\n}\n")
    rc, iss = hits(JAVA_BAD, "Pay2.java")
    check("★ 行为对照·阳性：块注释内缺字段仍判 Critical（证明不是整块被跳过）",
          rc == 1 and any(i.get("type") == "missing_fields" for i in iss))


def test_gates_see_the_encapsulated_form():
    """[63] 把手抄动作收敛进脚本后，各门必须**仍看得见**这些站点。

    ⛔ 本组的存在理由：`autopilot_fail_handle.py` 把「bump → 判阈 → 冻结四件套 → 发 #4 → 让位」
    五步收进一个调用，这是修复；但只认手抄形态的门会因此**巡检面整体缩水** ——
    WARN 数随迁移下降，看起来像"修好了"，实则"看不见了"。本仓栽过一模一样的跟头：
    `chrome-unavailable` 一度被误报成「零写入者」，正是因为写入者换成了脚本形态。
    四道门（冻结契约 / yield 守卫 / flow 变量 / bash 语法）各钉一条。
    """
    print("\n[63] 收敛进脚本后，各门仍看得见")
    repo = Path(__file__).resolve().parents[3]

    # ① 冻结契约门：认 fail_handle 为写入者，且 --no-card / 非法 reason 要报 ERROR
    fc = (repo / ".aidp/scripts/check_freeze_contract.py").read_text(encoding="utf-8")
    check("★ 冻结契约门认得 autopilot_fail_handle.py 形态",
          "FAIL_HANDLE_RE" in fc and "FAIL_HANDLE_REASON_RE" in fc)
    check("★ 且把 `--no-card` 判为「停得住但停不响」", "FAIL_HANDLE_NOCARD_RE" in fc)

    d = Path(tempfile.mkdtemp())
    for sub in ("sprint-autopilot", "sprint-aiauto-test"):
        (d / ".aidp/flows" / sub).mkdir(parents=True, exist_ok=True)
        shutil.copy(repo / ".aidp/flows" / sub / "rationale.md",
                    d / ".aidp/flows" / sub / "rationale.md")
    (d / ".aidp/scripts").mkdir(parents=True, exist_ok=True)
    shutil.copy(repo / ".aidp/scripts/autopilot_unfreeze.py", d / ".aidp/scripts")

    def freeze_probe(extra):
        (d / ".aidp/flows/sprint-autopilot/probe.md").write_text(
            "```bash\npython3 .aidp/scripts/autopilot_fail_handle.py --version \"$V\" \\\n"
            "  --phase p --reason probe-timeout --why w" + extra + "\n```\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(repo / ".aidp/scripts/check_freeze_contract.py"),
                            "--root", str(d), "--json"], capture_output=True, text=True)
        o = json.loads(r.stdout)
        return [f for f in o["findings"]
                if f.get("level") == "ERROR" and "probe.md" in str(f.get("file", ""))]

    check("★ 阴性：默认发卡形态不报 ERROR", not freeze_probe(""))
    check("★ 阳性：--no-card 判 ERROR（冻结停不响）", bool(freeze_probe(" --no-card")))

    # ② yield 守卫：fail_handle 视为守卫（它内建 wake 判断）+ 行内 UNATTENDED_YIELD 形态可见
    yg = (repo / ".aidp/scripts/check_yield_guard.py").read_text(encoding="utf-8")
    check("★ yield 守卫认 fail_handle 为守卫", "autopilot_fail_handle" in yg)
    check("★ 且认「行内 exit 0 + UNATTENDED_YIELD」这一形态", "YIELD_RE2" in yg)

    yd = Path(tempfile.mkdtemp())
    (yd / ".aidp/flows/x").mkdir(parents=True)
    (yd / ".aidp/flows/x/a.md").write_text(
        '```bash\n[ -n "$R" ] && { echo "UNATTENDED_YIELD"; exit 0; }\n```\n', encoding="utf-8")
    r = subprocess.run([sys.executable, str(repo / ".aidp/scripts/check_yield_guard.py"),
                        "--root", str(yd), "--json"], capture_output=True, text=True)
    o = json.loads(r.stdout)
    check("★ 阳性：行内 yield 且无守卫 → ERROR（旧正则对它完全失明）",
          o.get("sites") == 1 and len(o.get("errors") or []) == 1)

    # ③ flow 变量门：--streak-key 算递增方
    fv = (repo / ".aidp/scripts/check_flow_var_refs.py").read_text(encoding="utf-8")
    check("★ flow 变量门把 `--streak-key <字段>` 算作递增方（否则修复被报成「只清零不递增」）",
          fv.count("--streak-key") >= 2)

    # ④ bash 语法门：命令位占位符（`bash -n` 结构性抓不到）
    bs = (repo / ".aidp/scripts/check_flow_bash_syntax.py").read_text(encoding="utf-8")
    check("★ bash 门判「命令位尖括号占位符」", "placeholder-in-command-position" in bs)
    bd = Path(tempfile.mkdtemp())
    (bd / ".aidp/flows/x").mkdir(parents=True)

    def bash_probe(code):
        (bd / ".aidp/flows/x/a.md").write_text("```bash\n%s\n```\n" % code, encoding="utf-8")
        r = subprocess.run([sys.executable, str(repo / ".aidp/scripts/check_flow_bash_syntax.py"),
                            "--root", str(bd), "--json"], capture_output=True, text=True)
        return [f for f in (json.loads(r.stdout).get("findings") or [])
                if f.get("kind") == "placeholder-in-command-position"]

    check("★ 阳性：`ENV=1 <gh workflow run> --ref x` 判违规",
          len(bash_probe('GH_MODE=1 <gh workflow run> --ref "$C"')) == 1)
    check("★ 阴性：参数位 `<...>` 是正常模板，不判（判它会满屏假红）",
          not bash_probe('curl -s "<后端 health 端点>" | jq .'))
    check("★ 阴性：真重定向 / heredoc 不判",
          not bash_probe("sort < in.txt > out.txt") and not bash_probe("cat <<EOF\nx\nEOF"))


def test_fail_handle_freeze_now_and_enum_guard():
    """[64] fail_handle 的两项新能力 + 枚举不可解析时的 fail-closed 边界。"""
    print("\n[64] 失败处置：--freeze-now / --extra / 枚举不可解析")
    repo = Path(__file__).resolve().parents[3]
    fh = repo / ".aidp/scripts/autopilot_fail_handle.py"
    check("★ 脚本存在", fh.is_file())
    if not fh.is_file():
        return

    def run(args, root=None, extra_env=None):
        d = root or Path(tempfile.mkdtemp())
        (d / "memory").mkdir(parents=True, exist_ok=True)
        bl = d / "memory/.sprint-autopilot-baseline.json"
        if not bl.exists():
            bl.write_text('{"versions":{},"autopilot":{"wake_source_this_tick":"1"}}',
                          encoding="utf-8")
        r = subprocess.run([sys.executable, str(fh)] + args + ["--no-card", "--json"],
                           capture_output=True, text=True, cwd=str(d))
        try:
            return r.returncode, json.loads(r.stdout), json.loads(bl.read_text(encoding="utf-8")), r.stderr
        except ValueError:
            return r.returncode, {}, {}, r.stderr

    base = ["--version", "V0.1.0", "--phase", "p", "--why", "w"]

    # --freeze-now：直接冻 + 不写 streak + --extra 与四件套同批
    rc, o, bl, _ = run(base + ["--reason", "stuck-phase", "--freeze-now",
                               "--extra", "unconverged_frozen_head=abc123"])
    v = bl.get("versions", {}).get("V0.1.0", {})
    check("★ --freeze-now 直接冻结（rc=3）", rc == 3 and o.get("frozen") is True)
    check("★ 四件套写齐 + 顶层阻塞值带 @version",
          v.get("needs_human") is True and v.get("aiauto_frozen_at")
          and v.get("freeze_reason") == "stuck-phase"
          and bl.get("aiauto_blocked_reason") == "frozen:stuck-phase@V0.1.0")
    check("★ ⛔ 不写任何 streak（判据不在那里，假计数会误导巡检）",
          not [k for k in v if "streak" in k])
    check("★ --extra 与四件套同批写入（分两次写会留下「冻了但解冻判据缺失」的中间态）",
          v.get("unconverged_frozen_head") == "abc123")

    # 常规路径仍记账、未达阈不冻
    rc, o, bl, _ = run(base + ["--reason", "deploy-unreachable",
                               "--streak-key", "dev_fail_streak", "--threshold", "3"])
    check("★ 阴性对照：常规路径仍 bump streak、未达阈不冻",
          rc == 0 and o.get("streak") == 1
          and bl["versions"]["V0.1.0"].get("needs_human") is None)

    # 枚举解析不到 → 记账照做，但**拒绝写冻结四件套**
    d = Path(tempfile.mkdtemp())
    sc = d / ".aidp/scripts"
    sc.mkdir(parents=True)
    for f in ("autopilot_fail_handle.py", "baseline_edit.py", "aidp_runtime.py"):
        shutil.copy(repo / ".aidp/scripts" / f, sc / f)
    src = (repo / ".aidp/scripts/check_freeze_contract.py").read_text(encoding="utf-8")
    (sc / "check_freeze_contract.py").write_text(
        src.replace("def _parse_enum", "def _renamed_parse_enum"), encoding="utf-8")
    (d / "memory").mkdir(parents=True, exist_ok=True)
    (d / "memory/.sprint-autopilot-baseline.json").write_text(
        '{"versions":{},"autopilot":{"wake_source_this_tick":"0"}}', encoding="utf-8")
    r = subprocess.run([sys.executable, str(sc / "autopilot_fail_handle.py"),
                        "--version", "V9.9.9", "--phase", "p", "--reason", "probe-timeout",
                        "--why", "w", "--no-card", "--json"],
                       capture_output=True, text=True, cwd=str(d))
    o = json.loads(r.stdout)
    bl = json.loads((d / "memory/.sprint-audit.json").read_text(encoding="utf-8")) \
        if (d / "memory/.sprint-audit.json").exists() else \
        json.loads((d / "memory/.sprint-autopilot-baseline.json").read_text(encoding="utf-8"))
    v = bl.get("versions", {}).get("V9.9.9", {})
    check("★ 枚举解析不到 → 仍记账（拒绝记账会制造新的静默停摆）", o.get("streak") == 1)
    check("★ 但**拒绝写冻结四件套** + 显式报错（未经校验的 reason 落不进任何解冻分支 ⇒ 永久冻结）",
          o.get("freeze_suppressed") is True and v.get("needs_human") is None
          and "不写冻结四件套" in (r.stderr or ""))


def test_commonmark_fence_and_env_freshness():
    """[65] 围栏判定按 CommonMark（否则死链恒绿）+ env.tpl 键集漂移可见。"""
    print("\n[65] CommonMark 围栏判定 + env/.env 键集新鲜度")
    repo = Path(__file__).resolve().parents[3]
    ma = repo / ".aidp/scripts/check_md_anchors.py"
    src = ma.read_text(encoding="utf-8")
    check("★ 不再用「见 ``` 就翻转」的朴素 toggle", "in_fence = not in_fence" not in src)
    check("★ 收尾围栏须无 info string 且长度不小于开启（CommonMark）",
          "FENCE_OPEN_RE" in src and "fence_marks" in src)

    d = Path(tempfile.mkdtemp())
    (d / "docs/init").mkdir(parents=True)   # 必须落在 DEFAULT_PATHS 扫描面内
    # 外层 ```markdown 模板里嵌一个 ```bash：朴素 toggle 会以为块已结束、把后面的标题收进 slug
    body = ("# T\n\n- [5. 目标章节](#5-目标章节)\n\n```markdown\n# 模板\n"
            "```bash\necho hi\n```\n## 模板内小节\n```\n\n## 5. 目标章节\n正文\n")
    (d / "docs/init/a.md").write_text(body, encoding="utf-8")
    r = subprocess.run([sys.executable, str(ma), "--root", str(d), "--json"],
                       capture_output=True, text=True)
    o = json.loads(r.stdout)
    check("★ 阳性：破损围栏把真章节吞进代码块 → 目录锚点判死链（旧实现恒绿）",
          len(o.get("broken") or []) == 1)
    (d / "docs/init/a.md").write_text(body.replace("```markdown", "````markdown", 1)
                                      .replace("```\n\n## 5.", "````\n\n## 5.", 1), encoding="utf-8")
    r = subprocess.run([sys.executable, str(ma), "--root", str(d), "--json"],
                       capture_output=True, text=True)
    check("★ 阴性：外层改四反引号后，章节回到块外、锚点有效",
          not (json.loads(r.stdout).get("broken") or []))


def test_defect_triage_and_block_review():
    """[66] 收尾门 3p/3q：缺陷分流完整性 + 上轮 block 复评。

    两条都堵「从未做过」与「做完了」在机器上同形的缺口：
    · 3p —— 一条缺陷都没分流时，3j（auto_fixable_pending 不真）与 3m（报告无"待复验"字样）
      恰好同时静默通过。下游实证：两条缺陷被一句"需要产品决策"笼统盖住报给用户等人，收尾门全绿，
      而其中一条是纯技术缺陷、根本不需要产品输入。
    · 3q —— 每轮测试独立跑，没有任何东西要求它回头看上一轮的 block，于是 block 原样沉淀。
    """
    print("\n[66] 收尾门 3p/3q 缺陷分流 + 上轮 block 复评")
    gate = os.path.join(os.path.dirname(HERE), "autopilot-ceremony-gate.py")

    def scene(defects=(), vnode=None, cur_cases=(), prev_cases=None, retest=False):
        root = Path(tempfile.mkdtemp())
        d = root / "docs/reports/V0.1/AI执行报告/data"
        d.mkdir(parents=True)

        def js(b, cases, defs):
            (d / f"{b}.js").write_text(
                "window.__A__=window.__A__||[];window.__A__.push("
                + json.dumps({"cases": list(cases), "defects": list(defs)},
                             ensure_ascii=False) + ");", encoding="utf-8")
        if prev_cases is not None:
            js("V0.1_build1001", prev_cases, [])
        js("V0.1_build1002", cur_cases, defects)
        (root / "memory").mkdir()
        vn = {"builds": [{"build": "V0.1_build1001"},
                         {"build": "V0.1_build1002",
                          **({"retest_of": "V0.1_build1001"} if retest else {})}]}
        vn.update(vnode or {})
        (root / "memory/.sprint-autopilot-baseline.json").write_text(
            json.dumps({"versions": {"V0.1": vn}}, ensure_ascii=False), encoding="utf-8")
        cp = subprocess.run([sys.executable, gate, "check", "--version", "V0.1",
                             "--build", "V0.1_build1002", "--stage", "final",
                             "--will-browser-test", "1", "--repo-root", str(root),
                             "--notify", "0", "--no-advance-run-state"],
                            capture_output=True, text=True)
        shutil.rmtree(root, ignore_errors=True)
        return cp.stdout + cp.stderr

    D2 = [{"id": "BUG-001", "title": "部门筛选口径不同源"},
          {"id": "BUG-002", "title": "错误态文案"}]

    out = scene(defects=D2)
    check("★ 3p 阳性：两条缺陷一条都没分流 → FAIL（下游实测形态）",
          "一条都没进分流" in out)
    out = scene(defects=D2, vnode={"auto_fixable_pending": True})
    check("3p 阴性：批量归 auto-fix → 放行（闭环交给 3j/3m）",
          "已按批次归入 auto-fix" in out)
    out = scene(defects=D2, vnode={"pending_clarifications": [{"question": "需要产品确认"}]})
    check("★ 3p 阳性：待澄清问句空泛 → FAIL（写不出问句=不需要产品输入）",
          "没写「具体要产品回答什么」" in out)
    out = scene(defects=D2, vnode={"pending_clarifications": [
        {"question": "BUG-001 部门筛选是否应含已停用部门？"},
        {"question": "BUG-002 停用企业的错误态该显示什么文案？"}]})
    check("3p 阴性：问句具体且点名缺陷 → 放行", "均已落到三档之一" in out)
    out = scene(defects=[])
    check("★ 3p 零误报：报告无缺陷时不得恒红", "❌ 缺陷分流完整性" not in out)

    PREV = [{"id": "TC-A-023", "result": "block", "note": "前置不满足"},
            {"id": "TC-A-024", "result": "block", "note": "前置不满足"}]
    out = scene(prev_cases=PREV, cur_cases=[{"id": "TC-A-023", "result": "block",
                                             "note": "结构性不可达"}], retest=True)
    check("★ 3q 阳性：上轮 block 整条在本轮缺席 → FAIL", "完全没出现" in out)
    out = scene(prev_cases=PREV, retest=True,
                cur_cases=[{"id": "TC-A-023", "result": "block", "note": ""},
                           {"id": "TC-A-024", "result": "block", "note": ""}])
    check("★ 3q 阳性：仍判 block 却没写任何理由（原样沉淀）→ FAIL",
          "没写任何理由" in out)
    out = scene(prev_cases=PREV, retest=True,
                cur_cases=[{"id": "TC-A-023", "result": "block", "note": "前置不满足"},
                           {"id": "TC-A-024", "result": "pass", "note": "造数后解锁"}])
    check("3q 边界：理由与上轮逐字相同 → DEGRADE 告警而非阻断（「原因不变」是合法结论）",
          "逐字相同" in out)
    out = scene(prev_cases=PREV, retest=True,
                cur_cases=[{"id": "TC-A-023", "result": "block", "note": "零学习记录课程永远进不了排行"},
                           {"id": "TC-A-024", "result": "pass", "note": "建 2 门课后解锁"}])
    check("3q 阴性：逐条给出新结论 → 放行", "已全部复评" in out)
    out = scene(prev_cases=PREV, cur_cases=[], retest=False)
    check("★ 3q 零误报：非复测轮（无 retest_of）本项整段不出现",
          "上轮 block 复评" not in out)

    out = scene(defects=[], vnode={"current_build": "V0.1_build1002", "builds": [
        {"build": "V0.1_build1002", "driver_actual": "chrome"},
        {"build": "V0.1_build1002", "change_classification": {"x": 1}}]})
    check("★ 3l 扩展阳性：同 build 两条记录 → FAIL（读方只取第一条，后写字段永远不可见）",
          "重复 build 号" in out)


def test_classify_push_accumulates():
    """[67] 同一 build 多次 push 时，「本 build 发过正式代码」这个事实不得被后写覆盖。

    下游实证：build1002 的基线是一次含 2 个 Java 文件的提交，其后一次纯文档 push
    把 change_classification 整个覆盖成 no-formal-code-change / cicd_skipped=true。
    扁平键保持 per-push 语义（Phase 3.6/3.7 刚分类完就读，问的是"这一次要不要等部署"），
    build 级事实另存 build_* 系列，单调不回退。
    """
    print("\n[67] classify_push 同 build 多次推送累积")
    sys.path.insert(0, os.path.dirname(HERE))
    from classify_push import accumulate_push

    node = {}
    accumulate_push(node, {"classified_at": "t1", "formal_code_change": True,
                           "classification_error": False, "cicd_skipped": False,
                           "skip_reason": None, "changed_files": ["A.java", "B.java"],
                           "formal_code_files": ["A.java", "B.java"]})
    accumulate_push(node, {"classified_at": "t2", "formal_code_change": False,
                           "classification_error": False, "cicd_skipped": True,
                           "skip_reason": "no-formal-code-change",
                           "changed_files": ["README.md"], "formal_code_files": []})
    check("★ 阳性：代码 push 后再来一次纯文档 push，build 级事实不被降级",
          node["build_formal_code_change"] is True and node["build_cicd_skipped"] is False)
    check("build 级文件清单取并集、可追溯",
          node["build_formal_code_files"] == ["A.java", "B.java"] and node["push_count"] == 2)

    n2 = {}
    accumulate_push(n2, {"classified_at": "t1", "formal_code_change": False,
                         "classification_error": False, "cicd_skipped": True,
                         "skip_reason": "no-formal-code-change",
                         "changed_files": ["x.md"], "formal_code_files": []})
    check("★ 阴性：全程纯文档的 build 不得被误判成发过代码",
          n2["build_formal_code_change"] is False and n2["build_cicd_skipped"] is True)


def test_residue_variants_and_verdict_line():
    """[68] 口径残留门：短形式派生词表默认就跑 + 末尾必有一行判决。

    下游连续三轮宣布"真残留 0"，实际每轮都还有 10+ 条——因为「ℹ️ 订正留痕 N 处（应当保留）」
    很醒目且先于残留清单打印，看的人以为看完了。另有词表单一漏检：`--old 课程截止时间` 得 0 处，
    而 `--old 截止时间` 得 13 处含 1 条 Critical，而"补宽词表再跑"只是处置清单里的一句文字建议，
    连续三轮都被跳过。
    """
    print("\n[68] 口径残留门 短形式词表 + 判决行")
    sc = os.path.join(os.path.dirname(HERE), "check_cascade_residue.py")
    root = Path(tempfile.mkdtemp())
    d = root / "docs/design/detail/V0.1"
    d.mkdir(parents=True)
    (d / "01_设计.md").write_text(
        "# 设计\n\n## 事实清单\n\n- `getDeadline()` 按截止时间过滤（现状）\n", encoding="utf-8")

    def run(*extra):
        cp = subprocess.run([sys.executable, sc, "--root", str(root), "--version", "V0.1",
                             "--scope", "design", "--old", "课程截止时间", *extra],
                            capture_output=True, text=True)
        return cp.returncode, cp.stdout + cp.stderr

    rc, out = run()
    check("★ 阳性：原词 0 命中，短形式默认就跑并捞出漏检行",
          "短形式词表额外命中" in out and "截止时间过滤" in out)
    check("派生命中不计入退出码（派生是启发式，不做假红）", rc == 0)
    rc2, out2 = run("--no-derive-variants")
    check("★ 阴性：--no-derive-variants 还原旧行为，那一行彻底不出现",
          "短形式" not in out2 and "截止时间过滤" not in out2)
    rc3, out3 = run("--json")
    j = json.loads(out3)
    check("--json 顶层 has_real_residue 可直接判（不必去数并列字段）",
          j["has_real_residue"] is False and len(j["variant_residues"]) == 1)

    (d / "01_设计.md").write_text("# 设计\n\n本版取消课程截止时间字段。\n", encoding="utf-8")
    rc4, out4 = run()
    check("★ 判决行必须是输出的最后一行（否则被「订正留痕」段滚过去）",
          rc4 == 2 and (out4.rstrip().splitlines()[-1]).startswith("⛔ 仍有"))
    shutil.rmtree(root, ignore_errors=True)

    from importlib import util as _u
    spec = _u.spec_from_file_location("cr", sc)
    m = _u.module_from_spec(spec)
    spec.loader.exec_module(m)
    check("中文复合词只丢前 1~3 字（限定词长度），不产生碎片",
          m.derive_variants(["课程截止时间"]) == ["程截止时间", "截止时间", "止时间"])
    check("★ 带分隔符的词组只按词切，⛔ 不逐字符切（否则全是噪声派生词）",
          m.derive_variants(["course due date"]) == ["due date", "date"])


def test_exec_report_inherits_cases():
    """[69] AI执行报告的 cases[] / testSummary 从同 build 的测试报告继承。

    收尾门 3n（约定 33）读的是 exec 报告的 cases[]，而 exec 字段契约从未声明这个字段——
    典型的有读无写：finalize 不传就被判「基线有 N 条、报告一个 id 都没有」，
    而执行体翻遍 exec 契约找不到该填哪里。
    """
    print("\n[69] exec 报告继承 cases[]/testSummary")
    from importlib import util as _u
    er_path = os.path.join(os.path.dirname(HERE), "emit-report.py")
    spec = _u.spec_from_file_location("er", er_path)
    er = _u.module_from_spec(spec)
    spec.loader.exec_module(er)

    root = Path(tempfile.mkdtemp())
    rr = root / "docs/reports"
    (rr / "V0.1/AI测试报告/data").mkdir(parents=True)
    (rr / "V0.1/AI测试报告/data/V0.1_build1001.js").write_text(
        "window.__T__=window.__T__||[];window.__T__.push(" + json.dumps({
            "summary": {"total": 2, "pass": 2, "fail": 0, "passRate": 1.0},
            "cases": [{"id": "TC-A-1", "result": "pass"}, {"id": "TC-A-2", "result": "pass"}],
        }, ensure_ascii=False) + ");", encoding="utf-8")

    pl = {"overview": {}, "steps": [], "features": []}
    got = er.inherit_test_facts(pl, str(rr), "V0.1", "V0.1_build1001")
    check("★ 阳性：exec 未传 cases/testSummary → 从同 build 测试报告继承",
          bool(got) and [c["id"] for c in pl["cases"]] == ["TC-A-1", "TC-A-2"]
          and pl["testSummary"]["total"] == 2)

    pl2 = {"cases": [{"id": "TC-ZZZ"}], "testSummary": {"total": 9}}
    check("★ 阴性：显式传入优先，绝不被继承值覆盖",
          er.inherit_test_facts(pl2, str(rr), "V0.1", "V0.1_build1001") is None
          and pl2["cases"][0]["id"] == "TC-ZZZ")

    pl3 = {"overview": {}}
    check("★ 阴性：无同 build 测试报告时不编造（取不到就不填）",
          er.inherit_test_facts(pl3, str(rr), "V0.1", "V0.1_build9999") is None
          and "cases" not in pl3)
    shutil.rmtree(root, ignore_errors=True)

    rd = (Path(__file__).resolve().parents[3]
          / ".aidp/templates/reports/README.md").read_text(encoding="utf-8")
    check("★ exec 契约里 cases[] 有名有姓（有读必须有写）",
          "inherited_from_test_report" in rd)


def test_card_section_file_and_render_scope():
    """[70] notify --section-file 绕开 shell 命令替换 + 渲染冒烟排除 code/pre。

    前者：卡片正文写反引号包裹的代码标识时，bash 当命令替换执行，卡片内容**静默缺失**
    （内容没了、命令却成功返回）。后者：缺陷描述里讲 `Number(null)` 成因必然要写到
    undefined 这个词，整页 grep 会判 FAIL，逼作者把技术术语改写成中文才能过门。
    """
    print("\n[70] notify --section-file + 渲染冒烟检测面")
    cs = os.path.join(os.path.dirname(HERE), "notify.py")
    repo = Path(__file__).resolve().parents[3]
    d = Path(tempfile.mkdtemp())
    (d / "sec.txt").write_text("**字段：** `duration: null`　|　**状态：** ✅", encoding="utf-8")
    cp = subprocess.run([sys.executable, cs, "--title", "冒烟", "--section-file",
                         str(d / "sec.txt"), "--print-only", "--repo-root", str(repo)],
                        capture_output=True, text=True)
    check("★ 阳性：含反引号的正文经 --section-file 完整保留",
          "duration: null" in cp.stdout)
    cp2 = subprocess.run(["bash", "-c",
                          f'python3 {cs} --title 冒烟 --section "**字段：** `duration: null`" '
                          f'--print-only --repo-root {repo}'], capture_output=True, text=True)
    check("★ 阴性对照：同样内容走 --section 时 bash 吃掉反引号（内容静默缺失）",
          "duration: null" not in cp2.stdout)
    cp3 = subprocess.run([sys.executable, cs, "--title", "冒烟", "--section-file",
                          "/nope/x.txt", "--print-only", "--repo-root", str(repo)],
                         capture_output=True, text=True)
    check("读不到 section 文件 → fail-closed，不发缺小节的卡", cp3.returncode == 2)
    shutil.rmtree(d, ignore_errors=True)

    js = (repo / ".aidp/scripts/report_render_smoke.js").read_text(encoding="utf-8")
    check("★ undefined/NaN 的检测面剔除 <code>/<pre>（描述文本 ≠ 渲染故障）",
          "scanHtml" in js and "<\\/code>" in js.replace("\\/", "\\/")
          and "const undefinedCount = (scanHtml.match" in js)
    check("★ 三项判据统一走剔除后的文本（漏一项就是半截修复）",
          js.count("scanHtml.match") == 3)

def test_autopilot_reset():
    """[72] `--reset-*` 旗标的执行器三侧对照。

    这些旗标长期只存在于参数表与冻结 #4 通知正文里、没有任何实现（`BOOL_FLAGS` 一个都没登记），
    用户照通知跑的是空气。本测覆盖它们落地后的三条路径，并锁死两处易退化的细节：
    `--reset-baseline` 必须**整份删文件**（清成 `{}` 会让各处「baseline 不存在」的早退分支失效），
    `--reset-unattended` 必须**成对清掉确认键**（只清一个会让下一轮误判「已被人确认过」）。
    """
    print("\n[72] --reset-* 旗标执行器")
    repo = Path(__file__).resolve().parents[3]
    sc = str(repo / ".aidp/scripts/autopilot_reset.py")
    seed = ('{"autopilot":{"unattended_confirmed":true,"unattended_confirmed_at":"t","keep":1},'
            '"notify_enabled":false,"versions":{"V1":{}}}')
    brel = "memory/.sprint-autopilot-baseline.json"

    def _mk():
        d = Path(tempfile.mkdtemp())
        (d / "memory").mkdir()
        (d / brel).write_text(seed, encoding="utf-8")
        return d

    def _run_reset(d, arg):
        return subprocess.run([sys.executable, sc, "--arguments=" + arg],
                              capture_output=True, text=True, cwd=str(d))

    # ① 未命中任何 reset → rc=0，baseline 一个字节不动
    d = _mk()
    cp = _run_reset(d, "--unattended")
    check("无 reset 旗标 → rc=0", cp.returncode == 0)
    check("无 reset 旗标 → baseline 原样不动",
          (d / brel).read_text(encoding="utf-8") == seed)

    # ② --reset-unattended → rc=11，确认键成对清掉，其余键保留
    d = _mk()
    cp = _run_reset(d, "--unattended --reset-unattended")
    check("--reset-unattended → rc=11（已重置、继续本 tick）", cp.returncode == 11)
    left = json.loads((d / brel).read_text(encoding="utf-8"))
    ap_node = left.get("autopilot") or {}
    check("--reset-unattended → 确认键成对清空（⛔ 不能只清一个）",
          "unattended_confirmed" not in ap_node and "unattended_confirmed_at" not in ap_node)
    check("--reset-unattended → 不相干的键必须保留",
          ap_node.get("keep") == 1 and "notify_enabled" in left and "versions" in left)

    # ③ --reset-baseline → rc=10 且**文件被删除**（⛔ 不是清成 {}）
    d = _mk()
    cp = _run_reset(d, "--reset-baseline")
    check("--reset-baseline → rc=10（应结束本 tick）", cp.returncode == 10)
    check("--reset-baseline → 整份删除文件，⛔ 不留空壳 {}", not (d / brel).exists())


def test_design_goal_formal_landings():
    """[71] 语义维度 4 查出的两条「形式落地」：目标写着、实现走不到。

    · G-CHAIN-1 —— 裸委派 `/sprint-aiauto-test` 让被调侧判出 LOOP_UNATTENDED=0、
      在 tick 内退化成交互式挂死；而守卫的候选正则要求带参，裸调用连候选都不是 ⇒ 报绿。
    · G-CHAIN-2 —— 三处 `git push` 无错误捕获（围栏也无 set -e），失败后照跑探针、
      拿着从未推出去的 commit 宣告"发布完成"；Step 3.4.4 的入场前提无人产生 ⇒ 整片不可达。
    """
    print("\n[71] 设计目标三条形式落地的收口")
    repo = Path(__file__).resolve().parents[3]

    # —— G-CHAIN-1：守卫必须看得见裸委派 ——
    sc = str(repo / ".aidp/scripts/check_chain_unattended.py")
    d = Path(tempfile.mkdtemp())
    (d / ".aidp/flows/demo").mkdir(parents=True)
    (d / ".aidp/commands").mkdir(parents=True)
    (d / ".aidp/commands/sprint-aiauto-test.md").write_text(
        "# x\n`--unattended` 声明\n", encoding="utf-8")

    def chain(text):
        (d / ".aidp/flows/demo/step.md").write_text(text, encoding="utf-8")
        cp = subprocess.run([sys.executable, sc, "--root", str(d)],
                            capture_output=True, text=True)
        return cp.stdout + cp.stderr

    out = chain("仅当自检通过后，才 invoke `/sprint-aiauto-test` 跑浏览器实测。\n")
    check("★ G-CHAIN-1 阳性：裸委派被检出（旧实现连候选都不是 → 假绿）",
          "裸委派" in out)
    out = chain("仅当自检通过后，才 invoke `/sprint-aiauto-test [--no-loop]` 跑浏览器实测。\n")
    check("★ G-CHAIN-1 阴性：带 [--no-loop] 走【显式判定】放行（不是靠正则不匹配逃掉）",
          "裸委派" not in out)
    out = chain("⛔ **严禁**：识别到只跑测试就直接 invoke `/sprint-aiauto-test`、跳过骨架。\n")
    check("★ G-CHAIN-1 零误报：否定句里的命令名不是调用点", "裸委派" not in out)
    shutil.rmtree(d, ignore_errors=True)

    r7 = (repo / ".aidp/flows/version/release-7.md").read_text(encoding="utf-8")
    check("★ G-CHAIN-2：三处 push 逐个捕获 rc 并落 PUSH_FAILED",
          r7.count("PUSH_FAILED") >= 4 and 'PUSH_FAILED="commit"' in r7)
    check("★ G-CHAIN-2：失败即阻断并指向 Step 3.4.4（否则 release-7c 整片不可达）",
          "release-7c.md" in r7 and "推送失败" in r7)
    check("★ G-CHAIN-2 边界：tag/branch 用 if 而非 `[ -n ] && push`（空值不得误判成失败）",
          'if [ -n "$TAG_NAME" ]; then' in r7 and 'if [ -n "$BRANCH_NAME" ]; then' in r7)
    flow = (repo / ".aidp/flows/sprint-aiauto-test/phase-3-3b.md").read_text(encoding="utf-8")
    branch = flow.split('if [ "$STREAK" -lt "$FREEZE_AT" ]; then', 1)[1].split("  fi", 1)[0]
    check("未冻结分支 exit 0 前调用 notify.py --node #R",
          'notify.py --node "#R"' in branch
          and branch.index('notify.py --node "#R"') < branch.index("exit 0"))


if __name__ == "__main__":
    sys.exit(main())
