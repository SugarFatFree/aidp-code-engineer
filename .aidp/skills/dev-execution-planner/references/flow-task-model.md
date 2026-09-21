# 任务模型:任务模板 + 可用指令清单 + Phase 示例

> 本文件是 `SKILL.md`「核心原则」与「第二步:任务拆解」的细则分片,按需 Read。
> 承载 **12 条核心原则的完整正文**(SKILL.md 骨架只留每条一行结论速查,`item 0~11` 编号以本文件为准)+ 任务模板 + 5 级指令清单 + L2 Phase 级引用示例。

## 任务模板

```markdown
### Task {phase}.{seq}: {任务标题}

> **优先级**: P0/P1/P2 | **依赖**: Task X.Y 或 无
> **设计来源：** [§X.Y 章节名(L行号-L行号)](../docs/design/detail/{version}/xx.md#章节锚点)（**必填**,用于代码生成时严格对齐设计要求）
> **PRD 来源：** [§X.Y 章节名(L行号)](../requirements/{version}/研发需求/xxx.md#章节锚点)（如适用）
> **原型来源：** [<Component> 或 #锚点](../prototype/{version}/code/xxx.jsx#锚点)（如适用）
> **高保真来源：** [画板名](../prototype/{version}/mockup/xxx.fig#画板)（如有,用于前端 UI 还原）

**目标**：一句话说明要达成什么。

**严格依据**：执行本任务前,**必须先读取详细设计文档的指定章节**,代码实现必须与设计文档中的定义严格一致(字段命名、类型、校验规则、状态流转、接口契约、错误码、性能要求等)。如发现设计文档不明确或有歧义,必须暂停并反馈给用户澄清,**严禁自行推断或偏离设计**。本 Task **不在此处复述设计内容**,所有字段、接口、枚举、约束等技术要素以设计文档 `{设计来源}` 为准。

**AI 执行指令**（将整个代码块复制到 AI 工具中执行;以下示例以 Claude Code 为执行环境,其他支持 slash 命令的工具同样适用）：

~~~
{L1-L5 指令优先级中可用的最高层级命令}

请完成 Task {phase}.{seq}: {任务标题}。

设计来源: {详细设计文件路径} > {章节编号及名称} > {L 行号范围}
{如涉及 PRD: PRD 来源: {PRD文件路径} > {章节}}
{如涉及原型: 原型来源: {原型文件路径}}
{如有依赖: 前序产出: 基于 Task X.Y 生成的 {产出物}}

要求:
1. 先读取上述设计章节,载入完整技术要素(字段/接口/枚举/约束等);
2. 按 {指令优先级对应的工具} 生成代码,字段命名/类型/约束/URL/参数严格以设计为准,不得自行修改;
3. 完成后对照设计章节逐项核对一致性,发现偏差立即修正;
4. 输出到 {产出物路径}。

约束:
- 严禁自行推断设计未覆盖的技术细节,遇歧义暂停并反馈;
- {如 Phase 4 前端: 执行前先扫描并删除本页面的全部 mock 数据};
- {其他任务特定约束}。
~~~

> **指令来源**: {L1/L2/L3/L4/L5 + 工具名称,如 "L3 系统 Skill `/dev-logic-architect`"}
> **降级方案**: {下一层级的替代指令,如 "L4 `mvn mybatis-plus:generate`(若上层不可用)"}

**产出物**:
- 代码文件:`[具体路径]`
- 配置文件:`[具体路径]`(如有)
- 数据库变更:`[DDL 脚本路径]`(如有)

**验收标准**(至少包含一项自动化可执行检查):
- [ ] 代码实现与 `[详细设计文件路径]` 的 `[章节编号]` 章节定义一致,无字段/类型/规则偏差
- [ ] {可验证的检查项}
- [ ] 执行 `[具体自动化指令]` 通过
```

**核心原则(共 12 条,item 0~11):**

0. **零冗余(最高原则)** — Task 中**严禁**复述详细设计已定义的字段/接口/枚举/SQL 约束等技术细节,一律以"参考设计 `<章节+行号>`"代替。完整规则与正反示例见 `./flow-granularity.md` >「详细程度标准 > 核心原则：零冗余,只引用」。
1. **设计来源必须精确到章节 + 行号范围** — 不接受"参考详细设计"这类模糊引用,必须标注到"`<设计文档路径>` > `A.3 biz_user 表定义` > `L120-L180`"级别,方便执行代码的 Agent 快速定位
2. **必须有"AI 执行指令"代码块** — 每个 Task 必须包含一个 `**AI 执行指令**` 小标题及其下的 markdown 代码块;代码块内容 = AI 工具中的 slash 命令(或工具指令) + 完整提示词;用户复制整块即可投递到 Claude Code/Cursor/AIDP 等 AI 工具中执行
3. **AI 执行指令的首行必须是具体命令,不是描述** — 代码块第一行是可直接输入的指令,如 `/dev-logic-architect`、`/项目-api-gen`、`aidp gen:mapper --table biz_user`;不接受"请使用 xxx 工具"这类模糊描述
4. **命令选择必须遵循 5 级指令优先级** — L1 AIDP 命令 > L2 项目 `.claude/` 资源 > L3 系统 Claude Code 资源 > L4 通用工具 > L5 Shell 脚本,详见本文件「可用指令清单」
5. **提示词必须引用前序产出与设计章节** — AI 执行指令代码块内的提示词必须:(a) 显式引用依赖 Task 的产出;(b) 显式标注设计来源章节和行号;(c) 不复述设计中已定义的字段/接口/枚举等具体内容,仅以章节引用代替
6. **验收标准必须包含"设计一致性"检查** — 必须有一项验收检查代码与详细设计的一致性(如"字段名/类型/约束与 A.3 章节定义完全一致"),不得全部为功能性检查
7. **验收标准必须可自动化** — 至少一项验收标准是可通过命令执行验证的(如静态检查命令、研发自测用例 ID、`/code-verification-loop`;⛔ 不写需要启动服务的 `curl localhost` 类,见约定 35),不得全部为主观判断项
8. **产出物路径必须具体** — 不接受"生成用户管理代码"这类模糊产出物,必须精确到文件路径
9. **严禁偏离设计** — 若详细设计不明确或有冲突,Task 必须标注"⚠️ 设计待澄清",暂停实施,不允许 Agent 自行推断
10. **缓存确认 → 独立 Task(Critical)** — 仅当详细设计 A.2 章节存在「缓存方案」子章节(用户已确认使用缓存)时,才允许拆分缓存相关 Task;**严禁**详细设计未声明缓存方案的情况下,执行计划自作主张拆"添加 Redis 缓存"等任务。一旦设计已确认缓存,必须按以下 4 类拆分独立 Task,**严禁**将缓存逻辑混入业务接口 Task:
   - **a. 缓存中间件配置 Task**: 引入依赖 + 配置 `application.yml`/`config.yaml` 中缓存连接信息(host/port/password/database 走 `${ENV_VAR}`)+ 连接池参数 + Bean 初始化;验收"配置闭环通过、配置 Key 100% 走 ENV"；开发期不启动被测服务验证连通性
   - **b. 缓存层封装 Task**: 实现缓存 Service/Repository 接口(GET/PUT/EVICT),Key 命名规范统一前缀(如 `{project}:{module}:{biz_id}`),序列化方式统一,空值缓存防穿透;验收"Key 命名符合设计 A.2 缓存方案规范"
   - **c. 缓存失效与一致性 Task**: 数据更新接口同步触发缓存失效(`@CacheEvict` / 主动 delete);双写一致性策略(Cache-Aside / Write-Through);TTL 过期策略;验收"数据更新后 N 毫秒内缓存失效"
   - **d. 缓存监控告警 Task**: 命中率/失效率/慢查询监控指标 + 异常告警阈值 + 缓存击穿/雪崩防护(互斥锁/热点 Key 永不过期/随机 TTL);验收"监控大盘可见命中率指标"
   - **AI 执行指令引用**: 上述 4 类 Task 的 AI 执行指令必须引用详细设计 A.2「缓存方案」子章节具体行号,严禁自创缓存策略
   - **若设计无「缓存方案」子章节**: 执行计划仅拆业务接口 Task,**不**预埋"待加缓存"占位 Task;若开发后期发现性能问题需加缓存,触发设计返工流程(回 dev-logic-architect 走用户确认后再拆 Task),不在执行计划阶段绕过
11. **字段处置 → 独立 Task 拆分(Critical)** — 详细设计承接的「需求字段→处置对照表」(源自 PRD 需求字段清单,经 dev-logic-architect `B.2` 字段比对门透传;约定22 字段契约四级级联中本层为 L3「研发执行计划」)中,凡处置**不是「保留」**的字段,执行计划必须**显式承接**,**严禁**默默当「保留」字段排进常规接口/前端渲染 Task。按处置值分类拆分(与核心原则 10 同理:特定处置 → 强制独立 Task,严禁混入业务 Task):
   - **a. 前端计算还原 → 独立前端计算 Task**: 该字段后端接口**不返回**、需前端由其他字段派生/计算得出,必须拆**独立前端 Task** 实现派生逻辑(计算公式/规则来源详细设计对应章节行号),**严禁**混入常规列表/表单渲染 Task,也**严禁**误当后端返回字段去解析;验收"该派生字段展示值与设计计算规则一致"。AI 执行指令引用设计中字段计算规则章节,严禁前端自创公式。
   - **b. 请第三方补 → 关联第三方对接 Task**: 该字段需第三方接口补齐,纳入既有**第三方依赖 Task 机制**(见下文「第三方系统对接任务拆解规则」+「边界情况处理 > 情况 0:第三方平台接口未交付」;上游识别口径见 dev-logic-architect 核心原则 19「第三方依赖反向兜底识别」,本 SKILL 侧由「第一步半之二 > 反向兜底」跑 `check_third_party_dep_reverse.py` 承接),**严禁**假定本系统接口已含该字段;Task 标注"依赖第三方接口就绪",AI 执行指令引用设计中第三方契约章节。
   - **c. 裁剪 → 登记不实现、不静默保留**: 已确认裁剪的字段**不拆实现 Task**,但必须在计划中登记"该字段已裁剪(裁剪原因 + 产品确认状态)",**严禁**裁剪字段静默回流到接口/前端 Task 当保留字段;若处置标「待产品确认」,标注"⚠️ 字段处置待澄清"暂缓相关 Task,**不**自行推断保留或裁剪(对齐核心原则 9「严禁偏离设计」)。
   - **若详细设计无「需求字段→处置对照表」**: 执行计划**不臆造**字段处置,但须在上游引用核验中提示该对照表缺失(回 dev-logic-architect 补齐),避免「前端计算还原/请第三方补」字段在执行计划层**漏拆**独立 Task。

**AIDP 命令与 Claude Code 资源扫描流程(生成执行计划时必须执行):**

在生成任务拆解前,**必须**按指令优先级从高到低扫描以下五层资源,建立"可用指令清单":

**第 1 层:AIDP 命令与范式文档(最高优先级)**

1. 检查 `{{AIDP_HOME}}/` 目录或 `.aidp.yml`、`aidp.json` 配置文件
2. 检查项目根目录及 `docs/`、`doc/`、`{{AIDP_HOME}}/` 下的 `AIDP*.md` 文档(如 `AIDP.md`、`AIDP_范式.md`、`AIDP_规范.md`、`AIDP-README.md`、`AIDP_开发指南.md` 等),提取其中定义的:
   - 命令/脚本清单(如 `aidp gen:xxx`)
   - 代码生成范式(如命名约定、目录结构、生成器入口)
   - 约定的 Skill/Plugin 引用方式
3. 检查 `package.json` 的 `scripts` 字段(如 `"gen:api": "xxx"`)
4. 检查 `Makefile`、`justfile`、`taskfile.yml` 中定义的命令
5. 检查 `pom.xml` 的 plugin 配置(如 mybatis-plus-generator)
6. 检查项目 README 中"开发工具"、"代码生成"、"脚手架"章节

**第 2 层:项目 `.claude/` 下的 commands/skills/plugins/agents/mcp(次优先)**

扫描当前项目根目录下的 `.claude/` 配置,提取项目级 Claude Code 资源:
- `{{AIDP_HOME}}/commands/*.md` — 项目级 slash 命令(如 `/项目slash`)
- `{{AIDP_HOME}}/skills/*/SKILL.md` — 项目级 skill(含名称、description、触发条件)
- `.claude/plugins/` — 项目级 plugin
- `{{AIDP_HOME}}/agents/*.md` — 项目级 subagent 定义
- `.claude/mcp.json` 或 `.claude/settings.json` 中的 `mcpServers` — 项目级 MCP server
- `AGENTS.md` — 项目约定(可能包含命令使用规范)

**第 3 层:系统 Claude Code 的 commands/skills/plugins/agents/mcp(再次)**

扫描用户主目录下的全局 Claude Code 资源:
- `~/{{AIDP_HOME}}/commands/*.md` — 全局 slash 命令
- `~/{{AIDP_HOME}}/skills/*/SKILL.md` — 全局 skill(如 `/dev-logic-architect`、`/code-verification-loop`、`/api-tester`)
- `~/.claude/plugins/` — 全局 plugin
- `~/{{AIDP_HOME}}/agents/*.md` — 全局 subagent
- `~/.claude/settings.json` 中的 `mcpServers` — 全局 MCP server

**扫描产物**:在生成的执行计划开头列出"可用指令清单",按五层分组展示:
```

## 可用指令清单(按优先级)

### L1 — AIDP 命令与范式(项目专属,最高优先级)
- `aidp gen:mapper --table <name>` — 来源:AIDP.md 第 3 章
- `aidp scaffold:controller` — 来源:`.aidp.yml`

### L2 — 项目 .claude/ 资源(项目团队约定)
- `/项目-api-gen` — 来源:`{{AIDP_HOME}}/commands/项目-api-gen.md`
- skill: `project-entity-gen` — 来源:`{{AIDP_HOME}}/skills/project-entity-gen/SKILL.md`

### L3 — 系统 Claude Code 资源(全局)
- `/dev-logic-architect` — 来源:`~/{{AIDP_HOME}}/skills/dev-logic-architect/`
- `/code-verification-loop` — 来源:`~/{{AIDP_HOME}}/skills/code-verification-loop/`

### L4 — 通用工具命令
- `mvn mybatis-plus:generate`、`pnpm create vite` 等

### L5 — Shell 脚本(兜底)
- `bash scripts/xxx.sh`
```

**推荐使用跨平台扫描脚本(支持 Linux/macOS/Windows):**
```bash
# AIDP 命令扫描(L1 层)
python3 <SKILL_DIR>/scripts/scan_aidp.py [项目根目录]
python3 <SKILL_DIR>/scripts/scan_aidp.py [项目根目录] --json

# .env 配置合规检查(项目不采用该形态时 N/A 跳过 exit 0 + --json 出 skipped:true;
#                  团队规范强制要求示例副本时加 --require-env-example 把该项提回 Critical)
python3 <SKILL_DIR>/scripts/check_env_config.py [项目根目录]
python3 <SKILL_DIR>/scripts/check_env_config.py [项目根目录] --json
python3 <SKILL_DIR>/scripts/check_env_config.py [项目根目录] --require-env-example

# DDL 与详细设计 A.3 一致性检查
python3 <SKILL_DIR>/scripts/check_ddl_consistency.py <ddl文件.sql> <详细设计.md>
python3 <SKILL_DIR>/scripts/check_ddl_consistency.py <ddl文件.sql> <详细设计.md> --table biz_xxx --json

# 多文件拆分一致性检查(序号前缀/主文档/Task 编号唯一性)
python3 <SKILL_DIR>/scripts/check_doc_split.py <执行计划目录> --check-tasks
python3 <SKILL_DIR>/scripts/check_doc_split.py <执行计划目录> --check-tasks --json

# 从详细设计中提取第三方接口清单(涉及第三方对接时)
python3 <SKILL_DIR>/scripts/generate_third_party_checklist.py <详细设计文档> -o 第三方接口对接清单.md
python3 <SKILL_DIR>/scripts/generate_third_party_checklist.py <详细设计文档> --json

# 分析第三方接口对接进度(基于已填写的对接清单)
python3 <SKILL_DIR>/scripts/analyze_third_party_progress.py <执行计划文档>
python3 <SKILL_DIR>/scripts/analyze_third_party_progress.py <执行计划文档> --json

# 任务粒度 + EPIC 完整性 + AI 锚点检查(对应 QR 维度 3 + 维度 14)
python3 <SKILL_DIR>/scripts/check_task_granularity.py <研发执行计划路径>
python3 <SKILL_DIR>/scripts/check_task_granularity.py <研发执行计划路径> --json
# 退出码: 0 通过, 1 判错(警告与必修两档并入,分档读 --json 每条 finding 的 severity:1=警告 / 2=必修), 2 入参路径错(非维度违规)

# SQL 路径透传核验(对接 dev-logic-architect Module D, QR 维度 9 子项)
python3 <SKILL_DIR>/scripts/check_sql_path_handoff.py <研发执行计划路径>
python3 <SKILL_DIR>/scripts/check_sql_path_handoff.py <研发执行计划路径> --json
# 检测: 英文通用名禁止 / 版本子目录约束 / 中文+NN_命名 / 版本号一致 / 99_回滚配套
```

**使用原则**:每个 Task 中优先使用 L1 层资源;L1 层不满足时降级到 L2;L2 不满足时降级到 L3,依此类推。**同层资源同时可用时优先"项目专属"而非"通用",因为项目资源更贴合团队约定和代码仓库现状。**

**降级示例**:若项目无任何 AIDP 命令、范式文档或脚手架,退而使用项目 `.claude/` 下的资源,再退用系统 Claude Code 的 skill/plugin,最后才用通用工具命令。

**来源标注规则(四源原则,与本文件「L3 Task 级引用」一致):**

> **四源原则:** 每个 Task 必须在抬头标注完整的 "设计来源 + PRD 来源 + 原型来源 + 高保真来源(若有)" 四类上游引用(不适用项标"无")。**任一应填项缺失视为不通过**。这是下游迭代复盘、代码 review、测试用例反查的基础。

- **各 Phase 的"哪几源必填"差异**:以上文「L3 Task 级引用 > 按 Phase 的引用要求差异」表为**唯一权威**,此处不重复(避免两处漂移)。
- **路径要求**:所有路径使用仓库相对路径(示例:`docs/prd/xxx.md`、`docs/design/xxx.md`、`docs/ui/code/xxx.html`;实际路径自适应项目现有目录结构),不使用绝对路径
- **精确度要求**:不接受"参考 PRD"、"参考设计"等模糊引用,必须精确到 `<文件路径> > <章节编号及名称> > <行号范围>`
- **设计来源原则上不可省略**(因为所有代码实现都必须有设计依据);只有"调研型/调试型/纯运维型"任务可全部标"无",且需在 Task 描述中说明原因
- **高保真设计**:有高保真设计稿时,Phase 4 前端任务必须标注高保真设计文件路径,用于 UI 还原对照

### L2 Phase 级引用示例

```markdown
## Phase 1: 基础设施与数据层

> **本 Phase 主要参考:**
> - 详细设计: `<设计路径> > A.1 技术架构 + A.3 数据定义`
> - PRD: 不直接参考(纯技术任务)
> - 原型: 不参考

## Phase 4: 前端展示层

> **本 Phase 主要参考:**
> - 详细设计: `<设计路径> > B.2 API 契约定义`
> - PRD: `<PRD路径> > 五、页面交互明细 (全部页面)`
> - 原型: `<原型路径>` (全部页面 HTML)
> - 高保真: `<高保真路径>` (全部页面画板)(如有)
```

### L3 Task 级引用(每个 Task 必须的"四源原则")

> **四源原则:** 每个 Task 必须在抬头标注完整的 **设计来源 + PRD 来源 + 原型来源 + 高保真来源(若有)** 四类引用。**任一应填项缺失视为不通过**。

**Task 模板的引用部分(强制格式,必须 markdown 链接 + 相对路径 + 精细锚点):**

```markdown
### Task {phase}.{seq}: {任务标题}

> **优先级**: P0/P1/P2 | **依赖**: Task X.Y 或 无
> **设计来源:** [§X.Y 章节名(L行号)](../docs/design/detail/{version}/xx.md#章节锚点) ← **必填**
> **PRD 来源:** [§X.Y 章节名(L行号)](../requirements/{version}/研发需求/xxx.md#章节锚点) 或 标"无"(纯技术任务)
> **原型来源:** [<Component> 或 #锚点](../prototype/{version}/code/xxx.jsx#锚点) 或 标"无"(纯后端任务)
> **高保真来源:** [画板名](../prototype/{version}/mockup/xxx.fig#画板) 或 标"无"
```

**按 Phase 的引用要求差异:**

| Phase | 设计 | PRD | 原型 | 高保真 |
| :- | :-: | :-: | :-: | :-: |
| Phase 1 基础设施 | **必填** A.1/A.3 | 标"无"或 PRD 字段规格章节 | 标"无" | 标"无" |
| Phase 2 业务逻辑 | **必填** B.1/B.3/B.5 | **必填** 五-N 业务规则章节 | 标"无"或对应页面 | 标"无" |
| Phase 3 接口层 | **必填** B.2 接口编号 | **必填** 五-N 页面交互 | **必填** 触发按钮锚点 | 标"无" |
| Phase 4 前端 | **必填** B.2 接口编号 | **必填** 五-N 页面交互 | **必填** 页面文件+路由 | **必填**(若有) |
| Phase 5 测试 | **必填** B.3/B.5/C 章节 | **必填** 九、验收测试点 | 标"无"或对应页面 | 标"无" |

### L4 AI 执行指令内的引用透传(Task 提示词必填)

每个 Task 的 AI 执行指令代码块**必须**在提示词中重复引用:

```markdown
~~~
请完成 Task X.Y: <标题>。

设计来源: <设计路径> > <章节> (L行号-L行号)
PRD 来源: <PRD路径> > <章节> (L行号-L行号)
原型来源: <原型路径> (路由 X) #锚点
{如有依赖: 前序产出: 基于 Task X.Y 生成的 <产出物路径>}

要求:
1. 先读取上述【设计来源】章节,载入完整技术要素;
2. 对照【PRD 来源】核对业务规则,有冲突立即中断反馈;
3. {Phase 4 前端: 对照【原型来源】还原 UI 布局}
...
~~~
```

**严禁**只在 Task 抬头标注,而提示词内仅写"参考设计"——这会导致下游代码 Agent 无法定位。

### 引用格式标准化

| 引用类型 | 格式 | 示例 |
| :- | :- | :- |
| 详细设计(.md) | `<文件路径> > <章节编号> (L行号-L行号)` | `docs/design/总览.md > A.3 biz_user 表 (L120-L180)` |
| 研发 PRD(.md) | `<文件路径> > <章节编号> (L行号-L行号)` | `docs/prd/PRD.md > 五-1 用户列表 (L120-L150)` |
| 原型文件 | `<文件路径> (路由 <路由>) [#锚点]` | `docs/ui/code/user-list.html (路由 /user/list) #search-btn` |
| 高保真设计 | `<文件路径> > <画板名>` | `docs/design/用户列表.fig > "用户列表页" 画板` |
| 跨子文档 Task 依赖 | `Task X.Y(详见 ../<子文档> > Task X.Y)` | `Task 1.3(详见 ../01_Phase1.md > Task 1.3)` |

### 强制要求(违反任一即 Quality Review 检查项「上游引用完整性」不通过,详见 `references/quality-review-checklist.md`)

1. **主文档头部** 必须包含 5 个引用字段(设计/PRD/原型/产品文档/高保真),不适用项标"无"
2. **每个子文档头部** 必须包含同样 5 个字段
3. **每个 Phase 章节** 必须有 L2 Phase 级引用块,说明本 Phase 主要参考上游
4. **每个 Task 抬头** 必须标注 4 类来源(设计 必填;PRD/原型/高保真 按 Phase 要求填或标"无")
5. **每个 Task 的 AI 执行指令代码块内** 必须重复引用上述来源(透传给下游 Agent)
6. **路径必须为仓库相对路径**,不允许绝对路径
7. **不接受模糊引用**: ❌ "参考设计" / "参考 PRD" → ✅ `<设计路径> > A.3 (L120)`
8. **设计来源必须精确到行号**,不接受仅章节编号(因详细设计往往很长,行号是定位关键)

---
