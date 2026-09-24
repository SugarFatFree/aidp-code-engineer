# /version · 版本规划流程详情 — 分片 8/8

> 本片覆盖：**Step 2.5 progress / 2.6 activeContext / 2.7 更新版本 / 2.7.3 同步代码内应用版本号 / 2.7.4 收口上一版本变更台账 / 2.7.5 PRD快照 / 2.8 输出报告**。
> 完整分片清单见 `{{AIDP_HOME}}/commands/version.md` 的对应骨架表；按 Step 进度依次 `Read` 各分片，权威判定以本片正文为准。

<!-- BODY-BELOW -->
### Step 2.5.0：★ 审计落地门（进 Step 2.5 前的第一件事）

Step 2.4.7 的独立审计是规划产物「经审计才算数」的**唯一**承载者（也是 PRD 条目去处与
原型覆盖度两个 Critical 硬门的唯一落点）。⛔ 「跑了且通过」与「压根没跑」在终端上
**长得一模一样**——散文管不住这种形态，故本步以确定性脚本判定：

```bash
python3 {{AIDP_HOME}}/scripts/check_version_audit_landed.py --version {version} --json
# 用户显式传了 --skip-audit 时改为：… --version {version} --skip-audit --json
AUDIT_LANDED_EXIT=$?
```

- 退出码 `0` 且无 findings → 审计已落地，继续 Step 2.5。
- 退出码 `0` 且 findings 为 `audit-skipped-by-flag` → 合规豁免，但 **Step 2.8 报告必须如实写
  「本次规划产物未经独立审计（`--skip-audit`）」**，⛔ 不得写成「审计通过」。
- 退出码 `1` → **回跑 Step 2.4.7**（`planning-7.md`）。**交互式**：报出 findings 后停下；
  **无人值守**：按 `planning-7.md` 的 `audit-block` 同款处置交 autopilot 熔断，
  ⛔ 不得因为"看起来一切正常"就往下走。

### Step 2.5：初始化 memory/{version}/{user}/progress.md

如该文件不存在，按 `03_memory文件详细规范.md` 第 7 节（`progress.md`）模板创建，
并在「版本历史」表格中追加：

```markdown
| {version} | 待定 | {里程碑} | 待规划 | 🚧 开发中 | - |
```

如已存在（同用户已有其他版本），在「版本历史」表格中追加新行。

### Step 2.6：初始化 memory/{version}/{user}/activeContext.md

如不存在，按模板创建，头部填入 {version} 与 {user}，状态为"版本规划完成，等待 Sprint-001 执行"。

### Step 2.7：更新项目记忆文件「当前状态」当前版本

- `AGENTS.md`「当前状态.当前版本」改为 {version}。

*（Step 2.7.1 / 2.7.2 编号保留、暂未使用；其余分片有「见 Step 2.7.3」的直引，故不重排。）*

### Step 2.7.3：★ 同步代码内本应用版本号（构建描述符随版本号 bump 一起改）

> 版本号 bump 的落点是「文档 + 代码」两侧：Step 2.7 已写文档侧，本步补齐代码侧。理据见 `rationale.md`。

**执行**（扫描落点 / 归一化 / deny-list / 写回口径均以脚本为单一信源，本处不复述）：

```bash
python3 {{AIDP_HOME}}/scripts/check_version_identifier.py --version {version} --apply --json > /tmp/vid-plan-{version}.json
VID_EXIT=$?
```

- 默认档 `build-descriptor`：**自动改齐** `pom.xml` / `build.gradle(.kts)` / `package.json` / `Cargo.toml` / `pyproject.toml`
  **+ `Dockerfile`·`Containerfile`**（`LABEL version` / `LABEL org.opencontainers.image.version` / `ARG`·`ENV APP_VERSION` 等
  / `COPY`·`ADD` 产物名内嵌版本如 `app-0.2.0.jar`），
  **保留 `-SNAPSHOT` 等后缀**（`0.2.0-SNAPSHOT` → `0.3.0-SNAPSHOT`，不破坏 Maven 开发期惯例）、
  **剥掉 `V`/`v` 前缀**（`V0.11.2` → `0.12.0`）——匹配兼容三种形态，写回统一归一到**纯 semver**
  （前缀只属 AIDP 文档与 git tag；Maven·npm·Cargo·OCI 标签带 `V` 不规范甚至非法）；
  改父 pom 时**连带同步反应堆内子模块的 `<parent><version>`**（否则父子版本错位、`mvn` 解析不到父 POM）。
- **★ Dockerfile 只改白名单落点**：基础镜像 / 工具链 / 组件版本（`FROM`、`ARG BASE_IMAGE`、
  `ARG NGINX_VERSION`、`ENV JAVA_VERSION`）脚本一律不碰；`COPY app-*.jar` 通配写法自适应、不算落点；
  `COPY app-<版本>.jar` 硬编码写法**必须**跟着 pom 一起改（理据见 `rationale.md`）。
- 脚本自报 `applicable:false`（项目无任何自报版本落点）→ 记一行 INFO 跳过，不误报。
- **★ 第三方代码不在写回范围**：压缩产物 / `bower_components` / `a.VERSION=` 由脚本自动排除；
  vendored 的整个第三方工程脚本猜不准（理据见 `rationale.md`）—— **首次在本项目跑本步时须核对
  `applied[]` 清单**，发现第三方工程被改到就写进仓库根 `.aidp-version-ignore`（每行一个 glob，
  `#` 注释）后重跑；该文件是项目级长期声明，之后各版本自动生效。

**scope 外落点（`skipped_out_of_scope[]` — 代码常量 / `application.y(a)ml` / Dockerfile 裸 `ARG VERSION=`）的处置**：

| 场景 | 动作 |
|------|------|
| **交互式** | `AskUserQuestion` 二选一：① **一并改为本版本**（重跑脚本加 `--apply-scope all`，改完复验归零）② **保持不变**（写进规划报告「版本标识」段，留给发布期 Step 3.3.13 复核） |
| **无人值守**（`--unattended` / `--no-tag` / `LOOP_UNATTENDED`）| **不改**，WARN + 写进规划报告「版本标识」段，交发布期 Step 3.3.13 兜底（理据见 `rationale.md`）|

> ⚠️ 默认档可无人值守直接改、且与 Step 3.3.13「无人值守绝不自动改」不冲突，理据见 `rationale.md`。

- **补充模式（B-2）同样执行**：版本号未变时脚本为**幂等空操作**（0 处改动），但能兜住"上次漏改 / 中途被分支合并改回去"。
- **改动不自动提交**：与规划期其余产出（各类文档）同口径留在工作区，随用户下次提交带走；
  规划报告须列出**已改动的文件清单**（`applied[]` 逐处 `{file} {name}：{旧值} → {新值}`），让改动可见、可回退。

### Step 2.7.4：★ 收口上一版本遗留的开发期变更台账（约定 22 攒批级联 · 收口点 2）

> **单一信源 = `{{AIDP_HOME}}/reference/开发期族增量.md`**（台账格式 / 收口执行要点 / 跨版本落点 / 清理规则全在那份）。
> **进入本步第一动作 = Read 该文件**，本处只说明触发与范围，不复述规则。

- **触发**：**上一版本**（`{version}` 之前、按 SemVer 取最近）的**四族任一**增量册（含存量单册台账）
  有「待级联」条目时执行；四族全无 → 打印一行 INFO 跳过。路径走 `commit_gate.cascade_ledger_paths()`，⛔ 不自拼。
- **范围**：上一版本**四族全部**待级联条目（逐族走完，⛔ 不得"某族干净即收工"）。
- **动作**：派**独立子 Agent** 读四族增量册 → **结合代码现状核实**（条目是线索不是结论，被后续改动推翻的直接删、不产文档）
  → 按 `C-NNN` 跨族合并同类项 → **按族各自重判档位**（⛔ 不把四族改动量加总）→ 跑四级级联。
- **落点**：产物**落回上一版本**目录；若上一版本**已发布**（已打 tag、文档已冻结）→ 落**当前版本**并在产物头部注明
  `> 追溯自 {上一版本}：…因该版本已发布故落于本版本`。
- **★ 清理（必定清理，⛔ 不存在要保留的场景）**：本步结束时**上一版本的每一份增量册（含存量单册台账）
  必须已删除**——成功级联的条目随文件一并消失；**未能级联的条目【迁移】进当前版本 `{version}` 的
  【对应族】册子**（条目原文照搬 + 行尾加 `← 承接自 {上一版本}`，编号在新册内重排为连续 `C-{NNN}`；
  存量单册的条目按内容分派到对应族），随后 `git rm` 上一版本的这些文件。⛔ **不许**以"还有失败条目"
  为由留着——条目已在当前版本对应族的册子里继续攒批，留档只会造成同一条目两处并存。
- **★ 终态机器门（确定性，不通过不得进入 Step 2.7.5）**：
  ```bash
  # ★ 落点门（模式 A）必须与终态门并列跑：二者正交——终态门只看「台账清没清」，
  #   落点门只看「改动落在哪」（主文档 ✅ / 中转册 ❌ / 新建 NN_ 分册 ❌）。
  python3 {{AIDP_HOME}}/scripts/check_cascade_landing.py --worktree --version {上一版本} || exit 1
  # --transfer-to 支持逗号分隔多个目的地：拆四族后，条目按内容分派到哪一族要收口时才知道，
  # 故把当前版本四族册全部列为候选，任一找到痕迹即算转出到位。
  python3 {{AIDP_HOME}}/scripts/check_cascade_landing.py --must-delete --version {上一版本} \
    --transfer-to "docs/requirements/{version}/研发需求/_开发期需求增量.md,docs/design/detail/{version}/_开发期设计增量.md,docs/plans/{version}/_开发期计划增量.md,docs/testing/{version}/研发自测/_开发期用例增量.md"
  ```
  ① 断言**上一版本四族每一份都不存在**（有未决条目、打了 `LEDGER-ARCHIVED` 一律判失败——标记不替代删除）；
  ② **配套断言转出到位**——删前仍有 N 条未决时，`--transfer-to` 列出的当前版本册子里
  必须找得到 `← 承接自 {上一版本}` 痕迹，否则判 `deleted-without-transfer`。
  **必删 ≠ 把账删没**。理据见 `rationale.md`。
- **打印**：`📋 上一版本 {V} 攒批级联：处理 N 条（成功 M / 失效 K / 失败 J）→ 已写入各族主文档；上一版本四族册已全部删除；J 条未决已迁移进 {version} 对应族`（**恒为已删除**，无「保留」分支）。

### Step 2.7.5：★ 更新 PRD 快照

**所有子调用 + 校验全部通过**后，把当前 PRD、原型、**代码**三类输入的 sha256 + mtime 写入 / 更新 `memory/{version}/.aidp-inputs-snapshot.json`（★ `code_files` 取 `code-inventory.json` 内容 sha256 一条，⛔ 不逐文件 hash；清单缺失记 `code_snapshot: unavailable`、⛔ 不当"没变"。理据见 `rationale.md`）：

- fresh 模式（情况 A） → `snapshot_run: "fresh"`
- 补充模式（情况 B-2） → `snapshot_run: "supplement-{NN}"`
- `snapshot_at` 用 ISO-8601 本地时区
- 加入 .gitignore？**不要**，本快照需要进版本库随项目走，否则换台机器 / 换分支后 /version 会误判为 fresh
- 子调用 / 校验中途失败 → **绝不**更新快照，避免下次跑 /version 把"失败但有部分产物"误当"已完成"

### Step 2.8：输出规划报告

**fresh 模式输出**（情况 A）：

```
✅ 版本规划完成（{version} / fresh 模式）

版本号：{version}
里程碑：{里程碑}
当前开发者：{user}

📁 已创建目录骨架：
- docs/requirements/{version}/
- docs/design/detail/{version}/
- docs/testing/{version}/
- docs/plans/{version}/
- docs/reports/{version}/
- docs/prompts/{version}/
- docs/bugfix/{version}/
- docs/implementation/{version}/{user}/
- docs/prototype/{version}/mockup/
- docs/deployment/{version}/
- memory/{version}/{user}/（含 activeContext.md / progress.md / sprints/）

📋 已生成文档（各目录恒含专职 `00_索引.md`，约定 15）：
- 研发需求：docs/requirements/{version}/研发需求/00_索引.md + 01_研发需求.md（多系统则 `01_<系统>.md`/`02_<系统>.md` …）
- 详细设计：docs/design/detail/{version}/00_索引.md + 01_详细设计.md + 02_数据库设计.md + 03_接口设计.md（+ *事实清单.md，如 code/ 已存在）
- SQL 脚本：`docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql`（中文命名 + 两位数字序号前缀；`99_回滚脚本.sql` 序号保留；详见 /sprint-design Step 3）
- 研发执行计划：docs/plans/{version}/00_索引.md + 01_研发执行计划.md
- 研发自测用例：docs/testing/{version}/研发自测/00_索引.md（专职索引）+ 01_研发自测方案.md（方案）+ 02_全量自测用例.md（单文件）或 `02_自测用例-总览.md` + `03_<模块>.md`（+ `01_测试环境与账号.md` 配置文件，固定保留槽）— 由 `/sprint-selftest`（Step 2.4.3.5）生成

🔄 已更新：
- AGENTS.md「当前状态」指向 {version}
- memory/{version}/.aidp-inputs-snapshot.json（输入基线快照：PRD + 原型）

🏷️ 代码内本应用版本号（Step 2.7.3，改动未提交、随下次提交带走）：
- 已同步 {N} 处：{file} {name}：{旧值} → {新值}（逐处列出 `applied[]`）
- 未改 {M} 处（代码常量 / application.yml / Dockerfile 裸 VERSION，需人复核）：{file}:{line} {name} = {值} —— 交发布期 Step 3.3.13 复核
- 项目无自报版本落点时改为一行：`本项目无代码内自报版本落点，跳过`

📊 审计报告（Step 2.4.7 产出）：
- docs/audit/{version}/version-output-audit-YYYY-MM-DD.md
- 结论：✅ 通过 / ⚠️ 警告 / ❌ 阻塞（如阻塞应已在 Step 2.4.7 自动循环修复或用户手工干预后通过；强制忽略时此处标"⚠️ 强制忽略未通过项"）

📌 下一步：
- 分步 / 批量开发：/sprint-dev 001 开始第一个 Sprint（或 /sprint-batch 一键跑完研发执行计划所有 Sprint + 末段 AI 自动化测试）
- 🤖 7×24 全自动开发+测试（开发链路 + 测试链路双 /loop 并行；代码提交推送后远程 CI/CD（`cicd.provider`，默认 GitHub Actions）部署约 5 min → 部署完成自动跑 AI 自动化测试；全过程与结果按 `memory/aidp-config.yaml` 的 `notify` 配置发里程碑通知）：
    /sprint-autopilot                 # 首次直接调用 = 配置向导：检查里程碑通知渠道（notify.channels）+ 部署模式/CICD 等待时长，写入 baseline（两链路共享）
    # 配置完成后挂双 /loop 守护：
    /loop 10m /sprint-autopilot --unattended    # 开发链路：自动 /version + /sprint-batch + 提交推送触发 CICD 部署
    /loop 5m  /sprint-aiauto-test --unattended  # 测试链路：探测部署完成（约 5 min）→ AI 自动化测试 → 报告 + 里程碑通知
    # 或一句话口述交给 autopilot（首次会据此走配置向导确认通知渠道 / 部署模式后再挂 /loop 守护）：
    /sprint-autopilot {version} 版本规划已执行（文件均已生成），请你帮我自动执行后续的开发测试流程；当代码提交并推送后远程会自动执行 CICD 部署流程，大概需要 5 分钟部署完成；部署完成后再去执行 AI 自动化测试流程；任务执行的过程与结果通过里程碑通知推送。
```

**补充模式输出**（情况 B-2）：

```
✅ 版本规划补充完成（{version} / 补充 {NN}）

版本号：{version}
本轮序号：{NN}
触发原因：产品 PRD 变更（{变更文件数} 份文件）

📋 输入变更摘要：
- docs/requirements/{version}/研发需求/输入变更-{NN}.md（含 PRD 与原型变更的 diff 详情 + 受影响主文档预估）

📋 新增增量文档（统一 `NN_<业务主题>.md`，**文件名不带"补充"字眼**，NN 续编各目录现存最大序号 +1；补充身份记入 `00_索引.md`）：
- 研发需求：docs/requirements/{version}/研发需求/{NN}_<业务主题>.md
- 详细设计/接口设计/数据库设计：docs/design/detail/{version}/{NN}_<业务主题>.md（同目录多类型增量按序号连续续编）
- 增量 SQL：docs/deployment/{version}/sql/增量/{NN}_<中文名>.sql（如有 DDL；序号续在当前版本最大序号 +1）
- 研发执行计划：docs/plans/{version}/{NN}_<业务主题>.md
- 自测用例：docs/testing/{version}/研发自测/{NN}_<业务主题>.md（共享目录强制子目录化 — 历史扁平单文件在增量触发时自动迁入 `研发自测/02_全量自测用例.md`；研发自测导航锚 = `00_索引.md`，方案 `01_`，用例从 `02_` 起）

🔄 已回写：
- 上述各目录 `00_索引.md` 追加本轮增量行（类型=补充 + 生成时间 + 关联输入变更）
- memory/{version}/.aidp-inputs-snapshot.json → snapshot_run: "supplement-{NN}"
- 代码内本应用版本号（Step 2.7.3）：补充模式版本号未变，通常为 0 处改动；**有改动时逐处列出**（说明该处版本号与本版不一致、本轮已补齐）

📊 审计报告（Step 2.4.7 产出）：
- docs/audit/{version}/version-output-audit-补丁-{NN}.md
- 结论：✅ 通过 / ⚠️ 警告 / ❌ 阻塞（同 fresh 模式说明）

📌 下一步：
1. 阅读 输入变更-{NN}.md 确认变更范围理解一致
2. 阅读各目录 `00_索引.md`（类型=补充 行）找到本轮所有增量
3. 如本轮涉及 base/context-path 变更 → 检查事实清单的「⚠️ 本次变更」表 + /sprint-design Step 1.6.5 消费者级联告警是否已处理
4. 开发（三选一，与 fresh 模式一致）：
   - 累进开发本轮增量：/sprint-dev "<增量描述>"（累进 Sprint-{NNN}，前后端）或 /sprint-dev {NNN}
   - 全量开发：/sprint-batch（一键跑完研发执行计划所有 Sprint〔含本轮增量〕+ 末段 AI 自动化测试）
   - 🤖 7×24 全自动开发+测试（**推荐**；开发链路 + 测试链路双 /loop 并行，代码推送后远程 CI/CD（`cicd.provider`，默认 GitHub Actions）部署→自动跑 AI 自动化测试→里程碑通知）：
       /sprint-autopilot                 # 首次直接调用 = 配置向导（确认通知渠道 + 部署模式/CICD 等待时长，写 baseline）
       /loop 10m /sprint-autopilot --unattended    # 配置完成后挂开发链路守护
       /loop 5m  /sprint-aiauto-test --unattended  # 并行挂测试链路守护
       # 或一句话口述交给 autopilot（首次据此走配置向导）：
       /sprint-autopilot {version} 版本规划已执行（含本轮补充），请帮我自动执行后续开发测试流程；代码推送后远程 CI/CD（`cicd.provider`，默认 GitHub Actions）部署约 5 分钟；部署完成后跑 AI 自动化测试；过程与结果通过里程碑通知推送。
```

---

