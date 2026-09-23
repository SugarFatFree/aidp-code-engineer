<!-- 二次切分 · phase-3 片4/6：覆盖 3.5 收敛判定+切有头提醒 / 3.6 自动有头眼检-->
# /sprint-aiauto-test · 执行分片 分片 [4/6]（3.5 收敛判定+切有头提醒 / 3.6 自动有头眼检）

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-3-4.md`。理据见同目录 `rationale.md`。

### 3.5 ★ 本轮收敛判定（通用，本地 + 远程）+ 切有头提醒（仅 `DRIVER=mcp-remote` 远程）

> ★ **两件事、两种作用域，别混**：① **本轮收敛信号 `CONVERGED`**（本轮全通过 + 无待修 bug）——**本地 cli 与远程 mcp 都必须计算**（下游 3.4 `unconverged_streak` 清零、3.7 AI执行报告 finalize + #3 里程碑通知 两处共用；绝不能只在远程算，否则本地默认路径信号缺失 → 假冻结 / 报告永停骨架 / 通知不发）；② **切有头提醒**——**仅 `DRIVER=mcp-remote` 远程**且有「必须有头」延后用例时才做（本地 CLI 免重启即时切，延后集 `DEFERRED_HEADED_CASES` 本就为空，无须提醒）。
>
> **切有头核心铁律（仅远程）**：远程切有头要重启 Claude Code（0.1.1.5），所以**中途绝不停下来提醒切模式**——必须等整条无头闭环**收敛**后才一次性提醒。本命令自身不改代码（注意事项 1），「自修复 → 重新部署 → 再测」由外层 dev/bugfix loop（或 `/sprint-batch` Step 6 / 用户手动 `/sprint-bugfix`）完成；本步**每轮只判定是否收敛**，未收敛就不提醒，让外层 loop 继续修。
>
> ⛔ **新 build = 全量回归（命令端编排决策）**：修复后**铸新 build 复测**（铸 build 是命令/autopilot 职责）时，须**全量重跑本版本所有用例、不只复验被修的那几条**——**"跨 build 全量重跑、不沿用上一 build 的 `[√]`、resume/`[√]` 跳过仅限同一 build 内中断恢复"的 tasks.md 状态机作用域，以 `auto-test-runner` SKILL 为单一信源（约定 21 不复述）**。配合上面「覆盖率 100%」判据共同保证不留死角（实战教训：只验被修的 P0、漏了同源 P1 旁路取数）。

**收敛判定（★ 三条同时满足才算收敛 —— 双终止判据「问题清单空 且 覆盖率 100%」的落地）**：
1. 本版本所有**无头可跑用例**最近一轮**全部通过**（本轮无「① 用例失败」）；
2. 主用例文档末尾「问题汇总清单」**无任何 `待修复` 行**（① 用例失败 + ② 运行时错误都已被修复 + 重新部署 + 重测验证）；
3. **★ 用例覆盖率 = 100%**——本 build 无任何**标「阻塞 block / 未执行」而未解除**的用例：之前轮次因环境/前置未满足标 block 或跳过的用例，必须**本轮已解除并实际跑过**、或**有明确豁免依据**（如"需真实第三方数据、本期 Mock 覆盖不到"，记入报告豁免清单）。**"还有用例没跑到 / 一直 block 着"不算收敛**——防"只复验被修用例、其余用例长期未覆盖就宣告通过"。

```bash
# ★ 跨分片取回本 tick 变量 —— flow 每个分片是**独立的 Bash 调用**，shell 变量不持久；
#   漏这一行会让下方判据读到空串、`${VAR:-默认}` 静默落默认值（恒真/恒假）。
#   真源在 baseline 的（BUILD/DRIVER/DEPLOY_MODE/NOTIFY_ENABLED/LOOP_UNATTENDED…）由脚本自动回落。
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# 每轮 /sprint-aiauto-test 报告落盘后跑；本命令不改代码，自修复由外层 loop 完成（见注意事项 1）
# ★★ CONVERGED 已在 Phase 3.3 开头【无条件】算好（本地 cli + 远程 mcp 通用，位于所有消费点之前）——本步不重算、直接复用
#   （3.4 streak 清零 / 3.7 报告 finalize + #3 通知 均消费同一 CONVERGED；见 3.3 开头 Critical 修复说明）
# 本步只按 CONVERGED + 远程守卫决定"是否切有头提醒"（HEADED_REMINDER）：仅 DRIVER=mcp-remote 远程 + 无头 + 有「必须有头」延后用例才提醒
case "${DRIVER}" in mcp*) IS_MCP=1 ;; *) IS_MCP=0 ;; esac   # 两个 MCP 变体同受"切模式须重启"约束
if [ "$IS_MCP" != "1" ] || [ "${RENDER_MODE:-headless}" != "headless" ] || [ -z "$DEFERRED_HEADED_CASES" ]; then
  HEADED_REMINDER=0   # 本地 cli / 整体有头 / 无延后用例 → 无须切有头提醒（CONVERGED 已算，下游 3.4/3.7 照常消费）
else
  HEADED_REMINDER=1   # 远程无头且有延后 → 按 CONVERGED 决定是否一次性提醒切有头（见下）
fi
```

> ★ 以下「切有头提醒」两分支**仅 `HEADED_REMINDER=1`（远程无头 + 有延后用例）时执行**；`HEADED_REMINDER=0`（本地 cli / 无延后）**整段跳过**——但 `CONVERGED` 已在上方无条件算好，3.4 `unconverged_streak` 清零 / 3.7 报告 finalize + 发 #3 通知 照常按 `CONVERGED` 执行。

- **未收敛**（`CONVERGED=0`）：报告末尾 + 里程碑通知**不提醒**切有头；只在报告里记一行
  `🪟 仍有 {N} 条「必须有头」用例待覆盖（无头闭环未收敛：本轮失败 {F} / 待修复 bug {OPEN_BUGS}，待修复 + 重测通过后再提醒切有头）`。
  下一轮 /loop 唤起继续无头修复闭环。

- **已收敛**（`CONVERGED=1`，逻辑上只可能落在「全通过且无运行时错误」绿灯场景——有失败 / 有运行时错误必然 `OPEN_BUGS>0` 判未收敛）：报告末尾 + 绿灯里程碑通知 #F **追加切有头提醒**：

  ```
  ✅ 无头闭环已收敛（全部无头用例通过 + 无 bug 待修 + 报告已落盘）
  🪟 剩余 {N} 条标记「必须有头」的用例待覆盖：
     - {case_id} {标题}（原因：验证码 / 视觉像素比对 / 下载弹窗 / 反爬真人交互 …）
     - …
  📌 切有头补跑（须重启 Claude Code，见 0.1.1.5）：
     ① 测试方案「二·渲染模式」行改为 `有头（已确认；原因：…）`（或经 0.0.6 重新确认渲染模式）
     ② 改 chrome-devtools-mcp plugin / MCP 配置：去掉 `--headless=new`（有头本地需 GUI；无 GUI 则改配远程地址 http://<你的IP>:9222 + 端口转发，见 0.1.5）
     ③ 重启 Claude Code（plugin 只在启动时读配置）：退出（Ctrl+C 两次 / /exit）后重新打开，建议 `claude --dangerously-skip-permissions -c`（-c 续上原会话 + 免权限打断）
     ④ 重启后重新跑 /sprint-aiauto-test → Phase 2.0-E 识别 RENDER_MODE=headed，把这 {N} 条纳入本轮实跑
  ```

> ⛔ 绝不在无头闭环未收敛时提醒切有头，也绝不在本命令内部尝试运行时切模式（必失败，见 0.1.1.5）。

---

### 3.6 ★ 无头跑完后「自动有头眼检」（按环境有头能力自动决策，不询问用户）

> **本步目的**：全程无头跑完后，**不询问用户**，按环境有头能力自动决策——具备有头能力（已配远程 chrome MCP `DRIVER=mcp-remote` / 本机有 GUI 桌面 `GUI_OK=1`）就**直接**用有头浏览器打开几个主要功能界面做一次肉眼眼检；既无远程 chrome MCP（IP:端口未配）又无本机 GUI、且本轮用例都不需要有头 → 正常收尾不眼检。

> **与 3.5 的区别**：3.5 是**远程**把「**必须有头**」**用例**延后到无头闭环收敛后**补跑完整用例**（有断言、计入回归）；本 3.6 是**全程无头跑完后**用**有头浏览器**做一次**简单肉眼眼检**——**只打开几个主要功能界面看渲染 / 布局是否正常，不重跑任何完整用例、不做断言**。两者**完全独立**：即使本轮**没有**「必须有头」用例（3.5 整步跳过）、即使 `DRIVER=cli` 本地，本 3.6 仍按能力自动判定。

**触发前置**（都满足才进入下方能力判定）：
1. `RENDER_MODE=headless`（本轮**全程无头**；整体有头跑则无意义 → 整步跳过）；
2. 无头测试已**完整结束**（Phase 3 报告落盘 + #F 已发；若有 3.5 远程延后，先走完 3.5）。

**Step 1 — 自动能力判定（不询问用户）**：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
# 有头能力 = 已配远程 chrome MCP（DRIVER=mcp-remote，即 .mcp.json 有 chrome-{git_user} 条目）或 本机有 GUI 桌面（GUI_OK=1）
case "${DRIVER}" in mcp*) IS_MCP=1 ;; *) IS_MCP=0 ;; esac
if [ "$IS_MCP" = "1" ] || [ "${GUI_OK:-0}" = "1" ]; then
  HEADED_CAPABLE=1   # 直接开有头眼检（Step 2）
else
  HEADED_CAPABLE=0   # DRIVER=cli 且 GUI_OK=0：本机无 GUI 又未配远程 chrome MCP
fi
```

- **`HEADED_CAPABLE=1`** → **直接执行 Step 2 有头眼检**（无任何询问）。
- **`HEADED_CAPABLE=0`**（既无远程 chrome MCP IP:端口、本机又无 GUI）：
  - 本轮用例**都不需要有头**（Phase 2.0-E 未拆出 `DEFERRED_HEADED_CASES` + 测试方案未标「必须有头」）→ **正常收尾**，报告记一行「未配远程 chrome MCP 且本机无 GUI，本轮无『必须有头』用例 → 跳过有头眼检」；
  - 本轮**有**「必须有头」用例却无任何有头能力 → 属上游能力缺口（Phase 3.5 已就此提醒切远程 / 换有 GUI 的机器），本步同样跳过眼检，报告记一行指向 Phase 3.5 提醒。

**Step 2 — 执行有头眼检（`HEADED_CAPABLE=1` 自动进入）**：

> ★ **无人值守守卫前置（先于 a 发 #G）**：`LOOP_UNATTENDED=1` 且非显式 `--headed-glance` → 下方 b 各驱动分支都会整段跳过眼检 ⇒ **本步整体跳过、不发 #G**，只在报告记一行跳过原因。#G 只在确实要执行眼检时发。

a. **发里程碑通知 #G 有头眼检（见 `sprint-autopilot` 0.1bis；通过上方守卫、确实执行眼检时发）**——公共字段 + 下列内容：
   （**首行 = 通知标题 `notify.py --title`，按 0.1bis「通知标题固定前缀」必带项目中文名称**；其余为正文）
   ```
   🪟 {项目名称} {TARGET_VERSION}_Build{N} · 自动有头眼检（非完整用例）      ← 标题
   版本：{TARGET_VERSION}
   方式：有头浏览器仅打开主要功能界面，肉眼验证渲染 / 布局（不重跑用例、不做断言）
   待打开页面：{逐条列出将访问的功能页面，去重取前 K 个}
   驱动：{cli 本机即时切有头 | mcp 远程需改配置 + 重启}
   ```

b. **切有头 + 打开页面**（按 `DRIVER` 分流）：
   - **`DRIVER=cli`（本地）+ `GUI_OK=1`**：
     > ⚠️ **无人值守保护（与下面 mcp 分支同级、不可省）**：`LOOP_UNATTENDED=1` → **整段跳过有头眼检**，只在报告记一行「无人值守下跳过有头眼检（眼检的产物是给人肉眼看的，无人在场时纯属空耗）；如需可手动 `/sprint-aiauto-test --headed-glance`」。**Why**：本地 cli 切有头**不需要重启 Claude Code**，于是没有任何东西拦得住它——`GUI_OK=1` 的机器上每个 `/loop` tick 都会「重启 chrome 去无头 → 重新登录 → 逐页 navigate → 截图 → 再切回无头」，真实吃掉大段 tick，而截图无人查看。显式 `--headed-glance` 入口视为用户在场，不受本守卫约束。
     >
     重启本机 chrome **去掉 `--headless=new`**（须重新登录则按 Phase 2 登录流程走一次）→ Claude Code **无需重启** → 依次 navigate 到下方「眼检页面集」每个页面、等待加载（首屏 ≤ NAV 秒）、`take_screenshot` 存 `docs/reports/{version}/AI测试报告/screenshots/${BUILD}/headed-glance/` → 全部打开完毕后提示用户已可在有头窗口肉眼查看；**眼检完成切回无头**（恢复 `--headless=new`，避免影响后续轮 / 下次 /loop）。
   - **`DRIVER=mcp-remote`（远程）**：切有头须改 MCP 配置 + 重启 Claude Code（0.1.1.5 铁律，运行时切不动）→ 复用 3.5 的切有头指引（chrome 启动去 `--headless=new` / MCP 配置切有头 → 重启 Claude Code `claude --dangerously-skip-permissions -c`）→ 重启后跑 **`/sprint-aiauto-test --headed-glance`**（专用入口，直接进本步打开「眼检页面集」，**不重跑完整用例**）。
     > ⚠️ **无人值守保护**：`/loop` / `--no-loop` / 无 TTY 下，远程切有头要重启 Claude Code 会打断无人值守循环 → **不自动重启**，报告记一行「远程有头眼检需重启 Claude Code，无人值守下跳过；如需可手动 `/sprint-aiauto-test --headed-glance`」。

**眼检页面集**（"打开一些功能界面即可"——只打开、不操作、不断言）：取本轮**主集用例覆盖的代表性功能页面**（按菜单 / 路由去重），默认取前 **5–8** 个；优先覆盖各一级菜单首页 + 本版本新增 / 改造页面，不足则补登录后首页 + 主要列表页。**只 navigate + 截图，不点击表单 / 不提交 / 不跑断言**（眼检 = 看渲染与布局，不是回归）。

c. 眼检完成 → 在测试报告末尾追加「有头眼检」段（列出打开的页面 + 内联截图 `[![](相对路径)](相对路径)`），标注「自动有头眼检（环境具备有头能力触发）：人工肉眼快验，非完整用例回归」。

