# sprint-autopilot · Phase 0 详情分片 [7/11]（0.5 PRD 决策预声明 + 0.5bis 询问收敛）

> 本文件是 `/sprint-autopilot` 命令 **Phase 0** 详情的**第 7/11 片**（每片 ≤20KB，命令主体按子步进度依次 `Read` 对应分片）。
> - **本片覆盖**：0.5（PRD 头部决策预声明）+ 0.5bis（询问收敛总则）
> - **同 Phase 其它分片**：phase-0-1.md … phase-0-9.md（含 phase-0-6b.md）（清单见命令主体 Phase 0 骨架表「所在分片」列）
>
> ⚠️ **权威性**：进入 Phase 0 后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤/硬门。
> ⚠️ **维护**：随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-autopilot/phase-0-7.md`。理据见同目录 `rationale.md`。

---

### 0.5 PRD 头部决策预声明（`--full-auto` 默认强制）

`--full-auto` 模式下命令不会弹任何 `AskUserQuestion`，因此 PRD 必须在头部显式声明以下决策。扫描 PRD 目录内首份 `.md` 文件前 200 行，必须含 YAML 段：

```yaml
---
autopilot_decisions:
  # === 决策字段（7 段：①视觉基准 ②缓存策略 ③Mock 位置 ④第三方未交付 ⑤测试策略 ⑥决策冲突处置；⑦ deployment）===
  visual_baseline: prototype-only         # 约定 4 视觉基准：mockup-strict | prototype-only | optimize-with-uispec
  cache_strategy: disabled                 # 约定 26 + dev-logic-architect「缓存机制用户确认原则」：disabled | redis | caffeine | localStorage
  mock_position: frontend                  # 约定 26：frontend | backend | middleware
  third_party_mocked:                      # 第三方未交付清单（可空数组）
    - vendor: 银行代扣
      api: /api/bank/deduct
      expected_ready: 2026-07-15
  test_strategy: chrome-mcp                # chrome-mcp（浏览器实测）| static-only（仅静态扫描）
  on_decision_conflict: pause-notify       # 决策冲突时：pause-notify（暂停并发 #4 通知） | continue-with-default

  # === ★ 部署 + 测试环境 ===
  deployment:
    mode: local                            # local（本地启动） | cloud（云端自动部署） | none（不部署，强制 test_strategy=static-only）
    branch_strategy: current               # ★ dev 代码落哪个分支 + 与部署源对齐（Phase 0.4）：current（在当前分支开发，尊重"直接提交部署源分支"的项目约定，默认）| feature（建 feature/autopilot-{V}，须同时确定"合并回部署源"策略，否则代码搁浅在部署永不构建的分支上）| <指定分支名>。留空=自动推断：读部署源 ref（cicd-provider 取本次提交流水线运行的构建分支 / git-push 未配置 cicd.pipelines 取 CI 监听分支），当前分支==部署源→current；否则交互式 AskUserQuestion、无人值守默认收敛 current 并 WARN。⛔ 严禁在 master 上无条件建 feature/autopilot-{V}：它 + 不自动 merge master + 部署源是 master 三者组合会造成"dev 完成却部署不了"的死结，且要到部署阶段才暴露

    # --- mode=local 必填段（chrome-devtools 测本地 dev server）---
    local_frontend_command: "npm run dev"            # 前端启动命令（在 code/frontend/{子项目}/ 下执行）
    local_frontend_url: "http://localhost:5173"       # 前端访问地址（chrome 测这个）
    local_backend_command: "mvn spring-boot:run"      # 后端启动命令（在 code/backend/{子项目}/ 下执行；纯前端项目留空）
    local_backend_url: "http://localhost:8080"        # 后端 API 基址（纯前端项目留空）
    local_ready_wait_seconds: 30                      # 启动后等待多少秒才开始 AI 自动化测试（等服务监听 + 编译）

    # --- mode=cloud 必填段（chrome-devtools 测云端 UAT/Demo）---
    cloud_deploy_trigger: git-push                    # git-push（推 origin/{branch} 触发 CI） | manual-script（命令调本地脚本） | ci-pipeline（外部触发，命令只等部署完成） | cicd-provider（CICD 流水线，平台 = memory/aidp-config.yaml 的 cicd.provider，默认 GitHub Actions：命令检测/触发+监听+失败重跑+部署就绪探针，见约定 31.5 + Phase 3.2.1）
    cloud_deploy_script: "./deploy.sh"                # cloud_deploy_trigger=manual-script 时填，相对项目根目录
    cloud_deploy_url: "https://uat.example.com"       # 部署后前端访问地址（chrome 测这个）
    cloud_backend_url: "https://uat.example.com/api"  # 后端 API 基址（含网关路径）
    cloud_deploy_wait_seconds: 300                    # 提交代码后等多少秒 chrome 才能开始测（CI 构建+发布的预估时长）
    cloud_deploy_check_url: "https://uat.example.com/health"  # 部署完成探测端点（可选；命令会在 cloud_deploy_wait_seconds 后开始轮询直到 200）
    cloud_deploy_check_timeout_seconds: 900           # 探测最大等待时间（探测开始后，超时则发 #4 通知 @用户）

    # --- cloud_deploy_trigger=cicd-provider 专用段（见约定 31.5 + Phase 3.2.1；流水线标识取自 memory/aidp-config.yaml 的 cicd.pipelines[env]）---
    cicd_env: test                                    # ⚠️ 仅作候选起点：dev|test|prod，查 cicd.pipelines.<env> 得流水线标识。最终监听哪次运行由 Phase 3.2.1 Step A0 按「运行 commit==本次 push commit / 构建分支==本轮开发分支 + 部署目标」核验确定
    cicd_max_retries: 3                               # 流水线运行失败后最多重跑次数（缺省取 cicd.max_retries，默认 3）
    cicd_post_push_wait_seconds: 10                   # ★ 代码 push 后等多少秒再查流水线是否已自动触发（默认 10，给 push 事件触发运行留延迟）
    cicd_post_deploy_wait_seconds: 15                 # ★ 流水线报成功后等多少秒再开始部署就绪探针——**最少 15s**，并按后端技术栈冷启动特性额外延长（JVM/Spring Boot 类较重→30~45s；Node/Python/Go 较轻→20~25s）。留空则命令端按 code/backend 构建文件自动判定，用户填值覆盖（但不得低于 15）
    # 部署就绪探针：⛔ 不能用登录页可达性判就绪（登录页常是第三方/SSO，本应用没起来也照样 200）；有登录系统须以「登录成功后」自身接口为准
    cloud_ready_requires_login: true                  # 应用是否有登录系统：true→必须登录成功后再验证自身鉴权接口；false→直接验证自身公开取数接口
    cloud_ready_login_url: "https://uat.example.com/api/auth/login"  # requires_login=true：项目自身的登录接口（curl POST 拿 token/cookie；★ 非第三方登录页/SSO 页）。账号密码不放 PRD，读 研发自测/01_测试环境与账号.md
    cloud_ready_api_url: "https://uat.example.com/api/menu/list"  # 主就绪信号：项目自身实现、返回真实数据的后端接口（requires_login=true 时须为需鉴权接口，带登录凭证请求；非第三方、非纯健康探针）；要求连续 2 次取到数据
    cloud_ready_api_expect: '"code":"0"'              # 后端接口就绪标记（响应体含此串 / 数据非空才算后端就绪）
    cloud_ready_page_url: ""                           # （可选）登录后自身首页/受保护页地址（★ 非登录页）；纯前后端分离项目可留空、只靠 api 信号
    cloud_ready_page_marker: "<div id=\"app\""        # cloud_ready_page_url 非空时的页面就绪标记
    cloud_ready_interval_seconds: 15                  # 就绪探针刷新间隔
    cloud_ready_timeout_seconds: 600                  # 就绪探针最长等待（超时=部署成功但未就绪/登录不通→#4 介入）

    # --- ★ 分端部署声明段（可选；仅当前后端走【不同】部署链路时填，覆盖上面单段字段）---
    # 动机（半截部署）：单条流水线只部署了后端、前端产物未更新，却因"后端就绪探针过 + 报告齐全"通过全部硬门。
    #   分端声明让 Phase 3.2.1 Step D 逐端验证就绪 + ceremony-gate 3e 校验"有改动的那端确有部署证据"。
    #   不填 = 沿用上面单段字段（前后端一条流水线整体部署），向后兼容。
    deploy_ends:
      backend:
        trigger: cicd-provider                        # 该端部署方式（同 cloud_deploy_trigger 取值域）
        pipeline_env: test                            # cicd-provider 时的候选环境（最终仍由 Step A0 核验）
        ready_api_url: "https://uat.example.com/api/menu/list"   # 该端就绪探针（登录后自身鉴权接口，连续 2 次取数）
      frontend:
        trigger: cicd-provider                        # cicd-provider | manual | none（none=本端本次无部署，不校覆盖度）
        pipeline: ""                                  # 前端独立流水线标识（与后端不同条时填；含义同 cicd.pipelines 的值；留空走 Step A0 观测/核验）
        ready_asset_probe:                            # ★ 前端产物特征探针：证明"跑的是新版本"，而非仅 HTTP 200
          url: "https://uat.example.com/"             # 前端首页（抓 HTML → 提取主 JS/资源）
          must_contain: []                            # 本次改动的可判定特征串（占位文案 / 新配置接口路径 / 新路由 slug）；由本轮变更派生，空则探针跳过并 WARN

    # --- 登录测试段（AI 自动化实测需登录时必填；test_strategy=static-only 或 mode=none 时可全留空）---
    # === 登录测试段（AI 自动化实测用 — 由 /sprint-aiauto-test 命令收集 + 使用）===
    # 字段：requires_login / login_url / login_strategy / login_form_selectors
    #      / user_roles / login_after_seconds
    # 详见 /sprint-aiauto-test 命令文档 Phase 0.3 节

  # === ★ WebMCP 可选能力段（⛔ 不计入必填决策段；【整段不存在 = 未启用】，绝大多数项目就该没有这段）===
  # ⛔ Phase 0.6 的字段缺失收集【不得】把本段当缺失项去问、去补、去填默认值——
  #    "段不存在"本身就是完整且正确的答案（默认关闭），凭空补一段 enabled:false 只会制造噪音。
  # 判定唯一实现：python3 {{AIDP_HOME}}/scripts/check_webmcp.py --detect --json（各处禁止自行 grep）
  # 详规单一信源：{{AIDP_HOME}}/rules/webmcp.md（★ 按需安装：默认在模板位
  #   {{AIDP_HOME}}/templates/optional-rules/webmcp.md，启用后跑 check_webmcp.py --install-rule 装到 rules/）
  webmcp:
    enabled: true                                     # 仅当项目【显式决定】启用才写本段
    entry_symbols: ["navigator.modelContext"]         # 本项目实测的能力入口标识符（挂载位置已迁移过一次、
                                                      # 规范仍在演进；留空则用脚本内置默认，可能过期）
---
```

★ **账号密码不放 PRD**：账号密码、Chrome 连接地址、测试环境 URL 统一维护在 `docs/testing/{version}/研发自测/01_测试环境与账号.md`（由 `/sprint-selftest` Step 3 与研发自测用例配套生成；开发测试环境账号可明文维护，随代码入库便于团队共享）。`/sprint-aiauto-test` Phase 0.0.5 优先读取该文件；仅当账号涉及生产/UAT 安全要求时才回退到 `memory/.sprint-autopilot-credentials.json`（chmod 600 + .gitignore + 不入 git）。详见 `/sprint-aiauto-test` 命令文档。

**字段使用时机**：
- `local_*` / `cloud_*` 在本命令 Phase 3.2（部署动作）+ `/sprint-aiauto-test`（部署探测 + 浏览器实测）使用：
  - `mode=local` → 命令启动 dev server（前端 + 后端如有） → 等 `local_ready_wait_seconds` → chrome 测 `local_frontend_url`
  - `mode=cloud` → 命令按 `cloud_deploy_trigger` 触发部署 → 等 `cloud_deploy_wait_seconds` → 探测 `cloud_deploy_check_url` 直到 200（最长 `cloud_deploy_check_timeout_seconds`） → chrome 测 `cloud_deploy_url`
    - `cloud_deploy_trigger=cicd-provider`（CICD 流水线，`cicd.provider` 默认 GitHub Actions）→ 不走上面的"等固定秒数 + 探 health"，由 **Phase 3.2.1** 经 `cicd_watch.py` 检测 / 监听 + `--mode trigger` 触发 / `--mode retry` 失败重跑（≤`cicd_max_retries`）+ **部署就绪探针**（**有登录系统则以「登录成功后自身鉴权接口 `cloud_ready_api_url` 连续 2 次取到数据」为准；⛔ 不用登录页可达性判就绪**，详见约定 31.5 + Phase 3.2.1）后才放行测试链路
  - `mode=none` → 命令强制覆盖 `test_strategy=static-only`，跳过 AI 自动化测试（仅静态扫描）

---

### 0.5bis 询问收敛总则（P1-1 D3/D4/D5 — 把"过多交互门"收敛到只剩真正需要人的）

> 实测反馈：一次无人值守 autopilot 触发约 10 个 `AskUserQuestion`（多为脏树处置、上版收口、模块/技术边界确认）。用户期望**只有真正无默认可依的不可逆决策需要人工**。故：

- **★ D5 适用面（口径与 `LOOP_UNATTENDED` 无关，交互式单次同受约束）**：本节的**白名单**（下方"仍需人工的两类"）与 **D3 逐门默认**，**对交互式单次调用同样生效**——判据是"这个门有没有确定性默认可依"，**不是"用户在不在场"**。⛔ 不得以"本轮是交互式、用户就在旁边"为由把任何本可推出默认值的门丢回给人。
  - **Why**：P0-4 / IRON-10 明确要求**交互式单次由本次调用自身跑完全流程与缺陷闭环**；若询问收敛只在无人值守生效，交互式单次就落进"既被要求跑满全流程、又不受任何询问约束"的真空——下游实测正是从这里把 AI 测试半环丢回了人（详见 `rationale.md`「0.5bis 适用面」）。
  - **两种模式的【唯一】差别 = 命中白名单后怎么处置**（不是"要不要遵守白名单"）：
    | | 无人值守（`LOOP_UNATTENDED=1`） | 交互式单次（`LOOP_UNATTENDED=0`） |
    |---|---|---|
    | 命中白名单两类 | **不弹窗**，按占位 / 降级继续 + 留痕 | **允许弹一次 `AskUserQuestion` 就地问清**（用户在场，问清比占位更优） |
    | 问完之后 | — | **必须在本轮内接着跑完剩余全流程**（IRON-1） |
    | 未命中白名单 | 取确定性默认继续 | **同样取确定性默认继续，不得询问** |
  - ⛔ **"问一句然后结束回合"= 违规**：交互式的弹窗额度只用于**取回继续所需的信息**，不是把剩余流程的执行权交还用户。返回时 `run_state` 停在非终态且无人接手 = 违反 IRON-1，与话术怎么写无关（判据见命令主体「判据只看客观状态、不看收尾话术」）。
- **★ D4 总则（最高口径）**：`LOOP_UNATTENDED=1` / `--unattended` 上下文下，**任何"可由确定性规则推出默认值"的问题一律不得询问**——直接取默认继续并在日志/报告留痕。**只有**同时满足「错了会造成不可逆外部影响」**且**「无默认可依」的问题才允许弹窗（几乎只剩下方白名单两类）。
- **★ D3 逐门默认（补齐"预声明覆盖不全"的门，无人值守一律走默认、不弹窗）**：
  | 门 | 无人值守默认 | 来源 |
  |----|------|------|
  | 脏树处置（working tree 非空） | `git add -A` 纳入本轮提交（同 Phase 3.5 确定性提交） | Phase 3.5 |
  | 上版收口（存在未 close 的上个 Sprint/版本残留） | 按既有归档流程自动收口，不问 | Phase 3.x |
  | 模块边界 / 技术边界确认 | 取 PRD 预声明；无则按项目既有技术栈/目录约定确定性推断（约定 18/28） | PRD `autopilot_decisions` + 约定 28 |
  | test-intent 流程裁剪 | 保守默认 full、不裁剪（除非显式 `--skip-dev`） | Phase 0.1 |
- **仍需人工的两类（收敛后的白名单 · 两种模式共用，见 D5）**：① 本轮必需的外部写动作所依赖的凭据失效且无降级路径（如部署脚本凭据过期）② 部署目标完全无法推断（`deployment.mode` / 部署源分支无上下文可推）**且** PRD `deployment` 段未预声明。**除这两类之外**：无人值守零 `AskUserQuestion`；交互式单次同样不得询问，一律取确定性默认继续 + 留痕。⛔ **「缺前置数据 / 缺测试账号」不在白名单内**——它由 Phase 0「用例前置资源对账门」（`phase-0-9.md` 0.6bis）在 Phase 0 一次性问清，此后以此为由暂停即违规（见 `phase-3-1.md` 非法跳过借口清单）。

