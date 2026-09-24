#!/usr/bin/env python3
"""规划运行共享的来源 SHA 清单，不取代源代码或 PRD 原文。"""
import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def source(root, name):
    path = (root / name).resolve()
    try:
        rel = path.relative_to(root)
    except ValueError:
        raise ValueError("来源路径越出仓库")
    if not path.is_file():
        raise ValueError("来源文件不存在: " + str(rel))
    return {"path": rel.as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def actual_sha_missing(meta):
    """条目缺 `sha` —— ⛔ 不能当成"没变化"放行：那会把一份没有指纹的清单冒充成可信事实。"""
    return not isinstance(meta.get("sha"), str) or not meta.get("sha").strip()


def inventory_sources(root):
    cache = root / "memory/_facts/code-inventory.json"
    state = json.loads(cache.read_text(encoding="utf-8"))
    files = state.get("files")
    if not isinstance(files, dict):
        raise ValueError("代码清单缺 files 映射，不能冻结为可信事实")
    for name, meta in files.items():
        # ⛔ 形状必须先校验再取值：条目不是 dict 时 `meta.get` 会抛 AttributeError，
        #    下游看到的是一串 traceback 而不是「清单格式不对」——排障方向会被带偏到本脚本上。
        if not isinstance(meta, dict):
            raise ValueError("代码清单条目格式不符（应为 {sha, entities} 对象）: " + name)
        if actual_sha_missing(meta):
            raise ValueError("代码清单条目缺 sha，不能冻结为可信事实: " + name)
        actual = source(root, name)
        if actual["sha256"] != meta.get("sha"):
            raise ValueError("代码清单已过期: " + name)
        yield actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--version", required=True)
    actions = parser.add_subparsers(dest="action", required=True)
    create = actions.add_parser("create")
    create.add_argument("--file", action="append", required=True)
    actions.add_parser("verify")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    if not args.version.startswith("V") or "/" in args.version or ".." in args.version:
        parser.error("非法版本号")
    dest = root / "memory" / args.version / ".aidp-version-facts.json"
    try:
        if args.action == "create":
            files = [source(root, name) for name in sorted(set(args.file))]
            if any(item["path"] == "memory/_facts/code-inventory.json" for item in files):
                files.extend(inventory_sources(root))
            data = {"schema": 1, "version": args.version,
                    "created_at": datetime.now(timezone.utc).isoformat(), "files": files}
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=dest.parent, delete=False) as tmp:
                json.dump(data, tmp, ensure_ascii=False, indent=2)
                temp = tmp.name
            os.replace(temp, dest)
            print(json.dumps(data, ensure_ascii=False))
            return 0
        data = json.loads(dest.read_text(encoding="utf-8"))
        changes = []
        for item in data["files"]:
            try:
                if source(root, item["path"])["sha256"] != item["sha256"]:
                    changes.append(item["path"])
            except ValueError:
                changes.append(item["path"])
        print(json.dumps({"fresh": not changes, "changed": changes}, ensure_ascii=False))
        return 1 if changes else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[version_fact_snapshot] {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
