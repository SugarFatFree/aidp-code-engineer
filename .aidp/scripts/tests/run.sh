#!/usr/bin/env bash
# 一次跑**全部**确定性脚本回归单测。任一失败即非零退出（供 CI）。
#
# 用法（仓库根）：bash .aidp/scripts/tests/run.sh
#
# ★ 收录铁律：**全仓每一个** `tests/` 目录下的 test_*.py / test_*.js 都必须在此登记
#   —— 当前有两处：`.aidp/scripts/tests/` 与 `.aidp/skills/aidp-code-engineer/scripts/tests/`。
#   ⛔ 别把"tests/"默读成只有前者：后者守的是脚手架 skill 自身（镜像器 / 脚手架库 / 记忆文件同步器），
#   漏收即它红了也没人知道。漏收 = 该套件永远绿不了也红不了（与"护栏无调用方"同类）。
#   新增测试文件时同步加一行；勿依赖通配自动发现（顺序与跳过条件需显式可读）。
#   `test_guard_scripts.py` 的「run.sh 收录全部 test_* 文件」用例会机器回检本清单。
set -u
here="$(cd "$(dirname "$0")" && pwd)"
# ⛔ 必须是**仓库根**（`.aidp/scripts/tests` 往上 3 级）：凡是按仓库根解析路径的断言都依赖 cwd。
#   cd 错一级 = 这个受祝福的入口恒红，真新增的破坏混在老红里看不出来（恒红 = 等于没有）。
root="$(cd "$here/../../.." && pwd)"
cd "$root"
# 不写字节码：部分用例会执行脚手架 bundle（assets/）里的脚本副本，落下 __pycache__ 即被 mirror --check 判为漂移
export PYTHONDONTWRITEBYTECODE=1

rc=0
suites=0
failed_suites=()
total_pass=0
total_fail=0
total_skip=0
log="$(mktemp)"
trap 'rm -f "$log"' EXIT

# run <标题> <命令...>：执行一个套件，汇总其「══ 结果：N passed / M failed[ / K skipped] ══」行
run() {
  local title="$1"; shift
  echo ""
  echo "════════ ${title} ════════"
  suites=$((suites + 1))
  local code=0
  "$@" >"$log" 2>&1 || code=$?
  cat "$log"
  local line
  line="$(grep -E '══ 结果：[0-9]+ passed / [0-9]+ failed' "$log" | tail -1)"
  if [ -n "$line" ]; then
    local p f s
    p="$(sed -E 's/.*结果：([0-9]+) passed.*/\1/' <<<"$line")"
    f="$(sed -E 's/.* ([0-9]+) failed.*/\1/' <<<"$line")"
    s="$(grep -oE '[0-9]+ skipped' <<<"$line" | grep -oE '[0-9]+' || true)"
    total_pass=$((total_pass + p))
    total_fail=$((total_fail + f))
    total_skip=$((total_skip + ${s:-0}))
  fi
  # 「N passed, M failed」形态
  line="$(grep -E '^[0-9]+ passed, [0-9]+ failed' "$log" | tail -1)"
  if [ -n "$line" ]; then
    total_pass=$((total_pass + $(grep -oE '^[0-9]+' <<<"$line")))
    total_fail=$((total_fail + $(sed -E 's/.*, ([0-9]+) failed.*/\1/' <<<"$line")))
  fi
  # `--selftest` JSON 形态：逐条 {"ok": true|false}
  if grep -q '"cases"' "$log" && ! grep -qE '══ 结果|^Ran [0-9]+ tests?' "$log"; then
    total_pass=$((total_pass + $(grep -cE '"ok": ?true' "$log" || true)))
    total_fail=$((total_fail + $(grep -cE '"ok": ?false' "$log" || true)))
  fi
  # unittest 形态（脚手架侧）：「Ran N tests」+「OK (skipped=K)」
  line="$(grep -E '^Ran [0-9]+ tests?' "$log" | tail -1)"
  if [ -n "$line" ]; then
    local n k
    n="$(grep -oE '[0-9]+' <<<"$line" | head -1)"
    k="$(grep -oE 'skipped=[0-9]+' "$log" | tail -1 | grep -oE '[0-9]+' || true)"
    local uf ue
    uf="$(grep -oE 'failures=[0-9]+' "$log" | tail -1 | grep -oE '[0-9]+' || true)"
    ue="$(grep -oE 'errors=[0-9]+' "$log" | tail -1 | grep -oE '[0-9]+' || true)"
    total_pass=$((total_pass + n - ${k:-0} - ${uf:-0} - ${ue:-0}))
    total_fail=$((total_fail + ${uf:-0} + ${ue:-0}))
    total_skip=$((total_skip + ${k:-0}))
  fi
  if [ "$code" -ne 0 ]; then
    rc=1
    failed_suites+=("$title")
  fi
}

# ── 脚本本体（.aidp/scripts/）──
run "test_report_schema.py（报告数据契约）" python3 .aidp/scripts/tests/test_report_schema.py
run "test_commit_gate.py（提交前门禁 + 提交/推送分类）" python3 .aidp/scripts/tests/test_commit_gate.py
run "test_notify.py（里程碑通知：渠道渲染 / 签名 / 回落 / 退出码）" python3 .aidp/scripts/tests/test_notify.py
run "cicd_watch.py --selftest（CICD 多提供方监听：脚本自带离线自测）" python3 .aidp/scripts/cicd_watch.py --selftest
run "test_agent_sync.py（多 Agent 装配：agent_env / agent_sync）" python3 .aidp/scripts/tests/test_agent_sync.py
run "test_guard_scripts.py（确定性护栏全套）" python3 .aidp/scripts/tests/test_guard_scripts.py
run "test_release_gates.py（发布域：增量轨/只读采集/零残留总闸/推送状态）" python3 .aidp/scripts/tests/test_release_gates.py
run "test_report_immutability.py（测试链：单一信源/不可变锁/renderMode/3i 窗口）" python3 .aidp/scripts/tests/test_report_immutability.py
run "test_field_level_and_evidence.py（写读错层 / 保护面 / 落点收编）" python3 .aidp/scripts/tests/test_field_level_and_evidence.py
run "test_offchain_scope.py（约定41 链外动作边界 + 约定17 反向门）" python3 .aidp/scripts/tests/test_offchain_scope.py
run "test_baseline_archive.py（baseline 归档回落 + decisions 双信源）" python3 .aidp/scripts/tests/test_baseline_archive.py
run "test_unattended_recovery.py（无人值守失败处置 + 自动恢复）" python3 .aidp/scripts/tests/test_unattended_recovery.py
run "test_aidp_scheduler.py（7×24 操作系统调度）" python3 .aidp/scripts/tests/test_aidp_scheduler.py
run "test_agent_sync_router.py（原生命令生成 + 参数保真）" python3 .aidp/scripts/tests/test_agent_sync_router.py
run "test_runtime_and_vcs.py（运行根解析 + VCS 能力降级）" python3 .aidp/scripts/tests/test_runtime_and_vcs.py
run "test_command_skill_contracts.py（命令 ↔ SKILL 调用契约）" python3 .aidp/scripts/tests/test_command_skill_contracts.py
run "test_doc_reference_guards.py（符号引用 / CLI 归属 / 私有痕迹 三道门）" python3 .aidp/scripts/tests/test_doc_reference_guards.py

# ── 脚手架 skill 侧（.aidp/skills/aidp-code-engineer/scripts/tests/）──
run "test_mirror.py（脚手架侧：本体→bundle 镜像）" python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_mirror.py
run "test_scaffold_lib.py（脚手架侧：脚手架库）" python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_lib.py
run "test_scaffold_modes.py（脚手架侧：init / migrate / upgrade 三模式）" python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_scaffold_modes.py
run "test_sync_memory_md.py（脚手架侧：项目记忆文件同步）" python3 .aidp/skills/aidp-code-engineer/scripts/tests/test_sync_memory_md.py

# ── 渲染（需 node）──
if command -v node >/dev/null 2>&1; then
  run "test_report_render.js（报告渲染口径）" node .aidp/scripts/tests/test_report_render.js
else
  echo ""
  echo "⏭️ 无 node → 跳过 test_report_render.js（渲染类断言需 node）"
  total_skip=$((total_skip + 1))
fi

echo ""
echo "════════════════════════════════════════"
echo "套件 ${suites} 个 · 断言 ${total_pass} passed / ${total_fail} failed / ${total_skip} skipped"
echo "（跳过项含：依赖脚手架 skill 内部实现的分组，设 AIDP_TEST_SKILL_INTERNALS=1 开启）"
if [ $rc -eq 0 ]; then
  echo "✅ 全部单测通过"
else
  echo "❌ 有单测失败：${failed_suites[*]}"
fi
exit $rc
