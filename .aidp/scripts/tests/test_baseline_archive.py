#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baseline 归档 + autopilot_decisions 双信源合并 的确定性单测（stdlib only，零依赖）。

直接跑：`python3 .aidp/scripts/tests/test_baseline_archive.py`（cwd 必须是仓库根）。

覆盖三个脚本，回归点各不相同：

  · `baseline_archive.py`         —— **归档不能让读方取空**。最危险的失败不是报错，
                                     而是整段删掉 `versions.<V>` 后，一个早已 tag 发布的
                                     版本因 `internal_released_at` 读空而重新命中
                                     Phase 0.3.3 的 S2 判据、被当作准发布候选再跑一遍。
                                     故这里有一条**显式反例对照**：同一份数据，
                                     「整段删」会让 S2 谓词成真，「墓碑」不会。
  · `baseline_edit.py` 的归档回落 —— 主文件取不到要能从归档文件读回；⛔ 但"build 压根
                                     没铸出来"的 exit 2 不能被回落吞成"取到空、exit 0"。
  · `autopilot_decisions_merge.py`—— 两处声明冲突时 **PRD frontmatter 赢**，且**必须出声**；
                                     静默取胜正是陈旧兜底副本能长期无人发现的原因。
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SCRIPTS))
sys.path.insert(0, SCRIPTS)

import baseline_archive as BA  # noqa: E402

ARCHIVE = os.path.join(SCRIPTS, "baseline_archive.py")
EDIT = os.path.join(SCRIPTS, "baseline_edit.py")
MERGE = os.path.join(SCRIPTS, "autopilot_decisions_merge.py")

_passed = _failed = 0


def check(name, cond):
    global _passed, _failed
    if cond:
        _passed += 1
    else:
        _failed += 1
        print("  ❌ FAIL: %s" % name)


def run(args, cwd):
    return subprocess.run([sys.executable] + args, cwd=cwd, capture_output=True, text=True)


# ───────────────────────────── 夹具 ─────────────────────────────

def _version_node(v, released, builds=3):
    node = {
        "state": "S4" if released else "S1",
        "source": "autopilot",
        "phase_beta_done_at": "2026-01-01T10:00:00+08:00",
        "last_deployed_at": "2026-01-01T11:00:00+08:00",
        "deployment_mode": "cloud",
        "aiauto_tested_at": "2026-01-01T12:00:00+08:00",
        "build_seq": 1000,
        "current_build": "%s_build1000" % v,
        "release_tag_name": "v" + v[1:],
        "run_state": {"current_phase": "3.4", "next_phase": "done", "pending_actions": []},
        "req_scale": {"tier": "M", "req_count": 12},
        "auto_fixable_pending": False,
        "builds": [{"build": "%s_build%d" % (v, 1000 + k), "status": "tested",
                    "pass_rate": 0.95, "notes": "x" * 200} for k in range(builds)],
    }
    if released:
        node["internal_released_at"] = "2026-01-02T10:00:00+08:00"
    return node


def _mkbaseline(versions):
    """versions = [(版本号, 是否已准发布归档), …]，返回临时项目根。"""
    root = Path(tempfile.mkdtemp(prefix="aidp-baseline-test-"))
    (root / "memory").mkdir()
    data = {"versions": {v: _version_node(v, rel) for v, rel in versions},
            "aiauto_test_heartbeat_at": "2026-09-14T00:00:00+08:00"}
    (root / "memory" / ".sprint-autopilot-baseline.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return root


def _load(root):
    return json.loads((root / "memory" / ".sprint-autopilot-baseline.json")
                      .read_text(encoding="utf-8"))


# ───────────────────── ① 归档范围 + 幂等 + dry-run ─────────────────────

def test_archive_scope_and_idempotency():
    print("【baseline 归档：范围 / dry-run / 幂等】")
    root = _mkbaseline([("V0.8.0", True), ("V0.9.0", True), ("V0.10.0", True),
                        ("V0.14.0", True), ("V0.15.0", False)])
    base = "memory/.sprint-autopilot-baseline.json"

    # 阴性①：默认要求 git tag，夹具不是 git 仓库 → 一个都不搬（fail-closed）
    r = run([ARCHIVE, "--baseline", base, "--root", ".", "--json"], root)
    out = json.loads(r.stdout)
    check("★ 非 Git 默认 tag 约束明确 unsupported", r.returncode == 3 and
          out == {"status": "unsupported", "reason": "vcs-disabled", "capability": "tag"})
    check("  阴性时主文件一字未动", "builds" in _load(root)["versions"]["V0.8.0"])

    # 阴性②：dry-run 只报不写
    r = run([ARCHIVE, "--baseline", base, "--no-require-tag", "--dry-run", "--json"], root)
    out = json.loads(r.stdout)
    check("dry-run 列出 3 个待归档（V0.8.0/V0.9.0/V0.10.0）", len(out["archived"]) == 3)
    check("★ dry-run 不写盘：主文件仍有 builds",
          "builds" in _load(root)["versions"]["V0.8.0"])
    check("★ dry-run 不建归档目录", not (root / "memory" / ".aidp-baseline-archive").exists())

    # 阳性：真跑
    r = run([ARCHIVE, "--baseline", base, "--no-require-tag", "--json"], root)
    out = json.loads(r.stdout)
    names = sorted(x["version"] for x in out["archived"])
    check("★ 阳性：归档 V0.8.0/V0.9.0/V0.10.0", names == ["V0.10.0", "V0.8.0", "V0.9.0"])
    data = _load(root)
    check("★ --keep 2：最近两版（V0.14.0 / V0.15.0）明细原样保留",
          "builds" in data["versions"]["V0.14.0"] and "builds" in data["versions"]["V0.15.0"])
    check("★ 未发布版（无 internal_released_at）不会被搬",
          "builds" in data["versions"]["V0.15.0"])
    check("主文件确实变小", out["bytes_after"] < out["bytes_before"])
    arch = root / "memory" / ".aidp-baseline-archive" / "baseline-V0.8.0.json"
    check("归档文件已生成", arch.is_file())
    payload = json.loads(arch.read_text(encoding="utf-8"))
    check("★ 归档文件承载完整节点（builds 明细一条不少）",
          len(payload["node"]["builds"]) == 3 and payload["node"]["req_scale"]["tier"] == "M")

    # 幂等：再跑一次不动任何东西，尤其不能拿墓碑覆盖已有归档
    before = arch.read_text(encoding="utf-8")
    r2 = run([ARCHIVE, "--baseline", base, "--no-require-tag", "--json"], root)
    out2 = json.loads(r2.stdout)
    check("★ 幂等：第二次无可归档", out2["archived"] == [])
    check("★ 幂等：归档文件未被墓碑覆盖", arch.read_text(encoding="utf-8") == before)
    check("跳过原因如实标 already-archived",
          any(s["reason"] == "already-archived" for s in out2["skipped"]))

    # --keep 0 必须被拒（准发布要读上一版）
    r3 = run([ARCHIVE, "--baseline", base, "--keep", "0"], root)
    check("★ --keep 0 被拒（退出码 2）", r3.returncode == 2)


# ───────────────────── ② 墓碑 vs 整段删（状态机反例对照）─────────────────────

def test_tombstone_keeps_state_machine_predicates():
    print("【墓碑必须保住状态机判据（整段删的反例对照）】")
    root = _mkbaseline([("V0.8.0", True), ("V0.9.0", True), ("V0.14.0", True),
                        ("V0.15.0", False)])
    base = "memory/.sprint-autopilot-baseline.json"
    run([ARCHIVE, "--baseline", base, "--no-require-tag"], root)
    tomb = _load(root)["versions"]["V0.8.0"]

    # Phase 0.3.3 的 S2 判据（简化到 baseline 这一半）：internal_released_at 为空 → 命中 S2
    def s2_hits(node):
        return not (node or {}).get("internal_released_at")

    check("★ 墓碑保住 internal_released_at ⇒ 不会重新命中 S2", not s2_hits(tomb))
    check("★ 反例：整段删节点 ⇒ S2 谓词成真（这正是不能删的原因）", s2_hits({}))

    for k in ("phase_beta_done_at", "source", "last_deployed_at", "deployment_mode",
              "aiauto_tested_at", "current_build", "build_seq", "release_tag_name"):
        check("墓碑保留 %s（有确定读方）" % k, k in tomb)
    check("墓碑标记齐备", tomb.get("archived") is True and tomb.get("archive_file"))
    check("★ bulk 确已搬走（builds / req_scale 不在主文件）",
          "builds" not in tomb and "req_scale" not in tomb)
    # 已发布版本读空 run_state / auto_fixable_pending 是**期望行为**：
    # 0.3.4 靠这两个字段「不论 S 态优先作 TARGET」，已发布版不该再被选中。
    check("★ run_state / auto_fixable_pending 刻意不保留",
          "run_state" not in tomb and "auto_fixable_pending" not in tomb)

    # jq 直读面（无回落）：被归档版本的 KEEP 字段必须仍能直读到
    raw = _load(root)
    check("★ jq 直读面：已归档版本的 internal_released_at 仍非空",
          all(raw["versions"][v].get("internal_released_at")
              for v in ("V0.8.0", "V0.9.0")))


# ───────────────────── ③ baseline_edit 的归档回落 ─────────────────────

def test_baseline_edit_archive_fallback():
    print("【baseline_edit get 的归档回落】")
    root = _mkbaseline([("V0.8.0", True), ("V0.14.0", True), ("V0.15.0", False)])
    base = "memory/.sprint-autopilot-baseline.json"
    run([ARCHIVE, "--baseline", base, "--no-require-tag"], root)

    def get(*args):
        return run([EDIT, "--baseline", base] + list(args), root)

    r = get("--version", "V0.8.0", "get", "internal_released_at")
    check("墓碑字段直读命中", r.stdout.strip().startswith("2026-"))

    r = get("--version", "V0.8.0", "get", "req_scale.tier")
    check("★ 已搬走的字段经归档回落读回 M", r.stdout.strip() == "M" and r.returncode == 0)

    r = get("--version", "V0.8.0", "get", "run_state.next_phase")
    check("★ 嵌套路径回落（run_state.next_phase=done）", r.stdout.strip() == "done")

    r = get("--version", "V0.8.0", "--build", "V0.8.0_build1001", "get", "pass_rate")
    check("★ --build 形态同样回落", r.stdout.strip() == "0.95" and r.returncode == 0)

    # ⛔ 回归保护：回落不得把"build 还没铸出来"吞成 exit 0
    r = get("--version", "V0.14.0", "--build", "NOPE", "get", "pass_rate")
    check("★ 未归档版本的不存在 build 仍 exit 2", r.returncode == 2)
    r = get("--version", "V0.8.0", "--build", "NOPE", "get", "pass_rate")
    check("★ 已归档版本的不存在 build 也仍 exit 2", r.returncode == 2)

    # 归档文件缺失（如只 clone 了主文件）→ 回默认值、不崩
    (root / "memory" / ".aidp-baseline-archive" / "baseline-V0.8.0.json").unlink()
    r = get("--version", "V0.8.0", "get", "req_scale.tier", "--default", "NA")
    check("★ 归档文件缺失 → 回默认值且 exit 0（不崩）",
          r.returncode == 0 and r.stdout.strip() == "NA")

    # 选版单一信源不受归档影响
    r = get("current-version")
    check("★ current-version 仍选出唯一未准发布版 V0.15.0", r.stdout.strip() == "V0.15.0")

    # 写已归档版本 → 出声告警但不阻断
    r = get("--version", "V0.8.0", "set", "foo", "bar")
    check("★ 写已归档版本：rc=0 且 stderr 有告警",
          r.returncode == 0 and "已归档" in r.stderr)
    r = get("--version", "V0.14.0", "set", "foo", "bar")
    check("  未归档版本写入不产生该告警", "已归档" not in r.stderr)


# ───────────────────── ④ 归档范围的纯函数判据 ─────────────────────

def test_plan_and_tag_matching():
    print("【归档范围判据（纯函数）】")
    versions = {v: _version_node(v, True) for v in
                ("V0.8.0", "V0.9.0", "V0.10.0", "V0.11.1", "V0.14.0", "V0.15.0")}
    todo, skipped = BA.plan(versions, keep=2, tags=set(), require_tag=False)
    check("★ SemVer 排序不按字典序（V0.10.0 比 V0.9.0 新 ⇒ 不在保留位）",
          "V0.9.0" in todo and "V0.15.0" not in todo and "V0.14.0" not in todo)
    check("保留位标 recent-*", any(s["reason"].startswith("recent-") for s in skipped))

    tags = {"v0.8.0", "V0.9.0"}
    todo2, skipped2 = BA.plan(versions, keep=2, tags=tags, require_tag=True)
    check("★ require_tag：小写 v 与大写 V 两种 tag 都认",
          sorted(todo2) == ["V0.8.0", "V0.9.0"])
    check("无 tag 的标 no-git-tag",
          any(s["version"] == "V0.10.0" and s["reason"] == "no-git-tag" for s in skipped2))
    check("has_tag 对无关 tag 不误命中", not BA.has_tag("V0.8.0", {"v0.8.1", "foo"}))
    check("is_tombstone 认墓碑", BA.is_tombstone(
        {"internal_released_at": "x", "archived": True, "archive_file": "y"}))
    check("is_tombstone 不误判完整节点", not BA.is_tombstone(versions["V0.8.0"]))


# ───────────────────── ⑤ autopilot_decisions 双信源 ─────────────────────

def _mkdecisions(prd_body, fallback_body=None, prd_mtime=1_780_000_000,
                 fb_mtime=1_770_000_000):
    root = Path(tempfile.mkdtemp(prefix="aidp-decisions-test-"))
    d = root / "docs" / "requirements" / "V0.2.0" / "产品提供"
    d.mkdir(parents=True)
    p = d / "PRD-订单.md"
    p.write_text(prd_body, encoding="utf-8")
    os.utime(p, (prd_mtime, prd_mtime))
    if fallback_body is not None:
        (root / "memory").mkdir(exist_ok=True)
        f = root / "memory" / "aidp-config.yaml"
        f.write_text(fallback_body, encoding="utf-8")
        os.utime(f, (fb_mtime, fb_mtime))
    return root


PRD_BODY = """---
autopilot_decisions:
  visual_baseline: prototype-only
  test_strategy: chrome-mcp
  third_party_mocked:
    - vendor: 银行代扣
      api: /api/bank/deduct
  deployment:
    mode: cloud
    cloud_deploy_url: "https://uat.example.com"
---

# PRD 正文
"""

FB_CONFLICT = """autopilot_decisions:
  visual_baseline: prototype-only
  test_strategy: static-only     # 陈旧
  mock_position: backend
  deployment:
    mode: local
"""


def test_decisions_prd_wins_and_is_loud():
    print("【autopilot_decisions：PRD 优先 + 冲突必须出声】")
    root = _mkdecisions(PRD_BODY, FB_CONFLICT)

    r = run([MERGE, "--root", str(root), "--version", "V0.2.0", "--json"], REPO)
    res = json.loads(r.stdout)
    merged = res["merged"]
    check("★ 冲突字段取 PRD（test_strategy=chrome-mcp）",
          merged["test_strategy"] == "chrome-mcp")
    check("★ 嵌套冲突字段也取 PRD（deployment.mode=cloud）",
          merged["deployment"]["mode"] == "cloud")
    check("兜底独有字段仍合并进来（mock_position=backend）",
          merged["mock_position"] == "backend")
    check("PRD 独有的嵌套字段保留",
          merged["deployment"]["cloud_deploy_url"] == "https://uat.example.com")
    check("列表型字段解析正确",
          merged["third_party_mocked"][0]["vendor"] == "银行代扣")
    paths = {c["path"] for c in res["conflicts"]}
    check("★ 冲突逐条列出（test_strategy / deployment.mode）",
          paths == {"test_strategy", "deployment.mode"})
    check("★ 冲突必须出声（stderr 含 decisions-conflict）",
          "decisions-conflict" in r.stderr)
    check("每条冲突都标明赢家是 prd",
          all(c["winner"] == "prd" for c in res["conflicts"]))

    # --check：陈旧 + 冲突 → exit 1 + 删除建议
    r = run([MERGE, "--root", str(root), "--version", "V0.2.0", "--check"], REPO)
    check("★ 阳性：陈旧兜底副本 --check 退出码 1", r.returncode == 1)
    check("★ 给出整段清空建议", "整段清空" in r.stderr)

    check("★ stats 给出 冲突/一致/单边 三项计数（对齐下游对账口径）",
          res["stats"] == {"conflict": 2, "agree": 1, "prd_only": 2, "fallback_only": 1})
    check("★ 清理建议可直接执行（含整段清空 + 只删冲突字段两条路）",
          "整段清空" in r.stderr and "只留单边字段" in r.stderr)

    # --get 取单值
    r = run([MERGE, "--root", str(root), "--version", "V0.2.0",
             "--get", "deployment.mode"], REPO)
    check("--get 打印合并后的值", r.stdout.strip() == "cloud")

    # 兜底副本**更新**但仍冲突 → verdict=conflict，同样 exit 1 + 同样给清理建议。
    # ⛔ 判据是"有没有冲突"，不是"谁更新"：新写进去的错值一样会让实际行为出错。
    root2 = _mkdecisions(PRD_BODY, FB_CONFLICT,
                         prd_mtime=1_770_000_000, fb_mtime=1_780_000_000)
    r = run([MERGE, "--root", str(root2), "--version", "V0.2.0", "--json"], REPO)
    res2 = json.loads(r.stdout)
    check("★ 兜底更新但冲突 → verdict=conflict（不是 stale-fallback）",
          res2["verdict"] == "conflict" and res2["fallback_older_than_prd"] is False)
    check("  冲突字段依旧取 PRD", res2["merged"]["deployment"]["mode"] == "cloud")
    r = run([MERGE, "--root", str(root2), "--version", "V0.2.0", "--check"], REPO)
    check("★ 阳性：conflict 分支 --check 也退出码 1", r.returncode == 1)
    check("  conflict 分支同样给出可执行清理建议", "整段清空" in r.stderr)


def test_decisions_negative_controls():
    print("【autopilot_decisions：阴性对照（不误报）】")
    # 阴性①：根本没有兜底副本
    root = _mkdecisions(PRD_BODY, None)
    r = run([MERGE, "--root", str(root), "--version", "V0.2.0", "--check"], REPO)
    check("★ 阴性：无兜底副本 → exit 0 且零告警",
          r.returncode == 0 and "decisions-conflict" not in r.stderr)

    # 阴性②：兜底副本更旧、但与 PRD 无冲突 → 只记 INFO，不判 stale
    root2 = _mkdecisions(PRD_BODY, "autopilot_decisions:\n  mock_position: backend\n")
    r = run([MERGE, "--root", str(root2), "--version", "V0.2.0", "--json"], REPO)
    res = json.loads(r.stdout)
    check("★ 阴性：只旧不冲突 → verdict=older-no-conflict（不判 stale）",
          res["verdict"] == "older-no-conflict" and res["conflicts"] == [])
    r = run([MERGE, "--root", str(root2), "--version", "V0.2.0", "--check"], REPO)
    check("  只旧不冲突 --check 仍 exit 0（不制造噪音）", r.returncode == 0)

    # 阴性③：两处都不存在 → exit 2（响亮失败，而不是"合并出空"）
    root3 = Path(tempfile.mkdtemp(prefix="aidp-decisions-empty-"))
    r = run([MERGE, "--root", str(root3), "--version", "V0.2.0"], REPO)
    check("★ 两处都不存在 → exit 2（不静默返回空）", r.returncode == 2)


def main():
    # ★ 新增 test_* 必须登记到这里，否则定义了也不会跑。
    test_archive_scope_and_idempotency()
    test_tombstone_keeps_state_machine_predicates()
    test_baseline_edit_archive_fallback()
    test_plan_and_tag_matching()
    test_decisions_prd_wins_and_is_loud()
    test_decisions_negative_controls()
    print("\n%d passed, %d failed" % (_passed, _failed))
    return 1 if _failed else 0


if __name__ == "__main__":
    sys.exit(main())
