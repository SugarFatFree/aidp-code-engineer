# sprint-design · 落盘后回检 详情 [1/2]（Step 1.6 / 1.6.5 + 派单方式 + SKILL 脚本复核）

> 本文件是 `/sprint-design` 命令 **落盘后回检段**的完整详细步骤，由命令主体在**进入该段时按需 `Read`**——多份产物的 grep / 路径比对 / 级联对账 + SKILL 脚本复核从「每次调用整体入上下文」改为「走到该段才载」；命令主体只留**骨架表 + Read 指针**。
>
> ⚠️ **权威性**：进入本段后，**以本文件为准逐项执行**，不得凭命令主体骨架或记忆略过任一子步骤。
> ⚠️ **维护**：本文件与命令主体同属 template 自有、随脚手架下发；改动后同步 bundle 副本 `assets/aidp/flows/sprint-design/step-1.6-落盘后回检.md`。理据/根因见同目录 `rationale.md`。

---

### ★ 落盘后回检：统一派独立子 Agent 执行（覆盖 Step 1.6 / 1.6.5 / 1.7 / 1.7.5 / 1.8 + SKILL 脚本复核；1.7 起在 `step-1.7-对外接口与溯源回检.md`，同一子 Agent 一并读、隔离上下文不占主对话）

后续 Step 1.6 / 1.6.5 / 1.7 / 1.7.5（读产物文档做静态核验）+ SKILL 脚本复核**全部并入一个 general-purpose 子 Agent 统一执行**，主对话不读产物文档正文 / 不读脚本 stdout，只据子 Agent 回传的紧凑结果决定是否暂停 Step 2~6。

**派单方式**：`Agent` 派 general-purpose 子 Agent（**不用 Explore**，理据见 `rationale.md`），prompt 传：Step 1.6~1.7.5 检查清单原文 + 下方「SKILL 脚本复核」与「需额外入参的补跑项」两段 + `HAS_OPEN_API`/`HAS_THIRD_PARTY_DEP` 信号 + 事实清单路径。子 Agent 一次读完产物、跑完全部回检与脚本、就地写各「⚠️ 告警」表，**只回传紧凑结果**：① 合并 Pass/Fail 表（各项 + 各脚本退出码）② 阻塞项（base 不匹配 / 消费者级联 P0 / 对外接口免登录违规 / 脚本判不通过，含 file:line + 建议）③ 自动归一化/补写清单。

- 子 Agent 回传任一**阻塞项** → 按各步原规则**暂停后续 Step 2~6**，等用户裁决；无阻塞项 → 继续。
- 子 Agent 失败（超时/异常/返回空）→ 命令端内联兜底跑同一组清单 + 脚本（标注"⚠️ 子 Agent 失效兜底"），禁止静默放过。

#### ★ SKILL 脚本复核（单一信源 = `dev-logic-architect` Quality Review，约定 21）

子 Agent 按 **`{{AIDP_HOME}}/skills/dev-logic-architect/references/flow-qr-dispatch.md`「🛡️ 落盘后 bash 硬核回检」原样跑全部脚本**（`<SKILL_DIR>` = `{{AIDP_HOME}}/skills/dev-logic-architect`，SQL 版本隔离门传 `docs/deployment --version {version}`），各脚本的触发条件、退出码语义、哪些发现等级不占退出码（须读 `--json`）、处置一律以该文件与 `quality-review-checklist.md` 为准，⛔ 命令端不另列清单、不复述判级。只回传各脚本退出码 + `--json` 的 Critical / Important / `skipped` 摘要。

#### ★ 需额外入参的补跑项（**具备入参时必跑**——SKILL 调度表写明「需 PRD / code_root，调用方具备时自行加跑」）

> 本组吃**代码现状 / PRD** 而非设计产物，规划期「设计已改、代码未跟上」天然会红——⛔ **一律 report-only（告警档），不做阻断**（理据见 `rationale.md`「代码侧加跑组」）。

| 脚本（`{{AIDP_HOME}}/skills/dev-logic-architect/scripts/`） | 入参 | 触发条件 |
|------|------|---------|
| `check_feature_reuse.py <设计目录> code/` | 设计目录 + 代码根 | `code/` 存在即跑 |
| `check_service_impl_stub.py code/` | 代码根 | 同上 |
| `check_third_party_dep_reverse.py code/` | 代码根 | 同上 |
| `check_sql_style_consistency.py . <设计目录>` | 仓库根 + 设计目录 | 有历史 SQL 时（脚本自判无历史即跳过） |
| `validate_coverage.py <PRD文件> <单个设计.md>` | PRD 文件 + **单个 `.md`**（多册逐册循环） | 有 PRD 原文时；`--json.skipped:true` = 未核验，⛔ 不得当通过 |

> 接口字段级契约对齐 `check_api_contract_alignment.py` 需已部署后端，规划期不具备 → 本段不跑；测试期消费者 = `/sprint-test` Step 3（探活成功即跑）。
> 处置：读各脚本 `--json` 的发现项，**汇总进 QR 报告的「待澄清 / 建议」段**（不进阻断清单）；确属设计缺陷的（如设计声称"沿用已有"但代码里根本没有那个能力）→ 按普通违规交还 skill 补正。

#### ★ 业务计数声明表的全库回扫（项目级，非 SKILL 脚本）

```bash
python3 {{AIDP_HOME}}/scripts/check_count_claims.py --project-claims "docs/design/detail/{version}/"
```

表不存在 → 整段跳过（不报错、不阻断）。有表则按其「散落面」正则全库回扫，列出两类**候选**：
① 非动态声明而数字对不上 ② 已声明为动态、却仍被写成「共 N / 恰 N」这类固定值断言。
**一律 WARN、判定权在人**——"取值域全集 14 项"是合法留存、"恰 14 行"是必须改的断言，
脚本只负责把候选列全，把人肉 `grep -rn` 变成逐条判定。

> 任一脚本不存在或抛异常 → 视为 SKILL 镜像漂移，提示用户跑 `aidp-code-engineer upgrade` 同步后重试。

### Step 1.6：★ 路径事实回检

skill 输出落盘后，命令端在 `docs/design/detail/{version}/*接口设计.md`（glob 兼容 `03_接口设计.md` 与历史裸名；及拆分后的同主题分册）里**抽取所有 URL 前缀/端口/proxy**，与 Step 0.6.5 的「事实清单」逐条比对。

**核心：把每个出现的路径拆成 `<base> + <endpoint 后缀>`**（base = context-path + API 版本前缀，由事实清单定义；endpoint 后缀 = 业务路径，由本次设计定义），分别校验：

1. **抽取**：用正则扫描设计文档里出现的 `/[\w\-]+(/[\w\-{}:]+)*` 形式路径 + `:[0-9]{2,5}` 形式端口
2. **base 校验**（**强约束**）：每个抽取出的路径，其 base 部分必须与事实清单某一行的「完整 base」完全一致（含大小写）；端口必须与事实清单一致
3. **endpoint 校验**（**弱约束**）：base 之后的业务路径段属于设计正常输出，**只要 base 对，新增任意 endpoint 后缀都合法**；只校验是否与同文档其它接口冲突
4. **不匹配处置**：
   - **base 不匹配** → 标红，写入头部「⚠️ 路径回检告警」表 (设计文档位置 / 写入 base / 事实清单 base / 处理建议)，**暂停后续 Step 2~6**，要求用户裁决：(a) 改设计文档对齐代码 / (b) 在事实清单「⚠️ 本次变更」声明改代码意图后重跑
   - **仅大小写/末尾斜杠差异** → 自动归一化（默认以事实清单为准），日志记一行不暂停
   - **endpoint 后缀重复 / 冲突** → 告警但不暂停，让 skill 二次修订
   - **设计文档完全没出现 base**（接口设计.md 里只写了 endpoint 没带 base）→ 校验通过；提示用户在文档开头声明"全文 base = 事实清单 X 行"以便阅读

**目的**：杜绝 Claude 凭印象编造 base prefix（典型反例：代码 `application.yml` 实际是 `/server/`，设计却写 `/portal/`）；同时不阻碍设计在合法 base 上新增 endpoint 的正常职责。

**Step 1.6.5：★ base 变更的消费者级联校验**

如事实清单的「⚠️ 本次变更」表**非空且变更涉及 base / context-path / 端口 / API 前缀**，命令端必须额外做：

1. 取出「⚠️ 本次变更」表里**「已联动消费者点」列**的清单
2. 与「路径消费者点」表中的所有条目逐项对账：
   - 「路径消费者点」表里出现、但变更表「已联动消费者点」未声明 → 标红，写入「⚠️ 消费者级联告警」表：(消费者点位置 / 当前用法 / 变更项 / 是否已 git diff 命中)
   - 通过 `git diff --name-only HEAD` 抽取本轮命令实际改动的文件，与消费者点表里的文件做交集，未命中的文件即"未联动"
3. **暂停后续 Step 2~6**，要求用户：
   - (a) 解释为何某些消费者点不需要联动（写入「⚠️ 本次变更」表的"已联动消费者点"列里以**括号注明"无需联动 — 原因 XXX"**），或
   - (b) 补上联动修改（让 Claude 自动针对这些消费者点逐个 Read → Edit）

**典型反模式触发器**（命令端额外做 grep 警告，**不阻塞流程**，列在「⚠️ 消费者级联告警」表后的「💡 反模式提示」段）：

| 模式 | grep 模式（正则） | 警告 |
|------|----------------|-----|
| 前端 URL 守卫含反逻辑 `&&` 子条件 | `startsWith\(.*\).*&&.*!.*startsWith` | URL 守卫含 `!` 反逻辑，base 含子前缀时易翻车，参考事实清单"反模式提示"段 |
| SSE / WS 独立维护 baseURL | 文件含 `EventSource` 或 `new WebSocket(` 且**未引用**项目主 axios 实例 | SSE/WS 独立 URL 拼装，base 变更易漏改 |

> .env 多 profile 间 `VITE_API_BASE_URL` 值不同是常见做法（dev 走相对路径 + proxy / prod 走绝对 URL 直连），**不**当反模式告警。

---

> ⏭️ **接续 `step-1.7-对外接口与溯源回检.md`**：Step 1.7（对外开放接口规范，`HAS_OPEN_API=true` 触发）/ Step 1.7.5（第三方接口职责边界，`HAS_THIRD_PARTY_DEP=true` 触发）/ Step 1.8（上游溯源完整性）——**由同一个子 Agent 一并执行**，不另派。
