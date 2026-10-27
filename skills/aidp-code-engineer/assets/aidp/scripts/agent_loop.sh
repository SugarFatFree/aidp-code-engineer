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
#   · flock 互斥：同一命令上一轮未结束则本轮跳过（无 flock 时退回 python3 fcntl；两者皆无即告警退出非 0）；
#   · tick 硬超时（timeout → gtimeout → python3 回退）；超时写 memory/.aidp/alerts.jsonl 并计连续超时，
#     连续达阈发告警通知（`aidp_scheduler.py tick-result`）；
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

# 告警旁路：追加本地告警台账（与 autopilot_fail_handle / notify 同一写口 aidp_paths.append_alert）。
# ⛔ cron 下 stderr 直接被丢弃，只打 stderr = 没告警；必须落台账。
loop_alert() {
  # $1 = kind，$2 = message
  python3 - "$1" "$2" "$cmd" <<'PY' 9>&- 2>>"$log" || printf '🚨 [AIDP-ALERT] %s %s\n' "$1" "$2" >&2
import os, sys
sys.path.insert(0, os.path.join(os.environ["AIDP_HOME"], "scripts"))
import aidp_paths
aidp_paths.append_alert(".", kind=sys.argv[1], source="agent_loop", command=sys.argv[3], message=sys.argv[2])
PY
}

# ★ 平台预检（macOS 默认既无 flock 也无 timeout）。
#   ⛔ 旧写法 `if ! flock -n 9` 在缺 flock 时拿到 127，被当成「上一轮仍在运行」→ 每轮静默跳过、exit 0，
#   整条链路零信号停摆。缺 flock 时退回 python3 fcntl（flock(2) 锁挂在打开的文件描述上，子进程加的锁
#   在本 subshell 的 fd 9 关闭前一直有效）；两者都不可用 → 告警并以非 0 退出。
lock_mode=flock
if ! command -v flock >/dev/null 2>&1; then
  if python3 -c 'import fcntl' >/dev/null 2>&1; then
    lock_mode=python
  else
    loop_alert loop-lock-unavailable "无 flock 命令且 python3 fcntl 不可用，${cmd} 无法互斥，本轮拒绝执行"
    echo "[agent_loop] $(date '+%F %T') ⛔ 无 flock 且 python3 fcntl 不可用，拒绝执行" >>"$log"
    exit 3
  fi
fi
# 硬超时执行器：GNU timeout → gtimeout（Homebrew coreutils）→ python3 回退（同 124/137 语义）
timeout_bin=""
if command -v timeout >/dev/null 2>&1; then timeout_bin=timeout
elif command -v gtimeout >/dev/null 2>&1; then timeout_bin=gtimeout
fi

# 非阻塞取锁：0 = 取得；1 = 被占（上一轮仍在运行）；其它 = 加锁机制本身出错
try_lock() {
  if [ "$lock_mode" = flock ]; then
    flock -n 9
    return $?
  fi
  python3 -c '
import errno, fcntl, sys
try:
    fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError as e:
    sys.exit(1 if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES) else 2)
'
}

# python3 版 timeout：新会话跑子进程，超时整组 TERM，60s 后仍在则 KILL；返回码对齐 GNU timeout
PY_TIMEOUT='
import os, signal, subprocess, sys
lim = int(sys.argv[1])
p = subprocess.Popen(["bash", "-c", sys.argv[2]], start_new_session=True)
def _kill(sig):
    try:
        os.killpg(p.pid, sig)
    except OSError:
        pass
try:
    rc = p.wait(timeout=lim)
    sys.exit(128 - rc if rc < 0 else rc)
except subprocess.TimeoutExpired:
    _kill(signal.SIGTERM)
    try:
        p.wait(timeout=60)
        sys.exit(124)
    except subprocess.TimeoutExpired:
        _kill(signal.SIGKILL)
        p.wait()
        sys.exit(137)
'

run_one() {
  (
    lrc=0
    try_lock || lrc=$?
    if [ "$lrc" = 1 ]; then
      echo "[agent_loop] $(date '+%F %T') ${cmd} 上一轮仍在运行，跳过" >>"$log"
      exit 0
    elif [ "$lrc" != 0 ]; then
      # ⛔ 加锁机制本身出错 ≠ 锁被占：当成「跳过」就是静默停摆
      loop_alert loop-lock-error "${cmd} 加锁失败（mode=${lock_mode} rc=${lrc}），本轮拒绝执行"
      echo "[agent_loop] $(date '+%F %T') ⛔ 加锁失败（mode=${lock_mode} rc=${lrc}）" >>"$log"
      exit 3
    fi
    # 直接 tick 的持久占位同样在此锁内读写；短命 Python 只做原子准入，不冒充跨工具持锁。
    reserved=0
    python3 - "$lock" <<'PY' 9>&- >>"$log" 2>&1 || reserved=$?
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as fh:
        raw = fh.read().strip()
    rec = json.loads(raw) if raw else {}
    if not isinstance(rec, dict):
        raise ValueError("invalid lock record")
except (OSError, ValueError):
    sys.exit(3)
sys.exit(4 if rec.get("owner") == "session" else 0)
PY
    if [ "$reserved" = 4 ]; then
      echo "[agent_loop] $(date '+%F %T') ${cmd} 直接 tick 尚未 finish，跳过" >>"$log"
      exit 0
    elif [ "$reserved" != 0 ]; then
      loop_alert loop-lock-error "${cmd} 锁记录不可读，本轮拒绝执行"
      exit 3
    fi
    export AIDP_TICK_TOKEN
    AIDP_TICK_TOKEN=$(python3 -c 'import uuid; print(uuid.uuid4().hex)' 9>&-)
    # ★ 取得锁之后才写本轮起点（锁文件以 `>>` 打开、不截断）：aidp_scheduler watchdog 据此算持锁时长。
    #   ⛔ 旧写法 `9>"$lock"` 在 flock 之前就截断文件 —— 每次「跳过」都刷新 mtime，
    #   用 mtime 估 tick 起点的挂死判定因此永不触发。
    printf '{"owner":"agent_loop","pid":%s,"token":"%s","started_at":%s}\n' "${BASHPID:-$$}" "$AIDP_TICK_TOKEN" "$(date +%s)" >"$lock" || exit 3
    quoted=$(printf '%q' "$prompt")
    echo "[agent_loop] $(date '+%F %T') 开始 agent=$agent prompt=$prompt" >>"$log"
    rc=0
    cmdline="${exec_tpl//\{prompt\}/$quoted}"
    # ★ tick 必须有硬超时。⛔ 裸执行没有上限时的失效形态是**最安静的一种**：
    #   Agent 进程挂死（网络悬停 / 模型侧无响应 / 等一个永不回来的工具结果）→ 本函数永不返回
    #   → 互斥锁被永久持有 → 之后每次调度都走上面的「上一轮仍在运行，跳过」
    #   → watchdog 看见锁被持有就判 `running` → **永不 stale、永不告警、台账一行不写**。
    #   整条 7×24 链路静默停摆，且没有任何恢复路径。
    #   `AIDP_TICK_MAX_SECONDS=0` 可显式关掉（不推荐）。
    # 环境变量优先，其次 memory/aidp-config.yaml 的 scheduler.tick_max_seconds，最后 7200。
    # ★ 执行行一律 `9>&-`：tick 里 nohup 拉起的常驻进程（dev server / chrome）若继承 fd 9，
    #   会在 tick 结束后永久持锁，后续每轮都被判「上一轮仍在运行」。
    tick_max="${AIDP_TICK_MAX_SECONDS:-}"
    if [ -z "$tick_max" ]; then
      tick_max=$(python3 "$AIDP_HOME/scripts/aidp_config.py" get scheduler.tick_max_seconds 2>/dev/null || true)
    fi
    case "$tick_max" in ""|*[!0-9]*) tick_max=7200 ;; esac
    if [ "$tick_max" -gt 0 ] 2>/dev/null; then
      if [ -n "$timeout_bin" ]; then
        "$timeout_bin" --signal=TERM --kill-after=60 "$tick_max" bash -c "$cmdline" 9>&- >>"$log" 2>&1 || rc=$?
      else
        python3 -c "$PY_TIMEOUT" "$tick_max" "$cmdline" 9>&- >>"$log" 2>&1 || rc=$?
      fi
      if [ "$rc" = 124 ] || [ "$rc" = 137 ]; then
        echo "[agent_loop] $(date '+%F %T') ⏱️ 本轮超过 ${tick_max}s 上限，已终止（rc=$rc）" >>"$log"
        printf '🚨 [AIDP-ALERT] %s tick 超过 %ss 上限被终止（rc=%s），见 %s\n' \
          "$cmd" "$tick_max" "$rc" "$log" >&2
      fi
    else
      printf '⚠️ [agent_loop] AIDP_TICK_MAX_SECONDS=0，本轮 tick 无硬超时保护（挂死将静默停摆）\n' >&2
      bash -c "$cmdline" 9>&- >>"$log" 2>&1 || rc=$?
    fi
    echo "[agent_loop] $(date '+%F %T') 结束 rc=$rc" >>"$log"
    # 超时记账：落告警台账 + 连续超时计数，连续达阈发告警通知；非超时轮清零。旁路，不改本轮 rc。
    python3 "$AIDP_HOME/scripts/aidp_scheduler.py" tick-result --root "$root" --command "$cmd" \
      --rc "$rc" --tick-max "$tick_max" --log "$log" --quiet 9>&- >>"$log" 2>&1 || true
    exit "$rc"
  ) 9>>"$lock"
}

if [ "$once" = 1 ]; then
  python3 "$AIDP_HOME/scripts/aidp_scheduler.py" watchdog --quiet >>"$log" 2>&1 || true
  run_one || exit $?
  exit 0
fi

echo "[agent_loop] agent=$agent interval=${secs}s prompt=$prompt（日志：$log）" >&2
while true; do
  python3 "$AIDP_HOME/scripts/aidp_scheduler.py" watchdog --quiet >>"$log" 2>&1 || true
  run_one || true   # 单轮失败已持久记账；前台守护仍须等到下一轮，不能被 set -e 退出。
  sleep "$secs"
done
