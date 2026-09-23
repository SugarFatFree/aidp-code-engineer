<!-- 二次切分 · phase-0 片2/9：覆盖 0.0.6 AI自动化段预检+补全 / 0.0.7 连接模式判定护栏-->

> ⚠️ **权威性**：以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤 / 硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-aiauto-test/phase-0-2.md`。理据见同目录 `rationale.md`。

> ⚠️ **本片【不是】Phase 0.2**：`phase-0-N.md` 的 N 是**切片序号**、不是 Phase 号（本片装 0.0.6 / 0.0.7；Phase 0.2 在 `phase-0-6.md` + `phase-0-6b.md`）。按文件名直觉去 Read 会取错片——权威映射见 `{{AIDP_HOME}}/commands/sprint-aiauto-test.md` 的分片对照表。
### 0.0.6 ★ 测试方案 AI 自动化段预检 + 自动补全 + 信息收集（单一信源，供 /sprint-autopilot /sprint-batch 提前调用）

> 设计目的：让 `/sprint-autopilot`（Phase 0.5.5）/ `/sprint-batch`（前置 Step 0.3）/ 本命令在**流程最开始**就把 chrome-devtools-mcp 自动化测试**所需信息一次性补齐**，**尽量减少中途用户介入**。本预检是该逻辑的**单一信源**，三处命令引用本节、不复写。

**Step 1 — 是否前端 web 项目判定**：

```bash
IS_FRONTEND_WEB=0
# package.json 含 web 框架依赖
find code/frontend -maxdepth 3 -name package.json 2>/dev/null | while read p; do
  grep -qE '"(vue|react|@angular/core|svelte|vite|next|nuxt|umi|@vue)"' "$p" && echo HIT; done | grep -q HIT && IS_FRONTEND_WEB=1
# 兜底：有 .vue/.tsx/.jsx 源文件
[ "$IS_FRONTEND_WEB" = "0" ] && find code/frontend -maxdepth 5 \( -name '*.vue' -o -name '*.tsx' -o -name '*.jsx' \) 2>/dev/null | head -1 | grep -q . && IS_FRONTEND_WEB=1
```

- **非前端 web**（纯后端 / CLI / 库）→ 跳过本预检（chrome 浏览器自动化测试不适用），日志标"非前端 web 项目，跳过 AI 自动化测试方案补全"，直接返回主流程

**Step 2 — 测试方案 AI 自动化段存在性判定**：

<!-- dup-check: ignore 分片自包含 -->
```bash
# 同 Phase 0.0.5：按内容标记找承载「测试环境与账号」的文件（独立成文或内嵌方案皆可），测试人员目录优先、研发自测兜底
# ★ 与 0.0.5 同一版本号预解析（幂等；standalone / `/loop` 下 $TARGET_VERSION 若尚未赋值，这里补上，
#   否则下面路径拼成 docs/testing//… 恒不命中、每 tick 误落"字段缺失"分支）
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"   # 读回 0.0.0 落盘的 --target/--select 等
: "${TARGET_VERSION:=${TARGET_FLAG_VALUE:-$(python3 {{AIDP_HOME}}/scripts/baseline_edit.py current-version)}}"
# ★ 空版本号守卫：尚无可测版本（首个版本部署前）→ 本步无事可做，退出本 tick；⛔ 不拼 docs/testing//… 也不补全、不 commit
[ -z "$TARGET_VERSION" ] && { echo "ℹ️ 尚无可测版本（current-version 为空）→ 跳过测试方案预检，退出本 tick"; exit 0; }
TESTPLAN_DIR="docs/testing/${TARGET_VERSION}/研发自测"   # 缺配置时在此目录补全
CFG_MARK='Chrome Remote Debugging 地址|测试环境与账号|^#+ .*测试账号'
TESTPLAN=$(grep -rlE "$CFG_MARK" "docs/testing/${TARGET_VERSION}/正式用例" "docs/testing/${TARGET_VERSION}/测试验收" "docs/testing/${TARGET_VERSION}/测试执行" 2>/dev/null | sort | head -1)
[ -z "$TESTPLAN" ] && TESTPLAN=$(grep -rlE "$CFG_MARK" "$TESTPLAN_DIR" 2>/dev/null | sort | head -1)
HAS_AI_SECTION=0
[ -n "$TESTPLAN" ] && grep -qE '## 二、chrome-devtools-mcp 启动方式|chrome-devtools-mcp' "$TESTPLAN" && HAS_AI_SECTION=1
```

**Step 3 — 自动补全（`IS_FRONTEND_WEB=1` 且 `HAS_AI_SECTION=0`）**：

- 承载配置的文件缺失 或 有文件但无 chrome-devtools-mcp 段 → **自动补全**：用 `/sprint-selftest` Step 3 的「测试环境与账号」模板（含 ① 一、测试工具 安装命令 ② 二、chrome-devtools-mcp 启动方式 本地/远程完整命令 + 端口转发 + 验证 ③ 三、测试环境 ④ 四、测试账号）补全——**载体由 /sprint-selftest Step 3 模板决定**（独立成文于 `$TESTPLAN_DIR/`，或并入研发自测方案的章节），本命令不写死文件名 / 向已有承载文件追加缺失的「一、测试工具」+「二、chrome-devtools-mcp 启动方式」段（**不覆盖**已填的环境/账号行）；生成后按内容标记重新解析 `TESTPLAN=$(grep -rlE "$CFG_MARK" "$TESTPLAN_DIR" 2>/dev/null | sort | head -1)`
- **补全内容单一信源 = `/sprint-selftest` Step 3 模板**（本处不复抄整段，按同一模板写入）
- `git add "$TESTPLAN" && git commit -m "feat({version}): 补充测试环境与账号配置的 chrome-devtools-mcp AI 自动化段（预检自动补全）"`

**Step 4 — chrome-devtools-mcp 正式使用所需信息完整性核验**（即使段已存在也跑；命中 `<请填写...>` 占位 = 缺）：

| # | 必需信息 | 检查位置 | 缺失影响 |
|---|---------|---------|---------|
| ⓪ | **渲染模式**（默认**无头** `--headless=new`，无需 GUI 桌面；仅① 需被网站当真人（反无头/反爬）② 测分辨率/真实视觉 ③ 无头下页面无法加载/操作 三者之一才切有头）| 测试方案「二·渲染模式」行（无则默认无头）| 缺 → 默认无头；有头本地需 GUI，无 GUI 则须走有头+远程（详见 `dev-manual-testcase/references/chrome-devtools-mcp-setup.md` §0/§2）|
| ① | **测试环境访问地址（前端 URL）** | 测试方案「三、测试环境」表 | aiauto-test 不知道测哪个地址，无法跑 |
| ② | **测试账号密码（≥1 角色，需登录项目）** | 测试方案「四、测试账号」表 | 登录测试无法进行 |
| ③ | **是否跨设备**（Claude Code 与 Chrome 是否同机）→ 定 `DRIVER`（同机=本地 `cli` / 跨设备=远程 `mcp`） | 本机探测 Chrome+9222 可达 **且**（渲染模式=无头 **或** GUI 可用）→ 同机；否则跨设备 | 跨设备需远程 IP+端口转发 + 走 MCP（切模式须重启）|
| ④ | **远程 Chrome 的 IP + 端口**（仅跨设备 `DRIVER=mcp-remote` 时必填） | 测试方案「二·Chrome Remote Debugging 地址」表 | 跨设备缺 IP → 远程连不上 |
| ⑤ | 驱动是否可用（按 `check-cli` 五类矩阵判定：local-cli-ready / remote-ready / needs-restart-has-fallback / local-chrome-no-cli / blocked-no-fallback，非"二选一"）| Phase 0.1.1 委派 `chrome-mcp-doctor.py check-cli` | 仅 `blocked-no-fallback`（本机无 chrome 且远程不可用）才需先装驱动；`local-chrome-no-cli`（cli 不可用）有 `mcp-plugin-fallback` 兜底、非阻塞 |
| ⑥ | **浏览器操作等待时长**（默认 常规≤3s / 首次打开·导航≤30s，**需用户确认**）| 测试方案「五、浏览器操作等待时长」行 | 缺 → 交互式：跑测前与用户确认；**无人值守：采用默认值 3s/30s 继续、不冻结**，报告标注「默认值、未经人工确认」（约束见 Phase 2.2.1）|

> ★ **测试方案优先（铁律，见命令主体）**：上表各项的"默认值"（渲染模式无头 / 等待 3s·30s 等）只是兜底——若 `正式用例/`（测试人员方案）或其次 `研发自测/` 方案**已明确规定**该项，**直接采用方案值、不用默认、不再追问**；仅方案未规定的项才进入下面的一次性收集（用命令默认补空）。

**Step 5 — 缺失则在流程最开始一次性收集（核心：减少中途介入）**：

- **★ 无人值守守卫（`LOOP_UNATTENDED=1`）**：无人可答 → **绝不 `AskUserQuestion`**。
  - **只缺 ⑥ 等待时长**（或 ⓪ 渲染模式）→ **不冻结**：按默认值（常规≤3s / 首次打开·导航≤30s；无头）继续本 tick，回写 `$TESTPLAN` 为 `常规操作 ≤ 3s / 首次打开·导航 ≤ 30s（默认值、未经人工确认）`，并把 `wait_default_unconfirmed=1` 写入本版 baseline（`python3 {{AIDP_HOME}}/scripts/baseline_edit.py --version "$TARGET_VERSION" set wait_default_unconfirmed 1`），报告 `data.notes` 标注「浏览器等待时长为默认值、未经人工确认」。
  - **缺 ①② 或跨设备 ④**（缺了就无法测）→ 缺失字段回写 `{待用户填写}` 占位，随后**一次调用做完**「记账 → 判阈 → 冻结四件套 → 发 #4」：
  ```bash
  eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
  python3 {{AIDP_HOME}}/scripts/autopilot_fail_handle.py --command aiauto-test --version "${TARGET_VERSION:?}" --freeze-now \
    --phase 0.2-testplan --reason testplan-incomplete \
    --why "测试方案 AI 自动化段缺字段（<逐项列出缺哪些>），无人值守无法收集；补 研发自测/ 配置后重触发"
  ```
  **配置类**：解冻看测试方案文件 mtime（补字段不产生新部署）。本 tick **不测**、`UNATTENDED_YIELD` 退出。⛔ 「发 #4」必须由上面那行真发出去——只写四件套 = 停得住但停不响。委派路径（autopilot 0.5.5 预填）下字段已齐，不触发本守卫。
- **交互式**：任一必需信息缺 → **一次** `AskUserQuestion`（多问题合并，**主流程最开始就问完**）收集：① 测试环境前端访问地址 ② 各角色测试账号用户名/密码 ③ 是否跨设备 ④ 跨设备时你电脑的 IP 和端口（填 `IP:9222`）⑤ **浏览器操作等待时长确认**（给出默认 常规≤3s / 首次打开·导航≤30s，用户可直接采用默认或改值；**默认值也必须经此确认才生效**）⑥ **渲染模式确认**（默认**无头** `--headless=new`，无需 GUI；仅反无头/测分辨率/无头不可用时切有头——切有头须确认本地有 GUI 桌面，否则改走有头+远程）。收集后用 Write 回写 `$TESTPLAN` 对应表格（含新增「五、浏览器操作等待时长」行，写法 `常规操作 ≤ {OP}s / 首次打开·导航 ≤ {NAV}s（已确认）`）+ `git commit`。**渲染模式回写「二·渲染模式」行须写明确认值**（无头 → `无头（--headless=new）（已确认）`；有头 → `有头（已确认；原因：{反无头/测分辨率/无头不可用}）`），以便 Phase 0.0.5 解析为 `TESTPLAN_RENDER_MODE`（仅"有头·已确认"判 headed，其余一律无头）
- **★ 等待时长复用**：`$TESTPLAN` 已含「五、浏览器操作等待时长」行（已确认，或无人值守写入的「默认值、未经人工确认」）→ **不再重复问**，直接读用；交互式遇到「未经人工确认」行时顺带纳入一次性收集请人确认
- **★ 同时告知用户相关命令 + 先配后启铁律**（遵守 Phase 0.1.1.5）：
  - **安装**（首次）：`npm i chrome-devtools-mcp@latest -g`（含本地 CLI + 远程 MCP 服务）；**仅远程路径**再 `claude mcp add "chrome-$(git config user.name)" --scope project chrome-devtools-mcp`（服务名强制 `chrome-<git 用户名>`、强制项目级作用域）→ 退出 Claude Code → 重新打开（建议 `claude --dangerously-skip-permissions -c`，`-c` 续上原会话 + 免权限打断）；本地 CLI 路径免注册、免重启
  - **跨设备远程**：须**先在本机配好再连** — ① 启动 Chrome：`& "<Chrome 安装路径>\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="$env:TEMP\chrome-debug"` ② 端口转发：`netsh interface portproxy add v4tov6 listenaddress=0.0.0.0 listenport=9222 connectaddress=::1 connectport=9222`
  - 命令端**只负责把 IP/URL/账号填进测试方案**，**不在此试连**远程 Chrome（试连失败需重启，违反铁律）
- 全部齐全 → 标"✅ 测试方案 AI 自动化段就绪（地址/账号/连接信息完整）"，不弹任何问询，直接继续主流程
- **★ 一次性收全守卫（本命令流畅性铁律 — 后续 Phase 不得二次弹窗）**：Step 5 的这一次收集（交互式）/ 预填（委派）是**测试环境前端 URL + 各角色账号 + 连接模式·远程 IP + 等待时长 + 渲染模式**的**唯一交互窗口**。收集/预填并回写 `$TESTPLAN` + baseline 后，**后续 Phase 0.1.5（远程 IP）、Phase 0.3（部署 URL）、Phase 0.4（账号）一律直接复用已收字段、绝不再弹任何 `AskUserQuestion`**——那几个 Phase 的交互收集分支**仅在** Step 5 未覆盖到（用户跳过某项、或 standalone 首次尚无 `$TESTPLAN`）时才作为兜底触发。目标：把所有"需要问人"的动作压缩到主流程最开始这一次，之后到跑测结束零打断（无人值守下则统一走 `UNATTENDED_YIELD`，本就不问）。

> 💡 **调用方契约**：`/sprint-autopilot` 和 `/sprint-batch` 在各自 Phase 0 / 前置阶段调用本预检（传 `TARGET_VERSION`）；本命令 `/sprint-aiauto-test` 自身在 Phase 0.0.5 之后、Phase 0.1 之前也跑一次（兜底，确保 standalone 跑时信息齐全）。

### 0.0.7 ★ 连接模式判定护栏（强制前置 — 同机无 .mcp.json 必走本地 CLI，禁 MCP 变体顶替）

> ⛔ **铁律（任何浏览器自动化动作之前必跑）**：先由本护栏定死 `MODE`（local/remote）与 `DRIVER`——**同机 + 无 `.mcp.json`（未注册自己的 `chrome-<git_user>` 远程服务）→ 必走 `chrome-devtools-cli`（CLI 直调），绝不允许用 MCP `chrome-devtools` 变体（含无用户后缀通用名 `mcp__chrome-devtools__*`）顶替**。MCP 变体驱动的是共享/远程 Chrome（`list_pages` 会混入他人标签页），本机场景误用它 = 连错实例、串测污染。**仅当确为异机、且已注册自己的 `chrome-<git_user>` 服务 + 端点写入项目根 `.mcp.json`** 时才走 `DRIVER=mcp-remote`。

```bash
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
GIT_USER=$(git config user.name)
# 判据 1：是否有"自己的"远程注册 —— 项目根 .mcp.json 存在 且 含 chrome-$GIT_USER 条目
HAS_OWN_REMOTE=0
if [ -f .mcp.json ] && grep -q "\"chrome-${GIT_USER}\"" .mcp.json 2>/dev/null; then HAS_OWN_REMOTE=1; fi
# 判据 2：显式声明远程 —— 从 tick 命名空间**读回**（0.0.5 在另一分片落盘；理据见 rationale.md『驱动运行时记录与声明读回』）
eval "$(python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py --command aiauto-test --shell)"
DECLARED_REMOTE="${DECLARED_REMOTE:-0}"
# 结论：两条件同时成立才远程；缺任一即本地、强制 CLI（不因 .mcp.json 里他人条目或历史通用名翻远程）
if [ "$HAS_OWN_REMOTE" = 1 ] && [ "$DECLARED_REMOTE" = 1 ]; then
  MODE=remote; DRIVER=mcp-remote
else
  MODE=local;  DRIVER=cli
fi
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test MODE "$MODE" >/dev/null 2>&1 || true    # ★ MODE 无 baseline 真源，须落 tick 命名空间供后续分片读回
# ★ DRIVER 同样须落 tick 命名空间（baseline 回落源 0.6 认领后即 del，见 rationale「DRIVER 认领即删」）
python3 {{AIDP_HOME}}/scripts/autopilot_tick_flags.py set --command aiauto-test DRIVER "$DRIVER" >/dev/null 2>&1 || true
echo "连接模式判定：MODE=$MODE DRIVER=$DRIVER（HAS_OWN_REMOTE=$HAS_OWN_REMOTE DECLARED_REMOTE=$DECLARED_REMOTE）"
# ★★ 运行时记录**此刻立即**落盘（独立于报告的第二信源，供收尾门 3i 核对）；build 号此刻未解析 →
#   先落版本级待认领字段 driver_actual_pending，Phase 0.6 解析出 BUILD 后改挂 build 名下。
#   理据见 rationale.md『驱动运行时记录与声明读回』。
[ -n "$TARGET_VERSION" ] && python3 {{AIDP_HOME}}/scripts/baseline_edit.py \
  --version "$TARGET_VERSION" set driver_actual_pending "$DRIVER" >/dev/null 2>&1 || true
```

> ⛔ **后续任何驱动降级/切换（如 `mcp-plugin-fallback`、CLI 不可用改走 MCP）都必须【同步重写】本字段**——
> 字段语义是"**本轮最终真正用了什么**"，不是"最初打算用什么"。降级了不改 = 记录本身失真，
> 收尾门 3i 会拿一个错的"真值"去判报告，比没有记录更糟。

- **★★ CLI 命令名铁律 + 驱动判定委派 `check-cli`（单一信源）**：`chrome-devtools-cli` 是**技能名**（`/chrome-devtools-mcp:chrome-devtools-cli`）、**不是命令/二进制名**——cli 技能实际调用的命令是 **`chrome-devtools`**（由 `npm i chrome-devtools-mcp@latest -g` 安装，见插件 installation.md）。**严禁**用 `command -v chrome-devtools-cli` 判可用（探错名字会误判 cli 不可用并静默降级 MCP）。（余下见 `rationale.md`）
- **★ 驱动优先级（唯一合法顺序，任何情况不得静默切换）**：`chrome-devtools-cli`（本机，`chrome-devtools` 命令，首选高效）→ `mcp__chrome-{git_user}__*`（远程，需 `.mcp.json` + 重启）→ **`mcp-plugin-fallback`**（cli 真不可用时的**同插件 MCP 协议路径**——`chrome-devtools` 与 `chrome-devtools-cli` 是同一插件 `chrome-devtools-mcp` 的两条控制路径，MCP 本地效率低故非首选，但合法可用，见第五类，须显式声明）→ `blocked-no-fallback`（本机无 chrome 且远程不可用 → 终止 + 播报）。
- **★ 第五类 local-chrome-no-cli（补齐降级矩阵空洞，check-cli 判定）**：`CHROME_BIN_OK && !CLI_OK && 远程不可用` 这一真实组合的合法动作按序——① 先按 check-cli 诊断修 PATH/装包（多数是 npm 全局 bin 未链进 PATH，或旧文档探错名字；修好 `chrome-devtools` 即回 `local-cli-ready`、无需降级）；② 短期修不了 → 降级 `mcp-plugin-fallback`：调插件 `chrome-devtools` 技能 / `mcp__plugin_chrome-devtools-mcp_chrome-devtools__*`（它自起**本机独立隔离** chrome、非共享实例 → 无串测污染，可实测）；替代路径：手工起 `chrome --remote-debugging-port=9222` 再按远程连。
- **⛔ 禁静默切换 + driver 字段必如实（堵报告失真）**：实际使用的驱动**必须**同时打印到 ① 终端 ② AI测试报告 `data.driver`（取值枚举以 `auto-test-runner/references/report-format.md` 为单一信源，约定21 不逐值复述）③ #D 部署里程碑通知正文；**严禁**用了 plugin 却把 `driver` 填 `cli`（报告失真）。无人值守（`LOOP_UNATTENDED`）下第五类照样用 plugin-fallback（显式声明）继续测、不挂起；仅 `blocked-no-fallback` 才 `UNATTENDED_YIELD` 让位。
- **★ 防呆·共享实例检查（连接后、跑用例前必做一次）——★ 按驱动分流话术**：首次 `list_pages` 若发现**非本任务的标签页/上下文**（他人业务页、非目标测试 URL 的活动标签），结论**按 `DRIVER` 分流、绝不一刀切**——
  - **`DRIVER=mcp-remote`（远程/共享实例）**：疑似连到他人 Chrome → 告警「疑似连错实例」并**停下确认**（无人值守记 baseline 让位），避免在共享实例上串测（保持现有话术）。
  - **`DRIVER=cli` / `mcp-plugin-fallback`（`--isolated` 自起隔离实例，Phase 0.1.2.1 判 `isolated-self-spawned`）**：**属正常现象**——CLI daemon 跨会话长驻（unix socket），实例里的历史/非目标标签页多为**本执行体早先操作的残留**，**不是"他人 Chrome"、外部进程根本连不进 `--isolated` 实例**。正确动作 = `select_page` 切回目标页继续，**⛔ 禁止归因为"他人/其他进程抢占/被外部导航"**。
  - ⛔ **反捏造硬约束（Critical）**：**禁止对实例现象做未经 `chrome-devtools status` 核实的归因**。凡要在报告 / 日志 `data.notes` 写下"实例被抢占 / 被其他进程导航 / 复用了某外部实例"之类结论，**必须附上 `chrome-devtools status` 的 daemon args（含/不含 `--browser-url`）作为证据**（即 Phase 0.1.2.1 的 `OWNERSHIP` 判定）；**无 args 证据不得写入报告**——一手判据是 daemon args，不是 curl 9222 / 端口 / 快照里看到的某个页面。

