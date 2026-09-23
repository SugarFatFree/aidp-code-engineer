# Task Templates（任务模板库）

> 本文件隶属于 `dev-execution-planner` SKILL，供 SKILL.md 生成具体 Task 时参考。
> 上级文档：`../SKILL.md`
>
> **使用说明：** Agent 生成具体 Task 前必须读取本文件，参考模板格式确保 Task 包含完整的执行步骤、产出物、验收标准等关键字段。
>
> ⚠️ **本文件模板演示的是 Task 的「内容要素」(执行步骤/产出物/验收标准等),不是最终交付格式。** 落地到执行计划时,每个 Task **必须**把这些内容封装进一个独立的「**AI 执行指令**」代码块(精确命令式,见 `quality-review-checklist.md` 维度 4 / 维度 14b 与 `iteration-plan-sample.md` 的标准 Task 写法),**严禁仅用"执行步骤 1/2/3"序号列表直接交付**(维度 4 判不通过)。

---

**中间件配置任务拆解示例(Task 1.2 的执行步骤):**

```markdown
### Task 1.2: 第三方中间件配置

**执行步骤:**
1. **检查并读取配置文件**(按优先级):
   - 优先执行 `test -f .env && cat .env` 读取本地覆盖配置
   - 若 `.env` 不存在,执行 `test -f .env.example && cat .env.example` 读取团队共享开发环境配置
   - 两者均不存在,向用户询问中间件连接信息
2. **(可选)创建/更新 `.env.example` 模板**——仅当调用方规范采用"示例副本"形态时；模板只登记键名和格式，不写入任何真实地址、账号、密码、令牌或密钥:
   ```
   # MinIO(开发环境)
   MINIO_ENDPOINT={待用户填写: MINIO_ENDPOINT}
   MINIO_ACCESS_KEY={待用户填写: MINIO_ACCESS_KEY}
   MINIO_SECRET_KEY={待用户填写: MINIO_SECRET_KEY}
   MINIO_BUCKET={待用户填写: MINIO_BUCKET}

   # Redis(开发环境)
   REDIS_HOST={待用户填写: REDIS_HOST}
   REDIS_PORT={待用户填写: REDIS_PORT}
   REDIS_PASSWORD={待用户填写: REDIS_PASSWORD}
   REDIS_DATABASE={待用户填写: REDIS_DATABASE}

   # Nacos(开发环境)
   NACOS_SERVER_ADDR={待用户填写: NACOS_SERVER_ADDR}
   NACOS_NAMESPACE={待用户填写: NACOS_NAMESPACE}
   NACOS_GROUP={待用户填写: NACOS_GROUP}
   ```
   > 说明：默认推荐只留键名与占位值；是否维护 `.env.example` 由调用方规范决定，详见本模板末尾「`.env.example` 是可选形态」。
   > 生产环境敏感信息一律不得写入示例文件。
3. 确认 `.gitignore` 包含 `.env` 行(开发者本机个性化覆盖配置不提交)
4. 在 `application.yml` 中引用环境变量(来源与优先级按项目既有规范):
   ```yaml
   minio:
     endpoint: ${MINIO_ENDPOINT}
     access-key: ${MINIO_ACCESS_KEY}
     secret-key: ${MINIO_SECRET_KEY}
     bucket: ${MINIO_BUCKET:project-dev}
   ```
5. 创建 `MinioConfig.java`、`RedisConfig.java`、`NacosConfig.java` 配置类,读取 Spring Environment 注入客户端 Bean
6. 按详细设计实现客户端健康检查逻辑(如有要求);开发期只做静态配置与代码验证，不启动被测服务
7. **静态验证配置闭环**(⛔ 不启动应用,见下方铁律):
   - 配置项已声明:`.env.example`/`.env` 里的每个键都能在 `application.yml` 找到 `${KEY}` 引用,反之亦然(无悬空键、无未声明引用)
   - 依赖已就位:`pom.xml`/`package.json` 含各中间件客户端依赖
   - 配置类可编译:后端**按 `stack-java-spring.md` >「二、开发期轻量验证」的判据选命令(⛔ 别直接写 `mvn compile`——它会跑完 generate-* 相、可触发前端全量构建)**;前端 `vue-tsc --noEmit` 通过
   - 执行 `python3 <SKILL_DIR>/scripts/check_env_config.py <项目根>` 通过
   - **真实连通性验证不在本 Task**:挪到部署后由部署流水线或 `/sprint-aiauto-test` 在真实部署环境做,本 Task 只保证"配置写对了、能被加载",不保证"对端活着"

> ⛔ **本 Task 严禁启动被测服务**(`mvn spring-boot:run` / `pnpm dev` / `npm start` / `docker compose up` 一律禁止)。
> 三条理由,每条都踩过:① 这类命令**前台常驻不退出**,写进 Task 会让执行会话就地阻塞;
> ② **抢占端口**,与开发者自己已经跑着的服务冲突(我方发生过 `npx vite` 抢端口把开发机拖卡的真实事故);
> ③ 中间件连不上是**环境问题不是代码问题**,在开发机上验它既不代表部署环境结论、失败了也无从修。
> 这与本 SKILL 贯穿全栈的「开发期验证 ≠ 发布期构建」铁律(`stack-index.md`)是同一条工程判据的两面:
> **开发期只做秒级、无副作用、可重复的静态检查**——不全量 build,更不起常驻进程。

**产出物:**
- `.gitignore`(确认包含 `.env`)
- `.env.example`(⭕ **可选产出物**——仅当调用方/项目规范采用"示例副本"这一形态时才产;详见下方「`.env.example` 是可选形态」)
- `src/main/resources/application.yml`(更新,使用环境变量引用)
- `src/main/java/.../config/MinioConfig.java`
- `src/main/java/.../config/RedisConfig.java`
- `src/main/java/.../config/NacosConfig.java`

**验收标准:**
- [ ] 配置项闭环:`application.yml` 的每个 `${KEY}` 都有来源,配置文件里的每个键都被引用(无悬空、无未声明)
- [ ] `.env` 不在 git 追踪中(`git check-ignore .env` 返回 `.env`),仅用于开发者本机覆盖
- [ ] 配置类能编译:后端**按 `stack-java-spring.md` >「二、开发期轻量验证」的判据选命令(⛔ 别直接写 `mvn compile`——它会跑完 generate-* 相、可触发前端全量构建)**;前端 `vue-tsc --noEmit` 通过。⛔ **不含"启动应用连接成功"**——那是部署后验证项
- [ ] `python3 <SKILL_DIR>/scripts/check_env_config.py <项目根>` 通过
- [ ] (采用示例副本形态时)`.env.example` 已提交且不包含任何生产环境密钥或敏感信息
```

> **`.env.example` 是可选形态,不是本 SKILL 强制的产出物。** 它有两种正当替代:
> ① **运行时配置文件即权威**(不维护示例副本)——配置项清单直接写进 Task 的"配置项闭环"验收,
> 避免"改了 `.env` 忘了改 `.env.example`"这类必然发生的双写漂移;
> ② **只留占位不留真值**——`.env.example` 仅列键名与格式说明,值一律占位。
> ⚠️ **禁止把开发或生产环境真实地址、账号、密码、令牌、密钥写入 `.env.example`**；示例文件只能保留键名、格式说明和占位值。
> **是否维护 `.env.example` 由调用方规范决定**,生成 Task 时按调用方规范落地;调用方没规定时,**默认选占位形态**。
> 对应地,`check_env_config.py` 在项目**根本没有** `.env`/`.env.example` 时按 **N/A 跳过**(`exit 0` + `skipped: true`),
> 不会给不采用该形态的项目一个恒红门。

### 第三方系统对接任务拆解规则

第三方系统对接的任务拆解规则(逐个接口独立成 Task、判定规则、第三方接口对接清单生成)与三类 Task 模板(我方对外开放接口 Phase 3 / 调用第三方封装 Phase 2 / 逐接口联调验证 Phase 5)以 `./flow-phase-split.md` >「第三方系统对接任务拆解规则」+ `./flow-edge-cases.md` >「情况 0:第三方平台接口未交付」为**唯一权威定义**,此处不重复(避免两处漂移;历史曾在此单列一份 slimmer 副本、与 SKILL.md 手工同步易失步)。生成第三方对接 Task 时按 SKILL.md 该章节执行,每个 Task 仍须封装为独立「AI 执行指令」代码块(标准范例见 `iteration-plan-sample.md` EPIC-02 的 Task 2.2~2.6 第三方五件套)。

### 每 Phase 末尾的验证任务(强制)

每 Phase 末尾验证任务表(Phase 1~5 的末尾验证示例与可执行指令)与「每个功能 Task 验收标准须含一项自动化检查点」的要求,以 `./flow-phase-split.md` >「每 Phase 末尾的验证任务(强制)」章节为**唯一权威定义**,此处不重复(避免两处漂移;历史曾因此处单列副本致 Phase 4 `--third-party-mode` 提示与 SKILL.md 不一致)。生成 Phase 末尾验证 Task 时按 `flow-phase-split.md` 该表执行。

## 优先级 / 约束

任务优先级(P0/P1/P2)与全部约束(禁止复用原型 HTML、任务原子化、依赖显式化、测试不可省略、接口全覆盖、Mock 数据分级清除、**金额字段类型守恒**等)以 `./flow-task-model.md` >「核心原则」(12 条全文)与 `../SKILL.md` >「优先级」「约束」章节为**唯一权威定义**,此处不重复(避免两处漂移;历史曾因此处单列约束漏掉"金额字段类型守恒"一条)。

## 输出格式

单用户 / 多用户分配 / 按内容量拆分多文档的输出格式,以 `../SKILL.md` > 「输出格式」章节为唯一权威定义,此处不重复。生成执行计划文档骨架时必须按 SKILL.md 该章节执行(含主文档头部"上游输入来源"五项溯源块)。
