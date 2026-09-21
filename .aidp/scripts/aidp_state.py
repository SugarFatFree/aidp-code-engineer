#!/usr/bin/env python3
"""aidp_state.py — 通用项目级运行时状态记录（baseline 的 `project_state` 段）。

仿 memory/.sprint-autopilot-baseline.json 把项目级「程序写的运行时记录」集中到一处，
设计为**通用容器**：顶层按命名段组织，可持续追加新段，不为每类记录各开一个文件。
纯标准库，读写幂等，中间层不存在时按需创建。随 baseline **团队共享**（入库）。

人维护的开关（门禁 / 通知 / CICD）不在这里，单一信源是 `memory/aidp-config.yaml`
（`aidp_config.py`）；本脚本的 `*-enabled` 子命令只是对它的便捷读写。

子命令：
  get <dotted.key>            读取嵌套键（点分路径）；不存在 → 空输出 + exit 0
  set <dotted.key> <value>    写入（自动建中间层；value 先按 JSON 解析，失败按原始字符串存）
  commit-gate-enabled         读提交前门禁总开关（约定 24，`commit_gate.enabled`）。输出 "true"/"false"；缺省 true
  commit-gate-enable          开启（写 commit_gate.enabled = true）
  commit-gate-disable         关闭（写 commit_gate.enabled = false）——关闭后 commit_gate.py 退出码恒 0
  notify-enabled              读里程碑通知总开关（约定 32，`notify.enabled`）。输出 "true"/"false"；缺省 false
  notify-enable               开启（写 notify.enabled = true）
  notify-disable              关闭（写 notify.enabled = false）

退出码：*-enabled 恒 0（决策查询，由调用方读输出）；其它命令成功 0 / 出错 1。
"""
import argparse
import json
import sys
from pathlib import Path

BASELINE_REL = "memory/.sprint-autopilot-baseline.json"
STATE_SECTION = "project_state"                   # baseline 里承载本模块的顶层段
SCHEMA_VERSION = "1"


def _baseline_path(root: Path) -> str:
    return str(Path(root) / BASELINE_REL)


def load_state(root: Path) -> dict:
    """读项目级运行时状态。

    ## 它为什么住进 baseline

    本模块承载的全是**程序写的、团队共享的**记录——
    与 `memory/.sprint-autopilot-baseline.json` 是同一类东西，故同住一个文件；`memory/` 下的落点
    按「谁写 × 入不入库」各占一格（判据见 `aidp_paths.REGISTRY` 与其 `--check-vcs`）。

    baseline 缺失、损坏或无该段时返回空容器。
    """
    p = Path(root) / BASELINE_REL
    if p.is_file():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get(STATE_SECTION), dict):
                return data[STATE_SECTION]
        except (json.JSONDecodeError, OSError):
            pass                       # baseline 坏了不该让本模块崩，按空容器处理
    return {"schema_version": SCHEMA_VERSION}


def save_state(root: Path, data: dict) -> None:
    """写回 baseline 的 `project_state` 段（持锁 + 原子替换，与 baseline 其余写方同规格）。

    ⛔ 不能直接 json.dump 整个 baseline：autopilot 链路同时在写它的 `versions` 段，
    无锁覆盖会把对方刚写的 build 状态整段抹掉。
    """
    data.setdefault("schema_version", SCHEMA_VERSION)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import baseline_edit
    path = _baseline_path(root)
    with baseline_edit.LockedBaseline(path, write=True) as lb:
        lb.data[STATE_SECTION] = data


def get_key(data: dict, dotted: str):
    cur = data
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def set_key(data: dict, dotted: str, value) -> None:
    parts = dotted.split(".")
    cur = data
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def _cfg():
    """人维护配置访问器（`memory/aidp-config.yaml`，单一信源）。"""
    import sys as _s
    _s.path.insert(0, str(Path(__file__).resolve().parent))
    import aidp_config
    return aidp_config


def commit_gate_enabled(root: Path) -> bool:
    """提交前门禁总开关（约定 24）：`memory/aidp-config.yaml` 的 `commit_gate.enabled`，缺省 True。"""
    return _cfg().commit_gate_enabled(str(root))


def notify_enabled(root: Path) -> bool:
    """里程碑通知总开关（约定 32）：`notify.enabled`，缺省 False。"""
    return bool(_cfg().notify_config(str(root)).get("enabled"))


def set_enabled(root: Path, section: str, enabled: bool) -> bool:
    """写 `<section>.enabled = True/False`（外科手术式写入，保留注释），返回写入值。"""
    _cfg().set_scalar(str(root), "%s.enabled" % section, bool(enabled))
    return bool(enabled)


def main(argv) -> int:
    ap = argparse.ArgumentParser(description="通用项目级运行时状态记录（baseline project_state 段）")
    ap.add_argument("--repo-root", default=".")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("get", help="读取嵌套键（点分路径）")
    g.add_argument("key")

    s = sub.add_parser("set", help="写入嵌套键（value 先按 JSON 解析，失败按字符串）")
    s.add_argument("key")
    s.add_argument("value")

    sub.add_parser("commit-gate-enabled", help="读提交前门禁总开关（true/false；缺省=true）")
    sub.add_parser("commit-gate-enable", help="开启提交前门禁（commit_gate.enabled=true）")
    sub.add_parser("commit-gate-disable", help="关闭提交前门禁（commit_gate.enabled=false）")
    sub.add_parser("notify-enabled", help="读里程碑通知总开关（true/false；缺省=false）")
    sub.add_parser("notify-enable", help="开启里程碑通知（notify.enabled=true）")
    sub.add_parser("notify-disable", help="关闭里程碑通知（notify.enabled=false）")

    args = ap.parse_args(argv)
    root = Path(args.repo_root)

    if args.cmd == "get":
        val = get_key(load_state(root), args.key)
        if val is not None:
            print(val if isinstance(val, str) else json.dumps(val, ensure_ascii=False))
        return 0

    if args.cmd == "set":
        try:
            parsed = json.loads(args.value)
        except json.JSONDecodeError:
            parsed = args.value
        data = load_state(root)
        set_key(data, args.key, parsed)
        save_state(root, data)
        print(f"[aidp_state] set {args.key} = {parsed!r}")
        return 0

    if args.cmd == "commit-gate-enabled":
        print("true" if commit_gate_enabled(root) else "false")
        return 0

    if args.cmd in ("commit-gate-enable", "commit-gate-disable"):
        val = set_enabled(root, "commit_gate", args.cmd == "commit-gate-enable")
        print(f"[aidp_state] commit_gate.enabled = {str(val).lower()}")
        return 0

    if args.cmd == "notify-enabled":
        print("true" if notify_enabled(root) else "false")
        return 0

    if args.cmd in ("notify-enable", "notify-disable"):
        val = set_enabled(root, "notify", args.cmd == "notify-enable")
        print(f"[aidp_state] notify.enabled = {str(val).lower()}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
