#!/usr/bin/env python3
"""规划补件写集与五阶段恢复；不生成内容、不修改依赖 SKILL。

CLI 的 JSON 是调用层调度依据，失败保留产物；状态保存在 memory/{version}。
生成节点由 start/finish 消费真实子命令结果，refs 执行现有三份确定性脚本。
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

STAGES = {"plan": (), "case": (), "map": ("plan",),
          "ref": ("case", "map"), "verify": ("ref",)}
FAMILIES = {"requirements": "docs/requirements/{v}/研发需求",
            "design": "docs/design/detail/{v}", "plan": "docs/plans/{v}",
            "selftest": "docs/testing/{v}/研发自测"}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def local(root, name):
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"路径超出项目: {name}")
    return path


def content_bytes(path, semantic=False):
    """仅剥离索引中的 QR 协议控制行；索引正文/链接/顺序仍参与输入指纹。"""
    raw = path.read_bytes()
    if not semantic or path.name != "00_索引.md":
        return raw
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.replace("\r\n", "\n").split("\n")
    drop, fenced = set(), False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and line.startswith(("> QR 级别:", "<!-- AIDP-QR-HANDOFF")):
            drop.add(i)
    if drop and min(drop) > 0 and lines[min(drop) - 1] == "":
        drop.add(min(drop) - 1)
    return newline.join(line for i, line in enumerate(lines) if i not in drop).encode("utf-8")


def hashes(root, names, semantic=False):
    """目录含成员清单，增删文件也改变指纹；缺失输入不能被省略。"""
    result = {}
    for name in sorted(set(names)):
        path = local(root, name)
        files = sorted(path.rglob("*")) if path.is_dir() else [path]
        if not files:
            result[name + "/"] = "empty-directory"
        for item in files:
            if item.is_dir():
                continue
            local(root, str(item.relative_to(root)))
            result[item.relative_to(root).as_posix()] = (
                hashlib.sha256(content_bytes(item, semantic)).hexdigest() if item.is_file() else "missing")
    return result


def tree(root, version):
    return hashes(root, [p.format(v=version) for p in FAMILIES.values()])


def repair_scope(root, version, invalid=(), references=()):
    """六类存在性 + 显式机检失效目标；不把索引当内容，空文件视为缺件。"""
    dirs = {k: p.format(v=version) for k, p in FAMILIES.items()}
    targets, missing = {}, []
    files = {}
    for family, rel in dirs.items():
        files[family] = [p for p in local(root, rel).rglob("*.md")
                         if p.name != "00_索引.md" and not p.name.startswith(("_", "98_", "99_", "输入变更"))]
    categories = [
        ("requirements", "01_研发需求.md", files["requirements"]),
        ("design", "01_详细设计.md", files["design"]),
        ("plan", "01_研发执行计划.md", files["plan"]),
        ("selftest", "01_研发自测方案.md", [p for p in files["selftest"] if "自测方案" in p.name]),
        ("selftest", "01_测试环境与账号.md", [p for p in files["selftest"] if "测试环境与账号" in p.name]),
        ("selftest", "02_全量自测用例.md", [p for p in files["selftest"]
            if "自测用例" in p.name or "SUITE-" in p.read_text(encoding="utf-8")]),
    ]
    for family, default, candidates in categories:
        if not any(p.read_bytes().strip() for p in candidates):
            names = [p.relative_to(root).as_posix() for p in candidates] or [dirs[family] + "/" + default]
            for name in names:
                targets[name] = family
                missing.append(name)
    invalid = set(invalid)
    references = set(references)
    state = State(root, version)
    for stage in ("plan", "case"):
        if stage in state.nodes and not state.valid(stage):
            invalid.update(p for p in hashes(root, state.nodes[stage]["outputs"]) if p.endswith(".md"))
    if state.nodes.get("case") and state.valid("case") and not state.valid("ref"):
        # 生成结果可复用但计划映射变化时，仅授权回填对应 case，不重生成。
        references.update(state.nodes["case"].get("raw", {}))
    for name in sorted(invalid):
        local(root, name)
        family = next((f for f, d in dirs.items() if name.startswith(d + "/")), None)
        if family is None:
            raise ValueError(f"失效目标不属于规划产物: {name}")
        targets[name] = family
    indexes = {dirs[f] + "/00_索引.md" for f in targets.values()}
    for d in dirs.values():
        if not (root / d / "00_索引.md").is_file():
            indexes.add(d + "/00_索引.md")
    before = tree(root, version)
    references = sorted(set(references))
    for name in references:
        if name not in before or before[name] == "missing":
            raise ValueError(f"必要引用回写必须指向已存在规划文件: {name}")
    writable = sorted(set(targets) | indexes | set(references))
    # 上游按真实依赖取，不为一份环境配置重读/重生成全部四族。
    upstream = {"requirements": [f"docs/requirements/{version}/产品提供", f"docs/prototype/{version}"],
                "design": [dirs["requirements"]], "plan": [dirs["requirements"], dirs["design"]],
                "selftest": [dirs["requirements"], dirs["design"], dirs["plan"]]}
    inputs = sorted({p for family in targets.values() for p in upstream[family]})
    return {"targets": targets, "missing": missing, "necessary_indexes": sorted(indexes),
            "necessary_references": references, "required_inputs": hashes(root, inputs),
            "writable": writable, "readonly": {p: h for p, h in before.items() if p not in writable},
            "before": before, "reused": sorted(p for p, h in before.items()
                                               if p not in writable and h != "missing")}


def repair_check(root, version, scope):
    after = tree(root, version)
    allowed = set(scope["writable"])
    changed = sorted(p for p in set(scope["before"]) | set(after)
                     if scope["before"].get(p) != after.get(p) and not p.endswith("/"))
    unexpected = [p for p in changed if p not in allowed and
                  not (p in scope["before"] and scope["before"][p] == "missing")]
    required = set(scope["targets"]) | set(scope["necessary_indexes"])
    missing = sorted(p for p in required if not local(root, p).is_file()
                     or not local(root, p).read_bytes().strip())
    return {"ok": not unexpected and not missing, "redone": [p for p in changed if p in allowed],
            "reused": [p for p in scope["reused"] if p not in changed],
            "missing": missing, "unexpected": unexpected}


class State:
    def __init__(self, root, version):
        self.root, self.version = root, version
        self.path = root / "memory" / version / ".planning-state.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {"stages": {}}
        self.nodes = self.data["stages"]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.path)

    def fingerprint(self, stage, inputs, params):
        return digest({"inputs": hashes(self.root, inputs, semantic=True), "params": params,
                       "deps": {d: self.nodes.get(d, {}).get("token") for d in STAGES[stage]}})

    def valid(self, stage):
        node = self.nodes.get(stage, {})
        if node.get("status") != "pass" or not all(self.valid(d) for d in STAGES[stage]):
            return False
        return (node["fingerprint"] == self.fingerprint(stage, node["inputs"], node["params"])
                and node.get("observed") == hashes(self.root, node["outputs"]))

    def start(self, stage, inputs, outputs, params=(), force=False):
        if not inputs or not outputs:
            raise ValueError("每阶段必须声明真实输入和产物路径")
        absent = [p for p, value in hashes(self.root, inputs, semantic=True).items()
                  if value in ("missing", "empty-directory")]
        if absent:
            return {"stage": stage, "action": "missing", "missing": absent}
        fp = self.fingerprint(stage, inputs, params)
        if not force and self.valid(stage) and self.nodes[stage]["fingerprint"] == fp \
                and self.nodes[stage]["outputs"] == outputs:
            return {"stage": stage, "action": "reused", "token": self.nodes[stage]["token"]}
        blocked = [d for d in STAGES[stage] if not self.valid(d)]
        if blocked:
            return {"stage": stage, "action": "missing", "missing": blocked}
        self.nodes[stage] = {"status": "running", "inputs": inputs, "outputs": outputs,
                             "params": params, "fingerprint": fp}
        self.save()
        return {"stage": stage, "action": "redone", "fingerprint": fp}

    def finish(self, stage, result):
        node = self.nodes.get(stage, {})
        if node.get("status") != "running":
            raise ValueError(f"{stage} 没有对应 start")
        observed = hashes(self.root, node["outputs"])
        files = [local(self.root, p) for p in observed if not p.endswith("/")]
        ok = (result.get("status") == "pass" and result.get("exit_code") == 0
              and files and all(p.is_file() and p.stat().st_size for p in files)
              and node["fingerprint"] == self.fingerprint(stage, node["inputs"], node["params"])
              and all(self.valid(d) for d in STAGES[stage]))
        node.update(status="pass" if ok else "failed", result=result, observed=observed)
        node["token"] = digest({"fingerprint": node["fingerprint"], "outputs": observed})
        if ok and stage == "case":
            node["raw"] = {p: base64.b64encode(local(self.root, p).read_bytes()).decode()
                           for p in observed if p.endswith(".md")}
        self.save()
        return {"stage": stage, "ok": bool(ok), "action": "redone", "result": result}

    def status(self):
        if not self.nodes:
            return {"ok": True, "reused": [], "redone": [], "missing": [], "skipped": "no-parallel-run"}
        reused = [s for s in STAGES if self.valid(s)]
        return {"ok": len(reused) == len(STAGES), "reused": reused,
                "redone": [s for s in STAGES if s in self.nodes and s not in reused],
                "missing": [s for s in STAGES if s not in self.nodes]}

    def refs(self, home):
        """依赖脚本真实退出结果落盘；回填从原始用例快照重放，计划变化不重生成用例。"""
        v = self.version
        cases = f"docs/testing/{v}/研发自测"
        mapping = f"memory/{v}/.plan-refs.json"
        receipts = f"memory/{v}/.planning-results"
        scripts = {
            "map": home / "skills/dev-execution-planner/scripts/export_plan_refs.py",
            "ref": home / "skills/dev-manual-testcase/scripts/resolve_plan_refs.py",
            "verify": home / "skills/dev-manual-testcase/scripts/check_suite_upstream.py"}
        actions = {"reused": [], "redone": [], "missing": []}
        for stage in ("map", "ref", "verify"):
            if not all(self.valid(d) for d in STAGES[stage]):
                actions["missing"].append(stage)
                continue
            script = scripts[stage]
            # 工具版本本身亦是输入；使用内容 hash，不依赖部署位置。
            params = [hashlib.sha256(script.read_bytes()).hexdigest()]
            inputs = ([f"docs/plans/{v}"] if stage == "map" else
                      [mapping] if stage == "ref" else [cases, f"docs/plans/{v}"])
            # verify 结果写文件，避免用一个内存中的 exit 0 充当持久产物。
            output = mapping if stage == "map" else receipts + f"/{stage}.json"
            started = self.start(stage, inputs, [output], params)
            actions[started["action"]].append(stage)
            if started["action"] != "redone":
                continue
            if stage == "map":
                local(self.root, mapping).unlink(missing_ok=True)
                cmd = [sys.executable, str(script), str(self.root / f"docs/plans/{v}"),
                       "--cases-dir", str(self.root / cases), "--out", str(self.root / mapping), "--json"]
                cp = subprocess.run(cmd, cwd=self.root, capture_output=True, text=True)
            elif stage == "ref":
                # 不先覆盖真实用例；任何失败时仍保留之前有效产物。
                with tempfile.TemporaryDirectory(prefix="aidp-plan-ref-") as temp:
                    # 保留项目内目录深度，否则 ../../../ 在浅层临时根会被 normpath 截短。
                    staged = Path(temp) / cases
                    staged.mkdir(parents=True)
                    raw = self.nodes["case"].get("raw", {})
                    for name, body in raw.items():
                        dst = staged / Path(name).relative_to(cases)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        dst.write_bytes(base64.b64decode(body))
                    cp = subprocess.run([sys.executable, str(script), str(staged), "--map",
                                         str(self.root / mapping), "--json"], capture_output=True, text=True)
                    if cp.returncode == 0 and raw:
                        for name in raw:
                            local(self.root, name).write_bytes((staged / Path(name).relative_to(cases)).read_bytes())
                        # 仅认可本脚本刚执行的确定性回填，不改变生成 token。
                        self.nodes["case"]["observed"] = hashes(self.root, self.nodes["case"]["outputs"])
                    elif not raw:
                        cp = subprocess.CompletedProcess([], 1, "", "原始用例快照缺失")
            else:
                cp = subprocess.run([sys.executable, str(script), str(self.root / cases)],
                                    cwd=self.root, capture_output=True, text=True)
                unresolved = [p.as_posix() for p in (self.root / cases).rglob("*.md")
                              if "⟨PLAN-REF:" in p.read_text(encoding="utf-8")]
                if unresolved:
                    cp = subprocess.CompletedProcess(cp.args, 1, cp.stdout, "unresolved refs: " + str(unresolved))
            result = {"status": "pass" if cp.returncode == 0 else "fail", "exit_code": cp.returncode,
                      "stdout": cp.stdout, "stderr": cp.stderr}
            receipt = local(self.root, receipts + f"/{stage}.json")
            receipt.parent.mkdir(parents=True, exist_ok=True)
            receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            finished = self.finish(stage, result)
            if not finished["ok"]:
                break
        return {**actions, "ok": self.valid("verify"), "stages": self.status()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--version", required=True)
    sub = ap.add_subparsers(dest="action", required=True)
    for name in ("scope", "begin-repair"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--invalid", action="append", default=[])
        cmd.add_argument("--reference", action="append", default=[])
    sub.add_parser("check-repair")
    sub.add_parser("status")
    start = sub.add_parser("start")
    start.add_argument("stage", choices=("plan", "case"))
    start.add_argument("--input", action="append", required=True)
    start.add_argument("--output", action="append", required=True)
    start.add_argument("--param", action="append", default=[])
    start.add_argument("--force", action="store_true")
    finish = sub.add_parser("finish")
    finish.add_argument("stage", choices=("plan", "case"))
    finish.add_argument("--result", required=True, help="子命令真实 JSON 结果文件，含 status/exit_code")
    refs = sub.add_parser("refs")
    refs.add_argument("--aidp-home", default=str(Path(__file__).resolve().parents[1]))
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not re.fullmatch(r"[Vv]\d+(?:\.\d+){0,2}", args.version):
        ap.error("版本号须为 V主[.次[.补丁]]")
    directory = root / "memory" / args.version
    try:
        if args.action == "scope":
            result = repair_scope(root, args.version, args.invalid, args.reference)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            # 并行两支串行更新短状态；生成工作本身不持有锁。
            with (directory / ".planning-state.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                state = State(root, args.version)
                if args.action == "begin-repair":
                    if state.data.get("repair"):
                        prior = repair_check(root, args.version, state.data["repair"])
                        if prior["unexpected"]:
                            raise ValueError("上轮只读文件被改写，不能刷新基线掩盖: " + ", ".join(prior["unexpected"]))
                    result = repair_scope(root, args.version, args.invalid, args.reference)
                    state.data["repair"] = result
                    state.save()
                elif args.action == "check-repair":
                    result = repair_check(root, args.version, state.data["repair"])
                elif args.action == "start":
                    result = state.start(args.stage, args.input, args.output, args.param, args.force)
                elif args.action == "finish":
                    result = state.finish(args.stage, json.loads(local(root, args.result).read_text(encoding="utf-8")))
                elif args.action == "refs":
                    result = state.refs(Path(args.aidp_home).resolve())
                else:
                    result = state.status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get("ok") is False or result.get("action") == "missing" else 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
