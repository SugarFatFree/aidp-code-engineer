# 质量自检清单(Author 侧 27 项)

> 本文件是 `SKILL.md` 的**作者侧自检**分片,按需 Read。
> ⚠️ **与 [`quality-review-checklist.md`](./quality-review-checklist.md) 是两套东西、编号不可换算**:本文件是**作者写完自己过一遍**的 27 项;那份是**独立 QR 子 Agent** 的 40 维度清单(其「检查项 11」对应本文件「自检 12」)。**刻意不合并**——合并会让既有的编号映射关系失效。

## 质量自检清单(Author 自检,27 项)

> **本节与 Quality Review Agent 40 维度的关系:** 本清单是作者侧的工程性自检(关注脚本辅助、文件结构、命名规范);下文 "Post-Generation Quality Review" 章节调用的独立 Agent 执行**业务/契约/溯源层面的深度审查**(完整 40 维度详见 `references/quality-review-checklist.md`)。两套清单**编号不一一对应**,但目标互补、共同保障详细设计质量。下表给出**简明映射**便于交叉查阅:
>
> ### ⚠️ 多套编号并存，且**映射是任意的——严禁靠算**
>
> 本 skill 内并行存在**三套**编号，**它们是不同的清单、不是同一份清单的几种叫法**：
>
> | | 编号叫法 | 项数 | 归属文档 | 谁执行 |
> | :- | :- | :-: | :- | :- |
> | ① | **自检 N** / 自查序号 N | **27** | 本文件（SKILL.md）本节 | 作者侧，生成设计时自查 |
> | ② | **检查项 N** / **维度 N** | **35** | `references/quality-review-checklist.md` | 独立 QR Agent，生成后复核 |
> | ③ | **`<脚本名>` 内部检查项 N** | 各脚本自定 | 各 `scripts/check_*.py` 的 docstring「检查项」列表（典型：`check_doc_split.py` 12 项） | 脚本自身 |
>
> **① 与 ② 不可换算。** 下表 24 条有映射的项里，`维度号 − 自检号` 的偏移取值遍布 **−16 ~ +8 共 10 种**
> （如自检 1→维度 9 是 +8、自检 21→维度 5 是 −16、自检 23→维度 8 是 −15），
> 且存在**一对多**（自检 6 → 维度 5 与 7）与**多对一**（自检 6、7 都 → 维度 5）；
> 另有 3 项自检无对应维度、**12 个维度**无对应自检项(见文末列表;条件启用的维度 33 同样无自检项,不计入这 12)。
> **凡需要在两套编号间转换，一律查本表，绝不做加减法。**
>
> **③ 与 ①②毫无关系**，只在该脚本内部有效（如 `check_doc_split.py` 的「检查项 7 文件名分隔符」
> 与 QR 维度 7「存量数据与兼容性」、自检 7「索引合理性」三者互不相干）。
> 引用脚本内部编号时**必须带脚本名**、且**只写「检查项」不写「维度」**，
> 例：`check_doc_split.py 检查项 7`；**严禁**裸写「维度 7」指代脚本内部项。
>
> 最常被误判的一处：**「字典/枚举强制生成枚举类(Critical)」= 自检 12 = 检查项 / 维度 11**。
> 交叉引用时请写成成对形式「自检 12（= 检查项 11）」，只写一个数字极易被后续维护者或
> 下游审计当成编号错误——这已实际发生过不止一次。
> 另一处实际发生过的错标：`check_http_client_config.py` 曾把 **自检 23**(HTTP 客户端配置驱动一致性，
> = 检查项 / 维度 **8**) 写成「维度 23」，而 QR 维度 23 其实是「缓存机制用户确认」——已修正。
>
> | 自查序号 | 自查内容 | Quality Review 维度 |
> | :-: | :- | :-: |
> | 1 | 功规点覆盖率 | 维度 9 PRD 功能点完整覆盖 |
> | 2 | 接口完整性 | 维度 2 接口契约对齐 |
> | 3 | 数据一致性 | 维度 2 接口契约对齐 |
> | 4 | 服务配置一致性 | — (工程自检独有) |
> | 5 | 模块划分合理性 | — (工程自检独有) |
> | 6 | NOT NULL 合规 | 维度 5 性能与边界 / 维度 7 存量兼容 |
> | 7 | 索引合理性 | 维度 5 性能与边界 |
> | 8 | 可空字段容错 | 维度 4 异常处理容错 |
> | 9 | 包组织规范 | 维度 13 包组织规范(仅 Java) |
> | 10 | 测试覆盖 | — (工程自检独有) |
> | 11 | 字典与枚举完整性 | 维度 10 字典枚举完整性 |
> | 12 | 字典/枚举强制生成枚举类(Critical) | 维度 11 字典/枚举强制生成枚举类 |
> | 13 | 多文件拆分一致性 | 维度 12 多文件拆分(仅多文件) |
> | 14 | 职责边界 | 维度 14 职责边界 |
> | 15 | 上游溯源完备性 | 维度 15 上游引用完整性 |
> | 16 | 货币金额字段检查 | 维度 17 货币金额字段整数化 |
> | 17 | 历史 SQL 风格沿用 | 维度 18 历史 SQL 风格沿用 |
> | 18 | 不臆造兜底 | 维度 19 不臆造兜底 |
> | 19 | ER 关系图与外键约束 | 维度 20 ER 关系图与外键约束 |
> | 20 | 索引列 NOT NULL 强制 | 维度 21 索引列 NOT NULL 强制 |
> | 21 | 文本字段长度冗余 | 维度 5 性能与边界 > 文本长度子项 |
> | 22 | 版本归档完整性(Module D) | 维度 22 Module D 版本归档完整性 |
> | 23 | HTTP 客户端配置驱动一致性(A.2 ↔ B.7 ↔ D.3) | 维度 8 外部依赖与集成说明(HTTP 客户端 4 个 Critical 子项) |
> | 24 | 缓存机制用户确认 | 维度 23 缓存机制用户确认(Critical) |
> | 25 | 审计字段操作人溯源与逻辑删除同步(Critical) | 维度 30 审计字段操作人溯源与逻辑删除同步 |
> | 26 | 接口错误契约完整性(Critical) | 维度 31 接口错误契约完整性 |
> | 27 | 并发加锁选型与数据库级锁确认(Critical) | 维度 32 并发加锁选型与数据库级锁确认 |
>
> **⚠️ 上表仅覆盖 27 项工程自检对应的 QR 维度。** 未在上表出现的 **QR 维度 1 / 3 / 6 / 16 / 24 / 25 / 26 / 27 / 28 / 29 / 34 / 35 / 36 / 37 / 38 / 39** 在 Author 侧无对应自检项,**由 Post-Generation Quality Review 独立 Agent 执行**——其中**维度 16(待澄清清单完整性)、24(原型版本基底对齐)、25(代码事实采集深度)、26(第三方依赖反向兜底)、27(复用识别完整性)、28(数据单位标注与转换)、29(需求字段对账闭环·接口环)、34(统计指标口径五要素)、36(业务计数声明表)、37(渲染层归并声明表)、38A/B(结论型断言证据来源)、39(新增列举证 + 重复性对账 + DDL 注释配对)均为 Critical;35(上游调用日志与脱敏声明)与 38C(禁令反向边界)是 Important 档——**缺表判 Important 不等于可以不补**,同样要过**。**严禁因"27 项自检已过"就认为这些维度已覆盖**,它们必须经独立 QR Agent 单独核验(脚本见 `references/quality-review-checklist.md` 对应维度;维度 29 配套 `check_field_impl_inventory.py` 做「字段实现清单」结构性反向覆盖回检;⚠️ **维度 29 与维度 39 方向相反、并存互补**——29 查**上游出处**(需求字段有没有落地),39 查**下游消费者**(新增的这一列有没有人读),⛔ 勿合并,语义层"研发需求字段是否逐字段落地"仍由 QR Agent 纯语义审查)。

完成设计文档后,执行以下自查(编号仅在本清单内有效,与 Quality Review 40 维度的对应见上表):

1. **功规点覆盖率检查** — 遍历 PRD 功规点列表，确认每一条都有对应实现描述。可使用跨平台脚本辅助: `python3 <SKILL_DIR>/scripts/validate_coverage.py <PRD路径> <设计文档路径>` (支持 `--json` 输出)
2. **接口完整性检查** — 确认所有前后端交互都有明确的 API 契约
3. **数据一致性检查** — 确认数据库字段与接口字段、前端状态字段的一致性
4. **服务配置一致性检查** — 确认前后端服务名称不重复，接口路径格式符合 `/{后端服务名称}/{接口路径}` 规范（不含 `/api/v1` 等版本号前缀）
5. **模块划分合理性检查**（微服务/多模块时）— 确认每个模块职责清晰，功能点分配合理，无交叉重叠
6. **NOT NULL 合规检查** — 逐一审查每张表的 NOT NULL 字段：(a) 是否属于"必须 NOT NULL"的场景（主键、强关联外键、唯一约束、审计字段、枚举状态），不属于则改为允许 NULL；(b) 每个 NOT NULL 字段是否已声明初始化方式（DEFAULT / 触发器 / 应用层必填标注），缺失则补充；(c) 不得因为"建了索引"或"PRD 标注必填"而设为 NOT NULL
7. **索引合理性检查** — 确认每个索引字段满足"高频查询 + 高基数"条件，低重复度字段（如 gender、status）未滥建独立索引(联合索引辅助列除外);**索引列的 NOT NULL 约束是核心原则 8 的强制例外,任何索引引用的列均强制 NOT NULL,详见自检 20 / 维度 21**(本项与自检 20 互补:本项关注索引"该不该建",自检 20 关注索引列"NULL 性")
8. **可空字段容错检查** — 确认设计方案中对允许 NULL 的字段，在功规点实现映射（B.1）中标注了代码层面的空值容错处理方式
9. **包组织规范检查**（**技术栈相关，按已选栈加载 `references/stack-*.md` 的对应节**；Java/Spring Boot 项目见 `stack-java-spring.md` §三）— 确认项目结构采用"**分层优先**"的包组织方式（`controller/`、`service/`、`mapper/`、`entity/`、`dto/`、`vo/` 平级），**禁止**在每个功能模块包下重复创建分层子包；DDD 架构项目例外，采用"限界上下文优先,分layers次之"
10. **测试覆盖检查** — 确认关键业务逻辑都有对应的测试用例
11. **字典与枚举完整性检查** — 对照 PRD 提取的所有字典/枚举字段,在 A.4 章节必须有完整定义(编码、显示文本、排序、默认值、应用场景、前后端对齐方案);PRD 中出现但 A.4 未定义的字典/枚举属于不通过项;**字典/枚举单独拆分时**还需检查:索引主文档(`05_字典与枚举索引.md`)存在且列出全局清单;编码在多个子文件间全局唯一不重复;A.3 数据表/B.1 功规点/B.2 API/B.5 状态机引用字典枚举时使用正确的相对路径和章节引用,锚点可定位
12. **字典/枚举强制生成枚举类检查(Critical)**〔本项 = `quality-review-checklist.md` 的**检查项 / 维度 11**，两套编号不可换算、见上「多套编号并存」〕 — A.4 中**每一个**字典/枚举条目必须满足下列要求,缺一即不通过:
    - (a) 明确声明对应的**后端枚举类名**(PascalCase + Enum 后缀,如 `OrderStatusEnum`、`PaymentMethodEnum`)
    - (b) 明确声明**后端枚举类文件路径**、(c) **前端枚举/常量类名**(PascalCase,如 `OrderStatus`)、(d) **前端枚举类文件路径**、(e) **前端定义方式**、(f) **数据库映射方式**、(g) **Mapper/ORM 引用** —— 这六项(b~g)的**取值随技术栈而定，按已选栈加载对应文件的「检查项 11」节**：`references/stack-java-spring.md`(Java 类路径 + MyBatis `TypeHandler` / JPA `@Convert`) / `stack-go.md` / `stack-python.md` / `stack-nodejs.md` / `stack-kotlin.md` / `stack-dotnet.md`；前端侧 `stack-vue.md` / `stack-react.md`(TS `enum` vs `as const` 的选择与路径约定)
    - (h) 每个枚举常量包含 `code` / `label` / `description` 三个必备字段;状态类枚举追加 `color` 字段
    - (i) 枚举常量名采用 UPPER_SNAKE_CASE
    - (j) A.3 数据表中所有枚举字段(如 `status`、`type`、`category`)的 COMMENT 引用对应枚举类(如 `参考 OrderStatusEnum`)
    - (k) 同一枚举的 code/label 在前后端一致,无前后端各自定义且取值不同的情况
    - **不允许例外**:即便枚举只有 2 个候选值(如 `启用/停用`),也必须生成枚举类,**严禁**业务代码中以裸字符串/裸数字判断
13. **多文件拆分一致性检查**(若采用多文件输出)— `00_索引.md` 必须列出所有内容文档及其内容摘要、生成时间、主/补充标识;子文档间的引用必须使用相对路径且锚点存在;版本号、术语、章节编号在主子文档间保持一致;数据库设计主文档必须包含"字典/枚举索引"、"API 端点全局索引"、"数据表全局索引"三类全局索引;**所有文档文件名必须以两位数字前缀开头**(`00_` ~ `99_`,`00_` 恒给专职索引 `00_索引.md`、内容主文档从 `01_` 起,无前缀视为不通过;历史裸 `00_<专题>.md`/`00_*_总览.md` grandfather 放行);**严禁碎片化**:除专职索引/索引文档外,无 **<150 行且 <6KB** 的子文档,存在则合并回上级模块(⛔ **是「且」不是「或」**——120 行但 8KB 的密集文档**不是碎片**;**口径与豁免集的唯一信源**见 `flow-output-format.md`「避免过度拆分(碎片化)」小节的口径块)。⚠️ **判据已有机器门**:下面这条命令**加上 `--check-fragment`** 即执行碎片检测;⛔ **不加那个开关时它不查行数/体积**——该脚本其余检查只管拆分结构与枚举名唯一性。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_doc_split.py <设计文档目录> --check-dict-enums --check-fragment` (支持 `--json` 输出)
14. **职责边界检查** — 详细设计文档全文不得出现研发执行计划、Sprint 排期、研发周期、工时估算、里程碑、上线日期、版本发布计划、人员分工等研发管理内容;不得将模块/功规点/接口/数据表绑定具体迭代版本号或交付日期;研发计划归 `dev-execution-planner` 处理
15. **上游溯源完备性检查** — (a) 主文档头部包含完整的"上游输入来源"四项(PRD/原型/产品文档/高保真),路径精确到文件;(b) 每个子文档头部包含同样的四项来源,不涉及则标"无";(c) B.1 功规点表每条标 PRD 章节+页码/行号、原型文件+路由(必要时锚点);(d) A.3 表 DDL 上方标 PRD 字段规格章节;(e) B.2 接口表每条标 PRD 页面交互章节 + 原型触发位置;(f) A.4 字典枚举每条标 PRD 字典枚举章节;(g) 严禁出现"参考 PRD"等模糊引用

**辅助脚本汇总:**
- `scripts/validate_coverage.py` — PRD 功规点覆盖率检查
- `scripts/check_ddl_consistency.py` — DDL SQL 与详细设计 A.3 字段一致性检查(执行计划/编码阶段亦可调用)
- `scripts/check_doc_split.py` — 多文件拆分一致性 + 字典枚举名全局唯一性检查
- `scripts/check_enum_contract.py` — A.4 字典/枚举代码契约 8 项必填字段合规扫描 + A.3 枚举字段 COMMENT 反向引用核验(对应自检 12 = 维度 11，两套编号不可换算)
- `scripts/check_money_field.py` — 货币金额字段整数化合规扫描(DDL + Markdown 表格双模式,对应自检 16 / 维度 17)
- `scripts/check_sql_style_consistency.py` — 历史 SQL 风格扫描与本次设计沿用一致性核验(对应自检 17 / 维度 18)
- `scripts/check_no_fabricated_fallback.py` — 不臆造兜底扫描:识别设计文档中的兜底关键词并输出疑似清单供人工溯源(对应自检 18 / 维度 19)
- `scripts/check_er_and_fk.py` — ER 图存在性 + DDL 中无 FOREIGN KEY/REFERENCES + 关联字段 COMMENT 完整性扫描(对应自检 19 / 维度 20)
- `scripts/check_index_not_null.py` — 索引列 NOT NULL + DEFAULT 哨兵值核验,联合索引整组核验,唯一索引零容忍 NULL(对应自检 20 / 维度 21)
- `scripts/check_text_field_length.py` — 文本字段长度冗余 3× 核验,识别自由输入字段 / 豁免字段 / TEXT 类型(对应自检 21 / 维度 5 文本长度子项)
- `scripts/check_sql_version_isolation.py` — Module D「SQL 版本严格隔离」铁律核验:V1 英文通用名禁止、V2 基线复制检测、V3 无变更不建目录、V4 中文命名+NN_ 序号(对应自检 22.f / 维度 22 子项)
- `scripts/check_http_client_config.py` — HTTP 客户端配置驱动一致性核验:A.2 落地完备性 + B.7 引用 A.2 配置 Key + D.3 依赖对齐 + 代码示例无硬编码 IP/URL/凭证(对应自检 23 / 维度 8 HTTP 客户端 4 个 Critical 子项)
- `scripts/check_cache_user_confirmed.py` — 缓存机制用户确认核验:扫描设计文档中的缓存关键词(Redis/Memcached/Caffeine/@Cacheable/MyBatis 二级缓存等),核验是否有 A.2「缓存方案」子章节、用户确认标注或 Module E 待澄清条目;豁免 HTTP 协商缓存/JVM 内置缓存等(对应自检 24 / 维度 23)
- `scripts/check_upstream_reference.py` — 三类元素(数据表 E1 / API E2 / 功规点 E3)段头部上游溯源覆盖率核验,E1/E2 的 R1+R2+R3 与 E3 的 R1+R2 覆盖率必须 ≥ 95%(对应自检 15 / 维度 15)
- `scripts/check_third_party_mock_runtime.py` — 第三方接口临时 Mock 运行时可控核验:扫描设计文档代码示例,检测构建期守卫反模式(`import.meta.env.DEV` / `@Profile("dev")` 等)与 THIRD_PARTY_MOCK 7 行标注块完整性(对应核心原则 14 / 维度 8 mock 子项)
- `scripts/check_service_impl_stub.py` — Service 实现层占位检测:扫描代码仓 `*ServiceImpl`,识别 6 类占位模式(throw 未实现/return null/mock 假数据/TODO 空方法/@Deprecated/仅日志),防止"伪沿用"(对应核心原则 18 / 维度 25)
- `scripts/check_third_party_dep_reverse.py` — 第三方依赖反向兜底识别:三向扫描代码 HTTP 客户端调用 + 配置文件外部 URL + 依赖清单 vendor SDK,与 PRD 正向识别取并集(对应核心原则 19 / 维度 26);`--aggregate` 同源聚合输出 `reuse_signals` 供复用核验(对应核心原则 20 / 维度 27)
- `scripts/check_feature_reuse.py` — 功能/数据/接口复用扫描:比对设计文档标 🆕 的实体/接口与代码仓已有实现,识别"设计标新增但代码已存在同义实现"的违规(对应核心原则 20 / 维度 27)
- `scripts/check_api_contract_alignment.py` — 接口字段级契约对齐核验:对标"✅ 沿用"的接口调用已部署后端抓取真实出参,比对前端消费字段集合,识别"接口能调通但出参缺字段"的伪沿用契约缺口(对应核心原则 18 / 维度 25)
- `scripts/check_unit_field.py` — 数据单位标注合规扫描:核验数值字段 COMMENT「单位:...」声明、百分比/时间字段单位歧义、字段后缀与单位一致性,防止后端返已转换展示字符串(对应核心原则 21 / 维度 28)
- `scripts/check_audit_field_fill.py` — 审计字段操作人溯源与自动填充核验:扫描设计文档,检测业务实体表是否带审计四件套、是否显式声明填充机制/操作人来源、是否交代逻辑删除同步 `update_by`/`update_time`,并抓取写死 `"system"` 反模式(弱机检·采集为主,对应核心原则 22 / 维度 30)
- `scripts/check_error_contract.py` — 「错误契约」结构性核验:每个接口是否有 5 列错误契约表(错误码 | HTTP Status | 触发条件 | 面向用户的中文提示 | 失败/降级行为)、中文提示逐行非空且无内部代号(`ops-service`/IP/URL)、失败降级行为逐行填实,并扫描「失败伪装成功(200/空数组/success:true)」与「安全判据 fail-open(取不到→放行)」两类文档级反模式(对应核心原则 23 / 维度 31)
- `scripts/check_lock_strategy.py` — 并发加锁选型合规核验:按 P0 进程内锁 / P1 Redis 分布式锁 / P2 数据库级锁三档识别加锁信号,查「数据库级锁无用户确认标注」与「分布式锁未声明自动过期」两类 Critical,另出「未说明为何 P0 不够」「有并发语境却无锁选型」两类告警;乐观锁与唯一索引幂等刻意不计入 P2(对应核心原则 24 / 维度 32)
- `scripts/check_field_impl_inventory.py` — 「字段实现清单」反向覆盖结构性核验:扫描详设,对每个列表/表单/详情页核查是否有一张「字段实现清单」表 + 表头 5 列齐全(`列名/字段 | 顺序 | 数据来源（接口字段） | 展示规则 | 上游出处`)+「上游出处」逐行非空;缺清单/缺列/上游出处空行 → 退出码非 0(对应维度 29 字段比对门反向覆盖 Critical 子项)。与 `check_upstream_reference.py`(正向溯源)方向相反、并存互补;语义层反向覆盖(研发需求字段是否逐字段落地)由 QR 子 Agent 判定
- `scripts/check_copy_landing_table.py` — 语义/口径变更类需求「文案落点表」结构性核验:扫描详设,检测到「文案落点表」(表头含 `改前文案`+`改后文案`)时校验表头 5 列齐全(`# | 文件路径 | 展示位 | 改前文案 | 改后文案`)+ 改前/改后文案逐行非空无占位(`待定`/`按实际调整`/`TBD` 等);缺列/空文案/占位 → 退出码 1,未检测到「文案落点表」→ exit 0 跳过(对应维度 29 字段比对门·文案落点姊妹子表 Critical 子项)。语义层覆盖(表 E 每个改写项是否落地 + 不改边界是否完整)由 QR 子 Agent 以上游「表 E」为基准判定
- `scripts/check_column_consumer_evidence.py` — 「新增列举证表」结构性核验:凡设计出现 `ALTER TABLE ... ADD`,核查是否有 6 列举证表(`列名 | 类型 | 业务含义 | 谁读它 | 不加会怎样 | 与既有近似列的区别`)、逐格填实、「谁读它」举得出**具体读取方**(「上游有这个字段」「以后可能要用」「备用」「预留」一律不算)、并与 DDL 双向对账(对应维度 39 Critical / 核心原则 32)。**须传目录**;缺表判 Important、表在而缺列或举不出消费者判 Critical
- `scripts/check_ddl_column_comment.py` — DDL 新增列注释配对核验:每个 `ADD COLUMN` 是否有配对列注释,**MySQL 内联 `COMMENT '...'` 与达梦/Oracle 独立 `COMMENT ON COLUMN t.c IS '...'` 两种方言形态都认**(只认前者会在国产库项目上静默失效)。**须传目录**(对应维度 39 Critical / 核心原则 32)

16. **货币金额字段检查** — 对照核心原则 11「💰 货币金额字段设计规则」,确认 A.3 所有金额字段类型为 BIGINT、COMMENT 含"单位:..."声明;多币种业务有 currency_code 字段;无 FLOAT/DOUBLE;DECIMAL 有降级理由;已有项目沿用现有约定并标注理由。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_money_field.py <设计文档路径>` (支持 `--json` 输出)
17. **历史 SQL 风格沿用** — 对照核心原则 12「历史 SQL 风格沿用」,若项目存在历史 SQL(`*.sql` / `migrations/` / `flyway/` / `liquibase/` 目录,或用户输入提供),确认: (a) A.3 数据表设计开头已添加"📜 历史 SQL 风格沿用说明"章节,列出本次沿用的具体约定; (b) 新表的命名风格(大小写/前缀/缩写)、公共审计字段命名、主键风格、索引/外键命名前缀、字符集/排序规则与历史多数表一致; (c) 风格冲突时已在沿用说明中标注处理理由(用户授权重构 / 按最近版本为准)。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_sql_style_consistency.py <代码仓根目录> <设计文档路径>` (支持 `--json` 输出)
18. **不臆造兜底** — 对照「⚠️ 不臆造兜底原则」,确认设计正文中所有"接口失败回退/默认数据/缺省值/降级方案/容错替代"等兜底语句都能在 PRD 中找到对应描述,或已显式打标 `🔧 暂行方案(Agent 推断)` 并汇总到 Module E 待澄清清单;严禁出现"真实接口失败回退到 mock 数据"的 mock 兜底逻辑;A.3 字段 NOT NULL DEFAULT(非时间戳/审计字段标准默认)的默认值必须能找到 PRD 来源。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_no_fabricated_fallback.py <设计文档路径>` (支持 `--json` 输出)
19. **ER 关系图与外键约束** — 对照 Phase 3「生成 A.3 数据表时必须附带 Mermaid ER 关系图」,确认: (a) A.3 章节(单文件)或每个数据域子文档(多文件)末尾有 Mermaid `erDiagram`,且多文件模式主文档有跨域全局 ER 图; (b) 图中表名/字段名与 DDL 一致,关联字段标 FK + 关联目标(如 `→ biz_user.id`),关系基数标准化(`||--o{` / `||--||` / `}o--o{`); (c) DDL 中**严禁**出现 `FOREIGN KEY` / `REFERENCES` 约束(关联完整性由应用层保证); (d) 关联字段(`_id` 后缀,主键 `id` 除外)的 COMMENT 必须标注关联表+字段。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_er_and_fk.py <设计文档路径>` (支持 `--json` 输出)
20. **索引列 NOT NULL 强制** — 对照核心原则 8 强制例外,确认: (a) 任何被普通索引/唯一索引/联合索引/主键引用的列均为 `NOT NULL`; (b) 这些列均有 `DEFAULT` 哨兵值(空字符串 `''`、`0`、`-1`、`'N/A'` 等;时间戳 `CURRENT_TIMESTAMP`、自增主键 `AUTO_INCREMENT` 免除); (c) 联合索引涉及的全部列整组核验,任一允许 NULL 整组违规; (d) 唯一索引列零容忍 NULL,无任何例外; (e) 业务语义"可空"但被强制 NOT NULL 的列,COMMENT 标注"索引列,空值用 X 表示"。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_index_not_null.py <设计文档路径>` (支持 `--json` 输出)
21. **文本字段长度冗余** — 对照核心原则 13「文本字段长度冗余原则」,确认: (a) 所有自由输入文本字段(`name` / `nickname` / `title` / `description` / `remark` / `content` / `address` 等用户可直接键入的 VARCHAR/CHAR 字段)的 DB 长度 ≥ 前端输入限制 × 3; (b) 字段 COMMENT 显式标注"前端限制 N 字符,DB 冗余 3×"或等价表述; (c) 豁免字段(强格式如手机号/身份证/邮箱、系统生成如 UUID/订单号、枚举 code、历史沿用、TEXT 类型)在 COMMENT 标注豁免理由(如"强格式,精确长度"/"系统生成,固定长度"/"枚举 code"); (d) VARCHAR 长度不超过 utf8mb4 单字段上限(约 16383),超出则改 `TEXT`; (e) 前端限制能在 PRD 字段规格表/页面交互章节找到来源,未定时 Module E 待澄清。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_text_field_length.py <设计文档路径>` (支持 `--json` 输出)
22. **版本归档完整性(Module D)** — 对照 Module D 章节,确认: (a) 单文件模式 Module D 章节存在,多文件模式 `20_版本归档.md` 文件存在; (b) D.1 交付物清单完整(设计文档、增量 SQL 脚本、接口文档、测试文档、配置文件 5 大类); (c) **增量 SQL 命名合规** — 文件采用中文命名 + 两位数字序号前缀,按 `{SQL脚本目录}/v{版本号}/` 子目录组织(**路径发现**: 按"路径占位符实施指南"章节扫描项目现有 SQL 文件位置确定,若无历史则使用 `db/migrations/` 并在 Module E 标注待确认);序号按执行顺序自增,不绑定文件类型;`99_回滚脚本.sql` 序号固定保留; (d) DDL 包含 `IF NOT EXISTS` / `IF EXISTS` 幂等性判断; (e) D.2 环境要求、D.3 第三方依赖、D.4 部署说明 3 个子章节齐全(D.4 若含构建打包,宜遵循「构建打包产物规范」:前后端产物尽量聚合为单一文件/压缩包、非可执行产物[非 exe/rpm/apk 等安装介质]文件名尽量不带版本号——属"尽量"偏好、非阻塞,SQL/接口文档等设计交付物的 `v{版本号}` 命名不受此约束;且后端服务打包须配套 `start.sh`/`stop.sh`(启动脚本后台启动 + 重复执行"先停后启"保持幂等、停止脚本优雅停止,详见 D.4「后端服务启停脚本规范」)); (f) **🛡️ SQL 版本严格隔离铁律(硬核)** — 详见下方 4 项 V1-V4 子项,任一违规即整体不通过。

23. **HTTP 客户端配置驱动一致性(Critical)** — 对照核心原则 16「HTTP 客户端配置驱动铁律」,确认: (a) **A.2 落地**: 若 Phase 1 Step 3 选择 3 已选定 HTTP 客户端,A.2 章节包含「HTTP 客户端落地」子章节,提供 Bean/Client 初始化示例 + 完整配置块(`application.yml` / `config.yaml` / `.env` / `appsettings.json` 之一,随后端语言对应)+ 服务发现集成声明; (b) **配置 Key ENV 占位**: 所有第三方 base URL / IP / 端口 / API Key / Secret / 私钥在配置块中均为 `${XXX_KEY}` 形态,严禁明文; (c) **B.7 引用 A.2**: B.7 每个第三方集成项标注所选 HTTP 客户端方案(与 A.2 一致),并引用 A.2 中的具体配置 Key(如 `third-party.alipay.base-url`),不允许 B.7 重复定义配置; (d) **D.3 依赖对齐**: D.3 后端依赖列出所选 HTTP 客户端依赖(Java OpenFeign 时列 `spring-cloud-starter-openfeign` + Nacos Discovery + 熔断组件;Go/Python/Node/.NET 类似),版本与 A.2 示例一致; (e) **代码示例无硬编码**: A.2 / B.7 示例代码中不出现 `@FeignClient(url = "http://192.168.x.x")`、`new Uri("http://localhost:8080")`、`base_url="https://api.example.com"` 等硬编码 IP/URL,亦不出现明文 API Key/Secret; (f) **服务发现集成**: 若使用 Nacos/Eureka/Consul/etcd,A.2 声明服务名 + 命名空间 + 分组,B.7 标注"是(走服务名 `xxx-service`)";直连第三方时 B.7 标注"否(直连域名,通过 `application.yml > xxx.base-url`)"。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_http_client_config.py <设计文档路径>` (支持 `--json` 输出)

24. **缓存机制用户确认(Critical)** — 对照核心原则 17「缓存机制用户确认原则」,确认: (a) **零关键词或全标注**: 设计文档中所有缓存关键词(`Redis` / `Memcached` / `Caffeine` / `EhCache` / `Hazelcast` / `Spring Cache` / `@Cacheable` / `@CacheEvict` / `@CachePut` / `RedisTemplate` / `Redisson` / `CacheManager` / `MyBatis 二级缓存` / `<cache/>` / `Hibernate L2` / `JPA @Cacheable` / 本地缓存 / 多级缓存 / 缓存层 / 缓存 TTL / 缓存失效 / 缓存预热 / 缓存击穿 / 缓存雪崩 / 缓存穿透)出现处,均能找到三个证据之一: 证据 A: A.2 存在「缓存方案」/「缓存设计」/「缓存策略」子章节(用户已确认); 证据 B: 关键词所在段落或前 30 行内出现"用户同意" / "用户确认" / "已征得用户同意"; 证据 C: Module E 存在 `🔧 暂行方案(建议使用缓存,待用户确认)` 或 `❓ 待澄清` 条目并双向引用; (b) **A.2 缓存方案完备性**: 若有「缓存方案」子章节,必须含 ① 缓存中间件选型 + 版本 ② Key 命名规范 ③ TTL 策略表 ④ 一致性保障(失效策略 / 双写 / Cache-Aside) ⑤ 防护机制(穿透/击穿/雪崩) ⑥ 监控指标; (c) **ORM 二级缓存核验**: MyBatis `<cache/>` / Hibernate `cache.use_second_level_cache=true` / JPA `@Cacheable(true)` 等 ORM 隐式缓存必须在 A.2 显式声明; (d) **接口缓存标注一致**: B.X 接口设计章节标注 `[缓存: ...]` 时,Key 命名 / TTL / 失效策略必须与 A.2 缓存方案一致; (e) **D.3 依赖对齐**: 接口设计标注缓存或 A.2 含缓存方案时,D.3 后端依赖必须列出对应缓存中间件依赖(如 `spring-boot-starter-data-redis`); (f) **豁免场景**: HTTP 协商缓存(`Cache-Control` / `ETag` / `304`) / JVM 内置缓存(常量池 / 方法内联) / 浏览器静态资源缓存 / 数据库连接池语句缓存 / CDN 边缘缓存(无服务端代码改动) / DNS 解析缓存 — 这些不需要用户确认。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_cache_user_confirmed.py <设计文档路径>` (支持 `--json` 输出)

25. **审计字段操作人溯源与逻辑删除同步(Critical)** — 对照核心原则 22「审计字段操作人溯源与自动填充铁律」,确认: (a) **业务实体表覆盖**: 有增删改的业务主表均带审计四件套(`create_by`/`create_time`/`update_by`/`update_time`)+ 逻辑删除标记;字典/枚举/中间/日志表豁免须在 A.3 标注理由; (b) **填充机制显式**: A.3/A.2 显式写明填充机制(优先 MetaObjectHandler / JPA Auditing)+ 操作人来源(当前登录态如何取得),不留空让下游各自实现; (c) **禁写死 system**: `create_by`/`update_by` 无字符串字面量硬编码(`"system"`/`"admin"`)作通用默认; (d) **逻辑删除同步**: 逻辑删除接口/时序显式交代同步更新 `update_by`/`update_time`,并提示"逻辑删除走自定义 SQL/直接 UPDATE 会绕过 ORM 自动填充"的风险; (e) **system 兜底显式**: 仅定时任务/数据初始化/无登录态场景用固定 `system` 账号且显式标注场景与取值来源。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_audit_field_fill.py <设计文档路径>` (支持 `--json` 输出)

26. **接口错误契约完整性(Critical)** — 对照核心原则 23「错误契约铁律」,确认: (a) **每接口有错误契约小节**: B.2 每个接口均有固定 5 列表`| 错误码 | HTTP Status | 触发条件 | 面向用户的中文提示 | 失败/降级行为 |`,逐行填实不留空,无旧版「错误码 | HTTP Status | 说明」三列表; (b) **三态判然区分**: 小节写明本接口空结果形态(`code=0` + 空集合 = 合法成功),全文无「失败/超时 → 返 200 / 空数组 / `success:true`」表述; (c) **上游失败契约**: 调上游的接口有「上游不可达」行,文案为「{上游中文名}服务无法连接,请稍后再试」,服务名是业务中文名、无内部代号/IP/URL;确需降级处已就地写明降级理由 + 范围 + 用户可感知性; (d) **安全 fail-closed**: 鉴权/权限/归属/签名判断声明「取不到/解析失败/查询异常 → 拒绝或报错」,无「取不到就不过滤/默认放行」类 fail-open 表述; (e) **上游契约权威**: 引用上游/第三方契约处标注「以上游契约为准,上游变更即需跟进」+ 来源与采集时间。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_error_contract.py <设计文档路径>` (支持 `--json` 输出)

27. **并发加锁选型与数据库级锁确认(Critical)** — 对照核心原则 24「并发加锁选型优先级铁律」,确认: (a) **落档 + 理由**: 有并发临界区的场景在 B.3 落到 P0/P1/P2 具体档位并写明选择理由; (b) **P0 优先**: 单进程内竞争用语言自带锁(各栈写法见 `references/stack-<栈>.md`「核心原则 24 落地」);升到 P1/P2 已写明 P0 为何不够(多实例/跨进程竞争); (c) **P1 必带自动过期**: 原子加锁(`SET NX PX`/Redisson,禁先 SETNX 再 EXPIRE)、TTL/leaseTime、长任务续期、释放校验持有者、获取失败行为 + 错误码; (d) **P2 必须人为确认**: 数据库级锁(`FOR UPDATE`/`LOCK TABLES`/`GET_LOCK`/悲观锁/行锁/表锁)有用户确认三证据之一(正文标注 / 专章 / Module E D-NNN); (e) **乐观锁不误判**: version+CAS、唯一索引幂等属无锁并发控制,不计入档位、无需确认门。可使用脚本辅助: `python3 <SKILL_DIR>/scripts/check_lock_strategy.py <设计文档路径>` (支持 `--json` 输出)

#### 22.f SQL 版本严格隔离铁律(Critical 硬核子项)

> **背景:** 实测发现详细设计落地的 `code/sql/v{版本}/init.sql` 单文件,头部 32 行注释声明"本期增量",中段 82 行**完整复制上一版本基线**(注释自陈"上半段为前版本完整复制,保证单文件可还原")。这种"基线泄漏 / 多版本 DDL 重复"反模式让"哪些是本版本新增"无法判定。

**核心判定(哪些算违规,任一命中即整体不通过):**
- **V1** — `code/sql/v{当前版本}/` 出现 `init/schema/migration/baseline/database/all/full/setup.sql` 等英文通用名
- **V2** — 当前版本 SQL 与上一版本 SQL 重复行 ≥ 10(基线复制),Critical 阻塞(原始 `comm -12 | wc -l` 法阈值;`check_sql_version_isolation.py` 已先过滤模板/语法噪声,等价阈值为业务行 ≥ 5,两者判定强度相当)
- **V3** — 本版本无 DDL/DML 变更却创建了空 `v{版本}/` 目录或放空 init.sql/注释 SQL 占位(无变更应不建目录,或仅放 `00_README.md` 一句话说明)
- **V4** — 文件名不符合 `{NN}_{中文描述}.sql`(如 `01_用户表DDL.sql`),或 `99_` 序号未固定用于回滚脚本

> **完整 V1-V4 隔离清单(检测内容/违规判定逐项展开)与不通过标志核验矩阵详见** `references/quality-review-checklist.md` 检查项 22(权威)。本节与检查项 22 内容一致,以检查项 22 为准。

**bash 等价硬核回检命令:**

```bash
# V2 基线复制核验
comm -12 <(sort code/sql/v{prev}/*.sql 2>/dev/null) <(sort code/sql/v{current}/*.sql 2>/dev/null) | wc -l
# 重复 ≥ 10 行即不合规

# V1 英文通用名核验
ls code/sql/v{current}/*.sql 2>/dev/null | grep -E '/(init|schema|migration|baseline|database|all|full|setup)\.sql$'
# 命中即不合规

# V4 中文命名核验
ls code/sql/v{current}/*.sql 2>/dev/null | grep -vE '^code/sql/v[^/]+/\d{2}_[一-龥].*\.sql$'
# 命中即不合规
```

**自动化脚本(必跑):**

> **`<SKILL_DIR>` 占位符:** SKILL 实际安装位置(本项目 = `.aidp/skills/dev-logic-architect`),由 Agent 在执行前替换。

```bash
python3 <SKILL_DIR>/scripts/check_sql_version_isolation.py \
  <部署根目录 或 SQL根目录> --version <当前版本>
# AIDP 双轨布局传 docs/deployment(自动识别 {version}/sql/增量|全量,递归扫描;V2 只比增量轨)
# 扁平布局 {SQL根目录}/{version}/*.sql 传 SQL 根目录;可显式 --layout two-track|flat
# 退出码 0 = 通过, 1 = 不通过
```

**Why:** 单文件不需要"完整可还原" — 部署侧按版本顺序逐个 apply。基线泄漏导致部署侧无法判定哪些是本版本新增、哪些会与上一版本冲突;多版本 DDL 重复也增加了对账成本。设计阶段直接拦截。

---
