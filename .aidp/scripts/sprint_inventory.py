#!/usr/bin/env python3
"""Sprint 发现事实：占号、计划、启动、验收、归档分开；消费者显式选择范围。

inventory(root, version=None) 返回按版本索引的集合及逐号来源。
closed = accepted & archived；仅有任一证据都不代表完成。
占号扫描所有计划目录 Markdown、progress、activeContext、归档和启动标记；
planned 只取 *研发执行计划*.md，未来计划本身不是 started。
"""
from pathlib import Path
import re

SPRINT_REF_RE = re.compile(r"\bsprint[-\s]?(\d{3,})\b", re.I)
SPRINT_FILE_RE = re.compile(r"sprint-(?:[a-z]+)?(\d{3,})\.md", re.I)
START_FILE_RE = re.compile(r"sprint-(\d{3,})\.started\.json", re.I)
VERSION_RE = re.compile(r"[Vv]\d+(?:\.\d+)*(?:[-_][A-Za-z0-9.]+)?")
NOT_STARTED = re.compile(r"未开始|待开始|未启动|待启动")
STARTED = re.compile(r"进行中|开发中|执行中|已启动|已开发|待测试|测试中|待验收|验收中|待归档")


def _ids(text):
    return {f"{int(value):03d}" for value in SPRINT_REF_RE.findall(text)}


def inventory(root, version=None):
    root = Path(root)
    versions = {version} if version else {
        path.name for base in (root / "docs/plans", root / "memory")
        if base.is_dir() for path in base.iterdir()
        if path.is_dir() and VERSION_RE.fullmatch(path.name)
    }
    result = {}
    for ver in sorted(versions):
        item = {key: set() for key in ("occupied", "planned", "started", "accepted", "archived", "closed")}
        item.update(plan_files=[], sources={})
        result[ver] = item

        def add(numbers, source, *kinds):
            for number in numbers:
                item["occupied"].add(number)
                item["sources"].setdefault(number, {}).setdefault(source, set()).update(kinds)
                for kind in kinds:
                    item[kind].add(number)

        plans = root / "docs/plans" / ver
        for path in sorted(plans.glob("*.md")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            numbers = _ids(path.read_text(encoding="utf-8"))
            if "研发执行计划" in path.name:
                item["plan_files"].append(rel)
                add(numbers, rel, "planned")
            else:
                add(numbers, rel, "occupied")
        memory = root / "memory" / ver
        for path in sorted(memory.glob("*/sprints/*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            marker, archive = START_FILE_RE.fullmatch(path.name), SPRINT_FILE_RE.fullmatch(path.name)
            if marker:
                add({f"{int(marker[1]):03d}"}, rel, "started")
            elif archive:
                numbers = {f"{int(archive[1]):03d}"}
                # 即使产物为空也占号并属于已启动，但不能凭空文件声称归档完整。
                kinds = ("started", "archived") if path.read_text(encoding="utf-8").strip() else ("started",)
                add(numbers, rel, *kinds)
        for name in ("progress.md", "activeContext.md"):
            for path in sorted(memory.glob("*/" + name)):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                for line in path.read_text(encoding="utf-8").splitlines():
                    numbers = _ids(line)
                    add(numbers, rel, "occupied")
                    if NOT_STARTED.search(line):
                        continue
                    if name == "progress.md":
                        if "✅" in line:
                            add(numbers, rel, "accepted", "started")
                        elif STARTED.search(line):
                            add(numbers, rel, "started")
                    elif "已关闭" not in line:
                        plain = line.replace("*", "").replace("`", "")
                        match = re.search(r"(?:当前\s*Sprint|Sprint\s*编号)\s*[:：|]\s*(sprint[-\s]?\d{3,})\b", plain, re.I)
                        if match:
                            add(_ids(match[1]), rel, "started")
        item["closed"] = item["accepted"] & item["archived"]
    return result


def closure_evidence(item, numbers):
    """JSON 可序列化事实；不把不相关历史转换成阻断项。"""
    return {"Sprint-" + number: {
        "accepted": number in item["accepted"],
        "archived": number in item["archived"],
        "missing": (["missing-acceptance"] if number not in item["accepted"] else [])
                   + (["missing-archive"] if number not in item["archived"] else []),
        "sources": [{"file": path, "kinds": sorted(kinds)}
                    for path, kinds in sorted(item["sources"].get(number, {}).items())],
    } for number in sorted(numbers)}
