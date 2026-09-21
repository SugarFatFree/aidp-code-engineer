#!/usr/bin/env python3
"""Classify a push and persist the result on the current autopilot build.

The caller must make the push decision from this record: a clean formal-code
classification skips remote CICD, while a classification error watches it.

Every record is keyed by the pushed HEAD commit (`commit`), so `commit_gate.py`
can tell whether *this* push was classified and whether its deploy terminal is
known. After watching CICD, record the terminal with:

    classify_push.py --version V (--build B | --standalone) --record-terminal success|failed|unknown:<reason>
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from baseline_edit import LockedBaseline, resolve_build_idx  # noqa: E402

REQUIRED_KEYS = {
    "has_formal_code_change",
    "changed_files",
    "formal_code_files",
    "non_formal_files",
    "cicd_should_watch",
    "skip_reason",
    "classification_error",
    "source_roots",
}
ALLOWED_KEYS = REQUIRED_KEYS


def validate_payload(payload: object) -> tuple[bool, str]:
    if not isinstance(payload, dict) or set(payload) != ALLOWED_KEYS:
        return False, "classifier JSON schema has missing or unknown fields"
    bool_keys = ("has_formal_code_change", "cicd_should_watch", "classification_error")
    if any(not isinstance(payload.get(key), bool) for key in bool_keys):
        return False, "classifier JSON schema has invalid boolean fields"
    list_keys = ("changed_files", "formal_code_files", "non_formal_files", "source_roots")
    if any(not isinstance(payload.get(key), list)
           or any(not isinstance(item, str) or not item for item in payload[key])
           or len(payload[key]) != len(set(payload[key]))
           for key in list_keys):
        return False, "classifier JSON schema has invalid list fields"
    changed = payload["changed_files"]
    formal_files = payload["formal_code_files"]
    non_formal_files = payload["non_formal_files"]
    if set(formal_files) & set(non_formal_files):
        return False, "classifier JSON schema has overlapping formal/non-formal files"
    if len(changed) != len(set(formal_files + non_formal_files)) or set(changed) != set(formal_files + non_formal_files):
        return False, "classifier JSON schema has inconsistent file collections"
    if bool(formal_files) != payload["has_formal_code_change"]:
        return False, "classifier JSON schema has inconsistent formal file relation"
    if payload.get("skip_reason") is not None and not isinstance(payload["skip_reason"], str):
        return False, "classifier JSON schema has invalid skip_reason"
    formal = payload["has_formal_code_change"]
    failed = payload["classification_error"]
    watching = payload["cicd_should_watch"]
    reason = payload["skip_reason"]
    if failed and (not watching or reason != "unrecognized-source-layout"):
        return False, "classifier JSON schema has inconsistent classification-error relation"
    if not failed and not formal and (watching or reason != "no-formal-code-change"):
        return False, "classifier JSON schema has inconsistent no-formal-code relation"
    if not failed and formal and (not watching or reason is not None):
        return False, "classifier JSON schema has inconsistent formal-code relation"
    return True, ""


def classify_command(root: Path, base_ref: Optional[str]) -> tuple[dict, str, int]:
    command = [sys.executable, str(HERE / "classify_commit_change.py"),
               "--root", str(root), "--json"]
    if base_ref is not None:
        command.extend(["--base-ref", base_ref])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    raw = (result.stdout or "").strip()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}, (result.stderr or raw or "classifier returned no JSON")[:1000], result.returncode or 1
    if result.returncode != 0 or not isinstance(payload, dict):
        return {}, (result.stderr or "classifier returned an invalid result")[:1000], result.returncode or 1
    valid, reason = validate_payload(payload)
    if not valid:
        return {}, reason, 1
    return payload, "", 0


def failure_result(reason: str) -> dict:
    return {
        "has_formal_code_change": False,
        "formal_code_change": False,
        "changed_files": [],
        "formal_code_files": [],
        "non_formal_files": [],
        "source_roots": [],
        "cicd_should_watch": True,
        "cicd_skipped": False,
        "skip_reason": "classification-error",
        "classification_error": True,
        "classification_command_error": reason,
    }


def normalize_result(payload: dict) -> dict:
    result = dict(payload)
    result["formal_code_change"] = bool(payload["has_formal_code_change"])
    result["cicd_skipped"] = not bool(payload["has_formal_code_change"] or payload["classification_error"])
    if payload["classification_error"]:
        result["cicd_skipped"] = False
        result["cicd_should_watch"] = True
    return result


def decide_cicd_path(classification: dict) -> str:
    """Return the only two push paths: ``skip`` or ``watch``."""
    if classification.get("classification_error"):
        return "watch"
    return "watch" if classification.get("has_formal_code_change") else "skip"


def _head_sha(root: Path) -> str:
    """当前 HEAD 的 sha（取不到 → 空串，调用方据此跳过 commit 键控记录）。"""
    import subprocess
    try:
        cp = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"],
                            capture_output=True, text=True, timeout=30)
        return (cp.stdout or "").strip() if cp.returncode == 0 else ""
    except (OSError, ValueError):
        return ""


def persist(root: Path, version: str, build: str, result: dict, baseline: Path,
            standalone: bool = False) -> None:
    if not version or (not build and not standalone):
        raise ValueError("--version and --build are required unless --standalone is used")
    with LockedBaseline(str(baseline), write=True) as locked:
        version_node = locked.data.setdefault("versions", {}).setdefault(version, {})
        stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
        result = dict(result)
        result["classified_at"] = stamp
        head = _head_sha(root)
        if head:
            result["commit"] = head
        if standalone:
            version_node["release_change_classification"] = result
            # ★ 另追加一条 **commit 键控**的记录：单槽 `release_change_classification`
            #   后写覆盖前写、且不带 commit sha —— 欠账判定无从知道它覆盖的是不是**这次**推送。
            #   `commit_gate::_standalone_push_pending` 读的正是这个数组（读写必须同层，
            #   否则重蹈「decidable_skips 写版本级、读 build 级」那次的覆辙）。
            if head:
                pushes = version_node.setdefault("standalone_pushes", [])
                if not any(isinstance(it, dict) and str(it.get("commit") or "")[:40] == head[:40]
                           for it in pushes):
                    pushes.append({
                        "commit": head,
                        "classified_at": stamp,
                        "formal_code_change": bool(result.get("has_formal_code_change")),
                        "cicd_skipped": result.get("cicd_skipped"),
                    })
                    del pushes[:-50]      # 只留最近 50 条，⛔ 别让它无限长
            return
        idx, ids = resolve_build_idx(locked.data, version, build)
        if idx is None:
            # ★ current_build 指向它 = 它是合法的当前 build，只是 builds[] 漏登记了
            #   （baseline 内部不一致，不是调用方传错）。此时**自动补登记**再继续：
            #   直接失败会让整条 push 分流走 fail-closed 白跑一轮 CICD 监听，
            #   而降级成 --standalone 会把分类写到版本级、build 级的读方仍读不到，
            #   同样落回 fail-closed —— 补登记才是真正修复不一致的那一步。
            #   ⛔ 只对 current_build 生效：其它 build 找不到就是真传错了，照常报错。
            if build and build == version_node.get("current_build"):
                version_node.setdefault("builds", []).append(
                    {"build": build, "status": "unknown",
                     "note": "由 classify_push 自动补登记（current_build 指向但 builds[] 缺失）"})
                idx, ids = resolve_build_idx(locked.data, version, build)
                sys.stderr.write(
                    f"⚠️ build {build!r} 是 current_build 但不在 builds[] 中 —— 已自动补登记；"
                    f"请检查上游为何漏登记（正常路径由 baseline_edit set current_build 一并写入）\n")
        if idx is None:
            raise ValueError(f"build {build!r} not found for {version} (existing: {ids})")
        node = version_node["builds"][idx]
        # ⛔ 扁平键 + change_classification 是**本次 push** 的判定，必须保持"最新一次"语义 ——
        #    Phase 3.6 / 3.7 / release-7 都是「刚分类完立刻读」，问的是"这一次 push 要不要等部署"，
        #    把它们改成累积会让纯文档 push 去等一场根本不会发生的部署。
        node["change_classification"] = result
        for key in (
            "cicd_skipped", "skip_reason", "formal_code_change",
            "has_formal_code_change", "classification_error", "cicd_should_watch",
            "changed_files", "formal_code_files", "non_formal_files",
        ):
            node[key] = result.get(key)
        accumulate_push(node, result)


# ★ 同一 build 可能被 push 多次（典型：先推代码、再补文档）。只覆写扁平键会让**后写的赢**：一次纯文档 push 就把"本 build 改过 2 个 Java 文件"整个抹成
#   `formal_code_change=false` / `cicd_skipped=true`，build 级从此查不到它曾发布过代码。
#   两种语义都要，所以分开存：
#     · 扁平键 / change_classification = **本次 push**（逐次覆写，per-push 读者用）
#     · pushes[] + build_* = **本 build 累积**（append + 单调，build 级读者用）
#   `build_formal_code_change` 只会 false→true，绝不回退 —— "这个 build 发过代码"是既成事实。
_PUSH_HISTORY_CAP = 100


def accumulate_push(node: dict, result: dict) -> None:
    """把本次 push 记入 build 级累积视图（append + 单调 OR），不覆盖历史。"""
    history = node.get("pushes")
    if not isinstance(history, list):
        history = []
    history.append({
        "commit": result.get("commit"),
        "classified_at": result.get("classified_at"),
        "formal_code_change": bool(result.get("formal_code_change")),
        "classification_error": bool(result.get("classification_error")),
        "cicd_skipped": bool(result.get("cicd_skipped")),
        "skip_reason": result.get("skip_reason"),
        "changed_files": list(result.get("changed_files") or []),
        "formal_code_files": list(result.get("formal_code_files") or []),
    })
    node["pushes"] = history[-_PUSH_HISTORY_CAP:]

    was_formal = bool(node.get("build_formal_code_change"))
    now_formal = any(bool(h.get("formal_code_change")) for h in node["pushes"]) or was_formal
    any_error = any(bool(h.get("classification_error")) for h in node["pushes"]) \
        or bool(node.get("build_classification_error"))
    node["build_formal_code_change"] = now_formal
    node["build_classification_error"] = any_error
    node["build_cicd_skipped"] = not (now_formal or any_error)
    merged = list(node.get("build_formal_code_files") or [])
    for f in (result.get("formal_code_files") or []):
        if f not in merged:
            merged.append(f)
    node["build_formal_code_files"] = merged
    node["push_count"] = len(node["pushes"])

    # 本次判"无正式代码"但本 build 此前已发过代码 —— 合法（补文档），但必须看得见：
    # 静默下去就是下游那次"已部署成功却查不到"的复现路径。
    if was_formal and not bool(result.get("formal_code_change")):
        sys.stderr.write(
            "ℹ️ 本次 push 无正式代码变更，但本 build 此前已推送过正式代码 —— "
            "扁平键按本次 push 覆写（per-push 语义），build 级事实保留在 "
            "`build_formal_code_change=true` / `pushes[]`；问「这个 build 是否发过代码」请读 build_* 系列\n")


def record_terminal(root: Path, version: str, build: str, standalone: bool, terminal: str,
                    baseline: Path) -> dict:
    """给 HEAD 对应的推送记录写部署终态（success / failed / unknown:<原因>）。

    `unknown:<原因>` 用于 provider=none / CLI 不可用等无法获知终态的合法降级：
    不算欠账，但必须显式可见（`deploy_terminal` 非空）。
    """
    if not (terminal in ("success", "failed") or terminal.startswith("unknown:")):
        raise ValueError("--record-terminal 只接受 success / failed / unknown:<原因>")
    head = _head_sha(root)
    if not head:
        raise ValueError("取不到 HEAD commit")
    stamp = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    hit = 0
    with LockedBaseline(str(baseline), write=True) as locked:
        vn = locked.data.setdefault("versions", {}).setdefault(version, {})
        recs = []
        if standalone:
            recs += [it for it in vn.get("standalone_pushes") or [] if isinstance(it, dict)]
        else:
            idx, ids = resolve_build_idx(locked.data, version, build)
            if idx is None:
                raise ValueError(f"build {build!r} not found for {version} (existing: {ids})")
            node = vn["builds"][idx]
            recs += [it for it in node.get("pushes") or [] if isinstance(it, dict)]
            cc = node.get("change_classification")
            if isinstance(cc, dict):
                recs.append(cc)
        for it in recs:
            if str(it.get("commit") or "")[:40] == head[:40]:
                it["deploy_terminal"] = terminal
                it["deploy_terminal_at"] = stamp
                hit += 1
    if not hit:
        raise ValueError(f"HEAD {head[:8]} 没有分类记录：先跑 classify_push.py 再记终态")
    return {"commit": head, "deploy_terminal": terminal, "records": hit}


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Classify push changes and persist the build decision")
    parser.add_argument("--root", default=".")
    parser.add_argument("--version", required=True)
    parser.add_argument("--build", default="")
    parser.add_argument("--standalone", action="store_true",
                        help="记录到版本级 release_change_classification（无 current_build 的发布路径）")
    parser.add_argument("--baseline", default="")
    parser.add_argument("--base-ref")
    parser.add_argument("--record-terminal", default="",
                        help="不分类，只给 HEAD 对应的推送记录写部署终态：success / failed / unknown:<原因>")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    baseline = Path(args.baseline).resolve() if args.baseline else root / "memory/.sprint-autopilot-baseline.json"
    if args.record_terminal:
        try:
            print(json.dumps(record_terminal(root, args.version, args.build, args.standalone,
                                             args.record_terminal, baseline), ensure_ascii=False))
        except (OSError, ValueError, SystemExit) as exc:
            print(f"record terminal failed: {exc}", file=sys.stderr)
            return 2
        return 0
    payload, error, rc = classify_command(root, args.base_ref)
    result = normalize_result(payload) if rc == 0 else failure_result(error)
    try:
        persist(root, args.version, args.build, result, baseline, standalone=args.standalone)
    except (OSError, ValueError, SystemExit) as exc:
        print(f"classification record failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"path": decide_cicd_path(result), **result}, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
