# 任务详细程度标准(粒度判据 + 长示例)

> 本文件是 `SKILL.md`「第二步:任务拆解」的粒度判据分片,按需 Read。

## 详细程度标准（重要）

### 核心原则：零冗余,只引用

**执行计划是一份"路由表",不是"设计文档的拷贝"。**

详细设计文档才是技术真相的唯一源头。执行计划中**严禁**重复抄写设计文档已经定义过的内容(字段清单、表结构、接口 URL、Request/Response 字段、枚举值、错误码、状态机、校验规则、SQL 类型/长度/索引/约束、前端字段列定义等)。每个 Task 仅需:

1. **精确指向设计章节**(必填):`设计来源: <设计文档路径> > A.3 biz_user 表定义(L120-L180)`
2. **说明做什么**(做什么动作、走什么流程),**不说设计内容**
3. **让执行 Agent 在运行时读取设计章节**获取具体技术要素

> 任何需要在 Task 中展开的"字段清单/接口字段/枚举值/SQL 约束/表名字段名",都应替换为"按详细设计 `<章节+行号>` 定义实施"。

### 要写什么 ✅

- **数据库任务**:只写"按详细设计 `A.3 > {表名}(行号范围)` 定义创建表",**不列字段、不列索引、不列约束**
- **后端服务任务**:只写"按详细设计 `B.1 > {功规点}` + `B.3 异常容错` 定义实现 {ServiceName}.{方法名}",**不列字段、不抄业务规则原文**
- **API 任务**:只写"按详细设计 `B.2 > {接口编号}` 定义实现接口,URL/方法/请求/响应严格以设计为准",**不贴 URL、不列请求字段、不列返回字段**
- **前端任务**:只写"按原型 `[路径]` 布局创建 {PageName},按设计 `B.2 > {接口编号}` 对接后端接口",**不列表格列、不列表单字段、不贴接口路径**
- **前端任务(存在接口文档时)**:第一步必须是"扫描并删除该页面的 mock 数据"(见零 Mock 规则),后续步骤再"按设计对接真实接口"
- **执行步骤**:只写"读取设计 `<章节>` → 执行 `<指令>` → 对照设计核对",**步骤文案中不出现具体字段名、表名、URL、枚举值**
- **关键业务规则**:仅当设计文档未覆盖该规则时才写在 Task 中;已覆盖的全部用"参考设计 `<章节>`"代替
- **踩坑点**:仅写具体操作注意事项(如"CAS 协议必须用 getTicket() 不是 getCode()")这类**不属于设计文档**的技术陷阱

### 不要写什么 ❌

- 不要列数据库字段清单(`id, name, status, ...`)
- 不要列接口 URL、请求参数、返回字段
- 不要列枚举值、错误码、状态枚举
- 不要列前端表格列、表单字段、筛选条件
- 不要贴完整的 SQL DDL 语句
- 不要贴 Java/TypeScript 代码片段
- 不要贴完整的 JSON 请求/响应示例
- 不要贴 pom.xml / package.json / yml 配置内容
- 不要内联设计方案中的大段原文
- **不要在 Task 描述中复述"按设计文档 xxx 字段是 xxx 类型"这类设计已定义的技术细节**

### 判定标准

自问:"如果删掉这个 Task 中的技术细节描述,执行 Agent 能否通过读取 `设计来源` 指向的章节完整补齐?"
- 能 → 删掉,只保留"指向 + 动作 + 验收"
- 不能 → 说明设计文档不完备,先让用户补充详细设计

### 示例对比

**太模糊 ❌**：
```
- [ ] 创建工单表
```

**太详细 ❌**（冗余,抄了设计文档）：
```
- [ ] 创建工单表
  包含字段：id(BIGINT 主键), order_no(VARCHAR(32) 唯一), enterprise_id(BIGINT), title(VARCHAR(255))...
  索引：order_no 唯一索引、enterprise_id 普通索引...
  ```sql
  CREATE TABLE "biz_work_order" (
      "id" BIGINT NOT NULL IDENTITY(1, 1),
      ...50行SQL...
  );
  ```
```

**刚好 ✅**（只指路,不抄内容;用 AI 执行指令代替序号步骤）：
```
### Task 1.3: 创建工单数据库表

> **优先级**: P0 | **依赖**: Task 1.1
> **设计来源：** `<设计文档路径>` > `A.3 数据定义` > `biz_work_order 表(L150-L230)`

**目标**：创建工单上下文的数据库表。

**严格依据**：本任务必须严格按照详细设计 `A.3 > biz_work_order 表(L150-L230)` 实施,**字段、类型、长度、NOT NULL、DEFAULT、索引、注释全部以设计文档为准,本 Task 不在此处复述**。

**AI 执行指令**（将整个代码块复制到 Claude Code 等 AI 工具中执行）：

~~~
/dev-logic-architect

请完成 Task 1.3: 创建工单数据库表。

设计来源: <设计文档路径> > A.3 数据定义 > biz_work_order 表(L150-L230)
数据库: 达梦 DM8
依赖: Task 1.1(工程骨架)

要求:
1. 先读取上述设计章节,载入完整字段清单、索引定义、约束要求;
2. 生成 biz_work_order 的 DDL,字段名/类型/长度/NOT NULL/DEFAULT/索引/注释严格以设计为准,不得增删字段或修改类型;
3. 使用达梦 DM8 语法,BIGINT 自增主键;
4. 输出 DDL 到 `{SQL脚本目录}/v{版本号}/{两位序号}_工单表DDL.sql`(SQL脚本目录自适应项目现有目录,详见详细设计 Module D > D.1;中文命名 + 序号前缀,`99_` 保留给回滚脚本),并在达梦 DM8 执行验证;
5. 完成后对照设计 A.3 逐字段、逐索引、逐约束核对一致性。

约束:
- 严禁自行推断设计未覆盖的字段或索引,遇歧义暂停反馈;
- 遵守"字段宽容原则":仅在设计明确标注 NOT NULL 的字段加 NOT NULL,且必须有 DEFAULT 或应用层赋值保障。
~~~

> **指令来源**: L3 系统 Skill `/dev-logic-architect`
> **降级方案**: L4 `mvn mybatis-plus:generate`(若 Skill 不可用) / L5 手动编写 DDL

**产出物**:
- `{SQL脚本目录}/v{版本号}/{两位序号}_工单表DDL.sql`

**验收标准**:
- [ ] DDL 字段清单、类型、约束、索引与设计 `A.3 > biz_work_order 表(L150-L230)` 完全一致(字段/索引/约束不在此列出,以设计文档为准)
- [ ] DDL 在达梦 DM8 执行成功
- [ ] 执行 `python3 <SKILL_DIR>/scripts/check_ddl_consistency.py <DDL文件路径> <设计文档路径> --table biz_work_order` 通过(脚本第二参数为设计文档**文件路径**,用 `--table` 锁定表名;勿在路径后拼 `#A.3` 锚点)
```

**前端任务示例（存在接口文档时）✅**（零冗余 + AI 执行指令版）：
```
### Task 4.2: 工单列表页面

> **优先级**: P0 | **依赖**: Task 3.1, Task 3.2
> **原型来源：** [<WorkOrderListPage>(/work-order/list)](../docs/ui/code/work-order/work-order-list.html#work-order-list)
> **PRD 来源：** [§五-1 工单列表页(L220-L280)](../prd/工单管理.md#五-1-工单列表页)
> **设计来源：** [§B.1 FR-010(L420-L470)](../docs/design/总览.md#B-1-FR-010) + [§B.2 GET /work-order/list(L580-L620)](../docs/design/总览.md#B-2-GET-work-order-list)

**目标**：实现工单列表页面,对接后端真实接口。

**严格依据**：页面字段/筛选项/列定义以 PRD `五-1(L220-L280)` 为准;接口 URL/请求参数/返回字段以设计 `B.2 GET /work-order/list(L580-L620)` 为准。**本 Task 不复述 PRD 和设计中的字段、列、参数、返回结构**。

**AI 执行指令**（将整个代码块复制到 Claude Code 执行）：

~~~
/dev-logic-architect

请完成 Task 4.2: 工单列表页面。

原型来源: docs/ui/code/work-order/work-order-list.html  路由: /work-order/list
PRD 来源: <PRD路径> > 五-1 工单列表页(L220-L280)
设计来源: <设计文档路径> > B.1 FR-010(L420-L470) + B.2 GET /work-order/list(L580-L620)
依赖: Task 3.1(后端接口 GET /work-order/list)、Task 3.2(后端接口 DELETE /work-order/{id})
技术栈: Vue 3 + Element Plus + Pinia + axios(沿用项目已有脚手架)

要求:
1. 【清除 mock】扫描本页面涉及的全部 mock 数据/静态假数据/mock 工具配置并删除,禁止 mock 兜底;
2. 读取 PRD 五-1 载入页面字段、列、筛选项和交互要求;读取设计 B.2 载入接口契约;
3. 创建 WorkOrderList.vue,路由 /work-order/list,布局参照原型;页面字段、列、筛选项严格以 PRD 五-1 为准;
4. 对接后端接口:URL、请求参数名、返回字段解析严格以设计 B.2 为准,不得自行增减字段或改名,筛选条件通过 query 参数传递,禁止前端本地过滤;
5. 完成后对照 PRD 五-1 和设计 B.2 逐项核对:列定义、筛选条件、接口路径、请求参数、返回字段解析。

约束:
- 禁止复用原型 HTML;
- 禁止使用 mock 数据兜底真实接口失败;
- 遇设计/PRD 不明确处暂停反馈,严禁自行推断。
~~~

> **指令来源**: L3 系统 Skill `/dev-logic-architect`
> **降级方案**: L4 `pnpm create vite` + 手动编写(若 Skill 不可用)

**产出物**:
- `src/views/work-order/WorkOrderList.vue`
- `src/api/workOrder.ts`(更新,删除 mock,新增真实接口调用)
- `src/router/routes.ts`(更新,新增路由 `/work-order/list`)

**验收标准**:
- [ ] 已删除所有 mock/静态假数据,代码中无硬编码列表数据(执行 `python3 <SKILL_DIR>/scripts/scan_mock_data.py src/views/work-order src/api/workOrder.ts` 通过)
- [ ] 页面字段/列与 PRD `五-1(L220-L280)` 完全一致
- [ ] 接口调用的 URL、请求参数、返回字段解析与设计 `B.2 GET /work-order/list(L580-L620)` 完全一致
- [ ] 执行 `/code-verification-loop src/views/work-order` 通过
- [ ] 联调后端真实接口通过,列表数据从后端获取
```

---
