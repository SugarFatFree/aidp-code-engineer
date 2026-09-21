#!/usr/bin/env python3
"""P1-7 单测：报告数据契约校验（emit-report.validate_payload）+ buildNo 派生 + 示例文件自校验（防回归）。
纯标准库，直接 `python3 .aidp/scripts/tests/test_report_schema.py` 运行；退出码 0=全绿、1=有失败。"""
import glob
import importlib.util
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


er = _load(".aidp/scripts/emit-report.py", "er")
gate = _load(".aidp/scripts/autopilot-ceremony-gate.py", "gate")  # 复用 _extract_payload 解析 .js fixture / 示例

_fails = []


def check(cond, msg):
    print(("  ✅ " if cond else "  ❌ ") + msg)
    if not cond:
        _fails.append(msg)


def load_js(rel, global_var="__BUILDS__"):
    """加载 .js data payload：先试 json 解析（emit-report 生成的合规 JSON / 本仓 JSON fixture），
    失败（手写示例是 JS 对象字面量：无引号键 + 注释）则回退 node eval。node 缺失且 json 失败 → 返回 None。"""
    abs_p = os.path.join(ROOT, rel)
    p, err = gate._extract_payload(abs_p)
    if err is None:
        return p
    node = shutil.which("node")
    if not node:
        return None
    js = ('let a=[];global.window={};window.__BUILDS__=a;window.__AIRUNS__=a;'
          'eval(require("fs").readFileSync(process.argv[1],"utf8"));'
          'process.stdout.write(JSON.stringify(a[0]||{}));')
    out = subprocess.run([node, "-e", js, abs_p], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else None


print("① buildNo 派生（P1-6）")
p = {"build": "V0.10.2_build1002"}
er.enrich_build_no(p, "V0.10.2_build1002")
check(p.get("buildNo") == 1002, "V0.10.2_build1002 → buildNo=1002")
p2 = {"build": "V0.10.2_build1002", "buildNo": 7}
er.enrich_build_no(p2, "V0.10.2_build1002")
check(p2["buildNo"] == 7, "已有 buildNo 不覆盖")

print("② 问题数据 fixture → 精确报出各类问题（P0-1）")
test_bad = load_js(".aidp/scripts/tests/fixtures/test_bad_build1002.js")
er.enrich_build_no(test_bad, test_bad["build"])  # 模拟 emit-report 先派生 buildNo
e_test = er.validate_payload("test", test_bad)
check(any("passRate" in x for x in e_test), "test：捕获 passRate 口径异常(100.0)")
check(any("cases[0] 缺字段 `title`" in x for x in e_test), "test：捕获 cases 别名 name→title")
check(any("cases[0] 缺字段 `result`" in x for x in e_test), "test：捕获 cases 别名 status→result")

exec_bad = load_js(".aidp/scripts/tests/fixtures/exec_bad_build1002.js")
er.enrich_build_no(exec_bad, exec_bad["build"])
e_exec = er.validate_payload("exec", exec_bad)
check(any("risks" in x and "dict" in x for x in e_exec), "exec：捕获 risks 分组对象(白屏根因)")
check(any("todos" in x for x in e_exec), "exec：捕获 todos 裸字符串")
check(any("featureRate" in x for x in e_exec), "exec：捕获 featureRate 字符串口径")
check(any("testPassRate" in x for x in e_exec), "exec：捕获 testPassRate 字符串口径")

print("③ 示例契约文件零错误（示例即契约、永不与校验器分叉）")
# ★ 必须 glob 全部 示例_*.js，不能只校 build1001：曾因只校第一份，build1002 的
#   summary 长期与 cases[] 失真却无人发现（示例是下游照抄的模板，失真会被复制到每个下游）。
for kind, cn in (("test", "AI测试报告"), ("exec", "AI执行报告")):
    examples = sorted(glob.glob(os.path.join(
        ROOT, ".aidp/templates/reports", cn, "data", "示例_*.js")))
    check(bool(examples), f"{kind} 示例文件存在（data/示例_*.js）")
    for abs_p in examples:
        rel = os.path.relpath(abs_p, ROOT)
        payload = load_js(rel)
        if payload is None:
            print(f"  ⏭️ {rel} 需 node 解析（JS 字面量），本环境无 node → 跳过（非失败）")
            continue
        errs = er.validate_payload(kind, payload)
        check(not errs, f"{rel} 契约零错误" + ("" if not errs else " → " + "; ".join(errs)))

print("④ 防回归：把示例 passRate 改坏 → 校验必红")
bad_ex = load_js(".aidp/templates/reports/AI测试报告/data/示例_build1001.js")
if bad_ex is None:
    print("  ⏭️ 需 node 解析示例，本环境无 node → 跳过（非失败）")
elif isinstance(bad_ex.get("summary"), dict):
    bad_ex["summary"]["passRate"] = 84.0  # 0~100 口径误填
    check(bool(er.validate_payload("test", bad_ex)), "示例 passRate 改 84.0 → 校验报错")

print("⑤ 防回归：计数溯源三门（分母注水 / 四态不平 / 套件分解打架）")
base = load_js(".aidp/templates/reports/AI测试报告/data/示例_build1001.js")
if base is None:
    print("  ⏭️ 需 node 解析示例，本环境无 node → 跳过（非失败）")
else:
    def _mutate(fn, want, label):
        """深拷一份合规示例 → 按 fn 改坏一处 → 断言校验必报出含 want 的错。"""
        p = json.loads(json.dumps(base))
        fn(p)
        errs = er.validate_payload("test", p)
        check(any(want in e for e in errs),
              label + ("" if any(want in e for e in errs)
                       else f" → 实际错误: {errs or '（无，漏网）'}"))

    # 分母注水：total 与 cases[] 明细条数脱节（本轮真实缺陷：示例声称 50 条、只列 13 条）
    def _inflate(p):
        p["summary"]["total"] = 50
        p["summary"]["pass"] = 43   # 保持五态之和 = total，绕过①、专测②
        for st in p["suites"]:
            st["total"] += 0
        p["suites"][0]["total"] += 37
        p["suites"][0]["pass"] += 37
    _mutate(_inflate, "明细条数", "total=50 但 cases[] 仅 13 条 → 报「分母不可溯源」")

    # 五态之和 ≠ total
    _mutate(lambda p: p["summary"].update(total=99),
            "五态之和", "summary.total=99 与五态之和不符 → 报错")

    # 套件分解与总账打架
    def _skew_suite(p):
        p["suites"][0]["total"] += 5

    _mutate(_skew_suite, "suites[] 分解", "suites 合计多 5 条 → 报「与 summary 总账不符」")

    # 反向：合规示例不得被这三门误伤（假红比漏网更难排查）
    check(not er.validate_payload("test", json.loads(json.dumps(base))),
          "未改动的合规示例 → 三门均不误报")

print()
if _fails:
    print(f"❌ {len(_fails)} 项失败")
    sys.exit(1)
print("✅ 全部通过")
sys.exit(0)
