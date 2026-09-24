# {{AIDP_HOME}}/scripts/ — AIDP 工具脚本

> 模板仓库 `.aidp` 中的 scripts 只作维护源；本目录由脚手架 `aidp-code-engineer` 下发到当前 Agent 的 `{{AIDP_HOME}}/scripts/`，供命令端 / CI / 开发者调用（使用安装后的路径 `python3 {{AIDP_HOME}}/scripts/<脚本>`）。非 Git 项目不会自动 `git init`；脚本的 Git 专属能力不适用时须显式记录，不得视为发布成功。
> 脚本是**脚手架契约**（随版本升级覆盖更新），请勿在下游项目内手改；需变更回到模板仓库修改后升级下发（约定 16）。

> ⚡ **不确定某个脚本怎么调？别猜、别翻文档**——本目录与各 SKILL `scripts/` 下的脚本 CLI 形态
> **互不统一**（位置子命令 / `--paths` / 单个位置路径 / 多个位置参数都有），猜错只会拿到一行
> argparse 原文报错。直接问它自己：
>
> ```bash
> python3 {{AIDP_HOME}}/scripts/scripts_usage.py <脚本名片段>   # 不带参数 = 列全部
> ```
>
> 它现场跑 `--help` 取真值，**永不过期**（手写速查表必然过期，那是又一处「加东西的人不会
> 想起去改」的副本）。⚠️ usage 里**不带 `--` 的那些是位置参数**，是最常踩的一类。

## aidp_runtime.py — 运行包与项目根路径解析

供运行脚本导入 `runtime_root()`、`project_root()` 和 `runtime_text()`：从脚本位置识别模板仓库或 Agent 原生运行包，展开运行路径，不依赖 Git 查找项目根。它是库模块，不作为独立命令调用。

## vcs.py — Git 能力检测与非 Git 降级

供脚手架和 Git 专属脚本导入 `detect_mode()`、`developer_identity()`、`unsupported()`；非 Git 能力返回 `vcs-disabled`，退出码为 3。

另带一个极薄 CLI 供 flow / 命令的 bash 段取值：
`python3 {{AIDP_HOME}}/scripts/vcs.py mode [--root DIR]` → 打印 `git` 或 `none`。
⛔ **别再写内联 `python3 -c 'from vcs import detect_mode …'`**：那种写法此前在 flows / commands 里逐字复制了 6 份，既撑分片体积（单处 ~90B），又把「探测口径」散成 6 处——改判据时必漏一处。

## chrome-mcp-doctor.py — chrome-devtools-mcp 远程连接配置强制校验 + 配置器

`/sprint-aiauto-test` / `/sprint-autopilot` 连接**远程 Chrome** 做浏览器自动化测试时，
「写/合并项目根 `.mcp.json` + 连通性预检 + 用户级/全局 MCP 配置污染检测 + 安装状态 + 生效验证指引」的**单一信源**。
把散文式「禁改清单」固化成有退出码的硬闸，杜绝 Agent「`.mcp.json` 看似不生效 → 去改用户级/全局配置」的违规反模式。
`check` 还会探测 chrome-devtools-mcp 是否已装（npm 全局包 / 本地 CLI / 历史插件任一），未装时**一键打印**安装命令（`npm i chrome-devtools-mcp@latest -g` + 远程 `claude mcp add … --scope project`，降低安装摩擦，不必翻文档）。

### 用法

```bash
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py check                 # 体检（默认）：读 .mcp.json + 连通预检 + 污染检测 + 生效指引
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py check-cli             # 本地 CLI 驱动可用性（五类驱动判定的单一信源）
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py explain-error         # 把 chrome / MCP 报错串翻成处置建议
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py check --ip 192.0.2.5:9222   # 指定目标做连通预检
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py set --ip 192.0.2.5:9222     # 写/合并远程条目 chrome-{git_user} 后自动体检
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py set --local-headless       # 本地无头兜底：切 chrome-devtools-cli（清 MCP 条目、免重启）
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py reset                      # 删除 chrome-{git_user} 条目（= --reset-chrome-ip）
python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py check --json               # 末尾追加机器可读 JSON（命令端按退出码 + JSON 分流）
```

### 退出码（命令端按此分流）

| 码 | 含义 | 命令端应做 |
|---|---|---|
| 0 | READY 配置就绪 | 继续连接（远程用工具前缀 `mcp__chrome-{git_user}__*`） |
| 3 | NO_CONFIG `.mcp.json` 缺条目 | 跑 `set --ip <IP:9222>` |
| 4 | UNREACHABLE 远端连不上 | 按打印的 Chrome 启动参数修复远端 + 重启 Claude Code 后重试 |
| 5 | POLLUTED 用户级/全局 MCP 配置被写脏 | 按打印的复位指引移除该注册（移除 `--scope user`/全局注册、历史插件残留则卸载；**绝不手改**用户级/全局文件） |
| 2 | USAGE 参数错误 | 修正参数 |

### 铁律（脚本强制 + 文档约束）

- 远程地址**只**写**项目根 `.mcp.json`** 的 server 条目 `chrome-{git_user}`（按 git 用户名分键、入库共享、JSON 合并保留其它 server）。
- **绝不**读改 `~/.claude.json`（`claude mcp add --scope user`/全局注册落地处）/ `~/.claude/settings*.json` / 历史遗留 `~/.claude/plugins/` 等任何用户级/全局 MCP 配置（脚本只**只读探测**它们是否被写脏并给复位指引）。
- 远程注册强制 `--scope project`（写项目根 `.mcp.json`）、服务名强制 `chrome-{git_user}`；**禁用**通用名 `chrome-devtools` 与 `--scope user`/全局。
- 新增/改动 `.mcp.json` server → 必须**整体重启** Claude Code 才生效；`/mcp` 重连加载不了新增条目。
- 远程连接调 `mcp__chrome-{git_user}__*`，不要调通用名的 `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`。

> 详细规则单一信源见 `{{AIDP_HOME}}/commands/sprint-aiauto-test.md` 的 0.1.1.4 / 0.1.1.5。

## autopilot-preflight.py — Phase 0 通道与配置就绪只读检测器 + 结构化硬门

`/sprint-autopilot` / `/sprint-aiauto-test` 的 **Phase 0「通道与配置就绪」单一信源**：把散文铁律
（"必须先发 #0a 里程碑通知"）固化成**确定性、有退出码、跳不过去**的硬门。解决根因——
"脏工作区 → 立即 exit"若排在发通知之前，会导致「通道全就绪却整次零推送」。

**只读**：读 `memory/aidp-config.yaml` 的 `notify` 段（经 `notify.channel_ready` 逐渠道核凭据）+ 判 `.mcp.json` 的
`chrome-{git_user}` 条目（chrome 维度**复用** `chrome-mcp-doctor.py`）+ 列 git 非 PRD 脏改动。
**绝不写配置、绝不发通知、绝不问用户**——发 #0a 通知、就脏树让用户决策这些**交互动作留在命令端**（子进程做不到）。
脚本负责"查得准、拦得住"，命令负责"在最前面发通知/就问"。

### 用法

```bash
python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py check                       # 就绪体检（默认）：打印就绪表，恒 exit 0（信息态）
python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py check --json                # 末尾追加 JSON，供命令端读各项布尔值分流
python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py check --record-probe        # 另把通知通道探测证据写入 baseline notify_probe
python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py gate                        # 收尾核验门：默认必需 notify，缺即 exit 1
python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py gate --require notify,mcp_chrome   # 需远程 chrome 时加校 mcp_chrome
python3 {{AIDP_HOME}}/scripts/autopilot-preflight.py gate --require notify --interactive # 交互式调用：通知启用却无可用渠道时不放行
```

可校验项（`--require` 取值）：`notify`（`notify.enabled=false` 视为满足；启用时至少一个渠道**本地可用**——webhook 渠道 = 对应 `*_env` 环境变量已设置、`lark-cli` = 命令在 PATH 且配了 `chat_id`、`command` = 命令非空；启用却无可用渠道时无人值守视为降级满足（冻结 / 告警照常写本地告警台账 `memory/.aidp/alerts.jsonl`），**`--interactive` 下不满足**）/
`mcp_chrome`（仅"需远程 chrome"时要求）/ `clean_tree`（一般**不**进 gate，脏树走命令端决策门）。

### 退出码（命令端按此分流）

| 码 | 含义 | 命令端应做 |
|---|---|---|
| 0 | READY check 恒 0 / gate 全部必需项就绪 | 继续：check 后按缺失项补做；gate 通过则进 Phase 1/2/3 或委派 |
| 1 | MISSING gate 有必需项缺失 | 就地补做（补渠道环境变量或关通知 / 写 .mcp.json）后**复跑本门**，不得带缺失往下 |
| 2 | USAGE 参数错误 | 修正 `--require` 取值 |

### 铁律（脚本强制 + 文档约束）

- **顺序铁律**：Phase 0 最前先 `check`，命令端据此**先发 #0a 通知 + 写 .mcp.json**，**再**做拉码/脏树等可能 exit 的门；进入 Phase 1/2/3 或委派 `/sprint-aiauto-test` 前必须 `gate` 通过。
- **脏树不静默退**：非 PRD 改动走命令端 `AskUserQuestion` 决策门（commit/stash/abort），无人值守给安全默认（跳过 pull + #4 告警）。
- **Phase 0 必问白名单**：通知渠道确认属一次性前置配置收集，其"必问"**不受**"零弹窗 / 禁止中途阻塞 / test-only 精简"约束；仅无人值守允许降级。
- **密钥不入库**：通知渠道的 webhook 地址 / 密钥只经环境变量引用（约定 32），本门只判变量是否已设置、不读不打印其值。

> 详细规则单一信源见 `{{AIDP_HOME}}/commands/sprint-autopilot.md` Phase 0 / `{{AIDP_HOME}}/commands/sprint-aiauto-test.md` Phase 0.2。

## emit-report.py — AI执行/测试报告确定性产出器（防手搓退化 markdown）

`/sprint-autopilot` / `/sprint-aiauto-test` 产报告的**唯一机械通道**：输入执行体产出的「结果 JSON」，
自动 ① 缺骨架则 cp 模板（清示例 data）② 写 `data/{build}.js`（exec→`__AIRUNS__` 注册 index+plan / test→`__BUILDS__` 注册 index）
③ 反检拒绝违规 markdown ④ 报告只落本地 `docs/reports/`，生成带 `#/build` hash 的仓库内相对访问路径
⑤ exec 报告的 `testSummary` 恒从同 build 测试报告 `summary` 派生（输出回报 `testSummary_derived`）
⑥ `--record-baseline 1` 时回写 baseline `report_deliveries.<build>.<exec_report|test_report>` = `{delivery, url, at, integrity}` 供收尾钢门校验（`0` = 骨架态不登记；`integrity` 为内容摘要，收尾门据此判篡改，与文件 mtime 无关）。用法：
`python3 {{AIDP_HOME}}/scripts/emit-report.py --kind exec|test --version V --build B --data 结果.json [--record-baseline 0|1] [--patch] [--json]`（`--json` 输出含 `report_path` / `access_url`；`--patch` = 只传变化字段、顶层浅合并回填）；
`python3 {{AIDP_HOME}}/scripts/emit-report.py verify-reports [--repo-root .] [--json]` 批量契约校验 + 摘要防篡改巡检全部历史 build 报告（`--help` 的 epilog 同列）。
执行体只产结果 JSON、绝不手写 data / 手工 sed 注册（那正是"只落 markdown"退化的根因）。

## autopilot-ceremony-gate.py — 无人值守强制仪式硬门 + 里程碑通知台账

`/sprint-autopilot` / `/sprint-aiauto-test` 的**关键产出不许偷省**确定性硬门：`check` 子命令核验本 build 的
AI执行报告 SPA + **AI测试报告 SPA（有浏览器测试时 `--will-browser-test 1`）** + **报告交付台账（`report_deliveries`，含内容摘要，非只落 markdown）**
+ version-auditor 报告 + 里程碑通知台账（`--notify 1` 校台账；`--notify 0` = 合法降级，须有 baseline `notify_probe` 举证）+ 无违规 markdown 是否齐全，缺失且无合法降级 → exit 1 卡住收尾；
`record-card --node N --version V [--build B]` 把已发通知追加进台账（由 `notify.py` 发送成功后调用）。**test-only 路径两处强制跑**（委派前骨架门 + 收尾全量门），杜绝"以交互式/省时为由"把报告偷省成一份 markdown + 手搓通知。

### `handback-check` — 中途交还控制权检测（与「产物齐全」同级的结构级门）

「强制仪式产物必须齐全」早已从自律级升级为结构级（缺产物 `exit 1`，执行体绕不过）；而「不许中途把控制权交还用户」一直**只有文档谴责、没有机器门**——两条规则强制度不对称，可后者失效的后果（整轮停摆）并不更轻。真实事故：规划段跑完就问"要我继续进入开发阶段吗？"，本轮 `HAS_WAKE_SOURCE=0`、没有下一 tick 会来接，Phase 3.2~3.4 连同全部 Sprint 被丢回给用户。

**判据（两个值本就落盘，纯确定性、无需新增采集）**：`autopilot.wake_source_this_tick == 0` **且** `versions.{V}.run_state.next_phase` 或 `next_sprint` **任一**非空且 ≠ `done` → VIOLATION，`exit 1`。
- ⚠️ **两个都要看**：命令正文原有的反向硬断言只写了 `next_sprint != "done"`，而真实事故停在 Phase 3.1→3.2 边界——那时 `next_phase="3.2-dev"` 而 `next_sprint` 尚未进入循环，旧判据恰好判不出来。
- ⚠️ **空值不算违背**：`next_phase` 为空 = Phase 状态机从未启动，对应「Phase 1 无变化干净退出 / 版本已交付 / 停在配置向导」等合法 bailout，那些路径由 `--no-pipeline-reason` 各自负责大声说清依据。
- **★ 判定式、不看话术**：文档一度点名禁"如需无人值守请挂 `/loop`"这一类**具体措辞**，而真实失效用的是"要我继续吗 / 你想先看看吗"这种征询式变体——措辞不同、实质一样，于是没被自己的禁令拦住。**枚举话术堵不住，只看客观状态才堵得住**。

用法：`python3 {{AIDP_HOME}}/scripts/autopilot-ceremony-gate.py handback-check --version <V> [--wake-source 0|1] [--record] [--json]`。`--record` 把判定写回 `autopilot.last_handback`，供下一轮 Phase 0.0.0bis 开局识别"上轮丢过活儿"并直接续跑。⛔ **刻意不并进 `check`**：那道门在测试链路 Phase 3.7 / autopilot 3.4 step2 就跑，而 `run-state … done` 要到 phase-3-9 收尾才写，此刻 `next_phase` 必然仍是非终态——并进去就是每轮必 FAIL 的假阳性（与当初拆 `--stage skeleton|final` 躲的是同一类时序坑）。故唯一落点 = **命令返回前**。

## report_render_smoke.js — 报告 SPA 离线渲染冒烟（白屏 / undefined / 口径自检）

被 `autopilot-ceremony-gate.py`（3h 渲染冒烟）与 `tests/` 复用：用最小 DOM stub 加载 `data/{build}.js` + `assets/app.js`，把 hash 设为 `#/build/{build}` 触发路由后断言 `#view-build`——① 无未捕获异常 ② 渲染长度 > 500（白屏必挂）③ 无字面量 `undefined`/`NaN` ④ 无 ≥1000% 的百分比（`10000%` 类口径错）。输出一行 JSON，`exit 0`=通过 / `1`=不通过 / `2`=用法或文件错。
用法：`node {{AIDP_HOME}}/scripts/report_render_smoke.js <reportDir> <build>`（`reportDir` = `docs/reports/{V}/{AI执行报告|AI测试报告}`）。

## code_inventory.py — 代码现状清单的跨版本增量缓存（sprint-design Step 0.6.4.7 内核）

Step 0.6.4.7「扫描代码现状清单」原文写死**全扫（不增量）**、产物又落在版本目录，于是**每个版本从零重扫整个 `code/`，上一版的结论一点都不复用**——这是整条 `/version` 链路里**唯一真正随累积增长**的环节（其余跨版本读取都已收敛到 `{prev_version}` 或走"变更重算 + 其余前滚"）。本脚本把清单提到项目级 `memory/_facts/code-inventory.json`，按**文件内容 sha** 增量维护：首跑全扫，之后只重新解析内容变了的文件。
抽取 5 个维度（与 Step 0.6.4.7 表格一一对应）：后端 API 端点（Spring `@*Mapping` / Express-Koa `router.*` / FastAPI）、数据库表（`sql/**` 的 `CREATE TABLE` 为权威 + ORM `@Entity` 辅助）、前端路由（Vue Router / React `<Route>` / **文件式路由**按 `pages/` 目录派生）、前端页面、配置文件（只列文件、不展开配置项——约定 25）。
**★ 按 sha 而非 `git diff <commit>..HEAD`**：git diff 漏未提交改动、对浅克隆/变基/换分支不稳（旧 commit 可能已不可达），取不到差异就得静默退回全扫而调用方看不出来；sha 比对是纯本地 IO，**任何来源的改动都不会漏**。
**★ 两条实测校准**（改动时勿退回）：① 文件式路由（unplugin-vue-router / Next.js / Nuxt）的路由不写在 `router.ts` 里而由 `pages/` 目录派生，不支持则这类项目「前端路由」维度恒为 0——看着像"扫过了没有路由"，实为漏抽；② `pages/x/components/Foo.vue` 是就近放置的子组件，既不是页面也不是路由，不排除会让页面数虚高（实测 57 → 25 才是真实页面数）。
用法：`update`（增量刷新，`--full` 强制全扫）/ `show` / `render`（渲染成事实清单「代码现状清单」段 Markdown）/ `snapshot --version <V>`（打快照）/ `delta --since <V>`（相对某版的实体级 Δ，规划期 Δ 裁剪的输入）。退出码：`0` 正常 / `1` 缓存缺失 / `2` 用法错。
实测（580 个源文件的真实项目）：首扫 0.4s、无改动增量刷新 0.12s、缓存 164KB。

## requirement_query.py — 历史需求读时查询（约定 34 清算 / 审计 H；⛔ 纯读、不落盘）

AIDP 级联恒「版本内单向向下」，约定 34 补了反向清算。它要回答两个问题，且**只有第一个需要读原文**：

- **① 本版反转的口径，以往哪些版本提过** → `search <词…> --before <V>`：现读现搜各版
  `研发需求/*.md`。**这不可能从 `98_*.json` 聚合出来**（后者只有各版自己的表 E/F）。
  ⛔ 只读上一版会把漏检固化——被推翻的结论若落在更早版本就查不到。
- **② 已经判过的跨版本作废** → `supersessions --before <V>`：聚合各版
  `研发需求/98_语义变更与需求作废.json` 的 `table_f`，那是**唯一机读信源**。
  输出的 `missing_copies` 列出缺副本的版本 —— 那些版本的判定**查不到**，⛔ 不得当成「该版无作废」。

**★ 编号格式必须容忍多种写法**——同一仓库 18 个版本实测出 4 种（`REQ-001` / `REQ-3` /
`REQ-V0.10-A02` / `F1`），只认 `REQ-` 会让一半版本索引成 0 条而输出看着完全正常（实测 50 → 184 条目）。
识别不到编号的版本显式打 `⚠️ 未识别到 REQ 条目`，调用方须回退读原文、**不得当作"该版无需求"**。

**为什么不落盘**：落盘台账会**过期而不报错**——索引只在规划期刷一次，之后累进的新 REQ 不进去；
于是审计「先查索引」查到的是一份看起来完整的空结果，比没有索引更危险。
现读现搜的代价是读 3.7MB markdown（数十毫秒量级，审计每版只跑一次），换掉这个假绿是划算的。

退出码：`0` 正常 / `1` 数据缺失（无 `docs/requirements/`）/ `2` 用法错。

## archive_old_artifacts.py — 老版本大目录留仓归档（跨版本去重 + 打包，豁免最近 N 版）

版本化产物目录只增不减：真实项目实测 `docs/prototype/` 191MB、`docs/reports/` 133MB、`.git` 265MB。它们不进 AI 上下文，但拖慢一切 glob / grep / clone / status。
**处置口径（硬边界）**：⛔ **不移出仓库**（归档产物仍在 git 里，只是从散落目录变成一个 zip）；跨版本去重（内容 sha 一致的文件只保留**最新版本**里那份，老副本删除并记明"同哪一份"）；老版本目录整体压成 `<area>/_archive/<V>.zip` 并删原目录；**豁免最近 N 个版本**（默认 5）。
**★ 同版本内不去重**：同一版本里两个文件字节相同但文件名不同是刻意的（实测 `resolution-1920x1080.png` 与 `resolution-1366x768.png` 内容恰好一致——删掉任一份就丢掉了"两种分辨率都截过图"这条事实）。
**安全设计（会删文件，默认什么都不做）**：① 默认 dry-run，必须显式 `--apply`；② 归档范围内有未提交改动即拒绝执行；③ **先打包、校验条目数与 `testzip()` 通过才删原目录**，中途失败原目录仍在；④ 每个 area 留 `_archive/00_归档说明.md` + `_manifest.json` 记来源/文件数/体积/去重明细；⑤ `restore --version <V> --apply` 可解回原位并按清单补回被去重的文件（保留副本仍在别的归档包里时**显式报出**要先 restore 哪些版本，不静默留缺口）。
用法：`plan`（默认，只读）/ `apply --apply` / `restore --version <V> --apply`；`--area`（可重复，默认 `docs/reports`、`docs/prototype`、`docs/testing`）、`--keep N`（默认 5，最小 1）、`--allow-dirty`（不建议）。退出码：`0` 正常 / `1` 前置不满足 / `2` 用法错。
实测（真实项目 dry-run）：`docs/prototype` 10 个老版本 150.7MB 里有 487 个跨版本重复文件（97.7MB）。

## notify.py — 里程碑通知发送器（构造 + 按渠道发送 + 成功才登记台账）

`/sprint-autopilot` / `/sprint-aiauto-test` 发里程碑通知的**安全通道**：
① **字段入参**（`--title`/`--section`/`--section-file`/`--link-text`/`--link-url`/`--footer`），脚本先构造一个**中性通知模型**（`schema=aidp.notify/v1`：title / color / sections / link / footer / meta），再按渠道渲染，调用方**绝不手拼 JSON**；
② 给了 `--node` 时登记里程碑通知台账：发送成功记 `sent`，失败或无可用渠道记 `undelivered`（收尾门判 DEGRADE 而非 FAIL，杜绝"发送失败仍记已发"骗过收尾门）；`--alert`（冻结 / 告警类节点）无论送达与否都追加本地告警台账 `memory/.aidp/alerts.jsonl` 并在 stderr 打印 `🚨 [AIDP-ALERT]`——无通知渠道时"停得响"靠它；
③ **标题前缀确定性兜底**：项目名称按 `--project-name` > `AIDP_PROJECT_NAME` > `memory/aidp-config.yaml` 的 `project.name_cn` > `project.name` > git 根目录名解析（恒非空），标题缺项目名称 / 缺 `--version` 版本号即就地补齐并在 stderr 提示；只解析到英文目录名时另打 `⚠️`（`--check-name` 只打印来源，英文兜底 exit 3）。
④ **渠道回落在代码里**：`--auto` 按 `memory/aidp-config.yaml` 的 `notify.channels` 依次尝试、成功即停（`notify.fallback=false` 时首个真实失败即停）：

| `type` | 发送形态 | 配置键 |
|---|---|---|
| `feishu` | 飞书自定义机器人 interactive 卡片；配了密钥则带 `timestamp`+`sign`（`timestamp+"\n"+secret` 为 key 的 HmacSHA256 → base64） | `webhook_env` / `secret_env` |
| `dingtalk` | 钉钉机器人 markdown 消息；配了密钥则 URL 追加 `&timestamp=&sign=`（HmacSHA256 → base64 → urlencode） | `webhook_env` / `secret_env` |
| `wecom` | 企业微信机器人 markdown 消息 | `webhook_env` |
| `lark-cli` | 调飞书 CLI 发到 `chat_id`；命令不存在 = 该渠道不可用（可用 `bin` / `args` 覆盖调用形态） | `chat_id` |
| `command` | 自定义命令，stdin 收中性 JSON，退出码 0 = 成功 | `command` |

⛔ webhook 地址与密钥**只经环境变量引用**（`*_env` 写变量名），不入库；仅用标准库 `urllib`。`--sender '<命令>'` = 调用方自选的自定义发送命令（stdin 收中性 JSON），与 `--auto` 互斥。
用法：`python3 {{AIDP_HOME}}/scripts/notify.py --title … --section … [--section-file F] [--link-text T --link-url U] (--auto | --sender '<发送命令>') [--node '#F' --version V --build B] [--alert] [--project-name '<项目中文名>'] [--print-only] [--json]`；`--self-check` 离线自测（本地 HTTP 桩，不发外网）。
退出码：`0`=发送成功（给了 `--node` 则已登记 `sent`）/ `1`=尝试过的渠道全部失败（给了 `--node` 则登记 `undelivered`）/ `2`=参数或构造错误 / `3`=未配置任何可用渠道（`notify.enabled=false` / `channels` 为空 / 渠道均缺环境变量或命令，合规降级）。
⛔ `1` 与 `3` **都不是"去问用户"的信号**：按 flow 语义静默跳过本播报节点、不阻塞主流程；`needs_human`/熔断信号另有 baseline + 终端强警兜底。

## autopilot-prd-watch.py — PRD 目录变化检测（`/sprint-autopilot` Phase 1 的确定性内核）

Phase 1「PRD 变化检测」的确定性程序。内联 bash 的常见失效是拿 `sha256sum` 的**文本行**哈希去比 baseline 里 `tracked_files` **JSON 串**的哈希——两种不可比的表示、永不相等，`SHOULD_RUN` 恒为 1、每 tick 空转。本脚本**两侧归一到同一 JSON 结构后比对**，并处理 PRD 目录不存在、时间戳比较、回写与判据同口径。
判定顺序：无 PRD 文件 → skip(`no-prd-files`)；无 baseline/该版本无记录 → run(`no-baseline`)；`last_commit_hash` 变 → run(`new-commit`)；`tracked_files` 归一后不等 → run(`uncommitted-change`)；其余 → skip(`no-change`)。
用法：`python3 {{AIDP_HOME}}/scripts/autopilot-prd-watch.py --version <V> [--json|--shell]` 检测（只读）；`--commit` 命中后加锁回写 `tracked_files`/`last_commit_hash`/`last_trigger_at`。

## autopilot_tick_flags.py — 两条 loop 的「本 tick 变量」解析 / 落盘 / 读回

`/sprint-autopilot` 与 `/sprint-aiauto-test` 的正文被拆成几十份 flow 分片，**每份是一次独立的 Bash 工具调用**、shell state 不跨调用持久。于是 A 分片 `WILL_BROWSER_TEST=…`、B 分片 `if [ "${WILL_BROWSER_TEST:-0}" = 1 ]` 这种写法读的那侧必然取空，`${VAR:-默认}` 静默落默认值——flag（`--skip-dev`/`--skip-deploy`/`--target` 等）没有解析落点、派生变量零赋值，游标就会永远停在某一步。
"每个分片重新赋一遍"治不了（默认路径会漂），"把派生提前"也治不了（还是跨调用）；而落盘/读回的样板代码散写进分片，既撑爆 20480B 上限又会再生同类手写错误。故收敛为本脚本：
- `parse --command autopilot|aiauto-test --arguments "$ARGUMENTS"` — 解析全部 flag，**每 tick 整段重写** `autopilot.tick`（不残留上轮裁剪 flag）
- `set --command <c> <VAR> <值>` — 落盘派生变量；**只接受已登记的变量名**，拼错即报错退 2（防的正是"写 `url`、读 `access_url`"那类事故）
- `--command <c> --shell` — 输出可 `eval` 的赋值行，分片里一行取回全部。⛔ **`--command` 不可省**（tick 键按命令分：`autopilot.tick.<command>`；省了就落回默认 `autopilot`、在 aiauto-test 侧读回恒空）；少数变量（如 `DEPLOY_MODE`）本 tick 无人落盘时从 baseline 版本节点回落
- `list` — 列出已登记变量名，供排查拼写

写操作一律 shell out 到 `baseline_edit.py`（加锁 + 原子替换），绝不自己开文件写 JSON。新增 flag / 派生变量必须同时登记进本脚本，否则等于该变量不存在——`check_flow_var_refs.py` 会把漏登记的引用报成 ERROR。

## autopilot-deploy-watch.py — 部署就绪探针 + last_deployed_at 写入（确定性、可复用，约定 31.5）

`/sprint-autopilot` 部署后的确定性就绪探针：**先 health 判 UP（⛔ 不用登录页可达性判就绪）→ 冷启动窗口内 502/503/连接拒绝属正常不判失败 → `--auth-url` 给出时要求鉴权接口连续 2 次取到非空数据 → 就绪后写 baseline `versions.{version}.last_deployed_at` 放行测试链路**。超时 / 间隔由 `autopilot_tick_flags.py` 的 `CLOUD_READY_TIMEOUT` / `CLOUD_READY_INTERVAL` 从 PRD 供给。
**单次调用有上限、跨 tick 续探**：`--max-seconds`（默认 480，短于宿主工具 10 分钟上限）到时未就绪且总超时未到 → `exit 4`（pending），下个 tick 带同一 `--since <首次探测时刻>` 续探，冷启动窗口与 `--timeout` 均从 `--since` 起算、不记失败。
用法：`python3 {{AIDP_HOME}}/scripts/autopilot-deploy-watch.py --health-url <health端点> [--auth-url <鉴权取数接口> --auth-header 'Authorization: Bearer <token>'] [--cold-start-seconds 55] [--timeout 300] [--interval N] [--since <ISO>] [--max-seconds 480] --version <V> [--no-write]`。退出码：`0`=就绪（不带 `--no-write` 时写 last_deployed_at）；`2`=总超时仍未就绪（命令端递增 `push_probe_fail_streak` 熔断，⛔ 不重跑流水线）；`3`=参数错误；`4`=本次调用到上限、下 tick 续探；`5`=**已就绪但写 `last_deployed_at` 失败**（⛔ 刻意不与 `2` 共用：`probe-timeout` 的解冻证据正是 `last_deployed_at`，按超时熔断等于把恢复路径一起堵死）。autopilot Step D 使用 `--no-write`，完成前端校验后才统一落部署证据。

## frontend_asset_probe.py — 前端产物特征探针与部署证据原子落盘

从本版 PRD `autopilot_decisions.deployment.deploy_ends.frontend.ready_asset_probe` 读首页 URL 与 `must_contain` 特征串，下载首页引用的同源 JS/CSS，逐串核对真实部署资产。前端未声明或未配置特征串时标 `skipped`（不伪造 `frontend_deploy_verified`）；应校验而资源缺失或未命中则退出 1。`--record-ready --build <BUILD> [--commit <SHA>]` 在特征校验后通过 `LockedBaseline` 同锁写入 build 级 `probe_passed/frontend_deploy_verified/probe_at` 与版本级 `last_deployed_at/phase_beta_done_at`，失败不留部分成功证据（退出 2）。无 Git 本地部署省略 `--commit`，Git 部署必须用本 build 的 push SHA 绑定。用法：`python3 {{AIDP_HOME}}/scripts/frontend_asset_probe.py --version <V> [--record-ready --build <BUILD> --commit <SHA>] [--baseline <path>]`。

## release_scope.py — 本次发布实际覆盖哪些版本（含未单独发布的过渡版本）

AIDP 允许**中间过渡版本**（做完需求/设计/开发但不单独打 tag，代码随后续版本一并发布）。发布收口若只认「本版本」，过渡版本的收口工作就**无人认领**。它是确定性可算的：**收口范围 = `(上一个已发布 tag, 本次版本]` ∩ 仓库真实存在的版本目录**。
版本目录取 `docs/requirements` / `docs/design/detail` / `docs/plans` / `memory` 四处**并集**（过渡版本可能只有需求没有设计，只看一处会漏）；版本序按**数字段 tuple** 比较，⛔ 绝不按字符串（`'V0.9' > 'V0.11'` 会翻车）。
用法：`python3 {{AIDP_HOME}}/scripts/release_scope.py --version V0.11.1 [--root .] [--json]` → `{released_version, prev_released_tag, covered_versions[], transitional_versions[], known_versions[], released_tags[], reason}`。退出码：`0`=算出结果（含"无过渡版本"这一正常结论）；`2`=版本号非法/仓库不可读。

## cicd_watch.py — CICD 推送即监听内核（约定 31.5，平台无关）

`autopilot-deploy-watch.py` 的**姊妹件**，补齐它明确不做的前半段：**① detect**（push 后按运行的 commit `== 本次 HEAD` **强绑定**查本次提交是否已起跑流水线）+ **③ poll**（按 run id **精确**轮询锚定的那次运行至终态，失败时判定"该重试第几次"）；另提供两个显式写动作 **`--mode trigger`**（主动触发一次运行）与 **`--mode retry`**（重试一次失败的运行）。
平台 = `memory/aidp-config.yaml` 的 `cicd.provider`（`github-actions` 默认 / `gitlab-ci` / `jenkins` / `command` 任意平台自定义命令 / `none`），差异全部收在 `cicd_providers.py`。
流水线取值：`--pipeline` > `cicd.pipelines[<env>]` > baseline `versions.{V}.cicd_run.pipeline` > 只配了一条时自动选中（`pipelines.<env>` 的含义随 provider：workflow 文件名 / 分支名 / Job 路径 / 命令模板里的 `{pipeline}`）。
**★ 读写分离**：`detect` / `poll` / `watch` 只读，把"该不该触发 / 该不该重试"判成 `next_action`，并在 JSON 里给出下一步命令 `trigger_cmd` / `retry_cmd`（形如 `python3 {{AIDP_HOME}}/scripts/cicd_watch.py --mode trigger|retry …`）；调用方显式再调写模式。无人值守下是否自动执行写动作受 `cicd.auto_trigger`（默认 true）控制，脚本不越权代判。trigger / retry 受理后 `next_action=poll`（已拿到 run id）或 `detect`（平台不回显 run id，需按 commit 再探测）。
穷尽判定、不留悬空态：失败→重试（配额未尽）；**平台调用失败/网络不可达** → `unreachable`，**不消耗重试配额**（取不到状态 ≠ 取到失败态）；**锚定运行消失/被顶替** → `vanished` 交人工（⛔ 绝不滑到"最近一条"顶替，那是误报部署成功的根因）；状态无法归类 → 不给绿灯、交人工。
用法：`python3 {{AIDP_HOME}}/scripts/cicd_watch.py [--mode watch|detect|poll|trigger|retry] [--commit <本次push HEAD>] (--env <dev|test|prod> | --pipeline <标识>) [--run-id <id>] [--ref <branch>] [--post-push-wait 10] [--interval 25] [--timeout 480] [--max-retries N] [--retry-count N | --version <V> --baseline <path>]`（`--max-retries` 不传读 `cicd.max_retries`，缺省 3）。输出字段含 `provider`（配置值）/ `pipeline` / `pipeline_source` / `run_commit`（运行对应的 commit，重试后 run id 为空时按它 detect 回写）。**单次调用有上限**：poll / watch 到 `--timeout`（默认 480s）仍在运行 → `verdict=running`、`next_action=poll`、rc 0，下个 tick 继续 poll 同一 run id，不交人工、不耗重试配额。
退出码：`0`=运行终态成功（`next_action=probe`，接着跑就绪探针）/ detect 命中（`poll`）/ 写动作已受理；`1`=**需调用方做写动作**（`next_action=trigger`/`retry`；`retry` 时同时输出 `run_id` / `retry_run_id` / `retry_commit` / `retry_count` / `retry_cmd`）；`2`=需人工（重试用尽/锚定消失/`trigger-failed`/`retry-failed`）；`3`=未接入或环境不满足（verdict：`disabled` provider=none / `not-configured` / `cli-missing` / `unauthenticated` / `provider-unavailable` / `bad-args`；命令端据此只 push 不监听）。`unreachable` / CLI 不可用在 autopilot 侧按 streak（3 次）才冻结，归环境类冻结、由 `autopilot_unfreeze.py --env-reprobe` 退避复探。stdout 恒一行 JSON。

★ **`4` = 降级放行就绪探针**（仅当 `cicd.push_auto_deploy` 已记录为 true）：平台给不出状态（不可达 / 运行消失 / 状态未知）或未观测到本次 commit 起跑的运行时，补等满 `cicd.push_deploy_min_wait_seconds`（缺省 300）后返回 `next_action=probe` + `degraded=true`，调用方**照 rc=0 进就绪探针、⛔ 不冻结**。它防的是一个**自锁**误冻：那类项目的流水线无法被单独触发（推送本身就是触发），于是「未起跑 → 主动触发」恒失败、「取不到状态 → 熔断」必然冻结，而解冻证据又是部署成功。⛔ 代价随 `degraded=true` 落进部署证据：未经平台确认、失败不自动重试、构建慢于等待时长时可能探到旧服务，**不得当作「确认成功」**。⛔ `failed`（取到明确失败态）与退出码 3（CLI 未装/未登录，可自动复探的 `cicd-cli-unavailable`）**都不走本通道**。开关：`aidp_state.py cicd-push-autodeploy-yes|-no`（只记事实，不改平台配置）；参数 `--push-auto-deploy auto|yes|no` / `--min-wait <秒>` 可覆盖。

## cicd_providers.py — CICD 平台适配层（约定 31.5）

`cicd_watch.py` 的底座：各平台统一暴露 `check()` / `list_runs()` / `view_run()` / `trigger()` / `retry()`，运行状态归一为 `queued|running|success|failure|cancelled|skipped|unknown`。内置 `github-actions`（`gh` CLI 已登录）、`gitlab-ci`（REST API，`cicd.gitlab-ci.url` / `project`，令牌经 `token_env`）、`jenkins`（REST API，`cicd.jenkins.url`，账号 / API Token 经 `user_env` / `token_env`）、`command`（`cicd.command.<动作>` 命令模板，占位符 `{pipeline}` `{commit}` `{run_id}` `{ref}` `{limit}`）。⛔ 令牌只经环境变量引用。接口细节以模块 docstring 为准。

### `--selftest`：证明它现在还能用

`python3 {{AIDP_HOME}}/scripts/cicd_watch.py --selftest` —— 用假平台输出离线自测（不访问网络，覆盖各提供方）：解析、状态分类、退出码 3 的各情形、未触发 / 命中 / 成功 / 触发 / 重试 / 重试用尽 / 运行消失 / 解析失败 / 含糊终态。

**为什么非要有这条**：本脚本坏掉时最危险的不是它坏了，而是**调用方会「贴心地」回落到自写轮询、
把故障吸收掉**——于是所有 poll 模式全是坏的却零信号，约定 31.5「CICD 失败的第一动作恒为重试、最多 3 次」
这条铁律在实践中退化成**靠执行体自律**。

⛔ **`parse-error` 与 `unreachable` 是两个 verdict、别合并**：前者是脚本 bug（该报修）、
后者是环境问题（该修平台凭据 / 网络），处置方向完全相反。

## release_baseline_check.py — 双轨部署基线机器门（12 项确定性校验，约定 37）

约定 37 要求发布期为每个版本同时产出**增量轨**（怎么升级）与**全量轨**（从零怎么搭）。本检查以确定性规则阻断配置占位变量碰撞、SQL 中的环境绑定物残留及相对链接失效；不同命名空间的键脱敏后仍须保持唯一，避免两个配置项意外共用同一占位值。
覆盖 12 项（含 **11. 全量核对可复核**〔00_索引.md 须写明剔除结论与导出源，二者均 ERROR 级〕与 **12. DDL 注释实查**〔委派 `check_sql_ledger_comment.py`〕）：结构完整性 / YAML 语法（`.yml` 逐文件 + `.md` 内 ```yaml 代码块逐块）/ SQL 环境绑定物残留（命中数须为 0）+ 建表幂等 / 明文凭据 / **占位变量名唯一性**（全路径命名回检）/ `${a.b}` 引用可解析 / 注释完备性（「无行内注释且上一行非注释」）/ 生效形态唯一（多形态中间件，判据绑**解析出的全路径**、不绑原始行文本——绑行文本永远匹配不到嵌套的 `redis.cluster`，本项曾因此静默空跑）/ 相对链接有效性。 / **增量极简度**（增量配置文档无 Markdown 表格、行内注释 ≤20 字符，约定 37.5-6）
**PyYAML 可选**：可用则做严格语法校验，不可用自动降级为内置结构自检（Tab 缩进 / 同层重复键）+ INFO 告知，**绝不因缺依赖而假通过**。
用法：`python3 {{AIDP_HOME}}/scripts/release_baseline_check.py --version V0.2.0 [--root .] [--json]`。退出码：`0`=无 ERROR；`1`=有 ERROR（**不得带 ERROR 发布全量基线**）；`2`=版本目录不存在/用法错。编排落点 = `/version` Step 3.3.7.9（`release-4.md`），判据单一信源 = `{{AIDP_HOME}}/reference/约定细则-5.md`。

## commit_gate.py — 约定 24 提交前门禁（确定性、可单测）

每次 `git commit` 前跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 读 JSON。作用域 = **变更事实**、与命令入口无关（裸对话路径同样适用）。总开关 = `memory/aidp-config.yaml` 的 `commit_gate.enabled`（缺省 true）。
输出字段：`commit_gate_enabled` / `is_template_project`（脚手架 skill 的任一落点——模板仓库根级 `skills/`、下游 `.claude/skills/` 或 `.agents/skills/`、历史的 `各 Agent 的运行根/skills/`——下 `SKILL.md` 与 `scripts/sync_memory_md.py` 都在、且 `scaffold_marker.py` 判为非下游）/ `working_tree_dirty` / `has_business_code_change` / `is_scaffold_only_change` / `today` /<!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->
`pending_cascade`（约定 22 四族增量册摘要 `{files,total,stale,cascaded_not_cleaned,unparsed,archived_not_deleted,destructive_unregistered,versions,…}`）/ `should_dispatch_cascade`（= `stale>0`）/ `cascaded_not_cleaned` / `suspected_cascade_bypass`（约定 22 攒批被绕过的反向判据：「当场级联」/「结构性新增零台账」两形态，`--cascade-now` 抑制）/ `pending_cicd`（约定 31.5 推送欠账：`cicd.provider != none` 时按 HEAD commit 查分类记录；正式代码推送超 1 小时无部署终态〔`deploy_terminal` / `last_deployed_at` / `probe_passed`〕计欠账，`unknown:<原因>` 终态不计欠账但可见）/ `offchain`（约定 41 链外档位 XS/S/M/L 与动作预算）/ `debts`（未落地义务代号清单）。
可 import：`pending_cascade()` / `cascade_ledger_paths()` / `CASCADE_FAMILIES` / `suspected_cascade_bypass()` / `has_business_code_change()` / `is_scaffold_only_change()` / `pending_cicd()` / `offchain_budget()` / `gather()`。
**★ 欠账告警恒打印 + 退出码说话**：未落地义务告警**不受 `--quiet` 压制**；退出码 `0`=无欠账 / `3`=有未落地义务（台账积压 · 已级联未清理 · 格式漂移 · 归档标记未删 · 🔴 破坏性变更未登记失准点 · 疑似绕过攒批 · CICD 推送欠账）/ `4`=阻塞级（保留档位：当前判据集不产生该值，消费方仍须按阻塞处理）。**Why**：约定 24 强制的写法就是 `--quiet`，提醒若住在 `if not args.quiet:` 里就等于在唯一被强制执行的路径上从不打印。⚠️ 3/4 的语义是"本轮结束前有一项义务未落地"，**不是"禁止 commit"**；逃生阀 `--no-fail-on-debt`：压退出码但**不消音**——用掉它会往告警台账 `memory/.aidp/alerts.jsonl` 落一条 `commit-gate-debt-waived`（否则「豁免过的欠账」与「真的没欠账」在任何地方都分不开）。其余参数：`--context bare-conversation|aidp-command`（留痕 + 约定 41 适用性）。

## agent_env.py — 启用的 AI Agent 与项目记忆文件落点

`detect_agents(root)`：`AIDP_AGENT` 环境变量（逗号分隔）> 根目录标记（`.codex/`→codex、`.dsh/`→dsh、`.claude/`→claude）> 缺省 `["claude"]`。  <!-- runtime-path-ignore: 指 Agent 自身目录这一概念，非运行契约路径，两包均保持原样 -->
`memory_file(root)`：只有 claude → `CLAUDE.md`；否则 `AGENTS.md`；`AGENTS.md` 存在且 `CLAUDE.md` 仅为 `@AGENTS.md` 薄壳 → `AGENTS.md`。读写项目记忆文件的脚本一律经它取路径，⛔ 不自行拼文件名。
用法：`python3 {{AIDP_HOME}}/scripts/agent_env.py detect|memory-file [--root .]`（输出 JSON）；`--self-check` 自测。

## agent_sync.py — `{{AIDP_HOME}}/` 单一信源 → 各 Agent 工具入口装配（确定性、幂等）

按 `agent_env.py` 的检测结果生成 Claude Code（`.claude/skills|commands|plugins`、`.claude/settings.json`）、Codex（公共 `.agents/skills`、官方命令根 `.codex/skills/aidp`、插件 `.codex/skills`、`.codex/hooks.json` / `config.toml`）、DeepSeek Harness（公共与插件 `.agents/skills`、`.dsh/commands`、`.dsh/hooks.json` / `mcp.json`）入口；生成入口登记进根 `.gitignore` 托管块、不入库。Codex 命令 SKILL 是**指针入口、不内联正文**：前言声明「第一动作 = Read `{{AIDP_HOME}}/commands/<命令>.md`」，正文中串联的 `/foo args` 同法读取 `{{AIDP_HOME}}/commands/foo.md`，把 `args` 原样作为 `$ARGUMENTS` 执行，未知命令 fail closed。⛔ 别改回内联：命令正文只是骨架（真正的指令在 `flows/` 分片里按需读），内联会让「脚手架升了 commands/ 与分片、agent_sync 未重跑」时 Codex 执行旧骨架 / 读新分片，Step 编号对不上。入口默认是 managed-copy 副本；兼容的 `--mode link` 也归一为 managed-copy，不再生成符号链接。改规则永远改 `{{AIDP_HOME}}/` 后重跑。同时负责项目记忆文件形态（`CLAUDE.md` / `AGENTS.md` / `@AGENTS.md` 薄壳）切换，⛔ 绝不丢弃正文。适配层配置由本脚本生成，不进脚手架 bundle 镜像。
用法：`python3 {{AIDP_HOME}}/scripts/agent_sync.py [--agents claude,codex,dsh] [--mode copy] [--check] [--human]`；`--self-check` 自测。退出码：`0`=已一致/已写入；`1`=`--check` 发现漂移；`2`=参数、环境或用户自有目标冲突。

## agent_loop.sh — 非交互唤起 AIDP 命令

`--once <命令> [参数…]` 单次执行（供操作系统调度调用）；`<间隔> <命令> [参数…]` 前台循环（临时使用）。每轮自动补齐 `--unattended --no-loop`、export `AIDP_TICK_COMMAND`（Stop 护栏据此识别 autopilot tick）与 `ARGUMENTS`（原样作为命令参数）、加载可选的 `~/.config/aidp/env` 凭据、flock 互斥（上一轮未结束则跳过）、日志追加到 `memory/.aidp/logs/<命令>.log`。
**tick 硬超时**：`AIDP_TICK_MAX_SECONDS`（默认 7200，`0` = 关闭）给每轮 tick 套 `timeout`；超时按 rc `124/137` 记日志并打 `🚨 [AIDP-ALERT]`。⛔ 裸 `eval` 没有上限时，挂死的 tick 会永久持锁、让整条链路静默停摆。`timeout` 命令不可用时退回裸 `eval` 并告警。

Agent：`AIDP_AGENT` > `memory/aidp-config.yaml` 的 `scheduler.agent`（`auto` 取 `agent_env.py detect` 第一个）；执行模板（`{prompt}` 占位）：`AIDP_AGENT_EXEC` > `scheduler.exec.<agent>` > 内置默认（Claude Code `claude -p --permission-mode acceptEdits {prompt}`、Codex `codex exec --sandbox workspace-write {prompt}`；DeepSeek Harness 无内置默认、须配置，写法以所用版本官方文档为准）。

## aidp_scheduler.py — 7×24 操作系统调度装配（开发链路 + 测试链路 + 独立 watchdog）

7×24 的运行载体：为**开发链路**（`sprint-autopilot`）与**测试链路**（`sprint-aiauto-test`）各装一个用户级定时任务，分别调用 `agent_loop.sh --once <命令> --unattended`；第三条独立 watchdog 任务默认每 5 分钟巡检，即使两条链路都从未启动也可在宽限期后告警。平台自动选择：Linux `systemd --user` timer（无 systemd 时 crontab）、macOS launchd、Windows 输出 `schtasks` 命令供手工执行。
`watchdog --scheduled` 做独立心跳巡检：首次无心跳超过宽限期，或已有心跳超过 `scheduler.stale_cycles × 周期` → 写本地告警台账 `memory/.aidp/alerts.jsonl` 并经 `notify.py --alert` 播报。另判 **`hung`（挂死）**：链路已 stale 但互斥锁仍被持有、且持锁时长超过 `max(stale 阈值, scheduler.tick_max_seconds, 1h)` → 写 `loop-tick-hung` 告警。⛔ 这一档必须有：Agent 进程挂死时锁被永久持有，之后每次调度都被 `agent_loop.sh` 的 `flock -n` 跳过，而 watchdog 只按「持锁 = 正在跑」判 `running` —— 于是永不 stale、零告警、整条链路静默停摆（tick 内部的 stuck 熔断救不了：tick 根本没开始）。手动调用不对尚无心跳的链路倒计时；会话内 `/loop` 仅适合交互式短期使用。
用法：`python3 {{AIDP_HOME}}/scripts/aidp_scheduler.py install|uninstall|status|watchdog [--agent auto|claude|codex|dsh] [--dev-interval 10m] [--test-interval 5m] [--platform systemd|cron|launchd|schtasks] [--dry-run] [--json]`；`--self-check` 离线自测（临时目录渲染三条任务）。配置段 = `memory/aidp-config.yaml` 的 `scheduler`（`aidp_config.scheduler_config()`）。

## aidp_state.py — 项目级运行时状态（baseline 的 `project_state` 段）

把项目级**程序写的**运行时记录集中到 `memory/.sprint-autopilot-baseline.json` 的 `project_state` 段（团队共享、随 git 提交），顶层按命名段组织，可持续追加。⚠️ **人维护的开关不在这里**——提交前门禁 / 里程碑通知 / Stop 护栏开关与脚手架版本戳住 `memory/aidp-config.yaml`（`aidp_config.py`），本脚本的开关子命令只是对它的读写入口。二分判据 = **谁写的**，见 `aidp_paths.REGISTRY`。
用法：`python3 {{AIDP_HOME}}/scripts/aidp_state.py [--repo-root .] {get <点分键>|set <点分键> <值>|commit-gate-enabled|commit-gate-enable|commit-gate-disable|notify-enabled|notify-enable|notify-disable}`（**共 8 个子命令，与源码 `add_parser` 一一对应**）。

## baseline_edit.py — autopilot baseline 的加锁读改写编辑器（并发安全的唯一写入口）

`memory/.sprint-autopilot-baseline.json` 被**两条 `/loop` 并发写**（开发链路 `/sprint-autopilot` 写 run_state / 部署 / build / 决策字段，测试链路 `/sprint-aiauto-test` 写心跳 / 测试结果 / 冻结字段）。`jq '…' f > tmp && mv tmp f` 式的裸读改写**只原子、不加锁**，长 tick 交叉即丢更新（典型形态：aiauto-test 刚写的 `ai_report_finalized` 被 autopilot 的 run_state 整体回写覆盖，导致重复 finalize / 收尾门判据错乱）。本脚本把 `emit-report.py::record_baseline` 已验证的范式（flock + **锁内重读** + `os.replace`）抽成通用工具，所有写点共用同一把锁。
**铁律：flow / 命令端一律经本脚本写 baseline，不写裸 `jq … > tmp && mv`**（只读 `jq -r` 查询不受限）。路径用点号分段、**含点的键必须加双引号**（`versions."V0.1.0".needs_human`），`--version V0.1.0` 会给后续相对路径自动加 `versions."V0.1.0".` 前缀。
子命令：`get` / `set`（可多组 path/value）/ `del` / `bump [--by N]` / `touch`（写当前 ISO8601）/ `now` / `current-version`（解析「当前开发版本」，两条 loop 共用的单一信源）/ `run-state`（Phase 游标：`current_phase` / `next_phase` / `next_sprint` / `phase_summary` / `pending_actions` / `phase_enter_count` / `phase_first_entered_at` 的**唯一**维护者，⛔ 别在别处 bump `phase_enter_count`）。

## autopilot_stuck_check.py — 通用 stuck 熔断（"既不失败也不推进"的兜底）

autopilot 现有熔断（`dev_fail_streak` / `probe_fail_streak` / `test_loop_missing_streak` / `report_gate_fail_streak`）**全要求先有一次明确失败**才计数，堵不住真实卡死里最常见的一类——**没有失败**：子 Agent 每 tick 回传 partial、某 Sprint 永远 close 不掉、`pending_actions` 每 tick 都补不完。表现是 `/loop` 岁月静好地空转、零告警、build 永不收口。
判据**两条同时满足**才熔断（缺一都会误伤）：① `run_state.phase_enter_count ≥ 8`（`--enter-threshold`）② `phase_first_entered_at` 距今 > 2 小时（`--age-seconds`）。只看次数会误伤"逐 tick 单 Sprint"（`3.2-dev` 本就每 tick 重入），只看时长会误伤长 Sprint。
**只读判定**：`phase_enter_count` 的唯一维护者是各 Phase 出口的 `baseline_edit.py run-state`，本脚本绝不 bump（多加一次 = 阈值提前一半到达）。冻结按「冻结字段写入契约」经 `baseline_edit.py` 写齐四件，`freeze_reason=stuck-phase` 属交接类（解冻 = 人工）。
用法：`python3 {{AIDP_HOME}}/scripts/autopilot_stuck_check.py --version <V> [--dry-run] [--no-card] [--json]`。**退出码**：`0`=未 stuck/不适用 · `1`=已判 stuck、已冻结、**#4 已由本脚本自己发出**（调用方让位本 tick 即可）· `2`=入参错 · `3`=判定 stuck 但**冻结字段写盘失败**（#4 仍已发）——⛔ 调用方不得当 1 处理：盘上没冻，下 tick 判据未变、`already-frozen` 早退不生效 ⇒ 无限重冻循环。**★ 发 #4 通知归本脚本自己**（⛔ 不交给调用方：调用方少写一行，净效果就从「静默空转」换成「静默永冻」，而 `stuck-phase` 属人工专属、没有任何探针能自动解冻；解冻用 `autopilot_unfreeze.py --manual <V>`）；`--no-card` 仅供自检/演练，正常链路不要传。调用点 = `flows/sprint-autopilot/phase-1.md` 1.3ter（按 `1/2/3` 三路分流），无条件先于续跑短路门跑一次。

## check_md_anchors.py — Markdown 站内锚点死链（确定性）

全仓扫 `.md` 的**站内锚点链接**（`[文案](#锚点)` 与 `[文案](./x.md#锚点)`），按 GitHub slugify 规则（小写 → 去掉非 `\w`/空格/连字符（**中文保留**）→ 空格转连字符（不折叠，故 ` + ` 会产出 `--`）→ 同名标题追加 `-1`）计算每个标题的真实锚点，比对后报死链。围栏代码块内的 `#` 行不当标题、也不收集其中的链接。
需要豁免的段落（如"教别人怎么写锚点"的示例）用 `<!-- anchor-check: ignore-file -->` 整份文件豁免，或 `<!-- anchor-check: ignore-begin -->` … `<!-- anchor-check: ignore-end -->` 包住——豁免块内**不收集链接但仍登记标题**。
用法：`python3 {{AIDP_HOME}}/scripts/check_md_anchors.py`（退出码 `0`=全通过 / `1`=有死链 / `2`=用法错）。由 `verify.py` 调用，`tests/test_guard_scripts.py` 有专门用例。

## check_convention_dup.py — 核心约定「主行双写」护栏（确定性）

核心约定二分落点的守卫：**决策要点主行**只许在**主行文件**「核心约定」段（常驻上下文、唯一权威），`{{AIDP_HOME}}/reference/约定细则-N.md` 只放该条的**子项 / Why / 示例**。分片一旦原样复制主行就形成双写——两处各自演进悄悄漂移、"见约定 N"以哪份为准全靠猜（典型：同一约定两处文本已不同）。脚本从主行取**首句探针**（切到首个句末标点、不足 40 字符则续取），与各细则分片**归一化**（去 `*`、折叠空白）后子串匹配；`### 约定 N — …` 小节标题行**排除**在扫描面外（标题是分片的自解释锚点、取自主行粗体标题，属保留项）。
★ **主行文件按形态探测**：先取「核心约定」正文所在的项目记忆文件（`AGENTS.md`，Claude Code 单独使用时为 `CLAUDE.md`；`CLAUDE.md` 仅为 `@AGENTS.md` 薄壳时取 `AGENTS.md`）。写死单一文件名会让另一形态的项目 **100% SKIP、exit 0**——那是假通过而非不适用。
另报**主行超长**（> 600 字符，JSON `overlong[]`，WARN、不进退出码）：主行只留决策要点 + 详规指针，Why / 实证 / 回检细节放细则分片或 `rules/*.md`。
用法：`python3 {{AIDP_HOME}}/scripts/check_convention_dup.py [--root <仓库根>] [--json]`。退出码：`0`=无重复（或不适用）/ `1`=检出重复 / `2`=用法或读取错误。JSON 带 `skip_kind` 区分跳过原因（`not-aidp` / `no-conventions` / `no-detail-fragments`）。
**执行链入口** = `verify.py::check_convention_main_line_dup`（三模式末尾 + `aidp-compliance` Agent 都会跑到）；`no-conventions` 报 WARN、其余跳过报 INFO 并说明原因。

## check_version_identifier.py — 「发布版本 ↔ 代码内自报版本」对齐护栏（确定性）

发布期唯一能兜住"tag 打了 v0.3.0，但 `/health` 仍返回 `version: 0.2.0`"的环节（实际项目中真实发生过）。扫四类落点——**代码常量**（`*_VERSION` 赋 semver 字面量）/ **构建描述符**（`pom.xml` 自身 `<version>`、`build.gradle(.kts)`、`package.json`、`Cargo.toml`、`pyproject.toml`）/ **运行时配置**（`application.y(a)ml` 的 `info.app.version` 等）/ **容器镜像**（`Dockerfile`·`Containerfile` 的 `LABEL version`、`ARG`/`ENV APP_VERSION`、`COPY`/`ADD` 产物名内嵌版本如 `app-0.2.0.jar`），归一化（去前导 `V`、去 `-SNAPSHOT`）后与发布版本比对。
降噪三条：`0.0.0`/`${...}`/`@..@` 记占位豁免；`*_FORMAT_VERSION`/`API_VERSION`/`JAVA_VERSION` 等**协议/依赖/工具链**版本走 deny-list（**后缀匹配**，`CURRENT_FORMAT_VERSION` 同样排除）；`pom.xml` 只取自身直接子 `<version>`（只有 `<parent>` 的继承模块不算落点）。
★ **第三方代码排除**（有了 `--apply` 后，这条从"降噪"升级为"防破坏"——写回第三方库就是改坏别人的代码）：① 对象属性赋值 `a.VERSION="3.4.1"` 不算落点（第三方 JS 库写法，`\b` 拦不住点号）；② `*.min.js`/`*.bundle.js` 等压缩产物整文件跳过；③ `bower_components`/`third_party`/`site-packages`/`jspm_packages` 等落地目录不下钻；④ **vendored 进来的整个第三方工程**（连 `pom.xml` 一起拷进来，和自家子模块长得一模一样、猜不准）由项目在仓库根 `.aidp-version-ignore` 逐条声明（每行一 glob，`#` 注释），或 `--exclude <glob>` 临时传。真实回流：本仓 `adminlte/bootstrap.min.js` 误报 11 处 + `xxl-job/pom.xml`（第三方 3.1.0）被当自家模块。
★ **Dockerfile 只认白名单**：容器文件里基础镜像/工具链/组件版本满天飞（`FROM …jre-noble:17.0.20_8`、`ARG BASE_IMAGE=…`、`ARG NGINX_VERSION=1.21.6`、`ENV JAVA_VERSION 17.0.2`、`LABEL java.version`），宽匹配写回 = **拉错基础镜像 / 构建直接失败**。故 `LABEL` 键与 `ARG`/`ENV` 名各走白名单、`FROM` 行永不产生落点、通配 `app-*.jar` 天然不匹配（那种写法本就自适应）。裸 `ARG VERSION=` 更常指被装组件版本 → 算落点照常报告但归 `runtime-config` **需人复核档**，不进默认自动改档。反过来 `COPY app-<版本>.jar` **必须**跟着 pom 改，否则镜像构建找不到文件。
**同时是写回器（`--apply`）**：只检查不改 = 每次 bump 版本号都要人手动去改 `pom.xml`/`package.json`，漏改就是上面那个 `/health` 误判。`--apply` 把不一致落点改成目标版本，三条硬保证——① **保后缀 / 剥前缀**（只换 semver 主体；`-SNAPSHOT`/`-RELEASE` 后缀原样留，`0.2.0-SNAPSHOT`→`0.3.0-SNAPSHOT`；**`V`/`v` 前缀一律剥掉**，`V0.11.2`→`0.12.0`——匹配兼容 `V0.11.2`/`v0.11.2`/`0.11.2` 三形态，写回统一归一到纯 semver，因为前缀是 AIDP 文档/git tag 的写法，Maven·npm·Cargo·OCI 标签带 `V` 不规范甚至非法）；② **不重排文件**（全走文本级定点替换，不用 `ET.write`/`json.dumps` 回写，注释缩进键序全不动）；③ **Maven 反应堆连带同步**——改父 pom 自身 `<version>` 后，同步其反应堆内子模块的 `<parent><version>`（只改 `<parent>` span 内、不误伤 `<dependency>`），否则父子版本错位、`mvn` 直接解析不到父 POM，比不改更糟。写回后**强制重扫复验**，以重扫结果定退出码。
`--apply-scope` 两档：`build-descriptor`（默认安全档，仅构建描述符——那就是制品版本本身，纯机械零业务语义）/ `all`（再加代码常量 + `application.y(a)ml`，这两类**可能被业务逻辑读取**，需人复核故不进默认档）。scope 外的不一致记 `skipped_out_of_scope[]` 照常报告，绝不静默吞。
用法：`python3 {{AIDP_HOME}}/scripts/check_version_identifier.py --version V0.3.0 [--root <仓库根>] [--path code] [--json] [--apply] [--apply-scope build-descriptor|all] [--exclude <glob>]`。退出码：`0`=对齐或无落点（`--apply` 下含"本次已改齐"）/ `1`=仍有不一致 / `2`=用法错误。
**执行链两个入口**：① **规划期** `/version` Step 2.7.3（`flows/version/planning-8.md`）—— 版本号 bump 的落点是"文档 + 代码"两侧，Step 2.7 改完文档侧，本步带 `--apply` **自动改齐代码侧构建描述符**；② **发布期** `/version` Step 3.3.13（`flows/version/release-7.md`，打 tag 前最后一道）—— 正常应检出 0 处，作**复核兜底**接住规划后被合并改回 / 开发期手改错 / scope 外残留。⚠️ **退出码 1 不阻断发布**：交互式让用户三选一（选"自动改"即调本脚本 `--apply --apply-scope all`，**不要手工逐处改**——手改极易漏掉后缀保留与反应堆同步），无人值守 WARN + 自动登记 `docs/audit/{version}/发布欠账.md`（**发布期不自动改代码常量**）。

## check_sprint_numbering.py — Sprint 编号跨版本连续性 + 划分粒度（确定性）

两条规则若只隐含在示例里、没有机器回检，下游就会各按各的理解落地（两类典型问题）：
① **编号被重置**——若取号扫的是 `memory/{version}/{user}/sprints/` + `docs/plans/{version}/…`，**两个路径都带 `{version}` 限定**，新版本目录天然为空 → MAX=0 → 新版本又从 `sprint-001` 起。于是同一项目里多个 `sprint-001`，bugfix 记录 / `testing/{version}/sprint-{NNN}/` 全部无法只凭编号定位。
② **前后端被拆成两个 Sprint**——`dev-execution-planner` 按「**EPIC × Sprint × Task** 三层模型」产出（`SKILL.md` 第二步 + `references/flow-execution.md`：Sprint 是时间盒，一个 Sprint 可含多个 EPIC、一个 EPIC 也可跨 Sprint），「同一功能的前后端不得拆到两个 Sprint」须单独判；拆开后任一 Sprint 都无法独立验收（前端 Sprint 无接口可联调、后端 Sprint 无页面可验证），Sprint 退化成"任务批次"。
判据：**A1 跨版本重复 / A2 版本内重复 / B1 同一功能模块跨 Sprint = Critical**；**B2 单端 Sprint = Important**（豁免 = 该行标注「单端/仅前端/仅后端/纯前端/纯后端」，与 `dev-execution-planner` 的 `check_task_granularity.py` 同款词表）；**A3 断号 = Info 只报不拦**（Sprint 取消/合并属正常，重复才是错）。矩阵列位置按表头**动态定位**、不写死列序（下游增删列不会静默错位）。
用法：`python3 {{AIDP_HOME}}/scripts/check_sprint_numbering.py next|check [--root <仓库根>] [--json]`。`next` = **跨全部版本**扫 MAX+1 取号（`/sprint-dev`·`/sprint-full`·`/sprint-plan`·`/sprint-bugfix` 一律用它，**严禁**自己 glob 当前版本目录）；`check` 退出码 `0`=过 / `1`=检出 / `2`=用法错，由 `verify.py::check_sprint_convention` 映射为 ERROR/WARN。模板项目与尚无 Sprint 的新项目自动 SKIP。

## check_tick_var_supply.py — tick 变量「登记了但没有供给链」巡检（确定性）

一次审计抓出 **16 个**同形状缺陷。**★ 另有二级校验**：一级只问「变量名在不在回落表里」，答"在"即放行、**从不追问那个 baseline 键有没有人写**——于是「回落链指向一个无人写的键」这类缺陷能在全绿之下长期存活（实测：`deployment_mode` 全仓无写入者、`autopilot_entry_mode` 在 test-only 路径无写入者）。二级校验对 `BASELINE_FALLBACK` 的每个 `(scope,key)` 反查写入者，缺失且无 `DYNAMIC_FALLBACK` 兜底即报 WARN。`autopilot_tick_flags.py` 的 `DERIVED_VARS` 只是**声明变量存在**，不等于它会被写入：若全仓无 `autopilot_tick_flags.py set <NAME>` 落点、又不在 `BASELINE_FALLBACK`/`DERIVED_FROM`/`FALLBACK_DEFAULT` 里，`--shell` 对它**恒输出空串**，消费方 `${VAR:-默认}` / `[ "$VAR" = "x" ]` 于是**判据恒取默认、恒为假且零报错**。实测后果：`ENTRY_MODE` 恒空 → test-only 分支不可达 + 收尾门恒按 full 拼期望卡集 → 3 tick 冻结；`NEXT_SPRINT_NO` 恒空 → 首个 Sprint 关闭后即写 `next_sprint=done`、**剩余 Sprint 被静默丢弃**。
**为什么 `check_flow_var_refs.py --strict` 抓不到**：它有一行 `if TICK_EVAL_RE.search(text): file_allow |= tickvars` —— 把「文件里出现 `--shell` eval」当成「这个变量取得到值」的证明，而 eval 只对有供给链的变量返回真值。本脚本补的正是这一格：不看有没有 eval，只看**到底有没有人写**。
判据：无供给 + 有消费 → ERROR；无供给 + 无消费 → WARN（死登记）；豁免 = 登记行加 `# supply-check: ignore <原因>`。
用法：`python3 {{AIDP_HOME}}/scripts/check_tick_var_supply.py [--root <仓库根>] [--json]`，退出码 `0`/`1`/`2`；由 `verify.py::check_tick_var_supply` 映射为 **ERROR 硬门**（存量已全部补齐，`findings=0`；⛔ 这里不写 `declared` 的具体数字——它随登记变量增减而变，写死必腐烂）。

## check_step_index_coverage.py — 命令骨架表 ↔ flow 分片 Step 编号覆盖（确定性）

大命令的正文外置成 `flows/<cmd>/*.md` 多片后，命令主体只留一张**骨架索引表**，并要求「按 Step 进度依次 Read 对应分片」——于是这张表成了执行体**唯一的"该跑哪些步"清单**：**不在表里的 Step 没有任何理由被执行，哪怕分片里写得再完整**。真实事故：新增的 `Step 2.7.4`（收口上一版本变更台账）与 `Step 3.3.9.5`（发布前收口，还标着"必须先于 3.3.10"）都在分片里定义好了、**却都没进骨架表** → 三个收口点里的两个定义了但永不执行；`--finalize-docs` 的清单里 3.3.9.5 两头都不在、补跑也无路径。人工每次改 flow 都要回头对表，必漏。
判据刻意收窄到**「同级兄弟已被逐个列举、却漏掉其中一个」**：表里有 `2.7 / 2.7.3 / 2.7.5` 说明这一层按子步登记，此时分片里的 `2.7.4` 缺席 = 遗漏；而表里只有 `2.7`、分片有 `2.7.1~2.7.9` = 按父级粒度登记，不算。要求该父级下**表内已有 ≥2 个子步**才判定（1 个不足以说明是列举模式）。识别**区间记法** `**2.4.1–2.4.3.5**`（区间内视为已覆盖）与 `**0.2**（子步骤 1–4）` 这类带后缀说明的登记。⛔ **不做反向检查**（表有·分片无）——骨架表登记的 Step 未必外置（部分由命令主体内联承载），实测该方向绝大多数是误报；断链方向由 `check_md_anchors.py` 覆盖。调参过程：85 → 30 → 7 → **0 误报**，同时构造场景仍精确命中。
用法：`python3 {{AIDP_HOME}}/scripts/check_step_index_coverage.py [--root <仓库根>] [--json]`，退出码 `0`/`1`/`2`；由 `verify.py::check_step_index_coverage` 映射为 **ERROR**。豁免：标题行 `<!-- stepindex-check: ignore -->` / 整文件 `ignore-file`。

## check_cross_file_dup.py — 跨文件长片段逐字重复（双写漂移守卫，确定性）

「单一信源」是本范式的核心纪律，但纪律靠人守就会失效：一次审计找出 6 组跨文件双写（最大 636 字符逐字相同），而**每组两侧都白纸黑字写着「单一信源在别处、本处不复述（约定 21）」**——写的人真心以为自己没复述。双写的代价不是多占几行、是**漂移**：改了一处、另一处留在旧口径，且两处都声称权威（典型：某个判据的实现改了、5 处文档还说老规矩）。既有 `check_convention_dup.py` 只比对**约定主行整句**，对「改写型复制」与「分片内部互抄」无能为力——它报「38 条主行无一被复制」时，那 6 组正躺在仓库里。
判据：`{{AIDP_HOME}}/{commands,agents,flows,reference,rules}` + `docs/init` 的 `.md` 归一化（去 markdown 标记/折叠空白/去列表符号）后按句切分，**同一片段出现在 ≥2 个文件**：≥150 字符 = ERROR，≥80 字符 = WARN。只比跨文件（同文件内重复多是模板正常重复）。豁免 `<!-- dup-check: ignore <理由> -->`（作用域到**空行或代码块围栏**为止——只豁免一行不够，自包含 bash 块跨多行）/ 整文件 `ignore-file`。
用法：`python3 {{AIDP_HOME}}/scripts/check_cross_file_dup.py [--root <仓库根>] [--json] [--error-len 150] [--warn-len 80]`，退出码 `0`/`1`/`2`；由 `verify.py::check_cross_file_dup` 映射为 **ERROR**（仅 ERROR 级；WARN 级短重复不阻塞）。

## check_singlesource_pointer.py — 「单一信源」指针有效性 + 不分裂（确定性）

「单一信源」是本范式核心纪律，文档里散落着大量 `单一信源 = X` / `详规见 X` / `本处不复述` 断言。两种失效都很隐蔽：① **指针失效**（`X` 已改名/删除/移位——典型：指「见 version.md Step 2.4.4」，而 2.4.4 已外置到 `planning-4.md`，指针指向了另一个指针）；② **指针分裂**（同一规则声明了两个不同的"单一信源"，此时这个词本身就是谎言，改动必漏一处）。
判据：只校验**契约文件路径**（`{{AIDP_HOME}}/` 或 `docs/init/` 下、带目录）。函数级指针 `脚本.py::符号` 由 `check_code_symbol_refs.py` 校验。⛔ 刻意不校验裸文件名与非契约路径——不收窄的话 178 处命中全是误报，三类都不该报：运行时文件（`.mcp.json`/`config.json`，由命令生成）、迭代产物（`00_索引.md`，落在 `docs/{version}/`）、省略泛指写法（`（+ -2.md）`/`phase-0-N.md`）。另排除运行时凭据（`config.json`/`auth.*.json`/`.env`——按 example 自建且已 gitignore，"不存在"是设计而非断链）。分裂检测只判 **WARN**：主题键靠文本提取、可能把两条不同规则误并成一个键。
用法：`python3 {{AIDP_HOME}}/scripts/check_singlesource_pointer.py [--root <仓库根>] [--json]`，退出码 `0`/`1`/`2`；由 `verify.py::check_singlesource_pointer` 映射为 **ERROR**（仅失效指针；分裂 WARN 不阻塞）。豁免 `<!-- ssp-check: ignore <理由> -->` / `ignore-file`。

## check_webmcp.py — 前端 WebMCP 的启用判定 + 脚手架侧装配守卫（★ 未启用即整体 N/A）

**第一职责是「启用判定的单一实现」**：WebMCP 是**可选**能力（详规 `{{AIDP_HOME}}/rules/webmcp.md`），横跨 rules / agents / flows / verify 五六个落点，每个落点都要回答「本项目启用了吗」。各处各自 grep PRD 必然判据漂移，且**一处判错就给未启用项目凭空长出告警和产物位**、直接违反「默认关闭」总原则。故 `--detect` 是该判定的唯一实现，其余落点一律调它。声明位置按序：① PRD `autopilot_decisions.webmcp.enabled: true`（**可选段，不计入必填 8 段；段不存在 = 未启用**）② `docs/architecture/架构约束.md` 显式声明。
**第二职责是「按需安装详规」**：`--install-rule` 把 `{{AIDP_HOME}}/templates/optional-rules/webmcp.md` 幂等装到 `{{AIDP_HOME}}/rules/webmcp.md`（未启用时**拒绝安装**，`--force` 可强装）。⚠️ **详规默认不在 `rules/` 下是刻意的**——`rules/*.md` 是**路径触发**加载的，常驻会让绝大多数不启用该能力的项目每次编辑前端代码白读十几 KB。配套四条保证见 `{{AIDP_HOME}}/rules/README.md`「按需安装的可选规则」段（漏装硬拦 / **随升级自动刷新** / 升级不删 / 不误报孤儿）；其中"刷新"由 `scaffold.py::refresh_optional_rules` 承担——安装位**不在 bundle 下发面里**，两条同步路径都碰不到它，不专门处理就永久停在安装那天的版本。
★ **职责边界（别把代码合规检查加回来）**：WebMCP 检查分两处、判据不重叠——**代码实现合规**（单一适配层 / `unregisterTool` / 错误契约死文案 / 写操作绕通道 / 敏感值外泄 / 白名单）归上游 `code-verification-loop` **维度 9** + 其 `scripts/check_webmcp_adapter.py`；**脚手架侧装配**归本脚本。前两项曾在本脚本实现过，上游落地后已**移交**（同一判据两份实现 = 改一处漏一处、两处都自称权威，是本仓最高频漂移源；`check_di_resolvability.py` 有同样先例）。`test_guard_scripts.py` 有一条防回归断言盯着这件事。
未启用 → `applicable:false` + 退出码 `0` + **零 finding**，`verify.py` 侧连 `note()` 都不发。启用后跑三项守卫：① **详规已安装**（ERROR — `rules/*.md` 是路径触发加载的，不在那儿就永不加载 = 规则等于不存在）② **详规未过期**（WARN — 与模板位不一致，即自动刷新没跑到或副本被本地改过）③ **「测试环境与账号」已回写 WebMCP 段**（ERROR，**只判最新版本**不连坐旧版；下游踩过：用例三处指向该文档、文档里从未写，文件在锚点空、链接检查查不出来）。
用法：`python3 {{AIDP_HOME}}/scripts/check_webmcp.py [--root <仓库根>] [--detect] [--install-rule] [--force] [--json]`，退出码 `0`（通过或 N/A）/`1`/`2`；由 `verify.py::check_webmcp` 映射为 **ERROR**（仅启用时）。★ 命令端据 `--detect` 的输出把 `webmcp_enabled` / `webmcp_entry_symbols` 传给四个上游 SKILL（`dev-logic-architect` 维度 33 / `dev-manual-testcase` 用例族 + 维度 20 / `code-verification-loop` 维度 9 / `auto-test-runner` `invoke` 能力）——它们**全部入参门控且明令不自行探测**，⛔ **不传 = 那些维度永不启用**，启用了该能力的项目会静默漏掉四层质量门。

## check_client_mcp.py — 「客户端 MCP 能力暴露」的跨端声明判定【唯一实现】

★ **先分清两条轴，混了必错**：**应用能力** = 被测应用**自己**向 AI 暴露业务工具（带 Schema、权限、审计）—— 本脚本管的就是它；**测试驱动** = AI 用 chrome-devtools / Appium / 小程序驱动去**操控**客户端 —— ⛔ 本脚本**一个字节的驱动信息都不读**。两者用的都是 MCP 协议，但「AI 能操控客户端」与「这个应用提供了业务工具」毫无关系，读了就会把前者当后者的证据，把整个功能点判成假绿。

「客户端 MCP 能力」是**跨端**功能点（Web / 小程序 / 移动 / 桌面），**WebMCP 只是它的 Web 端实现**（`client_type=web` + `implementation_kind=webmcp`）。存量 Web 项目的 `webmcp_declared` / `webmcp_entry_available` / `requires_webmcp` 继续作为别名接收。

用法：`python3 {{AIDP_HOME}}/scripts/check_client_mcp.py [--root .] [--json] [--self-check]`；可选规则模板位 `{{AIDP_HOME}}/templates/optional-rules/client-mcp.md` → 安装位 `{{AIDP_HOME}}/rules/client-mcp.md`（已登记进 `scaffold_lib.py::OPTIONAL_RULES`，随升级自动刷新、也不会被误报孤儿）。

## aiauto_readiness.py — 客户端用例的前置状态（⛔ 绝不产 pass）

消费**运行期取证**，输出 `ready / block / unverified`；⛔ 不自行探测、不读驱动信息、不执行登录、不读凭据。四态与 `auto-test-runner/references/driver-client-mcp.md` 一一对应（⛔ 别在两处各立一套）：`declared ↔ client_mcp_declared`、`entry ↔ client_mcp_entry_available`、`registration ↔ registered_tools`、`invocation ↔ invoked_tools + invocation_evidence`。声明缺失时该类专项用例一律 block（`block_reason=precondition-unmet`），⛔ **测试驱动可用不是应用提供 MCP 能力的证据**，故 `driver_*` 一类事实**根本不参与判定**。

## 规划计量与预检（`/version` Step 2.3.9 / 2.4.6.5 配套，⛔ 都不参与质量判定）

- **`aidp_run_metrics.py`** — `--root <仓库根> --version V --run-id ID start|end|wait|summary`。阶段计时与等待区间独立存 `docs/audit/{V}/metrics-{ID}.json`。`unclassified_seconds` 只是**墙钟扣除已记录等待的余额**，⛔ 不等于模型工作时间；`model_work_seconds` 只有拿到可靠独立计时才显式传入，否则为 `null`；用量取不到记 `null`，⛔ **不用文件篇幅推算 token**（推算值看起来像计量、实则是捏造的证据）。指标记录失败只告警，⛔ 不改变任何质量门结论。
- **`version_fact_snapshot.py`** — `--root <仓库根> --version V create --file <来源相对路径>` 生成来源 SHA 清单（来源含 `code-inventory.json` 时逐个核对其列出的源码 SHA）；`verify` 检出源文件变化。⛔ 过期即重读刷新，**不得把「缺失或过期的快照」当成「无变化」**；清单只是来源哈希引用，不代替源码 / PRD 正文。条目形状不符或缺 `sha` 时 fail closed 并给出明确原因（⛔ 不放行、也不抛 traceback）。
- **`version_preflight.py`** — `--input <已运行检查器结果清单.json> --json` 合并来源、最高严重度与定位。输入为数组，每项 `{source, executed, exit_code, output_present, scanned_files?, skipped?, findings:[{check_id,file,anchor?,severity}]}`。⛔ `executed=false`、空输出、`scanned_files=0`、`skipped=true` 或异常退出码**一律不得判 pass**；⛔ 不重写任何检查器的判据，也**不替代** `version-auditor` 的八项独立审计。

## check_sibling_family.py — 约定 20 姊妹条「同族增量项」确定性检查（F0–F4）

向**已有 ≥2 个同构成员**的家族（运维入口 / 菜单项 / 版本区块 / 增量脚本 / 索引条目 / 枚举项 / 页签…）追加成员时，拦「没有公共外壳、各抄一份」与「顺序靠物理位置 + 注释提醒」。**判据是「有没有兄弟」，不是「我写了几遍」**——约定 20 的阈值判据（第 2/3 次即抽）在这类场景下不触发：执行体主观上是在复用家族里已有的东西。失败形态是"看起来正常"（类型检查/lint/构建全绿，只有并排比对才看得见），故必须有机器门。

★ **家族必须显式声明**（`SIBLING-FAMILY: name=… members=<glob> registry=… [shell=…] [order=registry]`，只在 `code/` 与 `docs/` 下扫描），⛔ **刻意不做自动家族识别**：按「同目录 ≥3 个同命名模板」自动识别会命中本仓库自己的 `flows/sprint-autopilot/phase-3-*.md`、`reference/约定细则-*.md`、下游 `sql/NN_*.sql` —— 而它们的顺序**本就该由文件名序号决定、也不该有注册表**，对其恒红会让下游直接关掉整个脚本。

用法：`python3 {{AIDP_HOME}}/scripts/check_sibling_family.py [--root .] [--json] [--changed-only] [--check F2] [--self-check]`。退出码：`0`=无 Critical；`1`=有 Critical；`2`=用法错。检查项：**F0 声明漂移 / F1 成员自带外壳 / F2 成员未登记 = Critical**；**F3 顺序未数据化 / F4 疑似家族无公共外壳 = Important**。豁免 `sibling-family-ignore: <F号> <原因>`（**原因必填**，注释结束符 `-->` 不算原因）。调用落点 = `/sprint-dev` Phase 1.3 Step 4.6（默认执行，带 `--changed-only`）；规则单一信源 = `{{AIDP_HOME}}/rules/code.md`「约定 20 姊妹条 —『同族增量项』」。

## check_ui_fidelity.py — 约定 39 通用还原度规则集的确定性机器检查（R2 / R3 / R10）

约定 39 共 13 条（R1–R13），**只有三条是确定性可机检的**，本脚本就做这三条：**R2** 状态标签内容随数据变化而 `type`/`color` 是字面量常量（不同取值共用同一视觉编码）→ Important；**R3** 文本截断（`text-overflow:ellipsis` / `-webkit-line-clamp` / `truncate` 原子类）而同节点或父节点无 `title`/tooltip → Important；**R10** 导出方法体内透传分页参数（导出只导当前页）→ **Critical**。其余 10 条依赖语义判断，归 `version-auditor` 审计 F（R1）/ `code-verification-loop`（R5–R9）/ `dev-manual-testcase`（通用还原度套件），本脚本**不涉足**。

★ **三条都做了收窄，别把它们"优化"回去**——每条的放行条件都是刻意的，去掉就会刷屏：**R2** 只在「内容动态 + 颜色写死」时报（写死内容+写死颜色是正当的固定角标，动态+动态是正确写法，只有前者动后者不动才是缺陷特征）；内容区**必须按闭合标签精确截断**，早期版本用「开标签 + 固定 2 行」当窗口，把下一个兄弟节点的 `{{ }}` 当成本标签内容而误报。**R3** 只查模板里真正用到的截断类，命中后在前后 2 行窗口找 tooltip 线索才报。**R10** 窗口内出现循环 / `hasNext` / `MAX_VALUE` 等「翻页捞全量」特征即放行——那是正当写法。**宁可漏报、不可刷屏**：一条误报就会让下游把整个脚本关掉，比漏报糟得多。

用法：`python3 {{AIDP_HOME}}/scripts/check_ui_fidelity.py [--root <仓库根>] [--check R2,R3,R10] [--paths <文件…>] [--json]`。退出码：`0`=无 Critical（含仅 Important）/ `1`=有 Critical / `2`=用法错误。扫描面 `code/**`，自动跳过 `node_modules`/`dist`/`target` 等构建产物与 `test`/`spec`/`mock`/`demo` 命名的文件（测试与示例代码不参与还原度判定）。
豁免：受检行**或其上一行**加 `fidelity-ignore: <规则号> <原因>`（只看这两行是刻意的——豁免必须贴着被豁免的代码，否则文件头写一条就能静默整份文件）。R2/R3/R4 存在正当例外故可豁免；**R10 的「导出只导当前页」不设正当场景**。

## check_upstream_call_log.py — 约定 40 上游/第三方接口调用日志的确定性机器检查

判 5 条：**C1** 出站调用类零日志 / **C2** 成功路径不可见（日志全为 warn/error）→ **Critical**；
**I1** 无一条日志提到 URL / **I2** 成功路径只有 debug / **I3** 疑似凭据明文入日志 → **Important**。
**单位是文件不是行**——这类缺陷天然是类级的（"这个客户端有没有日志"），行级判定只会制造噪音。

用法：`python3 {{AIDP_HOME}}/scripts/check_upstream_call_log.py [--root <仓库根>] [--check C1,C2] [--paths <文件…>] [--pii] [--json]`。
退出码：`0`=无 Critical / `1`=有 Critical / `2`=用法错误。扫描面 `code/**` 的 `.java`/`.kt`（其余语言按技术栈门控整体跳过，不猜）。
豁免：受检行或其上一行（文件级检查写在类声明行或文件头 30 行内）加 `upstream-log-ignore: <检查号> <原因>`。

★ 两条口径别"优化"掉：① **出站客户端变量名一律通配**（实测同仓并存 `restTemplate`/`smsRestTemplate`/`aiStaffRestTemplate`，
写死名字会静默漏掉一半出站类、且表现为全绿）；② **拦截器只在同文件内抵扣、且只抵扣 HTTP 类机制**（真实样本里拦截器是内部私有类、
只挂在自己那个 `RestTemplate` 上，全局抵扣会放过隔壁真正零日志的客户端；对象存储 SDK 也不在 HTTP 拦截器覆盖面内）。
已知盲区（刻意不做）：`@FeignClient` 接口整体排除、序列化后对象内嵌的凭据静态不可判、个人信息字段默认不检（`--pii` 开）。

## check_skill_ref_freshness.py — 命令/Agent 引用 SKILL 内部编号的新鲜度守卫

`{{AIDP_HOME}}/{commands,agents,flows,rules,reference}` 里大量写着「`code-verification-loop` 维度 11」
「`dev-logic-architect` 检查项 34」这类**对 SKILL 内部编号的引用**。SKILL 在本仓库迭代，
**SKILL 加一个维度时，命令侧的引用不会有人想起来改数字**——而读的人会当真：执行体会去找不存在的维度、
或按过期的计数以为少跑了一档。真值就在 `{{AIDP_HOME}}/skills/*/` 里、数得出来。

判三类（全部要求**同行出现 SKILL 名**才纳入判定）：**索引引用**（`维度 11`）编号须存在 · **计数声明**
（`11 维度`）须等于最大编号 · **脚本引用**（`check_xxx.py`）须真在那个 SKILL 的 `scripts/` 下。

**真值源只收 `{{AIDP_HOME}}/skills/`（`contract` 安装位）**，⛔ 不收并列安装的脚手架 SKILL（`aidp-code-engineer` 在 `{{AIDP_HOME}}/skills/`）——与 `check_skill_ref_drift.py` 的注册表**刻意不同**（那边两位都收）。
它的 `scripts/` 是脚手架引擎、本就由 skill 自己编排、不该被命令端逐个接线，收进来只会让 `unreferenced_skill_scripts` 一次冒出一批永远消不掉的 WARN，这条告警随即整体失去信号；它也没有「维度 N / 检查项 N」这套编号体系，索引与计数两条判据对它恒空跑。
⚠️ 这不是"脚手架 SKILL 无人看管"：它的内部文件引用归 `check_skill_ref_drift.py`（只问"文件在不在"，与安装位无关），镜像一致性归 `mirror_to_bundle.py --check`。**拆表 ⛔ 不等于加豁免**——豁免会连"文件在不在"一起放掉。

用法：`python3 {{AIDP_HOME}}/scripts/check_skill_ref_freshness.py [--root <仓库根>] [--json]`。
退出码：`0`=无 ERROR / `1`=有 ERROR / `2`=用法错。已挂进 `verify.py::check_skill_ref_freshness`。
豁免：行尾 `<!-- skillref-check: ignore -->`；整份 `<!-- skillref-check: ignore-file 理由 -->`。

★ 两条口径别"优化"掉（都是实测误报的固化）：① 一行同时点名两个 SKILL 是常态，编号归**左侧最近**那个；
② 还要**限距 300 字符**——`reference/` 里有单条 bullet 上千字符顺带点名四五个 SKILL，实测一处编号距最近
SKILL 名 713 字符，那不是归属是噪音（窗口调小到 120 会漏掉距离 167 的真阳性，200~500 结果恒定）。

⚠️ **本脚本抓不到「SKILL 新增硬门、命令侧回检表没接线」**——那时 SKILL 自己的派单块必然引用了该脚本。
那个不变量是仓库专属的，放在 `tests/test_guard_scripts.py`「Step1.6 回检表覆盖 dla 派单清单」断言里。

## check_flow_bash_syntax.py — 契约目录里 ```bash 围栏的语法有效性

`flows` / `commands` / `agents` / `reference` / `rules` 里的 bash 围栏是**要被逐字执行的**，却写在 Markdown 里、没有任何编译期检查。一次维护就能写坏，
而坏法看起来都很正常：注释插进 `\` 续行中间 · 编辑长行时截断了字符串 · `case` 少 `esac`。
执行现场往往是 7×24 无人值守的某个 tick，炸了只留一行 stderr、没人看。

判两类：**A. `bash -n`**（纯语法解析、不执行任何命令）；**B. 续行吞注释** —— 行尾 `\` 的下一行是注释时，
续行会把两行并成一条命令、`#` 之后的参数被静默吞掉。B 类**语法完全合法**，`bash -n` 查不出，只能按词法判。

**bash 能力探针（Windows 上零空等的关键）**：执行前先 `shutil.which("bash")`，再用它跑一次 `bash -c exit 0`（5 秒上限、stdin 接 DEVNULL）。
⛔ 只靠 `which` 不够——Windows 上 `C:\Windows\System32\bash.exe`（未装发行版的 WSL 转发壳）与缺 MSYS 运行时的 Git-Bash 都是"**存在但起不来**"，`which` 对它们一律为真，于是每个围栏各挂一次、直到调用方 180 秒超时才收场，**一次 verify 被一条环境事实拖死**。
逐围栏的 `bash -n` 另设 10 秒上限：探针过了却在某个围栏挂住，同样立刻整门收敛成「不适用」（⛔ 不记成 finding——那是把环境故障栽赃给契约正文）。

用法：`python3 {{AIDP_HOME}}/scripts/check_flow_bash_syntax.py [--root <仓库根>] [--json]`。
退出码：`0`=全通过 / `1`=有语法错 / `2`=用法错 / **`3`=不适用（`N/A(bash-unavailable)`，本机无可用 bash，一个围栏都没验过）**。已挂进 `verify.py::check_flow_bash_syntax`。
⛔ `3` 既不是通过也不是"环境炸了"：返回 `0` 会把"没验过"伪装成"验过且没问题"（假绿，最坏），返回 `2` 会让调用方按环境错处理。`--json` 下同时给 `applicable=false` / `status="unsupported"` / `reason="bash-unavailable"` / `level="INFO"`，按退出码判与按字段判同源。
`applicable` **两条路都给**（真跑过 = `true`，不适用 = `false`）：只在 N/A 分支给字段，按 `data.get("applicable")` 判的调用方会把一次「跑过且没问题」读成「不适用」而整门跳过——那是比误报更难发现的假绿。
豁免：围栏上方一行加 `<!-- bashsyntax-check: ignore -->`；整份加 `<!-- bashsyntax-check: ignore-file 理由 -->`。

★ 三处口径别"优化"掉（都是实测误报的固化）：① 占位符 `<…>` 必须中和，否则被 bash 读成重定向（实测 7 处假红）；
② 中和正则要排除 heredoc `<<'PY'` 与含引号/斜杠的片段，否则会把 `python3 - <<'PY' 2>/dev/null` 的定界符吃掉；
③ B 类要跳过**注释行末**的 `\`——在注释块里贴示例命令是正当写法（实测命中过一处）。

## check_chain_unattended.py — 「串联下游必透传 `--unattended`」的棘轮守卫

规则：任何命令调起任何「认该 flag」的下游命令时都必须带上它（有唤醒源时另加 `--no-loop`）。
但**「这一行到底是不是调用」判不了**——同一份文件里这三种写法几乎一样：
真调用（「循环调用 `/sprint-full {NNN}` 执行每个 Sprint」）· 明令禁止的反例（「❌ 输出『下一步：…』」）·
边界说明。区分要读中文语境；正则做检测器要么漏真调用、要么报几十条描述性引用，
而**一道从第一天就报几十条红的门只会被关掉**。

故改成**棘轮**：已人工判定为「不是调用」的站点冻进 `chain-unattended-baseline.txt`，
只有**新增**候选才报错、逼作者当场判一次；baseline 里的站点后来补了 flag 会提示可收紧（只紧不松）。

用法：`python3 {{AIDP_HOME}}/scripts/check_chain_unattended.py [--root <仓库根>] [--json]`；
人工判定完用 `--update-baseline` 重新冻结。退出码：`0`=无新增 / `1`=有新增待判 / `2`=用法错。
已挂进 `verify.py::check_chain_unattended`。

★ baseline 必须记**出现次数**（第三列）：同文件同形调用常出现多次，只记 (文件, 调用文本)
会让新增的那一次被既有条目掩盖 —— 实测加一行后候选 33→34 却全绿。

## check_shard_id_style.py — flow 分片编号标题风格一致性（提示性 WARN）

同一命令的 flow 分片里，**同一层级**标题的编号写法两种形态并存（`#### Step 3.3.7.1：` vs `#### 3.3.7.1：`）会让**跨片引用无法被同一套锚点检查覆盖**——写「见 Phase 3.1.5」还是「见 3.1.5」取决于目标标题怎么写，检查器只能按一种找、必然漏掉另一半，于是这类引用只能靠人读。
★ **按标题层级分组统计**：`### Step 3.3.7：`（主步带前缀）+ `#### 3.3.7.1：`（子步裸编号）是**有规律的分层**、正常；只有**同层级内**并存才判问题。不分层的一刀切会把合理设计报成缺陷（初版即如此）。判 **WARN 不判 ERROR**：统一风格要动大量标题并连带影响引用，属需集中整改的事，不宜阻断提交。
用法：`python3 {{AIDP_HOME}}/scripts/check_shard_id_style.py [--root <仓库根>] [--json]`，退出码恒 `0`（提示性）/ `2`=用法错；由 `verify.py::check_shard_id_style` 映射为 **WARN**。豁免：分片内 `<!-- shardstyle-check: ignore-file <理由> -->`。

## check_ghost_flags.py — 幽灵旗标（文档教用户传的 flag 必须真存在，确定性）

命令 flag 的**定义处**（`{{AIDP_HOME}}/commands/*.md` 参数表/参数列表/命令语法块）与**引用处**（flows 分片、reference 速查、docs/init 指导）之间没有约束时，稳定复发两类缺陷：① **幽灵旗标**——文档言之凿凿教用户传 `--aiauto-suite` / `--suite`，而它们在任何命令里都没有定义，用户照抄执行 → 解析不到、静默当无参跑；② **未登记旗标**——命令正文消费某 flag 却没写进自己的参数表。二者都跑一次才知道，任何断链/锚点检查都发现不了。
定义源（任一命中即算存在）：命令 `.md` 的**表格首格** / **参数列表项** / **自身命令语法块**（围栏里以 `/<本命令>` 开头的行）/ **小标题**，加上仓库脚本的 `add_argument("--x")` 与脚本·skill 源码里的 flag 字符串字面量（含 `startswith("--x=")` 形态）。引用面抽两类：行内代码里的 `` `--x` `` + **围栏代码块内裸写**的 `--x`（可复制粘贴的示例最该抓）。
★ **零误报的主力是「旗标归属（owner）」判定，不是白名单**：每处提及按 `| ; && || $( ` 切段后归属到段首命令 token——owner 是 AIDP 斜杠命令或本仓脚本 → 受管；是 `git`/`npx`/`claude`/skill 自带 CLI → 不受管；无 owner（表格里孤零零一个 `` `--x` ``）→ 受管。`\` 续行继承上一行 owner。这样"新写一条 `git xxx --yyy`"永远不会制造误报，白名单不必追着外部工具跑；`THIRD_PARTY_FLAG_WHITELIST` 只兜**散文里无命令可归属的裸提及**（CICD 流水线参数 / chrome / claude CLI / git 等，逐组注明豁免理由），`IGNORED_FLAG_PREFIXES` 兜 CSS 自定义属性（`--el-color-*` 等）。教学示例/反面教材用 `<!-- flag-check: ignore -->`（另有 `ignore-file` / `ignore-begin`…`ignore-end`）。
用法：`python3 {{AIDP_HOME}}/scripts/check_ghost_flags.py [--root <仓库根>] [--path <相对路径>] [--show-orphans] [--json]`。退出码：`0`=无未定义旗标 / `1`=检出 / `2`=用法错。`--show-orphans` 额外列「定义了但引用面无人提及」的可能废弃 flag（**INFO，不影响退出码**）。`tests/test_guard_scripts.py` 有正反两类用例。

## check_loop_examples.py — `/loop` 示例必带 `--unattended`（确定性）

7×24 的两条链路示例（`/loop 10m /sprint-autopilot --unattended` + `/loop 5m /sprint-aiauto-test --unattended`）里，`--unattended` 不是装饰：**首个 tick** 上 baseline 持久化标志尚未落盘，无人值守判据实际只剩"prompt 里有没有 `/loop` 字样"一个信号，某些 runtime 唤起时不含该字样 → 首 tick 误判交互式 → 撞第一个 `AskUserQuestion` 就挂起等人。文档自己写着这条，散落各处的示例照样反复漏写（一次审计查出多处）。
判据：全仓 `.md`（默认不下钻 `{{AIDP_HOME}}/skills/`——SKILL 本体 + bundle 镜像，由 `mirror_to_bundle.py` 同步）里匹配 `/loop [间隔] /sprint-autopilot|aiauto-test`（间隔可缺省），**逐"出现"判而非逐行判**（本次出现 → 下次出现/行尾之间必须含 `--unattended`，故"一行两条 loop 只给一条加 flag"同样被抓）。
豁免只认写在文件里的显式标记 `<!-- loop-check: ignore -->` / `ignore-file` / `ignore-begin`…`ignore-end`（对比反例、讲"去掉该 flag 才保留交互式判据"的段落用）——**绝不硬编码文件名白名单**：那种豁免会随文件改名/拆分静默失效，且下一个人根本不知道某文件为何被放过。
用法：`python3 {{AIDP_HOME}}/scripts/check_loop_examples.py [--root <仓库根>] [--path <相对路径>] [--json]`。退出码：`0`=全部合规 / `1`=检出漏写 / `2`=用法错。

## check_flow_var_refs.py — flow 分片里「读了但没人写」的变量（确定性，**ERROR 级**）

**★ `--per-fence`（诊断模式，⛔ 未接进 verify.py，刻意不设硬门）**：把「已赋值」再收紧一档到
**本围栏内、且在引用行之前**。Why：flow 的每个 ```bash 围栏是**一次独立 Bash 调用**，
围栏之间连 shell 变量都不共享；而默认 / `--strict` 两档收集赋值的粒度分别是「全仓」「本文件」，
于是「围栏 A 赋值、围栏 B 读取」这一整类断链**结构上检不出**——典型后果是 `$BE` 展开成空、
`--version … set …` 报 command not found、状态一字节不写，而**全程不报错**。
⚠️ 当前有噪声（`for` 体内赋值、`$(...)` 子壳、循环局部量按行序判会误报），故只作**排查工具**：
改动 flow 后跑一次、逐条人工判定，**别直接当门用**（假红多了守卫就没人看）。

扫 `{{AIDP_HOME}}/flows/**/*.md` 的 bash 块，找出**引用了、但全仓 flow 从未赋值**的 shell 变量。这类缺陷人读发现不了（每段单独看都合理，错在写的人和读的人不在同一分片），而后果是**判据恒真/恒假**——最坏的一次把"红"判成了"绿"（`THIS_ROUND_FAIL_COUNT` 无人赋值 → `${VAR:-0}` 取 0 → 不论失败多少条都判收敛）。

用法：`python3 {{AIDP_HOME}}/scripts/check_flow_var_refs.py [--root <仓库根>] [--path <相对路径>] [--json]`。

判据：只扫 ```bash / ```sh 围栏，**行注释里的 `$VAR` 不计**（那是"文档在讨论这个变量"、不是代码在读它）。赋值识别覆盖行首、`;`/`&&`/`||`/`then`/`do` 之后、多变量 `local A=1 B=2`、无 `=` 的 `declare -A MAP`、以及 `eval "$(脚本 --shell)"` 注入。

三类**绑文件**的合法放行（绝不全局放行——"读的人和写的人不在同一分片"正是本脚本要抓的病）：① `TUNABLE_ALLOW` 可调阈值（新增须满足「引用处恒带 `:-默认值`」且「默认值本身安全，取到它不会把红判成绿」两条）② 写了 `autopilot_tick_flags.py --shell` 的文件放行本 tick 变量全集（清单单一信源 = 该脚本）③ 写了 `autopilot-prd-watch.py --shell` 的文件放行其注入的四个变量。行级/文件级豁免 `<!-- flowvar-check: allow VAR -->` / `ignore` / `ignore-file`。

⚠️ **它曾长期只作诊断工具、不作硬门**，理由是 `${VAR:-3}`（合法可选阈值）与 `${THIS_ROUND_FAIL_COUNT:-0}`（默认值恰好意味着"没失败"，致命）语法完全同形、区别只在语义，当闸门会得到一屏恒红噪音然后被所有人忽略。噪声源现已逐条根除（见上两段），实测 63 → 0，故升为 `verify.py` 的 ERROR 级硬门：**归零之后再红就是真信号**。若将来又出现大批合法误报，正确动作是补豁免规则或登记 `TUNABLE_ALLOW`，不是降级为非硬门。

## check_line_refs.py — 跨文件引用里的硬编码行号（确定性，**WARN 级**）

`06_版本与用户目录约定.md §2.2 行 49~52` 这类引用**必然失效**：被引文件前面插一段话，行号整体位移，读者翻过去看到的是毫不相干的内容却毫无察觉（真实回流：`docs/testing/V0.0.1/README.md` 曾漂移约 18 行，两份文件本身都"没错"，断链/锚点检查都发现不了）。行号不属于被引文档的语义，正确做法是引**小节名/标题锚点**。  <!-- lineref-check: ignore -->
判据：全仓 `.md`（同上不下钻 `{{AIDP_HOME}}/skills/`）匹配 `行 12~34`（含 `-`/en·em dash）、`第 12~34 行`、`:L12-34`、`L120-L180` 四种写法；**L 形态只认两位以上数字**——本范式用 `L1-L3` 表示层级（UI L1/L2 分级、上游溯源 L1-L3），不设下限即恒误报。报告按目标可解析性分两组：**目标存在**（真会漂移，优先改）/ **目标路径解析不到**（多为文档拆分后的 `（原 phase-3.md 行 1–84）` 溯源留痕，可低优先）；解析只做"相对引用者目录 + 相对仓库根"两步，不按 basename 全仓找同名（否则会得出"目标仍在"的假结论）。豁免：`<!-- lineref-check: ignore -->` / `ignore-file` / `ignore-begin`…`ignore-end`。
用法：`python3 {{AIDP_HOME}}/scripts/check_line_refs.py [--root <仓库根>] [--path <相对路径>] [--json]`。退出码沿用全仓统一口径 `0`=通过 / `1`=检出 / `2`=用法错；⚠️ **本项为 WARN 级**——退出码 1 表示"检出"而非"必须阻断"，调用方（`verify.py` / 命令端）自行决定映射成 WARN 还是 ERROR（同 `check_version_identifier.py` 先例）。

## check_shard_counts.py — flow 分片自称片数 / 范围记法 vs 实际文件数（确定性，**ERROR 级**）

分片会**二次切分**（`phase-0-6.md` 旁边追加 `phase-0-6b.md`），而散落多处的「**N 片**」与「`phase-0-1.md` … `phase-0-9.md`」这类**范围记法**不会跟着改。后果不是排版问题：执行体按「共 9 片、`phase-0-1` … `phase-0-9`」推进时 **`phase-0-6b.md` 整片不会被 Read**，那一片里的硬门（0.4 项目状态检查、P0-1 incremental 判据等）就此静默漏跑，而**既有守卫一个都看不出来**（`check_count_claims.py` 只查三类硬编码计数、`check_md_anchors.py` 只验链接）。
判据两条：① **片数声明**——行内能确定归属命令时，声明值须命中该命令的合法真值集（整命令执行分片数 / 全部文件数 / 任一前缀分组片数如 `phase-0` 组 10 片）；② **范围记法**——端点之间存在未被本行显式提及的分片（典型 `b`/`bis` 后缀）即 FAIL。零误报设计：排除序数形「第 N 片」、范围只在**本文件所属命令**内比对（`phase-3-*` 多命令都有）、附属文件（`rationale`/`invariants`/`usage-guard`）不计执行分片。豁免：`<!-- shardcount-check: ignore -->` / `ignore-file`。
用法：`python3 {{AIDP_HOME}}/scripts/check_shard_counts.py [--root <仓库根>] [--json]`。退出码 `0`=一致 / `1`=检出 / `2`=用法错；由 `verify.py::GUARDS` 映射为 **ERROR**。

## check_deployment_path_refs.py — 文档里的部署路径必须写成约定 37 两轨结构（确定性，**ERROR 级**）

`verify.py::check_deployment_two_track_layout` 只查**文件系统**，查不到文档；而长期漂移的恰恰是文档——命令 / flow / README / memory 里若写着 `docs/deployment/{version}/sql/init.sql` 这类**旧结构路径**，执行体照着它 `mkdir`、写文件，于是"文件系统那道门刚过、下一次又被文档带回旧结构"。本脚本 = 那道门的**文档版**，与它同源同判据。  <!-- deploypath-check: ignore 本行为反例示范，故意写旧结构路径 -->
判据：全仓 `.md`（默认不下钻 `{{AIDP_HOME}}/skills/`——SKILL 本体 + bundle 镜像，由 `mirror_to_bundle.py` 同步）里，① `docs/deployment/<版本>/sql/` 之后的**下一个路径段**不是 `增量`/`全量` → 违规；② `docs/deployment/<版本>/配置文件/` **直接**接 `配置项清单*.md` / `*.conf` / `docker-compose*` / `k8s-*` → 违规（前者归增量轨、后三者是完整文件 = 全量轨，见约定 37.2）。`<版本>` 同时认占位符 `{version}`/`<version>`、真实号 `V1.2.3`、通配 `*`。**后面什么都不接的裸目录引用不报**（那是指两轨的父目录本身，约定 37 正文自己就这么写）；配置侧**只认上述四种旧文件名**——宁可少报，不为多抓一个而制造噪音。
豁免只认显式标记 `<!-- deploypath-check: ignore -->` / `ignore-file` / `ignore-begin`…`ignore-end`（搬迁映射表的"旧位置"列、讲历史结构的段落用）——**绝不硬编码文件名白名单**（随改名静默失效）。
用法：`python3 {{AIDP_HOME}}/scripts/check_deployment_path_refs.py [--root <仓库根>] [--path <相对路径>] [--json]`。退出码：`0`=全部两轨写法 / `1`=检出旧结构 / `2`=用法错。

## 约定 22 四族增量册 / AI 测试可见性 / DDL 注释配套脚本

| 脚本 | 一句话 | 用法 |
|------|--------|------|
| `check_testdata_prereq.py` | 用例前置资源对账：用例册的 `{待用户填写: X}` 占位 ↔ 约定 38 产物 | `--version V0.1.0` |
| `check_underscore_glob.py` | 四族目录的通配 `.md` 扫描是否漏排 `_` 前缀（漏排 = 增量册被当用例源） | 无参 |
| `check_case_ledger_pending.py` | 实测前门：本版还有没有**未级联**的用例增量（有 = 跑的是老用例集） | `--version V0.1.0` |
| `incremental_cases.py` | 从 git 算本轮新增的用例 TC-ID（只认新增的用例**标题行**） | `--version V --build B --record` |
| `check_sql_ledger_comment.py` | 本版 `ADD COLUMN` 的注释覆盖率**有没有实查库**并落台账「三之二」 | `--version V0.1.0` |

**基线清单**：`skill-script-wiring-baseline.txt` — SKILL 自带、命令端**无需**接线的脚本白名单
（`check_skill_ref_freshness.py` 的豁免面；每条必须写清为什么不用接，且前提须核实过）。

## check_count_claims.py — 文档「自称计数」与实际对账（确定性，**ERROR 级**）

「N 项核心约定」「N 个语义维度」「共 N 组」这类自称计数的共同点是：**加东西的人不会想起改数字，读的人会当真**——「3 个语义维度」会让执行体跑完第 3 个就收工、第 4 维静默不执行。一次审计一口气抓到三处过期（`aidp-compliance`「3 个语义维度」实为 4、本文件「共 9 组」实为 16、`设计目标.md`「36 项核心约定」实为 37）。计数天然确定性——被数的东西就在仓库里，不该靠人记得回头改。  <!-- countclaim-check: ignore 本行复述已修复的历史过期计数，非现行声明 -->
判据（三类，**宁可少做不可误报**）：① `N 项核心约定` / `核心约定 1–N` / `约定 1-N` / `核心约定 N 条` ⇢ 比对「核心约定」正文最大约定号（口径复用 `verify.py::check_convention_anchor_consistency`；正文权威文件：模板仓库 = `{{AIDP_HOME}}/AIDP-AGENTS.md`（下发记忆源），下游 = `agent_env.py memory-file` 判定的项目记忆文件。差别在**本脚本扫全仓**、verify.py 只扫 4 个固定文件——`设计目标.md` 那处正是漏在那 4 个之外）；② `N 个语义维度` ⇢ 比对 `{{AIDP_HOME}}/agents/aidp-compliance.md` 的 `语义维度 N` 小节数；③ `共 N 组` **且同行提到 `test_guard_scripts`**（行内共现锁上下文、不写死文件名）⇢ 比对 `tests/test_guard_scripts.py` 的 `【…】` 分组数。任一真值取不到 → 该类整类跳过、不猜不报。
豁免：`<!-- countclaim-check: ignore -->` / `ignore-file` / `ignore-begin`…`ignore-end`（讲历史演进的段落用）。
用法：`python3 {{AIDP_HOME}}/scripts/check_count_claims.py [--root <仓库根>] [--json]`。退出码：`0`=全部一致 / `1`=检出过期计数 / `2`=用法错。

**`--project-claims <设计目录>`（业务计数全库回扫）**：读「业务计数声明表」（5 列）后全库回扫，
报两类候选（非动态而数字对不上 / 已声明动态却仍写成「共 N·恰 N」）。**一律 WARN、判定权在人**
——"取值域全集 14 项"是合法留存、"恰 14 行"是必须改的断言，脚本只负责把候选列全。
表不存在即整段跳过，不影响原有三类检查。散落面列写正则，`\|` 等 markdown 表格转义会自动还原。

## check_cascade_obligation.py

约定 22 义务登记门：Sprint 归档里写下的「须按约定 22 回灌」必须同轮落进对应族的 `_开发期{族}增量.md`。
接线 = `/sprint-close` Step 3.5。只断言载体存在、不做逐条映射（逐条必产假阳性）。

## check_cascade_residue.py

约定 22 口径级联残留门：旧口径是否仍作为**生效规则**残留在四族文档里。
把命中分「真残留 / 订正留痕」两类，上下文扫描遇标题即止。接线 = `version-auditor` 审计 G 前置。

## tests/sync_group_table.py — tests/README 分组表重排器

把 `tests/README.md` 的分组表与 `test_guard_scripts.py` 的**实跑分组**对齐：真值现算
（跑一遍套件、按实跑顺序取 `【…】` 与 `[NN] …` 两种标题），已填的「覆盖」列按标题原样保留，
新增分组填 `—`。**Why 要有它**：那张表自称「单一信源」却停在 30 行、落后 45 组——根因不是
谁偷懒，而是**维护方式本身要求人手抄**。只加一道行数机器门不够：门每次红、人每次手工重排、
下一次照样漂，只是漂之前会红一下。
用法：`python3 {{AIDP_HOME}}/scripts/tests/sync_group_table.py [--check]`。
退出码：`0`=已一致 / 已写回；`1`=`--check` 下检出漂移；`2`=用法或环境错。

## plan_sprints.py — 研发执行计划 → Sprint 集合的唯一口径

扫 `docs/plans/{version}/` 下**全部** `*研发执行计划*.md`（不是第一份），产出 Sprint 全集 /
已关闭集 / 剩余集 / 下一个待跑。⛔ 别再用 `find … -print -quit`（只取一份、find 还不排序）或
硬编码 `01_研发执行计划.md`：多用户拆 `NN_研发执行计划-{姓名}.md`、超阈拆 `02_`…、跨 ≥3 里程碑拆
`01_M1研发执行计划.md` 都是 `dev-execution-planner` 明确支持的形态，取第一份 = **M1 跑完即判「全部 Sprint 已关闭」，
M2 从未执行且无任何告警**（不报错、不重试、结论是"成功"——无人值守下最坏的一类失效）。
用法：`python3 {{AIDP_HOME}}/scripts/plan_sprints.py --version V0.1.0 [--root .] [--shell | --json]`。
`--shell` 导出 `PLAN_FILE_COUNT` / `PLAN_FILES` / `ALL_SPRINTS` / `CLOSED_SPRINTS` /
`REMAIN_SPRINTS` / `REMAIN_COUNT` / `FIRST_SPRINT` / `NEXT_SPRINT` / `CURRENT_SPRINT`
（变量名与 `check_flow_var_refs.py::SCRIPT_INJECTED` 登记表由回归用例钉死一致）。
退出码：`0`=解析成功 / `1`=fail-closed（无计划文件，或有文件但一个 Sprint 都解析不出——
⛔ 刻意不返回"空集 + exit 0"，空集会被调用方读成「全部已关闭」）/ `2`=用法错。
接线 = `flows/sprint-autopilot/phase-3-5.md`（三处）+ `phase-3-4.md` 铸 build 出口游标。

## check_design_anchor.py

实现偏离设计门：详细设计点名过的字段/常量到源码里找落点，抓「换了数据来源却编译过、
界面完整、不报错」那类偏离。Important 级。接线 = `/sprint-close` Step 2.5.1 +
`code-verification-loop` 维度 13（**比维度 10/12 多一个必填 `--version`**）。
用法：`python3 {{AIDP_HOME}}/scripts/check_design_anchor.py --version V0.14.0 [--root .] [--code code] [--design <额外设计目录>] [--json]`。
退出码：`0`=全部锚点可定位（或无设计/无代码 → N/A 跳过）/ `1`=有找不到落点的锚点（Important），或路径不可读（fail-closed）/ `2`=用法错。
⚠️ **「有发现」必须落 1 而非 2**——与 `check_ui_fidelity.py`·`check_upstream_call_log.py` 同一套。
维度 13 的调用方对 `exit 2` 的处置是「入参/环境错 → 修正参数后重跑」，既不计过也不计不过；
把发现放在 2 上，每条真实偏离都会被读成环境问题丢掉，**门在跑、恒绿、两侧报告都不留痕**。

## check_cascade_landing.py — 约定 22 收口落点门（确定性，**ERROR 级**）

收口级联**直接改各族内容主文档**（`01_` 等）+ 可刷 `00_索引.md`；⛔ 不新建分册。四族增量册 `_开发期{族}增量.md` 是开发期变更的唯一承载，收口时在其中删条目、清空即删文件，因此在收口批次里被改动属**合法落点**。
判据：给定收口批次范围，四族版本目录下的改动里**不得出现本批次新建的** `NN_<业务主题>.md` 分册（`NN_` 是产品侧 PRD/原型变更 + 口述累进的命名空间）。⚠️ 判"新建"而非文件名——主文档 `01_研发需求.md` 与增量 `07_订单主题.md` 名字完全同形，正则分不开。⛔ 刻意**不做**全仓扫描：发布期收敛、`/version` 规划期生成、人工修订错别字都会合法地改主文档，范围锚在 base-ref 上语义才确定。
⚠️ 实现要点：git 的 `core.quotepath` 默认把中文路径转义，不关掉则路径恒匹配不上、本门恒报「0 处改动、合规」（实测原地改主文档的反例被判通过）——回归用例已钉死这条。
用法：`python3 {{AIDP_HOME}}/scripts/check_cascade_landing.py [--worktree | --base-ref <收口前 HEAD>] [--version V0.1.0] [--json]`。退出码：`0`=合规 / `1`=违规或无法判定（fail-closed：base-ref 解析不了、识别不出版本目录同样 exit 1）。

## check_skill_ref_drift.py — 命令/Agent 对 SKILL 内部文件的引用有效性（确定性，**ERROR 级**）

命令端按约定 21 只做编排，但正文里大量出现 `dev-logic-architect/scripts/check_ddl_consistency.py`、`auto-test-runner/references/report-format.md` 这类**对 SKILL 内部文件的事实性引用**。SKILL 改个脚本名、并个 reference 时，命令侧的引用不会跟着变，就此悬空——而且**完全静默**，verify 全绿、测试全过，只有真去执行那一步的 AI 才发现文件不存在，那时已在下游业务项目的运行现场。
判据：扫 `{{AIDP_HOME}}/{commands,agents,flows,reference,rules}/**.md` 里形如 `<skill>/scripts/<f>.py`、`<skill>/references/<f>.md` 的引用，`<skill>` 命中**注册表**里真实存在的 SKILL 时该文件必须存在。
**注册表带 `location`，两类归属都收**：`contract` = 随运行包下发、进 `.aidp-runtime.json` 受管清单的公共 SKILL；`sibling` = 与运行包**并列安装、不进受管清单**的（脚手架自身 `aidp-code-engineer` 就是这一类，由 `scaffold_lib.py::RUNTIME_EXCLUDES` 排除出运行包、由安装器单独装/刷新）。⚠️ **运行根降层后两者物理同址**（都在 `各 Agent 的运行根/skills/<名>`：模板仓库是根 `skills/`，下游是 `.claude/skills/` 或 `.agents/skills/`），区别在**归属**而不在路径 —— 别再按路径去分它们。<!-- runtime-path-ignore: 适配位对照，必须逐字写出各 Agent 的目录 -->
两个根都由运行包解析算出，⛔ 不写死 Agent 目录字面量、也⛔ 不用手维护名单或单点豁免：`aidp-code-engineer` 从契约位挪到并列位那天，本门对契约正文里每一处 `aidp-code-engineer/scripts/*.py` 引用同时**静默**失明，而那正是 `/sprint-init`、`/health-check`、`aidp-compliance` 真要跑的几行 `scaffold.py` / `verify.py`——加豁免只会把这个洞永久钉死。
`location` 同时是给上层对账用的信源：**只有 `contract` 的 SKILL 才该被拉进"公共 SKILL 表"双向对账**，`sibling` 的按公共表口径对账必然报"表里有、目录里没有"的假红。相应地，`check_skill_ref_freshness.py` **刻意只收 `contract` 位**（脚手架 `scripts/` 是引擎、不该被命令端逐个接线，收进来会一次冒出一批消不掉的 WARN）。⛔ 刻意**不查**维度编号/参数名/章节标题：那些要语义匹配、误报率高，一个恒红的门比没有门更糟。
用法：`python3 {{AIDP_HOME}}/scripts/check_skill_ref_drift.py [--root <仓库根>] [--json]`。退出码：`0`=全部有效或无 skills 目录（N/A）/ `1`=检出悬空引用。
`--json` 的 **`skills` 字段（`{名: contract|sibling}`）是本仓唯一算出来的 SKILL 真值表**，刻意对外暴露：散文侧判定（如 `aidp-compliance`「命令调用的 skill 必须存在」）应拿它作减项信源——散文里带连字符的反引号 token（`emit-report`、`record-card`、`run-state` …）大量是脚本名 / 子命令动词而非 SKILL，靠词形分不开，只有对着真实目录减一次才分得开。⛔ 别再各自 `ls {{AIDP_HOME}}/skills/`：漏 `sibling` 位，且两处口径会各自漂。

## check_flow_shell_escapes.py — flow/命令 shell 围栏内的双重转义（确定性，**ERROR 级**）

在 Markdown 里写 bash，作者常出于"文档里反斜杠要转义一次"的直觉写成 `printf '%s\\n' "${ARR[@]}"`。但 **shell 单引号内不做任何转义**：`\\n` 就是反斜杠加 n 两个字符，整个数组被拼成**一行**且带字面 `\n`，紧跟的 `grep -qx`（整行精确匹配）**永远匹配不上**。本仓真实踩过：autopilot 的「未关闭 Sprint」集合判定因此恒不匹配 → REMAIN 恒等于全集 → 部署出口永不可达，而语法合法、退出码 0、既有 16 道门全绿。
判据：只在 ```bash/sh/shell 代码块内检查**单引号**字符串，含 `\\n`/`\\t`/`\\r` 即 ERROR。⛔ 双引号不查（jq/sed/awk 程序文本里那常常是对的），散文不查。豁免：`# shell-escape-ignore`。
用法：`python3 {{AIDP_HOME}}/scripts/check_flow_shell_escapes.py [--root <仓库根>] [--json]`。退出码：`0`=无 / `1`=检出。

## autopilot_unfreeze.py — 冻结解冻入口（幂等）

两条链路所有「解冻」动作的唯一入口，一律幂等（不满足条件即 no-op + exit 0）：

- **前置熔断按 reason 解冻**：`autopilot_unfreeze.py <prd-root-missing|stale-active-sprint|preflight-gate>` —— **仅当**当前 `preflight_fail_reason` 恰等于入参时才清三件套（这三类失败点在 0.1 之后产生，0.1 自身不清它们；恢复条件要用产生点自己的上下文判定，故由各自成功路径调用本入口）。未知 reason 退 2。
- **环境类冻结自动复探**：`--env-reprobe <V> [--apply]` —— 环境类集合从冻结枚举表实时解析（如 `cicd-unreachable` / `cicd-cli-unavailable` / `chrome-unavailable`）；指数退避 20min×2^n、单次封顶 4h、最多 10 次，到期配 `--apply` 放行并清以 `@V` 结尾的顶层 `aiauto_blocked_reason`；次数用尽写本地告警台账并转人工。
- **成功路径显式解冻**：`--clear <V> --reason <freeze_reason>` —— 仅当该版 `freeze_reason` 与入参一致时清（如驱动检测通过后清 `chrome-unavailable`）。
- **人工解冻**：`--manual <V>` —— 清该版冻结字段、复测上限冻结标记与全部失败计数；#4 通知正文按冻结类别附这条恢复指令。
- **只判不写**：`--aiauto-probe <V>` / `--aiauto-probe-all`（判 aiauto 冻结是否具备解冻证据；配置类 reason 如 `cicd-auto-trigger-off` 以 `memory/aidp-config.yaml` 修改时间晚于冻结时刻为证据，部署类以冻结后出现新部署为证据）；`--notify-reprobe`（里程碑通知通道被关后配置恢复即重开，清 `notify_enabled` / `notify_disabled_reason` / `notify_disabled_at`）。

用法：`python3 {{AIDP_HOME}}/scripts/autopilot_unfreeze.py [reason] [--env-reprobe V [--apply]] [--clear V --reason R] [--manual V] [--aiauto-probe V | --aiauto-probe-all] [--notify-reprobe] [--root <仓库根>] [--json]`。

## classify_commit_change.py / classify_push.py — 正式代码变更分类与 push 分流（约定 31.5）

`classify_commit_change.py` 判定一批改动里是否含**正式代码**（`code/**`、`web/**`、`server/**`、`src/**` 及各布局入口/锁文件），`classify_push.py` 在 push 前调它并把完整结果写进当前 build。无正式代码变更时记 `cicd_skipped=true`、**不触发/监听远端 CICD、不等部署、不跑就绪探针**，但仍校验 push 成功；正式代码变更、分类缺失或分类出错一律走监听路径（**fail-closed**）。⛔ 不得反过来用远端流水线状态反推分类。
用法：`python3 {{AIDP_HOME}}/scripts/classify_commit_change.py --root . [--base-ref <ref>] --json`；`python3 {{AIDP_HOME}}/scripts/classify_push.py --version <V> {--build <B> | --standalone} [--base-ref <ref>]`（记录按 commit 键控，供 `commit_gate.py::pending_cicd` 结算）。
监听结束后记部署终态：`python3 {{AIDP_HOME}}/scripts/classify_push.py --version <V> --record-terminal success|failed|unknown:<原因>`——`unknown:<原因>`（如 `provider=none`、CLI 不可用）是显式降级：不算欠账，但在门禁输出里可见。

## readme_policy.py — README 三档范围判定（共享策略，被 scaffold/migrate/verify 共用）

代码单元 / 导航枢纽 / 平铺叶子三档，判定顺序：**显式 `README_REQUIRED` 最先判（压过一切自动规则）** → 代码单元 → 导航判据（子目录数 ≥2，或 1 个非空子目录）→ 否则不需要。**判定的唯一实现**——`scaffold.py`/`migrate.py`/`verify.py` 一律调它，禁止各写一套路径判断。另提供范围外 README 扫描（排除依赖/产物/备份目录 + 按 git 跟踪过滤，输出先给汇总行）。详规见 `{{AIDP_HOME}}/rules/code.md` 约定 19。

## rename_version.py — 版本号全仓改名（目录/文件名/正文）

开发期临时编号发布时按 SemVer 正名是常规操作，下游已连续两版手工做：12 个版本目录 `git mv` + 15 个文件/目录改名 + **1710 处**文本替换，每次约 10 分钟，漏一处就是隐性残留且无机器门可拦。三个内置处理：① `{{AIDP_HOME}}/skills/` 与 `{{AIDP_HOME}}/scripts/tests/` 整棵排除（那里的版本号是**范式示例与测试夹具**，改了会破坏脚手架一致性和测试）；② 空目录 `git mv` 会失败，自动回退 `mv`；③ 收尾恒打印**剩余命中清单 + 逐条豁免理由**，有未豁免残留时**退出码 1**。代码内自报版本（pom 各级子模块/package.json/Dockerfile）是裸版本号格式，交 `check_version_identifier.py`，收尾会提示。
用法：`python3 {{AIDP_HOME}}/scripts/rename_version.py <old> <new> [--root .] [--apply] [--json]`（默认只出计划）。

## design_full_rollforward.py — 全量设计分册内 section 级前滚（3.3.11 提速）

3.3.11 的「变更范围增量」原只到**专题层**：进了 Δ 就整册从零合成，内容上一分没省。下游实测 6342 行里 **5245 行（83%）被重算**，该步占发布关键路径 **72%**——而"多域并行的正常版本"Δ 几乎必然全覆盖，这不是特例。
两个子命令：`scope` 出**覆盖率报告**（⛔ 必须在重算**开工前**打印，≥70% 时告警——否则要等四十分钟才发现"这次其实接近全量"）；`rollforward` 以**旧分册为底本**只替换点名的 H2 章节、其余原样保留（按 `^## ` H2 切段）。**哪些章节要重写是语义判断，脚本不猜**——由执行体按 Δ 映射传入，脚本只保证"没点名的一字节不动"，并对点名却在新内容里缺失的章节**报错而非静默丢弃**。
用法：`design_full_rollforward.py scope --full-dir <全量目录> --delta <专题名,...>` / `design_full_rollforward.py rollforward --old <旧分册> --new <staging 分册> --sections "<H2,...>" --out <目标>`。

## tests/ — 上述确定性脚本的回归单测

一键跑全部：`bash {{AIDP_HOME}}/scripts/tests/run.sh`。

| 文件 | 覆盖 | 运行 |
|------|------|------|
| `test_report_schema.py` | `emit-report.py` 数据契约校验（`validate_payload`）+ `buildNo` 派生 + 示例文件自校验（示例即契约）| `python3 {{AIDP_HOME}}/scripts/tests/test_report_schema.py` |
| `test_report_render.js` | 渲染口径（`pct` 0.84→84%、100.0→100% 不出 10000%）+ 坏数据健壮性（不白屏 / 无 undefined / 无 `#undefined`）| `node {{AIDP_HOME}}/scripts/tests/test_report_render.js` |
| `test_guard_scripts.py` | 确定性护栏全套（`check_convention_dup` / `check_version_identifier` / `baseline_edit` / 里程碑通知门 / `release_baseline_check` / `autopilot_stuck_check` / `check_md_anchors` / `check_ghost_flags` / `check_loop_examples` / `check_line_refs` 等）。**分组清单见 [`tests/README.md`](./tests/README.md)**（组数只能现算、不写死；机器回检 `check_count_claims.py` 同时统计 `【…】` 与 `[NN]` 两种标题形态）| `python3 {{AIDP_HOME}}/scripts/tests/test_guard_scripts.py` |
| 其余套件 | 提交前门禁、通知、多 Agent 装配与路由、7×24 调度、无人值守恢复、命令 ↔ SKILL 契约、发布域、报告不可变、文档引用与开源卫生三道门等，逐文件覆盖面见 [`tests/README.md`](./tests/README.md) | 见 `run.sh` |
| `fixtures/*.js` | 报告链路问题数据的回归样本（脱敏）| —（被上面两份消费）|
| `run.sh` | 一次跑全部；★ **新增测试文件必须登记进来**（漏收 = 该套件永远绿不了也红不了）| `bash {{AIDP_HOME}}/scripts/tests/run.sh` |

> 详见 `{{AIDP_HOME}}/scripts/tests/README.md`。

---

## check_skill_gate_list.py — 命令端写死「SKILL 阻断名单」的棘轮门（确定性）

SKILL **改一份名单**——比如把「不可豁免 = 维度 1/3/5/7」改成「凡标 `Critical` 的一律不可豁免，
判据就是标记本身」——命令侧写死的名单不会有人想起来去改。
而命令端那份写死的编号名单**只会比新规则窄**，窄掉的那几档就此静默放过。

实测（`auto-test-runner` 升级）：SKILL 把不可豁免集合从 4 条扩到 9 条，命令端仍写「维度 1/3/5/7
任一不通过 → 阻断」，于是**维度 2「驱动适配层四能力完备」失败只告警不阻断**——驱动四能力残缺时
那一轮的"全绿"结论根本无效，build 却被当成通过关闭。⚠️ 该次升级中两道既有 SKILL 引用门
（`check_skill_ref_drift` / `check_skill_ref_freshness`）**都返回 0 findings**：它们查的是
「编号存在吗 / 计数等于最大编号吗 / 脚本还在吗」，查不出「一份语义名单已经不再是权威」。

**判据由 SKILL 自己的声明驱动**，不靠本脚本猜哪些编号属于谁（本仓自己也有大量编号命名空间——
`aidp-compliance` 的 4 个语义维度、`/health-check` 的 10 个检查项、`/sprint-design` step-1.7
那张自有回检表，按编号形态判必然满屏误报）：某 SKILL 在自己文件里写了「不另立名单 / 不另列名单 /
判据就是标记本身」= 它在说「我这份集合会变，谁也别抄」；此后本仓契约正文里出现**归属于它**的
编号枚举（含 `维度 1（两层解耦）/ 3（状态机无残留）` 这种带括注的写法）即 ERROR。
豁免：行尾 `<!-- skillgate-check: ignore 理由 -->`。
退出码 `0`/`1`/`2`；映射为 `verify.py::check_skill_gate_list_guard`（ERROR）。

## check_arguments_channel.py — `$ARGUMENTS` 接收通道完整性（确定性）

`$ARGUMENTS` 是**斜杠命令正文的 runtime 文本替换**：只有 `{{AIDP_HOME}}/commands/<cmd>.md` 里真的写了
这个字样，宿主才会把用户输入替换进去。而 flow 分片是被 `Read` 进来的**普通文本**，
`${ARGUMENTS:-}` 在那里只是一个未设置的 shell 变量。

于是形成一个恰好落在最要命处的缺口：某命令把入参解析放在 flow 分片里做，命令正文却没写
`$ARGUMENTS` → 解析器恒收空串 → **该命令全部 flag 落 0**。实测两条 7×24 loop 命令曾同时踩中：
`--unattended` 收不到 ⇒ Phase 1 输出引导文案后退出，**每 tick 刷一屏引导、永不开工**；
而全仓其余命令都写了这一行。失败形态是「读起来完全正确」——flow 里那句解析写得一丝不苟，
只是它拿到的永远是空串。

判据：某命令自己或它的 `{{AIDP_HOME}}/flows/<cmd>/**` 里出现 `$ARGUMENTS` → 命令正文必须也出现，
否则 ERROR。只查「用了却没声明」，反向无害不查。豁免：行尾 `<!-- argch-check: ignore 理由 -->`。
退出码 `0` 齐备（或不适用）/ `1` 有缺口 / `2` 用法错。映射为 `verify.py::check_arguments_channel_guard`（ERROR）。

## check_prose_vs_executable.py — 散文承诺 ↔ 可执行语句对账（确定性）

本仓反复出现同一个形状：**契约把某个动作说得很清楚、校验侧也建好了确定性硬门，唯独动作本身
从头到尾只存在于散文里**。三次实测：里程碑通知发送在 autopilot 侧出现 7 次全在散文、bash 围栏内
0 处，而收尾门对里程碑通知台账的核验是无条件的 ⇒ 发送侧不真跑 = 台账恒空 = 收尾门恒 FAIL；
`ai_report_finalized` / `phase_beta_done_at` 等状态位曾同样「此时应把 X 标记为 Y」写在散文里、
没有任何 `baseline_edit.py set`；冻结三件套曾有分支只 `echo` 不写 `needs_human`。

共同点是**读起来完全正确**：句子在、理由在、判据在，只有执行不在。对应的失败形态不是报错，
是「门恒 FAIL」或「状态永不更新」，都要跑几个 tick 才显形。

判据（刻意只查确定性强、误报低的四个动作词）：某 flow 目录的散文里承诺了
`notify.py` / `record-card` / `needs_human` / `run-state`，则该目录的 ```bash 围栏里必须
至少出现一次同一动作。只做「整个目录有没有」，不做逐处配对（逐处配对必然满屏假红）。
豁免：目录里根本没提该动作即不适用；行尾 `<!-- proseexec-check: ignore 理由 -->`；
`rationale.md` / `usage-guard.md` / `invariants.md` / `README.md` 等纯说明性文件整体跳过。
退出码 `0` 全部有落点（或不适用）/ `1` 检出只说不做 / `2` 用法错。
映射为 `verify.py::check_prose_vs_executable_guard`（ERROR）。

## check_freeze_contract.py — 「冻结字段写入契约」齐备性 + 枚举合法性（确定性）

7×24 链路靠 `versions.{V}.needs_human=true` 冻结出问题的版本，等条件恢复再自动解冻。契约要求
**一次写齐四件**：`needs_human` + `aiauto_frozen_at` + `freeze_reason`（枚举内取值）+ 顶层
`aiauto_blocked_reason`。缺任何一件的后果都不是「少记一个字段」，而是**这一版永久停摆**——
缺 `aiauto_frozen_at` 则解冻判据（`last_deployed_at > frozen_at` / 配置 mtime > frozen_at）恒假；
缺 `freeze_reason` 则落 `unknown`、既不进环境类复探窗口也不进配置类分支。失效表现是
「安静地什么都不发生」，`/loop` 岁月静好地空转、零告警。

项目已为 CLI flag、tick 变量、loop 示例、链式透传都建了棘轮门，这条自称「缺一即冻死不解冻」的
契约若没有机器门，违约只会在永久停摆时才被发现（典型：7×24 最高频的部署探针超时路径
`probe-timeout` **零写入者**）。

判据：① 每个「置 needs_human 为 true」的站点，逻辑窗口内须同时出现 `*_frozen_at` 与 `freeze_reason`
② 取值须在枚举内 ③ 每个枚举值至少一个写入者（无写入者 = 死枚举）④ 至少一个解冻路径。
枚举**不硬编码**，从 `flows/sprint-aiauto-test/rationale.md` 的权威表实时解析。
`retest-cap` 走 `needs_human_kind` + `retest_cap_frozen_at` 是唯一合法变体，自动放行。

用法：`python3 {{AIDP_HOME}}/scripts/check_freeze_contract.py [--root <仓库根>] [--json]`，退出码 `0`/`1`/`2`；
由 `verify.py::GUARDS`（`check_freeze_contract_guard`）映射。豁免 `<!-- freeze-contract: ignore 理由 -->`。

---

## check_banned_terminology.py — AIDP 术语一致性（确定性）

AIDP 的模型是 **EPIC × Sprint × Task，没有 User Story 层**。这不是措辞洁癖：
`agents/version-auditor.md` 的 B-02 把「用户故事 / US-NNN」列为详细设计**命中即标**的越界项。
契约文档自己写着这些词 → 下游 AI 照着产出带 US 标注的设计 → 再被同一套范式里的审计 Agent
判违规，**规则自己和自己打架**，而这类冲突现有守卫一个都看不见。

豁免靠**显式清单**不靠正则猜：那些「正在定义该禁令」的行（B-02 判据行、模板里的 ⚠️ 警示行、
migrate 的改名说明）必须原样保留禁用词——它们就是规则本身。

用法：`python3 {{AIDP_HOME}}/scripts/check_banned_terminology.py [--root <仓库根>] [--json]`，退出码 `0`/`1`/`2`；
由 `verify.py::check_banned_terminology` 映射为 **ERROR**。豁免 `<!-- term-check: ignore 理由 -->`。

---

## check_convention30_prose.py — 约定 30「正文只陈述最终行为」的棘轮守卫

约定 30 禁止在指令正文里铺陈「原来怎样→现在改成怎样→为什么」。理由很实际：下游 AI 每次会话
都读这些正文，历史叙事既占上下文、又让它分不清「哪句是现行规则、哪句是已废弃的旧做法」。
没有机器门时叙事会一路堆积。

**棘轮而非检测器**：存量命中冻结进 baseline、只逼新增当场判一次；清理存量后 `--update-baseline` 收缩（僵尸条目会被报出）。
扫描面 = `{{AIDP_HOME}}/{commands,agents,flows,reference,rules}` + `docs/init` + 各 SKILL 的 `SKILL.md` + `docs/**/README.md` +
`{{AIDP_HOME}}/scripts/README.md` + `memory/README.md` + 根级 `AGENTS.md` / `CLAUDE.md` / `README.md` / `{{AIDP_HOME}}/AIDP-AGENTS.md`；
只豁免 `rationale.md`——它的职责就是记录「为什么」。词表含旧行为叙述（`此前…` / `曾经` / `曾允许` / `实测曾` / `原散落` 等）与范式版本戳。  <!-- conv30: ignore 本行列举词表本身 -->

用法：`python3 {{AIDP_HOME}}/scripts/check_convention30_prose.py [--root <仓库根>] [--json]`；
`--update-baseline` 重冻水位。退出码 `0`/`1`/`2`；由 `verify.py::check_convention30_prose` 映射为 **ERROR**。
豁免 `<!-- conv30: ignore 理由 -->`。数据文件 `convention30-prose-baseline.txt`。

---

## check_design_goals.py — `设计目标.md` 的指纹棘轮 + 实现名词体检

设计目标是审计维度「目标 ↔ 实现背离」的**参照系**，它的全部价值来自**稳定**：命令天天改、
目标跟着动，审计就退化成"拿今天的实现核对今天刚按实现改过的目标"——恒绿且毫无意义。
实测形态正是每次改命令都顺手把目标改一点，几轮下来目标里塞满「违约信号 / 边界例外」、
体积不断膨胀，写进去的早已不是目标而是实现。

两道判据：**① 指纹棘轮** —— 每条 `G-<域>-<序号>` 的正文做指纹存 baseline，改一个字 / 删一条
即 ERROR（**新增放行**：新增不改变老编号的含义，改写与删除会）；**② 实现名词体检** —— 目标句里
出现文件名 / flag / 步骤号 / Phase 号 / 路径 / 函数落点即 ERROR（只扫目标句本身，文件头的
维护纪律段点名脚本是合法的）。

用法：`python3 {{AIDP_HOME}}/scripts/check_design_goals.py [--root <仓库根>] [--json]`；
`--update-baseline` 重新定基 —— ⛔ **人工动作，执行体不得顺手调用**，那等于棘轮不存在。
退出码 `0`/`1`；由 `verify.py::check_design_goals` 映射为 **ERROR**。数据文件
`design-goals-baseline.txt`。下游无 `设计目标.md`（模板专属、不下发）→ INFO 跳过、退出码 0。

---

## check_changelog_fix_scope.py — 更新日志「🐛 修复」段准入判据回检

`版本更新日志.md` 是**给使用者读的**。列一条「修复了 X」等于告诉他「你之前遇到的 X 现在好了」——
但本版新功能自己引入、又在本版修掉的缺陷，**带 bug 的那版根本没发出去**，使用者从来没遇到过 X。
`/version` 取修复项的两个来源（`docs/bugfix/{version}/` 与 `git log | grep '^fix('`）都会把它们收进来。

实际项目中出现过：某版从 28 条 `fix(` 里挑 10 条写进日志，7 条依附于本版才新增的功能；
剔除后只剩 3 条，其中 1 条自五个版本前就存在——**那条才是真正值得写的，却被 9 条自产缺陷淹没**。
三重危害：对外失真 / 虚增修复数污染质量信号（那一列的真实含义是「清理了多少历史欠债」，
不是「这版返工了多少次」）/ 掩盖真实信号。

判据（唯一）：**该问题在上一个已发布版本中真实存在，且使用者可触达。** 脚本按提交粒度近似：
一条 `fix(` 提交若其改动的正式代码文件全部引入于上一个已发布 tag 之后 → 判「疑似自产自消」。
**F1（Important）**：日志修复段条数 K > 非自产自消的 fix 提交数 (N−M) → 至少 K−(N−M) 条应剔除。

⛔ **不做「日志条目 ↔ 提交」的逐条映射**：条目是中文一句话、与提交无链接，靠关键词猜匹配
只会制造比它能发现的更多的误判。计数不等式是能确定性成立的那部分，剩下的判断交给人。

用法：`python3 {{AIDP_HOME}}/scripts/check_changelog_fix_scope.py [--version V0.14.0] [--since-tag v0.13.0] [--json]`，
退出码 `0` 通过/不适用、`3` 有 Important（**⛔ 不阻断发布**）、`2` 入参错。
豁免 `<!-- changelog-scope-ignore: 理由 -->`。编排落点 = `/version` Step 3.3.5（`flows/version/release-2.md`）。
自检不走 `selfcheck.py`（克隆树无 `.git` 恒判不适用），由 `tests/test_guard_scripts.py::test_changelog_fix_scope`
用 `git init` 夹具做完整阳性/阴性对照。

---

## autopilot_reset.py — `--reset-*` 旗标的唯一执行者

`--reset-baseline` / `--reset-unattended`
在 `/sprint-autopilot` 参数表里有定义、被冻结 #4 里程碑通知写成"人工恢复动作"（`--reset-baseline`
更被 `invariants.md` 称作某类冻结的**唯一出路**），却长期**没有任何实现**——`BOOL_FLAGS`
一个都没登记，全仓也搜不到对应变量。净效果是：用户被通知指引着去跑一个什么都不做的参数。

本脚本把它们落地，接在 Phase 0.1 的**最前面**（它们要改/删的正是 baseline，必须先于任何读取）。

```bash
python3 {{AIDP_HOME}}/scripts/autopilot_reset.py --arguments="$ARGUMENTS"; rc=$?
# rc: 0=未命中任何 reset（继续正常流程） / 10=已重置且应结束本 tick（--reset-baseline）
#     11=已重置、继续本 tick（--reset-unattended） / 2=执行出错
```

- `--reset-baseline` **整份删除**文件、不是清空成 `{}`：留一个空壳会让各处「baseline 不存在」
  的早退分支失效，反而进入一堆读空值的路径。


## autopilot_fail_handle.py — 「失败处置」五步一次做完

两条链路的失败处置是**五步固定动作**：`bump <streak>` → 判阈 → 达阈写冻结四件套
+ 顶层 `aiauto_blocked_reason` → 发 #4 + 写本地告警台账 → 让位。十余处引用点逐处手抄时稳定漏三样：

- **只写「走「失败处置」流程」一句散文、没有 `bump`** → 那几类失败**永远累不到阈值**，
  不会按可自动解冻的 reason 冻结，只能等通用 stuck 熔断冻成人工专属的 `stuck-phase`；
- **写了四件套但没发 #4** → 冻结只存在于 baseline，通知渠道零消息（停得住、停不响）——故冻结时**恒写**本地告警台账 `memory/.aidp/alerts.jsonl` + stderr，无通知渠道时同样可见；
- **无唤醒源时阈值恒不可达** → `--once` / 无 `/loop` 的轮次没有下一 tick 叠 streak。

收进一个调用后，这三样在结构上不可能再单独发生。

```bash
python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --version "$V" --command autopilot|aiauto-test --phase <游标> \
  --reason <freeze_reason 枚举> --why "<真因>" [--build "$BUILD"] \
  [--streak-key dev_fail_streak] [--threshold 3] [--freeze-now] [--extra K=V] [--no-card] [--card-on-streak] [--json]
```

`--command` 决定唤醒源键与前置熔断计数键（测试链路必须传 `aiauto-test`，否则会误读开发链路的唤醒源）；`--preflight` 为无版本号的前置熔断模式。
同版本同 reason 已冻结 → no-op（不刷新冻结时刻、不重发 #4）；未达阈默认不发通知（`--card-on-streak` 显式开启）。

`--reason` 的合法集**直接调 `check_freeze_contract._parse_enum`**（同一信源，⛔ 不另写一份）。
退出码：**0 = 已记账让位本 tick / 3 = 已冻结（达阈或无唤醒源）/ 2 = 入参错，此时什么都没写**
——⛔ 别把 2 当成"处置过了"。

## check_memory_loss.py — memory 整段被吞（与写前快照比，缺省与 git HEAD 比）

`memory/` 下的项目级长期记忆（`projectBrief` / `productContext` / `systemPatterns` /
`techContext` / `databaseBaseline`）**相当一部分由人手写，且往往是仓库里唯一一份记录**——
覆盖即永久丢失。确定性防线靠本脚本：与比对基线比 **L1 段落消失 / L2 段落塌缩 ≥40% / L3 整份塌缩**，任一命中 exit 1。
受保护面另含 `memory/V*/*/{activeContext,progress}.md`。
**比对基线优先取写前快照**：写入前调 `--snapshot`，把受保护文件的工作区现状存到 `memory/.aidp/memory-snapshot/`（未提交的手写内容同样受保护）；检查通过后自动清掉快照（`--keep-snapshot` 保留），报红时保留快照供取回被吞段落。无快照时回落 `git HEAD`。

⛔ **填 `（待填充）` 占位符不算丢失**——那正是约定 8 强制要求的动作，按标题**前缀**匹配，
误伤这一条等于用一道门去阻止另一条约定要求做的事。

调用方：`/memory-sync` Step 0 写前快照 + Step 3 收尾（硬门，exit 1）+ `verify.py`（WARN，只要可见）。
`--file` 可显式指定扫描面。

**非 Git 且无快照 = 不适用**（退出码 `3`，`N/A(vcs-disabled)`）：本门是差分门，没有基线就没有"丢了什么"可言。
Git 能力判定的**单一信源**是 `vcs.py::detect_mode`（`git` / `none`），⛔ 本脚本不另写一套探测（两套探测迟早给出不同答案，而"谁说了算"没有信源）。
⚠️ 判据是"非 Git **且**连快照都没有"——非 Git 项目跑过 `--snapshot` 后基线照样成立、门照常判红，故 **N/A ⛔ 不是"非 Git 就免检"的总开关**。
`--json` 下给 `applicable=false` / `reason="vcs-disabled"` / `level="INFO"`、`errors` 为空，且**刻意不给 `passed`**：写 `true` 是假绿（memory 覆盖即永久丢失、其实一次都没查过），写 `false` 是假红，「没查过」必须与两者可区分。（适用时照常给 `applicable=true` + `passed`，字段两路对称。）

## check_index_staleness.py — 内容变了但 `git status` 报 clean

git 判"改没改"走 **stat 快速路径**：index 记的 `(size, mtime)` 与磁盘一致就不重新哈希。
写入器若保留了源文件 mtime（`shutil.copy2` 就是），会出现**磁盘内容 ≠ index 记录、而
`git status` / `git diff` 双双报 clean** 的状态。它比"忘了提交"严重得多：
**所有基于工作区的检查会一起假绿**——`mirror --check` 绿、`verify.py` 绿，而从 HEAD
重新克隆一份立刻一堆「脚手架副本漂移」ERROR，`CONTRACT_MANIFEST.json` 记的还是未提交内容的指纹，
于是每个下游初始化后天生带一批清不掉的契约漂移 WARN。

判据：index blob ≠ `git hash-object <文件>` **且** `git status` 没列出它 → ERROR。
正常的未提交改动（status 看得见）**不报**。扫描面默认取**当前运行根**（`DEFAULT_PATHS` 经 `aidp_runtime.runtime_relpath` 派生：模板仓库是维护源目录、下游是 `.claude` 或 `.agents`）。

根因已修（`mirror_to_bundle.py` 改 `write_bytes`，见 `_copy_content`），本脚本是**防复发兜底**。

**非 Git 项目 = 不适用**（退出码 `3`，`N/A(vcs-disabled)`）：没有 index 就没有"index 与磁盘分叉"这回事，一个字节都没法比。
能力判定同走 `vcs.py::detect_mode` 这一个信源。`--json` 下给 `applicable=false` / `reason="vcs-disabled"` / `level="INFO"`、`errors` 为空、**不给 `passed`**。（适用时给 `applicable=true` + `passed`，字段两路对称。）
⛔ 既不能记成 pass（假绿），也不该落进 WARN 区——非 Git 项目会为此恒挂一条永远消不掉的警告，几轮之后所有人开始整体无视 WARN。

## check_release_ask_whitelist.py — 发布路径 AskUserQuestion 的白名单归属门

`release-1.md` 早有两道明文禁令（交互式发布 = 全量执行 / 点名禁止的高频误判暂停理由），
下游实测**全被绕过**：执行体自发弹「补完凭据后按什么顺序走？」，自辩措辞恰好就是被点名的那条。

根因是**判据形状**：白名单是**允许清单**（哪些可以问），缺**反向判据**（怎么知道自己正在违规）。
在「我这是负责任地提示风险」的框架下，执行体不会主动去比对允许清单。

判据：发布路径每处 `AskUserQuestion` 提及，其 ±6 行窗口内须出现白名单归属锚点，否则 ERROR。
⛔ 本门只能查**文档里写死的问询点**，查不了运行时自发的那一次——那一次由 `release-1.md` 的
「`AskUserQuestion` 前置自检」条款约束（每次调用前先指名是白名单哪一项，指不出即违规）。
本门保证的是**契约文本自己不再长出无归属的问询点**。

用法：`python3 {{AIDP_HOME}}/scripts/check_release_ask_whitelist.py [--json]`，退出码 `0`/`1`/`2`。
豁免 `<!-- ask-whitelist: ignore 理由 -->`（描述下游命令行为的提及用它标注）。

---

## check_yield_guard.py — 让位前必须确认有下一 tick

无人值守里有一类退出叫 **yield**：本 tick 干不完、让位给下一 tick。它成立的前提只有一个——
**真的会有下一 tick**，判据就是 `HAS_WAKE_SOURCE`。但派生 ≠ 消费：
`--once --unattended`（autopilot 的补测与自愈交接反向 invoke 都走这条）满足 `LOOP_UNATTENDED=1`
却**没有下一 tick**，而各 yield 点只判 `LOOP_UNATTENDED` → 直接 exit → 测试半途而废，
**且无任何结构级拦截**（Stop hook 只读 autopilot 的 run_state，测试链路根本不写）。
调用方拿到 `tested:false` 降级静态-only 收尾——用户以为跑了全链路实测，拿到的是静态结论。

判据：**围栏内**的 `exit 0 … 让位` 站点，同一围栏内须出现 `HAS_WAKE_SOURCE` 守卫
（⛔ 检查面是围栏、不是行窗口：shell state 不跨 Bash 调用，守卫不在同一围栏就不生效）。
⚠️ 本门分不清「让位等下一 tick」与「已冻结的终态退出」（后者本就该退），
故现存站点一律登记为 `KNOWN_OPEN`**待人工判定**、只报不阻断；**新增站点即 ERROR**。
⛔ `KNOWN_OPEN` 只能变短，别往里加新条目。

用法：`python3 {{AIDP_HOME}}/scripts/check_yield_guard.py [--json]`，退出码 `0`/`1`/`2`。
豁免 `<!-- yield-guard: ignore 理由 -->`。

---

## scripts_usage.py — 脚本调用速查（现场问 `--help`，永不过期）

`{{AIDP_HOME}}/scripts/` 与各 SKILL `scripts/` 下有上百个脚本，**CLI 形态互不统一**——实测同一轮里
踩到四种：位置子命令（`check_sprint_numbering.py check`）、`--paths <路径>`、单个位置路径、
三个位置参数。子 Agent 每次都要试错 1~2 次才跑对，失败信息还是 argparse 原文、不指向正确用法。

**为什么不做统一或手写速查表**：统一 CLI 会破坏既有调用，且各 SKILL 脚本各自演进；手写速查表必然过期——那是又一处"加东西的人不会想起去改"的副本。故做成**现场生成**。

用法：`python3 {{AIDP_HOME}}/scripts/scripts_usage.py [名字片段] [--root <仓库根>] [--json]`，退出码恒 `0`。

## check_doc_numbering.py — 结构性文档编号连续性 / 唯一性（确定性）

约定 35「批量替换与切片编辑」的机器门。扫 `{{AIDP_HOME}}/{commands,agents,flows,reference,rules,templates}`
+ `docs/init` + 根级 `.md`，识别三类编号序列（标题编号 / 有序列表 / 加粗编号条目）。

**严重度按种类分档（口径经全仓实测校准，勿一刀切）**：
- **列表类重号 = ERROR** —— 一份清单里出现两个「3.」没有正当场景，是切片替换吞并条目的确定性痕迹；
- **标题同号 = WARN** —— 本范式里 `## 约定 23` 与 `## 约定 23 姊妹条`、rationale 里从两个角度各写一节
  `## Step 3.4.2` 都是正当写法；`rationale.md`/`invariants.md`/`README.md`/`usage-guard.md` 这类叙述型文件整体不判；
- **标题跳号一律不报** —— 「已退役的编号不再复用」是明文规则，报出来 100% 是噪音。

豁免：受检行或其上一行 `<!-- numbering-ignore: 理由 -->`；整文件 `<!-- numbering-ignore-file: 理由 -->`（理由必填）。
退出码 0/1/2；`--strict` 下 WARN 也计入。已挂进 `verify.py::check_doc_numbering`（只上浮列表类重号）。

## selfcheck.py — 契约检查脚本的阳性对照自检骨架

约定 35 的落点：`{{AIDP_HOME}}/scripts/check_*.py` **每个都支持 `--self-check`**，全量跑 `python3 {{AIDP_HOME}}/scripts/selfcheck.py`。

**探针形态 = 克隆真实契约树 + 注入**，不是手搓最小 fixture——手搓 fixture 写少一层目录，
检查器就扫不到探针、返回 0 命中，而这**与"检查器坏了"完全同形**，自检自己先假绿。
种子复制一次，每个探针的工作副本用 `cp -al` 硬链接分发，注入时先 `os.remove` 再写（断开硬链接、不回写种子）。

**双侧对照**：阳性（注入后必须报红）+ 阴性（未注入不得红）。只跑阳性证明得了"能红"、证明不了"不是恒红"。

**覆盖缺口刻意可见**：未登记探针的记 `unregistered`、需 git/多版本夹具无法登记的记 `unsupported` 并**写明原因**，
两者都在摘要里点名、但不计失败——⛔ 不许静默当成"全都自检过了"。

---

## aidp_paths.py — AIDP 运行时产物的路径单一信源

登记每个运行时/配置产物的路径、性质（人维护 / 运行时状态 / 运行时日志）与入库策略，
并提供 `inventory()` 供体检遍历。落点分三类：`memory/aidp-config.yaml`（人写·入库）、
`memory/.sprint-autopilot-baseline.json`（程序写·入库）、`memory/.aidp/`（程序写·本地：锁 `locks/`、日志 `logs/`、
通知台账、Stop 护栏计数、**本地告警台账 `alerts.jsonl`**）。
`append_alert(root, **fields)` 追加一条告警到 `memory/.aidp/alerts.jsonl` 并在 stderr 打印 `🚨 [AIDP-ALERT]`——
无人值守下所有冻结 / 告警都经它落本地，不依赖通知渠道是否配置。

`--check-vcs` 断言**登记的入库策略与 `git check-ignore` 的事实一致** ——
这张表存在的理由就是让人分得清「哪个我能动」，标错等于把清单变成误导源，
而标错与标对在输出上完全同形。

## aidp_config.py — 人维护配置（`memory/aidp-config.yaml`）

项目标识（`project.name` 英文应用编码 / `project.name_cn` 中文名称）/ 提交前门禁（`commit_gate.enabled`）/ 里程碑通知（`notify.enabled` / `fallback` / `channels`）/ CICD（`cicd.provider` / `auto_trigger` / `max_retries` / `pipelines`）/ 7×24 调度（`scheduler.agent` / `dev_interval` / `test_interval` / `stale_cycles` / `exec`）/ Stop 护栏开关、脚手架版本戳、autopilot 决策兜底。
读取 API：`project_config()` / `commit_gate_enabled()` / `notify_config()` / `cicd_config()` / `scheduler_config()` / `stop_guard_enabled()` / `scaffold_version()` / `scaffold_pending()` / `is_downstream()`；单行流式写法（`- {type: feishu, webhook_env: …}`、`pipelines: {dev: deploy-dev.yml}`）解析时展开。
写入是**逐行外科手术**而非重新序列化 —— 这份文件一半的价值在注释（每个开关旁写着
关掉之后会发生什么），`yaml.dump()` 一次就把它退化成无注释的 json。
读取顺序恒为「本文件 → 内置缺省」。

## autopilot_decisions_merge.py — PRD frontmatter × 兜底配置的决策合并

权威是本版 PRD 的 `autopilot_decisions` 段，`memory/aidp-config.yaml` 的同名段只在
PRD 未声明时兜底。挑兜底文件的判据是「**有没有声明**」而非「文件在不在」——
脚手架会给每个下游建出 `aidp-config.yaml`（该段初值为空），只按存在性挑会在升级当天
把下游真实决策静默换成空。

## baseline_archive.py — baseline 历史版本节点归档

把已发布版本的节点搬进 `memory/.aidp-baseline-archive/baseline-{version}.json`（落点单一信源 = `baseline_edit.py::ARCHIVE_DIRNAME`），控制 baseline 体积。
用法：`python3 {{AIDP_HOME}}/scripts/baseline_archive.py [--baseline <path>] [--root <仓库根>] [--keep N（默认 2，保留最近 N 个已发布版本节点）] [--no-require-tag] [--dry-run] [--json]`。
⚠️ **预演开关是 `--dry-run`，不是 `--json`**——`--json` 只切输出格式、照常写盘。

## check_comment_ratio.py — 约定 17 反向门（注释写太多同样是缺陷）

**只判「声明之外的注释」**：约定 17 本就要求给类/接口/方法/字段逐个写文档，
故「短注释块 + 紧随声明」先从分子里扣除，剩余注释/代码行数比 > 1.0 且未命中 A 档特征
→ Important（不阻断）。A 档与 JSDoc 契约型注释整档豁免，`comment-ratio-ignore: <原因>`
可就地豁免。由 `/sprint-dev` Phase 1 Step 7bis 调用。

## check_release_residual_gate.py — 零残留断言发布总闸

发布前把「轮次收尾验证任务」登记表全跑一次，**不接受任何 `skipped`**：
Sprint 内按守护面裁剪是合法的，发布前必须全跑一次，否则整张表在测试期与发布期
都没有消费入口。在役行必须是当日实跑的 `0 命中(YYYY-MM-DD)`。

## check_release_debt_landing.py — 发布期失败兜底必须落账

扫 `flows/version/release-*.md`，找 `check_*.py … ||` 的失败兜底块里有没有写
`发布欠账.md`（或调 `release_debt.py`）。只喊话的兜底，其欠账在产物上与「本步通过」
完全同形 —— 发布报告与 `--finalize-docs` 都读不到它。由 `verify.py` 上浮为 ERROR。

## release_debt.py — 发布期欠账台账的唯一读写入口

`docs/audit/{version}/发布欠账.md` 的唯一读写入口，格式由脚本保证（Step 3.6 发布报告与 `--finalize-docs` 都按格式解析这张台账；调用点各写一段 `echo >>` 时格式必然分叉、未决条数数不准、补跑后也无字段可勾销）。

| 子命令 | 作用 |
|---|---|
| `add --version V --step S --title T [--locate L] [--impact I] [--redo R] [--level Important\|Critical\|Minor] [--note N]` | 登记（幂等：同一 step+title 仍未决只刷新时间戳；已勾销后再失败新增一条） |
| `resolve --version V --step S [--title T]` | 补跑成功后把未决条目改为 ✅ 已补齐（日期） |
| `list --version V [--open] [--json]` | 列出条目（Step 3.6 顶部欠账块 / 补跑短路开场读它） |
| `gate --version V [--no-tag] [--register-missing] [--json]` | 终态落账门（Step 3.4.1 提交前）：关键产物「存在，或台账里有该步未决条目」，二者皆无 → exit 1；`--register-missing` 当场补登记 |

不带子命令直接给 `--version --step --title` 视为 `add`。`--self-check` 自测。退出码：`0` 成功 / `1` gate 发现未落账的跳过 / `2` 用法错。

## check_code_symbol_refs.py — 文档里 `脚本.py::符号` 引用的存在性（确定性，**ERROR 级**）

契约文档用 `scaffold_lib.py::skeleton_dirs` 这种写法把「单一信源」指到具体函数；函数改名、挪文件后指针全部悬空，链接 / 锚点检查查不到反引号里的符号。
判据：扫全仓 `.md` / `.py` / `.sh` / `.js` / `.json` / `.yaml`（排除 `assets/`）里的 `name.py::symbol`（也认 `.sh` / `.js`）：文件按文件名找（同名多份取并集），找不到 → `missing-file`；符号须是 `.py` 的模块级 `def` / `class` / 赋值、类内方法、字典字符串键或登记表元组首元素（如 `verify.py::GUARDS` 的检查名），`.sh` / `.js` 的函数或变量 → 否则 `missing-symbol`。`A.b` 形态同时校验方法 `b`。占位文件名（`x.py` / `name.py` 等）不校验。
豁免：行内 `symbol-ref-ignore: <原因>`。用法：`python3 {{AIDP_HOME}}/scripts/check_code_symbol_refs.py [--root <仓库根>] [--path <相对路径>] [--json]`；`--self-check`。退出码：`0`=全部可解析 / `1`=有悬空引用 / `2`=用法错。CI 必跑。

## check_cli_invocation.py — 文档里的子命令与 flag 必须属于被调用的那个脚本（确定性，**ERROR 级**）

`check_ghost_flags.py` 只查 flag 在全仓有没有定义，查不到「它是不是这个脚本的 flag」（`agent_env.py sync` 这类写法全局检查放行，照抄即 argparse 报错）。
判据：扫 `.md` 里的 `python3 <路径>.py …` 调用（代码块与行内代码都算，`\` 续行拼接，`[--flag X]` 可选写法与 `--a|--b` 并列写法照常判定）：① 路径含占位（`<SKILL_DIR>` 等）时按文件名找，优先与文档同属一个 SKILL 的那份；`{{AIDP_HOME}}/` 下写死的路径不存在 → `missing-script`；② 每个 `--flag` 必须是目标脚本（及同目录被 import 的模块）源码里的字符串常量或可被 argparse 缩写唯一匹配 → 否则 `unknown-flag`；③ 目标脚本有 `add_subparsers` 时，紧跟路径的首个非 flag 词须是 `add_parser` 名，首个位置参数声明了 `choices` 时须落在其内 → 否则 `unknown-subcommand`；④ 非 argparse 脚本被传 flag → WARN `non-argparse`。
豁免：行内 `cli-check: ignore <原因>`。用法：`python3 {{AIDP_HOME}}/scripts/check_cli_invocation.py [--root <仓库根>] [--path <相对路径>] [--json]`；`--self-check`。退出码：`0`=无 ERROR / `1`=有 ERROR / `2`=用法错。CI 必跑。

## check_version_audit_landed.py — 版本规划产物审计「真的跑过」（确定性，**ERROR 级**）

`/version` Step 2.4.7 的独立审计是「规划产物经审计才算数」的唯一承载者（PRD 条目去处 = 审计 C/C-4、原型覆盖度 = 审计 F，都是 Critical 硬门），而**「跑了且通过」与「压根没跑」在终端上长得一模一样**——散文管不住这种形态：`docs/audit/{version}/` 为空、没有任何 flag、命令照样往下走。本门把它变成可判定的。
判据只做**存在性 + 非空壳**，⛔ 不碰审计结论（pass/warn/block 是审计自己的事）：`docs/audit/{version}/version-output-audit-*.md` 至少一份（fresh 与 `-补丁-NN` 两种命名都认），且报告须命中八项审计标记中的 ≥5 项 + 含结论字样 + ≥512B，否则判空壳。
**适用范围**：该版本有规划产物（`docs/{requirements,design/detail,plans,testing}/{version}/` 任一含 `.md`）才判；一个都没有 = Step 2.4 还没跑完，报「审计缺失」会指错方向 → N/A 跳过。
**唯一豁免** = `--skip-audit`（对应用户显式给 `/version` 传的同名旗标）：退出 0，但恒打印 `audit-skipped-by-flag`，供 Step 2.8 报告如实登记「本次未经审计」，⛔ 不得写成「审计通过」。
调用方 = `{{AIDP_HOME}}/flows/version/planning-8.md` Step 2.5.0。用法：`python3 {{AIDP_HOME}}/scripts/check_version_audit_landed.py --version <V> [--root <仓库根>] [--skip-audit] [--json]`；`--self-check`。退出码：`0`=已落地 / 豁免 / N/A；`1`=缺失或空壳；`2`=用法错。

## check_runtime_paths.py — 下发运行路径抽象守卫（确定性，**ERROR 级**）

扫描下发运行契约真源，拒绝**硬编码的旧运行根**（迁移语义之外一律须写成 `{{AIDP_HOME}}/`）；同时拒绝**降层前的嵌套形态**（运行根下再套一层 `aidp/` 中间目录，判为 `stale-nested-runtime-path`）——后者的扫描面除契约目录外还含**下发文档面**（`docs/init/`、`memory/README.md`、脚手架 `SKILL.md` 与其 `references/`），因为那批文件同样逐字下发、写错就把下游引到一个安装后不存在的目录。加 `--rendered` 时另拒未解析 `{{AIDP_HOME}}`。排除脚手架自身、模板测试与维护 baseline。用法：`python3 {{AIDP_HOME}}/scripts/check_runtime_paths.py [--root <仓库根>] [--path <相对路径>] [--rendered] [--json]`；`--self-check`。退出码：`0`=无命中 / `1`=有命中 / `2`=用法错。CI 必跑。  <!-- runtime-path-ignore: 说明检查器自身的判据，必须逐字写出被拒的形态 -->

## check_private_markers.py — 开源模板里的私有环境痕迹（确定性，**ERROR 级**）

模板仓库公开分发，示例、事故叙述、占位值最容易夹带真实环境信息。本脚本**只按模式识别、不内置任何真实私有名单**（名单写进仓库等于再泄露一次）。
判据：P1 RFC 1918 / CGNAT / 链路本地 IPv4（示例一律用 RFC 5737 文档地址段 `192.0.2.x` / `198.51.100.x` / `203.0.113.x`）· P2 URL 或 `host:port` 中以 `.local` `.lan` `.internal` `.intranet` `.intra` `.corp` `.localdomain` 结尾的主机 · P3 非占位、非公共服务（`chrome-devtools*` / `chrome-<用户>` / `context7` 等）的 `mcp__<名字>__` · P4 事故叙述里点名下游项目（「下游 `xxx` 实测/实证/事故…」）· P5 前缀不在示例白名单的 `<前缀>-backend` / `<前缀>-frontend` · P6 `--denylist <本地文件>`（不入库，也可用环境变量 `AIDP_PRIVATE_DENYLIST`）逐行子串匹配。扫描面含脚手架 bundle。
豁免：行内 `private-marker-ignore: <原因>`。用法：`python3 {{AIDP_HOME}}/scripts/check_private_markers.py [--root <仓库根>] [--path <相对路径>] [--denylist <文件>] [--json]`；`--self-check`。退出码：`0`=无命中 / `1`=有命中 / `2`=用法错。CI 必跑（模板仓库专用，不挂进 `verify.py`：下游项目自己的内网地址是合法内容）。
