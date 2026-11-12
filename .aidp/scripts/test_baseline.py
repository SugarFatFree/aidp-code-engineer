#!/usr/bin/env python3
"""已知失败基线：代替 git stash 做「改动前后」对照。

  record --root . [--execution-context CTX] [--key K] (--ids-file F | --from-junit X.xml | --from-log LOG)
  diff   --root . [--execution-context CTX] [--key K] (--ids-file F | --from-junit X.xml | --from-log LOG) [--json]
  show   --root . [--execution-context CTX] [--key K]

基线文件 memory/.aidp/test-baseline/<key>.json（key = 上下文 task_id，缺省 default）：
  {"schema":1,"task_id":key,"failures":[测试ID...],"source":"...","recorded_at":epoch}
diff 输出 {"new_failures":[本次失败-基线],"known_failures":[交集],"fixed":[基线-本次失败]}；
有新失败退出 1，否则 0；基线缺失或本次输入为空（疑似未执行）退出 2，拒绝给出差值。
record 必须在「改动前」的干净树上跑出结果后调用；record/diff 应使用同一种来源格式，测试 ID 才可比。
测试 ID 解析：pytest 摘要行 FAILED/ERROR path::name、unittest FAIL:/ERROR: name (mod.Class)、
Jest 的 ● 与 FAIL path、Maven/Gradle 的 Class.method / Class > method FAILED、JUnit XML 的 failure/error 用例。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

BASELINE_DIR = "memory/.aidp/test-baseline"


class InputError(ValueError):
    pass


def safe_key(value):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value or "default")).strip(".") or "default"


def context_key(ctx):
    if not ctx:
        return "default"
    try:
        return safe_key(json.loads(Path(ctx).read_text(encoding="utf-8"))["task_id"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise InputError(f"执行上下文不可读：{ctx}（{exc}）") from exc


def parse_junit(path):
    try:
        tree = ET.parse(path)
    except (OSError, ET.ParseError) as exc:
        raise InputError(f"JUnit XML 不可读：{path}（{exc}）") from exc
    ids, total = set(), 0
    for case in tree.iter("testcase"):
        total += 1
        if case.find("failure") is not None or case.find("error") is not None:
            cls, name = case.get("classname", ""), case.get("name", "")
            ids.add(f"{cls}::{name}" if cls else name)
    return ids, total


LOG_PATTERNS = (
    re.compile(r"^(?:FAILED|ERROR)\s+(\S+::\S+?)(?:\s+-\s.*)?$"),            # pytest 摘要
    re.compile(r"^(?:FAIL|ERROR):\s+(\S+)\s+\(([\w.]+)\)"),                  # unittest
    re.compile(r"^\s*●\s+(.+?)\s*$"),                                         # jest 用例
    re.compile(r"^\s*FAIL\s+(\S+\.(?:js|jsx|ts|tsx|mjs))\b"),                # jest 文件
    re.compile(r"^\[ERROR\]\s+(?:Failures:\s*)?\s*([\w.$]+\.\w+):\d+"),      # maven
    re.compile(r"^(\S+)\s+>\s+(\S.*?)\s+FAILED$"),                           # gradle
    re.compile(r"^--- FAIL:\s+(\S+)"),                                        # go
)
EXECUTED = re.compile(r"(passed|failed|PASSED|FAILED|Ran \d+ test|Tests?:\s+\d|Tests run:|BUILD |\bok\b|--- (PASS|FAIL))")


def parse_log(path):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        raise InputError(f"日志不可读：{path}（{exc}）") from exc
    ids, ran = set(), False
    for line in lines:
        ran = ran or bool(EXECUTED.search(line))
        for i, pat in enumerate(LOG_PATTERNS):
            m = pat.match(line)
            if m:
                if i == 1:
                    ids.add(f"{m.group(2)}.{m.group(1)}")
                elif i == 5:
                    ids.add(f"{m.group(1)}.{m.group(2)}")
                else:
                    ids.add(m.group(1))
                break
    return ids, ran


def read_ids_file(path):
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"ID 文件不可读：{path}（{exc}）") from exc
    text = text.strip()
    if text.startswith("["):
        try:
            return {str(x) for x in json.loads(text)}
        except ValueError as exc:
            raise InputError(f"ID 文件不是合法 JSON 数组：{exc}") from exc
    return {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")}


def load_failures(args):
    """返回 (失败 ID 集合, 来源描述, 是否确有执行)。"""
    chosen = [bool(args.ids_file), bool(args.from_junit), bool(args.from_log)]
    if sum(chosen) != 1:
        raise InputError("必须且只能给出 --ids-file / --from-junit / --from-log 之一")
    if args.ids_file:
        return read_ids_file(args.ids_file), f"ids-file:{args.ids_file}", True
    if args.from_junit:
        ids, total = parse_junit(args.from_junit)
        return ids, f"junit:{args.from_junit}", total > 0
    ids, ran = parse_log(args.from_log)
    return ids, f"log:{args.from_log}", ran


def baseline_path(root, key):
    return Path(root) / BASELINE_DIR / f"{key}.json"


def record(root, key, failures, source):
    path = baseline_path(root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"schema": 1, "task_id": key, "failures": sorted(failures), "source": source,
            "recorded_at": int(time.time())}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return data


def load_baseline(root, key):
    path = baseline_path(root, key)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InputError(f"基线文件缺失或损坏：{path}（先在改动前 record）") from exc


def diff(base, failures):
    old = set(base["failures"])
    return {"new_failures": sorted(failures - old), "known_failures": sorted(failures & old),
            "fixed": sorted(old - failures)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    for name in ("record", "diff", "show"):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        p.add_argument("--execution-context", default="")
        p.add_argument("--key", default="")
        if name != "show":
            p.add_argument("--ids-file", default="")
            p.add_argument("--from-junit", default="")
            p.add_argument("--from-log", default="")
        if name == "diff":
            p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        key = safe_key(args.key) if args.key else context_key(args.execution_context)
        if args.mode == "show":
            print(json.dumps(load_baseline(args.root, key), ensure_ascii=False, indent=2))
            return 0
        failures, source, executed = load_failures(args)
        if not executed:
            raise InputError(f"{source} 中没有测试已执行的迹象，拒绝{'记录基线' if args.mode == 'record' else '比较'}")
        if args.mode == "record":
            data = record(args.root, key, failures, source)
            print(json.dumps({"recorded": len(data["failures"]), "file": str(baseline_path(args.root, key))}, ensure_ascii=False))
            return 0
        result = diff(load_baseline(args.root, key), failures)
    except InputError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=None if args.json else 2))
    return 1 if result["new_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
