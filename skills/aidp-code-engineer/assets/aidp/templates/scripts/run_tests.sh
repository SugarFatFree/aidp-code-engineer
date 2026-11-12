#!/usr/bin/env bash
# run_tests.sh —— 下游项目测试入口范例（下游自有文件；模板只给范例，不自动安装）。
#
# 采用：复制到项目的 scripts/run_tests.sh，把 AIDP_HOME 改成运行真源目录（Claude Code 为 .claude，
# 使用 Codex / DeepSeek Harness 时为 .agents），再按项目技术栈改下面 TEST_CMD / LINT_CMD 两处。
#
# 约束（由 test_command_guard.py 机器强制，不靠自觉）：
#   · 无参数 / 参数是目录      → 拒绝，并提示改用相关测试白名单
#   · --related               → 先算白名单（select_related_tests.py），只跑白名单内测试
#   · 显式测试文件参数          → 须在白名单内（白名单缺失时放行并告警）
#   · --allow-full            → 仅当执行上下文真实持有 full-regression（autopilot 测试编排）才放行
#   · --lint                  → 只检查改动文件（ruff 无参数/目录会被拒绝）
#
# 用法：
#   bash scripts/run_tests.sh --related                       # 日常：改动相关测试
#   bash scripts/run_tests.sh tests/unit/test_a.py            # 显式文件（须在白名单内）
#   bash scripts/run_tests.sh --lint                          # 只 lint 改动文件
#   bash scripts/run_tests.sh --allow-full --execution-context <ctx.json>   # 仅授权后的全量
set -euo pipefail

AIDP_HOME="${AIDP_HOME:-.claude}"                      # ← 改成运行真源目录
GUARD="$AIDP_HOME/scripts/test_command_guard.py"
SELECT="$AIDP_HOME/scripts/select_related_tests.py"
TEST_CMD=(python3 -m pytest -q)                        # ← 改成项目的测试命令（后接文件列表）
LINT_CMD=(ruff check)                                  # ← 改成项目的 lint 命令（后接文件列表）

mode="files"; allow_full=(); ctx=(); files=()
while [ $# -gt 0 ]; do
  case "$1" in
    --related) mode="related" ;;
    --lint) mode="lint" ;;
    --allow-full) allow_full=(--allow-full) ;;
    --execution-context) ctx=(--execution-context "$2"); shift ;;
    *) files+=("$1") ;;
  esac
  shift
done

wrap() { python3 "$GUARD" wrap ${allow_full[@]+"${allow_full[@]}"} ${ctx[@]+"${ctx[@]}"} -- "$@"; }

if [ "${#allow_full[@]}" -gt 0 ]; then
  # 全量：是否放行完全由 guard 按执行上下文裁决；未授权会在这里被拒绝并以非零退出
  wrap "${TEST_CMD[@]}"
  exit $?
fi

if [ "$mode" = "lint" ]; then
  mapfile -t changed < <(python3 "$GUARD" changed --ext .py)
  [ "${#changed[@]}" -gt 0 ] || { echo "run_tests.sh: 没有改动的源文件，无需 lint"; exit 0; }
  wrap "${LINT_CMD[@]}" "${changed[@]}"
  exit $?
fi

if [ "$mode" = "related" ]; then
  related_json="$(mktemp)"
  python3 "$SELECT" ${ctx[@]+"${ctx[@]}"} --json > "$related_json"
  mapfile -t files < <(python3 -c 'import json,sys; print("\n".join(json.load(open(sys.argv[1]))["tests"]))' "$related_json")
  rm -f "$related_json"
  [ "${#files[@]}" -gt 0 ] || { echo "run_tests.sh: 没有相关测试（见 select_related_tests.py 的 unmapped），不回落全量"; exit 0; }
fi

if [ "${#files[@]}" -eq 0 ]; then
  echo "run_tests.sh: 拒绝无参数运行（等同全量）。请用 --related 或显式传入白名单内的测试文件。" >&2
  echo "  白名单：python3 $SELECT --json；全量仅在 autopilot 授权后经 --allow-full 放行。" >&2
  exit 2
fi
wrap "${TEST_CMD[@]}" "${files[@]}"
