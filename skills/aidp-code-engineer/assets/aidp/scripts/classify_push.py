#!/usr/bin/env python3
"""Read-only push classifier: should this push be watched on remote CICD?

    classify_push.py --root . [--base-ref REF] [--head REF] [--json]

stdout (always one JSON object, exit 0 unless the repo is not git):

    {"decision": "watch|skip", "paths": {changed_files, formal_code_files,
     non_formal_files, conservative_files, source_roots}, "reason": str|null,
     "error": bool}

It never writes anything (no baseline, no files): `git status` is unchanged by
running it.  A classification failure is fail-closed: decision=watch,
error=true.  Callers that need a commit id obtain it live
(`git rev-parse HEAD` / `git ls-remote`); nothing is persisted.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Sequence

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from vcs import detect_mode, unsupported, EXIT_UNSUPPORTED  # noqa: E402

REQUIRED_KEYS = {
    "has_formal_code_change",
    "changed_files",
    "formal_code_files",
    "non_formal_files",
    "cicd_should_watch",
    "skip_reason",
    "classification_error",
    "source_roots",
    "conservative_files",
}
ALLOWED_KEYS = REQUIRED_KEYS
PATH_KEYS = ("changed_files", "formal_code_files", "non_formal_files", "conservative_files", "source_roots")


def validate_payload(payload: object) -> tuple[bool, str]:
    if not isinstance(payload, dict) or set(payload) != ALLOWED_KEYS:
        return False, "classifier JSON schema has missing or unknown fields"
    bool_keys = ("has_formal_code_change", "cicd_should_watch", "classification_error")
    if any(not isinstance(payload.get(key), bool) for key in bool_keys):
        return False, "classifier JSON schema has invalid boolean fields"
    list_keys = ("changed_files", "formal_code_files", "non_formal_files", "source_roots", "conservative_files")
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


def classify_command(root: Path, base_ref: Optional[str], head: Optional[str] = None) -> tuple[dict, str, int]:
    command = [sys.executable, str(HERE / "classify_commit_change.py"),
               "--root", str(root), "--json"]
    if base_ref:
        command.extend(["--base-ref", base_ref])
    if head:
        command.extend(["--head", head])
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


def decide(payload: dict, error_reason: str = "") -> dict:
    """纯函数：把分类器 payload（或失败原因）转成对外结果。分类缺失/出错 → watch（fail-closed）。"""
    if error_reason or not payload:
        return {"decision": "watch", "paths": {k: [] for k in PATH_KEYS},
                "reason": "classification-error: %s" % (error_reason or "empty classification"), "error": True}
    failed = bool(payload.get("classification_error"))
    watch = failed or bool(payload.get("has_formal_code_change"))
    return {"decision": "watch" if watch else "skip",
            "paths": {k: list(payload.get(k) or []) for k in PATH_KEYS},
            "reason": payload.get("skip_reason") if (failed or not watch) else "formal-code-change",
            "error": failed}


def decide_cicd_path(classification: dict) -> str:
    """兼容读取方：classification 含 decision 字段则直接取，否则按旧字段判定。"""
    if "decision" in classification:
        return classification["decision"]
    if classification.get("classification_error"):
        return "watch"
    return "watch" if classification.get("has_formal_code_change") else "skip"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="只读推送分类：输出 watch / skip，不落盘")
    parser.add_argument("--root", default=".")
    parser.add_argument("--base-ref", help="本次推送的基线（通常是远端已有的提交）；空串按未提供处理")
    parser.add_argument("--head", help="被推送的提交（缺省 HEAD）")
    parser.add_argument("--json", action="store_true", help="兼容参数：输出始终为 JSON")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    if detect_mode(root) != "git":
        print(json.dumps(unsupported("push")))
        return EXIT_UNSUPPORTED
    payload, error, rc = classify_command(root, args.base_ref, args.head)
    out = decide(payload, error if rc != 0 else "")
    print(json.dumps(out, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
