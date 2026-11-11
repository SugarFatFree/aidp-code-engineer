#!/usr/bin/env python3
"""Sprint 改动前基线 `baseline_ref` 的确定性解析（供 /sprint-test 传给 code-verification-loop）。

resolve --root . [--card-ref REF] [--passthrough REF] [--sprint-uncommitted] [--main-branch B] [--json]
  按序取到即停；每个候选都必须是本仓库可读的 commit 且为 HEAD 的祖先：
    ① --card-ref        契约卡 / activeContext 保存的改动前基线 ref
    ② --passthrough     上游编排（/sprint-full 等）透传的起点 commit
    ③ --sprint-uncommitted  调用方声明「本 Sprint 改动全部仍在工作区未提交」，且工作区确有未提交改动 → HEAD
    ④ merge-base HEAD <主干分支>，仅当结果 ≠ HEAD 才有效（主干开发时恒等于 HEAD，会把本次改动吞成存量）
    ⑤ 以上皆不成立 → baseline_ref = none
  非 Git 仓库直接 none + unsupported:vcs-disabled。⛔ 永不使用 HEAD~1，也不猜 commit。
输出：{baseline_ref, source, reason, vcs_mode, unverified_label}；退出码 0 = 取到，3 = 取不到（none），2 = 入参错误。
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from vcs import detect_mode


def _git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, check=False)


def _commit(root, ref):
    """ref → 完整 SHA；选项形态、解析不到、非 commit 一律 None。"""
    if not ref or ref.startswith("-"):
        return None
    r = _git(root, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def _valid_start(root, ref):
    sha = _commit(root, ref)
    if sha and _git(root, "merge-base", "--is-ancestor", sha, "HEAD").returncode == 0:
        return sha
    return None


def _main_branch(root, given):
    if given:
        return given
    for name in ("main", "master", "trunk"):
        if _commit(root, name):
            return name
    return None


def resolve(root, card_ref=None, passthrough=None, sprint_uncommitted=False, main_branch=None):
    mode = detect_mode(root)
    base = {"vcs_mode": mode}
    if mode != "git":
        return {**base, "baseline_ref": "none", "source": "none", "reason": "非 Git 仓库，无可检出的改动前代码",
                "unverified_label": "unsupported:vcs-disabled"}
    notes = []
    for source, ref in (("contract-card", card_ref), ("passthrough", passthrough)):
        if ref is None:
            continue
        sha = _valid_start(root, ref)
        if sha:
            return {**base, "baseline_ref": sha, "source": source, "reason": "", "unverified_label": ""}
        notes.append(f"{source} 候选无效（非 commit 或不是 HEAD 祖先）：{ref}")
    head = _commit(root, "HEAD")
    if sprint_uncommitted:
        dirty = _git(root, "status", "--porcelain", "--untracked-files=all").stdout.strip()
        if head and dirty:
            return {**base, "baseline_ref": head, "source": "worktree-only-HEAD", "reason": "",
                    "unverified_label": ""}
        notes.append("声明改动均未提交，但工作区干净或无 HEAD，声明不成立")
    trunk = _main_branch(root, main_branch)
    if trunk:
        mb = _git(root, "merge-base", "HEAD", trunk)
        sha = mb.stdout.strip() if mb.returncode == 0 else ""
        if sha and sha != head:
            return {**base, "baseline_ref": sha, "source": "merge-base", "reason": "", "unverified_label": ""}
        notes.append(f"merge-base HEAD {trunk} 为空或等于 HEAD（主干开发，会把本次改动吞成存量）")
    else:
        notes.append("无可识别的主干分支")
    return {**base, "baseline_ref": "none", "source": "none", "reason": "；".join(notes),
            "unverified_label": "基线无效：未取到 Sprint 起点 commit"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve", help="解析改动前基线")
    r.add_argument("--root", default=".")
    r.add_argument("--card-ref")
    r.add_argument("--passthrough")
    r.add_argument("--sprint-uncommitted", action="store_true")
    r.add_argument("--main-branch")
    r.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not Path(a.root).is_dir():
        print("目录不存在：" + a.root, file=sys.stderr)
        return 2
    out = resolve(a.root, a.card_ref, a.passthrough, a.sprint_uncommitted, a.main_branch)
    print(json.dumps(out, ensure_ascii=False) if a.json else
          f"baseline_ref={out['baseline_ref']} source={out['source']}" + (f" ({out['reason']})" if out["reason"] else ""))
    return 0 if out["baseline_ref"] != "none" else 3


if __name__ == "__main__":
    sys.exit(main())
