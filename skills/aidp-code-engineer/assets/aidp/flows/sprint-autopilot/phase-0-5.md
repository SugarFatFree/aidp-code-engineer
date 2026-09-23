# sprint-autopilot · Phase 0 详情分片 [5/11]（0.1bis 通知骨架 + 应发通知集矩阵 + 通知模板）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 5/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.1bis（固定通知字段骨架 + ENTRY_MODE×应发通知集矩阵 + #F/#3/#1d 通知模板）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-5.md`。理据见同目录 `rationale.md`。

---

**★ 固定通知字段骨架 —— 禁止手搓结构、只填槽位**：所有里程碑通知**共用同一份固定骨架** = `notify.py` 的字段式参数（`--title --header-color --section --section-file --link-text --link-url --footer --node --version --build`），由脚本按 `memory/aidp-config.yaml` 的 `notify.channels` 渲染为各渠道消息（单一信源，约定 21 不在命令端另定结构）。执行体发通知**只允许填下列槽位、严禁自拼渠道 payload / 自创 header**：

| 槽位 | 取值 | 来源 |
|------|------|------|
| `--header-color`（色）| 见通知表 `header` 列：蓝=`blue` / 绿=`green` / 橙=`orange` / 红=`red` | 通知表 |
| `--title`（标题）★ | **固定前缀 + 本通知标题**：`{emoji} {项目名称中文} {version}_Build{N} · {通知名}`（前缀铁律见下「★ 通知标题固定前缀」）| 通知表 / 本通知模板首行 + 下方前缀规则 |
| `--section` / `--section-file`（正文 markdown）| 公共字段块 + 本通知「公共字段外的内容」；富文本通知（#3/#1d/#F）直接用其**已有完整模板**填槽 | 通知表 + 各通知模板 |
| `--link-text` / `--link-url`（报告链接）| 报告文件的仓库相对路径（或 GitHub 文件链接）| `emit-report.py` 返回值 |

> ★ **通知标题固定前缀（铁律 —— 所有节点的每一条通知都必须带，本节为两命令单一信源）**：`--title` **必须**以固定前缀开头，再接本通知自身标题，统一格式：
> ```
> {emoji} {项目名称中文} {version}[_Build{N}] · {本通知标题}
> ```
> ⛔ **`_Build{N}` 是条件段、不是无条件**：**仅"已铸 build"的通知（Phase 3.1.5 之后：#1d/#2/#D/#R/#F/#G/#3 等）才带 `_Build{N}`**；**铸 build 之前的通知（#0/#1/#1b/#1c/#pre-*）一律省略 `_Build{N}`**（典型误用：#0 启动通知误带 `_Build1001`）。详见下方「缺值优雅降级」。
>   - **`{emoji}`**：本通知情绪图标（成功 ✅ / 进行 🚀🛠️ / 测试 🧪 / 失败 ❌ / 告警 ⚠️ 等，沿用各通知原 emoji）。
>   - **`{项目名称中文}`**：取**公共字段同款** `项目名称`（中文优先：读 `memory/aidp-config.yaml` 的 `project.name_cn`；未填 → `project.name` → git 仓库名英文兜底，并建议填写 `project.name_cn`）。**绝不缺省**——防「标题常缺项目名」。
>   - **`{version}_Build{N}`**：版本 + build 序号（`{N}` = `{version}_build{N}` 的同一序号；标题展示用大写 `Build`）。
>   - **`{本通知标题}`**：即「通知表 `header` 列对应的通知名 / 本通知模板首行」（如 `部署完成 · 代码已推送`）。
>   - **缺值优雅降级**（少数通知尚无 version/build 时**前缀只截到已知粒度，但项目名称恒在**）：
>     - version + build 都已知（绝大多数里程碑通知：#1d/#2/#D/#R/#F/#G/#3 等）→ 全格式 `{emoji} {项目名称} {version}_Build{N} · {本通知标题}`。
>     - 有 version、build 未铸造（Phase 3.1.5 前的 #0/#1/#1b/#1c/#pre-*）→ `{emoji} {项目名称} {version} · {本通知标题}`（省 `_Build{N}`）。
>     - version 都未知（极少数 pre-scan 通知如 #0a 通道就绪）→ `{emoji} {项目名称} · {本通知标题}`（仅省版本段，**项目名称仍必须在**）。
>   - **取值来源**：`{项目名称}` 同公共字段；`{version}`=本轮 `TARGET_VERSION`；`{N}`=本 build 序号（baseline `current_build` 解析，未铸造则降级）。富文本通知（#3/#1d/#F）的标题**同样套此前缀**，正文模板不变。
>   - **★ 确定性兜底（不靠执行体自律）**：`notify.py` 在发送前对 `--title` 做**标题前缀补齐**——自动解析项目中文名称（`--project-name` > `AIDP_PROJECT_NAME` > `memory/aidp-config.yaml` 的 `project.name_cn` > `project.name` > 仓库根目录名，**任何分支都返回非空、绝不静默省略**），标题里缺项目名称/缺 `--version` 版本号即就地补上并在 stderr 打一行 `ℹ️ 标题已按固定前缀补齐`；解析只拿到英文目录名时另打 `⚠️` 提示填写 `project.name_cn`。执行体**仍须按本节写对标题**（兜底只是安全网，不是免检借口）；`_Build{N}` 属条件段，兜底**不臆造**、由各通知按语义写。

> 口诀：**结构交给 `notify.py`，内容只换槽位**；不得每条通知自拼一份不同结构的渠道 payload（结构漂移 = 通知噪音根因）。富文本通知（#3「AI执行报告」、#1d「部署完成」、#F「最终测试」）正文模板已在本节给全，照填即可；**标题一律按上「★ 通知标题固定前缀」拼**。

**★ ENTRY_MODE × 应发通知集矩阵（按入口精简，test-only 不发开发链路通知）**：执行体发任一通知前先按本轮 `ENTRY_MODE`（Phase 3.0 自动判定）查下表，**不在应发集内的通知一律不发**——

| ENTRY_MODE | 应发通知集 | 明确不发 |
|---|---|---|
| `full`（默认全流程）| #0 → #pre-start/#pre-done（有准发布对时）→ #1/#1b/#1c/#1d → #2（每 Sprint）→ #D/#R/#F/#G（条件）→ #3 → #4（失败时）（#0a 仅 `notify.channel_ready_card=true` 才发）| **#0a 默认不发** |
| `incremental`（增量路径，无 Sprint 拆分）| #0 → #1（仅当本轮真跑规划）→ #1b（**恒发**，含"复用已有规划"）→ #1c → #1d（会部署时）→ #D/#R/#F/#G（条件）→ #3 → #4（失败时）| **#0a**、**#2**（增量路径无 Sprint 可关，见 `phase-3-5.md`） |
| `test-only`（`--skip-dev` / test-intent 命中）| #D/#R/#F/#G → #3 → #4（失败时）（#0a 仅开关开启才发）| **#0a 默认不发**、**#0**（版本扫描=开发里程碑）、#1/#1b/#1c/#1d/#2/#pre-* 开发链路通知 **全部不发** |

> ⛔ **本矩阵与 `phase-3-9.md` 收尾门的 `EXPECT_CARDS` 必须逐条同源**：期望集里出现一条本轮"明确不发"的通知 → 台账恒缺 → 收尾门每 tick FAIL → `dev_fail_streak` 3 次即冻结版本。改动任一侧务必同步另一侧。**四个**条件通知的判据在此汇总（收尾门按此拼装）：**#1**（规划开始）仅 `PLANNING_DONE=0` 或 `--force-replan`；**#1d** 仅 `deployment.mode≠none` 且无 `--skip-deploy`；**#2** 仅非 `incremental`；**#G**（有头眼检）仅 `HEADED_CAPABLE=1`（配了远程 chrome MCP **或** 本机有 GUI，判定见 `sprint-aiauto-test/phase-3-4.md` Step 1）——⛔ 别因为它在上表与 #D/#R/#F 并列就当成恒发通知，两条期望集都**不无条件期望**它。⛔ **`#1b` 规划完成不是条件通知、是恒发通知**（`phase-3-3.md` step 3 无条件发，含"复用已有规划"）——曾被误与 `#1` 并列写成条件通知，与发送侧相反；期望集里必须恒有它。

> ★ **#0a 默认不发、#0 test-only 剔除**：**#0a（通道就绪通知）默认不发**（开关 `notify.channel_ready_card`，默认 `false`）——防零播报由**终端打印通知渠道来源日志 + 真实里程碑通知 #D/#F/#3 自然验证渠道**达成（更轻、不打扰接收方）；#0（版本扫描启动通知）属开发链路里程碑，test-only 无开发活动 → 不发。

**#F 最终通知必含字段**（除公共字段）：① 测试版本（应用版本号 + 测试轮次，如 `V0.2.0 / 第 3 轮`）② 测试结论（**通过 / 不通过**）③ 测试用例总数 ④ 测试通过数 ⑤ 测试失败数 ⑥ 测试阻塞数 ⑦ 测试用例忽略数 ⑦bis 不适用数（`na`，⛔ 不并进通过数）⑧ 自动化过程发现缺陷数 / 回归验证通过数 ⑨ 测试报告文件路径（★ 超链接显示文案固定为「AI测试报告」单一词，不加括注 / 不描述视图结构）。**报告本体由 `emit-report.py` 单一产出**：报告 SPA 已在 aiauto-test Phase 3 step 4 由 `emit-report.py --kind test` 落本地 `docs/reports/{version}/`（`report_deliveries` 已记）；#F 通知**直接引用它返回的报告路径**（仓库相对路径，或 GitHub 文件链接）作 `--link-url`，不另行打包分发。**禁止**通知指向 markdown、禁止手搓通知结构。#F 实际逻辑以 `/sprint-aiauto-test` Phase 3.7 为准。

> ★ **通知内「AI 自动化测试范围」标注规则**：凡通知（#3 下一步、#D 将开始测试、#R/#F 统计）描述将测 / 已测的**用例数 / 套件数 / 来源**，**一律按 `/sprint-aiauto-test` Phase 2.0「用例来源优先级」**：① `docs/testing/{version}/正式用例/`（测试人员正式方案 = **主集**）→ ② `docs/testing/{version}/研发自测/`（查漏**补集**；**仅当 `正式用例/` 为空时**才是唯一来源）。**贴来源标签时**：`正式用例/` **非空** → 必须写「**测试人员测试方案** N 例 / M 套件（来源：`正式用例/`）」（有补集再加「+ 研发自测查漏 K 例」），**严禁**在 `正式用例/` 已有正式用例时把范围标成「研发自测用例」；**仅** `正式用例/` 为空时才写「研发自测用例 N 例 / M 套件（`正式用例/` 为空，兜底）」。计数口径与 Phase 2.0 的 `find` 排除规则一致（排除 `00*` 管家 / `99*` 待澄清前缀文件），命令端不另算、不臆造数字。autopilot 发 #3 通知若要预告测试范围，按本规则先扫 `正式用例/` 再 `研发自测/`。
>
> ★ **对称计数铁律**：主集与补集**都必须报「用例条数（例）」**，口径一致。主集 `正式用例/` 的用例条数要**真实点算用例条目**（数每份用例文件内的**用例表格行 / `T-NNN` 编号 / 用例标题**），**严禁只报「N 份文件」就交差**（份数 ≠ 例数）；补集 `研发自测/` 同样报「查漏 K 例」。统一呈现为「**主集 {N} 例**（`正式用例/` {X} 份）**+ 补集 {K} 例**（研发自测查漏）= 共 {N+K} 例」。**反例**：「测试人员用例 2 份 + 研发自测 17 例」——主集只报份数没数条目；**正例**：先点算那 2 份正式用例的条目数，写成「主集 23 例（正式用例/ 2 份）+ 补集 17 例查漏」。若通知发出时点早于 Phase 2.1 用例解析（如 #D 在 Phase 1，Phase 2.0/2.1 尚未算 `TOTAL`）→ 该通知**仍需就地扫 `正式用例/` 用例文件点算条目数**，不能用份数顶替。

**#3 AI执行报告通知完整模板**——绿色 header；除公共字段（项目名称 / 工作目录 / 完成时间）外，正文按下模板填充（字段来源见每段右侧括注；**本通知发送时机 = #F 之后**——有浏览器测试时由测试链路 finalize AI执行结果 testSummary + 发报告本体后发（携带真实测试结论），静态-only 时由 autopilot Phase 3.4 末尾发）：

```
🤖 {项目名称} {TARGET_VERSION}_Build{N} · AI执行报告      ← 标题（`--title`，按上「通知标题固定前缀」）
📦 任务包：{项目名称}{TARGET_VERSION}_build{N}                  （{BUILD}）

📊 执行情况
{✅ 执行完成 | ⚠️ 部分完成} | {done}/{N} 功能完成 | {pend}待处理 | 测试通过率 {静态自测通过率}%
⏱️  执行时间：{build started_at} - {finished_at}（{总耗时}）

📋 需求功能执行清单                                              （每 Sprint 一行，来自 01_研发执行计划.md 标题 + close 状态）
🟢 1. {Sprint-001 标题}
🟢 2. {Sprint-002 标题}
⚠️  N. {未关闭 Sprint 标题} (待处理)
📊 小计：{done}/{N} 个 Sprint 完成 | {pend}个待处理
🎯 需求功能点覆盖：{doneFP}/{totalFP} 个功能点已完成（{完成率}%）          （来自 data `features` 逐条对照 01_研发需求.md，plan.html 功能点比对页可视化；逐条明细见完整报告）

🧪 测试结论                                                     （★ 真实浏览器测试结论 = 本 build #F 的 testSummary；静态-only 无浏览器测试时 = code-verification-loop 静态自测结果，并注明「静态自测、无浏览器测试」）
📊 测试执行统计
• 用例总数：{TOTAL}个
• 通过：{PASS}个 | 失败：{FAIL}个 | 阻塞：{BLOCK}个 | 忽略：{SKIP}个 | 不适用：{NA}个
• 总体通过率：{真实通过率}%
🐛 缺陷统计                                                     （来自 docs/bugfix/{TARGET_VERSION}/ + 研发自测「问题汇总清单」）
• 总数：{缺陷总数}个
• 🔴 P0（发版阻断）：{p0}个
• 🟡 P1（建议修改）：{p1}个
• 💡 P2（优化建议）：{p2}个
📈 覆盖率：{有则行/分支覆盖；静态阶段无则填「待 AI 自动化测试回填」}

⚠️  风险与建议                                                  （综合残留缺陷 + version-auditor 结论）
🔴 高风险
• {如 P0 未清 / 残留风险项}
🟡 中风险
• {如 P1 待处理 / 静态告警}
💡 建议
• {下一步优化建议}

📄 查看完整报告 → {AI_REPORT_URL}                              （★ 超链接显示文案固定为「AI执行报告」单一词，不加括注、不写"结果+计划双视图"等视图结构描述；链接 = 本 build 报告 HTML 的仓库相对路径或 GitHub 文件链接）
(包含：执行概览、全任务步骤执行结果、需求功能点逐条比对（对照 01_研发需求.md）、测试摘要、缺陷详情、剩余待办)

📌 下一步                                                       （#3 在 #F 之后发，本 build 测试已闭环）
1. 你 review + merge PR（代码已推 origin/{branch}）
2. 运维跑 /version {TARGET_VERSION} 正式打 tag + 取最终验收 build 生成版本测试报告
（静态-only 由 autopilot 发本通知时：本 build 无浏览器测试；如该版本后续部署可访问，再挂 /loop 5m /sprint-aiauto-test --unattended 补跑实测）
```

> ★ **#3 时序（#F 之后发，携带真实测试结论）**：#3 由 build 关闭方在 **#F 之后**发出——有浏览器测试时由测试链路 `/sprint-aiauto-test` 在 finalize AI执行结果 testSummary 后发（「测试结论」段 = **真实浏览器测试** 通过/失败/阻塞/忽略/不适用 + 通过率（分母 = 总数−不适用），见其 Phase 3.7）；纯静态（`deployment.mode=none`）无浏览器测试时由 autopilot Phase 3.4 末尾发（「测试结论」段 = code-verification-loop 静态自测结果，注明「静态自测、无浏览器测试」）。**不在开发完成时早发、不标「待 #F 回填」**——开发完成的里程碑由 **#1d 部署通知**承担。计数口径（用例数 / 缺陷数）按真实点算，不臆造（与 0.1bis 对称计数铁律一致）。

**#1d 部署完成通知模板**——蓝色 header；本通知在 **Phase 3.2 部署动作完成后**发出（`deployment.mode != none` 且未带 `--skip-deploy`），是**开发链路的收尾播报 + 测试链路的接力交接**。除公共字段外正文按下模板填充：

```
🚀 {项目名称} {TARGET_VERSION}_Build{N} · 部署完成 · 代码已推送      ← 标题（`--title`，按上「通知标题固定前缀」）
📦 版本：{TARGET_VERSION}（{BUILD}）
🌐 部署模式：{local | cloud} · 访问地址：{deploy_url}
🔀 代码已推：origin/{branch}（待你 review + merge）

⚠️  接力提示（开发链路到此结束）
AI 自动化测试由**独立测试链路** /sprint-aiauto-test 承担（与本命令 /loop 拆分）。
若你**尚未**挂起测试守护，请立即**并行**执行：

    /loop 5m /sprint-aiauto-test --unattended

不挂第二条 loop → 本次部署不会被探测 → 后续 AI 测试 / 测试报告（#D/#R/#F 通知）全部不会自动触发。
```

> ★ **不发 #1d 的两种情形**：① `deployment.mode=none`（纯静态，无部署动作）→ 不发 #1d（部署交接语义不成立）；② 带 `--skip-deploy`（用户主动跳过部署阶段）→ 不发 #1d。两种情形下「请挂第二条 loop」的接力提示由 Phase 3.4 的 #3 通知下一步导航兜底，不重复打扰。

> ⛔ **`chrome_preflight=blocked-no-fallback` 终止处理（Phase 0.5.5 预判的极端类落地 —— Q2 用户既定策略）**：当 Phase 0.5.5 驱动预判标记 `chrome_preflight=blocked-no-fallback`（远程 chrome MCP 需重启才生效 **且** 本机无 chrome 可兜底）时，浏览器测试在本会话内**根本无法执行**——按用户既定策略**绝不在 dev 前/后空等重启**，而是：① **开发 + 部署照常跑完**（dev 链路不依赖 chrome，#1d 该发照发）；② 跑完后**经里程碑通知告知原因 + 给出彻底解法（在 Claude Code 设备装 Chrome + 插件）**——在 #1d 接力提示**追加下面整段**（无 #1d 时则单独补发一条 #4 同款蓝/橙通知，正文同此段），**同时在终端原样打印安装命令**：
>
>     ⚠️ 浏览器测试未在本会话执行：远程 chrome MCP 需重启 Claude Code 才生效，且本机（Claude Code 设备）无 chrome 可兜底。
>     根因 = 本机缺本地兜底能力。彻底解法（二选一）：
>       【A 推荐 · 让本机能本地兜底】在 **运行 Claude Code 的这台设备** 上装 Chrome 浏览器 + chrome-devtools-mcp（npm 全局包自带 chrome-devtools-cli，装好后测试可走本机无头 cli，免远程、免重启、免 MCP 注册）：
>           # 1) 安装 Chrome / Chromium 浏览器（按本机 OS 装，无 GUI 也能跑无头）
>           # 2) 全局安装 chrome-devtools-mcp（含本地 CLI chrome-devtools-cli + 远程 MCP 服务）
>           npm i chrome-devtools-mcp@latest -g
>           # 3) 走本机无头 cli 无需注册 MCP、无需重启；即可挂 /loop 5m /sprint-aiauto-test --unattended
>       【B 走远程】重启 Claude Code 加载远程 .mcp.json 后挂 /loop 5m /sprint-aiauto-test --unattended，或换一台有 chrome 的机器跑测试。
>
> ③ **不 invoke `/sprint-aiauto-test`、不空等、不反复提示重启**，autopilot **正常收尾退出**（开发成果已交付、原因 + 安装解法已播报）。其余四类预判（`local-cli-ready` / `remote-ready` / `needs-restart-has-fallback` / `local-chrome-no-cli`）**不触发本终止**，照常委派测试链路（`needs-restart-has-fallback` 的 3 分钟窗口 + cli 兜底、`local-chrome-no-cli` 的 cli 修复回落或 `mcp-plugin-fallback` 显式降级均由 `/sprint-aiauto-test` 承担）。仅 `blocked-no-fallback`（本机无 chrome 且远程不可用）才触发本终止。
