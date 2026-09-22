# sprint-autopilot · Phase 0 详情分片 [4/11]（0.1bis 渠道选择 + 回落 + 通知公共字段）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 4/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.1bis（渠道选择 + 失败回落编排 + 通知公共字段）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-4.md`。理据见同目录 `rationale.md`。

---

### 0.1bis 通知机制：里程碑通知节点表（单一信源）

#### 渠道选择 + 失败回落（里程碑通知发送编排 · 单一信源）

> 里程碑通知经 `{{AIDP_HOME}}/scripts/notify.py` 发出。渠道在 `memory/aidp-config.yaml` 的 `notify.channels` 中按顺序声明，支持 `feishu`（飞书自定义机器人 webhook）/ `lark-cli`（飞书 CLI）/ `dingtalk`（钉钉机器人 webhook）/ `wecom`（企业微信机器人 webhook）/ `command`（自定义命令，从 stdin 读通知 JSON）。webhook 地址与签名密钥**只经环境变量引用**（`webhook_env` / `secret_env`），⛔ 不明文入库（约定 32）。「回落」= 同一条通知换下一个渠道重发，**不是**"通道坏了"。
>
> **★ 执行方式：渠道候选链已收编进 `notify.py --auto`，⛔ 执行体不手工编排。**
> 发通知一律照抄下面这段（**⛔ 是可执行语句，不是示意；每个节点都要真的跑一次**）：
>
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"   # ★ 必须在本围栏首行：
> #   shell state 不跨 Bash 调用，漏了它 $TARGET_VERSION / $BUILD 取空 → 通知以**空 version/build**
> #   登记进台账 → 收尾门的 `c.get("version")==V and c.get("build")==B` 恒不匹配 →
> #   「本 build 非零推送(台账≥1)」恒 FAIL → 每 3 tick 冻结一个健康版本。照抄时勿删。
> python3 {{AIDP_HOME}}/scripts/notify.py --title '…' --section '…' [--section '…'] \
>   [--link-text '…' --link-url '…'] --auto --node '#N' \
>   --version "$TARGET_VERSION" --build "$BUILD"
> ```
>
> ⛔ **「发通知 #N（见 0.1bis）」是【要跑这段命令】，不是【在终端 echo 一句】**：台账的唯一
> 自动登记者是 `notify.py`（且**仅当发送成功**才登记），而收尾门对台账的核验是**无条件**的
> —— 只要 `NOTIFY_ENABLED != 0` 就必查。发送侧不真跑 = 台账恒空 = 收尾门恒 FAIL。
> 脚本负责：读 `notify.channels` 解析候选链 → 依次实发同一条通知 → 成功即停；`notify.fallback=false` 时只试首个渠道。**退出码：0 发送成功；1 全部渠道失败；2 参数错误；3 未配置任何渠道（合规降级，等价 `NOTIFY_ENABLED=0`）。**
> **Why 收编**：渠道链若只以散文写在本片、靠执行体读到后照做，一旦本片被跳过，回落能力随之归零，退化成「首个渠道报错 → 弹窗问用户通知发哪儿」。写进脚本后，回落是否发生不再取决于执行体读没读到这一段。
>
> **配置落点（`memory/aidp-config.yaml` 的 `notify` 段，人维护、团队共享入库）**：
> - `notify.enabled`：总开关，缺省 `false`。
> - `notify.fallback`：一个渠道失败时是否尝试下一个，缺省 `true`。
> - `notify.channels`：有序渠道列表；排在前面的优先。
> - `notify.channel_ready_card`（可选，缺省 `false`）：是否发 #0a 通道就绪通知。
> - 自定义发送：`--sender '<命令>'` 可绕过候选链、把通知 JSON 交给指定命令（特殊场景使用；常规一律 `--auto`）。
>
> **★ 失败判据表（拿到具体错误时该回落还是该放弃 —— 本表只定编排处置）**：
>
> | 失败形态 | 含义 | 处置 |
> |---|---|---|
> | `webhook_env` / `secret_env` 引用的环境变量未设置 | 本机缺凭据 | 跳过该渠道、试下一个 |
> | HTTP 非 2xx / 超时 / 连接失败 | 渠道暂不可用 | 换下一个渠道重试 |
> | 平台返回业务错误（签名校验失败 / 关键词不匹配 / 频率限制） | 该渠道配置有误或被限流 | 换下一个渠道重试；全部失败时 stderr 如实打印各渠道错误 |
> | `lark-cli` / `command` 命令不存在或非零退出 | 宿主工具不可用 | 换下一个渠道重试 |
> | 其余任何失败 | 未分类失败 | 一律**先换渠道重试**，不预设"这是真不可用" |
>
> ⛔ **唯一允许放弃本播报节点的条件 = 候选链里每个渠道都【实测发过且都失败】**（脚本 exit 1）或**未配置任何渠道**（exit 3）。此时按 `NOTIFY_ENABLED=0` 语义**静默跳过、不阻塞主流程、不登记台账**；**⛔ 绝不因发送失败弹窗询问用户「通知发到哪里」**——无人值守下弹窗即挂起，有人值守下也只是把通道问题变成打断。exit 3 时同 `phase-0-2.md` Step 3 落盘 `notify_enabled=false`。`needs_human` / 熔断信号仍照落 baseline + 终端强警（见下）。
>
> **就绪期自查**：`python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py check` 会对已配置渠道做一次只读检查（加 `--record-probe` 另把探测证据落 baseline `notify_probe`）（凭据环境变量是否存在、命令是否可执行，不发消息），把「已配置」与「具备发送条件」分行显示。⚠️ 检查是提示不是拦截：未确认可达仍照发，且 `gate` **不受检查影响**（必须离线可跑）。

> 全部播报节点集中在此表定义；下文各 Phase 只写「发通知 #N（见 0.1bis）」不再重复内容。
> ⛔ **「发通知 #N」= 真跑上面那段命令，不是写一行注释**（`# 发 #4 通知（见 0.1bis）` 不算发）。
> **#4 尤其要当心**：它是**冻结时刻唯一对外可见的信号**——`needs_human` 落在 baseline 里、
> 终端 ⛔ 强警只在当场可见，**凌晨无人值守时运维两者都看不到**（除非自行配 `jq` 巡检）。
> 而 #4 **不在任何收尾门的期望通知集里**（`EXPECT_CARDS` 只含 #0/#1/#1b/#1c/#1d/#2/#3），
> 漏发不会被任何门抓到 ⇒ 表现为「停了，但没人知道」。**每个冻结点都必须真调一次 `notify.py --node "#4"`。**
发送方式统一：**通知** = `notify.py --auto`（候选链/回落全在脚本内，见上节；默认蓝色 header，`#4` 用 `--header-color red`）；**报告本体** = 落本地 `docs/reports/{version}/…`，通知里以 `--link-text` / `--link-url` 附**仓库内相对路径**（或 GitHub 文件链接）。`NOTIFY_ENABLED=0` 时所有节点**静默跳过**（仅终端日志标「通知跳过」）。**★ 但熔断 / `needs_human` 冻结不受通知降级影响（关键失败信号绝不因通道关闭而丢）**：所有冻结路径（`dev_fail_streak` 达阈 / Step A0 流水线识别不出 / Step D 账号缺失 / 测试链路未挂载收敛等）**始终把 `needs_human=true` + `needs_human_reason` 写入 baseline**（机器可读——外部 cron / 巡检可 `jq -r '.versions[]|select(.needs_human==true)'` 抓取待人工版本）**+ 终端打印显式 `⛔` 强警**；`NOTIFY_ENABLED=0` 只是少了 #4 通知推送，**冻结事实与原因仍持久落 baseline + 终端可见**，不构成"静默卡住无人可知"。**★ 发通知 + 台账登记（强制仪式可校验化 · ★ BUG-4 修复：字段入参 + 成功才登记）**：`NOTIFY_ENABLED != 0` 时，发通知**一律经 `notify.py` 按字段入参发送**，**⛔ 绝不手拼整份通知 JSON**（正文含中文 + 一个 ASCII 双引号即让整份 JSON 解析失败——实跑踩中过）：`python3 {{AIDP_HOME}}/scripts/notify.py --title '…' --section '…' [--section '…'] [--link-text '…' --link-url '…'] --auto --node '#N' --version "$TARGET_VERSION" --build "$BUILD"`（转义由脚本 `json.dumps` 负责；渠道候选链与失败回落亦由脚本负责，见上节——**⛔ 常规路径别手工传 `--sender` 自选发送命令，那会丢掉回落**）。**★ `--title` 必须按 0.1bis「通知标题固定前缀」写全 `{emoji} {项目名称中文} {version}[_Build{N}] · {本通知标题}`**——`notify.py` 另有**确定性兜底**：项目中文名称（`--project-name` > `AIDP_PROJECT_NAME` > `memory/aidp-config.yaml` 的 `project.name_cn` > `project.name` > 仓库根目录名，恒非空）与 `--version` 版本号若不在标题里会被自动补齐并在 stderr 提示，但兜底是安全网、不免除按规范写标题的责任。**★ 台账仅在发送成功（`notify.py` 返回 0）后由它自动登记 `record-card`**——发送失败**不登记**（堵"先登记后发送、发送失败留假台账骗过 ceremony-gate"）。build 未铸造的 #0/#pre-* 等可省 `--build`。〔仅在特殊场景无法用 `notify.py` 时才回退手工 `autopilot-ceremony-gate.py record-card --node '#N' …`，且必须自行保证"确已发送成功才登记"。〕<!-- proseexec-check: ignore 手工 record-card 是「notify.py 用不了」时的回退说明，正常路径由 notify.py 自动登记，不该有独立可执行落点 -->这让 Phase 3.4 完成核验门能据台账确定性核验「通道可用却整次零推送 / 漏发应发通知」——通知虽无本地产物，台账把"静默省略 + 事后说已精简"这条路堵死。`NOTIFY_ENABLED=0`（合法降级）时不发也不记。

**所有通知公共字段（每个节点都含）**：`项目名称`（**中文优先**：读 `memory/aidp-config.yaml` 的 `project.name_cn`（如「订单管理平台」）；未填 → `project.name` → git 根目录名英文兜底，并建议填写 `project.name_cn`）、`工作目录`（绝对路径）、**时间字段（★ 标签按通知语义取，值恒为发送时刻 `date '+%Y-%m-%d %H:%M:%S'`）**。
> ⛔ **时间字段标签分层（开始类通知显示"完成时间"是语义错）——按节点语义区分标签**：
> - **开始/进行类通知 → 标签「开始时间」**：#0 启动 / #pre-start 准发布启动 / #1 规划开始 / #1c 开发开始 / #D 部署完成-开始测试（测试开始语义）。
> - **完成/结束类通知 → 标签「完成时间」**：#pre-done 准发布完成 / #1b 规划完成 / #2 Sprint 关闭 / #1d 部署完成 / #3 执行报告 / #R 每轮测试结束 / #F 测试完成 / #G 眼检 / #4 失败。
> - 里程碑时序参照：开发开始(开始时间) → 开发完成/部署完成(完成时间) → 测试开始(开始时间) → 测试完成(完成时间)，每节点一张、时间标签与节点语义一致。

| 通知 # | 触发节点 | 命令 | header | 公共字段外的内容 |
|--------|---------|------|--------|----------------|
| #0a 通道就绪（**默认不发**）| 0.0 Step 2：**仅当 `notify.channel_ready_card==true`** 才发（默认 `false` → 只终端打印通道就绪 + 渠道列表）| autopilot | 蓝 | `✅ AIDP autopilot 通知渠道已连通，里程碑将在此播报`。**默认关闭以免每次发"已连接"噪音通知**；防零播报已由终端渠道日志 + 真实里程碑通知 #D/#F/#3 兜住 |
| #0 启动 | 0.3.6 识别最近一对后 | autopilot | 蓝 | **本通知标题固定为「启动 · 本轮计划」（★ 非"开始开发/开始开发测试"——那是 #1c 的语义，避免与 #1c 撞词）**；正文 = 本轮计划：Phase 2 准发布 `<上版>` / Phase 3 全流程 `<下版>`（版本扫描结果，不阻塞、仅通知）|
| #pre-start | Phase 2 启动 | autopilot | 蓝 | 上版 `<V>` 开始准发布（`--no-tag` 模式）|
| #pre-done | Phase 2 完成 | autopilot | 蓝 | 上版 `<V>` 准发布完成（归档 SQL+文档，未打 tag）|
| #1 规划开始 | Phase 3.1 `/version` 执行**前**（**仅当真正要跑规划**：`PLANNING_DONE=0` 或带 `--force-replan`；规划已提前完成 `PLANNING_DONE=1` → **跳过本通知**）| autopilot | 蓝 | 开始版本规划 `<V>`：触发原因 / PRD 目录 / 模式 / 分支 / 即将生成 研发需求·详细设计·接口·数据库·执行计划·自测用例 |
| #1b 规划完成 | Phase 3.1 `/version` 后（**总是发**，含复用已有规划）| autopilot | 蓝 | {版本规划完成 \| 复用已有版本规划}；将执行 N 个 Sprint + 研发需求/设计/执行计划 产物路径 |
| #1c 开发开始 | Phase 3.2 `/sprint-batch` 执行**前**（**总是发**）| autopilot | 蓝 | 开始开发 `<V>`，共 N 个 Sprint（逐个 start→dev→test→bugfix→close）+ 分支 / 部署模式(local/cloud/none) |
| #2 Sprint | Phase 3.2 每个 Sprint 关闭 | autopilot | 蓝 | Sprint-NNN 关闭（i/N）+ 标题 |
| **#1d 部署完成-代码已推送** ★ | Phase 3.2 部署动作完成后（`deployment.mode != none` 且未带 `--skip-deploy`；**总是发**）| autopilot | 蓝 | 版本、部署模式(local/cloud)、访问 URL、代码已推 origin/`<branch>` + **★ 接力强提示**：测试链路独立，**如尚未挂 `/loop 5m /sprint-aiauto-test --unattended` 则后续 AI 自动化测试不会自动开始**——请立即并行挂起（详见模板「#1d 部署完成通知模板」）|
| **#3 AI执行报告** ★ | **#F 之后**（build 关闭方 finalize 后发：有浏览器测试=测试链路在 #F 后发；静态-only=autopilot Phase 3.4 发）| **aiauto-test**（静态-only=autopilot）| **绿** | **完整模板见 `phase-0-5.md`「#3 AI执行报告通知完整模板」**：任务包 build / 执行情况 / 需求功能执行清单 / 测试结论（**真实浏览器测试结论**，来自本 build #F；静态-only=静态自测无浏览器）/ 缺陷统计 / 风险建议 / 查看完整报告（→ `$AI_REPORT_URL`：仓库内报告相对路径 / GitHub 文件链接）+ 下一步导航 |
| **#D 部署完成-开始测试** ★ | aiauto-test Phase 1 部署就绪 | aiauto-test | 蓝 | 版本号、部署模式(local/cloud)、访问 URL、渲染模式 + 驱动(cli/mcp)、测试范围（按★测试范围标注规则，`正式用例/` 优先）|
| **#R 每轮测试结束** ★ | aiauto-test 每轮末 | aiauto-test | 蓝/橙 | 版本+轮次、本轮 通过/失败/阻塞/忽略/**不适用**（⛔ 不并进 pass）、本轮新发现缺陷数、是否收敛、报告路径 |
| **#F 最终测试完成** ★ | aiauto-test 收敛/结束 | aiauto-test | 绿/红 | **见 `phase-0-5.md`「#F 最终通知必含字段」+ 附报告路径** |
| #G 有头眼检 | aiauto-test Phase 3.6（**全程无头**跑完 + **环境具备有头能力**自动触发：已配远程 chrome MCP 或本机有 GUI；不询问用户）| aiauto-test | 蓝 | 版本、方式=有头仅打开主要功能界面肉眼验证（**非完整用例**）、待打开页面清单、驱动切换方式(cli 即时 / mcp 需重启) |
| #4 失败 | 任一 Phase 卡住 | autopilot/aiauto-test | 红 | 阶段、错误摘要(≤200 字)、日志路径 |

> ⛔ **#0 与 #1c 差异化（避免连收「…开始开发测试」+「…开始开发」两条近义通知）**：#0 与 #1c 是**两个不同里程碑、不合并**（#0=启动·本轮计划/版本扫描结果，#1c=开发开始+Sprint 数+分支+部署模式），但**标题必须差异化、绝不都读作"开始开发"**——#0 标题「启动 · 本轮计划」、#1c 标题「开发开始」；#0 正文只讲"本轮要跑什么版本/阶段"，不讲"开始开发"。`test-only` 模式 #0 本就不发（见 0.1bis 通知集矩阵），full 模式两条通知语义各一、不冗余。

