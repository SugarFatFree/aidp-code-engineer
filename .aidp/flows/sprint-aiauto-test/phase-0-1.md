<!-- 二次切分 · phase-0 片1/9：覆盖 0.0.0 无人值守信号 / 0.0 拉代码 / 0.0.5 读测试方案-->
# sprint-aiauto-test · Phase 0 详情（前置条件检查 0.0.0–0.4）

> 本文件是 `/sprint-aiauto-test` 命令 **Phase 0** 详情的**第 1/9 片**（⛔ 后续子步在 `-2`…`-8` 分片〔含 `-6b`〕，按进度依次 Read，勿读完本片即认为已覆盖全段），由命令主体（`{{AIDP_HOME}}/commands/sprint-aiauto-test.md`）在**进入 Phase 0 时用 Read 工具按需加载**。
>
> ⚠️ **权威性**：进入 Phase 0 后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/`。理据/根因见同目录 `rationale.md`。

---

## Phase 0：前置条件检查

### 0.0.0 ★ 规范化无人值守信号 `LOOP_UNATTENDED`（所有无人值守分支的统一开关）

> 本命令下文多处按 `LOOP_UNATTENDED` 分流（失败处置、账号降级、探测超时等）。该变量**必须在 Phase 0 最开始由 `/loop` 上下文信号派生**，否则恒 0、被当交互式，`/loop` 守护下所有无人值守分支形同虚设。
>
> 📎 **编号说明**：本节刻意编号 `0.0.0`（小于紧随的 `0.0`），表示它是**排在一切之前、最先派生的全局信号**，非"0.0 的子步骤"；与 `/sprint-autopilot` 0.0.0 同源同范式（勿据"0.0.0<0.0"误判为顺序倒置）。

```bash
# ══ 第一步：【全部】参数标志的确定性解析 + 落盘（与 sprint-autopilot 0.0.0 同款、同一脚本）══
# 全部 flag 统一交给确定性脚本解析 + 落盘到 baseline tick 命名空间（每 tick 整段重写）。
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py parse --command aiauto-test --arguments "${ARGUMENTS:-}"
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# ⚠️ `$ARGUMENTS` 取不到（宿主未注入）→ 全部标志恒 0；此时由 Claude 读本轮用户输入原文补判，
#    把 `--arguments` 换成用户原文重跑上面一行，绝不留空。
# IS_LOOP_CONTEXT（探测法单一信源在 sprint-autopilot 0.0.0，此处同款）：prompt 启动上下文含 `/loop` 字样 → 1，否则 0。
#   纯 shell 读不到，**由 Claude 判定后就地写死下面这行再执行**：
IS_LOOP_CONTEXT=0    # ← Claude 按本轮 prompt 是否含 `/loop` 就地改为 0 / 1
#
# ══ 第二步：由【本轮】3 个确定性信号 OR 派生 LOOP_UNATTENDED ══
#   ① IS_LOOP_CONTEXT：/loop 周期唤起——主判据；
#   ② HAS_NO_LOOP_FLAG：参数含 `--no-loop`（OS cron 无头单发，prompt 无 `/loop` 字样但同样无人可答）；
#   ③ HAS_UNATTENDED_FLAG：参数含 `--unattended`（★ 显式 opt-in，不依赖任何探测；配 `--once --unattended` 即"无头跑一轮测试"）。
# ⛔ **本轮无信号 = 交互式，不读 baseline 历史 `autopilot.unattended_confirmed` 把自己升级成无人值守**：该字段永不自动清除，
#    拿它当判据会让后续任何一次手动无 flag 调用被误判无人值守、吞掉该弹的窗（账号收集等）。只写不读。
# ★ 显式交互式最高优先：手动 `--once`（未带 `--unattended`）恒交互式。
if [ "$HAS_UNATTENDED_FLAG" = "1" ]; then
  LOOP_UNATTENDED=1
elif [ "$HAS_ONCE_FLAG" = "1" ]; then
  LOOP_UNATTENDED=0
elif [ "$IS_LOOP_CONTEXT" = "1" ] || [ "$HAS_NO_LOOP_FLAG" = "1" ]; then
  LOOP_UNATTENDED=1
else
  LOOP_UNATTENDED=0
fi
# ★★ 第三步：`HAS_WAKE_SOURCE`（口径同 autopilot Phase 0.0.0 第三步）——**本条决定 yield 合不合法**
#   （理据见 rationale.md『Phase 0 信号派生与落盘』）。
HAS_WAKE_SOURCE=0
{ [ "$IS_LOOP_CONTEXT" = "1" ] || [ "$HAS_NO_LOOP_FLAG" = "1" ]; } && HAS_WAKE_SOURCE=1
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test \
  HAS_WAKE_SOURCE "$HAS_WAKE_SOURCE" >/dev/null 2>&1 || true
# ⛔ 消费口径（所有 UNATTENDED_YIELD 点统一）：
#   `HAS_WAKE_SOURCE=1` → 可 yield（下一 tick 会接着跑）；
#   `HAS_WAKE_SOURCE=0` → **不许 yield**：本轮内重试 / 降级，并如实回传 `tested:false + reason`，
#                          ⛔ 绝不静默 exit 让上游以为测过了。

# ★ 诊断留痕（只写不读，不参与判定；与 autopilot 共享同一字段，故交互式轮不清它）：
if [ "$LOOP_UNATTENDED" = "1" ]; then
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py set \
    autopilot.unattended_confirmed true autopilot.unattended_confirmed_at @now >/dev/null 2>&1 || true
fi
# ★ 必须落盘：本命令可独立挂 `/loop 5m … --unattended`（不经 autopilot），
#   只靠 autopilot 写则独立跑时读回恒空 → 账号收集弹窗在无人值守下挂死。
# ⛔ 键名须带 `aiauto.` 前缀（rationale.md）
python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto.loop_unattended_this_tick "$LOOP_UNATTENDED" >/dev/null 2>&1 || true
echo "🔧 无人值守信号：LOOP_UNATTENDED=$LOOP_UNATTENDED（loop=$IS_LOOP_CONTEXT no-loop=$HAS_NO_LOOP_FLAG unattended=$HAS_UNATTENDED_FLAG once=$HAS_ONCE_FLAG）"
# ★ 测试链路全局心跳：必须在**任何 early-exit 之前**写（0.0 拉码冲突 / 0.1.1 chrome 缺失 /
#   0.1.5 远端引导 都会在 0.2 之前退出）。⛔ 心跳≠能干活，阻塞原因由 0.2 按本 tick 结论维护。
python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto_test_heartbeat_at @now >/dev/null 2>&1 || true
# 无人值守统一动作宏（下文引用）：发一次 #4 通知 → 不轮询回复 → 退出本 tick（交下次 /loop 唤起按 baseline 状态决定）
# 记为 UNATTENDED_YIELD：`发 #4 + exit`（绝不 AskUserQuestion / 绝不 60 分钟轮询）
```

### 0.0 拉取远端最新代码（同 /sprint-autopilot Phase 0.0）

`git fetch + git pull --rebase --autostash`，保证 baseline 文件读到 sprint-autopilot 最新写入的状态；rebase 冲突 → **一律 `git rebase --abort` + 记一行日志**：
- **`LOOP_UNATTENDED=1`（测试链路专属顶层熔断，退出本 tick）**：冲突发生在版本解析之前、无版本上下文，走 `--preflight --command aiauto-test`（键 `aiauto_preflight_fail_streak / aiauto_preflight_frozen_at / aiauto_preflight_fail_reason`，不与开发链路的 `preflight_*` 共用）：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
  if git fetch --quiet && git pull --rebase --autostash --quiet; then
    python3 {{AIDP_HOME}}/scripts/baseline_edit.py del aiauto_preflight_fail_streak aiauto_preflight_frozen_at aiauto_preflight_fail_reason >/dev/null 2>&1 || true
  else
    git rebase --abort 2>/dev/null || true
    if [ "${LOOP_UNATTENDED:-0}" = "1" ]; then
      [ -n "$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get aiauto_preflight_frozen_at --default '')" ] && { echo "⏸️ 测试链路拉码已熔断待人工，静默退出"; exit 0; }
      python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --preflight --command aiauto-test \
        --reason preflight-incomplete --streak-key aiauto_preflight_fail_streak --threshold 3 \
        --why "测试链路 git pull --rebase 冲突（git-pull-conflict），已 abort；人工解决冲突后下一 tick 拉取成功即自动清零"
      exit 0
    fi
    echo "⚠️ 拉取冲突已 abort，交互式按本地 checkout 继续本轮测试"
  fi
  ```
- **交互式则 abort 后直接用当前本地 checkout 继续本轮测试**——测试只读代码、不写代码，拉取冲突不构成阻塞，绝不 @用户卡住等待（如需同步最新代码请到 `/sprint-autopilot` 开发链路侧处置冲突）。

### 0.0.5 读取测试方案文档（主配置入口）

> ★ **同步必读「环境探针档案」`docs/testing/{version}/研发自测/02_环境探针档案.md`**（存在才读）：
> 它是上一轮实测沉淀的**环境行为事实**（驱动通道限制 / 鉴权头形态 / **未登录的真实响应形态** /
> 三类取证各自可用性 / 关键元素定位 / 已知需重试项），由 Phase 3.2.8 追加维护。
> **读到就必须注入 Phase 2 执行子 Agent 的 prompt**（与 run-context 一并给），
> ⛔ 不能只在主流程读一遍——真正从零摸索环境的是子 Agent，不给它等于没沉淀。
>
> **文件不存在 = 首轮，正常继续**，不报错、不阻塞。
> 档案说的是"上一轮看到的事实"、不是权威契约：与本轮实际观测冲突时**以本轮观测为准**，
> 并在 3.2.8 把该条改写为"已失效 + 新结论"。

> ★ **连接模式声明解析（`DECLARED_REMOTE`）—— 本步必须置位并 export**
>
> Phase 0.0.7 的连接模式护栏用「`HAS_OWN_REMOTE` 且 `DECLARED_REMOTE`」两条件判远程，
> 其中**声明侧就取自本步解析的测试方案**（本步不置位则「测试方案优先」永不可达）。
>
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
> # ⛔ 必须在本围栏重新定位 TESTPLAN（它赋在下面那个围栏 = 另一次 Bash 调用）：
> #    取空 ⇒ DECLARED_REMOTE 恒 0 ⇒「测试方案声明远程」这条优先级永不可达。口径同下方，改一处同步另一处。
> CFG_MARK='Chrome Remote Debugging 地址|测试环境与账号|^#+ .*测试账号'
> TD="docs/testing/${TARGET_VERSION}"
> TESTPLAN=$(grep -rlE "$CFG_MARK" "$TD/正式用例" "$TD/测试验收" "$TD/测试执行" 2>/dev/null | sort | head -1)
> [ -z "$TESTPLAN" ] && TESTPLAN=$(grep -rlE "$CFG_MARK" "$TD/研发自测" 2>/dev/null | sort | head -1)
> DECLARED_REMOTE=0   # 取不到保持 0（本地，fail-safe）
> if [ -n "${TESTPLAN:-}" ] && [ -f "$TESTPLAN" ]; then
>   grep -A 20 -E '^##[^#]*(连接模式|chrome-devtools-mcp)' "$TESTPLAN" 2>/dev/null \
>     | grep -qE '连接模式[^|]*\|[^|]*远程|模式[[:space:]]*[:：][[:space:]]*远程' && DECLARED_REMOTE=1
> fi
> case "${ARGUMENTS:-}${USER_INTENT:-}" in *远程*|*remote*) DECLARED_REMOTE=1 ;; esac
> # ★ 必须落 tick 命名空间：消费点 0.0.7 在**另一个分片**，`export` 跨不过 Bash 调用
> #   （只 export 时回读恒空 → 落 0 → MODE=remote 分支结构上不可达，声明形同无效）
> python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test \
>   DECLARED_REMOTE "$DECLARED_REMOTE" >/dev/null 2>&1 || true
> ```

> ★ **「研发自测/ 配置优先」总则（单一信源，下文各 Phase 引用本节）**：chrome 地址 / 部署 URL / 账号统一维护在 `docs/testing/{version}/研发自测/`，读到即跳过对应交互收集。口径见 `rationale.md` 同名节。

<!-- dup-check: ignore 分片自包含 -->
```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# ★★ 版本号轻量预解析（与 0.2 同一信源；`--target` 显式覆盖，不能用 `:=`，理据见 rationale.md『Phase 0 信号派生与落盘』）
[ -n "${TARGET_FLAG_VALUE:-}" ] && TARGET_VERSION="$TARGET_FLAG_VALUE"
: "${TARGET_VERSION:=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version)}"
# ★ 空版本号守卫：尚无可测版本（首个版本部署前）→ 本步无事可做，退出本 tick；⛔ 不拼 docs/testing//… 也不补全、不 commit
if [ -z "$TARGET_VERSION" ]; then
  python3 {{AIDP_HOME}}/scripts/baseline_edit.py set aiauto_blocked_reason "no-testable-version" >/dev/null 2>&1 || true
  echo "ℹ️ 尚无可测版本（current-version 为空）→ 跳过测试方案预读，退出本 tick"; exit 0
fi

# ★ 测试环境与账号配置可能 ① 单独成文（如 研发自测/01_测试环境与账号.md）② 直接内嵌在「测试人员的测试方案」或「研发自测方案」的章节里（不单独开文件）
#   → 按内容标记找承载配置的 .md（独立或内嵌都能命中），不假设有独立文件、不写死文件名；测试人员目录优先、研发自测兜底
TESTPLAN_DIR="docs/testing/${TARGET_VERSION}/研发自测"   # 缺配置时由 /sprint-selftest Step 3 在此目录补全
CFG_MARK='Chrome Remote Debugging 地址|测试环境与账号|^#+ .*测试账号'
TESTPLAN=$(grep -rlE "$CFG_MARK" "docs/testing/${TARGET_VERSION}/正式用例" "docs/testing/${TARGET_VERSION}/测试验收" "docs/testing/${TARGET_VERSION}/测试执行" 2>/dev/null | sort | head -1)
[ -z "$TESTPLAN" ] && TESTPLAN=$(grep -rlE "$CFG_MARK" "$TESTPLAN_DIR" 2>/dev/null | sort | head -1)
TESTPLAN_CHROME_ADDR=""   # 格式 IP:PORT
TESTPLAN_DEPLOY_URL=""
TESTPLAN_CREDS_READY=0    # 1 = 配置中账号已填写
TESTPLAN_RENDER_MODE="headless"   # 渲染模式：headless（默认，无需 GUI）| headed
TESTPLAN_REQUIRES_LOGIN=1         # 是否需要登录：1 需要（fail-closed 默认）| 0 无需

if [ -n "$TESTPLAN" ] && [ -f "$TESTPLAN" ]; then
  echo "📋 发现配置文件：$TESTPLAN，读取配置..."

  # 读 Chrome 地址（表格格式：| Chrome Remote Debugging 地址（IP:PORT） | `IP:PORT` |）
  ADDR_RAW=$(grep -A1 'Chrome Remote Debugging 地址' "$TESTPLAN" \
    | tail -1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:[0-9]+' | head -1)
  [ -n "$ADDR_RAW" ] && TESTPLAN_CHROME_ADDR="$ADDR_RAW" \
    && echo "  ✅ Chrome 地址：$ADDR_RAW（→ Phase 0.1 跳过地址收集）"

  # ★ 最早时机写入项目根 .mcp.json（IP 已知即建/合并，不等场景判定 / 不等 MCP 可达性）：
  #   测试方案给出 chrome IP = 远程 DRIVER=mcp-remote 信号 → 此刻立即无条件建/合并文件，根除"迟迟不建 / 根本不建"。
  #   写/合并 + 连通预检 + 污染检测 + 生效指引统一由 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py 强制校验（单一信源，见 0.1.1.4）。
  if [ -n "$TESTPLAN_CHROME_ADDR" ]; then
    GIT_USER=$(git config user.name 2>/dev/null | tr -d ' '); [ -z "$GIT_USER" ] && GIT_USER=user
    if [ -f {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py ]; then
      python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py set --ip "$TESTPLAN_CHROME_ADDR"; DOCTOR_RC=$?
      # set 内部已：写/合并 chrome-{git_user}（保留其它 server）+ 清 .gitignore 残留 + 跑体检。
      # 退出码：0 就绪 / 3 缺配置 / 4 远端不可达（已打印 Chrome 启动参数）/ 5 用户级/全局 MCP 配置被写脏（已打印复位指引）。
      # ⛔ 无论 DOCTOR_RC 为何，绝不改任何用户级/全局 MCP 配置（~/.claude.json / ~/.claude/settings*.json / 历史 ~/.claude/plugins，见 0.1.1.4 禁改清单）；
      #   rc=4 此刻不阻塞建文件（重启后由 0.1.5 复检）；rc=5 必须先按脚本指引卸载重装插件再继续。
    else
      # ⚠️ 脚本缺失（脚手架未下发 / 旧版）→ 内联兜底写 .mcp.json，绝不因单点脚本缺失写不出（建议重跑 aidp-code-engineer upgrade 补回）
      echo "  ⚠️ {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py 缺失 → 走内联兜底写 .mcp.json"
      python3 - ".mcp.json" "chrome-${GIT_USER}" "http://${TESTPLAN_CHROME_ADDR}" <<'PY'
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
      echo "  ✅ 内联兜底已写项目根 .mcp.json（server: chrome-${GIT_USER}）——绝不改用户级/全局 MCP 配置"
    fi
  fi

  # 读测试环境 URL
  URL_RAW=$(grep -A3 '开发/测试环境' "$TESTPLAN" | grep '|' \
    | awk -F'|' 'NR==1{print $3}' | tr -d '`' | xargs)
  # ⛔ 必须落盘：Phase 0.7 在另一个 Bash 调用里把它当第 1 优先级读取
  [[ -n "$URL_RAW" && "$URL_RAW" != *"请填写"* ]] && TESTPLAN_DEPLOY_URL="$URL_RAW" \
    && python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" \
         set testplan_deploy_url "$URL_RAW" \
    && echo "  ✅ 测试环境 URL：$URL_RAW（已落盘 → Phase 0.7 优先用此值）"

  # 读账号表（判定是否有任意角色已填写）
  UNFILLED=$(grep -cE '请填写' "$TESTPLAN")
  ACCOUNT_ROWS=$(grep -E '^\| .*(admin|用户|user)' "$TESTPLAN" | grep -vc '请填写')
  [ "$ACCOUNT_ROWS" -gt 0 ] && TESTPLAN_CREDS_READY=1 \
    && echo "  ✅ 测试账号已填写 ${ACCOUNT_ROWS} 个角色（→ Phase 0.4 从本文件读取）"

  [ "$UNFILLED" -gt 0 ] && \
    echo "  ⚠️ 配置中有 ${UNFILLED} 处「请填写」未配置，对应环节将回退到交互式收集"

  # ★ 读「是否需要登录」（真源 = 测试方案「二·连接模式/登录」行；本步是 REQUIRES_LOGIN 唯一生产者）。
  #   只有明确写了"无需登录/免登录/不需要登录"才置 0，其余一律 1（fail-closed）。
  LOGIN_ROW=$(grep -iE '连接模式|是否需要登录|登录方式' "$TESTPLAN" | head -1)
  if echo "$LOGIN_ROW" | grep -qE '无需登录|免登录|不需要登录|无登录'; then
    TESTPLAN_REQUIRES_LOGIN=0
    echo "  ✅ 测试方案声明：无需登录（→ Phase 0.7 账号环节直接收口）"
  else
    TESTPLAN_REQUIRES_LOGIN=1
  fi

  # 读渲染模式（表格「二·渲染模式」行）：默认无头；仅当行内明确确认「有头」才 headed
  RM_ROW=$(grep -E '渲染模式' "$TESTPLAN" | head -1)
  if echo "$RM_ROW" | grep -qE '有头.*(已确认|采用|选用)'; then
    TESTPLAN_RENDER_MODE="headed"
    echo "  ✅ 渲染模式：有头（→ Phase 0.1 启动不加 --headless；有头本地需 GUI，无 GUI 则走远程）"
  else
    TESTPLAN_RENDER_MODE="headless"   # 含「默认/待确认」行 → 一律无头
    echo "  ✅ 渲染模式：无头 --headless=new（→ Phase 0.1 本机自启无需 GUI）"
  fi
else
  echo "⚠️ 在 正式用例/ 与 研发自测/ 下均未找到含「测试环境与账号」内容的文件（独立成文或内嵌方案皆未命中）"
  echo "   建议先跑 /sprint-selftest 生成/补全测试环境与账号配置（含模板），再填写后运行本命令"
  echo "   当前本轮将回退到 Phase 0.1/0.3/0.4 交互式收集"
fi
# ★ 落盘供后续分片读回（Phase 0.4 取渲染模式 / Phase 0.7 取账号就绪度）——
#   这两个值的真源是"本轮解析测试方案"，baseline 里没有，不落盘则后续分片恒取空：
#   TESTPLAN_CREDS_READY 取空会让"方案已填好账号"也掉进交互式收账号分支、无人值守挂死。
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test TESTPLAN_RENDER_MODE "$TESTPLAN_RENDER_MODE" >/dev/null 2>&1 || true
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test TESTPLAN_CREDS_READY "$TESTPLAN_CREDS_READY" >/dev/null 2>&1 || true
# ★ REQUIRES_LOGIN 的唯一落盘点（Phase 0.7 读它决定要不要收账号）
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test REQUIRES_LOGIN "$TESTPLAN_REQUIRES_LOGIN" >/dev/null 2>&1 || true
```

