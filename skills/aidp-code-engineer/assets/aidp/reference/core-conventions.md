# 核心约定完整协议

formal 进入正式流程时读取本文件及对应细则；light 只读 `{{AIDP_HOME}}/reference/light-entry.md` 与受影响的 rules，不自动加载本协议。编号 1–41 保持稳定，引用「约定 N」定位到下文主行及其详规。

## 核心约定（必须遵守）

> 约定编号 1–41 为稳定锚点（命令/Agent/SKILL/记忆全靠「约定 N」引用），不得重排或合并。**本文件每条只做「决策要点 + 详规指向」索引**；详细规则在其**单一信源**处（随脚手架下发，可查）——工作流约定指向所指 SKILL/agent/命令，**代码向约定（4/17/18/19/20/23/26/27/28/29/35/39/40）指向 `{{AIDP_HOME}}/rules/*.md`**（`frontend.md`→`code/frontend/**`、`backend.md`→`code/backend/**`、`code.md`→`code/**`，带 `paths:` frontmatter，**Claude Code 下编辑对应代码时才自动加载**、不占常驻上下文；Codex / DeepSeek Harness 无此机制，须编辑前显式 Read，见 `{{AIDP_HOME}}/reference/agent-tools.md`）。「见约定 N」始终解析到本文件索引摘要 + 其单一信源详规。 **★ 每条的完整细则/Why/示例/实现子项已外置为按需 Read 的分片（本目录总览见 `{{AIDP_HOME}}/reference/README.md`），映射如下——约定 1·2·6·9·11·13·14·15·16·21 → `{{AIDP_HOME}}/reference/约定细则-1.md`；约定 22·24·30 → `{{AIDP_HOME}}/reference/约定细则-2.md`；约定 31·32·33 → `{{AIDP_HOME}}/reference/约定细则-3.md`；约定 34·35·36 → `{{AIDP_HOME}}/reference/约定细则-4.md`；约定 37·38·41 → `{{AIDP_HOME}}/reference/约定细则-5.md`（其余约定为一行、无外置细则）。★ 分片内只放该条的子项/Why/示例，**决策要点主行以本文件为唯一权威、分片不复制**（避免双写漂移）。**
>
> ⚙️ **技术栈中立**：下文出现的具体技术（`@RefreshScope`/`@Profile`/`el-*`/`@Size`/`VITE_USE_MOCK`/MyBatis 等）一律为**示例**，请按本项目实际编程语言与技术选型对应等价机制；纯属某技术栈的约定（如约定 27 仅配置中心项目适用）不适用时直接忽略。AIDP 范式的角色技术细则（`agents/backend.md` / `frontend.md`）默认以 Java Spring Boot + Vue 为例，下游可按需替换。

1. **版本规划期生成所有设计文档**：需求和详细设计在 `/version` 阶段一次性生成，Sprint 执行期只读取不重新生成

2. **任务身份先于累进**：普通自然语言新增功能/修复默认 light，复用 `/sprint-dev`、`/sprint-bugfix` 不自动创建 Sprint。**formal 明确累进**才创建 Sprint 并追加设计，且仅适用于当前版本未发布；两种身份都保留版本落点、破坏性及不可逆操作授权门。详规适用域由约定 41 与 `flows/sprint-dev/light-context.md` 先行裁定。

3. **零散 bug 独立修复**：`/sprint-bugfix`（无参数），无需新 Sprint

4. **UI 优先级（视觉+内容+操作逻辑三层对齐 / 字段裁剪三件套 / 设计令牌 / L1·L2 / 4 情形 A-D）**：前端视觉·内容·操作逻辑三层须对齐原型（除非走裁剪三件套显式说明）；原型字段的裁剪/改名/增列走「研发需求留痕 → 产品确认门 → 约定 22 级联」三件套，绝不静默漂移；无高保真时按情形 A/B/C/D 决策（C/D 用户显式选），情形 B/C 先从原型提「设计令牌」再开发；L1 页面样式（元素齐全+设计语言体系+布局）严格对齐、偏差 Critical，L2 用项目组件默认样式但主题 token 取自 L1。**★ 全部决策铁律（三层定义 / 三件套双向双盲区 / 规划期"漏写=违规" / 强制产出物「原型内容基线」+「设计令牌」/ 约定 28 边界 / L1·L2 分级 / 叶子组件白名单 / 图标语义化 等）见 `{{AIDP_HOME}}/rules/frontend.md`（编辑 `code/frontend/**` 时自动加载）**；回检 = `code-verification-loop` 维度 4「视觉还原度(L1/L2)」+ `version-auditor`「原型覆盖度」(Critical 硬门) + `dev-manual-testcase`。

5. **公共组件优先**：布局/导航/侧边栏等公共组件必须先抽取复用，禁止跨页面重复实现

6. **数据库基线必读 + ★ SQL 开发期自动应用（幂等）**：设计表前必须读 `memory/databaseBaseline.md`，已有表不重复创建。

7. **遵守架构约束 + 全目录识别架构文档**：所有设计和代码必须符合 `docs/architecture/` 约束文档；读 `docs/architecture/` 时**全目录扫描**——除约束三件套外，还识别可选的**架构设计文档**（单文档 `架构设计.md` 或子文件夹 `架构设计/` 多文档，兼容存量任意命名，详见 `06_版本与用户目录约定.md` §2.1.1），架构设计文档作为详细设计的上游输入。**★ 仅有架构设计、缺架构约束时**（版本规划期）：`/sprint-design` Step 4.2 据架构设计派生一份 `架构约束.md`，使全局约束基线不缺失

8. **ADR 必记**：影响架构的技术决策必须追加到 `memory/systemPatterns.md`

9. **formal Sprint 关闭前归档**：未执行 `/sprint-close` 不得开始下一个 Sprint；light 收尾不创建 Sprint 归档、不重置已有 activeContext/progress。**★ 归档只记「事后查不到的东西」+ 篇幅分档**（约定 41.5）：⛔ 不记 git log 查得到的、不记文档里已有的、不记下一轮会重算的；记的是**判断与取舍**（为什么选这个方案、放弃了什么、留下什么已知失准点）。建议上限：口述累进 ≤40 行 / 计划内 Sprint ≤80 行 / 含口径反转 ≤120 行（超出不阻断，但须自问「这些是不是事后查得到的」）。

10. **formal Bugfix 文件规范**（light 修复证据使用任务上下文目录的机器 JSON）：`docs/bugfix/{version}/bugfix-{YYYYMMDD}-{user}.md`（一天一人一份）+ 表格 + 详情章节。用户主动提及 GitHub Issue 时先用 `gh issue view/list` 读取再修（可选），详见约定 31.3。

11. **目录隔离**：迭代产出按 `{version}/` 或 `{version}/{user}/` 隔离，不跨用户改他人目录。

12. **★ 文档动态同步（触发条件在此，【执行时机与落盘形态】一律归约定 22，本条不另立一套）**：引入新接口 / 表 / 功能时，详细设计·接口设计·数据库设计·研发执行计划**都要跟上**——但**跟上的方式 = 约定 22 的攒批**：**开发过程中只写四族 `_开发期{族}增量.md`（与各族内容主文档同目录，落点见详规）**，到**收口点**才批量级联、**就地改各族内容主文档正文**（⛔ 不新建分册；机器门 `check_cascade_landing.py` 见到 `NN_<业务主题>.md` 即判违规）。**⛔ 开发过程中不实时改这些文档**：不改 `01_` 等主文档正文、不逐次刷 `00_索引.md`、不为一次改动新起分册——`00_索引.md` 的生成时间/清单（约定 15）在**收口时**随增量一并刷新。⛔ 本条**不构成**「实时回写」的授权；与约定 22 冲突时**以约定 22 为准**。

13. **提交信息规范**：遵循 Conventional Commits（`feat:` / `fix:` / `docs:` / `refactor:` / `test:` / `chore:`，可带作用域如 `feat(user):`），**一次提交只做一件事**（业务改动、重构、格式化、脚手架同步各自成笔）。详规见 `{{AIDP_HOME}}/reference/约定细则-1.md`。

14. **文档语言（中文为主）**：AIDP 命令生成文档**正文 + 文件名都用中文**。

15. **同类多文件编号 + `00_索引.md` 专职导航锚 + 补充文档命名（去"补充"字眼）**：**四类版本规划文档（研发需求/详细设计/研发执行计划/研发自测）恒有 `00_索引.md` + 内容主文档从 `01_` 起——含单文件态、无例外**（裸中文名如 `详细设计.md` 属 `version-auditor` A-06b Critical）；其余同类多文件才按两位数字前缀排序（`01_`~`99_`，超 99 合并；已带日期前缀的文件按日期排序不加数字前缀）。单一信源 = `dev-logic-architect` SKILL「多文件拆分」+ `{{AIDP_HOME}}/skills/dev-logic-architect/scripts/check_doc_split.py`（⚠️ `dev-execution-planner` / `ux-logic-extractor` 各自另带一份**同名但形态定义不全**的脚本，判据以 dla 那份为准）。

16. **★ SKILL 修改作用域硬约束**：`{{AIDP_HOME}}/skills/` 下**全部 SKILL 均由 AIDP 模板仓库（`aidp-code-engineer`）自有维护**——在模板仓库内可直接修改，改后同步进脚手架；**经脚手架初始化/升级的下游项目内不应直接改**——改后无法回流模板、下次升级被覆盖丢失、与姊妹项目永久漂移，需要变更时回到模板仓库修改后再升级下发。

17. **★ 代码注释强制规范**（覆盖 Claude 默认"无注释"原则，统一遵守）：类/接口/枚举/组件、方法/函数、字段/常量、关键代码段均须按规范加**业务含义**注释（枚举值域、参数·返回·抛出语义、与 DB COMMENT/PRD 对齐），强度按 A/B/C 三档。**详规见 `{{AIDP_HOME}}/rules/code.md`（编辑 `code/**` 时自动加载）**；回检**两个方向都有**：写少了 = `code-verification-loop`「注释完备性」（A 档裸代码 → Critical 回 `/sprint-bugfix`）；写多了 = `python3 {{AIDP_HOME}}/scripts/check_comment_ratio.py`（声明之外的注释过密 → Important 不阻断，由 `/sprint-dev` Phase 1 Step 7bis 调用）。⛔ 反向门不是「少写注释」的许可——它只砍 B/C 档的同义反复。

18. **★ 代码目录统一标准（`{子项目}` 中间层为铁律）**：新建 `code/` 强制前后端二分 `code/frontend/{子项目}/` + `code/backend/{子项目}/`，源码根标志（`src/`/`pom.xml`/`build.gradle`/`package.json`/`go.mod` 等）**只能落在 `{子项目}` 层下、严禁直放 `code/frontend`·`code/backend` 父目录根**（即便单项目也须有 `{子项目}` 层）；`{子项目}名` 经用户确认门（默认推荐 `<项目名>-frontend|backend`、不静默采用）。**详规（init/migrate/upgrade 三模式行为 + Agent 读写边界 + 强制范围）见 `{{AIDP_HOME}}/rules/code.md`**；回检 = `verify.py::check_code_layout`。

19. **★ README 三档规范**：① 前后端子项目根（含每个 module）必有 `README.md`，说明用途、技术栈、启动、目录、配置与依赖；源码单元内部不生成。② 源码树外直接子目录 ≥2 或有 1 个非空子目录的枢纽，只保留一份导航，默认 README；已有契约要求的 `00_索引.md`（约定 15）或部署说明时不再补 README。③ 其余平铺目录不生成。判定唯一实现 = `readme_policy.py::is_readme_required_directory`，`README_REQUIRED` 显式声明优先，存量范围外 README 只报告不删除。详规见 `{{AIDP_HOME}}/rules/code.md`；触发 = `/sprint-dev` 首次写码前 / `/sprint-init`，回检 = `verify.py::check_code_readme`。

20. **★ 文件复杂度 + 复用封装强制规范**（任务需要的复用 ≠ 过度抽象）：单文件按语言软阈值（Java/Kotlin ≤500、Vue/React ≤300、TS/JS ≤400、Python ≤600、Go ≤500、SQL DDL ≤800）、单方法/函数硬阈值 ≤50 行必拆；同 Sprint 内 3 次复用即抽公共单元（**★ 前端视觉单元收紧到 2 次**——逻辑的重复会被 bug 打出来，**样式的重复不报错、只会分叉**；**★ 判据类逻辑**——URL/base 拼装、鉴权头、租户解析、时间格式化、金额换算、脱敏归一——**散落 ≥2 处即须收敛，比 3 次阈值更严**）；复制型代码必落 `SYNC-WITH: <源文件>` 标记 + 技术债项写明「为什么现在不抽 / 解除条件」（缺任一 = 未处理，⛔ 登记不是免责声明）；抽取须**整族 + 全参数化**、且**与重构分两次提交**；禁 God Class（>1000 行）/ 瑞士军刀方法 / 3+ 复制粘贴 / 无 3 次复用的空抽象。**详规（各语言阈值 + 豁免）见 `{{AIDP_HOME}}/rules/code.md`**；回检 = 超阈值 Important、>2 倍 Critical 回 `/sprint-bugfix`。

21. **★ 命令调用 SKILL 的内容职责分层**（强制）：命令通过 `Skill` 工具调 SKILL 时**不得重复或修改 SKILL 已有规则**，但允许做项目级补充。SKILL 是单一信源，命令只做编排 + 项目级延伸。

22. **★ 上游文档级联同步（默认【攒批】执行，非即时）**：引入超出既存文档范围的实质变更（新增接口/表/业务规则/页面/功能点/Sprint 拆分/原型字段被覆盖或裁剪/第三方接口 Mock 切真实/语义·口径·范围·单位·默认值·状态机·权限范围变更）在相应收口点按受影响范围级联回核心上游文档族：**研发需求 → 详细设计 → 研发执行计划 → 研发自测用例**。**★ 执行形态 = 攒批**：先按受影响的族记入 `_开发期{族}增量.md`（同一变更跨族共用 `C-NNN`），由【收口点】批量级联、结合代码现状核实，成功即删条目、清空即删文件；`--cascade-now` 仅用户显式要求时可当场级联；light 只记实际受影响族，不建空册、Sprint 卡、替代审批文档，test/close 不触发全套级联。**★ 作用域 = 变更事实、与命令入口无关**：裸对话路径同样先记增量册（绕过由 `commit_gate.py::suspected_cascade_bypass` 反向检出）。**详规见 `{{AIDP_HOME}}/reference/开发期族增量.md`**。

23. **★ DB 约束写代码硬规范**：DDL 声明的字段约束（NOT NULL/长度/唯一/外键/数值范围）必须前置校验到**接口层/服务层/前端表单层**，禁止依赖 DB 抛错回滚、禁止把数据库异常（如 `SQLException`/`DataIntegrityViolationException`）原样暴露前端（须包业务码 + 友好提示）。**详规见 `{{AIDP_HOME}}/rules/code.md`（编辑 `code/**` 时自动加载）**——后端长度/唯一查/外键查 + 前端必填·长度·失焦查唯一·枚举对齐·数值范围 + 反模式均在其中；回检在 `code-verification-loop` 维度 4 + `dev-manual-testcase` 4 类边界场景（null/超长/重复/外键缺失）。

24. **★ 提交前门禁 `commit_gate.py`（每次 `git commit` 前必跑；强制铁律）**：**每次** `git commit` 前**必须**跑 `python3 {{AIDP_HOME}}/scripts/commit_gate.py --quiet` 并读其 JSON（无需 execution-context，不核 grant；用户一句「提交」即授权）。**★ 退出码即欠账信号**：`0`=无欠账；**`3`=有未落地义务**；`4`=保留阻塞档位——3/4 **不是"禁止 commit"**；提交照常，之后按成因补做（台账格式/清理异常 → 修正并复核；CICD 已启用时的 commit 提示行 → 按约定 31.5 现场补监听；实际级联仅由阶段入口或显式 `--cascade-now` 触发）；欠账告警恒打印 stderr、`--quiet` 不压制。**★ 作用域 = 变更事实、与命令入口无关**：裸对话路径同样适用。总开关 = `memory/aidp-config.yaml` 的 `commit_gate.enabled`。**详规见 `{{AIDP_HOME}}/reference/约定细则-2.md`**。

25. **★ 配置文件分层**：运行时配置（如 `application.yml`/`.env`/`nginx.conf`/`vite.config` 等）**原文件为权威**，**禁止**在任何 Markdown 复抄完整配置文件、维护 key→示例值全量大表或创建 `.env.example` 等示例副本；.md 只承担 ① 增量配置项的代码块片段 ② 全量配置文件的"路径+用途+维护方"索引。**唯一例外 = 约定 37 的发布期全量基线 `docs/deployment/{version}/配置文件/全量/`**（判据见细则片 5 的 37.7）。`部署流程.md` 与 `配置项清单.md` 不得双写配置项内容（流程讲怎么做、清单讲配什么，清单只讲本版改了什么）。`docs/deployment` 中数据库脚本与实际配置文件可随开发/修复实时更新；文档性内容仅版本规划/正式发布集中整理，日常不登记待同步引用，普通部署不为留痕改文件；备份与部署后核验属项目自有运维策略，AIDP 不要求。详规见 `{{AIDP_HOME}}/reference/部署操作约定.md`。

26. **★ Mock 实现位置选型优先级**（允许 mock 的合规场景）：P0 前端 mock 首选 / P1 后端运行时开关次选（禁 `@Profile("dev")` 等环境专属守卫）/ P2 中间件最后；口诀"前端能拦截就前端拦截"、后端接口未部署严禁写一次性假数据接口；**守卫策略按标记分流（⛔ 两类目的相反，绝不能混用）**——`THIRD_PARTY_MOCK`（第三方未交付、要活到 UAT/Demo）**必须运行时开关**、6 字段标注块必填，构建期守卫判 Critical；`DEV_MOCK`（同项目后端未部署、绝不能进生产）**应当构建期裁掉**（`import.meta.env.DEV` 即合规形态），3 字段（since/owner/REMOVE_WHEN），反给它套运行时开关才判 Important；≤30% 工时、全生命周期 4 阶段（切真实/清理须触发约定 22 文档级联，非只清代码）。**详规见 `{{AIDP_HOME}}/rules/code.md`（编辑 `code/**` 时自动加载）**；回检 = `code-verification-loop` 维度 2B（残留 Critical 回 `/sprint-bugfix`）+ `dev-manual-testcase`。

27. **★ 配置中心动态配置热刷新**（仅用配置中心的项目适用）：注入配置中心**可变**配置的组件（连接池/限流阈值/开关/第三方地址密钥等）必须支持**运行时热刷新**（无需重启即生效，如 `@RefreshScope`），长生命周期持有者避免缓存旧引用；仅启动期固定配置/纯逻辑类/服务发现不需要。**详规见 `{{AIDP_HOME}}/rules/backend.md`（编辑 `code/backend/**` 时自动加载）**；回检 = `code-verification-loop` 维度 4。

28. **★ 实现层"已有技术栈/组件复用优先"原则**：实现层优先用项目已有栈/组件（不强引原型用而项目无的库），**★ 作用域仅"实现选型层"（用哪个库/组件去实现），绝不豁免约定 4 的视觉+内容+操作逻辑三层对齐**——"用项目组件 ≠ 用组件库默认观感 ≠ 可砍内容/简化流程"；已有栈能满足禁引新库，不支持须 `AskUserQuestion` 同意 + 写 `systemPatterns.md` ADR。**详规见 `{{AIDP_HOME}}/rules/code.md`**；回检 = `code-verification-loop` 维度 4 grep 新增依赖是否在 baseline。

29. **★ 历史代码识别与处置**：开发同名/同语义模块前先核对历史代码。无菜单、无静态引用、无路由、显式重做仅是候选信号，须补查动态入口及实际可达性；未知保留。A 仍使用→按约定 28 复用；B 证据充分且不再使用→按清单删旧重写；C 仍使用且显式重构优先→兼容迁移，未获裁决不删。关联文件逐项证明独占引用，不能连带推定。详规见 `{{AIDP_HOME}}/rules/code.md`；判定入口 = `/sprint-dev` Phase 0A.5，回检 = `code-verification-loop` 维度 4。

30. **★ 命令 / Agent / 文档正文只陈述「最终行为」；版本号与变更历史收口归档**（强制）：`{{AIDP_HOME}}/commands/*.md`、`{{AIDP_HOME}}/agents/*.md`、**`{{AIDP_HOME}}/flows/**`、`{{AIDP_HOME}}/reference/**`、`{{AIDP_HOME}}/rules/**`**、`docs/init/*.md`、根级项目记忆文件（`AGENTS.md` / `CLAUDE.md`）/`README.md` 等指令/文档正文只描述当前该做什么（★ 契约正文的大头如今在 flows/reference/rules 三处，它们同受本条约束——**唯 `rationale.md` 例外**，那本就是承载「为什么这么定」的根因文件），**禁止**铺陈版本变更历史（"原来怎样→现在改成怎样→为什么"），**也不写任何范式版本号戳**（文件头 `AIDP Vx.y` / 标题 `（Vx.y）` / 页脚 `基于 AIDP Vx.y 范式` / 行内 `（Vx.y 新增）`/`Vx.y 起` 等一律不写）。

31. **★ CICD 与协作平台集成（多提供方，默认 GitHub Actions）**：**31.3 缺陷读取（可选）** = 用户主动提及 GitHub Issue 时用 `gh issue view/list` 读取后再修，未安装 `gh` 即跳过。**★ 31.5「推送分类与监听」**：先读 `aidp_config.py cicd-enabled`：未启用 → 推送只有 `git push`，不跑脚本、不落盘；已启用 → 推送前用只读 `classify_push.py` 现场分类（不落盘）：无正式代码变更 → 只校验 push 成功；有正式代码变更 / 分类缺失或出错 → 经 `cicd_watch.py` 监听 `cicd.provider` 的流水线至终态（commit 现场 `git rev-parse HEAD` 取得），主动重试及就绪探针先核 deploy 授权与剩余预算；CLI/凭据不可用时只 push、不监听。用户主动要求跑流水线同样适用。**详规见 `{{AIDP_HOME}}/reference/约定细则-3.md`**。

32. **★ 里程碑通知渠道装配**：里程碑通知统一经 `python3 {{AIDP_HOME}}/scripts/notify.py`（`--auto` 按 `memory/aidp-config.yaml` 的 `notify.channels` 依次尝试 `feishu` / `lark-cli` / `dingtalk` / `wecom` / `command`，成功即停）；`notify.enabled=false` 或未配置任何渠道（退出码 3）= 合规降级、静默跳过本播报节点，⛔ 不弹窗问人。**⛔ webhook 地址 / 签名密钥不得明文入库**：配置里只写环境变量名引用（`webhook_env: AIDP_FEISHU_WEBHOOK`、`secret_env: AIDP_FEISHU_SECRET` 等），真实值放本机环境变量。**详规见 `{{AIDP_HOME}}/reference/约定细则-3.md`**。

33. **★ 规划期基线类文档 → 测试期消费入口对账铁律**：AIDP 规划期强制产出多份**基线类文档**（version-auditor 规划期硬门保证产出 + 被上游设计覆盖），**测试期必须有对应消费者以基线为基准逐项断言**，否则"产出即沉睡"（卡片该删没删/列漏渲染/统计口径错〔已删数据仍计入〕/字段未脱敏等 AI 测试全绿却漏测）。

34. **★ 需求作废清算（跨版本 + ★ 同版本 / 同 Sprint 内口径反转；补约定 22「级联只版本内单向向下」的反向盲区）**：新结论推翻已写入文档的旧结论时（跨版本，或同一版本 / 同一 Sprint 内第二次口述反转第一次），必须清算所有引用旧结论的落点（需求条目 / ADR / 衍生论证 / 用例与断言 / 铁律 / 代码注释，关键语义词全库检索并留痕），被推翻条目加**显式作废标记指向新结论**、不静默改写，并**强制回答「旧口径下判定为安全的设计，在新口径下是否仍然安全」**。**★ 执行时机 = 两段式**：开发期当场只落作废标记（≤10 行）并把扩散面记进需求族增量册「已知失准点」，收口点才做全文订正。决策门落点 = `/sprint-dev` Phase 0B.1.3；**详规见 `{{AIDP_HOME}}/reference/约定细则-4.md`**。

35. **★ 运行时验证纪律（默认静态验证 + 当前任务相关单测；不擅自启动前后端服务、不完整构建——两类独立禁止项）**：开发/验证代码时按此默认（类型检查 / 语法 / lint / 确定性检查脚本 / 相关单测）。**除非用户显式要求，禁止** ① **启动任何前后端服务**（dev server 或后端常驻进程）② **执行完整打包构建**。**★ 静态验证工具被当作「零新增」判据前，必须先做一次阳性对照**（工具失效的形态恰是输出「0 错误」；`{{AIDP_HOME}}/scripts/check_*.py` 除少数需专用夹具的外均支持 `--self-check`，全量跑 `{{AIDP_HOME}}/scripts/selfcheck.py`（逐脚本报 pass/unsupported 并写明原因））。**★ 格式化类 autofix 只允许作用于【本次新建】的文件**，既有文件只手工消除自己引入的告警。**详规见 `{{AIDP_HOME}}/rules/code.md`（编辑 `code/**` 时自动加载；`约定细则-4.md` 只做回检与指针，不复述详规）**；回检 = `verify.py::check_project_claude_aidp_conflict` + `agents/frontend.md`·`agents/backend.md` 验证步骤。

36. **子 Agent 继承授权**：派发只是完成已授权动作的执行方式，prompt 必带父 execution_context、revision、action、budget、真实输入 hash 与写集。用户显式选定的持久策略才可复用；模板、命令路由名、旧 true 与宿主可调用能力均不构成 grant。未启用角色记 NOT_REQUESTED，已启用角色受实际宿主能力约束；同输入工具失败停止重试。唯一协议见 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md`，角色协作见 `{{AIDP_HOME}}/reference/约定细则-4.md`。

37. **★ 版本发布双轨部署基线（全量 + 增量；全量以「代码 × 真实环境」交叉核对为准、全程只读）**：`/version` 正式发布须为每个版本同时产出**增量轨**（已有环境怎么升级 = `sql/增量/` + `配置文件/增量/配置项清单.md`）与**全量轨**（从零怎么搭 = `sql/全量/` + `配置文件/全量/`，只跟最新代码走、不含 ALTER/迁移），**两套绝不叠加执行**，**零变更的版本同样要产全量**；`sql/` 与 `配置文件/` 根下不得直放两轨产物（`verify.py::check_deployment_two_track_layout` ERROR）。**详规见 `{{AIDP_HOME}}/reference/约定细则-5.md`**（与约定 25 的边界见 37.7）；编排落点 = `/version` Step 3.3.7.9（可 `--rebuild-baseline` 补跑），机器门 = `{{AIDP_HOME}}/scripts/release_baseline_check.py`。

38. **★ 开发期环境地址 / 账号即时归档到研发自测（用户随口给出即落库，绝不用完即丢）**：用户在**任意时刻**（含无命令的普通对话）给出**环境访问地址、登录账号密码、DB 连接**或**写操作授权**时，**必须在本轮就**归档到当前版本 `docs/testing/{version}/研发自测/01_测试环境与账号.md`（机器消费权威）并同步 `01_研发自测方案.md` §3；**生产 / UAT 凭据**改存 `memory/.sprint-autopilot-credentials.json`（chmod 600 + `.gitignore`）并须用户显式确认；写操作授权按「只读 / 可逆写 / ⛔ 不可逆写」三档登记，**未登记一律按只读处理（fail-closed）**。**详规见 `{{AIDP_HOME}}/reference/约定细则-5.md`**；显式补录入口 = `/sprint-selftest --capture`。

39. **★ 通用还原度规则集（R1–R13，与业务领域无关）**：把原型对齐从「整体判断」换成「逐项打勾」——**R1** 原型内容基线按六类逐项列出 · **R2** 状态取值视觉可区分 · **R3** 截断必配 tooltip · **R4** 破坏性操作二次确认 · **R5** 失效实体入口拦截 · **R6** 被引用实体删除后降级展示 · **R7** 加载未完成不渲染脏数据 · **R8** 编辑后视图自动同步 · **R9** 存量数据兼容验证 · **R10** 导出全量且与页面一致 · **R11** 数值字段五要素 · **R12** 同一指标跨页同源 · **R13** 列表页声明数据量级与分页。**详规见 `{{AIDP_HOME}}/rules/code.md` 约定 39**（含三段回检）；机器门 = `python3 {{AIDP_HOME}}/scripts/check_ui_fidelity.py`（R10 零豁免）。跨 SKILL 引用写全称 `约定39-RN`、严禁裸 `RN`。

40. **★ 上游/第三方接口调用日志强制规范（成功也要打；完整 URL + 入参出参；二进制只打元信息）**：调用**进程外**的第三方/上游依赖时（不含本地 DB 与缓存），**无论成功失败**都打印完整 URL + method + 入参与 status + 业务 code + 出参 + 耗时，请求响应可配对；**成功用 INFO、⛔ 不降级为 DEBUG**；二进制只打元信息、超长文本截断须标原始长度；**脱敏必须与本条同时落地**；实现上拦截器/过滤器优先、⛔ 禁止每个 client 各写各的。**详规见 `{{AIDP_HOME}}/rules/code.md` 约定 40**（后端接线见 `{{AIDP_HOME}}/rules/backend.md`，参考骨架见 `{{AIDP_HOME}}/reference/上游调用日志参考实现.md`）；机器门 = `python3 {{AIDP_HOME}}/scripts/check_upstream_call_log.py`，由 `/sprint-dev` Phase 1 Step 8 调用。

41. **light/formal 身份与动作边界**：自然开发/修复默认 light、implement+static+related-test；formal 保留编号、规格、归档，但不增授权。动作模型、budget、失败分类、hash 证据复用及 complete 配方统一见 `{{AIDP_HOME}}/flows/sprint-dev/light-context.md`。light 无 Sprint 卡/归档，不认领旧 Sprint；规模风险、复杂度、成本分别判断。未请求的额外审查/文档为 NOT_REQUESTED，默认相关测试不得借此跳过，不作欠账或 PASS。既有版本、破坏性、DB 授权和运行时纪律继续适用。
