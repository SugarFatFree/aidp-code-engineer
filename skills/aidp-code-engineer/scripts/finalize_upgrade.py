#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize_upgrade.py —— 脚手架交付收口闸：语义改写队列逐条核验完成，才把 `scaffold.pending` 提升为正式版本戳。

脚手架把项目文件分两类处理：契约文件与项目记忆文件由脚本确定性覆盖 / 合并；已填写的用户填充型契约、
项目改过的 docs 结构性 README 等含项目自有内容、又需要吸收新版骨架的文件进 `.aidp-rewrite-queue.txt`，
由 Agent 逐条语义改写。后者脚本无法代劳，故 `scaffold.py` 在队列非空时只写 `scaffold.pending`，由本脚本收口。

收口核验（逐条）：队列行记录了入队时目标文件的 sha256；目标文件内容已变化 = 已改写；
未变化的条目必须用 `--accept <目标路径>` 显式确认「无需改动」，否则拒绝收口。
队列文件被手工删除而 `scaffold.pending` 仍在 → 无从核验，拒绝收口（重跑 `scaffold.py --mode upgrade` 重新生成队列）。
收口成功后：指纹台账 `.aidp-user-fillable.json` 推进到新版骨架（下次升级骨架未变即不再入队），删除队列文件。

用法：
    python3 <SKILL_DIR>/scripts/finalize_upgrade.py [--root DIR] [--accept 路径 …] [--json]
    python3 <SKILL_DIR>/scripts/finalize_upgrade.py --status     # 只报告，不写入

退出码：0 已收口 / 无待交付 · 1 有未改写条目或队列缺失，拒绝收口 · 2 用法错误
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scaffold_lib as L  # noqa: E402
import scaffold_marker  # noqa: E402

QUEUE = L.REWRITE_QUEUE_FILE


def entry_states(root: Path, accepted) -> list:
    """[{target, template, state}]；state ∈ rewritten | accepted | unchanged | missing。"""
    out = []
    for line in L.queue_entries(root):
        e = L.parse_queue_entry(line)
        target = root / e["target"]
        if e["target"] in accepted:
            state = "accepted"
        elif not target.is_file():
            state = "missing"
        elif e["before"] and L.sha256(target.read_bytes()) != e["before"]:
            state = "rewritten"
        else:
            state = "unchanged"
        out.append({**e, "state": state})
    return out


def promote_ledger(root: Path, states: list):
    """已收口条目的指纹台账推进到新版骨架（记骨架指纹，不记项目文件指纹）。"""
    for e in states:
        if e["target"] in ("AGENTS.md", "CLAUDE.md"):
            continue
        tpl = root / e["template"]
        if e["template"] and tpl.is_file():
            L.uf_record(root, L.ledger_label(e["target"]), tpl.read_bytes())


def main(argv=None) -> int:
    # 与 scaffold.py / verify.py 同口径：先把控制台配成不会因编码抛异常（Windows GBK 控制台上
    # `✅`/`⛔` 一 print 就 UnicodeEncodeError），⛔ 不能让打印把一次成功的收口判成失败。
    L.configure_console()
    ap = argparse.ArgumentParser(description="脚手架交付收口：语义改写队列逐条核验完成才提升版本戳")
    ap.add_argument("--root", default=".")
    ap.add_argument("--accept", action="append", default=[], metavar="路径",
                    help="确认该队列条目无需改动（目标文件相对路径，可多次）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)

    root = Path(a.root).resolve()
    if not root.is_dir():
        print(f"项目根不存在：{root}", file=sys.stderr)
        return 2
    queue = root / QUEUE
    pending = scaffold_marker.read_pending(root) or ""
    current = scaffold_marker.read_version(root) or ""
    states = entry_states(root, set(a.accept))
    left = [e for e in states if e["state"] in ("unchanged", "missing")]

    def emit(ok, state, msg, code):
        if a.json:
            print(json.dumps({"ok": ok, "state": state, "message": msg, "current_version": current,
                              "pending_version": pending, "entries": states,
                              "unconsumed": [e["target"] for e in left]},
                             ensure_ascii=False, indent=2))
        else:
            print(msg)
            for e in left[:20]:
                print(f"   - {e['target']}（{'目标文件不存在' if e['state'] == 'missing' else '入队后未改动'}）")
            if len(left) > 20:
                print(f"   … 另 {len(left) - 20} 条")
        return code

    if left:
        return emit(False, "blocked",
                    f"⛔ {QUEUE} 仍有 {len(left)} 条未改写（目标版本 {pending or '未记录'}）。逐条完成语义改写后再跑本脚本；"
                    f"确认无需改动的条目加 `--accept <路径>`：", 1)
    if pending and not queue.is_file() and not states:
        # 队列非空时 scaffold.py 才写 pending；队列文件却不在 = 被手工删除，无从核验
        return emit(False, "queue-missing",
                    f"⛔ scaffold.pending = {pending}，但 {QUEUE} 不存在，无法核验语义改写是否完成。"
                    f"重跑 `scaffold.py <项目根> --mode upgrade` 重新生成队列后再收口", 1)
    if a.status:
        if not pending and not states:
            return emit(True, "nothing-pending", f"✅ 无待交付升级（scaffold.version = {current or '未建立'}）", 0)
        return emit(True, "ready", f"✅ 队列已全部改写，可收口：{current or '未建立'} → {pending or current}（--status 未写入）", 0)
    promote_ledger(root, states)
    if queue.is_file():
        queue.unlink()
    if not pending:
        return emit(True, "nothing-pending", f"✅ 无待交付升级（scaffold.version = {current or '未建立'}）", 0)
    scaffold_marker.write_version(root, pending)
    return emit(True, "finalized", f"✅ 收口完成：scaffold.version {current or '未建立'} → {pending}", 0)


if __name__ == "__main__":
    sys.exit(main())
