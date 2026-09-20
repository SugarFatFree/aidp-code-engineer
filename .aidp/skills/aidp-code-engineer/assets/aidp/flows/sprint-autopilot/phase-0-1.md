# sprint-autopilot · Phase 0 详情分片 [1/11]（Phase 0 前置硬门 + 0.0.0 无人值守信号 + 0.0 Step 0–1）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 1/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：Phase 0 前置硬门 + 0.0.0 无人值守信号 LOOP_UNATTENDED + 0.0 Step 0–1（preflight / 通知渠道检查）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-1.md`。理据见同目录 `rationale.md`。

---

## Phase 0：前置条件检查（缺一不可启动）

> ⛔ **Phase 0 前置硬门（exit-1 级铁律 — 任何入口 / 任何 `ENTRY_MODE` / 任何用户意图都不得绕过）**：无论命令以何种方式被触发——`--full-auto` / `--once` / `--skip-dev` / `/loop` 守护，**还是用户用自然语言表达"只做浏览器测试 / 远程功能验证 / 跑后续 AI 自动化测试"等 test-intent**——在执行**任何** 开发 / 部署 / 测试 / **委派（invoke `/sprint-aiauto-test`）** 动作之前，**必须先完整跑完 Phase 0.0–0.7**：
> ① **0.0 通道与配置就绪（最前 —— 任何 exit 门之前）**：`preflight check` → 里程碑通知渠道检查（**Step 2 打印已配置渠道**；未配置 = 静默降级、不弹窗；#0a 通知默认不发）→ Step5 写 `.mcp.json`（需远程 chrome 时）→ ② **0.1 拉码 + 脏树决策门**（脏树**不静默 exit**，改交互/安全默认）→ ③ 0.3 版本扫描 + **0.3.6 发 #0 启动通知（仅 `full` 模式；test-only 跳过，见 0.1bis「ENTRY_MODE × 应发通知集矩阵」）** → ④ 0.5/0.6 决策预声明收集 → ⑤ **0.7 收尾核验门**（`autopilot-preflight.py gate` 逐项 `exit 1` 打勾：.mcp.json 等必需项；通知渠道仅作信息项）。
> **未跑完 Phase 0 → 不得进入 Phase 1/2/3，也不得 invoke `/sprint-aiauto-test`。** 缺任一必需项 → **交互式**当场 `AskUserQuestion` 一次性收齐（遵守 0.6 铁律：Phase 0 收完、禁中途阻塞）；**★ `/loop` 无人值守（`LOOP_UNATTENDED`）则不弹窗**——按 Phase 0.6 白名单自动走 PRD `autopilot_decisions` 预声明 / 文档化默认，缺失项标 `{待用户填写}` 占位后继续（`autopilot-preflight.py` 已对可降级项做无人值守降级放行），绝不挂起。
> ⛔ **test-intent 专项防绕过（本硬门要解决的根因）+ 按上下文分流问不问（P0-0 纠正过宽禁令）**：收到"只做浏览器 / AI 测试 / 远程功能验证"类意图——**默认仍走全流程**；**流程裁剪（跳过开发→test-only）的唯一合法来源 = 用户显式声明**：① 显式 `--skip-dev` → 直接置 `ENTRY_MODE=test-only`；② **命中 test-intent 关键词但未带 `--skip-dev`**：**交互式（`LOOP_UNATTENDED=0`）→ 必须 `AskUserQuestion` 问用户「全流程 / 仅部署+测试」**（用户选才裁剪，纠正旧"严禁弹窗、自动判定"——那把隐式裁剪凌驾于用户之上）；**`/loop` 无人值守（`LOOP_UNATTENDED=1`）→ 保守默认 full、不弹窗不裁剪**（旧"防挂死"初衷靠此达成、不再靠"一律禁问"）。无论 full 还是 test-only，委派 `/sprint-aiauto-test` / 驱动浏览器**之前 Phase 0.0–0.7 一步都不能省**。**绝不允许**"识别到 test-intent → 静默跳过 Phase 0 配置收集与通道就绪打印"（这正是「通道全就绪却整次零推送」的根因）。**通知集按 ENTRY_MODE 精简**（详见 0.1bis「ENTRY_MODE × 应发通知集矩阵」）：`full` 发 #0 + 全部开发链路通知；`test-only` 只发测试链路通知 #D/#R/#F/#G/#3 + #4，**不发** #0 版本扫描及 #1/#1b/#1c/#1d/#2/#pre-* 开发链路通知；**#0a 通道就绪通知两模式都默认不发**（开关 `notify.channel_ready_card`），防零播报靠终端渠道日志 + 真实里程碑通知。
> 与 0.7 的关系：0.7 升级为**结构化收尾核验门**（调 `autopilot-preflight.py gate`，`exit 1` 逐项打勾），与本前置硬门构成**两道钢门**夹击——本硬门管"按正确顺序最早做"，0.7 管"带缺失绝不放行往下 / 委派"。

### 0.0.0 ★ 规范化无人值守信号 `LOOP_UNATTENDED`（所有无人值守分支的统一开关，必须最先派生）

> 本命令下文多处按 `LOOP_UNATTENDED` 分流（0.7 收尾钢门是否传 `--interactive`、失败处置退 tick、配置缺项是否弹窗等）。该变量**必须在 Phase 0 最开始由 `/loop` 上下文信号 `IS_LOOP_CONTEXT` 派生**——否则 0.7 钢门（在 `IS_LOOP_CONTEXT` 于 Phase 1.3 派生之前）读到的 `${LOOP_UNATTENDED:-0}` 恒为 0、被当交互式，`/loop` 无人值守首跑时会被 gate 误判为交互式而 `exit 1` 阻断、无人可答形成死结。与 `/sprint-aiauto-test` 0.0.0 同源同范式。

```bash
# ══ 第一步：【全部】参数标志的确定性解析 + 落盘（★ 不解析 = 全部落 `:-0`，对应 flag 等于不存在）══
# `$ARGUMENTS` = 本次调用的原始参数串（斜杠命令由 runtime 注入）；未注入时按空串处理。
# ⛔ 本 case 必须**枚举全部旗标**，漏一个即该旗标恒不生效：`--unattended`/`--once`/`--no-loop` 之外，`--skip-dev`/`--skip-deploy`/
#    `--no-planning`/`--force-replan`/`--target`/`--batch-one-tick` **全仓没有任何解析落点** ——
#    命令正文把「流程裁剪的唯一来源是用户显式声明」立为铁律，而那个"显式声明"根本没被读进来：
#    `[ "$SKIP_DEV" = 1 ]` 恒假 → `--skip-dev` 静默失效、test-only 入口不可达。
#    现统一交给确定性脚本解析 + 落盘到 baseline `autopilot.tick`（**每 tick 整段重写**，不残留上轮）。
# ★ 四个 `--reset-*` 必须先于读 baseline（它们改的正是 baseline）。
#   rc: 0=未命中 / 10=已重置且结束本 tick / 11=已重置继续（根因见 rationale 同名段）。
python3 .aidp/scripts/autopilot_reset.py --arguments="${ARGUMENTS:-}"; _RST=$?
[ "$_RST" = "10" ] && exit 0
python3 .aidp/scripts/autopilot_tick_flags.py parse --command autopilot --arguments "${ARGUMENTS:-}"
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
# ⚠️ `$ARGUMENTS` 未被宿主注入时全部标志恒 0 —— 由 Claude 读用户原文补判后重跑上面两行，⛔ 绝不留空。
# IS_LOOP_CONTEXT（探测法单一信源在此；Phase 1.3 复用本处值、不再独立探测）：
#   判据 = 当前 prompt 是否含 `/loop` 字样。纯 shell 读不到，**须由 Claude 就地改成 0/1**，不得跳过：
IS_LOOP_CONTEXT=0    # ← Claude 按本轮 prompt 是否含 `/loop` 就地改为 0 / 1
# ★ 确定性第二信源：`LOOP_EVIDENCE` 由 parse 按「近期是否反复唤起」自动算
#   （只增补、不否定；根因见 rationale「IS_LOOP_CONTEXT 为何需要第二信源」）。
[ "${LOOP_EVIDENCE:-0}" = "1" ] && [ "$IS_LOOP_CONTEXT" != "1" ] && {
  IS_LOOP_CONTEXT=1
  echo "🔁 LOOP_EVIDENCE=1（近期反复唤起）→ 补判 IS_LOOP_CONTEXT=1" >&2; }
#
# ══ 第二步：由【本轮】3 个确定性信号 OR 派生 LOOP_UNATTENDED ══
# ★ 无人值守信号 = 下列任一（OR），**三者都只看本轮、不读任何历史持久化值**：
#   ① IS_LOOP_CONTEXT：/loop 周期唤起（第一步已探测）——主判据；
#   ② HAS_NO_LOOP_FLAG：本轮参数含 `--no-loop`（OS cron 无头单发 `claude -p "... --no-loop"`，prompt 无 `/loop` 字样但同样无人可答）；
#   ③ HAS_UNATTENDED_FLAG：本轮参数含 `--unattended`（★ 运维显式 opt-in——不依赖任何探测，最可靠；配 `--once --unattended` 即"无头跑一轮"）。
# ⛔ **本轮无信号 = 交互式，绝不读 baseline 历史值把自己升级成无人值守**：`autopilot.unattended_confirmed` 一经写入就永不清除，
#    若拿它当判据，上次 7×24 留下的标志会让**后续任何一次手动无 flag 调用**被误判无人值守 —— 0.7 钢门丢 `--interactive`、
#    交互式必问项被静默吞掉（用户在场却一句不问）。故该字段**只写不读**，仅作诊断留痕。
# ★ 显式交互式最高优先：手动 `--once`（且未带 `--unattended`）恒交互式（用户在场、保留弹窗）。
if [ "$HAS_UNATTENDED_FLAG" = "1" ]; then
  LOOP_UNATTENDED=1                                   # 显式 opt-in 最先判定（含 --once --unattended 无头单发）
elif [ "$HAS_ONCE_FLAG" = "1" ]; then
  LOOP_UNATTENDED=0                                   # --once 默认交互式（用户在场）；如需无头请 --once --unattended
elif [ "$IS_LOOP_CONTEXT" = "1" ] || [ "$HAS_NO_LOOP_FLAG" = "1" ]; then
  LOOP_UNATTENDED=1
else
  LOOP_UNATTENDED=0
fi
# ★ 诊断留痕（只写不读，不参与上面的判定）：本轮判为无人值守时记一笔，供运维排查"这台机器到底跑没跑 7×24"。
#   两条 loop 共享同一字段，故**交互式轮不清它**（避免手动跑一次 autopilot 把并行测试 loop 的留痕抹掉）；
#   要显式清除用 `/sprint-autopilot --reset-unattended`（等价 `baseline_edit.py del autopilot.unattended_confirmed autopilot.unattended_confirmed_at`）。
if [ "$LOOP_UNATTENDED" = "1" ]; then
  python3 .aidp/scripts/baseline_edit.py set \
    autopilot.unattended_confirmed true autopilot.unattended_confirmed_at @now >/dev/null 2>&1 || true
fi
# ★★ 本 tick 判定结果**必须落盘**（否则下游分片读不到）——`LOOP_UNATTENDED` 是普通 shell 变量，
#    而各分片分属**不同 Bash 工具调用**、shell state 不跨调用持久：0.7 收尾钢门（phase-0-9.md）
#    读到的 `${LOOP_UNATTENDED:-0}` 会恒为 0 → 恒传 `--interactive` → 交互式必问项
#    被判缺失 → **每 tick 恒 exit 1，Phase 1/2/3 永不进入**。仅"把派生提前"治不了这个，必须落盘。
# ⛔ 与只写不读的 `autopilot.unattended_confirmed` **不是一回事**：本字段是 **tick 级**的，
#    每个 tick 在此**无条件重写**（含写 0），故不存在"上轮 7×24 的标志把本轮手动调用升级成无人值守"的风险。
python3 .aidp/scripts/baseline_edit.py set autopilot.loop_unattended_this_tick "$LOOP_UNATTENDED" >/dev/null 2>&1 || true
echo "🔧 无人值守信号：LOOP_UNATTENDED=$LOOP_UNATTENDED（loop=$IS_LOOP_CONTEXT no-loop=$HAS_NO_LOOP_FLAG unattended=$HAS_UNATTENDED_FLAG once=$HAS_ONCE_FLAG）"
#
# ══ 第三步：派生 HAS_WAKE_SOURCE（"我 yield 之后，还有谁来叫我？"）══
# ⛔⛔ **`LOOP_UNATTENDED` ≠ 有唤醒源，二者答的不是同一个问题**：前者答"有没有人能回答弹窗"，
#    本变量答"退出本 tick 之后还有没有下一 tick"。上面三路信号里**只有** ① `/loop` 上下文
#    ② `--no-loop`（OS cron 周期拉起）真的有下一 tick；③ **裸 `--unattended`（典型 `--once --unattended`
#    "无头跑一轮"）没有任何唤醒源** —— 此时若仍按 `LOOP_UNATTENDED=1` 走"跑完一个 Sprint 就
#    `UNATTENDED_YIELD`"，就是**把自己停死在半路**：`run_state.next_sprint` 停在 NNN，永远等不到人来续。
#    真实事故：下游一次 `--unattended` 跑完 Sprint-015 即退，21 个 Task（约 84h）停摆，
#    收尾还反过来提示用户"要无人值守请挂两条 loop"——**命令自称全自动、实际把活儿丢回给了人**。
# ★ 判定口径：**yield 是一种"托付给下一 tick"的动作，没有受托人就不许 yield**（见 phase-3-5.md 步骤 1）。
if [ "$IS_LOOP_CONTEXT" = "1" ] || [ "$HAS_NO_LOOP_FLAG" = "1" ]; then
  HAS_WAKE_SOURCE=1                                   # /loop 守护 或 OS cron —— 有下一 tick，可分 tick 续跑
else
  HAS_WAKE_SOURCE=0                                   # 交互式单次 / 裸 --unattended —— ⛔ 无人叫醒，禁止 yield
fi
python3 .aidp/scripts/baseline_edit.py set autopilot.wake_source_this_tick "$HAS_WAKE_SOURCE" >/dev/null 2>&1 || true
echo "🔧 唤醒源信号：HAS_WAKE_SOURCE=$HAS_WAKE_SOURCE（1=可 yield 分 tick 续跑；0=本轮内连跑到底、绝不 yield）"
# ★ 把「本轮将怎么跑」明写到 stderr：`IS_LOOP_CONTEXT` 漏改不会报错、只会**静默换挡**
#   （两种后果见 rationale「IS_LOOP_CONTEXT 为何需要第二信源」），所以必须打出来让人看见。
if [ "$HAS_UNATTENDED_FLAG" = "1" ] && [ "$HAS_WAKE_SOURCE" = "0" ]; then
  echo "⚠️ 本轮判为【无唤醒源的无人值守】（裸 --unattended / --once --unattended）：" >&2
  echo "   · 本轮内连跑到全部 Sprint 关闭为止，绝不 UNATTENDED_YIELD（上下文可能很长）" >&2
  echo "   · 任何一次失败**当场冻结**本版（无下一 tick 可叠 streak），不消耗重试配额" >&2
  echo "   若你其实是 \`/loop 10m /sprint-autopilot --unattended\` 挂着的，说明上面的 IS_LOOP_CONTEXT 漏改成 1 了。" >&2
fi
```

> ★ **0.0.0bis 上一轮遗留自检（开局第一件事，读一行 baseline）**：上一轮若在无唤醒源下把未完成的流程交还给了用户，本轮开局必须**立刻识别并续跑**，而不是当作新一轮从头判断：
> ```bash
> LAST_HB=$(python3 .aidp/scripts/baseline_edit.py get autopilot.last_handback --default "")
> case "$LAST_HB" in *VIOLATION*)
>   echo "⚠️ 上一轮为契约违背（无唤醒源却停在非终态）→ 本轮【直接从 run_state 续跑那个未完成 Phase】，不重跑已完成部分" ;;
> esac
> ```
> 判定不需要执行体理解上轮发生了什么——`handback-check --record` 已把结论写进 `autopilot.last_handback`。续跑动作本就是 IRON-3「每轮开始先读 `run_state`」的既有行为，本自检只是给它一个**显式信号**，不再依赖执行体自己想起来。

> ★ **0.0.0ter 收尾护栏 fail-open 台账自检（紧接 0.0.0bis，同为开局只读一眼）**：Stop hook `autopilot-stop-guard.py` 是"收尾门没过不许结束"的结构级兜底，但它有 4 层 fail-open。**放行不等于收口，只等于护栏判不出来**——所以每一次"本可介入却放行"都会记进台账，本轮开局读一眼：
> ```bash
> SKIPS=memory/.aidp/stop-guard-skips.jsonl
> [ -f "$SKIPS" ] && tail -3 "$SKIPS" | while IFS= read -r l; do echo "⚠️ 上轮收尾护栏未介入：$l"; done
> ```
> 命中 `no-build-no-runstate` / `gate-exec-failed` / `gate-script-missing` → **上一轮的仪式产物很可能真的缺**，本轮按 IRON-3 从 `run_state` 续跑时**一并复核**该 build 的收尾门（`autopilot-ceremony-gate.py check`），别默认它已过。命中 `escape-hatch` → 提醒用户逃生舱还开着（`memory/.autopilot-stop-guard-off` 未删，护栏全程沉默）。**无台账文件 = 从未发生可疑放行**（良性放行刻意不记，见 hook 内 `_note_skip` 注释）。

> ★ **无人值守信号下传（invoke `/sprint-aiauto-test` 必守）**：本命令 `LOOP_UNATTENDED=1` 时，**任何** `invoke /sprint-aiauto-test`（Phase 0 硬门委派 / Phase 3 子流程 R 骨架后重新委派浏览器实测）**恒附加 `--unattended`，并按唤醒源决定是否追加 `--no-loop`**：`HAS_WAKE_SOURCE=1`（有下一 tick）→ `--unattended --no-loop`；`HAS_WAKE_SOURCE=0`（如 `--once --unattended`，无下一 tick）→ 只附加 `--unattended`（⛔ 不得带 `--no-loop`：被调侧据它判「有下一 tick」而让位记账，而下一 tick 永远不来 → 无报告、无冻结、无 #4）。两者都保证被调侧 `LOOP_UNATTENDED=1`、不在 tick 内退化为交互式挂死（与 aiauto-test → autopilot 自愈交接透传对称，见 `/sprint-aiauto-test` 2.5.1 铁律）。

### 0.0 通道与配置就绪（★ 最前 —— 任何可能 exit 的门之前必跑）

> ⛔ **本节是 Phase 0 第一块，排在 0.1 拉码 / 脏树门之前**：先把「里程碑通知渠道就绪（打印已配置渠道；#0a 通知默认不发）」「远程 chrome `.mcp.json`」全部收齐，**再**做可能 `exit` 的拉码 / 脏树门——根除「脏工作区在发通知 / 采集之前就 `exit 1` → 通道全就绪却整次零推送」。确定性兜底由 `.aidp/scripts/autopilot-preflight.py` 提供（查得准、拦得住）；发通知 / 问用户等**交互动作**在本节按正确顺序做（脚本只读、不发通知、不问用户）。

**Step 0 — 就绪体检（preflight check，拿确定性快照）**：

```bash
# 只读体检：aidp-config notify 渠道 + .mcp.json chrome 条目 + git 脏树，
# 输出 JSON 供本节按缺失项分流补做（恒 exit 0，纯信息态）。脚本缺失（旧版 / 未下发）→ 跳过体检、按下列 Step 手工收齐，
# 并建议重跑 aidp-code-engineer upgrade 补回（已达目标版本也会幂等自愈下发，见 migrate）。
[ -f .aidp/scripts/autopilot-preflight.py ] \
  && python3 .aidp/scripts/autopilot-preflight.py check --json --record-probe \
  || echo "⚠️ preflight 脚本缺失，按下列 Step 手工收齐；建议重跑 aidp-code-engineer upgrade 补回"
```

> ★ **`--record-probe` 不可省**：它把通知渠道探测证据落 baseline `notify_probe`（已配置渠道类型 / webhook 环境变量是否存在 / 时间）。**这是收尾门区分「通道没配所以没发」与「通道配好了但没去发」的唯一依据**——两者在产物上完全同形（都是零通知 + `--notify 0`）。缺证据时收尾门只能判 DEGRADE「无从判断」；**证据显示通道当时可用却整组跳过 → 直接判 FAIL 漏发**。实际项目中出现过：通知渠道齐全可用，整轮零通知而流程照常"完成"。

> ★ **通知机制**：本命令的全部里程碑播报以**里程碑通知**（通知卡片）发出，发送经 `notify.py --auto`——它按 `memory/aidp-config.yaml` 的 `notify.channels` 依次尝试各渠道（`feishu` / `lark-cli` / `dingtalk` / `wecom` / `command`），成功即停（编排见 0.1bis）。命令端只定「何时发、发什么」（见 0.1bis 通知节点表）。

**Step 1 — 通知渠道检查（读 `notify` 段；首次必跑）**：

```bash
N_ENABLED=$(python3 .aidp/scripts/aidp_config.py get notify.enabled)
N_CHANNELS=$(python3 .aidp/scripts/aidp_config.py get notify.channels)
[ "$N_ENABLED" = "true" ] && [ -n "$N_CHANNELS" ] && [ "$N_CHANNELS" != "[]" ] && CH_OK=1 || CH_OK=0
```

`CH_OK` 表征**配置层面是否有可尝试的渠道**；渠道真正发不发得出去由 `notify.py --auto` 实发时逐个判定（任一成功即算播报成功）。整体 `NOTIFY_ENABLED` 由 Step 3 统一落盘。

- **`CH_OK=0`（`notify.enabled=false` 或 `notify.channels` 为空）** → 打印一行提示后继续，**⛔ 不弹窗问人**（通知是可选增强、缺失不阻塞开发主流程）：
  ```
  ℹ️ 未配置里程碑通知渠道（memory/aidp-config.yaml → notify），本轮通知节点静默跳过。
     如需播报：置 notify.enabled: true，并在 notify.channels 中添加渠道
     （如 {type: feishu, webhook_env: AIDP_FEISHU_WEBHOOK, secret_env: AIDP_FEISHU_SECRET}），
     webhook 地址/密钥只经环境变量引用，⛔ 不明文入库（约定 32）。
  ```
- **`CH_OK=1`** → 进 Step 2。

