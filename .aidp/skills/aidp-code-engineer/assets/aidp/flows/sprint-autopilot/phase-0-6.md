# sprint-autopilot · Phase 0 详情分片 [6/11]（0.2 测试归属 + 0.3 版本扫描与状态机）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 6/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.2（AI 测试归属声明）+ 0.3.1/0.3.2/0.3.3/0.3.5/0.3.6（PRD root 解析 / 版本扫描 / 状态机 / 决策矩阵 / #0 通知）
> - **不在本片**：0.3.4 选版 + 冻结跳过/解冻 → `phase-0-6b2.md`；0.3.4bis 自愈复测 + 0.4 项目状态检查 → `phase-0-6b.md`
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-6.md`。理据见同目录 `rationale.md`。

---

### 0.2 AI 自动化测试由独立命令 `/sprint-aiauto-test` 承担

本命令专注开发链路（PRD 监听 + /version + /sprint-batch + 里程碑通知播报），**前置统一收集后续所需配置**（含 Phase 0.0 Step 5 写项目根 `.mcp.json` 远程 chrome 配置）；但**不触发浏览器实测**——chrome-devtools-mcp 检测 / 智能启动 / 远端引导 / 账号收集 / credentials / 实际连接驱动浏览器由独立命令 `/sprint-aiauto-test` 承担。

> ⛔ **委派红线（autopilot 与 chrome 的职责边界）**：
> - ✅ **可做**：Phase 0.0 Step 5 写/合并**项目根 `.mcp.json`** 的远程 chrome 配置（前置配置收集，与 `/sprint-aiauto-test` Phase 0.0.5 同一套合并逻辑、远程地址单一信源 = `.mcp.json` 的 `chrome-{git_user}`）；**Phase 0.5.5 chrome-devtools-mcp 安装预检**（只读探测 npm 全局包是否已装 + 未装就地打印安装命令，**不连 chrome**）——这些都是"autopilot 最开始就备齐后续流程所需工具/环境/配置"的一部分。
> - ❌ **不做**：autopilot **不实际连 chrome / 不调用任何 `chrome-devtools` MCP tool / 不跑浏览器实测**（这些是 `/sprint-aiauto-test` 的职责）；用户在 autopilot 会话里要求"顺便跑 AI 自动化测试" → **先跑完 Phase 0（见前置硬门）再 invoke `/sprint-aiauto-test`**，不在本命令上下文手搓 chrome 连接。
> - ⛔ **test-intent 不绕过 Phase 0 + 裁剪按上下文分流（P0-0）**：用户用自然语言要求"只做浏览器测试 / 远程验证 / 跑后续 AI 测试"时**默认全流程**；裁剪只认显式声明——`--skip-dev` → `test-only`；仅命中 test-intent 关键词而未带 `--skip-dev` → **交互式必须 `AskUserQuestion` 问「全流程 / 仅测试」（用户选才裁剪）、`/loop` 无人值守保守默认 full 不弹窗**。（口径与理由见 rationale.md「test-intent 分流」）。
> - ⛔ **两命令都绝不做**：用 `claude mcp add --scope user`/全局注册，或改 `~/.claude.json`、`~/.claude/settings*.json`、历史遗留 `~/.claude/plugins/` 下**任何**用户级 / 全局 MCP 配置——远程 chrome 地址**只写项目根 `.mcp.json`**（`--scope project`，服务名 `chrome-{git_user}`；见 `/sprint-aiauto-test` 0.1.1.4 禁改清单 + 决定性铁律）。

> ⛔ **两类报告的归属 + "dev 已完成只要跑测试"铁律**：
> - **AI执行报告【骨架】= autopilot 产**（Phase 3.1.5 写 `data` 计划态 + Phase 3.4 finalize 结果态 + `testSummary` 占位）；**finalize（真实 testSummary）+ 报告本体 + #3 通知 = build 关闭方在 #F 后做**（有浏览器测试=测试链路 aiauto-test Phase 3.7；静态-only=autopilot Phase 3.4）。**测试报告 = aiauto-test 专属产物**（AI测试报告 HTML + #F 通知）。委派给 aiauto-test 的 = **浏览器实测 + R-4 收尾**（finalize AI执行报告 + 发 #3）。
> - **dev 已完成 / 只跑测试 / `--skip-dev` 时仍必须先产 AI执行报告【骨架】再委派浏览器实测**：这是**入口无关的编号硬门**，由 Phase 3.0「入口路由 + 前置硬门」强制——`ENTRY_MODE=test-only` 时必须按顺序跑完「子流程 R 骨架」（铸造/复用 build + 写 `data` 计划态 + 注册两页 → 部署如需 → finalize 结果态骨架 + 产物自检，**不在此发 #3**）**才允许** invoke `/sprint-aiauto-test`。委派出去的 = **浏览器实测 + R-4 收尾**（aiauto-test 在 #F 后 finalize testSummary + 发 #3）。**严禁**识别到"只跑测试"就直接 invoke `/sprint-aiauto-test`、跳过骨架。
> - **★ 报告访问链接必带 `#/build/{BUILD}` hash**（#3 AI执行报告 / #F 测试报告 两条通知都适用）：报告是多 build 共享的 HTML SPA，链接**不带 hash 打开就是综合首页/概览**，必须 `…/index.html#/build/{BUILD}` 才直达本次 build 结果页。**即使手动构造链接 / 手动改路径，也绝不能丢这个 hash。**

**7×24 守护推荐用法**（两条 `/loop` 并行）：

```bash
/loop 10m /sprint-autopilot --unattended     # 监听 PRD → 开发 + 里程碑通知（不跑 chrome）
/loop 5m  /sprint-aiauto-test --unattended   # 监听 baseline 看是否有新部署 → AI 自动化实测 + 报告 + 里程碑通知
```

详见 [`/sprint-aiauto-test` 命令文档](../../commands/sprint-aiauto-test.md)。

### 0.3 PRD root 解析 + 版本扫描 + 状态机识别（★）

#### 0.3.1 PRD root 解析

```bash
PRD_ROOT="${1:-docs/requirements/}"   # 用户传入 = 优先；否则默认 docs/requirements/

# 校验
if [ ! -d "$PRD_ROOT" ]; then
  # ⛔ 不裸 exit 1（/loop 每 tick 重撞、零告警）：内联记账，口径同 phase-0-3.md 的 `_preflight_fail`
  BE="python3 .aidp/scripts/baseline_edit.py"
  S=$($BE bump preflight_fail_streak); $BE set preflight_fail_reason "prd-root-missing"
  # 无唤醒源（--once / 无 /loop）时没有下一 tick 叠 streak ⇒ 阈值恒不可达、永不熔断
  HAS_WAKE_SOURCE=$($BE get autopilot.wake_source_this_tick --default 0)
  if [ "$S" -ge "${PREFLIGHT_THRESHOLD:-3}" ] || [ "$HAS_WAKE_SOURCE" = "0" ]; then
    $BE set preflight_frozen_at @now
    # ⛔ 阻塞值必须带 `@<作用域>`，且作用域必须落在 `autopilot_unfreeze.py` 的清除前缀内。
    #   写成裸 `frozen:prd-root-missing`（无 @）有两个后果，且都是永久的：
    #   ① 无 @ ⇒ ceremony-gate 的 `test_loop_alive` 判它「全局阻塞、对任何版本成立」⇒ 两条 loop
    #      好好挂着也恒判「测试链路未挂载」，phase-3-9 每 tick 叠 test_loop_missing_streak 把正常
    #      build 冻成 config-missing，phase-2 的准发布也永久走 missing 熔断；
    #   ② 该前缀不在 `BLOCKED_PREFIX`（`frozen:preflight-incomplete@`）内 ⇒ 下面成功路径的
    #      `autopilot_unfreeze.py prd-root-missing` 清得掉三个 preflight_* 键，**清不掉它**。
    #   故复用与 0.7 收口门同一个已被覆盖的值（`@preflight` 是伪作用域，匹配不到任何真实版本）。
    $BE set aiauto_blocked_reason "frozen:preflight-incomplete@preflight"
  fi
  echo "⛔ PRD root 不存在：$PRD_ROOT（第 $S 次）→ 达阈即熔断待人工"
  # ★ 发 #4：⛔「发 #4」必须是这一行命令，不是一句注释——PRD root 缺失是整条链路最上游的门，
  #   它一旦把版本挡住而通知渠道零消息，表现就是「挂着跑却什么都没发生」，无人会来看终端。
  #   ⛔ 本步在选版之前，无版本号 ⇒ **不带 `--node`**（notify 对「有 --node 缺 --version」发送前 fail-closed，rc=2 一个字节都发不出）。
  python3 .aidp/scripts/notify.py --alert --auto --header-color red \
    --title "前置受阻：PRD 目录不存在" \
    --section "PRD root 不存在：$PRD_ROOT（连续第 $S 次）。请确认 docs/requirements/ 下的产品输入已就位后重触发。"
  NRC=$?
  case "$NRC" in
    0|3) : ;;   # 0 已发 / 3 未配置渠道（合规降级，告警已落 memory/.aidp/alerts.jsonl）
    *) echo "⚠️ #4 未发出（notify.py rc=$NRC）——不阻断熔断处置" ;;
  esac
  exit 0
else
  python3 .aidp/scripts/autopilot_unfreeze.py prd-root-missing || true
fi
```

#### 0.3.2 扫描 V*.*.* 子目录（仅 SemVer 命名）

```bash
# ⛔ `PRD_ROOT` 必须**在本围栏重新派生**：0.3.1 与本步是两次独立 Bash 调用，shell 变量不跨调用存活。
#    取空时 `ls -1 ""` 无输出 ⇒ VERSIONS 空 ⇒ 下面直接 `exit 0` —— 每个 tick 都停在这里，
#    版本扫描与整个状态机结构上不可达，且打印的是"PRD 下没有版本目录"这条误导性结论。
PRD_ROOT="${PRD_ROOT:-${1:-docs/requirements/}}"
# 找所有 V*.*.* 命名的子目录（严格匹配 SemVer 前缀 V）
VERSIONS=$(ls -1 "$PRD_ROOT" 2>/dev/null | grep -E '^V[0-9]+\.[0-9]+\.[0-9]+$' | sort -V)

if [ -z "$VERSIONS" ]; then
  echo "⚠️ $PRD_ROOT 下无任何 V*.*.* 命名的版本子目录"
  echo "👉 产品请创建 ${PRD_ROOT%/}/V0.1.0/产品提供/ 并放 PRD 文件"
  exit 0
fi
```

#### 0.3.3 解析每个版本的状态（状态机）

对每个 `<V>`，按以下顺序判定状态（首个命中即生效）：

| 状态 | 判定条件 | 含义 |
|------|---------|------|
| **S0 仅 PRD** | `<PRD_ROOT>/<V>/产品提供/*.md` 存在 + `docs/requirements/<V>/研发需求/` 不存在 | 产品已提需求，未规划 |
| **S1 已规划进行中** | `docs/plans/<V>/` 下存在 `*研发执行计划*.md`（★ 通配，**不得**硬判 `01_`：多用户 / 超阈 / 多里程碑拆分会产 `NN_研发执行计划-{开发者}.md`、`01_M1研发执行计划.md` 等）+ `memory/<V>/<user>/sprints/` 下至少有一个**未关闭** Sprint | 开发中 |
| **S2 Sprint 全关闭未准发布** | `docs/plans/<V>/` 下存在 `*研发执行计划*.md`（同 S1 的通配口径；⛔ 别硬判 `01_`，见 rationale.md「S2 通配口径」）+ 所有 Sprint 在 `memory/<V>/<user>/progress.md` 都标 ✅ + baseline 该版本字典 `versions.<V>.internal_released_at` 为空 | 等待准发布归档 |
| **S3 已准发布（无 tag）** | baseline 该版本字典 `versions.<V>.internal_released_at` 有值 + 无 `git tag v{<V>去V}` | 已归档，等待正式发布 |
| **S4 已正式发布** | `git tag` 含 `v{<V>去V}` 或 `V<V>` | 完成 |

> 📌 **`<user>` 归属（多开发者/跨机 7×24 消歧）**：上表 `memory/<V>/<user>/` 中的 `<user>` **默认取本机 `git config user.name`**；但 baseline 已扁平化为项目级（不按用户分桶），Sprint 记录可能落在任一协作者目录下——故 S1/S2 判定应**跨用户扫描 `memory/<V>/*/sprints/` 与 `memory/<V>/*/progress.md`**（任一开发者存在未关闭 Sprint 即 S1；需所有用户目录的 Sprint 全 ✅ 才 S2），避免只看本机用户目录而误判。单开发者项目两者等价。

#### 0.3.4 识别「最近的一对」+ 熔断冻结跳过 / 解冻

> 📄 **本小节全文见 `phase-0-6b2.md`**（候选筛选 / `--target` 逃生阀 / 全量解冻探针 /
> 两个版本号落盘与自检）。**进入本步第一动作 = Read 该文件。**

#### 0.3.5 决策矩阵

| PRE_RELEASE_VERSION | TARGET_VERSION | 本轮行为 |
|--------------------|---------------|---------|
| null | null | **退出**：所有版本状态 ∈ {S3, S4}，无事可做；输出"📭 PRD root 无待处理版本" |
| 有 | null | 仅跑 Phase 2（上版准发布）|
| null | 有 | 仅跑 Phase 3（下版全流程）|
| 有 | 有 | **完整序列**：Phase 2 上版准发布 → Phase 3 下版全流程 |
| TARGET = PRE_RELEASE 且 `auto_fixable_pending=true` | — | **合法组合**：复测轮里该版既是 S2 准发布候选、又因待复测作 TARGET。**Phase 3 优先**，Phase 2 hold 让位到复测收敛后 |
| TARGET = PRE_RELEASE 且该版 `run_state.next_phase` 为 Phase 3 尾段游标（`3.2.1-*` / `3.3*` / `3.4*`） | — | **合法组合**：末个 Sprint 关闭即判 S2，而部署 / CICD / 探针 / 终审 / 收尾尾段仍在续跑。**Phase 3 优先**，Phase 2 按 0y 尾段让位（不记账） |
| TARGET = PRE_RELEASE（无尾段游标、`auto_fixable_pending` 非真、无 `auto_fix_in_progress_since`） | — | 数据冲突（多为状态机 bug 令同版既判 S2 又判 S0/S1）。**交互式**：发 #4 通知 @用户 + 退出。**`/loop` 无人值守**：纳入 `preflight_fail_streak` 熔断（同 Phase 0.1 pull 冲突处置），**绝不每 tick @用户刷屏**；若能安全降级则优先「跳过 PRE_RELEASE、只跑 TARGET」而非整轮退出。★ 熔断只止损、**不能自愈状态机 bug**（新部署不会让 bug 消失）——故达阈冻结的 #4 通知正文附一句「若反复命中此冲突，请人工 `--reset-baseline` 重建 baseline 状态机」，指明根治动作 |

#### 0.3.6 里程碑通知 #0（启动前确认，见 0.1bis）

⛔ **先判 `SKIP_DEV` 再发**（`eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"`，`[ "${SKIP_DEV:-0}" = "1" ]` 为真则整段跳过）：test-only 入口按通知集矩阵**明确不发 #0**。

⛔ **#0 只在「首次进入某版本全流程」时发**：`TARGET_VERSION` 的 `run_state.next_phase` 为空或 `done`（终态 = 本 tick 是该版新一轮的起点）才发；续跑中的 tick（逐 tick 单 Sprint、部署/测试尾段、准发布暂缓期）一律不发，否则每 10 分钟一张。

```bash
eval "$(python3 .aidp/scripts/autopilot_tick_flags.py --shell)"
NP0=$(python3 .aidp/scripts/baseline_edit.py --version "${TARGET_VERSION:-_}" get run_state.next_phase --default "")
case "$NP0" in ""|done) SEND_N0=1;; *) SEND_N0=0; echo "ℹ️ #0 跳过：$TARGET_VERSION 续跑中（next_phase=$NP0）";; esac
```

最近一对识别完成后经 `notify.py --auto --node "#0"` 发里程碑通知（**不阻塞**，仅通知；含公共字段；`NOTIFY_ENABLED=0` 或退出码 3 = 未配置渠道 → 静默跳过）。**首行 = 通知标题（`notify.py --title`），必须按 0.1bis「通知标题固定前缀」带项目中文名称**；其余行为正文：

```
🚀 {项目名称} {TARGET_VERSION} · 启动 · 本轮计划      ← 标题（#0 未铸 build，不带 _Build{N}）
PRD root：docs/requirements/
扫到版本：V0.1.0（S2 待准发布）/ V0.2.0（S0 新 PRD）
本轮行动：
  Phase 2 准发布 V0.1.0（归档 SQL + 文档清理，不打 tag）
  Phase 3 全流程 V0.2.0（/version + /sprint-batch）
```

> ⏭️ **接续 `phase-0-6b.md`**：① **0.3.4bis 自动修复复测闭环 step 1–2**——选完版、进 Phase 1 之前必跑（消费测试链路写的 `auto_fixable_pending`；漏跑 = 缺陷无人拾取、版本永不收敛）；② **0.4 项目状态检查**。
