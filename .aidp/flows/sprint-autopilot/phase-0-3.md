# sprint-autopilot · Phase 0 详情分片 [3/11]（0.0 Step 5 远程 chrome + 0.1 拉码与脏树门）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 3/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.0 Step 5（远程 chrome .mcp.json）+ 0.1（拉码 + 脏树决策门）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-3.md`。理据见同目录 `rationale.md`。

---

**Step 5 — 远程 chrome MCP 配置（写项目根 `.mcp.json`，与 `/sprint-aiauto-test` 共享，只问一次）**：

> autopilot 在最开始就统一收集后续流程所需的工具/环境/配置（里程碑通知渠道 / **远程 chrome 连接**），缺失即问、记录到 baseline 两命令共享。远程 chrome 自动化测试（Claude Code 与 Chrome **不同机**，走 `chrome-devtools-mcp`）依赖**项目根 `.mcp.json`**；本步在拿到远程 IP 时即写/合并该文件，让后续 `/sprint-aiauto-test` 直接用、无需等到跑测时才建。**本机 chrome（同机，走 `chrome-devtools-cli`）或 `test_strategy=static-only` 不需要 `.mcp.json`，本步跳过。**

1. **判定是否需要远程 chrome**：读 PRD `autopilot_decisions.test_strategy`（`static-only` → 跳过本步）；无法判定时在配置补全阶段 `AskUserQuestion` 问「本项目 AI 自动化测试用**远程** chrome 吗？（Claude Code 与 Chrome 不同机）」——否（本机 / 不测）→ 跳过本步。
2. **读项目根 `.mcp.json` 复用**：`jq -r --arg k "chrome-$(git config user.name|tr -d ' ')" '.mcpServers[$k].args[]? | select(test("^https?://"))' .mcp.json 2>/dev/null`——已有 `chrome-{git_user}` 远程地址条目 → 复用、确保文件存在即可（清空重收用 `/sprint-aiauto-test --reset-chrome-ip`，删 `.mcp.json` 该条目）。**远程地址只存 `.mcp.json`（按 git 用户名分键、入库共享），baseline 不再存 `chrome_remote_ip`。**
3. **缺失 → 一次性 `AskUserQuestion` 收集远程 chrome `IP:端口`**（如 `192.0.2.10:9222`；提示先在该机启动 chrome 调试 + 端口转发，详见 `/sprint-aiauto-test` 0.1.5 / 测试方案「二·2.2」）；写/合并项目根 `.mcp.json` 的 `chrome-{git_user}` 条目（见下方第 4 项脚本）。**无人值守 `/loop` 中若 `.mcp.json` 仍缺该条目（补全阶段没收集到）→ 跳过本步不阻塞**，留给 `/sprint-aiauto-test` 跑测时收集。
4. **写/合并项目根 `.mcp.json`**（server 条目 `chrome-{git_user}`，与 `/sprint-aiauto-test` Phase 0.0.5 同一套**合并**逻辑——只增改 chrome key、保留团队其它 server、不整体覆盖；入库提交、不 gitignore）：

```bash
CHROME_IP="<baseline 复用 / 本步收集到的 IP:端口>"
GIT_USER=$(git config user.name 2>/dev/null | tr -d ' '); [ -z "$GIT_USER" ] && GIT_USER=user
# 优先用脚手架下发的 doctor 脚本（写/合并 chrome-{git_user} + 清 .gitignore 残留 + 连通预检 + 污染检测，
#   单一信源，与 /sprint-aiauto-test 0.1.1.4 同源；用法详见 scripts/README.md）；
# ⚠️ 脚本缺失（脚手架未下发 / 旧版）→ 走内联 python 合并兜底，**绝不因单点脚本缺失写不出 .mcp.json**
#   （并建议重跑 aidp-code-engineer upgrade 补回脚本——已达目标版本也会自愈下发，见 migrate）。
if [ -f {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py ]; then
  python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py set --ip "$CHROME_IP"; DOCTOR_RC=$?
  # 退出码：0 就绪 / 4 远端不可达（脚本已打印 Chrome 启动参数；/loop 下不阻塞、留给 aiauto-test 复检）
  #         / 5 全局插件被写脏（按脚本打印的卸载重装复位，⛔ 绝不手改 ~/.claude/plugins 下任何全局文件）
else
  echo "  ⚠️ {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py 缺失 → 走内联兜底写 .mcp.json（建议重跑 aidp-code-engineer upgrade 补回）"
  python3 - ".mcp.json" "chrome-${GIT_USER}" "http://${CHROME_IP}" <<'PY'
import json, os, sys
path, name, url = sys.argv[1], sys.argv[2], sys.argv[3]
data = {}
if os.path.exists(path):
    try: data = json.load(open(path, encoding="utf-8")) or {}
    except Exception: data = {}
data.setdefault("mcpServers", {})
data["mcpServers"][name] = {"command": "npx", "args": ["-y", "chrome-devtools-mcp@latest", "--browser-url", url]}
json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
  [ -f .gitignore ] && sed -i.bak '/^\.mcp\.json$/d; /^\.claude\/mcp\/chrome-devtools-mcp\.json$/d' .gitignore && rm -f .gitignore.bak
  echo "  ✅ 内联兜底已写项目根 .mcp.json（server: chrome-${GIT_USER} / browser-url: http://${CHROME_IP}）——绝不改全局插件配置"
fi
```

5. **绝不修改全局插件配置**：远程地址**只写项目根 `.mcp.json`**；`~/.claude/plugins/`（marketplace / 缓存副本 / `plugin.json` manifest）、`~/.claude.json`、`~/.claude/settings*.json` 下任何 chrome 配置一律禁改（见 `/sprint-aiauto-test` 0.1.1.4 禁改清单）。远程连接**只调自己的 server `mcp__chrome-$GIT_USER__*`**（`GIT_USER=$(git config user.name)`），不要调插件自带的 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`。
   - **★ git 用户隔离铁律（默认本地、绝不用他人 chrome MCP）**：本命令**不直接选驱动**（浏览器实测归 `/sprint-aiauto-test`），但下发的 `.mcp.json` server 名 + 后续测试链路一律遵守——**唯一可用的远程 server = `chrome-$GIT_USER`（精确全等当前 git 用户）**；`.mcp.json` 里他人的 `chrome-<other>` 绝对禁用（会连同事机器串测）。**默认走 `chrome-devtools-cli` 操作本机浏览器**；没有属于自己的 `chrome-$GIT_USER` 条目时也回落本机 CLI，**绝不**因存在他人条目就改走远程。单一信源见 `/sprint-aiauto-test` Phase 0.1.1「git 用户隔离铁律」。

### 0.1 拉取远端全部分支 + 当前分支最新代码 + 脏树决策门

> **`vcs_mode=none` 前置出口**：先消费命令入口经 `{{AIDP_HOME}}/scripts/vcs.py` 检测的模式；无 Git 时整段 fetch/pull/脏树门跳过并记录 `status=skipped, reason=unsupported:vcs-disabled`，直接继续 Phase 0.3 的本地 PRD 扫描。不运行下方 Bash 块，不把 Git 命令失败当 `dirty-tree` / `git-pull-conflict`，不冻结本地开发。`git` 时下方原流程不变。

> 排在 0.0 之后：进入本节时 **通知渠道就绪已打印**（0.0 完成），故脏树**不静默 `exit 1` 击穿前置交互**——非 PRD 改动走下方「脏树决策门」（交互三选一 / `/loop` 安全默认）。

★ **为什么仍要先拉码**：定时执行（`/loop` 唤起 / OS cron）时，产品可能刚 push 了新 PRD 到 origin；命令端不先拉则本地 git log 仍是旧版本，Phase 1 baseline 检测会误判"PRD 无变化"漏跑。**先 `git fetch --all` 拉全部分支**（产品/其他成员可能把新 PRD 或 Sprint 推到非当前分支，全分支 fetch 才不漏；也让后续版本扫描看得到所有分支的 close 记录），**再对当前分支 `git pull --rebase` 取最新代码**。

```bash
# 0. 前置失败熔断 helper（落地下方「特别说明」的 preflight_fail_streak——避免裸 exit 每 tick 刷屏、熔断永不触发）
BASELINE_FILE="memory/.sprint-autopilot-baseline.json"
PREFLIGHT_THRESHOLD=3
# ★ 起始短路（B3）：已达阈冻结（preflight_frozen_at 非空）→ 本 tick 一行日志静默退出，
#   不再重复 fetch/pull 尝试、不再让 streak 无界膨胀。
# ⚠️ 短路**之前必须先做一次只读复检**：本段末尾的"成功一次自动清零/解冻"在短路之后，
#   若无脑短路则那段代码**永远执行不到** —— 一次 `git pull --rebase` 冲突后即便工作区早已恢复，
#   也只能靠人工 `--reset-baseline` 才起得来，与"工作区恢复后自动解冻"的承诺不符。
#   复检只读、不改工作区（`git status` + `git fetch --dry-run`），命中即就地解冻继续跑本 tick。
if [ -f "$BASELINE_FILE" ] && [ -n "$(jq -r '.preflight_frozen_at // empty' "$BASELINE_FILE" 2>/dev/null)" ]; then
  # ⛔ 解冻判据必须与冻结原因**同域**：只有 0.1 自己那些 reason（脏树 / detached / pull 冲突 /
  #    远端不可达）才由"树干净 + 远端可达"证明已恢复。对 `prd-root-missing` 这类**非 0.1 域**的原因，
  #    该条件在树干净时恒成立 ⇒ 每 tick 解冻→再冻结，形成 4-tick 周期震荡、人也看不出到底冻没冻。
  _PF_R=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get preflight_fail_reason --default "")
  case "$_PF_R" in ""|detached-head|git-pull-conflict|git-fetch-failed|dirty-tree|remote-unreachable) _PF_SAME_SCOPE=1 ;; *) _PF_SAME_SCOPE=0 ;; esac
  # dirty-tree：无人值守下脏树本就走 --autostash 拉码，恢复证据只需远端可达（树不必干净）
  _PF_TREE_OK=0; { [ "$_PF_R" = "dirty-tree" ] || [ -z "$(git status --porcelain 2>/dev/null)" ]; } && _PF_TREE_OK=1
  if [ "$_PF_SAME_SCOPE" = "1" ] && [ "$_PF_TREE_OK" = "1" ] && git fetch --dry-run >/dev/null 2>&1; then
    python3 {{AIDP_HOME}}/scripts/baseline_edit.py del preflight_frozen_at preflight_fail_streak preflight_fail_reason
    echo "🔓 前置冻结自动解除（工作区已干净 + 远端可达）→ 继续本 tick"
  elif [ "$_PF_SAME_SCOPE" = "1" ]; then
    # 0.1 自己那几个 reason：条件未恢复 → 本 tick 确实无法拉码，让位
    echo "⏸️ 前置失败已熔断待人工（$_PF_R，复检仍未恢复）→ 跳过本 tick 拉码（工作区恢复即自动解冻，或人工 --reset-baseline）"; exit 0
  else
    # ⛔ **非 0.1 域的 reason（prd-root-missing / stale-active-sprint / preflight-gate）绝不能在这里 exit**：
    #    清除它们的那三行分别在 0.3.1 / 0.3.5 / 0.7 —— 全在本步**下游**。在这里让位 = 解冻代码
    #    结构上永不可达：根因修好了也不解冻，本步打印的「工作区恢复即自动解冻」成了假承诺，
    #    唯一出路只剩 `--reset-baseline`（毁整份 baseline）。
    #    正确做法：只跳过本步的 fetch/pull，**继续本 tick**，把解冻权交还给各自的成功路径。
    echo "⏭️ 前置冻结（$_PF_R）不属本步作用域 → 只跳过本步拉码，继续本 tick（解冻由其对应的成功路径负责）"
    _PF_SKIP_PULL=1
  fi
fi
# ⛔ 全部经 baseline_edit.py 加锁写（invariants「baseline 单一写入口不变式」）：
#    Phase 0 每 tick 都跑，与测试 loop 的 5m 写窗高频重叠；裸 `jq … > tmp && mv` 会整份覆盖
#    对方刚落的心跳 / ai_report_finalized / 各 streak（后者会让熔断永不达阈）。
BE="python3 {{AIDP_HOME}}/scripts/baseline_edit.py"
_preflight_fail() {   # $1=reason(机读类别，如 detached-head / git-pull-conflict) $2=人读摘要
  # 记账 → 判阈 → 冻结 → 发 #4 全归 autopilot_fail_handle.py --preflight（⛔ 别在这另写一份，
  # 「发 #4」曾长期只是一句 echo 文案，而本处是最上游的冻结点、三道门都盖不到，见 rationale.md）
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --preflight \
    --reason "$1" --why "$2" --threshold "$PREFLIGHT_THRESHOLD"
  exit 0   # 让位本 tick（已记账 + 已告警），⛔ 不是 exit 1 让 /loop 空撞
}

# 1. 检测当前分支
BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null || echo "detached")
[ "$BRANCH" = "detached" ] && _preflight_fail detached-head "HEAD detached，无法 pull"

# 2. 检测远端跟踪分支
UPSTREAM=$(git rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || echo "")
if [ -z "$UPSTREAM" ]; then
  echo "⚠️ 分支 $BRANCH 无远端跟踪，跳过 pull（本地分支）"
  GIT_PULL_SKIPPED=1
else
  # 3. 工作区干净性检查（PRD/baseline 改动允许；其余非 PRD 改动 → 脏树决策门，不再静默 exit）
  # ⛔ 排除表必须覆盖**每 tick 必产且无人 commit** 的产物（AI执行/测试报告、截图、审计、bugfix 记录、
  #    测试链路写的研发自测文件〔问题汇总清单 / 环境账号 / 探针档案〕、`.mcp.json`）：漏排 ⇒ 脏树恒非空 ⇒
  #    跳过拉码 ⇒ 产品推到 origin 的新 PRD 永远看不见、下一版本永不启动。
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"
  DIRTY_NON_PRD=$(git status --porcelain | grep -vE "^.. (docs/requirements/|docs/reports/|docs/bugfix/|docs/audit/|docs/testing/[^/]+/研发自测/|\.mcp\.json|memory/\.sprint-autopilot-baseline\.json)")
  if [ -n "$DIRTY_NON_PRD" ]; then
    echo "⚠️ 工作区有非 PRD 未 commit 改动（绝不静默退出）："
    echo "$DIRTY_NON_PRD"
    if [ "${LOOP_UNATTENDED:-0}" = "1" ]; then
      # 无人值守：照常拉码，改动由 `git pull --rebase --autostash` 暂存并回放（不吞改动）；
      #   拉码失败按 `dirty-tree` 前置熔断记账（下方 4.）
      DIRTY_AUTOSTASH=1
    else
      # 交互式 → 见下方「脏树决策门」AskUserQuestion 三选一
      DIRTY_TREE=1; GIT_PULL_SKIPPED=1
    fi
  fi

  # 4. 工作区可拉时才 fetch+rebase（脏树已按决策门处置；跳过 pull 避免在脏树上 rebase）
  #    ★ `_PF_SKIP_PULL=1` = 存在**非本步作用域**的 preflight 冻结：只跳过拉码、本 tick 继续往下走
  #    （解冻由 0.3.1 / 0.3.5 / 0.7 各自的成功路径负责，见上方短路块）
  if [ -n "$_PF_SKIP_PULL" ]; then
    echo "⏭️ 本 tick 跳过 fetch/pull（存在非本步作用域的 preflight 冻结）"; GIT_PULL_SKIPPED=1
  elif [ -z "$DIRTY_TREE" ]; then
    # ⛔ 不能写 `git fetch … | tail -5`：`$?` 变成 tail 的 0，失败被吞
    #   （后果见 rationale「fetch 退出码为何不能进管道」）。
    _FETCH_OUT=$(git fetch --all --prune 2>&1); _FETCH_RC=$?
    echo "$_FETCH_OUT" | tail -5
    if [ "$_FETCH_RC" != "0" ]; then
      _preflight_fail git-fetch-failed "git fetch 失败（rc=$_FETCH_RC）：$(echo "$_FETCH_OUT" | tail -1)"
      GIT_PULL_SKIPPED=1
    else
    LOCAL_HEAD=$(git rev-parse HEAD); REMOTE_HEAD=$(git rev-parse "$UPSTREAM")
    if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
      echo "✅ 本地与 $UPSTREAM 已同步（HEAD=$LOCAL_HEAD），跳过 pull"
      GIT_PULL_SKIPPED=1
    else
      echo "📥 远端有新提交，pull --rebase（避免无意义 merge commit）..."
      if git pull --rebase --autostash origin "$BRANCH"; then
        NEW_HEAD=$(git rev-parse HEAD); echo "✅ pull 成功：$LOCAL_HEAD → $NEW_HEAD"
        GIT_PULL_DONE=1; GIT_PULL_FROM=$LOCAL_HEAD; GIT_PULL_TO=$NEW_HEAD
      else
        git rebase --abort 2>/dev/null   # rebase 冲突 → 不自动解决
        if [ -n "$DIRTY_AUTOSTASH" ]; then
          _preflight_fail dirty-tree "脏树下 pull --rebase --autostash 失败（本地未提交改动与远端冲突），需人工处理：$DIRTY_NON_PRD"
        fi
        _preflight_fail git-pull-conflict "pull --rebase 失败（rebase 冲突），需人工解决"
      fi
    fi
    fi
  fi
fi

# 前置检查走完且工作区干净 → 清零前置熔断计数（落地「特别说明」的"成功一次自动清零/解冻"）
# ⛔ **必须按 reason 分辨作用域，不能无条件清**：本行位于 0.1，每 tick 必跑；而**同一个**
#    `preflight_fail_streak` 还被 0.1 之后的三个失败点复用（0.3.1 PRD root 缺失 /
#    0.4 遗留 Sprint 收口失败 / 0.7 收尾钢门）。无条件清零 ⇒ 那三类失败每 tick 都被重置回 0、
#    **永远达不到阈值 3**：既不冻结、也不停，只是每 10 分钟刷一次 #4 通知，无限刷屏且永不推进
#    （工作区干净正是 7×24 常态，所以这条 100% 成立）。
#    正确口径：只清**本段自己**产生的那些 reason（0.1 作用域）；其余 reason 说明失败发生在
#    后续步骤，本段无权判定它是否已恢复，留给各自的成功路径去清。
PF_REASON=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get preflight_fail_reason --default "")
case "$PF_REASON" in
  ""|detached-head|git-pull-conflict|git-fetch-failed|dirty-tree|remote-unreachable)
    [ -z "$DIRTY_TREE" ] && python3 {{AIDP_HOME}}/scripts/baseline_edit.py \
      del preflight_fail_streak preflight_frozen_at preflight_fail_reason || true ;;
  *)
    echo "ℹ️ 前置计数保留（reason=$PF_REASON 属 0.1 之后的失败点，由其成功路径自行清零）" ;;
esac
```

**脏树决策门（`DIRTY_TREE=1` 时）**：

- **交互式（用户在场）**：`AskUserQuestion` 三选一——① `commit` 现有改动后继续 pull ② `stash` 暂存后 pull、跑完提示恢复 ③ `abort` 本轮（已发的 #0a 通知不撤）。**绝不自动 stash 全局**（避免吞掉用户改动）。
- **无人值守（`LOOP_UNATTENDED=1`）**：照常 fetch + `git pull --rebase --autostash`（本地改动暂存后回放、不吞改动）；拉码失败 → `_preflight_fail dirty-tree`（`autopilot_fail_handle.py --preflight`）记账（连续 3 次冻结 + #4 + 本地告警台账），远端可达即自动解冻。

**6 种结果处置**：

| 结果 | 命令行为 |
|------|------|
| `BRANCH=detached` | ❌ **前置失败熔断**（`_preflight_fail detached-head`）：未达阈值发 #4 @用户「HEAD detached 无法 pull」+ 退本 tick；已达阈值静默退出不再刷 #4 |
| `UPSTREAM=空`（本地分支无远端跟踪）| 跳过 pull，继续后续 Phase；日志记 "本地分支，跳过 pull" |
| 工作区有非 PRD 改动 | ⚠️ **脏树决策门**（不静默退）：通道就绪已在 0.0 打印 → 交互式 `AskUserQuestion` commit/stash/abort；`LOOP_UNATTENDED=1` 用 `--autostash` 照常拉码，失败按 `dirty-tree` 前置熔断 |
| `LOCAL_HEAD = REMOTE_HEAD` | 跳过 pull，继续；日志记 "已同步" |
| `git pull --rebase` 成功 | 继续；记录 `GIT_PULL_FROM` / `GIT_PULL_TO` 供 Phase 2 触发原因引用 |
| `git pull --rebase` 失败（rebase 冲突）| ❌ `git rebase --abort` + **前置失败熔断（见下方特别说明）**：`preflight_fail_streak` 未达阈值 → 里程碑通知 #4 @用户介入「git pull 冲突需手动解决」+ 退出本 tick；已达阈值 → **静默退出、不再刷 #4** |

**特别说明**：
- **★ 无版本上下文的前置失败熔断（`preflight_fail_streak`——补 `dev_fail_streak` 的盲区）**：Phase 0.1 的 pull 冲突 / `detached HEAD` 等**发生在 TARGET_VERSION 由 0.3 解析之前**，没有版本上下文可写 `versions.{V}.dev_fail_streak`——若无独立熔断，`/loop` 每 tick 都 pull→冲突→#4→退出，**无限刷屏且熔断永不触发**。故引入 baseline **顶层**键 `preflight_fail_streak`（+ `preflight_frozen_at` / `preflight_fail_reason`）：每次前置失败退出前 `preflight_fail_streak++` 写盘；`< 阈值`（默认 3）→ 发 #4 告警 + 退出本 tick；`≥ 阈值` → 置 `preflight_frozen_at`、**只保留首张告警**、之后每 tick **静默退出不再发 #4**（仅一行终端日志「⏸️ 前置失败已熔断待人工，跳过」）。**解冻**：前置动作成功一次（pull 成功 / 工作区恢复干净）自动清零，或人工 `--reset-baseline`。与 `dev_fail_streak`（版本级，Phase 0.3 之后）互补，二者共同覆盖"无版本上下文"与"有版本上下文"两段失败。
- `git fetch --all --prune`：拉取 origin **全部分支**的最新 ref（不止当前分支）+ 清理本地已删除的远端跟踪分支；随后只对**当前分支** `git pull --rebase` 更新工作区代码（不逐个 checkout 其他分支，避免切分支风险）
- `--rebase` 而非 merge：避免 `/loop` 周期触发生成大量无意义 merge commit 污染历史
- `--autostash`：命令端只对 baseline 文件（自己管理的）做自动 stash，其它不动
- PRD 目录的 unstaged 改动**允许**通过（产品在工作区放新 PRD 文件未 commit 是合规场景）；其他文件走脏树决策门
- pull 后立即重新跑 Phase 0.3 的版本扫描（本地状态可能因 pull 而改变，比如远端已有 V0.2.0 的 Sprint close 记录）

**与 Phase 1 的协作**：`GIT_PULL_TO` 即新的 HEAD 会让 Phase 1.2 的 `git log -1 --format=%H -- $PRD_DIR` 检测到新 commit，触发 SHOULD_RUN=1。

