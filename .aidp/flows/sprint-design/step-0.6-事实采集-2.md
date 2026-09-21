# sprint-design · Step 0.6 事实采集 — 分片 2/共3（代码现状清单 + 关联项目采集）

> 本片承接 `step-0.6-事实采集-1.md`。**本片覆盖范围**：Step 0.6.4.7（★ 扫描代码现状清单，Step 0.3 四象限"代码已实现"列源头）+ Step 0.6.4.8（★ 关联项目源码事实采集，含 0.6.4.8.1~0.6.4.8.3）。续见同目录 `step-0.6-事实采集-3.md`（0.6.5 事实清单模板 · 0.6.6 skill 硬约束）。
>
> ⚠️ **权威性**：进入本段后以本文件为准逐项执行，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-design/step-0.6-事实采集-2.md`。理据/根因见同目录 `rationale.md`。

---

**Step 0.6.4.7：★ 扫描代码现状清单**（代码作为最终事实源；为 Step 0.3 四象限对比提供"代码已实现"列）

> 编号说明：无 `Step 0.6.4.6`（编号保留，`0.6.4.7` 为稳定锚点、被多处引用，不回填改号）。

**★ 执行方式：一律经 `code_inventory.py`，⛔ 不手工 grep 全扫。**

```bash
python3 {{AIDP_HOME}}/scripts/code_inventory.py update            # 增量刷新（内容没变的文件零解析）
python3 {{AIDP_HOME}}/scripts/code_inventory.py render            # 渲染「代码现状清单」段 Markdown
python3 {{AIDP_HOME}}/scripts/code_inventory.py delta --since {prev_version}   # 本版相对上版新增/删除了哪些代码事实
```

> **Why 收编成脚本**：本步原文写死「全扫（不增量）」，产物又落在版本目录 `docs/design/detail/{version}/*事实清单.md`——
> **每版从零重扫、上版结论一点不复用**，是整条 `/version` 链路里唯一真正随累积增长的环节。
> 脚本把清单提到项目级 `memory/_facts/code-inventory.json` 并按内容 sha 增量维护：首跑全扫，
> 之后只重新解析**内容变了的文件**。实测 580 个源文件的真实项目，首扫 0.4s、无改动增量刷新 0.12s、
> 缓存 164KB —— 相比"让 AI 逐个 grep 再通读全量结果"是数量级差异。
> **`delta --since` 是规划期 Δ 裁剪的输入**：它直接回答"本版代码动了哪些实体"，
> 下游审计据此只对动过的部分做语义判断（同 `release-6.md` 全量设计的"变更重算 + 其余前滚"范式）。

扫描深度：**内容级增量**（首跑等价全扫；`--full` 可强制全量重扫）。脚本按以下规则提取功能/接口/表/页面级实体清单：

| 维度 | 扫描位置（按实际框架按需扫，未命中的不强求） | 提取字段 |
|------|---------------------------------|---------|
| **后端 API 端点** | Spring：`grep -rEn '@(Get\|Post\|Put\|Patch\|Delete\|Request)Mapping' code/backend/*/src/main/java/` 拿 method + path<br>Express/Koa：`grep -rEn 'router\\.(get\|post\|put\|patch\|delete)' code/backend/`<br>FastAPI：`grep -rEn '@(app\|router)\\.(get\|post)' code/backend/`<br>对应 Controller/View 类首行注释作为简述（旧扁平 `code/server/` upgrade 兼容）| method + path + 简述 + 文件:行号 |
| **后端数据库表** | 以 `docs/deployment/{version}/sql/增量/*.sql` + `docs/deployment/{prev-version}/sql/增量/*.sql` 全部 CREATE TABLE 为权威；ORM Entity（如 JPA `@Entity` / Mybatis Mapper `*Mapper.xml` / Sequelize Model）作辅助核对 | 表名 + 主要字段 + 来源 SQL 文件:行号 |
| **前端路由** | Vue Router：`grep -rEn 'path:.*name:' code/frontend/*/src/router/`<br>React Router：`grep -rEn '<Route .*path=' code/frontend/*/src/`<br>Next.js：`code/frontend/*/{src/,}{app,pages}/` 目录树（旧扁平 `code/web/` upgrade 兼容）| path + name + 对应 view 文件 |
| **前端页面** | `find code/frontend/*/src/{views,pages} -name '*.vue' -o -name '*.tsx' -o -name '*.jsx'` 拿文件清单；每个文件首个 `<template>` 注释或 `<h1>` 内容作页面标题（旧扁平 `code/web/` upgrade 兼容）| 页面标题 + 文件路径 |
| **配置文件**（参考）| `find code/ env/ docs/deployment/{version}/ \( -name 'application*.yml' -o -name 'application*.yaml' -o -name 'application*.properties' -o -name 'bootstrap*.yml' -o -name '.env*' -o -name '*.conf' -o -name 'docker-compose*.yml' -o -name 'docker-compose*.yaml' \) 2>/dev/null` 拿文件清单（**不展开配置项**，仅列文件作为线索；find 不支持 `{a,b}` 大括号扩展，必须每个扩展名单独 `-o -name`，外层 `\( ... \)` 包起否则 `-o` 优先级与目录混淆）| 文件路径 + 大致用途（后端/前端/部署） |

**输出**：`render` 出的 Markdown 直接写入事实清单的「代码现状清单」段（紧跟「路径消费者点」表之后），格式见分片 `step-0.6-事实采集-3.md` 的 Step 0.6.5 事实清单模板。
**落盘后补一次快照**：`python3 {{AIDP_HOME}}/scripts/code_inventory.py snapshot --version {version}`——下一个版本的 `delta --since {version}` 靠它算 Δ，漏打快照会让下版退回全量判断。

> **配置文件清单的边界**：本步骤**仅列文件路径作为线索**，**不展开具体配置项**——具体配置项的权威清单由 `/sprint-dev` Step X.7 维护到 `docs/deployment/{version}/配置文件/增量/配置项清单.md`（运维视角）。两者分工：本清单帮设计/开发"知道有哪些配置文件存在"；配置项清单帮运维"知道每个 key 改什么"。

**用途**：
- 直接作为 Step 0.3 四象限对比的"代码已实现"列输入
- 在 Step 1 调 skill 时一并传入（让 skill 知道哪些接口/表已存在，避免重新设计）
- /sprint-design 在补充模式下（`--supplement={NN}`）也跑此 Step，与 PRD-补充的新增项做"是否代码已实现"比对（决定是"代码超前-补写"还是"全新-需实现"）

**性能提示**：增量刷新通常 <1s（无改动时零解析）。⛔ **本步不设跳过旁路**——跳过会让四象限退化为只比设计基线（象限③「代码超前」恒不成立）。

**Step 0.6.4.8：★ 关联项目源码事实采集（跨项目复用识别）**

本项目若**消费兄弟/关联项目**（如同目录下的订单中心、用户中心等）提供的接口，这些接口的**真实可用性以对方源码为准，不依赖对方文档**（文档常滞后于代码）。本步骤扫描关联项目源码，把"对方已提供的接口"作为复用候选写入事实清单，避免下游设计把已存在的接口误判为"第三方未就绪 → 降级兜底 / 新造"。

**Step 0.6.4.8.1：确定关联项目源码路径（存 Claude 长期记忆，绝不入 git）**

> ⚠️ 关联项目源码路径**因开发者/机器而异**（同一仓库不同人 clone 到不同位置），**禁止写入 git 跟踪的 `memory/techContext.md` 或任何版本库文件**——只存 Claude Code 的**长期记忆**（跨会话、本机持久、不进版本库）。

1. 查 Claude **长期记忆**中本项目的「关联项目源码路径」记录。**有 → 直接用**。
2. **无** → 命令端用 `AskUserQuestion` 主动询问用户：① 本版本是否需要读取兄弟/关联项目源码做复用识别？② 若是，关联项目源码路径是什么（如 `../order-center`，可多个）？③ 该项目对本项目的角色（如"订单中心 order-center，本项目透传其对外接口"）。
3. 用户回答后**写入 Claude 长期记忆**（下次免问）；用户明确"无需关联项目"也记一条（避免重复问）。**绝不写入 `memory/techContext.md` 等 git 跟踪文件。**

**Step 0.6.4.8.2：扫描关联项目接口（穿透确认真实实现）**
对每个声明路径，按本项目可能消费的接口扫描（与 Step 0.6.4.7 同款框架适配），**穿透到 Service 实现层确认是真实业务实现而非占位**（throw 5xx / return null / mock）：

| 扫描 | 位置（glob，`<关联路径>` 为声明值） | 提取 |
|------|--------------------|------|
| 对方 Controller 端点 | `<关联路径>/**/src/main/java/**/*Controller.java`（Spring）/ `<关联路径>/**/*.controller.ts` 等 | method + path + 类#方法 |
| 穿透实现层 | 对应 `*ServiceImpl.java` / `*Service` | 是否真实实现（非占位）+ 出参字段 |

结合本项目 PRD / 研发需求 的数据需求，**匹配出"对方已提供、本项目正好要用"的接口**。

**Step 0.6.4.8.3：写入事实清单**
把命中的接口写入事实清单新「关联项目已有接口」段，每条标 `✅ 关联项目已提供（<项目>:<类>#<方法> → <path>，已穿透确认真实实现）`，并标注本项目对应的消费场景（如"总览页用量分析"）。Step 1 调 skill 时一并传入——下游 dev-logic-architect 据此按"复用类型 C：第三方接口复用 / ✅ 沿用关联项目现有接口"处理，严禁默判"未就绪 / 降级"（配合 dev-manual-testcase 与 dev-logic-architect 的 SKILL 侧「第三方依赖反向兜底识别」+「复用优先与去重」核心原则改造）。

> **边界**：仅扫描**用户声明**的关联项目路径，不自动遍历同级所有目录（避免误扫无关项目、噪音）；关联项目源码不可达（路径不存在）→ 降级为读 `docs/references/{version}/`（本版本对方资料）+ `docs/references/`（跨版本通用全接口文档）对方接口文档 + 标「⚠️ 源码不可达，依据文档（可能滞后）」。

