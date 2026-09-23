# sprint-autopilot · Phase 0 详情分片 [8/11]（0.5.5 测试方案预检 + 0.6 字段缺失收集铁律）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 8/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.5.5（测试方案 AI 自动化预检）+ 0.6（字段缺失统一 Phase 0 收集铁律）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-8.md`。理据见同目录 `rationale.md`。

---

### 0.5.5 ★ 测试方案 AI 自动化预检（提前补全 chrome-devtools-mcp 测试信息 + 安装预检）

> 衔接 0.6 的"一次性收集"理念：在 Phase 0 就把**下版（开发版本）** chrome-devtools-mcp 浏览器自动化测试所需信息补齐，让后续 `/sprint-aiauto-test`（`/loop 5m`）直接可跑，**不在测试阶段才中途找用户要**。

对**下版 `TARGET_VERSION`** 运行「测试方案 AI 自动化预检」（**逻辑单一信源 = `/sprint-aiauto-test` Phase 0.0.6**，命令端不复写）：

1. 定位下版测试环境与账号配置（独立成文 `研发自测/01_测试环境与账号.md` 或内嵌方案章节，按 `/sprint-aiauto-test` Phase 0.0.6 内容标记定位，不写死文件名）
2. **前端 web 项目** 且 **缺 chrome-devtools-mcp 段** → 调 `/sprint-selftest` Step 3 模板自动补全该段（含安装 / 本地+远程启动 / 端口转发 / 验证命令）
3. 核验 chrome-devtools-mcp 正式使用所需信息：① 测试环境访问地址 ② 测试账号密码 ③ 是否跨设备（Claude Code 与 Chrome 同机？）④ 跨设备时远程 Chrome 的 IP + 端口
4. 缺任一项 → **交互式**：在 Phase 0（现在）一次性 `AskUserQuestion` 收集 + 告知用户安装命令 / 远程端口转发命令 / 先配 mcp 文件后启动的铁律 + Write 写回测试方案 + commit；**`/loop` 无人值守**（`ENTRY_MODE` 由 /loop 触发）→ **不弹窗**，按缺失项标 `{待用户填写}` 延后交测试链路（与 0.6 无人值守铁律、Phase 3.2.1 Step D「测试账号占位 → needs_human 降级」口径一致），绝不在此挂起

- `--strict-prd` 模式下缺信息 → 同 deployment 字段，记入缺失清单一并退出（不中途问）
- **非前端 web 项目** / `deployment.mode=none` → 跳过本预检
- 与 0.5/0.6 的关系：0.5/0.6 收 PRD `deployment` 部署配置；本步收**测试方案 chrome-devtools-mcp 段 + 连接/账号信息**，两者互补不重复，但**同属"Phase 0 一次性收齐、禁止中途阻塞"铁律**

> ★ **本步只补"测试方案的 chrome-mcp 段 + 连接/账号"，不校验"测试用例是否存在"**：测试用例（研发自测用例）由 **Phase 3.1 `/version` 规划阶段**经 Step 2.4.3.5 `/sprint-selftest` 调 `dev-manual-testcase` SKILL 生成——规划尚未跑时用例本就不存在，故 Phase 0 不设"用例存在性"门（否则与"规划阶段才产出用例"自相矛盾）。用例的实际存在性 + 来源优先级（测试人员正式用例为主 / 研发自测查漏为补）由 `/sprint-aiauto-test` Phase 2.0 在测试链路统一判定，命令端不前移、不复算。

> 🔧 **chrome-devtools-mcp 安装预检（测试方案声明用 chrome-mcp 时执行，不阻塞开发链路）**：当下版**测试方案明确使用 chrome-devtools-mcp**（`autopilot_decisions.test_strategy=chrome-mcp`，即前端 web 项目走浏览器实测）时，本步**核验驱动就绪**——**委派 `python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py check-cli --json`**（检测单一信源，两命令共用；★ 它探**真实 cli 命令 `chrome-devtools`**（非 `chrome-devtools-cli`——那只是技能名）+ 四独立信号 `CLI_OK/NPM_PKG_OK/CHROME_BIN_OK/REMOTE`，**不再把"npm 包在"当"cli 可用"等价**，正是本次下游"包在但探错名 → 误判 cli 不可用 → 静默降级 MCP"的根因修复）：
>   - ✅ 已安装 → 仅记一行 INFO，继续。
>   - ❌ 未安装 → **就地打印安装引导**（让用户在挂 `/loop 5m /sprint-aiauto-test --unattended` 前装好，否则测试链路会卡在其 Phase 0.1 安装门）：
>     ```
>     ⚠️ 测试方案声明使用 chrome-devtools-mcp，但未检测到该工具 —— 请安装：
>        # 全局安装（含本地 CLI chrome-devtools-cli + 远程 MCP 服务）
>        npm i chrome-devtools-mcp@latest -g
>        # 仅远程路径需注册（本地 CLI 免注册、免重启）；服务名强制 chrome-<git 用户名>、强制项目级作用域
>        claude mcp add "chrome-$(git config user.name)" --scope project chrome-devtools-mcp
>        # ★ 远程注册后必须重启 Claude Code 才会加载新 MCP tool（完整引导见 /sprint-aiauto-test Phase 0.1）
>     ```
>   - **不阻塞开发主流程**：autopilot 不实际连 chrome，开发链路（Phase 2/3）照常继续；正式的工具检测 + 自启 + 远端引导仍由 `/sprint-aiauto-test` Phase 0.1 承担。`test_strategy=static-only` / 非前端 web → 跳过本预检。

> 🔭 **chrome 驱动前置预判（dev 前就把"测试能否连上 / 要不要重启"摆出来，绝不留到开发完才提醒；不阻塞开发）**：上面插件预检之后**紧接着**做一次**只读、零连接**的驱动预判（检测单一信源 = `chrome-mcp-doctor.py check-cli`，命令端不复算），把它返回的 `category` 写 baseline `chrome_preflight` 并**就地打印一行预判**，让用户在长链路开始**前**就知道测试阶段会怎么走：
>   - check-cli 探四独立信号 + 远程是否**强制**（测试方案「二·连接模式」显式"远程" / 用户本轮显式要求远程）+ 远程 MCP 是否**已加载**（`ToolSearch` 查 `mcp__chrome-{git_user}__*`）。
>   - 据此**预判测试阶段走向并打印**（★ 五类，仅告知不连接；`category` 直接取 check-cli 输出）：
>     - **本机 cli 可用**（`CLI_OK && CHROME_BIN_OK`）→ `🔭 测试将走本机 CLI（chrome-devtools 命令，免 MCP、免重启）——无需任何操作`。`chrome_preflight=local-cli-ready`。
>     - **远程 MCP 已加载** → `🔭 远程 chrome MCP 已就绪，测试将走远程`。`chrome_preflight=remote-ready`。
>     - **远程未加载（需重启）但本机可兜底** → `⚠️ 远程 chrome MCP 未加载（需重启 Claude Code 才生效）；本机有 chrome → 测试阶段会按 /sprint-aiauto-test B0 处理（交互式给你 3 分钟重启窗口，超时/无人值守自动切本机无头 cli 兜底）。开发现在照常进行`。`chrome_preflight=needs-restart-has-fallback`。
>     - **★ 本机有 chrome、cli 不可用、远程不可用**（`CHROME_BIN_OK && !CLI_OK && 远程不可用`，check-cli 判 `local-chrome-no-cli`）→ `⚠️ 本机 cli 命令 chrome-devtools 不可用（多半 npm 全局 bin 未在 PATH，见 check-cli 诊断）→ 测试阶段先按 check-cli 修 PATH/装包回落 cli；短期修不了则降级 mcp-plugin-fallback（同插件 MCP 协议、须显式声明 driver）继续测、不阻塞`。`chrome_preflight=local-chrome-no-cli`。**照常委派测试链路**（不终止；plugin-fallback 由 /sprint-aiauto-test 承担、须把 driver 如实填 `mcp-plugin-fallback`）。
>     - **⛔ 远程未加载（需重启）+ 本机无 chrome 可兜底（极端）** → `⛔ 远程 chrome MCP 需重启且本机无 chrome 兜底 → 本会话内无法执行浏览器测试`。`chrome_preflight=blocked-no-fallback`。**按用户既定策略：开发照常进行，开发完成后经里程碑通知（#4）告知原因再退出，绝不在 dev 前/后空等重启**（落地见 Phase 3 末段「chrome_preflight=blocked-no-fallback 终止处理」，含安装命令）。**★ 现在就一并提示彻底解法**（趁开发这几分钟装好、dev 完成即可走本机无头 cli 兜底、无需重启）——在 **运行 Claude Code 的这台设备** 装 Chrome 浏览器 + chrome-devtools-mcp 并**原样打印安装命令**：`npm i chrome-devtools-mcp@latest -g`（npm 全局包自带 chrome-devtools-cli；本机无头 cli 免 MCP 注册、免重启；Chrome 无 GUI 也能跑无头）。
>   - ⛔ **本预判只读不连、绝不阻塞开发**：五类结果**都不拦 Phase 2/3**，开发链路照常跑；预判仅用于"提前告知 + 为极端类标记终止策略"。`test_strategy=static-only` / 非前端 web → 跳过本预判。

>   - **★ 两项判定必须【落盘】**（不落盘 = 零写入者 → 0.7 钢门读回恒空：
>     `chrome_preflight` 恒取默认 `local-cli-ready` ⇒ `blocked-no-fallback` 终止策略永不触发；
>     `test_strategy` 恒空 ⇒ `mcp_chrome` 永不进必需项 REQ。两处校验形同虚设）：
>
> ```bash
> eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"   # 取回 TARGET_VERSION（分片间 shell 变量不持久）
> # chrome_preflight：值域直接取 check-cli 的 category（与上面五类一一对应）
> CAT=$(python3 {{AIDP_HOME}}/scripts/chrome-mcp-doctor.py check-cli --json 2>/dev/null \
>       | awk '/^\{/,0' | python3 -c "import json,sys;print(json.load(sys.stdin).get('category',''))" 2>/dev/null)
> [ -n "$CAT" ] && python3 {{AIDP_HOME}}/scripts/baseline_edit.py set chrome_preflight "$CAT"
> # test_strategy：真源在 PRD autopilot_decisions；PRD 大目录取 baseline prd_root（可被项目覆盖）
> # ⛔ 检索面必须限定到**本轮目标版本**：对整个 prd_root 递归 grep + head -1 会按文件系统序
> #    取到**别的版本**的值（多版本共存是常态），而写入的又是 baseline **顶层**键 —— 于是
> #    「上一版写 static-only、本版要 chrome-mcp」会让 0.7 钢门的 chrome 必需项恒假、
> #    0.5.5 的 chrome 预检整段按 static-only 跳过，直到测试链路才发现驱动没装。
> PRD_ROOT=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get prd_root --default "docs/requirements")
> TS=$(grep -rhoE '^[[:space:]]*test_strategy:[[:space:]]*[a-z-]+' \
>        "$PRD_ROOT/$TARGET_VERSION" 2>/dev/null | head -1 | sed 's/.*:[[:space:]]*//')
> [ -n "$TS" ] && python3 {{AIDP_HOME}}/scripts/baseline_edit.py set test_strategy "$TS"
> ```

### 0.6 字段缺失统一在 Phase 0 收集（★ 铁律：禁止执行主流程（Phase 2/3）中途阻塞）

★ **核心原则**：所有"可能中途阻塞执行主流程（Phase 2/3）"的决策必须在 Phase 0 全部收齐。绝不允许命令跑到 Phase 3.2 才弹 `AskUserQuestion` 问"你的部署 URL 是什么"——长时间运行被半路打断对 7×24 是致命缺陷。

★ **零交互覆盖清单（不只"字段缺失"，连"自动判定 / 自动降级"也算 Phase 0 责任）**：以下**会中途阻塞**的决策全部前置为 Phase 0 自动判定或自动降级，**主流程（Phase 2/3）中途一律不得再就它们弹 `AskUserQuestion`**（前置为 Phase 0 一次性决策，不是禁止交互式在 Phase 0 问）——① **ENTRY_MODE**：`--skip-dev` → `test-only`（显式、零交互）；`full`↔`incremental` 由 3.1.0 `PLANNING_DONE` 硬判据自动裁定（非弹窗）；**唯一需交互的是"命中 test-intent 关键词但未带 `--skip-dev`"这一裁剪歧义** → **属 Phase 0 必问白名单**：**交互式在 Phase 0 `AskUserQuestion` 问「全流程 / 仅测试」（P0-0，不再"绝不弹窗自动判 test-only"）、`/loop` 无人值守保守默认 full 不弹窗**；② **远程 chrome 不可达**由测试链路 `/sprint-aiauto-test` Phase 0.1.5 A0 **自动降级本机无头 cli**（非强制远程 + 本机可用时），绝不弹"retry / 换IP / abort"；③ 其余决策字段按下表一次性收齐（字段清单单一信源 = `phase-0-7.md` 字段定义块）。⛔ **`/loop` 无人值守上下文：主流程任何 `AskUserQuestion` 视为规范违规**（无人值守恒走保守默认，含 ENTRY_MODE 保守 full）。

★ **Phase 0 必问白名单（"零弹窗"的显式例外）**：test-intent 裁剪歧义（P0-0）、0.6 决策字段缺失、0.6bis 用例前置资源缺口属于**一次性前置配置收集**，**不受**上面「零弹窗 / 禁止中途阻塞」约束——那些约束针对**执行主流程（Phase 2/3）中途**阻塞，**不是** Phase 0 前置一次性收集。即：**交互式调用（用户在场）下必须在 Phase 0 `AskUserQuestion` 问一次**；**仅 `/loop` 无人值守**（无人可问）才走保守默认 + WARN。

★ **Agent 执行铁律**：① 部署 URL / 访问地址类字段缺失时，**严禁**用 spec 默认值 / 外部 config / 历史 memory **"推导"出部署地址蒙混过关**——交互式必须 `AskUserQuestion` 问，`/loop` 无人值守缺则 `deployment.mode=none`，绝不拼一个会 404 的链接；② **不得自创 spec 之外的里程碑通知**（如部署链接发错后补的"🔗 链接更正"通知）——真正的修复永远是"Phase 0 一开始就问对 / 输对"，而非事后补发。

**收集机制**（默认行为，可加 `--strict-prd` 改为缺失直接退出）：

1. **合并两处声明，判定 = 「PRD frontmatter 优先」**：PRD 头部 frontmatter 是真源，`memory/aidp-config.yaml` 的 `autopilot_decisions:` 段 **只在 PRD 未声明该字段时兜底**；同名叶子两处值不同 → **取 PRD 值**并**逐条打印 `[decisions-conflict]`**（⛔ 不许静默取胜）。**唯一实现** = `autopilot_decisions_merge.py`，⛔ 不另写 grep/yq：

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --shell)"   # 取回 TARGET_VERSION（分片间 shell 变量不持久）
PRD_ROOT=$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py get prd_root --default "docs/requirements")
DM="python3 {{AIDP_HOME}}/scripts/autopilot_decisions_merge.py --version $TARGET_VERSION --prd-root $PRD_ROOT"
$DM --json   # 合并结果 = 第 2 步字段比对的唯一输入；冲突告警走 stderr、恒可见
# 兜底副本与 PRD 有冲突字段 → exit 1 + 可直接执行的清理建议；⛔ 不阻塞本轮
$DM --check || echo "⚠️ 兜底段 memory/aidp-config.yaml autopilot_decisions 与 PRD 冲突：本轮按 PRD 跑，按上面建议清理"
```
2. 与必填决策字段清单对比（单一信源 = `phase-0-7.md` 的字段定义块），得出**完整缺失字段清单**
3. 缺失字段为空 → 直接进入 Phase 1
4. 缺失字段非空 → **按上下文分流**（堵住"7×24 中途新增一份缺字段 PRD 就弹窗死锁"缺口）：
   - **交互式（用户在场）**：命令端**一次性弹 AskUserQuestion 系列收集**，按下方批次分批问（每批最多 4 题）。
   - **★ 无人值守（无人可问，`LOOP_UNATTENDED=1`）**：**绝不弹窗**——对缺失字段套用「无人值守保守默认表」自动填 + 终端 `WARN 本版 N 个决策字段缺失，按保守默认跑（见下表），建议补 PRD 后 --force-replan` + 在 #1b/#4 里程碑通知留一句同款提示（可见不静默）；`--strict-prd` 仍强制记入缺失清单退出（不套默认）。**保守默认表**（只给"能安全兜底"的决策字段；**部署/URL 类字段一律 `deployment.mode=none`——绝不猜 URL**，本版退化为纯开发 + 静态验收、跳过自动部署与浏览器实测，留人工补 PRD 后重规划）：

     | 缺失字段 | 无人值守保守默认 | 理由 |
     |---------|----------------|------|
     | `visual_baseline` | `prototype-only` | 有原型按原型对齐、无则纯功能，不臆造视觉基准 |
     | `cache_strategy` | `disabled` | 不启用缓存最安全，避免脏读 |
     | `mock_position` | `frontend` | 约定 26 P0 首选（前端拦截） |
     | `on_decision_conflict` | `continue-with-default` | 无人可拍板，冲突用默认 + 留档、不死等（口径见 `/sprint-dev` 决策门）|
     | `test_strategy` | `static-only` | 无实测账号/环境时只做静态验收，不空等 chrome |
     | `third_party_mocked` | `[]`（空） | 无声明按无第三方未交付处理，真有会在开发中暴露 |
     | `deployment.mode` / 各部署 URL | `none` | ⛔ 绝不猜部署地址（见上方 Agent 执行铁律）；退化为纯开发、跳过部署+实测，补 PRD 后 `--force-replan`。**★ 命中即落 `degraded_reason="deployment-undeclared"`** + #3 **标题**带「（未部署·静态-only）」——本降级属「不挂起但活没干」：仪式齐全、门全绿，比挂起更难发现 |

   分批问的批次表（**仅交互式路径用**；`/loop` 走上方保守默认表）：

   | 批次 | 收集字段 | 题型 |
   |------|---------|------|
   | **批 1**：开发决策核心 | `visual_baseline` / `cache_strategy` / `mock_position` / `on_decision_conflict` | 单选（含选项卡片）|
   | **批 2**：测试 + 部署模式 | `test_strategy` / `deployment.mode` | 单选 |
   | **批 3a**（mode=local）| `local_frontend_command` / `local_frontend_url` / `local_backend_command` / `local_backend_url` | 文本（用 Other 选项收集自由输入）|
   | **批 3b**（mode=local）| `local_ready_wait_seconds` | 单选（10/30/60/120 秒 + Other）|
   | **批 4a**（mode=cloud）| `cloud_deploy_trigger` / `cloud_deploy_wait_seconds` | 单选 |
   | **批 4b**（mode=cloud）| `cloud_deploy_url` / `cloud_backend_url` / `cloud_deploy_check_url` / `cloud_deploy_script`（仅 trigger=manual-script 时）| 文本 |
   | **批 4c**（mode=cloud）| `cloud_deploy_check_timeout_seconds` | 单选（300/600/900/1800 + Other）|
   | **批 4d**（cloud_deploy_trigger=cicd-provider）| `cicd_env` / `cicd_max_retries` / `cloud_ready_requires_login` / `cloud_ready_login_url` / `cloud_ready_api_url`（+ expect 文本）| 单选 + 文本（`memory/aidp-config.yaml` 的 `cicd.provider` 与 `cicd.pipelines` 须先配好 env→流水线映射；就绪以登录后自身接口为准、不用登录页判）|
   | **批 5**：第三方未交付清单 | `third_party_mocked` | 文本（YAML 列表，Other 自由输入；用户填"无"则空数组）|
   | **批 6**：登录元数据 + 测试账号 + Chrome 远程 IP（如有）| ❌ **已移至 `/sprint-aiauto-test`** Phase 0.3/0.4/0.1.5（避免本命令承担测试期才需要的字段）| —（本命令不问）|

5. 收集完毕 → 命令端**主动分发到两个位置**：
   - **元数据**（autopilot_decisions YAML 段，含部署 URL / 登录选择器 / 角色清单等非敏感字段）→ **恒写回 PRD 目录首份 `.md` 文件头部**（追加 YAML frontmatter）——那是第 1 步判定的真源；**仅当本版 PRD 目录下一份 `.md` 都没有**才退而写 `memory/aidp-config.yaml` 的 `autopilot_decisions:` 段，并同轮打印「已用兜底位置，PRD 落点补齐后请把该段清回 `{}`」。⛔ **两处都写 = 当场制造双信源漂移**（理据见 `rationale.md`）。写完 `git add` + commit `chore(autopilot): 补全 v0.X autopilot_decisions 决策预声明`
   - **账号密码 / Chrome 连接信息**（敏感）→ 不在本命令收集，由 `/sprint-aiauto-test` Phase 0.4 收集写入 `memory/.sprint-autopilot-credentials.json`（见批 6）
6. 进入 **0.6bis 用例前置资源对账门**（`phase-0-9.md`）→ 0.7 就绪完整性总表收口
