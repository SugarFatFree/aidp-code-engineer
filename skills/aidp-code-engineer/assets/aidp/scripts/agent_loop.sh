#!/usr/bin/env bash
# agent_loop.sh —— 以非交互模式唤起 AIDP 命令（Claude Code / Codex / DeepSeek Harness 通用）
#
# 两种形态：
#   "$AIDP_HOME/scripts/agent_loop.sh" --once sprint-autopilot --unattended  # 单次执行
#   "$AIDP_HOME/scripts/agent_loop.sh" 10m sprint-autopilot --unattended     # 前台循环
#
# 7×24 推荐由 `python3 $AIDP_HOME/scripts/aidp_scheduler.py install` 为开发链路与测试链路各装一个
# 操作系统定时任务，每个任务调用本脚本的 --once 形态。
#
# 每轮都会：
#   · 自动补齐 `--unattended --no-loop`（已带则不重复）——被操作系统调度唤起即「无人值守 + 有下一轮」；
#   · export AIDP_TICK_COMMAND=<命令>（Stop 护栏据此识别本进程是否在执行 autopilot tick）、
#     export ARGUMENTS="<参数>"（供原生命令正文读取）；
#   · 加载 ~/.config/aidp/env（可选，KEY=VALUE 行；放通知 webhook、CICD 令牌等凭据环境变量）；
#   · flock 互斥：同一命令上一轮未结束则本轮跳过；
#   · 日志追加到 memory/.aidp/logs/<命令>.log。
#
# Agent：AIDP_AGENT 环境变量 > memory/aidp-config.yaml 的 scheduler.agent（auto 时按 agent_env.py detect 取第一个）。
# 执行命令模板（{prompt} 为占位符）：AIDP_AGENT_EXEC > scheduler.exec.<agent> > 内置默认。
#   claude 内置默认：claude -p --permission-mode acceptEdits {prompt}
#   codex  内置默认：codex exec --sandbox workspace-write {prompt}
#   dsh    无内置默认：须在 scheduler.exec.dsh 或 AIDP_AGENT_EXEC 中配置（写法以所用版本官方文档为准）
# 各 CLI 的参数以所用版本官方文档为准；非交互执行需预授权工具权限，见 $AIDP_HOME/reference/agent-tools.md 第三节。
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
AIDP_HOME="${AIDP_HOME:-$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)}"
home_name="$(basename -- "$AIDP_HOME")"
host_name="$(basename -- "$(dirname -- "$AIDP_HOME")")"
if [ "$home_name" = "aidp" ] && { [ "$host_name" = ".claude" ] || [ "$host_name" = ".agents" ]; }; then
  default_root="$(CDPATH= cd -- "$AIDP_HOME/../.." && pwd)"
elif [ "$home_name" = ".aidp" ]; then
  default_root="$(CDPATH= cd -- "$AIDP_HOME/.." && pwd)"
else
  echo "[agent_loop] 非法 AIDP_HOME: $AIDP_HOME" >&2; exit 2
fi
root="${AIDP_PROJECT_ROOT:-$default_root}"
export AIDP_HOME AIDP_PROJECT_ROOT="$root"
cd "$root"

usage() {
  echo "用法: $0 --once <命令名> [参数...]" >&2
  echo "      $0 <间隔，如 5m|10m|1h> <命令名> [参数...]" >&2
  exit 2
}
[ $# -ge 2 ] || usage

once=0
secs=0
if [ "$1" = "--once" ]; then
  once=1; shift
else
  interval="$1"; shift
  case "$interval" in
    *s) secs=${interval%s} ;;
    *m) secs=$(( ${interval%m} * 60 )) ;;
    *h) secs=$(( ${interval%h} * 3600 )) ;;
    *) usage ;;
  esac
fi
[ $# -ge 1 ] || usage
cmd="$1"; shift

# 参数补齐：--unattended / --no-loop
extra=()
has_unattended=0; has_no_loop=0
for t in "$@"; do
  [ "$t" = "--unattended" ] && has_unattended=1
  [ "$t" = "--no-loop" ] && has_no_loop=1
done
[ "$has_unattended" = 1 ] || extra+=("--unattended")
[ "$has_no_loop" = 1 ] || extra+=("--no-loop")
args="$* ${extra[*]:-}"
args="$(echo "$args" | sed -e 's/^ *//' -e 's/ *$//')"

if [ -f "$HOME/.config/aidp/env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$HOME/.config/aidp/env"
  set +a
fi

cfg_get() {
  # $1 = agent | exec.<agent>
  python3 - "$1" <<'PY' 2>/dev/null || true
import os, sys
sys.path.insert(0, os.path.join(os.environ["AIDP_HOME"], "scripts"))
import aidp_config
c = aidp_config.scheduler_config(".")
k = sys.argv[1]
if k == "agent":
    print(c.get("agent") or "auto")
elif k.startswith("exec."):
    print((c.get("exec") or {}).get(k[5:], ""))
PY
}

agent="${AIDP_AGENT:-}"
if [ -z "$agent" ]; then
  agent="$(cfg_get agent)"
  [ -n "$agent" ] || agent=auto
fi
if [ "$agent" = "auto" ]; then
  agent="$(python3 "$AIDP_HOME/scripts/agent_env.py" detect | python3 -c 'import json,sys; print(json.load(sys.stdin)["agents"][0])')"
fi
agent="${agent%%,*}"

case "$agent" in
  codex)  prompt="\$${cmd} ${args}"; default_exec='codex exec --sandbox workspace-write {prompt}' ;;
  dsh)    prompt="/${cmd} ${args}";  default_exec='' ;;
  claude) prompt="/${cmd} ${args}";  default_exec='claude -p --permission-mode acceptEdits {prompt}' ;;
  *) echo "[agent_loop] 未知 Agent: $agent" >&2; exit 2 ;;
esac
exec_tpl="${AIDP_AGENT_EXEC:-}"
[ -n "$exec_tpl" ] || exec_tpl="$(cfg_get "exec.$agent")"
[ -n "$exec_tpl" ] || exec_tpl="$default_exec"
if [ -z "$exec_tpl" ]; then
  echo "[agent_loop] Agent=$agent 没有内置的非交互执行命令：请在 memory/aidp-config.yaml 的 scheduler.exec.$agent" \
       "或环境变量 AIDP_AGENT_EXEC 中配置（{prompt} 为占位符，写法以该 Agent 当前版本官方文档为准）" >&2
  exit 2
fi

export AIDP_TICK_COMMAND="$cmd"
export ARGUMENTS="$args"

mkdir -p memory/.aidp/locks memory/.aidp/logs
lock="memory/.aidp/locks/loop-${cmd}.lock"
log="memory/.aidp/logs/${cmd}.log"

run_one() {
  (
    if ! flock -n 9; then
      echo "[agent_loop] $(date '+%F %T') ${cmd} 上一轮仍在运行，跳过" >>"$log"
      exit 0
    fi
    quoted=$(printf '%q' "$prompt")
    echo "[agent_loop] $(date '+%F %T') 开始 agent=$agent prompt=$prompt" >>"$log"
    rc=0
    eval "${exec_tpl//\{prompt\}/$quoted}" >>"$log" 2>&1 || rc=$?
    echo "[agent_loop] $(date '+%F %T') 结束 rc=$rc" >>"$log"
    exit "$rc"
  ) 9>"$lock"
}

if [ "$once" = 1 ]; then
  python3 "$AIDP_HOME/scripts/aidp_scheduler.py" watchdog --quiet >>"$log" 2>&1 || true
  run_one || exit $?
  exit 0
fi

echo "[agent_loop] agent=$agent interval=${secs}s prompt=$prompt（日志：$log）" >&2
while true; do
  python3 "$AIDP_HOME/scripts/aidp_scheduler.py" watchdog --quiet >>"$log" 2>&1 || true
  run_one
  sleep "$secs"
done
