# sprint-bugfix · 方式 B 详情（独立修复已记录的 bug — ★ 最常用）

> 本文件是 `/sprint-bugfix` 命令 **方式 B（独立修复已记录的 bug）** 的完整详细步骤，由命令主体（`.aidp/commands/sprint-bugfix.md`）在**判定为方式 B 时用 Read 工具按需加载**——把这一段（前置准备 / 独立使用流程 / 执行步骤 Step 1–6）从"每次调用整体入上下文"改为"走到方式 B 才载"，降低"lost in the middle"式漏步。命令主体只保留方式 B 的**骨架表 + 关键规则 + 指向本文件的指针**。
>
> ⚠️ **权威性**：进入方式 B 后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤（Step 0 口述 bug 与来源 B 先落记录 / Step 1 调 bugfix skill〔附项目级专项〕 / Step 2 推送分类与监听 / Step 3 回填状态与报告链接 / Step 4 编译·前端校验 / Step 5 回写设计文档 / Step 5.1 累进产物审计 / Step 5.5 P0·P1 反哺回归用例 / Step 6 更新 activeContext）。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-bugfix/mode-b.md`。理据/根因见同目录 `rationale.md`。

---

## 方式 B：独立修复已记录的 bug（★ 最常用）

### 前置准备

读取以下文件了解项目上下文：

项目级：
1. `memory/systemPatterns.md` — 代码规范
2. `memory/techContext.md` — 技术栈信息
3. `docs/architecture/` — 全目录：架构约束三件套 + 可选架构设计文档（单/多文档）

迭代级：
4. `memory/{version}/{user}/activeContext.md` — 当前状态
5. `docs/design/detail/{version}/` — 详细设计
6. `docs/design/detail/{version}/*事实清单.md`（如存在）— ★ 端口/context-path/proxy 真值 + **「路径消费者点」表 + 反模式提示**
   - 如 bug 标题 / 描述 / 现象包含 **路径 / URL / 404 / proxy / baseURL / context-path / 双前缀 / cors / 跳转** 等关键词 → 必须**精读「路径消费者点」表和「反模式提示」段**，按这些线索定位根因，避免只改一处而漏改级联消费者
7. `docs/design/detail/{version}/对外开放接口.md`（如存在）— ★ 当 bug 涉及对外接口时**必读**；修复时**红线**：不允许通过引入 Session/Cookie/JWT 实现"快速修复"（由 /sprint-design Step 1.7 检查项 2 强制，重跑会把违规改动判为告警）；幂等键/限流/审计 3 项规范的回归修复必须维持 9 项要素的完整性。**本地 MD 始终为权威**（同目录如有 `openapi.yaml` 则是由它派生的机读副本）；本次修复**若改了本地 MD 正文**，`openapi.yaml` 将落后于本地——下次 /sprint-design 重跑会检测 SHA256 变化并询问是否重新生成，或人工跑 Step 6.5 单独重新生成

### 独立使用流程

**无需依赖任何 Sprint 流程**：

1. 用户在 `docs/bugfix/{version}/bugfix-{今日}-{user}.md` 手动添加 bug 表格行和详情章节
2. 执行 `/sprint-bugfix`，Claude 自动：
   - 扫描当前用户的所有 bug 文件
   - 筛选状态为「Open 待修」或「待修复」的条目
   - 按优先级修复（P0 > P1 > P2 > P3）
   - 回填修复信息到 bug 文件
   - 编译（后端）/ 前端校验（lint + 类型检查，不打包；仅本次改动侧 + 资源受限）
3. 修复完成后，bug 状态自动更新为「Fixed 已修」

**Sprint 序号字段**：
- bug 表格中的 Sprint 列可以为空（普通的孤立 bug）
- 或填入所属 Sprint 编号（用于跨 Sprint 修复场景）
- `/sprint-bugfix sprint-{NNN}` 只会处理标注了该 Sprint 的 bug

### 执行步骤

#### Step 0：★ 待修 bug 先落记录（约定 10；⛔ 不得跳过直接改代码）

`bugfix` SKILL 只读 `docs/bugfix/{version}/bugfix-*.md`（其输入契约），故一切来源都先落成这里的条目：

- **来源 A · 已有记录**（用户手动写的 `bugfix-*-{user}.md` 表格行）→ 无需处理。
- **用户口述、尚无任何记录**（`/sprint-bugfix "<描述>"` 或自然语言路由进来的零散 bug）→ 按约定 10 写 `docs/bugfix/{version}/bugfix-{YYYYMMDD}-{user}.md`（一天一人一份，已存在则追加），含**表格行 + 详情章节**，字段按 `bugfix` SKILL Step 2.2b 的四字段（现象 / 归因 / 证据 / 处置）填。
- **来源 B · 问题汇总清单**：扫 `docs/testing/{version}/研发自测/**/*.md` + `docs/testing/{version}/正式用例/**/*.md` 末尾「问题汇总清单」表中状态为「待修复」的行，逐行追加到今日 `bugfix-{YYYYMMDD}-{user}.md`：
  - 字段映射：序号 / 用例 ID（反查执行步骤定位根因）/ 问题描述 / 严重程度 P0~P3 / 复现步骤；表格行「来源」列写回链 `<清单文件>#<序号>`。
  - **序号前缀**：`T-NNN` 用例自测发现 / `C-NNN` AI 自动化测试失败用例（`/sprint-batch` Step 6.5 写）/ `R-NNN` chrome 运行时错误（`/sprint-aiauto-test` Phase 2.4 写，问题描述带 `[chrome运行时]` 前缀；「用例 ID」为 `运行时-<页面>` 时根因定位以「复现步骤」列为准）。
  - **去重**：bugfix 文件里已有同一回链（`<清单文件>#<序号>`）→ 不重复追加；与来源 A 条目**问题描述完全相同**（去首尾空格 + 标点统一后 exact match）→ 视为重复、以 A 为主并补回链；⛔ 不做语义模糊合并。
  - Sprint 列：清单按版本组织，追加条目的 Sprint 列留空（零散模式处理）。

**Why**：命令路由表把「口述零散 bug」「测试问题清单」都指向本流程，而 SKILL 只扫 `docs/bugfix/`。不先落条目，这些 bug 要么被 SKILL 扫描忽略、要么修完查无此事，`/sprint-close` 归档与回归验证都拿不到。

#### Step 1：调用 bugfix skill（附项目级专项）

使用 `Skill` 工具调用 `bugfix` skill，参数 = 调用方给定的 `sprint-{NNN}` / 文件名，**都没有则留空（零散模式）**。修复流程（归因拆分 → 根因定位〔方法论 `superpowers:systematic-debugging`，⛔ 根因证据确认前不改代码〕→ 修复 → 逐项验证 → 修复报告）以 SKILL 为单一信源，命令端不复述、不另行调用 systematic-debugging（约定 21）。

调用 prompt **附带下列项目级专项**（SKILL 未覆盖，属本项目路径 / 配置类 bug 的附加检查）：

**★ 路径/URL/proxy 类 bug**（典型症状：404 / 双前缀 / `/<base>/<base>/...` 重复 / CORS / 跳转错误），修复前**必须**：

1. 读 `docs/design/detail/{version}/*事实清单.md` 的「路径消费者点」表，找到本 bug 涉及的全部上下游使用点
2. 用 `git log -p -- <消费者点文件>` 反查最近一次相关改动，验证当时是否漏改某个消费者点（典型反模式 — base 改后前端含 `!startsWith(baseURL)` 子条件的守卫反逻辑失效导致双前缀 404）
3. 修复时**同步审视事实清单的「反模式提示」段**，避免引入新的反逻辑
4. **修完单点不够 — 必须把同表中"形态类似"的其他消费者点也巡检一遍**（如改 axios 守卫必同时看 SSE / WebSocket 的独立 URL 拼装是否同病）
5. 如本次修复实际上是"base 已变但消费者未联动"的清算 → 必须回写事实清单的「⚠️ 本次变更」表「已联动消费者点」列

**★ 配置项清单联动**：本 bug 修复改动了任一配置文件（同 `/sprint-dev` Step X.7 触发条件清单）→ **同步执行** `/sprint-dev` Step X.7 的增量更新流程——往 `docs/deployment/{version}/配置文件/增量/配置项清单*.md` 的对应段（①新增配置 / ②删除配置 / ③运行时配置文件变更，**3 段代码块结构、无表格**）追加条目，行内注释标注来源（Sprint 编号或 `bugfix-{YYYYMMDD}`）。

**★ 部署流程 + SQL执行台账联动（检测驱动，独立于是否改配置）**：详见同目录 `rationale.md`「部署流程 + SQL执行台账联动的检测驱动细则」。

#### Step 2：推送分类与监听（约定 31.5）

部署上下文下，修复 push 前先保存 `BASE_REF`，调用 `python3 .aidp/scripts/classify_push.py --root . --version "$VERSION" --build "$BUILD" --base-ref "$BASE_REF"`（链外无 build → `--standalone`）。无正式代码变更且无分类错误 → 仍校验 push 成功、记 `cicd_skipped=true`，不监听 CICD、不跑探针；正式代码变更 / 分类缺失或错误 → 走 `cicd_watch.py --mode watch --commit <sha> --env <env>` 监听 CICD 流水线终态（`cicd.provider`，默认 GitHub Actions；失败经 `--mode retry` 重试≤3）+ `autopilot-deploy-watch.py` 就绪探针。⛔ 不得以远端状态反推分类。

#### Step 3：回填状态与报告链接

> **★ 契约边界（约定 21，与 SKILL 5.3 对齐）**：根因 / 证据 / 修复方案的**权威落点 = SKILL 生成的 `bugfix-*-report.md`**；问题记录与来源清单只就地回填状态、Commit 与报告链接，⛔ 不复写根因。

**bugfix 记录（`bugfix-*-{user}.md`）**——表格行「状态」改 `已修复`、「Commit」填 hash；详情章节追加一行 `修复报告：<report 相对路径>#<小节锚点>`，以及**部署提醒**（前端/后端/DB/Redis 是否需要重启或变更，报告未覆盖时）。

**来源 B 清单行**（由 Step 0 回链定位；**不改 template 表结构**，6 列保持原状）：
1. 「状态」列从 `待修复` 改为 `已修复`
2. 「复现步骤」列末尾**追加内嵌 HTML**（保持列数不变）：`<br><sub>✅ 已修复 / commit: <hash> / 报告: <report 相对路径></sub>`
3. **不要删行** — 清单本身就是审计轨迹，状态「待修复」→「已修复」→「已验证」逐步演进；/sprint-test Step 6 回归后再改「已验证」

#### Step 4：编译（后端）/ 前端校验（★ 仅改动侧 + 资源受限 + 前端不打包）

调用 `superpowers:verification-before-completion`：
- **仅处理本次 bugfix 实际改动的一侧**——改了后端才执行编译命令、改了前端才执行前端校验（**lint + 类型检查，不打包**），未改动侧不处理
- 执行走**资源受限方式**（`nice` + 限并发 worker/线程，可选 `taskset/cpulimit`，避免 CPU 打满），配方见 `agents/backend.md`「Step 7: 编译验证」/ `agents/frontend.md`「Step 4: 前端验收校验」；**前端不跑完整打包**，部署打包由使用者按需自行执行
- 运行相关单元测试

#### Step 5 ~ 6

> 📄 **本段全文见 `mode-b2.md`**（Step 5 自动回写设计文档〔约定 22 攒批 / `--cascade-now` 级联〕、Step 5.1 累进产物审计、Step 5.5 P0/P1 缺陷反哺回归用例、Step 6 更新 activeContext）。进入本段第一动作 = Read 该文件。
