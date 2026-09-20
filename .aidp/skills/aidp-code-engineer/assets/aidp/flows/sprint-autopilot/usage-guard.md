# /sprint-autopilot · 7×24 守护用法 + 输出示例（usage-guard）

> 本文件承载 `/sprint-autopilot` 的**7×24 守护挂载用法（操作系统调度 / 会话内 /loop / 单次模式 / 用法对比）+ 输出示例**。
> 命令正文「命令语法」段保留最关键的挂载写法；需要调度细节 / 用法对比 / 输出示例时 `Read` 本文件。
> ⚠️ 维护：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/usage-guard.md`。

---

## 7×24 守护用法

### #1 ★ 标准用法：操作系统调度双进程（推荐）

```bash
# ★ 一次装齐两条链路：开发链路（默认 10m）+ 测试链路（默认 5m），各自独立进程、互不阻塞
python3 .aidp/scripts/aidp_scheduler.py install [--agent claude|codex|dsh] [--dev-interval 10m] [--test-interval 5m]
python3 .aidp/scripts/aidp_scheduler.py status      # 定时任务是否在位 + 两条链路心跳
python3 .aidp/scripts/aidp_scheduler.py uninstall   # 停用并删除两个定时任务
```

- 平台：Linux = systemd --user timer（无 systemd 用户实例时用 crontab）；macOS = launchd；Windows = 输出 `schtasks` 命令手工执行。Linux 注销后仍要运行需执行一次 `loginctl enable-linger "$USER"`。
- 每个定时任务调用 `.aidp/scripts/agent_loop.sh --once <命令> --unattended`：自动补 `--no-loop`（`HAS_WAKE_SOURCE=1`，允许分 tick 让位）、导出 `AIDP_TICK_COMMAND`（Stop 护栏只拦 autopilot tick）与 `ARGUMENTS`、flock 互斥（上一轮未结束则本轮跳过）、日志落 `memory/.aidp/logs/<命令>.log`、加载可选的 `~/.config/aidp/env`（通知 webhook / CICD 令牌等凭据环境变量）。
- ⚠️ **两条链路缺一不可**：autopilot 只管开发链路（PRD→/version→/sprint-batch→触发部署），浏览器实测由 aiauto-test 链路负责；只跑第一条 = 测试半环永久缺失（Phase 3.4 step4③ 累加 `test_loop_missing_streak`，连续 ≥3 tick 后把 build 按静态-only 收尾 + 冻结告警）。
- **存活巡检**：每轮开跑前 `aidp_scheduler.py watchdog` 检查两条链路心跳（`autopilot_loop_heartbeat_at` / `aiauto_test_heartbeat_at`）；任一链路超过 `scheduler.stale_cycles × 周期` 无心跳且不在执行中 → 写本地告警台账 `memory/.aidp/alerts.jsonl` + 发里程碑通知（同一次中断只告警一次）。
- ★ **权限前置（headless 必做）**：非交互执行时未预授权的工具调用会被拒绝、整轮零进展。Claude Code 在 `.claude/settings.json` 的 `permissions.allow` 放行命令所需的 `Bash` / `Agent` / MCP 工具等（内置执行命令为 `claude -p --permission-mode acceptEdits {prompt}`）；Codex 需 `codex exec --sandbox workspace-write`（内置默认）且项目已 trust；DeepSeek Harness 须在 `memory/aidp-config.yaml` 的 `scheduler.exec.dsh` 填入其非交互执行命令。各 CLI 参数以所用版本官方文档为准，详见 `.aidp/reference/agent-tools.md` 第三节。

### #2 会话内 `/loop`（Claude Code 交互式短期用法）

```bash
/loop 10m /sprint-autopilot --unattended    # ① 开发链路
/loop 5m  /sprint-aiauto-test --unattended  # ② 测试链路
```

- `/loop` 是**会话级**定时任务：关闭 Claude Code 会话即停；定时任务 **7 天后自动过期**；只在会话**空闲**的轮次之间触发，同一会话里的两条 loop **实际串行**（一条长 tick 期间另一条被推迟，心跳会因此变旧）。适合临时观察、演示；需要 7×24 时用 #1。
- ★ **示例默认带 `--unattended`**：无人值守判据只看**本轮**信号，唤起时 prompt 不含 `/loop` 字样会误判为交互式而挂起等人，且每个 tick 重犯；显式带 `--unattended` 消除该单点。
- `/loops` 查看会话内运行中的 loop 与下次执行时间。

### #3 单次 / 临时模式

```bash
/sprint-autopilot                  # 用户首次直接调用 → 配置补全 + 提示挂载方式后退出
/sprint-autopilot --once           # 强制立即跑执行主流程（Phase 2/3）一次（不查 baseline）
                                   # ★ "一次" = 这一对版本的全流程做完（全部 Sprint + 部署 + AI 测试），
                                   #   不是"跑一个 Sprint 就收工"：无下一轮唤起时 HAS_WAKE_SOURCE=0，
                                   #   ⛔ 禁止 UNATTENDED_YIELD（yield 了没有下一 tick 来接 = 永久停摆）
/sprint-autopilot --no-loop        # 单次 baseline 检查（有外部调度会再次唤起时使用）
/sprint-autopilot --watch          # 单 Bash session 内挂 50 分钟轮询
```

- headless 单次（不经 `agent_loop.sh`）务必写全 `--once --unattended`，否则首个 `AskUserQuestion` 无人可答而挂起。

### 用法对比

| 用法 | 适用场景 | 会话关闭后 | 推荐度 |
|------|---------|----------|------|
| `aidp_scheduler.py install` | 7×24 无人值守（两条链路独立进程 + 心跳巡检）| 不受影响 | ★★★ |
| `/loop 10m /sprint-autopilot --unattended`（+ 测试链路一条）| 会话内临时观察 / 演示 | 停止（且 7 天过期）| ★ |
| `/sprint-autopilot`（直接调）| 首次配置补全 + 引导 | 不适用 | 配置 |
| `/sprint-autopilot --once` | PRD 已就绪，临时跑一次 | 不适用 | 单次 |
| `/sprint-autopilot --watch` | 临时挂 50 分钟监听 | 停止 | 临时 |

---

## 输出示例

> 📄 各场景（PRD 无变化 / 有更新触发 / 首次缺 autopilot_decisions / 规划已存在跳过）的**终端输出示例**已外置到 `.aidp/skills/aidp-code-engineer/references/autopilot/output-examples.md`（纯说明、执行时无需载入；想看命令打印样子时按需查阅）。

---


---

## 停止机制

| 方式 | 效果 |
|------|------|
| `python3 .aidp/scripts/aidp_scheduler.py uninstall` | 停用并删除两条链路的操作系统定时任务 |
| Claude Code 终端 Ctrl+C | 立即中止本次命令；如外层有 `/loop` 包装，需另跑 `/loops` 看面板停 |
| `/loops` + 中止对应 loop | 停掉会话内 /loop；后续不再唤起命令 |
| 关闭 Claude Code 会话 | 会话内 `/loop` 随之消失（操作系统定时任务不受影响）|
| `--reset-baseline` | 删 baseline 文件后退出（不进执行主流程（Phase 2/3））|

---


## 与其他命令的关系

| 命令 | 关系 |
|------|------|
| `/sprint-autopilot` | **顶层一键编排器**（本命令）|
| `.aidp/scripts/aidp_scheduler.py` ★ | **7×24 守护标准方式**：为开发链路 / 测试链路各装一个操作系统定时任务（经 `agent_loop.sh --once`），并做两条链路心跳巡检 |
| `/loop` | 会话内交互式短期用法（会话级、7 天过期、空闲触发、同会话串行）|
| `/version` | Phase 3.1 内部调用（上版准发布走 Phase 2 `/version --no-tag`）|
| `/sprint-batch` | Phase 3.2 内部调用 |
| `version-auditor` Agent | Phase 3.1（/version 内强制）+ Phase 3.3 终审（强制仪式）|
| `.aidp/scripts/emit-report.py` ★ | AI执行/测试报告确定性产出器：输入结果 JSON → 写 data + 注册 SPA 两页/一页（落本地 `docs/reports/{version}/`）+ 回写 `report_deliveries`（Phase 3.1.5/3.4/aiauto-test 3.2.6·3.7 调用；防手搓退化 markdown）|
| `.aidp/scripts/autopilot-ceremony-gate.py` ★ | Phase 3.4 完成核验门：确定性校验强制仪式（AI执行报告 SPA / **AI测试报告 SPA（有浏览器测试时）** / **报告交付台账** / version-auditor 报告 / 通知台账 / 无 markdown），exit 1 阻断带缺失收尾 |
| `.aidp/scripts/notify.py` ★ | 里程碑通知发送器：`--auto` 按 `memory/aidp-config.yaml` 的 `notify.channels` 依次尝试（飞书/钉钉/企业微信机器人 webhook、`lark-cli`、自定义命令），成功即停；退出码 3 = 未配置任何渠道 → 静默跳过本节点、不阻塞 |
| `.aidp/scripts/cicd_watch.py` | CICD 流水线监听（`--mode` watch / detect / poll，平台 = `cicd.provider`，默认 GitHub Actions）；触发/重试写动作由命令端显式调 `--mode trigger` / `--mode retry`，受 `cicd.auto_trigger` 控制（见 IRON-5）|


## 注意事项

1. **不自动 merge master / 不自动推 master / 不自动 tag**：严守「destructive 动作需人工」原则——**这三类**才需人工。**但 feature 分支的开发提交 + 推送是 autopilot 开发链路的正常职责、非 destructive 动作**：Phase 3.2「部署触发前置」步骤会在部署动作前对当前 feature 分支 `git add`+`commit`+`git push origin <feature 分支>`（用户执行 `/sprint-autopilot` 即为此持久授权，不再逐次确认），这是 push 触发型 CICD（`git-push` / `cicd-provider`）能启动的前提，**绝不省略**（省了 → CI 不触发 → 部署不发生 → 测试链路空等，正是要堵的下游卡死根因）。仅 `deployment.mode=none` / `--skip-deploy` 时只 commit 不 push。
2. **baseline 文件是单一信源**：PRD 变化检测仅靠 `memory/.sprint-autopilot-baseline.json`（项目级共享、入库；内部按 `versions.{V}` **按版本分字典、不按用户分桶**，绝不记录 git 用户名——见上方注「baseline 为项目级存储」）；删除等于"重置全部监听"，下次任意版本任意 PRD 变化都触发
3. **决策预声明的权威性**：`--full-auto` 模式下，PRD 头部 `autopilot_decisions` 是唯一信源（含部署字段）；命令运行中**禁止**自行修改这些决策（如发现冲突 → 走失败处置发里程碑通知 #4）
4. **失败暂停不退出**：命令进程保留，working tree + memory 现场不动；baseline **不更新**（下次唤起会重试同一份 PRD）；用户可以接管 / 重试 / 跳过 / 中止
5. **chrome 检测 / 安装 / 远端 IP 全部移至 `/sprint-aiauto-test`**：本命令不涉及 chrome（详见注意事项 11 + Phase 0.2）；MCP 安装方式见 `/sprint-aiauto-test` 命令文档
6. **首次使用必看 Phase 0.1**：按需配置 `memory/aidp-config.yaml` 的 `notify` 段（里程碑通知渠道，webhook 地址/密钥只经环境变量引用；未配置则所有通知节点静默跳过、不阻塞）；使用 CICD 流水线部署时先配置 `cicd.provider` / `cicd.pipelines` 并完成提供方登录或令牌环境变量
7. **★ `/sprint-autopilot` 的"准发布" ≠ 正式发布**：Phase 2 跑 `/version <prev> --no-tag` 只归档 SQL/文档/memory 但**不打 tag**；要正式打 tag + 部署，仍需运维手动跑 `/version <version>`（不带任何 flag = 完整发布模式，自动补打 tag）
8. **循环交给外部调度**：命令不自管循环。7×24 用 `aidp_scheduler.py install`（操作系统定时任务，两条链路独立进程）；会话内 `/loop` 仅作交互式短期用法（会话级、7 天过期、同会话串行）
9. **本地 dev server 端口冲突**：`deployment.mode=local` 时如果其他进程占用相同端口，命令会跳过启动并发 #4 通知提醒用户；多份 PRD 并行测试请配置不同端口
10. **云端部署探测超时不是部署失败**：`cloud_deploy_check_url` 探测超时只意味着"chrome 暂时没法测"，命令会发 #4 通知并暂停（保留状态）；用户人工确认部署成功后重新唤起命令即可继续
11. **★ AI 自动化实测/浏览器测试已独立为 `/sprint-aiauto-test`**：chrome-devtools-mcp 检测 / 智能启动 / 远端 IP / 登录元数据 / 账号收集 / credentials 文件 / 浏览器测试段全部由该命令承担（见 0.2），本命令只管开发链路、不触发浏览器。生产守护两条链路同时运行（`aidp_scheduler.py install`：开发链路监听 PRD + 测试链路监听部署），状态经 `memory/.sprint-autopilot-baseline.json` 共享。
12. **★ 装调度前必做一次：确认 CICD 提供方可用**（`deployment.mode=cicd-provider` 时）：提供方 CLI 已登录或令牌环境变量已设置（GitHub Actions = `gh auth status`；GitLab CI / Jenkins = `token_env` 等指向的环境变量），`memory/aidp-config.yaml` 的 `cicd.pipelines` 已映射本环境的流水线。流水线未配 push 自动触发时首次部署需命令端 `cicd_watch.py --mode trigger` 主动触发，这一写动作受 `cicd.auto_trigger`（默认 true）控制——设为 false 时无人值守会冻在第一次部署（`freeze_reason=cicd-auto-trigger-off`）。**正确做法二选一**：① 保持 `cicd.auto_trigger=true`；② 给流水线配上 push 自动触发，此后命令只接管监听。`cicd_watch.py` 退出码 3 分两类：`cicd.provider=none` 或未配置流水线（verdict `disabled` / `not-configured`）→ 按无远端流水线的轻量部署分支处理；提供方 CLI 未安装 / 未登录 / 凭据失效（verdict `cli-missing` / `unauthenticated` / `provider-unavailable`）→ 按 `cicd_cli_fail_streak` 记账、连续 3 次冻结为 `cicd-cli-unavailable`（环境类，装好或重新登录后自动复探解冻）；CICD 平台不可达同样按 `cicd_unreachable_streak` 连续 3 次才冻结为 `cicd-unreachable`。

13. **★ 三大铁律速查（正文已详述，此处仅索引、不复述规则）**：① Phase 0 一次性收齐所有会阻塞 Phase 2/3 的决策（详见 0.6）；② 执行前强制 `git pull`，否则漏检产品已 push 的新 PRD（详见 0.0）；③ Phase 3 先过 3.1.0「规划已存在则跳过门」，需推翻重规划加 `--force-replan`（详见 3.1.0）。
14. **★ AI 执行报告 = 执行结果（`index.html`，主入口）+ 执行计划（`plan.html`），合并拍平、共享 `data/`**：Phase 3.1.5 写 `AI执行报告/data/{BUILD}.js` 计划态（steps/features/元信息）+ 注册到 index.html/plan.html 两页（plan.html 渲染工作流/甘特/依赖/功能点比对）；Phase 3.4 finalize 同一份 data 的结果态（`AI执行报告/index.html` 渲染，与 AI测试报告同构、多 build 共享入口），报告只落本地 `docs/reports/`，#3 通知「查看完整报告」给仓库内相对路径（含 build 子页 hash）。#3 通知「测试结论」段在开发链路完成时填的是**静态自测结果**，完整浏览器实测以 `/sprint-aiauto-test` #F 通知为准（详见 0.1bis #3 模板的阶段语义标注）。
