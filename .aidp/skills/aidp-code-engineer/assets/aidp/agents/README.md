# .aidp/agents/ — AIDP 角色指令文件（**不是** Claude Code 原生 subagent 注册目录）

> ⚠️ **先读这一条，能省掉一整轮误解**：本目录下的 9 份 `.md` 是**角色指令文件**，
> 由执行体用 **`Read` 工具**加载后自己扮演该角色，或写进派发给子 Agent 的 prompt 里。
> 它们**没有 YAML frontmatter**，因此**不会**出现在 `/agents` 列表、也**不能**用
> `Agent({subagent_type: "backend"})` 这种注册式类型名调起。

## 为什么要专门说这件事

命令与 flows 里大量写着「派 **Backend Agent**」「激活 **version-auditor** Agent」。
这句话的**正确读法**是：

    用 `Agent` 工具派一个通用子 Agent（`general-purpose`），
    并在 prompt 里明确要求它「先 Read `.aidp/agents/<角色>.md`，按该文件逐项执行」。

**错误读法**是把 `backend` / `version-auditor` 当成已注册的 `subagent_type` 直接传——
那会拿到「未知 agent 类型」而不是想要的角色。两者的差别在报错上很明显，
但**在「派了一个没读角色文件的通用子 Agent」这种半对的情形下完全静默**：子 Agent 照样跑、
照样回结果，只是那份角色文件里的红线、写权限白名单、完成标准一条都没生效。

## 九份角色与归属

| 文件 | 角色 | 谁激活 |
|------|------|--------|
| `pm.md` | 产品经理 | `/sprint-requirements`、`/sprint-plan`（Step 2）、`/version`、`/sprint-init`、`/sprint-close` |
| `architect.md` | 架构师 | `/sprint-design`、`/sprint-init` |
| `ui.md` | UI / 原型 | `/sprint-design` Step 5.2（原型内容基线 / 设计令牌） |
| `frontend.md` | 前端开发 | `/sprint-dev` Phase 1.3 |
| `backend.md` | 后端开发 | `/sprint-dev` Phase 1.2 |
| `qa.md` | 测试验收 | `/sprint-test`（⛔ 只做静态与文档层验收，运行时归 `/sprint-aiauto-test`） |
| `reviewer.md` | 代码审查 | `/sprint-close` Step 2.5 |
| `aidp-compliance.md` | 范式合规 | 脚手架 init / migrate / upgrade 末尾 |
| `version-auditor.md` | 版本规划产物审计 | `/version` Step 2.4.7、autopilot Phase 3.3 build 终审 |

## 写权限边界

每份角色文件里的「管辖的文件（写权限白名单）」是**该角色唯一允许写的范围**。
跨角色写别人的白名单文件 = 违规（典型：Architect 去写 `NN_原型内容基线.md`——那归 UI）。
分工表的权威在 `docs/init/04_agents详细规范.md` §4.2，本目录各文件与它保持一致。

## 维护边界（约定 16）

本目录是**脚手架契约文件**，随 `aidp-code-engineer` 下发/升级同步——下游直接手改会在下次升级被覆盖。
需变更角色指令 → 改模板项目本体 → 镜像进 bundle。下游若需项目特化，
改用嵌套 `code/{子项目}/AGENTS.md`（Claude Code 下为 `CLAUDE.md`）承载。

⛔ **各角色的通用代码约定详规不写在这里**：约定 4/17/18/19/20/23/26/27/28/29/35/39/40 的正文
在 `.aidp/rules/{code,frontend,backend}.md`（按 `paths:` 自动加载）。
本目录只留**索引 + 角色专属要点**——复制详规必然双写漂移。
